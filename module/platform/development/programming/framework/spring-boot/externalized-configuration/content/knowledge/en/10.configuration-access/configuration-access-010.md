# Replacing Scattered @Value Annotations with a Structured Configuration Object

In a Spring Boot application, a simple way to read configuration is `@Value("${...}")`. When there are only one or two values, this approach is very convenient. However, when a feature has many parameters such as URLs, timeouts, retries, lists of active regions, and toggle flags, placing `@Value` across multiple beans **scatters configuration**, makes it hard to tell what the application actually requires, and makes validating the entire property group difficult.

Spring Boot solves this with `@ConfigurationProperties`: grouping properties sharing a common prefix into **one Java object with explicit data types**, supporting nested structures, type conversion, defaults, validation, and constructor injection.

This lesson walks through migrating from scattered `@Value` annotations to a cohesive configuration structure using Spring Boot 3.3.x and Java 21. The main examples use `record` to emphasize that configuration is initialized once and consumed as read-only data.

## 1. The problem with many `@Value` annotations

Suppose a system has a feature that calls a delivery service. Initially one bean reads the endpoint and timeout:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DeliveryClient {

    @Value("${app.delivery.endpoint}")
    private URI endpoint;

    @Value("${app.delivery.connect-timeout:4s}")
    private Duration connectTimeout;

    // Uses endpoint and connectTimeout to call the external system.
}
~~~

Another bean manages retries:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DeliveryRetryPolicy {

    @Value("${app.delivery.retry.max-attempts:3}")
    private int maxAttempts;

    @Value("${app.delivery.retry.backoff:250ms}")
    private java.time.Duration backoff;
}
~~~

A third bean handles a feature flag:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DeliveryFeatureSwitch {

    @Value("${app.delivery.enabled:true}")
    private boolean enabled;
}
~~~

All five values belong to one business domain, yet developers have to read multiple classes to see the entire configuration. Several consequences follow:

- There is no single Java type describing the **configuration contract** of the delivery feature.
- Defaults `4s`, `3`, `250ms`, and `true` sit in annotations across different files, making them hard to cross-check against configuration files.
- When adding validation, each bean risks validating data in its own way.
- Properties in the same group may drift into inconsistent names like `retry.count` in one place and `retry.max-attempts` in another.
- Tests constructing multiple beans must supply individual placeholders rather than instantiating a well-defined data object.
- Field injection makes reading constructor dependencies and instantiating objects in unit tests harder.

`@Value` is not a wrong API. The problem lies in **using too many independent injections for a group of parameters that belong to a single concept**.

## 2. Desired outcome: one grouped configuration

Suppose `src/main/resources/application.yml` is organized as follows:

~~~yaml
app:
  delivery:
    endpoint: https://delivery.example.org/api
    enabled: true
    connect-timeout: 4s

    retry:
      max-attempts: 3
      backoff: 250ms

    allowed-regions:
      - vn
      - sg
~~~

These properties have a clear structure:

~~~text
app.delivery
├── endpoint            → URI
├── enabled             → boolean
├── connect-timeout     → Duration
├── retry
│   ├── max-attempts    → int
│   └── backoff         → Duration
└── allowed-regions     → List<String>
~~~

Instead of injecting six values into multiple fields, one `DeliveryProperties` object holds the entire `app.delivery` group's configuration. Other services simply depend on that object.

Design target:

~~~text
application.yml / environment variables / CLI
                    ↓
       Spring Boot Configuration Binder
                    ↓
             DeliveryProperties
                    ↓
       DeliveryClient / RetryPolicy / Service
~~~

The Binder reads configuration from `Environment` following active precedence rules; the `DeliveryProperties` class defines the structure and data types expected by source code.

## 3. Creating a configuration class with `@ConfigurationProperties` and a Java record

Create `src/main/java/com/example/delivery/config/DeliveryProperties.java`:

~~~java
package com.example.delivery.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        URI endpoint,
        boolean enabled,
        Duration connectTimeout,
        Retry retry,
        List<String> allowedRegions) {

    public record Retry(
            int maxAttempts,
            Duration backoff) {
    }
}
~~~

Explanation:

- `@ConfigurationProperties(prefix = "app.delivery")` instructs Spring Boot to bind child properties of `app.delivery`.
- `endpoint` receives `app.delivery.endpoint` and converts to `java.net.URI`.
- `enabled` receives boolean `true` or `false`.
- `connectTimeout` receives values like `4s` and converts to `java.time.Duration`.
- `retry` is a nested record grouping `maxAttempts` and `backoff`.
- `allowedRegions` receives elements from the YAML list into `List<String>`.

Spring Boot 3.x supports constructor binding for classes with a single parameter constructor or suitable records. For the record in this example, **there is no need to place `@ConstructorBinding` on the record** and no need to write setters.

Java records fit post-startup read-only configuration groups because:

- Components are explicitly declared in the record's signature.
- The object provides accessors `endpoint()`, `enabled()`, `retry()`, and `allowedRegions()`.
- Record components have no setters; data is supplied when the object is instantiated.
- Service dependencies can be passed through constructors.

Records do not guarantee deep immutability of every component: for example, `List<String>` could be a mutable collection if a mutable reference is retained. Treat configuration as read-only data and avoid mutating collections after binding; if deep immutability is needed, make defensive copies in your design logic.

## 4. Registering the configuration object with Spring Boot

Putting `@ConfigurationProperties` on a class **does not automatically** make that class a Spring bean. A common choice is enabling scanning on the startup class.

~~~java
package com.example.delivery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DeliveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeliveryApplication.class, args);
    }
}
~~~

In package `com.example.delivery`, `@ConfigurationPropertiesScan` discovers configuration classes beneath that package, including `com.example.delivery.config.DeliveryProperties`.

Another registration approach:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(DeliveryProperties.class)
public class DeliveryApplication {
    // ...
}
~~~

The second approach is useful when you want to **explicitly specify which configuration types** are registered without scanning. In this example, pick one of the two registration approaches; do not apply both simultaneously to the same class.

### Do not add `@Component` to a constructor-bound record

Avoid writing:

~~~java
@Component
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(URI endpoint, Duration connectTimeout) {
}
~~~

Constructor-bound configuration must be registered by Spring Boot via an appropriate configuration-properties mechanism (`@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`), rather than letting Spring create it as a regular `@Component` bean and attempting to autowire constructor parameters from other beans. For setter-based JavaBean classes, Spring Boot supports some other registration patterns, yet you should not mix them arbitrarily with record constructor binding.

## 5. Injecting the configuration object into services

Instead of reading placeholders directly, services receive a typed dependency:

~~~java
package com.example.delivery.service;

import com.example.delivery.config.DeliveryProperties;
import org.springframework.stereotype.Service;

@Service
public class DeliveryService {

    private final DeliveryProperties settings;

    public DeliveryService(DeliveryProperties settings) {
        this.settings = settings;
    }

    public String describeConnection() {
        return "Endpoint=" + settings.endpoint()
                + ", timeout=" + settings.connectTimeout()
                + ", retry=" + settings.retry().maxAttempts();
    }

    public boolean supportsRegion(String region) {
        return settings.allowedRegions().contains(region);
    }
}
~~~

Here:

- No need to add `@Value` to `DeliveryService`.
- The service constructor clearly states it depends on `DeliveryProperties`.
- Logic reads via `settings.endpoint()` or `settings.retry().backoff()`, instead of repeating string paths like `app.delivery.retry.backoff`.
- When renaming a configuration key, you only update the binding in one place and related typed-property call sites, rather than searching for string annotations.

Another bean uses the same object without duplicating configuration:

~~~java
package com.example.delivery.service;

import com.example.delivery.config.DeliveryProperties;
import org.springframework.stereotype.Component;

@Component
public class DeliveryRetryPolicy {

    private final DeliveryProperties settings;

    public DeliveryRetryPolicy(DeliveryProperties settings) {
        this.settings = settings;
    }

    public int maxAttempts() {
        return settings.retry().maxAttempts();
    }

    public java.time.Duration backoff() {
        return settings.retry().backoff();
    }
}
~~~

You can further split interfaces or business classes as needed, yet the **parameter source** is now consolidated into a single shared object. There is no need to make every bean in the application depend on one giant class; each functional group should have its own prefix and configuration class.

## 6. How Spring Boot maps YAML names to Java

Spring Boot uses *relaxed binding*. Property names in configuration are normally written in canonical lowercase hyphenated form (*kebab-case*), while Java components use camelCase.

| In YAML | In Java |
| --- | --- |
| `app.delivery.endpoint` | `DeliveryProperties.endpoint()` |
| `app.delivery.enabled` | `DeliveryProperties.enabled()` |
| `app.delivery.connect-timeout` | `DeliveryProperties.connectTimeout()` |
| `app.delivery.retry.max-attempts` | `DeliveryProperties.retry().maxAttempts()` |
| `app.delivery.retry.backoff` | `DeliveryProperties.retry().backoff()` |
| `app.delivery.allowed-regions` | `DeliveryProperties.allowedRegions()` |

You do not need to rewrite YAML keys into Java names like `connectTimeout`. Keep canonical format in YAML and properties for consistency with other configuration sources.

Commonly bindable data types:

- `boolean`: `true`, `false`.
- `int`, `long`: integers within range.
- `URI`: addresses such as `https://delivery.example.org/api`.
- `Duration`: `250ms`, `4s`, `2m`, `1h`.
- `DataSize`: strings with size units, e.g. `10MB`, when the field uses `org.springframework.util.unit.DataSize`.
- `List<String>` or `List<SomeRecord>`: YAML sequences.
- `Map<String, String>`: key–value pairs under a mapping.
- Enum: configuration strings converted to the corresponding enum per the Binder's conversion rules.

### Corresponding environment variable names

When running in a deployment environment:

~~~bash
export APP_DELIVERY_ENDPOINT="https://delivery.example.org/api"
export APP_DELIVERY_CONNECTTIMEOUT="7s"
export APP_DELIVERY_RETRY_MAXATTEMPTS="5"
java -jar delivery-app.jar
~~~

The values bind to `endpoint`, `connectTimeout`, and `retry.maxAttempts`. When converting canonical property names to environment variables, dots `.` become `_`, hyphens `-` inside property names are removed, and the name is uppercased.

Writing `APP_DELIVERY_CONNECT_TIMEOUT` with an extra underscore inside a component is not the recommended canonical conversion for `connect-timeout`; use `APP_DELIVERY_CONNECTTIMEOUT`. Similarly, `max-attempts` becomes `MAXATTEMPTS`, not automatically `MAX_ATTEMPTS`.

### Mapping lists

Example:

~~~yaml
app:
  delivery:
    allowed-regions:
      - vn
      - sg
      - th
~~~

Binding populates `List<String>` in order. To provide a list via environment variables, list indices are represented in names, such as `APP_DELIVERY_ALLOWEDREGIONS_0_=vn` and `APP_DELIVERY_ALLOWEDREGIONS_1_=sg`, following environment rules for list indices. For large lists, YAML files are usually much easier to read.

## 7. Validation: turning bad configuration into clear startup errors

Switching to typed configuration **does not automatically guarantee** every value is valid. For example, if `endpoint` is absent, the constructor could receive `null`; if `maxAttempts` is 0, that is still a valid integer yet invalid for business rules.

Use Bean Validation with `@Validated`, `@NotNull`, `@Min`, `@NotBlank`, etc., to establish a clearer contract.

In a Spring Boot project, typically add the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

If using a Gradle Version Catalog or project-managed BOM, adjust the declaration to match the current build; the artifact providing Bean Validation support must be present.

Example record with validation:

~~~java
package com.example.delivery.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        @NotNull URI endpoint,
        boolean enabled,
        @NotNull Duration connectTimeout,
        @Valid @NotNull Retry retry,
        List<String> allowedRegions) {

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff) {
    }
}
~~~

The annotations serve different purposes:

- `@Validated` enables validation on the configuration properties bean when the Binder creates the object.
- `@NotNull` requires critical components to have values.
- `@Min(1)` prevents retry counts below 1.
- `@Valid` cascades constraint checks into the nested `Retry` object.

If `app.delivery.retry` is missing, `@NotNull` on `retry` helps detect the error. If the retry object exists with `max-attempts=0`, `@Min(1)` reports an error.

For required strings with content, use `@NotBlank String name` instead of only `@NotNull`. For URLs, `@NotNull URI` checks object presence; if business rules require an `https` scheme and valid host, add appropriate validation for that rule.

When binding fails, Spring Boot can report details such as the prefix, property, input value, type conversion error, or violated constraint. Instead of failing deep inside service execution, the error can surface when creating the configuration properties bean.

## 8. Where should default values live?

Old `@Value` sites often had defaults in placeholders:

~~~java
@Value("${app.delivery.connect-timeout:4s}")
private Duration connectTimeout;

@Value("${app.delivery.retry.max-attempts:3}")
private int maxAttempts;
~~~

When migrating to `@ConfigurationProperties`, **migrate the intent of the defaults as well**, not just the key names.

There are three common approaches.

### 8.1. Declaring defaults in `application.yml`

~~~yaml
app:
  delivery:
    connect-timeout: 4s
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

This is intuitive when defaults are configuration decisions that may vary by environment. With validated classes and required keys, files or other sources must supply complete data.

### 8.2. Using `@DefaultValue` in constructor binding

Spring Boot supports `org.springframework.boot.context.properties.bind.DefaultValue` on constructor-bound parameters, including record components:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("500ms") Duration backoff,
        @DefaultValue("true") boolean enabled) {
}
~~~

When the corresponding keys are absent, the Binder uses the declared defaults. Present values from `Environment` take precedence and undergo standard type conversion.

This ties defaults directly to the Java contract. When applying it, ensure defaults are genuinely safe across every environment, especially for security-related properties.

### 8.3. JavaBean configuration with field initializers

Another option is a mutable class with fields and setters:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {

    private int maxAttempts = 3;
    private Duration backoff = Duration.ofMillis(500);

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public Duration getBackoff() {
        return backoff;
    }

    public void setBackoff(Duration backoff) {
        this.backoff = backoff;
    }
}
~~~

Bean-style binding helps older Java codebases migrate incrementally, while records are usually cleaner when object mutation after binding is not needed.

**Avoid accidentally creating multiple conflicting default sources** such as `4s` in an old annotation, `5s` in YAML, and `6s` in a constructor. During refactoring, decide which source of defaults is intentional and update remaining call sites accordingly.

## 9. Step-by-step refactoring while preserving behavior

A safe migration pays attention to **effective values**, bean structure, and missing-configuration cases. Practical workflow:

### Step 1 — Inventory keys belonging to the same feature

Example findings:

~~~text
DeliveryClient
  app.delivery.endpoint
  app.delivery.connect-timeout

DeliveryRetryPolicy
  app.delivery.retry.max-attempts
  app.delivery.retry.backoff

DeliveryFeatureSwitch
  app.delivery.enabled

RegionFilter
  app.delivery.allowed-regions
~~~

Group everything under prefix `app.delivery`. Note the data types, defaults, and validation rules existing beans apply. If a key belongs to another feature, do not force it into `DeliveryProperties` just because it also starts with `app`.

### Step 2 — Define a typed configuration class

Create `DeliveryProperties` as in section 3. Use a nested record for `retry`, `List<String>` for lists, `Duration` for timeouts, and `URI` for endpoints.

### Step 3 — Consolidate defaults and shared values into the chosen source

If defaults stay in the configuration file:

~~~yaml
app:
  delivery:
    enabled: true
    connect-timeout: 4s
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

Mandatory values such as endpoints are supplied in the appropriate place for each environment; avoid leaving a sample production endpoint as an operational default.

### Step 4 — Register the `@ConfigurationProperties` bean

Add `@ConfigurationPropertiesScan` on the application class, or `@EnableConfigurationProperties(DeliveryProperties.class)` in configuration. This enables services to inject the object via constructor.

### Step 5 — Migrate each call site

Before:

~~~java
@Value("${app.delivery.retry.max-attempts:3}")
private int attempts;
~~~

After:

~~~java
private final DeliveryProperties properties;

public DeliveryRetryPolicy(DeliveryProperties properties) {
    this.properties = properties;
}

public int attempts() {
    return properties.retry().maxAttempts();
}
~~~

During migration, other beans can temporarily keep using `@Value`. You do not have to switch every class in one commit if the scope is large; simply avoid keeping two conflicting configuration sources for the same value.

### Step 6 — Remove old read paths once migration is complete

Once all consumers in the scope receive `DeliveryProperties`, delete the corresponding `@Value` fields. If previous business logic had custom conversions or fallbacks, move them deliberately into the typed configuration or appropriate service.

Do not leave an old `@Value` "just in case" in a bean if it could trigger unnecessary missing-placeholder errors or mislead maintainers into thinking two independent configuration mechanisms still exist.

## 10. Profile-based configuration and source precedence still work

`@ConfigurationProperties` does not invent a new precedence order. It binds from the `Environment` that Spring Boot has constructed. Therefore, moving from `@Value` to a typed object does not disable:

- `application.yml` and profile files like `application-prod.yml`.
- Files loaded via `spring.config.import`.
- Environment variables.
- Java system properties.
- Command-line arguments.

Shared file example:

~~~yaml
app:
  delivery:
    endpoint: https://sandbox.delivery.example.org/api
    connect-timeout: 4s
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

File `application-prod.yml`:

~~~yaml
app:
  delivery:
    endpoint: https://delivery.example.org/api
    connect-timeout: 2s
~~~

Run:

~~~bash
java -jar delivery-app.jar --spring.profiles.active=prod
~~~

In the example, `DeliveryProperties.endpoint()` receives the production endpoint and `connectTimeout()` receives `2s`. With no higher-precedence source, `retry.maxAttempts()` remains `3` and `retry.backoff()` remains `250ms` from the shared file.

You can override retry alone via CLI:

~~~bash
java -jar delivery-app.jar --spring.profiles.active=prod --app.delivery.retry.max-attempts=5
~~~

The Binder receives `5` for `maxAttempts`. The Java class needs no changes.

### Lists and multi-source configuration

For lists like `allowed-regions`, remember that Spring Boot normally **replaces the whole list** with the value from a higher-precedence source; it does not simply append elements to the old list. For example, if the prod file provides `allowed-regions: [vn]`, the final list does not retain `sg` from the shared file.

For Maps and nested configuration objects, merging and override rules can differ from lists. When refactoring a complex structured property group, verify the expected behavior for each data type.

## 11. Testing configuration after refactoring

One benefit of typed objects is that tests can assert on **bound configuration** instead of checking individual placeholder strings.

Spring Boot Test example:

~~~java
package com.example.delivery;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import com.example.delivery.config.DeliveryProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.delivery.endpoint=https://test.delivery.example.org",
        "app.delivery.enabled=true",
        "app.delivery.connect-timeout=6s",
        "app.delivery.retry.max-attempts=4",
        "app.delivery.retry.backoff=200ms",
        "app.delivery.allowed-regions[0]=vn",
        "app.delivery.allowed-regions[1]=sg"
})
class DeliveryPropertiesTest {

    @Autowired
    private DeliveryProperties properties;

    @Test
    void bindsStructuredProperties() {
        assertThat(properties.endpoint()).isEqualTo(
                URI.create("https://test.delivery.example.org"));

        assertThat(properties.connectTimeout()).isEqualTo(
                Duration.ofSeconds(6));

        assertThat(properties.retry().maxAttempts()).isEqualTo(4);
        assertThat(properties.retry().backoff()).isEqualTo(
                Duration.ofMillis(200));

        assertThat(properties.allowedRegions())
                .containsExactly("vn", "sg");
    }
}
~~~

This sample assumes the project has `spring-boot-starter-test` and a discoverable `@SpringBootApplication` class. Test properties are fed directly into the test context's `Environment`, letting you test the binder, nested objects, and type conversion.

### Testing validation

Try setting `app.delivery.retry.max-attempts=0` when `@Min(1)` is active. Creating the configuration bean should fail due to this constraint. Likewise, omitting a required endpoint or passing an unparseable `Duration` should be caught during startup.

For plain Java unit tests of business logic, there is no need to start a Spring context. You can instantiate the configuration record directly:

~~~java
DeliveryProperties settings = new DeliveryProperties(
        URI.create("https://mock.example.org"),
        true,
        Duration.ofSeconds(2),
        new DeliveryProperties.Retry(
                2, Duration.ofMillis(100)),
        java.util.List.of("vn")
);

DeliveryService service = new DeliveryService(settings);
~~~

Such tests verify how the service uses the configuration object without depending on YAML files or the environment. With validation annotations, keep in mind that instantiating a record directly **does not invoke Bean Validation automatically**; validation must be triggered separately if a test needs to verify constraints.

## 12. Differences between `@Value` and `@ConfigurationProperties`

| Criterion | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- |
| Purpose | Read a single value/expression at one injection point | Bind a group of properties into a structured object |
| Naming | Direct placeholder, usually a string | Prefix + field/record components, using relaxed binding |
| Nested objects | Must access individually or assemble manually | Cleanly binds nested classes/records |
| Lists and Maps | May require special declarations/conversions per case | Binder supports structured collections and Maps |
| Type conversion | Supports conversion at injection point | Consistent type conversion across fields |
| Validation | Usually handled separately in each bean | Supports `@Validated` and Bean Validation across the whole object |
| Defaults | `${key:fallback}` | Config files, `@DefaultValue`, JavaBean defaults |
| SpEL | Supports Spring Expression Language inside `@Value` | Not designed to evaluate SpEL inside config values |
| Discoverability | Must inspect each bean | Inspect one class to see what the config group requires |

### Cases where `@Value` still makes sense

- Reading a single standalone property not belonging to a cohesive group.
- Evaluating an intentional SpEL expression that does not fit normal configuration binding.
- A tiny internal bean with no need to reuse a configuration object.

Migrating to `@ConfigurationProperties` does not mean banning `@Value` altogether. Choose the tool suited to the **complexity and domain boundaries** of the configuration.

## 13. Common mistakes during refactoring

### 13.1. Forgetting to register the configuration-properties bean

You created:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(URI endpoint) {
}
~~~

Without adding `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, services injecting `DeliveryProperties` can fail with "No qualifying bean".

**Fix:** register the class with an appropriate configuration-properties mechanism.

### 13.2. Mismatched prefix

YAML:

~~~yaml
app:
  delivery:
    endpoint: https://delivery.example.org
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.deliveries")
~~~

Prefix `app.deliveries` does not match `app.delivery`. The Binder fails to find expected keys. With records and validation, this can raise missing required field errors; without validation, the app risks receiving `null` or primitive defaults.

**Fix:** use a canonical prefix, keeping paths consistent across YAML, properties, CLI, and classes.

### 13.3. Moving to a record while leaving old defaults only in annotations

If you previously used `@Value("${app.delivery.connect-timeout:4s}")`, removing `@Value` without supplying the value in files or `@DefaultValue` can leave `connectTimeout` as `null`.

**Fix:** move defaults and validation into `DeliveryProperties`'s design, or require deployers to supply the property.

### 13.4. Ignoring missing nested objects

If YAML omits `retry`, a `Retry retry` record component can be `null`. When a service calls `settings.retry().maxAttempts()`, a `NullPointerException` can occur.

**Fix:** use `@NotNull`/`@Valid` validation, provide valid defaults, or handle optional configuration explicitly.

### 13.5. Believing data types alone enforce business validity

Value `retry.max-attempts=0` binds to `int` successfully, yet is invalid if the feature must try at least once. `Duration.ofSeconds(-5)` is also a valid `Duration` instance, even though a negative timeout makes no sense in some APIs.

**Fix:** add appropriate business constraints, such as `@Min(1)` or custom validation for positive `Duration`s.

### 13.6. Forgetting to update tests

Old tests might attach `@TestPropertySource` or mock a `@Value` field. After migration, tests should construct an appropriate `DeliveryProperties` or supply full properties for the Binder to build the object.

**Fix:** update tests that relied on the old injection style to match each test's goal: unit tests use Java objects directly, integration tests use real `Environment` and Binder.

### 13.7. Exposing secrets in a record's `toString()`

Java records generate `toString()` including all components. If you put an API token or password into a record, logging the whole object directly can leak the value.

**Fix:** never log entire sensitive configuration objects; log only non-sensitive attributes and use proper secret management. Validation and typed binding do not hide values if application code prints them.

### 13.8. Treating configuration beans as mutable objects

With JavaBeans containing setters, code could accidentally call `properties.setTimeout(...)` at runtime, causing in-memory state to diverge from initial configuration. In apps requiring dynamic updates, dedicated lifecycle and synchronization designs are needed.

**Fix:** for startup-read, rarely changing configuration, use constructor binding/records. Do not treat mutating fields as an automatic Config Data update mechanism.

## 14. A maintainable project layout

With multiple functional domains, split configuration classes by prefix:

~~~text
src/main/java/com/example/app/
├── AppApplication.java
├── delivery/
│   ├── DeliveryService.java
│   ├── DeliveryRetryPolicy.java
│   └── config/
│       └── DeliveryProperties.java
├── email/
│   ├── EmailService.java
│   └── config/
│       └── EmailProperties.java
└── storage/
    ├── StorageService.java
    └── config/
        └── StorageProperties.java
~~~

In YAML:

~~~yaml
app:
  delivery:
    endpoint: https://delivery.example.org
    connect-timeout: 4s
    retry:
      max-attempts: 3
      backoff: 250ms

  email:
    from: noreply@example.org
    timeout: 5s

  storage:
    base-path: /var/app/data
~~~

Each service depends only on its own domain's configuration. An "`AllApplicationSettings`" object with hundreds of fields would reintroduce wide coupling and hard-to-test dependencies, even without `@Value`.

You can keep configuration in a dedicated `config` package or alongside business modules; choose whichever matches your project's current architecture and conventions.

## 15. Migration practice exercises

### Exercise 1 — Grouping configuration

Currently:

~~~java
@Value("${app.report.enabled:true}")
private boolean enabled;

@Value("${app.report.max-rows:500}")
private int maxRows;

@Value("${app.report.output-dir:/tmp/reports}")
private String outputDir;
~~~

Create `ReportProperties` with prefix `app.report` and three corresponding components. One way to write it:

~~~java
import java.nio.file.Path;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("500") int maxRows,
        @DefaultValue("/tmp/reports") Path outputDir) {
}
~~~

Register the record with `@ConfigurationPropertiesScan` and inject it into a service.

### Exercise 2 — Nested properties

Currently using:

~~~properties
app.cache.enabled=true
app.cache.redis.host=localhost
app.cache.redis.port=6379
~~~

Build `CacheProperties` with a nested record `Redis(String host, int port)`. Verify that `settings.redis().host()` returns `localhost`.

### Exercise 3 — Validation

Change `app.delivery.retry.max-attempts` to `0` and apply `@Min(1)` in the nested record. Observe the configuration error at startup. Try deleting `app.delivery.endpoint` and using `@NotNull` to catch the missing required field.

### Exercise 4 — Profile override

Create `application-dev.yml` with `connect-timeout: 8s` and `application-prod.yml` with `connect-timeout: 2s`. Run with each profile and verify `DeliveryProperties.connectTimeout()`. Do not modify Java code when switching environments.

### Exercise 5 — Unit test without Spring

Instantiate `DeliveryProperties` via the record constructor and pass it to `DeliveryService`. Verify that `supportsRegion("vn")` returns the right result for the provided list.

### Exercise 6 — Tracking down a lost default

After removing `@Value("${app.delivery.connect-timeout:4s}")`, a test gets `connectTimeout() == null`. Decide the right place for the default: YAML, `@DefaultValue("4s")`, or making the setting required. Explain your reasoning.

## 16. Checklist when reviewing a change from `@Value` to a configuration object

A change can be reviewed through these technical questions:

- Are all keys of a business domain grouped under a clear prefix?
- Does each field/record component have a type matching real data?
- Have previous `@Value` defaults been preserved or intentionally revised?
- Is the configuration class registered properly with Spring Boot?
- Are required fields and business constraints validated appropriately?
- Do configuration consumers inject the object and remove obsolete placeholders?
- Do profile configurations, environment variables, and CLI arguments still yield expected effective values?
- Are missing configuration, wrong-type, and validation-failure scenarios covered by suitable tests?
- Is there any place logging the entire object and risking secret leakage?

This checklist helps confirm that refactoring code structure **does not silently alter the semantics of active properties**.

## 17. Key takeaways

`@Value` suits injecting a small property at one usage point. When multiple properties belong to the same feature, using `@ConfigurationProperties` creates **a structured configuration contract**, with clear prefixes, data types, nested objects, lists, defaults, and validation.

With Spring Boot 3.3 and Java 21, a record annotated with `@ConfigurationProperties`, registered via `@ConfigurationPropertiesScan`, and injected via constructor is a concise way to replace scattered `@Value` annotations. After migrating, Spring Boot still uses the same `Environment` mechanism and configuration precedence order; what must be preserved are the **effective values and business behavior** of the original properties.

## References

- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 — Constructor Binding](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding)
- [Spring Boot 3.3 — Configuration Properties Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Boot 3.3 — @Value and Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.vs-value-annotation)
- [Spring Framework — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)