import os
import asyncio
import ssl
import certifi
from dotenv import load_dotenv
from typing import Dict, Any
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

# MCP Server
from mcp.server.fastmcp import FastMCP

# Slack
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient

# --- Environment Setup ---
# Load environment variables from .env file
load_dotenv()
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")

# --- Initialization ---
# Create SSL context (to avoid SSL certificate errors)
ssl_context = ssl.create_default_context(cafile=certifi.where())

# Create WebClient with SSL settings
web_client = AsyncWebClient(token=SLACK_BOT_TOKEN, ssl=ssl_context)

# Initialize Slack Bolt app asynchronously (pass WebClient with SSL settings)
app = AsyncApp(token=SLACK_BOT_TOKEN, client=web_client)

# --- Global variable for waiting for responses ---
# Format: { "message timestamp": {"event": asyncio.Event(), "response": "reply content"} }
pending_requests: Dict[str, Dict[str, Any]] = {}

# --- Global variable for thread continuation ---
# Save the timestamp of the first message, and use it for posting in the same thread from the second time onwards
current_thread_ts: str = ""

# --- Application Context ---
@dataclass
class AppContext:
    handler: AsyncSocketModeHandler
    handler_task: asyncio.Task

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage the server lifecycle"""
    print("Starting Slack Socket Mode handler...")
    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    handler_task = asyncio.create_task(handler.start_async())
    
    # Wait briefly for the handler to start properly
    await asyncio.sleep(1)
    print("Slack Socket Mode handler started successfully.")
    
    try:
        yield AppContext(handler=handler, handler_task=handler_task)
    finally:
        print("Stopping Slack Socket Mode handler...")
        try:
            await handler.close_async()
        except Exception as e:
            print(f"Handler close error: {e}")
        
        if handler_task and not handler_task.done():
            handler_task.cancel()
            try:
                await handler_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"Handler task cancellation error: {e}")
        print("Slack Socket Mode handler stopped.")

# Instantiate the MCP server as "SlackInputServer" (specifying lifespan)
mcp = FastMCP("SlackInputServer", lifespan=app_lifespan)

# --- Slack Event Listener ---
@app.event("message")
async def handle_message_events(body: Dict[str, Any]):
    """
    Handle Slack message events.
    Detect replies in threads and pass the response to the waiting tool.
    """
    event = body.get("event", {})
    thread_ts = event.get("thread_ts")
    user_text = event.get("text")
    print(f"thread_ts: {thread_ts}, user_text: {user_text}")

    # If this is a reply in a thread and the thread is a pending request
    if thread_ts and thread_ts in pending_requests:
        await app.client.chat_postMessage(
            channel=str(SLACK_CHANNEL_ID),
            text="Received your message. Please wait.",
            thread_ts=thread_ts
        )
        request_info = pending_requests[thread_ts]
        # Save the response content
        request_info["response"] = user_text
        # Set the event to signal and release the wait in ask_user_via_slack
        request_info["event"].set()

# --- MCP Tool ---
@mcp.tool()
async def ask_user_via_slack(question: str) -> str:
    """
    Post the specified question to a specific Slack channel, wait for a thread reply from a user, and return the content as a string.
    If there is no response, timeout after 30 minutes.
    
    The first time, post as a new message; from the second time onwards, post in the same thread.

    :param question: The text of the question to ask the user.
    :return: The reply text from the user. If timed out, returns an error message.
    """
    global current_thread_ts
    
    if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_ID]):
        return "Error: Required environment variables for Slack integration are not set."

    # Get handler from context
    ctx = mcp.get_context()
    app_ctx = ctx.request_context.lifespan_context
    
    message_ts = None
    
    try:
        # 1. Post the question to Slack (first time as a new message, from the second time in the thread)
        if SLACK_CHANNEL_ID is None:
            raise ValueError("SLACK_CHANNEL_ID is not set.")
        
        if current_thread_ts:
            # From the second time: post in the thread
            result = await app.client.chat_postMessage(
                channel=str(SLACK_CHANNEL_ID),
                text=question,
                thread_ts=current_thread_ts
            )
            message_ts = result["ts"]
            # Use the timestamp of the first message to wait for a response
            response_waiting_ts = current_thread_ts
        else:
            # First time: post as a new message
            result = await app.client.chat_postMessage(
                channel=str(SLACK_CHANNEL_ID),
                text=question
            )
            message_ts = str(result["ts"])
            response_waiting_ts = message_ts
            # Save the timestamp of the first message
            current_thread_ts = message_ts
        
        # 2. Create an event to wait for a response and register it in the pending list
        event = asyncio.Event()
        pending_requests[str(response_waiting_ts)] = {"event": event, "response": None}
        
        # 3. Wait for the event to be set (timeout set to 1800 seconds = 30 minutes)
        await asyncio.wait_for(event.wait(), timeout=1800.0)

        # 4. When the event is set, get the saved response
        response_text = pending_requests[str(response_waiting_ts)]["response"]
        return f"The user's answer is: '{response_text}'. Please create your response to this and post it to Slack again."

    except asyncio.TimeoutError:
        return "Error: No response from the user within 5 minutes."
    except Exception as e:
        return f"An error occurred: {e}"
    finally:
        # After processing, remove the request from the pending list
        if message_ts and str(response_waiting_ts) in pending_requests:
            del pending_requests[str(response_waiting_ts)]

# --- Main function to start the server ---
# This part is not used directly because it is run with `mcp run server.py:mcp`,
# but is defined to encapsulate the server startup logic.
async def main():
    """Start the MCP server and Slack handler"""
    print("Please start this script with the `mcp run server.py:mcp` command.")
    print("The Slack handler is automatically managed by the server lifecycle.")

# For testing when running this script directly
if __name__ == "__main__":
    mcp.run(transport='stdio')
