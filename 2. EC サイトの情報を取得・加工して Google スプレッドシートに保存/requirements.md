# 要件定義書 — 楽天市場商品データ → Google スプレッドシート保存ツール

---

## 1. 目的

楽天市場商品検索 API で取得した商品情報を整形し、Google スプレッドシートに自動追記する Python スクリプトを構築する。
定期実行（cron）により、最新の商品情報を継続的に蓄積する。

---

## 2. MVP（最小スコープ）

| 項目 | 内容 |
|---|---|
| 検索キーワード | 1 件のみ（例：`コーヒー豆`） |
| 取得件数 | 10 件 |
| 書き込み先 | スプレッドシート 1 枚目（末尾追記） |
| 重複チェック | なし |
| 出力カラム順 | 商品名 / 価格 / 店舗名 / 在庫 / レビュー件数 / 商品URL / 取得日時 |

---

## 3. 機能要件

### 3-1. 必須機能

| # | 機能 | 詳細 |
|---|---|---|
| F-01 | 楽天 API 呼び出し | キーワードを指定して `IchibaItem/Search/20220601` を叩き、商品リストを取得する |
| F-02 | データ抽出・整形 | レスポンス JSON から 6 フィールドを抜き出し、取得日時（JST）を付与する |
| F-03 | スプレッドシート追記 | Google Sheets API でシート末尾に行を追加する |
| F-04 | レート制限遵守 | 複数ページ取得時は 1 秒以上のウェイトを挟む |
| F-05 | エラーハンドリング | API 通信失敗・検索結果 0 件・シート書き込み失敗の 3 パターンを処理する |
| F-06 | ログ出力 | 実行日時・取得件数・エラー詳細を `logs/app.log` に記録する |

### 3-2. 任意機能（MVP 後に検討）

| # | 機能 |
|---|---|
| F-10 | 複数キーワードの一括検索（`keywords.txt` から読み込み） |
| F-11 | 重複商品 URL のスキップ |
| F-12 | 取得件数の設定ファイル化（`.env` or `config.yaml`） |
| F-13 | Slack / LINE への実行結果通知 |
| F-14 | シート自動作成（存在しない場合） |

---

## 4. 使用 API と認証情報

### 4-1. 楽天ウェブサービス — IchibaItem/Search

| 項目 | 内容 |
|---|---|
| エンドポイント | `https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601` |
| 認証方式 | クエリパラメータ `applicationId` |
| 取得フィールド | `itemName`, `itemPrice`, `shopName`, `availability`, `reviewCount`, `itemUrl` |
| レスポンス形式 | JSON |
| 取得件数上限 | 1 リクエスト最大 30 件（`hits` パラメータ） |
| 必要なキー | `applicationId`（楽天デベロッパーポータルで発行） |

主要クエリパラメータ：

| パラメータ | 値 | 説明 |
|---|---|---|
| `applicationId` | `.env` から読み込み | アプリ ID |
| `keyword` | 任意の文字列 | 検索キーワード（URL エンコード） |
| `hits` | `10` | 1 ページ当たりの取得件数 |
| `page` | `1` | ページ番号（MVP では固定） |
| `format` | `json` | レスポンス形式 |

`availability` の値：`1` = 在庫あり、`0` = 取り扱いなし

### 4-2. Google Sheets API v4

| 項目 | 内容 |
|---|---|
| 認証方式 | サービスアカウント（`credentials.json`） |
| スコープ | `https://www.googleapis.com/auth/spreadsheets` |
| 操作 | `spreadsheets.values.append` |
| 必要なキー | `credentials.json`（Google Cloud Console で発行） |
| 必要な設定 | スプレッドシート ID を `.env` に記載し、サービスアカウントを対象シートに「編集者」として共有 |

---

## 5. 楽天 API 利用規約・レート制限の遵守方針

- **1 秒に 1 リクエスト以下** に抑える（`time.sleep(1)` を各リクエスト後に挿入）
- 楽天ウェブサービス利用規約（[https://webservice.rakuten.co.jp/terms/](https://webservice.rakuten.co.jp/terms/)）に従い、取得データを自社サービスの商業利用に転用しない
- レスポンスヘッダー `X-Ratelimit-Remaining` が返る場合は値を確認し、残量 0 のときは追加のスリープを入れる
- User-Agent に独自の識別子を含める（`rakuten-sheets-tool/1.0`）

---

## 6. データフロー図

```
┌─────────────────────────────────────────────────────────┐
│  cron / 手動実行                                         │
│  python main.py --keyword "コーヒー豆"                    │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  config.py                                               │
│  ・.env から applicationId / SPREADSHEET_ID を読み込み    │
│  ・credentials.json を読み込み（サービスアカウント認証）    │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  rakuten_client.py                                       │
│  ・IchibaItem/Search API を呼び出す                       │
│  ・JSON レスポンスをパースして商品リスト（list[dict]）を返す│
│  ・リクエスト後に 1 秒スリープ                            │
└──────────────────────────┬──────────────────────────────┘
                           │ 商品リスト（0〜N件）
                           ▼
┌─────────────────────────────────────────────────────────┐
│  data_transformer.py（main.py 内でも可）                  │
│  ・dict → 行リスト [商品名, 価格, 店舗名,                  │
│           在庫, レビュー件数, URL, 取得日時(JST)] に変換   │
└──────────────────────────┬──────────────────────────────┘
                           │ 行リスト（list[list]）
                           ▼
┌─────────────────────────────────────────────────────────┐
│  sheets_client.py                                        │
│  ・Google Sheets API で末尾に行を追記                     │
│  ・書き込み成功件数をログに記録                            │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  logs/app.log                                            │
│  ・実行日時 / キーワード / 取得件数 / エラー詳細を記録      │
└─────────────────────────────────────────────────────────┘
```

---

## 7. ディレクトリ構成

```
2. EC サイトの情報を取得・加工して Google スプレッドシートに保存/
├── requirements.md          # 本ファイル
├── main.py                  # エントリーポイント（引数解析・フロー制御）
├── rakuten_client.py        # 楽天 API クライアント
├── sheets_client.py         # Google Sheets API クライアント
├── config.py                # .env / credentials.json の読み込み
├── .env                     # 環境変数（Git 管理外）
├── credentials.json         # GCP サービスアカウントキー（Git 管理外）
├── requirements.txt         # pip 依存パッケージ
└── logs/
    └── app.log              # 実行ログ（Git 管理外）
```

> `credentials.json` と `logs/` は親リポジトリの `.gitignore` に追記が必要。

---

## 8. .env の項目

```dotenv
# 楽天ウェブサービス
RAKUTEN_APPLICATION_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx

# Google Sheets
SPREADSHEET_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 検索設定（オプション：コマンドライン引数でも上書き可）
SEARCH_KEYWORD=コーヒー豆
SEARCH_HITS=10
```

| キー | 説明 | 取得元 |
|---|---|---|
| `RAKUTEN_APPLICATION_ID` | 楽天 API のアプリ ID | 楽天デベロッパーポータル |
| `SPREADSHEET_ID` | Google スプレッドシートの ID（URL の `/d/` 以降） | Google Drive |
| `SEARCH_KEYWORD` | 検索キーワード | ユーザー設定 |
| `SEARCH_HITS` | 1 回の取得件数（最大 30） | ユーザー設定 |

---

## 9. エラーハンドリング方針

### 9-1. API 通信失敗（楽天 API）

| 状況 | 対処 |
|---|---|
| タイムアウト / 接続エラー | `requests.exceptions.RequestException` をキャッチし、最大 3 回リトライ（1 回目 +2 秒、2 回目 +4 秒のバックオフ） |
| HTTP 4xx（認証エラー等） | リトライせず即時終了。`applicationId` が無効である旨をログに出力 |
| HTTP 5xx（楽天側障害） | 3 回リトライ後も失敗した場合はログにエラーを記録してスクリプト終了（`sys.exit(1)`） |

### 9-2. 検索結果 0 件

| 状況 | 対処 |
|---|---|
| `hits == 0` または `Items` が空 | シート書き込みをスキップ。ログに「キーワード『xxx』の検索結果が 0 件でした」を WARNING レベルで記録し、スクリプトを正常終了（`sys.exit(0)`） |

### 9-3. シート書き込み失敗（Google Sheets API）

| 状況 | 対処 |
|---|---|
| 認証エラー（`credentials.json` 不正・権限不足） | ログに「サービスアカウントにシートの編集権限がありません」を出力し、即時終了 |
| API クォータ超過 | 60 秒待機後に 1 回リトライ。それでも失敗した場合はログに記録して終了 |
| その他 API エラー | `googleapiclient.errors.HttpError` をキャッチしてログに出力し、終了 |

---

## 10. 実行頻度と方法

### 手動実行

```bash
# 仮想環境を有効化
source .venv/bin/activate

# デフォルト（.env のキーワードで実行）
python main.py

# キーワードを上書き指定
python main.py --keyword "紅茶" --hits 20
```

### cron 設定例（macOS）

```cron
# 毎日 8:00 JST に実行
0 8 * * * cd "/Users/username/AIプログラミング課題用/5-1 自分のためのツール/2. EC サイトの情報を取得・加工して Google スプレッドシートに保存" && /path/to/.venv/bin/python main.py >> logs/cron.log 2>&1
```

> macOS では `crontab -e` で設定。Python の絶対パスは `which python` で確認。

---

## 11. 依存パッケージ（requirements.txt）

```
requests>=2.31.0
python-dotenv>=1.0.0
google-api-python-client>=2.100.0
google-auth>=2.23.0
google-auth-httplib2>=0.1.1
```

---

## 12. 実装ステップ（優先順）

1. `config.py` — `.env` と `credentials.json` の読み込み確認
2. `rakuten_client.py` — API 呼び出しとレスポンスパース
3. `sheets_client.py` — 行追記の動作確認
4. `main.py` — フロー統合・エラーハンドリング・ログ出力
5. cron 設定・動作確認

---

*作成日: 2026-06-12*
