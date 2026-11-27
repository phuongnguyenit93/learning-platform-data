# Distinguishing Re-Runnable Builds from Byte-for-Byte Reproducible Outputs

A team can run the exact same build command multiple times and succeed every time. However, the output files may still differ: a JAR contains a new timestamp, a container image has altered metadata, a ZIP file orders its entries differently, or a binary embeds the build machine's absolute paths. This means the build is re-runnable, yet the output is not necessarily reproducible.

In CI/CD, this distinction matters when a team needs to verify which source code produced an artifact, investigate incidents, compare builds across two runners, or prove a release package can be independently rebuilt. This lesson clarifies those two levels, identifies sources of divergence, and explains how to normalize inputs, environments, and packaging tools as well as how to verify artifacts.

## 1. Two Concepts to Distinguish

### Re-runnable builds

A re-runnable (or repeatable, as used in this lesson) build is a build that can be executed again using the same process and complete successfully. The team can run the build command today, tomorrow, or on another runner without manually editing steps.

This is valuable for automation, yet insufficient to conclude that two builds produce the exact same output. The command can succeed both times while the artifact embeds creation time, build number, workspace path, or newly downloaded dependencies.

### Byte-for-byte reproducible builds

A reproducible build requires two independent builds, using identical declared inputs and an equivalent process, to produce byte-for-byte identical outputs. For the same artifact, a cryptographic hash such as SHA-256 must yield the exact same value.

For example:

- The first build produces `app.jar` with SHA-256 `H`.
- An independent build in a clean workspace produces a second `app.jar`.
- If both files are byte-for-byte identical, their SHA-256 hashes match and a binary comparison finds zero differences.

A reproducible build does not merely mean "the command succeeded." It proves the output does not depend on variable factors outside the controlled set of inputs.

### Comparison table

| Criterion | Re-runnable Build | Byte-for-Byte Reproducible Build |
|---|---|---|
| Goal | Can re-execute the process and complete | Produces identical output contents across independent builds |
| Conditions | Command, tools, and environment are sufficient to run | Inputs, tools, environment, and artifact generation steps are controlled |
| Result | Can succeed while producing different files | Corresponding artifacts are byte-for-byte identical |
| Timestamps | May use the current time | Variable timestamps must be normalized or removed |
| Dependencies | May fetch newer versions if declared dynamically | Dependency versions and contents must be pinned and verified |
| Workspace | May depend on current machine state | Source state and intermediate data must be controlled |
| Evidence | Logs show the build command succeeded | Hashes or byte comparisons confirm identical outputs |
| Value | Keeps pipelines operating reliably | Supports origin verification, auditing, and software supply chain integrity |

In practice, terms like repeatable, reproducible, and deterministic are sometimes used differently across teams or tools. Therefore, when setting quality criteria, describe the required outcome via a concrete test: the same commit and the same set of inputs must produce the same artifact digest.

## 2. Determinism and Reproducibility

A processing step is deterministic when the same inputs and controlled state always produce the same result. For instance, a compiler can compile identical source code into identical object files if the compiler version, flags, paths, and relevant inputs stay unchanged.

However, a multi-step pipeline can contain one non-deterministic step. If even a single step injects variable data into an artifact, the entire final output can differ.

Three scopes can be distinguished:

1. **Step-level reproducibility:** each tool or task produces identical output when inputs do not change.
2. **Build-level reproducibility:** the entire process from source to artifact produces identical results.
3. **Release-level reproducibility:** published artifacts, metadata, manifests, and release outputs can be regenerated or verified according to defined rules.

A build can be reproducible at the binary level while release metadata or signatures generated in a subsequent step still vary over time. Teams should clearly specify which artifacts are compared: JARs, executables, container images, packages, manifests, or the entire release bundle.

### Example: two JAR files with identical class bytecode but different bytes

Suppose two builds produce `app.jar`:

- The `.class` files inside are identical.
- The `MANIFEST.MF` file is identical.
- Yet the timestamps on individual ZIP entries differ.

The application may behave identically at runtime, but the two JAR files are not byte-for-byte identical. Relying solely on unit tests or behavioral checks will miss this discrepancy. Comparing SHA-256 hashes yields two different values.

This illustrates the need to distinguish:

- **Functional equivalence:** the application exhibits equivalent runtime behavior.
- **Content reproducibility:** the artifact is byte-for-byte identical.

Byte-for-byte reproducibility is the stricter criterion and typically requires controlling packaging metadata, not just source code.

## 3. Sources of Divergence Between Two Builds

A build can be affected by many factors seemingly unrelated to source code. Grouping them helps identify root causes.

### Time and timestamps

Tools may embed the current time into:

- Metadata of JAR, ZIP, TAR, or package archives.
- Auto-generated files such as `version.properties` or `build-info.json`.
- Headers, manifests, or debug information.
- Container image configs and layer metadata.
- File names, directories, or build reports.

If each build reads the system clock, outputs will differ even when source code has not changed.

### Mutable dependencies and tools

Declarations such as latest versions, version ranges, or mutable tags can fetch different contents across runs. Examples include:

- Dependencies using dynamic versions like `1.+` or `latest.release`.
- Container base images using the `latest` tag.
- Build plugins without pinned versions.
- Tools downloaded directly from a URL pointing to a replaceable file.
- Git submodules not checked out to the intended commit.
- Dependencies fetched from repositories without checksums or content verification.

The same name and version do not guarantee the same content if a repository allows overwriting released artifacts.

### Operating system and toolchain

The following factors can alter outputs:

- Versions of the JDK, compiler, linker, or build tool.
- Runtime vendor and patch level.
- Operating system version and system libraries.
- CPU architecture, optimization flags, and instruction sets.
- Docker/BuildKit or packaging tool versions.
- Locale, timezone, encoding, and string collation rules.
- Umask, file permissions, owner/group, and filesystem metadata.

Recording just "Java 21" is sometimes insufficient. You need to know the exact toolchain version and components that affect bytecode or artifacts.

### Paths and workspace state

Absolute workspace paths can appear inside debug information, generated sources, manifests, or packaged logs. For instance, one build running in `/home/runner/work/project` and another in `/builds/project` can produce different binaries if the compiler embeds file paths.

A dirty workspace also introduces divergence:

- Generated files left over from a previous build.
- Untracked files accidentally bundled into the package.
- Builds picking up uncommitted source changes or a dirty working tree.
- Caches holding stale data.
- Tasks reading configuration files located outside the repository.

### Processing order and randomness

Some differences stem from how data is traversed or how tasks run in parallel:

- Filesystem directory iteration order or non-deterministic map iteration.
- Multiple tasks writing to a shared output.
- Names or element ordering generated from unordered collections.
- Undeclared random seeds.
- Auto-generated code using random numbers or UUIDs.
- Tests or code generation depending on completion timing of asynchronous threads.

### External services and data

A build might call an API, query a database, download a schema, or read information from a changing service. If those results enter the artifact, two builds can differ despite identical source code.

For example: a pipeline generates a file containing current exchange rates, feature flag lists, or responses from an external endpoint. Those values are actual build inputs and must be pinned or excluded from the artifact to achieve reproducibility.

## 4. Controlling Build Inputs

To achieve reproducibility, you must first know exactly what the build consumed. A build can be described by its input set:

- Source repository commit SHA.
- Submodule commits and Git LFS contents, if applicable.
- Dependencies and checksums.
- Compiler, runtime, build tool, and plugin versions.
- Base image or execution environment.
- Relevant build flags and environment variables.
- Configuration files, schemas, code generators, and input data.
- Packaging rules, timestamps, and metadata.

### Use immutable commits

CI should check out an explicit commit rather than building from a moving branch reference. Record the full commit SHA in build metadata. Before building, verify the working tree contains no unexpected modifications.

In single-use CI workspaces, create a fresh checkout for every build. When cleaning an old workspace, run deletion commands only within clearly scoped CI directories, never on developer working directories.

### Lock dependencies

Use version locking and content verification mechanisms:

- Gradle dependency locking to record resolved dependency versions.
- Gradle dependency verification to check checksums or signatures per configuration.
- Maven explicit versions for dependencies and plugins; manage parent POMs and BOMs cleanly.
- Node.js lockfiles such as `package-lock.json`, `pnpm-lock.yaml`, or `yarn.lock`.
- Python lock or hash-pinned constraints files where supported by tooling.
- Container base images referenced by digest when exact content identity is required.

Avoid version ranges or mutable tags in release builds. Updating a dependency should happen through a reviewed change that updates the lockfile or manifest.

### Pin build tools

For Java projects:

- Commit the Gradle Wrapper or Maven Wrapper.
- Declare explicit JDK/toolchain versions.
- Control build plugin versions.
- Record the OS or base image version.
- Do not rely on a pre-installed Gradle/Maven binary on the runner without knowing its exact version.

Wrappers select the right build tool version, yet are insufficient to lock the whole environment. JDKs, dependencies, plugins, and system libraries still require explicit control.

### Control external sources outside the repository

If a build requires schemas, binaries, submodules, or data supplied by another team, record the version or digest of each input. Avoid downloading the "latest" file mid-build without recording the exact content used.

For internal dependencies, use an artifact repository supporting immutable versions and checksums. Where supported, enable policies preventing released artifacts from being overwritten.

## 5. Normalizing the Execution Environment

Identical source and dependencies can still yield different outputs if the environment differs. Make impactful environment factors explicit.

### Pin the operating system and toolchain

Select a specific runner image or container image version. Record:

- OS image or container digest.
- JDK, compiler, and build tool versions.
- CPU architecture.
- Compression tool versions.
- Build-relevant environment variables.

Aliases like `ubuntu-latest` are convenient, yet can point to newer images over time. For builds requiring reproducibility, use explicit image versions under controlled upgrade procedures.

### Normalize locale and timezone

Locale can affect string sorting, number formatting, or date formatting. Timezone can alter generated timestamps.

A build environment commonly sets:

~~~sh
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
umask 022
~~~

This configuration reduces variations from locale, timezone, and default file permissions. Tools or plugins may still ignore some environment variables, so inspect actual outputs.

### Normalize paths

Where supported by the compiler, use source path remapping options so specific workspace paths are not embedded in debug information. For example, some compilers support prefix-map options; exact flag names and syntax depend on the compiler.

Also avoid generating files containing absolute paths, hostnames, or the executing username. If such metadata is needed for diagnostics, store it in build logs or external provenance outside the release artifact.

### Limit influence from the external environment

A hermetic build uses only declared inputs. It does not arbitrarily depend on the network, local host files, or changing services.

You can move toward hermetic builds incrementally:

1. Resolve dependencies in a preparation step and store checksums.
2. Use a controlled dependency repository or cache.
3. Run builds in an environment that needs no undeclared downloads.
4. Restrict filesystem read access outside the workspace.
5. Limit network egress for build jobs where appropriate.
6. Record actual inputs so the run can be recreated.

Hermetic builds support reproducibility, though the two concepts are not completely identical. A process might consume only declared inputs yet still embed the current timestamp; inputs appear controlled, while outputs still fail byte-for-byte reproducibility.

## 6. Eliminating Variable Timestamps and Metadata

Timestamps are one of the most common reasons archives and packages differ between two builds.

### SOURCE_DATE_EPOCH

`SOURCE_DATE_EPOCH` is an environment variable supported by many tools in the reproducible builds ecosystem. It supplies a fixed timestamp that tools use instead of the current clock when generating outputs.

Its value is usually derived from the source commit timestamp or a fixed milestone defined in the release process. Crucially, the same source revision must receive the same value across compared builds.

Conceptual example:

~~~sh
export SOURCE_DATE_EPOCH=1704067200
./gradlew --no-daemon clean build
~~~

The value above illustrates a fixed Unix timestamp. In production pipelines, derive the timestamp consistently from the commit or release metadata, then pass it uniformly to tools that honor this variable.

Not every tool reads `SOURCE_DATE_EPOCH` automatically. Check documentation for your compiler, archiver, packager, and plugins. If a plugin ignores this variable, timestamps may still vary.

### Normalizing archives

JARs and ZIPs store metadata per entry. To improve reproducibility:

- Use a deterministic entry ordering.
- Normalize entry timestamps.
- Normalize file permissions where the format supports it.
- Avoid bundling temporary or unintended generated files into archives.
- Pin compression tool versions and compression settings if they affect output bytes.

Gradle Kotlin DSL example:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

These properties instruct Gradle to produce archives with deterministic file ordering without preserving original input file timestamps. They are part of the solution; other plugins, file contents, and additional metadata still require verification.

### Maven output timestamp

With Maven, plugin versions supporting reproducible archives can use the `project.build.outputTimestamp` property. Example configuration:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

This is an illustrative fixed timestamp. In practice, supply a timestamp derived consistently from the source revision. Use plugin versions that support this property and verify other packaging plugins do not inject the current timestamp.

## 7. Controlling Code Generation and Auto-Generated Data

Code generation typically creates source or resource files from schemas, templates, API definitions, or data. If a generator uses the current time, unstable input ordering, or differing tool versions, outputs will diverge.

Mitigations:

- Pin generator and plugin versions.
- Pin schemas, templates, and input files by commit or digest.
- Sort inputs before passing them to the generator.
- Use a fixed random seed if the generator uses randomness and supports seeding.
- Strip timestamps or build numbers from released content.
- Do not fetch data from mutable APIs during the build.
- Record generator commands and configurations so they can be re-executed independently.

If generated files are committed to the repository, establish rules for updating them and verifying they match generator output. If generated in CI, store generator versions and inputs in provenance to diagnose discrepancies.

## 8. Container Images Must Be Reproducible Too

A container image is more than a collection of application files. Images also include manifests, configs, layers, metadata, and timestamps. Two images carrying identical application files can still have different digests if layers or metadata differ.

Common sources of divergence:

- Base images using mutable tags like `latest`.
- Package managers installing the newest version at build time.
- Files copied into the image retaining workspace timestamps.
- Changing file or layer order.
- Build arguments containing timestamps or build IDs.
- Image metadata populated with the current build time.
- Changing image builder tools or BuildKit versions.

### Pin base images by digest

Example:

~~~dockerfile
FROM eclipse-temurin:21-jre@sha256:<base-image-digest>

WORKDIR /app
COPY app.jar /app/app.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The digest pinpoints the exact base image content referenced. Tags help humans recognize versions, whereas digests serve as content identifiers. Replace the placeholder with a real digest from a trusted registry.

### Keep image inputs stable

- Pin base images by digest.
- Lock versions of packages installed inside the Dockerfile.
- Use package repositories or snapshots with fixed contents.
- Control timestamps, file permissions, and layer creation order.
- Use consistent builder versions and build configurations.
- Never pass secrets or personal data into build arguments or layers.
- Record the image digest and build provenance.

A container image can contain a reproducible JAR while the image itself remains non-reproducible. Therefore, verify both the application artifact digest and the final OCI image digest.

## 9. Build Once and Verify via Independent Rebuild

To prove an artifact is reproducible, perform at least two independent builds with controlled inputs.

Reference workflow:

1. Select a specific commit SHA.
2. Provision two clean, independent workspaces.
3. Supply identical toolchains, dependencies, configurations, and environment variables.
4. Run the identical build command.
5. Collect the resulting artifact from both runs.
6. Compute the SHA-256 digest of each artifact.
7. Compare hashes; if they differ, analyze structural and byte-level differences.
8. Save logs, metadata, and comparison results.

Both builds should execute on independent runners or workspaces. If both share a cache, build directory, or intermediate artifacts, they could rely on shared stale state and fail to genuinely test reproducibility.

### Comparing via hash

On Linux:

~~~sh
sha256sum build-a/app.jar
sha256sum build-b/app.jar
cmp build-a/app.jar build-b/app.jar
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash build-a/app.jar -Algorithm SHA256
Get-FileHash build-b/app.jar -Algorithm SHA256
fc.exe /b build-a/app.jar build-b/app.jar
~~~

`fc.exe /b` is a built-in binary comparison utility on Windows. Matching hashes confirm identical content under that hash algorithm. Differing hashes do not automatically mean source code or behavior changed; pinpoint where the bytes differ.

### Using diffoscope to diagnose causes

`diffoscope` inspects differences across many file formats. For JARs or ZIPs, it recurses into entries; for binaries, it reveals structural differences when supporting tools are available.

Investigation workflow:

1. Compare overall artifact hashes.
2. List archive contents and compare entry lists.
3. Compare timestamp metadata, permissions, and file ordering.
4. Extract into two separate directories and compare inner files.
5. Run `diffoscope` to locate differing bytes or metadata.
6. Trace the differing file back to the task or plugin that generated it.

Never try to make two hashes match by blindly stripping metadata. Determine whether that metadata is needed for runtime behavior, security, debugging, or traceability.

## 10. Integrating Reproducibility Checks into CI

You can start with a standard build check job and add an independent rebuild job to compare artifacts. For large workloads, running dual builds on every commit is not strictly necessary; apply it to releases, main branches, or schedules depending on cost and risk.

### Reference CI flow

~~~text
Commit SHA
    |
    v
Resolve locked dependencies
    |
    v
Build A on clean runner A
    |
    +--------------------+
    |                    |
    v                    v
Build B on clean runner B
    |                    |
    v                    v
Artifact A            Artifact B
    |                    |
    +----------+---------+
               |
               v
       Compare SHA-256
               |
        +------+------+
        |             |
      Equal        Different
        |             |
        v             v
  Reproducible    Investigate diff
  check passed    and fail gate
~~~

Both jobs must use the exact same commit SHA and identical locked input sets. If runners differ in OS or architecture, any difference may be a finding to detect or an environment outside the project's promised reproducibility scope. Define the comparison scope clearly.

### Example dual-build verification configuration

A pipeline can split into the following jobs:

~~~yaml
jobs:
  build_a:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.sha }}
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon clean build
      - run: mkdir -p reproducibility && cp build/libs/app.jar reproducibility/app.jar
      - run: sha256sum reproducibility/app.jar > reproducibility/app.sha256
      - uses: actions/upload-artifact@v4
        with:
          name: reproducibility-a
          path: reproducibility/

  build_b:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.sha }}
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon clean build
      - run: mkdir -p reproducibility && cp build/libs/app.jar reproducibility/app.jar
      - run: sha256sum reproducibility/app.jar > reproducibility/app.sha256
      - uses: actions/upload-artifact@v4
        with:
          name: reproducibility-b
          path: reproducibility/

  compare:
    needs: [build_a, build_b]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: reproducibility-a
          path: result-a
      - uses: actions/download-artifact@v4
        with:
          name: reproducibility-b
          path: result-b
      - run: cmp result-a/app.jar result-b/app.jar
~~~

This example illustrates the structure. In real workflows, adapt JAR paths, Gradle tasks, artifact names, and action versions to your project. Both jobs use the same runner image and SHA while running in separate workspaces. For higher assurance, use two independent runner pools or separate builders with documented configurations.

If the build requires dependencies, both jobs must resolve identical locked dependency contents. Caches only accelerate execution; caches must never replace lockfiles or checksums. During initial validation, run without caches to detect hidden dependencies on cache state.

### Handling comparison failures

If `cmp` reports differences, the `compare` job must fail so the result is never mistaken as reproducible. Preserve both artifacts, hashes, logs, and metadata for investigation. After fixing the root cause, re-run in clean workspaces to confirm.

Never mark the job as always-succeeding or ignore comparison errors just to keep the pipeline green. If an artifact intentionally carries variable metadata, separate that metadata out or explicitly define the verified artifact scope.

## 11. Reproducibility and Provenance: Complementary Evidence

Reproducible builds and build provenance answer two distinct questions:

- **Reproducibility:** given the same inputs and process, can the exact same artifact be produced again?
- **Provenance:** which source code, builder, tools, dependencies, and pipeline run produced this artifact?

An artifact can be reproducible yet built from malicious source code. Conversely, an artifact with complete provenance may still be non-reproducible if the build embeds timestamps or variable data.

A provenance record should capture:

- Repository and commit SHA.
- Build tool, compiler, and runtime versions.
- Container image or runner image digest.
- Dependency lockfiles and checksums.
- Key build flags and environment variables.
- Pipeline run ID and builder identity.
- Artifact URI, version, and digest.
- Reproducibility check outcome.
- Signatures or attestations where supported by the system.

Never include secrets, tokens, or sensitive data in provenance. Attestations can be signed using protected keys or short-lived workload identities, then verified prior to release.

### Reproducible builds do not replace security checks

Two builds producing identical binaries only prove the process consistently reproduces outputs from declared inputs. That does not prove dependencies are vulnerability-free, source was properly reviewed, or the compiler was uncompromised.

Combine with:

- Dependency scanning and license checks.
- Static analysis and testing.
- Dependency checksum/signature verification.
- Builder provenance verification.
- Hardening pipeline definitions and runners.
- Reviewing toolchain and lockfile updates.
- Storing immutable artifacts alongside digests.

## 12. Digital Signatures and Intentionally Variable Outputs

Digital signatures may contain timestamps from a timestamping authority, certificate details, or random nonces. As a result, signing the exact same binary twice can produce different signature files even though the binary itself is unchanged.

A common pattern:

1. Build the artifact using a reproducible process.
2. Compute and store the digest of the unsigned artifact.
3. Verify reproducibility on that unsigned artifact.
4. Sign the artifact or generate an attestation in a separate release step.
5. Store signatures and signing metadata separately or link them by digest.

Not every signature is inherently non-reproducible; this depends on the algorithm, format, and signing method. However, if signing injects external timestamps or changing certificate info, do not use the entire signed file as the binary comparison target. Define precisely which portion of the content must be reproducible.

Data such as build numbers, release times, approvers, or release notes may also vary intentionally. Separate them from immutable artifacts unless required inside the runtime package, or manage them in a separate release manifest.

## 13. Practice Maturity Levels and Rollout Roadmap

Not every project needs to become a complex hermetic system overnight. You can advance through stages:

| Level | Practice | Outcome |
|---|---|---|
| 1. Re-runnable | Standard build command, clean workspace, clear logs | Team can reliably re-execute the process |
| 2. Input-locked | Specific commits, dependency locks, pinned toolchains | Reduces variance from versions and external state |
| 3. Environment-normalized | Specific images, stable locale/timezone, timestamps, and paths | Reduces sources of nondeterminism |
| 4. Hermetic build | Declared inputs only, restricted network and external filesystem access | Strengthens independent rebuild capability |
| 5. Byte-verified | Two independent builds, hashes, and diffoscope | Concrete evidence of artifact reproducibility |
| 6. Provenance-attached | Stored source, builder, dependencies, digest, and attestation | Full artifact creation chain is verifiable |

### Roadmap for Java projects

1. Standardize the build command with Gradle Wrapper or Maven Wrapper.
2. Pin the JDK/toolchain and plugin versions.
3. Enable dependency locking or declare explicit dependency versions.
4. Enable dependency verification where supported by the ecosystem.
5. Normalize archive timestamps and file ordering.
6. Use clean workspaces and pin the source commit.
7. Run two independent builds and compare JARs via SHA-256.
8. When hashes differ, use `diffoscope` or extract archives to pinpoint changing metadata.
9. Store results alongside the commit SHA and artifact digest.
10. Enforce strict verification on releases once the process stabilizes.

## 14. Common Mistakes

| Practice | Issue | Improvement |
|---|---|---|
| Re-running a build, seeing success, and calling it reproducible | Only proves the command can succeed | Compare artifacts byte-for-byte |
| Using dynamic dependency versions | Two builds may fetch different content | Lock versions and verify checksums |
| Using the `latest` container tag | Base image can change silently | Pin by digest |
| Embedding the current time in files | Every build emits different bytes | Use stable timestamps or separate metadata |
| Not normalizing file order | Archives may alter entry order | Sort entries deterministically |
| Building from a dirty workspace | Stale or untracked files leak into packages | Use clean checkouts and control state |
| Sharing caches across unequal trust zones | Caches can corrupt or taint builds | Partition caches and verify dependencies |
| Checking only the JAR and ignoring the container image | Image metadata or layers still change | Verify digests of both packages and images |
| Comparing signed files with dynamic timestamps | Signatures differ even when binaries match | Verify binary reproducibility before signing |
| Storing only hashes without inputs | Cannot diagnose why a hash changed | Record provenance and build metadata |
| Reusing the same workspace for two builds | Intermediate state may be shared | Use independent runners/workspaces |

## 15. Reproducible Build Verification Checklist

### Inputs

- [ ] Build checks out an explicit commit SHA.
- [ ] Working tree is clean with no unexpected modifications.
- [ ] Submodules, Git LFS, and auto-generated files are clearly defined.
- [ ] Dependencies and plugins have locked versions.
- [ ] Dependency contents are verified via checksum or signature where possible.
- [ ] Container base images are pinned by digest if used.

### Environment and process

- [ ] OS, JDK, compiler, and build tool versions are recorded.
- [ ] Locale, timezone, encoding, and umask are normalized where impactful.
- [ ] Variable timestamps and build metadata are removed or fixed.
- [ ] Archive file ordering is deterministic.
- [ ] Absolute paths and personal workstation info are not inadvertently embedded.
- [ ] Builds do not depend on mutable external data or services.

### Output verification

- [ ] Both builds run in independent workspaces.
- [ ] Both builds consume identical declared input sets.
- [ ] Artifacts are compared via SHA-256 or byte-level comparison.
- [ ] When hashes differ, logs and analysis tools are available to isolate the cause.
- [ ] Verification results are stored alongside commit SHA and artifact digest.
- [ ] Signatures and release metadata are evaluated under their own separate scope.

## Conclusion

Re-runnable builds let teams reliably repeat execution; byte-for-byte reproducible builds prove that identical inputs and processes yield identical artifacts across independent runs. Achieving this requires locking dependencies, pinning toolchains, normalizing environments, controlling timestamps and metadata, eliminating variable data sources, and verifying hashes across two clean builds. Combining those results with provenance and immutable artifacts enables teams to better verify the origin, integrity, and rebuildability of release packages throughout the entire CI/CD lifecycle.
