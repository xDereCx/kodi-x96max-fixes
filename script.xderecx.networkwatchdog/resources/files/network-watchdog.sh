#!/bin/bash
# network-watchdog.sh — if no LAN (192.168.x.x) IP shows up shortly after boot
# (excluding WireGuard/OpenVPN tunnel interfaces), restart connman. Keeps
# retrying (with a cooldown between attempts) for as long as it takes -
# only stops once a real LAN IP actually shows up.
LOGTAG="network-watchdog"
INITIAL_GRACE=60   # give connman this long on its own before the first restart
CHECK_INTERVAL=5   # how often to poll while waiting
RESTART_COOLDOWN=30 # how long to wait after a restart before checking/retrying
elapsed=0
restarts=0

has_lan_ip() {
    ip -4 -o addr show 2>/dev/null | awk '{print $2, $4}' \
        | grep -Ev '^(wg[0-9]*|tun[0-9]*|ppp[0-9]*|lo) ' \
        | grep -q '192\.168\.'
}

while true; do
    if has_lan_ip; then
        logger -t "$LOGTAG" "LAN IP present after ${elapsed}s (${restarts} connman restart(s)), ok"
        exit 0
    fi

    if [ "$elapsed" -lt "$INITIAL_GRACE" ]; then
        sleep "$CHECK_INTERVAL"
        elapsed=$((elapsed + CHECK_INTERVAL))
        continue
    fi

    restarts=$((restarts + 1))
    logger -t "$LOGTAG" "No 192.168.x.x LAN IP after ${elapsed}s, restarting connman (attempt ${restarts})"
    systemctl restart connman
    sleep "$RESTART_COOLDOWN"
    elapsed=$((elapsed + RESTART_COOLDOWN))
done
