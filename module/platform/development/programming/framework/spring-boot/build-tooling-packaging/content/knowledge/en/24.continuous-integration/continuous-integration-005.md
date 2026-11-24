# Running Verify or Build and Collecting Test Reports

## 1. Objective

A reliable CI build must accomplish two things: confirm that the source code passes required checks, and preserve sufficiently detailed evidence to investigate failures. Merely seeing "BUILD SUCCESS" or "BUILD FAILED" is not enough; you need to know which tests ran, which passed/failed/were skipped, which module failed, what the stack trace says, and where reports are stored.

This lesson guides running verification/builds with Gradle or Maven, reading test reports, and configuring CI to collect reports even when tests fail. The focus is on Spring Boot / Java 17, JUnit 5, and GitHub Actions; the principles apply equally to other CI platforms.

After this lesson, you will be able to:

- Distinguish Gradle `check`/`build` from Maven `verify`.
- Run unit tests, integration tests, and packaging using the Wrapper.
- Read human-facing HTML reports and CI-facing JUnit XML reports.
- Collect reports from multi-module builds.
- Keep the build status failed when tests fail while still uploading reports.
- Distinguish test reports, coverage reports, and static-analysis reports.
- Handle undiscovered tests, flaky tests, timeouts, missing reports, and CI-only failures.

**Example versions:** Java 17, JUnit Jupiter 5.10.2, Gradle Wrapper, and Maven Wrapper. These versions are illustrative; use versions compatible with your project and approved by your organization.

## 2. How Do Build, Check, Verify, and Test Differ?

The word "verify" means different things depending on the build tool. Do not run the same command name assuming Gradle and Maven share identical lifecycles.

| Build Tool | Command/Task | Meaning |
| --- | --- | --- |
| Gradle | `test` | Runs configured test tasks, typically unit tests |
| Gradle | `check` | Runs verification tasks; defaults to depending on `test` and can include quality/integration checks |
| Gradle | `assemble` | Produces configured outputs/artifacts |
| Gradle | `build` | Lifecycle task combining `check` and `assemble` |
| Maven | `test` | Runs the `test` phase, typically via Maven Surefire |
| Maven | `package` | Runs preceding phases and packages the artifact |
| Maven | `verify` | Runs through the `verify` phase, including plugin goals bound to `integration-test`/`verify` |
| Maven | `install` | Runs `verify` and then installs the artifact into the local Maven repository |

### 2.1. Gradle Has No Default verify Lifecycle Task

The Gradle Java plugin provides standard lifecycle tasks such as `check`, `assemble`, and `build`. A project may define its own `verify` task or apply a plugin that provides one, but do not assume that task always exists.

Run:

~~~bash
./gradlew tasks --all
./gradlew help --task check
./gradlew help --task build
~~~

If the project defines a custom `verify` task, inspect the task graph and plugin documentation before using it.

For typical Java/Spring Boot CI:

~~~bash
./gradlew --no-daemon --console=plain clean build
~~~

To run verification without assembling artifacts:

~~~bash
./gradlew --no-daemon --console=plain clean check
~~~

### 2.2. Maven verify Is a Standard Lifecycle Phase

Maven uses a standard build lifecycle. When running:

~~~bash
./mvnw -B -ntp clean verify
~~~

Maven executes phases prior to `verify` in order, including compile, test, package, and plugin goals bound to the lifecycle. When Failsafe is properly configured, integration tests run in `integration-test` and results are verified in `verify`.

For CI pipelines that test and verify artifacts, `verify` is usually the right endpoint. There is no need to run `install` unless the pipeline must install artifacts into the local repository for another build step.

### 2.3. Do Not Confuse a Passing Build with Tests Actually Running

A build can turn green even when zero tests were discovered if the project or plugin does not enable fail-on-no-tests or if test sources are misconfigured. Therefore, always check the test counts in reports:

- Number of tests discovered.
- Number of passing tests.
- Number of failures and errors.
- Number of skipped/aborted tests.
- Which modules and source sets ran.
- Whether the test task was actually in the task graph.

If a module is intentionally designed without tests, zero tests can be valid. If tests are mandatory for a module, configure an explicit policy to fail when no tests are discovered.

## 3. Java 17 and JUnit 5 Example

Let's use a small Java class to give us an isolated test suite with easy-to-read reports.

### 3.1. Production Class

Create `src/main/java/com/example/Calculator.java`:

~~~java
package com.example;

public final class Calculator {

    public int add(int left, int right) {
        return left + right;
    }

    public int multiply(int left, int right) {
        return left * right;
    }

    public int divide(int dividend, int divisor) {
        if (divisor == 0) {
            throw new ArithmeticException("divisor must not be zero");
        }
        return dividend / divisor;
    }
}
~~~

### 3.2. JUnit 5 Test Class

Create `src/test/java/com/example/CalculatorTest.java`:

~~~java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {

    private final Calculator calculator = new Calculator();

    @Test
    void addsTwoNumbers() {
        assertEquals(7, calculator.add(3, 4));
    }

    @Test
    void multipliesTwoNumbers() {
        assertEquals(12, calculator.multiply(3, 4));
    }

    @Test
    void rejectsDivisionByZero() {
        ArithmeticException exception = assertThrows(
                ArithmeticException.class,
                () -> calculator.divide(10, 0)
        );

        assertEquals("divisor must not be zero", exception.getMessage());
    }
}
~~~

This test has three independent methods. When JUnit Jupiter is properly configured and discovered, the report shows a total of 3 tests, 0 failures, 0 errors, and 0 skipped. Execution timings and output formatting vary by runner and plugin.

### 3.3. Configuring the Java Version

The project requires JDK 17 and Java 17 bytecode target. With Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

With Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Compiler release does not install a JDK. The runner must have a suitable JDK installed; verify with `java -version` and `javac -version` before running the build.

## 4. Gradle: Configuring and Running Tests

### 4.1. Groovy DSL

Minimal `build.gradle` example for Java/JUnit 5:

~~~groovy
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
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    reports {
        junitXml.required = true
        html.required = true
    }

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showStandardStreams = false
    }
}
~~~

The JUnit BOM keeps JUnit artifact versions aligned. `useJUnitPlatform()` tells the Gradle `Test` task to use the JUnit Platform to discover Jupiter tests.

### 4.2. Kotlin DSL

If the project uses `build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

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
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    reports {
        junitXml.required.set(true)
        html.required.set(true)
    }

    testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
        showStandardStreams = false
    }
}
~~~

Pick only one DSL per module. For Spring Boot projects, keep existing plugins and dependencies and add the appropriate test dependencies and settings; never overwrite the whole build file just to add JUnit.

### 4.3. Running at Each Level

Run unit tests:

~~~bash
./gradlew --no-daemon --console=plain test
~~~

Run full verification:

~~~bash
./gradlew --no-daemon --console=plain check
~~~

Build artifacts and run checks:

~~~bash
./gradlew --no-daemon --console=plain clean build
~~~

Inspect the task graph:

~~~bash
./gradlew check --dry-run
./gradlew build --dry-run
~~~

`--dry-run` prints the planned tasks without executing them. Use it to confirm `test` and verification tasks are in the graph; it does not produce actual test reports.

### 4.4. Running a Specific Test

By class:

~~~bash
./gradlew test --tests "com.example.CalculatorTest"
~~~

By method (when filter syntax matches the test engine):

~~~bash
./gradlew test --tests "com.example.CalculatorTest.addsTwoNumbers"
~~~

Filtering by package or class speeds up debugging loops. Before merging or releasing, still run the full verification suite. If a filter matches zero tests, inspect the output and reports so you do not mistake zero executions for passing tests.

### 4.5. Where Are Gradle Test Reports Stored?

For a single-module project:

~~~text
build/
├── reports/
│   └── tests/
│       └── test/
│           └── index.html
└── test-results/
    └── test/
        ├── TEST-com.example.CalculatorTest.xml
        └── binary/
~~~

- HTML report: `build/reports/tests/test/index.html` — open in a browser to inspect summaries, classes, methods, and failure details.
- JUnit XML: `build/test-results/test/*.xml` — parsed by CI to display test annotations and trends.
- Binary results: internal Gradle data used to generate reports; does not replace JUnit XML in common upload workflows.

In multi-module projects, each module has its own `build` directory, for example:

~~~text
service/build/reports/tests/test/index.html
service/build/test-results/test/*.xml
api/build/reports/tests/test/index.html
api/build/test-results/test/*.xml
~~~

Never assume reports exist only in the root `build/` folder.

## 5. Gradle: Continuing Independent Tasks and Preserving Failure Status

By default, a task failure can cause downstream or dependent tasks to be skipped. In multi-module builds, you can use:

~~~bash
./gradlew --no-daemon --console=plain clean build --continue
~~~

`--continue` lets Gradle keep running independent tasks after a failure when permitted by the dependency graph. The overall build still fails if any task fails. This lets CI collect more test reports across other modules.

Do not configure:

~~~groovy
tasks.withType(Test).configureEach {
    ignoreFailures = true
}
~~~

in release verification if the build must fail on test failures. `ignoreFailures = true` prevents the `Test` task from propagating failure to the build result as intended. To preserve reports on failure, use a CI upload step with an `always` condition rather than turning test failures into a pass.

### 5.1. Test Output and Report Verbosity

You can configure:

~~~groovy
tasks.withType(Test).configureEach {
    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showCauses true
        showStackTraces true
        showStandardStreams false
    }
}
~~~

Console logs should clearly show which test failed and provide a failure summary. HTML and XML reports preserve full details for later inspection. Enable standard output/error for all tests only when needed, because logs can grow huge or accidentally leak sensitive test data/credentials.

### 5.2. Test Parallelism

Gradle can run test forks in parallel:

~~~groovy
tasks.withType(Test).configureEach {
    maxParallelForks = 2
}
~~~

Increase parallelism only when tests are isolated and resources suffice. Tests sharing ports, database schemas, file paths, or singleton state can race when run concurrently. Any test that passes sequentially yet fails in parallel requires investigating shared state, isolation, and cleanup.

`maxParallelForks` sets the fork count for a single `Test` task; Gradle worker limits and CI CPU count also constrain total concurrency. Never crank it up without measuring memory usage and test stability.

## 6. Maven: Running Verify and Collecting Reports

### 6.1. Surefire for Unit Tests

The Maven Surefire Plugin runs unit tests in the `test` phase. JUnit Jupiter requires a compatible engine or aggregator dependency.

In a POM using the Spring Boot parent, you can add the test dependency:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

If not using the Spring Boot parent/BOM, pin the JUnit version or import the JUnit BOM in `dependencyManagement`. Pin Maven plugin versions per project policy; never let builds rely on arbitrary plugin versions.

An explicit Surefire configuration:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <reportsDirectory>target/surefire-reports</reportsDirectory>
        <useModulePath>false</useModulePath>
    </configuration>
</plugin>
~~~

`useModulePath=false` helps certain classpath-based projects when JPMS/module path causes issues; it is not mandatory for every project. Keep this option only if it suits your actual module layout.

### 6.2. Running Unit Tests and Inspecting Reports

~~~bash
./mvnw -B -ntp clean test
~~~

Surefire normally generates:

~~~text
target/
└── surefire-reports/
    ├── TEST-com.example.CalculatorTest.xml
    ├── com.example.CalculatorTest.txt
    └── ...
~~~

- XML: structured test suite/case data, counts, failures/errors/skips, and failure details.
- TXT: console-style report per test class, convenient for reading stack traces.
- Console: Maven summary showing plugin goals and build status.

Paths can vary if the POM customizes `reportsDirectory` or a module sets a custom build directory.

### 6.3. Maven Failsafe for Integration Tests

Surefire fits fast unit tests. Maven Failsafe is built for integration tests, typically matching naming patterns such as `*IT.java` or configured patterns.

Example plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.2.5</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Failsafe separates running integration tests in the `integration-test` phase from checking results in the `verify` phase. This design allows `post-integration-test` steps (such as shutting down a test server or compose stack) to run before concluding an integration test failure in `verify`.

Run:

~~~bash
./mvnw -B -ntp clean verify
~~~

Running only `mvn test` stops before `integration-test` and `verify`; therefore, it cannot prove the Failsafe integration suite executed.

### 6.4. Failsafe Reports

~~~text
target/
├── surefire-reports/
│   ├── TEST-...xml
│   └── ...
└── failsafe-reports/
    ├── TEST-...xml
    ├── ...-output.txt
    └── ...
~~~

Surefire and Failsafe maintain separate report directories. Upload both when the pipeline runs unit and integration tests. Never confuse Failsafe reports with Surefire paths and miss integration failures.

### 6.5. Multi-Module Maven Builds

If a reactor has multiple modules and you want to gather as many reports as possible before failing, use:

~~~bash
./mvnw -B -ntp clean verify -fae
~~~

`-fae`/`--fail-at-end` lets Maven continue building modules that do not depend on a failed module, reporting the build failure at the end. Modules depending on a failed module may still be skipped. This never converts a failure into a success.

Never use `-fn`/`--fail-never` in a release gate: that option can cause Maven to exit as successful despite errors.

## 7. Reading JUnit XML and HTML Reports

### 7.1. JUnit XML

A JUnit XML report generally looks like:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.CalculatorTest"
           tests="3"
           failures="0"
           errors="0"
           skipped="0"
           time="0.012">
    <testcase classname="com.example.CalculatorTest"
              name="addsTwoNumbers"
              time="0.003"/>
    <testcase classname="com.example.CalculatorTest"
              name="multipliesTwoNumbers"
              time="0.002"/>
    <testcase classname="com.example.CalculatorTest"
              name="rejectsDivisionByZero"
              time="0.007"/>
</testsuite>
~~~

This example illustrates schema and counts, not an actual run report. Real reports contain timings, names, and failure details depending on the plugin and test engine.

Attributes to check:

- `tests`: total test cases recorded.
- `failures`: assertion failures.
- `errors`: execution errors outside assertions or unexpected exceptions.
- `skipped`: tests skipped, disabled, or aborted per the reporter.
- `time`: elapsed time recorded by the reporter.

A suite may span multiple XML files; aggregate totals across all unique suites without double-counting duplicate report artifacts.

### 7.2. Assertion Failures vs. Test Errors

Example assertion failure:

~~~text
expected: <7>
 but was: <6>
~~~

The test ran, but expected and actual values differed.

Example error:

~~~text
java.lang.IllegalStateException: database connection refused
~~~

The test failed during setup, runtime, or an external service call before the assertion completed. Proper classification helps decide whether to fix application code, test fixtures, or the environment.

### 7.3. HTML Reports

HTML reports are typically convenient for:

- Viewing total test counts and success rates.
- Drilling into packages and classes.
- Checking individual test durations.
- Reading failure stack traces.
- Spotting slow or failing tests.

CI should keep both HTML and XML: HTML for human readers; XML for CI parsers, trend dashboards, and integrations.

### 7.4. Different Reports Are Not the Same Thing

| Report | Information | Common Source |
| --- | --- | --- |
| Unit test report | Pass/fail/skip, stack traces, duration | Gradle `Test` / Maven Surefire |
| Integration test report | Test results against DB/services/containers | Gradle `integrationTest` / Maven Failsafe |
| Coverage report | Lines and branches executed | JaCoCo |
| Static analysis | Code smells, bug patterns, rule violations | Checkstyle, PMD, SpotBugs, Sonar |
| Build scan / build report | Task graph, performance, dependency resolution | Gradle Enterprise / Build Scan or CI |
| Packaging report | Artifact metadata, checksums, image details | Build/publish tooling |

Running tests does not automatically generate a coverage report unless JaCoCo is configured. Likewise, a high coverage percentage does not prove tests have strong assertions; examine both reports and test quality.

## 8. GitHub Actions: Uploading Gradle Reports Even When Tests Fail

This is crucial: if the Gradle step returns a non-zero exit code, subsequent steps are skipped by default. Report uploads require the `if: always()` condition.

Example workflow:

~~~yaml
name: Gradle Verification

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

      - name: Run Gradle build
        run: ./gradlew --no-daemon --console=plain clean build --continue

      - name: Upload Gradle test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: gradle-test-reports
          path: |
            **/build/test-results/**
            **/build/reports/tests/**
          if-no-files-found: warn
          retention-days: 14
~~~

When a test fails:

- The Gradle step fails and the job stays failed.
- The upload step still runs thanks to `if: always()`.
- XML and HTML reports are saved as a workflow artifact.
- Reviewers can download the artifact to inspect the specific failing test and module.

`if-no-files-found: warn` prevents missing reports (e.g., if the build failed before test execution) from causing a second upload error that obscures the root cause. If your project strictly mandates reports and missing reports violate policy, switch to `error` after confirming paths are accurate.

In production, pin actions by reviewed full commit SHA rather than just the `@v4` tag. The example uses tags for readability; tags are not immutable pins.

### 8.1. Why Not Use continue-on-error?

Do not write:

~~~yaml
- name: Run Gradle build
  continue-on-error: true
  run: ./gradlew clean build
~~~

if merge or release gates must fail when tests fail. `continue-on-error` prevents step failures from blocking the job as intended. Upload reports in a separate step with `if: always()`, preserving the build step's exit code.

### 8.2. Reports in Multi-Module Gradle

The pattern:

~~~yaml
path: |
  **/build/test-results/**
  **/build/reports/tests/**
~~~

covers submodules that each have their own `build` directory. Verify artifact uploads on a build where at least one module passes and one fails to confirm report paths are collected accurately.

## 9. GitHub Actions: Uploading Maven Surefire/Failsafe Reports

Maven example:

~~~yaml
name: Maven Verification

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

      - name: Run Maven verification
        run: ./mvnw -B -ntp clean verify -fae

      - name: Upload Maven test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: maven-test-reports
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
          if-no-files-found: warn
          retention-days: 14
~~~

If Maven `verify` fails due to a unit or integration test, the upload step still saves available reports. `-fae` lets the reactor continue independent modules after a failure, while the job still ends failed.

For a single-module Maven project, `target/...` paths suffice. The `**/target/...` pattern supports multi-module builds. If report directories are customized in the POM, adjust upload paths to match actual outputs.

## 10. Collecting Reports Outside GitHub Actions

The same principles apply to GitLab CI, Jenkins, Azure Pipelines, and other platforms:

1. Run build/tests and preserve the exit code.
2. Always run the report publish/archive step even when the test step fails.
3. Upload JUnit XML for test result parsers.
4. Upload HTML/TXT for human investigation.
5. Keep the build/job status failed if tests fail.
6. Set appropriate retention and restrict access permissions.
7. Never publish sensitive reports as public artifacts.

### 10.1. GitLab CI Example

~~~yaml
test:
  image: eclipse-temurin:17-jdk
  script:
    - ./gradlew --no-daemon clean test
  artifacts:
    when: always
    reports:
      junit: "**/build/test-results/test/*.xml"
    paths:
      - "**/build/reports/tests/"
      - "**/build/test-results/"
    expire_in: 14 days
~~~

`when: always` saves artifacts when the job finishes, even if `script` fails. Verify GitLab runner glob syntax and support against your deployed GitLab version. For Maven, replace the JUnit report glob with Surefire and Failsafe XML paths.

### 10.2. Jenkins Pipeline Example

~~~groovy
pipeline {
    agent any

    stages {
        stage('Verify') {
            steps {
                sh './gradlew --no-daemon clean build --continue'
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true,
                  testResults: '**/build/test-results/**/*.xml'
            archiveArtifacts allowEmptyArchive: true,
                             artifacts: '**/build/reports/tests/**'
        }
    }
}
~~~

`post { always { ... } }` runs report archiving even when the stage fails. `allowEmptyResults`/`allowEmptyArchive` helps when a build fails before generating reports; if the project mandates reports on every run, enforce a stricter policy. The Jenkins JUnit plugin must be installed.

### 10.3. Do Not Mask Failures with the Publish Step

The report publisher can fail on its own—for example, due to malformed XML or wrong paths. Distinguish:

- Test failure: product or test defect; the build must fail.
- Report publishing failure: evidence collection defect; the pipeline must surface this clearly too.
- Pre-test build failure: having no reports may be expected, yet logs must clearly show tests did not run.

Never turn a failed build into a success solely because report uploading succeeded.

## 11. Multi-Module: Running All Tests and Gathering Reports Properly

### 11.1. Gradle Multi-Project

List modules:

~~~bash
./gradlew projects
~~~

Run full verification and build:

~~~bash
./gradlew --no-daemon --console=plain clean build --continue
~~~

Gradle writes separate reports per project and per `Test` task, for example:

~~~text
api/build/test-results/test/
service/build/test-results/test/
worker/build/test-results/test/
~~~

With multiple `Test` tasks such as `test`, `integrationTest`, and `functionalTest`, reports live under directories matching each task name. Use a broader upload pattern:

~~~yaml
path: |
  **/build/test-results/**
  **/build/reports/tests/**
~~~

If a report aggregation plugin is applied, combined reports may be written to a separate project. Do not assume aggregation runs automatically unless the plugin/task is configured.

### 11.2. Maven Reactor

Run all modules:

~~~bash
./mvnw -B -ntp clean verify -fae
~~~

The Maven reactor orders modules by dependency graph. `-fae` continues modules independent of a failed module; dependent modules may still be skipped. Reports are generated in each module's `target` directory.

### 11.3. Aggregating Test Counts

Never sum test counts from both HTML and XML simultaneously, as they represent the same test run. In multi-module builds, aggregate across unique module/task XML files. If reruns, retries, or multiple executions occur, check report formats and plugin behavior to avoid double-counting.

## 12. Test Failures, Skipped, Flaky, and Zero Tests

### 12.1. Failure vs. Error vs. Skipped

- **Failure:** an assertion did not hold or the test framework recorded a failed check.
- **Error:** an exception, setup issue, or runtime failure prevented the test from completing normally.
- **Skipped:** the test was disabled, failed an assumption, or was recorded as skipped by the reporter.
- **Aborted:** the test halted due to an assumption/condition; representation depends on engine and reporter.

Never treat skipped tests as passing. If a suite shows many skipped tests, check the reasons and policy; some skips are intentional (e.g., OS-specific), while others may mask unexecuted tests.

### 12.2. Flaky Tests

Flaky tests that pass intermittently often involve:

- Shared mutable state or test execution ordering.
- Shared ports, files, or databases.
- Timing, fixed sleeps, or race conditions.
- Unstable external services or networks.
- Timezone, clock, or locale assumptions.
- Missing test cleanup or leftover threads/processes.
- Parallel forks hitting resource limits.

Record seeds, test order, retry counts, environment details, and logs. Never auto-retry indefinitely just to turn CI green; retries can aid diagnosis, not fix root causes. When using a retry plugin, reports should preserve both failed and passed attempts per policy so flaky behavior is not hidden.

### 12.3. Zero Tests Discovered

If a Gradle/Maven build passes with no reports:

1. Check whether the test task/phase executed.
2. Check whether test source directories match conventions.
3. Check class naming patterns.
4. Check JUnit Platform engine and dependencies.
5. Check test filters and exclusions.
6. Check whether the report output path was customized.
7. Check whether the module actually has tests or is permitted zero tests.

Gradle `Test` tasks and Maven Surefire behave differently when no tests match. For modules where tests are mandatory, configure fail-on-no-tests and verify the gate using a test deliberately filtered out.

### 12.4. Timeouts and Hanging Processes

Tests can hang due to unclosed threads, servers, executors, or containers. Configure bounded test timeouts and CI job timeouts, capturing thread dumps/logs when needed. Never just increase timeouts if tests are deadlocking or waiting on nonexistent dependencies.

## 13. JaCoCo Coverage Reports (Supplementary)

Coverage measures code executed during tests, which differs from JUnit test results. You can have 100% line coverage with weak assertions, or solid tests with lower coverage. Treat coverage as a supplementary signal, not a replacement for test review.

### 13.1. Gradle JaCoCo

Enable the plugin:

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}

jacocoTestReport {
    dependsOn test
    reports {
        xml.required = true
        html.required = true
    }
}
~~~

Run:

~~~bash
./gradlew test jacocoTestReport
~~~

Default reports usually appear at:

~~~text
build/reports/jacoco/test/html/index.html
build/reports/jacoco/test/jacocoTestReport.xml
~~~

In multi-module builds, paths lie under each corresponding project/module. The JaCoCo task generates coverage reports from the execution data of configured test tasks; if those tasks did not run or the agent was not attached properly, reports may be empty or missing.

### 13.2. Maven JaCoCo

You can configure the JaCoCo Maven Plugin with `prepare-agent` and `report` goals in the lifecycle. Pin the plugin version. After running `verify`, HTML and XML coverage reports typically appear under:

~~~text
target/site/jacoco/index.html
target/site/jacoco/jacoco.xml
~~~

Check the actual plugin configuration and execution phases; do not assume Surefire/Failsafe produces JaCoCo reports without the JaCoCo agent.

### 13.3. Uploading Coverage Separately

CI can upload:

~~~yaml
path: |
  **/build/reports/jacoco/**
  **/target/site/jacoco/**
~~~

Give it a dedicated artifact name or label it clearly if bundled with test reports. JUnit XML does not contain line/branch coverage; JaCoCo XML does not replace lists of test failures.

## 14. Keeping Reports Safe and Useful

Test reports can contain:

- Stack traces and absolute file paths.
- HTTP responses/bodies or test fixtures.
- Database names and URLs.
- Console output from the application.
- System properties or environment values logged by tests.
- Personal data used in tests.

Never log secrets in assertion messages, test stdout, or exception messages. Never upload `.env`, Maven `settings.xml`, Gradle properties, or test database dumps just because they sit next to reports.

Configure:

- Artifact retention matching audit and cost requirements.
- Access controls matching source/repository confidentiality.
- Redaction in loggers and test fixtures.
- No production customer data in CI tests.
- No publishing public artifacts from workflows running untrusted pull requests if reports contain internal data.

## 15. Quick Troubleshooting

| Symptom | Common Cause | Action |
| --- | --- | --- |
| Gradle `build` passes yet no XML exists | Test task skipped or reports disabled | Check `build` task graph, `Test` reports config, and module |
| Gradle `verify` task does not exist | Project does not define that task | Use `check`/`build` or inspect plugins/custom tasks |
| Maven `verify` passes yet Failsafe reports missing | Failsafe goals unbound or no IT tests exist | Check Failsafe executions and naming patterns |
| Test reports appear only at root | Wrong module upload path/pattern | Use multi-module globs or inspect each subproject |
| Upload step skipped after test failure | Missing always-run condition | Add `if: always()` to the upload step |
| Job green despite test failures | `continue-on-error`/`ignoreFailures`/`fail-never` | Restore failure propagation |
| JUnit XML parser fails to read file | Malformed XML, schema mismatch, or wrong path | Inspect XML and publisher/parser versions |
| Zero tests discovered | Wrong naming, source set, engine, or filter | Check JUnit Platform, Surefire patterns, and test tasks |
| All tests skipped | Assumptions, conditions, profiles, or disabled tests | Inspect test annotations, profiles, and report reasons |
| Tests fail only in parallel | Shared state or resource collisions | Isolate DB/schemas/ports/files; reduce forks to confirm |
| Flaky tests | Races, timeouts, external services, or missing cleanup | Record seeds/order, remove shared state, use deterministic waits |
| Failsafe test fails yet `verify` passes | Plugin goals/policy unbound | Check `integration-test` and `verify` execution goals |
| Maven stops at first failing module | Default reactor fail-fast | Use `-fae` to run independent modules while preserving failure |
| Gradle stops early on failing module | Dependent tasks skipped | Use `--continue` to run independent tasks |
| Empty HTML report | No test results or report task did not run | Check XML and test execution first |
| Missing coverage report | JaCoCo agent/task unconfigured | Check `prepare-agent`, execution data, and report task |
| Report leaks secrets | Tests log environment or credentials | Redact output, fix logging, restrict artifact access |
| Build fails before tests | Configuration, dependency, or compile error | Expect no test reports; use the build log as evidence |

## 16. Practice Exercises with Answers

### Exercise 1 — Gradle verify

A Java project uses Gradle Wrapper; running `./gradlew verify` reports task not found. How do you fix it?

**Answer:** The Gradle Java plugin provides `check` and `build` by default, with no built-in `verify` lifecycle like Maven. Run `./gradlew check` or `./gradlew build`, or check for custom tasks/plugins if the project defines `verify`.

### Exercise 2 — Maven Integration Tests

`mvn test` passes, yet integration tests did not run. Why?

**Answer:** Maven `test` ends before the `integration-test` phase. Configure Failsafe goals and run `mvn verify`.

### Exercise 3 — Tests Fail, Reports Still Needed

Gradle tests fail and the report upload step is skipped. What change fixes this?

**Answer:** Add `if: always()` to the upload step while preserving the Gradle step's exit code/failure.

### Exercise 4 — Multi-Module Maven

Module A fails, yet you want independent Module B to still run tests and produce reports. What do you use?

**Answer:** `mvn verify -fae`/`--fail-at-end`. Maven still exits failed; modules depending on A may still be skipped.

### Exercise 5 — Green Build, Zero Tests

Can this be treated as tests passing?

**Answer:** Insufficient evidence. Check test counts in XML, source directories, engines, naming patterns, and filters. For modules requiring tests, enable fail-on-no-tests.

### Exercise 6 — XML and HTML

Do the two report formats replace each other?

**Answer:** Not completely. HTML suits human readers; XML suits CI parsers and automation. Keep both if the pipeline needs manual inspection and published test results.

### Exercise 7 — 100% Coverage

Can you conclude the application has no bugs?

**Answer:** No. Coverage only measures code paths/lines/branches executed per instrumentation; assertion quality, input space, concurrency, and requirements still require review.

### Exercise 8 — continue-on-error

Why shouldn't you enable `continue-on-error` on the test step?

**Answer:** It can stop the job from reflecting test failures required by release gates. Use a report upload step with `always()` to preserve evidence while keeping the build failed.

### Exercise 9 — Failsafe

Why does Failsafe split `integration-test` and `verify`?

**Answer:** So `post-integration-test` cleanup/teardown can run before failure is asserted in `verify`. Surefire unit tests normally fail directly in the `test` phase.

### Exercise 10 — Stale Reports

The CI log says Gradle task `test` was skipped as up-to-date, yet XML exists from an earlier run. How do you know reports belong to the current run?

**Answer:** Inspect task outcomes, timestamps, and artifact lifecycles; run `clean` in the job or wipe outputs via workspace isolation. Never upload stale reports from an old workspace/cache as test results of the current commit.

## 17. Checklist for CI Verification

- [ ] Gradle uses `check`/`build` per project convention; Maven uses `verify` when integration-test lifecycles are needed.
- [ ] CI invokes the committed Wrapper and uses the designated JDK/toolchain.
- [ ] JUnit Platform/Surefire/Failsafe are configured to discover the right tests.
- [ ] Build logs show which tasks, modules, and phases ran.
- [ ] Gradle XML/HTML reports are enabled and written to expected paths.
- [ ] Maven Surefire and Failsafe reports are collected separately.
- [ ] Multi-module report globs cover every required module and test task.
- [ ] Build/test failures still fail the job.
- [ ] Report upload/archiving runs under an `always`/`finally`/`post` condition.
- [ ] JUnit XML is published to the CI parser; HTML/TXT are retained for investigation.
- [ ] `ignoreFailures`, `continue-on-error`, and Maven `-fn` are never used to hide test failures.
- [ ] A policy exists for modules required to discover at least one test.
- [ ] Integration tests manage external dependencies and cleanup cleanly.
- [ ] Flaky tests are tracked and fixed at root cause; retries do not mask failures.
- [ ] Coverage and static-analysis reports are kept distinct from JUnit results.
- [ ] Reports contain no secrets or customer data and have proper retention and access controls.
- [ ] CI builds/tests the exact commit and never uploads stale reports from prior runs.

**Conclusion:** Gradle uses `check`/`build` for verification and builds; Maven uses the `verify` lifecycle to run both unit and bound integration-test goals. Gradle writes XML/HTML under `build/test-results` and `build/reports/tests`; Maven Surefire/Failsafe write under `target/surefire-reports` and `target/failsafe-reports`. CI must upload reports in a step that always runs after failures while keeping the build status failed so test errors are never hidden.

## 18. Official Documentation

- Gradle — Java Testing: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Java Plugin and lifecycle tasks: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Test task reports: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven Surefire Plugin: https://maven.apache.org/surefire/maven-surefire-plugin/
- Apache Maven Failsafe Plugin: https://maven.apache.org/surefire/maven-failsafe-plugin/
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
- JaCoCo — Gradle Plugin: https://www.jacoco.org/jacoco/trunk/doc/gradle.html
- JaCoCo — Maven Plugin: https://www.jacoco.org/jacoco/trunk/doc/maven.html
- GitHub Actions — Workflow artifacts: https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts
- GitHub Actions — Workflow syntax and status functions: https://docs.github.com/en/actions/learn-github-actions/expressions#status-check-functions

Report directory names and certain plugin options can vary by version and configuration. When applying these patterns, inspect the actual tasks/goals, open a generated report, and confirm CI uploads the exact files from that run.