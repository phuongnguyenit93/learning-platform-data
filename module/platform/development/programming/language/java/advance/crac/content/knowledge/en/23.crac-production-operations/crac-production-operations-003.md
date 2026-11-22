# Tracing a Release from Source Code to JDK and Checkpoint

With Java CRaC (Coordinated Restore at Checkpoint), a release is not just a JAR file or container image. The application also depends on the specific JDK, CRaC-enabled build, native libraries, JVM configuration, kernel/CRIU environment, and process state stored inside the checkpoint. Without recording relationships among these components, when a Pod fails or needs a rollback, the operations team struggles to determine which source commit and which JDK produced the checkpoint, and whether it fits the restoring node.

Release traceability is the ability to trace backward from a running checkpoint to the exact source commit, build, dependencies, image, JDK, and image-creation environment; and simultaneously trace forward from a commit to every artifact and checkpoint produced from it. Each link in the chain needs an immutable identifier, checksum or signature, build metadata, and a clear link to the preceding link.

A typical traceability chain:

~~~text
Git commit
   |
   v
CI run + build toolchain + dependency lock
   |
   v
JAR / application artifact + SBOM + build provenance
   |
   v
OCI image digest + exact JDK/CRaC + native runtime
   |
   v
Warm-up profile + runtime configuration
   |
   v
Checkpoint files + checkpoint manifest + signatures
   |
   v
Restore target (kernel / CRIU / CPU / container runtime)
   |
   v
Running Pod + release identity + restore attempt
~~~

The goal is for operators to answer accurately: Which source commit does this Pod run? Which JDK build created the checkpoint? Do the image and native libraries match the manifest? Which node pool was this image restored on? If a rollback is needed, which artifact has already been verified?

## 1. Why Does CRaC Require Deeper Traceability Than a Normal Java Release?

In a normal Java deployment, release teams typically trace from source commit to JAR or container image. On startup, the JVM starts from scratch and builds new runtime state.

With CRaC, a checkpoint saves the state of an already-running process. That state may contain:

- The application's heap and object graph.
- Class metadata and class initialization state.
- JIT-compiled code and runtime metadata.
- Thread state, stacks, and some native state.
- Loaded client objects, caches, and configuration.
- State related to native libraries and open resources, depending on support.

A checkpoint is therefore tied to a combination of inputs and image-creation environment. The exact same JAR can run with two different JDK builds, different JVM flags, different native dependencies, or different CPU features. Those differences can affect restorability and post-restore behavior.

### 1.1. A JAR Does Not Fully Identify the Runtime

A JAR file does not fully indicate:

- JDK vendor, version, and build number.
- Which CRaC support and patches the JDK includes.
- JVM flags and GC configuration.
- Base image and OS packages.
- glibc or musl version.
- OpenSSL, zlib, and native libraries.
- CPU architecture and instruction set baseline.
- Kernel, CRIU, container runtime, and security policies.

Therefore, storing only an application version like 2.4.1 is insufficient to determine where a checkpoint can be restored.

### 1.2. Checkpoints Are Artifacts With Their Own Lineage

A checkpoint must have its own identifier linked to the release from which it was created. One release can produce multiple checkpoints due to differing:

- Warm-up profiles.
- Runtime configurations.
- Node pools or CPU baselines.
- JDK/CRaC builds.
- Kernel/CRIU environments.
- Warm-up datasets or configurations.

Do not reuse the same artifact name for different images. Each checkpoint needs a distinct checkpoint ID and digest, even when they originate from the same source commit.

### 1.3. Traceability Aids Incident Response and Rollback

When restore fails, lineage helps narrow down:

- Did source change or did dependencies change?
- Does the JDK build differ from the tested version?
- Was the checkpoint modified or corrupted during storage?
- Does the restore node have a different kernel, CPU, or CRIU baseline?
- Which configuration or secrets did warm-up load?
- Is the Pod using the right checkpoint for the current release?

When rolling back, you can select the exact checkpoint tested with the compatible image, JDK, and environment instead of picking a file merely by similar name.

## 2. Identification Model for the Entire Release Chain

Each layer needs an identifier that never changes once the artifact is released.

| Component | Identifier to store | Example |
|---|---|---|
| Source | Git commit SHA | a1b2c3... |
| Source tree | Tree SHA and clean/dirty status | tree:..., clean=true |
| Release | Release ID | orders-api-2026.11.13.2 |
| CI build | Pipeline run ID and attempt | build-84721/1 |
| Build toolchain | Gradle/Maven, compiler, and builder image digest | gradle-8.x, sha256:... |
| Dependency graph | Lockfile checksum | sha256:... |
| Application artifact | JAR SHA-256 | sha256:... |
| Container image | OCI image digest | sha256:... |
| JDK | Vendor, version, build, and image digest | Exact distribution/build |
| Native runtime | libc, OpenSSL, JNI library versions | Package/version/digest |
| Runtime config | JVM flags and config profile version | runtime-profile-v7 |
| Warm-up | Scenario set and dataset version | warmup-profile-v4 |
| Checkpoint | Checkpoint ID and file digests | checkpoint-... |
| Restore target | Node pool, arch, kernel, CRIU | linux-x86-pool-a |
| Restore attempt | Pod UID and attempt ID | podUID/restore-2 |

Tag names such as latest, stable, or production can be helpful for humans, yet should not be the sole evidence of artifact identity. Tags can be repointed to different contents. Digests, commit SHAs, and build IDs are the appropriate values for traceability.

### 2.1. Release ID and Checkpoint ID Serve Different Roles

A Release ID identifies a released application version. A Checkpoint ID identifies a specific image creation.

Example:

- Release: orders-api-2026.11.13.2
- Source commit: a1b2c3d4...
- Checkpoint: orders-api-2026.11.13.2-jdk21crac-x86-pool-a-warm4-01

One release can have multiple checkpoints:

| Release | Checkpoint | Reason |
|---|---|---|
| orders-api-2026.11.13.2 | cp-x86-pool-a-001 | CPU baseline A |
| orders-api-2026.11.13.2 | cp-x86-pool-b-001 | Kernel/runtime pool B |
| orders-api-2026.11.13.2 | cp-x86-pool-a-002 | New warm-up profile |

These checkpoints all point to one source release yet have different environment lineages.

## 3. Tracing from Git Source

The first step is identifying the exact source tree used for building.

Information to store:

- Repository URL or repository identity.
- Full commit SHA.
- Branch and tag at build time.
- Git tree SHA.
- Working tree status.
- Submodule commits if any.
- Git LFS object identities if used.
- Patches or generated sources involved in the build.
- Build timestamp and CI workflow identity.

### 3.1. Do Not Build from an Indeterminate Working Tree

Building from a working tree with uncommitted changes means the commit SHA no longer fully describes what was built.

CI should verify a clean working tree or explicitly record applied patches/diffs. For production builds, the easiest approach to trace is building from an immutable commit in a clean CI checkout.

Common Git commands:

~~~bash
git rev-parse HEAD
git rev-parse HEAD^{tree}
git status --porcelain
git submodule status --recursive
git describe --tags --always --dirty
~~~

The git status --porcelain command producing no output usually indicates a clean working tree. If changes exist, build provenance must record those exact changes or the pipeline should halt before creating a release artifact.

### 3.2. Commit SHA Must Accompany Repository Identity

A commit SHA is meaningful only when you know which repository contains that commit. Two different repositories can theoretically share an object SHA or share a mirrored commit.

Store the normalized repository URL, organization/project identity, and commit SHA. If using mirrors, record both the upstream identity and the mirror build source.

### 3.3. Source Tags Do Not Replace Commit SHAs

Tags can be moved or deleted if the repository allows it. Store tags for readability, yet use the commit SHA as the primary identifier. Release tags should be protected per repository governance procedures.

## 4. Tracing Builds and Dependencies

Even the same source commit can produce different artifacts if the toolchain or dependencies change.

Build inputs to record:

- Gradle or Maven version.
- JDK used to run the build.
- Java compiler version and options.
- Plugin versions.
- Dependency lockfiles.
- Repositories/mirrors used to download dependencies.
- Build container image digest.
- Non-sensitive build arguments and environment variables.
- Test results and test suite version.
- Build script revision.
- Generated code and code generator versions.

### 4.1. Dependency Locking

Dependency declarations using version ranges or dynamic versions may resolve differently across two builds. Use dependency locking or dependency verification to reduce uncontrolled changes.

With Gradle, commit lockfiles and verification metadata into source control per project policy. With Maven, dependency management and repository policies can be used to control versions.

### 4.2. The Build Toolchain Is Also an Input

Identical source and dependencies with different compilers or build plugins can generate different bytecode or resources. Therefore, build provenance should record:

- Build tool version.
- Build runner JDK vendor/version/build.
- Runner OS/architecture.
- Build image digest.
- Compiler flags.
- Plugin versions.

### 4.3. Checking the JAR After Build

Compute artifact digests and record them in release metadata:

~~~bash
sha256sum build/libs/orders-api.jar
jar --describe-module --file build/libs/orders-api.jar
unzip -l build/libs/orders-api.jar
~~~

These commands are examples for Linux runners. On Windows, Get-FileHash can be used to compute SHA-256. The digest must be computed on the exact file that will be packaged and released.

Do not compute a checksum for a file and then modify its contents before building the container. If the artifact is transformed or repackaged, compute digests at each layer.

## 5. SBOM and Build Provenance

An SBOM (Software Bill of Materials) describes the software components contained inside an artifact. Build provenance describes how an artifact was produced and from which inputs.

These two pieces of information complement each other:

- SBOM answers: "Which packages/libraries does this artifact contain?"
- Provenance answers: "From which source, toolchain, and workflow was this artifact built?"

### 5.1. SBOM for Application Artifacts

An SBOM should record direct and transitive dependencies, including versions and package identities. Common formats include SPDX and CycloneDX.

For a Java application, the SBOM may include:

- Maven/Gradle dependencies.
- Frameworks and libraries.
- Native packages packaged inside the image.
- JNI libraries.
- Operating system packages inside the container image.

A JAR SBOM does not yet describe the entire JDK and OS packages if they reside in the base image. A separate image SBOM or a unified report may be required.

### 5.2. Provenance for Builds

Provenance should bind the artifact digest to:

- Source repository and commit.
- Build invocation.
- Builder identity.
- Build environment.
- Dependency resolution.
- Build parameters.
- Required check results.

Attestation models such as in-toto/SLSA provenance can be used. The goal is not merely producing a JSON file, but creating verifiable evidence from a trusted publisher linked to the artifact digest.

### 5.3. An SBOM Is Not a Checkpoint Manifest

An SBOM describes software. A checkpoint manifest must also describe the runtime and image-creation environment:

- JDK CRaC build.
- JVM flags.
- Kernel and CRIU.
- CPU architecture/baseline.
- libc and native libraries.
- Container image digest.
- Warm-up profile.
- Checkpoint file digests.
- Restore compatibility constraints.

Link the image's SBOM and provenance into the checkpoint manifest rather than trying to cram all package info into one unstructured field.

## 6. Pinpointing the Exact JDK Creating the Checkpoint

The JDK is one of the most critical links. Recording only Java 21 or JDK 21 is insufficient.

Record:

- Vendor/distribution.
- Java runtime version.
- Full build string.
- VM name and VM version.
- CRaC support/patch level.
- JDK image digest.
- JDK package checksum if installed via package.
- JVM flags.
- GC and compiler configuration.
- Critical Java modules/providers.

### 6.1. Collecting Runtime Information

The following commands record Java information in the checkpoint-creation environment:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Important system properties can be logged from the application:

~~~java
public final class RuntimeIdentity {

    public static void print() {
        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("java.vendor="
                + System.getProperty("java.vendor"));
        System.out.println("java.vm.name="
                + System.getProperty("java.vm.name"));
        System.out.println("java.vm.version="
                + System.getProperty("java.vm.version"));
        System.out.println("os.name="
                + System.getProperty("os.name"));
        System.out.println("os.version="
                + System.getProperty("os.version"));
        System.out.println("os.arch="
                + System.getProperty("os.arch"));
    }

    private RuntimeIdentity() {}
}
~~~

These properties are useful for runtime observability, yet do not replace the JDK image digest or build provenance. Some CRaC/CRIU details must be collected from the pipeline and host because not all details are exposed by Java system properties.

### 6.2. Recording JVM Flags

JVM flags affect the heap, GC, JIT, code cache, and runtime behavior. Record the exact effective flags rather than only part of the launch command.

They can be recorded using appropriate JVM tooling, for example:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
~~~

PID is the process ID of the JVM on the host/container. Commands must run in an environment with permission to access the process. Do not include secrets or sensitive values in the manifest if they might appear on the command line.

### 6.3. The JDK Image Digest Is a Stronger Identifier Than a Tag

If using a container base image containing the JDK, record the OCI digest instead of only a tag like jdk:21-crac. A tag can change contents over time. The digest identifies the exact image used.

If the JDK is installed via package, record the package version, repository identity, and checksum of the package or installation source. For custom builds, save the source/build recipe and output digest.

### 6.4. Create a New Checkpoint When the JDK Changes

When changing the JDK build, CRaC patch, JVM flags, or native runtime, do not continue attaching an old checkpoint to a new release without testing. Create a checkpoint with the new runtime, restore in the target environment, and run smoke tests.

## 7. Tracing Container Images and Native Runtimes

A checkpoint is typically created inside a specific container image or a specific runtime filesystem. The image digest is a crucial link between the application artifact, the JDK, and OS packages.

Record:

- OCI repository and digest.
- Base image digest.
- JAR digest inside the image.
- JDK distribution/build.
- libc and dynamic linker.
- OpenSSL and native packages.
- JNI libraries and checksums.
- User/group and security configuration.
- Entrypoint, command, and environment profile version.

### 7.1. Do Not Store Only Image Tags

Example:

~~~text
registry.example.com/orders-api:2026.11
~~~

This tag can be republished or pointed to another image. Store the digest in the manifest:

~~~text
registry.example.com/orders-api@sha256:<image-digest>
~~~

At deployment time, reference the digest or verify the tag resolves to the exact released digest.

### 7.2. Native Dependencies Need Checksums

For critical JNI libraries or native packages, store versions and checksums. This detects cases where filenames match yet contents changed.

Useful Linux commands:

~~~bash
file /opt/app/lib/libexample.so
sha256sum /opt/app/lib/libexample.so
ldd /opt/app/lib/libexample.so
readelf -h /opt/app/lib/libexample.so
~~~

Not every native dependency resides in the application directory. Image SBOMs and package inventories must supplement information about system libraries.

### 7.3. Recording Non-Sensitive Environment Configuration

Several settings affect checkpoints:

- JAVA_TOOL_OPTIONS.
- JVM flags.
- Timezone and locale.
- Library search paths.
- Memory limits.
- CPU limits.
- Mount layout.
- User ID and group ID.
- Security profile identity.

Store only names or versions of secret/config profiles, never store credential values in the manifest. Secrets should be re-resolved from a secret manager after restore if they can change.

## 8. Warm-Up Profiles Are Also Part of Lineage

A checkpoint is created after the application has warmed up. The warm-up workload affects class loading, JIT profiles, caches, and the live heap. Therefore, record how warm-up was performed.

Record:

- Warm-up profile ID and version.
- List of scenarios or endpoints executed.
- Iteration counts and concurrency.
- Dataset version or test tenant.
- Warm-up duration.
- Warm-up completion criteria.
- Cache policy and cache generation.
- Post-warm-up verification results.
- Script or test harness version.

### 8.1. Warm-Up Profiles Must Be Versioned

Do not write only "warm-up completed". Two checkpoints of the same release may be created with different workloads and exhibit different post-restore performance.

Example:

| Profile | Contents |
|---|---|
| warmup-v1 | Initialize framework and health endpoint |
| warmup-v2 | Add common read endpoints |
| warmup-v3 | Add serializers and critical caches |
| warmup-v4 | Representative workload matching new traffic profile |

If the profile changes, create a new checkpoint and explicitly record the version.

### 8.2. Warm-Up Must Be Explainable and Reproducible

Store scripts, test harnesses, or scenario definitions in source control. If warm-up uses data, store the dataset version or input digest, not necessarily sensitive data.

When investigating post-restore latency, you can look up which profile created the checkpoint and know which code paths ran before checkpointing.

## 9. Checkpoint Manifest

A checkpoint manifest is a document describing the identity and creation conditions of a specific checkpoint. It links source, build, image, JDK, native runtime, warm-up, and the checkpoint artifact.

YAML example:

~~~yaml
schemaVersion: 1

release:
  id: "orders-api-2026.11.13.2"
  application: "orders-api"
  source:
    repository: "https://git.example.com/platform/orders-api"
    commit: "a1b2c3d4e5f6..."
    tree: "f1e2d3c4b5a6..."
    clean: true
    tag: "v2026.11.13.2"

build:
  id: "ci-84721-attempt-1"
  builderImage: "registry.example.com/builders/java@sha256:..."
  tool: "Gradle"
  toolVersion: "8.x"
  buildJdk: "vendor-version-build"
  dependencyLockDigest: "sha256:..."
  artifact:
    path: "orders-api.jar"
    sha256: "..."
  sbom:
    format: "CycloneDX"
    digest: "sha256:..."
  provenance:
    format: "in-toto"
    digest: "sha256:..."

container:
  image: "registry.example.com/orders-api@sha256:..."
  baseImage: "registry.example.com/jdk-crac@sha256:..."
  architecture: "amd64"

runtime:
  jdkVendor: "Exact vendor"
  javaRuntimeVersion: "Exact version and build"
  vmVersion: "Exact VM build"
  cracSupport: "Exact CRaC build"
  jvmFlagsDigest: "sha256:..."
  libc: "glibc exact package version"
  nativeLibraries:
    - name: "libexample.so"
      version: "1.8.2"
      sha256: "..."
    - name: "libssl.so"
      version: "exact-package-version"
      sha256: "..."

warmup:
  profile: "warmup-v4"
  scenarioDigest: "sha256:..."
  datasetVersion: "catalog-fixture-v12"
  durationSeconds: 75
  completed: true

checkpoint:
  id: "orders-api-2026.11.13.2-x86-poola-warm4-001"
  createdAt: "2026-11-13T08:30:00Z"
  files:
    - path: "checkpoint.img"
      sha256: "..."
    - path: "pages-1.img"
      sha256: "..."
  totalBytes: 123456789
  signature:
    artifact: "checkpoint-manifest.sig"
    identity: "release-ci"

platform:
  os: "Linux"
  architecture: "x86_64"
  kernelRelease: "exact-kernel-release"
  criuVersion: "exact-version"
  containerRuntime: "containerd exact-version"
  cgroupMode: "v2"
  cpuBaseline: "x86-64-v2"
  nodePoolProfile: "crac-linux-x86-pool-a"

restoreConstraints:
  allowedImageDigest: "sha256:..."
  allowedJdkBuild: "Exact version and build"
  allowedArchitecture: "x86_64"
  allowedNodePoolProfiles:
    - "crac-linux-x86-pool-a"
  requiresResourceReinitialization: true
~~~

Values are placeholders. Real manifests must be generated by CI/CD and the checkpoint job. Do not fill values manually if the pipeline can collect them automatically.

### 9.1. The Manifest Must Accurately Describe Checkpoint Files

A checkpoint can consist of multiple files. Store relative paths, sizes, and SHA-256 of each file, plus total size. If the tooling packages checkpoints into an archive, store the archive digest and pre-packaging file digests if needed.

Do not record only the checksum of one primary file if the image also contains other memory page files or metadata.

### 9.2. Do Not Embed Secrets in the Manifest

A manifest may be shared more broadly than a checkpoint. Store only secret references, version IDs, or provider paths if needed for traceability. Do not write passwords, tokens, private keys, or credential contents.

A checkpoint may contain a sensitive heap and objects. Read permissions on artifacts, manifests, and signatures must be managed under the same release-artifact protection policy.

## 10. Checkpoints Are Not Necessarily Reproducible Like JARs

A Java build can target reproducible builds: identical source, dependencies, and toolchain produce identical artifacts. Checkpoints are usually hard to reproduce byte-for-byte because they contain runtime state that varies over time.

Factors that can make checkpoints differ:

- Timestamps and runtime metadata.
- JIT compilation timing.
- Heap layout and object allocations.
- Thread state.
- Random state.
- Cache contents.
- File descriptors and resource state.
- Host-specific mappings.
- Warm-up execution order.

Thus, distinguish:

- **Reproducible application build:** ability to recreate a JAR/image with identical content from identical inputs.
- **Repeatable checkpoint procedure:** ability to repeat the image creation workflow with the same described profile and conditions.
- **Checkpoint byte reproducibility:** two image creations yielding identical digests; should not be assumed achievable.

Even when checkpoint digests differ, lineage can still prove both images were created from the same release and runtime profile.

### 10.1. Compare Inputs Instead of Expecting Byte-for-Byte Identical Checkpoints

When regenerating a checkpoint, compare:

- Source commit.
- JAR and image digests.
- JDK build.
- JVM flags.
- Native dependencies.
- Warm-up profile.
- Kernel/CRIU/CPU profile.
- Restore test results.

If inputs are compatible yet checkpoint digests differ, that does not automatically prove an error. Check restore behavior, smoke tests, and performance baselines.

## 11. Generating Provenance and Signing Artifacts

Checksums detect content modifications if the original checksum is trusted. Digital signatures and attestations verify who published an artifact and which provenance the artifact is bound to.

A workflow can include:

1. CI builds the JAR and container image.
2. Generate SBOM and build provenance.
3. Sign the image or artifact digest.
4. Create a checkpoint from the verified image.
5. Generate the checkpoint manifest.
6. Compute digests for the entire checkpoint.
7. Sign the manifest or attestation containing the checkpoint digest.
8. Store artifacts and metadata in controlled registries/storage.

Container/artifact signing tools such as Cosign or an internal signing system can be used. Integration depends on the registry and organizational policy.

### 11.1. Signing the Manifest and Linking to Checkpoint Digests

A signature on a manifest alone is meaningful when the manifest contains the artifact digests. When verifying, the system must:

- Verify the manifest signature.
- Read the file list in the manifest.
- Recompute digests of each file or archive.
- Compare actual digests against signed digests.
- Confirm the release ID and image digest match.

Signing only filenames without binding contents via digests allows files to be altered while names stay unchanged.

### 11.2. Checkpoint Attestation

A checkpoint can be treated as a separate artifact with a subject digest. Attestation should reference:

- Checkpoint digest.
- Checkpoint manifest digest.
- Source commit.
- Application image digest.
- JDK build.
- Builder identity.
- Restore test evidence.

Thus, the system can verify which release and which pipeline created a specific checkpoint.

### 11.3. Controlling CI Identity

Provenance is trustworthy only when builder identity is authenticated. Use verifiable CI identities, least-privilege publishing permissions, and tamper-evident logs.

Do not use shared signing credentials stored in the repository. Prefer workload identities, key management services, or managed signing services.

## 12. Examples of Checking Digests and Signatures

For a single artifact file:

~~~bash
sha256sum orders-api.jar
sha256sum checkpoint-manifest.yml
~~~

For OCI images, retrieve the digest from the registry after pushing and store the returned digest. Do not record only the tag used during the build.

Example image signing/verification commands with Cosign (syntax and authentication method depend on version, registry, and organizational policy):

~~~bash
cosign sign registry.example.com/orders-api@sha256:<image-digest>
cosign verify registry.example.com/orders-api@sha256:<image-digest>
~~~

For a checkpoint manifest, you can sign the manifest file itself or create an attestation referencing the checkpoint subject digest. Use an appropriate signing policy and store public verification identities alongside metadata.

Do not sign a checkpoint before all files have finished writing and digests have been computed. If an artifact changes after signing, generate a new manifest and signature.

## 13. Embedding Release Identity Into the Running Application

Build information can be packaged into a resource inside the JAR so the application can self-report its release identity. Example build-info.properties resource:

~~~properties
application.name=orders-api
application.version=2026.11.13.2
source.commit=a1b2c3d4e5f6
build.id=ci-84721-attempt-1
artifact.sha256=...
image.digest=sha256:...
warmup.profile=warmup-v4
~~~

These values should be generated automatically in CI. Do not edit manually after build because doing so alters the artifact and breaks digest matching.

### 13.1. Reading Build Identity in Java

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class BuildIdentity {

    private final Properties properties = new Properties();

    public BuildIdentity() throws IOException {
        try (InputStream input =
                BuildIdentity.class.getResourceAsStream(
                    "/build-info.properties")) {

            if (input == null) {
                throw new IllegalStateException(
                    "build-info.properties is missing"
                );
            }

            properties.load(input);
        }
    }

    public String get(String key) {
        return properties.getProperty(key, "unknown");
    }

    public String releaseId() {
        return get("application.version");
    }

    public String sourceCommit() {
        return get("source.commit");
    }

    public String buildId() {
        return get("build.id");
    }
}
~~~

Safe fields can be exposed via internal endpoints or logged at startup. Do not expose full JVM flags, environment variables, or secrets to public endpoints.

### 13.2. Supplementary Runtime Identity

Build identity tells where the application was built from. Runtime identity tells which platform the process is running on.

Additionally record:

- java.vendor.
- java.runtime.version.
- java.vm.name.
- java.vm.version.
- os.name.
- os.version.
- os.arch.
- Container image digest injected from deployment metadata.
- Checkpoint ID injected or mounted by the restore controller.

Build identity and runtime identity should be displayed separately to detect cases where the JAR is right yet the JDK or checkpoint is wrong.

## 14. Tracing Checkpoints in CI/CD

A pipeline can be split into stages:

~~~mermaid
flowchart TD
    A["Checkout immutable Git commit"] --> B["Verify clean tree and submodules"]
    B --> C["Resolve locked dependencies"]
    C --> D["Build and test JAR"]
    D --> E["Generate SBOM and build provenance"]
    E --> F["Build OCI image with exact JDK"]
    F --> G["Sign image and publish digest"]
    G --> H["Run CRaC warm-up job"]
    H --> I["Create checkpoint"]
    I --> J["Generate checkpoint manifest"]
    J --> K["Hash and sign checkpoint"]
    K --> L["Restore validation"]
    L --> M{"Restore tests pass?"}
    M -->|No| N["Reject checkpoint artifact"]
    M -->|Yes| O["Promote checkpoint to release channel"]
~~~

### 14.1. Build Stage

- Checkout immutable commit.
- Confirm clean source tree.
- Resolve dependencies from lockfile.
- Build and run tests.
- Compute JAR digest.
- Generate SBOM and build provenance.

### 14.2. Image Stage

- Use JDK/base image pinned by digest.
- Install native packages with fixed versions.
- Package digest-checked JAR.
- Build OCI image.
- Capture image digest after push.
- Sign image and store image SBOM.

### 14.3. Checkpoint Stage

- Run container with the exact image digest.
- Record runtime identity.
- Run the versioned warm-up profile.
- Stop or reinitialize resources according to the CRaC lifecycle.
- Create checkpoint.
- Compute file digests.
- Generate manifest.
- Sign manifest/attestation.

### 14.4. Restore validation stage

- Select compatible node pool.
- Verify image/JDK/manifest.
- Restore checkpoint.
- Run smoke tests.
- Confirm dependencies and readiness.
- Record restore duration, time to ready, and first response.
- Promote the artifact only when release criteria are met.

## 15. Promotion Between Environments

Do not copy a checkpoint across environments based solely on the release name. Each environment must check restore conditions.

A promotion flow might be:

| Environment | Activity | Advancement criteria |
|---|---|---|
| Build | Create JAR and image | Tests, SBOM, provenance, and signature succeed |
| Checkpoint factory | Warm-up and image creation | Complete manifest, valid digests |
| Validation pool | Trial restore | Smoke tests and compatibility pass |
| Staging | Restore under near-production workload | Readiness and performance meet targets |
| Production canary | Restore a small subset | Error rate and dependency load stable |
| Production rollout | Expand in batches | Within operational thresholds |

### 15.1. Do Not Promote a Checkpoint Not Yet Trial-Restored

Creating a checkpoint successfully does not prove that restore will succeed on the target node pool. At least one restore validation in a compatible environment is required, storing the result alongside the checkpoint ID.

### 15.2. Each Environment May Need Its Own Checkpoint Profile

If staging and production use different CPU baselines, kernels, or native runtimes, separate checkpoints may be needed for each compatibility group. Do not alter metadata to make a checkpoint appear suitable for another environment.

### 15.3. Store Validation Results

Validation results should contain:

- Checkpoint ID and digest.
- Node pool profile.
- JDK and CRIU versions.
- Restore result.
- Application smoke test result.
- Dependency readiness.
- Time to ready.
- First-request latency.
- Test run ID and timestamp.
- Approving person or pipeline.

## 16. Tracing in the Kubernetes Runtime

When a Pod runs, it is necessary to know exactly which release and checkpoint it is using. Non-sensitive metadata can be placed into Pod labels, annotations, and environment variables.

Example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
    release-id: orders-api-2026-11-13-2
spec:
  replicas: 4
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        release-id: orders-api-2026-11-13-2
      annotations:
        release.source-commit: "a1b2c3d4e5f6"
        release.image-digest: "sha256:..."
        release.checkpoint-id: "orders-api-2026.11.13.2-x86-poola-warm4-001"
        release.jdk-build: "exact-jdk-build"
        release.warmup-profile: "warmup-v4"
    spec:
      containers:
        - name: app
          image: registry.example.com/orders-api@sha256:<image-digest>
          env:
            - name: RELEASE_ID
              value: "orders-api-2026.11.13.2"
            - name: SOURCE_COMMIT
              value: "a1b2c3d4e5f6"
            - name: CHECKPOINT_ID
              value: "orders-api-2026.11.13.2-x86-poola-warm4-001"
~~~

Values in the example are placeholders. Kubernetes labels have format and length limits; digests or long metadata are better suited for annotations or an external release record.

### 16.1. Attach Pod UID and Restore Attempt

One checkpoint can be restored by multiple Pods. Therefore, logs need to distinguish:

- Release ID: the release.
- Checkpoint ID: the restored artifact.
- Pod UID: the specific instance.
- Restore attempt ID: the instance's restore attempt.
- Node name/pool: the restore environment.

Do not use the checkpoint ID as the unique identifier of an instance because multiple Pods may share one checkpoint.

### 16.2. Structured Logging

A log event might look like:

~~~json
{
  "event": "application_ready",
  "releaseId": "orders-api-2026.11.13.2",
  "sourceCommit": "a1b2c3d4e5f6",
  "imageDigest": "sha256:...",
  "jdkBuild": "exact-jdk-build",
  "checkpointId": "orders-api-2026.11.13.2-x86-poola-warm4-001",
  "restoreAttemptId": "restore-02",
  "podUid": "pod-uid",
  "nodePool": "crac-linux-x86-pool-a"
}
~~~

These fields help query logs by release or checkpoint when investigating incidents. Do not include secrets, tokens, or credentials in logs.

## 17. Matching Runtime Against the Manifest Before Serving

Upon restore, the application or startup coordinator can check a set of mandatory conditions:

- Release ID matches the manifest.
- Application image digest matches.
- JDK build is in the allowed list.
- CPU architecture is compatible.
- Node pool profile is accepted.
- Checkpoint digest has been verified.
- Resources requiring reinitialization have been created.
- Warm-up profile matches the release.

Some checks should be performed by the deployment controller before the process restores; others can run during startup or afterRestore. Do not wait until real requests fail to discover an incorrect image or checkpoint.

### 17.1. Compatibility Policy

The policy can be described using a versioned file:

~~~yaml
compatibilityPolicy:
  application: "orders-api"
  releaseId: "orders-api-2026.11.13.2"
  checkpointId: "orders-api-2026.11.13.2-x86-poola-warm4-001"
  required:
    imageDigest: "sha256:..."
    jdkBuild: "exact-jdk-build"
    architecture: "x86_64"
    nodePoolProfile:
      - "crac-linux-x86-pool-a"
    criuVersionRange: "validated-range"
  resourceChecks:
    database: required
    redis: required
    messageBroker: optional
~~~

This is an illustrative policy. CRIU or kernel version ranges should only be permitted when test evidence exists. Avoid using overly broad ranges without a compatibility matrix.

### 17.2. Fail Closed on Mandatory Mismatches

If the checkpoint digest does not match or the JDK/architecture falls outside the policy, do not proceed with restore as if nothing were wrong. Reject the artifact or switch to cold start via a pre-designed and pre-tested fallback.

Cold-start fallback can be useful when the checkpoint is unsuitable yet the application image remains valid. However, the startup mode must be recorded so metrics and logs do not mix cold starts with restores.

## 18. Managing Multiple Checkpoints and Rollbacks

One release can produce multiple checkpoints. A registry or catalog storing metadata is needed to select the right image.

Catalog information should include:

- Release ID.
- Source commit.
- Application image digest.
- JDK build.
- Checkpoint ID.
- Checkpoint digest.
- Warm-up profile.
- Platform compatibility profile.
- Validation status.
- Created time.
- Signature/attestation reference.
- Retention state.

### 18.1. Do Not Overwrite Released Checkpoints

Promoted checkpoints should be immutable. If recreating a checkpoint, assign a new ID. Do not overwrite the old file under the same name because Pods or rollback workflows may be referencing that artifact.

### 18.2. Rollback Must Select the Matching Image and Checkpoint Pair

If rolling back to a previous release, roll back all of:

- Application image.
- JDK/base image.
- Checkpoint created from the corresponding image/JDK.
- Runtime configuration profile.
- Warm-up profile.
- Compatibility policy.

Do not use a checkpoint from a new release with an old image just because both releases share the same application name.

### 18.3. Retention and Garbage Collection

Checkpoints are often large. Retention can be configured based on release and promotion status:

- Retain the current production checkpoint.
- Retain several verified previous releases.
- Retain checkpoints currently referenced by Pods.
- Delete expired artifacts once no deployment or rollback policy references them.

Before deleting, check the catalog and deployment references. Do not delete checkpoints based solely on file age.

## 19. Supply Chain Security and Checkpoints

A checkpoint may contain the heap, objects, and runtime state. If the application holds tokens, credentials, sessions, or user data in memory, the checkpoint may contain that information.

Protection is needed for:

- Checkpoint files.
- Checkpoint manifest.
- SBOM and provenance.
- Signing keys or signing identities.
- CI logs and build artifacts.
- Registry/storage access.
- Restore node and temporary extraction directory.

### 19.1. Least-Privilege Access

Only authorized pipelines and workloads should read checkpoints. Users do not need direct access to memory images to operate the application.

### 19.2. Encryption at Rest and in Transit

Use encrypted storage and transport, managing keys per organizational policy. Upon restore, ensure artifacts are verified before entering the runtime.

### 19.3. Do Not Leave Secrets in Build Provenance

Provenance may be stored long-term and shared across many systems. Record only variable names, secret references, or version IDs. Do not record secret values, tokens, or private keys.

### 19.4. Signatures Do Not Replace Access Control

A checkpoint with a valid signature can still contain sensitive data. A signature verifies integrity and publisher identity per trust policy; it does not grant permission to read or decrypt the artifact.

## 20. Investigating Incidents Using Release Lineage

When a Pod fails to restore, start from the Pod UID and checkpoint ID, then trace backward through the catalog.

An investigation sequence:

1. Identify Pod UID, node, and restore attempt.
2. Retrieve release ID and checkpoint ID from logs/annotations.
3. Read the checkpoint manifest.
4. Verify checkpoint digest and signature.
5. Compare image digest against Pod spec.
6. Compare JDK build and JVM flags.
7. Check node pool, kernel, CRIU, and CPU baseline.
8. Check warm-up profile and runtime configuration.
9. Read restore logs and CRIU logs.
10. Compare with the checkpoint validation record.
11. Identify the first discrepancy in the lineage.

If the checkpoint digest is valid and the image and JDK match, yet restore fails only on one node pool, focus on kernel/CRIU/CPU/runtime differences. If all nodes fail after a new source release, inspect the build and application resource lifecycle.

### 20.1. Distinguishing Artifact Errors from Environment Errors

| Symptom | First link to check |
|---|---|
| Checksum mismatch | Storage, transfer, or artifact mutation |
| Invalid signature | Signing identity, manifest, or trust policy |
| Wrong source commit | CI checkout and release metadata |
| JAR digest mismatch | Build output or packaging |
| Incorrect JDK build | Base image digest and runtime selection |
| Native library missing symbol | Image packages/ABI |
| Restore fails only on one pool | Kernel, CRIU, CPU, namespace |
| Restore succeeds yet readiness fails | Resource reinitialization and dependencies |
| Slow first request | Warm-up profile, cache, and JIT |
| Rollback uses wrong checkpoint | Catalog mapping and deployment reference |

## 21. Example of Querying Release Identity in the Application

An internal endpoint can return non-sensitive metadata:

~~~json
{
  "application": "orders-api",
  "releaseId": "orders-api-2026.11.13.2",
  "sourceCommit": "a1b2c3d4e5f6",
  "buildId": "ci-84721-attempt-1",
  "jdkVendor": "Example Vendor",
  "javaRuntimeVersion": "exact-version",
  "checkpointId": "orders-api-2026.11.13.2-x86-poola-warm4-001",
  "warmupProfile": "warmup-v4",
  "startupMode": "crac-restore"
}
~~~

This endpoint is useful for support and deployment verification. It can be protected by an internal network or authentication if metadata should not be public. Do not return the JVM command line or environment dump because they may contain secrets.

### 21.1. Recording Startup Mode

An application can run along two paths:

- cold-start
- crac-restore

Recording startup mode helps group metrics. If a Pod falls back to cold start due to an unsuitable checkpoint, the observability system must reflect that instead of recording it as a successful restore.

## 22. Checklist for Tracing from Source to Checkpoint

### Source and Build

- [ ] Repository identity and commit SHA are recorded.
- [ ] Clean source tree or patches explicitly recorded.
- [ ] Submodule/LFS identity recorded if present.
- [ ] Build tool, build JDK, and builder image digest are recorded.
- [ ] Dependency lock and verification metadata are saved.
- [ ] JAR digest is computed after build.
- [ ] Test results linked to build ID.

### Image and Runtime

- [ ] OCI image is referenced by digest.
- [ ] Base image and JDK distribution/build are recorded.
- [ ] JVM flags and GC/compiler configuration are saved.
- [ ] libc, OpenSSL, and native dependencies are inventoried.
- [ ] Application and image SBOMs are generated.
- [ ] Build provenance is published and verified.

### Warm-up and Checkpoint

- [ ] Warm-up profile has an ID/version.
- [ ] Scenarios and dataset version are recorded.
- [ ] Checkpoint has a distinct ID.
- [ ] Manifest links checkpoint with source, image, and JDK.
- [ ] Every checkpoint file has a digest.
- [ ] Manifest or checkpoint attestation is signed.
- [ ] Checkpoint artifact is stored immutably with access control.

### Restore and Promotion

- [ ] Node pool/kernel/CRIU/CPU profile is recorded.
- [ ] Restore environment is matched against the manifest.
- [ ] Signature and digest are verified before restore.
- [ ] Restore validation and smoke tests have run.
- [ ] Validation results are linked to the checkpoint ID.
- [ ] Deployment records release ID, image digest, and checkpoint ID.
- [ ] Rollback selects the matching image/checkpoint pair.

### Security and Operations

- [ ] Checkpoint is protected as an artifact that may contain secrets in memory.
- [ ] Manifest does not contain credentials.
- [ ] Signing identity is managed securely.
- [ ] Logs include Pod UID and restore attempt ID.
- [ ] Startup mode is recorded.
- [ ] Retention does not delete checkpoints still referenced.

## 23. Frequently Asked Questions

### Is storing only the Git commit SHA sufficient to trace a checkpoint?

No. A commit SHA identifies the source, yet does not identify the build toolchain, dependencies, JDK, image, native libraries, warm-up profile, or image-creation environment. All of those components must be linked in the provenance and checkpoint manifest.

### Why store the JDK build if the Java major version is already stored?

The same major version can have different vendors, builds, CRaC patches, and native runtimes. Checkpoints depend more heavily on the specific runtime than normal Java bytecode does. Store the vendor, full version/build, and image digest.

### Can a checkpoint be used for every image of the same release?

Do not assume so. Images may differ in JDK, native packages, filesystem, or runtime configuration. Use a checkpoint only with images/runtimes confirmed compatible in the manifest and restore validation.

### Is an SBOM needed for a checkpoint?

An SBOM typically describes software in the application artifact and container image. A checkpoint additionally needs a manifest describing runtime state and platform. Link the image's SBOM/provenance into the checkpoint manifest.

### Must two checkpoints from the same commit be identical?

Not necessarily. Warm-up timing, heap layout, JIT state, cache content, and host state may differ. Track each checkpoint by its own ID and digest; do not assume checkpoints are byte-for-byte reproducible.

### Can only the image tag be stored instead of the digest?

No. Tags can be updated to point to a different image. Digests identify specific image content and are appropriate for verification during restore.

### How can you tell which checkpoint a Pod is using?

Attach the checkpoint ID, release ID, and image digest to Pod annotations or environment metadata, then record those values in structured logs. Combine Pod UID and restore attempt ID to distinguish instances sharing the same checkpoint.

### Must a new checkpoint be created when upgrading the JDK?

A new checkpoint should be created and tested with the new JDK build. Do not attach an old checkpoint to a new runtime without compatibility evidence from documentation and restore validation.

### Does the checkpoint itself need to be signed?

A mechanism to verify integrity and publisher origin is needed. You can sign the manifest or an attestation containing digests of all checkpoint files. Upon restore, verify the signature and recompute digests before use.

### Should secrets be stored in the checkpoint manifest for easier tracing?

No. Store only secret references or version IDs. Both checkpoints and manifests need protection because checkpoints may hold secrets on the heap, whereas manifests should avoid storing credential values.

### If a checkpoint is incompatible with a node, can it fall back to cold start?

Yes, if the deployment is designed and tested for that fallback. Clearly record the startup mode, reason for rejecting the checkpoint, and separate metrics. Do not record a cold start as a successful CRaC restore.

## Conclusion

CRaC release traceability needs to run end-to-end from source commit to build toolchain, JAR, OCI image, JDK/CRaC build, native dependencies, warm-up profile, and checkpoint artifact. Each layer needs an immutable identifier, digest, and provenance so relationships among components can be verified.

Generate checkpoint manifests automatically, sign or attest manifests along with digests of the entire image, store SBOMs and build provenance, record release/checkpoint identity in Pods and logs, and verify the restore environment before opening readiness. With complete lineage, the development team can determine accurately where a checkpoint came from, which runtime it runs on, which environments it was tested in, and which artifact to select when deploying or rolling back.
