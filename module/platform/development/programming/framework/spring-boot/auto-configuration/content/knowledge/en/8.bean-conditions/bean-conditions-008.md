# Spring Boot `@ConditionalOnMissingBean`: Using `ignored` and `ignoredType` to Exclude Bean Types from Missing-Bean Checks

## 1. The Problem to Solve

Suppose an application has a `MessageSender` interface with two groups of implementations:

- `HealthCheckSender` is a bean for technical checks or monitoring. It also implements `MessageSender`, but **must not be treated as a business choice**.
- `DefaultSender` is the default bean provided by auto-configuration when the application does not yet have a business `MessageSender`.
- The application can also register its own `BusinessSender`; in that case, the default configuration must back off.

If you only use `@ConditionalOnMissingBean(MessageSender.class)`, the presence of `HealthCheckSender` makes Spring Boot consider a `MessageSender` **already present** and skip creating `DefaultSender`. That is the use case for `ignored` or `ignoredType`: allowing certain **bean types** not to count as matches in the missing-bean check.

> Key idea: "ignoring" only happens **when `@ConditionalOnMissingBean` is evaluated**. The ignored bean still exists in the `ApplicationContext`, can still be retrieved or injected, and can still cause multiple candidates when autowiring by the same interface.

## 2. Distinguishing the Type *to Look For* vs. the Type *to Ignore*

`@ConditionalOnMissingBean` belongs to `org.springframework.boot.autoconfigure.condition`. Some easily confused attributes:

| Attribute | Data Type | Role |
|---|---|---|
| `value` | `Class<?>[]` | Specifies the bean types to check whether they are **missing**; e.g., `MessageSender.class`. |
| `type` | `String[]` | Like `value`, but specifies **fully qualified class names** as strings. |
| `name` | `String[]` | Checks by **bean name**, not type name. |
| `ignored` | `Class<?>[]` | Bean types to **ignore when searching for matching beans**; e.g., `HealthCheckSender.class`. |
| `ignoredType` | `String[]` | Like `ignored`, but using **fully qualified class names** as strings; e.g., `"com.example.notice.HealthCheckSender"`. |

Both `ignored` and `ignoredType` default to empty arrays, can declare multiple elements, and can be used together. They add to the list of ignored types; they **do not replace** `value`/`type` (the target of the check). Spring Boot looks up beans using type info in the `BeanFactory`, then filters out candidates of the ignored types from the condition's matching results.

Illustrative example:

```java
@Bean
@ConditionalOnMissingBean(
    value = MessageSender.class,
    ignored = HealthCheckSender.class
)
DefaultSender defaultSender() {
    return new DefaultSender();
}
```

Suppose all beans below have already been **registered before** the condition runs:

| Existing Bean Implementing `MessageSender` | Without `ignored` | With `ignored = HealthCheckSender.class` |
|---|---|---|
| No bean at all | Creates `DefaultSender` | Creates `DefaultSender` |
| Only `HealthCheckSender` | Does not create | **Creates** `DefaultSender` |
| Only `BusinessSender` | Does not create | Does not create |
| Both `HealthCheckSender` and `BusinessSender` | Does not create | Does not create |

In the second scenario, there are **two `MessageSender` beans in the context** after the condition runs; ignoring does not remove the monitoring bean. If code injects a single `MessageSender` without specifying a candidate, consider an appropriate `@Qualifier` or `@Primary`.

## 3. Step-by-Step Evaluation Mechanism

1. Spring Boot processes the `@Bean` or auto-configuration class carrying `@ConditionalOnMissingBean`.
2. It determines the search requirement from `value`, `type`, `name`, `annotation`; if applied on a `@Bean` method without specifying a target type/name, the method's return type is normally the default target.
3. It collects beans **whose definitions have already been processed up to that point** within the search scope, then identifies candidates matching by type, name, and related constraints.
4. Beans whose types belong to `ignored`/`ignoredType` are removed from the candidate set used to decide the condition.
5. If no candidates remain satisfying the check requirement, the condition **matches** and the default configuration bean can be registered; if at least one checked candidate remains, the condition does not match.

Note that the condition does not actively wait for beans registered in the future. Therefore, place this condition in **auto-configuration**, which is processed after user bean definitions. When the outcome depends on a bean from another auto-configuration, ensure proper execution order (such as `@AutoConfiguration(after = ...)`).

## 4. Runnable Verification Example with Spring Boot 3.x and Java 17+

Place the file `src/test/java/demo/IgnoredBeanConditionTest.java` in a Spring Boot project with `spring-boot-starter-test`. The example uses `ApplicationContextRunner` to create isolated contexts, allowing user beans to be processed before auto-configuration. This is a test, so no HTTP server needs to run.

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IgnoredBeanConditionTest {

    interface MessageSender {
        String kind();
    }

    static final class HealthCheckSender implements MessageSender {
        @Override
        public String kind() {
            return "health";
        }
    }

    static final class BusinessSender implements MessageSender {
        @Override
        public String kind() {
            return "business";
        }
    }

    static final class DefaultSender implements MessageSender {
        @Override
        public String kind() {
            return "default";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class HealthConfiguration {
        @Bean
        HealthCheckSender healthCheckSender() {
            return new HealthCheckSender();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BusinessConfiguration {
        @Bean
        BusinessSender businessSender() {
            return new BusinessSender();
        }
    }

    @AutoConfiguration
    static class SenderAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(
                value = MessageSender.class,
                ignored = HealthCheckSender.class
        )
        DefaultSender defaultSender() {
            return new DefaultSender();
        }
    }

    @AutoConfiguration
    static class WithoutIgnoredAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(MessageSender.class)
        DefaultSender defaultSender() {
            return new DefaultSender();
        }
    }

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(SenderAutoConfiguration.class));

    @Test
    void createsDefaultWhenNoSenderExists() {
        runner.run(context -> {
            assertTrue(context.containsBean("defaultSender"));
            assertEquals("default", context.getBean(DefaultSender.class).kind());
        });
    }

    @Test
    void ignoresHealthBeanAndCreatesDefault() {
        runner.withUserConfiguration(HealthConfiguration.class)
                .run(context -> {
                    assertTrue(context.containsBean("healthCheckSender"));
                    assertTrue(context.containsBean("defaultSender"));
                });
    }

    @Test
    void businessBeanStillPreventsDefault() {
        runner.withUserConfiguration(
                        HealthConfiguration.class,
                        BusinessConfiguration.class
                )
                .run(context -> {
                    assertTrue(context.containsBean("healthCheckSender"));
                    assertTrue(context.containsBean("businessSender"));
                    assertFalse(context.containsBean("defaultSender"));
                });
    }

    @Test
    void withoutIgnoredHealthBeanPreventsDefault() {
        new ApplicationContextRunner()
                .withUserConfiguration(HealthConfiguration.class)
                .withConfiguration(
                        AutoConfigurations.of(WithoutIgnoredAutoConfiguration.class)
                )
                .run(context ->
                        assertFalse(context.containsBean("defaultSender"))
                );
    }
}
```

Run in a Spring Boot Gradle project with test dependencies:

```bash
./gradlew test --tests demo.IgnoredBeanConditionTest
```

On Windows, `./gradlew` can be replaced with `.\gradlew.bat`. Expected result: **4 tests pass**; each test checks bean presence by name, and the first test verifies the output of `kind()`. This is the expectation from the code; if a project has custom configuration or a different version, inspect the actual test report.

**Why does the example declare specific return types?** `@Bean HealthCheckSender healthCheckSender()` exposes the concrete type to Spring Boot when it evaluates conditions. If the method declared the broad return type `MessageSender`, the system might not yet infer `HealthCheckSender` at condition evaluation time, causing `ignored` not to take effect as expected. Similarly, `@Bean DefaultSender defaultSender()` has a concrete return type, yet the annotation **explicitly specifies** `value = MessageSender.class` to check the entire interface, not just `DefaultSender`.

## 5. Switching to `ignoredType` When Only the Type Name Is Available

When auto-configuration code wants to avoid directly referencing a class provided by an optional module, it can use the fully qualified class name:

```java
@Bean
@ConditionalOnMissingBean(
        value = MessageSender.class,
        ignoredType = "com.example.notice.HealthCheckSender"
)
DefaultSender defaultSender() {
    return new DefaultSender();
}
```

This snippet illustrates a method inside a configuration that already has the `MessageSender` and `DefaultSender` types; `com.example.notice.HealthCheckSender` is an **example class name** and should be replaced with the actual package in the application. `ignoredType` accepts a **Java class name**, not a bean name like `"healthCheckSender"`, nor an expression or wildcard. For nested classes, the binary name may use the `$` character; do not guess the name—verify with `SomeClass.class.getName()`.

Equivalent declarations:

```java
ignored = HealthCheckSender.class

ignoredType = "com.example.notice.HealthCheckSender"
```

- Choose `ignored` when the class is available on the compile classpath: clear, compiler-checked, and refactoring-safe.
- Choose `ignoredType` when you need to declare by class name, especially when building auto-configuration integrating an optional module without wanting annotation code to depend directly on that class.
- If creating a custom annotation wrapping `@ConditionalOnMissingBean` (meta-annotation), be careful with class references when Spring reads annotation metadata; the Javadoc recommends preferring the string-based `ignoredType` attribute for ignored types in this scenario.

Using a string does not make a non-existent class magically appear. If the listed type does not exist at runtime, there are no beans of that type to ignore; other targets and conditions are still checked normally.

## 6. Common Misunderstandings

**Misconception 1 — "`ignored` deletes the bean from Spring".** False: it only excludes the bean from the matching result set for **that condition evaluation**. The bean can still be retrieved by name, `getBeansOfType`, or injected. If you create an additional fallback bean implementing the same interface, interface-based injection may need to resolve ambiguity via `@Qualifier`, `@Primary`, or cleaner design.

**Misconception 2 — "`ignoredType` is a bean name".** False: you must use a type like `"com.example.notice.HealthCheckSender"`. Bean names belong to the `name` attribute and are a separate check criterion.

**Misconception 3 — Ignoring the checked interface itself.** If you set `value = MessageSender.class, ignored = MessageSender.class`, every type-matching `MessageSender` candidate can be ignored; the fallback may be created even when the application has already provided a business bean. Specify **a concrete technical implementation type** with a clear reason for ignoring it.

**Misconception 4 — Omitting `value` when returning an implementation type.** With `@Bean DefaultSender defaultSender()` and `@ConditionalOnMissingBean(ignored = HealthCheckSender.class)`, by default it may only check for the absence of `DefaultSender`, not the absence of `MessageSender`. When the target is an interface or abstraction, write `value = MessageSender.class` explicitly.

**Misconception 5 — Configurations running in the wrong order.** A bean whose definition does not exist yet when the condition is evaluated will not be counted, even if the bean appears later. Put fallback beans in auto-configuration, order them after related auto-configurations, and test with `ApplicationContextRunner`.

**Misconception 6 — The ignored bean lacks recognizable type metadata.** When `@Bean` returns a generic interface, or involves a `FactoryBean`, proxy, or dynamic bean registration configuration, the concrete implementation type may not be visible when the condition runs. Expose a sufficiently specific return type, or design the condition around types/names actually known to Spring; do not assume matching will rely on the runtime instance after bean instantiation.

**Misconception 7 — Using `ignored` to replace classpath conditions.** `ignored`/`ignoredType` checks **registered beans**, not whether a library is on the classpath. To enable configuration when a dependency is present or absent, use `@ConditionalOnClass`/`@ConditionalOnMissingClass` appropriately.

## 7. How to Inspect and Diagnose

1. Confirm what type the check target is (`value`/`type`), and which **concrete implementation type** you want to ignore.
2. Confirm the candidate `@Bean` exposes appropriate type metadata, especially before beans have been instantiated as objects.
3. Use `ApplicationContextRunner` to write scenarios for **no bean**, **only the ignored bean**, **business bean present**, and **both present**. Rely on bean counts only when appropriate for the test; the example above tests bean names so results are not confused with other sender types.
4. When running the application, enable the condition report with `--debug` or view `/actuator/conditions` if the project has Spring Boot Actuator installed and appropriately configured. Look up `OnBeanCondition` results and the auto-configuration name, distinguishing a matching condition from actual bean creation.
5. If multiple beans exist for the same interface after the fallback is created, inspect injection points to apply qualifiers/primary appropriately.

## 8. Takeaways to Apply

- `value`/`type` answers: **"Which bean type are we checking is missing?"**
- `ignored`/`ignoredType` answers: **"During that check, which bean types must not be counted?"**
- `ignored` takes `Class<?>[]`; `ignoredType` takes `String[]` containing fully qualified class names.
- Ignoring in a condition **does not remove the bean**, does not disable autowiring, and does not change the search scope.
- Condition evaluation relies on already-processed bean definitions; auto-configuration and processing order matter greatly.

### Official Reference Documentation

- Spring Boot 3.3 Javadoc — `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot Reference — Developing Auto-configuration, Bean Conditions: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
