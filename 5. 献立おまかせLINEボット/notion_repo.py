"""Notion のレシピ_DB の読み書きと、献立ログ_DB の記録（requirements.md 5章）。

パッケージ名 notion_client（公式SDK）と衝突しないよう、ファイル名を notion_repo にしている。
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import requests

from recipe import EFFORT_NORMAL, MAIN, SIDE, Recipe

STATUS_PENDING = "確認待ち"
STATUS_MADE = "作った"
STATUS_NOT_MADE = "作ってない"

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


def _request(method: str, token: str, path: str, body: Optional[dict] = None) -> dict:
    response = requests.request(
        method, f"{NOTION_API}{path}", headers=_headers(token), json=body, timeout=30
    )
    response.raise_for_status()
    return response.json()


def fetch_recipe(token: str, page_id: str) -> Optional[Recipe]:
    return parse_recipe(_request("GET", token, f"/pages/{page_id}"))


def set_last_made(token: str, recipe_id: str, day: date) -> None:
    _request(
        "PATCH",
        token,
        f"/pages/{recipe_id}",
        {"properties": {"最後に作った日": {"date": {"start": day.isoformat()}}}},
    )


def set_rating(token: str, recipe_id: str, rating: str) -> None:
    _request(
        "PATCH", token, f"/pages/{recipe_id}", {"properties": {"評価": {"select": {"name": rating}}}}
    )


@dataclass(frozen=True)
class Log:
    id: str
    title: str  # 例: 「2026-10-22 しょうが焼き＋漬け新玉ねぎ」
    recipe_ids: list[str]
    status: Optional[str]

    @property
    def menu(self) -> str:
        """タイトルから日付を除いた献立名。"""
        return self.title.split(" ", 1)[-1]


def parse_log(page: dict) -> Log:
    props = page["properties"]
    title = "".join(t["plain_text"] for t in props["タイトル"]["title"])
    status = props["ステータス"]["select"]
    return Log(
        id=page["id"],
        title=title,
        recipe_ids=[r["id"] for r in props["レシピ"]["relation"]],
        status=status["name"] if status else None,
    )


def create_log(token: str, data_source_id: str, recipes: list[Recipe], decided_at: datetime) -> str:
    """[これにする]で決めた献立を「確認待ち」で記録し、ページIDを返す。"""
    title = f"{decided_at.date().isoformat()} " + "＋".join(r.name for r in recipes)
    page = _request(
        "POST",
        token,
        "/pages",
        {
            "parent": {"type": "data_source_id", "data_source_id": data_source_id},
            "properties": {
                "タイトル": {"title": [{"text": {"content": title}}]},
                "レシピ": {"relation": [{"id": r.id} for r in recipes]},
                "決定日時": {"date": {"start": decided_at.isoformat()}},
                "ステータス": {"select": {"name": STATUS_PENDING}},
                "確認送信済み": {"checkbox": False},
            },
        },
    )
    return page["id"]


def fetch_log(token: str, log_id: str) -> Log:
    return parse_log(_request("GET", token, f"/pages/{log_id}"))


def update_log(
    token: str, log_id: str, status: Optional[str] = None, sent: Optional[bool] = None
) -> None:
    props: dict = {}
    if status is not None:
        props["ステータス"] = {"select": {"name": status}}
    if sent is not None:
        props["確認送信済み"] = {"checkbox": sent}
    _request("PATCH", token, f"/pages/{log_id}", {"properties": props})


def find_logs_to_confirm(token: str, data_source_id: str, decided_before: datetime) -> list[Log]:
    """「作った？」をまだ送っていない、decided_before より前に決めた「確認待ち」のログ。"""
    body = {
        "filter": {
            "and": [
                {"property": "ステータス", "select": {"equals": STATUS_PENDING}},
                {"property": "確認送信済み", "checkbox": {"equals": False}},
                {"property": "決定日時", "date": {"on_or_before": decided_before.isoformat()}},
            ]
        },
        "page_size": 100,
    }
    data = _request("POST", token, f"/data_sources/{data_source_id}/query", body)
    return [parse_log(page) for page in data["results"]]
