# Bean Conditions Only Observe Definitions Already Processed at Evaluation Time

> **Core rule:** When Spring Boot evaluates `@ConditionalOnBean` or `@ConditionalOnMissingBean`, the condition only sees the bean definitions that the `ApplicationContext` has processed at **that moment**. It cannot foresee bean definitions that will be registered in a subsequent step, even if they will exist by the time the application finishes starting.

This is an important rule when designing **Spring Boot Auto Configuration**, especially when one auto-configuration depends on a bean provided by another auto-configuration or when you need to provide a default bean while still allowing the application to override it.

## 1. What Does "Already Processed" Mean?

A **bean definition** is the metadata Spring uses to manage a bean: bean type, name, how to create it, scope, etc. Having a definition registered is **different** from the bean object already being instantiated.

Picture the startup process of an application:

1. Spring processes user configurations, registering the corresponding bean definitions.
2. Spring Boot processes auto-configurations in a determined order, adding bean definitions from those classes if conditions allow.
3. The container creates the needed beans, injects dependencies, and completes startup; object creation order depends on dependency relationships and initialization constraints.

At step 2, suppose configuration A has already registered the `Clock` definition, while configuration B has not yet been processed: a condition checking for `Clock` will see the definition from A, but cannot look ahead at definitions that B intends to register. A bean declared with `@Lazy` can still be recognized by the condition if its **definition** already exists, even though the object has not yet been instantiated.

| Condition | Question It Answers at Evaluation Time | Consequence of a Definition Arriving Later |
| --- | --- | --- |
| `@ConditionalOnBean(Clock.class)` | Is there already a matching bean of type `Clock` in the search scope? | A bean appearing later cannot make the condition true at this point. |
| `@ConditionalOnMissingBean(Clock.class)` | Is there currently **no** matching bean of type `Clock`? | A fallback may already be registered before another configuration declares `Clock`. |

"Matching" is not based solely on class name text: Boot checks the specified bean type, name, or annotation; the search scope in the `ApplicationContext` hierarchy and whether a bean qualifies as a candidate also have an effect. The ordering examples below assume a single context and ordinary beans eligible for autowiring.

**Do not confuse three different things:** a class being on the classpath ≠ a registered bean definition ≠ a created bean object. `@ConditionalOnClass` inspects the classpath; bean conditions inspect the registry/factory at evaluation time; and `@DependsOn` primarily governs bean initialization order.

## 2. Why Can Processing Order Change the Result?

Consider two auto-configurations in the same application:

- `ClockAutoConfiguration` creates a default `Clock` bean.
- `ClockConsumerAutoConfiguration` creates `ClockReader` only if a `Clock` bean already exists.

If the consumer configuration is evaluated **before** the `Clock` definition appears, `@ConditionalOnBean(Clock.class)` may not match and `ClockReader` is skipped. When the `Clock` definition is registered afterward, Spring Boot does not automatically "go back" to register a `@Bean` method that was already excluded by an earlier condition.

Similarly, if an auto-configuration checks `@ConditionalOnMissingBean(Clock.class)` too early, it may create a fallback while another auto-configuration has not yet registered a `Clock`. If the later configuration registers `Clock` without a corresponding condition, the application can end up with multiple beans of the same type and cause ambiguity during dependency injection.

**Therefore, ordering matters in the bean definition registration phase.** `@AutoConfiguration(after = ...)` or `@AutoConfigureAfter` is how you declare ordering relationships between auto-configurations. They **do not** guarantee which bean is instantiated as an object first, nor do they replace `@DependsOn` or dependency injection when initialization order is truly needed.

## 3. Java 17+ Example — Declaring the Right Order

The following example uses Spring Boot 3.x. Three Java classes belong to package `example.autoconfig`; this package should sit outside the application's component-scan scope because auto-configurations are loaded via the auto-configuration mechanism and should not be scanned like user configurations.

**File `src/main/java/example/autoconfig/ClockAutoConfiguration.java`:**

~~~java
package example.autoconfig;

import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ClockAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
~~~

When no matching `Clock` bean exists yet, Boot registers the `appClock` definition. If the application has already defined its own `Clock`, the condition does not match and this method does not contribute a default bean. Explicitly specifying `Clock.class` also makes it clear to readers which type is being checked; with `@ConditionalOnMissingBean` placed on `@Bean` without specifying type or name, Boot can infer the type from the method's return type.

**File `src/main/java/example/autoconfig/ClockReader.java`:**

~~~java
package example.autoconfig;

import java.time.Clock;
import java.time.Instant;

public record ClockReader(Clock clock) {
    public Instant now() {
        return clock.instant();
    }
}
~~~

`ClockReader` is an object that depends on `Clock`; it uses the `Clock` injected by the container rather than creating a new clock itself.

**File `src/main/java/example/autoconfig/ClockConsumerAutoConfiguration.java`:**

~~~java
package example.autoconfig;

import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = ClockAutoConfiguration.class)
@ConditionalOnBean(Clock.class)
public class ClockConsumerAutoConfiguration {
    @Bean
    public ClockReader clockReader(Clock clock) {
        return new ClockReader(clock);
    }
}
~~~

Explaining each key point:

1. `after = ClockAutoConfiguration.class` tells Boot to process the auto-configuration that provides `Clock` before the auto-configuration that consumes `Clock`.
2. `@ConditionalOnBean(Clock.class)` at the **class level** allows registering the consumer configuration only when a matching `Clock` bean already exists at evaluation time. If the condition is placed on an individual `@Bean` method, it controls only the registration of the bean from that method.
3. The `Clock clock` parameter of `clockReader` is a dependency when creating the object; it does not make a class-level condition automatically see an unregistered definition.

For Boot 3.x to discover these two auto-configurations when packaged in a library, add the file:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
example.autoconfig.ClockConsumerAutoConfiguration
example.autoconfig.ClockAutoConfiguration
~~~

The line order in this file is **not** how dependencies are declared. Boot sorts auto-configurations based on metadata, where the `after` relationship in this example requires `ClockAutoConfiguration` to be processed before `ClockConsumerAutoConfiguration`. To test without packaging a library, you can load the classes directly with `ApplicationContextRunner` as shown in the next section.

### Two Scenarios to Distinguish

**A. The application does not define its own `Clock`:**

- `ClockAutoConfiguration` sees `Clock` is missing and registers the default `appClock`.
- When it is `ClockConsumerAutoConfiguration`'s turn, the `Clock` definition is already present, so the condition is true and `clockReader` is registered.
- When instantiating `ClockReader`, Spring injects the existing `Clock` bean.

**B. The application has a user-defined `@Bean Clock customClock()`:**

- Boot processes user-declared bean definitions before auto-configurations.
- `@ConditionalOnMissingBean(Clock.class)` does not match, so the default `appClock` is not registered.
- The consumer's `@ConditionalOnBean(Clock.class)` still matches and `clockReader` uses `customClock`.

The conclusions above assume there is only one matching `Clock` bean; with multiple candidates, injection also needs to account for `@Primary`, qualifiers, or bean names.

## 4. Verifying with ApplicationContextRunner

In a Spring Boot 3.x project with the `spring-boot-starter-test` dependency, create `src/test/java/example/autoconfig/ClockAutoConfigurationTest.java`:

~~~java
package example.autoconfig;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ClockAutoConfigurationTest {
    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(
                            ClockConsumerAutoConfiguration.class,
                            ClockAutoConfiguration.class));

    @Test
    void registersDefaultClockBeforeConsumer() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Clock.class);
            assertThat(context).hasSingleBean(ClockReader.class);
            assertThat(context).hasBean("appClock");
        });
    }

    @Test
    void userClockMakesDefaultBackOff() {
        runner.withUserConfiguration(UserClockConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Clock.class);
                    assertThat(context).hasSingleBean(ClockReader.class);
                    assertThat(context).hasBean("customClock");
                    assertThat(context).doesNotHaveBean("appClock");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClockConfiguration {
        @Bean
        Clock customClock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC);
        }
    }
}
~~~

Run in a Maven or Gradle project configured with JUnit 5:

~~~bash
mvn test -Dtest=ClockAutoConfigurationTest
# Or with Gradle:
./gradlew test --tests example.autoconfig.ClockAutoConfigurationTest
~~~

**Expected result:** both tests PASS. The first test confirms that the fallback and the consuming bean coexist. The second test confirms that the user-declared bean is already known before evaluating the fallback; Boot does not register `appClock` yet still creates `ClockReader`. Do not infer order from the position of the two classes in `AutoConfigurations.of(...)`: the runner processes auto-configuration order just like the application flow.

## 5. How to Read Errors and Troubleshoot Systematically

When `@ConditionalOnBean` unexpectedly **does not match** or `@ConditionalOnMissingBean` creates an unintended fallback:

1. **Check the exact bean being looked up:** type (`value`/`type`), name (`name`), annotation, whether the bean qualifies as a candidate, and the `search` parameter if there is a context hierarchy. Having a class on the classpath does not mean a bean definition has been registered.
2. **Identify who creates the bean definition and when:** is the bean declared by the application or from another auto-configuration? If from another auto-configuration, are `before`/`after` relationships properly declared on the auto-configurations?
3. **Check the return type of `@Bean`:** type metadata must be specific enough for Boot to recognize the condition before instantiating objects. For example, do not declare an overly generic return type like `Object` when a condition looks for a specific type.
4. **Inspect the Condition Evaluation Report:** start with `--debug` or read the Actuator `/actuator/conditions` endpoint when Actuator is installed and access to the endpoint is permitted. The report tells you which conditions matched/did not match and why; compare it against the actual auto-configuration order.
5. **Reproduce with `ApplicationContextRunner`:** test separately the cases "no bean," "user bean present," "bean provided by another auto-configuration," and "changing order."

Do not use `@DependsOn` to fix a bean condition failing to see a definition: `@DependsOn` resolves dependencies during **bean creation**, whereas this issue occurs during **definition registration**. Also do not use `@Primary` to mask an accidentally created extra fallback; `@Primary` mainly resolves bean selection at injection time.

## 6. Common Misconceptions

- **"If the bean exists at the end, `@ConditionalOnBean` will surely be true."** False. A condition evaluated earlier may not see this bean.
- **"`@ConditionalOnMissingBean` means the entire context will never have that bean."** False. It inspects the part of the registry processed at evaluation time, without predicting the future.
- **"The bean must be instantiated before it counts as existing."** False. A matching registered definition can be enough; there is no need to call `getBean()` to force instantiation.
- **"Ordering auto-configurations also orders when constructors are called."** False. Those are two different phases.
- **"Using these two annotations freely in user configuration is safe too."** Do not assume so. Spring Boot's official recommendation is to use them in auto-configurations because Boot processes auto-configurations after user-declared definitions.
- **"Just matching the class name makes the condition match."** Incomplete. Conditions can be based on type, name, annotation, and context hierarchy; some definitions are not eligible as candidates.

## 7. Self-Check Questions

1. A `@Bean` with `@Lazy` has registered its definition, but its object has not yet been created. Can `@ConditionalOnBean` see it? **Yes**, if the bean matches the search criteria.
2. The consumer auto-configuration is evaluated before the provider; the provider later registers a bean of the right type. Will the consumer automatically be re-triggered? **No**, there is no mechanism to go back and register a bean already skipped by that condition; the processing order must be fixed.
3. A library wants to provide a default service while yielding to a bean declared by the application. What should be placed and where? **`@ConditionalOnMissingBean(Service.class)` on the default bean inside an auto-configuration**, with a sufficiently clear `@Bean` return type; if it depends on another auto-configuration, declare the appropriate ordering.

## Reference Documentation

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): bean conditions, auto-configuration ordering, `@Bean` return type recommendations, and `ApplicationContextRunner`.
- [Spring Boot 3.3 API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): "processed so far" rule, search criteria, and return type inference.
- [Spring Boot 3.3 API — ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): condition based on processed bean definitions.

**Remember:** a bean condition is a question about the registry state **at evaluation time**. When it depends on a bean from another auto-configuration, design the definition registration order properly and verify it with a small context test.
