#!/usr/bin/env bash
set -e

BASEDIR=$(dirname "$0")
cd $BASEDIR

echo "=== ISort ==="
python -m isort .
python -m isort ./debspawn/dsrun

echo "=== Black ==="
python -m black .
