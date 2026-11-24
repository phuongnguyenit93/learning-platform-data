# JavaBean Binding via Getters, Setters, and Initial Values in Spring Boot 3.3

## 1. Nature of JavaBean Binding

`@ConfigurationProperties` lets Spring Boot group configuration values sharing a prefix into a strongly typed Java object. With **JavaBean binding**, Spring Boot instantiates (or receives) a mutable object and assigns properties through **JavaBean property descriptors**: getters, setters, and sometimes getters returning an already-initialized object or collection so the Binder can update it directly.

For example, instead of reading four values separately:

```java
@Value("${app.name:Catalog}")
String name;

@Value("${app.enabled:true}")
boolean enabled;
```

we place them in one class:

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private String name = "Catalog";
    private boolean enabled = true;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
}
```

From the file:

```properties
app.name=Order Service
app.enabled=false
```

The Binder locates `app.name` and `app.enabled`, converts types if necessary, and calls the setters to update the object. The result is `name="Order Service"` and `enabled=false`, **overriding** the corresponding initialized values.

The key point: default values set via field initializers in a JavaBean **are only preserved when the Binder does not bind another value for that property**. Do not treat `null`, `""`, `0`, and `false` as equivalent states.

## 2. When Does JavaBean Binding Occur?

In a standard Spring Boot application:

1. Spring Boot builds `Environment` from sources: Config Data (`application.properties`, YAML, etc.), OS environment variables, JVM system properties, command-line options, and other sources.
2. Spring Boot registers the configuration bean via `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an appropriate standard bean mechanism.
3. For **JavaBean binding**, the object with a no-arg constructor is instantiated; its field initializers and constructor body execute first.
4. The Binder reads properties under the prefix, maps names via relaxed binding, converts source values to target types, and updates bindable JavaBean properties.
5. Properties that are not supplied keep their initialized values, unless other code modifies them. The bound configuration bean is injected into other services via constructor injection.

This is the general model. `@ConfigurationProperties` also supports **constructor binding** and records, where parameters are passed to the constructor; that approach has different initialization rules. This lesson focuses on **JavaBean binding via getters and setters**.

### Basic Requirements for a JavaBean

A standard configuration JavaBean needs:

- An instantiable class, usually `public` with a **no-arg constructor**.
- Scalar values intended to be overridden by configuration must have appropriate **setters** (`setName`, `setMaxRetries`, etc.).
- Appropriate getters (`getName`, or `isEnabled` for booleans) for reading or for the Binder to access nested objects, maps, or collections.
- Data types convertible from configuration values, e.g., `String`, `int`, `boolean`, `Duration`, `List<String>`, `Map<String,String>`.
- Bean **registration** with Spring; merely putting `@ConfigurationProperties` on a plain class does not guarantee it becomes a Spring bean.

In default JavaBean binding, the Binder relies on **JavaBean properties**, not arbitrary reflective access to private fields regardless of getters/setters. Writing `private String name;` alone and expecting the Binder to mutate it is a false assumption.

## 3. Complete Example: JavaBean with Scalars, List, Map, and Nested Object

The example below uses **Java 17+**, compatible with Spring Boot 3.3. Create `src/main/java/com/example/demo/config/AppProperties.java`:

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    // Initial values: preserved when the corresponding property is not bound.
    private String name = "Catalog";
    private boolean enabled = true;
    private int maxRetries = 3;
    private Duration connectTimeout = Duration.ofSeconds(2);

    // Collection: provide a setter to support standard binding formats.
    private List<String> regions =
            new ArrayList<>(List.of("ap-southeast-1"));

    // Pre-initialized Map can be updated by the Binder via getter.
    private final Map<String, String> labels = new LinkedHashMap<>();

    // Pre-initialized nested object can be updated via getter.
    private final Security security = new Security();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public List<String> getRegions() {
        return regions;
    }

    public void setRegions(List<String> regions) {
        this.regions = regions;
    }

    public Map<String, String> getLabels() {
        return labels;
    }

    public Security getSecurity() {
        return security;
    }

    public static class Security {
        private String username = "reader";
        private List<String> roles = new ArrayList<>(List.of("USER"));

        public String getUsername() {
            return username;
        }

        public void setUsername(String username) {
            this.username = username;
        }

        public List<String> getRoles() {
            return roles;
        }

        public void setRoles(List<String> roles) {
            this.roles = roles;
        }
    }
}
```

Intentionally demonstrated traits:

- `name`, `enabled`, `maxRetries`, and `connectTimeout` are scalars/typed values: all have getters and setters.
- `regions` is initialized with one element and **still has a setter**, supporting both indexed list configuration and comma-delimited strings.
- `labels` is a **pre-initialized Map**, `final` field with **getter only**: the Binder can mutate Map contents without reassigning the field reference.
- `security` is a **pre-initialized nested JavaBean**, `final` field with **getter only**: the Binder retrieves the existing instance, then invokes setters on its child properties.
- `Security.roles` is a List with getter/setter and an initial value. Each child property can be overridden independently where appropriate.

### Registering the Configuration Bean

In `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

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
```

`@ConfigurationPropertiesScan` scans classes annotated with `@ConfigurationProperties` in the application's package and subpackages, including `com.example.demo.config` in this example.

An alternative for explicit registration:

```java
@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class DemoApplication {
    // main(...) as usual
}
```

With the second approach, import `org.springframework.boot.context.properties.EnableConfigurationProperties`. Use one clear registration strategy; avoid accidentally declaring two equivalent beans by combining `@Component` and scanning improperly.

### Configuration File in `.properties`

```properties
# src/main/resources/application.properties
app.name=Order Service
app.enabled=false
app.max-retries=0
app.connect-timeout=5s

app.regions[0]=ap-southeast-1
app.regions[1]=eu-west-1

app.labels.team=platform
app.labels.env=staging

app.security.username=operator
app.security.roles[0]=AUDITOR
app.security.roles[1]=ADMIN
```

### Equivalent Configuration File in YAML

```yaml
# src/main/resources/application.yaml
app:
  name: Order Service
  enabled: false
  max-retries: 0
  connect-timeout: 5s
  regions:
    - ap-southeast-1
    - eu-west-1
  labels:
    team: platform
    env: staging
  security:
    username: operator
    roles:
      - AUDITOR
      - ADMIN
```

Both file examples are **alternatives**, not meant to sit simultaneously in the same location. When a single location contains both `.properties` and YAML sharing the same basename, Spring Boot gives `.properties` higher precedence.

### Result After Binding

When the application starts with either file and no higher-precedence source overrides it:

| Property of `AppProperties` | Initial Value | Value After Binding |
| --- | --- | --- |
| `name` | `"Catalog"` | `"Order Service"` |
| `enabled` | `true` | `false` |
| `maxRetries` | `3` | `0` |
| `connectTimeout` | `2s` | `5s` |
| `regions` | `["ap-southeast-1"]` | `["ap-southeast-1", "eu-west-1"]` |
| `labels` | Empty Map | `team=platform`, `env=staging` |
| `security.username` | `"reader"` | `"operator"` |
| `security.roles` | `["USER"]` | `["AUDITOR", "ADMIN"]` |

No manual `load()` or `bind()` call is needed in the application to receive these properties; `@ConfigurationProperties` is registered and Boot performs binding when creating/initializing the bean.

## 4. Getters and Setters Have Different Roles

### 4.1. Scalars Typically Require a Setter

For `String`, numbers, booleans, `Duration`, enums, etc., the standard JavaBean pattern is:

```java
private int maxRetries = 3;

public int getMaxRetries() {
    return maxRetries;
}

public void setMaxRetries(int maxRetries) {
    this.maxRetries = maxRetries;
}
```

The Binder maps configuration such as `app.max-retries=5` to property `maxRetries` and calls the setter with the converted integer. Without **a setter**, a read-only scalar will not normally be updated by the Binder under JavaBean binding; if you want immutable fields set at instantiation time, use constructor binding.

For booleans, the JavaBean getter name is typically `isEnabled()`:

```java
private boolean enabled = true;

public boolean isEnabled() { return enabled; }
public void setEnabled(boolean enabled) { this.enabled = enabled; }
```

`isEnabled` does not mean the default is true; it is solely the boolean getter naming convention. The setter can still receive `false`.

### 4.2. Getters Are Not Just for Services to Read Values

Getters also help the Binder locate an existing object to **mutate internally**. Two key cases:

```java
private final Map<String, String> labels = new LinkedHashMap<>();
public Map<String, String> getLabels() { return labels; }
```

and:

```java
private final Security security = new Security();
public Security getSecurity() { return security; }
```

In this Map/nested POJO case, the Binder obtains the reference via the getter and updates child entries/properties **without** needing `setLabels(...)` or `setSecurity(...)`.

Conversely, a getter-only property returning an **uninitialized** object cannot reliably bind nested data:

```java
// Risk: security is null and there is no setter to assign a new object.
private Security security;
public Security getSecurity() { return security; }
```

If you want the Binder to create the nested object when needed, add a setter:

```java
private Security security;

public Security getSecurity() { return security; }
public void setSecurity(Security security) { this.security = security; }
```

Then the Binder has a way to assign a new `Security` instance, provided the nested class can be instantiated appropriately. If you prefer no setter on the nested object, initialize it directly on the field or in the constructor:

```java
private final Security security = new Security();
public Security getSecurity() { return security; }
```

### 4.3. Getter-Only Maps Need a Mutable Instance

An initialized Map with a getter is normally sufficient:

```java
private final Map<String, String> labels = new HashMap<>();

public Map<String, String> getLabels() {
    return labels;
}
```

However, do not use an immutable Map if the Binder must update it directly:

```java
// Unsuitable as a getter-only Map for the Binder to add entries.
private final Map<String, String> labels = Map.of();

public Map<String, String> getLabels() {
    return labels;
}
```

`Map.of()` produces a Map whose contents cannot be modified; binding through the getter may fail or behave unexpectedly without a setter to replace the entire Map. A mutable `LinkedHashMap` or `HashMap` is better suited for this style of JavaBean binding.

## 5. Collections and Arrays: Exceptions to Remember

Spring Boot 3.3 supports special getter-only cases, yet **adding setters for Lists/collections is recommended** so binding works consistently across input formats.

### 5.1. List with a Setter: The Reliable Choice

```java
private List<String> regions = new ArrayList<>();

public List<String> getRegions() { return regions; }
public void setRegions(List<String> regions) {
    this.regions = regions;
}
```

Can be bound from `.properties` by index:

```properties
app.regions[0]=vn
app.regions[1]=sg
```

or as comma-delimited values:

```properties
app.regions=vn,sg
```

YAML:

```yaml
app:
  regions:
    - vn
    - sg
```

When the input is **a CSV string** `app.regions=vn,sg`, the Spring Boot 3.3 documentation specifies that **a setter is required** for collections in that binding mode. Therefore, do not rely on getter-only Lists as a general rule across all configuration formats.

### 5.2. Pre-Initialized Getter-Only Lists

An initialized and **mutable** List can be accessed via getter by the Binder in some cases, especially indexed element configuration:

```java
private final List<String> regions = new ArrayList<>();

public List<String> getRegions() {
    return regions;
}
```

However, that is not a reason to omit setters regardless of how data is supplied. Official documentation recommends **always adding setters for collections/arrays** because value representation and conversion affect whether the Binder mutates an existing List or assigns a new List. If a design mandates getter-only, choose clearly supported formats, keep the collection mutable, and do not rely on CSV binding.

### 5.3. `List.of()` and `Collections.unmodifiableList()`

Do not use an immutable collection as an initial value while expecting the Binder to add/remove elements:

```java
// List cannot be modified directly:
private final List<String> regions = List.of("vn");

public List<String> getRegions() {
    return regions;
}
```

A safer approach when wanting both a default list and a setter:

```java
private List<String> regions =
        new ArrayList<>(List.of("vn"));

public List<String> getRegions() { return regions; }
public void setRegions(List<String> regions) { this.regions = regions; }
```

Note the difference: `List.of("vn")` is an immutable List; `new ArrayList<>(List.of("vn"))` creates a mutable List containing the same initial element.

### 5.4. Nested Collections

If the nested object field is pre-initialized, the Binder can enter the child object and update its inner List using the child object's getter/setter:

```java
private final Security security = new Security();

public Security getSecurity() { return security; }

public static class Security {
    private List<String> roles = new ArrayList<>(List.of("USER"));

    public List<String> getRoles() { return roles; }
    public void setRoles(List<String> roles) { this.roles = roles; }
}
```

Input:

```properties
app.security.roles[0]=ADMIN
app.security.roles[1]=AUDITOR
```

If `app.security.roles` is bound from a higher-precedence source, **do not assume the initial `USER` element will automatically be appended**. Lists follow replacement semantics under precedence rules; if you want default roles merged alongside configured ones, implement an explicit merge step in application logic.

## 6. Initial Values: Fallback When Configuration Is Missing

Consider this JavaBean:

```java
@ConfigurationProperties(prefix = "app")
public class DefaultsProperties {
    private String displayName = "Catalog";
    private int retryCount = 3;
    private boolean enabled = true;

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { displayName = value; }

    public int getRetryCount() { return retryCount; }
    public void setRetryCount(int value) { retryCount = value; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean value) { enabled = value; }
}
```

Cases:

| Value in `Environment` | Result After Binding |
| --- | --- |
| No `app.display-name` | Retains `"Catalog"` |
| `app.display-name=Store` | `"Store"` |
| `app.display-name=` | Empty string `""` (if `String` type) |
| No `app.retry-count` | Retains `3` |
| `app.retry-count=0` | `0`, does not revert to `3` |
| No `app.enabled` | Retains `true` |
| `app.enabled=false` | `false`, does not revert to `true` |

An initial value **is not** a rule saying "reject 0, false, or empty string." Explicit values override defaults whenever they convert to the property type.

In particular, `int` and `boolean` have Java language defaults of `0` and `false` even when not assigned in code. Therefore **`retryCount == 0` does not prove the property was explicitly set to 0**, and **`enabled == false` does not prove an operator actively disabled the feature**. If you must distinguish undeclared from explicitly declared, use wrapper types `Integer`/`Boolean` with validation, or inspect property sources.

### Why Do Field Initializers Run Before the Binder?

A new Java object follows this lifecycle:

```text
new DefaultsProperties()
  ├─ JVM default values
  ├─ field initializers, e.g. retryCount = 3
  ├─ constructor body (if any)
  └─ Binder assigns discovered properties via JavaBean setters
       └─ unbound properties retain their prior values
```

If a no-arg constructor explicitly assigns a different value to an initialized field, the pre-binding value is whatever the constructor produces. The Binder does not distinguish whether a default came from a field initializer or the constructor; it simply receives an initial object to update.

## 7. Nested JavaBeans: Pre-Initialized vs. Binder-Created

### 7.1. Pre-Initialized Without a Parent Setter

```java
@ConfigurationProperties(prefix = "app")
public class ServiceProperties {
    private final Client client = new Client();

    public Client getClient() {
        return client;
    }

    public static class Client {
        private String host = "localhost";
        private int port = 8080;

        public String getHost() { return host; }
        public void setHost(String host) { this.host = host; }
        public int getPort() { return port; }
        public void setPort(int port) { this.port = port; }
    }
}
```

Configuration:

```yaml
app:
  client:
    host: api.example.test
```

After binding, `client.host = "api.example.test"` and `client.port = 8080`, because `port` is absent from configuration. The `client` field remains the originally instantiated object; the Binder only updates child properties.

### 7.2. Not Pre-Initialized, with a Setter

```java
private Client client;

public Client getClient() { return client; }
public void setClient(Client client) { this.client = client; }
```

When `app.client.host` is present, the Binder can instantiate `Client` (if it has an appropriate constructor), bind child properties, and assign it via `setClient(...)`. If no child properties exist, `client` can remain `null`; this **differs from** pre-initializing an object holding defaults.

### 7.3. Nested Property Naming Follows Field Names, Not Class Names

For:

```java
private final Client client = new Client();
```

the property name is `app.client.host`, not `app.Client.host` or `app.ServiceProperties.Client.host`. The Binder constructs property paths from **prefix + JavaBean property name + nested object property**.

For a `readTimeout` field inside `Client`, the recommended canonical form is `app.client.read-timeout`. Spring Boot supports relaxed binding between kebab-case in files and camelCase in Java.

## 8. JavaBean Defaults and Configuration from Multiple PropertySources

Initialized values serve as fallbacks **after the Binder evaluates effective configuration sources**; a field initializer is not a `PropertySource` placed at some priority rank in `Environment`.

Suppose the field is:

```java
private String name = "Catalog";
public String getName() { return name; }
public void setName(String name) { this.name = name; }
```

And `application.properties`:

```properties
app.name=FileName
```

If executed as:

```bash
java -jar myapp.jar --app.name=CliName
```

The final value on the bean is `CliName` because command-line properties have higher precedence than files. Only when no source provides `app.name` does the field retain `Catalog`.

This is **two steps**:

1. `Environment`/Binder determines the effective configuration value across multiple PropertySources.
2. The Binder updates the matching JavaBean property or leaves it untouched if no matching property exists.

Do not write constructor code that manually calls `System.getenv()` to build custom precedence logic just to override properties; that breaks consistency with Config Data ordering, JVM system properties, and command-line arguments.

### Empty String Is an Explicit Value

```bash
java -jar myapp.jar --app.name=
```

When the Binder sees a String property present with an empty value, the setter receives `""` and overwrites the `"Catalog"` default. If business rules require a non-empty name, use `@NotBlank` validation; field initializers do not turn empty strings back into defaults.

### Boolean false and Zero Are Valid Values

```bash
java -jar myapp.jar --app.enabled=false --app.max-retries=0
```

Even though the JavaBean initializes `enabled=true` and `maxRetries=3`, the bound values are `false` and `0`. They are meaningful operational choices, such as disabling a feature and disabling retries.

### Note on Unconvertible Properties

A setting like `app.max-retries=abc` is not "missing," and will not automatically fall back to the initial value `3`. The Binder can throw a conversion error depending on property type and binding options. Fix mistyped configuration or handle validation/exceptions properly instead of hiding errors behind defaults.

## 9. Binding Lists and Maps Across Overriding Sources

When two PropertySources both contain collections or maps, you must understand **multi-source binding semantics** beyond just getters and setters.

### 9.1. A List from a Higher-Precedence Source Normally Replaces the Entire List

Packaged file:

```yaml
# application.yaml
app:
  regions:
    - vn
    - sg
```

Dev profile file:

```yaml
# application-dev.yaml
app:
  regions:
    - localhost
```

When the `dev` profile is active, `regions` is bound from the higher-precedence source, producing:

```text
["localhost"]
```

Do not expect lists from lower sources to be concatenated with lists from higher sources. Similarly, default elements created in a Java field initializer are not guaranteed to be appended to newly configured lists.

If you want "append new values to a default list" behavior, model and implement the merge explicitly in business code, or use a suitable structure (such as a Map with explicit keys) instead of relying implicitly on the Binder.

### 9.2. Maps Can Merge Keys Across Multiple Sources

Suppose `labels` is a pre-initialized empty Map:

```java
private final Map<String, String> labels = new LinkedHashMap<>();
public Map<String, String> getLabels() { return labels; }
```

Shared file:

```properties
app.labels.team=platform
app.labels.env=dev
```

Higher-precedence source:

```properties
app.labels.env=prod
app.labels.owner=backend
```

The result normally contains three keys:

```text
team  -> platform
env   -> prod
owner -> backend
```

Map binding can merge **keys** across sources, while duplicate keys take values from the higher-precedence source. This differs from lists. Maps holding nested objects can even pull different child properties from different sources.

If a key contains `/` or special characters, use Map bracket notation, e.g., `app.labels.[/service/api]=active`; in YAML, quote the key `"[/service/api]"` to preserve the literal name.

## 10. Relaxed Binding and Type Conversion

`@ConfigurationProperties` supports **relaxed binding**, so config keys do not have to match exact Java field casing as long as they follow the rules.

| JavaBean Property | Canonical Form in File | Suggested Env Var |
| --- | --- | --- |
| `maxRetries` | `app.max-retries` | `APP_MAXRETRIES` |
| `connectTimeout` | `app.connect-timeout` | `APP_CONNECTTIMEOUT` |
| `displayName` | `app.display-name` | `APP_DISPLAYNAME` |
| `security.username` | `app.security.username` | `APP_SECURITY_USERNAME` |
| `regions[0]` | `app.regions[0]` | `APP_REGIONS_0_` |

Recommended canonical naming: **lowercase kebab-case**. For environment variables under Boot rules: `.` becomes `_`, `-` is removed, letters become uppercase; list indices are wrapped with `_`.

The Binder also performs type conversion:

```properties
app.enabled=false
app.max-retries=0
app.connect-timeout=750ms
```

These bind to `boolean false`, `int 0`, and `Duration.ofMillis(750)`. For durations, write explicit units like `ms`, `s`, `m` to avoid guessing how bare numbers are interpreted.

Command-line example:

```bash
java -jar myapp.jar \
  --app.name=Catalog-API \
  --app.connect-timeout=5s \
  --app.enabled=false
```

When command-line properties are processed by Spring Boot by default, they override matching properties from files.

### Prefix and Property Names

`@ConfigurationProperties(prefix = "app")` maps keys starting with `app.`. For example:

- `app.name` → `setName(...)`.
- `app.max-retries` → `setMaxRetries(...)`.
- `app.security.username` → getter `getSecurity()` then `setUsername(...)` on the nested JavaBean.

Do not invent prefixes with uppercase letters or mixed casing; prefer lowercase names with dots for hierarchy and kebab-case for compound words.

## 11. JavaBean Binding vs. Constructor Binding

Spring Boot 3.3 supports both models, but how "default values" are expressed differs.

| Aspect | JavaBean Binding | Constructor Binding |
| --- | --- | --- |
| Instantiation | No-arg constructor; Binder mutates object | Binder invokes constructor with bound arguments |
| Are setters required? | Scalars typically need setters; initialized maps/nested objects have exceptions | No setters needed; assigned via constructor |
| Initial values | Field initializers or no-arg constructor | Parameter defaults / `@DefaultValue` per constructor rules |
| Mutability | Typically mutable | Can be immutable; suits records |
| Getter-only collections | Limited by format and mutability | Values passed directly into constructor |
| Purpose | Mutable config beans, including Spring-created beans | Immutable config, clear dependencies via constructor |

Record example (for comparison, **not JavaBean binding**):

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app")
public record ImmutableAppProperties(
        @DefaultValue("Catalog") String name,
        @DefaultValue("true") boolean enabled) {
}
```

`@DefaultValue` in this example is for **constructor binding**. It does not replace field initializer assignments in JavaBeans. If you create a JavaBean with `private boolean enabled = true;`, its default logic comes from the object's state before setters are called.

**Do not accidentally trigger constructor binding:** for a `@ConfigurationProperties` class registered via scan/`@EnableConfigurationProperties`, a single parameterized constructor may be picked by Boot for constructor binding. To use JavaBean binding, provide an appropriate no-arg constructor and follow how the Binder resolves constructors. Lombok annotations like `@AllArgsConstructor` can alter constructor signatures; choose Lombok annotations carefully to avoid unintentionally switching binding mechanisms.

For beans instantiated by Spring via `@Component` or `@Bean`, constructor binding of `@ConfigurationProperties` does not apply in the same way as when registering classes via configuration-properties scanning/enablement. You can use **JavaBean binding** on normally created Spring beans, while keeping config clear and avoiding injecting dependencies into pure configuration classes.

## 12. Proper Bean Registration: Scan, Enable, Component, and @Bean

### Option A — `@ConfigurationPropertiesScan`

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
```

Use when scanning explicit configuration classes across application packages. `@ConfigurationPropertiesScan` **does not scan `@Component`-annotated classes in the same way**; avoid relying on overlapping mechanisms.

### Option B — `@EnableConfigurationProperties`

```java
@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class DemoApplication {
}
```

Use when you want to register exact known configuration classes. This is also the recommended registration mechanism for constructor binding with custom classes.

### Option C — `@Component` with `@ConfigurationProperties`

```java
@Component
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private String name = "Catalog";

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
```

This lets Spring instantiate the bean normally and applies JavaBean property binding. It works well for simple mutable classes, but should not be used to attempt constructor binding of immutable objects whose constructors Spring treats as dependency injection.

### Option D — On a `@Bean` Method

When configuring a third-party library component whose source code you do not own:

```java
@Configuration(proxyBeanMethods = false)
public class LibraryConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "client.pool")
    public LibraryPoolProperties libraryPoolProperties() {
        return new LibraryPoolProperties();
    }
}
```

`LibraryPoolProperties` in this example is a hypothetical library class with matching JavaBean properties; it is not a built-in Spring Boot class. `@ConfigurationProperties` on the method tells the Binder to update the **returned instance**. It cannot fix third-party class APIs that lack corresponding getters/setters/bindable properties.

### Do Not Arbitrarily Inject Services into Pure Configuration Classes

A `@ConfigurationProperties` class should primarily represent external configuration data. Instead of injecting `DataSource`, `RestClient`, or services into it, inject **AppProperties** into the services that consume it. That keeps dependencies clean and avoids mixing container lifecycle with the property model.

## 13. Validation: Default Values Do Not Replace Data Validation

Example adding validation:

```java
package com.example.demo.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public class ValidatedAppProperties {

    @NotBlank
    private String name = "Catalog";

    @Min(0)
    private int maxRetries = 3;

    @Valid
    private final Security security = new Security();

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public Security getSecurity() { return security; }

    public static class Security {
        @NotBlank
        private String username = "reader";

        public String getUsername() { return username; }
        public void setUsername(String username) {
            this.username = username;
        }
    }
}
```

Meaning:

- `@NotBlank`: name and username cannot be null, empty, or whitespace-only.
- `@Min(0)`: `maxRetries` of 0 is valid, negative values are invalid.
- `@Valid`: enables cascading checks into nested `Security` so child constraints are evaluated in context.

If configuration supplies `app.name=`, the empty String does not revert to `"Catalog"`; validation rejects it. If configuration supplies `app.max-retries=-1`, validation reports an error instead of falling back to 3. For the example above, a compatible Bean Validation implementation is required, usually via `spring-boot-starter-validation`, along with registering the configuration properties class in the context.

In Spring Boot, validating nested properties also involves nuances when child properties are not bound; placing `@Valid` on the nested field expresses the intent to validate the child object even when pre-initialized.

**Separate three concerns:**

1. *Field initializer*: provides an initial value.
2. *Binder*: modifies values based on effective configuration.
3. *Validation*: checks whether the final object satisfies business requirements.

Do not use defaults to hide malformed or constraint-violating configuration.

## 14. Consuming the Bound Object in the Application

Example of a service receiving `AppProperties` via constructor:

```java
package com.example.demo.service;

import com.example.demo.config.AppProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final AppProperties properties;

    public CatalogService(AppProperties properties) {
        this.properties = properties;
    }

    public void printEffectiveConfig() {
        System.out.println(properties.getName());
        System.out.println(properties.isEnabled());
        System.out.println(properties.getMaxRetries());
        System.out.println(properties.getConnectTimeout());
        System.out.println(properties.getRegions());
        System.out.println(properties.getLabels().get("team"));
        System.out.println(properties.getSecurity().getUsername());
    }
}
```

In real applications, avoid printing passwords/tokens or the entire environment. If a configuration class contains secrets, log only non-sensitive values needed for diagnostics. The `AppProperties` bean is managed by Spring; services do not call setters again to "trigger binding."

### Brief Comparison with `@Value`

```java
@Value("${app.name:Catalog}")
private String name;
```

`@Value` is suitable for reading a few simple properties. When configuration involves nested objects, Lists, Maps, validation requirements, and multiple properties under a shared prefix, `@ConfigurationProperties` offers a cleaner type-safe model and fuller relaxed binding. Do not use `@Value` expecting it to bind complex nested objects by JavaBean conventions.

## 15. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| String property always keeps initial value | No config source with matching key, bean unregistered, or missing setter | Check prefix, sources, `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`, and `setXxx` |
| Getter works, but Binder never changes scalar | Getter only, missing appropriate setter | Add setter or switch completely to constructor binding |
| `client.host` does not bind to nested object | `client` is uninitialized and has no setter | Pre-initialize nested object + getter, or add setter for Binder to create |
| Getter-only Map does not receive entries | Map is uninitialized or immutable | Use mutable `new HashMap<>()`/`new LinkedHashMap<>()` and getter |
| Getter-only List fails on `a,b` | CSV binding requires a setter for collections | Add setter for List; do not rely on getter-only for all formats |
| Default List loses elements on profile override | List is replaced by higher-precedence source | Specify complete List or implement explicit merge logic |
| Configuration bean missing from context | Only has `@ConfigurationProperties`, not registered | Add scan/enable or register the bean appropriately |
| JavaBean class treated as constructor-bound | Single parameterized constructor, or unwanted Lombok constructor | Provide appropriate no-arg constructor or intentionally use constructor binding |
| `maxRetries=0` does not keep default 3 | Expected behavior: `0` is an explicit value | Do not use `0` as a sentinel for missing |
| `enabled=false` does not keep default true | Expected behavior: `false` overrides default | Separate "unconfigured" from "explicitly disabled" |
| Value `abc` set for numeric property | Conversion failed | Fix config to a valid value; apply validation |
| Getter returns `List.of(...)` and Binder fails to update | Immutable collection | Use a mutable collection and setter |
| YAML config fails to bind to camelCase field | Wrong key indentation level or prefix | Check YAML indentation and canonical kebab-case names |
| Using static field as configuration property | JavaBean binding does not bind static properties | Change to instance field |
| Nested property binds, but constraints are ignored | Missing validation or `@Valid` on nested member | Add appropriate validation and dependency |
| Using `@ConfigurationPropertiesScan` on `@Component` class | Config scanning excludes `@Component` classes | Register cleanly via one bean mechanism and avoid duplicates |

### Code Snippet Ineligible for JavaBean Binding

```java
@ConfigurationProperties(prefix = "app")
public class IncompleteProperties {
    private String name = "Catalog";
}
```

Even with `app.name=NewName`, the class lacks JavaBean getter/setter for `name`, so the Binder cannot update the field via standard JavaBean binding. Minimal fix:

```java
@ConfigurationProperties(prefix = "app")
public class FixedProperties {
    private String name = "Catalog";

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
```

You also need to register the class as a configuration bean as instructed if you want the application to perform binding automatically.

## 16. Checking Effective Values and Finding Why They Differ from Defaults

If a field keeps its initialized value, do not immediately conclude the Binder is broken. The config property might genuinely be absent from loaded PropertySources, or the key name might be misspelled.

A snippet inspecting `Environment` after startup:

```java
@Configuration
public class ConfigDiagnostics {

    @Bean
    ApplicationRunner showSource(Environment env, AppProperties app) {
        return args -> {
            String key = "app.max-retries";
            System.out.println("Present in Environment: "
                    + env.containsProperty(key));
            System.out.println("Raw effective value: "
                    + env.getProperty(key));
            System.out.println("Bound bean value: "
                    + app.getMaxRetries());
        };
    }
}
```

Required imports for the example:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
```

With the code above:

- `env.containsProperty(key) == false` and bean having `maxRetries=3` is valid when no config is supplied for that key.
- `env.containsProperty(key) == true` and `env.getProperty(key)="0"` causes a valid JavaBean with a setter to bind `maxRetries=0`.
- If the raw property exists yet the bean didn't change, check bean registration, JavaBean property name, setter, conversion, and nested object path.
- If multiple sources contain the same key, the effective property follows Spring Boot precedence; an environment variable or command-line option may override the file you are inspecting.

When using Spring Boot Actuator, `/actuator/configprops` can display bound configuration properties (with display/sanitization policies), and `/actuator/env` helps trace property sources. Only enable, secure, and use them for diagnostics; avoid exposing secrets.

## 17. Design Decision Table

| Goal | Implementation |
| --- | --- |
| A String with a default that files can override | Field initializer + getter/setter |
| Boolean enabled by default that operators can disable | `boolean enabled = true` + `isEnabled/setEnabled` |
| Retry defaults to 3, and 0 is valid | `int maxRetries = 3` + getter/setter; `@Min(0)` validation |
| Nested object always exists and holds defaults | `private final Nested nested = new Nested();` + getter |
| Nested object exists only when configured | Uninitialized field + appropriate getter/setter |
| Map receives entries from config | Mutable initialized Map + getter (setter optional) |
| List accepts both comma strings and indexed/YAML | Mutable List + getter/setter |
| Fields immutable after creation | Constructor binding / record |
| Change defaults per environment | Configure via Config Data/OS env/JVM/CLI and PropertySource order |
| Reject missing or rule-violating values | Bean Validation + `@Validated`/constraints |
| Verify actual bound value | Inject bean + read getter; cross-check key in `Environment` |

## 18. Official References

- Spring Boot **3.3 Reference — Externalized Configuration**, especially *Type-safe Configuration Properties*, *JavaBean Properties Binding*, *Constructor Binding*, *Relaxed Binding*, *Merging Complex Types*, *PropertySource Order*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot **3.3 Reference — Configuration Properties**, practical guide to naming and registering config: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot **3.3 API — `@ConfigurationProperties`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Framework — JavaBeans, `Environment`, and integrated Bean Validation: https://docs.spring.io/spring-framework/reference/core/beans/environment.html

**Rule of thumb:** JavaBean binding instantiates a mutable object and **assigns properties present in effective configuration sources** via JavaBean accessors. Scalars require setters; **pre-initialized Maps** and **pre-initialized nested objects** can bind via getters; **Lists/arrays should have setters**, especially when accepting comma-delimited strings. **Field initializers are initial values**, and do not take precedence over explicit values like `0`, `false`, or empty strings.
