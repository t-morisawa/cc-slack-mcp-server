import os
import sys
import asyncio
import ssl
import certifi
import time
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

# MCP Server
from mcp.server.fastmcp import FastMCP

# Slack
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient

# --- 環境設定 ---
# .envファイルから環境変数を読み込む
load_dotenv()
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")

# --- 初期化 ---
# SSL contextを作成（SSL証明書エラーを回避）
ssl_context = ssl.create_default_context(cafile=certifi.where())

# SSL設定を含むWebClientを作成
web_client = AsyncWebClient(token=SLACK_BOT_TOKEN, ssl=ssl_context)

# Slack Boltアプリを非同期で初期化（SSL設定を含むWebClientを渡す）
app = AsyncApp(token=SLACK_BOT_TOKEN, client=web_client)

# --- 応答待機のためのグローバル変数 ---
# 形式: { "スレッドのタイムスタンプ": {"response": "返信内容", "found": True/False} }
polling_requests: Dict[str, Dict[str, Any]] = {}

# --- スレッド継続のためのグローバル変数 ---
# 最初のメッセージのタイムスタンプを保存し、2回目以降はスレッドで投稿するために使用
current_thread_ts: str = ""

# --- ポーリング設定 ---
POLLING_INTERVAL = 60.0 # 1分に1回しかリクエストできない

# --- アプリケーションコンテキスト ---
@dataclass
class AppContext:
    handler: AsyncSocketModeHandler
    handler_task: asyncio.Task

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """サーバーのライフサイクルを管理する"""
    print("Starting Slack Socket Mode handler...", file=sys.stderr)
    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    
    # 接続状態を監視するためのコールバック
    async def connection_callback():
        print("[DEBUG] Socket Mode connection callback triggered", file=sys.stderr)
    
    handler_task = asyncio.create_task(handler.start_async())
    
    # 短時間待機してハンドラーが正常に起動するまで待つ
    await asyncio.sleep(1)
    print("Slack Socket Mode handler started successfully.", file=sys.stderr)
    
    # 接続テスト
    try:
        print("[DEBUG] Testing Slack API connection...", file=sys.stderr)
        response = await app.client.api_test()
        print(f"[DEBUG] API test result: {response}", file=sys.stderr)
        
        # Auth test
        auth_response = await app.client.auth_test()
        print(f"[DEBUG] Auth test result: {auth_response}", file=sys.stderr)
        
    except Exception as e:
        print(f"[ERROR] Connection test failed: {e}", file=sys.stderr)
    
    try:
        yield AppContext(handler=handler, handler_task=handler_task)
    finally:
        print("Stopping Slack Socket Mode handler...", file=sys.stderr)
        try:
            await handler.close_async()
        except Exception as e:
            print(f"Handler close error: {e}", file=sys.stderr)
        
        if handler_task and not handler_task.done():
            handler_task.cancel()
            try:
                await handler_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"Handler task cancellation error: {e}", file=sys.stderr)
        print("Slack Socket Mode handler stopped.", file=sys.stderr)

# MCPサーバーを"SlackInputServer"という名前でインスタンス化（lifespanを指定）
mcp = FastMCP("SlackInputServer", lifespan=app_lifespan)

# --- ポーリング関数 ---
async def poll_for_thread_replies(thread_ts: str, since_ts: Optional[str] = None) -> Optional[str]:
    """
    指定されたスレッドの返信をポーリングで取得する
    
    :param thread_ts: スレッドのタイムスタンプ
    :param since_ts: この時刻以降のメッセージのみを取得
    :return: 新しい返信があればそのテキスト、なければNone
    """
    try:
        # チャンネルIDの確認
        if not SLACK_CHANNEL_ID:
            print("[ERROR] SLACK_CHANNEL_ID is not set", file=sys.stderr)
            return None
        
        # スレッドの返信を取得
        response = await app.client.conversations_replies(
            channel=SLACK_CHANNEL_ID,
            ts=thread_ts,
            oldest=since_ts if since_ts else thread_ts
        )
        
        if not response["ok"]:
            print(f"[ERROR] Failed to get thread replies: {response['error']}", file=sys.stderr)
            return None
        
        messages = response.get("messages")
        if not messages:
            print(f"[DEBUG] No messages found in thread", file=sys.stderr)
            return None
        
        print(f"[DEBUG] Polling found {len(messages)} messages in thread", file=sys.stderr)
        
        # Bot自身のメッセージを除外し、スレッドの最初のメッセージより新しいメッセージを探す
        bot_user_id = None
        try:
            auth_response = await app.client.auth_test()
            bot_user_id = auth_response["user_id"]
        except:
            pass
        
        for message in messages:
            message_ts = message.get("ts")
            user_id = message.get("user")
            text = message.get("text", "")
            
            print(f"[DEBUG] Checking message: ts={message_ts}, user={user_id}, text={text}", file=sys.stderr)
            
            # Bot自身のメッセージはスキップ
            if user_id == bot_user_id:
                print(f"[DEBUG] Skipping bot message", file=sys.stderr)
                continue
            
            # 最初のメッセージ（質問）はスキップ
            if message_ts == thread_ts:
                print(f"[DEBUG] Skipping original message", file=sys.stderr)
                continue
            
            # since_ts以降のメッセージのみを対象とする
            if since_ts and message_ts <= since_ts:
                print(f"[DEBUG] Skipping old message", file=sys.stderr)
                continue
            
            # 有効な返信を見つけた
            if text.strip():
                print(f"[DEBUG] Found valid reply: {text}", file=sys.stderr)
                return text
        
        return None
        
    except Exception as e:
        print(f"[ERROR] Error polling thread replies: {e}", file=sys.stderr)
        return None

# --- MCPツール ---
@mcp.tool()
async def ask_user_via_slack(question: str) -> str:
    """
    指定された質問をSlackの特定チャンネルに投稿し、ユーザーからのスレッド返信を待ち、その内容を文字列として返す。
    ポーリングベースでメッセージを受信するため、イベント駆動の不安定さを回避する。
    応答がない場合、5分でタイムアウトする。
    
    初回は新規メッセージとして投稿し、2回目以降は同じスレッドで投稿される。

    :param question: ユーザーに尋ねたい質問内容のテキスト。
    :return: ユーザーからの返信テキスト。タイムアウトした場合はエラーメッセージを返す。
    """
    global current_thread_ts
    
    print(f"[DEBUG] ask_user_via_slack called with question: {question}", file=sys.stderr)
    
    if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_ID]):
        return "エラー: Slack連携に必要な環境変数が設定されていません。"

    # コンテキストからハンドラーを取得
    ctx = mcp.get_context()
    app_ctx = ctx.request_context.lifespan_context
    
    print(f"[DEBUG] Handler context available: {app_ctx is not None}", file=sys.stderr)
    
    message_ts = None
    response_waiting_ts = None
    
    try:
        # 1. Slackに質問を投稿（初回は新規メッセージ、2回目以降はスレッドで投稿）
        if SLACK_CHANNEL_ID is None:
            raise ValueError("SLACK_CHANNEL_IDが設定されていません。")
        
        print(f"[DEBUG] Current thread_ts: {current_thread_ts}", file=sys.stderr)
        
        if current_thread_ts:
            # 2回目以降：スレッドで投稿
            print(f"[DEBUG] Posting to existing thread: {current_thread_ts}", file=sys.stderr)
            result = await app.client.chat_postMessage(
                channel=str(SLACK_CHANNEL_ID),
                text=question,
                thread_ts=current_thread_ts
            )
            message_ts = result["ts"]
            # 応答を待つためには、最初のメッセージのタイムスタンプを使用
            response_waiting_ts = current_thread_ts
        else:
            # 初回：新規メッセージとして投稿
            print(f"[DEBUG] Posting new message to channel: {SLACK_CHANNEL_ID}", file=sys.stderr)
            result = await app.client.chat_postMessage(
                channel=str(SLACK_CHANNEL_ID),
                text=question
            )
            message_ts = str(result["ts"])
            response_waiting_ts = message_ts
            # 最初のメッセージのタイムスタンプを保存
            current_thread_ts = message_ts
            print(f"[DEBUG] New thread_ts set: {current_thread_ts}", file=sys.stderr)
        
        print(f"[DEBUG] Message posted successfully. message_ts: {message_ts}, response_waiting_ts: {response_waiting_ts}", file=sys.stderr)
        
        # 2. ポーリングリクエストを登録
        polling_requests[str(response_waiting_ts)] = {"response": None, "found": False}
        
        print(f"[DEBUG] Added to polling_requests: {str(response_waiting_ts)}", file=sys.stderr)
        print(f"[DEBUG] Current polling_requests keys: {list(polling_requests.keys())}", file=sys.stderr)
        
        # 3. ポーリングで応答を待つ
        print(f"[DEBUG] Starting polling for user response...", file=sys.stderr)
        start_time = time.time()
        timeout = 300.0  # 5分
        last_checked_ts = message_ts  # 投稿したメッセージのタイムスタンプ
        
        while time.time() - start_time < timeout:
            # 指定間隔で待機
            await asyncio.sleep(POLLING_INTERVAL)

            # ポーリングで新しい返信をチェック
            reply_text = await poll_for_thread_replies(str(response_waiting_ts), last_checked_ts)
            
            if reply_text:
                print(f"[DEBUG] Received response via polling: {reply_text}", file=sys.stderr)
                polling_requests[str(response_waiting_ts)]["response"] = reply_text
                polling_requests[str(response_waiting_ts)]["found"] = True
                break
        
        # 4. 結果を確認
        if polling_requests[str(response_waiting_ts)]["found"]:
            response_text = polling_requests[str(response_waiting_ts)]["response"]
            print(f"[DEBUG] Successfully received response: {response_text}", file=sys.stderr)
            return f"ユーザーからの回答は「{response_text}」です。これに対するあなたの回答を作成し、再度Slackに投稿してください。"
        else:
            print("[DEBUG] Timeout occurred - no response within 5 minutes", file=sys.stderr)
            return "エラー: ユーザーからの応答が5分以内にありませんでした。"

    except Exception as e:
        print(f"[ERROR] Error in ask_user_via_slack: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return f"エラーが発生しました: {e}"
    finally:
        # 処理が完了したら、待機リストから該当リクエストを削除
        if response_waiting_ts and str(response_waiting_ts) in polling_requests:
            del polling_requests[str(response_waiting_ts)]
            print(f"[DEBUG] Removed from polling_requests: {str(response_waiting_ts)}", file=sys.stderr)
        print(f"[DEBUG] ask_user_via_slack completed", file=sys.stderr)

# --- サーバー起動用メイン関数 ---
# `mcp run server.py:mcp`で実行されるため、この部分は直接は使われないが、
# サーバーの起動ロジックをカプセル化するために定義しておく。
async def main():
    """MCPサーバーとSlackハンドラを起動する"""
    print("このスクリプトは `mcp run server.py:mcp` コマンドで起動してください。", file=sys.stderr)
    print("Slackハンドラーはサーバーのライフサイクルで自動管理されます。", file=sys.stderr)
    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    await handler.start_async()
    # handler_task = asyncio.create_task(handler.start_async())
    # await asyncio.sleep(10000)

# このスクリプトを直接実行した際の動作確認用
if __name__ == "__main__":
    print("このスクリプトは `mcp run server.py:mcp` コマンドで起動してください。", file=sys.stderr)
    print("直接実行すると、Slackのリスナーのみが起動し、MCPツールは利用できません。", file=sys.stderr)
    
    # 動作確認のためにSlackハンドラのみを起動
    asyncio.run(main())
