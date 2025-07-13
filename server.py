import os
import asyncio
import ssl
import certifi
from dotenv import load_dotenv
from typing import Dict, Any
from contextlib import asynccontextmanager

# MCP Server
from mcp.server.fastmcp import FastMCP
from dataclasses import dataclass

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
# 形式: { "メッセージのタイムスタンプ": {"event": asyncio.Event(), "response": "返信内容"} }
pending_requests: Dict[str, Dict[str, Any]] = {}

# MCPサーバーを"SlackInputServer"という名前でインスタンス化
mcp = FastMCP("SlackInputServer")

# --- Slackイベントリスナー ---
@app.event("message")
async def handle_message_events(body: Dict[str, Any]):
    """
    Slackのメッセージイベントを処理する。
    スレッドへの返信を検知し、待機中のツールに応答を渡すのが目的。
    """
    event = body.get("event", {})
    thread_ts = event.get("thread_ts")
    user_text = event.get("text")
    print(f"thread_ts: {thread_ts}, user_text: {user_text}")
    
    # スレッドへの返信であり、かつそのスレッドが待機中のリクエストである場合
    if thread_ts and thread_ts in pending_requests:
        request_info = pending_requests[thread_ts]
        # 応答内容を保存
        request_info["response"] = user_text
        # イベントをシグナル状態にし、ask_user_via_slack関数の待機を解除する
        request_info["event"].set()

# --- MCPツール ---
@mcp.tool()
async def ask_user_via_slack(question: str) -> str:
    """
    指定された質問をSlackの特定チャンネルに投稿し、ユーザーからのスレッド返信を待ち、その内容を文字列として返す。
    応答がない場合、5分でタイムアウトする。

    :param question: ユーザーに尋ねたい質問内容のテキスト。
    :return: ユーザーからの返信テキスト。タイムアウトした場合はエラーメッセージを返す。
    """
    if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_ID]):
        return "エラー: Slack連携に必要な環境変数が設定されていません。"

    message_ts = None
    handler = None
    handler_task = None
    
    try:
        # 1. Slackに質問を投稿
        if SLACK_CHANNEL_ID is None:
            raise ValueError("SLACK_CHANNEL_IDが設定されていません。")
        result = await app.client.chat_postMessage(
            channel=str(SLACK_CHANNEL_ID),
            text=question
        )
        message_ts = result["ts"]
        
        # 2. 応答を待つためのイベントを作成し、待機リストに登録
        event = asyncio.Event()
        pending_requests[str(message_ts)] = {"event": event, "response": None}

        # 3. 別タスクでAsyncSocketModeHandlerを起動
        handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
        handler_task = asyncio.create_task(handler.start_async())
        
        # 4. イベントが発生するのを待つ (タイムアウトを300秒=5分に設定)
        await asyncio.wait_for(event.wait(), timeout=300.0)

        # 5. イベントが発生したら、保存された応答を取得
        response_text = pending_requests[str(message_ts)]["response"]
        return f"ユーザーからの回答: '{response_text}'"

    except asyncio.TimeoutError:
        return "エラー: ユーザーからの応答が5分以内にありませんでした。"
    except Exception as e:
        return f"エラーが発生しました: {e}"
    finally:
        # 6. ハンドラーを停止し、タスクをキャンセル
        if handler:
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
        
        # 7. 処理が完了したら、待機リストから該当リクエストを削除
        if message_ts and message_ts in pending_requests:
            del pending_requests[str(message_ts)]

# --- サーバー起動用メイン関数 ---
# `mcp run server.py:mcp`で実行されるため、この部分は直接は使われないが、
# サーバーの起動ロジックをカプセル化するために定義しておく。
async def main():
    """MCPサーバーとSlackハンドラを起動する"""
    print("Starting Slack Socket Mode handler...")
    # Slack Socket Modeハンドラをバックグラウンドタスクとして起動
    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    await handler.start_async()

# このスクリプトを直接実行した際の動作確認用
if __name__ == "__main__":
    print("このスクリプトは `mcp run server.py:mcp` コマンドで起動してください。")
    print("直接実行すると、Slackのリスナーのみが起動し、MCPツールは利用できません。")
    
    # 動作確認のためにSlackハンドラのみを起動
    asyncio.run(main())
