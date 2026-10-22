#!/usr/bin/env bash
# Publish the web game to roshambo.docshock.studio: the roshambo package as committed at HEAD, the
# service that runs it (deploy/roshambo-web.service) and the Caddy site that serves it
# (deploy/roshambo.caddy), on the server shared with docshock.studio (ssh alias tff).
#
#   deploy/deploy.sh        dry run: runs the tests at HEAD and shows every change, touches nothing
#   deploy/deploy.sh --go   publishes, if the tests pass at HEAD
#
# The service restarts only when the code or the unit changed, since a restart ends every game in
# progress. If it doesn't come back, the log is printed and Caddy's config is left alone.
# The DNS record, a proxied A and AAAA for roshambo, is set once in Cloudflare, not here.
# Needs the login's passwordless sudo, for the app directory and the unit only.
set -euo pipefail
cd "$(dirname "$0")/.."

host=${SSH_HOST:-tff}
app=/srv/roshambo.docshock.studio
unit=/etc/systemd/system/roshambo-web.service
caddy_site=/etc/caddy/sites/roshambo.caddy
port=8777
go=false
[[ "${1:-}" == "--go" ]] && go=true
ssh=(ssh "$host")

if [[ -n $(git status --porcelain -- roshambo deploy) ]]; then
  echo "Note: roshambo/ or deploy/ has uncommitted changes. Only what's committed is published." >&2
fi

# What's committed, tested as it will run.
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git archive HEAD | tar -x -C "$work"
if ! out=$(cd "$work" && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests 2>&1); then
  printf '%s\n' "$out" >&2
  echo "The tests fail at HEAD, so nothing was published." >&2
  exit 1
fi
version=$(git log -1 --format='%h %s')

rsync_opts=(-rlpzc --delete-delay --delay-updates --chmod=D755,F644 --exclude=__pycache__ --itemize-changes)

if ! $go; then
  echo "== The code, at $version"
  if "${ssh[@]}" test -d "$app/roshambo"; then
    rsync "${rsync_opts[@]}" --dry-run "$work/roshambo/" "$host:$app/roshambo/"
  else
    echo "$app/roshambo doesn't exist yet; all of it is new."
  fi
  echo "== $unit"
  "${ssh[@]}" "cat $unit 2>/dev/null" | diff -u --label server --label deploy/roshambo-web.service - deploy/roshambo-web.service && echo "No change."
  echo "== $caddy_site"
  "${ssh[@]}" "cat $caddy_site 2>/dev/null" | diff -u --label server --label deploy/roshambo.caddy - deploy/roshambo.caddy && echo "No change."
  echo
  echo "Dry run only. Re-run with --go to publish."
  exit 0
fi

# The app directory, owned by the login, so publishing the code needs no sudo.
"${ssh[@]}" "sudo install -d -m 755 -o \$(id -un) -g \$(id -gn) $app"
changed=$(rsync "${rsync_opts[@]}" "$work/roshambo/" "$host:$app/roshambo/")
printf '%s\n' "$version" | "${ssh[@]}" "cat > $app/VERSION"

# The unit, installed if it changed; then a restart if anything changed or the game isn't running.
tmp=$("${ssh[@]}" mktemp)
"${ssh[@]}" "cat > $tmp" < deploy/roshambo-web.service
"${ssh[@]}" "set -e
  restart=${changed:+yes}
  if ! cmp -s $tmp $unit; then
    sudo install -m 644 $tmp $unit && sudo systemctl daemon-reload && restart=yes
    echo 'Service: unit installed.'
  fi
  rm -f $tmp
  sudo systemctl enable --quiet roshambo-web
  systemctl is-active --quiet roshambo-web || restart=yes
  if [ -n \"\$restart\" ]; then sudo systemctl restart roshambo-web; echo 'Service: restarted.'; else echo 'Service: no change.'; fi
  for i in \$(seq 40); do curl -fsS -o /dev/null http://127.0.0.1:$port/ && exit 0; sleep 0.25; done
  sudo journalctl -u roshambo-web -n 30 --no-pager
  exit 1" || { echo "The game isn't answering on the server; its log is above. Caddy was left as it was." >&2; exit 1; }

# The Caddy site. If Caddy refuses it, the old configuration keeps running and the old file goes
# back, so the next reload of any site on the server doesn't trip on it.
if "${ssh[@]}" "cat $caddy_site 2>/dev/null" | cmp -s - deploy/roshambo.caddy; then
  echo "Caddy: no change."
else
  "${ssh[@]}" "test -e $caddy_site || sudo install -m 644 -o \$(id -un) -g \$(id -gn) /dev/null $caddy_site"
  "${ssh[@]}" "f='$caddy_site'"'; old=$(mktemp); cat "$f" > "$old"; cat > "$f"
    if caddy reload --adapter caddyfile --config /etc/caddy/Caddyfile; then status=0; else status=$?; cat "$old" > "$f"; fi
    rm -f "$old"; exit $status' < deploy/roshambo.caddy
  echo "Caddy: running deploy/roshambo.caddy."
fi

# Through Caddy on the server itself, then from outside through Cloudflare.
"${ssh[@]}" "curl -fsS -k -o /dev/null --resolve roshambo.docshock.studio:443:127.0.0.1 https://roshambo.docshock.studio/" \
  || { echo "Caddy isn't serving roshambo.docshock.studio on the server." >&2; exit 1; }
if curl -fsS -o /dev/null --max-time 10 https://roshambo.docshock.studio/ 2>/dev/null; then
  echo "Published $version to https://roshambo.docshock.studio"
else
  echo "Published $version on the server. https://roshambo.docshock.studio doesn't answer from here yet:"
  echo "check its DNS record (proxied A and AAAA) in Cloudflare."
fi
