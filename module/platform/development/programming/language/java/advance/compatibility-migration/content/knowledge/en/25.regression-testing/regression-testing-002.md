# Running the Same Test Suite on Old and New Environments

When upgrading Java from the currently operating JDK to a target JDK, the key question is not merely “does the application compile?” but also **“given the same input data and the same business contract, does the system on the new environment still behave the same way as before?”**. An application may start up on a new JDK yet change how it handles time, decimals, serialization, JDBC, TLS, reflection, or resource management. If tests are run only on the new environment, it is hard for the team to distinguish regression bugs from preexisting buggy behavior, intentional security changes, or configuration differences.

In **Java Advance Compatibility Migration**, the foundational method of the **Regression Testing** chapter is to run a **comparable test suite** on both source and target environments, keeping data and verification criteria consistent, and then compare results per test case rather than merely looking at a BUILD SUCCESS line. This method generates evidence for migration decisions while also pinpointing where code changes, dependency upgrades, configuration updates, or contract updates are needed.

“Same test suite” means preserving **the same intent, the same test cases, the same baseline data, and the same assertions within comparable scope**. It does not necessarily mean running the exact same bytecode file in every scenario: sometimes tests must be compiled separately for different JDKs or frameworks. Any difference must be explicitly recorded so false conclusions are avoided.

## 1. Why Testing Only on the New JDK Is Not Enough

Suppose a team migrates from Java 17 to Java 21. The JDK 21 CI runs 400 tests and all of them PASS. That report still leaves many open questions:

- How many tests ran on Java 17? What were the baseline failures?
- Are those 400 tests actually the **exact same 400 tests** across both JVMs?
- Were any tests omitted due to changing the JUnit engine, plugin, tag, or Maven profile?
- Are the dependency versions, database, schema, and fixture data identical?
- Have behavior changes outside the existing assertions been checked?
- Were error paths, denied permissions, and historical data tested?
- Did the tests actually run on JDK 21, or did Gradle run on Java 21 while the test worker ran on a different JDK?
- Were the container, OS, timezone, fonts, or credentials changed in the same batch?

A passing test suite only proves what was checked **within the exact environment that ran it**. To evaluate regressions, you need a reference point on the source environment and clear comparison rules.

## 2. Precisely Identifying the Old and New Environments

Labels like “old” and “new” are usually too vague. Create an **environment fingerprint** for each test run.

| Component | Evidence to Record | Reason |
|---|---|---|
| Source | Git commit/tag, state of built files | Avoids comparing two source revisions from different bases |
| JDK | Feature/update/build, vendor, CPU architecture | Different Java updates or distributions can behave differently |
| Compiler | JDK compiler, `--release`, bytecode baseline | Distinguishes compiler from runtime |
| Test JVM | Java launcher executing unit/integration tests | Does not necessarily match the JVM running the build tool |
| Build tool | Gradle/Maven wrapper, plugin versions | Affects dependency resolution and test discovery |
| Dependency | Resolved graph, BOM, version lock | Libraries can change behavior independently of the JDK |
| OS/container | OS, image digest, CPU/memory limits | Impacts paths, native code, memory, and timeouts |
| Database | Driver/server version, schema revision | Impacts JDBC, timestamps, transactions |
| Locale/timezone | Locale, ZoneId, DB session timezone | Impacts date/time and data formatting |
| Runtime flags | GC, module opens, TLS, native access | Impacts startup and security |
| Test selection | Task/goal, tag, profile, test case list | Detects skipped/missing tests |
| External systems | Mock version, sandbox endpoint, service contract | Reduces external noise |

Example record:

~~~yaml
regressionRun:
  runId: "java17-baseline-001"
  commit: "record actual commit SHA"
  runtime:
    jdkFeature: 17
    jdkVendorBuild: "record java -version"
    os: "linux-x64"
    timezone: "UTC"
  build:
    tool: "Gradle"
    wrapperVersion: "record actual version"
    release: 17
  dependencies:
    lockChecksum: "record actual checksum"
  database:
    version: "record actual version"
    schema: "S42"
  testSuite:
    id: "regression-v1"
    executedCount: "fill from report"
    report: "reports/java17/"
~~~

This is only a record template, **not actual executed results**. If a piece of information is unknown, record UNKNOWN or NOT_CAPTURED instead of guessing.

## 3. One Problem, Three Types of Comparison

### 3.1. Changing Only the JDK Runtime

Keep the same source commit, application binary, and dependencies when they support both JVMs:

~~~text
Same application binary + same dependency set
             |
        +----+----+
        |         |
      JDK OLD   JDK NEW
        |         |
   Same tests  Same tests
        |         |
      Report A Report B
~~~

This approach isolates the impact of the JDK runtime relatively well. However, if an old library does not support the new JDK, that combination cannot be treated as an officially supported state.

### 3.2. Changing Both the JDK and Dependencies/Frameworks

~~~text
OLD: JDK 17 + framework A + driver X + schema S1
NEW: JDK 21 + framework B + driver Y + schema S2
~~~

Running the same contract tests helps verify the **entire new stack**, though it is insufficient to assert that differences come from the JDK alone. Run intermediate tests if a supported combination exists, or build a small reproduction to isolate the cause.

### 3.3. Testing Old Consumer Binaries

If the system exposes a library/plugin API, besides rebuilding from source, keep a consumer JAR compiled on the old version and test running that bytecode against the new dependency/runtime. Always recompiling consumers can hide `NoSuchMethodError` or `IllegalAccessError` failures that un-rebuilt consumers will hit.

**Each test type answers a different question.** The migration report must state which comparison type was actually executed.

## 4. What Must “Same Test Suite” Keep Identical?

A trustworthy comparison preserves these elements:

1. **Same test intent:** the same requirements are guarded.
2. **Same test identity:** test IDs or mappings from old cases to new cases.
3. **Same inputs and fixtures:** including boundary values.
4. **Same business assertions:** except for approved changes.
5. **Same test selection:** tags, suites, profiles, and filters.
6. **Same external dependency contracts:** mocks/sandboxes whenever possible.
7. **Same reasonable measurement conditions:** resources, concurrency, warm-up, timezone.
8. **Same result recording:** distinguishing PASS, FAIL, SKIPPED, and NOT_RUN.

Certain metadata such as PIDs, random ports, or log timestamps may differ due to the environment. Strip them during comparison only after verifying they are **not part of the contract**. Do not normalize output so broadly that monetary amounts, business states, or security changes are hidden.

## 5. Preparing the Baseline Before Editing Source Code

Ideally, run the regression suite on the source environment before upgrading the JDK or dependencies.

~~~text
Commit X (baseline)
  - capture JDK and dependency versions
  - run compile, unit, integration, contract tests
  - save reports and expected outputs
  - record known failures and skips

Commit X on target runtime (if supported)
  - run equivalent test selection
  - save reports
  - compare by test ID and behavior

Later migration commits
  - keep contract suite and baseline references
  - record intentionally changed expectations
~~~

If the baseline already has failing tests, do not call a candidate exhibiting the same failure a new regression. At the same time, do not turn baseline failures into PASS. Clearly record known issues, owners, and handling conditions.

| Status | Meaning |
|---|---|
| PASS | Test ran and passed assertions |
| FAIL | Test ran and failed assertions |
| SKIPPED | Test was discovered but skipped by rule |
| NOT_RUN | No evidence the test executed |
| BLOCKED | Infrastructure/dependency prevented execution |
| FLAKY | Outcome varies across runs under equivalent conditions |
| NOT_SUPPORTED | Combination outside the support matrix |

Do not use PASS in place of NOT_RUN or NOT_SUPPORTED.

## 6. Expanding the Regression Suite According to Java Migration Risks

| Scope | Test Cases to Include |
|---|---|
| Source/build | Compilation, annotation processors, generated sources, packaging |
| Binary/runtime | Class loading, linkage, service providers, reflection, agent/JNI |
| API/behavior | Return values, nulls, exceptions, ordering, validation |
| Data | DECIMAL precision, timestamps, Unicode, JSON/XML, serialization |
| JDBC/ORM | Type mapping, transactions, generated keys, SQLState |
| Protocols | HTTP headers/status/body, retries/timeouts, TLS |
| Security | Invalid certificates, authorization, input filters, permissions |
| Concurrency | Races, deadlocks, cancellation, thread-local/resource lifecycle |
| File/OS | Paths, permissions, encoding, fonts, native libraries |
| Operations | Startup, health checks, shutdown, logs, GC/memory |
| Performance | Throughput, latency percentiles, RSS, GC pauses |

Not everything needs to run in one single task. You can organize separate unit, integration, contract, security, performance, and end-to-end suites, provided each suite has a comparison mechanism or a documented reason why it applies to only one environment.

## 7. Designing Repeatable Tests

Tests affected by system clocks, timezones, random seeds, file paths, or remote services introduce heavy noise when comparing two JDKs.

### 7.1. Fixing the Clock for Business Dates

Instead of:

~~~java
LocalDate today = LocalDate.now();
~~~

allow Clock injection:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public final class BillingDateService {
    private final Clock clock;

    public BillingDateService(Clock clock) {
        this.clock = clock;
    }

    public String todayIso() {
        return LocalDate.now(clock)
                .format(DateTimeFormatter.ISO_LOCAL_DATE);
    }
}
~~~

JUnit test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

class BillingDateServiceTest {
    @Test
    void usesVietnamBusinessDate() {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-11-11T18:30:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(
                "2026-11-12",
                new BillingDateService(fixed).todayIso());
    }
}
~~~

This prevents the test from depending on the runner's date and time. If data involves historical timezone rules, record the JDK/tzdb version when comparing.

### 7.2. Specifying Locale and Charset Explicitly

~~~java
String formatted = String.format(
        java.util.Locale.US,
        "%,.2f",
        1234.5);
~~~

If formatting is part of the contract, choose an explicit locale. When reading/writing text files, specify the charset explicitly:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(
        Path.of("fixtures", "customer-vi.txt"),
        StandardCharsets.UTF_8);
~~~

`Files.readString` requires Java 11+. If the baseline must support Java 8, use Reader/InputStream with UTF-8 accordingly.

### 7.3. Isolating State

Tests should create and clean up their own data, use dedicated temporary directories, and not rely on records preexisting on a developer's machine. For databases or brokers, each job should have a resettable schema, namespace, or fixture. Do not let tests on old and new JDKs update the same table or queue unless shared contention is itself what is being tested.

## 8. Example: Same Contract Test Across Two JDKs

Suppose a tax calculation contract requires preserving decimal precision:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class InvoiceCalculator {
    private InvoiceCalculator() {}

    public static BigDecimal total(
            BigDecimal net,
            BigDecimal taxRate) {

        if (net == null || taxRate == null) {
            throw new IllegalArgumentException("Missing value");
        }

        return net.multiply(BigDecimal.ONE.add(taxRate))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

JUnit Jupiter test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class InvoiceCalculatorTest {
    @Test
    void preservesDecimalPrecision() {
        BigDecimal actual = InvoiceCalculator.total(
                new BigDecimal("19.995"),
                new BigDecimal("0.10"));

        assertEquals(new BigDecimal("21.99"), actual);
    }

    @Test
    void rejectsMissingRate() {
        assertThrows(
                IllegalArgumentException.class,
                () -> InvoiceCalculator.total(
                        new BigDecimal("20.00"), null));
    }
}
~~~

The calculation `19.995 × 1.10 = 21.9945` rounds to `21.99` with HALF_UP at two decimal places. This example shows that a test should verify **concrete behavior**, not merely that a method throws no exception.

Additional edge cases should cover zero, negative, very large values, varying scales, nulls, and rounding boundaries. If the application uses JDBC, add round-trip tests through real SQL DECIMAL columns rather than testing only Java arithmetic.

## 9. Comparing Results Semantically, Not by Arbitrary Strings

Consider two timestamps:

~~~text
OLD: 2026-11-12T00:00:00Z
NEW: 2026-11-12T07:00:00+07:00
~~~

They can represent the same instant. If the contract specifies an instant, compare `Instant` after parsing. However, if the API promises a `Z` format or a specific timezone representation, changing the string can be a breaking change.

Similarly:

- JSON object key order may not matter, whereas array order may matter.
- `BigDecimal.compareTo()` checks numeric value; `equals()` also checks scale.
- XML prefixes may differ while namespace URIs are equivalent; schema/element contracts must still hold.
- CSV may require specific newlines and quoting.
- PDF files may differ in random metadata yet must preserve required Unicode/glyphs, layout, or text extraction.

**Do not build broad normalizers** that erase every difference and declare the two environments equivalent.

## 10. Golden Files and Historical Data

For serializers, ORMs, events, or reports, store representative fixtures:

~~~text
fixtures/
  invoice-v1.json
  customer-vi.txt
  payment-legacy.bin

expected/
  invoice-response.json
  reconciliation.csv
  report-summary.xml
~~~

Tests on both the old and new JDKs read the same fixtures and compare outputs against the contract. Beyond round-tripping on the new runtime, test reading data created by the old version if the system commits to supporting it.

Do not blindly regenerate expected snapshots simply because the candidate differs from the baseline. First identify whether the change comes from an intentional fix, a regression, a serialization difference, or unstable metadata.

## 11. Testing Error Paths and Security Boundaries as Well

A regression suite with only happy paths is insufficient.

| Test | Contract to Preserve or Evaluate |
|---|---|
| Invalid input | Validation rejects cleanly |
| Expired token | Access denied |
| Insufficient user permissions | Rejected per policy |
| Mismatched TLS hostname | Certificate/hostname verification must reject |
| Disallowed deserialization class | Filter blocks input |
| SQL constraint violation | Transaction rollback and expected exception |
| Dangerous XML external entity | Parser rejects per security config |
| Restricted file permissions | Cannot read/write outside granted rights |

Sometimes a newer JDK rejects an unsafe behavior that an older JDK previously accepted. This is **not automatically a regression to revert**. Review the contract and security policy, fix certificates/peers/configs properly, or update test expectations with approval.

Negative tests must run in authorized test environments, never by deliberately exploiting production.

## 12. Source Compatibility and Binary Compatibility Are Two Separate Checks

**Source compatibility**: compile old consumer source with the new dependency/JDK. Tests can detect removed methods, ambiguous overloads, generic signature changes, or module export changes.

**Binary compatibility**: run precompiled consumer bytecode with the new library/runtime when that combination is supported. Tests can detect `NoSuchMethodError`, `NoClassDefFoundError`, `IllegalAccessError`, and linkage errors.

If you always rebuild consumers when testing, you may miss binary incompatibilities affecting un-rebuilt downstream plugins or applications.

### 12.1. Compiler Release Alone Is Not Enough

Compiling on JDK 21 with `--release 17` restricts source/bytecode and Java SE APIs for the compiled sources. It **does not control the bytecode of preexisting dependency JARs**. If a product claims Java 17 support, execute actual integration/runtime tests on JVM 17.

## 13. Build JVM Is Not Necessarily Test JVM

In Gradle, separate JVMs may run the daemon, compiler toolchain, test worker, and JavaExec tasks. In Maven, the JVMs running Maven core, the compiler, and Surefire/Failsafe test forks can also differ.

Commands:

~~~bash
java -version
./gradlew --version
./mvnw --version
~~~

are helpful for observing the environment, yet are insufficient to confirm which JVM all test workers use. Inspect launcher/toolchain settings, reports, and executed commands.

A clear record might look like:

~~~text
Gradle daemon JDK: 21
Compiler toolchain: 21
javac --release: 17
Unit tests launcher: 17
Application target: 17 and 21
~~~

This is an example, not a mandatory configuration.

## 14. Gradle: Organizing a Test Matrix with Java Toolchains

Suppose an application supports Java 17 and Java 21, and both source and dependencies can run on Java 17. You can compile against the baseline and then execute the **same test classes** on both runtimes.

Illustrative `build.gradle.kts` example:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

listOf(17, 21).forEach { version ->
    tasks.register<Test>("testJava$version") {
        group = "verification"
        description = "Run tests on JDK $version"

        testClassesDirs =
            sourceSets["test"].output.classesDirs
        classpath =
            sourceSets["test"].runtimeClasspath

        useJUnitPlatform()

        javaLauncher.set(
            javaToolchains.launcherFor {
                languageVersion.set(
                    JavaLanguageVersion.of(version))
            }
        )

        reports.junitXml.required.set(true)
        reports.junitXml.outputLocation.set(
            layout.buildDirectory.dir(
                "test-results/java$version")
        )
    }
}
~~~

These tasks require JDK toolchains to be available or provisioned according to configuration. They only verify runtime execution of tests compiled for release 17, and dependencies must also run on 17. Other projects may need custom task/plugin/version configuration.

Reference command:

~~~bash
./gradlew clean testJava17 testJava21
~~~

**Not a command actually executed while writing this article.** To serve as a release gate, pipelines must invoke these tasks explicitly or wire them into verification tasks. Registering tasks does not guarantee CI runs them automatically.

### 14.1. Compile Matrix and Runtime Matrix Differ

- **Compile matrix:** same source compiled under supported compilers; checks source/API compatibility.
- **Runtime matrix:** same bytecode/test artifact executed on supported JVMs; checks runtime compatibility.
- **End-to-end matrix:** actually deployed artifact/container with concrete JDK, OS, DB, and external services.

Do not treat one kind of matrix as proof for every kind.

### 14.2. Test Selection Must Be Identical

Across both runtimes, keep the same `useJUnitPlatform()`, test filters, tags, environment variables, and fixture sources. Partition test data and report outputs by task so they do not overwrite each other. If one task discovers 200 tests while another discovers only 150, investigate before declaring “the same test suite PASSED on both”.

## 15. Maven: Running the Wrapper with Two Provisioned JDKs

A practical approach is creating two CI jobs, each provisioning a different JDK and running the same command:

~~~bash
./mvnw clean verify
~~~

In both jobs, record:

- `./mvnw --version` and Maven's Java version.
- Maven Compiler Plugin/release settings.
- The JDK used by test forks per Surefire/Failsafe configuration.
- Active profiles and test selection.
- JUnit engine/plugin versions and discovered test counts.
- Dependency tree/resolved artifacts.

Maven Toolchains allow the compiler to use a different JDK from the JVM running Maven, yet not all plugins and test forks automatically follow the same toolchain by default. When testing two JDK runtimes, configure **the exact JVM for tests** and verify from reports.

Example Java 17 compiler baseline:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

This is a build POM configuration; compiler/plugin versions must actually support it. It does not by itself guarantee all runtime dependencies run on Java 17.

## 16. CI Matrix: Same Source, Same Suites, Two Runtimes

Conceptual pipeline:

~~~text
                     Commit X
                         |
                 Pin dependencies
                         |
               Prepare test fixtures
                         |
            +------------+------------+
            |                         |
        JDK OLD                  JDK NEW
            |                         |
      Wrapper build             Wrapper build
            |                         |
      Unit/contract             Unit/contract
      integration                integration
            |                         |
        Report A                 Report B
            |                         |
            +-----------+-------------+
                        |
                  Compare by ID
                        |
             Triage and go/no-go
~~~

A CI-vendor-agnostic **pseudocode** YAML:

~~~yaml
matrix:
  java:
    - "17"
    - "21"

forEachJob:
  checkout: "same commit"
  provisionJdk: "selected matrix version"
  run:
    - "java -version"
    - "./gradlew clean test"
  publishReports:
    - "build/test-results/test/"
    - "build/reports/tests/test/"
~~~

This file illustrates the logic only; it is not configuration that can be copied and run directly on GitHub Actions/GitLab/Jenkins. When implementing, use your CI provider's syntax, pin tool/action versions per policy, and provide JDKs/dependencies explicitly.

### 16.1. When an OS Matrix Is Needed

If the application runs across Windows/Linux/macOS or uses JNI, file permissions, fonts, charsets, and external commands, add an OS/architecture matrix. If production is Linux-only, at least test the artifact/container close to the actual Linux runtime.

Do not open an overly huge matrix only to ignore slow jobs. Supported combinations must have reasonable coverage and execution times; untested combinations must be clearly documented.

## 17. Comparing Test Inventory, Not Only Total PASS Count

A useful comparison report:

| Test ID | Old | New | Action Required |
|---|---|---|---|
| `InvoiceCalculatorTest.preservesDecimalPrecision` | PASS | PASS | No difference |
| `BillingDateServiceTest.usesVietnamBusinessDate` | PASS | FAIL | Check timezone and dependencies |
| `SecurityTest.rejectsInvalidCertificate` | FAIL | PASS | Evaluate security fix/old contract |
| `PluginTest.loadsLegacyExtension` | PASS | NOT_RUN | Restore coverage or document limitation |
| `JdbcTest.roundTripDecimal` | FAIL | FAIL | Preexisting baseline or shared infra failure |
| `ConcurrentTest.noLostUpdate` | FLAKY | FLAKY | Investigate race condition and test fixture |

All data in the table is **illustrative only**.

A common mistake is claiming “both sides had 400 tests pass” while the underlying test lists differ. Inspect test identifier lists and actual execution counts. Some tools may change testcase names for parameterized tests; define test ID mapping rules according to the framework/plugin.

### 17.1. JUnit XML Reports

Build tools typically produce JUnit-style XML reports. You can compare class/test names, failures, skips, execution times, and configuration info. However, **missing XML reports do not mean tests PASS**. Reports must distinguish NOT_RUN from INCOMPLETE_REPORT.

If an upgrade causes certain tests to stop being discovered, possible causes include:

- JUnit Jupiter engine missing or incompatible version.
- Surefire/Failsafe or Gradle test runner behavior changed.
- Different tags/profiles across the two jobs.
- Test classes failed to compile.
- Tests conditionally disabled.
- An integration test task not wired into the pipeline.

## 18. JDBC, ORM, and Legacy Data: Test Both Directions

A JDK upgrade can bring JDBC driver or ORM upgrades with it. The regression suite should cover:

- SQL `NULL` distinct from 0, false, and empty strings.
- `BigDecimal` precision/scale/rounding.
- `DATE`, `TIME`, `TIMESTAMP`, timezone/DST.
- UUID, JSON, ARRAY, BLOB/CLOB per vendor.
- Unicode, Vietnamese text, and collation.
- Transaction commit/rollback, isolation, generated keys.
- Connection pool lifecycle, timeouts, and TLS.
- `SQLException`/`SQLState` if retry/error handling depends on them.

You must test **data written by the old version**. Only writing with the new driver and reading back with the same driver can miss backward-compatibility bugs.

Sample matrix:

| Driver | Server/Schema | Goal |
|---|---|---|
| Old | Old | Baseline |
| New | Old | Isolate driver changes |
| New | New | Target state |
| Old | New | Test only if combination remains supported |

Do not force running unsupported combinations; document why they were skipped.

## 19. Issues Appearing Only on the New JDK: Classify Before Fixing

| Symptom | Priority Investigation |
|---|---|
| `invalid source release` | Incorrect compiler/toolchain |
| `UnsupportedClassVersionError` | Bytecode incompatible with runtime JDK |
| `NoSuchMethodError` | Binary API mismatch or transitive dependency conflict |
| `ClassNotFoundException` | Packaging, classpath/module path |
| `InaccessibleObjectException` | Framework reflection and JPMS |
| `SSLHandshakeException` | Truststore, certificate, protocol |
| Shifted timestamps | JDBC/ORM mapping, timezone/session settings |
| Different PDF fonts | Font availability, Java desktop/headless, image |
| Native library fails to load | OS/architecture, path, ABI, permissions |
| Different GC pauses/memory | Default GC, heap sizing, workload, cgroup |
| Tests fail only in CI | Environment, test isolation, seeds, caches, credentials |

A failure appearing after a JDK upgrade is not necessarily caused by the JDK. When build tool, framework, and container change together, create a minimal reproduction or intermediate test to isolate the factor causing the difference.

## 20. Flaky Tests and Concurrency

A newer JDK can shift timing or thread scheduling, exposing preexisting race conditions. A test failing 1 out of 20 runs must not automatically be treated as PASS after a retry.

Recommended practices:

1. Preserve seeds and fixtures whenever possible.
2. Save failing runs, stack traces, and timings.
3. Run repeatedly on both environments if suspected flaky.
4. Audit shared state, thread safety, timeouts, and synchronization.
5. Mark FLAKY distinctly in reports.
6. Do not use infinite retries to mask bugs.

Concurrency tests should assert **invariants** (“no data loss”, “no deadlock”, “eventually reaches a valid state”) rather than assuming thread execution order if the application does not guarantee it.

## 21. Performance Must Be Compared by Workload, Not a Single Unit Test

A single unit test running in 15 ms on the old JDK and 12 ms on the new JDK **does not prove** the new environment is 20% faster. JIT compilation, GC, warm-up, thread scheduling, and CPU throttling introduce noise.

When evaluating performance regressions:

- Keep identical request mix, dataset, concurrency, and duration.
- Try to maintain identical CPU/memory limits and OS/architecture.
- Warm up and repeat runs multiple times.
- Measure throughput, p95/p99 latency, and error rates.
- Track GC pauses, allocation rate, heap/metaspace, and peak RSS.
- Confirm which GC is selected, since defaults can change between JDKs.
- Compare against SLOs and resource budgets rather than requiring pixel-identical graphs.

JMH can be used for Java microbenchmarks, yet it does not replace end-to-end load tests. Performance suites are usually separate CI/staging stages; avoid making unit suites flaky with overly tight timing assertions.

## 22. When New Behavior Is an Acceptable Change

Not every difference requires fixing to match the old behavior. Examples:

- The new JDK rejects weak TLS/certificates per security policy.
- The new framework fixes a serialization bug.
- The application deliberately changes an API response per versioning.
- The new JDBC driver returns a more accurate type and the system accepts updating the contract.

Diff triage workflow:

1. Identify the exact output/exception change.
2. Check release notes, issues, and current contracts.
3. Classify as a regression or an intentional change.
4. Identify affected consumers and migration requirements.
5. If acceptable, update expected tests with formal review.
6. If a regression, fix the root cause and rerun.
7. Record owner, decision, and remaining compatibility scope.

**Do not edit tests just to get PASS under deadline pressure**, and do not turn off security controls to reproduce unsafe legacy behavior.

## 23. Avoiding Cross-Contamination Between Old and New Environments

If two CI jobs run in parallel, they must not share mutable state unless shared contention is itself the test subject.

Example:

~~~text
Run OLD:
  Database schema: regression_old_001
  Object store prefix: regression/old/001/
  Queue topic: regression-old-001

Run NEW:
  Database schema: regression_new_001
  Object store prefix: regression/new/001/
  Queue topic: regression-new-001
~~~

When services cannot be isolated, runs can be executed sequentially with verifiable state resets. Using the same **logical fixture** does not mean sharing a single database instance written to by multiple jobs.

## 24. Reviewable Comparison Report Template

~~~yaml
comparison:
  sourceCommit: "record actual commit"
  suiteId: "core-regression-v4"
  baseline:
    jdk: "old exact vendor/build"
    executed: 420
    passed: 418
    failed: 1
    skipped: 1
  candidate:
    jdk: "new exact vendor/build"
    executed: 420
    passed: 417
    failed: 2
    skipped: 1
  differences:
    newFailures:
      - "BillingDateServiceTest.usesVietnamBusinessDate"
    resolvedFailures: []
    missingTests: []
  evidence:
    baselineXml: "reports/old/"
    candidateXml: "reports/new/"
    dependencyGraph: "reports/resolution/"
  decision: "BLOCKED_PENDING_TRIAGE"
~~~

This template is not actual test results. A complete report should also include artifact digests, database/schema versions, OS/container details, launch arguments, known issues, skipped tests with reasons, and output diffs for every critical test case.

If test inventories differ, the report must explicitly call out the **coverage gap** rather than drawing conclusions from PASS counts alone.

## 25. Step-by-Step Execution Process

### Step 1: Lock Requirements and Versions

Identify source and target JDKs/stacks, API consumers, contracts to preserve, minimum Java runtime, and OS/container scope.

### Step 2: Save Baseline on Old Environment

Run builds/tests with standard commands; record commit, dependency versions, JDK, reports, known failures, and fixtures.

### Step 3: Build a Shared Core Regression Suite

Keep identical test IDs, inputs, assertions, and selection rules. Tests applicable only to the new JDK/framework must live in a separate suite with documented rationale.

### Step 4: Control Sources of Nondeterminism

Clock, seed, locale, timezone, charset, file paths, database state, external service mocks, and concurrency must all be managed.

### Step 5: Provision JDK/Build Toolchain Explicitly

Use wrappers, compiler release settings, test launchers, and appropriate runtime flags. Verify the Java version actually executing the tests.

### Step 6: Run Candidate on Target Environment

Run the same suites and fixtures within supported scope. Save logs, test XML reports, outputs, and environment fingerprints.

### Step 7: Compare Test Inventory

Check discovered, executed, skipped, and missing test counts. Do not declare equivalence if important tests failed to execute.

### Step 8: Compare Behavior and Metrics

Analyze return values, exceptions, contract outputs, historical data, TLS/security, and performance against SLOs.

### Step 9: Triage and Resolve Differences

Distinguish new bugs, baseline failures, approved changes, environment drift, and flaky tests. Edit code/configs/expected tests only when root cause is understood.

### Step 10: Record Release Decision

Document PASS/FAIL/NOT_RUN/BLOCKED/NOT_SUPPORTED counts, owners, risk acceptances, untested environments, and rollback/roll-forward plans.

## 26. When an Identical Test Suite Cannot Be Used

Some situations make differences unavoidable:

- New APIs exist only on the target JDK.
- Framework changes namespaces from `javax.servlet` to `jakarta.servlet`.
- Native/agent libraries do not support the older JDK or OS.
- Database schema changes are not backward-compatible.
- New security policies require different negative tests.
- New features have no equivalent on the baseline.

In those cases, split the suites:

~~~text
Core regression suite:
  contracts shared by old and new
  -> directly comparable

Migration-specific suite:
  removed APIs, module openness, new restrictions
  -> run where applicable

New-feature suite:
  features absent on old runtime
  -> no old-environment equivalence claim
~~~

What matters is **not running different test suites while still claiming full equivalence**.

## 27. Common Misconceptions

**“A green suite on the new JDK proves there are no regressions.”** No, you need a baseline and verification of an identical test inventory.

**“The same Gradle command means the same test JDK.”** No, the Gradle daemon, toolchain, and test launcher can differ.

**“A test file compiled on Java 21 will run on Java 17.”** Not necessarily; verify `--release`, dependency bytecode, and the actual JVM.

**“Comparing total PASS counts is enough.”** No, test identities and skips reveal coverage gaps.

**“We can skip the baseline because it already has flaky tests.”** A noisy baseline still provides essential signal if preexisting failures are recorded and separated from new regressions.

**“If snapshots differ, just update expected files.”** No. Understand which contract changed first.

**“Normalizing all outputs proves both environments equivalent.”** Over-normalization can hide rounding errors, timezone shifts, authorization failures, or formatting bugs.

**“The new JDK tightening TLS is a bug that requires re-enabling old configs.”** It may be an intentional security enforcement requiring updated endpoints/certificates per policy.

**“Retrying until tests PASS is good enough.”** No, flakiness or concurrency bugs still remain.

**“Better performance in a single run means the JVM is faster.”** Equivalent workloads, warm-up, multiple runs, and matched resource limits are required.

**“NOT_RUN can be treated as PASS.”** No, it is a gap in evidence.

**“If multiple dependencies changed, tests cannot be compared.”** You can still compare a core contract suite; simply state honestly that the root cause of differences was not isolated solely to the JDK.

## 28. Checklist for Completing the Regression Matrix

- [ ] Recorded exact source and target JDK feature/update/vendor/build.
- [ ] Saved source commit, dependency graph, and artifact version.
- [ ] Clarified whether only the JDK changed or the entire stack changed.
- [ ] Locked core regression suite, test IDs, tags, and profiles.
- [ ] Saved baseline and known failures prior to migration where feasible.
- [ ] Verified compiler, `--release`, build JVM, and test JVM.
- [ ] Kept input fixtures, schema, and service contracts consistent.
- [ ] Isolated DB/queues/storage across parallel test runs.
- [ ] Controlled clock, timezone, locale, charset, random seeds, and working directory.
- [ ] Covered source, binary, data, behavior, and security checks by risk.
- [ ] Included negative tests and historical data where required by the product.
- [ ] Compared executed test case lists and skips, not just total PASS counts.
- [ ] Triaged differences without unconditionally auto-regenerating expected snapshots.
- [ ] Measured performance under controlled workloads and SLOs.
- [ ] Executed across OS/container/JDK targets in the support matrix.
- [ ] Marked NOT_RUN, BLOCKED, or NOT_SUPPORTED accurately.
- [ ] Archived JUnit XML, logs, outputs, artifact digests, and environment fingerprints.
- [ ] Documented unverified consumers and environments.
- [ ] Defined owners, go/no-go criteria, and rollback/roll-forward plans.

## Conclusion

**Running the same test suite across old and new environments is how comparable compatibility evidence is built**, rather than simply running two build commands and seeing both turn green. You must pin the baseline and candidate precisely, preserve the core regression suite, fixtures, and assertions, control nondeterminism, verify the actual JVM running tests, and compare test inventories, behavior, and operational metrics.

When JDK, dependencies, and frameworks must all change together, state the limits of the comparison clearly, preserve contract tests, and split suites into shared versus environment-specific groups. Every difference must be triaged as a regression, an approved change, an infrastructure issue, or missing evidence. A solid conclusion answers **which tests ran, on which runtime, with what data, where differences appeared, and why it is safe to release**.
