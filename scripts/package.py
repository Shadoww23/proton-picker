#!/usr/bin/env python3
"""Build Proton Picker's source ZIP, tarball, and SHA-256 checksums."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import tarfile
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXECUTABLES = {"compatibility-tool/proton", "install.sh"}
PACKAGE_FILES = (
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "THIRD-PARTY-NOTICES.md",
    "app.js",
    "app.py",
    "index.html",
    "install.py",
    "install.sh",
    "style.css",
    "test_dispatcher.py",
    "test_proton.py",
    "uninstall.py",
    "compatibility-tool/compatibilitytool.vdf",
    "compatibility-tool/proton",
    "compatibility-tool/toolmanifest.vdf",
)
PACKAGE_DIRECTORIES = ("scripts",)
EXCLUDED_PARTS = {"__pycache__", ".git", ".venv", "dist", ".pytest_cache"}


def project_version() -> str:
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(r'(?m)^VERSION\s*=\s*"([^"]+)"\s*$', source)
    if match is None:
        raise ValueError("could not read VERSION from app.py")
    return match.group(1)


def package_sources() -> list[Path]:
    paths = [PROJECT_ROOT / name for name in PACKAGE_FILES]
    for directory_name in PACKAGE_DIRECTORIES:
        directory = PROJECT_ROOT / directory_name
        if not directory.is_dir():
            raise FileNotFoundError(f"required package directory is missing: {directory}")
        for path in directory.rglob("*"):
            parts = path.relative_to(PROJECT_ROOT).parts
            if any(part in EXCLUDED_PARTS for part in parts):
                continue
            if path.is_symlink():
                raise ValueError(f"refusing to package a symbolic link: {path}")
            if path.is_file() and path.suffix != ".pyc":
                paths.append(path)
    unique = {path.relative_to(PROJECT_ROOT).as_posix(): path for path in paths}
    for name, path in unique.items():
        if not path.is_file():
            raise FileNotFoundError(f"required package file is missing: {name}")
    return [unique[name] for name in sorted(unique, key=str.casefold)]


def add_zip(archive: zipfile.ZipFile, source: Path) -> None:
    name = source.relative_to(PROJECT_ROOT).as_posix()
    info = zipfile.ZipInfo(name)
    info.date_time = (1980, 1, 1, 0, 0, 0)
    mode = 0o100755 if name in EXECUTABLES else 0o100644
    info.external_attr = mode << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def create_zip(destination: Path, sources: list[Path]) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in sources:
            add_zip(archive, source)
    with zipfile.ZipFile(destination) as archive:
        damaged = archive.testzip()
        if damaged is not None:
            raise OSError(f"created ZIP failed its CRC check: {damaged}")


def create_tarball(destination: Path, sources: list[Path]) -> None:
    with tarfile.open(destination, "w:gz", compresslevel=9, format=tarfile.PAX_FORMAT) as archive:
        for source in sources:
            name = source.relative_to(PROJECT_ROOT).as_posix()
            info = archive.gettarinfo(str(source), arcname=name)
            info.mtime = 315532800
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if name in EXECUTABLES else 0o644
            with source.open("rb") as handle:
                archive.addfile(info, handle)


def write_checksums(paths: list[Path], destination: Path) -> None:
    lines = []
    for path in sorted(paths, key=lambda item: item.name.casefold()):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        lines.append(f"{digest.hexdigest()}  {path.name}")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_archive(destination: Path, sources: list[Path], kind: str) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        if kind == "zip":
            create_zip(temporary, sources)
        else:
            create_tarball(temporary, sources)
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "dist",
                        help="destination directory (default: project dist/)")
    args = parser.parse_args(argv)

    try:
        version = project_version()
        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        sources = package_sources()
        zip_path = output_dir / f"ProtonPicker-{version}.zip"
        tar_path = output_dir / f"ProtonPicker-{version}.tar.gz"
        checksum_path = output_dir / f"ProtonPicker-{version}-SHA256SUMS.txt"
        build_archive(zip_path, sources, "zip")
        build_archive(tar_path, sources, "tgz")
        write_checksums([zip_path, tar_path], checksum_path)
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
        with tarfile.open(tar_path) as archive:
            tar_names = archive.getnames()
        expected = [source.relative_to(PROJECT_ROOT).as_posix() for source in sources]
        if names != expected or tar_names != expected:
            raise OSError("archive contents do not match the allowlist")
    except (OSError, ValueError) as exc:
        print(f"error: packaging failed: {exc}")
        return 1

    print(f"ZIP: {zip_path}")
    print(f"Tarball: {tar_path}")
    print(f"Checksums: {checksum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
