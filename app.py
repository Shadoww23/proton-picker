#!/usr/bin/env python3
"""Local Linux helper for evidence-based Proton selection in Steam."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import tempfile
import sys
import fcntl
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
VERSION = "0.1.0-alpha"
RECOMMENDATION_CACHE: dict[str, dict] = {}
CACHE_UPDATED = 0.0
OFFICIAL_PROTON_APP_IDS = {"7": "1887720", "8": "2348590", "9": "2805730",
                           "10": "3658110", "11": "4628710"}
NON_GAME_APP_IDS = set(OFFICIAL_PROTON_APP_IDS.values()) | {
    "228980", "1070560", "1391110", "1493710", "1628350", "4183110"}
NON_GAME_PREFIXES = ("proton ", "steam linux runtime", "steamworks common redistributables")


def steam_roots() -> list[Path]:
    home = Path.home()
    candidates = [
        home / ".steam/steam",
        home / ".local/share/Steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        home / ".steam/root",
    ]
    roots = []
    for p in candidates:
        try:
            p = p.resolve()
        except OSError:
            pass
        if p.is_dir() and (p / "steamapps").is_dir() and p not in roots:
            roots.append(p)
    return roots


def parse_vdf(path: Path) -> dict:
    """Parse the small quoted-key VDF subset used by Steam manifests/config."""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    vals = []
    token_pattern = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])|//[^\r\n]*|([^\s{}]+)')
    for match in token_pattern.finditer(data):
        if match.group(0).startswith("//"):
            continue
        quoted, brace, bare = match.groups()
        vals.append(quoted.replace('\\"', '"').replace('\\\\', '\\') if quoted is not None else (brace or bare))
    def block(i: int, nested: bool = False):
        out = {}
        while i < len(vals):
            key = vals[i]
            if key == "}":
                return out, i + 1
            i += 1
            if i < len(vals) and vals[i] == "{":
                val, i = block(i + 1, True)
            elif i < len(vals):
                val, i = vals[i], i + 1
            else:
                break
            out[str(key)] = val
        return out, i
    result, _ = block(0)
    return result


def steam_config_tree(roots: list[Path]) -> tuple[Path | None, dict]:
    for root in roots:
        path = root / "config/config.vdf"
        if path.is_file():
            return path, parse_vdf(path)
    return None, {}


def compat_mapping(tree: dict) -> dict:
    return (tree.get("InstallConfigStore", {}).get("Software", {}).get("Valve", {})
            .get("Steam", {}).get("CompatToolMapping", {}))


def ensure_compat_mapping(tree: dict) -> dict:
    node = tree
    for key in ("InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping"):
        node = node.setdefault(key, {})
    return node


def installed_tool_ids(roots: list[Path], folders: set[str]) -> dict[str, str]:
    result = {}
    for folder in folders:
        lowered = folder.casefold()
        if lowered.startswith("proton - experimental") or lowered == "proton experimental":
            result[folder] = "proton_experimental"
            continue
        match = re.match(r"proton\s+(\d+)", folder, re.I)
        if match:
            result[folder] = f"proton_{match.group(1)}"
            continue
        # Third-party tools expose the internal compatibility-tool name in this file.
        for root in roots:
            candidate = root / "compatibilitytools.d" / folder / "compatibilitytool.vdf"
            if not candidate.is_file():
                continue
            compat_tools = parse_vdf(candidate).get("compatibilitytools", {}).get("compat_tools", {})
            if compat_tools:
                result[folder] = str(next(iter(compat_tools)))
                break
        result.setdefault(folder, folder)
    return result


def find_compat_overrides(roots: list[Path]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for root in roots:
        path, tree = steam_config_tree([root])
        if not path:
            continue
        for appid, mapping in compat_mapping(tree).items():
            if isinstance(mapping, dict) and appid != "0" and mapping.get("name"):
                overrides[str(appid)] = str(mapping["name"])
    return overrides


def get_library() -> dict:
    roots = steam_roots()
    libraries: list[Path] = []
    for root in roots:
        libraries.append(root / "steamapps")
        vdf = parse_vdf(root / "steamapps/libraryfolders.vdf")
        section = vdf.get("libraryfolders", vdf)
        if isinstance(section, dict):
            for key, value in section.items():
                if key.isdigit() and isinstance(value, dict) and value.get("path"):
                    libraries.append(Path(str(value["path"])) / "steamapps")
    libraries = list(dict.fromkeys(libraries))
    games = {}
    tools = set()
    for steamapps in libraries:
        if not steamapps.is_dir():
            continue
        common = steamapps / "common"
        if common.is_dir():
            for path in common.iterdir():
                if path.is_dir() and (path.name.lower().startswith("proton") or path.name.lower().startswith("wine")):
                    tools.add(path.name)
        for manifest in steamapps.glob("appmanifest_*.acf"):
            data = parse_vdf(manifest)
            app = data.get("AppState", data)
            if not isinstance(app, dict):
                continue
            appid, name = str(app.get("appid", "")), str(app.get("name", ""))
            lowered = name.casefold()
            if (not appid or not name or appid in NON_GAME_APP_IDS
                    or lowered.startswith(NON_GAME_PREFIXES)):
                continue
            games[appid] = {"appid": appid, "name": name, "installdir": app.get("installdir", ""),
                            "oslist": str(app.get("oslist", "windows"))}
    for root in roots:
        for path in (root / "compatibilitytools.d").glob("*"):
            if path.is_dir():
                tools.add(path.name)
    overrides = find_compat_overrides(roots)
    ordered = sorted(tools, key=tool_sort_key, reverse=True)
    stable = [t for t in ordered if "experimental" not in t.lower() and "ge-proton" not in t.lower()]
    baseline = stable[0] if stable else (ordered[0] if ordered else "Proton Experimental")
    tool_ids = installed_tool_ids(roots, tools)
    tool_paths = {}
    for steamapps in libraries:
        common = steamapps / "common"
        if not common.is_dir():
            continue
        for path in common.iterdir():
            launcher = path / "proton"
            internal = tool_ids.get(path.name)
            if path.is_dir() and internal and launcher.is_file() and os.access(launcher, os.X_OK):
                tool_paths[internal] = str(launcher.resolve())
    for root in roots:
        custom_tools = root / "compatibilitytools.d"
        if not custom_tools.is_dir():
            continue
        for path in custom_tools.iterdir():
            launcher = path / "proton"
            internal = tool_ids.get(path.name)
            if path.is_dir() and internal and launcher.is_file() and os.access(launcher, os.X_OK):
                tool_paths[internal] = str(launcher.resolve())
    display_by_id = {internal: display for display, internal in tool_ids.items()}
    for game in games.values():
        chosen = overrides.get(game["appid"], "")
        game["selected"] = display_by_id.get(chosen, chosen) if chosen else "Steam default"
        game["recommendation"] = display_by_id.get(chosen, chosen) if chosen else "Steam default"
        game["reason"] = "Current Steam override" if chosen else "Steam manages this game by default"
    return {"games": sorted(games.values(), key=lambda x: x["name"].casefold()), "tools": ordered,
            "tool_ids": tool_ids, "tool_paths": tool_paths, "baseline": baseline,
            "steam_found": bool(roots), "count": len(games)}


def dispatcher_dir() -> Path | None:
    for root in steam_roots():
        path = root / "compatibilitytools.d" / "proton-picker"
        if (path / "proton").is_file():
            return path
    return None


def official_rank(internal: str) -> tuple[int, int, str]:
    """Sort official stable Proton builds first, newest major version leading."""
    match = re.fullmatch(r"proton_(\d+)", internal or "")
    if match:
        return (0, -int(match.group(1)), internal.casefold())
    if internal == "proton_experimental":
        return (1, 0, internal.casefold())
    return (2, 0, internal.casefold())


def fallback_candidates(library: dict) -> list[str]:
    """List usable Proton launchers, newest official stable build first."""
    paths = library.get("tool_paths", {})
    ordered: list[str] = []

    def usable(path: str | None) -> bool:
        return bool(path) and Path(path).is_file() and os.access(path, os.X_OK)

    for internal, path in sorted(paths.items(), key=lambda item: official_rank(item[0])):
        if usable(path) and path not in ordered:
            ordered.append(path)
    return ordered


def fallback_chain(library: dict, tool_dir: Path | None = None) -> list[str]:
    """Fallback launchers in order, never including Proton Picker's own shim."""
    candidates = fallback_candidates(library)
    tool_dir = tool_dir or dispatcher_dir()
    if tool_dir:
        own_shim = (tool_dir / "proton").resolve()
        candidates = [path for path in candidates
                      if Path(path).resolve() != own_shim
                      and own_shim.parent not in Path(path).resolve().parents]
    return candidates


def write_dispatcher_cache(recommendations: dict[str, dict], library: dict,
                           tool_dir: Path, pins: dict[str, str] | None = None) -> dict:
    """Refresh the launch-time cache without editing Steam's per-game mappings."""
    paths = library.get("tool_paths", {})
    candidates = fallback_chain(library, tool_dir)
    if not candidates:
        log_event("sync failed: no installed Proton launcher is available as a fallback")
        return {"status": "error", "selected": 0,
                "message": "No installed Proton launcher is available as a fallback."}
    fallback = candidates[0]
    game_ids = {g["appid"] for g in library.get("games", [])
                if "windows" in g.get("oslist", "windows").casefold()}
    records: dict[str, str] = {}
    for appid, tool in (pins or {}).items():
        target = paths.get(tool)
        if appid in game_ids and target and os.access(target, os.X_OK):
            records[appid] = target
    for appid, recommendation in recommendations.items():
        if appid not in game_ids or not recommendation or appid in records:
            continue
        target = paths.get(recommendation.get("tool"))
        if target and os.access(target, os.X_OK):
            records[appid] = target
    lines = [f"{appid}\t{target}" for appid, target in sorted(records.items())]
    tool_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(tool_dir / "selections.tsv", "\n".join(lines) + "\n")
    atomic_write(tool_dir / "fallback.txt", fallback + "\n")
    atomic_write(tool_dir / "fallback-list.txt", "\n".join(candidates) + "\n")
    return {"status": "updated", "selected": len(records), "pinned": len(pins or {}),
            "fallback": fallback, "fallback_count": len(candidates),
            "message": f"Refreshed {len(records)} game choices."}


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def sync_dispatcher(recommendations: dict[str, dict] | None = None) -> dict:
    tool_dir = dispatcher_dir()
    if not tool_dir:
        return {"status": "not-installed", "message": "Install the Steam compatibility tool first."}
    library = get_library()
    if recommendations is None:
        recommendations = RECOMMENDATION_CACHE if time.time() - CACHE_UPDATED < 900 else fetch_recommendations()
    state = load_state()
    result = write_dispatcher_cache(recommendations, library, tool_dir, state.get("pins", {}))
    if result["status"] == "not-installed":
        state["enabled"] = False
    elif result["status"] == "updated":
        state["enabled"] = True
    state["last_sync"] = time.time()
    save_state(state)
    if result["status"] == "updated":
        install_autostart(True)
    log_event(f"sync {result['status']}: {result.get('message', '')}")
    return result


def set_pin(appid: str, tool: str | None) -> dict:
    """Pin a game to an installed build, or clear its pin when tool is empty."""
    library = get_library()
    state = load_state()
    pins = state.setdefault("pins", {})
    appid = str(appid)
    if tool:
        if tool not in library.get("tool_paths", {}):
            return {"status": "error", "message": "That Proton build is not installed."}
        pins[appid] = tool
    else:
        pins.pop(appid, None)
    save_state(state)
    result = sync_dispatcher()
    log_event(f"pin {appid} -> {tool or 'auto'}")
    return {"status": "pinned" if tool else "unpinned", "pins": pins, "sync": result}


def tool_sort_key(name: str):
    nums = tuple(int(n) for n in re.findall(r"\d+", name))
    return ("experimental" in name.lower(), "ge-proton" in name.lower(), nums, name.casefold())


def tool_for_report_version(version: str, tools: dict[str, str]) -> tuple[str, str, str | None] | None:
    label = version.strip()
    low = label.casefold()
    if "experimental" in low:
        for display, internal in tools.items():
            if "experimental" in display.casefold():
                return display, internal, None
        return "Proton Experimental", "proton_experimental", "1493710"
    is_ge = "ge-proton" in low or "proton-ge" in low or "wine-ge" in low
    wanted = tuple(int(x) for x in re.findall(r"\d+", low))
    if not wanted:
        return None
    candidates = []
    for display, internal in tools.items():
        display_low = display.casefold()
        ge_tool = "ge-proton" in display_low or "proton-ge" in display_low or "wine-ge" in display_low
        if ge_tool != is_ge:
            continue
        found = tuple(int(x) for x in re.findall(r"\d+", display_low))
        if found and found[0] == wanted[0] and (len(wanted) < 2 or len(found) < 2 or found[1] == wanted[1]):
            candidates.append((display, internal, None))
    if not candidates:
        if not is_ge and wanted[0] in {int(key) for key in OFFICIAL_PROTON_APP_IDS}:
            major = str(wanted[0])
            minor = wanted[1] if len(wanted) > 1 else 0
            return f"Proton {major}.{minor}", f"proton_{major}", OFFICIAL_PROTON_APP_IDS[major]
        return None
    return sorted(candidates, key=lambda item: tool_sort_key(item[0]), reverse=True)[0]


def rating_score(rating: str) -> float | None:
    return {"platinum": 5.0, "gold": 4.0, "silver": 3.0, "bronze": 2.0, "borked": 0.0}.get(rating.casefold())


def hardware_weight(report_gpu: str, local_gpu: str) -> float:
    if not report_gpu or not local_gpu:
        return 1.0
    report, local = report_gpu.casefold(), local_gpu.casefold()
    vendor = next((v for v in ("nvidia", "amd", "intel") if v in local), "")
    if vendor and vendor in report:
        # Same GPU model is a stronger signal than same vendor alone.
        model_terms = [x for x in re.findall(r"[a-z]+|\d+", local) if len(x) > 2]
        overlap = sum(term in report for term in model_terms)
        return 1.6 if overlap >= 2 else 1.25
    return 0.75


def rank_reports(reports: list[dict], tools: dict[str, str], local_gpu: str = "") -> dict | None:
    """Pick the strongest installed Proton build supported by recent reports."""
    now = time.time()
    grouped: dict[str, dict] = {}
    for report in reports:
        version = str(report.get("protonVersion") or "")
        tool = tool_for_report_version(version, tools)
        score = rating_score(str(report.get("rating") or ""))
        if not tool or score is None:
            continue
        display, internal, installer_appid = tool
        try:
            timestamp = float(report.get("timestamp", 0))
            age_days = max(0, (now - timestamp) / 86400) if timestamp else 730
        except (TypeError, ValueError):
            timestamp, age_days = 0, 730
        freshness = 0.5 ** (age_days / 365)
        weight = freshness * hardware_weight(str(report.get("gpu") or ""), local_gpu)
        item = grouped.setdefault(internal, {"display": display, "installer_appid": installer_appid,
                                               "sum": 0.0, "weight": 0.0, "count": 0,
                                               "latest": timestamp, "match_count": 0})
        item["sum"] += score * weight
        item["weight"] += weight
        item["count"] += 1
        item["latest"] = max(item["latest"], timestamp)
        if local_gpu and report.get("gpu") and hardware_weight(str(report["gpu"]), local_gpu) > 1:
            item["match_count"] += 1
    eligible = []
    for internal, item in grouped.items():
        if item["count"] < 2 or not item["weight"]:
            continue
        average = item["sum"] / item["weight"]
        if average >= 3.5:
            eligible.append((internal, item, average))
    if not eligible:
        return None
    internal, item, average = max(eligible, key=lambda row: (row[2], row[1]["count"], row[1]["latest"]))
    confidence = "high" if item["count"] >= 6 and average >= 4 and item["match_count"] >= 2 else "medium"
    return {"version": item["display"], "tool": internal, "installer_appid": item["installer_appid"],
            "installed": item["installer_appid"] is None, "score": round(average, 2),
            "reports": item["count"], "confidence": confidence,
            "reason": f"{item['count']} recent reports · {average:.1f}/5 compatibility score"}


def local_gpu_name() -> str:
    try:
        result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=3, check=False)
        for line in result.stdout.splitlines():
            if re.search(r"VGA compatible controller|3D controller|Display controller", line, re.I):
                return line.split(":", 2)[-1].strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def state_path() -> Path:
    return Path.home() / ".config/proton-picker/state.json"


def load_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"enabled": False, "managed": {}, "pending": False, "last_sync": 0}


def save_state(state: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(temp, path)


def log_event(message: str) -> None:
    """Append a diagnostic line so silent background failures leave a trace."""
    path = Path.home() / ".local/state/proton-picker/updater.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 256 * 1024:
            kept = path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
            path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as stream:
            stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            stream.write(f"{stamp} {message}\n")
    except OSError:
        pass


def steam_running() -> bool:
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            name = (proc / "comm").read_text(encoding="utf-8").strip().casefold()
            if name in {"steam", "steamwebhelper"}:
                return True
        except OSError:
            continue
    return False


def install_autostart(enabled: bool) -> None:
    path = Path.home() / ".config/autostart/proton-picker.desktop"
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    def desktop_arg(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    command = f'{desktop_arg(sys.executable)} {desktop_arg(str(ROOT / "app.py"))} --background'
    path.write_text("[Desktop Entry]\nType=Application\nName=Proton Picker\n"
                    f"Exec={command}\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n",
                    encoding="utf-8")


def fetch_recommendations() -> dict[str, dict]:
    global RECOMMENDATION_CACHE, CACHE_UPDATED
    library = get_library()
    gpu = local_gpu_name()
    eligible_games = [g for g in library["games"] if "windows" in g.get("oslist", "windows").casefold()]

    def fetch(game):
        appid = game["appid"]
        url = f"https://mdeguzis.github.io/proton-pulse-web/data/{appid}/latest.json"
        req = urllib.request.Request(url, headers={"User-Agent": "ProtonPicker/0.1 (local Steam companion)"})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.headers.get("Content-Type", "").startswith("text/html"):
                    return appid, {"unavailable": True}
                reports = json.loads(response.read().decode("utf-8"))
            if not isinstance(reports, list):
                return appid, {"unavailable": True}
            best = rank_reports(reports, library["tool_ids"], gpu)
            if best:
                best["source"] = "Proton Pulse community reports"
            return appid, best
        except (OSError, ValueError, urllib.error.URLError):
            return appid, {"unavailable": True}

    with ThreadPoolExecutor(max_workers=8) as pool:
        RECOMMENDATION_CACHE = dict(pool.map(fetch, eligible_games))
    CACHE_UPDATED = time.time()
    return RECOMMENDATION_CACHE


def quote_vdf(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "") + '"'


def dump_vdf(tree: dict, indent: int = 0) -> str:
    lines = []
    pad = "\t" * indent
    for key, value in tree.items():
        if isinstance(value, dict):
            lines.extend((f"{pad}{quote_vdf(key)}", f"{pad}{{"))
            lines.append(dump_vdf(value, indent + 1).rstrip("\n"))
            lines.append(f"{pad}}}")
        else:
            lines.append(f"{pad}{quote_vdf(key)}\t\t{quote_vdf(value)}")
    return "\n".join(lines) + "\n"


def _write_config(config_file: Path, tree: dict) -> None:
    fd, temp_name = tempfile.mkstemp(prefix="config.vdf.", dir=config_file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(dump_vdf(tree))
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(config_file, temp_name)
        os.replace(temp_name, config_file)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def set_default_compatibility_tool(config_file: Path, tool_name: str,
                                   clear_overrides: bool = False) -> dict:
    """Set Steam's default tool, optionally removing all per-game overrides."""
    if steam_running():
        raise SteamRunningError("Close Steam before changing its default compatibility tool.")
    if not config_file.is_file():
        raise FileNotFoundError(f"Steam config not found: {config_file}")
    tree = parse_vdf(config_file)
    if not tree:
        raise ValueError("Steam config could not be parsed; left it unchanged.")
    mapping = ensure_compat_mapping(tree)
    original = mapping.get("0")
    already_owned = isinstance(original, dict) and original.get("name") == tool_name
    removed = {}
    if clear_overrides:
        removed = {appid: mapping.pop(appid) for appid in list(mapping) if appid != "0"}
    if already_owned and not removed:
        return {"changed": False, "original": original, "backup": None, "removed": {}}
    backup = config_file.with_name(f"{config_file.name}.proton-picker-backup-{time.time_ns()}")
    shutil.copy2(config_file, backup)
    if not already_owned:
        priority = original.get("priority", "75") if isinstance(original, dict) else "75"
        mapping["0"] = {"name": tool_name, "config": "", "priority": str(priority)}
    _write_config(config_file, tree)
    return {"changed": True, "original": original, "backup": str(backup), "removed": removed}


def restore_default_compatibility_tool(config_file: Path, tool_name: str,
                                       original: dict | None,
                                       restore_overrides: dict | None = None) -> dict:
    """Restore a prior global choice only if Proton Picker still owns it."""
    if steam_running():
        raise SteamRunningError("Close Steam before restoring its default compatibility tool.")
    tree = parse_vdf(config_file)
    mapping = compat_mapping(tree)
    current = mapping.get("0")
    if not isinstance(current, dict) or current.get("name") != tool_name:
        return {"changed": False, "reason": "Steam's current default was changed after setup."}
    shutil.copy2(config_file, config_file.with_name(
        f"{config_file.name}.proton-picker-uninstall-backup-{time.time_ns()}"))
    if original is None:
        mapping.pop("0", None)
    else:
        mapping["0"] = original
    for appid, entry in (restore_overrides or {}).items():
        mapping.setdefault(appid, entry)
    _write_config(config_file, tree)
    return {"changed": True}


def complete_pending_setup() -> bool:
    state = load_state()
    if not state.get("pending_setup"):
        return not state.get("pending_setup", False)
    if steam_running():
        return False
    installation = state.get("installation", {})
    config_file = Path(installation.get("steam_config", ""))
    if not config_file.is_file():
        return False
    original = installation.get("original_default_mapping")
    tree = parse_vdf(config_file)
    current = compat_mapping(tree).get("0")
    if current != original and not (isinstance(current, dict) and current.get("name") == "proton-picker"):
        state["pending_setup"] = False
        state["setup_skipped_user_change"] = True
        save_state(state)
        return False
    selected = set_default_compatibility_tool(
        config_file, "proton-picker", clear_overrides=bool(state.get("clear_overrides")))
    if selected.get("backup"):
        installation["config_backup"] = selected["backup"]
    if selected.get("removed"):
        installation.setdefault("original_overrides", {}).update(selected["removed"])
    state["installation"] = installation
    state["pending_setup"] = False
    state["default_tool_installed"] = True
    save_state(state)
    return True


class SteamRunningError(RuntimeError):
    pass


def background_worker() -> None:
    while True:
        time.sleep(30)
        state = load_state()
        if state.get("pending_setup"):
            try:
                complete_pending_setup()
            except Exception as exc:
                print(f"Steam setup is still pending: {exc}")
            continue
        if not state.get("enabled"):
            continue
        installed = dispatcher_dir()
        fallback_missing = True
        if installed:
            try:
                first = (installed / "fallback.txt").read_text(encoding="utf-8").strip()
                fallback_missing = not first or not os.access(first, os.X_OK)
            except OSError:
                fallback_missing = True
        if fallback_missing or time.time() - float(state.get("last_sync", 0)) > 86400:
            try:
                sync_dispatcher(fetch_recommendations())
            except Exception as exc:
                log_event(f"auto-select sync crashed: {exc}")
                print(f"Auto-select sync failed: {exc}")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send(self, status: int, body: bytes, mime: str):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/library":
            library = get_library()
            library["pins"] = load_state().get("pins", {})
            chain = fallback_chain(library)
            if chain:
                internal = next((key for key, value in library.get("tool_paths", {}).items()
                                 if value == chain[0]), "")
                names = {internal_id: display for display, internal_id
                         in library.get("tool_ids", {}).items()}
                library["fallback"] = {"tool": internal,
                                       "name": names.get(internal, internal)}
            body = json.dumps(library).encode()
            return self.send(200, body, "application/json; charset=utf-8")
        if parsed.path == "/api/recommendations":
            result = fetch_recommendations()
            body = json.dumps({"recommendations": result, "checked": CACHE_UPDATED,
                               "gpu": local_gpu_name()}).encode()
            return self.send(200, body, "application/json; charset=utf-8")
        if parsed.path == "/api/status":
            state = load_state()
            state["steam_running"] = steam_running()
            state["dispatcher_installed"] = dispatcher_dir() is not None
            body = json.dumps(state).encode()
            return self.send(200, body, "application/json; charset=utf-8")
        if parsed.path == "/api/protondb":
            ids = parse_qs(parsed.query).get("ids", [""])[0].split(",")
            results = {}
            def fetch_summary(appid):
                if not appid.isdigit():
                    return appid, {"tier": "unavailable"}
                req = urllib.request.Request(
                    f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json",
                    headers={"User-Agent": "ProtonPicker/0.1 (local Steam companion)"})
                try:
                    with urllib.request.urlopen(req, timeout=5) as response:
                        data = json.loads(response.read().decode("utf-8"))
                        return appid, {"tier": data.get("tier", "unknown"),
                                       "confidence": data.get("confidence", ""),
                                       "trendingTier": data.get("trendingTier", ""),
                                       "bestReportedTier": data.get("bestReportedTier", "")}
                except (OSError, ValueError, urllib.error.URLError):
                    return appid, {"tier": "unavailable"}
            with ThreadPoolExecutor(max_workers=6) as pool:
                results.update(pool.map(fetch_summary, ids[:80]))
            return self.send(200, json.dumps(results).encode(), "application/json; charset=utf-8")
        if parsed.path == "/" or parsed.path == "/index.html":
            return self.send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        if parsed.path == "/style.css":
            return self.send(200, (ROOT / "style.css").read_bytes(), "text/css; charset=utf-8")
        if parsed.path == "/app.js":
            return self.send(200, (ROOT / "app.js").read_bytes(), "text/javascript; charset=utf-8")
        self.send(404, b"Not found", "text/plain")

    def do_POST(self):
        route = urlparse(self.path).path
        if route not in ("/api/auto", "/api/pin"):
            return self.send(404, b"Not found", "text/plain")
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 4096)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if route == "/api/pin":
                appid = str(payload.get("appid", "")).strip()
                if not appid.isdigit():
                    raise ValueError("A numeric Steam app id is required.")
                result = set_pin(appid, payload.get("tool") or None)
                if result["status"] == "error":
                    return self.send(400, json.dumps(result).encode(),
                                     "application/json; charset=utf-8")
                result["state"] = load_state()
                return self.send(200, json.dumps(result).encode(),
                                 "application/json; charset=utf-8")
            enabled = bool(payload.get("enabled"))
            if enabled:
                result = sync_dispatcher()
            else:
                state = load_state()
                state["enabled"] = False
                save_state(state)
                install_autostart(False)
                result = {"status": "disabled",
                          "message": "Background updates paused. Proton Picker remains selected in Steam until you change Steam Play settings."}
            result["state"] = load_state()
            return self.send(200, json.dumps(result).encode(), "application/json; charset=utf-8")
        except (ValueError, OSError, KeyError) as exc:
            return self.send(400, json.dumps({"status": "error", "message": str(exc)}).encode(),
                             "application/json; charset=utf-8")


def main():
    if "--version" in sys.argv:
        print(f"Proton Picker {VERSION}")
        return
    if "--background" in sys.argv:
        lock_base = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        lock_base.mkdir(parents=True, exist_ok=True)
        with (lock_base / "proton-picker-background.lock").open("w") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            background_worker()
        return
    address = ("127.0.0.1", 8765)
    server = ThreadingHTTPServer(address, Handler)
    print("Proton Picker is running at http://127.0.0.1:8765 (Ctrl+C to stop)")
    try:
        import webbrowser
        threading.Timer(0.7, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
