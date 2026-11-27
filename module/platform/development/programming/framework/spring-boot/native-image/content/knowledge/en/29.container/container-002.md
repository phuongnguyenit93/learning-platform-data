# Multi-Stage Dockerfile Separates the Compilation Environment from the Runtime Image

A Spring Boot application compiled into a **GraalVM Native Image** can run as a standalone Linux executable without carrying a JVM. As a result, the production container does not need to contain the JDK, Maven/Gradle, compilers, or the entire source code. A **multi-stage Dockerfile** separates the build stage (which requires the GraalVM Native Image toolchain) from the runtime stage (which only needs the executable and the OS libraries the executable links against).

In the **`SPRING_BOOT_NATIVE_IMAGE`** module, the goal is to compile Spring Boot with Spring AOT, evaluate startup and memory, test compatibility, package containers, and operate native builds. This lesson guides you through writing a multi-stage Dockerfile for Maven and Gradle, leveraging build cache, choosing a runtime image suited for a native executable, running the container as an unprivileged user, and diagnosing common issues when moving the binary from the builder to the runtime stage.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the roles of the builder stage and the runtime stage.
- Choose a GraalVM container image with the `native-image` tool to build the executable.
- Write a multi-stage Dockerfile for Spring Boot native builds with Maven or Gradle.
- Structure `COPY` instructions to leverage Docker layer caching and `.dockerignore` to shrink the build context.
- Distinguish a dynamically linked native executable from a static executable.
- Verify glibc, shared libraries, and CPU architecture compatibility between the builder and runtime images.
- Produce a runtime image free of the JDK, Maven/Gradle, and compilers.
- Run the application as a non-root user, restrict write permissions, and manage secrets safely.
- Verify the container via health endpoints and log inspection.

## 2. Why Use a Multi-Stage Build?

A Native Image build requires many tools:

- JDK/GraalVM and the `native-image` utility.
- Native compiler, linker, and C/C++ development libraries.
- Maven or Gradle along with dependency caches.
- Source code, generated AOT sources, and reachability metadata.

These components are needed only at build time. The runtime image usually needs only:

- The generated executable.
- The shared libraries the executable depends on (if dynamically linked).
- CA certificates, timezone data, or other system files if the application needs them.
- Temporary directories and runtime configuration.

A Docker multi-stage build uses multiple `FROM` instructions. Each stage has its own filesystem; the final stage defines the contents of the released image. We use `COPY --from=<stage>` to pull only the executable from the builder stage into the runtime stage. Layers containing compilers and source code in the builder are not included in the final image unless explicitly copied.

~~~mermaid
flowchart TD
    A["Source + Maven/Gradle project"] --> B["Builder stage: GraalVM + native-image"]
    B --> C["Spring AOT processing"]
    C --> D["Native Image compiler"]
    D --> E["Linux executable"]
    E --> F["COPY --from=builder"]
    F --> G["Runtime stage: OS libraries + executable"]
    G --> H["Non-root container"]
~~~

Benefits:

1. **Smaller runtime image:** excludes compilers, JDK, build tools, and source code.
2. **Reduced attack surface:** minimizes packages and tools that could be exploited in production.
3. **Separation of concerns:** the builder has the full toolchain; the runtime has only what the application needs.
4. **Faster builds with caching:** dependency layers can be reused when only source code changes.
5. **Easier runtime control:** base image, user, writable directories, and shared libraries can be controlled independently.

A multi-stage build does not automatically make the executable static. By default, Native Image typically still dynamically links against certain OS libraries; the runtime image must provide those libraries.

## 3. Choosing a Builder Image

GraalVM Community Edition provides the `native-image-community` container image on GitHub Container Registry. This image includes the GraalVM JDK and the `native-image` utility; tags can be selected by Java feature version, GraalVM release, and Oracle Linux platform.

Example builder for Java 21:

~~~dockerfile
FROM ghcr.io/graalvm/native-image-community:21-ol9 AS builder
~~~

The tag above is an example. Choose a GraalVM/JDK compatible with your project's Java target, Spring Boot, Native Build Tools, and dependencies. In production CI, pin a more specific tag or image digest so builds are reproducible and to prevent a floating tag from pointing to a newer image later.

Verify the image before using it:

~~~bash
docker run --rm ghcr.io/graalvm/native-image-community:21-ol9 java -version
docker run --rm ghcr.io/graalvm/native-image-community:21-ol9 native-image --version
~~~

If your project uses Java 17 or 25, choose the corresponding GraalVM image instead of keeping the Java 21 tag. Do not use an ordinary JDK runtime image as a builder if it lacks `native-image` and the required toolchain.

## 4. Maven Dockerfile: Building Native in the Builder Stage

The example below assumes:

- The Maven Wrapper is at the root: `mvnw`, `.mvn/`.
- The Spring Boot Maven plugin and GraalVM Native Build Tools are configured.
- The `native` profile runs Spring AOT and native compilation.
- The Maven `artifactId` is `orders-service`, so the executable is produced at `target/orders-service`.

~~~dockerfile
# syntax=docker/dockerfile:1

ARG GRAALVM_IMAGE=ghcr.io/graalvm/native-image-community:21-ol9
ARG RUNTIME_IMAGE=oraclelinux:9-slim

FROM ${GRAALVM_IMAGE} AS builder

WORKDIR /workspace

# Copy Maven Wrapper and POM first so the dependency layer can be cached.
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./

RUN chmod +x mvnw

RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp -Pnative dependency:go-offline

# Source changes frequently, so copy it after the dependency layer.
COPY src/ src/

RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp -Pnative native:compile

# Inspect the shared libraries the executable links against.
RUN ldd /workspace/target/orders-service

FROM ${RUNTIME_IMAGE} AS runtime

WORKDIR /app

COPY --from=builder --chown=10001:10001 --chmod=0555 \
    /workspace/target/orders-service /app/orders-service

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/app/orders-service"]
~~~

### Explaining the Stages

**Builder stage**

- `GRAALVM_IMAGE` contains GraalVM and the Native Image toolchain.
- `.mvn`, `mvnw`, and `pom.xml` are copied before source code so code edits do not invalidate the dependency cache.
- `dependency:go-offline` downloads dependencies and plugins needed by the `native` profile.
- `native:compile` executes the native build process configured in the Maven project, including Spring AOT processing as configured by Spring Boot.
- `ldd` prints the dynamic libraries required by the executable. Read its output to determine what the runtime image must provide.

**Runtime stage**

- Starts from Oracle Linux slim matching the builder's major version to reduce the risk of ABI/glibc mismatch.
- Copies only the executable from the builder; does not copy the JDK, Maven, source, or full `target` directory.
- `--chmod=0555` sets read/execute-only permissions on the executable.
- `--chown=10001:10001` assigns the file to an unprivileged UID/GID.
- `USER` ensures the process does not run as root.

If your Maven project's `artifactId`, executable name, or output directory differs from the example, update the paths in `ldd` and `COPY --from=builder`. For multi-module Maven builds, copy the parent POM, relevant module POMs, and sources according to the actual structure; copying only a root `pom.xml` will fail if the module build depends on other POMs.

### Building and Running the Image

From the directory containing the Dockerfile:

~~~bash
docker build --pull \
  --build-arg GRAALVM_IMAGE=ghcr.io/graalvm/native-image-community:21-ol9 \
  --build-arg RUNTIME_IMAGE=oraclelinux:9-slim \
  -t orders-service:native .
~~~

Run the container:

~~~bash
docker run --rm -p 8080:8080 orders-service:native
~~~

From the host, call an application endpoint, for example:

~~~bash
curl http://localhost:8080/actuator/health
~~~

This endpoint must be enabled and accessible according to the project's Spring Boot Security configuration. If the application does not include Actuator, call a readiness/health endpoint provided by the application.

## 5. Optimizing Docker Cache and Build Context

Docker builds images in layers. When a layer changes, subsequent layers may have to re-run. Therefore, copy less frequently changing files (wrappers, POMs, build scripts) before source code.

Example `.dockerignore`:

~~~text
.git
.idea
.vscode
.gradle
build
target
*.log
.env
.env.*
~~~

Do not exclude `.mvn/`, `gradle/`, Maven/Gradle wrappers, or required build files. If the project has generated sources, schemas, frontend assets, or custom build config files, keep them in the context and copy them in the appropriate stage.

### BuildKit Cache Mount

The Maven command uses:

~~~dockerfile
RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp -Pnative dependency:go-offline
~~~

A cache mount persists the Maven repository across builds on BuildKit-enabled builders. This cache never becomes part of the runtime image.

If using a private Maven repository, do not copy a `settings.xml` containing tokens into the image and do not pass passwords via `ARG` or `ENV`. Use a BuildKit secret mount:

~~~dockerfile
RUN --mount=type=secret,id=maven-settings,target=/root/.m2/settings.xml \
    --mount=type=cache,target=/root/.m2/repository \
    ./mvnw -B -ntp -Pnative native:compile
~~~

Build with the secret:

~~~bash
docker build \
  --secret id=maven-settings,src=./settings.xml \
  -t orders-service:native .
~~~

Use a secret mount only when access to a private repository is actually needed. Do not leave credential-bearing settings files in the build context if `.dockerignore` does not exclude them.

## 6. Gradle Native Build Tools Variant

With Gradle, the builder stage uses the same GraalVM Native Image image, but invokes the Gradle Wrapper and the `nativeCompile` task. The `org.graalvm.buildtools.native` plugin must be applied in the build; the Spring Boot Gradle plugin coordinates the AOT tasks as configured.

Example executable name configuration in `build.gradle`:

~~~groovy
graalvmNative {
    binaries {
        main {
            imageName = "orders-service"
        }
    }
}
~~~

Gradle Dockerfile:

~~~dockerfile
# syntax=docker/dockerfile:1

ARG GRAALVM_IMAGE=ghcr.io/graalvm/native-image-community:21-ol9
ARG RUNTIME_IMAGE=oraclelinux:9-slim

FROM ${GRAALVM_IMAGE} AS builder

WORKDIR /workspace

COPY gradlew settings.gradle build.gradle ./
COPY gradle/ gradle/

RUN chmod +x gradlew

# If the project uses Kotlin DSL, version catalog, gradle.properties,
# buildSrc, or included builds, copy those files in this layer.
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon help

COPY src/ src/

RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon nativeCompile

RUN ldd /workspace/build/native/nativeCompile/orders-service

FROM ${RUNTIME_IMAGE} AS runtime

WORKDIR /app

COPY --from=builder --chown=10001:10001 --chmod=0555 \
    /workspace/build/native/nativeCompile/orders-service /app/orders-service

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/app/orders-service"]
~~~

The output path above is the typical default path used by Gradle Native Build Tools. If you customized `buildDirectory`, binary name, or another native binary, check the output of `nativeCompile` and update the path accordingly. For Kotlin DSL or multi-project builds, also copy `settings.gradle.kts`, `build.gradle.kts`, `gradle.properties`, `gradle/libs.versions.toml`, `buildSrc`, and required subprojects before running Gradle.

Build:

~~~bash
docker build -t orders-service:native .
~~~

The `/root/.gradle` cache mount preserves the Gradle distribution and dependency cache across builds. Do not copy the entire `.gradle` directory from a developer machine into the runtime image.

## 7. Choosing a Runtime Image and Checking Shared Libraries

A native executable is a Linux binary tied to the CPU architecture and ABI environment on which it was built. The runtime image must provide the required shared libraries.

### 7.1. Keep the Same Base OS When Starting Out

The example Dockerfile uses a GraalVM builder based on Oracle Linux 9 and the `oraclelinux:9-slim` runtime. Matching the major version reduces the chance that the executable requires newer glibc symbols than the runtime image offers.

Do not build on a newer distro and run on an older distro without verifying glibc compatibility. An executable built with a newer glibc can reference symbols absent in an older runtime glibc.

### 7.2. Reading ldd Output

In the builder stage:

~~~bash
ldd target/orders-service
~~~

The output lists shared libraries and the paths resolved inside the builder. If any entry shows `not found`, identify the missing dependency. Even when all libraries are present in the builder, the runtime image must still contain the corresponding libraries.

Common dependencies include:

- glibc and core system libraries.
- libstdc++ or libgcc if the binary links against them.
- zlib or TLS/crypto libraries depending on the build and dependencies.
- CA certificates when the application makes HTTPS calls.
- timezone data if the application needs the OS timezone database.

Do not install a compiler or the entire build toolchain in the runtime image just to resolve a missing shared library. Identify the exact runtime package needed and add only that package to the runtime stage.

### 7.3. Using Distroless as the Runtime Stage

Once you know the exact shared libraries required by the binary, you can replace the runtime stage with a minimal image such as:

~~~dockerfile
FROM gcr.io/distroless/base-debian13:nonroot AS runtime
WORKDIR /app
COPY --from=builder --chown=nonroot:nonroot --chmod=0555 \
    /workspace/target/orders-service /app/orders-service
EXPOSE 8080
ENTRYPOINT ["/app/orders-service"]
~~~

A Distroless base image includes glibc and common system libraries, without a shell or package manager. You must verify that the binary is ABI-compatible and that every required library is present in the image. If C++ or other libraries are missing, choose an appropriate variant or a different runtime image; do not assume every Native Image runs on the `static` image.

Distroless `static` is meant for executables that do not require glibc. Use it only when the binary is genuinely built statically (for example, with an appropriate musl toolchain), dependencies are verified, and CA certificates, timezone data, `/tmp`, and other system files needed by the application have been tested.

### 7.4. Static Builds with musl

GraalVM provides Native Image builder variants bundled with a musl toolchain, such as tags with the `muslib` suffix. This can produce statically linked executables, enabling smaller runtime images. However, you must check architecture constraints, native library compatibility, and your project's build results. Some `muslib` images are published only for x86_64; check the current platform matrix before choosing one.

Do not switch to musl solely to shrink image size if the application has JNI/native dependencies that do not support musl. Build and run integration tests on the exact runtime type before releasing.

## 8. CPU Architecture and Binary Compatibility

A native executable depends on the target CPU architecture, such as `linux/amd64` or `linux/arm64`. The builder and runtime image must share the same architecture as the binary.

GraalVM Community images currently offer multi-architecture variants for x64 and AArch64, though pulling a matching base image alone is not enough to guarantee successful native cross-builds.

Safe rules:

- Build the executable on a runner/builder whose architecture matches the release architecture.
- Produce separate artifacts for amd64 and arm64.
- Never copy an arm64 binary into an amd64 runtime image or vice versa.
- If using Docker Buildx/QEMU to emulate an architecture, verify whether GraalVM Native Image supports that workflow; native compilation can be very slow or hit limits under emulation.
- Do not mechanically use `FROM --platform=$BUILDPLATFORM` for a native builder if the output binary must run on `$TARGETPLATFORM`.

Example building an amd64 image on an amd64 runner:

~~~bash
docker buildx build --platform linux/amd64 --load \
  -t orders-service:native-amd64 .
~~~

For arm64, prefer an arm64 runner:

~~~bash
docker buildx build --platform linux/arm64 --load \
  -t orders-service:native-arm64 .
~~~

When publishing a multi-arch manifest, each platform needs a binary built and tested on the matching architecture before assembling the manifest.

## 9. Container Runtime Security

A multi-stage build removes tools from the runtime, but container permissions still need to be configured.

### 9.1. Running Non-Root

The example runtime stage used:

~~~dockerfile
COPY --from=builder --chown=10001:10001 --chmod=0555 \
    /workspace/target/orders-service /app/orders-service
USER 10001:10001
~~~

The application should log to stdout/stderr. If it must write files, mount a volume or specify an explicit writable directory and grant minimal permissions to the UID running the application.

### 9.2. Read-Only Filesystem

You can run the container with a read-only root filesystem:

~~~bash
docker run --rm -p 8080:8080 \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=64m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  orders-service:native
~~~

Adjust `/tmp` size and writable mounts according to upload, temporary file, or library requirements. If the application writes to another directory, provide a specific mount rather than making the entire root filesystem writable.

### 9.3. Secrets and Runtime Configuration

Never bake database passwords, JWT signing secrets, OAuth client secrets, or private keys into a Dockerfile, build argument, or image layer. Pass them via a secret manager or the container platform's secret mechanism.

You can pass runtime properties via environment variables:

~~~bash
docker run --rm -p 8080:8080 \
  -e SPRING_DATASOURCE_URL="$SPRING_DATASOURCE_URL" \
  -e SPRING_DATASOURCE_USERNAME="$SPRING_DATASOURCE_USERNAME" \
  orders-service:native
~~~

The example above assumes environment variables are supplied from the deployment environment's secret/config store. Never record real credentials in shell history or committed compose files.

## 10. Ports, Readiness, and Health Checks

`EXPOSE 8080` in a Dockerfile only documents the port the container intends to listen on; it does not publish the port to the host. When running locally, map it:

~~~bash
docker run --rm -p 8080:8080 orders-service:native
~~~

Spring Boot applications default to listening on port 8080. You can configure the runtime port with `SERVER_PORT` or `server.port`, ensuring port mappings and probes match the actual port.

If Spring Boot Actuator is present, enable health/readiness endpoints according to deployment needs. Kubernetes can use a readiness probe to send traffic only after the application is ready; a liveness probe detects hung processes under an appropriate policy.

Do not add a `HEALTHCHECK` calling `curl` to a minimal runtime image if the image lacks a shell/curl. Use orchestrator probes or choose an explicitly managed health-check binary. With Distroless, there is no shell for direct debugging; you can use a `debug` image temporarily in diagnostic environments, never releasing the debug image as the default runtime.

## 11. Buildpacks vs. Manual Dockerfiles

Spring Boot supports Cloud Native Buildpacks with the Paketo Java Native Image buildpack. With Maven, a project with the native profile configured can run:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

With Gradle:

~~~bash
./gradlew bootBuildImage
~~~

Once the Native Image plugin is configured, Spring Boot can produce a native executable container image via Buildpacks. This is a convenient option when you want buildpacks to manage the builder/runtime images.

A manual multi-stage Dockerfile is suitable when you need:

- Control over the builder image, runtime base image, and OS baseline.
- Exact control over which files enter the runtime image.
- Enforcement of organization-specific image conventions, security policies, and build caching.
- Customization of runtime users, writable paths, and packaging layout.

Both approaches can produce containers running native executables. Choose one consistent workflow for CI/CD and record the builder image version/tag.

## 12. Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `native-image: command not found` | Builder image lacks Native Image tool or wrong tag | Use `native-image-community` and check the version |
| Maven cannot find `native` profile | POM does not configure the profile/plugin per Spring Boot guide | Check Maven plugins and the native profile |
| `target/orders-service` not found | Different executable name or output path | Check `artifactId`, `imageName`, and native compile output |
| `exec format error` | Binary built for a different CPU architecture than runtime | Rebuild on the matching target architecture |
| `error while loading shared libraries` | Runtime image is missing dynamic libraries | Read `ldd`, install the right runtime package, or pick a compatible base |
| `GLIBC_x.y not found` | Binary requires a newer glibc than runtime provides | Use a runtime matching/newer than the builder baseline or rebuild on an older baseline |
| Container exits immediately after start | Executable error, missing config, or app shutdown | Inspect `docker logs` and test running the binary in the runtime stage |
| Cannot write temporary files | Read-only root filesystem or `/tmp` not writable | Mount tmpfs/volume and grant permissions to the non-root UID |
| Container cannot reach HTTPS | Missing CA certificates or truststore | Add an appropriate CA bundle and test TLS |
| Works on host but fails in container | Host has libraries absent from the runtime image | Check `ldd` and test on the exact final image |
| Final image is still huge | Copied JDK, source, or build directory | `COPY --from=builder` only the executable and required runtime files |
| Build always re-downloads dependencies | Suboptimal layer ordering or cache mount unused | Copy build files before source and use BuildKit cache mounts |

## 13. Pre-Release Checklist

- [ ] Select a GraalVM builder image matching the Java feature version and Native Image tool.
- [ ] Pin builder/runtime image tags or digests per CI policy.
- [ ] Run Spring AOT and native compilation cleanly in the builder stage.
- [ ] Verify the exact executable name and path.
- [ ] Check `ldd` output or an equivalent tool for shared libraries.
- [ ] Choose a runtime image with compatible ABI and libraries.
- [ ] Copy only the executable and required runtime assets into the final stage.
- [ ] Use `.dockerignore` to exclude build outputs, IDE files, and secrets.
- [ ] Use BuildKit cache mounts for Maven/Gradle dependency repositories.
- [ ] Store no secrets in `ARG`, `ENV`, the Dockerfile, or image layers.
- [ ] Run the container as a non-root user.
- [ ] Identify directories needing write access and configure minimal volumes/tmpfs.
- [ ] Verify ports, readiness, health endpoints, and logs.
- [ ] Build and test separately for each released CPU architecture.
- [ ] Scan the image, verify the SBOM, and record the released image digest.

## 14. Self-Check Exercises

**Q1.** Why does the builder stage require GraalVM Native Image while the runtime stage does not need a JDK?

**Hint:** The builder compiles code into an executable; a native executable does not need a JVM to launch.

**Q2.** Why can't `scratch` or Distroless `static` be used by default for every native executable?

**Hint:** By default, binaries can dynamically link to glibc, zlib, or other system libraries; the runtime must supply those dependencies.

**Q3.** Why should POM/build scripts be copied before source code?

**Hint:** The dependency layer changes less often than source code, allowing Docker to reuse cached layers when code changes.

**Q4.** What does `COPY --from=builder` do?

**Hint:** Copies artifacts from the builder stage into the runtime stage without including the entire builder filesystem in the final image.

**Q5.** Does `EXPOSE 8080` automatically publish the port to the host?

**Hint:** No. You need `-p hostPort:containerPort` when running Docker or port/service configuration in an orchestrator.

**Q6.** Why might a binary run on the build machine yet fail with `GLIBC_x.y not found` inside a container?

**Hint:** The runtime image has an older glibc than the symbol version required by the binary.

**Q7.** Can a single native binary support both amd64 and arm64?

**Hint:** No. A native executable is compiled for a specific architecture; separate artifacts must be built and tested for each platform.

## 15. References

- [Docker — Multi-stage builds](https://docs.docker.com/build/building/multi-stage/): multiple build stages and copying artifacts into the final stage.
- [Docker — Build cache optimization](https://docs.docker.com/build/cache/optimize/): layer ordering, build context, and cache mounts.
- [Docker — Build best practices](https://docs.docker.com/build/building/best-practices/): `.dockerignore`, pinning images, and multi-stage builds.
- [GraalVM — Community Edition Container Images](https://www.graalvm.org/latest/getting-started/container-images/): `native-image-community` images, tags, Java versions, Oracle Linux, and architectures.
- [Spring Boot — Developing Your First GraalVM Native Application](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html): native executables and Buildpacks/Maven/Gradle choices.
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): differences between JVM and Native Image, closed-world assumption, and AOT.
- [Google Distroless — Base images](https://github.com/GoogleContainerTools/distroless/blob/main/base/README.md): runtime base contents, glibc, and distroless variants.

**Key Takeaway:** A multi-stage Dockerfile puts the GraalVM compiler and build tools in the builder stage, then transfers only the native executable and its runtime dependencies to the final stage. Verify shared libraries, glibc baseline, and CPU architecture before choosing a runtime image; run as non-root, manage secrets outside the image, and verify the final container itself with health/readiness tests.
