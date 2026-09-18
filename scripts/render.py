#!/usr/bin/env python3
"""rating.json + content/*.md -> README.md

README больше не хранит данные, а собирается из них. Руками правится только
content/*.md; всё, что с цифрами, считает score.py.

Запуск:  python scripts/render.py
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Границы по нижней границе Уилсона. Подобраны по фактическому распределению,
# а не «на глаз»: разрывы в данных приходятся примерно сюда.
TIERS = [
    (0.55, "🟢 Хорошо", "Одобрение уверенно держится выше половины даже по нижней границе."),
    (0.30, "🔵 Рабочие", "Больше плюсов, чем минусов, но запас невелик."),
    (0.15, "🟡 Спорные", "Мнения расходятся или выборка не даёт уверенности."),
    (0.00, "🔴 Избегать", "Негатив преобладает устойчиво."),
]


def bar(w):
    filled = round(w * 10)
    return "█" * filled + "░" * (10 - filled)


def brand_cell(b):
    name = f"**{b['brand']}**"
    if b["url"]:
        name = f"**[{b['brand']}]({b['url']})**"
    marks = ""
    if b["vendor_tests"]:
        marks += " 🏷"
    if b["satire_tests"]:
        marks += " 🎭"
    return name + marks


def trend(b):
    if b["recent_votes"] < 5:
        return "—"
    delta = b["recent_wilson"] - b["wilson"]
    if delta > 0.08:
        return "📈"
    if delta < -0.08:
        return "📉"
    return "="


def table(brands, start=1):
    head = (
        "| # | Хостинг | Оценка | Реакции | Голосов | Тестов | Тренд | Страны | Реф |\n"
        "|:---:|---|---|:---:|:---:|:---:|:---:|:---:|:---:|\n"
    )
    out = []
    for i, b in enumerate(brands, start):
        ref = f"{b['referral_tests']}/{b['tests']}"
        reactions = f"+{b['pos']} / −{b['neg']}"
        out.append(
            f"| {i} | {brand_cell(b)} | `{bar(b['wilson'])}` {b['wilson']:.0%} | {reactions} | "
            f"{b['votes']} {b['tier']} | {b['tests']} | {trend(b)} | {b['flags'] or '—'} | {ref} |"
        )
    return head + "\n".join(out)


def main():
    r = json.load(open(ROOT / "rating.json", encoding="utf-8"))
    t = r["totals"]
    period_to = r["period"]["to"]
    age = (date.today() - date.fromisoformat(period_to)).days
    freshness = "🟢 актуально" if age <= 30 else ("🟡 стареет" if age <= 60 else "🔴 устарело")

    ranked = [b for b in r["brands"] if b["ranked"]]
    thin = [b for b in r["brands"] if not b["ranked"]]

    p = []
    p.append('<div align="center">\n')
    p.append("# 🖥️ VPS Rating — Telegram «Тесты VPS»\n")
    p.append("Рейтинг VPS-хостингов по реакциям участников чата. Считается скриптом из сырой выгрузки — цифры можно перепроверить.\n")
    p.append(
        f"![Хостингов](https://img.shields.io/badge/хостингов-{t['brands']}-blue?style=flat-square) "
        f"![Тестов](https://img.shields.io/badge/тестов-{t['tests']}-green?style=flat-square) "
        f"![Данные](https://img.shields.io/badge/данные-{period_to}-orange?style=flat-square) "
        f"![Свежесть](https://img.shields.io/badge/{freshness.split()[1]}-{age}_дней-lightgrey?style=flat-square)\n"
    )
    p.append("</div>\n")
    p.append("---\n")

    # Гид идёт первым: он отвечает на вопрос, с которым сюда приходят.
    p.append((ROOT / "content" / "guide.md").read_text(encoding="utf-8").strip() + "\n")
    p.append("---\n")
    p.append((ROOT / "content" / "warnings.md").read_text(encoding="utf-8").strip() + "\n")
    p.append("---\n")

    p.append("## 📊 Рейтинг\n")
    p.append(
        "**Оценка** — доля одобрения по нижней границе 95% интервала Уилсона: «сколько плюсов "
        "у бренда в худшем правдоподобном случае». Она сознательно занижена там, где голосов "
        "мало, — один тест с тремя лайками не обгонит девять тестов с полусотней. Рядом стоят "
        "сырые реакции, чтобы вы видели, из чего она посчитана.\n"
    )
    p.append(
        "| Значок | Что значит |\n|:---:|---|\n"
        "| ●●● / ●●○ / ●○○ | Сколько голосов за брендом: 25+, 10–24, 1–9 |\n"
        "| 🏷 | Есть посты от представителя хостинга — в Score не идут |\n"
        "| 🎭 | Есть сатирические обзоры — в Score не идут |\n"
        "| 📈 📉 | Последние 90 дней заметно лучше или хуже общей картины |\n"
        "| Реф | Сколько тестов бренда содержат реферальную ссылку |\n"
    )

    rank = 1
    for i, (floor, title, note) in enumerate(TIERS):
        ceil = TIERS[i - 1][0] if i else 1.01
        group = [b for b in ranked if floor <= b["wilson"] < ceil]
        if not group:
            continue
        p.append(f"### {title}\n")
        p.append(f"*{note}*\n")
        p.append(table(group, rank) + "\n")
        rank += len(group)

    if thin:
        p.append("### ⚪ Мало данных\n")
        p.append(
            f"{len(thin)} брендов набрали меньше 5 голосов. Это не оценка — по ним просто "
            "нечего считать, и ставить их рядом с остальными было бы враньём.\n"
        )
        p.append("<details><summary>Показать список</summary>\n")
        rows = ["| Хостинг | Тестов | Голосов | Страны |", "|---|:---:|:---:|:---:|"]
        for b in sorted(thin, key=lambda x: (-x["tests"], x["brand"])):
            rows.append(f"| {brand_cell(b)} | {b['tests']} | {b['votes']} | {b['flags'] or '—'} |")
        p.append("\n".join(rows) + "\n")
        p.append("</details>\n")

    p.append("---\n")
    p.append("## Как это считается\n")
    p.append(
        f"- **{t['tests']} тестов** за период {r['period']['from']} — {period_to}, "
        f"**{t['brands']} брендов**, из них {t['ranked_brands']} с достаточной выборкой.\n"
        f"- **{t['pos']}** положительных реакций против **{t['neg']}** отрицательных.\n"
        f"- **{t['ambiguous']}** реакций (😁 🤣 и подобные) знака не несут и в Score не идут — "
        "они считаются отдельно, а не приписываются к плюсам молча.\n"
        f"- **{t['custom']}** кастом-эмодзи Telegram отдаёт без идентификатора, опознать их нечем. "
        "Они честно исключены и показаны здесь, а не растворены в цифрах.\n"
        f"- **{t['satire_tests']}** сатирических и **{t['vendor_tests']}** вендорских постов "
        "исключены из Score.\n"
        f"- **{t['referral_tests']} из {t['tests']}** тестов содержат рефссылку — на позицию это не влияет.\n"
    )
    p.append("Подробно — в [METHODOLOGY.md](./METHODOLOGY.md). Сырые данные и скрипты — в [data/](./data) и [scripts/](./scripts).\n")
    p.append("Разбор по чату «Обсуждение хостингов» — в [DISCUSSION_RATING.md](./DISCUSSION_RATING.md).\n")
    p.append("---\n")
    p.append(
        f"*Данные: {period_to} · Тестов: {t['tests']} · "
        f"Сгенерировано скриптом из `data/raw/` · Пересобрать: `python scripts/build.py`*\n"
    )

    (ROOT / "README.md").write_text("\n".join(p), encoding="utf-8")
    print(f"README.md собран: {len(ranked)} в рейтинге, {len(thin)} с малой выборкой, свежесть {age} дн.")


if __name__ == "__main__":
    main()
