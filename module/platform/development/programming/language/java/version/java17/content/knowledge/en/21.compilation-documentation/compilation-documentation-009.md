# Reproducible Builds with Pinned JDK and Tools in Java 17

A reliable build must produce consistent outputs when re-run from the same source code and inputs. If a developer's machine uses one JDK, CI uses another, Gradle or Maven downloads a newer version automatically, dependencies use dynamic versions, or archives embed timestamps that change on each run, two builds can yield different outputs even when the code has not changed.

A **reproducible build** is a build process capable of recreating artifacts from identically defined inputs. The strongest goal is for two independent builds to produce byte-for-byte identical artifacts. Moving toward that goal requires pinning the JDK, build tools, plugins, dependencies, environment configuration, and artifact packaging steps.

For a Java 17 project, distinguish three version layers:

1. **Build runner JDK:** the JVM used to execute Gradle/Maven and build plugins.
2. **Compile/test toolchain JDK:** the JDK used by compiler and test tasks.
3. **Target Java release:** the language, bytecode, and API version the application may use, typically configured as `--release 17`.

These three layers are related yet are not necessarily the same setting. Setting `--release 17` does not pin the JDK running the build; declaring a Java 17 toolchain does not pin the Gradle or Maven version.

This lesson explains how to establish stable builds with Gradle or Maven, manage dependencies, normalize environments, create deterministic archives, and verify results on Java 17.

## 1. Distinguishing repeatable, reproducible, and hermetic builds

These terms are often used near one another:

| Concept | Practical meaning |
| --- | --- |
| Repeatable build | The build process can be re-run with the same configuration to obtain equivalent outputs. |
| Reproducible build | Independent builds from controlled identical inputs produce byte-for-byte identical artifacts, typically verified via checksums. |
| Hermetic build | The build depends solely on declared/controlled inputs without accidentally relying on undeclared machine state, network access, files, or external tools. |

A build may repeat successfully yet still fail byte-for-byte reproducibility. For example, JAR files with identical classes and resources can have different ZIP entry timestamps, resulting in different checksums.

A build may also appear reproducible on a developer's machine without being hermetic: the machine might rely on a cached dependency or an unrecorded environment variable. On a clean CI runner, the output may differ or fail to build.

The practical path is to tighten each layer step by step:

- Identical source revision and configuration.
- Identical JDK, build tool, plugins, and dependencies.
- Consistent required environment settings.
- No timestamps, file ordering variance, or random data altering artifacts.
- Ability to build in a clean workspace and compare checksums.

## 2. Pinning the JDK version

The JDK is one of the most critical inputs. Differences between JDK versions can affect the compiler, APIs, bytecode, annotation processors, runtime behavior, and bundled tools.

For projects targeting Java 17, specify clearly:

- Major version: Java 17.
- JDK vendor, if standardized by the organization.
- Exact JDK update (patch/build) for release environments.
- OS/CPU architecture, if artifacts or tools are platform-dependent.

Do not simply write "requires Java 17" in a README and let every machine pick any JDK 17. Different patch updates within the same major version are generally compatible, yet bit-for-bit reproducibility requires pinning the exact distribution and build.

### 2.1. Checking which JDK is in use

Run:

```bash
java -version
javac -version
```

Check environment variables:

```bash
# Linux/macOS
echo "$JAVA_HOME"

# PowerShell
$env:JAVA_HOME
```

`java -version` shows the runtime resolved via PATH; `javac -version` shows the compiler. In CI, inspect both and verify the build tool actually uses the intended JDK.

### 2.2. Pinning the JDK in CI

CI should install or select an agreed JDK 17 vendor and version. Example workflow using a digest-pinned container image:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    container:
      image: eclipse-temurin:17-jdk@sha256:<approved-image-digest>
    steps:
      - uses: actions/checkout@v4
      - name: Verify JDK
        run: |
          java -version
          javac -version
      - name: Build
        run: ./gradlew --no-daemon clean build
```

The image name and digest here are placeholders for your organization's approved image. A tag such as `17-jdk` pins only the major line and may resolve to a newer image later. A digest pins exact image contents. If runners install JDKs via a setup action, pin an exact version instead of dynamic labels like `latest`.

Never commit an absolute `JAVA_HOME` path from a personal machine into the repository. That path differs across Windows, Linux, macOS, and CI.

## 3. Distinguishing build runner JDK, toolchain, and release target

A Gradle build may launch on the JDK used by the Gradle daemon, while compile and test tasks execute on a configured Java toolchain JDK.

For example:

- Gradle daemon runs on JDK 17.
- Java compilation uses a JDK 17 toolchain.
- `--release 17` restricts target APIs and bytecode to Java 17.

These three layers differ:

| Component | What does it control? | Example |
| --- | --- | --- |
| Build runner JDK | JVM executing Gradle/Maven and plugins. | Pinned JDK 17 in the CI image. |
| Java toolchain | JDK used by toolchain-aware compile/test tasks. | Toolchain language version 17. |
| Release target | Language, bytecode, and APIs permitted. | `--release 17`. |

Setting `--release 17` is essential. Setting only `sourceCompatibility = 17` and `targetCompatibility = 17` still lets the compiler see newer JDK APIs if the build runs on a newer JDK. `--release` simultaneously constrains language level, target class file format, and the public API surface of the selected release.

### 3.1. Checking with javac

You can compile a single file using:

```bash
javac --release 17 -encoding UTF-8 -d out src/main/java/com/example/Main.java
```

This does not replace a build tool, yet it clearly illustrates the compiler target.

## 4. Pinning Gradle with the Gradle Wrapper

The Gradle Wrapper ensures all developers and CI use the exact Gradle version specified by the project. The repository should contain the wrapper files generated by Gradle:

```text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

`gradle/wrapper/gradle-wrapper.properties` specifies the distribution version:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=<verified-distribution-sha256>
```

The version above is an illustrative example of pinning a concrete version; choose a Gradle version supported by your project and verify its official checksum before committing. Never substitute `gradle-8.x` or a mutable distribution URL.

The checksum protects the Gradle distribution download against tampering or mismatch. Never guess a checksum; obtain it from the official distribution source or a trusted release process.

Run builds through the wrapper:

```bash
./gradlew --version
./gradlew clean build
```

On Windows:

```powershell
.\\gradlew.bat --version
.\\gradlew.bat clean build
```

Never tell developers to install Gradle globally and invoke `gradle build`. That can run a different version from the one pinned in the repository.

### 4.1. Pinning the Java toolchain in Gradle

In `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
```

In `build.gradle.kts` (Kotlin DSL):

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
```

Toolchains allow Gradle to select an appropriate JDK for Java tasks like compiling and testing. If you also need to constrain the vendor, specify:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}
```

A vendor constraint restricts the distribution vendor, though it does not pin an exact patch/build number. For exact reproducibility, standardize the JDK distribution/build in CI or managed build environments.

### 4.2. Toolchain does not equal the Gradle daemon JVM

Java toolchains control the JDK used by toolchain-aware tasks. The Gradle daemon runs on its own JVM, typically selected from `JAVA_HOME` or environment/Gradle configuration.

Therefore, specify all three:

- The JDK running Gradle.
- The toolchain JDK for compiling/testing.
- The target Java release.

Never commit `org.gradle.java.home` with an absolute path from a developer's machine. If an organization must pin the daemon JDK, configure it in CI/containers or via provisioning supported by your Gradle version.

## 5. Pinning Maven with the Maven Wrapper

The Maven Wrapper serves the same purpose as the Gradle Wrapper: the repository defines which Maven version the build uses.

Typical files:

```text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.jar
.mvn/wrapper/maven-wrapper.properties
```

Example `.mvn/wrapper/maven-wrapper.properties`:

```properties
distributionUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=<verified-distribution-sha256>
```

The Maven version shown is an illustrative pinned version. Choose a version supported by your project, verify its official checksum, and commit the wrapper files and configuration. Avoid unpinned download URLs or relying on globally installed Maven.

Run:

```bash
./mvnw --version
./mvnw clean verify
```

On Windows:

```powershell
.\\mvnw.cmd --version
.\\mvnw.cmd clean verify
```

### 5.1. Pinning compiler release in Maven

In `pom.xml`, declare encoding and release explicitly:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Pin plugin versions explicitly, such as `3.13.0` above. When upgrading, update the version deliberately and review the diff. Do not let Maven pick plugin versions from environment defaults or implicit super POM settings when pursuing reproducible builds.

You can use the Maven Toolchains Plugin and a `toolchains.xml` file to select a specific JDK for compiler/test plugins. Because toolchain files contain machine-specific JDK installation paths, manage them per environment rather than committing personal paths into the source repository.

## 6. Pinning plugins and build logic

Application dependencies are not the only inputs. Build plugins also download libraries, execute code, and shape output artifacts.

### With Gradle

Pin plugin versions in the `plugins` block:

```kotlin
plugins {
    java
    id("com.example.build-conventions") version "1.4.2"
}
```

If using internal plugins, ensure their versions and dependencies are explicitly managed too. Avoid dynamic versions or snapshot plugins for release builds.

You can centralize dependency versions in a Version Catalog:

```toml
[versions]
jackson = "2.17.2"
junit = "5.11.0"

[libraries]
jackson-databind = {
    module = "com.fasterxml.jackson.core:jackson-databind",
    version.ref = "jackson"
}
junit-jupiter = {
    module = "org.junit.jupiter:junit-jupiter",
    version.ref = "junit"
}
```

The versions above illustrate concrete version pins, not blanket recommendations for every project. Choose versions vetted for compatibility and security.

### With Maven

Pin every build plugin's version in `pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
```

Explicit plugin versions prevent builds from shifting with Maven super POM or environment defaults. Treat plugins used by the project with the same version-pinning rigor as runtime dependencies.

## 7. Pinning dependencies and the dependency graph

Declarations such as `1.2.+`, `latest.release`, version ranges, or `SNAPSHOT` can resolve to different versions across builds. That changes the dependency graph even when source code has not changed.

Best practices:

- Declare exact versions for direct dependencies.
- Centralize versions using a Version Catalog or Maven dependency management.
- Avoid dynamic versions, ranges, and snapshots in release builds.
- Control which repositories may supply dependencies.
- Monitor transitive dependencies.
- Persist dependency resolution state using your build tool's mechanisms.

### 7.1. Gradle dependency locking

Gradle supports dependency locking to record resolved versions across locked configurations.

Example in `build.gradle.kts`:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Generate or update lock state during dependency resolution:

```bash
./gradlew --write-locks build
```

Commit the generated lockfiles into the repository. When upgrading dependencies intentionally, update the lockfiles alongside the version change and review the diff. Never hand-edit lockfiles unless you understand Gradle's format and resolution rules.

Dependency locking pins resolved versions, including transitive dependencies in managed configurations. It does not verify the bytes of downloaded artifacts; pair it with dependency verification.

### 7.2. Gradle dependency verification

Gradle can verify checksums or signatures of downloaded dependencies. Initialize checksum metadata:

```bash
./gradlew --write-verification-metadata sha256 build
```

This resolves the dependencies for the executed tasks and generates or updates `gradle/verification-metadata.xml`. Review the file and commit it. Subsequent builds verify that downloaded artifacts match the recorded checksums.

When adding a dependency or upgrading versions, update verification metadata under review. Never run metadata generation blindly to accept arbitrary new artifacts without checking their origin and checksums.

### 7.3. Maven dependency management

Maven centralizes versions via `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.11.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

A BOM (Bill of Materials) keeps ecosystem dependencies on compatible versions. The versions shown are concrete examples; select a BOM suited to your project.

Maven core does not provide a dependency lockfile workflow identical to Gradle dependency locking. To stabilize the dependency graph, pin versions, avoid ranges and SNAPSHOTs, manage BOMs, inspect the dependency tree, and govern repositories/mirrors.

Inspect the dependency graph:

```bash
./mvnw dependency:tree
```

Inspect the POM after inheritance and active profiles:

```bash
./mvnw help:effective-pom
```

These commands reveal effective versions and plugins coming from parent POMs, profiles, or the super POM rather than looking at only one `pom.xml`.

## 8. Pinning repositories and artifact sources

Even with pinned versions, repositories remain a build input. Standardize which repositories/mirrors CI and developers are allowed to access.

### Gradle

Declare repositories intentionally:

```kotlin
repositories {
    mavenCentral()
}
```

In enterprise environments, use an internal repository manager as a mirror/proxy. Restrict arbitrary repositories declared inside individual subprojects; centralize repository configuration at the appropriate level and govern plugin repositories separately.

### Maven

Configure mirrors in `settings.xml` so all repository requests route through an approved repository manager. Because `settings.xml` is typically a user/environment configuration, distribute it consistently in CI and onboarding docs.

Never allow a build to rely on an artifact present only in a local Maven repository or Gradle cache. A build in a clean workspace must fetch all inputs from declared repositories.

## 9. Making archives and artifacts deterministic

A JAR file is a ZIP archive. If entry timestamps, file ordering, or metadata vary between two builds, the overall JAR checksum will differ even when the compiled classes match.

### 9.1. Maven: outputTimestamp

Maven Archiver supports `project.build.outputTimestamp` to generate archives with deterministic timestamps.

Example:

```xml
<properties>
    <project.build.outputTimestamp>
        2024-01-01T00:00:00Z
    </project.build.outputTimestamp>
</properties>
```

The value above is an illustrative fixed timestamp. In release workflows, derive a standard timestamp from the source revision or a fixed release timestamp, ensuring all builds of the same revision use the exact same value.

Confirm that plugins generating JARs, source JARs, javadoc JARs, or other ZIPs also support and honor reproducible archive settings.

### 9.2. Gradle: archive tasks

Gradle provides properties on archive tasks to normalize timestamps and file ordering:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

`isPreserveFileTimestamps = false` strips unstable source file timestamps from the archive; `isReproducibleFileOrder = true` enforces deterministic file ordering. Modern Gradle versions default toward reproducible archives, yet declaring these properties makes intent explicit. Verify your project's Gradle version supports these properties.

### 9.3. Generated files and manifests

Archives can still diverge if the build generates files embedding:

- The current wall-clock time.
- Build machine username or hostname.
- Absolute workspace paths.
- Incrementing CI build numbers.
- Content fetched from unpinned external APIs or environments.
- Nondeterministic iteration order from maps/sets or parallel tasks.

When embedding build metadata in an artifact, use deterministic values such as the source commit ID, release version, and a managed timestamp. Never write `new Date()` or `Instant.now()` into resources if identical source revisions must yield identical artifacts.

## 10. Normalizing encoding, locale, timezone, and environment

Builds can depend on operating system defaults:

- Default character encoding for reading/writing text.
- Locale affecting number, date formatting, or sorting.
- Timezone affecting generated timestamps.
- Environment variables affecting profiles, endpoints, versions, or generated files.
- Line endings and filesystem behavior differing between Windows and Linux.
- Absolute paths and directory traversal ordering.

### 10.1. Declare encoding explicitly

With Maven:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <maven.compiler.encoding>UTF-8</maven.compiler.encoding>
</properties>
```

With Gradle:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

In application or build code, specify charsets explicitly when converting between bytes and text:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

Never rely on the machine's default charset for data entering artifacts.

### 10.2. Normalize timezone and locale

If the build generates files containing dates, times, or locale-formatted text, enforce a consistent environment in CI, such as:

```bash
export TZ=UTC
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
./gradlew clean build
```

Available locale names can vary across OS images. Verify the locale is installed in the image and avoid assuming an absent locale in build scripts.

Even better, when logic does not depend on system defaults, pass explicit `ZoneId` and `Locale` arguments to APIs instead of relying on process-wide defaults.

### 10.3. Normalize line endings and source files

Use `.gitattributes` to standardize line endings for text files:

```text
* text=auto
*.java text eol=lf
*.gradle text eol=lf
*.gradle.kts text eol=lf
*.xml text eol=lf
*.properties text eol=lf
```

Line-ending rules reduce unnecessary differences between Windows and Unix environments. For scripts requiring CRLF or binary files, declare specific attributes accordingly.

## 11. Making tests and code generation deterministic

Even with pinned compilers and dependencies, flaky tests or generators can destabilize builds.

Common culprits:

- Tests relying on the real system clock or default timezone.
- Tests using unseeded random numbers.
- Tests depending on execution order or shared mutable test state.
- Tests calling live external services whose data changes.
- Annotation processors or generators embedding timestamps in files.
- Tasks fetching unpinned snapshots over the network.
- Code iterating over unordered collections and writing output to files.

Best practices:

- Use `Clock.fixed()` when testing time-dependent logic.
- Use a fixed random seed in tests requiring repeatability.
- Sort data before serializing or writing files whenever order matters.
- Mock or run controlled test doubles with fixed fixtures rather than calling public APIs.
- Pin annotation processor and code-generator plugin versions.
- Omit current timestamps from generated sources unless strictly necessary.

Time test example:

```java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);
```

When every test run uses the same fixed clock, outcomes do not vary by the calendar date.

## 12. Controlling network access and offline builds

Running completely offline confirms dependencies are cached, yet offline execution alone does not guarantee reproducibility. If caches contain mismatched artifacts or the build uses dynamic dependencies, outputs can still vary across machines.

With Gradle:

```bash
./gradlew --offline clean build
```

With Maven:

```bash
./mvnw -o clean verify
```

These commands require dependencies to already exist in cache. They help catch tasks that unexpectedly hit the network during a build, while release builds still require fetching dependencies from controlled repositories, verifying checksums, and keeping trusted inputs.

Never let compile or test tasks hit external endpoints to generate sources or download unversioned data. When a task requires external data, turn that data into a versioned, checksum-verified artifact and declare it explicitly as a dependency.

## 13. Building in CI with the same workflow as developers

A CI pipeline should invoke the repository's wrapper, verify the JDK, and execute the same tasks developers run locally.

Gradle example:

```yaml
steps:
  - uses: actions/checkout@v4

  - name: Verify Java
    run: |
      java -version
      javac -version

  - name: Verify Gradle wrapper
    run: ./gradlew --version

  - name: Build and test
    run: ./gradlew --no-daemon clean build
```

Maven example:

```yaml
steps:
  - uses: actions/checkout@v4

  - name: Verify Java and Maven
    run: |
      java -version
      javac -version
      ./mvnw --version

  - name: Build and test
    run: ./mvnw --batch-mode --no-transfer-progress clean verify
```

CI actions themselves are build inputs. For pipelines requiring strict supply-chain controls, pin actions to a reviewed commit SHA rather than mutable tags. Similarly, pin container images by digest and control extra tools installed during jobs.

CI should execute on a clean workspace or fresh checkout to avoid picking up stale generated or cached files from prior runs. Dependency caches speed up builds, yet they must never be the sole source of unverified artifacts.

## 14. Verifying two builds produce identical outputs

Two green builds do not prove identical outputs. Compare checksums of generated files.

### 14.1. Linux/macOS

```bash
sha256sum build/libs/app.jar
```

Or on macOS:

```bash
shasum -a 256 build/libs/app.jar
```

### 14.2. Windows PowerShell

```powershell
Get-FileHash .\\build\\libs\\app.jar -Algorithm SHA256
```

Maven typically places JARs under `target/`; the Gradle Java plugin places them under `build/libs/`.

To truly verify reproducibility, build artifacts from two independent runs:

1. Check out the exact same source commit into two clean workspaces.
2. Use the same JDK distribution/build, wrapper, plugins, and dependencies.
3. Apply the same specified environment configuration.
4. Run the exact same build command.
5. Compare SHA-256 hashes of the artifacts.

If checksums differ, inspect archive contents:

```bash
jar tf app.jar
```

Extract both artifacts into separate directories and diff files. If classes and resources match while the JAR checksums differ, inspect timestamps, ZIP entry ordering, manifests, or archive metadata. If file contents differ, investigate code generation, dependency resolution, encoding, locale/timezone, and environment variables.

## 15. Example reproducible Gradle Java 17 configuration

Example `build.gradle.kts` combining key practices:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

plugins {
    java
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.0")
}

tasks.test {
    useJUnitPlatform()
}

dependencyLocking {
    lockAllConfigurations()
}
```

In this configuration:

- Toolchain requests JDK 17 for Java tasks.
- `options.release` constrains target APIs and bytecode to Java 17.
- Encoding is pinned to UTF-8.
- Archive tasks strip source timestamps and enforce deterministic file order.
- Dependencies specify exact versions.
- Dependency locking is enabled across configurations.

Next, run the build to generate lockfiles and verification metadata per project policy, and commit those files. Pin the Gradle Wrapper and daemon JDK in CI as covered earlier.

## 16. Example reproducible Maven Java 17 configuration

Example key sections in `pom.xml`:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>app</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <!-- Pin exact dependency versions -->
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

This is an illustrative skeleton; add dependencies and plugins matching your project. Pin the Maven Wrapper, compiler plugin, test/packaging plugins, and transitive dependencies. Keep the output timestamp consistent for a given source revision rather than changing it arbitrarily between builds.

Maven lacks a built-in dependency lockfile workflow identical to Gradle locking, so pay special attention to explicit versions, BOMs, repositories, and auditing `dependency:tree` and `effective-pom`.

## 17. Workflow for adopting reproducible builds in an existing project

Proceed in this order to isolate causes easily if differences appear:

1. **Record a baseline:** commit current sources, run a build, and save artifact checksums.
2. **Pin the JDK:** choose a Java 17 vendor/build and verify `java -version` and `javac -version`.
3. **Pin the build tool:** commit the Gradle Wrapper or Maven Wrapper and distribution checksums.
4. **Pin the compiler target:** configure `--release 17`.
5. **Pin plugins:** declare exact versions for every build plugin.
6. **Pin dependencies:** eliminate dynamic versions, ranges, and snapshots from release builds; govern transitive dependencies.
7. **Enable verification:** for Gradle, enable locking and dependency verification; for Maven, inspect effective POM, dependency tree, and repository policies.
8. **Normalize archives:** configure timestamps, file order, and generated metadata.
9. **Normalize the environment:** encoding, locale, timezone, paths, containers, and environment variables.
10. **Test in clean workspaces:** run the same command in two independent environments.
11. **Compare checksums:** investigate every discrepancy before releasing artifacts.

Avoid changing all variables simultaneously. Adjusting one configuration group at a time makes isolating checksum diffs much faster.

## 18. Common misconceptions

| Misconception | Reality |
| --- | --- |
| Setting `sourceCompatibility = 17` is enough to pin the build. | You must also pin the JDK/toolchain and use `--release 17` to restrict target APIs. |
| Any Java 17 JDK produces identical artifacts. | Vendor, patch/build, compiler, plugins, and environment can all affect outputs. |
| Installing Gradle/Maven globally is sufficient. | Wrappers pin the build tool per repository so CI and developers run the exact same version. |
| Pinning direct dependencies is enough. | Transitive dependencies and plugins are also inputs that must be controlled. |
| Two successful builds mean the build is reproducible. | You must compare artifacts, ideally via checksums from independent clean workspaces. |
| Running offline automatically guarantees reproducibility. | Offline only blocks network access; local caches can still hold unverified or divergent inputs. |
| Different JAR checksums always mean different classes. | Timestamps, ZIP entry ordering, and metadata also change archive checksums. |
| Only CI needs a pinned JDK. | Developers and CI should follow compatible setups; otherwise failures appear in only one environment. |
| Every environment variable must be pinned identically. | Only build-affecting variables need normalization or declaration; secrets and deployment configs are managed separately. |

## 19. Practice exercises

### Exercise 1 — Identify build inputs

List the JDK, Gradle/Maven, plugins, dependencies, repositories, environment variables, and container images used by your project. Distinguish which inputs are already pinned and which still vary.

### Exercise 2 — Pin the Java release

Configure Gradle or Maven to compile with Java 17 and `--release 17`. Try calling an API introduced only in a newer JDK to confirm the compiler rejects it.

### Exercise 3 — Use the Wrapper

Run `./gradlew --version` or `./mvnw --version`. Confirm the build tool version matches the repository wrapper config. Avoid invoking global build commands.

### Exercise 4 — Pin dependencies

Locate any dynamic versions, ranges, or snapshots in build files. Replace them with reviewed exact versions. For Gradle, enable dependency locking and generate lockfiles. Generate SHA-256 verification metadata and commit after review.

### Exercise 5 — Normalize archives

Configure archive tasks or `project.build.outputTimestamp`. Build twice from the same source in two separate workspaces and compare SHA-256 hashes.

### Exercise 6 — Track down sources of divergence

If checksums mismatch, compare JAR contents, manifests, ZIP entry timestamps, and generated resources. Check whether locale, timezone, encoding, username, hostname, or source paths leaked into artifacts.

### Exercise 7 — Set up clean CI

Create a CI job using a pinned JDK 17, the wrapper, and the same build command developers run. Run on a fresh checkout, log JDK/build tool versions, and record artifact checksums.

## 20. Quick reference

| Component | How to pin |
| --- | --- |
| Build runner JDK | Choose a specific vendor/build in CI or a digest-pinned container image. |
| Java compile/test toolchain | Gradle `java.toolchain` or Maven Toolchains. |
| Target API/bytecode | `--release 17`. |
| Gradle | Gradle Wrapper with pinned distribution version and SHA-256. |
| Maven | Maven Wrapper with pinned distribution version and SHA-256. |
| Build plugins | Pin exact versions and review upgrades. |
| Dependencies | Exact versions, BOM/version catalog, and transitive graph governance. |
| Gradle dependency state | Dependency locking and verification metadata. |
| Maven dependency state | Dependency management, effective POM, dependency tree, and repository policies. |
| Archives | Deterministic timestamps and file order. |
| Text resources | Explicit UTF-8, line endings, and locale/timezone. |
| Tests/code generation | Fixed clocks, seeds, and deterministic inputs; avoid mutable network data. |
| Output verification | Build in independent workspaces and compare SHA-256 checksums. |

**Core principle:** To achieve reproducible Java 17 builds, treat the JDK, build tools, plugins, dependencies, and environment as pinned, controlled inputs. Wrappers pin Gradle/Maven; toolchains select the JDK for compiling and testing; `--release 17` locks down target APIs; dependency locking/verification and deterministic archive metadata eliminate drift across runs. Ultimately, only matching checksums from artifacts built in independent clean workspaces provide direct evidence that a build is reproducible.
