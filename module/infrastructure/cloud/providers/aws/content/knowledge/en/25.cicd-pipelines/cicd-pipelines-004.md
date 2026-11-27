# Dependency Caching and Java Application Packaging in CodeBuild

A Spring Boot development team has a pipeline running on AWS CodeBuild. On every build, Maven or Gradle has to download hundreds of dependencies, compile source code, run tests, and package an executable JAR. When a build runs on a new build host, dependencies may have to be downloaded from scratch. If the pipeline does not clearly specify output files, the uploaded artifact might be missing the JAR, include unintended intermediate files, or lack test reports for traceability.

AWS CodeBuild supports caching to reuse dependencies and build data across runs. The buildspec defines cached directories, execution phases, and the files packaged as artifacts. Proper configuration reduces build times, maintains reproducibility, and produces clear outputs for downstream stages.

This lesson belongs to the **CI/CD on AWS** chapter of the **CLOUD_PROVIDERS_AWS** module. We will practice with Maven and Gradle, distinguish S3 cache from local cache, construct cache keys from dependency descriptors, output JAR/WAR files, publish test reports, and control access permissions for caches and artifacts.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the role of AWS CodeBuild and buildspecs in a Java pipeline.
2. Distinguish between dependency cache, task/build cache, and build output artifact.
3. Explain the two CodeBuild cache types: Amazon S3 and local.
4. Choose the appropriate local cache mode: source, Docker layer, or custom.
5. Identify the default dependency cache directories for Maven and Gradle.
6. Construct cache keys based on POM, Gradle build files, version catalogs, and lockfiles.
7. Use fallback keys and understand how CodeBuild restores caches.
8. Write a buildspec version 0.2 for Maven and Gradle.
9. Choose a stable Java runtime and build image.
10. Package an executable JAR/WAR and specify artifacts accurately.
11. Publish JUnit XML test reports and coverage reports.
12. Manage multi-module projects and monorepos.
13. Combine CodeArtifact with dependency caching.
14. Protect caches from secret leakage and cache poisoning.
15. Measure cache effectiveness, handle cache misses, and debug slow builds.

## 2. CodeBuild in the Java Build Flow

A CodeBuild build typically receives source code from CodeCommit, GitHub, Bitbucket, S3, or CodePipeline. CodeBuild prepares the build environment, reads the buildspec, runs Maven/Gradle commands, and uploads artifacts or pushes an image to Amazon ECR.

    Source repository / CodePipeline
                |
                v
          AWS CodeBuild
                |
       +--------+---------+
       |                  |
       v                  v
    Restore cache       Build image
       |               JDK + Maven/
       |               Gradle tools
       +--------+---------+
                |
                v
       Compile + unit tests
                |
                v
       Package JAR / WAR
                |
        +-------+-------+
        |               |
        v               v
    Test reports     Build artifact
    JUnit / coverage  S3 / Pipeline
        |               |
        +-------+-------+
                |
                v
       Deploy / integration test

Caches and artifacts serve different purposes:

- **Dependency cache** stores downloaded dependencies, such as the Maven local repository or Gradle module cache.
- **Build cache** can store precomputed task outputs to avoid re-execution when inputs have not changed.
- **Build artifact** is the output passed to the next stage, such as an executable JAR, WAR, ZIP, or manifest.
- **Test report** is the test result for the pipeline to display and store quality history.

Do not use the cache as a release artifact store. A cache is a performance optimization and can be replaced or expire; artifacts must be stored, identified, and managed according to release policy.

## 3. Buildspec Version 0.2 and Phases

A buildspec is a YAML file describing how CodeBuild runs a build. By default, CodeBuild looks for `buildspec.yml` at the source root. A different name or location can be configured in the build project.

Buildspec version 0.2 is recommended. Unlike version 0.1, commands within the same phase share a shell context, preserving state such as the current working directory and shell variables across commands in that phase.

Commonly used phases:

| Phase | Role in a Java build |
|---|---|
| install | Select Java runtime, install required tools |
| pre_build | Check versions, prepare registries/repositories, verify source |
| build | Compile, run unit/integration tests, package |
| post_build | Verify outputs, generate checksums/manifests, prepare metadata |

Declaring all four phases is not mandatory. If a phase needs no commands, it can be omitted.

Minimal example:

    version: 0.2

    phases:
      install:
        runtime-versions:
          java: corretto17
      pre_build:
        commands:
          - java -version
          - mvn -version
      build:
        commands:
          - mvn -B -ntp clean verify
      post_build:
        commands:
          - echo "Build completed"

`corretto17` is only an example. The runtime version must be supported by the selected CodeBuild image. Runtime selection in the buildspec is supported on the corresponding standard images; check the image version and runtime list before deploying.

Source: AWS CodeBuild Buildspec reference — https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html

## 4. Choosing a Stable Build Image and Java Runtime

A CodeBuild build environment is a Docker image containing the operating system, runtimes, and tools. You can choose an AWS-managed image or a custom image in Amazon ECR.

For reproducible builds:

- Intentionally select the image family and image version.
- Explicitly declare the Java runtime instead of relying on the default runtime.
- Pin the Maven/Gradle wrapper version in the repository.
- Pin plugin and dependency versions.
- Record the Java version, Maven/Gradle version, and commit SHA in build logs or the build manifest.
- Update images on a tested schedule rather than letting runtimes change unexpectedly.

If no runtime is declared, CodeBuild uses the default runtime included in the image. The default runtime can change when older versions reach end of support.

For Maven, commit the Maven Wrapper (`mvnw`, `.mvn/wrapper/`) so the project defines the Maven version. For Gradle, commit the Gradle Wrapper (`gradlew`, `gradle/wrapper/gradle-wrapper.properties`) so the build agent uses the exact Gradle distribution.

## 5. How Dependency Caching Works

Maven and Gradle both store downloaded dependencies on the build user's filesystem. If CodeBuild can restore that directory before running the build, the build tool can use local dependencies and download only what is missing.

Cache flow:

    Build N
      |
      +-- Resolve dependencies
      +-- Download missing artifacts
      +-- Compile / test / package
      +-- Save selected cache paths
                |
                v
          Cache storage
                |
                v
    Build N+1
      |
      +-- Restore cache paths
      +-- Resolve dependencies
      +-- Download only missing/expired data
      +-- Compile / test / package

Caching does not guarantee offline builds. Maven/Gradle may still need repository access to check metadata, fetch uncached plugins, download new versions, or verify artifacts. A cache miss only causes the build to re-download dependencies; it must not alter the logical output of the build.

Do not use caching to mask repository errors or skip dependency pinning. Builds must succeed from an empty cache in an independent run.

## 6. Two CodeBuild Cache Types

CodeBuild supports two project-level cache types:

| Type | Stored where | Advantages | Limitations |
|---|---|---|---|
| Amazon S3 | S3 bucket/prefix configured in the project | Usable across multiple build hosts | Incurs cache upload/download time; requires S3 permissions |
| Local | CodeBuild build host | Can restore quickly, no S3 transfer | Only usable when the next build runs on a host with the cache; host reuse is not guaranteed |

### 6.1. When to Choose S3 Cache

S3 cache fits when builds frequently run on different hosts, or when the dependency cache is small/medium and re-download cost exceeds cache storage/transfer cost.

S3 cache supports cache keys, fallback keys, versioning, and sharing across projects. When the cache key changes with the dependency descriptor, CodeBuild can store a separate cache for the new dependency set.

### 6.2. When to Choose Local Cache

Local cache is useful for projects that build frequently, have large caches, and are likely to reuse build hosts. It is not suitable if builds run infrequently because the host may no longer retain the cache when the next build starts.

Local cache is not persistent disk storage. Do not rely on it to store release artifacts or data that must always exist.

Source: AWS CodeBuild — Cache builds to improve performance — https://docs.aws.amazon.com/codebuild/latest/userguide/build-caching.html

## 7. Three Local Cache Modes

When selecting cache type `LOCAL`, CodeBuild requires selecting one or more modes:

| Mode | Cached content | When suitable |
|---|---|---|
| `LOCAL_SOURCE_CACHE` | Git metadata of primary/secondary sources | Large repositories where source checkout is time-consuming |
| `LOCAL_DOCKER_LAYER_CACHE` | Existing Docker layers | Building or pulling large Docker images |
| `LOCAL_CUSTOM_CACHE` | Directories specified in the buildspec | Maven/Gradle dependency directories or suitable intermediate folders |

Important notes:

- Docker layer cache supports Linux only and requires privileged mode.
- Privileged mode expands the build container's access to devices; assess security risks carefully.
- Windows does not support privileged mode.
- Custom cache accepts directories only, not individual files.
- Custom cache uses symlinks to reference cached directories.
- Cached directories are linked into the build before CodeBuild downloads the source. Cache contents can overwrite source contents if names collide.
- AWS currently documents that local caching is not supported when a CodeBuild project is configured to run inside a VPC; some compute/environment types also do not support it.

For Java dependency caching, `LOCAL_CUSTOM_CACHE` is usually the appropriate mode. `LOCAL_SOURCE_CACHE` only caches Git metadata and does not replace Maven/Gradle caches. `LOCAL_DOCKER_LAYER_CACHE` is primarily for Docker builds.

Source: AWS CodeBuild — Local caching — https://docs.aws.amazon.com/codebuild/latest/userguide/caching-local.html

## 8. Maven Local Repository

Maven stores downloaded dependencies, plugins, and metadata in the local repository. The default path is:

    ~/.m2/repository

In a typical CodeBuild Linux image running as root, the path is usually:

    /root/.m2/repository

CodeBuild and AWS CodeArtifact provide Maven cache path examples:

    cache:
      paths:
        - '/root/.m2/**/*'

You can narrow the path to cache only the repository:

    cache:
      paths:
        - '/root/.m2/repository/**/*'

The second approach avoids caching other user configuration files in `.m2`, such as `settings.xml` if the build environment stores it there.

Do not cache files containing repository credentials. Use CodeArtifact authorization or a secret provider to retrieve credentials at build time, keep config files with secrets out of the cache, and never print tokens to logs.

Sources:
- AWS CodeArtifact dependency caching — https://docs.aws.amazon.com/codeartifact/latest/ug/dependency-caching.html
- Maven settings — https://maven.apache.org/settings.html

## 9. Gradle Dependency Cache

The default Gradle User Home is:

    ~/.gradle

Module dependencies typically reside in:

    ~/.gradle/caches/modules-2

CodeBuild/AWS CodeArtifact commonly use the path:

    /root/.gradle/caches/**/*

You can cache dependency caches specifically:

    cache:
      paths:
        - '/root/.gradle/caches/**/*'
        - '/root/.gradle/wrapper/dists/**/*'

`caches` contains dependency metadata, downloaded modules, and other Gradle caches. `wrapper/dists` stores the Gradle distribution downloaded by the Wrapper. If the build project sets a different `GRADLE_USER_HOME`, adjust cache paths to match that variable.

Do not carelessly cache the entire home directory. `.gradle/gradle.properties` may contain credentials; `init.d` may contain custom scripts. Keep cache paths scoped to only the required dependency directories.

### 9.1. Dependency Cache vs. Gradle Build Cache

Gradle has at least two distinct concepts to separate:

- **Dependency cache:** stores POM/module metadata and dependency artifacts to avoid re-downloading.
- **Build cache:** stores task outputs keyed by input hash, avoiding re-executing tasks when inputs are unchanged.

Build cache can be enabled for a single run:

    ./gradlew --build-cache build

Or enabled in `gradle.properties`:

    org.gradle.caching=true

If you only cache dependency directories, Gradle may still need to compile/test on every build. To reuse task outputs, enable and configure the Gradle build cache properly. CodeBuild S3 cache can save the `build-cache-1` directory inside Gradle User Home, but this remains a local cache transferred via S3 rather than automatically creating a dedicated remote Gradle Build Cache.

Sources:
- Gradle dependency caching — https://docs.gradle.org/current/userguide/dependency_caching.html
- Gradle build cache — https://docs.gradle.org/current/userguide/build_cache.html
- Gradle directory layout — https://docs.gradle.org/current/userguide/directory_layout.html

## 10. Cache Keys and Dependency Descriptors

The cache key identifies the cache snapshot CodeBuild looks up to restore. If only a static key is used, dependency changes may reuse an outdated cache. It is better to derive the key from dependency descriptor files.

Maven example:

    cache:
      key: "maven-java17-$(codebuild-hash-files '**/pom.xml')"
      fallback-keys:
        - maven-java17-
        - maven-
      paths:
        - '/root/.m2/repository/**/*'

Gradle example:

    cache:
      key: "gradle-java17-$(codebuild-hash-files '**/build.gradle*' '**/settings.gradle*' 'gradle/libs.versions.toml' 'gradle.lockfile' 'gradle/wrapper/gradle-wrapper.properties')"
      fallback-keys:
        - gradle-java17-
        - gradle-
      paths:
        - '/root/.gradle/caches/**/*'
        - '/root/.gradle/wrapper/dists/**/*'

`codebuild-hash-files` is a CodeBuild utility that computes a SHA-256 hash over files matching globs. When dependency descriptors change, the key changes and CodeBuild stores a new cache under that key.

For multi-module Maven projects, hashing all `pom.xml` files detects changes in submodules. When using the Maven Wrapper, include `.mvn/wrapper/maven-wrapper.properties` in the hash list. For Gradle, include version catalogs, lockfiles, settings/build scripts, and wrapper properties in the key.

### 10.1. Fallback Keys

CodeBuild searches for the primary key first. If there is no exact match, CodeBuild tries each fallback key in order via prefix search. The build can restore the closest older cache and then save a cache under the new primary key.

Up to five fallback keys are supported. `fallback-keys` is ignored if `key` is not specified.

Do not use overly broad fallback keys across incompatible runtimes or projects with different trust boundaries. For example, do not share a Maven cache between Java 8 and Java 21 if plugins/dependencies or native artifacts may differ.

### 10.2. Cache Keys Do Not Replace Dependency Locking

A cache key is a cache lookup mechanism, not proof that dependencies are pinned or their integrity is verified.

- Maven: declare explicit versions, manage plugin versions, and avoid uncontrolled `SNAPSHOT` dependencies.
- Gradle: use dependency locking/version catalogs and dependency verification when appropriate.
- Changing the dependency graph must change the cache key.
- When suspecting cache issues, run an uncached build or clear the cache per procedure to compare.

Source: AWS CodeBuild — S3 caching and cache keys — https://docs.aws.amazon.com/codebuild/latest/userguide/caching-s3.html

## 11. S3 Cache in Buildspec

The project must be configured with cache type S3 pointing to a cache bucket/prefix. The buildspec defines the key and paths.

Example CloudFormation project configuration:

    Cache:
      Type: S3
      Location: company-codebuild-cache
      CacheNamespace: java-builds

Buildspec section:

    version: 0.2

    phases:
      build:
        commands:
          - mvn -B -ntp verify

    cache:
      key: "maven-java17-$(codebuild-hash-files '**/pom.xml')"
      fallback-keys:
        - maven-java17-
      paths:
        - '/root/.m2/repository/**/*'

If `cache.paths` is not declared, CodeBuild may perform best-effort caching of some common dependencies, but declaring it explicitly makes behavior easier to review and predict.

Available cache fields:

| Field | Meaning |
|---|---|
| `key` | Primary key matched exactly |
| `fallback-keys` | Prefix keys searched sequentially on primary miss |
| `action: restore` | Restore only, do not save changes |
| `action: save` | Save only, do not restore |
| `paths` | Files/directories included in the cache |

If `action` is omitted, CodeBuild defaults to both restore and save.

S3 caches can be shared across projects when they use the same `CacheNamespace`, same `key`, same `cache.paths`, and same S3 bucket/prefix. Share caches only among projects with equivalent dependencies/toolchains and trust levels.

## 12. Local Custom Cache for Maven

If the project uses local caching, select `LOCAL_CUSTOM_CACHE` in the CodeBuild project's cache section. CloudFormation example:

    Cache:
      Type: LOCAL
      Modes:
        - LOCAL_CUSTOM_CACHE

Buildspec declares the path:

    version: 0.2

    phases:
      install:
        runtime-versions:
          java: corretto17
      build:
        commands:
          - mvn -B -ntp clean verify

    cache:
      paths:
        - '/root/.m2/repository/**/*'

Local custom cache only works when the project enables the matching mode. Adding `cache.paths` in the buildspec when the project uses `NO_CACHE` will not create a cache.

## 13. Complete Maven Buildspec

Example for a Spring Boot project whose Maven `finalName` is `orders-api`, where Surefire/Failsafe output JUnit XML and the executable JAR is at `target/orders-api.jar`.

    version: 0.2

    phases:
      install:
        runtime-versions:
          java: corretto17

      pre_build:
        commands:
          - java -version
          - mvn -version
          - echo "Starting Maven verification"

      build:
        commands:
          - mvn -B -ntp clean verify

      post_build:
        commands:
          - test -f target/orders-api.jar
          - sha256sum target/orders-api.jar > target/orders-api.jar.sha256
          - echo "Maven build completed"

    reports:
      junit:
        files:
          - 'target/surefire-reports/TEST-*.xml'
          - 'target/failsafe-reports/TEST-*.xml'
        file-format: JUNITXML

    artifacts:
      files:
        - 'target/orders-api.jar'
        - 'target/orders-api.jar.sha256'
      discard-paths: yes
      name: orders-api-$CODEBUILD_BUILD_NUMBER

    cache:
      key: "maven-java17-$(codebuild-hash-files '**/pom.xml')"
      fallback-keys:
        - maven-java17-
      paths:
        - '/root/.m2/repository/**/*'

Points to adjust:

- `orders-api.jar` must match the actual filename generated by Maven. If not using `finalName`, replace with the exact `artifactId-version`.
- If multi-module, include only the executable module in the primary artifact or declare secondary artifacts.
- `clean verify` runs the lifecycle up to verify, including compile, test, and package per the Maven project configuration.
- `-B` enables batch mode; `-ntp` disables transfer progress to keep logs concise.
- `sha256sum` is an example for Linux build images.
- `reports` uses the actual XML paths created by Surefire/Failsafe plugins.

## 14. Complete Gradle Buildspec

Example for a Spring Boot Gradle project whose `bootJar` task produces `build/libs/orders-api.jar`:

    version: 0.2

    phases:
      install:
        runtime-versions:
          java: corretto17

      pre_build:
        commands:
          - java -version
          - ./gradlew --version
          - echo "Starting Gradle verification"

      build:
        commands:
          - ./gradlew --no-daemon clean test bootJar

      post_build:
        commands:
          - test -f build/libs/orders-api.jar
          - sha256sum build/libs/orders-api.jar > build/libs/orders-api.jar.sha256
          - echo "Gradle build completed"

    reports:
      junit:
        files:
          - '**/build/test-results/test/*.xml'
        file-format: JUNITXML

    artifacts:
      files:
        - 'build/libs/orders-api.jar'
        - 'build/libs/orders-api.jar.sha256'
      discard-paths: yes
      name: orders-api-$CODEBUILD_BUILD_NUMBER

    cache:
      key: "gradle-java17-$(codebuild-hash-files '**/build.gradle*' '**/settings.gradle*' 'gradle/libs.versions.toml' 'gradle.lockfile' 'gradle/wrapper/gradle-wrapper.properties')"
      fallback-keys:
        - gradle-java17-
      paths:
        - '/root/.gradle/caches/**/*'
        - '/root/.gradle/wrapper/dists/**/*'

`bootJar` requires the Spring Boot Gradle plugin. For Java applications without Spring Boot, the packaging task may be `jar`. If building multiple modules, adjust report globs and artifact paths to match the project layout.

`--no-daemon` avoids relying on a daemon persisting across build containers. Gradle can still use the dependency cache and build cache inside Gradle User Home.

## 15. Packaging JAR/WAR Files Properly

A successful build command is not enough; you must identify which file is the releasable product.

| Application type | Typical artifact | Notes |
|---|---|---|
| Java library | JAR | May also need sources JAR, javadoc JAR, and POM |
| Spring Boot service | Executable JAR | Check manifest and boot loader |
| Traditional Java web app | WAR | Must match the target application server |
| Java Lambda | ZIP/JAR or shaded JAR | Follow the runtime/handler packaging model |
| Containerized service | Docker image in ECR | Image digest is usually a better deploy identifier than mutable tags |

Do not use `artifacts.files: - '**/*'` for release artifacts if the source tree contains `.git`, caches, test reports, secret files, or intermediate build files. Select only the exact files needed by downstream stages.

With Spring Boot Maven, the plugin typically builds the executable JAR in `target`. With Gradle, `bootJar` creates the executable JAR in `build/libs`. Verify the actual output file and ensure stable naming before configuring artifacts.

### 15.1. Artifact Name and Versioning

You can include the build number in the artifact name:

    artifacts:
      name: orders-api-$CODEBUILD_BUILD_NUMBER
      files:
        - 'target/orders-api.jar'

Artifact names can be computed at build time using shell syntax or CodeBuild environment variables. Combining the build number with the commit SHA or release version aids build traceability.

Do not overwrite approved release artifacts. Use a versioned S3 bucket, S3 versioning, or immutable naming conventions per release policy.

### 15.2. Artifact Path and base-directory

`artifacts.files` accepts paths relative to the source build directory or `base-directory`. Example:

    artifacts:
      base-directory: target
      files:
        - orders-api.jar
        - orders-api.jar.sha256

`discard-paths: yes` flattens the directory structure. Enable it only when module layout does not need to be preserved. If multiple files in different directories share the same name, flattening can cause collisions; keep default paths when disambiguation is needed.

## 16. Test Reports and Coverage Reports

CodeBuild can collect reports from test/coverage files produced by the build tool.

With Maven Surefire, test reports usually reside in:

    target/surefire-reports/TEST-*.xml

With Maven Failsafe:

    target/failsafe-reports/TEST-*.xml

With Gradle:

    build/test-results/test/*.xml

JUnit report example:

    reports:
      junit:
        files:
          - 'target/surefire-reports/TEST-*.xml'
        file-format: JUNITXML

CodeBuild supports several test report formats such as JUnit XML, NUnit, TestNG, and Visual Studio TRX. For coverage, CodeBuild supports formats such as JaCoCo XML and Cobertura XML.

Reports vs. artifacts:

- Reports are collected by CodeBuild to display test/coverage results.
- Artifacts are packaged and sent to S3/CodePipeline or a configured destination.
- The same file can be used as a report and also packaged if needed, but the two configurations serve different purposes.

Do not use `on-failure: CONTINUE` to ignore test failures and publish artifacts as if the build passed. If tests fail, the release pipeline should halt per quality gates.

Source: AWS CodeBuild Buildspec reference — https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html

## 17. Multi-Module Maven and Gradle

For monorepos or multi-module projects, the cache key must reflect the entire dependency graph. Hashing only the root POM or root build file may miss changes in submodules.

Maven:

    cache:
      key: "maven-$(codebuild-hash-files '**/pom.xml' '.mvn/wrapper/maven-wrapper.properties')"
      paths:
        - '/root/.m2/repository/**/*'

Gradle:

    cache:
      key: "gradle-$(codebuild-hash-files '**/build.gradle*' '**/settings.gradle*' '**/gradle.lockfile' 'gradle/libs.versions.toml' 'gradle/wrapper/gradle-wrapper.properties')"
      paths:
        - '/root/.gradle/caches/**/*'
        - '/root/.gradle/wrapper/dists/**/*'

If each service has an independent dependency graph, consider separate cache keys per service path, project name, or namespace. This prevents project A from reducing project B's cache effectiveness or mixing dependency contexts.

With multi-module Maven, builds may produce multiple JARs. Select only the module to release, rather than uploading every JAR if the pipeline deploys only one service.

## 18. Using CodeArtifact as a Private Dependency Source

AWS CodeArtifact can serve as a Maven/Gradle package repository for internal dependencies and a proxy/upstream for public packages. CodeBuild caching reduces repeated downloads; CodeArtifact controls package sources, versions, and access permissions.

Flow:

    CodeBuild service role
          |
          | Get authorization token
          v
      CodeArtifact
          |
          | Maven / Gradle resolve
          v
      Local dependency cache
          |
          v
      Compile / test / package

With CodeArtifact, the build role typically needs permissions to retrieve an authorization token and read packages from the repository. If using a KMS customer-managed key, corresponding permissions are required. Do not hard-code tokens into `pom.xml`, `settings.xml`, `build.gradle`, or the buildspec.

CodeBuild buildspecs support retrieving environment variables from Parameter Store and Secrets Manager. However, secret masking only hides exact stored values; if a command encodes, changes case, or concatenates a secret into another string, logs may fail to redact the transformed string. Avoid `set -x`, shell tracing, and printing all environment variables.

## 19. Securing Caches and Preventing Cache Poisoning

Caches can contain artifacts downloaded or produced by previous builds. If multiple branches/projects with different trust levels share a cache, an untrusted build could write data that compromises subsequent builds.

Principles:

- Separate cache namespaces and S3 prefixes between production/release branches and untrusted pull requests.
- Do not share writable caches between fork/untrusted PRs and release pipelines.
- Restrict the IAM service role to read/write only the required cache prefix.
- Enable encryption on the cache bucket; use SSE-S3 or SSE-KMS as required.
- Do not cache `settings.xml`, `gradle.properties`, credential files, private keys, or tokens.
- Do not store secrets in artifacts or test reports.
- Pin dependency and plugin versions; verify checksums/signatures when supported by the ecosystem.
- Use lockfiles and dependency verification to detect unexpected changes in the dependency graph or artifacts.
- Do not allow build jobs to write to the production cache if the job only runs tests from untrusted branches.

### 19.1. Maven Cache and Gradle User Home

The Maven local repository usually contains JARs/POMs and metadata, whereas `~/.m2/settings.xml` can contain repository credentials. Cache only `repository/**/*` when appropriate.

Gradle User Home can contain `gradle.properties`, `init.d` scripts, and cache metadata. Cache only the necessary dependency directories; do not blindly cache all of `/root/.gradle/**/*`.

### 19.2. Cache and Build Isolation

Builds should not read caches written by untrusted principals. Separate CodeBuild projects, service roles, and cache namespaces by trust boundary, or use separate S3 buckets/prefixes. For higher assurance, run a clean uncached build before major releases and compare artifact checksums.

## 20. Caching, Reproducibility, and Dependency Freshness

Caching improves speed but must not make builds non-deterministic.

Maven and Gradle have specific rules for dynamic/changing dependencies. `SNAPSHOT`, version ranges, and dynamic versions can be refreshed per policy/TTL. If a pipeline uses these dependencies, the same commit may resolve to different contents at two different times.

For reproducible builds:

1. Pin dependency versions.
2. Pin plugin and build tool versions.
3. Use Maven Wrapper/Gradle Wrapper.
4. Use Gradle dependency locking and verification when appropriate.
5. Avoid version ranges and `SNAPSHOT` in release builds without controls.
6. Record commit SHA, runtime version, and artifact checksum.
7. Periodically run builds with an empty cache to verify reproducibility.

`mvn -o` and `gradle --offline` should only be used when you are certain the cache contains all required dependencies/plugins. Do not enable offline mode by default for builds that need to resolve new dependencies.

## 21. Measuring Cache Effectiveness

Do not just enable caching and assume builds are faster. Compare before and after using metrics.

| Metric | Meaning |
|---|---|
| Build duration | Total build time |
| Dependency resolution time | Time spent by Maven/Gradle resolving dependencies |
| Downloaded bytes | Data downloaded from repositories |
| Cache restore/save duration | Overhead of downloading and saving the cache |
| Cache hit/miss | Key match rate and cache availability |
| Test duration | Time to run tests, not necessarily reduced by dependency caching |
| Build failure rate | Detects cache-induced errors or stale data |
| S3 storage/requests | Cache operational cost |

Caching helps when restore cost is lower than re-download/re-compilation cost. If the cache is very large while builds run infrequently, S3 transfer or local host misses may prevent overall time improvements.

Measure at least one set of cold-cache builds and one set of warm-cache builds with equivalent source/dependencies. Do not compare builds that differ in test count, runtime, compute type, or dependency graph.

## 22. Troubleshooting Common Errors

### 22.1. Cache Is Not Restored

Check:

- Whether the project cache type is S3/LOCAL as intended.
- For local cache, whether `LOCAL_CUSTOM_CACHE` mode is enabled.
- Whether the cache path matches the user home and build image.
- Whether `GRADLE_USER_HOME` or the Maven local repository has been overridden.
- Whether the S3 role has permissions for the bucket/prefix and KMS key.
- Whether the cache key changed due to hashed descriptors.
- Whether the build host was reused when using local cache.

### 22.2. Cache Restores but Maven Still Downloads Dependencies

Maven may need fresh metadata, uncached plugins, changed dependency versions, or artifacts missing from the local repository. Inspect with `mvn -X` in a controlled debug run; avoid enabling debug logs permanently if they could print sensitive details.

### 22.3. Gradle Still Resolves/Downloads Heavily

Check `GRADLE_USER_HOME`, Gradle Wrapper, lockfiles, repository configuration, dynamic versions, and cache paths. Gradle may need to refresh metadata per TTL or the build may be using a Gradle version with a different cache format.

### 22.4. Build Passes but Artifact Does Not Exist

Check Maven `finalName`, Gradle `bootJar`/`jar`, the module being built, actual output paths, and `artifacts.files`. Commands like `find target -maxdepth 2 -type f` or `find build/libs -maxdepth 1 -type f` can help debug on Linux images, but do not include the whole output directory in release artifacts without filtering.

### 22.5. Test Reports Do Not Appear

Check whether Surefire/Failsafe/Gradle generated XML files, whether the path glob matches, whether the file format is JUnit XML, and whether tests actually ran. If tests were skipped or the build failed before the test phase, reports may not exist.

### 22.6. Cache Causes Errors or Inconsistent Results

Try an uncached build. If a clean build succeeds while a warm-cache build fails, check whether the cache path includes stale outputs, changed dependency metadata, build tool version mismatches, or contamination from another build. Generate a new cache key after fixing dependencies/toolchain.

## 23. Scenario Exercises

### Exercise A — Maven Re-Downloads All Dependencies on Every Build

The CodeBuild project uses S3 cache, but the buildspec has no `cache.paths`.

**Answer:** Declare `/root/.m2/repository/**/*` or the actual local repository path in `cache.paths`, then verify the project cache type is S3 and the IAM role has permissions.

### Exercise B — Gradle Cache Is Not in `/root/.gradle`

The project sets `GRADLE_USER_HOME=/opt/gradle-home`.

**Answer:** Update the cache path to `/opt/gradle-home/caches/**/*` and wrapper distributions if needed.

### Exercise C — Local Cache Does Not Work in a VPC Project

The build project runs inside a VPC with local custom cache enabled.

**Answer:** Per current CodeBuild limitations, local caching is not supported when a project is configured to run in a VPC. Consider S3 cache.

### Exercise D — CodeBuild Runs Linux Docker Layer Cache

The project enables `LOCAL_DOCKER_LAYER_CACHE`, but privileged mode is disabled.

**Answer:** Docker layer caching requires Linux and privileged mode. Evaluate security implications before enabling privileged mode.

### Exercise E — Cache Key Never Changes Despite Dependency Updates

The cache key is simply `maven-java17`.

**Answer:** Include hashes of POMs/lockfiles/build descriptors in the key so changes to the dependency graph produce a new cache key.

### Exercise F — Fork Build Writes to a Cache Shared with Releases

An untrusted PR build uses the same S3 cache namespace and write permissions as production.

**Answer:** Separate cache namespaces/bucket prefixes and IAM roles by trust boundary. Do not let untrusted PRs write to caches consumed by release builds.

### Exercise G — `settings.xml` Gets Cached

A developer caches all of `/root/.m2/**/*`; the settings file contains a server password.

**Answer:** Narrow the cache path to `/root/.m2/repository/**/*`, fetch credentials from a secret provider, and rotate the exposed credential.

### Exercise H — `artifacts.files` Uses `**/*`

The output ZIP contains source code, test reports, and unnecessary configuration files.

**Answer:** List only the exact JAR/WAR, checksums, and manifests needed for release; do not bundle the entire source directory.

### Exercise I — Maven Build Passes but CodeBuild Does Not Upload the JAR

Maven produces `target/payment-service-1.2.0.jar`, while the buildspec points to `target/app.jar`.

**Answer:** Fix the artifact path to match the actual file or configure a stable `finalName`.

### Exercise J — Gradle Reports Do Not Appear

The buildspec points to `target/surefire-reports`, even though the project uses Gradle.

**Answer:** Use `build/test-results/test/*.xml` and file format `JUNITXML`.

### Exercise K — Offline Mode Used on an Empty Cache

The build fails because plugins are missing from the local cache.

**Answer:** Remove offline mode and allow dependency resolution/downloads. Use offline mode only when the cache is fully pre-seeded and explicitly intended.

### Exercise L — Artifact Changes Under the Same Version

Two builds produce `orders-api-1.0.0.jar` with different contents and upload under the same name.

**Answer:** Name/version artifacts by build or commit, retain checksums, enable versioning/immutable release policies, and never overwrite approved releases.

## 24. Review Questions

1. What is a buildspec and where does CodeBuild look for it by default?
2. Why should buildspec version 0.2 be used?
3. What are the four main phases of a buildspec?
4. How does a dependency cache differ from a build artifact?
5. What are the two primary CodeBuild cache types?
6. How does S3 cache differ from local cache?
7. What does `LOCAL_SOURCE_CACHE` store?
8. What conditions does `LOCAL_DOCKER_LAYER_CACHE` require?
9. Can `LOCAL_CUSTOM_CACHE` cache a single individual file?
10. Does local cache work in every VPC CodeBuild project?
11. Where is the Maven local repository located by default?
12. Where is the Gradle dependency cache located by default?
13. Why should the entire Maven/Gradle user home not be cached?
14. Which files should a cache key be based on?
15. What does `codebuild-hash-files` do?
16. How are fallback keys searched?
17. What is the maximum number of fallback keys?
18. Does `cache/action: restore` save a new cache?
19. Why do cache keys not replace dependency locking?
20. Does Maven `verify` include the package lifecycle phase?
21. When is Gradle `bootJar` used?
22. Where is Maven Surefire XML usually located?
23. Where is Gradle JUnit XML usually located?
24. What does `artifacts.files` specify?
25. How does `discard-paths: yes` alter artifact structure?
26. Why should `**/*` not be used for all release artifacts?
27. What role does CodeArtifact play in dependency management?
28. Why should repository tokens not be stored in the buildspec?
29. How can cache poisoning affect a release pipeline?
30. When should an uncached build be run?

**Quick answers:** (1) YAML instructions for building, defaulting to the source root; (2) commands in the same phase share a shell context; (3) `install`, `pre_build`, `build`, `post_build`; (4) cache speeds up builds, whereas artifacts are outputs passed between stages; (5) S3 and `LOCAL`; (6) S3 is shared across hosts, while local is tied to the build host; (7) Git metadata; (8) Linux and privileged mode; (9) no, directories only; (10) no; (11) `~/.m2/repository`; (12) `~/.gradle/caches`; (13) it may contain settings/credentials/scripts; (14) POM, Gradle scripts, version catalogs, lockfiles, wrapper properties; (15) generates a SHA-256 hash of files matching globs; (16) sequential prefix searches after a primary miss; (17) five; (18) no; (19) keys only locate caches, they do not pin the dependency graph; (20) yes; (21) Spring Boot executable JARs; (22) `target/surefire-reports`; (23) `build/test-results/test`; (24) files to be uploaded; (25) flattens directory paths; (26) it can include source/secrets/intermediate build outputs; (27) private package repository/proxy; (28) to avoid exposing credentials; (29) untrusted builds could poison caches used by releases; (30) to test reproducibility or investigate cache issues.

## 25. Production Checklist

- [ ] Buildspec uses version 0.2.
- [ ] CodeBuild image and Java runtime are intentionally selected and pinned.
- [ ] Maven Wrapper or Gradle Wrapper is committed and its version is pinned.
- [ ] Maven/Gradle dependency versions and plugins are explicitly managed.
- [ ] Cache type (`S3`/`LOCAL`) fits build frequency and environment.
- [ ] Cache paths match the actual Maven local repository or Gradle User Home.
- [ ] Cache keys hash dependency descriptors/lockfiles.
- [ ] Fallback keys do not cross project/runtime/trust boundaries.
- [ ] `settings.xml`, `gradle.properties` containing secrets, and private keys are never cached.
- [ ] S3 cache bucket/prefix has encryption and least-privilege IAM.
- [ ] Local cache mode is accurate and satisfies VPC/compute/image constraints.
- [ ] Docker layer cache is enabled only when genuinely needed and privileged mode has been reviewed.
- [ ] Builds succeed starting from an empty cache.
- [ ] Release builds do not depend on uncontrolled `SNAPSHOT`/dynamic dependencies.
- [ ] Maven/Gradle build commands run tests and packaging in the proper lifecycle.
- [ ] Test reports point to the correct XML output paths.
- [ ] Artifacts contain only the JAR/WAR/checksums/manifests required for release.
- [ ] Artifact names include a build identity or release version.
- [ ] Artifact output bucket is encrypted and has appropriate retention/versioning.
- [ ] Caches are never used in place of an artifact repository or release storage.
- [ ] Build logs do not print tokens, secrets, or the entire environment.
- [ ] Cold-cache/warm-cache metrics exist and cache hit/miss rates are tracked.
- [ ] A process exists to rotate cache keys or run uncached builds when cache corruption is suspected.

## 26. Summary

AWS CodeBuild caching and artifact packaging address two distinct needs in Java CI/CD:

- Caching Maven/Gradle dependencies reduces repeated downloads.
- S3 caches work across multiple build hosts; local caches can be faster but depend on build hosts and cache modes.
- `LOCAL_SOURCE_CACHE` stores Git metadata, `LOCAL_DOCKER_LAYER_CACHE` stores Docker layers, and `LOCAL_CUSTOM_CACHE` stores directories specified in the buildspec.
- Maven typically uses `/root/.m2/repository`; Gradle typically uses `/root/.gradle/caches`.
- Cache keys should change with POMs, Gradle scripts, version catalogs, lockfiles, and wrapper versions.
- Caching does not replace dependency locking, checksum verification, or the ability to build from an empty cache.
- Buildspec version 0.2 defines phases, test reports, and artifact outputs.
- Artifacts must specify the exact executable JAR/WAR passed to the next stage; test reports are configured separately.
- S3 caches require IAM, encryption, and segmentation by trust boundary; never let untrusted PRs write caches consumed by production releases.
- Measure cold-cache/warm-cache builds to confirm caching truly saves time and cost.

A solid Java pipeline produces traceable, testable, and reproducible artifacts from controlled source and dependencies. Caching simply helps the pipeline do it faster.

### Official AWS and Vendor Documentation

1. AWS CodeBuild buildspec reference: https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html
2. AWS CodeBuild cache builds: https://docs.aws.amazon.com/codebuild/latest/userguide/build-caching.html
3. AWS CodeBuild S3 caching: https://docs.aws.amazon.com/codebuild/latest/userguide/caching-s3.html
4. AWS CodeBuild local caching: https://docs.aws.amazon.com/codebuild/latest/userguide/caching-local.html
5. Specify a local cache: https://docs.aws.amazon.com/codebuild/latest/userguide/specify-caching-local.html
6. Create a CodeBuild project: https://docs.aws.amazon.com/codebuild/latest/userguide/create-project.html
7. Getting started with CodeBuild: https://docs.aws.amazon.com/codebuild/latest/userguide/getting-started-overview.html
8. AWS CodeArtifact dependency caching: https://docs.aws.amazon.com/codeartifact/latest/ug/dependency-caching.html
9. Maven settings reference: https://maven.apache.org/settings.html
10. Maven local repository configuration: https://maven.apache.org/guides/mini/guide-configuring-maven.html
11. Gradle dependency caching: https://docs.gradle.org/current/userguide/dependency_caching.html
12. Gradle build cache: https://docs.gradle.org/current/userguide/build_cache.html
13. Gradle directory layout: https://docs.gradle.org/current/userguide/directory_layout.html
14. Gradle security guidance: https://docs.gradle.org/current/userguide/securing_builds.html
