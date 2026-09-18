#!/usr/bin/env python3
"""mentions.csv + rating.json -> DISCUSSION_RATING.md

Запуск:  python scripts/render_discussion.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MIN_MENTIONS = 20


def spark(values):
    """Мини-график помесячной динамики."""
    blocks = "▁▂▃▄▅▆▇█"
    top = max(values) or 1
    return "".join(blocks[min(len(blocks) - 1, round(v / top * (len(blocks) - 1)))] for v in values)


def verdict_cell(b):
    if b is None:
        return "нет тестов", "нет тестов"
    if not b["ranked"]:
        return f"⚪ мало данных ({b['tests']} т. / {b['votes']} гол.)", "мало данных"
    share = f"{b['share']:.0%}"
    if b["wilson"] >= 0.55:
        return f"🟢 {share}", "тесты подтверждают"
    if b["wilson"] >= 0.30:
        return f"🔵 {share}", "тесты нейтральны"
    if b["wilson"] >= 0.15:
        return f"🟡 {share}", "тесты спорны"
    return f"🔴 {share}", "тесты против"


def main():
    rows = list(csv.DictReader(open(DATA / "processed" / "mentions.csv", encoding="utf-8")))
    months = [c for c in rows[0].keys() if c not in ("brand", "total")]
    rating = json.load(open(ROOT / "rating.json", encoding="utf-8"))
    by_brand = {b["brand"]: b for b in rating["brands"]}
    total_msgs = sum(int(r["total"]) for r in rows)

    p = []
    p.append('<div align="center">\n')
    p.append("# 💬 О чём говорят — чат «Обсуждение хостингов»\n")
    p.append("Счётчик упоминаний и динамика интереса. Оценка качества — в [README.md](./README.md).\n")
    p.append(
        f"![Сообщений](https://img.shields.io/badge/сообщений-174_782-blue?style=flat-square) "
        f"![Брендов](https://img.shields.io/badge/брендов-{len(rows)}-green?style=flat-square) "
        f"![Период](https://img.shields.io/badge/период-{months[0]}–{months[-1]}-orange?style=flat-square)\n"
    )
    p.append("</div>\n")
    p.append("---\n")

    p.append("## Что здесь считается\n")
    p.append(
        "**Единица счёта — одно сообщение**, в тексте которого встретился любой алиас бренда, "
        "без учёта регистра и с проверкой границ слова. Два упоминания в одном сообщении "
        "считаются за одно. HTML-разметка вырезается до поиска, иначе доменные имена в ссылках "
        "накручивают счёт.\n"
    )
    p.append(
        "> **Упоминания — это интерес, а не качество.** Лидер этой таблицы — Aeza, у которой "
        "в тестах 27% одобрения. Высокий счётчик означает «много говорят», и говорить могут "
        "что угодно. Колонка «в тестах» рядом показывает, что именно.\n"
    )
    p.append("---\n")

    p.append((ROOT / "content" / "discussion.md").read_text(encoding="utf-8").strip() + "\n")
    p.append("---\n")

    p.append(f"## 📊 Упоминания (от {MIN_MENTIONS})\n")
    p.append(f"Помесячно: {' · '.join(months)}\n")
    head = ("| # | Бренд | Всего | Динамика | " + " | ".join(m[5:] for m in months) +
            " | В тестах |\n|:---:|---|:---:|:---:|" + ":---:|" * len(months) + "---|\n")
    body = []
    n = 0
    for r in rows:
        total = int(r["total"])
        if total < MIN_MENTIONS:
            continue
        n += 1
        vals = [int(r[m]) for m in months]
        cell, note = verdict_cell(by_brand.get(r["brand"]))
        body.append(f"| {n} | **{r['brand']}** | {total} | `{spark(vals)}` | " +
                    " | ".join(str(v) for v in vals) + f" | {cell} |")
    p.append(head + "\n".join(body) + "\n")

    p.append("---\n")
    p.append("## 👀 Обсуждают, но не тестировали\n")
    p.append("Кандидаты на будущие тесты: в разговорах мелькают, а в «Тестах VPS» ни одного поста.\n")
    radar = [r for r in rows if int(r["total"]) >= 10 and r["brand"] not in by_brand]
    if radar:
        lines = ["| Бренд | Упоминаний |", "|---|:---:|"]
        for r in sorted(radar, key=lambda r: -int(r["total"]))[:25]:
            lines.append(f"| {r['brand']} | {r['total']} |")
        p.append("\n".join(lines) + "\n")
    else:
        p.append("*Сейчас таких нет: все заметные бренды из обсуждений уже протестированы.*\n")

    p.append("---\n")
    p.append(
        f"*Сообщений: 174 782 · Период: {months[0]} — {months[-1]} · "
        f"Упоминаний суммарно: {total_msgs} · Сгенерировано `scripts/render_discussion.py`*\n"
    )

    (ROOT / "DISCUSSION_RATING.md").write_text("\n".join(p), encoding="utf-8")
    print(f"DISCUSSION_RATING.md собран: {n} брендов в таблице, {len(radar)} на радаре")


if __name__ == "__main__":
    main()
