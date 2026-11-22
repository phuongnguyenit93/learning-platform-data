# Build Environment in Java

A **build environment** is the set of tools, runtimes, operating system, configuration, environment variables, dependencies, and external data involved in producing an artifact. For the same commit, two builds can only produce identical results when the inputs that affect the artifact are identified and controlled.

A build may succeed on a developer's machine yet produce a different JAR on CI due to differences in JDK patch level, Gradle/Maven version, locale, timezone, file permissions, downloaded dependencies, system time, or environment variables. These differences reduce bug reproducibility and make it difficult to verify released artifacts.

The goal is to establish a Java build environment that can be described, inspected, and reproduced. Two concepts must be distinguished:

- **Reproducible build:** the same source and the same controlled inputs produce byte-for-byte identical artifacts.
- **Hermetic build:** a build that uses only declared inputs, without implicitly depending on machine state, network, or uncontrolled external resources.

A hermetic build may still not be reproducible if timestamps, file ordering, or random seeds vary. Conversely, two builds accidentally producing the same output do not prove that the entire environment is under control.

## 1. Components That Make Up the Build Environment

For a Java project, at least the following layers need to be considered:

| Component | Example inputs | How to control |
|---|---|---|
| JDK | Vendor, major/patch version, architecture | Java toolchain, pinned image or package |
| Build tool | Gradle/Maven and wrapper distribution | Gradle Wrapper or Maven Wrapper |
| Plugins and dependencies | Gradle plugins, Maven plugins, libraries | Fixed versions, dependency locking, and checksums |
| Operating system | Linux distribution, Windows, macOS | Fixed runner image/container |
| Architecture | x86_64, ARM64 | Explicit platform selection |
| Locale/encoding | Language, charset, collation | Explicit `LANG`, `LC_ALL`, UTF-8, and `Locale` |
| Timezone/clock | UTC, current time | `TZ=UTC`, deterministic timestamps |
| Filesystem | Paths, case sensitivity, permissions | Clean workspace, consistent layout |
| Environment variables | `JAVA_HOME`, `PATH`, proxy, flags | Allowlist and versioned configuration |
| Network/repository | Maven Central, plugin portal, mirrors | Stable repositories, dependency verification |
| Generated output | Code generation, archive timestamps | Explicitly declared task inputs/outputs |
| CI runner | Agent, image, actions/plugins | Version pinning and environment logging |

Not every difference affects every artifact. For example, locale may not affect a JAR containing only pure Java classes, but it can alter resources generated from templates or data sorted by collation. It is necessary to identify which inputs actually participate in the project's build.

## 2. Distinguishing Build Environment from Source Code and Build Configuration

Source code describes the program. Build configuration describes how to compile and package it. The build environment provides the runtime and system in which those configurations execute.

For example, `build.gradle.kts` may require a Java 17 toolchain, yet CI may still run Gradle using JDK 25. Both versions are part of the environment and must be recorded.

A project may declare:

- The JDK used to run Gradle.
- The JDK compiler used for compilation.
- The Java release target supported by the artifact.
- The Gradle Wrapper distribution.
- Dependency and plugin versions.
- The container image running the build.
- Locale, timezone, and important environment variables.

A good build configuration declares the required prerequisites instead of assuming the host machine already has the right tools installed.

## 3. Pinning the JDK and Java Toolchain

JDKs can differ by vendor, version, patch level, and architecture. Two builds of the same major version can still differ in compiler, implementation, security providers, or bug fixes.

Gradle Java Toolchains help select the JDK for compile/test tasks:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
```

The configuration above requests JDK 17 from the Adoptium vendor for tasks using the toolchain, while restricting language/API/bytecode to Java 17 and using UTF-8 during compilation.

A toolchain specified by major version does not pin the patch version. If strict build requirements need the exact JDK build to be determined, use a pinned JDK distribution in a container image or a package archive with a verified checksum. Record the output of `java --version`, `javac --version`, vendor, and architecture in the build metadata.

It is also important to distinguish the JVM running Gradle from the compiler's JDK toolchain. Check with:

```sh
java --version
javac --version
./gradlew --version
./gradlew -q javaToolchains
```

If `java --version` shows a different JDK than the compiler toolchain, that may be intentional by design. Record both values.

## 4. Pinning Gradle or Maven with the Wrapper

Do not rely on a globally installed Gradle/Maven on the runner. Commit the wrapper into the repository so developers and CI invoke the same build tool distribution.

Gradle Wrapper uses the `gradle/wrapper/gradle-wrapper.properties` file:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
```

When you need to protect the integrity of the distribution, add the `distributionSha256Sum` property with the actual checksum obtained from the official distribution page for the exact ZIP file chosen. Do not copy checksums from other versions or archives.

Wrapper files that should be tracked in Git:

- `gradlew`
- `gradlew.bat`
- `gradle/wrapper/gradle-wrapper.jar`
- `gradle/wrapper/gradle-wrapper.properties`

Run `./gradlew --version` to verify the actual distribution. When upgrading Gradle, update the wrapper in a separate pull request and check release notes, plugin compatibility, and the full build.

For Maven, use the Maven Wrapper (`mvnw`, `mvnw.cmd`, and `.mvn/wrapper`). Pin the Maven distribution in `maven-wrapper.properties`, verify the checksum if the wrapper version supports it, and run `./mvnw --version` in CI.

The wrapper pins the build tool, but does not automatically pin the JDK, plugins, dependencies, OS, or container image. Those layers must be controlled separately.

## 5. Pinning the Operating System and Container Image

A build running on Ubuntu, Windows, and macOS may encounter differences in path separators, filesystem case sensitivity, shells, permissions, native libraries, and pre-installed tools.

If building inside a container, the image is a critical input. Tags like `eclipse-temurin:17-jdk` select a JDK line, but tags can be updated. For builds requiring high immutability, pin the image by digest obtained directly from a trusted registry. The digest must match the exact image/platform; do not fabricate or copy digests from other images.

Multi-stage Dockerfile example:

```dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

COPY gradlew .
COPY gradle gradle
COPY settings.gradle.kts build.gradle.kts ./
RUN chmod +x gradlew

COPY src src
RUN ./gradlew --no-daemon clean build

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/*.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
```

This is an example of a multi-stage structure. To achieve immutable pinning, replace both `FROM` directives with image references that include verified digests. The build stage image and runtime stage image are two separate inputs.

A container does not freeze the entire host. The kernel, CPU architecture, container runtime, and build platform configuration can still differ. If producing native binaries, JNI libraries, or CPU-dependent artifacts, you must also pin the target architecture and native toolchain.

## 6. Selecting Architecture and Platform Explicitly

Do not assume `x86_64` and `ARM64` produce the same artifact. Pure Java bytecode is usually portable, but native images, JNI libraries, compressed assets, generated binaries, or dependencies with native classifiers may differ by architecture.

In CI:

- Explicitly specify the runner architecture.
- Select the Docker platform when building multi-architecture images.
- Do not mix native output caches between `x86_64` and `ARM64`.
- Separate the job matrix by OS/architecture if the product supports multiple platforms.
- Verify that the artifact is built for the right target platform before publishing.

If only a pure Java JAR is needed, you can build once on a standard platform and run compatibility tests on other runtimes. If packaging native libraries, you must build and test separately for each supported platform.

## 7. Standardizing Locale, Charset, and Timezone

The default locale affects number/date formatting, string sorting, case conversion, and certain libraries. The default charset affects reading/writing text if the code does not specify an encoding.

For example, locale-dependent number formatting can produce different results:

- A locale using a decimal comma: `12,50`.
- A locale using a decimal point: `12.50`.

For data or output that must be stable, specify the locale explicitly in code:

```java
import java.util.Locale;

public class FormatDemo {
    public static void main(String[] args) {
        String value = String.format(Locale.ROOT, "%.2f", 12.5);
        System.out.println(value);
    }
}
```

Compile and run:

```sh
javac FormatDemo.java
java FormatDemo
```

Stdout:

```text
12.50
```

`Locale.ROOT` is suitable for machine-readable formatting that does not depend on the user's language. For user-facing content, choose an explicit business locale instead of always forcing `ROOT`.

In CI, you can standardize:

```sh
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
```

Also set the encoding in the compiler/build tool:

- Gradle `JavaCompile`: `options.encoding = "UTF-8"`.
- Maven: `project.build.sourceEncoding=UTF-8`.
- When reading/writing files in Java, pass `StandardCharsets.UTF_8` explicitly.

Do not use the system locale for sorting or formatting business data if the result must be reproducible. Choose `Locale.ROOT`, a specific locale, or a deterministic comparator in code.

## 8. Controlling Timezone and System Time

The current time is a common hidden input. A build can produce different artifacts if it embeds build dates, timestamps, source generation times, or manifest timestamps.

Setting the job's timezone to UTC keeps logs and time-handling tools consistent:

```sh
export TZ=UTC
date -u
```

However, a UTC timezone does not make the clock fixed. If code calls `Instant.now()` or `System.currentTimeMillis()` to write into an artifact, each build can still differ.

Principles:

- Do not embed wall-clock time into artifacts unless necessary.
- If a build timestamp is needed, use a stable value tied to the source revision or release, not an arbitrary current time.
- Pass a fixed timestamp to code generators or archive tasks that support it.
- Do not use `LocalDateTime.now()` as default build data.
- Use UTC and `Instant` for actual points in time; use an injected `Clock` when testing is needed.

`SOURCE_DATE_EPOCH` is a convention supported by many build/release tools to provide a stable timestamp. Not every Java plugin or task reads this variable automatically; check the tool documentation and pass the value into the appropriate task or archive configuration.

## 9. Controlling Environment Variables

Environment variables can alter the JVM, build tool, dependency resolution, and code generators. Some variables commonly worth reviewing:

| Variable | Impact |
|---|---|
| `JAVA_HOME` | Default JVM used to run Gradle/Maven |
| `PATH` | Versions of `java`, `javac`, shell, and invoked tools |
| `JAVA_TOOL_OPTIONS` | JVM options injected into Java processes |
| `_JAVA_OPTIONS` | Additional JVM options on some runtimes |
| `GRADLE_OPTS` | JVM options for the Gradle client |
| `MAVEN_OPTS` | JVM options for Maven |
| `GRADLE_USER_HOME` | Gradle cache, init scripts, and user configuration |
| `HOME` / `USERPROFILE` | Maven/Gradle config and user-level files |
| `TMPDIR` / `TEMP` | Temporary directory |
| `LANG` / `LC_ALL` | Locale and charset |
| `TZ` | Timezone |
| `HTTP_PROXY` / `HTTPS_PROXY` | Network path to repositories |
| `CI` / `BUILD_NUMBER` | Build scripts or plugins may use these as metadata |

Do not dump the entire environment into logs, as this can expose tokens, passwords, signing keys, or repository credentials. Log only an allowlist of non-sensitive variables and record configured secret names without printing their values.

Build scripts should not silently change their output based on `BUILD_NUMBER`, branch name, username, or home path. If such metadata is needed, decide explicitly whether it belongs inside the artifact or only in external logs.

## 10. Pinning Filesystem, Paths, and File Permissions

Different filesystems can alter build results:

- Linux is typically case-sensitive in filenames; some Windows/macOS filesystems are case-insensitive by default.
- Path separators differ (`/` and `\`).
- Permission bits and executable bits differ.
- Symbolic links may be handled differently depending on OS and runner.
- The order of files listed from the filesystem should not be assumed stable.
- Line endings may be `LF` or `CRLF`.

To reduce differences:

1. Use a clean workspace for every build.
2. Do not rely on leftover files from a previous build.
3. Sort file lists before passing them to generators or archives.
4. Use Java's path API (`Path`, `Paths`) instead of manual string concatenation for paths.
5. Normalize line endings with `.gitattributes`.
6. Track script executable bits in Git.
7. Do not include the workspace's absolute path in artifact contents.

Example `.gitattributes`:

```gitattributes
*.java text eol=lf
*.kt text eol=lf
*.kts text eol=lf
*.properties text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
```

This configuration ensures Git checks out each file type with the chosen line endings. When adding new files, check `git diff --check` and line-ending status before building.

## 11. Dependency Repositories and Network

A build can become non-reproducible if dependencies are resolved from dynamic versions or repositories whose contents change over time.

Avoid declaring:

- Dynamic versions such as `1.+`.
- Unlocked version ranges.
- Snapshot dependencies that change under the same coordinates.
- Unpinned plugin versions.
- Internal repositories that overwrite artifacts at the same coordinates.
- Direct file downloads without checksum verification.

Recommended practices:

- Specify exact dependency and plugin versions.
- Use dependency locking to record the resolved graph.
- Enable dependency verification with checksums/signatures.
- Use trusted repositories and define explicit artifact ordering/sources.
- Never republish an artifact with different content under the same group/name/version.
- Store released artifacts in immutable repositories.
- Record mirrors/proxies if they are part of the dependency resolution path.

With Gradle, you can enable dependency locking:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

After configuring, resolve the required configurations and write the lock state:

```sh
./gradlew build --write-locks
```

Dependency verification can generate SHA-256 metadata:

```sh
./gradlew --write-verification-metadata sha256 help
```

Inspect and review lock/verification metadata files before committing. Never automatically accept new checksums without verifying the dependency source.

## 12. Managing Plugins and Build Logic

Plugins are also build dependencies. A new plugin can change the task graph, compiler arguments, archive metadata, or how dependencies are resolved.

Best practices:

- Pin plugin versions in the `plugins` block or `pluginManagement`.
- Do not use dynamic versions for production plugins.
- Verify plugin compatibility with Gradle/Maven and the JDK.
- Version convention plugins and build logic inside the repository.
- Review init scripts and global Gradle/Maven settings, as they can alter a build without appearing in the repository.
- Avoid depending on plugins installed separately on the runner.

`GRADLE_USER_HOME` can contain `init.gradle`, `init.d`, and caches that affect the build. For reproducible CI, use a dedicated user home or control the contents of init scripts; do not rely on unversioned global configuration.

## 13. Standardizing the Gradle Build Environment

Example `gradle.properties`:

```properties
org.gradle.jvmargs=-Dfile.encoding=UTF-8 -Duser.timezone=UTC
org.gradle.caching=true
org.gradle.daemon=false
```

These properties standardize encoding/timezone for the Gradle JVM, enable the build cache, and disable the daemon in CI environments to reduce the impact of long-lived processes across jobs. Depending on runner architecture, the daemon may be used for speed; the key is ensuring stale state never alters the output.

Configure archive tasks for stable file ordering and timestamps:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

`isPreserveFileTimestamps = false` normalizes entry timestamps in archives; `isReproducibleFileOrder = true` enforces a stable entry order. These settings do not automatically fix timestamps or content written into files by code generators before archiving.

You can create a task to log non-sensitive environment properties:

```kotlin
tasks.register("printBuildEnvironment") {
    doLast {
        println("gradle=" + gradle.gradleVersion)
        println("java.version=" + System.getProperty("java.version"))
        println("java.vendor=" + System.getProperty("java.vendor"))
        println("os.name=" + System.getProperty("os.name"))
        println("os.arch=" + System.getProperty("os.arch"))
        println("user.timezone=" + System.getProperty("user.timezone"))
        println("file.encoding=" + System.getProperty("file.encoding"))
    }
}
```

Run:

```sh
./gradlew printBuildEnvironment
```

This task only logs diagnostic information; do not embed machine-specific details like usernames or absolute workspace paths into artifacts.

## 14. Standardizing the Maven Build Environment

With Maven, declare encoding, Java release, and output timestamp:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

The timestamp in the example is an illustrative fixed value. In a real project, you can pass a deterministic timestamp from the source revision or release process, as long as every compared build receives the same value.

Key Maven plugins and archive components need explicitly pinned versions. For example:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>
    </plugins>
</build>
```

The versions above are illustrative examples of plugin pinning; verify compatibility and choose organization-approved versions before use. Use the Maven Wrapper to pin the Maven distribution and the Maven Enforcer Plugin if minimum Maven/JDK version checks are required.

## 15. Generated Sources and Code Generation

Generated sources are a frequent source of differences because tools may embed timestamps, absolute paths, input ordering, or generator versions into the output.

Examples of code generation tools:

- OpenAPI Generator.
- Protocol Buffers compiler.
- JAXB/XJC.
- Annotation processors.
- SQL/schema code generators.
- Frontend asset bundlers invoked from Gradle/Maven.

For stable output:

1. Pin generator and plugin versions.
2. Declare all schema/input files completely.
3. Sort input lists if ordering is significant.
4. Do not embed the current time into generated files.
5. Do not embed absolute paths or usernames.
6. Pin locale/encoding.
7. Declare task dependencies so generators run before compilation.
8. Write output to a dedicated build directory rather than modifying developer-managed sources.
9. Verify whether generated files differ between two builds.

Generator tasks must declare inputs/outputs so Gradle knows when to rerun the task and can cache its output. A task that depends on undeclared environment variables or files outside the repository may return stale cached output.

## 16. Randomness, Parallelism, and Processing Order

Build scripts or generators can produce unstable output if they use random numbers, unordered concurrent collections, or non-deterministic file traversal order.

For example, do not rely on the iteration order of a `HashSet` to generate a config file. Sort before serializing:

```java
import java.util.List;

public class StableOrderDemo {
    public static void main(String[] args) {
        List<String> names = List.of("gamma", "alpha", "beta");
        String output = names.stream()
                .sorted()
                .reduce((left, right) -> left + "," + right)
                .orElse("");

        System.out.println(output);
    }
}
```

Compile and run:

```sh
javac StableOrderDemo.java
java StableOrderDemo
```

Stdout:

```text
alpha,beta,gamma
```

If randomness is needed in builds/tests, use an explicitly declared seed and log it. Do not use `System.nanoTime()` or the current time as a seed when repeatable results are required.

Parallel builds can change log ordering or expose tasks with missing dependency declarations. Task outputs must not depend on arbitrary execution order. Declare complete task inputs/outputs and dependency graphs; disable parallelism only to isolate race conditions, not as a permanent fix.

## 17. Recording the Build Environment Without Exposing Secrets

Every CI build should store an environment manifest outside the artifact or as intentional build metadata.

You can record:

- Git commit SHA and working tree status.
- JDK vendor/version/architecture.
- Gradle/Maven Wrapper version.
- OS/container image and digest.
- Locale, timezone, and encoding.
- Runner OS/architecture.
- Plugin/dependency lock state.
- Non-sensitive environment variables that affect the build.
- Timestamp or source timestamp if the build uses one.
- Command line executed.

Example commands to record in Linux CI:

```sh
git rev-parse HEAD
git status --short
java --version
javac --version
./gradlew --version
uname -a
locale
date -u
printenv LANG LC_ALL TZ JAVA_HOME
```

The commands above print only selected variables. Do not use `env`, `printenv` without arguments, or `set` in CI logs if the environment contains secrets.

On Windows PowerShell, you can record:

```powershell
git rev-parse HEAD
java --version
javac --version
.\gradlew.bat --version
Get-Culture
Get-TimeZone
$env:JAVA_HOME
$env:PROCESSOR_ARCHITECTURE
```

Store the manifest alongside build logs or artifact provenance. Avoid embedding personal paths, tokens, sensitive hostnames, or confidential information into public artifacts.

## 18. Verifying with Two Clean Builds

A practical verification method is to build the same commit in two independent workspaces without reusing outputs from the previous run.

Procedure:

1. Check out the same commit SHA into two different directories.
2. Use the same JDK, Wrapper, container image, dependency locks, and environment configuration.
3. Use separate caches or build offline after downloading the exact dependency versions.
4. Run the same command, e.g. `./gradlew --no-daemon clean build`.
5. Collect the artifact from each workspace.
6. Compare SHA-256 checksums.
7. If checksums differ, inspect archive contents, timestamps, entry ordering, and generated files.

Linux example:

```sh
sha256sum build-a/build/libs/app.jar
sha256sum build-b/build/libs/app.jar
```

If both checksums match, the two files are byte-for-byte identical. If they differ, inspect the details:

```sh
unzip -l build-a/build/libs/app.jar
unzip -l build-b/build/libs/app.jar
diffoscope build-a/build/libs/app.jar build-b/build/libs/app.jar
```

`diffoscope` helps pinpoint deep differences inside archives if installed. You can also use `jar tf` to compare entry lists and extract both JARs to compare individual files.

Do not compare two builds on different JDKs or OSes and conclude the build is non-reproducible if the test goal is the same environment. First compare two equivalent environments; then expand to cross-platform compatibility.

## 19. Byte-for-Byte vs. Functional Equivalence

Two artifacts can run identically yet differ in bytes. For example:

- JARs have different entry timestamps.
- Manifests contain `Build-Time`.
- Files are compressed in a different order.
- Generated sources contain workspace paths.
- Debug metadata records different information.
- The dependency graph changed, but the tested code paths do not exercise the changed parts.

Functional tests only prove equivalent tested behavior. They do not prove byte-for-byte artifact identity.

Conversely, two JARs having the same checksum is strong evidence of byte identity, but does not automatically prove that external dependencies, runtime images, or deployment configurations are also identical.

Define the target requirements clearly:

- **Functional repeatability:** the same inputs produce equivalent tested behavior.
- **Artifact reproducibility:** the same inputs produce byte-for-byte identical artifacts.
- **Environment reproducibility:** the environment and dependencies can be reconstructed from versioned declarations.
- **Hermeticity:** the build reads no inputs outside the declared list.

A pipeline can pursue multiple levels simultaneously, but each goal must be verified with the appropriate method.

## 20. Configuring CI to Reproduce the Environment

A well-configured CI pipeline should:

- Use a runner image or container image with an explicit version.
- Pin the image digest when an immutable environment is required.
- Install the exact JDK vendor/version and verify with `java --version`.
- Use the Wrapper committed in the repository.
- Resolve dependencies only from approved repositories.
- Use dependency locking and verification.
- Standardize locale, timezone, and encoding.
- Start with a clean workspace.
- Never allow secrets or build-number variables to alter artifact contents unintentionally.
- Store the environment manifest, logs, and artifact checksums.
- Run reproducibility checks periodically or before releases.

Caches reduce build time but must never be the source of truth for dependencies/versions. On a cache miss, the build must still resolve the exact pinned dependencies. On a cache hit, the build must ensure the cache key includes critical inputs such as the Wrapper, JDK/toolchain, dependency locks, and OS/architecture if relevant.

## 21. Common Pitfalls When Controlling the Build Environment

| Symptom | Possible cause | Resolution |
|---|---|---|
| Developer build passes, CI fails | Different JDK, OS, `PATH`, or environment variables | Record manifest and compare environments |
| Same commit produces JAR with different checksum | Timestamps, file order, manifest, or generated content changed | Inspect archive entries and generators |
| Build only works with Internet access | Dependencies/plugins uncached or incompletely declared | Pin dependencies, prepare repository mirror, and test offline |
| Displayed JDK is right, but compiler differs | Toolchain selects a different JDK than the build JVM | Check `javaToolchains` and compiler tasks |
| Vietnamese/non-ASCII resources are corrupted | Different default encodings | Use UTF-8 in source/resource processing |
| Sort results differ across machines | Unspecified locale or non-deterministic iteration order | Use explicit `Locale`/`Comparator` and sort inputs |
| Timestamps inside JAR change | Archive or generator uses wall-clock time | Normalize archive timestamps and build metadata |
| Build fails on Windows | Case sensitivity, path, or shell differences | Check filenames, path APIs, and cross-platform scripts |
| Build output contains machine paths | Generator or compiler embeds absolute paths | Use relative paths and strip workspace info |
| Task cache returns stale output | Task lacks input declarations or reads hidden env vars | Declare all inputs/outputs and environment inputs |
| Dependency changes despite unchanged version | `SNAPSHOT` or repository overwrites artifacts | Use immutable releases, locking, and verification |
| Native artifacts differ across runners | Different architecture, compiler, or native libraries | Pin platform/toolchain and build per architecture |
| CI logs accidentally leak credentials | Printing entire environment or commands with secrets | Log only an allowlist and use secret masking |

## 22. Runbook for Setting Up a New Build Environment

When creating a pipeline for a Java project:

1. Choose the minimum Java runtime and JDK vendor/version.
2. Choose a compatible Gradle/Maven Wrapper.
3. Configure the Java toolchain and `--release`.
4. Choose the OS/architecture and container image.
5. Standardize locale, timezone, charset, and line endings.
6. Control `JAVA_HOME`, `PATH`, JVM options, home/cache, and temp directories.
7. Pin plugins/dependencies and enable locking/checksum verification.
8. Declare generated sources and task inputs/outputs completely.
9. Normalize timestamps and archive entry ordering.
10. Record a build environment manifest without secrets.
11. Build the same commit in two clean workspaces.
12. Compare checksums and investigate any differences.
13. Store logs, manifest, checksums, and artifact provenance.
14. Repeat verification after upgrading the JDK, build tool, image, or plugins.

## 23. Checklist

- [ ] All build environment components have been fully identified.
- [ ] JDK vendor/version or container image containing the JDK is pinned.
- [ ] Both the build-running JDK and the toolchain JDK are verified.
- [ ] Gradle/Maven Wrapper and distribution checksum (if applicable) are pinned.
- [ ] OS, architecture, and image digest (when needed) are pinned.
- [ ] Locale, UTF-8, timezone, and line endings are standardized.
- [ ] Environment variables that can affect the build are audited.
- [ ] Secrets are prevented from being printed to CI logs.
- [ ] Dependencies, plugins, repositories, and checksums are controlled.
- [ ] Task inputs/outputs and generated sources are explicitly declared.
- [ ] Timestamps and archive entry ordering are normalized.
- [ ] Clean workspaces are used without relying on leftover files.
- [ ] Environment manifest and Git commit SHA are recorded.
- [ ] The same commit has been built in two clean environments.
- [ ] SHA-256 checksums are compared and archive contents inspected on mismatch.
- [ ] Artifact provenance and version upgrade procedures are documented.

## 24. References

- Gradle User Manual — Reproducible Archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Gradle User Manual — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle User Manual — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle User Manual — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Maven — Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Docker Docs — Image Digests: https://docs.docker.com/dhi/core-concepts/digests/
- Reproducible Builds — SOURCE_DATE_EPOCH: https://reproducible-builds.org/docs/source-date-epoch/
- Git Attributes — End-of-line conversion: https://git-scm.com/docs/gitattributes

A reproducible build environment must be described by concrete inputs: JDK, Wrapper, plugins/dependencies, OS/container, locale, timezone, filesystem, and environment variables. When these inputs are controlled, tasks are completely declared, and timestamps/archives are normalized, you can build the same commit in two clean workspaces and compare checksums to confirm whether the artifact is reproducible.
