# Not Recording the Toolchain in Java Projects

**Not recording the toolchain** is an anti-pattern that occurs when a team only stores source code and build commands, without storing or controlling the versions of the tools that actually produce the artifact. Each machine may use a different JDK, Gradle/Maven version, compiler, plugin, and dependency set. A build may still succeed on both machines while producing different bytecode, metadata, dependency graphs, or test results.

A good toolchain record must answer two questions: **what environment the project requires to build**, and **what environment a specific build actually used**. The first is configuration that can be reviewed in the repository; the second is provenance recorded in CI or a build report. Missing either one makes bugs hard to reproduce and hard to explain.

## 1. What Components Make Up a Toolchain?

In Java, a toolchain is not just the Java version written in `pom.xml` or `build.gradle`.

| Component | Example | Why it needs to be recorded |
| --- | --- | --- |
| Build tool | Gradle 9.2.1, Maven 3.9.12 | Different versions can change lifecycle, tasks, dependency resolution, or plugin compatibility |
| JVM running the build tool | Azul Zulu JDK 24.0.2 | Runs the Gradle daemon/Maven and plugins that do not use a separate toolchain |
| JDK compiler | Amazon Corretto 17.0.15 | Determines the actual compiler, language features, and bytecode |
| Java release target | `--release 17` | Specifies the language/API level and class-file target |
| Test/runtime JDK | JDK 17, 21, or 24 | May differ from the compiler JDK; affects test and runtime behavior |
| Build plugins | Compiler Plugin 3.13.0, Surefire 3.5.2 | Plugins are also part of the build logic |
| Dependencies | Direct and transitive libraries | Resolved versions can change over time |
| OS and architecture | Windows 11/amd64, Ubuntu Linux/arm64 | Affects native tools, file system, line endings, and artifacts |
| CI/container image | Runner label or image digest | Images can be updated even when the workflow does not change |
| Build environment | Locale, timezone, encoding, JVM flags | Can alter tests, generated files, and output |

It is important to distinguish the following concepts:

- **Build JVM**: the JVM running Gradle/Maven itself.
- **Compiler toolchain**: the JDK providing `javac` for compilation.
- **Test launcher**: the JVM running tests.
- **Release target**: the Java version whose syntax, bytecode, and public API the compiler must conform to.
- **Production runtime**: the actual JRE/JDK running the application after deployment.

These components can be the same version, but they do not have to be. For example, Gradle can run on JDK 24, use a JDK 17 compiler/test toolchain, and produce Java 17-compatible classes.

## 2. Why Does Not Recording the Toolchain Cause Bugs?

### Green builds with different artifacts

Developer A uses JDK 17, developer B uses JDK 24. Both set source/target or `maven.compiler.release` to 17. If the compiler JDK is not controlled, differences in compiler implementation, plugins, generated metadata, and environment can still appear.

### Bugs that only reproduce on one machine

A build that depends on the state of `JAVA_HOME`, `PATH`, IDE JDK, or `~/.m2/toolchains.xml` not described by the repository leaves others unable to tell which compiler or test JVM was selected.

### Unintentional tool upgrades

Running `gradle build` uses the globally installed Gradle. A machine with Gradle 8.5 may run a build differently from a machine with Gradle 9.2.1. Similarly, `mvn package` may use different Maven versions on different machines.

### Dependencies and plugins changing on their own

Dynamic versions such as `1.+`, `latest.release`, version ranges, or unpinned plugins can resolve to a newer version on another day. A build with unchanged source code can still receive a different dependency graph.

### Insufficient evidence to investigate a release

When production fails, having only the JAR and commit ID is not enough. The team needs to know the JDK, compiler, build tool, plugins, dependencies, OS, command, and build parameters that produced that JAR.

## 3. What Information Should Be Recorded?

A toolchain manifest for each build should include the following fields:

1. Commit SHA and working tree status.
2. Build command, tasks/goals, Maven profiles, and build flags.
3. Build tool with its actual version; wrapper distribution URL and checksum if applicable.
4. JVM running the build tool: full version, vendor, and runtime.
5. Compiler JDK: language version, vendor, and full version when possible.
6. Test JVM and runtime JDK if different from the compiler.
7. Configured Java release/source/target.
8. Versions of build plugins and resolved dependencies.
9. OS, OS version, CPU architecture, and container image digest.
10. Locale, timezone, file encoding, and relevant JVM flags.
11. CI provider, runner image/label, workflow revision, and action versions.
12. Checksums of output artifacts and dependency verification metadata when applicable.

Not all information needs to be stored in a single file. The Wrapper and build files store stable requirements; CI reports store observed information; lockfiles and verification metadata store dependency state. They can be combined into a single build provenance report.

**Do not put secrets into the report.** Do not dump all environment variables, Maven `settings.xml`, tokens, passwords, private keys, or credential contents. Record only selected variables and redact sensitive values.

## 4. Checking the Toolchain Currently in Use

Run the following commands from the repository root to inspect the current environment.

### Java and compiler

```bash
java --version
javac --version
```

On Windows PowerShell:

```powershell
Get-Command java, javac
where.exe java
where.exe javac
```

`java --version` shows the runtime invoked via `PATH`; `javac --version` shows the compiler invoked via `PATH`. These commands do not prove that Gradle or Maven is using the same JDK, because the build tool may select a different daemon JVM or toolchain.

### Gradle

```bash
./gradlew --version
./gradlew javaToolchains
```

On Windows:

```powershell
.\gradlew.bat --version
.\gradlew.bat javaToolchains
```

`--version` displays the Gradle version and JVM launcher/daemon information. `javaToolchains` lists the JDKs discovered by Gradle, including version, vendor, architecture, and installation location. If the project uses the Java Plugin, run this task to verify which toolchains are actually available.

### Maven

```bash
./mvnw --version
./mvnw help:effective-pom
./mvnw dependency:tree
```

You can list the JDK toolchains discovered by Maven:

```bash
./mvnw toolchains:display-discovered-jdk-toolchains
```

The JDK discovery goal is available in the Maven Toolchains Plugin starting from version 3.2.0. `mvn -version` shows the JVM running Maven; if Maven Toolchains selects a different JDK for the compiler or Surefire, the toolchain selection log shows the JDK used by those respective plugins.

## 5. Pinning the Build Tool with a Wrapper

A Wrapper stores the build tool version in the repository and ensures every developer and CI runner invokes the same distribution.

### Gradle Wrapper

Commit the wrapper files to Git:

```text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

Example `gradle/wrapper/gradle-wrapper.properties`:

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.2.1-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

`distributionUrl` must point to a specific version. You can add `distributionSha256Sum` with the official SHA-256 of the distribution so the Wrapper verifies the downloaded file. Obtain the checksum from the release checksums page independently of the ZIP file; do not compute the checksum of an unverified file yourself and treat it as trusted proof.

Using the Wrapper:

```bash
./gradlew clean check
```

Windows:

```powershell
.\gradlew.bat clean check
```

Do not use `gradle build` in project documentation or CI when the repository already has a Wrapper. That command depends on a globally installed Gradle.

### Maven Wrapper

Commit the Maven Wrapper files, including `mvnw`, `mvnw.cmd`, the wrapper JAR, and `.mvn/wrapper/maven-wrapper.properties`. In the properties file, set `distributionUrl` to a specific Maven distribution version, such as Maven 3.9.12.

Run:

```bash
./mvnw --batch-mode clean verify
```

Windows:

```powershell
.\mvnw.cmd --batch-mode clean verify
```

The Maven Wrapper pins the Maven distribution. The JDK running Maven still must be configured and verified separately via `JAVA_HOME`, CI setup, or Maven Enforcer. If the compiler needs a different JDK, configure Maven Toolchains.

## 6. Distinguishing Gradle Daemon JVM, Compiler JDK, and Release Target

Gradle can use different JVMs for the client, daemon, compiler, and tests. The JVM launching the Wrapper/Gradle client is usually determined by `JAVA_HOME`, `PATH`, or the IDE. The daemon can use a JVM specified by `org.gradle.java.home`, the Tooling API, or daemon JVM criteria. The project's Java toolchain controls compiler, test, and Javadoc tasks.

Example `build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

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

Here, Gradle selects JDK 17 for the project's Java tasks; `options.release = 17` ensures the compiler conforms to the Java 17 API/language level. If you want to require a specific vendor, you can add `vendor = JvmVendorSpec.ADOPTIUM` or a vendor matching the project's policy.

Do not confuse `options.release` with the toolchain. `--release 17` does not install JDK 17, does not select `javac` 17, and does not control the JVM running Gradle. It controls how the compiler compiles the source code.

### Recording the build JVM and toolchain in a report

Gradle provides `JavaToolchainService` to query the selected compiler and launcher. You can create a task to write a report to `build/reports/toolchain/toolchain.txt`:

```groovy
def toolchains = extensions.getByType(
    org.gradle.jvm.toolchain.JavaToolchainService
)

tasks.register('toolchainReport') {
    doLast {
        def compiler = toolchains.compilerFor(java.toolchain).get()
        def launcher = toolchains.launcherFor(java.toolchain).get()

        def compilerMetadata = compiler.metadata
        def launcherMetadata = launcher.metadata

        def lines = [
            "gradle.version=" + gradle.gradleVersion,
            "build.jvm.version=" + System.getProperty('java.version'),
            "build.jvm.vendor=" + System.getProperty('java.vendor'),
            "compiler.language.version=" + compilerMetadata.languageVersion,
            "compiler.vendor=" + compilerMetadata.vendor,
            "launcher.language.version=" + launcherMetadata.languageVersion,
            "launcher.vendor=" + launcherMetadata.vendor,
            "java.release=17",
            "os.name=" + System.getProperty('os.name'),
            "os.arch=" + System.getProperty('os.arch')
        ]

        def output = layout.buildDirectory
            .file('reports/toolchain/toolchain.txt')
            .get()
            .asFile

        output.parentFile.mkdirs()
        output.setText(
            lines.join(System.lineSeparator()) + System.lineSeparator(),
            'UTF-8'
        )

        println(lines.join(System.lineSeparator()))
    }
}
```

You can add a small Java program to record the full runtime version of the test launcher. File `src/main/java/com/example/ToolchainProbe.java`:

```java
package com.example;

public final class ToolchainProbe {
    private ToolchainProbe() {
    }

    public static void main(String[] args) {
        System.out.println("runtime.version=" + Runtime.version());
        System.out.println("runtime.vendor=" + System.getProperty("java.vendor"));
        System.out.println("runtime.vm=" + System.getProperty("java.vm.name"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
    }
}
```

Register a task to run the program using the selected toolchain:

```groovy
tasks.register('toolchainProbe', JavaExec) {
    dependsOn tasks.named('classes')
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.ToolchainProbe'
    javaLauncher = toolchains.launcherFor(java.toolchain)
}
```

Run and save the report:

```bash
./gradlew toolchainReport toolchainProbe javaToolchains
```

Verified example on Windows 11: Gradle 9.2.1 runs on Azul Zulu JDK 24.0.2, while the project selects Amazon Corretto JDK 17.0.15 for the compiler and launcher. `options.release` is also 17.

```text
gradle.version=9.2.1
build.jvm.version=24.0.2
build.jvm.vendor=Azul Systems, Inc.
compiler.language.version=17
compiler.vendor=Amazon Corretto
launcher.language.version=17
launcher.vendor=Amazon Corretto
java.release=17
os.name=Windows 11
os.arch=amd64

runtime.version=17.0.15+6-LTS
runtime.vendor=Amazon.com Inc.
os.name=Windows 11
os.arch=amd64
```

This is a concrete example showing that the build JVM, compiler/test JDK, and release target are three separate pieces of information. If you need to pin an exact patch version or vendor, CI must provision the exact distribution/version and report the full version; `languageVersion = 17` only specifies the Java major version.

### Recording the Gradle daemon JVM

In Gradle, `gradlew --version` helps inspect the launcher and daemon JVMs. With Gradle versions that support daemon JVM criteria, the `updateDaemonJvm` task can generate `gradle/gradle-daemon-jvm.properties` to declare the daemon's JVM requirements:

```bash
./gradlew updateDaemonJvm --jvm-version=17
```

Commit the criteria file if the project uses this mechanism and verify compatibility with the Gradle Wrapper version. When using `org.gradle.java.home`, avoid committing absolute paths from a developer's machine; those paths usually differ on CI and other people's machines.

## 7. Recording Maven Runtime and JDK Toolchain Separately

`mvn -version` shows the Maven version and the Java runtime running Maven. If Maven Toolchains is configured, the compiler, Surefire, Javadoc, or JAR Plugin can use a different JDK.

### Locking Maven and the JDK running Maven with Enforcer

Example POM requiring Maven 3.9.x and Maven runtime JDK 24:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-enforcer-plugin</artifactId>
  <version>3.6.3</version>
  <executions>
    <execution>
      <id>enforce-build-runtime</id>
      <goals>
        <goal>enforce</goal>
      </goals>
      <configuration>
        <rules>
          <requireMavenVersion>
            <version>[3.9,4)</version>
          </requireMavenVersion>
          <requireJavaVersion>
            <version>[24,25)</version>
          </requireJavaVersion>
        </rules>
      </configuration>
    </execution>
  </executions>
</plugin>
```

Adjust the ranges according to your support policy. `requireJavaVersion` checks the JVM running Maven; it does not automatically select the compiler JDK if Maven Toolchains is configured separately.

### Selecting the compiler JDK with Maven Toolchains

In `pom.xml`, declare the JDK that toolchain-aware plugins must use:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-toolchains-plugin</artifactId>
  <version>3.3.0</version>
  <executions>
    <execution>
      <goals>
        <goal>toolchain</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <toolchains>
      <jdk>
        <version>17</version>
        <vendor>Amazon Corretto</vendor>
      </jdk>
    </toolchains>
  </configuration>
</plugin>
```

Each developer/runner declares the JDK paths on their machine in `~/.m2/toolchains.xml`. Example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>Amazon Corretto</vendor>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/corretto-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
```

`jdkHome` is the JDK installation path on the current machine. This path belongs to local/runner configuration; the repository only declares version/vendor criteria to avoid forcing every machine to use the same absolute path.

Maven Toolchains Plugin finds a matching configuration and provides the JDK to plugins that support toolchains. When running, the log shows which JDK was selected:

```bash
./mvnw --batch-mode verify
```

If no matching toolchain is found, the build should fail early in the `validate` phase with a clear message. Do not fall back to compiling with an arbitrary JDK on `PATH`.

### Release is still a separate configuration

In the Maven Compiler Plugin:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>17</release>
    <encoding>UTF-8</encoding>
  </configuration>
</plugin>
```

`release` controls the source/API/bytecode target; Maven Toolchains selects the actual JDK for the compiler. If Maven runs on JDK 24 and the toolchain selects JDK 17, the log may show both versions. This is a valid configuration when the project has clearly defined its rationale and compatibility policy.

### Verified Maven example

The test environment used Maven 3.9.12 running on Azul Zulu JDK 24.0.2. Maven Enforcer verified the Maven/JDK runtime; Maven Toolchains Plugin 3.3.0 selected Amazon Corretto JDK 17.0.15; Compiler Plugin 3.13.0 compiled with `release 17`; Surefire 3.5.2 and JAR Plugin 3.4.2 also received the JDK 17 toolchain. The `package` build succeeded.

## 8. Pinning Plugin and Dependency Versions

The Wrapper pins the build tool, but it does not automatically pin every plugin or dependency. Versions must be specified explicitly in the build configuration.

### Gradle

Use a version catalog to centralize versions:

```toml
[versions]
junit = "5.11.4"
spotbugs = "6.0.26"

[libraries]
junit-bom = { module = "org.junit:junit-bom", version.ref = "junit" }
```

Declare plugin versions explicitly in the `plugins` block or plugin management. Avoid dynamic versions such as `1.+`, `latest.release`, or uncontrolled snapshots.

Enable dependency locking for configurations:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Generate/update the lock state when intentionally changing dependencies:

```bash
./gradlew dependencies --write-locks
```

Commit `gradle.lockfile` and review the diff when the lockfile changes. Locking records resolved dependency versions, including transitive dependencies. For the buildscript/plugin classpath, configure corresponding locking if you want to lock the build logic as well.

You can enable dependency verification to check checksums/signatures of downloaded artifacts:

```bash
./gradlew --write-verification-metadata sha256
```

This command generates `gradle/verification-metadata.xml`. Generate metadata from verified dependencies, review checksums/signatures, and commit the file. Do not blindly trust all checksums bootstrapped from a repository that may already be compromised.

### Maven

A Maven project should:

- Declare dependency versions centrally in `dependencyManagement` or a BOM.
- Pin build plugin versions in `pluginManagement` or `plugins`.
- Avoid `LATEST`, `RELEASE`, wide version ranges, and `SNAPSHOT` dependencies in release builds.
- Use Enforcer to check Maven/JDK requirements and project rules.
- Save `help:effective-pom` and `dependency:tree` when investigating a specific build.

Maven does not have a built-in dependency lockfile in the same way Gradle does. Therefore, declare versions explicitly, manage transitive dependencies through a BOM/`dependencyManagement`, fix plugin versions, and save the release dependency tree when traceability is needed.

## 9. Recording the Toolchain in CI

CI should run the Wrapper, install the right JDK distribution/version, and save the report alongside build artifacts. GitHub Actions example for Gradle:

```yaml
name: Java Build Provenance

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle

      - name: Record build JVM and compiler discovery
        run: |
          java --version
          javac --version
          ./gradlew --version
          ./gradlew javaToolchains

      - name: Build and write toolchain report
        run: ./gradlew --no-daemon clean toolchainReport toolchainProbe check

      - name: Record source revision
        run: |
          git rev-parse HEAD
          git status --short

      - name: Upload provenance report
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: java-toolchain-report
          path: build/reports/toolchain/toolchain.txt
          if-no-files-found: ignore
```

Maven example using the same principles:

```yaml
- name: Set up JDK
  uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven

- name: Record Maven runtime
  run: |
    java --version
    javac --version
    ./mvnw --version

- name: Show discovered Maven JDK toolchains
  run: ./mvnw toolchains:display-discovered-jdk-toolchains

- name: Build
  run: ./mvnw --batch-mode --no-transfer-progress clean verify
```

`actions/setup-java` can install the JDK distribution/version, set `JAVA_HOME`, update `PATH`, cache Maven/Gradle dependencies, and generate Maven Toolchains entries. If the project requires a specific vendor, configure the vendor in both the action and the toolchain requirement to match.

For critical releases, you can use an OS/JDK matrix. Record the actual runner OS/architecture and container image digest if the build runs in a container. Runner labels like `ubuntu-latest` can point to images that are updated over time; provenance must record the image version/digest for accurate investigation.

If your supply-chain policy requires stronger controls, pin GitHub Actions by verified commit SHA, verify the Wrapper JAR, verify the Gradle distribution checksum, and use JDK archives with verified checksums/signatures.

## 10. Reproducible Builds and Toolchain Reports

Recording the toolchain helps reproduce the environment, but the record alone does not make a build reproducible. To recreate an artifact byte-for-byte, you also need to control:

- Source revision and working tree status.
- Build tool, JDK, compiler, plugin, and dependency versions.
- OS/architecture, locale, timezone, and line endings.
- Timestamps and file order inside archives.
- Generated metadata so it does not depend on username, absolute paths, or current time.
- Repositories/mirrors and dependency checksums.

With Gradle, combine the Wrapper, toolchains, dependency locking, and dependency verification. With Maven, combine the Wrapper, Enforcer, Maven Toolchains, plugin/dependency version pinning, and `project.build.outputTimestamp` for plugins that support reproducible archives.

Maven example:

```xml
<properties>
  <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Build twice in equivalent environments and compare the SHA-256 hashes. If the hashes differ, check timestamps, manifests, generated files, tool versions, the resolved dependency graph, and OS newlines. The Maven reproducible-build guide also notes that builds on Windows and Unix can differ due to CRLF/LF if content is not normalized.

The toolchain manifest is evidence about the environment; lockfiles and verification metadata control dependencies; reproducible-build checks confirm the artifact can be recreated. All three parts support each other, but solve different problems.

## 11. Example Build Provenance Report

A concise report might look like this:

```text
build.tool=Gradle 9.2.1
build.jvm=Azul Zulu 24.0.2
compiler.toolchain=Amazon Corretto 17.0.15
test.launcher=Amazon Corretto 17.0.15
java.release=17
os=Windows 11
architecture=amd64
source.revision=<commit-sha>
build.command=./gradlew clean toolchainReport toolchainProbe check
dependency.lock=gradle.lockfile
dependency.verification=gradle/verification-metadata.xml
```

The commit, command, and metadata path values must be generated from the actual build. Do not copy an old report and edit versions by hand. If the report is uploaded to CI, keep it alongside the artifacts, test reports, and checksums so investigators can correlate the exact build.

For Maven, the report should separately record `mvnw --version` and the toolchain selection log, because the Maven runtime and compiler JDK may differ.

## 12. Common Anti-Patterns

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Only writing `Java 17` in README | Unknown vendor, patch version, compiler, or runtime used | Record the full build JVM, compiler/test toolchain, and release target |
| Only using `--release 17` | May compile with different JDKs | Configure a separate toolchain |
| Running global `gradle build` or `mvn package` | Build tool version depends on the machine | Commit and use the Wrapper |
| Relying on the IDE JDK | Local and CI may select different JDKs | Set the toolchain in build files and CI |
| Not recording the Gradle daemon JVM | Unknown which JVM executes build logic | Run `gradlew --version` and check daemon criteria |
| Assuming `mvn -version` shows the compiler JDK | Misses Maven Toolchains selecting a different JDK | Record toolchain selection from Maven logs/plugin |
| Not pinning plugin versions | Build changes when plugin metadata changes | Declare versions explicitly |
| Using dynamic dependency versions in releases | Dependency graph changes over time | Gradle lockfile or Maven dependencyManagement/BOM |
| Saving only `BUILD SUCCESS` logs | Insufficient data to reproduce | Save toolchain report, commit SHA, and dependency state |
| Dumping all environment variables | May expose secrets/tokens | Record only a safe allowlist and redact sensitive values |
| Committing personal machine absolute JDK paths | Other machines do not have the same path | Use toolchain requirements and local mapping |
| Using `latest` in CI | Same workflow, but runner installs a different version | Pin distribution/version or image digest |

## 13. Troubleshooting Toolchain Mismatches

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `Unsupported class file major version` | Build tool/plugin does not support the JDK running the build, or input bytecode is too new | Check Gradle/Maven runtime and plugin versions |
| Compiler reports missing API | Incorrect compiler JDK or `--release` | Check compiler toolchain and release target |
| Passes locally, fails in CI | CI installs a different JDK/build tool or uses a different OS | Compare provenance reports, runner image, and command |
| Gradle uses a JDK different from `JAVA_HOME` | Daemon JVM criteria, IDE, or toolchain selects another runtime | Run `./gradlew --version`, `javaToolchains`, check IDE |
| Maven uses a JDK different from terminal | Maven Wrapper/`JAVA_HOME` or Maven Toolchains | Run `./mvnw --version`, check `toolchains:toolchain` log |
| Toolchain not found | Matching JDK not installed, or version/vendor mismatch | Run `javaToolchains` or `toolchains:display-discovered-jdk-toolchains` |
| Dependencies change despite unchanged source | Dynamic versions, SNAPSHOTs, or missing lockfile | Check Gradle lockfile or Maven dependency tree |
| JAR hash differs between two builds | Timestamps, OS newlines, generated metadata, or different plugins | Compare reports and inspect archive entries |
| Build works locally but differs in IDE | IDE Gradle JVM/Maven runner JDK differs from terminal | Check IDE build delegation and JDK settings |

When encountering an error, compare the two provenance reports first. Change only one layer at a time: build tool, build JVM, compiler toolchain, dependencies, or OS. After a successful build, save the new report alongside the artifact so future investigations have evidence.

## 14. Checklist for Setting Up a Java Project Toolchain

1. Choose the JDK baseline and runtime support matrix.
2. Decide whether vendor/patch version needs to be fixed or only the Java major version.
3. Commit the Gradle/Maven Wrapper and pin the distribution version.
4. Verify the distribution/Wrapper checksum according to security policy.
5. Configure Gradle Java toolchains or Maven Toolchains.
6. Set `options.release` or `maven.compiler.release` explicitly.
7. Record the build JVM, compiler JDK, and test/runtime JDK separately.
8. Pin plugin versions and dependency versions.
9. Enable Gradle dependency locking/verification where appropriate.
10. Use Maven Enforcer to check Maven/JDK runtime requirements.
11. Configure CI to install the exact JDK distribution/version and use the Wrapper.
12. Generate a toolchain report containing commit, build command, versions, OS, and architecture.
13. Upload the report alongside test reports and build artifacts.
14. Verify reproducibility with repeated builds and checksum comparisons.
15. Review the report to ensure it contains no credentials, tokens, or sensitive data.

## 15. Takeaways

- A toolchain includes the build tool, build JVM, compiler JDK, test/runtime JDK, plugins, dependencies, and OS/CI environment.
- `--release 17` specifies the API/language/bytecode target; it does not select the compiler JDK.
- Gradle client, daemon, compiler, and test launcher can run on different JVMs.
- Maven `-version` reports the JVM running Maven; Maven Toolchains can select a different JDK for compiler/Surefire/Javadoc.
- The Wrapper pins the Gradle/Maven distribution; Enforcer checks Maven/JDK requirements; toolchains select the actual JDK.
- Pin plugin/dependency versions and save lock state to prevent the dependency graph from changing silently.
- Gradle dependency verification checks artifact checksums/signatures; only trust reviewed metadata.
- CI should record OS/architecture, JDK distribution/version, build tool, commit SHA, command, and toolchain report.
- Never write secrets or the entire environment into a build report.
- Reproducible builds require controlling the toolchain, dependencies, timestamps, file order, and generated metadata.

When the toolchain is declared, verified, and recorded with every build, the team can explain why two environments produce different results, recreate release artifacts, and upgrade tools in a controlled manner.

## References

- [Gradle: Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle: Daemon JVM Toolchains and criteria](https://docs.gradle.org/current/userguide/gradle_daemon.html)
- [Gradle: Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle: Securing the Build Tool and distribution checksum](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Gradle: Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle: Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Maven: Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Maven: Toolchains Plugin Usage](https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html)
- [Maven: JDK Toolchain configuration](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk.html)
- [Maven: Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Maven Compiler Plugin: Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/)
- [Maven: Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [GitHub Actions: actions/setup-java](https://github.com/actions/setup-java)
