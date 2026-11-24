# @ConfigurationProperties, Binding, and Validation in Tests

## 1. Goal: treating configuration as part of the application contract

In Spring Boot, an application can have perfectly valid Java logic yet fail or misbehave at startup because of missing configuration, wrong data types, misspelled property names, or out-of-range values. Familiar examples are invalid timeouts, zero retry counts, missing service URLs, and blank access keys.

`@ConfigurationProperties` groups configuration keys under a **prefix** and binds them to a strongly typed Java object. `@Validated` works with Jakarta Bean Validation constraints to reject configurations that violate rules.

In tests, three separate questions must be answered:

1. **Registration:** Was the configuration class registered with Spring as a configuration-properties bean?
2. **Binding and conversion:** Were keys, nested structures, default values, and formats like `5s` converted to the right Java types?
3. **Validation:** When values are required or bounded by business rules, does the application **fail fast** on missing/invalid configuration?

This lesson uses Java 17, Spring Boot **3.x** (illustrated with 3.5 APIs), JUnit Jupiter, AssertJ, and Jakarta Validation. There are two test levels: a lightweight context with `ApplicationContextRunner` and an integration test using `@SpringBootTest`. Neither an HTTP server nor external service connections are needed to verify configuration binding.

**Distinction:** `@ConfigurationProperties` is Spring Boot's binding mechanism, unlike passing a POJO directly into a Java constructor. Writing `new DeliveryProperties(...)` never tests whether Spring reads keys from `Environment` or validates during binding.

## 2. Mechanism from configuration file to Java object

A typical flow:

~~~text
application.yml / application.properties
       + env vars / test properties / other sources
                     |
                     v
             Spring Environment
             (PropertySources, priority order)
                     |
                     v
           ConfigurationProperties Binder
         key -> field name -> type conversion
                     |
                     v
     @ConfigurationProperties DeliveryProperties
                     |
                     v
       @Validated + Jakarta Bean Validation
                     |
               valid / error
                 |      |
                 v      v
          bean ready   context startup fails
~~~

Example keys:

~~~properties
app.delivery.base-url=https://sandbox.example/api
app.delivery.max-attempts=3
app.delivery.timeout=5s
app.delivery.auth.api-key=test-key
~~~

When binding succeeds, the object holds:

- `baseUrl = "https://sandbox.example/api"` (String).
- `maxAttempts = 3` (int).
- `timeout = Duration.ofSeconds(5)`.
- `auth.apiKey = "test-key"`.

`test-key` here is a **dummy value for testing**; never put real keys in a repository or logs.

### Relaxed binding

Spring Boot supports **relaxed binding**: the canonical key `app.delivery.base-url` binds to Java property `baseUrl`. Write keys in `.properties`/`.yml` files in **lowercase kebab-case**. Other forms such as `baseUrl` may also be accepted by the binder depending on the source, yet do not abuse that flexibility to justify inconsistent config keys.

Note that **OS environment variable** naming rules differ from properties files; for instance, representing dots and hyphens normally converts to uppercase, replaces dots with underscores, and drops hyphens per the official guide. Nested/list properties also have specific indexing rules. Testing via `withPropertyValues` verifies binding from a test property source, **not** that a particular OS env var name resolves properly.

### Type conversion and validation are two separate steps

- `app.delivery.timeout=5s` → converts to `Duration`.
- `app.delivery.timeout=not-a-duration` → **type conversion / bind error**, before any `Duration` constraint can even run.
- `app.delivery.max-attempts=0` → integer conversion **succeeds**, then `@Min(1)` rejects it.
- `app.delivery.base-url=   ` → String binding succeeds, then `@NotBlank` rejects it.

In startup error reports, exceptions can be wrapped across several layers—bean creation → configuration properties bind → bind validation/conversion. Tests should not match verbatim against entire stack traces or exception messages that may vary across Spring Boot releases.

## 3. Choosing data types and registering @ConfigurationProperties

Spring Boot supports two common designs:

| Design style | Characteristics | Testing notes |
| --- | --- | --- |
| Mutable JavaBean | Fields, getters/setters, no-arg constructor; binder invokes property setters | Verify fields are actually populated, setters/getters, and default values |
| Immutable constructor binding / Java `record` | Values passed via constructor; well suited for immutable config | Verify proper registration, type conversion, constructor params, and nested objects |

For a **Java 17 `record` with a single canonical constructor**, Spring Boot 3.x applies constructor binding without needing `@ConstructorBinding`. If a class has multiple constructors, designate the binding constructor per your version's API.

**Important:** constructor-bound configuration types must be registered via `@EnableConfigurationProperties(...)` or `@ConfigurationPropertiesScan`. Do not annotate the record with `@Component` expecting constructor binding to process it like a normal bean; that is not the right bean-creation path for constructor binding. In scoped tests, `@EnableConfigurationProperties` identifies the exact type under test.

An application may use:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

This is an **illustrative snippet** needing appropriate imports and other classes in a real Spring Boot project. `@ConfigurationPropertiesScan` scans from the annotated class's package (or specified packages), whereas `@EnableConfigurationProperties(DeliveryProperties.class)` registers that specific type. **There is no need to use both for the same class** in the test examples below.

## 4. A realistic configuration model with Jakarta Validation

Consider configuration for an internal notification sender. Contract:

| Field | Java type | Rule |
| --- | --- | --- |
| `app.delivery.base-url` | String | Required and not blank |
| `app.delivery.max-attempts` | int | From 1 to 5 |
| `app.delivery.timeout` | Duration | Required (non-null) |
| `app.delivery.auth.api-key` | String in nested record | Required and not blank |
| `app.delivery.auth` | Nested record | Required to exist |

**File `src/main/java/com/example/testing/DeliveryProperties.java`:**

~~~java
package com.example.testing;

import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        @NotBlank String baseUrl,
        @Min(1) @Max(5) int maxAttempts,
        @NotNull Duration timeout,
        @NotNull @Valid Auth auth
) {
    public record Auth(@NotBlank String apiKey) {
    }
}
~~~

Each annotation serves a distinct role:

- `@ConfigurationProperties("app.delivery")`: binds the `Environment` prefix to the object.
- `@Validated`: tells Spring Boot to validate the configuration bean during binding when a compatible validator/provider exists.
- `@NotBlank`: ensures the String is non-null, non-empty, and not whitespace-only.
- `@Min(1)`, `@Max(5)`: bounds retry attempts.
- `@NotNull`: ensures timeout and the `Auth` object are present.
- `@Valid`: **cascades validation** into the `Auth` record so `apiKey` is not skipped when the nested object is constructed.

With only `@NotNull Auth` and no `@Valid`, the bean could hold an `Auth` with a blank `apiKey` while nested constraints go unevaluated. With only `@Valid` and no `@NotNull`, `Auth = null` does not automatically become a violation. When a nested object is required, specify **both**.

Example limitation: `@NotBlank baseUrl` only checks that the string is non-blank; **it does not check whether the URL has a valid scheme/host**. To enforce HTTPS or specific domains, add appropriate rules (such as a custom constraint). Likewise, `@NotNull Duration` does not require a positive duration; add a constraint if business rules demand timeout > 0.

## 5. Preparing dependencies for testing

The examples target a Spring Boot **3.x** project using Gradle Groovy DSL and Java 17+. `build.gradle` needs the Spring Boot Gradle plugin, repositories, and appropriate dependency management/toolchain; **the block below shows only the relevant dependencies and task**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-validation` brings in the Jakarta Bean Validation API and a runtime provider, typically Hibernate Validator. `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and `spring-boot-test` (which includes `ApplicationContextRunner`).

Do not confuse `spring-boot-starter-test` with automatically having every validation provider needed: **add the validation starter** when using `@Validated` and Jakarta constraints. Having only `jakarta.validation.constraints.NotBlank` on the compile classpath without a runtime provider is not enough for fail-fast validation.

If your project uses Spring Boot 2.x, Bean Validation package names, Java requirements, and constructor binding mechanics differ substantially. These examples are written intentionally for **Spring Boot 3.x + Java 17**; do not copy them verbatim across major versions.

## 6. Complete example: testing binding and validation with ApplicationContextRunner

`ApplicationContextRunner` is a Spring Boot Test utility that creates a lightweight `ApplicationContext`, applies specified configs and properties, passes the context to an assertion callback, and closes it automatically afterward. It excels at answering **whether configuration binds and whether missing properties fail context startup** without booting the entire app.

We register `DeliveryProperties` explicitly with `@EnableConfigurationProperties` and supply values via `withPropertyValues`. Each `run(...)` call gets its own isolated context and never modifies global `System.setProperty(...)`.

**File `src/test/java/com/example/testing/DeliveryPropertiesBindingTest.java`:**

~~~java
package com.example.testing;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.validation.BindValidationException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesBindingTest {
    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(OnlyPropertiesConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class OnlyPropertiesConfiguration {
    }

    @Test
    void bindsAllProperties_whenConfigurationIsValid() {
        runner.withPropertyValues(
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=3",
                "app.delivery.timeout=5s",
                "app.delivery.auth.api-key=test-key"
        ).run(context -> {
            assertThat(context).hasNotFailed().hasSingleBean(DeliveryProperties.class);

            DeliveryProperties props = context.getBean(DeliveryProperties.class);
            assertThat(props.baseUrl()).isEqualTo("https://sandbox.example/api");
            assertThat(props.maxAttempts()).isEqualTo(3);
            assertThat(props.timeout()).isEqualTo(Duration.ofSeconds(5));
            assertThat(props.auth().apiKey()).isEqualTo("test-key");
        });
    }

    @Test
    void bindsRelaxedNameAndDuration_whenKeyUsesCamelCase() {
        runner.withPropertyValues(
                "app.delivery.baseUrl=https://sandbox.example/api",
                "app.delivery.max-attempts=2",
                "app.delivery.timeout=1500ms",
                "app.delivery.auth.api-key=test-key"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            DeliveryProperties props = context.getBean(DeliveryProperties.class);

            assertThat(props.baseUrl()).isEqualTo("https://sandbox.example/api");
            assertThat(props.timeout()).isEqualTo(Duration.ofMillis(1500));
        });
    }

    @Test
    void rejectsMissingBaseUrl_whenRequiredPropertyIsAbsent() {
        runner.withPropertyValues(
                "app.delivery.max-attempts=3",
                "app.delivery.timeout=5s",
                "app.delivery.auth.api-key=test-key"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(hasCause(
                    context.getStartupFailure(),
                    BindValidationException.class
            )).isTrue();
        });
    }

    @Test
    void rejectsZeroAttempts_whenMinimumIsOne() {
        runner.withPropertyValues(
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=0",
                "app.delivery.timeout=5s",
                "app.delivery.auth.api-key=test-key"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(hasCause(
                    context.getStartupFailure(),
                    BindValidationException.class
            )).isTrue();
        });
    }

    @Test
    void rejectsBlankNestedApiKey_whenCascadeValidationRuns() {
        runner.withPropertyValues(
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=3",
                "app.delivery.timeout=5s",
                "app.delivery.auth.api-key=   "
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(hasCause(
                    context.getStartupFailure(),
                    BindValidationException.class
            )).isTrue();
        });
    }

    @Test
    void rejectsMissingAuth_whenNestedObjectIsRequired() {
        runner.withPropertyValues(
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=3",
                "app.delivery.timeout=5s"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(hasCause(
                    context.getStartupFailure(),
                    BindValidationException.class
            )).isTrue();
        });
    }

    @Test
    void rejectsUnconvertibleTimeout_whenBindingFails() {
        runner.withPropertyValues(
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=3",
                "app.delivery.timeout=not-a-duration",
                "app.delivery.auth.api-key=test-key"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(hasCause(
                    context.getStartupFailure(),
                    BindException.class
            )).isTrue();
        });
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expectedType
    ) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
~~~

### Analyzing the positive tests

The `bindsAllProperties_whenConfigurationIsValid` case proves **registration + binding + conversion + validity** together:

1. `withUserConfiguration` registers `OnlyPropertiesConfiguration`.
2. `@EnableConfigurationProperties` registers `DeliveryProperties` so the binder instantiates the immutable record.
3. `withPropertyValues` supplies inputs for this isolated run.
4. `assertThat(context).hasNotFailed()` proves the lightweight context started cleanly.
5. `hasSingleBean` confirms a single bean of the expected type exists.
6. Assertions on `baseUrl`, `maxAttempts`, `Duration`, and `Auth` verify each actual field, not merely bean presence.

If you only assert `context != null` or `context.containsBean(...)`, a bean holding wrong defaults can still pass. Always check the bound values of business-meaningful fields.

`bindsRelaxedNameAndDuration_whenKeyUsesCamelCase` highlights two easy config mistakes: `baseUrl` binds to the `baseUrl` record component; `1500ms` becomes `Duration.ofMillis(1500)`, **not mistakenly 1,500 seconds**.

### Analyzing the negative tests: validation vs. conversion

The three cases—missing `baseUrl`, `maxAttempts = 0`, and blank `auth.apiKey`—provide inputs that **can bind yet violate Jakarta constraints**. They verify context startup failed and a `BindValidationException` exists in the cause chain.

`timeout=not-a-duration` is a **type conversion** failure, not a `@NotNull` violation. It verifies the context failed with `org.springframework.boot.context.properties.bind.BindException` in the cause chain.

`hasCause` walks nested causes instead of matching the outermost exception's exact class name or message. That makes sense because binding errors are commonly wrapped by `BeanCreationException` or `ConfigurationPropertiesBindException`. When upgrading Spring Boot versions, verify the exception taxonomy and update assertions if needed.

### What is actually proven?

`ApplicationContextRunner` tests prove **the configuration object receives the right values** and **Spring rejects missing/invalid configuration**. They **do not** prove HTTP endpoints work, external services are reachable, `application-prod.yml` exists, or profiles are enabled across the full app. Add targeted integration tests at the proper layer to cover those.

## 7. Additional test cases for boundaries, nulls, and nested properties

A test matrix avoids testing only the "happy path":

| Group | Input | Expected |
| --- | --- | --- |
| Minimum attempts | `max-attempts=1` | Binds successfully |
| Maximum attempts | `max-attempts=5` | Binds successfully |
| Below min | `max-attempts=0` | Validation fails |
| Above max | `max-attempts=6` | Validation fails |
| Unconvertible number | `max-attempts=abc` | Binding/conversion fails |
| Valid duration | `timeout=2s`, `timeout=1500ms` | Correct `Duration` |
| Invalid duration | `timeout=hello` | Binding/conversion fails |
| Missing timeout | `timeout` omitted | `@NotNull` fails |
| Base URL null/blank | Key omitted or spaces only | `@NotBlank` fails |
| Missing `auth` | Child keys omitted | `@NotNull Auth` fails |
| Blank nested key | `auth.api-key=   ` | `@Valid` + `@NotBlank` fails |
| Valid configuration | All four keys with valid values | Bean created and all fields bound |

Because this exercise uses primitive `int maxAttempts`, if the key is missing Java receives `0` during constructor binding. `@Min(1)` rejects `0`, yet **that does not always distinguish a missing key from an explicit `0`**: intentionally setting `0` and omitting the key produce the same symptom. If you need to distinguish "explicitly required" from "defaulted," use an appropriate type (such as `Integer` with `@NotNull`) or inspect the property source directly in tests.

With `@NotBlank baseUrl`, a string like `"not a URL"` is non-blank and passes the current contract. Do not write a test demanding rejection of "malformed URLs" unless the code actually declares a matching constraint.

### Writing parameterized tests without losing context isolation

You can group boundary values for `maxAttempts` using `@ParameterizedTest`, while keeping **the other three properties valid** in every invocation. Example method placed inside `DeliveryPropertiesBindingTest` above:

~~~java
@ParameterizedTest
@ValueSource(ints = { 1, 5 })
void acceptsBoundaryAttempts(int attempts) {
    runner.withPropertyValues(
            "app.delivery.base-url=https://sandbox.example/api",
            "app.delivery.max-attempts=" + attempts,
            "app.delivery.timeout=5s",
            "app.delivery.auth.api-key=test-key"
    ).run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context.getBean(DeliveryProperties.class).maxAttempts())
                .isEqualTo(attempts);
    });
}
~~~

This is an **additional method snippet** needing imports for `org.junit.jupiter.params.ParameterizedTest` and `org.junit.jupiter.params.provider.ValueSource`. `ApplicationContextRunner` creates a fresh context for each run so cases `1` and `5` never interfere. Never share a `static` mutable variable to record attempt counts across invocations.

## 8. Testing @ConfigurationProperties in a real Spring Boot test

When the goal extends beyond the binder to Spring Boot test infrastructure integration, use `@SpringBootTest`. The next example explicitly configures a small test application to avoid depending on a project's main application class.

**File `src/test/java/com/example/testing/DeliveryPropertiesSpringBootTest.java`:**

~~~java
package com.example.testing;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        classes = DeliveryPropertiesSpringBootTest.TestApplication.class,
        properties = {
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=2",
                "app.delivery.timeout=2s",
                "app.delivery.auth.api-key=test-key"
        }
)
class DeliveryPropertiesSpringBootTest {

    @Autowired
    DeliveryProperties properties;

    @Test
    void configurationProperties_whenBootContextStarts_areBound() {
        assertNotNull(properties);
        assertEquals("https://sandbox.example/api", properties.baseUrl());
        assertEquals(2, properties.maxAttempts());
        assertEquals(Duration.ofSeconds(2), properties.timeout());
        assertEquals("test-key", properties.auth().apiKey());
    }

    @SpringBootConfiguration
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class TestApplication {
    }
}
~~~

`@SpringBootTest(properties=...)` feeds test properties into Spring's `Environment` for the test class. `@SpringBootConfiguration` provides a Boot configuration class so the loader initializes the context; `@EnableConfigurationProperties` ensures the configuration record is registered. Here neither `@EnableAutoConfiguration` nor network services are enabled: the goal is solely proving **Boot test context and binding/validation**.

**Cost difference:** `@SpringBootTest` participates in Spring TestContext and context caching; as the real application scan/context grows, tests get heavier. `ApplicationContextRunner` is leaner and usually better for a matrix of startup failure cases. Do not boot the entire application for every invalid-value combination just to test one constraint when a small context proves it cleanly.

## 9. `@ActiveProfiles`, `@TestPropertySource`, and `@DynamicPropertySource`

In real projects, test data does not come solely from `withPropertyValues`.

| Mechanism | Used for | Common confusion |
| --- | --- | --- |
| `@ActiveProfiles("test")` | Activates the `test` profile in Spring TestContext | Does not create files on its own; Spring Boot considers `application-test.yml`/`application-test.properties` if present |
| `@TestPropertySource(properties = "...")` | Inserts test properties directly into TestContext | Does not automatically parse YAML via `locations` |
| `@SpringBootTest(properties = "...")` | Supplies properties for a Boot test class | Contexts with different property sets can produce different cache keys |
| `@DynamicPropertySource` | Supplies dynamic properties, often from Testcontainers or runtime ports | Method is usually `static`; values are dynamic and high-precedence |
| `ApplicationContextRunner.withPropertyValues` | Builds individual lightweight contexts with distinct configurations | Does not automatically load the main app's `application.yml` |

Profile example:

~~~yaml
# src/test/resources/application-test.yml
app:
  delivery:
    base-url: https://sandbox.example/api
    max-attempts: 2
    timeout: 2s
    auth:
      api-key: test-key
~~~

This is a **test-environment-only file** containing only dummy credentials. In a `@SpringBootTest` test using Spring Boot config data, `@ActiveProfiles("test")` activates the profile. However, if you want to test the real YAML file, **do not simultaneously override all keys with `@SpringBootTest(properties=...)`**, otherwise the test only proves your overrides rather than the file's contents.

For integration tests with Testcontainers, `@DynamicPropertySource` supplies container-assigned JDBC URLs/ports. Never hard-code ports or call `System.setProperty` across tests causing JVM-wide state leaks. Always account for property source precedence when multiple sources define the same key.

### Property precedence: what are you testing?

If `application-test.yml` sets `max-attempts: 2` while a test annotation sets `app.delivery.max-attempts=4`, the bound value comes from the **higher-precedence source** in that test configuration (normally the test override). A test running only with that override **will not** catch a broken key in the YAML file.

Split into two distinct test styles:

1. **Controlled-data binding:** use `ApplicationContextRunner` or annotation properties to verify mapping/validation rules.
2. **Real configuration/profile verification:** load the right profile, avoid overriding the keys being verified, and assert the final bound values.

## 10. Default values, nulls, and @DefaultValue

A record can declare default values for constructor-binding parameters via `org.springframework.boot.context.properties.bind.DefaultValue` (Spring Boot 3.x API). Illustrative example:

~~~java
@ConfigurationProperties("example.retry")
public record RetryProperties(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("2s") Duration timeout
) {
}
~~~

This is an **illustrative class snippet** needing imports for `java.time.Duration`, `ConfigurationProperties`, and `DefaultValue`; for the binder to create the bean, register the type as shown in Section 3. When those keys are absent, the binder applies the declared defaults.

**Distinction:** defaults on constructor/record parameters populate values in the Java object; they **do not necessarily add an actual property entry in `Environment`**. Therefore tests must assert on the bound `RetryProperties` bean, not inspect `environment.getProperty("example.retry.max-attempts")` expecting the default to appear there.

Clear design rules to choose from:

- Use `@NotNull Integer attempts` if you want to detect when a property is genuinely omitted.
- Use primitive `int` with an explicit default if the system should have a valid default value.
- Use `@NotNull @Valid Nested nested` when a nested config must be present and validated inside.
- For nested constructor binding, `@DefaultValue` with no argument is sometimes used to instantiate the nested object even when child keys are absent, after which validation inspects inside it. Test that specific design choice explicitly.

For security settings, **never log full secret values**, even on context startup failure. Inspect errors by key/constraint rather than copying sensitive values into reports.

## 11. Common mistakes and how to fix them

1. **Calling the Java constructor directly and claiming binding is tested.** That test never touches Spring Binder or `Environment`. **Fix:** use `ApplicationContextRunner` or a real Boot test context.
2. **Forgetting to register the configuration-properties bean.** `@ConfigurationProperties` is metadata and does not guarantee scanning on its own. **Fix:** declare `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.
3. **Annotating a constructor-bound record with `@Component`.** Spring DI instantiates it through a different path, often failing or bypassing the expected binder. **Fix:** register it with the proper configuration-properties API.
4. **Missing `spring-boot-starter-validation`.** Constraints may go unenforced without a provider/configuration. **Fix:** ensure a Jakarta validation provider is on the classpath.
5. **Forgetting `@Validated` on the configuration-properties class.** Placing `@NotBlank`/`@Min` alone may not trigger binding validation. **Fix:** add `@Validated` and write a failing validation test.
6. **Forgetting `@Valid` on nested objects.** Inner constraints are skipped. **Fix:** combine cascading `@Valid` with `@NotNull` when the nested object is required.
7. **Confusing conversion failures with Bean Validation failures.** `timeout=not-a-duration` cannot convert to `Duration`; `max-attempts=0` converts to `int` yet violates `@Min`. **Fix:** distinguish both failure classes and test each appropriately.
8. **Matching exception messages verbatim.** Wrappers, wording, and violation ordering can change across versions. **Fix:** assert context failure and exception/cause type or stable violation structure.
9. **Using real production configuration in tests.** URLs/secrets can point to production or leak in logs. **Fix:** keep all test endpoints/secrets dummy values making no real connections.
10. **Using `@TestPropertySource(locations="classpath:application-test.yml")` without a YAML factory.** Default `TestPropertySource` mechanics differ from Boot's Config Data loader. **Fix:** use `@ActiveProfiles("test")` with `application-test.yml` per Boot conventions or supply an intentional factory.
11. **Overriding every property when testing a profile file.** The test only verifies overrides and misses broken YAML. **Fix:** separate controlled-data tests from real-file tests.
12. **Putting every invalid-config case into a heavy `@SpringBootTest`.** Startup failures become clunky and slow. **Fix:** prefer `ApplicationContextRunner` for binding/validation matrices.
13. **Assuming `@NotBlank` validates URLs or `@NotNull Duration` enforces positive timeouts.** Those are different contracts. **Fix:** add constraints/custom validators matching requirements and write corresponding negative tests.
14. **Introducing uncontrolled OS/time dependencies.** Developer machine env vars/secrets/profiles alter outcomes. **Fix:** isolate sources, fix test inputs, and never mutate global system properties between tests.

## 12. Practical workflow and QA checklist

When adding a new `@ConfigurationProperties` group:

1. **List keys and types:** prefix, canonical names, nested structure, `Duration`/`DataSize`/enum types, and valid formats.
2. **Specify rules:** required vs. optional, defaults, bounds, security requirements, failure behavior.
3. **Pick binding style:** mutable JavaBean or immutable constructor/record; register via scan or `@EnableConfigurationProperties`.
4. **Write a positive test:** bind full valid values and assert every important field.
5. **Write negative tests:** missing keys, blanks, out-of-range min/max, conversion errors, and nested validation.
6. **Pick the right tool:** `ApplicationContextRunner` for small matrices; `@SpringBootTest` when proving real wiring/Boot TestContext.
7. **Verify the test environment:** profiles, precedence, property sources, no real secrets.
8. **Run tests standalone and across the full suite:** confirm no shared state or interference from other tests' configurations.

Checklist before finishing:

- [ ] `@ConfigurationProperties` uses the right prefix and the bean is registered.
- [ ] Canonical/kebab-case keys match Java fields.
- [ ] Tests verify proper type conversion (String, int, Duration, nested record).
- [ ] Valid and invalid boundary cases are tested for constraints.
- [ ] `@Validated` and Jakarta provider are actually active; `@Valid` cascades into nested objects.
- [ ] Binding errors are tested separately from validation errors where meaningful.
- [ ] Startup failure cases use the context runner without crashing the suite.
- [ ] Did not stop at `assertNotNull` on the bean; asserted all critical bound values.
- [ ] Real profile/config file tests are not accidentally shadowed by overrides.
- [ ] No real credentials or global property mutations leaking state.
- [ ] Examples and filenames/class names match Java 17, JUnit Jupiter, Spring Boot 3.x.

### Running the test suite

From the project directory with Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.testing.DeliveryPropertiesBindingTest"
./gradlew test --tests "com.example.testing.DeliveryPropertiesSpringBootTest"
~~~

On Windows, use `gradlew.bat` instead of `./gradlew`. Neither test class calls `System.out.println`, so there is **no fixed application stdout**. The build/test runner displays test status and reports per project settings. Both require Spring Boot, AssertJ, and JUnit dependencies on the classpath, so you cannot compile/run `javac DeliveryPropertiesBindingTest.java` standalone without providing those libraries.

**Remember:** `@ConfigurationProperties` governs **how configuration is read and converted**; `@Validated` + Jakarta constraints govern **which configurations are allowed to exist**. In tests, prove all three layers—**bean registration → bind/convert → validate**—and clearly separate controlled-input tests from real loaded profile/configuration tests.

### References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot — Creating Your Own Auto-configuration / ApplicationContextRunner](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.5 — BindValidationException API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/bind/validation/BindValidationException.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/)