# Overriding Properties with @SpringBootTest(properties = ...)

## 1. The Problem: Testing with Custom Configuration Without Editing application.yml

Spring Boot separates configuration from source code. The same application can run with different endpoints, timeouts, retry limits, or feature flags depending on the environment. When writing integration tests, we often want to verify a bean behaves properly **with a specific set of values** without modifying the configuration used for development or production.

For example, the application has `src/main/resources/application.yml`:

```yaml
notification:
  enabled: false
  sender-name: Default Sender
  max-attempts: 2
  timeout: 5s
```

Yet the test wants to verify the case:

```text
notification.enabled      = true
notification.sender-name  = Integration Test Sender
notification.max-attempts = 7
notification.timeout      = 250ms
```

A common anti-pattern is temporarily editing `application.yml` before running tests and reverting it afterward. That mutates project state, creates conflicts between tests, risks accidental commits, and fails to guarantee repeatability on CI.

Spring Boot provides the annotation attribute:

```java
@SpringBootTest(properties = {
    "notification.enabled=true",
    "notification.sender-name=Integration Test Sender",
    "notification.max-attempts=7",
    "notification.timeout=250ms"
})
```

The `key=value` strings in `properties` are added to the **Environment of the ApplicationContext used for the test**. They typically take higher precedence than standard configuration files, so when the context initializes, beans reading those keys receive the test values.

**Be exact about what this does:** this annotation **does not edit `application.yml`**, **does not alter machine-wide environment variables**, and **does not retroactively update beans created earlier**. It configures the **test context** during initialization.

This lesson covers syntax, overriding mechanics, effects on `Environment`, `@Value`, and `@ConfigurationProperties`, interactions with profiles and other test property sources, writing assertions, and common pitfalls.

## 2. What Is @SpringBootTest?

`@SpringBootTest` lives in package:

```java
import org.springframework.boot.test.context.SpringBootTest;
```

It is placed on a test class to launch a Spring Boot `ApplicationContext` for integration testing. Unlike unit tests that only call `new Service(...)`, this test can exercise:

- Spring Boot auto-configuration.
- Component scanning and the application's main configuration.
- Dependency injection via `@Autowired` or test constructor injection per Spring Test rules.
- An `Environment` prepared by Spring Boot's mechanisms.
- Config Data such as `application.yml` and profile-specific files.
- Binder creating `@ConfigurationProperties` objects.
- Beans conditionally registered by property or profile.

Common `@SpringBootTest` attributes:

| Attribute | Purpose |
| --- | --- |
| `properties` | Supplies `key=value` pairs to the test Environment |
| `value` | Alias for `properties` |
| `classes` | Specifies configuration classes for context startup when needed |
| `webEnvironment` | Controls whether a web environment is mocked, real, or disabled |
| `args` | Passes application arguments to Spring Boot |
| `useMainMethod` | Controls invoking `main` when building the test context, if supported |

Minimal example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = "demo.mode=test")
class DemoApplicationTest {

    @Test
    void contextStarts() {
        // Context is built with demo.mode=test.
    }
}
```

`@SpringBootTest` is a **class-level** annotation, not a way to override properties directly per `@Test` method. If tests in the same class need different configurations per method, structure separate contexts or pick another suitable tool rather than mutating global environment state between tests.

### Default webEnvironment

For web applications, `@SpringBootTest` defaults to `WebEnvironment.MOCK`: creating a mocked web application context **without starting a real embedded server**. When a lesson only tests configuration and plain Java services, you can set:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "demo.mode=test"
)
```

`NONE` builds a context with no web environment. That avoids opening ports and eliminates servlet/web-layer dependencies.

If a test actually needs to send HTTP requests to a server, use `RANDOM_PORT` with a suitable HTTP client or test framework. Overriding a property does not start a server by itself; `webEnvironment` controls that test setup.

## 3. Dependencies and Project Structure

Examples target Spring Boot 3.x, Java 17+, and JUnit Jupiter. Spring Boot 4 may differ in certain auto-configuration packages, though `@SpringBootTest` and `properties` remain available. Use dependencies and plugins managed by your project's BOM/parent.

### 3.1. Maven

In `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`spring-boot-starter-test` provides common testing infrastructure, including JUnit Jupiter, AssertJ, and Spring Test for your Boot version. If your app needs web, database, or validation support, add those starters as needed; this illustrative example does not require them.

### 3.2. Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

With Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

These snippets assume the project applies the Spring Boot plugin and manages dependency versions properly. In multi-module builds, place `spring-boot-starter-test` in the module containing tests.

### 3.3. Example Structure

```text
notification-config-demo/
└── src/
    ├── main/
    │   ├── java/com/example/notification/
    │   │   ├── NotificationApplication.java
    │   │   ├── NotificationProperties.java
    │   │   └── NotificationPlanService.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/notification/
            ├── NotificationPropertiesOverrideTest.java
            └── NotificationDefaultsTest.java
```

We build an application running purely in memory, with no external API calls or real database. That keeps focus on **effective configuration values**, unmixed with network mocking or transactions.

## 4. Defining Baseline Configuration in application.yml

Create `src/main/resources/application.yml`:

```yaml
notification:
  enabled: false
  sender-name: Default Sender
  max-attempts: 2
  timeout: 5s
```

This is the application's standard Config Data source.

Relevant keys:

| Key | Value in YAML | Expected type |
| --- | --- | --- |
| `notification.enabled` | `false` | `boolean` |
| `notification.sender-name` | `Default Sender` | `String` |
| `notification.max-attempts` | `2` | `int` |
| `notification.timeout` | `5s` | `Duration` |

Because YAML sits in `src/main/resources`, it appears on both the main and test classpaths; however, effective values still depend on higher-precedence sources in `Environment`.

You do not need a separate `application.yml` for every test class just to override a few keys. `@SpringBootTest(properties = ...)` suits specific, targeted overrides visible directly on the test class.

## 5. Creating @ConfigurationProperties to Observe Binding

Create `NotificationProperties.java`:

```java
package com.example.notification;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        boolean enabled,
        String senderName,
        int maxAttempts,
        Duration timeout
) {}
```

A Java record holds all four configuration values. Spring Boot's Binder maps `sender-name` in YAML to the `senderName` record component via relaxed binding.

Key points:

- Java code interacts with `properties.senderName()` rather than looking up raw YAML keys.
- `timeout` receives a `Duration` object instead of the string `"5s"`.
- `@ConfigurationProperties` does not create a bean until registered via an appropriate mechanism.
- Record parameters here are **configuration data**, not a place to inject a `Repository`, `HttpClient`, or business service.

### 5.1. Creating a Service That Consumes Properties

Create `NotificationPlanService.java`:

```java
package com.example.notification;

import java.time.Duration;

import org.springframework.stereotype.Service;

@Service
public class NotificationPlanService {

    private final NotificationProperties properties;

    public NotificationPlanService(
            NotificationProperties properties) {
        this.properties = properties;
    }

    public NotificationPlan currentPlan() {
        return new NotificationPlan(
                properties.enabled(),
                properties.senderName(),
                properties.maxAttempts(),
                properties.timeout()
        );
    }

    public record NotificationPlan(
            boolean enabled,
            String senderName,
            int maxAttempts,
            Duration timeout
    ) {}
}
```

`currentPlan()` merely returns a plan descriptor object **without sending emails or making network calls**. We use it to verify that not only `Environment`, but also a **Spring-injected service** sees the expected configuration.

### 5.2. Registering Properties

Create `NotificationApplication.java`:

```java
package com.example.notification;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationApplication.class, args);
    }
}
```

`@EnableConfigurationProperties` registers the record type so Spring Boot's binder produces the bean. Do not add `@Component` to this constructor-bound record.

By package structure, `@SpringBootTest` inside `com.example.notification` normally discovers `NotificationApplication` even without specifying `classes`. To keep the example independent of configuration discovery, we explicitly declare `classes = NotificationApplication.class` in the test.

## 6. Main Test: Overriding Four Properties

Create `NotificationPropertiesOverrideTest.java`:

```java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

@SpringBootTest(
    classes = NotificationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "notification.enabled=true",
        "notification.sender-name=Integration Test Sender",
        "notification.max-attempts=7",
        "notification.timeout=250ms"
    }
)
class NotificationPropertiesOverrideTest {

    @Autowired
    Environment environment;

    @Autowired
    NotificationProperties properties;

    @Autowired
    NotificationPlanService planService;

    @Test
    void environmentSeesTestValues() {
        assertThat(environment.getProperty("notification.enabled"))
                .isEqualTo("true");

        assertThat(environment.getProperty(
                "notification.sender-name"))
                .isEqualTo("Integration Test Sender");

        assertThat(environment.getProperty(
                "notification.max-attempts"))
                .isEqualTo("7");

        assertThat(environment.getProperty(
                "notification.timeout"))
                .isEqualTo("250ms");
    }

    @Test
    void configurationPropertiesAreBoundFromOverrides() {
        assertThat(properties.enabled()).isTrue();
        assertThat(properties.senderName())
                .isEqualTo("Integration Test Sender");
        assertThat(properties.maxAttempts()).isEqualTo(7);
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofMillis(250));
    }

    @Test
    void serviceReceivesTheSameEffectiveConfiguration() {
        NotificationPlanService.NotificationPlan plan =
                planService.currentPlan();

        assertThat(plan.enabled()).isTrue();
        assertThat(plan.senderName())
                .isEqualTo("Integration Test Sender");
        assertThat(plan.maxAttempts()).isEqualTo(7);
        assertThat(plan.timeout())
                .isEqualTo(Duration.ofMillis(250));
    }
}
```

The three tests serve distinct goals:

1. **`environmentSeesTestValues`** verifies the test `Environment` property resolver.
2. **`configurationPropertiesAreBoundFromOverrides`** verifies Spring Boot Binder and type conversion.
3. **`serviceReceivesTheSameEffectiveConfiguration`** verifies the business bean receives the bound configuration object.

If you assert only `environment.getProperty(...)`, you do not prove the record is registered or that the service uses it. If you assert only the service, failures blur the line between binding and service logic. Checking all three illuminates the configuration data flow.

## 7. Running Tests and Observing Results

With the Maven wrapper:

```bash
./mvnw test
```

With the Gradle wrapper:

```bash
./gradlew test
```

On Windows, you can run `mvnw.cmd test` or `gradlew.bat test` depending on your build tool. Packaged JAR paths are not needed because tests are executed by the build tool.

When all three tests pass, you have proof that **within this test context**, those keys are overridden as expected.

Notes:

- Tests do not alter `src/main/resources/application.yml`.
- `@SpringBootTest(properties=...)` applies only to the context built for tests bearing that annotation, subject to TestContext inheritance/caching rules.
- Running `NotificationApplication.main` normally without overrides still reads `enabled=false`, `maxAttempts=2`, and `timeout=5s` from YAML.
- This test does not prove a real SMTP/email endpoint works, as the example performs no external communication.

**Core rule:** Annotation overrides belong to **test setup**, not persistent application configuration changes.

## 8. Properties Syntax: Single String or Multiple Strings?

`@SpringBootTest.properties` has type **`String[]`**. You can pass one element:

```java
@SpringBootTest(properties = "feature.mode=fast")
class FeatureModeTest {}
```

Or multiple elements:

```java
@SpringBootTest(properties = {
    "feature.enabled=true",
    "feature.mode=fast",
    "feature.limit=12"
})
class FeatureConfigurationTest {}
```

Each element represents a text property entry. In this lesson, prefer `key=value` to avoid ambiguity, matching the syntax documented in the `@SpringBootTest` Javadoc.

**Never** place a multi-level YAML snippet inside one element expecting the annotation to parse YAML:

```java
// Do not expect this string to be parsed as a YAML document:
@SpringBootTest(properties = "feature:\n  mode: fast")
```

Proper form:

```java
@SpringBootTest(properties = "feature.mode=fast")
```

When many keys, large collections/maps, or shared test setups are involved, consider `application-test.yml` or `@TestPropertySource` rather than stuffing hundreds of lines into an annotation.

### 8.1. Whitespace and Data Types

```java
@SpringBootTest(properties = {
    "feature.label=Hello World",
    "feature.retry-count=4",
    "feature.enabled=false",
    "feature.timeout=1s"
})
```

`"feature.label=Hello World"` has a space inside the value, yet remains a valid Java `String`. Binder later converts `"4"` to `int` and `"1s"` to `Duration`.

If a value itself contains `=`, keep Java properties parsing rules in mind: the first separator splits key and value, leaving the rest in the value under standard properties syntax. Do not try to build a custom YAML parser by concatenating strings; for complex payloads, use a source with explicit serialization support.

### 8.2. Do Not Mix with Application Argument Syntax

Compare:

```java
@SpringBootTest(properties = "feature.mode=fast")
```

and:

```java
@SpringBootTest(args = "--feature.mode=fast")
```

The first is a **test property**. The second is an **application argument** passed to the application via `args`. Both may result in a key getting a similar value, yet they travel through two different test setup mechanisms.

Do not prefix `--` to keys inside `properties`:

```java
// Wrong intent: this is not the canonical property name
@SpringBootTest(properties = "--feature.mode=fast")
```

Use `feature.mode=fast` with `properties`. Use `args` when specifically testing how the application handles command-line arguments.

## 9. Why Annotation Overrides Take Effect

Spring Boot resolves values through `Environment` and ordered `PropertySource` instances. When Spring Test builds an `ApplicationContext`, inline properties from `@SpringBootTest(properties=...)` are added to the test environment so they can override values from normal configuration files.

Visualize it as:

```text
src/main/resources/application.yml
notification.max-attempts = 2
notification.timeout      = 5s
                   |
                   v
     Test Environment & PropertySources
                   ^
                   |
@SpringBootTest(properties = {
  notification.max-attempts = 7
  notification.timeout      = 250ms
})
                   |
                   v
           Effective values
maxAttempts = 7
timeout     = 250ms
                   |
                   v
       Binder creates NotificationProperties
                   |
                   v
       NotificationPlanService receives bean
```

Spring Boot never modifies the YAML file. It inserts a suitably prioritized source into the **test Environment** before beans are bound and injected.

Compare the approaches:

- **Adjusting config sources at context startup:** beans receive new values from the start.
- **Mutating `Environment` after context starts:** already-bound or injected beans typically do not update automatically.
- **Calling JVM-wide `System.setProperty`:** can leak into other tests and is hard to clean up.
- **Modifying `application.yml` in code:** creates side effects on project resources.

`@SpringBootTest(properties=...)` establishes a predictable context without global side effects.

## 10. Partial Overrides: Unlisted Properties Still Come from Other Sources

You do not need to override the whole `notification.*` group. Suppose YAML remains:

```yaml
notification:
  enabled: false
  sender-name: Default Sender
  max-attempts: 2
  timeout: 5s
```

The test sets only:

```java
@SpringBootTest(properties = {
    "notification.max-attempts=9"
})
```

Expected values:

| Property | Effective value | Source in example |
| --- | --- | --- |
| `notification.enabled` | `false` | YAML |
| `notification.sender-name` | `Default Sender` | YAML |
| `notification.max-attempts` | `9` | Inline test property |
| `notification.timeout` | `5s` | YAML |

Spring does not "wipe the whole `notification` block" just because one key is overridden. Property resolution works per key alongside binding rules for target structures.

One architectural exception to remember: for **Lists** and certain collection types, Spring Boot applies different replacement/merge semantics across sources than for maps and scalars. Do not extrapolate this scalar table to claim every collection merges element-by-element. When testing lists or Maps, review the relevant binder rules.

### 10.1. Test Using Remaining Values from YAML

```java
@SpringBootTest(
    classes = NotificationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "notification.max-attempts=9"
)
class PartialOverrideTest {

    @Autowired
    NotificationProperties properties;

    @Test
    void changesOnlyChosenProperty() {
        assertThat(properties.enabled()).isFalse();
        assertThat(properties.senderName())
                .isEqualTo("Default Sender");
        assertThat(properties.maxAttempts()).isEqualTo(9);
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofSeconds(5));
    }
}
```

This snippet requires the same imports as the test in section 6. To keep it runnable standalone, place the test in `com.example.notification` and include the imports shown earlier.

## 11. Comparing Against a Non-Overridden Test

Create a separate class `NotificationDefaultsTest.java`:

```java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
    classes = NotificationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class NotificationDefaultsTest {

    @Autowired
    NotificationProperties properties;

    @Test
    void readsFileValuesWhenNoTestOverrideIsDeclared() {
        assertThat(properties.enabled()).isFalse();
        assertThat(properties.senderName())
                .isEqualTo("Default Sender");
        assertThat(properties.maxAttempts()).isEqualTo(2);
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofSeconds(5));
    }
}
```

The two test classes describe two configurations:

```text
NotificationDefaultsTest:
  @SpringBootTest              -> YAML baseline

NotificationPropertiesOverrideTest:
  @SpringBootTest(properties)  -> test overrides + YAML baseline
```

Spring TestContext caches contexts. Because the configuration used to build each context differs, tests with different configurations receive separate contexts rather than unexpectedly mixing data.

More important than memorizing internal cache details is **never turning tests into programs that mutate global state**. Declare explicit configuration on the test class and let Spring TestContext manage lifecycles.

## 12. Overriding Values Used by @Value

Not every application uses `@ConfigurationProperties` exclusively. A bean can read properties via `@Value`:

```java
package com.example.notification;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class SenderLabel {

    private final String value;

    public SenderLabel(
            @Value("${notification.sender-name}") String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
```

With test:

```java
@SpringBootTest(properties = {
    "notification.sender-name=Sender From Test"
})
class SenderLabelTest {

    @Autowired
    SenderLabel senderLabel;

    @Test
    void valueAnnotationSeesTestProperty() {
        assertThat(senderLabel.value())
                .isEqualTo("Sender From Test");
    }
}
```

Because `@Value` is resolved during bean instantiation and test properties are already in the environment by then, the bean receives the overridden value.

### 12.1. Default Values in @Value

Example:

```java
@Value("${notification.sender-name:Anonymous}")
String senderName;
```

The default `Anonymous` is used only when placeholder resolution finds no matching value. If YAML or `@SpringBootTest(properties=...)` supplies the key, the bean receives the resolved value.

Do not confuse `@Value`'s `:Anonymous` placeholder fallback with high-priority test overrides. When a test source supplies an empty value, behavior differs from an absent key; sources generally treat `""` as a provided value.

## 13. Overrides and @ConfigurationProperties Constructor Binding

With a record:

```java
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        URI gatewayUrl,
        Duration timeout,
        int maxAttempts
) {}
```

Configuration:

```yaml
payment:
  gateway-url: https://payment.example.invalid
  timeout: 3s
  max-attempts: 2
```

Test:

```java
@SpringBootTest(properties = {
    "payment.timeout=400ms",
    "payment.max-attempts=5"
})
```

Binder creates the record with `timeout=Duration.ofMillis(400)` and `maxAttempts=5`, while `gatewayUrl` still comes from YAML unless overridden by a higher-priority source.

If the test writes:

```java
@SpringBootTest(properties = "payment.max-attempts=not-a-number")
```

and Java expects `int`, the test fails **during context startup** due to a conversion error. That is useful when checking configuration validity, though distinct from an assertion failure inside an executing test method.

### 13.1. Do Not Misspell a Key and Assume It Overrode YAML

`payment.max-attemtps` (typo) is not the canonical name `payment.max-attempts`. Binder may ignore an unbound key under default settings and still take the YAML value for the real field.

If tests always assert `properties.maxAttempts()` instead of merely checking that the test method ran, they catch ineffective overrides immediately.

Relaxed binding supports valid name variations; it does not auto-fix spelling mistakes.

## 14. Overriding Properties That Control @ConditionalOnProperty

An application can toggle beans based on properties:

```java
package com.example.notification;

public interface AuditSink {
    String channel();
}
```

An implementation:

```java
package com.example.notification;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    prefix = "audit",
    name = "enabled",
    havingValue = "true"
)
public class ConsoleAuditSink implements AuditSink {

    @Override
    public String channel() {
        return "console";
    }
}
```

With YAML:

```yaml
audit:
  enabled: false
```

The `ConsoleAuditSink` bean is not created because the condition is unmet.

Test enabling the bean:

```java
@SpringBootTest(
    classes = NotificationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "audit.enabled=true"
)
class AuditEnabledTest {

    @Autowired
    ApplicationContext context;

    @Test
    void createsAuditSinkWhenEnabled() {
        assertThat(context.getBeansOfType(AuditSink.class))
                .hasSize(1);
    }
}
```

Test disabling the bean:

```java
@SpringBootTest(
    classes = NotificationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "audit.enabled=false"
)
class AuditDisabledTest {

    @Autowired
    ApplicationContext context;

    @Test
    void omitsAuditSinkWhenDisabled() {
        assertThat(context.getBeansOfType(AuditSink.class))
                .isEmpty();
    }
}
```

Import `org.springframework.context.ApplicationContext` and the basic test imports shown earlier. Both classes must be in packages where component scanning detects `ConsoleAuditSink`.

Because `@ConditionalOnProperty` is evaluated when building bean definitions/context, test properties are already present and can alter the **bean structure of the context**, not only field values.

### 14.1. Do Not Flip Flags After Beans Are Built

If a test runs:

```java
System.setProperty("audit.enabled", "true");
```

**after** the context was built with `audit.enabled=false`, it will not create `ConsoleAuditSink`. Bean conditions are not continuous listeners watching property changes. To test two states, use two separate test contexts or a test utility built for multiple contexts.

## 15. Precedence: When a Value Is Declared in Multiple Places

A configuration value can appear simultaneously in:

- `src/main/resources/application.yml`.
- `src/test/resources/application.yml` or other test config files on classpath.
- `application-test.yml` when profile `test` is active.
- CI environment variables.
- Java system properties.
- Command-line/application arguments.
- `@SpringBootTest(properties=...)`.
- `@TestPropertySource`.
- `@DynamicPropertySource`.

For this lesson, the most important rule is:

**Values supplied via `@SpringBootTest(properties=...)` are designed to take higher precedence than standard configuration sources such as Config Data, environment variables, and Java system properties in the test context.**

Example:

```text
application.yml:
  notification.max-attempts = 2

CI environment:
  NOTIFICATION_MAXATTEMPTS = 6

@SpringBootTest(properties):
  notification.max-attempts = 7

Result in matching test conditions:
  maxAttempts = 7
```

This keeps tests independent of environment variables set earlier by developers or CI pipelines.

### 15.1. Do Not Memorize One Rigid Order for All Annotations

`@TestPropertySource` and `@DynamicPropertySource` also carry high precedence; exact priority when multiple mechanisms declare the **exact same key** depends on Spring TestContext, Spring Boot, and version rules.

Safe practices:

1. Each overridden key in a test should have **one clear owning test source**.
2. Avoid declaring the same key simultaneously across `@SpringBootTest(properties=...)`, `@TestPropertySource`, and `@DynamicPropertySource` unless specifically testing precedence.
3. When a test is meant to prove precedence, assert both `Environment` and bound bean values rather than guessing.
4. When upgrading Spring Boot/Spring Framework, re-verify any tests with overlapping sources.

In normal cases without competing high-priority test sources, inline `properties` override matching keys in application config files.

## 16. @SpringBootTest(properties) and @ActiveProfiles("test")

`@ActiveProfiles` comes from Spring Test:

```java
import org.springframework.test.context.ActiveProfiles;
```

This annotation selects active profiles when TestContext loads the application context.

Example:

```java
@ActiveProfiles("test")
@SpringBootTest(
    classes = NotificationApplication.class,
    properties = "notification.max-attempts=7"
)
class ProfilePlusOverrideTest {}
```

Create `src/test/resources/application-test.yml`:

```yaml
notification:
  enabled: false
  sender-name: Test Profile Sender
  max-attempts: 4
  timeout: 2s
```

With profile `test` active:

- `senderName` receives `Test Profile Sender`.
- `timeout` receives `2s`.
- `maxAttempts` receives `7` from `@SpringBootTest.properties` because that key was overridden.
- `enabled` comes from the profile or another source according to precedence.

Table:

| Key | Base file | Test profile file | Inline override | Expected value |
| --- | --- | --- | --- | --- |
| `enabled` | false | false | None | false |
| `sender-name` | Default Sender | Test Profile Sender | None | Test Profile Sender |
| `max-attempts` | 2 | 4 | 7 | 7 |
| `timeout` | 5s | 2s | None | 2s |

**Distinct roles:**

- `@ActiveProfiles("test")` selects a **profile-based configuration set**, potentially spanning many keys and bean conditions.
- `@SpringBootTest(properties=...)` adds **specific inline values** to the test Environment.

They complement each other. Do not use `@ActiveProfiles` as a clumsy way to replace single properties, nor replace a shared test profile with hundreds of inline properties across many classes.

### 16.1. Why Not Set spring.profiles.active Arbitrarily?

Some developers try:

```java
@SpringBootTest(properties = "spring.profiles.active=test")
```

While this can affect profiles during context startup in some cases, in Spring Test `@ActiveProfiles` is the dedicated tool designed to declare active test profiles.

When selecting a profile for the context, prefer `@ActiveProfiles("test")` so intent is explicit and TestContext tracks the profile properly. Reserve inline properties for specific business values you want to override.

## 17. @SpringBootTest(properties) vs. @TestPropertySource

`@TestPropertySource` is a Spring TestContext annotation:

```java
import org.springframework.test.context.TestPropertySource;
```

It can supply inline properties or point to dedicated `.properties` files for integration tests.

Inline example:

```java
@SpringBootTest(classes = NotificationApplication.class)
@TestPropertySource(properties = {
    "notification.enabled=true",
    "notification.max-attempts=8"
})
class NotificationTestPropertySourceTest {}
```

Or loading a file:

```java
@SpringBootTest(classes = NotificationApplication.class)
@TestPropertySource(
    locations = "classpath:/notification-fixture.properties"
)
class NotificationFixtureTest {}
```

`src/test/resources/notification-fixture.properties`:

```properties
notification.enabled=true
notification.sender-name=Fixture Sender
notification.max-attempts=8
notification.timeout=1s
```

Comparison:

| Mechanism | When appropriate? |
| --- | --- |
| `@SpringBootTest(properties=...)` | A few fixed values tied directly to a Boot test class |
| `@TestPropertySource(properties=...)` | Using Spring Framework's standard TestContext inline properties |
| `@TestPropertySource(locations=...)` | A reusable test properties file shared across tests |
| `@ActiveProfiles("test")` | A full set of profile-based values and bean conditions |
| `@DynamicPropertySource` | Runtime-determined values like Testcontainers host/port |

They can coexist in a project, though avoid overlapping the **same key** across mechanisms without reason. For "this test just needs a different timeout and max-attempts," `@SpringBootTest(properties=...)` is usually the cleanest choice.

## 18. Comparing with @DynamicPropertySource

Some values are unknown when compiling tests:

- Random ports assigned by Testcontainers.
- Endpoints of mock servers launched inside the test.
- Database URLs on dynamic ports.
- Test broker addresses.
- Short-lived test credentials generated by test fixtures.

For these, `@DynamicPropertySource` is the right extension point:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class IntegrationTestBase {

    @DynamicPropertySource
    static void registerDynamicProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "external.service.port",
            () -> TestServerHolder.port()
        );
    }
}
```

`TestServerHolder` here is an illustrative class your project would define to manage test resources; it is not a built-in Spring class.

Contrast with a hardcoded value:

```java
@SpringBootTest(properties = "external.service.port=9099")
```

If the mock server's port changes across runs, hardcoding `9099` makes tests fragile. `@DynamicPropertySource` supplies values determined during test lifecycles.

Spring Framework documents dynamic test properties as having higher precedence than many static test sources; avoid declaring the same key in both `@SpringBootTest.properties` and `@DynamicPropertySource` unless specifically testing precedence.

### 18.1. Do Not Overuse Dynamic Properties

If you only need:

```java
"feature.enabled=false"
"notification.max-attempts=1"
```

then `@SpringBootTest(properties=...)` is clearer and more readable than a supplier lambda. Use `@DynamicPropertySource` when values **depend on runtime resources**, not merely to put literal strings into Environment.

## 19. @SpringBootTest(properties) Is Not @TestPropertySource(locations)

A common misconception:

```java
@SpringBootTest(properties = "classpath:/my-test.properties")
```

This string is **not a file-loading directive** like `@TestPropertySource(locations=...)`. `@SpringBootTest.properties` expects **inline property declarations**.

To load a reusable file:

```java
@TestPropertySource(
    locations = "classpath:/my-test.properties"
)
```

or use Spring Boot's Config Data and profiles as needed.

For inline values:

```java
@SpringBootTest(properties = {
    "my.feature.enabled=true",
    "my.feature.name=test"
})
```

This syntactic boundary is critical: **file locations** and **property declarations** are completely different parameters.

## 20. Overriding for @Value Beans and Direct Environment Readers

Suppose a class reads a property inside its constructor:

```java
@Component
public class AuditPolicy {

    private final boolean enabled;

    public AuditPolicy(Environment env) {
        this.enabled = Boolean.parseBoolean(
            env.getProperty("audit.enabled", "false")
        );
    }

    public boolean enabled() {
        return enabled;
    }
}
```

When a test uses:

```java
@SpringBootTest(properties = "audit.enabled=true")
```

and the context creates the bean after test properties are applied, `enabled` becomes `true`.

This shows property overrides affect **every component reading from the same test Environment** according to when it reads:

- `Environment`: read when methods are called.
- `@Value`: typically injected during bean creation.
- `@ConfigurationProperties`: bound when beans are created/updated per application mechanics.
- `@ConditionalOnProperty`: affects bean registration decisions.
- `@Configuration` bean factories: read configuration when creating infrastructure.

**Do not assume everything automatically refreshes if a property changes later.** Test annotations primarily prepare the environment **before context initialization**.

## 21. Which Properties Make Sense to Override in Tests?

Commonly appropriate groups:

### 21.1. Feature Flags

```java
@SpringBootTest(properties = {
    "features.discount.enabled=true"
})
```

Tests conditional beans, service behavior, or specific business branches.

### 21.2. Limits and Timeouts

```java
@SpringBootTest(properties = {
    "batch.max-items=25",
    "client.connect-timeout=100ms"
})
```

Tests typed property fields and logic using them. In unit tests without Spring, passing the configuration object directly is still faster.

### 21.3. Fake URLs or Mock Endpoints

```java
@SpringBootTest(properties = {
    "partner.endpoint=http://127.0.0.1:18080"
})
```

Only use a fixed port if the test truly manages that resource and avoids collisions. For mock servers with random ports, use `@DynamicPropertySource`.

### 21.4. Disabling Schedulers or Outbound Jobs

```java
@SpringBootTest(properties = {
    "app.scheduler.enabled=false",
    "app.outbound.enabled=false"
})
```

These are **application-defined keys** in the example; they have no effect in Spring unless your project code reads and honors them. An inline property does not magically disable an arbitrary scheduler or client lacking matching configuration/conditions.

### 21.5. Test-Specific Flags

```java
@SpringBootTest(properties = {
    "app.test-mode=true",
    "app.display-label=Integration Example"
})
```

Document which keys exist solely for tests and avoid making production logic depend on ad-hoc "test flags" without a clear design.

## 22. Verifying Values via Environment and Binder

When a test fails with an unexpected value, do not jump to the conclusion that `@SpringBootTest.properties` was ignored. Check both layers:

```java
@Autowired Environment env;

@Autowired NotificationProperties props;
```

Then assert:

```java
assertThat(env.getProperty("notification.max-attempts"))
    .isEqualTo("7");

assertThat(props.maxAttempts())
    .isEqualTo(7);
```

If Environment holds `7` while the record holds `2` or `0`, investigate:

1. Is `NotificationProperties` registered?
2. Is the right `NotificationProperties` bean injected?
3. Are the prefix, field names, and relaxed binding right?
4. Does another bean read/configure the value early in a custom way?
5. Are multiple contexts involved, with assertions hitting a different one?
6. Is custom binding or refresh logic changing observation timing?

If neither Environment nor the record sees `7`, check key spelling, which test class has the annotation, and whether another test source overrides it.

### 22.1. Do Not Dump Every PropertySource to Logs

Sometimes developers print the entire `Environment` or all keys/values while debugging. That can expose CI secrets, database credentials, or tokens. Log only source names and selected harmless keys, or write assertions against known test values.

```java
assertThat(env.getProperty("notification.max-attempts"))
        .isEqualTo("7");
```

For tokens, use a **dummy sentinel** and avoid logging real system values.

## 23. Empty Values vs. Undeclared Properties

There is a difference between:

```java
@SpringBootTest(properties = "demo.label=")
```

and **omitting** `demo.label` from the annotation.

The first provides an empty text value for `demo.label`. The inline source can override a non-empty value from YAML. The second lets the resolver fall through to remaining sources.

Example YAML:

```yaml
demo:
  label: Default Label
```

Test:

```java
@SpringBootTest(properties = "demo.label=")
```

causes `Environment.getProperty("demo.label")` to return an empty string, not `Default Label`. That is standard **precedence-based property resolution**.

If non-empty values are required, add validation such as `@NotBlank` in `@ConfigurationProperties` with a Jakarta Validation provider. Having a YAML default does not fix an empty string supplied by a higher-priority source.

### 23.1. Null Literals vs. Missing Properties

`@SpringBootTest.properties` accepts strings; it is not an API for supplying a `null` literal with "property absent" semantics. Writing:

```java
@SpringBootTest(properties = "demo.label=null")
```

normally produces the literal string `"null"`, **not** removal of the key from `Environment`. To test an absent key, control the configuration sources supplying it or use a minimal test setup.

## 24. Overriding List and Map Data

For scalar values like `int`, `boolean`, `String`, and `Duration`, a `key=value` string is straightforward. For Lists and Maps, pay attention to binding syntax.

Example class:

```java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
    List<String> destinations,
    Map<String, String> handlers
) {}
```

You can supply entries using property paths:

```java
@SpringBootTest(properties = {
    "routing.destinations[0]=primary",
    "routing.destinations[1]=secondary",
    "routing.handlers[/api/v1]=orders"
})
```

List items use `[0]`, `[1]`. For Map keys containing slashes `/`, bracket notation preserves the literal key `/api/v1` during binding.

Notes:

- Inside `@SpringBootTest.properties` Java strings, do not wrap brackets in YAML quotes, because this is not a YAML document.
- Lists have distinct binding and override rules; do not assume index `0` from one source automatically merges with index `1` from another in every scenario.
- If configuration is complex or lengthy, `application-test.yml` is far more readable than dozens of inline strings.

### 24.1. When Map Keys Contain Dots

For `Map<String, Object>`, write:

```java
"routing.options[feature.beta]=on"
```

to prevent dots inside the key from being interpreted as nested properties. With `Map<String,String>`, dots are preserved without brackets in some cases, yet `[feature.beta]` makes literal-key intent unmistakable.

## 25. Validation: Invalid Test Properties Can Prevent Context Startup

Suppose a configuration class has constraints:

```java
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        @Min(1) int maxAttempts
) {}
```

If a test declares:

```java
@SpringBootTest(properties = {
    "notification.max-attempts=0"
})
class InvalidNotificationPropertiesTest {}
```

and Spring Boot has a suitable validation provider configured, the context **fails to start** because `@Min(1)` is violated. Test methods inside the class never run to perform normal assertions.

That outcome is expected if verifying rejection of invalid configuration, yet **`@SpringBootTest` is often not the most convenient tool to assert a startup failure**: the annotation builds the context before entering test methods.

A better fit for "invalid field must cause startup failure" is `ApplicationContextRunner`, designed to let you inspect context startup failures without failing test setup before assertions run.

## 26. Testing Invalid Configuration with ApplicationContextRunner

Example:

```java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.constraints.Min;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.context.PropertyPlaceholderAutoConfiguration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;

class ValidationFailureTest {

    @Validated
    @ConfigurationProperties(prefix = "limits")
    record LimitProperties(@Min(1) int maxItems) {}

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(LimitProperties.class)
    static class LimitConfig {}

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(LimitConfig.class);

    @Test
    void rejectsZero() {
        runner.withPropertyValues("limits.max-items=0")
            .run(context ->
                assertThat(context.getStartupFailure()).isNotNull()
            );
    }
}
```

To behave as expected, the test context needs a Jakarta Validation provider and Spring Boot integration properly set up, such as via `spring-boot-starter-validation` in the project.

`PropertyPlaceholderAutoConfiguration` in the imports above is unnecessary for this core test and can be omitted for brevity. The key point is `ApplicationContextRunner.withPropertyValues(...)` supplying test properties and the callback inspecting the context creation outcome.

**Distinguish two goals:**

- `@SpringBootTest(properties=...)`: starts a context cleanly with **valid configuration** to test beans and behavior.
- `ApplicationContextRunner`: ideal for testing multiple valid combinations as well as **configurations causing startup failures**.

Do not write a `@SpringBootTest` expecting startup failure and try to assert it inside a test method that will never execute.

## 27. Context Caching: Why Multiple Tests Share an ApplicationContext

Spring TestContext Framework maintains a context cache. When multiple test classes share compatible context configurations, the framework reuses the cached context instead of recreating it from scratch, speeding up the suite.

Test configuration inputs affecting the cache key include:

- Loaded configuration classes.
- Active profiles.
- Inline test properties.
- Test property source locations.
- Context customizers, including dynamic or test-specific sources.
- Parent context, loader, and other TestContext options.

Hence two classes:

```java
@SpringBootTest(properties = "app.mode=A")
class ModeATest {}
```

and:

```java
@SpringBootTest(properties = "app.mode=B")
class ModeBTest {}
```

generally do not share the exact same context because their test properties differ.

However, **do not treat caching as a business state management mechanism**. If a test mutates a singleton bean's state, other tests sharing that cached context will observe the mutation. Isolate test state, reset data, or use suitable tools; do not rely on changing an inline property to work around state leakage.

### 27.1. When to Use @DirtiesContext

`@DirtiesContext` marks the context as dirty so it is not reused normally.

Do not place `@DirtiesContext` on every class merely because it uses `@SpringBootTest(properties=...)`. Distinct inline properties already yield distinct context cache keys.

Overusing `@DirtiesContext` increases context startups and slows the test suite. Use it only when a test genuinely mutates context state that cannot be cleaned up more cheaply or cleanly.

## 28. Avoiding System.setProperty in Parallel Tests

Writing:

```java
@Test
void something() {
    System.setProperty("notification.max-attempts", "7");
    // ...
}
```

carries serious risks:

1. System properties are **JVM-shared state**.
2. Parallel tests can overwrite each other's values.
3. Forgetting cleanup corrupts subsequent tests.
4. If the Spring context already started before the test method, the change arrives too late.
5. An already-created `@ConfigurationProperties` bean does not automatically rebind.
6. Test execution order accidentally determines pass/fail.

`@SpringBootTest(properties=...)` is much better when configuring values for **a test class's context initialization**. It keeps test setup declarative and avoids global side effects.

If you must test code outside Spring that reads system properties directly, manage scope and state restoration explicitly—that is a different problem from Spring Boot externalized configuration.

## 29. Managing Similar Overrides Across Multiple Test Classes

A codebase may have many tests all needing:

```java
"app.scheduler.enabled=false"
"app.outbound.enabled=false"
"notification.timeout=100ms"
```

There are three ways to organize this:

### 29.1. Inline per Class

Ideal when 1–3 keys are specific to a test:

```java
@SpringBootTest(properties = {
    "app.scheduler.enabled=false",
    "notification.timeout=100ms"
})
class NotificationServiceTest {}
```

Pro: reading the test class immediately shows its config. Con: repetition across many classes.

### 29.2. Shared Test Profile

Create `src/test/resources/application-test.yml` and use:

```java
@ActiveProfiles("test")
@SpringBootTest
class NotificationServiceTest {}
```

Ideal for a shared baseline test configuration. Individual classes can still combine `properties` for minor overrides.

### 29.3. Composed Annotation for Shared Policy

Java allows custom composed test annotations:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.Target;
import org.springframework.boot.test.context.SpringBootTest;

import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Target(TYPE)
@Retention(RUNTIME)
@SpringBootTest(properties = {
    "app.scheduler.enabled=false",
    "app.outbound.enabled=false"
})
public @interface SafeIntegrationTest {
}
```

Then:

```java
@SafeIntegrationTest
class ApplicationSafetyTest {}
```

This standardizes a common baseline across tests. Avoid packing every module's properties into one giant annotation, though, or tests lose clarity on what they actually depend on.

If a class using a composed annotation needs its own overrides, understand how annotations are inherited and merged in TestContext. Do not assume placing two `@SpringBootTest` annotations or two meta-annotations of the same type automatically merges in intuitive order.

## 30. When Should You Avoid @SpringBootTest?

`@SpringBootTest` can load far more auto-configurations and beans than needed. Using it to test pure Java logic makes test suites unnecessarily slow.

### 30.1. Unit Testing Services Without Spring

```java
@Test
void planUsesProvidedProperties() {
    NotificationProperties props =
        new NotificationProperties(
            true,
            "Unit Sender",
            3,
            Duration.ofSeconds(1)
        );

    NotificationPlanService service =
        new NotificationPlanService(props);

    assertThat(service.currentPlan().maxAttempts())
        .isEqualTo(3);
}
```

This is a unit test; neither `@SpringBootTest` nor YAML is needed when testing pure service logic.

### 30.2. Testing Small Binder/Auto-Configuration Scopes

`ApplicationContextRunner` builds a small context, supplies properties, and checks conditions. It works well for testing many pass/fail configuration combinations.

### 30.3. Testing MVC Slices

If only testing a controller, `@WebMvcTest` with mocked dependencies fits better than a full context. When verifying binder, services, and full wiring together, `@SpringBootTest` makes sense.

**Selection rule:** use the lightest tool that still verifies what needs to be proven. In this lesson, `@SpringBootTest(properties=...)` is chosen intentionally to test configuration **inside a Spring Boot context**.

## 31. Overriding Properties to Avoid Calling Real Services

A practical goal is keeping integration tests from contacting production resources accidentally.

For example, the application has:

```yaml
partner:
  endpoint: https://partner.example.invalid
```

The test can specify:

```java
@SpringBootTest(properties = {
    "partner.endpoint=http://127.0.0.1:18080",
    "partner.outbound.enabled=false"
})
```

However, **a property override alone does not guarantee code skips network calls**. That works only if the bean/client actually reads `partner.outbound.enabled` and respects disabling outbound connections.

Additional safeguards:

- Use fake adapters or mock beans for clients during logic tests.
- For HTTP integration tests, use a mock server with explicit lifecycle and port management.
- Use random ports and `@DynamicPropertySource` when needed.
- Never place production endpoints or production tokens in test fixtures.
- Ensure `ApplicationRunner`/`CommandLineRunner` beans do not execute real external tasks at startup.
- Do not assume `webEnvironment=NONE` stops arbitrary beans from opening outbound connections: it only disables the application's web environment.

Properly configured tests still require architectural isolation to prevent external side effects.

## 32. Certain Property Names Affect Early Startup Phases

`@SpringBootTest(properties=...)` is applied while constructing the test context, before most binding and bean creation. Thus it works well for many startup properties.

Example:

```java
@SpringBootTest(properties = {
    "spring.main.banner-mode=off",
    "logging.level.com.example.notification=DEBUG"
})
```

However, properties read by Spring Boot during very early stages can have timing subtleties. If testing specialized bootstrap behaviors—such as Config Data location/imports, logging initialization, or custom `SpringApplication` builders—do not assume every inline property acts identically to arguments passed before `SpringApplication` begins.

Check the documentation for your Boot version and write dedicated bootstrap integration tests where needed. This lesson focuses on **values consumed by beans inside the context**, where inline test properties are the standard mechanism.

### 32.1. The main Method Is Not Always Invoked

In modern `@SpringBootTest`, without specifying `useMainMethod`, the test context is usually built without invoking the application's `main` method. If `main` programmatically sets profiles or default properties, test behavior can differ from running the JAR.

When you need to test logic inside `main`, pick an appropriate `useMainMethod` option for your Boot version, such as `SpringBootTest.UseMainMethod.ALWAYS`. Do not enable it just for routine property overrides.

## 33. Overriding the Same Key Across Classes and Test Inheritance

A base test can define shared properties:

```java
@SpringBootTest(properties = {
    "notification.enabled=false",
    "notification.timeout=1s"
})
abstract class BaseNotificationIntegrationTest {}
```

Subclasses inherit test configurations per Spring TestContext rules. Keep in mind, though, that **annotation inheritance and merging do not automatically mean every `String[] properties` across two same-named annotations concatenates as desired**.

If a subclass needs different overrides, safer patterns are:

- Shared test profile + inline overrides on the subclass.
- Or a clearly designed composed annotation.
- Or placing `@SpringBootTest` directly with the complete property set on each class.
- Avoid nesting multiple meta-annotations with unclear precedence.

Above all, every test should make it obvious **what configuration actually loaded**. If you have to trace three inheritance layers just to learn `timeout`, the test setup is too hard to maintain.

## 34. Working with @Nested Test Classes

JUnit Jupiter supports `@Nested` for grouping tests. In Spring TestContext, annotations and test configurations can be inherited from outer classes per framework and version rules.

Do not assume every nested class automatically gets a fresh `ApplicationContext` with separate overrides just because it is an inner class.

If two scenarios need completely different contexts:

```text
Case A: notification.enabled=true
Case B: notification.enabled=false
```

two independent test classes are easiest for newcomers to read. If you need flexible per-scenario testing in one file, `ApplicationContextRunner` offers a cleaner per-scenario model than overlapping `@SpringBootTest` setups.

## 35. Troubleshooting "Failed to load ApplicationContext"

Common causes related to overridden properties:

### 35.1. Malformed Property String

```java
@SpringBootTest(properties = "notification.timeout:")
```

If `notification.timeout=100ms` was intended but an empty or missing value was written, binder fails or produces unexpected values. Use `key=value`.

### 35.2. Unconvertible Value

```java
@SpringBootTest(properties = "notification.max-attempts=seven")
```

Cannot convert `seven` to `int`. Fix the test data or match the target type.

### 35.3. Conditionally Created Bean Disabled

```java
@SpringBootTest(properties = "audit.enabled=false")
```

If another service constructor requires `AuditSink` while that bean exists only when auditing is enabled, the context fails from a missing dependency. Design optional dependencies/conditions cleanly or supply an appropriate fake bean in tests.

### 35.4. Configuration Triggers Real External Connections

A test may fail because a client tries to connect to a database, broker, or API at startup. Overriding a property does not automatically mock external dependencies. Use mocks/fake servers, Testcontainers, or architectural toggles to disable startup connections.

### 35.5. Configuration Class Not Found

If the test resides outside the app's package or lacks a discoverable `@SpringBootConfiguration`, specify:

```java
@SpringBootTest(classes = NotificationApplication.class)
```

to point directly to the application class.

### 35.6. Test Reuses Mutated Bean State

When contexts are cached, a singleton holding state modified by an earlier test can affect later tests. Keep tests isolated or reset state; do not mistake this for a precedence bug in `@SpringBootTest.properties`.

### 35.7. Wrong Profile or Higher-Priority Test Source

Check `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, test command-line args, and custom context initializers. Never assume a single annotation string is the only place setting a key.

### 35.8. Test Runs in the Wrong Module

In multi-module projects, a test might not be loading the `application.yml` you currently have open in your editor. Check the test runtime classpath, configuration package, and module boundaries.

## 36. Systematic Diagnosis Steps

When a test expects `maxAttempts=7` yet gets `2`:

1. Verify the annotation sits on the **exact test class being executed**.
2. Verify the string is `"notification.max-attempts=7"`.
3. Verify the `@ConfigurationProperties(prefix="notification")` class has field `maxAttempts`.
4. Verify Spring Boot registered the properties bean.
5. Assert `Environment.getProperty("notification.max-attempts")`.
6. Assert `NotificationProperties.maxAttempts()`.
7. If Environment is right yet the bean is wrong, check binding, bean instances, and creation timing.
8. If Environment is wrong, check `@TestPropertySource`, `@DynamicPropertySource`, or other test sources defining the same key.
9. Check test context caching and global state mutations from other tests.
10. Do not edit `application.yml` before finding the real root cause.

A tiny diagnostic check like:

```java
@Test
void investigatesOnlyRelevantProperty() {
    assertThat(environment.getProperty(
            "notification.max-attempts")).isEqualTo("7");

    assertThat(properties.maxAttempts()).isEqualTo(7);
}
```

is usually far more useful than printing all environment variables or turning on DEBUG logs across the entire application.

## 37. Comparison Table of Ways to Supply Test Values

| Approach | Scope | Strengths | Limitations |
| --- | --- | --- | --- |
| `@SpringBootTest(properties=...)` | Class's Boot test context | Concise, overrides clearly visible | Unsuitable for huge config sets |
| `@TestPropertySource(properties=...)` | Spring TestContext | Standard Spring Test inline properties | Can overlap with Boot inline |
| `@TestPropertySource(locations=...)` | Spring TestContext | Reusable fixture files | Requires managing resource locations |
| `@ActiveProfiles("test")` | Test context profile | Shared profile config and bean conditions | Does not override single keys if file omits them |
| `@DynamicPropertySource` | Test context with runtime values | Ideal for random ports/Testcontainers | Must manage resource lifecycles |
| `ApplicationContextRunner.withPropertyValues(...)` | Small context per scenario | Multiple combinations, startup failures | Does not test full app by default |
| `System.setProperty(...)` | Entire JVM | Tests direct system property readers | Easy to leak state across tests |
| Editing `application.yml` manually | Source file | Discouraged for automation | Causes conflicts and side effects |

When the requirement is simply "pass two or three test values differing from the main file," `@SpringBootTest(properties=...)` fits very cleanly.

## 38. Common Mistakes and How to Avoid Them

### 38.1. Writing Properties as YAML

Do not put nested YAML strings inside the annotation; use dotted keys and `=`.

### 38.2. Prepending -- Before Keys

`--demo.mode=fast` is command-line argument syntax, not a property name for `properties`.

### 38.3. Thinking the Annotation Modifies application.yml

It adds a test property source; the file on disk is untouched. After the test finishes, no "new values" remain in source files.

### 38.4. Asserting Only a String from Environment

That does not prove the service consumes the right bean. Test typed properties or consuming bean behavior.

### 38.5. Using Wrong Keys or Prefixes

`notification.max-attmpts` will not match `maxAttempts`. Check canonical key names.

### 38.6. Misunderstanding @Value Defaults

If a test source supplies an empty string for a key, that behaves differently from omitting the key and letting fallback apply.

### 38.7. Expecting Lists to Always Merge Element-by-Element

Spring Boot applies specific rules for collections across sources; test real binding outcomes instead of guessing.

### 38.8. Expecting @SpringBootTest to Start a Real Server

Default `MOCK` does not open a port. Use `RANDOM_PORT` for real HTTP; `NONE` when web is not needed.

### 38.9. Running All Tests in One Context While Mutating Properties Mid-Run

Already-created `@ConfigurationProperties` records/beans do not rebind automatically. Separate contexts or use a runner for multiple scenarios.

### 38.10. Putting @DirtiesContext Everywhere

Unnecessary when configurations are declared explicitly; wastes startup time.

### 38.11. Changing Properties via System.setProperty After Autowiring

Too late for many beans and risks breaking other tests in the same JVM.

### 38.12. Hitting Real Environments During Tests

Overriding one endpoint key does not guarantee all connections are disabled. Use explicit fakes or test resources without production credentials.

### 38.13. Skipping Test Profiles

An `application-test.yml` file takes effect only when the matching profile is activated via Boot mechanisms. Use `@ActiveProfiles` when testing profiles.

### 38.14. Overlapping @TestPropertySource and @DynamicPropertySource

If the same key appears in both, understand precedence; normally avoid overlap and pick one owning source.

### 38.15. Using @SpringBootTest Just to Test Addition

A full context is overkill for pure Java logic. Choose unit tests or lightweight runners.

### 38.16. Assuming Startup Failures Can Be Asserted Inside @SpringBootTest Methods

`@SpringBootTest` builds the context before running methods; if binding fails at startup, the method never executes. Use `ApplicationContextRunner` for expected failures.

### 38.17. Thinking Wrong-Type Properties Fall Back to YAML Defaults

A malformed value in a higher-priority source fails the context rather than falling back to YAML. That is intentional fail-fast behavior.

### 38.18. Logging All Configuration Values While Debugging

Never print the whole `Environment` or `@ConfigurationProperties` containing secrets. Use fake data and targeted assertions.

## 39. Exercise 1: Overriding a Single Property

Given YAML:

```yaml
catalog:
  enabled: false
  max-items: 100
```

And record:

```java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(boolean enabled, int maxItems) {}
```

Write `@SpringBootTest(properties="catalog.max-items=25")` and assert:

```text
enabled  = false
maxItems = 25
```

Explain why `enabled` stays `false` while `maxItems` is overridden.

## 40. Exercise 2: Multiple Properties with Different Types

Given:

```yaml
reports:
  title: Daily Report
  batch-size: 50
  flush-interval: 2s
```

Task: test title `"Test Report"`, batch size `10`, and flush interval `500ms`.

Annotation snippet:

```java
@SpringBootTest(properties = {
    "reports.title=Test Report",
    "reports.batch-size=10",
    "reports.flush-interval=500ms"
})
```

Assert `String`, `int`, and `Duration.ofMillis(500)` after binding. If Java has `Duration flushInterval` and the test supplies `five-hundred-ms`, predict the failure type.

## 41. Exercise 3: Combining @ActiveProfiles with Overrides

Create:

```yaml
# application.yml
worker:
  queue: default
  batch-size: 100
```

```yaml
# application-test.yml
worker:
  queue: test
  batch-size: 25
```

Test:

```java
@ActiveProfiles("test")
@SpringBootTest(properties = "worker.batch-size=5")
```

Predict:

```text
worker.queue      = test
worker.batch-size = 5
```

Write an explanation in exact sequence: profile selection, Config Data source resolution, inline test override application, and binder bean creation.

## 42. Exercise 4: Conditional Bean Flag

Given:

```java
@Component
@ConditionalOnProperty(
    prefix = "feature",
    name = "enabled",
    havingValue = "true"
)
class FeatureClient {}
```

Write two test classes with properties:

```java
"feature.enabled=true"
"feature.enabled=false"
```

Assert the bean is present when enabled and absent when disabled. Do not use `System.setProperty` inside a test method to flip state.

## 43. Exercise 5: Why Are Tests Non-Independent?

Test A calls `System.setProperty("worker.batch-size", "5")` without restoring it. Test B expects YAML defaults and sometimes receives 5 instead of 100.

Explain:

- Why system properties are shared across the JVM.
- Why test execution order can change outcomes.
- How to convert test A to `@SpringBootTest(properties=...)`.
- How to keep B free from global state.
- When state cleanup or separate test contexts are needed.

## 44. Exercise 6: Testing Startup Failures

Record:

```java
@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
    @Min(1) int batchSize
) {}
```

Goal: confirm `worker.batch-size=0` is rejected when validated binding runs.

Questions:

1. Why is writing `@SpringBootTest(properties=...)` and expecting a `@Test` method to assert startup failure the wrong approach?
2. How do you use `ApplicationContextRunner.withPropertyValues("worker.batch-size=0")`?
3. Why does the project need a compatible validation provider?
4. What happens if `0` is replaced by `abc` when the field is `int`?

## 45. Exercise 7: Working with Testcontainers

A test database gets a different Testcontainers JDBC URL on every run.

Explain why:

```java
@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:postgresql://localhost:5432/test"
})
```

fails when the container actually binds a random port, and why `@DynamicPropertySource` or Spring Boot/Testcontainers service connection support fits better.

Never use production database URLs or credentials in tests just to make setup "easy to run."

## 46. Exercise 8: Spotting Broken Annotations

What issues exist in the following snippet?

```java
@SpringBootTest(properties = {
    "--mail.host=localhost",
    "mail.timeout: 2s",
    "classpath:/integration.properties"
})
```

Hints:

- `--mail.host=localhost` is command-line argument syntax, not a canonical key for `properties`.
- `mail.timeout: 2s` may parse under Java properties rules, yet `mail.timeout=2s` is clearer for the `@SpringBootTest` API.
- `classpath:/integration.properties` is not file-loading syntax for `properties`. Use `@TestPropertySource(locations=...)` for fixture files.

Rewrite the annotation cleanly with clear intent.

## 47. Exercise 9: Testing Typed Configuration

Given:

```java
@ConfigurationProperties(prefix = "image")
public record ImageProperties(
        URI endpoint,
        Duration timeout,
        int maxRetries
) {}
```

Test:

```java
@SpringBootTest(properties = {
    "image.endpoint=https://image.example.invalid/api",
    "image.timeout=750ms",
    "image.max-retries=4"
})
```

Write three assertions using `URI.create(...)`, `Duration.ofMillis(750)`, and `int 4`. Why is checking the typed object more meaningful than checking three strings in `Environment`?

## 48. Exercise 10: Evaluating Isolation

An integration test declares:

```java
@SpringBootTest(properties = {
    "external.service.enabled=false"
})
```

yet a bean constructor still opens a socket to an external system.

Analyze:

- Why an unused key cannot disable the connection.
- How to fix the bean configuration so the flag takes effect.
- When a fake adapter or mock server is required.
- Why `webEnvironment=NONE` does not block outbound network requests.
- The role of integration tests in catching startup side effects.

## 49. Checklist When Writing Tests Using properties

A quick checklist when preparing tests:

1. **Is a Spring Boot context actually needed?** If not, write a unit test.
2. **Is it on the test class?** `@SpringBootTest` is a class-level annotation.
3. **Is the right app configuration selected?** Specify `classes` if needed.
4. **Is the syntax clean?** Use `"key=value"`; avoid `--` prefixes or file paths inside `properties`.
5. **Are canonical names used?** For example, `notification.max-attempts`.
6. **Are only needed keys overridden?** Let remaining keys come from standard sources.
7. **Which profile is active?** Use `@ActiveProfiles` if needed.
8. **Do other dynamic test sources touch the same key?** Minimize overlap.
9. **Is the bean registered and bound?** Assert typed properties.
10. **Does the test cause external side effects?** Use fake/mock servers and dummy data.
11. **Is a real web server required?** Use `NONE` or default `MOCK` for config tests.
12. **Are startup failures expected?** Consider `ApplicationContextRunner`.
13. **Does the test dirty singleton context state?** Reset state; avoid overusing `@DirtiesContext`.
14. **Does the test depend on CI machine values?** Override for tests or use explicit fixtures.
15. **Is a failure easy to diagnose?** Assert both `Environment` and bound beans.
16. **Could secrets be logged accidentally?** Use safe dummy test data only.

Addressing these points makes `@SpringBootTest(properties=...)` tests far more repeatable than editing config files manually or mutating JVM-wide state.

## 50. Summary

`@SpringBootTest(properties = ...)` is a **declarative way to supply test properties** when Spring Boot builds an `ApplicationContext` for integration testing.

Core syntax:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "notification.enabled=true",
        "notification.max-attempts=7",
        "notification.timeout=250ms"
    }
)
class NotificationConfigurationTest {
    // @Test methods and assertions
}
```

Flow:

```text
application.yml / application-test.yml / env / ...
                         |
                         v
              Test Environment
                         ^
                         |
          @SpringBootTest(properties)
                         |
                         v
               Effective values
                         |
               +---------+---------+
               |         |         |
               v         v         v
          Environment  @Value  @ConfigurationProperties
                                     |
                                     v
                                Service bean
```

Key points to remember:

1. **Does not edit `application.yml`.** Overrides live inside the test context.
2. **Use `key=value` strings**, as one or more elements of `String[]`.
3. **Test properties generally beat standard app config**, including YAML, environment variables, and system properties when no higher-priority test source competes.
4. **Overrides apply per key**, without needing to redeclare the entire group; check binder rules for Lists/Maps.
5. **Test values are converted by Binder** into `Duration`, `URI`, `int`, `boolean`, or other target types.
6. **Can drive bean conditions** such as `@ConditionalOnProperty` because properties apply during context initialization.
7. **`@ActiveProfiles`, `@TestPropertySource`, and `@DynamicPropertySource` serve related yet distinct needs**; avoid unintentional key collisions.
8. **Never use `System.setProperty` to alter an already-built context**, especially in parallel test suites.
9. **Use `ApplicationContextRunner` for intentional startup failure tests**, rather than letting `@SpringBootTest` fail before test methods run.
10. **Pick the right scope:** full context for wiring/binding, unit tests for Java logic, slices for single functional layers.

Used well, `@SpringBootTest(properties=...)` turns a configuration scenario into a **reproducible test**: readers immediately see the input conditions, Spring Boot constructs beans with those values, and assertions verify the expected behavior.

### Official Documentation References

- [Spring Boot — SpringBootTest annotation API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/SpringBootTest.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html)
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
