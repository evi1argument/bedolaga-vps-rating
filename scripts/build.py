#!/usr/bin/env python3
"""Полная пересборка рейтинга: выгрузка -> tests.csv -> rating.json -> README.md.

    python scripts/build.py

Падает, если валидация нашла ошибку: лучше не выпустить обновление, чем
выпустить его с расходящимися цифрами.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = [
    ("разбираю выгрузку", "parse_export.py"),
    ("считаю рейтинг", "score.py"),
    ("собираю README", "render.py"),
    ("собираю DISCUSSION_RATING", "render_discussion.py"),
    ("проверяю", "validate.py"),
]


def main():
    for title, script in STEPS:
        print(f"\n=== {title} ({script}) ===")
        code = subprocess.call([sys.executable, str(HERE / script)])
        if code != 0:
            print(f"\n{script} завершился с кодом {code} — сборка остановлена.")
            return code
    print("\nГотово.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
