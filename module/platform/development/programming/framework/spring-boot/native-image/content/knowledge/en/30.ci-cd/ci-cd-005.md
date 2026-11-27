# Build Strategies by Target OS and Architecture

A native executable is produced for a specific operating system and CPU architecture. A Linux/AMD64 binary cannot run directly as a Windows/x64 or macOS/ARM64 binary. Even among machines running Linux, differences in architecture, libc, and toolchains can make an artifact incompatible.

GraalVM Native Image does not support general-purpose cross-compilation. Therefore, CI/CD must structure builds per target platform. With Spring Boot, you can produce an executable JAR already containing Spring AOT assets as an OS-neutral intermediate artifact, then convert that JAR into a native executable or container image on a worker matching each target.

This lesson designs pipelines for Linux, Windows, and macOS on AMD64/AArch64; distinguishes standalone binaries from container images; configures Maven, Gradle, and Buildpacks; organizes CI matrices; and covers testing, caching, artifact storage, and safe releasing.

## 1. Define the Artifact's Target Platform

When releasing an application, specify at least three layers:

1. **Operating system:** Linux, Windows, or macOS.
2. **CPU architecture:** AMD64/x86-64 or AArch64/ARM64.
3. **Runtime ABI and environment:** libc, system libraries, native toolchain, and JNI libraries required by the executable.

| Target | Common executable format | Required build environment |
| --- | --- | --- |
| Linux/AMD64 | ELF x86-64 | GraalVM Native Image, GCC/Clang, and Linux headers/libraries |
| Linux/AArch64 | ELF ARM64 | GraalVM with AArch64 support and Linux ARM64 toolchain |
| Windows/AMD64 | PE executable | GraalVM with Windows x64 support, MSVC, and Windows SDK |
| macOS/AArch64 | Mach-O ARM64 | GraalVM with macOS ARM64 support and Xcode Command Line Tools |

Targets do not form a full Cartesian matrix. A GraalVM distribution might support Linux/ARM64 without supporting Windows/ARM64; a newer release might drop a platform an older release supported. Only add an OS/architecture combination after confirming that your chosen distribution and version provide Native Image for that target.

### Binaries and Container Images Are Two Different Artifact Types

- A standalone native executable uses the target OS format: ELF, PE, or Mach-O.
- A container image runs on a compatible container runtime. With Spring Boot Buildpacks, the common case is a Linux container.
- A multi-architecture OCI manifest can point to multiple images such as `linux/amd64` and `linux/arm64`. This manifest does not turn an AMD64 executable into an ARM64 executable.
- Windows and macOS binaries are normally released as separate artifacts, outside a Linux multi-platform manifest.

Never share the same filename or container tag across binaries for different targets unless the pipeline preserves clear per-artifact metadata.

## 2. Why Workers Must Match the Target OS and Architecture

Native Image performs static analysis, compiles code, and links a native executable. This process relies on the GraalVM distribution and the build environment's toolchain. The `--target` option can select certain OS/architecture targets supported by the toolchain, but it does not turn `native-image` into a general-purpose cross-compiler.

Spring Boot allows building an executable JAR containing AOT-generated assets, then converting that JAR into a native image on the appropriate CI/CD platform. A JAR is a Java artifact that can move between workers; the native executable is produced separately on a worker matching the target OS/architecture.

### Two Ways to Organize the Pipeline

**Build from source on each worker**

Each matrix job checks out source, runs Spring AOT, and runs Native Image on the runner for that target. This is straightforward to set up and diagnose, and typically works well when the number of targets is small.

**Build the AOT JAR once, then convert on each worker**

The first job compiles, tests, and packages an executable JAR with generated classes, resources, and reachability metadata. Downstream jobs download that JAR and run GraalVM Native Image or Buildpacks on platform-specific workers.

The second approach avoids repeating some Java/AOT steps. Make sure the JAR genuinely contains the AOT assets and that all workers use compatible JDK/GraalVM versions. Only pass the JAR between jobs; never pass a native executable from one platform to another worker and treat it as compatible.

## 3. Verify the Supported Platform Matrix

Do not build a matrix as the Cartesian product of every OS and architecture. Before declaring runners, check:

- GraalVM distribution: Oracle GraalVM, GraalVM Community, Mandrel, or Liberica Native Image Kit.
- Specific GraalVM/JDK version and patch level.
- OS version, CPU architecture, and distribution support status.
- Whether Native Image is shipped for that combination.
- Whether the runner's build toolchain includes the compiler, linker, headers, and SDK.
- Whether the runtime image or target host environment is compatible with the binary.

For example, an Oracle GraalVM 25 matrix might cover Linux x64, Linux AArch64, Windows x64, and macOS AArch64 when the corresponding release supports those platforms. macOS x64 has been dropped from newer GraalVM releases; Windows ARM64 likewise should not be added just because a CI provider offers ARM64 runners. Check the distribution's support matrix before enabling a job.

### Example Runners on GitHub Actions

The labels below are examples of runners currently available in GitHub Actions; availability, quotas, and image versions depend on repository and runner tier:

| Target | Example runner | Notes |
| --- | --- | --- |
| Linux/AMD64 | `ubuntu-24.04` | Suitable for building Linux x64 executables |
| Linux/ARM64 | `ubuntu-24.04-arm` | Uses real ARM64 hardware, not x64 CPU emulation |
| Windows/AMD64 | `windows-2025` | Verify Visual Studio Build Tools and Windows SDK |
| macOS/ARM64 | `macos-15` | Apple Silicon runner; verify GraalVM distribution supports macOS ARM64 |

If your CI provider lacks a runner for a needed target, use a self-hosted runner or suitable build service. Never substitute target testing by merely changing `--target` on a runner of a different architecture.

## 4. Split the Pipeline into Stages

A maintainable pipeline typically divides into these stages:

~~~mermaid
flowchart TD
    A["Commit / Pull request"] --> B["JVM compile and unit tests"]
    B --> C["Spring AOT and executable JAR"]
    C --> D["Native build matrix"]
    D --> E["Linux AMD64"]
    D --> F["Linux ARM64"]
    D --> G["Windows x64"]
    D --> H["macOS ARM64"]
    E --> I["Native smoke / integration tests"]
    F --> I
    G --> I
    H --> I
    I --> J["Checksum, SBOM, and provenance"]
    J --> K["Publish platform artifacts"]
    I --> L["Build Linux container images"]
    L --> M["AMD64 image + ARM64 image"]
    M --> N["OCI multi-platform manifest"]
    K --> O["Release"]
    N --> O
~~~

**JVM verification** runs faster and catches compile, unit test, dependency, formatting, or static analysis errors before spending native build resources.

**AOT preparation** produces an executable JAR with generated code and metadata. For Spring Boot, Spring AOT is mandatory to run an `ApplicationContext` inside a native image.

**Native matrix** builds independent artifacts on each worker. One failing job should not cancel the other targets, because per-platform logs help isolate platform-specific differences.

**Validation and publishing** happen only after artifacts have been verified. If any target failed to build or failed native tests, do not create a release assuming all platforms are ready.

## 5. Prepare the Toolchain for Each OS

Native Image requires the compiler and development libraries of the build platform.

### Linux

On Ubuntu, the environment typically requires `build-essential` and zlib development headers:

~~~bash
sudo apt-get update
sudo apt-get install -y build-essential zlib1g-dev
~~~

Some distributions also need `glibc-devel`, `libstdc++-static`, or equivalent packages. Follow the installation guide for your exact GraalVM release and Linux distribution.

Distinguish clearly between glibc and musl. A binary built against one libc does not automatically run on a runtime image providing only the other libc. Buildpacks builder and run images must also share a matching stack/ABI.

### Windows

Native Image on Windows requires the Microsoft Visual C++ compiler version required by GraalVM and the Windows SDK. GitHub-hosted Windows runners usually include Visual Studio Build Tools, but verify the toolchain in the image being used:

~~~powershell
java --version
native-image --version
cl
~~~

If `cl` is not found, open the appropriate Developer Command Prompt or initialize the MSVC environment per runner/GraalVM guidance. Do not assume installing the JDK alone satisfies native build prerequisites.

### macOS

Install Xcode Command Line Tools:

~~~bash
xcode-select --install
~~~

Then verify:

~~~bash
java --version
native-image --version
clang --version
xcode-select -p
~~~

The GraalVM distribution and version must support the runner's macOS architecture. Some distributions no longer ship Native Image for Intel macOS; check the download/support matrix before adding that target.

## 6. Configuring Maven for Native Builds

With Maven, the Spring Boot Maven Plugin handles Spring AOT and GraalVM Native Build Tools executes Native Image compilation. Projects using `spring-boot-starter-parent` can use the `native` profile to configure the required steps.

Example declaration of both plugins in the application module:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>

        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

If plugin versions are not managed by a parent POM, declare compatible versions in your project's dependency/plugin management. Keep Spring Boot, GraalVM, and Native Build Tools at versions tested together.

Build native on the corresponding runner:

~~~bash
./mvnw -B -Pnative package
~~~

On Windows:

~~~powershell
.\mvnw.cmd -B -Pnative package
~~~

With the Spring Boot Maven Plugin, the `native` profile can activate `process-aot` and configure Native Build Tools or Buildpacks appropriately. If organizing a separate AOT JAR job, configure the AOT/package step independently from the execution that builds the native executable; avoid accidentally running Native Image inside an intermediate job that only needs a JAR.

### Use Explicit Artifact Names

You can configure `imageName` in Native Build Tools for a stable executable name, such as `orders-api`. The output still depends on OS:

- Linux/macOS: `target/orders-api`.
- Windows: `target/orders-api.exe`.

In CI, name uploaded artifacts with both OS and architecture, such as `orders-api-linux-amd64` or `orders-api-windows-amd64`. Never upload two identically named files into the same artifact without preserving target metadata.

## 7. Configuring Gradle for Native Builds

With Gradle, Native Build Tools provides the `nativeCompile` task. The Spring Boot Gradle Plugin runs AOT processing when the native configuration is enabled.

Example plugin declaration:

~~~kotlin
plugins {
    id("org.springframework.boot")
    id("org.graalvm.buildtools.native")
}
~~~

Build the native executable:

~~~bash
./gradlew nativeCompile
~~~

On Windows:

~~~powershell
.\gradlew.bat nativeCompile
~~~

The default output typically resides under `build/native/nativeCompile/`, with the binary name derived from the application/project configuration. If the project needs a fixed name, configure the binary under `graalvmNative` and apply the same naming convention across all matrix jobs.

Groovy DSL example:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            imageName = "orders-api"
        }
    }
}
~~~

Verify the DSL against your Native Build Tools version. For projects with multiple binaries—such as the application and native tests—configure targets and artifact names separately per binary.

## 8. Using an AOT JAR as an Intermediate Artifact

A Spring Boot executable JAR can be converted into a native image if it contains the AOT-generated assets, such as generated classes and JSON hints. This lets you keep an existing JVM pipeline and then build native executables in per-platform CI jobs.

The intermediate JAR must:

- Be built after Spring AOT processes the application context.
- Package the generated classes and resources.
- Package the required reachability metadata.
- Be built with a JDK version compatible with the GraalVM builder used in the native step.
- Have a clear version and checksum so matrix jobs download the exact same input.

An AOT JAR is not a native executable. It remains a Java archive and can serve as input to different workers. The native compiler running on each worker is what produces the OS/architecture-specific binary.

### When Should Each Matrix Job Build from Source?

If the target count is small and build times are acceptable, building from source on each worker is usually simpler. It avoids the complexity of extracting JARs, transferring AOT assets, and coordinating builder versions.

If you have many targets or AOT processing is expensive, split out a dedicated AOT JAR job. Weigh total pipeline time against operational complexity before choosing.

## 9. Building Linux Container Images with Buildpacks

Spring Boot integrates Cloud Native Buildpacks via Maven `spring-boot:build-image` and Gradle `bootBuildImage`. You can also use `pack` to build a container image from an AOT-processed executable JAR.

Example:

~~~bash
pack build orders-api:1.0.0 \
  --builder paketobuildpacks/ubuntu-resolute-builder \
  --run-image paketobuildpacks/ubuntu-resolute-run-tiny \
  --path target/orders-api.jar \
  --env BP_NATIVE_IMAGE=true
~~~

`BP_NATIVE_IMAGE=true` instructs the Paketo Native Image buildpack to build a native executable. The builder provides GraalVM Native Image and the required toolchain; the run image contains the minimal environment to run the application.

With Spring Boot 4.2, current documentation requires building the application with at least JDK 25 for the Buildpacks native workflow, because Buildpacks selects a GraalVM Native Image version matching the Java version used to compile. Check the requirements of your exact Spring Boot and buildpack versions if your project is on another release.

### Build Containers per Architecture

Build the Linux/AMD64 image on a Linux/AMD64 worker and the Linux/ARM64 image on a Linux/ARM64 worker. Both the builder image and run image must also support that architecture. Do not assume a builder tag has identical platform variants for every architecture; inspect the manifests of the builder/run images before using them.

Buildpacks produces Linux container images. If you need standalone Windows or macOS executables, use Native Build Tools on the corresponding Windows/macOS workers. Never try to use Linux Buildpacks to generate Mach-O or Windows PE executables.

## 10. CI Matrix Example with GitHub Actions

The following example illustrates building four targets supported by the chosen GraalVM distribution and runners: Linux/AMD64, Linux/ARM64, Windows/AMD64, and macOS/ARM64. Adjust runner labels, GraalVM version, plugin versions, and targets for your actual repository.

~~~yaml
name: native-artifacts

on:
  push:
    branches: [main]
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v6

      - uses: graalvm/setup-graalvm@v1
        with:
          version: '25.0'
          distribution: 'graalvm'
          cache: 'maven'
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: JVM verification
        run: ./mvnw -B verify

  native:
    needs: verify
    strategy:
      fail-fast: false
      max-parallel: 2
      matrix:
        include:
          - os: linux
            arch: amd64
            runner: ubuntu-24.04
            binary: target/orders-api

          - os: linux
            arch: arm64
            runner: ubuntu-24.04-arm
            binary: target/orders-api

          - os: windows
            arch: amd64
            runner: windows-2025
            binary: target/orders-api.exe

          - os: macos
            arch: arm64
            runner: macos-15
            binary: target/orders-api

    runs-on: ${{ matrix.runner }}

    steps:
      - uses: actions/checkout@v6

      - uses: graalvm/setup-graalvm@v1
        with:
          version: '25.0'
          distribution: 'graalvm'
          cache: 'maven'
          github-token: ${{ secrets.GITHUB_TOKEN }}
          native-image-job-reports: 'true'

      - name: Build native executable on Unix
        if: runner.os != 'Windows'
        run: ./mvnw -B -Pnative package -DskipTests

      - name: Build native executable on Windows
        if: runner.os == 'Windows'
        shell: pwsh
        run: .\mvnw.cmd -B -Pnative package -DskipTests

      - name: Upload platform artifact
        uses: actions/upload-artifact@v4
        with:
          name: orders-api-${{ matrix.os }}-${{ matrix.arch }}
          path: ${{ matrix.binary }}
          if-no-files-found: error
~~~

This example assumes the POM declares the Spring Boot Maven Plugin, Native Build Tools, and the `native` profile, with `imageName` configured as `orders-api`. The `verify` job runs JVM verification once, while the matrix jobs run Native Image on each runner. `fail-fast: false` lets other targets finish so you collect complete results; `max-parallel` caps concurrent heavy builds.

`version: '25.0'` illustrates a GraalVM LTS line. In a release pipeline, pin a tested patch version and update deliberately. Action major tags in the example should also be pinned to commit SHAs per your organization's supply-chain security policy.

If using Gradle, replace the build step with the `nativeCompile` task and adjust `matrix.binary` to match your project's output path.

## 11. Building Multi-Platform OCI Images

For Linux container deployments, build and push each architecture's image under its own tag:

~~~text
registry.example.com/orders-api:1.0.0-linux-amd64
registry.example.com/orders-api:1.0.0-linux-arm64
~~~

Once both images are pushed and tested, create the shared manifest:

~~~bash
docker buildx imagetools create \
  --tag registry.example.com/orders-api:1.0.0 \
  registry.example.com/orders-api:1.0.0-linux-amd64 \
  registry.example.com/orders-api:1.0.0-linux-arm64
~~~

Inspect the manifest:

~~~bash
docker buildx imagetools inspect registry.example.com/orders-api:1.0.0
~~~

When a client pulls the shared tag, the container runtime selects the image matching the node's OS/architecture. Each image still holds a native executable built for that exact platform.

Do not add Windows/macOS binaries into a Linux manifest. Windows container images, if needed by the project, require a separate Windows pipeline and Windows base image. Keep in mind that OCI platform metadata usually expresses only OS/architecture; CPU instruction-set baselines must still be governed by your build and deployment policy.

## 12. Testing on Each Target

A successful build only proves the compiler produced an artifact. It does not prove the binary runs on target machines or that every application flow works correctly.

| Testing layer | Where it runs | Goal |
| --- | --- | --- |
| JVM unit and integration | A standard runner | Verify business logic and Spring context |
| Spring AOT processing | AOT job or native matrix | Verify `BeanFactory` and generated code |
| Native build | Each OS/architecture runner | Verify the target compiler and linker |
| Native smoke test | Same platform as the binary | Verify executable startup and core request flows |
| Native integration test | Target-matching runner or test environment | Verify reflection, resources, JNI, serialization, and networking |
| Deployment test | Real host/cluster | Verify ABI, libc, container runtime, and production config |

Gradle Native Build Tools provides the `nativeTest` task. With Maven, Spring Boot supports the `nativeTest` profile combining AOT test processing and Native Build Tools test goals. Use them for branches with native risk while keeping most unit tests on the JVM for fast feedback.

### Testing When Runners Lack Matching Hardware

If you cannot run the binary directly on the build runner, use a test host or cluster with the matching OS/architecture. Emulation can help with basic smoke tests, but it does not fully replace native hardware testing—especially when JNI, CPU-specific code, or performance SLAs are involved.

Do not test only `--version` or whether the process starts. Send real requests, check health endpoints, read resources, access databases/message brokers, and exercise flows that use reflection or serialization.

## 13. Caching, Build Duration, and Reproducibility

Native Image builds consume CPU, RAM, and time. A pipeline can cut build times while preserving reproducibility if it caches the right layers.

### Safe to Cache

- Maven local repository or Gradle dependency cache.
- Wrapper and plugin downloads.
- Dependency metadata per build tool.
- Caches independent of native outputs that are safe to reuse.

### Do Not Share Arbitrarily

- Native executables built for a different OS/architecture.
- Native build intermediates across different GraalVM versions.
- Compiler caches or object files across Windows, macOS, and Linux runners.
- Caches produced with an incompatible toolchain, builder, or libc.

Cache keys should include at least OS, architecture, JDK/GraalVM version, build tool, and lock/dependency file hashes. Caches holding only the dependency repository can be reused more broadly; caches holding native outputs must be partitioned by platform and toolchain.

### Control Concurrency

Each Native Image build can require substantial RAM. Running eight targets simultaneously on small runners can slow down builds or trigger OOM kills. Use `max-parallel`, sufficiently sized runners, and distribute jobs according to CI capacity. Record build durations per target to spot which platform is the bottleneck.

### Pin the Toolchain

For reproducible builds, record explicitly:

- GraalVM distribution, JDK version, and patch level.
- Spring Boot version.
- Native Build Tools Maven/Gradle plugin version.
- Maven/Gradle wrapper version.
- OS runner image and architecture.
- C compiler, linker, SDK, and libc/runtime stack.
- Buildpack builder/run image tags or digests.
- Native Image build arguments and CPU baseline.

Do not use `latest` for builder images or toolchains in a release pipeline without a controlled update and verification step.

## 14. Managing Artifacts, Checksums, and Provenance

Name artifacts so recipients immediately recognize the target:

| Artifact name | Meaning |
| --- | --- |
| `orders-api-linux-amd64` | ELF binary for Linux x64 |
| `orders-api-linux-arm64` | ELF binary for Linux ARM64 |
| `orders-api-windows-amd64.exe` | PE executable for Windows x64 |
| `orders-api-macos-arm64` | Mach-O executable for Apple Silicon macOS |
| `orders-api-1.0.0-linux-amd64` | Container image for Linux/AMD64 |

Each artifact should ship with metadata or a release manifest recording the source commit, application version, target platform, GraalVM version, and build timestamp.

Generate checksums after building:

~~~bash
sha256sum target/orders-api > target/orders-api.sha256
~~~

In PowerShell:

~~~powershell
Get-FileHash .\target\orders-api.exe -Algorithm SHA256
~~~

In release pipelines, consider:

- Generating an SBOM per binary/container image.
- Provenance linking source commit, workflow run, and toolchain.
- Artifact or container image signing.
- Vulnerability scanning of dependencies and base images.
- Archiving build logs and native-image build reports alongside release metadata.

If distributing macOS binaries to end users, handle code signing and notarization per Apple ecosystem requirements. On Windows, consider Authenticode signing. Only publish after all mandatory targets pass validation.

## 15. Diagnosing Common CI Matrix Failures

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `native-image` not found | `JAVA_HOME` points to a regular JDK or action did not install Native Image | Check GraalVM distribution, `PATH`, and `native-image --version` |
| Linux job fails missing `gcc`/headers | Runner or container lacks native toolchain | Install packages per GraalVM and OS instructions |
| Windows job fails unable to find `cl.exe` | MSVC/Windows SDK not initialized in shell | Use a runner image with Build Tools or initialize the developer environment |
| macOS job fails at linker | Xcode Command Line Tools missing or incompatible | Check `xcode-select`, `clang`, and SDK |
| ARM64 job has no GraalVM download | Distribution/version does not publish that target or runner architecture is wrong | Check support matrix; pick a compatible distribution/runner |
| Binary builds, but fails at runtime with exec format error | Artifact downloaded for wrong OS/architecture | Name artifacts by target and verify file format |
| Linux image fails with libc errors on another distro | Incompatible builder/run image or native linkage | Pick a compatible stack/runtime and test on the production base image |
| AOT JAR fails to build a native image | JAR lacks generated classes or reachability metadata | Inspect Spring AOT processing and executable JAR contents |
| Buildpack does not run native mode | `BP_NATIVE_IMAGE` not enabled or builder lacks support | Check buildpack config and builder/run images |
| Only one target fails | Platform difference, JNI dependency, or support matrix mismatch | Inspect that specific job's logs and native libraries |
| Matrix job OOMs or times out | Native build too heavy or too many concurrent jobs | Increase RAM, limit parallelism, or optimize the build |
| OCI manifest misses ARM64 | ARM64 image not pushed yet or manifest created too early | Wait for both images, inspect manifest, then apply shared tag |

Do not fix platform issues by randomly tweaking `--target`. First verify the actual runner, OS/architecture, GraalVM distribution, toolchain, and artifact target.

## 16. Hands-On Exercise: Build a Pipeline for Linux AMD64, Linux ARM64, Windows, and macOS

Suppose the `orders-api` service needs to release native executables for Linux x64, Linux ARM64, Windows x64, and macOS ARM64, while also shipping a multi-arch Linux container image.

Steps:

1. Select a GraalVM distribution and version supporting all four targets.
2. Verify that each corresponding runner has the right architecture and native toolchain.
3. Configure Spring Boot AOT and Native Build Tools in Maven or Gradle.
4. Create a JVM verification job that runs unit/integration tests once.
5. Create a native matrix explicitly declaring the four OS/architecture combinations.
6. Use the same GraalVM/JDK version and build arguments for targets expected to stay aligned.
7. Name artifacts by OS/architecture and upload binaries and checksums separately.
8. Add native smoke/integration tests on matching runners or target hosts.
9. Build the two Linux container images via Buildpacks on AMD64 and ARM64 runners.
10. Test each image on its matching architecture, then create the multi-platform OCI manifest.
11. Record provenance, SBOM, GraalVM version, source commit, and builder image digest.
12. Deliberately drop a runner or change a builder version on a test branch; confirm the pipeline catches the missing artifact or toolchain mismatch before publishing.

### Self-Check Questions

1. Why can't a single native executable be shared across Linux, Windows, and macOS?
2. Does `--target` make Native Image a general-purpose cross-compiler?
3. Why can a Spring Boot executable JAR containing AOT assets serve as an intermediate artifact for multiple platforms?
4. Why must native builds run on workers matching the target OS/architecture?
5. Why shouldn't a matrix be built as the Cartesian product of every OS and architecture?
6. Which compiler and SDK does Windows Native Image require?
7. Why might Intel macOS no longer be supported by a newer GraalVM distribution?
8. What artifact type do Buildpacks create, and why don't they replace Windows/macOS native executables?
9. What does a multi-platform OCI manifest solve, and what does it not solve?
10. What data should be included in the checksum, SBOM, and provenance of a native release?

**Success criteria:** design a CI matrix covering supported OS/architecture combinations; distinguish AOT JARs from native executables and container images; build on matching runners; configure Maven/Gradle/Buildpacks; run native tests per target; produce an OCI manifest for multi-arch Linux; and publish artifacts with clear naming, checksums, and provenance.

## Official Documentation

- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Boot — Maven Ahead-of-Time Processing: https://docs.spring.io/spring-boot/maven-plugin/aot.html
- Spring Boot — Gradle Ahead-of-Time Processing: https://docs.spring.io/spring-boot/gradle-plugin/aot.html
- GraalVM — Native Image: https://www.graalvm.org/latest/reference-manual/native-image/
- GraalVM — Supported Platforms: https://www.graalvm.org/latest/support/
- GraalVM Native Build Tools — Maven Plugin: https://graalvm.github.io/native-build-tools/latest/maven-plugin.html
- GraalVM Native Build Tools — Gradle Plugin: https://graalvm.github.io/native-build-tools/latest/gradle-plugin
- GraalVM — GitHub Actions setup: https://github.com/graalvm/setup-graalvm
- GitHub Actions — Hosted Runners: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- Paketo — Java Native Image Buildpack: https://paketo.io/docs/reference/java-native-image-reference/
