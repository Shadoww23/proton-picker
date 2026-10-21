# Proton Picker

Proton Picker is designed to choose a Proton build at Steam launch time. After setup, the player clicks **Play** as usual: Steam starts the Proton Picker compatibility tool, which routes that game's launch to a cached Proton build. A background updater refreshes the per-game choices; there is no version prompt during launch.

Proton Picker is part of [Brlinkin](https://shadoww23.github.io/brlinkin/), a small suite of local-first tools for Linux gaming and game releases.

## Common problems this solves

- Steam keeps launching the same Proton version for every game.
- Per-game Proton overrides get lost when Steam rewrites its config.
- A game stops launching after an external games drive is unmounted.
- You want to pin one Proton build per game without editing Steam settings.

See [docs/PROBLEMS.md](docs/PROBLEMS.md) for checks, logs, and honest limits. GTA IV controller and Dead Space stutter are diagnostic paths, not guaranteed fixes.

## Requirements

- Linux desktop Steam (Steam Deck/Decky and Flatpak Steam are not yet validated)
- Python 3.10 or newer
- At least one Proton build installed in Steam

## Setup

Close Steam and run this once:

```sh
./install.sh
```

or:

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

## License and price

Proton Picker 0.1 is free to download and use under the proprietary freeware
terms in [LICENSE](LICENSE): no redistribution, modification, or resale.
Donations are optional. The alpha is provided as-is; see the license for the
warranty and liability terms.

Proton Picker is not affiliated with Valve Corporation. See
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

More tools: [Brlinkin](https://shadoww23.github.io/brlinkin/) · [ReleaseGuard](https://github.com/Shadoww23/releaseguard).
