# Proton Picker: common Steam and Proton problems

These are the problems Proton Picker is designed to address, with concrete
checks. It is a compatibility-tool router, not a graphics or controller driver;
game-specific issues still need their own testing.

## Steam uses the same Proton version for every game

Steam applies its global compatibility tool to games without an override.
Proton Picker replaces that global choice with one entry that reads the game's
app ID at launch, then starts your pinned build, a strongly supported build, or
the newest installed official Proton.

Check which build actually ran:

```sh
grep -i "proton-picker" ~/.local/share/Steam/logs/console_log.txt | tail
grep -i "Proton 11.0/proton" ~/.local/share/Steam/logs/console_log.txt | tail
```

## A per-game Proton override is being ignored or keeps disappearing

Steam rewrites `config.vdf` when it exits. Proton Picker avoids per-game
overrides entirely: pins live in `~/.config/proton-picker/state.json` and are
merged into the launch cache. If you want every game managed by the picker,
run the installer and accept "remove existing per-game overrides". It backs up
the config and records removed mappings for uninstall.

Inspect the current mapping:

```sh
python3 -c "import app,json; print(json.dumps(app.compat_mapping(app.parse_vdf(app.Path.home()/'.local/share/Steam/config/config.vdf')), indent=1))"
```

## I want one Proton tool for all Steam Windows games

1. Close Steam.
2. Run `./install.sh` from the Proton Picker download.
3. Accept the prompt to remove per-game overrides.
4. Restart Steam once.
5. Leave Steam Play set to **Proton Picker (automatic)**.

## A pinned Proton build is not being used

- Confirm the game is a Windows game and the pin is visible in the dashboard.
- Confirm the build is installed in Steam and its `proton` file is executable.
- Restart Steam after changing global compatibility settings.
- Check the cache: `cat ~/.local/share/Steam/compatibilitytools.d/proton-picker/selections.tsv`
- Check the updater log: `~/.local/state/proton-picker/updater.log`

## The game stopped launching after an external drive was unmounted

Proton Picker writes a ranked fallback list, not a single hard-coded path. If
the preferred build disappears, the next usable official Proton is used. A
last-resort scan checks the standard Steam folders. If no build is usable, the
launcher exits 126 instead of starting the wrong one.

## "No usable Proton build" or exit code 126

Install at least one Proton build in Steam, mount the drive that contains it,
then run:

```sh
cat ~/.local/share/Steam/compatibilitytools.d/proton-picker/fallback-list.txt
```

The first existing, executable path in that list is used.

## The dashboard shows no games

- Proton Picker currently targets desktop Steam, not Flatpak Steam.
- Check that Steam was found: the dashboard status should say "Steam library connected".
- Runtime and Proton app IDs are intentionally hidden; only games are listed.

## GTA IV controller does not work on Linux

Proton Picker only routes the game to a Proton build. Controller behavior comes
from Steam Input, the game, and the Proton build. Check Steam's controller
config first:

```sh
grep -i "Loaded Config for Local Selection Path for App ID 12210" ~/.local/share/Steam/logs/console_log.txt
```

If a community config is loaded, test the same controller layout with a pinned
different Proton build before changing game files. This is a diagnostic path,
not a confirmed fix.

## Dead Space stutters on Linux

Stutter can come from shader compilation, frame pacing, or the Proton build.
Proton Picker makes A/B testing practical: pin one build, play the same section,
then pin another. Let Steam finish shader processing before comparing. This is
not a guaranteed performance fix.

## Steam Deck and Flatpak Steam

Not validated in this alpha. Do not install on a Deck or Flatpak Steam library
until those paths are tested.
