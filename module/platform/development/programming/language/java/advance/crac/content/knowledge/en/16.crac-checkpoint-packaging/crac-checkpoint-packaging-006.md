# Permissions, Ownership, and Paths to Preserve When Distributing

A CRaC checkpoint image contains the state of a JVM process at the time of the checkpoint. When distributing an image to another environment for restore, copying enough files is not sufficient. The restore process also needs to be able to read the image, access the paths that the process state depends on, and have appropriate permissions for external resources.

On Linux, access depends on the user ID (UID), group ID (GID), permission bits, ACL, namespaces, mounts, and security policies such as SELinux or AppArmor. Paths also matter significantly: a file opened before checkpoint may need to appear at the same location in the restore environment; a symlink may point to a different target; a volume may be mounted at a different path.

Therefore, when packaging and distributing a checkpoint, three groups of information must be managed simultaneously:

- **Permissions**: who may read, write, traverse, or modify the image and its dependent files.
- **Ownership**: which UID/GID owns the files, directories, and restored resources; how those IDs are mapped inside a container or user namespace.
- **Paths and mounts**: which absolute paths, symlinks, mount points, and filesystems must exist with a compatible structure at restore time.

An image should only be considered ready for distribution when the checkpoint has completed, necessary metadata has been preserved, permissions at the destination have been verified, and the restore environment satisfies the assumptions about paths, UID/GID, and mounts.

## 1. Why Permissions and Paths Affect Restore

Checkpoint/restore does not simply read a standalone data file. The runtime and OS tooling need to access the image files, re-establish the process state, and handle the resources the process was using. The application may also need to read configuration, native libraries, certificates, data files, or volumes mounted at specific paths.

Common errors include:

- The user running the JVM does not have permission to traverse the parent directory or read the image files.
- The image files belong to a different UID/GID than the user in the restore environment.
- The archive is extracted but loses owner, permissions, ACL, or extended attributes.
- The container runs with a different UID but the volume retains the host's owner.
- The user namespace maps UID/GID differently from the environment where the checkpoint was created.
- The absolute paths of files or mount points do not exist at restore time.
- Symlinks are preserved but their targets are missing or point to different data.
- SELinux labels or AppArmor policies block access even though permission bits appear correct.
- The image is extracted into a different filesystem that does not support the required metadata or behavior.

These errors can appear during the image-reading phase, during file descriptor reconstruction, or when the application resumes after restore. Therefore, both the restore operation itself and subsequent business operations must be tested.

### Distinguishing Image Permissions from Application Resource Permissions

There are two separate groups of permissions to consider:

1. **Permissions on the checkpoint directory**: allows the runtime to create the image, store sub-files, read the image, and perform restore.
2. **Permissions on application resources**: allows the restored process to access logs, data files, certificates, temporary directories, Unix sockets, or volumes that the application requires.

Granting read access to the image does not mean the application has permission to write logs or reopen data files. Conversely, granting permissions on the data directory does not help the runtime read the checkpoint if the image directory is blocked.

## 2. UID, GID, and Permission Bits on Linux

Linux determines access based on the process's UID, the GIDs the process belongs to, the permission bits of the filesystem object, and additional control mechanisms.

Example:

~~~bash
id
id myapp
stat -c '%u:%g %a %n' /var/lib/myapp/crac
~~~

The `id` command shows the UID, primary GID, and supplementary groups of the user. `stat` displays the owner, group, and permission mode of the path.

### Meaning of Permissions on Files and Directories

| Permission | On a file | On a directory |
|---|---|---|
| Read (`r`) | Read the contents | List the names of entries |
| Write (`w`) | Modify the contents | Create, delete, or rename entries if other conditions allow |
| Execute (`x`) | Execute the file if its format and policy allow | Traverse/search the directory to access entries within |

A user who has read permission on a file but lacks `x` permission on a parent directory still cannot access the file via that path. Therefore, checking the permission of the image file alone is insufficient; the entire directory chain must be checked.

Example:

~~~bash
namei -l /var/lib/myapp/crac/release-001
~~~

`namei -l` displays each component of the path and its corresponding permissions. This is a useful way to find the parent directory that is blocking access.

### Choosing a Minimal Owner and Mode

The directory containing the image should generally be owned by the application's dedicated user or group. Access should only be granted to components that need to create, read, or manage the image.

Example of creating a parent directory:

~~~bash
sudo install -d -o myapp -g myapp -m 0700 /var/lib/myapp/crac
~~~

This command creates the directory with owner `myapp`, group `myapp`, and permissions that only the owner can access. If a backup or restore process runs under a separate group, the permission design must correctly reflect the operational model; `0700` is not the right default for every workflow.

Do not use `chmod -R 777` to fix permission errors. Read/write access for all users can expose data in the image and allow unrelated processes to modify or delete the state that needs to be restored.

## 3. Owner and Group Must Match the Restore Environment

The username displayed on one machine is not the identifier stored in the filesystem. Filesystems typically store UID/GID as numeric values. Two machines may both have a user named `myapp` but with different UIDs.

Example:

| Environment | User | UID | GID |
|---|---|---:|---:|
| Image-creating host | myapp | 1001 | 1001 |
| Restore host | myapp | 2001 | 2001 |

If the archive preserves numeric ownership, the files may still belong to UID 1001 on the target machine. The `myapp` user with UID 2001 will not automatically become the owner just because the name is the same.

Before distributing, determine:

- The UID/GID running the JVM at the source.
- The UID/GID running the JVM at the destination.
- The required supplementary groups.
- The user of the process that creates, transfers, extracts, and restores the image.
- The ownership rules of the volume or shared storage.

You can check the user/group in both environments using `id`. When needed, check numeric ownership with `stat` or `ls -ln`; do not rely solely on names resolved from `/etc/passwd`.

### Choosing a Clear Ownership Policy

There are two common implementation approaches:

**Keep the same numeric UID/GID.** Configure the application user to have the same UID/GID across related hosts or containers. This reduces the need to change ownership during distribution and keeps filesystem permissions consistent.

**Map ownership at the destination.** If UIDs/GIDs differ, extract or prepare the volume with the owner appropriate for the restore user. Only change ownership on the destination copy and in accordance with the security policy; do not modify the source image while it is being used by another process.

Do not change ownership blindly. Some files or resources may need a different owner than the user running the JVM; base decisions on how the runtime and application created them.

### Permissions of the Restore Process

The user running the restore needs read permission on the entire image and traverse permission on parent directories. The runtime may require additional permissions depending on the JDK's checkpoint/restore mechanism, CRIU, and the operating system. Do not assume ordinary read access is sufficient for every CRIU configuration; consult the requirements of the runtime and container.

If the restore operation runs under a different user than the one that created the checkpoint, clearly identify who owns the image and whether that process can access the restored resources.

## 4. Umask, ACL, and Extended Attributes

Permission bits are not the only filesystem metadata.

### Umask

The umask removes some default permissions when a process creates a file or directory. Therefore, the same file-creation command can produce different permissions in two different environments.

Check:

~~~bash
umask
~~~

If the runtime or the script that creates the image runs under different umask values, newly created files may receive different modes. Do not rely on the default umask of the shell or service manager; configure permissions explicitly and verify them after image creation.

### POSIX ACL

ACLs can grant additional permissions to users/groups beyond the traditional owner and group. A file showing mode `640` may still have ACL entries that affect effective permissions.

Check:

~~~bash
getfacl -p /var/lib/myapp/crac
~~~

When distributing, determine whether ACLs must be preserved or need to be recreated according to the destination's policy. If the archive tool does not preserve ACLs, the extracted result may have different access permissions.

### Extended Attributes and File Capabilities

Filesystems may store extended attributes (xattrs), security labels, or file capabilities. Some packaging tools do not preserve them by default.

Extended attributes can be checked with:

~~~bash
getfattr -d -m- /var/lib/myapp/crac
~~~

Do not arbitrarily add file capabilities or security attributes to the image. Only preserve the metadata that is necessary and permitted by the deployment policy.

## 5. SELinux, AppArmor, and Security Policies

Correct permission bits do not guarantee that access will succeed. Linux may apply Mandatory Access Control mechanisms such as SELinux or AppArmor.

### SELinux

SELinux attaches a security context to files and processes. A file that the owner permits to be read may still be denied if its label does not match the service's domain.

Check the context:

~~~bash
ls -Z /var/lib/myapp/crac
~~~

Check policies and AVC logs following the system's administration procedures. When transferring an image to another host, labels may no longer be compatible with the policy at the destination. Typically, labels should be assigned according to the destination host's policy rather than copying labels verbatim from the source host.

Do not disable SELinux just to make checkpoint/restore work. Identify the correct paths, file types, and required policies, then grant the minimum necessary permissions.

### AppArmor

AppArmor controls access based on the process's profile. A profile may allow a service to read a path at the source but block the staging or restore path at the destination.

Check the active profile and denial logs. If the profile needs to be updated, restrict rules to the exact checkpoint directory and the application resources that must be accessed.

### Container Security Policy

Inside a container, there may also be:

- User namespace and UID/GID mapping.
- Read-only root filesystem.
- Seccomp profile.
- Capability set.
- Mount propagation and bind mounts.
- Cgroup and resource limits.
- SELinux label or AppArmor profile of the container.

Do not use `--privileged` as a general fix for permission errors. Determine exactly what permissions CRIU, the JDK, and filesystem operations require, then configure the smallest possible scope.

## 6. Absolute Paths and Directory Structure to Preserve

A checkpoint image is typically stored in a directory structure created by the runtime and checkpoint tooling. When distributing, the entire directory tree and the names of sub-files must be preserved exactly. Do not arbitrarily rename individual files within the image.

The checkpoint path should be clearly specified in the configuration:

~~~bash
java -XX:CRaCCheckpointTo=/var/lib/myapp/crac/release-001 -jar app.jar
~~~

When restoring:

~~~bash
java -XX:CRaCRestoreFrom=/var/lib/myapp/crac/release-001
~~~

Option names and behavior may depend on the JDK CRaC distribution. Check the documentation for the exact runtime before using.

### Why Use Absolute Paths?

Relative paths depend on the working directory. Service managers, container entrypoints, and scripts may set different working directories. Absolute paths make the image creation, transfer, and restore workflow more consistent.

Do not only record the checkpoint path. Also record all paths the application is using, for example:

- Configuration directory.
- Log directory.
- Data directory.
- Temporary directory.
- Certificates, trust stores, and key files.
- Native libraries and file mappings.
- Unix domain sockets or mount points of internal services.

Not every path is required to be identical in every situation. However, if the process or a library holds a file descriptor, memory mapping, or state that depends on a path, the restore environment must satisfy the corresponding requirement.

### Mount Points and Volumes

In a container, the same path may be provided by different volumes. For example, `/var/lib/myapp/data` at the source is a persistent volume, but at the destination it is an empty directory in the writable layer. Restore may succeed but the application may read incorrect data or fail to find files.

Record the mount table and volume source:

~~~bash
findmnt
findmnt -T /var/lib/myapp/data
~~~

In the restore environment, mount the correct volume to the correct path before starting the restore. Verify the filesystem, owner, mode, and data inside. If a volume is replaced, a data compatibility plan is needed rather than simply creating a directory with the same name.

## 7. Symlinks, Hard Links, and File Mappings

A path may contain symlinks. Preserving a symlink only preserves the target string it points to; it does not guarantee the target exists or is the same as the source.

Check:

~~~bash
find /var/lib/myapp -type l -printf '%p -> %l\n'
readlink -f /var/lib/myapp/current
~~~

Before restoring, verify:

- Required symlinks still exist.
- The target path is present.
- The target has appropriate owner and permissions.
- Symlinks do not inadvertently point outside the permitted filesystem area.
- No symlink has been changed to point to different data or an unsafe path.

Hard links can cause multiple filenames to reference the same inode. If the packaging tool does not preserve hard links, the extracted result may produce independent copies. For data that depends on hard links, choose tools and options that preserve them appropriately.

Memory-mapped files and open file descriptors may have specific requirements during checkpoint/restore. Do not assume that simply creating a file with the same name is sufficient. The inode, mount, file content, and how CRIU handles that file under the actual configuration all need to be verified.

## 8. Packaging the Image and Preserving Metadata

Only package after the checkpoint has completed successfully and the runtime is no longer writing to the image directory. Do not archive a directory that is still being created or updated.

### Using tar When Metadata Preservation Is Needed

On Linux, GNU tar has options to preserve owner, ACL, xattrs, and SELinux context:

~~~bash
tar --numeric-owner --acls --xattrs --selinux \
    -cpf release-001.tar \
    -C /var/lib/myapp/crac release-001
~~~

Option support and behavior depend on the tar version, user permissions, and filesystem. When extracting, appropriate permissions may be needed to restore numeric ownership and metadata:

~~~bash
sudo tar --numeric-owner --same-owner --acls --xattrs --selinux \
    -xpf release-001.tar \
    -C /var/lib/myapp/crac
~~~

If the destination environment uses a different SELinux policy, labels may need to be reassigned according to the destination policy after extraction. Do not mechanically keep source labels if they are not compatible.

### Using rsync to Transfer a Directory Tree

If transferring directly between filesystems or hosts, rsync can preserve many types of metadata:

~~~bash
rsync -aHAX --numeric-ids \
    /var/lib/myapp/crac/release-001/ \
    restore-host:/var/lib/myapp/crac/release-001/
~~~

Where:

- `-a` preserves basic archive attributes such as permissions, timestamps, symlinks, and owner/group to the extent permitted by capabilities/permissions.
- `-H` preserves hard links.
- `-A` preserves ACLs.
- `-X` preserves extended attributes.
- `--numeric-ids` uses numeric UID/GID instead of mapping by user/group name.

Owner/group options may require root access at the source or destination. The destination filesystem must also support the corresponding metadata. If a particular attribute cannot be preserved, document it and apply a deliberate metadata recovery policy.

### Do Not Copy Only the Visible Files

A checkpoint image may consist of many files, subdirectories, and metadata. Copying only part of it, skipping hidden files, or altering the structure may cause restore to fail. Use an operation that copies the entire image tree while preserving its structure, then verify the manifest/checksum and file count.

Do not run multiple sync operations concurrently into the same image directory. Avoid editing, re-compressing, or changing ownership while a restore process is reading the image.

## 9. UID/GID Mapping in Containers and User Namespaces

Containers may use user namespaces to map UID/GID inside the container to different UID/GID on the host. For example, UID 1000 inside a container may be mapped to UID 101000 on the host.

This means:

- `id` inside the container may show UID 1000.
- `stat` on the host may show UID 101000.
- A volume created from the host may not be accessible to the user inside the container.
- An archive extracted on the host may need a different numeric owner than what is seen inside the container.

Before distributing, determine whether the image is created and restored within the same or different user namespaces. If the mapping changes, check the ownership of the entire image directory and resources outside the image.

Do not change the UID/GID of all files in the checkpoint tree without first knowing whether the runtime depends on owner metadata. A safer approach is to keep compatible mapping between source and destination, or to explicitly test the remap workflow on a copy.

### Rootless Containers

With rootless containers, the user inside the container is typically mapped to a range of UID/GID belonging to the user running the container on the host. The process may not have arbitrary `chown` permission on the filesystem.

Check:

- UID/GID inside the container.
- UID/GID mapping on the host.
- Owner of bind mounts or volumes.
- Ability to preserve owner during archive/unarchive.
- Permissions required by CRIU and the runtime in rootless mode.

If ownership cannot be preserved via normal operations, use the volume or mapping mechanisms supported by the platform. Do not assume that `sudo` inside the container grants true root on the host.

## 10. Paths Outside the Image That Must Be Preserved

A checkpoint image does not necessarily package all the data the process needs. Many resources are provided from the filesystem, volumes, or external services. Compile a list of path dependencies and determine how to distribute them.

| Path/Resource | What must be preserved or verified |
|---|---|
| Checkpoint directory | Full image structure, owner, mode, and required metadata |
| JDK/runtime | Correct distribution/version and compatible installation path |
| Native library | Binary with correct architecture, version, and loader path |
| Configuration file | Content and path compatible with the restore environment |
| Certificate/trust store | Current file, read permissions, and valid chain |
| Data directory | Same volume or compatible data at the path the application uses |
| Log directory | Exists, is writable, and does not point to a lost filesystem |
| Temporary directory | Can create files and has sufficient space |
| Unix domain socket | Directory and endpoint recreated by the service owner |
| File lock | No old lock held; re-execute the lock protocol after restore |
| Memory-mapped file | Path, inode/content, and mount compatible with the state to be restored |

### Absolute Paths in Process State

A process may hold a working directory, root directory, file descriptor, or memory mapping. Some state depends on the path or mount namespace of the environment where the image was created. If restore occurs in an environment with a different path structure, CRIU may be unable to restore resources or the application may behave incorrectly.

Record mounts and critical paths in the deployment manifest. Before restore, create the necessary mounts at the correct locations. If paths must change, verify how the runtime and application support that change; do not simply rename the image directory and hope all references are updated.

### Do Not Distribute Unix Sockets as Regular Files

A Unix domain socket is an endpoint created and managed by a process/service. Copying a socket filesystem entry does not create a listening server at the destination. Typically, the service that owns the socket must start and recreate the endpoint after restore; the application reconnects via the new or stable path.

## 11. Securing the Image During Distribution

A checkpoint image may contain data from the heap and process state, including:

- Access tokens, passwords, or credentials.
- Session and request data.
- Personal information or business data.
- Private keys or sensitive content that has been decrypted.
- Caches and internal data.

Treat a checkpoint image as a sensitive data snapshot of the application.

### Restrict Access

- Only the users/services that need to should be able to read the image.
- Do not place the image in a public web directory or public bucket.
- Do not commit the image to Git or include it in a Docker build context.
- Do not grant read access to all users on the host.
- Protect temporary archives, checksum manifests, and backups.
- Apply a retention policy and secure deletion in accordance with data policy.

### Encryption at Rest and in Transit

Use an authenticated and encrypted transport channel, such as SSH/SFTP or a storage service with TLS. If encryption at rest is required, apply the appropriate filesystem, volume, or artifact repository encryption mechanism.

Do not send passwords or private keys in command lines or logs. Manage encryption keys using an approved secret/key management system. Ensure that only the restore environment is granted permission to decrypt the image.

### Separating Creation, Distribution, and Restore Permissions

In large systems, it may be possible to separate:

- The service runtime that creates the checkpoint.
- The job that packages and signs the manifest.
- The artifact store that holds the distributed image.
- The restore worker that downloads, verifies, and extracts.
- The JVM restore that runs under a dedicated runtime user.

Each component should only have the permissions necessary for its task. For example, the distribution job does not need read access to the production database if it is only transferring an archive.

## 12. Verifying Image Integrity and Provenance

After packaging, create a checksum to detect errors or unintended changes during transfer.

Example:

~~~bash
sha256sum release-001.tar > release-001.tar.sha256
~~~

At the destination:

~~~bash
sha256sum -c release-001.tar.sha256
~~~

A checksum proves that the received data matches the data for which the checksum was created; it does not prove the sender is trustworthy if the checksum and archive are transferred via the same unauthenticated channel. For strict release workflows, sign the manifest with a separately managed key and verify the signature at the destination.

The manifest should record:

- Checkpoint ID and creation timestamp.
- Application build/version.
- Dependency lockfile or artifact checksum.
- JDK distribution/version and JVM flags.
- CRIU, kernel, OS, and CPU architecture.
- UID/GID of the process that created the image and the mapping policy.
- Checkpoint paths and important mounts.
- List of volumes or external data the image depends on.
- Archive size and SHA-256.
- Restore test status.

Do not embed secrets in the manifest. Record the name/version of a secret or a secure reference if traceability is needed; do not record secret values.

## 13. Controlled Distribution Workflow

~~~mermaid
flowchart TD
    A[Checkpoint complete] --> B[Freeze image tree]
    B --> C[Collect path and UID/GID metadata]
    C --> D[Package with metadata preservation]
    D --> E[Create checksum and sign manifest]
    E --> F[Transfer via secure channel]
    F --> G[Verify signature and checksum]
    G --> H[Extract to staging]
    H --> I["Apply owner, ACL, and security labels per destination"]
    I --> J["Check paths, mounts, and permissions"]
    J --> K[Promote to restore directory]
    K --> L[Restore and check readiness]
~~~

### Step 1 — Wait for Checkpoint to Complete

Only begin packaging when the runtime confirms the checkpoint was successful. Do not archive a directory that CRIU/JVM is still writing. If the checkpoint fails, verify whether the image is complete before distributing.

### Step 2 — Collect Metadata

Record the owner, group, mode, ACL, xattrs, symlinks, and mount assumptions. Record the runtime version, architecture, and paths the process requires. Create a manifest outside the image.

### Step 3 — Package

Use a tool that preserves metadata appropriate for the source and destination filesystems. Record the tool version and options used so the process can be repeated.

### Step 4 — Create Checksum and Sign

Compute a checksum for the archive and sign the manifest if the workflow requires provenance verification. Store the signature and metadata separately from secrets.

### Step 5 — Transfer the Image

Use a transport channel that is authenticated, encrypted, and has restricted access. Avoid writing the archive to a temporary directory with overly broad permissions.

### Step 6 — Verify at the Destination

Verify the checksum/signature before extracting. Do not restore an archive with an incorrect checksum or unknown provenance.

### Step 7 — Extract and Prepare Metadata

Extract into a separate staging directory. Preserve the image structure, then adjust owner/ACL/security labels according to the destination's mapping and policy if needed. Do not modify the original archive directly.

### Step 8 — Check Paths and Mounts

Verify all required paths, mount points, native libraries, configuration, volumes, and access permissions. Test with the actual runtime user, not just an administrative user.

### Step 9 — Promote and Restore

When staging has been verified, move it to the final restore directory using an atomic rename if staging and destination reside on the same filesystem. Do not rename or move the image tree while a restore is reading it.

### Step 10 — Post-Restore Verification

Confirm that the JVM restored successfully, resources were recovered, the application can access files and volumes, listeners opened the correct paths/ports, and readiness is only exposed after mandatory dependencies are ready.

## 14. Example of Checking Permissions and Paths Before Restore

Assuming the image is located at:

~~~text
/var/lib/myapp/crac/release-001/
~~~

Before restore, the following checks can be performed:

~~~bash
id myapp
namei -l /var/lib/myapp/crac/release-001
stat -c '%u:%g %a %n' /var/lib/myapp/crac/release-001
getfacl -p /var/lib/myapp/crac/release-001
findmnt -T /var/lib/myapp/crac/release-001
~~~

If using SELinux:

~~~bash
ls -Zd /var/lib/myapp/crac/release-001
~~~

After verifying the user and policy, run the restore using the correct user/service manager and runtime configuration. Do not run restore as root just to bypass permission errors if the application was designed to run as an unprivileged user.

### Distinguishing Permission Errors from Path Errors

| Message | What to check |
|---|---|
| `Permission denied` | Owner, mode, ACL, parent directory, SELinux/AppArmor, and namespace |
| `No such file or directory` | Path, symlink target, mount, and volume startup order |
| `Read-only file system` | Mount option, container rootfs, and volume mode |
| `Operation not permitted` | Capability, user namespace, filesystem, and security policy |
| `Invalid argument` when restoring a resource | Filesystem/kernel/runtime behavior and resource metadata |

Do not draw conclusions from a single error message alone. Read the logs of the JVM, CRIU, kernel, and container runtime to identify which component denied the operation.

## 15. Common Distribution Errors

| Error | Consequence | How to Prevent |
|---|---|---|
| Extracting with a user that lacks permission to preserve owner | UID/GID changes or is incorrect | Use a restore metadata workflow with appropriate permissions |
| Copying without ACL/xattrs | Effective permissions or security labels change | Use tools with preservation options and check after copying |
| Same username but different UID | Runtime does not have the same permissions as the source | Match numeric UID/GID or intentionally remap |
| Changed checkpoint path | Runtime cannot find the image or its sub-structure | Preserve the image tree and configure the restore path explicitly |
| Volume mounted at the wrong location | Application reads different data or cannot find files | Verify the mount table and manifest paths |
| Symlink pointing to a non-existent target | Restore or application fails on access | Check the target and preserve the structure |
| Archiving before checkpoint is complete | Archive is incomplete or inconsistent | Wait for checkpoint completion confirmation |
| Restoring while copying is in progress | Runtime reads incomplete data | Only promote after copy and checksum succeed |
| SELinux/AppArmor blocks access | Permission bits are correct but access is still denied | Check policy and audit log |
| Publishing image to a public location | Data in memory is exposed | Restrict permissions, encrypt, and apply retention policy |
| Restoring on an incompatible filesystem | Metadata or file behavior changes | Verify filesystem and run a restore test |
| Different UID mapping in a rootless container | Owner on host does not match owner inside container | Verify user namespace mapping |

## 16. Testing Distribution and Restore

Testing must include transferring the image between environments, not only restoring on the host where the checkpoint was created.

### Basic Test Scenarios

1. Run the application as the designated user/group.
2. Record the UID/GID, umask, permissions, ACL, xattrs, and mount of the image directory.
3. Create a checkpoint and wait for the operation to complete.
4. Package the entire image tree using a tool that preserves metadata.
5. Create a checksum/manifest.
6. Transfer the archive to the destination environment.
7. Verify the checksum and signature.
8. Extract to staging and check owner, mode, ACL, xattrs, and symlinks.
9. Prepare the correct mount points, paths, and security policy.
10. Restore using the expected runtime user.
11. Check that the application can access files, volumes, logs, certificates, and dependencies.
12. Confirm readiness and business operations.

### Additional Scenarios

| Scenario | What to verify |
|---|---|
| Same UID/GID at source and destination | Effective permissions are preserved |
| Different UID/GID | Owner remap workflow functions correctly |
| Restore in a rootless container | Mapping and volume permissions are appropriate |
| ACL/xattrs in use | Metadata is preserved or correctly recreated |
| SELinux enabled at the destination | Label/policy permits the required access |
| Different mount point from source | Restore is safely rejected or the path is explicitly supported |
| Symlink pointing outside the image tree | Target exists and does not violate policy |
| Checksum mismatch | Artifact is rejected before restore |
| Insufficient disk space or inodes | Workflow detects this before extraction |
| External data file missing | Readiness is not exposed and the error is clearly reported |

Do not use a single test that only runs as root to conclude that the runtime user's permissions are correct. Test with the actual user, group, namespace, and policy.

## 17. Pre-Distribution Checklist

### Ownership and Permissions

- [ ] Recorded the UID/GID of the checkpoint-creating user and the restore user.
- [ ] Identified numeric UID/GID mapping in the container or user namespace.
- [ ] Owner, group, and permission bits of the image tree are preserved or intentionally remapped.
- [ ] Verified traverse permissions for all parent directories.
- [ ] ACL, xattrs, and file capabilities handled according to policy.
- [ ] SELinux/AppArmor policy permits the correct access scope.
- [ ] No overly broad permissions such as `777` or unnecessary root usage.

### Paths and Filesystem

- [ ] Checkpoint tree structure preserved intact.
- [ ] Absolute paths and required working directories recorded.
- [ ] Mount points and volume dependencies prepared at the destination.
- [ ] Symlinks and hard links preserved as required.
- [ ] File mappings, file descriptors, and Unix sockets have a handling plan.
- [ ] Destination filesystem supports the required metadata and behavior.
- [ ] Data, configuration, log, certificate, and native library paths verified.

### Packaging and Security

- [ ] Packaged only after checkpoint completed.
- [ ] Archive/transfer tool preserves required metadata.
- [ ] Checksum and manifest created; signature verified if the workflow requires it.
- [ ] Transport channel and image storage are authenticated, encrypted, and access-restricted.
- [ ] Temporary archives and backups are protected as sensitive data.
- [ ] Image not distributed while it is being modified or restored.

### Restore at Destination

- [ ] Checksum/signature valid before extraction.
- [ ] Owner, permissions, ACL, and security labels verified.
- [ ] Runtime user has read access to the image and access to application resources.
- [ ] Mounts, paths, and external dependencies exist at the correct locations.
- [ ] Restore tested with the correct user and a production-like configuration.
- [ ] Readiness only exposed after the application and dependencies have recovered.

Distributing a CRaC checkpoint involves transferring both the image data and the filesystem and environment assumptions that created it. Preserving UID/GID, permissions, ACL, xattrs, symlinks, mounts, and paths allows the runtime to access the correct data; a manifest, checksum, and secure transport channel verify provenance and integrity; and testing with the correct user/container at the destination proves the image can actually be restored. When these factors are managed together, a checkpoint can be packaged and delivered in a repeatable, secure, and reliable manner.
