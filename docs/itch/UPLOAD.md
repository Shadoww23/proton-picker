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

1. Create a downloadable project named **Proton Picker**.
2. Set the classification to tool/development, platform Linux, price free with
   donations enabled.
3. Upload `ProtonPicker-0.1.0-alpha.zip`; mark it Linux.
4. Paste the page copy from `PAGE.md`.
5. Upload `cover.png`, `icon.png`, and `dashboard.png`.
6. Add a clear alpha warning and the non-affiliation disclaimer.
7. Test the download from a logged-out browser, then publish.

Butler alternative:

```sh
butler push dist/ProtonPicker-0.1.0-alpha.zip <user>/proton-picker:linux --userversion 0.1.0-alpha
```

## Before each release

- Run `python3 -m unittest test_proton.py test_dispatcher.py`.
- Run `python3 scripts/package.py`.
- Extract the archive in a clean directory and run `python3 app.py --version`.
- Confirm no `__pycache__`, `.git`, `dist`, state files, or logs are archived.
- Verify `sha256sum -c ProtonPicker-0.1.0-alpha-SHA256SUMS.txt`.
- Confirm the version in `app.py` matches the tag.
