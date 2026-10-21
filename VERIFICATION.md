# Proton Picker verification record

Date: 2026-10-21
Environment: Fedora 44, kernel 7.2.8-200.fc44.x86_64, Python 3.14.8, Steam desktop client.

This record documents what was actually observed. It is not a full gameplay test.

## Verified: Steam invokes Proton Picker and routes to the fallback

Steam was configured with Proton Picker as the global compatibility tool and with
no per-game override for App ID 12210 (GTA IV). Launching that app produced this
process chain:

```
reaper SteamLaunch AppId=12210 ...
  SteamLinuxRuntime_4/_v2-entry-point --verb=run --
    compatibilitytools.d/proton-picker/proton
      python3 /run/media/kasean/Games/SteamLibrary/steamapps/common/Proton 11.0/proton
        run .../legacycompat/iscriptevaluator.exe legacycompat\evaluatorscript_12210.vdf
```

The `proton-picker/proton` entry point was invoked by Steam and executed the
fallback build (`Proton 11.0`). Steam then paused on its shader-cache prompt, so
the game did not reach gameplay in this test.

## Verified: per-game overrides are preserved

The GTA IV override (`12210 -> proton_experimental`) was removed only for the
launch test and restored afterwards. The parsed `CompatToolMapping` after
restoration:

```json
{
  "241930": {"name": "proton_11", "config": "", "priority": "250"},
  "0": {"name": "proton-picker", "config": "", "priority": "75"},
  "1693980": {"name": "proton_9", "config": "", "priority": "250"},
  "12210": {"name": "proton_experimental", "config": "", "priority": "250"}
}
```

## Verified: fallback resilience

The updater now writes `fallback-list.txt` with every usable installed build,
excluding the Proton Picker shim itself. Tests confirm that:

- a missing selected build falls back to the configured fallback,
- a missing fallback path moves to the next entry in the list,
- a last-resort scan finds a Steam-installed Proton,
- the shim fails with exit 126 when nothing usable exists.

20 unit tests pass (`python3 -m unittest test_proton.py test_dispatcher.py`).

## Update: override management and pins

The installer now asks whether to remove per-game overrides (default: remove)
and records them in `state.json` for uninstall. Tests cover removal, restoration,
clearing when Proton Picker is already the default, pin precedence over
recommendations, and official-stable fallback ordering ahead of GE builds.
The earlier "overrides are preserved" observation describes the pre-update
installer; it is kept here as a record of that run.

## Not verified

- A complete game launch into gameplay or a multi-hour session.
- Steam Deck, Decky, and Flatpak Steam.
- Automatic installation of a missing Proton build.
