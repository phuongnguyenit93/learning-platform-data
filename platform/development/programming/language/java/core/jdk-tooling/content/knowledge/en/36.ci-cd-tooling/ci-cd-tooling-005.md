# Compiling Java in CI: consistent builds from commit to artifact

**Compiling in CI (Continuous Integration)** is the step of automatically compiling Java source code on a runner or build agent after each push, pull request, or manually triggered pipeline run. CI checks out the exact commit, prepares the JDK and build tool, restores dependencies, compiles the source, runs checks, packages the output, and stores logs/artifacts for the team to review.

The goal is to catch compile errors, wrong JDK versions, missing dependencies, incompatible annotation processors, and differences between developer machines and the build environment early. A good pipeline can be re-run from a known commit and produce results that are explainable, verifiable, and reproducible.

This lesson uses Maven, Gradle, and GitHub Actions as examples. The same principles apply to Jenkins, GitLab CI, Azure Pipelines, Buildkite, or internal runners.

## 1. Where does CI compilation fit in the development workflow?

A typical CI cycle:

1. A developer pushes a commit or opens a pull request.
2. CI checks out the exact commit and sets up the build environment.
3. It installs/selects the JDK and build tool specified by the project.
4. It restores dependencies from the repository/cache.
5. It compiles the main source and test source.
6. It runs unit tests, static analysis, and quality checks.
7. It packages the JAR/WAR or other artifacts.
8. It stores artifacts, test reports, and logs.
9. It reports the pass/fail status back to the pull request or commit.

Compiling is one part of the build. A successful **javac** run does not prove the application is ready: tests may fail, resources may be missing, modules may not be packaged, or integration tests may reveal runtime errors.

Typically, CI should run a lifecycle/task broad enough to compile, test, and verify. Only run compile alone when the purpose is genuinely a fast compilation check.

## 2. How do compile, test, package, and verify differ?

| Task | Question answered | Example |
|---|---|---|
| Compile | Does the source compile with the selected JDK/API? | `mvn compile`, `./gradlew compileJava` |
| Test compile | Does the test source compile? | `mvn test-compile`, `./gradlew compileTestJava` |
| Test | Do unit tests run and pass? | `mvn test`, `./gradlew test` |
| Package | Can a JAR/WAR be created? | `mvn package`, `./gradlew jar` |
| Verify/check | Do the checks attached to the lifecycle pass? | `mvn verify`, `./gradlew check` |
| Build | Produces the project's main outputs according to the build tool | `./gradlew build` |

With Maven, `compile` runs the preceding phases up to the compile phase. `test` also compiles the test source and runs the test runner. `package` packages the output; `verify` runs all preceding phases and any checks bound to the verify phase.

With the Gradle Java Plugin, `compileJava` compiles the main source, `compileTestJava` compiles tests, `test` runs tests, `check` aggregates verification tasks, and `build` depends on both `check` and `assemble`.

A CI job typically uses `mvn verify` or `gradle build`. A standalone compile command is suitable for a compile-only job or a fast feedback step, but does not replace quality checks before merging.

## 3. Distinguishing the JDK running the build from the target Java version

There are three concepts to keep separate:

- **JDK running Maven/Gradle:** the JVM used to launch the build tool and plugins.
- **JDK compiler/toolchain:** the javac that actually compiles the source.
- **Target Java release:** the language version, bytecode, and public Java APIs that the application is allowed to use.

For example: CI can run Maven with JDK 21, use JDK 21 as the compiler toolchain, and generate bytecode for Java 17. In that case, the compiler uses `--release 17`.

`--release 17` controls Java syntax, the class-file target, and the Java SE APIs available in Java 17. Using only `-source 17 -target 17` does not provide the same level of API checking; code can still accidentally call newer APIs if the compiler JDK has them.

Do not infer the target version solely from `java -version`. Check the build configuration and the actual compiler being used.

## 4. Choosing a stable JDK for CI

The chosen JDK must match:

- The Java version supported by the application.
- The Maven/Gradle and plugin versions.
- Annotation processors, compiler plugins, and test frameworks.
- The runner's operating system and architecture.
- The team's support policy.

For example, a project targeting Java 17 can run its main CI on JDK 17. If you want to test compatibility on newer runtimes, add a matrix for JDK 21 and 25. Keep `--release 17` so the compiler does not use newer APIs in the source.

Do not use the `latest` alias for release builds that need to be reproducible. Pin the Java major version, vendor/distribution, and when stricter control is required, pin the specific JDK build or image digest as well.

You can print the environment at the start of the job:

~~~bash
java -version
javac -version
mvn -version
./gradlew --version
~~~

`mvn -version` and `gradle --version` show which JVM the build tool is using. If the version differs from what is expected, check `JAVA_HOME`, PATH, the runner image, and the toolchain configuration.

## 5. Using the Maven Wrapper or Gradle Wrapper

A wrapper stores the build tool version configuration in the repository so developers and CI run the same Maven/Gradle version without depending on whatever version is pre-installed on the runner.

The Maven Wrapper typically consists of:

~~~text
.mvn/
  wrapper/
    maven-wrapper.properties
mvnw
mvnw.cmd
~~~

Running on Linux/macOS:

~~~bash
./mvnw --version
./mvnw --batch-mode --no-transfer-progress clean verify
~~~

On Windows:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd --batch-mode --no-transfer-progress clean verify
~~~

`maven-wrapper.properties` should specify the distribution URL. For integrity-sensitive builds, also configure the official `distributionSha256Sum` checksum from the Maven release page. Commit the wrapper scripts, wrapper JAR, and properties according to the Maven Wrapper guidelines.

The Gradle Wrapper includes `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, and `gradle/wrapper/gradle-wrapper.properties`.

~~~bash
./gradlew --version
./gradlew --no-daemon clean build
~~~

Pin `distributionUrl` to a specific Gradle version and set `distributionSha256Sum` according to the release checksum. Commit all wrapper files. Do not let CI pick an arbitrary Gradle version from the runner.

A wrapper makes the build tool more consistent, but it does not automatically pin the JDK, dependencies, or plugins. Those parts still need to be configured separately.

## 6. Configuring the Maven Compiler Plugin

In Maven, `maven-compiler-plugin` invokes javac to compile main and test sources. Explicitly declare the release, encoding, and plugin version in the POM:

~~~xml
<properties>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  <maven.compiler.release>17</maven.compiler.release>
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
~~~

`release` is the key setting to avoid accidentally compiling against APIs from a higher JDK. Pin the plugin version so results do not depend on the default plugin version chosen by Maven.

If the project has multiple modules, place the compiler plugin and Java release in the parent POM or `pluginManagement` so all modules share the same configuration. Check the effective POM if a module inherits a different configuration than expected.

## 7. Maven lifecycle in CI

Common commands:

~~~bash
# Compile only the main source
./mvnw --batch-mode compile

# Compile test source as well
./mvnw --batch-mode test-compile

# Compile and run unit tests
./mvnw --batch-mode test

# Create the artifact after running tests
./mvnw --batch-mode package

# Run the full lifecycle through verify
./mvnw --batch-mode clean verify
~~~

`clean` deletes old build outputs so the run starts from a clean state. `verify` runs the preceding phases, including compile, test compile, test, and package, along with any verification goals configured in the project.

Two commonly confused test-skipping options:

- `-DskipTests`: skips test execution, but the test source is still compiled.
- `-Dmaven.test.skip=true`: skips both test compilation and test execution.

Do not use skip options in a CI merge gate if the goal is to verify quality. Only use them when there is a dedicated job and a clear reason.

`--batch-mode` disables interactive prompts, making it suitable for runners. `--no-transfer-progress` reduces lengthy download logs. `--errors` displays Maven error stack traces when needed.

## 8. Configuring JavaCompile in Gradle

The Gradle Java Plugin creates compile tasks per source set. With Kotlin DSL, configure the Java release and encoding:

~~~kotlin
plugins {
    java
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}
~~~

The toolchain selects the appropriate compiler JDK; `options.release` restricts the target API and bytecode. If toolchain 17 is configured, the runner must have JDK 17 or Gradle must be configured with a reliable resolver to download the toolchain.

Main tasks:

~~~bash
./gradlew compileJava
./gradlew compileTestJava
./gradlew test
./gradlew check
./gradlew jar
./gradlew clean build
~~~

With Groovy DSL, the equivalent configuration is:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Do not mix multiple Java version configuration sources without understanding their precedence. Inspect the toolchain and compiler tasks when building on machines with multiple JDKs.

## 9. Maven Toolchains when the compiler JDK differs from the JDK running Maven

There are cases where Maven needs to run on a newer JDK to satisfy plugin requirements, while the project must compile with a different JDK. Maven Toolchains allows plugins to select a toolchain declared in `toolchains.xml`.

A toolchain configuration can declare JDK 17:

~~~xml
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>/opt/jdk-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

On CI, the actual path depends on the runner. Do not commit absolute paths from a developer machine into the repository. Use environment variables, JDK installation paths, or toolchain configurations generated by a setup action.

`maven.compiler.release` still needs to be configured to specify the target API and bytecode. The toolchain selects the compiler JDK; `release` defines the Java compatibility contract of the output.

## 10. Complete Maven project example

Structure:

~~~text
ci-compile-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/CiCompileDemo.java
    └── test/java/com/example/CiCompileDemoTest.java
~~~

File `src/main/java/com/example/CiCompileDemo.java`:

~~~java
package com.example;

public final class CiCompileDemo {
    private CiCompileDemo() {}

    public static String status() {
        return "CI_COMPILE_OK version=17";
    }

    public static void main(String[] args) {
        System.out.println(status());
    }
}
~~~

File `src/test/java/com/example/CiCompileDemoTest.java`:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CiCompileDemoTest {
    @Test
    void returnsExpectedBuildStatus() {
        assertEquals("CI_COMPILE_OK version=17", CiCompileDemo.status());
    }
}
~~~

Complete POM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>ci-compile-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.12.2</version>
      <scope>test</scope>
    </dependency>
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
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>com.example.CiCompileDemo</mainClass>
            </manifest>
          </archive>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Compile, test, and package:

~~~bash
./mvnw --batch-mode --no-transfer-progress clean verify
java -jar target/ci-compile-demo-1.0.0.jar
~~~

JAR stdout:

~~~text
CI_COMPILE_OK version=17
~~~

JUnit reports are placed in `target/surefire-reports/`. The JAR is created in `target/`. In CI, both the JAR and reports can be uploaded so reviewers can download or inspect them when a job fails.

## 11. GitHub Actions workflow for Maven

Create `.github/workflows/java-ci.yml`:

~~~yaml
name: Java CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Check Java and Maven
        run: |
          java -version
          ./mvnw --version

      - name: Compile, test and verify
        run: ./mvnw --batch-mode --no-transfer-progress --errors clean verify

      - name: Upload JAR and test reports
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: java-build-${{ github.run_id }}
          path: |
            target/*.jar
            target/surefire-reports/**
          if-no-files-found: warn
          retention-days: 7
~~~

Key points:

- `checkout` fetches the exact source commit of the event.
- `setup-java` installs the JDK and sets `JAVA_HOME`.
- `cache: maven` caches downloaded dependencies and the wrapper distribution.
- `./mvnw` ensures CI uses the Maven version pinned by the project.
- `clean verify` runs compile, test, and lifecycle verification.
- `if: always()` ensures test reports/logs are uploaded even if the build step fails; if no JAR exists yet, the upload action may warn that files were not found.
- `permissions: contents: read` restricts token permissions to what is needed for checkout.

`actions/setup-java` can cache Maven dependencies based on files like `pom.xml` and wrapper properties. For monorepos, use `cache-dependency-path` to specify the POMs/wrappers that should be included in the cache key.

## 12. GitHub Actions workflow for Gradle

If the project uses the Gradle Wrapper, you can use `gradle/actions/setup-gradle` to configure the Gradle User Home cache and verify the wrapper:

~~~yaml
name: Gradle CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v6

      - name: Check toolchain
        run: |
          java -version
          ./gradlew --version

      - name: Build and test
        run: ./gradlew --no-daemon clean build

      - name: Upload JAR and test reports
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: gradle-build-${{ github.run_id }}
          path: |
            build/libs/*.jar
            build/reports/tests/test/**
          if-no-files-found: warn
          retention-days: 7
~~~

Minimal Gradle Kotlin DSL configuration for Java 17:

~~~kotlin
plugins {
    application
}

group = "com.example"
version = "1.0.0"

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}

application {
    mainClass = "com.example.CiCompileDemo"
}
~~~

`gradle/actions/setup-gradle@v6` manages the Gradle User Home cache and validates the Gradle Wrapper. Another simpler option is `actions/setup-java` with `cache: gradle`. Choose one primary caching strategy and avoid configuring two overlapping mechanisms without a specific reason.

## 13. Matrix builds across multiple JDKs

A matrix lets you run the same build across multiple JDK versions or operating systems. For example, a project targeting Java 17 that supports running on Java 17, 21, and 25:

~~~yaml
jobs:
  test-jdk-matrix:
    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21', '25']
    runs-on: ubuntu-latest
    name: Test on Java ${{ matrix.java }}
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven

      - run: ./mvnw --batch-mode --no-transfer-progress clean verify
~~~

Keep `maven.compiler.release` at 17 in the POM. Each matrix job uses a different JDK to test runtime and compiler behavior. If you only want to compile with a fixed compiler but test on multiple runtimes, configure Maven Toolchains or a Gradle toolchain for compilation, then choose a separate Java launcher for tests.

A matrix increases runner time and cost. Choose versions that represent the actual support range rather than adding every JDK just because it is available.

You can extend the matrix to `ubuntu-latest`, `windows-latest`, and `macos-latest` when the project has platform-dependent code, cross-OS scripts, or native libraries.

## 14. Caching dependencies and build outputs

Caching reduces dependency download times between CI runs. It must not be a prerequisite for a correct build.

What to cache:

- Maven local repository (`~/.m2/repository`).
- Gradle dependency cache and wrapper distribution.
- Tool dependencies resolved via lock/configuration files.

Do not cache `target/` or `build/` as a default dependency cache. Build outputs may contain stale classes, generated sources, environment-dependent files, or invalid incremental state. Use Gradle's dedicated build cache only when you understand its keys, task inputs/outputs, and trust boundaries.

Cache keys should change when dependencies or build configurations change. By default, the Maven setup action hashes POMs and Maven wrapper metadata; the Gradle cache relies on build scripts, wrapper properties, and relevant version catalogs.

If a cache miss occurs, CI must still be able to download dependencies and build. Periodically run clean builds to detect if the pipeline is inadvertently relying on stale outputs.

## 15. Pinning dependencies, plugins, and build tools

A build can change even if the source code does not if a dependency or plugin version is swapped out.

Best practices:

- Pin versions for Maven plugins and direct dependencies.
- Use a BOM or dependency management to align versions across multiple modules.
- Avoid version ranges and SNAPSHOT dependencies in release builds.
- With Gradle, use version catalogs and dependency locking when the project needs to lock the graph.
- Enable dependency verification/checksum verification as supported by the build tool.
- Pin the Maven/Gradle Wrapper version.
- Manage the JDK distribution/version explicitly.
- Review lockfile, POM, and wrapper property changes in pull requests.

Do not rely on uncontrolled default plugin versions. Maven plugins can change behavior when Maven core or a parent POM is upgraded; declaring versions explicitly makes those changes visible to reviewers.

## 16. Reproducible builds and verifiable artifacts

A **reproducible build** means that given the same source, dependencies, build instructions, and defined environment, the build produces bit-for-bit identical artifacts.

Factors that cause artifacts to differ:

- Different JDK vendor or major version.
- Changed plugin or dependency versions.
- Timestamps in JAR manifests/resources.
- Locale, timezone, line endings, or environment variables.
- Generated sources containing timestamps, paths, or build machine information.
- Dependencies fetched from repositories whose contents changed or were not verified.

Maven supports `project.build.outputTimestamp` and plugins that support reproducible archives. Gradle also provides archive timestamp/order settings to produce deterministic outputs.

Example in a POM:

~~~xml
<properties>
  <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

To compare two builds, rebuild from a clean workspace and compare the artifact's SHA-256 hash. To prove reproducibility, build independently in a different environment and compare hashes; running twice on the same runner does not prove all sources of variance have been eliminated.

## 17. Compile warnings and static analysis in CI

Compiler warnings typically report deprecated APIs, unchecked conversions, raw types, serialization issues, or potentially buggy code.

You can enable lint:

~~~bash
javac --release 17 -Xlint:all -encoding UTF-8 -d out src/main/java/com/example/*.java
~~~

With Maven, pass compiler arguments through `maven-compiler-plugin`. With Gradle, configure `options.compilerArgs`.

Only enable `-Werror` after the codebase has stably addressed warnings. When adding a new JDK, the compiler may introduce new warnings; if CI turns every warning into an error immediately, a JDK upgrade can cause widespread build failures.

Static analysis tools such as Checkstyle, SpotBugs, PMD, Error Prone, or Sonar can run as separate verification tasks. Attach their results to `verify` or `check` so pull requests have a clear status.

## 18. Annotation processors and generated sources

Some libraries generate source code or bytecode during compilation, such as annotation processors, code generators, MapStruct, AutoValue, or Lombok.

CI must ensure:

- Processor dependencies have pinned versions.
- Processors run on a supported JDK.
- The processor path is explicitly declared if required by the build tool.
- Generated sources are properly included in the compile task.
- The build does not depend on leftover generated files from a previous build.
- Processors do not read secrets or write unexpected content outside the workspace.

If a local build passes but CI reports that a generated class cannot be found, inspect the annotation processing logs, processor path configuration, and task order. Do not fix the issue by committing generated outputs if the project does not manage generated sources that way.

## 19. Multi-module projects and monorepos

For Maven multi-module projects, run from the root POM:

~~~bash
./mvnw --batch-mode --no-transfer-progress clean verify
~~~

To build a single module along with its required dependency modules:

~~~bash
./mvnw -pl service-api -am verify
~~~

`-pl` selects the project; `-am` adds the modules needed to build the selected module.

With Gradle, you can run tasks by project path:

~~~bash
./gradlew :service-api:build
~~~

In a monorepo, cache keys should include the POMs/build files/wrapper properties that affect the module's dependencies. Artifact names should include the module and matrix dimensions so they do not overwrite outputs from other jobs.

Set the working directory explicitly if the workflow runs in a subdirectory. Do not assume the repository root is the directory containing `pom.xml` or `settings.gradle.kts`.

## 20. Storing artifacts, test reports, and logs

After a successful build, artifacts can be stored for QA, staging, or release pipelines to reuse. With Maven this is usually `target/*.jar`; with Gradle, `build/libs/*.jar`.

What to store alongside artifacts:

- Surefire/Failsafe XML and HTML reports.
- Gradle test reports.
- Compiler/static-analysis reports.
- Build logs on failure.
- Commit SHA, JDK version, Maven/Gradle version, and build metadata.

Do not upload `~/.m2`, the entire `~/.gradle` directory, credentials, `.env` files, signing keys, or directories containing secrets. Artifacts should have an appropriate retention period; a CI artifact is not necessarily an approved release artifact.

If a release pipeline reuses an artifact from CI, verify the artifact ID/hash and source commit. Do not rebuild with a different configuration during the deploy step and assume the output matches the tested artifact.

## 21. Securing the compile workflow

Build scripts, Maven plugins, Gradle plugins, and annotation processors can all execute code on the runner. Treat builds from pull requests as untrusted code.

Basic practices:

- Use `permissions: contents: read` for jobs that only checkout and build.
- Do not pass deploy tokens, signing keys, or cloud credentials to pull requests from forks.
- Do not use `pull_request_target` to check out and execute untrusted source with repository permissions.
- Do not print secrets into logs or include secrets in artifacts.
- Only grant publish permissions in a separate release job, after the CI gate succeeds.
- Keep runners clean, especially self-hosted runners; prefer ephemeral runners for untrusted workloads.
- Pin actions by commit SHA if supply-chain policy requires immutability; major tags are convenient for upgrades but can point to newer releases.
- Use checksum/signature verification for the JDK, wrapper, and dependencies when supported by the platform.

A compile job should only have the minimum required permissions. Do not run deployment or publishing from the same pull request job simply because compilation passed.

## 22. Diagnosing compile failures in CI

| Error | Common cause | How to check |
|---|---|---|
| `invalid source release` | Compiler JDK does not support the configured release. | `java -version`, toolchain, and compiler log. |
| `Unsupported class file major version` | Build plugin or runtime is reading bytecode newer than it supports. | Check the JDK running the build tool and plugin versions. |
| `package ... does not exist` | Missing dependency, wrong scope, or cache/repository error. | `mvn dependency:tree`, Gradle dependency insight. |
| `cannot find symbol` | Incomplete source/generated source/module/classpath. | Check source sets, processors, and module path. |
| Test compile passes but tests fail | Different runtime behavior, environment, or test data. | Inspect Surefire/Gradle test reports and environment. |
| Wrapper does not run on Linux | Script lacks executable bit or wrapper files are missing. | Check `mvnw`/`gradlew` permissions and wrapper files. |
| `toolchain not found` | Runner lacks a matching JDK or resolver is not configured. | Check toolchain installation and auto-download repository. |
| Build passes locally but fails in CI | Different JDK, OS, encoding, case sensitivity, environment, or dependencies. | Print tool versions and run a clean build in an equivalent container. |
| Cache hit but wrong build | Cache key does not cover inputs or build relies on stale outputs. | Clean the workspace and disable cache to compare. |

Maven diagnostics:

~~~bash
./mvnw --version
./mvnw --errors --debug -DskipTests compile
./mvnw help:effective-pom
./mvnw dependency:tree
~~~

Gradle diagnostics:

~~~bash
./gradlew --version
./gradlew compileJava --info --stacktrace
./gradlew dependencies
./gradlew dependencyInsight --dependency junit --configuration testRuntimeClasspath
~~~

Only enable `--debug` when needed because logs can be very long and some plugins may print sensitive information. Before sharing logs externally, inspect and redact tokens, internal URLs with credentials, or confidential data.

## 23. Verifying bytecode and output JARs

After compiling, check the class file version:

~~~bash
javap -verbose -classpath target/classes com.example.CiCompileDemo
~~~

Java 17 has class-file major version 61. Some common milestones:

| Java | Class-file major version |
|---|---:|
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

Inspect JAR contents:

~~~bash
jar tf target/ci-compile-demo-1.0.0.jar
~~~

Run the JAR:

~~~bash
java -jar target/ci-compile-demo-1.0.0.jar
~~~

These steps confirm that the bytecode and artifact have the expected structure. They do not replace tests or runtime checks on the JDKs supported by the project.

## 24. Compile pipelines in GitLab CI and Jenkins

Build tool commands do not depend on GitHub Actions. GitLab CI can run the Maven Wrapper in an image with a pinned JDK/Maven:

~~~yaml
stages:
  - verify

compile_and_test:
  stage: verify
  image: maven:3.9.12-eclipse-temurin-17
  script:
    - java -version
    - ./mvnw --batch-mode --no-transfer-progress clean verify
  artifacts:
    when: always
    paths:
      - target/*.jar
      - target/surefire-reports/
    expire_in: 7 days
~~~

If the project uses a wrapper, the image still needs a suitable JDK; the Maven pre-installed in the image does not have to match the Maven version used because the wrapper will select the pinned distribution.

In a Jenkins Pipeline, the same command can run in a stage:

~~~groovy
pipeline {
    agent any
    stages {
        stage('Compile and verify') {
            steps {
                sh './mvnw --batch-mode --no-transfer-progress clean verify'
            }
        }
    }
    post {
        always {
            junit 'target/surefire-reports/*.xml'
            archiveArtifacts artifacts: 'target/*.jar', allowEmptyArchive: true
        }
    }
}
~~~

On a Windows agent, use `bat '.\\mvnw.cmd --batch-mode --no-transfer-progress clean verify'` instead of `sh`. Configure tool installations or container images so JDK and build tool versions stay consistent.

## 25. Checklist for implementing CI compilation on a new project

1. Choose the Java version supported by the project and determine the JDK running the build.
2. Choose Maven or Gradle; generate and commit the wrapper.
3. Declare the compiler release, encoding, and plugin versions.
4. Add minimal unit tests to verify critical behavior.
5. Run the wrapper locally with a clean build.
6. Create a CI workflow for push and pull request events.
7. Use a pinned JDK distribution/version and cache dependencies by build files.
8. Run `verify` or `build`, without skipping tests in the merge gate.
9. Store JARs, test reports, and logs with appropriate retention.
10. Test building from a clean runner and verify the artifact/class-file version.
11. Add a JDK/OS matrix when needed to verify the support range.
12. Separate publish/deploy permissions from pull request build jobs.

A reliable compile job must answer three questions: which commit was built, which compiler/JDK generated the bytecode, and which artifact corresponds to the test results. When that information is recorded alongside a pinned wrapper, dependencies, and workflow, the team can reproduce compile errors and trace changes without depending on a single developer's machine.

## References

- GitHub Docs — [Building and testing Java with Maven](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-maven).
- GitHub Docs — [Building and testing Java with Gradle](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-gradle).
- GitHub — [actions/setup-java](https://github.com/actions/setup-java).
- GitHub — [actions/checkout](https://github.com/actions/checkout).
- GitHub — [actions/upload-artifact](https://github.com/actions/upload-artifact).
- Gradle — [Gradle on GitHub Actions](https://docs.gradle.org/current/userguide/github-actions.html).
- Gradle — [Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html).
- Apache Maven — [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/).
- Apache Maven — [Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html).
- Apache Maven — [Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html).
- Apache Maven — [Maven in Five Minutes: Build Lifecycle](https://maven.apache.org/guides/getting-started/maven-in-five-minutes).
