#!/usr/bin/env python3
"""HTML-выгрузка чата «Обсуждение хостингов» -> data/processed/mentions.csv

Зачем отдельный скрипт: в прежней версии рейтинга счётчики упоминаний были
невоспроизводимы — нигде не описано, что считалось (регистр? подстрока?
кириллические алиасы? сообщения представителей?). Здесь метод зафиксирован:

  единица счёта = ОДНО СООБЩЕНИЕ, в тексте которого встретился любой алиас
  бренда, без учёта регистра. Два упоминания в одном сообщении = один раз.
  HTML-разметка вырезается до поиска, иначе доменные имена в ссылках
  накручивают счёт.

Выгрузка «Обсуждения» весит ~190 МБ и в репозиторий не кладётся, поэтому путь
к ней передаётся аргументом, а в git уезжает только итоговый CSV.

    python scripts/parse_mentions.py "путь/к/ChatExport_YYYY-MM-DD"
"""
import csv
import html
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MSG_RE = re.compile(
    r'<div class="message default clearfix(?: joined)?"[^>]*>(.*?)(?=<div class="message |\Z)',
    re.S,
)
DATE_RE = re.compile(r'title="(\d{2})\.(\d{2})\.(\d{4})')
BODY_RE = re.compile(r'<div class="text">(.*?)</div>', re.S)
TAG_RE = re.compile(r"<[^>]+>")


def strip_html(chunk):
    return html.unescape(TAG_RE.sub(" ", chunk))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    export = Path(sys.argv[1])
    files = sorted(export.glob("messages*.html"),
                   key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    if not files:
        sys.exit(f"в {export} нет файлов messages*.html")

    brands = json.load(open(DATA / "brands.json", encoding="utf-8"))
    # Границы слова обязательны: без них алиас «serv» ловил «server»,
    # «serverspace» и «servcity» и накручивал счётчик втрое.
    # Короткие алиасы в свободном чате всё равно слишком шумные.
    lookup = []
    for b in brands:
        pats = [re.compile(r"(?<![0-9a-zа-яё])" + re.escape(a) + r"(?![0-9a-zа-яё])")
                for a in b["aliases"] if len(a) >= 4]
        if pats:
            lookup.append((b["name"], pats))

    counts = defaultdict(lambda: defaultdict(int))   # brand -> month -> messages
    total_msgs = 0
    months = set()

    for path in files:
        raw = path.read_text(encoding="utf-8", errors="replace")
        for chunk in MSG_RE.findall(raw):
            d = DATE_RE.search(chunk)
            if not d:
                continue
            month = f"{d.group(3)}-{d.group(2)}"
            months.add(month)
            total_msgs += 1
            body = BODY_RE.search(chunk)
            if not body:
                continue
            text = strip_html(body.group(1)).lower()
            if not text.strip():
                continue
            for name, pats in lookup:
                if any(p.search(text) for p in pats):
                    counts[name][month] += 1

    months = sorted(months)
    out = DATA / "processed" / "mentions.csv"
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["brand", "total"] + months)
        rows = sorted(counts.items(), key=lambda kv: -sum(kv[1].values()))
        for name, per_month in rows:
            w.writerow([name, sum(per_month.values())] + [per_month.get(m, 0) for m in months])

    print(f"файлов обработано : {len(files)}")
    print(f"сообщений         : {total_msgs}")
    print(f"период            : {months[0]} .. {months[-1]}")
    print(f"брендов упомянуто : {len(counts)}")
    print(f"-> {out}")
    print()
    print(f"{'бренд':<20}{'всего':>8}   по месяцам")
    for name, per_month in sorted(counts.items(), key=lambda kv: -sum(kv[1].values()))[:20]:
        series = " ".join(f"{per_month.get(m, 0):>5}" for m in months)
        print(f"{name:<20}{sum(per_month.values()):>8}   {series}")


if __name__ == "__main__":
    main()
