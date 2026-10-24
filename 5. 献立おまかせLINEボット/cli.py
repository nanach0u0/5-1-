"""LINE なしで提案を試すための CLI。

使い方:
  python cli.py ヘトヘト            # 気分は「なんでも」
  python cli.py ヘトヘト がっつり
  python cli.py 疲れたけど肉食べたい  # 自由文を Claude が読み替える
"""

import logging
import sys
from datetime import date

import config
from claude_client import interpret, select_menu
from notion_repo import fetch_recipes
from recommender import ALLOWED_EFFORTS, MOOD_ANY, MOODS, Proposal, suggest


def format_proposal(p: Proposal) -> str:
    lines = []
    for role, r in (("メイン", p.main), ("副菜  ", p.side)):
        if r:
            label = "🆕 " if r.is_untried else ""
            lines.append(f"  {role}: {label}{r.name}（手間: {r.effort}）")
            if r.url:
                lines.append(f"          {r.url}")
    lines.append("  （ごはんと一緒に）" if p.with_rice else "  （一品完結なのでごはんなし）")
    lines.append(f"  → {p.reason}" if p.reason else "  （ランダムに選びました）")
    return "\n".join(lines)


def parse_args(args: list[str]) -> tuple[str, str]:
    if len(args) == 1 and args[0] not in ALLOWED_EFFORTS:
        try:
            condition, mood = interpret(args[0])
        except Exception as e:
            print(f"自由文を読み替えられなかったので「ふつう／なんでも」にします（{e}）")
            return "ふつう", MOOD_ANY
        print(f"読み替え: コンディション={condition}、気分={mood}")
        return condition, mood
    if 1 <= len(args) <= 2 and args[0] in ALLOWED_EFFORTS:
        mood = args[1] if len(args) == 2 else MOOD_ANY
        if mood in MOODS:
            return args[0], mood
    print(f"使い方: python cli.py [{' | '.join(ALLOWED_EFFORTS)}] [{' | '.join(MOODS)}]")
    print("    または python cli.py 自由文")
    sys.exit(1)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if not config.NOTION_TOKEN:
        print(".env に NOTION_TOKEN を設定してください")
        sys.exit(1)
    condition, mood = parse_args(sys.argv[1:])

    recipes = fetch_recipes(config.NOTION_TOKEN, config.NOTION_RECIPE_DS_ID)
    print(f"レシピを {len(recipes)} 件読み込みました\n")

    proposals = suggest(recipes, condition, mood, date.today(), select=select_menu)
    if not proposals:
        print("条件に合うレシピがありませんでした")
        return
    for p in proposals:
        print("【作ってみたい】" if p.challenge else "【一軍】")
        print(format_proposal(p))
        print()


if __name__ == "__main__":
    main()
