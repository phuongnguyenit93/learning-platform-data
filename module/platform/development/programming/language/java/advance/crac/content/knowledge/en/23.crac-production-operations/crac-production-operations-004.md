# Choosing an Image Rebuild Policy Based on Changes and Image Age

A CRaC (Coordinated Restore at Checkpoint) checkpoint image is a snapshot of a Java process's state at the time the image is created. It can store loaded application code, a warmed-up heap, thread state, native memory, and runtime structures supported by the checkpoint engine. When the application is restored, the process continues from that state and runs resource recovery callbacks.

Because a checkpoint image carries the state of a specific run, the operations team must decide when an existing image can continue to be used, when only external state needs to be refreshed, and when a new image must be created. An image may still be technically restorable yet be outdated relative to the current application release, JDK, native libraries, configuration, database schema, or security policy.

An image rebuild policy must answer two separate questions:

- **Is the image still compatible to restore?** This depends on code, JDK/CRaC build, checkpoint engine, kernel, CPU, container runtime, and platform conditions.
- **Is the state inside the image still suitable for serving?** This depends on caches, configuration, credentials, sessions, leases, data, and the state of external services.

Image age is an important operational signal, yet it is not the sole proof of compatibility. An image created yesterday can still be unsuitable if the JDK or a secret has been revoked. An older image may still restore on the right profile yet require refreshing caches or credentials before receiving traffic.

This article presents how to classify changes, set image age thresholds, define rebuild triggers, manage versions and rollbacks, and integrate that policy into CI/CD so outdated or unsupported images are never used.

## 1. Rebuilding an Image Is a Multi-Signal Decision

Do not rebuild a checkpoint based solely on a time interval or solely on a new deployment. Combine these signals:

- Application code or dependency changes.
- JDK, CRaC runtime, or checkpoint engine changes.
- Kernel, CPU architecture/features, or container runtime changes.
- Native library, JVM flags, or filesystem layout changes.
- External configuration and data changes.
- Secret, certificate, token, or identity policy changes.
- Image age and how long the image has been retained.
- Restore failures, callback failures, or performance degradation.
- Rollback requirements and release support duration.

There are three basic actions:

1. **Reuse:** continue using the current image when compatibility and freshness policies are still met.
2. **Reconcile:** keep the image yet refresh dynamic state after restore, such as fetching new secrets, reconnecting to the database, loading new configuration, or rebuilding caches.
3. **Rebuild:** start the application from the current valid artifact/runtime, warm up again, and create a new checkpoint image.

Sometimes an image must be **retired**: disallow restoring it, revoke access permissions, and delete the artifact per retention policy. Rebuilding does not automatically replace the retire step if the old image contains credentials or data that are no longer permitted for use.

## 2. Distinguishing Compatibility from State Freshness

These two concepts must be managed separately.

### 2.1 Compatibility

Compatibility answers whether the runtime can restore the process from the image. Key factors include:

- JDK vendor, version, and exact build.
- CRaC API/runtime build.
- Checkpoint engine and version.
- OS/kernel and system requirements.
- CPU architecture and features.
- Native libraries and ABI.
- Container image digest, runtime, namespaces, and mounts.
- JVM flags and runtime configuration.

If a change falls outside the vendor-supported scope, do not use an old image merely because it remains in storage. A new image must be created on the supported target profile, or fall back to a fresh JVM startup.

### 2.2 Freshness

Freshness answers whether the state stored inside the image is still fresh enough for the application to continue operating correctly.

Examples:

- A feature flag on the heap has been disabled in the configuration service.
- An access token has expired.
- A secret has been rotated.
- A session has been revoked.
- A reference data cache is stale.
- A lease has been granted to another instance.
- The message broker has changed partition assignments.
- The database schema has been upgraded.

These changes do not always require creating a new checkpoint. Typically, the application needs to reconnect and reconcile after restore. However, if the image contains state that cannot be safely refreshed, or code inside the image is incompatible with the new state, the image must be discarded and recreated.

### 2.3 Distinction Table

| Situation | Compatibility | Freshness | Usually appropriate action |
|---|---|---|---|
| Only new data added in the database, schema compatible | May still pass | Cache may be stale | Reconcile or rebuild cache |
| Access token expired | Process can restore | Credentials no longer valid | Obtain new token after restore |
| Feature flag changed | Process can restore | Stale config snapshot | Load new revision and validate |
| JAR/application code changed | Image contains old code | Image does not represent new release | Rebuild checkpoint |
| JDK/engine changed outside compatibility policy | Not guaranteed | May be unrelated | Rebuild and test on new runtime |
| Kernel/CPU node pool changed | Need source-target verification | May be unchanged | Run compatibility tests; rebuild if policy requires |
| Certificate revoked | Process can restore | Trust/identity state invalid | Revoke image if it contains old key; obtain new certificate |
| Image exceeds max age | Compatibility not necessarily lost | Increased risk of stale state | Reconcile or rebuild per age policy |
| Checkpoint corrupted | Fails | Unrelated | Retire artifact and recreate |

Do not use a generic status such as "old image" to handle every case. Clearly record whether an image is blocked due to compatibility, freshness, security, integrity, or image-age policy.

## 3. Classifying Changes and Rebuild Actions

Before configuring automation, build a change-classification table. This table serves as system policy and must be checked against the JDK vendor and checkpoint engine support matrix.

| Change | Default action | Reason |
|---|---|---|
| Source code or JAR changed | Rebuild | Image contains loaded code from old release |
| Java dependency changed | Rebuild | Classes and object graph may belong to old dependency |
| JDK vendor/build changed | Rebuild and test | Runtime implementation may differ |
| CRaC runtime/API changed | Rebuild and test | Callbacks and checkpoint format may differ |
| Checkpoint engine changed | Rebuild and test | Process image depends on the engine |
| Native library/JNI changed | Rebuild and test | Native code, ABI, and memory state may differ |
| JVM flags affecting runtime changed | Rebuild | Image was created with different runtime configuration |
| Container base image changed | Evaluate; usually rebuild | Userland, JDK, or native libraries may change |
| Kernel patch within supported range | Test target | May only require verifying restore on new target |
| CPU node pool changed | Test target | Feature baseline or architecture may differ |
| Config revision changed | Reconcile | Load and validate current config after restore |
| Secret/certificate rotated | Reconcile or retire | Obtain new credentials; images containing revoked secrets must be retired |
| Database schema changed | Check compatibility | Code inside image must be compatible with new schema |
| Cache TTL expired | Invalidate/rebuild cache | Cache is no longer fresh enough |
| Image exceeds max age | Reconcile or rebuild | Limit stale state and operational risk |
| Invalid artifact checksum | Retire | Integrity cannot be trusted |

### 3.1 Code Changes Always Create a New Application Generation

A checkpoint image is not a container where you can swap the underlying JAR and keep using the old heap. The heap may hold classes, objects, singletons, framework context, and data created by the previous binary.

When the application JAR or dependencies change, the usual safe approach is:

1. Build a new JAR.
2. Build/pin a new container image if the runtime or filesystem changed.
3. Start a new JVM.
4. Warm up the new application.
5. Create a new checkpoint.
6. Test restore before publishing.

Do not swap a new JAR into the container filesystem and attempt to restore a checkpoint created from an old JAR. The process image may still contain classes and objects from the old code.

### 3.2 Host Changes Do Not Always Require Immediate Rebuilding

A kernel patch or node pool change may fall within the vendor's compatibility range. In that case, you can keep the checkpoint artifact and run restore tests on the new target.

However, reuse is permitted only after policy confirms the source-target pair falls within supported bounds and required tests pass. Do not infer that same Linux or same amd64 guarantees compatibility.

### 3.3 External Changes Usually Require Reconciliation

Configuration services, secret managers, databases, and brokers have their own lifecycles. They continue changing while the image is stored. After restore, fetch current state from authoritative sources.

Do not create a new checkpoint every time a feature flag changes if the image can safely load the new configuration. Conversely, if code inside the image does not understand the new config schema, block the old image and build a compatible release.

## 4. Building a Checkpoint Fingerprint

Each checkpoint needs a manifest recording the factors that formed the image. Fingerprints help the pipeline compare the image-creation environment with the intended restore environment.

A manifest may contain:

~~~yaml
checkpoint:
  id: orders-2.8.1-amd64-001
  createdAt: "2026-11-13T07:00:00Z"
  artifactDigest: sha256:example-checkpoint-digest

application:
  name: orders-service
  version: 2.8.1
  sourceCommit: abcdef123
  jarDigest: sha256:example-jar-digest

runtime:
  jdkVendor: example-vendor
  jdkVersion: 21.x
  jdkBuild: example-crac-build
  cracRuntime: example-crac-version
  engine: example-engine
  engineVersion: example-engine-version
  jvmFlagsProfile: production-default

platform:
  os: linux
  architecture: amd64
  kernelProfile: kernel-profile-a
  containerDigest: sha256:example-container-digest
  containerRuntime: example-runtime

compatibility:
  sourceProfile: linux-amd64-jdkA-engineE1
  allowedTargets:
    - prod-amd64-poolA
    - prod-amd64-poolB

freshness:
  configRevisionAtCreate: cfg-1842
  schemaCompatibility:
    minimum: 42
    maximum: 44
  maxAgeHours: 168
~~~

This is an illustrative schema defined by the pipeline, not a mandatory CRaC format. Do not put passwords, tokens, private keys, or secret values in the manifest. Store only non-sensitive version IDs, digests, or references.

### 4.1 Policy-Based Fingerprint Comparison

Not every field necessarily requires an exact match. Categorize them into:

- **Must match:** must match exactly, such as application build, JDK build, or engine if required by the vendor.
- **Allowed range:** allowed to differ within vendor-supported bounds, such as certain kernel patch levels.
- **Must retest:** changes requiring a restore test before continuing to use the image.
- **Runtime refresh:** state re-fetched after restore, such as secrets, config, and service endpoints.
- **Informational:** fields solely for traceability that do not determine compatibility.

Do not compare only one combined hash and report a mismatch. When fingerprints differ, the pipeline must report which field changed and which policy applies to that field.

### 4.2 Binding the Image to Release and Target Profiles

The checkpoint ID must be immutable and linked to:

- Application release.
- JAR digest.
- Container image digest.
- JDK/CRaC build.
- Engine version.
- Source environment profile.
- Verified target profiles.
- Checkpoint timestamp and checksum.

Do not use mutable tag names such as latest as the sole identifier. A tag can point to a different artifact after the next build.

## 5. Setting a Maximum Image Age Policy

Image age is the time from when the checkpoint was created until it is selected for restore. It can be calculated as:

~~~text
imageAge = currentTime - checkpoint.createdAt
~~~

Image age helps limit how long a snapshot can hold stale state. However, there is no single TTL value right for every application. An image can be old yet still compatible; a freshly created image can also hold credentials that were revoked shortly afterward.

### 5.1 Distinguishing Soft Age and Hard Max Age

Two thresholds can be defined:

- **Soft age:** when exceeded, the pipeline schedules creating a new image or increases freshness checks. The current image may still be used if reconciliation and compatibility pass.
- **Hard max age:** when exceeded, policy forbids restoring that image. A new image must be created or fall back to fresh startup.

Illustrative example:

| Image age | Policy |
|---|---|
| 0–24 hours | Reuse if fingerprint and external state are valid |
| 24–72 hours | Reuse after freshness validation; schedule rebuild |
| 72–168 hours | Reuse only with exception/policy and full reconciliation |
| Over 168 hours | Hard expire; recreate or fresh startup |

These intervals are merely policy design examples. Choose thresholds based on release frequency, dependency volatility, state refreshability, startup goals, and security risk.

### 5.2 Choosing TTL by Application Type

TTL should reflect change frequency and risk:

| Workload | Factors determining TTL |
|---|---|
| Stateless API | Release frequency, runtime patches, and cache freshness |
| Service holding large caches | Cache invalidation, data revision, and rebuild time |
| Event-processing consumer | Cursor, partition assignment, and replay policy |
| Service holding credentials | Token TTL, secret rotation, and identity refresh |
| Batch worker | Workflow deadline and ability to resume from durable state |
| Service with native resources | Runtime/engine compatibility and resource lifecycle |
| Regulated workload | Security policy, audit, and retention requirements |

Do not set a short TTL just to build more images. If the costly part is warm-up, measure rebuild cost against reuse benefits. Conversely, do not extend TTL just to save CI cost if state inside the image carries stale or credential risk.

### 5.3 Image Age Does Not Replace Expiry of Internal Data

A 10-minute-old image may contain an expired token with a 5-minute TTL. A 5-day-old image may hold no tokens and only need to load new configuration.

Therefore, check each expiration type individually:

- Token exp and refresh token validity.
- Session idle/absolute timeout.
- Certificate validity/revocation.
- Lease TTL and fencing tokens.
- Cache TTL and source revision.
- Request/workflow deadlines.
- Database schema compatibility.
- Image hard max age.

Do not use image TTL to replace checking credentials and state for each dependency.

## 6. Choosing Image Rebuild Triggers

Triggers can be categorized into mandatory, scheduled, age-based, event-driven, and operational.

### 6.1 Release-Based Mandatory Triggers

Create a new checkpoint when the application release or image-creating runtime components change:

- JAR or source build.
- Dependency graph.
- JDK/CRaC build.
- Checkpoint engine.
- Native libraries.
- JVM flags affecting runtime.
- Required container base image or filesystem.
- Warm-up procedure or object initialization changes.

These triggers carry high priority because the old image contains the previous code/runtime generation.

### 6.2 Platform-Change Triggers

When a node pool changes kernel, CPU, container runtime, or security profile:

1. Collect the new target fingerprint.
2. Compare against verified target profiles.
3. If the change is vendor-supported and policy-permitted, run restore tests.
4. If tests pass, continue using the image within verified bounds.
5. If unsupported or tests fail, create a new image on the appropriate profile or use fresh startup.

Rebuilding an image solely because host metadata changed is not always necessary. What matters is verifying source-target compatibility. Some changes affect only the target, not the image contents.

### 6.3 Freshness-Event Triggers

Events such as secret rotation, certificate renewal, feature flag updates, or schema migrations normally trigger reconciliation. Rebuild the image only if:

- The image contains revoked credentials that cannot be guaranteed removed.
- Code inside the image is incompatible with the new state.
- Caches or object graphs cannot be rebuilt after restore.
- Policy requires the image to be created from the current config revision.
- External state cannot be safely reconciled.

If the image has proper refresh callbacks, rebuilding is unnecessary merely because a secret version changed.

### 6.4 Age-Based Triggers

A scheduler or release pipeline checks createdAt. When an image exceeds soft age, create a new image in the background. When it exceeds hard max age, block restore.

Creating the new image ahead of time avoids discovering during scale-out that the old image has expired. Allow sufficient time for warm-up, checkpointing, restore testing, and publishing before the current image hits hard max age.

### 6.5 Error or Performance Triggers

A new image can be created upon detecting:

- Repeated restore failures.
- afterRestore callbacks failing because image state is no longer suitable.
- First-request latency or time-to-ready exceeding thresholds.
- Warm-up cache state becoming ineffective.
- Native resource leaks or abnormal memory usage.
- Image artifact integrity failures.

Do not use rebuilding to mask code bugs or dependency errors. Record the root cause first to determine whether the old image is the cause or merely where the bug manifests.

## 7. Decision Matrix: Reuse, Reconcile, or Rebuild

A decision table helps pipelines and operators take consistent actions.

| Condition | Reuse | Reconcile | Rebuild |
|---|---:|---:|---:|
| Application/JAR digest matches required release | Possible | Possible | Unneeded if other conditions pass |
| Application/JAR digest differs | No | No | Yes |
| JDK/engine outside compatibility policy | No | Insufficient | Yes |
| Target profile unverified | Not yet | Insufficient | Rebuild/test on suitable target or fresh startup |
| Config revision changed yet schema compatible | Possible | Yes | Only if policy pins revision |
| Secret rotated and runtime identity re-fetchable | Possible | Yes | Not mandatory |
| Revoked credentials remain in image | Disallowed by security policy | May be insufficient | Retire image and recreate safely |
| Cache TTL expired yet rebuildable after restore | Possible | Yes | Not mandatory |
| Cache cannot refresh and fresh data required | No | Insufficient | Yes |
| Image exceeds soft age | Conditional | Yes | Schedule |
| Image exceeds hard max age | No | Insufficient | Yes or fresh startup |
| Invalid checksum | No | No | Retire |
| Database schema incompatible with code in image | No | Insufficient | Rebuild compatible application release |
| Target restore test passes, application checks pass | Yes | Per policy | Not mandatory |

The word "possible" means remaining conditions—integrity, compatibility, freshness, and security—must also pass. Do not treat a single row as the final decision.

### 7.1 Precedence Rules

When multiple triggers occur simultaneously, apply this order:

1. **Security/integrity block:** images with revoked secrets, compromised integrity, or usage bans must be retired immediately.
2. **Compatibility block:** incompatible code/runtime/target must not restore.
3. **Hard age expiry:** images exceeding maximum age must not restore.
4. **Freshness reconciliation:** refresh dynamic state and verify dependencies.
5. **Performance policy:** if the image fails operational targets, create a new image or adjust warm-up.
6. **Reuse:** only when all mandatory conditions pass.

Do not allow a "process restore succeeded" outcome to override a security block or hard age expiry.

## 8. Process for Rebuilding Images Without Disrupting Deployments

Rebuilding an image does not necessarily require stopping the serving service. A new image can be built in parallel, switching the deployment only after restore tests pass.

~~~mermaid
flowchart TD
    A["Current checkpoint is serving"] --> B["Change or age trigger"]
    B --> C["Build new JAR/container if needed"]
    C --> D["Start isolated checkpoint builder"]
    D --> E["Warm up with approved dependencies"]
    E --> F["Create new checkpoint"]
    F --> G["Restore test on required targets"]
    G --> H{"All required checks pass?"}
    H -->|No| I["Keep current image if still valid<br/>or use fresh startup"]
    H -->|Yes| J["Publish immutable new image"]
    J --> K["Canary restore"]
    K --> L["Promote new image"]
    L --> M["Retire old image after rollback window"]
~~~

### 8.1 Parallel Build

While the new image is being created:

- Current instances continue serving if still valid.
- CI or checkpoint builder uses an isolated environment.
- Warm-up data is controlled.
- Credentials have appropriate scope and TTL.
- The new checkpoint artifact is created with a new ID.
- Restore tests run on mandatory target profiles.

Do not overwrite a checkpoint artifact currently in use. Create a new version and publish immutably.

### 8.2 Canary Restore

After CI tests pass, a subset of canary instances can restore from the new image. Monitor:

- Restore success rate.
- Callback duration.
- External reconciliation.
- Time-to-ready.
- First-request latency.
- Error rate and resource usage.

If the canary fails, halt promotion. The old image may be kept as fallback only if it still meets compatibility, security, and age policies.

### 8.3 Promote and Retire

When the canary passes, shift traffic or roll out to the new image. Retain the old image for the defined rollback window. Once the window expires:

- Mark the old image RETIRED.
- Block new restores.
- Revoke read access if needed.
- Delete artifacts per retention policy.
- Check backups/replicas and registry caches per procedure.

## 9. Managing Rollback When a New Image Has Issues

Rolling back a checkpoint is unlike rolling back a plain JAR. An old image may contain old code, config snapshots, tokens, or schema assumptions.

Before retaining an image for rollback, verify:

- Image remains within the compatibility window.
- JDK/engine/target profiles are still supported.
- Current database schema remains compatible with old code.
- New external APIs and config do not break old code.
- Credentials are freshly obtained after restore.
- Image is not retired or security-revoked.
- Image has not exceeded hard max age.

### 9.1 Expand/Contract Helps Preserve the Rollback Window

If database schemas change using expand/contract, old and new code can operate concurrently for a period. This allows rolling back the application release without immediately rolling back the database.

However, after the contract step drops columns or changes semantics, the old image may no longer be compatible. In that case, retire the old checkpoint before or concurrently with the contract migration.

### 9.2 Do Not Roll Back to a Security-Revoked Image

If an old image was retired due to compromised credentials, do not restore it merely because the new image has bugs. Use a fresh startup from a safe artifact or create a new checkpoint. Security revocation takes precedence over rollback convenience.

### 9.3 Bounding the Rollback Time

The rollback window should be shorter than or equal to the period during which:

- Schema remains compatible.
- Runtime profile remains supported.
- Credentials can be reissued.
- Image has not reached hard max age.
- The release remains permitted to operate.

Store the rollback expiration date in the manifest or deployment metadata so pipelines do not select old images indefinitely.

## 10. Distinguishing Image Rebuilds from Refreshing External State

A common operational mistake is recreating checkpoints on every external change, even when the application can refresh after restore. Doing so increases build costs and creates extra artifacts without improving compatibility.

### 10.1 What Can Usually Be Refreshed

After restore, the application can usually:

- Fetch current secret versions.
- Refresh access tokens.
- Reconnect to databases and check schemas.
- Resolve service discovery/DNS.
- Load feature flags and new config revisions.
- Rebuild caches.
- Rejoin message consumer groups.
- Reacquire leases and fencing tokens.
- Revalidate sessions or identities.

These operations should reside in Resource callbacks or an appropriate lifecycle stage. Readiness turns true only after mandatory dependencies are verified.

### 10.2 What Usually Requires a New Image

- Application code has changed.
- Classes or dependencies on the heap no longer match the release.
- JDK/engine build changed outside compatibility bounds.
- Native libraries or ABI changed.
- JVM flags changed runtime assumptions.
- The image was created from the wrong environment or holds state that cannot be safely removed.
- Checkpoint artifact is corrupted or has an invalid checksum.
- Policy requires the image to be built after a specific security patch.

### 10.3 When External State Cannot Be Verified

If the secret manager or configuration service is unavailable, do not assume the snapshot on the heap is current.

Keep the instance in RECONCILING and retry with limits. If policy allows degraded mode, enable only features independent of unverified state. If mandatory security or data dependencies cannot be checked, keep readiness false.

## 11. Environment-Specific Policies

Staging and production do not necessarily share the same TTL or the same checkpoint artifact.

| Environment | Goal | Recommended policy |
|---|---|---|
| Local development | Test callbacks and learn API | Temporary image, short TTL, mock data |
| CI | Regression testing | Build per commit or build, delete after short retention |
| Staging | Near-production testing | Build per release candidate, test target profiles and external reconciliation |
| Production | Fast scale/rollout | Build per release/runtime profile, hard max age, canary and rollback window |
| Disaster recovery | Cross-region recoverability | Separate image or verified target pair, periodically tested |
| Long-running batch | Resume workflow | Prioritize durable state and deadlines; checkpoint age per workflow semantics |

Production checkpoints should typically be created from a tested release candidate with configuration free of long-lived credentials. After restore, fetch runtime identity and secrets according to the target environment.

Do not promote a staging checkpoint directly to production if the heap holds staging-specific endpoints, tenants, identities, or caches. If the design allows one image across environments, explicit reconciliation steps and testing are mandatory.

## 12. Example YAML Policy

A policy can describe triggers, image age, and actions:

~~~yaml
checkpointPolicyVersion: 1

image:
  maxAge:
    softHours: 72
    hardHours: 168
  immutable: true

rebuildOn:
  applicationDigestChange: true
  dependencyDigestChange: true
  jdkBuildChange: true
  cracRuntimeChange: true
  checkpointEngineChange: true
  nativeLibraryChange: true
  jvmRuntimeProfileChange: true
  containerDigestChange: true

retestOn:
  kernelProfileChange: true
  cpuFeatureProfileChange: true
  containerRuntimeChange: true
  targetNodePoolChange: true

reconcileAfterRestore:
  configuration: true
  secrets: true
  certificates: true
  databaseConnections: true
  schemaCompatibility: true
  serviceDiscovery: true
  cacheRevision: true
  messageAssignments: true
  leases: true

security:
  rejectRevokedArtifact: true
  requireArtifactChecksum: true
  requireApprovedProvenance: true
  requireRuntimeIdentityAfterRestore: true

release:
  requiredTargetProfiles:
    - production-amd64-a
    - production-amd64-b
  requireRestoreTest: true
  requireApplicationReadiness: true
  canaryBeforePromotion: true
  rollbackWindowHours: 48
~~~

This is an illustrative structure defined by the deployment system, not a standard CRaC configuration file. Hour values and profiles must be replaced with actual policy values.

### 12.1 Validating Policy Before Use

The pipeline should verify:

- softHours is less than hardHours.
- Every required target profile exists.
- Each trigger has a corresponding action.
- Image ID and digest are immutable.
- No secrets appear in the manifest.
- Rollback window does not exceed image hard max age.
- Revoked images cannot be selected even if still in storage.
- External reconciliation is enabled for mandatory dependencies.

If the policy is missing or invalid, fail closed for checkpoint deployment and use fresh startup per fallback policy if allowed.

## 13. Example Image Selection Logic

A simple decision service can be implemented based on metadata and policy. The example below illustrates decision order, not a complete engine implementation.

~~~java
import java.time.Duration;
import java.time.Instant;

enum ImageAction {
    REUSE,
    RECONCILE,
    REBUILD,
    RETIRE
}

record ImageMetadata(
        String applicationDigest,
        String runtimeFingerprint,
        Instant createdAt,
        String artifactDigest,
        boolean revoked) {
}

record TargetState(
        String applicationDigest,
        String runtimeFingerprint,
        Instant now,
        Duration hardMaxAge,
        boolean targetVerified,
        boolean externalStateCanBeReconciled) {
}

final class CheckpointPolicy {

    ImageAction decide(
            ImageMetadata image,
            TargetState target) {

        if (image.revoked()) {
            return ImageAction.RETIRE;
        }

        if (image.artifactDigest() == null
                || image.artifactDigest().isBlank()) {
            return ImageAction.RETIRE;
        }

        if (!image.applicationDigest()
                .equals(target.applicationDigest())) {
            return ImageAction.REBUILD;
        }

        if (!target.targetVerified()) {
            return ImageAction.REBUILD;
        }

        Duration age = Duration.between(
                image.createdAt(),
                target.now());

        if (age.isNegative() || age.compareTo(
                target.hardMaxAge()) > 0) {
            return ImageAction.REBUILD;
        }

        if (!image.runtimeFingerprint()
                .equals(target.runtimeFingerprint())) {
            return ImageAction.REBUILD;
        }

        if (target.externalStateCanBeReconciled()) {
            return ImageAction.RECONCILE;
        }

        return ImageAction.REUSE;
    }
}
~~~

This example uses fingerprint equality as a strict policy. Production systems typically need a compatibility evaluator able to handle allowed ranges, vendor support, and retest evidence. Actual checksums, image status, target profiles, and mandatory dependencies must also be verified before deciding.

Do not treat RECONCILE as a final state allowing traffic. It is an action to perform. Readiness is enabled only after reconciliation succeeds.

## 14. Integrating Age Policies into Schedulers and CI/CD

An expiring image should not be discovered only when a new instance needs to scale. Monitor image age periodically and create replacement images ahead of time.

### 14.1 Scheduled Refresh

A periodic job can:

1. List active checkpoints.
2. Read createdAt and hard max age.
3. Compare application/runtime fingerprints with the current release.
4. Check whether target profiles remain supported.
5. Create a new image when the current image reaches soft age.
6. Run the restore matrix.
7. Publish the new image if it passes.
8. Mark the old image retiring per the rollback window.

The scheduler should use a lock or idempotency key so multiple concurrently running pipelines do not create duplicate identical images.

### 14.2 Event-Driven Rebuild

Rebuilds can be triggered when:

- An application release is published.
- JDK/engine base image is updated.
- Native dependencies are upgraded.
- A security patch requires rebuilding the runtime image.
- A checkpoint artifact is revoked.
- A restore test detects incompatibility.
- A new target node pool is added.

Do not trigger rebuilds for every config event if config can be refreshed after restore. Use event classification to pick the right action.

### 14.3 CI Release Gate

Before publishing a new checkpoint, the pipeline must:

- Verify JAR/container digests.
- Collect source fingerprint.
- Create the checkpoint from the pinned runtime.
- Check artifact checksum.
- Restore on mandatory target profiles.
- Run callbacks and application smoke tests.
- Check time-to-ready and performance thresholds.
- Record manifest and evidence.
- Publish only when required pairs pass.

The new image must not be treated as replacing the old image until all mandatory steps finish.

## 15. Observing Image Age and Image Lifecycle

Metrics and logs are needed so operators know which image is in use and why a new image was created.

Useful metrics:

- Age of active checkpoints.
- Time remaining until soft age and hard max age.
- Image counts by state: ACTIVE, CANDIDATE, RETIRED, REVOKED.
- Restore counts per checkpoint ID.
- Restore success/failure rate.
- Reconciliation success/failure rate.
- Time-to-ready.
- Rebuild count by trigger.
- Rate of images rejected for compatibility.
- Count of images exceeding hard age.
- Storage usage and count of undeleted expired artifacts.

Event logs should record:

~~~json
{
  "event": "checkpoint_rebuild_decision",
  "currentCheckpointId": "orders-2.8.1-amd64-001",
  "action": "REBUILD",
  "reason": "SOFT_AGE_EXCEEDED",
  "ageHours": 74,
  "softAgeHours": 72,
  "targetProfile": "production-amd64-a"
}
~~~

This example contains no secrets. Release ID, fingerprint delta, and pipeline run ID can be added for traceability.

### 15.1 Measure Time-to-Ready Instead of Only Restore Duration

An image may restore quickly yet take a long time fetching secrets, reconnecting to databases, or rebuilding caches.

Measure these milestones:

~~~text
T0: restore command started
T1: process restored
T2: afterRestore callbacks completed
T3: external state reconciled
T4: readiness true
~~~

- Restore duration = T1 - T0.
- Callback duration = T2 - T1.
- Reconciliation duration = T3 - T2.
- Time-to-ready = T4 - T0.

If rebuilding a new image reduces warm-up yet does not improve time-to-ready, examine dependency recovery rather than simply increasing checkpoint frequency.

## 16. Managing Retention and Image States

Each checkpoint should have a clear lifecycle state:

| State | Meaning | Restorable? |
|---|---|---|
| CANDIDATE | Newly created, under testing | No |
| ACTIVE | Approved for target profiles | Yes, if not expired |
| DEPRECATED | Replaced by newer image, within rollback window | Only per rollback policy |
| RETIRED | Past usage lifetime | No |
| REVOKED | Revoked due to security/integrity/policy | No |
| EXPIRED | Exceeds hard max age | No |

State transitions must be recorded and audited. Do not allow a DEPRECATED image to be selected by default for scale-out merely because it still exists in the registry.

### 16.1 Retention Is More Than Deleting Files

When retiring an image, check:

- Primary artifact store.
- Registry or object storage replicas.
- CI artifacts.
- Node caches.
- Backups.
- Copies downloaded to local workspaces.
- Manifests and deployment references.

If an image is revoked due to credential compromise, handle both the credentials and every copy per incident policy. Deleting files does not revoke exposed credentials.

### 16.2 Keep Enough Images for Rollback, Yet Do Not Keep Forever

Retention should balance:

- Rollback window.
- Image hard max age.
- Database schema compatibility.
- Runtime support window.
- Security retention.
- Storage cost.
- Time needed for incident investigation.

An old image that is no longer compatible has no rollback value merely because it remains stored. Automatically mark it RETIRED once rollback conditions are no longer met.

## 17. Testing the Image Rebuild Policy

Policies should be tested like code. Tests can be written for the decision table without launching a real JVM or checkpoint engine.

Required cases:

| Case | Expected outcome |
|---|---|
| Same application/runtime fingerprint, image valid | REUSE or RECONCILE |
| Application digest changed | REBUILD |
| JDK/engine changed outside policy | REBUILD |
| Target profile unverified | Block reuse, require test/rebuild |
| Soft age exceeds threshold | Schedule rebuild |
| Hard age exceeds threshold | Do not restore |
| Secret rotated yet re-fetchable after restore | RECONCILE |
| Credential revoked and image banned | RETIRE |
| Invalid checksum | RETIRE |
| Cache stale yet rebuildable | RECONCILE |
| Schema incompatible with code | REBUILD application release or block |
| Old image within rollback window and still compatible | Allow rollback per policy |
| Old image security-revoked | Disallow rollback |

Beyond policy unit tests, integration tests are needed to confirm:

- A new image is created when the right trigger fires.
- Duplicate images are not created when multiple schedulers run.
- Old artifacts are not overwritten.
- Restore jobs select the right image ID.
- Expired or revoked images are rejected.
- Failed reconciliation keeps readiness false.
- Rollback selects only still-valid images.
- Retention jobs do not delete active images or images within the rollback window.

## 18. Common Mistakes

### Rebuilding on a Schedule Without Checking Changes

A daily cron job fails to detect a secret revoked right after the image was created. Event-driven revocation and runtime validation are required.

### Using Image Age as Proof of Compatibility

A brand-new image can still be incompatible with the target kernel or CPU. Compatibility requires fingerprints and testing.

### Rebuilding on Every Config Change

Dynamic configuration can usually be refreshed after restore. Continuous rebuilding raises costs without solving state ownership.

### Keeping Old Images for Rollback Indefinitely

Schema, runtime, and security policies can render old images unusable. The rollback window must be bounded and tested.

### Overwriting Active Checkpoint Artifacts

This breaks traceability and can cause new instances to receive different bytes than the tested image. Use immutable checkpoint IDs.

### Checking Only Process Restore

A live process does not mean the application is ready. Check callbacks, external reconciliation, and functional paths.

### Allowing Restore of Revoked Images

An image may still have a valid checksum while credentials inside it have been revoked. Security status must be checked separately.

### Rebuilding to Mask Application Bugs

If callbacks or dependencies fail repeatedly, creating a new image may merely mask symptoms. Collect root causes and classify errors before deciding to rebuild.

### Omitting Test Duration from Age Policy

A candidate image may take many hours to run the restore matrix. By the time it is published, the image age differs from its creation time. Use the actual createdAt and recheck hard age before deploying.

## 19. Recommended Operational Workflow

A practical workflow to choose reuse, reconcile, or rebuild may include:

**Step 1 — Read the manifest.** Obtain checkpoint ID, createdAt, application digest, JDK/engine, container digest, and source profile.

**Step 2 — Check integrity and security state.** Verify checksum, provenance, REVOKED status, and artifact access permissions.

**Step 3 — Compare application/runtime fingerprint.** If code, dependencies, JDK, or engine changed outside policy, require rebuild.

**Step 4 — Verify target profile.** Compare kernel, CPU, container runtime, and target profile against the verified matrix.

**Step 5 — Calculate image age.** Apply soft age and hard max age. Never restore an image exceeding the hard limit.

**Step 6 — Classify external changes.** Determine whether config, secrets, schema, caches, sessions, leases, and broker state can be reconciled or force retire/rebuild.

**Step 7 — Select action.** Reuse, reconcile, rebuild, or retire following precedence: security, compatibility, hard age, and freshness.

**Step 8 — Create candidate image when needed.** Build from pinned JAR/container/runtime, warm up with suitable data, and assign a new artifact ID.

**Step 9 — Test restore.** Run source-target matrix, callbacks, external reconciliation, functional smoke, and performance checks.

**Step 10 — Controlled promotion.** Publish immutable artifact, canary restore, and transition to ACTIVE after passing.

**Step 11 — Maintain rollback window.** Keep old image only if still compatible, not revoked, and not hard-expired.

**Step 12 — Retire and clean up.** Block new restores, revoke permissions, and delete artifacts per retention policy.

## 20. Completion Criteria for an Image Rebuild

A new image should be considered ACTIVE only when:

- Built from the right application release and runtime profile.
- Manifest completely records JAR/container digests, JDK/engine, and source profile.
- Checkpoint artifact has a valid checksum.
- Mandatory target profiles are within supported bounds.
- Actual restore tests pass.
- Resource callbacks complete.
- External state is reconciled.
- Functional smoke tests pass.
- Time-to-ready and resource usage are within thresholds.
- Security scans, provenance, and access policies pass.
- Rollback/retention metadata is set.

A newly created image that has not passed restore tests remains CANDIDATE. Do not let schedulers or deployments automatically select it solely because createdAt is newer.

## References

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore model and process state.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): preparing the runtime and running a CRaC application.
- [CRaC — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): engines and compatibility scope by build.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): managing Resource callbacks before checkpoint and after restore.
- [CRaC — Debugging](https://crac.org/reference/debugging/): investigating checkpoint/restore failures.
- [OCI Image Format Specification](https://github.com/opencontainers/image-spec): immutable container image digests and metadata.
- [Kubernetes — Container Images](https://kubernetes.io/docs/concepts/containers/images/): managing images, tags, and digests in deployments.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): secret lifecycle, rotation, and revocation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): validators and conditional requests when managing revisions.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): protecting tokens and refresh tokens.
