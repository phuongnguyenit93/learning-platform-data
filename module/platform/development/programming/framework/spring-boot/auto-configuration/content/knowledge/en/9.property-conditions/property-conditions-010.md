# @ConditionalOnExpression and the Risk of Bean References Causing Premature Initialization

## 1. Objectives and Scope

`@ConditionalOnExpression` is a Spring Boot Auto Configuration conditional annotation. It allows registering a configuration class or a `@Bean` method **only when a Spring Expression Language (SpEL) expression returns `true`**.

The key issue in this lesson is **how expressions are written**: conditions that read properties from `Environment` normally do not touch bean instances, whereas an expression like `@clientSettings.enabled` **references a Spring bean**. Resolving this bean can cause the bean to be initialized prematurely during `ApplicationContext` refresh, before normal post-processing steps are applied. In particular, `@ConfigurationProperties` binding may not have been fully applied, leaving the bean's state incomplete and causing the condition to draw the wrong conclusion.

After this lesson, learners should understand: basic SpEL syntax; the difference between `${...}` placeholders and `@beanName` bean references; the premature initialization mechanism; before-and-after examples; how to replace them with `@ConditionalOnProperty`/`Condition`; and how to test and diagnose.

## 2. How `@ConditionalOnExpression` Works

The annotation belongs to package `org.springframework.boot.autoconfigure.condition` and uses the `value` attribute containing a SpEL expression:

```java
@ConditionalOnExpression("${demo.enabled:false}")
```

In this example, Spring reads property `demo.enabled` from `Environment`, substitutes the placeholder, and evaluates the expression. If the property does not exist, it uses `false` from the default value after the colon. The final expression result must have a boolean meaning: `true` for the condition to match, `false` for no match.

Logical and arithmetic expressions can be combined:

```java
@ConditionalOnExpression(
    "${demo.enabled:false} and ${demo.pool-size:0} >= 8"
)
```

Example `application.yml`:

```yaml
demo:
  enabled: true
  pool-size: 12
```

The condition above matches because both clauses are true. Variants:

| `demo.enabled` | `demo.pool-size` | Condition matches? |
| --- | --- | --- |
| Missing | Missing | No, defaults to `false` and `0` |
| `false` | `12` | No |
| `true` | `4` | No |
| `true` | `8` | Yes |
| `true` | `12` | Yes |

Common SpEL operators include `and`/`or` or `&&`/`||`, `!`, `==`, `!=`, `>`, `>=`, `<`, `<=`. Use parentheses when combining multiple conditions so readers clearly see precedence order. If property substitution produces an invalid expression (for example, putting an alphabetic string where a number is expected), condition evaluation may fail at startup.

The annotation can be placed at two levels:

- **On a `@Configuration` or `@AutoConfiguration` class:** the condition result affects registering that configuration and its `@Bean` methods.
- **On a `@Bean` method:** only the corresponding method is controlled by the condition.

By default the `value` attribute is `"true"`, though an annotation without an expression usually offers no feature-control benefit. This condition **is evaluated when Spring processes configurations and registers beans**, not as a callback re-running whenever configuration or runtime data changes.

## 3. Difference Between Placeholders and Bean References

| Syntax | Target accessed | Impact on bean lifecycle |
| --- | --- | --- |
| `${demo.enabled:false}` | Value in `Environment`, with default `false` | The placeholder itself does not require creating a bean |
| `@clientSettings` | Bean named `clientSettings` in BeanFactory | Can trigger fetching the bean instance and prematurely initialize it |
| `@clientSettings.enabled` | Bean instance then reads property `enabled` | Risks premature initialization and reading incomplete state |
| `@clientSettings.isEnabled()` | Bean instance then calls method | Carries the risks above, plus method side effects |

The `@clientSettings` notation **inside a SpEL string** is a *bean reference*. It is completely different from the `@ConditionalOnExpression` Java annotation syntax. If a bean name contains dots, SpEL uses syntax like `@'some.bean'`. However, knowing this syntax **does not mean you should use bean references inside startup conditions**.

### Core Question

Does the expression `@ConditionalOnExpression("@clientSettings.enabled")` really just "read a boolean"?

**No.** Before reading the boolean, SpEL must obtain the `clientSettings` object. If the bean only has a definition and has not been instantiated yet, resolving the reference can cause `BeanFactory` to **instantiate that object immediately**, at a time when the container is still building configurations. The danger lies not in the boolean operator, but in fetching the instance.

## 4. Chain of Events Leading to Premature Initialization

Suppose an auto-configuration contains the method:

```java
@Bean
@ConditionalOnExpression("@clientSettings.enabled")
FeatureClient featureClient() {
    return new FeatureClient();
}
```

This is an **illustrative snippet**, assuming a bean definition named `clientSettings` is already registered in another configuration; `FeatureClient` is an application class. This snippet alone is not a standalone runnable Java file.

A possible sequence of events:

1. Spring starts `refresh()`, reading configurations and bean definitions.
2. During condition evaluation for `featureClient()`, `OnExpressionCondition` requests SpEL evaluation.
3. SpEL encounters `@clientSettings`. The bean resolver turns that into looking up/fetching the bean by name from `BeanFactory`.
4. Because the bean has no instance yet, `BeanFactory` may **instantiate the bean right while the condition is being processed**.
5. At this overly early point, necessary `BeanPostProcessor`s may not yet be registered/applied completely. The instance therefore risks skipping steps such as configuration binding, validation, proxying, or other processing.
6. The condition reads the instance state and decides whether to register `FeatureClient`. The result may differ from expectations based on configuration values.

**Spring Boot officially warns**: referencing beans in `@ConditionalOnExpression` can cause the bean to be initialized very early during context refresh; as a result, the bean may not be eligible for post-processing such as `@ConfigurationProperties` binding, and its state may be incomplete.

Things to distinguish:

- **Bean definition registered:** Spring knows *how* to create the bean.
- **Bean instantiated:** an instance exists.
- **Bean post-processed:** required lifecycle steps have been applied.

These three states are not synonymous. Evaluating a registration condition that only needs metadata/properties **should not force** an immediate transition to instance creation. If a bean is fetched too early, Spring makes no promise to "backfill" all missing post-processing afterward.

Not every expression containing `@bean` instantiates the bean in all situations: if the bean already has an instance, it need not be created again; if a SpEL branch is skipped due to short-circuiting, the reference may not execute. However, relying on these accidental circumstances to treat bean references as safe makes configuration dependent on startup order.

## 5. Failure Example: `@ConfigurationProperties` Read Before Binding

Consider an application-defined configuration class:

```java
package example.demo;

public final class ClientSettings {
    private boolean enabled;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Another configuration registers it as a bean bound from `application.yml`:

```java
@Bean
@ConfigurationProperties(prefix = "demo.client")
ClientSettings clientSettings() {
    return new ClientSettings();
}
```

Desired configuration values:

```yaml
demo:
  client:
    enabled: true
```

Normally, Spring creates `ClientSettings` and applies the configuration mechanism so the `enabled` field receives `true`. However, if an auto-configuration has the condition:

```java
@ConditionalOnExpression("@clientSettings.enabled")
```

then the `clientSettings` bean may be created **before binding post-processing** and still hold the Java default value `false`. Then the condition may fail to match even though property `demo.client.enabled=true`. Even if a specific startup run happens to give the right result, the design depends unnecessarily on bean creation timing.

**This is a risk-explaining scenario**, not a claim that every Spring Boot application observes the exact `false` result across all versions and configurations. Concrete outcomes also depend on the registration order of beans and BeanPostProcessors, yet the risk mechanism is confirmed by Spring Boot documentation.

Other errors that can accompany accessing beans in SpEL:

- Bean not yet registered: the resolver cannot find the bean name and expression evaluation can cause context startup to fail.
- Getters/methods in the expression perform I/O, call services, or initialize dependent objects earlier than intended.
- Bean is initialized before proxy mechanisms like AOP or before another post-processor, leading to unexpected behavior.
- A circular dependency cycle may surface during condition evaluation instead of normal bean initialization.
- Conditions relying on mutable bean data make bootstrap behavior unpredictable and hard to reproduce when auto-configuration order changes.

## 6. Safe Alternatives and Intended Uses

### 6.1. Simply toggling a feature: `@ConditionalOnProperty`

```java
@Bean
@ConditionalOnProperty(
    prefix = "demo.client",
    name = "enabled",
    havingValue = "true"
)
FeatureClient featureClient() {
    return new FeatureClient();
}
```

This reads only the **property** `demo.client.enabled`, without creating `ClientSettings`. With `havingValue="true"`, the condition matches when the corresponding property value is `true`. `matchIfMissing` defaults to `false`, so if the property is absent, the condition does not match. This is usually the first choice for an on/off flag.

### 6.2. Combining booleans and numeric thresholds: SpEL using placeholders only

```java
@Bean
@ConditionalOnExpression(
    "${demo.client.enabled:false} and ${demo.client.pool-size:0} >= 8"
)
FeatureClient featureClient() {
    return new FeatureClient();
}
```

Still uses SpEL, but relies solely on properties in `Environment`; **does not use `@clientSettings`**. Tests should cover missing properties, wrong data types, and the exact boundary value `8`.

### 6.3. Complex rules: writing a `Condition` that only reads `Environment`

Create file `src/main/java/example/conditions/PoolCapacityCondition.java`:

```java
package example.conditions;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class PoolCapacityCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        boolean enabled = context.getEnvironment()
                .getProperty("demo.client.enabled", Boolean.class, false);
        int poolSize = context.getEnvironment()
                .getProperty("demo.client.pool-size", Integer.class, 0);
        return enabled && poolSize >= 8;
    }
}
```

Use in a `@Configuration` class (snippet, with appropriate imports and application types):

```java
@Bean
@Conditional(PoolCapacityCondition.class)
FeatureClient featureClient() {
    return new FeatureClient();
}
```

Here `matches` only retrieves data from `Environment`, **without accessing bean instances**. If a numeric property cannot be converted to `Integer`, the application may report a conversion error during evaluation; for clearer configuration messages, design dedicated validation for configuration data. `PoolCapacityCondition` should not call networks, databases, or instantiate dependent beans itself, because it also runs during the configuration phase.

### 6.4. Checking whether a bean exists: `@ConditionalOnBean`

```java
@Bean
@ConditionalOnBean(ClientSettings.class)
FeatureClient featureClient() {
    return new FeatureClient();
}
```

This checks bean presence by type among already-processed bean definitions, **without reading the instance's `enabled` value**. Thus it can only replace the requirement "a `ClientSettings` bean exists", not "the client is enabled". Conditions based on bean definitions also depend on configuration ordering; place them in auto-configuration and test ordering if configurations depend on each other.

### Quick Selection Table

| Purpose | Appropriate tool |
| --- | --- |
| Enable when `demo.enabled=true` | `@ConditionalOnProperty` |
| Enable when properties compare via a simple expression | `@ConditionalOnExpression` with `${...}` |
| Complex configuration rules requiring explicit data checks | `Condition` reading only `Environment` |
| Enable when a bean of a certain type/name exists | `@ConditionalOnBean` |
| Enable when a bean of a certain type/name is missing | `@ConditionalOnMissingBean` |
| Continuous toggling based on a bean's running state | Runtime logic; startup registration conditions are not the right tool |

## 7. Runnable Test Example with Java 17+ and Spring Boot 3.3

This is a complete test file demonstrating safe property-only `@ConditionalOnExpression` and comparing it with `@ConditionalOnProperty`. There is no `@beanName` in the expression.

Create `src/test/java/example/conditions/ExpressionConditionTests.java` in a Spring Boot 3.3.x project with `spring-boot-starter-test` (JUnit Jupiter and AssertJ) and JUnit Platform enabled:

```java
package example.conditions;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ExpressionConditionTests {

    static final class FastPathMarker {}
    static final class EnabledFlagMarker {}

    @AutoConfiguration
    static class DemoAutoConfiguration {

        @Bean
        @ConditionalOnExpression(
                "${demo.fast-mode:false} and ${demo.min-size:0} >= 10"
        )
        FastPathMarker fastPathMarker() {
            return new FastPathMarker();
        }

        @Bean
        @ConditionalOnProperty(
                prefix = "demo",
                name = "fast-mode",
                havingValue = "true"
        )
        EnabledFlagMarker enabledFlagMarker() {
            return new EnabledFlagMarker();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(DemoAutoConfiguration.class));

    @Test
    void noPropertiesCreatesNeitherBean() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(FastPathMarker.class);
            assertThat(context).doesNotHaveBean(EnabledFlagMarker.class);
        });
    }

    @Test
    void disabledFeatureCreatesNeitherBean() {
        runner.withPropertyValues(
                "demo.fast-mode=false",
                "demo.min-size=20"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FastPathMarker.class);
            assertThat(context).doesNotHaveBean(EnabledFlagMarker.class);
        });
    }

    @Test
    void enabledButSmallPoolCreatesOnlyFlagBean() {
        runner.withPropertyValues(
                "demo.fast-mode=true",
                "demo.min-size=4"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FastPathMarker.class);
            assertThat(context).hasSingleBean(EnabledFlagMarker.class);
        });
    }

    @Test
    void enabledAndLargePoolCreatesBothBeans() {
        runner.withPropertyValues(
                "demo.fast-mode=true",
                "demo.min-size=12"
        ).run(context -> {
            assertThat(context).hasSingleBean(FastPathMarker.class);
            assertThat(context).hasSingleBean(EnabledFlagMarker.class);
        });
    }
}
```

Command to run when the project has Gradle wrapper and `test` uses JUnit Platform:

```bash
./gradlew test --tests example.conditions.ExpressionConditionTests
```

In a Maven project configured with JUnit 5/Surefire, use `./mvnw -Dtest=ExpressionConditionTests test`. The expected result is **four tests PASS**; there is no single fixed stdout string across all build configurations.

| Case | `FastPathMarker` — SpEL | `EnabledFlagMarker` — property |
| --- | --- | --- |
| No properties provided | Absent | Absent |
| `fast-mode=false`, `min-size=20` | Absent | Absent |
| `fast-mode=true`, `min-size=4` | Absent | Present |
| `fast-mode=true`, `min-size=12` | Present | Present |

The tests confirm condition semantics and default values. They **do not assume** that every example with `@beanName` produces the exact same failure across all configurations. To prove a specific bean is prematurely initialized in a project, additionally observe constructor timing, binding, and corresponding BeanPostProcessors in isolated contexts.

## 8. Observing and Diagnosing in Real Projects

1. **Inspect SpEL strings:** search for `@beanName`, `@beanName.property`, getter calls, or method calls. Those are signs that the condition depends on a bean instance.
2. **Inspect underlying properties:** use exact keys from `Environment`, check defaults inside `${...}`, boolean/numeric types, and missing-key cases. Do not confuse a property sharing the same name with a bean attribute.
3. **Enable condition reporting:** run the Spring Boot application with `--debug` to view `ConditionEvaluationReport`, or attach a listener to `ApplicationContextRunner` in tests. The report explains why conditions matched/did not match; it does not necessarily prove the order of all post-processing on its own.
4. **Observe lifecycle:** log timestamps of bean creation, `@ConfigurationProperties` binding, and `BeanPostProcessor` execution if you suspect an instance is fetched while a condition is running.
5. **Compare before and after:** replace the bean-referencing expression with an equivalent property condition. Verify bean registration outcomes and bound bean state.
6. **Cover edge branches:** missing property, `true`, `false`, threshold exactly equal to the boundary, invalid data types, and bean-definition-only conditions.

In tests you can use `ConditionEvaluationReportLoggingListener` as in the snippet below (add imports and place in the runner setup chain):

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

// Example inside ApplicationContextRunner configuration:
.withInitializer(
    ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
)
```

This snippet is illustrative rather than a standalone Java file. `ApplicationContextRunner` builds a separate context for each case, preventing beans created in an earlier test from affecting subsequent cases.

## 9. Common Mistakes and Self-Check Exercises

### Common Mistakes

- **Assuming SpEL only "reads a property":** `@service.enabled` must first resolve the `service` bean, which can trigger initialization.
- **Confusing a registered bean with a ready bean:** having a bean definition does not mean binding/proxying/validation stages have finished.
- **Using `@ConditionalOnExpression` for a simple boolean:** prefer `@ConditionalOnProperty`, especially when you want easy explanation and testing.
- **Thinking `@ConditionalOnBean` checks bean properties:** it only checks presence via bean metadata that it can observe.
- **Using runtime state to alter bean structure:** conditions are evaluated during registration only; they do not re-register beans after the app is running.
- **Not handling defaults and numeric types:** missing placeholders, invalid numbers, or type-mismatched comparisons can make condition logic deviate from intent.
- **Assuming Spring will automatically backfill post-processing after early initialization:** Spring Boot warns that prematurely initialized beans may not be eligible for post-processing as expected.

### Self-Check

1. Does the expression `${demo.enabled:false}` require a `demo` bean? **No.** It reads the property directly from `Environment`.
2. Why can `@ConditionalOnExpression("@clientSettings.enabled")` evaluate to `false` even when `demo.client.enabled=true`? **Because the bean may be instantiated and read before the `@ConfigurationProperties` binding step.**
3. Need a condition that is true when `demo.enabled=true`. Clean and safe choice? **`@ConditionalOnProperty(prefix="demo", name="enabled", havingValue="true")`.**
4. Need to check `demo.pool-size >= 8` without ever fetching a bean instance. How? **Use SpEL with configuration placeholders only or a `Condition` reading `Environment`.**
5. After the context has started, does changing `demo.enabled` from false to true automatically create the previously skipped bean? **No.** A separate runtime mechanism must be designed if dynamic toggling is needed.

## Official Reference Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, SpEL Expression Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): explains the warning about very early bean initialization, post-processing, and `@ConfigurationProperties` binding.
- [Spring Framework — SpEL Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html): `@beanName` syntax and how the bean resolver references beans.
- [Spring Boot — ConditionalOnExpression API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnExpression.html): annotation semantics and default value of `value`.
