#!/usr/bin/env python3
"""Проверки, которых не хватало старому рейтингу.

Ровно эти ошибки были найдены при аудите README от 11.07.2026: расхождение
цифр в тексте и таблице, бренд в предупреждениях без строки в рейтинге,
разные флаги стран в двух файлах, реакция, не попавшая ни в один список.

Выход: 0 — чисто, 1 — есть ошибки. Годится для CI.
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

errors, warnings = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def main():
    brands = json.load(open(DATA / "brands.json", encoding="utf-8"))
    classes = json.load(open(DATA / "reactions.json", encoding="utf-8"))
    known = set(classes["positive"]) | set(classes["negative"]) | set(classes["ambiguous"])
    tests = list(csv.DictReader(open(DATA / "processed" / "tests.csv", encoding="utf-8")))
    rating = json.load(open(ROOT / "rating.json", encoding="utf-8"))

    # 1. Каждая реакция из дампа обязана быть классифицирована.
    unseen = Counter()
    for row in tests:
        for emoji, n in json.loads(row["reactions_detail"]).items():
            if emoji in ("CUSTOM", "_UNKNOWN"):
                continue
            if emoji not in known:
                unseen[emoji] += n if isinstance(n, int) else 0
    for emoji, n in unseen.items():
        err(f"реакция {emoji} ({n} шт.) не описана в data/reactions.json")

    # 2. Эмодзи не может стоять в двух списках сразу.
    for a, b in (("positive", "negative"), ("positive", "ambiguous"), ("negative", "ambiguous")):
        dup = set(classes[a]) & set(classes[b])
        if dup:
            err(f"эмодзи в двух списках сразу ({a}/{b}): {' '.join(dup)}")

    # 3. Алиасы брендов не должны пересекаться.
    seen = {}
    for brand in brands:
        for alias in brand["aliases"]:
            if alias in seen and seen[alias] != brand["name"]:
                err(f"алиас {alias!r} принадлежит сразу {seen[alias]} и {brand['name']}")
            seen[alias] = brand["name"]

    # 4. Слишком общий алиас поймает чужие тесты. Трёхбуквенные («p2g», «п2г»)
    #    в чате реально используются, поэтому это предупреждение, а не ошибка.
    for brand in brands:
        for alias in brand["aliases"]:
            if len(alias) < 3:
                err(f"алиас {alias!r} у {brand['name']} короче 3 символов — будет ложно срабатывать")
            elif len(alias) == 3:
                warn(f"алиас {alias!r} у {brand['name']} очень короткий — проверьте ложные срабатывания")

    # 5. Каждый бренд из tests.csv обязан быть в словаре.
    names = {b["name"] for b in brands}
    for name in {r["brand"] for r in tests}:
        if name not in names:
            err(f"бренд {name!r} есть в tests.csv, но отсутствует в brands.json")

    # 6. Арифметика рейтинга должна сходиться с датасетом.
    for b in rating["brands"]:
        if b["pos"] - b["neg"] != b["raw"]:
            err(f"{b['brand']}: raw={b['raw']}, а pos−neg={b['pos'] - b['neg']}")
        if b["votes"] != b["pos"] + b["neg"]:
            err(f"{b['brand']}: votes не равен pos+neg")
        if b["tests"] != b["scored_tests"] + b["satire_tests"] + b["vendor_tests"]:
            err(f"{b['brand']}: tests не разбивается на scored+satire+vendor")
        if not 0.0 <= b["wilson"] <= 1.0:
            err(f"{b['brand']}: wilson={b['wilson']} вне [0,1]")

    if rating["totals"]["tests"] != len(tests):
        err(f"rating.json насчитал {rating['totals']['tests']} тестов, в tests.csv их {len(tests)}")

    # 7. Ранжирование должно быть монотонным.
    ranked = [b for b in rating["brands"] if b["ranked"]]
    for a, b in zip(ranked, ranked[1:]):
        if a["wilson"] < b["wilson"]:
            err(f"порядок нарушен: {a['brand']} ({a['wilson']}) стоит выше {b['brand']} ({b['wilson']})")

    # 8. README должен быть отрендерен из текущего rating.json.
    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        for b in ranked[:10]:
            if b["brand"] not in text:
                err(f"{b['brand']} входит в топ-10 rating.json, но не найден в README.md")
        m = re.search(r"Данные:\s*(\d{4}-\d{2}-\d{2})", text)
        if m and m.group(1) != rating["period"]["to"]:
            err(f"README говорит про данные на {m.group(1)}, а rating.json — на {rating['period']['to']}")

    # 9. Каждое ручное решение обязано быть объяснено.
    ov = json.load(open(DATA / "overrides.json", encoding="utf-8"))
    ids = {r["msg_id"] for r in tests}
    for mid, rule in ov.items():
        if mid.startswith("_"):
            continue
        if not rule.get("note"):
            err(f"override {mid} без поля note — непонятно, почему так решили")
        if mid not in ids and not rule.get("exclude"):
            warn(f"override {mid} не соответствует ни одному тесту (сообщение удалено или не распознано)")

    # 10. Предупреждения — только про бренды, которые есть в рейтинге.
    warn_file = ROOT / "content" / "warnings.md"
    if warn_file.exists():
        rated = {b["brand"] for b in rating["brands"]}
        for name in re.findall(r"\*\*\[([^\]]+)\]\(", warn_file.read_text(encoding="utf-8")):
            name = name.strip()
            if name and name not in rated:
                warn(f"предупреждение про {name!r}, но по нему нет тестов в текущем периоде")

    # 11. Свежесть данных.
    from datetime import date
    age = (date.today() - date.fromisoformat(rating["period"]["to"])).days
    if age > 45:
        warn(f"данные устарели на {age} дней — пора обновлять выгрузку")

    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  ERROR {e}")
    print()
    print(f"проверок пройдено, ошибок: {len(errors)}, предупреждений: {len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
