# Checkpoint File Set Structure and Completeness Preservation Requirements

A CRaC checkpoint is a snapshot of the state of a running JVM process. When using a CRIU-based engine, the output is typically a directory containing multiple process image files, memory data, thread information, file descriptors, and OS resources. These files work together to restore the same process state; they are not independent parts that can be arbitrarily picked, renamed, or copied individually.

Therefore, **checkpoint completeness is the integrity of the entire file set and the environment that the file set depends on**. Missing just a single memory image, having an incorrect path, losing access permissions, modifying a referenced file, or mixing data from two separate dumps can cause restore to fail or recover the process in an incorrect state.

This article presents the common structure of a CRIU checkpoint, how to distinguish the image directory from a deployment bundle, how to package and verify integrity, and the requirements that must be maintained when transferring a checkpoint to another environment.

## 1. A CRaC Checkpoint Is a Linked Dataset

When an application runs on a CRaC-enabled JDK, the JVM is started with the target path for the checkpoint:

~~~bash
java -XX:CRaCCheckpointTo=/var/lib/myapp/checkpoints/current \
     -jar app.jar
~~~

After the application has initialized, warmed up, and prepared resources, a checkpoint can be requested using the command:

~~~bash
jcmd <PID> JDK.checkpoint
~~~

With a Linux image-saving engine, CRIU collects the process state and writes out a set of image files. The `-XX:CRaCCheckpointTo` path is the directory containing the checkpoint images. The exact layout depends on the JDK build, checkpoint engine, CRIU version, kernel, and the resources the process is currently using.

Restore uses the image path:

~~~bash
java -XX:CRaCRestoreFrom=/var/lib/myapp/checkpoints/current
~~~

The restore command recovers the process from the image. This is not an operation that re-runs `app.jar` following the normal startup flow. The JVM and application state are recovered from the checkpoint, after which CRaC invokes the `afterRestore` callbacks so the application can reconnect required resources.

### 1.1. The CRaC API and the Checkpoint Engine Are Two Different Layers

The CRaC API notifies the application about the pre-checkpoint and post-restore phases. The actual image creation mechanism is selected by the runtime.

On OpenJDK CRaC, the Linux engine typically uses CRIU. Some runtimes or vendors may provide a different engine. For example, a simulation engine can test the callback cycle without creating a set of image files on disk. Therefore, not every CRaC run generates a directory with the exact same structure.

When this document refers to files such as `inventory.img`, `core-*.img`, `pagemap-*.img`, and `pages-*.img`, those are common file groups in a checkpoint using CRIU. Do not treat the file names or file counts in the examples as a fixed standard for all engines and versions.

### 1.2. The Image Directory Is Not Synonymous with a Complete Deployment Bundle

Two concepts must be distinguished:

- **Checkpoint image directory**: the directory created by the engine, containing the data needed to restore the process according to the engine's format.
- **Deployment bundle**: the package that the pipeline releases and deploys, typically consisting of the intact checkpoint directory, a compatibility manifest, checksums, references to the application artifact/JDK image, and instructions regarding mounts or runtime configuration.

A JAR is not a CRIU image file. Nor does a deployment manifest replace the process image. Conversely, having only the checkpoint directory may not be enough to deploy on another host, because the process may depend on the JDK, native libraries, mounted files, network namespaces, and OS conditions.

## 2. Common File Groups in a CRIU Checkpoint

CRIU splits process state into multiple image files. Some files contain structured metadata, while others contain page-structured memory data or raw data. The groups below help clarify the role of the file set; exact names and the presence of each group vary per checkpoint.

### 2.1. Inventory and Overall Information

`inventory.img` is the image describing the dump's image set. It contains overview information that CRIU uses to identify the image set.

You can think of the inventory as the table of contents for the checkpoint set. It does not replace the memory, thread, or file descriptor files that the process needs to recover.

Other metadata may describe the process tree, task/thread relationships, and general attributes of the dump. File names and organization depend on the CRIU version.

### 2.2. Process and Thread State

CRIU needs to restore each process/task along with its execution state. In the image set, you may encounter groups such as:

- `core-<pid>.img`: core state of the process/task, including register information and necessary execution state.
- `pstree.img`: process tree relationships in layouts that use this file.
- Thread/task-related images: thread information, signals, states, and relationships between tasks.
- Memory-map-related images: describing the process's virtual address regions and memory mappings.

Do not assume a Java process needs only a single core file. A JVM has many threads, and the checkpoint must preserve the state of all relevant threads.

### 2.3. Memory Maps, Pagemap, and Pages

This is an important data group for restoring the heap, stacks, code, and other memory regions.

| Group | General Role |
|---|---|
| `mm-*.img` or equivalent metadata | Describes memory maps and process address regions |
| `pagemap-*.img` | Describes saved memory pages and how to map them into address regions |
| `pages-*.img` | Contains the contents of dumped memory pages |
| Images related to VMA/file mappings | Describes file mappings, access permissions, and memory region attributes |

`pagemap` and `pages` are interdependent. One metadata group indicates which page data needs to be placed at which location; the other group holds the page contents. Missing any of these required components can prevent memory from being reconstructed properly.

Do not delete `pages` files on your own just because they are large, or assume they can be regenerated from the JAR. They may contain heap state, stacks, class metadata, code, and runtime data at the time of checkpoint.

### 2.4. File Descriptors and Open Files

A process may hold file descriptors to files, pipes, sockets, or other OS resources. CRIU needs information to recreate or re-link these descriptors.

Some common groups:

- `fdinfo-*.img`: file descriptor information.
- `files.img` or corresponding metadata images: describing relationships between descriptors and resources.
- `reg-files.img`: information about regular files opened via system calls.
- `ext-files.img`: information about files handled through an external mechanism/plugin.
- Dedicated images for pipes, eventfd, eventpoll, inotify, and other descriptor types.

Not every descriptor can be preserved as-is. This is why CRaC Resource callbacks require the application to close or re-prepare resources such as sockets, connections, file handles, and client sessions before checkpoint.

If an open file still needs to exist upon restore, the file path and contents must satisfy the engine's requirements. An image may record the referenced file rather than packaging the entire file contents into the checkpoint set.

### 2.5. Namespaces, Networking, and IPC

A process/container may depend on Linux namespaces, network interfaces, routes, sockets, pipes, shared memory, or other IPC mechanisms. CRIU can create images for these resources.

Examples of data groups that may appear:

- Namespaces and mount information.
- Network interfaces and routes.
- Sockets and associated state.
- Pipes and pipe data.
- Shared memory and semaphores.
- Eventfd, eventpoll, and inotify.
- Filesystem or required mount information.

The presence of these files depends on actual resources. An application that does not use pipes or a certain type of IPC may not have the corresponding images. Do not use the file list of another checkpoint as a mandatory requirement for all checkpoints.

### 2.6. Raw Images, Auxiliary Files, and Logs

Not all files share the same format. CRIU has images in protobuf format, images containing binary payloads, and raw files generated by other tools or plugins.

Besides images used for restore, the directory may contain auxiliary data, statistics, or logs. Log names and generation behavior depend on the engine/runtime. For instance, some environments may write dump logs into the image directory; do not assume every runtime generates the same log names.

Logs help investigate failed checkpoints, but do not replace the required images. Conversely, having a log does not mean the checkpoint completed successfully.

## 3. Directory Structure Illustration

A CRIU directory might look similar to the following example:

~~~text
crac-checkpoint/
├── inventory.img
├── pstree.img
├── core-1234.img
├── mm-1234.img
├── pagemap-1234.img
├── pages-1.img
├── fdinfo-1234.img
├── reg-files.img
├── files.img
├── pipes.img
├── pipes-data.img
├── ids-1234.img
├── stats-dump
├── dump.log
└── ...
~~~

This is only an illustrative diagram. An actual dump may have more files, fewer files, or use different names. The PID in the file names is an example; it is not a fixed value.

Do not use the list above to manually fabricate a dummy directory, rename files, or remove files that do not appear in the diagram. The actual structure is created by the CRaC runtime and checkpoint engine.

### 3.1. Why Can't You Just Keep `inventory.img`?

The inventory describes the image set, but it does not contain all the state needed to restore. If you keep only the inventory and discard `pages`, `core`, file descriptors, or other images, CRIU cannot recreate the process.

Similarly, keeping only `pages` files while discarding mapping metadata is not enough to know which address regions the data needs to be placed into. Completeness is the relationship among the files, not the presence of a single specific file.

### 3.2. Do Not Use File Count as the Sole Criterion

Two checkpoints of the same application can have different file counts because:

- The number of threads or child processes differs.
- The workload produces different memory maps.
- File descriptors and IPC resources differ.
- The CRIU/JDK version or engine differs.
- The kernel features used differ.
- Page data is split into files differently.

Therefore, a checkpoint with fewer files is not automatically incomplete; a checkpoint with more files is not automatically complete either. You must verify the actual output of the dump, checksums, and restorability.

## 4. What Needs to Be Preserved When Packaging

### 4.1. Keep the Entire Image Directory Intact

When packaging, copying, or archiving, preserve the entire checkpoint directory tree generated by the engine:

- All image files.
- Subdirectories, if any.
- File names and relative paths.
- Log/metadata files generated by the runtime.
- Hidden files, if any.
- Symlinks, hard links, and file attributes if used by the format/engine.

Do not pick out only files with the `.img` extension. There are files supporting restore that do not carry that extension, and there are `.img` files that are only one part of the image set.

### 4.2. Preserve File Contents and Sizes

Each file must be kept byte-for-byte intact. Do not open and re-save with a text editor, modify headers, concatenate two files with the same name, or truncate large files to save space.

Operations that can corrupt the image set:

- Copying only small files and skipping large `pages` files.
- Copying while CRIU is still writing the checkpoint.
- Overwriting some files from an old checkpoint.
- Concatenating files from two different dumps.
- Renaming files according to self-invented conventions.
- Transferring through a sync tool that alters content or skips hidden files.
- Extracting with missing files due to disk space limits or transfer errors.

### 4.3. Preserve Filesystem Metadata

Beyond file content, consider:

- Permissions and executable bits.
- Owner/group and numeric UID/GID when needed.
- Symlinks and hard links.
- Timestamps if the engine or recovery procedure depends on them.
- Extended attributes, ACLs, and sparse files when used.
- Directory structure and mount paths.

A copy tool that preserves only contents while dropping access permissions can cause restore to fail when the engine needs to read files as a specific user or with specific permissions. When packaging on Linux, use an archive tool capable of preserving metadata suited to the environment.

## 5. Do Not Mix Multiple Checkpoints

Each checkpoint run must have its own target directory. Do not reuse a directory that already contains images from a previous dump unless it has been processed according to proper procedure.

Example:

~~~text
checkpoints/
├── build-2.4.0-run-001/
├── build-2.4.0-run-002/
└── build-2.4.1-run-001/
~~~

Each directory belongs to a single checkpoint run only. Do not copy files from `run-001` into `run-002` to "patch" missing files. Even when file names match, their contents may describe a different process state.

If a checkpoint fails midway, the directory may contain partial files. Mark or move it to a failed/quarantine area, save the logs, and create a new directory for the next attempt. Do not treat the existence of `inventory.img` or a few `pages` files as proof that the dump completed.

### 5.1. Use a New Path for Each Creation

Example on Linux:

~~~bash
CHECKPOINT_ROOT=/var/lib/myapp/checkpoints
CHECKPOINT_DIR="$CHECKPOINT_ROOT/build-2.4.0-run-001"

mkdir -p "$CHECKPOINT_ROOT"

java -XX:CRaCCheckpointTo="$CHECKPOINT_DIR" \
     -jar app.jar
~~~

After the application is ready and prepared for checkpointing, find the PID and request a dump:

~~~bash
jcmd -l
jcmd <PID> JDK.checkpoint
~~~

The checkpoint path should be prepared according to the documentation of the JDK/runtime in use. Current CRaC documentation describes the runtime creating the target directory if it does not exist yet, but not automatically creating all parent directories; therefore, creating parent directories beforehand is a clear and reproducible practice.

### 5.2. Wait for Checkpoint Completion Before Copying

Do not archive or synchronize the directory while CRIU is still writing images. Confirm that the checkpoint operation has finished via application and engine logs. Some versions of `jcmd` may print a success message on the client side even when detailed errors are logged to the process's console/log; read the actual logs rather than relying on a single stdout line.

Only after the checkpoint is confirmed complete should you build the inventory, generate checksums, and create the archive.

## 6. Generating Inventory and Checksums for the Checkpoint Set

A checksum manifest serves as evidence to detect missing or modified files during transfer. This manifest should be stored **next to** the image directory, not added into the CRIU directory after the dump.

### 6.1. Listing Files and Sizes

On Linux:

~~~bash
find "$CHECKPOINT_DIR" -type f -printf '%P\t%s bytes\n' | sort
du -sh "$CHECKPOINT_DIR"
~~~

The first command lists relative paths and sizes of each file. The second reports the total size of the directory.

You can save the inventory:

~~~bash
find "$CHECKPOINT_DIR" -type f -printf '%P\t%s\n' \
    | sort \
    > "$CHECKPOINT_DIR.files.txt"
~~~

In the example, the inventory file is placed alongside the checkpoint directory. Clearly record which checkpoint run the inventory file belongs to.

### 6.2. Generating Checksums

~~~bash
CHECKSUM_FILE="$CHECKPOINT_DIR.sha256"
(
    cd "$CHECKPOINT_DIR"
    find . -type f -print0 | sort -z | xargs -0 -r sha256sum
) > "$CHECKSUM_FILE"
~~~

The paths in the checksum file are relative paths from the checkpoint directory. When verifying, run from the exact extracted directory:

~~~bash
CHECKSUM_FILE=/opt/artifacts/orders-service/checkpoint.sha256
(
    cd "$RESTORED_CHECKPOINT_DIR"
    sha256sum -c "$CHECKSUM_FILE"
)
~~~

If the checksum manifest is placed elsewhere, adjust the path accordingly. Do not edit the manifest contents to ignore a file reporting an error; identify the missing or mismatched file and re-transfer the entire bundle from a valid source.

A checksum only proves that the listed files match the manifest contents. It does not prove that the image is compatible with the kernel, JDK, or restore environment.

### 6.3. Verifying Inventory After Extraction

After the archive is extracted, compare:

- The list of relative paths.
- The number of files.
- The size of each file.
- SHA-256 checksums.
- Permissions and symlinks, if any.

Do not compare total size alone. Two directories can have the same total size while having different contents, or missing one file and having an extra different file.

## 7. Archiving the Checkpoint Without Losing Structure

`tar` on Linux can be used to package the entire directory tree. For example, creating an archive from the parent directory:

~~~bash
tar --numeric-owner --acls --xattrs --sparse \
    -cpf crac-checkpoint.tar \
    -C "$CHECKPOINT_DIR" .
~~~

The command above saves the contents of the checkpoint directory into the archive, including the directory tree and the attributes supported by the options. Depending on the environment, preserving ownership, ACLs, and extended attributes upon extraction may require appropriate privileges.

Extract into a new directory:

~~~bash
mkdir -p "$RESTORED_CHECKPOINT_DIR"

tar --numeric-owner --acls --xattrs --sparse \
    -xpf crac-checkpoint.tar \
    -C "$RESTORED_CHECKPOINT_DIR"
~~~

After extraction, re-run the inventory and checksum verification. Use only verified directories for restore.

### 7.1. Compression Can Affect Performance and Resources

Checkpoints can be very large because they contain memory page data. Compressing the archive can reduce storage size but consumes CPU and time. When aiming to reduce deploy/restore time, measure all of the following:

- Checkpoint creation time.
- Archive and upload time.
- Download and extraction time.
- Checksum verification time.
- Restore time.
- Size before and after compression.

Do not compress individual image files and place compressed files back into the checkpoint directory unless the runtime supports that format. If you want compression, compress the **outer archive** and fully decompress it before restore.

### 7.2. Do Not Alter the Directory Structure After Extraction

If the archive contains the root directory's contents, extract it so that `-XX:CRaCRestoreFrom` points directly to the directory containing the image files. Avoid accidentally creating an extra directory nesting level:

~~~text
Incorrect restore path:
restore-root/
└── crac-checkpoint/
    └── inventory.img

Path restore needs to point to:
restore-root/crac-checkpoint/
    ├── inventory.img
    ├── core-*.img
    └── ...
~~~

The exact path depends on how the archive was created. Inspect the archive contents with `tar -tf` and inspect the directory after extraction before running restore.

## 8. A Compatibility Manifest Must Accompany the Checkpoint

The image set describes process state, but does not by itself provide all information about the deployment environment. A separate manifest should be created at the deployment bundle level to record provenance and compatibility conditions.

Example manifest structure:

~~~yaml
checkpoint:
  id: orders-service-2.4.0-run-001
  createdAt: "2026-11-13T07:00:00Z"
  engine: criu
  imageDirectory: ./checkpoint
  checksumFile: ./checkpoint.sha256

application:
  name: orders-service
  version: 2.4.0
  gitCommit: 8f31c2a
  artifact: app.jar
  artifactSha256: "<sha256>"

runtime:
  javaVendor: "<vendor>"
  javaVersion: "<full version and build>"
  architecture: x86_64
  os: Linux
  kernel: "<kernel version>"
  criuVersion: "<version>"
  jvmOptions:
    - "-Xms512m"
    - "-Xmx2g"

compatibility:
  runtimeConfigSchema: 3
  requiredMounts:
    - "/run/app-config"
    - "/run/secrets"
  notes: "Restore only in a validated compatible environment"
~~~

This is an example schema defined by the pipeline, not an official CRaC or CRIU manifest format. Do not write passwords, API tokens, private keys, or secret values into the manifest.

### 8.1. Information to Record

| Group | Information |
|---|---|
| Checkpoint identity | Unique ID, creation timestamp, creation environment |
| Application | Version, Git commit, artifact checksum |
| JVM | Vendor, full version, build, JVM options |
| Operating system | Distribution, kernel, architecture |
| Engine | CRaC engine, CRIU version, and related options |
| Filesystem | Mount paths, volumes, required external files |
| Configuration | Schema version, non-sensitive configuration revision |
| Verification | Inventory, total size, checksums, restore test results |

The manifest helps operators know which source and runtime a checkpoint was created from. It does not replace compatibility checks prior to restore.

### 8.2. Specify CPU and Architectural Conditions

Restoring on another machine can fail if the CPU lacks features that the checkpoint used. Similarly, different CPU architectures or different kernel conditions can make the image incompatible.

Therefore, do not simply record "Linux x86_64" and conclude that every x86_64 machine can restore it. Retain CPU/JDK information and follow the compatibility guidance of the CRaC runtime/vendor.

## 9. Resources External to the Image Directory

A complete image set can still depend on external resources. This is why you must distinguish "having all files" from "having all conditions met for restore."

### 9.1. Referenced Files and Mounts

A process may hold file descriptors or memory mappings to external files. Depending on the file type and how CRIU handles it, the content may be saved in the image, handled by a plugin, or required to exist at the corresponding path.

Before moving a checkpoint:

- Identify the mounts used by the process.
- Ensure referenced files are present with the correct content.
- Keep required paths, permissions, and access rights.
- Do not replace JDK/native library files that the process needs to map.
- Verify container volumes and mount namespaces.

Do not assume that copying only the checkpoint directory brings along the entire container filesystem.

### 9.2. Sockets and Networking

Open sockets typically need to be handled via CRaC Resource callbacks before checkpointing. After restore, the application should recreate connections to databases, brokers, HTTP services, and external systems according to the appropriate lifecycle.

Even if the image contains socket metadata, network endpoints, or namespaces, external server-side state may have changed while the process was stopped. Thus, callbacks should validate or recreate resources rather than trusting that old sessions are still valid.

### 9.3. Credentials and Secrets

The checkpoint may contain data on the heap, including secrets previously read by the application. If a checkpoint is shared across multiple environments, avoid loading environment-specific credentials before dumping.

Do not treat clearing a field from an object as proof that the secret has vanished from the entire memory image. Protect checkpoint artifacts as sensitive data, restrict access permissions, encrypt at rest and in transit, and use a secret manager to load environment-specific credentials after restore.

### 9.4. Temporary Files and Data in tmpfs

If the process depends on files in `/tmp`, tmpfs, or a temporary mount, determine whether the CRIU engine saved the content or requires the restore environment to re-provide it. A path existing with different content can also cause the application to behave incorrectly.

For temporary files that can be recreated, the safe approach is usually to close the resource before checkpoint and recreate it after restore via callbacks. For files that must remain intact, clearly record their location and preservation requirements.

## 10. A Safe Checkpoint Packaging Workflow

A pipeline can be organized into the following stages:

~~~text
1. PREPARE
   - Build application
   - Select JDK/CRaC runtime and CRIU
   - Identify mounts, configs, and resource dependencies

2. RUN AND WARM UP
   - Start application
   - Execute representative workload
   - Check READY state

3. QUIESCE
   - Stop accepting new traffic/work
   - Drain requests, transactions, and background work
   - Close resources that must be recreated after restore

4. CHECKPOINT
   - Invoke JDK.checkpoint
   - Wait for engine to complete dump
   - Save logs and results

5. VERIFY IMAGE SET
   - List all files
   - Record sizes and checksums
   - Confirm directory is no longer changing

6. PACKAGE
   - Archive the entire directory
   - Create external manifest
   - Compute archive checksum

7. TRANSFER
   - Upload/copy archive
   - Verify checksum at destination
   - Extract completely

8. RESTORE TEST
   - Verify compatible environment
   - Restore from verified copy
   - Run smoke tests and health checks

9. PUBLISH
   - Mark artifact READY only after the steps above complete
~~~

Each stage should have its own status. For example: `PREPARING`, `CHECKPOINTING`, `IMAGE_VERIFIED`, `PACKAGED`, `TRANSFERRED`, `RESTORE_TESTED`, `READY`. Do not use a single `exists=true` flag to represent all steps.

### 10.1. Use a Temporary Directory and Publish Only Once Verified

A safe implementation pattern is to write the checkpoint to a run-unique path, then verify it before renaming or publishing the archive to the official location.

~~~text
artifact-staging/
└── orders-2.4.0-run-001.tmp/
    ├── checkpoint/
    ├── checkpoint.sha256
    └── manifest.yml

artifact-repository/
└── orders-2.4.0-run-001/
    ├── checkpoint.tar
    ├── checkpoint.tar.sha256
    └── manifest.yml
~~~

Do not include `.tmp` directories in the list of artifacts allowed for restore. Transition the status to READY only after the checkpoint completes, checksums match, the archive extracts cleanly, and the restore test succeeds.

If using object storage, you can upload to a temporary key and then publish the manifest or version tag last. Do not let consumers download an archive that is still being uploaded.

### 10.2. Do Not Modify the Image Directory After Dump

Once CRIU finishes, treat the image directory as an immutable artifact:

- Do not add pipeline-generated files inside it.
- Do not edit file contents or permissions without a clear procedure.
- Do not delete logs/images that "seem unnecessary."
- Do not rename files.
- Do not merge images from another dump.
- Do not extract over an existing old directory.

Store manifests, checksums, and logs outside the image directory to avoid altering the file set created by the engine.

## 11. Verifying Completeness Before Restore

Verification can be performed across multiple layers.

### 11.1. Existence and Structure Checks

Confirm that the restore path points directly to the image directory, the directory is non-empty, and it contains the files created by the engine. Compare against the inventory from that exact dump.

Do not use a fixed list of filenames as the sole standard. A valid image may lack a certain resource type if the process did not use it.

### 11.2. Checksum Verification

Run `sha256sum -c` against the manifest generated immediately after the checkpoint. If a file is missing or differs by even a byte, halt the process and re-fetch the archive from a valid source.

Do not proceed with restore by ignoring a few failing checksum lines. The files have internal cross-references; missing one component can break the entire restore.

### 11.3. Environment Capability Checks

CRIU provides a command to check kernel features and capabilities:

~~~bash
criu check
~~~

This command helps confirm some of the environmental conditions CRIU requires. It is not a tool for verifying an entire checkpoint image and does not prove that a specific checkpoint will definitely restore.

In addition, verify:

- The CRaC JDK is compatible with the image.
- The CRIU/engine version is appropriate.
- Kernel and CPU features meet requirements.
- Required checkpoint/restore permissions/capabilities are present.
- External mounts and files are present.
- Network namespaces, ports, and filesystems match.
- Runtime configuration and secrets can be loaded after restore.

### 11.4. Restore Testing Is the Most Important Validation

The most practical test is to restore a copy of the checkpoint in a compatible test environment.

~~~bash
java -XX:CRaCRestoreFrom=/opt/artifacts/orders-2.4.0/checkpoint
~~~

After restoring, check:

1. Whether the process starts from the image.
2. Whether CRaC logs and resource callbacks complete.
3. Whether application readiness transitions to READY.
4. Whether health endpoints respond.
5. Whether databases, message brokers, and external services reconnect.
6. Whether representative requests or background tasks run properly.
7. That there are no file descriptor, permission, or mount errors.
8. That memory and resource usage stay within deployment limits.

A valid checksum only proves that the data was not altered relative to the manifest. A restore test confirms that the image set and environment actually work together in real conditions.

## 12. Common Error Handling

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Restore reports missing image file | Archive missing files or wrong extraction path | Compare inventory/checksums and re-extract into a new directory |
| Restore reads inventory but fails on memory pages | Missing or corrupted `pagemap`/`pages` | Re-transfer the entire image set from a valid source |
| Permission denied | Lost owner, mode, or missing capability | Restore metadata and check runtime permissions |
| Referenced file not found | Mount or external file absent on target host | Restore appropriate mount/path and contents |
| Restore fails on CPU feature | Target host lacks required features | Use compatible host or create checkpoint with suitable CPU policy |
| Restore fails on network/socket | Resource not properly closed/restored or different namespace | Handle via CRaC Resource and verify networking |
| Extracted archive has an extra directory level | Archive structure/extract path mismatch | Point restore directly to the directory containing the image files |
| Archive checksum valid but restore fails | Archive intact but image/environment incompatible | Check JDK, CRIU, kernel, mounts, and restore logs |
| Checkpoint directory has files but dump failed | Only partial images written before error | Read logs, mark as failed, and create a new checkpoint |
| Restore test passes but production fails | Differences in permissions, mounts, secrets, network, or resource limits | Compare environment manifests and check each dependency |

### 12.1. Do Not Fix a Checkpoint by Guessing Missing Files

If restore reports a missing file, do not take a file of the same name from another checkpoint to fill it in. A file with the same name does not mean it belongs to the same process snapshot.

Safe handling:

1. Preserve the original checkpoint for investigation.
2. Check dump and transfer logs.
3. Determine whether the file was lost during creation, archiving, upload, or extraction.
4. Re-fetch the entire archive from a valid source if the transfer failed.
5. If the original checkpoint already missed files because the dump failed, create a new checkpoint.
6. Regenerate the manifest/checksum and run a restore test.

## 13. Artifact Protection and Lifecycle Management

A checkpoint may contain application data, caches, user information, and secrets in memory. It must be protected as a sensitive artifact.

Measures to apply:

- Restrict people and services with read access to checkpoints.
- Encrypt at rest and in transit.
- Do not send checkpoints over unencrypted/insecure channels.
- Do not commit images into regular Git repositories.
- Do not leave checkpoints in public web directories.
- Audit who creates, downloads, extracts, and restores artifacts.
- Have a retention policy and secure deletion process.
- Define access permissions for backups and archive replicas.
- Do not place secret values into manifests or logs.

If a checkpoint is shared across multiple environments, pay special attention to data loaded into the heap before the dump. Closing a connection or clearing a field does not prove all sensitive data has been purged from the memory image.

### 13.1. Distinguishing Checksums from Signatures

Checksums like SHA-256 help detect unintended modifications during storage or transfer. However, anyone with permission to replace the archive could also regenerate the checksum.

If you need to verify artifact provenance, sign the manifest or checksum using a separately managed key. Upon restore, verify the signature with a public key/trust store managed independently from the archive. A signature confirms the publisher under a trust policy; it does not prove that the image is compatible or business-safe.

## 14. Rules for Preserving Completeness

When operating CRaC checkpoints, observe the following principles:

1. **One dump, one dedicated directory:** do not mix files across checkpoint runs.
2. **Keep the entire directory tree:** do not copy only `.img` files or small files.
3. **Do not modify images:** do not rename, truncate, merge, or edit file contents.
4. **Wait for dump completion:** do not archive while the engine is still writing.
5. **Preserve metadata:** retain permissions, ownership, symlinks, ACLs, and xattrs when required.
6. **Generate checksums outside the image directory:** verify after every transfer or extraction.
7. **Record a compatibility manifest:** JDK, CRIU, kernel, CPU, artifact, and mounts.
8. **Keep external resources intact:** required files, mounts, secret providers, and networking must be ready.
9. **Restore test before release:** do not treat file existence or checksums as proof of successful restore.
10. **Protect checkpoints:** images may contain sensitive data in memory.

A checkpoint should be considered deployment-ready only when the image set was completely generated, preserved intact, accompanied by a compatibility manifest, all external dependencies have been identified, and a restore test in an equivalent environment has succeeded.

## 15. References

- [CRaC — Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/): how to configure the checkpoint path, request checkpoints, and restore.
- [CRaC — Implementing the CRaC API](https://crac.org/use/implement-crac/): managing resources before checkpoint and after restore.
- [CRIU — Images](https://criu.org/Images): image file types, metadata, and memory pages.
- [CRIU — Checkpoint/Restore](https://criu.org/Checkpoint/Restore): how CRIU collects process and resource state.
- [Spring Boot — Checkpoint and Restore With the JVM](https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html): overview of checkpoint/restore and Spring Boot's lifecycle support scope.

Specific file structures must be confirmed against the deployed JDK, engine, and CRIU version. The file names in this article are examples for identifying data groups; they are not a fixed list for every checkpoint.
