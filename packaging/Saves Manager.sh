#!/bin/bash
set -uo pipefail

unit=r36s-saves-manager.service
config_dir=/home/ark/.config/r36s-saves-manager
mapper_pid=
terminal_state=

translate() {
    /usr/bin/python3 -c 'import json, pathlib, sys; root = pathlib.Path("/home/ark/.local/share/r36s-saves-manager/locales"); english = json.loads((root / "en.json").read_text()); language = sys.argv[1] if sys.argv[1] in ("en", "it") else "en"; catalog = json.loads((root / (language + ".json")).read_text()); print(catalog.get(sys.argv[2], english[sys.argv[2]]))' "${R36S_LANGUAGE:-en}" "$1"
}

show_status() {
    local address
    if ! systemctl is-active --quiet "$unit"; then
        translate menu_inactive
        systemctl show "$unit" --property=ActiveState --property=SubState
        return 1
    fi
    if ! /usr/bin/python3 -c 'import urllib.request; response = urllib.request.urlopen("http://127.0.0.1:8765/", timeout=5); assert response.status == 200 and b"R36S" in response.read(4096)' 2>/dev/null; then
        translate menu_http_failed
        return 1
    fi
    translate menu_active
    for address in $(hostname -I); do
        if [[ "$address" != *:* ]]; then
            printf 'http://%s:8765\n' "$address"
        fi
    done
    translate menu_local
}

start_service() {
    if [[ ! -r "$config_dir/password" ]]; then
        translate menu_password_missing
        return 1
    fi
    if ! mountpoint -q /roms2; then
        translate menu_sd_missing
        return 1
    fi
    if ! sudo -n systemctl start "$unit"; then
        translate menu_start_failed
        printf 'Log: journalctl -u %s -n 30\n' "$unit"
        return 1
    fi
    show_status
}

stop_service() {
    if sudo -n systemctl stop "$unit"; then
        translate menu_stopped
    else
        translate menu_stop_failed
        return 1
    fi
}

cleanup() {
    if [[ -n "$mapper_pid" ]]; then
        sudo -n kill -TERM "$mapper_pid" 2>/dev/null || true
        wait "$mapper_pid" 2>/dev/null || true
    fi
    if [[ -n "$terminal_state" ]]; then
        stty "$terminal_state" < /dev/tty1 2>/dev/null || true
    fi
    /usr/bin/dialog --clear 2>/dev/null || true
}

case "${1:-}" in
    --start) start_service; exit $? ;;
    --status) show_status; exit $? ;;
    --stop) stop_service; exit $? ;;
    '') ;;
    *) printf '%s %s [--start|--status|--stop]\n' "$(translate menu_usage)" "$0"; exit 2 ;;
esac

export TERM=linux
export DIALOGRC=/opt/inttools/noshadows.dialogrc
export SDL_GAMECONTROLLERCONFIG_FILE=/opt/inttools/gamecontrollerdb.txt
exec < /dev/tty1 > /dev/tty1 2>&1
terminal_state=$(stty -g)
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
if ! pgrep -x gptokeyb > /dev/null && ! pgrep -x oga_controls > /dev/null; then
    sudo -n env SDL_GAMECONTROLLERCONFIG_FILE="$SDL_GAMECONTROLLERCONFIG_FILE" /opt/inttools/gptokeyb -1 "dialog" -c /opt/inttools/keys.gptk > /dev/null 2>&1 &
    mapper_pid=$!
fi

while choice=$(/usr/bin/dialog --stdout --title 'R36S Saves Manager' --cancel-label "$(translate menu_exit)" --ok-label "$(translate menu_ok)" --menu '' 16 48 4 "$(translate menu_start)" "$(translate menu_start_description)" "$(translate menu_status)" "$(translate menu_status_description)" "$(translate menu_stop)" "$(translate menu_stop_description)"); do
    case "$choice" in
        "$(translate menu_start)") message=$(start_service 2>&1) || true ;;
        "$(translate menu_status)") message=$(show_status 2>&1) || true ;;
        "$(translate menu_stop)") message=$(stop_service 2>&1) || true ;;
        *) continue ;;
    esac
    /usr/bin/dialog --title 'R36S Saves Manager' --ok-label "$(translate menu_ok)" --msgbox "$message" 16 48 || true
done