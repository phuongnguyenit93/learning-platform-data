# Filesystems, Mounts, and Resources Required at Restore

CRaC (Coordinated Restore at Checkpoint) saves the state of a Java process so that it can be restored in a compatible runtime environment. The heap and execution state can be recovered from the checkpoint image, but filesystems, mounts, volumes, access permissions, and external services still belong to the operating environment.

A Path object stored in the heap is only location information. It does not carry file contents, mount points, access permissions, or any guarantee that the file at that location is still the same file after restore. Similarly, an open file descriptor may depend on the inode, filesystem, mount namespace, and kernel state that the checkpoint/restore runtime must handle.

Therefore, the application must identify required paths and resources, ensure they exist in the restore environment, verify their identity and contents before resuming work, and reopen resources whose lifecycle depends on the operating system.

## 1. Distinguishing the Checkpoint Image from Filesystem Data

A checkpoint image stores process state according to the capabilities of the runtime and the underlying checkpoint mechanism. It should not be viewed as a backup of the host's entire filesystem.

Data can be divided into the following groups:

| Group | Example | Handling at Restore |
|---|---|---|
| State in the heap | Objects, loaded configuration, application offsets, caches | Recovered from the checkpoint image |
| External application files | Input files, output files, logs, manifests | Must remain accessible and be verified |
| Executables and libraries | JARs, native libraries, configs, certificates | Restore environment must provide compatible versions |
| Kernel resources | File descriptors, sockets, locks, pipes, device handles | Depends on checkpoint/restore capabilities and requires checking |
| Mounts and volumes | Bind mounts, PVCs, NFS, tmpfs | Must have suitable topology and permissions in the restore environment |
| Out-of-process services | Databases, object storage, secret managers | Must be ready or have a reconnection procedure |

For example, the application holds:

~~~java
Path dataPath = Path.of("/var/lib/myapp/events.dat");
long savedOffset = 1024 * 1024;
~~~

The checkpoint can save these two values in the heap. However, it does not guarantee that the path **/var/lib/myapp/events.dat** will exist, have the same contents, or be mounted from the same volume after restore.

A safe way to think about it is: the checkpoint restores process state; the deployment system must re-provide the environment and resources that this state needs to continue.

## 2. Absolute Paths, Relative Paths, and the Working Directory

A relative path is resolved against the process's working directory. If the working directory differs between checkpoint and restore, the same path string can point to a different location.

For example:

~~~java
Path path = Path.of("data/events.dat");
~~~

If the process runs with working directory **/opt/service**, the path is interpreted as:

~~~text
/opt/service/data/events.dat
~~~

If restored from a different working directory, the relative path may point to a different file or fail to find the file.

For required resources, use explicit path configuration and specify the working directory in the deployment environment. Relative paths can be converted into absolute paths at initialization:

~~~java
Path configured = Path.of(System.getenv("APP_DATA_DIR"));
Path dataDirectory = configured.toAbsolutePath().normalize();
Path inputFile = dataDirectory.resolve("events.dat");
~~~

toAbsolutePath() only converts the path against the current working directory; it does not confirm that the filesystem or mount will exist after restore. The application still needs to check permissions and file identity.

### Do Not Rely on a Path String as a File Identifier

Two different paths can point to the same file via a symlink or hard link. Conversely, the same path can point to a different file if the file has been replaced.

For example:

~~~text
/var/lib/myapp/current/events.dat
                 |
                 +---- symlink -> /mnt/data/generation-42/events.dat
~~~

After a deployment, the current symlink may be switched to a new generation. The path string remains the same, but the data has changed.

When a file must remain unchanged across a checkpoint, store additional identifying metadata and verify it after restore rather than comparing only the path string.

## 3. Mount Points and Mount Namespaces

A mount point is the location in the directory tree where a filesystem or storage device is attached. A path can access the right data only when the corresponding mount exists in the namespace visible to the process.

On Linux, each process belongs to a mount namespace. Two processes can see different mounts even when running on the same host. Containers typically use their own mount namespace and map volumes from the host to paths inside the container.

For example:

~~~text
Host:
  /srv/volumes/customer-data

Container:
  /var/lib/myapp/data
       |
       +---- bind mount from host /srv/volumes/customer-data
~~~

The application only knows the path inside the container. Upon restore, ensure the container or recovery environment has the corresponding mount at **/var/lib/myapp/data**.

Checking only that the directory exists is not enough. If the mount is missing, the path may still exist as an empty directory on the root filesystem. The application could accidentally write data to the container's writable layer instead of the intended volume.

### Checking Mounts on Linux

Some commands that assist with inspection:

~~~bash
findmnt
findmnt -T /var/lib/myapp/data
cat /proc/self/mountinfo
df -h /var/lib/myapp/data
stat /var/lib/myapp/data
~~~

- findmnt -T shows the filesystem containing the path.
- /proc/self/mountinfo describes the mounts visible in the current mount namespace.
- df displays filesystems and disk space.
- stat provides metadata of a file or directory.

These commands only observe state at the time they run. Run them in the exact container or namespace that the restored process will use, rather than checking only on the host.

### Mount Topology Must Be Compatible

Some checkpoint/restore runtimes may need to restore file descriptors or kernel state tied to a mount. Changing the mount namespace, mount order, filesystem, or paths can cause restore to fail or cause the application to access the wrong data.

Specific requirements depend on the CRaC JDK, CRIU, kernel, container runtime, and deployment setup. Follow the guidelines of the runtime in use and keep the required topology stable.

## 4. Persistent Volumes and Ephemeral Storage

Not all filesystems have the same lifecycle.

| Storage Type | Example | Risk After Restore |
|---|---|---|
| Persistent volume | Long-lived attached disk, cloud block volume, PVC | Can retain data, but requires attaching and mounting the right volume |
| Host bind mount | Host directory mounted into container | Depends on host path and mount namespace |
| Container writable layer | Container-specific filesystem layer | Can be lost when the container is replaced |
| tmpfs | /run, some /tmp setups, memory-backed volumes | Contents may not exist after creating a new environment |
| Kubernetes emptyDir | Ephemeral volume tied to Pod lifecycle | Not persistent storage across creation of a new Pod |
| Network filesystem | NFS, SMB, EFS, CephFS | Requires consistent network, mounts, permissions, and semantics |
| Object storage | S3-compatible, cloud object store | Not a POSIX filesystem; requires client and credentials |

### Persistent Volumes

For data that must persist across restore, use storage with a durable lifecycle and a clear attach/mount procedure.

Verify:

- The right volume or claim is attached.
- The filesystem is mounted before the runtime needs to restore file descriptors.
- The path inside the container matches the application's configuration.
- UID/GID, ACLs, and mount options allow access.
- Sufficient space remains.
- Data contents correspond to the checkpoint generation.

Having the same PVC name or volume name is not enough to prove the data comes from the same volume. Check the storage provider's ID or metadata when correctness depends on volume identity.

### tmpfs and Temporary Directories

/tmp is not persistent storage by default. It may be tmpfs or cleared when the container/host restarts. Java may also use java.io.tmpdir for temporary files.

If the application needs temporary files across restore, identify the actual filesystem and its lifecycle. Typically, temporary files should be regenerated from persistent data or recreated in afterRestore() rather than assuming old contents still exist.

### Kubernetes

In Kubernetes, distinguish:

- PersistentVolumeClaim: request for persistent storage.
- PersistentVolume: provisioned storage resource.
- emptyDir: ephemeral storage whose lifecycle is tied to the Pod.
- hostPath: depends on the filesystem on the node.
- CSI volume: depends on the storage provider's driver and attach/mount workflow.

When restoring inside the same Pod, some volumes may remain mounted. If a new Pod is created or moved to another node, conditions may differ. Do not assume the checkpoint image carries PVCs, emptyDir, hostPath, or volume data with it.

Let orchestration ensure that volumes are attached and mounted before launching restore. Only after that should the JVM be instructed to restore the checkpoint.

## 5. Access Permissions and User Identity

A file that exists still cannot be used if the process lacks read or write permission.

Attributes to consider:

- UID and GID of the process.
- Owner and group of the file/directory.
- POSIX permission bits.
- POSIX ACLs.
- SELinux labels or AppArmor policies.
- Mount options such as ro, rw, noexec, nodev, nosuid.
- Umask and default permissions when creating files.
- Access permissions on parent directories.

To open a file by path, a process generally needs search/execute permission on parent directories and appropriate read/write permission on the file. Having permissions on the file without directory traversal permission can still result in AccessDeniedException.

### Checking Permissions on Linux

~~~bash
id
namei -l /var/lib/myapp/data/events.dat
ls -ld /var/lib/myapp /var/lib/myapp/data
ls -l /var/lib/myapp/data/events.dat
getfacl /var/lib/myapp/data/events.dat
~~~

In an environment with SELinux, you may need to check the corresponding context and policies. Do not resolve errors by disabling SELinux or setting 777 permissions on an entire directory. Grant minimal permissions to the exact user/group and mount.

### UID/GID in Containers

A container may run with a different UID/GID than the host. A file owned by UID 1000 on the host may be inaccessible to a container process running as UID 10001 if group permissions or ACLs do not allow it.

When using Kubernetes securityContext, runAsUser, runAsGroup, and fsGroup can affect volume permissions. Check the behavior of the CSI driver and storage provider; not every filesystem applies ownership in the same way.

## 6. Symlinks, Hard Links, and File Identity

A path may contain a symlink. If the symlink changes between checkpoint and restore, the application may open a different file without realizing it.

You can check symbolic links:

~~~java
if (Files.isSymbolicLink(path)) {
    Path target = Files.readSymbolicLink(path);
}
~~~

To obtain the path after resolving symlinks:

~~~java
Path realPath = path.toRealPath();
~~~

toRealPath() requires the path to exist and may throw IOException if the target is inaccessible. It checks the target at the time of the call but does not lock the target to prevent subsequent changes.

You can read BasicFileAttributes:

~~~java
BasicFileAttributes attributes = Files.readAttributes(
    path,
    BasicFileAttributes.class
);

long size = attributes.size();
FileTime modified = attributes.lastModifiedTime();
Object fileKey = attributes.fileKey();
~~~

fileKey() may be null, and its stability depends on the filesystem/provider. Do not use fileKey() alone as a portable ID across hosts or mounts. Combine metadata with checksums, generation IDs, or the application's manifest.

If preserving the exact file is required, verify the exact data object before reopening and avoid race conditions between checking and using it. When supported by the filesystem, open the file and read attributes from the opened handle itself to reduce the risk of the path being replaced between operations.

## 7. File Descriptors and Open Handles

Java streams, channels, and RandomAccessFile typically hold an underlying file descriptor or native handle. That descriptor references kernel state, not merely a path string.

For example:

~~~java
FileChannel channel = FileChannel.open(
    Path.of("/var/lib/myapp/events.dat"),
    StandardOpenOption.READ,
    StandardOpenOption.WRITE
);
~~~

A channel may hold:

- Current read/write position.
- Open state of the file.
- Reference to the file object in the kernel.
- Associated lock or mapping state.
- Buffers and state of outer Java wrapper classes.

Whether a file descriptor can be checkpointed/restored depends on the descriptor type and the runtime. A file descriptor for a regular file may be handled differently from a socket, pipe, device, or special filesystem. Do not assume every handle will recover automatically and correctly.

### Close-and-Reopen Strategy

For many applications, an easy-to-control approach is:

1. Stop new read/write operations.
2. Complete the in-progress batch or record.
3. Flush writers and force data if needed.
4. Save the committed offset alongside file metadata.
5. Close the channel before checkpoint.
6. After restore, reopen the path.
7. Verify file identity, size, and contents.
8. Reset the offset and resume.

This approach avoids relying on the runtime to restore certain old handles. However, if the checkpoint is aborted, the original process also needs to reopen the channel. When the application calls Core.checkpointRestore(), it can catch CheckpointException to perform rollback. Do not use afterRestore() as a rollback callback for an aborted checkpoint.

### Memory-Mapped Files

MappedByteBuffer maps a file region into the process address space. Restoring the mapping depends on the filesystem, file identity, offset, size, and the runtime's mapping handling capabilities.

Do not automatically assume an old mapping remains valid if the file was replaced or truncated. For data requiring guarantees, close/release the mapping according to API/runtime capabilities, reopen the file, and verify before resuming. Some mapping APIs have limitations around explicit unmapping; check the JDK documentation and implementation details.

## 8. File Locks and Data Ownership

Java provides FileLock via FileChannel:

~~~java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {

    // Exclusive operation region according to filesystem semantics.
}
~~~

A file lock may be advisory on some operating systems/filesystems. It is not a distributed lock with uniform guarantees across all storage systems.

Across checkpoint and restore, a lock may depend on the file descriptor, inode, or network filesystem semantics. If multiple replicas are restored from the same image, each replica might believe it holds the same checkpointed lock state. The system must verify the actual behavior of the runtime and filesystem.

For work requiring mutual exclusion across multiple instances:

- Use a database lease or a distributed lock with a fencing token.
- Use a lock file on a filesystem only if the filesystem supports the required semantics and has been tested.
- Clearly identify who owns the file and when the lease expires.
- Do not rely solely on synchronized or ReentrantLock, as they only coordinate threads within a single JVM.
- Do not open multiple writers without a coordination mechanism.

If a lock is released before checkpoint, define how to reacquire the lock after restore. If the checkpoint is aborted, the original process needs to restore ownership according to the application's policy.

## 9. Network Filesystems and Remote Mounts

A network filesystem such as NFS, SMB, EFS, or CephFS can provide POSIX paths while still depending on the network, server, client cache, leases, and mount options.

After restore, consider:

- Are network interfaces and routes ready yet?
- Does DNS resolve the endpoint correctly?
- Is the remote storage server operational?
- Is the mount attached in the right namespace?
- Are credentials, Kerberos tickets, or secrets still valid?
- Are file locks and leases still valid?
- Does the client cache return stale data?
- Has the mount entered a stale or hung state?

Not every network filesystem error can be resolved by retrying file open. Some I/O operations may hang according to kernel timeouts or mount options. Set timeouts at the application layer if the API supports it, and keep readiness false while required storage is not yet ready.

### Checking Filesystem Type and Mount Options

You can inspect the filesystem and options with:

~~~bash
findmnt -T /mnt/shared-data -o TARGET,SOURCE,FSTYPE,OPTIONS
~~~

For example, the same path /mnt/shared-data may be mounted via NFS in one environment and via local disk in another. If the application depends on NFS semantics or file locking, comparing paths alone is insufficient.

### Object Storage Is Not a POSIX Mount

S3-compatible object storage is typically accessed through an SDK/API. If FUSE is used to mount object storage, semantics for rename, locking, consistency, and random writes may differ from a POSIX filesystem.

With object storage, store the object key and version/ETag per the service contract. After restore, recreate the client, load credentials, and verify the object's version or checksum. Do not assume file rename or file locking behaves like a local disk.

## 10. Configuration Files, Secrets, and Certificates

An application may read the following files after startup:

- application properties or YAML.
- truststore and keystore.
- TLS certificates and private keys.
- credentials or tokens.
- native library configuration files.
- mapping files or model data.
- files containing feature flags or endpoints.

If values were already read into the heap before checkpoint, restore may continue using the old copy in memory even though the file on disk has changed. If the resource needs to be refreshed, re-read it after restore according to application policy.

For certificates and secrets:

- Verify that the file exists and has minimal permissions.
- Do not log secret contents.
- Verify the certificate chain, validity period, and truststore.
- Consider that credentials may be rotated during the checkpoint window.
- Recreate TLS clients if a client holds an old SSLContext or connection pool.
- Do not assume secret files are remounted with the same version if the secret provider performs rotation.

If the application requires a specific configuration version, store the version or generation ID alongside the checkpoint state. After restore, check whether the current version is compatible before using it.

## 11. Native Libraries, Devices, and Operating System Resources

Some applications use JNI/JNA or native libraries to access resources outside the Java heap:

- .so or shared libraries.
- Unix domain sockets.
- Named pipes.
- Device files such as /dev/....
- Shared memory.
- GPU or accelerator handles.
- File descriptors created by native code.
- Native threads and mutexes.

These resources may not be restored in the same way a normal Java object is restored. Support depends on the runtime, CRIU, kernel, drivers, and native libraries.

Before choosing CRaC, inventory native resources and determine:

1. Is the resource directly supported by checkpoint/restore?
2. If not, can it be closed before checkpoint and recreated after restore?
3. Is there an explicit close/destroy API?
4. Does it depend on a device or driver present only on a single host?
5. Does the shared library need to be reloaded or the native context reinitialized?
6. Can the resource be recreated before workers use it?

For example, a native client should have a Java wrapper implementing Resource. beforeCheckpoint() closes the native handle; afterRestore() creates a new handle. Do not retain an old native pointer and assume it remains valid after restore.

### Unix Domain Sockets and Device Files

A Unix domain socket path may still exist on the filesystem while the corresponding server socket or connection is no longer active. A file path does not prove the endpoint is listening.

After restore, recreate the client socket or reconnect to the service. For device files, confirm that the device node, driver, permissions, and container privileges are still provided.

## 12. Disk Space, Inodes, and File Descriptor Limits

The filesystem may exist yet lack sufficient resources to continue.

Check:

- Available disk space.
- Available inodes.
- User/project quotas.
- Open file descriptor limits (ulimit -n or RLIMIT_NOFILE).
- File size limits.
- Memory mapping limits.
- Number of temporary files and log files.
- Separate disk space for checkpoint images versus application data.

On Linux:

~~~bash
df -h /var/lib/myapp
df -i /var/lib/myapp
ulimit -n
cat /proc/self/limits
~~~

If the application opens many files after restore, it may hit descriptor limits even though every file exists. Close old handles, limit concurrent open files, and monitor for Too many open files errors.

Do not store checkpoint images on the same filesystem as critical data if doing so could cause checkpoints to exhaust disk space. Reserve separate capacity and configure alerts before it fills up.

## 13. Verifying Resources with Java Before Opening Service

You can create a component that checks required paths:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.List;

public final class RequiredFileValidator {
    private final List<Path> requiredFiles;

    public RequiredFileValidator(List<Path> requiredFiles) {
        this.requiredFiles = List.copyOf(requiredFiles);
    }

    public void validate() throws IOException {
        for (Path path : requiredFiles) {
            if (!Files.exists(path)) {
                throw new IOException(
                    "Required path does not exist: " + path
                );
            }

            if (!Files.isReadable(path)) {
                throw new IOException(
                    "Required path is not readable: " + path
                );
            }

            BasicFileAttributes attributes =
                Files.readAttributes(
                    path,
                    BasicFileAttributes.class
                );

            if (!attributes.isRegularFile()) {
                throw new IOException(
                    "Expected a regular file: " + path
                );
            }
        }
    }
}
~~~

This is a simple example. For directories, mount points, sockets, or devices, check the corresponding resource type instead of requiring every path to be a regular file.

Files.exists() can return false when the state is indeterminate or access is denied. It also does not verify the right volume or the right contents. A production validator should additionally check:

- Whether the resolved path lies within an allowed directory.
- Whether the file identity or volume ID matches.
- Whether the size and checksum are correct.
- Whether the filesystem type and mount source are suitable.
- Whether the file can be opened in the exact mode the application requires.
- Whether temporary files can be created, written, flushed, and deleted if the workload needs write access.

### Checking Write Permission with a Temporary File

Files.isWritable() is a preliminary check; it does not guarantee subsequent write operations will succeed. When write permission must be confirmed, you can create a temporary file in the target directory and then delete it:

~~~java
Path probe = Files.createTempFile(dataDirectory, ".restore-check-", ".tmp");

try {
    Files.writeString(probe, "ready");
} finally {
    Files.deleteIfExists(probe);
}
~~~

Perform this probe only in a directory where the application is permitted to write and ensure the filename does not conflict. If data is sensitive, use harmless test content and do not write secrets.

## 14. Resource Callbacks for Closing and Reopening Files

CRaC provides the Resource interface:

- beforeCheckpoint(): handles resources before creating a checkpoint.
- afterRestore(): recreates or verifies resources after restore.

A Resource managing a file can close the channel before checkpoint and reopen it after restore.

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class FileResource implements Resource {
    private final Path path;

    private FileChannel channel;
    private long savedOffset;
    private boolean closedForCheckpoint;

    public FileResource(Path path) throws IOException {
        this.path = path.toAbsolutePath().normalize();
        open();
        Core.getGlobalContext().register(this);
    }

    private void open() throws IOException {
        channel = FileChannel.open(
            path,
            StandardOpenOption.READ,
            StandardOpenOption.WRITE
        );
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // The caller must drain the writer and flush buffers first.
        channel.force(true);
        savedOffset = channel.position();

        channel.close();
        channel = null;
        closedForCheckpoint = true;
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        reopenAndRestorePosition();
    }

    public synchronized void reopenAfterAbortedCheckpoint()
            throws IOException {
        if (closedForCheckpoint) {
            reopenAndRestorePosition();
        }
    }

    private void reopenAndRestorePosition() throws IOException {
        FileChannel reopened = null;

        try {
            reopened = FileChannel.open(
                path,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE
            );

            if (savedOffset < 0 || savedOffset > reopened.size()) {
                throw new IOException(
                    "Saved offset is outside the current file"
                );
            }

            reopened.position(savedOffset);
            channel = reopened;
            reopened = null;
            closedForCheckpoint = false;
        } finally {
            if (reopened != null) {
                reopened.close();
            }
        }
    }
}
~~~

This example assumes the application owns the file and has drained all write operations. In practice, also save file identity, size, generation, and checksum. Do not only check that the offset is within bounds; verify that the file still contains the data the application expects.

If beforeCheckpoint() closes the channel but the checkpoint is aborted, the original process continues. When the application calls Core.checkpointRestore(), it can catch CheckpointException and call reopenAfterAbortedCheckpoint(). afterRestore() applies only to a process that is actually restored.

If the checkpoint is requested externally via jcmd, the business flow has no catch block around the API call. Design resources and operational procedures appropriate for that trigger mechanism.

## 15. Verifying Mounts and Volumes Before Restore

Required mounts should be verified before invoking the restore command, without waiting until the application begins processing requests.

A general operational sequence:

~~~text
Prepare node / container
        |
        v
Attach volume or mount filesystem
        |
        v
Verify mount namespace and mount source
        |
        v
Verify UID/GID, ACL, and mount options
        |
        v
Verify files, configs, secrets, and native dependencies
        |
        v
Start restore from checkpoint image
        |
        v
Resource.afterRestore()
        |
        v
Reopen files / clients / handles
        |
        v
Verify data and readiness
        |
        v
Open request listeners and workers
~~~

If the runtime needs access to file descriptors or mounts while recovering process state, the mount must be ready prior to the restore step. The afterRestore() callback cannot fix a condition that the runtime needs from the very first stage.

### Example Inspection Commands in a Linux Container

~~~bash
id
findmnt -T /var/lib/myapp/data
df -h /var/lib/myapp/data
df -i /var/lib/myapp/data
namei -l /var/lib/myapp/data/events.dat
test -r /var/lib/myapp/data/events.dat
test -w /var/lib/myapp/data
~~~

Run the commands inside the exact container or mount namespace that will perform the restore. If orchestration creates a new container, run the check after volumes have been mounted into the new container.

## 16. Compatibility Checks Between Checkpoint and Restore Environments

Not every environmental difference causes restore to fail. However, the following changes must be evaluated:

| Component | Change That Can Cause Problems |
|---|---|
| Path | Working directory or absolute path changed |
| Mount namespace | Missing mount point or points to a different volume |
| Filesystem | Filesystem type or mount options changed |
| Volume | Wrong volume attached, different volume generation |
| Permissions | Different UID/GID, ACL, or SELinux context |
| File identity | Path points to a new file or different symlink |
| File content | File modified, truncated, or rotated |
| Native library | Different .so version or loader path |
| Device | Different device node, driver, or container permissions |
| Network mount | DNS, route, credentials, or remote server not ready |
| Resource limit | Insufficient file descriptors, inodes, quota, or disk space |

Record an environment manifest when creating a checkpoint, containing the information needed for comparison. The manifest does not need to contain secrets; store only safe identifiers or versions.

For example:

~~~text
checkpointGeneration = image-2026-11-13-001
applicationVersion   = 4.2.1
dataVolumeId         = volume-abc123
dataMountPath        = /var/lib/myapp/data
filesystemType       = ext4
dataFormatVersion    = 7
requiredConfigVersion= 18
nativeLibraryVersion = 2.4
~~~

The values above are illustrative only. Depending on the storage provider, the volume ID can be obtained from the storage management API or metadata provided by the deployment system.

## 17. When the Filesystem Changes While the Application Is Checkpointed

A checkpoint may exist for a long time before restore. During that time, external data may change.

The application should define a policy by data type:

| Data Type | Policy |
|---|---|
| Image-immutable configuration file | Require matching version or hash |
| Append-only input file | Verify processed prefix, then resume from offset |
| Exclusive output file | Verify committed region, handle tail according to rules |
| Rotated logs | Identify the exact generation/file identity |
| Rotated secrets or certificates | Re-read the new version if policy permits |
| Shared directory | Use locks/leases or a coordination protocol between writers |
| Object storage | Check object version/ETag and recreate the SDK client |

Do not automatically overwrite or truncate files that differ from the checkpointed state. If the file identity or checksum does not match, keep the application not ready and apply a clear reconciliation policy.

## 18. Common Errors and How to Handle Them

### Path Exists but Volume Mount Is Missing

The mount point directory may still exist on the root filesystem. The application opens the path but mistakenly reads the container's writable layer.

How to handle: inspect the mount source, filesystem type, and volume identity using operating system tools. Do not rely solely on Files.exists().

### Volume Is Not Yet Attached When Restore Starts

The runtime or callback needs to access a file, but the volume is not ready yet.

How to handle: orchestrate attach/mount before invoking restore. Use a readiness gate so traffic is not opened until the volume is verified.

### Permissions Differ After Restore

The process has a different UID/GID or the storage provider applies different ACLs.

How to handle: verify user, group, ACLs, SELinux labels, and mount options. Grant minimal required permissions.

### Path Is Identical but Data Differs

A symlink, bind mount, or volume was switched to a different generation.

How to handle: compare volume ID, file identity, version, size, and checksum. Do not compare only the path string.

### Network Filesystem Is Stale or Disconnected

The mount still appears present, but I/O fails or hangs due to the remote server/network.

How to handle: verify network and storage server, set appropriate timeouts, retry with bounds, and keep the application not-ready when required data is inaccessible.

### File Lock Is No Longer Valid

The lock depends on a file descriptor or filesystem semantics; after restore it may not represent current ownership.

How to handle: reacquire the lease/lock using an out-of-process protocol and use a fencing token if needed to prevent an old owner from continuing to write.

### File Descriptor or Native Handle Cannot Be Restored

The handle type is not supported by the runtime or kernel.

How to handle: close before checkpoint and recreate after restore if an API is available. If the resource cannot be recreated or is unsupported, change the design or deployment environment.

### Out of Disk Space or Inodes

The file still exists, but new write operations fail.

How to handle: check df -h, df -i, quotas, and space reserved for checkpoint images. Open write services only after confirming sufficient resources.

## 19. Designing Readiness Around Required Resources

Do not mark an application as ready solely because the JVM restored successfully. The application needs a readiness state that reflects the resources the workload actually requires.

For example:

~~~text
RESTORING
    |
    v
CHECKING_MOUNTS
    |
    v
CHECKING_FILES
    |
    v
REOPENING_HANDLES
    |
    v
CHECKING_DEPENDENCIES
    |
    v
STARTING_WORKERS
    |
    v
READY
~~~

If a step fails:

~~~text
Any verification step
          |
          v
        FAILED
          |
          v
Keep request gate closed
          |
          v
Retry with limit or report error to orchestration
~~~

Resources can be categorized into:

- **Required:** cannot serve if missing, such as the primary data volume or mandatory certificates.
- **Optional:** a feature can be disabled while the application keeps running, such as a regenerable cache directory.
- **Rebuildable:** can be recreated from another data source, such as caches or index files.

Clear categorization avoids halting the entire application over a rebuildable cache while also preventing it from continuing to run when the primary data volume is missing.

## 20. Implementation Workflow

### When Preparing a Checkpoint

1. List all paths, mounts, volumes, native libraries, devices, and network filesystems required by the application.
2. Classify resources as required, optional, and rebuildable.
3. Stop new work and drain operations using files.
4. Flush and force data requiring durability.
5. Save offsets, file identity, volume generation, and appropriate checksums.
6. Close channels, locks, or native handles if adopting a recreate-after-restore strategy.
7. Record an environment manifest without secrets.
8. Complete the beforeCheckpoint() callback once components are safe.

### Before Restore

1. Prepare the proper node, container, and mount namespace.
2. Attach volumes and mount required filesystems.
3. Verify volume ID, mount source, filesystem type, and mount options.
4. Verify UID/GID, ACLs, SELinux/AppArmor, and access permissions.
5. Provide configs, secrets, certificates, and native libraries of the right version.
6. Check disk space, inodes, quotas, and descriptor limits.
7. Invoke restore only when mandatory runtime resources are ready.

### After Restore

1. Keep the request gate closed.
2. Reopen files, sockets, or native handles that need recreation.
3. Verify file identity, version, size, checksum, and offset.
4. Recreate clients for network filesystems or object storage.
5. Reacquire leases/locks per the application protocol.
6. Verify dependencies and readiness.
7. Start workers before opening traffic.

### When a Checkpoint Is Aborted

If the application calls Core.checkpointRestore(), catch CheckpointException and reopen the closed handles in the original process. Re-verify files and mounts before continuing. If rollback fails, keep the application not-ready.

If the checkpoint is requested externally via jcmd, the business flow does not catch an exception via the API. A corresponding operational procedure is needed to detect checkpoint failure and recover resources.

## 21. Principles to Remember

- A checkpoint image is not a backup of the entire filesystem or volume.
- A path in the heap does not guarantee the file or mount still exists after restore.
- Verify mounts inside the exact namespace that the restored process will see.
- Distinguish persistent volumes from container writable layers, tmpfs, and emptyDir.
- Keep UID/GID, ACLs, SELinux/AppArmor, and mount options appropriate.
- Verify volume identity and file identity; a path string is not enough.
- Do not assume all file descriptors, locks, sockets, devices, or native handles are safely restored.
- For critical files, save the committed offset and metadata; reopen and verify before resuming.
- Network filesystems require verifying network, server, leases, credentials, and filesystem semantics.
- Secrets, certificates, and native libraries must have compatible versions and appropriate access permissions.
- Prepare mandatory mounts before invoking restore if the runtime needs them to recover process state.
- Open the request gate only when all required resources are ready.
- Test restore on the exact container, node, filesystem, and storage provider of the deployment environment.

Restore capability does not depend solely on the checkpoint image. The process also needs to see the right filesystem, mounts, volumes, permissions, and operating system resources to continue its work. By preparing mounts before restore, verifying identity and contents after restore, and recreating handles that cannot be safely kept, the application can detect incompatible environments early and avoid writing corrupted data or serving traffic before required resources are ready.