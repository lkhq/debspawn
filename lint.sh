#!/usr/bin/env bash
set -e

BASEDIR=$(dirname "$0")
cd $BASEDIR

echo "=== Flake8 ==="
python -m flake8 ./ --statistics
python -m flake8 debspawn/dsrun --statistics
echo "✓"

echo "=== Pylint ==="
python -m pylint -f colorized ./debspawn
python -m pylint -f colorized ./debspawn/dsrun
python -m pylint -f colorized ./tests ./data
python -m pylint -f colorized setup.py install-sysdata.py
echo "✓"

echo "=== MyPy ==="
python -m mypy .
python -m mypy ./debspawn/dsrun
echo "✓"

echo "=== Isort ==="
isort --diff .
echo "✓"

echo "=== Black ==="
black --diff .
