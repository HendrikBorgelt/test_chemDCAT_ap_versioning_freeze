# Implement versioned sub-module imports and downstream freeze pipeline

## Problem statement

`chem-dcat-ap` defines several sub-modules — `chemical_entities_ap`, `chemical_reaction_ap`, etc. — that are currently referenced using bare local imports:

```yaml
imports:
  - chemical_entities_ap
  - chemical_reaction_ap
```

Bare imports carry no version information, so downstream schemas cannot determine which version of a sub-module was in use when a class was defined. The same problem applies to the upstream `dcat-ap-plus` dependency: without a pinned version in the `dcatapplus:` prefix URI, the deployed schema silently drifts whenever `dcat-ap-plus` releases a new version.

This is the same problem that was resolved in `dcat-ap-plus` — this issue tracks the equivalent fix for `chem-dcat-ap`.

---

## The inheritance chain

```
dcat-ap-plus  →  chem-dcat-ap  →  specialized-chem-schema-A
                               →  specialized-chem-schema-B
```

Each arrow is a schema import. Unversioned imports anywhere in this chain make it impossible to reproduce validation results deterministically, or for downstream schemas to declare a stable dependency.

---

## What the freeze pipeline delivers

At release time, CI transforms the development-form schemas into fully version-pinned release artifacts.

**Source (on `main`, development form):**
```yaml
prefixes:
  dcatapplus: https://w3id.org/nfdi-de/dcat-ap-plus/
  chemdcatap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/

imports:
  - dcatapplus:latest/schema/dcat_ap_plus
  - chemical_entities_ap
  - chemical_reaction_ap
```

**Released artifact (on GitHub Pages, at `/v0.3.0/schema/`):**
```yaml
prefixes:
  dcatapplus: https://w3id.org/nfdi-de/dcat-ap-plus/v0.3.0/
  chemdcatap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/v0.3.0/

imports:
  - dcatapplus:schema/dcat_ap_plus
  - chemdcatap:schema/chemical_entities_ap
  - chemdcatap:schema/chemical_reaction_ap
```

Note: `id:` fields are **not** versioned — they are stable RDF namespace identifiers. Versioning them would break RDF compatibility for all consumers of the schema's named classes.

Source files on `main` retain bare imports and unversioned prefixes for development ergonomics. CI handles the entire transformation automatically at release time.

---

## Two-phase pipeline

**Phase 1 — `build-docs` job:**
1. `gen-doc` runs on raw schemas (bare imports resolve locally).
2. Freeze step transforms the working copy (no commit to `main`).
3. `mike deploy` publishes the frozen schemas to gh-pages.

**Phase 2 — `post-deploy-validate` job (runs after `build-docs`):**
1. Waits for gh-pages to serve the new files (polls every 30 s, 20 attempts max).
2. Re-applies the same freeze to a fresh checkout (idempotent).
3. Validates frozen schemas with `gen-yaml` — sub-schema imports are fetched from gh-pages, which now carries consistently versioned prefixes.
4. Pushes frozen schemas to reference branch `schema-release/{tag}` (always, even on failure, for maintainer inspection).
5. Opens a GitHub Issue on validation failure.

---

## Implementation steps

See `for_direct_implementation_at_chemdcat_ap/README.md` for the complete guide. In summary:

1. Add `scripts/freeze_imports.py` and `scripts/should_update_latest.py`.
2. Enable "Allow GitHub Actions to create and approve pull requests" in repository settings.
3. Replace `.github/workflows/deploy-docs.yaml` with the version in `workflows/`.
4. Replace `.github/workflows/check-schema-compatibility.yaml` with the version in `workflows/`.

---

## Why not always-versioned imports on `main`

Keeping versioned imports directly in source would break local development: `gen-doc` and `linkml-run-examples` would always resolve to a previously-deployed version rather than the local file being edited. It also creates a chicken-and-egg problem for new sub-modules (a URL cannot exist before the first deploy). Bare imports on `main` with CI-managed versioning at release time gives the best of both worlds.
