# Handling Stale Caches, Corrupted Caches, and Inconsistent Results

Caching helps CI/CD pipelines download dependencies faster, avoid recomputing reusable outputs, and cut wait times. Yet caches can also become a source of baffling bugs: one cached build succeeds while another fails; clearing the cache makes the error vanish; or the same commit produces different artifacts between a developer laptop and a runner.

To handle this properly, identify what kind of data the cache stores, which inputs that data depends on, and which rules the system uses to restore caches. A cache is merely a regenerable copy. A build must still run accurately when the cache is empty, and a cache hit must never alter result correctness.

## 1. Distinguishing Cache Types and Artifacts

In a build workflow, multiple directories may loosely be called caches, yet they have different purposes and risk profiles:

| Data Type | Examples | Purpose | Handling When Failure Is Suspected |
|---|---|---|---|
| Dependency cache | Downloaded JARs, package archives, repository metadata | Avoid re-downloading libraries and plugins | Check checksums, metadata, and versions; delete only the faulty entry |
| Build cache | Outputs of compile, test, or packaging tasks | Reuse task outputs for equivalent inputs | Check input/output declarations and task determinism |
| Workspace cache | Intermediate build directories, generated sources, local outputs | Reduce work across runs on the same workspace | Clean workspace or test on a fresh workspace for comparison |
| Tool cache | Downloaded Gradle, Maven, JDK, or tool distributions | Avoid re-downloading tools | Check version, download source, and checksum |
| CI cache | Archives saved and restored between jobs by the CI platform | Share regenerable data across runners | Check key, access scope, save timing, and cache version |
| Artifact | Produced JAR, WAR, image, or release package | Store an identified output for deployment or distribution | Verify digest, provenance, and build source; never treat artifacts as temporary caches |

**Artifacts and caches do not replace each other.** An artifact is the output of a build run, requiring identity and storage for deployment, testing, or release. A cache is acceleration data; it can be deleted and regenerated without changing the valid outcome of a build.

For example, a built JAR tagged with a version and checksum is an artifact. A directory holding downloaded dependencies for reuse in the next build is a dependency cache. If the dependency cache is deleted, the build must re-download libraries. If a released artifact is deleted, the team can lose the output needed to deploy or roll back.

### A Cache Hit Is Not Proof of Correctness

A cache hit only indicates the system found an entry matching the requested key and restored it. It does not prove:

- Cache contents were built from the exact right inputs.
- The cache has not been corrupted or altered.
- Every input affecting the output was included in the cache key.
- Build tasks completely declared all inputs and outputs.
- Results were verified against the current source code state.

Therefore, control how caches are created, how keys are chosen, and how data is verified after restoration.

## 2. Identifying Stale Caches, Corrupted Caches, and Inconsistent Results

These three conditions have similar symptoms, yet different root causes.

### Stale Cache

A stale cache is a cache created from inputs or environments that no longer fit the current build. Examples:

- A dependency lockfile changed, yet the cache key omitted the lockfile.
- The JDK was upgraded from 17 to 21, yet the cache is still shared.
- A build script or compiler option changed, yet the build cache failed to detect the new input.
- Repository metadata changed, yet the old cache retains prior resolution info.
- A `SNAPSHOT` or dynamic-version dependency updated, yet the local repository still holds the old copy.

A stale cache is not necessarily corrupted at the file level. It may be readable and extract cleanly, yet no longer represent the required inputs.

### Corrupted Cache

A corrupted cache is stored data that is no longer intact or usable properly:

- An archive truncated because a job was terminated mid-write.
- An incomplete JAR file or mismatched checksum.
- Partially written metadata or indexes.
- Two processes writing concurrently to the same cache directory.
- A cache archive corrupted during upload, download, or extraction.
- Another process modifying files while the build reads them.

Common symptoms include extraction errors, ZIP errors, checksum mismatches, unreadable classes, missing files, or intermittent I/O errors.

### Inconsistent Results

Inconsistent results occur when the same change yields different outputs or test outcomes across runs. Causes may include caching, or stem from:

- Unpinned dependency or plugin versions.
- Builds depending on timestamps, timezone, locale, or file ordering.
- Tasks reading from mutable networks or external services.
- Generated sources relying on leftover workspace state.
- Build scripts with incomplete input or output declarations.
- Tests sharing mutable data while running unsafely in parallel.
- Runners having differing JDKs, OSes, architectures, or environment variables.

Do not conclude caching is the sole root cause just because clearing the cache makes a build pass. Clearing the cache can force tools to re-download dependencies, recompute outputs, or pick up fresh metadata, temporarily masking the underlying cause.

## 3. Designing Cache Keys to Avoid Restoring Incompatible Data

A cache key is an identifier used to store and restore a dataset. A key that is too broad can restore incompatible data; a key that is too narrow lowers reuse and increases storage overhead.

A cache key should reflect inputs that can change cache contents:

- Runner operating system and architecture.
- JDK or runtime version affecting outputs.
- Gradle/Maven or package manager version.
- Wrapper properties and tool configuration.
- Lockfiles, dependency manifests, and BOMs.
- Build scripts, plugins, and compiler options.
- Cache type and task scope.
- Cache format version or a team-managed cache salt.

For example, a Gradle dependency cache can use this conceptual key:

~~~text
gradle-dependencies
  + operating-system
  + architecture
  + jdk-major
  + wrapper-version
  + dependency-lock-hash
  + cache-schema-version
~~~

Not every cache needs every field above. Pick the exact set of inputs matching the stored data. A pure dependency cache depends less on commit SHAs than a build output cache. A compilation cache must account for compiler, build scripts, and task inputs.

### Do Not Use Commit SHA as the Default Key for Dependency Caches

If a key contains the commit SHA, every commit typically creates a new cache even when dependencies do not change. This sharply drops the cache hit rate. For dependency caches, hashing lockfiles and dependency configuration is usually more appropriate.

Conversely, for build outputs depending on source contents, task caches must identify task inputs. Do not use a static key for all build outputs, because source changes could restore stale outputs.

### Distinguishing Exact Keys and Restore Keys

Some CI platforms support an exact key plus a list of fallback restore keys. The exact key represents the expected input set. Restore keys allow finding a close match when no exact match exists.

Restore keys help for dependency caches that can top up missing items without altering locked dependencies. Yet overly broad fallbacks can pull in incompatible metadata or packages. Do not use broad restore keys for caches holding build outputs or generated files without proving safety.

When using fallbacks:

1. Keep critical invariant fields such as OS, architecture, and tool type.
2. Never fall back across incompatible major versions.
3. Verify dependencies against lockfiles and checksums after restoring.
4. Save a new cache only after the job completes successfully.
5. Log the actual cache key and restore source for diagnostics.

## 4. Example Dependency Caching in GitHub Actions

The following example illustrates Gradle caching based on OS, wrapper properties, and dependency lockfiles:

~~~yaml
steps:
  - name: Checkout
    uses: actions/checkout@v4

  - name: Set up JDK
    uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'

  - name: Restore Gradle dependency cache
    uses: actions/cache/restore@v4
    with:
      path: |
        ~/.gradle/caches/modules-2
        ~/.gradle/wrapper/dists
      key: gradle-deps-linux-jdk17-<lockfile-hash>
      restore-keys: |
        gradle-deps-linux-jdk17-

  - name: Build
    run: ./gradlew --no-daemon clean check

  - name: Save Gradle dependency cache
    if: success()
    uses: actions/cache/save@v4
    with:
      path: |
        ~/.gradle/caches/modules-2
        ~/.gradle/wrapper/dists
      key: gradle-deps-linux-jdk17-<lockfile-hash>
~~~

In this example, `<lockfile-hash>` is a placeholder representing the hash of lockfiles and dependency configs. In practice, use an expression or hashing step suited to the files in your repository. If using broad restore keys, restrict them to dependency caches that can be re-verified; do not apply the same approach to build outputs.

The snippet above is illustrative; adjust paths and action versions to match your repository. Not every folder in `GRADLE_USER_HOME` should be shared across runners. Avoid caching daemon state, active lock files, temporary logs, or OS-dependent data without clear justification.

### Caching Maven in CI

For Maven, the local repository directory is usually `~/.m2/repository`. This directory can be cached to avoid re-downloading dependencies and plugins:

~~~yaml
steps:
  - name: Checkout
    uses: actions/checkout@v4

  - name: Set up JDK
    uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'
      cache: maven

  - name: Verify
    run: ./mvnw -B clean verify
~~~

The built-in Maven cache in the JDK setup action is a convenient option. Check the key the action generates, tracked dependency files, and repository cache policies. If the project uses multiple `pom.xml` files, profiles, BOMs, or custom dependency config files, make sure those files feed into cache key computation.

Do not cache `~/.m2/settings.xml` containing credentials or private repository configurations. Caches should hold only regenerable dependency data. Credentials must be supplied via secrets or dedicated CI authentication mechanisms.

## 5. Differences Between Gradle and Maven Dependency Caching

### Gradle

Gradle stores several kinds of data under `GRADLE_USER_HOME`, including:

- Wrapper distributions.
- Module artifacts and metadata.
- Dependency resolution cache.
- Build cache if configured to reside there.
- Daemon state, logs, and other supporting data.

Do not treat the entire `GRADLE_USER_HOME` as an arbitrary cache archive movable across any runner. Some data depends on version, OS, running processes, or specific configuration. Prefer caching only the needed areas, such as module artifacts or wrapper distributions; separate the build cache if it has its own policy.

The Gradle dependency cache and Gradle build cache also differ. The dependency cache stores resolved libraries and metadata. The build cache stores reusable task outputs keyed by task inputs. Clearing the dependency cache makes the build re-download libraries; disabling the build cache forces certain tasks to re-execute. These two actions help isolate different root causes.

### Maven

Maven's local repository stores dependencies, plugins, metadata, and downloaded or locally installed artifacts. Caching all of `~/.m2/repository` can help, but note:

- `SNAPSHOT` artifacts can change over time.
- Repository metadata can become stale.
- Plugins or parent POMs may update per repository policy.
- Multiple projects might share a local repository with different configurations.
- A build might leave locally installed artifacts that do not exist in remote repositories.

With immutable release dependencies and explicitly declared versions, Maven caching is easier to manage. With `SNAPSHOT`s or dynamic versions, limit cache lifetimes, isolate namespaces, or force intentional updates. When re-checking metadata, use appropriate update flags or remove only the suspected artifact rather than immediately wiping the entire local repository.

## 6. Distinguishing Dependency Cache and Build Cache

This is a vital step when build results are inconsistent.

The **dependency cache** answers: which libraries did the tool download and resolve? If the dependency cache is wrong, the build may use an incorrect version or a corrupted library file.

The **build cache** answers: for a given set of task inputs, which outputs can be reused? If the build cache is wrong, the build may pull outputs created from different inputs or from a task with missing dependency declarations.

In Gradle, tasks can participate in the build cache when inputs/outputs are properly declared and the task is cache-safe. A task that reads an undeclared file, queries system time, or calls external APIs while still marked cacheable can return stale outputs that are no longer valid.

When writing custom tasks:

- Declare every file, property, and option affecting output as an input.
- Declare outputs explicitly.
- Avoid depending on implicit workspace state.
- Never mark non-deterministic tasks as cacheable.
- Normalize outputs if ordering, timestamps, or paths can vary.

If a task cannot fully describe its inputs, consider disabling caching for that task until correctness is guaranteed. Do not enable caching for every task just to raise hit rates.

## 7. Stale Caches: Knowing When to Invalidate

Caches should be invalidated when a critical input changes enough that old data is no longer compatible. Events typically requiring a cache key or cache version update:

| Change | Cache to Review | Reason |
|---|---|---|
| Upgrading Gradle or Maven | Related wrapper/tool cache, dependency cache, and build cache | Cache format or resolution behavior may change |
| Upgrading JDK | Build cache and caches holding JDK-dependent outputs | Bytecode and compiler behavior may change |
| Changing lockfile or BOM | Dependency cache or dependency-based key | Expected dependency set changed |
| Changing plugin/build script | Build cache and config keys | Output generation logic may change |
| Changing compiler options | Build cache | Compilation outputs may differ |
| Changing OS/architecture | Platform-dependent tool cache and build cache | Binaries or native outputs may be incompatible |
| Changing cache format | Cache schema/version | Legacy data can no longer be read cleanly |
| Changing repository source | Dependency metadata and related caches | Same coordinates may resolve from a different source |

There is no need to purge caches solely because a new commit arrived if relevant inputs did not change. Selective cache key updates preserve reuse efficiency while avoiding incompatible data.

### Using Cache Salts Intentionally

A cache salt is a team-managed version string, such as `cache-v3`. When stale caches occur due to structural or policy changes not yet reflected in keys, increment the salt to open a fresh namespace.

Do not bump the salt on every build or every commit. Doing so turns the cache into single-use data and blinds the team to which inputs genuinely require rotation.

## 8. Corrupted Caches: Isolation and Recovery Workflow

When cache corruption is suspected, narrow the scope first:

**Step 1: Capture evidence.** Save the run ID, commit SHA, cache key, restore key, download/extraction logs, and exact error. Record runner, OS, JDK, and build tool details.

**Step 2: Reproduce on identical inputs.** Re-run the same commit and configuration. If the failure appears only on a specific runner or restore event, check workspace differences and cache sources.

**Step 3: Run a control build without the suspect cache.** Disable cache restore or use a fresh cache key for that scope. If the clean build still fails, the cause likely lies in source code, dependencies, or environment.

**Step 4: Delete only the faulty entry.** If a specific artifact or metadata file is identified as corrupted, delete that entry from the local cache or rotate to a new cache namespace. Avoid wiping entire shared caches unnecessarily.

**Step 5: Re-download and verify.** Fetch dependencies from a trusted repository, verify checksums if available, and run build and tests. Save the new cache only after the job succeeds.

**Step 6: Compare outputs.** Compare logs, dependency trees, artifact digests, and cache keys between the clean run and cached run.

**Step 7: Find the root cause.** Check for missing inputs in keys, concurrent cache writes, tasks under-declaring inputs/outputs, mutable repository responses, or interrupted upload/download flows.

### Isolation Example with Gradle

Separate dependency cache and build cache to pinpoint the failing layer:

~~~bash
# Run build without using build cache
./gradlew --no-build-cache clean check

# Force refresh of dependency metadata on demand
./gradlew --refresh-dependencies clean check

# List Java toolchains detected by Gradle
./gradlew -q javaToolchains
~~~

The first two flags do not do the same thing. `--no-build-cache` disables reading/writing task outputs from the build cache for that run. `--refresh-dependencies` tells Gradle to re-validate dependency state via its resolution mechanism; it does not wipe every cache on disk.

Use `--refresh-dependencies` only when checking dependency resolution. It can increase network traffic and build times. If a specific JAR file is suspected of corruption, identify its dependency coordinates and delete only its corresponding entry in the Gradle cache to trigger re-download.

### Isolation Example with Maven

~~~bash
# Run Maven with metadata/dependency updates from repositories
./mvnw -B -U clean verify
~~~

Depending on repository type and dependency version, `-U` instructs Maven to check updates for snapshots and missing releases. It does not delete the entire local repository. If a specific artifact is corrupted, locate its `groupId`/`artifactId`/`version` and remove only that artifact directory under `~/.m2/repository` so Maven re-downloads it.

Do not delete the local repository directory while another Maven process is actively using it. If multiple jobs share a local repository, stop or isolate related jobs before cleaning data.

## 9. Inconsistent Results: Comparing Clean Builds and Cached Builds

A control matrix helps distinguish cache errors from other non-deterministic bugs:

| Run | Workspace | Cache | Purpose |
|---|---|---|---|
| A | Completely fresh | Do not restore cache | Establish clean-build baseline |
| B | Completely fresh | Restore current cache | Test cache impact |
| C | Completely fresh | Fresh cache key | Test stale cache namespace |
| D | Same config as A | Re-run clean build | Test determinism of the build itself |

Compare the results:

- Dependency tree and actual resolved versions.
- JDK, build tool, plugins, and environment config.
- File list inside the artifact.
- File contents and checksums.
- Test results, generated sources, and task logs.
- Cache hit/miss status and restored cache source.

If A and B differ while A and D match, caching is a strong suspect. If A and D also differ, the build may depend on timestamps, network, external data, or non-deterministic tasks. If A, B, and C all fail identically, investigate source code, dependencies, or environment before deleting more caches.

### Comparing Artifacts

When byte-for-byte identical artifacts are required, compute SHA-256:

~~~bash
# Linux
sha256sum build/libs/application.jar

# PowerShell
Get-FileHash .\build\libs\application.jar -Algorithm SHA256
~~~

Different digests tell you file contents differ, without showing why. Unpack and diff individual files to spot variations like timestamps, entry order, manifests, generated metadata, or build-time embedded strings.

An artifact can have a different digest due to archive timestamps even when bytecode and logic are unchanged. Conversely, two artifacts with identical names do not guarantee identical contents. Store digests alongside build ID, commit SHA, and environment metadata.

## 10. Controlling Caches When Multiple Jobs Run in Parallel

Multiple jobs may restore or write caches concurrently. If they share an active working directory directly, issues can occur:

- Files partially written while another job reads them.
- Metadata or lockfile contention.
- A failing job leaving behind half-built state.
- Two jobs saving different contents under the same key.
- A runner terminating before cache upload finishes.

Prefer the CI platform's caching mechanism with isolated upload/download flows and explicit cache keys. For shared local caches, use locking, atomic temp-write-and-swap where possible, and avoid unsafe concurrent writes to the same data area across processes.

If parallel jobs only read a completed dependency cache, allow sharing in ways supported by the build tool. Never share daemon state or task output directories across multiple processes unless the tool guarantees safety.

### Save Caches Only After Successful Execution

A job failing midway may have downloaded partial dependencies or produced incomplete outputs. If the system uploads the cache regardless of status, future runs may restore incomplete data.

Normally, save caches only after verification steps succeed. For dependency caches, know whether the tool can recover interrupted downloads; for build caches, publish outputs only when tasks finish validly and all input metadata is recorded completely.

## 11. Cache Security and Trust Boundaries

Caches can contain generated code, dependencies, metadata, config files, and occasionally sensitive data if cache paths are overly broad. Treat caches as a data channel across runs:

- Never cache files containing secrets, access tokens, credentials, or settings with passwords.
- Never cache an entire user home directory without auditing contents.
- Separate caches by repository, project, OS, and trust level when needed.
- Never allow workflows from untrusted pull requests to overwrite caches used by trusted release workflows.
- Verify dependency/artifact checksums or signatures according to policy.
- Restrict cache access permissions and log enough details to trace creation sources.
- Never execute scripts or binaries retrieved from an untrusted cache in environments holding secrets or elevated privileges.

Cache poisoning can trick a trusted job into restoring files created by a lower-trust workflow. Consequences include arbitrary code execution, substituted dependencies, or compromised artifacts. Design read/write permissions around trust boundaries, not merely branch names.

For pipelines with publish or deploy privileges, consider allowing them to read only caches created by trusted branches or workflows. If the platform lacks strict access isolation, use separate cache namespaces or disable caching in sensitive stages.

## 12. Monitoring Cache Effectiveness and Quality

A high cache hit rate is not the sole objective. A cache is valuable when it cuts runtime and cost without raising error rates or producing incorrect results.

A dashboard can track:

| Metric | Meaning |
|---|---|
| Cache hit rate | Percentage of cache restore requests succeeding |
| Restore duration | Time to download and extract the cache |
| Save duration | Time to pack and upload the cache |
| Cache size | Storage footprint and growth rate |
| Dependency download time | Time spent downloading dependencies on cache misses |
| Build duration with/without cache | Net improvement provided by caching |
| Cache-related failure rate | Rate of failures tied to restore, checksums, or cached data |
| Clean-build consistency | Consistency across clean builds |
| Cache invalidation frequency | How often keys must rotate or caches are purged |

If a cache grows so large that restore time approaches dependency download time, net gains may be negligible. Narrow cached paths, drop unneeded data, and evaluate caching by total `restore + build + save` time.

Also watch the failure rate following cache hits. A fast cache hit that increases inconsistent failures harms delivery flow.

## 13. Cache Troubleshooting Checklist

When a build shows signs of cache issues, walk through this checklist:

- [ ] Identify the cache type involved: dependency, build output, workspace, tool, or CI cache.
- [ ] Record commit SHA, run ID, runner, JDK, build tool, and cache key.
- [ ] Determine whether the cache restored via exact key or restore key.
- [ ] Check whether lockfiles, build scripts, plugins, toolchains, and inputs are reflected in the key.
- [ ] Run a control build excluding only the suspected cache type.
- [ ] Inspect checksums, archives, metadata, and the dependency tree.
- [ ] If needed, rotate to a new cache key or delete only the corrupted entry.
- [ ] Run clean builds multiple times to verify stability.
- [ ] Compare artifact digests and contents if byte-for-byte reproducibility is required.
- [ ] Audit cache read/write permissions, parallel jobs, and cache poisoning risks.
- [ ] Save new caches only after data has been verified.
- [ ] Document the root cause and update cache keys or workflows to prevent recurrence.

## 14. Practical Rules

- Design caches around the data type and inputs that genuinely affect that data.
- Use lockfiles and explicit tool versions; never use caches to hide unstable dependencies.
- Keep exact keys strict enough; use restore keys only when compatibility risks are understood.
- Separate dependency caches from build caches and release artifacts.
- During investigation, disable the exact suspected cache type as a control before purging everything.
- Delete only isolated cache entries or open a new namespace when invalidating.
- Avoid sharing actively written paths across parallel jobs unless the tool guarantees safety.
- Never store secrets or let lower-trust workflows write caches consumed by trusted release pipelines.
- Track both cache performance and post-hit failure rates; clean builds must still succeed reliably.

Good caching makes CI/CD faster without changing the meaning of a build. When keys accurately reflect inputs, caches are separated by purpose, data is verified, and recovery workflows stay targeted, teams can leverage caching while keeping build outputs reliable. If a build only passes with—or only fails without—a specific cache, that is a signal to investigate determinism in dependencies, tasks, and environment.
