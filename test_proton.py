import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class RecommendationTests(unittest.TestCase):
    def test_matches_only_installed_reported_version(self):
        now = time.time()
        reports = [
            {"protonVersion": "10.0-3", "rating": "gold", "timestamp": now, "gpu": "AMD Radeon RX 6800"},
            {"protonVersion": "10.0-3", "rating": "platinum", "timestamp": now, "gpu": "AMD Radeon RX 6800"},
            {"protonVersion": "11.0-1", "rating": "silver", "timestamp": now, "gpu": "NVIDIA GeForce RTX 4090"},
        ]
        tools = {"Proton 10.0": "proton_10", "Proton 11.0": "proton_11"}
        result = app.rank_reports(reports, tools, "AMD Radeon RX 6800")
        self.assertEqual(result["version"], "Proton 10.0")
        self.assertEqual(result["tool"], "proton_10")
        self.assertEqual(result["reports"], 2)

    def test_official_proton_can_be_requested_from_steam_when_missing(self):
        now = time.time()
        result = app.rank_reports([
            {"protonVersion": "10.0-3", "rating": "gold", "timestamp": now},
            {"protonVersion": "10.0-3", "rating": "platinum", "timestamp": now},
        ], {"Proton 9.0": "proton_9"})
        self.assertEqual(result["tool"], "proton_10")
        self.assertEqual(result["installer_appid"], "3658110")
        self.assertFalse(result["installed"])

    def test_sparse_or_weak_reports_do_not_override_steam_default(self):
        now = time.time()
        tools = {"Proton 10.0": "proton_10"}
        self.assertIsNone(app.rank_reports([
            {"protonVersion": "10.0-3", "rating": "platinum", "timestamp": now}
        ], tools))
        self.assertIsNone(app.rank_reports([
            {"protonVersion": "10.0-3", "rating": "silver", "timestamp": now},
            {"protonVersion": "10.0-3", "rating": "silver", "timestamp": now},
        ], tools))

    def test_inline_vdf_comments_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tool.vdf"
            path.write_text('"compat_tools" { "GE-Proton11" // internal name\n { "display_name" "GE-Proton11" } }')
            parsed = app.parse_vdf(path)
        self.assertEqual(parsed["compat_tools"]["GE-Proton11"]["display_name"], "GE-Proton11")

    def test_default_tool_setup_backs_up_and_preserves_per_game_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.vdf"
            config.write_text('"InstallConfigStore" { "Software" { "Valve" { "Steam" { '
                              '"CompatToolMapping" { "0" { "name" "proton_11" "config" "" "priority" "75" } '
                              '"100" { "name" "manual_tool" "config" "" "priority" "250" } } } } } }')
            with patch.object(app, "steam_running", return_value=False):
                result = app.set_default_compatibility_tool(config, "proton-picker")
                mapping = app.compat_mapping(app.parse_vdf(config))
                repeat = app.set_default_compatibility_tool(config, "proton-picker")
            self.assertTrue(result["changed"])
            self.assertTrue(Path(result["backup"]).is_file())
            self.assertEqual(mapping["0"]["name"], "proton-picker")
            self.assertEqual(mapping["0"]["priority"], "75")
            self.assertEqual(mapping["100"]["name"], "manual_tool")
            self.assertFalse(repeat["changed"])

    def test_default_tool_restore_is_safe_and_respects_later_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.vdf"
            config.write_text('"InstallConfigStore" { "Software" { "Valve" { "Steam" { '
                              '"CompatToolMapping" { "0" { "name" "proton_11" "config" "" "priority" "75" } '
                              '"100" { "name" "manual_tool" "config" "" "priority" "250" } } } } } }')
            with patch.object(app, "steam_running", return_value=False):
                app.set_default_compatibility_tool(config, "proton-picker")
                restored = app.restore_default_compatibility_tool(
                    config, "proton-picker", {"name": "proton_11", "config": "", "priority": "75"})
            mapping = app.compat_mapping(app.parse_vdf(config))
            self.assertTrue(restored["changed"])
            self.assertEqual(mapping["0"]["name"], "proton_11")
            self.assertEqual(mapping["100"]["name"], "manual_tool")

            with patch.object(app, "steam_running", return_value=False):
                app.set_default_compatibility_tool(config, "proton-picker")
                tree = app.parse_vdf(config)
                mapping = app.compat_mapping(tree)
                mapping["0"]["name"] = "user-choice"
                config.write_text(app.dump_vdf(tree))
                skipped = app.restore_default_compatibility_tool(
                    config, "proton-picker", {"name": "proton_11", "config": "", "priority": "75"})
            self.assertFalse(skipped["changed"])
            self.assertEqual(app.compat_mapping(app.parse_vdf(config))["0"]["name"], "user-choice")

    def test_auto_apply_preserves_manual_setting_and_can_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Steam"
            steamapps = root / "steamapps"
            (steamapps / "common/Proton 10.0").mkdir(parents=True)
            (steamapps / "appmanifest_100.acf").write_text(
                '"AppState" { "appid" "100" "name" "Manual Game" "oslist" "windows" }')
            (steamapps / "appmanifest_200.acf").write_text(
                '"AppState" { "appid" "200" "name" "Auto Game" "oslist" "windows" }')
            config = root / "config/config.vdf"
            config.parent.mkdir(parents=True)
            config.write_text('"InstallConfigStore" { "Software" { "Valve" { "Steam" { '
                              '"CompatToolMapping" { "100" { "name" "manual_tool" "config" "" "priority" "250" } }'
                              '} } } }')
            state_file = Path(tmp) / "state.json"
            with patch.object(app, "steam_roots", return_value=[root]), \
                 patch.object(app, "state_path", return_value=state_file), \
                 patch.object(app, "steam_running", return_value=False), \
                 patch.object(app, "install_autostart"):
                applied = app.apply_recommendations({
                    "100": {"tool": "proton_10", "version": "Proton 10.0"},
                    "200": {"tool": "proton_10", "version": "Proton 10.0"},
                })
                self.assertEqual(applied["applied"], 1)
                self.assertEqual(applied["skipped"], 1)
                mapping = app.compat_mapping(app.parse_vdf(config))
                self.assertEqual(mapping["100"]["name"], "manual_tool")
                self.assertEqual(mapping["200"]["name"], "proton_10")
                self.assertTrue(config.with_suffix(".vdf.proton-picker-backup").exists())
                app.disable_auto()
                mapping = app.compat_mapping(app.parse_vdf(config))
                self.assertEqual(mapping["100"]["name"], "manual_tool")
                self.assertNotIn("200", mapping)

    def test_missing_recommended_tool_is_requested_from_steam(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Steam"
            steamapps = root / "steamapps"
            (steamapps / "common/Proton 9.0").mkdir(parents=True)
            (steamapps / "appmanifest_200.acf").write_text(
                '"AppState" { "appid" "200" "name" "Auto Game" "oslist" "windows" }')
            (root / "config/config.vdf").parent.mkdir(parents=True)
            (root / "config/config.vdf").write_text('"InstallConfigStore" {}')
            state_file = Path(tmp) / "state.json"
            with patch.object(app, "steam_roots", return_value=[root]), \
                 patch.object(app, "state_path", return_value=state_file), \
                 patch.object(app, "steam_running", return_value=False), \
                 patch.object(app, "install_autostart"), \
                 patch.object(app, "request_steam_install") as request:
                result = app.apply_recommendations({
                    "200": {"tool": "proton_10", "version": "Proton 10.0", "installer_appid": "3658110"}
                })
            self.assertEqual(result["status"], "installing")
            request.assert_called_once_with("3658110")
            self.assertFalse(app.compat_mapping(app.parse_vdf(root / "config/config.vdf")))

    def test_manual_reset_of_auto_mapping_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Steam"
            steamapps = root / "steamapps"
            (steamapps / "common/Proton 10.0").mkdir(parents=True)
            (steamapps / "appmanifest_200.acf").write_text(
                '"AppState" { "appid" "200" "name" "Auto Game" "oslist" "windows" }')
            config = root / "config/config.vdf"
            config.parent.mkdir(parents=True)
            # The user removed the mapping that Auto Mode had previously set.
            config.write_text('"InstallConfigStore" { "Software" { "Valve" { "Steam" { "CompatToolMapping" {} } } } }')
            state_file = Path(tmp) / "state.json"
            state_file.write_text(json.dumps({"enabled": True, "managed": {"200": "proton_9"}}))
            with patch.object(app, "steam_roots", return_value=[root]), \
                 patch.object(app, "state_path", return_value=state_file), \
                 patch.object(app, "steam_running", return_value=False), \
                 patch.object(app, "install_autostart"):
                app.apply_recommendations({"200": {"tool": "proton_10", "version": "Proton 10.0"}})
            mapping = app.compat_mapping(app.parse_vdf(config))
            state = json.loads(state_file.read_text())
            self.assertNotIn("200", mapping)
            self.assertIn("200", state["manual_opt_out"])


if __name__ == "__main__":
    unittest.main()
