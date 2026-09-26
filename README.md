# R36S Saves Manager

[Italiano](README-it.md)

A local web app for importing RetroArch saves onto the R36S, downloading saves
and backups, and deleting automatic savestates. Available in English and Italian.
Requires **Python >= 3.9**, with no external packages or Internet access.

## Supported Formats

| System | Accepted input | Destination |
| --- | --- | --- |
| Super Nintendo | `.srm` | Per-game `.srm` save |
| PlayStation | `.srm`, raw 128 KiB `.mcd` / `.mcr` | Per-game `.srm` memory card |

Files are copied without format conversion. PSX raw cards are checked for size,
signature, and header checksum, but game compatibility is not guaranteed.
**A PSX import replaces the entire per-game memory card**, not a single slot.
The shared card `pcsx-card2.mcd` is not managed.

Importing savestates, headered exports, `.bin` cards, and standalone emulator
saves is not supported. A `.sav` file is accepted only when the system is
configured for `.sav`; it is not automatically converted to `.srm`.
Always check the game's region, revision, and emulator compatibility.

## Installation

### From Windows

Requires PowerShell 5.1 or 7, the native Windows OpenSSH client, and `tar.exe`.
The console installer targets the dArkOSen layout with user `ark`, `systemd`,
`dialog`, `/opt/inttools/gptokeyb`, and passwordless `sudo -n`.

```powershell
.\packaging\deploy.ps1
```

Enter the console's IPv4 address and SSH user, then choose whether to publish
the configuration and start the service. OpenSSH handles authentication;
verify the console's fingerprint on first connection.

- Deployment stops the service and invalidates sessions: finish imports first.
- Existing configuration and web password are preserved by default.
- `-PublishConfig` replaces the complete remote configuration after backing it up; profiles are not merged.
- `-StartService` starts the service afterward; startup at boot is never enabled.
- `-DryRun` checks the package without connecting. Deployment has no automatic rollback.

### Manual Installation

Transfer [R36SavesManager.py](R36SavesManager.py), [config.json](config.json),
[index.html](index.html), [app.js](app.js), [console.png](console.png),
the [locales](locales) directory, and [packaging](packaging) to the console.
Preserve the directory structure, then run:

```bash
sudo -n bash packaging/install.sh
```

### Password and Startup

After either installation method, set the web password from an interactive SSH
terminal **as `ark`, without sudo**:

```bash
python3 /home/ark/.local/share/r36s-saves-manager/R36SavesManager.py \
  --set-password --password-file /home/ark/.config/r36s-saves-manager/password
```

Use at least 8 characters and a password different from the SSH password. Enter
it only at the hidden prompts. The password file is stored in plaintext with
permissions `0600`, in a private `0700` directory; `ark` and root can read it.
To change it, repeat the command and restart the service.

Open **Advanced > Saves Manager > Start**, then visit the displayed address
from a PC or phone on the same network. The default port is `8765`.
**Status** shows the service state; **Stop** shuts it down. Leaving the menu
keeps the server running. If the port is occupied, startup fails.

### Run Without Installing

Copy the same runtime files and `locales` directory, then run as `ark`:

```bash
python3 R36SavesManager.py --host 0.0.0.0 --port 8765
```

Enter the web password at the prompt; it is not saved to disk in this mode.
The server runs in the foreground, so closing SSH may stop it. Use `--port`
to select a different port.

## Import Saves

1. **Close the game on the console** to prevent the emulator from overwriting the save.
2. Select the system and ROM, then choose or drag in a nonempty save file, up to **16 MiB**.
3. Open the preview and check the destination, which is determined by the selected ROM.
4. Confirm that the game is closed, approve any replacement, and import.

Previews are single-use and expire after ten minutes. Imports are rejected if
the destination is ambiguous or the existing save has changed since preview.
Select PlayStation before uploading `.mcd` / `.mcr` files.

Before replacement, the old save is copied to `.r36s-backups` beside the save.
If backup creation fails, the save is not replaced. The current save can be
downloaded from the preview, and the previous backup immediately after import.
Older backups remain on the SD card; restore their `.srm` or `.sav` extension
before uploading them manually. There is no backup history browser or automatic cleanup.
**Keep a separate SD card backup:** atomic writes do not protect against hardware failure or power loss.

## Delete an Automatic Savestate

Select a game, open **Automatic savestate > Check selected game**, verify the
path, and confirm that the game is closed and deletion is permanent. Then press
**Delete automatic savestate**. No save upload is needed.

**Only the selected game's `.state.auto` file is deleted, without a backup.**
SRAM saves, manual savestates, thumbnails, and other games remain untouched.
Missing, changed, unsafe, or ambiguous targets are not deleted. Keep the game
closed throughout the operation so RetroArch cannot recreate the file.

## Configuration

Edit [config.json](config.json) and restart the server:

| Setting | Default |
| --- | --- |
| `rom_root` | `/roms2` |
| `save_root` | `~/.config/retroarch/saves` |
| `state_root` | `~/.config/retroarch/states` |
| `systems` | Super Nintendo (`snes`) and PlayStation (`psx`) |

Relative paths are resolved from the configuration file's directory; `~`
refers to the user running the app. If `state_root` is omitted, the app uses
the `states` directory alongside `save_root`.

Save paths use the **immediate parent directory of the ROM** and the ROM's name
without its final extension. This assumes RetroArch sorting by content directory,
not by core, with saves stored outside the ROM directory. Overrides are not
detected automatically. For archives, multidisc games, and playlists, check the
actual path created by the emulator first.

To add systems, define their `label`, `rom_extensions`, and `save_extension` in
`systems`, after checking the core's format and path rules. Custom `save_root`
or `state_root` paths also require updating `ReadWritePaths` in
[packaging/r36s-saves-manager.service](packaging/r36s-saves-manager.service).
Restart the service if the default `states` directory is created after startup.

Use the header selector to change language; the browser remembers the choice.
For Italian terminal messages use `--language it`; for the console launcher,
set `R36S_LANGUAGE=it`. Both catalogs in `locales` are required.

## Security

**Use trusted networks only.** HTTP does not encrypt passwords or saves.
Do not expose the server to the Internet or enable port forwarding.
For encrypted access, start the server with `--host 127.0.0.1` and open an SSH
tunnel from your PC, replacing `CONSOLE_IP` with the console's address:

```bash
ssh -L 8765:127.0.0.1:8765 ark@CONSOLE_IP
```

Then open <http://127.0.0.1:8765>. Use IP addresses or `localhost`, not mDNS names
or custom domains. Never commit passwords or personal saves to Git.

## Updates and Removal

Rerun the deployment script or installer to update. The service stops during
installation; restart it afterward. Configuration and password are preserved
unless you explicitly publish a replacement configuration.

To uninstall the application while keeping saves, backups, configuration, and password:

```bash
sudo -n systemctl stop r36s-saves-manager.service
sudo -n rm /etc/systemd/system/r36s-saves-manager.service '/opt/system/Advanced/Saves Manager.sh'
sudo -n systemctl daemon-reload
rm -r /home/ark/.local/share/r36s-saves-manager
```

## Demo and Tests

With a local Python environment available:

```powershell
.\.venv\Scripts\python.exe R36SavesManager.py --demo
.\.venv\Scripts\python.exe -m unittest test_saves -v
```

The demo runs at <http://127.0.0.1:8765> without a password, using temporary
sample data instead of real ROMs or saves. Stop it with Ctrl+C before running
tests. Tests run locally without accessing the console.