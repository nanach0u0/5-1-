"""Notion のレシピ_DB を読み込む。

パッケージ名 notion_client（公式SDK）と衝突しないよう、ファイル名を notion_repo にしている。
"""

from datetime import date
from typing import Optional

import requests

from recipe import EFFORT_NORMAL, MAIN, SIDE, Recipe

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _select_name(prop: dict) -> Optional[str]:
    select = prop.get("select") if prop else None
    return select["name"] if select else None


def parse_recipe(page: dict) -> Optional[Recipe]:
    """Notion のページ1件を Recipe に変換する。メインでも副菜でもないページは None。"""
    props = page["properties"]

    tags = [t["name"] for t in props.get("タグ", {}).get("multi_select", [])]
    if MAIN in tags:
        role = MAIN
    elif SIDE in tags:
        role = SIDE
    else:
        return None

    title = props.get("名前", {}).get("title", [])
    name = "".join(t["plain_text"] for t in title).strip()
    if not name:
        return None

    date_prop = props.get("最後に作った日", {}).get("date")
    last_made = date.fromisoformat(date_prop["start"][:10]) if date_prop else None

    return Recipe(
        id=page["id"],
        name=name,
        role=role,
        rating=_select_name(props.get("評価")),
        # 手間が未入力のレシピは「ふつう」として扱う
        effort=_select_name(props.get("手間")) or EFFORT_NORMAL,
        one_dish=props.get("一品完結", {}).get("checkbox", False),
        last_made=last_made,
        url=props.get("URL", {}).get("url"),
    )


def fetch_recipes(token: str, data_source_id: str) -> list[Recipe]:
    """レシピ_DB の全ページを取得する（100件ごとのページ送りに対応）。"""
    recipes = []
    payload: dict = {"page_size": 100}
    while True:
        response = requests.post(
            f"{NOTION_API}/data_sources/{data_source_id}/query",
            headers=_headers(token),
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        for page in body["results"]:
            recipe = parse_recipe(page)
            if recipe:
                recipes.append(recipe)
        if not body.get("has_more"):
            return recipes
        payload["start_cursor"] = body["next_cursor"]
