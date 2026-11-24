# Using withUserConfiguration to Simulate Application Configuration When Testing Spring Boot Auto-configuration

## 1. Why simulate application-provided configuration?

A Spring Boot library typically includes an auto-configuration that provides default beans. A consuming application may declare its own beans to replace defaults, supply additional dependencies, or customize integration behavior.

For example, a library provides a default `GreetingService`. An application wants to use greetings with its own rules:

~~~java
@Configuration(proxyBeanMethods = false)
class UserGreetingConfiguration {

    @Bean
    CustomGreetingService customGreetingService() {
        return new CustomGreetingService();
    }
}
~~~

When testing an auto-configuration, we need to reproduce two independent scenarios:

- The application **does not declare** a custom bean: the library must create the default.
- The application **declares** a custom bean: the auto-configuration must recognize that bean and back off properly.

Spring Boot's `ApplicationContextRunner` creates a small `ApplicationContext` for each test. The `withUserConfiguration(...)` method lets you pass one or more configuration classes representing application-owned configuration directly into the test context.

**Significance:** tests can verify the interaction between user configuration and auto-configuration without booting the entire application, scanning all packages, or standing up a real server/database.

## 2. What components make up ApplicationContextRunner?

A runner typically has two configuration groups:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(GreetingAutoConfiguration.class));
~~~

- `ApplicationContextRunner` is a standalone context builder suited for tests focused on bean registration and conditions.
- `withConfiguration(AutoConfigurations.of(...))` adds the auto-configurations under test to the runner using the mechanism dedicated to auto-configuration.
- `withUserConfiguration(...)` adds user-provided configuration, typically `@Configuration` classes with `@Bean` methods.
- `run(context -> { ... })` opens the context, executes assertions inside the callback, and closes the context afterward.

A key mindset is role separation:

| API | Used to simulate | Example |
| --- | --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Library/Spring Boot auto-configuration under test | `GreetingAutoConfiguration.class` |
| `withUserConfiguration(...)` | Application-declared configuration | `UserGreetingConfiguration.class` |
| `withPropertyValues(...)` | Application configuration values in `Environment` | `acme.greeting.prefix=Hi` |
| `withBean(...)` | A test bean registered directly via supplier/type | Mock or standalone fixture |
| `withClassLoader(...)` | Application classpath in a test scenario | `FilteredClassLoader` to simulate a missing dependency |
| `withInitializer(...)` | ApplicationContext initializer/listener | Printing `ConditionEvaluationReport` |

Do not pass an auto-configuration to `withUserConfiguration` just to make it appear in the context. Use `AutoConfigurations.of(...)` for auto-configurations so Boot applies the proper semantics and ordering for that group.

## 3. What does withUserConfiguration do?

`withUserConfiguration(Class<?>... userConfigurations)` accepts one or more configuration classes and adds them to the context created by the runner.

Example:

~~~java
contextRunner
        .withUserConfiguration(
                UserGreetingConfiguration.class,
                UserMetricsConfiguration.class)
        .run(context -> {
            // Verify beans declared by the application
        });
~~~

These classes are usually written with `@Configuration(proxyBeanMethods = false)` and supply beans via `@Bean`. Each class can represent an independent part of the application's configuration: custom clients, metrics, caches, security adapters, or mock dependencies.

This method:
- Registers the passed configuration sources with the runner.
- Allows `@Bean` methods in the user configuration to participate in context creation.
- Helps verify that the auto-configuration sees user-provided beans and backs off properly.
- Lets you combine multiple configuration classes in the same scenario.

It **does not automatically scan the package** containing those classes. You explicitly specify which classes are included. If the user configuration itself carries `@ComponentScan`, that scan may still run; therefore, tests focused on auto-configuration should keep fixtures explicit and avoid unintended scanning.

### Nested configurations in tests should be static

A common organization pattern is placing fixture classes inside the test class:

~~~java
@Configuration(proxyBeanMethods = false)
static class UserGreetingConfiguration {

    @Bean
    CustomGreetingService customGreetingService() {
        return new CustomGreetingService();
    }
}
~~~

Use a `static` nested class so Spring can instantiate the configuration without needing an instance of the enclosing test class. These classes are strictly test fixtures; there is no need to place them in the application's component-scan packages.

## 4. Sample auto-configuration structure

Let's build a Java 17+ example with three parts:

1. `GreetingService` is the API consumed by clients.
2. `GreetingAutoConfiguration` creates a default when no implementation exists.
3. User configuration can supply a custom implementation and another supporting bean.

Interface:

~~~java
public interface GreetingService {
    String message();
}
~~~

Default implementation:

~~~java
public final class DefaultGreetingService implements GreetingService {

    @Override
    public String message() {
        return "hello from library";
    }
}
~~~

Auto-configuration:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    DefaultGreetingService greetingService() {
        return new DefaultGreetingService();
    }

    @Bean
    @ConditionalOnBean(AuditSink.class)
    GreetingAuditRecorder greetingAuditRecorder(AuditSink auditSink) {
        return new GreetingAuditRecorder(auditSink);
    }
}
~~~

Key points to note:

- The `@ConditionalOnMissingBean(GreetingService.class)` condition checks the interface contract. If user configuration supplies a bean implementing `GreetingService`, the default is not registered.
- The method return type is `DefaultGreetingService`, a concrete type that gives Spring clear type metadata.
- `@ConditionalOnBean(AuditSink.class)` illustrates another auto-configured bean that appears only when the application supplies the `AuditSink` prerequisite.
- Bean conditions of this style belong in auto-configuration. Spring Boot ensures auto-configuration is applied after user-declared bean definitions; conditions evaluate against bean definitions already processed up to that point.

In a real library, the auto-configuration must also be published via `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. The runner below receives the class directly through `AutoConfigurations.of(...)`, so the test fixture does not require the descriptor to load that class into the runner.

## 5. User configuration representing the application

The application supplies its own implementation:

~~~java
@Configuration(proxyBeanMethods = false)
static class UserGreetingConfiguration {

    @Bean
    CustomGreetingService customGreetingService() {
        return new CustomGreetingService();
    }
}
~~~

Bean class:

~~~java
static final class CustomGreetingService implements GreetingService {

    @Override
    public String message() {
        return "hello from application";
    }
}
~~~

Another application configuration can provide a supporting dependency:

~~~java
@Configuration(proxyBeanMethods = false)
static class UserAuditConfiguration {

    @Bean
    MemoryAuditSink auditSink() {
        return new MemoryAuditSink();
    }
}
~~~

In the test, call:

~~~java
contextRunner
        .withUserConfiguration(
                UserGreetingConfiguration.class,
                UserAuditConfiguration.class)
        .run(context -> {
            // Context contains both custom greeting and audit sink
        });
~~~

This is the strength of `withUserConfiguration`: you can assemble a context simulating multiple parts of real application configuration. There is no need to copy every production class; include only the configuration sources relevant to the scenario under test.

## 6. Complete test with JUnit 5 and AssertJ

The following file puts the interfaces, implementations, auto-configuration, and user configurations into a single test class so the example can be read and run standalone. The project requires Java 17+, Spring Boot 3.3, and the `spring-boot-starter-test` dependency.

Create `src/test/java/com/example/demo/GreetingAutoConfigurationTests.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    interface GreetingService {
        String message();
    }

    static final class DefaultGreetingService implements GreetingService {
        @Override
        public String message() {
            return "hello from library";
        }
    }

    static final class CustomGreetingService implements GreetingService {
        @Override
        public String message() {
            return "hello from application";
        }
    }

    interface AuditSink {
        String destination();
    }

    static final class MemoryAuditSink implements AuditSink {
        @Override
        public String destination() {
            return "memory";
        }
    }

    static final class GreetingAuditRecorder {
        private final AuditSink auditSink;

        GreetingAuditRecorder(AuditSink auditSink) {
            this.auditSink = auditSink;
        }

        String destination() {
            return auditSink.destination();
        }
    }

    static final class GreetingMetrics {
    }

    @AutoConfiguration
    static class GreetingAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(GreetingService.class)
        DefaultGreetingService greetingService() {
            return new DefaultGreetingService();
        }

        @Bean
        @ConditionalOnBean(AuditSink.class)
        GreetingAuditRecorder greetingAuditRecorder(AuditSink auditSink) {
            return new GreetingAuditRecorder(auditSink);
        }

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.greeting.metrics",
                name = "enabled",
                havingValue = "true"
        )
        GreetingMetrics greetingMetrics() {
            return new GreetingMetrics();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreetingConfiguration {

        @Bean
        CustomGreetingService customGreetingService() {
            return new CustomGreetingService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditConfiguration {

        @Bean
        MemoryAuditSink auditSink() {
            return new MemoryAuditSink();
        }
    }

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class));

    @Test
    void defaultServiceIsCreatedWhenNoUserConfigurationIsAdded() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasSingleBean(DefaultGreetingService.class);
            assertThat(context).doesNotHaveBean(CustomGreetingService.class);
            assertThat(context.getBean(GreetingService.class).message())
                    .isEqualTo("hello from library");
            assertThat(context).doesNotHaveBean(GreetingAuditRecorder.class);
        });
    }

    @Test
    void userConfigurationReplacesTheDefaultService() {
        contextRunner
                .withUserConfiguration(UserGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context).hasSingleBean(CustomGreetingService.class);
                    assertThat(context).doesNotHaveBean(DefaultGreetingService.class);
                    assertThat(context.getBean(GreetingService.class).message())
                            .isEqualTo("hello from application");
                    assertThat(context.getBean("customGreetingService"))
                            .isSameAs(context.getBean(GreetingService.class));
                });
    }

    @Test
    void multipleUserConfigurationsCanBeCombined() {
        contextRunner
                .withUserConfiguration(
                        UserGreetingConfiguration.class,
                        UserAuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(CustomGreetingService.class);
                    assertThat(context).hasSingleBean(AuditSink.class);
                    assertThat(context).hasSingleBean(GreetingAuditRecorder.class);
                    assertThat(context.getBean(GreetingAuditRecorder.class)
                            .destination()).isEqualTo("memory");
                    assertThat(context).doesNotHaveBean(DefaultGreetingService.class);
                });
    }

    @Test
    void userConfigurationCanBeCombinedWithEnvironmentProperties() {
        contextRunner
                .withUserConfiguration(UserGreetingConfiguration.class)
                .withPropertyValues("acme.greeting.metrics.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(CustomGreetingService.class);
                    assertThat(context).hasSingleBean(GreetingMetrics.class);
                    assertThat(context).doesNotHaveBean(DefaultGreetingService.class);
                });
    }

    @Test
    void missingUserDependencyKeepsConditionalBeanDisabled() {
        contextRunner
                .withUserConfiguration(UserGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditSink.class);
                    assertThat(context).doesNotHaveBean(GreetingAuditRecorder.class);
                });
    }
}
~~~

Run in a Gradle project with the test dependency:

~~~bash
./gradlew test --tests "com.example.demo.GreetingAutoConfigurationTests"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.GreetingAutoConfigurationTests"
~~~

Maven:

~~~bash
mvn -Dtest=GreetingAutoConfigurationTests test
~~~

**Expected result:** 5 tests PASS. Assertions verify beans and behavior:
- Without user configuration: default service is created.
- With custom user configuration: default backs off and custom bean is injected.
- With two user configurations: both are added to the context; audit recorder is created because its prerequisite is present.
- User configuration can combine with property values to enable another bean.
- Without an audit sink: the audit-dependent bean does not appear.

The tests are runnable examples under the stated dependency configuration; run them in a project to confirm your specific build environment.

## 7. withUserConfiguration and companion APIs

An auto-configuration test often simulates multiple dimensions of an application. Choose the API matching the kind of input needed in the context:

| API | When to use | Example |
| --- | --- | --- |
| `withUserConfiguration(A.class)` | Application has a `@Configuration` class containing multiple `@Bean`s | Custom service, cache config |
| `withUserConfiguration(A.class, B.class)` | Application has multiple independent configuration groups | Client config + metrics config |
| `withPropertyValues(...)` | Configuration comes from `Environment` | Enable/disable features via properties |
| `withBean(...)` | Need to register a single fixture or mock directly without a configuration class | Mock external gateway |
| `withConfiguration(AutoConfigurations.of(...))` | Load the auto-configuration under test | LibraryAutoConfiguration |
| `withClassLoader(new FilteredClassLoader(...))` | Simulate a dependency absent from the classpath | Testing `@ConditionalOnClass` |
| `withInitializer(...)` | Add a context initializer or listener | Log Condition Evaluation Report |

You do not need to create a `@Configuration` class just to register a single mock bean; `withBean` can be more concise. Conversely, when simulating a slice of production configuration with multiple beans, `withUserConfiguration` makes intent clearer.

## 8. Ordering of user configuration and auto-configuration

One main goal of these tests is confirming that users can replace default beans. With standard auto-configuration, Spring Boot processes user-declared bean definitions before auto-configurations. Hence `@ConditionalOnMissingBean` sees the custom bean and skips the default.

~~~mermaid
flowchart TD
    A["ApplicationContextRunner"] --> B["Load UserGreetingConfiguration"]
    B --> C["Register CustomGreetingService"]
    C --> D["Apply GreetingAutoConfiguration"]
    D --> E{"GreetingService already exists?"}
    E -->|"Yes"| F["Default bean backs off"]
    E -->|"No"| G["Create DefaultGreetingService"]
    F --> H["AssertJ verifies custom bean"]
    G --> I["AssertJ verifies default bean"]
~~~

This is the logical order for understanding bean conditions. Do not rely on calling builder methods before/after each other as an ordering trick; distinguish user configuration and auto-configuration using the proper APIs.

### Why must conditions live in auto-configuration?

`@ConditionalOnMissingBean` relies on bean definitions processed by the time the condition is evaluated. If you place a similar condition on a regular configuration picked up early by component scanning, it may run before the bean it needs to detect.

Spring Boot recommends using bean conditions on auto-configuration classes/methods because auto-configuration is applied after user bean definitions. Testing with `withUserConfiguration` is how you verify this contract in an isolated context.

## 9. Multiple user configurations, bean collisions, and ambiguity

`withUserConfiguration` allows passing multiple classes. That does not mean Spring resolves every conflict automatically:

- If two classes declare beans with the same name, the context may fail due to a bean definition conflict; do not rely on bean overriding.
- If two classes create two beans of the same type and a consumer injects a single-valued dependency, `NoUniqueBeanDefinitionException` can occur if no unambiguous candidate exists.
- `@Primary` can designate a preferred candidate for single-valued injection when multiple matching beans exist; `@Qualifier` can select a bean by qualifier.
- `@ConditionalOnMissingBean` prevents creating the default when a matching bean already exists, but it does not eliminate colliding custom beans of the same type.
- Each test should declare only the user configurations needed for its scenario; avoid stuffing every test fixture into every test, which makes results hard to interpret.

Example of independent user configurations:

~~~java
contextRunner
        .withUserConfiguration(
                UserGreetingConfiguration.class,
                UserAuditConfiguration.class,
                UserMetricsConfiguration.class)
        .run(context -> {
            // Assert beans belonging to this scenario
        });
~~~

If a configuration is only needed in one specific test, do not place it in a shared base runner. Add it via `withUserConfiguration` in the exact test that requires that scenario.

## 10. Inspecting conditions and diagnosing the context

When a test lacks an expected bean, distinguish among:
- User configuration was not added to the runner.
- Auto-configuration was not added to `AutoConfigurations.of(...)`.
- Bean is present, causing the condition to make the default back off.
- Property condition did not match.
- Dependency bean required by the method was not registered.
- Multiple candidates made injection ambiguous.

You can attach `ConditionEvaluationReportLoggingListener`:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(GreetingAutoConfiguration.class))
        .withUserConfiguration(UserGreetingConfiguration.class)
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .run(context -> {
            // Assertions
        });
~~~

Imports:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

The report shows which conditions matched or did not match and why. Combine with AssertJ:
- `hasSingleBean(Type.class)` confirms exactly one matching bean.
- `doesNotHaveBean(Type.class)` confirms the default does not appear.
- `getBean(Type.class)` retrieves the bean to verify behavior.
- `getBean("beanName")` inspects a specific bean by name.

Do not merely assert that the context starts successfully. Auto-configuration can back off unintentionally while the context still starts normally.

## 11. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| `withUserConfiguration` is how you load auto-configuration | Use `AutoConfigurations.of(...)` for auto-configuration; `withUserConfiguration` is for application configuration |
| Passing a class to the runner means its package is scanned | The runner loads the specified source classes; it does not auto-scan packages |
| No user configuration means auto-configuration won't run | The runner still runs auto-configurations added via `withConfiguration` |
| A custom bean of the same type is created alongside the default | `@ConditionalOnMissingBean` causes the default to back off when the condition sees the custom bean |
| Multiple user configurations always merge without conflict | Bean names/types still obey registry and dependency injection rules |
| Varargs class order controls auto-configuration order | Use auto-configuration ordering metadata; do not treat user config argument order as a contract |
| `withPropertyValues` replaces `withUserConfiguration` | One API populates Environment, while the other adds configuration sources |
| Testing with a runner equals running the full `SpringApplication` | The runner builds an isolated context and does not run the main class or full application startup flow |
| Successful context refresh proves all desired beans exist | You must assert both present and absent beans |
| Sharing one base runner means all tests share a context instance | Each `run` creates a context for the callback; the runner is a template for independent test contexts |

## 12. When to use another runner or @SpringBootTest?

`ApplicationContextRunner` fits standard auto-configurations, non-web contexts, and fast scenarios. If conditions depend on the web context type:
- Use `WebApplicationContextRunner` for servlet.
- Use `ReactiveWebApplicationContextRunner` for reactive.

Use `@SpringBootTest` when the goal is testing the application close to production configuration, requiring `SpringApplication` integration, real component scanning, multiple auto-configurations working together, or application startup components. `ApplicationContextRunner` is usually preferable when isolating a single auto-configuration and individual combinations of user configuration/properties/classpath.

One limitation to know: Spring Boot documentation notes that `ApplicationContextRunner` does not work when running tests in a native image. If your project tests native images, choose a testing approach compatible with the project's native workflow.

## 13. Checklist for writing tests with withUserConfiguration

1. Create a base runner and supply auto-configuration via `withConfiguration(AutoConfigurations.of(...))`.
2. Identify which configuration belongs to the application and which belongs to the library.
3. Place user fixtures in `@Configuration(proxyBeanMethods = false)` classes, typically static nested classes.
4. Add the right user configuration via `withUserConfiguration(...)` in each test.
5. If the scenario involves properties, add `withPropertyValues(...)`.
6. If the scenario needs a single mock, consider `withBean(...)`.
7. Assert the default bean, custom bean, and condition-dependent beans.
8. Check whether multiple user configs collide on names/types or cause ambiguity.
9. When conditions are unclear, enable `ConditionEvaluationReportLoggingListener`.
10. Run the tests and verify against the project's actual Spring Boot/JUnit/AssertJ versions.

## 14. Self-check questions

1. Does `withUserConfiguration` accept instances or classes? **It accepts configuration/source classes (one or more classes).**
2. Which API loads auto-configurations? **`withConfiguration(AutoConfigurations.of(...))`.**
3. Why use `@Configuration(proxyBeanMethods = false)` in user fixtures? **To declare an explicit configuration source without proxying bean methods when cross-method calls are not needed.**
4. Can one user configuration declare multiple beans? **Yes**, using multiple `@Bean` methods.
5. Can you pass two user configurations in a single call? **Yes**, because the method accepts class varargs.
6. How do you verify that the default backs off? **Assert the custom bean exists, the default bean does not exist, and retrieving by interface returns the custom implementation.**
7. Can you add properties alongside user configuration? **Yes**, combine with `withPropertyValues`.
8. If two user configs create the same bean type, what can happen? **Ambiguous injection or bean definition conflict depending on names and consumers.**
9. When do you use `WebApplicationContextRunner`? **When the auto-configuration requires a servlet web context.**
10. Can `ApplicationContextRunner` run in native image tests? **No, per the limitation documented in Spring Boot documentation.**

## Official reference documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Testing your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): how to build runners, `AutoConfigurations.of`, `withUserConfiguration`, property values, condition reports, classloaders, and web runners.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html): test modules and the `spring-boot-starter-test` dependency.
- [Spring Boot 3.3 — `ApplicationContextRunner` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): API for creating and customizing test contexts.
- [Spring Boot 3.3 — `AutoConfigurations` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html): registering auto-configuration lists in the runner.
- [Spring Boot 3.3 — `@ConditionalOnMissingBean` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): back-off mechanism based on existing beans.
