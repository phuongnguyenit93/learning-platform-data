# Multi-Architecture Images for x86 and Arm

Container images are typically built on a developer machine or CI runner and then executed across diverse node types in cloud environments. If a cluster contains both x86-64 and Arm64 machines, an image must include the right binaries, libraries, and metadata for the target architecture. An x86-64-only binary may build cleanly on CI yet fail when the scheduler places the container onto an Arm node. Multi-architecture images solve distribution by providing matching variants under a single image reference.

An OCI image index—previously known as a Docker manifest list—is the standard mechanism allowing one tag to represent multiple images across operating systems, architectures, and sometimes CPU variants. When a client pulls an image, the registry returns the index; the container runtime selects the manifest matching the node's platform and downloads the corresponding layers.

This lesson walks through designing, building, verifying, and deploying multi-architecture images for x86 and Arm. It covers binary and native library differences, cross-compilation, emulation, Docker Buildx, registries, testing on real hardware, and scheduling workloads in mixed-architecture clusters. After this lesson, you will be able to:

- Explain the difference between a single-architecture image, a manifest list, and an OCI image index.
- Identify build and target platforms using OS, architecture, and variant.
- Build images for linux/amd64 and linux/arm64 using Docker Buildx.
- Write Dockerfiles that safely support native builds or cross-compilation.
- Verify that a registry holds all required variants and that runtimes select the right image.
- Test binaries, native libraries, performance, and behavior on both x86 and Arm.
- Deploy workloads on mixed-architecture compute clusters without mis-scheduling containers onto incompatible nodes.

## 1. Why Are Multi-Architecture Images Needed?

Two machines can run the same Linux operating system and the same container runtime while having different CPU architectures. An x86-64 CPU is typically identified as `amd64` in Docker/OCI; 64-bit Arm is typically identified as `arm64`. Architecture names in container tooling do not necessarily match the strings displayed by OS utilities.

| Platform | Common Name in OCI/Docker | Common `uname -m` Value |
|---|---|---|
| Linux x86 64-bit | linux/amd64 | x86_64 |
| Linux Arm 64-bit | linux/arm64 | aarch64 |
| Linux Arm 32-bit, v7 variant | linux/arm/v7 | armv7l |

A binary compiled for x86-64 cannot natively execute directly on an Arm64 CPU. Likewise, an Arm64 binary cannot execute directly on x86-64 without an emulation or translation layer. Sharing the same image tag name does not automatically make the binaries inside compatible.

### Single-Architecture Images

A single-architecture image holds one variant built for a single platform. For example, `orders-api:1.4-amd64` contains only an x86-64 binary. To run on Arm, the team must build and distribute a separate variant such as `orders-api:1.4-arm64` and manage two distinct references in deployment systems.

### Multi-Architecture Images

A multi-architecture image provides a single shared reference—such as `orders-api:1.4`—pointing to an index containing manifests for both `linux/amd64` and `linux/arm64`. The runtime reads the metadata and automatically selects the variant matching the node.

~~~mermaid
flowchart TD
    T["orders-api:1.4"] --> I["OCI image index"]
    I --> A["Manifest linux/amd64"]
    I --> B["Manifest linux/arm64"]
    A --> AL["Config + layers x86-64"]
    B --> BL["Config + layers Arm64"]
    N1["Node x86-64"] --> T
    N2["Node Arm64"] --> T
    N1 -. "runtime selects" .-> A
    N2 -. "runtime selects" .-> B
~~~

Thus, a manifest index provides a unified deployment interface. Pipelines must still build and test each variant; the index only ensures the right image is distributed to the matching platform.

## 2. How Do OCI Image Indexes and Manifests Work?

An OCI image typically consists of an image configuration and filesystem layers. A manifest describes the config and list of layers for a specific image. An OCI image index is a higher-level structure containing multiple descriptors pointing to different manifests.

A descriptor in an index can specify:

- `os`: operating system, such as `linux`.
- `architecture`: architecture, such as `amd64` or `arm64`.
- `variant`: architectural variant when needed, such as `v7` for certain Arm platforms.
- `digest`: content-addressable identifier of the referenced manifest.
- `mediaType` and `size`: content type and descriptor size.

When pulling a multi-architecture tag, the runtime fetches the index and chooses the descriptor matching the current platform. It then downloads the corresponding manifest and layers. A single tag can point to the shared index, while each child manifest has its own distinct digest.

### Tags and Digests

Tags like `1.4` or `stable` are human-readable names that can be updated to point to different content. Digests like `sha256:...` identify immutable content. In production deployments, record verified digests to guarantee reproducible rollouts and accurate rollbacks.

For multi-architecture images, distinguish among:

- Digest of the OCI index: identifies the collection of manifests across platforms.
- Digest of a child manifest: identifies a specific image for one OS/architecture.
- Digest of each layer: identifies the contents of a layer.

Pinning the index digest ensures every node consumes the exact same published set of variants. Each runtime still selects the child manifest matching its architecture.

### Runtimes Do Not Translate Binaries Automatically

An OCI index only selects an image already built for the matching platform. It does not recompile binaries, convert native libraries, or guarantee logical application compatibility. If the index omits `linux/arm64`, an Arm node may fail during pull with an error stating no matching manifest was found.

## 3. Components That Can Differ Between x86 and Arm

Architectural differences affect multiple layers inside an image.

### Binaries and Compiler Targets

Executables must be compiled for the target CPU architecture. For example, Go can use `GOARCH=amd64` or `GOARCH=arm64`; GCC/Clang use the appropriate target triple and toolchain. A program built on x86 does not automatically become an Arm binary when packaged into an image.

### Native Libraries and ABIs

Applications may depend on OpenSSL, `libstdc++`, native database drivers, codecs, image-processing libraries, or C/C++ extensions. Every library must have a build matching the runtime's architecture and ABI.

Never copy `.so` libraries from an x86 stage into an Arm image. Install packages for the target architecture or compile from source using the target toolchain.

### Runtimes and Packages with Native Extensions

Certain Python, Node.js, Ruby, Java JNI, or .NET native dependencies contain architecture-specific compiled components. Package managers may select different wheels or binary packages by platform. If no compatible artifact exists, builds may fail or fall back to building from source.

### Base Images

Many official base images support multiple architectures, though not every tag or variant offers identical support. Internal base images, vendor images, and images carrying proprietary agents must have their manifests verified before use.

### CPU Instruction Sets and Optimizations

Binaries can be compiled targeting specific CPU instruction sets. An x86-64 binary optimized for AVX-512 may fail to run on x86 instances lacking that instruction set. Arm also has features like NEON or SVE depending on the CPU. Choose a baseline instruction set compatible across your entire target instance fleet, or ship optimized variants under explicit conditions.

### Behavior and Performance

Even when a binary runs properly on both architectures, performance can differ due to core counts, caches, memory bandwidth, NUMA topology, compilers, runtimes, and instance families. Never assume the same vCPU count yields identical throughput. Benchmark representative workloads on each machine type before deciding capacity ratios.

## 4. Inspecting Build and Target Architectures

On Linux:

~~~bash
uname -s
uname -m
getconf LONG_BIT
~~~

In Docker:

~~~bash
docker version --format '{{.Server.Os}}/{{.Server.Arch}}'
docker info --format '{{.OSType}}/{{.Architecture}}'
~~~

Inside a Dockerfile, BuildKit provides automatic build arguments:

- `BUILDPLATFORM`: the builder's platform.
- `BUILDOS`, `BUILDARCH`, `BUILDVARIANT`: OS, architecture, and variant of the builder.
- `TARGETPLATFORM`: the target image's platform.
- `TARGETOS`, `TARGETARCH`, `TARGETVARIANT`: target OS, architecture, and variant.

For example, CI runs on `linux/amd64` while needing to build a `linux/arm64` image. In that case, `BUILDARCH=amd64` and `TARGETARCH=arm64`. Distinguishing these two sets of variables is crucial when cross-compiling.

## 5. Building Multi-Architecture Images with Docker Buildx

Docker Buildx is a BuildKit-based build CLI supporting multi-platform builds and outputting an image manifest/index. A builder can use native nodes across multiple architectures or use emulation to execute build steps for the target architecture.

### Checking Buildx

~~~bash
docker buildx version
docker buildx ls
~~~

Create a builder using the `docker-container` driver if the environment lacks a suitable builder:

~~~bash
docker buildx create --name multiarch-builder --driver docker-container --use
docker buildx inspect --bootstrap
~~~

Running `inspect --bootstrap` initializes the builder and displays supported platforms. The list may depend on QEMU/binfmt or registered builder nodes.

### Building and Pushing Two Architectures

Assuming the Dockerfile supports multiple architectures and you are logged into the registry:

~~~bash
docker login registry.example.com

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag registry.example.com/team/orders-api:1.4.0 \
  --push \
  .
~~~

Buildx builds a variant for each platform and pushes the manifests/index to the registry. For multi-platform builds, `--push` is the standard way to publish results. `--load` in the classic Docker image store typically loads only a single platform; local multi-platform storage depends on the image store backend and Docker version. Do not assume `--load` always creates a multi-architecture index.

Inspect the result:

~~~bash
docker buildx imagetools inspect registry.example.com/team/orders-api:1.4.0
~~~

The output should include descriptors for the expected platforms, such as `linux/amd64` and `linux/arm64`. If only one platform appears, do not deploy that tag to a mixed cluster before fixing the pipeline.

## 6. Writing a Dockerfile Supporting Cross-Compilation

For pure Go applications that do not require CGO, binaries can be compiled for the target architecture on a builder host of a different architecture. This reduces reliance on emulation during compilation.

~~~dockerfile
# syntax=docker/dockerfile:1

FROM --platform=$BUILDPLATFORM golang:1.23 AS build
WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download
COPY . .

ARG TARGETOS
ARG TARGETARCH
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath -ldflags="-s -w" -o /out/orders-api ./cmd/orders-api

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/orders-api /orders-api
USER nonroot:nonroot
ENTRYPOINT ["/orders-api"]
~~~

In the build stage, `BUILDPLATFORM` keeps the compiler running natively on the builder's architecture. `TARGETOS` and `TARGETARCH` specify the output binary. The runtime stage does not pin the platform to the builder, so BuildKit selects the runtime base image matching the target platform. Verify that the distroless base image in the example fully supports all target architectures before adopting it.

This example applies to pure Go binaries without CGO. If the application depends on C libraries, a cross-compilation toolchain, sysroot, and target libraries are needed; setting `GOARCH` alone is insufficient.

### Native Builds per Platform

For C/C++ applications, Java with JNI, or complex native packages, building on native runners for each architecture is often simpler and more reliable:

1. An x86 runner builds the `linux/amd64` image.
2. An Arm runner builds the `linux/arm64` image.
3. Each runner executes tests and produces its own artifact.
4. The pipeline combines the manifests into a shared index.

The advantage is that compilers, package managers, and tests run directly on the target architecture. In exchange, CI needs runners for both CPU types and artifact management across jobs.

## 7. Emulation and QEMU

If only x86 builders are available yet Arm images are needed, QEMU user-mode combined with `binfmt_misc` enables executing Arm binaries inside an x86 build environment. Buildx typically detects platforms supported by the builder.

On Linux, some environments register QEMU handlers via the `tonistiigi/binfmt` image:

~~~bash
docker run --privileged --rm tonistiigi/binfmt --install arm64,amd64
docker buildx inspect --bootstrap
~~~

Installing `binfmt` requires privileged mode and should only run in controlled build environments. Managed CI or Docker Desktop may already have emulation configured; do not reinstall it blindly.

### When to Use Emulation

- Lightweight builds or smoke tests for architectures lacking native runners.
- Building images whose package managers or scripts must execute target binaries during the build.
- Quickly verifying that entrypoints and basic startup commands work.

### Limitations of Emulation

- Builds can be significantly slower than native builds.
- Certain kernel operations, syscalls, or devices are not fully emulated.
- Performance measurements are not representative of real CPUs.
- Applications using JIT, SIMD, or native extensions may exhibit differences.
- Heavy builds can hit CI timeouts or place heavy load on builders.

Emulation is helpful for extending build capabilities, but it does not replace testing on real Arm hardware before releasing critical workloads.

## 8. Handling Native Dependencies and Multi-Architecture Packages

This is one of the most frequent failure sources. An image tagged with an `arm64` manifest that still contains x86 libraries inside will not run properly.

### OS Packages

When installing packages in a target stage, the package manager must run for the target architecture. If that stage executes under emulation, the package manager generally selects packages for the target root filesystem. When cross-compiling manually, explicitly target the proper package sysroot and target libraries.

Never copy `/usr/lib` or binaries from the build host into a target image without verifying the architecture and ABI of every file.

### Python Wheels

Python packages with native extensions typically publish wheels keyed by ABI, architecture, and libc. An x86-64 `manylinux` wheel will not work on Arm64. If no matching wheel exists, `pip` may build from source, requiring a compiler, headers, and system libraries.

Verify:

- Wheels match the Python version and ABI.
- Platform tags match `x86_64` or `aarch64`.
- Whether libc is glibc or musl and which one the package supports.
- Source builds have the target toolchain and dependencies.

### Node.js and Native Addons

Some npm packages download prebuilt platform binaries or compile addons via `node-gyp`. CI must ensure addons are compiled for the target architecture and Node ABI version. Never copy `node_modules` from an x86 host into an Arm image if it contains native addons.

### Java and JNI

Pure Java bytecode is typically architecture-independent, yet JNI libraries, native compression, cryptography providers, or agents containing native binaries still depend on CPU and libc. Inspect all libraries loaded at runtime.

### libc and Base Images

Alpine typically uses musl; many Debian/Ubuntu images use glibc. A binary compiled against glibc will not necessarily run on musl. Even with the right CPU architecture, an incompatible libc or ABI causes `not found`, `exec format error`, or missing symbol errors on startup.

## 9. Verifying Images and Binaries Before Release

### Inspecting the Index

~~~bash
docker buildx imagetools inspect registry.example.com/team/orders-api:1.4.0
~~~

Confirm the index lists all required OS, architecture, and variant entries. Also check base images and dependent images if the pipeline spans multiple stages or downloads external binaries.

### Inspecting a Running Image

Inside a container:

~~~bash
uname -m
cat /etc/os-release
~~~

On a Docker host:

~~~bash
docker image inspect registry.example.com/team/orders-api:1.4.0 \
  --format '{{.Os}}/{{.Architecture}}'
~~~

Note that `docker image inspect` on a local machine shows the variant pulled or loaded into that machine's local image store; it does not replace inspecting the index in the registry.

### Inspecting Executables

On Linux, you can use:

~~~bash
file /orders-api
readelf -h /orders-api
ldd /orders-api
~~~

`file` and `readelf` identify the file format and machine architecture. `ldd` shows dynamic libraries resolved on the current system; do not run `ldd` on untrusted binaries. For static binaries, `ldd` may report no dynamic dependencies.

### Troubleshooting Common Errors

| Error | Possible Cause | Investigation Direction |
|---|---|---|
| `exec format error` | Wrong-architecture binary or invalid executable file | Check `file`, `readelf`, `TARGETARCH`, and Dockerfile |
| `no matching manifest for linux/arm64` | Index lacks an Arm64 descriptor | Check `imagetools inspect` and publish pipeline |
| `not found` even though file exists | Missing dynamic loader or incompatible libc | Check `readelf -l`, `ldd`, and base image |
| `undefined symbol` | Incompatible native library/ABI | Check library versions, build toolchain, and runtime |
| Runs correctly but slowly | Differences in CPU, SIMD, memory, or dependencies | Benchmark natively on the target instance |
| Some nodes pull successfully, others fail | Mutable tag changed, cache, registry mirror, or different architecture | Pin digest, inspect index, and check runtime logs |

## 10. Testing on Both x86 and Arm

A multi-architecture pipeline must validate each variant. At a minimum:

1. Successful build for each target.
2. Pulling the image on a runner or node of the matching architecture.
3. Checking the entrypoint and health checks.
4. Running relevant unit/integration tests.
5. Verifying connectivity to databases, storage, queues, and external services.
6. Testing native libraries, TLS, compression, and codecs if used.
7. Measuring startup time, memory, and CPU on real hardware.
8. Verifying graceful shutdown and signal handling.

### Cross-Testing and Native Testing

You can run `docker run --platform linux/arm64` on an x86 host if emulation is configured. This works for smoke tests, though it does not prove performance, driver stability, or behavior on real Arm CPUs.

For critical workloads, run at least a native canary on each architecture. Test scenarios sensitive to CPU features, atomic operations, concurrency, memory ordering, codecs, or native libraries.

### Benchmarking and Instance Selection

Do not assume an Arm instance with the same vCPU count has the same performance as an x86 instance. Measure:

- Throughput and p95/p99 latency.
- CPU utilization, throttling, and memory bandwidth.
- RSS, heap, garbage collection, and page faults.
- I/O and network throughput.
- Startup time and warm-up duration.
- Cost per successful request or job.

A workload may perform better on Arm in performance-per-watt or price-performance, depending on CPU generation, runtime, and application characteristics. Base decisions on representative benchmarks.

## 11. Deploying on Mixed-Architecture Compute Clusters

When a cluster contains both x86 and Arm nodes, the scheduler needs to know which architectures each workload supports. Multi-architecture images enable sharing one tag, but they do not guarantee node capacity or that the workload has been tested.

### Kubernetes

Kubernetes applies standard node labels:

- `kubernetes.io/arch=amd64`
- `kubernetes.io/arch=arm64`

If an image supports both architectures, Pods can run on both node types. If an application supports only one architecture, use a `nodeSelector` or node affinity to constrain placement.

Example restricting a workload to Arm64 only:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: image-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: image-worker
  template:
    metadata:
      labels:
        app: image-worker
    spec:
      nodeSelector:
        kubernetes.io/arch: arm64
      containers:
        - name: worker
          image: registry.example.com/team/image-worker:2.1.0
          resources:
            requests:
              cpu: "1"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "2Gi"
~~~

With a multi-architecture image, you can omit `nodeSelector` once the workload has been tested on both node types so the scheduler can place Pods based on available capacity. If you need to prefer one architecture or avoid nodes with incompatible accelerators/drivers, use node affinity and taints/tolerations according to cluster design.

### Cluster Components to Verify

- Node pools carry accurate architecture labels.
- DaemonSets, CNI, CSI, monitoring agents, and security agents support the node architecture.
- Sidecars and init containers also have compatible images.
- Admission policies or deployment policies do not accidentally pin a single-architecture image.
- Autoscalers can provision node pools of the right architecture with sufficient quota.
- Pod disruptions and rollouts do not concentrate all replicas on a single architecture unintentionally.

A main application with a multi-architecture image whose sidecar only exists for `amd64` will still fail on Arm. Check every container in the Pod.

### VMs and Managed Container Services

With VM groups or managed container services, confirm the instance family supports the desired architecture and the platform offers corresponding node pools. Some services support Arm in certain regions or instance types while lacking support for all features. Verify compatibility of platform-managed agents, extensions, monitoring, and runtimes.

## 12. Designing a CI/CD Pipeline for Multi-Architecture Images

~~~mermaid
flowchart TD
    S["Source + Dockerfile"] --> B["Build for amd64 and arm64"]
    B --> T["Test each variant"]
    T --> Q["Scan vulnerabilities and generate SBOM"]
    Q --> P["Push manifests/layers"]
    P --> I["Create or verify OCI index"]
    I --> V["Sign and publish digest"]
    V --> C["Canary on x86 and Arm nodes"]
    C --> R["Controlled rollout"]
~~~

### Key Steps

1. **Source pinning:** lock dependency versions and base images by digest when needed.
2. **Build matrix:** build `linux/amd64` and `linux/arm64` targets.
3. **Platform testing:** run tests on native runners or controlled emulation environments.
4. **Security scanning:** scan each variant and its layers; store results keyed by digest.
5. **SBOM and provenance:** generate a Software Bill of Materials and build provenance for each artifact or index depending on tooling.
6. **Publish:** push manifests and index to the registry.
7. **Verify:** confirm the index has all expected descriptors and digests.
8. **Sign:** sign the published digest and verify signatures before deployment.
9. **Canary:** deploy a subset of replicas onto each architecture.
10. **Rollout:** expand gradually once health checks and metrics pass.

### Managing Build Caches

BuildKit caching speeds up builds, but caches must be scoped properly by target architecture and toolchain. Avoid reusing `amd64` native artifacts for `arm64` simply because a cache key omitted the target. Include `TARGETPLATFORM`, compiler version, and dependencies in cache keys where needed.

Never store credentials or sensitive data in build caches. Pass build secrets using BuildKit secret mounts rather than embedding them in layers or public build arguments.

## 13. Security and Software Supply Chain

A multi-architecture image has multiple manifests and layers, so provenance controls must cover the entire artifact set:

- Use official or organization-approved base images.
- Pin digests for reproducible builds.
- Scan each variant for vulnerabilities, since package sets can differ.
- Generate SBOMs reflecting the exact binaries and packages in each image.
- Store provenance including source commit, builder, toolchain, and target platform.
- Sign the index digest or artifacts according to organizational signing policy.
- Allow only approved registries and workload identities.
- Verify signatures and policies prior to deployment.

A clean scan of an `amd64` image does not prove the `arm64` image is safe. The two variants may contain different packages or dependencies because package managers select different artifacts per architecture.

## 14. Example: Building a Multi-Architecture Go Image

Suppose an API is written in Go without CGO and must run on both x86-64 and Arm64 VMs. The Dockerfile in Section 6 used `BUILDPLATFORM` to keep the compiler running natively on the builder and `TARGETOS`/`TARGETARCH` to produce the target binary.

Execution workflow:

~~~bash
# Inspect builder and supported platforms
docker buildx inspect --bootstrap

# Build and publish both architectures
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/team/orders-api:1.4.0 \
  --push .

# Inspect the OCI index
docker buildx imagetools inspect \
  registry.example.com/team/orders-api:1.4.0
~~~

After publishing:

1. Pull the tag on an x86 runner and check the image architecture.
2. Pull the same tag on an Arm runner and check the image architecture.
3. Run health checks and integration tests on both.
4. Run benchmarks on native instances.
5. Record the index digest and sign the artifact.
6. Deploy a canary onto each node pool before scaling out.

If the application requires CGO, the team must add a cross-toolchain or build natively on each architecture. Do not keep `CGO_ENABLED=0` if the application actually requires native libraries.

## 15. Common Errors and Remediation

| Symptom | Common Cause | Fix |
|---|---|---|
| `exec format error` on Arm | x86 binary packaged into Arm image or vice versa | Inspect `file`, `readelf`, `TARGETARCH`, and build stage |
| Registry reports no matching manifest | Index is missing the required platform | Build/push missing platform and re-verify index |
| Runtime missing `.so` | Copied wrong-architecture or wrong-ABI native library | Install/build dependencies in the target stage |
| Python package fails to install on Arm | No matching wheel or missing toolchain | Check wheel tags, build from source, or pick a supported version |
| Node addon fails at startup | `node_modules` contains binaries from another architecture | Install dependencies in the target build stage |
| Image works but runs slowly on one architecture | Compiler flags, CPU features, or dependency differences | Benchmark natively and profile per platform |
| Pod pending or unscheduled | Node selector/affinity mismatches labels or lacks capacity | Check node labels, taints, affinity, and autoscaler |
| Sidecar fails on Arm | Helper image exists only for `amd64` | Switch to an Arm-compatible image or constrain Pod to compatible nodes |
| CI reuses wrong artifact | Cache key fails to distinguish target architecture | Separate caches by target and toolchain |

## 16. Pre-Release Checklist for Multi-Architecture Images

- [ ] Target platforms such as `linux/amd64` and `linux/arm64` are explicitly defined.
- [ ] Base images support all target platforms.
- [ ] All executables and native libraries are compiled for the target architecture.
- [ ] Python/Node/Java/JNI or native package dependencies are verified.
- [ ] Compiler flags do not require CPU features beyond the node pool baseline.
- [ ] Buildx builder supports all required platforms.
- [ ] Registry contains an OCI index with complete descriptors and digests.
- [ ] Index verified with `docker buildx imagetools inspect`.
- [ ] Smoke/integration tests passed on each architecture.
- [ ] Representative benchmarks completed on native hardware.
- [ ] Sidecars, init containers, DaemonSets, and agents are compatible.
- [ ] Kubernetes node selectors/affinity match image capabilities.
- [ ] SBOM, scanning, provenance, and signatures apply to each variant.
- [ ] Release digest is recorded for rollback and reproducibility.
- [ ] Canaries on x86 and Arm pass health checks before broad rollout.

## 17. Applied Exercise

A team deploys an image-processing service on a Kubernetes cluster with 70% x86-64 nodes and 30% Arm64 nodes. Currently, the image is built on an x86 runner, runs fine on x86 nodes, yet fails on Arm nodes with `exec format error`. The Dockerfile uses an official base image and copies the build directory from the CI machine into the image. The application includes a native library for image decoding.

1. Why does the container still fail on Arm nodes even though the base image supports Arm?
2. Which metadata should be checked in the OCI index and executable?
3. Propose two approaches to build images for both architectures: cross-compilation and a native build matrix.
4. How should the native library be handled to guarantee the right architecture and ABI?
5. Which components beyond the main container must be tested before expanding the rollout?
6. If image-processing performance differs between Arm and x86, which metrics should the team compare?

Hint: the build directory likely contains an x86 binary copied directly into the Arm image. Inspect `file`, `readelf`, target platform, and the index; rebuild both the executable and native library for each target. You can cross-compile if the toolchain and sysroot support it, or run native builds on both runner types and merge them into a manifest index. Verify sidecars, init containers, agents, health checks, startup, and benchmark throughput/latency/CPU/memory on real hardware.

## Conclusion

Multi-architecture images use an OCI image index so one shared reference points to manifests matching each OS and CPU architecture. This simplifies deployment across x86 and Arm clusters, though it does not automatically translate binaries or dependencies. To release safely, pipelines must build for the proper targets, handle native libraries and ABIs, verify the index, test every variant on appropriate hardware, and validate all sidecars and platform components. Combining immutable digests, SBOMs, provenance, signing, and per-architecture canaries keeps images reproducible, auditable, and reliable in production.
