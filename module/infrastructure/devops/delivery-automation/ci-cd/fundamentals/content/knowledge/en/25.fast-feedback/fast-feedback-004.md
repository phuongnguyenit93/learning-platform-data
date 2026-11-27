# Leveraging Caches While Preserving Correctness

Caching makes CI/CD feedback faster by reusing pre-computed data or results. Instead of re-downloading every dependency, recompiling every module, or rebuilding every container image layer, pipelines can restore content from cache when the relevant inputs have not changed.

However, a cache is only an optimization. A cache hit does not prove a result is correct, and a cache miss is not a build error. If a cache key omits an important input, the pipeline may reuse stale results for new source code or a new toolchain. If caches are shared across different trust levels, an untrusted pull request could write malicious content into a cache consumed by a release pipeline. If a cache contains secrets or release artifacts, reusing it can leak data or cause the pipeline to deploy the wrong payload.

The guiding design principle is: **caches can be wiped at any time and the pipeline must still build correctly; a cache hit must be semantically equivalent to recomputing from current inputs**. Achieving this requires complete input identification, control over cache writers, integrity verification, and periodic validation via cold builds.

## 1. What Is a Cache and Where Does It Speed Up CI/CD?

A cache is a storage area for reusing data or computed outputs over time. In a pipeline, caches typically reduce repetitive work across runs:

- Downloading dependencies from package registries.
- Downloading compilers, SDKs, or toolchains.
- Compiling modules whose inputs have not changed.
- Reusing Docker/OCI image layers.
- Reusing intermediate build data.
- Reusing task outputs when the build system tracks complete inputs and outputs.
- Reusing analysis data or test fixtures generated from trusted sources.

For instance, a Java project may spend considerable time downloading Gradle dependencies on every CI run. A Gradle cache can retain downloaded dependencies and part of the build state. Subsequent runs only fetch missing or changed dependencies, cutting wait times.

Caches can live in multiple places:

- **Local cache:** directories on a runner or build machine.
- **CI cache:** cache services provided by GitHub Actions, GitLab CI, or other platforms.
- **Remote build cache:** shared across multiple runners, typically keyed by content.
- **Registry cache:** Docker/BuildKit layer caches stored in a container registry.
- **Package manager cache:** npm, pnpm, Maven, Gradle, or NuGet caches storing downloaded packages.
- **Tool cache:** pre-installed SDKs, runtimes, compilers, and executables.

Not all caches share the same semantics. Dependency caches store downloaded packages; build caches store task outputs; Docker layer caches store per-step image build results. Key generation, invalidation, and risk profiles differ for each.

## 2. A Cache Hit Is Not Proof of Correctness

A cache hit only means the system found an entry matching a key or restore rule. It does not prove that:

- The key included every input affecting the output.
- The entry was built from trusted sources and dependencies.
- The entry was not tampered with or corrupted.
- The current toolchain is compatible with the entry.
- The entry does not contain data from a different environment.
- The task can reuse outputs without skipping required side effects.

For example, suppose a build task depends on the `FEATURE_SET` environment variable, yet the cache key only includes the commit SHA. Two jobs with the same source but different `FEATURE_SET` values could receive the same cache entry even though their outputs should differ.

Another example: a cache populated by an external pull request is stored in a scope accessible to a release workflow. If a contributor can control cache contents, the release pipeline could ingest altered outputs.

Therefore, separate two questions:

1. Can a cache entry be found and restored?
2. Is that cache entry genuinely valid for the current inputs, environment, and trust level?

Only the second question directly concerns correctness.

## 3. Classifying Caches Before Designing

| Cache Type | Typical Contents | Benefit | Main Risks |
|---|---|---|---|
| Dependency cache | Downloaded packages, metadata, and checksums | Cuts dependency download time | Mutable dependencies, missing lockfiles, cache poisoning |
| Toolchain cache | SDKs, compilers, runtimes, wrappers | Cuts tool installation time | Version or architecture mismatch |
| Build cache | Task/module outputs keyed by inputs | Avoids recompilation | Undeclared inputs or non-deterministic tasks |
| Docker layer cache | Layers generated from instructions and build context | Speeds up image builds | Wrong layer keys, incomplete build context, untrusted cache sources |
| Test/result cache | Reusable test results or test data | Reduces repeated work | Skipping tests that should run or reusing stale results |
| Analysis cache | Static analysis data, indexes, metadata | Cuts analysis time | Source/config/plugin changes without cache invalidation |
| Artifact/release storage | Binaries/images/packages used for deployment | Preserves release outputs | This is an artifact store; do not treat it like an evictable/overwritable cache |

A helpful rule of thumb: caches hold reproducible data; release artifacts are outputs that must be retained, identified, and audited. Never use a cache as the sole source for production deployments.

## 4. Identifying All Inputs That Affect Cache Keys

A cache key must change whenever any input capable of altering the cached result changes. A key typically needs to consider:

- Runner operating system and architecture.
- Runtime, compiler, SDK, and build tool versions.
- Dependency lockfiles or dependency manifests.
- Build scripts, plugins, and configuration affecting outputs.
- Source/config files consumed by the task.
- Feature flags or build profiles active during the build.
- Target platform, architecture, and runtime.
- Cache schema or format version when the format changes.
- Trust level or cache scope when segregated by trust domain.

A conceptual key model:

~~~text
cache_key = hash(
    cache_format_version,
    operating_system,
    architecture,
    toolchain_versions,
    dependency_lockfiles,
    build_configuration,
    relevant_task_inputs
)
~~~

Not every cache needs every component above. A dependency download cache may not need the commit SHA because packages are identified by coordinates, version, and checksum. A build output cache requires finer-grained inputs because outputs depend on source code, toolchains, and task settings.

### 4.1. Overly Broad Keys vs. Overly Narrow Keys

| Key Design | Consequence |
|---|---|
| Key contains only branch name | Different commits may share incompatible outputs |
| Key contains only commit SHA | May omit toolchain, architecture, or build flags |
| Key hashes every file in the repository | Frequent cache misses whenever docs or unrelated files change |
| Key includes lockfiles and required toolchain | Generally appropriate for dependency caches |
| Key reflects actual task inputs | Appropriate for build caches when tasks declare full inputs |
| Key includes a random run ID | Virtually every run results in a cache miss |
| Key omits cache format version | Old entries may be misread by incompatible new logic |

Keys must balance precision with reuse rate. Never optimize for cache hits by omitting a required input; an incorrect cache hit is far more dangerous than a cache miss.

## 5. Dependency Lockfiles and Package Integrity

A dependency cache only reuses downloaded packages. Correctness must still be guaranteed by how the project pins and verifies dependencies.

### 5.1. Using Lockfiles for Dependency Graphs

Ecosystems typically provide version-locking mechanisms:

- Gradle dependency locking.
- Maven dependency versions managed via POM/BOM and explicit version rules.
- npm `package-lock.json`.
- `pnpm-lock.yaml`.
- Yarn lockfile.
- NuGet `packages.lock.json` or equivalent locking mechanisms.

Lockfiles pin the dependency graph and keep builds from resolving different versions on each run. Cache keys should change whenever lockfiles change.

### 5.2. Verifying Checksums and Package Sources

If your package manager supports integrity/checksum verification, enable and enforce it. Gradle supports dependency verification metadata for verifying checksums or signatures. npm lockfiles embed integrity metadata for each package. Maven repositories can provide checksums/signatures; configure verification policies accordingly.

A cache does not replace package verification. If a cache entry is corrupted or tampered with, the package manager must detect the mismatch against integrity metadata and re-fetch from a trusted source or fail the build.

### 5.3. Being Careful with Mutable Dependencies

Dependencies such as SNAPSHOTs, floating versions, `latest`, branch URLs, or mutable tags can point to content that changes over time. Caches can retain stale versions longer than expected.

Prefer pinned versions and lockfiles. If mutable dependencies are unavoidable, enforce freshness policies, refresh intervals, and actual checksum/version checks. Never treat a cache hit as proof that a dependency is still the latest version.

## 6. Distinguishing Dependency Cache from Build Cache

These two cache types are frequently confused:

**Dependency cache** stores downloaded packages so they do not need to be downloaded again—for example, Gradle modules cache, Maven local repository, or npm content cache.

**Build cache** stores outputs of executed tasks. If a task's inputs match, the system can restore outputs without re-executing the task.

Dependency caches generally carry lower risk when packages are pinned and checksum-verified. Build caches require that task inputs/outputs be fully declared and that task results be safely reusable.

A task that reads source files, compiler versions, and build flags without declaring an environment variable affecting output can produce an incomplete cache key. In that case, the build cache serves old outputs for a new configuration.

### 6.1. Tasks Must Declare Accurate Inputs and Outputs

In Gradle, custom tasks should declare inputs and outputs via appropriate annotations or properties. Illustrative example:

~~~kotlin
abstract class GenerateConfig : DefaultTask() {
    @get:Input
    abstract val environmentName: Property<String>

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val templateFile: RegularFileProperty

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val template = templateFile.get().asFile.readText()
        val rendered = template.replace(
            "{{environment}}",
            environmentName.get()
        )
        outputFile.get().asFile.writeText(rendered)
    }
}
~~~

This example shows `environmentName` and `templateFile` as inputs, and `outputFile` as the output. If the task also depends on locale, timezone, environment variables, tool binaries, or other files, those inputs must also be declared or removed from task logic.

Do not mark a task cacheable if it causes external side effects, depends on undeclared state, or cannot produce deterministic outputs.

### 6.2. Do Not Cache Tasks Just for Speed

Tasks such as publishing packages, sending notifications, deploying, updating databases, or calling external APIs should generally not be treated as pure output-producing tasks to cache. If a cache hit skips the task, a required side effect might never occur. If a cache miss re-runs it, the side effect might duplicate.

Separate tasks that compute outputs from tasks that perform side effects. Cache the computation; manage publishing/deployment with operation IDs, idempotency, and dedicated state tracking.

## 7. Cache Keys for Gradle

A Gradle project can often benefit from both dependency caching and build caching. The two mechanisms have distinct configurations and purposes.

Example enabling the build cache in `gradle.properties`:

~~~properties
org.gradle.caching=true
org.gradle.parallel=true
~~~

Gradle's dependency cache stores module artifacts and metadata under Gradle User Home. To preserve correctness:

- Commit the Gradle Wrapper and pin the Gradle version.
- Lock dependency versions when the project needs a stable dependency graph.
- Use dependency verification metadata for checksums/signatures.
- Ensure custom tasks declare accurate inputs and outputs.
- Do not cache outputs that depend on undeclared environment variables.
- Do not share build caches across incompatible trust domains.
- Periodically run clean builds to catch missing input declarations.

Example dependency locking:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Commands to generate or update lockfiles depend on project setup; only update locks when reviewed dependency changes are made. Never auto-generate a new lockfile on every CI run and treat it as authoritative.

## 8. Caching for Maven, npm, and pnpm

### 8.1. Maven

Maven typically stores downloaded dependencies in a local repository, defaulting to `.m2/repository`. CI can cache this directory keyed on POMs, parent POMs, BOMs, and relevant dependency configuration files.

Pay attention to:

- Pinned dependency versions and explicitly managed BOMs.
- Refresh policies for snapshot/floating versions.
- Never caching credentials or `settings.xml` files containing secrets.
- Verifying checksums/signatures per repository policy.
- Never using a local repository from an untrusted runner as a package source for releases without integrity checks.

### 8.2. npm

npm maintains a content cache; the lockfile is the critical source for reconstructing the dependency graph. `npm ci` installs strictly from `package-lock` and removes existing `node_modules` first.

Example:

~~~bash
npm ci
npm test
npm run build
~~~

CI can cache the npm download cache to reduce network time. Avoid naively caching `node_modules` across different OSes, Node versions, or native modules.

### 8.3. pnpm

pnpm uses a content-addressable store and hardlinks/reflinks to populate `node_modules`. You can cache the pnpm store keyed by OS, architecture, pnpm version, and lockfile. Use a frozen lockfile in CI so the pipeline never mutates the dependency graph.

Example:

~~~bash
pnpm install --frozen-lockfile
pnpm test
pnpm build
~~~

The store still requires package manager integrity verification. Do not allow jobs from forks to write to caches consumed by releases without proper trust boundaries.

## 9. Caching in GitHub Actions

GitHub Actions caches are typically identified by `key` and can use `restore-keys` to find close matches when an exact key does not exist.

Example caching Gradle by OS, architecture, JDK, and hashes of dependency/toolchain files:

~~~yaml
- name: Set up JDK
  uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: '21'

- name: Cache Gradle data
  uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches
      ~/.gradle/wrapper
    key: gradle-linux-x64-jdk21-LOCKFILE_AND_TOOLCHAIN_HASH
    restore-keys: |
      gradle-linux-x64-jdk21-
      gradle-linux-x64-

- name: Verify
  run: ./gradlew --no-daemon check
~~~

This example is illustrative; the `HASH` placeholder must be replaced with a hash computed from the appropriate dependency files, wrapper, verification metadata, and configuration. In real workflows, pin actions to full commit SHAs per organizational policy and explicitly specify Gradle/JDK versions.

If a restore key is broader than the exact key, the restored cache might not match all dependency inputs; Gradle still must verify and download missing pieces. Do not use broad restore keys to reuse compiled outputs unless you have a mechanism verifying their validity.

### 9.1. Exact Keys vs. Restore Keys

- Exact keys match the full key, ideal when you need cache contents corresponding precisely to the inputs.
- Restore keys act as prefix fallbacks to locate the closest match.
- Broad restore keys raise hit rates but may restore older content.
- On a cache miss, the workflow may save a new cache entry after the job succeeds depending on action/platform behavior.

Only use broad restore keys for content that can be safely verified or regenerated. For dependency caches, the package manager and lockfile/integrity checks govern package usage. For build outputs, avoid fallbacks that serve outputs from mismatched inputs.

### 9.2. Cache Scope and Pull Requests

Platform cache scoping has specific rules by branch, repository, and event. Read your platform's exact semantics. In particular, never assume pull requests from forks can write to the default branch's cache, or conversely that caches created by forks cannot be read by release workflows. Design explicit trust boundaries and verify actual permissions.

## 10. Caching in GitLab CI

GitLab CI supports declaring cache keys and paths. Example:

~~~yaml
build:
  image: gradle:8.10-jdk21
  cache:
    key:
      files:
        - gradle.lockfile
        - gradle/wrapper/gradle-wrapper.properties
      prefix: gradle-jdk21-linux
    paths:
      - .gradle/caches/
      - .gradle/wrapper/
  script:
    - ./gradlew --no-daemon check
~~~

This is a simple example; adjust actual lockfiles and Gradle User Home paths to match your image and runner. When multiple jobs share a cache, understand GitLab's cache upload/download behavior and policies. Jobs that only need to read the cache can use `pull` policy; designated cache-updating jobs can use `pull-push`.

Do not let every job concurrently write to a shared cache key if contents could become inconsistent or a runner could upload partial state. You can dedicate a warm-cache job or use a content-addressed, write-once remote build cache.

## 11. Docker BuildKit Layer Caching

Docker builds split execution into layers. An unchanged instruction and build context can reuse a previously built layer. Ordering your Dockerfile thoughtfully prevents source code edits from invalidating dependency download layers.

Example:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace

COPY gradlew .
COPY gradle/ gradle/
COPY settings.gradle.kts build.gradle.kts ./
COPY */build.gradle.kts ./

RUN ./gradlew --no-daemon dependencies

COPY . .
RUN ./gradlew --no-daemon clean build

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/app/build/libs/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

This is a conceptual structure; dependency commands and build script copies must be adapted for your multi-module layout. Key points:

- Copy dependency and build configuration files before source code to preserve dependency layers when source changes.
- Use `.dockerignore` to exclude `.git`, build outputs, local caches, and unnecessary files from the build context.
- Pin base images by version or digest when reproducibility is required.
- Never `COPY` secrets or credential files into an image.
- Never pass secrets via build arguments.
- Verify that layer caches come from trusted sources and match the target platform.

### 11.1. Registry Cache with BuildKit

BuildKit can import/export cache via a container registry:

~~~bash
docker buildx build \
  --cache-from type=registry,ref=registry.example.com/cache/orders:buildkit \
  --cache-to type=registry,ref=registry.example.com/cache/orders:buildkit,mode=max \
  --tag registry.example.com/orders:3.2.0 \
  --push .
~~~

Adjust syntax to fit your builder, registry, and platform. A registry cache is not a release artifact. Restrict push permissions to the cache; never allow untrusted workflows to write to a cache read by release pipelines. Separate cache refs by branch or trust domain, and only promote or seed caches from verified sources.

## 12. Cache Poisoning and Trust Boundaries

Cache poisoning happens when cache contents are written or altered by an untrusted source, and another pipeline later consumes those contents as if they were trustworthy.

Example scenario:

1. A pull request from a fork runs a workflow with permission to write to a shared cache key.
2. The job populates a cache containing tampered dependencies or build outputs.
3. A workflow on the release branch restores the same cache.
4. The build/release consumes malicious content without recognizing who produced the cache.

Protective measures:

- Separate caches by trust domain: fork/untrusted PRs, internal branches, protected branches, and releases.
- Never allow fork workflows to write caches that release pipelines can restore.
- Never use caches from unprotected branches for production publishing/deployment.
- Restrict write permissions on caches and registry caches.
- Use exact keys and verify content/integrity.
- Never cache executables or build outputs from untrusted sources and then run them in jobs holding secrets.
- Never allow caches to become a channel for leaking secrets across jobs or repositories.
- Track cache provenance and cache format versions.

### 12.1. Cache Scope Is Not an Absolute Security Boundary

A key prefixed with `main-` does not automatically guarantee only `main` can write to it. Check actual read/write permissions and scoping rules of your cache service. Likewise, do not assume a cache in a separate repository is safe if untrusted workflows can push to it.

### 12.2. Caches and Untrusted Code

A pull request can modify build scripts, test code, plugins, or dependencies. If a job running untrusted code also holds secrets or write access to shared caches, that code could exfiltrate secrets or poison the cache. Separate unprivileged validation jobs (no secrets) from privileged publish/deploy jobs, using dedicated runners and cache scopes.

## 13. Never Cache Secrets or Sensitive Data

Caches can persist longer than a single job lifecycle and be restored by other permitted jobs. Therefore, never place into a cache:

- Access tokens, private keys, cloud credentials, or registry passwords.
- Configuration files containing secrets.
- Production `.env` files or sensitive kubeconfigs.
- Database dumps containing real personal data without appropriate controls.
- Logs containing tokens, request bodies, or customer information.
- Entire workspaces when you do not know everything inside them.

With Docker BuildKit, use dedicated secret mounts for steps requiring authentication instead of `ARG`, `ENV`, or `COPY`ing secrets into layers. Secret mounts are designed not to become part of image layers when used properly; still ensure build commands do not print or copy secret contents into outputs.

Treat caches as storage with their own access controls and retention policies. If you suspect a cache holds a secret, purge/revoke the affected cache scope and rotate the exposed credentials; deleting source files alone does not remove already-cached copies.

## 14. Invalidation: When Must a Cache Be Invalidated?

A cache must be invalidated whenever inputs or semantics change such that old entries are no longer valid.

Common cases:

- Lockfiles or dependency coordinates change.
- JDK, Node.js, compiler, SDK, or build tool versions change.
- OS/architecture or target platform changes.
- Build scripts, plugins, or compiler flags change.
- Cache serialization format changes.
- New task inputs are added or task logic changes.
- Base images or Dockerfile instructions change.
- Dependency verification metadata or policies change.
- Poisoning, corruption, or untrusted origin is suspected.
- A bug reveals that an earlier cache key omitted a required input.

### 14.1. Version Prefixes for Cache Formats

When cache structure changes, embed a version in the key:

~~~text
gradle-cache-v3-linux-x64-jdk21-<dependency-hash>
docker-cache-v2-orders-<build-input-hash>
frontend-cache-v4-node22-<lockfile-hash>
~~~

Version prefixes allow intentional transitions without guessing whether old entries remain compatible. Never use a new prefix merely to hide a broken key without fixing the missing input.

### 14.2. Targeted Invalidation

Do not purge every cache whenever a build fails. First determine whether the failure came from dependencies, the toolchain, task outputs, the registry, or source code. Invalidate only the relevant cache and keep valid caches intact to avoid overloading package registries and inflating build times.

If cache poisoning or an integrity violation is suspected, make the purge scope broad enough to prevent any affected entry from being reused. Then run a clean build from trusted sources and re-verify.

## 15. Cache Misses and Fallbacks Must Be Safe

A cache may be absent due to expiration, eviction, a new runner, or a changed key. The pipeline must still succeed by fetching or recomputing from authoritative sources.

A safe pipeline should:

- Never fail solely because of a cache miss.
- Never depend on a cache as the sole store of source files.
- Fall back to fetching dependencies from trusted registries.
- Be able to rebuild outputs from source and locked inputs.
- Verify checksums/signatures after downloading.
- Never use a stale cache without proving compatibility.
- Report cache hit/miss metrics for observability, without treating misses as quality failures.

Caching is a speed optimization; source code, lockfiles, toolchains, and artifact stores are the sources of truth.

## 16. Caching and Build Reproducibility

A reproducible build means identical source and controlled inputs yield equivalent or byte-identical outputs according to defined criteria. Caching does not create reproducibility by itself, and it can hide non-reproducible builds if pipelines perpetually restore old outputs.

To keep builds reproducible:

- Pin dependencies and toolchains.
- Record OS, architecture, locale/timezone, and build flags when they affect outputs.
- Eliminate unnecessary timestamps/randomness or control seeds.
- Never download unversioned binaries from mutable URLs.
- Use build scripts with deterministic inputs and outputs.
- Record source revisions and artifact digests.
- Run clean builds without caches periodically.
- Compare checksums or metadata when byte-for-byte reproducibility is required.

Some artifacts embed timestamps or variable metadata, so two builds may not share identical digests even when semantically equivalent. In those cases, define clear comparison criteria: byte-level, package contents, API behavior, or test outcomes. Never claim reproducibility based solely on a cache hit.

## 17. Cache Concurrency and Safe Cache Writes

Multiple jobs may compute the same key or update a cache nearly simultaneously. If the cache service permits overwrites, a slower job could overwrite a newer entry with stale data. If a cache is uploaded before a task finishes, the entry could be incomplete.

Core principles:

- Use immutable input-based keys; avoid multiple jobs writing inconsistent contents to the same key.
- Prefer content-addressed caches or write-once keys.
- Publish caches only after the cache-producing step finishes and passes verification.
- Use locking or atomic publishing when backends update an index or manifest.
- Separate read-only cache consumers from cache writers if supported by the platform.
- Never let cancelled jobs upload partial caches.
- Version cache schemas so older readers cannot misinterpret new formats.

For distributed caches, metadata and content should be written atomically or guarded by a completion manifest. Incomplete entries should be ignored and recomputed.

## 18. Verifying Correctness with Cold Builds

One effective way to catch cache keys with missing inputs is periodically running a build with caching disabled. Cold builds verify that the project can still be built cleanly from source and authoritative dependencies.

Practices to adopt:

- Run a clean build pipeline daily or weekly.
- For critical releases, run validation on a fresh runner or clean cache namespace.
- Compare test results, artifact metadata, and digests against defined criteria.
- If a cached build and a cold build produce different outcomes, treat it as a correctness bug and investigate.
- After upgrading toolchains or build scripts, run a cold build before opening a new cache for releases.
- Retain logs and input manifests from both runs for comparison.

Cold builds do not need to run on every commit if cost is high. Schedule them periodically, on release candidates, or for sensitive changes. What matters is that caches never mask a broken clean build.

## 19. Measuring Cache Effectiveness Without Compromising Reliability

Useful metrics:

- Cache hit rate by cache type and key namespace.
- Cache miss rate and miss reasons.
- Dependency download duration before vs. after caching.
- Build duration p50/p95.
- Cache size and restore/save duration.
- Integrity or checksum failure rates.
- Frequency of manual invalidations.
- Number of cold builds revealing discrepancies against cached builds.
- Share of cache entries originating from trusted sources.
- Storage and egress costs.

Do not optimize solely for cache hit rate. A cache with a 99% hit rate that occasionally serves wrong outputs is more dangerous than a 70% hit rate cache that always tracks exact inputs. Measure both time saved and output correctness.

Comparison example:

| Metric | Without Cache | With Cache |
|---|---:|---:|
| Dependency download | 4 minutes | 25 seconds |
| Unchanged build tasks | 6 minutes | 1 minute |
| Total CI duration | 12 minutes | 5 minutes |
| Clean build verification | Pass | Pass |
| Integrity checks | Enabled | Enabled |
| Conclusion | Baseline | Faster while preserving verified results |

Numbers in the table illustrate how to evaluate caching, not a universal benchmark.

## 20. Cache Design Process for a Pipeline

1. **Define the goal:** reduce dependency download time, compilation, image builds, or analysis?
2. **Choose cache types:** dependency, toolchain, build output, Docker layer, or analysis.
3. **Identify authoritative sources:** lockfiles, source code, toolchain manifests, registries, and build configs.
4. **List all inputs:** OS, architecture, tool versions, lockfiles, task inputs, and relevant feature flags.
5. **Design keys and versions:** keys change whenever inputs or cache format change; avoid branch-only keys.
6. **Set trust boundaries:** define who can read and write caches; separate forks, internal branches, protected branches, and releases.
7. **Enable integrity verification:** checksums/signatures, lockfiles, provenance, or appropriate metadata.
8. **Design safe fallbacks:** on a cache miss, download or recompute from trusted sources.
9. **Isolate side effects:** never cache publish, deploy, migration, or notification steps as pure computations.
10. **Observe:** hit/miss rates, durations, sizes, origins, integrity checks, and cold-build outcomes.
11. **Rehearse invalidation:** change toolchain, lockfile, or cache format to confirm keys rotate as expected.
12. **Verify periodically:** run clean builds and compare against cached build results.

## 21. Common Anti-Patterns

| Anti-Pattern | Risk | Better Practice |
|---|---|---|
| Branch-only keys | Consuming outputs from a different commit | Key on inputs and toolchains |
| Caching `node_modules` across all environments | Incompatible native binaries or dependencies | Key on OS, architecture, runtime, and lockfile; consider caching package store |
| Restoring build outputs via overly broad prefixes | Stale outputs mismatched with current inputs | Use exact keys or build caches with input tracking |
| Using caches as release artifacts | Cache can be evicted or overwritten | Publish immutable artifacts to a registry |
| Allowing forks to write release caches | Cache poisoning | Separate trust domains and write permissions |
| Caching the entire workspace | May store secrets, stale outputs, and unrelated files | Cache only required paths |
| Skipping lockfiles/checksums | Dependencies change while cache still hits | Pin versions and verify integrity |
| Caching tasks with side effects | Hits skip actions or misses duplicate them | Separate computation tasks from side effects |
| Using mutable tags as build inputs | Base image changes without key changing | Pin versions/digests |
| Never running cold builds | Missing cache-key inputs stay hidden | Periodic cold-build verification |
| Purging all caches on any error | Inflates build time and registry load | Investigate first, then invalidate selectively |
| Unversioned cache formats | New readers misparse old entries | Include cache namespace/version |

## 22. Checklist for Preserving Correctness When Caching

### Inputs and Keys

- [ ] Caches are classified as dependency, toolchain, build output, Docker layer, or other.
- [ ] Keys include every input affecting cache contents.
- [ ] Keys account for OS/architecture/toolchain where needed.
- [ ] Lockfiles and build configurations act as input/version signals.
- [ ] Cache format versioning and invalidation rules are defined.
- [ ] Random run IDs or bare branch names are not used in place of input identity.

### Integrity and Trust

- [ ] Dependencies are pinned/locked and checksums/signatures are verified.
- [ ] Cache writers and readers are restricted by trust domain.
- [ ] Forks/untrusted PRs cannot write caches consumed by release pipelines.
- [ ] Caches do not inadvertently contain secrets, tokens, or sensitive data.
- [ ] Release artifacts are stored separately with digests and provenance.
- [ ] Corrupted or unverified cache entries are discarded and recomputed.

### Builds and Side Effects

- [ ] Tasks using build caches declare complete inputs and outputs.
- [ ] Non-deterministic tasks or tasks with side effects are not mis-cached.
- [ ] Publishing, deployment, migrations, and notifications are managed via dedicated operation state.
- [ ] Cache misses fall back safely to downloading/recomputing from authoritative sources.
- [ ] Broad restore keys are used only for safely verifiable content.
- [ ] Concurrent cache writes do not produce partial entries or unintended overwrites.

### Verification and Operations

- [ ] Cold builds run periodically or before critical releases.
- [ ] Cached builds and clean builds are compared against clear criteria.
- [ ] Hit/miss rates, durations, integrity failures, and cache origins are monitored.
- [ ] Procedures exist to invalidate caches when changing toolchains, lockfiles, task inputs, or cache formats.
- [ ] The entire cache can be purged and the pipeline still builds and releases correctly.
- [ ] Runbooks document which caches may be restored in jobs holding secrets or deploy permissions.

Caching speeds up CI/CD by reusing the right data for the right inputs. Correctness comes from lockfiles, controlled toolchains, complete input/output declarations, checksums/provenance, and clear trust boundaries; caches merely avoid recomputing what has already been verified. Treat caches as disposable, reproducible storage, keep them separate from release artifacts, never cache side effects, and use cold builds to ensure optimizations never mask bugs.
