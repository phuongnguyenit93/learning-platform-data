# User Permissions, Read-Only Filesystems, and Writable Directories

Running a Java application with a read-only filesystem and a non-root user is a way to reduce container privileges. This configuration also makes clear where the application and CRaC need to write data. The JVM may need a temporary directory to extract native libraries or create temporary files; a framework may write caches; the application may create files, logs, or PIDs; and the checkpoint engine needs a place to store checkpoint images and metadata depending on the deployment approach.

With CRaC in containers, access permissions must be designed by resource type. The root filesystem can be read-only while separately mounted volumes remain writable. The user running the JVM must have permission to read the application, write to the exact runtime directories needed, and access checkpoint resources permitted by the platform. Upon restore, the UID/GID identity, mounts, and access permissions must be compatible with the checkpointed state.

There is no need to run the entire container as root just because checkpointing requires special privileges. First separate the application's permissions from the checkpoint/restore runtime's permissions; which additional privileges are needed depends on the kernel, CRIU, container runtime, and Kubernetes cluster policies.

## 1. Why Are Filesystem Permissions Important for CRaC?

Checkpointing saves the state of a running process. Creating and restoring a checkpoint also involve file descriptors, open files, sockets, the working directory, mount namespaces, and the paths used by the process. An application that runs normally in a container with a writable root filesystem may fail when `readOnlyRootFilesystem` is enabled if a library attempts to write to `/tmp`, the current working directory, or the home directory.

Common issues:

- The JVM or a library needs to create temporary files in `/tmp`.
- Native libraries are extracted into `java.io.tmpdir` upon loading.
- A framework writes caches, PID files, lock files, or uploaded files into the installation directory.
- A log appender writes to a file located under the root filesystem.
- The application writes state data into a directory without a volume.
- The checkpoint engine cannot create the checkpoint image because the target directory does not exist or the user lacks write permission.
- Restore fails because the checkpoint image is unreadable, mount paths changed, or the UID/GID no longer has access permissions.

Therefore, clearly identify three groups of paths:

1. **Read-only paths:** JARs, classpath, immutable configuration, libraries, and application files.
2. **Paths the application needs to write:** temp, cache, runtime data, log files, or state files if the application genuinely needs them.
3. **Checkpoint paths:** where the checkpoint engine or orchestration tool writes and reads checkpoint images, metadata, and auxiliary files.

Checkpoint paths may be managed outside the container or mounted into the container, depending on the CRaC/CRIU integration approach. Do not assume that every deployment requires the Java application itself to write the checkpoint image to a fixed directory.

## 2. Running the JVM as a Non-Root User

In a container, the default user may be root if the image does not specify `USER`. Running the application with a dedicated UID/GID limits the impact if the application is exploited or writes files mistakenly.

For example, an image can use UID `10001` and GID `10001` for the Java process. These numbers are examples; choose IDs appropriate for your system's user/group policy.

```dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /opt/app

# Application and immutable directories are owned by the runtime user.
COPY --chown=10001:10001 app.jar /opt/app/app.jar

# Create only the runtime directories that the application actually needs to write to.
RUN mkdir -p /var/lib/myapp /var/cache/myapp /var/log/myapp /tmp \
    && chown -R 10001:10001 /var/lib/myapp /var/cache/myapp /var/log/myapp \
    && chmod 0750 /var/lib/myapp /var/cache/myapp /var/log/myapp \
    && chmod 1777 /tmp

ENV JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=/tmp"

USER 10001:10001

ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
```

In this example:

- The JAR resides under `/opt/app` and only needs read access at runtime.
- The runtime user has write permission to the pre-created data directories.
- `/tmp` has the sticky bit (`1777`) so multiple users can create temporary files without arbitrarily deleting each other's files.
- The JVM uses `/tmp` as the temporary directory.

If deployed with `readOnlyRootFilesystem`, directories that were writable inside the image still become read-only when the container runs with a read-only root filesystem. In that case, writable volumes must be mounted at the exact paths the application needs to use.

### 2.1. UID and GID Must Be Kept Consistent

Permissions on Linux rely on UID, GID, supplementary groups, mode bits, and ACLs. Usernames in `/etc/passwd` are merely a human-readable mapping; the kernel checks the process's numeric IDs.

When checkpointing and restoring, maintain consistent identity:

- Use the same UID/GID for the Java process across runs that need to share a checkpoint.
- Ensure the UID/GID has permission to read the checkpoint image and write to runtime directories.
- If a volume is pre-created, check the actual ownership on the volume, not only `runAsUser` in YAML.
- With rootless containers or user namespaces, distinguish the UID inside the container from the mapped UID on the host.
- Do not assume identical usernames mean identical UID/GID.

A checkpoint created while a process ran under one UID does not automatically grant permission to a restored process running under another UID. Beyond file permissions, the checkpoint engine may also enforce constraints on process credentials, capabilities, and namespaces. Use the same security identity required by the runtime and test on the target cluster.

### 2.2. Directory Permissions and umask

Common mode bits:

| Mode | Meaning | Use case |
|---|---|---|
| `0700` | Only owner reads, writes, accesses the directory. | Checkpoint directory or sensitive data of a single user. |
| `0750` | Owner full access; group reads/accesses; others have no access. | Runtime data directory shared within one group. |
| `0770` | Owner and group read/write/access. | Volume shared among processes in the same group. |
| `1777` | Any user can create files; sticky bit restricts deleting others' files. | Shared `/tmp`. |

For directories, execute permission (`x`) means permission to traverse/search through the directory. A user with read permission on a file but lacking execute permission on a parent directory still cannot access that file.

`umask` determines which permission bits are masked out when creating new files/directories. For example, `umask 027` typically creates new files with at most mode `0640` and new directories with at most `0750`, depending on the mode requested by the program. If umask needs to be set, an entrypoint script can be used:

```sh
#!/bin/sh
set -eu
umask 027
exec java -Djava.io.tmpdir=/tmp -jar /opt/app/app.jar
```

Do not rely on umask to fix permissions of already-existing files. Check volume ownership and modes after mounting.

## 3. Enabling `readOnlyRootFilesystem` in Kubernetes

Kubernetes allows setting `readOnlyRootFilesystem: true` in the container `securityContext`. This setting makes the container's root filesystem read-only. Separately mounted volumes remain writable if the mount does not set `readOnly: true` and the volume type supports writing.

Example Pod with a non-root JVM, read-only root filesystem, and separate writable volumes:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-crac-app
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 20001
    fsGroupChangePolicy: OnRootMismatch
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: example/java-crac-app:1.0
      env:
        - name: JAVA_TOOL_OPTIONS
          value: "-Djava.io.tmpdir=/tmp"
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
      volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: app-state
          mountPath: /var/lib/myapp
        - name: app-cache
          mountPath: /var/cache/myapp
        - name: checkpoint-store
          mountPath: /var/lib/crac
  volumes:
    - name: tmp
      emptyDir: {}
    - name: app-state
      persistentVolumeClaim:
        claimName: java-app-state
    - name: app-cache
      emptyDir: {}
    - name: checkpoint-store
      persistentVolumeClaim:
        claimName: java-crac-checkpoints
```

This is an illustrative skeleton for permissions and mounts. It is not a complete CRaC manifest: checkpoint/restore also requires configuration of the JDK, CRIU, container runtime, kernel, and cluster. The example also does not grant capabilities to CRIU; required privileges depend on how the platform performs checkpointing.

### 3.1. `runAsUser`, `runAsGroup`, and `fsGroup`

| Field | Role |
|---|---|
| `runAsUser` | UID of the process inside the container. |
| `runAsGroup` | Primary GID of the process. |
| `fsGroup` | Supplementary group used for volume access permissions in cases where Kubernetes/volume drivers support managing ownership. |
| `supplementalGroups` | Other supplementary groups that the process belongs to. |
| `runAsNonRoot` | Requires Kubernetes to verify that the container does not run with UID 0. |
| `fsGroupChangePolicy` | Controls when Kubernetes changes volume ownership/permissions, if supported by the volume type. |

`fsGroup` is not a universal permission fix for every filesystem. How it applies depends on the volume type and CSI driver; some CSI drivers handle group ownership themselves or use mount group mechanisms. `hostPath`, NFS with `root_squash`, and some storage backends may require preparing permissions on the node/storage side. Verify actual UID/GID and modes using a test Pod running with the same security context.

### 3.2. Volume Mounts Can Still Be Writable When the Root Filesystem Is Read-Only

`readOnlyRootFilesystem: true` applies to the container's root filesystem. A writable volume mounted at `/tmp` or `/var/lib/myapp` remains writable if:

- The volume supports write operations.
- `volumeMounts` does not set `readOnly: true`.
- The process's UID/GID has permission per mode/ACL.
- SELinux, AppArmor, seccomp, and node policies do not block the operation.

Conversely, mounting a volume with `readOnly: true` makes that path read-only even if the user has write permissions on the volume's underlying filesystem.

## 4. Identifying Which Directories Need to Be Writable

Do not make the entire root filesystem writable merely because you do not yet know where the application writes. Inventory actual runtime paths and mount only the necessary directories.

| Common path | Purpose | Recommended configuration |
|---|---|---|
| `/tmp` | Temporary files, native library extraction, libraries creating temporary files. | Mount `emptyDir`; set `-Djava.io.tmpdir=/tmp`. |
| `/var/tmp` | Temporary files that need to persist longer than `/tmp` by convention of some applications. | Mount only if the application or library actually uses it. |
| `/var/lib/myapp` | Runtime data that needs to persist across restarts. | PVC or volume with appropriate persistence. |
| `/var/cache/myapp` | Regenerable cache. | `emptyDir` if losing the cache does not affect correctness; PVC if there is a clear reason. |
| `/var/log/myapp` | Log files if not writing to stdout/stderr. | Separate log volume; logging to stdout/stderr is generally preferred. |
| `/run` or `/var/run` | PID files, internal sockets, runtime state. | `emptyDir` or memory-backed volume if appropriate. |
| `/var/lib/crac` | Checkpoint image/metadata if the deployment tool requires a path inside the container. | Writable volume with restricted permissions and appropriate storage. |
| `$HOME` | Cache/config of some libraries and tools. | Set `HOME` to an intentional directory or mount separately if writing is needed. |

The list above is a starting point. An application may not need all of these directories. Use error logs, library configuration, system call tracing in a test environment, or filesystem inspection to determine actual write locations.

### 4.1. Configuring the Temporary Directory for the JVM

The JVM uses the `java.io.tmpdir` system property to determine the default temporary directory for several Java APIs and libraries. It can be configured at launch:

```bash
java -Djava.io.tmpdir=/tmp -jar application.jar
```

Some native libraries or subprocesses may read `TMPDIR`, `TMP`, or `TEMP` environment variables instead of `java.io.tmpdir`. If needed, configure them consistently:

```yaml
env:
  - name: TMPDIR
    value: /tmp
  - name: JAVA_TOOL_OPTIONS
    value: "-Djava.io.tmpdir=/tmp"
```

Check whether the application creates temporary files in the home or working directory. Changing `java.io.tmpdir` alone does not automatically redirect all libraries to `/tmp`.

### 4.2. Where Should Logs Go?

In Kubernetes, the straightforward approach is typically writing logs to stdout/stderr for collection by the container runtime and logging system. If using a file appender, mount a separate log directory and grant write permission to the application's UID/GID.

Do not write logs into `/opt/app`, `/`, or the directory containing the JAR when the root filesystem is read-only. If log files must survive Pod recreation, use durable storage or appropriate log shipping; `emptyDir` is not a place for long-term log retention.

### 4.3. Home Directory and Library Caches

Some libraries write by default to `$HOME/.cache`, `$HOME/.config`, or the user directory. When running non-root, home may be `/` or a nonexistent path if the image is not explicitly configured.

Determine the runtime user's `HOME` and set an appropriate directory. Example:

```yaml
env:
  - name: HOME
    value: /var/lib/myapp/home
  - name: XDG_CACHE_HOME
    value: /var/cache/myapp
```

If a library needs to write to those two paths, mount a volume and create the directories with matching ownership/mode. Do not set `HOME=/root` for a non-root process hoping it will be able to access that directory.

## 5. Checkpoint Storage Directory and Volume Lifecycle

A checkpoint image can contain the process's memory state, including sensitive data on the heap. The checkpoint storage directory therefore needs both sufficient capacity and strict access permissions along with an appropriate storage lifecycle.

### 5.1. Choosing Volume Type by Restore Target

| Storage type | Typical lifecycle | When appropriate |
|---|---|---|
| `emptyDir` | Exists for the Pod lifecycle; lost when the Pod is deleted. | Checkpointing and restoring in the same Pod or short tests if supported by the runtime. |
| PVC | Exists independently of the Pod per reclaim policy and storage backend. | Need to retain checkpoints across new Pod creation or coordinate restore to another compatible Pod. |
| `hostPath` | Tied to a specific node's filesystem. | Only when the platform clearly manages node affinity, ownership, and security. |
| External/container runtime storage | Managed by CRIU, runtime, or control plane. | When the platform's checkpoint mechanism requires artifacts outside the container filesystem. |

`emptyDir` usually persists when a container in the same Pod restarts, but is deleted when the Pod is removed from the node. Therefore, do not place a checkpoint meant for a new Pod into `emptyDir` expecting the data to remain after the Pod is replaced.

A PVC also does not automatically guarantee restoring on another node. Check access mode, topology, mount options, filesystem semantics, and how the checkpoint engine uses artifacts. If storage is node-local, the restore Pod may need to be scheduled on the right node.

### 5.2. Checkpoint Directory Permissions

If the deployment tool requires a checkpoint directory inside the container:

- Create the directory before the application runs or use a volume mount at that path.
- Grant write permission to the user/group that the checkpoint process actually uses.
- Restrict read permissions because the image may contain sensitive data.
- Ensure sufficient space and inodes for the checkpoint image and auxiliary files.
- Keep mount paths and directory layout compatible between checkpoint creation and restore.
- Prevent other processes from overwriting or deleting files while restore is using them.

An example of tight permissions for a directory owned by one user could be `0700`. If the checkpoint and restore tools run under a dedicated group, use appropriate group access such as `0750` or `0770` per exact platform requirements. Do not open `0777` to quickly bypass permission errors.

### 5.3. Checkpoint Images Are Sensitive Data

The heap may contain passwords, tokens, sessions, personal data, request payloads, or key material. Therefore, the checkpoint directory must be protected like an artifact containing sensitive runtime data:

- Grant access only to responsible service accounts and operators.
- Use encryption at rest if required by storage/platform.
- Do not publish checkpoint images to public registries or object stores.
- Define retention periods and procedures for deleting old images.
- Do not log paths containing secrets or sensitive content.
- Audit access permissions and checkpoint copy/download operations.

## 6. Filesystem Permissions for CRIU and the Checkpoint Runtime

In many Linux deployments, CRIU participates in process checkpoint/restore. CRIU needs to interact with the kernel and process resources, so it may require capabilities or special privileges depending on the kernel, configuration, and types of resources to checkpoint.

Here is the separation to make:

- **Java application:** needs minimal permissions to read JARs/config, write temp/cache/state, and access dependencies.
- **Checkpoint/restore tool:** may need additional privileges to dump/restore processes, memory mappings, namespaces, file descriptors, and other resources.
- **Container runtime or orchestrator:** may perform part of the checkpoint operation outside the container and manage artifacts separately.

Do not assume that merely running Java as root will make every checkpoint succeed. Conversely, `readOnlyRootFilesystem` and `drop: [ALL]` also do not guarantee CRIU has sufficient privileges. Specific requirements depend on the CRIU version, Linux kernel, container runtime, seccomp profile, LSM, and how Kubernetes integrates checkpoint functionality.

### 6.1. Capabilities and Special Privileges

Some environments may require capabilities such as `CAP_CHECKPOINT_RESTORE`, `CAP_SYS_ADMIN`, or other privileges depending on the operation and kernel/CRIU version. There is no single minimal list valid for every deployment.

Appropriate procedure:

1. Identify whether checkpoint/restore is performed by CRIU inside the container, an external runtime, or a node agent.
2. Read requirements for the exact CRIU, kernel, and container runtime versions.
3. Grant the right capabilities to the right responsible component, per cluster policy.
4. Keep the application running non-root if elevated privileges are not needed.
5. Test both checkpoint and restore under the exact expected security context.

Do not add `privileged: true` or `CAP_SYS_ADMIN` by default merely to bypass errors. If the cluster does not allow the required capabilities, use a platform-supported checkpoint mechanism or request a policy change through cluster administrators.

### 6.2. Seccomp, AppArmor, and SELinux

Traditional Unix permissions are not the only factor. An operation can be blocked by:

- **seccomp:** filters system calls a process is allowed to invoke.
- **AppArmor:** restricts file paths, capabilities, and process behavior per profile.
- **SELinux:** enforces access control based on process and file labels.
- **Mount options:** such as `ro`, `noexec`, `nodev`, `nosuid` can affect how libraries use files or executable mappings.

If checkpoint or restore reports permission denied, identify which syscall/path was blocked and which policy denied it. Do not solve it by disabling all security protections without knowing the actual requirement. With SELinux, volumes need appropriate labels; with AppArmor/seccomp, profiles must allow operations required by the runtime.

## 7. Kubernetes Volume Permissions in Practice

When mounting a PVC or `emptyDir`, files may belong to a different owner/group than the JVM's UID/GID. The Pod `securityContext` can declare `fsGroup`, but the outcome depends on the volume plugin/CSI driver.

### 7.1. Checking Permissions from Inside the Pod

A debug Pod using the same `runAsUser`, `runAsGroup`, `fsGroup`, and mounts can check:

```sh
id
umask
pwd
printf 'probe\n' > /tmp/write-test
printf 'probe\n' > /var/lib/myapp/write-test
printf 'probe\n' > /var/lib/crac/write-test
ls -ld /tmp /var/lib/myapp /var/lib/crac
ls -ln /var/lib/myapp /var/lib/crac
```

The write commands are only tests in a debug environment. Do not run them on a checkpoint directory actively used by the runtime. Use a separate probe file and delete it after checking.

`id` reports the process's UID/GID and supplementary groups. `ls -ln` displays numeric IDs, which is useful when the image and storage do not share the same `/etc/passwd` mapping.

### 7.2. When `fsGroup` Cannot Resolve Permissions

Possible causes include:

- The volume type does not support Kubernetes changing ownership.
- The CSI driver manages mount groups itself.
- The NFS export uses `root_squash` or another user mapping.
- `hostPath` was created with unsuitable owner/mode on the node.
- ACLs or SELinux labels from storage block access.
- Existing files have a mode writable only by the old owner.

In that case, coordinate with storage/cluster administrators to set owner/group/mode or configure the CSI properly. Do not assume an init container running as root can fix every volume type; it is also subject to cluster security policies and may not be permitted.

### 7.3. `fsGroupChangePolicy`

`fsGroupChangePolicy: OnRootMismatch` can reduce startup time when a volume has many files by avoiding recursive ownership changes if the root directory already has matching group/mode. This field only affects volumes for which Kubernetes manages ownership; if a CSI driver handles mount groups, behavior may differ.

With large checkpoint volumes, recursive ownership changes can be time-consuming and generate I/O load. It is better to prepare proper permissions when provisioning the volume or use an appropriate storage mechanism.

## 8. Keeping Paths and Mounts Consistent Between Checkpoint and Restore

A checkpoint can hold file descriptors and references to files or mounts. If the restore environment changes mount namespaces, paths, or backing filesystems, some resources may not restore as expected.

Check:

- Same mount paths for required directories at checkpoint creation and restore.
- Same read/write permissions and appropriate ownership.
- Files that must exist are still present on the corresponding volume.
- Filesystems support the semantics needed by the application or checkpoint engine.
- Sockets/file descriptors are handled via Resource callbacks if peers or files may change.
- The checkpoint image resides on storage that persists throughout the restore process.

Do not treat mounting a PVC with the same name as sufficient. A PVC may be bound to a different filesystem or node, have different mount options, or have data provisioned with a different owner. Verify actual storage before restoring.

## 9. Example Separating Writable Paths in a Pod

The following manifest illustrates separating runtime directories. In the example, the application logs to stdout/stderr, so no separate log volume is needed. The checkpoint PVC is only an example if the runtime requires a checkpoint directory inside the container; replace it with the platform's actual storage mechanism.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: crac-java
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 20001
    fsGroupChangePolicy: OnRootMismatch
  containers:
    - name: java
      image: example/java-crac-app:1.0
      env:
        - name: HOME
          value: /var/lib/myapp/home
        - name: TMPDIR
          value: /tmp
        - name: JAVA_TOOL_OPTIONS
          value: "-Djava.io.tmpdir=/tmp"
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: app-state
          mountPath: /var/lib/myapp
        - name: cache
          mountPath: /var/cache/myapp
        - name: checkpoints
          mountPath: /var/lib/crac
  volumes:
    - name: tmp
      emptyDir:
        sizeLimit: 256Mi
    - name: app-state
      persistentVolumeClaim:
        claimName: myapp-state
    - name: cache
      emptyDir:
        sizeLimit: 512Mi
    - name: checkpoints
      persistentVolumeClaim:
        claimName: myapp-checkpoints
```

Points to adjust before use:

- `runAsUser`, `runAsGroup`, and `fsGroup` must match the owner/group allowed by storage.
- PVCs must be provisioned with access mode, topology, and filesystem matching the restore method.
- `emptyDir.sizeLimit` is an example limit; base it on real needs and the Pod's ephemeral storage quota.
- `readOnlyRootFilesystem` is appropriate only after all writable paths have been identified and mounted.
- `drop: ["ALL"]` is a least-privilege baseline for the application; if the checkpoint runtime requires capabilities, grant them to the right component per platform design rather than enabling privileged for the entire container.
- `HOME` needs an existing and writable directory on the `/var/lib/myapp` volume.

## 10. Permission Troubleshooting Checklist

When the application or checkpoint engine reports `Permission denied`, investigate in order:

1. Identify the exact process failing: JVM, CRIU, container runtime, or node agent.
2. Record the denied syscall or path from relevant logs.
3. Check the actual process's UID/GID and supplementary groups.
4. Check owner, mode, and ACLs of the file and all parent directories.
5. Confirm whether the volume mount is read-only.
6. Check SELinux/AppArmor/seccomp and mount options.
7. Confirm whether the required capability belongs to the application or the checkpoint runtime.
8. Check whether the volume exists, is writable, and is mounted at the same path on restore.
9. Check quota, capacity, and inodes.
10. Test with a minimal Pod having the same security context to isolate storage permissions.

Do not resolve every error by running the container as root or setting `chmod -R 777`. Those approaches can hide root causes and expand write permissions beyond what is necessary.

## 11. Common Misconceptions

**`readOnlyRootFilesystem: true` makes every volume read-only.** Incorrect. Separate volume mounts remain writable if not mounted read-only and permissions permit.

**Mounting `/tmp` alone is enough for a CRaC application to work.** `/tmp` addresses one group of temporary files; the application may also need home, cache, state, logs, or checkpoint storage.

**`fsGroup` always fixes PVC permissions.** Incorrect. Behavior depends on volume type, CSI driver, storage backend, and node policies.

**Running Java as root will solve all CRaC errors.** Root does not guarantee kernel, CRIU, seccomp, mount, or runtime compatibility; it also increases application privileges.

**The checkpoint directory can be placed in `emptyDir` in all cases.** `emptyDir` is lost when the Pod is deleted. If restore happens in a new Pod, storage that lasts long enough or a platform-specific artifact mechanism is required.

**The same UID is enough for restore.** You must also check GID, supplementary groups, capabilities, namespaces, ACLs, SELinux labels, and checkpoint engine permissions.

**Checkpoint images contain only technical, non-sensitive data.** The heap can contain tokens, sessions, personal data, and key material. Protect the image like sensitive data.

## 12. Pre-Deployment Checklist

- [ ] Choose a stable non-root UID/GID for the JVM.
- [ ] Ensure JARs, classpath, and configuration only need read access at runtime.
- [ ] List all paths the application needs to write.
- [ ] Set `java.io.tmpdir` and `TMPDIR` to a writable temporary directory.
- [ ] Direct logs to stdout/stderr or mount a separate log directory.
- [ ] Set `HOME` and cache paths explicitly if libraries need to write.
- [ ] Enable `readOnlyRootFilesystem` after writable paths have been mounted.
- [ ] Verify UID/GID, `fsGroup`, ACLs, and ownership on actual volumes.
- [ ] Identify whether the checkpoint directory is managed by the application, CRIU, runtime, or orchestrator.
- [ ] Use storage with a lifecycle matching where and when restore takes place.
- [ ] Protect checkpoint images with restricted permissions and retention policies.
- [ ] Identify capability, seccomp, AppArmor, and SELinux requirements for the checkpoint runtime.
- [ ] Keep security identity and mount layout compatible between checkpoint and restore.
- [ ] Test writing files, creating temps, checkpointing, and restoring using the exact expected security context.
- [ ] Do not grant `privileged: true` or broader root privileges than verified requirements.

## 13. Terms to Remember

- **Non-root container:** a container running processes with a UID other than 0.
- **`runAsUser` / `runAsGroup`:** the primary UID and GID of processes in a Pod.
- **`fsGroup`:** a supplementary group used by Kubernetes to support volume access permissions when supported by the volume driver.
- **`readOnlyRootFilesystem`:** a setting making the container's root filesystem read-only.
- **Writable mount:** a volume mount allowing a process to write data at a specific path.
- **`emptyDir`:** a temporary volume whose lifecycle is tied to the Pod.
- **PVC:** PersistentVolumeClaim requesting storage with a lifecycle independent of the container/Pod depending on backend configuration.
- **UID mapping:** mapping user IDs between a namespace/container and the host.
- **umask:** a permission mask cleared when creating new files or directories.
- **Capability:** a fine-grained Linux privilege for specific privileged operations.
- **seccomp:** a system call filtering mechanism.
- **SELinux/AppArmor:** additional access control mechanisms for processes and filesystems.
- **Checkpoint image:** data storing process state to serve restore.

Deploying CRaC safely in containers requires combining a non-root user, a read-only root filesystem, and purposeful writable mounts. Separately identify temp, cache, state, log, and checkpoint directories; grant proper UID/GID and group permissions to each volume; and keep storage and mount paths present across the restore workflow. Special privileges needed by CRIU or the container runtime must be identified for the specific environment and granted to the right component, while the Java application continues running with least privilege.

## References

- [Kubernetes — Configure a Security Context for a Pod or Container](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/): `runAsUser`, `runAsGroup`, `fsGroup`, `fsGroupChangePolicy`, capabilities, and `readOnlyRootFilesystem`.
- [Kubernetes — Volumes](https://kubernetes.io/docs/concepts/storage/volumes/): lifecycle and behavior of `emptyDir`, volume mounts, and storage types.
- [Kubernetes — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/): PV/PVC, access modes, and storage lifecycles.
- [CRIU — Documentation](https://criu.org/): Linux process checkpoint/restore requirements and OS resources.
- [CRaC — About CRaC](https://crac.org/about/about-crac/): checkpoint/restore model and coordination requirements between the application and environment.
