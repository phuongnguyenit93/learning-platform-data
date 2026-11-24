# Tags and Conditions for Enabling or Disabling Tests

A Spring project typically has many kinds of tests: fast unit tests, controller tests, repository tests requiring a database, integration tests against external services, and certain tests suited only to a specific operating system or Java version. If every test always runs together, the development feedback loop can become slow; if tests are skipped arbitrarily, the pipeline can turn green even though important risks remain unverified.

JUnit Jupiter provides two complementary mechanisms to organize test execution: **tags** for categorizing and filtering test groups, and **conditions** for enabling or disabling a test based on environment or execution criteria. In addition, JUnit offers `Assumptions` to abort a run when a required runtime assumption does not hold. Understanding the differences between these mechanisms helps teams select the right tests for each stage while keeping results trustworthy.

## 1. Distinguishing Tags, Conditions, and Assumptions

The three mechanisms address three different needs:

| Mechanism | Purpose | When It Takes Effect | Example |
| --- | --- | --- | --- |
| Tag | Attaches labels to include or exclude a group of tests | When the test platform filters tests to run | Run only `unit`, exclude `slow` |
| Condition | Decides whether a test should execute in the current environment | When JUnit evaluates execution conditions | Run only on Linux or when an environment variable is set |
| Assumption | Checks a runtime assumption; if false, aborts the remainder of that test run | During test execution | Skip checks requiring an optional service when that service is unavailable |

A tag does not disable a test on its own. It merely provides a label; the build tool or JUnit Platform must be configured to include or exclude that label. A condition governs whether a test is executed at all. An assumption is checked inside the test body or a lifecycle method and can mark that run as aborted/skipped when the assumption is unsatisfied.

For example, a repository test can carry the `integration` and `database` tags. When running a fast test suite, Gradle excludes `integration`; when running the integration pipeline, Gradle includes `integration` while excluding `slow`. If a test is Linux-specific, `@EnabledOnOs(OS.LINUX)` enforces the environment condition even after the tag is selected.

## 2. Attaching Tags with `@Tag`

JUnit Jupiter provides the `@Tag` annotation in the `org.junit.jupiter.api` package. Tags can be placed at the class or method level.

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("integration")
class OrderRepositoryTest {

    @Test
    void savesAndReloadsAnOrder() {
        // Verify database operations
    }

    @Test
    @Tag("slow")
    void loadsOrdersForALargeCustomerDataset() {
        // Verify with a large dataset
    }
}
```

In this example, tests in the class carry the `integration` label; the second method additionally carries `slow`. Thus, the second test has both tags. When a filter excludes `slow`, that method is excluded even though the class was selected by `integration`.

A test can carry multiple tags. Use the `@Tags` container to declare multiple labels at the same location:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Tags;

@Tags({
    @Tag("integration"),
    @Tag("database")
})
class CustomerRepositoryTest {

    @Test
    void findsCustomerByEmail() {
        // ...
    }
}
```

You can combine class-level and method-level tags to represent different classification dimensions. For instance, the class is tagged `integration`, while specific methods carry `slow` or `external`.

### Choosing Tag Naming Conventions

Tags should describe stable properties of a test rather than turning into an arbitrary list of labels. A tag vocabulary can start from these categories:

| Category | Example Tags | Meaning |
| --- | --- | --- |
| Scope | `unit`, `integration`, `e2e` | Degree of collaboration across components |
| Component | `database`, `http`, `messaging`, `security` | Boundary or infrastructure under test |
| Time/Resources | `slow`, `long-running` | Significant execution cost |
| Pipeline Purpose | `smoke`, `critical` | Representative or high-priority suite |
| External Dependency | `external`, `container` | Requires external services or extra infrastructure |

You do not need to attach every tag to every test. One test may only need `unit`; another may carry `integration` and `database`. Add a label only when it helps the team build a useful filter or clarify test scope.

Use lowercase, short, and consistent names—such as `database` instead of alternating between `db`, `Database`, and `database-test`. Avoid names with whitespace or special characters that make filter configurations hard to read. Project documentation should state clearly what each tag means and which pipeline uses it.

## 3. Filtering Tags with JUnit Platform

JUnit Jupiter runs on JUnit Platform. Test filtering is typically configured in the build tool or test launcher. The two basic operations are:

- **Include:** select only tests matching the specified tags.
- **Exclude:** remove tests matching the specified tags from the selected set.

When a test carries multiple tags, having just one excluded tag excludes the test. Hence, if a class carries `integration` and a method also carries `slow`, a configuration including `integration` and excluding `slow` will not run that method.

### Gradle

With Gradle Groovy DSL:

```groovy
tasks.test {
    useJUnitPlatform {
        includeTags 'unit'
        excludeTags 'slow', 'external'
    }
}
```

With Gradle Kotlin DSL:

```kotlin
tasks.test {
    useJUnitPlatform {
        includeTags("unit")
        excludeTags("slow", "external")
    }
}
```

This configuration selects tests tagged `unit`, while excluding tests tagged `slow` or `external`. If no include tags are declared, Gradle normally runs all discovered tests except those removed by exclude filters and other conditions.

A project can define separate tasks for different groups. For instance, a `test` task runs quickly during development, while an `integrationTest` task runs the integration suite in CI. When creating custom tasks, configure source sets, classpaths, and test tasks according to how the project is structured; tags are only part of the filter and do not automatically create new tasks.

### Maven Surefire

With Maven Surefire versions supporting JUnit Platform, you can use `groups` and `excludedGroups` to select tags:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <groups>unit</groups>
        <excludedGroups>slow,external</excludedGroups>
    </configuration>
</plugin>
```

In this configuration, Surefire runs only tests in the `unit` group and excludes tests tagged `slow` or `external`. Use a plugin version compatible with the project's JUnit Platform and `junit-jupiter-engine` dependency. If the project has separate Maven profiles for integration tests, verify whether those profiles override or extend filters as intended.

### JUnit Platform Suite

When you want to define a test suite in Java code, you can use the JUnit Platform Suite module:

```java
import org.junit.platform.suite.api.ExcludeTags;
import org.junit.platform.suite.api.IncludeTags;
import org.junit.platform.suite.api.SelectPackages;
import org.junit.platform.suite.api.Suite;

@Suite
@SelectPackages("com.example.orders")
@IncludeTags("integration")
@ExcludeTags("slow")
class OrderIntegrationSuite {
}
```

This suite discovers tests in the selected package, keeps only the `integration` group, and excludes `slow`. This is helpful when a team wants a clearly named entry point for a test suite. Add the corresponding JUnit Platform Suite dependency to test runtime.

## 4. Tag Expressions

JUnit Platform supports expressions to combine multiple tags wherever tag expressions are accepted. The main operators are:

| Operator | Meaning | Example |
| --- | --- | --- |
| `!` | Negation | `!slow` |
| `&` | AND | `integration & database` |
| `|` | OR | `smoke | critical` |
| `( )` | Grouping | `(integration & database) | smoke` |

Precedence is negation first, then AND, then OR. Use parentheses when expressions contain multiple groups so readers do not have to infer precedence.

Examples of expression meanings:

- `unit & !slow`: tests tagged `unit` and not tagged `slow`.
- `integration & database`: tests carrying both tags.
- `smoke | critical`: tests carrying at least one of the two tags.
- `(integration & !external) | smoke`: integration tests without external service dependencies, or smoke tests.

Not every build tool configuration accepts full tag expressions identically. Use the syntax supported by the launcher or plugin in use. In common Gradle configurations, `includeTags` and `excludeTags` typically accept lists of tags to include and exclude; do not assume an arbitrary expression string will be interpreted identically to the JUnit Console Launcher.

## 5. Enabling Tests by Operating System with `@EnabledOnOs` and `@DisabledOnOs`

Some tests only make sense on a specific operating system, such as testing Unix domain sockets, file permissions, or OS commands. JUnit provides `@EnabledOnOs` and `@DisabledOnOs` in `org.junit.jupiter.api.condition`.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;

class NativeFileIntegrationTest {

    @Test
    @EnabledOnOs(OS.LINUX)
    void readsPermissionsUsingLinuxFileAttributes() {
        // ...
    }
}
```

You can use `@DisabledOnOs(OS.WINDOWS)` if a test applies to other operating systems yet is unsuitable for Windows. Restrict by OS only when behavior genuinely differs or depends on OS APIs. For pure Java logic that can run cross-platform, prefer cross-platform tests rather than accidentally narrowing verification scope.

Condition annotations can be placed on methods or classes. When placed on a class, the condition applies to tests within that class. Document a clear reason when disabling a test on a particular platform so maintainers understand why it does not run in that environment.

## 6. Enabling Tests by Java Version

An application may support multiple JDK versions, or a test may verify behavior that exists only on a specific version. JUnit provides `@EnabledOnJre`, `@DisabledOnJre`, `@EnabledForJreRange`, and `@DisabledForJreRange`.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnJre;
import org.junit.jupiter.api.condition.JRE;

class RuntimeCompatibilityTest {

    @Test
    @EnabledOnJre(JRE.JAVA_21)
    void verifiesBehaviorSpecificToJava21() {
        // ...
    }
}
```

If you need to check a version range:

```java
@Test
@EnabledForJreRange(min = JRE.JAVA_17, max = JRE.JAVA_21)
void verifiesSupportedRuntimeRange() {
    // ...
}
```

JRE conditions are helpful when testing runtime compatibility, APIs, or version-dependent behavior. They do not replace a CI matrix running the application across all supported JDKs. If a project promises support for Java 17 and 21, the pipeline still needs to actually execute tests on both runtimes; an annotation only decides which tests apply in the current runtime.

## 7. Enabling or Disabling Tests by System Property

System properties fit when a build or launcher explicitly passes a configuration flag. Use `@EnabledIfSystemProperty` or `@DisabledIfSystemProperty` to check the property name and a regular expression for its value.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

class ExternalPaymentIntegrationTest {

    @Test
    @EnabledIfSystemProperty(named = "run.external.tests", matches = "true")
    void chargesPaymentThroughConfiguredSandbox() {
        // Call the payment sandbox configured for the test
    }
}
```

You can enable the test by passing the property to the JVM:

```bash
./gradlew test -Drun.external.tests=true
```

Or with Maven:

```bash
mvn test -Drun.external.tests=true
```

If the property is absent or does not match the regex, the test is not enabled. Use `@DisabledIfSystemProperty` to express the inverse condition. Because `matches` is a regular expression, write a clear pattern; if you want an exact match for `true`, do not use an overly broad pattern like `.*true.*`.

Do not use system properties to hide an essential test when the pipeline is misconfigured. If an integration test must run in a release job, the pipeline should supply the property and validate configuration before running tests. A test disabled due to a missing property can produce a green report without providing the evidence the job requires.

## 8. Enabling or Disabling Tests by Environment Variable

Environment variables fit when configuration comes from the execution environment, container, or CI. JUnit provides `@EnabledIfEnvironmentVariable` and `@DisabledIfEnvironmentVariable`.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

class StagingContractTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_STAGING_CONTRACT_TESTS",
        matches = "true"
    )
    void verifiesOrderApiAgainstStagingContract() {
        // ...
    }
}
```

You can set the environment variable in the shell before running the build. On Linux/macOS:

```bash
RUN_STAGING_CONTRACT_TESTS=true ./gradlew test
```

On PowerShell:

```powershell
$env:RUN_STAGING_CONTRACT_TESTS = "true"
./gradlew test
```

If the variable is unset or its value does not match the regex, JUnit skips the test conditionally. This is convenient for tests depending on staging or a sandbox. However, if staging is a mandatory part of the release workflow, have the release job verify that the variable is enabled and the endpoint is validly configured; do not let a missing variable turn into a silent skip.

## 9. Unconditionally Disabling Tests with `@Disabled`

`@Disabled` is used when you need to temporarily disable a single test or an entire class. Always provide a reason so readers know why the test is not running and what conditions are needed to re-enable it.

```java
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

class LegacyPaymentIntegrationTest {

    @Test
    @Disabled("Payment sandbox is down for maintenance; tracked in OPS-241")
    void verifiesLegacyGatewaySettlement() {
        // ...
    }
}
```

`@Disabled` is an explicit, environment-independent decision to turn off a test. It suits a test broken by a known bug or a feature not yet testable in the current phase. Avoid leaving this annotation in place indefinitely without an owner, reason, or plan to re-enable.

If you only need to disable a test in one environment, consider an appropriate condition annotation instead of `@Disabled`. If a test must run in CI, disabling it removes important protection; track disabled tests in reports and review them periodically.

## 10. Using `Assumptions` for Runtime-Determined Conditions

JUnit Jupiter provides `Assumptions` to check an assumption during execution. If the assumption does not hold, the test aborts at that point and the rest of the method does not run.

```java
import static org.junit.jupiter.api.Assumptions.assumeTrue;

@Test
void readsCustomerFromOptionalSandbox() {
    assumeTrue(isSandboxAvailable(), "Sandbox is not available");

    Customer customer = sandboxClient.findCustomer("customer-42");

    assertNotNull(customer);
}
```

Unlike `@EnabledIfEnvironmentVariable`, assumptions can rely on dynamic checks such as whether an endpoint responds. Use timeouts on readiness checks and avoid calling external services indefinitely.

`assumingThat` lets you run a subset of assertions only when a condition holds, while the rest of the test continues:

```java
import static org.junit.jupiter.api.Assumptions.assumingThat;

@Test
void formatsCustomerResponse() {
    Customer customer = sampleCustomer();

    assertEquals("customer-42", customer.id());

    assumingThat(customer.hasPremiumStatus(), () -> {
        assertNotNull(customer.premiumBenefits());
    });
}
```

`assumeTrue` fits when the entire remainder of the test makes no sense if the condition is false. `assumingThat` fits when only one group of assertions is conditional while core assertions must still run.

Do not use assumptions to bypass failures in the application itself. For example, if a test requires a database and the database is a mandatory CI dependency, `assumeTrue(databaseIsAvailable())` can turn an infrastructure outage into an aborted test and make the job appear successful. In mandatory jobs, let initialization or preflight fail explicitly when required dependencies are unavailable.

## 11. Class-Level vs. Method-Level Conditions

Tags and condition annotations can generally be placed at either the class or method level. Choose the placement based on the scope to which the condition genuinely applies.

```java
@EnabledOnOs(OS.LINUX)
@Tag("integration")
class LinuxSocketIntegrationTest {

    @Test
    void opensUnixDomainSocket() {
        // ...
    }

    @Test
    @Tag("slow")
    void transfersLargePayloadOverSocket() {
        // ...
    }
}
```

The class-level OS condition applies to both tests; the `slow` tag is added only to the large-payload transfer method. This organization clarifies shared versus specific attributes.

For nested tests, check carefully whether an annotation is placed on the enclosing class or the nested class to avoid accidentally applying a condition too broadly. If one group runs only when an external service is present, place the condition on the class containing tests that depend on that service. Do not put a condition on a large class if only a single test requires an optional dependency.

## 12. Combining Tags with Conditions in Spring Projects

Tags and conditions can be used together. Tags help pipelines select test groups; conditions ensure tests only run in suitable environments.

```java
@Tag("integration")
@Tag("database")
@DataJpaTest
class OrderRepositoryIntegrationTest {

    @Test
    void persistsOrderAndReloadsIt() {
        // ...
    }
}
```

This test is categorized as integration/database and uses the JPA test slice. If the database is provided via Testcontainers, that dependency must be configured in the test runtime. Attaching a tag does not automatically start containers.

Another example is staging contract testing:

```java
@Tag("integration")
@Tag("external")
class OrderStagingContractTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_STAGING_CONTRACT_TESTS",
        matches = "true"
    )
    void returnsOrderAccordingToPublishedContract() {
        // ...
    }
}
```

Here, the pipeline can exclude `external` from fast feedback runs. A dedicated contract job selects `integration` or `external`; the condition further verifies that the environment flag is enabled. If that job is required to execute tests, CI configuration must ensure the environment variable is present and never accept all tests being skipped.

An important note in Spring: JUnit tags do not activate `@ActiveProfiles`, change Spring profiles, register beans, or replace datasource configurations. If a test needs the `integration` profile, declare `@ActiveProfiles("integration")` or the corresponding configuration separately. Tags only categorize tests for JUnit Platform.

## 13. What Happens When Tests Are Filtered or Disabled?

When a test is excluded by a tag filter, JUnit Platform does not include it in the selected execution set. When a condition is unsatisfied or a test carries `@Disabled`, the test is discovered but its body is skipped, usually appearing as skipped in reports. When an assumption fails during execution, the run is typically reported as aborted.

This distinction is helpful when reading reports:

| Status | Common Cause | What to Check |
| --- | --- | --- |
| Absent from selected set | Excluded by include/exclude tag filter or selector | Build tool configuration, suite, and test tags |
| Skipped/disabled | `@Disabled` or unsatisfied condition | Disable reason, properties, environment variables, OS, or JRE |
| Aborted | Unsatisfied assumption or explicit abort | Which assumption failed and whether it is truly an optional dependency |
| Failed | Assertion, exception, or initialization/execution error | Test logic, configuration, or actual application bug |

Do not treat skipped or aborted test counts as unimportant details. A job can report success while an entire critical test group never ran. Surface skipped test counts and inspect their causes in pipelines that act as release gates.

## 14. Designing a Tag Set for CI Stages

A simple tag vocabulary can support different execution stages:

| Stage | Included Groups | Excluded Groups | Purpose |
| --- | --- | --- | --- |
| During development | `unit` | `slow`, `external` | Fast feedback for small changes |
| Pull request | `unit`, `smoke` via dedicated task | `external`, `long-running` | Quick verification of key behaviors |
| Integration pipeline | `integration` | `long-running` if run in a separate job | Verify Spring and infrastructure collaboration |
| Contract verification | `external` or agreed contract tag | Do not exclude mandatory contract groups | Verify compatibility with partner systems |
| Pre-release | Suite per release policy | Only temporarily approved exclusions | Produce evidence for high-risk flows |

This table is only an example of organization. Projects must define which tags go on which tests and which jobs are responsible for running them. If an important test belongs to no mandatory job, it may never run despite existing in source control.

Avoid creating too many synonymous tags or per-developer tags. When a test carries `integration`, `database`, and `slow`, readers should see each label representing an independent attribute. If two tags are always used together and produce no distinct filtering, a single clearer tag may suffice.

## 15. Conditions Must Be Deterministic

Test execution conditions are part of pipeline design. If a condition depends on random data, flaky network state, or time of day, test results can become erratic.

Prefer conditions that are:

- Clearly determined before tests run, such as OS, JRE, or build-supplied properties.
- Backed by clear defaults documented in project configuration.
- Supported by an explicit business or technical reason for not running.
- Observable in CI reports so operators know whether tests ran or were skipped.
- Re-evaluated when changing environments, JDKs, or infrastructure.

For external services, distinguish two situations clearly: optional dependent tests may skip when the environment is not provisioned; release-contract tests must fail if the required environment is unavailable. Never turn a configuration mistake into an accidental skip condition.

When using `@EnabledIfSystemProperty` or `@EnabledIfEnvironmentVariable`, choose meaningful flag names such as `run.external.tests` or `RUN_STAGING_CONTRACT_TESTS`. Avoid vague flags like `enabled=true`, because later it becomes hard to tell which behavior group they enable.

## 16. Writing Custom Conditions via Extensions When Needed

Built-in annotations cover most common cases. When a project needs a more complex shared enable/disable rule, JUnit Jupiter allows writing an extension implementing `ExecutionCondition`.

Simple skeleton example:

```java
import org.junit.jupiter.api.extension.ConditionEvaluationResult;
import org.junit.jupiter.api.extension.ExecutionCondition;
import org.junit.jupiter.api.extension.ExtensionContext;

class ExternalServiceCondition implements ExecutionCondition {

    @Override
    public ConditionEvaluationResult evaluateExecutionCondition(
            ExtensionContext context) {

        String enabled = System.getProperty("run.external.tests", "false");

        if (Boolean.parseBoolean(enabled)) {
            return ConditionEvaluationResult.enabled(
                "External tests were enabled"
            );
        }

        return ConditionEvaluationResult.disabled(
            "Set -Drun.external.tests=true to enable external tests"
        );
    }
}
```

Register the extension with `@ExtendWith`:

```java
@ExtendWith(ExternalServiceCondition.class)
class ExternalGatewayTest {

    @Test
    void verifiesGatewayContract() {
        // ...
    }
}
```

Extensions centralize rules and return explicit enabled/disabled reasons. However, do not create a custom extension for a simple condition already handled by built-in annotations. A shared extension must be documented, behave deterministically, and never mask critical configuration errors.

When checking whether a service is available, weigh the cost of network calls inside `evaluateExecutionCondition`. Network calls there can slow down or destabilize discovery. If dynamic dependency checks are unavoidable, use short timeouts, avoid side effects, and consider performing a separate preflight step in the pipeline so infrastructure errors are reported clearly.

## 17. Complete Strategy Example for an Orders Module

Suppose an application has tests for orders, repositories, and a payment gateway. The team can classify and gate them as follows:

```java
@Tag("unit")
class OrderPricingTest {

    @Test
    void calculatesTotalAfterApplyingEligibleDiscount() {
        // ...
    }
}
```

```java
@Tag("integration")
@Tag("database")
@DataJpaTest
class OrderRepositoryTest {

    @Test
    void persistsAndReloadsOrderWithLineItems() {
        // ...
    }
}
```

```java
@Tag("integration")
@Tag("external")
class PaymentGatewayContractTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_PAYMENT_SANDBOX_TESTS",
        matches = "true"
    )
    void acceptsPaymentRequestAccordingToGatewayContract() {
        // ...
    }
}
```

In the fast feedback loop, the build includes `unit` and excludes `slow`, `external`. In the database job, the build includes `integration` and `database`; in the payment sandbox job, the build includes `external` or `integration` per project policy while setting `RUN_PAYMENT_SANDBOX_TESTS=true`.

For mandatory sandbox tests, the pipeline should validate that the flag is enabled before running. If the flag is missing, the job should report an invalid configuration instead of letting JUnit mark tests skipped and exit successfully.

## 18. Common Pitfalls

- **Adding tags without configuring filters:** tests still run with the whole suite; tags do not automatically create separate run groups.
- **Confusing tags with Spring profiles:** `@Tag("integration")` does not activate `@Profile("integration")` or `@ActiveProfiles`.
- **Adding `@Disabled` without a reason:** maintainers cannot tell why the test stopped running or when it can be re-enabled.
- **Skipping essential tests when dependencies fail:** pipelines can stay green even when a required database or service is down.
- **Using conditions instead of compatibility testing:** `@EnabledOnJre` does not prove the app works on every supported JDK; CI must run the runtime matrix.
- **Using assumptions for product bugs:** assumptions must not turn a failing assertion or mandatory error into an aborted status.
- **Overly granular tags:** too many labels make filter configuration complex and hard to maintain.
- **Not monitoring skipped tests:** tests skipped for a long time lose protective value unnoticed.
- **Conditions with side effects:** evaluating conditions by creating data or mutating state makes discovery unpredictable.

## 19. Workflow for Choosing the Right Mechanism

When adding a new test, determine requirements in order:

1. **Which group does the test belong to?** Attach tags like `unit`, `integration`, `database`, or `external` if the team needs to filter tests by those traits.
2. **Does it require a specific environment to run?** Use condition annotations for OS, JRE, system properties, or environment variables.
3. **Is a condition only known at runtime?** Use `Assumptions` if it is genuinely an optional assumption; for mandatory dependencies, let preflight or the test fail explicitly.
4. **Does the test need to be turned off temporarily?** Use `@Disabled` with a reason, an owner/issue tracker reference, and a re-enable plan.
5. **Which pipeline must run this test?** Ensure at least one mandatory job includes the matching tag group and monitors skipped tests.

A reliable test suite does not merely contain many tests—it also shows which tests ran, which were excluded, and why. Tags organize suites by purpose; conditions constrain tests to appropriate environments; assumptions handle runtime preconditions. Used in their proper roles alongside visibility into skipped tests, teams can speed up feedback loops while retaining the verification evidence required for Spring applications.
