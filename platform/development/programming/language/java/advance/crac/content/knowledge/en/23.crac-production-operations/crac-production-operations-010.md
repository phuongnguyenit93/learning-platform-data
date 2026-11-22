# Incident Handling, Image Revocation, and Space Reclamation Procedures

In Java CRaC operations, a checkpoint image is an artifact with its own lifecycle. An image may become corrupted, become incompatible with a new runtime, contain revoked credentials, or consume storage space after multiple creations and replications. When an incident occurs, the operations team needs to both restore the service and control the images, copies, snapshots, and resources still being referenced.

It is necessary to distinguish a **CRaC checkpoint image** from a **container image**. A container image contains a filesystem and layers to create a container; a checkpoint image contains the state of a running process. Both artifacts may be stored in the same registry or storage, but they have different metadata, compatibility conditions, risks, and revocation procedures.

A good procedure must answer four questions: which image is currently in use, which image is still permitted for restore, which image needs to be quarantined or revoked, and what data is actually freed after deletion.

## 1. Classification of CRaC Incidents

Common incidents can be divided into the following categories:

| Category | Symptoms | Handling Goal |
|---|---|---|
| Checkpoint failure | `beforeCheckpoint()` callback throws an exception or runtime cannot write the image | Recover the original process and identify the failed step |
| Invalid image | Wrong checksum, missing files, mismatched metadata | Prevent restoring from a corrupted artifact |
| Restore failure | Runtime cannot restore the process or `afterRestore()` callback fails | Switch to a valid image or cold startup |
| Incompatible image | JDK, native library, kernel, or configuration has changed | Block restore and create a new image |
| Suspected compromised image | Unusual access permissions, modified image, or potentially exposed credentials | Quarantine the artifact, revoke credentials, and investigate |
| Expired image | No longer fits the release or retention policy | Stop distribution and perform controlled revocation |
| Storage pressure | Filesystem full, inodes exhausted, or quota threshold exceeded | Reclaim only expired artifacts while preserving rollback |
| Restore loop | Instance repeatedly restores then fails or restarts | Stop the loop and switch to a stable recovery path |

You should not handle every case by deleting the newest image. First, determine the scope of impact, the state of running processes, and whether the image is still used as a rollback source.

## 2. Distinguishing Artifacts and Copies

A checkpoint image can exist in multiple locations:

- Temporary directory when the runtime creates the checkpoint.
- Primary checkpoint directory on the node.
- Artifact store or object storage.
- Cached copy on the restore node.
- Volume snapshot or backup.
- Copy in a staging or disaster recovery environment.
- Copy for incident investigation.

Deleting a file in one location does not mean all copies have disappeared. Conversely, deleting an object in an artifact store may not immediately free physical space if the storage uses versioning, snapshots, replication, or deduplication.

Checkpoint images should be managed using an immutable identifier and a manifest. Do not use a file name or directory name as the sole proof of an artifact's identity.

### Metadata to Store for Each Image

| Field | Purpose |
|---|---|
| Image ID | Unique identifier of the checkpoint image |
| Digest/checksum | Verify artifact contents |
| Signature/key ID | Verify creation source and authenticity if signed |
| Application build | Checkpointed application version |
| JDK vendor/version/build | Runtime version that created the image |
| CRaC implementation | CRaC distribution and version |
| OS/kernel/architecture | Critical environmental conditions |
| Native dependency version | Native library or driver version |
| Configuration generation | Corresponding configuration version |
| Created at | Time the image was created |
| Last restored at | Most recent restore time |
| Restore references | Deployments or workloads still using the image |
| Encryption key reference | Independent encryption key used to protect the image |
| Lifecycle state | Current state of the artifact |
| Retention deadline | Earliest time it can be revoked per policy |

Do not put passwords, tokens, or secret contents into the manifest. Only store the identifier or version reference needed to verify and reissue secrets.

## 3. Managing Image Lifecycle States

Images should be managed with explicit states rather than relying solely on file existence:

~~~text
CREATING
   |
   v
VALIDATING
   |
   v
AVAILABLE
   |
   +------> QUARANTINED
   |             |
   |             v
   |          REVOKED
   |             |
   v             v
EXPIRED ------> DELETING
                  |
                  v
                DELETED
~~~

Meaning:

- **CREATING:** runtime is creating the image; must not be distributed.
- **VALIDATING:** verifying integrity, metadata, and restorability.
- **AVAILABLE:** verified and usable according to policy.
- **QUARANTINED:** temporarily disallowed from restore during investigation.
- **REVOKED:** no longer permitted to be used to create new instances.
- **EXPIRED:** past its usage period according to the retention policy.
- **DELETING:** deletion process has started and copies are being processed.
- **DELETED:** confirmed that the artifact and its managed copies have been processed.

An image may still be used as the initial state by already-restored instances, but that does not mean the original image is still permitted for new restores. Instance serving state and artifact distribution state must be tracked separately.

Do not modify an image's contents in place to turn it into a new version. Create a new artifact with a new ID and digest; keep the history of the old image for auditing and rollback.

## 4. Initial Incident Response Procedure

When an incident related to checkpoint or restore is detected:

1. Identify the affected workload, node, image ID, and deployment generation.
2. Record the timestamp, runtime logs, exception chain, and process state.
3. Identify which instances are still serving requests.
4. Pause creating or distributing new images if the root cause may spread.
5. Prevent orchestration from continuing to restore from the suspected image.
6. Preserve logs, manifests, checksums, and artifacts needed for investigation.
7. Choose a recovery path: a verified last-known-good image or cold startup.
8. Only open traffic once readiness and dependencies have been confirmed.

If the incident shows signs of a security compromise, quarantining the image and revoking credentials must be handled in parallel. Do not delete artifacts before preserving the necessary evidence according to the organization's incident response procedure.

### Impact Severity Classification

| Level | Example | Action |
|---|---|---|
| Sev 1 | Production image may contain exposed credentials; multiple workloads affected | Quarantine immediately, block new restores, coordinate secret revocation and service recovery |
| Sev 2 | Corrupted image or restore failure on a group of nodes | Block the faulty image, switch to a valid artifact or cold startup |
| Sev 3 | Old/expired images or storage nearly full while service remains stable | Schedule revocation, keep rollback, and monitor capacity |
| Sev 4 | Missing metadata or retention warning not yet affecting runtime | Fix metadata per procedure, add auditing and checks |

Specific severity levels must follow the system's operational policy. The table above is only a classification framework to standardize response actions.

## 5. Handling Checkpoint Failures

If `beforeCheckpoint()` throws an exception, the checkpoint preparation process did not complete. Operations prior to the exception may have already altered application state: the request gate was closed, workers were stopped, or the connection pool was closed.

Do not assume CRaC automatically rolls back those side effects.

### If the Application Calls Core.checkpointRestore()

When the application orchestrates checkpointing via the API, the calling thread can catch `CheckpointException` and recover the original process:

~~~java
try {
    Core.checkpointRestore();

    // The process has been restored and afterRestore() has handled the resources.
    markRestored();

} catch (CheckpointException checkpointFailure) {
    try {
        reopenResourcesClosedForCheckpoint();
        restartWorkers();
        resumeRequestGate();
    } catch (Exception recoveryFailure) {
        checkpointFailure.addSuppressed(recoveryFailure);
        markNotReady();
    }

    throw checkpointFailure;

} catch (RestoreException restoreFailure) {
    markNotReady();
    throw restoreFailure;
}
~~~

The example is an orchestration skeleton. Only open the request gate after all resources have recovered successfully. If recovery fails, keep the instance in a not-ready state and let orchestration handle it.

### If Checkpoint Is Requested via jcmd

Example of triggering a checkpoint from the terminal:

~~~bash
jcmd <pid> JDK.checkpoint
~~~

The application thread does not have a catch block wrapping an external terminal call. You must observe the command output, runtime logs, and process state. If the application needs immediate rollback within the original process, design an independent recovery mechanism or orchestrate via the in-application API.

### Partially Created Images

If the runtime fails while writing the image, the artifact may only be a partial file. Do not move that file to the AVAILABLE state. Mark it as failed, keep logs for investigation, and delete the temporary artifact after confirming no process or runtime operation is still using it.

The image creation process should write to a separate staging area and only move to the distribution location after the runtime reports success and the validation step completes.

## 6. Handling Restore Failures

Restore can fail before the application can invoke callbacks, inside the runtime, or inside `afterRestore()` when reopening resources.

It is necessary to distinguish:

- **Runtime restore failure:** the process is not restored to the point where the application can execute callbacks.
- **Application restore failure:** the process has recovered, but callbacks or dependency initialization fail.
- **Readiness failure:** callbacks complete, but health checks, workers, or dependencies are not ready.

Do not treat process existence as proof of a successful restore.

### Handling Sequence

1. Keep the instance out of the load balancer or traffic router.
2. Collect the exit code, runtime logs, and exception chain.
3. Determine whether the error belongs to the image, environment, or dependencies.
4. Prevent restart loops with retry limits and backoff.
5. If the image is invalid, mark it QUARANTINED or REVOKED.
6. Choose a verified last-known-good image or cold startup.
7. Check database, broker, file system, secret, and network resources.
8. Only add the instance to the serving pool when readiness meets requirements.

If `afterRestore()` fails after partially opening resources, the callback must clean up the newly created resources or leave the instance in the FAILED state. Do not swallow exceptions and mark READY.

### Choosing Between Another Image and Cold Startup

| Option | When Appropriate |
|---|---|
| Restore last-known-good image | A verified artifact exists that is compatible with the current environment and data |
| Cold startup | No suitable image exists or old memory state needs to be discarded |
| Create a new image | The application has started stably and can safely create a checkpoint |
| Stop workload | Cannot verify the correctness or safety of any recovery path |

Do not automatically restore an older image if the database schema, event offsets, or data format have changed incompatibly. Check the compatibility manifest before rolling back.

## 7. Quarantining and Revoking Images

Quarantine and revoke have different goals:

- **Quarantine:** temporarily prevent using an image while verifying or investigating.
- **Revoke:** officially forbid an image from being used for new restores.
- **Delete:** remove the artifact from storage according to retention and evidence policies.

An image can be quarantined first and then returned to AVAILABLE if the investigation confirms it is safe. An image that has been REVOKED must not be redistributed simply by renaming it or copying it to another directory.

### Quarantine Procedure

1. Set the lifecycle state to QUARANTINED in the catalog/registry.
2. Block the scheduler and API from distributing that image ID for new restores.
3. Revoke read permissions for workloads that do not need to investigate.
4. Record the digest, signature, metadata, and locations of copies.
5. Keep the artifact in a restricted-access storage area.
6. Identify instances already restored from that image.
7. Decide whether running instances need to be stopped or replaced.

Do not move or rename files being read by the runtime during a restore. Before modifying a storage object, check that no restore operation is currently running or referencing the artifact.

### Revocation Due to Suspected Secret Exposure

If an image may contain exposed credentials:

- Block all new restores from the image.
- Identify the types of credentials that may reside in heap or native memory.
- Rotate or revoke passwords, tokens, certificates, or keys per policy.
- Invalidate sessions or refresh tokens that could be reused.
- Check audit logs for unusual image access.
- Create a new image after the workload obtains valid credentials.
- Keep the old image in an investigation area or delete it per incident response decision.

Deleting the image alone is not enough to handle credentials that have already been copied. If secrets may have been exposed, the secrets must be handled at the issuing system.

### Preserving Evidence

When investigation is needed, save metadata, digests, audit logs, access logs, and a protected copy of the artifact. Limit the number of people with read access to the artifact because the image itself may contain sensitive data.

Do not create additional plaintext copies for debugging convenience. If image analysis is needed, use a controlled forensic environment with full auditing and clear retention.

## 8. Revoking Old or Incompatible Images

An image may become unsuitable after:

- The application changes build or dependencies.
- The JDK vendor, version, or CRaC implementation changes.
- Native libraries or drivers change.
- The kernel, architecture, or container runtime changes.
- Configuration or secret generation is no longer compatible.
- The database schema or data format has evolved.
- Certificates, credentials, or trust policies have rotated.

Do not rely solely on image age. A new image created from a faulty build is still invalid; an old image may still be suitable if all compatibility conditions are verified.

### Compatibility Gate

Before restoring, compare the image manifest against the target environment:

| Component | Must Compare |
|---|---|
| Application build | Build ID and dependency set |
| JDK/CRaC | Vendor, version, build, and implementation |
| OS/kernel | Version and checkpoint/restore support capabilities |
| Architecture | CPU architecture and ABI |
| Native libraries | Version, path, and dependencies |
| Filesystem | Required mounts, paths, and filesystem types |
| Configuration | Accepted generation/version |
| Data schema | Compatibility with database and persisted state |
| Security | Signature, key reference, and current policy |

If a mandatory condition does not match, do not attempt a restore in production just to see if it works. Use an equivalent test environment or switch to cold startup.

## 9. Retention Policy for Checkpoint Images

A retention policy defines which images must be kept, for how long, and under what conditions deletion is permitted.

A policy may classify:

| Image Type | Suggested Policy |
|---|---|
| Current production | Keep the image currently used by the release |
| Last-known-good | Keep at least one or more verified versions for rollback |
| Candidate | Keep during rollout/validation |
| Failed checkpoint | Keep logs and artifacts needed for investigation; delete partial files once confirmed safe |
| Quarantined | Keep in a restricted area per incident policy |
| Revoked | Do not restore; delete after completing investigation and retention |
| Expired | Delete when no longer referenced and retention period has ended |
| Test image | Short TTL, clean up per test run or workspace |

Specific retention durations must be based on RTO, RPO, release frequency, storage cost, audit requirements, and the organization's retention regulations. Do not apply a single TTL for production, test, and forensic artifacts.

### Deliberate Rollback Retention

Before deleting an old image, confirm:

- The new release is stable.
- The replacement image has restored successfully in an equivalent environment.
- No rollout or rollback operation still references the old image.
- No disaster recovery site needs that image.
- Necessary backups or snapshots remain protected.
- Retention and legal holds have been checked.

Keep the policy-defined number of last-known-good versions; do not keep every image indefinitely just because storage is not yet full.

## 10. Safe Space Reclamation

Storage space can be consumed across multiple layers:

- Original checkpoint image.
- Local copies on each node.
- Image staging and temporary files.
- Volume snapshots.
- Backups and object versions.
- Logs, core dumps, and diagnostic bundles.
- Filesystem metadata and inodes.

Before deleting, identify which filesystem is full and which components are consuming space.

### Checking on Linux

~~~bash
df -h
df -i
findmnt
du -xhd1 /var/lib/myapp/checkpoints
du -xhd1 /var/tmp
~~~

Meaning:

- `df -h` displays filesystem capacity.
- `df -i` displays remaining free inodes.
- `findmnt` shows the mount containing a path.
- `du -xhd1` estimates space per directory without crossing into other filesystems.
- Check staging, cache, and artifact store directories separately.

Specific commands may vary by Linux distribution. Run them on the node or container that owns the filesystem under pressure, not only on the management host.

### Checking Deleted Files Still Held Open by Processes

On Linux, an unlinked file whose descriptor is still held by a process continues to consume space until the descriptor is closed:

~~~bash
lsof +L1
~~~

If you see large files with a link count of 0, identify the process holding the file and close/restart it according to operational procedures. Do not kill processes arbitrarily without assessing the impact on workloads.

### Checking on PowerShell

In a Windows environment, you can view volume capacity with:

~~~powershell
Get-Volume
Get-PSDrive -PSProvider FileSystem
~~~

How to check file locks and storage snapshots depends on the OS and storage provider tools. For CRaC deployments on Linux, prioritize checking from the exact Linux node performing checkpoint/restore.

## 11. Safe Image Deletion Procedure

Do not delete using broad wildcards or simply because a file name looks old. Deletion must be based on a verified image ID, digest, and lifecycle state.

Sequence:

1. Select images in the EXPIRED or REVOKED state whose retention has ended.
2. Verify the image has no active restore operations.
3. Verify no deployment, rollback plan, or disaster recovery references remain.
4. Verify there is no legal hold or evidence preservation requirement.
5. Set the state to DELETING to block new consumers.
6. Delete the original object via the storage provider's API.
7. Delete cache and staging copies by image ID.
8. Handle replicas, versions, snapshots, and backups per retention policy.
9. Record audit events and the result of each step.
10. Verify the artifact is no longer distributed by the catalog.
11. Check actual reclaimed space or record the reason it has not been reclaimed.
12. Set the state to DELETED once mandatory steps are complete.

### Idempotency

The cleanup procedure must be safe to rerun. If an object has already been deleted, the next run should recognize that state and continue processing remaining copies.

Do not mark DELETED just because the command to delete the original file returned success. Object versions, snapshots, replicas, or open file descriptors may still remain.

### Do Not Delete Images Currently Being Restored

An image may be currently read by the runtime or distributed to other nodes. Before deleting, reference tracking or operation state is needed to confirm no in-flight restores remain.

If the system does not yet have reference tracking, use a clearly coordinated drain/quiescence period and confirm restore operations have finished before cleanup.

## 12. Reclaiming Space from Snapshots and Object Storage

Deleting a checkpoint image may not immediately reduce physical usage:

- Object storage with versioning retains old versions.
- Volume snapshots may reference shared data blocks.
- Backup retention may keep copies.
- Deduplication or compression causes logical and physical metrics to differ.
- The storage provider has asynchronous garbage collection.

Therefore, distinguish:

- **Logical size:** artifact size displayed in the catalog.
- **Allocated size:** space allocated on the filesystem or volume.
- **Physical usage:** actual backend space used after deduplication/compression.
- **Reclaimable space:** space that can be freed when no references remain.

After cleanup, re-measure using the storage provider's or filesystem's metrics. If logical size decreases but physical usage does not, check versioning, snapshots, and garbage collection before continuing to delete other data.

Do not delete an entire volume snapshot just to reclaim a few images if that snapshot also contains business data or serves as a system rollback point.

## 13. Handling Disk Pressure by Severity

### Capacity Warning

When space begins growing rapidly:

1. Identify the affected filesystem and mount.
2. Find the fastest-growing directories.
3. Check the image creation rate and number of copies.
4. Stop unnecessary experimental checkpoint creation.
5. Identify expired images eligible for cleanup.
6. Check quotas and inodes.
7. Schedule cleanup according to the retention policy.

### Space Nearly Exhausted

When the filesystem is nearly full:

1. Pause new checkpoint creation if there is a risk of filling the filesystem.
2. Keep artifacts needed for rollback and disaster recovery.
3. Delete failed staging files confirmed to be no longer in use.
4. Reclaim unreferenced local image caches.
5. Clean up expired images one ID at a time.
6. Monitor space after each batch.
7. Reopen the checkpoint workflow when sufficient headroom is available.

### Filesystem Full

When the filesystem is full:

1. Preserve last-known-good artifacts.
2. Stop non-essential image creation and copy tasks.
3. Identify temporary files, logs, or expired artifacts.
4. Delete each item verified as eligible.
5. Check inodes and held file descriptors.
6. Confirm the application can write required logs and data.
7. Do not create new checkpoints until sufficient safe space is available.

Do not randomly delete checkpoint directories to free disk space. You may accidentally delete the only image used for rollback or an image referenced by an active restore operation.

## 14. Preventing Restore Loops and Checkpoint Loops

An instance may restore from an image, fail in `afterRestore()`, be restarted by orchestration, and then restore the same image again. This loop both disrupts the service and consumes CPU, I/O, and logs.

Record:

- Image ID and digest.
- Restore attempt number.
- Node and deployment generation.
- Last callback executed.
- Exception class and cause.
- Failed resource.
- Time since the previous attempt.
- Retry or fallback decision.

Apply:

- Retry limits.
- Exponential backoff with jitter.
- Circuit breaker or temporarily paused image distribution state.
- Switching to last-known-good if verified.
- Cold startup when no suitable image exists.
- Alerts when the same image fails repeatedly.

Do not infinitely retry an image with a deterministic error such as a wrong checksum or compatibility mismatch. Mark the image QUARANTINED or REVOKED so the scheduler stops selecting it.

## 15. Revoking Images When Security Risks Are Detected

If there is evidence that an image was tampered with, downloaded without authorization, or contains potentially exposed credentials, handle it according to incident response:

~~~text
       Suspicious image detected
                   |
                   v
    Block new restores from the image
                   |
                   v
Quarantine artifact and preserve evidence
                   |
                   v
Identify affected instances and credentials
                   |
                   v
          Rotate / revoke secrets
                   |
                   v
        Evaluate running instances
                   |
                   v
 Create a new image from a trusted workload
                   |
                   v
   Verify and distribute the new image
                   |
                   v
Delete old artifact per evidence / retention policy
~~~

A valid signature does not prove an image is safe if the signing key or build pipeline has been compromised. You must examine the creation source, access permissions, build provenance, digest, and audit trail.

If the image was modified and the checksum in the manifest was also altered, a checksum alone is not enough. Use signatures verified by an independent trust root and control permissions for updating metadata.

## 16. Service Recovery After Image Revocation

After an image is revoked, ensure workloads no longer depend on that image for the next restart.

Steps:

1. Select a verified replacement image or cold startup.
2. Confirm compatibility with JDK, kernel, native libraries, and configuration.
3. Verify current secrets and credentials.
4. Restore in a small group or canary environment.
5. Wait for resource reopening and readiness to complete.
6. Check requests, error rates, and dependencies.
7. Expand rollout once the canary is stable.
8. Update the catalog so the new image is the artifact permitted for distribution.
9. Keep the old image in the revoked/quarantined state per policy.
10. Verify orchestration no longer selects the old image.

Do not change the image ID of a running deployment without updating the catalog or release metadata. There must be a single source of truth so the scheduler knows which image is permitted for use.

## 17. Monitoring Image Lifecycle and Storage

Monitor both artifact states and storage impact.

### Suggested Metrics

| Metric | Meaning |
|---|---|
| `crac_checkpoint_images_available` | Number of images currently permitted for use |
| `crac_checkpoint_images_quarantined` | Number of images currently quarantined |
| `crac_checkpoint_image_bytes` | Logical size per image or group |
| `crac_checkpoint_create_failures_total` | Total failed checkpoint creations |
| `crac_restore_failures_total` | Total failed restores |
| `crac_restore_retries_total` | Total retries |
| `crac_image_cleanup_total` | Number of artifacts cleaned up |
| `crac_image_cleanup_failures_total` | Total failed cleanups |
| `checkpoint_storage_free_bytes` | Remaining free space |
| `checkpoint_storage_free_inodes` | Remaining free inodes |
| `checkpoint_storage_reclaimable_bytes` | Reclaimable space if supported by the provider |

Metrics per image ID can create high cardinality. Use logs or an inventory catalog for individual IDs; metrics should be grouped by environment, lifecycle state, or storage class.

### Suggested Alerts

- Unusual increase in restore failures.
- The same image fails multiple consecutive times.
- An image stays in the CREATING state for too long.
- A QUARANTINED image is still requested for restore.
- Free space or inodes drop below threshold.
- Cleanup job fails repeatedly.
- Artifacts lack owner or retention metadata.
- Old images are still referenced by deployments.
- Restoring from an image whose digest does not match the catalog.

## 18. Example Runbook for a Corrupted Image

Scenario: a group of instances fails to restore from a new image.

**Detection:** restore failures increase, instances have not reached READY.

**Response:**

1. Pause the rollout and prevent the scheduler from creating more instances from that image.
2. Record the image ID, digest, runtime version, and logs.
3. Set the image to QUARANTINED.
4. Confirm whether instances currently running from the previous image are affected.
5. Select a last-known-good image that has restored successfully in the same environment.
6. If no suitable image exists, switch to cold startup.
7. Check readiness, dependencies, and requests on the canary.
8. Only continue the rollout when restore and request rates are stable.

**Post-Incident:**

- Determine whether the root cause was image corruption, incompatibility, or a dependency.
- Create a new image after the application is running stably.
- Test the new image before marking it AVAILABLE.
- Keep the faulty artifact for the required investigation period, then clean it up.
- Add checks to prevent the same error from recurring.

## 19. Example Runbook for Disk Pressure

Scenario: the filesystem containing checkpoint images reaches the warning threshold.

**Detection:** free bytes or free inodes drop rapidly.

**Response:**

1. Identify the filesystem using `df` and `findmnt`.
2. Identify space-consuming directories using `du`.
3. Pause new checkpoint creation if headroom is insufficient.
4. List images by lifecycle state, age, and references.
5. Keep current production and last-known-good images.
6. Delete failed staging artifacts confirmed to be no longer in use.
7. Delete EXPIRED images whose retention has ended and that have no remaining references.
8. Clean up local caches by image ID.
9. Check object version, snapshot, and backup retention.
10. Re-measure logical and physical usage.
11. Reopen the checkpoint workflow when safe headroom is restored.

Do not delete logs or diagnostic evidence needed for an incident. If logs are the cause of space consumption, apply rotation or move them to separate storage per policy.

## 20. Checklist Before Deleting an Image

Before transitioning an image to DELETING, confirm:

- Image ID and digest have been accurately identified.
- State is EXPIRED or REVOKED.
- No restore operation is currently reading the image.
- No deployment or rollback plan references the image.
- A replacement artifact exists if the workload requires restore.
- Retention period has ended.
- There is no legal hold or forensic hold.
- Required backups to keep have been verified.
- Local, remote, and cache copies have been listed.
- Audit event has been recorded.
- Space can be checked after cleanup.

If any mandatory condition is unclear, keep the image and move to an investigation step. Do not use disk pressure as a reason to bypass reference and retention controls.

## 21. Overall Operational Workflow

### When Creating a Checkpoint

1. Write the manifest and a unique image ID.
2. Create the artifact in the staging area.
3. Wait for the runtime to report checkpoint success.
4. Verify checksum, signature, and compatibility metadata.
5. Run a restore test in an appropriate environment.
6. Transition the state to AVAILABLE.
7. Record the owner, retention deadline, and copy locations.

### When Restoring

1. Select an image in the AVAILABLE state.
2. Check digest, signature, and compatibility gate.
3. Confirm required mounts, secrets, and dependencies.
4. Start restore within retry limits.
5. Monitor runtime and `afterRestore()`.
6. Only place the instance into service when readiness succeeds.
7. Record the restore generation and image reference.

### When an Incident Occurs

1. Stop distribution of the suspected image.
2. Quarantine the artifact and preserve evidence.
3. Identify affected instances, dependencies, and credentials.
4. Recover using a last-known-good image or cold startup.
5. Verify the service before opening traffic.
6. Revoke credentials if exposure is possible.
7. Record the root cause and corrective actions.

### When Reclaiming Space

1. Check filesystem, inodes, and quotas.
2. List expired images and references.
3. Keep current, rollback, and necessary forensic artifacts.
4. Transition candidates to DELETING.
5. Delete the original artifact, caches, replicas, and expired copies.
6. Check snapshot/version retention.
7. Re-measure physical usage.
8. Set to DELETED after confirming completion.

## 22. Key Principles to Remember

- A CRaC checkpoint image differs from a container image and requires a separate lifecycle policy.
- Use image ID, digest, and manifest to manage artifacts; do not rely solely on file names.
- Distinguish between QUARANTINED, REVOKED, and DELETED.
- A checkpoint failure can leave side effects in the original process; modified resources must be recovered.
- A restore failure must not be marked READY or continue receiving traffic.
- Do not infinitely retry the same faulty image.
- Quarantine an image before investigating; preserve evidence if there are signs of compromise.
- If secrets may be exposed, rotate or revoke credentials; deleting the image alone is not enough.
- Keep last-known-good images and check compatibility before rolling back.
- Retention must account for the original artifact, caches, replicas, snapshots, backups, and staging.
- Do not delete an image currently being restored or still referenced.
- Use idempotent cleanup and audit every step.
- Verify actual space after deletion; logical deletion does not always free physical blocks immediately.
- Under disk pressure, clean up verified artifacts one by one instead of using wildcard deletion.
- Monitor restore failures, image states, storage bytes, inodes, and cleanup failures.

Managing checkpoint images is part of production operations. When images have clear identifiers, states, compatibility metadata, and retention, the operations team can quarantine faulty artifacts, recover using trusted images or cold startup, revoke credentials when necessary, and reclaim space while still preserving rollback paths and evidence for investigation.
