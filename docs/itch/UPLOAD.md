# Publishing checklist — Proton Picker

## Files

- `dist/ProtonPicker-0.1.0-alpha.zip` — itch.io upload.
- `dist/ProtonPicker-0.1.0-alpha.tar.gz` — GitHub release alternative.
- `dist/ProtonPicker-0.1.0-alpha-SHA256SUMS.txt` — publish beside downloads.
- `docs/itch/cover.png`, `icon.png`, `dashboard.png` — storefront assets.

## GitHub

The repository is `Shadoww23/proton-picker`. Pushing tag `v0.1.0-alpha` runs
`.github/workflows/release.yml`, tests the project, rebuilds the archives, and
creates a GitHub release.

## itch.io

Live: <https://brlinkin.itch.io/proton-picker> (Linux, free with donations).

Build channel pushed:

```sh
butler push dist/ProtonPicker-0.1.0-alpha.zip Brlinkin/proton-picker:linux --userversion 0.1.0-alpha
```

Published with classification Tool, page copy from `PAGE.md`, the Brlinkin
suite link, cover/icon/screenshot, and the alpha/non-affiliation disclaimers.

## Before each release

- Run `python3 -m unittest test_proton.py test_dispatcher.py`.
- Run `python3 scripts/package.py`.
- Extract the archive in a clean directory and run `python3 app.py --version`.
- Confirm no `__pycache__`, `.git`, `dist`, state files, or logs are archived.
- Verify `sha256sum -c ProtonPicker-0.1.0-alpha-SHA256SUMS.txt`.
- Confirm the version in `app.py` matches the tag.
