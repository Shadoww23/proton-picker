# AUR package

`proton-picker` installs the unmodified release archive from
<https://github.com/Shadoww23/proton-picker/releases/tag/v0.1.0-alpha> into
`/opt/proton-picker` and exposes `proton-picker` / `proton-picker-uninstall`.

The package does not run the installer as root. Run `proton-picker` as your
user; it installs the compatibility tool into your Steam directory and backs up
the Steam config first.

Build and verify (from a clean Arch container or an Arch host):

```sh
makepkg -f
namcap proton-picker-*.pkg.tar.zst
sudo pacman -U proton-picker-*.pkg.tar.zst
proton-picker --help
proton-picker-uninstall
```

`makepkg` runs the unit tests in `check()`.

## Verified build (2026-10-21)

Built and installed in a clean `archlinux:latest` container:

```sh
makepkg -f --nodeps --noconfirm
namcap proton-picker-0.1.0_alpha-1-any.pkg.tar.zst
sudo pacman -U proton-picker-0.1.0_alpha-1-any.pkg.tar.zst
```

- `check()` unit tests passed.
- `namcap` reported no errors. The remaining warnings are false positives for
  the local `app` module, `/bin/sh`, and `python3`.
- Smoke tests passed: `proton-picker --help` and `proton-picker-uninstall`.

## Publishing to the AUR

The package name `proton-picker` is unclaimed. Publishing needs an AUR account
with your SSH public key added at <https://aur.archlinux.org/account/>.

```sh
makepkg --printsrcinfo > .SRCINFO
git clone ssh://aur@aur.archlinux.org/proton-picker.git
cp PKGBUILD .SRCINFO proton-picker/
cd proton-picker && git add PKGBUILD .SRCINFO && git commit -m "Initial import"
git push
```
