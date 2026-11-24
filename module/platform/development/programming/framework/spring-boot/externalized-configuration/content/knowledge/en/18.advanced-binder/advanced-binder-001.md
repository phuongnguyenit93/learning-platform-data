# When to Use Programmatic Binding Instead of Annotations in Spring Boot

## Objectives

In Spring Boot, the most common way to read a configuration group is to create a class/record annotated with **@ConfigurationProperties**, register it with Spring, and inject the configuration bean into services. This approach is concise, declares a clear contract, supports nested configurations, and integrates with validation. However, there are situations where an application needs **direct control over the timing, prefix, target type, or binding result handling**. In such cases, the **Binder API** can be used to bind properties in Java code, also known as *programmatic binding*.

For example:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {}
~~~

and:

~~~java
Binder binder = Binder.get(environment);
ClientProperties client = binder
        .bind("app.client", ClientProperties.class)
        .orElse(null);
~~~

both aim to read the **app.client** group. However, the second option lets the code **directly decide when to bind**, choose the prefix via logic, distinguish between present and absent data, and handle the result as needed.

**Do not assume that the Binder API is inherently better than annotations.** For stable configurations tied to the application lifecycle, annotations are usually easier to maintain. Programmatic binding is suitable when there are requirements that annotations cannot express conveniently, or when a component that is not a Spring bean needs to read configuration in a controlled way.

After this lesson, the reader will be able to:

- Describe the **externalized configuration → PropertySource → Binder → Java object** mechanism.
- Distinguish between **@ConfigurationProperties**, **@Value**, **Environment.getProperty**, and the **Binder API**.
- Know when to switch—and when not to switch—to programmatic binding.
- Use **Binder.get(environment)**, **bind**, **BindResult**, **Bindable**, List, and Map.
- Understand dynamic prefix handling, per-tenant/per-module configuration, optional values, and fallbacks.
- Control conversion, validation, BindHandler, binding timing, and error handling.
- Write test examples with **MapConfigurationPropertySource** without starting the entire application.
- Avoid misconceptions about runtime refresh, security, typos, or configuration precedence order.

The examples follow the **Spring Boot 3.x** style, using Java 17+ and familiar APIs from **org.springframework.boot.context.properties.bind**. For projects using another version, verify the corresponding packages, overloads, and extension points.

---

## 1. Configuration Processing Flow in Spring Boot

Configuration data can come from:

- application.properties or application.yml.
- Profile-specific documents, for example application-prod.yml.
- Operating system environment variables.
- JVM system properties, for example **-Dapp.client.timeout=10s**.
- Command-line arguments, for example **--app.client.timeout=10s**.
- Config Data imports/locations and PropertySources provided by the application or libraries.

Spring Boot places them into a lookup system with a precedence order. Binder handles property names, nested structures, and conversion before creating or populating Java objects.

~~~text
application.yml      ENV      -Dsystem.property      --argument
       \              |                |                  /
        \             |                |                 /
                 Spring Environment
                 (PropertySource precedence)
                          |
                          v
                       Binder
             (name matching, conversion,
              nested paths, collection)
                          |
             +------------+------------+
             |                         |
             v                         v
  @ConfigurationProperties     Binder API in Java code
  when creating config bean    when explicitly invoked
             |                         |
             v                         v
        Properties bean           Object / BindResult
~~~

Key point: **The Binder API does not create a new precedence system**. When Binder retrieves data from Spring Environment, the result is still governed by the precedence order of the existing configuration sources.

If a value in application.yml is overridden by a command-line argument, replacing @ConfigurationProperties with Binder.get(environment) will not suddenly give the YAML file higher priority.

## 2. Three Common Ways to Read Configuration

Suppose the configuration is:

~~~yaml
app:
  client:
    base-url: "https://catalog.example.test"
    timeout: 5s
    pool:
      max-size: 20
      enabled: true
~~~

### 2.1. @Value — a few individual properties

~~~java
@Value("\${app.client.base-url}")
private String baseUrl;

@Value("\${app.client.timeout:5s}")
private Duration timeout;
~~~

At integration points supported by Spring, @Value resolves placeholders and converts values to the target type. It works well for a few simple properties, but it is not the best choice for deeply nested structures.

### 2.2. @ConfigurationProperties — long-lived configuration model

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Duration timeout,
        Pool pool
) {
    public record Pool(int maxSize, boolean enabled) {}
}
~~~

Register the record via **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties(ClientProperties.class)**, then inject ClientProperties into services. This is the preferred default choice when the configuration group is already well-known at design time.

### 2.3. Binder — binding via Java code at a call site

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

Binder binder = Binder.get(environment);
ClientProperties properties =
        binder.bind("app.client", ClientProperties.class)
              .orElse(null);
~~~

Unlike @ConfigurationProperties, this code directly asks Binder to read a prefix and create an object. It allows handling the result, choosing the prefix conditionally, and deciding how to react if the prefix is not bound.

### 2.4. Comparison Table

| Criterion | @Value | @ConfigurationProperties | Binder API |
| --- | --- | --- | --- |
| Nested object modeling | Inconvenient | Very suitable | Very suitable |
| Managed as a configuration bean | At injection points | Yes, when registered | Not automatic |
| Fixed prefix | Usually in placeholder | In annotation | Passed as parameter |
| Code-selected prefix | Hard to maintain | Not the primary goal | Suitable |
| Clearly knows whether binding succeeded | Requires extra logic | Usually fails/validates at startup | BindResult |
| When data is read | Usually at injection time | Usually at bean creation | When code calls bind |
| Built-in validation | Depends on injection point | Standard mechanism available | Requires active setup/application |
| Conciseness for stable groups | Moderate | Best | May require more code |
| Metadata/tooling integration | Limited | Good with processor | No equivalent metadata contract automatically |

**Selection rule:** if a stable configuration group can become a clear bean, do not switch to the Binder API just to avoid an annotation.

## 3. Case 1: Dynamically Selected Configuration Prefix

Suppose an application works with two partner services:

~~~yaml
integration:
  catalog:
    endpoint: "https://catalog.example.test"
    timeout: 3s
  billing:
    endpoint: "https://billing.example.test"
    timeout: 8s
~~~

The two configurations share the same structure but have different prefix names:

~~~text
integration.catalog.*
integration.billing.*
~~~

A shared record:

~~~java
import java.time.Duration;

public record PartnerSettings(
        String endpoint,
        Duration timeout
) {}
~~~

With the Binder API:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class PartnerSettingsReader {

    private final Binder binder;

    public PartnerSettingsReader(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public PartnerSettings read(String partner) {
        if (!partner.equals("catalog") && !partner.equals("billing")) {
            throw new IllegalArgumentException("Unknown partner: " + partner);
        }

        String prefix = "integration." + partner;
        return binder.bind(prefix, PartnerSettings.class)
                .orElseThrow(() ->
                        new IllegalStateException(
                                "Missing configuration: " + prefix));
    }
}
~~~

This is a clear example of a **prefix chosen at method invocation time**. If a module selects catalog or billing according to a controlled rule, Binder avoids writing multiple branches that manually bind each scalar.

### 3.1. Do not concatenate prefixes directly from untrusted input

An HTTP call accepting an arbitrary **partner** must not be used directly as a Binder path without verifying that it belongs to a valid set of names. Otherwise, a request could cause the application to read outside the intended scope or expose unauthorized configuration data.

An enum or registry can be used:

~~~java
public enum Partner {
    CATALOG("catalog"),
    BILLING("billing");

    private final String key;

    Partner(String key) {
        this.key = key;
    }

    public String key() {
        return key;
    }
}
~~~

And:

~~~java
public PartnerSettings read(Partner partner) {
    String prefix = "integration." + partner.key();
    return binder.bind(prefix, PartnerSettings.class)
            .orElseThrow(() ->
                    new IllegalStateException("Missing " + prefix));
}
~~~

**Dynamic prefix does not mean arbitrary prefix.** When used in a multi-tenant system, authorization boundaries and policies governing who can view configurations must live outside Binder.

### 3.2. When Map is better than a dynamic prefix

If all partner configurations share the exact same structure, you can use:

~~~java
@ConfigurationProperties(prefix = "integration")
public record IntegrationProperties(
        Map<String, PartnerSettings> partners
) {}
~~~

Same YAML, restructured:

~~~yaml
integration:
  partners:
    catalog:
      endpoint: "https://catalog.example.test"
      timeout: 3s
    billing:
      endpoint: "https://billing.example.test"
      timeout: 8s
~~~

Then the service can use **properties.partners().get(partner)**. This approach is generally better when the partner list is known and you want all configurations bound and validated at startup.

Use a dynamic prefix when the source structure is difficult to change or you only want to bind selected groups; use Map when the application's data model is genuinely a **key → value table** and the whole table can be bound as one bean.

## 4. Case 2: Bind Only When a Feature Is Enabled

An application has a report export module that does not always run:

~~~yaml
app:
  reports:
    enabled: false
    export:
      directory: "/var/reports"
      batch-size: 100
~~~

If the module is only used when enabled=true, you may need to decide whether to bind the export group or not.

Record:

~~~java
public record ExportSettings(String directory, int batchSize) {}
~~~

Example at an initialization point:

~~~java
boolean enabled = Boolean.TRUE.equals(
        environment.getProperty(
                "app.reports.enabled",
                Boolean.class,
                false
        )
);

if (enabled) {
    ExportSettings settings = Binder.get(environment)
            .bind("app.reports.export", ExportSettings.class)
            .orElseThrow(() ->
                    new IllegalStateException("Export config missing"));

    // Initialize the export module with settings.
}
~~~

The advantage of programmatic binding in this situation is that the code expresses **the decision to bind only when needed** and **how to handle missing configuration**.

However, distinguish carefully:

- If you only want to **enable/disable a bean** based on a property, **@ConditionalOnProperty** is usually the more appropriate Spring Boot solution.
- If you want configuration bound and validated right at startup regardless of whether the feature is enabled or disabled, @ConfigurationProperties may be clearer.
- If you only want to choose *when* to perform a specific bind in code, the Binder API is useful.

Do not use Binder to replace the entire conditional bean registration system when bean creation conditions already have suitable annotations.

## 5. Case 3: Optional Configuration That May Truly Be Absent

Suppose an application has **app.telemetry** configuration, but some environments do not deploy telemetry.

~~~yaml
app:
  telemetry:
    endpoint: "https://metrics.example.test"
    interval: 30s
~~~

A record:

~~~java
import java.time.Duration;

public record TelemetrySettings(
        String endpoint,
        Duration interval
) {}
~~~

It can be read as:

~~~java
var result = Binder.get(environment)
        .bind("app.telemetry", TelemetrySettings.class);

if (result.isBound()) {
    TelemetrySettings settings = result.get();
    // Use settings.
} else {
    // Accept that telemetry configuration does not exist.
}
~~~

**BindResult.isBound()** lets you separate the case where a binding result exists from the case where no object was bound. This differs from always creating a bean with null fields and letting other code infer its state.

### 5.1. Do not treat configuration errors as "missing data"

A dangerous mistake is:

~~~java
try {
    return binder.bind("app.telemetry", TelemetrySettings.class)
            .orElse(null);
} catch (Exception ex) {
    return null;
}
~~~

This approach can swallow type conversion errors, object structure errors, and genuine deployment mistakes.

Distinguish between:

| Situation | Handling to consider |
| --- | --- |
| Prefix is not provided and is allowed to be absent | Return Optional or disabled state |
| Prefix is provided but value has wrong type | Report error, do not silently ignore |
| Prefix has some properties but misses required fields | Validation or explicit invariant |
| A higher-precedence source overrides a value | Analyze precedence |
| Prefix is not in allowlist | Reject request before binding |

**Optional** does not mean **ignoring all errors**.

### 5.2. Using orElse, get, and isBound

~~~java
var bound = binder.bind("app.telemetry", TelemetrySettings.class);

TelemetrySettings withFallback = bound.orElse(
        new TelemetrySettings("disabled", Duration.ZERO)
);
~~~

**orElse(...)** is the choice for the *no result* case. It does not turn a conversion error into a valid default value.

As for **get()**, it should only be called when binding produced a result or when it is established that a missing result should raise an error. Calling get on a BindResult without a value will fail rather than silently returning null.

## 6. Case 4: Using Target Types Decided at Runtime

Some systems need to read configurations of different types depending on the module:

~~~yaml
app:
  workers:
    email:
      concurrency: 4
      sender: "noreply@example.test"
    indexing:
      concurrency: 8
      index-name: products
~~~

You can design the records:

~~~java
public record EmailWorkerSettings(int concurrency, String sender) {}
public record IndexingWorkerSettings(int concurrency, String indexName) {}
~~~

In a factory managing worker types:

~~~java
Binder binder = Binder.get(environment);

EmailWorkerSettings email = binder
        .bind("app.workers.email", EmailWorkerSettings.class)
        .orElseThrow();

IndexingWorkerSettings indexing = binder
        .bind("app.workers.indexing", IndexingWorkerSettings.class)
        .orElseThrow();
~~~

The two calls use **two prefixes and two target classes**. The Binder API fits when a factory needs to pick a configuration set according to the activated type.

Avoid writing code that reads every property as Map<String, Object> and casts manually when the concrete Java type is already known. Binder handles conversion, nested values, and collections more consistently than manual string assembly.

### 6.1. Do not overuse runtime type selection

If the application only has two fixed workers from design time, creating two separate @ConfigurationProperties beans and injecting them into the factory can be simpler. Programmatic binding increases responsibility for managing timing, errors, and validation manually.

Choose it only when **dynamism** provides a clear benefit.

## 7. Binder API: Core Components

Classes and APIs to recognize:

| Component | Role |
| --- | --- |
| Binder | Entry point to bind from ConfigurationPropertySource instances |
| Binder.get(Environment) | Create/obtain a Binder backed by Environment's configuration sources |
| bind(prefix, Class<T>) | Read a prefix and bind it to a concrete Java type |
| bind(prefix, Bindable<T>) | Use a detailed target type description |
| BindResult<T> | Binding result; indicates whether binding succeeded |
| Bindable<T> | Describes the type or instance used as the target |
| ConfigurationPropertySource | Data source in the property model intended for binder |
| MapConfigurationPropertySource | Test/programmatic source backed by a Map |
| BindHandler | Extension point to intercept binding lifecycle/handling |
| Converter/ConversionService | Converts String/property values to target types |

Common imports:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.core.env.Environment;
~~~

### 7.1. Foundational example: binding a record

~~~java
import java.time.Duration;

public record HttpSettings(
        Duration connectTimeout,
        Duration readTimeout,
        int maxConnections
) {}
~~~

Configuration:

~~~yaml
app:
  http:
    connect-timeout: 2s
    read-timeout: 8s
    max-connections: 40
~~~

Code:

~~~java
Binder binder = Binder.get(environment);

HttpSettings http = binder
        .bind("app.http", HttpSettings.class)
        .orElseThrow(() ->
                new IllegalStateException("app.http is missing"));
~~~

With this data, binder can create HttpSettings with Duration 2 seconds, Duration 8 seconds, and int 40.

Spring Boot does not require the HttpSettings record to carry @ConfigurationProperties when **code actively invokes Binder**. The annotation is used for automatic integration with the configuration bean lifecycle; an explicit Binder call already specifies the prefix and target type.

### 7.2. Java field names and property names

~~~text
Java record component:  readTimeout
Canonical property:     app.http.read-timeout
Environment variable:   APP_HTTP_READTIMEOUT
~~~

Binder applies appropriate relaxed binding for configuration sources and does not require naming the Java field read-timeout.

### 7.3. Reading a scalar works, though it is not always needed

~~~java
int port = binder.bind("server.port", Integer.class)
        .orElse(8080);
~~~

For a simple scalar, **environment.getProperty("server.port", Integer.class, 8080)** is often easier to read. The Binder API makes the most sense when handling **structured objects**, **dynamic prefixes**, or **BindResult**.

## 8. Bindable<T>: When Class<T> Is Not Enough

For simple types:

~~~java
binder.bind("app.http", HttpSettings.class)
~~~

is sufficient. However, Java generics such as **List<Server>** or **Map<String, Region>** need to preserve element type information.

Example:

~~~java
import java.util.List;

public record Server(String host, int port) {}
~~~

YAML:

~~~yaml
app:
  servers:
    - host: primary.example.test
      port: 8080
    - host: backup.example.test
      port: 8081
~~~

Binder:

~~~java
List<Server> servers = Binder.get(environment)
        .bind("app.servers", Bindable.listOf(Server.class))
        .orElse(List.of());
~~~

Here **Bindable.listOf(Server.class)** describes a List containing Server, not a List with unknown element type.

### 8.1. Binding a Map

~~~yaml
app:
  regions:
    asia:
      endpoint: "https://asia.example.test"
      timeout: 3s
    europe:
      endpoint: "https://eu.example.test"
      timeout: 5s
~~~

Record:

~~~java
import java.time.Duration;

public record Region(String endpoint, Duration timeout) {}
~~~

Binder:

~~~java
Map<String, Region> regions = Binder.get(environment)
        .bind(
                "app.regions",
                Bindable.mapOf(String.class, Region.class)
        )
        .orElse(Map.of());
~~~

Bindable carries both key type and value type information. This is convenient when reading a Map at a chosen prefix without creating a separate @ConfigurationProperties wrapper.

### 8.2. Why not use List.class?

~~~java
binder.bind("app.servers", List.class)
~~~

cannot express that **Server** is the element type. For collections of objects, losing the generic type can cause data to be bound only as generic structures or fail to reach the desired target type.

**Prefer Bindable.listOf(Server.class)** or a full type descriptor when working with collections, rather than raw generics.

### 8.3. Array and Set

Spring Boot binder supports various collection forms with corresponding rules. If you want a group of unique values regardless of order, Set is an option to consider. For ordered lists or indexed elements **[0]**, **[1]**, use List.

In public API design, do not change a type from List to Set just to write less binding code. The collection type must reflect the data contract.

## 9. Case 5: Binding into an Existing Instance

Given a prepared JavaBean-style class:

~~~java
public class PoolSettings {

    private int maxSize = 10;

    public int getMaxSize() {
        return maxSize;
    }

    public void setMaxSize(int maxSize) {
        this.maxSize = maxSize;
    }
}
~~~

Programmatic binding can work with an existing object via **Bindable.ofInstance(...)** in the appropriate overloads:

~~~java
PoolSettings target = new PoolSettings();

PoolSettings result = binder
        .bind("app.pool", Bindable.ofInstance(target))
        .orElse(target);
~~~

Understand the boundaries clearly:

- Binder can populate configured properties into target according to the corresponding JavaBean strategy.
- Default values initialized in the object can take effect when properties are not supplied.
- If target or nested collections are immutable, do not assume every type will be updated.
- State-mutation effects depend on the target type and binding strategy; test on the actual Spring Boot version.

### 9.1. When should you use ofInstance?

It is better suited when a **mutable or builder-like object** has already been constructed through a workflow and needs binder to populate additional configuration into it.

Do not choose ofInstance just to bypass the constructor of an immutable record. For records, binding directly by class and receiving the result is usually clearer.

### 9.2. Risk of rebinding the same mutable instance

If binder is called multiple times on the same mutable instance, some fields may retain stale state or be updated unpredictably, especially List/Map. If the goal is a fresh configuration snapshot, bind into **a new object** and swap the reference explicitly in the managing layer.

## 10. Case 6: Creating Objects from a Test Configuration Source

You do not need to start an ApplicationContext to test every Binder scenario. Spring Boot provides **MapConfigurationPropertySource**, allowing you to create a standalone property source from a Map.

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

Map<String, Object> values = Map.of(
        "app.http.connect-timeout", "2s",
        "app.http.read-timeout", "7s",
        "app.http.max-connections", "25"
);

Binder binder = new Binder(new MapConfigurationPropertySource(values));

HttpSettings http = binder
        .bind("app.http", HttpSettings.class)
        .orElseThrow();
~~~

This example can be placed in a plain Java unit test. It is very useful when you:

- Want to verify the binding structure of a record, nested class, List, or Map.
- Want to test canonical property names and conversion.
- Want to check missing keys or wrong-type values.
- Do not want to configure an entire application context for a small binding test.

**Important limitation:** A Binder created from this Map only sees the data in the provided source; it does not automatically read application.yml, environment variables, or profiles of the real application. It is an **isolated test environment**, not proof of PropertySource precedence at runtime.

### 10.1. When the application has multiple sources

If the goal is to reproduce precedence, you must supply the ConfigurationPropertySources in the appropriate order or use ApplicationContextRunner with the corresponding property values/profiles. A test using only a single Map does not prove whether CLI overrides env.

## 11. When Is Binder.get(environment) Convenient?

Inside a Spring bean:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.stereotype.Component;

@Component
public class ConfigReader {

    private final Binder binder;

    public ConfigReader(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public HttpSettings readHttp() {
        return binder.bind("app.http", HttpSettings.class)
                .orElseThrow();
    }
}
~~~

Here the Spring-injected Environment already contains the application's PropertySource hierarchy.

Advantages:

- No need to manually assemble sources from files and environment variables.
- Reuses Spring Boot's existing precedence.
- Can bind nested structures with conversion without manually parsing each key.

Limitations:

- Still requires explicitly specifying the prefix, target type, and handling unbound cases.
- Needs validation management if the configuration is critical.
- Must consider when the method is called and how results are cached.
- Does not automatically create a @ConfigurationProperties bean with equivalent metadata and lifecycle.

If it is only read once at startup and used indefinitely, you can produce the result in a constructor/factory and inject the configuration object where needed, instead of calling Binder on every request.

## 12. When Should You Avoid Calling Binder Repeatedly?

Suppose a Controller has:

~~~java
@GetMapping("/price")
public int price() {
    return Binder.get(environment)
            .bind("app.pricing.base-price", Integer.class)
            .orElse(100);
}
~~~

This is usually unnecessary if base-price is a stable configuration. It forces every request to perform lookup and conversion again, makes testing harder, and easily creates the false impression that properties hot-reload automatically.

A simpler design:

~~~java
@ConfigurationProperties(prefix = "app.pricing")
public record PricingProperties(int basePrice) {}
~~~

The Controller injects PricingProperties and reads **properties.basePrice()**.

### 12.1. Programmatic binding does not mean dynamic refresh

Some configuration sources in Environment can be updated via dedicated mechanisms, however:

- A Java process's environment variables generally do not change automatically when another shell sets a variable.
- An already-bound object does not automatically update when the source changes.
- Calling binder again only reflects sources **available at the time of the call**, without guaranteeing the system has refreshed all Config Data or related beans.

If runtime updates are required, you must build or use an appropriate refresh mechanism, defining when sources are reloaded, who validates the data, and how snapshots are safely replaced.

### 12.2. On-demand binding is a lifecycle decision

It can make sense if a feature is only loaded on demand, but you must clarify whether **every invocation** is intended or **only the first time followed by caching**. For rarely changing configurations, avoid unnecessary repeated binding.

## 13. BindResult and Proper Error Handling

A call:

~~~java
BindResult<HttpSettings> result =
        binder.bind("app.http", HttpSettings.class);
~~~

has these scenarios:

1. **Bound successfully:** result.isBound() is true; result.get() returns HttpSettings.
2. **No suitable data found to bind:** result may be unbound; handle fallback according to the contract.
3. **Binding failed:** may throw an exception, such as a type conversion failure or object instantiation failure.

Do not lump cases 2 and 3 together as "no configuration".

Handling example:

~~~java
BindResult<HttpSettings> result =
        binder.bind("app.http", HttpSettings.class);

if (!result.isBound()) {
    throw new IllegalStateException(
            "Missing required configuration: app.http"
    );
}

HttpSettings http = result.get();
~~~

### 13.1. Do not use fallback for wrong-type errors

With configuration:

~~~yaml
app:
  http:
    max-connections: "many"
~~~

the record expects an int. During binding, the string **many** does not become an absent value that **orElse(new HttpSettings(...))** can handle.

If data is supplied with the wrong type, report an error so operators fix the configuration rather than silently falling back to a default value that alters system behavior.

### 13.2. Returning Optional in the application API

A reader class can express "optionality":

~~~java
import java.util.Optional;

public Optional<TelemetrySettings> readTelemetry() {
    var result = binder.bind(
            "app.telemetry",
            TelemetrySettings.class
    );
    return result.isBound()
            ? Optional.of(result.get())
            : Optional.empty();
}
~~~

This is an **application-defined API contract**, not Binder automatically producing Optional for every call.

If the design requires only valid data to be returned, add validation before exposing the object externally.

## 14. Why Can Binder Handle Duration and Nested Objects?

Spring Boot Binder combines several steps:

~~~text
Prefix / path name
       |
       v
Read ConfigurationProperty
       |
       v
Match names, collection indices, nested paths
       |
       v
Conversion from source value to target type
       |
       v
Constructor or JavaBean properties
       |
       v
Final object
~~~

Example:

~~~yaml
app:
  storage:
    max-file-size: 25MB
    retention: 7d
~~~

Record:

~~~java
import java.time.Duration;
import org.springframework.util.unit.DataSize;

public record StorageSettings(
        DataSize maxFileSize,
        Duration retention
) {}
~~~

Binder can convert string values into DataSize and Duration using Spring Boot's converters.

However, **Binder only guarantees conversion when the value uses a supported syntax**. For instance, retention="never" can cause a conversion error unless a custom converter or handling logic exists.

### 14.1. Do not convert everything to String manually

A poor choice:

~~~java
Map<String, String> config = ...
int retries = Integer.parseInt(config.get("max-retries"));
Duration timeout = Duration.parse(config.get("timeout"));
~~~

Such code has to manually handle names, defaults, types, units, errors, nested paths, and precedence. Binder is designed to handle these responsibilities consistently.

If the configuration is structured, bind directly to the target type instead of reading everything as String and parsing manually.

## 15. What Does Not Change When Switching to Programmatic Binding

Changing the API call **does not change**:

- The precedence order of existing PropertySources.
- The canonical naming rules to follow.
- The meaning of dots and hyphens in property paths.
- Resolution rules for profiles or Config Data imports.
- The principle that a List is typically replaced by a List from a higher-precedence source.
- The rule that a Map can merge keys when multiple sources supply data.
- The requirement that mistyped data be reported as an error.
- System safety and security requirements.

In other words, **programmatic binding changes how Binder is invoked, not the principles of externalized configuration**.

## 16. Nested Objects with Binder

YAML:

~~~yaml
app:
  notification:
    enabled: true
    delivery:
      retry:
        max-attempts: 3
        backoff: 250ms
      batch:
        max-size: 50
~~~

Model:

~~~java
import java.time.Duration;

public record NotificationSettings(
        boolean enabled,
        Delivery delivery
) {
    public record Delivery(Retry retry, Batch batch) {}
    public record Retry(int maxAttempts, Duration backoff) {}
    public record Batch(int maxSize) {}
}
~~~

Bind:

~~~java
NotificationSettings settings = binder
        .bind("app.notification", NotificationSettings.class)
        .orElseThrow();
~~~

Logical paths:

~~~text
app.notification.enabled
app.notification.delivery.retry.max-attempts
app.notification.delivery.retry.backoff
app.notification.delivery.batch.max-size
~~~

Binder can create nested records via constructor binding when the target types and data match. There is no need to call bind separately for each field.

### 16.1. When you need to bind an individual branch

If Delivery is optional and only one module needs Batch, you can bind:

~~~java
NotificationSettings.Batch batch = binder
        .bind(
            "app.notification.delivery.batch",
            NotificationSettings.Batch.class
        )
        .orElseThrow();
~~~

This is a way to read only a single branch. However, if data must be checked consistently against an invariant between Retry and Batch, binding isolated branches can lose overall validation context. In that case, binding the entire NotificationSettings and validating the full object may be better.

## 17. List, Map, and Source Rules

List example:

~~~yaml
app:
  servers:
    - host: alpha.example.test
      port: 8080
    - host: beta.example.test
      port: 8081
~~~

~~~java
public record Server(String host, int port) {}

List<Server> servers = binder
        .bind("app.servers", Bindable.listOf(Server.class))
        .orElse(List.of());
~~~

Map example:

~~~yaml
app:
  labels:
    owner: platform
    region: asia
~~~

~~~java
Map<String, String> labels = binder
        .bind(
            "app.labels",
            Bindable.mapOf(String.class, String.class)
        )
        .orElse(Map.of());
~~~

When multiple sources exist:

- A **List** from a higher-precedence source usually replaces a List from a lower-precedence source rather than appending elements.
- A **Map** can merge keys from different sources, while duplicate keys take the value according to precedence.
- If a Map key contains dots or special characters, pay attention to bracket notation in the appropriate source.

Choosing the Binder API does not alter these merge/replacement rules.

### 17.1. Map is not always suitable for dynamic tenants

If a Map contains all tenants and is bound at startup, all tenants can be validated together. This is suitable when the number of tenants is moderate and the full configuration must be valid before the application accepts requests.

If a system has thousands of tenants activated in waves, or some tenants only have configuration when needed, dynamic prefix binding can offer benefits. In that case, caching, validation, and authorization must be added, as Binder is not responsible for these mechanisms.

## 18. Validation: Crucial Difference from Annotations

With @ConfigurationProperties:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotBlank String baseUrl,
        @Valid Pool pool
) {
    public record Pool(@Min(1) int maxSize) {}
}
~~~

When the bean is registered via the configuration properties mechanism and the project has an appropriate Jakarta Validation provider, Spring Boot runs validation during binding.

**With an explicit Binder API call, do not assume that merely putting @Validated on a record runs the exact same validation as a configuration properties bean.** Programmatic binding must explicitly decide how to invoke validation.

### 18.1. Simple approach: bind then use Jakarta Validator

Suppose the application injects **jakarta.validation.Validator**:

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;

public final class ClientConfigReader {

    private final Binder binder;
    private final Validator validator;

    public ClientConfigReader(
            Environment environment,
            Validator validator
    ) {
        this.binder = Binder.get(environment);
        this.validator = validator;
    }

    public ClientProperties read() {
        ClientProperties settings = binder
                .bind("app.client", ClientProperties.class)
                .orElseThrow();

        Set<ConstraintViolation<ClientProperties>> violations =
                validator.validate(settings);

        if (!violations.isEmpty()) {
            throw new IllegalStateException(
                    "Invalid app.client configuration: "
                    + violations.iterator().next().getPropertyPath()
            );
        }

        return settings;
    }
}
~~~

The example puts only the property path in the error message, avoiding printing configuration values that might contain sensitive data.

For this code to work, there must be a validator provider and appropriate Validator injection/initialization. In Spring Boot 3.x, the commonly used dependency is **spring-boot-starter-validation**.

### 18.2. @Valid on nested objects is still necessary

If ClientProperties contains Pool and you want to check the **@Min(1)** constraint inside Pool, appropriate cascading is needed:

~~~java
public record ClientProperties(
        @NotBlank String baseUrl,
        @Valid @NotNull Pool pool
) {}
~~~

**@Valid** descends into Pool; **@NotNull** checks that Pool is present. Using @Valid alone does not forbid null.

### 18.3. Programmatic validation is the caller's responsibility

With the Binder API, the caller must decide:

1. Can the configuration be completely absent?
2. If an object exists but violates constraints, should startup fail or should the module be skipped?
3. Do nested Lists/Maps need to be validated?
4. Do cross-field invariants like timeout > backoff need checking?
5. Are errors allowed to display raw values?

If all configuration groups in the application must fail-fast at startup, manually implementing the answers above with Binder in many places can be more complex than using @ConfigurationProperties.

## 19. BindHandler — When You Need to Intercept the Binding Process

**BindHandler** is an advanced extension point of the Spring Boot binder. It lets you observe or adjust the binding process at hooks defined by the API, such as when binding starts, succeeds, fails, or finishes.

Some needs that may lead to BindHandler:

- Detecting unbound properties within a group.
- Handling a specialized, scope-limited error policy.
- Integrating validation into the binding process instead of validating the object afterward.
- Controlled observation of property names and binding status for diagnostics.
- Building a shared framework/module binding pipeline.

### 19.1. Using the overload with BindHandler

In supported Spring Boot versions, Binder has an overload accepting a **Bindable<T>** and a **BindHandler**:

~~~java
BindResult<HttpSettings> result = binder.bind(
        "app.http",
        Bindable.of(HttpSettings.class),
        handler
);
~~~

Here **handler** represents a BindHandler built for a specific policy. This is an API illustration skeleton, not a complete self-contained handler implementation.

**Do not add a BindHandler just to read a simple record.** It can introduce hard-to-follow error or lifecycle rules if multiple modules intervene.

### 19.2. Do not use ignore-errors to hide misconfiguration

Spring Boot has BindHandlers for specialized error policies, but intentionally ignoring bind errors is a risky decision.

For example, a mistyped maxConnections could cause the application to run with a default without anyone noticing because errors were ignored. For URLs, credentials, resource limits, or critical production parameters, let errors surface clearly instead of ignoring them automatically.

### 19.3. Strict binding is not a one-size-fits-all boolean

A requirement like "fail if there are unbound properties" may require an appropriate handler or strict configuration. However, understand that:

- A prefix might contain properties meant for multiple versions/modules.
- Map keys and List indices must be interpreted according to Java types.
- Properties from multiple sources may share the same logical name.
- Checking unknown properties differs from checking mistyped values.

When applying strict binding to a module, write tests with valid keys, invalid keys, and nested properties to verify the validation scope.

## 20. An Independent Source: MapConfigurationPropertySource

If a library has normalized Map-based configuration:

~~~java
Map<String, Object> sourceData = Map.of(
        "module.worker.concurrency", "4",
        "module.worker.enabled", "true"
);
~~~

you can create:

~~~java
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

Binder binder = new Binder(
        new MapConfigurationPropertySource(sourceData)
);

WorkerSettings settings = binder
        .bind("module.worker", WorkerSettings.class)
        .orElseThrow();
~~~

Record:

~~~java
public record WorkerSettings(int concurrency, boolean enabled) {}
~~~

This is an option for **libraries, tests, or framework modules** that need binding capabilities without putting data into the shared Spring Environment.

### 20.1. Why not just put data into System properties?

Inserting data via **System.setProperty** for Binder to see has many drawbacks:

- Mutates global JVM state.
- Can interfere with tests running in parallel.
- Mixes the module's configuration with other configurations.
- Hard to restore prior state before/after tests.
- Does not manage sources and precedence cleanly.

A standalone MapConfigurationPropertySource provides a cleaner data scope for testing or isolated binding.

### 20.2. Do not use a test source to evaluate runtime precedence

A Binder built from a single Map does not prove what happens when the real application receives env vars, JVM system properties, and CLI args simultaneously. For precedence concerns, test via ApplicationContextRunner or configure a corresponding set of sources.

## 21. Configuring Extensible Plugins/Modules

An application can load modules by name:

~~~yaml
plugins:
  cache:
    enabled: true
    ttl: 10m
  audit:
    enabled: false
    batch-size: 100
~~~

Each plugin has a different configuration type. The plugin manager can read the list of allowed plugins and bind the appropriate prefix to the known class type.

Example:

~~~java
public record CachePluginSettings(boolean enabled, Duration ttl) {}
public record AuditPluginSettings(boolean enabled, int batchSize) {}
~~~

~~~java
CachePluginSettings cache = binder
        .bind("plugins.cache", CachePluginSettings.class)
        .orElseThrow();

AuditPluginSettings audit = binder
        .bind("plugins.audit", AuditPluginSettings.class)
        .orElseThrow();
~~~

If the plugin manager selects modules using a registry, a shared programmatic binding layer can be built.

**Even so:** do not bind arbitrary classes specified by untrusted strings from requests or user inputs. Select target classes from an application-controlled registry; do not use reflection on external input to resolve arbitrary types.

## 22. When a Module Needs Configuration Before Creating Business Beans

There are framework initialization needs such as:

- Creating beans based on a variable-length configuration list.
- Selecting an implementation based on a configuration property.
- Creating clients for multiple endpoints from a registry.
- Configuring a library without built-in @ConfigurationProperties integration.
- Reading information to decide which modules or beans to register.

Programmatic binding can support the **reading configuration to make decisions** step, but lifecycle must be considered carefully.

If bean selection only depends on a simple boolean/string property, conditional annotations like **@ConditionalOnProperty** or Spring Boot auto-configuration are usually appropriate.

If a complex structure must be bound to decide how to assemble a group of beans, the Binder API can be a tool for advanced framework configuration.

### 22.1. Do not overuse overly early bean initialization

Components executing during bootstrap may run before all configuration sources or supporting beans are ready, depending on the extension point. Calling Binder at an inappropriate phase can result in missing sources or missing converters that the application expects.

When using specialized Spring Boot extension points, verify:

- Which PropertySources are already available.
- Which ConversionService and placeholder resolution are being used.
- Whether Environment/Validator can be injected at that point.
- Whether Spring Boot auto-configuration should manage it instead of doing it manually.

Do not assume that Binder.get(environment) from an ApplicationRunner and Binder in a very early hook always see the same environment state.

## 23. Constructor Binding and JavaBean Binding with Binder

Given a record:

~~~java
public record PoolSettings(int maxSize, boolean enabled) {}
~~~

Binder can use the constructor to create the record.

A JavaBean:

~~~java
public class PoolSettingsBean {
    private int maxSize;
    private boolean enabled;

    public int getMaxSize() { return maxSize; }
    public void setMaxSize(int maxSize) { this.maxSize = maxSize; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
}
~~~

Binder can populate values through JavaBean properties.

You do not need to turn a record into a JavaBean just because you switched from annotations to programmatic binding. The target type, constructor, and binding metadata determine how binder constructs the object.

### 23.1. Mutable/immutable collections

With a getter-only JavaBean containing an initialized mutable List/Map, binder has mechanisms to update the collection in supported cases. If the collection is **List.of** or an unmodifiable wrapper and has no setter, updating during binding may not be possible.

With records, bind List/Map via the constructor and make a **defensive copy** if read-only state is needed. Programmatic binding does not make collections immutable automatically.

## 24. Default Values: Where Should They Live?

A configuration group can get defaults from:

1. The base **application.yml** file.
2. Values in JavaBean field initializers.
3. Constructors or compact constructors of a record.
4. **@DefaultValue** in supported constructor binding.
5. Fallback logic in code handling **BindResult**.

Example:

~~~java
HttpSettings http = binder
        .bind("app.http", HttpSettings.class)
        .orElse(new HttpSettings(
                Duration.ofSeconds(2),
                Duration.ofSeconds(5),
                10
        ));
~~~

This fallback applies when the entire bind result is absent, not as a per-field default rule for missing fields inside HttpSettings.

### 24.1. Per-field defaults differ from object-level defaults

Suppose app.http only has:

~~~yaml
app:
  http:
    read-timeout: 8s
~~~

Binder can create an HttpSettings with some missing members set to null/default primitive values depending on the target type and constructor. **orElse(...)** will not be chosen just because an inner field is missing, if the overall object was bound.

To set a specific default for connectTimeout, use base configuration, constructor logic, or an appropriate binder default mechanism. To detect missing fields, use validation.

### 24.2. Defaults can hide deployment errors

If a required production endpoint is omitted and code uses:

~~~java
.orElse(new PartnerSettings("http://localhost:8080", Duration.ofSeconds(5)))
~~~

production may mistakenly call localhost when configuration is absent. For URLs, secrets, or safety-critical settings, require the property and fail clearly rather than providing a "valid" yet unsafe fallback.

## 25. A Factory Using Binder with Proper Scope

Suppose a service wants to read options for each job type once and keep a snapshot:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class JobSettingsFactory {

    private final Binder binder;
    private final Map<String, JobSettings> cache =
            new ConcurrentHashMap<>();

    public JobSettingsFactory(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public JobSettings get(String jobType) {
        if (!jobType.equals("mail") && !jobType.equals("index")) {
            throw new IllegalArgumentException("Unsupported job type");
        }
        return cache.computeIfAbsent(jobType, this::load);
    }

    private JobSettings load(String jobType) {
        String prefix = "app.jobs." + jobType;
        return binder.bind(prefix, JobSettings.class)
                .orElseThrow(() ->
                        new IllegalStateException("Missing " + prefix));
    }
}
~~~

Record:

~~~java
public record JobSettings(int concurrency, boolean enabled) {}
~~~

Meaning:

- The prefix belongs to an allowed set.
- Binder reads on demand the first time a job type is needed.
- The factory caches the result so it does not rebind on every request.
- Subsequent calls receive the same object.

**Consideration:** if configuration is refreshed at runtime, this cache will retain the old snapshot until the application actively invalidates/replaces it. A cache is not a refresh mechanism.

### 25.1. Validation must be part of loading

If concurrency must be greater than 0, the load method should validate before putting the object into the cache. A cached invalid entry can cause many tasks to use invalid values.

An invariant can be placed in the record:

~~~java
public record JobSettings(int concurrency, boolean enabled) {
    public JobSettings {
        if (concurrency < 1) {
            throw new IllegalArgumentException(
                    "job concurrency must be positive"
            );
        }
    }
}
~~~

Or invoke Jakarta Validation explicitly. Choose the approach that matches the scale of the configuration contract.

## 26. Using Binder to Build Multiple Distinct Clients

A typical scenario is configuring multiple outbound clients whose names are determined by modules:

~~~yaml
clients:
  catalog:
    endpoint: "https://catalog.example.test"
    timeout: 3s
  pricing:
    endpoint: "https://pricing.example.test"
    timeout: 6s
~~~

Record:

~~~java
public record HttpClientSettings(
        String endpoint,
        Duration timeout
) {}
~~~

Factory:

~~~java
public HttpClientSettings load(String clientName) {
    if (!Set.of("catalog", "pricing").contains(clientName)) {
        throw new IllegalArgumentException("Unknown client");
    }

    return binder
            .bind("clients." + clientName, HttpClientSettings.class)
            .orElseThrow();
}
~~~

This reuses the same data type across multiple prefixes.

If all clients are known at startup and startup should fail if any client is misconfigured, a **@ConfigurationProperties(prefix="clients")** bean with **Map<String, HttpClientSettings>** combined with validation is usually easier to maintain.

## 27. Programmatic Binding for Configuration Outside Spring Environment

Some libraries receive Map-based configurations or custom PropertySources and need shared converters/binding instead of writing custom parsers.

For example, a source from a file or API that has been **read and verified by application code** and converted into Map<String, Object>. It can be wrapped in MapConfigurationPropertySource and bound by prefix:

~~~java
Map<String, Object> values = Map.of(
        "engine.pool.size", "16",
        "engine.pool.idle-timeout", "30s"
);

Binder binder = new Binder(
        new MapConfigurationPropertySource(values)
);

EngineSettings engine = binder
        .bind("engine.pool", EngineSettings.class)
        .orElseThrow();
~~~

Record:

~~~java
public record EngineSettings(int size, Duration idleTimeout) {}
~~~

**Benefit:** the same nested binding/conversion mechanism as standard configurations without stuffing everything into the global Environment.

**Limitation:** no built-in profile handling, Config Data imports, CLI precedence, or bean lifecycle. Those only exist if the surrounding sources and infrastructure are appropriately integrated.

### 27.1. Binder is not a client for querying remote config services

If config resides in a database or HTTP API, Binder does not connect to or fetch that data itself. The application or framework must load the data and turn it into an appropriate ConfigurationPropertySource/Environment before binding.

Do not use Binder as a direct replacement for a secret management system, config server, or remote data caching.

## 28. Risks When Manually Mixing Multiple Configuration Sources

If you construct a Binder with multiple ConfigurationPropertySources, **the order of sources** becomes the code's responsibility. A mistake can let a default source beat an override source or produce results different from Spring Environment.

When the goal is "read just like the running application", you should usually do:

~~~java
Binder binder = Binder.get(environment);
~~~

instead of manually assembling the source list.

For isolated unit tests, using a single MapConfigurationPropertySource is sufficient. Do not use a single-Map test result to claim that full precedence across application.yml, env, and CLI has been verified.

## 29. When Must You Use @ConfigurationProperties Despite Having Binder?

Cases where @ConfigurationProperties should be preferred:

### 29.1. Stable configuration known at build time

Example:

~~~yaml
app:
  email:
    sender: "noreply@example.test"
    retries: 3
~~~

An EmailProperties bean is easier to understand than an EmailConfigReader calling Binder in multiple services.

### 29.2. Centralized validation and fail-fast needed

If URLs, passwords, timeouts, and pool sizes must be valid before the system accepts requests, @ConfigurationProperties with @Validated is the standard, easy-to-explain path.

### 29.3. IDE metadata and configuration documentation needed

Configurations using @ConfigurationProperties are supported by the metadata processor tool, depending on the build setup. This provides property suggestions, descriptions, types, and typo detection in the IDE.

A Binder call built from a dynamic prefix does not automatically get the same metadata. If Binder is used for a multi-module library, you may need to write schema documentation and custom validation tooling.

### 29.4. Injecting the same snapshot into multiple services

A single immutable configuration bean injected into multiple services is easier to test and avoids redundant binding.

### 29.5. Simple management and operational workflow

Programmatic binding adds logic to maintain: prefixes, error handling, validation, caching, and lifecycle. If annotations solve the problem cleanly, the extra logic can be unnecessary overhead.

## 30. When Is Programmatic Binding Truly Worth It?

| Situation | Reason Binder may be useful |
| --- | --- |
| Prefix chosen at runtime from an allowed set | bind("clients." + name, Type.class) |
| Only certain modules are activated | Bind according to module needs |
| Same configuration shape has multiple independent prefixes | Reuse record/class |
| Building a framework/plugin loader | Factory controls target type, prefix, and bind timing |
| Need to handle a completely absent prefix | Clear BindResult and Optional/fallback |
| Need isolated binder tests without starting Spring context | MapConfigurationPropertySource |
| Need to bind a library-provided class | No need to modify class to add @ConfigurationProperties |
| Need advanced BindHandler/conversion control | Use corresponding overloads/extension points |
| Need to update a prepared mutable bean | Bindable.ofInstance when appropriate |
| Bind config produced from a normalized source outside Environment | Create a dedicated ConfigurationPropertySource |

**Common thread:** the caller has a practical reason to control the binding process. Otherwise, use annotations.

## 31. Programmatic Binding Is Not Always Good for Multi-Tenancy

Multi-tenancy is an often-cited example, yet it is also easily overused.

If tenant information comes from a **database and changes continuously**, with each request needing tenant-specific settings, Binder from Environment may not fit because Environment is not a per-request database query.

If a set of tenants' configurations is declared in Config Data:

~~~yaml
app:
  tenants:
    alpha:
      timeout: 3s
    beta:
      timeout: 5s
~~~

there are two reasonable approaches:

**Approach A — bind a Map at startup:**

~~~java
@ConfigurationProperties(prefix = "app")
public record TenantProperties(Map<String, TenantSettings> tenants) {}
~~~

**Approach B — bind prefix on demand:**

~~~java
binder.bind("app.tenants." + tenantName, TenantSettings.class)
~~~

Approach B is only suitable when tenantName is checked against an allowlist and lazy reading brings clear benefits. If tenant keys contain dots or special characters, simple prefix concatenation also risks malformed paths; a Map design with bracket notation and naming constraints may be more appropriate.

**Binder does not perform access control checks between tenants.** Configuration results must be protected and never returned verbatim in public APIs.

## 32. Missing, Empty, and Null Configuration

With Binder:

~~~java
var result = binder.bind("app.client", ClientProperties.class);
~~~

do not conflate these states:

- No properties under the prefix.
- Prefix exists, but only some fields are present.
- A String field with an empty value.
- A YAML null value.
- A mistyped value such as retries="abc".

Some cases can produce an object with null/default fields; some can be unbound; some throw conversion errors. The outcome depends on the target type, constructor, source, and binding strategy.

**Clear design:** use validation or constructor invariants to reject half-populated objects; only use BindResult.orElse when the entire group is allowed not to exist.

### 32.1. Do not use BindResult to check every field

BindResult.isBound() is not an **isValid()** check for the whole object. It answers whether a binding result exists; business constraints must be checked separately.

If an endpoint must be non-blank:

~~~java
public record ClientProperties(String endpoint) {
    public ClientProperties {
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException(
                    "app.client.endpoint must not be blank"
            );
        }
    }
}
~~~

Or use Bean Validation after binding.

## 33. Spring Profiles and Code-Driven Binding

Example:

~~~yaml
# application.yml
app:
  client:
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 10s
~~~

If the prod profile is active, Binder from Spring Environment can receive timeout=10s, following normal Config Data precedence.

~~~java
ClientProperties settings = Binder.get(environment)
        .bind("app.client", ClientProperties.class)
        .orElseThrow();
~~~

Selecting a prefix in code **does not bypass profiles**. Conversely, if the caller builds a Binder from a standalone MapConfigurationPropertySource containing only timeout=3s, it will not know about the prod profile.

### 33.1. Do not manually merge config files by profile

Do not use the Binder API as an excuse to manually read application.yml and application-prod.yml with a custom parser and merge Maps in an invented order. Spring Boot Config Data already defines rules for profiles, location groups, and imports. When you want the same behavior as Boot, use the initialized Spring Environment.

## 34. Environment Variables and Relaxed Binding

Canonical path:

~~~text
app.client.read-timeout
~~~

The environment variable name is converted using the standard rules:

~~~text
APP_CLIENT_READTIMEOUT
~~~

Three steps:

1. Dots become underscores.
2. Remove hyphens.
3. Convert letters to uppercase.

Example:

~~~bash
APP_CLIENT_READTIMEOUT=12s java -jar demo.jar
~~~

Binder from Spring Environment can bind this value to the **readTimeout** field in the target class.

The name **APP_CLIENT_READ_TIMEOUT** is not the standard conversion of **app.client.read-timeout**, because hyphens are removed rather than turned into underscores.

Programmatic binding does not alter naming rules. For predictable results, use canonical prefixes and document the standard env var names.

## 35. Sensitive Data Considerations

A Binder can generally read any configuration present in the provided sources. Therefore, avoid:

- Exposing a public endpoint that accepts a prefix and returns the configuration object.
- Printing an entire BindResult, record, or Map if it contains passwords/tokens.
- Concatenating a prefix from an arbitrary tenantId without an allowlist.
- Adding debug logs that dump every key/value in Environment.
- Using a custom handler that writes raw values into logs.
- Including secrets in exception messages.

If diagnostics are needed, log **safe property names**, module names, error types, and a correlation ID; never log secret values.

Programmatic binding must also respect authorization boundaries between modules/tenants. Just because data exists in Environment does not automatically allow every piece of code or request to read it.

## 36. Using Binder in Unit Tests

A plain Java test:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class HttpBinderTest {

    @Test
    void bindsNestedProperties() {
        Map<String, Object> config = Map.of(
                "app.http.connect-timeout", "2s",
                "app.http.read-timeout", "8s",
                "app.http.max-connections", "25"
        );

        Binder binder = new Binder(
                new MapConfigurationPropertySource(config)
        );

        HttpSettings result = binder
                .bind("app.http", HttpSettings.class)
                .orElseThrow();

        assertThat(result.maxConnections()).isEqualTo(25);
        assertThat(result.readTimeout())
                .isEqualTo(Duration.ofSeconds(8));
    }
}
~~~

This test verifies:

- Correct property paths.
- Appropriate Java types.
- Duration conversion.
- Nested naming if nested records are added.

It does not verify:

- The application's actual Spring profiles.
- Validation triggered via @ConfigurationProperties.
- Precedence between env and CLI.
- Whether beans are scanned/injected.

Each kind of test has its own goal.

## 37. Testing Missing and Wrong-Type Cases

Example with entire prefix missing:

~~~java
Binder binder = new Binder(
        new MapConfigurationPropertySource(
                Map.of("unrelated.value", "x")
        )
);

var result = binder.bind("app.http", HttpSettings.class);

assertThat(result.isBound()).isFalse();
~~~

Example with wrong type:

~~~java
Map<String, Object> config = Map.of(
        "app.http.max-connections", "many"
);
~~~

If the record expects **int maxConnections**, binding may throw a conversion error. In tests, assert the appropriate error and offending property rather than catching all Exceptions and treating that as success.

### 37.1. Testing validation separately

If a record has Jakarta Validation constraints, test the bind method followed by **validator.validate(result)**. This proves the program has a data validation path even when not going through @ConfigurationProperties auto-binding.

### 37.2. Testing runtime integration

If the program uses Binder.get(environment) and depends on profiles, Config Data imports, or command-line overrides, use **ApplicationContextRunner**, **@SpringBootTest**, or an appropriate startup integration test. Unit tests with standalone Maps are necessary, but not sufficient for precedence.

## 38. When You Need to Read a Configuration Group Without Creating a Bean Yet

In some utilities/bootstrap modules, code needs a transient configuration object without placing it into ApplicationContext as a singleton bean:

~~~java
public static HttpSettings fromEnvironment(Environment environment) {
    return Binder.get(environment)
            .bind("app.http", HttpSettings.class)
            .orElseThrow();
}
~~~

Advantage: clearly named method, easy to call, no need to create a separate configuration bean just to hold the object.

Limitation: the caller must decide lifecycle and validation. If multiple services call this method, there is a risk of repeated binding and each service receiving a different instance. Once requirements stabilize, consider creating a unified configuration bean.

## 39. Do Not Forget Metadata and IDE Support

When using:

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(Duration timeout, int maxConnections) {}
~~~

the configuration processor tool can generate property metadata for IDEs, documentation, and autocomplete support.

If all configuration is read via:

~~~java
binder.bind(dynamicPrefix, DynamicSettings.class)
~~~

the actual prefixes/paths may not be known to static analyzers. This increases the need to document manually:

- Valid prefixes.
- Required properties.
- Data types and units.
- Default values.
- Corresponding env var names.
- Error handling policies.
- Relationships across modules.

**Runtime flexibility comes with a tooling cost.** This is an important factor when choosing between annotations and programmatic binding.

## 40. Hybrid Architecture: Annotations for Stable Parts, Binder for Dynamic Parts

You do not have to choose "100% annotation" or "100% programmatic".

For example, an application has:

~~~yaml
app:
  service:
    name: orders
    enabled: true
  integrations:
    catalog:
      timeout: 3s
    billing:
      timeout: 8s
~~~

You can use @ConfigurationProperties for service configuration:

~~~java
@ConfigurationProperties(prefix = "app.service")
public record ServiceProperties(String name, boolean enabled) {}
~~~

and use Binder only in the integration factory that needs prefix selection:

~~~java
public IntegrationSettings readIntegration(String name) {
    String prefix = switch (name) {
        case "catalog" -> "app.integrations.catalog";
        case "billing" -> "app.integrations.billing";
        default -> throw new IllegalArgumentException(
                "Unknown integration"
        );
    };

    return binder
            .bind(prefix, IntegrationSettings.class)
            .orElseThrow();
}
~~~

This hybrid model keeps **stable data paths as beans with validation/metadata**, while Binder is used precisely where dynamism is genuinely needed.

### 40.1. Do not let multiple components "own" the same prefix

If both ServiceProperties and IntegrationFactory independently process the same prefix with different defaults/validations, two different interpretations can appear in one application.

Clearly demarcate which prefixes belong to standard configuration beans and which belong to dynamic factories, and document this in the corresponding module.

## 41. Quick Selection Table

| Question | If "Yes" | Approach to consider |
| --- | --- | --- |
| Fixed prefix and schema? | Yes | @ConfigurationProperties |
| Need a shared bean across multiple services? | Yes | @ConfigurationProperties |
| Need automatic startup validation/fail-fast? | Yes | @ConfigurationProperties + @Validated |
| Need to pick prefix from a set of names at runtime? | Yes | Binder |
| Only want to bind when a module is used? | Yes | Binder with clear lifecycle |
| Need to read configs of plugins with different target types? | Yes | Binder inside plugin factory |
| Need to bind an isolated test Map? | Yes | MapConfigurationPropertySource + Binder |
| Only need a single String/int scalar? | Yes | Environment or @Value |
| Need a typed List/Map at a prefix? | Yes | Binder + Bindable or @ConfigurationProperties |
| Need secret protection / tenant isolation? | Yes | Authorization/secret policy outside Binder |
| Configuration hot-changes continuously? | Yes | Consider separate refresh/state mechanism; Binder is not enough |
| Need full property autocomplete? | Yes | Prefer @ConfigurationProperties metadata |
| Clear reason to handle bind events/errors? | Yes | Scoped BindHandler |

## 42. Common Mistakes

### 42.1. Using Binder just to avoid writing annotations

A class with a fixed prefix is used in five services, and each service calls Binder itself. The result is duplicated code and inconsistent defaults and validation.

**Solution:** create a @ConfigurationProperties bean and inject it.

### 42.2. Ignoring conversion errors

~~~java
try {
    return binder.bind("app.pool", PoolSettings.class).orElse(null);
} catch (Exception ex) {
    return null;
}
~~~

An invalid value can be turned into "no configuration". **Solution:** treat unbound as optional only when the design permits; report errors for invalid data.

### 42.3. Uncontrolled prefix concatenation from requests

~~~java
binder.bind("app.tenants." + request.getParameter("tenant"), Type.class)
~~~

This is not automatically a secure multi-tenant architecture. **Solution:** validate the tenant, enforce an allowlist/access control, canonicalize keys, and avoid returning sensitive data.

### 42.4. Treating @Validated on a record as automatic validation for all Binder calls

Programmatic binding can bypass the validation integration layer used by @ConfigurationProperties. **Solution:** invoke a validator after binding or configure a validation handler via the appropriate API.

### 42.5. Calling Binder on every request unnecessarily

Stable config is repeatedly converted, making code slower and harder to test. **Solution:** create a bean/snapshot or explicit cache.

### 42.6. Using Binder with a standalone Map source and expecting it to read application.yml

MapConfigurationPropertySource only contains the keys provided to it. **Solution:** use Binder.get(environment) if you want to read the actual Spring Boot source hierarchy.

### 42.7. Expecting BindResult.orElse to handle all missing fields

An object can be bound even if some fields remain null/0. **Solution:** per-field defaults or validation; do not use object-level orElse as validation.

### 42.8. Misunderstanding List replacement

If the base file has two servers and the prod file has one server, binder may take the list from the prod file. This is precedence, not the Binder API "missing items". **Solution:** declare the full List in the overriding source.

### 42.9. Logging entire configuration objects containing secrets

Record toString may contain passwords/tokens. **Solution:** log non-sensitive keys/paths, apply masking, and do not expose BindResult in APIs.

### 42.10. Expecting Binder to automatically refresh already-created beans

A previously bound object remains the old Java object. **Solution:** define a reload and snapshot-replacement mechanism, or restart the application when configuration changes.

## 43. Exercise 1: Choosing the Right Tool

Consider four requirements:

**A.** The app has fixed properties app.mail.sender and app.mail.retries, used in many services, and needs fail-fast.

**B.** A plugin manager selects prefix **plugins.email** or **plugins.audit** when initializing a plugin.

**C.** A controller only needs to read **server.port**.

**D.** A unit test wants to convert a Map with keys app.pool.max-size and app.pool.enabled into PoolSettings without starting a Spring context.

Suggestions:

- A → **@ConfigurationProperties**, with validation added.
- B → **Binder API** inside the plugin manager.
- C → **Environment.getProperty(...)** or @Value.
- D → **new Binder(new MapConfigurationPropertySource(map))**.

The reason for choosing ties to the requirement, not one API being "newer" than another.

## 44. Exercise 2: Dynamic Prefix

YAML:

~~~yaml
gateways:
  bank-a:
    endpoint: "https://bank-a.example.test"
    timeout: 3s
  bank-b:
    endpoint: "https://bank-b.example.test"
    timeout: 6s
~~~

Record:

~~~java
public record GatewaySettings(String endpoint, Duration timeout) {}
~~~

Write a method **readGateway(String name)** that only accepts **bank-a** and **bank-b**, and uses Binder to bind the corresponding prefix.

Suggested solution:

~~~java
public GatewaySettings readGateway(String name) {
    if (!Set.of("bank-a", "bank-b").contains(name)) {
        throw new IllegalArgumentException("Unknown gateway");
    }

    return binder
            .bind("gateways." + name, GatewaySettings.class)
            .orElseThrow();
}
~~~

**Extension:** if gateway names are dynamic Map keys, consider a Map model instead of manually concatenating prefixes.

## 45. Exercise 3: Binding a Typed List

YAML:

~~~yaml
jobs:
  scheduled:
    - name: cleanup
      interval: 1h
    - name: backup
      interval: 12h
~~~

Record:

~~~java
public record ScheduledJob(String name, Duration interval) {}
~~~

Code:

~~~java
List<ScheduledJob> jobs = Binder.get(environment)
        .bind(
                "jobs.scheduled",
                Bindable.listOf(ScheduledJob.class)
        )
        .orElse(List.of());
~~~

Explain why Bindable.listOf(ScheduledJob.class) is advantageous over binding with List.class: it provides the **element type**, allowing binder to convert each item into ScheduledJob.

## 46. Exercise 4: Distinguishing Absent Config from Invalid Config

Source A:

~~~properties
# No app.pool.* keys
~~~

Source B:

~~~properties
app.pool.max-size=many
~~~

Record:

~~~java
public record PoolSettings(int maxSize) {}
~~~

Call:

~~~java
var result = binder.bind("app.pool", PoolSettings.class);
~~~

**Source A** can produce unbound; the caller is allowed to fall back if the contract permits.

**Source B** can cause a type conversion error to int; do not silently turn it into unbound. If max-size must be valid, the application needs to detect and report the specific error.

## 47. Exercise 5: Validation

Record:

~~~java
public record HttpSettings(
        @jakarta.validation.constraints.Min(1) int maxConnections
) {}
~~~

Configuration:

~~~properties
app.http.max-connections=0
~~~

Binder can bind the int value 0, because it is a valid number for type conversion. However, the configuration **violates @Min(1)**.

Question: how do you ensure an object created by programmatic binding is validated?

Hint: invoke a **Jakarta Validator** on the bound object or integrate an appropriate validation handler. Do not just put @Validated on the record and assume a standard Binder call has the exact same validation mechanism as a configuration bean.

## 48. Exercise 6: Refactoring Repeated Binding Architecture

Initial code:

~~~java
@Service
class CheckoutService {
    private final Environment environment;

    CheckoutService(Environment environment) {
        this.environment = environment;
    }

    int retries() {
        return Binder.get(environment)
                .bind("app.checkout.retries", Integer.class)
                .orElse(3);
    }
}
~~~

If retries is fixed throughout the application lifecycle and used across multiple services, refactor:

~~~java
@ConfigurationProperties(prefix = "app.checkout")
public record CheckoutProperties(int retries) {}
~~~

Then inject CheckoutProperties. Using a configuration bean simplifies testing and centralizes defaults/validation, avoiding unnecessary repeated Binder calls.

## 49. Implementation Checklist

When deciding to use programmatic binding, verify:

1. **Is there a genuine reason** not to use @ConfigurationProperties?
2. **Is the source** the current Spring Environment or a dedicated ConfigurationPropertySource?
3. **Is the prefix** fixed or dynamic? If dynamic, where is the allowed prefix set defined?
4. **Is the target type** a scalar, record, JavaBean, List, or Map?
5. **Are generic types** preserved with Bindable?
6. **When data is absent**, should the caller return Optional, fall back, or throw an error?
7. **When data has the wrong type**, is the error clearly reported rather than swallowed?
8. **Where is validation** executed, including nested Lists/Maps?
9. **Is binding timed** at startup, first use, or every request?
10. **Is the result cached**, and what is the refresh strategy if sources change?
11. **Is PropertySource precedence** preserved as required?
12. **Are canonical names and env vars** properly documented?
13. **Is there any secret/tenant config leakage** via logs, exceptions, or APIs?
14. **Do tests** cover bound, unbound, invalid, and overriding sources?
15. **Do IDE/metadata tools** need extra documentation when annotations are not used?

If you cannot answer these questions clearly, a @ConfigurationProperties bean may be a more maintainable design.

## 50. Key Takeaways

- **@ConfigurationProperties** should be the default choice for a stable configuration group reused via dependency injection, with validation and metadata aligned with the application lifecycle.
- **Binder API** fits when code must control the **prefix, target type, binding timing, data source, or result handling**.
- **Binder.get(environment)** uses existing PropertySources in Spring Environment, along with the same precedence system used by the application.
- **bind(prefix, Class<T>)** suits a concrete target type; **Bindable** helps describe Lists, Maps, and targets needing detailed type information.
- **BindResult.isBound()** distinguishes presence/absence of a result; it **is not a validity check** and does not turn conversion errors into default values.
- **@Validated in the annotation model does not mean programmatic binding automatically validates like a @ConfigurationProperties bean**. When needed, explicitly use Validator or a validation-integrated BindHandler.
- **MapConfigurationPropertySource** is useful for testing or binding isolated data; it does not automatically read all existing application configurations.
- **Programmatic binding does not solve runtime refresh, authorization, secret management, or caching**. These remain architectural responsibilities of the system.
- **List/Map, relaxed names, profiles, and precedence** remain governed by binder/externalized configuration rules; changing the API does not change the meaning of configuration.
- A balanced design can use **annotations for static parts** and the **Binder API right where dynamism is needed**.

The best decision question is not "does annotation or Binder take less code?", but rather: **"Who needs to control the timing and scope of binding?"**. If Spring Boot can create a standard configuration bean at startup, use @ConfigurationProperties. If a module must select prefixes/source types at runtime and handle results per its own contract, programmatic binding is the right tool—provided errors, validation, security, and lifecycle are designed clearly.
