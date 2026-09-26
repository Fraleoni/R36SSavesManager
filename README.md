# R36S Saves Manager

[Italian documentation](README-it.md)

A local web interface, available in English and Italian, for importing RetroArch SRAM saves
onto the R36S. Requires Python >= 3.9, with no external packages, CDNs, or Internet access.
Python 3.13.5 and the paths below have been verified on the console via SSH.

## Languages

The default language is **English**. The selector in the header lets you switch to
**Italiano** without reloading the page or losing the selected file, preview, or
confirmations. Your choice is remembered in this browser using `localStorage`;
if storage is unavailable, it remains valid for the current page.
ROM names, filenames, configured system names, and paths are not translated.

The [locales/en.json](locales/en.json) and [locales/it.json](locales/it.json)
catalogs contain interface strings, API errors, Python messages, and Advanced
menu messages. Keep the same keys and brace-delimited parameters, such as
`{size}`. Missing Italian keys fall back to English. Do not include HTML in
translations. Catalog changes require a server restart.
Both files must be deployed in the `locales` subdirectory.

The API accepts `X-Language: en` or `X-Language: it`; missing or unsupported
values fall back to English. Errors include `error` (text), `error_key`
(a stable key), and `parameters`, allowing the page to translate them again
after receiving the response.

For Python messages, use `--language it`, including with `--set-password`.
For the launcher, set `R36S_LANGUAGE=it` in its environment, for example:

```bash
R36S_LANGUAGE=it bash '/opt/system/Advanced/Saves Manager.sh' --status
```

The browser language is independent of the terminal and console menu language.
The installation and deployment tools display messages in English; native
messages from the browser, operating system, argparse, SSH, and systemd depend
on those tools.

## Initial Configuration

The [config.json](config.json) file enables **Super Nintendo** and **PlayStation**.
For Super Nintendo:

- ROMs: `/roms2/snes/`
- Saves: `/home/ark/.config/retroarch/saves/snes/`
- Input and output format: `.srm`
- Default port: `8765`, configurable with `--port`.

For PlayStation: ROMs are in `/roms2/psx/`, per-game saves are in
`/home/ark/.config/retroarch/saves/psx/`, and the destination is `<ROM name>.srm`.
Accepted inputs are `.srm` files and raw `.mcd` / `.mcr` images. For the latter
two formats, the application checks the exact size of 131072 bytes (128 KiB),
the `MC` signature, and the header XOR checksum (the first 128-byte frame).
Bytes are preserved without conversion or header removal.
These checks do not guarantee the integrity of individual saves within the
card or compatibility with the game's region and revision.

A PSX import replaces **the game's entire memory card**, not a single slot.
The previous card is backed up when you confirm replacement.
The shared second card, `pcsx-card2.mcd`, is not a destination managed by this tool.
Select PlayStation before choosing or dragging a `.mcd` / `.mcr` file.

The settings observed in both RetroArch and RetroArch32 are:
`sort_savefiles_by_content_enable = "true"`, `sort_savefiles_enable = "false"`,
`savefiles_in_content_dir = "false"`.
The application follows this rule; it does not automatically read overrides.
For a ROM in a subdirectory, it uses the name of the **directory immediately
containing the ROM**, not the full relative path. For example:

```text
/roms2/snes/Collection/Game.zip
-> /home/ark/.config/retroarch/saves/Collection/Game.srm
```

Absolute and relative paths are configurable; relative paths are resolved from
the JSON file's directory. `~` refers to the user running the application:
on the console, run it as **ark**, not with sudo.

## Try It on a PC

```powershell
.\.venv\Scripts\python.exe R36SavesManager.py --demo
```

Open <http://127.0.0.1:8765>. Demo mode listens on loopback only and does not
require a password. It creates three placeholder ROMs, a synthetic 8 KiB save,
and two synthetic savestates (automatic and manual) in a temporary directory,
without reading `/roms2` or real saves.
Temporary data is removed on normal shutdown with Ctrl+C.
The demo contains no playable ROMs or original game saves.

## Installation with the Advanced Menu

### Deploy from Windows

Run [packaging/deploy.ps1](packaging/deploy.ps1) from PowerShell:

```powershell
.\packaging\deploy.ps1
```

The script asks for the IPv4 address, SSH user (default: `ark`), whether to
publish the configuration, and whether to start the service afterward. It asks
for confirmation before connecting: deployment stops the web service and
invalidates open sessions. Finish any imports before proceeding.

OpenSSH requests the login password directly using hidden input; it is neither
saved nor passed on the command line. Verification, transfer, and installation
use **a single SSH connection**, so you only need to enter it once. If the
password is incorrect, the script exits and must be run again; existing SSH
keys are used normally. On the first connection, verify the console's
fingerprint before accepting it.
The application's web password is separate and is not changed.

Requires Windows PowerShell 5.1 or PowerShell 7, the native Windows OpenSSH
client, and native Windows `tar.exe`. The console must support `sudo -n`
without prompts, as in the verified dArkOSen configuration. The requested user
is used for authentication: the installation layout and service user remain
`/home/ark` and `ark`.

Explicit options, still requiring confirmation before deployment:

```powershell
.\packaging\deploy.ps1 -ConsoleIp 192.168.1.43 -SshUser ark -PublishConfig -StartService
```

`-PublishConfig` publishes the entire local [config.json](config.json), including
new profiles. Before replacing the remote configuration, it creates a private
backup named `config.json.before-<release-id>.bak`. Without this option, or if
you answer No at the prompt, the existing configuration is preserved. Profiles
are not merged: check any remote customizations first.
Without the final start step, the service remains stopped; startup at boot is
never enabled.

To check the package and display the commands without connecting:

```powershell
.\packaging\deploy.ps1 -ConsoleIp 192.168.1.43 -SshUser ark -DryRun
```

The transfer includes only the required runtime/installer files and catalogs,
sent as Base64 over SSH standard input, with SHA256 verification on the console
before extraction. Encoding prevents byte corruption even in Windows
PowerShell 5.1; it does not replace SSH encryption.
Passwords, ROMs, saves, and virtual environments are not included.
Local temporary files are removed even on failure; if the transfer is
interrupted before installation, any remaining remote temporary path is
reported. An error stops deployment without reporting success; automatic
rollback is not provided.

### Manual Installation

The [packaging/install.sh](packaging/install.sh) package installs a system unit
that runs Python as `ark`, independently of the SSH session and menu.
It does not start the server or enable startup at boot. It requires the dArkOSen
layout verified in [CONSOLE_NOTES.md](CONSOLE_NOTES.md), `systemd`, `dialog`, and
`/opt/inttools/gptokeyb`.

Transfer the runtime files and catalogs listed in the manual startup section
below, along with the `packaging` directory, to the console, preserving the
directory structure. From the transferred directory, run:

```bash
sudo -n bash packaging/install.sh
```

Destinations:

```text
/home/ark/.local/share/r36s-saves-manager/   code and assets
/home/ark/.config/r36s-saves-manager/       config.json and password
/etc/systemd/system/r36s-saves-manager.service
/opt/system/Advanced/Saves Manager.sh
```

Set the web password from an interactive SSH terminal **as ark**, not with
sudo. Enter it only at the hidden prompts, never on the command line or in chat:

```bash
python3 /home/ark/.local/share/r36s-saves-manager/R36SavesManager.py \
  --set-password --password-file /home/ark/.config/r36s-saves-manager/password
```

The password must contain at least 8 characters and differ from the SSH password.
The file is written atomically with `0600` permissions inside the private `0700`
directory; it contains the password in plaintext and is readable by `ark` and
root. Run the command again to change it, then stop and restart the service.

Reopen **Advanced > Saves Manager**: **Start**, **Status**, **Stop**.
Start waits for systemd's READY notification and checks HTTP before displaying
the address. Leaving the menu keeps the server running. The menu entry's
visibility, display layout, and buttons must be checked on the console; do not
automatically restart the frontend to force a menu refresh.

The same controls are available over SSH without starting the gamepad mapper:

```bash
bash '/opt/system/Advanced/Saves Manager.sh' --start
bash '/opt/system/Advanced/Saves Manager.sh' --status
bash '/opt/system/Advanced/Saves Manager.sh' --stop
journalctl -u r36s-saves-manager.service -n 30 --no-pager
```

Open the displayed address, usually <http://192.168.1.43:8765>.
The port is `8765`; if it is already in use, startup fails. The process using
it is not terminated. The unit has no Install section and should not be enabled
at boot. Shutdown waits for ongoing requests, with a systemd limit of 90 seconds;
after that limit, the process is forcibly terminated.

To update, transfer the new package and run the installer again: the service is
stopped, code and launcher are replaced, and configuration and password are
preserved. Restart it explicitly. The service's write access is restricted to
the default save directory and its own temporary space, plus the savestate
directory described below. Changing `save_root` requires updating
`ReadWritePaths` in the unit as well as the JSON configuration.
The same applies to `state_root`: the unit also allows writes to
`/home/ark/.config/retroarch/states` if it exists when the service starts.

To uninstall without deleting saves, backups, configuration, or password:

```bash
sudo -n systemctl stop r36s-saves-manager.service
sudo -n rm /etc/systemd/system/r36s-saves-manager.service '/opt/system/Advanced/Saves Manager.sh'
sudo -n systemctl daemon-reload
rm -r /home/ark/.local/share/r36s-saves-manager
```

The private directory containing the configuration and credential is kept for
reinstallation. Firmware updates may remove the launcher.

## Alternative Manual Startup

Copy these files to the console, preserving the `locales` subdirectory:

- [R36SavesManager.py](R36SavesManager.py)
- [config.json](config.json)
- [index.html](index.html)
- [app.js](app.js)
- [console.png](console.png)
- [locales/en.json](locales/en.json)
- [locales/it.json](locales/it.json)

Start from the console or over SSH as user `ark`:

```bash
python3 R36SavesManager.py --host 0.0.0.0 --port 8765
```

At the prompt, set a password containing at least 8 characters, different from
the SSH password. The password is not saved to disk. Alternatively, the process
can receive it through the `R36S_PASSWORD` environment variable; do not put it
in source code or Git.

From a PC or phone on the same network, open <http://192.168.1.43:8765> and log in.
The IP address may change if assigned through DHCP. The server runs in the
foreground: closing the SSH session may stop it. This mode does not install
services. If the port is already in use, choose another one with `--port`.

**Trusted networks only:** HTTP does not encrypt passwords or saves. Do not
expose the service to the Internet or configure port forwarding. Python's
standard server is suitable for this local use, not for a public service.
For an encrypted connection, start it with `--host 127.0.0.1` and use an SSH
tunnel from your PC:

```bash
ssh -L 8765:127.0.0.1:8765 ark@192.168.1.43
```

With the tunnel open, use <http://127.0.0.1:8765>. The service accepts local IP
addresses or `localhost`, not mDNS names or custom domains. Login expires after
30 minutes; five incorrect passwords block new attempts from that IP until
the end of the one-minute window.

## Delete an Automatic Savestate

Select the game in the library, then choose **Automatic savestate > Check selected game**
(in Italian, **Savestate automatico > Controlla gioco selezionato**).
You do not need to upload an SRAM file. Check the displayed path, confirm that
the game is closed, and accept permanent deletion, then press
**Delete automatic savestate** / **Cancella savestate automatico**.

Only `<ROM name>.state.auto` is deleted, without a backup. For example:

```text
/roms2/psx/Alundra (USA).chd
-> ~/.config/retroarch/states/psx/Alundra (USA).state.auto
```

Files such as `.srm`, `.sav`, `.state`, `.state1`, `.state.auto.png` images, and
other games' savestates remain unchanged. If the file is missing, nothing is
deleted. The server requires authentication, CSRF protection, two confirmations,
and a single-use ticket valid for ten minutes; it rejects ambiguous
destinations, symbolic links, and content changed after the check.
Changing the selected ROM clears the confirmations.

`state_root` in [config.json](config.json) specifies the savestate directory.
For older configurations without this key, the `states` directory alongside
`save_root` is used. Mapping uses the name of the directory immediately
containing the ROM, just as for SRAM saves. Check that this matches the
RetroArch settings: custom directories, sorting by core, and overrides are
not detected automatically. The game must be closed: the app cannot prevent
RetroArch from recreating or modifying the file during the operation.

To enable permission in the installed unit, redeploy the package using the
installer and restart the service. You do not need to republish the
configuration if you use the default paths. If the `states` directory is
created while the service is already running, restart it to make the directory
writable.

## Import Saves

1. Close the game on the console. The application cannot prevent an emulator
   that is still running from overwriting the save afterward.
2. Select the system and ROM. Search includes region, revision, and subdirectory.
3. Select or drag a single `.srm` or `.sav` file onto the page
   (for PSX, raw 128 KiB `.mcd` / `.mcr` files are also accepted).
   The file must be nonempty and no larger than 16 MiB. Drag and drop is
   available after login when no operation is in progress. It does not start
   the import automatically. If the filename exactly matches a single ROM,
   that ROM is selected automatically.
4. Open the preview and check the destination. The uploaded file's original
   name is not used as a path: the selected ROM determines the destination.
5. Confirm that the game is closed and, if necessary, approve replacement.
   Import the save.

The preview expires after ten minutes and can only be used once. If the save
changes after the preview, the import is rejected. Ambiguous destinations
among ROMs in the configured directories are rejected rather than silently
choosing one. Import preserves the file's bytes: it does not interpret or
convert the format.

Before each replacement, the previous file is copied to:

```text
<save directory>/.r36s-backups/<ROM name>.srm/<UTC date>-<id>.bak
```

Writing uses a temporary file in the same directory and an atomic replacement.
If backup creation fails, the save is not replaced. This does not replace an
external backup of the SD card or protect against hardware failure or power
loss. Backups are not deleted automatically.

The current save can be downloaded from the preview; immediately after import,
you can download the previous backup, already renamed to `.srm` for reimport.
Older backups remain on the SD card even after the page is closed. To recover
one manually, copy it to your PC and restore the `.srm` extension (or `.sav`,
depending on the system) before uploading it. A backup history management page
is not included.

## Compatibility and Other Systems

The 8 KiB PocketSNES Zelda file appears likely to be a compatible SRAM save,
but it has not been imported or tested in-game. Use the same ROM, region, and
revision. Automated tests use synthetic data, not the supplied file.

- Importing `.state` savestates, format conversion, exports with headers,
  shared memory card destinations, `.bin` files, and saves from standalone
  emulators are not supported. Raw `.mcd` / `.mcr` files are accepted only as
  PSX inputs targeting the game's `.srm` file, with the checks described above.
- A `.sav` file is not automatically renamed to `.srm`: except for PSX
  `.mcd` / `.mcr` inputs, the source extension and configured format must match.
  A correct extension does not prove that the content is valid; the game's
  internal checksum is not checked.
- For archives with different internal names, multidisc games, playlists, and
  specific overrides, first check the path of a save produced by the emulator.
  The application uses the archive's name without its final extension.
- Do not change RetroArch's sorting settings without updating the manager.
  Automatic detection of cores and their overrides is not implemented.

To add a system, add an entry to `systems` and restart. For example,
**after verifying that the GBA core uses `.srm` and the same path rule**:

```json
"gba": {
  "label": "Game Boy Advance",
  "rom_extensions": [".gba", ".zip", ".7z"],
  "save_extension": ".srm"
}
```

## Local Checks

```powershell
.\.venv\Scripts\python.exe -m unittest test_saves -v
```

Tests cover byte-for-byte integrity, renaming, subdirectories, ambiguous names,
backups, changes after preview, write failures, unsafe paths, login, CSRF,
import/download APIs, the private password file, simulated systemd notification,
and waiting for requests during shutdown. PSX tests cover `.mcd` / `.mcr`
inputs, raw validation through the API, backups, and preserving the shared card.
No test accesses the console.