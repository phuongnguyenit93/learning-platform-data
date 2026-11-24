# Choosing Data Types, Default Values, and Functional Property Groups in a Spring Boot Library

## Lesson Objectives

When building a **library or Spring Boot starter**, public configuration keys are part of the API that applications using the library must understand and maintain. For example, a message-sending library might let users configure `enabled`, `timeout`, `max-payload`, `mode`, and a `retry` policy. If every value is declared as a `String`, defaults are scattered, or unrelated keys are lumped into one group, using and maintaining the library becomes harder.

This lesson focuses on three closely coupled design decisions:

1. **Data types:** choose Java types that accurately express the meaning of configuration values.
2. **Default values:** define sensible, consistent states when the user does not declare a key.
3. **Property groups:** organize keys by function with clear namespaces and configuration objects.

After this lesson, you will be able to design a typed configuration API with `@ConfigurationProperties`, choose defaults with `@DefaultValue` for Java records, handle nested groups, bring properties into auto-configuration via `@EnableConfigurationProperties`, test binding with `ApplicationContextRunner`, and recognize common pitfalls.

## 1. Why Must Library Configuration Be Designed Like a Public API?

Suppose a library provides message-sending functionality. An unstructured way to declare properties might look like:

~~~properties
enabled=true
timeout=5000
size=2097152
retries=3
mode=1
~~~

The problems:

- Names like `enabled` or `timeout` are too generic and easily collide with other libraries' configuration.
- `timeout=5000` does not clarify whether the unit is milliseconds or seconds.
- `size=2097152` forces users to calculate units themselves.
- `mode=1` requires separate documentation to know what `1` means.
- `retries` does not indicate whether it is the number of retries or the total number of attempts.
- An invalid value may only be detected very late if library code parses strings itself.

With Spring Boot, instead of reading individual strings with `@Value`, a library can declare a **typed configuration model**:

~~~text
acme.delivery.enabled
acme.delivery.mode
acme.delivery.timeout
acme.delivery.max-payload
acme.delivery.max-attempts
acme.delivery.retry.max-retries
acme.delivery.retry.backoff
~~~

Here, the `acme` namespace is owned exclusively by the library; `delivery` is the feature; `retry` is a subgroup. Java types like `Duration`, `DataSize`, and `enum` directly express the domain. This is the library's API whether configured via YAML, properties, environment variables, or command-line arguments.

## 2. Choosing the Right Data Types Instead of Using `String` for Everything

`@ConfigurationProperties` works with the Spring Boot Binder to map configuration values into fields or constructor parameters of a class/record. Choose types according to **the meaning of the information**, then define valid ranges and defaults.

| Configuration data kind | Suggested Java type | Example property | Rationale |
| --- | --- | --- | --- |
| Toggle a two-state feature | `boolean` | `enabled: true` | Clear on/off state; primitive has Java default `false` if no explicit default is declared |
| Need to distinguish "omitted" from `false` | `Boolean` | `feature-enabled` | `null` can signify absence; use only when business logic genuinely needs a third state |
| Retry counts, thread counts, counting limits | `int`/`Integer` or `long` | `max-attempts: 3` | Allows numeric binding and constraints such as `@Min(1)` |
| Wait time / delay / TTL | `java.time.Duration` | `timeout: 5s` | Expresses units, avoiding `long` with unclear milliseconds/seconds |
| Payload/cache/buffer size | `org.springframework.util.unit.DataSize` | `max-payload: 2MB` | More readable than raw byte counts |
| Finite set of choices | Java `enum` | `mode: HTTP` | Reduces arbitrary values or cryptic numeric codes |
| Display name, identifier, token | `String` | `client-name: app-a` | Appropriate when genuinely text, optionally paired with `@NotBlank` |
| Resource address or endpoint | `URI`/URL (when appropriate) | `endpoint: https://...` | Avoids manual string parsing and path validation |
| List of items of the same kind | `List<T>` | `allowed-topics: [a, b]` | Declares an ordered set of values |
| Key-to-value mapping | `Map<K,V>` | `headers: {x-app: demo}` | Suits flexible key sets; has special rules when binding keys containing special characters |
| Group of related options | Nested record/class | `retry.backoff: 200ms` | Groups properties belonging to the same function |

**Type selection rule:** prefer a Java type that reflects the true value domain. If a user enters `max-attempts=abc`, numeric binding usually fails at startup, which is easier to catch than keeping `"abc"` and failing during business execution.

### 2.1. Plain Numbers, Durations, and Data Sizes Differ

Avoid designing:

~~~java
String timeout;       // Who parses it? Which unit?
long payloadSize;     // Bytes or kilobytes?
String transportMode; // Allows any string, easy to mistype.
~~~

Instead use:

~~~java
Duration timeout;
DataSize maxPayload;
Mode mode;
~~~

When configured:

~~~yaml
acme:
  delivery:
    timeout: 1500ms
    max-payload: 2MB
    mode: HTTP
~~~

Spring Boot can convert the values above into the right types. `Duration` supports unit suffixes such as `ms`, `s`, `m`; `DataSize` supports `B`, `KB`, `MB`, `GB` according to Boot's conversion mechanism. When using a number without a suffix, the default unit depends on converter rules and annotations such as `@DurationUnit`/`@DataSizeUnit`; for a public API, **encourage users to write the unit explicitly**.

`DataSize.ofMegabytes(2)` represents 2 MiB in binary units (2 × 1024 × 1024 bytes). Document this clearly when the parameter relates to real limits of external systems.

### 2.2. `enum` Is Suitable for a Closed Set of Choices

~~~java
enum Mode {
    HTTP,
    QUEUE
}
~~~

Users pick `HTTP` or `QUEUE`. An unexpected value like `BANANA` normally causes a binding error, helping catch misconfiguration. Only choose `enum` if the value set is truly controlled by the library; do not use an enum for a list that plugins or partners might dynamically extend.

### 2.3. Distinguish Primitives from Wrapper Types

`boolean` cannot hold `null`; an `int` without configuration and without an explicit default may receive `0`. That is the Java type's default, **not necessarily the right business default**. With `Boolean` or `Integer`, `null` can indicate the user omitted it, but requires consuming code to handle that state.

For example, `max-attempts=0` may be meaningless, whereas `enabled=false` is a valid state. Decide defaults based on the library's contract, rather than letting accidental primitive defaults dictate business behavior.

## 3. Grouping Properties by Function and Owned Namespace

A library should choose its own namespace, such as `acme`, rather than adding keys under `spring`, `server`, or `management` which are managed by Spring Boot. With multiple independent features, each feature gets a clear branch:

~~~text
acme.delivery.*           # Message delivery configuration
acme.delivery.retry.*     # Delivery's retry policy branch
acme.audit.*              # Independent audit feature
acme.metrics.*            # Independent metrics feature
~~~

A configuration might be written as:

~~~yaml
acme:
  delivery:
    enabled: true
    mode: QUEUE
    timeout: 5s
    max-payload: 2MB
    max-attempts: 3
    retry:
      max-retries: 2
      backoff: 200ms
~~~

This structure makes it clear to users that:

- `enabled`, `mode`, `timeout`, `max-payload`, and `max-attempts` control the **delivery** feature.
- `retry.max-retries` and `retry.backoff` control **a sub-policy**.
- `audit` and `metrics` are features that can be configured, toggled, and maintained independently.

### When to Nest a Group vs. Split into a Separate Properties Class?

**Nest a subgroup** when the properties only make sense within the lifecycle or responsibility of the parent feature. For example, `acme.delivery.retry.*` is the retry policy specifically for message delivery.

**Split the prefix and properties class** when a feature has an independent lifecycle, owner, and API. For example, `acme.audit.*` can be enabled or disabled without needing the delivery service. Do not create a monolithic `AcmeProperties` containing a dozen unrelated modules just for "convenience."

Avoid unnecessary depth. A key like `acme.delivery.retry.backoff` is easier to understand than a tree six to eight levels deep when there is no genuine hierarchical domain concept.

### Naming Rules

- Use **lowercase kebab-case** for multi-word segments: `max-attempts`, `request-timeout`, `max-payload`.
- Use dots between groups: `acme.delivery.retry.backoff`.
- Names describe meaning, not implementation details: `max-attempts` is clearer than `count1`; `timeout` is clearer than `t`.
- Avoid redundant repetition: inside the `acme.delivery` namespace, `delivery-timeout` is usually unnecessary; `timeout` is enough.
- Keep key names stable. Renaming keys after release can break applications using the library; if a rename is unavoidable, provide a compatibility path, deprecation, and migration documentation.

Spring Boot supports **relaxed binding**, so the canonical key `max-attempts` can bind to the Java component `maxAttempts`. However, library documentation should consistently use the canonical key form, especially when users configure from multiple sources.

## 4. Defining Default Values Deliberately

A good default value should:

1. Have **safe**, explainable behavior when the application declares nothing.
2. Be practical enough to start using the library without causing unexpected side effects.
3. Be consistent across binding, auto-configuration conditions, documentation, and tests.
4. Be attached to **the right configuration field** and tested when the property is absent.
5. Never contain credentials, secrets, environment-specific endpoints, or dangerous settings that require explicit user decisions.

Example of a possible contract for a hypothetical library:

| Key | Type | Default | Design rationale |
| --- | --- | --- | --- |
| `acme.delivery.enabled` | `boolean` | `true` | Core feature enabled by default if that is the starter's contract |
| `acme.delivery.timeout` | `Duration` | `5s` | Avoid waiting indefinitely |
| `acme.delivery.max-payload` | `DataSize` | `2MB` | Clear size limit |
| `acme.delivery.max-attempts` | `int` | `3` | Total attempts, including the initial attempt |
| `acme.delivery.mode` | `Mode` | `HTTP` | Selects a supported mode |
| `acme.delivery.retry.max-retries` | `int` | `2` | Number of **retries**, excluding the initial attempt |
| `acme.delivery.retry.backoff` | `Duration` | `200ms` | Wait interval between retries |

**Note the difference between `max-attempts` and `max-retries`:** in common terminology, `max-attempts=3` includes the initial send plus up to two retries; `max-retries=2` means at most two retries *after* the initial send. If both keys are used in the same real library, their coordination/precedence must be stated clearly to avoid two confusing limits. In the learning example below, they represent main-group parameters and retry policy parameters for practicing binding; no retry algorithm is implemented yet.

### 4.1. Records and `@DefaultValue` in Spring Boot 3.3

Java 17 records combined with constructor binding are a suitable way to model an **immutable configuration snapshot**:

~~~java
@ConfigurationProperties(prefix = "acme.delivery")
public record DeliveryProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("2MB") DataSize maxPayload,
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("HTTP") Mode mode,
        @DefaultValue Retry retry
) {
    public enum Mode { HTTP, QUEUE }

    public record Retry(
            @DefaultValue("2") int maxRetries,
            @DefaultValue("200ms") Duration backoff
    ) {
    }
}
~~~

This is an **illustrative snippet of the model body**; it requires `import` statements for `ConfigurationProperties`, `DefaultValue`, `Duration`, `DataSize` and must be registered by Spring Boot via the configuration properties mechanism. A complete test example with imports appears later.

`@DefaultValue("5s")` applies when the `timeout` key is not supplied and converts the string `"5s"` into `Duration`. Similarly, `@DefaultValue("2MB")` becomes `DataSize`, and `@DefaultValue("HTTP")` becomes `Mode.HTTP`.

**Key point about nested groups:** an **argumentless** `@DefaultValue` on the `Retry retry` component instructs the Binder to instantiate the subgroup object even when no `retry.*` keys are present. If this empty annotation is omitted, for a constructor-bound nested object with no subgroup properties at all, the `retry` component can be `null`. Each field of `Retry` also has its own `@DefaultValue` to receive a value when the corresponding key is missing.

If the user sets `acme.delivery.retry.max-retries=4` but omits `retry.backoff`, the Binder creates `Retry` with `maxRetries=4` and `backoff=200ms`.

### 4.2. Binding Defaults Differ from Keys Existing in `Environment`

A particularly common misconception that breaks auto-configuration is: "Since `@DefaultValue("true")` is declared, `Environment` definitely contains `acme.delivery.enabled=true`."

**Not true.** Defaults on `@ConfigurationProperties` apply when **binding into the object**; they do not automatically add a new property source into `Environment`. For an application that does not declare `acme.delivery.enabled`:

- `DeliveryProperties.enabled()` can be `true` due to `@DefaultValue`.
- `Environment.containsProperty("acme.delivery.enabled")` can still be `false`.
- A plain `@ConditionalOnProperty(prefix="acme.delivery", name="enabled")`, with default `matchIfMissing=false`, **does not match** if the key is absent, even though the properties record has a default of true.

If you want the bean created when the key is omitted, give the condition the same default contract:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "acme.delivery",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
DeliveryClient deliveryClient(DeliveryProperties properties) {
    return new DeliveryClient(properties);
}
~~~

This is an **illustration**, assuming `DeliveryClient` is a class with a matching constructor. In the runnable example below, `DeliveryClient` is defined concretely as a simple interface.

Conversely, if the feature requires opt-in, choose **`enabled=false` by default** on the model and `matchIfMissing=false` on the condition. Both places must stay consistent.

### 4.3. Defaults in Code or in the Library's `application.yml`?

For a configuration API provided by a starter, place primary defaults in the properties class/record, accompanied by documentation and tests. Avoid forcing default configuration via an `application.yml` file inside the library JAR: a library should not unexpectedly interfere with the host application's configuration sources.

For example, when using a mutable JavaBean instead of a record, defaults can be declared on fields:

~~~java
@ConfigurationProperties("acme.delivery")
public class MutableDeliveryProperties {
    private Duration timeout = Duration.ofSeconds(5);

    public Duration getTimeout() { return timeout; }

    public void setTimeout(Duration timeout) { this.timeout = timeout; }
}
~~~

This is a **complete class snippet** when the two corresponding types are imported, though the configuration properties bean must be registered. For records, defaults more appropriately live on constructor parameters/record components via `@DefaultValue`.

Do not mix conflicting default layers (field defaults, `@DefaultValue`, condition defaults, and defaults inside services) without transparent resolution rules.

## 5. Connecting Properties to the Library's Auto-Configuration

In Spring Boot 3.x, an auto-configuration can register typed configuration properties using `@EnableConfigurationProperties`:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(DeliveryProperties.class)
class DeliveryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DeliveryClient.class)
    DeliveryClient deliveryClient(DeliveryProperties properties) {
        return new DeliveryClient(properties);
    }
}
~~~

This snippet only illustrates wiring; a `DeliveryClient` class with a matching constructor is assumed. When using record/constructor binding, **do not** manually instantiate the record via a `@Bean` method or annotate it with `@Component` expecting Spring Boot to apply constructor binding as a standard `@ConfigurationProperties` bean. For auto-configuration, `@EnableConfigurationProperties(DeliveryProperties.class)` is the explicit mechanism.

A library distributed as a starter typically needs to list the auto-configuration class in:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

For example, one line is the actual class name:

~~~text
example.library.autoconfigure.DeliveryAutoConfiguration
~~~

The imports file **does not** list `DeliveryProperties`; the properties class is registered by `@EnableConfigurationProperties`. Production code layout typically has:

~~~text
src/main/java/example/library/autoconfigure/
  DeliveryAutoConfiguration.java
  DeliveryProperties.java
  DeliveryClient.java
src/main/resources/META-INF/spring/
  org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

This is an illustrative structure. Specific package/module names belong to the library.

### Relationship with `@ConditionalOnMissingBean`

Properties hold only **configuration data**. The `@ConditionalOnMissingBean` condition registers a default bean only if the application has not supplied a bean of the same type. The two mechanisms have different responsibilities:

- `@ConfigurationProperties` answers "What does the application want to configure?"
- `@ConditionalOnProperty` answers "When should the feature be enabled?"
- `@ConditionalOnMissingBean` answers "Should a default implementation be created?"

Do not put business logic or network connections inside the constructor of a properties record. Let services/clients consume the bound and validated values.

## 6. Runnable Example: Record with Defaults, Nested Group, and `ApplicationContextRunner` Tests

The complete example below focuses on binding and defaults, without sending network requests or running a retry algorithm. It creates a simple `DeliveryClient` to observe mode and total attempts, while also testing the feature-disabled case.

**Prerequisites:** Java 17+; Spring Boot 3.3.x; JUnit Jupiter, AssertJ, and `ApplicationContextRunner` from `spring-boot-starter-test`.

**File:** `src/test/java/example/library/DeliveryPropertiesBindingTest.java`

~~~java
package example.library;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.util.unit.DataSize;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(DeliveryAutoConfiguration.class));

    @Test
    void usesTypedDefaultsWhenNoKeysAreConfigured() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(DeliveryProperties.class);
            assertThat(context).hasSingleBean(DeliveryClient.class);

            DeliveryProperties p = context.getBean(DeliveryProperties.class);
            assertThat(p.enabled()).isTrue();
            assertThat(p.timeout()).isEqualTo(Duration.ofSeconds(5));
            assertThat(p.maxPayload()).isEqualTo(DataSize.ofMegabytes(2));
            assertThat(p.maxAttempts()).isEqualTo(3);
            assertThat(p.mode()).isEqualTo(DeliveryProperties.Mode.HTTP);

            assertThat(p.retry()).isNotNull();
            assertThat(p.retry().maxRetries()).isEqualTo(2);
            assertThat(p.retry().backoff()).isEqualTo(Duration.ofMillis(200));

            assertThat(context.getBean(DeliveryClient.class).profile())
                    .isEqualTo("HTTP/3");

            // Model default values do not automatically add a property source.
            assertThat(context.getEnvironment()
                    .containsProperty("acme.delivery.enabled")).isFalse();
        });
    }

    @Test
    void bindsOverridesAndKeepsMissingNestedDefaults() {
        runner.withPropertyValues(
                    "acme.delivery.timeout=1500ms",
                    "acme.delivery.max-payload=512KB",
                    "acme.delivery.max-attempts=6",
                    "acme.delivery.mode=QUEUE",
                    "acme.delivery.retry.max-retries=4")
                .run(context -> {
                    DeliveryProperties p = context.getBean(DeliveryProperties.class);

                    assertThat(p.enabled()).isTrue();
                    assertThat(p.timeout()).isEqualTo(Duration.ofMillis(1500));
                    assertThat(p.maxPayload()).isEqualTo(
                            DataSize.ofKilobytes(512));
                    assertThat(p.maxAttempts()).isEqualTo(6);
                    assertThat(p.mode()).isEqualTo(DeliveryProperties.Mode.QUEUE);
                    assertThat(p.retry().maxRetries()).isEqualTo(4);
                    assertThat(p.retry().backoff()).isEqualTo(
                            Duration.ofMillis(200));
                    assertThat(context.getBean(DeliveryClient.class).profile())
                            .isEqualTo("QUEUE/6");
                });
    }

    @Test
    void disabledPropertyStopsOnlyTheDefaultClientBean() {
        runner.withPropertyValues("acme.delivery.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(DeliveryProperties.class);
                    assertThat(context).doesNotHaveBean(DeliveryClient.class);
                    assertThat(context.getBean(DeliveryProperties.class)
                            .enabled()).isFalse();
                });
    }

    @Test
    void invalidNumericValueFailsDuringBinding() {
        runner.withPropertyValues("acme.delivery.max-attempts=not-a-number")
                .run(context -> assertThat(context).hasFailed());
    }

    interface DeliveryClient {
        String profile();
    }

    @ConfigurationProperties(prefix = "acme.delivery")
    record DeliveryProperties(
            @DefaultValue("true") boolean enabled,
            @DefaultValue("5s") Duration timeout,
            @DefaultValue("2MB") DataSize maxPayload,
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("HTTP") Mode mode,
            @DefaultValue Retry retry
    ) {
        enum Mode { HTTP, QUEUE }

        record Retry(
                @DefaultValue("2") int maxRetries,
                @DefaultValue("200ms") Duration backoff
        ) {
        }
    }

    @AutoConfiguration
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class DeliveryAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.delivery",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = true)
        @ConditionalOnMissingBean(DeliveryClient.class)
        DeliveryClient deliveryClient(DeliveryProperties properties) {
            return () -> properties.mode().name()
                    + "/" + properties.maxAttempts();
        }
    }
}
~~~

### Why Does This Example Test All Three Decisions?

1. **Type selection:** `Duration`, `DataSize`, `enum`, and `int` bind into their exact types; the nonsensical number `not-a-number` causes context startup to fail.
2. **Defaults:** when keys are omitted, `@DefaultValue` annotations still take effect, and the empty `@DefaultValue` creates the nested `Retry`.
3. **Grouping:** `acme.delivery.retry.*` keys bind into `Retry` separately; overriding `max-retries` does not erase the `backoff` default.

The `enabled=false` test illustrates how model defaults coordinate with client registration conditions. When disabled, **the properties bean still exists** to hold configuration values, while the default client is not created.

If `DeliveryProperties` is moved to a separate production file, the record should be declared `public` and placed in `DeliveryProperties.java`; nested classes in the test are used to keep the example **runnable in a single test file**.

### Gradle Dependencies and Run Commands

In a Gradle project **that already has the Spring Boot plugin or BOM managing versions** (Spring Boot 3.3.x), the main dependencies for the example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // Generate metadata so IDEs suggest the library's configuration keys:
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run in the module containing the test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.library.DeliveryPropertiesBindingTest"

# Windows
gradlew.bat test --tests "example.library.DeliveryPropertiesBindingTest"
~~~

**Expected result:** four tests PASS. In test 1, `DeliveryClient.profile()` returns `HTTP/3`; in test 2 it returns `QUEUE/6`; in test 3 the client does not exist; in test 4 invalid type binding causes context startup to fail and the `hasFailed()` assertion succeeds. The tests have no `System.out.println` calls, so there is no fixed application stdout; displayed output depends on Gradle test logging. These results are **expected from the code**, not logs executed within this lesson.

## 7. Validating Value Constraints with Bean Validation

Choosing the right data type is only the first step. For example, `max-attempts=-10` **is still a valid integer when binding**, yet may be an invalid business value. Similarly, `timeout=-5s` can bind to a negative `Duration`; you should explicitly decide whether to allow it.

For properties classes/records, Spring Boot can apply Jakarta Bean Validation when:

1. A Bean Validation implementation is on the classpath (for example `spring-boot-starter-validation`).
2. The properties class is annotated with `@Validated`.
3. Values carry constraints such as `@Min(1)`, `@NotBlank`, `@NotNull`; use `@Valid` to cascade into nested groups.

Example **illustrating the annotations** (not a standalone file; requires importing `@Validated`, `@Min`, `@Valid`, and related types):

~~~java
@ConfigurationProperties(prefix = "acme.delivery")
@Validated
record ValidatedDeliveryProperties(
        @Min(1) int maxAttempts,
        @Valid @DefaultValue Retry retry
) {
    record Retry(@Min(0) int maxRetries) {
    }
}
~~~

If `max-attempts` is omitted, the default primitive `int` value is `0`, so the `@Min(1)` constraint helps detect that the library forgot to provide a default or mark the key required. If you want a default of 3, add `@DefaultValue("3")` to the `maxAttempts` component.

**Design decision:** distinguish **type conversion errors** (for example `max-attempts=abc`) from **business rule violations** (for example `max-attempts=-1`). The Binder handles the first kind; Bean Validation handles the second. They complement each other.

If a nested object must exist even when no keys are configured, an empty `@DefaultValue` ensures it is created under constructor binding; meanwhile `@Valid` checks inner constraints when validation is enabled.

Do not pick a default value just to "pass validation" if it cannot be used safely. For secrets or required endpoints, it may be better to have **no default** and fail fast with appropriate constraints.

## 8. Metadata and Documentation: Helping Users See Types, Defaults, and Groups

For a library/starter, users usually type configuration in an IDE. Spring Boot provides a **configuration metadata processor** to generate:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Spring Boot's annotation processor can collect key names, types, descriptions, and defaults from `@ConfigurationProperties`. This tool helps IDEs suggest the right keys, groups, and values, and also helps reviewers inspect the configuration API.

When writing a regular class with fields, write Javadoc describing each property. For a **record**, document record components via `@param` tags in the record's Javadoc; for example:

~~~java
/**
 * Configuration for the delivery feature.
 *
 * @param enabled whether delivery is enabled
 * @param timeout maximum wait time for a delivery operation
 * @param maxPayload maximum accepted payload size
 */
@ConfigurationProperties(prefix = "acme.delivery")
public record BriefDeliveryProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("2MB") DataSize maxPayload
) {
}
~~~

The snippet above illustrates writing metadata Javadoc; it requires importing the types as in the test example. With the generated metadata, verify the actual key names and their types/defaults. Do not assume IDEs will understand subgroups properly if the class is not recognized by the compiler/annotation processor.

Documentation for each key should show at least: **key name**, **type**, **unit**, **default**, **valid range**, **impact of changing the value**, and **relationship with other keys**. In particular, a default can change how an application behaves immediately upon upgrading the starter version; changing a default should be treated as a public behavior change.

## 9. Distinguishing Default Design from Real Configuration Sources

Suppose `@DefaultValue("5s") Duration timeout` is the library's default. An application using the library may set:

~~~properties
acme.delivery.timeout=2s
acme.delivery.mode=QUEUE
~~~

Or the same meaning in YAML:

~~~yaml
acme:
  delivery:
    timeout: 2s
    mode: QUEUE
~~~

The user-supplied value (from the effective configuration source in `Environment`) will be used by the Binder instead of the component's default. In a real application, the effective value may come from a profile file, environment variable, or command-line argument depending on Boot's configuration source precedence mechanism.

**Principle:** defaults from `@DefaultValue` are used only for components **with no value to bind**; they must not override valid user decisions. Conditions and runtime behavior must also read from the same contract, avoiding a situation where one place uses `timeout=5s` while another service defaults itself to `30s`.

With lists/collections, be cautious when choosing defaults and merging configuration sources: lists are not always concatenated across sources; Spring Boot has specific override/binding rules. Avoid assuming lists from profile A and profile B will automatically merge together.

## 10. Common Pitfalls When Designing Properties for a Library

1. **Using `String` for numbers, durations, or sizes.** Code then has to parse them manually; choose `int`, `Duration`, `DataSize` according to data semantics.
2. **Writing raw time numbers without clarifying the unit.** `timeout=5000` can be misunderstood; prefer `timeout=5s` or `5000ms`.
3. **Letting primitive defaults decide business behavior.** `max-attempts=0` due to a missing default can prevent the feature from running; set `@DefaultValue("3")` or use validation if configuration is mandatory.
4. **Using `Boolean` when only two states are needed**, then letting `null` leak into services. `Boolean` has design value only when "unspecified" genuinely carries meaning.
5. **Placing keys in `spring`, `server`, or `management` namespaces.** Those prefixes are managed by Spring Boot; use a namespace owned by the library.
6. **Dumping everything into a flat group.** `retry-backoff`, `audit-enabled`, `metrics-port` scattered in the same class erase functional boundaries; use separate groups.
7. **Creating too many nested levels for a simple idea.** Deep, unstable configuration trees are hard to read and hard to maintain backward compatibility for.
8. **Missing defaults on nested constructor-bound objects.** If no subgroup keys are set, the nested record can be `null`; use an empty `@DefaultValue` and component defaults when you want the group to always exist.
9. **Assuming a `@ConfigurationProperties` default is a key already added to `Environment`.** `@ConditionalOnProperty` conditions may treat missing keys differently from record defaults; use `matchIfMissing` consistently.
10. **Confusing type validity with business validity.** `-10` is an integer but may be wrong for `max-attempts`; add Bean Validation for value ranges.
11. **Failing to document defaults or silently changing them.** Applications may change behavior after upgrading the library version even when config files did not change.
12. **Skipping configuration metadata generation.** Users lack key, type, and description suggestions in IDEs; add `spring-boot-configuration-processor` when releasing a starter.
13. **Putting `@Component` on a constructor-bound record.** For record configuration properties, use `@EnableConfigurationProperties` or properties scanning instead of registering as a regular bean.
14. **Storing default API tokens/passwords in source code.** Secrets should be supplied via appropriate configuration/secret-manager mechanisms; never hard-code sensitive values into a starter.
15. **Testing only when users configure every key.** This misses branches where all keys are absent, a few keys are overridden, keys have invalid types, and features are disabled.

## 11. Design Checklist Before Releasing a Starter

Read each item as a review question:

- Do the namespace and property groups reflect **the owner and feature**?
- Does each key have **the right Java type**, especially for `Duration`, `DataSize`, and enums?
- Do keys with units use self-explanatory types/values?
- Is each key's default **specified and tested** when the user omits it?
- Does an absent nested group cause unexpected `null` values?
- Are there values needing validation that are currently only type-checked?
- Are auto-configuration conditions consistent with defaults in the properties record?
- Does IDE metadata include complete keys, types, defaults, and Javadoc?
- Does the library accidentally depend on or overwrite Spring Boot's namespaces?
- Are there tests for defaults, partial overrides, explicit `false`, and mistyped input?

## 12. Self-Check Exercises

**Question 1.** A library accepts `upload-timeout=3000`. Why is `Duration` better than `int`?

**Answer:** `Duration` expresses the temporal nature, supports transparent units such as `3s` or `3000ms`, and reduces manual unit conversion in code.

**Question 2.** A record has `@DefaultValue("true") boolean enabled`, but the user has no `enabled` key. Does `@ConditionalOnProperty(name="enabled")` with `matchIfMissing=false` match automatically?

**Answer:** No. A record's binding default does not create a key in `Environment`. The condition is evaluated against the effective value in `Environment`.

**Question 3.** A user declares only `acme.delivery.retry.max-retries=4`; the remaining fields have `@DefaultValue`. What should you watch out for with the `retry` group?

**Answer:** The Binder can instantiate the nested record when a subgroup key is present, and use `@DefaultValue` for missing components. If all `retry.*` keys are absent and you want the object to always be non-null, annotate the subgroup component with an empty `@DefaultValue`.

**Question 4.** The key `acme.delivery.max-attempts=-4` has a valid numeric type. Is using the binder alone enough to protect business logic?

**Answer:** Not yet. Add business constraints, such as `@Min(1)` with `@Validated` and an appropriate Bean Validation provider.

**Question 5.** A library has both delivery and audit; should both be placed under `acme.properties.*` or split into separate groups?

**Answer:** If they are two independent features, they should have meaningful branches like `acme.delivery.*` and `acme.audit.*`. Sub-structures such as `acme.delivery.retry.*` should be nested only under the feature that owns them.

## 13. Practical Conclusion

**Data types**, **default values**, and **property groups** must be designed together. Choose `@ConfigurationProperties` for the library's configuration API; use `Duration`, `DataSize`, enums, and constrained numbers instead of ambiguous strings; group keys under a dedicated prefix and by function; set deliberate defaults (such as `@DefaultValue` for records); and then test **missing keys**, **partial overrides**, and **invalid configuration**.

Pay closest attention in auto-configuration: defaults on a properties object **are not synonymous** with properties being present in `Environment`; `@ConditionalOnProperty` conditions must be configured to match the library's default policy.

### Official Spring Boot Documentation

- [Spring Boot 3.3 — Externalized Configuration: Type-safe Configuration Properties, DefaultValue, Conversion, Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration: Configuration Keys](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 Javadoc — @ConfigurationProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [Spring Boot 3.3 Javadoc — @DefaultValue](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/DefaultValue.html)
