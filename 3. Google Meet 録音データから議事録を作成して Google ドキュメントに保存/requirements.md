# 要件定義書：Google Meet 議事録作成ツール

## 概要

Notion AI のミーティング文字起こしテキスト（`transcript.txt`）を読み込み、Claude API で議事録に整形し、既存の Google ドキュメントへ末尾追記するツール。

---

## 1. 機能要件

### 必須（MVP）

| # | 機能 | 詳細 |
|---|------|------|
| F-01 | 文字起こし読み込み | `transcript.txt` をローカルから読み込む |
| F-02 | 議事録要約 | Claude API を呼び出し、定形フォーマットで議事録を生成する |
| F-03 | Google ドキュメント追記 | 指定した既存 Google ドキュメントの末尾に議事録を書き込む |

### 議事録フォーマット（F-02 の出力）

```
【議事録】

■ 日時
（文字起こし内から推定、不明な場合は「不明」と記載）

■ 参加者
（発言者名を抽出、不明な場合は「不明」と記載）

■ 議題
（会議のメインテーマ）

■ 決定事項
・（箇条書き）

■ ToDo
・担当者：内容（期限があれば記載）

---
```

### 任意（将来拡張）

| # | 機能 | 備考 |
|---|------|------|
| F-10 | 複数ファイルの一括処理 | `transcripts/` ディレクトリ内を順次処理 |
| F-11 | 議事録ファイルのローカル保存 | `.txt` または `.md` で出力 |
| F-12 | メール通知 | 書き込み完了後に Gmail 通知 |

---

## 2. 使用 API と必要な認証情報

### Claude API

| 項目 | 内容 |
|------|------|
| SDK | `anthropic`（Python 公式） |
| モデル | `claude-haiku-4-5-20251001`（コスト優先）または `claude-sonnet-4-6`（品質優先） |
| 用途 | 文字起こしテキストを議事録フォーマットに変換 |
| 認証 | `ANTHROPIC_API_KEY`（`.env` から読み込み） |

### Google Docs API

| 項目 | 内容 |
|------|------|
| API バージョン | Google Docs API v1 |
| ライブラリ | `google-api-python-client`, `google-auth` |
| 用途 | 既存 Google ドキュメントへの末尾追記 |
| 認証方式 | サービスアカウント（`credentials.json`） |
| スコープ | `https://www.googleapis.com/auth/documents` |

#### Google 側の事前設定

1. Google Cloud Console でプロジェクトを作成
2. Google Docs API を有効化
3. サービスアカウントを作成し、`credentials.json` をダウンロード
4. 議事録を保存したい Google ドキュメントを開き、サービスアカウントのメールアドレスを **編集者** として共有設定する

---

## 3. データフロー

```
[ユーザー]
    │
    │  transcript.txt をフォルダに配置
    ▼
[main.py] ─────────────────────────────────────────────┐
    │                                                   │
    │ 1. ファイル読み込み                                 │
    ▼                                                   │
[transcript_reader.py]                                  │
  └─ transcript.txt を読み込み、文字列として返す           │
    │                                                   │
    │ 2. 議事録要約リクエスト                              │
    ▼                                                   │
[summarizer.py]                                         │
  └─ Claude API へ送信                                   │
       │                                                │
       ▼                                                │
  [Claude API]                                          │
       │                                                │
       ▼                                                │
  └─ 整形済み議事録テキストを返す                          │
    │                                                   │
    │ 3. Google ドキュメントへ書き込み                     │
    ▼                                                   │
[docs_client.py]                                        │
  └─ Google Docs API で末尾追記                          │
       │                                                │
       ▼                                                │
  [Google ドキュメント]                                   │
    │                                                   │
    └───────────────────────────────── 完了メッセージ ──┘
                                           │
                                     [ターミナル出力]
```

---

## 4. ディレクトリ構成

```
3. Google Meet 録音データから議事録を作成して Google ドキュメントに保存/
├── main.py               # エントリーポイント。全体フローを制御
├── transcript_reader.py  # transcript.txt の読み込み
├── summarizer.py         # Claude API 呼び出し・議事録生成
├── docs_client.py        # Google Docs API 操作
├── requirements.txt      # 依存パッケージ一覧
├── requirements.md       # 本ファイル
├── .env                  # API キー等（Git 管理外）
├── credentials.json      # GCP サービスアカウントキー（Git 管理外）
└── transcript.txt        # 文字起こしテキスト（都度差し替え）
```

> `.env` と `credentials.json` は親リポジトリの `.gitignore` で除外済み。

---

## 5. .env の項目

```dotenv
# Claude API
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx

# Google Docs
GOOGLE_DOC_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 設定（省略時はデフォルト値を使用）
TRANSCRIPT_PATH=transcript.txt
CLAUDE_MODEL=claude-haiku-4-5-20251001
```

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `ANTHROPIC_API_KEY` | 必須 | Anthropic コンソールで発行 |
| `GOOGLE_DOC_ID` | 必須 | Google ドキュメントの URL 末尾の ID 文字列 |
| `TRANSCRIPT_PATH` | 任意 | デフォルト `transcript.txt` |
| `CLAUDE_MODEL` | 任意 | デフォルト `claude-haiku-4-5-20251001` |

> **GOOGLE_DOC_ID の確認方法：** Google ドキュメントの URL `https://docs.google.com/document/d/【ここ】/edit` の部分

---

## 6. エラーハンドリング方針

| ケース | 検出タイミング | 対応 |
|--------|--------------|------|
| **テキストが空** | `transcript_reader.py` 読み込み後 | エラーメッセージを表示してプロセスを終了（`sys.exit(1)`）。空ファイル・ファイル未存在の両方をカバー |
| **要約失敗** | `summarizer.py` の Claude API 呼び出し後 | `anthropic.APIError` をキャッチしてエラー内容を表示。リトライは行わず終了（`sys.exit(1)`） |
| **書き込み失敗** | `docs_client.py` の Docs API 呼び出し後 | `googleapiclient.errors.HttpError` をキャッチしてステータスコードとメッセージを表示して終了（`sys.exit(1)`）。典型的な原因（権限不足・Doc ID 誤り）をメッセージに含める |

### エラーメッセージ例

```
[ERROR] transcript.txt が見つからないか空です。ファイルを配置してから再実行してください。
[ERROR] Claude API エラー: 401 Unauthorized - ANTHROPIC_API_KEY を確認してください。
[ERROR] Google Docs API エラー: 403 Forbidden - サービスアカウントにドキュメントの編集権限があるか確認してください。
```

---

## 7. 実行方法

### 初回セットアップ

```bash
# 1. 作業フォルダへ移動
cd "3. Google Meet 録音データから議事録を作成して Google ドキュメントに保存"

# 2. 仮想環境を作成・有効化
python -m venv .venv
source .venv/bin/activate

# 3. 依存パッケージをインストール
pip install -r requirements.txt

# 4. .env を作成（.env.example をコピーして編集）
cp .env.example .env
# → ANTHROPIC_API_KEY と GOOGLE_DOC_ID を記入

# 5. credentials.json を配置
# GCP コンソールでダウンロードしたファイルをフォルダ直下に置く
```

### 議事録作成（毎回の実行）

```bash
# 1. 仮想環境を有効化（未有効化の場合）
source .venv/bin/activate

# 2. 文字起こしファイルを配置
# transcript.txt をフォルダ直下に置く

# 3. 実行
python main.py

# 期待される出力例：
# [INFO] transcript.txt を読み込みました（3,200 文字）
# [INFO] Claude API で議事録を生成中...
# [INFO] 議事録を Google ドキュメントに書き込み中...
# [SUCCESS] 完了しました。ドキュメントを確認してください。
```

---

## 8. 依存パッケージ（requirements.txt）

```
anthropic
google-api-python-client
google-auth
python-dotenv
```
