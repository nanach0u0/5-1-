"""suggest（Claude での最終選択とフォールバック）と claude_client のテスト。

Claude は呼ばず、selector や API クライアントを偽物に差し替える。
"""

import json
from types import SimpleNamespace

import pytest

from claude_client import interpret, select_menu
from recipe import SIDE
from recommender import (
    CONDITION_RELAXED,
    CONDITION_TIRED,
    Proposal,
    candidate_pools,
    is_valid,
    suggest,
)
from tests.test_recommender import TODAY, make

MAIN = make("main")
PASTA = make("pasta", one_dish=True)
SIDE_EASY = make("side", role=SIDE)
SIDE_NORMAL = make("side_normal", role=SIDE, effort="ふつう")
NEW_MAIN = make("new_main", rating=None)
RECIPES = [MAIN, PASTA, SIDE_EASY, SIDE_NORMAL, NEW_MAIN]


def pools(condition=CONDITION_RELAXED):
    return candidate_pools(RECIPES, condition, TODAY)


# --- is_valid ---------------------------------------------------------------


def test_valid_regular():
    assert is_valid(pools(CONDITION_TIRED), CONDITION_TIRED, [Proposal(MAIN, SIDE_EASY)])


def test_one_dish_with_normal_side_is_invalid():
    assert not is_valid(pools(), CONDITION_RELAXED, [Proposal(PASTA, SIDE_NORMAL)])


def test_missing_side_is_invalid_when_side_available():
    assert not is_valid(pools(), CONDITION_RELAXED, [Proposal(MAIN, None)])


def test_untried_in_regular_is_invalid():
    assert not is_valid(pools(), CONDITION_RELAXED, [Proposal(NEW_MAIN, SIDE_EASY)])


def test_challenge_and_regular_must_not_share_recipes():
    ok = [Proposal(NEW_MAIN, SIDE_EASY, challenge=True), Proposal(MAIN, SIDE_NORMAL)]
    shared = [Proposal(NEW_MAIN, SIDE_EASY, challenge=True), Proposal(MAIN, SIDE_EASY)]
    assert is_valid(pools(), CONDITION_RELAXED, ok)
    assert not is_valid(pools(), CONDITION_RELAXED, shared)


def test_challenge_not_allowed_when_tired():
    proposals = [Proposal(NEW_MAIN, SIDE_EASY, challenge=True), Proposal(MAIN, SIDE_NORMAL)]
    assert not is_valid(pools(CONDITION_TIRED), CONDITION_TIRED, proposals)


# --- suggest のフォールバック ----------------------------------------------


def test_uses_selector_result_when_valid():
    chosen = [Proposal(MAIN, SIDE_EASY, reason="理由")]
    result = suggest(RECIPES, CONDITION_TIRED, "がっつり", TODAY, select=lambda *a: chosen)
    assert result == chosen


@pytest.mark.parametrize(
    "select",
    [
        lambda *a: [Proposal(PASTA, SIDE_NORMAL, reason="ルール違反")],
        lambda *a: (_ for _ in ()).throw(RuntimeError("API エラー")),
    ],
)
def test_falls_back_to_random(select):
    [p] = suggest(RECIPES, CONDITION_TIRED, "がっつり", TODAY, select=select)
    assert p.reason is None
    assert is_valid(pools(CONDITION_TIRED), CONDITION_TIRED, [p])


# --- claude_client（API クライアントは偽物） --------------------------------


class FakeClient:
    def __init__(self, reply: dict, stop_reason="end_turn"):
        self.calls = []
        text = SimpleNamespace(type="text", text=json.dumps(reply))
        response = SimpleNamespace(stop_reason=stop_reason, content=[text])

        def create(**kwargs):
            self.calls.append(kwargs)
            return response

        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))

    @property
    def schema(self):
        return self.calls[0]["output_config"]["format"]["schema"]


def test_select_menu_regular_only_when_tired():
    client = FakeClient({"regular": {"main_id": "main", "side_id": "side", "reason": " ごはんが進みます "}})
    [p] = select_menu(pools(CONDITION_TIRED), CONDITION_TIRED, "がっつり", client=client)
    assert (p.main, p.side, p.reason, p.challenge) == (MAIN, SIDE_EASY, "ごはんが進みます", False)
    # ヘトヘトなので「ふつう」の副菜も作ったことないメインも選択肢に入らない
    regular = client.schema["properties"]["regular"]["properties"]
    assert set(regular["main_id"]["enum"]) == {"main", "pasta"}
    assert regular["side_id"]["anyOf"][0]["enum"] == ["side"]
    assert "challenge" not in client.schema["properties"]


def test_select_menu_challenge_when_relaxed():
    client = FakeClient(
        {
            "challenge": {"main_id": "new_main", "side_id": "side", "reason": "A"},
            "regular": {"main_id": "main", "side_id": "side_normal", "reason": "B"},
        }
    )
    challenge, regular = select_menu(pools(), CONDITION_RELAXED, "なんでも", client=client)
    assert challenge.challenge and challenge.main == NEW_MAIN
    assert not regular.challenge and regular.side == SIDE_NORMAL
    assert client.schema["required"] == ["regular", "challenge"]


def test_select_menu_raises_on_refusal():
    client = FakeClient({}, stop_reason="refusal")
    with pytest.raises(RuntimeError):
        select_menu(pools(CONDITION_TIRED), CONDITION_TIRED, "がっつり", client=client)


def test_interpret():
    client = FakeClient({"condition": "ヘトヘト", "mood": "がっつり", "about_meal": True})
    assert interpret("疲れたけど肉食べたい", client=client) == ("ヘトヘト", "がっつり")


def test_interpret_not_about_meal():
    client = FakeClient({"condition": "ふつう", "mood": "なんでも", "about_meal": False})
    assert interpret("ありがとう", client=client) is None
