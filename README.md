# cc-slack

This is an MCP server for interacting with coding agents such as Claude Code via Slack.

## Overview

This server provides integration with Slack using the Model Context Protocol (MCP). You can post questions from an MCP client (such as Claude Code or Continue.dev) to a specific Slack channel and receive responses from users. You can also continue the conversation in the same thread.

## Features

- **ask_user_via_slack**: Posts a question to a specified Slack channel and waits for a reply in the thread
- **Timeout**: 30-minute timeout if no response is received

## Slack App Configuration

1. Create an app at [Slack API](https://api.slack.com/apps)
2. Under **Bot Token Scopes**, add the following permissions:
   - `chat:write`
   - `channels:read`
   - `channels:history`
3. Enable **Socket Mode** and obtain an App-Level Token
4. Under **Event Subscriptions**, subscribe to the `message.channels` event
5. Add the app to the target channel

## Installation & Startup

### 1. Install uv

```bash
# Mac/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
iwr -useb https://astral.sh/uv/install.ps1 | iex
```

### 2. Project Setup

```bash
# Create a virtual environment
uv venv

# Activate the virtual environment
# Mac/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt
```

### 3. Set Environment Variables

Create a `.env` file in the project root and set the following variables:

```.env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_CHANNEL_ID=C1234567890
```

### 4. Using with MCP Clients

Configure your MCP client (e.g., Claude Code or Continue.dev) as follows:

```json
{
  "mcpServers": {
    "cc-slack": {
      "command": "uv",
      "args": ["run", "server.py"],
      "cwd": "/path/to/cc-slack-mcp-server"
    }
  }
}
```

To add the MCP server from the Claude Code command line:

```bash
claude mcp add cc-slack uv run /path/to/cc-slack-mcp-server/server.py
```

- `cc-slack`: Server name (arbitrary)
- `uv run ...`: Starts the server with automatic virtual environment and dependency resolution

After running this command, `cc-slack` will be added to the list of MCP servers in Claude Code, and MCP tools will be available.

**Note:** Since it is not possible to grant command permissions from Slack, it is recommended to run the server in a safe environment with auto-run or dangerously-skip-permissions mode enabled, so that the server does not prompt for command permissions.

### 5. Debugging

```bash
uv run mcp dev server.py
```

- Command: `uv`
- Arguments: `run server.py`
