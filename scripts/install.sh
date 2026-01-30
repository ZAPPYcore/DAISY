#!/usr/bin/env sh
set -eu

PREFIX="${1:-$HOME/.daisy}"

python3 -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/python" -m pip install --upgrade pip
"$PREFIX/venv/bin/python" -m pip install -e .

echo "DAISY installed."
echo "Activate: source $PREFIX/venv/bin/activate"
echo "Run: daisy --help"

