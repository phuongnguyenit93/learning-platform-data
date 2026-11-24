# Testing Collections, Nested Objects, Blank Values, and Missing Configuration in Spring Boot

## 1. Lesson Objectives

Spring Boot configuration is rarely limited to a few String or Integer keys. In real applications, `@ConfigurationProperties` often contains:

- `List<String>`, `List<Server>`, or `Set<String>`.
- `Map<String, String>` and Maps holding complex objects.
- Multi-level nested records or JavaBeans.
- Optional fields, defaulted fields, and required fields.
- Empty strings, whitespace-only strings, empty Lists, and empty Maps.
- Boolean `false`, integer `0`, or a zero `Duration`.
- Settings present in the base file yet overridden by profiles or higher-priority sources.

This lesson teaches how to test **post-binding results** rather than just checking whether a YAML file contains a particular line.

Questions to answer clearly:

1. Given a List, are element count and ordering preserved?
2. When a new profile overrides a List, are items appended or replaced?
3. Does a Map with special keys like `/admin` or `api.v2` preserve exact keys?
4. When a nested group is absent, does the nested object become null?
5. What is the difference between `retry: {}` and omitting `retry`?
6. How does `@DefaultValue` behave at the field level vs. nested-object level?
7. How do `@NotEmpty`, `@NotBlank`, `@NotNull`, and `@Valid` differ?
8. How do you test "missing key" separately from "present key with wrong type"?
9. When should you use `Binder`, `ApplicationContextRunner`, or `@SpringBootTest`?

Examples target Spring Boot 3.x, Java 17+, JUnit 5, and AssertJ. All data is dummy data with no production credentials.

## 2. Distinguishing Four Stages to Test

A configuration property passes through these stages:

~~~text
application.yaml / application-{profile}.yaml
OS environment / System properties / CLI / test properties
                         |
                         v
                   Environment
                  PropertySources
                         |
                         v
                 Binder + Conversion
                         |
                 +-------+-------+
                 |               |
                 v               v
          Object bound     Conversion error
                 |
                 v
         @ConfigurationProperties
                 |
                 v
          @Validated + @Valid
                 |
           +-----+-----+
           |           |
           v           v
         Valid   Validation error
~~~

A good test knows which layer it targets:

- **Source loading:** did the file or profile enter `Environment`?
- **Binding:** do property names match Java members and target types?
- **Conversion:** does `"5s"` convert into `Duration.ofSeconds(5)`?
- **Validation:** do Lists and nested objects satisfy business policies?

For example, `retry-count=abc` for `int retryCount` is a **conversion error**, not "undeclared." Conversely, `retry-count=0` converts cleanly yet may violate `@Min(1)`.

Never lump these cases into a single vague "bad configuration" branch without dedicated tests.

## 3. Configuration Model Used Throughout

~~~java
package com.example.demo.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        boolean enabled,
        List<String> regions,
        List<Endpoint> endpoints,
        Map<String, String> headers,
        Retry retry) {

    public record Endpoint(
            String name,
            String url) {
    }

    public record Retry(
            Integer maxAttempts,
            Duration initialDelay) {
    }
}
~~~

A valid `application.yaml`:

~~~yaml
app:
  delivery:
    enabled: true
    regions:
      - apac
      - emea
    endpoints:
      - name: primary
        url: https://primary.example.test
      - name: backup
        url: https://backup.example.test
    headers:
      client: demo-app
      region: apac
    retry:
      max-attempts: 3
      initial-delay: 500ms
~~~

Expected result:

| Member | Java type | Value |
| --- | --- | --- |
| `enabled` | `boolean` | `true` |
| `regions` | `List<String>` | `["apac","emea"]` |
| `endpoints` | `List<Endpoint>` | Two records with name and url |
| `headers` | `Map<String,String>` | client and region |
| `retry` | `Retry` | Non-null object |
| `retry.maxAttempts` | `Integer` | 3 |
| `retry.initialDelay` | `Duration` | 500 ms |

Reminder: `@ConfigurationProperties` alone does not make a class a bean. In the application:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

In small test contexts, register it explicitly via `@EnableConfigurationProperties(DeliveryProperties.class)`.

## 4. Choosing the Right Test Tool

| What to verify | Tool | Keep in mind |
| --- | --- | --- |
| A property or object from simulated keys | `Binder` + `MapConfigurationPropertySource` | No Spring context needed |
| Collection has the right element type | `Bindable.listOf`, `Bindable.mapOf` | Preserves generic type info |
| Bean binds and instantiates in context | `ApplicationContextRunner` | Register class via `@EnableConfigurationProperties` |
| Validation causes startup failure | `ApplicationContextRunner` with validation provider | Requires `@Validated` and constraints |
| Real profile file loads and overrides | `@SpringBootTest` + `@ActiveProfiles` | Avoid test sources overriding keys under test |
| OS environment variable has exact name | Properly prepared environment test | Map property source is not always identical to OS env |
| Full startup with production config files | Integration test selecting files/profiles | May need fake infrastructure for other beans |

`spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and `ApplicationContextRunner`. When using Jakarta Bean Validation, include a provider such as `spring-boot-starter-validation`.

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

## 5. Testing List<String>: Do Not Check Only One Element

YAML:

~~~yaml
app:
  delivery:
    regions:
      - apac
      - emea
      - americas
~~~

Assertion:

~~~java
assertThat(properties.regions())
        .containsExactly("apac", "emea", "americas");
~~~

`containsExactly` verifies **exact count and exact order**. When order carries business meaning, this is the right choice.

If order does not matter:

~~~java
assertThat(properties.regions())
        .containsExactlyInAnyOrder(
                "apac", "emea", "americas");
~~~

Never assert only:

~~~java
assertThat(properties.regions())
        .contains("apac");
~~~

because a List missing `emea` would still pass.

Equivalent `application.properties` syntax:

~~~properties
app.delivery.regions[0]=apac
app.delivery.regions[1]=emea
app.delivery.regions[2]=americas
~~~

For simple scalar Lists, comma-separated syntax also works:

~~~properties
app.delivery.regions=apac,emea,americas
~~~

For Lists of objects, indexed syntax or YAML sequences are clearer.

## 6. Unit Testing Lists with Binder

Full JUnit 5 example without starting a Spring context.

~~~java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class ListBindingTest {

    @Test
    void bindsIndexedStringsInOrder() {
        var source = new MapConfigurationPropertySource(
                Map.of(
                        "app.regions[0]", "apac",
                        "app.regions[1]", "emea"));

        Binder binder = new Binder(source);

        BindResult<List<String>> result =
                binder.bind(
                        "app.regions",
                        Bindable.listOf(String.class));

        assertThat(result.isBound()).isTrue();
        assertThat(result.get())
                .containsExactly("apac", "emea");
    }
}
~~~

`Bindable.listOf(String.class)` tells Binder the element type. Do not pass `List.class` when tests must verify conversion of each element to `Duration`, `Integer`, or complex records.

Example with `List<Duration>`:

~~~properties
app.delays[0]=100ms
app.delays[1]=2s
~~~

Expected:

~~~java
assertThat(delays)
        .containsExactly(
                Duration.ofMillis(100),
                Duration.ofSeconds(2));
~~~

If one element is `not-a-duration`, Binder throws a conversion error; test that separately rather than expecting an empty default List.

## 7. Lists of Objects: Checking Elements and Child Fields

Source:

~~~properties
app.delivery.endpoints[0].name=primary
app.delivery.endpoints[0].url=https://primary.example.test
app.delivery.endpoints[1].name=backup
app.delivery.endpoints[1].url=https://backup.example.test
~~~

With `List<Endpoint>` in `DeliveryProperties`:

~~~java
assertThat(properties.endpoints())
        .containsExactly(
                new DeliveryProperties.Endpoint(
                        "primary", "https://primary.example.test"),
                new DeliveryProperties.Endpoint(
                        "backup", "https://backup.example.test"));
~~~

Records implement `equals` across all components, so this verifies count, order, and every field of each element together.

Boundary case:

~~~properties
app.delivery.endpoints[0].name=primary
~~~

There is enough data for Binder to instantiate an element, yet `url` becomes null when no default exists.

**Common mistake:** calling only `assertThat(endpoints).hasSize(1)` and assuming config is valid. A non-empty List does not guarantee element contents are valid. When URL is required, add validation and test missing/blank URL cases.

## 8. Crucial Rule: Lists Across Sources Do Not Merge Automatically

When multiple `PropertySource`s or profiles define a List, Spring Boot follows this rule: **the highest-precedence List replaces the entire List** instead of combining elements.

Example `application.yaml`:

~~~yaml
app:
  delivery:
    endpoints:
      - name: primary
        url: https://primary.example.test
      - name: backup
        url: https://backup.example.test
~~~

In `application-dev.yaml`:

~~~yaml
app:
  delivery:
    endpoints:
      - name: local
        url: http://localhost:8089
~~~

When profile `dev` is active, the result is:

~~~text
endpoints:
  - name=local, url=http://localhost:8089
~~~

Not three elements.

### Partial Override of List Objects

Base source:

~~~properties
app.delivery.endpoints[0].name=primary
app.delivery.endpoints[0].url=https://primary.example.test
~~~

Higher-priority source:

~~~properties
app.delivery.endpoints[0].name=local
~~~

Under Spring Boot's complex-type binding rules, the element from the higher source carries:

~~~text
name = local
url  = null
~~~

**It does not inherit the URL from the lower source** into the higher source's List item.

Appropriate test to catch this:

~~~java
assertThat(properties.endpoints()).hasSize(1);
assertThat(properties.endpoints().get(0).name())
        .isEqualTo("local");
assertThat(properties.endpoints().get(0).url())
        .isNull();
~~~

When URL is always required, declare it completely in the higher-priority source and put `@NotBlank` on the URL field.

## 9. Maps: Check Keys and Values, Not Only Size

Example:

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        Map<String, String> headers) {
}
~~~

Properties:

~~~properties
app.gateway.headers.client=demo
app.gateway.headers.region=apac
~~~

Assertion:

~~~java
assertThat(properties.headers())
        .containsEntry("client", "demo")
        .containsEntry("region", "apac");
~~~

Checking `map.size()==2` alone is insufficient; a Map could hold two **wrong key names** and still have size 2.

### Keys with Special Characters

For Map key `/admin`:

~~~properties
app.gateway.routes[/admin]=https://admin.example.test
~~~

In YAML:

~~~yaml
app:
  gateway:
    routes:
      "[/admin]": https://admin.example.test
~~~

Square brackets instruct Binder to preserve special characters. Without brackets, Binder may strip `/` from the Map key.

Tests must assert the exact key:

~~~java
assertThat(properties.routes())
        .containsKey("/admin");
~~~

### Keys Containing Dots

For `Map<String,String>`, dotted keys may stay intact because values are scalars. For `Map<String,Object>` or structured values, dots can be interpreted as nested levels. To keep literal key `api.v2`, use brackets:

~~~yaml
app:
  gateway:
    routes:
      "[api.v2]": https://api-v2.example.test
~~~

Explicitly assert `containsKey("api.v2")`.

## 10. Map Merging Differs from List Replacement

Base source:

~~~properties
app.gateway.headers.client=demo
app.gateway.headers.region=apac
~~~

Higher-priority source:

~~~properties
app.gateway.headers.region=emea
app.gateway.headers.trace=true
~~~

When binding Maps, entries merge across sources; on matching keys/properties, the higher source wins:

~~~text
client=demo
region=emea
trace=true
~~~

Tests should assert both preserved keys and overridden keys:

~~~java
assertThat(headers)
        .containsEntry("client", "demo")
        .containsEntry("region", "emea")
        .containsEntry("trace", "true");
~~~

For `Map<String, SomePojo>`, object fields can also come from different sources per Binder rules. If every field of an entry must come from a single source, do not assume Map binding enforces that; test and enforce a dedicated policy.

**Quick comparison:**

| Type | When higher-priority source also declares it |
| --- | --- |
| `List<T>` | Typically replaces the entire list. |
| `Map<K,V>` | Merges keys and child fields; matching properties take the higher source's value. |

## 11. Nested Records: Verify the Child Object Is Created

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        String bucket,
        Retry retry) {

    public record Retry(
            Integer attempts,
            Duration backoff) {
    }
}
~~~

YAML:

~~~yaml
app:
  storage:
    bucket: demo-bucket
    retry:
      attempts: 3
      backoff: 2s
~~~

Test:

~~~java
assertThat(properties.bucket())
        .isEqualTo("demo-bucket");

assertThat(properties.retry()).isNotNull();

assertThat(properties.retry().attempts())
        .isEqualTo(3);

assertThat(properties.retry().backoff())
        .isEqualTo(Duration.ofSeconds(2));
~~~

Full key paths:

~~~text
app.storage.bucket
app.storage.retry.attempts
app.storage.retry.backoff
~~~

`app.storage` is the prefix; `retry` is the child object member; inner fields sit under the nested path.

Do not place `@ConfigurationProperties` on nested child records when they are merely members of a parent configuration properties object.

## 12. Missing Entire Nested Group vs. Missing One Field

Keep the record from the previous section, with a source containing only:

~~~properties
app.storage.bucket=demo-bucket
~~~

No keys under:

~~~text
app.storage.retry.*
~~~

With constructor binding of a nested record lacking its own default, `properties.retry()` is **null**.

Tests should encode the policy:

~~~java
assertThat(properties.retry()).isNull();
~~~

if retry is optional.

Or if retry is required, add validation blocking missing configuration. Never call:

~~~java
properties.retry().attempts();
~~~

without knowing whether retry can be null.

If only this is set:

~~~properties
app.storage.retry.attempts=3
~~~

Binder constructs `Retry`, yet `backoff` stays null because its value is missing. That is a separate case requiring its own test.

### Two Missing Levels

1. **Entire group absent:** `retry` is null.
2. **Group partially present:** `retry` is non-null, yet has a null member.

A test asserting only `retry != null` does not prove inner fields are valid.

## 13. Field-Level @DefaultValue vs. @DefaultValue on the Child Object

Spring Boot supports default values on constructor parameters or record components:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        String bucket,
        Retry retry) {

    public record Retry(
            @DefaultValue("3") int attempts,
            @DefaultValue("2s") Duration backoff) {
    }
}
~~~

If the source contains:

~~~properties
app.storage.bucket=demo
app.storage.retry.attempts=5
~~~

then nested `Retry` is created with attempts=5 and backoff=2s.

However, if **no `app.storage.retry.*` key exists at all**, defaults inside `Retry` do not force the parent's `retry` component to become non-null.

### Using Empty @DefaultValue on the Nested Member

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        String bucket,
        @DefaultValue Retry retry) {

    public record Retry(
            @DefaultValue("3") int attempts,
            @DefaultValue("2s") Duration backoff) {
    }
}
~~~

`@DefaultValue` with no arguments on `Retry retry` instructs Binder to instantiate the nested object using its defaults even when no child keys are provided, when the parent uses matching constructor binding.

Test:

~~~java
assertThat(properties.retry()).isNotNull();
assertThat(properties.retry().attempts()).isEqualTo(3);
assertThat(properties.retry().backoff())
        .isEqualTo(Duration.ofSeconds(2));
~~~

Note: a member-level default does not mean `Binder.bind("app.storage", ...)` always creates the parent object if the **entire prefix** is absent. Check completely absent targets with `BindResult` or a matching context test.

## 14. Empty Nested Mappings in YAML

Two sources look similar yet behave differently.

**A — retry omitted completely:**

~~~yaml
app:
  storage:
    bucket: demo
~~~

**B — empty retry mapping declared:**

~~~yaml
app:
  storage:
    bucket: demo
    retry: {}
~~~

Spring Boot constructor-binding docs note that an empty nested mapping can trigger binding of the child object using parameter defaults, whereas omitting the group completely leaves the nested member null.

When distinguishing A and B matters, write an integration test using real YAML because behavior depends on how Config Data passes data to Binder.

Do not force operators to write `retry: {}` just to avoid null in new designs. When the child object should always exist, an empty `@DefaultValue` on the nested member expresses intent much more clearly.

An equivalent Properties example for an empty nested object from the docs:

~~~properties
app.storage.bucket=demo
app.storage.retry=
~~~

Do not generalize that every `key=` creates an object. For String, numeric types, Maps, and Lists, empty values carry different meanings.

## 15. Mutable JavaBeans with Inline Defaults Differ from Records

Example:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {

    @Valid
    private final Eviction eviction = new Eviction();

    public Eviction getEviction() {
        return eviction;
    }

    public static class Eviction {

        @NotBlank
        private String strategy;

        @Min(1)
        private int batchSize = 10;

        public String getStrategy() {
            return strategy;
        }

        public void setStrategy(String strategy) {
            this.strategy = strategy;
        }

        public int getBatchSize() {
            return batchSize;
        }

        public void setBatchSize(int batchSize) {
            this.batchSize = batchSize;
        }
    }
}
~~~

`CacheProperties` eagerly instantiates `Eviction`, so the child object exists even without `app.cache.eviction.*` properties. Unlike a nested record with no default, it is never null.

`@Valid` on the child member enables deep validation. If `strategy` is unconfigured, `@NotBlank` causes context startup to fail.

This is an essential test whenever refactoring a JavaBean into a record: the exact same YAML can behave differently due to **different default-creation strategies**.

## 16. Missing, Empty, Blank, and YAML Null Are Four Distinct Cases

**Missing key:**

~~~properties
# No app.display-name
~~~

For String or wrapper types, the field is null when no default exists.

**Empty string:**

~~~properties
app.display-name=
~~~

For String, Binder binds `""`. This is a present-but-empty value.

**Whitespace-only string:**

~~~properties
app.display-name=   
~~~

The string has characters yet no real content per `@NotBlank`.

**YAML null:**

~~~yaml
app:
  display-name: null
~~~

This is not the String literal `"null"`. YAML flattening and conversion can treat null as absent rather than a literal String; test via the real loading path.

**Empty collection:**

~~~yaml
app:
  regions: []
  headers: {}
~~~

Do not assume every target receives `List.of()` or `Map.of()` across every binding path; test differences across YAML, Properties, field defaults, and constructor binding.

### State Matrix

| Source | Target | What to check |
| --- | --- | --- |
| Key absent | `String` | null/default |
| `name=` | `String` | empty string and validation |
| `name=   ` | `String` | whitespace-only and `@NotBlank` |
| Count absent | `Integer` | null if no default |
| Count absent | `int` | primitive default per binding |
| `count=0` | `Integer` | zero as an explicit value |
| `count=abc` | `Integer` | conversion exception |
| `regions: []` | `List<String>` | result and `@NotEmpty` |
| `retry: {}` | nested record | whether default object is created |
| Retry absent | nested record | null/default |

## 17. @NotNull, @NotEmpty, @NotBlank: Testing Exact Semantics

Jakarta Bean Validation distinguishes:

- `@NotNull`: value must not be null.
- `@NotEmpty`: not null and not empty; fits supported Strings, collections, maps, and arrays.
- `@NotBlank`: applies to CharSequence; requires at least one non-whitespace character.

| Input | @NotNull | @NotEmpty | @NotBlank |
| --- | --- | --- | --- |
| null | Fail | Fail | Fail |
| String `""` | Pass | Fail | Fail |
| String `"   "` | Pass | Pass (length > 0) | Fail |
| Empty List | Pass | Fail | Not applicable |
| One-element List | Pass | Pass | Not applicable |

Example:

~~~java
import java.util.List;
import java.util.Map;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

public record RulesProperties(
        @NotBlank String policyName,
        @NotEmpty List<String> regions,
        @NotEmpty Map<String, String> headers) {
}
~~~

Never put `@NotBlank` on a List or Map; that target type is unsupported.

### When Explicit Configuration Is Mandatory

A primitive `int attempts` can receive 0 when omitted. If constrained with `@Min(0)`, the default 0 still passes. To distinguish omitted from 0, use `Integer` + `@NotNull` or an explicit key-presence check.

## 18. @Valid: Validating Inside Lists of Objects

A List can be non-empty while containing an item missing a field:

~~~yaml
app:
  delivery:
    endpoints:
      - name: primary
        url: ""
~~~

Use Bean Validation on the elements:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record ValidatedDeliveryProperties(
        @NotEmpty List<@Valid Endpoint> endpoints) {

    public record Endpoint(
            @NotBlank String name,
            @NotBlank String url) {
    }
}
~~~

- `@NotEmpty`: List must have at least one item.
- `@Valid`: validation descends into each `Endpoint`.
- `@NotBlank`: name and url cannot be missing, empty, or whitespace.

Checking only `@NotEmpty` on the List lets an item with `url=""` slip past collection checks. Tests must verify each validation layer.

### For a Single Nested Object

~~~java
@Validated
@ConfigurationProperties(prefix = "app.connection")
public record ConnectionProperties(
        @NotNull @Valid Security security) {

    public record Security(
            @NotBlank String username,
            @NotBlank String password) {
    }
}
~~~

- `@NotNull security` forbids a missing child object.
- `@Valid security` validates fields inside Security.
- `@NotBlank` on String catches empty/blank values.

Never use `@Valid` alone to forbid null nested objects; cascading validation does not trigger on null.

## 19. ApplicationContextRunner: Testing Beans and Validation

`ApplicationContextRunner` builds a small context to test binding and startup failures without running the full system.

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class StoragePropertiesContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        ConfigurationPropertiesAutoConfiguration.class,
                        ValidationAutoConfiguration.class))
                .withUserConfiguration(TestConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(StorageProperties.class)
    static class TestConfig {
    }

    @Test
    void bindsNestedProperties() {
        runner.withPropertyValues(
                "app.storage.bucket=demo",
                "app.storage.retry.attempts=3",
                "app.storage.retry.backoff=2s")
            .run(context -> {
                assertThat(context).hasNotFailed();

                StorageProperties props =
                        context.getBean(StorageProperties.class);

                assertThat(props.retry()).isNotNull();
                assertThat(props.retry().attempts())
                        .isEqualTo(3);
                assertThat(props.retry().backoff())
                        .isEqualTo(Duration.ofSeconds(2));
            });
    }
}
~~~

`@EnableConfigurationProperties` registers the exact class under test. Do not rely on component scanning missing from the context runner and misdiagnose bean binding as broken.

### Testing Absent Nested Group

~~~java
@Test
void nestedRetryAbsentWithoutDefault() {
    runner.withPropertyValues(
            "app.storage.bucket=demo")
        .run(context -> {
            StorageProperties props =
                    context.getBean(StorageProperties.class);

            assertThat(props.retry()).isNull();
        });
}
~~~

This test matches the `StorageProperties` version without empty `@DefaultValue`. With the annotation on the nested member, expect an object populated with defaults instead.

## 20. ApplicationContextRunner with Collections and Maps

Class:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(
        List<String> labels,
        Map<String, Integer> quotas) {
}
~~~

Test:

~~~java
@Test
void bindsListAndMap() {
    runner.withPropertyValues(
            "app.catalog.labels[0]=new",
            "app.catalog.labels[1]=popular",
            "app.catalog.quotas.free=10",
            "app.catalog.quotas.premium=100")
        .run(context -> {
            assertThat(context).hasNotFailed();

            CatalogProperties props =
                    context.getBean(CatalogProperties.class);

            assertThat(props.labels())
                    .containsExactly("new", "popular");

            assertThat(props.quotas())
                    .containsEntry("free", 10)
                    .containsEntry("premium", 100);
        });
}
~~~

In a real test, `runner` must register `CatalogProperties` via:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
static class TestConfig {
}
~~~

Watch out when copying snippets: a runner registering `StorageProperties` will not create `CatalogProperties`. Match the test config to the type under test.

### Testing Absent Collections

~~~java
@Test
void absentCollectionHasNoValueInRecordWithoutDefault() {
    runner.withPropertyValues(
            "app.catalog.some-other-key=demo")
        .run(context -> {
            CatalogProperties props =
                    context.getBean(CatalogProperties.class);

            assertThat(props.labels()).isNull();
            assertThat(props.quotas()).isNull();
        });
}
~~~

With a JavaBean initialized to `new ArrayList<>()` and `new HashMap<>()`, expect empty collections instead of null. Align expectations with your class model.

## 21. Testing @NotEmpty and @NotBlank in Context

Example:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.rules")
public record RulesProperties(
        @NotBlank String policyName,
        @NotEmpty List<String> allowedRegions) {
}
~~~

Test missing List:

~~~java
@Test
void requiredListMustBeConfigured() {
    runner.withPropertyValues(
            "app.rules.policy-name=demo")
        .run(context ->
                assertThat(context).hasFailed());
}
~~~

Test blank string:

~~~java
@Test
void blankNameIsRejected() {
    runner.withPropertyValues(
            "app.rules.policy-name=   ",
            "app.rules.allowed-regions[0]=apac")
        .run(context ->
                assertThat(context).hasFailed());
}
~~~

Valid test:

~~~java
@Test
void validRulesCanBeBound() {
    runner.withPropertyValues(
            "app.rules.policy-name=demo",
            "app.rules.allowed-regions[0]=apac")
        .run(context -> {
            assertThat(context).hasNotFailed();
            RulesProperties props =
                    context.getBean(RulesProperties.class);
            assertThat(props.allowedRegions())
                    .containsExactly("apac");
        });
}
~~~

Here the runner must configure:

~~~java
@EnableConfigurationProperties(RulesProperties.class)
~~~

and include a Jakarta Validation provider. Without a provider, constraints will not run as expected.

## 22. Binder.bind and BindResult: Testing "No Data"

You can test at the pure Binder level:

~~~java
import java.util.Map;

import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

Binder binder = new Binder(
        new MapConfigurationPropertySource(Map.of()));

BindResult<String> result =
        binder.bind("app.title", String.class);

assertThat(result.isBound()).isFalse();

String title = result.orElse("Untitled");

assertThat(title).isEqualTo("Untitled");
~~~

Values `false` and `0` are still **bound**:

~~~properties
app.enabled=false
app.retry-count=0
~~~

Test:

~~~java
assertThat(
        binder.bind("app.enabled", Boolean.class).get())
        .isFalse();

assertThat(
        binder.bind("app.retry-count", Integer.class).get())
        .isZero();
~~~

### Do Not Confuse Conversion Errors with Absent Keys

~~~properties
app.retry-count=abc
~~~

Binder cannot convert to `Integer`. The call throws `BindException` before `orElse(3)` ever supplies a fallback.

A thorough test covers three branches:

1. No `app.retry-count` -> unbound.
2. `app.retry-count=0` -> bound and equal to 0.
3. `app.retry-count=abc` -> binding failure.

## 23. Partially Bound Objects and orElseGet Limits

~~~java
public record ConnectionOptions(
        String host,
        Integer port,
        Duration timeout) {
}
~~~

Source has only:

~~~properties
app.connection.host=api.example.test
~~~

Binder constructs `ConnectionOptions` with host populated, and port/timeout null.

~~~java
BindResult<ConnectionOptions> result =
        binder.bind("app.connection", ConnectionOptions.class);
~~~

Because `result.isBound()` is true, this code:

~~~java
ConnectionOptions options = result.orElseGet(() ->
        new ConnectionOptions(
                "localhost", 8080, Duration.ofSeconds(5)));
~~~

**does not fill in** defaults for port and timeout. `orElseGet` is only a fallback when the **entire result is unbound**.

For per-field defaults:

- Use `@DefaultValue` with constructor binding.
- Use field initializers with mutable JavaBeans.
- Or apply explicit post-binding merge logic.

To require all fields, use `@NotNull`/`@NotBlank` and validation. Never treat `isBound()==true` as proof the object is complete.

## 24. Testing List Replacement and Map Merging Across Sources

You can simulate two prioritized `ConfigurationPropertySource` instances.

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

var highPriority =
        new MapConfigurationPropertySource(Map.of(
                "app.regions[0]", "local"));

var lowPriority =
        new MapConfigurationPropertySource(Map.of(
                "app.regions[0]", "apac",
                "app.regions[1]", "emea"));

Binder binder = new Binder(
        List.of(highPriority, lowPriority));

List<String> result =
        binder.bind(
                "app.regions",
                Bindable.listOf(String.class))
              .get();

assertThat(result).containsExactly("local");
~~~

This proves the higher-priority List replaces the lower List instead of appending elements.

### Map Test

Lower source:

~~~text
app.headers.client=demo
app.headers.region=apac
~~~

Higher source:

~~~text
app.headers.region=emea
~~~

For target `Map<String,String>`, expect:

~~~text
client=demo
region=emea
~~~

When creating Binder in tests, pass sources in the **exact priority order you intend to simulate**. Reversing them changes the test outcome without indicating a library bug.

## 25. Testing Profiles with @SpringBootTest and @ActiveProfiles

To test real Config Data files, create:

~~~yaml
# application.yaml
app:
  delivery:
    regions: [apac, emea]
~~~

~~~yaml
# application-dev.yaml
app:
  delivery:
    regions: [local]
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("dev")
class DeliveryProfileTest {

    @Autowired
    DeliveryProperties properties;

    @Test
    void devListReplacesBaseList() {
        assertThat(properties.regions())
                .containsExactly("local");
    }
}
~~~

`DeliveryProperties` must be registered in the test application. Unlike a Binder unit test, this tests loading `application-dev.yaml` and the outcome when the profile is active.

### Never Let Test Properties Mask Broken Files

If a file contains:

~~~properties
app.worker.threads=abc
~~~

and the test overrides:

~~~java
@SpringBootTest(properties = "app.worker.threads=4")
~~~

the test passes because the higher-priority test source overrides the bad value. Never cite that as proof the underlying YAML/Properties file is valid.

When verifying the file itself, avoid putting `@TestPropertySource` or `@SpringBootTest(properties=...)` on keys under test.

## 26. Environment Variables for List Indices

Canonical name:

~~~text
app.delivery.endpoints[0].url
~~~

Environment form supported by Spring Boot:

~~~text
APP_DELIVERY_ENDPOINTS_0_URL
~~~

Index `0` is wrapped in underscores.

However, a plain `MapConfigurationPropertySource` in a unit test **does not share naming rules with system environment sources**. To test real Kubernetes or Docker setups:

- Supply the corresponding environment variable in the test process or launcher environment.
- Or use an appropriate `SystemEnvironmentPropertySource`.
- Verify after Spring Boot constructs `Environment`.
- Never use real credentials in tests.

Keep **testing Binder with canonical keys** distinct from **testing runtime environment-variable-to-canonical mapping**.

## 27. Missing-Config Tests Should Not Use Unsafe Defaults

An optional display setting like `app.display-name` can default to `"Untitled"`. A payment URL or secret key should never silently fall back to a fake default and keep running in production.

Example:

~~~java
@Validated
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        @NotBlank String endpoint,
        @NotBlank String clientSecret) {
}
~~~

Minimal tests:

1. Missing endpoint -> context fails.
2. Blank endpoint -> context fails.
3. Missing client secret -> context fails.
4. Whitespace-only secret -> context fails.
5. Valid dummy values -> context starts.

In fixtures use `DEMO_ONLY_NOT_A_REAL_SECRET`. Never print the record or `Environment` in tests because `record.toString()` can expose secrets.

## 28. When Should You Create a Class-Level Custom Validator?

Some rules cannot be expressed on a single field alone.

For example, when `tls.enabled=true`, `tls.certificate-path` is required, whereas when TLS is off, it may be omitted.

Use a custom class-level Jakarta `@Constraint` with a `ConstraintValidator` to enforce cross-field rules.

Test matrix:

| enabled | certificate-path | Expected |
| --- | --- | --- |
| false | missing | Pass if policy permits |
| true | missing | Fail |
| true | blank | Fail |
| true | syntactically valid path | Pass config validation |

This verifies **configuration validity** only. It does not prove the certificate file exists on disk or that the TLS library can parse it, unless an integration test also tests the system layer.

## 29. Test Case Tables by Data Type

### List

| Case | Input | Expected |
| --- | --- | --- |
| Single item | `[apac]` | size=1 |
| Multiple items | `[apac,emea]` | exact order |
| Missing | key absent | null/default per design |
| Empty | `[]` | verify result and `@NotEmpty` |
| Item missing URL | name only | fails if nested validation exists |
| Overridden by profile | base 2, dev 1 | List has 1 item from dev |

### Map

| Case | Input | Expected |
| --- | --- | --- |
| Single key | region=apac | entry present |
| Special key | `[/admin]` | preserves `/` |
| Dotted key | `[api.v2]` | preserves literal key |
| Higher source swaps one key | region=emea | preserves non-overridden keys |
| Empty map | `{}` | matches policy |

### Nested Object

| Case | Input | Expected |
| --- | --- | --- |
| All fields | retry.attempts and retry.backoff | valid object |
| Entire retry absent | no retry | null/default/fail per design |
| Empty mapping | retry: {} | verify constructor defaults |
| One field absent | attempts set, backoff missing | default or validation |
| Wrong type | backoff=bad | conversion failure |

### Empty and Missing Scalars

| Case | Input | Expected |
| --- | --- | --- |
| String absent | missing | null/default |
| Empty string | name= | fails if `@NotBlank` |
| Whitespace | name=   | fails if `@NotBlank` |
| Boolean false | enabled=false | value is false |
| Integer 0 | count=0 | value is 0 |
| Invalid Integer | count=abc | conversion error |

## 30. Common Testing Mistakes

### Mistake 1 — Checking Only Bean Existence

~~~java
assertThat(context)
        .hasSingleBean(DeliveryProperties.class);
~~~

Insufficient; the bean might have an empty List, null nested objects, or wrong values. Assert members against the contract.

### Mistake 2 — Assuming Lists Merge

Profile defines one item while tests expect the two base items to remain. Spring Boot's default List behavior is replacement.

### Mistake 3 — Assuming Maps Replace Everything

Maps merge keys across sources, with higher-priority sources winning per property.

### Mistake 4 — Checking Only Map Size

Having the right key count does not guarantee literal key names—especially with `/` and dots.

### Mistake 5 — Confusing Missing Group with Missing Field

A null nested object differs from an existing nested object with null members.

### Mistake 6 — Using @NotNull Instead of @NotEmpty on Required Non-Empty Lists

An empty List is non-null; `@NotNull` allows an empty List.

### Mistake 7 — Putting @NotBlank on Collections

`@NotBlank` applies to String/CharSequence, not Lists or Maps.

### Mistake 8 — Missing @Valid on Child Objects

Validation does not descend into nested members without cascading validation.

### Mistake 9 — Assuming Field-Level @DefaultValue Creates the Whole Group

Defaults on child fields do not make parent or nested objects appear when the entire prefix is absent.

### Mistake 10 — Treating Empty Strings as Missing Keys

`app.name=` binds an empty String and requires explicit validation.

### Mistake 11 — Treating Boolean false or Integer 0 as Unbound

Those are explicit configured values, not absent values.

### Mistake 12 — Letting Fallbacks Hide Conversion Errors

`orElse(...)` should not silently replace `retry-count=abc` with a default; Binder throws an exception.

### Mistake 13 — Test Overrides Masking Broken YAML

A higher-priority `@SpringBootTest(properties=...)` can hide broken config files.

### Mistake 14 — Forgetting Class Registration in ApplicationContextRunner

Use `@EnableConfigurationProperties(Target.class)` or equivalent so Binder creates the bean.

### Mistake 15 — Testing Validation Without a Provider

`@Validated` and constraints do nothing without a compatible Jakarta Bean Validation provider.

### Mistake 16 — Order-Dependent or Shared-State Tests

Test A mutates a shared Map and Test B reuses it. Build fresh contexts and property sources per test.

### Mistake 17 — Comparing Collection toString Output

`toString()` is not a binding contract. Assert elements directly.

### Mistake 18 — Printing Secrets in Test Logs

Never log full properties records containing API tokens/passwords or dump `Environment`.

## 31. Practice Exercises with Answers

### Exercise 1 — Ordered List

Source:

~~~properties
app.regions[0]=apac
app.regions[1]=emea
~~~

**Answer:** List has two items in order. Assert with `containsExactly("apac","emea")`.

### Exercise 2 — Profile Overriding a List

Base regions=[apac,emea]; dev regions=[local].

**Answer:** when dev has higher priority, List becomes `local`, not three concatenated items.

### Exercise 3 — Map Merging

Base headers.client=demo, headers.region=apac. Higher source headers.region=emea.

**Answer:** client=demo remains, region=emea wins.

### Exercise 4 — Map Key with /

Source:

~~~properties
app.routes[/admin]=https://admin.example.test
~~~

**Answer:** use bracket notation and assert `containsKey("/admin")`.

### Exercise 5 — Nested Record Missing Entire Group

Record has `Retry retry`, yet only `app.storage.bucket` is set.

**Answer:** retry becomes null unless a nested-member default exists; test and handle explicitly.

### Exercise 6 — Nested Record with Empty Default

`@DefaultValue Retry retry` and Retry has `@DefaultValue("3") int attempts`.

**Answer:** when the parent binds, nested Retry instantiates with attempts=3 even without retry keys.

### Exercise 7 — Empty String

~~~properties
app.name=
~~~

**Answer:** binds `""` for String; `@NotBlank` rejects it.

### Exercise 8 — Whitespace String

~~~properties
app.name=   
~~~

**Answer:** `@NotBlank` rejects it, `@NotNull` alone allows it.

### Exercise 9 — int vs. Integer

`app.retry-count` is absent.

**Answer:** `int` may receive 0, `Integer` becomes null. To catch absence explicitly, use wrapper + `@NotNull`.

### Exercise 10 — List Item Missing a Field

~~~yaml
app:
  endpoints:
    - name: primary
~~~

**Answer:** assert item URLs. With `List<@Valid Endpoint>` and `@NotBlank url`, validation rejects it.

### Exercise 11 — Empty List and @NotEmpty

Source has `allowed-regions: []`.

**Answer:** `@NotEmpty` rejects an empty List; `@NotNull` is insufficient.

### Exercise 12 — Unconvertible Data

`count=abc` targeting Integer.

**Answer:** conversion failure, not missing key.

### Exercise 13 — Testing Profile Context

Verify `application-dev.yaml` overrides `application.yaml`.

**Answer:** use an integration test with `@ActiveProfiles("dev")` or equivalent startup.

### Exercise 14 — List Index in Environment

Canonical name `app.delivery.endpoints[0].url`.

**Answer:** `APP_DELIVERY_ENDPOINTS_0_URL` is the Spring Boot environment variable form.

### Exercise 15 — Test Override Masking Errors

File has `app.worker.threads=abc`, test adds `@SpringBootTest(properties="app.worker.threads=4")`.

**Answer:** the test passes due to the test override, which does not validate the underlying file.

## 32. Complete Test Suite Checklist

**Collections:** test single/multiple elements, ordering, empty, missing keys, invalid elements, Map special keys, List replacement, and Map merging.

**Nested objects:** test all fields present, entire group absent, empty mapping, one field absent, member-level vs. object-level defaults, and proper `@Valid`/`@NotNull` placement.

**Scalars:** test missing, empty string, whitespace, null, false, 0, wrong types, and overrides.

**Spring Boot:** register beans properly, include validation provider in context tests, use real profiles/files where needed, never mask file bugs with test overrides, avoid shared state, and never print secrets.

## 33. Conclusion

Testing `@ConfigurationProperties` should never stop at one happy-path YAML file. You must verify how each data shape behaves when values are **complete, missing, empty, malformed, or overridden by another source**.

Core principles:

1. `List`s across sources are generally **replaced wholesale**, not concatenated.
2. `Map`s **merge keys** across sources; colliding keys resolve by precedence.
3. Nested records become **null** when their group is absent; an empty `@DefaultValue` on the nested member requests instantiation with defaults.
4. Empty strings, whitespace-only strings, empty Lists, empty mappings, and missing keys are **not identical**.
5. `@NotNull`, `@NotEmpty`, `@NotBlank`, and `@Valid` serve distinct purposes.
6. `BindResult.isBound()` does not prove all fields are populated or validated.
7. `Binder` suits unit tests; `ApplicationContextRunner` suits bean/binding/validation tests; `@SpringBootTest` suits real files and profiles.

A test suite with a clear boundary matrix catches broken configuration long before `NullPointerException`s, surprising overrides, or production outages happen.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot — Binder API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Binder.html).
- [Spring Boot — BindResult API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/BindResult.html).
- [Spring Boot — ApplicationContextRunner API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
- [Jakarta Bean Validation specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0).
- [Spring Framework — TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html).
