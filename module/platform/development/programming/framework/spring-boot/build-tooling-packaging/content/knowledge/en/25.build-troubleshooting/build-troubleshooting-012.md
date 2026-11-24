# Diagnosing Docker Daemon, Buildpacks, Image Architecture, and File Permission Errors

When building or running a Spring Boot container image with **Cloud Native Buildpacks (CNB)**, an error that looks like “Docker build failed” can originate from multiple layers: the Docker client failing to reach the daemon; the daemon failing to pull builder/run images; buildpacks failing to detect or build the application; the image built for a different CPU architecture; or a non-root process unable to read/write files and volumes.

To fix it properly, first identify **which stage failed and which component returned the error**. This lesson guides diagnostics across Docker Engine, the Spring Boot Maven/Gradle plugin, the CNB lifecycle, image platforms, and UID/GID and filesystem permissions.

Examples use Spring Boot 3.3, Java 17, and the hypothetical image `registry.example.com/team/diagnostic-app:1.0.0`. Shell commands assume Linux/macOS unless Windows/PowerShell is specified. Prefer read-only status commands before changing configuration.

## 1. Identifying Which Layer Owns the Error

Image creation and execution flow:

```text
Maven / Gradle command
        |
        v
Spring Boot build plugin
        |
        v
Docker client configuration
(context, host, TLS, socket)
        |
        v
Docker daemon / Engine
        |
        +------------------------------+
        |                              |
        v                              v
Pull CNB builder image           Pull CNB run image
        |                              |
        +---------------+--------------+
                        |
                        v
               CNB lifecycle + buildpacks
              analyze -> detect -> restore
                    -> build -> export
                        |
                        v
               OCI application image
                        |
                        v
             Docker daemon / registry
                        |
                        v
                  Container runtime
                        |
                        v
          Process user + filesystem + mounts
                        |
                        v
                Spring Boot application
```

| Symptom | Layer to Investigate First |
| --- | --- |
| `Cannot connect to the Docker daemon` | Docker daemon, context, socket, network |
| `permission denied ... docker.sock` | Docker socket access permissions |
| `failed to pull builder/run image` | Registry auth, DNS, TLS, network |
| `no buildpack groups passed detection` | Source artifact, builder, and buildpack detection |
| `failed to launch` | Launch process, run image, application configuration |
| `no space left on device` | Docker host disk/inodes/cache |
| `no matching manifest` | Image architecture/platform |
| `exec format error` | Binary/script wrong architecture or format |
| `Permission denied` while app runs | User, file mode, ownership, or mount |
| `Read-only file system` | Read-only root filesystem or mount |
| `ImagePullBackOff` | Runtime registry pull, image reference, credentials, or platform |

Record the full command, exit code, first error, and most recent phase. A Docker socket error is not fixed by switching buildpacks; a volume UID error is not fixed by re-pulling the builder.

## 2. Checking the Docker Daemon Before Running Buildpacks

The Spring Boot Maven/Gradle plugin needs access to a **Docker-compatible daemon** to run the builder and create the image. The Spring Boot Maven plugin can read Docker CLI configuration to locate the current context; if it cannot obtain context/connection details, it falls back to the default local connection. The plugin also supports explicit host, context, and TLS configuration.

### 2.1. The First Three Commands

```bash
docker version
docker info
docker context ls
```

How to read them:

- `docker version` displays **Client** and **Server** sections. If Client appears yet Server is missing or errors on connect, focus on the daemon/connection.
- `docker info` verifies daemon responsiveness and reports storage driver, architecture, and rootless/security options.
- `docker context ls` lists daemon endpoints selectable by the Docker CLI.

If `docker version` cannot retrieve the Server section, do not run Maven/Gradle Buildpacks yet. Fix the Docker connection path first.

### 2.2. Context and Environment Variables

The Docker CLI can use a different context than the local daemon. Check:

```bash
docker context show
docker context inspect "$(docker context show)"
env | grep -E '^(DOCKER_HOST|DOCKER_CONTEXT|DOCKER_CONFIG|DOCKER_TLS_VERIFY|DOCKER_CERT_PATH)='
```

| Variable | Effect |
| --- | --- |
| `DOCKER_CONFIG` | Docker CLI config/context directory; usually defaults to `$HOME/.docker` |
| `DOCKER_CONTEXT` | Selects context; in the Spring Boot Maven plugin, this overrides `DOCKER_HOST` when resolving context |
| `DOCKER_HOST` | Docker daemon endpoint, e.g., Unix socket or TCP host |
| `DOCKER_TLS_VERIFY` | Enables TLS verification when using HTTPS/TLS connections |
| `DOCKER_CERT_PATH` | Client certificate/key directory when TLS is enabled |

A common mistake is a developer switching to a remote Docker context to build elsewhere, leaving `DOCKER_CONTEXT` or `DOCKER_HOST` set in CI/terminal. The Docker CLI and Spring Boot plugin may then talk to different daemons.

To use the default local context, clear unintended overrides in that shell/job and re-check `docker context show` and `docker info`. Do not delete global configuration before checking whether other projects depend on it.

### 2.3. Checking the Docker Daemon Endpoint

On Linux, the local endpoint is normally the Unix socket `/var/run/docker.sock`. Rootless Docker normally uses a socket in the user runtime directory, e.g., `unix:///run/user/<uid>/docker.sock`. Docker Desktop on Windows normally uses a named pipe/context managed by Desktop; WSL2 may require Docker Desktop WSL integration.

If using a TCP daemon, confirm hostname/IP and port, that the daemon is listening, firewall/network routes permit runner access, TLS client certificates/CAs are right, and the identity is authorized. Never expose an unauthenticated Docker API publicly for “quick testing”: the Docker API holds root-equivalent control over the daemon host.

### 2.4. Docker Socket Permission Errors

Example message:

```text
permission denied while trying to connect to the Docker daemon socket
unix:///var/run/docker.sock
```

This is a **host/runner** socket permission error occurring before the CNB builder starts. On Linux:

```bash
id
ls -l /var/run/docker.sock
stat -c '%U %G %a %n' /var/run/docker.sock
```

Compare the process user/group against the socket's owner/group. Docker normally grants socket permissions to `root` and a configured group. Adding a user to the `docker` group grants effectively root-equivalent privileges on the host; do so only per runner governance policy with full awareness of security impact. After changing group membership, a new session is required for permissions to take effect.

For rootless Docker:

```bash
systemctl --user status docker
printf '%s\n' "$DOCKER_HOST"
docker context show
```

Do not assume the rootless socket resides at `/var/run/docker.sock`.

**Do not fix socket errors by running all of CI as root or enabling privileged containers.** Identify the right daemon/socket and grant least-privilege access to the runner identity.

### 2.5. Docker Desktop and Windows/WSL

On Windows PowerShell:

```powershell
docker version
docker info
docker context ls
$env:DOCKER_HOST
$env:DOCKER_CONTEXT
$env:DOCKER_CONFIG
```

If the CLI cannot reach the daemon:

1. Check whether Docker Desktop has finished starting.
2. Check that the context and Linux/Windows engine match the image.
3. If running in WSL2, verify WSL integration is enabled for that distribution.
4. Check for stale environment variables left over from an old terminal/session.
5. Inspect Docker Desktop diagnostics/service logs if the CLI cannot retrieve Server information.

Spring Boot CNB images are typically Linux containers. Docker Desktop needs the Linux engine/VM active to run Linux builder/run images; Windows container mode prevents Linux builders from running.

## 3. Distinguishing Daemon Errors from Registry/Network Errors

Once the Docker daemon works, check whether it can pull the builder and run images.

```bash
docker pull paketobuildpacks/builder-jammy-base:latest
```

Run this only if the project actually uses that builder. Get the **actual builder name** from Maven/Gradle configuration or build logs; do not pull an arbitrary image and assume the project is configured correctly.

| Error | Likely Cause | Check |
| --- | --- | --- |
| `unauthorized` / `401` | Missing/wrong registry credentials | Username/token and pull permissions |
| `denied` / `403` | Identity lacks repository read permission | Repository ACL, namespace |
| `manifest unknown` | Wrong image name/tag/digest | Builder/run image reference |
| `x509: certificate signed by unknown authority` | Docker host does not trust registry CA | Daemon/registry CA/TLS |
| `no such host` | DNS resolution failure | DNS resolver/network |
| `i/o timeout` | Firewall/proxy/route or slow registry | Network from Docker host |
| `no space left on device` | Daemon storage out of space | Disk/inodes/cache |

**The Docker daemon pulls the builder/run images**; once the builder container starts, the builder itself may need to download buildpack dependencies, JDKs, Maven/Gradle artifacts, or metadata. The builder container's network path can differ from the Docker daemon's network path. Thus `docker pull` succeeding does not guarantee every buildpack download will succeed.

### 3.1. Proxy and CA Inside the Builder Container

If logs show the builder failing to download artifacts from a Maven repository or vendor endpoint, identify the failing request's hostname. You may need to configure `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` for the buildpack environment per builder docs. Spring Boot plugins allow passing environment variables into the builder; Paketo Java buildpacks honor proxy variables.

Maven fragment example:

```xml
<image>
    <env>
        <HTTP_PROXY>http://proxy.corp.example:8080</HTTP_PROXY>
        <HTTPS_PROXY>http://proxy.corp.example:8080</HTTPS_PROXY>
        <NO_PROXY>localhost,127.0.0.1,.corp.example</NO_PROXY>
    </env>
</image>
```

This is an illustrative fragment, not a complete POM. Replace proxy/hosts with real configuration. Never place proxy usernames/passwords directly in the POM or logs. If a private CA must be trusted inside the builder, install certificates using the binding/CA trust mechanism supported by the builder; Docker daemon trust does not automatically ensure processes inside the builder share the same trust store.

### 3.2. Which Component Performs Which Download?

| Download | Executing Component | Check |
| --- | --- | --- |
| Builder image | Docker daemon | Docker pull, daemon logs, registry auth |
| Run image | Docker daemon/lifecycle per flow | Image reference, registry auth, daemon network |
| Buildpack/JDK/dependencies | Process inside builder | Builder logs, proxy, DNS, CA, repository config |
| Application image push | Docker daemon/plugin publish flow | Target registry, publish credentials, write permissions |

When seeing timeouts, do not rotate credentials before knowing which host the request is targeting.

## 4. Diagnosing Spring Boot Plugins and CNB Builders

### 4.1. Maven and Gradle Commands

Maven:

```bash
./mvnw -B -ntp -e spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.com/team/diagnostic-app:1.0.0
```

The `spring-boot:build-image` goal is suitable for direct CLI invocation; it forks a lifecycle to ensure the `package` phase runs. If binding the goal to the lifecycle, use `build-image-no-fork` per configuration.

Gradle:

```bash
./gradlew bootBuildImage --stacktrace --info \
  --imageName=registry.example.com/team/diagnostic-app:1.0.0
```

The commands above illustrate local image creation. Pushing requires separate publish options/configuration. During diagnostics, do not enable verbose/debug logs on runners holding secrets without redaction; Maven `-X` and Gradle `--debug` can print sensitive configuration details.

### 4.2. Builder and Run Images

The CNB builder image holds the buildpacks and lifecycle used to detect/build the app. The run image supplies the runtime base for the application image. Spring Boot plugins choose a default builder if unconfigured; builder metadata usually specifies a compatible run image.

You can override builder/run images:

```xml
<image>
    <builder>paketobuildpacks/builder-jammy-base:latest</builder>
    <runImage>paketobuildpacks/run-jammy-base:latest</runImage>
</image>
```

This is a fragment. In production, pin builder/run images to approved versions or digests rather than mutable `latest` tags. Never pick an arbitrary builder and run image just because both pull cleanly.

**Builder and run images must match in stack/lifecycle/mixins.** Swapping in a run image from a different stack or missing components needed by launch layers can fail the build or create an unlaunchable image.

### 4.3. Pull Policy and Cache

Spring Boot Maven plugin supports pull policies for builder/run images: `ALWAYS`, `NEVER`, and `IF_NOT_PRESENT`.

| Policy | Behavior | When to Use |
| --- | --- | --- |
| `ALWAYS` | Always attempt to pull image from registry | Need to verify connectivity or fetch referenced version |
| `IF_NOT_PRESENT` | Use local image if present, otherwise pull | Normal development with managed tags/versions |
| `NEVER` | Do not pull; require image locally | Offline builds with pre-staged images/caches |

If using `NEVER` while the builder is absent locally, the build fails even if the registry has the image. If using mutable tags with `IF_NOT_PRESENT`, the local cache may retain a stale builder. When suspecting a mismatch, inspect local image IDs/digests and pull policies instead of wiping all caches immediately.

### 4.4. Reading CNB Lifecycle Logs

The CNB lifecycle has five build phases in order:

1. **Analyze:** reads metadata/layers of the previous image and checks registry access to prepare for the new build.
2. **Detect:** buildpacks evaluate whether the app matches and generate a build plan.
3. **Restore:** restores eligible cached layers based on metadata from Analyze and the build plan from Detect.
4. **Build:** buildpacks process sources/artifacts and generate build/launch layers.
5. **Export:** assembles layers and exports the OCI image.

**Launch is the runtime step after Export:** the launcher is the OCI image entrypoint and starts the selected process when the container runs; it is not a sixth build phase.

Failures by stage point to causes:

- Analyze failure: cannot read previous image metadata, registry denies access, or invalid prior image reference.
- Detect failure: unrecognized application artifact, builder lacks a suitable buildpack, or incompatible buildpack version.
- Restore failure: corrupted or unreadable cache/layer metadata/volume.
- Build failure: missing JDK/dependencies, buildpack bug, proxy/DNS/CA, or source configuration.
- Export failure: Docker storage, layer write, permissions, or disk space.
- Launch/runtime failure: launcher, process type/start command, run image, or incompatible runtime config.

### 4.5. Inspecting Builders and Images

If Pack CLI is installed:

```bash
pack inspect-builder paketobuildpacks/builder-jammy-base:latest
pack inspect-image registry.example.com/team/diagnostic-app:1.0.0
```

Substitute the actual builder/image references. `pack inspect-image` displays the run image, buildpacks, process types, and metadata of a Buildpacks-built image. If Pack CLI is unavailable, use Docker image inspection and Spring Boot plugin logs; there is no need to install extra tools just to run one command if the environment already provides sufficient evidence.

### 4.6. Common Detection Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `no buildpack groups passed detection` | Builder found no matching buildpack group | Confirm JAR/WAR was built and builder includes Java buildpacks |
| No executable archive found | Wrong build goal/source artifact | Run `package`/`verify`, inspect target JAR |
| Unsupported Java version | Java version outside buildpack support | Choose supporting builder/buildpack or compatible Java version |
| Dependency download fails | Builder network/proxy/repository | Check failing hostname, proxy, CA, and Maven repository |
| Run image/stack mismatch | Builder and run image incompatible | Use the run image from builder metadata or an approved pair |
| Export/cache write fails | Docker storage/volume/permissions | Inspect daemon disk, cache volumes, and logs |

With Maven, `spring-boot:build-image` ensures `package` runs before building the image. With Gradle, `bootBuildImage` depends on the matching executable archive task. If the source archive is wrong, fix build outputs before changing builders.

## 5. Diagnosing CPU Architecture and Image Platforms

An image can build successfully on a developer's machine yet fail on production nodes due to **OS/CPU architecture incompatibility**.

| Platform | Target |
| --- | --- |
| `linux/amd64` | Linux x86-64, common on Intel/AMD servers |
| `linux/arm64` | Linux ARM 64-bit, e.g., ARM servers/Apple Silicon VMs |
| `windows/amd64` | Windows containers on x86-64 |
| `linux/arm/v7` | Linux ARM 32-bit variant |

Spring Boot JARs containing Java bytecode are normally portable across architectures, yet the **JRE, native libraries, OS packages, and run image** are platform-specific. Java bytecode does not turn a Linux AMD64 run image into an ARM64 image.

### 5.1. Checking Machine and Image

On Linux/macOS:

```bash
uname -m
docker info --format '{{.OSType}}/{{.Architecture}}'
docker image inspect --format '{{.Os}}/{{.Architecture}}' \
  registry.example.com/team/diagnostic-app:1.0.0
```

Common outputs for `uname -m` are `x86_64` or `aarch64`. `docker image inspect` shows the platform of the image built/pulled locally.

On Windows PowerShell:

```powershell
$env:PROCESSOR_ARCHITECTURE
docker info --format '{{.OSType}}/{{.Architecture}}'
docker image inspect --format '{{.Os}}/{{.Architecture}}' registry.example.com/team/diagnostic-app:1.0.0
```

Compare the image's OS/architecture against the Docker daemon and deployment nodes. Apple Silicon Macs can run AMD64 images via emulation; a build passing on a developer's laptop does not prove native ARM64 support.

### 5.2. Inspecting Remote Multi-Platform Manifests

If an image is published and may contain multiple platform manifests:

```bash
docker buildx imagetools inspect registry.example.com/team/diagnostic-app:1.0.0
```

This displays the manifest/index and platforms published to the registry; it requires Docker Buildx and registry read access. If only `linux/amd64` exists while production nodes are ARM64, the runtime may report `no matching manifest for linux/arm64`.

`docker image inspect` locally usually shows the platform of the image already pulled into that daemon. To inspect all platforms in a remote manifest list, use a registry index tool like `buildx imagetools inspect`.

### 5.3. Distinguishing Architecture Errors

| Error | Symptom | Resolution |
| --- | --- | --- |
| `no matching manifest for linux/arm64` | Registry lacks the platform required by the node | Publish a multi-platform image or build separately for that platform |
| `exec format error` | Binary/entrypoint mismatches architecture/format | Inspect image architecture, binary, and shebang |
| Native library load fails | Native dependency wrong architecture/ABI | Rebuild native layer for target platform |
| Image runs slowly on ARM laptop | Running an AMD64 image under emulation | Use a native ARM64 image if builder/run image supports it |

Do not assume Maven/Gradle `bootBuildImage` shares the same `--platform` flag behavior as `docker run`/Buildx. `docker run --platform linux/amd64` only asks the runtime to select that platform and may invoke emulation; it **does not** convert an already-built image to ARM64 and does not replace CNB-supported multi-architecture build/publish workflows.

### 5.4. Designing Releases for Multiple Architectures

- Choose builders and run images supporting each target platform.
- Build/test on native runners for each architecture when possible.
- If using emulation, validate compatibility; never treat emulation as a full substitute for native testing.
- Create multi-platform manifests/indexes using CNB/registry-supported processes and verify them.
- Inspect the remote manifest before deploying.
- Test on at least one real node/runner for every published architecture.

## 6. User Permissions and File Ownership in CNB Images

Spring Boot documentation notes that images built with Buildpacks **build and run as non-root users for security reasons**. This is intentional. An application writing files to a root-only path may build cleanly yet fail once the container runs.

First determine the **actual process user** inside the image:

```bash
docker image inspect --format '{{.Config.User}}' \
  registry.example.com/team/diagnostic-app:1.0.0
```

The value may be a UID, `UID:GID`, or username depending on the image. Do not assume every CNB image uses UID `1000` or `10001`; inspect the actual image metadata. In minimal images lacking a shell/coreutils, do not assume `sh`, `id`, or `ls` exist.

### 6.1. Basic POSIX Permissions

| Bit | File | Directory |
| --- | --- | --- |
| `r` | Read contents | List filenames |
| `w` | Modify contents | Create/delete/rename entries (also depends on directory permissions and filesystem) |
| `x` | Execute file | Traverse directory |

Examples:

- `0644`: owner read/write; group and others read.
- `0640`: owner read/write; group read; others no access.
- `0755`: owner read/write/execute; group/others read/execute.
- `0700`: only owner can read/write/traverse.

A file with mode `0644` is still unreadable if a parent directory denies traverse permission to the process. A directory with `r` but lacking `x` is also insufficient to access files inside it.

### 6.2. Checking UID/GID and Modes on the Host

On Linux:

```bash
id
stat -c '%u:%g %a %n' ./data
stat -c '%u:%g %a %n' ./data/*
namei -l ./data
```

- `id` reports the current process UID/GID.
- `stat` displays numeric owner, group, and permission mode.
- `namei -l` displays permissions along every component of the path.

On macOS, `stat` syntax differs; use `stat -f '%u:%g %Lp %N' path`. On Windows, host permissions are governed by NTFS ACLs and Docker Desktop file-sharing translation; inspect with `Get-Acl` or `icacls`.

Do not rely solely on usernames. The kernel evaluates access using numeric UID/GID and ACLs; two containers with identical usernames yet different numeric UIDs may still fail to access the same volume.

### 6.3. Bind Mounts Preserve Host Ownership

Example:

```bash
mkdir -p ./data
docker run --rm \
  -p 127.0.0.1:18080:8080 \
  --mount type=bind,source="$PWD/data",target=/data \
  registry.example.com/team/diagnostic-app:1.0.0
```

The container sees the host directory at `/data`. If the host directory is owned by `root:root` with mode `0755`, a non-root CNB process generally cannot create files there. Errors may surface as `java.nio.file.AccessDeniedException` or `Permission denied`.

How to resolve:

1. Determine the actual image UID/GID and host directory owner.
2. Choose appropriate ownership/group for the application data.
3. Grant proper read/write/traverse permissions to the process or authorized group.
4. Verify with a container run.
5. Document the permission policy for deployment environments to prevent recurrence.

Never use `chmod -R 777` as a blanket fix. It opens write access to all users and introduces data tampering/deletion risk.

### 6.4. Named Volumes vs. Bind Mounts

| Mount Type | Initial Ownership | What to Check |
| --- | --- | --- |
| Bind mount | Taken from host directory/file | Host UID/GID, ACL, mode, SELinux label if enabled |
| Docker named volume | Managed by Docker; contents may initialize from image on first mount | Owner/mode of volume data, stale existing volumes |
| Kubernetes PVC | Storage driver/CSI and security context cooperate | `fsGroup`, volume driver, access mode |
| `tmpfs`/`emptyDir` | Per runtime/orchestrator and mount options | Writable paths, quotas, lifecycle |

Named volumes do not automatically guarantee non-root processes can write all data. Pre-existing volumes from earlier runs can retain old owners/modes. Inspect the volume and data initialization before changing permissions.

### 6.5. Rootless Docker and UID Mapping

Rootless Docker runs the daemon/containers in a user namespace and maps container UIDs/GIDs to host IDs. The UID shown inside a container does not necessarily equal the UID on the host filesystem.

If a bind mount fails with permission errors on a rootless engine:

- Verify the right rootless daemon/context.
- Review UID/GID mapping per Docker documentation.
- Check host path ownership under the user running the daemon.
- Do not assume `chown 1000:1000` on the host always maps to UID `1000` inside the container.
- Test on a dedicated, recoverable data directory before altering production permissions.

## 7. Distinguishing Permission Denied, Read-Only, and No Space

These three errors require different fixes:

| Error | Meaning | What to Check |
| --- | --- | --- |
| `Permission denied` / `EACCES` | Process lacks access rights | UID/GID, mode, ACL, parent directories |
| `Read-only file system` / `EROFS` | Filesystem/mount is read-only | `readOnlyRootFilesystem`, bind mount flags, volume |
| `No space left on device` / `ENOSPC` | Out of blocks, inodes, or quota | Disk, inodes, Docker storage, volume quota |

### 7.1. Container Running with a Read-Only Root Filesystem

A container may be configured with `readOnlyRootFilesystem: true`. The app cannot write to the root filesystem even when the directory is owned by the right user. That is `EROFS`, not `EACCES`.

Design writable paths explicitly:

- Persistent data: dedicated volume mount, e.g., `/data`.
- Temporary files: `emptyDir`/`tmpfs` or an appropriate `/tmp` mount.
- Logs: prefer stdout/stderr for runtime collection.
- Caches: verify whether persistence is truly needed and set quotas/lifecycles.

Do not disable read-only root filesystems just to hide errors when the app can use dedicated volume/temp paths.

### 7.2. Checking Docker Disk Space

Status commands:

```bash
docker system df
docker system df -v
df -h
df -i
```

`docker system df` shows space used by images, containers, local volumes, and build caches. `df -h` checks blocks; `df -i` checks inodes on Linux. A filesystem can still have gigabytes free while out of inodes.

Do not run `docker system prune -a --volumes` reflexively. Pruning can delete needed images/caches/volumes; check resources, ownership/lifecycles, and backups before cleanup. Buildpacks rely on cache volumes for speed; deleting them forces subsequent builds to re-download layers.

### 7.3. OOM and Resource Limits

If the builder/container exits abruptly or the exit code indicates OOM:

- Check memory limits on Docker Desktop/VM/runner.
- Check daemon logs and Linux kernel OOM events.
- Check container memory usage/limits.
- Distinguish CNB builder OOM from Spring Boot runtime OOM.
- Size resources appropriately for the workload; do not increase indefinitely or strip all limits.

Memory used by the builder/lifecycle differs from the runtime application heap.

## 8. Diagnosing File Permissions When Java Code Writes Data

Suppose an app writes files to a directory configured via `APP_DATA_DIR`. Code should accept the path explicitly and surface errors clearly so logs show the cause:

```java
package dev.example.diagnostic;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DataFileProbe {

    private DataFileProbe() {
    }

    public static Path writeProbe() throws IOException {
        String configured = System.getenv()
                .getOrDefault("APP_DATA_DIR", "/data");

        Path directory = Path.of(configured).toAbsolutePath().normalize();
        Files.createDirectories(directory);

        Path file = directory.resolve("permission-probe.txt");
        Files.writeString(
                file,
                "write-ok" + System.lineSeparator(),
                StandardCharsets.UTF_8
        );

        return file;
    }
}
```

This is a standalone Java 17 class, not a complete Spring Boot application. You can call `DataFileProbe.writeProbe()` in a controlled startup check or integration test. If you do not want the app to create directories itself, require the mount path to exist and fail with a clear log message.

Check:

- Is `APP_DATA_DIR` set to the right path inside the container?
- Is the directory mounted?
- Does the process UID/GID have traverse and write permissions?
- Is the mount `ro` or the filesystem read-only?
- Does the directory have enough space/inodes?
- Are SELinux/AppArmor/storage policies blocking access?
- On Kubernetes, does the volume driver support ownership changes via `fsGroup`?

Never log secrets or actual data file contents during diagnostics.

## 9. Kubernetes: `runAsNonRoot`, `fsGroup`, and Volume Permissions

When running in Kubernetes, the runtime security context can alter user/group and filesystem permissions compared to local Docker.

Pod fragment example:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: diagnostic-app
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 2000
    fsGroupChangePolicy: OnRootMismatch
  containers:
    - name: app
      image: registry.example.com/team/diagnostic-app:1.0.0
      ports:
        - containerPort: 8080
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      volumeMounts:
        - name: app-data
          mountPath: /data
        - name: app-tmp
          mountPath: /tmp
  volumes:
    - name: app-data
      emptyDir: {}
    - name: app-tmp
      emptyDir: {}
```

This is an example security context that must be cross-checked against the actual image and storage driver. `runAsUser: 1000` is illustrative only; pull the actual UID/GID from image metadata and check cluster policies. `fsGroup: 2000` sets the supplemental group on volumes supporting `fsGroup`; it does not change the process UID.

`fsGroupChangePolicy: OnRootMismatch` can shorten ownership-change time on large volumes by updating only when the root volume's owner/mode mismatches. This field applies only to volume types supporting `fsGroup`; CSI drivers may handle mount groups themselves. Secrets, ConfigMaps, and `emptyDir` each have their own behavior/limits.

### 9.1. When a Pod Reports Permission Denied

Fetch status and events:

```bash
kubectl describe pod diagnostic-app
kubectl get pod diagnostic-app -o wide
kubectl logs diagnostic-app --all-containers=true --tail=200
```

If the container restarted:

```bash
kubectl logs diagnostic-app --previous --tail=200
```

Check:

1. Image reference and node architecture.
2. Pod/container `securityContext`: `runAsNonRoot`, `runAsUser`, `runAsGroup`, `fsGroup`.
3. Volume mounts match paths and are not read-only.
4. Whether the PVC/CSI driver supports ownership/group handling.
5. File/directory modes on existing data from previous deployments.
6. Whether the app writes to `/data`, `/tmp`, or the root filesystem.
7. Whether Pod events report mount failures, image pull failures, or security admission rejections.

`kubectl exec` only helps if the image includes a shell/diagnostic binaries. Minimal images may lack `/bin/sh`; in that case use logs, metadata, ephemeral debug containers per policy, or an appropriate diagnostic image.

### 9.2. Distinguishing `ImagePullBackOff` from App Permission Failures

- `ImagePullBackOff`: the container runtime could not pull the image. Check registry auth, image path/tag/digest, TLS, and platform manifests.
- Pod starts and then crashes with `Permission denied`: the image pulled cleanly; inspect user, filesystem, volumes, and app logs.
- `CreateContainerError` can stem from runtime configuration, mounts, or entrypoint; read events to classify.

Do not tweak `fsGroup` when the Pod has not even pulled the image yet. Do not rotate registry tokens when the app already started and only failed writing a file.

## 10. Gathering Logs and State to Narrow Down Scope

### 10.1. Docker Container Logs

While the container still exists:

```bash
docker ps -a
docker logs --tail=200 diagnostic-app
docker inspect --format '{{.State.Status}} {{.State.ExitCode}} {{.State.Error}}' diagnostic-app
docker inspect --format '{{.Config.User}}' diagnostic-app
# Image OS/architecture, not container metadata
docker image inspect --format '{{.Os}}/{{.Architecture}}' registry.example.com/team/diagnostic-app:1.0.0
```

If you need to keep a container around for investigation, start one with a dedicated name and omit `--rm` during the diagnostic run:

```bash
docker run -d --name diagnostic-app \
  -p 127.0.0.1:18080:8080 \
  registry.example.com/team/diagnostic-app:1.0.0

docker logs --tail=200 diagnostic-app
docker inspect --format '{{.State.Status}} {{.State.ExitCode}} {{.State.Error}}' diagnostic-app
```

Once finished, remove only the test container you created:

```bash
docker rm -f diagnostic-app
```

Do not reuse another application's container name. `docker rm -f` deletes the named container.

### 10.2. Docker Daemon Logs

On Linux with systemd:

```bash
sudo journalctl -u docker --since "15 minutes ago"
```

Reading daemon logs may require administrative privileges. On Docker Desktop, use Desktop's Diagnostics/Troubleshoot and log collection. On Windows Server, inspect services/Event Viewer per host operations.

If the daemon hangs or restarts, daemon logs usually yield clearer answers than application logs because the app may never have started.

### 10.3. Maven/Gradle Diagnostic Output

Maven:

```bash
./mvnw -B -ntp -e spring-boot:build-image
```

Gradle:

```bash
./gradlew bootBuildImage --stacktrace --info
```

`-e`/`--stacktrace` reveals the exception chain; `--info` adds task output. Enable full debug only when needed and on controlled runners, as verbose logs may expose repository URLs, environment/configuration, and sensitive details.

## 11. Common Errors and Evidence-Based Fixes

| Symptom | High-Probability Cause | Resolution Step |
| --- | --- | --- |
| `Cannot connect to Docker daemon` | Engine not running or wrong endpoint/context | `docker info`, context, `DOCKER_HOST`, service |
| `permission denied` on `docker.sock` | Runner user lacks socket access | `id`, socket owner/group, rootless context |
| Docker CLI works, Maven plugin fails | Plugin reads different context/config via env | Compare `DOCKER_CONFIG`, `DOCKER_CONTEXT`, `DOCKER_HOST` in same process |
| Client/API version error | Docker client/plugin and Engine API incompatible | Check client/server versions, update per support matrix |
| Builder pull 401 | Lacks read permission for builder registry | Configure builder registry credentials for right host |
| Builder pull x509 | Daemon does not trust registry CA | Install CA per Docker Engine/registry policy |
| Buildpack download timeout | Builder network/proxy/DNS | Check failing hostname, proxy, and CA |
| `no buildpack groups passed detection` | Source artifact/builder incompatible | Check executable JAR, builder/buildpack versions |
| Build phase fails downloading JDK | Buildpack network or Java version constraint | Check buildpack logs, proxy, supported versions |
| Export phase `no space left on device` | Docker data/cache volume full | `docker system df -v`, host disk/inodes |
| Build uses stale builder | Pull policy/cache keeps old image | Check builder digest and pull policy |
| Incompatible run image | Builder/run stack mismatch | Use run image from builder metadata |
| `no matching manifest` | Registry lacks platform required by node | Check manifest list, publish right architecture |
| `exec format error` | Binary/script wrong arch or format | Inspect OS/arch, binary, and shebang |
| `AccessDeniedException` | App UID/GID cannot write to path | Inspect image user, host mount owner/mode |
| Permission denied reading secret/config | File mode/ACL blocks process read | Check UID/GID, file mode, and mount |
| `Read-only file system` | Writing to root filesystem or read-only mount | Switch to writable volume/tmpfs |
| `No space left on device` writing app data | Volume/disk/inodes/quota exhausted | Check storage and quotas |
| Pod `ImagePullBackOff` | Runtime pull credentials/path/platform | Pod events, `imagePullSecret`, registry manifest |
| Pod crashes after start | App/config/permission/runtime error | Previous logs, state, volumes, and `securityContext` |

## 12. Ordered Diagnostic Workflow

**Step 1 — Record the failing command and phase.** Save the Maven/Gradle command, first error, exit code, and timing. Determine whether failure occurred before daemon connection, during builder pull, in detect/build/export, or when running the container.

**Step 2 — Verify the Docker Engine.** Run `docker version`, `docker info`, `docker context show`. If the Server section fails, fix daemon/context/socket/TLS first.

**Step 3 — Check builder/run images.** Confirm the exact builder/run images and pull policy. Try pulling that exact reference; verify auth, CA, DNS, and disk space.

**Step 4 — Read CNB logs.** Identify the failing build phase (analyze/detect/restore/build/export); separate build failures from launcher/runtime failures occurring after export. Check source artifacts, buildpack support, dependency downloads, cache, and run image compatibility.

**Step 5 — Verify platform.** Compare OS/architecture across the daemon, local image, remote manifest, and production nodes. Check native libraries if the Java app uses JNI or native dependencies.

**Step 6 — Check process user and file paths.** Read `Config.User`; inspect UID/GID, modes, ACLs, parent directories, bind/named volumes, and read-only mounts.

**Step 7 — Verify runtime independently.** Pull/run the exact image and capture logs/state/exit code. On Kubernetes, read Pod events and previous logs to separate pull errors from app crashes.

**Step 8 — Fix one root cause and re-run.** Record the change, verification command, and results. Never wipe the entire Docker data root or grant root/privileged mode without evidence.

## 13. Safe Remediation Practices

| Scenario | Proper Fix | Avoid |
| --- | --- | --- |
| Daemon not running | Start Docker service/Desktop for your environment | Spinning up extra daemons with unclear contexts |
| Wrong Docker context | Select the right context for that process/job | Modifying global config for unrelated projects |
| Socket permission | Grant access to runner identity per policy | Running whole build as root or opening socket widely |
| Registry CA | Install verified CA chain in daemon/runtime | Disabling TLS/using insecure registries in production |
| Builder mismatch | Pin compatible builder/run images | Arbitrarily picking `latest` tags |
| Builder download fails | Configure proxy/CA/repository for right host | Putting credentials in build logs |
| Disk full | Clean resources with verified owner/lifecycle, expand capacity | Blindly running `docker system prune -a --volumes` |
| Wrong architecture | Build/publish matching platform, inspect manifest | Assuming `docker run --platform` rebuilds the image |
| Volume permission | Adjust owner/group/mode for the process | `chmod 777` |
| Read-only root filesystem | Mount writable data/temp paths per policy | Unconditionally enabling writable root filesystems |
| Kubernetes `fsGroup` | Use matching group and supporting volume driver | Picking random UID/GID without checking the image |
| Debug logs | Use `-e`, `--stacktrace`, `--info` to gather evidence | Leaving debug enabled on runners with secrets |

## 14. Self-Check Exercises

**Scenario A.** `docker version` shows Client yet no Server section; Maven `build-image` reports connection failure. Where do you start?

*Answer:* Docker daemon/context/endpoint. Check `docker info`, `docker context show`, `DOCKER_HOST`/`DOCKER_CONTEXT`, and Docker service status. Do not touch buildpacks yet.

**Scenario B.** Docker pulls the builder cleanly, yet CNB times out downloading the JDK. Is the registry password wrong?

*Answer:* Not necessarily. The builder container may need proxy/DNS/CA to download the JDK from another host. Check the hostname in lifecycle logs and the builder's network.

**Scenario C.** App image runs on x86-64, yet ARM64 production reports `no matching manifest`. Why?

*Answer:* The registry manifest lacks a matching `linux/arm64` platform. Build/publish an image for that platform or a verified multi-platform index.

**Scenario D.** App starts, yet writing `/data/report.txt` throws `AccessDeniedException`. What should you inspect?

*Answer:* Image `Config.User`, mount owner/group/mode, directory traverse permissions, and volume read/write state. Do not assume the app runs as root.

**Scenario E.** Container reports `Read-only file system` even though the directory is owned by the right UID. Why?

*Answer:* The filesystem/mount is attached read-only. Check `readOnlyRootFilesystem`, bind mount flags, and volumes; `chmod` cannot turn a read-only filesystem writable.

**Scenario F.** `docker image inspect` shows `linux/amd64`, yet an ARM64 developer laptop runs it fine. Does that guarantee native ARM64 production runs?

*Answer:* No. The developer may be running via emulation. Inspect the remote manifest and test on a native ARM64 runner/node.

**Scenario G.** CNB export fails with `no space left on device`; app runtime has not started. Where do you check?

*Answer:* Docker daemon storage, builder cache volumes, disk blocks/inodes, and runner capacity; this is a build/export phase failure.

**Scenario H.** Kubernetes Pod reports `ImagePullBackOff`; should you change `fsGroup`?

*Answer:* Not as a first step. Inspect Pod events, image reference, registry credentials/TLS, and platform. `fsGroup` handles volume permissions after the image is pulled and mounted.

**Scenario I.** Adding the user to group `docker` fixed the socket error. Can that be treated as an ordinary permission?

*Answer:* It requires security policy review because the `docker` group can confer root-equivalent control on the host. Grant it only to dedicated runner identities with scoped jobs.

**Scenario J.** `docker image inspect` shows an empty user. Does that guarantee the image runs as root?

*Answer:* Do not conclude from a single unclear metadata field alone. Inspect image/buildpack process metadata and runtime behavior; Spring Boot CNB images are designed to build/run non-root, yet actual images and runtime overrides must be verified.

## 15. Checklist Before Concluding the Issue Is Resolved

**Docker daemon and network:**

- Docker client retrieves Server information from the right daemon.
- Context, host, TLS variables, and Docker config path are verified.
- Runner user has socket/endpoint access per policy.
- Builder/run images pull from the right registry.
- Builder network reaches dependency/JDK sources through proper proxy/CA.
- Docker storage has sufficient disk/inodes; caches are intentionally managed.

**Buildpacks and image:**

- Source JAR/WAR is valid and packaged.
- Builder has matching buildpacks; lifecycle logs identify any failing phase.
- Builder/run images are compatible and pinned by version/digest.
- Pull policy fits cache/registry usage.
- Generated image has valid process metadata and is inspectable.
- Image OS/architecture matches target runtime; remote manifest contains needed platforms.

**User and filesystem:**

- `Config.User`/process UID/GID have been verified.
- Bind mounts/named volumes/PVCs have matching owner/group/mode.
- Process has traverse rights on parent directories and read/write on target paths.
- `EACCES`, `EROFS`, and `ENOSPC` are properly distinguished.
- Writable data/temp paths are explicitly designed; root filesystem can stay read-only.
- Neither `chmod 777`, root, nor privileged mode is required to run the app.

**Runtime and evidence:**

- Container/Pod logs, exit codes, and events have been collected.
- Smoke test runs against the exact built/pulled image.
- Kubernetes `ImagePullBackOff` is distinguished from application crashes.
- Fix is re-verified with the exact command that originally reproduced the error.
- Root cause, fix, image digest/platform, and verification results are documented.

**Conclusion:** CNB container troubleshooting flows from **Docker daemon/context**, through **builder/run images and lifecycle**, to **OS/CPU platform**, and finally **process user and filesystem mounts**. When classified at the right layer, `docker info`, lifecycle logs, `docker image inspect`, remote manifest inspection, UID/GID, and volume events pinpoint the exact cause. Fix based on evidence and re-verify with the exact failing command/runtime.

### Official Documentation

- Spring Boot 3.3 Maven Plugin — Packaging OCI Images: https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html
- Spring Boot 3.3 Gradle Plugin — Packaging OCI Images: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html
- Spring Boot 3.3 System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Docker Docs — Troubleshooting the Docker daemon: https://docs.docker.com/engine/daemon/troubleshoot/
- Docker Docs — Docker daemon configuration: https://docs.docker.com/engine/daemon/
- Docker Docs — Rootless mode and UID/GID mapping: https://docs.docker.com/engine/security/rootless/
- Cloud Native Buildpacks — Inspect your app image: https://buildpacks.io/docs/for-app-developers/how-to/build-outputs/inspect-app/
- Kubernetes — Configure a Security Context for a Pod or Container: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Kubernetes — Volumes and file ownership: https://kubernetes.io/docs/concepts/storage/volumes/