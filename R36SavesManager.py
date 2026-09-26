# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///

import argparse
import getpass
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import shutil
import signal
import socket
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit


MAX_SAVE_BYTES = 16 * 1024 * 1024
TRANSLATIONS = {language: json.loads((Path(__file__).parent / "locales" / (language + ".json"))
                                   .read_text(encoding="utf-8")) for language in ("en", "it")}


def translate(key, language="en", **parameters):
    catalog = TRANSLATIONS.get(language, TRANSLATIONS["en"])
    return catalog.get(key, TRANSLATIONS["en"].get(key, key)).format(**parameters)


class SaveError(ValueError):
    def __init__(self, key, **parameters):
        self.key = key
        self.parameters = parameters
        super().__init__(translate(key, **parameters))


def safe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise SaveError("invalid_path")
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise SaveError("unsafe_path")
    return path


def fingerprint(path):
    if not path.exists():
        return "missing"
    if not path.is_file():
        raise SaveError("target_not_file")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


class SaveManager:
    def __init__(self, config_path):
        config_path = Path(config_path).resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))

        def root_path(value):
            path = Path(value).expanduser()
            return (config_path.parent / path).resolve()

        self.rom_root = root_path(config["rom_root"])
        self.save_root = root_path(config["save_root"])
        self.state_root = root_path(config.get("state_root", str(self.save_root.parent / "states")))
        self.systems = config["systems"]
        for identifier, settings in self.systems.items():
            if Path(identifier).name != identifier or identifier in {".", "..", ""}:
                raise SaveError("invalid_system_id")
            if settings["save_extension"] not in {".srm", ".sav"}:
                raise SaveError("invalid_save_format")
            if not settings["rom_extensions"]:
                raise SaveError("missing_rom_extensions")
        self.lock = threading.RLock()

    def system(self, identifier):
        if identifier not in self.systems:
            raise SaveError("unknown_system")
        return self.systems[identifier]

    def input_extensions(self, identifier):
        extension = self.system(identifier)["save_extension"]
        return [extension, ".mcd", ".mcr"] if identifier == "psx" and extension == ".srm" else [extension]

    def paths(self, identifier, relative_rom):
        settings = self.system(identifier)
        root = safe_path(self.rom_root, identifier).resolve()
        rom = safe_path(root, relative_rom)
        if not rom.is_file() or rom.suffix.lower() not in settings["rom_extensions"]:
            raise SaveError("rom_unavailable")
        target = safe_path(self.save_root, Path(rom.parent.name) / (rom.stem + settings["save_extension"]))
        return rom, target

    def library(self, identifier):
        settings = self.system(identifier)
        root = safe_path(self.rom_root, identifier)
        if not root.is_dir():
            raise SaveError("rom_folder_missing", path=str(root))
        records = []
        for folder, directories, filenames in os.walk(root, followlinks=False):
            directories[:] = [name for name in directories if not name.startswith(".")
                              and name not in {"images", "videos", "manuals"}]
            for filename in filenames:
                path = Path(folder) / filename
                if path.suffix.lower() in settings["rom_extensions"] and not path.is_symlink():
                    relative = path.relative_to(root).as_posix()
                    _, target = self.paths(identifier, relative)
                    records.append({"rom": relative, "name": path.stem,
                                    "saved": target.is_file()})
        return sorted(records, key=lambda record: record["rom"].casefold())

    def preview(self, identifier, relative_rom, extension):
        extensions = self.input_extensions(identifier)
        if extension.lower() not in extensions:
            raise SaveError("expected_format", extensions=", ".join(extensions))
        _, target = self.paths(identifier, relative_rom)
        if not self.save_root.is_dir():
            raise SaveError("save_folder_missing", path=str(self.save_root))
        for other_system in self.systems:
            other_root = safe_path(self.rom_root, other_system)
            if not other_root.is_dir():
                continue
            for record in self.library(other_system):
                if (other_system, record["rom"]) == (identifier, Path(relative_rom).as_posix()):
                    continue
                _, other_target = self.paths(other_system, record["rom"])
                if other_target == target:
                    raise SaveError("ambiguous_target")
        return {"destination": str(target), "exists": target.is_file(),
                "size": target.stat().st_size if target.is_file() else 0,
                "fingerprint": fingerprint(target)}

    def auto_state_path(self, identifier, relative_rom):
        rom, _ = self.paths(identifier, relative_rom)
        target = safe_path(self.state_root, Path(rom.parent.name) / (rom.stem + ".state.auto"))
        if target.parent.is_symlink():
            raise SaveError("unsafe_path")
        return target

    def preview_auto_state(self, identifier, relative_rom):
        target = self.auto_state_path(identifier, relative_rom)
        for other_system in self.systems:
            if not safe_path(self.rom_root, other_system).is_dir():
                continue
            for record in self.library(other_system):
                if (other_system, record["rom"]) == (identifier, Path(relative_rom).as_posix()):
                    continue
                if self.auto_state_path(other_system, record["rom"]) == target:
                    raise SaveError("auto_state_ambiguous")
        current = fingerprint(target)
        return {"destination": str(target), "exists": current != "missing", "fingerprint": current}

    def delete_auto_state(self, identifier, relative_rom, expected, closed=False, confirmed=False):
        with self.lock:
            if not closed:
                raise SaveError("confirm_closed")
            if not confirmed:
                raise SaveError("auto_state_confirm_required")
            preview = self.preview_auto_state(identifier, relative_rom)
            if not preview["exists"]:
                raise SaveError("auto_state_missing")
            if preview["fingerprint"] != expected:
                raise SaveError("auto_state_changed")
            target = self.auto_state_path(identifier, relative_rom)
            target.unlink()
            return {"destination": str(target), "deleted": True}

    def import_save(self, identifier, relative_rom, extension, data, expected, overwrite=False):
        if not data or len(data) > MAX_SAVE_BYTES:
            raise SaveError("save_size")
        with self.lock:
            preview = self.preview(identifier, relative_rom, extension)
            if extension.lower() in {".mcd", ".mcr"}:
                if len(data) != 131072 or data[:2] != b"MC":
                    raise SaveError("card_raw")
                checksum = 0
                for value in data[:127]:
                    checksum ^= value
                if checksum != data[127]:
                    raise SaveError("card_checksum")
            if preview["fingerprint"] != expected:
                raise SaveError("save_changed")
            if preview["exists"] and not overwrite:
                raise SaveError("confirm_overwrite")
            target = Path(preview["destination"])
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".r36s-upload-", dir=target.parent)
            backup = None
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                if preview["exists"]:
                    backup_dir = safe_path(self.save_root, target.parent.relative_to(self.save_root)
                                           / ".r36s-backups" / target.name)
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    backup = backup_dir / (stamp + "-" + uuid.uuid4().hex + ".bak")
                    with target.open("rb") as source, backup.open("xb") as output:
                        shutil.copyfileobj(source, output)
                        output.flush()
                        os.fsync(output.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {"destination": str(target), "backup": str(backup) if backup else None,
                    "bytes": len(data)}


class SaveServer(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, address, manager, password, demo=False):
        super().__init__(address, SaveHandler)
        self.manager = manager
        self.password_hash = hashlib.sha256(password.encode("utf-8")).digest()
        self.demo = demo
        self.sessions = {}
        self.attempts = {}
        self.auth_lock = threading.RLock()


class SaveHandler(BaseHTTPRequestHandler):
    server_version = "R36SavesManager/1.0"

    def setup(self):
        super().setup()
        assert isinstance(self.server, SaveServer)
        self.application = self.server
        self.connection.settimeout(20)

    def log_message(self, format, *arguments):
        pass

    def respond(self, status, body, content_type="application/json; charset=utf-8", headers=None):
        if isinstance(body, dict):
            if "error" in body:
                key = body["error"]
                parameters = body.get("parameters", {})
                body = dict(body, error=translate(key, self.headers.get("X-Language", "en"), **parameters),
                            error_key=key, parameters=parameters)
            body = json.dumps(body, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; "
                         "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def validate_origin(self):
        host = self.headers.get("Host", "")
        parsed = urlsplit("http://" + host)
        if not parsed.hostname or parsed.port != self.application.server_port or parsed.username or parsed.path:
            raise SaveError("host_denied")
        if parsed.hostname != "localhost":
            try:
                address = ipaddress.ip_address(parsed.hostname)
            except ValueError:
                raise SaveError("use_local_ip") from None
            if not (address.is_private or address.is_loopback):
                raise SaveError("local_only")
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + host:
            raise SaveError("origin_denied")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise SaveError("cross_site")

    def body(self, limit, content_type):
        if self.headers.get("Transfer-Encoding"):
            raise SaveError("transfer_unsupported")
        if self.headers.get_content_type() != content_type:
            raise SaveError("invalid_content_type")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= limit:
            raise SaveError("request_size")
        data = self.rfile.read(length)
        if len(data) != length:
            raise SaveError("upload_incomplete")
        return data

    def json_body(self):
        body = json.loads(self.body(16384, "application/json"))
        if not isinstance(body, dict):
            raise SaveError("invalid_json")
        return body

    def session(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except Exception:
            return None, None
        token = cookies.get("r36s_session")
        identifier = token.value if token else ""
        with self.application.auth_lock:
            now = time.monotonic()
            self.application.sessions = {key: value for key, value in self.application.sessions.items()
                                    if value["expires"] > now}
            session = self.application.sessions.get(identifier)
            if session:
                session["expires"] = now + 1800
            return identifier, session

    def new_session(self):
        identifier = secrets.token_urlsafe(32)
        session = {"csrf": secrets.token_urlsafe(32), "expires": time.monotonic() + 1800,
                   "preview": None}
        with self.application.auth_lock:
            if len(self.application.sessions) >= 64:
                self.application.sessions.pop(next(iter(self.application.sessions)))
            self.application.sessions[identifier] = session
        return session, {"Set-Cookie": "r36s_session=" + identifier
                         + "; HttpOnly; SameSite=Strict; Path=/; Max-Age=1800"}

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)

    def dispatch(self, post):
        try:
            self.validate_origin()
            self.route(post)
        except SaveError as error:
            self.respond(400, {"error": error.key, "parameters": error.parameters})
        except (ValueError, KeyError, TypeError):
            self.respond(400, {"error": "invalid_request"})
        except OSError:
            try:
                self.respond(503, {"error": "io_error"})
            except OSError:
                pass

    def route(self, post):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        identifier, session = self.session()
        if not post and url.path in {"/locales/en.json", "/locales/it.json"}:
            self.respond(200, TRANSLATIONS[url.path.split("/")[-1][:-5]])
            return
        if not post and url.path in {"/", "/app.js", "/console.png"}:
            filename, content_type = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/console.png": ("console.png", "image/png"),
            }[url.path]
            self.respond(200, Path(__file__).with_name(filename).read_bytes(), content_type)
            return
        if post and url.path == "/api/login":
            body = self.json_body()
            password = body.get("password", "")
            if not isinstance(password, str):
                raise SaveError("invalid_password")
            with self.application.auth_lock:
                now = time.monotonic()
                self.application.attempts = {key: value for key, value in self.application.attempts.items()
                                        if value[1] > now}
                count, expires = self.application.attempts.get(self.client_address[0], (0, now + 60))
                if count >= 5:
                    self.respond(429, {"error": "rate_limit"})
                    return
                if not hmac.compare_digest(hashlib.sha256(password.encode("utf-8")).digest(),
                                           self.application.password_hash):
                    self.application.attempts[self.client_address[0]] = (count + 1, expires)
                    self.respond(401, {"error": "wrong_password"})
                    return
                self.application.attempts.pop(self.client_address[0], None)
            if identifier:
                with self.application.auth_lock:
                    self.application.sessions.pop(identifier, None)
            session, headers = self.new_session()
            self.respond(200, {"csrf": session["csrf"]}, headers=headers)
            return
        if not post and url.path == "/api/session":
            headers = {}
            if self.application.demo and not session:
                session, headers = self.new_session()
            self.respond(200, {"authenticated": bool(session), "demo": self.application.demo,
                               "csrf": session["csrf"] if session else None}, headers=headers)
            return
        if not session:
            self.respond(401, {"error": "login_required"})
            return
        if post and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
            self.respond(403, {"error": "invalid_session"})
            return
        manager = self.application.manager
        if post and url.path == "/api/logout":
            with self.application.auth_lock:
                self.application.sessions.pop(identifier, None)
            self.respond(200, {}, headers={"Set-Cookie": "r36s_session=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/"})
        elif not post and url.path == "/api/systems":
            self.respond(200, {"systems": [dict(id=key, label=value["label"],
                                extension=value["save_extension"],
                                input_extensions=manager.input_extensions(key),
                                available=safe_path(manager.rom_root, key).is_dir())
                                for key, value in manager.systems.items()]})
        elif not post and url.path == "/api/roms":
            self.respond(200, {"roms": manager.library(query["system"][0])})
        elif post and url.path == "/api/auto-state/preview":
            body = self.json_body()
            with manager.lock:
                session["auto_state"] = None
                preview = manager.preview_auto_state(body["system"], body["rom"])
                ticket = secrets.token_urlsafe(24)
                session["auto_state"] = dict(system=body["system"], rom=body["rom"],
                                            expected=preview["fingerprint"], ticket=ticket,
                                            expires=time.monotonic() + 600)
            self.respond(200, dict(preview, ticket=ticket))
        elif post and url.path == "/api/auto-state/delete":
            body = self.json_body()
            with manager.lock:
                preview = session.get("auto_state")
                if not preview or preview["expires"] < time.monotonic():
                    raise SaveError("preview_expired")
                if body.get("ticket") != preview["ticket"]:
                    raise SaveError("preview_invalid")
                session["auto_state"] = None
                result = manager.delete_auto_state(preview["system"], preview["rom"], preview["expected"],
                                                   body.get("closed") is True, body.get("confirmed") is True)
            self.respond(200, result)
        elif post and url.path == "/api/preview":
            body = self.json_body()
            system, rom, extension = body["system"], body["rom"], body["extension"]
            with manager.lock:
                preview = manager.preview(system, rom, extension)
                ticket = secrets.token_urlsafe(24)
                session["preview"] = dict(system=system, rom=rom, extension=extension,
                                           expected=preview["fingerprint"], ticket=ticket,
                                           expires=time.monotonic() + 600)
            self.respond(200, dict(preview, ticket=ticket))
        elif post and url.path == "/api/import":
            data = self.body(MAX_SAVE_BYTES, "application/octet-stream")
            with manager.lock:
                preview = session.get("preview")
                if not preview or preview["expires"] < time.monotonic():
                    raise SaveError("preview_expired")
                if query.get("ticket", [""])[0] != preview["ticket"]:
                    raise SaveError("preview_invalid")
                if query.get("closed", [""])[0] != "yes":
                    raise SaveError("confirm_closed")
                session["preview"] = None
                result = manager.import_save(preview["system"], preview["rom"], preview["extension"],
                                              data, preview["expected"], query.get("overwrite") == ["yes"])
            result["backup_id"] = Path(result["backup"]).name if result["backup"] else None
            self.respond(200, result)
        elif not post and url.path in {"/api/save", "/api/backup"}:
            _, target = manager.paths(query["system"][0], query["rom"][0])
            path = target
            if url.path == "/api/backup":
                backup_root = safe_path(manager.save_root, target.parent.relative_to(manager.save_root)
                                         / ".r36s-backups" / target.name)
                path = safe_path(backup_root.resolve(), query["name"][0])
                if path.parent != backup_root or path.suffix != ".bak":
                    raise SaveError("invalid_backup")
            with manager.lock:
                with path.open("rb") as source:
                    data = source.read(MAX_SAVE_BYTES + 1)
                if len(data) > MAX_SAVE_BYTES:
                    raise SaveError("download_too_large")
            self.respond(200, data, "application/octet-stream", {
                "Content-Disposition": "attachment; filename*=UTF-8''" + quote(target.name, safe="")})
        else:
            self.respond(404, {"error": "not_found"})


def demo_config(folder):
    root = Path(folder)
    roms = root / "roms" / "snes"
    saves = root / "saves" / "snes"
    states = root / "states" / "snes"
    roms.mkdir(parents=True)
    saves.mkdir(parents=True)
    states.mkdir(parents=True)
    names = ["Legend of Zelda, The - A Link to the Past (USA)",
             "Final Fantasy II (USA) (Rev 1)", "Super Mario World (USA)"]
    for name in names:
        (roms / (name + ".zip")).write_bytes(b"R36S demo placeholder, not a ROM")
    (saves / (names[0] + ".srm")).write_bytes(bytes(range(256)) * 32)
    (states / (names[0] + ".state.auto")).write_bytes(b"Synthetic automatic savestate")
    (states / (names[0] + ".state1")).write_bytes(b"Synthetic manual savestate")
    config = root / "config.json"
    config.write_text(json.dumps({"rom_root": "roms", "save_root": "saves", "state_root": "states", "systems": {
        "snes": {"label": "Super Nintendo", "rom_extensions": [".zip", ".sfc", ".smc", ".7z"],
                 "save_extension": ".srm"}}}), encoding="utf-8")
    return config


def read_password(password_file=None, language="en"):
    if password_file is not None:
        password = Path(password_file).read_text(encoding="utf-8").rstrip("\r\n")
    else:
        password = os.environ.get("R36S_PASSWORD", "")
        if not password:
            if not sys.stdin.isatty():
                raise SaveError("password_required")
            password = getpass.getpass(translate("password_prompt", language))
    if len(password) < 8 or "\n" in password or "\r" in password:
        raise SaveError("password_rules")
    return password


def set_password(password_file, language="en"):
    if password_file is None or not sys.stdin.isatty():
        raise SaveError("password_setup_usage")
    password = getpass.getpass(translate("password_new", language))
    confirmation = getpass.getpass(translate("password_repeat", language))
    if password != confirmation:
        raise SaveError("password_mismatch")
    if len(password) < 8 or "\n" in password or "\r" in password:
        raise SaveError("password_rules")
    path = Path(password_file).expanduser()
    if path.is_symlink():
        raise SaveError("password_symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".password-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(password + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(translate("password_set", language))


def request_stop(signum, frame):
    raise KeyboardInterrupt


def notify_ready():
    address = os.environ.get("NOTIFY_SOCKET")
    if address:
        unix_family = getattr(socket, "AF_UNIX", None)
        if unix_family is None:
            raise SaveError("systemd_unavailable")
        if address.startswith("@"):
            address = "\0" + address[1:]
        with socket.socket(unix_family, socket.SOCK_DGRAM) as notification:
            notification.sendto(b"READY=1", address)


def main():
    language_parser = argparse.ArgumentParser(add_help=False)
    language_option = language_parser.add_argument("--language", choices=tuple(TRANSLATIONS), default="en")
    language = language_parser.parse_known_args()[0].language
    parser = argparse.ArgumentParser(description=translate("cli_description", language), parents=[language_parser])
    language_option.help = translate("cli_language", language)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--demo", action="store_true", help=translate("cli_demo", language))
    parser.add_argument("--password-file", type=Path, help=translate("cli_password_file", language))
    parser.add_argument("--set-password", action="store_true", help=translate("cli_set_password", language))
    arguments = parser.parse_args()
    temporary = None
    try:
        if arguments.set_password:
            set_password(arguments.password_file, language)
            return
        if arguments.demo:
            temporary = tempfile.TemporaryDirectory(prefix="r36s-demo-")
            config = demo_config(temporary.name)
            password = secrets.token_urlsafe(32)
            host = "127.0.0.1"
        else:
            config = arguments.config
            host = arguments.host
            password = read_password(arguments.password_file, language)
        manager = SaveManager(config)
        signal.signal(signal.SIGTERM, request_stop)
        with SaveServer((host, arguments.port), manager, password, arguments.demo) as server:
            label = translate("cli_demo_label" if arguments.demo else "cli_http_label", language)
            print("R36S Saves Manager: http://{}:{} ({})".format(host, server.server_port, label), flush=True)
            print(translate("cli_stop", language), flush=True)
            notify_ready()
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, KeyError) as error:
        message = translate(error.key, language, **error.parameters) if isinstance(error, SaveError) else str(error)
        parser.exit(1, translate("cli_failed", language, error=message) + "\n")
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    main()
