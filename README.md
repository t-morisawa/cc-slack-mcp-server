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

```
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

```bash
# 依存関係をインストール
pip install mcp slack-bolt python-dotenv certifi

# MCPサーバーとして起動
mcp run server.py:mcp
```

## 使用方法

MCPクライアント（Claude Code等）から以下のツールを使用できます：

### ask_user_via_slack

```python
# 例：Claude Codeから使用
await ask_user_via_slack("この機能についてどう思いますか？")
```

1. 質問がSlackの指定チャンネルに投稿されます
2. ユーザーはスレッドで回答します
3. 5分以内に回答がない場合はタイムアウトします
4. 回答内容がMCPクライアントに返されます

## 注意事項

- スレッドでの返信のみが有効な回答として認識されます
- 複数の質問を同時に投稿することも可能です
- SSL証明書エラーを回避するため、`certifi`を使用しています

## トラブルシューティング

- 環境変数が正しく設定されているか確認
- Slackアプリの権限が適切に設定されているか確認
- チャンネルIDが正しいか確認（Cで始まる文字列）
- ボットがチャンネルに追加されているか確認
