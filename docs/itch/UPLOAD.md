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

Draft project: <https://brlinkin.itch.io/proton-picker> (Linux, free).

Build channel pushed:

```sh
butler push dist/ProtonPicker-0.1.0-alpha.zip Brlinkin/proton-picker:linux --userversion 0.1.0-alpha
```

Remaining in the itch.io editor before publishing:

1. Confirm the project type/classification is a tool, not a game.
2. Confirm platform Linux and price free with donations enabled.
3. Paste the page copy from `PAGE.md`, including the Brlinkin suite link.
4. Upload `cover.png`, `icon.png`, and `dashboard.png`.
5. Add the alpha warning and non-affiliation disclaimer.
6. Test the download from a logged-out browser, then publish.

## Before each release

- Run `python3 -m unittest test_proton.py test_dispatcher.py`.
- Run `python3 scripts/package.py`.
- Extract the archive in a clean directory and run `python3 app.py --version`.
- Confirm no `__pycache__`, `.git`, `dist`, state files, or logs are archived.
- Verify `sha256sum -c ProtonPicker-0.1.0-alpha-SHA256SUMS.txt`.
- Confirm the version in `app.py` matches the tag.
