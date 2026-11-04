#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

xgettext -k_ -kadd_menu_branch:2 -o locale/stable-gimpfusion3.pot \
  --from-code=UTF-8 --package-name=stable-gimpfusion3 --package-version=0.1.0 \
  --language=Python --copyright-holder=shsmad --add-comments=TRANSLATORS \
  stable-gimpfusion3.py sg_*.py sg_plugins/*.py

for lang in en it ru zhcn; do
  catalog="locale/${lang}/LC_MESSAGES/stable-gimpfusion3"
  msgmerge --backup=none --no-fuzzy-matching -U "${catalog}.po" locale/stable-gimpfusion3.pot
  msgcmp "${catalog}.po" locale/stable-gimpfusion3.pot
  msgfmt --check --check-format "${catalog}.po" -o "${catalog}.mo"
done

# GIMP native menus use the standard Chinese locale name.
mkdir -p locale/zh_CN/LC_MESSAGES
cp locale/zhcn/LC_MESSAGES/stable-gimpfusion3.mo locale/zh_CN/LC_MESSAGES/stable-gimpfusion3.mo
