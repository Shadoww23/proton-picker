#!/usr/bin/env python3
"""Remove Proton Picker and restore its prior Steam default when still owned."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import app


def uninstall() -> int:
    if app.steam_running():
        print("Close Steam before uninstalling Proton Picker.", file=sys.stderr)
        return 1
    state = app.load_state()
    installation = state.get("installation", {})
    config = Path(installation["steam_config"]) if installation.get("steam_config") else None
    if config and config.is_file():
        try:
            result = app.restore_default_compatibility_tool(
                config, "proton-picker", installation.get("original_default_mapping"))
            print("Restored the previous Steam default." if result["changed"] else result["reason"])
        except (OSError, ValueError, app.SteamRunningError) as exc:
            print(f"Could not restore Steam's default: {exc}", file=sys.stderr)
            return 1

    tool_dir = Path(state.get("dispatcher_dir", "")) if state.get("dispatcher_dir") else None
    if tool_dir and (tool_dir / ".proton-picker-managed").is_file():
        shutil.rmtree(tool_dir)
    app.install_autostart(False)
    app_dir = Path(installation["app_dir"]) if installation.get("app_dir") else None
    if app_dir and app_dir.is_dir() and app_dir.name == "proton-picker":
        shutil.rmtree(app_dir)
    state.update({"enabled": False, "default_tool_installed": False,
                  "dispatcher_dir": None, "installation": {}})
    app.save_state(state)
    print("Proton Picker was removed. Restart Steam to refresh its compatibility-tool list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(uninstall())
