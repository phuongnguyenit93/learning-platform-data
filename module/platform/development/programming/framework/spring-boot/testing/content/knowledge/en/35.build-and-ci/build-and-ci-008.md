# JUnit XML, HTML Reports, Logs, and Artifacts for Failure Investigation

## 1. Why Is Reading "BUILD FAILED" Not Enough When Tests Turn Red?

A Spring Boot pipeline can run thousands of tests. Gradle's `BUILD FAILED` line only tells you a task did not succeed; it fails to answer:

- Which exact test class and test case actually failed?
- Was it an **assertion failure**, an **exception/error**, a **skipped test**, or **zero tests executed**?
- Did the failure occur in business logic, during Spring `ApplicationContext` startup, while Testcontainers provisioned a database, or before Java tests even started due to compilation/dependency resolution?
- Does it reproduce only on one CI branch, one JDK, one OS, or under parallel test execution?
- In the logs, which request/correlation ID connects service layers to the failure?
- What stack traces, sanitized inputs, application logs, HTTP mock captures, screenshots, or container logs need to be preserved?
- Why did a rerun pass after an initial failure? Is it a flaky test, race condition, time dependency, shared resource, or a retry hiding a real bug?
- How do you preserve evidence **after a job fails**, instead of letting the pipeline abort before uploading?

This article belongs to **Build and CI**, covering **"JUnit XML, HTML Reports, Logs, and Artifacts for Failure Investigation"** in the **Spring Boot - testing** module. Examples use **Java 17+**, **Spring Boot 3.3.5**, **Gradle 8.x**, **JUnit Jupiter**, and a **GitHub Actions** workflow. The concepts apply equally to Jenkins and GitLab CI, though paths, UI, and upload syntax differ.

### Learning Objectives

1. Distinguish JUnit XML, HTML reports, console logs, and CI artifacts as complementary layers of evidence.
2. Know Gradle `Test` default output paths: `build/test-results/test/`, `build/reports/tests/test/index.html`, and binary test results.
3. Configure `useJUnitPlatform()`, `testLogging`, `reports.junitXml`, and `reports.html` without silencing diagnostic signals.
4. Read `<testsuite>`, `<testcase>`, `<failure>`, `<error>`, `<skipped>`, and captured stdout/stderr.
5. Build a Spring Boot project whose tests pass by default, with an intentional failure scenario **enabled only on demand** for report inspection training.
6. Write a Python standard-library script to summarize JUnit XML without leaking sensitive messages or bodies.
7. Use GitHub Actions `if: always()` + `actions/upload-artifact` to capture XML, HTML, and Gradle console logs on both green and red builds.
8. Preserve **failing exit codes** when piping through `tee` using `set -o pipefail`, never using `|| true` to fake CI success.
9. Distinguish test failures, build setup failures, skipped tests, missing reports, and stale reports.
10. Collect Spring logs, Testcontainers logs, request traces, and screenshots following least-privilege principles.
11. Investigate flaky/parallel/timeout failures with evidence instead of rerunning to erase the clue.
12. Configure retention, access controls, and redaction when storing logs/reports as artifacts.

**Scope limitation:** The sources in this article form an illustrative project you can build and run with a matching JDK and Gradle version. XML snippets and sample outcomes are **structural illustrations**, not live Gradle output captured during writing.

## 2. Four Key Types of Evidence

| Evidence | Produced By | Primary Purpose | Limitations |
| --- | --- | --- | --- |
| **JUnit XML** | Gradle `Test` or Surefire/Failsafe | Machine-readable case/fail/skip counts; identifies class/method and failure stacks | Not a single rigid universal spec; depends on producer/version |
| **HTML test report** | Gradle, Maven reporting plugins, or CI | Human-readable summary, class/method drill-down, stack traces, and output | Multi-file bundle with CSS/JS; downloading `index.html` alone breaks assets |
| **Console/build log** | Gradle/Maven, JVM, Spring Boot, test runner | Shows why dependency/compile/startup/test tasks failed, timestamps, warnings, exception chains | Can be huge; risks exposing secrets/PII if loggers are unchecked |
| **CI artifact** | GitHub Actions/Jenkins/GitLab uploader | Preserves **copies** of XML, HTML, logs, screenshots, dumps after job exit | Requires retention, permissions, encryption/redaction, and storage quotas |

**JUnit XML does not contain all logs.** Gradle may include `<system-out>` and `<system-err>` depending on configuration; other runners have different semantics. Conversely, console logs capture early build failures before JUnit starts—cases where no JUnit XML exists at all.

```text
./gradlew test
   |
   +-- Gradle build setup / Java compile / dependency resolution
   |      |
   |      +-- failure before Test execution -> console log is primary source
   |
   +-- Gradle Test task + JUnit Platform
          |
          +-- test results (binary data)
          +-- XML: build/test-results/test/TEST-*.xml
          +-- HTML: build/reports/tests/test/index.html
          +-- stdout/stderr + stack traces per configuration
                    |
                    v
              CI artifacts + human triage
```

## 3. Three Questions to Answer When a Job Turns Red

**Question 1: Did tests actually execute?**

If the build failed in `compileJava`, `compileTestJava`, plugin resolution, or an image pull, do not hunt for a `<failure>` in XML—there may be no test results. Start in the Gradle log and locate the **`FAILED` task**.

**Question 2: Did tests genuinely fail, or did reporting/CI mishandle the result?**

CI parsers can miscount skipped tests, choke on retry-specific XML tags, or scan only one module. A job can also look falsely green due to `|| true` or a `tee` pipeline lacking `pipefail`. Always verify **process exit code**, XML, and stack traces together.

**Question 3: Is the evidence sufficient to reproduce?**

An XML report naming a test method without JDK version, environment, fixtures, random seed, or correlation ID may not be enough. Preserve safe metadata: commit SHA, runner OS, JDK version, Gradle version, test task, reports, relevant logs, and sanitized artifacts.

## 4. Sample Project: Passing Tests Plus an Opt-In Failure

We build a small `PricingService`, use `@SpringBootTest` so Spring creates real beans, `@ParameterizedTest` for multiple cases, and `@EnabledIfSystemProperty` to **activate an intentional failure only during diagnostic runs**.

Layout:

```text
junit-report-investigation/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/report/
│   ├── ReportDemoApplication.java
│   └── PricingService.java
├── src/test/java/com/example/report/
│   └── PricingServiceTest.java
├── scripts/
│   └── summarize_junit.py
└── .github/workflows/
    └── test-reports.yml
```

**Demo rule:** running `gradle test` normally leaves the conditional failure **skipped**. Passing `-PdemoFail=true` triggers an intentional `assertEquals` mismatch; the Gradle task fails while still producing reports for the executed tests. Never commit the fail flag into default CI workflows.

### Why Gate the Intentional Failure Behind a Flag?

If a repo contains an unconditional failing `@Test`, learners cannot run a green baseline to verify CI setup. If the failure is always `@Disabled`, learners cannot inspect `<failure>` output. A project property cleanly separates **normal mode** from **incident-reproduction mode**.

## 5. Gradle: settings.gradle and build.gradle

### settings.gradle

```groovy
rootProject.name = 'junit-report-investigation'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // -PdemoFail=true is a Gradle project property.
    // Forward it explicitly to the JVM running JUnit.
    systemProperty 'demo.fail',
            providers.gradleProperty('demoFail')
                     .orElse('false')
                     .get()

    reports {
        junitXml.required = true
        html.required = true

        // Attach captured stdout/stderr per testcase when supported by CI.
        junitXml.outputPerTestCase = true

        // Demo prints no secrets; production must apply redaction.
        junitXml.includeSystemOutLog = true
        junitXml.includeSystemErrLog = true
    }

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat =
                org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL

        // Do not dump all stdout to console automatically.
        showStandardStreams = false
    }
}
```

### Explaining the Configuration

- `useJUnitPlatform()`: executes JUnit Jupiter. Without it, tests may not be discovered as expected.
- `spring-boot-starter-test`: brings Spring TestContext, JUnit Jupiter, AssertJ, and common test libraries.
- `junit-platform-launcher` in `testRuntimeOnly`: aligns JUnit Platform discovery/launching per Gradle compatibility guidance.
- `systemProperty 'demo.fail', ...`: forwards `-PdemoFail=true` from the Gradle JVM into the **test worker JVM**. Passing `-Ddemo.fail=true` to an arbitrary Gradle command does not propagate into forked test JVMs automatically.
- `reports.junitXml.required=true` and `reports.html.required=true`: ensure both reports are enabled; Gradle Java `Test` **enables both by default**.
- `outputPerTestCase=true`: associates captured stdout/stderr with individual testcases rather than only class level in XML.
- `includeSystemOutLog`/`includeSystemErrLog`: helpful for demo diagnostics, though they risk exposing sensitive output—see the security section.
- `testLogging.events`: logs pass/skip/fail events in the Gradle console.
- `TestExceptionFormat.FULL`: prints full test stack traces rather than truncated ones. It **differs** from Gradle CLI `--stacktrace`, which prints build/task exception stacks.
- `showStandardStreams=false`: avoids flooding console output. Logback/Log4j and Spring logging still need proper configuration/redaction; this flag is not a security control.

### Keep Default Report Paths Unless Needed

Gradle writes XML to `build/test-results/test/` and HTML to `build/reports/tests/test/index.html` by default. Keeping defaults simplifies CI integration. If you customize `reports.junitXml.outputLocation` or `reports.html.outputLocation`, update uploaders and parsers in lockstep.

## 6. Spring Boot Application Root

`src/main/java/com/example/report/ReportDemoApplication.java`:

```java
package com.example.report;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReportDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReportDemoApplication.class, args);
    }
}
```

The project uses `spring-boot-starter`, **with no web starter** and no datasource. Tests still use `@SpringBootTest(webEnvironment=NONE)` to load a Spring context without opening an HTTP port, DB, or external APIs. This keeps reports focused on JUnit and Spring startup rather than network flakiness.

### Why Not Just One Plain JUnit Test?

Plain JUnit fits pure utility logic. Since this module covers Spring Boot testing, `@SpringBootTest` illustrates two common failure layers: **Spring context startup** and **JUnit assertions**. The sample does not inject a broken context, yet the triage sections show how to tell them apart in logs.

## 7. PricingService: Real Logic and Safe Logging

`src/main/java/com/example/report/PricingService.java`:

```java
package com.example.report;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class PricingService {

    private static final Logger log =
            LoggerFactory.getLogger(PricingService.class);

    public long totalInCents(
            long unitPriceCents,
            int quantity) {

        if (unitPriceCents < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "price and quantity must be non-negative");
        }

        long amount = Math.multiplyExact(
                unitPriceCents, quantity);

        log.info(
                "pricing calculated quantity={} amountCents={}",
                quantity, amount);

        return amount;
    }
}
```

Logs use SLF4J structured placeholders rather than string concatenation, recording only quantity and amount—never tokens, customer names, authorization headers, or raw request bodies. Because it logs at `INFO`, output may appear in Gradle-captured stdout/stderr or console depending on logging config.

**Never assert verbatim timestamps or logger prefixes.** Logback patterns, timezones, and thread names vary across profiles and CI runners. When an event must be asserted, prefer **business state** or a properly configured test appender/`ObservationRegistry` rather than brittle regexes over full log text.

### Math.multiplyExact Can Throw

`Math.multiplyExact` throws `ArithmeticException` on `long` overflow. That is valid Java 17 behavior, though production code needing a domain exception (e.g., invalid amount) would design and test that explicitly. This article focuses on reporting rather than a complete pricing engine.

## 8. PricingServiceTest: Parameterized, Skipped, and Intentionally Failed

`src/test/java/com/example/report/PricingServiceTest.java`:

```java
package com.example.report;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInfo;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class PricingServiceTest {

    private static final Logger log =
            LoggerFactory.getLogger(PricingServiceTest.class);

    @Autowired
    PricingService pricing;

    @ParameterizedTest(
            name = "[{index}] price={0} quantity={1} expected={2}")
    @CsvSource({
        "125, 2, 250",
        "199, 3, 597",
        "0, 4, 0"
    })
    void calculatesExpectedTotals(
            long price,
            int quantity,
            long expected) {

        assertEquals(
                expected,
                pricing.totalInCents(price, quantity));
    }

    @Test
    @DisplayName("rejects negative quantities")
    void rejectsNegativeQuantity() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> pricing.totalInCents(125, -1));

        assertTrue(error.getMessage()
                .contains("non-negative"));
    }

    @Test
    void logsASafeDiagnosticEvent(TestInfo testInfo) {
        long total = pricing.totalInCents(75, 2);

        log.info(
                "test-check method={} scenario={} totalCents={}",
                testInfo.getTestMethod()
                        .orElseThrow()
                        .getName(),
                "normal-pricing",
                total);

        assertEquals(150L, total);
    }

    @Test
    @DisplayName("intentional diagnostic failure (opt in)")
    @EnabledIfSystemProperty(
            named = "demo.fail",
            matches = "true")
    void intentionalFailureForReportTraining() {
        long actual = pricing.totalInCents(125, 2);

        // Intentionally wrong: actual is 250, expected is 251.
        assertEquals(
                251L,
                actual,
                "diagnostic demo: expected amount mismatch");
    }
}
```

**Declared methods:** three standard `@Test` methods (two always enabled, one conditional) and one `@ParameterizedTest` with three invocations. More accurately: **4 test methods in source**, expanding to **6 potential test cases/invocations** during JUnit execution (3 parameterized cases, 2 always-enabled tests, 1 conditional test). Pass/fail/skip outcomes depend on `demo.fail` and execution success.

### Why Distinguish Method Count from Case Count?

A JUnit parameterized test produces multiple executions from **one** Java method. `@RepeatedTest` or `@TestFactory` produces even more. Reporters count **testcases**, not annotation counts; CI triage must read `tests`, `failures`, and `skipped` from actual outputs rather than counting annotations.

### Conditional Failure Only Runs When Enabled

Normally, `@EnabledIfSystemProperty(named="demo.fail",matches="true")` disables only the failure method. When `-PdemoFail=true` is forwarded by Gradle to the test JVM, JUnit runs the method and `assertEquals(251L,250L,...)` fails. This is a **training mechanism**, not an automatic production failure.

Do not `@Disabled` a test and expect `--tests` to run it; `@Disabled` still skips execution even when selected by Gradle filters. For conditional toggling, use conditional annotations or explicit tags/feature flags.

## 9. Running on macOS/Linux and Windows

If the repository already includes the Gradle Wrapper:

```bash
./gradlew clean test
./gradlew clean test -PdemoFail=true
./gradlew test --tests 'com.example.report.PricingServiceTest'
./gradlew test --tests 'com.example.report.PricingServiceTest.intentionalFailureForReportTraining' -PdemoFail=true
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat clean test -PdemoFail=true
.\gradlew.bat test --tests "com.example.report.PricingServiceTest"
```

If no Wrapper is present yet, use a compatible installed Gradle 8.x or generate the Wrapper per project conventions:

```bash
gradle clean test
gradle clean test -PdemoFail=true
```

**Note:** the project tree here lists only content files. Unless you generate/commit a Wrapper, `./gradlew` will not exist. Never mistake "command not found" for a JUnit failure.

### Useful Gradle Flags

| Command/Flag | When to Use | Notes |
| --- | --- | --- |
| `clean test` | Need fresh reports free of old outputs | Deletes `build/` before running |
| `--tests 'package.Class.method'` | Reproduce one testcase | Java method name may differ from display name |
| `--rerun-tasks` | Task marked `UP-TO-DATE` yet needs fresh run | Can be slow; not a fix for flakiness |
| `--stacktrace` | Inspect Gradle build/task failure stacks | Test assertions are clearer in HTML/XML |
| `--info` | Inspect Gradle task/classpath/startup details | Verbose; may expose sensitive info |
| `--debug` | Deep investigation with proper access | Very verbose; never upload casually |
| `--continue` | Keep running independent tasks after a failure | Overall build still fails; dependent tasks may skip |
| `--fail-fast` | Stop testing early on first failure | Report does not cover the full suite |
| `--no-daemon` | Clean process lifecycle in one-off CI | Does not directly alter report contents |
| `--console=plain` | Stable log format when piping to a file | Keeps stack traces and statuses intact |

When enabling the failure scenario, the **process exit code must be non-zero**. Turn off `-PdemoFail=true` before committing standard CI workflows. Never use `ignoreFailures=true` on critical tests just to turn a pipeline green; it hides regressions.

## 10. Real Gradle JUnit XML and HTML Output Paths

For a single-project Gradle Java build with the default `test` task:

```text
build/
├── test-results/
│   └── test/
│       ├── TEST-com.example.report.PricingServiceTest.xml
│       └── binary/
│           └── ... internal Gradle test result data ...
└── reports/
    └── tests/
        └── test/
            ├── index.html
            ├── classes/
            │   └── com.example.report.PricingServiceTest.html
            ├── packages/
            │   └── com.example.report.html
            ├── css/
            └── js/
```

This is a **typical layout**; exact CSS/JS filenames may vary across Gradle versions. **Output paths follow task names**: an `integrationTest` task writes JUnit XML and HTML reports to `build/test-results/integrationTest/` and `build/reports/tests/integrationTest/`.

### Do Not Upload Only index.html

`index.html` links to per-class/per-package pages plus CSS/JS assets. Uploading only the single HTML file without subdirectories leaves investigators with unstyled pages and broken links. Upload the **entire `build/reports/tests/test/` directory** and open `index.html` after downloading/extracting the artifact.

### What Is Binary Test Result Data For?

Gradle writes internal binary files to render and aggregate reports. They are **not JUnit XML** and are not a portable format recommended for CI parsers. If preserving binary results for official Gradle report aggregation, ensure Gradle versions match. For human/CI inspection, XML and HTML usually suffice.

## 11. JUnit XML Is a Pseudo-Standard, Not an Immutable Universal Schema

A Gradle XML file typically follows this structure:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite
    name="com.example.report.PricingServiceTest"
    tests="..."
    skipped="..."
    failures="..."
    errors="..."
    time="...">
  <testcase
      classname="com.example.report.PricingServiceTest"
      name="calculatesExpectedTotals(...)"
      time="..."/>
  <testcase
      classname="com.example.report.PricingServiceTest"
      name="intentionalFailureForReportTraining()"
      time="...">
    <failure type="..." message="...">
      ...stack trace...
    </failure>
  </testcase>
</testsuite>
```

**This is a schematic XML example**, with `...` standing for unknown attributes/stack traces; **it is not a real XML file from executing the sample**. Exact test counts, parameterized case names, timings, exception types, and stack traces must be read from generated XML. Never copy guessed numbers or messages into CI reports.

### Element Meanings

| Element/Attribute | Common Meaning | Caution |
| --- | --- | --- |
| `<testsuite>` | Group/class/suite with summary attrs | Producers vary in exact attributes emitted |
| `<testcase>` | One reported invocation | Parameterized/repeated tests emit multiple entries |
| `<failure>` | Assertion/test failure | `message` and text may expose sensitive data |
| `<error>` | Unhandled error/exception in runner or test | Some producers distinguish `<error>` from `<failure>` |
| `<skipped>` | Test did not run due to condition/disable/skip | Skipped does not mean passed |
| `<system-out>` | Captured standard output | Placement (suite vs. testcase) depends on config |
| `<system-err>` | Captured error output | May include stack traces or tokens |
| `time` | Execution duration reported by producer | Not an SLA; may exclude context startup |
| `tests`, `failures`, `errors`, `skipped` | Summary counters | Understand reruns, merges, containers, and producer |

Gradle describes this format as the **JUnit XML pseudo-standard**: widely supported by CI tools, yet lacking one unified schema across extensions. Never build parsers assuming optional attributes exist across every XML producer.

### A Failure May Not Be the Same Defect as Before

When a retry plugin re-runs tests, XML may contain multiple `<testcase>` executions or rerun/flaky elements depending on Gradle report options. Enabling `junitXml.mergeReruns` **changes only how the report is written** and **does not trigger retries**. A CI parser that ignores `<flakyFailure>` can treat the testcase as passed and hide the initial failure. When investigating flakiness, preserve raw XML and attempt metadata rather than trusting a green summary.

## 12. HTML Reports: Drilling Down by Class and Method

Open `build/reports/tests/test/index.html`. In a standard Gradle report, triage in order:

1. **Summary:** total tests/failures/ignored, duration, and success rate. Treat this as a summary of **the task and tests actually executed**, not a guarantee for the whole repo.
2. **Packages:** narrow down failing packages/modules, e.g., `com.example.report`.
3. **Classes:** open `PricingServiceTest`; focus on failed/error/skipped methods.
4. **Test case:** inspect the failure assertion message and stack trace; find the first failing line in your own code.
5. **Standard output/error:** check captured logs if enabled; do not blindly assume the first log line came from a single thread if tests ran concurrently.
6. **Correlate with commits:** identify which change introduced the failure rather than assuming every failure in that test class shares one cause.

With `@ParameterizedTest`, multiple rows share a Java method name while differing in parameters/display names. Check the case index, safe parameter values, and exception. When formats collapse method names, include non-PII contextual inputs in assertion messages.

### Why Avoid Machine-Parsing HTML?

HTML is a presentation format whose CSS and DOM can change across Gradle releases. CI dashboards should parse JUnit XML or structured result APIs; humans use HTML to drill down. For aggregate dashboards, use standard parsers or CI integrations rather than regexing HTML.

## 13. Console Logs: Spot the First Error and Boundary

Three log streams interleave during Gradle runs:

- **Gradle build logs:** tasks, dependency resolution, compiler errors, toolchain/configuration failures.
- **Spring Boot app/test logs:** `ApplicationContext` startup, bean wiring, profiles, Hibernate/JDBC, HTTP clients, Logback/SLF4J.
- **Test stdout/stderr & stack traces:** assertions, exception chains, test framework events, custom `println` calls.

A noisy log may contain hundreds of unrelated `WARN` lines. On failure, check first whether `:test FAILED` or `:compileTestJava FAILED` occurred. If tests ran, open the class/method report and look for the **first meaningful `Caused by`** or assertion line rather than the final `BUILD FAILED` footer.

### Case: Spring Context Failed to Load

Messages like `Failed to load ApplicationContext`, `BeanCreationException`, `UnsatisfiedDependencyException`, or `NoSuchBeanDefinitionException` point to a **startup/wiring failure**, not a business assertion. Check active profiles, property binding, required dependencies, migrations, port collisions, and conditional auto-config. `@SpringBootTest` caches contexts; one root startup failure can fail many test methods in a row. Do not file each cascading failure as a separate defect.

### Case: Timeouts or Testcontainers

`ContainerLaunchException`, Docker socket errors, image pull failures, DB connection refused, or Kafka partition assignment timeouts indicate infrastructure/fixture errors before assertions even run. Inspect container logs, image versions, resource limits, and readiness checks. Never assume transaction logic is broken just because `@SpringBootTest` failed to create a `DataSource`.

## 14. Capturing Console Logs While Preserving Exit Codes

Linux/macOS Bash:

```bash
set -o pipefail
./gradlew --no-daemon clean test --stacktrace \
  --console=plain 2>&1 | tee gradle-test-console.log
```

**`set -o pipefail` is critical.** Without it, the pipeline exit status comes from `tee`; Gradle can fail while `tee` writes successfully and exits 0. With `pipefail`, Gradle failures still fail the step while preserving logs for downstream uploaders.

### Never Write Logs into a Directory Wiped by clean

Running `./gradlew clean test` while piping to `tee build/diagnostics/gradle.log` risks having `clean` delete `build/` while `tee` holds the file open, losing or breaking the log. In the example, `gradle-test-console.log` sits at the **project root**, outside `build/`.

### Never Fake Green Builds

Wrong:

```bash
./gradlew test || true
```

Wrong when it hides failures:

```bash
./gradlew test 2>&1 | tee test.log
# Without pipefail: Gradle exit status may be lost.
```

An upload step can use `if: always()`, yet the **test execution step must retain its failing exit code**. If workflow policy needs multiple independent test tasks to continue after a failure, use Gradle `--continue` (which still exits non-zero) or separate CI jobs per task.

### Windows PowerShell

PowerShell 5.1 and PowerShell 7 handle native pipelines and `$LASTEXITCODE` differently, so do not copy Bash `set -o pipefail` verbatim to PowerShell. When logging on Windows agents, use a dedicated wrapper that tees output and **returns the exact native process exit code**, and test it against an intentionally failing command first. Simplest for the demo: invoke `.\gradlew.bat test` directly and rely on CI runner logs.

## 15. Small Script to Summarize JUnit XML

Most CI systems ship JUnit report parsers; when you want a quick local/CI summary without extra libraries, Python's standard library suffices. The script below scans `TEST-*.xml` under Gradle's result directories, counts `<testcase>` entries, and tallies failures/errors/skips. It **never prints exception messages, raw logs, or stack traces** to avoid leaking sensitive data in CI summaries.

Create `scripts/summarize_junit.py`:

```python
#!/usr/bin/env python3
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

result_root = Path("build/test-results")
files = sorted(result_root.rglob("TEST-*.xml"))

if not files:
    print("No JUnit XML files found under build/test-results")
    print("Check whether the test task actually executed.")
    sys.exit(2)

total = 0
passed = 0
failed = 0
skipped = 0
failed_names = []

for path in files:
    try:
        tree = ET.parse(path)
    except ET.ParseError as error:
        print(f"Malformed report: {path}: {error}")
        sys.exit(2)

    for case in tree.iter("testcase"):
        total += 1
        failure = case.find("failure")
        error = case.find("error")
        skip = case.find("skipped")

        if failure is not None or error is not None:
            failed += 1
            classname = case.get("classname", "unknown")
            name = case.get("name", "unknown")
            failed_names.append(f"{classname}#{name}")
        elif skip is not None:
            skipped += 1
        else:
            passed += 1

print(f"XML files: {len(files)}")
print(f"Test cases: {total}")
print(f"Passed: {passed}")
print(f"Failed or error: {failed}")
print(f"Skipped: {skipped}")

if failed_names:
    print("Failed cases:")
    for name in failed_names:
        print(f"  - {name}")

# Informational report; the Gradle test step retains gate status.
# If XML files are missing or malformed, the script exits 2.
```

### What the Script Does and Does Not Do

- Uses `ElementTree`, never regexes on XML.
- Counts actual `<testcase>` elements inside XML files rather than annotations.
- Distinguishes `failure`, `error`, and `skipped` via XML child elements.
- Exits with code 2 when files are missing, signaling an early build failure.
- Never prints exception bodies, secrets, or stdout.
- **Does not** decide build pass/fail: the Gradle test step remains the CI gate, while the script aids triage.
- Scans `build/test-results` of the **current module** only; multi-project builds must pass root paths or run per subproject.
- If reports include `<flakyFailure>`, retry metadata, multiple runs, or custom producers, this minimal summary is insufficient—use a full-featured CI parser.
- Guard against double-counting if duplicate XML files from multiple tasks/shards sit under the same root.
- For untrusted testcase names, sanitize/bound printed strings; this demo uses no external user input for test names.

Run command:

```bash
python3 scripts/summarize_junit.py
```

**Never use the script to override a CI gate.** If Gradle fails while the summary prints `Failed or error: 0`, the failure likely occurred in `compileTestJava`/Docker/setup, or XML only covers a subset; CI must stay red.

## 16. GitHub Actions: Retaining Reports Even on Failure

Create `.github/workflows/test-reports.yml`:

```yaml
name: Spring test reports

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  tests:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Run tests, retain Gradle exit status
        shell: bash
        run: |
          set -o pipefail
          chmod +x ./gradlew
          ./gradlew --no-daemon clean test --stacktrace \
            --console=plain 2>&1 | tee gradle-test-console.log

      - name: Summarize JUnit results
        if: ${{ always() }}
        shell: bash
        run: |
          set -o pipefail
          python3 scripts/summarize_junit.py | tee junit-summary.txt

      - name: Upload test diagnostics
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: junit-diagnostics-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            build/test-results/test/
            build/reports/tests/test/
            gradle-test-console.log
            junit-summary.txt
          if-no-files-found: warn
          retention-days: 7
```

**This is a minimal workflow for a repository with the Gradle Wrapper.** Commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties`, and a valid Wrapper JAR before running it. `chmod +x ./gradlew` sets the executable bit and will not create a missing Wrapper. Never commit `-PdemoFail=true` into the default workflow.

### Key Details in the YAML

- `actions/checkout` fetches the source and Gradle Wrapper.
- `actions/setup-java` sets up JDK 17.
- `gradle/actions/setup-gradle` manages Gradle caching and CI integration; avoid configuring duplicate caches in multiple actions simultaneously.
- `set -o pipefail` preserves Gradle's exit code across `tee`.
- `2>&1 | tee ...` captures both stdout and stderr in the console log for debugging stacks/errors.
- `if: always()` ensures summary and upload steps **are still evaluated after test failure**; hard runner kills or cancellations can still interrupt uploaders.
- `actions/upload-artifact@v4` bundles directories and logs into one artifact.
- Naming with run ID and attempt prevents collisions across retries and keeps CI iterations traceable.
- `if-no-files-found: warn` keeps a compile failure (where XML/HTML were never created) from causing a secondary uploader failure. The console log remains primary.
- `retention-days: 7` is an example; org/enterprise policies may enforce shorter limits.
- `permissions: contents: read` applies least privilege for a simple workflow.

**You are not locked into `upload-artifact@v4` forever.** That is the current major release in GitHub Actions docs; when upgrading majors, check release notes/compatibility and consider pinning immutable commit SHAs per supply-chain policy.

### What Happens When Triggering the Intentional Failure?

If a separate **diagnostic workflow** passes `-PdemoFail=true`, the `test` task exits non-zero on the assertion; the test step turns red. The `if: always()` steps still summarize and upload XML/HTML/logs. The overall job status **remains failed**. You do not need `continue-on-error: true` on the test step just to run the uploader.

### What Happens on a Compile Failure?

`compileTestJava` or dependency resolution fails before tests run: `build/test-results/test/` does not exist. The summary script exits 2 (writing diagnostic text to `junit-summary.txt`), and the uploader warns on missing paths while still saving `gradle-test-console.log` if created. Read the compile error first; never interpret "No JUnit XML" as a failing test method.

## 17. A GitHub Actions Artifact Is an Archive, Not a JUnit Parser

After the workflow finishes, **Actions → workflow run → Artifacts** lets you download the bundle. Download and extract the full tree, then open `build/reports/tests/test/index.html` locally in a browser. Security policies often block viewing HTML directly in CI UIs; inspect locally in a browser.

`upload-artifact` **does not render test pass/fail charts** from XML. For PR annotations, check runs, or dashboards, integrate a dedicated JUnit-parsing action/plugin and review its permissions on forked PRs/untrusted code. Never grant `checks: write` or broad repository tokens to a simple artifact-upload workflow.

### Retention and Access Controls

Reports may expose stack traces, filesystem paths, environments, headers, or test inputs. Set artifact retention considering:
- data sensitivity;
- triage window needed by the team;
- storage quotas and costs;
- compliance and data residency;
- download permissions across teams/external collaborators;
- expiration, purging, and external sharing rules.

**Never upload `.env`, credential files, Docker configs, kubeconfigs, full heap dumps, or raw production data.** If a dump is strictly required, sanitize it and store it under tight ACLs; never zip up all of `build/` out of laziness and leak build secrets.

## 18. Maven Equivalents: Surefire and Failsafe

While the runnable demo uses Gradle, Maven projects write reports to different paths:

| Tool | Typical Report Path | Purpose |
| --- | --- | --- |
| Gradle `test` | `build/test-results/test/` | Test task XML |
| Gradle `test` HTML | `build/reports/tests/test/` | Human-readable |
| Maven Surefire | `target/surefire-reports/` | Unit tests; XML and `.txt` summaries |
| Maven Failsafe | `target/failsafe-reports/` | Integration tests; typically `integration-test`/`verify` phases |
| Jenkins JUnit publisher | Configured glob | CI test trends/dashboards |
| GitLab test report | `artifacts:reports:junit` | Merge request / pipeline test UI |

Maven `surefire-reports` contains `TEST-*.xml` and per-class `.txt` files; it **does not** emit Gradle's `build/reports/tests/test/index.html` structure by default. Failsafe runs integration tests across phases and requires `verify` to fail the build when ITs fail. Never point a Surefire glob at Failsafe and report "No tests" while ITs actually ran.

### Never Apply One Pattern Blindly Across Build Tools

If CI publishes `target/surefire-reports/TEST-*.xml`, adding a Gradle task will not feed that dashboard. Always match producer and output path per module/task. When using specialized Surefire JSON or JUnit Platform launchers, inspect actual paths and formats instead of guessing.

## 19. Multi-Module Builds and Multiple Test Tasks: Avoiding Missed Failures

In a Gradle multi-project build:

```text
root/
├── service-a/build/test-results/test/TEST-*.xml
├── service-a/build/reports/tests/test/
├── service-b/build/test-results/test/TEST-*.xml
├── service-b/build/test-results/integrationTest/TEST-*.xml
└── service-b/build/reports/tests/integrationTest/
```

The single-module workflow in section 16 uploads only root `build/...`. Across multiple modules, use appropriate globs, such as:

```yaml
path: |
  **/build/test-results/**/TEST-*.xml
  **/build/reports/tests/**
  gradle-test-console.log
```

This is a **path snippet**, not a complete workflow. Verify actual glob matching in CI and preserve relative paths so identical class names across modules remain distinguishable.

### New Test Tasks Need New Report Paths

When you define a separate `integrationTest` task, outputs live in `build/test-results/integrationTest`, not `.../test`. Never upload only `**/test-results/test` and claim the integration suite is green. When Gradle reports `:module:integrationTest FAILED`, read that exact task's report.

### Aggregated Reports

Gradle provides `TestReport` and the **Test Report Aggregation Plugin** to combine results across multiple `Test` tasks/projects when variants are wired properly. Never hand-concatenate multiple `index.html` files; relative paths, CSS, and links will break. Keep raw XML intact for independent CI parsing.

### Matrix Builds and Artifact Names

In a JDK/OS matrix workflow, give each job/variant a **unique** artifact name, for example:

```yaml
name: reports-${{ matrix.os }}-jdk${{ matrix.java }}-${{ github.run_id }}
```

This is a **snippet**, valid only when `matrix.os` and `matrix.java` are declared. With `upload-artifact@v4`, multiple jobs must not write into the **same immutable artifact name**; give each variant its own artifact or use a supported merge workflow.

## 20. Clarifying Failed, Error, Skipped, and Aborted

JUnit Jupiter defines several test outcomes:

- **Successful:** test case ran and assertions passed.
- **Failed:** assertion/test execution threw a failure.
- **Aborted:** test halted via an assumption (`Assumptions.assumeTrue`) or condition; reporters may record this as skipped/aborted depending on format.
- **Disabled/Skipped:** test was excluded by `@Disabled`, non-matching `@EnabledIfSystemProperty`, or filters; never proves logic is valid.
- **Not discovered / not executed:** JUnit Platform never found it, Gradle filtered it out, or compilation failed first; may leave no `<testcase>` entry at all.

Thus **0 failed tests does not mean the full suite ran**. Monitor total test counts, skipped counts, deltas against baseline, and which tasks actually executed.

### When Test Discovery Returns 0

Verify:
- Is `useJUnitPlatform()` enabled?
- Is the Jupiter engine on the test runtime classpath?
- Are test classes/methods inside the Gradle test source set?
- Does `--tests` match the exact class/method?
- Are tests assigned to tasks other than `test`?
- Are tests `@Disabled` or gated by conditions?
- Are unintended `includes`/`excludes`/tags active?
- Did the build abort in compilation or integration setup?

A "green" pipeline running 0 tests is a CI policy bug to detect, not an achievement.

## 21. What Safe Logs Should Include for Fast Investigation

A clean, searchable log line should identify:

- `event=...` or operation name.
- `correlationId`/`traceId` or a safe test run ID (never a secret).
- `outcome`: success/error/timeout/rejected.
- Logical `dependency` name (low cardinality).
- `attempt` number if retried.
- `elapsedMs` or timing metrics from real measurements.
- Exception class and stack trace on important errors.
- Test class/method/run ID in test infrastructure logs.
- Environment: app version, JVM version, active profiles, and CI shard (safe metadata).

**Never use emails, raw JWTs, Authorization headers, passwords, customer payment data, or full request bodies as correlation IDs.** In metrics, avoid high-cardinality user/order ID tags. Keep retention, ACLs, and redaction aligned with org policy.

### Tying Logs to One Test Method

`outputPerTestCase=true` in JUnit XML attaches test stdout/stderr per testcase for supporting parsers. However, when tests spawn worker threads or HTTP servers, background logs can arrive after the method returns or in another process. Do not assume Gradle capture assigns every async log line to the right method.

In Spring Boot integration tests, attach test-specific correlation IDs to events/requests, await async completion with timeouts, and assert business outcomes before finishing. Never use `Thread.sleep` as sloppy log synchronization.

## 22. When to Retain Artifacts Beyond JUnit XML/HTML

| Test Type | Valuable Extra Artifacts | Notes |
| --- | --- | --- |
| Spring MVC / MockMvc | Safe request/response summaries, `MvcResult` diagnostics | Redact headers/bodies |
| Spring WebFlux | `StepVerifier` failure traces, filtered logs | Avoid dumping sensitive Reactor Context |
| Testcontainers PostgreSQL | Container logs, DB version, SQL migration error context | Never upload full DBs or credentials |
| Kafka / RabbitMQ | Test-owned topic/group/queue names, sanitized broker/listener logs | Do not wipe shared topics just to "clean up" |
| REST client | MockWebServer/WireMock request journal, status/timing | Redact Authorization and cookies |
| Browser / E2E | Screenshots, traces, short recordings | Blur PII, strip access tokens |
| Performance | Histograms, samples, JVM GC logs | Never treat perf checks as plain JUnit thresholds |
| Flaky / concurrent | Thread dumps, async state, seed, shard metadata | Dumps may reveal memory/path details |
| Migration / schema | Flyway/Liquibase logs, schema revision | Never store production dumps |
| Security / auth | Redacted error codes/statuses, audit event IDs | Never store raw secrets |

### Collecting Testcontainers Logs

When running a `PostgreSQLContainer`/Kafka container in a dedicated test environment, capture `container.getLogs()` on failure or stream via a log consumer. **Never** upload raw logs from a shared production database, and do not assume container logs contain full business error state. Filter by instance ID / test run and cap sizes rather than dumping unlimited output.

### Screenshots and Browser Traces

UI tests can save screenshots/traces on failure. Store them per test ID and upload via `if: always()`. Ensure screenshots never display live tokens, private customer data, private locations, or payment details; use synthetic fixtures, masking/redaction, and artifact ACLs.

### Heap Dumps and Thread Dumps

Thread dumps are invaluable for deadlocks and timeouts; heap dumps are highly sensitive because they contain in-memory credentials and user data. Collect them only when authorized and store in restricted channels rather than public PR artifacts.

## 23. Classifying Root Cause by Where Failure Starts

| Symptom | First Suspect | Primary Source to Read |
| --- | --- | --- |
| `:compileJava FAILED` | Java syntax/toolchain/dependencies | Gradle console log |
| `:compileTestJava FAILED` | Test code/imports/API mismatch | Gradle console log |
| `:test FAILED` + assertion | Wrong business assertion | JUnit XML/HTML |
| `Failed to load ApplicationContext` | Spring bean/config/profile/setup | XML stack + Spring logs |
| `ContainerLaunchException` | Docker image/network/container lifecycle | Console + container logs |
| `BindException Address already in use` | Fixed port / shared resource | Console + test setup |
| `SocketTimeoutException` | Slow downstream / network | App/HTTP mock logs + cause chain |
| `AssertionFailedError expected/actual` | Input, value, assertion | HTML testcase |
| `TimeoutException` in async test | Await signal never completed | Test trace + executor/event logs |
| Empty JUnit XML on failed build | Tests never ran or wrong report path | Build log/tasks |
| Skipped count spiked | Conditions, tags, filters | XML plus build configuration |
| CI green yet logs show exception | Swallowed exception or non-gating task | Test logic / Gradle exit status |
| Fails only in full suite | Shared state/parallelism/order/flakiness | Historical artifacts, run ID, seed |

**Never treat raising timeouts or adding retries as a first fix before finding the cause.** Raising a timeout from 5s to 30s will not cure a deadlock; it only slows CI down.

## 24. Ten-Step Failure Investigation Workflow

1. Check **job status + commit SHA + JDK/Gradle versions**, confirming the test step actually returned non-zero and was not masked.
2. Locate the first **failing Gradle task**. If tests never ran, read the console log rather than waiting for XML.
3. Download the artifact containing **all XML/HTML/logs**, not just a screenshot of the last red line.
4. Open HTML `index.html` and drill into the failing class/method; separate assertion failures from errors/setup failures.
5. Inspect XML: `classname`, `name`, `failure`/`error`/`skipped`, invocation counts, and stacks.
6. Walk down to the first meaningful `Caused by` in the exception chain; separate Spring startup from assertions and external dependencies.
7. Correlate logs with test inputs/outputs using correlation/run IDs—never log secrets.
8. Reproduce the exact test method/parameters/filters via `--tests` with matching JVM/profile/config; add `--rerun-tasks` to avoid stale up-to-date skips.
9. Re-run across **the full suite or parallel shard** if it only fails under shared resources; a passing single-test run does not disprove a race.
10. Document root cause, retain evidence, add a regression assertion, and only then consider bounded retry/quarantine with issue tracking.

### Why Download Artifacts Before Rerunning?

A rerun may turn temporarily green and overwrite clues about races, temp files, failing container logs, or timing. Grab the first-failure snapshot first, then reproduce. Since CI artifacts expire after a few days, download them within the retention window.

## 25. Flaky Tests and Retries: Avoid False Green Signals

A flaky test changes outcome across runs **when code and inputs are supposedly identical**. Common causes:

- Shared database/schema/queue/cache or static mutable state.
- `Thread.sleep` instead of synchronization/bounded awaits.
- Uncontrolled clocks/timezones or random seeds.
- Test execution order or parallel scheduling.
- Fixed port numbers or hardcoded directories.
- External networks/providers.
- CI resource exhaustion.
- Mismatch between Spring TestContext cache and container lifecycles.
- Undeclared inter-test dependencies.
- Browser animations/timings and nondeterministic selectors.

### Retry Policy

A retry plugin can help gather diagnostic signal, yet **never fixes a defect**. Retain:
- attempt count;
- first failure message/stack;
- record of pass-on-retry cases;
- seed/shard/environment;
- issue tracking and flakiness rate.

If enabling Gradle `junitXml.mergeReruns=true`, ensure your CI JUnit parser understands `<flakyFailure>`; not all parsers display rerun failures. An XML file appearing "green" because the parser ignored unknown rerun tags hides regressions.

### Quarantine Must Be Transparent

If an integration test is temporarily excluded due to a broken environment, record the ticket, owner, deadline, and interim compensating coverage. Never leave `@Disabled`/`ignoreFailures` indefinitely just for a green dashboard.

## 26. Keeping Sensitive Data Out of Reports

JUnit XML/HTML can expose:

- AssertJ/JUnit expected/actual values.
- Full SQL queries and bound parameters if verbose logging is enabled.
- HTTP request/response headers and bodies.
- JWTs, session cookies, passwords, and API keys in stack traces/logs.
- Local filesystem paths or hostnames.
- Screenshots/traces of authenticated UIs.

Best practices:

1. Use **synthetic test data**, never production customer records.
2. Disable verbose HTTP/SQL parameter logging by default on public fork CI.
3. Redact `Authorization`, `Cookie`, `Set-Cookie`, credentials, and PII before writing files.
4. Keep secrets out of assertion messages, `@DisplayName`, testcase parameters, and artifact filenames.
5. Restrict artifact download permissions per repo/org policy; watch forked PR triggers.
6. Set finite retention; never keep artifacts forever.
7. Never upload full home directories, `.env`, kubeconfigs, Docker credentials, or cloud credentials.
8. Consider limiting `includeSystemOutLog`/`ErrLog` if tests risk printing sensitive data; if disabled, retain sanitized logs via a controlled channel.
9. Enforce file size caps on dump collection to avoid gigabyte logs slowing or breaking uploads.
10. When sharing with vendors, build a dedicated sanitized bundle rather than forwarding raw CI artifacts.

### Redact Before Upload, Not After

Once a secret enters a console log and is uploaded in an artifact, scrubbing a downloaded copy does not clean what CI already stored. Prevent at the source: avoid printing secrets, keep fixtures clean, apply log filters, and enforce scanners/retention. If a real secret leaks, rotate/revoke the credential per incident response rather than merely deleting the artifact link.

## 27. Never Report "Tests Passed" Without Evidence

Accurate statements:

- "Wrote 4 methods and 6 potential invocations in source; **JUnit has not been run yet**."
- "Gradle `test` executed; XML reports N cases, F failures, S skipped"—only when reading actual generated reports.
- "Build failed in `compileTestJava`; no JUnit XML was generated."
- "Artifact upload succeeded"—only after GitHub Actions or the plugin confirms it.
- "Upload step is configured with `if: always()`, though a hard runner kill can still prevent upload."

False statements:

- "17 tests PASSED" just from counting 17 `@Test` annotations.
- "0 failures means zero bugs" when all tests were skipped or undiscovered.
- "Artifacts saved" right after writing YAML before any workflow ran.
- "XML proves containers work" if setup skipped due to missing Docker.
- "Full Gradle suite passed" when only one method ran via `--tests`.
- "CI green" when `|| true` or `tee` masked a non-zero exit code.

**This Knowledge article did not execute Gradle or GitHub Actions live.** Commands, expected behaviors, and report layouts are guides for reproduction; actual PASS status depends on running in the reader's environment.

## 28. Optimizing Triage Time and Artifact Costs

Avoid uploading needlessly:
- all of `build/` (class files and caches) when only test results are needed;
- thousands of raw HTTP bodies;
- screenshots for every step of every passing test;
- Docker images/dumps;
- unredacted debug runner logs.

Sensible pattern:
- Keep raw JUnit XML and HTML when runs fail or when tracking trends.
- Keep one `--console=plain` console log.
- Collect extra sanitized logs/traces/screenshots **only on failure**.
- Tag artifact names with run ID, CI attempt, and module/task.
- Keep retention short on PRs and longer on release/regression investigations per policy.
- Save storage with compression, file size limits, and cleanup.
- Standardize on one CI test-report aggregator instead of divergent per-module dashboards.

If oversized artifacts cause the upload step to fail, uploader errors can obscure the underlying test failure. Set file limits, size warnings, and separate unit/integration/E2E artifact bundles.

## 29. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Build fails without XML | Compile/dependency/setup failed before `Test` | Read Gradle console log |
| CI reads 0 tests even though Gradle ran | Wrong report glob/task/module | Check `build/test-results/<task>` |
| HTML `index.html` lacks styling | Downloaded only `index.html`, missing CSS/JS | Upload entire directory |
| Tests failed, upload step skipped | Missing `if: always()` on uploader | Add `always()` for diagnostics |
| Gradle failed, CI step green | `tee` missing `pipefail` or `|| true` | Preserve exit status |
| Testcase name differs from method | `@DisplayName` / parameterized invocations | Match XML classname/name/display |
| "Skipped" counted as "passed" | Broken CI dashboard aggregation | Report explicit counts |
| Report still shows old failures | `UP-TO-DATE`, stale artifacts, missing `clean` | `clean test` or `--rerun-tasks` |
| Failure only in a subproject | Uploader scans only root `build/` | Use multi-module globs |
| Failsafe ITs missing from dashboard | Dashboard watches only Surefire paths | Add `failsafe-reports` |
| XML parse error | Partial/truncated report, mismatched producer | Keep raw XML; check task lifecycle |
| Stack trace truncated | Short test logging format | `TestExceptionFormat.FULL`, HTML |
| Logs contain tokens | Verbose HTTP/SQL logging | Redaction, synthetic fixtures |
| Huge XML files | Excessive captured stdout | Output caps / log levels |
| Flaky pass-on-retry "hides" errors | Rerun merge / incompatible parser | Keep attempt logs/retries |
| `upload-artifact@v4` matrix collision | Multiple jobs sharing artifact name | Unique per-matrix names |
| Missing Gradle Wrapper | Wrapper files not committed | Generate/commit Wrapper or use installed Gradle |
| XML shows 1 failure yet Gradle passes | `ignoreFailures`/`continue-on-error`/exit masking | Fix pipeline gate |
| JUnit shows 0 failures yet app errored | Swallowed exception, weak assertions | Add business outcome assertions |
| Binary test-results unreadable | Gradle internal format | Use XML/HTML for triage |
| Report finished yet uploader canceled | Runner/job hard-killed | Check retention/cancellation policy and upstream logs |
| CI uploads only on green runs | Default `if: success()` | Switch diagnostics to `if: always()` |

## 30. QA Checklist for a Spring Boot Pipeline

- [ ] Can JDK/Gradle/Spring Boot/JUnit versions be identified from build logs?
- [ ] Does JUnit Jupiter run via `useJUnitPlatform()`?
- [ ] Does the `Test` task execute tests rather than silently discovering 0?
- [ ] Are both JUnit XML and HTML reports enabled?
- [ ] Are report paths from all `Test` tasks and subprojects uploaded?
- [ ] Does `testLogging` show failed tests and useful exception details?
- [ ] Do console logs preserve exact exit codes across `tee` pipes?
- [ ] Do summary and upload diagnostic steps run on failure (`if: always()`)?
- [ ] Are `|| true` and `ignoreFailures` absent from required gates?
- [ ] Do artifacts keep the full HTML directory, not just `index.html`?
- [ ] Does the JUnit XML parser support the producer format and reruns?
- [ ] Are baseline test/skip counts tracked to detect missing coverage?
- [ ] Do assertion messages help locate domain failures without leaking secrets?
- [ ] Are test failures distinguished from Spring context, Docker, and compile failures?
- [ ] Do logs carry safe correlation IDs, test run IDs, and shard metadata?
- [ ] Is unrestricted debug logging disabled in public CI?
- [ ] Do uploads have defined retention and access controls?
- [ ] Are test fixtures free of PII and production secrets?
- [ ] Do extra artifacts collect only targeted test outputs rather than the entire workspace?
- [ ] Are matrix artifact names distinct per OS/JDK/variant?
- [ ] Do flaky retries preserve first-failure evidence?
- [ ] Are canceled/killed CI runs flagged as insufficient evidence?
- [ ] After fixing a bug, is a regression test added to prevent recurrence?

## 31. Hands-on Practice Exercises

1. Create the project files and run `gradle clean test`.
2. Locate `build/test-results/test/TEST-...xml` and `build/reports/tests/test/index.html`; open summary and class pages.
3. Pass `-PdemoFail=true`, re-run, and inspect expected vs. actual in the report.
4. Run `intentionalFailureForReportTraining` alone using `--tests` with the fail flag.
5. Run `summarize_junit.py` and compare its counts with HTML; verify skipped counts.
6. Temporarily remove `useJUnitPlatform()` in a sandbox, observe build behavior, then restore it.
7. Disable `reports.html.required` and see what disappears from artifact uploads.
8. Toggle `outputPerTestCase` and compare where stdout appears in XML.
9. Turn off `includeSystemOutLog` and explain the sensitive-data trade-off.
10. Pipe a failing Gradle run into `tee` with and without `set -o pipefail`, checking exit codes.
11. Add a `@Disabled` test; check skipped counts rather than counting it as passed.
12. Add a `@ParameterizedTest` with more cases and compare testcase counts to annotation counts.
13. Introduce an intentional compile error in a sandbox and observe why no fresh XML appears after `clean`.
14. Set up the GitHub Actions workflow in a test repository and verify artifacts on a failed run.
15. Give a workflow two JDK matrix variants with unique artifact names per variant.
16. Add a Gradle `integrationTest` task and include its report paths in the uploader.
17. Trigger a Spring context startup failure on a dedicated branch and practice reading `Caused by`.
18. Add MockWebServer/WireMock in an integration test and collect a sanitized request journal on failure.
19. Create a flaky test using shared static state in a sandbox; compare single `--tests` vs. full suite.
20. Experiment with the Gradle retry plugin in a sandbox and compare raw failure logs with `mergeReruns`.
21. Set a short `retention-days` on PRs and check whether org policies override it.
22. Inspect the downloaded artifact zip to confirm no tokens, credentials, or customer data are present.
23. Write a team triage checklist: task, class, case, stack, environment, correlation, reproduction.
24. After fixing a bug, run the full suite and check actual executed/skipped/failed counts in CI.

## 32. Authoritative References

- [Gradle User Guide — Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): Java `Test` task, JUnit XML/HTML report paths, logging, `outputPerTestCase`, `TestReport` aggregation, XML rerun semantics.
- [Gradle DSL — Test](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): `useJUnitPlatform`, reports, `testLogging`, filters, and fail-fast.
- [Gradle DSL — JUnitXmlReport](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.JUnitXmlReport.html): `includeSystemOutLog`, `includeSystemErrLog`, `outputPerTestCase`, and `mergeReruns`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, Spring context/slice test semantics.
- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.0/user-guide/): `@Test`, `@ParameterizedTest`, `@EnabledIfSystemProperty`, and test discovery.
- [GitHub Docs — Store and share data with workflow artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data): uploading/downloading artifacts, retention.
- [GitHub actions/upload-artifact](https://github.com/actions/upload-artifact): `if-no-files-found`, `retention-days`, and major-version behavior.
- [GitHub Docs — Expressions and status check functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions): `always()` and conditional steps.
- [Maven Surefire Reports](https://maven.apache.org/surefire/maven-surefire-plugin/examples/reporting.html): Surefire XML/text reports.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): `integration-test`/`verify` lifecycle.
- [JUnit Platform — Console Launcher](https://junit.org/junit5/docs/current/user-guide/): differences between JUnit Platform output and Gradle reporting.

## 33. Conclusion

**To triage Spring Boot failures in CI, knowing tests turned red is not enough—you must preserve complete evidence and accurate exit codes.** Gradle JUnit XML serves machine parsing of test cases, HTML reports serve human inspection of stack traces, console logs reveal build/setup/startup failures, and CI artifacts preserve everything after the job exits.

A solid workflow runs real tests, keeps Gradle's non-zero exit code on failure, generates per-task XML/HTML, uploads full reports and console logs under `if: always()`, sets safe retention and permissions, and traces failures along Gradle task → test class → test case → stack/cause → logs/correlation → environment/commit for reproduction. Never count a skipped test as passed, never treat 0 failures as full coverage when zero tests ran, and never let retries or `|| true` erase failure signals.

The Java 17+ / Spring Boot 3.3.5 codebase illustrates **4 test methods and up to 6 executions** when the conditional failure scenario is enabled. Actual runtime outcomes must be verified from generated Gradle/JUnit reports rather than inferred from code or prose.