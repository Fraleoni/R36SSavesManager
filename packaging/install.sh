#!/bin/bash
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
    printf 'Run: sudo -n bash packaging/install.sh\n' >&2
    exit 1
fi

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
app_dir=/home/ark/.local/share/r36s-saves-manager
config_dir=/home/ark/.config/r36s-saves-manager
unit=/etc/systemd/system/r36s-saves-manager.service
launcher='/opt/system/Advanced/Saves Manager.sh'

id ark > /dev/null
test -x /usr/bin/python3
test -d /opt/system/Advanced
test -d /home/ark/.config/retroarch/saves
for path in "$app_dir" "$app_dir/locales" "$app_dir/locales/en.json" "$app_dir/locales/it.json" "$config_dir" "$config_dir/config.json" "$config_dir/password" "$unit" "$launcher"; do
    if [[ -L "$path" ]]; then
        printf 'Installation refused: symbolic link %s\n' "$path" >&2
        exit 1
    fi
done
for filename in R36SavesManager.py index.html app.js console.png config.json locales/en.json locales/it.json packaging/r36s-saves-manager.service 'packaging/Saves Manager.sh'; do
    test -f "$source_dir/$filename"
done
bash -n "$source_dir/packaging/Saves Manager.sh"
/usr/bin/python3 -c 'import ast, json, pathlib, sys; root = pathlib.Path(sys.argv[1]); ast.parse((root / "R36SavesManager.py").read_text()); [json.loads((root / name).read_text(encoding="utf-8")) for name in ("config.json", "locales/en.json", "locales/it.json")]' "$source_dir"

if [[ -e "$unit" ]]; then
    systemctl stop r36s-saves-manager.service
fi
install -d -o ark -g ark -m 0755 "$app_dir"
install -d -o ark -g ark -m 0755 "$app_dir/locales"
install -d -o ark -g ark -m 0700 "$config_dir"
for filename in R36SavesManager.py index.html app.js console.png locales/en.json locales/it.json; do
    install -o ark -g ark -m 0644 "$source_dir/$filename" "$app_dir/$filename"
done
if [[ ! -e "$config_dir/config.json" ]]; then
    install -o ark -g ark -m 0600 "$source_dir/config.json" "$config_dir/config.json"
fi
install -o root -g root -m 0644 "$source_dir/packaging/r36s-saves-manager.service" "$unit"
install -o root -g root -m 0755 "$source_dir/packaging/Saves Manager.sh" "$launcher"
systemd-analyze verify "$unit"
systemctl daemon-reload
printf 'Installed. Service not started or enabled at boot.\n'
printf 'Existing configuration and password preserved. ROMs and saves unchanged.\n'
printf 'Set the password as ark, then start from Advanced > Saves Manager.\n'