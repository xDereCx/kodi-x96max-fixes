#!/bin/bash
# network-watchdog.sh — if no LAN (192.168.x.x) IP shows up shortly after boot
# (excluding WireGuard/OpenVPN tunnel interfaces), restart connman.
LOGTAG="network-watchdog"
MAX_WAIT=60
INTERVAL=5
elapsed=0

has_lan_ip() {
    ip -4 -o addr show 2>/dev/null | awk '{print $2, $4}' \
        | grep -Ev '^(wg[0-9]*|tun[0-9]*|ppp[0-9]*|lo) ' \
        | grep -q '192\.168\.'
}

while [ "$elapsed" -lt "$MAX_WAIT" ]; do
    if has_lan_ip; then
        logger -t "$LOGTAG" "LAN IP present after ${elapsed}s, ok"
        exit 0
    fi
    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
done

logger -t "$LOGTAG" "No 192.168.x.x LAN IP after ${MAX_WAIT}s, restarting connman"
systemctl restart connman
sleep 20

if has_lan_ip; then
    logger -t "$LOGTAG" "connman restart fixed it, LAN IP now present"
else
    logger -t "$LOGTAG" "still no LAN IP after connman restart"
fi
