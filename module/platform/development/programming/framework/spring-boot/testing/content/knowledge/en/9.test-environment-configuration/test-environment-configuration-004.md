# @ActiveProfiles and application-test.yml

In Spring Boot testing, the same code may have to run under different configurations: production sends real emails, whereas tests only record send requests; production connects to live databases and external services, whereas tests use isolated databases or adapters. If these settings get mixed up, tests become slow, flaky, or dangerous by accidentally hitting real systems.

**`@ActiveProfiles`** and **`application-test.yml`** solve two related—but distinct—parts:

- `@ActiveProfiles("test")` tells the **Spring TestContext Framework** that the `test` profile must be active when building the test's `ApplicationContext`.
- `application-test.yml` is a **profile-specific configuration file** that **Spring Boot's Config Data** mechanism searches for and loads when the `test` profile is active in an application bootstrapped by Spring Boot.
- The annotation selects the **profile**; the YAML file declares **configuration values**. Spring `@Profile` determines **which bean definitions are activated**; Spring Boot merges property sources to determine the **final effective values**.
- Simply having a file named `application-test.yml` does not activate the `test` profile automatically. And `@ActiveProfiles` does not automatically cause YAML files to be processed in every way of loading a context: you need the appropriate Boot configuration flow, such as `@SpringBootTest`.

The goal of this lesson is to understand the mechanics, write a Java 17+/Spring Boot/JUnit 5 example, design safe test environments, and diagnose configuration issues without guessing from filenames.

## 1. The big picture: profiles, beans, and properties

Imagine an application with a service that greets users. In production, the service uses the prefix `Hello` and may send notifications through an outbound port. In tests, the prefix is `Xin chào` and sending is either disabled or replaced by an in-memory recording port.

Processing flow:

```text
JUnit Jupiter test
   |
   | @SpringBootTest + @ActiveProfiles("test")
   v
Spring TestContext / SpringExtension
   |
   | bootstraps ApplicationContext with Spring Boot
   v
SpringApplication + Config Data
   |                               |
   | application.yml               | application-test.yml
   | (common defaults)             | (overrides when test is active)
   v                               v
              Spring Environment
                       |
              +--------+---------+
              |                  |
       @Profile("!test")   @Profile("test") or @Imported test bean
       production bean      controlled fake bean
              |                  |
              +--------+---------+
                       |
             Beans injected into service
                       |
                 Test assertions
```

Distinguish three concepts:

| Concept | Role | Example |
|---|---|---|
| **Active profile** | Environment name marked active by Spring | `test`, `integration`, `local` |
| **Property source** | Provider supplying key–value pairs into Spring `Environment` | `application.yml`, `application-test.yml`, env vars, test properties |
| **Conditional bean definition** | Decides which bean gets created based on profiles | `@Profile("!test")` or `@Profile("test")` |

Activating a profile **does not mean** every dependency automatically turns into a fake. Only beans and settings that actually declare profile conditions or read the relevant properties change behavior.

## 2. What does `@ActiveProfiles` do exactly?

`@ActiveProfiles` lives in package:

```java
import org.springframework.test.context.ActiveProfiles;
```

Common usage in integration tests:

```java
@SpringBootTest
@ActiveProfiles("test")
class MyIntegrationTest {
    // @Test methods use an ApplicationContext with the "test" profile.
}
```

The snippet above only illustrates the annotation; it is not a complete test.

For TestContext, this annotation:

1. Specifies the active profile or profiles when the test context is loaded.
2. Causes Spring to evaluate `@Profile` conditions on `@Component`, `@Configuration`, or `@Bean` methods.
3. Contributes to the context configuration key used to decide context reuse from cache.
4. Supports inheriting profiles from superclasses or enclosing classes per Spring TestContext rules.
5. Can specify multiple profiles and a custom `ActiveProfilesResolver` when specialized behavior is needed.

Multiple profiles example:

```java
@ActiveProfiles({"test", "integration"})
class DatabaseIntegrationTest {
    // Illustration: both profiles are activated.
}
```

**Common points of confusion:**

- `@ActiveProfiles` is a **Spring TestContext** annotation, not a general way to configure a production application running via `java -jar`.
- If a test uses plain JUnit without `SpringExtension`/Boot TestContext, writing this annotation **does not load a context**.
- Once you declare `@ActiveProfiles` on a test, **TestContext takes profiles from the annotation/resolver** rather than letting environment variables or the `spring.profiles.active` system property silently override the annotation. This behavior is documented by Spring TestContext.
- The profile name `test` is just a common convention, not a magic profile with built-in faking features.
- With Spring Boot 3.x/JUnit Jupiter, `@SpringBootTest` already includes `SpringExtension`; you do not need `@ExtendWith(SpringExtension.class)` just to enable `@ActiveProfiles`.

To verify which profiles are active, inject `Environment` and read `getActiveProfiles()` or call `acceptsProfiles(Profiles.of("test"))`. **Reading profiles is a diagnostic step**, while tests should also assert the resulting configuration values or behaviors to protect.

## 3. What is `application-test.yml` and when is it loaded?

Spring Boot normally searches for Config Data files like `application.properties` or `application.yml`. When the `test` profile is active, it also considers files of the form **`application-{profile}.yml`**, in this case `application-test.yml`, at valid configuration locations.

Example structure:

```text
src/
├── main/
│   ├── java/
│   │   └── ... application code ...
│   └── resources/
│       └── application.yml
└── test/
    ├── java/
    │   └── ... JUnit tests ...
    └── resources/
        └── application-test.yml
```

In a standard Gradle/Maven project, `src/test/resources` is on the **test runtime classpath**. Files there serve tests and are not packaged into the default production artifact. Putting test-only configuration here is a clean separation.

**Typical loading flow with `@SpringBootTest + @ActiveProfiles("test")`:**

1. Boot creates the `ApplicationContext` via `SpringApplication`.
2. Config Data reads common configuration `application.yml`.
3. Because the `test` profile is active, Boot also loads `application-test.yml` from discovered locations.
4. For keys with the same name at matching location levels, values in the profile-specific file can **override** common values.
5. Beans using `@ConfigurationProperties`, `@Value`, or accessing `Environment` receive the effective values from the merged property sources.
6. Beans annotated with `@Profile` are created or excluded based on the active profile set.

For example:

**`src/main/resources/application.yml`**

```yaml
app:
  welcome:
    prefix: "Hello"
    sending-enabled: true
    max-length: 80
```

**`src/test/resources/application-test.yml`**

```yaml
app:
  welcome:
    prefix: "Xin chào"
    sending-enabled: false
```

Under the `test` profile, expected results:

| Key | Common file | Test file | Effective value in example |
|---|---|---|---|
| `app.welcome.prefix` | `Hello` | `Xin chào` | `Xin chào` |
| `app.welcome.sending-enabled` | `true` | `false` | `false` |
| `app.welcome.max-length` | `80` | Not declared | `80` |

That means **the profile-specific file only needs to declare differing properties**; common properties still apply. Do not copy all of `application.yml` into `application-test.yml`, as duplication increases maintenance cost and lets test config drift out of date.

**Important:** the example above assumes no higher-precedence source defines those same keys. Environment variables, system properties, inline test properties, dynamic configuration, or external sources can change final values. Therefore, when debugging, inspect the **effective property** rather than just reading one file.

## 4. The test profile should not use production configuration

A safe test environment requires real boundaries, not just the `test` label. For example:

- Email, payment, message broker, and object storage endpoints must be fakes, mock servers, isolated containers, or authorized sandbox accounts.
- Test databases must use dedicated schemas/databases and self-managed test data; never mix with real data.
- Real credentials must never be committed to source-controlled YAML. Use CI/test-runner secret mechanisms for test credentials if unavoidable.
- Any external side effects outside the database—such as sending messages, webhooks, files, or real HTTP requests—must be controlled separately; transaction rollbacks do not undo them.
- Set appropriate timeouts, fixed test data, and cleanup for the test tier.

**Setting `sending-enabled: false` only works if the code actually reads and respects that property.** If another bean still fires HTTP requests directly, the test profile will not stop it. In the upcoming example, we both swap out the external adapter with a fake bean and check the YAML flag.

## 5. Complete example: Spring Boot 3.x, Java 17+, JUnit Jupiter 5

Let us build a minimal application that:

- Returns `Hello, Mai!` under common configuration.
- When the `test` profile is active, returns `Xin chào, Mai!` and **does not send a notification** due to `sending-enabled: false`.
- Only includes the production delivery adapter when the `test` profile is not active.
- In tests, brings a message-recording adapter into the context via `@TestConfiguration`.
- Includes a second test proving you can override a single property for one case while keeping the `test` profile.

The tests focus on **observable behavior and what Boot actually injects**, not just comparing filenames.

### 5.1. Directory layout

```text
src/
  main/
    java/com/example/profiles/
      ProfileDemoApplication.java
      WelcomeSettings.java
      DeliveryPort.java
      ConsoleDeliveryPort.java
      WelcomeService.java
    resources/
      application.yml
  test/
    java/com/example/profiles/
      RecordingPortConfig.java
      WelcomeProfileTest.java
      WelcomeOverrideTest.java
    resources/
      application-test.yml
```

Test classes in the same `com.example.profiles` package can use package-private fixture types.

### 5.2. Bootstrapping Spring Boot and scanning `@ConfigurationProperties`

**`src/main/java/com/example/profiles/ProfileDemoApplication.java`**

```java
package com.example.profiles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProfileDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` enables standard configuration/auto-configuration. `@ConfigurationPropertiesScan` locates `@ConfigurationProperties` types in the relevant package (including `WelcomeSettings`).

### 5.3. Strongly typed configuration with a Java record

**`src/main/java/com/example/profiles/WelcomeSettings.java`**

```java
package com.example.profiles;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.welcome")
public record WelcomeSettings(
        String prefix,
        boolean sendingEnabled,
        int maxLength) {
}
```

In Spring Boot 3.x, a record with a single canonical constructor uses constructor binding without needing `@ConstructorBinding`. Boot performs **relaxed binding**, so YAML key `sending-enabled` maps to record component `sendingEnabled`, and `max-length` maps to `maxLength`.

`@ConfigurationProperties` describes **configuration value** binding, not profile activation. The `@ActiveProfiles` annotation on the test determines the profile and thereby affects the values seen by the binder.

If a required property is missing or configured with the wrong type, the context may fail to construct the bean properly. For strict business configuration, consider validation (`@Validated` and constraints with an appropriate validation dependency); avoid silently accepting `null` or primitive defaults when configuration errors ought to be caught.

### 5.4. Isolating side effects behind an outbound port

**`src/main/java/com/example/profiles/DeliveryPort.java`**

```java
package com.example.profiles;

public interface DeliveryPort {
    void send(String destination, String message);
}
```

**`src/main/java/com/example/profiles/ConsoleDeliveryPort.java`**

```java
package com.example.profiles;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("!test")
public class ConsoleDeliveryPort implements DeliveryPort {

    @Override
    public void send(String destination, String message) {
        System.out.println("To " + destination + ": " + message);
    }
}
```

This is a **pedagogical console adapter**, not a real production email/payment adapter. `@Profile("!test")` indicates the bean is registered when **the `test` profile is not active**. Thus, it is excluded from the context when running under the `test` profile. In a real system, profile conditions should reflect deliberate environment policies rather than serving as the sole safeguard against side effects.

### 5.5. Service running real business code

**`src/main/java/com/example/profiles/WelcomeService.java`**

```java
package com.example.profiles;

import org.springframework.stereotype.Service;

@Service
public class WelcomeService {
    private final WelcomeSettings settings;
    private final DeliveryPort deliveryPort;

    public WelcomeService(
            WelcomeSettings settings,
            DeliveryPort deliveryPort) {
        this.settings = settings;
        this.deliveryPort = deliveryPort;
    }

    public String welcome(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        String normalized = name.strip();
        if (normalized.length() > settings.maxLength()) {
            throw new IllegalArgumentException("name too long");
        }

        String message = settings.prefix() + ", " + normalized + "!";
        if (settings.sendingEnabled()) {
            deliveryPort.send(normalized, message);
        }
        return message;
    }
}
```

The service receives both settings and the port via constructor injection; **it does not read `application-test.yml` using file APIs**. It only interacts with beans created by Spring. Consequently, the exact same `WelcomeService` class runs in production and tests while delivery behavior and prefix change with the environment.

Checks for `null` and `blank` names happen before `strip()`. `maxLength` uses `80` from the common file in the example, demonstrating that test configuration does not need to repeat every property.

### 5.6. YAML files for environments

**`src/main/resources/application.yml`**

```yaml
app:
  welcome:
    prefix: "Hello"
    sending-enabled: true
    max-length: 80
```

**`src/test/resources/application-test.yml`**

```yaml
app:
  welcome:
    prefix: "Xin chào"
    sending-enabled: false
```

Use the exact filenames and directories. The test file sits in **test resources**, placed on the classpath when running JUnit. Do not declare `spring.profiles.active: test` inside `application-test.yml` — this file is selected **after** the profile is already active, and Spring Boot disallows declaring `spring.profiles.active` in profile-specific documents.

YAML uses indentation to express maps; use spaces instead of tabs. For string values containing spaces or values YAML might parse as another type, use quotes to make intent explicit.

### 5.7. Creating a fake port in test scope, outside production sources

**`src/test/java/com/example/profiles/RecordingPortConfig.java`**

```java
package com.example.profiles;

import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class RecordingPortConfig {

    @Bean
    RecordingDeliveryPort recordingDeliveryPort() {
        return new RecordingDeliveryPort();
    }
}

final class RecordingDeliveryPort implements DeliveryPort {
    private final List<String> messages = new ArrayList<>();

    @Override
    public void send(String destination, String message) {
        messages.add(destination + "|" + message);
    }

    List<String> messages() {
        return List.copyOf(messages);
    }
}
```

`@TestConfiguration` marks this as test-specific configuration; `@Import(RecordingPortConfig.class)` on the test class explicitly imports this bean. `ConsoleDeliveryPort` is excluded by `@Profile("!test")`, so under the `test` profile only the appropriate fake port is wired into `WelcomeService`.

The fake records into an in-memory list. This is a **synchronous fixture** for illustration; if tests involve concurrency, multiple threads, or sharing an instance across methods with side effects, stronger isolation is needed. Ideally each test/fixture stays independent; never share a mutable list across tests running in parallel.

### 5.8. Profile test: YAML values, bean selection, and real behavior

**`src/test/java/com/example/profiles/WelcomeProfileTest.java`**

```java
package com.example.profiles;

import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ProfileDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Import(RecordingPortConfig.class)
class WelcomeProfileTest {

    @Autowired
    WelcomeService service;

    @Autowired
    WelcomeSettings settings;

    @Autowired
    RecordingDeliveryPort recorder;

    @Autowired
    Environment environment;

    @Test
    void loadsTestProfileAndConfigData() {
        assertTrue(Arrays.asList(environment.getActiveProfiles())
                        .contains("test"));

        assertAll("configuration under test profile",
                () -> assertEquals("Xin chào", settings.prefix()),
                () -> assertFalse(settings.sendingEnabled()),
                () -> assertEquals(80, settings.maxLength()));
    }

    @Test
    void appliesTestSettingsToRealService() {
        assertEquals("Xin chào, Mai!",
                service.welcome("  Mai  "));

        assertEquals(List.of(), recorder.messages(),
                "Should not send message when sending-enabled=false");
    }

    @Test
    void validatesInputWhileUsingTestProfile() {
        assertThrows(IllegalArgumentException.class,
                () -> service.welcome("   "));
    }
}
```

In `loadsTestProfileAndConfigData`, the test verifies the **active profile**, **test YAML property overrides**, and **common properties inherited from `application.yml`**. In `appliesTestSettingsToRealService`, the real service runs while the recording adapter is not called because the flag is disabled.

For `@SpringBootTest`, `webEnvironment=NONE` avoids creating a web environment when HTTP is unnecessary. The test still uses TestContext Framework and a Spring Boot `ApplicationContext`. There is no need to call `SpringApplication.run` manually in tests.

**Note on test independence:** this file has multiple methods sharing the same context and singleton fake, though only `appliesTestSettingsToRealService` checks the messages list and with the flag off it does not mutate the list. In tests that actually trigger sends, reset fixtures or isolate context/bean state to avoid order dependence across tests. JUnit method ordering must not be treated as business sequencing.

### 5.9. A separate test overriding a property while keeping the test profile

Sometimes you want to test the `sending-enabled=true` branch **without changing `application-test.yml` for the entire suite**. You can use `@TestPropertySource(properties=...)`.

**`src/test/java/com/example/profiles/WelcomeOverrideTest.java`**

```java
package com.example.profiles;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ProfileDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Import(RecordingPortConfig.class)
@TestPropertySource(properties = "app.welcome.sending-enabled=true")
class WelcomeOverrideTest {

    @Autowired
    WelcomeService service;

    @Autowired
    WelcomeSettings settings;

    @Autowired
    RecordingDeliveryPort recorder;

    @Test
    void inlineTestPropertyOverridesProfileYamlForThisContext() {
        assertTrue(settings.sendingEnabled());

        assertEquals("Xin chào, Mai!", service.welcome("  Mai  "));
        assertEquals(
                List.of("Mai|Xin chào, Mai!"),
                recorder.messages());
    }
}
```

**Meaning:**

- The profile **is still `test`**, so `application-test.yml` still participates in building the context and the `@Profile("!test")` production adapter is not selected.
- Inline properties from `@TestPropertySource` take higher precedence than the config data file here, making the effective flag `true`.
- Calling the real `WelcomeService` sends exactly one message to the fake `RecordingDeliveryPort`, **not** to the production adapter.
- The two test classes have different property source configurations and therefore typically get **two different cache keys/contexts**. Do not mutate a global property mid-test and expect a `@ConfigurationProperties` bean to automatically rebind; configuration beans are normally bound when the context is built.

## 6. Why can the example above verify profile correctness?

A test that only writes:

```java
@ActiveProfiles("test")
@Test
void profileWorks() {
    assertTrue(true);
}
```

proves nothing about configuration loading. `assertTrue(true)` always passes, even without a context.

A valuable test should protect at least one meaningful contract, for example:

- `Environment` contains the expected profile;
- `WelcomeSettings.prefix()` has the value `Xin chào` instead of `Hello`;
- `WelcomeSettings.sendingEnabled()` is accurately `false`;
- `WelcomeService.welcome(...)` returns the expected string;
- the production bean is excluded and the fake port is injected;
- when the flag is enabled in a separate test context, the message is recorded by the fake.

In a real project, you do not need to assert every single configuration key if they are internal details already proven through behavior. Conversely, safety-critical keys such as sandbox URLs, disabling external delivery, or test database endpoints **deserve explicit assertions** to reduce the risk of accidentally calling real resources.

## 7. How do `@Profile` and `@ActiveProfiles` differ?

**`@ActiveProfiles`** is attached to a **test class** to select active profiles. **`@Profile`** is attached to a **bean/configuration** to govern bean registration conditions.

Example:

```java
@Component
@Profile("!test")
class RealGateway implements Gateway {
    // ...
}

@Component
@Profile("test")
class InMemoryGateway implements Gateway {
    // ...
}
```

This illustrates syntax only, not a standalone file: `Gateway`, imports, and method implementations are omitted.

When `test` is active, only beans matching `@Profile("test")` are accepted, while `@Profile("!test")` is excluded. `@Profile("!test")` does not strictly mean production-only: it also activates under `local`, `dev`, or when no profile is active, as long as `test` is not active.

**Best practice:** in many projects, place test adapters in `src/test/java` using `@TestConfiguration` and `@Import` as shown in the complete example, rather than packaging fakes inside the production artifact. This separation prevents test-only behavior from reaching deployed environments.

### 7.1. Some profile expressions

```java
@Profile("test")               // Only when test is active
@Profile("!prod")              // When prod is not active
@Profile({"local", "test"})     // Either profile is active
@Profile("integration & !prod") // Example AND/NOT expression
```

These illustrate standalone annotations, not a full Java class. In `@Profile({"local","test"})`, the array uses OR semantics. Combined AND/NOT/OR expressions are supported via profile expressions; keep syntax clear and check the Spring docs for your version when using complex combinations.

### 7.2. Beans can conflict when multiple profiles are active

If two beans implement `DeliveryPort` and both are active, type-only injection can trigger `NoUniqueBeanDefinitionException`. The fix is designing mutually exclusive profile conditions, choosing `@Primary`/`@Qualifier` intentionally, or replacing beans with a version-appropriate test override mechanism. **Do not resolve this by scattering fake beans into every test context**, as outcomes become unpredictable.

## 8. Property precedence order: which file wins?

Spring Boot combines multiple `PropertySource`s in priority order. Test configuration can be determined by:

- common file `application.yml`;
- profile-specific file `application-test.yml`;
- external files outside the jar, custom locations, and `spring.config.import`;
- environment variables, JVM system properties, and other runtime sources;
- the `properties` attribute on `@SpringBootTest` or a test slice;
- `@TestPropertySource`, `@DynamicPropertySource` in tests.

Do not memorize a simplified order and assume it holds for every application. Location groups, files outside the jar, combined profiles, inline test properties, and config importers can make ordering nuanced. For the two files in our example on the same classpath, values in `application-test.yml` beat matching keys in `application.yml`, **assuming no higher-precedence source exists**.

Illustrative table:

| Configuration | `prefix` | `sending-enabled` | Explanation |
|---|---|---|---|
| `application.yml` only | `Hello` | `true` | Common values |
| `@ActiveProfiles("test")` + Boot config data | `Xin chào` | `false` | `application-test.yml` overrides |
| Above + `@TestPropertySource(properties="app.welcome.sending-enabled=true")` | `Xin chào` | `true` | Inline test property overrides flag |
| Above, plus a higher-precedence source declaring `app.welcome.prefix` | Depends on source | Per priority source | Cannot conclude from the two files alone |

**`@TestPropertySource(locations="classpath:application-test.yml")` is not the standard way to load YAML.** Spring TestContext's `@TestPropertySource` handles `.properties` format by default (or formats supported via a custom factory); for Boot's profile-specific YAML, let Boot Config Data load the file via the active profile. If you need a non-conventional file, use `spring.config.import` or a compatible property source/factory as appropriate.

## 9. `@ActiveProfiles` vs. `spring.profiles.active`

During **normal application execution**, profiles can be enabled with:

```bash
java -jar app.jar --spring.profiles.active=local
```

Or via environment variable `SPRING_PROFILES_ACTIVE=local`, JVM system property, or suitable configuration. This controls profiles at application runtime.

In **Spring TestContext tests**, `@ActiveProfiles("test")` explicitly declares the test profile on the class. Per Spring TestContext documentation, when this annotation is present, `spring.profiles.active` from system properties or environment variables **does not automatically override the profiles declared in `@ActiveProfiles`**. If external runtime settings must determine test profiles, use an `ActiveProfilesResolver` intentionally with appropriate isolation rather than relying on implicit behavior.

Syntax-only example:

```java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationEnvironmentTest {
    // Test context uses the integration profile via TestContext.
}
```

Still, the `spring.profiles.active` property follows Boot Config Data rules in contexts not governed by `@ActiveProfiles`. Do not merge the two mechanisms into a single mental model.

**Do not put the following inside `application-test.yml`:**

```yaml
spring:
  profiles:
    active: test
```

Spring Boot disallows configuring `spring.profiles.active` inside a **profile-specific** document or one activated by `spring.config.activate.on-profile`. Moreover, it creates a circular dependency: the profile would have to be active already for the file to be chosen. Keep `@ActiveProfiles("test")` on the test class, or place profile-selection settings in a **non-profile-specific** source when running the app.

## 10. Combining multiple profiles and corresponding YAML files

You can run a test with multiple profiles:

```java
@ActiveProfiles({"test", "integration"})
@SpringBootTest
class IntegrationTest {
}
```

If Boot finds `application.yml`, `application-test.yml`, and `application-integration.yml`, the profile-specific files can participate together. When multiple files declare the **same key**, Boot applies a precedence model with *last-wins* rules within the matching profile order/location group. Do not rely on unverified ordering in a complex configuration setup.

Illustrative example:

**`application-test.yml`**

```yaml
app:
  endpoint:
    mode: "fake"
    timeout-ms: 200
```

**`application-integration.yml`**

```yaml
app:
  endpoint:
    timeout-ms: 1000
```

When profiles apply within the same location group in an order allowing the integration file to override, `mode` can remain `fake` while `timeout-ms` becomes `1000`. Whenever the exact value matters, **assert the effective property in the test**, since ordering can vary with configuration layout.

**Recommended scopes:**

- `test` for general tests, fake ports, and safe values.
- `integration` to add configuration for databases/containers/infrastructure.
- `local` for local development—should not be mixed automatically into CI tests if doing so could hit real services.

Avoid creating many profiles just to flip one boolean in a single test. For a minor exception, `@TestPropertySource` or `@SpringBootTest(properties=...)` is usually easier to read.

## 11. Default profile and `@Profile("default")`

When no active profile is explicitly set, Spring has a set of **default profiles**, typically containing `default`. That is different from saying `default` is always active alongside `test`.

For example:

- A `@Profile("default")` bean is only selected when the default profiles condition is active.
- Once `test` is active, the `default` profile by default **no longer activates beans** the way it does when no profiles are active.
- A bean without `@Profile` is normally created in both test and production, unless another condition/config excludes it.

Therefore, do not put `@Profile("default")` on a main bean and then wonder why it disappears under the `test` profile. If a bean should run unless `test` is active, `@Profile("!test")` states that clearly; if a bean is specifically for when no profile is active, `default` has that specific meaning.

Also distinguish **default values from `application.yml`** from the **default profile**. `application.yml` is a common configuration source, not a file exclusively for `@Profile("default")`.

## 12. Another option: multi-document YAML files

You do not have to create a separate `application-test.yml` file. Spring Boot supports multiple documents in a single YAML file using the `---` separator and `spring.config.activate.on-profile`.

Example **alternative file layout**—do not place both simultaneously with the earlier example files if you want to avoid overlapping overrides:

**`src/main/resources/application.yml`**

```yaml
app:
  welcome:
    prefix: "Hello"
    sending-enabled: true
    max-length: 80

---
spring:
  config:
    activate:
      on-profile: "test"
app:
  welcome:
    prefix: "Xin chào"
    sending-enabled: false
```

In this file, the first document holds common configuration; the second document applies only when the `test` profile is active.

Comparison:

| Approach | Advantages | Limitations |
|---|---|---|
| `src/test/resources/application-test.yml` | Keeps test-specific config out of the production artifact; clear test scope | Must ensure test runtime classpath and profile are selected properly |
| `src/main/resources/application-test.yml` | Can be used when running the app itself with a `test` profile | File gets packaged into the artifact; easy to confuse with CI test config |
| Multi-document `application.yml` | Groups short branches and shares structure | Larger file containing environment configs together; harder to audit with many profiles |

Neither wins universally. For **automated tests** needing dedicated configuration and fake adapters, `src/test/resources/application-test.yml` usually maintains cleaner separation.

**Do not place `spring.profiles.active` inside a document with `spring.config.activate.on-profile`.** Boot restricts profile-activation properties to non-profile-specific documents.

## 13. `@ActiveProfiles` and inheritance across test classes

When creating a shared base test class, Spring TestContext supports inheriting active profiles from the superclass by default. Example:

```java
@ActiveProfiles("test")
abstract class BaseContextTest {
}

@ActiveProfiles("integration")
class OrderIntegrationTest extends BaseContextTest {
    // By default, profiles from the base class are inherited
    // and combined with the subclass profile per framework rules.
}
```

This is **illustrative code**, not a complete test. Setting `inheritProfiles = false` on the subclass annotation disables inheriting profiles from the superclass. Tests in nested classes also follow enclosing-class inheritance rules per configuration.

Risk: a test believes only `integration` is active, yet because the superclass still declares `test`, production beans are excluded by `@Profile("!test")` or another test file loads as well. That can cause unexpected test behavior.

**Prevention:** keep test hierarchies shallow; inspect actual active profiles in the context when debugging; do not hide critical profiles deep inside base classes or meta-annotations. When a specific profile is needed, declare it clearly and understand inheritance rules.

## 14. `ApplicationContext` caching and runtime impact of profiles

Spring TestContext Framework caches contexts by configuration combination, including active profiles and many other attributes. Two tests with the same Spring Boot config but different profiles normally produce **two distinct context cache entries**, because the resulting beans and effective properties may differ.

In Spring Framework 6.x, the context cache is typically **static within the test JVM**. It has a default entry limit and LRU eviction. If CI generates too many combinations of profiles/properties/mock beans, reloading contexts can slow down the entire suite.

Example:

```text
Test A: @SpringBootTest + @ActiveProfiles("test")
Test B: same config/profile/test imports
    -> Can share the context within the same JVM if cache keys match.

Test C: @SpringBootTest + @ActiveProfiles("integration")
    -> Different profile, normally does not share a context with A/B.

Test D: @SpringBootTest + @ActiveProfiles("test")
        + @TestPropertySource(properties="app.welcome.sending-enabled=true")
    -> Different property source, normally a different cache key from A/B.
```

**Note:** two classes both specifying `@ActiveProfiles("test")` does not guarantee a cache hit. Other factors—configuration classes, inherited profiles, dynamic properties, context customizers, `@MockBean`/`@MockitoBean` per version, web resource base path, and `@DirtiesContext`—can also produce different keys.

**Reducing maintenance overhead and test runtime:**

1. Pick one common test profile configuration for the majority of tests.
2. Only use a different profile or inline property when a test genuinely needs different behavior.
3. Keep fake ports independent of specific test classes if multiple suites share valid configuration.
4. Avoid `@DirtiesContext` on every test just to "reset"; prefer resetting fixtures/DB where appropriate.
5. Keep pure logic unit tests free of any Spring context.
6. Inspect cache statistics via Spring TestContext logging if a suite becomes slow.

The context cache **does not automatically reset mutable singletons between methods** when reusing the same context. If a fake port holds a message list, the test or fixture itself must ensure state does not leak.

## 15. How does `@SpringJUnitConfig` differ from `@SpringBootTest` when reading YAML?

A common misconception: "Since `@ActiveProfiles("test")` is present, Spring will definitely read `application-test.yml` automatically in every test." In fact, **`@ActiveProfiles` only determines active profiles in TestContext**. Processing `application*.yml` files by convention is the responsibility of **Spring Boot Config Data** inside a context bootstrapped via Boot.

With a plain Spring configuration test:

```java
@SpringJUnitConfig(TestOnlyConfiguration.class)
@ActiveProfiles("test")
class PlainSpringTest {
}
```

the test can be built via `@ContextConfiguration`/`@SpringJUnitConfig` **without launching `SpringApplication`**. `@ActiveProfiles` still governs `@Profile` on beans, yet you must not assume Boot will locate and load `application-test.yml`. If YAML config is needed here, configure an appropriate loader/property source or switch to Boot test bootstrapping when warranted.

With:

```java
@SpringBootTest
@ActiveProfiles("test")
class BootProfileTest {
}
```

Spring Boot uses `SpringApplication` and Config Data rules; `application-test.yml` at valid locations is considered automatically.

Similarly, Spring Boot test slices are bootstrapped with appropriate Boot configuration while **loading only the relevant slice of the application**. Do not use `@SpringBootTest` for a pure Java calculation just to read a property; test the logic directly if loading configuration is not part of the contract.

## 16. Connecting profiles with databases, message brokers, and external services

### 16.1. Database

`application-test.yml` can define a test datasource, for example:

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1"
    username: "sa"
    password: ""
```

This is an **illustrative configuration snippet**, not part of the runnable project in Section 5 (which declares no JDBC/JPA or H2). Using it requires adding the corresponding JDBC/JPA and H2 dependencies and choosing a test database matching the contract.

H2 is convenient, though it differs from PostgreSQL/MySQL in SQL dialect, transactions, collation, and constraints. If a test must prove production-compatible queries or migrations, Testcontainers or a matching database engine may be more appropriate.

Never let tests accidentally point to a production database. Enforce separation at the infrastructure level via schemas, credentials, and write permissions; **do not rely solely on profiles**.

### 16.2. Message broker, email, HTTP

Several options exist:

| Need | Suitable testing approach |
|---|---|
| Unit test message-sending logic | Mock/fake an outbound port interface |
| Test HTTP client serialization/retry | Controlled mock web server or contract test |
| Test messaging adapter | Embedded/test broker or Testcontainers when real behavior is needed |
| Authorized end-to-end test | Dedicated sandbox, bounded data/credentials, explicit cleanup |
| Test configuration selection | Assert effective properties and the injected bean/adapter |

Do not use `application-test.yml` to point a production endpoint to `localhost` without ensuring the test service is actually running. Connection refused errors cause flaky or pointless failures.

### 16.3. Do not put real secrets in YAML

YAML is a configuration source, not a vault. Do not commit production API keys/passwords in `src/main/resources` or `src/test/resources`. Tests can use fake credentials sufficient for local/fake servers; real sandbox integrations should obtain secrets from a CI secret manager with least privilege.

## 17. Troubleshooting: when a profile or YAML has no effect

| Symptom | Causes worth checking | Fix |
|---|---|---|
| Test reads `Hello` instead of `Xin chào` | `test` not active, wrong filename/location, context not using Boot Config Data, higher-precedence source overriding | Check `Environment.getActiveProfiles()`, classpath, `application-test.yml` name, and effective properties |
| `@Autowired` is null | Test not managed by SpringExtension or instantiated manually with `new` | Use `@SpringBootTest`/slice or `@SpringJUnitConfig` as appropriate |
| Production bean still created in tests | Missing `@Profile`, profile inactive, or another bean ignores the profile | Inspect bean definitions and conditions, assert the injected bean |
| `NoSuchBeanDefinitionException: DeliveryPort` | Production `!test` bean excluded, but fake was not `@Import`ed | Bring fake bean into test context or configure bean replacement properly |
| `NoUniqueBeanDefinitionException` | Two beans of the same type are both active | Design mutually exclusive profiles or use qualifier/primary intentionally |
| `application-test.yml` ignored | File not on test classpath, misspelled, or plain Spring loader used | Check build resources, use Boot bootstrap, or declare config source explicitly |
| Spring Boot reports invalid YAML types | Indentation error, tabs, string/boolean/number parsing | Check YAML formatting, use kebab-case keys and properly typed values |
| `spring.profiles.active` fails inside test profile file | Property declared in a profile-specific document (disallowed) | Remove key from that file; activate via `@ActiveProfiles` on the test |
| Test flag overridden by inline property | `@TestPropertySource`, `@SpringBootTest(properties)`, dynamic properties, or env/CLI present | Inspect property source precedence and effective values |
| CI behaves differently from local | Different env vars, JVM props, config locations, classpath, secrets | Standardize test config and inspect permitted environment info |
| Two tests interfere with each other | Context cache sharing mutable singletons or database/test data | Reset fixtures, clean up, isolate data; do not rely on test execution order |
| Tests slow when toggling many profiles | Different cache keys forcing context reloads | Reduce config variants, use unit/slice tests where sufficient, inspect cache stats |

### 17.1. Layered debugging approach

**Layer 1 — verify profile:** inject `Environment`; check `getActiveProfiles()` or `acceptsProfiles(Profiles.of("test"))`.

**Layer 2 — verify property:** read effective property `environment.getProperty("app.welcome.prefix")` and the field on the `@ConfigurationProperties` bean. Do not just look at YAML on disk and assume Spring loaded it.

**Layer 3 — verify bean:** inspect what beans exist in `ApplicationContext` for the required interface, whether `@Profile` conditions match, and whether the test bean was `@Import`ed.

**Layer 4 — check config source precedence:** look for `@TestPropertySource`, inline test properties, system props, env vars, and config locations. When multiple sources share a key, the higher-precedence source wins.

**Layer 5 — check cache and state:** if a test passes in isolation but fails in the full suite, check mutable singleton beans, context cache, test ordering, DB state, and shared data.

### 17.2. Logs should aid diagnosis without leaking secrets

In configuration tests, you can selectively inspect `Environment` and bean configuration. Never dump all `PropertySources` or print passwords/tokens to CI logs. Only log non-sensitive keys, such as `app.welcome.prefix` or active profile names.

If the error is `Failed to load ApplicationContext`, read the **root cause** in the `Caused by` lines of the stack trace; the top-level wrapper message rarely identifies the exact failing property or bean.

## 18. Gradle and running the example

The example uses **Java 17+**, Spring Boot **3.x**, and JUnit Jupiter **5**. In a project that already declares the Spring Boot plugin/BOM for dependency version management, `build.gradle` needs the following dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**This is only an addition to an already configured Spring Boot build**, not a standalone Gradle file since `plugins`, `repositories`, and version management are omitted. `spring-boot-starter-web` is not needed because the example has only services and ports, with no HTTP controllers.

Run from the directory containing the Gradle wrapper:

```bash
./gradlew test --tests com.example.profiles.WelcomeProfileTest --tests com.example.profiles.WelcomeOverrideTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.profiles.WelcomeProfileTest --tests com.example.profiles.WelcomeOverrideTest
```

If the project uses a multi-project Gradle setup, replace the `test` task with the test task path of the module containing the code. Keep packages/paths matching the file list in Section 5 inside a compatible Spring Boot 3.x project. **The example files are for learning; there is no need to modify the current repository just while reading this lesson.**

**Expected test outcomes:**

1. `WelcomeProfileTest` loads the `test` profile and binds `prefix="Xin chào"`, `sendingEnabled=false`, and `maxLength=80`.
2. `WelcomeProfileTest` calls the real `WelcomeService` and receives `"Xin chào, Mai!"`, while the fake port records no messages.
3. `WelcomeProfileTest` throws `IllegalArgumentException` when the name is whitespace-only.
4. `WelcomeOverrideTest` still uses the `test` profile, while the inline test property enables sending; the fake port records `"Mai|Xin chào, Mai!"`.
5. If compilation, bootstrap, and assertions are set up properly, Gradle reports `BUILD SUCCESSFUL`. This is the **expected outcome of the example code**, not a claim about running a specific local repo. The JUnit tests have no fixed business stdout; the console adapter is not used when the `test` profile is active.

Gradle test reports are typically generated at `build/reports/tests/test/index.html`; XML results live in `build/test-results/test/`, relative to the module's build directory.

### 18.1. Checking runtime values instead of trusting annotation names alone

If you want to prove a property truly comes from the expected source, consider assertions on beans and `Environment` as shown in the example. However, **do not assert the exact order or internals of individual `PropertySource`s as implementation details** if the contract only cares about the final value and bean. When a test genuinely requires verifying data sources, choose the appropriate level of assertion without coupling tightly to Config Data internals.

## 19. Common misconceptions and consequences

**"Creating `application-test.yml` is enough."** Wrong: a profile-specific file does not activate a profile by itself. Tests must activate the profile through the proper mechanism.

**"`@ActiveProfiles` reads YAML even in a JUnit test that does not start Spring."** Wrong: the annotation requires TestContext and an appropriate bootstrap; auto-loading `application-{profile}.yml` is a Boot Config Data feature.

**"Put `spring.profiles.active=test` inside `application-test.yml`."** Wrong: Boot disallows declaring profile-activating properties in a file already scoped to a specific profile. Activate it from test annotations or an appropriate external source.

**"Having a `test` profile turns every external request into a fake."** Wrong: adapters must be configured and tested; unconditional production components can still be created and executed.

**"Every property in `application-test.yml` always wins."** Wrong: there are multiple property sources with varying precedence; a `@TestPropertySource` or higher-priority source can override it.

**"A test can call `System.setProperty` and expect already-created Spring beans to update immediately."** Do not assume that. `@ConfigurationProperties` beans are normally bound at context startup, and mutating JVM-wide system properties causes side effects in other tests. Build contexts with the intended config via explicit annotations/configurations.

**"Put `@DirtiesContext` on every test to always get a fresh environment."** Reloading contexts is expensive, and it does not reset resources outside the context. Prefer state isolation, cleanup, and sensible cache configuration.

**"Having `@ActiveProfiles('test')` makes it completely safe to run on CI."** No. Safety also depends on database URLs, credentials, network policies, schedulers, message brokers, and which beans actually run. Use isolated infrastructure/test credentials and defense in depth.

## 20. Self-assessment exercises

### Exercise 1 — determine the final values

Given `application.yml`:

```yaml
app:
  feature:
    enabled: true
    label: "base"
    retries: 4
```

and `application-test.yml`:

```yaml
app:
  feature:
    enabled: false
    label: "test-only"
```

If `@SpringBootTest` + `@ActiveProfiles("test")` uses Boot Config Data with no other override sources, determine the three effective values.

**Answer:** `enabled=false`, `label="test-only"`, `retries=4`. The profile-specific file overrides two keys, while the remaining key comes from the common file.

### Exercise 2 — why can't Spring find the bean?

A `PaymentPort` interface has a production implementation annotated with `@Profile("!test")`. A test uses `@ActiveProfiles("test")` without importing a test implementation. What error is likely, and what is the right fix?

**Answer:** If a service injects `PaymentPort`, the context will likely fail with no qualifying bean found. Supply a fake/test bean via `@TestConfiguration` and `@Import`, or use a bean override mechanism appropriate for your Spring/Boot version. Do not remove the `!test` condition just to make the test start.

### Exercise 3 — distinguish plain Spring TestContext from Boot

Why can `@SpringJUnitConfig(TestConfig.class)` + `@ActiveProfiles("test")` pick `@Profile("test")` beans yet fail to automatically find `application-test.yml`?

**Answer:** Spring TestContext understands active profiles and bean definition conditions, whereas the `application-test.yml` convention is how Spring Boot Config Data loads properties when a context is bootstrapped by Boot.

### Exercise 4 — prevent tests from calling production

List three safeguards besides `@ActiveProfiles("test")` to keep tests from affecting production.

**Hint:** fake adapters/mock servers, dedicated databases with restricted credentials, no production secrets, asserted sandbox URLs, disabling out-of-scope schedulers or consumers, and test data cleanup.

### Exercise 5 — reduce context cache overhead

If a suite has 40 `@SpringBootTest` classes differing across dozens of tiny override flags, why can runtime grow? How can you fix it without losing bug detection?

**Answer:** Many combinations of configs/properties create many context cache entries. Group tests with shared configuration needs, use unit/slice tests for logic not requiring the full context, avoid unnecessary profile/inline property variations, and reserve integration tests for wiring and side effects.

## 21. Practical pre-run test checklist

- [ ] `@ActiveProfiles` is placed on tests with appropriate Spring TestContext/Boot bootstrapping.
- [ ] `application-test.yml` is in the right location, properly named, with valid YAML syntax.
- [ ] I did not declare `spring.profiles.active` inside a profile-specific file.
- [ ] I know which keys come from `application.yml` and which are overridden by the `test` profile.
- [ ] I verify **effective values** via beans/`Environment`, not merely by looking at files.
- [ ] Production adapters have appropriate conditions; test fakes are injected when needed.
- [ ] No production endpoints or credentials exist in the test context or CI configuration.
- [ ] Tests are isolated from databases, networks, message brokers, and mutable singleton state.
- [ ] Inline property overrides are used only when a test needs variation; not overused to fragment the context cache.
- [ ] I do not assume `@TestPropertySource` parses `.yml` the same way Boot Config Data does.
- [ ] I understand active profiles on superclasses or outer classes may be inherited.
- [ ] I choose unit, slice, or `@SpringBootTest` based on the risk being verified.
- [ ] I do not use `@DirtiesContext` as a substitute for cleaning up data.
- [ ] When failures occur, I distinguish wrong profile, wrong property source, missing bean, bootstrap failure, and business logic failure.

**Conclusion:** `@ActiveProfiles` selects the profile set for Spring TestContext; `application-test.yml` supplies profile-specific configuration loaded by Spring Boot when the `test` profile is active in a properly bootstrapped context. Reliable testing requires **correct effective configuration values**, **correct beans/adapters**, and **isolation of external resources**. Tests should not just turn green—they must prove the constructed environment is the environment you intended to test.

### Official references

- Spring Framework — `@ActiveProfiles`: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-activeprofiles.html
- Spring Boot — Externalized Configuration and profile-specific files: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Profiles and `spring.profiles.active` restrictions: https://docs.spring.io/spring-boot/reference/features/profiles.html
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html