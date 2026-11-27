# Temporary directories, file permissions, and external storage

## 1. Why is the filesystem part of Native Image operations?

Spring Boot Native Image produces a native executable, yet the application still interacts with the filesystem at runtime. Frameworks and libraries may create temporary files, read certificates, write logs, export reports, store uploads, build caches, or extract JNI libraries into a temporary directory. A binary starting successfully does not prove these operations work in a production container.

A common failure occurs when an application runs fine on a developer machine under a privileged user, then fails when the container runs as non-root or mounts its root filesystem read-only. Failures can also appear late—only when a user uploads a file, generates a PDF, runs a migration, or a library needs to unpack a native resource.

In the **SPRING_BOOT_NATIVE_IMAGE** module, explicitly design for three categories of data:

- **Binary and immutable resources**: executable, classpath resources, and libraries shipped with the image; normally require only read/execute permissions.
- **Temporary data**: intermediate files, in-flight uploads, socket files, or extractions; can be deleted once the process exits.
- **Persistent data**: user files, reports, state, or business data; must be stored on an appropriate volume, object storage, or database.

Never use directories in the container's writable layer to store data that must survive container replacement. Containers can be replaced during deploys, rescheduling, or autoscaling.

## 2. Filesystem concepts to distinguish

| Concept | Meaning | Example |
|---|---|---|
| Working directory | Current directory of the process | `/app` |
| Temporary directory | Location for creating temporary data | `/tmp` |
| Classpath resource | Resource packaged with the application | `templates/invoice.html` |
| Runtime file | File mounted or created at runtime | `/var/run/secrets/db-password` |
| Persistent volume | Persists data across container lifecycles | `/var/lib/app-data` |
| Executable permission | Permission allowing a binary/script to run | `chmod +x` |
| Read permission | Permission to read a file or traverse a directory | `r--`, `x` on directory |
| Write permission | Permission to create/delete/modify files | `w` on directory |

Directory permissions differ in meaning from file permissions. To read a file, a process needs read permission on the file plus execute/traverse permission on each parent directory. To create a file inside a directory, the process needs write and execute permissions on that directory.

## 3. Identifying your application's filesystem operations

Before choosing permissions, list every actual filesystem operation:

- Reading classpath templates, schemas, migrations, and message bundles.
- Reading mounted configuration files or secrets.
- Creating temporary files while handling requests.
- Writing logs to stdout/stderr or files.
- Exporting PDFs/CSVs or archives.
- Uploading/downloading files.
- Caching regenerable data.
- JNI libraries unpacking binaries into a temp directory.
- Creating PID files, lock files, or Unix domain sockets if used by the application.

Every path needs an owner, lifecycle, expected capacity, required permissions, and cleanup policy. Do not grant write access to the entire filesystem just because one library needs to write to one directory.

## 4. Temporary directories in Java and Spring Boot

Java provides the `java.io.tmpdir` system property to specify the default temporary directory. You can inspect it at runtime:

```java
System.out.println(System.getProperty("java.io.tmpdir"));
```

Create temporary files with the standard API:

```java
Path tempFile = Files.createTempFile("invoice-", ".tmp");
try {
    // Write or process temporary content.
} finally {
    Files.deleteIfExists(tempFile);
}
```

If a file must be shared across multiple steps or processes, define ownership and cleanup clearly. Never leave temporary files containing sensitive data around indefinitely.

Spring may use `Resource`, `MultipartFile`, upload handling, and third-party libraries. Check where each library creates files; do not assume every library uses `java.io.tmpdir`. Some libraries have their own properties or use the working directory.

## 5. Configuring the temp directory when running a native executable

You can set the temp directory via a system property when launching the executable if the runtime supports that option:

```bash
./api-app -Djava.io.tmpdir=/tmp/app-tmp
```

With Native Image, verify how system properties are passed for your GraalVM Native Image version and how your application launcher handles arguments. You can set `TMPDIR` or configure a library-specific property if the library uses that environment variable.

In a container, create the directory and grant permissions to the runtime user:

```dockerfile
RUN mkdir -p /tmp/app-tmp \
    && chown -R 10001:10001 /tmp/app-tmp
ENV TMPDIR=/tmp/app-tmp
USER 10001
```

You do not need a separate directory if the image/runtime already provides `/tmp` with appropriate permissions. Verify by running the process under the exact target user.

## 6. Unix permissions: owner, group, and mode

Unix permissions cover owner, group, and others. Common bits:

| Bit | File | Directory |
|---|---|---|
| `r` | Read contents | List entry names |
| `w` | Modify contents | Create/delete/rename entries |
| `x` | Execute file | Traverse/search directory |

Example:

```bash
chmod 0555 /app/api-app
chmod 0750 /var/lib/app-data
chown 10001:10001 /var/lib/app-data
```

The binary can be read and executed by the runtime user without being writable. Data directories should belong to the appropriate user/group and grant only necessary permissions.

Mode `0777` is usually overly broad. Prefer explicit owner/group, group permissions when sharing is needed, and an appropriate `umask` so new files are not created with world-accessible permissions.

## 7. Running containers as a non-root user

Containers should run as a non-root user whenever the application does not require system privileges. Example Dockerfile:

```dockerfile
FROM debian:bookworm-slim
WORKDIR /app
COPY --chown=10001:10001 api-app /app/api-app
RUN mkdir -p /tmp/app-tmp /var/lib/app-data \
    && chown -R 10001:10001 /tmp/app-tmp /var/lib/app-data \
    && chmod 0555 /app/api-app
ENV TMPDIR=/tmp/app-tmp
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/api-app"]
```

This is an example. If the data directory is mounted from a runtime volume, `chown` during image build does not change the ownership of the volume mounted over it. Permissions must be configured at the storage/platform layer or via appropriate group ownership.

Verify the process actually runs with the expected UID/GID. Do not look only at `USER` in the Dockerfile, since orchestrators can override user/security context.

## 8. Read-only root filesystem

A read-only root filesystem reduces the chance of a process modifying executables, configurations, or other files inside the image. However, the application may still need to write to specific mounts such as temp, upload staging, or caches.

Design:

- `/app`: holds the executable and immutable files, read-only.
- `/tmp`: `emptyDir` or writable `tmpfs` with an appropriate quota.
- `/var/lib/app-data`: persistent volume if state is needed.
- `/var/run/secrets`: read-only secret/config mounts.
- `stdout`/`stderr`: logging to the container runtime.

Do not enable a read-only root filesystem before identifying every write path. Test file creation, logging, PDF generation, uploads, caching, and JNI extraction flows.

## 9. Configuring a read-only filesystem in Docker

Docker can run a container with a read-only root filesystem and provide a dedicated `tmpfs`:

```bash
docker run --read-only \
  --tmpfs /tmp/app-tmp:rw,noexec,nosuid,size=64m \
  -p 8080:8080 api-app:local
```

`tmpfs` options depend on the Docker host/kernel. If the application needs to execute a native library extracted into temp, `noexec` may block execution of that file; do not drop `noexec` by default. Verify the specific library's requirements, then scope mounts/permissions strictly as needed.

If persistent writes are needed, mount a dedicated volume instead of making the entire root filesystem writable.

## 10. Kubernetes: emptyDir for temporary data

Kubernetes `emptyDir` provides a temporary directory tied to the Pod lifecycle. Data survives container restarts within the Pod but is deleted when the Pod is removed.

Example:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: native-api
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: api
      image: registry.example.com/native-api:1.0.0
      securityContext:
        readOnlyRootFilesystem: true
        allowPrivilegeEscalation: false
      env:
        - name: TMPDIR
          value: /tmp/app-tmp
      volumeMounts:
        - name: temp
          mountPath: /tmp/app-tmp
  volumes:
    - name: temp
      emptyDir:
        sizeLimit: 128Mi
```

This is an illustrative manifest. `fsGroup` behavior depends on the volume driver and Kubernetes configuration. For temporary data needing memory-backed `tmpfs`, you can set `emptyDir.medium: Memory`, provided you set a size limit and account for it in the Pod's memory usage.

## 11. Kubernetes: persistent volumes for data that must persist

If the application must store files beyond the Pod lifecycle, use a `PersistentVolumeClaim` or object storage. Example volume mount:

```yaml
volumeMounts:
  - name: app-data
    mountPath: /var/lib/app-data
volumes:
  - name: app-data
    persistentVolumeClaim:
      claimName: native-api-data
```

The PVC manifest and access modes depend on your storage class. Do not assume a volume can be mounted read-write concurrently by multiple replicas. With multiple instances, consider object storage or storage supporting the corresponding access pattern.

If files are critical business data, design backups, retention, encryption, access control, and recovery. A persistent volume does not automatically replace backups.

## 12. Classpath resources are not writable data directories

Classpath resources typically live inside the executable/JAR or native image. They are meant for reading default templates, schemas, and immutable configuration files.

Never overwrite classpath resources at runtime. Instead:

- Read default templates from the classpath.
- Write outputs to a data directory or object storage.
- Place configuration overrides at an external config path.
- Mount secrets separately at a read-only path.
- Store user uploads in durable storage.

A resource inside a JAR may not map to a modifiable filesystem file. Use streams to read resources; do not rely on `Resource.getFile()` for packaged resources.

## 13. Configuring data paths outside the binary

Expose runtime paths as explicit configuration:

```yaml
app:
  storage:
    temp-dir: ${APP_TEMP_DIR:/tmp/app-tmp}
    data-dir: ${APP_DATA_DIR:/var/lib/app-data}
```

Bind them into configuration properties:

```java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(Path tempDir, Path dataDir) {}
```

At startup, verify the directory exists or create it if policy permits, check readable/writable access, and fail fast if requirements are not met. Do not arbitrarily auto-create directories anywhere; paths must stay within authorized areas.

Paths should come from the deployment environment. The binary can stay identical across staging and production while storage mounts/paths differ.

## 14. File uploads and controlling temporary storage usage

Uploads often require staging files before writing to final storage. Control:

- Maximum request/file size at both gateway and application.
- Capacity of the temp volume.
- Server-generated filenames; never trust client-supplied paths.
- Cleanup when requests fail or cancel.
- Concurrent upload limits.
- Content-type and actual payload validation.
- Antivirus/content scanning if required by the product.
- Retention policies for incomplete files.

If the temp volume fills up, uploads can fail even when the process still has memory. Monitor disk usage, inode usage, and temp file counts. Run a safe cleanup job for expired staging files; never delete files actively in use by another process.

## 15. JNI libraries and temp directories

Some Java libraries package native libraries inside a JAR and extract them into a temporary directory before making JNI calls. In containers:

- The temp path must exist and be writable for the runtime UID.
- If the library must execute the extracted binary, the mount must not block execution.
- The library's architecture and libc must match the binary/container.
- A read-only root filesystem still requires a writable temp mount.
- Cleanup must not delete the library while the process is still using it.

Do not grant execute permission to all of `/tmp` if only one specific directory needs it. Find the library's official property for setting its extraction path; do not assume every library uses `java.io.tmpdir`.

## 16. Logging: stdout/stderr or files?

In containers, prefer logging to `stdout`/`stderr` so the runtime platform collects and forwards logs. If the application writes files:

- Pick a log directory with an explicit writable mount.
- Configure rotation and retention.
- Avoid writing logs into the directory containing the executable.
- Monitor disk usage.
- Never log secrets, credentials, or sensitive data.
- Ensure the log path is writable by the non-root UID.

Do not mount a persistent volume just to store logs if the platform already provides log aggregation. Container log files can be lost when a Pod/container is replaced.

## 17. Umask, ownership, and volume permissions

`umask` restricts default permissions on newly created files. For example, `umask 0027` typically creates files without read/write access for others, depending on the mode requested by the application.

Check permissions inside the container:

```bash
id
umask
pwd
ls -ld /app /tmp /tmp/app-tmp /var/lib/app-data
touch /tmp/app-tmp/permission-check
```

`touch` is a simple check; delete the test file afterward. Run under the exact runtime user—do not test as root and assume a non-root user can also write.

With NFS or CSI volumes, ownership mapping and root-squash can interfere. Handle this at the storage/platform layer; avoid running privileged init containers just to `chmod`/`chown` when safer volume permission configuration is available.

## 18. Capacity, quotas, and cleanup

Temporary directories require size limits. With `tmpfs`, consumed data may count toward container/Pod memory. With disk-backed volumes, track ephemeral storage requests/limits and quotas.

Monitor:

- Bytes used and free.
- Inode/file count.
- Temporary files by age.
- Incomplete staged uploads.
- Disk pressure/eviction events.
- Cleanup failures.
- Temp write latency and I/O errors.

Cleanup should follow naming conventions/metadata and controlled file ages. Never wipe all files in a shared temp directory used by multiple processes or libraries without knowing their lifecycles.

## 19. Common errors

| Symptom | Possible cause | How to check |
|---|---|---|
| `AccessDeniedException` | UID/GID lacks permission on path | Check `id`, owner, mode, and directory traversal |
| `Read-only file system` | Application writes to read-only root filesystem | Identify write path and add dedicated writable mount |
| `No space left on device` | Temp/ephemeral volume full or out of inodes | Check quota, usage, and cleanup |
| Temp file cannot be created | `java.io.tmpdir` or `TMPDIR` wrong/not writable | Print runtime path and test file creation |
| JNI library load fails | Extraction path not writable or `noexec` | Check library docs, temp mount, and ABI |
| Uploads lost after redeploy | Written to container writable layer/`emptyDir` | Move to PVC/object storage |
| Config/secret unreadable | Wrong mount path or permissions | Check mount, UID/GID, and read permissions |
| Binary fails to run | Missing executable bit or wrong architecture | Check file mode and target binary |
| Logs missing | File appender writes to nonexistent path | Use `stdout`/`stderr` or mount log path |
| Fails only when running non-root | Image build created files owned by root | Fix ownership/group in image or volume |

## 20. Pre-release checklist

- Listed every path the application and libraries read and write.
- Binary and classpath resources are treated as immutable.
- Temp directory has explicit path, quota, permissions, and cleanup.
- `java.io.tmpdir`/`TMPDIR` matches the runtime image.
- Process runs under a non-root UID/GID.
- Read-only root filesystem has been tested.
- Writable mounts are granted only to required temp/data paths.
- Persistent data uses appropriate PVC/object storage/database.
- Secret/config mounts are read-only with minimal read permissions.
- JNI extraction paths meet writable/execute requirements.
- Uploads enforce size limits, staging, and cleanup.
- Logging uses `stdout`/`stderr` or a managed volume.
- Disk/inode usage and cleanup failures are monitored.
- Smoke/integration tests run under the exact runtime user and final container image.

## 21. Self-assessment questions

1. Why does a native executable still need a temporary directory?
2. What are the differences between classpath resources, temporary files, and persistent data?
3. How does `java.io.tmpdir` affect Java libraries?
4. Why does write permission on a directory differ from write permission on a file?
5. Which writable mounts does a read-only root filesystem require?
6. How does Kubernetes `emptyDir` differ from a PVC in data lifecycle?
7. Why might a non-root container fail to write to a volume even if the Dockerfile ran `chown`?
8. How can `noexec` affect JNI library extraction?
9. Why should uploads and business files not live only in the container's writable layer?
10. How should you test filesystem behavior under the exact UID/GID and final image?

**Takeaway:** keep the binary and classpath resources immutable; provide a temp directory with appropriate quotas and permissions; place durable data on persistent storage; run as non-root and test a read-only filesystem on the exact final container.
