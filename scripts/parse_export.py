#!/usr/bin/env python3
"""Telegram-выгрузка чата «Тесты VPS» -> data/processed/tests.csv

Один тест = одно сообщение. Скрипт ничего не оценивает: он только извлекает
факты (бренд, реакции, флаги) и оставляет след для ручной проверки.
Всё, что не удалось разобрать, уезжает в data/processed/unmatched.csv.

Запуск:  python scripts/parse_export.py
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "processed"

# Тестом считается сообщение со скриншотом, узнанным брендом и минимумом текста.
# Формат в чате разный: и развёрнутые обзоры, и «бренд + конфиг + вердикт» в три
# строки. Порог 150 отсекал вторые — вместе с 💩×19 под ними.
MIN_TEST_CHARS = 60
MIN_TEST_CHARS_NO_PHOTO = 150

REFERRAL_RE = re.compile(
    r"(?:\bреф\b|\bрефк|ref_id=|[?&]ref=|/aff|aff_id|partner_id|\bреферал)", re.I
)

FLAG_RE = re.compile("[\U0001F1E6-\U0001F1FF]{2}")

# Самораскрытие представителя хостинга. Такой пост — реклама, а не тест.
VENDOR_RE = re.compile(
    r"(?:я\s+представитель|мы\s+в\s+\S+\s+затестили|наш(?:а|его)?\s+хостинг|"
    r"у\s+нас\s+открылся|открывайте\s+тикет,?\s+я|представитель\s+хостинга)", re.I
)

NEG_MARKERS = [
    "не рекомендую", "не советую", "несоветую", "не берите", "не стоит брать",
    "говно", "говнохост", "шляпа", "скам", "развод", "кал", "помойка",
    "ужас", "отвратительно", "мусор", "не покупайте", "обходите стороной",
    "оно вам не надо", "не подойдёт", "не подойдет", "разочаров", "верните деньги",
]
POS_MARKERS = [
    "рекомендую", "советую", "отличный", "отлично", "доволен", "всё работает",
    "все работает", "без нареканий", "стабильно работает", "полет нормальный",
    "полёт нормальный", "проблем не было", "проблем нет", "хороший хостинг",
    "годно", "топ за свои деньги", "нареканий нет", "работает на ура",
]


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def plain_text(msg):
    """Собирает текст сообщения из text_entities (или из text, если их нет)."""
    ents = msg.get("text_entities")
    if ents:
        return "".join(e.get("text", "") for e in ents)
    txt = msg.get("text")
    if isinstance(txt, str):
        return txt
    return "".join(e if isinstance(e, str) else e.get("text", "") for e in (txt or []))


def split_reactions(msg, classes):
    """-> (pos, neg, amb, custom, подробная раскладка)."""
    pos = neg = amb = custom = 0
    detail = {}
    for r in msg.get("reactions", []):
        count = r.get("count", 0)
        if r.get("type") != "emoji":
            custom += count
            detail["CUSTOM"] = detail.get("CUSTOM", 0) + count
            continue
        emoji = r.get("emoji", "")
        detail[emoji] = detail.get(emoji, 0) + count
        if emoji in classes["positive"]:
            pos += count
        elif emoji in classes["negative"]:
            neg += count
        elif emoji in classes["ambiguous"]:
            amb += count
        else:
            # Незнакомая реакция — не молчим, validate.py это поймает.
            detail.setdefault("_UNKNOWN", []).append(emoji)
            amb += count
    return pos, neg, amb, custom, detail


def match_brand(text, brands):
    """Бренд по первым 400 символам.

    Побеждает алиас, встретившийся РАНЬШЕ всех: тест почти всегда начинается с
    названия хостинга, а дальше по тексту легко всплывает чужой бренд
    («Beget … использую как мост к Hetzner» — это тест Beget, не Hetzner).
    При равной позиции берём более длинный алиас.
    """
    head = text[:400].lower()
    best = None
    best_pos = len(head) + 1
    best_len = 0
    for brand in brands:
        for alias in brand["aliases"]:
            pos = head.find(alias)
            if pos == -1:
                continue
            if pos < best_pos or (pos == best_pos and len(alias) > best_len):
                best, best_pos, best_len = brand["name"], pos, len(alias)
    return best


def guess_verdict(text):
    """Грубая эвристика вердикта автора. Всегда проигрывает overrides.json."""
    low = text.lower()
    neg = sum(1 for m in NEG_MARKERS if m in low)
    pos = sum(1 for m in POS_MARKERS if m in low)
    if neg and neg > pos:
        return "negative", "heuristic"
    if pos and pos > neg:
        return "positive", "heuristic"
    return "unknown", "heuristic"


def main():
    brands = load_json(DATA / "brands.json")
    classes = {k: set(v) for k, v in load_json(DATA / "reactions.json").items()
               if k in ("positive", "negative", "ambiguous")}
    overrides = {k: v for k, v in load_json(DATA / "overrides.json").items()
                 if not k.startswith("_")}

    exports = sorted(RAW.glob("*.json"))
    if not exports:
        sys.exit(f"нет выгрузок в {RAW}. Положите туда result.json из Telegram.")

    rows, unmatched = [], []
    seen_ids = set()

    for path in exports:
        dump = load_json(path)
        for msg in dump.get("messages", []):
            if msg.get("type") != "message":
                continue
            mid = str(msg.get("id"))
            if mid in seen_ids:      # одно сообщение может попасть в две выгрузки
                continue
            text = plain_text(msg).strip()
            ov = overrides.get(mid, {})
            if ov.get("exclude"):
                continue
            floor = MIN_TEST_CHARS if msg.get("photo") else MIN_TEST_CHARS_NO_PHOTO
            if len(text) < floor:
                continue

            brand = ov.get("brand") or match_brand(text, brands)
            pos, neg, amb, custom, detail = split_reactions(msg, classes)

            if not brand:
                unmatched.append({
                    "msg_id": mid,
                    "date": msg.get("date", "")[:10],
                    "author": msg.get("from", ""),
                    "reactions": pos + neg + amb + custom,
                    "head": text[:120].replace("\n", " "),
                })
                continue

            seen_ids.add(mid)
            if "verdict" in ov:
                verdict, vsrc = ov["verdict"], "override"
            else:
                verdict, vsrc = guess_verdict(text)

            rows.append({
                "msg_id": mid,
                "date": msg.get("date", "")[:10],
                "author_id": msg.get("from_id", ""),
                "author": msg.get("from", ""),
                "brand": brand,
                "verdict": verdict,
                "verdict_source": vsrc,
                "pos": pos,
                "neg": neg,
                "ambiguous": amb,
                "custom": custom,
                "flags": "".join(dict.fromkeys(FLAG_RE.findall(text[:300]))),
                "has_referral": int(bool(REFERRAL_RE.search(text))),
                "vendor_post": int(ov["vendor_post"]) if "vendor_post" in ov
                               else int(bool(VENDOR_RE.search(text))),
                "text_len": len(text),
                "reactions_detail": json.dumps(detail, ensure_ascii=False),
                "source_file": path.name,
            })

    rows.sort(key=lambda r: (r["date"], r["msg_id"]))
    OUT.mkdir(parents=True, exist_ok=True)

    with open(OUT / "tests.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    with open(OUT / "unmatched.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["msg_id", "date", "author", "reactions", "head"])
        w.writeheader()
        w.writerows(unmatched)

    total = len(rows) + len(unmatched)
    print(f"выгрузок обработано : {len(exports)}")
    print(f"тестов распознано   : {len(rows)}")
    print(f"бренд не определён  : {len(unmatched)}  ({len(unmatched)/total:.0%}) -> unmatched.csv")
    print(f"период              : {rows[0]['date']} .. {rows[-1]['date']}")
    print(f"вердикт вручную     : {sum(1 for r in rows if r['verdict_source']=='override')}")
    print(f"с рефссылкой        : {sum(r['has_referral'] for r in rows)} ({sum(r['has_referral'] for r in rows)/len(rows):.0%})")


if __name__ == "__main__":
    main()
