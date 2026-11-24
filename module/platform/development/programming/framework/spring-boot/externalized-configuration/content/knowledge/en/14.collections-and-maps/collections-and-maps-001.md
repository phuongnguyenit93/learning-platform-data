# Binding Arrays, Lists, and Sets from Properties or YAML in Spring Boot

## 1. Overview

When configuring a Spring Boot application, a property is not always a single scalar value like `String`, `int`, or `Duration`. Certain groups of values naturally require a **collection**: a list of fallback servers, allowed CORS origins, tasks to run, enabled modules, a set of tags, or a list of downstream system endpoints.

Spring Boot supports **type-safe configuration properties binding**: converting data from `application.properties`, `application.yml`, environment variables, system properties, command-line arguments, and other configuration sources into structured Java types, including:

- Arrays: `String[]`, `int[]`, `URI[]`, or arrays of suitable objects.
- `java.util.List<T>`: an ordered collection that allows duplicate elements.
- `java.util.Set<T>`: a collection that contains no duplicate elements according to the `equals`/`hashCode` rules of the element type.
- Collections containing nested objects, such as `List<Server>`, `List<Duration>`, or `Set<Region>`, when converters and the binding mechanism are appropriate.

Configuration example:

~~~yaml
app:
  endpoints:
    - https://api-a.example.test
    - https://api-b.example.test
~~~

Bound to the class:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(List<URI> endpoints) {
}
~~~

If the class is properly registered with the configuration properties mechanism, `endpoints()` is a `List<URI>` consisting of two type-converted elements. The application does not need to parse YAML or split strings manually.

**Lesson objectives:** understand the array/list/set syntax in `.properties` and YAML, how the Spring Boot binder handles indexed properties and comma-separated values, the differences between `List` and `Set`, override rules across Config Data sources, and how to test collection configurations.

## 2. Diagram from Configuration File to Java Object

General processing flow:

~~~text
application.properties / application.yml
             +
environment variables, JVM properties, command line
             |
             v
      Spring Environment
       (PropertySources)
             |
             v
 Spring Boot ConfigurationProperties Binder
  - relaxed binding of key names
  - resolving appropriate values
  - converting element types
  - assembling collection indices
             |
             v
     Java properties object
    String[] / List<T> / Set<T>
             |
             v
        Service, Bean, Validator
~~~

Spring Boot does not bind collections by interpreting YAML as Java code. YAML is read into corresponding properties, typically **indexed** such as `app.endpoints[0]` and `app.endpoints[1]`; the Binder uses those keys to construct the corresponding collection.

The same Java target can be supplied via multiple representations:

~~~properties
app.endpoints[0]=https://api-a.example.test
app.endpoints[1]=https://api-b.example.test
~~~

or:

~~~yaml
app:
  endpoints:
    - https://api-a.example.test
    - https://api-b.example.test
~~~

or in cases where a converter supports comma-separated values:

~~~properties
app.endpoints=https://api-a.example.test,https://api-b.example.test
~~~

These forms carry a similar meaning for simple string/URI lists, but they are not completely equivalent in every scenario: commas inside an element, nested objects, shell quoting, and how the Binder processes each PropertySource can produce different results. For complex collections, using indexed properties or a YAML sequence is usually clearer.

## 3. Preparing a Configuration Properties Class

Example using Spring Boot 3.x and Java records:

~~~java
package com.example.catalog.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String[] regions,
        List<URI> endpoints,
        Set<String> tags,
        List<RemoteServer> servers
) {
    public record RemoteServer(
            String name,
            URI baseUrl,
            Duration timeout
    ) {}
}
~~~

Registering the class via scanning:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` scans for classes annotated with `@ConfigurationProperties` according to the package. If the classes are outside the default package, `basePackages` or `basePackageClasses` can be used. Explicit registration with `@EnableConfigurationProperties(AppProperties.class)` is also possible.

For constructor-bound records, you should not add `@Component` expecting Spring to use the configuration properties constructor binding mechanism; regular component scanning creates beans through a different dependency injection mechanism.

In `application.yml`:

~~~yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1
  endpoints:
    - https://api-a.example.test
    - https://api-b.example.test
  tags:
    - inventory
    - catalog
  servers:
    - name: primary
      base-url: https://primary.example.test
      timeout: 2s
    - name: backup
      base-url: https://backup.example.test
      timeout: 5s
~~~

After binding:

- `regions()` is a two-element array.
- `endpoints()` is a `List<URI>` containing two URIs.
- `tags()` is a `Set<String>` containing two distinct tags.
- `servers()` is a `List<RemoteServer>` containing two records, each holding three typed components.

**Important:** a class annotated with `@ConfigurationProperties` must still be registered as a bean before it can be injected into services. This document continues to use this class to illustrate multiple data source formats.

## 4. Binding an Array (`array`) from `application.properties`

### 4.1. Using Indices `[0]`, `[1]`, ...

Example:

~~~properties
app.regions[0]=ap-southeast-1
app.regions[1]=eu-west-1
app.regions[2]=us-east-1
~~~

Corresponding to the target:

~~~java
@ConfigurationProperties(prefix = "app")
public record RegionProperties(String[] regions) {
}
~~~

The effective value of `regions` is a three-element array in index order:

~~~text
regions[0] = ap-southeast-1
regions[1] = eu-west-1
regions[2] = us-east-1
~~~

Indices start at **0**. Specifying `[0]` and then `[2]` while omitting `[1]` can cause binding errors or unexpected results; when declaring a list with indices, use contiguous indices.

### 4.2. Using Comma-Separated Values

For simple collections, you can write:

~~~properties
app.regions=ap-southeast-1,eu-west-1,us-east-1
~~~

The Spring Boot Binder can convert a comma-separated string into an array or collection of the corresponding values. However, when an element **itself contains a comma**, this notation easily causes ambiguity about element boundaries. In that case, use the indexed form.

### 4.3. Numeric Arrays

Example:

~~~properties
app.retry.delays[0]=100
app.retry.delays[1]=250
app.retry.delays[2]=500
~~~

Target:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(int[] delays) {
}
~~~

The Binder must convert each element into a valid integer. If an element contains a string like `fast`, binding may fail. Use `long[]` if the value range exceeds `int`; for actual time durations, `Duration[]` or `List<Duration>` is usually more expressive because it includes units of measurement.

### 4.4. Object Arrays

In some cases, an array of objects such as `Server[]` can be bound. However, arrays have a fixed length and are less flexible to manipulate as collections than `List<Server>`. For complex configuration properties, `List<T>` is usually easier to evolve and test.

## 5. Binding `List<T>` from Properties

### 5.1. List of Strings

~~~properties
app.allowed-origins[0]=https://shop.example.test
app.allowed-origins[1]=https://admin.example.test
~~~

Target:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record WebProperties(List<String> allowedOrigins) {
}
~~~

When bound successfully, the list is ordered:

~~~text
0 -> https://shop.example.test
1 -> https://admin.example.test
~~~

`List` is appropriate when:

- the priority order among endpoints is meaningful;
- duplicate elements may be meaningful;
- elements need to be accessed by position or iterated in declaration order;
- the configuration represents a sequence of consecutive processing steps.

### 5.2. List of Numeric Types and `Duration`

~~~properties
app.retry.delays[0]=100ms
app.retry.delays[1]=500ms
app.retry.delays[2]=2s
~~~

Target:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(List<Duration> delays) {
}
~~~

The resulting value can be:

~~~text
[PT0.1S, PT0.5S, PT2S]
~~~

The elements `100ms`, `500ms`, and `2s` are converted to `Duration` thanks to Spring Boot's conversion support. This is more explicit than declaring `List<Integer>` and implicitly assuming milliseconds.

### 5.3. List of Objects with Multiple Fields

~~~properties
app.servers[0].name=primary
app.servers[0].base-url=https://primary.example.test
app.servers[0].timeout=2s

app.servers[1].name=backup
app.servers[1].base-url=https://backup.example.test
app.servers[1].timeout=5s
~~~

Target:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ServerCatalog(List<Server> servers) {
    public record Server(String name, URI baseUrl, Duration timeout) {}
}
~~~

Here `[0]` and `[1]` identify the elements, while `.name`, `.base-url`, and `.timeout` are fields of each object.

This is a major advantage of indexed properties over a long comma-separated string: each element can carry an entire bean/record structure.

### 5.4. List of Enums

Example:

~~~java
public enum AlertChannel {
    EMAIL, SMS, WEBHOOK
}
~~~

~~~java
@ConfigurationProperties(prefix = "alerts")
public record AlertProperties(List<AlertChannel> channels) {
}
~~~

~~~properties
alerts.channels[0]=email
alerts.channels[1]=webhook
~~~

Spring Boot provides enum conversion for many common formats. However, if a value does not match a supported enum constant, binding can fail. Do not assume an arbitrary string is a valid enum just because the Binder supports relaxed naming.

## 6. YAML Sequences for Arrays and Lists

YAML represents lists using a leading `-`:

~~~yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1
    - us-east-1
~~~

Or in inline form:

~~~yaml
app:
  regions: [ap-southeast-1, eu-west-1, us-east-1]
~~~

When Spring Boot loads Config Data from YAML, the elements are represented as corresponding properties such as `app.regions[0]`, `app.regions[1]`, and `app.regions[2]`. From there, the Binder can create a `String[]` or `List<String>`.

### 6.1. YAML List of Objects

~~~yaml
app:
  servers:
    - name: primary
      base-url: https://primary.example.test
      timeout: 2s
    - name: backup
      base-url: https://backup.example.test
      timeout: 5s
~~~

This YAML notation is semantically equivalent to the indexed keys `app.servers[0].name`, `app.servers[1].name`, and so on.

Use **consistent** indentation; lines belonging to the same element must sit under its corresponding `-`. In `application.properties`, indentation does not create nested structure; the indexed syntax is what determines it.

### 6.2. Quoting Elements Containing Special Characters

Example:

~~~yaml
app:
  patterns:
    - "type:order"
    - "origin,region"
    - "#internal"
    - "https://api.example.test/v1?mode=fast"
~~~

These are four string elements. In YAML, `#` can start a comment in certain positions, `:` has special meaning in some contexts, and `,` is significant in flow sequences. Quoting helps the parser preserve the string as intended.

For `.properties`, an element containing a comma should be declared using an index instead of a combined comma-separated value:

~~~properties
app.patterns[0]=type:order
app.patterns[1]=origin,region
app.patterns[2]=#internal
~~~

In this example, `#` appears after `=`, so it is part of the value rather than an end-of-line comment. If you need literals with backslashes or newlines, refer to the escaping rules specific to the properties format.

### 6.3. Do Not Confuse a YAML Scalar with a YAML Sequence

These two configurations do not represent the exact same YAML data structure:

~~~yaml
app:
  hosts: "host-a,host-b"
~~~

and:

~~~yaml
app:
  hosts:
    - host-a
    - host-b
~~~

The first form is a **scalar string** containing a comma. The Spring Boot Binder may split it to bind into a collection depending on the converter. The second form is a two-element **YAML sequence**, modeled explicitly as indexed properties.

If you want to guarantee element boundaries at the YAML level, use a sequence.

## 7. Binding `Set<T>`: Characteristics and Differences from List

A `Set` is a collection that contains no duplicate elements according to the equality semantics of the element type. Example:

~~~java
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record FeatureProperties(Set<String> tags) {
}
~~~

Configuration:

~~~yaml
app:
  tags:
    - catalog
    - inventory
    - catalog
~~~

According to `Set<String>` semantics, the repeated element `catalog` does not need to exist twice. After binding, the object represents only the set of unique values according to `String.equals`.

### 7.1. Comparing `String[]`, `List<String>`, and `Set<String>`

| Criterion | `String[]` | `List<String>` | `Set<String>` |
| --- | --- | --- | --- |
| Preserves index order | Yes | Yes | Should not rely on order without an explicit contract |
| Allows duplicate elements | Yes | Yes | No |
| Access by index | Yes | Yes | No |
| Size after creation | Fixed | Modifiable with a mutable implementation | Modifiable with a mutable implementation |
| Suitable when | API requires an array | Endpoint lists, execution steps, priorities | Tags, permission sets, unique values |
| Configurable from YAML sequence | Yes | Yes | Yes |

**Do not choose `Set` if order is a business requirement.** Even though a `Set` implementation may preserve insertion order in some cases, the general `Set` contract does not require every implementation to guarantee ordering. When position and priority matter, use `List`.

### 7.2. Duplicates in a `Set`

~~~properties
app.tags[0]=catalog
app.tags[1]=inventory
app.tags[2]=catalog
~~~

The Binder converts the values into a `Set`; elements that are duplicates by `equals` are no longer represented repeatedly. If the application needs to detect duplicate declarations to report a configuration error, binding directly into a `Set` can mask the duplicate signal.

One approach is to bind into `List<String>`, check for duplicates during validation, and convert to a `Set` when used if valid.

### 7.3. Set of Complex Objects

`Set<MyType>` uses `equals` and `hashCode` of `MyType` to determine duplicate elements. If `MyType` is a plain Java class that does not override these two methods, two objects with identical contents may still be treated as distinct. Records typically provide value-based `equals`/`hashCode` for their components.

Therefore, when binding `Set<Server>`, you must be clear about which fields actually define "duplicate". If you want to preserve every object in configuration order, `List<Server>` is usually less surprising.

### 7.4. Fields Well-Suited for a Set

- A list of feature-flag labels, if order does not matter.
- A set of unique namespace or region names.
- Types of identifiers that cannot repeat.
- A set of permissions/roles in a static configuration, assuming the `Set` is not treated as a standalone security mechanism.

Even when using a `Set`, validation is needed if it must be non-empty, contain no blank elements, or accept only a valid subset of values.

## 8. Collection Types in JavaBean Setter Binding

Records are not mandatory. You can create a JavaBean with setters and register it using `@Component`:

~~~java
package com.example.catalog.config;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app")
public class AppCollectionProperties {

    private List<String> hosts = new ArrayList<>();
    private Set<String> tags = new LinkedHashSet<>();

    public List<String> getHosts() {
        return hosts;
    }

    public void setHosts(List<String> hosts) {
        this.hosts = hosts;
    }

    public Set<String> getTags() {
        return tags;
    }

    public void setTags(Set<String> tags) {
        this.tags = tags;
    }
}
~~~

Configuration:

~~~properties
app.hosts[0]=host-a.example.test
app.hosts[1]=host-b.example.test
app.tags[0]=catalog
app.tags[1]=search
~~~

Spring creates the JavaBean via component scanning, and then the Binder assigns the corresponding collections. Pre-initializing with `new ArrayList<>()` or `new LinkedHashSet<>()` gives the class a clear default state even when no matching keys are present.

### 8.1. Are Setters Strictly Necessary?

For pre-initialized mutable collections, Spring Boot can bind through the getter in some scenarios. However, to keep JavaBeans easy to understand and avoid relying on mutability details, declare appropriate getters/setters when choosing the mutable setter-binding model.

Do not assume every `final` collection, immutable list, or instance created by `List.of()` can be updated in place by the Binder. If you want immutability after creation, constructor binding/records are a more intentional choice.

### 8.2. Avoiding Mutable Configuration Changes After Startup

If a singleton bean returns a mutable `List<String>`, another service could execute:

~~~java
properties.getHosts().clear();
~~~

This mutates the runtime state of the configuration bean rather than updating a property source, and it is not guaranteed to be thread-safe.

If you do not want consumers to mutate the data:

~~~java
public List<String> hostsView() {
    return List.copyOf(hosts);
}
~~~

Or design a record with a compact constructor that creates an appropriate defensive copy. Note that `List.copyOf` rejects null elements; if the data can contain nulls, a different policy is required.

Spring Boot does not automatically enable live reload just because a collection has a setter; changing `application.yml` while the application is running normally requires a restart or a dedicated refresh mechanism.

## 9. Constructor Binding and Collections in Records

Records are well suited for representing configuration data that is immutable with respect to **references**:

~~~java
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        List<String> categories,
        Set<String> tags
) {
}
~~~

A compact constructor can be declared to prevent consumers from modifying collections after binding:

~~~java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        List<String> categories,
        Set<String> tags
) {
    public CatalogProperties {
        categories = categories == null ? List.of() : List.copyOf(categories);
        tags = tags == null ? Set.of() : Set.copyOf(tags);
    }
}
~~~

This example establishes an **application policy**: when a collection is not configured, use an empty collection; when it is, create an unmodifiable copy. However:

- `List.copyOf` and `Set.copyOf` do not accept null elements.
- `Set.copyOf` eliminates duplicates and does not promise to preserve an iteration order that consumers can rely on.
- Copying the outer collection does not automatically deep-copy mutable objects inside it.

If a list must not be empty, use validation instead of defaulting to `List.of()`.

### 9.1. When a Collection Is Completely Missing

If `catalog.categories` is absent from all configuration sources, the constructor-bound value depends on the Binder mechanism and the target's applicable defaults. For collection-typed record components, avoid assuming "it is definitely an empty list" across all versions and binding styles.

You can define an explicit fallback in the constructor as shown in the example, or use the default mechanism supported by Spring Boot for constructor binding. If the list is mandatory, use Bean Validation to catch missing or empty values.

### 9.2. Combining with `@DefaultValue`

`@DefaultValue` supports defaults for constructor-binding parameters; usage may vary across scalars, nested objects, and collections depending on the Boot version and conversion rules. Do not assume `@DefaultValue("a,b")` is always equivalent to a two-element YAML sequence in every complex context.

For complex collections, declaring a default value in `application.yml` or explicit constructor logic is usually easier to follow than packing lots of data into an annotation.

## 10. Property Names, Relaxed Binding, and Indices

The Spring Boot Binder supports **relaxed binding** for property names. For example, the Java field `allowedOrigins` can be bound to the canonical name `allowed-origins`:

~~~properties
app.allowed-origins[0]=https://a.example.test
app.allowed-origins[1]=https://b.example.test
~~~

With Java:

~~~java
@ConfigurationProperties(prefix = "app")
public record WebProperties(List<String> allowedOrigins) {
}
~~~

In YAML:

~~~yaml
app:
  allowed-origins:
    - https://a.example.test
    - https://b.example.test
~~~

### 10.1. Indexed Environment Variables

In environment variables, dots are typically converted to underscores, dashes are removed, names are uppercased, and list indices are placed between underscores.

Example with a Java record:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Client> remoteClients) {
    public record Client(String name, String url) {}
}
~~~

Canonical form:

~~~properties
app.remote-clients[0].name=primary
app.remote-clients[0].url=https://primary.example.test
app.remote-clients[1].name=backup
app.remote-clients[1].url=https://backup.example.test
~~~

This can be represented as environment variables following Boot's rules:

~~~text
APP_REMOTECLIENTS_0_NAME=primary
APP_REMOTECLIENTS_0_URL=https://primary.example.test
APP_REMOTECLIENTS_1_NAME=backup
APP_REMOTECLIENTS_1_URL=https://backup.example.test
~~~

The `_0_` and `_1_` segments correspond to the collection indices. For many deployment tools, using YAML or a properties file for long lists of objects is easier to read and less error-prone than setting many environment variables.

### 10.2. A Single Comma-Separated Environment Variable

For a simple list:

~~~bash
APP_REGIONS=ap-southeast-1,eu-west-1 java -jar app.jar
~~~

When the Binder needs `List<String>` or `String[]` at `app.regions`, the value can be converted into a collection. This feature is convenient for short collections, but difficult for representing elements with commas or multi-field objects.

On Windows PowerShell, do not use the Linux variable assignment syntax before the command; instead, set `$env:APP_REGIONS` appropriately.

### 10.3. Do Not Treat the Bean Field Name as the Full Key

A field `List<String> hosts` inside `@ConfigurationProperties(prefix = "app.client")` corresponds to `app.client.hosts`, not automatically to `hosts` at the root. Check both the prefix and the field name when binding fails.

## 11. When Configuration Spans Multiple Sources: Lists Are Replaced, Not Accumulated

This is an especially important rule in **Spring Boot Externalized Configuration**:

> When a `List` is declared across multiple property sources, the Spring Boot Binder typically **selects the list from the source with higher precedence**; it does not automatically merge elements from all sources into a combined list.

Example base file:

~~~yaml
# application.yml
app:
  servers:
    - name: api-a
      base-url: https://a.example.test
      timeout: 2s
    - name: api-b
      base-url: https://b.example.test
      timeout: 3s
~~~

Profile-specific file:

~~~yaml
# application-prod.yml
app:
  servers:
    - name: api-prod
      base-url: https://prod.example.test
      timeout: 5s
~~~

When the `prod` profile is active and this source has higher precedence in a standard loading scenario, the resulting `app.servers` is a **single-element list** containing `api-prod`. The two servers from the base file are not automatically retained.

Contrast:

~~~text
Base list:     [api-a, api-b]
Prod list:     [api-prod]
Effective:     [api-prod]
NOT:           [api-a, api-b, api-prod]
~~~

### 11.1. Overriding Individual Fields Does Not Mean Merging Individual Elements

Suppose:

~~~yaml
# application.yml
app:
  servers:
    - name: primary
      base-url: https://primary.example.test
      timeout: 2s
~~~

and:

~~~yaml
# application-prod.yml
app:
  servers:
    - name: prod-primary
~~~

Do not expect `base-url` and `timeout` from the old element to be automatically merged into the new element at the same index 0. Under list replacement rules, the element from the higher-precedence source may only have `name=prod-primary`, while undeclared fields may receive null/defaults/other values depending on the Java type and initialization logic.

If a list element has mandatory fields, declare all required fields in the overriding source and use validation. Overriding only a single field at index 0 is not a safe patching mechanism for lists.

### 11.2. Do Not Add `[1]` in a Higher-Precedence Source to "Append"

Suppose the base file has `app.servers[0]` and `app.servers[1]`, and an external source has `app.servers[2]`. Do not assume the external source can append a third element to the end of the old list. Under replacement rules, non-contiguous indices in a single source can cause binding to behave unexpectedly.

If you want dynamic appending, design a dedicated configuration mechanism, such as explicit list merging in code, or use a `Map` for entries with stable identifiers. Do not treat the Config Data Binder as a JSON Patch tool.

## 12. `Map` Differs from `List` When Combining Multiple Sources

Although this article focuses on arrays/Lists/Sets, the difference from `Map` is crucial because it is a frequent source of confusion.

Example:

~~~yaml
# application.yml
app:
  clients:
    primary:
      url: https://primary.example.test
      timeout: 2s
    backup:
      url: https://backup.example.test
      timeout: 3s
~~~

Higher-precedence source:

~~~yaml
# application-prod.yml
app:
  clients:
    primary:
      timeout: 5s
~~~

If the Java target is an appropriate `Map<String, Client>`, the Binder can combine **Map keys** from multiple sources: `primary` still exists with its corresponding property overridden, and `backup` still exists from the lower-precedence source. This behavior is fundamentally different from list replacement.

**Summary:**

- With `List`, a higher-precedence source replaces the entire list during binding.
- With `Map`, entries can be combined by key, and properties sharing the same key follow source precedence.
- With `Set`, do not view choosing `Set` as a way to automatically merge collections across multiple sources. Verify the exact behavior if the application uses overlapping sources, and design an explicit replacement policy rather than relying on element deduplication.

When items need to be maintained by stable identifiers across environments, `Map<String, Client>` is usually a better model than `List<Client>` with the intent of editing one element by index.

## 13. Profile-Specific Files and Lists

Example base file:

~~~properties
# application.properties
app.allowed-origins[0]=https://dev.example.test
app.allowed-origins[1]=https://preview.example.test
~~~

File for the production profile:

~~~properties
# application-prod.properties
app.allowed-origins[0]=https://shop.example.test
~~~

When the `prod` profile is selected and the profile-specific file has higher precedence, the effective list is typically:

~~~text
[https://shop.example.test]
~~~

Not:

~~~text
[https://shop.example.test, https://preview.example.test]
~~~

The same principles apply when external files have higher precedence than the classpath or other imports. However, exact source ordering also depends on location groups, `spring.config.location`, `spring.config.additional-location`, `spring.config.import`, and non-Config Data sources.

### 13.1. Multi-Document YAML

~~~yaml
app:
  modes:
    - standard
    - debug

---
spring:
  config:
    activate:
      on-profile: prod
app:
  modes:
    - standard
    - audit
~~~

When `prod` is active and its document has higher precedence than the base document in this file, the `app.modes` list is taken from the `prod` document. It is not `[standard, debug, standard, audit]`.

### 13.2. A Profile-Specific File Without the List

If `application-prod.yml` only overrides a completely different property, `app.modes` from the base file can still be used. "List replacement" occurs when a higher-precedence source **contributes values for that list**; it does not mean every list in the base file is wiped out whenever a profile is enabled.

## 14. Commas Inside Elements and Safe Configuration

A configuration string:

~~~properties
app.labels=type:order,region:asia
~~~

is typically interpreted as two elements when bound to `List<String>`. If the actual intent is **a single element** `type:order,region:asia`, this notation can produce an error.

Use indexed properties:

~~~properties
app.labels[0]=type:order,region:asia
~~~

Or a YAML sequence:

~~~yaml
app:
  labels:
    - "type:order,region:asia"
~~~

Key point: when an element contains a `,` character, represent element boundaries at the file format level rather than relying on the comma-separated string converter.

### 14.1. URLs Containing Commas

Some URLs have query strings or paths containing commas. If you use:

~~~properties
app.urls=https://example.test/search?q=a,b
~~~

and the target is `List<URI>`, the comma may be treated as a collection delimiter. Do not assume from looking at the string that it will definitely bind as a single URL.

Clear approach:

~~~properties
app.urls[0]=https://example.test/search?q=a,b
~~~

Or:

~~~yaml
app:
  urls:
    - "https://example.test/search?q=a,b"
~~~

### 14.2. Spaces Around Commas

When writing:

~~~properties
app.regions=ap-southeast-1, eu-west-1
~~~

whitespace trimming depends on the conversion path and element type. To avoid unintentionally creating `" eu-west-1"`, write consistently without spaces when using a comma-separated scalar, or use a YAML sequence. Do not rely on every converter trimming exactly as you expect.

## 15. Empty Collections, Undeclared Collections, and `null`

Three states must be distinguished:

1. **Property absent**: no list key exists in any source.
2. **Empty collection present**: the application intentionally wants a set/list with zero elements.
3. **Empty element present**: the collection contains an empty-string element, which differs from having no elements.

YAML example:

~~~yaml
app:
  tags: []
~~~

This is the YAML syntax representing an empty sequence. However, how the Binder observes an empty sequence from YAML depends on flattening details and the Boot version; do not rely on the presence of an empty sequence to guarantee that every Java target receives `Set.of()`.

In Java:

~~~java
@ConfigurationProperties(prefix = "app")
public record TagProperties(Set<String> tags) {
    public TagProperties {
        tags = tags == null ? Set.of() : Set.copyOf(tags);
    }
}
~~~

This example defines an explicit empty fallback inside the object itself. However, if "no tags" is a configuration error, use validation instead of turning a missing state into an empty collection.

For JavaBeans:

~~~java
private List<String> hosts = new ArrayList<>();
~~~

A field initializer is another option for expressing a default when sources provide no value. It does not mean the Binder will merge list values across multiple sources.

## 16. Validation for Lists and Sets

Spring Boot can integrate Jakarta Bean Validation when `@ConfigurationProperties` is registered and a suitable provider is present, typically via `spring-boot-starter-validation`.

Example:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty List<@NotBlank String> allowedOrigins,
        @Size(max = 10) Set<@NotBlank String> tags
) {}
~~~

Meaning:

- `@NotEmpty`: the list must have at least one element.
- `@NotBlank` on elements: each string must not be null, empty, or whitespace-only.
- `@Size(max = 10)`: the tag set must not exceed 10 elements.
- `List<@NotBlank String>` is a **container element constraint**; it requires support from the Bean Validation implementation.

Do not check only `allowedOrigins != null`: a list containing an empty string can still be invalid for a CORS configuration.

### 16.1. Validating Nested Objects

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record ServerProperties(
        @NotEmpty List<@Valid Server> servers
) {
    public record Server(
            @NotBlank String name,
            @NotNull URI baseUrl
    ) {}
}
~~~

In a complete project, import `jakarta.validation.constraints.NotEmpty` appropriately. `@Valid` on the element propagates validation into the `Server` object; `baseUrl` being a `URI` does not by itself verify that the hostname exists or that the endpoint responds.

### 16.2. Checking for Duplicate Elements

If a configuration uses `List<String>` but requires all elements to be unique, `@NotEmpty` is not enough. You can build a custom Bean Validation constraint or enforce an invariant in the constructor/application.

Do not switch to `Set` merely to "silently deduplicate" if declaring duplicates is a configuration error that should be reported to the deployer.

## 17. Per-Element Conversion Errors

Suppose:

~~~properties
app.retry.delays[0]=100ms
app.retry.delays[1]=fast
app.retry.delays[2]=2s
~~~

The target is `List<Duration>`. The element `fast` is not a valid `Duration` format for the corresponding converter, so binding can fail with an error. Depending on the error structure, Spring Boot provides details about the property, index, and unconvertible value.

Similarly:

~~~properties
app.ports[0]=8080
app.ports[1]=eight-thousand
~~~

with `List<Integer>` can fail at index 1.

Changing the target to `List<String>` makes parsing succeed, **but does not solve the requirement that the data be valid**. If a port is genuinely a number, keep the numeric type and appropriate validation so errors are caught early.

With arrays, lists, and sets containing nested objects, an error can occur in a deeply nested field, such as `app.servers[1].timeout`. When debugging, examine the full property name and index instead of looking only at the generic "Failed to bind properties" message.

## 18. `@Value` vs. `@ConfigurationProperties` for Reading Lists

`@Value` is convenient for a single property:

~~~java
@Value("${app.client.timeout:5s}")
private String timeout;
~~~

For a simple list represented as a comma-separated string, `@Value` and the conversion service can handle some cases:

~~~properties
app.regions=eu-west-1,ap-southeast-1
~~~

However, with a YAML sequence:

~~~yaml
app:
  regions:
    - eu-west-1
    - ap-southeast-1
~~~

the elements are flattened into indexed keys such as `app.regions[0]`, `app.regions[1]`. `@Value("${app.regions}")` is not guaranteed to receive the entire collection like the `@ConfigurationProperties` Binder does.

Therefore, **prefer `@ConfigurationProperties` for arrays/Lists/Sets**, especially when:

- binding from YAML sequences is needed;
- there are nested lists of objects;
- per-element validation is required;
- multiple configuration sources with relaxed binding must be supported;
- a centralized, easily testable configuration object is desired.

Do not try to stitch together multiple indexed `@Value` fields if the list has variable length. Using SpEL to split strings easily introduces dependencies on string syntax and does not fully replicate the Binder.

## 19. A Complete Example: List of Upstreams and Tags

### 19.1. YAML Configuration

~~~yaml
# application.yml
gateway:
  upstreams:
    - name: catalog
      url: https://catalog.example.test
      timeout: 2s
    - name: payments
      url: https://payments.example.test
      timeout: 4s
  tags:
    - customer-facing
    - auditable
~~~

### 19.2. Configuration Record

~~~java
package com.example.gateway.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        @NotEmpty List<@Valid Upstream> upstreams,
        Set<@NotBlank String> tags
) {
    public record Upstream(
            @NotBlank String name,
            @NotNull URI url,
            @NotNull Duration timeout
    ) {}
}
~~~

### 19.3. Registration

~~~java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
~~~

With the package structure in the example, `@ConfigurationPropertiesScan` finds `GatewayProperties` in the subpackage `com.example.gateway.config`.

### 19.4. Usage in a Service

~~~java
import com.example.gateway.config.GatewayProperties;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class GatewayRoutingService {

    private final GatewayProperties properties;

    public GatewayRoutingService(GatewayProperties properties) {
        this.properties = properties;
    }

    public List<String> targetNames() {
        return properties.upstreams().stream()
                .map(GatewayProperties.Upstream::name)
                .toList();
    }
}
~~~

`targetNames()` returns `["catalog", "payments"]` in list order. Meanwhile, `tags()` represents a set of distinct tags.

This service example illustrates reading configuration; it does not implement routing, retries, or HTTP requests itself. If business logic requires prioritizing upstreams in order, `List` is a more appropriate choice than `Set`.

### 19.5. Properties Equivalent

~~~properties
gateway.upstreams[0].name=catalog
gateway.upstreams[0].url=https://catalog.example.test
gateway.upstreams[0].timeout=2s

gateway.upstreams[1].name=payments
gateway.upstreams[1].url=https://payments.example.test
gateway.upstreams[1].timeout=4s

gateway.tags[0]=customer-facing
gateway.tags[1]=auditable
~~~

In projects with multiple sources, pick a consistent representation for each list to avoid hard-to-read configurations, especially when profile overrides are involved.

## 20. Testing Collection Binding

You can write tests against the Spring Boot application context to verify that arrays, lists, and sets bind as expected.

Suppose `GatewayProperties` and `GatewayApplication` are defined as above:

~~~java
package com.example.gateway;

import com.example.gateway.config.GatewayProperties;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
    "gateway.upstreams[0].name=one",
    "gateway.upstreams[0].url=https://one.example.test",
    "gateway.upstreams[0].timeout=750ms",
    "gateway.upstreams[1].name=two",
    "gateway.upstreams[1].url=https://two.example.test",
    "gateway.upstreams[1].timeout=2s",
    "gateway.tags[0]=internal",
    "gateway.tags[1]=audit"
})
class GatewayPropertiesTest {

    @Autowired
    GatewayProperties properties;

    @Test
    void bindsIndexedCollections() {
        assertEquals(List.of("one", "two"),
                properties.upstreams().stream()
                        .map(GatewayProperties.Upstream::name)
                        .toList());

        assertEquals(Duration.ofMillis(750),
                properties.upstreams().get(0).timeout());

        assertTrue(properties.tags().contains("internal"));
        assertTrue(properties.tags().contains("audit"));
    }
}
~~~

This test illustrates indexed configuration in a test property source. In a real project, you need Spring Boot Test, JUnit, the main application, and appropriate registration of `GatewayProperties`.

### 20.1. Testing List Replacement Across Profiles

You can create `application.yml` and `application-prod.yml` as in section 11, run the test with `@ActiveProfiles("prod")`, and confirm that only the list from the higher-precedence source remains.

Note that the test framework also supplies its own property sources; if a test sets part of a list via `@SpringBootTest(properties=...)`, that test source may take higher precedence than the files and produce results different from an actual deployment scenario.

### 20.2. Testing Sets Without Relying on Iteration Order

If the target is `Set<String>`, compare the set of values:

~~~java
assertEquals(Set.of("internal", "audit"), properties.tags());
~~~

Do not write tests requiring `properties.tags().iterator().next()` to always be `internal` unless the application contract explicitly mandates and guarantees ordering.

### 20.3. Testing Validation

With `@NotEmpty List<@Valid Upstream>`, test an empty list or an element missing a name/URL to confirm the application fails at startup. That documents the configuration contract in tests rather than letting errors surface when a service uses the element.

## 21. Troubleshooting When Collection Binding Goes Wrong

If the YAML configuration shows three elements but Java receives `null`, a list missing elements, or a conversion error:

1. **Check whether the bean is registered.** `@ConfigurationProperties` alone does not always create a bean; check `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or `@Component` for suitable JavaBeans.
2. **Check the prefix.** A class declaring `prefix = "gateway"` requires `gateway.upstreams`, not `app.upstreams`.
3. **Check canonical property names.** For example, `remote-clients` with Java `remoteClients`; when using env vars, name conversion follows specific rules.
4. **Check YAML syntax.** Dashes `-`, indentation, quotes, and document separators must be valid.
5. **Check indices.** Indexed lists should start at 0 and be contiguous.
6. **Check whether comma-separated and indexed forms are mixed across sources.** Mixing representations can make behavior hard to reason about, especially during source overrides.
7. **Check profiles and document activation.** A property might reside in `application-prod.yml` while the `prod` profile is not active.
8. **Check property source precedence.** An external file or command-line property might replace the entire list.
9. **Check target types.** `List<Duration>` requires values parseable as `Duration`; `List<URI>` requires valid URI syntax.
10. **Check nested types.** If using JavaBeans, getters/setters and object structures must be bindable; if using records, register them with the appropriate constructor-binding mechanism.
11. **Check validation.** `@NotEmpty`, `@NotBlank`, and `@Valid` can reject a collection that parses fine but is invalid.
12. **Check for elements containing commas.** Switch to indexed notation or a YAML sequence if a single element is being split into multiple parts.
13. **Check whether the application was restarted.** Spring Boot does not normally rebind collections automatically when files change.
14. **Inspect safely only.** Do not log collections containing tokens, credentials, or API keys.

In secured environments, Spring Boot Actuator `/actuator/configprops` or `/actuator/env` can help inspect property sources and bindings; mask sensitive values and restrict access.

## 22. Common Misconceptions

### 22.1. "The list in the prod file will be appended to the list in the base file"

No. The Spring Boot Binder rule for Lists across multiple sources is replacement by the higher-precedence source, not appending.

### 22.2. "Writing one index in a higher source will only edit that element"

Do not rely on this interpretation. When a list belongs to a higher-precedence source, it does not act as a per-element patch on the lower-precedence source. Provide a full list in the overriding source or switch the model to a `Map` when key-based overrides are needed.

### 22.3. "Set is like List and will preserve order"

`Set` has no general contract guaranteeing iteration order. If declaration order matters, use `List`.

### 22.4. "Set automatically deduplicates by a name field"

No. Deduplication depends on `equals`/`hashCode` of the element type. Two objects with the same `name` but different `endpoint` values may or may not be considered duplicates depending on the equality definition.

### 22.5. "A YAML sequence and a comma-containing string are always identical"

No. A YAML sequence distinguishes individual elements at the structural level. A comma-separated string requires conversion and can run into issues when a comma is part of an element's data.

### 22.6. "Using `@Value` for a YAML list is sufficient"

Do not assume this. `@ConfigurationProperties` is designed to bind collection structures and nested objects; `@Value` is intended for expressions or single keys and may not see flattened indexed lists as expected.

### 22.7. "A missing collection always yields an empty list"

You cannot assume this across all targets, constructors, and versions. Define an explicit default/validation policy.

### 22.8. "An array can grow automatically after binding"

Arrays have a fixed size. If a collection needs to change at runtime, design it explicitly, and generally avoid mutating a shared configuration object directly.

## 23. Quick Selection Table

| Requirement | Recommended Type | Readable Source Syntax | Notes |
| --- | --- | --- | --- |
| Ordered list | `List<T>` | YAML sequence or indexed properties | List from higher-precedence source replaces lower |
| Data may contain duplicates | `List<T>` / array | Indexed properties | Preserves duplicate elements if present |
| API requires an array | `T[]` | Indexed properties or YAML sequence | Fixed size |
| Set of unique values | `Set<T>` | YAML sequence | Do not assume order |
| List of complex objects | `List<Server>` | YAML sequence of mappings | Use `@Valid` on child objects when needed |
| Override individual objects by ID | `Map<String, Server>` | YAML mapping by ID | Map differs from List in multi-source merging |
| Just a few short strings | `List<String>` | Comma-separated can be used | Avoid when elements contain commas |
| Mandatory collection | `List<T>`/`Set<T>` + validation | Explicit YAML sequence | `@NotEmpty`, element constraints |
| Immutable configuration | Record constructor binding + defensive copy | YAML / indexed | Record is only reference-immutable if collection is mutable |

## 24. Implementation Checklist

- Choose **array** when an API requires an array, **List** when ordered and duplicates are allowed, and **Set** when uniqueness matters and order does not.
- In `.properties`, use `app.items[0]`, `app.items[1]` for elements; for objects use `app.items[0].name`.
- In YAML, use `- item` sequences or flow sequences for simple elements.
- For simple collections, commas can be convenient; if an element itself contains a comma, use indexed properties or a YAML sequence.
- Choose appropriate Java types so the Binder converts `String`, `URI`, `Duration`, numbers, enums, and nested objects.
- Use `@ConfigurationProperties` instead of relying purely on `@Value` for YAML sequences or nested collections.
- Register records with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`; use `@Component` for JavaBean setter binding when appropriate.
- Remember that **Lists do not automatically merge across PropertySources**; a higher-precedence source replaces a lower-precedence list.
- With `Set`, understand duplicate semantics via `equals`/`hashCode` and avoid relying on iteration order.
- Explicitly design for **missing collection**, **empty collection**, **empty element**, and **type mismatch** cases.
- Use `@NotEmpty`, `@NotBlank`, `@Valid`, and other validations when configuration is mandatory.
- For nested lists requiring overrides by ID, consider using `Map` instead of patching by index.
- Prevent consumers from arbitrarily mutating configuration collections unless intentional.
- When results are wrong, inspect prefix, indices, active profiles, property-source precedence, and source representation.

## 25. Conclusion

The Spring Boot Binder can **bind arrays, `List`, and `Set`** from many configuration representations: indexed keys in `application.properties`, YAML sequences, comma-separated strings, and appropriate externalized configuration sources.

This capability goes beyond simply turning multiple strings into a Java collection. It also encompasses relaxed binding of key names, per-element type conversion, nested object construction, profile conditions, and source precedence. Details such as **List replacement**, **Set uniqueness**, **YAML sequence vs. comma-separated string**, and **missing vs. empty values** can significantly alter application behavior.

For safe and maintainable configuration, prefer `@ConfigurationProperties` with clear types, represent structured lists with YAML or indexed properties, place validation on the properties class, and verify effective values in the actual startup environment.

### References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Binding Lists](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Relaxed Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding)
