# Dependency Caching in CI/CD

## 1. What is a dependency cache?

A **dependency cache** is temporary storage for packages, libraries, metadata, and distribution files that a build tool has downloaded or processed. A pipeline restores the cache in subsequent runs to reduce the time spent downloading dependencies from Maven Central, the Gradle Plugin Portal, the npm registry, or internal repositories.

Examples in Java projects:

- Maven stores downloaded dependencies and plugins in its local repository, defaulting to `~/.m2/repository`.
- Gradle stores artifacts and metadata in the Gradle User Home, typically `~/.gradle/caches`.
- Maven Wrapper and Gradle Wrapper download build tool distributions into their own wrapper directories.
- npm stores package metadata and tarballs in its cache, defaulting to `~/.npm` on Linux/macOS.

Caching is useful on ephemeral CI runners, where each job starts in a clean environment. Without a cache, each build may have to re-download hundreds of dependencies and plugins.

Caching is a performance optimization, not a requirement for a build to run correctly. A pipeline must still be able to build on a cache miss, when the cache is deleted, or when the cache service is temporarily unavailable.

## 2. How does caching work in a pipeline?

A pipeline with dependency caching typically goes through the following cycle:

1. Check out source code and lockfiles.
2. Set up the JDK, build tool, and environment.
3. Generate a cache key from the operating system, architecture, build tool, and dependency declaration files.
4. CI searches for a matching cache and restores the configured paths.
5. Maven/Gradle/npm checks its internal cache and only downloads missing components or those that need updating.
6. The job compiles, tests, and packages as usual.
7. When the job completes according to the CI policy, the cache is saved for use in subsequent runs.

A **cache hit** means a matching cache was found. A **cache miss** means no matching cache was found; the build tool will download dependencies from the repository, and CI may save a new cache after the job succeeds.

A cache miss is a normal state, not a build error. The build must be able to reconstruct the environment from source and lockfiles.

## 3. Distinguishing dependency cache, build cache, and artifact

| Type | Contents | Purpose |
|---|---|---|
| Dependency cache | Downloaded JARs, POMs, package tarballs, metadata | Avoid downloading dependencies repeatedly |
| Build cache | Computed task results, e.g., compile or transform outputs | Avoid re-running tasks when inputs have not changed |
| Artifact | JAR/WAR, test reports, coverage reports, logs produced by a job | Store run outputs or pass data between jobs |

`~/.m2/repository` is Maven's dependency cache. `target/app.jar` produced by a job is an artifact. The Gradle build cache stores task outputs and can reuse compilation results; it is distinct from the dependency cache.

In GitLab CI, use `cache` for dependencies downloaded from the Internet and `artifacts` to pass build files/test reports between stages. GitHub Actions has a similar distinction between caches and workflow artifacts.

Do not use the cache as the sole storage location for release builds. Caches can expire, be evicted, or fail to be restored in the next run.

## 4. Cache paths and key-generation files

| Tool | Common cache path | Files to include in cache key |
|---|---|---|
| Maven | `~/.m2/repository` | `pom.xml`, module POMs, Maven Wrapper properties, extensions |
| Gradle | `~/.gradle/caches` | `build.gradle`, `build.gradle.kts`, `gradle.properties`, wrapper properties, version catalog, `gradle.lockfile` |
| Maven Wrapper | `~/.m2/wrapper/dists` | `.mvn/wrapper/maven-wrapper.properties` |
| Gradle Wrapper | `~/.gradle/wrapper` | `gradle/wrapper/gradle-wrapper.properties` |
| npm | `~/.npm` | `package-lock.json` or `npm-shrinkwrap.json` |
| Yarn | Yarn cache or offline mirror | `yarn.lock` |

Actual paths depend on the OS, user home, and runner configuration. You can check them using `mvn help:evaluate`, `gradle properties`, or `npm config get cache`.

Do not arbitrarily cache the entire home directory. Only include the necessary directories in the cache to avoid accidentally storing credentials, logs, temporary files, or data from other jobs.

## 5. Designing cache keys

The cache key determines when a cache can be reused. A good key changes whenever dependencies or the environment make the cache incompatible.

Common structure:

~~~text
<schema>-<os>-<arch>-<build-tool>-<tool-version>-<dependency-hash>
~~~

Components:

- **Schema/version:** proactively invalidate old caches when changing storage layout or format.
- **OS and architecture:** necessary when packages contain platform-specific native binaries.
- **Build tool/version:** avoid using incompatible metadata caches across tool versions.
- **Dependency hash:** hash of the lockfile or dependency declaration files to create a new cache when dependencies change.

Example manual key for Maven on GitHub Actions:

~~~yaml
key: maven-v2-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('**/pom.xml', '.mvn/wrapper/maven-wrapper.properties') }}
~~~

Do not use a single fixed key across all commits and branches if dependencies can change. In a monorepo, include every file that affects module dependency resolution in the key. Hashing only the root POM is insufficient if child POMs can change dependencies independently.

## 6. Lockfiles and build reproducibility

Caches and lockfiles solve two different problems:

- Caching reduces dependency download and resolution time.
- Lockfiles or dependency locking pin the exact dependency versions used.

If you only use caching without locking dependencies, builds may pick up newer versions from version ranges, dynamic versions, or SNAPSHOTs after metadata expires.

- Maven: declare explicit versions in `pom.xml`, use `dependencyManagement` for centralized version management; avoid version ranges in release builds.
- Gradle: use dependency locking and commit `gradle.lockfile` or lockfiles under `gradle/dependency-locks/`.
- npm: commit `package-lock.json` and use `npm ci` in CI.

Gradle supports generating lock state with:

~~~bash
./gradlew dependencies --write-locks
~~~

Dependency locking can be enabled with:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Lockfiles must be reviewed like source code. When upgrading dependencies, inspect the diff to see which libraries changed and which transitive dependencies are affected.

## 7. Maven dependency cache

Maven stores downloaded artifacts in the local repository, defaulting to:

~~~text
~/.m2/repository
~~~

The local repository can contain JARs, POMs, metadata, Maven plugins, and plugin dependencies. Maven allows changing the local repository via settings or a system property:

~~~bash
mvn -Dmaven.repo.local=.m2/repository verify
~~~

In CI, you can place the repository inside the workspace so GitLab Runner can cache the path:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$CI_PROJECT_DIR/.m2/repository" verify
~~~

Useful commands:

~~~bash
mvn -B -ntp dependency:go-offline
mvn -B -ntp verify
mvn -o -B -ntp verify
mvn -U -B -ntp verify
mvn dependency:tree
~~~

- `dependency:go-offline` pre-downloads required dependencies and plugins.
- `verify` runs the verification phases of the Maven lifecycle.
- `-o` runs offline, using only data already present in the local repository.
- `-U` forces a check for updates on SNAPSHOTs and missing artifacts according to Maven's update mechanism.
- `dependency:tree` displays the resolved dependency tree.

Offline mode verifies that the cache is complete for a specific build. If a plugin or artifact is missing, the build fails; run online again to download the missing parts.

Do not include `~/.m2/settings.xml` in the cache. This file may contain usernames, passwords, server credentials, private keys, or internal mirrors.

## 8. Gradle dependency cache

The default Gradle User Home is `~/.gradle`. The dependency cache is primarily located under:

~~~text
~/.gradle/caches/modules-2
~~~

Gradle maintains two main types of data:

- A file store containing downloaded artifacts, such as JARs, POMs, and metadata files.
- A metadata store containing module resolution results, dynamic versions, artifacts, and the repositories that provided the data.

Gradle stores artifacts by checksum and records the source repository. The same dependency coordinates returning different binaries from two repositories can be handled as separate artifacts. This storage approach helps prevent binaries from overwriting each other across sources.

Common commands:

~~~bash
./gradlew build
./gradlew --offline build
./gradlew --refresh-dependencies build
./gradlew dependencies
./gradlew dependencyInsight --dependency commons-lang3
~~~

- `--offline` uses only dependencies already in the cache; the build fails if any artifact is missing.
- `--refresh-dependencies` instructs Gradle to re-check metadata and artifacts, though it does not necessarily re-download every file if checksums have not changed.
- `dependencyInsight` explains why a particular version was selected for a specific dependency.

Gradle handles dynamic versions and changing modules, such as SNAPSHOTs, based on cache expiration times. By default, resolution results for these dependency types are typically cached for 24 hours. When using frequently changing dependencies, understand the TTL and refresh policies clearly.

The Gradle cache uses file locking. Multiple processes can only access it concurrently safely when they can coordinate via the locking mechanism. Do not mount a shared writable Gradle cache across multiple independent containers building concurrently; in CI, prefer restoring a separate cache archive per job or using a dedicated caching mechanism supported by Gradle.

## 9. npm cache in accompanying JavaScript pipelines

A Java project may have a frontend build run by npm. npm stores a content-addressable cache, defaulting to `~/.npm`.

In CI, cache downloaded packages while still installing dependencies according to the lockfile:

~~~bash
npm ci --cache .npm --prefer-offline
~~~

`npm ci` requires an existing `package-lock.json` or `npm-shrinkwrap.json`, checks that the lockfile matches `package.json`, deletes any existing `node_modules` before installing, and does not update the lockfile.

Verify the cache:

~~~bash
npm cache verify
~~~

npm automatically verifies integrity when writing and reading the cache. `npm cache clean --force` is usually not needed to fix common issues; first run `npm cache verify` and read the specific error.

In GitLab, cache npm by lockfile using a path inside the workspace:

~~~yaml
cache:
  key:
    files:
      - package-lock.json
  paths:
    - .npm/
script:
  - npm ci --cache .npm --prefer-offline
~~~

Do not cache `.npmrc` if the file contains registry tokens or credentials.

## 10. GitHub Actions: caching Maven with setup-java

`actions/setup-java` supports dependency caching for Maven, Gradle, and sbt. Configuring `cache` avoids having to manually write cache paths and keys.

Example Maven workflow:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '24'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            **/.mvn/wrapper/maven-wrapper.properties
            **/.mvn/extensions.xml
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Build and test
        run: mvn -B -ntp verify
~~~

In this example:

- `cache: maven` enables Maven dependency caching.
- `cache-dependency-path` specifies the files used to generate the hash; useful in monorepos.
- `cache-read-only` allows pull requests to restore the cache without saving new cache changes.
- `mvn -B -ntp verify` runs Maven in batch mode and suppresses transfer progress output.

Setup Java manages dependency caches, Maven/Gradle Wrapper caches, and JDK caches as separate entries. The internal key includes OS, architecture, package manager, and the hash of dependency files. For monorepos, ensure all POMs or build files affecting dependencies are included in the key.

To cache Maven dependencies more thoroughly, you can run:

~~~bash
mvn -B -ntp dependency:go-offline dependency:resolve-plugins
~~~

For Gradle, change `cache: maven` to `cache: gradle` and run `./gradlew --no-daemon build`. Files used for hashing can include `**/*.gradle*`, `gradle.properties`, `gradle-wrapper.properties`, and version catalogs.

## 11. GitHub Actions: manual cache keys and restore keys

When you need custom control over cache paths or keys, you can use the cache action directly. Separating restore and save steps allows jobs to only read or only seed the cache.

Example:

~~~yaml
- name: Restore Maven dependencies
  id: maven-cache
  uses: actions/cache/restore@v4
  with:
    path: ~/.m2/repository
    key: maven-v2-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('**/pom.xml') }}
    restore-keys: |
      maven-v2-${{ runner.os }}-${{ runner.arch }}-

- name: Build
  run: mvn -B -ntp verify

- name: Save Maven dependencies
  if: steps.maven-cache.outputs.cache-hit != 'true'
  uses: actions/cache/save@v4
  with:
    path: ~/.m2/repository
    key: maven-v2-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('**/pom.xml') }}
~~~

`restore-keys` allows finding a cache with a matching prefix when the primary key has no exact match. GitHub selects the most recent cache matching the prefix. A cache is created under the new key after the job succeeds; existing cache entries cannot be modified in place.

Order restore keys from most specific to broadest. An overly broad prefix can restore an outdated, unsuitable cache and increase verification time. The package manager still has to verify that dependencies match the lockfile or POM.

If `setup-java` already has caching enabled, do not add another cache action for the same directory unless there is a specific requirement. Having two mechanisms write to the same path makes the pipeline harder to understand and wastes compression/decompression time.

## 12. GitLab CI: caching the Maven repository

GitLab Runner caches paths relative to the project workspace. You can point the local Maven repository to a directory inside the project:

~~~yaml
stages:
  - build

maven-build:
  image: maven:3.9.12-eclipse-temurin-24
  stage: build
  cache:
    key:
      files:
        - pom.xml
        - .mvn/wrapper/maven-wrapper.properties
    paths:
      - .m2/repository/
    policy: pull-push
  script:
    - mvn -B -ntp -Dmaven.repo.local="$CI_PROJECT_DIR/.m2/repository" verify
~~~

The key is based on the contents of the POM and Maven Wrapper properties. When dependencies or the wrapper change, GitLab generates a new key. For multi-module Maven projects, include module POMs in the key; you can generate a key from the hash of all POMs or use a per-module strategy.

`policy: pull-push` is the default: the job downloads the cache at the start and uploads changes at the end. When multiple parallel jobs share the same cache, you can use one seed job with `policy: push` and have test jobs use `policy: pull` to avoid multiple jobs uploading simultaneously.

## 13. GitLab CI: caching Gradle

The Gradle User Home can be placed inside the project so GitLab Runner can cache it:

~~~yaml
variables:
  GRADLE_USER_HOME: "$CI_PROJECT_DIR/.gradle-user-home"

gradle-build:
  image: gradle:9.2.1-jdk24
  stage: build
  cache:
    key:
      files:
        - gradle/wrapper/gradle-wrapper.properties
        - gradle/libs.versions.toml
    paths:
      - .gradle-user-home/caches/modules-2/
      - .gradle-user-home/wrapper/dists/
    policy: pull-push
  script:
    - gradle --no-daemon build
~~~

This example caches dependency metadata/artifacts and the Gradle Wrapper distribution. If the project does not use a version catalog, replace that key file with a lockfile or appropriate build file.

GitLab `cache:key:files` supports a limited number of files per key definition. For monorepos with many build files, generate a key from a combined manifest or split caches by module instead of omitting dependency files.

Do not cache the entire Gradle User Home unnecessarily. Avoid caching daemon state, logs, credentials, and temporary data. With container-based runners, each job should receive its own cache copy rather than sharing a live writable cache across independent processes.

## 14. Caching in monorepos and multi-job pipelines

A monorepo may contain multiple Maven/Gradle applications, frontend modules, and multiple lockfiles. If everything shares a single broad key, a small change can invalidate the cache for the entire repo or cause modules to use the wrong cache.

Some strategies:

- Per-module keys: `backend-maven-<hash pom>`, `frontend-npm-<hash lockfile>`.
- Combined keys: compute the hash of all POMs, Gradle build files, version catalogs, and lockfiles.
- Per-platform keys: include OS/architecture when dependencies contain native binaries.
- Per-toolchain keys: include Maven/Gradle major or JDK major versions if the cache depends on format/tool version.
- Use one cache-seeding job and multiple read-only jobs to reduce duplicate uploads.

With a GitHub Actions matrix, one job can download dependencies upfront and matrix jobs can use the cache in read-only mode. This reduces cache writes and repository load.

For Gradle, if you need to cache task outputs across multiple jobs or runners, look into Gradle Build Cache/Develocity. Dependency caching only handles dependency resolution; it does not automatically share task compilation/test results.

## 15. Caching and supply chain security

Caches can become a data conduit between different workflows. A cache created by a less-trusted job could be restored by a workflow with higher privileges. If the cache contains modified executables, scripts, or build outputs, subsequent workflows might execute unintended code.

Security principles:

- Never cache secrets, access tokens, signing keys, private keys, or settings files containing passwords.
- Never include `.m2/settings.xml`, `.npmrc` files with tokens, `gradle.properties` containing credentials, or `.env` in the cache.
- Review which branches, pull requests, and workflows share a cache.
- Use read-only caches for pull request jobs or matrix consumers where appropriate.
- Let trusted workflows on the default branch create/update shared caches.
- Do not enable cache writes for workflows processing untrusted source if that cache will be restored by higher-privilege workflows.
- Treat restored cache contents as untrusted input that needs verification.
- Use lockfiles, checksums, and dependency verification to validate artifacts.

GitHub restricts cache permissions by branch/ref and certain trigger types. Less-trusted workflows may be restricted to reading caches from the default branch only. Do not proactively enable write mode for `pull_request_target`, `issue_comment`, or `workflow_run` without assessing cache poisoning risks.

Caching does not replace dependency verification. Gradle can use `gradle/verification-metadata.xml` to verify artifact checksums or signatures. Prefer SHA-256/SHA-512 and review checksum sources; checksums from unverified sources do not prove an artifact is trustworthy.

## 16. Dependency caching does not guarantee reproducible builds

A reproducible build requires the same source, dependency versions, toolchain, configuration, and environment to produce consistent results. Caching only speeds up downloading or reusing data.

Practices that support reproducible builds:

- Commit lockfiles and wrapper properties.
- Pin JDK, Maven/Gradle, and plugin versions.
- Avoid version ranges, dynamic versions, or SNAPSHOTs in release pipelines unless there is an explicit refresh policy.
- Use dependency verification or checksum policies.
- Control which repositories/mirrors are allowed.
- Keep build scripts and dependency declarations in version control.
- Periodically test the pipeline with a cacheless run.
- Do not let a build succeed solely because the runner machine has leftover files not declared in source.

A cache hit should not alter the set of resolved dependencies. If a clean runner build fails while a cached runner succeeds, it is a sign that the build depends on state outside the source.

## 17. Cache invalidation and cleanup

Changing the cache key when dependencies or the environment change is the standard invalidation mechanism. You can bump the schema version, e.g., from `maven-v2` to `maven-v3`, when changing cache paths, compression, tool versions, or structure.

When a cache becomes invalid:

- Maven: use `-U` to check SNAPSHOTs and artifacts that need updating; only delete specific artifacts in the local repository if a cached file is confirmed corrupt.
- Gradle: use `--refresh-dependencies` to re-check metadata/artifacts; the cache is self-managed and has built-in cleanup for unused old artifacts.
- npm: run `npm cache verify` before considering clearing the cache.
- GitHub Actions: generate a new key when a new cache entry is needed; existing cache entries cannot be modified in place.

Do not wipe the entire cache just because one build is slow. First check whether it is a cache miss, key mismatch, slow repository, stale metadata, expired credentials, or an unwarmed dependency.

Caches have platform-imposed size limits and retention policies. Do not treat a cache as durable storage; if evicted, the pipeline must be able to re-download dependencies.

## 18. Measuring cache effectiveness

To know whether caching helps, measure before and after enabling the cache on comparable workloads.

Useful metrics:

- Cache restore time.
- Uploaded and downloaded cache size.
- Cache hit rate and miss rate.
- Dependency resolution time.
- Total build/test time.
- Network transfer and number of repository requests.
- Job failure rate due to cache or repository issues.
- Cache size by branch and over time.

A larger cache is not always faster. If compressing/decompressing 1 GB takes longer than downloading the needed dependencies, caching can slow the pipeline down. Choose small, stable paths; exclude temporary files, daemons, logs, and quickly regenerable data.

Compare median and p95 durations across multiple runs. A single cache hit is not enough to conclude that the pipeline is faster.

## 19. Troubleshooting

### No cache hit

Check whether the key changed, dependency files are at the expected paths, the cache path existed at save time, OS/architecture match, and whether the cache expired or was evicted.

### Cache hit, yet Maven still downloads dependencies

Check the local repository path Maven is using, active profiles/mirrors, SNAPSHOT update policy, plugin dependencies, and private repository credentials. Restoring a cache to one path while Maven uses another path will not help.

### Cache hit, yet Gradle still downloads artifacts

Check the Gradle User Home, Gradle wrapper version, repository URL/identity, and changing dependency TTL. Gradle stores metadata per repository, so changing the repository can trigger re-resolution.

### Offline build fails

The cache does not yet contain all required artifacts or plugins. Run an online build to complete resolution; for Maven you can run `dependency:go-offline` and `dependency:resolve-plugins`; for Gradle, run the required tasks before testing offline.

### Stale cache

Use Maven `-U` for snapshot/update checks or Gradle `--refresh-dependencies`. Check whether the lockfile changed and whether the cache key includes that file.

### Cache grows too quickly

Narrow the cached paths, improve key precision, exclude unnecessary logs/daemons/build outputs, and review retention. Only cache reusable dependencies.

### Parallel jobs overwrite the cache

Use one seed/push job and consumer/pull or read-only jobs. Avoid having multiple concurrent jobs write to a shared cache key when the platform does not guarantee the desired outcome.

### Build succeeds only when cached

Check whether the source is missing dependency declarations, wrappers, or generated files. Perform a clean build on a fresh runner and verify that all dependencies are declared, locked, and downloadable.

## 20. Complete Java example to test Maven caching

This example uses Apache Commons Lang to verify that a dependency is downloaded and reused.

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>dependency-cache-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.commons</groupId>
      <artifactId>commons-lang3</artifactId>
      <version>3.17.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Create `src/main/java/demo/CacheDemo.java`:

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class CacheDemo {
    public static void main(String[] args) {
        System.out.println("READY " + StringUtils.capitalize("dependency cache"));
    }
}
~~~

Run online the first time to download dependencies and plugins:

~~~bash
mvn -B -ntp verify
~~~

Run offline again to verify the local repository has all required components:

~~~bash
mvn -o -B -ntp verify
~~~

You can compile directly with JDK 17+ once the dependency is in the local repository:

~~~bash
javac --release 17 -cp "$HOME/.m2/repository/org/apache/commons/commons-lang3/3.17.0/commons-lang3-3.17.0.jar" -d target/classes src/main/java/demo/CacheDemo.java
~~~

Run the compiled class:

~~~bash
java -cp "target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.17.0/commons-lang3-3.17.0.jar" demo.CacheDemo
~~~

Exact stdout:

~~~text
READY Dependency cache
~~~

In a test environment with Maven 3.9.12 and JDK 24.0.2, the online run succeeded; the offline run against the same local repository also succeeded. The offline verify duration in that test was 1.091 seconds. Actual times depend on the runner, plugins, and cache.

## 21. Gradle example to test dependency caching

Create `settings.gradle`:

~~~groovy
rootProject.name = 'dependency-cache-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

application {
    mainClass = 'demo.CacheDemo'
}
~~~

Use the same `CacheDemo.java` file from the Maven example. Run online:

~~~bash
gradle run
~~~

After dependencies have been downloaded, run offline:

~~~bash
gradle --offline run
~~~

Exact stdout:

~~~text
READY Dependency cache
~~~

In testing with Gradle 9.2.1 and JDK 24.0.2, both `gradle run` and `gradle --offline run` succeeded and printed the same output. Offline builds only work when the cache already contains all required dependencies.

For real projects, commit the Gradle Wrapper and use `./gradlew` to pin the Gradle version. The dependency cache will be stored in the runner's Gradle User Home.

## 22. Dependency caching implementation checklist

- [ ] Identify the build tool and actual cache paths on the runner.
- [ ] Cache downloaded dependencies rather than caching every file in the workspace.
- [ ] Generate keys based on OS, architecture, build tool, and lockfiles/dependency files.
- [ ] Include module POMs, Gradle version catalogs, wrapper properties, and relevant lockfiles.
- [ ] Use a versioned prefix for proactive invalidation.
- [ ] Keep lockfiles and dependency versions in version control.
- [ ] Use Maven `-o`, Gradle `--offline`, or npm cache verification to validate the cache.
- [ ] Use GitHub `setup-java` caching or GitLab `cache:key:files` matching the project layout.
- [ ] Use `pull`/read-only for parallel cache-consuming jobs when appropriate.
- [ ] Do not cache credentials, signing keys, `.env`, or settings files containing secrets.
- [ ] Treat restored caches as untrusted input and guard against cache poisoning.
- [ ] Distinguish caches from artifacts used to pass build outputs between jobs.
- [ ] Measure restore time, cache hit rate, network usage, and total pipeline duration.
- [ ] Periodically run a clean cacheless build to confirm the build does not depend on stale state.
- [ ] Ensure a cache miss or cache eviction does not prevent the pipeline from building.

## 23. References

- [GitHub Actions — Dependency caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching): caching purpose, artifacts vs. caches, and cache security.
- [GitHub Actions — Dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching): cache keys, restore keys, cache hit/miss, branch scope, and cache poisoning.
- [actions/setup-java](https://github.com/actions/setup-java): Maven/Gradle cache configuration, cache-dependency-path, wrapper cache, and read-only cache.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): artifact/metadata cache, repository identity, checksums, changing dependencies, offline mode, and refresh.
- [Gradle — Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum and signature verification for dependencies.
- [Apache Maven — Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html): local repository and user settings.
- [Apache Maven — Settings reference](https://maven.apache.org/ref/3.9.9/maven-settings/settings.html): localRepository, offline, mirror, proxy, and server settings.
- [GitLab — Caching in CI/CD](https://docs.gitlab.com/ci/caching/): cache paths, key strategies, and caches vs. artifacts.
- [GitLab — CI/CD caching examples](https://docs.gitlab.com/ci/caching/examples/): lockfile-based cache keys and npm examples.
- [npm — npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/): clean install based on lockfile for CI.
- [npm — npm cache](https://docs.npmjs.com/cli/v11/commands/npm-cache/): content-addressable cache and npm cache verify.

Dependency caching helps CI/CD pipelines reduce the time spent downloading libraries and plugins. Long-term effectiveness comes from accurate cache keys, stable lockfiles, small cache paths, controlled write permissions, and a pipeline that still builds successfully when no cache exists.
