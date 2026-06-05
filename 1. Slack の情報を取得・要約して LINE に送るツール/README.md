# Slack Summary to LINE

指定したSlackチャンネルの直近メッセージを取得し、Claude APIで要約してLINEに通知するPythonツール。

## 機能

- Slackの指定チャンネルから直近24時間のメッセージを取得
- Claude APIで日本語の箇条書き要約を生成
- LINE Messaging API経由で個人アカウントに通知
- cronで毎日自動実行可能

## 必要なもの

- Python 3.10 以上
- Slack Bot Token（`xoxb-`） ※スコープ: `channels:history`, `channels:read`, `users:read`
- Anthropic API キー
- LINE チャネルアクセストークン & ユーザーID

## セットアップ

### 1. リポジトリをクローン

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

### 2. 仮想環境を作成・有効化

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

### 4. 環境変数を設定

```bash
cp .env.example .env
```

`.env` を開いて各値を入力する（下記「環境変数」を参照）。

### 5. 動作確認

```bash
python main.py
```

## 環境変数

| キー | 説明 |
|------|------|
| `SLACK_BOT_TOKEN` | Slack Bot Token（`xoxb-`で始まる） |
| `SLACK_CHANNEL_ID` | 取得対象チャンネルのID（`Cxxxxxxxxxx`） |
| `ANTHROPIC_API_KEY` | Anthropic APIキー |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINEチャネルアクセストークン |
| `LINE_USER_ID` | LINE送信先ユーザーID（`Uxxxxxxxxxx`） |
| `FETCH_HOURS` | 何時間前までのメッセージを取得するか（デフォルト: `24`） |
| `CLAUDE_MODEL` | 使用するClaudeモデル（デフォルト: `claude-haiku-4-5-20251001`） |

## cron設定（Mac）

```bash
crontab -e
```

以下を追記（毎日午前8時に実行する例）：

```
0 8 * * * /path/to/.venv/bin/python /path/to/main.py >> /path/to/logs/cron.log 2>&1
```

> macOSではスリープ中はcronが実行されないため、常時起動が前提。

## ディレクトリ構成

```
.
├── main.py            # エントリーポイント
├── slack_client.py    # Slack API呼び出し・メッセージ整形
├── summarizer.py      # Claude APIによる要約生成
├── line_notifier.py   # LINE Push Message送信
├── config.py          # 環境変数の読み込み
├── .env               # 環境変数（git管理外）
├── .env.example       # 環境変数のテンプレート
├── requirements.txt   # 依存パッケージ
└── requirements.md    # 要件定義書
```

## 使用API

| サービス | API |
|---------|-----|
| Slack | [Web API – conversations.history](https://api.slack.com/methods/conversations.history) |
| Anthropic | [Messages API](https://docs.anthropic.com/en/api/messages) |
| LINE | [Messaging API – Push Message](https://developers.line.biz/en/reference/messaging-api/#send-push-message) |
