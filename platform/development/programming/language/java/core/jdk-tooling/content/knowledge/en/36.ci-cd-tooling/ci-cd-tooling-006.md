# Testing in CI for Java Projects

**Testing in Continuous Integration (CI)** is the step that automatically compiles and runs the test suite whenever code is pushed or a pull request is opened. CI provides early feedback on logic bugs, integration failures, differences across JDKs, and regressions before changes are merged or released.

A good test pipeline must answer three questions: did the test suite actually run, are the results saved for investigation, and do failures fail the pipeline properly? A green build when no tests were discovered, tests being unintentionally skipped, or reports being lost after a job fails can all create a false sense of security.

This article uses Java 17 as an example compatibility level, JUnit 5 for unit tests, Gradle and Maven for builds, along with GitHub Actions and GitLab CI to illustrate how it works in practice.

## 1. Where Do CI Tests Fit in the Pipeline?

A typical Java pipeline includes the following steps:

1. Check out the exact commit.
2. Install the JDK and build tool at the selected versions.
3. Restore the dependency cache.
4. Compile production source and test source.
5. Run unit/component tests.
6. Start supporting services if needed and run integration tests.
7. Generate test reports and coverage reports.
8. Upload reports so developers can inspect them even when tests fail.
9. Mark the job as succeeded or failed based on the build exit code.
10. Allow merging/releasing only after all required quality gates have passed.

CI is typically triggered by push, pull_request, or merge_request events. You can also run an additional nightly schedule to check slow flows, compatibility tests, or resource-intensive tests.

**The test job is a quality gate.** If a required test fails, the build command must return a non-zero exit code so CI marks the job as failed. The report upload step can run with an `always()` condition, but you must not use `continue-on-error` to turn failing tests into a green pipeline.

## 2. Types of Tests Commonly Run in CI

| Test type | Goal | Characteristics | Appropriate timing |
| --- | --- | --- | --- |
| Unit test | Verify a method/class with isolated dependencies | Fast, minimal environment dependencies | Every push and pull request |
| Component test | Verify a group of classes or a module | May use mocked databases/services | Every pull request |
| Integration test | Verify interactions between real components | May require a database, queue, HTTP service, or container | Pull request or main pipeline |
| Contract test | Verify the contract between producer/consumer | Requires managed contract data | Pull request and scheduled runs |
| End-to-end test | Verify end-to-end flows across multiple services | Slow, prone to environment dependencies | After deploying to a test environment or nightly |

You should not put every test into a single group. Unit tests need to be fast and stable so developers get early feedback. Integration/E2E tests often require starting services, data, and separate configuration; they can run in a later stage, yet they must still act as a quality gate if changes depend on them.

For example, an ordering service might have:

- Unit tests for calculating totals and validating discounts.
- Integration tests for persisting orders to the database.
- Contract tests confirming that the JSON API does not break consumers.
- E2E tests verifying the order placement, simulated payment, and confirmation sending flow.

## 3. Writing CI-Environment-Independent Tests

Tests that pass on a developer's machine but fail in CI usually depend on external state.

Key principles:

- Each test prepares its own data and cleans up afterward.
- Do not depend on test execution order or data created by a previous test.
- Do not use hardcoded ports if multiple jobs can run concurrently.
- Do not rely on system time, timezone, locale, or default random seeds.
- Use a fixed clock/seed when testing time-dependent or randomized logic.
- Never call a production database, production API, or real user accounts.
- Set reasonable timeouts for network, database, and process operations.
- Log enough detail to diagnose failures without printing passwords, tokens, or personal data.
- Separate tests that require real network/services from pure unit tests.

For integration tests that need a database or message broker, you can use CI service containers or Testcontainers to spin up temporary dependencies for each run. Tests should wait until the service is healthy before sending requests, use an isolated database/schema, and clean up resources upon completion.

If a test only passes when a service is already running locally on a personal machine, turn that service into a declared dependency in the pipeline. Do not rely on implicit runner state.

## 4. Java 17 and JUnit 5 Example

Create a small class to demonstrate how tests are discovered and executed in both Gradle and Maven.

File `src/main/java/com/example/Calculator.java`:

```java
package com.example;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static int divide(int numerator, int denominator) {
        if (denominator == 0) {
            throw new IllegalArgumentException("denominator must not be zero");
        }
        return numerator / denominator;
    }
}
```

File `src/test/java/com/example/CalculatorTest.java`:

```java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(12, Calculator.add(7, 5));
    }

    @Test
    void rejectsDivisionByZero() {
        IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> Calculator.divide(10, 0)
        );

        assertEquals("denominator must not be zero", error.getMessage());
    }
}
```

These two tests verify normal results and an error condition. They require no files, network, or database, making them suitable to run on any CI runner.

## 5. Running Unit Tests with Gradle

With the Gradle Java Plugin, test sources reside in src/test/java by default, while production sources reside in src/main/java.

Example build.gradle using JUnit 5 and allowing the test JDK to be selected via a project property:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

def testJdk = providers.gradleProperty('testJdk')
    .orElse('17')
    .get()
    .toInteger()

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(testJdk)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
```

The JUnit BOM aligns the versions of JUnit artifacts. `useJUnitPlatform()` tells Gradle to run the JUnit Platform. `junit-platform-launcher` provides the launcher at runtime; you should declare this dependency explicitly when using modern Gradle versions. `options.release = 17` keeps source/API compatibility at Java 17 while tests can run on JDK 17, 21, or 25.

Run tests on JDK 17:

```bash
./gradlew -PtestJdk=17 test
```

Run the full verification lifecycle:

```bash
./gradlew -PtestJdk=17 clean check
```

`test` runs unit tests. `check` is the lifecycle verification task and can additionally depend on integration tests, static analysis, or other verification tasks registered by the project.

Gradle generates default reports:

| Report | Path |
| --- | --- |
| HTML | build/reports/tests/test/index.html |
| JUnit XML | build/test-results/test/TEST-*.xml |

XML reports are compatible with many CI servers. HTML reports are useful when developers want to inspect individual tests, assertion failures, and stack traces.

A verification run on Gradle 9.2.1 with JDK 24.0.2 executed the two tests in the example above: both `addsTwoNumbers` and `rejectsDivisionByZero` PASSED; both HTML and XML reports were generated. The JDK used to run tests can differ from the source's target JDK version.

## 6. Separating Integration Tests with Gradle

Integration tests often need separate dependencies or environments. You can create an `integrationTest` source set to manage its classpath and reports independently.

Add to build.gradle:

```groovy
sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    shouldRunAfter tasks.named('test')
    useJUnitPlatform()
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

Place integration tests in src/integrationTest/java—for example, a class named `CalculatorIT`. When running `check`, Gradle runs both `test` and `integrationTest`; the integration task is ordered after unit tests.

Run integration tests alone:

```bash
./gradlew integrationTest
```

Run both groups:

```bash
./gradlew clean check
```

Reports are separated by task:

- build/test-results/test/
- build/test-results/integrationTest/
- build/reports/tests/test/
- build/reports/tests/integrationTest/

When integration tests require a database, add dependency/service startup and teardown to the pipeline. Do not place connection logic to a shared service inside a static initializer, as it makes tests harder to isolate and diagnose.

## 7. Running Unit Tests with Maven Surefire

Maven uses the Surefire Plugin to run unit tests during the `test` lifecycle phase. For JUnit 5, add the `junit-jupiter` dependency in `test` scope and pin the plugin version.

Example pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>calculator</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

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
        <configuration>
          <failIfNoTests>true</failIfNoTests>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Run unit tests:

```bash
mvn --batch-mode test
```

`--batch-mode` is suitable for CI because it requires no interactive input. By default, Surefire recognizes common test names such as `TestCalculator`, `CalculatorTest`, `CalculatorTests`, and `CalculatorTestCase`. You can configure include/exclude patterns if your project uses a different naming convention.

Default reports:

- Text: target/surefire-reports/*.txt
- XML: target/surefire-reports/TEST-*.xml

You can open the XML reports in CI to view test counts, failures, errors, and skipped tests. If a module is required to have tests, enable `failIfNoTests` on that module so a run that discovers no tests is not mistaken for a success.

A verification run on Maven 3.9.12, Surefire 3.5.2, and JDK 24.0.2 ran two JUnit 5 tests successfully: 2 tests, 0 failures, 0 errors, 0 skipped.

## 8. Separating Integration Tests with Maven Failsafe

Surefire is for unit tests. The **Failsafe Plugin** is for integration tests and participates in two lifecycle phases: `integration-test` and `verify`.

Add the plugin to pom.xml:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-failsafe-plugin</artifactId>
  <version>3.5.2</version>
  <executions>
    <execution>
      <goals>
        <goal>integration-test</goal>
        <goal>verify</goal>
      </goals>
    </execution>
  </executions>
</plugin>
```

Maven Failsafe looks by default for names such as `ITCalculator`, `CalculatorIT`, or `CalculatorITCase`. Under the default configuration, these classes live in src/test/java; Surefire does not pick up `*IT` names under its default unit test patterns, while Failsafe does.

Example src/test/java/com/example/CalculatorIT.java:

```java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorIT {
    @Test
    void integrationFlowUsesCalculator() {
        assertEquals(12, Calculator.add(7, 5));
    }
}
```

Run both unit tests and integration tests:

```bash
mvn --batch-mode clean verify
```

Important point: invoke `verify`, not just `integration-test`. Failsafe defers failing the build until the `verify` phase so that the `post-integration-test` phase can run to clean up the environment even if integration tests fail.

Reports are separated:

- Unit tests: target/surefire-reports/
- Integration tests: target/failsafe-reports/

A verification run on Maven 3.9.12 and Failsafe 3.5.2 ran `CalculatorTest` and `CalculatorIT` successfully; both report directories contained the corresponding XML files.

## 9. GitHub Actions: Testing Gradle Across Multiple JDKs

A JDK matrix helps detect compatibility issues across the runtimes your project supports. The example below tests Java 17, 21, and 25. Adjust this list according to your project's compatibility policy.

File .github/workflows/gradle-ci.yml:

```yaml
name: Java Gradle CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21', '25']

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: gradle

      - name: Show Java version
        run: java --version

      - name: Run verification
        run: ./gradlew --no-daemon -PtestJdk=${{ matrix.java }} clean check

      - name: Upload test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: gradle-test-reports-jdk-${{ matrix.java }}
          path: |
            **/build/test-results/**
            **/build/reports/tests/**
          if-no-files-found: ignore
```

Explanation:

- `actions/setup-java` installs the JDK, sets `JAVA_HOME`, and can cache Gradle dependencies.
- `matrix.java` creates a separate job for each JDK.
- `fail-fast: false` lets the remaining JDK jobs continue so you can see the full matrix results; a failed job still fails the workflow.
- `clean check` runs unit tests and registered verification tasks.
- `if: always()` applies only to uploading reports, so reports are still saved when the test job fails.
- `permissions: contents: read` restricts token permissions for a pipeline that only needs to read source code.

If using self-hosted runners, ensure a runner version compatible with the Node.js 24 runtime of modern actions. Check the runner version requirements in the action documentation before upgrading.

## 10. GitHub Actions: Testing Maven and Saving Surefire/Failsafe Reports

File .github/workflows/maven-ci.yml:

```yaml
name: Java Maven CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21', '25']

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven

      - name: Show Java version
        run: java --version

      - name: Run verification
        run: mvn --batch-mode --no-transfer-progress clean verify

      - name: Upload test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: maven-test-reports-jdk-${{ matrix.java }}
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
          if-no-files-found: ignore
```

If a project only has unit tests and has not configured Failsafe, you can use `mvn clean test`. Once Failsafe is registered, `mvn clean verify` is the appropriate command to run both unit and integration tests along with teardown steps.

Artifacts containing XML reports allow developers to download and analyze failures after the job finishes. There is no need to keep the entire build directory in the cache just to inspect reports; reports should be uploaded as separate artifacts.

The action versions in the examples are the current major versions at the time of writing. For pipelines requiring strict supply-chain control, you can pin actions to verified commit SHAs and update them in a controlled manner.

## 11. GitLab CI: Integrating JUnit XML into the Pipeline

GitLab can display JUnit XML results in pipelines and merge requests. Example with Maven:

File .gitlab-ci.yml:

```yaml
image: maven:3.9.12-eclipse-temurin-17

stages:
  - test

variables:
  MAVEN_OPTS: "-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository"

cache:
  key:
    files:
      - pom.xml
  paths:
    - .m2/repository/

test:
  stage: test
  script:
    - mvn --batch-mode --no-transfer-progress clean verify
  artifacts:
    when: always
    reports:
      junit:
        - target/surefire-reports/TEST-*.xml
        - target/failsafe-reports/TEST-*.xml
    paths:
      - target/surefire-reports/
      - target/failsafe-reports/
    expire_in: 1 week
```

`artifacts:reports:junit` tells GitLab which files contain test results. `artifacts:paths` keeps the files for direct download and inspection. `when: always` ensures regular artifacts are collected even if the test script fails.

For Gradle, change the command to `./gradlew clean check` and the report paths to `build/test-results/**` and `build/reports/tests/**`. The runner image must include the appropriate JDK/Gradle, or you must install the JDK in the job.

## 12. Choosing a JDK Matrix and Target Release

Testing on multiple JDKs does not mean every build has to change its target API.

For example, for a library supporting Java 17 and above:

- JDK 17: baseline runtime.
- JDK 21: verify a newer LTS runtime.
- JDK 25: verify the current LTS runtime.
- The compiler still uses `--release 17` to prevent accidentally using APIs newer than Java 17.

With Gradle, select the toolchain via a property and set `options.release = 17`. With Maven, set `maven.compiler.release` to `17`, while CI switches the JDK via `actions/setup-java`.

The matrix does not have to include every OS and every JDK. An oversized matrix slows down the pipeline and wastes resources. Choose combinations representative of your product's support matrix; add Windows/macOS when the code has OS-, filesystem-, or native-library-dependent behavior.

## 13. Caches, Artifacts, and Wrappers

These three concepts serve different roles:

| Component | Purpose | Examples |
| --- | --- | --- |
| Dependency cache | Reduce dependency download time | .gradle/caches, .m2/repository |
| Build artifact | Output needed by downstream jobs or releases | JAR, Docker image, generated package |
| Test report artifact | Evidence for analyzing test results | JUnit XML, HTML report, logs |

Caches do not replace reports and must not be used to hide test failures. A cache key should be based on dependency management files such as `build.gradle`, version catalogs, `gradle-wrapper.properties`, or `pom.xml`. When dependencies change, a new key ensures the runner downloads the right dependencies.

Commit the Gradle Wrapper and Maven Wrapper to the repository:

- Gradle: ./gradlew
- Maven: ./mvnw

Wrappers ensure local environments and CI use the same build tool version. Do not rely on whatever Gradle/Maven version happens to be preinstalled on the runner.

If the build uses a JDK toolchain, ensure the corresponding JDK is installed or provisioned by Gradle according to explicit configuration. Do not let CI silently pick a different compiler from local builds.

## 14. Test Failures, Skips, and Reports

CI needs to distinguish between the following statuses:

| Status | Meaning | Handling |
| --- | --- | --- |
| Passed | Test executed and assertions succeeded | Job can proceed |
| Failed | Assertion or test logic failed | Job must fail |
| Error | Test encountered an unexpected exception | Job must fail |
| Skipped | Test was not executed due to a condition or annotation | Inspect the skip reason |
| No tests found | No matching tests were discovered | Verify discovery/naming and fail if the project requires tests |

Commands that skip tests must be controlled:

- Maven `-DskipTests` skips running tests but may still compile test sources.
- Maven `-Dmaven.test.skip=true` skips both compiling and running tests.
- Gradle `-x test` excludes the `test` task from the execution graph.

These options are useful in certain standalone packaging tasks, but should not appear in CI jobs used as required test checks. Do not wrap test commands in `continue-on-error` or `|| true` to mask a non-zero exit code.

Uploading reports under `always()` is the right way to preserve failure evidence. That condition must not be placed on the test step itself. The test job must still retain its failure status if tests fail.

## 15. Test Suite Stability and Speed

As a test suite grows, you need to optimize it while preserving reliability.

**Controlled parallel execution**

Gradle supports `maxParallelForks`; Maven Surefire has `forkCount` and `reuseForks`. Increasing parallelism can shorten runtime, but if tests share a database, port, file, or static state, it easily introduces race conditions. Start low and measure CPU, RAM, and duration.

**Splitting test groups**

You can split unit, integration, and E2E tests into separate jobs/stages. Unit tests run fast on every pull request; E2E tests can run after deploying to a test environment or on a schedule. Required tests must still block merge/release at their corresponding stage.

**Managing flaky tests**

A test that intermittently passes and fails usually indicates a time dependency, race condition, shared state, or unstable service. You can rerun it to gather evidence, but retries must not turn an initial failure into an unrecorded green status. Track flaky tests as engineering issues to fix.

**Coverage**

Coverage measures which code was executed; it does not prove tests verify the right behavior. If using JaCoCo or a similar tool, you can set line/branch coverage thresholds on critical modules. Do not inflate coverage with tests that merely call getters or execute code without meaningful assertions.

## 16. Security and Reliability of CI Tests

CI often runs code submitted by contributors, so runner permissions and secrets must be restricted.

- Grant `GITHUB_TOKEN` only the necessary permissions; jobs that only check out and test usually need only `contents: read`.
- Do not expose production secrets to tests on pull requests from forks.
- Do not use the `pull_request_target` workflow to check out and execute untrusted code without proper security boundaries.
- Use dedicated service accounts and temporary databases for integration tests.
- Do not print credentials or tokens in test output.
- Separate test jobs from deploy jobs; deploy only after the test gate passes and appropriate branch/environment conditions are met.
- For self-hosted runners, restrict which repositories/jobs may use them and clean up the workspace after each run.
- Pin dependencies and CI actions according to your organization's supply-chain policy.

CI tests should not access production data. If realistic data is needed, use anonymized fixtures or synthetic datasets.

## 17. Troubleshooting Test Failures in CI

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Green build but no test reports | Test discovery found no classes or task was skipped | Check class names, source sets, and report directories |
| Gradle does not load JUnit Platform | Missing engine/launcher or `useJUnitPlatform()` not enabled | Add JUnit Jupiter, launcher runtime, and platform configuration |
| Maven does not discover JUnit 5 | Missing Jupiter engine or Surefire is too old | Check dependencies and pin Surefire version |
| Tests pass locally but fail in CI | Different JDK, timezone, locale, OS, or environment variables | Print versions, pin environment settings, and write independent tests |
| Integration test times out | Service not healthy yet, wrong port, or readiness incomplete | Use health checks and bounded connection retries |
| Test passes alone but fails in suite | Shared state, test order, or resource contention | Isolate fixtures, schemas, files, and ports |
| Test reports missing after failure | Artifact upload only runs when job succeeds | Use `always()` for the upload step |
| JDK matrix fails on only one version | Different API/runtime behavior or compiler target | Inspect that job's log and verify source compatibility |
| Maven `verify` does not run integration tests | Failsafe execution not registered or wrong class name | Check plugin goals and `*IT` naming pattern |
| Gradle `check` only runs unit tests | `integrationTest` not wired into `check` | Add the task dependency |
| Build spends too long downloading dependencies | No cache or cache key changes constantly | Cache keyed on wrapper/build files |
| Tests fail but pipeline stays green | `continue-on-error`, `|| true`, or skip flag | Preserve exit codes and remove error-masking options |

## 18. Step-by-Step Process to Set Up CI Testing from Scratch

1. Determine the minimum JDK and the JDK runtimes to support.
2. Commit the Gradle/Maven Wrapper and pin plugin versions.
3. Standardize source layout and naming conventions for unit/integration tests.
4. Choose JUnit 5 or an appropriate testing framework.
5. Configure Gradle `test` or Maven Surefire.
6. Create a separate integration test task/phase if supporting services are needed.
7. Ensure `check` or `verify` executes all required tests.
8. Run the test command locally to verify reports and exit codes.
9. Create workflows for push/pull request and the JDK matrix.
10. Cache dependencies and upload reports with an always-run condition.
11. Set CI checks as required status checks for branch protection.
12. Monitor test duration, flaky rate, and failure reports to improve the suite.

With Gradle, the commonly used command is:

```bash
./gradlew --no-daemon clean check
```

With Maven, the commonly used command is:

```bash
mvn --batch-mode --no-transfer-progress clean verify
```

Use `check` when Gradle has unit/integration verification tasks registered; use `verify` when Maven has Surefire/Failsafe and post-test checks configured.

## 19. Key Takeaways

- CI tests automatically run the test suite on every change and provide a quality gate before merge/release.
- Unit tests should be fast, independent, and run on every pull request; integration/E2E tests need clear environments and schedules.
- JUnit 5 must be configured properly in Gradle/Maven; with modern Gradle, declare the launcher runtime explicitly.
- Gradle `test` runs unit tests; attach `integrationTest` to `check` to run both groups.
- Maven Surefire runs unit tests in the `test` phase; Failsafe runs integration tests and checks results in `verify`.
- Use `mvn verify` so Failsafe has a chance to run teardown steps before marking the build as failed.
- JUnit XML and HTML reports should be saved as artifacts, even when the test job fails.
- The JDK matrix should follow the support policy; keep a separate compiler release if API compatibility with an older version is required.
- Cache dependencies to speed up builds; do not confuse caches with test reports or build artifacts.
- Failing tests must cause the job to return a non-zero exit code; do not mask failures with skip flags or `continue-on-error`.
- Isolate data, services, and secrets; never run tests against production credentials or data.
- Track flaky tests, runtime, and coverage as metrics to improve suite quality.

A reliable Java pipeline does more than just run a test command. It ensures the right tests are discovered, the right JDKs are verified, reports are always available for inspection, and every required failure blocks merging or releasing.

## References

- [Gradle: Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [GitHub Actions: actions/setup-java](https://github.com/actions/setup-java)
- [GitHub Actions: actions/checkout](https://github.com/actions/checkout)
- [GitHub Actions: actions/upload-artifact](https://github.com/actions/upload-artifact)
- [GitHub Actions: Using jobs and matrix strategies](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs)
- [GitLab CI/CD YAML syntax](https://docs.gitlab.com/ci/yaml/)
- [GitLab CI/CD JUnit test reports](https://docs.gitlab.com/ci/yaml/artifacts_reports/)
