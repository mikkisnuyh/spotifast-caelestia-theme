"""Tests for caelestia-spotifast, install.sh and uninstall.sh.

Run with: python3 -m unittest discover -s tests
Every test uses a temporary HOME, so nothing on this machine is touched.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "caelestia-spotifast"
FIXTURES = ROOT / "tests/fixtures"
EXPECTED = ROOT / "tests/expected"

sys.path.insert(0, str(ROOT / "lib"))
import config_edit  # noqa: E402

# What Spotifast accepts (docs/_reference/settings-and-files.md, fastframe-theme).
SPOTIFAST_COLOURS = {
    "window", "panel", "surface", "surface_hover", "surface_active", "outline",
    "text", "secondary", "dim", "accent", "accent_hover", "on_accent", "danger",
    "warning", "overlay", "shadow",
}
SPOTIFAST_VALUE = re.compile(r"#[0-9a-f]{6}([0-9a-f]{2})?")
SPOTIFAST_MAX_BYTES = 64 * 1024


class Home:
    """A throwaway HOME with a PATH that holds only the basics plus `extra`."""

    def __init__(self, test: unittest.TestCase):
        self.test = test
        self.dir = Path(tempfile.mkdtemp(prefix="caelestia-spotifast-"))
        test.addCleanup(shutil.rmtree, self.dir)
        self.bin = self.dir / "fakebin"
        self.bin.mkdir()
        for tool in ("python3", "bash", "install", "realpath", "chmod", "mkdir", "rm", "dirname", "cat"):
            if found := shutil.which(tool):
                (self.bin / tool).symlink_to(found)
        self.env = {"HOME": str(self.dir), "PATH": str(self.bin), "LANG": "C.UTF-8"}

    def run_spotifast(self) -> None:
        """Starts a process named `spotifast`, as if the app were running."""
        app = self.dir / "app/spotifast"
        app.parent.mkdir()
        app.symlink_to(shutil.which("sleep"))
        process = subprocess.Popen([app, "60"])
        self.test.addCleanup(process.wait)
        self.test.addCleanup(process.kill)

    def scheme(self, name: str) -> None:
        path = self.dir / ".local/state/caelestia/scheme.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURES / f"{name}.json", path)

    def fake(self, name: str, body: str) -> Path:
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\n")
        path.chmod(0o755)
        return path

    def run(self, *args: str, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(
            [str(a) for a in args], env={**self.env, **(env or {})}, capture_output=True, text=True
        )
        if check and result.returncode != 0:
            raise AssertionError(f"{args} failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
        return result

    @property
    def themes(self) -> Path:
        return self.dir / ".config/spotifast/themes"

    @property
    def cli_json(self) -> Path:
        return self.dir / ".config/caelestia/cli.json"


class GeneratorTest(unittest.TestCase):
    def test_scheme_json_produces_the_expected_palettes(self):
        for name in ("catppuccin-mocha", "catppuccin-latte"):
            with self.subTest(name):
                home = Home(self)
                home.scheme(name)
                home.run(SCRIPT)
                written = (home.themes / "caelestia.json").read_text()
                self.assertEqual(written, (EXPECTED / f"{name}.json").read_text())

    def test_posthook_environment_wins_over_scheme_json(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        latte = json.loads((FIXTURES / "catppuccin-latte.json").read_text())
        out = home.run(
            SCRIPT, "--stdout",
            env={"SCHEME_MODE": "light", "SCHEME_COLOURS": json.dumps(latte["colours"])},
        ).stdout
        self.assertEqual(out, (EXPECTED / "catppuccin-latte.json").read_text())

    def test_output_is_a_palette_spotifast_accepts(self):
        for name in ("catppuccin-mocha", "catppuccin-latte"):
            text = (EXPECTED / f"{name}.json").read_text()
            palette = json.loads(text)
            self.assertLess(len(text.encode()), SPOTIFAST_MAX_BYTES)
            self.assertIn(palette["base"], ("dark", "light"))
            self.assertLessEqual(set(palette["colors"]), SPOTIFAST_COLOURS)
            for key, value in palette["colors"].items():
                self.assertRegex(value, SPOTIFAST_VALUE, key)

    def test_missing_or_invalid_colours_are_left_to_spotifast(self):
        home = Home(self)
        colours = {"surface": "#123456", "primary": "nothex", "onSurface": "abcdef"}
        out = home.run(
            SCRIPT, "--stdout", env={"SCHEME_MODE": "dark", "SCHEME_COLOURS": json.dumps(colours)}
        ).stdout
        self.assertEqual(
            json.loads(out), {"base": "dark", "colors": {"window": "#123456", "text": "#abcdef"}}
        )

    def test_unknown_mode_falls_back_to_dark(self):
        home = Home(self)
        out = home.run(SCRIPT, "--stdout", env={"SCHEME_MODE": "weird", "SCHEME_COLOURS": "{}"}).stdout
        self.assertEqual(json.loads(out)["base"], "dark")

    def test_no_scheme_fails_without_writing(self):
        home = Home(self)
        result = home.run(SCRIPT, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the Caelestia scheme", result.stderr)
        self.assertFalse(home.themes.exists())

    def test_scheme_json_that_is_not_an_object_fails_cleanly(self):
        home = Home(self)
        path = home.dir / ".local/state/caelestia/scheme.json"
        path.parent.mkdir(parents=True)
        for content in ("[]", "null", '"text"'):
            with self.subTest(content):
                path.write_text(content)
                result = home.run(SCRIPT, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertIn("cannot read the Caelestia scheme", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def wait_for(self, path: Path, content: str) -> None:
        """The reload runs detached, so it may finish after the script."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if path.exists() and path.read_text() == content:
                return
            time.sleep(0.02)
        self.assertEqual(path.read_text() if path.exists() else None, content)

    def test_write_is_atomic_readable_and_skipped_when_unchanged(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        home.run_spotifast()
        calls = home.dir / "reload-calls"
        home.fake("spotifast", f'echo "$@" >> "{calls}"')
        home.run(SCRIPT)
        palette = home.themes / "caelestia.json"
        self.assertEqual(stat.S_IMODE(palette.stat().st_mode), 0o644)
        self.assertEqual(os.listdir(home.themes), ["caelestia.json"])
        self.wait_for(calls, "reload-themes\n")

        before = palette.stat().st_mtime_ns
        home.run(SCRIPT)
        self.assertEqual(palette.stat().st_mtime_ns, before)
        time.sleep(0.2)
        self.assertEqual(calls.read_text(), "reload-themes\n", "unchanged palette must not reload")

        home.scheme("catppuccin-latte")
        home.run(SCRIPT)
        self.assertEqual(json.loads(palette.read_text())["base"], "light")
        self.wait_for(calls, "reload-themes\n" * 2)

    def test_reload_neither_starts_spotifast_nor_waits_for_it(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        calls = home.dir / "reload-calls"
        pid = home.dir / "reload-pid"
        home.fake("spotifast", f'echo $$ > "{pid}"; echo "$@" >> "{calls}"; exec {shutil.which("sleep")} 30')
        self.addCleanup(lambda: pid.exists() and os.kill(int(pid.read_text()), 9))
        home.run(SCRIPT)  # not running: no reload
        time.sleep(0.2)
        self.assertFalse(calls.exists())

        home.run_spotifast()
        home.scheme("catppuccin-latte")
        start = time.monotonic()
        home.run(SCRIPT)
        self.assertLess(time.monotonic() - start, 5, "the hook must not wait for the reload")
        self.wait_for(calls, "reload-themes\n")

    def test_flatpak_folder_is_written_when_the_app_is_installed(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        (home.dir / ".var/app/rocks.spotifast.Spotifast").mkdir(parents=True)
        home.run(SCRIPT)
        self.assertTrue((home.themes / "caelestia.json").is_file())
        self.assertTrue(
            (home.dir / ".var/app/rocks.spotifast.Spotifast/config/spotifast/themes/caelestia.json").is_file()
        )

    def test_themes_dir_override_and_xdg_config_home(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        custom = home.dir / "elsewhere"
        home.run(SCRIPT, env={"SPOTIFAST_THEMES_DIR": str(custom)})
        self.assertTrue((custom / "caelestia.json").is_file())
        self.assertFalse(home.themes.exists())

        home.run(SCRIPT, env={"XDG_CONFIG_HOME": str(home.dir / "xdg")})
        self.assertTrue((home.dir / "xdg/spotifast/themes/caelestia.json").is_file())


class HookEditTest(unittest.TestCase):
    CMD = "/home/u/.local/bin/caelestia-spotifast"
    EXISTING = (
        "", "notify-send hi", "notify-send hi;", "notify-send hi ;  ", "sleep 1 &", "a && b",
        "notify-send hi  # tell me", "case $x in a) b;; esac", "first\nsecond # last line",
    )

    def test_hook_joining_and_removal_round_trip(self):
        for existing in self.EXISTING:
            with self.subTest(existing=existing):
                joined = config_edit.hook_with(existing, self.CMD)
                self.assertTrue(joined.endswith(self.CMD))
                self.assertEqual(config_edit.hook_without(joined), existing.rstrip())

    def test_our_command_runs_after_any_existing_hook(self):
        for existing in self.EXISTING:
            with self.subTest(existing=existing):
                joined = config_edit.hook_with(existing, "echo OURS")
                result = subprocess.run(
                    ["sh", "-c", joined], env={"PATH": os.environ["PATH"]}, capture_output=True, text=True
                )
                self.assertEqual(result.stdout.splitlines()[-1:], ["OURS"])

    def test_removal_when_the_user_appended_after_ours(self):
        self.assertEqual(config_edit.hook_without(f"{self.CMD}; other"), "other")
        self.assertEqual(config_edit.hook_without(f"first; {self.CMD}; other"), "first; other")
        self.assertEqual(config_edit.hook_without(f"first\n{self.CMD}\nother"), "first\nother")

    def test_removal_of_hooks_added_by_older_versions(self):
        self.assertEqual(config_edit.hook_without(f"notify-send hi; {self.CMD}"), "notify-send hi")
        self.assertEqual(config_edit.hook_without(f"sleep 1 & {self.CMD}"), "sleep 1 &")
        self.assertEqual(config_edit.hook_without(f"a && {self.CMD}"), f"a && {self.CMD}")

    def test_hooks_from_any_bin_dir_are_recognised(self):
        for command in (self.CMD, "'/home/u/my tools/caelestia-spotifast'", r"/x/my\ tools/caelestia-spotifast"):
            with self.subTest(command):
                self.assertEqual(config_edit.hook_without(f"other\n{command}"), "other")
        for command in ("caelestia-spotifast-old", "/x/caelestia-spotifast --stdout", "echo caelestia-spotifast"):
            with self.subTest(command):
                self.assertEqual(config_edit.hook_without(f"other\n{command}"), f"other\n{command}")


class InstallTest(unittest.TestCase):
    def install(self, home: Home, *args: str, check: bool = True):
        return home.run("bash", ROOT / "install.sh", *args, check=check)

    def uninstall(self, home: Home, *args: str):
        return home.run("bash", ROOT / "uninstall.sh", *args)

    def test_install_keeps_existing_settings_and_hook_and_uninstall_restores(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        original = {
            "theme": {"enableGtk": False, "postHook": "notify-send changed"},
            "wallpaper": {"postHook": "echo wall"},
            "toggles": {"music": {"spotify": {"enable": True}}},
        }
        home.cli_json.parent.mkdir(parents=True)
        home.cli_json.write_text(json.dumps(original))

        self.install(home)
        script = home.dir / ".local/bin/caelestia-spotifast"
        self.assertTrue(os.access(script, os.X_OK))
        config = json.loads(home.cli_json.read_text())
        self.assertEqual(config["theme"]["postHook"], f"notify-send changed\n{script}")
        self.assertEqual(config["theme"]["enableGtk"], False)
        self.assertEqual(config["wallpaper"], original["wallpaper"])
        self.assertEqual(config["toggles"], original["toggles"])
        self.assertTrue((home.themes / "caelestia.json").is_file(), "initial sync")
        self.assertEqual(
            json.loads((home.cli_json.parent / "cli.json.caelestia-spotifast.bak").read_text()), original
        )

        self.install(home)  # idempotent
        self.assertEqual(json.loads(home.cli_json.read_text())["theme"]["postHook"], f"notify-send changed\n{script}")

        self.uninstall(home)
        self.assertEqual(json.loads(home.cli_json.read_text()), original)
        self.assertFalse(script.exists())
        self.assertFalse((home.themes / "caelestia.json").exists())

    def test_install_without_cli_json_creates_a_minimal_one(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        self.install(home)
        script = home.dir / ".local/bin/caelestia-spotifast"
        self.assertEqual(json.loads(home.cli_json.read_text()), {"theme": {"postHook": str(script)}})
        self.uninstall(home)
        self.assertEqual(json.loads(home.cli_json.read_text()), {})

    def test_invalid_cli_json_is_never_touched(self):
        home = Home(self)
        home.cli_json.parent.mkdir(parents=True)
        home.cli_json.write_text("{ not json")
        result = self.install(home, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(home.cli_json.read_text(), "{ not json")

    def test_uninstall_keeps_the_script_while_the_hook_cannot_be_removed(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        self.install(home)
        script = home.dir / ".local/bin/caelestia-spotifast"
        broken = home.cli_json.read_text().rstrip().removesuffix("}") + ",}"
        home.cli_json.write_text(broken)
        result = home.run("bash", ROOT / "uninstall.sh", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Nothing was removed", result.stderr)
        self.assertTrue(script.exists())
        self.assertTrue((home.themes / "caelestia.json").exists())
        self.assertEqual(home.cli_json.read_text(), broken)

    def test_old_style_hook_is_rewritten_and_non_ascii_text_is_kept(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        script = home.dir / ".local/bin/caelestia-spotifast"
        home.cli_json.parent.mkdir(parents=True)
        home.cli_json.write_text(json.dumps(
            {"theme": {"postHook": f"notify-send 'Thème changé'  # note; {script}"}}, ensure_ascii=False
        ))
        result = self.install(home)
        self.assertIn("updated", result.stdout)
        text = home.cli_json.read_text(encoding="utf-8")
        self.assertIn("Thème changé", text)
        self.assertEqual(
            json.loads(text)["theme"]["postHook"], f"notify-send 'Thème changé'  # note\n{script}"
        )

    def test_symlinked_cli_json_stays_a_link(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        real = home.dir / "dotfiles/cli.json"
        real.parent.mkdir()
        real.write_text('{"theme": {}}')
        home.cli_json.parent.mkdir(parents=True)
        home.cli_json.symlink_to(real)
        self.install(home)
        self.assertTrue(home.cli_json.is_symlink())
        self.assertIn("postHook", json.loads(real.read_text())["theme"])

    def test_install_without_a_scheme_still_succeeds(self):
        home = Home(self)
        result = self.install(home)
        self.assertIn("no palette yet", result.stderr)

    def test_select_sets_the_theme_only_when_spotifast_is_not_running(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        settings = home.dir / ".config/spotifast/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"bitrate": 320, "custom_theme": "nord.json", "custom_theme_cache": {}}))

        home.fake("pgrep", "exit 0")  # running
        result = self.install(home, "--select")
        self.assertIn("Spotifast is running", result.stderr)
        self.assertEqual(json.loads(settings.read_text())["custom_theme"], "nord.json")

        home.fake("pgrep", "exit 1")  # not running
        self.install(home, "--select")
        self.assertEqual(json.loads(settings.read_text()), {"bitrate": 320, "custom_theme": "caelestia.json"})

    def test_select_skips_missing_settings_and_continues_past_a_broken_one(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        home.fake("pgrep", "exit 1")
        native = home.dir / ".config/spotifast/settings.json"
        flatpak = home.dir / ".var/app/rocks.spotifast.Spotifast/config/spotifast/settings.json"
        flatpak.parent.mkdir(parents=True)

        result = self.install(home, "--select")
        self.assertIn("no settings.json yet", result.stdout)
        self.assertFalse(native.exists())
        self.assertFalse(flatpak.exists())

        native.write_text("{ broken")
        flatpak.write_text(json.dumps({"bitrate": 160}))
        result = self.install(home, "--select", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(native.read_text(), "{ broken")
        self.assertEqual(json.loads(flatpak.read_text()), {"bitrate": 160, "custom_theme": "caelestia.json"})

    def test_keep_theme(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        self.install(home)
        self.uninstall(home, "--keep-theme")
        self.assertTrue((home.themes / "caelestia.json").is_file())

    def test_reinstall_with_another_bin_dir_replaces_the_hook(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        self.install(home)
        bin_dir = home.dir / "my tools"
        result = self.install(home, "--bin-dir", str(bin_dir))
        self.assertIn("updated", result.stdout)
        hook = json.loads(home.cli_json.read_text())["theme"]["postHook"]
        self.assertEqual(hook, f"'{bin_dir}/caelestia-spotifast'")

        self.uninstall(home)  # default --bin-dir still takes out the hook
        self.assertEqual(json.loads(home.cli_json.read_text()), {})

    def test_custom_bin_dir_and_systemd_mode(self):
        home = Home(self)
        home.scheme("catppuccin-mocha")
        log = home.dir / "systemctl-calls"
        home.fake("systemctl", f'echo "$@" >> "{log}"')
        bin_dir = home.dir / "my tools & 100%"
        self.install(home, "--bin-dir", str(bin_dir))  # hook first, then switch
        self.install(home, "--systemd", "--bin-dir", str(bin_dir))

        units = home.dir / ".config/systemd/user"
        service = (units / "caelestia-spotifast.service").read_text()
        exec_start = str(bin_dir).replace("%", "%%")
        self.assertIn(f'ExecStart="{exec_start}/caelestia-spotifast"\n', service)
        self.assertTrue((units / "caelestia-spotifast.path").is_file())
        self.assertIn("--user enable --now caelestia-spotifast.path", log.read_text())
        self.assertEqual(json.loads(home.cli_json.read_text()), {}, "switching removes the hook")

        self.uninstall(home, "--bin-dir", str(bin_dir))
        self.assertFalse(any(units.iterdir()))
        self.assertFalse((bin_dir / "caelestia-spotifast").exists())

    def test_systemd_mode_refuses_a_path_systemd_cannot_run(self):
        home = Home(self)
        home.fake("systemctl", "exit 0")
        bin_dir = home.dir / 'say "hi"'
        result = self.install(home, "--systemd", "--bin-dir", str(bin_dir), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("systemd cannot run", result.stderr)
        self.assertFalse(bin_dir.exists())


if __name__ == "__main__":
    unittest.main()
