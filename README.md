# Slack MCP Server

Claude CodeなどのMCPクライアントからSlackでやり取りができるMCPサーバーです。

## 概要

このサーバーは、MCP（Model Context Protocol）を使用してSlackとの連携を提供します。MCPクライアント（Claude CodeやContinue.devなど）から、Slackの特定のチャンネルに質問を投稿し、ユーザーからの回答を受け取ることができます。

## 機能

- **ask_user_via_slack**: 指定されたチャンネルに質問を投稿し、スレッドでの返信を待つ
- **非同期処理**: Slack Socket Modeを使用した非同期通信
- **タイムアウト機能**: 5分でタイムアウト（応答がない場合）

## 必要な環境変数

`.env`ファイルまたは環境変数として以下を設定してください：

```.env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_CHANNEL_ID=C1234567890
```

## Slackアプリの設定

1. [Slack API](https://api.slack.com/apps)でアプリを作成
2. **Bot Token Scopes**で以下の権限を設定：
   - `chat:write`
   - `channels:read`
   - `channels:history`
3. **Socket Mode**を有効化してApp-Level Tokenを取得
4. **Event Subscriptions**で`message.channels`イベントを設定
5. アプリを対象チャンネルに追加

## インストール・起動

### 1. uvのインストール

公式推奨の高速パッケージマネージャ[uv](https://github.com/astral-sh/uv)を使います。

```bash
# Mac/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows（PowerShell）
iwr -useb https://astral.sh/uv/install.ps1 | iex
```

### 2. プロジェクトのセットアップ

```bash
# 仮想環境の作成
uv venv

# 仮想環境のアクティベート
# Mac/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 依存関係のインストール
uv pip install -r requirements.txt
```

### 3. 環境変数の設定

プロジェクトルートに `.env` ファイルを作成し、以下の環境変数を設定：

```.env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_CHANNEL_ID=C1234567890
```

### 4. MCPクライアントでの使用

Claude CodeやContinue.devなどのMCPクライアントから以下のようにサーバーを設定：

```json
{
  "mcpServers": {
    "slack-mcp": {
      "command": "uv",
      "args": ["run", "server.py"],
      "cwd": "/path/to/cc-slack-mcp-server"
    }
  }
}
```

### 5. Claude CodeでのMCPサーバー追加コマンド

Claude Codeのコマンドラインから、以下のコマンドでMCPサーバーを追加できます：

```bash
claude mcp add cc-slack uv run /path/to/cc-slack-mcp-server/server.py
```

- `cc-slack`：サーバー名（任意）
- `uv run ...`：仮想環境・依存関係を自動で解決しつつサーバーを起動

このコマンドを実行すると、Claude CodeのMCPサーバー一覧に`cc-slack`が追加され、MCPツールが利用できるようになります。

### 6. デバッグ

```bash
uv run mcp dev server.py
```

- Command: `uv`
- Arguments: `run server.py`
