#!/usr/bin/env bash
# Daily MySQL backup (run on the SERVER, e.g. from cron). Keeps the last 14 dumps.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
out="backups/araigogu-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
  sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines "$MYSQL_DATABASE"' | gzip > "$out"
ls -1t backups/araigogu-*.sql.gz | tail -n +15 | xargs -r rm --
echo "wrote $out"
