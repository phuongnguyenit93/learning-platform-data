# Configuring Dependency Caches by Build Tool, Operating System, and Configuration Files

## 1. Objective in the CI Automation Process

In CI, each Spring Boot build may need to download hundreds of artifacts: Spring Framework, Jackson, logging libraries, Maven/Gradle plugins, annotation processors, and transitive dependencies. If a runner always starts with an empty cache directory, repository and network wait time can account for a significant share of pipeline duration.

A **dependency cache** stores artifacts and metadata already downloaded by the build tool so subsequent builds can reuse them. A sound configuration must answer four questions:

1. Which kind of data is cached: Maven local repository, Gradle dependency cache, wrapper distribution, Docker BuildKit package cache, or task-output build cache?
2. Where does the cache live on Linux, macOS, Windows, containers, and CI runners?
3. When can it be reused: does the cache key reflect the build tool, OS/architecture, JDK, wrapper/tool version, repository identity, and files determining the dependency graph?
4. Who is allowed to read/write the cache, especially when the pipeline handles pull requests from untrusted branches or forks?

This lesson guides configuration across Maven, Gradle, GitHub Actions, GitLab CI, and Docker BuildKit. The goal is **to accelerate builds while preserving correctness and traceability**. Caching is a performance optimization; builds must still succeed cleanly when the cache is empty, expired, or deleted.

### Learning Outcomes

After this lesson, you will be able to:

- Distinguish dependency caches, wrapper caches, task-output build caches, Docker layer caches, BuildKit cache mounts, and build artifacts.
- Identify Maven/Gradle cache paths on Windows, Linux, and macOS.
- Select the exact configuration files to include in cache keys for single-module projects and monorepos.
- Separate caches by tool, OS, architecture, JDK/tool version, and repository configuration when needed.
- Configure Maven/Gradle local caches and verify offline builds.
- Write GitHub Actions workflows using `actions/setup-java` or `gradle/actions/setup-gradle`.
- Write GitLab CI cache keys based on dependency file contents.
- Leverage BuildKit cache mounts and understand their limits on ephemeral builders.
- Avoid accidentally caching `target/`, `build/`, or credentials.
- Diagnose cache misses, stale caches, repeated dependency downloads, and cache poisoning.

## 2. Distinguishing Different Cache Types

The word "cache" is often used for multiple distinct mechanisms. Do not lump them into a single directory or a single key.

| Type | Contents | Examples | Goal |
| --- | --- | --- | --- |
| **Dependency cache** | Resolved/downloaded JARs, POMs, module metadata | Maven `.m2/repository`; Gradle `caches/modules-2` | Avoid re-downloading dependencies |
| **Wrapper/tool cache** | Maven/Gradle distributions downloaded by the wrapper | `.m2/wrapper/dists`; `.gradle/wrapper/dists` | Avoid re-downloading the build tool distribution |
| **Build cache** | Reusable task outputs when inputs match | Gradle local/remote build cache | Avoid re-running compile/test/tasks |
| **Docker layer cache** | Results of Dockerfile instructions | BuildKit cache records | Avoid re-running unchanged instructions |
| **BuildKit cache mount** | Package-manager/compiler data during `RUN` | `RUN --mount=type=cache` | Persist repository data across builds on the same builder |
| **CNB cache** | Buildpack-contributed layers and lifecycle cache | Buildpacks build/launch cache volumes | Reuse layers in the Buildpacks workflow |
| **Artifact** | Outputs intended for handoff or release | JAR, test report, SBOM, image | Transfer build outputs to downstream jobs/stages/deployments |

**Caches are different from artifacts.** A cache can be deleted, expired, or skipped on restore without breaking pipeline correctness. An artifact is an output created for another job to consume or release; for example, a JAR built in a build job must be transferred via an artifact mechanism rather than relying on it happening to remain in a cache.

- Maven `.m2/repository` is a dependency/plugin cache; `target/classes` and `target/*.jar` are build outputs.
- Gradle `~/.gradle/caches/modules-2` is the dependency cache; Gradle build cache stores task outputs.
- Docker layer cache keeps instruction results; BuildKit cache mounts preserve package manager repositories inside `RUN`.
- CNB build cache is not synonymous with the Maven local repository on the host.

## 3. Designing Cache Keys

The cache key determines when a build is allowed to restore stored data. A clear structure for Java projects is:

~~~text
<tool>-<os>-<arch>-<jdk>-<tool-version>-<repo-profile>-<dependency-config-hash>
~~~

Examples:

~~~text
maven-linux-amd64-jdk17-wrapper-internal-mirror-a84f...
gradle-windows-amd64-jdk17-wrapper-locks-b31c...
maven-macos-arm64-jdk21-central-7f2a...
~~~

| Factor | Why It Affects the Cache | How to Include in Key |
| --- | --- | --- |
| Build tool | Maven and Gradle use different cache formats | Prefix `maven` or `gradle` |
| OS | Native dependencies, permissions, and paths differ | `linux`, `windows`, `macos` |
| Architecture | Native classifiers may differ between amd64 and arm64 | `x64`, `arm64` |
| JDK major/vendor | Profiles, toolchains, or native dependencies may depend on JDK | `jdk17-temurin`, `jdk21` |
| Wrapper/tool version | Gradle cache formats and plugin behaviors depend on version | Hash wrapper properties or prefix version |
| Dependency config | Versions, catalogs, and lockfiles change the dependency graph | Hash configuration files |
| Repository identity | Metadata and package sources can differ across repositories | Prefix or sanitized config |
| Trust boundary | Caches from untrusted jobs should not be used for releases | Separate protected/untrusted namespaces |

**Do not use the full source commit SHA as the primary key.** Every Java code commit would create a brand-new cache even when POMs and lockfiles have not changed. Likewise, do not hash the entire repository if the goal is reusing the dependency cache across source code changes.

### 3.1. Configuration Files to Hash

**Maven:**

- All `pom.xml` files in the reactor: root, modules, and in-repo parent POMs.
- `.mvn/wrapper/maven-wrapper.properties`.
- `.mvn/extensions.xml` if build extensions are used.
- `.mvn/maven.config` if active profiles, properties, or options affect dependency resolution.
- Project-managed BOM or version catalog files stored outside POMs.
- Repository/mirror identity and profiles affecting resolution sources.

**Gradle:**

- `settings.gradle` or `settings.gradle.kts`.
- `build.gradle`/`build.gradle.kts` at the root and in subprojects.
- `gradle.properties`.
- `gradle/wrapper/gradle-wrapper.properties`.
- `gradle/libs.versions.toml` and any other version catalogs.
- `gradle.lockfile` or `gradle/dependency-locks/*.lockfile`.
- `gradle/verification-metadata.xml`.
- `buildSrc/`, `build-logic/`, and included builds.
- Repository/plugin management in `settings.gradle(.kts)`.

**Monorepo:** hash every POM, build file, and lockfile of modules that may be built in the job. Hashing only the root POM while omitting module POMs or version catalogs can restore a stale cache even when the dependency graph changed.

### 3.2. Files That Should Not Be Cached

- `~/.m2/settings.xml` if it contains usernames/passwords, server tokens, or private credentials.
- `~/.gradle/gradle.properties` if it contains credentials.
- `.env`, private keys, registry tokens, and secret files.
- Full source code solely to construct a dependency cache key.
- `target/` or `build/` when the goal is only dependency caching.

Never put secrets into a cache archive or cache key. If repository mirrors change, use a repository ID or sanitized config file to distinguish caches.

## 4. Cache Paths by Tool and Operating System

### 4.1. Maven

Maven's default local repository is `.m2/repository` under the user's home directory. It stores dependencies, plugin artifacts, POM metadata, and repository tracking info.

| Operating System | Maven Local Repository |
| --- | --- |
| Linux | `$HOME/.m2/repository` |
| macOS | `$HOME/.m2/repository` |
| Windows PowerShell | `$env:USERPROFILE\.m2\repository` |
| Windows CMD | `%USERPROFILE%\.m2\repository` |

The Maven Wrapper distribution cache typically lives in `.m2/wrapper/dists`, separate from the local repository.

Check effective settings:

~~~bash
mvn help:effective-settings
~~~

Look for the `localRepository` element. If unconfigured, Maven defaults to the user-home location.

### 4.2. Gradle

Gradle User Home defaults to `~/.gradle` on Linux/macOS and `%USERPROFILE%\.gradle` on Windows. It can be overridden via `GRADLE_USER_HOME`.

| Contents | Linux/macOS | Windows |
| --- | --- | --- |
| Dependency artifacts/metadata | `$GRADLE_USER_HOME/caches/modules-2` | `%USERPROFILE%\.gradle\caches\modules-2` |
| Gradle wrapper distributions | `~/.gradle/wrapper/dists` | `%USERPROFILE%\.gradle\wrapper\dists` |
| Version-specific caches | `~/.gradle/caches/<version>/` | `%USERPROFILE%\.gradle\caches\<version>\` |
| Project-local state | `<project>/.gradle/` | `<project>\.gradle\` |

With default settings, `$GRADLE_USER_HOME` is `$HOME/.gradle`; thus the dependency cache resides at **$GRADLE_USER_HOME/caches/modules-2**. Gradle manages artifacts and metadata across these directories; you usually do not need to cherry-pick individual files.

Setting a dedicated Gradle User Home in CI:

~~~bash
export GRADLE_USER_HOME="$PWD/.gradle-user-home"
./gradlew --no-daemon build
~~~

Windows PowerShell:

~~~powershell
$env:GRADLE_USER_HOME = Join-Path $PWD ".gradle-user-home"
.\gradlew.bat --no-daemon build
~~~

If Gradle User Home is placed inside the workspace, CI must cache `.gradle-user-home/caches` and `.gradle-user-home/wrapper` accurately. Do not let Gradle write to `~/.gradle` while CI caches a different directory.

### 4.3. Why Separate Caches by OS and Architecture?

Pure Java JARs are usually portable, yet the dependency graph can differ due to OS/JDK-activated Maven profiles, Gradle variant attributes, native classifiers, JNI libraries, permissions, paths, plugin logic, or toolchains. Consequently, a `linux/amd64` cache should not be reused blindly by `windows/amd64` or `linux/arm64`.

## 5. Configuring Caching for Maven

### 5.1. Using the Default Local Repository

~~~bash
mvn -B -ntp verify
~~~

Maven searches `~/.m2/repository` before downloading from remote repositories. To specify a custom path:

~~~bash
mvn -Dmaven.repo.local="$HOME/.m2/repository" -B -ntp verify
~~~

Windows PowerShell:

~~~powershell
mvn "-Dmaven.repo.local=$env:USERPROFILE\.m2\repository" -B -ntp verify
~~~

### 5.2. Changing the Local Repository via settings.xml

The user settings file is normally `~/.m2/settings.xml`, or `%USERPROFILE%\.m2\settings.xml` on Windows.

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <localRepository>/opt/build-cache/maven-repository</localRepository>
</settings>
~~~

`/opt/build-cache/...` is a Linux example; on Windows/macOS, supply a valid path. `settings.xml` can also contain mirrors, proxies, profiles, and credentials; **never cache the entire user settings directory**.

In CI, `-Dmaven.repo.local` is often easier to control because you can point the repository to a workspace path allowed by the CI cacher.

### 5.3. Maven Key by POM and Wrapper

~~~text
maven-linux-amd64-jdk17-<hash-of-pom-and-maven-config>
~~~

Key files:

~~~text
pom.xml
**/pom.xml
.mvn/wrapper/maven-wrapper.properties
.mvn/extensions.xml
.mvn/maven.config
~~~

For multi-module builds, include the root POM and all module POMs. If a CI profile alters dependencies, put the profile name in the prefix or hash a safe config file representing that profile.

### 5.4. SNAPSHOT and Dynamic Versions

Caching does not make mutable dependencies immutable:

- Release dependencies with fixed versions usually reuse stably.
- `SNAPSHOT` builds and repository metadata can change over time.
- Version ranges or unpinned dependency versions can resolve to different versions.
- Maven `-U` forces checks for updated snapshots and missing/updated releases per resolver policy.

Intentional refresh:

~~~bash
mvn -U -B -ntp verify
~~~

Do not pass `-U` on every build just to "freshen the cache"; it can increase repository queries. For releases, prefer pinned versions and explicit dependency management.

### 5.5. Checking Whether the Maven Cache Is Sufficient

After warming the cache:

~~~bash
mvn -o -B -ntp verify
~~~

`-o` is offline mode. If the build reports missing artifacts or plugins, the cache does not yet hold all inputs needed by that build command. This is a completeness check, not a default pipeline setting.

`dependency:go-offline` is useful for warming a portion of dependencies and plugins, but does not guarantee all dynamic plugins/profiles have been fetched. Validate with the exact CI command—for example, `mvn verify` with the required profiles.

## 6. Configuring Caching for Gradle

### 6.1. Dependency Cache and Wrapper Cache

Gradle manages its dependency cache under Gradle User Home, primarily in `caches/modules-2`. Wrapper distributions are stored separately in `wrapper/dists`.

~~~bash
./gradlew --no-daemon build
~~~

Windows:

~~~powershell
.\gradlew.bat --no-daemon build
~~~

Do not cache only the project `.gradle/` directory and expect all dependencies to be cached. That is project-local state; the primary dependency cache lives in Gradle User Home.

### 6.2. Files to Hash

~~~text
settings.gradle(.kts)
build.gradle(.kts)
gradle.properties
gradle/wrapper/gradle-wrapper.properties
gradle/libs.versions.toml
gradle.lockfile
gradle/verification-metadata.xml
buildSrc/**
build-logic/**
~~~

In a monorepo, include subproject and included-build build files and lockfiles. If using multiple version catalogs, include every catalog file.

### 6.3. Dependency Cache vs. Gradle Build Cache

Gradle has a separate build cache, enabled via:

~~~bash
./gradlew --build-cache build
~~~

Or in `gradle.properties`:

~~~properties
org.gradle.caching=true
~~~

The dependency cache stores resolved module metadata and artifacts. The build cache stores **task outputs** reusable when corresponding task inputs match. Both can be enabled together, though they serve different purposes and have different invalidation rules.

### 6.4. Offline and Refresh

Checking the dependency cache:

~~~bash
./gradlew --offline build
~~~

When re-checking dependency metadata or changing/dynamic dependencies is required:

~~~bash
./gradlew --refresh-dependencies build
~~~

Gradle verifies metadata and checksums and only re-downloads what is strictly necessary; `--refresh-dependencies` does not always re-download every JAR.

Gradle cache metadata is repository-specific, and the cache format is tied to the Gradle version. Use the same wrapper version when populating and consuming a cache. Do not arbitrarily copy caches written by another version.

### 6.5. Dependency Locking and Verification

So that caches do not mask supply-chain risks:

- Enable dependency locking for relevant configurations and version-control lockfiles.
- Use `gradle/verification-metadata.xml` to verify checksums/signatures when required by policy.
- When adding dependencies, review changes to lockfiles and verification metadata.
- Never treat a cache hit as proof that an artifact has been verified.

Generating initial checksum metadata:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

This command bootstraps checksums from currently resolved artifacts; **review the result and verify trusted sources** before committing.

## 7. GitHub Actions: Caching Maven by OS and POM

GitHub-hosted runners normally start with a clean environment. Use `actions/setup-java` to configure Java and dependency caching.

### 7.1. Single-Module Maven Project

File `.github/workflows/maven.yml`:

~~~yaml
name: Maven build

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
          java-version: '17'
          cache: maven

      - name: Build and test
        run: ./mvnw -B -ntp verify
~~~

`cache: maven` enables caching for the local Maven repository. The action builds the key from runner OS, architecture, package manager, and hashes of dependency files. Wrapper distributions and the JDK may be cached separately.

### 7.2. Maven Monorepo or Custom Configuration

~~~yaml
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            .mvn/wrapper/maven-wrapper.properties
            .mvn/extensions.xml
            .mvn/maven.config
~~~

These globs update the key whenever POMs, Maven wrapper config, extensions, or Maven CLI config change. If the project uses a custom version catalog/BOM file, add it to the list.

**Note on Java matrices:** `setup-java`'s dependency cache key includes OS, architecture, package manager, and file hashes; JDK installation caching is separate. If a matrix spans multiple JDKs with an identical dependency graph, the dependency cache can be shared. If OS/JDK profiles or native dependencies alter resolved contents, separate namespaces per policy.

### 7.3. Restore Prefixes When Managing Caches Manually

When using `actions/cache` directly, you can design:

~~~yaml
key: maven-OS-ARCH-jdk17-DEPENDENCY_CONFIG_HASH
restore-keys: |
  maven-OS-ARCH-jdk17-
~~~

The exact key is tried first; `restore-keys` falls back to the closest cache for the same platform and toolchain. Never use an overly broad fallback like `maven-` alone, because it could restore caches from an incompatible OS, architecture, or JDK.

## 8. GitHub Actions: Caching Gradle

### 8.1. Using the Gradle Setup Action

~~~yaml
name: Gradle build

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
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v6

      - name: Build and test
        run: ./gradlew --no-daemon build
~~~

`gradle/actions/setup-gradle` manages caching of Gradle User Home and supports advanced cache features. When using this action, do not add another action caching `~/.gradle/caches` unless there is an explicit reason.

### 8.2. Hashing Gradle Files in a Monorepo

When using `actions/setup-java` with `cache: gradle`:

~~~yaml
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle
          cache-dependency-path: |
            **/*.gradle*
            **/gradle.properties
            **/gradle-wrapper.properties
            **/gradle.lockfile
            gradle/libs.versions.toml
            gradle/verification-metadata.xml
            buildSrc/**
            build-logic/**
~~~

The list must match your repository layout. If the version catalog lives elsewhere or there are multiple included builds, add the relevant files. **Pick one primary cache manager**, avoiding two actions restoring and saving the same Gradle directory.

## 9. GitLab CI: Content-Based Keys and Cache Paths

GitLab CI supports `cache:key:files` to derive keys from file contents. `cache:paths` specifies directories relative to the project directory.

### 9.1. Maven on a Linux Runner

File `.gitlab-ci.yml`:

~~~yaml
maven-build:
  image: maven:3.9-eclipse-temurin-17
  cache:
    key:
      prefix: "maven-linux-amd64-jdk17"
      files:
        - pom.xml
        - .mvn/wrapper/maven-wrapper.properties
        - .mvn/extensions.xml
        - .mvn/maven.config
    paths:
      - .m2/repository/
    policy: pull-push
  script:
    - mvn -Dmaven.repo.local="$CI_PROJECT_DIR/.m2/repository" -B -ntp verify
~~~

The Maven local repository is moved into `$CI_PROJECT_DIR/.m2/repository` inside the workspace so GitLab Runner can cache it. The key is isolated by platform/toolchain prefix and configuration file hashes.

For Windows runners, use a distinct prefix such as `maven-windows-amd64-jdk17`, and adjust commands and paths for PowerShell/CMD. Do not share caches between Linux and Windows solely because the Maven version matches.

### 9.2. Gradle on a Linux Runner

~~~yaml
gradle-build:
  image: eclipse-temurin:17-jdk
  cache:
    key:
      prefix: "gradle-linux-amd64-jdk17"
      files:
        - settings.gradle
        - build.gradle
        - gradle/wrapper/gradle-wrapper.properties
        - gradle/libs.versions.toml
        - gradle.lockfile
        - gradle/verification-metadata.xml
    paths:
      - .gradle-user-home/caches/
      - .gradle-user-home/wrapper/
    policy: pull-push
  script:
    - GRADLE_USER_HOME="$CI_PROJECT_DIR/.gradle-user-home" ./gradlew --no-daemon build
~~~

If the project uses Kotlin DSL, substitute `settings.gradle.kts` and `build.gradle.kts`. Add subproject build files, lockfiles, and build logic per your actual structure. GitLab `cache:key:files` supports up to 10 files; pick the root files that govern version catalogs/lockfiles or maintain a controlled checksum manifest.

### 9.3. pull, push, and pull-push

- `pull-push`: job restores the cache and uploads an updated cache upon completion.
- `pull`: consumes the cache without uploading changes; suitable for fan-out/matrix jobs.
- `push`: uploads a cache without restoring first; suitable for cache-warming jobs in some pipelines.

Multiple concurrent writers sharing a key can cause races or overwritten caches. Designate one primary warming/writer job and keep remaining jobs pull-only if needed. Cache availability depends on the runner executor and distributed cache setup; it is **not guaranteed** that every job sees the same cache.

### 9.4. Caches vs. Artifacts in GitLab

- **Cache:** dependency downloads reused across pipelines/jobs; can expire or be cleared.
- **Artifacts:** outputs produced by a job for downstream stages, such as JARs, test reports, SBOMs, or scan reports.

Do not place the same path in both `cache` and `artifacts` unintentionally. Caches are restored before artifacts; artifacts can overwrite workspace files. For deployable JARs, pass them via artifacts or a registry rather than relying on the dependency cache.

## 10. Docker BuildKit: Caching the Maven Repository in the Build Stage

When a Dockerfile runs Maven inside a build stage, each fresh container filesystem build might re-download dependencies. BuildKit supports cache mounts to retain repository data across `RUN` steps on the same builder.

~~~dockerfile
# syntax=docker/dockerfile:1
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY pom.xml ./
COPY .mvn/ .mvn/

RUN --mount=type=cache,id=catalog-maven-linux-amd64-jdk17,target=/root/.m2/repository,sharing=locked \
    mvn -B -ntp dependency:go-offline

COPY src ./src

RUN --mount=type=cache,id=catalog-maven-linux-amd64-jdk17,target=/root/.m2/repository,sharing=locked \
    mvn -B -ntp verify
~~~

- `target=/root/.m2/repository` must match the Maven local repository of the user inside the build container.
- `id=` creates an isolated namespace to avoid sharing caches across incompatible tools, projects, or platforms.
- `sharing=locked` forces a second concurrent writer to wait while the cache is in use.
- Both `RUN` steps must mount the same cache ID and path to share the Maven repository.
- `dependency:go-offline` warms the cache, though it does not guarantee every dynamic plugin/profile is fetched; `verify` still resolves completely.
- If the build needs `.mvn/extensions.xml`, `maven.config`, wrappers, or parent POMs, copy them before the corresponding Maven command.

### 10.1. Cache Mounts Are Not Docker Layer Caches

Docker BuildKit cache mounts store package-manager data in builder-local storage. They can persist across builds on the same builder, yet:

- They are not baked into the final image as regular filesystem layers.
- They are not automatically exported via `--cache-to` or restored via `--cache-from`.
- If CI provisions a fresh builder/machine per job, the cache mount starts empty.
- Builds must still succeed cleanly even when the cache mount is empty or garbage-collected.

If runners are ephemeral, consider a persistent BuildKit builder, a separate external dependency cache, a Maven repository proxy, or a CI-provider-managed cache mechanism. Docker layer cache export/import and BuildKit cache mounts are two distinct mechanisms.

For Gradle in Docker, mount the Gradle User Home matching the build user, including `caches` and `wrapper`. Do not hardcode `/root/.gradle` if the image runs as user `gradle` or another UID. Check the actual `GRADLE_USER_HOME` and isolate cache IDs by Gradle wrapper version, OS, and architecture.

## 11. Caching in Cloud Native Buildpacks

If Spring Boot uses `spring-boot:build-image` or Gradle `bootBuildImage`, CNB maintains its own build cache and launch cache managed by the lifecycle.

This is **not the same cache** as Maven `.m2/repository` or Gradle `caches/modules-2` on the host. CNB caches typically live in Docker volumes or Buildpacks builder infrastructure and depend on the image name, builder, lifecycle, and plugin configuration.

When CI uses Buildpacks:

- Keep builder/run images and cache naming stable per release policy.
- Check whether Docker volumes/caches persist across pipeline runs.
- Avoid generating random image names per job if cache reuse is desired.
- Prune caches by retention/size policy rather than deleting all volumes after every build.
- Never treat a CNB cache hit as proof that dependencies are pinned or verified.
- If Maven/Gradle builds before invoking `build-image`, maintain a separate dependency cache for the build tool.

## 12. Practical Key Strategies

**Single-module Maven project:**

~~~text
maven-<os>-<arch>-jdk17-<maven-wrapper-hash>-<pom-hash>
~~~

Hash the root `pom.xml`, wrapper properties, and `.mvn/extensions.xml`. If mirrors or profiles change, add the repository identity or a safe configuration file.

**Maven monorepo:**

~~~text
maven-<os>-<arch>-jdk17-<reactor-config-hash>
~~~

Hash all module POMs and relevant Maven configs. Avoid hashing the entire source tree.

**Gradle with version catalog and locking:**

~~~text
gradle-<os>-<arch>-jdk17-<wrapper-version>-<catalog-lock-verification-hash>
~~~

Include wrapper properties, settings/build scripts, version catalogs, dependency lockfiles, and verification metadata. Whenever a version changes in the catalog or lockfile, the cache key rotates.

**Multi-JDK/OS matrix:**

~~~text
maven-linux-amd64-jdk17-...
maven-linux-arm64-jdk17-...
maven-windows-amd64-jdk17-...
maven-macos-arm64-jdk21-...
~~~

If artifacts are purely portable, some caches could technically be shared, but separating keys is safer whenever profiles, native classifiers, or toolchains vary. Optimize after measuring.

**Restore prefix:** when the hash key changes, a restore prefix can fetch an older cache for the same tool and platform. Never fall back across different tools or OSes. Even after a fallback restore, Maven/Gradle must still verify dependency resolution against the current configuration.

## 13. Security and Correctness

### 13.1. Caches Are Inputs, Not Sources of Truth

Any job with write access to a cache could store corrupted or altered contents. Therefore:

- Never treat a cache as proof that a dependency came from a trusted repository.
- Enforce dependency verification, checksums, and signatures when required by policy.
- Keep lockfiles and dependency versions under version control.
- Scan and validate artifacts after building.
- Ensure you can wipe caches and rebuild without altering the source of truth.

### 13.2. Never Cache Credentials

Cache only directories containing necessary dependencies and tool distributions:

- Maven: `.m2/repository` and wrapper distributions if needed.
- Gradle: `caches` and appropriate `wrapper` directories.
- Never cache the entire user home directory if it holds settings, credentials, private init scripts, or secret files.
- Never place registry tokens, Maven server passwords, signing keys, or private keys inside cached paths.

### 13.3. Isolating Caches Between Trusted and Untrusted Jobs

Pull requests from untrusted forks or branches can run build scripts and write data into any cache they have permission to access. For release pipelines:

- Use separate cache namespaces and permissions for protected branches.
- Never allow release jobs to trust caches writable by untrusted workflows.
- Give PR jobs read-only cache access if supported by your CI provider.
- Designate only trusted jobs as writers for caches consumed by releases.
- Never share private dependency caches across projects or tenants unless permitted by policy.

GitLab separates caches between protected and non-protected branches in standard configurations; GitHub Actions has its own branch/trigger cache access scoping. Always review your CI provider behavior and organizational repository policies.

### 13.4. Caches and Checksums

Gradle dependency verification can use `gradle/verification-metadata.xml` to check artifact checksums and signatures. This file should be reviewed and version-controlled. A cache hit must never bypass verification.

With Maven, use trusted repositories, pinned release versions, strict checksum policies, and an internal repository manager when artifact provenance control is required. Never disable checksum verification just to make a cached build pass.

## 14. Diagnosing Cache Hits, Misses, and Stale Caches

Inspect paths:

~~~bash
mvn help:effective-settings
mvn -version
./gradlew --version
./gradlew --status
~~~

Confirm CI uses the expected user home, cache path, and wrapper. A cache saved at `~/.m2/repository` will not help the build if the command overrides `-Dmaven.repo.local` to another path.

**Offline test:**

~~~bash
mvn -o -B -ntp verify
./gradlew --offline --no-daemon build
~~~

If an offline build fails, read which artifact, plugin, or configuration is missing. Do not immediately wipe the entire cache; it may just be missing a plugin profile or un-warmed module.

**Forcing a refresh when needed:**

~~~bash
mvn -U -B -ntp verify
./gradlew --refresh-dependencies build
~~~

Use this when snapshot/dynamic dependencies change or stale metadata caches are suspected. Never make refreshing a default step in every pipeline.

Track exact cache hits, fallback hits, misses, restore/download durations, dependency resolution time, archive sizes, cold vs. warm build times, and invalidation frequency. If a 2 GB cache takes longer to restore than downloading a smaller set of dependencies, shrink the cache scope or switch to runners with persistent storage.

## 15. Common Errors and Fixes

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Maven re-downloads dependencies on every job | Cache path does not match `maven.repo.local`, or fresh runner skips restore | Print effective settings; inspect cache path and key |
| Maven cache key unchanged when module POM edits | Only hashed root POM | Include `**/pom.xml` or all reactor POMs |
| Maven cache contains settings/credentials | Cached entire `.m2` | Cache only `.m2/repository` and wrapper distributions |
| Maven offline fails on a plugin | Warm goal missed required plugins or profiles | Run the exact Maven goals/profiles CI requires |
| Stale SNAPSHOT still used | Snapshot metadata remains cached | Use `-U` intentionally or avoid SNAPSHOTs in releases |
| Gradle re-downloads module metadata | Cache path differs from `GRADLE_USER_HOME` or repo identity changed | Check Gradle User Home and repositories |
| Incompatible Gradle cache | Cache written by a different Gradle format/version | Key by wrapper version |
| Gradle build outputs not reused | Only dependency cache is enabled | Enable Gradle build cache separately where tasks support it |
| Windows and Linux share a cache | Key omits OS/architecture | Separate cache namespaces per runner platform |
| Cache unchanged when version catalog updates | Key omits `libs.versions.toml` | Add version catalog to hash |
| Cache unchanged when lockfile updates | Lockfile not included in key | Add lockfiles and verification metadata |
| Cache misses on every commit | Key includes commit SHA or entire source tree | Hash only dependency and build configuration files |
| GitHub Actions restores old cache yet downloads more | Fallback key hit or cache lacked newer artifacts | Rotate key on config changes; seed cache completely |
| GitLab jobs overwrite each other's caches | Shared key across differing paths or multiple writers | Separate keys or configure pull-only consumers |
| GitLab job cannot find cache | Different runner machine without distributed cache | Configure distributed cache or persistent runners |
| BuildKit cache mount empty in CI | Ephemeral builder; cache mount is builder-local | Use a persistent builder or external dependency cache |
| Docker layer cache hits yet Maven re-downloads | Layer cache and cache mount are separate mechanisms | Mount `.m2/repository` properly in every required `RUN` |
| Cache bloats in size | Accumulates old versions, modules, and metadata | Limit retention and prune caches systematically |
| Cache restore slower than download | Archive too large or slow cache network | Cache only necessary directories; measure restore cost |
| Build consumes wrong artifact from cache | Cache misused for artifact handoff | Use CI artifacts for JARs, test reports, and SBOMs |
| Private dependency leaks to another project | Cache scope too broad | Isolate by project, tenant, permissions, and repository identity |
| Checksum mismatch after cache restore | Corrupted cache artifact, republished dependency, or tampering | Halt release; verify checksums and upstream source |

## 16. Step-by-Step Cache Configuration Workflow

1. **Identify build tool and wrapper version.** Record Maven/Gradle version, JDK major/vendor, and platform.
2. **Determine actual cache paths.** Inspect Maven effective settings or `GRADLE_USER_HOME`; never guess from a developer's home directory.
3. **Classify data.** Separate dependency artifacts, wrapper distributions, task outputs, Docker caches, and release artifacts.
4. **List config files.** POMs, wrapper properties, settings/build scripts, version catalogs, lockfiles, profiles, and repository identity.
5. **Construct the cache key.** Include tool + OS + architecture + JDK/tool version + config hash; avoid commit SHA as the primary key.
6. **Establish trust boundaries.** Never cache credentials, separate protected and untrusted jobs, and restrict cache writers.
7. **Configure the provider.** GitHub Actions, GitLab CI, persistent runners, or BuildKit cache mounts depending on environment.
8. **Warm caches with the real build command.** Run `verify`/`build` with exact profiles and modules; do not rely solely on minimal resolve commands.
9. **Test offline and measure.** Confirm cache completeness and measure restore time vs. download time.
10. **Set invalidation/refresh rules.** Rotate keys when dependency configs change; refresh stale caches per policy.
11. **Store artifacts separately.** Pass JARs, reports, SBOMs, and image digests via artifacts/registries, never dependency caches.
12. **Monitor regularly.** Track cache size, hit rate, age, security, and operational cost.

## 17. Self-Check Exercises

**1. Why shouldn't you use the commit SHA as the primary cache key for Maven dependencies?**

Answer: Every commit generates a new key even when POMs have not changed, causing constant cache misses. Hash dependency configuration files instead.

**2. Where is the default Maven local repository on Windows?**

Answer: `%USERPROFILE%\.m2\repository`, unless changed via `settings.xml` or `-Dmaven.repo.local`.

**3. How do the Gradle dependency cache and Gradle build cache differ?**

Answer: The dependency cache stores resolved module metadata and artifacts; the build cache stores reusable task outputs keyed by task inputs.

**4. Why does a cache key need OS and architecture?**

Answer: OS profiles, native classifiers, JNI libraries, permissions, and toolchains can differ across Linux/Windows/macOS or amd64/arm64.

**5. What must a Maven monorepo hash?**

Answer: Root and module POMs, Maven wrapper properties, extensions, Maven config, and any other files affecting profiles, repositories, or dependency resolution.

**6. What files must a Gradle project using a version catalog include in its key?**

Answer: `gradle/libs.versions.toml` alongside build/settings scripts, wrapper properties, lockfiles, `gradle.properties`, and verification metadata when present.

**7. What is `mvn -o verify` used for?**

Answer: Runs Maven offline to verify whether the current cache holds all dependencies and plugins required by that build command.

**8. Does `./gradlew --refresh-dependencies build` re-download every JAR?**

Answer: No. Gradle refreshes metadata and verifies artifacts, downloading only what is actually needed.

**9. Does the GitLab cache replace artifacts?**

Answer: No. Caches reuse dependency downloads; artifacts pass job outputs to downstream stages/jobs or preserve them for retrieval.

**10. Why might a BuildKit cache mount be empty in the next CI job?**

Answer: Cache mounts live in builder-local storage and are not automatically exported/imported via `--cache-to`/`--cache-from`. Ephemeral builders start with an empty cache mount.

**11. Should you cache the entire `~/.m2` directory?**

Answer: Not by default. Cache `.m2/repository` and necessary wrapper distributions; keep settings and credentials in a separate protected location.

**12. Why does a Gradle cache hit still require dependency verification?**

Answer: A cache could be tampered with or populated from an untrusted source. Checksum and signature verification confirms artifacts against reviewed metadata.

## 18. Checklist for Java/Spring Boot Projects

- [ ] Build commands use the Maven/Gradle Wrapper with a pinned version.
- [ ] JDK major/vendor/architecture are recorded in the pipeline.
- [ ] Cache paths match the actual `maven.repo.local` or `GRADLE_USER_HOME`.
- [ ] Maven keys include root/module POMs and relevant `.mvn` configs.
- [ ] Gradle keys include settings/build scripts, wrapper, version catalogs, lockfiles, and verification metadata.
- [ ] Cache keys separate by tool, OS, architecture, and toolchain as needed.
- [ ] Repository/mirror identity is accounted for when multiple artifact sources exist.
- [ ] Credentials, user settings, and private keys are never cached.
- [ ] Caches are never substituted for artifacts to pass JARs, SBOMs, or test reports.
- [ ] Entire `target/` or `build/` directories are never cached as dependency caches.
- [ ] BuildKit cache mounts have isolated IDs and documented builder persistence behavior.
- [ ] Cache restore/seeding is tested with the exact Maven/Gradle build command.
- [ ] Offline builds are used as a completeness check where appropriate.
- [ ] Dynamic/SNAPSHOT dependencies have an explicit refresh/update policy.
- [ ] Lockfiles, checksums, and dependency verification are reviewed.
- [ ] Protected and untrusted jobs enforce cache access boundaries.
- [ ] Cache writer/reader policies prevent concurrent overwrites.
- [ ] Cache retention and size are actively managed.
- [ ] Hit rate, restore time, and before/after build durations are measured.
- [ ] Builds still succeed when the cache is deleted or not restored.

**Conclusion:** Good dependency caching starts with selecting **the right directory for the right build tool**, then building a key from **OS, architecture, toolchain, and the files that truly govern the dependency graph**. Maven needs `.m2/repository` alongside POM and wrapper configs; Gradle needs Gradle User Home caches alongside wrapper, version catalogs, and lockfiles. CI providers and BuildKit merely store and restore those caches. Keep credentials out of caches, keep caches separate from artifacts, and always ensure builds work cleanly when the cache is empty.

## 19. Official References

1. [Apache Maven — Settings Reference / Local Repository](https://maven.apache.org/settings.html)
2. [Apache Maven — Configuring Maven and Local Repository](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
3. [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html)
4. [Gradle — Directory Layout and Cache Locations](https://docs.gradle.org/current/userguide/directory_layout.html)
5. [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
6. [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
7. [GitHub Actions — Dependency Caching Reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
8. [GitHub — actions/setup-java Caching and cache-dependency-path](https://github.com/actions/setup-java)
9. [GitHub — gradle/actions/setup-gradle](https://github.com/gradle/actions/tree/main/setup-gradle)
10. [GitLab CI/CD — Caching](https://docs.gitlab.com/ci/caching/)
11. [GitLab CI/CD — cache:key:files and cache:paths](https://docs.gitlab.com/ci/yaml/#cache)
12. [Docker — Dockerfile RUN --mount=type=cache](https://docs.docker.com/reference/dockerfile/#run---mounttypecache)