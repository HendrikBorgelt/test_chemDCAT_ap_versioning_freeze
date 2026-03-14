# Versioning Freeze — Implementation Guide for chem-dcat-ap

This folder contains **drop-in artefacts** for implementing the versioning freeze
pipeline in the real [chem-dcat-ap](https://github.com/nfdi-de/chem-dcat-ap)
repository. Everything here is production-ready (using `w3id.org/nfdi-de/…` URLs)
and was developed and validated in the test repos
[test_dcat_ap_plus_versioning_freeze](https://github.com/HendrikBorgelt/test_dcat_ap_plus_versioning_freeze) and
[test_chemDCAT_ap_versioning_freeze](https://github.com/HendrikBorgelt/test_chemDCAT_ap_versioning_freeze).

---

## The problem being solved

`chem_dcat_ap.yaml`, `chemical_reaction_ap.yaml`, and `material_entities_ap.yaml`
all import dcat-ap-plus via:

```yaml
imports:
  - dcatapplus:latest/schema/dcat_ap_plus
```

`latest` is a **live alias** that mike updates on every dcat-ap-plus release.
This means every previously deployed version of chem-dcat-ap silently switches
to the new dcat-ap-plus the moment it is released — retroactively breaking any
version that was not compatible with the new dcat-ap-plus.

The fix: at release time, pin the import to the **specific dcat-ap-plus version**
that `latest` resolves to *at that moment*.

---

## How the freeze works

```
chem-dcat-ap tag pushed (e.g. v1.2.0)
        │
        ▼
CI: fetch https://nfdi-de.github.io/dcat-ap-plus/versions.json
        │  → find version with alias "latest"  (e.g. "v0.9.2")
        ▼
CI: in-place replace in working copy (NOT committed to git)
        │  src/chem_dcat_ap/schema/*.yaml
        │  dcatapplus:latest/  →  dcatapplus:v0.9.2/
        ▼
CI: just gen-doc  →  mike deploy v1.2.0
        │  deployed schema at /v1.2.0/schema/ now has frozen import
        ▼
CI: semver check — is v1.2.0 ≥ current "latest"?
        ├─ yes → also set "latest" alias to v1.2.0
        └─ no  → leave "latest" pointing to newer version
```

**Source files are never modified.** The `main` branch always contains
`dcatapplus:latest/schema/dcat_ap_plus` for development convenience.
Only the snapshot on GitHub Pages carries the pinned import.

---

## Folder structure

```
for_direct_implementation_at_chemdcat_ap/
  README.md                      ← This file
  workflows/
    deploy-docs.yaml             ← Drop-in for .github/workflows/deploy-docs.yaml
  scripts/
    freeze_imports.py            ← Add to scripts/ in chem-dcat-ap
    should_update_latest.py      ← Add to scripts/ in chem-dcat-ap
```

---

## Implementation steps

### 1. Add the scripts

Create a `scripts/` directory in the root of chem-dcat-ap (if it does not exist)
and copy both Python files from `scripts/` here into it.

### 2. Replace the deploy-docs workflow

Replace `.github/workflows/deploy-docs.yaml` with `workflows/deploy-docs.yaml`
from this folder.

> **Note on action versions:** The production workflow uses stable floating
> tags (`actions/checkout@v4`, `astral-sh/setup-uv@v5`, etc.) rather than the
> pinned minor versions used in the test repo. Update these to whatever your
> project currently uses.

### 3. Verify locally (optional but recommended)

Run the freeze script in dry-run style to confirm it resolves the alias
correctly — then discard the change:

```bash
# Check which version 'latest' currently resolves to
uv run python scripts/freeze_imports.py \
    --schema-dir src/chem_dcat_ap/schema \
    --prefix dcatapplus \
    --from-alias latest \
    --versions-url https://nfdi-de.github.io/dcat-ap-plus/versions.json

# Revert — the CI never commits this change, but locally you need to undo it
git checkout src/chem_dcat_ap/schema/
```

### 4. Release as usual

The release workflow is **unchanged** — just push a version tag:

```bash
git tag v1.2.0
git push origin v1.2.0
```

The CI will automatically freeze the import and handle the `latest` alias.

---

## Design decisions FAQ

### Does the schema `id:` need to be versioned?

**No.** The `id:` field is the stable namespace for concepts defined in the
schema (e.g. `chemdcatap:SubstanceSample`). Versioning it would change the
URI for every concept on every release, breaking RDF compatibility. The
GitHub Pages path already provides versioning context — the deployed file at
`/v1.2.0/schema/chem_dcat_ap.yaml` *is* the versioned artefact. Consumers
who need version-pinned imports reference that path directly.

### Do tests need versioning?

**No.** Tests run against the current branch's schema. On the `main` branch
they always use `dcatapplus:latest/`, which is correct for development. At
release time the freeze runs *before* `just gen-doc`, so any schema-level
validation performed during doc generation also exercises the frozen import.

If you want to additionally run `just test` against the frozen schema in CI
(recommended for critical releases), add a `just test` step *after* the
freeze step in `deploy-docs.yaml`.

### Does test data need versioning?

**No.** Test data files (`tests/data/valid/*.yaml`) live on the branch and
are implicitly versioned by git. When a breaking schema change is introduced,
the test data is updated in the same PR. On a maintenance branch (see below)
the test data reflects that version's schema.

### How do I work on v1.10.4 while v2.0.1 is already live?

Use a **maintenance branch**:

```bash
# Create a v1.x maintenance branch from the last v1 tag
git checkout -b v1.x v1.10.3
```

On the `v1.x` branch, **commit the frozen import** to git (unlike the
`main`-branch approach where only CI freezes it). This ensures that
`just test` works correctly locally and in CI for v1.x:

```bash
# On the v1.x branch, run the freeze and commit the result
uv run python scripts/freeze_imports.py \
    --schema-dir src/chem_dcat_ap/schema \
    --prefix dcatapplus \
    --from-alias latest \
    --versions-url https://nfdi-de.github.io/dcat-ap-plus/versions.json

git add src/chem_dcat_ap/schema/
git commit -m "chore: freeze dcatapplus import to <version> for v1.x maintenance"
```

Now apply your fix, then release:

```bash
git tag v1.10.4
git push origin v1.x v1.10.4
```

The `should_update_latest.py` script will detect that v1.10.4 < v2.0.1 and
**will not overwrite the `latest` alias**. The docs at `/v1.10.4/` will be
deployed cleanly alongside `/v2.0.1/` and `/latest/`.

---

## Summary table

| Concern | Approach |
|---|---|
| Import freeze scope | `src/chem_dcat_ap/schema/*.yaml` only |
| When freeze is committed | **Never on `main`** (CI working copy only); **committed on maintenance branches** |
| Schema `id:` | Unchanged — unversioned stable namespace |
| `latest` alias promotion | Semver-gated via `should_update_latest.py` |
| Test data | Branch-versioned via git, no explicit versioning needed |
| Maintenance releases | `v1.x` branch + committed frozen import |
