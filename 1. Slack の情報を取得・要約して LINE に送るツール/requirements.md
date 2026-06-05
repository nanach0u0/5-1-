# 要件定義書：Slack要約→LINE通知ツール

## 1. 概要

指定したSlackチャンネルの当日メッセージを定期取得し、Claude APIで日本語要約を生成してLINEに通知するPythonツール。

---

## 2. 機能要件

### 必須（MVP）

| # | 機能 | 説明 |
|---|------|------|
| F-01 | Slackメッセージ取得 | 指定チャンネルの直近N時間のメッセージを取得 |
| F-02 | Claude要約生成 | 取得メッセージをClaude APIに渡し、箇条書き要約を生成 |
| F-03 | LINE通知 | 生成した要約をLINE Messaging API経由で送信 |
| F-04 | cron対応 | 単一スクリプト実行で完結（crontabから直接呼び出せる） |
| F-05 | メッセージゼロ対応 | 取得件数が0件の場合はLINE通知をスキップ（またはその旨を通知） |

### 任意（MVP後に追加検討）

| # | 機能 | 説明 |
|---|------|------|
| O-01 | 複数チャンネル対応 | 設定ファイルで複数チャンネルを列挙して一括処理 |
| O-02 | スレッド取得 | スレッド内の返信も含めて要約 |
| O-03 | メンション検出 | 自分へのメンションを優先的に要約に含める |
| O-04 | 実行ログ記録 | ローカルファイルまたは標準出力にログを保存 |
| O-05 | リトライ処理 | API呼び出し失敗時の指数バックオフリトライ |
| O-06 | LINE グループ送信 | 個人ではなくグループ・トークルームへの送信 |

---

## 3. 使用API・必要なスコープ・トークン

### 3-1. Slack API

| 項目 | 値 |
|------|----|
| 使用API | Slack Web API |
| エンドポイント | `conversations.history`, `conversations.info`, `users.info`（表示名解決用） |
| トークン種別 | Bot Token（`xoxb-`） |
| **現在のスコープ** | `chat:write`（のみ） |
| **追加必要スコープ** | `channels:history`, `groups:history`（プライベートチャンネルの場合）, `channels:read`, `users:read` |

> **スコープ追加手順**（概要のみ）  
> Slack API管理画面 → OAuth & Permissions → Bot Token Scopes に上記を追加 → Reinstall to Workspace

### 3-2. Anthropic (Claude) API

| 項目 | 値 |
|------|----|
| 使用API | Anthropic Messages API |
| 使用モデル | `claude-haiku-4-5-20251001`（コスト優先）または `claude-sonnet-4-6`（品質優先） |
| トークン種別 | APIキー（`sk-ant-`） |
| **取得状況** | **未取得（新規取得が必要）** |

### 3-3. LINE Messaging API

| 項目 | 値 |
|------|----|
| 使用API | LINE Messaging API – Push Message |
| エンドポイント | `https://api.line.me/v2/bot/message/push` |
| トークン種別 | チャネルアクセストークン |
| **取得状況** | 取得済み |
| 送信先ID | ユーザーID（`Uxxxxxxxxx`）または グループID |

---

## 4. データフロー図

```
┌─────────────────────────────────────────────────────────┐
│                     crontab (Mac)                       │
│          毎日 XX:00 に main.py を実行                     │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  1. Slack取得                                            │
│     conversations.history → メッセージリスト取得          │
│     （直近24時間 or 当日0:00以降）                        │
└───────────────────────┬─────────────────────────────────┘
                        │ messages[]
                        ▼
┌─────────────────────────────────────────────────────────┐
│  2. 前処理                                               │
│     - ボットメッセージ・システムメッセージを除外            │
│     - user_id → 表示名に変換                             │
│     - テキストを整形（改行・空白正規化）                   │
└───────────────────────┬─────────────────────────────────┘
                        │ 整形済みテキスト
                        ▼
┌─────────────────────────────────────────────────────────┐
│  3. Claude要約                                           │
│     プロンプトに整形テキストを渡す                         │
│     → 箇条書き日本語要約を取得                            │
└───────────────────────┬─────────────────────────────────┘
                        │ 要約テキスト
                        ▼
┌─────────────────────────────────────────────────────────┐
│  4. LINE通知                                             │
│     Push Message API → 指定ユーザーに送信                 │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
                   [完了 / ログ出力]
```

---

## 5. ディレクトリ構成

```
1. Slack の情報を取得・要約して LINE に送るツール/
├── main.py               # エントリーポイント・全体オーケストレーション
├── slack_client.py       # Slack API呼び出し・メッセージ整形
├── summarizer.py         # Claude APIによる要約生成
├── line_notifier.py      # LINE Push Message送信
├── config.py             # 設定値の読み込み（.envから）
├── .env                  # 環境変数（gitignore対象）
├── .env.example          # .envのサンプル（git管理）
├── requirements.txt      # Pythonパッケージ一覧
├── requirements.md       # 本ファイル
└── .gitignore
```

---

## 6. .env の項目

```dotenv
# Slack
SLACK_BOT_TOKEN=xoxb-xxxxxxxxxxxx-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx
SLACK_CHANNEL_ID=Cxxxxxxxxxx          # 対象チャンネルのチャンネルID

# Anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxx

# LINE
LINE_CHANNEL_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxx
LINE_USER_ID=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # 送信先ユーザーID

# 動作設定（任意・デフォルト値あり）
FETCH_HOURS=24                         # 何時間前までのメッセージを取得するか（デフォルト: 24）
CLAUDE_MODEL=claude-haiku-4-5-20251001 # 使用するClaudeモデル
```

---

## 7. エラーハンドリング方針

| ケース | 対応 |
|--------|------|
| Slack API認証エラー（401） | スクリプトを即時終了・エラーログ出力 |
| Slackスコープ不足（403） | エラーメッセージにスコープ追加方法を明示して終了 |
| メッセージ0件 | LINEに「本日の対象メッセージはありませんでした」と通知してもよいし、何もしない（設定で切替）|
| Claude APIエラー | エラーログを出力してスクリプト終了（LINEには送らない） |
| LINE送信エラー | エラーログを出力（リトライは任意機能） |
| ネットワーク系エラー | 標準出力にトレースバックを出力して終了（cronがメールで通知） |
| トークン未設定 | 起動時に必須環境変数の存在をチェック・欠落があればわかりやすいエラーを出力 |

**基本方針：** MVPではtry/exceptで各API呼び出しを囲み、失敗時はエラー内容を標準エラー出力（stderr）に出力してスクリプトを`sys.exit(1)`で終了する。cronのメールアラートで検知できるようにする。

---

## 8. 実行頻度と方法（cron）

### crontab 設定例（Mac）

```bash
# 毎日午前8時に実行
0 8 * * * /path/to/venv/bin/python /path/to/main.py >> /path/to/logs/cron.log 2>&1
```

### セットアップ手順（概要）

```bash
# 仮想環境作成・有効化
python3 -m venv venv
source venv/bin/activate

# 依存パッケージインストール
pip install -r requirements.txt

# crontabに追加
crontab -e
```

> **Mac固有の注意点**  
> macOSではスリープ中はcronが実行されない。常時起動が前提。  
> LaunchAgents（`~/Library/LaunchAgents/`）を使う方法もある（スリープ復帰後の遅延実行が可能）。

---

## 9. MVPの最小スコープ

以下のみを実装した動作する最小構成を目指す。

| スコープ | 内容 |
|---------|------|
| チャンネル数 | **1チャンネルのみ**（`.env`で固定） |
| 取得範囲 | 直近24時間のメッセージ（スレッド返信は除く） |
| 要約形式 | 箇条書き5点以内、日本語 |
| 送信先 | **個人LINEアカウントのみ** |
| 実行方法 | `python main.py` を手動またはcronで呼び出す |
| エラー対応 | 各API呼び出しをtry/exceptで囲み、失敗時はstderrに出力してexit(1) |
| ログ | 標準出力のみ（ファイルへの書き込みは任意） |

**MVP対象外（後回し）：** 複数チャンネル、スレッド取得、リトライ処理、ログファイル管理、テストコード

---

## 10. 使用Pythonパッケージ（予定）

```
slack-sdk          # Slack Web API クライアント
anthropic          # Anthropic Claude API クライアント
line-bot-sdk       # LINE Messaging API クライアント
python-dotenv      # .envファイルの読み込み
```
