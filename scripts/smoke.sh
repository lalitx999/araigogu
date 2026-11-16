#!/usr/bin/env bash
# End-to-end smoke test against a RUNNING stack (default http://localhost:8000).
#   scripts/smoke.sh [BASE_URL] [AI_URL]
# Needs: bash, curl, python3. Creates a throw-away user; safe to re-run.
set -u
BASE="${1:-http://localhost:8000}"
AI="${2:-http://localhost:8001}"
JAR="$(mktemp)"; trap 'rm -f "$JAR"' EXIT
EMAIL="smoke$(date +%s)@example.com"; PW="Smoke-test-pass-9731"
pass=0; fail=0
ok()  { echo "  ok   $1"; pass=$((pass+1)); }
bad() { echo "  FAIL $1  ($2)"; fail=$((fail+1)); }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1" "got '$2', want '$3'"; fi; }
json() { python3 -c "import sys,json
try: d=json.load(sys.stdin); v=d
except Exception: print('<not-json>'); sys.exit()
for k in sys.argv[1].split('.'):
    v=v.get(k,'<missing>') if isinstance(v,dict) else '<missing>'
print(v)" "$1"; }
present() { case "$1" in ""|"<missing>"|"<not-json>") return 1;; *) return 0;; esac; }
csrf() { awk '$6=="csrftoken"{print $7}' "$JAR" | tail -1; }
post() { # post URL [curl args...]  -> body; ajax headers + csrf
  local url="$1"; shift
  curl -s -X POST -b "$JAR" -c "$JAR" -H "X-Requested-With: XMLHttpRequest" -H "X-CSRFToken: $(csrf)" -H "Referer: $BASE/" "$@" "$url"; }

echo "== services"
check "web /healthz"        "$(curl -s "$BASE/healthz" | json status)" ok
check "ai-service /health"  "$(curl -s "$AI/health" | json status)" ok
echo "   llm_configured: $(curl -s "$AI/health" | json llm_configured)  (false => degraded mode, AI-dependent steps are expected to differ)"

echo "== no-CDN guarantees"
H="$(curl -sI "$BASE/")"
echo "$H" | grep -qi "content-security-policy: default-src 'self'" && ok "CSP header present" || bad "CSP header" "missing"
HTML="$(curl -s "$BASE/")"
if [ -z "$HTML" ]; then bad "home page" "empty response"
elif echo "$HTML" | grep -qE '(src|href)="(https?:)?//'; then bad "external URL in page" "found"
else ok "page references no external host"; fi
check "bootstrap css served"  "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/static/vendor/bootstrap/css/bootstrap.min.css")" 200
check "bootstrap js served"   "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/static/vendor/bootstrap/js/bootstrap.bundle.min.js")" 200

echo "== accounts"
curl -s -c "$JAR" -o /dev/null "$BASE/accounts/register/"
code=$(curl -s -b "$JAR" -c "$JAR" -o /dev/null -w '%{http_code}' -H "Referer: $BASE/" \
  --data-urlencode "csrfmiddlewaretoken=$(csrf)" --data-urlencode "full_name=Smoke Test" \
  --data-urlencode "email=$EMAIL" --data-urlencode "password1=$PW" --data-urlencode "password2=$PW" \
  --data-urlencode "accept_terms=on" "$BASE/accounts/register/")
check "register -> redirect" "$code" 302
check "chat page after login" "$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' "$BASE/chat/")" 200

echo "== chat (AJAX)"
loc=$(curl -s -b "$JAR" -c "$JAR" -o /dev/null -w '%{redirect_url}' -H "Referer: $BASE/" \
  --data-urlencode "csrfmiddlewaretoken=$(csrf)" -d "language=ja&difficulty=beginner" "$BASE/chat/new/")
SID="$(echo "$loc" | sed -E 's#.*/chat/([0-9]+)/.*#\1#')"
[ -n "$SID" ] && ok "create chat session ($SID)" || bad "create chat session" "$loc"
R="$(post "$BASE/chat/$SID/send/" -H 'Content-Type: application/json' -d '{"message":"สวัสดี สอนคำว่าขอบคุณหน่อย"}')"
if present "$(echo "$R" | json reply)"; then ok "AI replied"; else echo "  info  no AI reply (expected when OPENAI_API_KEY is empty): $(echo "$R" | json error)"; fi
check "rename"  "$(post "$BASE/chat/$SID/rename/" -d 'title=Smoke chat' | json title)" "Smoke chat"

echo "== community (AJAX)"
R="$(post "$BASE/community/post/new/" -d 'content=ทดสอบโพสต์จาก smoke test')"
status="$(echo "$R" | json status)"; PID="$(echo "$R" | json post_id)"
case "$status" in published) ok "post published (id $PID)";; review) ok "post flagged -> review payload";; *) bad "create post" "$R";; esac
if [ "$status" = published ]; then
  check "like toggle on"  "$(post "$BASE/community/post/$PID/like/" | json active)" True
  check "like toggle off" "$(post "$BASE/community/post/$PID/like/" | json active)" False
  echo "  info  ryu comment created=$(post "$BASE/community/post/$PID/ryu/" | json created) (False is normal in degraded mode)"
  check "comment" "$(post "$BASE/community/post/$PID/comment/" -d 'body=ความเห็นทดสอบ' | json count)" 1
fi
present "$(curl -s -b "$JAR" -H 'X-Requested-With: XMLHttpRequest' "$BASE/community/" | json html)" && ok "feed returns JSON fragment" || bad "feed JSON" "no html key"
present "$(curl -s -b "$JAR" -H 'X-Requested-With: XMLHttpRequest' "$BASE/community/search/?q=smoke" | json html)" && ok "search returns JSON fragment" || bad "search JSON" "no html key"

echo "== ai-service auth"
check "no token -> 401" "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$AI/v1/chat" -H 'Content-Type: application/json' -d '{"message":"x"}')" 401

echo; echo "passed: $pass   failed: $fail"; [ "$fail" -eq 0 ]
