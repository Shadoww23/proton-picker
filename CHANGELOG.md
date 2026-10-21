# Changelog

## 0.1.0-alpha — 2026-10-21

Initial public alpha.

- Steam compatibility-tool shim routes Windows games to an installed Proton
  build at launch time.
- Background updater builds recommendations from public compatibility reports
  and the local GPU.
- Fallback order prefers the newest installed official stable Proton; a ranked
  backup list and last-resort scan handle missing drives and builds.
- Installer asks whether to remove per-game Proton overrides (default: remove),
  backs up `config.vdf`, and records removed mappings for uninstall.
- Dashboard shows installed games, compatibility tiers, the effective fallback,
  and a per-game build pin control.
- Uninstall restores the previous global Steam choice and removed overrides
  when Proton Picker still owns them.
- 20 unit tests cover dispatch, fallback resilience, pins, override cleanup,
  and restore behavior.
