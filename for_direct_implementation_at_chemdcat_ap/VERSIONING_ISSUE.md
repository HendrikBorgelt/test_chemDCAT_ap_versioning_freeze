# Implement versioned sub-module imports and downstream freeze pipeline

## Problem statement

`chem-dcat-ap` defines several sub-modules — `chemical_entities_ap`, `chemical_reaction_ap`, etc. — that are currently referenced using bare local imports:

```yaml
imports:
  - chemical_entities_ap
  - chemical_reaction_ap
```

Bare imports carry no version information, so downstream schemas cannot determine which version of a sub-module was in use when a class was defined. The same problem applies to the upstream `dcat-ap-plus` dependency: without a pinned version in the `dcatapplus:` prefix URI, the deployed schema silently drifts whenever `dcat-ap-plus` releases a new version.

---

## The inheritance chain

```
dcat-ap-plus  →  chem-dcat-ap  →  coremeta4cat
                               →  dcat-ap+labactions
                               →  visualization tool
                               →  ckan ?
```

Each arrow is a schema import. Unversioned imports anywhere in this chain make it impossible to reproduce validation results deterministically, or for downstream schemas to declare a stable dependency.

---

## What the freeze pipeline delivers

At release time, CI transforms the development-form schemas into fully version-pinned release artifacts.

**Source (on `main`, development form):**
```yaml
prefixes:
  dcatapplus: https://w3id.org/nfdi-de/dcat-ap-plus/v0.3.0/
  chemdcatap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/
  chemical_entities_ap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/entity/
  chemical_reaction_ap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/reaction/

imports:
  - dcatapplus:schema/dcat_ap_plus
  - chemical_entities_ap
  - chemical_reaction_ap
```

**Released artifact (on GitHub Pages / w3id.org, at `/chemistry/v0.3.0/schema/`):**
```yaml
prefixes:
  dcatapplus: https://w3id.org/nfdi-de/dcat-ap-plus/v0.3.0/
  chemdcatap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/v0.3.0/
  chemical_entities_ap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/entity/v0.3.0/
  chemical_reaction_ap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/reaction/v0.3.0/

imports:
  - dcatapplus:schema/dcat_ap_plus
  - chemical_entities_ap:schema/chemical_entities_ap
  - chemical_reaction_ap:schema/chemical_reaction_ap
```

Each sub-schema import resolves via its own prefix to the correct versioned w3id path.

Note: `id:` fields are **not** versioned. The schemas are used as SHACL shape definitions
rather than OWL ontologies; the `id:` field does not determine shape node URIs (those come
from the `default_prefix`, i.e. the `chemdcatap:` prefix value, which is versioned). Version
identity is already expressed by the schema's `version:` attribute and the versioned prefixes.

The `dcatapplus:` prefix is already pinned on `main` (via the `handle-upstream-release`
workflow; see below). The `chemdcatap:`, per-module prefixes, and bare sub-module imports
are all frozen at release time.

### How the test repo differs

The test repo (`test_chemDCAT_ap_versioning_freeze`) hosts all sub-schemas under a single
GitHub Pages root without w3id redirects. There is only one `chemdcatap:` prefix, and all
sub-schemas are deployed at `/{version}/schema/`. No per-module prefix declarations exist in
the source schemas, so all bare imports fall back to `chemdcatap:schema/name`. The
`--sub-module-base` flag is therefore not used in the test repo workflow.

Example of a frozen test-repo artifact:
- [chem_dcat_ap.yaml (v0.4.5)](https://hendrikborgelt.github.io/test_chemDCAT_ap_versioning_freeze/v0.4.5/schema/chem_dcat_ap.yaml)
- [chemical_entities_ap.yaml (v0.4.5)](https://hendrikborgelt.github.io/test_chemDCAT_ap_versioning_freeze/v0.4.5/schema/chemical_entities_ap.yaml)
- [chemical_reaction_ap.yaml (v0.4.5)](https://hendrikborgelt.github.io/test_chemDCAT_ap_versioning_freeze/v0.4.5/schema/chemical_reaction_ap.yaml)

---

## Two-phase pipeline

**Phase 1 — `build-docs` job (runs on every release tag push):**

since we want to make sure the schema is technically valid, we should do regular testing before the schema is transfered to the github pages. However since the test would run into a chicken and the egg problem, where it can't validate a schema published on the github pages, since it hasn't validated that it is correct, and thereby has not transfered those schemas to github, we need to do local testing. We can assume that the freezing of the import statements should not cause any issues, therefore testing the correctness of the schema can be tested with local imports.
1. `gen-doc` runs on raw schemas; bare local imports resolve against adjacent files — no network needed.
2. Freeze step transforms the working copy in place:
   - `chemdcatap:` prefix → versioned w3id URL / gh-pages url for the test repo
   - Sub-schema own-namespace prefixes → versioned w3id URLs / gh-pages url for the test repo
   - Bare local imports → `chemdcatap:schema/X` CURIE form
   - Copies frozen files to `docs/schema/` to replace any stale copies made by the `gen-doc` step.
3. `mike deploy` publishes the frozen schemas to gh-pages.

**Phase 2 — `post-deploy-validate` job (runs after `build-docs`, tags only):**

Since we don't want to introduce an errors with the freezing of the import statements, a post publishing validation is executed here. This is done in a "test" branch, where the schemas can be loaded into and are tested with the respective w3ids artefacts in place on the github pages.
1. Polls gh-pages until the new version is accessible (30 s interval, 20 attempts).
2. Re-applies the identical freeze (idempotent — already frozen from Phase 1).
3. Validates every frozen schema with `gen-yaml` — sub-schema CURIEs resolve against w3id / gh-pages, which now carries consistently versioned prefixes.
4. Pushes frozen schemas to reference branch `schema-release/{tag}` (always pushed, even on failure, for maintainer inspection).
5. Opens a GitHub Issue on validation failure.

---

## New workflows

Three new or significantly changed workflow files are introduced.

### `deploy-docs.yaml` (modified)

Adds the two-phase freeze pipeline described above to the existing `build-docs` job, and introduces the new `post-deploy-validate` job that runs after every successful release deploy.

### `handle-upstream-release.yaml` (new)

Runs **daily at 08:00 UTC**. Checks whether `dcat-ap-plus` has published a new `latest` version since the source schemas were last pinned.

**What it does:**

1. Fetches `versions.json` from the `dcat-ap-plus` GitHub Pages site and reads the version tagged `latest`.
2. Reads the current `dcatapplus:` prefix value from the source schemas to determine the currently pinned version.
3. Skip guard A: if the source is already pinned to the upstream latest, stops silently.
4. Skip guard B: if an open PR for this exact version already exists, stops silently.
5. Creates branch `freeze/dcatapplus-{version}`, commits the updated `dcatapplus:` prefix value, and opens a PR with a CI checklist.
6. Posts a notice comment on every other open PR so contributors are aware of the upstream change.

**Why should we not b informed by `dcat-ap-plus`:** The workflow polls the existing public `versions.json` file. It requires no secrets, webhooks, or permissions beyond the default `GITHUB_TOKEN` scoped to this repository. This keeps the change fully self-contained in `chem-dcat-ap`. 

**Why polling rather than a push event from `dcat-ap-plus`:** A push-based approach would require adding a downstream-dispatch step to the `dcat-ap-plus` release workflow and granting it a cross-repository secret. Polling from the child repo avoids any changes to the parent repo and needs no cross-repo permissions. The daily schedule introduces at most a 24-hour lag, which is acceptable.

**One-time repository setup required:**
Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests" must be enabled.

### `check-schema-compatibility.yaml` (new)

Runs **weekly on Mondays at 06:00 UTC**. For every deployed version of `chem-dcat-ap`, fetches the frozen `dcatapplus:` version from the published schema and checks whether that upstream version is still accessible on GitHub Pages.

**Why a compatibility page:** After release, the upstream schema it depends on could theoretically be removed or moved (e.g. if `dcat-ap-plus` deletes old versions from gh-pages). Downstream consumers of older `chem-dcat-ap` versions would then face broken imports without any visible warning. The compatibility matrix and badge give maintainers and users an at-a-glance view of which released versions are still fully resolvable.

**Outputs:**
- `badge.json` — shields.io endpoint badge pushed to the `gh-pages` root; embed in the README:
  ```markdown
  ![schema deps](https://img.shields.io/endpoint?url=https://nfdi-de.github.io/chem-dcat-ap/badge.json)
  ```
- `compatibility.html` — standalone HTML matrix pushed to the `gh-pages` root.
- `compatibility.md` — MkDocs-compatible markdown committed to `main`; rebuilt into the docs site by the subsequent `deploy-docs` run.
- GitHub Issue with label `schema-dep-stale` opened when `latest` becomes stale; closed automatically when it resolves.

---

## Compatibility table: tracking freeze-action success

The compatibility table includes a **Freeze validated** column showing whether the `post-deploy-validate` job succeeded for each released version.

**How it works:** At the end of every `post-deploy-validate` run (success or failure), the workflow writes a `freeze-status.json` file to the gh-pages root. Each key is a version string; each value records `validated` (true/false) and a timestamp. `check_compatibility.py` fetches this file at the start of each weekly check and uses it to populate the column. Versions released before this feature was added show `—` (no data).

This is particularly useful if a release is tagged but validation fails silently — maintainers can see at a glance that the frozen schemas for that version should be inspected.

---

## Implementation steps

See `for_direct_implementation_at_chemdcat_ap/README.md` for the complete guide. In summary:

1. Add `scripts/freeze_imports.py`, `scripts/check_compatibility.py`, and `scripts/should_update_latest.py`.
2. Enable "Allow GitHub Actions to create and approve pull requests" in repository settings.
3. Replace `.github/workflows/deploy-docs.yaml` with the version in `workflows/`.
4. Add `.github/workflows/handle-upstream-release.yaml` from `workflows/`.
5. Add `.github/workflows/check-schema-compatibility.yaml` from `workflows/`.

---

## Why not always-versioned imports on `main`

Keeping versioned imports directly in source would break local development: `gen-doc` and `linkml-run-examples` would always resolve to a previously-deployed version rather than the local file being edited. It also creates a chicken-and-egg problem for new sub-modules (a URL cannot exist before the first deploy). Bare imports on `main` with CI-managed versioning at release time gives the best of both worlds.

---

## Future: PyPI-based dependency management

The current polling and auto-PR approach for upstream releases is a pragmatic solution given that `dcat-ap-plus` is distributed as a GitHub Pages site rather than a PyPI package. If `dcat-ap-plus` were published to PyPI in the future, this workflow could be replaced by standard dependency-management tooling such as Dependabot or a `bump-my-version` action — which handle version pinning, PR creation, and CI checks natively. The current polling approach is not intended as a permanent architecture, but is the most practical option until PyPI publication is feasible.
