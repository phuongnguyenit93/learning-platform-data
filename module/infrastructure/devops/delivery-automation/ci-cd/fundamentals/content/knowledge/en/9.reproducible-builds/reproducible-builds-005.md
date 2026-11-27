# Identifying Inputs to Pin and Metadata to Record

## 1. What Are Reproducible Builds and Why Do They Matter?

A build consumes source code, dependencies, tools, configuration, and an execution environment to produce an artifact. If the same commit is built at two different times yet outputs differ because of an uncontrolled library version, compiler, base image, or environment value, the team cannot accurately explain what produced the artifact.

Reproducible builds aim to recreate the exact same artifact from the exact same source code and declared set of inputs. Under the strict definition, two independent builds yield byte-for-byte identical outputs, comparable via a checksum such as SHA-256. In some systems, "repeatable build" is used in a broader sense: the same inputs produce functionally equivalent results, even if output files differ in metadata or timestamps. When addressing byte-level reproducible builds, even seemingly harmless differences inside the build package must be eliminated.

Reproducibility delivers direct value to CI/CD:

- **Traceability:** identify the exact commit, dependencies, and toolchain behind an artifact.
- **Incident investigation:** rebuild an older revision to inspect bugs or verify patches.
- **Supply chain trust:** detect unexpected output modifications or build tampering.
- **Auditing:** supply evidence of artifact origin and build processes.
- **Consistent releases:** test one artifact and promote that exact same artifact across environments.
- **Reduced local-environment dependence:** avoid situations where a developer machine builds cleanly yet CI runners emit different outputs.

Input pinning and metadata recording (provenance) complement each other. Input pinning ensures the build uses the exact chosen versions. Metadata recording documents what the build actually used and produced. Recording only "JDK 21" without knowing the distribution, patch level, and image containing that JDK may be insufficient for exact reproduction.

## 2. Distinguishing Pinned Inputs from Provenance Data

These two concepts are often conflated, yet serve different purposes:

| Concept | Question Answered | Example |
|---|---|---|
| Pinned inputs | Which exact components is the build permitted to use? | Commit SHA, lockfile, JDK version, compiler version, image digest |
| Provenance data | Which inputs and conditions did the build actually run with? | Run ID, actual commit, builder image digest, build command, artifact SHA-256 |
| Verification results | What evidence shows the output meets requirements? | Test reports, dual-build comparison checksum, signature/attestation |

For example, a configuration file declaring image `builder:21` does not necessarily pin the environment because that tag can be updated. Provenance recording the actual image digest shows which image the build actually ran on. Similarly, a lockfile represents locked dependencies; build metadata should record the actually resolved dependencies and their sources where tooling supports it.

Not every observable value needs to become a fixed input. Run ID and execution time change per build, yet still must be recorded. Conversely, the compiler version can directly affect bytecode and must be pinned. Distinguish values fixed for reproducibility from values recorded for traceability.

## 3. Cataloging Inputs That Affect the Build

Before pinning, list everything capable of altering outputs. A practical catalog can be grouped as follows:

| Input Category | Values to Examine | How to Pin or Control |
|---|---|---|
| Source code | Commits, submodules, Git LFS objects, generated sources | Commit SHA; record submodule revisions and object IDs |
| Dependencies | Direct/transitive libraries, packages, plugins | Lockfiles, explicit versions, checksums/signatures, trusted repositories |
| Toolchain | Compiler, JDK, runtime, linker, package manager, build tool | Explicit versions, checksummed wrappers, immutable images or packages |
| Builder image | Base image, OS packages, pre-installed tools | Image digest, snapshot repository, or version-managed images |
| Execution platform | OS, CPU architecture, libc, kernel, or runner | Record versions; fix attributes that influence output |
| Build configuration | Build flags, profiles, feature flags, parameters, env vars | Store in version control or record explicitly in invocation metadata |
| Code generation inputs | Schemas, API definitions, generator compilers/plugins, assets | Pin revisions and generator tool versions |
| External resources | Package repositories, binary download URLs, network data | Mirrors/snapshots, checksums, allowlisted sources, or offline mode |
| Time and randomness | Timestamps, timezone, random seeds, file ordering | Normalize timestamps, seeds, and sorting algorithms where applicable |
| Packaging | Archiver version, entry ordering, file metadata | Pin tools, normalize metadata and package structure |

Not every project needs to pin every attribute down to the OS or hardware level. Identify which attributes genuinely affect outputs and match your target reproducibility level. For example, a pure Java application may not need exact kernel details pinned to reproduce a JAR, whereas a native compiled project can depend heavily on compiler, linker, libc, and CPU architecture.

## 4. Pinning Source Code with Immutable Revisions

Avoid using branch names like `main`, `develop`, or movable tags as the sole identifier for built source code. Branches advance over time. A tag can be deleted and recreated if the repository does not enforce tag immutability.

Recommended practices:

- Record the full commit SHA of the checked-out revision.
- Store the repository URL or identifier along with checkout state.
- Record submodule commits per path if the project uses Git submodules.
- Record object IDs for Git LFS or externally fetched source data.
- For source archives, store the archive checksum and release origin.
- Avoid undocumented manual source edits after checkout.
- If a build applies patches in the pipeline, keep patches in version control or record retrievable checksums and content references.

Example metadata:

```yaml
source:
  repository: https://example.com/platform/order-service.git
  revision: 8d3f2a1c...full-commit-sha
  submodules:
    shared-contracts: 4b71e9...
```

This YAML is illustrative; SHA values and URLs must be replaced with real data. For pull requests, clarify whether the build checks the source branch commit, a temporary merge commit, or the merged revision. Record the actual revision checked out by the runner, not just the pull request number.

## 5. Pinning Direct and Transitive Dependencies

Dependencies are not limited to directly declared libraries. Build tools may fetch transitive dependencies, plugins, compiler extensions, or system packages. If only direct dependencies are pinned, a transitive dependency update can alter outputs.

Key principles:

1. Use lockfiles or dependency locking mechanisms to record resolved versions, including transitive dependencies where supported.
2. Avoid dynamic versions such as `latest`, `1.+`, `^1.2`, or version ranges when fixed inputs are required. Some ecosystems use ranges for compatibility management, yet resolution results must be locked before release builds.
3. Use checksums or signatures to verify downloaded packages match approved contents.
4. Control which repositories/mirrors are permitted to supply dependencies; avoid fetching identical package coordinates from unknown sources.
5. Pin build plugins and code-generation plugins just like application dependencies.
6. Store lockfiles in version control and review dependency updates like code changes.
7. Maintain an intentional workflow for updating lockfiles, running tests, and releasing updates.

With Gradle, projects can use dependency locking and dependency verification. Conceptual configuration example:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Locking records dependency resolution results for project configurations; dependency verification checks artifact checksums or signatures against trusted metadata. Projects must generate and review lock state and verification metadata per Gradle's guidance. Adding the snippet above alone does not automatically generate complete lockfiles for every configuration.

With Maven, declare explicit versions for dependencies and plugins, avoid version ranges in release builds, and control repositories. Maven does not provide a built-in universal lockfile for the entire dependency graph across every project; supplementary tooling or processes may be needed to persist resolution results and verify checksums.

## 6. Pinning Build Tools and Toolchains

Build tools and toolchains directly influence bytecode, native binaries, archives, and metadata. Explicitly define:

- JDK/runtime version used to run the build tool.
- Compiler version and target/release level.
- Gradle/Maven or corresponding build tool version.
- Plugin, annotation processor, code generator, and linker versions.
- Package manager version and dependency resolution rules.
- Packaging, compression, signing, or metadata generation tools.

With Gradle, the Gradle Wrapper lets the repository specify the Gradle version. `gradle-wrapper.properties` can declare the distribution URL and checksum:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=<expected-sha256>
```

The checksum is a placeholder in this example; obtain it from a trusted release source and verify it before use. The wrapper does not automatically pin the JDK running Gradle; manage the JDK separately via toolchains or pinned runner images.

Example Dockerfile illustrating pinning a base image by digest:

```dockerfile
FROM eclipse-temurin:21-jdk@sha256:<image-digest>
WORKDIR /workspace
```

The `21-jdk` tag helps humans read the intended version; the digest identifies the exact image contents. Update digests deliberately when applying security patches or system upgrades.

## 7. Pinning the Builder Environment and Execution Platform

Two builds of the same source code can differ when run on different runner images. A newer image can include different versions of the shell, libc, CA certificates, system packages, or compression tools.

Manage the following:

- Builder image by digest or immutable release.
- CPU architecture (e.g., x86_64/ARM64) if it affects binaries.
- OS version and required system packages.
- Runtimes and native libraries used during the build.
- Locale, timezone, encoding, and umask settings.
- Build paths if the compiler embeds absolute paths into debug information.
- Network configuration, proxies, and package repository sources.

Pinning the entire runner image by digest stabilizes the environment, yet images still need updates when security patches arrive. Never hold onto an outdated image indefinitely solely for reproducibility. Publish updated image versions, test them, and upgrade under change control; keep old digests in provenance to recreate historical builds when necessary.

For native builds, consider fixing architecture, compiler, linker, sysroot, and libc versions as well. For Java, JARs are less sensitive to the kernel yet still depend on JDK, build tool, plugins, dependencies, and packaging metadata.

## 8. Controlling Environment Variables and Build Parameters

Build scripts often read environment variables without declaring them in configuration files. Variables like `TZ`, `LANG`, `JAVA_TOOL_OPTIONS`, `PATH`, `HOME`, or feature flags can change outputs.

Recommendations:

- List environment variables that influence the build.
- Set explicit values for locale, timezone, and encoding when they affect outputs.
- Record command-line arguments and build profiles used.
- Control `PATH` so unexpected tool versions are not invoked accidentally.
- Separate regular configuration variables from secrets.
- Never write secrets, tokens, or credentials into provenance, logs, or build metadata files.
- If a build needs secrets to pull private dependencies, record the source identifier and secret version if supported—never the secret value.

Example of setting up a more deterministic environment:

```bash
export TZ=UTC
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export SOURCE_DATE_EPOCH="$COMMIT_TIMESTAMP"
./gradlew --no-daemon clean build
```

`SOURCE_DATE_EPOCH` is a convention supported by several tools to normalize output timestamps; not every build tool uses it automatically. `COMMIT_TIMESTAMP` must be derived from the identified revision and formatted as a valid epoch integer. Check each packaging tool and plugin to confirm whether it honors this variable.

Never dump the entire `env` to logs for troubleshooting. Environments often hold tokens and secrets. Use an allowlist of non-sensitive variables to record while masking or excluding sensitive values.

## 9. Eliminating Nondeterminism: Time, Randomness, and Ordering

A build can change despite unchanged source code and dependencies due to nondeterministic factors:

- Current timestamps embedded in JAR, ZIP, or manifest files.
- File ordering inside archives depending on filesystem or directory traversal order.
- Random seeds varying across runs.
- Temporary directory names or absolute paths written into debug symbols.
- Locale/timezone altering date formatting, number formatting, or string sorting.
- Parallel builds making file generation or resource merging order unstable.
- Tools pulling live data directly from the network or time-varying APIs.
- Signatures or packaging metadata embedding timestamps and session data.

Mitigations:

1. Use a fixed timestamp from the source revision or a well-defined constant instead of the current clock.
2. Sort file lists before packaging and enable deterministic archive modes where tools support them.
3. Set fixed random seeds for reproducible generation steps; never use fixed seeds where business logic requires genuine runtime randomness.
4. Normalize locale, timezone, and encoding.
5. Use compiler flags to remap or strip unstable build paths where appropriate.
6. Fetch external data through versioned, checksummed snapshots/mirrors.
7. Verify that plugins, annotation processors, and code generators emit deterministic outputs.

Not every timestamp in provenance needs to be fixed. When the pipeline executed is an observational fact that should be recorded accurately. What must be normalized is any timestamp embedded inside the artifact if it causes identical inputs to yield different bytes without carrying semantic content.

## 10. Managing External Data Sources and Offline Builds

A build might reach out to the Internet to download dependencies, schemas, binaries, or reference data. If an external source changes or becomes unavailable, older builds may no longer be reproducible.

Mitigations:

- Use an internal package registry or mirror with clear retention policies.
- Pin versions and checksums of directly downloaded binaries.
- Store snapshots of input data if that data affects artifacts.
- Record the origin, retrieval timestamp, and content identifier of external data.
- Avoid URLs pointing to continuously overwritten files or endpoints returning time-dependent data.
- For builds requiring high reproducibility, prefetch all dependencies and run the build step in a network-isolated environment.
- Retain access to packages used in historical builds according to retention policies.

Offline builds uncover undeclared dependencies or steps silently downloading assets. However, offline mode is only meaningful after all inputs are staged and verified. If a build step requires an external service to generate an artifact, record the service, data version, and returned result, or replace it with a snapshotted input.

## 11. Data to Record for Every Build

Provenance must be detailed enough to answer where an artifact came from, how it was built, and under what conditions. A useful metadata set includes:

| Category | Fields to Record | Purpose |
|---|---|---|
| Run identity | Pipeline run ID, job ID, start/end timestamps | Correlate logs and steps within the same build |
| Source code | Repository, commit SHA, branch/tag reference, checkout state | Identify the built revision |
| Dependencies | Lockfile checksum, dependency graph, or resolved package list | Know external components included in the build |
| Toolchain | JDK/compiler, build tool, plugins, package managers, and versions | Recreate the build environment |
| Builder | Runner/image digest, OS, architecture, required runtimes | Identify the execution environment |
| Invocation | Command, arguments, profiles, and non-sensitive build config | Understand how the artifact was produced |
| Environment | Allowlisted impactful variables, locale, timezone, seeds, and `SOURCE_DATE_EPOCH` if used | Explain variations across runs |
| Outputs | Artifact name, version, size, SHA-256/digest | Pinpoint exact outputs |
| Verification | Test reports, scan results, checksum comparisons, quality gates | Prove required criteria passed |
| Supply chain | SBOM, provenance attestation, signatures, and builder identity | Support origin and integrity verification |

Not every field must live inside a single file. Metadata can live in the CI system, artifact repository, or attestations linked by identifier. What matters is that data remains retrievable, protected from unauthorized modification, and retained per policy.

## 12. Build Metadata Example

A simple metadata file could be structured as follows:

```yaml
build:
  run_id: "ci-1042"
  started_at: "2026-11-18T07:00:00Z"
  source:
    repository: "https://example.com/platform/order-service.git"
    commit: "8d3f2a1c..."
  builder:
    image: "registry.example/ci/java-builder@sha256:<digest>"
    os: "linux"
    architecture: "amd64"
    jdk: "21.0.x"
    gradle: "8.10.2"
  dependencies:
    lockfile_sha256: "<sha256>"
    verification_metadata_sha256: "<sha256>"
  invocation:
    command: "./gradlew --no-daemon clean build"
    timezone: "UTC"
    locale: "C.UTF-8"
  outputs:
    - name: "order-service.jar"
      sha256: "<artifact-sha256>"
```

This is an illustrative schema, not a mandatory standard provenance format. `started_at` changes per run and should reflect reality; it is not a fixed input for reproduction. Placeholders must be replaced with actual data. Never put tokens, passwords, private keys, or secret values into this file.

For systems exchanging provenance across multiple tools, use standardized attestation formats and bind the subject to the artifact digest. An SBOM describes software components inside a product; provenance describes how the product was built. The two complement each other without replacing one another.

## 13. Verifying via Checksums and Two Independent Builds

Pinning inputs is necessary, yet does not by itself prove outputs are reproducible. Direct verification means executing two independent builds using identical declared inputs—ideally in two clean workspaces or runners—and comparing artifact checksums.

Example:

```bash
sha256sum build-a/order-service.jar
sha256sum build-b/order-service.jar
```

If both SHA-256 values match, the two files contain identical bytes with negligible collision probability under SHA-256 properties. If they differ, do not immediately assume the build failed; determine whether differences come from content or packaging metadata.

A verification workflow can run as follows:

1. Select a commit SHA and record the lockfile, toolchain, builder image digest, and build parameters.
2. Run build A in a clean workspace, upload the artifact, and record its SHA-256.
3. Run build B on an independent runner/workspace with the exact same pinned inputs.
4. Compare artifact digests.
5. If they differ, extract or use binary comparison tools to isolate differing files/entries.
6. Inspect timestamps, archive order, paths, generated files, random seeds, dependencies, and toolchains.
7. Fix sources of nondeterminism, then re-run two independent builds.
8. Save comparison results alongside provenance for future audits.

Never compare two artifacts signed with differing signature timestamps or nonces and conclude the software is non-reproducible. Compare payloads before signing, or use deterministic signing mechanisms if supported. Signatures and attestations should be stored separately and remain verifiable against the payload digest.

## 14. Linking Provenance to Artifacts and Releases

A trustworthy artifact needs a clear link back to its source code and build execution. At minimum, store:

- Artifact name and version.
- Immutable artifact digest.
- Commit SHA and source repository.
- Pipeline run ID and builder identity.
- Toolchain versions, dependency lock state, and builder image.
- Test, scan, and quality gate results.
- Provenance/attestations and signatures if required by process.

Once an artifact is built and verified, CD should promote that exact artifact through staging and production. Do not rebuild from the same commit in each environment, because differing configurations or timing can produce different contents. Environment configuration is supplied at deployment time, while the application payload retains the exact same digest.

Example: `order-service.jar` with SHA-256 `abc...` is tested in staging. When deploying to production, the system pulls the exact artifact matching that digest and records a deployment pointing to that same digest. If production runs a newly rebuilt file—even with the same name and commit—the team must treat it as a different artifact until content equivalence is proven.

## 15. Trade-Offs of Input Pinning

Pinning everything can increase maintenance effort and storage overhead. Pinning overly old versions can retain security vulnerabilities or compiler bugs. Pinning too little allows builds to drift unexpectedly.

| Decision | Benefit | Cost / Risk | How to Balance |
|---|---|---|---|
| Pin all dependencies | Stable resolution results | Requires periodic lockfile updates | Automate update proposals, review, and test before merging |
| Pin builder images by digest | Explicit environment | Must bump digests to receive patches | Schedule image updates with compatibility testing |
| Build offline | Surfaces hidden network dependencies | Requires mirrors and dependency staging | Pre-fetch/verify, then build in restricted network |
| Pin compilers and plugins | Controls bytecode/output | Delays automatic uptake of new versions | Manage toolchains like dependencies and upgrade intentionally |
| Normalize timestamps | Improves byte-level comparability | Loses real build time inside artifacts | Record real timestamps in provenance, fixed timestamps in payloads |
| Retain old builders for history | Can rebuild older releases | Increases operational cost and risk | Store image digests, mirror packages, maintain old builders only when justified |

A sound policy classifies inputs by impact and risk. Dependencies and toolchains that directly shape artifacts require tight pinning. Lower-impact attributes may only need recording. Never pin secrets by storing their values; manage them via secret managers, version identifiers, or short-lived credentials.

## 16. Common Anti-Patterns

| Anti-Pattern | Consequence | Improvement |
|---|---|---|
| Using `latest` tag for builder images | Image changes without pipeline changes | Pin digests and upgrade deliberately |
| Using dynamic dependency versions in release builds | Same commit may pull different dependencies | Lock the dependency graph and verify checksums |
| Recording only the commit SHA | Compiler, plugins, and environment remain unknown | Record provenance covering builder, toolchain, dependencies, and invocation |
| Dumping all environment variables to logs | Risks leaking secrets | Log only an allowlist of non-sensitive variables |
| Using current clock inside archives | Checksums differ for identical payloads | Normalize timestamps or exclude variable metadata |
| Building once and claiming reproducibility | No proof two builds yield identical output | Run two independent builds and compare digests |
| Relying on cache as sole dependency source | Cache loss or poisoning breaks reproducibility | Maintain lockfiles, registries/mirrors, and checksum verification |
| Rebuilding separately per environment | Staging and production artifacts may differ | Promote the same immutable artifact across environments |
| Including signatures in payload comparisons | Signature timestamps/nonces create false diffs | Compare payloads before signing and verify signatures separately |

## 17. Checklist for Defining Inputs and Metadata

Before considering a pipeline reproducible, check:

- [ ] Source revision is identified by commit SHA.
- [ ] Submodules, Git LFS, and external source data are identified.
- [ ] Direct and transitive dependencies are locked with content verification.
- [ ] Build tools, plugins, compilers, and runtimes have pinned versions.
- [ ] Builder images are pinned by digest or an equivalent immutable mechanism.
- [ ] OS, architecture, and native libraries affecting builds are recorded.
- [ ] Build flags, profiles, and relevant environment variables are explicitly declared.
- [ ] Locale, timezone, timestamps, and random seeds are controlled when affecting outputs.
- [ ] External data sources have retrievable versions/checksums or snapshots.
- [ ] Secrets are never used in provenance; sensitive values are stripped from logs.
- [ ] Metadata records run ID, commit, builder, toolchain, invocation, and artifact digest.
- [ ] Dual independent builds and checksum comparisons run when byte-level reproducibility is required.
- [ ] Verified artifacts are promoted across environments under the same digest.
- [ ] Provenance, SBOMs, test reports, and signatures are stored per retention policy.

## 18. Core Practical Principles

1. Catalog every input that can affect artifacts before designing pinning rules.
2. Pin revisions, dependencies, toolchains, builder images, and code-generation data using immutable identifiers wherever possible.
3. Lock transitive dependencies, verify checksums/signatures, and control package sources.
4. Normalize environment variables, timestamps, locale, timezone, file ordering, and random sources.
5. Record provenance covering source code, builder, invocation, environment, dependencies, and output digests.
6. Never write secrets into metadata or logs; record only non-sensitive data needed for traceability.
7. Verify reproducibility via two independent builds and digest comparison.
8. Bind provenance to artifacts and promote the exact same artifact across environments.
9. Update pinned inputs through reviewed changes, testing, and security patching workflows.

Reproducible builds do not come from a single pipeline toggle. They result from defining inputs, removing sources of variance, recording the actual execution environment, and verifying outputs. When that metadata is managed alongside artifacts, teams can explain, verify, and recreate software releases throughout the entire CI/CD lifecycle.
