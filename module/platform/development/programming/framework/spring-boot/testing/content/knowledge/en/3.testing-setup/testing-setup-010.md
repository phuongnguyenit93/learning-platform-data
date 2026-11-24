# Reading Error Reports, Stack Traces, and Verifying Which Tests Actually Ran in Spring Boot

## 1. Why you cannot just look at `BUILD SUCCESSFUL` or `BUILD FAILED`

Automated testing is valuable when we know **which tests were selected, which tests actually executed, which were skipped, and at which step a failure occurred**. `BUILD SUCCESSFUL` only tells you that the requested tasks finished without error under the current configuration; it does not prove every test case in the repository ran. Likewise, `BUILD FAILED` does not necessarily mean an application assertion is wrong: a build can fail while compiling tests, preparing a database, starting a Spring context, or fetching dependencies.

For any given run, a reader should answer four questions:

1. **Which command was invoked, in which module and environment?** For example `./gradlew test`, `./mvnw test`, `./mvnw verify`, or a filtered class/method command.
2. **How many tests were recorded and what was each case's status?** Class name, method/invocation name, pass, failure, error, and skipped counts.
3. **When did the failure happen?** Before JUnit discovered tests, during setup/context startup, during an assertion, or during cleanup?
4. **What evidence points to the root cause?** Expected/actual messages, the `Caused by` chain, frames belonging to project source code, and reproducing inputs.

Distinguish five levels: **test file exists** → **test task requested** → **test discovered by JUnit** → **test case executed** → **test case passed**. These five are not equivalent.

## 2. Systematic workflow for reading test results

```text
Build command / CI job
  └─ Compile source, compile test source
      └─ Gradle test task / Maven test goal
          └─ JUnit Platform discovers and selects tests
              ├─ Execute test: PASS / FAILURE / ERROR
              ├─ Conditional skip: SKIPPED / ABORTED
              └─ Not discovered or filtered out: no execution record
          └─ Console and HTML / XML / TXT reports
```

Read in the order **command → task/goal → summary report → specific test case → stack trace → root cause**. Jumping straight to an arbitrary exception line in the console makes it easy to mistake an infrastructure error for a business logic bug.

| Signal | What you can conclude | What you CANNOT conclude on its own |
|---|---|---|
| Main and test sources compiled cleanly | Compilation succeeded within that scope | JUnit ran the tests |
| Gradle `:test` task has a report with testcases | That task recorded those test results | Every suite in the project ran |
| Maven Surefire: `Tests run: 4` | Surefire recorded four runs in that scope | Failsafe integration tests ran |
| `BUILD SUCCESSFUL` | Build succeeded per config and requested tasks | Tests freshly executed on this run |
| `BUILD FAILED` | A task/goal failed | It is definitely an assertion failure |
| `skipped` | The test was recorded as skipped | Business behavior is verified |
| A test name is absent from a report | No evidence it ran in the inspected report | The test definitely does not exist |

## 3. Finding Gradle reports

In a Spring Boot project with the Gradle wrapper, run from the project directory:

```bash
./gradlew test
```

On Windows PowerShell: `.\gradlew.bat test`.

With a test task named `test` and standard configuration, outputs are written to:

| Where to look | Information to read |
|---|---|
| `build/reports/tests/test/index.html` | HTML report, test class/method list, statistics, failures, and stack traces |
| `build/test-results/test/TEST-*.xml` | XML report with testcases and statuses for CI |
| Console output of `:test` | Whether the task ran or was `UP-TO-DATE`, `FROM-CACHE`, `SKIPPED`, `NO-SOURCE`; failure summary and report link |

In multi-module projects, paths live inside each module's directory. If custom tasks like `integrationTest` or `functionalTest` are configured, reports and results typically follow the task name; **never use `test`'s report to conclude another task ran**.

Run a specific class:

```bash
./gradlew test --tests "com.example.testing.ShippingFeePolicyTest"
```

Run a single method:

```bash
./gradlew test --tests "com.example.testing.ShippingFeePolicyTest.atThresholdIsFree"
```

These are **run-request filters**, not proof on their own that tests were discovered and executed. In projects using JUnit Jupiter, the Gradle test task needs matching JUnit Platform configuration, typically `useJUnitPlatform()`. Reading the report of the exact task gives the final answer.

### Proof of fresh execution or reused results?

- `UP-TO-DATE`: Gradle determined existing outputs remain valid for declared inputs and skipped re-running the task.
- `FROM-CACHE`: the task restored outputs from the build cache.
- `SKIPPED` or `NO-SOURCE`: the task did not execute tests due to a skip condition or missing matching sources.
- `BUILD SUCCESSFUL` following any of these states **does not mean tests freshly executed during that invocation**.

If you need to confirm tests execute afresh rather than reusing old outputs, use `./gradlew test --rerun-tasks`, with `--tests` if filtering. Then check the task outcome and new run's report. Avoid wiping the entire build directory when you only need to verify one class.

## 4. Finding Maven reports

With the Maven wrapper:

```bash
./mvnw test
```

On Windows PowerShell: `.\mvnw.cmd test`.

With Maven Surefire running unit tests in the `test` phase, common locations are:

| Where to look | Information to read |
|---|---|
| `target/surefire-reports/TEST-*.xml` | Test suite, testcases, counts, failures/errors/skipped |
| `target/surefire-reports/*.txt` | Summary and per-class details |
| Surefire console output | `Tests run`, `Failures`, `Errors`, `Skipped`, and related report paths |

Run a single class with Surefire:

```bash
./mvnw -Dtest=ShippingFeePolicyTest test
```

If a module uses Maven Failsafe for integration tests, they usually belong to the `integration-test` and `verify` phases, writing reports to `target/failsafe-reports/`. A passing `./mvnw test` **does not prove** Failsafe-managed integration tests ran; inspect the actual configuration and run through `verify` when appropriate.

In multi-module Maven projects, each module has its own `target/` directory. Verify the module, commit, CI job, and run before reading files. `-Dtest=...` filters Surefire scope; `-DskipTests` usually skips test execution, while `-Dmaven.test.skip=true` can skip compiling tests as well. Exact plugin behavior depends on project configuration, so treat logs as evidence.

## 5. Java 17+ example intentionally producing an assertion failure

Suppose shipping fee rules are: orders with subtotal **500,000 VND or higher** get free shipping; below the threshold costs 30,000 VND; negative subtotals are rejected.

The service code below intentionally has a bug `>` instead of `>=`. This is complete Java code inside a Spring Boot project with Java 17+ and `spring-boot-starter-test`.

File `src/main/java/com/example/testing/ShippingFeePolicy.java`:

```java
package com.example.testing;

public final class ShippingFeePolicy {
    public int fee(int subtotal) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be nonnegative");
        }
        return subtotal > 500_000 ? 0 : 30_000; // Bug: not free at the threshold
    }
}
```

File `src/test/java/com/example/testing/ShippingFeePolicyTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeePolicyTest {
    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void belowThresholdIsCharged() {
        assertEquals(30_000, policy.fee(499_999));
    }

    @Test
    void atThresholdIsFree() {
        assertEquals(0, policy.fee(500_000));
    }

    @Test
    void aboveThresholdIsFree() {
        assertEquals(0, policy.fee(500_001));
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class, () -> policy.fee(-1));
    }
}
```

This unit test instantiates `ShippingFeePolicy` directly without starting a Spring context. If JUnit Jupiter is configured and executes all four cases, **three cases pass; `atThresholdIsFree` fails**. For input 500,000, the service returns 30,000 while the test expects 0.

Illustrative Surefire console lines might show:

```text
Tests run: 4, Failures: 1, Errors: 0, Skipped: 0
com.example.testing.ShippingFeePolicyTest.atThresholdIsFree
org.opentest4j.AssertionFailedError: expected: <0> but was: <30000>
```

**Illustrative** abbreviated stack trace, not log output from a real build:

```text
org.opentest4j.AssertionFailedError: expected: <0> but was: <30000>
    at org.junit.jupiter.api.AssertionFailureBuilder.build(...)
    at org.junit.jupiter.api.AssertEquals.assertEquals(...)
    at com.example.testing.ShippingFeePolicyTest.atThresholdIsFree(
        ShippingFeePolicyTest.java:<line>)
```

`...` and `<line>` represent omitted details. Line numbers, order, and internal JUnit classes vary by version and actual file.

How to read it:
- **Failing case:** `ShippingFeePolicyTest.atThresholdIsFree`.
- **Expected:** 0; **actual:** 30,000. This is an assertion mismatch, not a Spring bean creation failure.
- **Test frame:** points to the `assertEquals` line; inspect `fee(500_000)` and trace the service logic.
- **Root cause:** the condition `subtotal > 500_000` excludes the exact 500,000 threshold.
- **Execution scope:** if the report accurately records four tests, three passed and one failed; do not extrapolate that tests in other classes/modules ran.

Fix production code to:

```java
return subtotal >= 500_000 ? 0 : 30_000;
```

Under the stated rule, all four assertions will hold against the new implementation. However, in real project reporting, declare `PASS` only after re-running tests and reading the new report.

## 6. Reading XML to identify recorded cases

An illustrative JUnit-style XML report has this structure:

```xml
<testsuite name="com.example.testing.ShippingFeePolicyTest"
           tests="4" failures="1" errors="0" skipped="0">
  <testcase classname="com.example.testing.ShippingFeePolicyTest"
            name="belowThresholdIsCharged"/>
  <testcase classname="com.example.testing.ShippingFeePolicyTest"
            name="atThresholdIsFree">
    <failure type="org.opentest4j.AssertionFailedError"
             message="expected: &lt;0&gt; but was: &lt;30000&gt;"/>
  </testcase>
  <testcase classname="com.example.testing.ShippingFeePolicyTest"
            name="aboveThresholdIsFree"/>
  <testcase classname="com.example.testing.ShippingFeePolicyTest"
            name="negativeSubtotalIsRejected"/>
</testsuite>
```

This is a **sample for practicing XML structure**, not output copied from a live Maven/Gradle run.

- `testsuite`: a test group reported by the runner, usually corresponding to a class.
- `tests`: total test runs recorded for the suite in this report.
- `failures`: runs that failed due to assertions or were classified by the runner as failures.
- `errors`: other exceptions/errors if the runner distinguishes them; inspect individual testcases since classification can vary.
- `skipped`: runs marked as skipped.
- `testcase classname + name`: identifies the class and test run recorded in the report.
- Child elements `failure`, `error`, or `skipped` indicate status; a complete `testcase` without them generally indicates a pass.

**Do not count Java methods to infer execution counts.** `@ParameterizedTest` and `@RepeatedTest` produce multiple runs for one method; `@Nested` produces nested class names; `@DisplayName` can differ from the method name. With `@TestFactory` dynamic tests, runs are also reported according to the runner's model. Inspect each `testcase`/invocation in the exact run's report.

If a test **does not appear** in the report, it may have been excluded by a filter, undiscovered by JUnit, located in another task, or you are looking at the wrong report. If a test appears as `skipped`, it **must not be counted as having executed successfully**.

## 7. Reading stack traces: from top error to root cause in source

A Java stack trace may include:
- **Exception name and message**: `AssertionFailedError`, `NullPointerException`, `IllegalStateException`, `BeanCreationException`.
- **`at ...` lines**: call stack order, often with `SomeFile.java:42`.
- **`Caused by:`**: underlying exception wrapped across layers.
- **`Suppressed:`**: secondary exceptions (e.g., resource-closing errors), not necessarily the main cause.

Follow this sequence:

1. From the report, find the exact failing class/method; do not grab a random exception from another test's logs.
2. Read the top exception and message. `expected/actual` usually means an assertion mismatch, whereas `Failed to load ApplicationContext` points to Spring setup.
3. Follow `Caused by` when present: dig down to a cause with actionable information. The key cause is often near the end of the chain, though not always the very last line.
4. Locate frames belonging to project source (`com.example....`) instead of staring at dozens of JUnit, Spring, Gradle, or Surefire frames.
5. Open the exact version of the file named in that frame and inspect data/fixtures. The test frame usually marks **where the mismatch was detected**; a frame inside a service or repository may mark where an exception was thrown.
6. Identify the failing phase: compile, context initialization, setup, test body, teardown, or infrastructure. If it failed before the test body, you cannot claim the business method was tested.
7. Fix the root cause, rerun the same case and related tests, and confirm using the fresh results.

### 7.1. Assertion failure

```text
org.opentest4j.AssertionFailedError:
expected: <0> but was: <30000>
```

Focus on **the assertion inputs**, expected contract, production code path, and actual value. Never change `expected` to match wrong output just to make the test green.

### 7.2. Spring context failed to initialize

An illustrative trace:

```text
java.lang.IllegalStateException: Failed to load ApplicationContext
    ...
Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
    Error creating bean with name 'orderService'
    ...
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
    No qualifying bean of type 'com.example.payment.PaymentClient' available
```

The root error points to a missing `PaymentClient` bean required to construct `orderService`. A `@SpringBootTest` or slice test can fail **before entering the `@Test` method**. Check component scanning, profiles, bean configuration, and mocks/test beans appropriate to the test type and Spring Boot version. Do not treat this trace as evidence that `orderService` logic computes wrong results.

If many tests fail with context loading errors, find the **first trace with a useful `Caused by`**; later tests may be affected by context caching/failure handling.

### 7.3. Exception thrown from application code

```text
java.lang.NullPointerException: ...
    at com.example.orders.OrderService.total(OrderService.java:42)
    at com.example.orders.OrderServiceTest.calculatesTotal(OrderServiceTest.java:27)
```

Frame `OrderService.java:42` points to where the exception was thrown; the test frame shows the calling scenario. Check which object was null: input, mock, mapper, or missing dependency. Do not guess solely from the exception type. Conversely, if a test uses `assertThrows` and catches the **exact required exception**, that exception is proof of a passing test, not a failure.

### 7.4. Compilation, classpath, and environment errors

`compileTestJava` failures, `NoClassDefFoundError`, `ClassNotFoundException`, database timeouts, `Connection refused`, port collisions, missing config, or unresolved dependencies each require separate analysis. If failure happens before JUnit discovery, there is no evidence any test case ran. A test failing because a database is unavailable also does not prove business rules are wrong.

## 8. How to prove a test case actually executed

Use this verification checklist during every analysis:

1. **Command and scope:** `./gradlew :orders:test --tests "com.example.testing.ShippingFeePolicyTest"` targets only the `orders` module's `test` task and that filter; `./gradlew test` at the root may have a different scope.
2. **Actual task/goal outcome:** did the task run tests, hit cache, skip, find no sources, or fail before the runner?
3. **Report matches the run:** timestamp/report artifact, module, job, branch/commit, task name, and environment.
4. **Testcase list:** does the target class/method/invocation appear in the report, and what is its exact status?
5. **Filters and conditions:** `--tests`, `-Dtest`, `@Tag`, `@Disabled`, JUnit conditions, include/exclude patterns, naming conventions, engine.
6. **Counts align with scope:** how many passed, failed/errored, skipped, and unselected?
7. **Require fresh execution:** if inspecting cached output, re-run deliberately and confirm both task status and fresh report before stating tests "just re-ran."

For example, `BUILD SUCCESSFUL` with `:test UP-TO-DATE` can reflect a green build from prior results; do not report "all tests were just freshly executed." Conversely, `Tests run: 0` or `No tests to run` is not proof that application behavior passed testing.

With Maven, inspect Surefire/Failsafe and skip flags. With Gradle, read JUnit Platform config and separate test tasks from the current project. **Having a `*Test.java` file in source does not prove JUnit discovered it.**

## 9. Quick reference table for common situations

| Situation | What may have happened | Next verification step |
|---|---|---|
| Console prints `BUILD SUCCESSFUL`, no tests seen | No tests matched, task skipped, or cached | Check task outcome and report/testcases |
| Gradle `UP-TO-DATE` or `FROM-CACHE` | Reused prior results | Use `--rerun-tasks` when proof of fresh execution is needed |
| Maven `Tests run: 0` | No tests discovered/selected | Check filters, plugins, naming, JUnit engine, module |
| `@Disabled` or failing assumption | Test recorded as skipped/aborted | Read reason and do not count as an executed pass |
| Filtered with `-Dtest` or `--tests` | Only a subset of classes/methods selected | Match testcases against the filter |
| Test fails to compile | JUnit never started that case | Fix compile/classpath first |
| `Failed to load ApplicationContext` | Bean/profile/test config error | Find actual `Caused by` and inspect setup |
| `AssertionFailedError` | Expected differs from actual | Inspect inputs, contract, and code path |
| Unit tests pass, API still broken | Tests bypass MVC/Security/JSON | Add tests at the exact failing boundary |
| `mvn test` green, integration tests missing | Failsafe/another suite did not run | Check configuration, `verify`, and separate reports |
| Execution count differs from method count | Parameterized/repeated/dynamic/nested | Inspect individual invocations/testcases in report |
| Many tests fail with same exception | Shared setup/context or external dependency | Group failures by root cause, read the first failure |

### Spring Boot-specific notes

- `@SpringBootTest` loads an application context, yet by default **does not start a real HTTP server**. To test a real HTTP server on a random port, configure `webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT`.
- `@WebMvcTest` is an MVC slice; missing collaborator beans can cause context startup failures inside the slice without meaning the production controller is broken.
- `@DataJpaTest` and test databases may use a different DB environment than production. For SQL/transaction bugs, verify which DB engine tests actually run against.
- Spring context tests can fail due to profiles/test properties/beans differing from deployment. Separate test config errors from application bugs before changing production code.

## 10. Reading CI reports and writing evidence-based bug reports

When CI runs multiple jobs or Java versions, tie results to **commit, job, module, command run, JDK, profile, and artifacts**. A unit-test job report does not prove an integration-test job ran. Stale reports lingering in a workspace can mislead; prefer reports archived from the exact CI run and check timestamps when needed.

If many tests fail:
1. Group by business assertions, context startup, database/network, timeouts, classpath, or configuration.
2. Find shared root causes, especially when many tests fail to build `ApplicationContext`.
3. Separate direct test failures from secondary setup failures.
4. Fix the root cause and re-run the failing case/class followed by the affected suite.
5. Avoid "fixing" a red CI build by deleting tests, weakening assertions, disabling tests, or retrying indefinitely.

An **illustrative** report sample:

> CI job `unit-tests` ran `./gradlew :orders:test --tests "com.example.testing.ShippingFeePolicyTest"` for the commit cited in the job. Report `:orders:test` recorded 4 tests: 3 passed, 1 failed, 0 skipped. Test `atThresholdIsFree` expected 0 but got 30000. `ShippingFeePolicy.fee(500_000)` uses `>` instead of `>=`. Proposed fixing the condition and re-running that test and related suite; not declaring the fix verified until fresh run results arrive.

When writing real reports, cite only facts directly observed in logs, XML, and code of that exact revision. Never copy illustrative numbers or claim tests passed without an actual run.

## 11. Checklist before concluding test results

- [ ] Identified the exact command, module, commit, environment, JDK, and CI job for the run.
- [ ] Separated compile/test discovery/setup failures from test body execution.
- [ ] Opened HTML/XML/TXT reports for the right task, right module, and right run.
- [ ] Read tests, failures, errors, and skipped counts instead of only `BUILD FAILED`/`BUILD SUCCESSFUL`.
- [ ] Identified `classname` + `testcase` + invocation and exact status of the target case.
- [ ] Checked filters, tags, disabled flags, caching, skips, and separate tasks to know what actually ran.
- [ ] Read exception messages, `Caused by`, source frames, and assertion lines.
- [ ] Compared expected/actual or state/side effects against the contract under test.
- [ ] After fixing, re-ran the failing case and related suite; distinguished real results from predictions.
- [ ] Report clearly states verified boundaries as well as unexecuted suites or skipped tests.

**Conclusion:** analyzing Spring Boot test results properly means linking **command run → task/goal → test case + status → stack trace → root cause in source**. Never confuse an assertion failure with a Spring `ApplicationContext` failure, or a green build with all tests having just executed. Reliable evidence always cites **specific case names, outcomes, scope, and run**.
