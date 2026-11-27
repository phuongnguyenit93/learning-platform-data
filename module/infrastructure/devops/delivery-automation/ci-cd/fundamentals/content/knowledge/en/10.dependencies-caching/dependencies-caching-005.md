# Designing Cache Keys Based on Appropriate Inputs and Environments

Caching helps CI/CD pipelines avoid re-downloading dependencies or recomputing already available results, thereby shortening build times and reducing load on package registries. However, caching is only useful when a pipeline restores the right data for the right inputs. If a cache key is too broad, a job may receive data from an incompatible environment or configuration. If a cache key is too specific, the cache is rarely reused and provides almost no benefit.

Good cache design starts by identifying **which data is reusable, which inputs alter that data, and which environments can safely share it**. Cache keys should reflect those factors while providing safe fallback mechanisms and limiting sharing scope.

## 1. What Is Pipeline Caching Used For?

A cache is temporary storage for reusing data across pipeline runs. Commonly cached data includes:

- Downloaded packages from Maven, Gradle, npm, pnpm, pip, or NuGet.
- Package repository metadata and indexes.
- Extracted dependencies or environment-specific wheels.
- Intermediate build outputs if the build cache system supports input tracking.
- Caches of compilers or static analysis tools.

For example, a Java project may need to download hundreds of dependencies on its first build. By saving the Maven local repository, subsequent runs can reuse many already downloaded packages and only fetch missing or changed dependencies.

Distinguish three types of data:

| Data Type | Purpose | Management Approach |
|---|---|---|
| Dependency cache | Retains packages and metadata to avoid re-downloading | Keyed by manifest/lockfile and environment |
| Build cache | Retains reusable intermediate computation outputs | Keyed by all inputs affecting outputs |
| Release artifact | Built product for testing or deployment | Stored as an artifact with identity, digest, and separate retention |

Caches are not the official storage for release products. When deploying or rolling back a version, always use managed, verified artifacts rather than relying on a cache directory that could be purged or replaced.

Caches are also never guaranteed to exist forever. Platforms can evict caches based on storage quotas, inactivity windows, or size limits. Pipelines must always remain capable of running from scratch when no cache exists.

## 2. What Is a Cache Key?

A cache key is an identifier the pipeline uses to look up a matching cache entry. When restoring a cache, the platform compares the current run's key against stored caches according to platform rules.

A good cache key balances two requirements:

- **Compatibility:** reuse cached data only when its contents can be used safely with the current inputs.
- **Reusability:** exclude values that change on every run if they do not affect cache contents.

Conceptually, a key can follow this structure:

~~~text
<cache-schema>-<os>-<arch>-<toolchain>-<package-manager>-<dependency-input-hash>
~~~

Example:

~~~text
deps-v3-linux-x64-jdk21-maven-<pom-hash>
~~~

Where:

- `deps-v3`: cache schema version; increment this when changing layout or invalidating old caches.
- `linux-x64`: operating system and architecture.
- `jdk21`: runtime or toolchain version.
- `maven`: package manager ecosystem.
- `pom-hash`: hash of dependency declaration files and relevant configurations.

This is a conceptual structure. Exact syntax and platform lookup behavior vary. What matters is that every component has a purpose: if it changes, cached contents may no longer be compatible.

## 3. Choosing Inputs for the Cache Key

There is no single fixed list suitable for every project. Start from the question: **if this value changes, is the current cache still usable?**

Common input groups to consider:

| Input Group | Examples | When to Include in Key? |
|---|---|---|
| Operating system | Linux, Windows, macOS | When cache contains OS-dependent data |
| CPU architecture | x64, ARM64 | When packages or binaries depend on architecture |
| Runtime | JDK 17/21, Node 20/22, Python 3.11/3.12 | When dependencies or build outputs depend on version |
| Package manager | Maven, Gradle, npm, pnpm, pip | When cache has tool-specific format or path |
| Package manager version | Maven 3.x, npm 10, pnpm 9 | When metadata or dependency resolution behavior changes |
| Manifest/lockfile | `pom.xml`, `package-lock.json`, `poetry.lock` | When the dependency set changes |
| Build configuration | profiles, compiler flags, feature flags | When they alter packages or build outputs |
| ABI and system libraries | glibc, OpenSSL, native toolchain | When cache holds native binaries tied to the environment |
| Project scope | `service-a`, `service-b` in a monorepo | When each module has separate dependencies |

### 3.1. Prefer Controlled Lockfiles or Manifests

Lockfiles are key inputs because they record resolved dependency versions. For example:

- npm: `package-lock.json` or `npm-shrinkwrap.json`.
- pnpm: `pnpm-lock.yaml`.
- Yarn: `yarn.lock`.
- Python: `poetry.lock`, `uv.lock`, or the lockfile of the active tool.
- Gradle: dependency lockfiles if the project enables dependency locking.
- Maven: typically `pom.xml`, parent POM, BOM, and relevant Maven configs; Maven does not automatically generate a standard lockfile equivalent to `package-lock.json`.

When the lockfile changes, the key should change so the pipeline does not treat the old cache as an exact match for the new dependency graph. The package manager must still perform verification and dependency resolution against the current manifest/lockfile.

With Maven, if dependencies use dynamic versions like `LATEST`, version ranges, or mutable `SNAPSHOT`s, hashing the POM alone may not fully capture repository dependency state. Pin versions, manage dependencies deliberately, and understand Maven's metadata update policy.

### 3.2. Hash Only Relevant Files

In a multi-module repository, not every cache needs to depend on every lockfile in the repository. Create separate caches per service or module so changes in module A do not invalidate module B's cache.

For example, a monorepo layout:

~~~text
repo/
├── services/
│   ├── billing/
│   │   └── package-lock.json
│   └── catalog/
│       └── package-lock.json
└── tools/
    └── package-lock.json
~~~

The cache for `billing` should hash the lockfile and configurations affecting `billing`'s dependencies. Hashing all lockfiles means changing a dependency in `catalog` also causes a cache miss for `billing`, even though the two modules are independent.

However, if a project uses a shared workspace, a root lockfile may govern dependencies for multiple modules. In that case, hashing the root lockfile makes sense. Understand how the package manager resolves workspaces before splitting keys.

## 4. Including Environment Factors in Cache Keys

The same dependency declaration can produce different cache contents on different environments.

Examples:

- Packages with native binaries can differ between Linux x64 and macOS ARM64.
- Python wheels can depend on Python version, ABI, OS, and architecture.
- Node native addons can depend on Node ABI and compiler toolchain.
- Java dependencies are generally more OS-independent, yet build caches or native libraries can still depend on JDK, OS, and architecture.
- Gradle or compiler caches can depend on tool versions, compiler flags, and build configuration.

Therefore, include environmental factors in the key that actually affect stored data. For pure Java packages fetched from Maven Central, separating caches by every environment variable may be unnecessary if the package manager and cached contents remain compatible. But if the cache holds native outputs or build outputs, use tighter keys.

An example key for a Python wheel cache might look like:

~~~text
pip-v2-linux-x64-cp312-<lock-hash>
~~~

Here `cp312` denotes CPython 3.12. If wheels include binaries depending on ABI or system libraries, consider adding corresponding environment details.

Do not mechanically stuff every environment variable into keys. Values such as job name, run ID, execution timestamp, or commit SHA constantly change the key without improving compatibility. Only add them if they genuinely affect cache contents or when you intentionally want a run-specific cache.

## 5. Cache Versioning and Intentional Invalidation

Caches need a team-controlled version component, often called a cache schema version or cache epoch.

Example:

~~~text
deps-v1-linux-x64-jdk21-<hash>
deps-v2-linux-x64-jdk21-<hash>
~~~

When changing cache directory layout, switching tools, altering storage format, or finding that old caches are no longer compatible, bump `v1` to `v2` to create a fresh namespace.

Reasons to increment the cache version:

- Changes in data format or directory layout.
- Changing package managers or dependency management approaches.
- Toolchain version upgrades affecting the cache.
- Discovering corrupted caches or invalid stale metadata.
- Needing to invalidate a group of caches after an incident.

Do not bump the cache version on every commit. Doing so destroys reusability and forces re-downloading all dependencies. Cache versions should change only for compatibility or governance reasons.

Likewise, never use timestamps in regular dependency cache keys. If a key contains execution time, every run creates a new cache and achieves nearly zero cache hits.

## 6. Exact Keys, Restore Keys, and Fallbacks

Some platforms support declaring a list of restore keys. This mechanism restores an approximate cache when an exact key match is not found.

Example primary key:

~~~text
npm-v3-linux-x64-node22-<lock-hash>
~~~

Restore keys can decrease in specificity:

~~~text
npm-v3-linux-x64-node22-
npm-v3-linux-x64-
~~~

The typical restore sequence is:

1. Search for a cache matching the exact key.
2. If none exists, try restore keys in order.
3. If a prefix match is found, restore the closest matching cache per platform rules.
4. Run the package manager to verify and download missing dependencies.
5. When needed, save a new cache under the current run's exact key.

Understand the semantics of your platform. Some systems treat restore keys as prefixes, while others have distinct scoping and lookup order rules. Do not assume all CI systems behave identically.

Fallbacks should only relax factors the package manager can handle safely. For instance, falling back across different lockfile hashes on the same OS, architecture, and runtime works if the cache only holds downloaded packages and the package manager always verifies required packages. Never fall back from Linux to Windows or from Python 3.12 to 3.8 if the cache stores environment-dependent binaries.

**Do not drop critical environment components from restore keys just to boost cache hit rates.** A high cache hit rate with incompatible data can trigger hard-to-reproduce failures.

## 7. Example: Dependency Caching with GitHub Actions

### 7.1. Maven

For Maven projects, GitHub Actions can use the built-in cache in `setup-java`:

~~~yaml
name: Java CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Java and Maven cache
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            .mvn/wrapper/maven-wrapper.properties

      - name: Verify
        run: ./mvnw --batch-mode verify
~~~

Here, the cache is tied to the Maven ecosystem and specified dependency files. For monorepos or complex Maven setups, adjust `cache-dependency-path` to include parent POMs, BOMs, or configuration files affecting dependency resolution.

The Maven local repository typically resides in `~/.m2/repository`. Do not cache the entire home directory, as that can inadvertently include user settings or sensitive data in the cache.

### 7.2. npm

For Node.js, the `setup-node` action can cache package manager data:

~~~yaml
name: Node CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: npm
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        working-directory: web
        run: npm ci

      - name: Run tests
        working-directory: web
        run: npm test
~~~

With npm, built-in caching typically stores npm's package data cache. It is not equivalent to caching the entire `node_modules` folder. `npm ci` installs dependencies from the lockfile and recreates the project's install directory cleanly. Never skip `npm ci` simply because a cache was restored.

### 7.3. Using `actions/cache` Directly

When finer control over keys is needed, use the cache action directly. The following example illustrates caching a Maven repository:

~~~yaml
- name: Restore Maven dependencies
  uses: actions/cache@v4
  with:
    path: ~/.m2/repository
    key: deps-v3-${{ runner.os }}-${{ runner.arch }}-jdk21-maven-${{ hashFiles('**/pom.xml', '.mvn/wrapper/maven-wrapper.properties') }}
    restore-keys: |
      deps-v3-${{ runner.os }}-${{ runner.arch }}-jdk21-maven-
~~~

The key includes cache schema, OS, architecture, JDK, package manager, and hashes of POMs plus the Maven Wrapper. The restore key drops only the dependency hash while preserving core environment factors.

This is an example for a dependency cache. For build caches or caches holding native binaries, you may need to include compiler version, ABI, build profile, or flags affecting output. Check your platform's cache action documentation regarding size limits, access scope, eviction, and post-job saving behavior.

## 8. Caching in Monorepos and Environment Matrices

A monorepo can contain multiple applications and dependency types. A single cache for the entire repository rarely balances reuse scope and accuracy well.

Caches can be split by:

- Service or module.
- Package manager.
- Corresponding lockfile.
- Runtime version.
- OS and architecture.
- Shared dependency groups.

For example, caches for `services/billing` and `services/catalog` can use separate keys with the same cache schema but different lockfile hashes. If both depend on a workspace root, the key should hash the root lockfile and relevant manifests.

For matrix builds, each combination of OS, runtime, or architecture may need a separate cache. For example:

| Matrix | Differentiate Cache When |
|---|---|
| Ubuntu x64 / Windows x64 | Packages or cached data depend on OS |
| Linux x64 / Linux ARM64 | Native binaries or compiler outputs exist |
| JDK 17 / JDK 21 | Build caches or tools depend on JDK |
| Node 20 / Node 22 | Native addons or caches depend on Node ABI |
| Python 3.11 / 3.12 | Wheels or caches depend on Python ABI |

Splitting caches for every matrix cell is unnecessary if cached contents are pure packages compatible across environments. Base the decision on the type of cached data, not merely the matrix name.

## 9. Caching and Supply Chain Security

Caches can contain data produced by a previous run. If an untrusted job can write to a cache that a high-privilege release job restores and executes, the cache becomes a conduit for malicious payloads.

Risks include:

- Cache poisoning by code or scripts in a pull request.
- Caches holding altered executables or scripts.
- Caches inadvertently storing tokens, credentials, or sensitive config files.
- Caches from one environment restored into an incompatible environment.
- Old caches retaining yanked dependencies or stale metadata.

Protective principles:

1. Treat caches as mutable data, not proof of provenance.
2. Never cache secrets, tokens, private keys, or credential files.
3. Isolate cache namespaces or scopes between untrusted jobs and privileged release jobs.
4. Never restore caches controlled by external pull requests into jobs with deploy or publish permissions.
5. Never execute binaries or scripts from a cache without proper verification mechanisms.
6. Use package managers and checksum/signature verification to validate dependencies.
7. Pin dependencies and tools; use lockfiles and dependency verification where supported by the ecosystem.
8. Preserve the ability to run clean builds for investigations or sensitive releases.

A cache key is not an access control mechanism. An unguessable or custom-named key does not replace platform access control policies. Understand who can write caches, who can restore caches, and whether caches are shared across branches, workflows, or repositories.

For critical releases, run a clean build without cache or using a cache generated strictly within a trusted scope, then compare outputs per policy. Although slower, this helps investigate cache poisoning or stale-data bugs.

## 10. Cache Invalidation and Handling Corrupted Caches

Cache invalidation is the process of stopping stale caches from being used or deleting caches that are no longer valid. It is one of the hardest parts of caching because caches can outlive the changes that produced them.

Approaches:

- **Rotate keys via dependency hash:** lockfile changes generate new keys.
- **Bump cache schema version:** when cache layout changes or bulk invalidation is needed.
- **Delete specific caches:** use platform management tools when cache corruption is detected.
- **Enforce retention limits:** set appropriate TTLs and storage caps.
- **Run clean builds:** bypass the cache to verify whether an error originates from the cache.

When a cache is corrupted, do not retry the exact same broken restore indefinitely. Pipelines should detect decompression or package manager errors, delete or bypass the cache per policy, and perform a clean dependency download. Log enough detail to distinguish a normal cache miss from cache corruption.

For package managers, let the dependency tool validate package integrity. Purging all caches should be an intentional action, as it increases build times and load on registries.

## 11. Measuring Cache Effectiveness

Caching does not automatically make pipelines faster. A massive cache can take longer to download and unpack than re-downloading a handful of small dependencies.

Track:

| Metric | Meaning |
|---|---|
| Exact hit rate | Percentage of runs restoring an exact key match |
| Restore hit rate | Percentage of runs finding a cache via fallback keys |
| Cache miss rate | Percentage of runs finding no cache |
| Restore duration | Time spent downloading and unpacking the cache |
| Save duration | Time spent packing and uploading the cache |
| Cache size | Storage footprint and growth rate |
| Build duration | Actual end-to-end pipeline duration |
| Dependency download volume | Data fetched from registries |
| Failure after restore | Errors occurring after restoring a cache |

Scenarios requiring investigation:

- High hit rate yet builds are no faster: cache is too large or the bottleneck lies elsewhere.
- Low hit rate: keys contain fast-changing inputs or restore keys are mismatched.
- Failures happen only on cache hits: cache is stale, incompatible, or corrupted.
- Cache size grows rapidly: unnecessary outputs are being saved or old versions are not pruned.
- Restore is slower than downloading: shrink cache scope or use the package manager's built-in cache.

Compare end-to-end job duration before and after enabling caching. The goal is reducing total runtime and system load, not maximizing cache hit numbers at all costs.

## 12. Cache Key Design Checklist

Before enabling caching or modifying cache keys, check:

- [ ] Clearly identified the type of cached data and its reuse purpose.
- [ ] Cache key includes manifests or lockfiles affecting dependencies.
- [ ] Key includes OS, architecture, and runtime when cached data is environment-dependent.
- [ ] Considered package manager version, compiler, and relevant build config.
- [ ] Monorepo module caches are separated according to actual dependencies.
- [ ] Cache schema version can be bumped on layout changes or forced invalidation.
- [ ] Excluded run IDs, timestamps, or commit SHAs if they do not affect cache contents.
- [ ] Restore keys only fall back across compatible environments.
- [ ] Package manager still verifies dependencies against the current lockfile.
- [ ] Caches contain no secrets, credentials, or sensitive data.
- [ ] Caches from untrusted jobs are never used in privileged release jobs.
- [ ] Clean builds can be triggered when caches fail or require investigation.
- [ ] Caches have size caps, retention rules, and deletion procedures.
- [ ] Metrics exist to measure cache hits, restore/save times, and net benefit.

Cache keys must accurately describe the inputs governing reusability. When keys include relevant dependencies and environments, fallbacks are bounded sensibly, and caches are isolated by trust scope, pipelines can accelerate while maintaining consistency and traceability.
