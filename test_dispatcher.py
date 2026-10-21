import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import app

DISPATCHER = Path(__file__).parent / "compatibility-tool" / "proton"


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tool = Path(self.temp.name) / "tool"
        self.tool.mkdir()
        self.dispatcher = self.tool / "proton"
        self.dispatcher.write_bytes(DISPATCHER.read_bytes())
        self.dispatcher.chmod(0o755)
        self.build = Path(self.temp.name) / "selected-proton"
        self.build.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
        self.build.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_dispatcher(self, appid, extra_env=None):
        env = dict(os.environ, STEAM_COMPAT_APP_ID=appid)
        if extra_env:
            env.update(extra_env)
        return subprocess.run([str(self.dispatcher), "waitforexitandrun", "game.exe"],
                              env=env, text=True, capture_output=True)

    def test_play_launch_uses_cached_per_game_selection(self):
        other = Path(self.temp.name) / "other-proton"
        other.write_text("#!/bin/sh\nexit 91\n")
        other.chmod(0o755)
        (self.tool / "selections.tsv").write_text(
            f"123\t{other}\n456\t{self.build}\n", encoding="utf-8")
        result = self.run_dispatcher("456")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines(), ["waitforexitandrun", "game.exe"])

    def test_unknown_game_uses_configured_fallback(self):
        (self.tool / "fallback.txt").write_text(str(self.build) + "\n", encoding="utf-8")
        result = self.run_dispatcher("789")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines(), ["waitforexitandrun", "game.exe"])

    def test_missing_target_fails_instead_of_launching_wrong_build(self):
        empty_home = Path(self.temp.name) / "empty-home"
        empty_home.mkdir()
        (self.tool / "selections.tsv").write_text("456\t/missing/proton\n", encoding="utf-8")
        result = self.run_dispatcher("456", {"HOME": str(empty_home)})
        self.assertEqual(result.returncode, 126)
        self.assertIn("no usable Proton build", result.stderr)

    def test_removed_recommended_build_uses_safe_fallback(self):
        (self.tool / "selections.tsv").write_text("456\t/missing/proton\n", encoding="utf-8")
        (self.tool / "fallback.txt").write_text(str(self.build) + "\n", encoding="utf-8")
        result = self.run_dispatcher("456")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines(), ["waitforexitandrun", "game.exe"])

    def test_fallback_list_recovers_when_mounted_drive_disappears(self):
        (self.tool / "fallback.txt").write_text("/missing/proton\n", encoding="utf-8")
        (self.tool / "fallback-list.txt").write_text(
            f"/missing/proton\n{self.build}\n", encoding="utf-8")
        result = self.run_dispatcher("789")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines(), ["waitforexitandrun", "game.exe"])

    def test_last_resort_scan_finds_a_steam_installed_proton(self):
        home = Path(self.temp.name) / "home"
        proton = home / ".local/share/Steam/steamapps/common/Proton 11.0/proton"
        proton.parent.mkdir(parents=True)
        proton.write_text("#!/bin/sh\nexit 0\n")
        proton.chmod(0o755)
        result = self.run_dispatcher("789", {"HOME": str(home)})
        self.assertEqual(result.returncode, 0)

    def test_cache_prefers_a_present_build_when_baseline_drive_is_gone(self):
        tool_dir = Path(self.temp.name) / "installed-picker"
        library = {
            "games": [{"appid": "123", "oslist": "windows"}],
            "tool_ids": {"Proton 11.0": "proton_11", "Proton 9.0": "proton_9"},
            "tool_paths": {"proton_11": "/missing/proton", "proton_9": str(self.build)},
            "baseline": "Proton 11.0",
        }
        result = app.write_dispatcher_cache({}, library, tool_dir)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["fallback"], str(self.build))
        self.assertEqual((tool_dir / "fallback.txt").read_text(), f"{self.build}\n")
        self.assertIn(str(self.build), (tool_dir / "fallback-list.txt").read_text())

    def test_cache_lists_every_usable_build_as_a_backup(self):
        second = Path(self.temp.name) / "second-proton"
        second.write_text("#!/bin/sh\nexit 0\n")
        second.chmod(0o755)
        tool_dir = Path(self.temp.name) / "installed-picker"
        library = {
            "games": [],
            "tool_ids": {"Proton 11.0": "proton_11", "Proton 9.0": "proton_9"},
            "tool_paths": {"proton_11": str(self.build), "proton_9": str(second)},
            "baseline": "Proton 11.0",
        }
        result = app.write_dispatcher_cache({}, library, tool_dir)
        self.assertEqual(result["fallback_count"], 2)
        listed = (tool_dir / "fallback-list.txt").read_text().split()
        self.assertEqual(listed[0], str(self.build))
        self.assertIn(str(second), listed)

    def test_cache_never_lists_the_picker_shim_as_its_own_fallback(self):
        tool_dir = Path(self.temp.name) / "proton-picker"
        tool_dir.mkdir()
        shim = tool_dir / "proton"
        shim.write_text("#!/bin/sh\nexit 0\n")
        shim.chmod(0o755)
        library = {
            "games": [],
            "tool_ids": {"proton-picker": "proton-picker", "Proton 9.0": "proton_9"},
            "tool_paths": {"proton-picker": str(shim), "proton_9": str(self.build)},
            "baseline": "proton-picker",
        }
        result = app.write_dispatcher_cache({}, library, tool_dir)
        self.assertEqual(result["fallback"], str(self.build))
        self.assertNotIn(str(shim), (tool_dir / "fallback-list.txt").read_text())

    def test_fallback_prefers_official_stable_over_third_party(self):
        ge = Path(self.temp.name) / "GE-Proton11-7" / "proton"
        ge.parent.mkdir()
        ge.write_text("#!/bin/sh\nexit 0\n")
        ge.chmod(0o755)
        tool_dir = Path(self.temp.name) / "installed-picker"
        library = {
            "games": [],
            "tool_ids": {"GE-Proton11-7": "GE-Proton11-7", "Proton 10.0": "proton_10"},
            "tool_paths": {"GE-Proton11-7": str(ge), "proton_10": str(self.build)},
            "baseline": "GE-Proton11-7",
        }
        result = app.write_dispatcher_cache({}, library, tool_dir)
        self.assertEqual(result["fallback"], str(self.build))
        self.assertEqual((tool_dir / "fallback.txt").read_text(), f"{self.build}\n")

    def test_pins_override_recommendations_and_unknown_tools_are_ignored(self):
        pinned = Path(self.temp.name) / "pinned-proton"
        pinned.write_text("#!/bin/sh\nexit 0\n")
        pinned.chmod(0o755)
        tool_dir = Path(self.temp.name) / "installed-picker"
        library = {
            "games": [{"appid": "123", "oslist": "windows"},
                      {"appid": "456", "oslist": "windows"}],
            "tool_ids": {"Proton 11.0": "proton_11", "Proton 9.0": "proton_9"},
            "tool_paths": {"proton_11": str(self.build), "proton_9": str(pinned)},
            "baseline": "Proton 11.0",
        }
        result = app.write_dispatcher_cache(
            {"123": {"tool": "proton_11"}, "456": {"tool": "proton_11"}}, library, tool_dir,
            {"123": "proton_9", "456": "removed-build"})
        self.assertEqual(result["pinned"], 2)
        self.assertEqual((tool_dir / "selections.tsv").read_text(),
                         f"123\t{pinned}\n456\t{self.build}\n")

    def test_cache_routes_only_games_with_installed_recommended_builds(self):
        tool_dir = Path(self.temp.name) / "installed-picker"
        library = {
            "games": [{"appid": "123", "oslist": "windows"},
                      {"appid": "456", "oslist": "windows"},
                      {"appid": "789", "oslist": "linux"}],
            "tool_ids": {"Proton 10.0": "proton_10"},
            "tool_paths": {"proton_10": str(self.build)},
            "baseline": "Proton 10.0",
        }
        result = app.write_dispatcher_cache({
            "123": {"tool": "proton_10"},
            "456": {"tool": "not-installed", "installer_appid": "12345"},
            "789": {"tool": "proton_10"},
        }, library, tool_dir)
        self.assertEqual(result["selected"], 1)
        self.assertEqual((tool_dir / "selections.tsv").read_text(), f"123\t{self.build}\n")
        self.assertEqual((tool_dir / "fallback.txt").read_text(), f"{self.build}\n")


if __name__ == "__main__":
    unittest.main()
