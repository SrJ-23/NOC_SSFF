#!/usr/bin/env bash
# Build script para Render
set -o errexit

python -m pip install --upgrade pip
pip install -r requirements.txt
