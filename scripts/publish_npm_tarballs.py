#!/usr/bin/env python3
"""Publish AICodex npm tarballs, skipping versions already on npm."""

import argparse
import json
import re
import subprocess
import tarfile
from pathlib import Path


PACKAGE_RE = re.compile(r"^(?:@[^/]+/)?[^@]+@(.+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--access",
        default="public",
        help="npm access level to pass to npm publish.",
    )
    parser.add_argument(
        "--tag",
        default="",
        help="Dist-tag for the root package. Platform packages use platform tags.",
    )
    parser.add_argument("tarballs", nargs="+", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for tarball in args.tarballs:
        publish_tarball(tarball.resolve(), access=args.access, root_tag=args.tag)
    return 0


def publish_tarball(tarball: Path, *, access: str, root_tag: str) -> None:
    if not tarball.is_file():
        raise FileNotFoundError(f"npm tarball not found: {tarball}")

    metadata = npm_pack_metadata(tarball)
    package_name = metadata["name"]
    package_version = metadata["version"]
    tag = dist_tag_for_tarball(tarball.name, package_version, root_tag)

    if npm_version_exists(package_name, package_version):
        print(f"Skipping {package_name}@{package_version}; already published", flush=True)
        return

    cmd = ["npm", "publish", str(tarball), "--access", access]
    if tag:
        cmd.extend(["--tag", tag])

    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def npm_pack_metadata(tarball: Path) -> dict[str, str]:
    with tarfile.open(tarball, "r:gz") as archive:
        package_json = archive.extractfile("package/package.json")
        if package_json is None:
            raise RuntimeError(f"Missing package/package.json in {tarball}")
        metadata = json.loads(package_json.read().decode("utf-8"))

    if not isinstance(metadata, dict):
        raise RuntimeError(f"Unexpected npm metadata for {tarball}: {metadata!r}")

    for key in ("name", "version"):
        if not isinstance(metadata.get(key), str):
            raise RuntimeError(f"Missing npm metadata field {key!r} for {tarball}")
    return metadata


def npm_version_exists(package_name: str, package_version: str) -> bool:
    result = subprocess.run(
        ["npm", "view", f"{package_name}@{package_version}", "version", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        existing = json.loads(result.stdout or "null")
    except json.JSONDecodeError:
        return False
    return existing == package_version


def dist_tag_for_tarball(filename: str, package_version: str, root_tag: str) -> str:
    platform_version_suffix = platform_suffix(package_version)
    if platform_version_suffix:
        return platform_version_suffix
    if filename == f"codex-npm-{package_version}.tgz":
        return root_tag
    if filename.startswith("codex-npm-") and filename.endswith(f"-{package_version}.tgz"):
        return filename.removeprefix("codex-npm-").removesuffix(f"-{package_version}.tgz")
    return root_tag


def platform_suffix(package_version: str) -> str:
    match = PACKAGE_RE.match(f"package@{package_version}")
    if match is None:
        return ""
    version = match.group(1)
    if "-" not in version:
        return ""
    suffix = version.split("-", 1)[1]
    if suffix.startswith(("linux-", "darwin-", "win32-")):
        return suffix
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
