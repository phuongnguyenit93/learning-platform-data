# Ensuring Pipelines Remain Correct When Caches Are Unavailable

Caching in CI/CD reduces dependency download times, restores intermediate build data, and avoids repeating expensive work. However, caches can be purged, expire, become incompatible, suffer corruption, or turn temporarily unreachable. Therefore, **a correct pipeline must still build and test cleanly starting from an empty cache**.

This is a core principle of **DEVOPS_CI_CD_FUNDAMENTALS**. A pipeline connects Git events to build steps, testing, artifact management, environments, and quality gates. Caches merely support the performance of those steps. If a pipeline's correctness depends on a specific cache existing, the pipeline harbors a hidden dependency and becomes hard to reproduce.

## 1. Caches Are Performance Optimizations, Not Mandatory Data Sources

A cache is a temporary copy of data that can be regenerated or re-downloaded from trusted sources. In pipelines, commonly cached data includes:

- Packages or libraries downloaded from registries.
- Build tool distributions, such as the Gradle Wrapper.
- Metadata helping package managers resolve dependencies faster.
- Build task outputs reusable when inputs remain unchanged.
- Intermediate data expensive to regenerate.

A cache may be absent on a first run, after key changes, upon cache eviction, when a branch lacks cache read access, on a different runner OS, or during a cache service outage. Such scenarios are normal in the CI lifecycle.

Ask: **if all caches are deleted and the pipeline re-runs on the same commit, are build, test, and artifact results still correct?** If the answer is no, find and eliminate the hidden dependency.

Examples:

- Correct: on an empty cache, Gradle downloads dependencies from the lockfile, then runs tests.
- Wrong: on an empty cache, the job fails because a script expects a file left behind by a previous run.
- Correct: a cache hit makes tests run faster; a cache miss still executes all steps.
- Wrong: skipping tests or quality checks simply because of a cache hit.

A cache miss is not a build failure. An unreachable cache service should not break build correctness if the pipeline can still pull data from official sources. However, if the upstream registry or source repository is also unreachable, the pipeline may fail; a cache does not automatically become a complete backup or mirror of that source.

## 2. Distinguishing Dependency Caches, Build Caches, and Artifacts

These three concepts are often lumped together yet serve distinct purposes and storage requirements:

| Type | Contents | Goal | Can Be Lost Without Corrupting Results? |
| --- | --- | --- | --- |
| Dependency cache | Downloaded packages, libraries, metadata | Reduce dependency download times | Yes; package manager must re-download from repositories |
| Build cache | Build task outputs keyed by inputs and configuration | Avoid re-running tasks with equivalent outputs | Yes; tasks must re-execute |
| Artifact | Produced JAR, binary, container image, test report, or release package | Hand off, archive, and release generated outputs | Must not be treated as temporary data; retain per policy |

**Caches do not replace artifacts.** A build's artifact must be stored in an artifact store or registry with a traceable identity. Never use caches to pass release packages between jobs or store mandatory release evidence.

Dependency caches contain re-downloadable files. Build caches can hold computed outputs, though safely only when the system fully tracks inputs, toolchains, and factors affecting output. Artifacts are outputs intentionally published and lifecycle-managed by the pipeline.

Example with Gradle:

- Dependency cache stores downloaded modules under Gradle User Home.
- Gradle Build Cache stores task outputs keyed by hashes of task inputs and configuration.
- The JAR produced by a build task for release is an artifact; it must be published to an artifact store.

Do not arbitrarily cache a project's entire `build` directory assuming old files stay compatible with new commits. Use the tool's official build cache mechanism, declare task inputs/outputs completely, and let the tool decide when outputs are safely reusable.

## 3. Designing Pipelines Around Cold-Cache Correctness

A cold cache is the state where a pipeline starts with no usable cache data. A correct pipeline must complete the entire workflow from this state:

1. Check out the exact commit.
2. Read the dependency manifest or lockfile.
3. Restore a cache if a compatible entry exists.
4. If the cache is missing or unusable, download dependencies from configured repositories.
5. Verify dependencies and run the build.
6. Run tests and quality gates.
7. Produce artifacts and store outputs per the release workflow.
8. Optionally save a new cache if the run succeeds.

Decision flow:

~~~mermaid
flowchart TD
    A["Start pipeline at specific commit"] --> B["Read lockfile and toolchain config"]
    B --> C["Attempt cache restore"]
    C --> D{"Cache available and compatible?"}
    D -- "Yes" --> E["Use restored cache data"]
    D -- "No" --> F["Skip cache and download dependencies"]
    C -. "Cache service error" .-> F
    E --> G["Resolve and verify dependencies"]
    F --> G
    G --> H["Build and test"]
    H --> I{"Required steps pass?"}
    I -- "No" --> J["Fail pipeline and retain logs"]
    I -- "Yes" --> K["Produce and publish artifact"]
    K --> L["Save cache if possible"]
~~~

The crucial point is that both cached and uncached paths converge on the same dependency resolution, build, and test steps. Caching can change execution time, but must never alter quality standards or expected output contents.

### 3.1. Never Use Cache Hit as a Condition to Skip Mandatory Work

A common mistake is writing a condition like:

~~~yaml
- name: Build
  if: steps.cache.outputs.cache-hit == 'true'
  run: ./gradlew build
~~~

On a cache miss, the build step is skipped and the pipeline can turn green without building anything. Such a condition inverts the role of caching.

The right approach ensures the build always runs:

~~~yaml
- name: Build and test
  run: ./gradlew --no-daemon test
~~~

The package manager or build tool decides internally whether to reuse existing data or fetch/rebuild missing parts. If you want to surface cache hit/miss status, use that output strictly for logging or performance metrics.

### 3.2. Do Not Run Offline Mode When Pipelines Need Cold-Build Capability

Some tools offer an offline mode. This helps when an environment has already pre-populated every dependency, yet causes cold builds to fail if a single package is missing.

For example, with Gradle, the standard command:

~~~bash
./gradlew --no-daemon test
~~~

allows Gradle to fetch missing dependencies from configured repositories. The offline command:

~~~bash
./gradlew --offline test
~~~

is appropriate only when the pipeline explicitly guarantees all required dependencies are already staged. Never enable offline mode merely to avoid re-downloading dependencies in regular pipelines. If offline builds are required by environmental constraints, stage and verify the input dependency bundle as a distinct workflow step.

## 4. Locking Dependencies So Caches Cannot Alter Versions

Caches must not decide library versions. Versions must come from manifests, lockfiles, or controllable, reviewable resolution rules.

Examples:

| Ecosystem | How Dependencies Are Pinned |
| --- | --- |
| Gradle | Dependency locking, version catalogs, and dependency verification |
| Maven | Explicit versions, centralized versions via BOM/parent, and repository controls |
| npm | `package-lock.json` and `npm ci` |
| pnpm | `pnpm-lock.yaml` and `pnpm install --frozen-lockfile` |
| Yarn | `yarn.lock` and immutable mode matching the Yarn version |
| Python | Lockfiles or pinned requirements files with hashes per policy |

Lockfiles define the dependency graph expected by the build. Checksum or dependency verification mechanisms detect package contents mismatching trusted values. Caches merely supply copies of packages; tools must still validate consistency per policy.

With Gradle, enable dependency locking for target configurations and generate verification metadata. When lockfiles or verification metadata change, review those diffs just like source code changes. With npm, use `npm ci` in CI to install from `package-lock.json`; it fails if `package.json` and the lockfile are out of sync and provides a more deterministic install than `npm install`.

Never use a floating dependency tag or overly broad version range while relying on a cache to hold onto an older version. Once the cache is purged, the tool may download a newer version and yield different results. Versions must be locked independently of caching.

## 5. Designing Predictable Cache Keys

A cache key identifies a reusable dataset. A good key changes when cached contents cease to be compatible and stays stable while data remains reusable.

Components typically included in keys:

- Runner operating system and architecture.
- Runtime version, such as JDK or Node.js.
- Package manager or build tool version.
- Lockfiles and manifests tied to dependencies.
- Configuration files affecting resolution.
- A team-managed version prefix to intentionally invalidate old caches.

Example key for Gradle:

~~~text
gradle-v2-linux-jdk21-<hash-of-lockfiles-and-toolchain>
~~~

Keys should not depend solely on branch names or commit SHAs. Putting the commit SHA in the key creates a fresh cache on nearly every commit and loses most reuse. Conversely, an overly broad key can restore caches from an incompatible runtime or OS.

### 5.1. Exact Keys and Restore Prefixes

Some systems support a list of restore keys. A pipeline can try:

1. An exact key containing the current lockfile hash.
2. A compatible prefix matching the same OS and runtime.
3. If no suitable cache is found, starting from an empty cache.

Restore prefixes are only a shortcut to grab close data and save time. They do not prove all current dependencies are present or at the right versions. The package manager must still resolve against the lockfile and fetch anything missing.

Never fall back from Linux to Windows, from JDK 21 to JDK 8, or across different CPU architectures when cached data holds environment-dependent components. Broaden restore scope only when compatibility is already known.

### 5.2. Intentional Cache Invalidation

When changing cache layout or discovering old caches cause bugs, increment the version prefix—for example, from `gradle-v2` to `gradle-v3`. This opens a new namespace without manually deleting every old cache.

When only dependencies change, the lockfile hash should rotate the key automatically. When toolchains, images, or cache-affecting configs change, keys must reflect those changes too.

## 6. GitHub Actions Example: Caching Gradle While Always Building When Cache Is Missing

The example below shows separating restore, build/test, and save steps. Cache actions are allowed to fail without failing the pipeline; the build/test step still runs and resolves dependencies itself.

~~~yaml
name: Java CI

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Restore Gradle dependency cache
        id: gradle-cache
        uses: actions/cache/restore@v4
        continue-on-error: true
        with:
          path: |
            ~/.gradle/caches/modules-2
            ~/.gradle/wrapper/dists
          key: gradle-v2-${{ runner.os }}-jdk21-${{ hashFiles('**/*.gradle*', '**/gradle-wrapper.properties', '**/gradle.lockfile', 'gradle/libs.versions.toml', 'gradle/verification-metadata.xml') }}
          restore-keys: |
            gradle-v2-${{ runner.os }}-jdk21-

      - name: Build and test
        run: ./gradlew --no-daemon test

      - name: Save Gradle dependency cache
        if: ${{ success() && steps.gradle-cache.outcome == 'success' && steps.gradle-cache.outputs.cache-hit != 'true' }}
        uses: actions/cache/save@v4
        continue-on-error: true
        with:
          path: |
            ~/.gradle/caches/modules-2
            ~/.gradle/wrapper/dists
          key: ${{ steps.gradle-cache.outputs.cache-primary-key }}
~~~

In this example:

- Restore is attempted before building. A cache miss is normal behavior.
- `continue-on-error` applies only to cache operations. If build or tests fail, the job still fails.
- The build/test step does not depend on `cache-hit`, so it always executes.
- Gradle downloads missing dependencies from repositories and still enforces locks/verification if configured.
- Save runs only after build/tests succeed and the restore step itself executed cleanly.
- Cache save cannot break the build outcome even if the cache service errors out.

The example uses dedicated GitHub Actions cache steps. Check action versions against your repository's update policy. Adjust cache keys and paths to match your toolchain, dependency setup, and exact data intended for storage. Never include directories holding secrets or auth config files in caches.

## 7. Examples with npm and Other Package Managers

With npm, the lockfile anchors deterministic dependency installs. Even when the npm cache is empty, `npm ci` still downloads required packages:

~~~yaml
- uses: actions/setup-node@v4
  with:
    node-version-file: .nvmrc
    cache: npm

- name: Install dependencies
  run: npm ci

- name: Run tests
  run: npm test
~~~

Never wrap `npm ci` in a condition requiring a cache hit. The package manager uses cached data when suitable and downloads missing parts as needed. `npm ci` enforces lockfile consistency and never modifies the lockfile during installation.

With pnpm or Yarn, choose the immutable install command matching your tool version and repository lockfile. Avoid unconstrained install commands in CI when reproducing the dependency graph is the goal.

If you want cache failures not to block the pipeline, inspect the error-handling semantics of your platform's cache action. With separate restore/save steps, cache errors can be made non-blocking; never apply error-ignoring policies to the actual dependency install or test commands.

## 8. GitLab CI and Other Platforms

GitLab CI supports defining caches per job or in shared configurations. For example:

~~~yaml
gradle-test:
  image: gradle:8-jdk21
  stage: test
  variables:
    GRADLE_USER_HOME: "$CI_PROJECT_DIR/.gradle"
  cache:
    key:
      files:
        - gradle.lockfile
        - gradle/wrapper/gradle-wrapper.properties
    paths:
      - .gradle/caches/modules-2/
      - .gradle/wrapper/dists/
    policy: pull-push
  script:
    - ./gradlew --no-daemon test
~~~

`GRADLE_USER_HOME` is placed inside the workspace so relative cache paths point directly to the directory Gradle uses. Caches are restored before `script` according to runner settings. If no matching cache exists, Gradle still resolves dependencies via repositories. When multiple jobs share caches, one job can update the cache while others use `policy: pull` to read only and reduce overwrites or contention. Actual caching behavior also depends on GitLab Runner and cache backend settings.

Other platforms offer equivalent mechanisms:

| Platform | Common Mechanism | Principle for Preserving Correctness |
| --- | --- | --- |
| GitHub Actions | `actions/cache` or built-in cache in setup actions | Never gate build/test on `cache-hit`; allow cache steps to fail |
| GitLab CI/CD | cache `key`, `paths`, `policy` | Script still resolves dependencies on cache miss |
| Azure Pipelines | Cache task with `key` and `restoreKeys` | Cache task does not replace dependency restore/install commands |
| Jenkins | Cache plugins, shared directories, or tool caches | Never assume workspace or agent always retains prior data |

Read documentation for your exact platform version to learn how cache misses, cache backend outages, read/write permissions, and sharing scopes behave. Do not copy syntax verbatim from one platform to another.

## 9. Caches Can Be Stale, Corrupted, or Untrusted

A cache existing does not guarantee its contents remain valid. A cache can contain stale data, truncated files, incompatible metadata, or unexpectedly altered contents.

### 9.1. Stale Cache

Stale caches happen when keys fail to capture all relevant inputs—for example, changing the JDK while omitting JDK version from the key, or updating a lockfile while keying caches solely on branch name.

Mitigations:

- Include critical inputs in the key.
- Use lockfiles to pin dependencies.
- Include toolchain and OS in keys when cached data depends on them.
- Use version prefixes for intentional cache refreshes.
- Never use caches to hold build configs or secrets that vary per environment.

### 9.2. Corrupted Cache

Caches can be corrupted by interrupted previous writes, filesystem glitches, or incomplete archives. When a tool detects invalid files, the pipeline must be able to discard that data and re-download or rebuild it.

For instance, if Gradle reports a corrupted artifact in the cache, identify the artifact and source repository, delete that specific cache entry or rotate the cache namespace, and re-run resolution. Never wipe arbitrary directories on shared runners indiscriminately, as other jobs may be impacted.

### 9.3. Cache Backend Unavailable

If the cache service is unreachable, pipelines can skip restore/save and proceed. Handling depends on the action and platform; with standalone cache steps, cache errors can be marked non-blocking.

Ignore errors only for cache operations. The following errors must still fail the pipeline:

- Dependencies fail to download from repositories.
- Package checksums or signatures are invalid.
- Lockfiles are out of sync.
- Builds or tests fail.
- Artifacts are not produced or fail quality gates.

If an organization must still build when both caches and public registries are unreachable, deploy a dependency proxy/mirror or internal repository with appropriate high availability and retention policies. That is a managed dependency source, not to be confused with temporary CI caches.

## 10. Securing Caches and Preventing Cache Poisoning

Caches can hold packages, metadata, or outputs produced by a pipeline. If an untrusted pipeline can write to a cache consumed by a privileged job, an attacker can try injecting malicious content into the build stream.

Protective principles:

- Never cache secrets, tokens, private keys, credential files, or contents containing sensitive data.
- Isolate caches by OS, runtime, and trust level as needed.
- Never allow pipelines from forks or unreviewed code to write to caches read by trusted release jobs.
- Restrict cache write access; read-only jobs should use read-only cache modes when supported.
- Verify packages via lockfiles, checksums, signatures, or dependency verification.
- Never execute scripts fetched from caches as though they were reviewed source code.
- Limit cache lifetimes and access rights according to organizational policy.

Caches are not security boundaries. If a job can write to a directory read back by a privileged job, treat those contents as untrusted inputs until verified.

In particular, never use caches from an untrusted pull request to supply binaries, scripts, or dependencies to jobs holding production secrets. Separate cache scopes and token privileges between testing external code and privileged deployment workflows.

## 11. Avoiding Overly Broad or Misplaced Caches

Overly broad caches inflate upload/download times, cause compatibility bugs, and mask build issues. Store only data that is genuinely expensive to re-download or regenerate.

Good candidates to cache:

- Package manager download caches.
- Appropriate Gradle/Maven dependency caches.
- Versioned tools or SDKs if not pre-installed on the runner.
- Official build caches when tasks declare deterministic inputs and outputs.

Think carefully before caching:

- Build directories holding commit- or timestamp-dependent outputs.
- Log files, temporary reports, or regenerable test data.
- An entire job workspace.
- Directories containing secrets or environment-specific configs.
- Compiler caches tied to OS/toolchain details omitted from keys.

Larger caches bring longer transfer times and higher failure probability. Measure total restore, build, save duration, and cache size. A cache hit delivers no benefit if downloading the cache takes longer than fetching the needed dependencies directly.

## 12. Measuring Effectiveness and Diagnostics

To tell whether caching genuinely helps pipelines, track:

- Cache hit rate per job and per branch.
- Restore and save durations.
- Dependency download duration on cold caches.
- Cache size and transfer throughput.
- Restore/save failure rates and errors from cache corruption.
- Build/test duration with versus without caches.

Never optimize hit rates by making keys overly broad. The goal is reusing compatible data while keeping cold builds correct. If hit rates are low yet cold builds are fast, caching may be unnecessary. If a bulky cache slows the pipeline down, narrow cached paths or adjust storage strategy.

When pipelines fail only on cache hits:

1. Re-run with a new cache namespace or cold cache.
2. Compare actual toolchain, lockfile, and package versions.
3. Check whether the key omitted any inputs.
4. Check whether cache data could have been written by an untrusted job.
5. Fix the key or cached data type, then verify both cold builds and warm builds.

When pipelines fail only on cache misses:

1. Verify that the dependency install command actually runs.
2. Check repository URLs, DNS, proxies, and credentials.
3. Verify that lockfiles are complete and in sync.
4. Check whether offline mode was enabled unintentionally.
5. Verify the runner has the required tools and write permissions on target directories.

## 13. Checklist for Cache-Independent Pipeline Correctness

**Dependency design**

- [ ] Dependencies are declared and version-pinned via manifests/lockfiles.
- [ ] Appropriate checksums, signatures, or verification mechanisms exist.
- [ ] Toolchains and package managers are explicitly specified.
- [ ] Source repositories are reachable from runners when caches are empty.

**Cache design**

- [ ] Caches contain only re-downloadable or regenerable data.
- [ ] Keys reflect OS, runtime, and relevant lockfiles.
- [ ] Restore prefixes apply only to compatible data.
- [ ] Cache misses and cache backend outages never skip builds or tests.
- [ ] Caches hold no secrets or sensitive data.
- [ ] Untrusted jobs cannot poison release job caches.

**Pipeline verification**

- [ ] Builds and tests run on both cache hits and cache misses.
- [ ] Pipelines succeed starting from an empty cache.
- [ ] Offline mode is never used outside pre-staged dependency workflows.
- [ ] Corrupted caches can be discarded and re-downloaded/rebuilt cleanly.
- [ ] Artifacts are published via separate artifact/registry mechanisms.
- [ ] Build, test, dependency verification, and quality gate failures still fail the pipeline.

## Conclusion

Caches make CI/CD faster, yet must never decide whether a pipeline is correct. Lock dependencies with manifests and lockfiles, build cache keys around compatibility factors, treat cache misses as normal execution paths, and let package managers fetch missing data. When caches are stale, corrupted, or unreachable, skip only the cache optimization; builds, tests, and quality gates must still run in full.

A trustworthy pipeline runs accurately from a cold-cache state, produces traceable artifacts, and surfaces real dependency issues. Then caches can be deleted or replaced at any moment while the CI/CD workflow preserves correctness and reproducibility.
