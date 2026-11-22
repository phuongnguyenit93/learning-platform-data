# Selecting and Pinning JDK, org.crac Library, and Operating System Versions

To practice CRaC reliably, you need to select an environment stack consisting of a JDK with checkpoint/restore support, the `org.crac` Java API, an operating system, and compatible system components. Simply noting “Java 21” or “Linux” is not enough to reproduce the environment: two JDK builds with the same major version can differ in CRaC support, and two Linux machines can differ in kernel, CPU architecture, CRIU, and container configuration.

The goal of pinning versions is to ensure every build, checkpoint image creation, and restore uses a verified set of components. When an upgrade is needed, you make deliberate changes, re-verify the entire process, and only then publish the new version set.

## 1. What Does a CRaC Environment Stack Consist Of?

When selecting an environment, consider the following components together:

| Component | What to Specify | Why It Must Be Pinned |
|---|---|---|
| JDK | Vendor, JDK line, full version, build, and architecture | Not every JDK distribution includes a CRaC implementation; builds may differ in how they support checkpoint/restore |
| CRaC Java API | Maven coordinates `org.crac:crac` and version if the project requires this dependency | Source code needs an API compatible with the JDK and CRaC-integrated libraries |
| Operating System | Linux distribution, version, architecture, and system libraries | Checkpoint/restore depends on kernel capabilities and the process environment |
| CRIU | Tool version and installation method | On Linux implementations using CRIU, this tool participates in saving and restoring process state |
| Container/runtime | Base image, container runtime, namespace configuration, cgroup, permissions, and mounts | A container image does not carry the host kernel or all permissions required for checkpoint/restore |
| Build tool | Gradle Wrapper, toolchain configuration, and dependency lock | Makes compilation and dependency resolution reproducible |

The components above form a **verified version stack**. You should not pick the JDK, libraries, and operating system independently based on “latest” criteria and then assume they are compatible with each other.

## 2. Selecting a JDK with CRaC Support

### 2.1. Start from the Distribution's CRaC Capability

CRaC requires support from the JVM and the checkpoint/restore platform. Installing a standard Java JDK and adding the `org.crac` dependency to Gradle does not automatically turn that JVM into a CRaC-enabled JDK.

When choosing a JDK vendor, check the official documentation for the exact vendor and version line. Confirm the following points:

- Whether the vendor provides a JDK build with built-in or supported CRaC for the major version the project needs.
- Whether that build supports the target operating system and CPU architecture for deployment.
- How enabling checkpoint, creating an image, and restoring are documented.
- Whether the JDK requires specific CRIU, kernel, permission, or system configurations.
- Whether the vendor provides an appropriate security update schedule, support policy, and terms of use.
- Whether that version is compatible with the application's frameworks, agents, JNI, and native libraries.

You can choose JDK 21 as the major version for a project using Java 21, but you must choose a **JDK 21 distribution that actually has CRaC**. Do not infer CRaC capability solely from the Java version number or from the fact that a JDK can run a normal Java application.

### 2.2. Record the Full Version

Several different pieces of information are often lumped together into the phrase “Java 21”:

- **Major version:** for example `21`, indicating the Java language and platform line.
- **Patch/update version:** for example `21.0.x`, indicating the update release within the JDK line.
- **Vendor build:** the vendor, build number, and vendor-specific patches.
- **CRaC capability:** the specific checkpoint/restore capability of that build.

Two JDKs that are both Java 21 but from different vendors or different builds cannot be assumed to create and restore the same checkpoint image. For images used in deployment, pin the vendor, full version, and tested build. When caution is needed, create and restore the image using the exact same JDK build.

You can inspect the currently running JDK information with:

```bash
java -version
java -XshowSettings:properties -version
```

The second command additionally displays properties such as `java.vendor`, `java.version`, `java.runtime.version`, `java.home`, and `os.arch`. Save the output to the build log or environment profile so you know the exact JDK that created the image.

### 2.3. Use Toolchains for Compilation, Pin the Runtime for Checkpoint

Gradle Java Toolchains help select a JDK by major version and vendor. For example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

The configuration above requests Java 21 for tasks that use the toolchain. It does not fully lock the patch version, build number, or CRaC capability. Gradle may locate a matching JDK installed on the machine or download a toolchain according to the configuration; therefore, a major version configuration alone should not be treated as proof that the runtime is pinned.

Separate the two requirements:

1. **Compilation JDK:** the toolchain needs the right major version and vendor according to project conventions.
2. **Image creation and restore JDK:** must be the exact pinned CRaC-enabled JDK build, typically provided via a container image with a full version tag and immutable digest, or via a managed JDK installer with a checksum.

If you use a toolchain, configure the vendor once the project has chosen one. Afterward, CI still needs to verify the actual runtime version using `java -version` and system properties. A toolchain does not replace verifying the CRaC build.

## 3. Selecting and Pinning the `org.crac` Library

### 3.1. Distinguish the Java API from the JVM's Checkpoint Capability

The `org.crac` package provides the Java types that an application uses to register resources and handle lifecycle events, such as `Resource`, `Context`, and `Core`. The Maven dependency is commonly declared with the coordinates:

```text
org.crac:crac
```

This dependency provides the API for Java code as packaged by the library. It does not replace a CRaC-capable JDK, does not provide kernel checkpoint capability, and does not install CRIU. An application that compiles with `org.crac` can still fail to checkpoint or restore if the runtime does not support CRaC.

Some JDK distributions or frameworks have their own way of providing/integrating the API. Therefore, before adding the dependency, read the documentation for your chosen JDK and framework. The goal is to have a single consistent API source and avoid packaging duplicate classes or classes incompatible with the runtime.

### 3.2. Lock Dependency Versions

Do not use dynamic versions such as `1.+`, `latest.release`, version ranges, or `SNAPSHOT` for dependencies used in the image creation process. Those declarations can resolve to a different version in a subsequent build without any changes to the source code.

With a Gradle Version Catalog, you can declare an explicit version:

```toml
[versions]
crac-api = "1.4.0"

[libraries]
crac-api = { module = "org.crac:crac", version.ref = "crac-api" }
```

Then reference the alias in `build.gradle`:

```groovy
dependencies {
    implementation(libs.crac.api)
}
```

`1.4.0` here is an example of specifying a concrete version, not a claim that it is the latest version or compatible with every JDK. When applying this to a project, choose the version supported by the documentation of your pinned JDK/framework and verify it with an actual build. If the JDK vendor already provides the API in another way, follow that guidance instead of mechanically adding a second dependency.

For dependencies that affect post-restore execution, check both direct dependencies and transitive dependencies. Do not lock only `org.crac:crac` while ignoring the versions of frameworks or libraries managing connection pools, HTTP clients, and schedulers that integrate with CRaC.

### 3.3. Lock Dependencies and Verify Artifacts

A Version Catalog centralizes version declarations, but does not by itself lock every dependency resolution result. You can enable dependency locking in Gradle:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Then generate or update the lock state with an appropriate Gradle task, for example:

```bash
./gradlew dependencies --write-locks
```

When dependencies change intentionally, inspect the diff of the lockfiles and confirm the new versions. Do not delete lockfiles just to resolve a resolution error without understanding the cause.

You can enable dependency verification to check artifact checksums or signatures against approved metadata. When generating verification metadata, review the download sources and checksum values before committing the metadata file to the repository. Automatically accepting all checksums from an unverified download diminishes the value of the verification step.

In CI, save the dependency tree of the runtime configuration to identify the exact artifacts being packaged. When the application uses `org.crac`, verify that there are no conflicting API versions and no library replacing CRaC classes with an incompatible version.

## 4. Selecting the Operating System and Checkpoint/Restore Platform

### 4.1. Identify the Platform Supported by the JDK

Common CRaC implementations on Linux work with CRIU (Checkpoint/Restore In Userspace) to checkpoint and restore processes. Therefore, the practice environment needs a Linux distribution, kernel, and system configuration that meet the requirements of the chosen JDK/CRaC build.

Do not assume that every operating system supports this workflow equally. Windows or macOS development machines can still be used to write code, edit Gradle files, and perform normal build steps. However, checkpoint/restore must be verified on a platform supported by the CRaC JDK. If the deployment environment is Linux, run checkpoint/restore smoke tests on Linux directly in CI or an equivalent test environment.

When selecting a Linux distribution, check:

- Whether the kernel version and configuration meet the requirements of CRIU and the JDK.
- Whether the CPU architecture is `x86_64`/`amd64` or `aarch64`/`arm64`, and whether the JDK has a CRaC build for that architecture.
- Whether the glibc version and system libraries are compatible with the JDK and native libraries.
- The CRIU version required or tested by the JDK vendor.
- Whether the required namespace, cgroup, mount features, and permissions are granted by the container environment.
- Whether the security policies of the host, container runtime, and orchestration platform allow checkpoint/restore operations.

Do not choose a distribution solely because it produces a small container size. For example, an image using musl or a minimal environment may lack libraries or tools required by the chosen JDK/CRIU. Check the compatibility documentation before using minimal images like Alpine.

### 4.2. Pin the Distribution and Architecture

In your environment documentation, specify the distribution name and version—for example, a specific Ubuntu or Debian release—along with the CPU architecture. Avoid floating labels like `latest`, `stable`, or simply `linux`.

The `amd64` and `arm64` architectures are two separate targets. An image created on `amd64` cannot be assumed to restore on `arm64`. If the product supports both architectures, maintain separate JDKs, images, CRIU configurations, and tests for each architecture.

Inspect the operating system and architecture information on a Linux machine:

```bash
cat /etc/os-release
uname -a
uname -m
ldd --version
criu --version
```

These commands record the distribution, kernel, architecture, glibc version, and CRIU version. If `criu` is not yet present in the environment, install it according to the distribution's instructions and re-verify the version after installation.

### 4.3. Distinguish the Container Image from the Host Kernel

A container image can pin the filesystem, JDK, libraries, and CRIU tool inside the container. However, a container uses the host's kernel. Therefore, pinning a container image digest is not enough to pin the entire checkpoint/restore environment.

In Docker or Kubernetes, you must also consider:

- The container runtime and its version.
- The permissions or capabilities required for checkpoint/restore.
- The configuration of the PID namespace, mount namespace, network namespace, and cgroup.
- Whether volume paths and mount points exist and have the same meaning upon restore.
- Whether security profiles such as seccomp, AppArmor, or SELinux block required operations.
- How the platform handles network addresses, ports, and instance identity after restore.

Do not enable broad privileges just to make the first test run. Use the least-privilege configuration according to the documentation of CRIU, the container runtime, and the deployment platform, and test that exact configuration. A test running in a privileged container when the real environment does not grant similar privileges does not prove that the deployment workflow will work.

## 5. Building a Compatibility Matrix

Before installing, create a matrix specifying the components and their verification status. Example profile structure:

```yaml
cracEnvironment:
  java:
    vendor: "<JDK vendor>"
    distribution: "<CRaC-enabled distribution>"
    version: "<full version and build>"
    architecture: "amd64"
  api:
    coordinate: "org.crac:crac"
    version: "<pinned version approved for this JDK>"
  operatingSystem:
    distribution: "<Linux distribution>"
    version: "<exact release>"
    architecture: "amd64"
    kernelBaseline: "<tested kernel baseline>"
  criu:
    version: "<tested version>"
  container:
    image: "<repository>:<immutable version>@sha256:<digest>"
    runtime: "<tested runtime and version>"
  build:
    gradleWrapper: "<wrapper version>"
    dependencyLocking: true
    dependencyVerification: true
  validation:
    checkpoint: "PASS/NOT_TESTED"
    restore: "PASS/NOT_TESTED"
    lastVerified: "<date or CI build identifier>"
```

Values in angle brackets are placeholders to be filled in according to the chosen environment. This is a descriptive and version-control profile; do not copy the placeholders verbatim into a runtime configuration.

The matrix can be extended across `development`, `CI`, and `production` environments, but it should indicate which components must remain identical. In particular, the JDK used to create the image and the JDK used to restore must follow a tested compatibility policy. If versions differ, there must be evidence from vendor documentation and test results rather than assuming the difference is safe.

An example of how to record verification status:

| Item | Selected Value | Evidence to Save |
|---|---|---|
| JDK | Vendor + full version + build | `java -version`, runtime properties, and download source |
| CRaC API | `org.crac:crac` + version | Dependency tree, lockfile, and verification metadata |
| Linux | Distro + release + architecture | `/etc/os-release`, `uname -a`, `uname -m` |
| CRIU | Exact version | `criu --version` and verification logs |
| Container | Full image tag + digest | Image inspect and runtime configuration |
| Checkpoint | Image creation result | Checkpoint logs and artifact location |
| Restore | Restore and readiness result | Restore logs, health check, and readiness time |

## 6. Pinning Container Images and Build Tools

### 6.1. Use Images with Full Versions and Digests

When a vendor provides a CRaC container image, select a tag with a full version and pin the digest of the tested image. Example declaration structure:

```dockerfile
FROM <vendor>/<crac-jdk>:<exact-version>@sha256:<verified-digest>

WORKDIR /app
COPY build/libs/application.jar application.jar

ENTRYPOINT ["java", "-jar", "application.jar"]
```

This is an illustrative template; replace the placeholders with the actual image from your chosen JDK vendor. A digest ensures that the same image reference points to the same image contents across builds. Tags can be updated by the vendor, so a tag alone does not provide an equivalent level of pinning.

If you need to install CRIU or system packages in the Dockerfile, use controlled repositories and package versions. Record the installation output in the image build and re-verify with `criu --version`. Do not install unpinned packages in a build step that requires exact reproducibility.

### 6.2. Pin the Gradle Wrapper and Dependencies

The Gradle Wrapper ensures every machine uses the same Gradle version declared in `gradle-wrapper.properties`. Commit the wrapper files and verify the distribution URL and checksum if the project uses distribution verification configuration.

Combine three layers of control:

1. **Version Catalog:** centralizes direct dependency versions such as `org.crac:crac`.
2. **Dependency locking:** records the actual versions resolved by Gradle for each configuration.
3. **Dependency verification:** verifies artifact checksums or signatures against approved metadata.

When building to create a checkpoint image, record the Gradle version, JDK, dependency tree, and container digest. This makes it possible to identify which change caused a difference between two images.

## 7. Process for Selecting and Finalizing the Environment Stack

You can follow this sequence to avoid selecting incompatible components:

**Step 1 — Finalize the deployment target.** Determine which Linux distribution and CPU architecture the application runs on, whether it uses containers or virtual machines, and where checkpoint/restore is performed. The target environment bounds your JDK and OS choices.

**Step 2 — Select the CRaC-enabled JDK.** Cross-check vendor documentation against the OS, architecture, and kernel requirements. Record the vendor, full version, build, and distribution source.

**Step 3 — Finalize the CRaC API.** Determine how the chosen JDK/framework provides the API. If the `org.crac:crac` dependency is needed, choose a specific supported version, declare it centrally, and inspect the dependency tree.

**Step 4 — Select Linux and CRIU.** Choose a distribution and architecture supported by the JDK. Pin the CRIU version according to compatibility guidance, then verify the kernel and system configuration on the target runner or host.

**Step 5 — Package the runtime.** Use a container image with a full version and digest. Clearly distinguish what belongs to the container image and what belongs to the host, especially the kernel, permissions, namespaces, and cgroups.

**Step 6 — Lock the build tools.** Pin the Gradle Wrapper, dependency locks, and verification metadata. Verify the actual runtime JDK in CI.

**Step 7 — Test checkpoint and restore.** Start the application on the exact target environment, create the image, restart from the image, and verify resource callbacks and readiness. A successful build or normal JVM startup alone does not prove CRaC works.

**Step 8 — Save the matrix and evidence.** Commit the version profile, build configuration, and lockfiles. Store verification logs per CI build or release so it is clear which environment stack was approved.

## 8. Verifying the Environment with a Smoke Test

A smoke test should verify both platform capability and application behavior. A minimal procedure includes:

1. Print the JDK, vendor, runtime version, and architecture information.
2. Print the Linux, kernel, and CRIU version information.
3. Start the application using the pinned CRaC JDK.
4. Confirm that the required `Resource` instances are registered.
5. Request a checkpoint and confirm the image is created successfully.
6. Restore the image using the runtime from the selected matrix.
7. Confirm that the `afterRestore` callback runs, required connections are re-established, and readiness transitions to healthy.
8. Record the time from restore start until the application is ready.

For example, the application can log inside the two callbacks:

```java
public final class ExampleResource implements org.crac.Resource {

    @Override
    public void beforeCheckpoint(
            org.crac.Context<? extends org.crac.Resource> context) {
        System.out.println("Preparing resource before checkpoint");
        // Pause or close the resource according to the application's policy.
    }

    @Override
    public void afterRestore(
            org.crac.Context<? extends org.crac.Resource> context) {
        System.out.println("Restoring resource after checkpoint");
        // Recreate or validate environment-dependent resources.
    }
}
```

Logs help confirm whether callbacks are invoked in the right phase. For real resources, verify recovery outcomes rather than just checking for log output. For example, after restore you must confirm that database connections can execute queries, message consumers have re-registered, and readiness checks reflect the actual state.

The smoke test should also be run on the exact target architecture and container configuration. If production runs Kubernetes with a specific security profile, testing only on a laptop or a broadly privileged container is not enough to confirm production compatibility.

## 9. Controlled Version Upgrades

The JDK, API library, CRIU, and Linux distribution can all receive security patches or support changes. Pinning versions does not mean staying on an old version forever; it means every change is reviewed and verified.

When upgrading, change one group of components deliberately and save the new matrix. For example, when updating a JDK patch version, re-verify compatibility with `org.crac`, frameworks, native libraries, CRIU, and image restore. When updating CRIU or the kernel, re-run checkpoint/restore on a host with the matching configuration.

An upgrade process should include these steps:

- Read the release notes and support matrices from the JDK vendor, CRaC API, and CRIU.
- Make explicit version changes in the version catalog, lockfiles, Dockerfile, or environment profile.
- Rebuild the application and create a new checkpoint image using the new version stack.
- Restore the new image on the target environment and run the smoke test.
- Compare startup time, restore time, readiness, and resource errors against the approved baseline.
- Only update the standard version stack after all required checks pass.

Do not use a checkpoint image created by an old environment stack as the default artifact after upgrading the JDK, OS, or native libraries. Create a new image from the application and the new environment stack unless there is compatibility documentation and specific testing proving reuse is valid.

## 10. Common Mistakes

**Locking only the Java major version.** `21` does not identify the vendor, patch, build, or CRaC capability. Record the full version and verify the actual runtime.

**Thinking that adding `org.crac` is enough.** The Java API does not replace a CRaC-enabled JDK, CRIU, or operating system checkpoint/restore capability.

**Using dynamic dependency versions.** `1.+` or `latest.release` can cause a build to pull in a different dependency without a reviewed change. Use concrete versions, locking, and artifact verification.

**Treating all Linux distributions as equivalent.** Kernel, architecture, glibc, CRIU, namespaces, and container permissions can all affect restore. Specify the distribution and test on the target platform.

**Pinning only the container tag.** A tag can point to a new image later; a digest pins the image contents. Even so, the kernel and several conditions still belong to the host.

**Creating an image on one architecture and restoring on another.** Do not assume `amd64` and `arm64` can share checkpoint images. Build and test each architecture separately.

**Only checking that the application starts normally.** A working JVM does not mean checkpoint/restore works. You must create an image, restore it, and confirm the application is ready.

**Upgrading one component without updating the matrix.** A change to the JDK, CRIU, or base image can cause the environment stack to no longer match the tested set. Update the profile and re-run the smoke test.

## 11. Self-Check Questions

1. **Why is writing “Java 21” not enough to pin a CRaC JDK?** Because it lacks the vendor, patch version, build, and confirmation that the JDK supports CRaC on the target platform.
2. **Does adding `org.crac:crac` turn a normal JDK into a CRaC-enabled JDK?** No. The dependency provides the Java API; checkpoint/restore capability requires runtime and platform support.
3. **Why is it necessary to lock the `org.crac` version?** So that the source code and runtime use a verified API, avoiding unintended dependency changes between builds.
4. **Why does a container digest not pin the entire CRaC environment?** A container uses the host kernel; permissions, namespaces, cgroups, and several checkpoint/restore conditions reside outside the image filesystem.
5. **Can you create a checkpoint image on `amd64` and assume it restores on `arm64`?** No. You must follow the compatibility matrix and test each architecture separately.
6. **What proves that an environment has been verified?** An actual workflow that creates a checkpoint image, restores the image, and confirms resources and readiness work on the target environment.

## Conclusion

A reproducible CRaC environment requires simultaneously pinning the CRaC-enabled JDK, the `org.crac` API, Linux, CRIU, CPU architecture, container/runtime, and build tools. Every choice must be based on vendor compatibility documentation and verified through an actual checkpoint and restore workflow.

Store the version stack along with digests, lockfiles, and smoke test evidence in the repository or release records. When upgrading, create a new matrix, build a new image, and verify restore on the target environment before using it in deployment. This way, the development team knows the exact environment stack an image was built from and can reproduce the results when needed.
