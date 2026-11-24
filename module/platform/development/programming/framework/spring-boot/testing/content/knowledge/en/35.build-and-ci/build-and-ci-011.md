# Test Retries, Flaky Tests, and Handling Unstable Failures in Spring Boot

## 1. Why Is a Test That "Passes on the Second Run" Still a Problem?

In CI, a JUnit case may fail on the first run with a timeout, `AssertionError`, `Connection refused`, or data error, yet pass on a rerun without any code change. This is commonly called a **flaky test**: the outcome of the same test varies across runs even when inputs, code, and configuration are expected to stay constant.

Flakiness destroys pipeline trust. Developers get used to clicking "Rerun job", reviewers ignore red builds, CI wastes runner minutes, and a genuine bug gets brushed off as "probably flaky again." **Retry is a bounded diagnostic and disruption-mitigation tool, never a fix for the root cause.**

In Spring Boot, frequent culprits include:
- Using `Thread.sleep` to wait for `@Async`, schedulers, message queues, or HTTP servers.
- Depending on JUnit method/class execution order, the system clock, random data, or timezones.
- Sharing `static` state, Spring singleton beans, Mockito mocks, system properties, H2/Redis/Kafka, or fixed file paths across tests.
- Expecting test-thread `@Transactional` to cover transactions inside HTTP or worker threads.
- Unready Testcontainers/DB/brokers, fixed ports, or missing cleanup.
- `@DirtiesContext` closing a context while parallel tests are still using it.
- Unstable network/outbound exporters/backends with retries failing to distinguish app bugs from infrastructure errors.
- CI CPU/RAM/connection-pool exhaustion after cranking up `maxParallelForks` or JUnit parallelism.

This lesson belongs to **Build and CI**, targeting Java 17+, Spring Boot 3.5.x, JUnit Jupiter, and Gradle. You will learn how the **Gradle Test Retry Plugin** works, distinguish retries from `@RepeatedTest` and `--rerun-tasks`, configure a CI policy that never hides flaky tests, write independent retry-safe tests, read reports, manage owned/time-bounded quarantine, and fix Spring Boot-specific root causes.

The main example uses **Gradle Test Retry Plugin 1.6.6** (published on the Gradle Plugin Portal in September 2026) and Spring Boot **3.5.8**. The runnable code is a Java/Gradle project featuring business logic, async execution, `@TempDir`, and `@SpringBootTest`. All sample tests are designed to be **deterministic**, without planting artificial random failures inside a normal suite. No live Gradle/JUnit execution occurred while authoring this article, so execution counts and results below are **expected from source**, not fabricated stdout.

## 2. Classify the Failure Before Deciding to Retry

Not every "fail then pass" comes from poorly written test code. Classification directs fixes to the right layer.

| Category | Symptoms | What Retry Reveals | Proper Fix |
|---|---|---|---|
| **Deterministic product bug** | Same input always fails | Usually keeps failing; occasional pass implies state leak | Fix application code, add regression test |
| **Test flakiness** | Outcome shifts with timing/order/seed | Fail→pass is a strong signal, though not yet root cause | Fix synchronization, fixtures, isolation |
| **Intermittent product failure** | Real service occasionally races/times out | Passing rerun does not eliminate the bug | Fix app concurrency, add business retry policy where valid |
| **Environment failure** | CI runner out of disk, DB down, Docker error | Many tests fail together; per-test retry wastes time | Fix readiness, resources, service availability |
| **External dependency outage** | Provider/collector/third-party API unreachable | May recover randomly | Use fakes/local stubs in unit; separate integration policy |
| **Non-hermetic test** | Relies on clock, locale, random, files, shared DB | Rerun receives different hidden inputs | Inject `Clock`/seeds, per-test resources |
| **Incorrect test expectation** | Asserts unguaranteed timing or format | Rerun shifts scheduling and hides bad assumptions | Assert invariant behavior instead of implementation quirks |
| **Real concurrency bug** | Fails only under load/parallelism | Passing rerun is still dangerous | Hunt data races, fix locking/thread-safety, add stress tests |

**Key point:** A test failing once and passing on rerun is a **symptom of nondeterminism**, yet does not immediately identify whether the flaw lies in the test, the app, the infrastructure, or the observer. Never declare a bug "gone" just because a rerun passed once.

### 2.1. Why Even Low-Rate Flakiness Is Dangerous

Suppose a test has an independent per-run failure probability `p`. Adding one retry drops the chance of failing both attempts under a simplistic model to `p × p`; many first failures get hidden when the second attempt passes. In real CI, however, failure events are often **not independent**: a down DB, OOMing Docker daemon, dirty shared state, or network outage can span both attempts. The formula is a mental model, **not a production reliability forecast**.

Measure more than final green/red status: track **first-attempt failure rate**, **pass-on-retry count**, retry attempts consumed, failure frequency by test/branch/runner, and engineering time spent triaging.

### 2.2. From Test Failure to Action

```text
JUnit execution FAILED
        |
        +--> Failure deterministic? --yes--> fix code/test assertion
        |
        +--> Multiple tests failing on shared infra?
        |          |
        |          +--yes--> fix runner, DB, Docker, secrets, readiness
        |
        +--> Allow at most one retry to gather more evidence?
                   |
                   +--> retry PASS
                   |      |
                   |      +--> mark flaky, preserve first failure
                   |      +--> assign owner + issue, find root cause
                   |      +--> build still FAILS under strict CI policy
                   |
                   +--> retry FAIL
                          |
                          +--> failure persists, fix directly
                          +--> never retry infinitely
```

A pipeline can temporarily "turn green if retry passes" during a transition period, yet that must be a **controlled exception** with metrics and an expiry date—never a default that blinds the team to failures.

## 3. Distinguish Four Mechanisms Often Lumped Together as "Retry"

| Mechanism | What It Actually Does | Scope | Re-runs Only Failed Tests? |
|---|---|---|---|
| Gradle Test Retry Plugin | Re-runs failed tests within the **same Gradle `Test` task** | Per test execution, per task | Yes, subject to framework & filter support |
| JUnit Jupiter `@RepeatedTest(n)` | Runs the method **n scheduled times** | Per JUnit test invocation | **No**; does not wait for failure |
| Gradle `--rerun-tasks` | Forces tasks to run even if up-to-date/cached | Gradle task graph level | **No**; does not isolate failed tests |
| CI "rerun failed job" | Re-runs the entire pipeline job/process | CI job level; may land on new host/state | Does not select just failing JUnit methods |
| `./gradlew test --tests "Class.method"` | Selects one method/class by name to run | Gradle Test filter | Manual targeted command, not automatic retry |
| HTTP/client retry | Retries a business/network operation | Application layer | Not JUnit/Gradle test retry |

**Never confuse `@RepeatedTest(20)` with "retry only on failure".** It works well as a diagnostic stress test for an isolated check, not for pass-on-retry tracking. In the runnable project, `@RepeatedTest(5)` lives in a dedicated **diagnostic lane**, rather than repeating 5 times on every PR unit run.

### 3.1. JUnit Extension Retries Differ from Gradle Retries

Teams or community libraries sometimes write JUnit extensions to retry failing methods. Verify lifecycle compatibility carefully—especially with `@BeforeEach`, `@AfterEach`, Spring TestContext, `@Transactional`, `@ParameterizedTest`, and retry reporting. The example here **does not install a JUnit retry extension**, relying solely on the Gradle plugin so attempt caps and reporting stay in one place.

Never stack a JUnit retry extension, Gradle Test Retry, and CI job reruns without budgeting total attempts. Multiplying retries across layers inflates runtime and masks ongoing incidents.

## 4. How the Gradle Test Retry Plugin Works

Official plugin ID:

```groovy
plugins {
    id 'org.gradle.test-retry' version '1.6.6'
}
```

Applying the plugin adds a `retry` block to Gradle `Test` tasks. **Applying the plugin alone does not enable retries**: `maxRetries` defaults to 0. You must configure policy per task.

Per plugin docs, after running all selected tests once, the plugin re-runs failed tests and repeats if errors persist until attempts are exhausted. It does not necessarily re-run the entire suite from scratch. With certain frameworks, dependencies or parameterization can widen re-execution beyond a single invocation.

### 4.1. Key Options

```groovy
tasks.named('test', Test) {
    retry {
        maxRetries = 1
        maxFailures = 10
        failOnPassedAfterRetry = true
        failOnSkippedAfterRetry = true
    }
}
```

| Property | Meaning | Recommendation |
|---|---|---|
| `maxRetries` | Number of **retries after the first attempt** per failing test | `1` means at most 2 total attempts; `0` disables |
| `maxFailures` | Failure count threshold in **one retry round** above which retries abort | Prevents "retry storms" when DB/runner dies |
| `failOnPassedAfterRetry` | Should a test failing first then passing on retry still fail the Gradle task? | `true` for strict CI to expose flakiness |
| `failOnSkippedAfterRetry` | Should a failed test that skips on retry fail the task? | `true` so skips never become false successes |
| `filter` | Selects tests **eligible for retry** by reported class name/annotations | Restrict retries to approved integration groups |
| `classRetry` | Re-runs the entire class for classes with ordering/dependencies | Use sparingly; increases cost |

**Important defaults:** `maxRetries=0` disables retries; `failOnPassedAfterRetry=false` by plugin default so pass-on-retry can turn tasks green; `failOnSkippedAfterRetry=true` per plugin compatibility policy. This article **explicitly sets both fail flags to `true`** to enforce strict error visibility.

`maxFailures=10` here is an **illustrative threshold**, not a universal constant. If 10 tests fail in one round and the threshold is 10, retries halt; below that threshold with remaining attempts, retries proceed. Per plugin docs, this limit applies **per round**, not as a naive cumulative sum across the suite.

### 4.2. A Concrete Walkthrough

Suppose a Gradle task has 40 tests:
1. Initial run: 38 pass, `A` fails, `B` fails.
2. `maxRetries=1`: the plugin selects the failed tests (at the method or class granularity supported by the framework) to retry.
3. Retry round: `A` passes, `B` fails.
4. `B` still fails → task fails.
5. Even if both `A` and `B` pass on retry, with `failOnPassedAfterRetry=true`, **the task still fails** because flakiness was detected.

**Never argue "attempt 2 passed so the build is clean."** The retry merely provided extra evidence that attempt 1 was unstable. CI must preserve the initial failure and assign a root-cause owner.

### 4.3. Parameterized Tests and Retry Granularity

For JUnit Jupiter `@ParameterizedTest`, the plugin may **retry the entire method across all argument sets**, including invocations that passed on the first attempt, due to framework selection granularity. Therefore:
- Never assume only the single failing parameter row is retried.
- Avoid non-idempotent side effects inside parameterized tests.
- Include useful parameter indices/values in test display names while avoiding random/dynamic names that break report merging.
- If a parameterized method runs 200 cases, a retry can be costly; split groups or tighten fixtures as needed.

### 4.4. Retry Filters Differ from Test Selection Filters

```groovy
tasks.named('test', Test) {
    retry {
        maxRetries = 1
        filter {
            includeClasses.add('*IntegrationTest')
            excludeClasses.add('*PaymentContractTest')
        }
    }
}
```

This is an **illustrative alternative snippet**, not active in the runnable build in section 7. `filter` here controls **which tests are allowed to retry after failing**, **not** which tests run initially. Gradle `--tests` and JUnit `includeTags` belong to initial test selection.

If a class name does not match the retry filter, it still runs normally, yet is not retried on failure. Annotation-based retry filtering inspects **class-level** annotations rather than arbitrary method-level `@Tag`s; never treat the two filter systems as identical.

### 4.5. What the Plugin Does Not Do

- Does not fix bugs or fixture races.
- Does not keep transactions or Spring contexts from the first attempt alive for inspection.
- Does not make non-idempotent tests idempotent.
- Does not retry tests skipped by Gradle tags or filters.
- Does not undo uncommitted/committed DB rows, outbox entries, or Redis keys mutated on attempt 1.
- Does not guarantee an external API recovers before the retry fires.
- Does not validate correctness if the suite was skipped or up-to-date.
- Does not create ownership, quarantine expiry, or triage dashboards automatically.

**Therefore, treat retries as diagnostic data and controlled noise reduction, never as a "green pipeline magic wand".**

## 5. Building a CI Policy That Never Hides Failures

A representative policy for teams improving reliability:

| Group | Local Developer | Pull Request CI | Nightly / Diagnostic |
|---|---|---|---|
| Pure unit | No retry by default | At most 1 retry for detection; pass-on-retry still fails task | Targeted `@RepeatedTest` / stress tests |
| Spring slice | No retry or opt-in | Same strict policy once tests are isolated | Analyze context cache / mock state |
| DB / container integration | Dedicated test environment | Bounded 1 retry, readiness checks before tests | Multi-run stress, resource isolation |
| External contract | Local stub/unit; no cloud calls | Runs only in jobs with explicit dependencies | Retry per external test agreement |
| Known flaky (isolated) | Outside main PR gate | Never silently dropped from coverage | Dedicated quarantine lane + issue owner |
| Post-deploy smoke | Not a unit test | Never silently skip production errors | Bounded wait/retry health checks per readiness policy |

**Choosing `failOnPassedAfterRetry`:**
- `true` fits teams prioritizing signal integrity and committed to fixing flakiness. A red build flags that attempt 1 failed.
- `false` may be chosen **temporarily** to avoid blocking every PR on a heavily flaky legacy suite, provided you track flaky metrics/alerts, open issues, and enforce a sunset deadline. Turning off alerts degrades trust steadily.
- Never use `ignoreFailures=true` to "fix pipelines". Ignoring failures defeats fail-on-retry protections completely.

### 5.1. Why Keep maxRetries Small?

One or two retries already yield enough signal for nondeterminism. Setting 5–10 retries:
- Multiplies CI cost and feedback latency.
- Increases the odds of masking a low-probability real bug.
- Re-runs DB/container state repeatedly, muddying traces.
- Hides dependency outages instead of failing fast with clear diagnostics.

When **application code** has a network retry policy, test that retry logic directly with a controlled fake clock and fault injection—never crank up JUnit retries as a substitute for production behavior.

### 5.2. Never Restart the Whole Job to "Fix" an Assertion

Rerunning a CI job can land on a different worker with different caches, DB snapshots, Docker state, and CPU load. Passing there only proves **a separate execution** succeeded; it obscures which step failed previously or how many retries fired. Always archive logs, JUnit XML, and CI metadata from the **first run** before triggering a rerun.

## 6. Reporting: Pass-on-Retry Must Leave Traces

Gradle generates HTML/XML reports per `Test` task:
- `build/reports/tests/test/index.html`.
- `build/test-results/test/`.

The Gradle Test Retry Plugin records each execution as an event. CI servers may tally fail-then-pass differently depending on XML parsers. Gradle exposes `reports.junitXml.mergeReruns`.

### 6.1. mergeReruns and Reporting Goals

```groovy
tasks.named('test', Test) {
    reports {
        junitXml {
            outputPerTestCase = true
            mergeReruns = false
        }
    }
}
```

The sample project sets `mergeReruns=false` so XML keeps separate execution entries, making the initial failure easy to inspect. With `mergeReruns=true`, Gradle merges fail→pass attempts under one testcase and records the initial error under `<flakyFailure>` instead of `<failure>`. That prevents some CI parsers from flagging red when the final attempt passed, **at the risk of dashboards ignoring `<flakyFailure>`**.

**Critically:** `mergeReruns` changes only **XML output formatting** and **never enables retries**. Retries come from the plugin or test framework. If CI parses XML to decide pass/fail independently, ensure its rules do not contradict `failOnPassedAfterRetry`.

### 6.2. Reading Metrics Accurately

| Status | Interpretation |
|---|---|
| `PASS` first attempt | Normal green test |
| `FAIL` then `PASS` | Flaky signal; never erase the initial failure |
| `FAIL` both attempts | Persistent error; still does not prove determinism by itself |
| `SKIPPED` on retry | Investigate why a failing test skipped later |
| Task `UP-TO-DATE` | Did not re-execute in this build |
| Task `FROM-CACHE` | Output restored from cache; not a fresh execution |
| Task `NO-SOURCE` / zero selected tests | Zero proof tests ran |
| Green build via `ignoreFailures` | False gate signal: JUnit failures may still exist |

CI summaries should report at minimum: first-attempt failures, pass-on-retry tests, permanently failed tests, skipped tests, retries consumed, build/task status, and environment fingerprint—never just a green checkmark and total test count.

## 7. Complete Spring Boot 3.5.8, Java 17+, Gradle Project

This project intentionally omits external DBs, HTTP servers, Redis, and exporters to stay focused on **flakiness and retry policies**. It features:
- A pricing service injecting `Clock` for deterministic date testing.
- An async service using `CompletableFuture` and a test-managed executor, awaiting with timeouts instead of sleeping blindly.
- A file writer tested with `@TempDir` to prevent collisions across forks/methods.
- A lightweight `@SpringBootTest` checking DI without external dependencies.
- `@RepeatedTest(5)` isolated in a separate **diagnostic** lane to contrast planned repetition with retry-on-failure.
- Gradle Test Retry Plugin allowing at most **one retry in CI**, configured with **`failOnPassedAfterRetry=true`**.

### 7.1. File Tree

```text
settings.gradle
build.gradle
src/main/java/com/example/retrylab/
    RetryLabApplication.java
    TimeConfiguration.java
    CheckoutQuote.java
    CheckoutService.java
    AsyncReceiptService.java
    ReceiptFileWriter.java
src/test/java/com/example/retrylab/
    CheckoutServiceTest.java
    AsyncReceiptServiceTest.java
    ReceiptFileWriterTest.java
    CheckoutSpringTest.java
    StabilityRepetitionTest.java
```

No `src/test/resources/application.properties` is required; the app has no DB or web server. There are no "flaky-by-design" tests in the normal lane. To test the retry plugin against a deliberate failure, do so on a dedicated diagnostic branch/fixture rather than putting random failures in the main suite.

### 7.2. settings.gradle

```groovy
rootProject.name = 'spring-boot-retry-lab'
```

### 7.3. Complete build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'org.gradle.test-retry' version '1.6.6'
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

def onCi = System.getenv().containsKey('CI')

tasks.named('test', Test) {
    useJUnitPlatform {
        // Quarantine and diagnostic are excluded from the PR test gate.
        excludeTags 'quarantine', 'diagnostic'
    }

    // Single JVM to keep the example reproducible; scale up only after
    // verifying isolation of Spring/IO tests.
    maxParallelForks = 1

    retry {
        // Local: no retry. CI: initial attempt + 1 retry.
        maxRetries = onCi ? 1 : 0
        maxFailures = 10
        failOnPassedAfterRetry = true
        failOnSkippedAfterRetry = true
    }

    reports {
        junitXml {
            outputPerTestCase = true
            mergeReruns = false
        }
    }

    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}

// Repeated test to investigate stability.
// NOT retry-on-failure.
tasks.register('diagnosticTest', Test) {
    description = 'Run repeated diagnostic tests'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'diagnostic'
    }

    maxParallelForks = 1

    retry {
        maxRetries = 0
    }
}

// Lane for known flaky tests if isolation is needed later.
// The initial sample project has NO tests with this tag.
tasks.register('quarantineTest', Test) {
    description = 'Run quarantined tests separately'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'quarantine'
    }

    maxParallelForks = 1

    retry {
        maxRetries = 0
    }
}

// The Java plugin's check already depends on test.
// Neither diagnostic nor quarantine tasks are added to check.
```

**Properties of this configuration:**
- `CI` is detected by the **presence** of the environment variable, not specifically the string `"true"`. CI providers must set it consistently; otherwise retries stay disabled.
- `maxRetries=1` means initial execution + at most one retry for failing tests, never running every test twice.
- `failOnPassedAfterRetry=true` ensures a fail→pass still turns Gradle `test` red in CI.
- `maxFailures=10` caps retry storms; the threshold is illustrative.
- `reports.junitXml.mergeReruns=false` retains separate execution entries in XML; `outputPerTestCase=true` links logs per test method.
- `diagnosticTest` selects `@Tag("diagnostic")` with plugin retries off, isolating planned JUnit repetitions.
- `quarantineTest` selects `@Tag("quarantine")`; initially matches nothing since the project contains no deliberate flaky cases.
- `./gradlew check` runs `test`, **never automatically running** `diagnosticTest` or `quarantineTest`.
- `maxParallelForks=1` and zero external services keep diagnosis clean before experimenting with higher concurrency.

**Do not set `ignoreFailures=true` or `failFast=true` in this example.** `ignoreFailures=true` prevents blocking broken builds; `failFast=true` aborts early and hides other failures in the same run. Once triage policies mature, teams may opt into fail-fast on specific groups per feedback goals.

### 7.4. Main Application

File `src/main/java/com/example/retrylab/RetryLabApplication.java`:

```java
package com.example.retrylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RetryLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(RetryLabApplication.class, args);
    }
}
```

Without `starter-web`, booting the Spring context opens no HTTP port. Without `starter-data-jpa`, no DB connections open. The focus stays on DI and deterministic test patterns.

### 7.5. Injecting Clock: Eliminating System-Time Dependencies

File `src/main/java/com/example/retrylab/TimeConfiguration.java`:

```java
package com.example.retrylab;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

File `src/main/java/com/example/retrylab/CheckoutQuote.java`:

```java
package com.example.retrylab;

import java.math.BigDecimal;
import java.time.LocalDate;

public record CheckoutQuote(
        String orderCode,
        BigDecimal payable,
        LocalDate processedDate) {
}
```

Production injects the Spring `Clock` bean, while unit tests pass `Clock.fixed(...)` directly. Tests verify expected dates **independently of midnight rollovers, CI runner timezones, or daylight-saving transitions**.

### 7.6. CheckoutService.java

File `src/main/java/com/example/retrylab/CheckoutService.java`:

```java
package com.example.retrylab;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final Clock clock;

    public CheckoutService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public CheckoutQuote quote(
            String orderCode,
            BigDecimal subtotal,
            int discountPercent) {

        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException(
                    "orderCode must not be blank");
        }

        Objects.requireNonNull(subtotal, "subtotal");

        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException(
                    "subtotal must not be negative");
        }

        if (discountPercent < 0 || discountPercent > 100) {
            throw new IllegalArgumentException(
                    "discountPercent must be in 0..100");
        }

        BigDecimal payable = subtotal.multiply(
                BigDecimal.valueOf(100 - discountPercent))
            .divide(
                BigDecimal.valueOf(100),
                2,
                RoundingMode.HALF_UP);

        return new CheckoutQuote(
                orderCode,
                payable,
                LocalDate.now(clock));
    }
}
```

This is a stateless Spring `@Service`: every `quote(...)` call relies solely on its arguments and `Clock`, with no mutable caches, static counters, or global current-date state. Unit tests pass a fixed `Clock`; integration tests assert pricing and bean wiring without asserting the machine's wall clock.

### 7.7. AsyncReceiptService.java

File `src/main/java/com/example/retrylab/AsyncReceiptService.java`:

```java
package com.example.retrylab;

import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public final class AsyncReceiptService {

    private final Executor executor;

    public AsyncReceiptService(Executor executor) {
        this.executor = Objects.requireNonNull(executor);
    }

    public CompletableFuture<String> normalizeAsync(
            String code) {
        return CompletableFuture.supplyAsync(() -> {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException(
                        "code must not be blank");
            }
            return code.trim().toUpperCase(Locale.ROOT);
        }, executor);
    }
}
```

The async service does not spawn an unmanaged global executor; tests supply their own executor. `CompletableFuture` lets tests **await completion with a bounded timeout** instead of calling `Thread.sleep(50)` and hoping the worker finished.

In production Spring Boot, `@Async` typically uses a Spring-managed `TaskExecutor`. The same principle applies: expose/inject a completion signal or observe durable state up to a deadline. Sleeping in tests hides bugs that only surface under slow CI CPUs or saturated schedulers.

### 7.8. ReceiptFileWriter.java

File `src/main/java/com/example/retrylab/ReceiptFileWriter.java`:

```java
package com.example.retrylab;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class ReceiptFileWriter {

    public Path write(
            Path directory,
            String baseName,
            String contents) throws IOException {

        Objects.requireNonNull(directory);
        Objects.requireNonNull(baseName);
        Objects.requireNonNull(contents);

        Files.createDirectories(directory);

        Path output = directory.resolve(
                baseName + ".txt");

        Files.writeString(
                output,
                contents,
                StandardCharsets.UTF_8);

        return output;
    }
}
```

Tests pass a dedicated directory via `@TempDir` instead of writing to a fixed `build/receipt.txt`. When raising Gradle `maxParallelForks` or enabling JUnit concurrency, per-test directories prevent file collisions. In real production code, validate `baseName` against path traversal if derived from untrusted input; this training demo passes safe test constants.

## 8. Deterministic JUnit Tests: Never "Simulate Flakiness" with Randomness

### 8.1. CheckoutServiceTest.java: Business Logic and Fixed Clock

File `src/test/java/com/example/retrylab/CheckoutServiceTest.java`:

```java
package com.example.retrylab;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CheckoutServiceTest {

    private final Clock fixedClock = Clock.fixed(
            Instant.parse("2026-01-20T23:59:59Z"),
            ZoneOffset.UTC);

    private final CheckoutService service =
            new CheckoutService(fixedClock);

    @Test
    void fixedClockMakesProcessedDateStable() {
        CheckoutQuote quote = service.quote(
                "ORD-A",
                new BigDecimal("100.00"), 10);

        assertThat(quote.processedDate())
            .isEqualTo(LocalDate.of(2026, 1, 20));
        assertThat(quote.payable())
            .isEqualByComparingTo("90.00");
    }

    @Test
    void roundingIsDeterministic() {
        CheckoutQuote quote = service.quote(
                "ORD-B",
                new BigDecimal("99.99"), 25);

        assertThat(quote.payable())
            .isEqualByComparingTo("74.99");
    }

    @Test
    void invalidDiscountAlwaysThrows() {
        assertThatThrownBy(() ->
                service.quote("ORD-C",
                    new BigDecimal("10.00"), 101))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage(
                "discountPercent must be in 0..100");
    }

    @Test
    void separateInputsDoNotShareMutableState() {
        CheckoutQuote first = service.quote(
                "ORD-D", new BigDecimal("10"), 0);
        CheckoutQuote second = service.quote(
                "ORD-E", new BigDecimal("20"), 50);

        assertThat(first.orderCode()).isEqualTo("ORD-D");
        assertThat(first.payable())
            .isEqualByComparingTo("10.00");

        assertThat(second.orderCode()).isEqualTo("ORD-E");
        assertThat(second.payable())
            .isEqualByComparingTo("10.00");
    }
}
```

Contains **4 `@Test` cases**. The first uses a fixed UTC timestamp; even if CI runs right across midnight or in another timezone, the expected date never shifts. Other tests compare `BigDecimal` values with `isEqualByComparingTo` rather than system-formatted strings.

**Never call `LocalDate.now()` directly in an assertion** to check code that called `LocalDate.now()` moments earlier: the date can flip between the two calls at midnight.

### 8.2. AsyncReceiptServiceTest.java: Awaiting Futures with Deadlines

File `src/test/java/com/example/retrylab/AsyncReceiptServiceTest.java`:

```java
package com.example.retrylab;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AsyncReceiptServiceTest {

    @Test
    void asyncResultIsWaitedForRatherThanSleptFor()
            throws Exception {

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            AsyncReceiptService service =
                    new AsyncReceiptService(pool);

            CompletableFuture<String> future =
                    service.normalizeAsync(" inv-101 ");

            assertThat(future.get(3, TimeUnit.SECONDS))
                .isEqualTo("INV-101");
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void rejectedInputIsVisibleAsFutureFailure()
            throws Exception {

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            AsyncReceiptService service =
                    new AsyncReceiptService(pool);

            CompletableFuture<String> future =
                    service.normalizeAsync("   ");

            assertThatThrownBy(
                () -> future.get(3, TimeUnit.SECONDS))
                .isInstanceOf(ExecutionException.class)
                .hasCauseInstanceOf(
                    IllegalArgumentException.class);
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void independentFutureResultsDoNotShareState()
            throws Exception {

        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        try {
            AsyncReceiptService service =
                    new AsyncReceiptService(pool);

            CompletableFuture<String> a =
                    service.normalizeAsync("a-1");
            CompletableFuture<String> b =
                    service.normalizeAsync("b-2");

            assertThat(a.get(3, TimeUnit.SECONDS))
                .isEqualTo("A-1");
            assertThat(b.get(3, TimeUnit.SECONDS))
                .isEqualTo("B-2");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Contains **3 `@Test` cases**. `Future.get(timeout)` awaits actual completion; the timeout merely bounds how long CI can wait. `shutdownNow()` inside `finally` prevents leaking executors after a failure. Never assert exact thread names or execution ordering where the scheduler gives no guarantee.

### 8.3. ReceiptFileWriterTest.java: @TempDir Instead of Shared Files

File `src/test/java/com/example/retrylab/ReceiptFileWriterTest.java`:

```java
package com.example.retrylab;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

class ReceiptFileWriterTest {

    private final ReceiptFileWriter writer =
            new ReceiptFileWriter();

    @Test
    void writesReceiptIntoPerTestDirectory(
            @TempDir Path directory) throws IOException {

        Path file = writer.write(
                directory, "receipt", "paid");

        assertThat(Files.exists(file)).isTrue();
        assertThat(Files.readString(
                file, StandardCharsets.UTF_8))
            .isEqualTo("paid");
    }

    @Test
    void anotherMethodMayUseSameFileNameSafely(
            @TempDir Path directory) throws IOException {

        Path file = writer.write(
                directory, "receipt", "refunded");

        assertThat(Files.readString(
                file, StandardCharsets.UTF_8))
            .isEqualTo("refunded");
    }
}
```

Contains **2 `@Test` cases**. Even though both write `receipt.txt`, each test method gets its own JUnit-managed `@TempDir`. That isolates more strongly than `@ResourceLock("receipt.txt")` when Gradle forks multiple JVMs, because `@ResourceLock` coordinates only within one JUnit execution plan.

### 8.4. CheckoutSpringTest.java: Real Context, Independent of Wall Clock

File `src/test/java/com/example/retrylab/CheckoutSpringTest.java`:

```java
package com.example.retrylab;

import java.math.BigDecimal;
import java.time.Clock;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CheckoutSpringTest {

    @Autowired
    CheckoutService service;

    @Autowired
    Clock clock;

    @Test
    void contextWiresServiceAndClock() {
        assertThat(service).isNotNull();
        assertThat(clock).isNotNull();
    }

    @Test
    void quoteWorksInSpringContext() {
        CheckoutQuote quote = service.quote(
                "SPRING-A", new BigDecimal("100"), 20);

        assertThat(quote.orderCode())
            .isEqualTo("SPRING-A");

        assertThat(quote.payable())
            .isEqualByComparingTo("80.00");

        // Do not assert processedDate == LocalDate.now()
        // because this test verifies wiring/pricing, not Clock.
    }
}
```

Contains **2 `@Test` cases**. The test boots an `ApplicationContext` with real beans and no DB/web/external services. Spring Boot can cache this context across tests; because the demo beans are stateless, no mock/shared-state reset is required.

### 8.5. StabilityRepetitionTest.java: @RepeatedTest Is for Stress/Diagnostics

File `src/test/java/com/example/retrylab/StabilityRepetitionTest.java`:

```java
package com.example.retrylab;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.RepetitionInfo;
import org.junit.jupiter.api.Tag;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("diagnostic")
class StabilityRepetitionTest {

    @RepeatedTest(5)
    void identicalInputHasIdenticalOutcome(
            RepetitionInfo repetitionInfo) {

        CheckoutService service = new CheckoutService(
                Clock.fixed(
                    Instant.parse("2026-01-20T00:00:00Z"),
                    ZoneOffset.UTC));

        CheckoutQuote result = service.quote(
                "REPEAT-A",
                new BigDecimal("100.00"), 10);

        assertThat(result.payable())
            .isEqualByComparingTo("90.00");

        assertThat(repetitionInfo.getCurrentRepetition())
            .isBetween(1, 5);

        assertThat(repetitionInfo.getTotalRepetitions())
            .isEqualTo(5);
    }
}
```

This class has **one `@RepeatedTest(5)` source method**, producing **5 invocations** when running `diagnosticTest`. It does not wait for failures to retry, nor does it uncover races in non-concurrent code. Its purpose is demonstrating fixed-input/deadline repetition in contrast to retry-on-failure plugins.

**Test counts in the sample:** 4 + 3 + 2 + 2 = **11 `@Test` methods** in the `test` task, plus 5 invocations from `@RepeatedTest` when running `diagnosticTest`. Since no intentionally failing test is included, when the suite passes on the first attempt, **zero actual retries fire**. To exercise the plugin on a controlled failure, use a dedicated diagnostic branch or separate plugin-validation fixture rather than injecting random failures into the main suite.

## 9. Analyzing the Anti-Pattern: Thread.sleep and Async Testing

An unstable pattern:

```java
CompletableFuture<String> future =
        service.normalizeAsync("INV-22");

Thread.sleep(20); // Hope the worker has finished
assertThat(future.isDone()).isTrue();
```

This is a **broken fragment shown for analysis**, not a runnable test in the project. It depends on the OS CPU scheduler, thread pool backlog, GC pauses, and CI host load. `Thread.sleep(20)` gives no guarantee the worker finished.

The fix:

```java
CompletableFuture<String> future =
        service.normalizeAsync("INV-22");

assertThat(future.get(3, TimeUnit.SECONDS))
    .isEqualTo("INV-22");
```

This fragment assumes `service` and `TimeUnit` are imported/declared. It waits for the actual outcome up to three seconds. When an app does not expose a `Future`, use `CountDownLatch`, `CompletableFuture`, Awaitility with a polling deadline, or observable durable state. Never bump `Thread.sleep(20)` to `5000` to "stabilize" it.

### 9.1. Latches Must Tie to a Real Event

```java
CountDownLatch finished = new CountDownLatch(1);

executor.submit(() -> {
    try {
        performWork();
    } finally {
        finished.countDown();
    }
});

assertThat(finished.await(3, TimeUnit.SECONDS))
    .isTrue();
```

This illustrative fragment assumes `executor` and `performWork()` are declared. Placing `countDown()` in `finally` keeps the test from hanging if the worker throws, **yet** you must still capture/rethrow worker exceptions (e.g., via `Future.get`) so worker errors do not turn into false green tests. A latch only proves execution reached `countDown`, not that business results were right.

### 9.2. Awaitility (When Genuinely Testing Eventual Consistency)

For Kafka consumers, schedulers, or eventual DB state, Awaitility provides bounded polling:

```java
await().atMost(Duration.ofSeconds(5))
       .untilAsserted(() ->
           assertThat(repository.existsById(id)).isTrue());
```

This is an **optional fragment**, requiring `org.awaitility:awaitility`, imports, and a defined repository; it is **not part of the sample build**. Use bounded polling with clear error messages, never infinite polling. Also verify tests poll committed/visible state rather than a stale `EntityManager` cache.

## 10. Flakiness from System Time, Timezones, and Random Data

### 10.1. System Clock

Wrong:

```java
LocalDate expected = LocalDate.now();
// ... service performs work ...
assertThat(result.date()).isEqualTo(expected);
```

If the calendar day flips between the two calls (especially around midnight or DST), the assertion fails. Inject `Clock` and use `Clock.fixed` in unit tests. When testing timezones, use `Clock.fixed(instant, ZoneId.of("Asia/Ho_Chi_Minh"))` with an explicit expected `LocalDate`, never mutating the JVM-wide default timezone in concurrent tests.

### 10.2. Random Seeds

A test generating 1,000 records with `new Random()` without logging its seed is hard to reproduce on failure. Use a fixed seed:

```java
Random random = new Random(20261108L);
int value = random.nextInt(100);
assertThat(value).isBetween(0, 99);
```

This is a fragment. If property-based tests randomize seeds to explore broader inputs, **log the seed and shrinkable counterexample** on failure for exact replay—never shrug off random failures as flaky.

### 10.3. UUIDs and Unique Test Data

`UUID.randomUUID()` prevents collisions across test records when generating identifiers, though tests should never assert a literal UUID. Instead:
- Assert format/uniqueness per contract.
- Clean up by test-generated namespace/ID.
- On failure, log the generated ID for traceability.
- Never rely on ID-generation order across multiple threads.
- In DB tests, use isolated schemas/databases if any integration test runs a truncate-all.

Random IDs cut collisions, yet **provide zero transactional isolation** against a `DELETE FROM table` wiping the whole table.

## 11. JUnit Parallelism, Gradle Forks, and Race Conditions

A suite may pass with `maxParallelForks=1` and break at 4. Distinguish:
- Gradle `maxParallelForks`: max concurrent **test JVM processes** for one `Test` task.
- `--max-workers`: total worker budget across the Gradle build.
- JUnit Jupiter parallel config: threads/classes/methods inside each JVM.
- `@ResourceLock`: coordinates resource access within one JUnit execution plan; **does not lock across two JVM forks**.
- `@Isolated`: isolates a class inside one JUnit plan, **not** across separate Gradle forks.
- `@TempDir`: creates unique paths per test, working safely across methods and JVMs.

Never blame the Gradle plugin and turn on retries when parallelism turns tests red. Inspect worker ID/PID/threads, locate shared state, and isolate fixtures.

### 11.1. Observing Process and Thread

```java
System.out.println(
    "gradleWorker="
        + System.getProperty("org.gradle.test.worker", "IDE")
        + " pid=" + ProcessHandle.current().pid()
        + " thread=" + Thread.currentThread().getName());
```

This is a diagnostic fragment. `org.gradle.test.worker` identifies the Gradle test worker **process**, not a method or thread name. When running in an IDE without delegating to Gradle, that property may be absent. Never assert a specific worker ID in JUnit.

### 11.2. When Does @ResourceLock Make Sense?

```java
@Test
@ResourceLock(
    value = Resources.SYSTEM_PROPERTIES,
    mode = ResourceAccessMode.READ_WRITE)
void modifiesSystemProperties() {
    String original = System.getProperty("feature.flag");
    try {
        System.setProperty("feature.flag", "true");
        // assertion...
    } finally {
        if (original == null) {
            System.clearProperty("feature.flag");
        } else {
            System.setProperty("feature.flag", original);
        }
    }
}
```

This fragment requires the corresponding JUnit imports. Both **the lock** and **restoring in `finally`** are essential. Another test omitting the lock can still mutate the system property, because `@ResourceLock` only coordinates nodes participating in Jupiter's lock manager.

If tests in two separate Gradle JVMs both write `build/report.json`, `@ResourceLock("report")` inside each JVM will not synchronize them; use per-worker paths or a true external lock.

## 12. Spring Boot TestContext and Spring-Specific Flakiness Causes

### 12.1. Spring ApplicationContext Cache

Spring TestContext caches and reuses `ApplicationContext` instances across test classes in the same JVM when configuration keys match. Great for speed, yet it means:
- Singleton beans with mutable fields can be dirtied by earlier tests.
- In-memory queues/caches/counters may carry leftover state.
- A test marked `@DirtiesContext` can tear down a context while parallel tests still depend on it.
- `@MockitoBean`/`@MockitoSpyBean` modify context beans; concurrent tests stubbing/resetting/verifying shared mocks can race.

Spring Framework docs advise against running tests concurrently when they use `@DirtiesContext`, mock bean overrides, or unisolated state/order dependencies.

**Proper fix:** use a serial lane, minimize context mutations, favor stateless beans or test-specific `@TestConfiguration`/fixtures; avoid slapping `@DirtiesContext` on every test just to "stay clean", which thrashes context startups and hides state design flaws.

### 12.2. @Transactional Rollbacks Do Not Cover Every Thread

A test:

```java
@SpringBootTest
@Transactional
class OrderTest {
    // ...
}
```

rolls back the **test-managed transaction** at the end of each method. However, `@SpringBootTest(webEnvironment=RANDOM_PORT)` runs request handlers on server threads with separate transactions that **commit for real** even when the test method rolls back. Likewise, `@Async` workers and broker consumers do not join the test thread's `ThreadLocal` transaction.

Under parallel runs, the same DB/schema accumulates rows a test assumed were rolled back, causing other tests to read them or hit unique constraint collisions.

**Proper fix:** isolate data by test ID/schema, clean up explicitly, avoid global truncates, assert real commits, and match Testcontainers DB engines. Never add retries to paper over state leaks.

### 12.3. @DataJpaTest and H2 Differ from Production DBs

`@DataJpaTest` defaults to an embedded database and test-managed transaction rollbacks. It suits persistence slices well, yet does not prove PostgreSQL locking, deadlocks, or isolation behavior. If failures surface only against CI's external DB, build dedicated integration tests with production-like Testcontainers, fixtures, and real transaction boundaries. **Never treat a passing retry as proof that SQL is sound.**

### 12.4. Spring Event Listeners and Commit Timing

`@EventListener` receives events synchronously on publish; `@TransactionalEventListener(AFTER_COMMIT)` waits for the enclosing transaction to commit. A `@Transactional` test that rolls back by default can prevent `AFTER_COMMIT` listeners from **ever firing**, silently.

If a test expects after-commit callbacks to run, commit a real transaction outside test-managed rollback, or use `TestTransaction.flagForCommit()` + `end()` appropriately. Retries do not change transaction phase semantics; a test "passing sometimes and failing sometimes" due to timing assumptions must be fixed at the transaction boundary.

### 12.5. ApplicationContext Startup / Condition Timing

When tests depend on an external Config Server, database, Redis, or mock HTTP server, properties like ports/URLs must be bound **before context refresh**. Use `@DynamicPropertySource` and dynamic random ports from Testcontainers/MockWebServer instead of hardcoded ports. If a dependency needs startup time, use its supported readiness wait strategy, never `Thread.sleep(3000)`.

If a context fails due to missing properties or unmatched `@ConditionalOnBean`, the failure is typically deterministic; hitting "rerun CI" will not fix bean configuration.

## 13. Testcontainers and External Services: Retries Can Worsen Things

An integration test using PostgreSQL Testcontainers can fail because:
- The Docker daemon is unavailable.
- Container image pull times out.
- The DB isn't ready or init scripts fail.
- Connection pools exceed limits across multiple Spring contexts.
- A reused container holds leftover data.
- Two forks target the same schema or fixed container name.
- Containers stop/restart between test methods.
- The CI runner runs out of disk or RAM.

**Read the exception chain before retrying:** `Connection refused`, `TimeoutException`, `BindException`, `PSQLException`, and `NoSuchBeanDefinitionException` point in very different directions. Never lump them all under "flaky".

### 13.1. Prevent Startup Failures with Readiness, Not Sleep

Example fragment with Testcontainers PostgreSQL:

```java
@Container
static PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine");

@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.datasource.url", postgres::getJdbcUrl);
    registry.add(
        "spring.datasource.username", postgres::getUsername);
    registry.add(
        "spring.datasource.password", postgres::getPassword);
}
```

This is a **configuration fragment**, not part of the runnable project in section 7, requiring Testcontainers/JDBC/PostgreSQL dependencies, `@Testcontainers`, imports, and lifecycle setup. Testcontainers handles readiness waits and dynamic hosts/ports. Never hardcode `localhost:5432` for random mapped ports, and never target a production database.

### 13.2. Cleanup Before Retry Must Be Idempotent

If a test sends an external message, creates an order, triggers a fake charge, or writes to object storage, attempt 1 may have **completed the side effect** before timing out on the assertion. Retrying then fires attempt 2:
- Duplicate messages.
- Duplicate rows / unique constraint failures.
- Mismatched mock/fake invocation counts.
- Duplicate audit events.
- Corrupted fixtures from skipped cleanup.

Therefore, any retryable integration test needs unique IDs and **idempotency/cleanup** built in. For payment-like contracts, never allow JUnit retries to hit real production financial APIs. Use sandboxes/test doubles, idempotency keys, and network isolation policies.

## 14. Separating Real Application Bugs from Flaky Tests

One of the greatest dangers is labeling an app race condition as "just a flaky test." Examples:
- Two concurrent `reserveStock()` calls occasionally oversell inventory.
- HTTP clients time out under realistic latency.
- Unique constraint races across multiple nodes.
- Outbox events occasionally get lost on process crashes.
- Cache invalidation or transaction callbacks fire slightly too early.

Even if a JUnit rerun passes, the root cause may be a **production concurrency bug**. Approach:
1. Build a minimal reproducer with controlled scheduling or fault injection.
2. Log correlation/trace IDs, random seeds, and DB isolation levels.
3. Run dedicated stress or concurrency tests where appropriate.
4. Fix invariants in production code (unique constraints, locks, transactions, idempotency)—never just add sleeps.
5. Keep deterministic regression tests using latches, barriers, or fake clocks.

**Lesson:** Retries help classify nondeterminism, never justify blaming "slow CI" automatically.

## 15. Quarantine: Acceptable Only with Ownership and a Path Back

An unfixed flaky test can block every PR, leading teams to move it to a **quarantine lane**. Done carelessly, quarantine simply **deletes coverage silently**.

A responsible process:
1. File an issue with an owner, discovery date, failure signature, first-attempt logs, CI environment, and test link.
2. Document the real reason: test causes noise yet must not be abandoned; note which contract loses PR coverage temporarily.
3. Set an **expiration/review deadline** based on severity (e.g., one sprint, or days for critical paths).
4. Apply `@Tag("quarantine")` to the test class or method per JUnit tag policy.
5. Main `test` task applies `excludeTags 'quarantine'`, **while** `quarantineTest` executes the quarantined set regularly (e.g., nightly).
6. Track failure rates and issue owners; surface quarantined tests on a visible dashboard.
7. Once fixed, remove the tag and restore the test to the main gate without leaving duplicate tests behind.

**Limitation of this example:** `quarantineTest` is registered in `build.gradle`, yet zero tests currently carry `@Tag("quarantine")`. Running it now selects zero tests; that is **not** a "quarantine suite pass". Tag a test for quarantine only when an actual issue and owner exist.

### 15.1. Never Use @Disabled as "Permanent Quarantine"

`@Disabled` stops execution entirely; most CI dashboards show it as skipped with zero visibility into whether it still fails. With `@Tag("quarantine")` and a dedicated task, the test still executes periodically so you collect failure data and spot when it stabilizes. Setting `retry.maxRetries=0` on the quarantine lane exposes raw first-attempt failures cleanly rather than hiding them behind "quarantine + 10 retries".

### 15.2. Quarantine Does Not Excuse Skipping Critical Bug Gates

Never quarantine a test catching security bugs, double charging, data loss, authorization bypasses, or destructive schema migrations just because it turns PRs red. Critical defects must **block releases or receive immediate mitigation**. Quarantine decisions depend on risk and coverage impact, not solely CI minutes.

### 15.3. Policy Maturity

| Level | Practice | Limitations |
|---|---|---|
| M0: Infinite manual reruns | Developers click rerun until green | Hides bugs and wastes CI |
| M1: Bounded retry | Plugin `maxRetries=1/2` | Surfaces flakiness signal without governance |
| M2: Retry + strict gate + reporting | `failOnPassedAfterRetry=true`, preserve first failures | Can increase red builds on weak legacy suites |
| M3: Owner/issue/quarantine TTL | Metrics and prioritized fixes | Prevents permanent coverage abandonment |
| M4: Root-cause prevention | Clock injection, isolation, deterministic async, env contracts | Engineering investment that yields long-term reliability |

The destination is not "more retries", but **high first-attempt pass rates and minimal hidden external state**.

## 16. Tagging and Grouping to Avoid Wasted Retries

JUnit Jupiter `@Tag` separates tests into `unit`, `integration`, `slow`, `external`, `quarantine`, and `diagnostic`. Remember that **tag selection and retry eligibility are separate layers**.

In the sample build:
- `test` runs all Jupiter tests **except** `quarantine` and `diagnostic`.
- `diagnosticTest` selects only `diagnostic`.
- `quarantineTest` selects only `quarantine`.
- Java plugin `check` runs `test`; it does not run the two custom tasks automatically.

Larger projects can expand further:
- `unitTest`: zero retries, or strict single retry to detect rare leaks.
- `integrationTest`: `maxRetries=1`, low `maxFailures`, isolated environment.
- `externalContractTest`: local stubs on PRs; real contracts in dedicated sandbox jobs.
- `flakyDiagnosticTest`: dedicated repetition/stress lane excluded from normal PR gates.
- `quarantineTest`: tracked by issues, failing visibly until fixed.

### 16.1. Trap When CI Only Runs the test Task

If a test is moved into `quarantineTest` yet CI never schedules that task, keeping the test in source **does not mean it ever runs**. Likewise, `@Tag("diagnostic")` is excluded from `test`; verify which tasks schedule it.

Reports should track **discovered/selected/executed/skipped** counts per task rather than counting `@Test` annotations in the repo.

### 16.2. --tests Does Not Override includeTags/excludeTags

```bash
./gradlew test --tests "*CheckoutServiceTest.fixedClockMakesProcessedDateStable"
```

This runs one method inside the `test` task. However, if a test carries `@Tag("quarantine")`, `--tests` does not lift `excludeTags 'quarantine'` from `test`. Invoke `quarantineTest --tests ...` so the task policy selects it. Always distinguish **test name filters** from **JUnit tag filters**.

## 17. CI: Triage Workflow Before Enabling or Raising Retries

### 17.1. Same-Day Triage Procedure

**Step 1 — Preserve initial evidence.** Save full stack traces, test names, test reports, console output, Gradle worker ID/PID, commit SHA, Java/Gradle versions, DB/container versions, CI node specs, and random seeds if used. Never rerun before archiving the first failure.

**Step 2 — Classify the failure.** `AssertionError` does not imply flakiness. `Connection refused` across 30 tests simultaneously points to infrastructure. `ConcurrentModificationException` points to shared state. `NoSuchBeanDefinitionException` often points to deterministic context/config issues.

**Step 3 — Reproduce narrowly.**
```bash
./gradlew test --tests "com.example.retrylab.CheckoutServiceTest"
```
Match the exact class/method and CI-like environment. If it doesn't reproduce alone, vary suite order, parallel/forks, seeds, and resources.

**Step 4 — Eliminate hidden factors.** Inject fixed `Clock`, use `@TempDir`, unique IDs, controlled executors/latches, dynamic ports, isolated DB schemas, and strict fixture ownership.

**Step 5 — Verify regression fix.** After fixing, run targeted tests repeatedly with bounded deadlines, then full parallel suites and CI—never stop after one local pass.

**Step 6 — Close the issue with proof.** Link the PR, root cause, measured first-attempt pass rate over a sufficient window, removal of the `quarantine` tag, and inclusion in `check`.

### 17.2. Reproducing Failures That Only Appear in Full Suites

```bash
./gradlew clean test --max-workers=1
./gradlew clean test --max-workers=4
```

These commands change Gradle's total worker budget, yet with `maxParallelForks=1` in the sample build, `test` still uses one fork. To test cross-process contention, **adjust task `maxParallelForks`** via a test branch or Gradle property rather than expecting `--max-workers` alone to add forks.

If JUnit parallelism is enabled via `junit-platform.properties`, lowering Gradle forks does not turn off concurrent Jupiter threads. Isolate one layer at a time to locate the root cause.

### 17.3. Never Retry Spring Context Startup Failures

If `@SpringBootTest` fails due to a missing required property or a bean blocked by `@ConditionalOnClass`, that is likely a consistent configuration error. Retries do not repair classpaths. Inspect `ConditionEvaluationReport`, active profiles, `@DynamicPropertySource`, configuration imports, and stack traces instead of blaming flakiness.

## 18. Retry Metrics and SLOs for Test Quality

To tell whether CI reliability is genuinely improving or merely "green via retries", track:

| Metric | Definition | Why It Matters |
|---|---|---|
| First-attempt failure rate | First-run failures / total tests | Measures raw signal quality |
| Pass-after-retry rate | Failures passing on retry / total initial failures | Quantifies visible flakiness |
| Permanently failed test count | Tests still failing after max attempts | Separates unresolved defects |
| Retry amplification | Total executions / unique selected tests | Measures CI cost of retries |
| Quarantine inventory | Quarantined count, owners, deadlines | Tracks temporarily disabled coverage |
| Mean time to fix flaky issue | Time from detection to root-cause fix | Measures remediation speed |
| CI build wall-clock p50/p95 | Job duration percentiles | Spots retry-induced slowdowns |
| Skipped/untagged count | Tests omitted by filters/disables | Prevents silent coverage loss |
| Environment incident count | Docker/DB/runner outages failing batches | Separates infra from test quality |

Never rely on `build pass rate` alone. Flipping `failOnPassedAfterRetry=false` spikes pipeline green rates overnight while first-attempt failures stay unchanged.

### 18.1. What Belongs in a Triage Issue/Record?

A solid triage record includes:
- Test: `com.example...AsyncReceiptServiceTest.asyncResultIsWaitedForRatherThanSleptFor`.
- First failure: `TimeoutException` after deadline, timestamp, and stack trace.
- Retry outcome: pass or fail, attempt count—never just final status.
- Environment: CI runner CPU quota, Java 17 build, Gradle, fork/parallel config.
- Suspected cause: executor starvation, thread leak, dependency readiness, or tight timeout.
- Owner, issue link, severity, date detected, deadline.
- Fix evidence: PR commit + repeated targeted and full-suite CI runs.
- Quarantine status: active/expired/removed with rationale.

Never store production credentials, PII, or customer payloads inside test artifacts or triage logs.

## 19. Example "Time-Bounded Quarantine" Policy

Sample policy for a team:
1. Allow quarantine only when first-attempt failures have captured evidence and the test does not guard critical security/data-integrity contracts.
2. Every quarantined item requires an owner and review deadline—no "flaky, ignore" comments.
3. `quarantineTest` must run nightly or on a regular schedule rather than turning into dead code.
4. Keep retries at `0` in the quarantine lane to preserve raw first failures; run repetition/stress tests in a separate diagnostic job.
5. Release builds must explicitly review any known flaky critical paths rather than shipping blindly on green PRs.
6. Overdue quarantines trigger escalation rather than automatic infinite extensions.
7. Fix the root cause, strip the `quarantine` tag, and verify the test returns to the main gate.
8. Track new flake rates and time-to-fix rather than judging teams purely by green build percentages.

**This is a sample policy, not a universal corporate mandate.** Teams can tune deadlines and severity tiers while preserving the core rule: **never hide failures and never lose test coverage silently**.

## 20. Troubleshooting Retry Configurations

| Symptom | Possible Cause | Action |
|---|---|---|
| Plugin applied yet tests never retry | Default `maxRetries=0` or `CI` env var missing | Check `retry` on the exact `Test` task |
| Local skips retry, CI retries | `onCi` condition in build script | Intentional policy in the sample |
| Thought `maxRetries=1` meant two retries | Misreading "retry" | Initial attempt + **one** extra attempt |
| Fail→pass still leaves Gradle task red | `failOnPassedAfterRetry=true` | Expected strict policy; fix the flaky test |
| Fail→pass turns Gradle task green | `failOnPassedAfterRetry=false` or different gate reporter | Check policy/reports; never discard initial failures |
| Mass failures stop retrying | `maxFailures` threshold reached | Check DB/Docker/runner outage |
| `@ParameterizedTest` re-runs all args | Method-level retry granularity | Keep cases idempotent and split large matrices |
| `@RepeatedTest(5)` runs 5x despite passing | Planned repetition, not retry | Move to dedicated diagnostic task |
| `--rerun-tasks` re-runs too many tests | Reruns Gradle task, not failing-only | Use `--tests` or retry plugin for targeted runs |
| `--tests` finds zero tests | Name filter + tags/exclusions | Pick matching task and inspect filters |
| IDE runs without retry while Gradle retries | IDE does not delegate to Gradle test runner | Run via Gradle task to test retry policy |
| XML reports fail while Gradle task passes | CI XML parser reads initial failed attempt | Check `mergeReruns` and CI parser semantics |
| XML looks green despite flaky test | Parser ignores `<flakyFailure>` | Use flake-aware dashboard or `mergeReruns=false` |
| Retry fails on dirty data | Attempt 1 side effects not cleaned up | Use unique IDs, rollback/cleanup, idempotency |
| Spring context fails after attempt 1 | Shared state, `@DirtiesContext`, Mockito overrides | Fix isolation / move to serial lane |
| Passes on retry after raising `Thread.sleep` | Race merely masked temporarily | Switch to latch/`Future`/Awaitility with deadline |
| Time test fails near midnight | Used wall clock | Inject `Clock.fixed` |
| Fails only with multiple forks | Shared DB/file/port/containers | Per-fork resources, `@TempDir` |
| Timeouts in CI | CPU throttling, deadlock, network | Capture thread dumps/futures, fix root cause |
| External provider returns 429 | Rate limits/quotas | Stub unit tests; dedicated sandbox contract policy |
| Green build with zero tests executed | `UP-TO-DATE`, `FROM-CACHE`, filters/`no-source` | Check task outcomes and test reports |
| Retries multiply CI duration | Too many retries / slow fixture boots | Lower attempts, fix root causes |
| Plugin filter ignores method annotation | Filters operate on reported class names/annotations | Use supported filter API; do not confuse with JUnit tags |
| Quarantined tests never run | No scheduler/job invokes `quarantineTest` | Add nightly job and reporting |
| Failed test skips on retry | Conditional disable or engine state shift | Keep `failOnSkippedAfterRetry=true` and investigate |

## 21. Commands and Verifying Properly

Once the project is created with a compatible Gradle wrapper:

```bash
# Local (no CI env var): normal test run, retries off
./gradlew test

# Run a single test method for debugging
./gradlew test --tests "com.example.retrylab.CheckoutServiceTest.fixedClockMakesProcessedDateStable"

# POSIX shell CI invocation: enables retry via env var
CI=true ./gradlew test

# Diagnostic lane: one @RepeatedTest yielding 5 invocations
./gradlew diagnosticTest

# Run verification lifecycle (runs test, does not run diagnostic automatically)
./gradlew check

# Force Gradle to re-execute tasks instead of trusting up-to-date
./gradlew test --rerun-tasks
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests "com.example.retrylab.CheckoutServiceTest.fixedClockMakesProcessedDateStable"

$env:CI = "true"
.\gradlew.bat test
Remove-Item Env:CI

.\gradlew.bat diagnosticTest
```

**Note:** This sample build **does not ship Gradle wrapper files**, so `./gradlew` only works once you add a compatible wrapper; if Gradle is installed locally, run `gradle wrapper`. Do not assume exact stdout; the environment needs a Java 17 toolchain and repository access on first build to resolve dependencies (runtime tests need no external app services). "No external services" describes **test runtime**, not offline builds before dependencies are cached.

### 21.1. Counting Source Tests vs. Invocations

| Task | Selected Sources | Designed Counts |
|---|---|---:|
| `test` | `CheckoutServiceTest` + `AsyncReceiptServiceTest` + `ReceiptFileWriterTest` + `CheckoutSpringTest` | **11 `@Test` methods** |
| `diagnosticTest` | `StabilityRepetitionTest` | **1 `@RepeatedTest` method, 5 invocations** |
| `quarantineTest` | No tests carry `quarantine` initially | **0 selected tests** |
| `check` | Java plugin `test` dependency | **11 `@Test` methods** in sample |
| `test` with first-attempt failure + CI retry | Same initial selection + retries of failed tests | Total executions may exceed 11 |

Counts in the table come from the **sample source and task filters**, not confirmed execution logs. When using `@ParameterizedTest`, `@RepeatedTest`, dynamic tests, or retries, always distinguish **test methods**, **JUnit invocations**, and **total execution attempts**.

### 21.2. Inspecting Per-Task Artifacts

```text
build/reports/tests/test/index.html
build/test-results/test/

build/reports/tests/diagnosticTest/index.html
build/test-results/diagnosticTest/

build/reports/tests/quarantineTest/index.html
build/test-results/quarantineTest/
```

When a test is retried, inspect **all attempts**, not just the final green result. If `test` reports `UP-TO-DATE` because inputs didn't change, that is neither a retry nor fresh proof of a first-attempt pass in the current run. When reproducing flakiness, run targeted tests with `--rerun-tasks`, capture logs, and record the CI environment fingerprint.

### 21.3. Testing the Retry Plugin Without Making the Normal Suite Flaky

To verify the retry plugin works for real, create an **isolated integration fixture** on a dedicated branch/test project for plugin validation:
1. Write a test controlled by an explicit input/marker so attempt 1 fails and attempt 2 passes—**never use random probability**.
2. Run the fixture via Gradle with `maxRetries=1`.
3. Verify the Gradle exit status honors `failOnPassedAfterRetry` and the XML report records two executions.
4. Remove the fixture or keep it in a separate plugin-validation project outside main `test`.
5. Never rely solely on a JVM static counter if retries spawn separate processes or classloaders; design state per the fixture's lifecycle.

This is a standalone verification exercise, **not part of the normal project suite**. The goal is to avoid shipping synthetic flaky tests into PR gates.

## 22. Qualities to Preserve After Fixing a Flaky Test

A proper fix does more than "bump the timeout." Verify:
- Does the test still verify the real business requirement rather than relaxing assertions so bugs slip by?
- Did you pinpoint the **root cause**: clock, shared state, async completion, DB transaction, context cache, port conflict, or external dependency?
- Did you test it standalone and in parallel under CI-like load?
- Does cleanup run in `finally`/`@AfterEach` without wiping other tests' state?
- Are unique IDs/schemas/paths used to prevent cross-test interference?
- Is `@DirtiesContext` genuinely required and safe with respect to concurrent tests?
- Were first-failure artifacts preserved to compare before vs. after?
- Was the `quarantine` tag removed and the test re-enabled in `test` / `check`?
- Did tests execute for real rather than caching/skipping/`NO-SOURCE`?
- Do CI metrics show rising first-attempt pass rates rather than merely more pass-on-retries?

**Never "fix" a flaky test by deleting critical assertions, leaving `@Disabled` indefinitely, or cranking up retries until it happens to turn green.** That trades a quality signal for a coverage blind spot.

## 23. CI Operations Checklist

- [ ] On every failure, archive stack traces and reports from the **first attempt** before retrying or rerunning jobs.
- [ ] Distinguish deterministic bugs, flaky tests, intermittent product failures, and environment outages.
- [ ] Remember `maxRetries=1` means **initial attempt + 1 retry**.
- [ ] Enable retries only on Gradle `Test` tasks with an explicit policy.
- [ ] Set `maxFailures` to halt retry storms when environment outages fail many tests.
- [ ] Define `failOnPassedAfterRetry` and `failOnSkippedAfterRetry` intentionally.
- [ ] Never set `ignoreFailures=true` to mask errors.
- [ ] Never mistake `@RepeatedTest` for Gradle retry-on-failure.
- [ ] Never mistake `--rerun-tasks` for retrying only failing tests.
- [ ] Avoid stacking multiple retry layers (JUnit/Gradle/CI) without an attempt budget.
- [ ] Remember `@ParameterizedTest` can retry the entire method across all rows.
- [ ] Ensure no test sends real production emails/payments/messages on retry.
- [ ] Never rely on `Thread.sleep` to guess async completion.
- [ ] Await `Future`/latch/Awaitility with deadlines and assert real outcomes.
- [ ] Inject `Clock` and control random seeds and timezones.
- [ ] Use `@TempDir`/unique test IDs and ownership-scoped cleanup.
- [ ] Never treat `@ResourceLock` as a distributed lock across Gradle forks.
- [ ] Isolate Spring contexts, `@DirtiesContext`, Mockito overrides, and DB fixtures.
- [ ] Remember test-thread `@Transactional` does not cover HTTP/async threads.
- [ ] Handle Testcontainers readiness and dynamic ports properly.
- [ ] Ensure quarantines have issues, owners, deadlines, and scheduled execution.
- [ ] Never quarantine security or data-integrity regressions.
- [ ] Publish HTML/XML reports for every executed test task.
- [ ] Understand how `mergeReruns` affects your CI XML parser.
- [ ] Track first-attempt failures and pass-on-retry metrics.
- [ ] Never report `UP-TO-DATE`/`FROM-CACHE` as a fresh execution.
- [ ] Verify root-cause fixes across representative CI runs afterward.
- [ ] Never claim runtime tests passed without actually running Gradle/JUnit.

## 24. Official Sources and Further Reading

- [Gradle Test Retry Plugin — Gradle Plugin Portal 1.6.6](https://plugins.gradle.org/plugin/org.gradle.test-retry/1.6.6): plugin ID, version, Groovy/Kotlin DSL setup.
- [Gradle Test Retry Plugin — Official README](https://github.com/gradle/test-retry-gradle-plugin): `maxRetries`, `maxFailures`, `failOnPassedAfterRetry`, filters, parameterized retries, reporting.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `Test` tasks, `--tests`, reports, `mergeReruns`, `failFast`, `ignoreFailures`.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--rerun-tasks`, `--max-workers`, `--continue`, task selection.
- [JUnit Jupiter — Repeated Tests](https://docs.junit.org/5.14.2/writing-tests/repeated-tests.html): `@RepeatedTest`, `RepetitionInfo`, invocation counts.
- [JUnit Jupiter — Tagging and Filtering](https://docs.junit.org/5.14.2/writing-tests/tagging-and-filtering.html): `@Tag`, including/excluding diagnostic/quarantine groups.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/): `@SpringBootTest`, test slices, Spring Boot starter-test.
- [Spring Framework — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html): Spring context cache, `@DirtiesContext`, mock overrides, shared state.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollbacks, thread boundaries, and `TestTransaction`.
- [Testcontainers — Java Quickstart](https://java.testcontainers.org/quickstart/junit_5_quickstart/): container lifecycle, JUnit 5 support, and readiness.
- [Gradle Blog — Handling Flaky Tests](https://blog.gradle.org/how-we-handle-flaky-tests-in-gradle): retries and failure triage workflows.

**Conclusion:** When a JUnit test fails first and passes on rerun, that is **a signal demanding investigation**, never proof that the system is healthy. `Gradle Test Retry Plugin` enables bounded retries with attempt tracking; `failOnPassedAfterRetry=true` prevents CI from masking flakiness silently. `@RepeatedTest`, `--rerun-tasks`, and CI job reruns solve distinct problems. Fix root causes via test isolation, fixed clocks, deterministic async awaits, clean DB/transaction boundaries, resource readiness, and independent fixtures; apply quarantine only with ownership and expiration while monitoring first-attempt pass rates and reports. A trustworthy pipeline is one that **detects real bugs consistently**, not one that retries until luck turns it green.