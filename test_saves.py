import http.client
import json
import threading
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from string import Formatter
from unittest.mock import patch

from R36SavesManager import TRANSLATIONS, SaveError, SaveManager, SaveServer, fingerprint, notify_ready, read_password, set_password, translate


class TranslationTests(unittest.TestCase):
    def test_catalog_keys_and_parameters_match(self):
        english = TRANSLATIONS["en"]
        italian = TRANSLATIONS["it"]
        self.assertEqual(english.keys(), italian.keys())
        for key, text in english.items():
            with self.subTest(key=key):
                self.assertIsInstance(text, str)
                self.assertIsInstance(italian[key], str)
                self.assertTrue(text.strip())
                self.assertTrue(italian[key].strip())
                parameters = {name for _, name, _, _ in Formatter().parse(text) if name}
                self.assertEqual(parameters, {name for _, name, _, _ in Formatter().parse(italian[key]) if name})

    def test_english_fallback_and_unmodified_parameters(self):
        self.assertEqual(translate("unknown_system"), "Unknown system.")
        self.assertEqual(translate("unknown_system", "it"), "Sistema non riconosciuto.")
        self.assertEqual(translate("unknown_system", "../config"), translate("unknown_system"))
        with patch.dict(TRANSLATIONS, {"it": {}}):
            self.assertEqual(translate("unknown_system", "it"), translate("unknown_system"))
        path = "/roms2/<Game>/{name}"
        self.assertIn(path, translate("rom_folder_missing", "it", path=path))

    def test_html_translation_keys_exist(self):
        keys = []

        class TranslationParser(HTMLParser):
            def handle_starttag(self, tag, attributes):
                keys.extend(value for name, value in attributes if name.startswith("data-i18n"))

        parser = TranslationParser()
        parser.feed(Path(__file__).with_name("index.html").read_text(encoding="utf-8"))
        self.assertGreater(len(keys), 20)
        for key in keys:
            self.assertIn(key, TRANSLATIONS["en"])


class SaveManagerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "roms" / "snes").mkdir(parents=True)
        (self.root / "saves").mkdir()
        self.rom = "Legend of Zelda, The - A Link to the Past (USA).zip"
        (self.root / "roms" / "snes" / self.rom).write_bytes(b"demo rom")
        config = self.root / "config.json"
        config.write_text(json.dumps({"rom_root": "roms", "save_root": "saves", "systems": {
            "snes": {"label": "Super Nintendo", "save_extension": ".srm",
                     "rom_extensions": [".zip", ".sfc"]}}}), encoding="utf-8")
        self.manager = SaveManager(config)
        self.target = self.root / "saves" / "snes" / (Path(self.rom).stem + ".srm")

    def import_save(self, data=b"new", overwrite=False, expected=None):
        if expected is None:
            expected = fingerprint(self.target)
        return self.manager.import_save("snes", self.rom, ".srm", data, expected, overwrite)

    def test_exact_rom_name_and_8k_content(self):
        data = bytes(range(256)) * 32
        result = self.import_save(data)
        self.assertEqual(Path(result["destination"]), self.target)
        self.assertEqual(self.target.read_bytes(), data)
        self.assertIsNone(result["backup"])

    def test_delete_only_selected_auto_state(self):
        self.import_save(b"keep SRAM")
        target = self.root / "states" / "snes" / (Path(self.rom).stem + ".state.auto")
        target.parent.mkdir(parents=True)
        target.write_bytes(b"automatic state")
        preserved = [target.parent / (Path(self.rom).stem + suffix)
                     for suffix in (".state", ".state1", ".state.auto.png", ".state.auto.bak")]
        preserved.append(target.parent / "Other game.state.auto")
        for path in preserved:
            path.write_bytes(b"keep state")
        preview = self.manager.preview_auto_state("snes", self.rom)
        self.assertEqual(Path(preview["destination"]), target)
        for closed, confirmed in ((False, False), (True, False), (False, True)):
            with self.assertRaises(SaveError):
                self.manager.delete_auto_state("snes", self.rom, preview["fingerprint"], closed, confirmed)
            self.assertTrue(target.exists())
        result = self.manager.delete_auto_state("snes", self.rom, preview["fingerprint"], True, True)
        self.assertTrue(result["deleted"])
        self.assertFalse(target.exists())
        self.assertEqual(self.target.read_bytes(), b"keep SRAM")
        for path in preserved:
            self.assertEqual(path.read_bytes(), b"keep state")

    def test_auto_state_changed_missing_and_ambiguous(self):
        preview = self.manager.preview_auto_state("snes", self.rom)
        self.assertFalse(preview["exists"])
        target = Path(preview["destination"])
        target.parent.mkdir(parents=True)
        target.write_bytes(b"new state")
        with self.assertRaises(SaveError) as caught:
            self.manager.delete_auto_state("snes", self.rom, preview["fingerprint"], True, True)
        self.assertEqual(caught.exception.key, "auto_state_changed")
        (self.root / "roms" / "snes" / (Path(self.rom).stem + ".sfc")).write_bytes(b"duplicate")
        with self.assertRaises(SaveError) as caught:
            self.manager.preview_auto_state("snes", self.rom)
        self.assertEqual(caught.exception.key, "auto_state_ambiguous")
        self.assertEqual(target.read_bytes(), b"new state")

    def test_auto_state_psx_nested_and_configured_root(self):
        config_path = self.root / "config.json"
        config = json.loads(config_path.read_text())
        config["state_root"] = "custom-states"
        config["systems"]["psx"] = {"label": "PlayStation", "rom_extensions": [".chd"], "save_extension": ".srm"}
        config_path.write_text(json.dumps(config), encoding="utf-8")
        manager = SaveManager(config_path)
        folder = self.root / "roms" / "psx"
        folder.mkdir()
        (folder / "Alundra (USA).chd").write_bytes(b"rom")
        self.assertEqual(manager.auto_state_path("psx", "Alundra (USA).chd"),
                         self.root / "custom-states" / "psx" / "Alundra (USA).state.auto")
        (folder / "Collection").mkdir()
        (folder / "Collection" / "Game.rev1.chd").write_bytes(b"rom")
        self.assertEqual(manager.auto_state_path("psx", "Collection/Game.rev1.chd"),
                         self.root / "custom-states" / "Collection" / "Game.rev1.state.auto")
        for rom in ("../outside.chd", str(folder / "Alundra (USA).chd"), "missing.chd"):
            with self.assertRaises(SaveError):
                manager.delete_auto_state("psx", rom, "missing", True, True)

    def test_auto_state_symlinks_and_directory_rejected(self):
        target = self.manager.auto_state_path("snes", self.rom)
        target.parent.mkdir(parents=True)
        outside = self.root / "outside.state.auto"
        outside.write_bytes(b"keep outside")
        try:
            target.symlink_to(outside)
        except OSError:
            self.skipTest("Symbolic links unavailable")
        with self.assertRaises(SaveError):
            self.manager.delete_auto_state("snes", self.rom, fingerprint(outside), True, True)
        self.assertEqual(outside.read_bytes(), b"keep outside")
        target.unlink()
        target.mkdir()
        with self.assertRaises(SaveError):
            self.manager.preview_auto_state("snes", self.rom)
        target.rmdir()
        target.parent.rmdir()
        other_folder = self.root / "states" / "other"
        other_folder.mkdir()
        (other_folder / target.name).write_bytes(b"keep internal linked file")
        target.parent.symlink_to(other_folder, target_is_directory=True)
        with self.assertRaises(SaveError):
            self.manager.preview_auto_state("snes", self.rom)
        self.assertEqual((other_folder / target.name).read_bytes(), b"keep internal linked file")

    def test_overwrite_requires_confirmation_and_keeps_original(self):
        self.import_save(b"original")
        with self.assertRaises(SaveError):
            self.import_save()
        result = self.import_save(overwrite=True)
        self.assertEqual(Path(result["backup"]).read_bytes(), b"original")
        self.assertEqual(self.target.read_bytes(), b"new")

    def test_changed_save_requires_new_preview(self):
        self.import_save(b"original")
        expected = fingerprint(self.target)
        self.target.write_bytes(b"changed")
        with self.assertRaisesRegex(SaveError, "changed"):
            self.import_save(overwrite=True, expected=expected)
        self.assertEqual(self.target.read_bytes(), b"changed")

    def test_invalid_paths_formats_and_sizes(self):
        for rom, extension in [("../outside.zip", ".srm"), (self.rom, ".sav"),
                               ("missing.zip", ".srm"), (str(self.root / "x.zip"), ".srm")]:
            with self.subTest(rom=rom, extension=extension), self.assertRaises(SaveError):
                self.manager.preview("snes", rom, extension)
        for data in [b"", b"a" * (16 * 1024 * 1024 + 1)]:
            with self.assertRaises(SaveError):
                self.import_save(data)

    def test_nested_rom_uses_immediate_parent(self):
        folder = self.root / "roms" / "snes" / "Collection"
        folder.mkdir()
        (folder / "Game.sfc").write_bytes(b"rom")
        result = self.manager.preview("snes", "Collection/Game.sfc", ".srm")
        self.assertEqual(Path(result["destination"]), self.root / "saves" / "Collection" / "Game.srm")

    def test_psx_card_import_preserves_shared_slot_and_backup(self):
        config = json.loads(Path(__file__).with_name("config.json").read_text(encoding="utf-8"))
        self.manager.systems["psx"] = config["systems"]["psx"]
        rom_folder = self.root / "roms" / "psx"
        rom_folder.mkdir()
        rom_name = "Final Fantasy Origins.PBP"
        (rom_folder / rom_name).write_bytes(b"synthetic rom")
        save_folder = self.root / "saves" / "psx"
        save_folder.mkdir()
        shared_card = save_folder / "pcsx-card2.mcd"
        shared_card.write_bytes(b"shared card")
        target = save_folder / "Final Fantasy Origins.srm"
        original = b"A" * 131072
        incoming = b"B" * 131072
        target.write_bytes(original)
        preview = self.manager.preview("psx", rom_name, ".srm")
        self.assertEqual(Path(preview["destination"]), target)
        self.assertEqual(preview["size"], 131072)
        with self.assertRaises(SaveError):
            self.manager.import_save("psx", rom_name, ".srm", incoming, preview["fingerprint"])
        result = self.manager.import_save("psx", rom_name, ".srm", incoming, preview["fingerprint"], True)
        self.assertEqual(target.read_bytes(), incoming)
        self.assertEqual(Path(result["backup"]).read_bytes(), original)
        self.assertEqual(shared_card.read_bytes(), b"shared card")

        card = bytearray(131072)
        card[:2] = b"MC"
        card[127] = ord("M") ^ ord("C")
        card[8192:] = b"P" * (131072 - 8192)
        for extension in (".mcd", ".MCR"):
            with self.subTest(extension=extension):
                preview = self.manager.preview("psx", rom_name, extension)
                previous = target.read_bytes()
                with self.assertRaises(SaveError):
                    self.manager.import_save("psx", rom_name, extension, card, preview["fingerprint"])
                result = self.manager.import_save("psx", rom_name, extension, card, preview["fingerprint"], True)
                self.assertEqual(target.read_bytes(), card)
                self.assertEqual(Path(result["backup"]).read_bytes(), previous)
                self.assertEqual(shared_card.read_bytes(), b"shared card")
                with self.assertRaises(SaveError):
                    self.manager.preview("snes", self.rom, extension)

        bad_checksum = bytearray(card)
        bad_checksum[127] ^= 1
        before = {path.relative_to(save_folder): path.read_bytes()
                  for path in save_folder.rglob("*") if path.is_file()}
        for extension in (".mcd", ".mcr"):
            for invalid in (card[:-1], card + b"extra", b"header" + card, b"XX" + card[2:], bad_checksum):
                with self.subTest(extension=extension, size=len(invalid)), self.assertRaises(SaveError):
                    self.manager.import_save("psx", rom_name, extension, invalid, fingerprint(target), True)
        after = {path.relative_to(save_folder): path.read_bytes()
                 for path in save_folder.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_duplicate_target_is_rejected(self):
        (self.root / "roms" / "snes" / (Path(self.rom).stem + ".sfc")).write_bytes(b"rom")
        with self.assertRaisesRegex(SaveError, "Ambiguous"):
            self.manager.preview("snes", self.rom, ".srm")

    def test_replace_failure_preserves_original_and_cleans_temporary(self):
        self.import_save(b"original")
        with patch("R36SavesManager.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                self.import_save(overwrite=True)
        self.assertEqual(self.target.read_bytes(), b"original")
        self.assertFalse(list(self.target.parent.glob(".r36s-upload-*")))

    def test_symlink_escape_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.root / "saves" / "snes").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creazione symlink non consentita su questo sistema")
        with self.assertRaises(SaveError):
            self.import_save()


class WebTests(SaveManagerTests):
    def setUp(self):
        super().setUp()
        self.server = SaveServer(("127.0.0.1", 0), self.manager, "test-password")
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.cookie = ""
        self.csrf = ""

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        supplied = {"Cookie": self.cookie, "X-CSRF-Token": self.csrf}
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            supplied["Content-Type"] = "application/json"
        supplied.update(headers or {})
        connection.request(method, path, body, supplied)
        response = connection.getresponse()
        data = response.read()
        result = response.status, data, dict(response.getheaders())
        connection.close()
        return result

    def login(self):
        status, data, headers = self.request("POST", "/api/login", {"password": "test-password"})
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.csrf = json.loads(data)["csrf"]

    def test_authentication_csrf_and_origin(self):
        self.assertEqual(self.request("GET", "/api/systems")[0], 401)
        self.assertEqual(self.request("POST", "/api/login", {"password": "wrong"})[0], 401)
        self.login()
        self.assertEqual(self.request("GET", "/api/systems")[0], 200)
        self.assertEqual(self.request("POST", "/api/preview", {}, {"X-CSRF-Token": "wrong"})[0], 403)
        self.assertEqual(self.request("GET", "/api/systems", headers={"Origin": "http://evil.test"})[0], 400)
        self.assertEqual(self.request("GET", "/api/systems", headers={"Host": "evil.test:8765"})[0], 400)

    def test_auto_state_http_confirmations_and_no_replay(self):
        target = self.manager.auto_state_path("snes", self.rom)
        target.parent.mkdir(parents=True)
        target.write_bytes(b"state")
        selection = {"system": "snes", "rom": self.rom}
        for route in ("preview", "delete"):
            self.assertEqual(self.request("POST", "/api/auto-state/" + route, selection)[0], 401)
        self.login()
        for route in ("preview", "delete"):
            self.assertEqual(self.request("POST", "/api/auto-state/" + route, selection,
                                          {"X-CSRF-Token": "wrong"})[0], 403)
            self.assertEqual(self.request("POST", "/api/auto-state/" + route, selection,
                                          {"Origin": "http://evil.test"})[0], 400)
        self.assertEqual(self.request("GET", "/api/auto-state/delete")[0], 404)
        for closed, confirmed in ((False, True), (True, False), ("true", True), (True, "true")):
            status, data, _ = self.request("POST", "/api/auto-state/preview", selection)
            self.assertEqual(status, 200)
            ticket = json.loads(data)["ticket"]
            status, _, _ = self.request("POST", "/api/auto-state/delete", {
                "ticket": ticket, "closed": closed, "confirmed": confirmed})
            self.assertEqual(status, 400)
            self.assertEqual(target.read_bytes(), b"state")
        status, data, _ = self.request("POST", "/api/auto-state/preview", selection)
        self.assertEqual(status, 200)
        ticket = json.loads(data)["ticket"]
        status, _, _ = self.request("POST", "/api/auto-state/delete", {
            "ticket": "wrong", "closed": True, "confirmed": True})
        self.assertEqual(status, 400)
        other_file = target.parent / "Other.state.auto"
        other_file.write_bytes(b"keep other")
        body = {"ticket": ticket, "closed": True, "confirmed": True, "destination": str(other_file)}
        status, data, _ = self.request("POST", "/api/auto-state/delete", body)
        self.assertEqual(status, 200, data)
        self.assertTrue(json.loads(data)["deleted"])
        self.assertFalse(target.exists())
        self.assertEqual(other_file.read_bytes(), b"keep other")
        target.write_bytes(b"new state")
        self.assertEqual(self.request("POST", "/api/auto-state/delete", body)[0], 400)
        self.assertEqual(target.read_bytes(), b"new state")

    def test_auto_state_http_changed_expired_missing_and_io_failure(self):
        self.login()
        selection = {"system": "snes", "rom": self.rom}
        target = self.manager.auto_state_path("snes", self.rom)
        target.parent.mkdir(parents=True)
        for failure in ("changed", "expired", "missing", "io"):
            target.write_bytes(b"original")
            _, data, _ = self.request("POST", "/api/auto-state/preview", selection)
            body = {"ticket": json.loads(data)["ticket"], "closed": True, "confirmed": True}
            if failure == "changed":
                target.write_bytes(b"changed")
            elif failure == "expired":
                next(iter(self.server.sessions.values()))["auto_state"]["expires"] = 0
            elif failure == "missing":
                target.unlink()
            if failure == "io":
                with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
                    status, data, _ = self.request("POST", "/api/auto-state/delete", body, {"X-Language": "it"})
                self.assertEqual(status, 503)
                key = "io_error"
            else:
                status, data, _ = self.request("POST", "/api/auto-state/delete", body, {"X-Language": "it"})
                self.assertEqual(status, 400)
                key = {"changed": "auto_state_changed", "expired": "preview_expired", "missing": "auto_state_missing"}[failure]
            self.assertEqual(json.loads(data)["error"], translate(key, "it"))
            if failure != "missing":
                self.assertEqual(target.read_bytes(), b"changed" if failure == "changed" else b"original")

    def test_localized_errors_are_request_scoped(self):
        for language, expected in ((None, "Sign in to continue."), ("it", "Accedi per continuare."),
                                   ("de", "Sign in to continue."), ("en", "Sign in to continue.")):
            headers = {"X-Language": language} if language else {}
            status, data, _ = self.request("GET", "/api/systems", headers=headers)
            self.assertEqual(status, 401)
            body = json.loads(data)
            self.assertEqual(body["error"], expected)
            self.assertEqual(body["error_key"], "login_required")
            self.assertEqual(body["parameters"], {})
        self.login()
        status, data, _ = self.request("POST", "/api/preview", {
            "system": "snes", "rom": self.rom, "extension": ".mcd"}, {"X-Language": "it"})
        self.assertEqual(status, 400)
        body = json.loads(data)
        self.assertEqual(body["error_key"], "expected_format")
        self.assertEqual(body["parameters"], {"extensions": ".srm"})
        self.assertEqual(body["error"], translate("expected_format", "it", extensions=".srm"))
        with patch.object(self.manager, "library", side_effect=ValueError("private implementation detail")):
            status, data, _ = self.request("GET", "/api/roms?system=snes", headers={"X-Language": "it"})
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(data)["error"], translate("invalid_request", "it"))

    def test_catalog_routes_are_public_and_allowlisted(self):
        for language in ("en", "it"):
            status, data, headers = self.request("GET", "/locales/" + language + ".json")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data), TRANSLATIONS[language])
            self.assertIn("application/json", headers["Content-Type"])
        self.login()
        for path in ("/locales/de.json", "/locales/../config.json", "/locales/%2e%2e/config.json"):
            self.assertEqual(self.request("GET", path)[0], 404)

    def test_close_waits_for_active_request(self):
        self.login()
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        original = self.manager.library

        def blocked_library(identifier):
            entered.set()
            release.wait(5)
            return original(identifier)

        def close_server():
            self.server.shutdown()
            self.server.server_close()
            finished.set()

        with patch.object(self.manager, "library", side_effect=blocked_library):
            client = threading.Thread(target=lambda: self.request("GET", "/api/roms?system=snes"))
            client.start()
            try:
                self.assertTrue(entered.wait(3))
                closer = threading.Thread(target=close_server)
                closer.start()
                self.assertFalse(finished.wait(0.7))
            finally:
                release.set()
                client.join(5)
            closer.join(5)
            self.assertTrue(finished.is_set())

    def test_psx_alias_http_validation(self):
        self.manager.systems["psx"] = {"label": "PlayStation", "save_extension": ".srm",
                                       "rom_extensions": [".chd"]}
        rom_folder = self.root / "roms" / "psx"
        rom_folder.mkdir()
        (rom_folder / "Game.chd").write_bytes(b"synthetic rom")
        self.login()
        status, data, _ = self.request("GET", "/api/systems")
        self.assertEqual(status, 200)
        systems = {system["id"]: system for system in json.loads(data)["systems"]}
        self.assertEqual(systems["psx"]["input_extensions"], [".srm", ".mcd", ".mcr"])
        self.assertEqual(systems["snes"]["input_extensions"], [".srm"])
        card = bytearray(131072)
        card[:2] = b"MC"
        card[127] = ord("M") ^ ord("C")
        target = self.root / "saves" / "psx" / "Game.srm"
        for extension in (".mcd", ".mcr"):
            for valid in (False, True):
                status, data, _ = self.request("POST", "/api/preview", {
                    "system": "psx", "rom": "Game.chd", "extension": extension})
                self.assertEqual(status, 200)
                ticket = json.loads(data)["ticket"]
                before = fingerprint(target)
                status, data, _ = self.request("POST", "/api/import?ticket=" + ticket
                    + "&closed=yes&overwrite=yes", bytes(card) if valid else b"X" * 131072,
                    {"Content-Type": "application/octet-stream"})
                self.assertEqual(status, 200 if valid else 400, data)
                if valid:
                    self.assertEqual(target.read_bytes(), card)
                else:
                    self.assertEqual(fingerprint(target), before)

    def test_preview_upload_download_and_no_replay(self):
        self.import_save(b"original")
        self.login()
        status, data, _ = self.request("POST", "/api/preview", {
            "system": "snes", "rom": self.rom, "extension": ".srm"})
        self.assertEqual(status, 200)
        ticket = json.loads(data)["ticket"]
        url = "/api/import?ticket=" + ticket + "&closed=yes&overwrite=yes"
        status, data, _ = self.request("POST", url, b"new save", {"Content-Type": "application/octet-stream"})
        self.assertEqual(status, 200, data)
        result = json.loads(data)
        self.assertEqual(self.target.read_bytes(), b"new save")
        self.assertEqual(Path(result["backup"]).read_bytes(), b"original")
        self.assertEqual(self.request("POST", url, b"again", {"Content-Type": "application/octet-stream"})[0], 400)
        from urllib.parse import urlencode
        params = urlencode({"system": "snes", "rom": self.rom, "name": result["backup_id"]})
        status, data, _ = self.request("GET", "/api/backup?" + params)
        self.assertEqual(status, 200)
        self.assertEqual(data, b"original")


class PasswordTests(unittest.TestCase):
    def test_systemd_ready_notification(self):
        with patch.dict("os.environ", {"NOTIFY_SOCKET": "@test-socket"}), patch("socket.AF_UNIX", 1, create=True), patch("socket.socket") as socket_mock:
            notify_ready()
            socket_mock.return_value.__enter__.return_value.sendto.assert_called_once_with(b"READY=1", "\0test-socket")

    def test_noninteractive_password_required(self):
        with patch.dict("os.environ", {}, clear=True), patch("sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(SaveError, "non-interactive"):
                read_password()

    def test_password_file_and_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            password_file = Path(folder) / "password"
            password_file.write_text("test password\n", encoding="utf-8")
            self.assertEqual(read_password(password_file), "test password")
        with patch.dict("os.environ", {"R36S_PASSWORD": "test environment"}):
            self.assertEqual(read_password(), "test environment")

    def test_password_setup_atomic_and_mismatch_preserves_previous(self):
        with tempfile.TemporaryDirectory() as folder, patch("sys.stdin.isatty", return_value=True):
            password_file = Path(folder) / "password"
            with patch("getpass.getpass", side_effect=["test password", "test password"]):
                set_password(password_file)
            self.assertEqual(read_password(password_file), "test password")
            with patch("getpass.getpass", side_effect=["replacement", "different"]):
                with self.assertRaises(SaveError):
                    set_password(password_file)
            self.assertEqual(read_password(password_file), "test password")


if __name__ == "__main__":
    unittest.main()