# Storage, Transfer, and Cleanup of Unused Images

A CRaC checkpoint image is the state of a Java process at the time of the checkpoint. In production environments, this image needs to be stored in a durable location, transferred to the right restore environment, and managed throughout its lifecycle as a deployment artifact. Missing files when copying, losing access permissions, changing filesystem metadata, or restoring in an incompatible environment can all render an image unusable.

A checkpoint image can also contain sensitive data in the heap such as access tokens, passwords, user information, cache data, and session state. Therefore, the storage process must protect integrity, compatibility, security, and traceability. The cleanup process must determine which images are still referenced by a deployment and which images are currently being restored before deleting them.

## 1. A Checkpoint Image Is an Environment-Bound Artifact

When launching a JVM with `-XX:CRaCCheckpointTo=<path>` and requesting a checkpoint, the runtime creates checkpoint data at the configured path. The internal structure is managed by the JDK/CRaC and the underlying checkpoint layer. Individual internal files should not be treated as application files to be manually edited, renamed, or deleted separately.

A checkpoint image differs from common artifacts:

| Artifact | Contents | Purpose |
| --- | --- | --- |
| Application JAR | Bytecode, resources, and packaging metadata | Runs the application on a compatible JVM. |
| Container image | Root filesystem, runtime, and image configuration | Creates the container environment. |
| CRaC checkpoint image | Process state saved by the runtime/platform | Resumes the process from the checkpointed state. |
| Database backup | Database data and metadata per the backup mechanism | Recovers persistent data. |
| WAL/transaction log archive | Database change logs | Recovery/PITR according to database capabilities. |

A CRaC checkpoint does not replace a JAR, container image, database backup, or transaction log. A deployment workflow may need to store all of these artifacts and link them via shared metadata.

A checkpoint image is typically tied to the environment that created it. Restore capability depends on the JDK/CRaC build, CRIU or platform mechanism, kernel, CPU architecture, namespaces, filesystem, mounts, native libraries, and process resources. It must not be assumed that an image can simply be copied to any machine and restored successfully.

## 2. Checkpoint Artifact Lifecycle

A storage lifecycle can be divided into stages:

```text
Launch application and prepare Resources
                 |
                 v
         Create checkpoint
                 |
                 v
   Confirm checkpoint completed
                 |
                 v
    Package / generate metadata
                 |
                 v
   Compute checksum and verify
                 |
                 v
   Upload to temporary staging area
                 |
                 v
Verify artifact transferred completely
                 |
                 v
Publish immutable/completed artifact
                 |
                 v
   Restore and test in practice
                 |
                 v
  Retain / mark obsolete / cleanup
```

Each step has its own outcome. Creating the directory does not mean the checkpoint is complete; uploading the archive file does not mean the artifact is published; a valid checksum does not prove the image is compatible with the restore host; and a successful restore does not yet prove the application has reached readiness.

State should be stored per attempt, for example `CREATING`, `CREATED`, `PACKAGING`, `UPLOADING`, `PUBLISHED`, `RESTORE_VERIFIED`, `OBSOLETE`, and `DELETED`. These are pipeline management labels, not mandatory states in the CRaC API.

## 3. Package Only After the Checkpoint Completes

Do not copy or compress the checkpoint directory while the JVM/CRIU is still writing the image. If copied mid-way, the artifact may miss image pages, metadata, or required files. The result might have all the filenames present but incomplete contents.

Before packaging:

1. Confirm that the checkpoint command has finished according to the semantics of the runtime in use.
2. Check JVM and CRIU/platform logs to confirm the checkpoint was acknowledged as successful.
3. Confirm that the original process has transitioned to the expected state of the checkpoint workflow; the process exiting may be normal behavior.
4. Ensure no writers are still modifying the image directory.
5. Record the creation timestamp and checkpoint attempt id.

Do not rely on the existence of the directory or a single file as the sole signal. If the checkpoint fails, the destination directory may still contain partial data. Mark the attempt as failed and handle the directory via a separate cleanup process; do not publish that data.

A manageable way to organize directories is to use a separate directory for each attempt:

```text
/var/lib/myapp/crac/
├── staging/
│   ├── attempt-20261113T090000Z/
│   └── attempt-20261113T093000Z/
└── published/
    ├── release-2026.11.13-001/
    └── release-2026.11.13-002/
```

Do not reuse the same destination directory for multiple concurrent checkpoint attempts. A failed attempt must not mix files with a previously published image.

## 4. Preserve Filesystem Structure and Metadata

A checkpoint image can contain many files and subdirectories created by the runtime. Depending on the platform and dump tool, filesystem attributes can matter at restore time:

- Relative paths and directory structure.
- Exact file contents and sizes.
- Read/write/execute permissions.
- Owner and group id.
- Symbolic links, hard links, and file types.
- Extended attributes (xattrs), ACLs, and security metadata if used.
- Sparse file layout and related filesystem characteristics.

When packaging, use tools and options capable of preserving the attributes required by the CRaC/CRIU environment. Do not use workflows that only copy text or only copy files with familiar extensions. Do not skip hidden files or metadata files.

For example, with GNU tar on Linux, you can create an archive that preserves multiple types of metadata:

```bash
tar --xattrs --acls --numeric-owner --sparse \
    -cpf checkpoint.tar \
    -C /var/lib/myapp/crac/staging \
    attempt-20261113T090000Z
```

When extracting in the destination environment:

```bash
mkdir -p /var/lib/myapp/crac/restore-staging

tar --same-owner --same-permissions --xattrs --acls \
    -xpf checkpoint.tar \
    -C /var/lib/myapp/crac/restore-staging
```

The options above are examples for GNU tar; the ability to preserve owner, ACLs, xattrs, sparse files, and security labels depends on the OS, filesystem, tool version, and privileges of the user running the command. Administrative privileges may be required to restore ownership or security metadata. Check the documentation of the deployment platform and test restoring from the extracted archive.

If using `rsync`, choose options that preserve required attributes for the environment, such as archive mode along with hard links, ACLs, xattrs, sparse, and numeric id where appropriate. Do not add destination-deletion options during the initial copy if there is no source/destination verification workflow; a misconfigured sync command with `--delete` can erase retained artifacts.

Do not edit the contents of files inside the image to reduce size or remove a few components. If the runtime provides an official packaging format or tool, prefer the method supported by that runtime's documentation.

## 5. Compression and Archive Formats

Checkpoints can be large because they contain heap state and process memory pages. Compression reduces transfer and storage size, but also increases CPU usage and packaging/extraction time.

When choosing a format:

- Preserve the entire directory tree and required metadata.
- Support large files, sparse files, and the expected archive size.
- Be able to verify integrity after transfer.
- Be extractable in the designated restore environment.
- Record the tool version and compression options in the artifact metadata.

Do not optimize compression ratio by altering image contents. Choose the compression level based on RTO, CPU, network bandwidth, and storage cost. For environments requiring fast restore, an extracted copy may be kept on storage close to the host to avoid extraction on the critical startup path.

The archive should contain the checkpoint directory at the exact relative level expected by the restore workflow. When extracting, avoid creating an extra unintended directory level that causes `-XX:CRaCRestoreFrom` to point to the wrong location.

## 6. Generating Checksums and Verifying Integrity

After packaging completes, compute a checksum for the archive or manifest file. SHA-256 is a common choice to detect corrupted files or unintended modifications:

```bash
sha256sum checkpoint.tar > checkpoint.tar.sha256

# On the receiving machine, after downloading:
sha256sum --check checkpoint.tar.sha256
```

If storing the checkpoint as an unpackaged directory, generate a checksum manifest for the files in a deterministic order, including relative paths and sizes. Do not only hash filenames or total size.

A checksum answers the question "does the received data match the hashed data?". It does not confirm:

- That the checkpoint was created successfully.
- That the files have complete filesystem metadata.
- That the artifact is compatible with the restore host.
- That the artifact contains no malicious code or was not created by an untrusted source.
- That the application will reach readiness after restore.

If source authenticity verification is needed, the manifest or checksum can be signed using the organization's artifact signing mechanism. Store signatures and key ids separately; do not place the private signing key inside the checkpoint image or with the same access permissions as the archive.

## 7. Metadata to Store Alongside the Checkpoint

Do not infer the image-creation environment solely from the directory name. Store a separate manifest alongside the artifact so operators know which image can be used where. The manifest is pipeline management metadata, not an internal CRIU file, and should not be inserted inside the image structure unless required by the runtime.

Useful fields:

| Category | Metadata to store |
| --- | --- |
| Identity | Artifact id, checkpoint attempt id, service/module name, release id. |
| Application | Build version, Git commit, JAR checksum, configuration profile without secrets. |
| Java runtime | JDK vendor, version/build, relevant JVM flags, CRaC support/version. |
| Platform | OS/distribution, kernel version, architecture, CPU feature baseline. |
| Checkpoint stack | CRIU version/capabilities or platform mechanism, container runtime version if applicable. |
| Filesystem | Filesystem type, mount layout, required paths, UID/GID, and metadata requirements. |
| Dependencies | Versions of native libraries, agents, drivers, and critical runtime dependencies. |
| Timing | Created at, checkpoint completed at, warm-up profile if any, artifact expiration time. |
| Integrity | Archive format, compression, size, SHA-256, signature/key id. |
| Storage | URI/path, storage class, encryption key id, retention class. |
| Verification | Host/environment where restore was tested, restore result, readiness result, and test timestamp. |

Example illustrative JSON manifest:

```json
{
  "artifactId": "myapp-release-2026.11.13-001",
  "checkpointAttemptId": "attempt-20261113T090000Z",
  "application": {
    "version": "2026.11.13",
    "gitCommit": "<commit-id>",
    "jarSha256": "<sha256>"
  },
  "runtime": {
    "jdkVendor": "<vendor>",
    "jdkVersion": "<version-and-build>",
    "cracVersion": "<version>",
    "criuVersion": "<version>"
  },
  "platform": {
    "os": "<distribution>",
    "kernel": "<kernel-version>",
    "architecture": "<architecture>",
    "cpuFeatures": "<required-feature-baseline>"
  },
  "archive": {
    "format": "tar",
    "compression": "<compression>",
    "sizeBytes": 0,
    "sha256": "<sha256>"
  },
  "createdAt": "2026-11-13T09:00:00Z",
  "restoreVerified": false
}
```

Values in angle brackets are placeholders. Do not include passwords, tokens, private keys, environment secret contents, or user data in the manifest. Store only enough metadata to determine compatibility and trace the artifact.

## 8. Checking Compatibility Before Transfer

A checkpoint image is not a portable container image. Before transferring to another host, compare at a minimum:

- JDK vendor, version, build, and CRaC implementation.
- CRIU version or underlying checkpoint mechanism.
- CPU architecture and instruction sets required by native/JIT code.
- Kernel and required features.
- Container runtime, namespaces, cgroups, and security capabilities.
- Mount points, filesystems, absolute paths, and access permissions.
- Shared libraries, native agents, drivers, and file mappings.
- External resources such as sockets, databases, DNS, secrets, and service endpoints.

Even if two machines share the `x86_64` architecture, they can still differ in CPU features, kernel, or namespaces. Do not use a generic OS name as proof of compatibility.

Some resources need to be recreated via CRaC callbacks after restore, such as connection pools, sockets, or clients connecting to external services. Being able to restore an artifact does not mean all external resources are ready; callbacks and readiness must be verified after restore.

If transferring checkpoints across hosts is needed, define a supported compatibility profile in advance and test on the exact target host type. If the destination environment differs significantly, the safe option may be to launch a fresh application instance and create a new checkpoint in the destination environment rather than trying to restore an old image.

## 9. Storing on Volumes, Filesystems, and Object Storage

### Local Persistent Volume

Storing images on a persistent volume can enable fast restore on the same host or within the same storage environment. Ensure the volume persists across the container/process lifecycle and has sufficient capacity. Do not leave checkpoints solely inside a container's ephemeral writable layer if the container might be deleted.

### Shared Filesystem

A shared filesystem is convenient for multi-host access, but you must confirm it supports the characteristics the checkpoint requires: permissions, ownership, locking, xattrs, ACLs, hard links, sparse files, file size, and rename semantics. Not every network filesystem is suitable for every CRIU mechanism.

### Object Storage

Object storage typically lacks full filesystem semantics. Usually the checkpoint must be packaged into an archive and uploaded as an immutable object. Do not assume object stores support atomic rename; many systems perform copy/delete or use a new object key.

A safe way to publish to object storage:

1. Upload the archive to a separate staging key, e.g., `staging/<attempt-id>/checkpoint.tar`.
2. Upload the checksum and manifest to staging.
3. Read back metadata/size and verify the checksum by downloading or using storage-supported checksums with appropriate semantics.
4. Copy/promote to an immutable versioned key in `published/` or mark the artifact with a completion manifest/marker written last.
5. Only update the deployment pointer after the entire artifact has been verified.

Do not overwrite a key currently being read by restore hosts. Use a new key/version for each checkpoint attempt and update a separate pointer using a mechanism with concurrency control.

## 10. Secure Transfer Between Environments

When transferring images over the network:

- Use an encrypted and authenticated transport, such as a TLS or SSH channel approved by the organization.
- Authenticate source and destination identities; restrict upload/download permissions by service identity.
- Check available free space before downloading.
- Download to a separate staging path; do not write directly over a directory currently being restored.
- Verify the checksum/signature before extracting or restoring.
- Extract to a new directory and preserve the required structure/metadata.
- Only publish the final path after verification completes.
- Log the artifact id, source, destination, bytes transferred, checksum, and result.

Do not send images over chat channels, personal email, or public file-sharing services. Checkpoints may contain credentials and sensitive data in memory. Do not place URLs containing access tokens into logs or public manifests.

For large files, multipart/resumable uploads can be used if supported by storage, but only consider the upload complete after all parts are finalized and the final checksum is verified. The ETag of a multipart object is not always the MD5/SHA-256 of the entire content; use the checksum semantics published by the provider.

## 11. Publishing Artifacts to Avoid Reading Incomplete Files

On filesystems that support atomic rename within the same filesystem, you can prepare the artifact in a staging directory and then rename it to the published name after completion:

```bash
STAGING=/var/lib/myapp/crac/staging/attempt-20261113T090000Z
PUBLISHED=/var/lib/myapp/crac/published/release-2026.11.13-001

# After archive/checksum/manifest are completed and verified:
mv "$STAGING" "$PUBLISHED"
```

Rename can only be considered atomic under appropriate filesystem and operation conditions, usually on the same filesystem. If the two paths reside on different filesystems, `mv` may become a copy followed by a delete. In that case, do not rely on rename as proof of atomic publish; copy to staging at the destination, verify, and then update a completion manifest/pointer.

For object storage, use an immutable key/version and write a completion marker or final reference manifest after uploading everything. Consumers must only read artifacts with a `PUBLISHED` status marker and a verified checksum.

Do not update the deployment pointer before the final artifact is ready. If the pointer points to an incomplete archive, a new restore might read a partial file.

## 12. Workflow for Restoring from a Stored Artifact

Before running `-XX:CRaCRestoreFrom`, perform these steps:

1. Select a specific artifact id from the manifest/deployment record; do not use wildcards or an uncontrolled "latest".
2. Verify the artifact status is `PUBLISHED` and has not been marked obsolete/deleted.
3. Verify the checksum and signature if present.
4. Check compatibility metadata against the destination host.
5. Extract to the exact path, preserving required metadata.
6. Check the permissions of the user running the JVM and dependent mounts/paths.
7. Ensure no other process is writing to or cleaning up this directory.
8. Restore according to the command and documentation of the JDK/CRaC in use.
9. Confirm `afterRestore` callbacks, resource connections, and readiness.
10. Record the host/runtime that restored successfully for traceability.

Example restore command:

```bash
java -XX:CRaCRestoreFrom=/var/lib/myapp/crac/restore-staging/attempt-20261113T090000Z
```

The path must point to the checkpoint directory expected by the runtime after extraction, not the archive file or a parent directory containing multiple checkpoints. The exact structure depends on the packaging method and JDK/CRaC distribution.

If restore fails, keep the artifact and logs for investigation according to the retention policy. Do not delete the image immediately after one failed restore; the failure might be due to an incompatible destination host rather than a corrupted artifact.

## 13. Retention Policy

Retention determines which images are kept and for how long. Do not rely solely on file age because an older image may currently be used for deployment rollback, while a newer image may never have been restored successfully.

A policy can combine:

- Retaining the checkpoint currently referenced by the active deployment.
- Retaining a number of the most recent checkpoints that restored successfully.
- Retaining the checkpoint of the previous release within a defined rollback window.
- Retaining unverified images until a clear operational decision is made.
- Deleting failed staging images after an investigation/grace period.
- Applying maximum age limits and capacity quotas.
- Retaining images under legal hold or incident investigation if required.

Illustrative example policy:

| Artifact type | Example policy |
| --- | --- |
| Current deployment | Retain until replaced by another deployment and no restore is still referencing it. |
| Verified checkpoints of recent releases | Retain the 3 most recent versions or 14 days, whichever is longer. |
| Unverified checkpoints | Retain up to 48 hours while awaiting restore test or discard decision. |
| Failed attempts / incomplete staging | Mark failed, keep logs, and clean up after a 24-hour grace period if there is no incident hold. |
| Artifacts marked obsolete | Delete after the rollback window expires and no active consumer/restore lease exists. |

These numbers are only examples, not defaults for every system. Choose them based on RTO, rollback capability, storage cost, image size, security requirements, and incident investigation time.

## 14. Safely Cleaning Up Unused Images

Cleanup is a destructive operation. Criteria are needed to verify that the artifact is no longer referenced, has no restore in progress, and has passed the retention/grace period.

A two-phase workflow is usually safer:

**Phase 1 — Mark obsolete**

- Mark the artifact as `OBSOLETE` in the metadata registry.
- Confirm the deployment pointer no longer points to the artifact.
- Confirm no restore job or host lease is using the artifact.
- Start the grace period for rollback or incident handling.

**Phase 2 — Delete**

- Re-read status and references immediately before deletion.
- Confirm the artifact id and absolute path match the registry.
- Delete the archive, manifest, checksum, and related staging data in a controlled management operation.
- Record an audit event including who/which automation deleted it, timestamp, artifact id, and result.
- Update the registry to `DELETED` after confirming storage deleted it according to its semantics.

Do not delete merely because the directory name contains an old date. Do not delete a directory being used by a deployment rollback, a restore job, or another host. Do not delete sub-files inside a checkpoint to "free up some space"; the image will no longer be reliable.

### Dry-Run Before Deleting

On Linux filesystems, you can list old staging directories for operators to preview:

```bash
find /var/lib/myapp/crac/staging \
  -mindepth 1 -maxdepth 1 -type d \
  -name 'attempt-*' -mtime +2 -print
```

This is only a list by file age; it has not checked deployment references or restore leases. Only after the registry confirms retention conditions should automation delete the exact selected artifact id. Avoid constructing paths from untrusted input or using broad wildcards with `rm -rf`.

With object storage, delete specific versions or specific object keys. Check versioning, soft delete, replication, and lifecycle rules because a delete operation might create a delete marker rather than physically deleting immediately. If there is a legal hold or object lock, cleanup must comply with that policy.

## 15. Avoiding Races Between Cleanup and Restore

A dangerous operational error occurs when cleanup sees an "old" artifact and deletes it just as a restore begins downloading or reading that artifact.

This can be avoided by managing references/leases:

1. The restore job requests to use the artifact id.
2. The registry issues a time-bounded lease or increments a reference count for the artifact.
3. Cleanup only selects artifacts with no leases/references and expired retention.
4. When the restore completes or fails, release the lease.
5. Expired leases must be reconciled against job status before cleanup proceeds.

If multiple workers/hosts operate concurrently, locking or atomic conditional updates are needed in the registry. Do not rely on checking a file and then deleting it after a delay because the state can change between the two steps.

With object storage, versioning helps retain specific versions but does not replace leases. Deployment records should point to an immutable object version, not merely to a key that can be overwritten.

## 16. Cleaning Up Staging and Failed Checkpoints

A failed checkpoint can leave behind an incomplete directory. Do not publish these directories and do not reuse them as the destination for a new checkpoint attempt.

Handling workflow:

1. Record the checkpoint attempt id and runtime/CRIU error.
2. Mark the attempt as `FAILED` or `INCOMPLETE`.
3. Retain logs and necessary data for the grace period for investigation.
4. Confirm no JVM/CRIU process is still writing to the directory.
5. Confirm no restore job is referencing it.
6. Delete the entire staging directory by artifact id.
7. Record the cleanup result and reclaim quota.

If it cannot be determined whether a writer is still active, do not delete. First confirm the state of the processes and runtime. Cleanup must not run concurrently with an ongoing checkpoint operation.

## 17. Capacity, Quotas, and Storage Costs

Checkpoints can be large and their count grows quickly when each release/host creates its own image. Plan for:

- Heap and native memory size at the time of checkpoint.
- Number of concurrently retained checkpoints.
- Temporary archive size during compression.
- Staging capacity on the destination host during download and extraction.
- Backup copies, object versioning, and replication storage.
- Free space needed for new checkpoints before old images are cleaned up.

A rough estimate:

```text
Storage budget
  = number of retained checkpoints × average size per image
  + staging/temporary copy
  + concurrent archive and extracted copy
  + versioning/replication overhead
  + safety margin
```

Do not use heap size `-Xmx` as an accurate estimate for checkpoint size. An image can contain native memory, pages, metadata, and other state regions; compression ratios also vary by data.

Monitor free space, upload/download speeds, compression/extraction duration, and artifact counts by status. When quotas approach capacity, prioritize cleaning up failed staging beyond its grace period and obsolete artifacts with no references; do not delete images serving rollback just to immediately free space.

## 18. Securing Checkpoint Images

A checkpoint image can contain process memory contents. Assume it has sensitivity equal to or higher than application logs and may contain:

- Passwords, tokens, API keys, and database credentials.
- Session cookies, access tokens, and private data.
- Personal data currently being processed.
- Request/response bodies or cache data.
- Private keys or TLS material if held in memory by the application.

Protection measures:

- Encrypt data at rest and in transit.
- Manage encryption keys separately from checkpoint storage; restrict decrypt permissions.
- Use dedicated service identities for upload/download and the principle of least privilege.
- Enable audit logging for read, copy, restore, and delete.
- Restrict who has direct access to hosts/storage containing images.
- Do not put images into source control, public artifacts, or unapproved tickets/chats.
- Apply the shortest retention that satisfies rollback/operational requirements.
- Handle staging copies, temporary archives, and download caches under the same security policy.

Deleting an object does not necessarily mean data has been physically overwritten immediately, especially on SSDs, snapshots, or object storage with versioning/replication. If secure deletion is required, use crypto-erasure/key revocation mechanisms or workflows supported and verified by the storage provider.

## 19. Common Errors

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Restore reports missing file/image | Copied before checkpoint completed or archive skipped files | Verify checkpoint completion, manifest file list, and repackage from a valid image. |
| Restore cannot access file | Lost owner, permissions, ACL, or xattr during copy/extract | Use metadata-preserving tools and restore with appropriate permissions. |
| Archive checksum valid but restore fails | Artifact intact but environment incompatible or image inherently invalid | Check JDK/CRaC, CRIU, kernel, CPU, mounts, and restore logs. |
| Restore path cannot find image | Extracted with an extra directory level or pointer points to wrong archive | Check post-extract structure and point `CRaCRestoreFrom` to the exact checkpoint directory. |
| Object storage has archive but pipeline says unpublished | File upload finished but completion manifest/marker not written | Only treat artifact as published after finalize step and checksum verification. |
| Checkpoint being restored gets deleted | Cleanup only checks file age, not leases/references | Use registry, leases, and conditional deletes. |
| Storage grows uncontrollably | Retaining every attempt, failed staging, and multiple object versions | Apply retention, quotas, lifecycle policies, and audited cleanup. |
| Unable to delete old objects | Object lock, legal hold, retention, or versioning | Check storage policy; do not bypass holds outside procedure. |
| Sensitive data exposed via checkpoint | Image stored/shared like an ordinary artifact | Encrypt, restrict permissions, audit, and manage keys separately. |

## 20. Sample Operational Workflow

A packaging and publishing pipeline can be implemented in this sequence:

```text
1. Start JVM with CRaCCheckpointTo=staging/<attempt-id>
2. Wait for application warm-up and resource preparation
3. Request JDK.checkpoint
4. Confirm checkpoint operation completed successfully
5. Confirm no process is writing the checkpoint directory
6. Create archive while preserving required filesystem metadata
7. Generate SHA-256 and external manifest
8. Upload archive + manifest to staging storage
9. Verify remote size/checksum/signature
10. Publish immutable artifact id / completion marker
11. Record artifact metadata and compatibility profile
12. Restore-test on a compatible target environment
13. Mark restore result and update deployment reference
14. Mark old artifacts obsolete after rollback window
15. Cleanup only unreferenced artifacts after grace period
```

Each step should be idempotent by `attempt-id`. If the pipeline retries an upload, do not create two different artifacts for the same attempt unless intentional. If the checksum differs between retries, mark the attempt anomalous and investigate rather than overwriting an already published object.

## 21. Implementation Checklist

- [ ] Each checkpoint attempt uses a separate directory.
- [ ] Only copy/compress after the runtime confirms checkpoint completion and no writers remain.
- [ ] Do not edit or delete individual files inside the checkpoint image.
- [ ] Archive preserves the directory layout and required filesystem metadata.
- [ ] Verified archive/extract tools support ACLs, xattrs, owner, hard links, and sparse files when needed.
- [ ] Manifest records build, JDK/CRaC, CRIU, kernel, CPU, filesystem, and compatibility metadata.
- [ ] Manifest contains no secrets or unnecessary sensitive data.
- [ ] Checksum exists and is verified after transfer; signature exists if provenance is required.
- [ ] Upload to staging first, publish only after full verification.
- [ ] Use immutable artifact id/version; do not overwrite an image in use.
- [ ] Storage has encryption, access control, and auditing.
- [ ] Restore uses only published artifacts compatible with the destination host.
- [ ] Restore-tested in the target environment.
- [ ] Retention accounts for active deployment, rollback window, restore leases, and incident holds.
- [ ] Cleanup includes dry-run, mark-obsolete, grace period, and reference check right before delete.
- [ ] Do not run cleanup concurrently with active checkpoint, upload, or restore.
- [ ] Monitor quotas, staging space, transfer duration, and artifact counts by status.
- [ ] Workflow exists to handle incomplete checkpoints and failed uploads.

## 22. Conclusion

A CRaC image must be managed as a deployment artifact bound to the environment that created it. Package only after checkpoint completion, preserve the full structure and required metadata, generate checksums/manifests, transfer over a secure channel, and publish using immutable identifiers. Before restoring, verify integrity, compatibility, permissions, and paths; after restoring, verify callbacks and readiness.

Cleanup must be based on reference status and retention, not solely on file age. Use a mark-obsolete then delete workflow after a grace period, check restore leases to avoid deleting images in use, and protect checkpoints as sensitive data since the heap may contain credentials or user data. Managing artifacts with clear metadata, integrity checks, and lifecycle rules ensures checkpoints can be traced, transferred, and cleaned up safely.
