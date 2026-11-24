# Testing Match, No-Match, and Diagnostic Messages of a Custom Condition

## 1. Objective: Verify Both the Decision and the Reason

A custom Spring Boot condition decides whether a configuration or bean is registered. A test that only checks whether the bean appears when the condition is true is not enough. The condition must also handle failing cases properly and explain why it did not match.

For example, the Northstar library has an audit feature enabled via a property:

~~~properties
northstar.audit.enabled=true
~~~

Desired rules:

- Property is `true`: condition matches, audit bean is created.
- Property is `false`: condition does not match, bean is not created.
- Property is undeclared: condition does not match and the message clearly states the property is missing.
- Property has an invalid value such as `yes`: condition does not match and the message states the unsupported value.

We need to verify two independent outputs:

1. **Condition outcome:** match or no-match, reflected by whether the bean is registered and `ConditionOutcome.isMatch()`.
2. **Diagnostic message:** the specific reason recorded in the condition evaluation report, reflected by `ConditionOutcome.getMessage()`.

Testing both avoids situations where a condition returns the right boolean yet produces a confusing report, or where the message says one thing while the bean is registered along another branch.

## 2. `Condition` and `SpringBootCondition`

Spring Framework defines the `org.springframework.context.annotation.Condition` interface. A typical implementation writes the method:

~~~java
boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata)
~~~

The method only returns `true` or `false`. It has no standard return type to attach a match/no-match reason.

Spring Boot provides the base class `org.springframework.boot.autoconfigure.condition.SpringBootCondition`. Instead of writing `matches` yourself, subclasses implement:

~~~java
ConditionOutcome getMatchOutcome(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
)
~~~

`ConditionOutcome` holds the match or no-match status along with a message explaining the result. The `SpringBootCondition` base class handles orchestration: calling `getMatchOutcome`, logging the outcome, and recording it in `ConditionEvaluationReport`. Therefore, custom conditions should return `ConditionOutcome.match(...)` or `ConditionOutcome.noMatch(...)` rather than logging or writing reports manually.

| Component | Responsibility |
|---|---|
| `ConditionContext` | Provides Environment, BeanFactory, ClassLoader, and ResourceLoader during evaluation |
| `AnnotatedTypeMetadata` | Provides metadata of the class or method currently being inspected |
| `SpringBootCondition` | Coordinates evaluation, logging, and outcome recording |
| `ConditionOutcome` | Holds match/no-match result and message |
| `ConditionMessage` | Builds consistent messages for condition outcomes |
| `ConditionEvaluationReport` | Stores results grouped by source class or bean method |

Only write a custom condition when built-in conditions such as `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean`, or `@ConditionalOnResource` cannot express the required rule. Custom conditions add code that must be tested and maintained.

## 3. Creating an Annotation for the Custom Condition

Example creating the `@ConditionalOnAuditEnabled` annotation:

~~~java
package com.example.audit.autoconfigure;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnAuditEnabledCondition.class)
public @interface ConditionalOnAuditEnabled {
}
~~~

The annotation can be placed on a configuration class or a `@Bean` method. In this lesson, we place it on the auto-configuration so tests can easily observe a single outcome for the whole configuration.

Condition extending `SpringBootCondition`:

~~~java
package com.example.audit.autoconfigure;

import org.springframework.boot.autoconfigure.condition.ConditionMessage;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class OnAuditEnabledCondition extends SpringBootCondition {

    private static final String PROPERTY = "northstar.audit.enabled";

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String configuredValue =
                context.getEnvironment().getProperty(PROPERTY);

        if (configuredValue == null) {
            return ConditionOutcome.noMatch(
                    ConditionMessage.of(
                            "property '" + PROPERTY + "' is missing; expected 'true'"
                    )
            );
        }

        String value = configuredValue.trim();

        if ("true".equalsIgnoreCase(value)) {
            return ConditionOutcome.match(
                    ConditionMessage.of(
                            "property '" + PROPERTY + "' is true"
                    )
            );
        }

        if ("false".equalsIgnoreCase(value)) {
            return ConditionOutcome.noMatch(
                    ConditionMessage.of(
                            "property '" + PROPERTY + "' is false"
                    )
            );
        }

        return ConditionOutcome.noMatch(
                ConditionMessage.of(
                        "property '" + PROPERTY + "' has unsupported value '"
                                + configuredValue + "'; expected 'true' or 'false'"
                )
        );
    }
}
~~~

The branches are separated clearly:

- `null` means the property does not exist.
- Case-insensitive `true` means the feature is enabled.
- `false` means the feature is disabled.
- Any other value is an invalid configuration.

Do not rely solely on `Boolean.parseBoolean(value)` if you need to diagnose invalid values. That method returns `false` for every string other than `true`, so `false`, empty strings, and `yes` would collapse into the same branch. Distinguishing these states makes messages much more helpful when configuring an application.

`ConditionMessage.of(...)` creates a message you can pass to `ConditionOutcome.match(...)` or `ConditionOutcome.noMatch(...)`. For more complex messages, Spring Boot also provides the `ConditionMessage.forCondition(...)` builder.

## 4. Using the Condition in Auto-Configuration

Create the bean only when the condition matches:

~~~java
package com.example.audit.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnAuditEnabled
public class AuditFeatureAutoConfiguration {

    @Bean
    AuditFeature auditFeature() {
        return new AuditFeature();
    }
}
~~~

Sample bean type:

~~~java
package com.example.audit.autoconfigure;

public final class AuditFeature {
}
~~~

When `northstar.audit.enabled=true`, Spring registers `AuditFeature`. When the property is missing, `false`, or holds an unsupported value, the configuration does not match and the bean is not registered.

In a real library, add `AuditFeatureAutoConfiguration` to the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

This file is required so applications can discover the auto-configuration from a packaged starter. Test examples using `ApplicationContextRunner` can register the class directly, so the test runner itself does not prove the imports file was packaged properly. If you need to verify artifact discovery, add a separate consumer smoke test.


## 5. Testing Four Scenarios with `ApplicationContextRunner`

`ApplicationContextRunner` creates a fresh application context for each test run. It lets you supply specific auto-configurations, properties, user configurations, and classloaders. This is the right tool for testing conditions without starting the entire application.

The tests below verify:

1. Property is `true`: condition matches and bean appears.
2. Property is `false`: condition does not match and bean is absent.
3. Property is missing: condition does not match with a missing-configuration reason.
4. Property is malformed: condition does not match and reports an unsupported value.

File `src/test/java/com/example/audit/autoconfigure/AuditFeatureConditionTests.java`:

~~~java
package com.example.audit.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AuditFeatureConditionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AuditFeatureAutoConfiguration.class
                            )
                    );

    @Test
    void matchesWhenPropertyIsTrue() {
        runner.withPropertyValues("northstar.audit.enabled=true")
                .run(context -> {
                    assertThat(context.getBeansOfType(AuditFeature.class))
                            .hasSize(1);

                    ConditionOutcome outcome = conditionOutcome(context);

                    assertThat(outcome.isMatch()).isTrue();
                    assertThat(outcome.getMessage())
                            .contains("northstar.audit.enabled")
                            .contains("is true");
                });
    }

    @Test
    void doesNotMatchWhenPropertyIsFalse() {
        runner.withPropertyValues("northstar.audit.enabled=false")
                .run(context -> {
                    assertThat(context.getBeansOfType(AuditFeature.class))
                            .isEmpty();

                    ConditionOutcome outcome = conditionOutcome(context);

                    assertThat(outcome.isMatch()).isFalse();
                    assertThat(outcome.getMessage())
                            .contains("northstar.audit.enabled")
                            .contains("is false");
                });
    }

    @Test
    void doesNotMatchWhenPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context.getBeansOfType(AuditFeature.class))
                    .isEmpty();

            ConditionOutcome outcome = conditionOutcome(context);

            assertThat(outcome.isMatch()).isFalse();
            assertThat(outcome.getMessage())
                    .contains("northstar.audit.enabled")
                    .contains("is missing");
        });
    }

    @Test
    void reportsUnsupportedPropertyValue() {
        runner.withPropertyValues("northstar.audit.enabled=yes")
                .run(context -> {
                    assertThat(context.getBeansOfType(AuditFeature.class))
                            .isEmpty();

                    ConditionOutcome outcome = conditionOutcome(context);

                    assertThat(outcome.isMatch()).isFalse();
                    assertThat(outcome.getMessage())
                            .contains("unsupported value 'yes'")
                            .contains("expected 'true' or 'false'");
                });
    }

    private ConditionOutcome conditionOutcome(
            AssertableApplicationContext context) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        var source = report.getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry -> entry.getKey().equals(
                        AuditFeatureAutoConfiguration.class.getName()
                ))
                .findFirst()
                .orElseThrow(() ->
                        new AssertionError(
                                "Condition report entry for AuditFeatureAutoConfiguration was not found"
                        )
                );

        return source.getValue().iterator().next().getOutcome();
    }
}
~~~

### 5.1. Why Do Tests Read `ConditionEvaluationReport`?

Merely checking whether a bean exists does not prove the condition took the intended branch. For instance, the bean could be absent because another condition failed to match or because the configuration was not imported.

`ConditionEvaluationReport` stores results keyed by the source class name or bean method. The test retrieves the `AuditFeatureAutoConfiguration` entry and reads `ConditionOutcome`:

- `isMatch()` verifies the logical outcome.
- `getMessage()` verifies the reason returned by the condition.

The `conditionOutcome` helper keeps report extraction in one place so each test can focus on the scenario under test.

If the condition is placed on a `@Bean` method instead of a configuration class, the source in the report may be the class name followed by `#beanMethodName`. In that case, filter by the key matching the bean method rather than defaulting to the class name.

### 5.2. Expected Test Matrix

| Property | Bean `AuditFeature` | `isMatch()` | Message content |
|---|---|---|---|
| `true` | Present | `true` | Property is true |
| `false` | Absent | `false` | Property is false |
| Undeclared | Absent | `false` | Property is missing |
| `yes` | Absent | `false` | Unsupported value; expected true or false |

A good test simultaneously verifies all three layers: input, bean result, and diagnostics. That way, when refactoring condition logic, tests catch both behavioral regressions and missing or broken messages.


## 6. Printing the Condition Report in Tests

When you need to see all results rather than just one condition, use `ConditionEvaluationReportLoggingListener`. The listener is an `ApplicationContextInitializer` that writes the condition evaluation report to logs.

Example of an isolated run:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(AuditFeatureAutoConfiguration.class)
        )
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
        )
        .withPropertyValues("northstar.audit.enabled=false")
        .run(context -> {
            assertThat(context.getBeansOfType(AuditFeature.class)).isEmpty();
        });
~~~

`forLogLevel(LogLevel.INFO)` requests the report to be logged at INFO level. By default, the listener logs at DEBUG. Create a new listener for each context; the Javadoc notes that the listener is not designed to be shared across multiple application context instances.

Choose between the two approaches by purpose:

- `ConditionEvaluationReport` in tests: read a specific entry and assert both outcome and message.
- `ConditionEvaluationReportLoggingListener`: print the entire report to observe related conditions during a test run.

There is no need to assert the full log text if the goal is testing condition logic. Overall log formatting can vary between versions; tests should assert `ConditionOutcome` and meaningful message substrings.

## 7. Diagnosing in a Running Application

When an auto-configured bean does not appear in an application, you can enable the condition report at startup using:

~~~bash
java -jar app.jar --debug
~~~

Or:

~~~bash
java -Ddebug=true -jar app.jar
~~~

The report helps identify:

- Which auto-configurations matched.
- Which auto-configurations did not match.
- Which condition failed.
- The reason recorded by the condition.
- Which configurations were excluded.

If the application includes Spring Boot Actuator, the `/actuator/conditions` endpoint provides the condition evaluation report as structured data. The endpoint must be enabled and exposed according to the application's Actuator configuration; protect the endpoint with appropriate security controls and never expose internal reports publicly on the Internet.

When reading the report, locate the exact class or bean method owning the bean under inspection. A bean can be absent for multiple reasons: a class missing from the classpath, an incorrect property, an existing replacement bean, or an unmet dependent condition. Reading each condition's message helps distinguish these cases.

## 8. Writing Helpful Diagnostic Messages

A condition message should answer three questions:

1. **What was checked?** For example, property `northstar.audit.enabled`.
2. **What was observed?** The property is missing, `false`, or holds `yes`.
3. **What does the condition need to match?** The value must be `true`.

Examples:

| Case | Appropriate message |
|---|---|
| Match | Property `northstar.audit.enabled` is true |
| No-match | Property `northstar.audit.enabled` is false |
| Missing | Property `northstar.audit.enabled` is missing; expected `true` |
| Invalid | Property has unsupported value `yes`; expected `true` or `false` |

A few guidelines:

- State the reason clearly; avoid generic phrases like `condition failed` or `feature disabled`.
- Use the exact same property or class name across all branches so readers can locate the source configuration.
- Distinguish missing configuration, disabled configuration, and invalid configuration.
- Never put passwords, tokens, secrets, connection strings containing credentials, or sensitive data into messages.
- Do not depend on the entire message sentence in tests when a few keywords suffice to confirm the cause.
- Never use exceptions to represent a normal no-match case. An unmet condition is typically a valid result, not a startup error.

`ConditionMessage` standardizes message creation. `ConditionOutcome.match` and `ConditionOutcome.noMatch` express outcomes clearly. Build the message inside the corresponding branch; never return a single success message for every branch while only flipping the boolean.

## 9. Principles for Implementing Custom Conditions

Conditions are evaluated while Spring processes configuration. Therefore, implementations should be fast, deterministic, and side-effect-free.

Do:

- Read required `Environment`, metadata, classpath, or resources.
- Return the same result for the same inputs.
- Provide clear reasons for both match and no-match branches.
- Use built-in conditions when they already express the rule properly.
- Test classpath, property, and bean conditions case by case.

Avoid:

- Instantiating beans or calling `context.getBean(...)` to decide a condition.
- Opening database connections, making HTTP calls, or querying remote services while evaluating a condition.
- Writing files, mutating properties, modifying global state, or performing operations that cannot be safely repeated.
- Logging manually and returning a boolean without providing `ConditionOutcome`.
- Catching every exception and turning it into a no-match without preserving the diagnostic cause.
- Including secret configuration values in messages.

If a condition needs to know whether another bean exists, prefer built-in annotations such as `@ConditionalOnBean` or `@ConditionalOnMissingBean`. If you need to combine conditions, look at `AllNestedConditions`, `AnyNestedCondition`, and `NoneNestedConditions` before writing complex boolean logic yourself.


## 10. Dependencies and Test Run Commands

The examples use Java 17+, Spring Boot 3.3.x, JUnit 5, and AssertJ. With Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Run the test class individually with Gradle:

~~~bash
./gradlew test --tests com.example.audit.autoconfigure.AuditFeatureConditionTests
~~~

Or Maven:

~~~bash
mvn -Dtest=AuditFeatureConditionTests test
~~~

The test suite has four cases. The expected result is four passing tests: one match branch and three no-match branches. This is the expected outcome from the example, not a log from an actual execution.

## 11. Common Mistakes

1. **Checking only whether the bean exists.** Bean absence could be caused by a different condition. Check `ConditionOutcome` in the report as well.
2. **Testing only the match branch.** Add tests for false, missing, and invalid properties so no-match branches are neither wrong nor missing messages.
3. **Using `Boolean.parseBoolean` and lumping all invalid values into false.** When invalid configuration must be diagnosed, distinguish false, missing, and invalid values.
4. **Implementing Spring `Condition` directly yet expecting automatic messages.** `Condition.matches` only returns a boolean. Extend `SpringBootCondition` and return `ConditionOutcome` to use Boot's reporting mechanism.
5. **Overriding `matches` in a subclass of `SpringBootCondition`.** That method is final; implement `getMatchOutcome`.
6. **Logging messages manually inside a condition.** This can duplicate logs and omit the reason from the condition report. Return messages via `ConditionOutcome`.
7. **Conditions with side effects.** Never call HTTP, query databases, or instantiate beans while evaluating conditions.
8. **Not distinguishing class-level and bean-method-level conditions.** Source keys in the report can be the class name or the class name plus `#beanMethod`. Retrieve the exact source.
9. **Asserting the entire log string.** Overall log formatting can change. Assert `isMatch()` and stable message substrings.
10. **Putting sensitive data in messages.** Reports can appear in logs or Actuator endpoints. Record only configuration names and safe reasons.
11. **Using exceptions for normal no-matches.** An unmet condition is a valid outcome; throw an exception only when the application truly cannot continue.
12. **Ignoring built-in conditions.** If `@ConditionalOnProperty` or another built-in condition already expresses the requirement, use it to reduce custom code to maintain.

## 12. Workflow for Testing a Custom Condition

1. Write the rule as a clear sentence: which inputs cause the condition to match and which cause no-match.
2. List all input states: valid, false, missing, and invalid; add classpath or bean cases if the condition checks them.
3. Implement the condition with `SpringBootCondition` and return `ConditionOutcome` for every branch.
4. Build messages clearly stating the checked data and the reason for the outcome.
5. Use `ApplicationContextRunner` to load the auto-configuration and vary each input per test case.
6. Assert that the bean is created or not created.
7. Read `ConditionEvaluationReport` to assert `isMatch()` and the message for the exact source.
8. Add a test logging the report via `ConditionEvaluationReportLoggingListener` when observing all conditions is helpful.
9. If the condition depends on the classpath, use `FilteredClassLoader` to test a missing library.
10. Run tests in the project against the actual Spring Boot version and inspect the report when a branch produces an unexpected result.

## 13. Takeaways

- Custom conditions should extend `SpringBootCondition` when results need diagnostic messages.
- Implement `getMatchOutcome`; do not override `matches`.
- Use `ConditionOutcome.match` and `ConditionOutcome.noMatch` to represent the two branches.
- `ConditionMessage` builds consistent messages and `ConditionEvaluationReport` records outcomes by class or bean method.
- `ApplicationContextRunner` lets you test each combination of properties, beans, and classpath in a small context.
- Verify bean behavior, `isMatch()`, and the message—do not look only at whether the context starts.
- Distinguish false properties, missing properties, and malformed values when they carry different diagnostic meanings.
- Use `ConditionEvaluationReportLoggingListener` in tests, `--debug` at application startup, or the Actuator conditions endpoint to investigate.
- Conditions should be fast, deterministic, side-effect-free, and never log secrets.

### Official Spring Boot 3.3 Documentation

- `SpringBootCondition` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html
- `ConditionOutcome` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html
- `ConditionMessage` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.html
- `ConditionEvaluationReport` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- `ConditionEvaluationReportLoggingListener` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html
- Creating Your Own Auto-configuration — testing auto-configuration and condition report: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Testing Spring Boot Applications — test support and ApplicationContextRunner: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Testing — Spring Boot's test support modules: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
