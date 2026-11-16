#!/usr/bin/env bash
# Run the whole project on localhost. No docker.
#   scripts/dev.sh setup     create .venv, install deps, migrate        (run once)
#   scripts/dev.sh           start ai-service (:8001) + web (:8000)     (Ctrl+C stops both)
#   scripts/dev.sh user      create an admin user
#   scripts/dev.sh test      run all tests
#
# Database: SQLite by default (zero setup).  MySQL on localhost:  USE_MYSQL=1 scripts/dev.sh setup
#   (needs `brew install mysql pkg-config`, and the DB + user from .env created once:
#    CREATE DATABASE araigogu CHARACTER SET utf8mb4; CREATE USER 'araigogu'@'localhost' IDENTIFIED BY '<DB_PASSWORD in .env>';
#    GRANT ALL ON araigogu.* TO 'araigogu'@'localhost'; )
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

# --- config: secrets come from .env, localhost overrides on top ---
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-local-dev-only-secret}"
export DJANGO_DEBUG=1
export AI_INTERNAL_TOKEN="${AI_INTERNAL_TOKEN:-local-dev-token}"
export AI_SERVICE_URL="http://127.0.0.1:8001"
if [ "${USE_MYSQL:-0}" = "1" ]; then
  export DB_HOST=127.0.0.1 DB_PORT="${DB_PORT:-3306}"; unset DB_ENGINE
else
  export DB_ENGINE=sqlite
fi

setup() {
  [ -x "$PY" ] || python3 -m venv "$VENV"
  "$PY" -m pip install -q --upgrade pip >/dev/null 2>&1 || true
  "$PY" -m pip install -q "Django>=5.2,<5.3" httpx "whitenoise>=6.7" -r "$ROOT/ai-service/requirements.txt"
  [ "${USE_MYSQL:-0}" = "1" ] && "$PY" -m pip install -q "mysqlclient>=2.2"
  cd "$ROOT/web" && "$PY" manage.py migrate --noinput && "$PY" manage.py createcachetable
  echo "setup done. next: scripts/dev.sh"
}

run() {
  [ -x "$PY" ] || { echo "run 'scripts/dev.sh setup' first"; exit 1; }
  if [ -z "${GEMINI_API_KEY:-}${GROQ_API_KEY:-}${DEEPSEEK_API_KEY:-}${OPENAI_API_KEY:-}" ]; then
    echo "note: no AI key set (GEMINI/GROQ/DEEPSEEK/OPENAI) -> AI runs in degraded mode (set one in .env)"
  fi
  ( cd "$ROOT/ai-service" && exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 ) &
  AI_PID=$!
  trap 'kill $AI_PID 2>/dev/null || true' EXIT INT TERM
  cd "$ROOT/web"
  WEB_PORT="${WEB_PORT:-8000}"
  echo "web: http://localhost:$WEB_PORT   ai-service: http://localhost:8001/health"
  "$PY" manage.py runserver "127.0.0.1:$WEB_PORT"
}

case "${1:-run}" in
  setup) setup ;;
  run)   run ;;
  user)  cd "$ROOT/web" && "$PY" manage.py createsuperuser ;;
  test)  (cd "$ROOT/ai-service" && AI_INTERNAL_TOKEN=test "$PY" -m pytest -q -p no:cacheprovider) && \
         (cd "$ROOT/web" && DB_ENGINE=sqlite "$PY" manage.py test) ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
