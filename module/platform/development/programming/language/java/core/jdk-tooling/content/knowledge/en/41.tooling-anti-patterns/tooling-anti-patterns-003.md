# Calling tools without pinning versions

Calling a tool without pinning its version means running a development or build tool without explicitly specifying the version to use. Common examples include invoking Maven or Gradle directly from a personal machine's PATH, using `latest` in a tool download command, using a Maven plugin without declaring its version, or referencing a GitHub Action by a mutable tag.

This configuration allows the same commit to produce different results at two different points in time. A developer's machine may have a newer Maven/Gradle/JDK than CI; a new runner may receive a different action or container image; a newly released plugin may change build behavior even though the source code has not changed. Pinning versions helps you know exactly which tools participated in producing an artifact, reproduce failures, and evaluate updates before introducing them into a release.

## 1. Distinguishing the types of versions to pin

A Java project involves multiple tools participating in the build. Pinning only the JDK is not enough if Maven, Gradle, plugins, actions, or images can still change automatically.

| Component | Example | Common pinning location |
|---|---|---|
| JDK/JRE | Temurin 21.0.7+6 | JDK toolchain, image digest, or provisioning script |
| Build tool | Maven 3.9.9, Gradle 9.9.0 | Maven Wrapper, Gradle Wrapper |
| Maven plugin | Compiler Plugin 3.13.0 | POM pluginManagement |
| Gradle plugin | Spring Boot Plugin 3.5.0 | plugins block or version catalog |
| Dependency | org.slf4j:slf4j-api:2.0.17 | Fixed version, BOM, lockfile |
| CI action | actions/checkout | Full commit SHA |
| Container image | Eclipse Temurin JDK image | Specific tag with digest |
| Auxiliary CLI | formatter, scanner, code generator | Version in command or tool manifest |

There are three levels of control to distinguish:

1. **Release version:** identifies the release, for example Gradle 9.9.0.
2. **Content identity:** identifies the exact content downloaded, for example the SHA-256 of a ZIP, the digest of a container image, or the commit SHA of a GitHub Action.
3. **Dependency graph:** identifies the exact libraries and plugins resolved by the build, including transitive dependencies.

Version pinning prevents automatic drift to a new release. Checksums/digests detect content that differs from the approved release. Lockfiles and dependency verification control which libraries are pulled into the build. These mechanisms complement one another.

## 2. Why calling tools without pinning versions is an anti-pattern

### 2.1. Builds change even when source code does not

Suppose a workflow runs:

~~~sh
mvn clean verify
~~~

Today a developer's machine has Maven 3.9.x and JDK 21; next week a new runner has a different Maven or a new default JDK. If the POM also does not pin plugins, Maven may resolve a different plugin version when repository metadata changes.

The result can be:

- A green build turning red after a plugin release.
- New warnings becoming errors or the compiler changing how it handles code.
- Different artifacts between local machines, CI, and the release environment.
- Difficulty reproducing failures because logs only record the build command, not the full tool versions.
- A compromised or buggy tool release running immediately in the pipeline.

### 2.2. Tags or aliases can change their target

All of the examples below allow versions to change over time:

~~~sh
docker run eclipse-temurin:latest java -version
npx --yes prettier@latest --check .
curl -fsSL https://example.com/install-latest.sh | sh
~~~

A Docker tag can be updated by the publisher to point to a new image. `latest` is an alias, not an immutable identifier. A script downloaded from a `latest` URL can change its content without the URL changing. A CLI using `@latest` will receive the newest release at runtime.

When a new tool version is needed, update the version in a reviewed change, run tests, and record evidence of the chosen release.

### 2.3. Software supply chain risks

Build tools and plugins often execute code in an environment with access to source code, tokens, or CI secrets. A modified plugin or action can execute code inside the pipeline.

Version pinning limits unintended changes. Pinning a commit SHA or digest also identifies specific content. However, pinning an outdated version also retains known vulnerabilities; therefore, a regular security update process is required.

## 3. Pinning the JDK and compiler toolchain

Do not rely solely on the default JDK on PATH. Project or CI configuration must specify the Java version, vendor, and when needed, the patch/build as well.

### 3.1. Distinguishing Java release from JDK patch version

The following configurations do not provide the same level of guarantee:

| Configuration | Meaning |
|---|---|
| java-version: '21' | Selects the Java 21 line; patch/build may vary by resolver |
| languageVersion = JavaLanguageVersion.of(21) | Gradle selects a matching Java 21 toolchain |
| java-version: '21.0.7+6' | Requests a specific JDK build if the distribution and resolver support that version |
| JDK image with digest | Locks the image content, including the JDK and packaged components |

Java feature release 21 specifies the target language/API level. It does not by itself specify the JDK patch build, vendor, or the contents of the entire build environment.

### 3.2. Gradle Java Toolchains

Use a toolchain so the build does not depend on whatever JDK happens to be selected via PATH:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Gradle uses the matching toolchain for compile, test, and Javadoc tasks. You can inspect the JDKs Gradle detects:

~~~sh
./gradlew -q javaToolchains
./gradlew --version
~~~

**Important limitation:** `languageVersion` selects the major version, such as Java 21; `vendor` filters the provider. This configuration does not lock a specific patch like 21.0.7 or build number. If a release requires the exact same JDK patch across all runners, provision that exact JDK using a digest-pinned image or a managed installation, expose only the chosen installation to the toolchain, and verify `java.version`, `java.vendor`, and `java.home` in CI.

Example of checking the actual runtime:

~~~sh
java -version
javac -version
./gradlew --version
~~~

### 3.3. Maven Toolchains

Maven can select a JDK based on toolchain information in `~/.m2/toolchains.xml`. For example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>21.0.7</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/temurin-21.0.7</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

A project or the Maven Toolchains Plugin can request the corresponding toolchain. Maven matches `version` and `vendor` values as metadata strings; it does not automatically verify whether the `jdkHome` directory actually contains the declared JDK. Therefore, only use JDK paths provided by a trusted provisioning system and re-verify with `java -version`/`javac -version`.

Maven Toolchains allows version ranges, but if the goal is to pin a specific patch, use a specific version string and verify the installation contents.

### 3.4. `--release` does not pin the JDK

Maven example:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Or `javac`:

~~~sh
javac --release 17 Example.java
~~~

`--release 17` restricts the language features, bytecode, and Java platform APIs that source code is allowed to use. It does not fix the JDK compiler patch/vendor being executed. A separate JDK toolchain is still required to control the compiler.

## 4. Using Maven Wrapper to pin Maven

Do not require every developer to install Maven manually and run `mvn`. Different machines may have different versions. Maven Wrapper (`mvnw` and `mvnw.cmd`) downloads and runs the exact Maven distribution declared in the repository.

Create or update the Wrapper using the Maven Wrapper Plugin:

~~~sh
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

Then commit the Wrapper files and instruct everyone to run:

~~~sh
./mvnw --version
./mvnw clean verify
~~~

On Windows:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean verify
~~~

The `.mvn/wrapper/maven-wrapper.properties` file can declare:

~~~properties
distributionUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=<SHA-256 of Maven 3.9.9 from the official release source>
wrapperSha256Sum=<verified SHA-256 of maven-wrapper.jar>
~~~

The two checksum values above are placeholders for real values, not literal strings. Obtain the SHA-256 from the official release page or a trusted independent source. Do not compute the checksum from a file you just downloaded and use that same value as proof of trust.

`distributionUrl` pins the Maven version; `distributionSha256Sum` verifies the Maven ZIP; `wrapperSha256Sum` verifies the Wrapper JAR. Use a Wrapper distribution that supports these checksum properties.

## 5. Pinning Maven plugins in the POM

Maven plugins are part of the build toolchain. If versions are not declared, Maven may have to resolve versions from repository metadata. Apache Maven recommends always specifying a version for every plugin so builds are reproducible.

Use `pluginManagement` to manage versions centrally:

~~~xml
<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
      </plugin>
    </plugins>
  </pluginManagement>
</build>
~~~

The versions in this example are illustrative fixed versions. When applying them to a project, check compatibility with your Maven/JDK and update deliberately.

When invoking a plugin directly from the command line, use its full coordinates with the version:

~~~sh
./mvnw org.codehaus.mojo:versions-maven-plugin:2.18.0:display-dependency-updates
~~~

Short commands like `mvn versions:display-dependency-updates` rely on plugin prefix resolution and may need to look up metadata to find the plugin. Full coordinates with a version explicitly specify which plugin to run.

## 6. Pinning Gradle with Gradle Wrapper

Do not run `gradle build` from a global installation. Use `./gradlew` or `gradlew.bat` so the project automatically selects the right Gradle distribution.

Create or update the Wrapper:

~~~sh
gradle wrapper --gradle-version 9.9.0 --distribution-type bin
~~~

Then run:

~~~sh
./gradlew --version
./gradlew clean build
~~~

The `gradle/wrapper/gradle-wrapper.properties` file should contain a specific URL:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
distributionSha256Sum=<official SHA-256 of gradle-9.9.0-bin.zip>
~~~

Replace the placeholder with the checksum from Gradle's official release checksums page. The Wrapper will reject the distribution if the SHA-256 does not match. Use HTTPS and a direct distribution URL; avoid redirect URLs or floating aliases.

Commit all Wrapper files to version control:

- gradlew
- gradlew.bat
- gradle/wrapper/gradle-wrapper.jar
- gradle/wrapper/gradle-wrapper.properties

The Wrapper JAR also needs to be verified according to Gradle's security guidelines. Pinning the distribution URL does not automatically verify a committed Wrapper JAR.

## 7. Pinning Gradle plugins and dependencies

### 7.1. Declaring explicit versions in the plugins block

Example `build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
}
~~~

Do not use dynamic versions such as `latest.release`, `1.+`, or broad ranges for plugins in release builds.

For larger projects, versions can be managed centrally in `gradle/libs.versions.toml`:

~~~toml
[versions]
spring-boot = "3.5.0"
junit = "5.12.2"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
~~~

Then reference the version catalog in the build script. The version catalog file must be committed alongside the source code.

### 7.2. Avoiding dynamic dependency versions

Example to avoid for releases:

~~~kotlin
dependencies {
    implementation("org.springframework:spring-web:5.+")
    testImplementation("org.junit.jupiter:junit-jupiter:5.+")
}
~~~

Dynamic versions can resolve to a different release on the next build. Declare fixed versions:

~~~kotlin
dependencies {
    implementation("org.springframework:spring-web:6.2.8")
    testImplementation("org.junit.jupiter:junit-jupiter:5.12.2")
}
~~~

Example versions must be checked for compatibility with the project before applying.

### 7.3. Enabling dependency locking

Fixed versions in a build file do not completely lock transitive dependencies. Gradle dependency locking records the resolved versions so subsequent builds use the same dependency graph.

In `build.gradle.kts`:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Generate or update the lock state after resolving the required configurations:

~~~sh
./gradlew dependencies --write-locks
~~~

Commit the `gradle.lockfile` files. When intentionally upgrading dependencies, update the lock state together with the version change and review the diff.

Do not use dependency locking as a way to freeze `SNAPSHOT` or changing modules; their contents can change even when the version string does not.

### 7.4. Verifying dependency checksums and signatures

Gradle supports dependency verification via `gradle/verification-metadata.xml`. You can initialize metadata for checksums and signatures:

~~~sh
./gradlew --write-verification-metadata sha256,pgp
~~~

Review the generated file, cross-check checksums/signatures against trusted sources, and then commit it. Do not blindly trust all newly generated metadata: the generation command only records currently resolved artifacts, while the development team must still verify the origin and contents of critical artifacts.

Checksums confirm that file contents have not changed compared to the approved value. Signatures help verify the publisher's identity. The two mechanisms serve different roles and complement each other.

## 8. Pinning GitHub Actions by full commit SHA

In workflows, tags like `@v4` are convenient, but a tag can be moved to a different commit. GitHub recommends pinning actions to a full-length commit SHA to use an immutable revision.

Syntax example:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<FULL_40_CHARACTER_COMMIT_SHA>

      - uses: actions/setup-java@<FULL_40_CHARACTER_COMMIT_SHA>
        with:
          distribution: temurin
          java-version: '21.0.7+6'

      - name: Verify toolchain
        run: |
          java -version
          javac -version

      - name: Build
        run: ./mvnw --batch-mode verify
~~~

`<FULL_40_CHARACTER_COMMIT_SHA>` is a placeholder to be replaced with the full commit SHA from the action's official repository. Verify that the SHA belongs to the upstream repository, not an untrusted fork. You can add a comment with a human-readable version/tag:

~~~yaml
# actions/checkout v4.x.y, pinned to reviewed commit
- uses: actions/checkout@<FULL_40_CHARACTER_COMMIT_SHA>
~~~

If an organization does not yet pin SHAs, at a minimum it should use actions from trusted publishers and review the source before granting access to secrets. A full SHA is a clearer way to keep workflows stable and changes auditable.

## 9. Pinning container images by digest

Docker tags are mutable labels. For example, `eclipse-temurin:21-jdk` may be updated to a newer JDK patch in the future. If you need repeatable builds with the same image, pin the digest:

~~~dockerfile
FROM eclipse-temurin:21-jdk@sha256:<64_HEX_IMAGE_DIGEST>

WORKDIR /app
COPY . .
RUN ./mvnw --batch-mode verify
~~~

`<64_HEX_IMAGE_DIGEST>` is a placeholder. Obtain the digest from a trusted registry and confirm it corresponds to the expected image/tag.

A digest fixes the image content. For multi-architecture images, a digest may identify a manifest index containing multiple platform manifests; the runner still selects the child image for its architecture. If exact results per architecture are needed, specify `--platform` or configure the platform in CI and record the digest used.

Pinning a digest keeps builds stable, but it does not automatically receive security updates. Periodically update digests via pull requests with testing and vulnerability review.

## 10. Pinning CLIs and tool installation scripts

Auxiliary tools can also drift in version:

| Unpinned invocation | Pinned invocation |
|---|---|
| npx prettier@latest --check . | npx --yes prettier@3.5.3 --check . |
| docker run maven:latest mvn -version | Maven image with specific tag and digest |
| Downloading install-latest.sh script | Downloading a specific release, verifying checksum/signature |
| mvn versions:set without pinning plugin | Invoking plugin with groupId, artifactId, and version |
| gradle build from PATH | ./gradlew build |
| mvn verify from PATH | ./mvnw verify |

If using `npm`/`npx` in a Java build step, commit the npm lockfile and use a chosen Node/npm version. For Python tools, use a requirements/lock file and a specific Python version. The principle is the same: every tool that can affect artifacts must be declared and version-controlled.

Avoid commands that download and execute scripts from the Internet without checking their content. If an organization needs automated tool installation, use a verified internal repository or release artifacts with checksums/signatures.

## 11. Does version pinning produce a completely reproducible build?

No. Version pinning is an important prerequisite, but a build can still differ if other inputs change.

Additional factors to control:

- Direct dependencies and transitive dependencies.
- Plugins, extensions, annotation processors, and code generators.
- JDK vendor, patch, architecture, and compiler.
- Maven/Gradle Wrapper distribution and Wrapper JAR.
- Base image, package manager, and OS image.
- Locale, timezone, environment variables, and working directory.
- Build timestamps written into JARs, archives, or generated files.
- Repository mirrors and downloaded artifact contents.

Maven provides a guide for configuring reproducible builds, where `project.build.outputTimestamp` normalizes timestamps in artifacts when supported by plugins. This shows that pinning tool versions alone is not enough to produce byte-for-byte identical binaries.

Record build provenance: source commit, JDK version/vendor, Maven/Gradle version, plugin/dependency versions, container digest, and CI run. When an incident occurs, this information helps trace the exact toolchain that produced the artifact.

## 12. Controlled version upgrade process

Pinning versions does not mean keeping them frozen forever. Old tools can reach end of life or have vulnerabilities. Create a dedicated upgrade change so it is clear why the build changed.

1. Select the tool to upgrade and determine the target version from official release notes.
2. Check compatibility across the JDK, Maven/Gradle, plugins, and dependencies.
3. Update the Wrapper, toolchain, plugin, or image digest in the proper management location.
4. Update the corresponding checksums, lockfiles, and verification metadata.
5. Run unit tests, integration tests, packaging, and security scans.
6. Compare artifacts/logs before and after the upgrade if the build requires reproducibility.
7. Review diffs of lockfiles, checksums, and workflow action SHAs.
8. Document the reason for the upgrade, old/new versions, and test results.
9. Merge the change after CI checks pass.
10. Maintain a schedule to check releases and security advisories so critical patches are not missed.

You can use Dependabot or Renovate to open update pull requests. Bots help detect new releases; the development team must still review compatibility, changelogs, checksums/digests, and test results before accepting.

## 13. Checking tool versions in the pipeline

Print versions at the start of the build so logs contain sufficient diagnostic data:

~~~sh
java -version
javac -version
./mvnw --version
./gradlew --version
~~~

If a workflow only uses Maven, there is no need to run Gradle commands and vice versa. On Windows:

~~~powershell
java -version
javac -version
.\mvnw.cmd --version
.\gradlew.bat --version
~~~

You can check the executable locations being resolved:

~~~sh
command -v java
command -v javac
command -v mvn
command -v gradle
~~~

PowerShell:

~~~powershell
Get-Command -All java
Get-Command -All javac
Get-Command -All mvn
Get-Command -All gradle
~~~

If the build runs in Docker, record the image digest. If it runs on GitHub Actions, keep the action SHA in the workflow. Do not log only "Java 21" if the release needs to know the specific patch, vendor, or architecture.

## 14. Java example to inspect the actual runtime

Create `ToolchainProbe.java` to print the runtime version, vendor, VM, and architecture:

~~~java
public class ToolchainProbe {
    public static void main(String[] args) {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.vm.name=" + System.getProperty("java.vm.name"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("java.home=" + System.getProperty("java.home"));
    }
}
~~~

Compile with JDK 17 or later:

~~~sh
javac --release 17 ToolchainProbe.java
java ToolchainProbe
~~~

This program confirms the running runtime. It does not by itself prove that Maven, Gradle, or CI actions are pinned; compare its output with the Wrapper/toolchain/image configuration and pipeline logs.

## 15. Troubleshooting unpinned tool versions

| Symptom | Common cause | Resolution |
|---|---|---|
| Local and CI builds produce different results | Different JDK or build tool on PATH | Use Wrapper, declare toolchain, and print versions |
| Build worked yesterday, fails today | Plugin, action, image tag, or dynamic dependency changed | Pin version/digest/SHA and review changes |
| Gradle selects a Java 21 with a different patch than expected | `languageVersion` only selects the major version | Provision a fixed JDK patch and verify the runtime |
| Maven uses a compiler different from the default JDK | Maven toolchain or `JAVA_HOME` differs from terminal | Check `mvnw --version`, `toolchains.xml`, and JDK path |
| Maven plugin changes between two builds | Plugin does not declare a version | Declare the version in `pluginManagement` |
| Gradle Wrapper downloads an unexpected file | Floating URL or missing checksum | Pin distribution URL and `distributionSha256Sum` |
| Wrapper runs but checksum mismatch occurs | ZIP/JAR differs from approved content or checksum is wrong | Stop the build, verify source and checksum independently |
| GitHub Action changes even though tag stays the same | Tags can be moved | Pin full commit SHA from the official repository |
| Docker image changes after rebuild | Image tag is mutable | Pin digest and update digest via PR |
| Lockfile reports version conflict | Dependency declaration changed but lock state was not updated | Review dependency change and run `--write-locks` |
| Dependency verification fails | New artifact does not have an approved checksum/signature yet | Verify the artifact and update verification metadata |
| Artifact differs byte-for-byte despite pinned tools | Different timestamp, environment, or other inputs | Check reproducible build settings and provenance |

## 16. Checklist against calling tools without pinning versions

- [ ] Selected the required JDK vendor, feature release, and patch/build.
- [ ] Used Gradle/Maven toolchains instead of relying solely on PATH.
- [ ] Understood that `--release` only locks target API/bytecode, not the compiler JDK.
- [ ] Committed Maven Wrapper or Gradle Wrapper.
- [ ] Pinned the exact Maven/Gradle distribution version.
- [ ] Verified checksums for the Wrapper JAR and distribution when supported.
- [ ] Declared versions for all Maven build plugins.
- [ ] Pinned Gradle plugins and managed versions centrally.
- [ ] Avoided `latest`, `1.+`, version ranges, and `SNAPSHOT` in release builds.
- [ ] Enabled dependency locking and committed lockfiles if using Gradle.
- [ ] Verified checksums/signatures of critical dependencies.
- [ ] Pinned GitHub Actions by full commit SHA.
- [ ] Pinned container images by digest.
- [ ] Pinned versions for auxiliary CLIs/tool installation scripts.
- [ ] Logged tool versions in CI logs.
- [ ] Established a review and testing process for version upgrades.
- [ ] Recorded sufficient provenance to reproduce artifacts.

Calling tools without pinning versions makes the build environment depend on state outside the repository at runtime. Use Wrappers for Maven/Gradle, declare JDK toolchains, pin plugins/actions/images, lock the dependency graph, and verify checksums or signatures. Update versions through reviewed and tested changes so builds remain both stable and patched against security vulnerabilities.

## References

- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/)
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [GitHub — Secure Use Reference for GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use)
- [Docker — Building Best Practices: Pin Base Image Versions](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions)