# Preserving Generic Type Information with `Bindable` in Spring Boot

## 1. Context: Binding One Value Is Easy, Binding Generic Types Is Hard

Spring Boot supports **externalized configuration**: settings from `application.yml`, `application.properties`, environment variables, Java system properties, and other sources are aggregated into `Environment`. For a single value, Java code can use:

~~~java
String region = environment.getProperty("app.region");
Integer port = environment.getProperty("server.port", Integer.class);
~~~

However, when the application needs to read a structure like `List<Endpoint>`, `Map<String, Duration>`, or `List<Map<String, RetryPolicy>>`, passing only `List.class` or `Map.class` **cannot fully represent the element types**. These classes do not carry `Endpoint`, `Duration`, or `RetryPolicy` as a separate `Class`.

Spring Boot provides two components in the `org.springframework.boot.context.properties.bind` package:

- **`Binder`**: reads configuration sources and performs binding into Java types.
- **`Bindable<T>`**: describes the **target to bind**: the target type (including generic information), associated annotations, and in some cases an existing value.

Short example:

~~~java
List<String> servers = Binder.get(environment)
    .bind("app.servers", Bindable.listOf(String.class))
    .orElseGet(List::of);
~~~

Here `Bindable.listOf(String.class)` explicitly states the target is **`List<String>`**, rather than a raw `List` with an unknown element type.

> Key idea: `Bindable` is not a list holding configuration data. It is a **type and binding-context descriptor** so `Binder` knows what Java type to construct.

## 2. Reviewing Java Generics and Type Erasure

When declaring:

~~~java
List<String> names;
List<Integer> ports;
List<Endpoint> endpoints;
~~~

The Java compiler has generic information to type-check the program. At runtime, however, using `List.class` does not preserve three distinct types:

~~~java
Class<?> raw = List.class;
~~~

There is no valid Java syntax for:

~~~java
// Invalid: there is no List<String>.class
// Class<List<String>> type = List<String>.class;
~~~

This is a consequence of **type erasure**: a runtime `Class` for the raw `List` type is insufficient to describe concrete elements.

If you only call:

~~~java
binder.bind("app.servers", List.class);
~~~

the binding target is a raw list. The result may lack information for binder to convert each element to `String`, `Duration`, or a nested object as intended. A cast like the following does not restore generic metadata:

~~~java
// Do not do this: casting only silences the compiler;
// it does not tell Binder which element type to create.
@SuppressWarnings("unchecked")
List<Endpoint> endpoints =
    (List<Endpoint>) (List<?>) binder.bind("app.endpoints", List.class).get();
~~~

For a list of objects, the code above risks receiving elements of an unintended type and failing when accessed.

**Solution:** pass a `Bindable<List<Endpoint>>` carrying type information to `Binder`.

## 3. Related APIs and How They Work Together

Common imports:

~~~java
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.core.ResolvableType;

import java.util.List;
import java.util.Map;
import java.util.Set;
~~~

In Spring Boot 3.x:

~~~java
Binder binder = Binder.get(environment);
~~~

Creates a binder from the current `Environment`. Some methods:

~~~java
BindResult<String> a =
    binder.bind("app.region", String.class);

BindResult<List<String>> b =
    binder.bind("app.servers", Bindable.listOf(String.class));

BindResult<Map<String, Integer>> c =
    binder.bind("app.limits", Bindable.mapOf(String.class, Integer.class));
~~~

Role table:

| Component | Role |
| --- | --- |
| `Environment` | Collection of configuration sources and precedence rules |
| `Binder` | Coordinates reading configuration, conversion, and binding to objects |
| `Bindable<T>` | Provides exact target type description and binding context |
| `ResolvableType` | Represents types with generic arguments, including multi-level nesting |
| `BindResult<T>` | Binding result indicating presence/absence, supporting value retrieval or fallback |
| `@ConfigurationProperties` | Declarative mechanism automatically integrated into the lifecycle by Spring Boot |

These APIs are not mutually exclusive. `@ConfigurationProperties` uses Spring Boot's binding mechanism; code calling `Binder` directly is the **manual, programmatic** access approach when you need to bind a prefix at specific times or dynamic generic structures.

## 4. First Example: `List<String>`

`application.yml` file:

~~~yaml
app:
  servers:
    - alpha.example.test
    - beta.example.test
    - gamma.example.test
~~~

If you need to retrieve a list directly inside a component:

~~~java
package com.example.service;

import java.util.List;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class ServerDirectory {
    private final List<String> servers;

    public ServerDirectory(Environment environment) {
        this.servers = Binder.get(environment)
            .bind("app.servers", Bindable.listOf(String.class))
            .orElseGet(List::of);
    }

    public List<String> servers() {
        return servers;
    }
}
~~~

When the list is declared as in the YAML above:

~~~text
servers[0] = alpha.example.test
servers[1] = beta.example.test
servers[2] = gamma.example.test
~~~

If `app.servers` is absent, `BindResult.orElseGet(List::of)` supplies an empty list **by the code's choice**. This differs from binder defaulting every list to empty automatically.

### 4.1. Same data in Properties format

~~~properties
app.servers[0]=alpha.example.test
app.servers[1]=beta.example.test
app.servers[2]=gamma.example.test
~~~

`Bindable.listOf(String.class)` is still the right target. Java code does not need to know whether the values came from YAML or Properties; binder reads through the configuration property sources.

### 4.2. Why not call `getProperty("app.servers")`?

`Environment.getProperty(...)` is useful for a single property, whereas a YAML list is typically flattened into keys like `app.servers[0]` and `app.servers[1]`. You cannot assume a single `app.servers` string holds the entire list in the format you want to parse.

`Binder` understands indexed structures and collection conversion. When configuration represents a List, it is a better choice than manually parsing keys as strings.

## 5. `List<Endpoint>`: Where `Bindable` Truly Shines

Suppose an application has a list of endpoints with name, URL, and timeout.

`application.yml`:

~~~yaml
app:
  endpoints:
    - name: catalog
      url: https://catalog.example.test
      timeout: 3s
    - name: inventory
      url: https://inventory.example.test
      timeout: 5s
~~~

Using a Java record in Java 17+:

~~~java
package com.example.config;

import java.time.Duration;

public record Endpoint(
        String name,
        String url,
        Duration timeout) {
}
~~~

Reading directly with Binder:

~~~java
package com.example.service;

import java.util.List;

import com.example.config.Endpoint;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public class EndpointLoader {

    public static List<Endpoint> load(Environment environment) {
        Binder binder = Binder.get(environment);

        return binder
            .bind("app.endpoints", Bindable.listOf(Endpoint.class))
            .orElseGet(List::of);
    }
}
~~~

`Bindable.listOf(Endpoint.class)` not only describes `List`, it also ensures binder knows **the element type is `Endpoint`**. With Spring Boot 3.x supporting record constructor binding, it can convert `3s` to `Duration` and construct the corresponding records.

Logical result:

~~~text
[
  Endpoint("catalog", "https://catalog.example.test", PT3S),
  Endpoint("inventory", "https://inventory.example.test", PT5S)
]
~~~

No need to manually read:

~~~java
environment.getProperty("app.endpoints[0].name");
environment.getProperty("app.endpoints[0].url");
environment.getProperty("app.endpoints[0].timeout");
~~~

then loop over indices and convert types manually. When lists are long or have nested fields, manual handling is very error-prone.

### 5.1. Model requirements

The element type must have an appropriate creation/binding mechanism, such as:

- A JavaBean with a no-arg constructor and getters/setters.
- An immutable class with appropriate constructor binding.
- A record with a canonical constructor as shown in the example.

`Bindable.listOf(Endpoint.class)` **does not magically add constructors/setters** to a class that does not support binding. If the type belongs to an external library and cannot be bound directly, use an intermediate application configuration class and build the vendor object from that data.

## 6. `Set<T>`: Preserving the Element Type of a Set

`Bindable` also provides a factory for Set:

~~~java
Set<String> roles = Binder.get(environment)
    .bind("app.allowed-roles", Bindable.setOf(String.class))
    .orElseGet(Set::of);
~~~

Configuration example:

~~~yaml
app:
  allowed-roles:
    - viewer
    - editor
    - auditor
~~~

`Set<String>` represents a set of values, appropriate when the application cares about **uniqueness** rather than index order. If you need an exact order for failover attempts or sequential steps, `List` expresses intent more clearly.

Whether using `Set` or `List`, elements in configuration still need to be convertible to type `T`. For example, `Bindable.setOf(Integer.class)` tells binder each element must be an `Integer`, not an unconverted string.

## 7. `Map<K,V>`: Preserving Both Key and Value Types

Suppose the application needs retry limits per service:

~~~yaml
app:
  retry-limits:
    catalog: 2
    inventory: 4
    billing: 1
~~~

Java target:

~~~java
Map<String, Integer> retryLimits = Binder.get(environment)
    .bind(
        "app.retry-limits",
        Bindable.mapOf(String.class, Integer.class))
    .orElseGet(Map::of);
~~~

Preserved type information:

~~~text
Map
 ├─ K = String
 └─ V = Integer
~~~

Binder knows to convert `2`, `4`, `1` to `Integer`. If a value is the text `"many"`, binding to `Integer` can fail; `Bindable` cannot turn mistyped input into a valid number.

### 7.1. Map with object values

Using the same `Endpoint` record, identifying endpoints by map keys:

~~~yaml
app:
  endpoints-by-name:
    catalog:
      name: catalog
      url: https://catalog.example.test
      timeout: 3s
    inventory:
      name: inventory
      url: https://inventory.example.test
      timeout: 5s
~~~

Bind:

~~~java
Map<String, Endpoint> endpoints = Binder.get(environment)
    .bind(
        "app.endpoints-by-name",
        Bindable.mapOf(String.class, Endpoint.class))
    .orElseGet(Map::of);
~~~

Then `endpoints.get("catalog")` returns an `Endpoint` with converted fields.

Difference from List: `catalog` and `inventory` are **meaningful keys**, whereas List identifies elements by index. This affects how Spring Boot binds configuration from **multiple sources**: a Map can merge keys, while a List is replaced wholesale by a higher-precedence source.

### 7.2. When keys are a type other than `String`

`Bindable.mapOf(Integer.class, String.class)` also expresses concrete key/value types:

~~~java
Map<Integer, String> labels = Binder.get(environment)
    .bind(
        "app.port-labels",
        Bindable.mapOf(Integer.class, String.class))
    .orElseGet(Map::of);
~~~

However, do not assume **every** YAML key form or special character will convert the same way for every map key type. Keys with dots, slashes, or brackets may require bracket notation per Spring Boot rules. For critical configurations, use simple keys, test binding thoroughly, and specify map key requirements clearly.

## 8. `Bindable` Factory Methods

Common ways to create a `Bindable`:

| Factory method | Type information captured | When to use |
| --- | --- | --- |
| `Bindable.of(String.class)` | `String` | Single value |
| `Bindable.of(Endpoint.class)` | `Endpoint` | Individual object |
| `Bindable.listOf(String.class)` | `List<String>` | List of strings |
| `Bindable.listOf(Endpoint.class)` | `List<Endpoint>` | List of objects |
| `Bindable.setOf(Integer.class)` | `Set<Integer>` | Set of numbers |
| `Bindable.mapOf(String.class, Integer.class)` | `Map<String,Integer>` | Map with simple key/value |
| `Bindable.mapOf(String.class, Endpoint.class)` | `Map<String,Endpoint>` | Map with object values |
| `Bindable.of(ResolvableType)` | Complex generic type expressed by `ResolvableType` | Nested structures |
| `Bindable.ofInstance(object)` | Type and existing instance value | Binding into an existing object |

Combined example:

~~~java
Binder binder = Binder.get(environment);

String region = binder
    .bind("app.region", Bindable.of(String.class))
    .orElse("vn");

List<String> servers = binder
    .bind("app.servers", Bindable.listOf(String.class))
    .orElseGet(List::of);

Map<String, Integer> limits = binder
    .bind("app.retry-limits",
          Bindable.mapOf(String.class, Integer.class))
    .orElseGet(Map::of);
~~~

`Binder.bind("app.region", String.class)` is also a convenient overload when you do not need to create a `Bindable` manually. But for collections with generic arguments, `Bindable.listOf/mapOf` expresses the target more clearly and provides better static typing.

## 9. Nested Generic Structures: `List<Map<String, RetryPolicy>>`

`listOf(Class<E>)` only accepts the `Class` of the immediate element. However, an element of a list can **itself be a generic type**:

~~~java
List<Map<String, RetryPolicy>>
~~~

Here there is no `Class<Map<String, RetryPolicy>>`. `Map.class` cannot represent `String` and `RetryPolicy`, so the entire type graph cannot be preserved with `listOf(Map.class)` alone.

Spring Framework provides `org.springframework.core.ResolvableType` to represent multi-level generic arguments.

### 9.1. Building nested `ResolvableType`

An example model:

~~~java
package com.example.config;

import java.time.Duration;

public record RetryPolicy(
        int attempts,
        Duration backoff) {
}
~~~

YAML:

~~~yaml
app:
  retry-groups:
    - catalog:
        attempts: 3
        backoff: 250ms
      inventory:
        attempts: 2
        backoff: 500ms
    - billing:
        attempts: 1
        backoff: 1s
~~~

Type declaration:

~~~java
import java.util.List;
import java.util.Map;

import com.example.config.RetryPolicy;
import org.springframework.core.ResolvableType;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;

ResolvableType mapType =
    ResolvableType.forClassWithGenerics(
        Map.class,
        ResolvableType.forClass(String.class),
        ResolvableType.forClass(RetryPolicy.class));

ResolvableType listType =
    ResolvableType.forClassWithGenerics(List.class, mapType);

Bindable<List<Map<String, RetryPolicy>>> target =
    Bindable.of(listType);

List<Map<String, RetryPolicy>> groups = binder
    .bind("app.retry-groups", target)
    .orElseGet(List::of);
~~~

Preserved type structure:

~~~text
List
 └─ Map
     ├─ K = String
     └─ V = RetryPolicy
          ├─ attempts: int
          └─ backoff: Duration
~~~

During binding, Spring Boot has enough information to create `RetryPolicy` and convert `250ms`, `500ms`, `1s` into `Duration` for each map value.

### 9.2. When are nested generics needed?

Not every application should model configuration as a List of Maps of objects. This structure is useful when data genuinely has multiple levels, though it increases complexity for YAML, validation, and testing.

If the data has a clear identity, a dedicated type such as:

~~~java
public record RetryGroup(Map<String, RetryPolicy> policies) {
}
~~~

can make the model easier to understand. Just because `ResolvableType` can express a generic type does not mean that model is optimal for the domain.

## 10. Preserving Type via a Declared `Field`

Java code may have a field containing the full generic type. `ResolvableType.forField(...)` reads generic information from the field declaration without manually assembling each level.

Example:

~~~java
package com.example.config;

import java.util.List;
import java.util.Map;

public final class RetryTypeHolder {
    // Field used as a type-metadata anchor for reference.
    private List<Map<String, RetryPolicy>> retryGroups;
}
~~~

Reading metadata and binding:

~~~java
import java.lang.reflect.Field;
import java.util.List;
import java.util.Map;

import org.springframework.core.ResolvableType;
import org.springframework.boot.context.properties.bind.Bindable;

Field field = RetryTypeHolder.class
    .getDeclaredField("retryGroups");

ResolvableType type = ResolvableType.forField(field);

Bindable<List<Map<String, RetryPolicy>>> target =
    Bindable.of(type);

List<Map<String, RetryPolicy>> groups = binder
    .bind("app.retry-groups", target)
    .orElseGet(List::of);
~~~

The snippet above needs to handle `NoSuchFieldException` or declare `throws` in the enclosing method. This illustrates **extracting metadata**, not advice to create unused fields in every project.

`ResolvableType.forField` reads the field's full generic declaration when that information exists in reflection metadata. This fits frameworks, libraries, or generic code that already have type declarations.

**Key takeaway:** type erasure does not mean all generic declarations disappear from metadata. Field declarations, parameters, and generic supertypes can provide enough information for `ResolvableType`; a bare `Class<List>` cannot.

## 11. Why `Bindable.of(List.class)` Is Not Equivalent to `Bindable.listOf(Endpoint.class)`

Consider two approaches:

~~~java
Bindable<List> rawTarget = Bindable.of(List.class);

Bindable<List<Endpoint>> typedTarget =
    Bindable.listOf(Endpoint.class);
~~~

The first only knows the collection type is `List`. The second knows **`List<Endpoint>`**. When configuration is a list of simple strings, raw list binding sometimes produces data that looks right; but when elements are objects with constructors, enums, `Duration`, or custom type converters, missing generic types can fail.

Common mistake:

~~~java
List raw = binder.bind("app.endpoints", List.class)
    .orElseGet(List::of);

// Assuming every element is already an Endpoint:
Endpoint first = (Endpoint) raw.get(0);
~~~

If elements are not actually `Endpoint`, casting can fail. A cast in application code **cannot instruct binder retroactively** after binding has finished.

Correct approach:

~~~java
List<Endpoint> endpoints = binder
    .bind("app.endpoints", Bindable.listOf(Endpoint.class))
    .orElseGet(List::of);
~~~

Now both the compiler and Binder have the proper type information. However, having the right type **does not automatically validate** URLs, positive timeouts, or business limits; validation still needs to be designed separately.

## 12. `BindResult<T>`: Retrieving Values, Checking Absence, and Fallbacks

`Binder.bind(...)` returns `BindResult<T>`, rather than always returning a `T` directly.

Example:

~~~java
BindResult<List<String>> result =
    binder.bind("app.servers", Bindable.listOf(String.class));
~~~

Usage:

~~~java
if (result.isBound()) {
    List<String> servers = result.get();
    // Use servers.
}
else {
    // No configuration was bound at this prefix.
}
~~~

Other options:

~~~java
List<String> servers =
    result.orElseGet(List::of);
~~~

or:

~~~java
List<String> defaultServers = List.of("localhost");
List<String> servers = result.orElse(defaultServers);
~~~

Separate three situations:

1. **No property to bind:** `isBound()` can be `false`, `orElse` provides a fallback.
2. **Property exists and converts successfully:** `isBound()` is `true`, `get()` yields the value.
3. **Property exists but cannot be converted/bound:** Binder may throw `BindException` or a related error; `orElse` **does not turn a mistyped configuration into a fallback**.

Example:

~~~properties
app.retry-limits.catalog=three
~~~

Binding `Map<String, Integer>` can fail when the converter encounters `three`. Do not write `orElse(Map.of())` expecting it to hide all configuration errors. Fallbacks are for **missing valid configuration**, not a mechanism to ignore invalid overrides.

### 12.1. When should you use `get()`?

`BindResult.get()` is appropriate when the result must definitely exist; if unbound, it reports a missing result. For optional configuration, `orElse` or `orElseGet` is clearer.

If the property is **business-required**, fail clearly:

~~~java
List<Endpoint> endpoints = binder
    .bind("app.endpoints", Bindable.listOf(Endpoint.class))
    .orElseThrow(() -> new IllegalStateException(
        "app.endpoints is required"));
~~~

The line above illustrates the fail-fast idea. When writing code against a specific version's `BindResult` API, use supported fallback methods; a universally viable approach is checking `isBound()` and throwing an application exception if needed.

## 13. `Bindable.ofInstance`: Pre-existing Target Objects

`Bindable` does not only describe a type for binder to instantiate. It can also attach an **existing value**:

~~~java
NodeSettings settings = new NodeSettings();

Bindable<NodeSettings> target =
    Bindable.ofInstance(settings);

NodeSettings bound = binder
    .bind("app.node", target)
    .orElse(settings);
~~~

With a JavaBean:

~~~java
package com.example.config;

public class NodeSettings {
    private String host;
    private int port = 8080;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }
}
~~~

YAML:

~~~yaml
app:
  node:
    host: node.example.test
    port: 9090
~~~

The target describes an existing instance that binder **can use as the current object**. This is particularly helpful with JavaBeans instantiated by another library, or when preserving object field initializers/defaults.

However, do not assume binder **always mutates the exact same reference in every case**. Binding behavior for objects, collections, immutable types, and constructor-bound values can differ; use the object returned from `BindResult` and test the behavior of the type you are using.

### 13.1. With generic collections, beware of instance metadata

~~~java
List<Endpoint> existing = new ArrayList<>();

// Do not assume inspecting the runtime Class of ArrayList
// reveals the generic element type Endpoint.
Bindable<List<Endpoint>> typed =
    Bindable.listOf(Endpoint.class).withExistingValue(existing);
~~~

`List<Endpoint>` has its generic type erased from the runtime class of an ordinary `ArrayList`. Thus `Bindable.ofInstance(existing)` may not know the exact element type from a plain collection instance unless type arguments are preserved in separate type metadata.

When you need both an existing value **and** element type information, starting from a generic-declared `Bindable` with `withExistingValue(...)` is clearer.

### 13.2. `withSuppliedValue`

Some Spring Boot versions support:

~~~java
Bindable<NodeSettings> target =
    Bindable.of(NodeSettings.class)
        .withSuppliedValue(NodeSettings::new);
~~~

This form supplies a `Supplier` to obtain/initialize the current object when binder needs it, instead of always passing an instance upfront. Exact usage details and when the supplier is invoked depend on the binding mechanism; do not rely on the supplier to perform I/O or side effects.

If you only need to construct an immutable object from config, you usually do not need an existing instance or supplier; `Bindable.of(Type.class)` or `Bindable.listOf(...)` is enough.

## 14. `Bindable.withAnnotations` and Metadata Affecting Conversion

Certain Spring Boot annotations can alter how a configuration value is interpreted, such as `@DurationUnit` and `@DataSizeUnit` for numbers without suffixes. `Bindable` can carry annotations attached to the target.

Imagine a timeout setting without a suffix that should default to seconds:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.convert.DurationUnit;

public class TimeoutHolder {
    @DurationUnit(ChronoUnit.SECONDS)
    private Duration timeout;
}
~~~

When a framework or reflection code reads annotation metadata from a field, it can build a `Bindable` with that metadata:

~~~java
import java.lang.reflect.Field;
import java.time.Duration;

import org.springframework.boot.context.properties.bind.Bindable;

Field field = TimeoutHolder.class.getDeclaredField("timeout");

Bindable<Duration> target = Bindable
    .of(Duration.class)
    .withAnnotations(field.getAnnotations());

Duration timeout = binder
    .bind("app.timeout", target)
    .orElse(Duration.ofSeconds(5));
~~~

The example needs to handle `NoSuchFieldException`; the relevant part is `withAnnotations(...)`.

Data:

~~~yaml
app:
  timeout: 10
~~~

With Spring Boot conversion honoring `@DurationUnit(SECONDS)`, the number `10` is interpreted as 10 seconds instead of the default 10 milliseconds. That is why `Bindable` sometimes needs not only the **target Class**, but also **annotation metadata** from the declaration site.

If dynamic binding is not truly needed, it is simpler to declare the property field directly in a `@ConfigurationProperties` class; Spring Boot reads the corresponding annotations without reflection code.

### 14.1. Annotations do not create a property source

`withAnnotations(...)` does not add configuration values to `Environment`, does not activate profiles, and does not alter source precedence. It supplies context for the binder/converter processing the **specified target**.

A unit annotation also **does not** create a fallback when a key is missing. The default unit of a provided value and the default value for an absent key are two different concerns.

## 15. Choosing `Bindable.of(Class)` or `Bindable.of(ResolvableType)`?

Quick rules:

- **Simple target:** use `Bindable.of(MyType.class)`, or pass `MyType.class` to `Binder.bind`.
- **List/Set with concrete class elements:** use `Bindable.listOf(Endpoint.class)` / `Bindable.setOf(String.class)`.
- **Map with concrete class key/value:** use `Bindable.mapOf(String.class, Endpoint.class)`.
- **Multi-level nested generics:** use `ResolvableType` then `Bindable.of(type)`.
- **Existing object or annotation metadata:** start from a Bindable with full type info, then add `withExistingValue` / `withAnnotations` as appropriate.

Another complex generic example:

~~~java
// Map<String, List<Integer>>
ResolvableType valueType =
    ResolvableType.forClassWithGenerics(
        List.class, ResolvableType.forClass(Integer.class));

ResolvableType mapType =
    ResolvableType.forClassWithGenerics(
        Map.class,
        ResolvableType.forClass(String.class),
        valueType);

Bindable<Map<String, List<Integer>>> target =
    Bindable.of(mapType);
~~~

With YAML:

~~~yaml
app:
  scores:
    alpha: [1, 2, 3]
    beta: [4, 5]
~~~

Binder has sufficient information to bind a `Map<String, List<Integer>>`. Having a YAML element that cannot be converted to a number, such as `"abc"`, remains a source data error rather than a reason to omit type metadata.

## 16. Differences Between Manual `Binder` and `@ConfigurationProperties`

In many projects, using `@ConfigurationProperties` is the standard choice for mapping long-lived configuration groups into a bean:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<Endpoint> endpoints,
        Map<String, Integer> retryLimits) {
}
~~~

Once the type is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(AppProperties.class)`, Spring Boot binds fields automatically using their generic declarations:

~~~java
private final AppProperties appProperties;

public SomeService(AppProperties appProperties) {
    this.appProperties = appProperties;
}
~~~

You **do not need** to call `Bindable.listOf` manually just to bind a `List<Endpoint>` field declared in a properties class.

Direct `Binder` code is suitable when:

1. The configuration prefix is chosen at runtime and not fixed in an annotation.
2. A library accepts a prefix name as a parameter and builds a Java structure at that path.
3. A small property group needs to be loaded independently of registering a Spring properties bean.
4. Building a configuration inspection tool or low-level binding test.
5. Passing a `ResolvableType` dynamically determined from a field, method, or generic signature.

**Do not** convert all project configuration properties into manual Binder calls; doing so forces you to handle lifecycle, validation, defaults, and configuration errors manually when Spring Boot already provides built-in mechanisms.

### 16.1. Manual Binder does not automatically equal the full auto-configuration pipeline

`Binder.get(environment)` creates a binder from environment. However, special cases like custom conversion services, bind handlers, integrated validation, or specialized metadata can depend on how Binder is initialized and configured.

Therefore, a manual Binder call **does not automatically guarantee** every validation behavior of a `@ConfigurationProperties` bean created by Spring Boot through its full infrastructure.

If beans must be validated consistently per policy, prefer `@Validated` + `@ConfigurationProperties`, or actively supply the corresponding handler/validation for manual binding. Do not treat `Bindable` as a way to bypass validation while retaining the same safety level.

## 17. Source Precedence with List and Map: Bindable Does Not Change Rules

Suppose the default file is:

~~~yaml
# application.yml
app:
  servers:
    - alpha.example.test
    - beta.example.test
  retry-limits:
    catalog: 2
    inventory: 3
~~~

Profile file:

~~~yaml
# application-prod.yml
app:
  servers:
    - prod.example.test
  retry-limits:
    catalog: 5
    billing: 1
~~~

Running `prod`:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

When the profile file has higher precedence and no other source overrides it:

~~~text
Bindable.listOf(String.class):
  servers = ["prod.example.test"]

Bindable.mapOf(String.class, Integer.class):
  retry-limits = {
      "catalog": 5,
      "inventory": 3,
      "billing": 1
  }
~~~

Why?

- For **List**, Spring Boot takes the list from the highest-precedence source that supplies the list, rather than appending elements.
- For **Map**, keys can be combined from multiple sources, with duplicate keys taking the value from the higher-precedence source.

`Bindable.listOf(...)` and `Bindable.mapOf(...)` only state the target data types; they **do not invent new merge rules**. If you want `alpha.example.test` included in the production list, declare the complete production list or design the data sources differently.

### 17.1. Leaf property lookup differs from collection binding

A call:

~~~java
environment.getProperty("app.servers[1]");
~~~

can return the value from a lower source if the higher source has no leaf property with that exact name. However, when binding the whole `List` across multiple property sources, binder applies the **List replacement rule**. Do not infer that Lists merge by index just because `Environment` looks up individual keys by precedence.

## 18. Dynamic Prefix Binding in Integration Libraries

Suppose a system has multiple tenants configured under separate prefixes:

~~~yaml
tenants:
  alpha:
    endpoints:
      - name: api
        url: https://alpha.example.test
        timeout: 3s
  beta:
    endpoints:
      - name: api
        url: https://beta.example.test
        timeout: 5s
~~~

An internal service needs to load the endpoint List for a selected tenant without declaring a separate properties bean for every tenant.

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public final class TenantEndpointLoader {

    private static final Set<String> ALLOWED_TENANTS =
        Set.of("alpha", "beta");

    private final Binder binder;

    public TenantEndpointLoader(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public List<Endpoint> load(String tenant) {
        if (!ALLOWED_TENANTS.contains(tenant)) {
            throw new IllegalArgumentException("Unknown tenant");
        }

        String prefix = "tenants." + tenant + ".endpoints";

        return binder
            .bind(prefix, Bindable.listOf(Endpoint.class))
            .orElseGet(List::of);
    }
}
~~~

`Bindable.listOf(Endpoint.class)` preserves the element type for both prefixes. This is a reasonable case for using Binder directly rather than one `@ConfigurationProperties` bean per tenant.

**Security note:** dynamic prefixes must be constructed from a controlled set of names or carefully validated. Never take raw untrusted input and concatenate it into a property name that could access sensitive configuration in another namespace.

Calling Binder at runtime **does not guarantee config data auto-refreshes** when files on disk change. `Environment` is usually built from configuration loaded at startup; dynamic updates depend on the configuration source and a dedicated refresh mechanism.

## 19. Adding Validation After Using `Bindable`

`Bindable` preserves generic types, but it does not verify business rules. For example, `Endpoint` has:

~~~java
public record Endpoint(String name, String url, Duration timeout) {
}
~~~

Binder can convert `timeout: -3s` into a negative `Duration` if conversion succeeds. That does not mean the endpoint has a valid configuration.

With manual Binder, you can validate after binding:

~~~java
List<Endpoint> endpoints = binder
    .bind("app.endpoints", Bindable.listOf(Endpoint.class))
    .orElseGet(List::of);

if (endpoints.isEmpty()) {
    throw new IllegalStateException(
        "app.endpoints must contain at least one endpoint");
}

for (Endpoint endpoint : endpoints) {
    if (endpoint.name() == null || endpoint.name().isBlank()) {
        throw new IllegalStateException(
            "app.endpoints contains an endpoint without name");
    }

    if (endpoint.timeout() == null
            || endpoint.timeout().isNegative()
            || endpoint.timeout().isZero()) {
        throw new IllegalStateException(
            "app.endpoints timeout must be positive");
    }
}
~~~

In a real application, you should also check URLs, HTTPS schemes, lengths, endpoint count limits, and specific requirements. Display only property names and error types; do not log credentials or tokens if endpoints contain sensitive information.

With `@ConfigurationProperties`, you can use:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
    @NotEmpty @Valid List<EndpointEntry> endpoints) {

    public record EndpointEntry(
        @NotBlank String name,
        @NotBlank String url,
        @NotNull Duration timeout) {
    }
}
~~~

This example uses Spring Boot 3.x with Jakarta Bean Validation; running it requires an appropriate implementation, typically `spring-boot-starter-validation`. `@NotNull` does not check for a positive timeout; add constraints or custom validation as required.

### 19.1. Why not just add annotations and call manual Binder?

A `Bindable` can carry annotation metadata, yet **running the validator** also depends on the bind handler/infrastructure. Manual `Binder.get(environment).bind(...)` should not be assumed to automatically trigger full Jakarta validation like a Boot-managed `@ConfigurationProperties` bean.

If the project requires automatic validation tied to the startup lifecycle, an annotation-driven properties bean is less error-prone. If manual binding is required, add explicit checks or build an appropriate handler.

## 20. Handling Type Errors and Property Names

### 20.1. Valid key names

In the example:

~~~java
binder.bind("app.retry-limits",
            Bindable.mapOf(String.class, Integer.class));
~~~

The prefix name must match the configuration. Spring Boot prefers canonical property names in kebab-case such as `retry-limits`. Mistyping `retry-limit` (singular instead of plural) will not automatically map to `retry-limits`.

### 20.2. Incompatible generic type

YAML:

~~~yaml
app:
  retry-limits:
    catalog: many
~~~

Java:

~~~java
Map<String, Integer> limits = binder
    .bind("app.retry-limits",
          Bindable.mapOf(String.class, Integer.class))
    .get();
~~~

Binder can fail when converting `"many"` to `Integer`. This is not a bug caused by `mapOf` lacking metadata; on the contrary, **because the type is preserved as Integer, binder catches the mistyped data**.

### 20.3. Missing property does not equal conversion failure

If `app.retry-limits` is completely absent, `BindResult` can be unbound. Then a fallback can be used. If a value exists with the wrong type, the result is an error to fix, not something to hide with a default map.

### 20.4. Do not use raw types in helpers

Avoid designing a helper like:

~~~java
public List loadList(Binder binder, String prefix) {
    return binder.bind(prefix, List.class).orElseGet(List::of);
}
~~~

Because the caller has no type guarantee.

A generic helper can accept the element type:

~~~java
public static <E> List<E> loadList(
        Binder binder,
        String prefix,
        Class<E> elementType) {

    return binder.bind(prefix, Bindable.listOf(elementType))
        .orElseGet(List::of);
}
~~~

At the call site:

~~~java
List<Endpoint> endpoints =
    loadList(binder, "app.endpoints", Endpoint.class);
~~~

Element type information is passed explicitly and the Java compiler can type-check the result.

## 21. Unit Testing `Bindable.listOf` and `mapOf`

A small test verifies two things: elements are created with the **correct type**, and mistyped data is not silently accepted.

Example using `MockEnvironment` from `spring-test` and Spring Boot Binder:

~~~java
package com.example.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class BindableExampleTest {

    record Endpoint(String name, String url, Duration timeout) {
    }

    @Test
    void bindsListWithTypedElements() {
        MockEnvironment env = new MockEnvironment()
            .withProperty("app.endpoints[0].name", "catalog")
            .withProperty("app.endpoints[0].url",
                    "https://catalog.example.test")
            .withProperty("app.endpoints[0].timeout", "3s");

        List<Endpoint> list = Binder.get(env)
            .bind("app.endpoints", Bindable.listOf(Endpoint.class))
            .get();

        assertThat(list).hasSize(1);
        assertThat(list.get(0)).isInstanceOf(Endpoint.class);
        assertThat(list.get(0).timeout())
            .isEqualTo(Duration.ofSeconds(3));
    }

    @Test
    void bindsMapWithIntegerValues() {
        MockEnvironment env = new MockEnvironment()
            .withProperty("app.retry-limits.catalog", "2")
            .withProperty("app.retry-limits.inventory", "4");

        Map<String, Integer> result = Binder.get(env)
            .bind("app.retry-limits",
                  Bindable.mapOf(String.class, Integer.class))
            .get();

        assertThat(result).containsEntry("catalog", 2);
        assertThat(result).containsEntry("inventory", 4);
    }
}
~~~

To run tests in a Spring Boot project, `spring-boot-starter-test` is usually used, which includes JUnit/AssertJ and Spring Test.

Across different projects, when binding a record via constructor, the compiler needs parameter name metadata and a Spring Boot version supporting record binding. If you write a standard immutable class instead of a record, make sure constructor binding uses the right mechanism.

### 21.1. Testing nested generics with `ResolvableType`

Keep the `RetryPolicy` record:

~~~java
record RetryPolicy(int attempts, Duration backoff) {
}
~~~

Create the target:

~~~java
ResolvableType mapType =
    ResolvableType.forClassWithGenerics(
        Map.class,
        ResolvableType.forClass(String.class),
        ResolvableType.forClass(RetryPolicy.class));

ResolvableType listType =
    ResolvableType.forClassWithGenerics(List.class, mapType);

Bindable<List<Map<String, RetryPolicy>>> target =
    Bindable.of(listType);
~~~

With a `MockEnvironment` providing:

~~~properties
app.retry-groups[0].catalog.attempts=3
app.retry-groups[0].catalog.backoff=250ms
~~~

The test can assert:

~~~java
List<Map<String, RetryPolicy>> groups = Binder.get(env)
    .bind("app.retry-groups", target)
    .get();

assertThat(groups).hasSize(1);
assertThat(groups.get(0).get("catalog").backoff())
    .isEqualTo(Duration.ofMillis(250));
~~~

This result demonstrates generic metadata preserved across **two levels**: the list element is a map and the map value is `RetryPolicy`.

## 22. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "`List.class` is already `List<Endpoint>`." | `Class<List>` does not contain the generic argument `Endpoint`. |
| "Casting `(List<Endpoint>)` after binding is enough." | Casting does not supply element types to Binder; accessing elements may fail. |
| "`Bindable` holds values read from YAML." | It describes the **target**; `Binder` is what reads property sources and creates results. |
| "`Bindable.listOf` automatically merges lists across profiles." | No. List binding still follows replacement rules from higher-precedence sources. |
| "`mapOf` and `listOf` are the same." | Map has key/value types, List has an element type; merge semantics differ too. |
| "`mapOf(String.class, Map.class)` keeps all inner generic levels." | `Map.class` is a raw value type; use `ResolvableType` if nested generics are needed. |
| "`ofInstance(new ArrayList<Endpoint>())` definitely infers Endpoint." | Java type erasure can lose the element type at runtime; use a typed `Bindable` plus existing value if needed. |
| "`BindResult.orElse` ignores all conversion errors." | No; fallback mainly handles the unbound case when keys are missing. |
| "`Bindable.withAnnotations` makes keys appear in Environment." | No; annotations provide metadata for binding. |
| "`Binder.get(environment)` always runs all `@ConfigurationProperties` validations." | Do not assume so; manual binding may require its own handler/validation. |
| "Right generic type guarantees URLs/timeouts are valid." | Binder handles types; business validation is a separate responsibility. |
| "Every Binder call makes Spring Boot reload config files." | No; that depends on the source and refresh mechanism. |
| "A dynamic prefix concatenated from user input is always safe." | Restrict/validate prefixes to avoid reading unintended namespaces. |
| "Map keys with special characters always bind like normal letters and dots." | Key notation rules apply; use bracket notation when needed. |

## 23. Practice Exercises

### 23.1. Exercise 1 — List of integers

Given:

~~~yaml
app:
  allowed-ports:
    - 8080
    - 8081
    - 9090
~~~

**Requirement:** use Binder to get `List<Integer>`, without using a raw list.

**Solution:**

~~~java
List<Integer> ports = Binder.get(environment)
    .bind("app.allowed-ports", Bindable.listOf(Integer.class))
    .orElseGet(List::of);
~~~

The result contains three `Integer` elements: `8080`, `8081`, `9090`.

### 23.2. Exercise 2 — Map of timeouts

Given:

~~~yaml
app:
  service-timeouts:
    catalog: 2s
    inventory: 5s
~~~

**Requirement:** get `Map<String, Duration>`.

**Solution:**

~~~java
Map<String, Duration> timeouts = Binder.get(environment)
    .bind("app.service-timeouts",
          Bindable.mapOf(String.class, Duration.class))
    .orElseGet(Map::of);
~~~

The value for `catalog` is `Duration.ofSeconds(2)`, and `inventory` is `Duration.ofSeconds(5)`.

### 23.3. Exercise 3 — Nested generic

Given:

~~~yaml
app:
  matrix:
    - east: [1, 2]
      west: [3, 4]
    - central: [5]
~~~

**Requirement:** get `List<Map<String, List<Integer>>>`. Because the List element is a Map whose values are Lists, `Bindable.listOf(Map.class)` is insufficient.

**Approach:**

~~~java
ResolvableType integers =
    ResolvableType.forClassWithGenerics(
        List.class, ResolvableType.forClass(Integer.class));

ResolvableType map =
    ResolvableType.forClassWithGenerics(
        Map.class, ResolvableType.forClass(String.class), integers);

ResolvableType outerList =
    ResolvableType.forClassWithGenerics(List.class, map);

Bindable<List<Map<String, List<Integer>>>> target =
    Bindable.of(outerList);

List<Map<String, List<Integer>>> matrix =
    Binder.get(environment)
        .bind("app.matrix", target)
        .orElseGet(List::of);
~~~

If binder builds the result properly, `matrix.get(0).get("east")` is the list of integers `[1, 2]`.

### 23.4. Exercise 4 — When is fallback needed?

**Question:** `app.servers` does not exist in any source; should you handle it with `get()` or `orElseGet(List::of)`?

**Answer:** if the server list is optional, use `orElseGet(List::of)`; if it is required for the application to operate, fail clearly when `!result.isBound()`, avoiding silently running with an empty list.

### 23.5. Exercise 5 — When generic type mismatches occur

**Question:** `app.service-timeouts.catalog=abc` while the target is `Map<String, Duration>`. Should you expect Binder to return an empty map because of `orElse(Map.of())`?

**Answer:** no. Failing to convert `abc` to `Duration` is a configuration error; fallback is not a mechanism to swallow conversion failures.

## 24. Checklist When Using `Bindable` in a Project

1. **Determine the full target type:** `List<Endpoint>`, `Map<String,Integer>`, or a nested generic.
2. **Do not use raw `List.class`/`Map.class`** when concrete element/value types are needed.
3. **Choose the right factory:** `listOf`, `setOf`, `mapOf`; for nested generics use `ResolvableType`.
4. **Use the right source:** `Binder.get(environment)` pulls configuration from the current environment; precedence still follows property sources.
5. **Handle missing properties explicitly:** `BindResult.isBound/get/orElse/orElseGet` according to the business contract.
6. **Do not mask conversion errors with defaults:** mistyped data should be fixed or reported clearly.
7. **Check the model:** record/constructor/JavaBean can be constructed and fields support conversion.
8. **Distinguish List and Map:** Lists typically replace across higher-precedence sources; Maps can merge keys.
9. **Consider existing instances:** `ofInstance`/`withExistingValue` are helpful, though they do not cure type erasure of a raw collection.
10. **If annotations affect conversion:** supply appropriate metadata or declare `@ConfigurationProperties` for Boot to process automatically.
11. **Do not skip validation:** successful type conversion does not guarantee valid business policies.
12. **Test at the right level:** unit tests for List/Map/nested generics, mistyped errors, and missing prefixes.
13. **Keep dynamic prefixes safe:** only accept namespaces from an allowlist or validate strictly.
14. **Do not assume reload:** creating a Binder does not replace a configuration refresh mechanism.
15. **Pick the simplest tool:** for a fixed configuration group, `@ConfigurationProperties` is usually clearer and easier to maintain than manual Binder.

## 25. Summary

**`Bindable` is the bridge between Java's generic type information and Spring Boot's `Binder` mechanism.**

When an application needs to bind:

~~~java
List<Endpoint>
Map<String, Duration>
List<Map<String, RetryPolicy>>
~~~

supply the complete type information:

~~~java
Bindable.listOf(Endpoint.class)
Bindable.mapOf(String.class, Duration.class)
Bindable.of(resolvableType)
~~~

Instead of:

~~~java
List.class
Map.class
~~~

and hoping a post-binding cast will recover the right data.

- **`Binder`** reads and binds configuration.
- **`Bindable<T>`** describes the target, including generics, annotation metadata, and optionally an existing value.
- **`ResolvableType`** is used when nested generic structures cannot be expressed by a simple `Class`.
- **`BindResult<T>`** represents whether binding succeeded or not, without automatically swallowing type conversion errors.
- **`@ConfigurationProperties`** is the standard path for binding a fixed configuration group within the application context; manual Binder/Bindable is for intentional advanced use cases.

### References

- Spring Boot 3.4 Javadoc — Bindable: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/context/properties/bind/Bindable.html
- Spring Boot 3.4 Javadoc — Binder: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/context/properties/bind/Binder.html
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Framework Javadoc — ResolvableType: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html
- Spring Boot Configuration Binding (wiki, background information): https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-Configuration-Binding
