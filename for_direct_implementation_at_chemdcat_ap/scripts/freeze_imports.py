#!/usr/bin/env python3
"""Freeze LinkML schema imports to specific resolved versions.

At release time the CI calls this script to:

1. Pin the ``dcatapplus`` prefix value from
   ``dcatapplus: {base}/`` to ``dcatapplus: {base}/{version}/``
   (version moves into the prefix URI, not the import path).

2. Strip any version/alias segment from ``dcatapplus:`` import paths
   e.g. ``dcatapplus:latest/schema/`` -> ``dcatapplus:schema/``

3. Pin the ``chemdcatap`` prefix value from
   ``chemdcatap: {base}/`` to ``chemdcatap: {base}/{version}/``

4. Convert bare local sub-module imports to ``chemdcatap:schema/`` imports
   e.g. ``  - chemical_entities_ap`` -> ``  - chemdcatap:schema/chemical_entities_ap``

The modifications are made to the *working copy only* — they are **not**
committed back to git. Source files stay in their development form
(bare imports, unversioned prefix) while every released GitHub Pages
snapshot carries fully versioned, reproducible imports.

Usage (auto-resolve dcatapplus version via mike versions.json,
       freeze chemdcatap to the current release tag):

    uv run python scripts/freeze_imports.py \\
        --schema-dir src/chem_dcat_ap/schema \\
        --dcatapplus-base https://w3id.org/nfdi-de/dcat-ap-plus \\
        --versions-url https://HendrikBorgelt.github.io/test_dcat_ap_plus_versioning_freeze/versions.json \\
        --chemdcatap-base https://w3id.org/nfdi-de/dcat-ap-plus/chemistry \\
        --chemdcatap-version v0.2.0

Usage (explicit dcatapplus version, no chemdcatap freeze):

    uv run python scripts/freeze_imports.py \\
        --schema-dir src/chem_dcat_ap/schema \\
        --dcatapplus-base https://w3id.org/nfdi-de/dcat-ap-plus \\
        --dcatapplus-version v0.3.0

Exit codes
----------
0  Success. Machine-parseable KEY=VALUE lines are printed on stdout:
     FROZEN_VERSION=<dcatapplus_version>           (if dcatapplus was frozen)
     FROZEN_CHEMDCATAP_VERSION=<chemdcatap_version> (if chemdcatap was frozen)
1  Error — details on stderr.
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def resolve_alias(versions_url: str, alias: str = "latest") -> str:
    """Return the version string that currently carries *alias* in mike's versions.json."""
    try:
        with urllib.request.urlopen(versions_url, timeout=15) as resp:
            versions = json.load(resp)
    except Exception as exc:
        raise RuntimeError(f"Could not fetch {versions_url}: {exc}") from exc

    for entry in versions:
        if alias in entry.get("aliases", []):
            return entry["version"]

    available = [e.get("version") for e in versions]
    raise ValueError(
        f"Alias '{alias}' not found in {versions_url}. "
        f"Available versions: {available}"
    )


def freeze_dcatapplus_prefix(text: str, base: str, version: str) -> str:
    """Pin the dcatapplus prefix value: base/ -> base/version/

    Replaces lines like:
      dcatapplus: https://w3id.org/nfdi-de/dcat-ap-plus/
    with:
      dcatapplus: https://w3id.org/nfdi-de/dcat-ap-plus/v0.3.0/
    """
    old = f"dcatapplus: {base}/\n"
    new = f"dcatapplus: {base}/{version}/\n"
    return text.replace(old, new)


def strip_dcatapplus_import_path_token(text: str) -> str:
    """Remove any version/alias token from dcatapplus import paths.

    Handles patterns like:
      - dcatapplus:latest/schema/foo   -> dcatapplus:schema/foo
      - dcatapplus:v0.3.0/schema/foo  -> dcatapplus:schema/foo

    Only matches when there is a token (non-colon, non-slash chars) between
    'dcatapplus:' and '/schema/' — does not touch lines already in the
    'dcatapplus:schema/' form.
    """
    return re.sub(r"dcatapplus:[^:/\s]+/schema/", "dcatapplus:schema/", text)


def freeze_chemdcatap_prefix(text: str, base: str, version: str) -> str:
    """Pin the chemdcatap prefix value: base/ -> base/version/

    Replaces lines like:
      chemdcatap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/
    with:
      chemdcatap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/v0.2.0/
    """
    old = f"chemdcatap: {base}/\n"
    new = f"chemdcatap: {base}/{version}/\n"
    return text.replace(old, new)


def convert_bare_imports_to_chemdcatap(text: str) -> str:
    """Convert bare local sub-module imports to chemdcatap-prefixed form.

    A bare import line looks like:
      - chemical_entities_ap
    and becomes:
      - chemdcatap:schema/chemical_entities_ap

    Only YAML list item lines (2-6 leading spaces, then '- ') whose value
    part contains no colon and no slash are converted. The special name
    'linkml:types' is never touched (it already has a colon).
    """
    lines = text.splitlines(keepends=True)
    result = []
    for line in lines:
        # Match lines: 2-6 spaces + '- ' + bare name (letters/digits/underscores/hyphens)
        m = re.match(r'^( {2,6}- )([A-Za-z][A-Za-z0-9_-]+)(\s*)$', line)
        if m and ':' not in m.group(2) and '/' not in m.group(2):
            result.append(f"{m.group(1)}chemdcatap:schema/{m.group(2)}{m.group(3)}\n"
                          if not line.endswith('\n')
                          else f"{m.group(1)}chemdcatap:schema/{m.group(2)}\n")
        else:
            result.append(line)
    return "".join(result)


def process_file(
    yaml_file: Path,
    dcatapplus_base: str | None,
    dcatapplus_version: str | None,
    chemdcatap_base: str | None,
    chemdcatap_version: str | None,
) -> bool:
    """Apply all requested freezes to one file. Returns True if the file changed."""
    text = yaml_file.read_text(encoding="utf-8")
    original = text

    if dcatapplus_base and dcatapplus_version:
        text = freeze_dcatapplus_prefix(text, dcatapplus_base, dcatapplus_version)
        text = strip_dcatapplus_import_path_token(text)

    if chemdcatap_base and chemdcatap_version:
        text = freeze_chemdcatap_prefix(text, chemdcatap_base, chemdcatap_version)
        text = convert_bare_imports_to_chemdcatap(text)

    if text != original:
        yaml_file.write_text(text, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--schema-dir",
        required=True,
        help="Directory containing the schema YAML files to update.",
    )
    p.add_argument(
        "--dcatapplus-base",
        default=None,
        help=(
            "Base URL for the dcatapplus prefix, no trailing slash. "
            "e.g. https://w3id.org/nfdi-de/dcat-ap-plus"
        ),
    )
    p.add_argument(
        "--dcatapplus-version",
        default=None,
        help=(
            "Explicit version to pin dcatapplus to (e.g. 'v0.3.0'). "
            "If omitted and --versions-url is given, the 'latest' alias is resolved."
        ),
    )
    p.add_argument(
        "--chemdcatap-base",
        default=None,
        help=(
            "Base URL for the chemdcatap prefix, no trailing slash. "
            "e.g. https://w3id.org/nfdi-de/dcat-ap-plus/chemistry"
        ),
    )
    p.add_argument(
        "--chemdcatap-version",
        default=None,
        help="Version to pin chemdcatap to (e.g. the current release tag 'v0.2.0').",
    )
    p.add_argument(
        "--versions-url",
        default=None,
        help=(
            "URL to the mike versions.json of the upstream dcat-ap-plus repo. "
            "Used to auto-resolve the 'latest' alias when --dcatapplus-version "
            "is not given."
        ),
    )
    return p


def main() -> int:
    args = build_parser().parse_args()

    schema_dir = Path(args.schema_dir)
    if not schema_dir.is_dir():
        print(f"ERROR: not a directory: {schema_dir}", file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Resolve dcatapplus version
    # ------------------------------------------------------------------
    dcatapplus_version: str | None = None
    if args.dcatapplus_base:
        if args.dcatapplus_version:
            dcatapplus_version = args.dcatapplus_version
        elif args.versions_url:
            print(f"Resolving 'latest' alias from: {args.versions_url}")
            try:
                dcatapplus_version = resolve_alias(args.versions_url, "latest")
            except Exception as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            print(f"  -> resolved to: {dcatapplus_version}")
        else:
            print(
                "ERROR: --dcatapplus-base given but neither --dcatapplus-version "
                "nor --versions-url was provided.",
                file=sys.stderr,
            )
            return 1

    chemdcatap_version: str | None = args.chemdcatap_version

    if not dcatapplus_version and not chemdcatap_version:
        print(
            "ERROR: nothing to do — provide at least one of: "
            "--dcatapplus-version (or --versions-url), --chemdcatap-version.",
            file=sys.stderr,
        )
        return 1

    # ------------------------------------------------------------------
    # Process all YAML files in schema_dir
    # ------------------------------------------------------------------
    changed_files: list[str] = []
    for yaml_file in sorted(schema_dir.glob("*.yaml")):
        if process_file(
            yaml_file,
            args.dcatapplus_base,
            dcatapplus_version,
            args.chemdcatap_base,
            chemdcatap_version,
        ):
            changed_files.append(yaml_file.name)

    if changed_files:
        print(f"Modified files: {', '.join(changed_files)}")
    else:
        print(f"No files changed in {schema_dir}")

    # ------------------------------------------------------------------
    # Emit machine-parseable KEY=VALUE lines for shell callers
    # ------------------------------------------------------------------
    if dcatapplus_version:
        print(f"FROZEN_VERSION={dcatapplus_version}")
    if chemdcatap_version:
        print(f"FROZEN_CHEMDCATAP_VERSION={chemdcatap_version}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
