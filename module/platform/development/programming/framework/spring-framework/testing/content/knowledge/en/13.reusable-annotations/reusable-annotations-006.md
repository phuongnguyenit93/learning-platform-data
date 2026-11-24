# @EnabledIf, @DisabledIf, and Conditions from Spring

In a test suite, there are tests that only suit a certain environment. For example, an integration test needing an external service should only run when CI has enabled the corresponding test group; a test needing a special bean or configuration only makes sense when a feature flag is on; a test might temporarily be skipped during system maintenance. JUnit Jupiter provides several conditional mechanisms to enable or skip tests. The Spring TestContext Framework adds `@EnabledIf` and `@DisabledIf`, allowing conditions to be expressed with Spring Expression Language (SpEL) or properties in the Spring `Environment`.

These two annotations are JUnit Jupiter execution conditions. They decide whether a test class or test method is executed based on the declared expression. They do not decide which beans are registered in the `ApplicationContext`; that job belongs to Spring configuration mechanisms such as `@Profile`, `@Conditional`, and other bean registration conditions.

## 1. Role of `@EnabledIf` and `@DisabledIf`

`@EnabledIf` allows a test to run when the expression evaluates to true. `@DisabledIf` skips a test when the expression evaluates to true.

| Annotation | Expression is true | Expression is false |
|---|---|---|
| @EnabledIf | Test is enabled and can run | Test is skipped |
| @DisabledIf | Test is skipped | Test is allowed to run |

The condition is evaluated by JUnit Jupiter before executing the corresponding test container or test method. When placed on a class, the condition applies to the test methods inside that class. When placed on a method, the condition applies only to the annotated method.

For example, a group of tests verifying a real payment system might only run when the test process has a flag enabled:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@EnabledIf(
        expression = "#{systemProperties['tests.external'] == 'true'}",
        reason = "External integration tests are enabled only on demand"
)
class ExternalPaymentIntegrationTest {
    @Test
    void chargesThroughTheExternalGateway() {
        // Test calls the payment gateway in a prepared integration environment.
    }
}
~~~

When running the JVM with system property `tests.external=true`, the expression is true and tests in the class are enabled. If the property is not set or has a value other than `true`, the condition is not satisfied and the test class is skipped. With conditions based only on system properties, there is no need to load the Spring `ApplicationContext` just to evaluate the expression.

You can use `@DisabledIf` to skip a test while a maintenance mode is enabled:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.DisabledIf;

class InventoryMaintenanceTest {
    @Test
    @DisabledIf(
            expression = "#{systemProperties['inventory.maintenance'] == 'true'}",
            reason = "Inventory writes are unavailable during maintenance"
    )
    void updatesInventory() {
        // Verifies inventory write operations.
    }
}
~~~

When `inventory.maintenance=true`, the method is skipped. When the condition is false, the method is allowed to run.

## 2. Correct Package and Scope of Support

Spring's annotations reside in the package:

~~~java
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.junit.jupiter.DisabledIf;
~~~

Spring provides them in the Spring TestContext Framework for integration with JUnit Jupiter. They were introduced in Spring Framework 5.0 and are used together with `SpringExtension`. If the test needs Spring configuration, you can register the extension via `@SpringJUnitConfig` or via `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`.

Common configuration example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@SpringJUnitConfig(FeatureTestConfig.class)
@EnabledIf(expression = "#{systemProperties['feature.tests'] == 'true'}")
class FeatureIntegrationTest {
    @Test
    void verifiesFeatureIntegration() {
        // Verifies feature integration.
    }
}
~~~

Since JUnit Jupiter 5.7, JUnit also has conditional annotations named `@EnabledIf` and `@DisabledIf`. Therefore, when using Spring's annotations, explicitly import `org.springframework.test.context.junit.jupiter`. The IDE may accidentally pick the identically named type from the JUnit package if you do not check imports.

These two Spring annotations are meant for the JUnit Jupiter model. Do not assume they work as general conditional annotations for JUnit 4 or TestNG. For tests using JUnit 4, Spring previously had profile-based conditional mechanisms such as `@IfProfileValue`; that is a different API and should not be mixed with JUnit Jupiter annotations.

## 3. Supported Expressions

The `expression` attribute of both annotations accepts three main forms:

1. A Spring Expression Language (SpEL) expression.
2. A placeholder for a property present in the Spring `Environment`.
3. A text literal.

The result is considered true if the expression returns `Boolean.TRUE` or a `String` equal to `true`, case-insensitively. Other results do not satisfy the enable condition of `@EnabledIf` or the disable condition of `@DisabledIf`.

### 3.1. Spring Expression Language (SpEL)

SpEL is useful when the condition is a logical expression based on system properties, bean state, or values accessible to Spring.

Example checking the operating system:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@EnabledIf(
        expression = "#{systemProperties['os.name'].toLowerCase().contains('mac')}",
        reason = "This test requires a macOS environment"
)
class MacSpecificIntegrationTest {
    @Test
    void usesMacSpecificIntegration() {
        // Test only runs on macOS.
    }
}
~~~

In SpEL, `systemProperties` lets you read JVM system properties. The expression calls `toLowerCase()` on the OS name and checks whether the string contains `mac`. This example illustrates SpEL's capability; if you only need to select an operating system, JUnit's built-in annotations such as `@EnabledOnOs` are usually shorter and clearer in intent.

You can check a flag passed from the command line:

~~~java
@EnabledIf(
        expression = "#{systemProperties['tests.database.integration'] == 'true'}",
        reason = "Database integration tests require an explicit opt-in"
)
class DatabaseIntegrationTest {
    @Test
    void queriesTheConfiguredDatabase() {
        // Integration test with database.
    }
}
~~~

Run the test with:

~~~text
-Dtests.database.integration=true
~~~

If you need to use a bean in the `ApplicationContext`, SpEL can reference the bean by name. In that case, the context must be loaded so the bean exists:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(FeatureTestConfig.class)
@EnabledIf(
        expression = "#{@testCapabilities.externalServiceAvailable}",
        loadContext = true,
        reason = "The external service is available in this test environment"
)
class ExternalServiceTest {
    @Test
    void callsTheExternalService() {
        // Verifies integration based on capabilities provided by the bean.
    }
}
~~~

In the example, `testCapabilities` is a bean with an `externalServiceAvailable` property, for instance provided by an `isExternalServiceAvailable()` method. SpEL reads the bean's property to decide whether to enable the test. The `loadContext = true` attribute asks Spring to load the context before evaluating the expression.

### 3.2. Placeholders from the Spring `Environment`

If the condition depends only on a property, a dollar-and-braces placeholder is usually easier to read than SpEL:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(FeatureTestConfig.class)
@TestPropertySource(properties = "tests.smoke.enabled=true")
@EnabledIf(
        expression = "${tests.smoke.enabled:false}",
        loadContext = true,
        reason = "Smoke tests are enabled by the test configuration"
)
class SmokeTest {
    @Test
    void verifiesTheSmokeScenario() {
        // Smoke test.
    }
}
~~~

Spring replaces the placeholder with the value of the property in the `Environment`. In the example, `@TestPropertySource` supplies `true`. The `:false` part is the default value if the property is not declared, preventing the condition from depending on every environment having that property.

When a property is provided by the test context configuration, such as `@TestPropertySource` or a context initializer, use `loadContext = true` to ensure the context and corresponding `Environment` are ready before the expression needs them. For conditions that only read system properties or process environment variables without accessing beans/context, you can keep the default `loadContext = false`.

You can use a placeholder for an environment property to skip an unsuitable test group:

~~~java
@DisabledIf(
        expression = "${tests.external-service.disabled:false}",
        loadContext = true,
        reason = "The external service is disabled in this environment"
)
class ExternalServiceContractTest {
    @Test
    void verifiesTheExternalServiceContract() {
        // Contract test.
    }
}
~~~

If `tests.external-service.disabled` is `true`, the test is skipped. If the property does not exist, the default `false` prevents the condition from disabling the test.

### 3.3. Text Literals

An expression can also be a text literal:

~~~java
@EnabledIf("true")
class AlwaysEnabledTest {
}

@DisabledIf("true")
class AlwaysDisabledTest {
}
~~~

These literals usually add little value because `@EnabledIf("true")` is equivalent to an always-enabled test, while `@DisabledIf("true")` is equivalent to an always-skipped test. Spring recommends using dynamic expressions or property placeholders so conditions reflect the actual environment.

## 4. Annotation Attributes

The two Spring annotations have four main attributes:

| Attribute | Meaning |
|---|---|
| expression | Expression evaluated to decide the enable or disable condition |
| value | Alias for expression, commonly used for concise declarations |
| reason | Reason attached to the condition result |
| loadContext | Whether to require loading the ApplicationContext before evaluating the expression |

### `expression` and `value`

`value` is an alias for `expression`. The following two declarations are equivalent when no additional attributes are needed:

~~~java
@EnabledIf("#{systemProperties['ci'] == 'true'}")
class CiOnlyTest {
}

@EnabledIf(expression = "#{systemProperties['ci'] == 'true'}")
class CiOnlyTestWithExpression {
}
~~~

When you need to declare `reason` or `loadContext`, use the `expression` attribute name to express intent clearly:

~~~java
@EnabledIf(
        expression = "${tests.integration.enabled:false}",
        loadContext = true,
        reason = "Integration environment is configured"
)
class ConfiguredIntegrationTest {
}
~~~

In Spring's API, `value` and `expression` are two alternative names for the same value. Do not pass two different values to both attributes.

### `reason`

`reason` helps JUnit report the rationale associated with the condition. With `@DisabledIf`, this is useful information so report readers know why a test was skipped. With `@EnabledIf`, `reason` describes why the test was enabled when the condition evaluated to true.

~~~java
@DisabledIf(
        expression = "#{systemProperties['external.api.offline'] == 'true'}",
        reason = "External API is unavailable in this test run"
)
class ExternalApiTest {
}
~~~

Write a short `reason` stating the environment condition or required dependency. This helps distinguish an intentionally skipped test from a misconfigured one.

### `loadContext`

`loadContext` decides whether Spring proactively loads the `ApplicationContext` associated with the test to evaluate the expression. The default value is `false`.

| Case | Value to Consider |
|---|---|
| Only reading systemProperties | false |
| Only reading process environment variables | false |
| Expression does not access beans in the context | Usually false |
| SpEL references a bean in ApplicationContext | true |
| Property only exists in test-context-specific configuration | true |

Keeping `loadContext = false` when the context is not needed avoids initializing the entire application only to decide to skip a test. If the condition needs beans or configuration that only exist once the context is created, set `true` so Spring can provide them.

Do not set `loadContext = true` out of habit for every test. If the condition ends up false, loading the context before skipping the test still consumes time and may initialize databases, connection pools, or other integration components.

## 5. Applying at Class Level and Method Level

You can place `@EnabledIf` or `@DisabledIf` on a test class or a test method.

### Class-Level Conditions

When the annotation is placed on a class, the condition applies to the test methods inside the class. This fits when the whole group of tests shares the same environment requirements.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@EnabledIf(
        expression = "#{systemProperties['tests.payment.integration'] == 'true'}",
        reason = "Payment integration suite requires an explicit opt-in"
)
class PaymentIntegrationTests {
    @Test
    void authorizesPayment() {
        // ...
    }

    @Test
    void refundsPayment() {
        // ...
    }
}
~~~

When the class-level condition is not satisfied, JUnit skips the container class and methods inside are not executed. When the condition is satisfied, methods are allowed to run and remain subject to any other conditions if present.

### Method-Level Conditions

When only one scenario needs a specific condition, place the annotation on the method:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.junit.jupiter.DisabledIf;

class PaymentServiceTests {
    @Test
    void calculatesTheFee() {
        // Pure logic test without external system dependencies.
    }

    @Test
    @EnabledIf(
            expression = "#{systemProperties['tests.payment.gateway'] == 'true'}",
            reason = "A payment gateway is available for this run"
    )
    void sendsPaymentToGateway() {
        // Integration test with gateway.
    }

    @Test
    @DisabledIf(
            expression = "#{systemProperties['tests.payment.readOnly'] == 'true'}",
            reason = "The configured payment environment is read-only"
    )
    void changesPaymentState() {
        // Test that needs to mutate payment state.
    }
}
~~~

Within the same class, pure logic tests still run normally; only methods with specific conditions are restricted. This organization keeps infrastructure requirements close to the tests that actually need them.

### Combining Class and Method Conditions

JUnit evaluates the conditions applied to both the container and the method. If the class-level condition does not allow execution, methods inside cannot run solely because of a separate method-level condition. If the class is enabled, the method condition further decides whether the specific method is executed.

Keep conditions easy to understand and avoid placing conflicting expressions on the same scope. If a group of tests always needs the same profile or bean configuration, use a dedicated test configuration; if only one method needs an optional dependency, put the condition on the method so the scope is clearly bounded.

## 6. Using Conditions Based on Spring Beans

One advantage of Spring `@EnabledIf` and `@DisabledIf` is that SpEL expressions can reference beans when the context is loaded. This is useful when whether a test can run depends on a component configured in the application, such as an integration adapter, feature capability, or environment information.

Example configuration of a bean providing availability status:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class FeatureTestConfig {
    @Bean
    TestCapabilities testCapabilities(Environment environment) {
        boolean available = environment.getProperty(
                "external.service.available",
                Boolean.class,
                false);
        return new TestCapabilities(available);
    }
}

class TestCapabilities {
    private final boolean externalServiceAvailable;

    TestCapabilities(boolean externalServiceAvailable) {
        this.externalServiceAvailable = externalServiceAvailable;
    }

    public boolean isExternalServiceAvailable() {
        return externalServiceAvailable;
    }
}
~~~

Test referencing the `testCapabilities` bean in SpEL:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(FeatureTestConfig.class)
@TestPropertySource(properties = "external.service.available=true")
@EnabledIf(
        expression = "#{@testCapabilities.externalServiceAvailable}",
        loadContext = true,
        reason = "The external service capability is available"
)
class ExternalCapabilityTest {
    @Test
    void runsTheCapabilityDependentScenario() {
        // Verifies behavior requiring an external service.
    }
}
~~~

Spring creates the context, registers the `testCapabilities` bean, and then SpEL reads the `externalServiceAvailable` property. Because the expression needs a bean in the context, `loadContext = true` is required.

Bean-based conditions should only be used when that state is genuinely part of the test configuration. Do not use a condition bean to perform an expensive network connection or an operation with side effects solely to decide whether to run a test. If you need to verify a real service is up, consider a lightweight health check, a separate setup step, or letting the integration test check connectivity and fail clearly.

## 7. Using Properties and Profiles to Select Test Groups

Conditions from Spring often work alongside `@ActiveProfiles`, `@TestPropertySource`, and `@DynamicPropertySource`.

### Profiles Select Bean Configuration

`@ActiveProfiles` determines active profiles for the test context. `@Profile` on bean configuration decides which beans are registered. `@EnabledIf` can read properties or related state to decide whether a group of tests should run.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
class ExternalClientTestConfig {
    @Bean
    @Profile("integration")
    ExternalClient externalClient() {
        return new RealExternalClient();
    }
}
~~~

Test using the `integration` profile:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@SpringJUnitConfig(ExternalClientTestConfig.class)
@ActiveProfiles("integration")
@EnabledIf(
        expression = "${tests.external.enabled:false}",
        loadContext = true,
        reason = "External integration tests are enabled by configuration"
)
class ExternalClientIntegrationTest {
    @Test
    void callsTheConfiguredClient() {
        // Tests the client configured for the integration profile.
    }
}
~~~

Profiles and test conditions have two distinct roles:

- `@ActiveProfiles("integration")` selects the profile used when creating the context.
- `@Profile("integration")` selects which beans are registered in the context.
- `@EnabledIf` decides whether the test runs in the current test run.

If the `integration` profile is already sufficient to define the test execution environment, you can use a clearly named property to enable/disable the test. Do not use test conditions as a replacement for profiles or use profiles just to represent a method toggle flag.

### Properties from `TestPropertySource`

`@TestPropertySource` fits fixed properties of a test group:

~~~java
@SpringJUnitConfig(ExternalClientTestConfig.class)
@TestPropertySource(properties = {
        "tests.external.enabled=true",
        "external.client.mode=stub"
})
@EnabledIf(
        expression = "${tests.external.enabled:false}",
        loadContext = true
)
class ConfiguredExternalClientTest {
}
~~~

When properties vary by CI environment, you can pass them to the JVM or configure the test task. The condition will reflect the value resolved by the Spring `Environment` according to property source precedence.

### Dynamic Properties from `DynamicPropertySource`

If a test uses Testcontainers or a service with a runtime port, `@DynamicPropertySource` can register dynamic values into the `Environment`. A condition can read that property if enabling the test truly depends on the registered value.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.junit.jupiter.EnabledIf;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ExternalClientTestConfig.class)
class ContainerBackedIntegrationTest {
    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("external.service.enabled", () -> true);
    }

    @Test
    @EnabledIf(
            expression = "${external.service.enabled:false}",
            loadContext = true
    )
    void callsTheContainerBackedService() {
        // Verifies integration once the dynamic property is registered.
    }
}
~~~

The example above illustrates how dynamic properties participate in the Spring `Environment`. In a real project, container lifecycle and property registration must be organized so resources are ready when the context is created. If the condition is only meant to determine whether a container can start, consider letting test setup or Testcontainers manage that instead of adding another lifecycle-dependent condition.

## 8. Creating Reusable Conditional Annotations

Spring allows using `@EnabledIf` and `@DisabledIf` as meta-annotations to create composed annotations. This is useful when many test classes follow the same condition.

Example creating an annotation for a test group depending on external services:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.test.context.junit.jupiter.EnabledIf;

@Target({ElementType.TYPE, ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@EnabledIf(
        expression = "${tests.external.enabled:false}",
        loadContext = true,
        reason = "External integration tests are enabled by configuration"
)
public @interface EnabledForExternalIntegration {
}
~~~

Using the composed annotation:

~~~java
@SpringJUnitConfig(ExternalClientTestConfig.class)
@EnabledForExternalIntegration
class ExternalClientContractTest {
    @Test
    void verifiesTheClientContract() {
        // ...
    }
}
~~~

You can also create an annotation to skip tests in a specific mode:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.test.context.junit.jupiter.DisabledIf;

@Target({ElementType.TYPE, ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@DisabledIf(
        expression = "${tests.database.readOnly:false}",
        loadContext = true,
        reason = "Database write tests are disabled in read-only mode"
)
public @interface DisabledInReadOnlyDatabaseMode {
}
~~~

Composed annotations help standardize conditions and reasons across a test suite. Name them after business or environment meaning, such as `@EnabledForExternalIntegration`, instead of having every test repeat the same long SpEL expression.

## 9. Distinguishing Spring Conditions from JUnit Conditional Annotations

JUnit Jupiter comes with many built-in conditional annotations for common cases. If a condition only depends on the operating system, a system property, or an environment variable, JUnit's annotations are usually the more direct choice.

| Need | Annotation to Use |
|---|---|
| Run only on a specific operating system | @EnabledOnOs, @DisabledOnOs |
| Run only when a system property has a certain value | @EnabledIfSystemProperty, @DisabledIfSystemProperty |
| Run only when an environment variable has a certain value | @EnabledIfEnvironmentVariable, @DisabledIfEnvironmentVariable |
| Condition needs SpEL or a property from Spring Environment | Spring @EnabledIf, @DisabledIf |
| Condition needs to read a bean in ApplicationContext | Spring @EnabledIf or @DisabledIf with loadContext = true |

For example, if a test only needs to run on Linux, JUnit provides a dedicated annotation:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;

class LinuxSpecificTest {
    @Test
    @EnabledOnOs(OS.LINUX)
    void usesLinuxSpecificFeature() {
        // ...
    }
}
~~~

If you only need to check the `CI` environment variable, you can use:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

class CiOnlyTest {
    @Test
    @EnabledIfEnvironmentVariable(
            named = "CI",
            matches = "true"
    )
    void runsInCi() {
        // ...
    }
}
~~~

Spring `@EnabledIf` is useful when a condition needs to combine multiple values, needs SpEL syntax, or must read properties/beans from the Spring context. For simple conditions that JUnit supports directly, JUnit's annotations usually make intent clearer and do not require Spring expression evaluation.

## 10. Distinguishing Test Execution Conditions from Bean Registration Conditions

Annotations with "If" or conditional semantics can appear at multiple layers, but they do not replace one another.

| Mechanism | Effect | Example |
|---|---|---|
| @EnabledIf / @DisabledIf | Decides whether a test class or method runs | Skip integration tests when a feature is not ready |
| @Profile | Selects beans by active profile | Select a fake gateway under the test profile |
| @Conditional | Decides whether a bean definition is registered | Register an adapter only when classpath or property matches |
| JUnit assumption | Aborts a running test when a runtime assumption fails | Skip a branch after the test inspects actual runtime state |

`@Profile` example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
class GatewayConfiguration {
    @Bean
    @Profile("test")
    PaymentGateway fakeGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("production")
    PaymentGateway realGateway() {
        return new RealPaymentGateway();
    }
}
~~~

Profiles decide which beans are created when the context starts. `@EnabledIf` decides which tests run. Both can be used in a test suite, but each annotation must perform its own role.

JUnit assumptions such as `Assumptions.assumeTrue()` are suitable when the condition is only known while the test method is executing, such as a quick check on a connected resource. Conversely, `@EnabledIf` fits conditions that can be evaluated before running the test method and can apply to an entire class.

## 11. Handling Errors During Condition Evaluation

Conditions should not be a place to hide configuration errors. If an expression cannot be resolved, a placeholder is missing, or SpEL syntax is invalid, condition evaluation can fail and JUnit reports an error instead of simply skipping the test.

Some common issues:

### Importing the Wrong Annotation

JUnit Jupiter and Spring have annotations with the same name. Verify imports are `org.springframework.test.context.junit.jupiter.EnabledIf` or `DisabledIf` if you want to use Spring expressions.

### Missing Property Placeholder

If you declare a property `tests.integration.enabled` but the environment does not provide it, Spring may fail to resolve the placeholder. You can declare the property in `@TestPropertySource`, configuration files, or command line; if the property is optional, provide a default `false` in the placeholder.

### SpEL Returning the Wrong Type

The condition must return `Boolean.TRUE` or the string `true` case-insensitively. An expression returning an arbitrary object or a different string will not make the condition true. Write an explicit boolean comparison:

~~~java
@EnabledIf(
        expression = "#{systemProperties['tests.external'] == 'true'}"
)
class ExternalTest {
}
~~~

### Referenced Bean Does Not Exist

If SpEL references `testCapabilities` but the configuration does not register that bean, the condition cannot evaluate successfully. Check configuration classes, component scanning, profiles, and `loadContext = true`.

### Loading the Context Unnecessarily

If a condition only reads a system property yet sets `loadContext = true`, Spring may initialize the entire context before skipping the test. Omit this flag if you do not need beans or configuration inside the context.

### Overly Complex Conditions

A long expression with multiple bean calls, system accesses, and logical branches will be hard to diagnose. Move complex logic into a bean or a clearly named property, and let the expression simply read one boolean value.

### Skipping Tests Instead of Reporting Environment Errors

If an integration test strictly requires a database or external service in the pipeline, a condition disabling the test when the dependency is absent can hide a CI configuration error. Only use skip conditions when not running is a valid, intentional state. If the dependency is mandatory, let the test start and fail clearly when the environment is missing it.

## 12. Process for Choosing the Right Condition

When deciding whether to use `@EnabledIf` or `@DisabledIf`, identify the data source and scope of the condition:

1. If the condition is a simple OS, system property, or environment variable check, consider JUnit's built-in conditional annotations.
2. If the condition needs SpEL, a property in Spring `Environment`, or a bean in the context, use Spring's annotations.
3. If the entire class shares the same environment requirement, place the condition on the class; if only one method depends on it, place it on the method.
4. If the expression needs a bean or context-specific property, set `loadContext = true`; if only reading system properties or environment variables, keep the default `false`.
5. Use `reason` to explain the condition to readers of test reports.
6. For optional properties, provide a default value or declare the property explicitly in test configuration.
7. If the same condition appears in multiple places, create a composed annotation whose name expresses its intent.
8. Do not use conditions to silently hide missing mandatory dependencies in CI or integration environments.
9. Use `@Profile` or `@Conditional` for bean selection; use `@EnabledIf` or `@DisabledIf` for running tests.
10. When condition evaluation fails, check imports, placeholders, SpEL, beans, and `loadContext` before changing business logic.

## 13. Key Principles to Keep in Mind

- Spring `@EnabledIf` enables a test when the expression evaluates to `Boolean.TRUE` or the string `true`; `@DisabledIf` skips a test when the expression evaluates to that value.
- Both annotations support SpEL, placeholders in Spring `Environment`, and text literals.
- Annotations can be placed at the class or method level; a class-level condition applies to the test methods inside the class.
- Import from `org.springframework.test.context.junit.jupiter` to avoid confusing them with JUnit's identically named annotations.
- `expression` and `value` are aliases; use `expression` when declaring `reason` or `loadContext`.
- `reason` helps explain the condition status in test reports.
- `loadContext` defaults to `false`; enable it only when the expression needs beans or configuration tied to the `ApplicationContext`.
- Prefer dedicated JUnit annotations for simple conditions such as OS, system properties, and environment variables.
- Distinguish test execution conditions from `@Profile` and `@Conditional`, which decide which beans are registered.
- Do not use conditions to silently turn a mandatory dependency into an optional one.
- Keep expressions short, with appropriate default values and clear reasons so the test suite remains easy to operate.

`@EnabledIf` and `@DisabledIf` add the ability to control tests based on Spring expressions and configuration. When you choose the right data source, place the condition at the right scope, and load the context only when needed, they help a test suite support multiple environments while clearly showing why a test ran or was skipped.

## References

- [Spring Framework Reference — Spring JUnit Jupiter Testing Annotations](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-junit-jupiter.html)
- [Spring Framework Javadoc 6.2 — EnabledIf](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/test/context/junit/jupiter/EnabledIf.html)
- [Spring Framework Javadoc 6.0 — DisabledIf](https://docs.spring.io/spring-framework/docs/6.0.19/javadoc-api/org/springframework/test/context/junit/jupiter/DisabledIf.html)
- [Spring Framework Reference — Meta-Annotation Support for Testing](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-meta.html)
