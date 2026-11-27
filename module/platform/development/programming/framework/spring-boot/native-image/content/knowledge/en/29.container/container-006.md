# Running as a Non-Root User and Managing Temporary Directory Permissions

## 1. Why Must a Native Image Container Run as Non-Root?

A container rarely needs operating system administrative privileges to serve HTTP requests, read configuration, connect to a database, or process messages. If an application process runs with UID 0, a vulnerability in the application or a library could allow an attacker to perform operations as root inside the container. Running under a dedicated user with least privilege limits the impact if the process is compromised.

Native Image does not eliminate this requirement. A binary produced by GraalVM still runs under the user/group assigned by the container runtime. It still needs to read the executable, libraries, certificates, and configs; and it may need to write temporary files, uploaded files, caches, or application data. If you switch to non-root without preparing permissions on writable directories, the application may fail at startup or on the first request that creates a temporary file.

This lesson belongs to the **Container** chapter of the **SPRING_BOOT_NATIVE_IMAGE** module. The module covers compiling Spring Boot into a GraalVM Native Image with Spring AOT, practicing Maven/Gradle builds, configuring reflection/resources, compatibility testing, container packaging, and operating native builds. This lesson focuses on non-root users and temporary directory write permissions.

After this lesson, learners will be able to:

- Run a native executable with a non-zero UID/GID.
- Configure ownership and permissions for application directories.
- Understand standard `/tmp` permissions and create a dedicated temporary directory.
- Configure `java.io.tmpdir` for a native executable at runtime.
- Run a container with a read-only root filesystem and mount a writable temp volume.
- Configure `securityContext` for Kubernetes.
- Diagnose `Permission denied` errors across Docker, Buildpacks, and Kubernetes.

## 2. UID, GID, and Permissions on Linux

Linux controls file access based on user ID (UID), group ID (GID), supplementary groups, and permission bits. Inside a container, the process's UID/GID determines which files it can read, write, or execute.

| Component | Meaning | Example |
|---|---|---|
| UID | Process user identifier | `10001` |
| GID | Process primary group | `10001` |
| Owner | User owning the file/directory | `10001:10001` |
| Mode | Read/write/execute permissions | `0750`, `0640` |
| Sticky bit | Restricts deleting/renaming other users' files in a shared directory | `1777` on `/tmp` |

Common permissions:

- `r` (read): read a file; on a directory, allows listing entry names.
- `w` (write): write a file; on a directory, allows creating/deleting/renaming entries if other conditions allow.
- `x` (execute): run a file; on a directory, allows traversing/accessing entries when their name is known.
- `0750`: owner has full access, group can read and traverse/execute, others have no access.
- `0640`: owner can read/write, group can read, others have no access.
- `1777`: any user can create files in the directory; the sticky bit prevents users from deleting files they do not own.

The root user (UID 0) holds many special capabilities in Linux. Applications typically do not need them. Grant permissions per directory and function rather than giving administrative privileges to the entire process just to fix a file-write error.

Check user and permissions in a Linux environment:

```bash
id
umask
stat -c '%A %a %U:%G %n' /app /tmp
test -x /app/service && echo "executable"
test -w /tmp && echo "tmp writable"
```

If the image lacks a shell or `stat`, inspect `Config.User` on the image, use debugging tools appropriate for the base image, or add a startup smoke check inside the application. Do not install a shell, package manager, or admin tools into the final image solely for production diagnostics.

## 3. Preparing Application and Writable Directories

A clear layout simplifies permission control:

```text
/
├── app/
│   └── service          # native executable, read/execute only
├── etc/                 # configuration, typically read-only
└── tmp/
    └── app/             # temporary data, writable
```

Principles:

- Place the executable and config files in directories that are read-only for the runtime user.
- Create writable directories only for actual needs, such as `/tmp/app`, upload directories, or spool directories.
- Create directories and set owner/group/mode during image build, before the `USER` instruction.
- Use `COPY --chown` to set ownership on files copied into the final stage.
- Do not assume `WORKDIR` is automatically writable by the application user.
- Prefer logging to stdout/stderr for container runtime collection; if logging to files, create the log directory and grant dedicated permissions.

Docker `COPY` creates files owned by root by default. `USER` only changes the default user for subsequent instructions and the runtime process; it does not retroactively change ownership of already copied files. This is a common reason an executable can be read yet fails to create temporary files or write logs.

## 4. Multi-Stage Dockerfile Running Native Image with a Dedicated UID/GID

The example below illustrates a final image based on Debian slim. Replace the builder image with a GraalVM Native Image builder pinned to a version/digest compatible with your project:

```dockerfile
# syntax=docker/dockerfile:1
FROM <graalvm-native-image-builder> AS build
WORKDIR /workspace

COPY . .
RUN ./mvnw -Pnative native:compile

FROM debian:bookworm-slim AS runtime

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 \
       --home-dir /nonexistent --shell /usr/sbin/nologin app \
    && install -d -o 10001 -g 10001 -m 0750 /app \
    && install -d -o 10001 -g 10001 -m 0700 /tmp/app \
    && chmod 1777 /tmp

WORKDIR /app

COPY --from=build --chown=10001:10001 \
    /workspace/target/service /app/service

ENV TMPDIR=/tmp/app

USER 10001:10001

ENTRYPOINT ["/app/service", "-Djava.io.tmpdir=/tmp/app"]
```

Replace `service` with the actual executable name. If building with Gradle, update the build command and output path accordingly, such as `./gradlew nativeCompile` and `build/native/nativeCompile/<application>`.

Key points in this example:

1. Builder and runtime are separate stages. Compilers, Maven/Gradle caches, and toolchain never enter the final image.
2. User `app` is created with a fixed UID/GID of `10001`; another ID can be chosen per organization policy.
3. `/app` belongs to the application user with mode `0750`; the executable is copied with matching ownership.
4. `/tmp` has mode `1777`, following the standard Linux shared temporary directory convention.
5. `/tmp/app` is accessible only to the application user and serves as a dedicated temp directory.
6. `USER` is placed after directory creation and file copies, so the final process runs non-root.
7. `TMPDIR` serves native libraries/tools that read that environment variable; `-Djava.io.tmpdir` sets the Java system property for the native executable.

If the runtime image lacks `groupadd`, `useradd`, or `install`, use the user and directory creation mechanism supported by the base image, or use a numeric UID/GID with `COPY --chown`. Minimal/distroless images may lack `/etc/passwd` or a shell; verify that the application and libraries do not depend on resolving usernames from the passwd database.

Never use floating builder tags in production pipelines. Pin a version and ideally an image digest for reproducible builds.

## 5. Standard `/tmp` Permissions and Dedicated Temporary Directories

By Linux convention, `/tmp` is a shared temporary directory and normally has mode `1777` (`drwxrwxrwt`). The sticky bit `t` lets multiple users create files while preventing them from deleting or renaming files owned by other users.

Do not change `/tmp` to `0755`: non-root users will be unable to create files. Likewise, avoid `chown -R app:app /tmp`; that alters ownership of other temporary files and breaks the shared directory model. Keep `/tmp` at mode `1777`, then create a dedicated subdirectory owned by the application.

Example:

```bash
install -d -o 10001 -g 10001 -m 0700 /tmp/app
stat -c '%A %a %U:%G %n' /tmp /tmp/app
```

Expected modes:

```text
drwxrwxrwt 1777 root:root /tmp
drwx------ 0700 app:app /tmp/app
```

`0700` is appropriate when only one application UID needs to read/write temp files. If multiple processes in the same group must share the directory, consider `0770` with an appropriate GID and matching umask. Broaden permissions only after identifying which processes need access.

### 5.1. Setting the Java Temporary Directory

Java normally reads the `java.io.tmpdir` system property to determine the default directory for temporary-file APIs. Native Image allows passing `-D` to the executable at **runtime**:

```bash
./service -Djava.io.tmpdir=/tmp/app
```

Distinctions to keep clear:

- `native-image -Djava.io.tmpdir=/tmp/app ...` sets the property for the build/hosted environment; it does not automatically configure the executable's runtime value.
- `./service -Djava.io.tmpdir=/tmp/app` passes the system property when running the native executable.
- `TMPDIR=/tmp/app` is an environment variable commonly used by native code and some OS libraries; do not assume it guarantees `java.io.tmpdir` has the same value.
- In containers, configure the property in `ENTRYPOINT` or the runtime command and verify the actual value via `System.getProperty("java.io.tmpdir")`.

A native executable accepts runtime `-D` options following GraalVM's syntax. Do not rely on `JAVA_TOOL_OPTIONS` as a general configuration mechanism for a native binary; that mechanism is intended for JVM launches, whereas a native executable must receive runtime options directly or through application configuration.

## 6. Running with a Read-Only Root Filesystem

A common hardening measure is mounting the root filesystem read-only. The application can then write only to explicitly provided volumes or tmpfs mounts.

With Docker:

```bash
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m,mode=1777 \
  --cpus=2 \
  --memory=512m \
  -p 8080:8080 \
  my-service:native
```

In this example, `/tmp` is a container-specific tmpfs. The non-root process can create `/tmp/app` and own that directory. If the application needs another temporary path, mount a tmpfs at that exact path and verify the mount's UID/GID/mode.

If the application needs to persist data across restarts, use a dedicated volume with appropriate permissions. Never use `/tmp` to store data that must survive container deletion or replacement.

If `--read-only` is enabled with only `/tmp` mounted, other write paths such as `/var/log/app`, `/app/uploads`, or cache directories will still fail. Ideally configure logging to console, disable file caches or move them to a granted writable directory, and use persistent volumes for durable data.

### 6.1. tmpfs Limits

tmpfs stores contents in host/kernel memory and may use swap depending on system configuration. The `size` limit does not replace the container memory limit. Data written to tmpfs counts toward container/cgroup memory usage, so choose an appropriate size and monitor memory pressure.

Do not set `noexec` if the application or a library genuinely needs to create and execute files inside the temp directory. Typical native executables do not need to run helper binaries from `/tmp`; if a special dependency requires it, verify the requirement before removing `noexec`.

## 7. Running Non-Root with Cloud Native Buildpacks

When using the Spring Boot Maven/Gradle plugin to build images with Cloud Native Buildpacks, the buildpack selects the builder and run images. Popular Paketo stacks run applications as a dedicated non-root user. However, the user ID, group, and base image depend on the stack/run image version; never assume every buildpack or custom run image uses the same UID.

After building the image, inspect the actual user configuration:

```bash
docker image inspect --format '{{.Config.User}}' my-service:native
```

If the output is empty, the Docker image config declares no user and containers may default to root. If the output is a numeric UID or username, verify the actual UID/GID by running the image in an environment with appropriate tools. For images without a shell, shell commands cannot be used for diagnostics; rely on image metadata or an equivalent diagnostic image.

Build the image with Maven or Gradle:

```bash
./mvnw -Pnative spring-boot:build-image
```

Or:

```bash
./gradlew bootBuildImage
```

Buildpacks usually set up a non-root user and application working directory. When changing the run image, adding custom buildpacks, or mounting volumes, re-verify permissions. A volume mount can shadow the contents and ownership of a directory prepared in the image.

If you need to change the UID/GID, use the configuration mechanism provided by the builder/run image in use and check the documentation for that version. Avoid directly modifying buildpack layers or assuming a user named `cnb` exists in every stack.

## 8. Configuring Kubernetes with Non-Root and Writable /tmp

Kubernetes lets you specify user/group and security restrictions at the Pod or container level. The example below runs a native executable as UID/GID `10001`, with a read-only root filesystem and an `emptyDir` mounted at `/tmp`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: native-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: native-service
  template:
    metadata:
      labels:
        app: native-service
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: service
          image: registry.example.com/native-service:1.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: TMPDIR
              value: /tmp/app
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 128Mi
```

In this configuration:

- `runAsNonRoot: true` requires the container not to run as UID 0.
- `runAsUser` and `runAsGroup` define the process UID/GID.
- `fsGroup` adds a group so the process can access volumes that support group ownership.
- `readOnlyRootFilesystem: true` makes the root filesystem read-only.
- `emptyDir` provides scratch write space for the Pod; data lives for the Pod's lifetime, not as persistent storage.
- `sizeLimit` caps the temporary volume size per Kubernetes configuration.

The Dockerfile example above passed `-Djava.io.tmpdir=/tmp/app` in `ENTRYPOINT`, so the manifest sets `TMPDIR=/tmp/app` so native libraries use the same directory. If the image does not preconfigure the property, pass the runtime argument in `ENTRYPOINT` or the container command accordingly. Setting `TMPDIR` in the manifest alone does not prove the Java system property has the same value.

### 8.1. fsGroup and Volume Permissions

`fsGroup` grants the process access to volumes supporting group ownership. How ownership/permissions are applied can depend on the volume type and CSI driver. Not all storage backends behave identically; verify actual permissions inside the Pod.

For large volumes, recursively changing ownership at mount time can slow startup. Kubernetes provides `fsGroupChangePolicy` for certain supported volumes, but this field has no effect on ephemeral volumes like `emptyDir`, `secret`, and `configMap`. Do not add it expecting to alter `emptyDir` permissions.

Do not mount `configMap` or `secret` at paths that need write access. Those volumes are normally provided read-only. If the application must modify contents, copy needed files into a writable `emptyDir` at startup with appropriate logic, or design the application to read configuration read-only.

### 8.2. When the Platform Assigns an Arbitrary UID

Some platforms override the image UID or assign a randomized UID per workload. In that case, a fixed owner `10001` in the Dockerfile may not match the runtime UID. Follow the platform's security policy:

- Identify the actual UID/GID the Pod receives.
- Grant group write/traverse permissions to the group supported by the platform.
- Use `fsGroup` if allowed by the storage driver and policy.
- Avoid making directories world-writable when group sharing suffices.
- Test the image with the environment's actual UID, not only the Dockerfile UID.

Do not assume a single group rule holds across every cluster or OpenShift distribution; consult the deployment platform's documentation and admission policies.

## 9. Checking java.io.tmpdir Inside the Application

A small startup smoke check catches permission errors immediately at boot rather than waiting for the first file upload or file-processing request.

Example using `ApplicationRunner`:

```java
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class TempDirectoryCheck implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) throws Exception {
        String configured = System.getProperty("java.io.tmpdir");
        Path tempDirectory = Path.of(configured);

        if (!Files.isDirectory(tempDirectory)
                || !Files.isWritable(tempDirectory)) {
            throw new IllegalStateException(
                "Temporary directory is not writable: " + tempDirectory
            );
        }

        Path probe = Files.createTempFile(
            tempDirectory, "native-image-check-", ".tmp"
        );

        Files.delete(probe);
    }
}
```

This is an illustrative startup check. In a real application, consider enabling it only in a verification profile or keeping it if temporary file creation is a hard requirement. Never write sensitive data into a probe file. If `java.io.tmpdir` is not passed, the code may receive the runtime default; log the resolved value and verify it points to the expected writable mount.

You can check manually in an environment with a shell:

```bash
id
printf 'TMPDIR=%s\n' "$TMPDIR"
test -d /tmp && test -w /tmp
touch /tmp/native-image-permission-check
rm /tmp/native-image-permission-check
```

If using a dedicated `/tmp/app` path, test that exact path rather than testing only `/tmp`.

## 10. Places Where Spring Boot May Need to Write Temporary Files

Beyond Java's `Files.createTempFile` API, Spring Boot components and integrated libraries may need writable directories:

| Component | Need | Configuration/Check |
|---|---|---|
| Java temporary files | Default JDK temporary files | `java.io.tmpdir` |
| Servlet multipart upload | Temporarily stores uploaded request bodies | `spring.servlet.multipart.location` |
| Embedded Tomcat | Base/work/temp directory in certain configs | `server.tomcat.basedir` |
| File logging | Writing logs to files | `logging.file.name` or log to stdout |
| Cache/file spool | Writing caches, reports, or intermediate files | Dedicated application path |
| TLS/client libraries | Some libraries may create temp truststore/key or scratch files | Check library config and docs |

If you set `spring.servlet.multipart.location=/tmp/app/uploads`, ensure the directory exists or the application can create it. For `server.tomcat.basedir`, use a subdirectory with appropriate permissions. Never enable file logging to a read-only path when running with `readOnlyRootFilesystem`.

Not every Spring Boot application needs all of these paths. Create and mount only directories actually used by your features; verify via upload, TLS, report generation, and corresponding file-handling tests.

## 11. Diagnosing Permission Errors

When a native executable reports a file-write error, identify the exact path and process user before changing permissions.

| Symptom | Common Cause | Resolution |
|---|---|---|
| Permission denied at `/tmp` | `/tmp` is not writable or mount has wrong mode/owner | Check mode `1777`, UID/GID, and mount options |
| No such file or directory when creating temp file | `java.io.tmpdir` points to a non-existent directory | Create the directory in the image or mount the right path |
| Read-only file system | Root filesystem is read-only and write path is unmounted | Mount emptyDir/tmpfs/volume at that path |
| Executable runs but fails to write logs | Log path owned by root or on read-only filesystem | Log to stdout/stderr or create an owned log directory |
| Runs fine in Docker, fails with `--user` | `docker run --user` overrides the image user | Grant ownership/permissions for the overridden UID/GID |
| Works locally, fails in Kubernetes | `runAsUser`, `fsGroup`, volume, or storage driver differs | Inspect security context and permissions inside the Pod |
| Upload fails while health check passes | Multipart location is not writable | Check `spring.servlet.multipart.location` and test uploads |
| Temp directory correct, native library still fails | Library uses `TMPDIR`, custom path, or another requirement | Check environment variables and library documentation |

### 11.1. Inspecting Image and Runtime Configuration

Check the user declared in the image:

```bash
docker image inspect --format '{{.Config.User}}' my-service:native
```

Check which user the running container uses and which mounts are attached:

```bash
docker inspect --format '{{.Config.User}}' my-service-container
docker inspect --format '{{json .Mounts}}' my-service-container
docker top my-service-container
```

If the image includes a shell and diagnostic utilities, you can run checks:

```bash
id
stat -c '%A %a %u:%g %n' /app /tmp /tmp/app
test -x /app/service
test -w /tmp/app
touch /tmp/app/permission-probe
rm /tmp/app/permission-probe
```

Minimal images may lack `sh`, `id`, or `stat`. In that case, do not draw conclusions about permissions merely from missing tools. Use a debug image with the same mounts and security context, or check via code running inside the native process itself.

### 11.2. Checking Kubernetes

Inspect the Pod and its security context:

```bash
kubectl get pod <pod-name> -o yaml
kubectl describe pod <pod-name>
kubectl logs <pod-name>
```

If the container has a shell:

```bash
kubectl exec <pod-name> -- id
kubectl exec <pod-name> -- sh -c 'stat -c "%A %a %u:%g %n" /tmp; test -w /tmp'
```

If a volume mount shadows a directory prepared inside the image, the in-image directory ownership no longer governs access. Inspect the mounted volume, runtime UID/GID, `fsGroup`, and CSI driver policy.

Do not fix errors by changing an entire application directory to `0777` or reverting the container to root. First identify the path being written, the running user, and the specific permission required.

## 12. Security Principles for Temporary Directories

Temporary directories can hold uploads, reports, payloads, or intermediate data. Treat them as potentially sensitive data:

- Use a dedicated application subdirectory with minimal mode, typically `0700`.
- Generate randomized filenames via safe APIs such as `Files.createTempFile`; never concatenate filenames from untrusted input.
- Do not share temp paths across tenants without isolation and access control.
- Delete temporary files upon completion; maintain a cleanup policy for files left behind after crashes.
- Avoid writing credentials, access tokens, or personal data to temp files unless necessary.
- Set size limits on tmpfs/volumes and test behavior when space runs out.
- Keep `/tmp` at mode `1777` if used as a shared directory; never change it to `0777` or change ownership of all of `/tmp`.
- Run as non-root, drop unnecessary Linux capabilities, and disable privilege escalation.
- Keep executables and configs read-only; grant writable mounts only to required paths.

File permissions do not replace input validation. If the application accepts uploads, still enforce size limits, validate content types, authorize access, and avoid using client-controlled paths.

## 13. Non-Root Container Test Matrix

Do not verify only that the container starts. Test operations that actually write files:

| Scenario | Expected Outcome |
|---|---|
| Start container with non-root UID/GID | Process runs with a non-zero UID |
| Read executable and configuration | Required files are readable |
| Read `java.io.tmpdir` | Value points to the intended directory |
| Create/delete temp files | Create, write, and delete succeed |
| File upload | Multipart path is writable and size limits work |
| Report/cache generation | Dedicated path is writable and cleans up properly |
| Logging | Logs go to stdout/stderr or a permitted file path |
| Read-only root filesystem | Application never writes to the root filesystem |
| Container/Pod restart | Temp data follows expected lifecycle rules |
| Volume mount | UID/GID/group permissions work after mounting |
| Temp space exhaustion | Errors are handled gracefully without corrupting business data |
| Shutdown | Process stops and completes cleanup within timeout |

Run the same matrix on the local image and the real deployment environment. Local Docker does not emulate all Kubernetes/OpenShift admission policies, CSI drivers, security profiles, or UID injection.

## 14. Hands-On Exercises

### Exercise A — Convert a Dockerfile to Non-Root

Create a user/group with a dedicated UID/GID, copy the native executable with matching ownership, create `/tmp/app`, and run with `USER`. Verify the process does not have UID 0.

**Completion criteria:** the executable can be read/executed and creates/deletes temp files in its dedicated directory.

### Exercise B — Enable a Read-Only Root Filesystem

Run the image with `--read-only` and mount a tmpfs for `/tmp`. Call an endpoint that creates a temp file or handles an upload. Then remove the `/tmp` mount to observe the error and explain why permissions/read-only filesystems cause it.

**Completion criteria:** the application runs with a read-only root filesystem and writes only to the granted path.

### Exercise C — Deploy to Kubernetes

Configure `runAsNonRoot`, `runAsUser`, `runAsGroup`, `fsGroup`, `readOnlyRootFilesystem`, and `emptyDir`. Verify UID/GID, mount permissions, and temp files from inside the Pod.

**Completion criteria:** the Pod starts, readiness passes, upload/temporary-file endpoints work, and the process does not run as root.

### Exercise D — Inspect Buildpacks

Build an image with `bootBuildImage` or `spring-boot:build-image`. Inspect `Config.User`, verify the runtime user, and check writable directories. Try mounting a volume over an application directory to see how mounts can shadow ownership prepared inside the image.

**Question:** why must permissions still be re-verified after switching the run image or mounting volumes even when Buildpacks uses a non-root user by default?

### Exercise E — Verify Runtime System Properties

Run the native executable with `-Djava.io.tmpdir=/tmp/app`, print the system property value, and create a temporary file. Compare this with setting only `TMPDIR` or passing `-D` only to the `native-image` command at build time.

**Completion criteria:** clearly distinguish build-time properties, runtime properties, and native-library environment variables.

## 15. Pre-Release Checklist

- [ ] Final image declares a non-root user or runtime policy enforces non-root execution.
- [ ] Actual UID/GID is verified; builder user is not assumed to be the runtime user.
- [ ] Executable, configuration, and libraries are readable by the runtime user.
- [ ] Writable directories are created and given ownership/mode before `USER`.
- [ ] Files copied into the final image have appropriate ownership.
- [ ] `/tmp` has mode `1777` if used as a shared temporary directory.
- [ ] Dedicated temp directory has minimal mode and is writable by the runtime user.
- [ ] `java.io.tmpdir` is configured at runtime and verified inside the process.
- [ ] Environment variables such as `TMPDIR` are not confused with Java system properties.
- [ ] Multipart, Tomcat, file logging, and cache paths are checked if used by the application.
- [ ] Root filesystem can be set read-only; writable volumes are mounted at the right paths.
- [ ] Kubernetes security context and volume ownership are tested in the cluster.
- [ ] UID overrides or randomized UIDs are tested if used by the platform.
- [ ] Temp files have size limits, cleanup, and an appropriate data policy.
- [ ] Smoke/integration tests have passed on the final container image.

## References

- [Dockerfile reference — USER and COPY](https://docs.docker.com/reference/dockerfile/): behavior of `USER`, `COPY --chown`, ownership, and permissions in images.
- [Docker build best practices](https://docs.docker.com/build/building/best-practices/): recommendations for running services as non-root users with explicit UID/GIDs.
- [Docker run reference](https://docs.docker.com/engine/containers/run/): default user, `--user`, working directory, and runtime overrides.
- [Paketo — Stacks](https://paketo.io/docs/concepts/stacks/): build/run images and dedicated non-root users in Paketo stacks.
- [Kubernetes — Configure a Security Context for a Pod or Container](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/): `runAsNonRoot`, `runAsUser`, `runAsGroup`, `fsGroup`, `readOnlyRootFilesystem`, and volume ownership.
- [Kubernetes — Application Security Checklist](https://kubernetes.io/docs/concepts/security/application-security-checklist/): guidance on non-root execution, preventing privilege escalation, and read-only root filesystems.
- [GraalVM — Use System Properties in a Native Executable](https://www.graalvm.org/jdk21/reference-manual/native-image/guides/use-system-properties/): distinguishing system properties passed at build time from `-D` options passed at native executable runtime.
- [GraalVM Native Image — Command-line Options](https://www.graalvm.org/dev/reference-manual/native-image/overview/HostedvsRuntimeOptions/): hosted options, runtime options, and system properties.

## Conclusion

Running a Spring Boot Native Image as a non-root user requires preparing both the process identity and the permissions of every path. Create an appropriate UID/GID, copy the executable with matching ownership, keep `/tmp` at mode `1777`, and use a dedicated subdirectory for temporary files. When enabling a read-only root filesystem, mount writable tmpfs/volumes only for paths that genuinely need write access; on Kubernetes, verify `runAsNonRoot`, `fsGroup`, and post-mount volume permissions. Finally, pass `java.io.tmpdir` as a runtime property to the native executable and verify it with real file creation. Once these steps are tested on the final image and deployment environment, the application can run with least privilege while still meeting Spring Boot's temporary storage needs.
