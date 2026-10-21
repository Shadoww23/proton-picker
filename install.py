#!/usr/bin/env python3
"""Install Proton Picker's Steam launch shim and background updater."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import app


def desktop_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def should_clear_overrides() -> bool:
    parser = argparse.ArgumentParser(description="Install Proton Picker.")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--clear-overrides", action="store_true",
                        help="remove Steam's per-game Proton overrides")
    choice.add_argument("--keep-overrides", action="store_true",
                        help="keep Steam's per-game Proton overrides")
    args = parser.parse_args()
    if args.clear_overrides:
        return True
    if args.keep_overrides:
        return False
    if not sys.stdin.isatty():
        return False
    answer = input("Remove existing per-game Proton overrides so Proton Picker manages "
                   "every game? [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")


def install() -> int:
    clear_overrides = should_clear_overrides()
    roots = app.steam_roots()
    if not roots:
        print("Steam was not found. Install Steam and run this setup again.", file=sys.stderr)
        return 1

    library = app.get_library()
    paths = library.get("tool_paths", {})
    fallback = None
    config_path, tree = app.steam_config_tree(roots)
    if not config_path:
        print("Steam's config.vdf was not found; setup stopped before changing files.", file=sys.stderr)
        return 1
    if config_path:
        global_entry = app.compat_mapping(tree).get("0", {})
        if isinstance(global_entry, dict):
            fallback = paths.get(global_entry.get("name", ""))
    fallback = fallback or paths.get(library["tool_ids"].get(library["baseline"], ""))
    if not fallback or not os.access(fallback, os.X_OK):
        print("No installed Proton build was found for the safe fallback. Install Proton in Steam and try again.",
              file=sys.stderr)
        return 1

    steam_tool = roots[0] / "compatibilitytools.d" / "proton-picker"
    if steam_tool.exists() and not (steam_tool / ".proton-picker-managed").is_file():
        print(f"Refusing to replace an existing compatibility tool: {steam_tool}", file=sys.stderr)
        return 1

    persistent_app = Path.home() / ".local/share/proton-picker"
    persistent_app.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app.ROOT, persistent_app, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "test_*.py", ".git"))

    steam_tool.mkdir(parents=True, exist_ok=True)
    for filename in ("compatibilitytool.vdf", "toolmanifest.vdf", "proton"):
        shutil.copy2(app.ROOT / "compatibility-tool" / filename, steam_tool / filename)
    (steam_tool / "proton").chmod(0o755)
    (steam_tool / ".proton-picker-managed").write_text("managed by Proton Picker\n", encoding="utf-8")

    # Seed a safe route before Steam can invoke the compatibility tool.
    app.write_dispatcher_cache({}, library, steam_tool)
    state = app.load_state()
    state.update({"enabled": True, "last_sync": 0, "dispatcher_dir": str(steam_tool),
                  "clear_overrides": clear_overrides})
    installation = state.setdefault("installation", {})
    if "original_default_mapping" not in installation:
        installation["original_default_mapping"] = app.compat_mapping(tree).get("0")
        installation["config_backup"] = None
        installation["steam_config"] = str(config_path)
    installation["app_dir"] = str(persistent_app)
    state["pending_setup"] = True
    app.save_state(state)

    autostart = Path.home() / ".config/autostart/proton-picker.desktop"
    autostart.parent.mkdir(parents=True, exist_ok=True)
    command = f"{desktop_quote(sys.executable)} {desktop_quote(str(persistent_app / 'app.py'))} --background"
    autostart.write_text("[Desktop Entry]\nType=Application\nName=Proton Picker\n"
                         f"Exec={command}\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n",
                         encoding="utf-8")

    try:
        result = app.write_dispatcher_cache(app.fetch_recommendations(), app.get_library(), steam_tool,
                                            app.load_state().get("pins", {}))
        print(result["message"])
        state = app.load_state()
        state["last_sync"] = time.time()
        app.save_state(state)
    except Exception as exc:
        print(f"Initial report sync skipped; the fallback Proton is ready ({exc}).")

    try:
        subprocess.Popen([sys.executable, str(persistent_app / "app.py"), "--background"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        print(f"Background updater will start at the next login ({exc}).")

    try:
        configured = app.complete_pending_setup()
    except (OSError, ValueError, app.SteamRunningError) as exc:
        print(f"Tool files are installed; Steam's default will be configured when Steam closes ({exc}).")
        configured = False
    print("\nTool files and background updater are installed.")
    if configured:
        print("Proton Picker is now Steam's default compatibility tool. Restart Steam once, then click Play as usual.")
        installed_state = app.load_state()
        backup = installed_state.get("installation", {}).get("config_backup")
        if backup:
            print(f"Previous Steam config backed up to: {backup}")
    elif app.steam_running():
        print("Steam is open. The updater will set Proton Picker as default after Steam closes; restart Steam once after that.")
    else:
        print("Steam's default choice could not be updated. Check the config file and rerun setup.")
    if app.load_state().get("pending_setup"):
        print("Per-game overrides will be " + ("removed" if clear_overrides else "kept")
              + " when Steam closes.")
    elif clear_overrides:
        print("Per-game Proton overrides were removed and saved so uninstall can restore them.")
    else:
        print("Per-game Proton overrides were kept.")
    return 0


if __name__ == "__main__":
    raise SystemExit(install())
