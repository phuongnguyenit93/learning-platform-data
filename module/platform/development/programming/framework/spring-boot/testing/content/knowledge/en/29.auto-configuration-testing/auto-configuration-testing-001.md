# Narrow-Scope ApplicationContextRunner for Auto-Configuration in Spring Boot

## 1. Why test auto-configuration with a very small context?

When building a Spring Boot starter or auto-configuration for a library, the main task is not testing a REST controller running on Tomcat. We need to verify **whether Spring creates a bean or not** under each condition: the library exists on the classpath, a property is enabled, the user has already defined their own bean, or a dependent bean is missing.

For example, a starter automatically creates `GreetingService` when all of the following hold simultaneously:
- The application has the `GreetingTransport` class from the optional library.
- `demo.greeting.enabled=true`.
- The user has **not** provided their own `GreetingService`.

If you use `@SpringBootTest` for every branch, Spring Boot may load many unrelated auto-configurations, creating a web server, datasource, security filters, and unrelated beans. Tests become slow, hard to root-cause, and easily affected by the test classpath. **`ApplicationContextRunner`** is provided by Spring Boot to create **a deterministic, minimal, and fresh `ApplicationContext` for each test case**, then automatically close the context when the callback completes.

```text
ApplicationContextRunner
  + AutoConfigurations.of(GreetingAutoConfiguration.class)
  + test-only user configuration (per case)
  + Environment property values (per case)
  + FilteredClassLoader (per case)
          |
          v
   START one narrow ApplicationContext
          |
          v
  Evaluate @ConditionalOnClass / @ConditionalOnProperty
  Evaluate @ConditionalOnMissingBean
  Register only requested configuration / beans
          |
          v
  callback: assert beans, values, failure, conditions
          |
          v
   CLOSE the context after the callback
```

**Key takeaway:** This is testing **auto-configuration conditions and outcomes**, not an end-to-end test of the entire application. Each `run(context -> ...)` invocation has its own context, so you can test many configuration combinations without needing `@DirtiesContext` or sharing state across a single `@SpringBootTest`.

This lesson uses **Java 17+, Spring Boot 3.5.x, Spring Framework 6.x, JUnit Jupiter, AssertJ**. The example includes a complete Gradle project with a custom auto-configuration, a discovery metadata file, a service interface, an optional-class marker, and multiple realistic branch tests. The examples do not require Docker, a network, or a database.

## 2. Concepts to distinguish

| Concept | Role | Common mistake |
|---|---|---|
| `@Configuration` | Regular Spring configuration | Treating it as automatically discovered like Boot auto-configuration in every project |
| `@AutoConfiguration` | Marks a configuration class for Boot's auto-configuration mechanism | Adding the annotation while forgetting to declare the entry in `AutoConfiguration.imports` |
| `@ConditionalOnClass` | Applies only when the required class/library is present | Using the optional class directly where the JVM must load the class before the condition runs |
| `@ConditionalOnProperty` | Constrains based on an `Environment` value | Assuming property presence means enabled even when `havingValue` differs |
| `@ConditionalOnMissingBean` | Backs off in favor of a user-defined bean | Evaluating the condition before user beans are known |
| `@ConditionalOnBean` | Creates a bean only when a dependency bean is already defined | Testing based on unstable registration order |
| `ApplicationContextRunner` | Creates/closes a small context per scenario | Expecting it to boot all auto-configurations like `@SpringBootTest` |
| `AutoConfigurations.of(...)` | Loads the specified auto-configurations in the runner | Thinking it equates to testing the `AutoConfiguration.imports` file |
| `withUserConfiguration(...)` | Loads "application user" bean configuration | Putting custom beans in auto-config and failing to test back-off |
| `withPropertyValues(...)` | Adds properties only for the current scenario | Mutating global system properties or sharing `Environment` |
| `FilteredClassLoader` | Simulates missing class/package on the classpath | Removing the real dependency from the build for all tests |
| `WebApplicationContextRunner` | Used when conditions require a Servlet web context | Using the plain runner and seeing web-only configuration always fail |
| `ReactiveWebApplicationContextRunner` | Used when conditions require a Reactive web context | Confusing it with the servlet `WebApplicationContextRunner` |
| `ConditionEvaluationReport` | Explains which conditions matched/did not match | Reading a missing-context exception without checking the condition report |

### 2.1. `ApplicationContextRunner` is not `@SpringBootTest`

`@SpringBootTest` boots a Spring Boot application according to the real application configuration. It is suitable for testing components integrated together. In contrast, `ApplicationContextRunner` typically creates only a context containing **explicitly declared auto-configurations and user configurations**.

This brings three benefits:
1. **Speed and isolation:** No HTTP server, datasource, or security needed when unrelated.
2. **Determinism:** Each scenario has its own properties, classpath, and bean definitions.
3. **Condition diagnostics:** Easy to see which condition caused a bean to be created or omitted.

However, there are also limitations: passing runner tests **does not automatically guarantee** that all auto-configurations across a full Spring Boot app are compatible, that discovery metadata in the JAR is packaged properly, or that a real server can start. Additional integration/smoke tests are needed when the project requires those guarantees.

## 3. Essential ApplicationContextRunner API

In Spring Boot 3.5, primary imports:

```java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
```

Creating a base runner:

```java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                GreetingAutoConfiguration.class));
```

This is a fragment inside a JUnit class, with a real `GreetingAutoConfiguration`. `ApplicationContextRunner` is configured with methods that **return a runner with extended configuration**; not every call runs a context by itself.

### 3.1. A workflow that reads like a specification

```java
runner
    .withPropertyValues(
        "demo.greeting.enabled=true",
        "demo.greeting.prefix=Greetings")
    .run(context -> {
        assertThat(context)
            .hasSingleBean(GreetingService.class);

        GreetingService service =
            context.getBean(GreetingService.class);

        assertThat(service.greet("An"))
            .isEqualTo("Greetings, An");
    });
```

This is a fragment inside a test class that has imports, the runner, and the interface/implementation. `withPropertyValues` puts key/value pairs into the scenario's `Environment`; `run` creates the context, supplies the `AssertableApplicationContext` callback, and then closes the context.

**Do not retain beans/context outside the callback** to use after `run`: they belong to a context that has already been closed. If you need to test steps on a bean, perform assertions inside the callback.

### 3.2. Commonly used methods

| API | Purpose |
|---|---|
| `new ApplicationContextRunner()` | Initializes the runner |
| `.withConfiguration(AutoConfigurations.of(MyAutoConfiguration.class))` | Selects the exact auto-config under test |
| `.withUserConfiguration(UserConfiguration.class)` | Registers beans/configuration supplied by the application |
| `.withPropertyValues("feature.enabled=true")` | Simulates environment/config properties |
| `.withClassLoader(new FilteredClassLoader(OptionalType.class))` | Simulates an absent class |
| `.withInitializer(...)` | Adds an initialization hook, e.g., condition report logger |
| `.run(context -> { ... })` | Creates an isolated context, asserts beans/failures, auto-closes |
| `assertThat(context).hasSingleBean(Type.class)` | Verifies there is exactly one bean of this type |
| `assertThat(context).doesNotHaveBean(Type.class)` | Verifies no bean of this type was created |
| `context.getBean(Type.class)` | Reads the bean to assert behavior |
| `context.getStartupFailure()` | Retrieves the exception when context startup fails |

The `hasSingleBean` and `doesNotHaveBean` assertions are AssertJ utilities for `AssertableApplicationContext`, distinct from just calling `context.getBeansOfType(...)` and counting. A good test usually asserts **both presence/absence and behavior/value**, not just the bean count.

## 4. Designing a mini auto-configuration with three conditions

We create an auto-configuration for a greeting feature. It is enabled **only when**:
- The `com.example.mini.optional.GreetingTransport` class is present.
- The `demo.greeting.enabled` property has the exact value `true`.
- There is no other `GreetingService` bean.

When enabled, the bean is created from the `demo.greeting.prefix` property, defaulting to `Hello`. If the user has already defined `GreetingService` in the application, the auto-config **backs off** without overriding it.

```text
                       Auto-configuration is specified
                                      |
                     Is GreetingTransport on classpath?
                         /                   \
                        No                   Yes
                        |                     |
                   No bean created     enabled == "true"?
                                          /         \
                                         No         Yes
                                         |           |
                                    No bean     User GreetingService
                                    created       already exists?
                                                 /       \
                                               Yes        No
                                                |          |
                                           Back off    Create default
                                           user bean  GreetingService
```

This is a **decision diagram**, not a new rule engine. The actual order and behavior are executed by Spring Boot conditions during the registration/configuration phase. We verify each branch with tests rather than assuming annotations are already right.

## 5. Complete Java 17+ / Spring Boot 3.5.x project

### 5.1. File structure

```text
build.gradle
src/main/java/com/example/demoapp/
    RunnerDemoApplication.java
src/main/java/com/example/mini/api/
    GreetingService.java
    DefaultGreetingService.java
src/main/java/com/example/mini/optional/
    GreetingTransport.java
src/main/java/com/example/mini/autoconfigure/
    GreetingAutoConfiguration.java
src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
src/test/java/com/example/mini/autoconfigure/
    GreetingAutoConfigurationTest.java
```

In the sample project, the `GreetingTransport` marker is placed in the same source set so everything compiles and runs independently with Spring Boot dependencies. **In a real starter**, it is usually a class from **an optional library in another module/JAR**, and the auto-config module must handle safely when the optional JAR is absent. `FilteredClassLoader` in tests will simulate that exact situation.

Place the main application in package `com.example.demoapp`, and the auto-configuration in `com.example.mini.autoconfigure`. This avoids having the demo app's component scanning automatically scan `GreetingAutoConfiguration`, ensuring that only the **auto-configuration imports** mechanism controls registration in the app. Runner tests will register the auto-config explicitly, independent of the main class.

### 5.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` brings Spring Core/Boot auto-configuration infrastructure, while starter-test provides JUnit Jupiter/AssertJ/Spring Boot test runner. The `spring-boot-autoconfigure-processor` annotation processor can generate condition metadata to support early filtering; it **does not replace** the `AutoConfiguration.imports` file and is not required for the core runtime logic of the example.

The example does not depend on `starter-web`, `starter-data-jpa`, security, DB, or Testcontainers. Avoiding unrelated dependencies also helps illustrate the true **narrow scope** of `ApplicationContextRunner`.

### 5.3. Spring Boot main class

File `src/main/java/com/example/demoapp/RunnerDemoApplication.java`:

```java
package com.example.demoapp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RunnerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RunnerDemoApplication.class, args);
    }
}
```

The main class allows running the demo app with `bootRun` when a smoke test is needed, but `ApplicationContextRunner` unit/integration tests **do not boot main**. Since there is no web starter, main does not start an HTTP server.

### 5.4. Service contract

File `src/main/java/com/example/mini/api/GreetingService.java`:

```java
package com.example.mini.api;

@FunctionalInterface
public interface GreetingService {

    String greet(String name);
}
```

File `src/main/java/com/example/mini/api/DefaultGreetingService.java`:

```java
package com.example.mini.api;

import java.util.Objects;

public final class DefaultGreetingService
        implements GreetingService {

    private final String prefix;

    public DefaultGreetingService(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    @Override
    public String greet(String name) {
        return prefix + ", " + Objects.requireNonNull(name);
    }
}
```

Tests verify both the bean type and the exact result, for example `Hello, An` and `Greetings, An`, rather than merely asserting that `ApplicationContext` started.

### 5.5. Optional-class marker

File `src/main/java/com/example/mini/optional/GreetingTransport.java`:

```java
package com.example.mini.optional;

/**
 * Marker representing an optional dependency in the example.
 */
public final class GreetingTransport {

    private GreetingTransport() {
    }
}
```

In a real application, this class could be the actual API/driver of a library supported by auto-configuration. Using the class name in the condition avoids a hard dependency when the optional module is absent.

### 5.6. Auto-configuration class

File `src/main/java/com/example/mini/autoconfigure/GreetingAutoConfiguration.java`:

```java
package com.example.mini.autoconfigure;

import com.example.mini.api.DefaultGreetingService;
import com.example.mini.api.GreetingService;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(
        name = "com.example.mini.optional.GreetingTransport")
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService(
            @Value("${demo.greeting.prefix:Hello}") String prefix) {
        return new DefaultGreetingService(prefix);
    }
}
```

**Exact breakdown:**

- `@AutoConfiguration` identifies a configuration managed by Boot's auto-config mechanism.
- `@ConditionalOnClass(name=...)` is evaluated at the **class level** and uses a String name for the optional type; if the marker is hidden by `FilteredClassLoader`, the auto-config class is not applied.
- `@ConditionalOnProperty(... havingValue="true", matchIfMissing=false)` means the property must **be present and match the value true**. Missing property, false, or any other string will not activate it.
- `@ConditionalOnMissingBean(GreetingService.class)` lets the default bean **back off** in favor of a bean of the same type defined by the user.
- `@Value("${demo.greeting.prefix:Hello}")` uses `Hello` when the `demo.greeting.prefix` property is not provided. The prefix property does not decide whether auto-config is **enabled**; `enabled` is the activation flag.

**Note on classpath safety:** If a `@Bean` method directly returns a type that only exists in an optional dependency, the JVM may need to load the return type before the condition on the method is evaluated. For those cases, wrap the optional beans in a nested `@Configuration` annotated with `@ConditionalOnClass` to isolate class loading. This example returns `GreetingService`, which belongs to the project itself, so it does not have that risk.

### 5.7. AutoConfiguration.imports for production discovery

Exact file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

**File contents** (one fully qualified class name per line):

```text
com.example.mini.autoconfigure.GreetingAutoConfiguration
```

This is the discovery convention of **Spring Boot 3.x**. When building a real starter JAR, the file must be packaged under `META-INF/spring/` of the artifact. When `@SpringBootApplication` enables auto-configuration, Boot reads this list and evaluates conditions.

**Critical QA point:** A test using `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(GreetingAutoConfiguration.class))` registers the class explicitly; it **does not prove** that the `AutoConfiguration.imports` file is present in the JAR. Therefore:
- Use runner tests to verify actual condition/bean logic.
- Add a metadata/JAR packaging check or a full-application auto-discovery smoke test if the starter will be published.
- Do not treat a passing runner test as proof that production consumers can definitely auto-import it.

This is not the old `spring.factories` style of auto-configuration. In Boot 3.x, declaring auto-configs via `AutoConfiguration.imports` is the approach documented by Boot.

## 6. Complete JUnit 5 class with ApplicationContextRunner

File `src/test/java/com/example/mini/autoconfigure/GreetingAutoConfigurationTest.java`:

```java
package com.example.mini.autoconfigure;

import com.example.mini.api.DefaultGreetingService;
import com.example.mini.api.GreetingService;
import com.example.mini.optional.GreetingTransport;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.logging
        .ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class));

    @Test
    void disabledWhenPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context)
                    .doesNotHaveBean(GreetingService.class);
        });
    }

    @Test
    void disabledWhenPropertyIsFalse() {
        runner.withPropertyValues(
                "demo.greeting.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void disabledWhenPropertyHasUnexpectedValue() {
        runner.withPropertyValues(
                "demo.greeting.enabled=enabled")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void enabledPropertyCreatesExactlyOneDefaultBean() {
        runner.withPropertyValues(
                "demo.greeting.enabled=true")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                    assertThat(context)
                            .hasBean("greetingService");

                    GreetingService service =
                            context.getBean(GreetingService.class);

                    assertThat(service)
                            .isInstanceOf(
                                    DefaultGreetingService.class);
                    assertThat(service.greet("An"))
                            .isEqualTo("Hello, An");
                });
    }

    @Test
    void customPrefixIsResolvedFromEnvironment() {
        runner.withPropertyValues(
                "demo.greeting.enabled=true",
                "demo.greeting.prefix=Greetings")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                    assertThat(
                            context.getBean(GreetingService.class)
                                    .greet("An"))
                            .isEqualTo("Greetings, An");
                });
    }

    @Test
    void userDefinedBeanWinsOverDefaultAutoBean() {
        runner.withUserConfiguration(
                CustomGreetingConfiguration.class)
                .withPropertyValues(
                    "demo.greeting.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                    assertThat(context)
                            .hasBean("customGreetingService");
                    assertThat(context)
                            .doesNotHaveBean("greetingService");

                    GreetingService service =
                            context.getBean(GreetingService.class);
                    assertThat(service.greet("An"))
                            .isEqualTo("Custom, An");
                });
    }

    @Test
    void optionalClassAbsentDisablesAutoConfiguration() {
        runner.withPropertyValues(
                "demo.greeting.enabled=true")
                .withClassLoader(
                        new FilteredClassLoader(
                                GreetingTransport.class))
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context)
                            .doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void optionalClassMissingDoesNotDeleteUserBean() {
        runner.withUserConfiguration(
                CustomGreetingConfiguration.class)
                .withPropertyValues(
                    "demo.greeting.enabled=true")
                .withClassLoader(
                        new FilteredClassLoader(
                                GreetingTransport.class))
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                    assertThat(context)
                            .hasBean("customGreetingService");
                    assertThat(context)
                            .doesNotHaveBean("greetingService");
                });
    }

    @Test
    void runnerVariantsDoNotLeakPropertiesBetweenRuns() {
        runner.withPropertyValues(
                "demo.greeting.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                });

        runner.run(context -> {
            assertThat(context)
                    .doesNotHaveBean(GreetingService.class);
        });
    }

    @Test
    void startupFailureCanBeAssertedWithoutFullBootTest() {
        runner.withUserConfiguration(
                FailingUserConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    IllegalStateException.class);
                });
    }

    @Test
    void conditionReportCanBePrintedForDiagnosis() {
        runner.withPropertyValues(
                "demo.greeting.enabled=true")
                .withInitializer(
                    ConditionEvaluationReportLoggingListener
                        .forLogLevel(LogLevel.INFO))
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return name -> "Custom, " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class FailingUserConfiguration {

        @Bean
        String failingStartupBean() {
            throw new IllegalStateException(
                    "Intentional startup failure");
        }
    }
}
```

The code above defines **11 `@Test` cases** in one class, each creating a separate context via the runner. The imports `ApplicationContextRunner`, `AutoConfigurations`, `FilteredClassLoader`, and `ConditionEvaluationReportLoggingListener` are the APIs officially documented by Spring Boot for auto-configuration testing.

**Note on Java import syntax in documentation:** In the code fence above, the `ConditionEvaluationReportLoggingListener` import was line-wrapped for display. When copying into a Java file, **use a single import line** as follows so it compiles cleanly:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
```

Wrapping across segments of a qualified import in Java may still be valid by tokenization if whitespace separates tokens appropriately, but **the single-line version above is clearest and safest**. The remaining imports do not depend on Spring Boot test extensions or Mockito mocking.

### 6.1. Why are these 11 tests sufficient for the demo scope?

| Case | Branch verified | Meaning |
|---|---|---|
| `disabledWhenPropertyIsMissing` | Property absent | `matchIfMissing=false` actually takes effect |
| `disabledWhenPropertyIsFalse` | enabled=false | No unintended bean created |
| `disabledWhenPropertyHasUnexpectedValue` | enabled other than true | `havingValue="true"` is not interpreted as any value other than false |
| `enabledPropertyCreatesExactlyOneDefaultBean` | All conditions true simultaneously | Default bean is created with right type and behavior |
| `customPrefixIsResolvedFromEnvironment` | Non-default property | Environment value is injected |
| `userDefinedBeanWinsOverDefaultAutoBean` | User bean exists | `@ConditionalOnMissingBean` backs off |
| `optionalClassAbsentDisablesAutoConfiguration` | Library missing | Negative `@ConditionalOnClass` |
| `optionalClassMissingDoesNotDeleteUserBean` | Library missing but user bean exists | Auto-config is disabled without losing user config |
| `runnerVariantsDoNotLeakPropertiesBetweenRuns` | Independent runner instances | No property leakage from previous scenario |
| `startupFailureCanBeAssertedWithoutFullBootTest` | Bean initialization throws error | Runner captures startup failure in callback |
| `conditionReportCanBePrintedForDiagnosis` | Diagnostics | Logs condition evaluation at INFO when needed |

The assertions belong to **Java/AssertJ**, and there is no fixed stdout. One test uses the condition report logger, which emits logs depending on logger config; **we do not** provide a fabricated "expected console transcript" because log level, framework version, and order depend on the environment.

### 6.2. What proves the auto-config truly creates the right bean?

An assertion `assertThat(context).hasSingleBean(GreetingService.class)` only proves count/type. Combine:
- `hasBean("greetingService")` for the default bean name.
- `isInstanceOf(DefaultGreetingService.class)` for the implementation.
- `service.greet("An") == "Hello, An"` for behavior.
- Custom bean test confirming the default bean is absent and the custom bean still works.

This is an appropriate level of evidence for **bean creation/conditions**, though it still does not prove that an external HTTP/MQ/client resource can actually connect.

## 7. Common misconception: "A single @SpringBootTest is enough"

A `@SpringBootTest` with `demo.greeting.enabled=true` may pass, yet fail to answer:
- When the property is not configured, is a default bean created unintentionally?
- When the user registers `GreetingService`, does auto-config back off or fail with bean ambiguity?
- When the optional dependency is missing, can the context still start?
- When changing the prefix property, does the bean actually receive the new value?
- When bean init throws an exception, does the test verify the exact root cause?
- When running multiple configurations, does state leak through the context cache?

`ApplicationContextRunner` solves those cases with small contexts instead of refreshing a large application multiple times. **Do not push all conditional branches into `@SpringBootTest`** when you only need to verify auto-configuration.

### 7.1. Be careful when testing user bean back-off

If you just invoke the factory method directly yourself:

```java
GreetingAutoConfiguration configuration =
        new GreetingAutoConfiguration();

GreetingService service =
        configuration.greetingService("Hello");
```

This is an illustrative snippet in a test with project dependencies. It **does not** run `@ConditionalOnMissingBean`, does no condition evaluation, and performs no `Environment` resolution. It only tests a plain Java factory method.

Proper proof is having the runner create a context with `CustomGreetingConfiguration`, then asserting only **one user bean** and no default `greetingService`. When auto-configuration is loaded properly, it is evaluated after user bean definitions, making the back-off condition meaningful.

### 7.2. Classpath-safe conditions do not make all code safe

Using:

```java
@ConditionalOnClass(name = "com.example.optional.ExternalClient")
class ExternalClientAutoConfiguration {
}
```

This is an illustrative fragment. Evaluating a class condition from annotation metadata lets Spring Boot avoid loading the optional class directly. However, if method parameter/return types, static initializers, or field signatures of the auto-config **force the JVM to load the optional class too early**, startup can still fail with `NoClassDefFoundError` despite the declared condition.

Safer pattern:

```java
@AutoConfiguration
public class OptionalClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.example.optional.ExternalClient")
    static class ExternalClientConfiguration {
        // @Bean methods can reference ExternalClient
        // inside a configuration class loaded only if the class is present.
    }
}
```

This is an illustrative snippet without a real library. For complex optional modules, build separate nested `@Configuration` classes to isolate class loading, then test the absent branch with `FilteredClassLoader`.

## 8. @ConditionalOnProperty: more precise than a boolean assumption

Spring Boot's `@ConditionalOnProperty` has semantics that must be read accurately:
- If **`havingValue` is not declared**, the condition matches by default when the property is present and not the string `false` (it is not simply `Boolean.parseBoolean`).
- With `havingValue="true"`, only a value corresponding to true matches the condition.
- `matchIfMissing=true` allows the condition to match when the property is absent; this lesson deliberately uses `false`.
- Using multiple `name` entries in a single annotation requires **all** named properties to match.
- For collection/indexed properties, `@ConditionalOnProperty` is not a matcher for every entry in the Binder; use a custom condition if the logic is complex.

Therefore, testing missing, false, true, and unexpected values is very useful. Having only a `true` case will miss an auto-config that accidentally activates when the property is missing.

### 8.1. Should you use @ConfigurationProperties instead of @Value?

In larger starters, `@ConfigurationProperties` is usually a better fit than `@Value`:
- Provides type-safe binding, default values, and validation.
- Generates metadata supporting autocomplete.
- Makes it easy to separate property names, default values, and constraints from the bean factory method.
- Supports `Duration`, `DataSize`, enums, and collections via the Spring Boot binder.

**Illustrative** example of a properties object type:

```java
@ConfigurationProperties(prefix = "demo.greeting")
public class GreetingProperties {

    private boolean enabled;
    private String prefix = "Hello";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
```

This is an illustrative Java class if placed in `GreetingProperties.java` with `import org.springframework.boot.context.properties.ConfigurationProperties`. It is **not part of the runnable project in section 5**, because the project uses simple `@Value` to focus on conditional logic.

If switching to `@ConfigurationProperties`, register it explicitly (for example `@EnableConfigurationProperties(GreetingProperties.class)` in the auto-config), and add `withPropertyValues` tests verifying binder type conversion/validation. Do not just put the annotation on a POJO and assume the bean will automatically appear in an `ApplicationContextRunner` that does not scan components.

## 9. @ConditionalOnBean, @ConditionalOnMissingBean, and ordering

These two conditions depend on **the bean definitions already known to Spring at evaluation time**. For auto-configurations, Boot orders them after user configurations and applies ordering metadata when needed.

```java
@AutoConfiguration(after = DependencyAutoConfiguration.class)
class FeatureAutoConfiguration {
    // Creates a bean depending on a bean created by DependencyAutoConfiguration.
}
```

This is an illustrative fragment; it needs the `DependencyAutoConfiguration` class and appropriate imports. With real Boot auto-config modules, you can use `@AutoConfiguration(before=...)`/`after=...` or `beforeName`/`afterName` to adjust definition ordering, **not** the instantiation order of every bean.

**Important:** `AutoConfigurations.of(A.class,B.class)` causes the auto-configurations in the runner to be ordered the same way Boot does in an application; do not rely on manual argument order when production code uses ordering annotations.

### 9.1. Dependency bean test pattern

For an auto-config that only creates a `SomeClient` bean when `SomeTransport` is present, there should usually be two cases:
1. Context **without `SomeTransport`** -> does not create `SomeClient`.
2. `withUserConfiguration(TransportConfiguration.class)` registers `SomeTransport` -> creates one `SomeClient`.

You should assert the bean type and actual dependency, rather than only testing `applicationContext.containsBeanDefinition("someClient")`. If the user has **multiple** candidates, `@ConditionalOnSingleCandidate` or `@Primary` may decide bean selection; test ambiguity/primary semantics if the auto-config depends on a single candidate.

## 10. @ConditionalOnClass: simulating a missing dependency with FilteredClassLoader

There is no need to remove a dependency from `build.gradle` and edit it back between tests. `FilteredClassLoader` is a Boot helper to **hide classes/packages from the classloader used by the runner**:

```java
runner
    .withClassLoader(
        new FilteredClassLoader(GreetingTransport.class))
    .withPropertyValues(
        "demo.greeting.enabled=true")
    .run(context -> {
        assertThat(context)
            .doesNotHaveBean(GreetingService.class);
    });
```

This scenario is important for starters supporting optional libraries such as:
- `DataSource`/JDBC drivers.
- Kafka producer/consumer clients.
- Redis clients.
- OpenTelemetry or tracing providers.
- Jackson modules, HTTP client implementations.
- Micrometer registries.
- Cache providers or messaging SDKs.

Not every library needs `FilteredClassLoader`. Use it only when **class presence/absence** is part of the condition contract. If you only need to test a property, `withPropertyValues` is sufficient and clearer.

### 10.1. Avoiding misleading tests against the runner's actual classpath

If an optional dependency is not on the test classpath, the **positive case** cannot prove the bean is created because the classpath condition is absent. Conversely, if the dependency is always present, it is hard to prove the **negative case** unless you filter the classloader.

In the example, we have a real marker class for the positive case to run, and `FilteredClassLoader(GreetingTransport.class)` for the negative case to run on the **same build**, rather than two separate Gradle environments. That is the strength of `ApplicationContextRunner`.

### 10.2. Class loading does not mean the class is used successfully

`@ConditionalOnClass` only checks that the class is present. It **does not** prove:
- The JDBC driver can connect to the database.
- The Kafka broker is reachable.
- An external SDK key is valid.
- The bean is fully initialized in all cases if custom conditions remain.
- The dependency's binary version is compatible across all method calls.

Those concerns require additional bean initialization assertions, contract tests, or integration tests with real resources. Do not turn a classpath check into an end-to-end claim.

## 11. Differences between plain, Servlet, and Reactive context runners

`ApplicationContextRunner` creates a **context with no web assumptions** by default. If an auto-config has:

```java
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
```

then the plain runner will normally **not activate** the Servlet branch. Use:

```java
WebApplicationContextRunner webRunner =
        new WebApplicationContextRunner()
                .withConfiguration(
                    AutoConfigurations.of(
                        MyServletAutoConfiguration.class));
```

Or for a reactive web context:

```java
ReactiveWebApplicationContextRunner reactiveRunner =
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(
                    AutoConfigurations.of(
                        MyReactiveAutoConfiguration.class));
```

The two snippets above are **illustrative** and require:
- Importing `org.springframework.boot.test.context.runner.WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner`.
- Real auto-config classes and relevant Servlet/WebFlux dependencies.
- Assertions inside `run(...)` to verify beans/conditions.

Using the **right context type** is necessary because `@ConditionalOnWebApplication` may inspect context type, scope, and environment, and should not be forced to "pass" by mocking an unrelated bean.

### 11.1. When is a web runner not needed?

If the auto-configuration only creates `GreetingService`, a JSON serializer, a clock abstraction, or a client that does not depend on a servlet/reactive web context, `ApplicationContextRunner` is usually the most accurate choice. Adding a web runner may load unnecessary infrastructure, pulling the test outside its original narrow scope.

If the auto-config needs `MockMvc`/controller mappings/HTTP filter chains, you are testing a broader web scope; consider `WebApplicationContextRunner`, `@WebMvcTest`, or `@SpringBootTest` depending on the goal.

## 12. Diagnosing conditions with ConditionEvaluationReport

A common issue: the context starts, yet the bean **does not appear**. This can happen because:
- `@ConditionalOnClass` did not match.
- `@ConditionalOnProperty` is absent or has the wrong value.
- An existing user bean caused `@ConditionalOnMissingBean` to back off.
- Multiple candidates caused `@ConditionalOnSingleCandidate` not to match.
- `@ConditionalOnWebApplication` ran in the wrong context type.
- The auto-configuration was not added to the runner.
- The bean was excluded by a condition on a nested configuration class.

**Do not fix the test by haphazardly `@Import`-ing the expected bean** and asserting it exists, because doing so can bypass the exact condition under test.

### 12.1. Enabling condition report logging for a scenario

Spring Boot includes `ConditionEvaluationReportLoggingListener`. Usage in a runner:

```java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(GreetingAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener
            .forLogLevel(LogLevel.INFO))
    .withPropertyValues(
        "demo.greeting.enabled=false")
    .run(context -> {
        assertThat(context)
            .doesNotHaveBean(GreetingService.class);
    });
```

This is a JUnit fragment with static imports and the demo class. The listener is officially documented by Spring Boot to print evaluation results at INFO/DEBUG. Do not dump full condition reports on every CI test when they are too long; enable them only for debugging cases or appropriate logging levels.

### 12.2. Understanding "positive matches" and "negative matches"

In the report:
- **Positive match**: a configuration's condition was satisfied.
- **Negative match**: a condition was not satisfied, with a reason message.
- A class-level condition mismatch can cause **the entire auto-config class to be skipped**, not just a single `@Bean`.
- A negative `@ConditionalOnMissingBean` **can be the right behavior**, because the user already registered a bean.

Do not treat "negative matches" as a list of bugs. A good starter intentionally **does not create beans** when a property is disabled, a dependency is absent, or a user overrides it — and those negative branches must be tested.

### 12.3. Startup failure differs from a bean not being created

**Two very different outcomes:**

- Context starts normally, `GreetingService` **does not exist** because a condition did not match: an expected behavior.
- Context **fails to start**, e.g., constructor/factory method throws an exception, bean ambiguity, config binding error: inspect `getStartupFailure()` and root cause.

`ApplicationContextRunner.run` lets the callback observe startup failure instead of failing the test class during Spring test context bootstrap like a failing `@SpringBootTest`.

For example, `startupFailureCanBeAssertedWithoutFullBootTest` in the code above checks `hasFailed()` and the `IllegalStateException` root cause intentionally produced by `FailingUserConfiguration`. It does not turn a startup failure into "auto-config disabled" behavior; the two states must be kept strictly separate.

## 13. Test matrices cover every condition without duplicating code

With three main conditions, the basic matrix:

| Class `GreetingTransport` | enabled | User `GreetingService` | Expected |
|---|---|---|---|
| Present | Not declared | No | No bean |
| Present | false | No | No bean |
| Present | Value other than true | No | No bean |
| Present | true | No | **One DefaultGreetingService** |
| Present | true | Yes | **One custom bean**, default backs off |
| Absent | true | No | No bean |
| Absent | true | Yes | **One custom bean**, auto-config disabled |
| Present | true + custom prefix | No | Default bean with prefix from Environment |
| Present | true then new scenario without property | No | Two independent contexts, no property leak |

This matrix focuses on **meaningful outcomes** rather than generating useless combinations. For a real starter, expand along:
- Whether there is one dependency bean or multiple candidates.
- `@Primary` present/absent.
- Enabled property missing/false/true/malformed.
- Class present/absent.
- Servlet vs Reactive vs non-web context.
- Native-image vs JVM behavior if the product must support it.
- External client configuration missing/broken credentials.
- Application custom bean replacing the default.

**Avoid overly rigid testing of implementation details:** Sometimes a bean name is considered a public contract (e.g., `"taskExecutor"`), in which case asserting the name makes sense. When the name is just an internal detail, prefer asserting **type, count, and behavior** to prevent tests from failing during functionality-preserving refactors.

## 14. Runner immutability and isolation between cases

Methods like `withPropertyValues`, `withUserConfiguration`, and `withClassLoader` typically create **a copy of the runner configuration** and return it for chaining. Therefore:

```java
ApplicationContextRunner base =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    GreetingAutoConfiguration.class));

base.withPropertyValues(
        "demo.greeting.enabled=true")
    .run(ctx -> assertThat(ctx)
        .hasSingleBean(GreetingService.class));

base.run(ctx -> assertThat(ctx)
        .doesNotHaveBean(GreetingService.class));
```

The two calls above do not share an `ApplicationContext`, and `base` is not mutated to `enabled=true` by the previous scenario's `withPropertyValues`. That is why you can place the runner as a `private final` field in the test class and create readable variants from it.

**Point to remember:** Context isolation does not automatically make every dependency stateless. If bean code writes to **static mutable fields, shared files, singletons outside Spring, system properties, or a shared database**, those side effects can still leak between runs. `ApplicationContextRunner` closes the Spring context; it does not arbitrarily wipe every external resource.

If an auto-config creates a thread pool, scheduler, or TCP client, ensure the bean has a shutdown lifecycle (`DisposableBean`, `@PreDestroy`, Spring-recognized `AutoCloseable`, or a custom destroy method). The runner closes the context after the callback, so resource cleanup can be verified when needed.

## 15. AutoConfigurations.of and ordering of multiple auto-configurations

Many starters have dependencies between auto-configurations:
- Metrics auto-config needs a registry.
- Repository auto-config needs a datasource.
- HTTP client auto-config needs a codec/client factory.
- Cache auto-config depends on a cache provider.
- Security filter registration depends on security infrastructure.

In a runner, you can pass multiple classes to `AutoConfigurations.of(A.class, B.class)`; Spring Boot applies ordering metadata just as in an application. If a bean condition depends on a bean from another auto-config, use `@AutoConfiguration(after=...)` or `before=...` as needed.

**Do not confuse auto-config bean definition ordering with bean instantiation order**. `@DependsOn` or constructor injection resolves initialization relationships, whereas `@AutoConfiguration(after=...)` primarily affects the order in which **definitions are processed / conditions are evaluated**.

A good test practice:
1. Runner with only the dependent auto-config -> confirm the bean is not created if the dependency is missing.
2. Runner with both the dependency auto-config and dependent auto-config -> confirm the bean is created.
3. Runner with a custom user bean replacing the dependency -> confirm proper back-off/conditional behavior.
4. Check the condition report when results differ from expectations.

When `@ConditionalOnBean` is placed on a regular application configuration class instead of an auto-config, evaluation may happen before certain required bean definitions exist. That is why Boot documentation recommends using bean conditions primarily in **auto-configurations** where ordering is controlled.

## 16. Test failures: do not "fix" by unnecessarily widening scope

Some failure modes:

| Symptom | Possible cause | Fix |
|---|---|---|
| `doesNotHaveBean` despite enabled property | Optional class filtered/absent, wrong user context, another condition negative | Check classpath and ConditionEvaluationReport |
| `hasSingleBean` fails due to 2 beans | `@ConditionalOnMissingBean` missing/wrong type, custom beans registered too late | Place condition properly, test back-off |
| Default bean still created when disabled | `@ConditionalOnProperty` has wrong prefix/name/havingValue | Test missing/false/non-true |
| Prefix property always "Hello" | Reading wrong key or `@Value` has no property | Assert `withPropertyValues` affects bean behavior |
| FilteredClassLoader does not make condition negative | Condition in wrong place, wrong name, or test loads class another way | Use class-level condition, check report |
| `NoClassDefFoundError` when optional lib absent | Method/field signature referencing optional class loaded too early | Nested conditional configuration |
| Custom user bean does not win | User config not added to runner, bean type mismatch | `withUserConfiguration` with right class and type |
| Runner tests pass but starter does not auto-activate in app | Missing/wrong `AutoConfiguration.imports` in JAR | Check resources/JAR packaging and smoke test |
| Startup failure when configuration property missing | Bean cannot resolve/bind required property | Assert `getStartupFailure`, validate/define defaults |
| `@ConditionalOnWebApplication` never matches | Using plain ApplicationContextRunner for web-only config | WebApplicationContextRunner/Reactive...Runner |
| Test passes alone, fails in suite | Shared system properties/static mutable state/external resources | Use runner per scenario, avoid global side effects |
| Changing auto-config ordering makes bean disappear | `@ConditionalOnBean` evaluated before dependency | `@AutoConfiguration` after/before and test both classes |
| Context starts very slowly | Runner accidentally imports entire app/all auto-configurations | Pass only relevant classes to `AutoConfigurations.of` |
| Native executable test has different runtime | ApplicationContextRunner does not support running tests in native image | Test on JVM, add native smoke tests if needed |
| ConditionEvaluationReport logs too long | INFO listener enabled for every test | Enable only when debugging specific cases |
| Bean created but errors when calling service | Condition only checks class/property, does not test external client | Add integration test against real dependency |
| `@SpringBootTest` errors hard to trace | Boots many unrelated auto-configs | Extract runner tests for condition-specific logic |

### 16.1. Anti-patterns to avoid

**Anti-pattern 1 — calling the factory method directly.** This bypasses Spring conditional evaluation.

**Anti-pattern 2 — using `@SpringBootTest` for every enabled/disabled combination.** Booting the entire app makes tests slower and noisier.

**Anti-pattern 3 — asserting a bean by name while ignoring type/behavior.** You could grab the wrong bean sharing a name but with a different implementation in complex configs.

**Anti-pattern 4 — mocking the auto-config class itself.** Testing a mock does not verify the real auto-configuration's conditions or registration.

**Anti-pattern 5 — stripping the optional dependency from the entire build to test missing-class.** Use `FilteredClassLoader` to test both positive/negative cases within the same test suite.

**Anti-pattern 6 — confusing a runner test with a discovery test.** `AutoConfigurations.of` puts the class directly into the runner without reading the imports file like normal deployment.

**Anti-pattern 7 — retaining a bean after the callback.** Once the context is closed, the bean may hold resources that are no longer valid.

**Anti-pattern 8 — expecting the runner to be a native-image test runner.** Boot docs state `ApplicationContextRunner` does not work when running tests **in a native image**; if native is a requirement, test auto-config logic on the JVM and have dedicated native smoke tests.

## 17. When to move to @SpringBootTest or Testcontainers?

`ApplicationContextRunner` excels at answering **"Which beans are registered under condition X?"**. When the question becomes **"Does the real application work end-to-end?"**, you need to change test levels:

| Goal | Tool |
|---|---|
| Bean created when enabled property = true | ApplicationContextRunner |
| Bean skipped when optional class is missing | FilteredClassLoader + runner |
| User bean overrides default | withUserConfiguration + runner |
| Context fails on invalid binding | Runner + getStartupFailure |
| Servlet-only/Reactive-only conditional | WebApplicationContextRunner/ReactiveWebApplicationContextRunner |
| Starter JAR is auto-discovered properly | Metadata/package check and @SpringBootTest smoke test |
| JDBC repository interacts with real PostgreSQL | @DataJpaTest/@SpringBootTest + Testcontainers |
| Filter chain/Security integration works | @WebMvcTest or @SpringBootTest + MockMvc |
| HTTP endpoint runs over server socket | @SpringBootTest(RANDOM_PORT) + HTTP client |
| Real Kafka/Redis/external SDK connects | Integration test with service test container |
| Native image startup with auto-config | Dedicated native-image integration/smoke test |

Separating the two levels **avoids pointless duplication**: runner tests for fast branches, full integration for a few key paths with production risk. Do not turn a small starter into dozens of full-context tests just to verify `@ConditionalOnProperty`.

## 18. Versions and support scope

In Spring Boot **3.5.x**, primary imports belong to these packages:

```java
org.springframework.boot.test.context.runner.ApplicationContextRunner
org.springframework.boot.test.context.runner.WebApplicationContextRunner
org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner
org.springframework.boot.test.context.FilteredClassLoader
org.springframework.boot.autoconfigure.AutoConfigurations
org.springframework.boot.autoconfigure.AutoConfiguration
org.springframework.boot.autoconfigure.condition.ConditionalOnProperty
org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean
org.springframework.boot.autoconfigure.condition.ConditionalOnClass
org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener
```

This is a **reference list of fully-qualified names**, not valid standalone Java `import` statements because it omits the `import` keyword. Note that Spring Boot 4.x reorganized several test and auto-config modules/packages; do not copy Boot 3.5 imports verbatim into Boot 4 without checking official APIs/your project's BOM version.

Since Boot 3.0, use `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` to declare the auto-configurations list instead of relying on the legacy `spring.factories` auto-configuration registration style.

**Article scope:** code tests JVM auto-configuration against Boot 3.5.x. It does not claim to have run a Gradle build, does not claim compatibility with a specific Boot 4 patch, and does not assume a native binary will run `ApplicationContextRunner`.

## 19. Running tests and observing output

If the project has a Gradle wrapper:

Linux/macOS:

```bash
./gradlew test --tests "com.example.mini.autoconfigure.GreetingAutoConfigurationTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.mini.autoconfigure.GreetingAutoConfigurationTest"
```

If using a Maven wrapper with an equivalent `pom.xml` and dependencies/BOM:

```bash
./mvnw -Dtest=GreetingAutoConfigurationTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=GreetingAutoConfigurationTest test
```

To run the demo application according to `build.gradle` with the `SpringBootApplication` main:

```bash
./gradlew bootRun --args='--demo.greeting.enabled=true'
```

The `bootRun` command **does not run JUnit tests**, and the demo app does not print a greeting because it has no runner invoking `GreetingService`; it only starts the Spring context. Use the `test` task to verify assertions.

**Expected result** in a proper environment: JUnit finds and runs 11 methods, and the condition branches above plus the root failure assertion match the sample code. This is **expected behavior, not actual stdout**. You must inspect `build/reports/tests/test/index.html` (Gradle) or `target/surefire-reports/` (Maven) to verify how many methods actually ran and were not `SKIPPED`, `NO-SOURCE`, or excluded by the test runner configuration.

### 19.1. When do you need javac/java?

`ApplicationContextRunner` examples require Spring Boot/Test/AssertJ/JUnit classes on the classpath. Therefore, standalone `javac` and `java` are not a convenient way to compile the whole project; use **Gradle/Maven with dependency management**. If you extract `DefaultGreetingService` and `GreetingService` into plain Java, you can use `javac`, but doing so **does not test Spring's conditional auto-configuration**.

## 20. QA checklist before finalizing an auto-configuration

- [ ] Exactly identify the conditions to test; do not pull every application auto-config into the runner.
- [ ] Have a base `ApplicationContextRunner` with `AutoConfigurations.of(...)`.
- [ ] Test missing, false, and true property values according to `havingValue/matchIfMissing`.
- [ ] Test that a custom property is actually injected/bound into the bean.
- [ ] Have positive tests asserting bean **type, name, and behavior** when required by contract.
- [ ] Have negative tests asserting no bean exists when conditions are not met.
- [ ] Have user-provided bean tests via `withUserConfiguration`, proving `@ConditionalOnMissingBean` backs off.
- [ ] When an optional dependency is involved, have a `FilteredClassLoader` test for the absent-class scenario.
- [ ] Have startup failure tests using `getStartupFailure()` if binding/initializers can fail.
- [ ] Use the right `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner` when conditions are web-only.
- [ ] Runner scenarios do not share `Environment`/beans and do not retain resources after the callback.
- [ ] Production auto-config is listed in `AutoConfiguration.imports` and packaged properly in the JAR.
- [ ] Do not confuse `AutoConfigurations.of` runner tests with production discovery verification.
- [ ] Read ConditionEvaluationReport when it is unclear why a bean was not created.
- [ ] With multiple auto-configs, have ordering tests for `@ConditionalOnBean` and user bean overrides.
- [ ] Avoid optional dependency class-loading errors before the condition check.
- [ ] Do not treat "green runner tests" as proof that DB/HTTP/Kafka resources are reachable.
- [ ] If native-image support is needed, have a separate test/smoke strategy since the runner is not used in native-image tests.
- [ ] Run JUnit via the build tool and inspect reports before claiming runtime PASS.

## 21. Official references

- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): `@AutoConfiguration`, conditions, `ApplicationContextRunner`, `AutoConfigurations`, `FilteredClassLoader`, testing user bean overrides, and `ConditionEvaluationReportLoggingListener`.
- [Spring Boot 3.5 — ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): runner constructors/configuration.
- [Spring Boot 3.5 — FilteredClassLoader Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/FilteredClassLoader.html): classpath filtering for tests.
- [Spring Boot — @ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): back-off behavior, search strategy, and conditions on definitions.
- [Spring Boot — @ConditionalOnProperty Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): `havingValue`, `matchIfMissing`, and property names semantics.
- [Spring Boot — ConditionEvaluationReportLoggingListener](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): condition diagnostics.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/testing.html): Spring TestContext with test contexts and runners.
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/): assertions, lifecycle, and test reports.

**Conclusion:** `ApplicationContextRunner` enables testing auto-configuration with **a tiny context per scenario**, without booting the entire Spring Boot application. Test both sides of `@ConditionalOnProperty`, `@ConditionalOnClass`, and `@ConditionalOnMissingBean` using `withPropertyValues`, `FilteredClassLoader`, and `withUserConfiguration`, then assert actual bean presence/absence along with its behavior. Do not mistake `AutoConfigurations.of` for discovery metadata verification; add `AutoConfiguration.imports` checks and smoke tests when releasing a starter. Combine these fast runner tests with selective integration tests to protect both **bean creation conditions** and **real application behavior**.