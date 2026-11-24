# Designing a Checkout, JDK Setup, Verification, Packaging, and Artifact Storage Pipeline for Spring Boot CI

## 1. Goal: From Commit to Verified Artifact

Within the parent topic **CI Automation**, this lesson designs an automated pipeline for a Spring Boot application following the sequence **source checkout → JDK setup → verification → packaging → validation → artifact storage**. The goal is for every stored file to be traceable to a specific commit, build environment, test result, and checksum.

A build command that succeeds on a personal machine is not enough to establish a reliable release process. CI must be able to answer:

- Did the workflow check out the exact commit of the push or pull request?
- Which JDK and Maven/Gradle version does the runner use?
- Is the wrapper committed and using the exact pinned version?
- Which unit tests and integration tests actually ran?
- Which file is the executable Spring Boot JAR, and which is only a plain JAR?
- Does the artifact exist, have the right structure, and run in a smoke test?
- What is the file's SHA-256 checksum?
- Where is the artifact uploaded, under what name, for how long is it retained, and which exact file does the downstream job download?
- Are pull requests from forks kept read-only and prevented from accessing release secrets?

This lesson provides two alternative GitHub Actions workflows: **Maven** and **Gradle**. The examples use **Java 17, Spring Boot 3.3.5, Maven Wrapper 3.9.x, or Gradle Wrapper 8.5**. This is a fixed version set for the exercises; real projects must choose versions appropriate for their repository and update them on a maintenance schedule.

**GitHub Actions versions used in the examples:** `actions/checkout@v7`, `actions/setup-java@v6`, `actions/upload-artifact@v7`, `actions/download-artifact@v8`. Major tags let you receive patches within the same major version; high-security pipelines can pin to a verified full commit SHA.

## 2. Overall Pipeline

~~~text
Push / Pull Request / Manual trigger
              |
              v
       Checkout exact commit
              |
              v
       Setup JDK + dependency cache
              |
              v
    Verify Java + Maven/Gradle Wrapper
              |
              v
       Compile + tests + verification
              |
              v
   Package executable Spring Boot JAR
              |
              v
   Validate archive + runtime smoke test
              |
              v
      Compute SHA-256 + staging output
              |
              v
       Upload workflow artifact
              |
              v
     Download + verify in next job
              |
              v
          Approval / deploy
~~~

The steps are ordered because each step depends on the result of the preceding one. If tests fail, the job should not proceed to upload an executable artifact as if the build were accepted. Test reports can still be uploaded by a separate step running with `if: always()` to support investigation.

## 3. Distinguishing Four Types of Data in CI

| Data Type | Contents | Purpose | Lifecycle |
| --- | --- | --- | --- |
| **Dependency cache** | Maven local repository or Gradle dependency cache/wrapper distributions | Reduce dependency download and build time | Can be reused across workflow runs |
| **Build output** | Files in `target/` or `build/` | Local output of the build job | Usually deleted along with the runner |
| **Workflow artifact** | JAR, checksum, and reports uploaded from a workflow run | Download, share between jobs, review/test/deploy | Retained according to repository policy |
| **Release package** | JAR/WAR published to a Maven repository, GitHub Packages, or registry | Consumers download by version/GAV or image tag/digest | Governed by the registry's retention policy |

**Uploading a workflow artifact is not Maven deploy or Gradle publish.** Uploading only stores outputs tied to a workflow run. If another module needs to declare `com.example:catalog-core:1.0.0`, it requires a publication with POM/Gradle Module Metadata, a repository, and appropriate access permissions.

Do not upload the entire `~/.m2` or `~/.gradle` directory or the full workspace as a product artifact. Caches are acceleration inputs; the JAR is the output that needs distribution.

## 4. Preparing the Repository and Build Wrapper

Single-module project structure:

~~~text
catalog-app/
├── .github/
│   └── workflows/
│       ├── ci-maven.yml
│       └── ci-gradle.yml
├── .mvn/wrapper/
│   └── maven-wrapper.properties
├── gradle/wrapper/
│   └── gradle-wrapper.properties
├── mvnw
├── mvnw.cmd
├── gradlew
├── gradlew.bat
├── pom.xml
├── build.gradle
├── settings.gradle
└── src/
    ├── main/java/com/example/catalog/CatalogApplication.java
    └── test/java/com/example/catalog/CatalogApplicationTests.java
~~~

This is an illustrative tree listing both Maven and Gradle. A real repository normally uses only one build system. If the project lives in a subdirectory of a monorepo, the workflow must set `working-directory` and artifact paths to match that module.

### 4.1. Why Do We Need a Wrapper?

**Maven Wrapper** consists of `mvnw`, `mvnw.cmd`, and configuration in `.mvn/wrapper`. **Gradle Wrapper** consists of `gradlew`, `gradlew.bat`, and configuration in `gradle/wrapper`.

The wrapper ensures local developers and CI use the exact same declared build tool version. Do not rely on Maven/Gradle pre-installed on GitHub runners because runner images can be updated independently of the project.

Example of Gradle Wrapper pinning 8.5 in `gradle/wrapper/gradle-wrapper.properties`:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.5-bin.zip
~~~

Maven Wrapper keeps the Maven 3.9.x distribution URL in `.mvn/wrapper/maven-wrapper.properties`. Choose a Maven version tested with your plugins and project; do not download an arbitrary latest version on every workflow run.

### 4.2. Wrapper Execution Permissions on Linux

If the wrapper script loses its executable bit when committed, a Linux runner may report `Permission denied`. Check the Git mode and commit the execute permission:

~~~bash
git update-index --chmod=+x mvnw
git update-index --chmod=+x gradlew
git commit -m "Make build wrappers executable"
~~~

Run the command only for the wrapper your repository actually uses. On Windows, you can invoke `mvnw.cmd` or `gradlew.bat`.

### 4.3. Pinning the JDK Target in the Build

Maven with Spring Boot parent:

~~~xml
<properties>
    <java.version>17</java.version>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

The JDK installed on the runner and the project's Java toolchain are two related but distinct configuration layers. `setup-java` installs the JDK and sets `JAVA_HOME`; the Maven compiler or Gradle toolchain decides which compiler/target the project uses. Check every module in a monorepo to prevent one module from accidentally compiling for Java 21 while the application must run on Java 17.

## 5. Java 17 Example: Application and Test

### 5.1. Spring Boot Application

File **src/main/java/com/example/catalog/CatalogApplication.java**:

~~~java
package com.example.catalog;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner ciProof() {
        return args -> System.out.println("CI_PACKAGE_OK");
    }
}
~~~

This is a complete Java 17 class. The example uses the basic Spring Boot starter without opening an HTTP server. When the context starts successfully, the stdout line printed by the application is:

~~~text
CI_PACKAGE_OK
~~~

Spring Boot may still print a banner and logs. The line above is the deterministic business output, not the entire terminal output.

### 5.2. JUnit 5 Test Class

File **src/test/java/com/example/catalog/CatalogApplicationTests.java**:

~~~java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public class CatalogApplicationTests {

    @Test
    void contextLoads() {
    }
}
~~~

This is a complete test class for JUnit Jupiter and Spring Boot Test. The `public` modifier is declared explicitly per the module's QA convention. The test verifies that the application context initializes; real projects need additional unit and integration tests for business logic, persistence, APIs, security, and service dependencies.

## 6. Maven: Configuring an Executable Boot JAR

File **pom.xml** for a single-module project:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>catalog-app</artifactId>
    <version>1.0.0</version>
    <name>catalog-app</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

This POM uses the Spring Boot starter parent:

- The parent manages dependency versions and common plugin configurations.
- `java.version` sets the Java target per the parent configuration.
- `spring-boot-starter-test` is used only in test scope.
- The Spring Boot Maven Plugin builds an executable archive via the `repackage` goal.
- When using the starter parent, the `repackage` execution is pre-managed; declaring the plugin as above is sufficient for standard cases.

### 6.1. Building with Maven Lifecycle Verification

~~~bash
./mvnw -B -ntp clean verify
~~~

- `-B`: batch mode, suitable for CI.
- `-ntp`: disables transfer progress so logs remain readable.
- `clean`: deletes previous build outputs.
- `verify`: runs prior phases, including compile, test, package, and verify.
- Spring Boot's `repackage` goal runs during the `package` lifecycle according to the parent configuration.

Default artifact:

~~~text
target/catalog-app-1.0.0.jar
~~~

If you do not use the Spring Boot parent, you must explicitly configure the `repackage` execution. If you set a different classifier, `finalName`, or output directory, you must adjust the workflow path to match the actual artifact.

### 6.2. Manual Maven Verification

~~~bash
./mvnw -B -ntp clean verify
jar tf target/catalog-app-1.0.0.jar
java -jar target/catalog-app-1.0.0.jar --spring.main.banner-mode=off
~~~

The command-line application in Section 5 exits after `CommandLineRunner` finishes and prints `CI_PACKAGE_OK`. A real web service keeps running; in that case, check a health endpoint or readiness probe instead of waiting for the process to exit on its own.

A typical executable Boot JAR contains:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/catalog/CatalogApplication.class
BOOT-INF/lib/...
~~~

### 6.3. Maven Workflow for Multi-Module Projects

If the app sits inside a reactor:

~~~text
repository/
├── pom.xml
├── core/pom.xml
└── app/pom.xml
~~~

Build the app together with its dependent modules:

~~~bash
./mvnw -B -ntp -pl app -am clean verify
~~~

`-pl app` selects the `app` module; `-am` instructs Maven to build the required reactor modules, such as `core`. The artifact may reside at:

~~~text
app/target/app-1.0.0.jar
~~~

The workflow must use this path instead of `target/catalog-app-1.0.0.jar`. If the project has multiple POMs, the cache key should reflect the POMs of the relevant modules.

## 7. Complete GitHub Actions Workflow for Maven

Create **.github/workflows/ci-maven.yml**:

~~~yaml
name: Spring Boot CI - Maven

on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    name: Test and package with Maven
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK 17 and Maven cache
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: "17"
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            **/.mvn/wrapper/maven-wrapper.properties
            **/.mvn/extensions.xml

      - name: Verify Java and Maven
        run: |
          java -version
          ./mvnw --version

      - name: Run tests and package executable JAR
        run: ./mvnw -B -ntp clean verify

      - name: Verify executable Boot JAR
        run: |
          test -s target/catalog-app-1.0.0.jar
          jar tf target/catalog-app-1.0.0.jar > target/jar-entries.txt
          grep -q '^BOOT-INF/classes/com/example/catalog/CatalogApplication.class$' target/jar-entries.txt
          grep -q '^BOOT-INF/lib/' target/jar-entries.txt

      - name: Smoke test executable JAR
        run: |
          java -jar target/catalog-app-1.0.0.jar --spring.main.banner-mode=off > target/smoke.log
          grep -q '^CI_PACKAGE_OK$' target/smoke.log

      - name: Prepare artifact and SHA-256
        run: |
          mkdir -p dist
          cp target/catalog-app-1.0.0.jar dist/
          (
            cd dist
            sha256sum catalog-app-1.0.0.jar > catalog-app-1.0.0.jar.sha256
          )

      - name: Upload executable JAR
        uses: actions/upload-artifact@v7
        with:
          name: spring-boot-maven-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: dist/
          if-no-files-found: error
          retention-days: 14

      - name: Upload Maven test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: maven-test-reports-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/target/surefire-reports/
            **/target/failsafe-reports/
          if-no-files-found: ignore
          retention-days: 7
~~~

This workflow performs the following:

1. Runs on pushes to `main`, pull requests targeting `main`, release tags matching `v*`, or manual dispatch.
2. Checks out the commit associated with the current event.
3. Installs Temurin JDK 17 and caches Maven dependencies.
4. Prints the Java/Maven versions for traceability.
5. Runs `clean verify`; test failures stop the job before the JAR upload step.
6. Verifies that the file exists and has a Boot executable layout.
7. Smoke-tests the command-line JAR to prove it starts and executes code.
8. Creates a `dist/` staging directory, copies the exact artifact, and generates a checksum.
9. Uploads the JAR + checksum under a unique name, failing if no files are found.
10. Uploads Surefire/Failsafe reports even if an earlier step failed.

**Cache path:** `**/pom.xml` includes child module POMs in a monorepo. If the build uses Maven extensions or wrapper properties, they also participate in the cache key. When the dependency graph changes, a new cache key prevents reusing a cache that does not reflect the current configuration.

**Smoke test:** the example app does not open a server, so the process exits. For a REST service, replace this with a step that starts the application in the background, waits for the health endpoint, and shuts down the process cleanly; do not use a `grep` output pattern as the sole check for a long-running server.

## 8. Gradle: Configuring the Java Toolchain and Boot JAR

File **build.gradle** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

- The Java plugin provides compile, test, and plain JAR tasks.
- The Spring Boot Gradle Plugin provides `bootJar` to create an executable archive.
- The Dependency Management Plugin integrates Spring Boot dependency management.
- The Java toolchain requests a compiler/test launcher matching Java 17.
- `useJUnitPlatform()` enables JUnit Jupiter.

Gradle Wrapper must be committed—for example, `gradle-wrapper.properties` pointing to Gradle 8.5. Do not rely on a global Gradle pre-installed on the runner.

### 8.1. Building and Verifying with Gradle

~~~bash
./gradlew --no-daemon clean check bootJar
~~~

- `--no-daemon`: avoids keeping a Gradle daemon running after the build on ephemeral runners.
- `clean`: deletes previous outputs.
- `check`: runs tests and attached verification tasks.
- `bootJar`: creates the executable Spring Boot JAR.

Default artifact:

~~~text
build/libs/catalog-app-1.0.0.jar
~~~

If the build also creates a plain JAR, its name usually has a `-plain.jar` suffix. The workflow must upload the exact file produced by `bootJar`.

### 8.2. Gradle Multi-Project Builds

With the structure:

~~~text
repository/
├── settings.gradle
├── build.gradle
├── core/build.gradle
└── app/build.gradle
~~~

Run:

~~~bash
./gradlew --no-daemon clean :app:check :app:bootJar
~~~

Artifact:

~~~text
app/build/libs/app-1.0.0.jar
~~~

Update the workflow from `build/libs/catalog-app-1.0.0.jar` to `app/build/libs/app-1.0.0.jar`. Only the `app` module needs the Spring Boot plugin; a `core` library typically uses the Java Library plugin and produces a plain JAR.

## 9. Complete GitHub Actions Workflow for Gradle

Create **.github/workflows/ci-gradle.yml**:

~~~yaml
name: Spring Boot CI - Gradle

on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    name: Test and package with Gradle
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK 17 and Gradle cache
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: "17"
          cache: gradle
          cache-dependency-path: |
            **/*.gradle*
            **/gradle.properties
            **/gradle/wrapper/gradle-wrapper.properties
            **/gradle/libs.versions.toml

      - name: Verify Java and Gradle
        run: |
          java -version
          ./gradlew --version

      - name: Run checks and package executable JAR
        run: ./gradlew --no-daemon clean check bootJar

      - name: Verify executable Boot JAR
        run: |
          test -s build/libs/catalog-app-1.0.0.jar
          jar tf build/libs/catalog-app-1.0.0.jar > build/jar-entries.txt
          grep -q '^BOOT-INF/classes/com/example/catalog/CatalogApplication.class$' build/jar-entries.txt
          grep -q '^BOOT-INF/lib/' build/jar-entries.txt

      - name: Smoke test executable JAR
        run: |
          java -jar build/libs/catalog-app-1.0.0.jar --spring.main.banner-mode=off > build/smoke.log
          grep -q '^CI_PACKAGE_OK$' build/smoke.log

      - name: Prepare artifact and SHA-256
        run: |
          mkdir -p dist
          cp build/libs/catalog-app-1.0.0.jar dist/
          (
            cd dist
            sha256sum catalog-app-1.0.0.jar > catalog-app-1.0.0.jar.sha256
          )

      - name: Upload executable JAR
        uses: actions/upload-artifact@v7
        with:
          name: spring-boot-gradle-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: dist/
          if-no-files-found: error
          retention-days: 14

      - name: Upload Gradle test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: gradle-test-reports-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/build/reports/tests/
          if-no-files-found: ignore
          retention-days: 7
~~~

The Maven and Gradle workflows are **two alternatives**. You do not need to put both in the same repository if the project uses only one build system.

## 10. Checkout: Ensuring the Right Commit Is Built

### 10.1. Push, pull_request, and Manual Triggers

- **push:** runs when commits are pushed to a declared branch or tag.
- **pull_request:** verifies changes before merging.
- **workflow_dispatch:** allows manual execution from the GitHub Actions UI/API.
- **tags:** can be used to trigger a release workflow on version tags.

The checkout action fetches the commit associated with the event. Do not manually clone the latest branch `HEAD` mid-workflow, because that commit may differ from the source revision being tested.

### 10.2. Shallow Checkout and fetch-depth

By default, checkout retrieves a shallow history suitable for most compile/test/package tasks. If a versioning plugin or release script needs Git tags or history, configure:

~~~yaml
- name: Checkout full history
  uses: actions/checkout@v7
  with:
    fetch-depth: 0
~~~

Use `fetch-depth: 0` only when genuinely needed. Downloading the full history can slow down checkout.

### 10.3. Submodules and Git LFS

If the source depends on submodules:

~~~yaml
- uses: actions/checkout@v7
  with:
    submodules: recursive
~~~

If using Git LFS:

~~~yaml
- uses: actions/checkout@v7
  with:
    lfs: true
~~~

Enable these options only when the repository actually uses them and the token has permission to fetch the corresponding data.

### 10.4. Monorepo and working-directory

If the POM/Gradle project resides under `services/catalog`, commands must run in that directory:

~~~yaml
- name: Build catalog service
  working-directory: services/catalog
  run: ./mvnw -B -ntp clean verify
~~~

Artifact paths must also reflect the working directory. A common mistake is building in a subdirectory while writing the upload path relative to the repository root.

## 11. Setting Up the JDK: Version, Distribution, and Toolchain

### 11.1. actions/setup-java

Example:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: "17"
~~~

This action installs the chosen JDK distribution, configures `JAVA_HOME`/PATH, and can cache Maven/Gradle dependencies. Java 17 is the feature version required by the example project.

**Major version and patch version:**

- `java-version: "17"` selects the Java 17 line; patch builds may be updated automatically.
- Pinning a specific version can improve strict reproducibility, provided the team maintains a security update policy.
- Do not use `latest` for releases that need a controlled Java 17 target, because the `latest` alias can move to a new feature release.

### 11.2. JDK Distribution

Distributions can differ in vendor, build, certificates, and packaging. The examples use Temurin for a clear baseline. If your organization standardizes on Microsoft Build of OpenJDK, Oracle JDK, or another distribution, change `distribution` to a name supported by the action and verify the actual version installed.

### 11.3. Checking Versions

~~~bash
java -version
./mvnw --version
./gradlew --version
~~~

Run only the wrapper command for your build system. With Gradle, you can inspect toolchains:

~~~bash
./gradlew -q javaToolchains
~~~

If multiple JDKs exist on the runner, the output helps confirm which toolchain Gradle detects. With Maven, you may need to check the compiler plugin or toolchains when the project uses a dedicated JDK.

### 11.4. Self-Hosted Runners

Newer major action versions use newer Node runtimes. Self-hosted runners need a runner version compatible with the runtime required by the action. When an action reports a Node/runner error, update the runner per GitHub Actions documentation and the action's release notes; do not arbitrarily downgrade action versions to mask runtime issues.

## 12. Dependency Cache: Configuring Properly for the Build System

### 12.1. Maven Cache

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: "17"
    cache: maven
    cache-dependency-path: |
      **/pom.xml
      **/.mvn/wrapper/maven-wrapper.properties
      **/.mvn/extensions.xml
~~~

Maven dependencies are typically downloaded to the local repository `~/.m2/repository`. Caching reduces downloads on subsequent builds. `cache-dependency-path` specifies which files contribute to the cache key hash.

For multi-module projects, include child POMs in the cache path. If Maven profiles or extensions alter the dependency graph, verify they are reflected in the key.

### 12.2. Gradle Cache

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: "17"
    cache: gradle
    cache-dependency-path: |
      **/*.gradle*
      **/gradle.properties
      **/gradle/wrapper/gradle-wrapper.properties
      **/gradle/libs.versions.toml
~~~

The Gradle cache stores downloaded dependencies, metadata, and the wrapper distribution. For projects with `buildSrc`, included builds, or custom version management files, verify that the cache key covers all inputs that affect dependency resolution.

### 12.3. Cache Does Not Guarantee Reproducibility

A cache only retrieves data faster. It does not by itself guarantee:

- SNAPSHOT or dynamic dependency versions have not changed.
- A repository has not overwritten the same artifact coordinates.
- The JDK patch version is always identical.
- Build scripts do not embed timestamps or random values.
- Artifact bytes are reproducible.

Release pipelines can use dependency locking/verification, checksums, and immutable repositories to control inputs.

### 12.4. When Should You Avoid Caching?

When investigating cache corruption, benchmarking a cold build, or running a one-off isolated verification, you can disable caching via the action or build tool mechanism. Do not permanently disable caching because of a single build failure; first determine whether the failure lies in dependency resolution, task outputs, or source code.

## 13. Testing and Verification: Placing Quality Gates Before Upload

### 13.1. Maven Lifecycle

The command:

~~~bash
./mvnw -B -ntp clean verify
~~~

runs the phases before `verify`, including compile, test, package, and verify. Spring Boot `repackage` is bound to the `package` lifecycle when using the starter parent. If tests or verification plugins fail, Maven returns a non-zero exit code and subsequent steps in the job are skipped by default.

### 13.2. Gradle Task Graph

The command:

~~~bash
./gradlew --no-daemon clean check bootJar
~~~

- `check` depends on verification tasks, including `test`.
- `bootJar` creates the executable archive.
- Gradle builds the task graph and executes dependency tasks first.
- A task does not run repeatedly within the same invocation just because multiple other tasks depend on it.

### 13.3. Unit Tests and Integration Tests

Maven typically uses Surefire for unit tests and Failsafe for integration tests when configured. Gradle uses `Test` tasks and corresponding source sets. Clearly define which tests belong to the pull request quality gate and which require external services.

If integration tests require PostgreSQL, Redis, Kafka, or an HTTP service, CI must provide the appropriate service container, Testcontainers, or test endpoint. Do not let tests be silently skipped simply because the runner lacks a service.

### 13.4. Uploading Test Reports Even When Tests Fail

Use:

~~~yaml
- name: Upload test reports
  if: ${{ always() }}
  uses: actions/upload-artifact@v7
  with:
    name: test-reports-${{ github.run_id }}-${{ github.run_attempt }}
    path: |
      **/target/surefire-reports/
      **/target/failsafe-reports/
    if-no-files-found: ignore
    retention-days: 7
~~~

This example is for Maven. For Gradle, change the path to `**/build/reports/tests/`. Because the step runs with `always()`, reports can still be saved after a test failure. `if-no-files-found: ignore` avoids adding a secondary failure if the project did not produce reports at that stage.

## 14. Packaging: Identifying the Exact Executable Boot JAR

### 14.1. Maven

With the Spring Boot parent and no classifier, the executable JAR is typically:

~~~text
target/catalog-app-1.0.0.jar
~~~

If an `exec` classifier is configured, the file may be:

~~~text
target/catalog-app-1.0.0-exec.jar
~~~

If `repackage` replaces the main artifact, the original JAR may be preserved as `.jar.original`. The workflow must upload the executable file matching the plugin configuration.

### 14.2. Gradle

The task:

~~~bash
./gradlew bootJar
~~~

creates an executable archive usually at:

~~~text
build/libs/catalog-app-1.0.0.jar
~~~

If a plain JAR is also generated alongside it, it may be named:

~~~text
build/libs/catalog-app-1.0.0-plain.jar
~~~

Do not use the wildcard `build/libs/*.jar` to select an artifact when the folder contains multiple JAR types. Specify the exact file produced by `bootJar`.

### 14.3. Checking Archive Structure

Maven:

~~~bash
test -s target/catalog-app-1.0.0.jar
jar tf target/catalog-app-1.0.0.jar > target/jar-entries.txt
grep -q '^BOOT-INF/classes/com/example/catalog/CatalogApplication.class$' target/jar-entries.txt
grep -q '^BOOT-INF/lib/' target/jar-entries.txt
~~~

Gradle:

~~~bash
test -s build/libs/catalog-app-1.0.0.jar
jar tf build/libs/catalog-app-1.0.0.jar > build/jar-entries.txt
grep -q '^BOOT-INF/classes/com/example/catalog/CatalogApplication.class$' build/jar-entries.txt
grep -q '^BOOT-INF/lib/' build/jar-entries.txt
~~~

These steps verify that the file exists, contains the application class, and includes nested libraries. They do not yet prove that all production APIs, databases, and configurations work; smoke tests and integration tests are still required.

### 14.4. Smoke Test for a Command-Line Application

~~~bash
java -jar target/catalog-app-1.0.0.jar --spring.main.banner-mode=off > target/smoke.log
grep -q '^CI_PACKAGE_OK$' target/smoke.log
~~~

The command above is for the `CommandLineRunner` example that exits after running. For a web service, start the process in the background, wait for the health endpoint, verify the response, and stop the process; do not expect the app to exit on its own.

## 15. SHA-256: Recording the Artifact Checksum

### 15.1. Generating the Checksum

On an Ubuntu runner:

~~~bash
mkdir -p dist
cp target/catalog-app-1.0.0.jar dist/
(
  cd dist
  sha256sum catalog-app-1.0.0.jar > catalog-app-1.0.0.jar.sha256
)
~~~

Staging directory:

~~~text
dist/
├── catalog-app-1.0.0.jar
└── catalog-app-1.0.0.jar.sha256
~~~

The checksum file contains the digest and corresponding filename. It helps detect files that were modified or incompletely transferred after upload/download.

### 15.2. Verifying After Download

~~~bash
cd downloaded
sha256sum -c catalog-app-1.0.0.jar.sha256
~~~

If it matches, stdout prints:

~~~text
catalog-app-1.0.0.jar: OK
~~~

If the file is wrong or missing, `sha256sum` returns a non-zero exit code. Do not regenerate the checksum from a mismatched file and mark it as passed; investigate the source of the change.

### 15.3. Windows PowerShell

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "catalog-app-1.0.0.jar"
~~~

PowerShell prints the algorithm, hash, and path. When comparing two files, compare hash values only after confirming they refer to the same artifact and version.

**A checksum is not a digital signature.** It verifies byte consistency when you have a trusted checksum; it does not prove the source is safe or the publisher is trustworthy. Release security may require signatures, provenance, SBOMs, and a trusted build policy.

## 16. Uploading the Workflow Artifact

Example uploading the JAR and checksum:

~~~yaml
- name: Upload executable JAR
  uses: actions/upload-artifact@v7
  with:
    name: spring-boot-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
    path: dist/
    if-no-files-found: error
    retention-days: 14
~~~

Explanation:

- **name:** includes the commit SHA, run ID, and run attempt for traceability and to avoid name collisions on reruns.
- **path:** uploads only the staging directory containing distributable artifacts.
- **if-no-files-found: error:** treats a missing file as a pipeline error.
- **retention-days:** 14 days as an example for short-lived CI artifacts; repository or organization settings may enforce a lower limit.

Current `upload-artifact` versions create immutable artifacts. Do not design multiple jobs to append files to the same artifact name; gather all files to upload in a single step or assign a distinct name per job/matrix entry.

### 16.1. Uploading Artifacts in a Matrix

When running across multiple OS/JDK combinations, the artifact name must include the matrix values:

~~~yaml
name: spring-boot-${{ matrix.os }}-java-${{ matrix.java }}-${{ github.run_id }}
~~~

Otherwise, jobs may upload conflicting artifact names. If only one JDK is allowed to produce the release artifact, separate the canonical release job from compatibility matrix jobs.

### 16.2. Retention Is Not Permanent Storage

Workflow artifacts are bound to a run and a retention policy. Once expired or deleted, the download link is no longer usable. Artifacts supporting QA/UAT may need longer retention; long-term release packages should be published to a Maven repository, GitHub Packages, or a container registry per organizational policy.

## 17. Downloading the Artifact in a Downstream Job

Example of a second job downloading the artifact from the same workflow run:

~~~yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      # Checkout, setup JDK, test, package, and upload in this job.

  verify-artifact:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Download executable JAR
        uses: actions/download-artifact@v8
        with:
          name: spring-boot-maven-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: downloaded

      - name: Verify downloaded artifact
        run: |
          cd downloaded
          sha256sum -c catalog-app-1.0.0.jar.sha256
          test -s catalog-app-1.0.0.jar
~~~

`needs: build` ensures the downstream job runs only after `build` succeeds. It does not need to check out or rebuild if its goal is strictly to verify the file uploaded by the build job.

If downloading artifacts from another workflow run or repository, the action needs an additional run identifier and a token with appropriate permissions. The example above applies only to artifacts within the same workflow run.

### 17.1. Deploying the Exact Tested Artifact

A sound release flow:

~~~text
Build + test + package
          |
          v
      Upload artifact
          |
          v
   Approval / release gate
          |
          v
    Download same artifact
          |
          v
     Verify checksum
          |
          v
         Deploy
~~~

Do not rebuild from the latest branch in the deploy job if the requirement is to deploy the exact tested file. Rebuilding can produce a different artifact even if the branch commit has not changed.

## 18. Secure Checkout and Workflow Permissions

### 18.1. Least Privilege

Example:

~~~yaml
permissions:
  contents: read
~~~

Grant only the minimum permissions needed. Build/test jobs usually do not need `packages: write`, `deployments: write`, or `id-token: write`. Only release jobs should receive those permissions, restricted by trigger and environment.

### 18.2. Pull Requests from Forks

Pull requests may contain code contributed by external authors. Do not pass production secrets, signing keys, or deploy credentials to jobs running untrusted source code.

- Keep PR CI read-only.
- Do not use `pull_request_target` to check out and execute untrusted PR code.
- Separate release/deploy into jobs that run after merge or tag creation.
- Use protected environments and reviewer approvals when deploying to production.
- Do not print secrets to logs or upload configuration files containing credentials.

### 18.3. Pinning Action Versions

The examples use major tags `@v7`, `@v6`, `@v7`, `@v8` to pick up patches within the same major version. For sensitive pipelines, pin verified full commit SHAs and update them through reviewed pull requests. Do not copy stale SHAs from blogs or unverified workflows.

### 18.4. Self-Hosted Runners

Actions may require runners supporting newer Node runtimes. Check runner versions against action release notes. Additionally, the runner must have network access to JDK distributions, Maven/Gradle distributions, and dependency repositories per policy.

## 19. Controlled Workflow Optimization

### 19.1. Concurrency

~~~yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
~~~

When consecutive commits arrive on the same branch/PR, older workflow runs can be canceled to save runner capacity. Do not blindly apply `cancel-in-progress` to release/deploy jobs that must not be interrupted mid-flight.

### 19.2. Timeout

~~~yaml
timeout-minutes: 20
~~~

Choose timeouts based on actual build durations. Timeouts help catch hung tests or stalled downloads, though setting them too low can cause intermittent failures in integration tests.

### 19.3. JDK Matrix

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: ["17", "21"]
~~~

Then:

~~~yaml
with:
  distribution: temurin
  java-version: ${{ matrix.java }}
~~~

Artifact names must include `matrix.java`. If the official product builds only with Java 17, keep the canonical release artifact separate from compatibility jobs running Java 21.

### 19.4. Separating PR CI, Main CI, and Release

- **PR CI:** checkout, JDK setup, test, package, upload artifact for review.
- **Main CI:** verify post-merge commits, produce canonical artifact.
- **Release:** triggered by tag or approval, create/publish versioned package.
- **Deploy:** receive the exact verified immutable artifact and deploy it.

Never allow an arbitrary pull request to trigger a production deployment simply because the workflow holds write permissions.

## 20. Troubleshooting Common Errors

**1. `mvnw`/`gradlew` not found.** Checked out the wrong directory or the wrapper was not committed. Check the repository root, `working-directory`, and wrapper files.

**2. Permission denied when running the wrapper.** Git did not store the executable bit on Linux. Commit the `+x` permission or invoke the wrapper via an appropriate shell.

**3. Wrapper downloads the wrong build tool version.** Check `distributionUrl` in the wrapper properties; do not substitute global Maven/Gradle for the wrapper.

**4. Runner uses the wrong Java version.** Check `setup-java`, `JAVA_HOME`, `java -version`, and toolchain/compiler configuration.

**5. Local build passes but CI fails.** The local machine has caches, generated files, or environment variables that the runner lacks. Declare all inputs explicitly and use the wrapper.

**6. Cache key does not change when dependencies change.** Add POMs, build scripts, version catalogs, and wrapper properties to `cache-dependency-path`.

**7. Maven tests do not run.** Check Surefire/Failsafe, naming conventions, profiles, and `skipTests`/`maven.test.skip` flags.

**8. Gradle `check` skips expected tests.** Check the task graph, source sets, `useJUnitPlatform`, and test filters.

**9. Build succeeds but no Boot JAR is produced.** Check the Spring Boot plugin, `repackage`/`bootJar`, packaging type, and classifier.

**10. Upload reports no files found.** Verify the filename, `target`/`build` path, module working directory, and classifier.

**11. Accidentally uploaded the plain JAR.** Gradle may produce `-plain.jar`. Upload the exact file created by `bootJar`.

**12. Maven kept the original JAR as `.original`.** `repackage` may replace the main artifact. Check plugin classifier/attach settings and pick the executable output.

**13. Downstream job cannot download the artifact.** Check `needs`, artifact name, workflow run, repository/token, and retention.

**14. Matrix jobs upload duplicate names.** Add OS/JDK/architecture to the artifact name.

**15. Workflow rerun encounters a conflict.** Include `run_attempt` in the name; artifacts are immutable, so do not design for appending to the same name.

**16. Checksum mismatch.** Verify the downloaded file, staging path, filename, and any post-upload modifications. Do not regenerate the checksum for the new file while ignoring the root cause.

**17. Test reports lost when tests fail.** Use `if: always()` on the report upload step and `if-no-files-found: ignore`.

**18. Artifact is too large.** Upload only required files; exclude caches, source trees, and temporary files from the staging directory.

**19. Pull request from a fork needs a production secret.** Separate testing from publish/deploy; do not expose secrets to untrusted PR code.

**20. Overlapping workflow runs.** Use intentional `concurrency` for branch/PR CI; keep release jobs controlled.

**21. Job timeout.** Investigate service containers, hung tests, downloads, and runner resources before raising the timeout.

**22. JAR fails to run.** Check the Java runtime version, manifest, nested dependencies, profiles, external configuration, and smoke test.

**23. Only ran Maven `package`.** Verification plugins or integration tests may be bound to phases after `package`. Use `clean verify` when lifecycle verification is required by policy.

**24. Only ran Gradle `bootJar`.** Tests may not have run. Use `clean check bootJar`.

**25. Action version is no longer compatible with the runner.** Read the release notes and update self-hosted runners/runtimes as required by the action.

**26. Using workflow artifacts as a long-term release store.** Artifacts have retention limits. Use a Maven repository, package registry, or container registry for releases.

**27. Uploading the entire workspace.** Can leak `.env`, source code, caches, or internal files. Use a staging directory containing only the intended artifacts.

**28. Checkout is missing tags.** If versioning needs Git history/tags, set `fetch-depth: 0`; otherwise keep shallow checkout.

**29. Java target mismatches production runtime.** Align `setup-java` with the compiler/toolchain target, and verify the runtime version.

**30. Cannot trace which commit an artifact belongs to.** Include the commit SHA/run ID in the artifact name or metadata; retain checksums and toolchain logs.

## 21. Pipeline Acceptance Checklist

- [ ] Workflow resides in `.github/workflows/`.
- [ ] Triggers (`push`, `pull_request`, and manual dispatch) target the right branches/tags.
- [ ] Checks out the exact event commit.
- [ ] Submodules/LFS are configured if required by the project.
- [ ] Maven/Gradle Wrapper is committed and executable on the runner.
- [ ] JDK distribution and version are explicitly declared.
- [ ] Maven `java.version` or Gradle toolchain matches the target.
- [ ] Dependency cache uses the right package manager.
- [ ] Cache dependency path includes all files affecting the dependency graph.
- [ ] Build log records Java and Maven/Gradle versions.
- [ ] Unit tests run and failures fail the job.
- [ ] Integration tests are enabled per policy.
- [ ] Build task produces the exact executable Boot JAR.
- [ ] Archive check confirms `BOOT-INF/classes` and `BOOT-INF/lib`.
- [ ] Smoke test runs the actual application.
- [ ] Artifact path explicitly specifies the files to upload.
- [ ] SHA-256 is generated alongside the artifact when needed.
- [ ] Upload action has a unique name, `if-no-files-found: error`, and retention.
- [ ] Test reports are preserved for failure investigation.
- [ ] Downstream job uses `download-artifact` and verifies the checksum.
- [ ] Permissions follow least privilege.
- [ ] Pull requests do not receive production secrets.
- [ ] Release/deploy is separated from PR CI and has appropriate approvals.
- [ ] Action versions are tracked/pinned per policy.
- [ ] Branch protection requires the build job's status check.
- [ ] Both the success path and test/package failure paths have been tested.

## 22. Official Documentation

- GitHub Actions — checkout: https://github.com/actions/checkout
- GitHub Actions — setup-java: https://github.com/actions/setup-java
- GitHub Actions — upload-artifact: https://github.com/actions/upload-artifact
- GitHub Actions — download-artifact: https://github.com/actions/download-artifact
- GitHub Docs — Store and share data with workflow artifacts: https://docs.github.com/en/actions/tutorials/store-and-share-data
- GitHub Docs — Workflow syntax: https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
- Spring Boot 3.3 — Maven executable archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle executable archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Maven — Build lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Wrapper: https://maven.apache.org/wrapper/
- Gradle 8.5 — Wrapper: https://docs.gradle.org/8.5/userguide/gradle_wrapper.html
- Gradle — Java toolchains: https://docs.gradle.org/current/userguide/toolchains.html

**Conclusion:** A reliable CI pipeline must trace the **commit, JDK, build tool, test results, and final artifact**. Check out the exact source, install JDK 17, use the Wrapper, run lifecycle verification, produce the executable Boot JAR, inspect the archive and runtime behavior, compute SHA-256, and upload the exact files with clear naming and retention. Downstream jobs should download and verify the tested artifact rather than rebuilding it. Finally, keep short-lived workflow artifacts separate from release packages and keep workflow permissions and secrets minimal.