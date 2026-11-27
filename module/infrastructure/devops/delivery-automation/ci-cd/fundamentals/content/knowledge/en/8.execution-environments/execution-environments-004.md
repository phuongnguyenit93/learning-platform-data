# Pinning OS, Toolchains, and Tool Versions

A CI/CD pipeline can sit unchanged in Git and still produce different outcomes across two runs. The cause often lies in the execution environment: the runner was updated, the OS image changed, the JDK or compiler version shifted, the build tool auto-downloaded a newer release, or a CLI was installed from an unpinned source.

**Pinning OS, toolchains, and tool versions** means explicitly specifying the environment components used to build, test, package, and deploy. The goal is for teams to know where the pipeline runs, which tools it uses, why it produced a given output, and how to reproduce the environment when investigating issues.

This principle belongs to the execution foundation of CI/CD. It supports consistent builds, reliable testing, traceable artifact management, and safe releases. Pinning versions does not mean freezing the environment indefinitely; OS and tool patches still need to be applied through a controlled process.

## 1. What Layers Make Up an Execution Environment?

A CI job is typically influenced by multiple environment layers:

| Layer | Example components | Impact on pipeline |
|---|---|---|
| Runner/host | VM, physical machine, kernel, CPU, filesystem | Determines compute resources, architecture, and certain system behaviors |
| Operating system | Ubuntu, Debian, Windows Server, macOS | Provides system libraries, shell, package manager, and base runtime |
| Container/executor image | Image containing JDK, Node.js, scanner, or CLI | Defines the root filesystem and many tools available in the job |
| Toolchain | JDK, compiler, linker, SDK, runtime | Determines how source code is compiled or executed |
| Build/test tools | Gradle, Maven, npm, pytest, linters, test runners | Determines how dependencies are resolved, built, and verified |
| Deployment tools | Docker CLI, kubectl, Helm, Terraform, cloud CLI | Affects how the pipeline interacts with target infrastructure |
| System configuration | Locale, timezone, environment variables, certificates, package repositories | Can alter outputs, test results, or network connections |

Not every job uses every layer. A Java build job may require a JDK, Gradle, and a container image; a Kubernetes deploy job may require `kubectl`, Helm, and short-lived credentials. Identify each job's actual inputs rather than recording only the operating system name.

## 2. Distinguishing the Runner Host from Inside the Container

The runner is the machine or executor that coordinates and executes the job. A job can run directly on the host, inside a container, or on a specialized executor. These approaches have different boundaries:

- When running directly on the host, the job uses the OS and tools installed on the runner. Changes to the runner image can directly affect outcomes.
- When running in a container, the job uses the container image's root filesystem and most user-space tools. However, the container still shares the host kernel and is affected by the container runtime/engine, CPU architecture, and runner configuration.
- With VMs or self-hosted runners, teams have finer control over machine images, kernels, and pre-installed tools, at the cost of owning updates and maintenance.

Therefore, pinning a container image does not mean pinning the entire execution machine. For example, the same Linux image can run on runners with different host kernels or container runtime versions. If a build depends on kernel features, filesystems, CPU instructions, or drivers, those factors must also be controlled or recorded.

## 3. Pinning the Operating System and Runner Image

### Choosing an Operating System Version Deliberately

Labels like `ubuntu-latest`, `windows-latest`, or `macos-latest` generally resolve to whatever the provider currently designates as latest at runtime. The underlying target can shift on the provider's upgrade schedule. This makes receiving updates convenient, but increases environment drift.

For greater stability, select a specific OS track supported by the platform—such as `ubuntu-24.04`—and decide how to control the actual image. A versioned OS label may still receive package and runner image updates within that track. It pins the OS generation, not necessarily individual packages or kernel patches.

GitHub Actions example:

```yaml
jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - name: Inspect environment
        run: |
          uname -a
          cat /etc/os-release
```

This workflow selects a specific Ubuntu track and logs actual runtime details. It does not lock the entire runner image. When deeper control is needed, use self-hosted runners with versioned images or run the job inside a container image pinned by digest.

### Using Immutable Images When User Space Needs Strict Control

A container image can package user-space OS libraries, the JDK, and required tools. Tags help humans identify versions; digests uniquely identify exact image contents.

```yaml
jobs:
  build:
    runs-on: ubuntu-24.04
    container:
      image: registry.example.com/ci/java-build:21.0.5@sha256:<IMAGE_DIGEST>
    steps:
      - name: Inspect toolchain
        run: |
          cat /etc/os-release
          java -version
          ./gradlew --version
      - name: Test
        run: ./gradlew clean test
```

`registry.example.com` and `<IMAGE_DIGEST>` are illustrative placeholders. In real pipelines, digests must come from a trusted registry and be reviewed alongside changes. Also verify that the image matches the runner architecture and includes the shell, user, certificates, and filesystem permissions the job expects.

### Pinning OS Packages

Pinning only the base image is insufficient if a Dockerfile installs packages from a mutable repository. For example, `apt-get install curl` might pull a different version on a different day. To improve stability, you can:

- Use repository snapshots or internal mirrors with managed history and contents.
- Pin explicit package versions where supported by the OS and repository.
- Record the installed package list and actual versions.
- Rebuild images periodically from updated base images and packages, then scan and publish a new digest.

Do not keep an outdated snapshot indefinitely. Snapshots make inputs reproducible; security patching processes must roll new patches into vetted snapshots or images.

## 4. Pinning Toolchains: JDK, Compilers, and Runtimes

The toolchain governs how source code is compiled and executed. For Java projects, consider at least:

- The JDK version running Gradle or Maven.
- The compiler version and Java language level of the source code.
- The JDK vendor or distribution when differences matter.
- The runtime version used when running tests or the application.
- Native toolchains such as C/C++ compilers, linkers, and build systems when using JNI or native images.

Declaring a Java toolchain in Gradle lets the project explicitly state the required major version:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

This configuration requests Java 21, though it does not necessarily lock a specific patch release or vendor. Gradle may pick a matching JDK already installed on the machine or auto-provision one if configured. When patch and vendor control is required, manage the JDK inside the runner/container image or use a toolchain setup mechanism with an exact version, then log the result with `java -version`.

When installing a JDK via an action, pin the action itself and specify the exact JDK version:

```yaml
steps:
  - name: Set up Java
    uses: actions/setup-java@<FULL_COMMIT_SHA>
    with:
      distribution: temurin
      java-version: '21.0.5+11'
```

`<FULL_COMMIT_SHA>` is a placeholder that must be replaced with a verified commit SHA. This configuration controls the action and requests a specific JDK version in the way the action supports; the runner itself remains a separate environment layer to account for.

## 5. Pinning Build Tools and Package Managers

Build tools are also pipeline inputs. Running a command that installs the latest version or relying on whatever version happens to be on the runner can cause the same repository to produce different results.

### Gradle Wrapper

The Gradle Wrapper lets a repository specify the exact Gradle version to use instead of relying on a globally installed Gradle on the runner. For example, in `gradle/wrapper/gradle-wrapper.properties`:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=<GRADLE_DISTRIBUTION_SHA256>
```

The checksum value is a placeholder; obtain the official checksum matching the exact distribution. `distributionSha256Sum` lets the Wrapper verify the downloaded archive's integrity. Review `gradlew`, `gradlew.bat`, and the wrapper JAR files under repository protection policies as well.

### Maven Wrapper

The Maven Wrapper provides a similar mechanism to pin the Maven distribution. For example, in `.mvn/wrapper/maven-wrapper.properties`:

```properties
distributionUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=<MAVEN_DISTRIBUTION_SHA256>
```

Checksums must likewise be obtained and verified against the exact distribution. Avoid downloading wrapper scripts or binaries from unverified sources during pipeline execution.

### Node.js, Python, and Package Managers

In other ecosystems, versions can be managed through configuration files committed alongside the repository, such as `.nvmrc`, `.python-version`, `.tool-versions`, or `mise.toml`. These files should declare explicit versions per project policy. Lockfiles such as `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, or Python lockfiles pin resolved dependencies.

A lockfile does not replace pinning the runtime and package manager. Control both the Node.js/Python version, npm/pnpm/Poetry/uv version, and how they are installed. Pipelines should use install modes that honor lockfiles—such as `npm ci`—rather than re-resolving dependencies without updating the lockfile.

## 6. Pinning CLIs and Auxiliary Tools

Deployment and verification jobs often pull additional tools such as Docker CLI, `kubectl`, Helm, Terraform, cloud CLIs, scanners, or linters. If a pipeline uses a script that fetches the latest release or an unpinned package manager, tool updates can alter deploy or scan behavior.

Practical rules:

- Specify explicit versions when installing CLIs; avoid `curl ... | sh` from URLs pointing to latest without verifying contents.
- Prefer official package repositories or releases; verify checksums or signatures when published by the vendor.
- Use vetted tool images referenced by digest where possible.
- Log CLI versions during runs for troubleshooting.
- Separate client CLI versions from the API or server versions they talk to; pinning the client does not guarantee the server runs the same version.

For example, a job can record tool versions before deploying:

```bash
docker version --format '{{.Client.Version}}'
kubectl version --client
helm version --short
terraform version
```

Exact flags may differ by tool version. If a CLI does not support printing versions with the syntax above, use the tool's official version command.

## 7. Controlling CPU Architecture, Locale, and Timezone

Two runners with the same OS name and toolchain can still differ in architecture or system settings. These differences matter especially for native binaries, multi-architecture images, date/time handling, and string tests.

**CPU architecture:** record whether the host is `x86_64`/`amd64` or `aarch64`/`arm64`. When building multi-architecture images, declare target platforms explicitly and verify manifest lists and digests. Native dependencies or compilers can emit architecture-specific binaries.

**Locale and encoding:** set a consistent locale, typically UTF-8, to prevent tests from depending on machine-specific collation, number formatting, or character handling. If an application requires a specific locale, configure it explicitly in the job and corresponding tests.

**Timezone:** use UTC for logs, timestamps, and tests needing consistency where business logic permits. Tests covering calendars, daylight saving time, or local timezone rules need explicit timezone data and timezone settings.

Example:

```yaml
env:
  LANG: C.UTF-8
  LC_ALL: C.UTF-8
  TZ: UTC
```

This is a reference configuration; verify that the locale exists inside the image being used and does not override valid application requirements.

## 8. Building Shared, Traceable Execution Environments

Across many repositories, repeating runner setup inside every pipeline easily introduces drift. Teams can build standardized CI images or shared environment templates. A CI image typically contains:

- A chosen OS track and necessary system packages.
- Verified versions of the JDK or runtime.
- Build tools or wrapper prerequisites.
- CLIs and scanners needed for a specific job category.
- CA certificates, timezone data, locales, and a non-privileged user.
- Metadata about image version, source commit that built the image, and package list.

Avoid building one monolithic image holding every tool for all pipelines. Instead, maintain role-specific images such as `java-build`, `container-build`, `security-scan`, and `deployment`. This shrinks attack surface and limits updates to relevant components.

Illustrative Dockerfile example:

```dockerfile
FROM eclipse-temurin:21.0.5_11-jdk-jammy@sha256:<BASE_IMAGE_DIGEST>

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
```

This is a skeleton example, not a complete production Dockerfile: replace the digest with a valid one, manage package versions or snapshot repositories per policy, and review the runtime user and permissions. Running `apt-get update` against a moving repository can still fetch different package versions on subsequent builds; strict reproducibility requires controlling package sources.

After building the CI image, push it to a registry, generate its digest, scan it, and record metadata. Pipelines consume the image by digest. When updating the JDK or OS packages, build a new image with a new digest and verify it before updating references.

## 9. Recording the Actual Runtime Environment in Every Run

Declaring versions in the pipeline file expresses team intent. For investigations, you also need to record what actually ran. A diagnostics step can capture:

- OS name, version, kernel, and architecture.
- Runner image or container image reference and digest.
- Versions of the JDK, compiler, Gradle/Maven, and package manager.
- Versions of key CLIs such as Docker, `kubectl`, or scanners.
- Commit SHA, lockfile fingerprint, and output artifact image digest.
- Locale, timezone, and environment variables affecting the build.

Example diagnostics step for a Java job:

```bash
cat /etc/os-release || true
uname -a
java -version
./gradlew --version
locale
date -u
```

On Windows or macOS, use equivalent commands to collect OS and toolchain details. Print only non-sensitive environment variables; never dump the entire environment, which can expose tokens, passwords, or credentials.

Environment metadata should be tied to both the pipeline run and the artifact. When a build breaks after a runner image update, teams can compare metadata between the last good run and the failing run instead of staring solely at source commits.

## 10. Updating Versions and Handling Security Patches

Pinning versions keeps environments stable, yet holding onto old versions indefinitely increases security risk and drops vendor support. Maintain an explicit update cycle:

1. **Inventory:** catalog active OS images, runners, JDKs, build tools, package managers, and CLIs.
2. **Track:** subscribe to support lifecycle notices, security advisories, and runner provider announcements.
3. **Evaluate:** review release notes, advisories, breaking changes, and compatibility requirements.
4. **Update under control:** update versions or digests in a pull request; avoid unrecorded direct edits on production runners.
5. **Verify:** run builds, tests, scans, and artifact checks in the updated environment.
6. **Roll out gradually:** test on a subset of pipelines or runners before expanding broadly.
7. **Roll back:** retain prior images/refs for an appropriate window and know how to revert if a new release causes regressions.

For critical vulnerabilities, prioritize patches according to security SLAs. An expedited update path can be used, while still verifying sources, checksums/signatures, compatibility checks, and recording the decision trail.

## 11. Limitations to Understand When Pinning Environments

Pinning the OS and toolchain reduces drift, but does not by itself guarantee fully deterministic builds:

- Hosted runners can change host-level components outside direct pipeline control.
- Containers share the host kernel; pinning an image does not pin the kernel.
- Package repositories can shift unless immutable snapshots or mirrors are used.
- Tools can call remote services or download fresh schemas or rule databases at runtime.
- Timestamps, random seeds, file ordering, CPU behavior, or external data can alter outputs.
- A pinned image digest can still harbor vulnerabilities; pinning never replaces scanning and patching.

Determine the required level of control based on risk and goals. For routine jobs, picking a specific OS track, using wrappers/lockfiles, and logging actual versions may suffice. For reproducible builds or critical release pipelines, consider ephemeral runners from managed images, digest-pinned containers, package snapshots, fixed toolchains, and full provenance.

## 12. Execution Environment Pinning Checklist

- [ ] Select runner OS/version explicitly; understand how far hosted runner labels can update underneath.
- [ ] Distinguish the runner host from the container/executor image and document each layer's limits.
- [ ] Pin container images by digest when locking user space.
- [ ] Control package repositories, package versions, or snapshots when builds require reproducibility.
- [ ] Specify JDK/compiler/runtime versions and log actual runtime versions.
- [ ] Use Gradle/Maven Wrappers and verify distribution checksums.
- [ ] Pin package managers and dependencies with lockfiles and integrity hashes where supported.
- [ ] Pin critical CLI versions and verify download sources.
- [ ] Control architecture, locale, encoding, and timezone when they affect outputs.
- [ ] Store secret-free diagnostics alongside pipeline runs and artifacts.
- [ ] Maintain patching, verification, rollout, and rollback procedures for images and toolchains.

When the OS, toolchains, and tools are explicitly declared, verified at the source, and updated through review, the execution environment becomes a traceable part of the pipeline. Teams can explain differences across runs, reproduce bugs accurately, and roll out security patches without losing control over CI/CD quality.
