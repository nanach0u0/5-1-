from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))


def process_items(items: list[dict]) -> list[list]:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    rows = []
    for item in items:
        rows.append([
            item.get("itemName", ""),
            int(item.get("itemPrice", 0)),
            item.get("shopName", ""),
            item.get("availability", 0),
            int(item.get("reviewCount", 0)),
            item.get("itemUrl", ""),
            now,
        ])
    return rows
