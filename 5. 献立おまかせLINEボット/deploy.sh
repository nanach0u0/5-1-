#!/bin/bash
# Webhook サーバーを Cloud Run にデプロイする（requirements.md 6章）。
# 使い方: ./deploy.sh   （.env の値を Cloud Run の環境変数として渡す）
set -euo pipefail
cd "$(dirname "$0")"

# 献立ボット専用のプロジェクト（ほかの課題の My First Project などとは分けている）
PROJECT=kondate-bot-6d4df6
SERVICE=kondate-bot
# Notion・Claude の API は米国にあるので、無料枠が確実な us-central1 に置く
REGION=us-central1

# .env から必要な値だけを一時ファイルに書き出す（終わったら消す）
ENV_FILE=$(mktemp)
trap 'rm -f "$ENV_FILE"' EXIT
python - "$ENV_FILE" <<'PY'
import json
import sys

from dotenv import dotenv_values

KEYS = [
    "NOTION_TOKEN",
    "NOTION_RECIPE_DS_ID",
    "NOTION_LOG_DS_ID",
    "ANTHROPIC_API_KEY",
    "LINE_CHANNEL_SECRET",
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_USER_ID",
]
values = dotenv_values(".env")
missing = [k for k in KEYS if not values.get(k)]
if missing:
    sys.exit(f".env に値がありません: {', '.join(missing)}")
with open(sys.argv[1], "w") as f:
    for k in KEYS:
        f.write(f"{k}: {json.dumps(values[k])}\n")
PY

# 費用を抑える設定:
#   --min-instances 0   使っていない間は止める
#   --max-instances 1   大量にアクセスされても1台まで
#   --no-cpu-throttling LINE に2秒以内に返事をしてから Claude・Notion の処理を続けるため
#                       （返事のあとも CPU を使える「インスタンスベース課金」。止まるまで最長15分は課金される）
gcloud run deploy "$SERVICE" \
  --project "$PROJECT" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --no-cpu-throttling \
  --cpu 1 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 1 \
  --env-vars-file "$ENV_FILE"
