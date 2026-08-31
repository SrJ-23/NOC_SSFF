#!/usr/bin/env bash
# Start script para Render que busca gunicorn/python en todos los PATHs del entorno

export PATH="$PATH:$HOME/.local/bin:/opt/render/project/src/.venv/bin:/opt/render/project/poetry/bin"

if [ -f "/opt/render/project/src/.venv/bin/gunicorn" ]; then
    exec /opt/render/project/src/.venv/bin/gunicorn app:app --bind 0.0.0.0:${PORT:-10000}
elif command -v gunicorn >/dev/null 2>&1; then
    exec gunicorn app:app --bind 0.0.0.0:${PORT:-10000}
elif [ -f "/opt/render/project/src/.venv/bin/python" ]; then
    exec /opt/render/project/src/.venv/bin/python app.py
else
    exec python3 app.py
fi
