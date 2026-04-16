# Implement versioned sub-module imports and downstream freeze pipeline

## Problem statement

`chem-dcat-ap` defines several sub-modules — `chemical_entities_ap`, `chemical_reaction_ap`, etc. — that are currently referenced by downstream schemas using bare local imports:

```yaml
imports:
  - chemical_entities_ap
  - chemical_reaction_ap
```

Because bare imports carry no version information, downstream consumers (sub-profiles, specialized schemas built on top of chem-dcat-ap) cannot determine *which version* of that sub-module was in use when a class was defined. This creates ambiguity in schema inheritance chains: a downstream schema might have been authored against one definition of `chemdcatap:SubstanceSample` but silently runs against a different one.

The same problem applies to the upstream `dcat-ap-plus` dependency: without a pinned version in the prefix URI, the deployed schema silently drifts whenever `dcat-ap-plus` releases a new version.

---

## The inheritance chain

```
dcat-ap-plus  →  chem-dcat-ap  →  specialized-chem-schema-A
                                →  specialized-chem-schema-B
```

Each arrow is a schema import. If intermediate schemas use floating (unversioned) imports:

- The chain cannot be reproduced deterministically. Running the same schema validator months later may produce different results.
- Published datasets validated against `specialized-chem-schema-A v1.0.0` may fail validation against newer versions if the upstream imports drifted.
- Automated tools that follow import chains (e.g. JSON-LD processors, OWL reasoners, LinkML generators) cannot determine provenance from the schema files alone.

---

## Why versioning matters for downstream

**Class URI stability.** Downstream profiles inherit from classes like `chemdcatap:SubstanceSample`. The class URI resolves to a specific definition only if the `chemdcatap` prefix itself is version-pinned. With a bare import and an unversioned prefix, `chemdcatap:SubstanceSample` resolves to whatever the current deployment says — not to the definition that was current when the downstream schema was authored.

**Silent breakage.** If `chemical_entities_ap` adds a required slot or changes a range constraint between releases, downstream profiles that were valid against the old version silently become invalid against the new one. There is no signal at the import level that anything changed.

**Traceability in triple stores.** RDF datasets declare their type using class URIs. If a dataset was produced using `chem-dcat-ap v0.2.0`, triples like `ex:mySample a chemdcatap:SubstanceSample` should resolve to the class definition as of `v0.2.0`. Version-pinned prefix URIs (`chemdcatap: https://.../chemistry/v0.2.0/`) make this possible; floating ones do not.

**Deterministic downstream freeze.** When a downstream schema repo implements its own freeze pipeline (see the inheritance chain above), it needs to know the exact version of chem-dcat-ap sub-modules it depends on — not just the top-level chem-dcat-ap version tag. Versioned prefix URIs in released schemas give downstream implementors a stable, inspectable dependency declaration.

---

## What the freeze pipeline delivers

At release time, the CI transforms the development-form schemas into fully version-pinned release artifacts:

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

**Released artifact (on GitHub Pages, e.g. at `/v0.3.0/schema/`):**
```yaml
prefixes:
  dcatapplus: https://w3id.org/nfdi-de/dcat-ap-plus/v0.3.0/
  chemdcatap: https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/v0.3.0/

imports:
  - dcatapplus:schema/dcat_ap_plus
  - chemdcatap:schema/chemical_entities_ap
  - chemdcatap:schema/chemical_reaction_ap
```

Key properties:
- Class URIs like `chemdcatap:SubstanceSample` now resolve to `https://w3id.org/nfdi-de/dcat-ap-plus/chemistry/v0.3.0/SubstanceSample` in released schemas.
- The `dcat-ap-plus` version pinned in the `dcatapplus` prefix reflects whichever version was current when the release was made.
- Source files on `main` keep bare imports and unversioned prefixes for development ergonomics — local testing and tooling continue to work without modifications.
- The CI handles the entire transformation automatically at release time. No manual editing required.

Additionally, the daily upstream check workflow monitors `dcat-ap-plus` releases and automatically opens a PR to pin the `dcatapplus` prefix in `main` source, so maintainers are notified of upstream changes before the next chem-dcat-ap release.

---

## Implementation steps

See `for_direct_implementation_at_chemdcat_ap/README.md` for the complete implementation guide, including:

1. Adding `scripts/freeze_imports.py` and `scripts/should_update_latest.py`
2. Enabling "Allow GitHub Actions to create and approve pull requests" in repository settings
3. Replacing `.github/workflows/deploy-docs.yaml` and adding `handle-upstream-release.yaml`
4. Optionally adding `check-schema-compatibility.yaml`, `scripts/check_compatibility.py`, and `docs/compatibility.md` for the weekly compatibility badge and matrix

---

## Why not Pattern A: always-versioned imports on `main`

An alternative approach would be to keep versioned imports directly in the source files on `main`:

```yaml
imports:
  - chemdcatap:v0.2.0/schema/chemical_entities_ap   # always versioned
```

This was considered and rejected for the following reasons:

**Breaks local development testing.** When a developer modifies `chemical_entities_ap` and wants to test whether a downstream schema that imports it still validates, the import needs to resolve to the *local file* — not to a previously deployed version on GitHub Pages. With versioned imports on `main`, `linkml-run-examples` and `gen-doc` would always resolve to the deployed version, making it impossible to test local changes end-to-end without a full release cycle.

**Creates a chicken-and-egg problem for new sub-modules.** Adding a new sub-module requires: (a) deploying it to get a versioned URL, (b) importing it at that versioned URL. But deploying requires a release, and releasing requires imports to be set up. With bare imports on `main`, a new sub-module can be developed and tested locally before its first release.

**No benefit during development.** The point of version pinning is to ensure that *released* artifacts are reproducible. Development builds on `main` are by definition the current tip — there is no reproducibility requirement there. Pinning imports on `main` would add maintenance overhead (updating import versions after every sub-module change) with no corresponding benefit.

The chosen approach (bare imports on `main`, version pinned at release time by CI) gives the best of both worlds: frictionless development and fully reproducible released artifacts.
