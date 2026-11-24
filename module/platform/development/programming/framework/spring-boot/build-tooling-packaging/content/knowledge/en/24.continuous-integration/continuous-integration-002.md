# Using Wrappers and Pinning the Build Environment on CI Runners

## 1. Objective

A Java project often runs smoothly on a developer's laptop yet fails in CI because each environment uses a different Gradle, Maven, or JDK version. For instance, a developer uses Gradle 8.8 and JDK 17 while the runner has Gradle 8.5 and JDK 21 installed; the build script, compiler, plugins, or test runtime can produce different results.

A **Wrapper** solves selecting the right build tool version: the Gradle Wrapper runs the Gradle distribution declared in the repository, and the Maven Wrapper runs the Maven distribution declared in the repository. **Pinning the CI environment** also requires controlling JDK vendor/major/patch, OS/architecture, plugin/dependency versions, repository inputs, build parameters, and environment variables that affect output.

This lesson breaks the problem into three layers:

1. **Build tool:** Gradle Wrapper or Maven Wrapper pins the Gradle/Maven version and can verify the distribution checksum.
2. **Java toolchain:** selects the JDK used to run the build tool, compile source code, run tests, and emit target bytecode.
3. **CI execution environment:** pins the runner/container, architecture, action versions, dependency resolution, environment variables, secrets, and cache policy.

~~~text
Source repository
  ├─ gradlew / gradlew.bat
  ├─ gradle/wrapper/gradle-wrapper.properties
  ├─ mvnw / mvnw.cmd
  ├─ .mvn/wrapper/maven-wrapper.properties
  ├─ build.gradle(.kts) / pom.xml
  ├─ dependency locks + verification metadata
  └─ CI workflow
          │
          ▼
Controlled CI runner/container
  ├─ OS + architecture
  ├─ JDK vendor/version
  ├─ Gradle/Maven Wrapper
  ├─ plugins + dependency inputs
  └─ environment/build parameters
          │
          ▼
clean build + tests + executable Spring Boot JAR
          │
          ▼
artifact checksum / image / release
~~~

After this lesson, you will be able to generate/update a Wrapper properly, verify its distribution, execute builds via the Wrapper in CI, lock the Java compiler target, lock dependency versions, audit caches, and record the build environment to reproduce failures.

**Illustrative versions:** Spring Boot 3.3.13, Java 17, and Gradle 8.8 / Maven 3.9.9. These versions form a consistent training baseline; they are not claims about the latest releases. When applying this to a real repository, choose versions compatible with your plugins, dependencies, and current security update policy.

## 2. Why Must CI Use the Wrapper?

If a workflow invokes:

~~~bash
gradle clean test bootJar
~~~

it uses whatever Gradle is pre-installed on the runner or on `PATH`. Another runner may have a different version installed. With the same repository, build results end up depending on an environment outside source control.

With the Gradle Wrapper:

~~~bash
./gradlew clean test bootJar
~~~

The Wrapper reads `gradle/wrapper/gradle-wrapper.properties`, downloads the exact distribution if not already cached, and runs the Gradle version declared by the project. On Windows:

~~~powershell
.\gradlew.bat clean test bootJar
~~~

Maven works the same way. Replace:

~~~bash
mvn clean verify
~~~

with:

~~~bash
./mvnw -B -ntp clean verify
~~~

On Windows:

~~~powershell
.\mvnw.cmd -B -ntp clean verify
~~~

**The Wrapper does not pin the entire environment on its own:** it pins the build tool distribution, not the JDK patch, OS, CPU architecture, Maven/Gradle plugins, dependencies, or CI actions. Therefore, the Wrapper is the first foundation of build repeatability, not the sole solution.

### 2.1. Wrapper Files That Must Be Committed

| Tool | Files Typically Required in Repository | Role |
| --- | --- | --- |
| Gradle | `gradlew`, `gradlew.bat` | Launcher scripts |
| Gradle | `gradle/wrapper/gradle-wrapper.jar` | Wrapper bootstrap code |
| Gradle | `gradle/wrapper/gradle-wrapper.properties` | Distribution URL/checksum |
| Maven | `mvnw`, `mvnw.cmd` | Launcher scripts |
| Maven | `.mvn/wrapper/maven-wrapper.properties` | Maven distribution/wrapper configuration |
| Maven | Wrapper JAR if the wrapper type uses a JAR | Bootstrap code |

The exact Maven Wrapper file layout depends on the wrapper type and version. If using the `only-script` type, the set of files differs from the wrapper JAR type. Commit **all files required by the configured wrapper type**; do not delete the wrapper JAR simply because another project uses `only-script`.

Do not regenerate the wrapper on every CI job. CI must use the exact wrapper reviewed and committed alongside the source code. Upgrading the Gradle/Maven Wrapper should be a reviewed change with tests and updated checksums.

## 3. Gradle Wrapper: Configuring and Verifying the Distribution

### 3.1. Creating or Upgrading the Wrapper

If Gradle is installed locally, run from the project root:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

This command creates or updates the wrapper files to use the Gradle 8.8 binary distribution. If a project does not yet have a wrapper, a suitable local Gradle installation is needed for initial creation; afterward, CI only invokes `./gradlew`.

You can pass the distribution checksum when generating the wrapper (if the task/Gradle version supports that option):

~~~bash
gradle wrapper \
  --gradle-version 8.8 \
  --distribution-type bin \
  --gradle-distribution-sha256-sum "$GRADLE_DIST_SHA256"
~~~

`GRADLE_DIST_SHA256` must hold the **official** SHA-256 of the exact `gradle-8.8-bin.zip` file, obtained from Gradle's checksum page via a trusted channel. Never pull checksums from an unverified mirror or enter placeholder strings.

### 3.2. Contents of gradle-wrapper.properties

Example `gradle/wrapper/gradle-wrapper.properties`:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.8-bin.zip
distributionSha256Sum=OFFICIAL_SHA256_FOR_EXACT_GRADLE_8_8_BIN_ZIP
networkTimeout=10000
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

In a real file, replace `distributionSha256Sum` with the official 64-character hex checksum. The uppercase placeholder merely marks where the value goes—it is **not a valid checksum to commit**. This lesson does not fabricate distribution checksums.

- `distributionUrl` specifies the Gradle distribution archive to download. Use HTTPS and a fixed version.
- `distributionSha256Sum` makes the Wrapper verify the downloaded distribution ZIP; if the checksum mismatches, using the distribution is rejected.
- `networkTimeout` sets the download timeout in milliseconds.
- `distributionType=bin` in the wrapper command picks the smaller binary distribution over `all`; `all` includes sources and docs useful for IDE attachments, which are unnecessary for standard CI builds.

Never use dynamic URLs like `gradle-8.+-bin.zip` or `latest` for release builds; dynamic versions cause unintended build tool shifts.

### 3.3. Verifying the Wrapper Runs the Right Version

~~~bash
./gradlew --version
~~~

The output should report Gradle 8.8 per the example along with the JVM running Gradle. That Java version may differ from the compile toolchain if the project configures Gradle toolchains.

To inspect the JDK toolchains detected by Gradle:

~~~bash
./gradlew javaToolchains
~~~

This task is useful when the Java plugin is applied. It shows the candidate JDKs/toolchains Gradle can use, though it does not prove that the production runtime container uses the same JVM.

### 3.4. Validating the Wrapper JAR

`gradle-wrapper.jar` is executable bootstrap code, so treat it as a controlled component. Use the Gradle Wrapper Validation Action in CI or an equivalent validation step to detect an invalid or tampered wrapper JAR.

Example GitHub Actions step (illustrative major version):

~~~yaml
- name: Validate Gradle Wrapper
  uses: gradle/actions/wrapper-validation@v4
~~~

For workflows with strict supply-chain requirements, pin actions by **reviewed full commit SHA**, not just a mutable tag. Check the action's documentation to pick the organization-approved version.

### 3.5. Controlled Wrapper Upgrades

When upgrading Gradle:

1. Check the Gradle compatibility matrix against the JDK, Spring Boot plugin, Kotlin plugin, and other plugins.
2. Run the wrapper command using an appropriate local Gradle version.
3. Record the official checksum for the exact distribution.
4. Review diffs of the properties, scripts, and wrapper JAR.
5. Run `./gradlew --version` to confirm.
6. Run a clean build and tests on the target CI JDK.
7. Commit the wrapper update with a release note or PR explaining the version change.

Do not merely edit a number in the properties file and forget the wrapper bootstrap JAR/scripts when the project needs them updated for the new Wrapper version.

## 4. Maven Wrapper: Pinning the Maven Distribution

### 4.1. Creating the Maven Wrapper

If Maven is already installed locally, you can generate the wrapper from the project root using the Maven Wrapper Plugin. Example with a pinned plugin version:

~~~bash
mvn org.apache.maven.plugins:maven-wrapper-plugin:3.3.2:wrapper -Dmaven=3.9.9
~~~

This generates wrapper files for Maven 3.9.9 according to the configured wrapper type. Afterward, commit the wrapper scripts and the `.mvn/wrapper` directory alongside the source code.

Plugin version `3.3.2` and Maven `3.9.9` are illustrative baselines. When upgrading, check plugin compatibility and choose a version approved by your organization. Never let CI run `mvn wrapper:wrapper` automatically and create a new wrapper depending on the runner.

### 4.2. maven-wrapper.properties

Example `.mvn/wrapper/maven-wrapper.properties`:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=OFFICIAL_SHA256_FOR_EXACT_MAVEN_3_9_9_BIN_ZIP
wrapperVersion=3.3.2
~~~

The checksum line must be replaced with the official SHA-256 of the exact Maven distribution. Supported property names depend on the Maven Wrapper version and type; some wrapper JAR setups also support `wrapperUrl`/`wrapperSha256Sum`. Inspect the generated files and the documentation for your exact version before adding properties; do not invent unsupported keys and assume checksums are being checked.

- `distributionUrl` pins the Maven version and distribution type.
- `distributionSha256Sum` verifies the downloaded Maven archive when supported by the wrapper version.
- `wrapperVersion` records the wrapper implementation version; it does not replace integrity verification of the wrapper bootstrap code.

### 4.3. Running Maven via the Wrapper

~~~bash
./mvnw --version
./mvnw -B -ntp -C clean verify
~~~

Flag meanings:

- `-B`: batch mode, suitable for non-interactive CI.
- `-ntp`: suppresses transfer progress for shorter, cleaner logs.
- `-C`: strict checksum mode when Maven downloads artifacts; checksum failures are handled strictly according to Maven Resolver behavior.

On Windows:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp -C clean verify
~~~

`-C` is only one checksum verification layer when resolving artifacts from a repository; it does not sign release JARs, does not replace repository identity verification, and does not guarantee a compromised repository cannot serve both a modified artifact and a matching checksum.

### 4.4. Wrapper Types and Wrapper Bootstrap

Maven Wrapper can use `only-script` or a bootstrap JAR depending on configuration. Do not delete `maven-wrapper.jar` if your scripts rely on it; conversely, do not commit an unused JAR if the project uses a wrapper type that does not need one. The wrapper plugin generates different layouts across modes.

In production, verify wrapper bootstrap files through organization-approved mechanisms, keep HTTPS, verify distribution checksums, and review every wrapper change. Never execute a wrapper script from an untrusted pull request with credentials that hold release publishing privileges.

## 5. Wrappers Do Not Pin the JDK: Pinning the Java Toolchain

Gradle Wrapper pins Gradle, and Maven Wrapper pins Maven. Neither **automatically pins the Java runtime or compiler**. A runner might run Gradle 8.8 on JDK 21 while the project requires Java 17 compilation.

### 5.1. Gradle Java Toolchain and Release Target

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

The toolchain requests JDK 17 from the chosen vendor for Java tasks; `options.release=17` constrains source, API, and bytecode to Java 17. Specifying `vendor` is optional per project; if the organization standardizes on Temurin/Adoptium, declaring it explicitly prevents silently picking up another vendor's JDK.

Toolchains can be auto-detected or auto-provisioned by Gradle depending on the project's resolver/configuration. For reproducible CI builds, the runner should pre-install the exact JDK or configure provisioning from a trusted repository; do not assume Gradle will auto-download a JDK in every environment.

### 5.2. Gradle Daemon JVM vs. Compiler Toolchain

`./gradlew --version` shows the JVM running Gradle. `java.toolchain` selects the JDK for configured compile/test tasks. You can run Gradle on JDK 21 while compiling with JDK 17 if your Gradle version and plugins support that setup.

However, to simplify and reduce CI variance, the practical examples use JDK 17 for both the runner and the Java toolchain. If you intentionally split the two versions, document it clearly and test compatibility.

### 5.3. Maven Compiler Release

In a Spring Boot 3.3.13 POM:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

`maven.compiler.release` configures the Maven Compiler Plugin to emit Java 17 bytecode and target Java 17 APIs when supported by the plugin version. It **does not install JDK 17**. If the Maven process runs on JDK 11, the compiler cannot use `--release 17`; you must provision a suitable build JDK or configure the Maven Toolchains Plugin to select JDK 17.

### 5.4. Verifying the JDK in CI

~~~bash
java -version
javac -version
./gradlew --version
./gradlew javaToolchains
~~~

With Maven:

~~~bash
java -version
javac -version
./mvnw --version
~~~

Record the vendor, full patch version, architecture, and JDK path in the CI log. `java -version` only confirms the executable on `PATH`; if a Gradle toolchain selects another JDK, you must inspect the toolchain output and task configuration as well.

## 6. Pinning Dependencies and Plugins

An exact Wrapper can still yield different outcomes if dependency versions drift, a repository serves different artifacts, or plugin versions are declared dynamically.

### 6.1. Gradle Dependency Locking

Gradle dependency locking fixes resolved versions. You can enable it for all configurations:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Or in Kotlin DSL:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Then resolve the required configurations and write the lock state:

~~~bash
./gradlew dependencies --write-locks
~~~

Inspect the generated lockfiles (usually under `gradle/dependency-locks` or the configured Gradle location) and commit them. When dependency versions change intentionally, update the lockfiles and review the diff.

Not all dynamic plugins or metadata are automatically locked by a single lockfile. Inspect resolution strategies, included builds, plugin management, and dependency substitutions if your project uses them.

### 6.2. Gradle Dependency Verification

Gradle supports checksum and signature verification for dependencies/plugins via:

~~~text
gradle/verification-metadata.xml
~~~

Generate an initial baseline:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

If you also want to capture PGP signature metadata (when repositories provide suitable signatures):

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

**Review the generated file before committing.** A baseline auto-generated from the currently resolving repository does not prove that repository was trustworthy initially; cross-check checksums/keys of critical dependencies from independent sources. Verification metadata protects inputs resolved by Gradle; it does not sign the output JAR produced by your project.

### 6.3. Pinning Plugin Versions

Gradle plugins should have explicit versions in the `plugins` block or in plugin management:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}
~~~

Never use dynamic plugin versions or logic that fetches `latest` from the Internet in release builds. With version catalogs, commit `gradle/libs.versions.toml` and review updates.

### 6.4. Maven Dependencies and Plugins

Maven should pin the Spring Boot parent/BOM version, as well as plugin versions managed by the parent or declared in `pluginManagement`. Avoid dependency version ranges, `LATEST`, `RELEASE`, and `SNAPSHOT` in release builds unless governed by a dedicated policy.

The Maven Enforcer Plugin can enforce Maven/JDK requirements, dependency convergence, or ban snapshots. When using it, pin the plugin version in the POM/parent and review its rules; avoid vague rules that behave differently between CI and developer machines.

Maven's strict checksum mode `-C` helps detect repository checksum mismatches, but **does not replace** an SBOM, a locking/verification policy, or trust in your repository manager.

## 7. Pinning the CI Runner and Execution Environment

To make builds repeatable, specify at least:

| Input | What to Pin/Record | Why It Matters |
| --- | --- | --- |
| OS image | Distro/release or container digest | Toolchain, libc, certificates, and filesystem |
| CPU architecture | amd64/arm64 | Native dependencies and compiler behavior |
| JDK | Vendor, major, and patch | Compiler/JVM APIs, bugs, and security patches |
| Gradle/Maven | Wrapper distribution + checksum | Build engine version |
| Plugins | Exact plugin versions | Task graph, compiler/package behavior |
| Dependencies | Locking, verification, BOM | Prevents version drift |
| Repository | Approved mirrors, TLS/trust config | Source of dependencies |
| Environment | Locale, timezone, encoding, variables | Timestamps, formatting, conditional logic |
| Build parameters | Tasks, profiles, flags, properties | Same source with different commands can yield different outputs |
| CI actions/plugins | Version or immutable commit SHA | Prevents action code from changing outside a PR |
| Secrets | Runtime injection from secret manager | Keeps credentials out of source, logs, and artifacts |
| Cache | Key, trust boundary, lifecycle | Speeds up builds without altering correctness |

### 7.1. JDK Major vs. Patch

Configuring `java-version: '17'` in a CI setup action typically selects the latest matching Java 17 build available at runtime. This keeps security patch updates automatic, but **is not strict patch pinning**.

If strict byte-level build reproducibility is required, pin the vendor, full JDK patch/build, and runner/container digest. At the same time, maintain a schedule for security patches; strict pinning must never become an excuse to retain a JDK with known vulnerabilities.

### 7.2. Runner Labels Can Be Mutable

For example, `ubuntu-24.04` pins the OS release family better than `ubuntu-latest`, yet hosted runner images still receive updates over time. If strict repeatability is needed, run inside an approved build container image referenced by digest on a suitable runner, or use a managed self-hosted runner recording OS, architecture, and toolchain metadata.

Do not use fabricated digests. Pull real digests from an organization-approved registry and update them via reviewed PRs.

### 7.3. Locale, Timezone, and Encoding

Some build scripts or code generators may depend on locale, timezone, or default charset. CI should set required values explicitly, for example:

~~~bash
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
~~~

This is an example for Linux runners; these variables do not share identical semantics across all OSes. Java 17 defaults to UTF-8 in many modern environments, but you should not rely on OS defaults for other tools. If outputs include timestamps, use UTC/`Instant` and define the timestamp source; avoid arbitrary `now` values in artifacts when targeting reproducible builds.

### 7.4. Recording the Build Environment

You can log the following non-secret details in CI:

~~~bash
uname -a
uname -m
java -version
javac -version
./gradlew --version
./gradlew javaToolchains
~~~

A Maven job replaces the last two commands with:

~~~bash
./mvnw --version
~~~

Never dump the full environment with `env` or `printenv` in public CI logs; that can expose tokens, passwords, and secrets. Print only an allowlist of non-sensitive diagnostic variables.

## 8. GitHub Actions Example: Gradle Wrapper + Java 17

Illustrative workflow at `.github/workflows/gradle-ci.yml`:

~~~yaml
name: Gradle CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Validate Gradle Wrapper
        uses: gradle/actions/wrapper-validation@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Show build environment
        run: |
          java -version
          javac -version
          ./gradlew --version
          ./gradlew javaToolchains

      - name: Build and test with Wrapper
        run: ./gradlew --no-daemon clean check bootJar
~~~

This is an easy-to-read illustrative workflow. In a production pipeline:

- Pin GitHub Actions by reviewed full commit SHA (optionally with a version comment), not just a tag like `@v4`.
- Choose runner images/containers per policy; `ubuntu-24.04` hosted runners are still updated over time.
- If an exact JDK patch is required, specify the full version/build and verify the post-setup output.
- Add caching keyed by Wrapper, JDK, OS, and dependency metadata; caches only optimize speed.
- If a job holds publish/sign permissions, isolate them from pull requests from forks; only the release workflow should receive OIDC/signing permissions.
- Keep `permissions` minimal; never grant `contents: write` to standard build/test jobs.

### 8.1. Caching Gradle in CI

You can use the setup action's Gradle cache or a dedicated cache action. The key should depend at least on OS, JDK, and files governing Gradle/dependency resolution such as:

~~~text
gradle-wrapper.properties
settings.gradle(.kts)
build.gradle(.kts)
gradle/libs.versions.toml
gradle/verification-metadata.xml
gradle/dependency-locks/**
~~~

Do not use a single shared cache across branches/trust boundaries for untrusted builds and privileged release builds. Never cache credentials or secret files. If the cache is deleted, the build must still succeed by downloading dependencies from valid sources.

### 8.2. Why Use `--no-daemon`?

In CI, `--no-daemon` reduces reliance on long-lived Gradle daemon processes across jobs. Gradle may still spawn a single-use daemon to satisfy JVM arguments; this flag does not mean every execution is a single plain process. It helps with job isolation, though it does not replace Wrapper/JDK pinning.

## 9. GitHub Actions Example: Maven Wrapper + Java 17

Illustrative workflow at `.github/workflows/maven-ci.yml`:

~~~yaml
name: Maven CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Show build environment
        run: |
          java -version
          javac -version
          ./mvnw --version

      - name: Build and verify with Maven Wrapper
        run: ./mvnw -B -ntp -C clean verify
~~~

As with Gradle, pin actions by full commit SHA and verify the runner image. `cache: maven` only caches repository artifacts to speed up builds; Maven must still enforce checksum/repository policies and builds must succeed on a cache miss.

The Maven Wrapper distribution checksum is checked via `maven-wrapper.properties` when the wrapper version supports that property. CI does not need a global Maven installation. Calling `mvn` instead of `./mvnw` bypasses the repository's pinned Maven version.

### 9.1. Does CI Need to Run on Windows?

If the project supports Windows, you can add a dedicated job:

~~~yaml
jobs:
  windows-verify:
    runs-on: windows-2022
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Verify with Maven Wrapper
        shell: pwsh
        run: .\mvnw.cmd -B -ntp -C clean verify
~~~

Runner names and action versions are examples; pin immutable action SHAs and match your runner policy. Do not merely swap script paths while skipping tests for path separators, file permissions, case sensitivity, and native libraries if the project claims Windows support.

## 10. Using Container Build Environments to Reduce Runner Drift

Another approach is running builds inside a controlled CI container image. Example workflow structure (the image reference must be replaced with an actual organization-approved digest):

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-24.04
    container:
      image: registry.example.org/ci/java17-gradle@sha256:APPROVED_IMAGE_DIGEST

    steps:
      - uses: actions/checkout@v4
      - name: Verify
        run: ./gradlew --no-daemon clean check bootJar
~~~

`registry.example.org` and `APPROVED_IMAGE_DIGEST` only illustrate the configuration shape; they are not usable image references. The CI image should contain a managed JDK vendor/patch, OS libraries, certificates, and tools. The Wrapper is still used to select the exact Gradle/Maven distribution.

Pinning a container digest stabilizes the image layers, yet is insufficient if the build still accesses dynamic dependencies, Maven snapshots, Gradle dynamic versions, remote scripts, or external services. Pin and control all relevant inputs.

### 10.1. No Need to Embed Global Gradle/Maven in the Image

You can build a CI image containing the JDK and utilities while projects still execute `./gradlew`/`./mvnw`. This keeps the build tool version dictated by the repository. Installing global Gradle/Maven inside the image just to run builds makes it easy for CI to accidentally invoke the global version.

### 10.2. Multi-Architecture

If runners move from amd64 to arm64, native dependencies, JDK builds, test outcomes, or OCI image architectures can differ. Record the architecture, run tests on every supported platform, and never share native build output caches across incompatible architectures.

## 11. Pinning Dependencies and Build Plugins in Releases

### 11.1. Gradle Version Catalogs

Use `gradle/libs.versions.toml` to centralize plugin and dependency versions:

~~~toml
[versions]
spring-boot = "3.3.13"
dependency-management = "1.1.7"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
dependency-management = { id = "io.spring.dependency-management", version.ref = "dependency-management" }
~~~

Build scripts reference the declared aliases. A version catalog centralizes reviews and updates, though it does not automatically lock every transitive version if dependency constraints/BOMs do not govern them. Combine it with dependency locking and verification.

### 11.2. Maven BOM and Plugin Management

The Spring Boot parent/BOM manages compatible dependency versions. The parent version must be explicitly pinned; plugin versions not managed by the parent should be pinned in `pluginManagement` or `build/plugins`.

Never use version ranges or `LATEST` in release builds. Avoid `SNAPSHOT` dependencies in production releases unless your organization operates a dedicated immutable snapshot repository process.

### 11.3. Repository Mirrors

CI should resolve artifacts from an approved repository manager or mirror with explicit TLS/trust configuration. Never download dependencies or plugins via ad-hoc scripts from unreviewed URLs. If credentials are required, supply them through a secret manager and only to jobs that need them; never put credentials in a `settings.xml` committed to the repository.

### 11.4. Maven Enforcer and Java/Maven Requirements

The Maven Enforcer Plugin can validate Maven version/JDK ranges, dependency convergence, and ban snapshots. Plugin rule versions must be pinned in a reviewed POM/parent. Do not specify an overly broad Java range and assume builds will always produce identical outputs; if targeting Java 17, define both the compiler release and runtime JDK explicitly.

## 12. Cache: Speed Optimization, Not a Trusted Input

CI commonly caches:

- Gradle Wrapper distributions and dependency caches.
- Gradle build cache/task outputs if enabled.
- Maven local repository `~/.m2/repository`.
- Build outputs in certain conditional pipelines.

Caches can be evicted, corrupted, stale, or populated by another branch/job. Builds must be **correct when the cache is empty**, and a cache must never be treated as the sole source of truth.

### 12.1. Cache Key

The key should depend on:

- OS/architecture.
- JDK vendor/version.
- Wrapper properties and Gradle/Maven version.
- Dependency lockfiles/verification metadata.
- Build scripts/plugin versions.
- Build parameters that affect outputs.

If the cache key omits these factors, jobs may restore incompatible caches or mask input changes.

### 12.2. Caches Do Not Replace Checksums/Verification

Gradle dependency verification, Maven strict checksum mode, and repository trust policies must remain active even when dependencies are cached. A local cache does not prove an artifact came from the legitimate publisher.

### 12.3. Caches and Untrusted Pull Requests

Never allow an untrusted pull request to write to a cache consumed by release jobs that hold signing or publishing permissions if that cache could influence build outputs. Separate cache keys, branch scopes, and permissions. Never cache secret material or private signing keys.

### 12.4. Do Not Mechanically Run Clean Expecting Caches to Disappear

`./gradlew clean` clears workspace build outputs; it does not delete Wrapper distributions or dependency caches. `mvn clean` deletes `target/` outputs; it does not clear the Maven local repository. When investigating cache issues, identify the right layer: wrapper distribution, dependency cache, task/build cache, or workspace outputs.

## 13. A Java 17 Probe to Record the CI Environment

Create `BuildEnvironmentProbe.java` to print non-secret diagnostic properties:

~~~java
public final class BuildEnvironmentProbe {

    public static void main(String[] args) {
        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println("java.vm.name=" +
                System.getProperty("java.vm.name"));
        System.out.println("os.name=" +
                System.getProperty("os.name"));
        System.out.println("os.arch=" +
                System.getProperty("os.arch"));
        System.out.println("file.encoding=" +
                System.getProperty("file.encoding"));
        System.out.println("user.timezone=" +
                System.getProperty("user.timezone"));
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 BuildEnvironmentProbe.java
java BuildEnvironmentProbe
~~~

Output varies by JDK vendor/patch, OS, architecture, and runtime properties. There is no single fixed stdout across all CI runners. This is a **standalone Java SE program** that does not require Spring Boot. It only records JVM/runtime properties of the process running the probe; it cannot inspect CI action versions, container digests, or source commits on its own.

You can append allowlisted CI variables such as commit SHA, build run ID, and image digest, but never print the entire environment since that could leak secrets.

## 14. Inspecting the Wrapper and Build Tool When CI Fails

### 14.1. Gradle Diagnostics

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew tasks --all
./gradlew --no-daemon clean check bootJar --info
~~~

Check:

- Does the Gradle version match the Wrapper properties?
- Does the JVM running Gradle satisfy Gradle and plugin requirements?
- Is the Java 17 toolchain detected/provisioned?
- Does the task graph target the right module/application?
- Does dependency resolution use the expected repository/mirror?
- Did a cache hit/miss cause behavioral drift or only change timing?

### 14.2. Maven Diagnostics

~~~bash
./mvnw --version
./mvnw -B -ntp -C help:effective-pom
./mvnw -B -ntp -C clean verify
~~~

The effective POM shows parent/plugin management and compiler settings after inheritance. If the toolchains plugin is used, inspect the CI toolchains file and corresponding JDK paths; never commit developer machine absolute paths to the repository.

### 14.3. Inspecting Class Output When Needed

Gradle:

~~~bash
javap -verbose -classpath build/classes/java/main com.example.Application
~~~

Maven:

~~~bash
javap -verbose -classpath target/classes com.example.Application
~~~

Replace `com.example.Application` with your actual fully qualified class name. When targeting Java 17, the main class normally shows `major version: 61`. Inspecting class output helps distinguish a compiler mismatch from a Wrapper or runtime issue.

### 14.4. Logging Without Exposing Secrets

It is safe to print `java -version`, Wrapper version, OS, architecture, commit SHA, and selected tasks. Never print `env`, Maven settings containing credentials, Gradle properties with tokens, or full build scan links that could expose private data if disallowed by policy.

## 15. Common Errors and How to Handle Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `gradlew: command not found` | Wrapper script not committed or invoked from the wrong directory | Check root path and `gradlew`; use `./gradlew` |
| Windows fails to run `./gradlew` | Wrong script used | Use `.\gradlew.bat` |
| Wrapper fails to download Gradle | Wrong distribution URL, TLS/proxy issue, or checksum mismatch | Verify official URL/checksum and network |
| Maven Wrapper fails to run | Missing script, properties, or bootstrap files | Check wrapper type and commit all required files |
| Maven Wrapper downloads archive but checksum fails | Wrong SHA or modified file | Stop build, verify distribution via a trusted source |
| Gradle/Maven version differs from local | CI invoked global command instead of Wrapper | Switch to `./gradlew`/`./mvnw` |
| Java version differs from expected | Runner JDK or toolchain differs | Inspect `java -version`, `--version`, and toolchains |
| Java 17 source produces class major 65 | Compiler target not locked | Set `options.release=17`/`maven.compiler.release=17` |
| Plugin resolution differs | Dynamic plugin versions or differing repositories | Pin plugin versions and repository policy |
| Dependency version drifts | Dynamic/range/SNAPSHOT or missing lockfile | Use dependency locking/BOM/ban snapshots |
| Gradle verification fails | Dependency checksum/signature changed | Investigate repository/source, review metadata before updating |
| Maven strict checksum fails | Artifact/checksum mismatch | Stop release and check repository/mirror |
| Build fails only on empty cache | Unintended cache reliance or missing offline input | Ensure dependency resolution repeats cleanly from repositories |
| CI cache restore causes strange errors | Cache key lacks OS/JDK/wrapper/lockfile | Adjust key and separate trust boundaries |
| Local passes, CI fails on Linux | File permissions, case sensitivity, or line endings | Check wrapper executable bit, path casing, and checkout |
| Local passes, CI fails on ARM | Different native dependencies or architecture | Test on the right architecture; do not share native caches across architectures |
| Build outputs differ by timezone | Task/script depends on clock or locale | Standardize UTC/locale; inspect generated timestamps |
| Action code changes outside PR | Mutable action tag used | Pin full commit SHA and update via review |
| CI release exposes secrets in logs | Printed full `env` or verbose commands | Use allowlisted diagnostics and redact secrets |
| Maven runs JDK 11 despite Java 17 setup | `JAVA_HOME`/PATH/toolchain config not updated | Check setup order and `mvnw --version` |
| Wrapper validation fails | Untrusted Wrapper JAR or wrong generated version | Regenerate from trusted distribution and review binary diff |

### 15.1. Investigation Order

1. Confirm the job runs at the repository root and invokes the right Wrapper script.
2. Print the Wrapper version and the JVM executing the build tool.
3. Check the JDK toolchain and compiler release.
4. Check the wrapper distribution URL/checksum and wrapper bootstrap files.
5. Check plugin/dependency locks and verification metadata.
6. Temporarily run without cache to determine if the cache is involved; do not wipe all caches before identifying the failing layer.
7. Check OS, architecture, locale, timezone, and environment parameters.
8. Compare build logs and outputs against local runs using identical inputs.
9. Only publish or sign artifacts after builds reproduce reliably.

## 16. Practice Exercises with Answers

### Exercise 1 — Global Gradle or Wrapper?

CI is running `gradle clean build` and the runner's Gradle was just upgraded. What is the minimal fix?

**Answer:** Call `./gradlew clean build` (`gradlew.bat` on Windows) and commit the complete Gradle wrapper files with the distribution URL, version, and checksum.

### Exercise 2 — Wrapper Pins Gradle, But Java Is Wrong

`./gradlew --version` shows Gradle 8.8 on JVM 21, while the project must compile for Java 17. Where do you fix this?

**Answer:** Pin the runner/toolchain JDK to Java 17; in Gradle, set `java.toolchain.languageVersion=17` and `options.release=17`. The Wrapper does not choose the compiler JDK by itself.

### Exercise 3 — Gradle Distribution Checksum

A runner downloads the Gradle distribution from an HTTPS URL, but the checksum does not match. Should you remove `distributionSha256Sum` to let the build continue?

**Answer:** No. Stop the job, verify the URL, archive, and checksum from a trusted Gradle source, inspect any mirror/proxy, and update the checksum only after review.

### Exercise 4 — Maven Strict Checksum

CI runs `./mvnw -B -ntp -C verify` and Maven reports a dependency checksum mismatch.

**Answer:** Do not switch to `-c` or disable strict mode to release. Inspect the artifact and checksum in the repository manager and upstream source, and investigate caches/proxies before proceeding.

### Exercise 5 — Wrapper Update

A PR upgrades Gradle from 8.8 to a newer version. What needs to be reviewed?

**Answer:** Distribution URL and checksum, wrapper scripts and JAR, Gradle/JDK/plugin compatibility, dependency resolution, and a full clean build and test run on the target runner.

### Exercise 6 — Cache

The build passes when a cache is present and fails when the cache is empty because dependencies fail to resolve.

**Answer:** The pipeline depends on the cache instead of a valid repository. Check repository, proxy, and offline flags, and ensure the build resolves dependencies cleanly on a cache miss.

### Exercise 7 — JDK Patch

The workflow uses `java-version: '17'`. Can you guarantee the exact same JDK patch across every month?

**Answer:** No. It usually picks a matching Java 17 build at runtime. If strict patch pinning is needed, declare the full version/build and pin the runner/container; still apply security patches on a controlled schedule.

### Exercise 8 — Action Tag

The workflow uses `actions/checkout@v4`. Is the action code strictly immutable?

**Answer:** A tag is not a strictly immutable reference. Under strict supply-chain policies, pin a reviewed full commit SHA and update it via PRs.

### Exercise 9 — Toolchain Differs from Gradle Daemon

The Gradle daemon runs JDK 21 while `javaToolchains` shows a JDK 17 compiler. Can the class target still be Java 17?

**Answer:** Yes, if compile tasks use toolchain 17 and release target 17. Verify the class major version with `javap`.

### Exercise 10 — Reproducibility

Two CI jobs use the same Wrapper yet produce different artifact checksums. Can you conclude the Wrapper is broken?

**Answer:** Not yet. Compare JDK patch/vendor, OS/architecture, dependencies, plugins, timestamps, locale, generated files, environment parameters, and build tasks. The Wrapper only pins the Gradle/Maven distribution.

## 17. Pre-Merge CI Workflow Checklist

- [ ] Gradle/Maven Wrapper scripts and required bootstrap files are committed.
- [ ] Wrapper distribution URL uses HTTPS and a fixed version.
- [ ] Gradle `distributionSha256Sum` or Maven checksum fields are populated from an official source if supported by the wrapper version.
- [ ] Wrapper JAR/bootstrap code has been validated and reviewed.
- [ ] CI invokes `./gradlew` or `./mvnw`, never an unintended global Gradle/Maven.
- [ ] JDK vendor/major/patch and architecture are clearly defined; Java toolchain/compiler release matches the contract.
- [ ] Plugin versions, dependency versions/BOMs, and repository policies are pinned.
- [ ] Gradle dependency locks/verification metadata are reviewed, or Maven strict checksum/repository policies are enforced.
- [ ] Runner OS, container, and action versions follow pinning and update policies.
- [ ] Locale, timezone, encoding, and build parameters are standardized where they affect outputs.
- [ ] Cache keys include critical inputs; builds remain valid on an empty cache.
- [ ] Secrets, private keys, or artifacts from untrusted PRs are never written to release caches.
- [ ] CI logs print only necessary environment details and never dump secrets.
- [ ] The build runs clean tests and produces the exact Spring Boot executable JAR.
- [ ] CI records toolchain versions, source commit, and build invocation for diagnostics.
- [ ] Wrapper/JDK/plugin upgrades undergo PR review, compatibility testing, and a regular security update cadence.

**Conclusion:** The Wrapper ensures the project itself specifies the exact Gradle/Maven distribution; the Java toolchain and compiler release ensure builds use the right JDK and bytecode target; and the CI runner/container, plugins, dependencies, and environment must be controlled separately. Use the Wrapper in every job, verify distribution checksums, pin JDK and build inputs, maintain dependency verification, and treat caches strictly as performance optimizations. That way, every commit is built and tested on CI with transparent inputs that can be audited and reproduced when needed.

## 18. Official Documentation

- Gradle — The Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle — Gradle Wrapper Validation: https://docs.gradle.org/current/userguide/gradle_wrapper.html#sec:verification
- Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Apache Maven — Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Maven Wrapper Plugin: https://maven.apache.org/wrapper/maven-wrapper-plugin/
- Apache Maven — Maven Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains.html
- Apache Maven — Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- GitHub Actions — Secure use reference: https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
- GitHub Actions — Dependency caching: https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows

Wrapper options and action syntax can change across versions. When upgrading the Gradle/Maven Wrapper, plugins, or CI actions, read the documentation for the exact pinned version, verify official checksums, and run a clean build on the target runner before releasing.