#!/bin/sh
# Check the bundled examples. The failing runs exit 1 on purpose,
# so each one ends with "|| true"; the script itself ends with
# exit 0 so it can be run as a demo. Run from the repo root:
# sh examples/run-example.sh
cd "$(dirname "$0")/.."
echo "== good.html: one good title, passes =="
python3 src/html_title_checker.py examples/good.html || true
echo
echo "== missing-title.html: no title at all =="
python3 src/html_title_checker.py examples/missing-title.html || true
echo
echo "== short-title.html: title too short =="
python3 src/html_title_checker.py examples/short-title.html || true
echo
echo "== long-title.html: title too long =="
python3 src/html_title_checker.py examples/long-title.html || true
echo
echo "== pages/: a folder walk, one bad page =="
python3 src/html_title_checker.py examples/pages/ || true
