# Downstream Notification — Implementation Guide for dcat-ap-plus

This folder contains the one change needed in
[dcat-ap-plus](https://github.com/nfdi-de/dcat-ap-plus) to complete the
versioning freeze pipeline:  after each release, dcat-ap-plus notifies
chem-dcat-ap so it can automatically open a compatibility freeze PR.

---

## What changes and why

The existing `deploy-docs.yaml` in dcat-ap-plus is unchanged except for one
new step added at the end: **"Notify downstream repos of new release"**.

When a version tag is pushed to dcat-ap-plus this step sends a
`repository_dispatch` event to chem-dcat-ap carrying the new version string.
The `handle-upstream-release` workflow in chem-dcat-ap receives this event
and takes over from there (creates the freeze branch, opens the PR, notifies
open PRs).

---

## Folder structure

```
for_direct_implementation_at_dcat_ap_plus/
  README.md             ← This file
  workflows/
    deploy-docs.yaml    ← Drop-in for .github/workflows/deploy-docs.yaml
```

---

## Implementation steps

### 1. Create the PAT

You need a Personal Access Token that allows dcat-ap-plus to trigger a
workflow event in chem-dcat-ap.

**Recommended: fine-grained PAT** (least privilege)

1. Go to GitHub → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token
2. Set **Resource owner** to the `nfdi-de` organisation (or your account)
3. Set **Repository access** → Only select repositories → `nfdi-de/chem-dcat-ap`
4. Under **Permissions → Repository permissions** set **Contents** to
   `Read and write`
   *(This permission is what `repository_dispatch` requires on the target repo)*
5. Give the token a meaningful name, e.g. `dcat-ap-plus → chem-dcat-ap dispatch`
6. Copy the token — you will not see it again

**Alternative: classic PAT** with `repo` scope (broader but simpler to create)

### 2. Store the PAT as a secret in dcat-ap-plus

1. Go to `nfdi-de/dcat-ap-plus` → Settings → Secrets and variables → Actions
2. Click **New repository secret**
3. Name: `DOWNSTREAM_NOTIFY_PAT`
4. Value: the PAT from step 1
5. Click **Add secret**

### 3. Replace the deploy-docs workflow

Replace `.github/workflows/deploy-docs.yaml` in dcat-ap-plus with
`workflows/deploy-docs.yaml` from this folder.

> **Note on action versions:** The production workflow uses stable floating
> tags (`actions/checkout@v4`, `astral-sh/setup-uv@v5`, etc.). Update these
> to whatever your project currently uses if needed.

### 4. Verify (optional)

Push a test tag to dcat-ap-plus and confirm that:

1. The "Notify downstream repos of new release" step shows
   `Dispatch sent successfully.` in the workflow log.
2. A new `handle-upstream-release` run appears in the chem-dcat-ap Actions tab.
3. A `freeze/dcatapplus-<version>` PR is opened in chem-dcat-ap.

If the step logs `WARNING: dispatch may have failed`, check that the
`DOWNSTREAM_NOTIFY_PAT` secret is correctly set and has the right permissions.

---

## How the full end-to-end pipeline works

```
dcat-ap-plus: git tag v1.2.0 && git push origin v1.2.0
        │
        ▼
dcat-ap-plus deploy-docs.yaml
  • mike deploy v1.2.0 latest
  • mike set-default latest
  • POST /repos/nfdi-de/chem-dcat-ap/dispatches   ← new step
        │
        ▼
chem-dcat-ap handle-upstream-release.yaml
  • Detect current dcatapplus import token in source
  • Create branch  freeze/dcatapplus-v1.2.0
  • freeze_imports.py: dcatapplus:<old>/ → dcatapplus:v1.2.0/
  • Commit + push
  • gh pr create  →  PR opened with CI checks
  • Comment on all open PRs  →  contributors notified
        │
        ▼
Maintainer reviews freeze PR
  • CI green  →  merge; main now pinned to v1.2.0
  • CI red    →  breaking change; schema updates needed before merge
```
