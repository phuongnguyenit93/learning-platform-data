# @ConditionalOnBean: Requiring Dependent Beans to Already Be Registered

## 1. Problem and Purpose

Suppose a Spring Boot library provides a `GatewayReporter` bean to monitor the status of `Gateway`. Not every application declares a `Gateway`. If `GatewayReporter` is always registered and asks Spring to inject `Gateway` via its constructor or `@Bean` method parameter, an application without `Gateway` can fail to start due to a missing dependency.

`@ConditionalOnBean` solves the problem of *conditional bean registration*: it only registers a bean or a configuration group when the `BeanFactory` already contains beans that satisfy the specified requirements.

~~~java
@Bean
@ConditionalOnBean(Gateway.class)
GatewayReporter gatewayReporter(Gateway gateway) {
    return new GatewayReporter(gateway);
}
~~~

In this example:
- When a bean of type `Gateway` has already been registered and is visible to the condition, Spring can register the `gatewayReporter` definition.
- When no `Gateway` bean is found, the `gatewayReporter` definition is skipped; no `GatewayReporter` object is created by this method.
- The condition **does not create** `Gateway` itself, nor does it mean that the dependent bean has already been initialized, connected successfully over the network, or is ready to serve requests.

This is a **Spring Boot** annotation: `org.springframework.boot.autoconfigure.condition.ConditionalOnBean`, built on top of Spring Framework's `@Conditional` mechanism.

## 2. What Is Checked and When?

You need to distinguish three events:

1. **Bean definition declaration/registration:** Spring has processed `@Component`, `@Bean`, or another registration mechanism and knows which beans exist, their names, and their types.
2. **Condition evaluation:** When processing a configuration annotated with `@ConditionalOnBean`, Spring Boot inspects the bean definitions **that have been processed up to that point** within the configured search scope.
3. **Instance creation and dependency injection:** Only afterward does Spring instantiate the required beans and resolve dependencies according to the container lifecycle.

Therefore, "a bean has been registered" is different from "a bean has finished initializing." A `@Lazy` bean may already be registered and make the condition match even though its instance has not been created yet. Conversely, a bean expected to be declared by another auto-configuration that **has not yet been processed** when the condition runs can cause the condition not to match.

`@ConditionalOnBean` is a decision made while building the `ApplicationContext`, not a mechanism that continuously watches the container to turn beans on or off while the application is running.

### How to Properly Understand Multi-Bean Requirements

~~~java
@ConditionalOnBean({Gateway.class, AuditStore.class})
~~~

Both the `Gateway` type **and** the `AuditStore` type must be found. They can be **two different beans**; the annotation does not require a single instance to be both types simultaneously.

~~~java
@ConditionalOnBean(value = Gateway.class, name = "primaryAuditStore")
~~~

A bean of type `Gateway` **and** a bean named `primaryAuditStore` must both exist; the two requirements do not necessarily have to be satisfied by the same bean. This is a conjunction of existence requirements, **not** a rule for automatically selecting the right bean for a dependency injection parameter.

## 3. Attributes You Need to Know

| Usage | What It Checks |
| --- | --- |
| `@ConditionalOnBean(Gateway.class)` or `value = ...` | Whether a bean with the specified type exists. With multiple types, all types must be present. |
| `@ConditionalOnBean(type = "com.example.Gateway")` | Whether a bean exists by class name as a string; useful when you do not want to reference the type directly in the annotation. |
| `@ConditionalOnBean(name = "gateway")` | Whether a bean with the specified name exists; if multiple names are declared, all must exist. |
| `@ConditionalOnBean(annotation = Marker.class)` | Whether a bean marked with the requested annotation exists; multiple annotations are multiple conditions that must be satisfied. |
| `search = SearchStrategy.CURRENT` | Checks only the current context, ignoring parent contexts. The default is `SearchStrategy.ALL`, which includes parent contexts. |
| `parameterizedContainer = ...` | Allows also inspecting generic container beans holding the target type, for example a custom `Registration<Gateway>` container. |

**Pitfall when omitting arguments:** Placing `@ConditionalOnBean` with no arguments on a `@Bean` method defaults the target type to **the return type of that method itself**, rather than automatically inferring the method's dependency parameters. If the goal is "only create the reporter when a gateway exists," explicitly write `@ConditionalOnBean(Gateway.class)`.

### Placing on a Class or a Method?

- On a **`@Bean` method**: the condition governs only the registration of the bean created by that method.
- On a **`@Configuration` or `@AutoConfiguration` class**: the condition governs the registration of that configuration class and its beans. If it does not match, the configuration class is not registered as a bean.
- Class-level and method-level conditions can be combined when beans have different requirements. Each level must satisfy its respective condition.

## 4. Runnable Example: Verifying Both Present and Missing Beans

The example below is a **complete Java 17+ test** for a Spring Boot 3.3 project with the `spring-boot-starter-test` dependency. Create the file:

`src/test/java/com/example/demo/OnBeanConditionTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class OnBeanConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ReporterAutoConfiguration.class));

    interface Gateway {
        String state();
    }

    static final class GatewayReporter {
        private final Gateway gateway;

        GatewayReporter(Gateway gateway) {
            this.gateway = gateway;
        }

        String report() {
            return "gateway=" + gateway.state();
        }
    }

    @AutoConfiguration
    static class ReporterAutoConfiguration {

        @Bean
        @ConditionalOnBean(Gateway.class)
        GatewayReporter gatewayReporter(Gateway gateway) {
            return new GatewayReporter(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGatewayConfiguration {

        @Bean
        Gateway gateway() {
            return () -> "ready";
        }
    }

    @Test
    void withoutGateway_reporterIsNotRegistered() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(Gateway.class);
            assertThat(context).doesNotHaveBean(GatewayReporter.class);
        });
    }

    @Test
    void withGateway_reporterIsRegistered() {
        runner.withUserConfiguration(UserGatewayConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Gateway.class);
                    assertThat(context).hasSingleBean(GatewayReporter.class);
                    assertThat(context.getBean(GatewayReporter.class).report())
                            .isEqualTo("gateway=ready");
                });
    }
}
~~~

In a Gradle project configured with the Spring Boot plugin and `spring-boot-starter-test`, run:

~~~bash
./gradlew test --tests "com.example.demo.OnBeanConditionTest"
~~~

On Windows you can use `.\gradlew.bat test --tests "com.example.demo.OnBeanConditionTest"`. Because this test uses Spring, JUnit, and AssertJ libraries, it **cannot** be compiled with `javac` alone without providing the full dependency classpath.

**Expected result:** both tests PASS. The first test does not declare `Gateway`, so there is no `GatewayReporter` bean. The second test adds a user configuration containing the `Gateway` bean; the auto-configuration detects it and registers the reporter. `report()` returns the exact string `gateway=ready`, verified by assertions rather than relying on stdout or build logs.

`ApplicationContextRunner` runs two independent contexts and verifies the actual conditions without starting an entire web server.

## 5. Auto-Configuration Ordering: The Subtlest Pitfall

If `Gateway` is **user-declared** in the application configuration, Spring Boot normally processes user bean definitions before auto-configuration. Therefore, conditions in auto-configuration usually see it.

If `Gateway` is **created by another auto-configuration**, you must ensure the configuration creating `Gateway` is processed **before** the dependent configuration. The following example only illustrates the relationship between two auto-configurations; it assumes `Gateway` and `GatewayReporter` are already defined as in the previous section:

~~~java
@AutoConfiguration
class GatewayAutoConfiguration {
    @Bean
    Gateway gateway() {
        return () -> "ready";
    }
}

@AutoConfiguration(after = GatewayAutoConfiguration.class)
class ReporterAutoConfiguration {
    @Bean
    @ConditionalOnBean(Gateway.class)
    GatewayReporter gatewayReporter(Gateway gateway) {
        return new GatewayReporter(gateway);
    }
}
~~~

Here, `after = GatewayAutoConfiguration.class` instructs Spring Boot to process the configuration that creates `Gateway` before the configuration that creates the reporter. Equivalently, you can use `@AutoConfigureAfter(GatewayAutoConfiguration.class)`. Auto-configurations used in a real application must be discoverable by Spring Boot, for instance listed by fully qualified class name in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` (for Spring Boot 3.x).

**Important:** `after` and `@AutoConfigureAfter` control the **order in which bean definitions are registered**, not the order in which instances are initialized. Initialization order is determined by dependency injection relationships, lifecycle, and possibly `@DependsOn`.

Do not expect `@DependsOn("gateway")` to fix a `@ConditionalOnBean` that already evaluated to **non-matching** due to registration order: `@DependsOn` only affects the initialization of beans that have already been registered.

## 6. Comparison with Easily Confused Mechanisms

| Mechanism | Question It Answers | Appropriate Use Case |
| --- | --- | --- |
| `@ConditionalOnBean` | Has the required bean **already been registered and become visible**? | Register an extension only when a dependent bean exists. |
| `@ConditionalOnMissingBean` | Does no bean satisfying the requirement exist yet? | Provide a default bean that users can replace. |
| `@ConditionalOnClass` | Is the Java type on the classpath? | Enable an integration only when the corresponding library is present. |
| `@ConditionalOnProperty` | Do configuration/property values satisfy the condition? | Enable/disable a feature via configuration. |
| `@ConditionalOnSingleCandidate` | Is there a suitable single candidate, such as only one matching bean or a clear primary? | Select an unambiguous dependency when multiple beans of the same type exist. |
| `@DependsOn` | Which instance needs to be initialized before another? | Coordinate initialization for beans **that have already been registered**. |

For example, merely having the library containing the `Gateway` class on the classpath is **not enough** for `@ConditionalOnBean(Gateway.class)` to match. There must be a matching bean in the `BeanFactory`. Conversely, having a bean definition does not guarantee it has been initialized, or that initialization will succeed.

## 7. Common Mistakes and How to Fix Them

1. **The dependent bean exists in source code, yet the condition is still false.** Check whether it is actually registered in the context: is the class component-scanned, is the `@Bean` imported, is another condition blocking it, or does the auto-configuration creating it run later?
2. **Putting `@ConditionalOnBean` in user configuration and relying on scan order.** The processing order of bean definitions can yield unexpected results. Per Spring Boot's recommendation, prefer using bean conditions in auto-configuration, where user-declared beans have already been processed beforehand.
3. **Forgetting to specify the dependency type.** An empty `@ConditionalOnBean` on `@Bean Reporter reporter(...)` checks `Reporter` by default, not `Gateway`. Write `@ConditionalOnBean(Gateway.class)` explicitly.
4. **Declaring an overly generic return type like `Object` on a `@Bean` method.** Conditions rely on type metadata known at evaluation time. Return the most specific and informative type possible instead of hiding the real type inside a factory method.
5. **The condition is true, yet bean injection still fails.** The existence of a bean by type or name does not guarantee a single bean matching `@Qualifier`, without ambiguity or circular dependencies. When a single candidate is needed, consider `@ConditionalOnSingleCandidate` or clarify with `@Qualifier`/`@Primary`.
6. **An optional bean is skipped, yet a consumer still requires injecting it.** Making only the reporter conditional while another bean constructor-injects a required `GatewayReporter` can still cause context startup to fail. Align conditions on the consumer, design optional integration, or provide an appropriate fallback.
7. **Confusing parent/child contexts.** The default `search = ALL` can find beans in a parent context. If only beans from the current context are acceptable, use `SearchStrategy.CURRENT`; you must account for the exact context hierarchy when debugging.
8. **Believing the condition guarantees healthy runtime infrastructure.** It only inspects bean registration. A bean can still fail during initialization or fail to connect to an external service after the condition has matched.

## 8. Diagnostics and Testing

When a bean does not appear:

1. Enable Spring Boot's condition report using the `--debug` argument or the `debug=true` property in an appropriate environment. Look for the auto-configuration name and the `matched`/`did not match` reason related to `OnBeanCondition`.
2. Confirm that the prerequisite bean is present **in the right ApplicationContext** and that the visible type of the bean definition matches the type being checked.
3. If the prerequisite is declared by another auto-configuration, check `@AutoConfiguration(after = ...)` or `@AutoConfigureAfter` and the auto-configuration registration in the imports file.
4. Write `ApplicationContextRunner` tests for at least the two branches: **without** and **with** the prerequisite. If two auto-configurations are involved, add a test running both to verify ordering. When needed, use `ConditionEvaluationReportLoggingListener` to inspect condition reasons in tests.
5. If the project includes Actuator and actively enables/exposes the corresponding endpoint, `/actuator/conditions` can also help inspect condition evaluation; exposing the endpoint depends on configuration and access policies.

### Self-Check Questions

- If the `Gateway` bean only exists as a class on the classpath, does `@ConditionalOnBean(Gateway.class)` match? **No, if no matching bean has been registered yet.**
- If a `Gateway` bean definition exists but the instance has not been created because of `@Lazy`, can the condition match? **Yes**, if the bean definition has already been processed and has sufficient type information.
- If the condition requires `{Gateway.class, AuditStore.class}`, must the two types belong to the same instance? **No**; all requirements must be satisfied, which may be done by multiple beans.
- Why is `@AutoConfiguration(after = ...)` needed? **So that the dependent auto-configuration is evaluated after the bean definitions from the providing auto-configuration have been processed.**
- Can `@DependsOn` turn a false condition into true? **No**; it handles initialization order, not retroactively re-evaluating registration conditions.

## Official Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): bean conditions, auto-configuration ordering, and `ApplicationContextRunner`.
- [Spring Boot 3.3 — JavaDoc `@ConditionalOnBean`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): exact semantics and annotation attributes.
