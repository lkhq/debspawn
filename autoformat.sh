#!/usr/bin/env bash
set -e

BASEDIR=$(dirname "$0")
cd $BASEDIR

echo "=== ISort ==="
python -m isort .

echo "=== Black ==="
python -m black .
