# How a Native Executable Container Image Differs from a JAR Container

Spring Boot can be packaged in a container in two common ways: running an **executable JAR on the JVM** or running a **native executable compiled with GraalVM Native Image**. Both can be distributed as OCI container images and deployed with Docker, Kubernetes, or compatible platforms. However, image contents, runtime dependencies, startup behavior, build requirements, and diagnostics differ significantly.

A JAR container requires a Java Runtime Environment (JRE) to execute bytecode. A native container runs an executable built for the target architecture and operating system; it does not need a JVM to run the application, though it may still require libc, a dynamic loader, shared libraries, CA certificates, timezone data, and other runtime files.

This lesson compares the two image types, shows how to build images using Cloud Native Buildpacks and Docker multi-stage builds, explains how to choose a runtime base image, handle glibc/musl, configure users and the filesystem, manage signals and health checks, test the final image, and integrate the artifacts into CI/CD.

## 1. Distinguishing a JAR Container from a Native Container

A JAR contains Java bytecode along with its dependencies. A JAR container typically starts the Java runtime and passes the JAR to the `java -jar app.jar` command. A native executable is machine code generated ahead of time for the target OS/CPU; the container executes that file directly.

| Component | Executable JAR Container | Native Image Container |
|---|---|---|
| Entry point | `java -jar app.jar` | `./application` |
| Primary runtime | JRE | Native executable and the GraalVM Native Image runtime linked into the binary |
| JVM in the image | Yes | No JVM required |
| Application artifact | JAR/bytecode | OS/architecture-specific native binary |
| Artifact portability | A JAR is generally portable across OS/CPUs with a matching JRE | Binary must match the OS, architecture, and ABI |
| Compilation time | Bytecode is executed/JIT-compiled by the JVM at runtime | AOT before release |
| Reflection/dynamic access | The JVM generally supports this flexibly | Requires metadata or appropriate AOT mechanisms |
| System libraries | JRE and native dependencies of libraries | libc, loader, shared libraries, and JNI dependencies if any |
| Startup | Must initialize the JVM and the Spring context | Usually faster, though still dependent on the Spring context and dependencies |
| Diagnostics | JVM/HotSpot tooling depending on the runtime | Native Image features selected at build time and OS tools |

Avoid a common misconception: **a native container does not mean the binary is always statically linked**. By default, GraalVM Native Image typically produces a dynamically linked binary. It may require glibc and shared libraries in the run image. Creating a fully static executable requires choosing the appropriate configuration and toolchain, usually using musl on Linux.

## 2. What Does a Container Image Actually Contain?

An OCI image is a set of filesystem layers together with metadata describing how to run the container. A runtime image may include:

- The application executable or JAR.
- A JRE if the application runs bytecode.
- libc, the dynamic loader, and shared libraries if the binary needs them.
- CA certificates for making HTTPS calls.
- A timezone database if the application handles time zones.
- Configuration files, templates, or resources outside the classpath.
- User/group, working directory, and filesystem permissions.
- Image configuration: entrypoint, command, environment, exposed ports, and labels.

Overview diagram:

~~~mermaid
flowchart TB
    subgraph JVM["JAR Container"]
      A["OCI image"] --> B["Linux runtime base"]
      B --> C["JRE"]
      C --> D["Spring Boot executable JAR"]
      D --> E["java -jar"]
    end
    subgraph NATIVE["Native Image Container"]
      F["OCI image"] --> G["Linux runtime base"]
      G --> H["libc / loader / shared libs if needed"]
      H --> I["Spring Boot native executable"]
      I --> J["Run directly"]
    end
~~~

A native image omits the JRE, so it typically reduces the number of runtime components. Still, the final size depends on the binary, base image, shared libraries, certificates, timezone data, and resources. You cannot conclude that a native image is always smaller than a JAR image without measuring the same application under the same runtime requirements.

## 3. When to Choose a JAR Image vs. a Native Image?

A JAR container is suitable when you need to keep your existing Java pipeline, rely on libraries that do not yet support Native Image, need flexible plugin/runtime class loading, or want a single artifact that runs across multiple architectures with a JRE.

A native container is suitable when startup time, deployment density, footprint, or running in an environment without a JVM is a critical requirement, and the application along with its dependencies are already AOT-compatible.

| Criterion | JAR Container | Native Container |
|---|---|---|
| Build speed | Usually faster | Native compilation can be slow and require significant RAM/CPU |
| Startup | Includes JVM startup step | Usually faster |
| Peak throughput | Can benefit from JIT after warm-up | Can vary depending on workload and profile |
| Memory | Has JVM overhead; depends on GC and configuration | No HotSpot-style JVM heap; still has a Java heap and Native Image native memory |
| Dynamic libraries | More flexible | Requires verifying metadata/AOT and runtime features |
| Debugging | Broad JVM ecosystem | Depends on the diagnostic features compiled into the build |
| Cross-platform artifact | A JAR can generally be reused | Built separately per target |
| Best fit | General-purpose applications, dynamic plugins, hard-to-migrate dependencies | Services with verified native compatibility needing strong startup/footprint |

Do not choose native just because the image looks small. Measure startup, memory, throughput, build time, CI cost, and operational complexity on real workloads.

## 4. Two Ways to Build a Native Container Image

Spring Boot supports two main approaches:

1. **Cloud Native Buildpacks (CNB):** Maven or Gradle invokes the Spring Boot plugin to turn the application into an OCI image. Buildpacks execute the build steps and produce the run image.
2. **Docker multi-stage:** one stage with the GraalVM/native-image compiler builds the executable; the final stage contains only the binary and required runtime dependencies.

Buildpacks reduce the amount of Dockerfile boilerplate you have to maintain and can generate layers/SBOMs according to the buildpack. A multi-stage Dockerfile gives explicit control over the builder, runtime base, system packages, and final filesystem.

~~~mermaid
flowchart TD
    A["Source + Spring AOT"] --> B{"Choose packaging approach"}
    B --> C["Cloud Native Buildpacks"]
    B --> D["Docker multi-stage"]
    C --> E["Builder image + buildpacks"]
    E --> F["Native executable"]
    F --> G["Run image + app layers"]
    D --> H["GraalVM builder stage"]
    H --> I["Native executable"]
    I --> J["Runtime base image"]
    J --> K["OCI image"]
    G --> L["Test final image"]
    K --> L
~~~

Whichever approach you choose, you must test the final image. A binary that runs in the builder does not prove it will run in the run image.

## 5. Build Requirements and Version Compatibility

A native container image depends on coordinated versions of:

- Spring Boot and Spring Framework.
- JDK/GraalVM Native Image.
- GraalVM Native Build Tools.
- Cloud Native Buildpacks builder and buildpacks.
- Run image, libc, and shared libraries.
- Target OS and CPU architecture.

In the current Spring Boot 4.2.0 documentation, the Buildpacks guide requires building with at least JDK 25 because Buildpacks uses the GraalVM Native Image version corresponding to the Java version used to compile. Earlier Spring Boot lines have different baselines and configurations; do not apply the JDK 25 requirement blindly to every project. Check the guide for the exact Spring Boot release you are using.

Native Image does not support cross-compilation in a way where you can take a Linux x86-64 binary and convert it to ARM64 after building. You must build on the matching target or use a builder/runner executing on the right architecture.

## 6. Building a Native Image Using Spring Boot Buildpacks with Maven

For Maven to build a native container image, the project typically needs the Spring Boot parent and the GraalVM Native Build Tools plugin. The Spring Boot parent provides a `native` profile with the required AOT/native steps.

Plugin section in `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Build the image:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

The Spring Boot plugin invokes Cloud Native Buildpacks to create an image containing the native executable. By default, the image is named after the application's artifact/version; you can configure the image name and builder/run image in the plugin configuration.

If you do not use `spring-boot-starter-parent`, you must configure the required executions manually, including Spring AOT `process-aot` and the corresponding Native Build Tools goals. Do not simply set `BP_NATIVE_IMAGE=true` and expect a JAR without AOT assets to turn into a native executable on its own.

## 7. Building a Native Image Using Spring Boot Buildpacks with Gradle

Gradle requires applying the Spring Boot plugin and the GraalVM Native Image plugin:

~~~kotlin
plugins {
    id("org.springframework.boot") version "4.2.0"
    id("io.spring.dependency-management") version "1.1.7"
    id("org.graalvm.buildtools.native") version "0.11.2"
}
~~~

The versions shown here illustrate one specific set of compatible versions; use versions compatible with the Spring Boot/JDK pinned by your project and avoid upgrading individual plugins independently without control.

When `org.graalvm.buildtools.native` is applied, the Spring Boot Gradle plugin automatically configures the AOT tasks and `bootBuildImage` builds a native image:

~~~bash
./gradlew bootBuildImage
~~~

You can configure the image name and run image in the `bootBuildImage` task according to the Spring Boot Gradle plugin documentation. Check the build logs to confirm that the buildpack selected the native executable rather than JVM launch mode.

## 8. Using the pack CLI with an AOT-Processed JAR

In some pipelines, an earlier step builds the JAR and a subsequent step builds the native image. The JAR must contain the generated classes and JSON hints produced by Spring AOT.

With the Cloud Native Buildpacks CLI:

~~~bash
pack build orders-service:native \
  --builder paketobuildpacks/ubuntu-resolute-builder \
  --run-image paketobuildpacks/ubuntu-resolute-run-tiny \
  --path target/orders-service.jar \
  --env BP_NATIVE_IMAGE=true
~~~

`BP_NATIVE_IMAGE=true` is a build-time environment variable for the buildpack build process. It instructs the buildpack to produce a native executable from the AOT JAR. Do not confuse this variable with runtime environment variables that the application reads when the container runs.

In the Spring Boot 4.2.0 guide, the `pack` example uses JDK 25 or later and the corresponding Ubuntu Resolute builder/run images. The builder and run image must be compatible with each other. Example names/tags can change across Paketo releases; pin specific versions or digests instead of using `latest` in production pipelines.

## 9. Builder Image and Run Image Have Different Roles

Cloud Native Buildpacks separates the build environment from the runtime environment:

| Component | Builder Image | Run Image |
|---|---|---|
| Purpose | Detect/build, run buildpacks, compilers, and native tools | Provide the platform for running the application |
| GraalVM/native-image | Present in the build environment when a native build needs it | No compiler needed |
| Maven/Gradle/build tools | Can be provided in the build stage | Not needed |
| Shell and debug tools | Usually includes more tools | May be stripped out |
| Build-time packages | No need to put all of them into the final image | Contains only required runtime packages |
| Used in production | No | Yes |

A common mistake is copying the entire builder image as the runtime image. That makes the final image large and increases the package count and attack surface. The run image should contain only the components needed to run the binary.

Spring Boot 4.2.0 currently uses the Paketo Ubuntu Resolute builder and the tiny run image as the default configuration in its guide. The tiny run image has a minimal footprint and attack surface, has no shell, and includes only a reduced set of system libraries. If you need diagnostic tools or additional packages, you can choose a fuller run image or use a separate debug image.

## 10. Running a JAR Container with a Dockerfile

A simple Dockerfile for a JVM image:

~~~dockerfile
FROM eclipse-temurin:25-jre

WORKDIR /app

COPY --chown=10001:10001 target/orders-service.jar /app/app.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This image requires a JRE to execute bytecode. In a real pipeline, you can use a multi-stage build to compile/package the JAR in a Maven/Gradle stage and copy only the JAR into the JRE runtime stage.

There is no need to include the JDK, Maven, Gradle, or source code in the runtime image. Choose a JRE major version compatible with your application's bytecode and framework.

## 11. Running a Native Executable Container with Docker Multi-Stage

The example below uses a GraalVM Community Native Image container as the build stage and Debian slim as the runtime stage. The project must have the Maven Wrapper and the `native` profile configured.

~~~dockerfile
FROM ghcr.io/graalvm/native-image-community:25i4 AS native-build

WORKDIR /workspace

COPY . .

RUN chmod +x mvnw
RUN ./mvnw -Pnative -DskipTests native:compile

FROM debian:bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata zlib1g libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=native-build --chown=10001:10001 \
    /workspace/target/orders-service \
    /app/application

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/app/application"]
~~~

Adjustments:

- The GraalVM tag must match the JDK/GraalVM supported by the project; pin a specific tag or digest.
- The path `/workspace/target/orders-service` must match the executable name generated by Maven.
- The runtime packages in the example are a starting point; inspect the binary with `readelf`/`ldd` and install the exact shared libraries the application actually needs.
- If using JNI, copy the JNI libraries along with their transitive dependencies and configure the loader search path.
- If the application needs fonts, custom CAs, timezone data, templates, or external files, include them in the runtime image or mount them at runtime.
- Use `.dockerignore` to avoid copying `target`, `.git`, secret files, and unnecessary artifacts into the build context.

Not every project needs the exact `zlib1g` or `libstdc++6` packages; actual dependencies depend on the binary, toolchain, and native libraries. Verify with tools inside the target image.

## 12. Why Docker Multi-Stage Builds Are Useful

A multi-stage build separates compilation tools from the runtime:

~~~mermaid
flowchart LR
    A["Source code + wrapper"] --> B["Builder stage"]
    B --> C["Spring AOT"]
    C --> D["GraalVM native-image"]
    D --> E["Executable"]
    E --> F["Copy binary"]
    F --> G["Runtime stage"]
    G --> H["Non-root container"]
~~~

Benefits:

- Keeps compilers and build tools out of production.
- Reduces runtime size and package count.
- Makes it easier to control libc, CA certificates, timezone data, and shared libraries.
- Allows caching the build stage independently of runtime layers.
- Makes it easier to scan and review what is actually released.

However, multi-stage builds do not automatically make a binary compatible. If the builder produces a binary requiring a newer glibc than the runtime stage provides, the container will still fail to run. Builder and runtime must be chosen based on the actual ABI.

## 13. A Native Executable Is Not Necessarily Static by Default

By default, Native Image typically generates a dynamically linked executable. The binary may require a dynamic loader and libraries such as libc or zlib depending on the configuration. The fact that an image contains no JRE does not mean the image can contain only the binary file.

There are three linking modes to distinguish:

| Mode | How It Links | Typical Suitable Base Image |
|---|---|---|
| Dynamic | Dynamically linked against libc and required shared libraries | Run image with matching loader/libc/shared libraries |
| Mostly static | Statically links native libraries except libc | glibc-based images such as Debian/Ubuntu or distroless Debian |
| Fully static | Statically linked with musl on Linux | Can run in `scratch` if no external runtime files are needed |

GraalVM supports building fully static executables on Linux with the musl toolchain. Static linking against glibc is not supported according to the Native Image documentation. Example flags:

~~~text
--static
--libc=musl
~~~

These are two build options passed to the Native Image builder; for a Spring Boot executable JAR, let Spring Boot/Native Build Tools supply the AOT assets and appropriate argument files rather than assuming you can invoke `native-image -jar` directly on any fat JAR. With Native Build Tools, pass the corresponding options in build arguments if the toolchain supports them. Building static executables depends on the OS/architecture and musl toolchain; do not assume every GraalVM distribution provides the same capability.

## 14. Choosing Between glibc, musl, distroless, and scratch

Common options:

- **Debian/Ubuntu slim:** use when the binary is dynamically linked against glibc and needs selected runtime packages.
- **Distroless Debian:** suitable for mostly-static binaries or binaries verified to have all required shared libraries; typically has no shell or package manager.
- **Alpine:** uses musl; glibc binaries are not automatically compatible.
- **Scratch:** a nearly empty filesystem; only suitable when the binary and all required files are fully provided, typically with a fully static executable.

GraalVM provides the mostly-static option `--static-nolibc`: it statically links relevant libraries while keeping libc dynamic. This configuration can be a good fit for glibc-based runtimes and distroless Debian.

Fully static does not mean the application needs no filesystem files. HTTPS still needs CA certificates; timezone handling may need tzdata; the application may need configs, fonts, or external resources. If you use `scratch`, you must copy these files in and ensure their paths are correct.

## 15. OS and CPU Architecture of a Native Image

A native executable is tied to a specific target:

| Binary | Compatible Runtime Required |
|---|---|
| Linux x86-64 | Linux AMD64 and matching ABI |
| Linux AArch64 | Linux ARM64 and matching ABI |
| macOS ARM64 | macOS ARM64 |
| Windows x64 | Windows x64 |

A Linux binary will not run directly on Windows simply by copying it into a Windows container. Likewise, a binary built on macOS is not a Linux executable for a Docker Linux container.

For multi-architecture images:

1. Build the native executable separately for each target.
2. Build the final image on a runner or builder of the matching architecture.
3. Verify that the image manifest includes all required platforms.
4. Run smoke tests on each architecture.
5. Attach the tested digest/manifest to the release.

Buildx and QEMU can assist some multi-architecture workflows, but they do not turn Native Image into a cross-compiler. Native compilation under emulation can be slow or hit limits; prefer native runners or remote builders for each architecture.

## 16. Runtime Configuration and Secrets

Containers should receive environment configuration at runtime rather than baking it into the image:

~~~bash
docker run --rm \
  --publish 8080:8080 \
  --env SPRING_PROFILES_ACTIVE=production \
  --env SERVER_PORT=8080 \
  --env SPRING_DATASOURCE_URL=jdbc:postgresql://db:5432/orders \
  orders-service:native
~~~

Spring Boot environment variable names typically use uppercase with underscores. The variables above are examples; do not pass real passwords on the command line or bake them into image layers.

Principles:

- Use the deployment platform's secret manager or secret mounts.
- Never put passwords, tokens, or private keys into Dockerfile `ARG` or `ENV` at build time.
- Mount external configuration files when needed.
- Keep the same image across environments and change configuration at runtime.
- Set `SPRING_PROFILES_ACTIVE` explicitly.
- Verify that environment variables do not expose sensitive data in inspect output or logs.

Build-time environment variables like `BP_NATIVE_IMAGE` control the buildpack; runtime environment variables like `SPRING_PROFILES_ACTIVE` control the application. The two groups have different lifecycles.

## 17. Non-Root User and Filesystem Permissions

A native image should not run as root by default. Choose a fixed UID/GID or a user provided by the base image:

~~~dockerfile
COPY --from=native-build --chown=10001:10001 \
    /workspace/target/orders-service \
    /app/application

USER 10001:10001
~~~

Verify:

- The binary has execute permission.
- Config files, CA certificates, and resources have read permission.
- The application only writes to mounted volumes or explicitly permitted directories.
- `/tmp` exists and is writable if libraries create temporary files.
- Logs go to stdout/stderr instead of files without a volume.
- The process does not assume privileges to bind low ports or change system settings.

You can test a read-only root filesystem:

~~~bash
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --user 10001:10001 \
  --publish 8080:8080 \
  orders-service:native
~~~

If the application needs to write uploads or data, mount a dedicated volume and grant specific permissions. `--read-only` is a testing/hardening configuration; identify in advance which directories the application is allowed to write to.

## 18. ENTRYPOINT, Signals, and Graceful Shutdown

Use exec form for the entrypoint:

~~~dockerfile
ENTRYPOINT ["/app/application"]
~~~

Exec form allows the executable to receive signals from the container runtime more directly. Using shell form such as `ENTRYPOINT /app/application` can make the shell an intermediary process and make signal forwarding unpredictable.

When deploying:

- Verify that the application handles `SIGTERM` and runs shutdown hooks.
- Configure a grace period long enough to finish in-flight requests and close connections.
- Do not use `docker kill` as the normal way to stop containers; `docker stop` sends SIGTERM first and only sends SIGKILL after the timeout expires.
- Verify that connection pools, message consumers, and schedulers shut down properly.
- In Kubernetes, configure `terminationGracePeriodSeconds` and readiness so traffic stops arriving before the process terminates.

A native executable still has the Java/Spring application lifecycle. Removing the JVM does not remove the need for graceful shutdown.

## 19. Ports, EXPOSE, Health Checks, and Readiness

`EXPOSE 8080` in a Dockerfile only records metadata about the intended port; it does not publish the port to the host. When running locally, map the port:

~~~bash
docker run --rm -p 8080:8080 orders-service:native
~~~

If using Spring Boot Actuator, you can expose readiness/liveness endpoints and configure Kubernetes probes. Distinguish between:

- **Liveness:** is the process still running properly?
- **Readiness:** can the application accept business traffic?
- **Startup probe:** has the application finished starting up?

Do not write a `HEALTHCHECK` invoking `curl` in a tiny/distroless image if the image has no curl or shell. You can rely on orchestrator health probes that call the HTTP endpoint from outside the container. If a Docker HEALTHCHECK is required, intentionally include a suitable health client in the image or use a check mechanism that does not require a shell.

## 20. Comparing Size, Startup, and Memory Properly

When comparing a JAR image and a native image, keep conditions identical:

- Same application commit and functionality.
- Same OS/architecture and runtime environment.
- Same Spring profile configuration and dependencies.
- Same workload, request count, and measurement duration.
- Same container CPU/memory limits.
- Same logging, TLS, and health probe policies.

Record at least:

| Metric | How to Measure |
|---|---|
| Image size | OCI image size and layer total |
| Build time | Time to build the JAR/native binary and the final image |
| Startup time | From process start until readiness |
| Memory | RSS/cgroup memory and appropriate heap metrics |
| CPU | CPU during startup and steady state |
| Throughput | Requests/second under a defined workload |
| Latency | p50/p95/p99 and error rate |
| Operational cost | Build cache, registry storage, debugging, and patch cycle |

Native images usually start faster, but take longer to build. A native image is not necessarily always smaller because the binary can be large, the base image may need extra packages, or the application may require JNI/resources. Native Image may also manage certain memory regions differently from the JVM; compare RSS and cgroup usage rather than comparing heap alone.

## 21. Layer Caching and Build Reproducibility

Native compilation is resource-intensive. Leverage caching while avoiding stale cached artifacts:

- Use Docker BuildKit cache mounts for Maven/Gradle dependency caches when maintaining your own Dockerfile.
- Leverage Cloud Native Buildpacks caching.
- Pin the GraalVM builder, buildpacks, and run image.
- Pin dependency versions and plugin versions.
- Record build args, OS, architecture, and toolchain.
- Rebuild when updating the base image or native dependencies.
- Do not use the `latest` tag as the sole reference in a release.

With a Dockerfile, `.dockerignore` should exclude `target`, `build`, `.git`, IDE files, and secrets not needed in the build context. Copy only the files needed in each stage to improve cache efficiency.

A native executable is bound to the toolchain and target; for reproducibility, store build metadata and the image digest alongside the artifact.

## 22. Container Security and Supply Chain

A native image may reduce runtime components by removing the JRE, but it does not automatically make the image secure. You still need to manage OS packages, native libraries, certificates, configuration, and process permissions.

Security checklist:

- Use a small, maintained base image with an active update schedule.
- Run as non-root.
- Exclude compilers, package managers, and debug tools from the runtime image unless needed.
- Never store secrets inside the image.
- Scan the final image and OS packages.
- Store the SBOM and image digest.
- Sign the image according to your organization's release process.
- Restrict Linux capabilities and apply appropriate security profiles.
- Track CVEs for both the base image and native dependencies.
- Establish a process to rebuild images when the base image or GraalVM is updated.

Buildpacks can provide metadata/layers/SBOMs depending on the chosen builder and buildpacks. With custom Dockerfiles, the pipeline must explicitly generate an SBOM and scan the final image. Always scan the runtime image itself, not just source dependencies or the executable.

## 23. Debugging a Native Container Without a Shell

Tiny or distroless run images may lack a shell, package manager, `ps`, `curl`, or `ldd`. That does not mean the container cannot be diagnosed.

Start from outside the container:

~~~bash
docker inspect orders-service-native
docker logs orders-service-native
docker image inspect orders-service:native
docker history orders-service:native
~~~

If the container exits immediately, inspect the exit code and logs. Check the command/entrypoint, environment, ports, permissions, and mounts.

To inspect the binary:

- Use a compatible builder/debug image to run `file`, `readelf`, or `ldd`.
- Inspect the ELF interpreter and shared library dependencies.
- Use the debug image corresponding to the run image to verify runtime packages.
- Run a separate diagnostic container with the same filesystem and libraries.
- Avoid adding a shell to the production image just for debugging when a debug variant can be used.

A `No such file or directory` error even when the binary exists can be caused by the dynamic loader specified in the ELF header missing from the runtime image. `Exec format error` usually indicates an OS/architecture mismatch. `libxyz.so not found` indicates a missing shared library or loader search path issue.

## 24. Hands-On: Building Two Images from the Same Spring Boot Application

Suppose we have a service named `orders-service` using Spring MVC with a `GET /actuator/health` endpoint.

### Step 1 — Build the JAR Image

Package the JAR with Maven:

~~~bash
./mvnw package
~~~

JVM Dockerfile:

~~~dockerfile
FROM eclipse-temurin:25-jre
WORKDIR /app
COPY --chown=10001:10001 target/orders-service.jar /app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Build and run:

~~~bash
docker build -f Dockerfile.jvm -t orders-service:jvm .
docker run --rm -p 8080:8080 orders-service:jvm
~~~

### Step 2 — Build the Native Image with Buildpacks

With Maven and the native profile configured:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Or with Gradle and the GraalVM Native Image plugin applied:

~~~bash
./gradlew bootBuildImage
~~~

Record the image name generated by the plugin and inspect the image metadata.

### Step 3 — Or Build the Native Executable with Docker Multi-Stage

Use the multi-stage Dockerfile from section 11. Ensure the Maven Wrapper, native profile, GraalVM version, and runtime base image are compatible. Build for the exact target OS/architecture.

### Step 4 — Inspect the Images

~~~bash
docker image inspect orders-service:jvm
docker image inspect orders-service:native
docker history orders-service:jvm
docker history orders-service:native
~~~

Record the image size, layers, base image, architecture, and entrypoint. Do not compare only MB counts; inspect packages and runtime dependencies as well.

### Step 5 — Run Smoke Tests

~~~bash
curl --fail http://localhost:8080/actuator/health
~~~

Send real business requests and inspect responses and logs. For the native image, also test reflection, JSON serialization, resources, JNI, and any integration paths the application uses.

### Step 6 — Compare and Record Results

| Item | JAR Image | Native Image |
|---|---|---|
| Runtime command | `java -jar` | Direct executable |
| JRE in image | Yes | No |
| Build time | Record | Record native compile separately |
| Image size | Measure | Measure |
| Startup/readiness | Measure under same conditions | Measure under same conditions |
| Memory/CPU | Measure under same workload | Measure under same workload |
| Shared libraries | JRE and native deps | Native executable and native deps |
| Compatibility | Check JRE/dependencies | Check OS/arch/ABI/hints |

## 25. Common Packaging Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| Image still runs a JAR when native was expected | GraalVM Native Image plugin not applied or native build not enabled | Check Maven profile/Gradle plugin and Buildpacks logs |
| Buildpack reports missing AOT assets | JAR was not processed by Spring AOT | Run AOT processing and package generated assets into the JAR |
| Binary fails to run in the container | Wrong OS/architecture or missing loader | Build for the right target, check ELF/PE/Mach-O |
| `GLIBC_x.y not found` | Runtime glibc is older than the binary requires | Use a compatible run image or build on a matching base |
| `libxyz.so not found` | Missing shared library | Check `ldd` and install the required package |
| Container exits immediately | Wrong entrypoint, permissions, or native startup error | Check inspect, exit code, and logs |
| Cannot write files | Running as non-root on a non-writable directory | Fix ownership or mount a volume |
| Health check always fails | Endpoint not exposed or image lacks curl/shell | Use an orchestrator probe or intentionally add a health client |
| Native image HTTPS calls fail | Missing CA bundle or truststore | Provide appropriate CA certificates and test HTTPS |
| ARM64 image fails on AMD64 | Binary was built for the wrong architecture | Build separately for each target |
| `scratch` runs but HTTPS fails | Missing CA certificates | Copy a CA bundle or use an appropriate runtime base |
| Container fails to shut down gracefully | Signal does not reach the executable or shutdown timeout is too short | Use an exec-form entrypoint and test SIGTERM |

## 26. Pre-Release Checklist

- [ ] Confirm whether the image runs a JAR or a native executable.
- [ ] Pin Spring Boot, JDK/GraalVM, Native Build Tools, builder, and run image.
- [ ] Confirm AOT assets are present in the JAR if using a buildpack to convert a JAR.
- [ ] Confirm the native binary matches the target OS, architecture, and ABI.
- [ ] Check glibc/musl and shared library dependencies.
- [ ] Choose a run image containing only the required runtime packages.
- [ ] Provide CA certificates, timezone data, resources, and JNI libraries if needed.
- [ ] Run as a non-root user and grant minimal filesystem permissions.
- [ ] Use an exec-form entrypoint and test SIGTERM/graceful shutdown.
- [ ] Configure readiness/liveness probes accurately for dependencies.
- [ ] Test the final image itself, not just the builder stage.
- [ ] Run black-box smoke tests and integration tests.
- [ ] Scan the image and store the SBOM, digest, and build metadata.
- [ ] Test every released architecture.
- [ ] Measure image size, startup, memory, and throughput on the same workload.

## 27. Key Takeaways

A JAR container carries a JRE and executes bytecode with `java -jar`. A Native Image container launches a compiled executable without needing a JVM, yet still must satisfy the binary's OS, architecture, ABI, and runtime dependencies. Both are OCI images; the difference lies in their contents and how the process is launched.

Spring Boot can build native container images via Cloud Native Buildpacks or by combining a GraalVM Native Image builder with Docker multi-stage builds. Buildpacks manage the builder/run images and layers; a multi-stage Dockerfile gives direct control over the runtime filesystem. Whichever you choose, test the final image, run as non-root, configure signal handling and health probes, and provide the right shared libraries and resources.

A native executable is not fully static by default. Dynamically linked binaries need libc and shared libraries; fully static binaries on Linux typically use musl, while mostly-static binaries still require libc. Choose the base image based on actual dependencies, build separately for each architecture, and release the exact tested image digest.

### References

- Spring Boot — Developing Your First GraalVM Native Application: https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html
- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Boot — Container Images: https://docs.spring.io/spring-boot/reference/packaging/container-images/
- GraalVM — Containerize a Native Executable and Run in a Container: https://www.graalvm.org/dev/reference-manual/native-image/guides/containerise-native-executable-and-run-in-docker-container/
- GraalVM — Build Static or Mostly-Static Native Executables: https://www.graalvm.org/latest/reference-manual/native-image/guides/build-static-executables/
- GraalVM Community Container Images: https://www.graalvm.org/latest/getting-started/container-images/
- Cloud Native Buildpacks — Buildpacks: https://buildpacks.io/docs/

Builder/run image names, buildpack environment variables, and JDK requirements depend on the Spring Boot/Paketo version. Use the documentation for your exact release and pin image tags or digests in your pipeline.
