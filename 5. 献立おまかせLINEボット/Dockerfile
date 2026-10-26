# Cloud Run 用。デプロイ: gcloud run deploy --source .（README 参照）
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./

# Cloud Run が渡す PORT で待ち受ける
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
