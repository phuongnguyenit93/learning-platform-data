# JUnit Jupiter: Assumptions, Environmental Conditions, and Reasons for Skipping Tests

## 1. Objectives and three easily confused outcomes

When implementing automated tests with **JUnit Jupiter** in a Spring Boot project, some tests **only make sense in a specific environment**: running on Linux, requiring a compatible Java version, needing an opt-in environment variable, or relying on optional infrastructure. JUnit allows skipping test execution under these circumstances, but you must accurately distinguish **FAILED**, **ABORTED**, and **DISABLED/SKIPPED**.

| Status at the JUnit Platform level | When does it happen? | Has test/lifecycle code run? | Meaning to understand |
| --- | --- | --- | --- |
| **SUCCESSFUL / PASSED** | Assertions succeed, no unexpected errors | Yes (except certain special test forms) | Test **executed and passed** |
| **FAILED** | Failed assertion or unhandled unexpected exception | Usually ran at least partially | Issue needing investigation; pipeline should normally turn red |
| **ABORTED** | `Assumptions.assumeTrue(false)`, `assumeFalse(true)`, or `TestAbortedException` | Started execution or ran up to the assumption | Precondition **not met**, so there is insufficient evidence to conclude pass/fail |
| **DISABLED / SKIPPED** | `@Disabled` or `ExecutionCondition` excludes the test before execution | Test method and method-level lifecycle do not run | Test **was not selected to run** due to policy/condition |

**Core principle:** Do not equate "did not FAIL" with "verified". An ABORTED or DISABLED test does not prove a feature works. Display tools like Maven Surefire, Gradle, IDEs, JUnit XML, or CI dashboards may group ABORTED into "skipped"; always inspect detailed info, reasons, and the number of tests that actually executed.

Examples:

- Local machine lacks an optional test environment → an integration test may be ABORTED by an assumption or DISABLED by an annotation.
- Tax calculation logic is broken across all supported environments → must be **FAILED** via assertions; never use assumptions to hide bugs.
- Linux-dependent feature → use OS conditional annotations so the test does not run on Windows.
- Test temporarily disabled due to a tracked bug → `@Disabled("... reason, issue, review date ...")`, tracking the timeline to re-enable it.

## 2. What is an assumption? How does it differ from an assertion?

An assumption is an **assumption about the environment or test preconditions**, not a business requirement of the system. The primary APIs reside in `org.junit.jupiter.api.Assumptions`:

- `assumeTrue(boolean condition)` / `assumeTrue(condition, message)` / lambda overloads: **continue** if condition is true; **ABORTED** if false.
- `assumeFalse(boolean condition)`: continue if condition is false; ABORTED if true.
- `assumingThat(boolean condition, Executable block)`: **only run the block** if condition is true; if false, skip the **block**, while the test continues and can PASS.
- `Assumptions.abort(...)` (available in newer JUnit Jupiter versions) explicitly aborts when needed; when support varies across versions, `assumeTrue(false, reason)` is easy to read and more broadly compatible.

When `assumeTrue` or `assumeFalse` is not met, JUnit Jupiter throws `org.opentest4j.TestAbortedException` to signal the test was aborted. Assertions like `assertTrue` throw an assertion error, causing the test to become FAILED. **Do not call assumptions to check behavior that must always hold true.**

### Example: same condition, different outcomes

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
import org.junit.jupiter.api.Test;

class AssumptionOrAssertionTest {

    @Test
    void optionalEnvironmentMayAbort() {
        boolean ready = false; // Simulates an optional environment not yet provided.
        assumeTrue(ready, "Optional environment has not been provided");
        assertEquals(4, 2 + 2); // Does not run when ready=false.
    }

    @Test
    void requiredBehaviorMustFail() {
        int calculated = 3; // Simulates a business logic bug.
        assertEquals(4, calculated); // FAILED, must never be skipped.
    }
}
```

This is an example **intentionally containing 1 ABORTED and 1 FAILED test for explanation**, not a test suite to copy verbatim into CI. In a real project, `ready` must come from validated configuration, and `calculated` must be real output from application code. Putting a fixture designed to FAIL into production CI will turn the pipeline red by design.

### When should assumptions be checked?

Use them when **no useful conclusion can be drawn** because an optional environment is absent. For instance, a smoke test checking connectivity to a separately provisioned sandbox. If the sandbox server is a **mandatory** dependency of a release pipeline, losing connection must FAIL to report missing infrastructure rather than always aborting and making the dashboard look "green".

Do not use assumptions to handle: incorrect business results, unexpected HTTP 500s, repositories saving wrongly, missing emitted messages, schema mismatches, or tests that consistently time out. Those are failures requiring investigation.

## 3. `assumingThat` is completely different from `assumeTrue`

A common mistake is thinking `assumingThat(false, block)` makes **the whole test ABORTED**. In reality, it merely skips executing the block; subsequent statements still run.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assumptions.assumingThat;

import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;

class AssumingThatDemoTest {

    @Test
    void skipsOnlyOptionalBlock() {
        AtomicBoolean optionalBlockRan = new AtomicBoolean(false);

        assumingThat(false, () -> optionalBlockRan.set(true));

        assertFalse(optionalBlockRan.get());
        assertEquals(9, 3 * 3); // Still runs; test PASSES.
    }
}
```

Use `assumingThat` when an extra verification step is genuinely **optional**, while the rest of the test remains valuable. Do not use it to wrap the test's primary assertion: otherwise the test could report PASS without verifying anything essential.

If the goal is to skip the **entire test** in an invalid environment, use `assumeTrue`/`assumeFalse` or a conditional annotation.

## 4. Two distinct mechanisms: runtime assumptions vs execution conditions

JUnit Jupiter implements the **`ExecutionCondition`** mechanism to decide whether to enable a test class or test method **before calling the test method**. Built-in annotations mostly live in `org.junit.jupiter.api.condition`.

| Need | Mechanism | Outcome when unmet |
| --- | --- | --- |
| Run only on Linux/macOS, or skip on Windows | `@EnabledOnOs` / `@DisabledOnOs` | DISABLED |
| Run only on Java 17, 21, or a specific JRE range | `@EnabledOnJre`, `@DisabledOnJre`, `@EnabledForJreRange`, `@DisabledForJreRange` | DISABLED |
| Run only when an environment variable matches | `@EnabledIfEnvironmentVariable` / `@DisabledIfEnvironmentVariable` | DISABLED |
| Depend on a JVM system property value | `@EnabledIfSystemProperty` / `@DisabledIfSystemProperty` | DISABLED |
| Boolean condition computed by a method | `@EnabledIf` / `@DisabledIf` | DISABLED |
| Explicitly disable temporarily, unrelated to environment | `@Disabled("reason")` | DISABLED |
| Condition only known while running the test | `assumeTrue` / `assumeFalse` | ABORTED |
| Only one optional check block inside a test | `assumingThat` | Skip block, test continues |

Prefer **built-in annotations** when the condition is clear OS/JRE/config info known before the test starts. Use **assumptions** when the condition must be evaluated during the test (such as data produced during setup). Complex custom conditions can implement a custom `ExecutionCondition`, though there is no need when built-in annotations suffice.

### 4.1. Enabling/disabling tests by operating system

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.DisabledOnOs;
import org.junit.jupiter.api.condition.OS;

class OsSpecificTest {

    @Test
    @EnabledOnOs(value = {OS.LINUX, OS.MAC},
                 disabledReason = "Tool is only available on Unix-like CI")
    void usesUnixTool() {
        // Real verification with a Unix-specific tool.
    }

    @Test
    @DisabledOnOs(value = OS.WINDOWS,
                  disabledReason = "Corresponding executable is not yet supported on Windows")
    void worksExceptOnWindows() {
        // Real application assertions.
    }
}
```

These two examples illustrate condition syntax; real test bodies must contain meaningful assertions. Do not make all tests Linux-only simply because developers usually use Linux: ensure OS restrictions actually reflect requirements.

### 4.2. Enabling/disabling tests by JRE

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledForJreRange;
import org.junit.jupiter.api.condition.EnabledOnJre;
import org.junit.jupiter.api.condition.JRE;

class JavaVersionTest {

    @Test
    @EnabledOnJre(JRE.JAVA_17)
    void specificJava17Behavior() {
        // Test applicable only to Java 17.
    }

    @Test
    @EnabledForJreRange(min = JRE.JAVA_17)
    void worksOnJava17AndNewer() {
        // Test on Java >= 17.
    }
}
```

Available `JRE.JAVA_xx` enums depend on the JUnit version, so when upgrading to a new major JDK, do not assume the corresponding enum already exists. Newer JUnit versions provide `minVersion`/`maxVersion`/`versions` parameters when a JDK number is not yet in the enum. If using JUnit 6, the Java baseline is **17**, and several older JRE options become redundant or deprecated.

### 4.3. Environment variables vs system properties

**Environment variables** come from the OS process environment, read via `System.getenv("NAME")`. **System properties** are JVM properties, read via `System.getProperty("name")`; set directly with `-Dname=value` or through test task configuration. Do not use them interchangeably.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.condition.DisabledIfEnvironmentVariable;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

class ConfigurationConditionTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_SANDBOX_TESTS",
        matches = "true",
        disabledReason = "Sandbox tests are only enabled when opted in")
    void runsWithSandboxOptIn() {
        // Real sandbox test.
    }

    @Test
    @DisabledIfEnvironmentVariable(
        named = "CI",
        matches = "(?i)true",
        disabledReason = "This test only verifies a local GUI tool")
    void localGraphicsOnly() {
        // Local GUI test, unsuitable for headless CI.
    }

    @Test
    @EnabledIfSystemProperty(
        named = "test.profile",
        matches = "sandbox",
        disabledReason = "Only runs with test.profile=sandbox configuration")
    void runsWithJvmProperty() {
        // Real test for sandbox profile.
    }
}
```

The `matches` attribute is evaluated as a **regular expression (regex)**. `"true"` and `"(?i)true"` differ in case sensitivity; a misspelled environment variable name or missing variable normally causes `@EnabledIf...` not to match. When applying `@DisabledIfEnvironmentVariable`, a missing variable will **not** trigger the disable condition; if a test should only run when explicitly allowed, using `@EnabledIfEnvironmentVariable` (opt-in) is safer.

Warning: JUnit's `@EnabledIf` (`org.junit.jupiter.api.condition.EnabledIf`) **differs** from Spring Test's `@EnabledIf` in `org.springframework.test.context.junit.jupiter.EnabledIf`. When the IDE auto-imports, check the exact package and expression syntax the annotation expects.

### 4.4. Method-based conditions and custom `ExecutionCondition`

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIf;

class ConditionMethodTest {

    @Test
    @EnabledIf("hasRequiredProperty")
    void runsOnlyWhenPropertyExists() {
        // Real test.
    }

    static boolean hasRequiredProperty() {
        return System.getProperty("app.test.optin") != null;
    }
}
```

For `@EnabledIf`/`@DisabledIf`, the method returns `boolean` and can take no parameters or one `ExtensionContext`. The condition method must be `static` in several cases, including when placed at the **class-level**, on parameterized tests/test templates, or when located in an outer class. If rich logic is needed for an entire group of tests, consider a custom `ExecutionCondition` to supply clear, centralized disable reasons; avoid complex side effects inside conditions.

## 5. `@Disabled` and writing actionable reasons

`@Disabled` applies to a test method or class. If placed on a class, all test methods in that class are disabled. Example:

```java
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

class PendingFixTest {

    @Test
    @Disabled("ISSUE-142: result depends on unstable external system; review 2026-12-01")
    void downstreamContract() {
        // Assertions once ISSUE-142 is resolved.
    }
}
```

The string in `@Disabled` should answer three questions: **why it is disabled**, **where it is tracked**, and **when/under what condition to re-enable it**. "flaky", "broken", "TODO", or leaving it blank are hard to manage. The sample reason above illustrates syntax; issue IDs and dates in a real project must be factual, not copied verbatim from the example.

Prefer fixing the root cause of flaky tests. For unresolved failures, depending on project policy, you can use a quarantine mechanism with an owner, issue, deadline, and dedicated job that reports red if a quarantined test keeps failing. Never turn `@Disabled` into a place to hide regressions. If a test covers a release-critical requirement, disabling it without alternative coverage can misrepresent quality.

### Does `@Disabled` block every lifecycle hook?

If **a test method** is disabled, that method and its corresponding `@BeforeEach`/`@AfterEach` callbacks **are not invoked**. However, disabling one method **does not guarantee** the class will not be instantiated or class-level `@BeforeAll`/`@AfterAll` hooks will not run. Contrast this with `assumeTrue` inside a test: at abort time, earlier setup may already have run and side effects must still be cleaned up properly.

Place external resources (files, servers, DB transactions) in fixtures with reliable cleanup; do not rely on assumptions as a substitute for resource closing. If another assertion or teardown error also occurs, the final outcome can be **FAILED** even after an earlier failed assumption.

## 6. Runnable Java 17 Maven project observing all states

To verify these mechanisms with executable code, create a simple Maven project **without needing a Spring context**. The example uses JUnit Jupiter 5.12.2, Java 17, and Maven Surefire 3.5.2. When using real **Spring Boot**, replace direct JUnit dependencies with `spring-boot-starter-test` and let the Spring Boot BOM manage JUnit; do not force version 5.12.2 onto a Boot 4 project using JUnit 6.

File structure:

```text
junit-assumptions-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── EnvironmentConditionsTest.java
```

### 6.1. Complete `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>junit-assumptions-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. `src/test/java/example/EnvironmentConditionsTest.java`

```java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
import static org.junit.jupiter.api.Assumptions.assumingThat;

import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;

class EnvironmentConditionsTest {

    @Test
    void basicUnitTestAlwaysRuns() {
        assertEquals(4, 2 + 2);
    }

    @Test
    void optionalTestAbortsWhenNotOptedIn() {
        boolean optIn = "true".equalsIgnoreCase(
                System.getenv("RUN_OPTIONAL_TESTS"));

        assumeTrue(optIn,
                () -> "Missing RUN_OPTIONAL_TESTS=true for optional test");

        assertEquals("ok", "o" + "k");
    }

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_OPTIONAL_TESTS",
        matches = "(?i)true",
        disabledReason = "Only runs when RUN_OPTIONAL_TESTS=true")
    void optionalTestSkippedBeforeExecutionWhenNotOptedIn() {
        assertEquals(10, 5 + 5);
    }

    @Test
    @EnabledOnOs(
        value = OS.LINUX,
        disabledReason = "Example only runs on Linux")
    void linuxOnlyTest() {
        assertNotNull(System.getProperty("os.name"));
    }

    @Test
    @Disabled("Guide example for @Disabled; not used as primary coverage")
    void sampleExplicitlyDisabledTest() {
        // This test method is not executed.
    }

    @Test
    void assumingThatSkipsOnlyTheOptionalBlock() {
        AtomicBoolean executed = new AtomicBoolean(false);

        assumingThat(false, () -> executed.set(true));

        assertFalse(executed.get());
        assertEquals(9, 3 * 3);
    }
}
```

Class, file, and package names match; there is no `@SpringBootTest`, and no Docker, database, or network is needed. The demo assertions are deterministic; outcomes vary **intentionally** with the environment.

### 6.3. Running and reading results

In the directory containing `pom.xml`:

```bash
mvn test
```

On bash, enable both opt-in tests:

```bash
RUN_OPTIONAL_TESTS=true mvn test
```

In PowerShell:

```powershell
$env:RUN_OPTIONAL_TESTS = 'true'
mvn test
Remove-Item Env:RUN_OPTIONAL_TESTS
```

Expected results table **per method**:

| Test method | Without `RUN_OPTIONAL_TESTS` on Linux | With `RUN_OPTIONAL_TESTS=true` on Linux |
| --- | --- | --- |
| `basicUnitTestAlwaysRuns` | PASSED | PASSED |
| `optionalTestAbortsWhenNotOptedIn` | ABORTED (failed assumption) | PASSED |
| `optionalTestSkippedBeforeExecutionWhenNotOptedIn` | DISABLED (condition) | PASSED |
| `linuxOnlyTest` | PASSED | PASSED |
| `sampleExplicitlyDisabledTest` | DISABLED | DISABLED |
| `assumingThatSkipsOnlyTheOptionalBlock` | PASSED | PASSED |

On Windows, `linuxOnlyTest` is also DISABLED. There is no fixed application stdout: the class does not call `System.out.println`. **Do not hard-expect a single Maven output line** because Surefire/IDEs can aggregate aborted and disabled differently; what matters is each method's status and reason. Maven reports are generated in `target/surefire-reports/` when the test plugin runs, and can be used to investigate unexecuted tests.

To avoid keeping an always-disabled test in a real project, remove `sampleExplicitlyDisabledTest` after practicing. To run all tests in CI, set `RUN_OPTIONAL_TESTS=true` in a test environment with a **properly provisioned** sandbox, never just to boost PASS percentages.

## 7. Applying in Spring Boot: optional tests vs mandatory tests

In Spring Boot projects, you typically already have:

**Maven (placed inside `<dependencies>` of `pom.xml`):**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

**Gradle Kotlin DSL:**

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
tasks.withType<Test> {
    useJUnitPlatform()
}
```

JUnit Jupiter is included in the common starter; many Spring Boot 3.x projects use JUnit 5, while Spring Boot 4.x uses the JUnit 6 line. The assumption and condition APIs presented here still use `org.junit.jupiter.api` and `org.junit.jupiter.api.condition`. Always check the project's actual version instead of copying the version number from the standalone Maven example.

### 7.1. When to use assumptions in integration tests

An **optional** smoke test checking connectivity to an internal sandbox only when the environment permits:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import org.junit.jupiter.api.Test;

class OptionalSandboxTest {

    @Test
    void validatesOptInBeforeCallingSandbox() {
        String enabled = System.getenv("RUN_SANDBOX_TESTS");
        String sandboxUrl = System.getenv("SANDBOX_URL");

        assumeTrue("true".equalsIgnoreCase(enabled),
                "RUN_SANDBOX_TESTS is not enabled");
        assumeTrue(sandboxUrl != null && !sandboxUrl.isBlank(),
                "SANDBOX_URL is not set");

        assertTrue(sandboxUrl.startsWith("https://"));
        // With a real HTTP client: call sandbox and assert contract results.
    }
}
```

This is a **runnable example checking only opt-in/URL configuration**; it does not yet verify connectivity or business behavior. If adding HTTP calls, enforce timeouts, verify status/body, and handle timeouts per SLA. When a sandbox is mandatory in a CI job, a missing endpoint or timeout should intentionally FAIL under that pipeline's policy; adjust the assumption instead of letting the test abort silently.

### 7.2. Conditions can apply at the class level

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

@EnabledIfEnvironmentVariable(
    named = "RUN_DB_INTEGRATION_TESTS",
    matches = "true",
    disabledReason = "DB integration runs in a separate job")
class DatabaseIntegrationTest {

    @Test
    void testsDatabaseContract() {
        // Real database test, e.g., via Testcontainers.
    }
}
```

The snippet above illustrates **class-level conditions**; it is not a complete DB test yet. When the environment variable does not match, the entire class is disabled. A real DB test requires repositories/drivers/migrations/schemas and possibly Testcontainers. Do not write an assumption "if Docker is not running, PASS" for a CI job tasked with verifying the DB: if mandatory infrastructure is unavailable, that is a job or configuration failure to fix.

### 7.3. Choosing approaches for Testcontainers, filesystems, and credentials

| Condition | When can it be optional? | Approach to consider |
| --- | --- | --- |
| Container runtime absent on developer machine | Integration tests run in a separate CI job guaranteeing the runtime | Opt-in annotation locally; CI integration must fail when required Docker is missing |
| Sandbox API unavailable locally | Separate smoke job provisioned with URL/credentials | Opt-in + config check; never print secrets in reasons/logs |
| Sample data file exists only in one job | Test genuinely belongs only to that job | Environment/path condition; if the file is a repo-tracked fixture, missing it should FAIL |
| Feature flag not yet enabled | Contract applies only when flag is on | Condition based on published flag; separate job verifies feature when enabled |
| Unsupported JDK/OS | Official contract only guarantees supported environments | OS/JRE annotation with reason; at least one job tests on supported environments |
| Application bug, HTTP 500, SQL error | Not an "optional condition" | Assertion/exception FAILED, fix root cause or track clearly in an issue |

Never use an assumption as a generic `catch` for every exception:

```java
// ANTI-PATTERN: do not turn system errors into skipped tests.
try {
    executeRequiredOperation();
} catch (Exception ex) {
    assumeTrue(false, "Skipped because operation failed");
}
```

The snippet above **only illustrates an anti-pattern** and does not compile standalone (missing `executeRequiredOperation()`). If the operation falls inside mandatory test scope, let the exception make the test FAILED or assert the expected exception. If testing only an optional dependency, check the opt-in condition before calling the operation and clearly define when aborting is still valid.

## 8. Parameterized tests, nested tests, and lifecycles: common traps

### 8.1. Assumptions in `@ParameterizedTest`

If one invocation fails an assumption, that invocation can be ABORTED while others remain PASSED. Thus a parameterized test with 10 inputs where 9 abort only proves **1 input**. Do not claim "10 cases verified".

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class ParameterAssumptionTest {

    @ParameterizedTest
    @ValueSource(ints = {0, 1, 2, 3})
    void verifiesOnlySupportedSamples(int value) {
        assumeTrue(value > 0, "Sample 0 is outside this test domain");
        assertTrue(value * 2 > value);
    }
}
```

In this illustrative fixture, invocation `0` is ABORTED while `1,2,3` are PASSED. In a real business test, **invalid inputs must be tested as error cases with assertions**, never aborted if they belong to requirements. Using separate "valid data" and "invalid data" test sets is clearer whenever possible.

### 8.2. Lifecycle

- Condition annotations are evaluated before calling the test method; disabled tests do not run method-level `@BeforeEach`/`@AfterEach`. However, class-level setup may still occur if the class contains other active tests.
- Assumptions live inside the test method: `@BeforeEach` may already have initialized data or connections before aborting. Cleanup/rollback must remain accurate and safe.
- An exception/assertion failure from lifecycle hooks can make the outcome FAILED even if an assumption aborted. Do not rely on error ordering to mask cleanup bugs.
- If checking the environment is expensive and can be decided early, prefer a condition over booting an entire Spring context only to call `assumeTrue`.
- Class-level `@Disabled` applies to all tests in that class; with `@Nested` or inheritance, check exact semantics for your JUnit version rather than guessing inheritance behavior.

### 8.3. Combining multiple conditions

You can combine OS and env var conditions:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.condition.OS;

class CombinedConditionsTest {

    @Test
    @EnabledOnOs(OS.LINUX)
    @EnabledIfEnvironmentVariable(named = "RUN_OPTIONAL_TESTS", matches = "true")
    void onLinuxWhenExplicitlyEnabled() {
        // Real test.
    }
}
```

The test is enabled only when **all enabled conditions are satisfied**. Once one condition disables the test, JUnit may stop evaluating remaining conditions; there is **no guarantee** all conditions are evaluated or all reasons aggregated into the report. Putting complex logic, side effects, or order-dependent checks inside conditions is therefore poor design.

`@Tag("integration")` and `includeTags`/`excludeTags` filters **select** the test subset at build time. Filtered-out tests do not necessarily show up as DISABLED in reports because JUnit may exclude them from the test plan altogether. Do not use the "skipped" count to deduce every test skipped by filters.

## 9. Designing skip reasons for monitorable CI

A solid policy answers: **which test**, **why**, **when it runs**, **who handles it**, and **where evidence lives**.

| Reason for not running | Expected status | Reason to document | How to avoid losing coverage |
| --- | --- | --- | --- |
| OS/JDK outside official support | Conditionally DISABLED | Supported OS/version, exact condition | Have a CI job running on supported OS/JDK |
| Job is not an integration job | Conditionally DISABLED / tag-filtered | Opt-in flag name, owning job config | Separate integration job runs in full |
| Optional sandbox absent | ABORTED or DISABLED depending on check timing | Missing variable/config, how to enable | Mandatory sandbox job measures PASS/FAIL |
| Test temporarily disabled for known bug | `@Disabled` | Issue, owner, target re-enable milestone | Track quarantine, report days disabled |
| Mandatory dependency failed | FAILED | Root error, safe stack trace/logs | Fix infrastructure or code, do not add assumption |
| Test excluded by tag filter | Not selected in test run | Build filter, test task configuration | Have another job covering the tag |

**Write thorough reasons without leaking secrets.** Good example: "RUN_SANDBOX_TESTS=true is not enabled; the sandbox-integration job is responsible for running this test". Bad example: concatenating the full `SANDBOX_TOKEN`, passwords, connection URLs with credentials, or personal data into the reason.

For `@Disabled`, use an issue tracker rather than scattered code comments. Set review deadlines; alert when disabled test counts rise or when release-critical tests run in zero jobs.

### Sample CI conventions

- **Fast PR job:** pure unit tests and mandatory slice tests, independent of Docker/external network.
- **Integration job:** supplies required DB/containers/credentials; enables integration tests and treats outages as infrastructure failures (FAILED).
- **Platform matrix:** exercises every OS/JDK promised by the product; annotations disable only genuinely incompatible cases.
- **Quarantine job:** continues tracking unfixed failing tests with issues and deadlines; never lets them vanish from schedules.

When reviewing a test suite, track **actually executed tests**, **failed**, **aborted**, **disabled**, and **filtered-out** counts along with reasons. Dashboards showing only green without surfacing skipped cases easily create false confidence.

## 10. Common mistakes and fixes

| Mistake | Harm | Fix |
| --- | --- | --- |
| Using `assumeTrue(response.isSuccessful())` to "test" an HTTP endpoint | Failing HTTP turns into ABORTED instead of FAILED | Use `assertTrue` or `assertEquals` against expected HTTP contract |
| Assuming `assumingThat(false, ...)` aborts the entire test | Test PASSES even though key assertion never ran | Use `assumeTrue` if the whole test is invalid; for optional blocks, keep main assertions outside |
| Always calling `assumeTrue(false)` on any IOException | Hides real network/DB failures | Separate optional prerequisites from mandatory dependencies |
| Forgetting `RUN_*` values on CI | Integration tests never run while pipeline stays green | Configure opt-in on the job; monitor executed counts |
| Switching from env var to JVM `-D` while keeping `@EnabledIfEnvironmentVariable` | Condition never finds the variable | Use `@EnabledIfSystemProperty` or pass an actual environment variable |
| `matches="true"` when CI supplies `TRUE` | Regex condition does not match | Standardize casing or use `(?i)true` |
| Using `@Disabled` with no reason | Test stays forgotten indefinitely | Record issue + reason + re-enable condition |
| Looking only at total skipped count | Cannot tell disabled from aborted | Open individual test reports and condition/assumption messages |
| Only running tests on Linux despite supporting Windows | Leaves Windows coverage empty | Maintain a platform CI matrix for supported OSes |
| Placing an assumption after side-effect operations | Test aborts after data already mutated | Check prerequisites early; ensure safe cleanup/transactions |
| Importing condition annotation from Spring Test by mistake | Condition behaves differently than intended | Use `org.junit.jupiter.api.condition...` for JUnit conditions |
| Disabling one method while `@BeforeAll` still accesses external dependencies | Job still wastes resources or fails in setup | Move setup to proper scope, use class-level conditions when appropriate |

## 11. Decision workflow when writing a new test

1. **Identify what must be proved.** If behavior is mandatory, the test must PASS or FAILED—never abort to dodge errors.
2. **List external prerequisites.** OS, JDK, config, sandbox, database, Docker, files, credentials; mark each **mandatory** or **optional** for the current job.
3. **Choose when to check.** Known from environment upfront → `@Enabled...`/`@Disabled...` annotations; evaluated mid-run → `assumeTrue`/`assumeFalse`.
4. **If only one check section is optional**, use `assumingThat` while guaranteeing core assertions always execute.
5. **Write helpful reasons**: missing condition, where to enable the test, and issue/milestone if temporarily disabled. Never print secrets.
6. **Ensure a mandatory execution path for coverage.** If disabled locally, some job must run it; avoid tests that are never verified anywhere.
7. **Inspect outcomes at the invocation level.** Especially for parameterized tests: inspect PASS/FAILED/ABORTED/DISABLED and tag filters; look past just "BUILD SUCCESS".
8. **Review periodically.** Cut down unjustified skips, fix flaky tests, remove expired `@Disabled`, and update OS/JDK/framework conditions.

### Self-assessment checklist

- [ ] Distinguished assumptions from assertions and explained why a test can become ABORTED?
- [ ] Identified whether a test depends on an **optional** environment or a mandatory requirement?
- [ ] Used condition annotations from the right package and configuration kind (env vs system property)?
- [ ] Verified `matches` regex reflects actual configuration values?
- [ ] Provided concrete details in `@Disabled`/`disabledReason`, never leaving them blank?
- [ ] Wrapped only secondary checks in `assumingThat`, never hiding primary assertions?
- [ ] Confirmed cleanup/lifecycle remains safe if a test aborts after setup?
- [ ] Ensured a CI job actually runs all critical test groups on supported environments?
- [ ] Verified reports distinguish passed, failed, aborted, disabled, and filtered tests?
- [ ] Made sure Maven/Gradle examples use the JUnit version managed by the Spring Boot project?

## 12. Primary reference sources

- [JUnit User Guide — Assumptions](https://docs.junit.org/6.1.3/writing-tests/assumptions.html): `assumeTrue`, `assumeFalse`, `assumingThat`, and aborted tests.
- [JUnit User Guide — Disabling Tests](https://docs.junit.org/6.1.0/writing-tests/disabling-tests.html): `@Disabled`, class-level behavior, and lifecycle.
- [JUnit User Guide — Conditional Test Execution](https://docs.junit.org/6.0.2/writing-tests/conditional-test-execution.html): OS, JRE, environment variables, system properties, and custom method conditions.
- [JUnit Jupiter 5.10 User Guide](https://docs.junit.org/5.10.0/user-guide/index.html): syntax reference for projects still using JUnit 5.
- [JUnit 6 Migration Notes](https://github.com/junit-team/junit-framework/wiki/Upgrading-to-JUnit-6.0): Java baseline and deprecated APIs/conditions when upgrading.

**Remember:** Assertions answer **"is the behavior correct?"**; assumptions answer **"are conditions sufficient to evaluate behavior right now?"**; conditional annotations answer **"does this test belong in the active set for the current environment?"**. Skipping a test with a clear reason is a controlled choice, but must always be tracked so coverage is never silently lost.
