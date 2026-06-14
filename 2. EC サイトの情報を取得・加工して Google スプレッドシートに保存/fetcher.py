import time
import requests

# 2026年2月のインフラ刷新後の新エンドポイント
RAKUTEN_API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"

# 新仕様では Origin / Referer ヘッダーが必須。楽天ドメインを指定する。
REQUEST_HEADERS = {
    "Origin": "https://www.rakuten.co.jp",
    "Referer": "https://www.rakuten.co.jp/",
    "User-Agent": "rakuten-sheets-tool/1.0",
}


def fetch_items(
    application_id: str,
    access_key: str,
    keyword: str,
    hits: int = 10,
) -> list[dict]:
    # 新仕様では applicationId と accessKey の両方が必須
    params = {
        "applicationId": application_id,
        "accessKey": access_key,
        "keyword": keyword,
        "hits": hits,
        "page": 1,
        "format": "json",
    }
    try:
        response = requests.get(
            RAKUTEN_API_URL,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"[fetcher] API通信エラー: {e}")
        return []

    time.sleep(1)

    items = data.get("Items", [])
    if not items:
        print("[fetcher] 検索結果が0件でした。")
        return []

    result = []
    for entry in items:
        item = entry.get("Item", entry)
        result.append({
            "itemName": item.get("itemName", ""),
            "itemPrice": item.get("itemPrice", 0),
            "shopName": item.get("shopName", ""),
            "availability": item.get("availability", 0),
            "reviewCount": item.get("reviewCount", 0),
            "itemUrl": item.get("itemUrl", ""),
        })
    return result
