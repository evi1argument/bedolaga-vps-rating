#!/usr/bin/env python3
"""data/processed/tests.csv -> rating.json

Что здесь принципиально иначе, чем в старой методике:

1. Реакции на РАЗГРОМНЫЙ обзор — это согласие с разгромом, а не похвала хостингу.
   Поэтому при verdict=negative весь отклик уходит в минус. Раньше ❤×11 на
   «из 50 гбит даст бог 5» поднимали Qwins с −14 до −4.
2. Сатира не оценивается вообще. Считается отдельной колонкой.
3. Посты представителей хостинга в score не идут.
4. Ранжирование — по нижней границе Уилсона, а не по сумме.
   Сумма поощряет количество тестов, а не качество хостинга.
5. «Реакций нет» — это отдельный статус, а не ноль.

Запуск:  python scripts/score.py
"""
import csv
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

Z = 1.96          # 95%
RECENT_DAYS = 90
MIN_VOTES_RANKED = 5   # меньше — в «мало данных», не в основную таблицу


def wilson_lower(pos, neg, z=Z):
    """Нижняя граница доли положительных при 95% доверии (Wilson, 1927)."""
    n = pos + neg
    if n == 0:
        return 0.0
    p = pos / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def tier(votes):
    if votes >= 25:
        return "●●●"
    if votes >= 10:
        return "●●○"
    if votes >= 1:
        return "●○○"
    return "—"


def contribution(row):
    """-> (pos_signal, neg_signal, kind) для одного теста.

    Переворот знака под разгромным обзором — сильная операция: она способна
    превратить 🔥×22 в минус. Поэтому она срабатывает ТОЛЬКО по подтверждённой
    вручную разметке (overrides.json). Негативный вердикт от эвристики
    считается обычным образом и попадает в review.csv на проверку.
    """
    pos, neg = int(row["pos"]), int(row["neg"])
    if row["verdict"] == "satire" and row["verdict_source"] == "override":
        return 0, 0, "satire"
    if int(row["vendor_post"]):
        return 0, 0, "vendor"
    if row["verdict"] == "negative" and row["verdict_source"] == "override":
        # Любой отклик под разгромом = подтверждение разгрома.
        return 0, pos + neg, "scored"
    return pos, neg, "scored"


def main():
    brands = {b["name"]: b for b in json.load(open(DATA / "brands.json", encoding="utf-8"))}
    rows = list(csv.DictReader(open(DATA / "processed" / "tests.csv", encoding="utf-8")))

    latest = max(r["date"] for r in rows)
    cutoff = (date.fromisoformat(latest) - timedelta(days=RECENT_DAYS)).isoformat()

    agg = defaultdict(lambda: {
        "tests": 0, "scored_tests": 0, "satire_tests": 0, "vendor_tests": 0,
        "pos": 0, "neg": 0, "ambiguous": 0, "custom": 0,
        "r_pos": 0, "r_neg": 0, "recent_tests": 0,
        "vendor_pos": 0, "vendor_neg": 0,
        "referral_tests": 0, "silent_tests": 0,
        "flags": defaultdict(int), "authors": set(),
        "first": "9999", "last": "0000",
    })

    for r in rows:
        a = agg[r["brand"]]
        p, n, kind = contribution(r)
        a["tests"] += 1
        a["ambiguous"] += int(r["ambiguous"])
        a["custom"] += int(r["custom"])
        a["referral_tests"] += int(r["has_referral"])
        a["authors"].add(r["author_id"])
        a["first"] = min(a["first"], r["date"])
        a["last"] = max(a["last"], r["date"])
        for f in [r["flags"][i:i + 2] for i in range(0, len(r["flags"]), 2)]:
            a["flags"][f] += 1

        if kind == "satire":
            a["satire_tests"] += 1
            continue
        if kind == "vendor":
            a["vendor_tests"] += 1
            a["vendor_pos"] += int(r["pos"])
            a["vendor_neg"] += int(r["neg"])
            continue

        a["scored_tests"] += 1
        a["pos"] += p
        a["neg"] += n
        if p + n == 0:
            a["silent_tests"] += 1
        if r["date"] >= cutoff:
            a["recent_tests"] += 1
            a["r_pos"] += p
            a["r_neg"] += n

    out = []
    for name, a in agg.items():
        votes = a["pos"] + a["neg"]
        meta = brands.get(name, {})
        flags = "".join(f for f, _ in sorted(a["flags"].items(), key=lambda kv: -kv[1])[:5])
        out.append({
            "brand": name,
            "url": meta.get("url"),
            "flags": flags or meta.get("flags", ""),
            "wilson": round(wilson_lower(a["pos"], a["neg"]), 4),
            "raw": a["pos"] - a["neg"],
            "pos": a["pos"],
            "neg": a["neg"],
            "votes": votes,
            "share": round(a["pos"] / votes, 4) if votes else None,
            "tests": a["tests"],
            "scored_tests": a["scored_tests"],
            "silent_tests": a["silent_tests"],
            "satire_tests": a["satire_tests"],
            "vendor_tests": a["vendor_tests"],
            "vendor_pos": a["vendor_pos"],
            "vendor_neg": a["vendor_neg"],
            "ambiguous": a["ambiguous"],
            "custom": a["custom"],
            "referral_tests": a["referral_tests"],
            "authors": len(a["authors"]),
            "recent_tests": a["recent_tests"],
            "recent_wilson": round(wilson_lower(a["r_pos"], a["r_neg"]), 4),
            "recent_raw": a["r_pos"] - a["r_neg"],
            "recent_votes": a["r_pos"] + a["r_neg"],
            "tier": tier(votes),
            "ranked": votes >= MIN_VOTES_RANKED,
            "first_test": a["first"],
            "last_test": a["last"],
            "legacy": meta.get("legacy"),
        })

    # Очередь на ручную проверку: места, где автоматика могла ошибиться и где
    # ошибка дорого стоит. Разметить их — задача мейнтейнера, а не скрипта.
    review = []
    for r in rows:
        votes = int(r["pos"]) + int(r["neg"])
        reason = None
        if r["verdict"] == "negative" and r["verdict_source"] == "heuristic":
            reason = "негативный вердикт от эвристики — подтвердить, чтобы включить переворот знака"
        elif int(r["vendor_post"]) and r["verdict_source"] != "override":
            reason = "пост опознан как вендорский автоматически — подтвердить"
        elif r["verdict"] == "unknown" and votes >= 8:
            reason = "много реакций, вердикт автора не распознан"
        if reason:
            review.append({"msg_id": r["msg_id"], "date": r["date"], "brand": r["brand"],
                           "pos": r["pos"], "neg": r["neg"], "reason": reason})
    review.sort(key=lambda r: -(int(r["pos"]) + int(r["neg"])))
    with open(DATA / "processed" / "review.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["msg_id", "date", "brand", "pos", "neg", "reason"])
        w.writeheader()
        w.writerows(review)

    out.sort(key=lambda b: (-b["wilson"], -b["votes"], b["brand"]))

    ranked = [b for b in out if b["ranked"]]
    thin = [b for b in out if not b["ranked"]]

    rating = {
        "generated_from": "data/processed/tests.csv",
        "period": {"from": min(r["date"] for r in rows), "to": latest},
        "recent_window_days": RECENT_DAYS,
        "method": {
            "rank_key": "wilson_lower_bound_95",
            "min_votes_ranked": MIN_VOTES_RANKED,
            "negative_review_rule": "отклик под разгромным обзором считается согласием с разгромом",
            "satire": "исключается из score",
            "vendor_posts": "исключаются из score",
        },
        "totals": {
            "tests": len(rows),
            "brands": len(out),
            "ranked_brands": len(ranked),
            "thin_brands": len(thin),
            "pos": sum(b["pos"] for b in out),
            "neg": sum(b["neg"] for b in out),
            "ambiguous": sum(b["ambiguous"] for b in out),
            "custom": sum(b["custom"] for b in out),
            "satire_tests": sum(b["satire_tests"] for b in out),
            "vendor_tests": sum(b["vendor_tests"] for b in out),
            "referral_tests": sum(b["referral_tests"] for b in out),
        },
        "brands": out,
    }
    with open(ROOT / "rating.json", "w", encoding="utf-8") as fh:
        json.dump(rating, fh, ensure_ascii=False, indent=1)

    t = rating["totals"]
    print(f"период            : {rating['period']['from']} .. {rating['period']['to']}")
    print(f"тестов            : {t['tests']}")
    print(f"брендов           : {t['brands']}  (в рейтинге {t['ranked_brands']}, мало данных {t['thin_brands']})")
    print(f"сатира / вендор   : {t['satire_tests']} / {t['vendor_tests']} тестов вне score")
    print(f"реакции +/-       : {t['pos']} / {t['neg']}")
    print(f"неоднозначных     : {t['ambiguous']}   кастом: {t['custom']}")
    print()
    print(f"{'#':>3} {'бренд':<18}{'Wilson':>8}{'доля':>7}{'голосов':>9}{'тестов':>8}  уровень")
    print("-" * 62)
    for i, b in enumerate(ranked[:20], 1):
        sh = f"{b['share']:.0%}" if b["share"] is not None else "—"
        print(f"{i:>3} {b['brand']:<18}{b['wilson']:>8.3f}{sh:>7}{b['votes']:>9}{b['tests']:>8}  {b['tier']}")


if __name__ == "__main__":
    main()
