# Planning a Rollback to a Previous Version with Stored Artifacts and Clear Identity

A reliable rollback plan must answer three questions: **which version is currently running, where the last known-good version lives, and how to redeploy the exact bytes that were previously tested**. Simply remembering a version like `2.4.0` or rebuilding the old release's source code is not enough. Dependencies, build tools, builder images, configuration, and data may have changed since the initial build.

For Spring Boot applications, rollbacks should rely on **immutably stored artifacts** with verifiable identities and sufficient metadata to redeploy. For a JAR, the identity is typically Maven coordinates combined with SHA-256. For a container image, the reliable identity is the repository plus OCI digest. A release manifest links the artifact to its Git commit, build run, SBOM, configuration, and corresponding database schema level.

This guide explains how to retain built artifacts, identify exact versions, roll back using Maven/Gradle artifact repositories, Docker/OCI registries, Kubernetes, and Helm, while handling database compatibility, configuration, feature flags, and live data.

## 1. Rollback Means Restoring a Verified Release

A Spring Boot release usually consists of multiple components:

- Executable JAR or OCI image.
- Dependency graph and runtime/toolchain versions.
- Builder/run image if built with Cloud Native Buildpacks.
- Helm chart or Kubernetes manifests.
- Configuration revision and feature-flag state.
- Database schema/migration level.
- SBOM, checksums, signatures, and build provenance.

Rolling back code only restores part of the system. If the new version changed database schemas, message formats, cache keys, or external API contracts, redeploying the old JAR may still fail.

```text
                Release 2.4.1
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
       App JAR     OCI image    Config/chart
          |           |           |
          +-----------+-----------+
                      |
                      v
             Release manifest
                      |
                      v
        Durable artifact repository
                      |
             deployment reference
                      |
                      v
             Production runtime

If 2.4.1 fails:
                      |
                      v
       Select verified 2.4.0 manifest
                      |
                      v
       Fetch exact JAR/image by digest
                      |
                      v
       Check schema/config compatibility
                      |
                      v
             Redeploy 2.4.0
                      |
                      v
       Health check + smoke test + metrics
```

**Rollback is not rebuilding an old release's source.** Fetch the exact artifact that was previously built, tested, scanned, and published. Rebuilding from source can yield different outputs because dependency repositories, toolchains, base images, or buildpacks may have changed, so the result is no longer the verified artifact.

## 2. Distinguishing Version, Release, Build, and Artifact Identity

| Identifier | Example | Answers the Question |
| --- | --- | --- |
| Product version | `2.4.1` | What do users call this version of the application? |
| Release ID | `orders-api-2026-11-09.3` | Which specific release event is this? |
| Git commit | `9f31c2a...` | Which commit was the source code built from? |
| CI run ID | `845201` | Which pipeline/build run produced the artifact? |
| Maven coordinates | `com.acme:orders-api:2.4.1` | Under which coordinates is the JAR artifact stored? |
| SHA-256 | `sha256:...` | Do the JAR file bytes match the exact stored binary? |
| OCI image digest | `registry.example.com/team/orders-api@sha256:...` | Which exact image manifest/index is running? |
| Chart version | `orders-api chart 2.4.1` | Which deployment templates are used? |
| Config revision | Git SHA of config repo | Which non-secret configuration is deployed? |
| Schema version | `V42` or migration ID | Which migration level is the database at? |
| Deployment revision | Kubernetes/Helm revision | Which runtime update occurred? |

**Product version is not synonymous with artifact identity.** Two builds can share version `2.4.1` while being produced from different commits, dependencies, build environments, or file bytes. Production releases need both a human-readable version and an unambiguous technical identity.

### 2.1. Maven Coordinates for JARs

A Maven artifact is typically identified by:

```text
groupId : artifactId : version : packaging : classifier
```

Example:

```text
com.acme : orders-api : 2.4.1 : jar
```

A Maven-compatible repository path typically looks like:

```text
com/acme/orders-api/2.4.1/orders-api-2.4.1.jar
com/acme/orders-api/2.4.1/orders-api-2.4.1.pom
```

If the project publishes an executable Spring Boot JAR with a custom classifier, record the exact classifier in the release manifest. Do not guess filenames from project names; save the path and checksum of the actual published file.

### 2.2. OCI Image Digest for Containers

Human-readable tags, such as `orders-api:2.4.1`, are convenient for searching but can be reassigned to a different image. A digest is a content-addressed identifier of a manifest or image index.

Exact deployment form:

```text
registry.example.com/team/orders-api@sha256:<image-digest>
```

The `2.4.1` tag can remain as a human alias, yet deployment records should store the actual digest. For multi-platform images, the digest may identify an image index containing multiple platform manifests; record the verified index digest and the platform used by the runtime.

Do not use `latest` as a rollback identity. That tag can point to a newer image while historical Deployment/manifests still record the old tag string.

## 3. Rules for Creating a Clear Release Identity

A release ID should be unique and traceable back to source/build. Example:

```text
service       = orders-api
version       = 2.4.1
release-id    = orders-api-2.4.1-build-845201
git-commit    = 9f31c2a7...
git-tag       = v2.4.1
build-run     = 845201
artifact      = com.acme:orders-api:2.4.1:jar
image         = registry.example.com/team/orders-api@sha256:...
chart         = orders-api-2.4.1
config-rev    = 7bc12d0...
schema-level  = V42
```

Practical rules:

1. A release version must never be reused for different bytes.
2. Release tags are protected and bound to a specific Git commit.
3. CI run ID/build number is separate metadata, not a substitute for product version.
4. Every artifact has a checksum/digest recorded after packaging/publishing.
5. The manifest links source, build, artifact, chart/config, and schema level.
6. Every deploy/rollback records the release ID and actual digest.
7. If an already-released version needs a fix, create a new version/release; never overwrite the old artifact.

For Maven release repositories, enable policies forbidding overwrites of the same release coordinates. For OCI registries, enable immutable tag policies if available and still deploy by digest. Merely renaming a tag does not create a new artifact and does not prove image contents.

## 4. Storing Built Artifacts Where They Can Be Recovered

Artifacts must reside in durable storage with retention policies and read permissions accessible to the rollback workflow. Local Maven caches, Gradle caches, laptop Docker caches, or temporary GitHub Actions artifacts are not long-term release storage.

| Artifact | Suitable Storage | Metadata to Store |
| --- | --- | --- |
| Spring Boot executable JAR | Maven-compatible release repository or artifact store | GAV/classifier, POM, SHA-256, signature |
| OCI image | Container registry | Repository, tag alias, manifest/index digest, platforms |
| Helm chart | OCI registry or chart repository | Chart name/version, digest, values/config revision |
| SBOM | Artifact store tied to release | SBOM format/version, checksum |
| Provenance/attestation | Artifact store or attestation service | Builder identity, source, subject digest |
| Kubernetes manifests | Git/config repository | Commit SHA, release ID, rendered manifest |
| Runtime config | Config repository/secret manager | Revision/reference; do not store plaintext secrets |
| Database backup | Dedicated backup system | Snapshot ID, timestamp, consistency/restore evidence |

### 4.1. Separate Snapshot and Release Repositories

- **Snapshot/dev:** mutable or purged by age; never used as a production rollback source.
- **Release:** immutable versions, restricted publish permissions, longer retention, and backed up/replicated per policy.
- **Quarantine:** unapproved artifacts or those with findings under investigation.
- **Promotion:** the exact same artifact advances from test environments to staging/production without rebuilding.

Do not group release and snapshot artifacts under the same cleanup rule where accidental deletion can happen. Release repositories should reject overwrites to the same coordinates/version; rollback needs to fetch old artifacts by read identity.

### 4.2. Retention Must Account for the Rollback Window

Define retention by operational needs, not just disk space:

- Keep all artifacts currently deployed in any environment.
- Keep at least the minimum number of recent releases required by policy.
- Keep releases for at least the rollback window plus needed investigation/audit time.
- Keep corresponding charts, manifests, SBOMs, signatures, and config revisions.
- Keep database backups/snapshots according to a separate recovery schedule and policy.
- Only garbage-collect artifacts no longer referenced by any release/deployment and past retention.

For example, a team might retain the last 10 releases and a minimum of 90 days; these are illustrative numbers only. Choose figures based on RTO/RPO, release cadence, storage capacity, and organizational retention obligations.

**Retention is unverified until restore is tested.** Periodically re-download an old release using the exact permissions the rollback job will use, verify its checksum/digest, and confirm the artifact still runs in staging.

## 5. Generating a Release Manifest for Every Publish

A release manifest is a record linking everything needed to identify and redeploy a release. It should be generated automatically by CI after a successful build/publish and stored beside the artifact or in a release metadata store.

The `release-manifest.yaml` example below uses illustrative values; digests/checksums must be populated by CI with real values:

```yaml
schemaVersion: 1
service: orders-api

release:
  version: 2.4.1
  releaseId: orders-api-2.4.1-build-845201
  gitTag: v2.4.1
  gitCommit: 9f31c2a7f6e1
  buildRunId: "845201"
  createdAt: "2026-11-09T03:15:00Z"

build:
  javaVersion: "17"
  springBootVersion: "3.3.13"
  buildTool: maven
  mavenVersion: "3.9.9"
  builderImage: "paketobuildpacks/builder-jammy-base@sha256:<builder-digest>"

artifacts:
  jar:
    coordinates: "com.acme:orders-api:2.4.1:jar"
    repository: "company-releases"
    sha256: "<jar-sha256>"
  image:
    reference: "registry.example.com/team/orders-api@sha256:<image-digest>"
    platforms:
      - linux/amd64
      - linux/arm64
  sbom:
    uri: "artifact-store://orders-api/2.4.1/sbom.cdx.json"
    sha256: "<sbom-sha256>"
  provenance:
    uri: "artifact-store://orders-api/2.4.1/provenance.json"

deployment:
  chart: "orders-api"
  chartVersion: "2.4.1"
  configRepository: "platform-config"
  configRevision: "7bc12d0e4a91"

database:
  migrationLevel: "V42"
  compatibility: "backward-compatible"
```

Values `<builder-digest>`, `<image-digest>`, `<jar-sha256>`, and `<sbom-sha256>` are placeholders to replace with real outputs, not values to copy into production. Never place tokens, passwords, private keys, or plaintext secrets inside the manifest. Only record secret references/versions in the secret manager when traceability is needed.

### 5.1. Manifests Must Be Validated Before Deploy

Release/deploy jobs should reject a manifest if:

- The Git commit does not match the approved release tag/source.
- Artifact coordinates or digests do not exist in the repository/registry.
- JAR/SBOM checksums do not match.
- The image lacks the platform required by the target runtime.
- The chart/config revision is no longer accessible.
- Schema compatibility does not allow running the selected version.
- Required signatures/attestations are missing or invalid.

A manifest is a structured index; it does not guarantee authenticity by itself. For high-assurance releases, sign manifests/attestations and verify builder identity and subject digests before deployment.

## 6. Build Once, Store Once, Promote the Same Artifact

A good pipeline separates three activities:

1. **Build:** compile, test, scan, package, and compute checksums/digests.
2. **Publish:** store verified artifacts in a release repository/registry under immutable versions.
3. **Promote/deploy:** fetch the exact artifact by identity and deploy it to the target environment.

```text
Source commit
     |
     v
Build + tests + security scan
     |
     v
Create JAR / OCI image
     |
     v
Calculate checksum / image digest
     |
     v
Publish immutable artifact
     |
     +---------------------+
     |                     |
     v                     v
   Staging              Production
     |                     |
     +----------+----------+
                |
                v
      Same artifact digest
```

Do not rebuild in staging/production from the same Git tag and assume identical outputs. Compare the digest of the artifact fetched in each environment against the release manifest.

### 6.1. Maven: Storing and Retrieving Executable JARs

A Maven release pipeline may run:

```bash
./mvnw -B -ntp clean verify
./mvnw -B -ntp deploy
```

`deploy` executes the lifecycle through the `deploy` phase after earlier phases; the target repository is configured via `distributionManagement` or deployment settings. After publishing, record the exact coordinates and SHA-256 of the executable JAR.

When you need to retrieve the JAR `com.acme:orders-api:2.4.1:jar` from a Maven-compatible repository:

```bash
./mvnw -B -ntp \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get \
  -Dartifact=com.acme:orders-api:2.4.1:jar
```

The Maven Dependency Plugin downloads the artifact by coordinates into the user's local repository. For `groupId` `com.acme`, `artifactId` `orders-api`, and `version` `2.4.1`, the default path is usually:

```text
~/.m2/repository/com/acme/orders-api/2.4.1/orders-api-2.4.1.jar
```

If there is a classifier, different packaging, or a custom local repository path, the path changes. Always use the coordinates and repository settings from the manifest.

Verify the checksum before running:

```bash
sha256sum ~/.m2/repository/com/acme/orders-api/2.4.1/orders-api-2.4.1.jar
```

Compare the output with `jar.sha256` recorded in the release manifest/independent metadata. If there is a mismatch, halt the rollback and investigate; do not overwrite the expected checksum with the newly downloaded file's hash.

`mvn deploy` in the initial build publishes that build's output. When rolling back, retrieve the previously stored artifact; do not run `clean verify deploy` from old source to produce a new file and treat it as the same artifact.

### 6.2. Gradle: Publishing and Retrieving Artifacts

The Gradle Maven Publish Plugin lets you declare a publication with `groupId`, `artifactId`, `version`, and artifacts to publish to a Maven-compatible repository. For a Spring Boot application, you must configure the publication to store the **executable `bootJar`** if that is the runtime deliverable; do not assume the default publication from the Java component matches the Boot executable archive in every setup.

Example pipeline when the project already configures publishing for the Boot JAR:

```bash
./gradlew --no-daemon clean check bootJar publish
```

Record the artifact path, Maven coordinates, SHA-256, and repository URL in the release manifest. When rolling back, fetch the exact recorded coordinates/version from the repository using an organization-supported client/repository API, then verify the checksum before running.

The Gradle cache or `build/libs` on a runner is not durable release storage. Ensure artifacts are published to durable storage and policies do not purge versions still within the rollback window.

### 6.3. OCI Image: Publishing and Pinning Digests

After creating the image, push a unique release tag:

```bash
docker push registry.example.com/team/orders-api:2.4.1
```

Save the digest returned by the registry after pushing and record it in the manifest. Pull the image back by digest:

```bash
docker pull registry.example.com/team/orders-api@sha256:<image-digest>
```

Inspect the digest/manifest from the registry using a supported tool:

```bash
docker buildx imagetools inspect registry.example.com/team/orders-api:2.4.1
```

When deploying, use `repository@sha256:digest` rather than mutable tags. Do not retag an old image as `latest` and use `latest` as a rollback identifier. A tag is only an alias; the digest is the identity of a specific manifest/index.

## 7. Retain Charts, Configurations, and Runtime Dependencies Too

Restoring the exact image is still not enough if the previous deployment used a different chart or configuration. Every release should retain:

- Helm chart package and chart version/digest.
- Rendered Kubernetes manifests or the GitOps commit containing the manifests.
- Non-secret configuration revision.
- Feature flag snapshot/export if supported by the system.
- Secret references/versions in the secret manager, without storing secret values.
- Ingress/API routing and service contract versions when changed.
- Database migration level and backup/snapshot reference.
- Runtime requirements such as Java version, mandatory environment variables, ports, volume paths, and resource constraints.

Do not roll back secret versions automatically if rotation was a security response. If a credential was revoked/compromised, rolling back the application must use the current compatible secret or a forward-fix; never restore invalidated secrets.

### 7.1. Separating App Releases and Config Releases

You can version apps and configs independently, but the release manifest must record the paired versions that ran together. When rolling back the app, choose a compatible config revision; do not assume the current config works with the old app.

| Release | App Image | Config Revision | DB Schema |
| --- | --- | --- | --- |
| 2.4.0 | digest A | config `c120...` | V41 |
| 2.4.1 | digest B | config `c811...` | V42 |

If rolling back to app 2.4.0, you need to know whether it runs with config `c811...` and schema V42 or whether a compatible config must be restored. Configuration changes need review and testing just like code.

## 8. Database Migrations: The Most Critical Condition for Rollback

Rolling back the application does not automatically roll back the database. Schema and data may have changed while the new version was running.

Dangerous example:

1. App 2.4.1 renames column `customer_name` to `display_name` and drops the old column.
2. App 2.4.1 writes data under the new schema.
3. The team redeploys app 2.4.0, which only reads `customer_name`.
4. The old app fails because the column was dropped.

### 8.1. Using Expand-and-Contract

Split schema changes across multiple releases:

```text
Release A: EXPAND
  - Add new column/table/index
  - Keep old schema
  - Old app continues working

Release B: MIGRATE
  - New app reads/writes compatible format
  - Backfill data
  - Validate old/new values

Release C: CONTRACT
  - Confirm no old app/client depends on old schema
  - Remove old column/API only in a later release
```

Rolling back the app during expand/migrate can still work because the old schema remains intact. Contract only after the old app's rollback window has closed and no consumers still depend on it.

### 8.2. Migration Rules

- Additive migrations (adding nullable columns, new tables, compatible indexes) make app rollbacks much easier than destructive migrations.
- Avoid breaking renames/drops/alters in the same release as the app change.
- Data backfills should be idempotent, checkpointed, and safely resumable.
- Do not automatically run down migrations during an app rollback without evaluating data loss and consumer dependencies.
- If a migration is irreversible, prepare backups/restores and verify recovery time before releasing.
- Record the migration level in the release manifest.
- Test the old app version against the new post-migration schema in staging.

**Rolling back binaries and rolling back data are two separate decisions.** If data was written in a new format or a destructive migration ran, a forward-fix may be safer than forcing the schema backward.

## 9. Rolling Back with Kubernetes Deployments

Kubernetes retains ReplicaSet history for a Deployment and provides `kubectl rollout history`/`kubectl rollout undo` to inspect and revert to an earlier Pod template. The `revisionHistoryLimit` field controls how many old ReplicaSets are retained; setting it to 0 disables rollback via Deployment history.

### 9.1. Inspecting Current and Historical Revisions

```bash
kubectl rollout history deployment/orders-api -n production
kubectl rollout history deployment/orders-api --revision=12 -n production
kubectl rollout status deployment/orders-api -n production
```

Note the revision, image reference, annotations/change-cause, and matching manifest. Do not infer the product version solely from the revision number: a Kubernetes revision counts Pod template changes, not the application's SemVer.

### 9.2. Rolling Back to the Previous Revision

```bash
kubectl rollout undo deployment/orders-api -n production
kubectl rollout status deployment/orders-api -n production --timeout=5m
```

Rolling back to a specific revision:

```bash
kubectl rollout undo deployment/orders-api \
  --to-revision=11 \
  -n production

kubectl rollout status deployment/orders-api -n production --timeout=5m
```

`rollout undo` restores the stored revision's Pod template. It does not automatically restore databases, standalone Secrets/ConfigMaps, external feature flags, or resources outside the Pod template. If those components changed, compatible versions must be restored separately.

### 9.3. Deploying an Image Directly by Digest

If using GitOps/manifests as the source of truth, revert the manifest to the old digest and let the controller reconcile. For controlled imperative operations, you can set the image by digest:

```bash
kubectl set image deployment/orders-api \
  orders-api=registry.example.com/team/orders-api@sha256:<previous-image-digest> \
  -n production

kubectl rollout status deployment/orders-api -n production --timeout=5m
```

The container name `orders-api` must match the container name in the Pod template. Afterward, update the GitOps source/release record so the controller does not overwrite the manual change.

### 9.4. Retaining Enough History

Example Deployment manifest:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  revisionHistoryLimit: 20
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: registry.example.com/team/orders-api@sha256:<image-digest>
```

`revisionHistoryLimit: 20` is just an illustrative value. Choose the revision count based on release frequency, capacity, and rollback window. ReplicaSet history does not replace registry artifact retention: if the image digest was purged from the registry, rolling back the template can still fail when nodes try to pull the image.

## 10. Rolling Back with Helm

Helm tracks release revisions for charts and values. Before rolling back, inspect history:

```bash
helm history orders-api -n production
```

Inspect values of the revision to restore:

```bash
helm get values orders-api --revision 11 -n production
```

Roll back to revision 11:

```bash
helm rollback orders-api 11 \
  -n production \
  --wait \
  --timeout 5m
```

Verify after rollback:

```bash
helm history orders-api -n production
kubectl rollout status deployment/orders-api -n production --timeout=5m
```

Helm creates a new revision to record the rollback operation; a new revision does not mean a new app version. You can use `--dry-run` to simulate the operation beforehand. Hooks may execute during a rollback; understand hook behavior and side effects before passing `--no-hooks` or `--force`.

If an older chart revision points to a mutable image tag, Helm may deploy a different image than originally ran in that revision. Ideally, chart values store image digests or immutable tags enforced by the registry. Store chart packages and values/config revisions alongside the release manifest.

## 11. Rollback by Deployment Strategy

| Strategy | How to Roll Back | What to Watch Out For |
| --- | --- | --- |
| Rolling update | Revert Pod template or `rollout undo` | ReplicaSet history, readiness, and capacity |
| Blue-green | Shift traffic back to the previous environment | Shared database/schema and state |
| Canary | Stop ramping traffic, set weight back to stable version | Metrics/traffic routing and background jobs |
| Helm release | Use Helm rollback to a specific revision | Chart, values, hooks, and image digest |
| VM/JAR service | Fetch old JAR by coordinates + checksum and restart service | systemd config, Java runtime, config/secret compatibility |
| Container service | Redeploy image by old digest | Registry retention, platform manifest |
| GitOps | Revert config commit to old release manifest | Controller reconciliation and source-of-truth |

With canary/blue-green, shifting traffic back quickly limits user impact, yet does not undo side effects already written to databases or message brokers. Stop background workers/consumers if they are writing incompatible data.

## 12. Executable Rollback Runbook for Incidents

A good runbook must be specific enough for an on-call responder to follow under high pressure.

### 12.1. Triggers and Scoping

A rollback may be triggered when:

- Error rate exceeds the release policy threshold.
- Latency/timeouts spike significantly after deploy.
- Pods crash-loop or readiness becomes unstable.
- Business metrics show failing transactions.
- A security incident requires pulling the new release.
- A reproducible regression occurs while the old release was confirmed stable.

Record the running release, deploy time, impact scope, and metrics/logs evidence. If possible, pause promotion/traffic shifting to prevent the rollout from spreading.

### 12.2. Picking the Right Last Known-Good Version

1. Open the release manifests of the running release and earlier releases.
2. Select the latest release marked known-good and confirmed stable in production/staging.
3. Verify the JAR checksum or OCI digest still exists and is pullable.
4. Check chart/config revision, platform, and runtime requirements.
5. Confirm the current schema/migration level is compatible with the old app.
6. Verify artifact signatures/provenance if required by policy.

Do not pick "one version number lower" by gut feel. The immediately preceding release might also be broken, never have run in production, or be incompatible with the current schema.

### 12.3. Executing the Rollback

1. Freeze new releases and halt auto-promotion.
2. Select the rollback target by release ID/manifest.
3. If using Kubernetes/Helm, update the Pod template/chart to the exact digest and config revision.
4. If running a JAR on a VM, download the artifact by coordinates and verify SHA-256 before replacing the active file.
5. Preserve backups/snapshots and do not run down migrations arbitrarily.
6. Wait for the rollout/restart to complete and readiness to pass.
7. Run smoke tests, checking critical endpoints and key business flows.
8. Monitor logs, error rates, latency, resource usage, and business metrics.
9. Confirm traffic/background workers are running the intended release.
10. Record the release ID, artifact digest, deployment revision, timestamp, and operator.

### 12.4. Post-Rollback

- Communicate service status and impact scope per incident process.
- Preserve logs, manifests, release manifests, and deployment events.
- Identify the regression and how it bypassed release gates.
- Build the fix in a new release; never patch/overwrite the old artifact.
- Re-run full tests/security gates and test rollback if schema/config changes.
- Ensure the new release is promoted from the verified artifact.

## 13. Post-Rollback Verification

A rollback command returning success only means the controller/repository accepted the operation. It does not prove the application is healthy.

Verification checklist:

- [ ] Deployment/Helm release reached rollout complete status.
- [ ] Running image digest or JAR checksum matches the rollback manifest.
- [ ] Ready/available replica count meets requirements.
- [ ] Readiness/liveness and smoke tests pass.
- [ ] Critical business flows succeed.
- [ ] Database queries and migration compatibility are stable.
- [ ] Message consumers/background jobs operate normally.
- [ ] Logs show no recurring errors.
- [ ] Error rate/latency/resource metrics return within acceptable thresholds.
- [ ] Config/feature flags match the compatible revision.
- [ ] Release record and incident timeline are updated.

If the rollback completed yet error rates remain high, the cause may lie in the database, an external dependency, config, secrets, or already-mutated data. Do not repeatedly roll back the same binary when evidence points outside the application artifact.

## 14. When to Roll Back vs. When to Forward-Fix?

| Situation | Usually Appropriate Action |
| --- | --- |
| Code regression while schema stays backward-compatible | Roll back app to known-good artifact |
| Bad new config while old config revision remains compatible | Roll back config along with app release |
| New image fails build/runtime while old image remains in registry | Deploy old digest |
| Database already dropped/renamed column and old app is incompatible | Forward-fix or restore data per plan; do not blindly roll back app |
| Data already underwent a one-way transformation | Evaluate restore/compensating migration; forward-fix may be needed |
| Old release has a critical security vulnerability | Do not roll back to vulnerable version; ship a safe fix |
| Old artifact was deleted/cannot be verified | Halt automated rollback; restore from trusted backup/replica or build a new controlled release |
| External API/queue contract changed | Coordinate consumer/producer rollback or forward compatibility fix |
| Old secret was revoked | Do not restore revoked secret; use new compatible credentials |

**Rollback is not always the safest action.** If the old release contains an actively exploited vulnerability or cannot read current data, a forward-fix may reduce risk better.

## 15. Common Pitfalls When Designing Rollbacks

| Pitfall | Consequence | Prevention |
| --- | --- | --- |
| Saving only Git tags, not artifacts | No guarantee of reproducing exact old binary | Store JAR/image alongside manifest |
| Using mutable image tags | Tag can point to different bytes | Deploy by digest |
| Overwriting Maven release coordinates | Old version is no longer the old artifact | Enforce immutable release repository |
| Keeping only local Docker layers | New runners/nodes cannot pull artifact | Registry retention/replication and restore tests |
| Purging old images via cleanup policies | Cannot roll back to exact digest | Exempt deployed/rollback-window artifacts from GC |
| Not saving charts/values/configs | Old image runs with incompatible new config | Version and store config/chart revisions |
| Not recording DB migration levels | Picking an old app incompatible with schema | Record migration levels and test old-app/new-schema |
| Running down migrations automatically | Risk of data loss or breaking other apps | Evaluate migrations separately, verified backup/restore |
| Using Kubernetes revision as app version | Confusing deployment history with release identity | Annotate release ID, Git SHA, and digest |
| `revisionHistoryLimit: 0` | Deployment retains no history to undo | Set appropriate retention and store external manifests |
| Helm rollback with mutable tags | Old chart may pull newer image | Pin digests in values |
| Never practicing restores | Discovering missing artifacts during an outage | Run staging restore drills |
| Rolling back traffic while workers still run new version | Background processing keeps writing incompatible data | Coordinate workers/consumers with the app release |
| Old secret revoked while rolling back old config | Old app fails to connect or violates security | Decouple secret lifecycles and check compatibility |

## 16. Testing Rollbacks Before You Need Them

Rollback must be rehearsed as a routine operational exercise.

A staging drill can:

1. Deploy release A using image digest A.
2. Record the release manifest, chart/config revision, and schema level.
3. Deploy release B using digest B with a schema-compatible change.
4. Intentionally trigger a defined rollback condition, such as a failing smoke test in staging.
5. Fetch manifest A from the artifact store.
6. Re-pull image A by digest and verify signature/checksum.
7. Roll back the chart/Deployment to A and compatible config.
8. Run smoke/integration tests and verify metrics.
9. Measure time from decision to service stability.
10. Verify artifact retention, read permissions, and whether the runbook has enough detail.

Record the actual RTO, manual steps, missing permissions, any unpullable artifacts, and schema compatibility issues. Update the runbook after the drill. Never use production as the first place to test a rollback.

## 17. Self-Check Exercises

**Scenario A.** Git tag `v2.4.0` still exists, yet image `orders-api:2.4.0` was deleted. Can you roll back from the tag alone?

*Answer:* Not reliably. A Git tag identifies a source commit, not the published image bytes. You need the stored artifact or a controlled rebuild process; rebuilding does not equate to the exact old artifact.

**Scenario B.** The release manifest records version 2.4.0, yet the registry tag now points to a newer image. What should be used to restore the exact image?

*Answer:* The `OCI repository@sha256:digest` recorded in the manifest, after verifying the digest and artifact still exist.

**Scenario C.** The Maven repository has JAR version 2.4.0, yet its SHA-256 does not match the release manifest. Should you run it?

*Answer:* No. Halt the rollback and investigate the artifact/repository; never update the expected checksum just to make the check pass.

**Scenario D.** Kubernetes `rollout undo` reverted to the previous revision, yet the app still fails because a ConfigMap changed. Why?

*Answer:* Deployment revisions primarily restore the Pod template; standalone ConfigMaps must be versioned/restored separately or managed together with the release via Helm/GitOps.

**Scenario E.** App 2.4.1 already dropped a column needed by app 2.4.0. Should you roll back the binary immediately?

*Answer:* Not before evaluating schema/data. A forward-fix or data restore may be needed; expand-and-contract keeps old apps compatible during the rollback window.

**Scenario F.** Helm history shows revision 8 was good. Running rollback creates revision 9. Is the app version now 9?

*Answer:* No. A Helm revision is the sequence number of the release operation; the app version remains whatever is recorded in the chart/image manifest.

**Scenario G.** The old JAR still exists in a developer's local Maven cache. Is that sufficient as a production rollback source?

*Answer:* No. A personal cache is not a durable artifact store with retention, access control, checksums/provenance, and auditing.

**Scenario H.** The old release has a confirmed critical CVE. Should you roll back to it when the new release hits a regression?

*Answer:* Not automatically. Weigh the security risk; a forward-fix or choosing another known-good release without blocked vulnerabilities may be required.

## 18. Rollback Plan Acceptance Checklist

**Artifacts and identity:**

- Every release has a product version, release ID, Git commit/tag, and CI run ID.
- Maven JAR has exact coordinates/classifier and SHA-256.
- OCI image has repository/digest, platform manifest, and registry location.
- Builder/run image, toolchain, SBOM, and provenance are stored when required by policy.
- Release manifest links app, image, chart, config, and database migration level.
- Release coordinates/tags are never overwritten.

**Retention and access:**

- Release artifacts live in a durable repository/registry.
- Snapshot cleanup does not touch the release repository.
- Retention covers the rollback window and all currently deployed artifacts.
- Corresponding charts, config manifests, SBOMs, and metadata are also retained.
- Rollback identity has needed read/pull permissions without needing publish permissions.
- Restore drills confirm old artifacts can still be downloaded and checksums/digests match.

**Database and runtime compatibility:**

- Migrations use expand-and-contract whenever app rollback is needed.
- Old app is tested against the post-migration schema.
- Down migrations are never run automatically if there is any risk of data loss.
- Config/feature flags/secrets have clear versions/references and compatibility.
- Message/API/cache contracts are evaluated.
- Background workers/consumers are coordinated alongside app releases.

**Execution and verification:**

- Runbook selects targets by release manifest, not merely version labels.
- Kubernetes/Helm revision history is retained long enough.
- Images are deployed by digest; never rely on mutable `latest`.
- Rollouts/restarts have timeouts and health checks.
- Smoke tests, business metrics, and logs are checked after rollback.
- Incident/release records save artifact digest, config revision, schema level, and outcomes.
- The team has rehearsed rollback in staging and knows the actual RTO.

**Conclusion:** A rollback plan is trustworthy when the team retains **the exact built artifacts**, identifies them by Maven coordinates or OCI digest, keeps a release manifest with source/build/config/schema metadata, and verifies integrity before redeploying. Kubernetes/Helm helps restore deployment revisions, yet does not automatically revert databases, external configuration, or data. Design compatibility and retention before releasing, then rehearse fetching old artifacts, redeploying, and verifying health so rollbacks work when needed.

### Official Documentation

- Docker Docs — Pull an image by digest: https://docs.docker.com/reference/cli/docker/image/pull/
- Docker Docs — Validate image inputs and require digest references: https://docs.docker.com/build/policies/validate-images/
- Apache Maven Deploy Plugin — Usage: https://maven.apache.org/plugins/maven-deploy-plugin/usage.html
- Apache Maven Dependency Plugin — dependency:get: https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html
- Gradle — The Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Kubernetes — Update a Deployment Without Downtime and roll back: https://kubernetes.io/docs/tasks/run-application/update-deployment/
- Kubernetes — kubectl rollout undo: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_undo/
- Kubernetes — Deployment revision history: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- Helm — helm history: https://helm.sh/docs/helm/helm_history/
- Helm — helm rollback: https://helm.sh/docs/helm/helm_rollback/
- Spring Boot 3.3 — Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/
- Spring Boot 3.3 — Gradle Plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/
