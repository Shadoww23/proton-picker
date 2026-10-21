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
    def test_setup_can_remove_overrides_and_uninstall_restores_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.vdf"
            config.write_text('"InstallConfigStore" { "Software" { "Valve" { "Steam" { '
                              '"CompatToolMapping" { "0" { "name" "proton_11" "config" "" "priority" "75" } '
                              '"100" { "name" "manual_tool" "config" "" "priority" "250" } } } } } }')
            original = {"name": "proton_11", "config": "", "priority": "75"}
            with patch.object(app, "steam_running", return_value=False):
                result = app.set_default_compatibility_tool(
                    config, "proton-picker", clear_overrides=True)
            self.assertEqual(app.compat_mapping(app.parse_vdf(config))["0"]["name"], "proton-picker")
            self.assertNotIn("100", app.compat_mapping(app.parse_vdf(config)))
            self.assertEqual(result["removed"]["100"]["name"], "manual_tool")

            with patch.object(app, "steam_running", return_value=False):
                app.restore_default_compatibility_tool(
                    config, "proton-picker", original, result["removed"])
            mapping = app.compat_mapping(app.parse_vdf(config))
            self.assertEqual(mapping["0"]["name"], "proton_11")
            self.assertEqual(mapping["100"]["name"], "manual_tool")

    def test_clearing_overrides_still_runs_when_picker_is_already_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.vdf"
            config.write_text('"InstallConfigStore" { "Software" { "Valve" { "Steam" { '
                              '"CompatToolMapping" { "0" { "name" "proton-picker" "config" "" "priority" "75" } '
                              '"100" { "name" "manual_tool" "config" "" "priority" "250" } } } } } }')
            with patch.object(app, "steam_running", return_value=False):
                result = app.set_default_compatibility_tool(
                    config, "proton-picker", clear_overrides=True)
            self.assertTrue(result["changed"])
            self.assertNotIn("100", app.compat_mapping(app.parse_vdf(config)))


if __name__ == "__main__":
    unittest.main()
