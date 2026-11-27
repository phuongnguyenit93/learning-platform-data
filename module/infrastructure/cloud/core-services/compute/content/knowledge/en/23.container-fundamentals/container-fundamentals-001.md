# Container Images, Runtimes, and Container Lifecycle

## Lesson Objectives

A container is a way to package and run an application along with its required dependencies in an OS-level isolated environment. Containers enable consistent deployment across developer machines, virtual machines, and Kubernetes clusters, while offering fast startup times and efficient resource utilization. However, a container is not a lightweight virtual machine: containers typically share the kernel with the host, and the image, runtime, process, network, and storage each have their own lifecycle.

To operate compute workloads in the cloud, you need to understand how images are built and distributed, how a runtime turns an image into a process, what states a container transitions through, and what happens when a process stops or is replaced.

After this lesson, you will be able to:

- Distinguish between a container, an image, a registry, and a runtime.
- Explain the structure of an OCI image, including its manifest, config, and layers.
- Write reproducible Dockerfiles that optimize build caching and reduce the attack surface.
- Distinguish between Docker Engine, containerd, CRI-O, CRI, and an OCI runtime.
- Describe the steps to create, start, stop, and delete a container.
- Design applications that support signals, graceful shutdown, and health checks.
- Manage container networking, volumes, logs, and resource limits.
- Secure images and runtimes across VM, cloud, and Kubernetes environments.

## 1. What Is a Container?

A container is an isolated execution environment for one or more processes. On Linux, containers are built primarily from kernel mechanisms:

- **Namespaces** restrict a process's view of specific resources such as process IDs, networking, mounts, hostnames, IPC, and users.
- **Control groups (cgroups)** meter and limit resources such as CPU, memory, process count, and I/O.
- **Filesystem isolation** provides a dedicated root filesystem for the container, typically assembled from image layers and a writable layer.
- **Capabilities, seccomp, and LSM** restrict the kernel operations that a process can perform.

Containers typically share the host's kernel. This makes containers lighter and faster to start than VMs, but it also means the kernel is a critical security boundary. A kernel vulnerability or misconfigured privilege setting can affect multiple containers on the same host.

VMs virtualize hardware and typically run their own kernel inside a guest OS. Containers isolate processes at the OS level and typically share a common kernel. The two models can be combined: containers running inside VMs to add an isolation layer and simplify infrastructure management.

| Characteristic | Container | Virtual machine |
|---|---|---|
| Kernel | Typically shares the host kernel | Guest OS has its own kernel |
| Packaging | Image containing filesystem and metadata | Disk image containing OS and software |
| Startup | Typically fast, depending on the application | Typically requires booting a guest OS |
| Overhead | Typically lower | Typically higher due to the guest OS |
| Isolation | Namespaces, cgroups, security controls | Hypervisor and guest OS |
| Portability | Depends on architecture, kernel interface, and runtime | Depends on hypervisor, image, and virtual hardware |
| Operations | Runtime, image, registry, and orchestrator | Hypervisor, VM image, and guest management |

You should not conclude that containers are always safer or faster than VMs. Performance and isolation levels depend on the workload, kernel configuration, runtime, storage, networking, and deployment architecture.

## 2. Images, Containers, and Registries

Three foundational concepts:

- **Container image:** an immutable package describing the filesystem, metadata, and default configuration used to create a container.
- **Container:** a running or previously run instance created from an image, with processes, runtime state, and usually its own writable layer.
- **Container registry:** a service for storing, distributing, and managing images by repository and tag/digest.

Multiple containers can be created from the same image. An image does not change when a container writes data to its writable layer; that data belongs to the container instance or a mounted volume.

~~~mermaid
flowchart LR
    S["Source code"] --> B["Image build"]
    B --> I["OCI image"]
    I --> R["Container registry"]
    R --> P["Pull image"]
    P --> RT["Container runtime"]
    RT --> C1["Container A"]
    RT --> C2["Container B"]
    C1 --> V1["Writable layer / volume"]
    C2 --> V2["Writable layer / volume"]
~~~

### 2.1. Repository, Tag, and Digest

An image reference typically looks like:

~~~text
registry.example.com/team/orders-api:2.4.1
~~~

Where:

- registry.example.com is the registry.
- team/orders-api is the repository.
- 2.4.1 is the tag.

A tag is a human-readable name, but it can be moved to point to a different image. Therefore, a `latest` tag or version tag does not automatically guarantee immutable content if the registry allows overwriting.

A digest is a content-addressable identifier based on a hash, typically in the form:

~~~text
registry.example.com/team/orders-api@sha256:<digest>
~~~

When reproducible deployments are required, pinning an image by digest ensures that the workload runs the exact tested content. Tags remain useful for humans and release workflows; digests are suited for identifying the exact artifact.

### 2.2. Image Registry

A registry can be a cloud service, a private organizational registry, or a service integrated into a development platform. Registries typically support:

- Pushing and pulling images.
- Managing repositories, tags, and digests.
- Authentication and authorization.
- Storing manifests and layers.
- Vulnerability scanning or policy integration.
- Retention, replication, and audit logs.

In cloud environments, placing the registry close to workloads can reduce pull times and data transfer costs. However, access should use workload identity or short-lived credential mechanisms; do not embed registry passwords in images.

## 3. OCI Image Structure

The Open Container Initiative (OCI) standardizes formats and interfaces so the container ecosystem can interoperate.

An OCI image typically consists of the following components:

- **Image manifest:** describes the config and list of layers of an image for a specific platform.
- **Image config:** contains metadata such as the default command, environment, user, working directory, and history.
- **Layers:** filesystem segments packaged as immutable blobs.
- **Image index/manifest list:** can point to multiple manifests for different platforms, such as linux/amd64 and linux/arm64.

~~~mermaid
flowchart TD
    IDX["OCI image index"] --> M1["Manifest: linux/amd64"]
    IDX --> M2["Manifest: linux/arm64"]
    M1 --> CFG1["Image config"]
    M1 --> L1["Layer 1"]
    M1 --> L2["Layer 2"]
    M1 --> L3["Layer 3"]
    M2 --> CFG2["Image config"]
    M2 --> L4["Layer 1"]
    M2 --> L5["Layer 2"]
~~~

When pulling a multi-architecture image, the client/runtime selects the manifest matching the current platform. If the image does not have a manifest for the node's architecture, the container may fail to start or fail to execute the binaries inside.

### 3.1. Layers and Copy-on-Write

Each filesystem instruction during a build can create a layer. Layers are shared across multiple images or containers if their content matches and the runtime supports the corresponding storage mechanism.

When creating a container, the runtime stacks the read-only layers into a root filesystem and adds a writable layer for the instance. This is the copy-on-write model commonly implemented with storage drivers such as OverlayFS on Linux.

Operational consequences:

- Image layers are immutable and can be cached.
- Multiple containers can share common image layers.
- Changes in the writable layer do not modify the original image.
- Writing large amounts of data to the writable layer can increase I/O and disk usage.
- Deleting a container typically deletes its writable layer if data has not been persisted to a volume or external system.

Do not use the writable layer to store business data that must survive container recreation.

### 3.2. Image Pull and Unpack

When a runtime needs to run an image that is not yet on the host, it typically must:

1. Authenticate with the registry.
2. Fetch the manifest or image index.
3. Select the manifest matching the platform.
4. Download layers not yet present in the local content store.
5. Verify digests and integrity.
6. Extract/unpack layers into filesystem snapshots.
7. Create the container root filesystem from the snapshots and writable layer.

Layers already present on the host can be reused, so a pull does not necessarily download the entire image every time. However, overly large images or images with many inefficient layers can slow down scale-out and increase network/storage costs.

## 4. Dockerfile Design and Image Building

A Dockerfile describes how to build an image. A good Dockerfile should be clear, reproducible, leverage the build cache, and minimize unnecessary components in the runtime image.

Java example using a multi-stage build:

~~~dockerfile
# Build stage: use JDK and Maven to compile the application
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace

# Copy dependency manifest first to leverage build cache
COPY pom.xml .
RUN mvn -B -q dependency:go-offline

COPY src ./src
RUN mvn -B -DskipTests package

# Runtime stage: keep only the JRE and built artifact
FROM eclipse-temurin:21-jre
WORKDIR /app

RUN groupadd --system app \
    && useradd --system --uid 10001 --gid app app

COPY --from=build --chown=10001:10001 \
    /workspace/target/app.jar /app/app.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This example assumes the project has a pom.xml, Maven sources, and produces target/app.jar. Artifact names, JDK/JRE versions, and build commands must be adjusted per project. For production images, pin base images by digest or manage tested versions carefully.

### 4.1. Multi-Stage Builds

A multi-stage build uses one stage for compiling/testing/packaging and another stage as the runtime. Only the required artifacts are copied into the final image.

Benefits:

- Avoids shipping compilers, build tools, and source code in the runtime image when unnecessary.
- Reduces image size and package count.
- Reduces the attack surface.
- Separates build dependencies from runtime dependencies.
- Enables separate caching for dependencies.

Even a small runtime image still needs CA certificates, timezone data, native libraries, or diagnostic tools if required by the application. Do not strip packages purely for size without verifying runtime dependencies.

### 4.2. Build Cache Optimization

The Docker build cache relies on instruction contents and associated files. When one step changes, subsequent steps may need to re-run.

Key principles:

- Copy dependency manifest files before source code if dependencies change less frequently than source code.
- Group package installation commands sensibly to reduce redundant layers.
- Exclude build output files or unnecessary local directories from the build context.
- Use `.dockerignore` to exclude `target`, `.git`, logs, secrets, and temporary files.
- Keep build steps deterministic.
- Use BuildKit cache mounts if the pipeline supports them and has an appropriate caching policy.

Example `.dockerignore`:

~~~text
.git
.gitignore
target/
build/
.gradle/
.idea/
*.log
.env
.env.*
secrets/
~~~

The list must be tailored to each project. Do not exclude files needed by the build, and do not include secrets in the build context.

### 4.3. Build Arguments and Secrets

Build arguments (ARG) may appear in image metadata or build history depending on how they are used and which builder is used. Do not use ARG or ENV to pass passwords, tokens, or private keys.

With BuildKit, use secret mounts to provide temporary secrets to a build step. Secret mounts are not automatically written into image layers if the command does not copy them onto the filesystem, though build scripts can still leak secrets into logs or artifacts. Only grant secrets to the steps that need them and revoke them after the build.

### 4.4. ENTRYPOINT, CMD, and Exec Form

ENTRYPOINT defines the main executable; CMD typically supplies default arguments or a default command. Exec form uses a JSON array:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Exec form allows the main process to receive signals more directly than shell form. With shell form, the shell can become the parent process and fail to forward signals as expected unless `exec` is used properly.

Inside a container, the main process usually runs as PID 1 in the PID namespace. PID 1 has special signal handling and process-reaping behavior compared to ordinary processes. If the application spawns child processes, ensure children are reaped properly; a minimal init such as `tini` can be used when needed.

## 5. Building, Tagging, Pushing, and Running Images

A basic release workflow:

~~~bash
# Build image
docker build -t orders-api:2.4.1 .

# Tag for registry
docker tag orders-api:2.4.1 registry.example.com/team/orders-api:2.4.1

# Log in to registry using securely provisioned credentials
docker login registry.example.com

# Push image
docker push registry.example.com/team/orders-api:2.4.1

# Run container for testing
docker run --name orders-api-test \
  --publish 8080:8080 \
  --memory 1g \
  --cpus 1.5 \
  registry.example.com/team/orders-api:2.4.1
~~~

Do not hardcode credentials directly in scripts or shell history. In CI/CD, prefer workload identity or a secret store with short-lived credentials.

Common inspection commands:

~~~bash
docker image ls
docker image inspect orders-api:2.4.1
docker container ls -a
docker logs orders-api-test
docker inspect orders-api-test
docker stats orders-api-test
docker stop orders-api-test
docker rm orders-api-test
~~~

The Docker CLI is a common tool for building and managing containers. In Kubernetes, node runtimes are typically managed via CRI; Docker Engine does not necessarily need to be present on the node.

## 6. Container Runtimes and Interface Layers

The runtime is responsible for turning an image into an execution environment and managing processes/containers on the host. The ecosystem has multiple layers, each with a distinct responsibility.

| Component | Role |
|---|---|
| Container engine | Provides API/CLI and orchestrates image/container operations |
| CRI (Container Runtime Interface) | Interface allowing kubelet to communicate with the container runtime |
| High-level runtime | Manages images, metadata, snapshots, and container lifecycle |
| Low-level OCI runtime | Creates processes/containers according to the OCI Runtime Specification |
| Kernel | Provides namespaces, cgroups, filesystems, networking, and syscalls |

### 6.1. Docker Engine

Docker Engine is a container management platform with an API and the Docker CLI. Its traditional deployment architecture includes the Docker client, daemon, and underlying runtime components. Docker can use containerd and an OCI runtime to create containers.

Docker is very useful in development environments and build pipelines. Modern Kubernetes does not require Docker Engine on nodes; kubelet communicates with the runtime through CRI.

### 6.2. containerd and CRI-O

**containerd** is a high-level container runtime that manages images, snapshots, and the container lifecycle. It can use an OCI runtime such as runc to create container processes. Kubernetes commonly integrates containerd through its CRI plugin.

**CRI-O** is a runtime designed for Kubernetes that implements CRI and uses an OCI runtime to create containers.

Both options can run Kubernetes workloads. Choose based on platform, vendor support, tooling ecosystem, security policy, and operational requirements.

### 6.3. runc and OCI Runtimes

runc is a widely used OCI runtime implementation. It reads a container configuration bundle and instructs the kernel to create a process environment with the required namespaces, cgroups, mounts, and settings.

The OCI Runtime Specification defines low-level configuration and lifecycle semantics. Other runtimes may provide additional isolation layers or distinct security mechanisms; not all runtimes share the same threat model.

### 6.4. CRI in Kubernetes

Kubelet uses CRI to instruct the runtime to perform operations such as:

- Pulling images.
- Creating a Pod sandbox.
- Creating, starting, and stopping containers.
- Checking container status.
- Collecting runtime information and logs.

A Pod sandbox typically establishes an environment sharing certain namespaces/networking across containers within the same Pod, depending on runtime configuration. Containers in a Pod can share a network namespace and communicate over localhost, while still having separate filesystems and resource limits.

~~~mermaid
flowchart TD
    K["Kubelet"] --> CRI["CRI API"]
    CRI --> R["containerd or CRI-O"]
    R --> IMG["Image / snapshot service"]
    R --> OCI["OCI runtime"]
    OCI --> L["Linux kernel"]
    L --> NS["Namespaces"]
    L --> CG["cgroups"]
    L --> FS["Mount / root filesystem"]
    L --> PR["Container processes"]
~~~

## 7. Container Lifecycle

At a high level, a container passes through these phases:

1. The image is pulled or retrieved from the local content store.
2. The runtime prepares the root filesystem and metadata.
3. The runtime creates the container and configures namespaces/cgroups/mounts.
4. The runtime launches the main process.
5. The process runs, serves traffic, and writes logs.
6. The process exits, is stopped, or is terminated by the runtime.
7. The runtime records the exit state and releases resources.
8. The container may be deleted; the writable layer may be discarded.

Displayed state names depend on the tool. Docker typically has states such as created, running, paused, restarting, exited, and dead. Kubernetes shows Pod phases such as Pending, Running, Succeeded, Failed, or Unknown; container states inside a Pod can be Waiting, Running, or Terminated.

Do not equate Pod status with the status of an individual container. A Pod can be Running while a container is restarting or a sidecar is not yet ready.

### 7.1. Created and Running

- **Created:** container metadata and configuration have been created, but the main process is not yet running.
- **Running:** the main process is executing.
- **Paused:** the process is frozen by the runtime if the feature is supported.
- **Exited/Terminated:** the main process has finished; the runtime retains the exit code and state information.
- **Removing/Deleted:** the container is deleted and runtime resources are freed.

A container does not automatically return to the running state after its process exits. A restart policy or orchestrator decides whether to recreate or restart the container.

### 7.2. Restart Policies

In Docker, restart policies can include `no`, `on-failure`, `always`, and `unless-stopped`. Each policy determines under what conditions the container is restarted and whether it depends on daemon state or user actions.

In Kubernetes, a Pod's `restartPolicy` is typically `Always`, `OnFailure`, or `Never`. For a Deployment, Pods typically use `Always`; the controller creates replacement Pods when a Pod no longer matches the desired state. Jobs typically use `OnFailure` or `Never` depending on design.

Restarting does not fix the root cause of an error. If a process crashes due to misconfiguration or an unavailable dependency, continuous restarts can create a crash loop and add load to dependent systems.

## 8. Stopping Containers and Graceful Shutdown

When a container is stopped in a controlled manner, the runtime typically sends a signal to the main process, waits for a grace period, and then sends a forced termination signal if the process has not exited. With Docker, the default signal is typically SIGTERM followed by SIGKILL after a timeout; the wait duration is configurable. Kubernetes also has a termination grace period and a defined sequence for sending stop signals to containers.

An application needs to handle shutdown in order to:

- Stop accepting new requests or messages.
- Complete in-flight requests/jobs within limits.
- Commit transactions and checkpoints.
- Flush critical logs or buffers.
- Close connection pools, consumers, and thread pools.
- Terminate the process before the grace period expires.

If the process does not handle SIGTERM or fails to exit in time, the runtime may send SIGKILL. SIGKILL cannot be caught or handled by the application.

### 8.1. Graceful Shutdown in Java

A Java shutdown hook can help close resources when the JVM receives a catchable termination signal:

~~~java
public final class Application {
    public static void main(String[] args) {
        WorkerService worker = new WorkerService();
        worker.start();

        Runtime.getRuntime().addShutdownHook(
            new Thread(() -> {
                worker.stopAcceptingNewWork();
                worker.awaitInFlightTasks();
                worker.closeResources();
            }, "shutdown-hook")
        );
    }
}
~~~

This is illustrative code. Methods must include appropriate timeouts and exception handling. Do not wait indefinitely in a shutdown hook; the orchestrator only grants a finite window before forced termination.

For containers, use exec form for ENTRYPOINT so the Java process receives signals directly. If a shell wrapper is needed, use `exec java ...` to replace the shell with the Java process.

### 8.2. PID 1 and Process Reaping

The first process in a PID namespace typically has PID 1. If an application spawns child processes without reaping terminated ones, zombie processes can accumulate. A lightweight init like `tini` can forward signals and reap orphaned child processes.

You do not need an extra init process if the application runs only a single process or handles child processes properly. Choose based on the actual process model.

## 9. Health Checks: Health, Readiness, and Startup

Health checks tell the runtime or orchestrator whether a process is alive and able to receive traffic. Three distinct questions must be separated:

- **Startup:** has the application finished its startup phase?
- **Readiness:** can the application serve requests right now?
- **Liveness:** is the process still running and capable of self-recovery?

In Docker, `HEALTHCHECK` can run a periodic command and mark a container healthy/unhealthy. Docker health status does not automatically mean a load balancer will remove the target or Docker will restart an unhealthy container; that behavior requires separate orchestration.

In Kubernetes, startup, readiness, and liveness probes have distinct semantics:

- A startup probe allows slow-starting applications to initialize without being prematurely failed by the liveness probe.
- A readiness probe determines whether a Pod is eligible to receive traffic through a Service.
- A liveness probe can cause kubelet to restart a container when it detects the process cannot recover under the probe conditions.

Do not use liveness probes to check every external dependency such as databases or external APIs. A transient dependency outage could cause all containers to restart repeatedly.

### 9.1. Docker HEALTHCHECK Example

~~~dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD curl --fail --silent http://127.0.0.1:8080/health/live || exit 1
~~~

This example assumes the image contains `curl` and the application exposes a liveness endpoint at this path. Health checks should only verify that the process can continue operating; readiness and dependency checks should be designed separately. If the image does not include `curl`/`wget`, use a controlled lightweight probe or the orchestrator's health check mechanism rather than adding tools to the runtime image without evaluating size and attack surface.

### 9.2. Kubernetes Probes Example

~~~yaml
startupProbe:
  httpGet:
    path: /health/startup
    port: 8080
  periodSeconds: 5
  failureThreshold: 36

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Endpoints must be implemented with accurate semantics. Readiness can return an error while the application is draining; liveness should only fail when the process genuinely needs a restart.

## 10. Container Networking

A container can have its own network namespace and virtual network interfaces. The runtime or orchestration platform configures IP addresses, routes, DNS, and connectivity between containers, the host, and external networks.

Common concepts:

- **Bridge network:** containers connect through a virtual bridge on the host.
- **Host network:** the container uses the host's network namespace, removing a layer of network isolation and changing how ports are managed.
- **Overlay network:** creates a logical network spanning multiple hosts.
- **CNI:** the network plugin interface commonly used in Kubernetes to configure Pod networking.
- **Port publishing:** mapping a container port to the host or an external endpoint.
- **Service discovery/DNS:** locating containers or services by name instead of static IPs.

Docker example:

~~~bash
# Create a dedicated network
docker network create app-net

# Run the database only inside the application's internal network
docker run -d --name db --network app-net postgres:16

# Run the API and publish the HTTP port to the host
docker run -d --name api \
  --network app-net \
  --publish 8080:8080 \
  orders-api:2.4.1
~~~

This example only illustrates network connectivity. In production, configure appropriate passwords, volumes, TLS, firewalls, and image digests. Do not publish database ports to the Internet without an explicit requirement and strict network controls.

### 10.1. DNS and IP Addresses

A container's IP address can change when the container is recreated. Applications should use service discovery or stable DNS names instead of caching container IP addresses long-term.

In Kubernetes, Pod IPs can change when Pods are replaced; a Service provides a stable endpoint for workloads. Network policies can restrict traffic flows between namespaces, Pods, or workloads as supported by the CNI plugin.

## 11. Container Storage and Data

A container's writable layer is typically suitable for temporary files and regenerable data. Data that must survive container recreation should reside on a volume or independent storage service.

Common storage types:

| Type | Lifecycle | Use cases |
|---|---|---|
| Writable container layer | Tied to the container instance | Temporary files, regenerable caches |
| Bind mount | Maps a host path into the container | Development or controlled host path access |
| Named volume | Managed by the runtime, exists independently of the container | Data that must be retained on the host |
| Ephemeral volume | Typically tied to the Pod or workload lifecycle | Scratch data, temporary caches |
| Persistent volume | Storage managed independently according to policy | Databases, stateful workloads |
| Object storage | Data accessed via API | Artifacts, backups, checkpoints, and shared data |

Not every named volume automatically replicates or survives host loss. Durability depends on the driver, backend, and storage policy.

### 11.1. Docker Volume Example

~~~bash
docker volume create orders-data

docker run -d --name orders-db \
  --mount source=orders-data,target=/var/lib/postgresql/data \
  postgres:16
~~~

This example only demonstrates how to attach a volume; production database deployments require dedicated secrets, backups, networking, version pinning, and storage policies.

### 11.2. Ephemeral Storage in Kubernetes

Container writable layers, logs, and emptyDir volumes can consume node ephemeral storage. If a workload writes excessive temporary data or logs, the node can experience disk pressure and kubelet may evict Pods.

For write-heavy workloads, set `ephemeral-storage` requests/limits when supported by the platform, monitor node filesystems, and move durable data to persistent storage.

## 12. Resource Limits with cgroups

Containers do not automatically receive fixed amounts of CPU and RAM. The runtime and orchestrator configure cgroups to meter and enforce limits.

### 12.1. CPU

CPU can be controlled via:

- CPU shares/weight: relative priority during contention.
- CPU quota/period: cap on CPU time within a period.
- CPU set: restricts the set of CPUs a process can run on.

In Docker, `--cpus`, `--cpu-shares`, and `--cpuset-cpus` configure the corresponding mechanisms. In Kubernetes, CPU requests affect scheduling and shares/weight; CPU limits are typically enforced as quotas.

Setting a CPU limit too low can cause throttling and increase latency. Do not look solely at average CPU usage; monitor throttling and tail latency as well.

### 12.2. Memory

A memory limit sets the cgroup ceiling for a container. If the container exceeds the limit, the kernel may trigger OOM handling and terminate one or more processes in the cgroup.

For Java, the heap should not occupy the entire memory limit. Leave headroom for metaspace, code cache, thread stacks, direct buffers, native libraries, and agents.

In Kubernetes:

- `requests.memory` affects scheduling and QoS.
- `limits.memory` caps the container's memory usage.
- A container can be OOMKilled if it exceeds its limit or if the node faces memory pressure under policy.
- Pods may be evicted when a node runs low on resources, even before a container hits its individual limit.

### 12.3. PIDs and I/O

Cgroups can limit process/thread counts and track I/O. A PID limit set too low can prevent the JVM or application from spawning threads. Disk I/O policies can affect read/write-heavy workloads, though support depends on the kernel and runtime.

Monitor both the container and the node: CPU throttling, memory working set, OOM events, PID usage, filesystem usage, and block I/O.

## 13. Image and Container Runtime Security

Because containers share the kernel, security configuration directly affects the host boundary.

Core principles:

- Run processes as a non-root user whenever possible.
- Avoid `--privileged` unless explicitly required and strictly controlled.
- Drop Linux capabilities to the minimum required.
- Use an appropriate seccomp profile to restrict syscalls.
- Use AppArmor or SELinux when supported by the platform.
- Mount the root filesystem read-only if the application permits.
- Restrict write permissions and host path mounts.
- Do not mount the Docker socket or runtime socket into application containers.
- Use user namespaces or rootless containers where appropriate.
- Restrict network ingress/egress.
- Keep the host kernel, runtime, and base images updated.

### 13.1. Running Non-Root and Read-Only

A Dockerfile can specify a non-root user:

~~~dockerfile
USER 10001:10001
~~~

`docker run` can apply several restrictions:

~~~bash
docker run --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  orders-api:2.4.1
~~~

This configuration is suitable only if the application does not need to write to the root filesystem and requires no special capabilities. If the application needs a temporary directory, mount a `tmpfs` or a dedicated volume with minimal permissions.

### 13.2. Image Supply Chain

Images are artifacts that must be secured from source to production:

1. Build from approved base images.
2. Pin dependencies and base images by version/digest.
3. Scan OS packages and application dependencies for vulnerabilities.
4. Generate a Software Bill of Materials (SBOM).
5. Sign images or artifacts according to organizational policy.
6. Verify signatures and provenance before deployment.
7. Control push/pull permissions per repository.
8. Enforce retention and clean up obsolete images by policy.
9. Track base image patches and rebuild periodically.

Image scanning does not guarantee zero vulnerabilities; scanners only detect issues known in current databases and rules. Combine scanning with patch management, runtime controls, and monitoring.

### 13.3. Secrets in Containers

Do not place secrets in Dockerfiles, image layers, source control, or long-lived environment variables when safer options exist. Prefer a secret manager and workload identity to issue short-lived credentials. Scope secret read permissions by service account and revoke access when the workload is deleted.

Environment variables are convenient but can be exposed via process inspection, crash dumps, or logs. Understand your threat model and the platform's secret injection mechanisms.

## 14. Container Logging and Observability

Containers are typically designed to write application logs to stdout/stderr. The runtime or platform can collect these streams and forward them to a logging backend.

Metrics and signals to monitor:

- Container state and restart count.
- Exit codes and termination reasons.
- CPU, memory, throttling, and OOM events.
- Network traffic, errors, and connections.
- Writable layer and ephemeral storage usage.
- Image digest, runtime version, and node.
- Startup/readiness duration.
- Application logs and metrics.

In Docker, commands such as `docker logs`, `docker inspect`, and `docker stats` help inspect host-level details. In Kubernetes, use `kubectl describe pod`, `kubectl logs`, `kubectl get events`, and an appropriate metrics backend.

Do not observe Pod state alone. A Pod may be Running while the application is not ready; a container may restart repeatedly; a node may be running out of disk or memory. Correlating runtime events with application metrics accelerates root-cause analysis.

### 14.1. Log Rotation and Volume

If logs are not rotated or capped, containers can fill the node disk. Configure the log driver/runtime and log collector with appropriate size limits, retention, and backpressure.

Applications should avoid high-rate repetitive logging during prolonged dependency outages. Use rate limiting, sampling, or lower log levels where appropriate, while preserving enough context for investigation.

## 15. Containers in VMs, Kubernetes, and Serverless

### 15.1. Containers on VMs

A VM can run Docker Engine or containerd to host multiple containers. Operators are responsible for managing the OS, kernel, runtime, image pulls, networking, volumes, and restart policies.

This model fits well when host-level control is needed or when running a moderate number of workloads. At larger scale, manually managing scheduling, service discovery, and capacity becomes complex.

### 15.2. Containers on Kubernetes

Kubernetes orchestrates containers through Pods and controllers. A Pod is the scheduling unit; containers in the same Pod share certain resources and network contexts. Deployments, StatefulSets, DaemonSets, and Jobs describe different workload patterns.

Kubernetes manages desired state: if a Pod is lost or a container needs restarting per policy, controllers/kubelet work to restore the desired state. Still, applications require proper readiness, graceful shutdown, persistent storage, and fault-tolerant design.

### 15.3. Containers in Serverless

Some serverless platforms accept container images or package applications in an image-compatible format, then manage the host and runtime on the user's behalf. Users still need to manage image size, startup time, memory/CPU requests, concurrency, health checks, and graceful shutdown according to the service contract.

Not all serverless platforms run arbitrary OCI images without constraints. A platform may require specific ports, entrypoints, architectures, image registries, or filesystem layouts.

## 16. Debugging the Container Lifecycle

Common Docker diagnostic commands:

~~~bash
# List containers and states
docker ps -a

# Inspect detailed configuration and state
docker inspect orders-api-test

# View logs
docker logs --tail 200 orders-api-test

# View live resource usage
docker stats orders-api-test

# View processes inside the container
docker top orders-api-test

# Inspect image and digest
docker image inspect orders-api:2.4.1
~~~

In Kubernetes:

~~~bash
# Pod status and node placement
kubectl get pods -o wide
kubectl get nodes

# Detailed Pod info, events, and probes
kubectl describe pod <pod-name>

# Current container logs
kubectl logs <pod-name> -c <container-name>

# Previous container logs if restarted
kubectl logs <pod-name> -c <container-name> --previous

# Check recent events
kubectl get events --sort-by=.lastTimestamp
~~~

Common reasons a container fails to start:

| Symptom | Possible Cause | Troubleshooting Direction |
|---|---|---|
| ImagePullBackOff | Registry auth, wrong tag/digest, or network issue | Check image reference, pull permissions, and registry |
| Exec format error | Binary or image built for wrong architecture | Check platform and manifest list |
| CrashLoopBackOff | Process exits repeatedly or misconfigured probes | Inspect exit code, logs, startup, and liveness probes |
| OOMKilled | Exceeded memory limit or node pressure | Compare RSS, heap, cgroup limits, and memory events |
| Container running but not receiving traffic | Readiness, port, network policy, or service routing | Check probes, listener, endpoints, and routes |
| Filesystem full | Growing logs or writable layer | Check ephemeral storage, log rotation, and volumes |
| Unclean shutdown | PID 1 not forwarding signals or app shutdown takes too long | Check ENTRYPOINT, signals, and grace period |

## 17. Secure Image Release Workflow

An image release pipeline should include these steps:

1. Check out source code from an identified revision.
2. Install dependencies from trusted sources.
3. Run tests and build artifacts.
4. Build the image using a reviewed Dockerfile.
5. Scan dependencies and the image.
6. Generate SBOM and provenance if supported by the pipeline.
7. Tag the release and capture the digest.
8. Push the image to the registry.
9. Sign the image and verify signatures per policy.
10. Deploy using the digest or verified artifact.
11. Monitor startup, readiness, errors, and resource usage.
12. Roll back to the previous digest if the release misses SLOs.

Tags help identify releases, while digests identify exact content. Record the digest in deployment records so you can reproduce and investigate the exact image that ran.

### 17.1. Rollout and Rollback

With a Kubernetes Deployment, rolling updates replace Pods in batches. Configure `maxSurge`, `maxUnavailable`, readiness probes, and `PodDisruptionBudget` appropriately to avoid losing too much capacity at once.

Rollback requires the previous image digest to still exist in the registry and remain compatible with current data/schemas. If a release includes backward-incompatible migrations, rolling back the image alone may not suffice; a safe migration process is required.

## 18. Common Pitfalls and How to Avoid Them

**Confusing images with containers:** an image is an immutable artifact; a container is a runtime instance. Data written in a container does not automatically update the image.

**Using mutable tags in production:** a tag can be repointed to different content. Record and pin tested digests.

**Including compilers and build tools in runtime images:** increases size and attack surface. Use multi-stage builds where appropriate.

**Running containers as root and privileged:** increases potential impact on the host. Run non-root, drop capabilities, and apply minimal security profiles.

**Storing state in the writable layer:** data can be lost when the container is recreated. Use volumes or durable storage services.

**Using shell form without handling signals:** the application may not receive SIGTERM properly. Use exec form or a wrapper with `exec`.

**Ignoring PID 1 behavior:** child processes may go unreaped. Use an appropriate process model or a lightweight init when needed.

**Using liveness probes to check the database:** transient dependency errors can restart all containers. Separate readiness and liveness probes.

**Omitting CPU/memory limits:** one container can impact other workloads on the same host. Set requests/limits and monitor throttling/OOM events.

**Oversized images:** increases pull times and scale-out latency. Optimize layers, multi-stage builds, and base images.

**Neglecting log rotation:** logs can fill the node disk. Configure log drivers and retention.

**Leaving secrets in images or build logs:** secrets can persist in layers and artifacts. Use a secret manager or BuildKit secret mounts.

**Treating PDBs or restart policies as zero-downtime guarantees:** orchestrators only assist recovery according to their semantics. Applications still need graceful shutdown, retries, and durable state.

## 19. Container Image, Runtime, and Lifecycle Checklist

- [ ] Images are built from approved base images with explicit versions/digests.
- [ ] Dockerfiles use multi-stage builds when appropriate and retain only required runtime dependencies.
- [ ] Build context is filtered using `.dockerignore`.
- [ ] No credentials or secrets are placed in images, ARG, ENV, or build logs.
- [ ] Images have manifests for allowed node architectures.
- [ ] Registries enforce authentication, authorization, and retention policies.
- [ ] Images are scanned, have SBOM/provenance when required by policy, and are verified before deployment.
- [ ] Containers run as non-root and avoid unnecessary privileged mode.
- [ ] Capabilities, seccomp, AppArmor/SELinux, and filesystems are appropriately restricted.
- [ ] Runtimes and kernels are patched and version-managed.
- [ ] The main process receives signals properly; graceful shutdown has a timeout.
- [ ] Readiness, liveness, and startup probes have distinct semantics.
- [ ] Persistent data is stored on volumes or durable storage services.
- [ ] CPU, memory, PIDs, and ephemeral storage have appropriate limits.
- [ ] Networking, DNS, ports, and network policies are controlled.
- [ ] Log rotation, metrics, and container events are collected.
- [ ] Deployments use digests and have a rollback plan.
- [ ] Pull failures, crashes, OOMs, restarts, and termination have been tested.

A container image describes the artifact to run; a registry distributes the artifact; a runtime creates and manages processes in an isolated environment. By understanding layers, digests, CRI/OCI runtimes, and lifecycles, teams can build smaller, more reproducible, and safer images. Applications must handle signals, health checks, storage, and resource limits properly to operate reliably when containers are restarted, replaced, or moved across cloud nodes.
