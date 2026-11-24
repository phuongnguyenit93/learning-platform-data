# `@DisabledInAotMode` and Environment-Based Test Conditions

Not every test fits every execution mode. Some tests rely on behavior available only in standard runtime, whereas Spring can pre-generate metadata and `ApplicationContext` initialization for Ahead-of-Time (AOT) execution. Other tests are meaningful only on a specific operating system, JDK version, or CI environment with external services available.

Spring Test provides `@DisabledInAotMode` to explicitly exclude tests incompatible with AOT mode. Spring TestContext and JUnit Jupiter also provide conditions to enable or disable tests based on expressions, system properties, environment variables, operating systems, and Java versions. Choosing conditions based on the actual root cause keeps the suite running within the right scope without hiding real bugs that need detection.

## 1. AOT Mode in Spring Testing

Ahead-of-Time processing prepares part of the work Spring normally performs when starting an application. Instead of relying solely on runtime scanning and analysis, Spring can analyze configuration at build time, generate initialization code, and use the generated artifacts at runtime.

With the Spring TestContext Framework, AOT support allows pre-processing eligible test `ApplicationContext` instances and generating corresponding initializers. When tests run in AOT mode, Spring can use the prepared configuration instead of running the full context-building process in the standard way.

This helps applications start faster and supports environments such as native images. However, a test may depend on behavior available only during dynamic initialization or a context customization incompatible with the AOT path the project uses.

Do not equate AOT with running tests on a specific operating system or JDK. AOT is an application processing and initialization mode; conditions for OS, JDK, or environment variables are separate environmental dimensions.

## 2. When Is `@DisabledInAotMode` Used?

`@DisabledInAotMode` is a Spring TestContext annotation in the `org.springframework.test.context.aot` package. Introduced in Spring Framework 6.2, this annotation marks a test class or test method to be disabled when tests run in AOT mode.

Class-level example:

```java
import org.springframework.test.context.aot.DisabledInAotMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfig.class)
@DisabledInAotMode
class RuntimeOnlyContextTests {

    @Test
    void checksRuntimeOnlyContextCustomization() {
        // This test runs only in regular test mode.
    }
}
```

When AOT mode is not enabled, the test still executes normally. When AOT mode is enabled, Spring Test skips tests covered by the annotation.

You can disable only a single method in a class:

```java
@SpringJUnitConfig(TestConfig.class)
class ContextTests {

    @Test
    void aotCompatibleTestStillRuns() {
        // This test still runs in AOT mode.
    }

    @Test
    @DisabledInAotMode
    void testRequiresRuntimeOnlyBehavior() {
        // Only this test is disabled in AOT mode.
    }
}
```

Place the annotation at the class level when the entire test class depends on incompatible behavior. Place it at the method level when only one scenario requires special runtime behavior. Keep AOT-compatible tests active so you maintain coverage for this mode.

## 3. When Should a Test Be Disabled in AOT Mode?

Use `@DisabledInAotMode` only after confirming a test cannot run properly in the current AOT mode and there is no suitable configuration way to support it. Examples might be a test relying on dynamic `ApplicationContext` structural mutations after AOT artifacts were generated, or a test fixture mechanism incompatible with the generated initializer.

Before disabling, consider:

- Can the test be rewritten to use beans or configuration declared prior to AOT processing?
- Can pure Java logic checks be separated from runtime context dependencies?
- Can another test verify the same contract using an AOT-compatible configuration?
- Does the test genuinely not apply in AOT mode, or is it merely missing required AOT configuration?

Do not use this annotation as a way to ignore an uninvestigated AOT error. If a critical controller, service, or production configuration fails in AOT mode, fix it or add tests for the AOT path instead of disabling the test covering it.

## 4. Scope and How Spring Processes the Annotation

`@DisabledInAotMode` can be placed on a test class or a test method. A class-level annotation applies to all test methods in the class; a method-level annotation affects only that method. This annotation is intended for Spring TestContext AOT conditions, not for selecting operating systems or environment variables.

It can be placed alongside standard test configuration annotations:

```java
@SpringBootTest
@DisabledInAotMode
class RuntimeConfigurationTests {
    // Test context is configured normally when not running AOT.
}
```

When running in AOT mode, Spring Test evaluates the condition and disables the corresponding tests. Tests are not removed from source code or from regular runs; the disabled state depends on the execution mode.

## 5. Expression-Based Conditions with Spring `@EnabledIf` and `@DisabledIf`

Spring TestContext provides `@EnabledIf` and `@DisabledIf` in the `org.springframework.test.context.junit.jupiter` package. These two annotations use Spring Expression Language (SpEL) expressions to decide whether a test should run.

Example running a test only when the `test.environment` system property equals `integration`:

```java
import org.springframework.test.context.junit.jupiter.EnabledIf;

@Test
@EnabledIf(expression = "#{systemProperties['test.environment'] == 'integration'}")
void runsOnlyInIntegrationEnvironment() {
    // Check depending on the integration environment.
}
```

Conversely, use `@DisabledIf` when you want to skip a test if a condition evaluates to true:

```java
import org.springframework.test.context.junit.jupiter.DisabledIf;

@Test
@DisabledIf(expression = "#{systemEnvironment['CI'] == 'true'}")
void skipsWhenRunningOnCi() {
    // Runs only when the CI condition is not true.
}
```

Expressions can access `systemProperties` and `systemEnvironment`. The `loadContext` attribute defaults to `false`; enable `loadContext = true` only when the expression needs beans or information from the `ApplicationContext`. Loading the context solely to check a simple environment variable is usually unnecessary.

Example using a bean in the context when truly needed:

```java
@Test
@EnabledIf(
        expression = "#{featureSwitch.enabled}",
        loadContext = true)
void runsWhenFeatureSwitchIsEnabled() {
    // FeatureSwitch is a bean in the test ApplicationContext.
}
```

Spring's `@EnabledIf` and `@DisabledIf` fit when a condition needs a SpEL expression or information from the Spring context. If you only need to match a system property or environment variable, JUnit's built-in conditional annotations are usually simpler.

## 6. Environment Variable Conditions with JUnit Jupiter

JUnit Jupiter provides `@EnabledIfEnvironmentVariable` and `@DisabledIfEnvironmentVariable` in the `org.junit.jupiter.api.condition` package.

Run a test only when the `RUN_EXTERNAL_TESTS` variable has the value `true`:

```java
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

@Test
@EnabledIfEnvironmentVariable(named = "RUN_EXTERNAL_TESTS", matches = "true")
void callsExternalTestEnvironment() {
    // Test depending on an external service.
}
```

It can be applied at the class level so the entire class runs only when the environment matches:

```java
@SpringBootTest
@EnabledIfEnvironmentVariable(named = "TEST_DATABASE_URL", matches = ".+")
class ExternalDatabaseIntegrationTests {
    // Tests requiring a database provided by the environment.
}
```

`matches` is a regular expression. The pattern `.+` requires the variable to exist and have at least one character. This condition only checks that the variable has a value; tests still need to verify that the service actually connects and handle errors when the endpoint is unavailable.

You can use `@DisabledIfEnvironmentVariable` to express a skip condition directly:

```java
@Test
@DisabledIfEnvironmentVariable(named = "OS", matches = "Windows_NT")
void usesUnixSpecificTooling() {
    // Skip on Windows.
}
```

## 7. System Property Conditions

System properties are typically passed via JVM `-Dname=value` arguments. JUnit Jupiter provides `@EnabledIfSystemProperty` and `@DisabledIfSystemProperty`.

Example running a test only when the JVM is launched with a property enabling integration tests:

```java
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

@Test
@EnabledIfSystemProperty(named = "test.integration", matches = "true")
void runsWhenIntegrationPropertyIsEnabled() {
    // Integration test explicitly enabled.
}
```

System properties can be used to select test implementations or environments, but keep that configuration in the build/test launcher rather than setting the property inside the test method itself and checking it again. If a test enables its own condition, the condition no longer controls the execution environment.

Distinguishing system properties from environment variables:

| Configuration Type | Common Way Provided | Java Lookup API | JUnit Annotation |
|---|---|---|---|
| System property | `-Dtest.integration=true` | `System.getProperty("test.integration")` | `@EnabledIfSystemProperty` |
| Environment variable | Process environment variable | `System.getenv("RUN_EXTERNAL_TESTS")` | `@EnabledIfEnvironmentVariable` |

## 8. Operating System and Java Version Conditions

When a test depends on an API or command specific to an operating system, use OS annotations:

```java
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.DisabledOnOs;
import org.junit.jupiter.api.condition.OS;

@Test
@EnabledOnOs(OS.LINUX)
void usesLinuxFilePermissions() {
    // Verify Linux-specific behavior.
}

@Test
@DisabledOnOs(OS.WINDOWS)
void usesUnixShellCommand() {
    // Do not run on Windows.
}
```

For Java versions:

```java
import org.junit.jupiter.api.condition.EnabledOnJre;
import org.junit.jupiter.api.condition.EnabledForJreRange;
import org.junit.jupiter.api.condition.JRE;

@Test
@EnabledOnJre(JRE.JAVA_21)
void verifiesJava21SpecificBehavior() {
    // Runs only on Java 21.
}

@Test
@EnabledForJreRange(min = JRE.JAVA_17)
void runsOnSupportedJavaVersions() {
    // Runs on Java 17 and above within JRE versions recognized by JUnit.
}
```

OS/JRE conditions are JUnit conditions, not Spring TestContext conditions. They can be used normally in Spring tests; Spring still creates the context per test configuration if the conditions allow the method/class to execute.

## 9. Combining Multiple Conditions

A test may require both a specific operating system and a specific environment variable at the same time. For example, a test calling tooling available only on Linux and running only when CI provides a service:

```java
@Test
@EnabledOnOs(OS.LINUX)
@EnabledIfEnvironmentVariable(named = "RUN_CONTAINER_TESTS", matches = "true")
void testsLinuxContainerIntegration() {
    // Requires Linux and an environment with container tests enabled.
}
```

When multiple conditions are declared, the test is eligible only if the conditions allow it to run. Place conditions at the narrowest scope needed: method level if only one scenario depends on the environment, class level if the entire class shares the same condition.

Do not attach an OS or environment variable condition to a large test class just because one method uses a specialized tool. Separating the method or class lets independent tests continue running in every environment.

## 10. Using `Assumptions` When Conditions Are Known Only During Test Execution

Conditional annotations are evaluated before the test method executes. If you need to check a condition after calling an API or initializing a fixture, JUnit provides `Assumptions`:

```java
import static org.junit.jupiter.api.Assumptions.assumeTrue;

@Test
void checksOptionalService() {
    assumeTrue(isTestServiceAvailable(),
            "Optional test service is not available");

    // Test body runs only when the service is available.
}
```

When an assumption fails, JUnit marks the test as aborted (conditionally skipped), not failed. This is useful when connectivity can only be determined at runtime.

Do not use assumptions to hide failures in the application itself. If a service is required to be present in CI yet is unavailable, the build should fail or have an explicit environment check instead of silently skipping tests.

## 11. Distinguishing Test Execution Conditions from Spring Profile Configuration

`@ActiveProfiles` selects profiles used to load beans and configuration for the `ApplicationContext`. It does not automatically disable a test when a profile is not selected.

Example:

```java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationProfileTests {
    // Context is created with the integration profile.
}
```

If you need a test to run only when a profile is selected externally, you can use a SpEL condition reading environment configuration or a system property passed by the build. Avoid mistaking `@ActiveProfiles("integration")` for an automatic check that the profile was enabled externally; this annotation actively instructs Spring to activate that profile for the test context.

`@TestPropertySource` and the `properties` attribute on test annotations also supply configuration to the context. They modify the test context's environment, not a test-skipping mechanism.

## 12. Example of Organizing Tests by Environment

Suppose a project has unit tests, AOT tests, and integration tests requiring an external database:

```text
src/test/java
  service/
    OrderServiceTests.java
  context/
    RuntimeOnlyContextTests.java
  integration/
    DatabaseIntegrationTests.java
  aot/
    AotCompatibleContextTests.java
```

Classes can declare conditions according to their purpose:

```java
// Logic test independent of environment.
class OrderServiceTests {
    // Runs in every test environment.
}

// Test depending on context behavior available only at standard runtime.
@SpringBootTest
@DisabledInAotMode
class RuntimeOnlyContextTests {
    // Excluded from AOT runs.
}

// Test requiring a database provided by CI or developer.
@SpringBootTest
@EnabledIfEnvironmentVariable(named = "TEST_DATABASE_URL", matches = ".+")
class DatabaseIntegrationTests {
    // Runs only when a database URL is declared.
}

// Test verifying configuration works in the AOT path.
@SpringBootTest
class AotCompatibleContextTests {
    // Keep this test active in the AOT pipeline.
}
```

Separating scopes makes the suite easier to read: logic tests always run, AOT-incompatible tests are clearly marked, tests depending on external services have environment conditions, and AOT-compatible tests continue verifying the pre-generated path.

## 13. Choosing Annotations by Need

| Need | Annotation/Mechanism | Source |
|---|---|---|
| Skip test when Spring runs in AOT mode | `@DisabledInAotMode` | Spring TestContext |
| Enable/disable with SpEL expression | `@EnabledIf`, `@DisabledIf` | Spring TestContext |
| Enable/disable by environment variable | `@EnabledIfEnvironmentVariable`, `@DisabledIfEnvironmentVariable` | JUnit Jupiter |
| Enable/disable by system property | `@EnabledIfSystemProperty`, `@DisabledIfSystemProperty` | JUnit Jupiter |
| Run only on specific OS | `@EnabledOnOs`, `@DisabledOnOs` | JUnit Jupiter |
| Run only on specific JDK or JDK range | `@EnabledOnJre`, `@EnabledForJreRange` | JUnit Jupiter |
| Condition determinable only inside test body | `Assumptions.assumeTrue(...)` | JUnit Jupiter |
| Select bean/configuration profile | `@ActiveProfiles` | Spring TestContext; not a skip condition |

## 14. Common Mistakes

| Symptom | Common Cause | Resolution |
|---|---|---|
| Test is unexpectedly disabled in AOT | `@DisabledInAotMode` placed at class level or broad meta-annotation | Move annotation to the exact method or remove it once the test is compatible |
| AOT tests do not run and nobody notices | Overly broad disable annotation used | Mark only genuinely incompatible tests and keep representative AOT-compatible tests |
| `@EnabledIf` cannot read a bean | `loadContext` remains at default `false` | Set `loadContext = true` when the expression truly needs a bean/context |
| Environment condition is always false | Confusing system property with environment variable or regex mismatch | Check how configuration is passed and the actual variable value |
| Integration test is unexpectedly skipped on CI | Pipeline has not supplied the required environment variable | Configure the variable in the appropriate job or adjust condition for supported environments |
| Test depends on profile yet still runs | `@ActiveProfiles` only selects profiles, not a disable condition | Use a dedicated condition if skipping by profile/runtime environment is needed |
| Test is skipped after starting execution | `Assumptions` fails inside test body | Identify unavailable service/fixture; decide whether it is optional or mandatory in CI |
| OS-specific test runs on wrong platform | Condition placed on another method or overly broad class | Apply `@EnabledOnOs`/`@DisabledOnOs` at the right scope |

## 15. Usage Guidelines

- Use `@DisabledInAotMode` for tests confirmed incompatible with AOT mode; do not use it to bypass uninvestigated AOT failures.
- Place conditions at the method level if only one test depends on the environment; use class-level when the entire class shares the same condition.
- Use dedicated JUnit annotations for OS, JRE, system properties, and environment variables.
- Use Spring's `@EnabledIf` or `@DisabledIf` when you need SpEL expressions or information from the Spring context.
- Set `loadContext = true` only when the expression actually needs beans or the context.
- Use `Assumptions` when a condition can only be determined while the test is running.
- Do not allow critical CI tests to be silently skipped merely because an environment variable is missing.
- Keep a group of AOT-compatible tests active to verify the generated context path.

## 16. Summary

Spring TestContext's `@DisabledInAotMode` (Spring Framework 6.2+) disables a test class or method when running in AOT mode. For environment-based conditions, Spring `@EnabledIf`/`@DisabledIf` support SpEL; JUnit Jupiter provides dedicated annotations for environment variables, system properties, OS, and JRE. `Assumptions` fit when conditions are known only during execution. `@ActiveProfiles` only selects profiles for the context and does not skip tests automatically. Choose the right condition type and apply it at the smallest necessary scope so the suite continues running thoroughly in environments that support it.

