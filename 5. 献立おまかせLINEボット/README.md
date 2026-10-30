# 献立おまかせLINEボット

LINE で「何食べよう」と送ると、Notion に貯めた自分のレシピの中から、その日のコンディションと気分に合う献立を1セット（余裕がある日は2択）だけ提案するボットです。献立を考えること自体の疲れ（選択疲れ）を減らすために作りました。

設計の考え方と詳しい仕様は [requirements.md](requirements.md)（要件定義書）を参照してください。

## できること

```
自分：何食べよう
Bot ：今日のコンディションは？   [ヘトヘト] [ふつう] [余裕あり]
自分：[ヘトヘト]
Bot ：気分は？                   [がっつり] [さっぱり] [なんでも]
自分：[がっつり]
Bot ：今日はこれどう？
      🍖 しょうが焼き
         https://cookpad.com/jp/recipes/18978075
      🥗 千切りキャベツ（カット野菜）
      （ごはんと一緒に）
      → しょうが焼きに千切りキャベツで、ラクにがっつり満足できます
      [これにする] [別のがいい]
```

- **提案は Notion のレシピからだけ**: AI に新しいレシピは考えさせません。候補の絞り込み（手間・評価・かぶり防止）は Python のルールで行い、最後の組み合わせ選びと理由の1文だけを Claude に任せます。
- **選択肢は最大2つ**: ふだんは1セット。「余裕あり」の日だけ、まだ作ったことのないレシピを含む【A】と、一軍だけの【B】の2択にします。[別のがいい]で引き直せるのは2回までです。
- **自由文にも対応**: 「疲れたけど肉食べたい」と送ると、Claude がコンディションと気分に読み替えて、ボタンを省いて提案します。
- **「作った？」の確認**: [これにする]から90分以上たったら「作った？」と聞きます（GitHub Actions の都合で、数時間後になることもあります）。[作った]を押すと、Notion の「最後に作った日」を更新します。初めて作ったレシピなら「どうだった？」と評価を聞き、Notion に書き込みます。
- **本人専用**: LINE の署名を検証し、自分の userId 以外からのメッセージは無視します。

## 仕組み

```
LINE アプリ
   │ メッセージ・ボタン操作（Webhook）
   ▼
Cloud Run（main.py / FastAPI）
   ├─ Notion API … レシピの読み込み、献立ログの記録、最後に作った日・評価の更新
   ├─ Claude API … 献立の最終選択と理由文、自由文の読み替え
   └─ LINE Messaging API … 返信

GitHub Actions（30分おきの設定。実際は数時間おきになることがある）
   └─ followup.py … 決めてから90分たった献立に「作った？」を送る
```

- 会話の状態はサーバーに持たず、ボタンの postback データに入れています。サーバーが止まっても会話は途切れません。
- LINE は Webhook の返事を2秒しか待たないため、すぐに 200 を返し、Notion・Claude の処理はその後で行います。

## 必要なもの

- Python 3.10 以上
- Notion のインテグレーション（コネクション）のトークン。権限は「読み取り・更新・挿入」。レシピ_DB と献立ログ_DB のあるページに接続しておく
- Anthropic API キー
- LINE の Messaging API チャネル（チャネルシークレット、チャネルアクセストークン（長期）、自分のユーザーID）
- 公開する場合: Google Cloud のプロジェクト（請求先アカウントの紐づけが必要）と、GitHub リポジトリ

Notion のデータベースに必要な列は、[requirements.md](requirements.md) の5章を参照してください。

## セットアップ

```bash
# 仮想環境の作成と依存パッケージのインストール
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 環境変数の設定（下の「環境変数」を参照）
cp .env.example .env
```

### LINE なしで試す（CLI）

Notion と Claude だけを使って、提案を確かめられます。

```bash
python cli.py ヘトヘト              # 気分は「なんでも」
python cli.py ヘトヘト がっつり
python cli.py 疲れたけど肉食べたい   # 自由文を Claude が読み替える
```

### （任意）コードを直しながら LINE で試す（ngrok）

公開して使うだけなら不要です。コードを直すたびにデプロイし直さずに、手元のサーバーを LINE で試したいときに使います。

```bash
uvicorn main:app --port 8000
ngrok http 8000      # 別のターミナルで
```

表示された `https://〜.ngrok-free.dev` に `/callback` を付けて、LINE Developers の「Webhook URL」に登録します。Mac がスリープすると止まるので、開発中の確認用です。

## 公開する（Cloud Run と GitHub Actions）

### Webhook サーバー（Cloud Run）

[deploy.sh](deploy.sh) の `PROJECT` を自分の Google Cloud プロジェクトに書き換えてから実行します。`.env` の値を Cloud Run の環境変数として渡します。

```bash
./deploy.sh
```

- 使っていないときは0台、最大1台、1 vCPU・512MiB で動かします。
- 返事のあとも Notion・Claude の処理を続けるため、`--no-cpu-throttling`（インスタンスベース課金）にしています。
- 新しく作ったプロジェクトでは、最初のビルドが権限不足で失敗することがあります。その場合は、既定のサービスアカウントに Cloud Build のビルダーの役割を付けます。

```bash
gcloud projects add-iam-policy-binding <プロジェクトID> --member="serviceAccount:<プロジェクト番号>-compute@developer.gserviceaccount.com" --role="roles/cloudbuild.builds.builder" --condition=None
```

デプロイ後に表示される `Service URL` に `/callback` を付けて、LINE の Webhook URL に登録します。

### 「作った？」の送信（GitHub Actions）

[.github/workflows/kondate-followup.yml](../.github/workflows/kondate-followup.yml) が30分おきに `followup.py` を実行する設定です。GitHub は混雑しているときに定期実行を間引くため、30分おきの設定でも、実際には数時間おきにしか動かないことがあります（10月26日〜30日の4日間では、2.8〜6.9時間おきに19回）。「作った？」が届くのは、決めてから90分〜数時間後です。

リポジトリの Settings → Secrets and variables → Actions に、次の3つを登録してください。

- `NOTION_TOKEN`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_USER_ID`

公開リポジトリの定期実行は、60日間コミットがないと GitHub に止められます。止まったら Actions の画面で再開してください。

## 環境変数

| キー | 説明 |
|------|------|
| `NOTION_TOKEN` | Notion のインテグレーションのトークン（`ntn_` で始まる） |
| `NOTION_RECIPE_DS_ID` | レシピ_DB のデータソースID（未設定なら config.py の既定値） |
| `NOTION_LOG_DS_ID` | 献立ログ_DB のデータソースID（未設定なら config.py の既定値） |
| `ANTHROPIC_API_KEY` | Anthropic API キー |
| `LINE_CHANNEL_SECRET` | LINE のチャネルシークレット（署名の検証に使う） |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE のチャネルアクセストークン（長期） |
| `LINE_USER_ID` | 自分の LINE ユーザーID（`U` で始まる）。これ以外からのメッセージは無視する |

## テスト

```bash
python -m pytest -q
```

テストは架空のレシピと偽物のクライアントだけを使い、Notion・Claude・LINE は呼びません。

## ディレクトリ構成

```
.
├── main.py            # LINE Webhook の受け口と会話の処理（FastAPI）
├── followup.py        # 「作った？」の送信（GitHub Actions から実行）
├── cli.py             # LINE なしで提案を試す CLI
├── recommender.py     # 候補の絞り込み（ルール）と、選択結果のルール確認
├── claude_client.py   # Claude による献立の最終選択と自由文の読み替え
├── notion_repo.py     # Notion のレシピ_DB・献立ログ_DB の読み書き
├── line_messages.py   # LINE のメッセージ・ボタンの組み立て、URL の短縮
├── line_api.py        # LINE の署名検証、返信・送信
├── recipe.py          # レシピのデータ型
├── config.py          # 環境変数の読み込み
├── tests/             # 単体テスト
├── Dockerfile         # Cloud Run 用
├── deploy.sh          # Cloud Run へのデプロイ
├── .env.example       # 環境変数のテンプレート
├── requirements.txt   # 依存パッケージ
└── requirements.md    # 要件定義書
```

## 費用

- Claude API は従量課金です。提案するたび（[別のがいい]を含む）に1回、自由文のときは読み替えでもう1回呼び出します。
- Cloud Run は、1日1〜2回使う程度なら無料枠に収まる見込みです。念のため、Google Cloud の予算アラートを少額で設定しておくと安心です。
- LINE の返信は無料です。「作った？」の送信（push）は、無料プランの月間上限（200通）に数えられます。

## 使用API

| サービス | API |
|---------|-----|
| Notion | [Data sources – Query](https://developers.notion.com/reference/query-a-data-source)、Pages（作成・更新） |
| Anthropic | [Messages API](https://docs.anthropic.com/en/api/messages)（Structured Outputs） |
| LINE | [Messaging API](https://developers.line.biz/ja/reference/messaging-api/)（reply / push / ローディング表示） |
