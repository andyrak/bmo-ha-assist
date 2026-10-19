#!/bin/sh
# Installs bmo-brightness and the timer that applies its schedule.
# Run from the repo:  sudo sh brightness/install.sh
# Re-run after editing SCHEDULE in brightness/bmo-brightness.
set -eu
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
DIR=$(cd "$(dirname "$0")" && pwd)

install -m 755 "$DIR/bmo-brightness" /usr/local/bin/bmo-brightness
install -m 644 "$DIR/bmo-brightness.service" "$DIR/bmo-brightness.timer" /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now bmo-brightness.timer
/usr/local/bin/bmo-brightness auto
echo "Installed. Scheduled brightness right now: $(/usr/local/bin/bmo-brightness now)%"
