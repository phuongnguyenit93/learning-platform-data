# Comparing JavaBean, Immutable Class, and Record Across the Same `@ConfigurationProperties` Model

## 1. Goal and Context

Spring Boot supports **externalized configuration**: a single application build can accept settings from YAML, Properties, environment variables, Java system properties, and command-line arguments. Instead of scattering `@Value` throughout Java code, we typically group related properties into a typed object and bind them with `@ConfigurationProperties`.

When designing a configuration object, three Java forms are worth considering:

1. **Mutable JavaBean:** has a no-args constructor, getters, and setters; the binder instantiates the object and sets each property.
2. **Immutable class:** has `final` fields and a parameterized constructor; the binder creates the object using constructor binding.
3. **Java record:** concisely models data using record components; constructor binding is usually inferred from the canonical constructor.

All three forms can represent **the exact same configuration model**. They differ in how objects are instantiated, Java APIs, default values, mutability, and design trade-offs.

This lesson uses the same `app.delivery` property group for a step-by-step comparison rather than inventing three mismatched property sets and comparing unequal outcomes.

> Example scope: Java 17+ and Spring Boot 3.x. Spring Boot 2.x has differences in `@ConstructorBinding` placement and validation namespaces, noted in the version remarks.

## 2. A Shared Configuration Model for All Three Approaches

Suppose a service sends data to a partner system. It needs four properties:

| Configuration Property | Java Type | Role |
| --- | --- | --- |
| `app.delivery.endpoint` | `String` | Target address for sending requests |
| `app.delivery.connect-timeout` | `Duration` | Connection timeout |
| `app.delivery.max-retries` | `int` | Maximum retry attempts |
| `app.delivery.enabled` | `boolean` | Whether delivery is enabled |

A `src/main/resources/application.yml` file:

~~~yaml
app:
  delivery:
    endpoint: https://api.example.test
    connect-timeout: 5s
    max-retries: 3
    enabled: true
~~~

Equivalent in `application.properties`:

~~~properties
app.delivery.endpoint=https://api.example.test
app.delivery.connect-timeout=5s
app.delivery.max-retries=3
app.delivery.enabled=true
~~~

Desired values after binding:

~~~text
endpoint       = "https://api.example.test"   (String)
connectTimeout = Duration.ofSeconds(5)        (Duration)
maxRetries     = 3                            (int)
enabled        = true                         (boolean)
~~~

Spring Boot uses **relaxed binding**: `connect-timeout` from the file maps to `connectTimeout` in Java; `max-retries` maps to `maxRetries`. `5s` is converted from text to `Duration`.

To keep comparisons clean, each code snippet below is **one alternative** for the same configuration, not a requirement to register all three properties beans simultaneously. Putting all three classes under one `@ConfigurationPropertiesScan` would create three separate beans reading `app.delivery`, muddying a single-style demonstration.

## 3. Approach 1 — Mutable JavaBean

### 3.1. Class Declaration

A JavaBean typically uses a no-args constructor and `getXxx`/`setXxx` (or `isXxx` for booleans).

~~~java
package com.example.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public class DeliveryJavaBeanProperties {

    @NotBlank
    private String endpoint;

    @NotNull
    private Duration connectTimeout;

    @Min(0)
    private int maxRetries;

    private boolean enabled;

    public DeliveryJavaBeanProperties() {
        // No-args constructor to instantiate JavaBean.
    }

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

With the YAML in Section 2, after Spring Boot binds it, this bean holds `endpoint=https://api.example.test`, `connectTimeout=PT5S`, `maxRetries=3`, and `enabled=true`.

### 3.2. Binder Mechanics

~~~text
Spring sees @ConfigurationProperties("app.delivery")
                |
                v
     new DeliveryJavaBeanProperties()
                |
                v
       setEndpoint("https://...")
       setConnectTimeout(5 seconds)
       setMaxRetries(3)
       setEnabled(true)
                |
                v
       properties bean ready for use
~~~

Core point: the binder needs a way to **write** values into the properties. For typical JavaBeans, that is setters. A class may contain setter logic, though side effects should be avoided: a properties configuration object is best kept solely for holding settings.

### 3.3. Default Values in JavaBeans

Defaults can be declared directly when the object is instantiated:

~~~java
private Duration connectTimeout = Duration.ofSeconds(5);
private int maxRetries = 2;
private boolean enabled = false;
~~~

If external configuration **does not declare** `max-retries`, the field keeps `2`. If `max-retries: 3` is present, the binder overwrites it with `3`.

This is an **object-level default**, and does not automatically create an `app.delivery.max-retries=2` entry in `Environment`. Code calling `environment.getProperty("app.delivery.max-retries")` may still receive `null` if no source explicitly declares that key.

### 3.4. Strengths and Limitations

**Strengths:** familiar to many Java/Spring projects, clear setter binding, easy to use with third-party library objects exposing JavaBean APIs, and able to pre-initialize collections/nested objects before binding.

**Limitations:** verbose getter/setter boilerplate; the object can be mutated after initialization due to public setters; a consuming bean accidentally calling `setMaxRetries(...)` mutates shared state and creates hard-to-trace bugs. When configuration is fixed truth for the duration of a startup, allowing post-init mutation is usually undesirable.

## 4. Approach 2 — Immutable Class with Constructor Binding

### 4.1. Declaration with Fields

In an immutable class, there are no setters; all fields are supplied via constructor. Here is the full declaration:

~~~java
package com.example.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public final class DeliveryImmutableProperties {

    @NotBlank
    private final String endpoint;

    @NotNull
    private final Duration connectTimeout;

    @Min(0)
    private final int maxRetries;

    private final boolean enabled;

    public DeliveryImmutableProperties(
            String endpoint,
            Duration connectTimeout,
            int maxRetries,
            boolean enabled) {
        this.endpoint = endpoint;
        this.connectTimeout = connectTimeout;
        this.maxRetries = maxRetries;
        this.enabled = enabled;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
~~~

In Spring Boot 3.x, a `@ConfigurationProperties` class with **a single parameterized constructor** is normally detected automatically for constructor binding; adding `@ConstructorBinding` is not mandatory in this situation.

### 4.2. Binder Mechanics

~~~text
Spring sees @ConfigurationProperties("app.delivery")
                   |
                   v
        looks up effective values
                   |
                   v
     convert endpoint        → String
     convert connect-timeout → Duration
     convert max-retries     → int
     convert enabled         → boolean
                   |
                   v
new DeliveryImmutableProperties(endpoint, timeout, retries, enabled)
                   |
                   v
     fully initialized object
~~~

The Binder **does not create an empty object and call setters one by one**. It prepares the arguments and invokes the constructor. Once constructed, there is no `setEndpoint` API to alter fields.

Note that `final` and the absence of setters create **immutability at the field-reference level**, without automatically guaranteeing deep immutability if a field points to a `List` or mutable object. Because this example uses only `String`, `Duration`, and primitives, state is relatively simple.

### 4.3. Registration Requirements for Constructor Binding to Work

A constructor-bound object must be registered through Spring Boot's configuration properties mechanism, for example:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DeliveryImmutableProperties.class)
public class DeliveryPropertiesConfiguration {
}
~~~

Or use `@ConfigurationPropertiesScan` to scan classes annotated with `@ConfigurationProperties`.

Do not use the same constructor-bound object as a regular bean created via `@Component`, `@Bean` method, or `@Import` expecting the binder to pass values into its constructor: that is a **different bean-creation mechanism**. If you need a vendor object created via `@Bean`, bind your own properties class separately and pass it into the factory method.

### 4.4. Multiple Constructor Choices

If a class has **multiple constructors**, Spring Boot needs to know which one is used for constructor binding. In Spring Boot 3.x, `@ConstructorBinding` can be placed on the selected constructor:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.sample")
public class SampleProperties {
    private final String name;

    public SampleProperties() {
        this.name = "fallback";
    }

    @ConstructorBinding
    public SampleProperties(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

This illustrates **placing the annotation on the constructor** in Spring Boot 3.x. Do not copy Spring Boot 2.x guides that put `@ConstructorBinding` on the class without checking the package and API of your version.

### 4.5. Parameter Compilation Note

Constructor binding needs constructor parameter names to map to property names. With regular Java classes, the build must retain parameter names, typically via the `-parameters` compiler option. Spring Boot's Maven parent or Spring Boot's Gradle plugin normally configures this automatically for standard projects.

A subtle bug in custom build setups is bytecode missing parameter-name metadata, leaving the constructor binder unable to tell which keys `endpoint` or `maxRetries` correspond to. If binding fails even though YAML and the constructor look correct, inspect Java compiler and build plugin settings.

## 5. Approach 3 — Record with Constructor Binding

Java records represent a fixed group of data components without manually writing boilerplate getters and constructors.

~~~java
package com.example.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryRecordProperties(
        @NotBlank String endpoint,
        @NotNull Duration connectTimeout,
        @Min(0) int maxRetries,
        boolean enabled) {
}
~~~

In just a few lines, the Java compiler generates the core parts of the record:

- A canonical constructor accepting four components.
- Accessors `endpoint()`, `connectTimeout()`, `maxRetries()`, and `enabled()`.
- `equals(...)`, `hashCode()`, and `toString()` based on record components.

Spring Boot 3.x supports constructor binding for records. When a record has a single standard canonical constructor, **there is no need for `@ConstructorBinding`**.

Registration:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DeliveryRecordProperties.class)
public class DeliveryPropertiesConfiguration {
}
~~~

Or allow `@ConfigurationPropertiesScan` to discover the record.

### 5.1. Java Access Syntax Differs from JavaBeans

With the JavaBean or immutable class getters shown earlier:

~~~java
String endpoint = props.getEndpoint();
int retries = props.getMaxRetries();
~~~

With a record:

~~~java
String endpoint = props.endpoint();
int retries = props.maxRetries();
~~~

**Do not** use `props.getEndpoint()` on the record above, because records generate `endpoint()` instead of JavaBean getters.

### 5.2. A Record Does Not Protect Secret Data

A record's `toString()` can display component values. If a record contains `apiKey`, `password`, or tokens, logging the object directly can leak secrets.

Avoid:

~~~java
// Do not log the entire record if it contains sensitive data.
// log.info("Delivery config: {}", properties);
~~~

Log only selected, masked details, or avoid logging sensitive configuration altogether. Records have `final` references, yet do not encrypt secrets or hide them from `toString()`.

## 6. What Values Do All Three Approaches Produce from the Same File?

Given the shared file:

~~~yaml
app:
  delivery:
    endpoint: https://api.example.test
    connect-timeout: 5s
    max-retries: 3
    enabled: true
~~~

All three properties models (when **registered via their corresponding appropriate mechanism**) represent the same configuration:

| Effective Value | JavaBean | Immutable Class | Record |
| --- | --- | --- | --- |
| Endpoint | `getEndpoint()` → sample URL | `getEndpoint()` → sample URL | `endpoint()` → sample URL |
| Timeout | `getConnectTimeout()` → `PT5S` | `getConnectTimeout()` → `PT5S` | `connectTimeout()` → `PT5S` |
| Max retries | `getMaxRetries()` → `3` | `getMaxRetries()` → `3` | `maxRetries()` → `3` |
| Enabled | `isEnabled()` → `true` | `isEnabled()` → `true` | `enabled()` → `true` |

**Identical configuration values do not mean identical object-creation mechanics.** A JavaBean instantiates an object and populates properties via setters. Constructor binding on an immutable class or record passes converted values directly into the constructor.

For example, if the application starts with:

~~~bash
java -jar app.jar --app.delivery.connect-timeout=9s
~~~

when Spring Boot allows command-line properties and no higher-precedence source overrides it, **all three** approaches can receive a `9s` timeout. The `@ConfigurationProperties` model does not change source precedence rules based on Java class style.

## 7. Registration: Choose One Model per Experiment

### 7.1. `@EnableConfigurationProperties` — Explicit Choice

To test the JavaBean:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DeliveryJavaBeanProperties.class)
public class DeliveryPropertiesConfiguration {
}
~~~

To test the immutable class, change only the class in the annotation:

~~~java
@EnableConfigurationProperties(DeliveryImmutableProperties.class)
~~~

To test the record:

~~~java
@EnableConfigurationProperties(DeliveryRecordProperties.class)
~~~

Place one of these configurations inside a package scanned by `@SpringBootApplication` or register it into the context appropriately. Do not leave all three classes registered simultaneously if the goal is verifying **a single representative model**.

### 7.2. `@ConfigurationPropertiesScan` — Package-Scanning Option

~~~java
package com.example;

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

The scan annotation finds `@ConfigurationProperties` classes within the package scope. Therefore, when using it in real projects, keep only intentional properties classes in scanned packages or specify scan packages explicitly.

If you put all three demo classes in the same package and enable general scanning, all three get registered; those are **three separate beans sharing a prefix**, not one bean morphing from a JavaBean into a record.

### 7.3. Do Not Confuse `@Component` with Constructor-Bound Properties

A mutable JavaBean can exist as a regular Spring component and be bound with JavaBean semantics when configured appropriately. However, constructor binding for immutable classes and records **does not** use regular bean-creation mechanisms like `@Component`.

To avoid confusion when working with dedicated `@ConfigurationProperties`, prefer `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`; reserve `@Component` for beans genuinely managed by Spring through normal injection and component lifecycle.

### 7.4. The `@Bean` Case for Third-Party Libraries

If you do not own a library class:

~~~java
@Bean
@ConfigurationProperties(prefix = "vendor.pool")
VendorPoolConfig vendorPoolConfig() {
    return new VendorPoolConfig();
}
~~~

Spring calls the factory method to obtain an instance and binds writable properties onto it; this is **JavaBean binding**, not Spring Boot passing values into an immutable constructor. If the library only supports constructors or builders, bind your own properties class and construct the vendor object inside `@Bean`.

## 8. How Do JavaBean, Immutable Class, and Record Differ?

| Criterion | Mutable JavaBean | Immutable Class | Java Record |
| --- | --- | --- | --- |
| How binder sets values | Calls setters after instantiation | Passes into constructor | Passes into canonical constructor |
| Typical constructor | No-args | Parameterized constructor | Java-generated canonical constructor |
| Public setters | Yes | No | No |
| `final` fields | Not required | Usually present | Record component backing fields are final |
| Boilerplate | Lots of getters/setters | Constructor + getters + `final` | Concise |
| Accessor API | `getXxx()`, `isXxx()` | Developer-written getters | `xxx()` |
| Standard registration for constructor binding | Not required | Scan or EnableConfigurationProperties | Scan or EnableConfigurationProperties |
| Defaults via field initializers | Easy | Does not automatically supply constructor args | No JavaBean-style instance field initializers |
| Defaults for constructor args | Not the primary mechanism | `@DefaultValue` on parameter | `@DefaultValue` on record component |
| Logic during creation | Constructor/setters can have logic | Constructor can have logic | Compact/canonical constructor can have logic |
| Generated `equals`/`hashCode`/`toString` | No | No | Yes |
| Mutability after creation | Possible via setters | Not via setters | Not via setters |
| Best suited for | Legacy/JavaBean-compatible classes | Complex API/constructor control | Concise config DTOs, fixed data |

"Immutable" in the table refers to having no setters and non-reassignable fields. If a class or record holds a mutable `List`, callers can still mutate list contents through the reference unless defensively copied.

## 9. Default Values: Same Meaning, Different Expression

Suppose we remove two keys from YAML:

~~~yaml
app:
  delivery:
    endpoint: https://api.example.test
    connect-timeout: 5s
~~~

We expect `maxRetries=2` and `enabled=false` when no overrides exist.

### 9.1. JavaBean — Field Initializers

~~~java
private int maxRetries = 2;
private boolean enabled = false;
~~~

If properties are not supplied, the object already holds defaults from creation time. The binder preserves those values.

### 9.2. Immutable Class — `@DefaultValue` on Constructor Parameters

In Spring Boot 3.x, `org.springframework.boot.context.properties.bind.DefaultValue` can be used:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

// Fields/getters and @ConfigurationProperties annotation are the same as the sample above.
public DeliveryImmutableProperties(
        String endpoint,
        Duration connectTimeout,
        @DefaultValue("2") int maxRetries,
        @DefaultValue("false") boolean enabled) {
    this.endpoint = endpoint;
    this.connectTimeout = connectTimeout;
    this.maxRetries = maxRetries;
    this.enabled = enabled;
}
~~~

`@DefaultValue("2")` specifies the value used when the corresponding parameter has no property. The string inside the annotation converts to `int`; similarly for `boolean`.

### 9.3. Record — `@DefaultValue` on Record Components

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryRecordProperties(
        String endpoint,
        Duration connectTimeout,
        @DefaultValue("2") int maxRetries,
        @DefaultValue("false") boolean enabled) {
}
~~~

Here `@DefaultValue` is binding metadata; it does not alter YAML syntax and does not inject keys into `Environment`.

### 9.4. A Missing Primitive Does Not Mean Valid Configuration

Without `@DefaultValue`, if a primitive `int` constructor parameter has no property, absence can result in the primitive default (`0`); for `boolean`, `false`. Yet `0` is not always valid in business rules.

If you want to **distinguish a missing key from a user explicitly setting 0**, consider using the `Integer` wrapper paired with `@NotNull`, or suitable validation/constructor logic.

Do not use primitive `int` expecting `@Min(0)` to detect when the key was omitted: `0` still satisfies `>= 0`.

## 10. Validation: Applied Similarly, Mind Annotation Placement

All three models can participate in Bean Validation if `@Validated` and matching constraints are added and the project includes a Jakarta Bean Validation implementation.

In Spring Boot 3.x, typically add:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Example constraints:

- `@NotBlank` for `endpoint`: rejects null, empty, or whitespace-only strings.
- `@NotNull` for `connectTimeout`: requires a value.
- `@Min(0)` for `maxRetries`: value must not be negative.

Example placements:

| Type | Constraint Placement |
| --- | --- |
| JavaBean | Fields or accessors as supported by validation |
| Immutable class | `final` fields or locations readable by Bean Validation |
| Record | Annotations on record components, such as `@NotBlank String endpoint` |

For beans with nested configuration objects, `@Valid` may be needed on the field/component holding the child object so validation cascades inward.

**Semantic note:** `@NotBlank` only checks that a string is non-empty/non-blank; it does not check that a URL uses HTTPS, has a valid host, or satisfies endpoint policies. For specialized checks, build a custom constraint or validate in an appropriate layer.

### 10.1. Do Not Build Logic Relying on Secrets in `toString()`

Records generate `toString()`. Immutable classes and JavaBeans also frequently get IDE- or Lombok-generated `toString()` methods. If an object stores passwords or tokens, do not log the whole object since it can leak values into logs or traces.

Validation exceptions should report **field names and violation types**, not secret values.

## 11. Nested Configuration: Same Hierarchical Structure

Suppose the configuration expands:

~~~yaml
app:
  delivery:
    endpoint: https://api.example.test
    connect-timeout: 5s
    max-retries: 3
    enabled: true
    security:
      username: delivery-bot
      mode: bearer
~~~

All three property models can include a `security` subgroup, though binding mechanics differ.

### 11.1. JavaBean: Nested JavaBean Pre-Initialized

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public class DeliveryJavaBeanProperties {
    private final Security security = new Security();

    public Security getSecurity() {
        return security;
    }

    public static class Security {
        private String username;
        private String mode;

        public String getUsername() { return username; }
        public void setUsername(String username) {
            this.username = username;
        }

        public String getMode() { return mode; }
        public void setMode(String mode) {
            this.mode = mode;
        }
    }
}
~~~

This snippet only illustrates **the security section** added to the JavaBean class in Section 3, not replacing the other four fields. With a pre-initialized nested object exposing child setters, the binder updates data inside that object.

### 11.2. Immutable Class: Nested Constructor

~~~java
public final class Security {
    private final String username;
    private final String mode;

    public Security(String username, String mode) {
        this.username = username;
        this.mode = mode;
    }

    public String getUsername() { return username; }
    public String getMode() { return mode; }
}
~~~

The main properties class adds `private final Security security;`, adds `Security security` to its constructor, and returns it via a getter. If the nested class uses constructor binding and Spring Boot treats it as a nested object, the binder can create `Security` from `security.username` and `security.mode`.

### 11.3. Record: Nested Record

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryRecordProperties(
        String endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled,
        Security security) {

    public record Security(String username, String mode) {
    }
}
~~~

The record form for nested structures is usually more concise. If the entire `security` group is absent from config data, the `security` parameter can be `null`, depending on default configuration. When you always want a default nested instance, Spring Boot supports an argument-less `@DefaultValue` in the appropriate spot, though inner fields also need defaults or nullability as required.

### 11.4. When Binding Collections

Likewise, `List<String>` and `Map<String,String>` can appear in all three models. However:

- With JavaBeans, pre-initialized mutable collections can be populated by the binder without always needing a setter for the collection itself.
- With immutable classes and records, collections are passed into constructors; **a final reference does not guarantee an immutable collection**. When safety is needed, consider creating unmodifiable copies in the constructor or compact constructor.
- When config data sources override the same `List`, binding normally picks the list from the higher-precedence source rather than merging multiple lists. `Map` entries can be merged under specific binding rules.

Do not pick JavaBean over record thinking the Java type changes precedence between YAML, environment variables, and CLI. Property sources and collection binding rules belong to separate layers of responsibility.

## 12. Should Constructors / Compact Constructors Perform Validation?

With an immutable class, you can enforce internal invariants directly in the constructor:

~~~java
public DeliveryImmutableProperties(
        String endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {

    if (maxRetries < 0) {
        throw new IllegalArgumentException("maxRetries must be >= 0");
    }

    this.endpoint = endpoint;
    this.connectTimeout = connectTimeout;
    this.maxRetries = maxRetries;
    this.enabled = enabled;
}
~~~

This is Java-level validation, distinct from Bean Validation. It prevents constructing invalid objects even when instantiated manually outside Spring.

Records have a **compact constructor**:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryRecordProperties(
        String endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {

    public DeliveryRecordProperties {
        if (maxRetries < 0) {
            throw new IllegalArgumentException(
                    "maxRetries must be non-negative");
        }
    }
}
~~~

When the compact constructor finishes, Java assigns the component parameters to the record fields per language rules, unless an exception aborts creation.

You can use constructors or compact constructors to enforce simple invariants, yet avoid:

- Accessing databases or making network calls during config binding.
- Using other Spring beans inside a properties constructor.
- Putting secrets into exception messages.
- Complex logic that makes startup failures hard to understand.

For projects wanting consistent validation reporting, `@Validated` and Jakarta Bean Validation are generally preferred; constructor validation can supplement them when invariants must hold across every instantiation context.

## 13. Source Precedence Is Identical Across All Three Models

Suppose `application.yml` is:

~~~yaml
app:
  delivery:
    endpoint: https://sandbox.example.test
    connect-timeout: 5s
    max-retries: 2
    enabled: false
~~~

During deployment, the environment supplies:

~~~bash
APP_DELIVERY_ENDPOINT=https://api.example.test \
APP_DELIVERY_CONNECTTIMEOUT=10s \
java -jar demo.jar --app.delivery.max-retries=4
~~~

In standard Spring Boot, with these sources enabled and no higher-precedence overrides:

| Property | Final Value | Source |
| --- | --- | --- |
| `app.delivery.endpoint` | `https://api.example.test` | OS environment |
| `app.delivery.connect-timeout` | `10s` | OS environment |
| `app.delivery.max-retries` | `4` | Command-line argument |
| `app.delivery.enabled` | `false` | YAML |

Whether you use a JavaBean, an immutable class, or a record, data is bound from the **effective values in `Environment`**. None of the three types creates new configuration sources or changes property override rules.

Canonical rule for environment variables when binding `@ConfigurationProperties`: dots `.` become `_`, hyphens `-` are removed, and characters become uppercase. For example, `app.delivery.connect-timeout` → `APP_DELIVERY_CONNECTTIMEOUT`.

If a system calls `setAddCommandLineProperties(false)`, `--app.delivery.max-retries=4` will not enter the default CLI property source; the outcome depends on remaining sources.

## 14. When Should You Choose Each Model?

### 14.1. Choose JavaBean When...

- The project or library relies on traditional getter/setter APIs.
- You have an external mutable class that Spring can only configure after instantiation.
- You need to keep a nested bean that can be bound via setters.
- You want compatibility with older frameworks or conventions expecting JavaBeans.

In return, you must guard against mutating configuration after startup. If runtime config mutation is not needed, public setters can be a design weakness.

### 14.2. Choose Immutable Class When...

- You want an object with `final` fields and a strict API.
- You need custom constructor logic, multiple helper methods, or complex invariants.
- You want full control over representation, such as preventing `toString()` from exposing secrets.
- A record does not fit because you need to extend another class, or your design requires flexibility records do not offer.

In return, there is more boilerplate for constructors, getters, and `equals` if needed.

### 14.3. Choose Record When...

- Configuration is primarily **data**, not an object with complex behavior.
- You want minimal code with clearly declared fields.
- You run a Java version supporting records and a Spring Boot version supporting constructor binding.
- You want a natural model for dependency injection: configuration is constructed once and read via accessors.

In return, records cannot extend other classes, auto-generated `toString()` can emit configuration contents into logs, and collection "immutability" is reference-level only.

**A practical choice:** for new, data-only configuration groups in Java 17+/Spring Boot 3.x, records are usually very clean. For vendor objects with setters, JavaBean binding fits better. For immutable requirements needing custom constructor logic, a `final` class is a solid choice.

## 15. Three Binding Forms Are Not Three Dynamic Reload Mechanisms

A common misconception: because a JavaBean has setters, editing `application.yml` while the application is running causes Spring Boot to call the setters again automatically.

This **does not happen automatically**. In a standard Spring Boot application, config data loads at startup, and bean properties are bound during context creation. Changing the YAML file on disk does not automatically update existing beans.

- A JavaBean can change if application code explicitly calls a setter, yet that is not automatic config refresh.
- An immutable class has no setters; if a dedicated refresh mechanism exists, it typically constructs a new object or handles lifecycle specifically.
- A record is likewise instantiated from values at binding time; editing the file does not alter existing components.

If a project uses Spring Cloud Config, `@RefreshScope`, or a custom reload mechanism, follow that mechanism's contract. Do not choose JavaBean hoping Spring Boot re-reads YAML on every request.

## 16. Verifying Through Consuming Code

With the **record** example registered via `@EnableConfigurationProperties(DeliveryRecordProperties.class)`:

~~~java
package com.example.service;

import com.example.config.DeliveryRecordProperties;
import org.springframework.stereotype.Service;

@Service
public class DeliveryService {

    private final DeliveryRecordProperties properties;

    public DeliveryService(DeliveryRecordProperties properties) {
        this.properties = properties;
    }

    public boolean canDeliver() {
        return properties.enabled() && properties.maxRetries() >= 0;
    }

    public String targetEndpoint() {
        return properties.endpoint();
    }
}
~~~

Switching to a JavaBean or immutable class changes the constructor parameter type and accessors:

~~~java
// JavaBean:
properties.isEnabled();
properties.getMaxRetries();
properties.getEndpoint();

// Immutable class with similar getters:
properties.isEnabled();
properties.getMaxRetries();
properties.getEndpoint();

// Record:
properties.enabled();
properties.maxRetries();
properties.endpoint();
~~~

Do not mix record access syntax with JavaBean syntax: records do not generate `getEndpoint()` by default.

**Note:** the `DeliveryService`/`DeliveryJavaBeanProperties` examples here are presented as alternatives; do not copy all snippets sharing the same class name into one source file expecting Java to compile. Place each public type in its own file and enable one matching configuration registration.

## 17. Testing Binding and Validation

A configuration test suite should cover at least three scenarios:

1. **Happy path:** all four keys are present and converted to the right types.
2. **Missing/defaults:** omitted optional keys receive intended defaults; omitted required keys fail.
3. **Invalid types/constraints:** `connect-timeout: not-a-duration`, `max-retries: -1`, and `endpoint: "   "` are caught.

A Spring Boot test can use `ApplicationContextRunner` to load a configuration class and verify the bean, shown here with a **record**:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ConfigurationPropertiesAutoConfiguration.class))
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsRecordFromExternalProperties() {
        runner
            .withPropertyValues(
                "app.delivery.endpoint=https://api.example.test",
                "app.delivery.connect-timeout=5s",
                "app.delivery.max-retries=3",
                "app.delivery.enabled=true"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                DeliveryRecordProperties props =
                        context.getBean(DeliveryRecordProperties.class);
                assertThat(props.endpoint())
                        .isEqualTo("https://api.example.test");
                assertThat(props.connectTimeout())
                        .isEqualTo(java.time.Duration.ofSeconds(5));
                assertThat(props.maxRetries()).isEqualTo(3);
                assertThat(props.enabled()).isTrue();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryRecordProperties.class)
    static class TestConfiguration {
    }
}
~~~

This test requires the `spring-boot-starter-test` dependency, plus validation dependencies when testing validation. If the project has a specific test setup, you can use `@SpringBootTest(properties = {...})` to verify at the application context level.

For the JavaBean and immutable class variants, swap the type registered in `@EnableConfigurationProperties` and update the getter assertions accordingly. The goal is verifying that **identical inputs** yield **identical model values** across all three approaches.

## 18. Common Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JavaBean has fields yet does not bind | Missing setter for writable property, or class unregistered | Add matching getters/setters and register the bean |
| Immutable class gets unexpected null/0 | Missing key, no `@DefaultValue`, or missing constraint | Declare defaults and validation explicitly |
| Record is not created from configuration | Used constructor binding with incompatible `@Component`/`@Bean` | Use `@EnableConfigurationProperties` or scanning |
| Class has two constructors and binder picks the wrong one | Binding constructor not designated | Place `@ConstructorBinding` on the chosen constructor in Boot 3.x |
| Constructor binding reports unknown parameter names | Build does not preserve parameter-name metadata | Check `-parameters` compiler configuration |
| `connectTimeout` fails to bind | Wrong key name or unconvertible timeout value | Use `connect-timeout: 5s` and matching `Duration` type |
| Invalid endpoint does not fail | Missing validation, or missing `spring-boot-starter-validation` | Add `@Validated` + constraints/business checks |
| Record leaks secrets in logs | Generated `toString()` includes record components | Never log objects holding secrets directly; use redaction |
| YAML changes yet object stays unchanged | No refresh mechanism configured | Restart/redeploy or configure dedicated refresh |
| Three beans share prefix, causing dependency ambiguity | Scanned/enabled all three variants at once | Register only one approach or use intentional qualifiers |
| JavaBean setter mutated at runtime | Business code accidentally called a setter | Reduce mutability, consider immutable class/record |
| Nested object is not instantiated | Missing default or proper nested binding | Initialize nested JavaBean or use proper default/constructor model |
| Default set on object yet `Environment` returns null | Object initializers do not add entries to property sources | Place defaults in config data if needed by other lookups |

## 19. Practice Exercise: Migrating from JavaBean to Record

### Problem Statement

Given the configuration file:

~~~yaml
app:
  delivery:
    endpoint: https://api.example.test
    connect-timeout: 7s
    max-retries: 4
    enabled: false
~~~

Existing JavaBean:

~~~java
@ConfigurationProperties("app.delivery")
public class DeliveryProperties {
    private String endpoint;
    private Duration connectTimeout;
    private int maxRetries;
    private boolean enabled;

    // getters and setters for all four fields
}
~~~

Convert it to a record without changing property names or value semantics.

### Reference Solution

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        String endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {
}
~~~

Register the record type with `@EnableConfigurationProperties(DeliveryProperties.class)` or `@ConfigurationPropertiesScan`. Result: `endpoint` is the sample URL, `timeout` is `Duration.ofSeconds(7)`, `maxRetries` is `4`, and `enabled` is `false`.

Remember that consuming code must switch from `properties.getEndpoint()` to `properties.endpoint()`, and similarly for the remaining fields.

### Follow-Up Questions

**Question 1.** If `app.delivery.max-retries` is removed and you want a default of `2`, what can you do?

**Answer:** add `@DefaultValue("2")` on the `int maxRetries` record component, or place the default value in a config data source such as `application.yml`. If you choose the object-level default, that key does not automatically appear in `Environment`.

**Question 2.** If the configuration class must inherit from a base class, is a record suitable?

**Answer:** A Java record cannot extend any class other than `java.lang.Record`. Consider a regular immutable class or a JavaBean depending on design needs.

**Question 3.** If a library client only has a constructor taking `endpoint` and `timeout`, can you put `@ConfigurationProperties` on a `@Bean` returning the immutable client and get automatic constructor binding?

**Answer:** Not via the dedicated constructor-binding mechanism. Bind a separate properties class/record, then inject it into the `@Bean` factory method to build the client.

**Question 4.** Does using a record automatically solve hot reload?

**Answer:** No. By default Spring Boot loads config data and binds beans during startup; reloading requires a separate mechanism and appropriate lifecycle design.

## 20. Project Selection Checklist

When designing a new configuration group, ask yourself:

1. Is the configuration object pure data, read-only after startup? If yes, a record or immutable class usually preserves state better.
2. Must it integrate with a setter-based framework or external object? If yes, a JavaBean may fit better.
3. Do you need custom constructor logic or subclassing? If yes, a regular immutable class is more flexible than a record.
4. Does the configuration contain nested objects or mutable collections? If yes, clarify null/default semantics and a deep-immutability strategy.
5. Do required keys and validity rules have `@Validated`/constraints? Constructor binding alone is not enough.
6. Is the project on Spring Boot 2.x or 3.x? Check `@ConstructorBinding` placement and Jakarta vs. Javax validation namespaces.
7. Is bean registration right? Especially for constructor-bound properties, prefer `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.
8. Are higher-precedence property sources overriding the file? Class style does not change precedence.
9. Do you plan to log the properties object? Watch out for secrets and record `toString()`.
10. Do you need runtime refresh or startup-only configuration? Do not confuse JavaBean mutability with automatic config reloading.

## 21. Summary

**The exact same `app.delivery` configuration can bind to a JavaBean, an immutable class, or a record**, provided registration and object creation are configured properly:

- **JavaBean:** no-args constructor + setters; easy per-field binding and field-initializer defaults, yet mutable and verbose.
- **Immutable class:** constructor binding + `final` fields; fits when strict APIs and custom instantiation logic are needed, yet requires writing constructors and getters.
- **Record:** constructor binding via record components; concise, readable, auto-generated accessors/`equals`/`hashCode`/`toString`, yet requires caution with secrets and collection mutability.

Choose your model based on **the configuration contract and desired Java API**, not on assumptions that one style receives different property-source precedence than another. Whichever form you pick, verify validation, default values, property names, and source ordering.

### References

- Spring Boot 3.5 Reference — JavaBean Properties Binding, Constructor Binding, and Default Values: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Validation and Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
- Java Language Specification — Record Classes: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10
