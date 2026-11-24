# Managing Base Images by Tag, Digest, and CPU Architecture in a Spring Boot Dockerfile

## 1. Goal: Choose the Right Platform, Stay Reproducible, and Patch Security Issues

A Spring Boot executable JAR can run across multiple CPU architectures if its code and dependencies are compatible, yet **a container image is not automatically multi-architecture**. A base image contains a minimal operating system, a Java runtime, and potentially native libraries, so it depends on **OS/CPU architecture** and the exact base image version.

A very familiar Dockerfile:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/base-demo-0.1.0.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

raises three operational choices:

1. **Tag** `17-jre`: a human-friendly name, yet the publisher can update what sits behind that tag.
2. **Digest** `sha256:...`: a content-addressed identifier naming a specific manifest/index, enabling auditing and pinning the base image.
3. **Platform** `linux/amd64`, `linux/arm64`...: selects the image variant matching the target CPU/kernel/runtime for deployment.

If a developer uses an ARM64 laptop while production servers are AMD64, Docker may pull **two different variants** of the same multi-platform tag. If CI rebuilds months later, the tag may point to **newer JRE/OS patches**. That behavior can help security, yet it does not produce a byte-for-byte reproducible build.

**Target outcomes for this lesson:**
- Understand that tag, digest, manifest, manifest list/OCI index, and platform are distinct concepts.
- Inspect image references and publisher-released architectures using Docker Buildx.
- Pin images by digest without fabricating a SHA-256 value.
- Create a Spring Boot Java 17 JAR and Dockerfile runnable on `linux/amd64`/`linux/arm64` when supported by the base.
- Build and push a tested multi-platform image and choose the right artifact reference for deployment.
- Balance **stability, vulnerability patching, CI speed, and CPU support**.

Examples use Spring Boot **3.5.0**, Java 17, and Docker Buildx/BuildKit for self-consistent documentation; this is not a claim about the latest versions. Real digests must be retrieved directly from **the registry at pinning time**, never invented or copied from old articles.

## 2. Three Identifiers of a Base Image: Repository, Tag, and Digest

Typical Docker/OCI reference:

```text
docker.io/library/eclipse-temurin:17-jre

registry/repository              tag
          \                       /
     eclipse-temurin           17-jre
                 \              /
          eclipse-temurin:17-jre

eclipse-temurin:17-jre@sha256:<64 hex characters>
                  \            /
                tag         pinned digest
```

`<64 hex characters>` in the diagram is **format notation**, not a real digest or runnable Docker command.

| Component | Meaning | Can Change Over Time? |
| --- | --- | --- |
| Registry host | Image distribution host, e.g., Docker Hub or enterprise registry | Can migrate or change ownership |
| Repository | Image namespace/name, e.g., `eclipse-temurin` | Stable logical name per publisher |
| Tag | Human-readable alias, e.g., `17-jre`, `17-jre-jammy`, `0.1.0` | **Mutable**: tag can be reassigned to a new manifest/index |
| Digest | Hash of the referenced manifest/index object | Hashed bytes are fixed; registry may stop retaining/serving the object |
| Platform | OS/architecture[/variant] used to pick executable/container layers | Not a version; does not replace digest |

### 2.1. A Tag Is Only a Name, Not an Immutability Guarantee

`FROM eclipse-temurin:17-jre` means "use whatever image the registry currently returns for tag `17-jre`." The publisher can update this tag to patch CVEs, update Java 17 patches, or update OS packages according to its release policy.

Even a very specific-looking tag like `17.0.x_yy-jre` is **not automatically immutable** unless the registry/publisher enforces immutable-tag rules. Many private registries support tag immutability policies; that is a registry policy, not an inherent property of tag syntax.

**Risk:** the same Dockerfile and same Git commit built at two points in time can pull two different base images. Never treat `:latest` as a reproducibility strategy; omitting a tag defaults to `latest`.

### 2.2. A Digest References an Exact Manifest or Index

Syntax:

```text
eclipse-temurin@sha256:<64-hex>
eclipse-temurin:17-jre@sha256:<64-hex>
```

When a reference contains both tag and digest, **the digest determines the fetched object**; the tag serves as readable context without causing the builder to ignore the digest and pull the newest tag. Docker docs describe pinning with `image:tag@sha256:...` to prevent unexpected tag drift.

**Do not confuse** a manifest/index digest with:
- `docker image inspect .Id`, which is usually the **image config** digest;
- the SHA-256 of a compressed layer;
- the SHA-256 of executable `app.jar`;
- a Git commit hash or version string in a tag;
- `RepoDigests` after pulling, whose visible digest type/value can depend on the registry and image store.

Those hash **different objects**. To pin `FROM`, you need a **digest reference served by the registry**, never a JAR hash pasted into `FROM`.

### 2.3. Pros and Costs of Pinning

**Pros:** stable underlying dependencies, easy CVE tracing and rollbacks, exact auditing of which base version was used, and protection against silent publisher changes.

**Costs:** pinning indefinitely without updating means **missing automatic security patches**. A digest may also be garbage-collected by registry retention policies, breaking future rebuilds even when source is intact. Pinning must therefore pair with a **scheduled or alert-driven digest update workflow**, scanning/testing, change review, and provenance.

## 3. What Is CPU Architecture and How Does It Differ from Java Bytecode?

A Docker platform typically takes the form:

```text
os/architecture[/variant]

linux/amd64
linux/arm64
linux/arm/v7
windows/amd64
```

In Linux containers:
- `amd64`: x86-64 architecture, often reported by `uname -m` as `x86_64`.
- `arm64`: 64-bit ARM/AArch64, often reported by `uname -m` as `aarch64`.
- `arm/v7`: 32-bit ARM with specific variant; cannot be treated as equivalent to `arm64`.
- `windows/amd64` is a Windows container platform, **not** `linux/amd64`.

A compiled Java 17 `.class` file normally shares the same bytecode format on AMD64 and ARM64. Yet the JVM binary, libc, JNI/JNA libraries, native-images, native executables, and shell utilities inside the base image are **platform-dependent**.

```text
Spring Boot bytecode .jar
          |
          +--> Linux AMD64 JRE + amd64 native libs --> linux/amd64 image
          |
          +--> Linux ARM64 JRE + arm64 native libs --> linux/arm64 image
```

**Conclusion:** "Java write once, run anywhere" does not make a single-architecture OCI image run natively across every CPU architecture. You need the right base variant for each platform, and all native/OS components must match.

### 3.1. Not Just CPU: OS and ABI Matter Too

Two `linux/amd64` bases can still differ in:
- distro `Ubuntu/Debian` vs `Alpine Linux`;
- `glibc` vs `musl`;
- package manager `apt` vs `apk`;
- CA certificates, locale/tzdata, shell, fonts, and OpenSSL native libraries;
- non-root user/permissions and image update policies.

Do not swap `eclipse-temurin:17-jre` to an Alpine or distroless variant purely for smaller size without testing JNI/native dependencies and runtime behavior. A matching Java version **does not guarantee native ABI compatibility**.

## 4. Multi-Platform Images: One Tag, Multiple Manifests

A multi-platform image reference normally points to an **OCI image index** or **Docker manifest list**:

```text
eclipse-temurin:17-jre  (tag)
           |
           v
OCI index / manifest list  ---> index digest sha256:INDEX...
           |
           +--> linux/amd64 manifest ---> amd64 config + amd64 layers
           |
           +--> linux/arm64 manifest ---> arm64 config + arm64 layers
           |
           +--> other platforms, if published by the maintainer
```

In the diagram, `INDEX...` is descriptive notation, not a real hash. When pulling/running via tag/index, Docker picks the child manifest matching the target platform (e.g., the Linux container host's native architecture). Users can specify platforms explicitly with `docker pull --platform`, `docker run --platform`, or `docker buildx build --platform`.

### 4.1. Index Digests Differ from Child Manifest Digests

| Digest Type | What It Identifies | Effect When Used |
| --- | --- | --- |
| **Index digest** | The list of platform variants and their referenced manifests | Pins a **specific set of platform variants**; builder picks matching variant from that set |
| **Platform manifest digest** | One concrete image variant, e.g., `linux/amd64` | Pins **one** platform; other platforms are unavailable |
| **Config digest** | Image variant JSON configuration | Cannot replace a manifest/index reference in `FROM` |
| **Layer digest** | One compressed filesystem layer | Does not describe the full base image |

If the goal is building one Dockerfile for both AMD64 and ARM64, the **index digest** fits better than a child manifest digest, *provided the index actually includes both platforms*. Pinning the `linux/amd64` child digest and then building for `linux/arm64` causes platform mismatches, pull failures, or non-executable runtime components.

**Do not assume pinning an index digest turns every architecture into the same binary.** AMD64 and ARM64 still have separate manifests, configs, and layers; the index digest simply locks **the list and references** pointing to them.

### 4.2. When No Matching Variant Exists

If a publisher only ships `linux/amd64` while CI asks for `linux/arm64`:
- the builder may fail with **no match for platform in manifest**;
- workflows attempting to run AMD64 binaries on ARM may need QEMU emulation;
- running an incompatible binary natively on the host hits `exec format error`.

No Dockerfile flag turns an AMD64 JRE into ARM64. Choose an image with an ARM64 variant or build/distribute a base matching the CPU architecture under proper controls.

## 5. Inspecting a Base Image Before Using It

### 5.1. Listing Manifests/Index in the Registry

Docker Buildx:

```bash
docker buildx imagetools inspect eclipse-temurin:17-jre
```

The tool reads image reference metadata from the registry. For a multi-platform image, output typically resembles:

```text
Name:       docker.io/library/eclipse-temurin:17-jre
MediaType:  ...
Digest:     sha256:...
Manifests:
  Name:     ...@sha256:...
  Platform: linux/amd64
  Name:     ...@sha256:...
  Platform: linux/arm64
```

This is an **output structure illustration**, not a real digest, and does not guarantee a tag always has those exact variants or display formatting. Always inspect actual platforms from the registry at execution time.

View the raw JSON manifest:

```bash
docker buildx imagetools inspect --raw eclipse-temurin:17-jre
```

When the reference points to an index/list, JSON includes `manifests[]`, where entries typically carry `digest`, `platform.os`, `platform.architecture`, and optionally `variant`. **Do not mistake** additional attestation manifests labeled `unknown/unknown` in some releases for a runnable CPU architecture.

If `jq` is installed on Linux/macOS:

```bash
docker buildx imagetools inspect --raw eclipse-temurin:17-jre |
  jq -r '.manifests[]? |
         select(.platform.os == "linux") |
         "\(.platform.os)/\(.platform.architecture)"'
```

This script works when the reference returns an **index/list** with a `manifests` array; a **single-platform manifest** lacks that array, so empty output does not necessarily mean the image has no platform. Inspect `mediaType` and `config` if the output is not an index.

### 5.2. Reviewing the Digest Being Pinned

A reliable manual workflow:
1. Pick a tag per policy (`17-jre` or a narrower tag).
2. Run `docker buildx imagetools inspect IMAGE:TAG`.
3. Read the top-level `Digest: sha256:...` at the **reference/index level** if pinning multi-platform.
4. Confirm `Manifests` contains `linux/amd64` and `linux/arm64` as required.
5. Copy the real digest **verbatim** into the Dockerfile or CI config manifest; review the diff.
6. Record registry provenance, inspection timestamp, human-readable tag, and security scan report.

**Never copy a digest from an online blog post or type 64 made-up hex characters.** The digest must come from the publisher/registry your CI actually pulls from, since mirrored, retagged, or rebuilt images can have different digests.

### 5.3. Distinguishing Remote Registry Inspection from Local Image Inspection

`docker buildx imagetools inspect`: inspects the manifest/index **in the registry**. `docker image inspect`: inspects an image/config already in the **local image store**, usually the pulled/loaded variant.

Example:

```bash
docker pull --platform linux/amd64 eclipse-temurin:17-jre
docker image inspect --format '{{.Os}}/{{.Architecture}}' eclipse-temurin:17-jre
```

When the local store holds the AMD64 variant, expected output:

```text
linux/amd64
```

If the local store supports multi-platform images and holds multiple variants, inspecting may require selecting a platform (depending on Docker API/Engine version). Therefore, to audit **all variants in a registry**, prefer `imagetools inspect` over relying on a local `image inspect`.

## 6. Choosing a Versioning Strategy for the Base Image

### 6.1. Three Common Reference Styles

```dockerfile
# A. Easy-to-update yet mutable tag:
FROM eclipse-temurin:17-jre

# B. Narrower tag, still mutable:
FROM eclipse-temurin:17-jre-jammy

# C. Digest-pinned:
# FROM eclipse-temurin:17-jre@sha256:<actual digest returned by registry>
```

Line C is commented out because it requires a real digest and cannot run as-is. **A and B are valid runnable Dockerfile lines**, assuming the publisher still serves those tags. Actual pinning syntax:

```text
FROM image:human-readable-tag@sha256:64-hex-digit-digest
```

The syntax diagram above is not a real Dockerfile. Never use descriptive placeholder text as a digest; substitute a verified value.

### 6.2. Decision Table

| Strategy | Base Image Reproducibility | Automatic Patches via Tag | Operational Work |
| --- | --- | --- | --- |
| `:latest` | Low | Possible | High risk of surprise updates |
| `:17-jre` | Not guaranteed | Usually on fresh rebuild/pull | Must test after tag moves |
| `:17-jre-jammy` | Not guaranteed | Possible within that distro/Java line | Better control of OS family |
| `:tag@sha256:index` | Pins exact multi-platform index | **Does not change automatically** | Track and update digest deliberately |
| `@sha256:platform-manifest` | Pins a single variant | Does not change automatically | Manage each architecture separately |
| Registry with immutable tag policy | Good within registry/policy scope | Depends on workflow creating new tags | Must verify policy and retention |

**Practical recommendation:** production/releases should know the **exact digest** of every base image. Pin digests when auditing and reproducibility matter, paired with a periodic and CVE-triggered update process. In development, short tags are fine for quick tests, yet CD should never pull a mutable tag without recording the image digest.

## 7. Do Not Hardcode CPU Architecture in the Dockerfile for Multi-Arch Builds

An anti-pattern:

```dockerfile
FROM --platform=linux/amd64 eclipse-temurin:17-jre
```

This line forces the stage to AMD64. When running `docker buildx build --platform linux/amd64,linux/arm64`, hardcoding `FROM` can put an AMD64 binary/runtime inside the ARM64 image, or trigger build failures/warnings. Docker Build Check `FromPlatformFlagConstDisallowed` advises **against hardcoding a constant platform** in `FROM` when targeting multi-platform builds.

**Right for the runtime stage:**

```dockerfile
FROM eclipse-temurin:17-jre
```

When building:

```bash
docker buildx build --platform linux/amd64 .
docker buildx build --platform linux/arm64 .
```

Docker/BuildKit selects the base variant for the **target platform** from the build command. Running without `--platform` usually defaults to the builder's native platform, which may not match every production node.

### 7.1. `BUILDPLATFORM` Differs from `TARGETPLATFORM`

BuildKit automatically supplies platform build arguments:

| ARG | Meaning | Example Value |
| --- | --- | --- |
| `BUILDPLATFORM` | Platform of the machine/node running the builder | `linux/arm64` |
| `BUILDOS`, `BUILDARCH` | OS/CPU components of the builder | `linux`, `arm64` |
| `TARGETPLATFORM` | Requested platform for the output image | `linux/amd64` |
| `TARGETOS`, `TARGETARCH` | OS and CPU of the output image | `linux`, `amd64` |
| `TARGETVARIANT` | Specific variant if applicable | `v7`, `v8`, or empty |

Example building an AMD64 image on an ARM64 laptop:

```text
BUILDPLATFORM = linux/arm64
TARGETPLATFORM = linux/amd64
```

They do not have to match. Specifically in multi-stage builds, you can run a **pure-Java compilation stage** on the native build platform and assemble the final runtime image on the target platform.

### 7.2. `ARG` Is Scoped: Redeclare to Use Inside `RUN`

BuildKit makes `BUILDPLATFORM`/`TARGETPLATFORM` available in global scope for `FROM`, yet to use them in a stage's `RUN` instruction, declare `ARG` inside that stage:

```dockerfile
# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM alpine:3.21 AS diagnostic

ARG BUILDPLATFORM
ARG TARGETPLATFORM
ARG TARGETARCH

RUN printf 'builder=%s target=%s arch=%s\n' \
    "$BUILDPLATFORM" "$TARGETPLATFORM" "$TARGETARCH"
```

This is a **diagnostic Dockerfile fragment**, not a complete Java application Dockerfile. Tag `alpine:3.21` can change and should be digest-pinned if production reproducibility is required. `RUN` in this stage executes on the build platform, while the target can differ.

**Note:** `FROM --platform=$BUILDPLATFORM` is an intentional optimization for a **build stage**; never put it on the **final runtime stage** when you want output matching `TARGETPLATFORM`.

## 8. Complete Runnable Spring Boot Java 17 Example

We create a small API with:
- `GET /ready` returning a fixed `ready` response.
- `GET /arch` returning the Java runtime architecture via `System.getProperty("os.arch")`, letting us observe the JRE variant.

### 8.1. Project structure

```text
base-demo/
├── pom.xml
├── Dockerfile
├── .dockerignore
└── src/
    └── main/
        └── java/
            └── com/example/base/
                └── BaseDemoApplication.java
```

You need Docker Buildx/BuildKit and network access for the builder to download Maven/plugins and registry base images. To run Maven on the host, you need JDK 17+ and compatible Maven 3.9.x. For multi-platform ARM on AMD64 (or vice versa), the builder must support that architecture via QEMU or native nodes.

### 8.2. Complete `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>base-demo</artifactId>
    <version>0.1.0</version>
    <packaging>jar</packaging>
    <name>base-demo</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot starter parent manages dependency/plugin versions; `spring-boot-maven-plugin` is declared so `repackage` builds an executable JAR during Maven `package`.

### 8.3. Runnable Java code

**`src/main/java/com/example/base/BaseDemoApplication.java`:**

```java
package com.example.base;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class BaseDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BaseDemoApplication.class, args);
    }

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    @GetMapping("/arch")
    public String arch() {
        return System.getProperty("os.arch");
    }
}
```

`System.getProperty("os.arch")` returns the Java runtime/OS architecture string, which **does not always match** Docker's architecture label verbatim. On Linux AMD64 it is typically `amd64`, whereas on ARM64 it is typically `aarch64`; inspect actual values rather than hardcoding a gate without mapping.

### 8.4. Testing on the Host Without Docker

```bash
mvn -B -ntp clean package
java -jar target/base-demo-0.1.0.jar
```

In another terminal:

```bash
curl -fsS http://localhost:8080/ready
```

**Exact response body:** `ready` (no extra newline added). `GET /arch` returns the `os.arch` string of **the JVM running on the host**, not the Docker build target. Stop the server with Ctrl+C.

## 9. Multi-Stage Dockerfile Using Tags, Easily Swapped for Digests

**Complete `Dockerfile`:**

```dockerfile
# syntax=docker/dockerfile:1

ARG BUILD_IMAGE=maven:3.9-eclipse-temurin-17
ARG RUNTIME_IMAGE=eclipse-temurin:17-jre

FROM --platform=$BUILDPLATFORM ${BUILD_IMAGE} AS build
WORKDIR /workspace

COPY pom.xml ./
COPY src ./src

RUN mvn -B -ntp clean package

FROM ${RUNTIME_IMAGE} AS runtime
WORKDIR /app

COPY --from=build /workspace/target/base-demo-0.1.0.jar /app/app.jar

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**Exact explanation:**

1. `ARG BUILD_IMAGE` and `ARG RUNTIME_IMAGE` are declared **before `FROM`** so they can parameterize base image names. The defaults are easy-to-test tags, still **mutable**.
2. `FROM --platform=$BUILDPLATFORM ... AS build` runs Maven/JDK on the builder's native architecture. Since this demo emits **pure Java bytecode/JAR with no native build artifacts**, that single JAR can be copied to either an AMD64 or ARM64 runtime stage.
3. `FROM ${RUNTIME_IMAGE} AS runtime` sets **no** fixed platform; Buildx picks the runtime variant matching the target.
4. `COPY --from=build .../base-demo-0.1.0.jar` grabs the **exact Maven executable JAR**, leaving behind the compiler, source code, and `~/.m2`.
5. `USER 10001` runs the app as non-root; the app only needs to read the JAR and listen on port 8080 (unprivileged). The copied file has appropriate read permissions in standard image builds.
6. Exec-form `ENTRYPOINT` delivers signals to the Java process more reliably than a shell form lacking `exec`.
7. `EXPOSE 8080` is metadata only; map/publish ports when running if host access is needed.

### 9.1. Why Not Put a Fake Base Digest in This Lesson?

Digests depend on real objects in the registry. Putting an invented `sha256` into the Dockerfile causes `docker build` to fail or, worse, misleads learners into believing the image is pinned.

The Dockerfile above is **runnable with tags**, while CI can inject pinned references **without editing source**:

```bash
docker buildx build \
  --build-arg RUNTIME_IMAGE=eclipse-temurin:17-jre \
  -t base-demo:local \
  --load .
```

Once you fetch a real **index or manifest** digest via `docker buildx imagetools inspect eclipse-temurin:17-jre`, pass that reference as `eclipse-temurin:17-jre@sha256:<actual-digest>` into `RUNTIME_IMAGE`. Do the same for `BUILD_IMAGE` when pinning the Maven builder too.

**Important:** pinning only runtime while leaving `maven:3.9-eclipse-temurin-17` and the Dockerfile frontend mutable can still alter build outputs due to compiler, plugin, tooling, or dependency resolution changes. End-to-end reproducibility requires pinning/controlling the **entire build chain**, not just the final JRE base.

### 9.2. `.dockerignore` File

**`.dockerignore`:**

```dockerignore
.git
.idea
.vscode
target
build
.gradle
**/node_modules
.env
*.pem
*.key
*.p12
```

This Dockerfile copies only `pom.xml` and `src`, so accidental copying is unlikely, yet `.dockerignore` still shrinks the build context, protects local data, and prevents accidentally packaging sensitive files if the Dockerfile evolves. It **does not protect** secrets placed inside `src/main/resources`; keep secrets out of source and inject them via runtime secret mechanisms.

### 9.3. When Is a Native-Platform Build Stage Unsafe?

`FROM --platform=$BUILDPLATFORM ... AS build` works when the build output is **CPU-neutral Java bytecode**. However, if a project:
- compiles JNI/shared `.so` libraries;
- produces native-image/GraalVM outputs;
- downloads binaries based on `uname -m` during the build;
- generates arch-specific artifacts;
- runs annotation/code generators tied to CPU or native libc;

then the JAR and native components may **not be portable**. Build separately per `TARGETARCH`, cross-compile with a proper toolchain, or run the build stage on a target-native builder. Never copy an ARM64 binary from a builder into an AMD64 runtime (or vice versa).

## 10. Building a Single-Architecture Image and Verifying Runtime

### 10.1. Local Single-Platform Build

When your machine/builder supports AMD64:

```bash
docker buildx build \
  --platform linux/amd64 \
  -t base-demo:amd64 \
  --load .
```

`--load` loads the single-platform build into the local Docker image store in common Buildx setups. On modern builders/engines with multi-platform image stores, loading capabilities vary; this example **requests only one platform**.

Run:

```bash
docker run --rm \
  --platform linux/amd64 \
  -p 127.0.0.1:8080:8080 \
  base-demo:amd64
```

Another terminal:

```bash
curl -fsS http://localhost:8080/ready
```

**Response body:** `ready`.

Check the image platform in the local store:

```bash
docker image inspect \
  --format '{{.Os}}/{{.Architecture}}' \
  base-demo:amd64
```

**Expected result for the right variant:** `linux/amd64`. `docker image inspect` and `docker buildx imagetools inspect` differ: one inspects local image config, while the other inspects the remote registry manifest/index.

### 10.2. Trying ARM64

If your builder and host or emulator support it:

```bash
docker buildx build \
  --platform linux/arm64 \
  -t base-demo:arm64 \
  --load .
```

Running an ARM64 image on an AMD64 host requires proper **emulation/runtime support**; without it, you may hit `exec format error`. More reliably, run the image on a **real ARM64 node** in CI/cloud.

`GET /arch` on the two architectures returns `amd64`/`aarch64` from Java, yet Docker image platform must be checked via manifest/image metadata. Never treat the `os.arch` string as absolute proof of OCI index metadata.

## 11. Building and Pushing an Image Supporting Both AMD64 + ARM64

### 11.1. Check What Your Builder Supports

```bash
docker buildx version
docker buildx ls
docker buildx inspect --bootstrap
```

`inspect --bootstrap` lists the platforms the builder can handle. If your current builder lacks multi-platform support, a common setup uses the `docker-container` driver:

```bash
docker buildx create \
  --name multiarch-builder \
  --driver docker-container \
  --use \
  --bootstrap
```

Run `create` only if no builder with that name exists; if it already exists, switch to it. Docker Desktop usually comes with binfmt/QEMU preconfigured; Linux Docker Engine may need QEMU/binfmt or dedicated builder nodes. Never automatically install QEMU onto production machines just to test multi-platform builds; use managed CI builders.

**Three strategies:**
1. **QEMU emulation:** quick setup, yet can be very slow for Maven/apt/native builds.
2. **Native AMD64 + ARM64 builder nodes:** faster with better compatibility, requires infrastructure.
3. **Cross-compilation:** good when language/toolchain supports it; with pure Java bytecode, you can build once on a native builder and copy into multiple runtime variants as in our demo.

### 11.2. Publishing a Multi-Platform Index to a Registry

Requires push access to a valid image repository; in CI, `IMAGE_REF` holds the release-tagged internal repository reference supplied by the pipeline.

```bash
: "${IMAGE_REF:?Set IMAGE_REF to a writable registry image tag}"

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "$IMAGE_REF" \
  --push .
```

`: "${IMAGE_REF:?...}"` is **fail-fast** Bash syntax if the variable is unset; it holds no credentials and assumes no specific learner registry name. CI must provide credentials via `docker login` or a secure credential helper, never hardcoding passwords in the Dockerfile, `ARG`, or Git.

`--push` publishes the image variants and manifest list/OCI index; use it when building multi-platform on a `docker-container` builder. Multi-platform `--load` behavior depends on the image store and Engine version, so the most portable general workflow is **push to the registry and inspect the manifest there**.

### 11.3. Inspecting the Index After Push

```bash
docker buildx imagetools inspect "$IMAGE_REF"
```

You should see at least `linux/amd64` and `linux/arm64`. To inspect JSON with `jq`:

```bash
docker buildx imagetools inspect --raw "$IMAGE_REF" |
  jq -r '.manifests[]? |
         select(.platform.os == "linux") |
         "\(.platform.os)/\(.platform.architecture)"'
```

When Buildx attaches SBOM/provenance attestations, `unknown/unknown` entries can appear in the index; **do not mistake those for CPU errors** as long as the required platform variants exist. Conversely, if the index contains only `linux/amd64`, putting "multiarch" in the tag name does not make it a multi-platform image.

### 11.4. Verifying by Pulling and Running per Platform

On an AMD64 runner:

```bash
docker pull --platform linux/amd64 "$IMAGE_REF"
docker run --rm --platform linux/amd64 \
  -p 127.0.0.1:8080:8080 "$IMAGE_REF"
```

On an ARM64 runner (or with valid emulation), switch to `--platform linux/arm64`. `/ready` must always return `ready`. With a multi-architecture image, each runner pulls **different child digests and layers** despite sharing the same tag/index. That is the intended behavior.

## 12. Pinning the Index Digest for Multi-Architecture Deployments

Release workflow:

1. CI builds and pushes `IMAGE_REF` after unit and smoke tests pass.
2. Run `docker buildx imagetools inspect "$IMAGE_REF"` to read the **index digest** of the pushed image.
3. Verify both `linux/amd64` and `linux/arm64` appear in `Manifests`.
4. Record `repository@sha256:<actual-index-digest>` in the release manifest, deployment descriptor, and SBOM/provenance.
5. At deploy time, use the **digest-pinned reference** rather than letting a mutable tag shift silently.
6. Periodically scan and bump base image digests through a tested process; pinning **does not remove the responsibility to patch CVEs**.

Example **deployment notation**:

```text
registry.example.org/team/base-demo@sha256:<real-index-digest>
```

This is a **format template**, not a runnable reference: the registry/repository is illustrative and the digest must be a real value. Never fabricate a random digest in documentation.

**Distinction:** pinning the **output application image's** digest at deploy time and pinning the **input base image's** digest at build time are two separate actions. A trustworthy release captures both:
- source Git commit;
- builder/runtime base image digests;
- Java/Maven/plugin versions;
- application image index digest and per-platform manifests;
- scan/test/attestation evidence.

### 12.1. Do You Need `--platform` in the Dockerfile When Pinning an Index?

No. With a multi-platform index digest, the Dockerfile can write:

```dockerfile
FROM eclipse-temurin:17-jre@sha256:<verified-index-digest>
```

This is **illustrative syntax and will not run until replaced with a real digest**. Keep `FROM` free of `--platform=linux/amd64`; specify the target via:

```bash
docker buildx build --platform linux/amd64 ...
docker buildx build --platform linux/arm64 ...
```

Docker/BuildKit resolves the matching variant inside the **pinned index**. If you pin an **AMD64 child manifest** instead of the index, an ARM64 build fails because no matching variant exists. Always inspect the manifest structure and confirm **which level** your digest points to.

## 13. Dockerfile Build Arguments: Designed for Pinning Yet Easy to Update

Section 9's Dockerfile accepts base references via `--build-arg`. This lets you:
- keep the source Dockerfile clean for review without mistyped digests;
- have CI pin digests via release configuration;
- build from dev tags up to release digests using the same Dockerfile;
- update base images independently of Java source when patching vulnerabilities.

It also carries a risk: if a pipeline passes an empty or wrong `RUNTIME_IMAGE`, the build fails or silently falls back to the mutable default tag.

**CI recommendations:**
- Dev builds may allow default tags.
- Release builds **must** set `BUILD_IMAGE`/`RUNTIME_IMAGE` to pinned digest references, verifying they point to approved registries/providers.
- Log **base image references and digests**, never private registry credentials.
- Never put secrets in `ARG` or `ENV`: values can surface in image metadata, history, and build logs.
- If using a registry mirror, resolve digests from that exact mirror/source.
- Provide a valid default in `ARG` so Docker build check `InvalidDefaultArgInFrom` passes, or validate pipeline inputs explicitly.

### 13.1. Why Do Tag and Digest Appear Together?

`FROM eclipse-temurin:17-jre@sha256:<digest>` tells human readers which Java/runtime line is intended, while the digest locks the exact manifest/index. Even when the publisher moves `17-jre`, the build continues using the pinned digest (as long as the registry retains it).

**Do not auto-resolve a new digest on every build and call it pinning.** If CI resolves the tag to the latest digest on every run and builds right away, it records actual inputs yet skips review of base changes. Good release pipelines update digests via reviewed PRs, scan, test, and publish a new version.

## 14. Base Image Selection, Security, and Support Lifecycle

### 14.1. JDK vs JRE

- The **build stage** needs a JDK, Maven/Gradle, and related toolchains.
- The **runtime stage** normally needs only a JRE compatible with the Java bytecode (e.g., Java 17), without Maven or the compiler.
- Multi-stage Dockerfiles shrink image surface by leaving build tools out of runtime.
- For AppCDS, `jlink`, `native-image`, or specialized features, runtime needs differ; test on the target distro/arch.

### 14.2. Choosing the Right Distro/Variant

When picking `eclipse-temurin:17-jre` or a distro-suffixed tag:
- check publisher docs for Debian/Ubuntu/Alpine variants, patch cadence, and supported architectures;
- verify `linux/arm64` exists rather than guessing from the tag name;
- check native dependencies, locales, TLS certificates, timezones, and fonts if your app relies on them;
- ensure Java 17 remains supported for your expected operational window;
- verify non-root user behavior and required filesystem permissions.

**Do not assume the smallest image is automatically the safest.** Distroless/minimal images shrink OS package surface yet complicate debugging and require intentional handling of CA certs, tzdata, and native libraries.

### 14.3. Security Scanning and SBOMs

Pinning a digest reproduces a **known** base, meaning if that base has a CVE, subsequent builds inherit that CVE too. CI should:
- scan both base and final images using an organization-approved tool (Docker Scout or equivalent);
- generate SBOMs and provenance/attestations where required;
- track publisher updates and automated dependency/base-image PRs;
- review changelogs, CVE fixes, and compatibility;
- rebuild, run unit/integration tests, re-scan, and roll out with canary/rollback controls;
- record old and new index digests, platforms, and output image digests.

### 14.4. Mutable Tags Do Not Guarantee Always Getting the Latest Patch

Docker uses build caches, local images, and pull policies. The same tag-only Dockerfile can reuse stale local cache/layers in one workflow while pulling a fresh manifest in another depending on builder/cache/pull settings. When intentionally checking for an updated tag, configure the appropriate Docker/Buildx pull mode and check the actual manifest digest rather than assuming "every build automatically includes new patches."

Even with `--pull`, **an old pinned digest still pulls the old object**: `--pull` refreshes the exact reference rather than turning a fixed digest into a moving tag.

## 15. Common CPU Architecture Errors in Java/Spring Boot

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| `exec format error` right at container start | Image binary/entrypoint mismatches host arch; no emulation | Check platform manifest, use matching variant or native node/QEMU |
| `no match for platform in manifest` | Tag/digest lacks the requested platform | Run `imagetools inspect` to check list; pick a supported base |
| ARM64 builds fast/cleanly while AMD64 fails | Native dependency/JNI/JDK distro mismatch across arch | Test each platform, inspect build and runtime stages |
| QEMU build runs very slowly | Running heavy Maven/apt/native steps under emulation | Use `--platform=$BUILDPLATFORM` for Java-only build stage or native nodes |
| Java throws `UnsatisfiedLinkError` | App native library mismatches arch or libc | Bundle exact JNI binary per target platform |
| `java: not found` in runtime image | Base image lacks JRE or has different `PATH` | Pick the right JRE image and check entrypoint |
| `UnsupportedClassVersionError` | Build JDK emitted newer bytecode than runtime supports | Set `--release 17`/matching toolchain, Java 17+ runtime |
| `linux/arm64` fails to run on AMD64 host | Missing QEMU or engine lacks support for that platform | Use an ARM64 runner or enable emulation on a managed builder |
| Registry push contains only AMD64 | Buildx command had only one `--platform` or pushed wrong output | Build `--platform linux/amd64,linux/arm64 --push` then inspect index |
| Dockerfile `FROM --platform=linux/amd64` triggers lint warning | Hardcoded single platform in multi-arch stage | Drop platform from final `FROM`, pass `--platform` at CLI |
| `docker image inspect` shows AMD64 while index has ARM64 | Local image store loaded only the AMD64 variant | Use `imagetools inspect` on remote index and pull target platform |
| Container runs Java 17 yet TLS/locale/native fails | Base distro/libs/CA/tzdata differ | Pick a compatible supported distro and test runtime behavior |
| Image runs on one K8s node, fails pull on another | Manifest missing platform, node labels/OS differ | Pin multi-platform index; verify node architecture and scheduling |

### 15.1. Checking Architecture with the Right Tool

**At the registry:** `docker buildx imagetools inspect REFERENCE` to list platform manifests.

**Locally:** `docker image inspect --format '{{.Os}}/{{.Architecture}}' IMAGE` to view local image config.

**Inside the container:** `uname -m` if shell/coreutils exist, or `System.getProperty("os.arch")` for the Java runtime. These strings **do not always match** Docker metadata labels like `linux/amd64`/`linux/arm64` verbatim.

**At the builder:** `docker buildx inspect --bootstrap` to see supported builder platforms.

Never use **only `uname -m` on your laptop** to infer the platform of a CI builder or final image: Docker Desktop VMs, remote contexts, and Buildx builder nodes can differ.

## 16. Kubernetes and CPU Architecture

With a multi-platform image index, kubelet and the container runtime automatically pull the child image matching the node's platform. Kubernetes nodes commonly carry labels:

```text
kubernetes.io/os=linux
kubernetes.io/arch=amd64
kubernetes.io/arch=arm64
```

If an application image only publishes an AMD64 variant, pods scheduled onto ARM64 nodes will fail to pull or run. You can constrain scheduling in the Deployment manifest:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        kubernetes.io/os: linux
        kubernetes.io/arch: amd64
```

This is only a **Deployment pod template snippet**, not a standalone Kubernetes Deployment file. It restricts node selection to Linux AMD64; it does not make an image AMD64. Once you publish and test an index covering both AMD64 and ARM64, `nodeSelector` by arch is usually unneeded for Java-only workloads unless native dependencies, performance, or support policies require it.

**Important:**
- A mutable `image: repository:tag` plus `imagePullPolicy: Always` is not an immutable release pin. For auditability, use `image: repository@sha256:<actual-index-digest>`.
- When a tag/digest points to a multi-platform index, nodes select the matching child platform; verify your runtime/registry supports OCI indexes/manifest lists.
- Pod spec Java args/configs operate independently of CPU image variants; apps still need proper readiness/liveness probes.
- In mixed-arch clusters, test both architectures on real nodes, not solely under emulated builds.
- Rolling upgrades when the base digest changes must verify rollback paths and monitor for runtime/GC/TLS errors.

## 17. CI Verification of Architecture Coverage and Exact Base Digests

A strong pipeline tracks two datasets:
1. **Base references:** pinned builder + runtime images, registry source, and CPU variants.
2. **Release outputs:** application container index digest, child manifest list, SBOM, and scan evidence.

### 17.1. Gating on Required Platform Coverage

Assume `IMAGE_REF` is set by CI to the remote application image after push and `jq` is installed. Bash:

```bash
set -eu
: "${IMAGE_REF:?IMAGE_REF must be set by CI}"

docker buildx imagetools inspect --raw "$IMAGE_REF" |
  jq -e '
    [ .manifests[]?
      | select(.platform.os == "linux")
      | .platform.architecture
    ] as $arch
    | ($arch | index("amd64") != null)
      and ($arch | index("arm64") != null)
  '
```

On a valid multi-platform index containing both AMD64 and ARM64, `jq -e` exits `0` (printing `true`). If either architecture is missing, it exits non-zero and fails the job. This check is written for an **index/list**, not a single-platform manifest; adjust logic if policy permits single-platform images.

### 17.2. Pinning Both Inputs and Outputs

For releases:
- Capture base references **after verifying them** from Docker Hub or an approved registry.
- Configure Dockerfile/CI to use `tag@sha256:index` or an explicit digest policy.
- Build and push output images with valid version/commit tags and an immutable release record.
- Capture the **output index digest** after push and deploy by digest.
- Scan all platform manifests; CVE and native package inventories can differ between AMD64 and ARM64.
- Run smoke tests on every supported platform.
- When the publisher updates a base image, open a PR updating the digest, run regressions, and roll out cleanly; never edit production digests manually without review.

### 17.3. Useful Quality Gates

| Gate | Input | Expected Result |
| --- | --- | --- |
| Lint Dockerfile | Dockerfile + BuildKit | No hardcoded final `FROM --platform=linux/amd64` when shipping multi-arch |
| Base manifest coverage | Pinned base index | Includes `linux/amd64` and `linux/arm64` |
| Toolchain | Maven/JDK/plugin versions | Java 17-compatible executable JAR |
| Image publish | Buildx multi-platform build | Produces output index and per-platform manifests |
| Runtime smoke | Containers on AMD64/ARM64 | `GET /ready` returns `ready` |
| Security | Scan/SBOM/base provenance | Zero policy-violating issues |
| Reproducibility | Immutable base refs + pinned build inputs | Traceable artifact and digests |
| Deployment | Release image index digest | Nodes pull right variant and pass readiness |
| Update policy | CVE/base update trigger | Tested PR with rollback plan |

**Never check only that a tag exists in the registry.** A tag may contain only one platform, or point to a newly pushed index that dropped ARM64. Re-verify architecture coverage on every digest update.

## 18. Distinguishing Tag, Digest, and Trust

Digests provide **content addressing**, yet do not by themselves prove an image came from a trustworthy publisher. A malicious image still has its own valid SHA-256 digest.

To establish **trust**:
- Use approved registries and repositories.
- Verify publisher identity, image signing, provenance/attestation, and SBOMs per supply-chain policy.
- Scan OS packages, JRE, and application dependencies.
- Pin digests only after verifying provenance.
- Restrict push/tag-mutation permissions and review registry retention policies.
- Never use `latest` or digests from unverified sources to swap production bases.
- Maintain a rebase/update cadence, because old pinned digests do not receive vulnerability fixes automatically.

A digest can **uniquely name content yet become unpullable** if the registry purges manifests/layers under retention rules. Reproducible builds require retaining dependencies, mirrors, and artifact provenance — not just committing a Dockerfile.

## 19. Advanced Case: Image Index and Native Images

### 19.1. A Java JAR Differs from a Native Executable

A Spring Boot JAR compiled to pure `.class` bytecode running on a matching Temurin JRE is normally portable across AMD64 and ARM64. Moving to a **Spring Boot native image**, however:
- produces a binary compiled for one specific OS/arch/ABI;
- cannot copy an AMD64 native binary into an ARM64 runtime stage;
- requires proper cross-compilation or native builds on target-architecture runners;
- yields separate per-variant image digests combined under an index;
- requires passing BuildKit's `TARGETARCH`/`BUILDARCH` cleanly into the toolchain.

Thus Section 9's Java-only Dockerfile **is not** a copy-paste template for GraalVM native-image or complex JNI applications.

### 19.2. AMD64 vs ARM64 Performance and Feature Differences

The two architectures can differ in JIT/GC performance, vector instructions, native compression, TLS crypto, and supported JVM flags. A passing multi-arch build does not imply equal performance or behavior. For latency-sensitive services, benchmark on real target CPUs and check memory limits and JVM flags rather than relying solely on QEMU smoke tests.

### 19.3. Index Digests and Per-Platform Child Digests in Releases

Multi-arch releases often track both:
- **index digest**: one shared reference for the manifest list/image index;
- **AMD64/ARM64 child digests**: for variant-specific auditing, runtime package scans, and matching SBOMs.

If an organization pins nodes to a fixed architecture, it can deploy the **per-platform** child digest. When using a single deployment descriptor across mixed-arch clusters, **pinning the index** is cleaner and avoids accidentally deploying an AMD64 child digest onto an ARM64 node.

## 20. Frequently Asked Questions

**Q1. Does `FROM eclipse-temurin:17-jre` automatically pick ARM64 on Apple Silicon?**

If the builder target is `linux/arm64` and the registry tag includes an ARM64 variant, BuildKit selects it. Docker Desktop, remote builders, and `--platform` flags can override the target; never assume from your laptop alone when using a remote builder.

**Q2. Does the Dockerfile need `FROM --platform=$TARGETPLATFORM`?**

Usually **no**, because the target platform is already the default for an unadorned `FROM`. Docker build checks even flag writing it redundantly. Use `--platform=$BUILDPLATFORM` only on build stages intentionally, leaving the final runtime at the target default.

**Q3. Does pinning `tag@sha256` still receive automatic security patches?**

No. The tag may update, while the pinned digest stays locked to the old object. Update digests intentionally alongside scanning and testing.

**Q4. Does `docker buildx build --platform linux/amd64,linux/arm64 --load` always work?**

Do not assume so. Multi-platform `--load` support depends on the builder driver and image store; with the `docker-container` driver, the standard approach is `--push` to a registry supporting manifest lists, then inspect. Single-platform `--load` is simpler locally.

**Q5. Why do two nodes report identical `java -version` output yet have different image SHAs?**

Because image configs, native JRE binaries, OS packages, and per-architecture layers differ, or the publisher updated the tag. Identical Java feature versions do not prove identical image bytes.

**Q6. Is `docker image inspect .Id` the digest to pin in a Dockerfile?**

Not necessarily. `.Id` is usually the image config digest; `FROM repository@sha256:...` needs a manifest/index digest resolvable from the registry. Use `imagetools inspect` as shown.

**Q7. Can the same index digest be pinned for both AMD64 and ARM64?**

Yes, **provided** it is a real multi-platform index digest containing both variants. Builders and pullers select the child manifest matching the platform. Pinning an AMD64 child manifest will not achieve this.

**Q8. If I use `ubuntu:latest` in the builder and `eclipse-temurin:17-jre` at runtime, is pinning runtime enough?**

No. The builder base, JDK, Maven/Gradle, dependency resolution, and generated build metadata all shape outputs. Pinning runtime is essential, yet not full end-to-end reproducibility.

**Q9. Is an image pulled by digest guaranteed to be safe?**

No. A digest identifies content; it does not prove a trusted publisher, legitimacy, or absence of CVEs. You still need publisher verification, scanning, signatures/attestations, and policy enforcement.

**Q10. I run a mixed AMD64 and ARM64 Kubernetes cluster — where should platform be set?**

Build and push a **multi-platform** image, then deploy using the **index digest**; each node's container runtime selects the matching variant. Add `nodeSelector` only when restricting architectures or running apps with incompatible native dependencies.

## 21. Pre-Release Checklist for Spring Boot Images

- [ ] Choose a trusted base image registry/repository and a supported Java runtime version.
- [ ] Confirm the intended tag still exists, along with its security patch cadence and OS variant.
- [ ] Run `docker buildx imagetools inspect` to inspect the index/manifest digest and platform list.
- [ ] If targeting multi-arch, ensure the base image offers both `linux/amd64` and `linux/arm64`.
- [ ] Distinguish the **index digest** from child manifest digests before pinning.
- [ ] Release builds use pinned base references or record full verified sources/digests.
- [ ] Never hardcode `--platform=linux/amd64` in the final `FROM` when shipping ARM64.
- [ ] Build-stage `--platform=$BUILDPLATFORM` used only when Java bytecode output is genuinely architecture-neutral.
- [ ] Native/JNI libraries tested separately on each target architecture.
- [ ] Maven/Gradle, JDK, plugins, and dependencies pinned/controlled in CI.
- [ ] Dockerfile uses multi-stage builds to keep compilers and credentials out of runtime.
- [ ] `.dockerignore` excludes local secrets and unneeded build artifacts.
- [ ] Non-root runtime, network config, permissions, and CA certificates match app requirements.
- [ ] Buildx builder supports target platforms, using native nodes or managed QEMU.
- [ ] Multi-arch image built and pushed, with the output index inspected afterward.
- [ ] Smoke-tested `GET /ready` on AMD64 and ARM64 on real hardware or valid emulation.
- [ ] Scanned JRE, OS, and Java dependencies; retained SBOMs and provenance as needed.
- [ ] Deployed by **output index digest**, not solely a mutable tag.
- [ ] Active digest-update mechanism in place for publisher CVE patches, with canary/rollback.
- [ ] Recorded base digests, application digest, Git commit, and test evidence.

## 22. Official Documentation for Reference

- Docker – [Dockerfile reference: FROM and ARG](https://docs.docker.com/reference/dockerfile/): `FROM image:tag@digest` syntax, `--platform`, and automatic build args.
- Docker – [Multi-platform builds](https://docs.docker.com/build/building/multi-platform/): image indexes/lists, emulation, multi-node builders, and cross-compilation.
- Docker – [Buildx build --platform](https://docs.docker.com/reference/cli/docker/buildx/build/): targeting output platforms and registry publishing.
- Docker – [Buildx imagetools inspect](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/): reading image manifests/indexes, digests, and architectures.
- Docker – [Building best practices](https://docs.docker.com/build/building/best-practices/): pinning base image digests and security update workflows.
- Docker – [Build variables](https://docs.docker.com/build/building/variables/): `BUILDPLATFORM`, `TARGETPLATFORM`, and `ARG` scoping.
- Docker – [FromPlatformFlagConstDisallowed](https://docs.docker.com/reference/build-checks/from-platform-flag-const-disallowed/): avoiding hardcoded architectures in Dockerfiles.
- Docker – [Image inspect](https://docs.docker.com/reference/cli/docker/image/inspect/): local image metadata.
- Docker – [Image digests](https://docs.docker.com/dhi/explore/security-concepts/digests/): digest identities and multi-platform index concepts.
- Spring Boot 3.5 – [Packaging Executable Archives with Maven](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): executable JARs and `repackage`.
- Kubernetes – [Well-Known Labels, Annotations and Taints](https://kubernetes.io/docs/reference/labels-annotations-taints/): `kubernetes.io/os`/`kubernetes.io/arch` for nodes.

**Final takeaway:** a **tag** is a convenient mutable name; a **digest** content-addresses a specific **manifest/index**; **architecture** determines the actual runtime variant. With Spring Boot on Java 17, confirm your base image provides `linux/amd64`/`linux/arm64`, compile a pure-Java JAR on a pinned toolchain, let the final Dockerfile stage inherit Buildx's target platform, publish the multi-platform index, and **deploy by verified digest**. Old pins do not patch themselves: every reproducibility strategy must include regular updates, scanning, and testing.