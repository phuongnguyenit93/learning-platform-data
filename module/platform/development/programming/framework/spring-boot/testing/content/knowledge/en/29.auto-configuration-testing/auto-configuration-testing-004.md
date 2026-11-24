# withPropertyValues and the Configuration Condition Matrix

In the **Auto-Configuration Testing** group of the **Spring Boot - testing** module, whether a bean is created often depends on multiple conditions: whether a property exists, whether its value is `true` or `false`, whether a user-defined bean is already present, whether an optional library is on the classpath, or whether the application is web/non-web. If you only start a `@SpringBootTest` with default configuration and observe that the bean appears, you do not yet know whether auto-configuration **disables at the right times**, **enables with the right values**, **backs off for custom beans**, and **does not leak configuration across test cases**.

**`ApplicationContextRunner.withPropertyValues(...)`** lets you supply `key=value` pairs into the `Environment` of **a small, fresh test context**, then verify whether the bean appears and whether its configuration is right. Combining multiple runner invocations with a **condition matrix**, you get clear evidence for `missing / false / true / invalid value / default / custom override` branches without booting the whole application or modifying real system configuration.

Lesson objectives:

1. Understand what `ApplicationContextRunner`, `AutoConfigurations.of(...)`, `withConfiguration(...)`, and `withPropertyValues(...)` do.
2. Design a matrix for `@ConditionalOnProperty` covering `prefix`, `name`, `havingValue`, and `matchIfMissing`; distinguish **an absent property** from **a present property with an empty/wrong value**.
3. Write a sample auto-configuration that creates `DeliveryClient` only when `lesson.delivery.enabled=true`, defaults to `transport=http`, and **no user-provided `DeliveryClient` bean exists**.
4. Use `@ConfigurationProperties` to test property binding independently of bean creation conditions.
5. Use `withUserConfiguration(...)` to prove `@ConditionalOnMissingBean` automatically backs off.
6. Inspect startup failures and read **ConditionEvaluationReport** when it is unclear why a condition matched or did not match.
7. Distinguish `ApplicationContextRunner` from `@SpringBootTest`, `@TestPropertySource`, `@DynamicPropertySource`, and web/reactive runners.
8. Interpret results accurately: a passing narrow context proves condition/bean registration under the constructed configuration, **not HTTP, broker, DB, or full production wiring**.

This lesson uses **Java 17+, Spring Boot 3.5.x, JUnit Jupiter 5, AssertJ/JUnit assertions**. The hands-on section includes a complete Java/Gradle module with an auto-configuration and JUnit tests, plus a Java SE demo run via `javac/java` with exact stdout to illustrate matrix logic (not a replacement for Spring runner tests).

## 1. What actually is auto-configuration?

Spring Boot auto-configuration consists of `@AutoConfiguration` classes (or configurations imported by Spring Boot via the appropriate mechanism) that register beans **only when conditions are satisfied**. Common starter pattern:

```text
Application startup
        |
        v
Spring Environment + user-defined beans + classpath
        |
        v
Auto-configuration condition evaluation
        |
        +-- Property enabled?
        +-- Optional library present?
        +-- Required bean present/absent?
        +-- Web application type appropriate?
        |
        v
Register default infrastructure beans
        |
        v
User application can inject/customize them
```

A practical configuration might use:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "lesson.delivery",
        name = "enabled",
        havingValue = "true")
class DeliveryAutoConfiguration {
    // @Bean methods with additional conditions.
}
```

This is a **snippet**, not a runnable file: it needs imports, beans, and actual classes. Complete files follow in later sections.

**Two principles:**

- Auto-configuration is not a way to force bean creation regardless of what the application wants. With `@ConditionalOnMissingBean`, default beans must **back off** for user beans.
- Condition evaluation happens primarily **when creating the ApplicationContext**. Changing a property after the context has refreshed **does not mean Spring will automatically create/remove** the corresponding bean. To test a new configuration, create a new context via the runner.

Therefore, a test matrix must have **a separate context per scenario**, rather than calling `System.setProperty(...)` while a single Spring context is already initialized.

## 2. How does ApplicationContextRunner create a context?

Minimal setup pattern:

```java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                DeliveryAutoConfiguration.class));
```

Meaning:

- `new ApplicationContextRunner()`: prepares a builder for a **non-web** context.
- `AutoConfigurations.of(...)`: registers auto-configuration classes using auto-config mechanism/ordering; distinct from user configuration.
- `withConfiguration(...)`: attaches the auto-configs under test to the runner.
- `withPropertyValues("lesson.delivery.enabled=true")`: produces a runner variant with the corresponding property.
- `run(context -> { ... })`: creates and refreshes an `ApplicationContext`, runs the callback to assert, and then closes the context per the runner lifecycle.
- `withUserConfiguration(CustomConfig.class)`: adds user-provided configuration to verify whether auto-config backs off.
- `withBean(...)`: customizes the runner with a direct user bean when no configuration class is needed.
- `withClassLoader(...)`: simulates a missing class/library; useful for `@ConditionalOnClass`.

**Difference from full integration tests:** `ApplicationContextRunner` does not boot an entire `SpringBootApplication` and scan all business code by default. It focuses on an auto-configuration and the minimal components declared by the test; thus it is fast and easy to isolate.

Spring Boot documentation explicitly notes that the context runner **does not work when tests run as a native image**. For native/AOT you need a separate testing plan; do not use green JVM runner tests to claim full native registration/Graal reflection coverage.

## 3. withPropertyValues: syntax and behavior to understand

Syntax:

```java
runner.withPropertyValues(
        "lesson.delivery.enabled=true",
        "lesson.delivery.transport=http",
        "lesson.delivery.endpoint=https://demo.invalid/send"
).run(context -> {
    // Assertions while the context is alive.
});
```

This is a **snippet** using a configured `runner` and requiring imports.

**Key technical points:**

- Each element is a string of the form `name=value`; these are **test property pairs**.
- `withPropertyValues(...)` attaches a property source to the environment of the context created by the runner; you do not need to write `application.properties`, edit environment variables, or call global `System.setProperty`.
- Test property values can override corresponding default properties from lower-priority sources; if configuring the same key multiple times, understand the runner's override rules for that case.
- Use **canonical kebab-case names** such as `lesson.delivery.enabled` and `lesson.delivery.transport`; Spring Boot supports relaxed binding in many contexts, but you should not test arbitrary aliases and rely on version-specific behavior.
- When testing a **missing key**, **omit that pair** from the runner; do not write `key=null` treating it as Java null/absent. The string `"null"` is literal text data.
- When testing **present-but-empty**, use `"lesson.delivery.transport="`; this is an intentional distinction from missing.
- Do not build property lists from shared global state without resetting; the matrix should explicitly state every input vector.

**The context runner is a builder**: calls create runner variants; safe practice is keeping a baseline `private final ApplicationContextRunner runner` and calling `runner.withPropertyValues(...).run(...)` in each method. Do not reassign the baseline field between tests or rely on test method execution order.

## 4. @ConditionalOnProperty: truth table

A condition:

```java
@ConditionalOnProperty(
        prefix = "lesson.delivery",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

Checks the full property name `lesson.delivery.enabled`. Because `havingValue="true"`, the value must match "true" under Spring Boot's string semantics; `false`, `0`, `off`, or an empty value **do not count as true** in this condition. When the key is absent, `matchIfMissing=false` causes the condition not to match.

Illustrative table:

| Property input | Key present? | `havingValue="true"` | Bean created if other conditions pass? |
| --- | --- | --- | --- |
| Property not passed | No | Does not match per `matchIfMissing=false` | No |
| `enabled=true` | Yes | Matches | Yes |
| `enabled=TRUE` | Yes | Matches via case-insensitive comparison | Yes |
| `enabled=false` | Yes | Does not match | No |
| `enabled=0` | Yes | Does not match | No |
| `enabled=yes` | Yes | Does not match | No |
| `enabled=` | Yes | Does not match | No |
| `enabled=null` (literal text) | Yes | Does not match | No |

**Do not confuse this with `@ConditionalOnProperty` without `havingValue`.** With the default `havingValue=""`, the condition checks that the property is present and its value is **not `false`**; an arbitrary string like `"maybe"` can still match. Therefore, when you want a feature flag that truly enables only on `true`, declare `havingValue="true"` explicitly and test other values too.

**`matchIfMissing=true` does not mean empty values are accepted.** It only defines the outcome if **the property is not found**. If the property is present with a value failing `havingValue`, the condition still fails.

### What about multiple property names?

```java
@ConditionalOnProperty(
        prefix = "lesson.delivery",
        name = {"enabled", "secure"},
        havingValue = "true")
```

This is a snippet. With multiple names, **all** must match; having `enabled=true` without `secure` is not enough. If you need `OR` logic, do not assume multiple names mean OR; use composition or an appropriate custom `Condition`/config structure.

**Collection warning:** `@ConditionalOnProperty` is not a reliable tool for checking the presence of **collection-indexed keys** such as `lesson.allowed[0]`. If a contract depends on collections, check via typed properties/custom conditions or an appropriate mechanism.

## 5. Designing a two-condition matrix: enabled × transport

In the main example, we want:

- The entire auto-config activates only when `lesson.delivery.enabled=true`.
- The default HTTP bean is created if `transport` is **absent** or equals `http`.
- If `transport=grpc` or empty, auto-config does not create the HTTP bean.
- If the user already declared a `DeliveryClient`, `@ConditionalOnMissingBean` must back off.
- If `enabled=true` and `endpoint` is provided, `DeliveryProperties.endpoint` is bound and passed into the bean.

Table:

| `enabled` | `transport` | User `DeliveryClient`? | Expected bean |
| --- | --- | --- | --- |
| Missing | Missing | No | None |
| false | Missing | No | None |
| true | Missing | No | Default HTTP |
| true | http | No | Default HTTP |
| true | grpc | No | None |
| true | empty | No | None |
| 0 | http | No | None |
| true | http | Yes | **Custom bean**, no default HTTP created |
| false | http | Yes | **Custom bean still present** because user created it |

The last row is crucial. A `@ConditionalOnProperty` placed on an **auto-config class** must not cause Spring to delete a user's bean just because the auto-config did not match. It governs only the beans provided by the auto-config.

**A matrix is more valuable than "test enabled=true"**: it protects the positive path, negative path, default, invalid values, and precedence of user configuration. Whenever a new condition is added, update the test matrix rather than only adding a happy-path test.

## 6. Complete runnable Java 17 project

This is an **auto-configuration library module**, requiring no web server, database, or `@SpringBootApplication`. The lesson uses Gradle's `java` plugin and the Spring Boot BOM so imports share consistent versions.

```text
delivery-autoconfig/
├── build.gradle
├── src/main/
│   ├── java/example/delivery/
│   │   ├── DeliveryClient.java
│   │   ├── HttpDeliveryClient.java
│   │   ├── DeliveryProperties.java
│   │   ├── DeliveryAutoConfiguration.java
│   │   └── ConditionMatrixDemo.java
│   └── resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── src/test/java/example/delivery/
    └── DeliveryAutoConfigurationTest.java
```

### 6.1. build.gradle

Create `build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
            'org.springframework.boot:spring-boot-dependencies:3.5.0')
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation platform(
            'org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Explanation:**

- The `java` plugin is sufficient to compile a Java library and run JUnit; the `org.springframework.boot` Gradle plugin is not required because this lesson does not package an executable `bootJar`.
- Spring Boot BOM 3.5.0 is a compatibility milestone for the 3.5 line; in real projects, use the latest 3.5.x patch according to security and compatibility policies.
- `spring-boot-autoconfigure` provides `@AutoConfiguration` and condition annotations, pulling in Spring context/core transitively.
- `spring-boot-starter-test` supplies JUnit Jupiter, Spring Boot test runner, assertions, and common test libraries.
- `junit-platform-launcher` ensures Gradle JUnit Platform runs stably according to the BOM version.
- No Docker/Testcontainers, HTTP sockets, or datasource needed to test bean creation conditions.

If a project already applies the Spring Boot Gradle plugin, simply add the appropriate dependencies without stacking conflicting BOM versions. In Spring Boot 4.x, test module/configuration packages and APIs may differ; check the documentation for the actual version used.

## 7. DeliveryClient.java: the default bean contract

Create `src/main/java/example/delivery/DeliveryClient.java`:

```java
package example.delivery;

public interface DeliveryClient {
    String endpoint();
}
```

This is a minimal interface that performs no network I/O. It serves as the dependency that auto-configuration can supply by default or that the user can define themselves. **Receiving the bean in a test does not mean an HTTP endpoint was contacted**; the topic is purely registration and property binding.

### HttpDeliveryClient.java

Create `src/main/java/example/delivery/HttpDeliveryClient.java`:

```java
package example.delivery;

public record HttpDeliveryClient(
        String endpoint) implements DeliveryClient {
}
```

A Java record automatically generates the constructor, `endpoint()` accessor, and `equals/hashCode/toString`. It fits assertions verifying that properties bound into the bean nicely. Using the `.invalid` hostname in the example ensures readers do not mistake the demo URL for a real service.

## 8. DeliveryProperties.java: binder separated from conditions

Create `src/main/java/example/delivery/DeliveryProperties.java`:

```java
package example.delivery;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "lesson.delivery")
public class DeliveryProperties {
    private String endpoint =
            "https://notification.invalid/send";

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }
}
```

Properties are bound from `Environment` when `@EnableConfigurationProperties(DeliveryProperties.class)` is processed.

- Omitting `enabled` and `transport` from this class is **completely valid**: `@ConditionalOnProperty` reads keys directly from `Environment`; `@ConfigurationProperties` binds only the fields needed.
- `endpoint` has a default value. When `lesson.delivery.endpoint` is not passed, the bean uses `https://notification.invalid/send`.
- If `lesson.delivery.endpoint=https://custom.invalid/api` is passed, the binder calls the setter before the bean factory method receives `DeliveryProperties`.
- Do not use `@Value` or read static system properties inside constructors when typed configuration properties exist; typed binding is easier to test and manage defaults for.
- If validation like `@NotBlank` is desired, a Jakarta Validation provider and `@Validated` on the properties class are required; **this example declares no validation**, so an empty endpoint can bind. Do not claim it gets rejected without writing the rule.

**Binding differs from conditions:** `@ConditionalOnProperty(enabled=true)` may match while `endpoint` is still invalid for business logic; to reject bad URLs, add separate validation/configuration-specific tests.

## 9. DeliveryAutoConfiguration.java: three cooperating conditions

Create `src/main/java/example/delivery/DeliveryAutoConfiguration.java`:

```java
package example.delivery;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "lesson.delivery",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
@EnableConfigurationProperties(DeliveryProperties.class)
public class DeliveryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DeliveryClient.class)
    @ConditionalOnProperty(
            prefix = "lesson.delivery",
            name = "transport",
            havingValue = "http",
            matchIfMissing = true)
    DeliveryClient deliveryClient(
            DeliveryProperties properties) {
        return new HttpDeliveryClient(
                properties.getEndpoint());
    }
}
```

Three layers of conditions:

1. **Class-level enabled:** if `lesson.delivery.enabled` is missing or not `true`, the entire auto-configuration does not match.
2. **Bean-level transport:** when the class is enabled, `deliveryClient()` matches only if `lesson.delivery.transport` is missing (because `matchIfMissing=true`) or equals `http`.
3. **Bean-level missing bean:** if the context already has a user-defined `DeliveryClient`, the default bean is not created.

**Ordering relative to user configuration:** Spring Boot processes auto-configurations after user-defined bean definitions. That is why `@ConditionalOnMissingBean` is used inside auto-configs rather than ordinary application configurations with arbitrary processing order. When writing tests, use `withUserConfiguration(...)` to prove the user bean is registered before the default.

**No network-calling methods:** `new HttpDeliveryClient(...)` merely creates an object storing the endpoint string, so unit/context tests accurately verify registration and binding without needing a fake HTTP server.

### 9.1. AutoConfiguration.imports

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File contents (one line):

```text
example.delivery.DeliveryAutoConfiguration
```

In Spring Boot 3.x, this metadata file allows a **real application** using the library to discover the auto-config via Boot's import mechanism.

**Important:** Tests using `AutoConfigurations.of(DeliveryAutoConfiguration.class)` are **explicit**, so they will still pass if you accidentally forget `AutoConfiguration.imports`. Therefore, review/verify resource packaging in your module/starter pipeline; context runner tests covering registration logic **do not replace a real discovery smoke test of the packaged artifact**.

## 10. Complete JUnit test class: withPropertyValues matrix

Create `src/test/java/example/delivery/DeliveryAutoConfigurationTest.java`:

```java
package example.delivery;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DeliveryAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    DeliveryAutoConfiguration.class));

    private record MatrixCase(
            String label,
            List<String> properties,
            boolean hasClient) {
    }

    @Test
    void propertyMatrixCoversMissingTrueFalseAndTransport() {
        List<MatrixCase> cases = List.of(
                new MatrixCase(
                        "enabled missing",
                        List.of(), false),
                new MatrixCase(
                        "enabled=false",
                        List.of(
                                "lesson.delivery.enabled=false"),
                        false),
                new MatrixCase(
                        "enabled=0",
                        List.of(
                                "lesson.delivery.enabled=0"),
                        false),
                new MatrixCase(
                        "enabled empty",
                        List.of(
                                "lesson.delivery.enabled="),
                        false),
                new MatrixCase(
                        "enabled=true, transport missing",
                        List.of(
                                "lesson.delivery.enabled=true"),
                        true),
                new MatrixCase(
                        "enabled=true, transport=http",
                        List.of(
                                "lesson.delivery.enabled=true",
                                "lesson.delivery.transport=http"),
                        true),
                new MatrixCase(
                        "enabled=true, transport=grpc",
                        List.of(
                                "lesson.delivery.enabled=true",
                                "lesson.delivery.transport=grpc"),
                        false),
                new MatrixCase(
                        "enabled=true, transport empty",
                        List.of(
                                "lesson.delivery.enabled=true",
                                "lesson.delivery.transport="),
                        false),
                new MatrixCase(
                        "enabled=false, transport=http",
                        List.of(
                                "lesson.delivery.enabled=false",
                                "lesson.delivery.transport=http"),
                        false));

        for (MatrixCase testCase : cases) {
            String[] pairs = testCase.properties()
                    .toArray(String[]::new);

            runner.withPropertyValues(pairs)
                    .run(context -> {
                        assertNull(
                                context.getStartupFailure(),
                                testCase.label());

                        boolean present =
                                context.getBeansOfType(
                                        DeliveryClient.class)
                                        .size() == 1;

                        assertEquals(
                                testCase.hasClient(),
                                present,
                                testCase.label());
                    });
        }
    }

    @Test
    void endpointIsBoundWhenAutoConfigurationEnabled() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=true",
                        "lesson.delivery.transport=http",
                        "lesson.delivery.endpoint="
                                + "https://custom.invalid/api")
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    DeliveryClient bean =
                            context.getBean(
                                    DeliveryClient.class);

                    assertEquals(
                            "https://custom.invalid/api",
                            bean.endpoint());

                    assertTrue(
                            bean instanceof HttpDeliveryClient);
                });
    }

    @Test
    void missingEndpointUsesDefaultFromProperties() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=true")
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    assertEquals(
                            "https://notification.invalid/send",
                            context.getBean(
                                    DeliveryClient.class)
                                    .endpoint());

                    assertEquals(
                            "https://notification.invalid/send",
                            context.getBean(
                                    DeliveryProperties.class)
                                    .getEndpoint());
                });
    }

    @Test
    void customUserBeanMakesDefaultBackOff() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=true",
                        "lesson.delivery.transport=http")
                .withUserConfiguration(
                        CustomDeliveryConfiguration.class)
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    assertEquals(
                            1,
                            context.getBeansOfType(
                                    DeliveryClient.class)
                                    .size());
                    assertEquals(
                            "memory://custom",
                            context.getBean(
                                    DeliveryClient.class)
                                    .endpoint());
                    assertFalse(
                            context.containsBean(
                                    "deliveryClient"));
                });
    }

    @Test
    void disabledAutoConfigurationDoesNotDeleteUserBean() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=false")
                .withUserConfiguration(
                        CustomDeliveryConfiguration.class)
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    assertEquals(
                            1,
                            context.getBeansOfType(
                                    DeliveryClient.class)
                                    .size());
                    assertEquals(
                            "memory://custom",
                            context.getBean(
                                    DeliveryClient.class)
                                    .endpoint());
                });
    }

    @Test
    void derivedRunnerDoesNotModifyBaseRunner() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=true")
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    assertEquals(
                            1,
                            context.getBeansOfType(
                                    DeliveryClient.class)
                                    .size());
                });

        runner.run(context -> {
            assertNull(context.getStartupFailure());
            assertTrue(
                    context.getBeansOfType(
                            DeliveryClient.class)
                            .isEmpty());
        });
    }

    @Test
    void conditionReportContainsOurAutoConfiguration() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=false")
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    ConditionEvaluationReport report =
                            ConditionEvaluationReport.get(
                                    context.getBeanFactory());

                    assertTrue(
                            report.getConditionAndOutcomesBySource()
                                    .keySet()
                                    .stream()
                                    .anyMatch(source ->
                                            source.contains(
                                                    "DeliveryAutoConfiguration")));
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomDeliveryConfiguration {

        @Bean
        DeliveryClient customDeliveryClient() {
            return () -> "memory://custom";
        }
    }
}
```

**Seven JUnit test methods** in this class check **9 matrix scenarios + 6 additional behaviors**. For the matrix, one method loops over nine cases and creates a separate context per vector, rather than 9 separate JUnit methods.

### 10.1. Why are the assertions strong enough?

- `assertNull(context.getStartupFailure())` prevents a "no bean" case from passing falsely when the context actually failed to start due to misconfiguration.
- `getBeansOfType(DeliveryClient.class).size() == 1` protects having exactly one matching bean; if two default beans were accidentally registered, the positive case also fails.
- Checking `endpoint()` confirms the property **bound into the dependency**, not just that Environment contains the key.
- `CustomDeliveryConfiguration` is a **user configuration**, so `@ConditionalOnMissingBean` must skip the default bean.
- The `enabled=false` + custom user bean case proves the class condition does not delete an independent user bean.
- The baseline runner remains unchanged after a customized `withPropertyValues(...)`; each `run(...)` has its own context.
- `ConditionEvaluationReport` shows that the condition framework evaluated the config; however, the assertion only checks **that a related entry exists**, without checking version-dependent diagnostic message text or ordering.

### 10.2. What the tests do not yet prove

- That `AutoConfiguration.imports` is definitely packaged properly in the jar and auto-discovered in another Spring Boot application — needs a separate artifact-level smoke test.
- That `HttpDeliveryClient` will successfully send HTTP requests — it only stores the endpoint string.
- That `@ConfigurationProperties` with an empty or malformed URL will be blocked by validation — the example has no URL constraint.
- That all other Spring Boot auto-configurations in a production app are compatible — the runner loads only declared classes.
- Native image/AOT behavior — Boot docs state ApplicationContextRunner is not used for native-image tests.
- Variants of environment profiles, servlet/reactive contexts, classpath dependencies — these are other axes to test when the starter supports them.

## 11. Reading the matrix properly instead of just counting test methods

The matrix has 9 vectors inside **one test method**, because the goal is ensuring every case runs with the exact same assertion structure. If 1 case fails, the `testCase.label()` message tells you which case deviated.

You can switch to `@ParameterizedTest` to report each vector as a separate test invocation, though when using JUnit parameterized tests you need to decide:

- Should `@MethodSource` supply configuration values + expected result?
- Does CI need each vector reported separately?
- Is context lifecycle kept isolated across invocations?
- Do you also need to test exceptions/startupFailure, not just bean presence?
- Do you avoid sharing a mutable `Environment` or an already-refreshed `ApplicationContext`?

The loop approach in the code is simple and **needs no extra JUnit ParameterizedTest APIs** beyond starter-test. If a team wants 9 separate invocation reports, convert it to `@ParameterizedTest(name = "{index} {0}")` with `@MethodSource`; just update the expected test count in CI accordingly.

**Do not test conditions by changing a property between two assertions in the same callback**: after context refresh, Spring does not re-evaluate class/bean conditions just because `Environment` changed. Each vector requires a new `run(...)`.

## 12. Distinguishing withPropertyValues from ConfigurationProperties binding

Both mechanisms cooperate, but serve different purposes:

```text
withPropertyValues
       |
       v
Spring Environment
       |
       +-- @ConditionalOnProperty(enabled, transport)
       |       |
       |       +-- decides whether bean definition is created
       |
       +-- @EnableConfigurationProperties
               |
               +-- binder -> DeliveryProperties.endpoint
                                   |
                                   v
                            new HttpDeliveryClient(endpoint)
```

A test checking only:

```java
assertEquals(
        "https://custom.invalid/api",
        context.getEnvironment()
               .getProperty("lesson.delivery.endpoint"));
```

**does not test the binder yet**. It only shows that Environment read the property. Real tests must check `DeliveryProperties.getEndpoint()` or a bean using the property; this lesson did both in separate cases.

### When `@ConfigurationProperties` has validation

If a production bean has:

```java
@ConfigurationProperties("lesson.delivery")
@Validated
class DeliveryProperties {
    @NotBlank
    private String endpoint;
}
```

This is a **snippet**, not the runnable class version from the lesson. It needs a Jakarta Validation provider, getters/setters/constructors, and imports. When the property is missing/blank, startup can fail during binding/validation; tests must assert **`context.getStartupFailure() != null`** and inspect the appropriate causal chain.

**Do not apply assumed validation criteria to a class without rules**. The main example allows any text as endpoint: it only tests binding. If you want valid-URL enforcement, add rules, dependencies, and a clear failure matrix.

### Null/missing semantics

`withPropertyValues("lesson.delivery.endpoint=null")` is the **four-character string `"null"`**, not Java null. To test a missing endpoint, omit the key pair. To test empty, use `"lesson.delivery.endpoint="`. These are three distinct cases.

## 13. ConditionEvaluationReport: explaining why no bean exists

When a scenario creates no bean, there are at least three possibilities:

1. The condition on the **auto-config class** did not match (enabled false/missing).
2. The class matched, yet the `@Bean` method was skipped by `@ConditionalOnProperty(transport=http)`.
3. Both properties matched, yet `@ConditionalOnMissingBean` saw a user bean so the default backed off.

One way to investigate from a runner is retrieving `ConditionEvaluationReport`:

```java
runner.withPropertyValues(
        "lesson.delivery.enabled=false")
    .run(context -> {
        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(
                        context.getBeanFactory());

        report.getConditionAndOutcomesBySource()
                .forEach((source, outcomes) -> {
                    if (source.contains(
                            "DeliveryAutoConfiguration")) {
                        System.out.println(
                                source + ": " + outcomes);
                    }
                });
    });
```

This is a **snippet using the test class's runner/imports**; it prints diagnostics, not fixed stdout, since class names, conditions, log formatting, and report ordering can differ across Spring Boot versions. The actual test in section 10 avoids asserting the entire diagnostic string.

Spring Boot includes `ConditionEvaluationReportLoggingListener` to log the report when tests need to read condition outcomes. Exact setup depends on version, e.g., using `withInitializer(...)` and the desired log level. There is no need to enable debug logging for the entire suite just to check one condition.

### Startup failure is not the same as an unmatched condition

`context.getBeansOfType(...).isEmpty()` can be true even when the context fails; hence matrix tests always assert **no startup failure** first. When intentionally testing invalid configuration, do the opposite:

```java
assertNotNull(context.getStartupFailure());
```

This is an **illustrative assertion**, not a complete failure test; you need a configuration that actually causes startup failure for it to be meaningful. For failure tests, inspect the root cause/exception type rather than hardcoding an exact message that can change across versions.

## 14. withUserConfiguration, withBean, and override behavior

`@ConditionalOnMissingBean` is a crucial starter contract: auto-config creates a default bean, while the user can provide their own implementation.

Example already in the test class:

```java
@Configuration(proxyBeanMethods = false)
static class CustomDeliveryConfiguration {
    @Bean
    DeliveryClient customDeliveryClient() {
        return () -> "memory://custom";
    }
}
```

Runner:

```java
runner.withPropertyValues(
        "lesson.delivery.enabled=true")
    .withUserConfiguration(
        CustomDeliveryConfiguration.class)
    .run(context -> {
        assertEquals(
                1,
                context.getBeansOfType(
                        DeliveryClient.class).size());
        assertEquals(
                "memory://custom",
                context.getBean(
                        DeliveryClient.class).endpoint());
    });
```

It is not `@Primary` "choosing" a bean between two candidates; **the default bean is not created** because of `@ConditionalOnMissingBean`. An important difference: if the default still existed and `@Primary` only selected custom, dependencies injecting by name or collection could see an unintended extra bean.

An alternative when no `@Configuration` class is needed:

```java
runner.withPropertyValues(
        "lesson.delivery.enabled=true")
    .withBean(
        "customDeliveryClient",
        DeliveryClient.class,
        () -> (DeliveryClient) () -> "memory://custom")
    .run(context -> {
        assertEquals(
                "memory://custom",
                context.getBean(
                        DeliveryClient.class).endpoint());
    });
```

This is a **snippet**: `withBean(name, type, supplier)` registers a user bean into the context. Depending on need, you can use `withBean(DeliveryClient.class, supplier)`. In the lesson, the complete test prefers `withUserConfiguration` because it clearly simulates an application custom configuration that a real starter will encounter.

**Do not confuse with `@MockBean/@MockitoBean`:** those annotations have override/mocking mechanics in the Spring test context. When the goal is testing auto-config back-off in favor of a user-defined bean, `withUserConfiguration` or `withBean` is clearer and closer to the contract.

## 15. Property matrix with defaults and precedence

With `matchIfMissing=true` on the transport method:

| Enabled | Transport | Endpoint | Result |
| --- | --- | --- | --- |
| true | Missing | Missing | HTTP bean + default endpoint |
| true | http | Missing | HTTP bean + default endpoint |
| true | http | Custom URL | HTTP bean + custom URL |
| true | grpc | Custom URL | No HTTP bean |
| false | http | Custom URL | Auto-config disabled |
| Missing | http | Custom URL | Auto-config disabled |

**Three kinds of "default" are not the same:**

1. **Condition default:** `matchIfMissing=true` for transport, deciding whether to create the bean when the key is absent.
2. **ConfigurationProperties default:** the `endpoint` field is pre-initialized to a value before binding.
3. **Application default property source:** a value residing in `application.properties`/env/source with its own precedence.

If a real configuration defines a property from another source (environment variable or test config file), "missing" from `withPropertyValues`'s perspective is not necessarily **missing across the whole Environment**. When proving a key is truly absent, ensure other property sources in the test runner do not supply that key themselves.

### Property overrides across runners

The runner supports chaining:

```java
ApplicationContextRunner base =
        new ApplicationContextRunner()
                .withPropertyValues(
                        "lesson.delivery.enabled=false");

ApplicationContextRunner enabled =
        base.withPropertyValues(
                "lesson.delivery.enabled=true");
```

This is a **standalone snippet on builder semantics**. A derived runner can apply new values per test-property precedence; the base retains its initial configuration. Never mutate global System properties or use static mutable fields to construct individual vectors.

When the matrix is large, create a base runner **without setting the main flag**, and let each case intentionally provide complete `enabled`/`transport` pairs. Keeping a default value in the base easily makes a "missing" case actually inherit the key from base, giving the test the wrong semantics.

## 16. How withPropertyValues differs from @TestPropertySource/@SpringBootTest

The three tools do not completely replace each other:

| Tool | Context/lifecycle | Best suited for |
| --- | --- | --- |
| `ApplicationContextRunner.withPropertyValues` | Small context, built/closed per `run` | Auto-config condition matrix, bean presence |
| `@SpringBootTest(properties=...)` | Spring TestContext, may cache contexts | Full application integration, many beans/services |
| `@TestPropertySource(properties=...)` | TestContext property sources | Customizing Spring Test's test context |
| `@DynamicPropertySource` | Static supplier to TestContext Environment | Dynamic JDBC URL/port from Testcontainers |
| `@ActiveProfiles` | TestContext active profiles | Profile-specific bean wiring |
| `@WebMvcTest`/`@DataJpaTest` | Test slices | Specialized web/data behavior |

For example, `@SpringBootTest(properties = "lesson.delivery.enabled=true")` can verify that auto-config applies in a **real application**, but if you want to test 10 different values across many classes/annotations, context setup/caching can be slower and more complex than the runner. Conversely, `ApplicationContextRunner` does not spin up an HTTP server or repository stack unless you configure it explicitly.

**The focus of this lesson is testing the auto-configuration contract**, not choosing a runner for every integration test.

## 17. Classpath, web application, and other condition axes

Testing only `enabled × transport × customBean` is insufficient when auto-config has other conditions. An expanded table:

| Axis | Common condition | How to simulate with runner |
| --- | --- | --- |
| Property | `@ConditionalOnProperty` | `withPropertyValues(...)` |
| User bean exists | `@ConditionalOnBean` / `@ConditionalOnMissingBean` | `withUserConfiguration(...)`, `withBean(...)` |
| Classpath | `@ConditionalOnClass` / `@ConditionalOnMissingClass` | `withClassLoader(new FilteredClassLoader(...))` |
| Servlet web context | `@ConditionalOnWebApplication` | `WebApplicationContextRunner` |
| Reactive web context | Reactive variant | `ReactiveWebApplicationContextRunner` |
| Resource path | `@ConditionalOnResource` | Classloader/resource setup |
| Environment/profiles | `@Profile` or custom conditions | `withPropertyValues("spring.profiles.active=...")` when appropriate |

### What is FilteredClassLoader?

Spring Boot test supports filtering a class from the classloader to simulate "optional dependency does not exist":

```java
runner.withClassLoader(
        new FilteredClassLoader(
                "com.example.optional.ExternalSdk"))
    .run(context -> {
        // Assert fallback when SDK is absent.
    });
```

This is a **directional snippet**, not part of the lesson's runnable test class since `DeliveryAutoConfiguration` does not depend on `ExternalSdk`. It is meaningful only when the auto-config under test actually has `@ConditionalOnClass(name="com.example.optional.ExternalSdk")` or a related condition. Do not write a test that always passes because the hypothetical class never existed on the classpath and then claim you tested fallback.

**`@ConditionalOnClass` note:** with optional dependencies, avoid exposing types that exist only when the dependency is present in a way that forces the JVM to load them too early. One pattern is extracting a nested configuration with `@ConditionalOnClass`; test classpath present/absent with the appropriate runner.

### Web context runner

If auto-configuration depends on `ServletWebServerApplicationContext`/servlet environment, use:

```java
new WebApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(
                        SomeWebAutoConfiguration.class))
        .run(context -> {
            // Assertions for web context.
        });
```

This is a **snippet**, requiring imports and a real `SomeWebAutoConfiguration` class. Non-web `ApplicationContextRunner` will cause `@ConditionalOnWebApplication` not to match even if production is a servlet app; passing the negative branch does not prove the positive branch in a web context.

Similarly, `ReactiveWebApplicationContextRunner` fits reactive web conditions. Choose the right context type before concluding an auto-configuration is broken.

## 18. @ConditionalOnProperty value table: read havingValue carefully

Per Spring Boot semantics, a typical `@ConditionalOnProperty` truth table:

| Actual property | Default `havingValue=""` | `havingValue="true"` | `havingValue="false"` | `havingValue="foo"` |
| --- | --- | --- | --- | --- |
| `true` | Matches | Matches | No | No |
| `false` | No | No | Matches | No |
| `foo` | Matches | No | No | Matches |
| `""` (empty) | Matches | No | No | No |
| Missing | Per matchIfMissing | Per matchIfMissing | Per matchIfMissing | Per matchIfMissing |

**Note:** the values in the table are **string property values**, not binder logic converting arbitrary truthy/falsy values like JavaScript. If `enabled="1"` or `enabled="yes"`, `havingValue="true"` does not automatically treat them as true under truthy semantics.

Why does this test matter? A starter might accidentally write:

```java
@ConditionalOnProperty(
        prefix = "lesson.delivery",
        name = "enabled")
```

If product requirements say "enable only when `enabled=true`" and an environment supplies `enabled=maybe`, the default conditional could still match. Testing `enabled=maybe` catches the discrepancy and forces the developer to declare `havingValue="true"` explicitly.

**Do not confuse `matchIfMissing` with a default value in `@ConfigurationProperties`.** `matchIfMissing` is evaluated against `Environment` before/independently of a properties object's field initializer defaults. A `boolean enabled = true` field in a Properties class **does not guarantee** `@ConditionalOnProperty(enabled)` will match when `Environment` lacks the key.

## 19. Diagnosing: do not confuse property conditions, bean back-off, and startup errors

A checklist when no bean appears:

```text
No DeliveryClient bean?
        |
        +-- Did context start successfully?
        |      |
        |      +-- NO -> inspect getStartupFailure/cause
        |
        +-- Is lesson.delivery.enabled exactly true?
        |      |
        |      +-- NO -> class-level condition skipped
        |
        +-- Is transport missing or http?
        |      |
        |      +-- NO -> method-level condition skipped
        |
        +-- Is user DeliveryClient already present?
               |
               +-- YES -> @ConditionalOnMissingBean backed off
               +-- NO  -> check bean creation/binding/factory error
```

**Inspect at the right layer:**

- `context.getStartupFailure() == null` when a case is expected to start cleanly.
- `getBeansOfType(DeliveryClient.class)` to check by type.
- `context.containsBean("deliveryClient")` when verifying the default method's **bean name**.
- `context.getBean(DeliveryProperties.class)` to check the binder.
- `ConditionEvaluationReport` to explain why a condition did not match.
- Logger at `INFO/DEBUG` when viewing diagnostics without hardcoding message wording.

A test that only runs `assertFalse(context.containsBean("deliveryClient"))` **is not enough** to prove there is no `DeliveryClient`, because a user bean can have a different name. Likewise, `getBean(DeliveryClient.class)` does not prove the default HTTP bean was chosen if a custom bean caused the default to back off. Tests must pick the right contract.

## 20. Anti-pattern: mutating global System properties between tests

A matrix written like this:

```java
System.setProperty(
        "lesson.delivery.enabled", "true");
// Another Spring test elsewhere runs in the same JVM...
System.clearProperty("lesson.delivery.enabled");
```

This is an **illustrative anti-pattern**, because global mutable properties can be read simultaneously by other tests, especially when JUnit runs in parallel. If cleanup fails to run due to an assertion failure, global state also leaks into the next test.

Prefer `withPropertyValues` to scope properties to **the case's context**. If you genuinely need to test System properties or Env precedence, use `withSystemProperties(...)` and test utilities with clear lifecycle/restore guarantees; never mutate globally without cleanup.

### Case isolation does not eliminate resources outside the context

`ApplicationContextRunner.run(...)` closes the context, yet if a `@Bean` method opens sockets/thread pools outside the lifecycle/disposable bean contract, they can still leak. For auto-configs that actually create HTTP clients, executors, or connection pools, explicitly test destroy callbacks/beans and fake external endpoints.

Do not spin up Docker just to check a property flag, yet do not use a plain runner and claim a real dependency can always connect.

## 21. How to QA a matrix without missing combinations?

With two axes:

- Enabled: `missing / true / false / invalid`.
- Transport: `missing / http / grpc / empty`.

There are **4 × 4 = 16 combinations** if testing exhaustively. Adding user bean absent/present makes 32 scenarios total. Not every project needs all 32 if rules are independent with no interactions; at a minimum, cover:

- Every enable/disable branch: missing, false, true, unexpected text/empty.
- Default transport behavior when missing, valid `http`, invalid `grpc`, present-empty.
- User override under both `enabled=true` and `enabled=false`.
- Endpoint property binding when `enabled+transport` match.
- Negative context succeeds cleanly without the bean, rather than failing startup.
- Condition report when a branch unexpectedly fails to match.
- Standalone artifact discovery test if publishing a starter library.

**If using pairwise testing** across many properties, retain critical interaction cases between conditions and missing-bean checks. "Having 20 test cases" does not prove full rule coverage if all 20 set `enabled=true`.

### Table of highest-risk cases

| Accidental mistake when editing config | Which test catches it? |
| --- | --- |
| Removing `havingValue="true"` | `enabled=0`/`enabled=maybe` negative |
| Changing `matchIfMissing=false` to true on enabled | `enabled missing` negative |
| Changing transport default to disabled | `transport missing` positive |
| Removing `@ConditionalOnMissingBean` | User-override test sees 2 beans |
| Changing prefix/name | Positive `enabled=true` has no bean |
| Omitting `@EnableConfigurationProperties` | Endpoint binding test fails (startup or wrong value) |
| Ignoring endpoint value | Custom endpoint test fails |
| Accidentally using `@Primary` instead of back-off | Bean count=1 assertion fails |
| Using wrong context type for web condition | Positive web-runner scenario fails |
| Forgetting imports metadata in starter JAR | Artifact-level discovery test fails |

**In the main code suite**, the matrix already checks absent/false/0/empty/true + transport missing/http/grpc/empty. If product requirements care about `enabled=maybe`, add a corresponding `MatrixCase`; because `havingValue="true"` is present, the expected outcome will be false. The lesson does not claim to have tested every conceivable string value.

## 22. Standalone Java 17: matrix model with exact stdout

The following Java SE program models the logic **strictly for the two specific property conditions of the example**, without creating an ApplicationContext. It helps learners see the cases before comparing them with Spring Boot JUnit tests.

Create `src/main/java/example/delivery/ConditionMatrixDemo.java`:

```java
package example.delivery;

public class ConditionMatrixDemo {

    private record Case(
            String name,
            String enabled,
            String transport) {
    }

    private static boolean shouldCreate(
            String enabled, String transport) {
        boolean on =
                "true".equalsIgnoreCase(enabled);
        boolean http =
                transport == null
                || "http".equalsIgnoreCase(transport);
        return on && http;
    }

    public static void main(String[] args) {
        Case[] cases = {
            new Case("missing enabled", null, null),
            new Case("disabled", "false", null),
            new Case("default transport", "true", null),
            new Case("http transport", "true", "http"),
            new Case("grpc transport", "true", "grpc")
        };

        for (Case testCase : cases) {
            System.out.println(
                    testCase.name() + ": "
                    + shouldCreate(
                            testCase.enabled(),
                            testCase.transport()));
        }
    }
}
```

Compile and run with **JDK 17+**, no Gradle, Spring, or Docker needed:

```bash
javac -d out src/main/java/example/delivery/ConditionMatrixDemo.java
java -cp out example.delivery.ConditionMatrixDemo
```

**Exact** stdout:

```text
missing enabled: false
disabled: false
default transport: true
http transport: true
grpc transport: false
```

This is a **pure Java model**, not the implementation of Spring Boot's `@ConditionalOnProperty`. It intentionally expresses only this lesson's `enabled havingValue=true + transport havingValue=http matchIfMissing=true`. The real Spring tests in section 10 are what prove the corresponding auto-configuration creates beans or not.

One memorable difference: the Java demo treats `null` in `Case.enabled` as "property missing", whereas in Spring `withPropertyValues("key=null")` is **a four-character string `"null"`**, not missing. Therefore the Spring matrix must represent missing by **omitting the key** from the property pairs.

## 23. How to run unit/context tests and evaluate results

From the module root with Gradle wrapper and JDK 17:

```bash
./gradlew test --tests example.delivery.DeliveryAutoConfigurationTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.delivery.DeliveryAutoConfigurationTest"
```

Expected results if Gradle dependencies/class files match the code:

- **7 JUnit test methods** in `DeliveryAutoConfigurationTest`.
- Method `propertyMatrixCoversMissingTrueFalseAndTransport` creates **9 independent contexts** corresponding to the 9 matrix cases.
- The remaining six methods verify endpoint binding/default, custom user bean/back-off, disabled auto-config retaining user bean, runner isolation, and condition report.
- No Docker, JDBC database, HTTP server, or external service required.
- `ApplicationContextRunner` closes the context for each `run(...)`; no `@DirtiesContext` needed to force Spring TestContext cache resets.

**There is no fixed stdout for the Gradle/JUnit test runner** because output depends on Gradle/JUnit/loggers and up-to-date task state. Only the `ConditionMatrixDemo` program has exact stdout in section 22. These are **designed and expected results**, not a claim that tests were run on the reader's machine.

### How to read a scenario failure

If `enabled=true,transport=grpc` unexpectedly has a bean:

1. Check whether the `@ConditionalOnProperty(transport)` annotation on the **bean method** is still present.
2. Check whether the property key prefix/name is spelled properly.
3. Retrieve `ConditionEvaluationReport` and inspect whether a condition matched erroneously.
4. Check whether a user `DeliveryClient` from another config is being added to the context.
5. Do not work around it by asserting `containsBean("deliveryClient")==false` if a custom bean exists that the contract forbids; check the true invariant.

If `enabled=true,transport=http` has no bean:

1. Check context startup failure first.
2. Check whether `DeliveryAutoConfiguration` is listed in `AutoConfigurations.of(...)`.
3. Check whether a user bean caused the default to back off.
4. Check whether `@EnableConfigurationProperties` and `DeliveryProperties` failed binding/bean creation.
5. Read the condition evaluation report rather than guessing it is a Spring context cache issue.

## 24. When do you need @SpringBootTest or artifact discovery tests?

Context runner tests fit the auto-config contract well, yet an externally published starter has other boundaries:

**A. Artifact discovery:** build the jar and ensure `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` is packaged. Test with a sample consumer application that actually imports the artifact and asserts beans appear per config, not only explicit `AutoConfigurations.of`.

**B. Full application wiring:** when multiple auto-configurations interact or component scanning/real service dependencies exist, use `@SpringBootTest(properties=...)` to test the full graph; do not turn every matrix case into a full context if cost is high.

**C. External dependencies:** if a real HTTP client opens network connections or a database driver needs a DB, separate fast unit registration tests from integration tests using WireMock/Testcontainers/service test doubles, testing connections and errors intentionally.

**D. Profile/override precedence:** when deployment environments have Helm/env/secret properties, test property source/profile precedence at the application level, not only a single property map.

**E. Native/AOT:** the runner does not run under native image tests; use appropriate build-time hints/integration/native test workflows.

**F. Classpath optionality:** `@ConditionalOnClass` must be tested with the dependency present and absent, not only when all dependencies sit on the test classpath.

**G. Auto-config ordering:** `@AutoConfigureBefore`/`@AutoConfigureAfter` or bean conditions depending on other configs must be tested inside `AutoConfigurations.of(A.class, B.class)` along with appropriate user overrides.

**H. Upgrade tests:** when upgrading Spring Boot, JUnit, starter dependencies, or third-party libraries, re-run the matrix and artifact discovery to catch condition semantics or bean naming changes.

## 25. Common mistakes with withPropertyValues

**1. Only testing enabled=true.** Skipping missing/false/invalid; annotations may enable unintentionally when users do not want them to.

**2. Forgetting havingValue="true" for boolean-like flags.** Default `havingValue=""` does not mean strict Boolean parsing.

**3. Treating matchIfMissing as "empty values also match".** Missing differs from present-empty; test both.

**4. Writing withPropertyValues("flag=null") to simulate missing.** That is literal text, not an absent property.

**5. Only checking getEnvironment().getProperty(...).** Does not prove bean binding/registration; assert the actual bean.

**6. Not asserting context.getStartupFailure()==null in negative tests.** A startup-failing context can make `getBeansOfType` empty and turn a test falsely green.

**7. Only checking bean name.** A user override can have the same type with a different name; enforce invariants by type/identity.

**8. Treating @Primary as @ConditionalOnMissingBean.** `@Primary` picks an injection candidate but does not prevent the default bean from existing.

**9. Putting @ConditionalOnMissingBean in user config with unclear ordering.** Bean registration order can affect the condition; use the auto-config contract and test user config first.

**10. Thinking a @ConfigurationProperties field default automatically activates @ConditionalOnProperty.** Conditions read Environment; field initializers do not create property sources.

**11. Thinking mutating Environment after refresh creates/removes beans.** Conditions are generally evaluated only when the context is created.

**12. Reusing the same context for multiple vectors.** Matrices must create separate contexts to isolate condition states.

**13. Mutating global System.setProperty between tests and forgetting cleanup.** Flaky/leaks properties in parallel runs; use runner-scoped test properties.

**14. Using @SpringBootTest for every vector when full app is unneeded.** Slow startup, environment depends on many out-of-contract parts.

**15. Using non-web ApplicationContextRunner to test servlet @ConditionalOnWebApplication.** Choose the appropriate `WebApplicationContextRunner`.

**16. Mocking the auto-configured bean and claiming you tested the bean factory.** Mocks can bypass the registration path; use real bean types and proper assertions.

**17. Testing presence only, ignoring default values.** The binder might skip the new endpoint; assert `bean.endpoint()` and `Properties.getEndpoint()`.

**18. Not testing custom overrides.** The starter might create two beans or fail to back off for user-defined implementations.

**19. Hardcoding full ConditionEvaluationReport output.** Diagnostic text/order is not a stable API contract across versions.

**20. Forgetting AutoConfiguration.imports while the runner stays green.** The runner loads the class explicitly; artifact discovery needs a separate test.

**21. Using FilteredClassLoader with a class name that never existed.** The "classpath missing" test naturally passes without testing real present/absent conditions.

**22. Assuming runner tests prove the starter is native-image compatible.** Needs separate native/AOT tests.

**23. Ignoring property alias/migration behavior.** When renaming keys, test both old/new keys if a backward-compatibility policy exists.

**24. Failing to test invalid typed values/startup failures.** If properties have enum/numeric validation, add a failure matrix; do not rely solely on bean presence.

**25. Confusing class conditions with @Bean conditions.** `enabled=false` skips the config; `transport=grpc` only skips the HTTP bean method inside the enabled config — `ConditionEvaluationReport` helps distinguish them.

## 26. QA checklist before finalizing the lesson

**Condition sources:**

- Did you accurately read `prefix/name/havingValue/matchIfMissing` on each annotation?
- Did you distinguish missing, true, false, unexpected string, and present-empty?
- With multiple property names, did you understand AND rather than OR?
- Did you check collection-indexed property conditions if the project uses lists?
- Did you distinguish Environment properties from `@ConfigurationProperties` field defaults?

**Context runner matrix:**

- Does each scenario get its own context via `run(...)`?
- Is there an unmutated baseline runner?
- Does `AutoConfigurations.of(...)` load the right auto-config classes per Boot's mechanism?
- Are there positive cases and negative cases?
- Do negative cases assert no startup failure before checking missing beans?
- Do you check **bean count/type/identity** instead of just bean names?
- Did you test custom user bean/back-off when enabled and when disabled?
- Did you verify endpoint/default binding?
- Are there `ConditionEvaluationReport` diagnostics for non-matching cases?

**Java correctness:**

- Do file names, packages, classes/imports, and Gradle dependencies match?
- Is `@ConfigurationProperties` registered via `@EnableConfigurationProperties`?
- Do the `DeliveryClient` interface and `HttpDeliveryClient` record have proper implementations?
- Do tests avoid needing a server/DB/Docker when only testing registration?
- Does the Java SE demo have `javac/java` commands and exact stdout?
- Do tests state only the number of methods actually present in source?
- Are non-runnable snippets clearly distinguished from full runnable source?

**Production extensions:**

- Is `AutoConfiguration.imports` packaged in the artifact?
- If the app is servlet/reactive, was the matching runner context type used?
- If conditions depend on classpath, are there class-present and class-absent tests?
- If bean validation/property binding fails, are startup failure/root cause asserted?
- With multiple auto-config modules, are ordering/user overrides tested?
- Is there a full application/artifact smoke test when needed rather than trusting only the context runner?
- Are resources created by beans kept clean after callbacks with no leaked global properties?
- Is native/AOT behavior not inferred from JVM `ApplicationContextRunner` tests?

**Conclusion:** `ApplicationContextRunner.withPropertyValues(...)` is a highly effective tool for testing **auto-configuration condition matrices**: each input vector builds a short-lived context, and assertions verify startup, bean presence/type, default/custom binding, and back-off. With `@ConditionalOnProperty`, always distinguish **missing**, **present but false/empty**, **`havingValue`**, and **`matchIfMissing`**; with `@ConditionalOnMissingBean`, always test user overrides. Context runners protect starter contracts quickly and clearly, but **do not automatically prove artifact discovery, real bean I/O, full application wiring, or native-image behavior**.

## 27. References

- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): how to declare auto-configs, imports metadata, and test with ApplicationContextRunner.
- [Spring Boot 3.5 — AbstractApplicationContextRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html): `withPropertyValues`, `withUserConfiguration`, `withBean`, `withClassLoader`, and `run`.
- [Spring Boot 3.5 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): havingValue truth table, matchIfMissing, collection limitations.
- [Spring Boot 3.5 — Configuration Properties](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): Environment, relaxed binding, and property source precedence.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest` and test slices compared to the context runner.
- [Spring Boot 3.5 — ConditionEvaluationReport API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): condition sources and outcomes.
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle, assertions, and parameterized tests.