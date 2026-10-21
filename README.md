# Proton Picker

Proton Picker is designed to choose a Proton build at Steam launch time. After setup, the player clicks **Play** as usual: Steam starts the Proton Picker compatibility tool, which routes that game's launch to a cached Proton build. A background updater refreshes the per-game choices; there is no version prompt during launch.

## Setup

Close Steam and run this once on Linux desktop Steam:

```sh
python3 install.py
```

The installer registers Proton Picker as Steam's default compatibility tool. It asks whether to remove existing per-game Proton overrides (default: remove, so every game goes through Proton Picker) and backs up `config.vdf` before changing it. Removed overrides are recorded so uninstall can restore them. Pass `--clear-overrides` or `--keep-overrides` for a non-interactive install. Restart Steam once so it discovers the new tool; after that, click Play as usual.

The installer places a custom Steam compatibility tool in the Steam folder and enables a per-user background updater. It seeds the fallback with the newest installed official stable Proton, so third-party builds such as GE-Proton are never chosen implicitly. If no Proton launcher is installed, setup stops without changing Steam.

## Launch and updates

Steam invokes `compatibility-tool/proton` for a Windows game. The dispatcher reads `STEAM_COMPAT_APP_ID`, looks up that game in `selections.tsv`, and executes the corresponding installed Proton launcher with Steam's original arguments. Pins from the dashboard take precedence, then strong recommendations, then the fallback. It fails clearly if that fallback disappears, rather than silently launching an arbitrary build.

The updater uses recent Proton community reports and locally detected GPU information to choose among installed builds. If data is sparse or weak, the game uses the fallback. Only app IDs are sent to the public report source; GPU matching remains local.

The dispatcher writes a ranked list of every usable installed build, not just one fallback path. If the preferred build disappears (for example an external games drive is unmounted), the next usable build is used, and the dispatcher scans the standard Steam folders as a last resort. Background sync failures are appended to `~/.local/state/proton-picker/updater.log`.

The local dashboard (`python3 app.py`) is optional. It lists the library, shows compatibility ratings, and lets you pin a game to an installed build (or return it to automatic selection). Pins are stored in `~/.config/proton-picker/state.json` and merged into the launch cache; no Steam per-game override is required. The dashboard is not part of the Play flow.

## Current alpha limits

- Steam's launch path is verified up to the point where Steam hands off to the tool: on 2026-10-21, launching an app with no per-game override invoked `compatibilitytools.d/proton-picker/proton`, which routed to the fallback `Proton 11.0/proton`. A full session into gameplay was not completed (Steam paused on its shader-cache prompt). Unit tests still exercise dispatch with stub Proton scripts.
- Recommendations are based on one public report mirror and its latest per-game page. Report coverage varies; a lack of evidence uses the fallback.
- The Steam tool must be selected once as the default compatibility tool. Steam Deck/Decky and Flatpak Steam are not yet validated.
- Removing an override in the installer discards Steam's own setting for that game; the previous mapping is kept in `state.json` and restored on uninstall.
- The updater currently routes only to Proton builds that are already installed. It does not install missing Proton versions automatically.

Run `python3 uninstall.py` with Steam closed to remove the tool, restore the previous global Steam choice when Proton Picker still owns that setting, and restore per-game overrides removed during setup. The uninstaller leaves a later Steam default change untouched.
