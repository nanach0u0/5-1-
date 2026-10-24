"""notion_repo.parse_recipe のテスト。Notion API のレスポンス形式のページを変換する。"""

from datetime import date

from notion_repo import parse_recipe


def page(name="しょうが焼き", tags=("メイン",), rating="おいしい", effort="ラク",
         one_dish=False, last_made=None, url="https://example.com"):
    return {
        "id": "page-1",
        "properties": {
            "名前": {"type": "title", "title": [{"plain_text": name}]},
            "タグ": {"type": "multi_select", "multi_select": [{"name": t} for t in tags]},
            "評価": {"type": "select", "select": {"name": rating} if rating else None},
            "手間": {"type": "select", "select": {"name": effort} if effort else None},
            "一品完結": {"type": "checkbox", "checkbox": one_dish},
            "最後に作った日": {"type": "date", "date": {"start": last_made} if last_made else None},
            "URL": {"type": "url", "url": url},
        },
    }


def test_parse_basic():
    r = parse_recipe(page(last_made="2026-10-20"))
    assert r.id == "page-1"
    assert r.name == "しょうが焼き"
    assert r.role == "メイン"
    assert r.rating == "おいしい"
    assert r.effort == "ラク"
    assert r.one_dish is False
    assert r.last_made == date(2026, 10, 20)
    assert r.url == "https://example.com"


def test_parse_side_and_one_dish():
    r = parse_recipe(page(tags=("副菜",), one_dish=True))
    assert r.role == "副菜"
    assert r.one_dish is True


def test_missing_effort_defaults_to_normal():
    assert parse_recipe(page(effort=None)).effort == "ふつう"


def test_missing_rating_is_untried():
    r = parse_recipe(page(rating=None))
    assert r.rating is None
    assert r.is_untried


def test_no_tag_is_skipped():
    assert parse_recipe(page(tags=())) is None


def test_datetime_last_made():
    assert parse_recipe(page(last_made="2026-10-20T19:30:00.000+09:00")).last_made == date(2026, 10, 20)
