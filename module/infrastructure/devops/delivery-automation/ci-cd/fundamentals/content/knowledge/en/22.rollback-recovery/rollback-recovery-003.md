# Retaining Verified Artifacts and Configurations

Rollback can only be executed quickly and safely when the team still has the exact version that previously worked well along with its corresponding configuration. If the old artifact has been deleted from the registry, the tag now points to a new image, the config file was modified directly in production, or the old secret version is no longer usable, an application rollback command may fail or put the system into an incompatible state.

Therefore, every release should leave behind a reusable **release record**: an immutable artifact, digest, verified configuration, versioned secret references, build source metadata, and verification results. The team must retain recent releases according to a retention policy, protect them from accidental overwrite/deletion, and periodically test restoring them in a representative environment.

The goal is that when an incident occurs, operators can identify the most recent good release, retrieve the exact artifact and configuration, verify them, and redeploy within the target recovery time. Retaining them does not mean storing secrets inside the bundle; secrets are still fetched from the secret manager using authorized identities and versions.

## 1. Rollback Requires More Than a Binary File

A running release is the result of multiple coordinated inputs:

- Artifact: JAR, ZIP, binary, package, or container image.
- Application configuration: endpoints, timeouts, feature settings, resource limits, and runtime parameters.
- Infrastructure configuration: Deployment, Service, ingress, autoscaling, policies, and corresponding IaC state.
- Feature flags: feature toggle states at release time.
- Secret references: secret names, versions, or version IDs to fetch from the secret manager.
- Database schema and migration level: data structure required by the artifact.
- Runtime/toolchain: JDK, base image, sidecar, or agent that affects behavior.
- Evidence: digest, signature, provenance, test reports, approvals, and deployment records.

If you store only the artifact without storing the configuration, a rollback may run old code with new configuration. If you store only the configuration without preserving secret versions or schema compatibility, the old application may still fail to start. Thus, a release must be managed as an identified bundle of artifacts and metadata, not a standalone version string.

### Example of a Release Record

Suppose production is running `orders-api` release `2026.11.18.3`. The release record must identify the exact image, config revision, and schema level:

```json
{
  "service": "orders-api",
  "releaseId": "2026.11.18.3",
  "source": {
    "repository": "https://git.example.com/platform/orders-api",
    "commit": "<full-commit-sha>"
  },
  "artifact": {
    "uri": "registry.example.com/platform/orders-api",
    "digest": "sha256:<64-hex-characters>"
  },
  "configuration": {
    "repository": "https://git.example.com/platform/orders-config",
    "revision": "<config-commit-sha>",
    "renderedBundleDigest": "sha256:<64-hex-characters>"
  },
  "secretReferences": [
    {"name": "orders-db-credentials", "version": "42"},
    {"name": "payment-client-certificate", "version": "17"}
  ],
  "database": {
    "minimumSchemaVersion": "2026_11_12_01",
    "maximumSchemaVersion": "2026_11_18_02"
  },
  "verification": {
    "signature": "verified",
    "provenance": "verified",
    "smokeTest": "passed"
  }
}
```

Values in this example are placeholders. Actual manifests must be generated from build and deployment metadata, not hand-written digests or check statuses. Do not put passwords, tokens, private keys, or secret contents into the manifest; store only references and version IDs if policy permits.

## 2. Determining Which Releases to Retain

Not every build needs to be kept indefinitely. Define a policy based on the required rollback window, release frequency, service criticality, audit requirements, and backup recovery capabilities.

A policy can categorize releases:

| Category | Example | Storage approach |
|---|---|---|
| Currently running release | Current production version | Retain artifact, config, and manifest; protect from automatic deletion |
| Known-good release | One or more prior versions confirmed stable | Retain in fast-retrieval registry/storage |
| Approved candidate | Release that passed gates but has not fully rolled out | Retain for the deployment duration and rollback window |
| Experimental build | PR, nightly, or non-release branch build | Short retention, restricted access |
| Revoked release | Artifact with security vulnerability or no longer permitted | Quarantine/mark revoked; exclude from valid rollback candidates |

### Retaining by Rollback Window and RTO

Retention must outlast the period during which the organization commits to being able to roll back. If the team needs to be able to revert to any of the last three releases, the artifacts and configurations for those three releases must remain available for the corresponding period. For systems with monthly jobs or long approval cycles, the rollback window may exceed normal deployment cadences.

Consider:

- RTO: maximum allowed time to restore the service.
- RPO: acceptable data loss; artifact retention does not replace data backups.
- Time to detect post-deploy bugs: defects may only surface after several days or a business cycle.
- Time needed for investigation and approval: releases may need to remain available while determining root cause.
- Support lifecycle of runtimes, dependencies, and base images.
- Legal, audit, and internal retention policy requirements.

Keeping too few releases forces rollback to depend on rebuilding during an incident. Keeping every artifact forever increases cost and expands the storage footprint. The policy should specify minimum counts or durations, exceptions for critical releases, and a controlled deletion process.

### Retaining All Dependent Components

Keeping a JAR file while deleting the required dependency repository, base image, Helm chart, deployment manifest, or IaC module can still prevent rollback from reproducing the environment. The release record must list the components that the recovery procedure depends on.

For container images, retain both the manifest/index and all layers by digest. For Java applications, ensure required packages and dependencies remain downloadable or are packaged in the distribution. For Kubernetes deployments, retain rendered charts/manifests or source revisions along with the tool versions needed to reapply configuration.

## 3. Artifacts Must Be Immutable and Unambiguously Identified

An approved artifact should never be overwritten with different contents. The same name or version must always represent the exact same content throughout the release lifecycle.

### Use Digests Instead of Mutable Tags

Tags like `latest`, `stable`, `production`, or `1.8` can be updated to point to different contents. For container images, record the digest:

```text
registry.example.com/platform/orders-api@sha256:<image-digest>
```

Tags remain helpful for humans, but deployment and rollback decisions should use immutable digests. If a tag moves, the old release record still points to the exact image.

For packages or archive files, use immutable versions and store SHA-256 hashes. Never republish different contents under the same Maven/package coordinates. If a bug fix is needed, create a new version.

### Verify Before Storing and Before Using

After building, the pipeline should:

1. Compute the artifact's digest.
2. Generate a signature or attestation per policy.
3. Store provenance linked to the source commit and builder identity.
4. Upload the artifact to a registry/storage with restricted write permissions.
5. Read back the artifact or inspect the registry digest to confirm the stored content matches.
6. Write the digest and URI into the release manifest.

Before rolling back, the pipeline retrieves the exact digest from the release record, verifies signature/provenance, and checks revocation status. Do not simply check that a tag exists and deploy.

Example verifying an image with Cosign using a public key distributed through a trusted trust store:

```bash
cosign verify --key release.pub \
  registry.example.com/platform/orders-api@sha256:<image-digest>
```

For blobs or package files, verify the corresponding digest and detached signature. A valid signature alone does not prove a release is still permitted for use; policy must also check revocation status, source revision, and builder identity.

### Protecting Registries and Storage

The artifact store is part of recovery infrastructure. You should:

- Separate permissions for publish, pull, delete, and retention administration.
- Allow only release pipelines to write to release namespaces.
- Enable versioning or immutable retention/locks if supported by the platform.
- Restrict deleting artifacts referenced by currently running or known-good releases.
- Enable audit logging for publish, overwrite, delete, and retention changes.
- Back up or replicate critical artifacts per availability requirements.
- Test accessibility when the primary registry experiences an outage.

If the registry supports retention lock/WORM, configure it for critical releases to prevent premature deletion. Distinguish artifact immutability from administrative delete permissions; administrative policies and credentials must still be protected.

## 4. Keep Configurations in a Recoverable Versioned Form

Configurations often change independently from code: endpoints, timeouts, resource limits, autoscaling, routes, policies, feature flags, and business parameters. If edited directly in production without recording a revision, the team may not know which configuration produced the failing behavior.

### Versioning Configuration

Common approaches:

- Store configuration in Git and use the commit SHA as the revision.
- Package config into a bundle with a digest and signature.
- Use a GitOps controller to reconcile the environment from a declared revision.
- Store a snapshot of the rendered configuration alongside the release record.
- Record versions of charts, manifests, policies, and IaC modules.

Do not use mutable branches or tags as the sole identifier. The manifest should record the commit SHA or bundle digest. If templates and per-environment values are used, record both the template version and the values revision used to render.

Example configuration repository structure:

```text
orders-config/
├── base/
│   ├── deployment.yaml
│   └── service.yaml
├── overlays/
│   ├── staging/
│   │   └── values.yaml
│   └── production/
│       └── values.yaml
└── policy/
    └── resource-limits.yaml
```

The release record can store this repository's revision and the digest of the rendered output for production. During rollback, retrieve that exact revision and render using the recorded tool version, or use the verified pre-rendered bundle.

### Store Effective Configuration, Not Only Source Configuration

Templates can produce different outputs depending on environment variables, chart versions, CI variables, or secret references. For investigation and rollback, you need to know the effective rendered configuration.

You can store:

- Config repository commit SHA.
- Helm/Kustomize/Terraform or renderer version.
- Digest of rendered bundle/manifests.
- Environment and release ID.
- Feature flag snapshot or revision from the feature flag system.
- Secret references and version IDs, not secret values.
- Permitted runtime variables that affect configuration.

Snapshots must be sanitized before storage. Some renderers may interpolate secrets directly into manifests; never upload rendered outputs containing secrets to public artifacts or logs. It is better to use secret references resolved by the platform at runtime.

### Detecting Configuration Drift

Drift occurs when the running configuration differs from the declared configuration. For example, an operator edits the replica count directly, changes a timeout in the console, or updates an environment variable outside Git.

Periodically compare desired configuration against effective configuration, record out-of-band changes, and decide whether to reconcile or adopt the change in a controlled manner. Before rolling back, check whether any emergency changes must be preserved so you do not accidentally erase a necessary fix.

Not all runtime changes should be automatically overwritten. Certain operational parameters such as temporary scaling may be managed separately. Policy should classify source config, operational config, and emergency changes.

## 5. Managing Secrets by Reference and Version

A release bundle should not contain passwords, API tokens, private keys, or private certificates. These values can be copied whenever artifacts are downloaded, stored, replicated, or shared.

Instead, store references to the secret manager:

```yaml
database:
  usernameSecret:
    name: orders-db-username
    version: "42"
  passwordSecret:
    name: orders-db-password
    version: "42"
```

This is an illustrative structure. Actual syntax depends on the secret manager and runtime platform. If the system does not support version pinning, record the rotation policy and ensure the new version can read current credentials.

### Secret Versions and Rollback Capability

Rolling back to an old artifact while using a new secret may succeed or fail depending on compatibility. For example, a new certificate might not be supported by an old runtime; a rotated database password might no longer match old connection config.

Determine:

- Which secrets require version pinning to recreate a release.
- Which secrets must always fetch the current version for security reasons.
- Whether secret rotation has an overlap period.
- Whether the old runtime can use new credentials.
- Whether an old secret version can be safely restored or new credentials must be generated.
- Who has permission to read secrets during rollback and in which environments.

Never restore a revoked or suspected-compromised credential just to make an old release run again. When an old secret is no longer safe, update the rollback release's configuration to use compatible new credentials.

### Do Not Package Rendered Secrets

If a config renderer injects secret values into YAML, JSON, or environment files, do not store that file in the release archive. You can store the rendered config after replacing secrets with references or redaction, then let the runtime fetch secrets via workload identity.

If storing sensitive configuration for recovery is strictly required, use a separate encrypted store with tightly restricted access, full auditing, separate encryption keys, and a break-glass access procedure. This is a controlled exception, not a reason to embed secrets in regular artifacts.

## 6. Release Manifest Linking Artifacts and Configuration

A unified manifest helps pipelines and operators know which components belong to the same release. The manifest should be immutable once signed and stored in a location accessible even if the CI system goes down.

Example YAML manifest:

```yaml
apiVersion: delivery.example.com/v1
kind: ReleaseRecord
metadata:
  service: orders-api
  releaseId: "2026.11.18.3"
source:
  repository: platform/orders-api
  commit: "<full-commit-sha>"
artifact:
  type: oci-image
  reference: registry.example.com/platform/orders-api@sha256:<image-digest>
  signature: registry.example.com/platform/orders-api-signature
configuration:
  repository: platform/orders-config
  revision: "<config-commit-sha>"
  environment: production
  renderedBundleDigest: "sha256:<config-bundle-digest>"
secrets:
  references:
    - name: orders-db-credentials
      version: "42"
database:
  schemaVersion: "2026_11_18_02"
  compatibility: "supports-previous-and-current"
verification:
  provenance: verified
  signature: verified
  smokeTest: passed
```

The `verified` values in the manifest are results recorded by the pipeline after real checks. A manifest must not be used as a self-attesting source for itself; sign the manifest or store it in a controlled release store and verify its signature before use.

The manifest should specify the environment because the same artifact may be deployed with different staging and production configurations. Do not put secret values in the manifest. You can maintain a root artifact manifest and a separate deployment record per environment, linked by release ID and digest.

### Separating Release Manifest and Deployment Record

A release manifest describes what was built and tested. A deployment record describes an application to an environment:

| Record | Key information |
|---|---|
| Release manifest | Source commit, artifact digest, signature, provenance, dependencies, and test evidence |
| Environment config record | Config revision, rendered bundle digest, secret references/versions, feature flag revision |
| Deployment record | Environment, release ID, timestamp, actor, approvals, rollout strategy, and result |
| Recovery record | Release selected for rollback, reason, digest/config revision, and post-rollback verification result |

Separating records allows the same artifact to be promoted across multiple environments while maintaining traceability of the effective configuration at each target.

## 7. Maintaining a List of Known-Good Releases

A registry may hold many artifacts without knowing which releases are known-good. Metadata or a deployment ledger is needed to record status.

Example list:

| Release | Artifact digest | Config revision | Production state | Rollback eligible? |
|---|---|---|---|---|
| `2026.11.18.3` | `sha256:aaa...` | `cfg-91ab...` | Current | No need to roll back to itself |
| `2026.11.16.2` | `sha256:bbb...` | `cfg-73cd...` | Previous known-good | Yes, if schema/secrets are compatible |
| `2026.11.12.5` | `sha256:ccc...` | `cfg-5e21...` | Older known-good | Conditional, requires compatibility check |
| `2026.11.18.4-rc1` | `sha256:ddd...` | `cfg-b104...` | Candidate | Not yet considered known-good |

Do not pick a rollback release solely based on higher/lower version numbers or recency. A candidate may not have been verified in production; an older release may be incompatible with the current schema.

### Marking Revoked Releases

If an artifact is found to have a critical vulnerability, invalid signature, or compromised dependency, mark that release as revoked/quarantined. The release record should still be kept for auditing, but the rollback pipeline must refuse to use it.

Known-good status should be updated after post-deployment validation passes, not immediately upon artifact upload. A release is only added to the rollback list when there is evidence it has served stably according to organizational criteria.

## 8. Rollback Procedure Using Retained Artifacts and Configurations

When a rollback is needed, the procedure should automatically fetch the right known artifact/config pair and verify compatibility before modifying production.

### Operational Steps

1. **Halt current rollout:** stop traffic increases or the failing deployment to prevent further changes.
2. **Select release:** identify a known-good release compatible with the current schema, dependencies, and security state.
3. **Fetch release record:** retrieve the signed manifest or record from a controlled release ledger.
4. **Pull artifact:** use the immutable digest, do not resolve mutable tags.
5. **Verify:** check digest, signature, provenance, revocation status, and builder origin.
6. **Fetch configuration:** check out the exact config revision or download the bundle with the recorded digest.
7. **Check secrets:** resolve secret references per current policy; do not restore revoked credentials.
8. **Check compatibility:** schema, APIs, feature flags, runtime, and dependencies must support the selected release.
9. **Deploy:** use an appropriate canary/rolling/blue-green strategy and preserve the current version to revert if needed.
10. **Verify post-rollback:** smoke tests, health, metrics, logs, and business indicators.
11. **Write recovery record:** log actor, reason, release/digest/config, approval, and outcome.

If the artifact or configuration cannot be verified, stop the rollback and switch to an approved recovery plan. Do not bypass signatures or use a newly built artifact during an incident if the goal is to return to a known release.

### Example Pre-Deployment Release Verification

The conceptual script below illustrates mandatory checks. `release-tool` and `deploy-tool` are hypothetical internal tool names and must be replaced with actual CLIs/APIs:

```bash
#!/usr/bin/env bash
set -euo pipefail

release_id="${1:?usage: rollback.sh <release-id> <environment>}"
environment="${2:?usage: rollback.sh <release-id> <environment>}"

# Fetch a signed release record from the trusted release ledger.
release-tool fetch-record "$release_id" --output release-record.json
release-tool verify-record release-record.json

# Resolve immutable artifact and config bundle references.
artifact_digest="$(release-tool field release-record.json artifact.digest)"
config_digest="$(release-tool field release-record.json configuration.renderedBundleDigest)"

# Verify the exact content before use.
release-tool verify-artifact "$artifact_digest"
release-tool verify-config "$config_digest"
release-tool assert-not-revoked "$release_id"
release-tool check-compatibility "$release_id" "$environment"

# Resolve secret references at runtime; never export secret values to the bundle.
release-tool resolve-secret-references "$release_id" "$environment"

# Deploy the exact approved release pair.
deploy-tool apply \
  --release-record release-record.json \
  --artifact-digest "$artifact_digest" \
  --config-digest "$config_digest" \
  --environment "$environment"

deploy-tool verify "$release_id" "$environment"
release-tool record-recovery "$release_id" "$environment" --result success
```

This is pseudo-code, not a script to run as-is. Actual tooling must verify signatures and provenance, validate inputs, protect command outputs, never print secrets, and allow only approved environments. Fields extracted from manifests must be parsed safely; never `eval` JSON/YAML contents or interpolate untrusted data directly into shell commands.

### Do Not Bypass Approvals During Rollback

Rollbacks often need to be fast, yet they still require authorization. Break-glass permissions can be defined for on-call engineers or incident commanders, scoped to specific environments and logged for audit. Approvals do not have to slow down the process if policy pre-defines who has authority and which releases are eligible.

## 9. GitHub Actions Example Retaining Artifacts and Release Metadata

The following workflow illustrates storing a distribution package along with checksums and a manifest in a build run. For production systems, the artifact store or package registry should have its own retention/immutability policy; GitHub Actions artifacts are only a short-term storage example.

```yaml
name: Build release bundle

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Build and test
        run: ./gradlew --no-daemon clean check distZip

      - name: Prepare release bundle
        env:
          SOURCE_COMMIT: ${{ github.sha }}
          RELEASE_TAG: ${{ github.ref_name }}
        run: |
          mkdir -p release-bundle
          cp build/distributions/*.zip release-bundle/
          cd release-bundle
          sha256sum *.zip > SHA256SUMS
          printf 'release=%s\nsource_commit=%s\n' "$RELEASE_TAG" "$SOURCE_COMMIT" > release-metadata.txt

      - name: Upload release bundle
        uses: actions/upload-artifact@v4
        with:
          name: release-${{ github.ref_name }}-${{ github.sha }}
          path: release-bundle/
          if-no-files-found: error
          retention-days: 90
```

This workflow illustrates build/test, checksum generation, and metadata storage. Before using it for real releases, add:

- Pin GitHub Actions to full commit SHAs per supply-chain policy.
- Verify protected tags and ensure releases are only built from authorized sources/branches.
- Sign the artifact, checksum manifest, and release metadata; generate provenance attestation.
- Store the config revision and rendered config digest in a separate deployment record.
- Publish to a registry with immutable versions and retention aligned with the rollback window.
- Configure secrets and signing identities in a separate job with least privilege.
- Do not treat the 90-day retention in this example as an appropriate default for every system.

A release bundle can contain binaries, checksums, an SBOM, provenance references, and a signed manifest. Environment configuration should be managed in a separate repository or config store, then linked via revision/digest. Do not place production secrets in artifacts.

## 10. Ensuring Configurations Can Be Independently Recovered

If configuration lives in GitOps, rolling back config can mean reverting or redeploying a previous revision. However, this operation must be controlled to avoid accidentally erasing emergency changes or applying incompatible old configs.

### Storing Revisions and Diffs

The deployment record should store:

- Config repository and commit SHA.
- Environment overlay or values file used.
- Renderer version and rendering parameters.
- Digest of the rendered output.
- Diff between the current release and the previous release.
- Person or automation that approved it.

Before rolling back, inspect the diff to see which changes will be reversed. Some settings may have been updated independently to address a security issue, such as minimum TLS version or a migrated endpoint. Do not restore the entire old config without evaluating those changes.

### Feature Flags

Feature flags can determine which code path is enabled. If an old artifact is restored while the flag remains in the new state, the application may continue entering a faulty code path. Store a revision or snapshot of flag states per release and define which flags are allowed to roll back with code.

Not every flag should be automatically reverted. Operational flags or kill switches may be enabled during an incident to protect the system and must retain their new state even when code rolls back. Classify flags by ownership and rollback behavior.

### Runtime Config and Dynamic Configuration

Some systems fetch configuration from a remote config service or database. Storing only a Git commit is insufficient if effective values changed after deployment. Record the revision or version of the config object, snapshot timestamp, and recovery method. If the system does not support versioning, add audit logging and export sanitized snapshots.

Do not automatically overwrite runtime configuration that may contain business state. Roll back only parameters within the defined release configuration scope.

## 11. Checking Compatibility Before Selecting an Old Release

The most recent release is not always eligible for rollback. Before selecting one, verify constraints:

| Component | Compatibility questions |
|---|---|
| Database schema | Can the old artifact read the current schema? Has a migration contracted or dropped old columns? |
| Data | Has new data been written in a format the old code understands? |
| API | Are clients and dependent services still compatible with the old contract? |
| Message schema | Can old consumers understand new messages already published to the queue? |
| Config | Does the current config contain new keys or omit old keys needed by the old artifact? |
| Secret | Are current credential versions compatible with the old runtime and still valid? |
| Runtime | Are required base images, JDKs, OS libraries, or sidecars still retained? |
| Security | Has the artifact been revoked or does it contain banned dependencies? |
| External services | Do external APIs/endpoints still support the protocol used by the old release? |

If the schema has progressed to contract and is no longer compatible with the old artifact, do not attempt a pure code rollback. A forward fix, supplementary migration, or database recovery under a separate procedure may be required. The release ledger should record minimum/maximum schema compatibility so rollback tooling can filter out ineligible candidates before deployment.

### Retaining Old Config Does Not Mean Retaining All Old Data

Artifact/config retention does not replace backups of databases, object storage, or message logs. If the old release needs data that was deleted or transformed, appropriate backup/PITR or replay/compensation capabilities must exist. Data recovery problems must be managed as a dedicated part of the recovery plan.

## 12. Access Controls and Protecting Stored Releases

Verified releases can become attractive targets because anyone who can alter an artifact or manifest can directly compromise rollback. Apply least privilege for both write and delete operations.

Separate these roles:

- Builder: creates artifacts and metadata, writing only to authorized build namespaces.
- Signer: signs artifacts/manifests per policy; does not accept untrusted code.
- Release manager: approves and marks releases as eligible.
- Deployer: reads approved releases and deploys to authorized environments.
- Storage administrator: manages retention, replication, and recovery; actions are audited.
- Incident responder: holds time-bound break-glass permissions with recorded justification.

Do not grant registry delete permissions to normal deployment jobs. Do not allow pull requests from forks to write to release namespaces or modify retention policies. Manifests and config revisions must be protected just like artifacts because altering them can misdirect a rollback.

## 13. Rehearsing Release Retrieval

A release is truly ready for rollback only when the team has proven it can retrieve and run it. Seeing the artifact still sitting in the registry is not enough; access permissions may have expired, signing keys may have changed, dependencies may have vanished, or the config renderer may no longer be installed.

### Periodic Drills

Select an older known-good release and execute against staging or a recovery environment:

1. Look up the release record by release ID.
2. Pull the artifact by digest and verify signature/provenance.
3. Fetch the config revision/bundle and verify its digest.
4. Resolve secret references using the test environment's identity.
5. Check schema compatibility and dependency availability.
6. Deploy the old release to the test environment.
7. Run smoke tests and check metrics.
8. Record step durations, errors, and results in the recovery drill record.

Do not use production secrets in drills unless necessary. Use revocable test credentials with equivalent scope.

### Measuring Actual Recovery Time

Measure the time from when the incident commander selects a release until the service passes post-deployment validation. Compare against RTO. If most of the time is spent pulling images, locating configs, or waiting for approvals, improve the release ledger, mirrors, access permissions, or break-glass process.

Drills must also test adverse cases:

- Primary registry is unreachable.
- Artifact exists by digest, but signature verification fails because trust policy changed.
- Config revision was deleted or read permission was lost.
- Old secret version was revoked.
- Old release is incompatible with the current schema.
- Artifact is marked revoked.

Drill results must explicitly state which fallbacks are usable and which cases mandate a forward fix or data recovery.

## 14. Practices That Easily Break Rollback Capability

| Practice | Risk | Improvement |
|---|---|---|
| Retaining only the `latest` tag | Tag can point to new contents | Store immutable digests in release records |
| Rebuilding old source during an incident | Toolchain/dependencies changed, yielding a different artifact | Retain released artifacts and verify them |
| Storing binaries without config revisions | Old code runs with incompatible configuration | Link artifacts and configs via a release manifest |
| Storing rendered configs containing secrets | Credentials get copied into artifacts/stores | Store sanitized configs and secret references/versions |
| Deleting old releases on short retention | No known-good release left when bugs appear late | Base retention on rollback window and RTO |
| Sharing a registry with broad write permissions | Good artifacts can be overwritten or deleted | Separate write/delete, immutable policies, and audit |
| Keeping release records only in CI logs | Logs may expire or CI system may be down | Store an independent, backed-up release ledger |
| Not retaining dependencies/base images | Cannot recreate old runtime | Retain required dependencies or controlled mirrors |
| Rolling back code without checking schema | Old code crashes on new schema | Record schema compatibility and check before deploy |
| Restoring revoked old secrets | Reopens security risk | Use compatible new credentials for the old artifact |
| Not rehearsing restores | Missing permissions or missing files discovered only during incidents | Conduct periodic rollback drills |

## 15. Checklist for Retaining Rollback-Ready Releases

Before marking a release as known-good, verify:

- [ ] Artifact is stored in a registry/storage with controlled write and delete permissions.
- [ ] Artifact has an immutable digest; does not rely on mutable tags.
- [ ] Digest, signature, and provenance have been verified.
- [ ] Release manifest links source commit, artifact digest, and builder identity.
- [ ] Config repository revision and rendered bundle digest are recorded.
- [ ] Feature flag revision/snapshot is stored per policy.
- [ ] Secrets are stored only as references/versions; no secret values exist in the bundle.
- [ ] Schema compatibility and migration level of the release are documented.
- [ ] Dependencies, base images, charts, or IaC modules needed for rollback remain accessible.
- [ ] Release retention exceeds the rollback window and aligns with RTO/storage policy.
- [ ] Revoked releases are marked and cannot be selected as rollback candidates.
- [ ] Deployment records and a list of known-good releases are maintained.
- [ ] Deploy, publish, sign, and delete permissions are separated.
- [ ] Audit logs exist for changes to artifacts, manifests, configs, and retention.
- [ ] Replicas/mirrors or fallback access exist if the primary registry fails.
- [ ] Rollback procedure re-verifies artifact/config before deployment.
- [ ] Retrieving the release, restoring config, and actual recovery time have been rehearsed.

Retaining verified artifacts and configurations turns rollback from an improvised scramble into a predictable procedure. Immutable artifacts identify the exact code running; config revisions show how the environment was configured; secret references and schema compatibility confirm the old release remains usable. When release records, retention, access controls, and recovery drills are managed together, teams can return to a known state without rebuilding or guessing configurations during an incident.
