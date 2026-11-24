# Testing Binding and Type Conversion with Binder and Small Data Sources

## 1. Learning Objectives

In Spring Boot Externalized Configuration, applications commonly declare properties in `application.yml`, `application.properties`, environment variables, or command-line arguments. `@ConfigurationProperties` then binds those properties into typed Java objects.

When testing a binding rule, many developers start with `@SpringBootTest` and boot the entire Spring context. That is useful for integration testing, but often overly broad when the real question is simply:

- Does the key `client.connect-timeout` convert from `"5s"` to `Duration`?
- Does the key `client.max-retries` convert from `"4"` to `int`?
- Does a record with nested components bind properly?
- Does data like `"2MB"` become a `DataSize`?
- If a key is missing, what does `BindResult` reflect?
- If a value has the wrong type, does a binding error appear as expected?
- Can we verify this behavior **without creating an ApplicationContext, reading real files, or starting a web server**?

The answer is **yes**: Spring Boot provides the `Binder` API and `ConfigurationPropertySource` implementations that let you run binding directly against a small data source.

This lesson focuses on the technique:

```text
Map<String, Object> test data
                |
                v
     MapConfigurationPropertySource
                |
                v
              Binder
                |
        key name lookup
        type conversion
        object binding
                |
                v
             BindResult
                |
                v
        JUnit / AssertJ assertions
```

This is a **unit-level binding test** or **focused binder test**. It tests the binder layer and does not replace all Spring Boot integration tests.

## 2. When Should You Use Binder Directly?

Suppose an application has a configuration group:

```yaml
client:
  endpoint: "https://api.example.invalid"
  connect-timeout: 5s
  max-retries: 4
  enabled: true
```

Record:

```java
import java.net.URI;
import java.time.Duration;

public record ClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {
}
```

If the goal is just confirming that the binder understands `client.connect-timeout=5s`, there is no need to launch an HTTP server, create a DataSource, scan services, load all YAML files, or enable profiles.

You can build a Map containing only the keys to test, then ask the binder to create `ClientProperties`.

Advantages of a small focused test:

1. **Fast and isolated:** no need to refresh a Spring ApplicationContext.
2. **Explicit inputs:** every value is declared right in the test.
3. **Minimal side effects:** independent of configuration files currently being edited by developers.
4. **Simple diagnostics:** when a failure occurs, the source may contain only a few properties.
5. **Easy to test variants:** change one input value without adding YAML files.
6. **Focused responsibility:** verifies property names, type conversion, nested objects, lists, and defaults.

However, this test **does not verify** whether Spring Boot finds profile-specific files, registers the configuration bean in a context, or loads a location from `spring.config.import`. Those parts require their corresponding test types.

## 3. Key API Components

| API | Main package | Role |
| --- | --- | --- |
| `Binder` | `org.springframework.boot.context.properties.bind` | Binds properties into Java objects |
| `Bindable<T>` | `org.springframework.boot.context.properties.bind` | Describes the target type and binding metadata |
| `BindResult<T>` | `org.springframework.boot.context.properties.bind` | Represents the result with or without a bound value |
| `ConfigurationPropertySource` | `org.springframework.boot.context.properties.source` | Property source understood by Binder |
| `MapConfigurationPropertySource` | `org.springframework.boot.context.properties.source` | Exposes a Map as a configuration property source |
| `BindException` | `org.springframework.boot.context.properties.bind` | Exception thrown when binding cannot succeed |
| `ConfigurationPropertyName` | `org.springframework.boot.context.properties.source` | Represents structured key names per Binder rules |

A minimal example:

```java
import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

public class MinimalBinderExample {

    public static void main(String[] args) {
        MapConfigurationPropertySource source =
                new MapConfigurationPropertySource(
                        Map.of("example.retries", "7")
                );

        Binder binder = new Binder(source);

        BindResult<Integer> result =
                binder.bind("example.retries", Integer.class);

        System.out.println(result.get()); // 7
    }
}
```

Here:

- The Map stores `"7"` as a string.
- `MapConfigurationPropertySource` wraps the Map as a configuration source.
- `Binder` converts the source value into the target type `Integer`.
- `BindResult#get()` returns the integer if a value was bound.

The test needs no `@SpringBootTest` annotation, creates no SpringApplication, and reads no configuration files.

## 4. Setting Up Dependencies for Writing Tests

Examples target projects using Java 17+ and Spring Boot 3.x. Verify exact APIs against your project's actual version.

A Spring Boot project with Gradle Groovy DSL typically already has:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Binder APIs live in Spring Boot's core libraries. `spring-boot-starter-test` provides common testing tools such as JUnit Jupiter and AssertJ.

With Maven, the standard test dependency is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Some validation examples at the end of this lesson require adding a Bean Validation provider, usually via:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

You do not need the web starter just to test a `String -> Duration` conversion.

If the project already uses the Spring Boot BOM or dependency-management plugin, you do not need to specify versions manually on each starter.

## 5. First Test: Binding an Integer Value

Create file:

```text
src/test/java/com/example/configdemo/BinderBasicsTest.java
```

Contents:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class BinderBasicsTest {

    @Test
    void bindsStringToInteger() {
        MapConfigurationPropertySource source =
                new MapConfigurationPropertySource(
                        Map.of("worker.thread-count", "8")
                );

        Binder binder = new Binder(source);

        BindResult<Integer> result =
                binder.bind("worker.thread-count", Integer.class);

        assertThat(result.isBound()).isTrue();
        assertThat(result.get()).isEqualTo(8);
    }
}
```

Main flow:

```text
"worker.thread-count" -> "8"
          |
          v
  MapConfigurationPropertySource
          |
          v
   Binder.bind(... Integer.class)
          |
          v
     BindResult<Integer>
          |
          v
           8
```

This is a direct test of **type conversion combined with binding**, not a plain unit test of `Integer.parseInt`.

Run with Gradle:

```bash
./gradlew test --tests "com.example.configdemo.BinderBasicsTest"
```

In PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.configdemo.BinderBasicsTest"
```

If using Maven, run the test with your project's wrapper or command, such as `./mvnw test -Dtest=BinderBasicsTest` in the appropriate environment.

## 6. BindResult: Present or Absent?

`Binder#bind` typically returns a `BindResult<T>` rather than always returning `T` directly.

This lets you distinguish:

- Binding found matching data and produced a result.
- Binding found no data, so there is no result.
- Binding found data, but failed during conversion or object creation.

Given source:

```java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(
                Map.of("worker.thread-count", "8")
        );
Binder binder = new Binder(source);
```

When querying an existing key:

```java
BindResult<Integer> found =
        binder.bind("worker.thread-count", Integer.class);

assertThat(found.isBound()).isTrue();
assertThat(found.get()).isEqualTo(8);
```

When querying a missing key:

```java
BindResult<Integer> missing =
        binder.bind("worker.max-attempts", Integer.class);

assertThat(missing.isBound()).isFalse();
```

Do not call:

```java
missing.get();
```

without checking whether a result is present. `BindResult#get()` is for when a value exists and can throw an exception when unbound.

You can use:

```java
Integer attempts = missing.orElse(3);
```

or apply other logic through appropriate `BindResult` methods.

**Note:** a default in `BindResult#orElse(...)` is logic in **your test or caller code**; it does not mean Spring Boot automatically sets a runtime default for a `@ConfigurationProperties` bean registered in an ApplicationContext.

## 7. Binding a Record from a Small Map

A more realistic scenario is binding a group of keys into a Java record.

### 7.1. Defining the Record

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

public record ClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {
}
```

In this example, the record **is not required to carry `@ConfigurationProperties`**, because we explicitly pass the prefix to Binder in the test. If the class is also used by the real application, add the annotation to register it via configuration properties scanning/enabling.

### 7.2. Creating Test Data

```java
Map<String, Object> input = Map.of(
        "client.endpoint", "https://api.example.invalid",
        "client.connect-timeout", "5s",
        "client.max-retries", "4",
        "client.enabled", "true"
);
```

Here all values are intentionally placed as Strings, matching most externalized configuration sources. That prevents the test from "cheating" by putting a pre-built `Duration` into the Map.

### 7.3. Test Constructing the Record

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class ClientPropertiesBinderTest {

    @Test
    void bindsRecordAndConvertsValues() {
        MapConfigurationPropertySource source =
                new MapConfigurationPropertySource(
                        Map.of(
                                "client.endpoint",
                                "https://api.example.invalid",
                                "client.connect-timeout", "5s",
                                "client.max-retries", "4",
                                "client.enabled", "true"
                        )
                );

        ClientProperties properties =
                new Binder(source)
                        .bind("client", ClientProperties.class)
                        .get();

        assertThat(properties.endpoint())
                .isEqualTo(URI.create("https://api.example.invalid"));
        assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(5));
        assertThat(properties.maxRetries()).isEqualTo(4);
        assertThat(properties.enabled()).isTrue();
    }
}
```

Each assertion verifies part of the same contract:

| Source property | Record component | Result |
| --- | --- | --- |
| `client.endpoint` | `endpoint()` | `URI` |
| `client.connect-timeout` | `connectTimeout()` | `Duration.ofSeconds(5)` |
| `client.max-retries` | `maxRetries()` | `int 4` |
| `client.enabled` | `enabled()` | `true` |

**Key characteristic:** Binder does not need setters on a record. It uses constructor binding to create the object with converted values.

## 8. Distinguishing Direct Binder from @ConfigurationPropertiesScan

In a standard Spring Boot application:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {
}
```

The bean is discovered and registered via one of:

```java
@ConfigurationPropertiesScan
```

or:

```java
@EnableConfigurationProperties(ClientProperties.class)
```

In a direct test, however:

```java
new Binder(source).bind("client", ClientProperties.class)
```

we **do not ask a Spring ApplicationContext to register a bean**. The test code creates the Binder and chooses the prefix and target type directly.

This has two consequences:

1. Binder can instantiate a record without `@ConfigurationProperties`, as long as the type is bindable.
2. A direct binder test **does not prove the bean will be discovered by component scanning or configuration properties scanning** in the real application.

Therefore, use Binder tests for **type conversion and structural rules**, and `ApplicationContextRunner` or `@SpringBootTest` for **bean registration and Spring integration**.

## 9. Testing Duration Without application.yml

`Duration` is used for timeouts, wait times, and task intervals. Spring Boot supports convenient configuration syntax such as `500ms`, `3s`, and `2m`.

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class DurationBinderTest {

    @Test
    void convertsSeveralDurationFormats() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(
                        Map.of(
                                "time.fast", "250ms",
                                "time.normal", "3s",
                                "time.slow", "2m"
                        )
                )
        );

        assertThat(binder.bind("time.fast", Duration.class).get())
                .isEqualTo(Duration.ofMillis(250));

        assertThat(binder.bind("time.normal", Duration.class).get())
                .isEqualTo(Duration.ofSeconds(3));

        assertThat(binder.bind("time.slow", Duration.class).get())
                .isEqualTo(Duration.ofMinutes(2));
    }
}
```

This test confirms **Spring Boot's binder and conversion** understand duration suffixes. It is not testing plain Java's `Duration.parse(...)` syntax.

Distinguish between:

```java
Duration.parse("PT3S"); // ISO-8601 syntax
```

and the externalized configuration string:

```text
3s
```

Both representations mean the same duration, but are not necessarily parsed by the same API.

## 10. Testing DataSize with Unit Suffixes

Spring Boot uses `org.springframework.util.unit.DataSize` to express data sizes.

Test example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;
import org.springframework.util.unit.DataSize;

class DataSizeBinderTest {

    @Test
    void convertsMegabytes() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(
                        Map.of("upload.max-size", "2MB")
                )
        );

        DataSize size = binder.bind(
                "upload.max-size",
                DataSize.class
        ).get();

        assertThat(size).isEqualTo(DataSize.ofMegabytes(2));
        assertThat(size.toBytes()).isEqualTo(2L * 1024 * 1024);
    }
}
```

Using `DataSize` rather than manually splitting `"2MB"` into two string parts keeps the code expressive and reduces unit-calculation errors.

A test like this is ideal when ensuring a configuration accepts `512KB`, `2MB`, or another size limit according to Spring Boot conventions.

**Note:** exact unit variants and conversion behavior depend on the conversion system used by the Binder. With a Binder created in standard Spring Boot setups, Boot's standard converters typically support `DataSize`.

## 11. When to Use Map<String,Object> Instead of YAML?

A small Map is the right tool when your goal is **testing Binder**, because:

- No temporary files are needed.
- No YAML parser is needed.
- The test keeps inputs and expectations in one place.
- You can supply an invalid value without affecting any other tests.
- It is easy to build many scenarios with different key sets.

Example:

```java
Map<String, Object> config = new LinkedHashMap<>();
config.put("client.connect-timeout", "5s");
config.put("client.max-retries", "3");
```

This is already key/value data understood by `MapConfigurationPropertySource`.

However, **a Map does not test YAML structure**. If your goal is catching indentation mistakes or how Spring Boot loads Config Data, a Map test will not help.

Distinction:

| Requirement | Preferred tool |
| --- | --- |
| String `5s` to `Duration` | Binder + small Map |
| Kebab-case keys to camelCase record | Binder + small Map |
| Invalid `int` value causing BindException | Binder + small Map |
| List structure via indexed keys | Binder + small Map |
| Syntactically valid YAML file | Parser test or Config Data integration |
| Profile-specific configuration loaded properly | Integration test with profiles |
| `@ConfigurationProperties` bean registered | `ApplicationContextRunner` / `@SpringBootTest` |
| CLI, env, YAML precedence in practice | Spring Environment/Boot test with real sources |
| `@Validated` enforced on bean creation | Context test or explicit validation handler |

Choose the smallest test level that accurately answers the question.

## 12. Testing Key Names Under Relaxed Binding

In Java, fields typically use camelCase:

```java
int maxRetries;
Duration connectTimeout;
```

In configuration sources, kebab-case is recommended:

```properties
client.max-retries=3
client.connect-timeout=5s
```

Spring Boot's Binder supports **relaxed binding**: equivalent representations differing in separators or casing map to the corresponding logical configuration name.

Test with a record:

```java
public record RetryOptions(
        int maxRetries,
        Duration connectTimeout) {
}
```

And Map:

```java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(
                Map.of(
                        "retry.max-retries", "4",
                        "retry.connect-timeout", "750ms"
                )
        );

RetryOptions result = new Binder(source)
        .bind("retry", RetryOptions.class)
        .get();
```

Expectations:

```java
assertThat(result.maxRetries()).isEqualTo(4);
assertThat(result.connectTimeout())
        .isEqualTo(Duration.ofMillis(750));
```

This test hits the mark: kebab-case source names must bind to camelCase constructor parameters.

**Do not use this test to infer that typos in key names are auto-corrected by the binder.** For instance, `retry.max-retrise` is a spelling error, not a valid variant of `retry.max-retries`.

## 13. Testing When an Entire Prefix Is Absent from the Source

Consider a Map containing only:

```java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(
                Map.of("database.url", "jdbc:example")
        );

Binder binder = new Binder(source);
```

When binding a group that is completely absent:

```java
BindResult<ClientProperties> result =
        binder.bind("client", ClientProperties.class);

assertThat(result.isBound()).isFalse();
```

This differs from **having some keys under the prefix while missing required components**.

For example, the Map:

```java
Map.of(
    "client.endpoint", "https://api.example.invalid",
    "client.enabled", "true"
)
```

can cause the binder to construct a `ClientProperties` instance with the omitted components left unset. Exact behavior depends on the Java type, constructor, defaults, and binding policies.

Therefore:

- **Entire prefix absent:** typically checked via `isBound()`.
- **Prefix has some keys while omitting others:** inspect the bound object and/or apply validation if fields are required.

Do not assume a reference-type record component is automatically checked for `@NotNull` when calling Binder directly without configuring validation.

## 14. Testing Malformed Data Types

Suppose a bean requires an integer:

```java
public record WorkerOptions(int threadCount) {
}
```

Map with invalid data:

```java
Map.of("worker.thread-count", "many")
```

The key name is right, but `"many"` cannot be converted into `int` under standard conversion.

JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class InvalidTypeBinderTest {

    @Test
    void rejectsNonNumericThreadCount() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(
                        Map.of("worker.thread-count", "many")
                )
        );

        assertThrows(BindException.class, () ->
                binder.bind("worker.thread-count", Integer.class)
        );
    }
}
```

This test describes **conversion/binding failure** behavior. You can use AssertJ's `assertThatThrownBy(...)` to inspect details further when needed.

Avoid asserting on the exact full error message string, as exception wording and source formatting can change across Spring Boot versions.

For important tests, selectively verify the exception type, property name, or underlying cause.

## 15. Distinguishing Missing Keys from Wrong-Type Values

Two Maps:

**A — missing property:**

```java
Map.of("worker.name", "batch")
```

**B — key present, unconvertible value:**

```java
Map.of("worker.thread-count", "many")
```

For the bind call:

```java
binder.bind("worker.thread-count", Integer.class)
```

possible outcomes:

| Case | Situation |
| --- | --- |
| A | Target property not found; `BindResult#isBound()` is typically `false` |
| B | Property exists but type conversion fails; binding can throw `BindException` |

If `@DefaultValue` or an object-level fallback is used, behavior for a missing property can differ. However, **present but malformed** data is not automatically treated as missing.

This is an important distinction when writing tests: do not lump "absent value" and "invalid value" into the same assertion.

## 16. Testing Boolean and Enum Values

### 16.1. Boolean

```java
Binder binder = new Binder(
        new MapConfigurationPropertySource(
                Map.of("feature.enabled", "true")
        )
);

Boolean enabled =
        binder.bind("feature.enabled", Boolean.class).get();

assertThat(enabled).isTrue();
```

When business code needs an on/off toggle, `boolean` or `Boolean` is a natural fit. If you need to distinguish **undeclared** from **false**, use `Boolean` paired with appropriate required/default rules.

### 16.2. Enum

Suppose:

```java
public enum DispatchMode {
    FAST,
    SAFE,
    OFF
}
```

Test:

```java
Binder binder = new Binder(
        new MapConfigurationPropertySource(
                Map.of("dispatch.mode", "safe")
        )
);

DispatchMode mode =
        binder.bind("dispatch.mode", DispatchMode.class).get();

assertThat(mode).isEqualTo(DispatchMode.SAFE);
```

Spring Boot includes converters that match enum names in common input formats. A value completely outside the enum, such as `"teleport"`, has no reason to be guessed as `SAFE`.

When an application permits only a finite set of values, enums are generally safer and easier to test than free-form strings.

## 17. Testing Nested Objects

Real-world configuration often has multiple levels.

Example:

```yaml
gateway:
  endpoint: "https://gateway.example.invalid"
  retry:
    attempts: 4
    delay: 2s
```

Record:

```java
import java.net.URI;
import java.time.Duration;

public record GatewayOptions(
        URI endpoint,
        Retry retry) {

    public record Retry(
            int attempts,
            Duration delay) {
    }
}
```

MapConfigurationPropertySource:

```java
Map<String, Object> values = Map.of(
        "gateway.endpoint", "https://gateway.example.invalid",
        "gateway.retry.attempts", "4",
        "gateway.retry.delay", "2s"
);
```

Test:

```java
GatewayOptions gateway = new Binder(
        new MapConfigurationPropertySource(values)
).bind("gateway", GatewayOptions.class).get();

assertThat(gateway.endpoint())
        .isEqualTo(URI.create("https://gateway.example.invalid"));

assertThat(gateway.retry()).isNotNull();
assertThat(gateway.retry().attempts()).isEqualTo(4);

assertThat(gateway.retry().delay())
        .isEqualTo(Duration.ofSeconds(2));
```

This test verifies all of the following at once:

1. Binder matches the `gateway` prefix.
2. Binder matches the `gateway.retry.*` branch.
3. Binder constructs the `Retry` object with the expected values.
4. Binder passes the nested object into `GatewayOptions`.
5. `Duration` conversion works inside nested components.

**Note:** if all `gateway.retry.*` keys are omitted, the nested object may not be instantiated. If it is required, add appropriate validation or defaults rather than testing only the happy path.

## 18. Testing Lists Using Indexed Keys

YAML file:

```yaml
queue:
  delays:
    - 1s
    - 3s
    - 10s
```

In a Map, this can be written with indexed keys:

```java
Map<String, Object> values = Map.of(
        "queue.delays[0]", "1s",
        "queue.delays[1]", "3s",
        "queue.delays[2]", "10s"
);
```

Record:

```java
import java.time.Duration;
import java.util.List;

public record QueueOptions(List<Duration> delays) {
}
```

Test:

```java
QueueOptions options = new Binder(
        new MapConfigurationPropertySource(values)
).bind("queue", QueueOptions.class).get();

assertThat(options.delays()).containsExactly(
        Duration.ofSeconds(1),
        Duration.ofSeconds(3),
        Duration.ofSeconds(10)
);
```

This is a valuable test because the binder performs **two jobs**:

- Recognizing list structure from keys `[0]`, `[1]`, `[2]`.
- Converting each element from a string into a `Duration`.

If the test simply placed a pre-built `List<Duration>` in the Map, it would not fully verify per-element conversion.

## 19. Testing Maps Whose Values Require Type Conversion

Another configuration Map:

```yaml
routing:
  weights:
    blue: 50
    green: 30
```

Record:

```java
import java.util.Map;

public record RoutingOptions(Map<String, Integer> weights) {
}
```

Test data:

```java
Map<String, Object> input = Map.of(
        "routing.weights.blue", "50",
        "routing.weights.green", "30"
);
```

Binding:

```java
RoutingOptions result = new Binder(
        new MapConfigurationPropertySource(input)
).bind("routing", RoutingOptions.class).get();

assertThat(result.weights())
        .containsEntry("blue", 50)
        .containsEntry("green", 30);
```

Here `blue` and `green` are dynamic Map keys, while `"50"` and `"30"` must convert to `Integer`.

**Do not confuse MapConfigurationPropertySource with a target property of type Map**:

- `MapConfigurationPropertySource` is **how the source is passed into Binder**.
- `Map<String,Integer> weights` is **data inside the resulting object**.

The two Maps serve completely different roles.

## 20. Multiple Small Sources: Testing Precedence Rules

Binder can accept multiple `ConfigurationPropertySource` instances. The order you supply matters when the same key exists in multiple sources.

Example:

```java
MapConfigurationPropertySource overrides =
        new MapConfigurationPropertySource(
                Map.of("client.max-retries", "8")
        );

MapConfigurationPropertySource defaults =
        new MapConfigurationPropertySource(
                Map.of(
                        "client.max-retries", "3",
                        "client.enabled", "true"
                )
        );

Binder binder = new Binder(
        java.util.List.of(overrides, defaults)
);
```

Test:

```java
assertThat(
        binder.bind("client.max-retries", Integer.class).get()
).isEqualTo(8);

assertThat(
        binder.bind("client.enabled", Boolean.class).get()
).isTrue();
```

`overrides` comes first, so the duplicate key `max-retries` comes from that source. `enabled` exists only in `defaults`, so it still binds.

This is a helpful test when confirming **precedence across a test-constructed list of sources**.

However, it **does not prove** the full precedence order among CLI, environment variables, system properties, and Config Data in a real application. To test Spring Environment runtime policy, write tests using actual PropertySources or an ApplicationContext with matching sources.

## 21. Constructor Binding and Parameter-Name Requirements

With a record:

```java
public record WorkerOptions(int threadCount) {
}
```

Binder can use the canonical constructor to build the object from `worker.thread-count`.

With a regular class:

```java
public final class WorkerOptions {

    private final int threadCount;

    public WorkerOptions(int threadCount) {
        this.threadCount = threadCount;
    }

    public int getThreadCount() {
        return threadCount;
    }
}
```

constructor binding needs the corresponding parameter names, which in standard Java builds relates to preserving parameter-name metadata, such as the `-parameters` compiler flag.

Spring Boot's Gradle/Maven plugins configure this in typical builds; with custom build setups, verify parameter-name retention if the binder reports it cannot bind a constructor-based class.

**Do not test a record and assume every Java class with multiple constructors can be bound automatically without extra metadata.** Multiple constructors may require specifying which constructor is used for binding according to your Boot version's rules.

## 22. Binder Does Not Mean ApplicationContext

Consider three ways to construct a configuration object:

**A. Manual construction:**

```java
ClientProperties p = new ClientProperties(
        URI.create("https://api.example.invalid"),
        Duration.ofSeconds(5),
        4,
        true
);
```

This tests Java object behavior, not binding or conversion.

**B. Direct Binder call:**

```java
ClientProperties p = new Binder(source)
        .bind("client", ClientProperties.class)
        .get();
```

This tests binding/conversion and constructor binding, without requiring a Spring context bean.

**C. Registering with @ConfigurationProperties and starting a context:**

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(...) {
}
```

along with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

Approach C verifies both bean registration and Boot's context-level mechanisms, at the cost of broader scope and more setup.

No single approach is "always best." Choose based on the test's goal, not out of habit of using `@SpringBootTest` for everything.

## 23. Testing Constructor-Binding Default Values

Spring Boot supports `@DefaultValue` on record components or constructor parameters of compatible `@ConfigurationProperties` types.

Example:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.bind.DefaultValue;

public record PollingOptions(
        @DefaultValue("5s") Duration interval,
        @DefaultValue("10") int batchSize) {
}
```

A source supplying only:

```java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(
                Map.of("polling.batch-size", "20")
        );
```

Test:

```java
PollingOptions options = new Binder(source)
        .bind("polling", PollingOptions.class)
        .get();

assertThat(options.interval()).isEqualTo(Duration.ofSeconds(5));
assertThat(options.batchSize()).isEqualTo(20);
```

This test confirms a value supplied by the source overrides a component's default, while an omitted component receives its default.

Notes:

- `@DefaultValue` is part of the binding model; record defaults do not apply when calling `new PollingOptions(...)` directly in Java.
- If the **entire prefix is absent**, `binder.bind("polling", ...)` can return unbound; check `isBound()` instead of assuming Binder always creates an object.
- A present value with the **wrong type** is not treated as "missing" to trigger `@DefaultValue`.
- If you want to ensure a nested branch exists even when no child data is given, configure a default for that branch using the appropriate binder mechanism.

## 24. The Value "0" vs. an Absent Property

Suppose:

```java
public record RetryOptions(int maxAttempts) {
}
```

And the source only contains:

```java
Map.of("retry.mode", "safe")
```

In a constructor-binding scenario where the prefix has data but a primitive is missing, the resulting object may receive the primitive's default value, such as `0` for `int`.

That raises a question: was `0` intentionally specified by an operator, or is it a side effect of an omitted property?

If the application needs to distinguish the two states, use a reference type:

```java
public record RetryOptions(Integer maxAttempts) {
}
```

and enforce `@NotNull` where validation is active.

For configurations requiring a positive attempt count, `@Min(1)` is also appropriate, keeping in mind that **direct Binder does not automatically mean bean validation ran**.

## 25. Direct Binder Does Not Automatically Run All Spring Boot @Validated Logic

Consider the record:

```java
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;

@Validated
public record RetryOptions(
        @Min(1) int maxAttempts) {
}
```

A test building a Binder manually:

```java
new Binder(source).bind("retry", RetryOptions.class)
```

primarily tests binding and conversion. Do not assume that simply annotating the record with `@Validated` makes objects bound via **every `new Binder(...)` call** go through Bean Validation like an ApplicationContext-registered `@ConfigurationProperties` bean.

In a Boot application, configuration-properties registration sets up the appropriate `BindHandler` and validators. A manually constructed Binder in a test is a lower-level component.

If you want to verify **startup-like Bean Validation**, you have two options:

1. Use `ApplicationContextRunner` with the `@ConfigurationProperties` bean registered and a Jakarta Validation provider.
2. Invoke validation explicitly in the test—either retrieving the object from Binder and passing it to a Jakarta `Validator`, or configuring an appropriate validation bind handler.

Do not write a Binder test with `@Min(1)` on the record and claim runtime always rejects `0` when the test never actually invoked a validator.

## 26. Explicit Bean Validation After Binding

Suppose you want to keep the test small while still verifying Jakarta constraints.

Record:

```java
package com.example.configdemo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record JobOptions(
        @NotBlank String queue,
        @Min(1) int maxAttempts) {
}
```

Input:

```java
Map<String, Object> values = Map.of(
        "job.queue", " ",
        "job.max-attempts", "0"
);
```

Test using the Jakarta Validation API:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class JobOptionsValidationTest {

    @Test
    void validatesBoundObject() {
        JobOptions options = new Binder(
                new MapConfigurationPropertySource(
                        Map.of(
                                "job.queue", " ",
                                "job.max-attempts", "0"
                        )
                )
        ).bind("job", JobOptions.class).get();

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            var violations = validator.validate(options);

            assertThat(violations)
                    .extracting(v -> v.getPropertyPath().toString())
                    .contains("queue", "maxAttempts");
        }
    }
}
```

Key points:

- Binder constructs the object from string data.
- Jakarta Validator validates the object **afterward**, explicitly triggered by the test code.
- The test requires an appropriate Bean Validation provider on the test runtime classpath.
- This is a focused test for combining binding and validation; it does not prove Spring ApplicationContext registered the bean or enabled validation automatically.

To test true "fail fast at startup" behavior, use `ApplicationContextRunner` as covered later.

## 27. Direct Binder and Unknown Keys

Suppose a record expects:

```java
public record RetryOptions(int maxAttempts) {
}
```

but the source has a typo:

```java
Map.of("retry.max-attemps", "5")
```

The key `max-attemps` does not match `maxAttempts`.

A simple Binder test asking:

```java
binder.bind("retry", RetryOptions.class)
```

should not be mistaken for a **full-Map schema validator**. Binder only binds values needed by the target, and unknown-field behavior can be customized by bind handlers on different paths.

In Spring Boot, `@ConfigurationProperties(ignoreUnknownFields = false)` can reject unbound properties within the bean's scope when the configuration-properties binding infrastructure is active.

However, **do not assume a Binder created directly via `new Binder(source)` enforces the same policy merely because the Java type has the annotation**.

If you need to test unknown fields at the Binder level, look into `BindHandler` implementations like `NoUnboundElementsBindHandler` and configure it explicitly—or use a context test closer to runtime behavior.

## 28. What Is BindHandler Used For?

Spring Boot provides the `BindHandler` API to hook into binding stages, such as before/after binding, error handling, and extra policies.

In real applications, bind handlers can be involved in:

- checking for unbound configuration elements;
- validating objects;
- handling specific binding failure conditions;
- observing/reporting in developer tooling.

However, **a basic type-conversion test does not need a custom BindHandler**.

Example:

```java
Binder binder = new Binder(
        new MapConfigurationPropertySource(
                Map.of("worker.max-attempts", "4")
        )
);

int attempts = binder.bind(
        "worker.max-attempts", Integer.class
).get();
```

If the goal is just converting `"4"` to an integer, this setup is clear enough.

When adding a bind handler, make sure your test actually checks the **specific behavior provided by the handler** without mixing unrelated error types.

## 29. Placeholders and Map Binder Limitations

In real applications, configuration values can use placeholders:

```properties
service.base-url=https://api.example.invalid
client.endpoint=\${service.base-url}/v1
```

An `Environment` with an appropriate property resolver resolves placeholders per Spring rules.

When constructing Binder directly:

```java
new Binder(new MapConfigurationPropertySource(values))
```

you are supplying a minimal source and **have not necessarily configured the same `PlaceholdersResolver` as a Binder backed by a Spring Environment**.

Do not write a test expecting every `\${...}` expression to resolve identically to a fully booted Spring Boot application.

If placeholders are the focus of the test:

- Configure a `PlaceholdersResolver` on the Binder explicitly, or
- Use `Binder.get(environment)` with a `ConfigurableEnvironment` holding test data, or
- Choose `ApplicationContextRunner` to test in a more runtime-like context.

This distinction is especially important when converting to `URI` or `Duration`: an unresolved placeholder can cause conversion to fail even if the post-resolution value would be valid.

## 30. Using Binder.get(Environment) When a More Realistic Environment Is Needed

Spring Boot lets you obtain a Binder from a Spring `Environment` instead of constructing a MapConfigurationPropertySource manually.

Simple test example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

class EnvironmentBinderTest {

    @Test
    void bindsFromMockEnvironment() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty("client.max-retries", "6");

        Integer retries = Binder.get(environment)
                .bind("client.max-retries", Integer.class)
                .get();

        assertThat(retries).isEqualTo(6);
    }
}
```

`MockEnvironment` is part of Spring's test utilities and is available through standard test dependencies.

This example still avoids starting a full ApplicationContext. It simply shifts inputs from a standalone MapConfigurationPropertySource into a test Environment.

**When to choose which:**

- `new Binder(new MapConfigurationPropertySource(...))` when you want a tiny test with exact key control.
- `Binder.get(environment)` when you need to observe how the binder interacts with an Environment's PropertySources, especially around placeholders or multiple sources.

Not every aspect of Spring Boot Config Data appears just by creating `MockEnvironment`. It does not automatically load profile-specific YAML files like a real SpringApplication.

## 31. An ApplicationContextRunner Test for the Same Contract

To verify broader behavior—whether the bean is registered, bound, and injectable in a context—use `ApplicationContextRunner`.

Record:

```java
package com.example.configdemo;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        Duration connectTimeout,
        int maxRetries) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientPropertiesContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsAsSpringBean() {
        runner.withPropertyValues(
                "client.connect-timeout=3s",
                "client.max-retries=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            ClientProperties props =
                    context.getBean(ClientProperties.class);

            assertThat(props.connectTimeout())
                    .isEqualTo(Duration.ofSeconds(3));
            assertThat(props.maxRetries()).isEqualTo(4);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfig {
    }
}
```

Comparison:

| Criterion | Direct Binder | ApplicationContextRunner |
| --- | --- | --- |
| Starts Spring context? | No | Yes, a small context |
| Needs bean registration? | No | Yes |
| Chooses prefix in call? | Yes | Usually from `@ConfigurationProperties` |
| Tests type conversion? | Yes | Yes |
| Tests bean registration? | No | Yes |
| Tests Boot context binder hooks? | Partial if manually configured | Yes, per context configuration |
| Speed and footprint | Minimal | Slightly more, still lightweight |

You do not need to write both test types for every configuration class. Choose based on project risk and goals.

## 32. Source Precedence: Map Binder Tests Are Not Enough to Verify Spring Boot

You can construct two Maps:

```java
MapConfigurationPropertySource first =
        new MapConfigurationPropertySource(
                Map.of("client.max-retries", "6")
        );

MapConfigurationPropertySource second =
        new MapConfigurationPropertySource(
                Map.of("client.max-retries", "3")
        );
```

Then:

```java
int retries = new Binder(
        java.util.List.of(first, second)
).bind("client.max-retries", Integer.class).get();

assertThat(retries).isEqualTo(6);
```

This test proves that the order **you passed into Binder** determines which value is chosen.

However, Spring Boot's default precedence across CLI, system properties, environment variables, profile-specific Config Data, `SPRING_APPLICATION_JSON`, and test properties is a broader concern.

If you want to verify production environments pick up values from environment variables properly, test via an appropriate `Environment` or SpringApplication rather than concluding from a Map Binder alone.

## 33. Keeping Tests Independent of External Configuration

One major advantage of Map Binder tests is that **tests are unaffected by the runner's environment**.

Example:

```java
Map<String, Object> values = Map.of(
        "client.max-retries", "7",
        "client.connect-timeout", "500ms"
);
```

Even if the shell running the test has:

```text
CLIENT_MAXRETRIES=99
```

a direct Binder using only that Map does not read that variable just because it exists in the process environment.

This keeps test results consistent across developer machines and CI.

If you intentionally want to test environment variables, build an appropriate source or use an Environment/context test instead of mixing them with a pure Map test.

**Test isolation** is the technique's greatest benefit: each test owns its own input data.

## 34. Writing a Small Helper to Reduce Repetition in Tests

When multiple tests share the same pattern, you can write a helper:

```java
import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

final class BinderTestSupport {

    private BinderTestSupport() {
    }

    static Binder binderOf(Map<String, ?> properties) {
        return new Binder(
                new MapConfigurationPropertySource(properties)
        );
    }
}
```

Usage:

```java
Binder binder = BinderTestSupport.binderOf(
        Map.of(
                "client.timeout", "2s",
                "client.max-retries", "4"
        )
);
```

This helper pays off when:

- Many tests share the same Map Binder construction.
- You need to switch to a shared, explicitly configured converter/placeholder resolver.
- You want each test focused on one set of properties and expectations.

Do not build a complex test framework that obscures input keys. A good test should still let readers immediately see **key -> raw value -> target type -> expected value**.

## 35. Catching Silent Typo Bugs

A typo:

```java
Map.of("client.connect-timout", "5s")
```

differs from:

```java
Map.of("client.connect-timeout", "5s")
```

If your tests only cover the happy path, they do not show what the application will do when an operator misspells a key.

You can write two separate tests:

**Test 1: right key**

```java
assertThat(
        new Binder(new MapConfigurationPropertySource(
                Map.of("client.connect-timeout", "5s")
        )).bind("client.connect-timeout", Duration.class).get()
).isEqualTo(Duration.ofSeconds(5));
```

**Test 2: key missing due to typo**

```java
BindResult<Duration> result =
        new Binder(new MapConfigurationPropertySource(
                Map.of("client.connect-timout", "5s")
        )).bind("client.connect-timeout", Duration.class);

assertThat(result.isBound()).isFalse();
```

Test 2 shows that Binder **does not auto-correct misspelled keys**.

If the contract requires startup failure on unknown fields, configure strict checking on the appropriate binding path. Testing `isBound()==false` is not equivalent to runtime detecting and rejecting an unknown key.

## 36. Boundary-Value Testing

A strong test suite includes **normal values, boundary values, and invalid inputs**.

Example with timeouts:

| Input | Target type | Expected |
| --- | --- | --- |
| `1ms` | `Duration` | 1 millisecond |
| `500ms` | `Duration` | 500 milliseconds |
| `2s` | `Duration` | 2 seconds |
| `PT3S` | `Duration` | 3 seconds per ISO-8601 |
| `invalid` | `Duration` | Binding/conversion failure |
| Key absent | `Duration` | `BindResult#isBound()==false` when binding a single key |

With integers:

| Input | Target type | Expected |
| --- | --- | --- |
| `0` | `Integer` | `0`, valid type |
| `1` | `Integer` | `1` |
| `-1` | `Integer` | `-1`, valid type though possibly invalid business-wise |
| `many` | `Integer` | Conversion error |
| Key absent | `Integer` | Unbound |

A Binder test only checks **type validity**, unless you also configure validation logic. For example, `-1` is a valid integer even if retry counts may never be negative.

## 37. How to Inspect BindException Failures

When binding fails, you may observe a `BindException` or related exception caused by conversion or object construction.

In a test, you can write:

```java
BindException exception = assertThrows(
        BindException.class,
        () -> binder.bind("client.max-retries", Integer.class)
);
```

For an input `"many"`, the test can check:

- whether an error occurred;
- which property path was being bound;
- the requested target type;
- the conversion root cause in the `getCause()` chain if needed.

However, exception messages can differ between Spring Boot versions. Do not match multi-line log output verbatim in assertions when the goal is verifying a conversion failure.

A concise assertion focused on **error type and trigger condition** is far more resilient.

## 38. Testing Custom Type Conversion

Sometimes configuration requires a custom domain type.

Suppose:

```java
public record RegionCode(String value) {
    public RegionCode {
        if (value == null
                || !value.matches("[A-Z]{2}-[A-Z]{2}")) {
            throw new IllegalArgumentException(
                    "RegionCode must match XX-YY");
        }
    }
}
```

Source:

```properties
routing.region=vn-sg
```

If you want `"vn-sg"` to convert automatically to `RegionCode("VN-SG")`, you can write a `Converter<String,RegionCode>`:

```java
import java.util.Locale;

import org.springframework.core.convert.converter.Converter;

public class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

In a direct Binder test, you must **register the converter in the conversion system used by Binder**. Simply declaring the converter class in source code does not make `new Binder(mapSource)` discover it automatically.

High-level view:

```text
MapConfigurationPropertySource
            |
            v
       Configured Binder
            |
            v
  ConversionService with converter
            |
            v
        RegionCode("VN-SG")
```

At runtime, Spring Boot can pick up converters for `@ConfigurationProperties` from beans annotated with `@ConfigurationPropertiesBinding`. A manually constructed Binder **does not component-scan** those beans.

This is a critical boundary when unit testing custom conversions: testing the Converter directly only checks `convert(...)` logic; to verify Binder actually applies the Converter, register it with the Binder or use a context test with converter registration enabled.

## 39. Example: Binder with a Custom ConversionService

To test integration between a Map Binder and a custom converter, you can create a ConversionService and pass it to a Binder constructor overload that accepts conversion support.

Illustrative example using Spring Boot 3.x types:

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;
import org.springframework.core.convert.ConversionService;
import org.springframework.format.support.DefaultFormattingConversionService;

class CustomConverterExample {

    static RegionCode bindRegion() {
        DefaultFormattingConversionService conversions =
                new DefaultFormattingConversionService();

        conversions.addConverter(
                String.class,
                RegionCode.class,
                raw -> new RegionCode(
                        raw.trim().toUpperCase(Locale.ROOT))
        );

        MapConfigurationPropertySource source =
                new MapConfigurationPropertySource(
                        Map.of("routing.region", "vn-sg")
                );

        Binder binder = new Binder(
                List.of(source),
                null,
                conversions
        );

        return binder.bind("routing.region", RegionCode.class).get();
    }
}
```

`DefaultFormattingConversionService` serves here as a conversion service for the custom-type example. For standard Boot configuration types, note that `ApplicationConversionService` provides additional converters such as `Duration` and `DataSize`.

Depending on your Spring Boot version, Binder overloads or how conversion services are supplied can vary; match the constructor signature for your version. When the goal is testing a converter in **Spring Boot runtime**, `ApplicationContextRunner` with a converter bean annotated `@ConfigurationPropertiesBinding` is a closer fit.

The key rule remains: **the test must explicitly register the converter** if you want to verify Binder uses that custom conversion.

## 40. Do Not Mix Custom Conversion with Schema Checking

A custom converter can validate the representation of a single value, such as RegionCode matching `XX-YY`.

However, it does not solve:

- A misspelled key like `routing.regoin`.
- An entire configuration group missing.
- Another profile failing to load.
- A service not being registered in the context.
- Precedence between CLI and Config Data.
- A Map containing unexpected keys.

To restrict keys in a group, control the namespace and unknown-field strategy. To require values, use defaults or validation. To verify loaders, test the loader/context.

Takeaway: **keep responsibilities separated** so that when a test fails, you can pinpoint the exact failing layer.

## 41. Testing with Given–When–Then Style

A readable test layout:

**Given — small input data**

```java
Map<String, Object> input = Map.of(
        "client.connect-timeout", "500ms"
);
```

**When — Binder performs binding**

```java
Duration result = new Binder(
        new MapConfigurationPropertySource(input)
).bind("client.connect-timeout", Duration.class).get();
```

**Then — compare Java values**

```java
assertThat(result).isEqualTo(Duration.ofMillis(500));
```

A concise test method combining all three parts:

```java
@Test
void bindsDurationFromMilliseconds() {
    // Given
    MapConfigurationPropertySource source =
            new MapConfigurationPropertySource(
                    Map.of("client.connect-timeout", "500ms")
            );

    // When
    Duration timeout = new Binder(source)
            .bind("client.connect-timeout", Duration.class)
            .get();

    // Then
    assertThat(timeout).isEqualTo(Duration.ofMillis(500));
}
```

Inputs and outcomes are immediately obvious, allowing anyone to read the test without booting a full Spring Boot application to trace it.

## 42. Should a Test Use Many Properties at Once?

If the goal is testing **one specific converter**, supply only one or a few keys:

```java
Map.of("upload.max-size", "2MB")
```

If the goal is testing **constructor binding of a record**, include all relevant fields:

```java
Map.of(
        "client.endpoint", "https://api.example.invalid",
        "client.connect-timeout", "5s",
        "client.max-retries", "4",
        "client.enabled", "true"
)
```

Do not include dozens of unrelated keys like `spring.datasource.password`, `logging.level.root`, or `server.port`. Those reduce isolation and can mislead readers into thinking a direct Binder test is exercising the full Spring Boot runtime.

**Small test data does not mean a sloppy test; it means the test is designed so failure causes are always easy to diagnose.**

## 43. Where Should Tests Live?

Project layout:

```text
src/
  main/
    java/
      com/example/configdemo/
        ClientProperties.java
    resources/
      application.yml
  test/
    java/
      com/example/configdemo/
        ClientPropertiesBinderTest.java
        ClientPropertiesContextTest.java
        ClientPropertiesValidationTest.java
```

The three test classes have distinct responsibilities:

- `ClientPropertiesBinderTest`: type conversion and binding with a small Map.
- `ClientPropertiesContextTest`: registering configuration-properties beans in a context.
- `ClientPropertiesValidationTest`: required constraints and domain limits.

You do not need all three files for every small record. This structure shows how to split them when a project grows complex enough that different protective layers need independent verification.

If tests are slow because they boot a full application context just to check `Duration`, consider converting those cases into Binder tests.

## 44. A Complete Test Suite for a Configuration Contract

A complete, ready-to-adapt example for a Spring Boot project:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class ClientConfigBindingTest {

    private static Binder binderOf(Map<String, ?> values) {
        return new Binder(
                new MapConfigurationPropertySource(values)
        );
    }

    @Test
    void bindsRecordWithTypedFields() {
        ClientProperties options = binderOf(
                Map.of(
                        "client.endpoint",
                        "https://api.example.invalid",
                        "client.connect-timeout", "3s",
                        "client.max-retries", "4",
                        "client.enabled", "true"
                )
        ).bind("client", ClientProperties.class).get();

        assertThat(options.endpoint())
                .isEqualTo(URI.create("https://api.example.invalid"));
        assertThat(options.connectTimeout())
                .isEqualTo(Duration.ofSeconds(3));
        assertThat(options.maxRetries()).isEqualTo(4);
        assertThat(options.enabled()).isTrue();
    }

    @Test
    void reportsMissingSingleProperty() {
        Binder binder = binderOf(
                Map.of("client.enabled", "true")
        );

        assertThat(
                binder.bind("client.connect-timeout", Duration.class)
                      .isBound()
        ).isFalse();
    }

    @Test
    void rejectsInvalidInteger() {
        Binder binder = binderOf(
                Map.of("client.max-retries", "many")
        );

        assertThrows(BindException.class, () ->
                binder.bind("client.max-retries", Integer.class)
        );
    }

    @Test
    void bindsMilliseconds() {
        Binder binder = binderOf(
                Map.of("client.connect-timeout", "750ms")
        );

        assertThat(
                binder.bind("client.connect-timeout", Duration.class)
                      .get()
        ).isEqualTo(Duration.ofMillis(750));
    }
}
```

Record used in the example:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

public record ClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {
}
```

If this record is also used as a Spring bean in the real application, you can add `@ConfigurationProperties(prefix="client")` and register it accordingly. The direct Binder test still supplies the `client` prefix explicitly.

This suite focuses on four exact goals: **typed object construction, absent keys, failed conversion, and time units**.

## 45. Common Misconceptions

### 45.1. "Testing @ConfigurationProperties always requires @SpringBootTest"

False. For binding and type conversion, Binder with a small Map source is sufficient.

### 45.2. "MapConfigurationPropertySource reads application.yml"

False. It wraps only the values you put into the Map. To verify YAML loading, use a different test.

### 45.3. "Adding @ConfigurationProperties makes new Binder know the prefix"

Do not assume that. In direct Binder tests, you pass the prefix in `binder.bind("client", ...)`.

### 45.4. "An unbound BindResult means a conversion error"

False. Unbound usually means no matching value was present to bind. Conversion failures typically throw an exception.

### 45.5. "Testing Integer=-1 proves @Min ran"

False. Converting to `int -1` succeeds; business validation is a separate concern.

### 45.6. "@Validated runs automatically on every new Binder(...) call"

Do not assume that. Direct Binder is not the entire Spring context configuration-properties lifecycle.

### 45.7. "A custom Converter in the source tree is automatically picked up by Binder"

False. Register the converter in the service/handler used by Binder, or test via a context with converter registration.

### 45.8. "Testing Binder with two Maps proves full Boot precedence"

False. It only proves the precedence order of the sources the test explicitly passed to Binder.

### 45.9. "A Map containing a pre-built Duration still tests String-to-Duration conversion"

Incomplete. To test conversion, pass `"3s"` as a raw String input.

### 45.10. "A Binder Map test guarantees prod configuration is right"

False. Profiles, Config Data imports, external file paths, and deployment environments need dedicated tests.

### 45.11. "Without a context you cannot test validation"

You can invoke Jakarta Validator explicitly after binding; however, to test context fail-fast behavior, you need a context test.

### 45.12. "Misspelled keys are automatically corrected by Binder"

False. Relaxed binding handles formatting variations of names, not typo correction.

## 46. Workflow for Selecting the Right Test Level

When planning a configuration test, answer these questions in order:

**Question 1 — Am I testing simple key names and type conversion?**

Use:

```java
Binder binder = new Binder(
        new MapConfigurationPropertySource(values)
);
```

**Question 2 — Am I testing nested objects, Lists, or Maps?**

Binder tests still fit well; supply proper dotted/indexed names and keep test inputs small.

**Question 3 — Do I need to verify a custom converter is actually registered?**

Use a Binder configured explicitly with the converter, or an `ApplicationContextRunner` with the converter bean registered.

**Question 4 — Do I want to test @Validated, bean registration, or Spring context @ConfigurationProperties mechanics?**

Prefer `ApplicationContextRunner`. If the full application is needed, use `@SpringBootTest`.

**Question 5 — Do I want to ensure application-prod.yml loads under the prod profile?**

Use an integration test with real profiles and Config Data.

**Question 6 — Do I want to verify `java -jar` in production has the right env vars, config locations, and secrets?**

Use smoke/integration tests against the packaged artifact and startup command, not just a unit-level Binder test.

Good test design does not pick a single layer; it **uses the right layer for each risk**.

## 47. Exercise A — Binding an Integer

Create Map:

```java
Map.of("scheduler.pool-size", "12")
```

Task: use Binder to obtain an `Integer` equal to 12.

Solution:

```java
Integer size = new Binder(
        new MapConfigurationPropertySource(
                Map.of("scheduler.pool-size", "12")
        )
).bind("scheduler.pool-size", Integer.class).get();

assertThat(size).isEqualTo(12);
```

## 48. Exercise B — Duration and DataSize

Input:

```java
Map.of(
        "upload.timeout", "1500ms",
        "upload.max-size", "3MB"
)
```

Questions:

1. How many seconds does `upload.timeout` convert to as a `Duration`?
2. How many bytes does `upload.max-size` convert to as a `DataSize`?

Answers:

- `1500ms` equals `Duration.ofMillis(1500)`, i.e., 1.5 seconds.
- `3MB` equals `3 * 1024 * 1024` bytes under Spring Boot's standard `DataSize` convention.

You can verify with:

```java
assertThat(
        binder.bind("upload.timeout", Duration.class).get()
).isEqualTo(Duration.ofMillis(1500));

assertThat(
        binder.bind("upload.max-size", DataSize.class)
              .get().toBytes()
).isEqualTo(3L * 1024 * 1024);
```

## 49. Exercise C — Missing Key vs. Wrong Type

Given two Maps:

```java
Map.of("task.enabled", "true")
```

and:

```java
Map.of("task.max-attempts", "many")
```

When binding `task.max-attempts` to `Integer`:

- The first Map **lacks the key** to bind; the result is typically unbound.
- The second Map **has the key with an invalid value format**; it can throw `BindException`.

Write two tests using `isBound()` and `assertThrows(...)` respectively.

## 50. Exercise D — Nested Record

Record:

```java
public record CacheOptions(Retry retry) {

    public record Retry(int attempts, Duration delay) {
    }
}
```

Source:

```java
Map.of(
        "cache.retry.attempts", "3",
        "cache.retry.delay", "250ms"
)
```

Solution:

```java
CacheOptions options = new Binder(
        new MapConfigurationPropertySource(
                Map.of(
                        "cache.retry.attempts", "3",
                        "cache.retry.delay", "250ms"
                )
        )
).bind("cache", CacheOptions.class).get();

assertThat(options.retry().attempts()).isEqualTo(3);
assertThat(options.retry().delay())
        .isEqualTo(Duration.ofMillis(250));
```

## 51. Exercise E — Identifying Binder Test Limits

A team discovers:

- A Binder test with `client.timeout=5s` passes.
- When running the JAR in production, the timeout is still 30 seconds.

Can you conclude the Binder has a bug?

**Not yet.** Check the effective value in production: which profile is active, whether CLI/environment/system properties override it, which Config Data files were loaded, and whether the deployed JAR is the expected version.

A Binder test only verifies behavior against the small input set **declared inside that test**.

## 52. Exercise F — Defaults and Validation

A record:

```java
public record RetryOptions(
        @DefaultValue("3") int attempts) {
}
```

The source contains:

```java
Map.of("retry.mode", "safe")
```

Questions:

1. Which default value can Binder use for `attempts`?
2. If the source contains `retry.attempts=many`, does it fall back to `3`?
3. Does adding `@Min(1)` make a direct Binder test automatically execute Jakarta Validation?

Answers:

1. Under matching constructor binding, the declared default is `3`.
2. Do not assume that; a present value with an invalid type can cause a binding failure.
3. Do not infer that; call a validator explicitly or use a Spring context test with appropriate validation configured.

## 53. Key Takeaways

- **`Binder` lets you test configuration binding without launching a Spring ApplicationContext.**
- **`MapConfigurationPropertySource`** is a small, explicit source suited to unit-level tests.
- `Binder#bind(...)` returns **`BindResult<T>`**; check `isBound()` before calling `get()` when a value may be absent.
- Binder combines **key lookup and type conversion**; you can test Strings converting to `Integer`, `Boolean`, `Duration`, `DataSize`, `URI`, or enums.
- For records, Binder performs **constructor binding**; you can test nested records, indexed lists, and Maps.
- Keep inputs as **raw strings** when the goal is verifying real conversion, rather than supplying pre-converted Java objects.
- **Absent keys** differ from **present keys with wrong types**; test the two cases with separate assertions.
- Direct Binder tests **do not prove** that `@ConfigurationProperties` beans are scanned/registered, that validators ran, that placeholders resolve as at runtime, or that files/profiles load properly.
- For custom converters, configure conversion explicitly; a `Converter` class is not discovered automatically by Binder.
- Use `ApplicationContextRunner` when checking Binder integration with Spring bean registration and validation; use `@SpringBootTest` or smoke tests when verifying application/artifact-wide configuration.
- A reliable test suite combines **small Binder tests for binding rules**, **context tests for wiring and validation**, and **integration/smoke tests for deployment environments**.
