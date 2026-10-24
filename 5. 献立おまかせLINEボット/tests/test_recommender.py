"""recommender.py のテスト。Notion・Claude には依存しない。"""

import random
from datetime import date, timedelta

from recipe import MAIN, SIDE, Recipe
from recommender import (
    CONDITION_NORMAL,
    CONDITION_RELAXED,
    CONDITION_TIRED,
    build_pools,
    recommend,
)

TODAY = date(2026, 10, 24)


def make(id, role=MAIN, rating="おいしい", effort="ラク", one_dish=False, last_made=None):
    return Recipe(
        id=id,
        name=id,
        role=role,
        rating=rating,
        effort=effort,
        one_dish=one_dish,
        last_made=last_made,
        url=None,
    )


def ids(recipes):
    return {r.id for r in recipes}


def run_many(recipes, condition, n=200, **kwargs):
    """ランダムに選ぶので、何度も回して全結果を集める。"""
    rng = random.Random(0)
    return [
        recommend(recipes, condition, TODAY, choose=lambda xs: rng.choice(xs), **kwargs)
        for _ in range(n)
    ]


# --- 絞り込み ---------------------------------------------------------------


def test_tired_only_easy():
    recipes = [make("easy"), make("normal", effort="ふつう"), make("hard", effort="がんばる")]
    pools = build_pools(recipes, CONDITION_TIRED, TODAY)
    assert ids(pools.first_mains) == {"easy"}


def test_normal_allows_easy_and_normal():
    recipes = [make("easy"), make("normal", effort="ふつう"), make("hard", effort="がんばる")]
    pools = build_pools(recipes, CONDITION_NORMAL, TODAY)
    assert ids(pools.first_mains) == {"easy", "normal"}


def test_relaxed_allows_all_efforts():
    recipes = [make("easy"), make("normal", effort="ふつう"), make("hard", effort="がんばる")]
    pools = build_pools(recipes, CONDITION_RELAXED, TODAY)
    assert ids(pools.first_mains) == {"easy", "normal", "hard"}


def test_futsuu_and_zannen_never_included():
    recipes = [make("good"), make("futsuu", rating="ふつう"), make("zannen", rating="残念")]
    for condition in (CONDITION_TIRED, CONDITION_NORMAL, CONDITION_RELAXED):
        pools = build_pools(recipes, condition, TODAY)
        all_ids = ids(pools.first_mains + pools.untried_mains)
        assert all_ids == {"good"}


def test_untried_only_on_relaxed():
    recipes = [make("good"), make("new", rating=None), make("notyet", rating="まだ作ってない")]
    assert build_pools(recipes, CONDITION_TIRED, TODAY).untried_mains == []
    assert build_pools(recipes, CONDITION_NORMAL, TODAY).untried_mains == []
    assert ids(build_pools(recipes, CONDITION_RELAXED, TODAY).untried_mains) == {"new", "notyet"}


def test_recent_three_days_excluded():
    recipes = [
        make("today", last_made=TODAY),
        make("2days", last_made=TODAY - timedelta(days=2)),
        make("3days", last_made=TODAY - timedelta(days=3)),
        make("never"),
    ]
    pools = build_pools(recipes, CONDITION_TIRED, TODAY)
    assert ids(pools.first_mains) == {"3days", "never"}


def test_exclude_ids():
    recipes = [make("a"), make("b")]
    pools = build_pools(recipes, CONDITION_TIRED, TODAY, exclude_ids=frozenset({"a"}))
    assert ids(pools.first_mains) == {"b"}


# --- 提案の組み立て ---------------------------------------------------------


def test_regular_proposal_main_side_and_rice():
    recipes = [make("main"), make("side", role=SIDE)]
    [p] = recommend(recipes, CONDITION_TIRED, TODAY)
    assert p.main.id == "main"
    assert p.side.id == "side"
    assert p.with_rice
    assert not p.challenge


def test_one_dish_has_no_rice_and_only_easy_side():
    recipes = [
        make("pasta", one_dish=True),
        make("easy_side", role=SIDE),
        make("normal_side", role=SIDE, effort="ふつう"),
    ]
    for proposals in run_many(recipes, CONDITION_NORMAL):
        [p] = proposals
        assert not p.with_rice
        assert p.side.id == "easy_side"


def test_falls_back_when_everything_recent():
    recipes = [make("main", last_made=TODAY), make("side", role=SIDE, last_made=TODAY)]
    [p] = recommend(recipes, CONDITION_TIRED, TODAY)
    assert p.main.id == "main"


def test_no_candidates_returns_empty():
    recipes = [make("hard", effort="がんばる")]
    assert recommend(recipes, CONDITION_TIRED, TODAY) == []


def test_relaxed_returns_challenge_and_regular():
    recipes = [
        make("good_main"),
        make("good_main2"),
        make("good_side", role=SIDE),
        make("good_side2", role=SIDE),
        make("new_main", rating=None),
        make("new_side", role=SIDE, rating="まだ作ってない"),
    ]
    for proposals in run_many(recipes, CONDITION_RELAXED):
        challenge, regular = proposals
        assert challenge.challenge and not regular.challenge
        # 作ってみたいセットには、作ったことないレシピがちょうど1品
        assert sum(r.is_untried for r in challenge.recipes) == 1
        # 一軍セットは一軍だけ
        assert all(r.rating == "おいしい" for r in regular.recipes)
        # 2つのセットで同じレシピを使わない
        assert not ids(challenge.recipes) & ids(regular.recipes)


def test_relaxed_without_untried_returns_one():
    recipes = [make("good_main"), make("good_side", role=SIDE)]
    [p] = recommend(recipes, CONDITION_RELAXED, TODAY)
    assert not p.challenge


def test_untried_normal_effort_side_not_paired_with_one_dish():
    recipes = [
        make("pasta", one_dish=True),
        make("new_side", role=SIDE, rating=None, effort="ふつう"),
        make("good_side", role=SIDE),
    ]
    # 一品完結のメインしかないので、「ふつう」の作ったことない副菜とは組めない
    for proposals in run_many(recipes, CONDITION_RELAXED):
        assert all(not p.challenge for p in proposals)
