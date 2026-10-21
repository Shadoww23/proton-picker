# itch.io page copy — Proton Picker 0.1 Alpha

## Title

Proton Picker

## Tagline

Right Proton. Every launch.

## Short description

A Steam compatibility tool that routes every Windows game to a Proton build
automatically, with per-game pins and a fallback that still works when a drive
disappears.

## Page description

Proton Picker sits between Steam and your installed Proton builds. Steam still
shows one compatibility tool; when you press Play, Proton Picker reads the game's
app ID and launches the build you pinned, the build with strong community
evidence behind it, or the newest installed official Proton.

No version prompt. No editing Steam Play settings for every game. No hosted
account.

Part of [Brlinkin](https://shadoww23.github.io/brlinkin/), a small suite of
local-first tools for Linux gaming and game releases.

### Common problems it addresses

- Steam launches the same Proton version for every game.
- Per-game Proton overrides disappear when Steam rewrites its config.
- A game stops launching after an external games drive is unmounted.
- You want to pin one Proton build per game without editing Steam settings.

Full checks, log paths, and limits:
[Proton Picker troubleshooting](https://github.com/Shadoww23/proton-picker/blob/main/docs/PROBLEMS.md).
GTA IV controller and Dead Space stutter are diagnostic paths, not guaranteed
fixes.

### What it does

- Routes Steam Windows-game launches through an installed Proton build.
- Uses recent public compatibility reports and your local GPU to suggest a
  build when the evidence is strong.
- Falls back to the newest official stable Proton instead of an arbitrary
  third-party build.
- Keeps a ranked backup list, so an unmounted games drive or removed build does
  not leave the game unable to start.
- Lets you pin any installed build per game from a local dashboard.
- Offers to remove existing per-game Proton overrides so the picker really does
  cover every game. It backs up Steam's config and records removed mappings so
  uninstall can restore them.
- Runs a lightweight background updater; failures are logged locally.

### Requirements

- Linux desktop Steam. Steam Deck/Decky and Flatpak Steam are not yet validated.
- Python 3.10 or newer.
- At least one Proton build installed in Steam.
- Close Steam before running the installer.

### Install

1. Extract the download.
2. Close Steam.
3. Run `./install.sh` (or `python3 install.py`).
4. Answer the prompt about per-game overrides.
5. Restart Steam once, then press Play as usual.

Uninstall with `python3 uninstall.py` while Steam is closed.

### Alpha limits

- This is an early alpha. A complete gameplay session and controller behavior
  still need broader testing.
- Recommendations depend on public report coverage. Weak or missing evidence
  deliberately falls back to official Proton rather than guessing.
- Only installed Proton builds are routed; the app does not install missing
  Proton versions automatically.
- The dashboard requires the local Python app; it is optional for launching
  games.

### Price and license

Free alpha with optional donations. Proprietary freeware: no redistribution,
modification, or resale. See `LICENSE` and `THIRD-PARTY-NOTICES.md`.

Proton Picker is not affiliated with or endorsed by Valve Corporation. Steam and
Proton are trademarks of their respective owners.

## Suggested itch.io setup

- Project type: downloadable tool.
- Platform: Linux.
- Price: free with donations enabled.
- Upload: `ProtonPicker-0.1.0-alpha.zip`.
- Cover: `cover.png` (630×500). Icon: `icon.png` (512×512).
- Screenshot: `dashboard.png` (1280×800).
- Tags: linux, steam, proton, utility, tool.
- Do not use Valve, Steam, or Proton logos in page art.

## Support request

Ask for Linux distribution, Steam client type (desktop/Flatpak), GPU, the game
app ID, whether the game is pinned, and relevant lines from
`~/.local/state/proton-picker/updater.log`. Do not ask for Steam credentials.
