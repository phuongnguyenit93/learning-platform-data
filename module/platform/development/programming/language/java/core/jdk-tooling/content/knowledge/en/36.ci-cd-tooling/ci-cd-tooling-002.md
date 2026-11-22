# Choosing CI Versions for a Java Project

Choosing versions for CI/CD means deciding which versions of Java, build tools, runner images, and pipeline components will be used to build, test, and package the application. If you only pick a single Java version number and let everything else update automatically, the same commit may build differently between a developer's machine, CI, and production.

For a Java project, five version layers should be separated:

1. **JDK running the CI job and build tool:** the JVM on which Gradle or Maven is running.
2. **Java toolchain:** the JDK compiler and Java launcher used to compile, test, or run tasks.
3. **Java release target:** the lowest Java version with which the application's bytecode and APIs must be compatible.
4. **Build tool and plugins:** Gradle/Maven Wrapper, plugins, compiler plugins, and dependencies.
5. **CI environment:** runner/agent, operating system image, container image, and CI actions/plugins.

These layers are related, but they do not have to be the same version. For example, CI can run Gradle on JDK 25, compile using a JDK 25 toolchain, yet use `--release 17` to ensure the artifact still runs on Java 17. Then, the pipeline can run tests on JDK 17, 21, and 25 to verify compatibility across multiple runtimes.

## 1. Start from the Java Version the Application Must Support

Before choosing a JDK for CI, determine the lowest runtime that the product commits to supporting. This is a product compatibility decision, not a runner decision.

For example:

- Application only runs on Java 17 or newer: target release is 17.
- Application has migrated to Java 21 and uses Java 21 APIs/features: target release is 21.
- Application requires Java 25: target release is 25.
- Library must serve many older applications: target the lowest runtime on which library users are still supported.

Choosing an LTS version is usually suitable for production systems that need a stable lifecycle. As of November 2026, Oracle lists Java 17, 21, and 25 as LTS releases; actual support schedules and terms still depend on the JDK vendor and support contract used by the organization.

| Version | Reference Role |
|---|---|
| Java 17 | Common baseline for systems needing long-term compatibility with Java 17 applications |
| Java 21 | Next LTS, suitable once the project has confirmed framework and dependency support |
| Java 25 | Newer LTS at the time of writing, suitable for evaluating upgrades and serving as a new target runtime |

Do not raise the target just because the CI runner already has a newer JDK. Check the framework, application server, database driver, monitoring agent, native libraries, container base image, and production environment before changing the minimum runtime.

## 2. Distinguish the JDK Running Gradle/Maven from the Compile/Test JDK

This is a common source of confusion.

**JDK running the build tool**

This is the Java installation that the Gradle or Maven process uses to start. It is constrained by the requirements of the Gradle/Maven version and plugins.

**JDK toolchain**

This is the JDK used by compile/test/JavaExec tasks. Gradle Java Toolchains allow selecting the compiler and launcher by version, vendor, or implementation. The toolchain can differ from the JVM running Gradle.

**Java release target**

This is the language level, JDK API, and bytecode that the compiler is allowed to use/produce. It determines which runtimes the application can run on, within the limits of its bundled dependencies.

Example:

| Layer | Value |
|---|---|
| JVM running Gradle in CI | JDK 25 |
| Java toolchain used for compile/test | JDK 25 |
| Java release target | 17 |
| Minimum production runtime | Java 17 |
| CI test matrix | 17, 21, 25 |

In this example, Gradle runs on Java 25, but the code is compiled targeting Java 17. The pipeline also runs tests on multiple JDKs to catch runtime compatibility issues.

Do not assume `JAVA_HOME` determines everything. `JAVA_HOME` typically selects the default JVM for Gradle/Maven, whereas a Java toolchain can select a different JDK for the compiler or test launcher.

## 3. Check Build Tool Compatibility Before Choosing a JDK

A new JDK may be released before the version of Gradle, Maven, or plugins that the project uses supports it. Check both directions:

- Can the build tool run on the JDK provided by CI?
- Do the build tool and plugins support compiling and testing with the target JDK?

For example, with Gradle 9.9.0, the current compatibility matrix requires Java 17 or higher to run Gradle. Java 25 is supported for running Gradle from Gradle 9.1.0 onward. Therefore, a project using Gradle 9.9.0 can choose JDK 17, 21, or 25 as the JVM running the build, provided plugins and remaining components are also compatible.

Quick check table for Gradle 9.9.0:

| JDK | Can run Gradle 9.9.0? | Compile/test toolchain |
|---|---|---|
| 17 | Yes | Yes |
| 21 | Yes | Yes |
| 25 | Yes | Yes |
| 26 | Yes, since Gradle 9.4.0 | Yes, since Gradle 9.4.0 |
| 27 | Yes, since Gradle 9.8.0 | Yes, since Gradle 9.8.0 |

This table reflects Gradle's compatibility, not a guarantee that every plugin, annotation processor, or library in your project supports all those versions. Also check the compatibility documentation of the plugins and frameworks in use.

For Maven, check the Maven Wrapper version, the JDK running Maven, and the Maven Compiler Plugin/toolchains configuration. Do not assume an older Maven version will support every new JDK just because `javac` can compile the source.

## 4. Use Gradle Wrapper to Pin the Build Tool

Do not let CI invoke an arbitrary pre-installed Gradle on the runner. Commit the Gradle Wrapper to the repository and run builds via `./gradlew` or `gradlew.bat`.

The `gradle/wrapper/gradle-wrapper.properties` file can specify an exact distribution:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
```

This ensures developers and CI use the same Gradle distribution. When you need to protect the integrity of the distribution, add `distributionSha256Sum` with the official checksum matching the exact ZIP file chosen.

Principles:

- Commit `gradlew`, `gradlew.bat`, the `gradle/wrapper` directory, and `gradle-wrapper.properties`.
- Do not use a globally installed Gradle as the primary version source.
- Do not use URLs pointing to `current`, `latest`, or nightly in production builds.
- Upgrade the Gradle Wrapper via a separate pull request, read the release notes, and run full verification.
- Check Gradle's compatibility with the build JDK and plugins before merging.

If using Maven, apply the same principle with the Maven Wrapper (`mvnw`, `mvnw.cmd`, and `.mvn/wrapper/maven-wrapper.properties`). Run `./mvnw` instead of relying on a pre-installed `mvn` on the runner.

## 5. Use Java Toolchains and --release to Pin Compiler and Runtime

With the Gradle Java Plugin, configure the toolchain at the project level:

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
}
```

The two settings have different meanings:

- `languageVersion = 17` tells Gradle to select JDK 17 for Java tasks that use toolchains.
- `options.release = 17` tells the compiler to restrict language features, JDK APIs, and bytecode to Java 17.

If CI runs Gradle on JDK 25 while the toolchain is 17, Gradle needs to locate or provision JDK 17 for compile/test. This is useful when you want to keep a newer build runtime while still compiling with the baseline's compiler.

Another approach is to run each matrix job on the exact JDK and pass the version into the Gradle build. The hands-on section below illustrates this approach.

Do not rely solely on `sourceCompatibility` and `targetCompatibility` as a substitute for `--release` when API compatibility must be guaranteed. Those older properties mainly configure the compiler's source/target; they do not provide the same level of API checking as `--release`.

## 6. Choose a JDK Distribution and Vendor

Besides the version, CI also needs a JDK distribution. Common options include:

- Eclipse Temurin.
- Amazon Corretto.
- Azul Zulu.
- Oracle JDK.
- Microsoft Build of OpenJDK.
- Red Hat Build of OpenJDK.
- GraalVM when Native Image or GraalVM-specific features are needed.

Choose based on operational criteria:

| Criterion | Question to Answer |
|---|---|
| Support lifecycle | Until when does the vendor provide security updates and support? |
| License | Are the terms of use suitable for CI, staging, and production? |
| Patch cadence | How are CPU/PSU updates released and applied? |
| Architecture | Are packages available for x64, ARM64, or the required runner architecture? |
| Platform | Are builds available for Linux, Windows, macOS, and container base images? |
| Compatibility | Are frameworks, native libraries, crypto providers, and monitoring agents compatible? |
| Distribution consistency | Does CI need to use the same vendor/build as production? |

If production uses a specific JDK vendor for support or crypto provider reasons, test CI on that same distribution in at least one critical job. If the product supports multiple vendors, you can add cross-vendor test jobs.

Do not mix vendors within the same matrix if the goal is only to test Java language versions. Every matrix dimension increases job count and cost. Only add a vendor matrix when there is a real compatibility requirement.

## 7. Choose an Appropriate Java Matrix

A matrix lets you run the same test suite across multiple Java versions. You do not have to run every version that exists.

A common strategy for applications supporting Java 17 and newer:

- Pull request: run on Java 17 (baseline) and Java 25 (newer LTS).
- Nightly or pre-release: run Java 17, 21, and 25.
- Release candidate: additionally run the exact runtime/vendor/OS used by production.
- When raising the target from 17 to 21: update the baseline matrix according to the migration plan, after checking frameworks and dependencies.

Example matrix:

| Job | JDK | Goal |
|---|---:|---|
| Compatibility baseline | 17 | Confirm the application still runs on the lowest runtime |
| Intermediate LTS | 21 | Detect differences between LTS releases |
| Current LTS | 25 | Catch runtime upgrade issues early |

If a project only supports Java 21, there is no need to test Java 17 just because it is an LTS release. The matrix should reflect the product's actual support contract.

A matrix can also combine OS or architecture:

- Linux x64 for fast day-to-day builds.
- Windows if the application or scripts depend on Windows.
- macOS if you need to test macOS behavior or build artifacts for that platform.
- ARM64 if production or users run on ARM64.

Do not multiply every matrix dimension mechanically. Choose combinations that carry real risk or have actual users.

## 8. Do Not Confuse Major Versions with Patch Versions

Declaring `java-version: '25'` typically selects a JDK from the Java 25 line according to the setup tool's rules and cache. It does not necessarily pin a single patch release.

There are three common pinning levels:

| Pinning Approach | Example | Characteristics |
|---|---|---|
| Major line | `25` | Easily receives new patch updates in the 25 line; suitable for controlled automatic patch updates |
| Full feature/update version | `25.0.x` or the full vendor-released version | Tighter control over a specific patch |
| Immutable artifact | Container image digest or JDK archive checksum | Identifies the exact artifact downloaded/executed |

Choose the pinning level based on requirements:

- Regular CI can follow the major line and update patches periodically.
- Release builds or tightly controlled environments can pin a specific patch or verified JDK archive.
- Containerized runners can pin images by digest.
- Do not use `latest` for pipelines that need stable results; this alias can point to a new Java major version as soon as a vendor releases it.

Pinning a version does not mean staying on an old release forever. Have a process to apply security patches and test them before promoting the new version into the main pipeline.

## 9. Choose CI Runner, Image, and Action/Plugin Versions

The JDK is only one part of the CI environment.

### Runner image and operating system

With GitHub-hosted runners, choose an image with an explicit OS version such as `ubuntu-24.04` when you want to avoid the `ubuntu-latest` label automatically switching to a new OS major version. However, hosted images still receive package and tool updates over time; an OS label is not an immutable snapshot.

With GitLab CI or Docker runners, declare an image with an explicit tag. When a more immutable environment is needed, use an image digest and store the image in a trusted registry.

With Jenkins, check the Jenkins controller, agents, tool installations, and the JDK used by the job. A Jenkins job may run on agents with different OSes or architectures; tool names must be configured consistently across those agents.

### CI actions and plugins

Actions and plugins also have their own versions:

- GitHub Actions: versions of `actions/checkout`, `actions/setup-java`, and third-party actions.
- GitLab CI: versions of GitLab Runner, container images, and included CI components.
- Jenkins: Jenkins LTS version, plugins, and JDK tool definitions.

Do not let actions/plugins track the `main` branch or `latest` in production pipelines. Choose tested releases, monitor security advisories, and upgrade in a controlled manner.

For GitHub Actions, tags such as `@v6` are convenient for updates, but their target can change if the tag is moved. GitHub recommends pinning actions to a full-length commit SHA for an immutable reference; Dependabot or workflow lockfiles can be used to manage updates.

## 10. GitHub Actions Example: Testing Java 17, 21, and 25

The workflow below runs the same build across three JDKs. The example uses `actions/checkout@v7` and `actions/setup-java@v6` per the current releases at the time of writing. In repositories with strict supply-chain security requirements, replace tags with verified full commit SHAs from each action's official repository.

Create `.github/workflows/java-ci.yml`:

```yaml
name: Java CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    name: Verify on Java ${{ matrix.java }}
    runs-on: ubuntu-24.04
    strategy:
      fail-fast: false
      matrix:
        java: [17, 21, 25]

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up Java
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: "${{ matrix.java }}"
          cache: gradle

      - name: Show build environment
        run: |
          java --version
          javac --version
          ./gradlew --version
          ./gradlew -q javaToolchains

      - name: Verify
        run: ./gradlew --no-daemon -PciJavaVersion=${{ matrix.java }} clean check
```

Explanation:

- `matrix.java` creates three independent jobs.
- `setup-java` installs the corresponding JDK and configures `JAVA_HOME`/`PATH`.
- `cache: gradle` caches dependencies and the wrapper distribution to reduce download time.
- `javaToolchains` shows which JDKs Gradle detects.
- `-PciJavaVersion=...` passes the JDK under test into the Gradle build.
- `clean check` runs the build and verification from scratch.

Caching is only a performance optimization. Caching is not a JDK selection mechanism and does not replace pinning the Wrapper, toolchains, or dependencies.

## 11. GitLab CI Example: Pinning the JDK Container

With GitLab CI using the Docker executor, the job image determines the container environment that runs the script. Example:

```yaml
verify:
  image: eclipse-temurin:25-jdk-noble
  stage: test
  script:
    - java --version
    - javac --version
    - ./gradlew --no-daemon -PciJavaVersion=25 clean check
```

Image tags select a specific JDK line and base OS. For exact artifact control, you can use the form `image: registry.example.com/team/temurin:25-jdk-noble@sha256:...` with an actual digest obtained from a trusted registry. Do not copy a digest from another image or use a digest that no longer exists in the registry.

When a matrix is needed, create jobs for JDK 17, 21, and 25 or use `parallel:matrix` with an image built from a CI variable. Validate the configuration with CI Lint and confirm the runner supports the Docker executor and selected image.

## 12. Jenkins Pipeline Example: Selecting a Configured JDK Tool

Jenkins manages JDKs under Manage Jenkins > Tools. Administrators create tool names such as `temurin-17`, `temurin-21`, or `temurin-25`, pointing to an existing installation or configuring an installer.

The pipeline references the tool by name:

```groovy
pipeline {
    agent any

    tools {
        jdk 'temurin-25'
    }

    stages {
        stage('Verify') {
            steps {
                sh 'java --version'
                sh './gradlew --no-daemon clean check'
            }
        }
    }
}
```

The name `temurin-25` must match the JDK name configured in Jenkins. On Windows agents, use `bat` instead of `sh` if the agent does not have a POSIX shell.

If Linux and Windows agents have JDKs installed at different paths, configure Tool Locations per agent. Do not assume the same `JAVA_HOME` path exists on every node.

## 13. Configuring Gradle to Run a Matrix While Preserving Java 17 Compatibility

The following Kotlin DSL build script uses the version passed from CI to select the toolchain, while keeping `--release 17` so the artifact remains compatible with Java 17.

File `build.gradle.kts`:

```kotlin
plugins {
    application
}

val ciJavaVersion = providers.gradleProperty("ciJavaVersion")
    .map { it.toInt() }
    .getOrElse(17)

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(ciJavaVersion))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

application {
    mainClass.set("com.example.App")
}
```

File `src/main/java/com/example/App.java`:

```java
package com.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("ci-version-ok");
    }
}
```

Create a Gradle Wrapper pointing to Gradle 9.9.0, then run:

Linux/macOS:

```sh
./gradlew -PciJavaVersion=17 clean check
./gradlew -PciJavaVersion=21 clean check
./gradlew -PciJavaVersion=25 clean check
./gradlew -PciJavaVersion=25 run
```

Windows:

```powershell
.\gradlew.bat -PciJavaVersion=17 clean check
.\gradlew.bat -PciJavaVersion=21 clean check
.\gradlew.bat -PciJavaVersion=25 clean check
.\gradlew.bat -PciJavaVersion=25 run
```

Application stdout:

```text
ci-version-ok
```

The three `check` commands use the compiler/test toolchain matching the passed version. `options.release.set(17)` keeps source/API/bytecode compatibility at Java 17. The `run` command uses the application runtime launcher from the project's toolchain.

In CI, the required JDKs must be pre-installed or Gradle must be configured with toolchain provisioning. If no matching JDK is available, the build may fail with an error stating that no toolchain was found.

## 14. Maven Example: Separating the JDK Running Maven from the Release Target

If the project uses Maven, select the JDK running Maven in CI via `JAVA_HOME` or a CI setup step. Then configure the release target in `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Use the Maven Wrapper to pin the Maven distribution:

```sh
./mvnw --version
./mvnw --batch-mode clean verify
```

`maven.compiler.release` instructs the compiler to check language features, APIs, and bytecode against Java 17. If you want to compile with a JDK separate from the JVM running Maven, configure Maven Toolchains and declare the corresponding toolchain.

In a CI matrix, you can run Maven on each selected JDK and keep the same `maven.compiler.release` to verify the application is compatible across those runtimes.

## 15. Inspect Actual Versions in CI Logs

Do not trust YAML configuration alone. Print the actual versions at the start of the job:

```sh
java --version
javac --version
echo "$JAVA_HOME"
./gradlew --version
./gradlew -q javaToolchains
```

For Maven:

```sh
java --version
javac --version
echo "$JAVA_HOME"
./mvnw --version
```

These commands help detect:

- The runner is using a different JDK than expected.
- Gradle is running on a different JVM than the Java toolchain.
- Gradle does not detect the required toolchain.
- Maven is running from a different installation.
- The agent/container has a different architecture or vendor.

On Windows PowerShell, use `$env:JAVA_HOME` to print the environment variable.

When you need to know which compiler/launcher a specific task uses, run Gradle with `--info` or inspect toolchain metadata. Do not look only at `java --version` and conclude that the compiler and test launcher use the same JDK.

## 16. Pin Plugin and Dependency Versions

Even when the JDK and Wrapper are pinned, builds can still change if plugins or dependencies are declared with dynamic versions.

You should:

- Specify Gradle plugin versions explicitly in `plugins {}` or `pluginManagement`.
- Use version catalogs to manage versions consistently in multi-project builds.
- Use dependency locking when you need to pin the dependency graph.
- Enable dependency verification/checksum or signature verification per policy.
- Avoid version ranges or dynamic versions like `1.+` in release builds.
- Check plugin compatibility when upgrading Gradle or the JDK.

Example of an explicitly declared plugin version:

```kotlin
plugins {
    java
    id("com.example.quality") version "2.4.1"
}
```

This example illustrates declaring a pinned version. When using a real plugin, choose a version confirmed to be compatible with the project's Gradle Wrapper and JDK.

Avoid upgrading the JDK, Gradle, plugins, and frameworks all at once in one large change if it can be broken into steps. When a build fails, changing one layer at a time helps pinpoint the cause faster.

## 17. Caching Does Not Replace Version Pinning

CI caches can store:

- Downloaded JDKs.
- Gradle/Maven distributions.
- Downloaded dependencies.
- Build output caches.

Caching speeds up builds, but it is not a reliable source of version configuration. On a cache miss, the pipeline must still download the exact declared versions. On a cache hit, the pipeline must also verify version metadata and matching cache keys.

To avoid stale caches:

- Include `gradle-wrapper.properties`, build scripts, `gradle.properties`, and version catalogs in the cache key.
- Include `pom.xml`, Maven Wrapper properties, and Maven extension configurations in the cache key.
- Separate caches by OS, architecture, JDK major version, and build tool when those factors affect artifacts.
- Do not use caching to skip the JDK installation or version verification step.
- Use read-only caches for fan-out matrix jobs if multiple jobs writing to the same key cause conflicts.

If build outputs depend on the JDK vendor or patch version, ensure the cache/build cache properly recognizes toolchain inputs. Do not reuse outputs from one JDK for another environment when compatibility has not been confirmed.

## 18. CI Version Upgrade Roadmap

Upgrading a JDK or CI image should be a planned change:

1. Record the production JDK, current build JDK, Gradle/Maven Wrapper, plugins, and runner image.
2. Check the compatibility matrix of the build tool and frameworks.
3. Create an experimental branch or pull request that upgrades only the JDK.
4. Run compilation, unit tests, integration tests, static analysis, and packaging.
5. Run the matrix on both the baseline and the new JDK.
6. Compare warnings, test failures, performance, and artifact metadata.
7. Update the runner image/actions/plugins in a separate change if needed.
8. Test in staging with a runtime matching production.
9. Roll out environment by environment and monitor for errors.
10. Record the new versions in build/release documentation.

Maintain a regular schedule for checking JDK security updates. Do not keep an old JDK indefinitely just for build stability; instead, update in a controlled manner and record the exact versions in each release.

## 19. Common Errors When Choosing CI Versions

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Unsupported class file major version` | The JDK running the build or plugin cannot read the bytecode version in use | Check `java --version`, Gradle/Maven version, and plugin compatibility |
| Gradle fails to run on a new JDK | The Gradle Wrapper is too old to support that JVM | Check the Gradle compatibility matrix and upgrade the Wrapper |
| Compilation uses Java 17 even though CI installed Java 25 | Gradle toolchain is pinned to Java 17 | Check `java.toolchain` and the `javaToolchains` task |
| App runs on CI but fails on Java 17 production | Compilation did not restrict APIs/bytecode with `--release` | Set `options.release` or `maven.compiler.release` to the baseline |
| `JAVA_HOME` is right but the compiler is wrong | The build uses a toolchain different from the JVM running Gradle/Maven | Check the toolchain compiler and launcher |
| Local CI passes but hosted runner fails | OS image, architecture, JDK vendor, or native library differs | Pin the OS/image and test in the matching environment |
| Build changes even when the commit does not | Runner image, action, JDK patch, or dependency version drifted | Pin appropriate versions/digests and record tool metadata |
| JDK setup step reports unsupported version | Action/runner is too old or the distribution lacks a package for the platform | Upgrade the action/runner or choose an available package |
| Jenkins uses the wrong JDK | Tool name mismatch or agent has a different installation path | Check Manage Jenkins > Tools and Tool Locations |
| GitLab job cannot find `java` | Image does not include a JDK or job runs on an unexpected shell executor | Check `image`, executor, and `PATH` |
| Cache restore makes builds hard to reproduce | Cache key does not account for Wrapper/JDK/dependency inputs | Adjust the cache key; verify versions independently of the cache |
| Java 25 build fails while Java 17 passes | Plugin/framework does not yet support the new JDK or runtime behavior changed | Isolate the plugin/dependency, check release notes, and run targeted tests |

## 20. Runbook for Choosing Versions in a New Project

Follow this order when setting up CI for the first time:

1. Determine the minimum runtime supported by the product.
2. Choose an LTS JDK distribution and vendor aligned with production.
3. Choose a Gradle/Maven Wrapper compatible with the build JDK.
4. Configure the Java toolchain and `--release` according to product requirements.
5. Choose the runner OS, architecture, and container image.
6. Pin CI actions/plugins to tested releases; use SHAs or digests when immutable references are needed.
7. Set up a matrix covering the baseline and supported runtimes.
8. Run compilation, unit tests, integration tests, and packaging.
9. Print actual versions in the logs.
10. Set up dependency caching with keys reflecting version inputs.
11. Establish a process for updating JDK patches and CI tooling.
12. Document the chosen versions along with the rationale and review date.

## 21. Checklist

- [ ] Determined the minimum Java runtime supported by the application.
- [ ] Selected an appropriate LTS JDK and distribution/vendor.
- [ ] Distinguished the JVM running the CI build from the Java toolchain.
- [ ] Configured `--release`/`maven.compiler.release` according to the target runtime.
- [ ] Verified Gradle/Maven Wrapper compatibility with the JDK.
- [ ] Pinned Gradle/Maven Wrapper and plugin versions.
- [ ] Selected an appropriate runner OS/architecture and container image.
- [ ] Pinned action/plugin versions and considered SHA/digest pinning.
- [ ] Configured a matrix for the baseline and supported runtimes.
- [ ] Printed `java --version`, `javac --version`, and the build tool version in CI.
- [ ] Verified the toolchain compiler and test launcher.
- [ ] Checked dependency locking/verification and cache keys.
- [ ] Tested the build in a production-like environment.
- [ ] Established a schedule for security patch updates and CI version upgrades.
- [ ] Documented version decisions so team members can reproduce builds.

## 22. References

- Oracle Java Verified Portfolio Support Roadmap: https://www.oracle.com/java/technologies/jvp-support-roadmap.html
- Gradle 9.9.0 — Compatibility Matrix: https://docs.gradle.org/9.9.0/userguide/compatibility.html
- Gradle 9.9.0 — Toolchains for JVM Projects: https://docs.gradle.org/9.9.0/userguide/toolchains.html
- Gradle User Manual — Building Java & JVM Projects: https://docs.gradle.org/current/userguide/building_java_projects.html
- GitHub Actions — actions/setup-java: https://github.com/actions/setup-java
- GitHub Actions — Secure Use Reference: https://docs.github.com/en/actions/reference/security/secure-use
- GitLab CI/CD YAML — image keyword: https://docs.gitlab.com/ci/yaml/#image
- Jenkins — Managing Tools: https://www.jenkins.io/doc/book/managing/tools/

Good CI version selection starts from the runtime the product commits to supporting. Pin the build tool and runner environment, choose an appropriate JDK toolchain, set an explicit Java release target, and then use a matrix to test the supported runtimes. Pinning produces reproducible builds; a regular update process ensures the pipeline continues to receive security patches and new improvements.