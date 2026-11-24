# Enabling Validation with `@Validated` on Spring Boot Configuration

## 1. Why Is Reading Configuration Alone Not Enough?

Spring Boot supports **Externalized Configuration**: an application can read properties from `application.yml`, `application.properties`, environment variables, Java system properties, command-line arguments, and other sources. When a class is annotated with `@ConfigurationProperties`, the Binder attempts to convert those values into the corresponding Java types.

For example:

~~~yaml
app:
  worker:
    thread-count: 8
    request-timeout: 10s
    service-name: order-worker
~~~

Configuration class:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int threadCount,
        Duration requestTimeout,
        String serviceName
) {}
~~~

The Binder can convert `8` to `int` and `10s` to `Duration`. However, if YAML declares:

~~~yaml
app:
  worker:
    thread-count: -8
    request-timeout: 0s
    service-name: " "
~~~

these values **still bind successfully**: `-8` is a valid integer, `0s` is a valid duration, and a string of spaces is a valid `String` by type. Yet all of them can violate a worker's operational requirements.

Therefore, two layers must be distinguished:

1. **Binding/conversion:** Can the configuration value be converted into the Java type?
2. **Validation:** Does the bound Java value satisfy the business rules?

Annotating a `@ConfigurationProperties` type with `@Validated` is the standard way to instruct Spring Boot to run **Bean Validation** on the configuration object after binding. This lets the application catch invalid configuration when the bean is created, rather than failing only after it begins serving requests.

## 2. Expected Outcomes When Enabling Validation

A configuration class may require:

- Worker count at least 1 and not exceeding an operational limit.
- Service name containing actual text, not just whitespace.
- Server host address provided.
- A nested configuration group not omitted.
- A list of endpoints containing at least one element.
- Each endpoint element having a valid name and timeout.

Example configuration contract:

| Property | Java Type | Constraint | Typical Invalid Values |
| --- | --- | --- | --- |
| `app.worker.thread-count` | `int` | Between 1 and 32 | `0`, `-3`, `100` |
| `app.worker.service-name` | `String` | Non-empty and not whitespace-only | `""`, `"  "` |
| `app.worker.request-timeout` | `Duration` | Non-null; if needed, greater than 0 | Missing key, `0s` |
| `app.worker.enabled` | `Boolean` | Must be configured if required | Missing key |
| `app.worker.endpoints` | `List` | At least one element | Empty list |
| `app.worker.endpoint.url` | `String` | Non-empty; appropriate format | `""` |

Spring Boot does not infer these rules from field names. You must declare them with **Jakarta Bean Validation constraints**, via annotations and/or intentional validation logic.

## 3. Three Annotation Groups to Distinguish

| Annotation | Typical Package | Responsibility |
| --- | --- | --- |
| `@ConfigurationProperties` | `org.springframework.boot.context.properties` | Declares the prefix and binding target of a configuration group |
| `@Validated` | `org.springframework.validation.annotation` | Enables validation for the configuration bean when compatible validation infrastructure exists |
| `@NotBlank`, `@Min`, `@NotNull`, `@Valid`... | `jakarta.validation...` | Declares value constraints or requests validation cascading into nested objects |

Example:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @Min(1) int threadCount,
        @NotBlank String serviceName
) {}
~~~

Meaning:

- `@ConfigurationProperties` tells the Binder to look up keys starting with `app.worker`.
- `@Min(1)` checks that `threadCount` is not less than 1.
- `@NotBlank` requires `serviceName` not to be null, empty, or whitespace-only.
- `@Validated` marks the configuration object to be validated by the configured validation mechanism.

**Important:** `@Validated` does not define any constraints by itself. Without appropriate constraint annotations, adding `@Validated` will not make `threadCount` positive on its own.

## 4. Setting Up the Bean Validation Dependency

In a Spring Boot 3.x project using the Jakarta stack, constraint annotations live in the `jakarta.validation` package. To evaluate them at runtime, the application needs a **Bean Validation provider**. The standard way is to add the Spring Boot Validation Starter.

### Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

### Gradle (Groovy DSL)

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

This starter typically provides Hibernate Validator infrastructure compatible with your Spring Boot version. Having `@NotBlank` in source code without a matching runtime validation provider is **not enough to guarantee constraints will be evaluated as expected**.

If your project uses an older Spring Boot 2.x version, many online examples use the `javax.validation` namespace. For Spring Boot 3.x, use `jakarta.validation` matching the Jakarta EE stack supported by Boot 3; do not mix the two namespaces arbitrarily.

You can use standard constraints:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
~~~

Each annotation has distinct semantics; choose the right constraint for the Java type and business requirement.

## 5. Complete Example: Validated Worker Configuration

Suppose a background-processing application needs configuration:

~~~yaml
# src/main/resources/application.yml
app:
  worker:
    service-name: invoice-worker
    thread-count: 6
    enabled: true
    request-timeout: 8s
~~~

Declare an immutable configuration type:

~~~java
package com.example.demo.config;

import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @NotBlank String serviceName,
        @Min(1) @Max(32) int threadCount,
        @NotNull Boolean enabled,
        @NotNull Duration requestTimeout
) {}
~~~

How to read it:

- `serviceName` must be a string with non-whitespace content.
- `threadCount` must fall within 1 to 32.
- `enabled` must be provided when using wrapper `Boolean` with `@NotNull`; it can accept `true` **or** `false`.
- `requestTimeout` cannot be null, though an additional constraint is still needed if business rules require a duration greater than 0.

Register configuration classes with `@ConfigurationPropertiesScan`:

~~~java
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
~~~

Then a service consumes the configuration:

~~~java
package com.example.demo.service;

import com.example.demo.config.WorkerProperties;
import org.springframework.stereotype.Service;

@Service
public class WorkerService {
    private final WorkerProperties properties;

    public WorkerService(WorkerProperties properties) {
        this.properties = properties;
    }

    public int configuredThreads() {
        return properties.threadCount();
    }
}
~~~

When the `WorkerProperties` bean is created through configuration-properties binding, Spring Boot resolves values, converts types, instantiates the record, and runs validation. If any constraint is violated, application startup typically fails rather than exposing an invalid configuration bean to other services.

## 6. Invalid Examples and Why They Are Rejected

Keep the class from above. Examine each configuration file below.

### 6.1. Zero Threads

~~~yaml
app:
  worker:
    service-name: invoice-worker
    thread-count: 0
    enabled: true
    request-timeout: 8s
~~~

`0` converts to `int`, yet violates `@Min(1)`. This is a **validation error**, not a conversion error.

### 6.2. Thread Count Too High

~~~yaml
app:
  worker:
    service-name: invoice-worker
    thread-count: 128
    enabled: true
    request-timeout: 8s
~~~

This violates `@Max(32)`. The Binder converts `128` to `int` with no type issue; the validator catches the upper bound.

### 6.3. Whitespace-Only Name

~~~yaml
app:
  worker:
    service-name: "   "
    thread-count: 8
    enabled: true
    request-timeout: 8s
~~~

`@NotBlank` checks not only that the string is non-null, but also that it contains non-whitespace characters.

### 6.4. Missing `enabled` Property

~~~yaml
app:
  worker:
    service-name: invoice-worker
    thread-count: 8
    request-timeout: 8s
~~~

With `Boolean enabled`, if no value and no default are provided, the value can be null; `@NotNull` rejects this state.

If primitive `boolean enabled` were used, Java's default is `false`, so `@NotNull` **cannot distinguish** between "the deployer intentionally set false" and "no value was provided." When explicit configuration is required, use wrapper `Boolean` with an appropriate constraint or an explicit property-presence check.

### 6.5. Malformed Timeout

~~~yaml
app:
  worker:
    service-name: invoice-worker
    thread-count: 8
    enabled: true
    request-timeout: tomorrow
~~~

`tomorrow` is not a valid duration string for standard converters. Binding to `Duration` can fail **before the validator ever evaluates `@NotNull`**. This is why validation does not replace conversion; the two stages catch different classes of errors.

## 7. Conceptual Order: Read Sources → Bind → Validate

You can picture the flow as:

~~~text
application.yml / .properties / environment / CLI
                       │
                       ▼
            Resolve property sources
              and winning values
                       │
                       ▼
           ConfigurationProperties Binder
              - match prefix and keys
              - relaxed-bind names
              - convert data types
              - instantiate object / call setters
                       │
                       ▼
                Bean Validation
            - @NotBlank / @Min...
            - cascade @Valid nested objects
                       │
              ┌────────┴────────┐
              ▼                 ▼
            Valid            Violated
              │                 │
              ▼                 ▼
        Usable config      Report binding/
            bean        validation error at startup
~~~

This is a conceptual diagram. Implementation details and exception types vary across Spring Boot versions and bean creation paths, but distinguishing **conversion** from **constraint validation** is essential.

| Input Data | Conversion Result | Validation Result |
| --- | --- | --- |
| `thread-count=8` | `int 8` | Passes `@Min(1)` and `@Max(32)` |
| `thread-count=0` | `int 0` | Violates `@Min(1)` |
| `thread-count=128` | `int 128` | Violates `@Max(32)` |
| `thread-count=abc` | Cannot convert to `int` | May stop before validation |
| `service-name="  "` | `String` | Violates `@NotBlank` |
| `enabled=false` | `Boolean.FALSE` | Passes `@NotNull` |
| `enabled` missing | May become null | Violates `@NotNull` |

Type correctness does not imply business validity.

## 8. `@NotNull`, `@NotEmpty`, and `@NotBlank`: Three Different Things

Three constraints are frequently confused:

| Constraint | Common Types | Condition |
| --- | --- | --- |
| `@NotNull` | Any nullable object | Value must not be null |
| `@NotEmpty` | Strings, collections, `Map`, arrays | Not null and not empty |
| `@NotBlank` | `CharSequence`/`String` | Not null and has at least one non-whitespace character |

Example:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record NotificationSettings(
        @NotBlank String senderName,
        @NotEmpty java.util.List<String> channels,
        @NotNull Boolean enabled
) {}
~~~

Cases:

- `senderName="  "`: `@NotBlank` is violated.
- `channels=[]`: `@NotEmpty` is violated.
- `enabled=false`: `@NotNull` is **not** violated, because `false` is a present value.
- `senderName=""`: both `@NotBlank` and `@NotEmpty` reject it, but `@NotBlank` clearly expresses "not whitespace-only."

Do not use `@NotBlank` on `int`, `Duration`, or arbitrary objects. Applying a constraint to an incompatible type causes validator configuration errors rather than performing an equivalent check.

## 9. Numeric Constraints: `@Min`, `@Max`, `@Positive`

For connection counts:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Positive;

public record PoolSettings(
        @Min(1) @Max(100) int maxConnections,
        @Positive int retryBudget
) {}
~~~

Meaning:

- `@Min(1)`: number must be greater than or equal to 1.
- `@Max(100)`: number must be less than or equal to 100.
- `@Positive`: number must be positive, i.e., strictly greater than 0.

Example constraining a decimal number:

~~~java
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import java.math.BigDecimal;

public record SamplingSettings(
        @DecimalMin("0.0") @DecimalMax("1.0")
        BigDecimal sampleRate
) {}
~~~

`0.0` and `1.0` are valid when `inclusive=false` is not set. Numeric annotations do not guarantee a property **is supplied** when using nullable wrappers; if absence must be rejected, combine them with `@NotNull`.

Specifically: `@Positive` is not a general annotation for every type that has a concept of positivity, such as `Duration`. For durations, use custom validation logic or a matching custom constraint.

## 10. `@Pattern`, `@Size`, and String Validation

For example, requiring an environment name to contain only lowercase letters, digits, and hyphens:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record EnvironmentSettings(
        @NotBlank
        @Size(max = 30)
        @Pattern(regexp = "[a-z0-9]+(?:-[a-z0-9]+)*")
        String environmentName
) {}
~~~

Explanation:

- `@NotBlank`: not missing, not empty, not whitespace-only.
- `@Size(max=30)`: maximum length of 30 characters per string constraint semantics.
- `@Pattern`: value must match the regular expression.

Inside a valid `@Validated @ConfigurationProperties` class, `prod-us-1` passes while `PROD US` violates the pattern.

For URLs, `@NotBlank` only checks that content exists; it does not ensure valid URL syntax, HTTPS, or an allowlisted host. You can use a suitable URL constraint, bind to `URI` and check the scheme, or write custom constraint/constructor validation. Never assume a simple regex completely secures URL validation.

## 11. Enabling Validation with JavaBean Binding

You do not have to use records. With JavaBeans, `@Validated` still works:

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {

    @Min(1)
    @Max(10000)
    private int maxEntries = 100;

    @NotBlank
    private String cacheName = "local-cache";

    public int getMaxEntries() {
        return maxEntries;
    }

    public void setMaxEntries(int maxEntries) {
        this.maxEntries = maxEntries;
    }

    public String getCacheName() {
        return cacheName;
    }

    public void setCacheName(String cacheName) {
        this.cacheName = cacheName;
    }
}
~~~

Configuration file:

~~~yaml
app:
  cache:
    max-entries: 500
    cache-name: product-cache
~~~

The bean is created according to `@ConfigurationProperties` rules and the Binder invokes setters; validation then evaluates the constraints. With `max-entries=0`, `@Min(1)` is violated.

Note: JavaBeans have field initializers, so when a key is **absent**, the initialized value remains. Validation therefore runs against the **final object state**, and does not automatically distinguish "explicitly provided" from "using default." If explicit declaration is required, design types, defaults, and constraints accordingly.

## 12. Validation with Constructor Binding and Java Records

In Spring Boot 3.x, a properly registered `@ConfigurationProperties` record is typically bound via its canonical constructor:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.jobs")
public record JobProperties(
        @NotBlank String queueName,
        @Min(1) @Max(64) int workers,
        @NotNull Duration shutdownTimeout
) {}
~~~

This is a concise way to:

- Avoid boilerplate getters and setters.
- Express the configuration schema through component types.
- Attach constraints directly to components.
- Prevent fields from being mutated after construction.

However, record immutability at the field-reference level does not guarantee deep immutability if a component is a mutable `List` or `Map`. If data must remain unmodifiable after startup, consider defensive copies while still validating collection contents.

**Do not confuse constructor binding with bean dependency injection.** `@ConfigurationPropertiesScan` and `@EnableConfigurationProperties` are the right registration approaches for constructor-bound configuration types; do not add `@Component` to a record just to make Spring pick it up as a regular bean.

## 13. Validating Nested Objects with `@Valid`

Real-world configuration often has multiple levels:

~~~yaml
app:
  client:
    name: catalog-client
    connection:
      host: catalog.example.org
      port: 8443
~~~

Record:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotBlank String name,
        @NotNull @Valid Connection connection
) {
    public record Connection(
            @NotBlank String host,
            @Min(1) @Max(65535) int port
    ) {}
}
~~~

Here:

- `@NotNull` requires `connection` to exist.
- `@Valid` tells the validator to **descend into `connection`** and evaluate its inner constraints.
- `@NotBlank` validates `host`.
- `@Min` and `@Max` constrain the port to 1–65535.

If you omit `@Valid`, never assume the validator automatically traverses every nested object. In Bean Validation, **cascaded validation** must be requested explicitly.

### Why Do `@NotNull` and `@Valid` Often Appear Together?

A nested property group can be completely absent from configuration:

~~~yaml
app:
  client:
    name: catalog-client
~~~

Under constructor binding, `connection` can become null if no values and no defaults exist. When the child object is null, `@Valid` does not conjure an object to inspect `host` and `port`. `@NotNull` is what catches that **the entire required group is missing**.

You can think of them as:

- `@NotNull`: the child object must exist.
- `@Valid`: when the child object exists, validate its internal rules.

These are two distinct requirements and neither replaces the other.

## 14. When a Nested Object Has No Properties Configured

Spring Boot supports instantiating nested objects via constructor binding with an empty `@DefaultValue` when appropriate:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid @DefaultValue Worker worker
) {
    public record Worker(
            @Min(1) int threads,
            @NotNull String name
    ) {}
}
~~~

Idea: an empty `@DefaultValue` on `worker` tells the Binder to instantiate the nested object even when no properties exist under `app.worker`, provided instantiation is possible. Without child properties, `threads` can receive the primitive default while `name` can be null; validation can then catch the violated constraints.

Do not use an empty default just to mask an omitted required configuration group. If `worker` is required, `@NotNull` on the child object plus internal constraints express intent more clearly. If a child object with genuinely valid defaults is desired, define `@DefaultValue("...")` on each needed parameter.

This example illustrates the relationship between **instantiating a nested object** and **validating a nested object**; it is not advice to put `@DefaultValue` on every nested object.

## 15. Validating Lists and Their Elements

Suppose configuration defines a list of endpoints:

~~~yaml
app:
  upstreams:
    - name: catalog
      base-url: https://catalog.example.org
      weight: 10
    - name: inventory
      base-url: https://inventory.example.org
      weight: 20
~~~

Java:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record UpstreamProperties(
        @NotEmpty List<@Valid Upstream> upstreams
) {
    public record Upstream(
            @NotBlank String name,
            @NotBlank String baseUrl,
            @Min(1) int weight
    ) {}
}
~~~

Meaning:

1. `@NotEmpty` requires the `upstreams` list to be non-null and contain at least one element.
2. `List<@Valid Upstream>` instructs the validator to descend into each element.
3. `@NotBlank` and `@Min` apply to each `Upstream`.

If the second element has `weight=0`, type conversion to `int` succeeds, but validation detects that the element violates its constraint.

If the configuration only has:

~~~yaml
app:
  upstreams: []
~~~

`@NotEmpty` catches the empty list.

One note: `@NotEmpty` **does not validate that elements inside are valid**. Checking element contents requires `@Valid` or appropriate container-element constraints.

## 16. Validating Maps and Value Objects

With a `Map` of tenants:

~~~yaml
app:
  tenants:
    team-a:
      quota: 100
      region: asia
    team-b:
      quota: 200
      region: europe
~~~

Java:

~~~java
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record TenantProperties(
        @NotEmpty Map<String, @Valid Tenant> tenants
) {
    public record Tenant(
            @Min(1) int quota,
            @NotBlank String region
    ) {}
}
~~~

`@NotEmpty` verifies the Map has entries. `@Valid` on the value type argument requests descending into each `Tenant` to check quota and region.

If Map keys need their own rules, Bean Validation supports **container-element constraints** as supported by the provider. For example, a model might require non-blank keys via `Map<@NotBlank String, @Valid Tenant>`. Ensure your runtime validator supports type-argument constraints and write corresponding tests.

If Map keys contain dots or special characters, binding syntax may require bracket notation in YAML, which is a matter of **key naming during binding** rather than `@Valid` checking values after binding.

## 17. Constraining Durations: `@NotNull` Does Not Mean Positive `Duration`

Projects often write:

~~~java
@NotNull Duration timeout
~~~

This constraint only requires `timeout` **not to be null**. It does not reject values like `Duration.ZERO` or negative durations if accepted by the Binder.

For example:

~~~yaml
app:
  retry:
    timeout: 0s
~~~

`0s` converts to `Duration.ZERO`, which still passes `@NotNull`.

If a positive duration is required, you can enforce it in the constructor:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
        @NotNull Duration timeout
) {
    public RetryProperties {
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.retry.timeout must be positive");
        }
    }
}
~~~

This approach checks the invariant when the record is constructed, which **differs** from using a Bean Validation constraint. If you want to apply the rule uniformly across many `Duration` fields, you can create a **custom Bean Validation constraint** and a matching `ConstraintValidator`.

Do not put `@Positive` on `Duration` simply because the annotation name looks fitting: that constraint is designed for supported numeric types in Bean Validation, not any class with a notion of being greater than 0.

## 18. Defaults Do Not Replace Validation

Suppose:

~~~yaml
app:
  worker:
    thread-count: "${WORKER_COUNT:4}"
~~~

When the `WORKER_COUNT` environment variable is absent, the placeholder defaults to `4`. But when the variable is set:

~~~bash
export WORKER_COUNT=0
~~~

the placeholder resolves to `0`; conversion to `int` succeeds; and then `@Min(1)` rejects it.

Defaults only handle **missing referenced values**, not whether supplied values make sense.

Similarly, constructor binding can use:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") @Min(1) int threadCount
) {}
~~~

`@DefaultValue("4")` specifies the default when no value is bound for the parameter. `@Min(1)` specifies the constraint. These two annotations complement each other with distinct responsibilities:

| Scenario | Default | Validation |
| --- | --- | --- |
| Thread count not configured | Can supply 4 | Checks that 4 is valid |
| Configured `thread-count=6` | Default not needed | Checks that 6 is valid |
| Configured `thread-count=0` | Does not replace 0 with 4 | `@Min(1)` rejects it |
| Configured `thread-count=abc` | Does not auto-fix bad type | Binding can fail before validation |

Never treat a sensible default as proof that all runtime configurations are safe.

## 19. Configuration Precedence and Validation

Suppose `application.yml` contains:

~~~yaml
app:
  worker:
    thread-count: 4
~~~

`application-prod.yml` contains:

~~~yaml
app:
  worker:
    thread-count: 8
~~~

The runtime environment supplies:

~~~bash
APP_WORKER_THREADCOUNT=0
~~~

When the `prod` profile is active, environment variables typically outrank Config Data. The Binder can receive `0` instead of `8` from the production file. If the class declares `@Min(1)` and enables `@Validated`, the application can fail validation.

This is beneficial because validation guards **the final resolved value across sources**, not just isolated files.

Never assume an application is safe just because `application-prod.yml` has valid values. A higher-precedence source—such as a CLI argument, environment variable, or test property—can change the outcome.

For example:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.worker.thread-count=0
~~~

Under standard precedence, `--app.worker.thread-count=0` overrides Config Data and triggers the `@Min(1)` violation.

## 20. `@Validated` Differs from `@Valid` in Activation Role

The two annotations often appear together, yet are not identical:

- `@Validated`: a Spring annotation used to indicate validation for a configuration bean or to select validation groups in supported contexts.
- `@Valid`: a Jakarta Bean Validation annotation requesting **cascaded validation** into an inner object or element.

Example:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull @Valid Connection connection
) {
    public record Connection(
            @NotBlank String host
    ) {}
}
~~~

Do not drop `@Validated` at the root just because `@Valid` is on a nested property and assume Spring Boot will necessarily validate the root. Likewise, do not put only `@Validated` at the root and assume every nested object is deeply validated.

In a structured configuration:

1. Mark the **root properties class** for validation.
2. Place constraints on individual fields.
3. Place `@Valid` at every boundary where validation must descend into objects or elements.
4. Use `@NotNull`/`@NotEmpty` when nested objects/collections are required to be present.

This clearly expresses both **activation** and **scope** of validation.

## 21. Validation on Regular Spring Beans vs. on `@ConfigurationProperties`

`@Validated` can also be used in other Spring contexts, such as method validation. However, this lesson focuses on **validating configuration-property values upon binding**, not validating HTTP request parameters or general method invocations.

Example service class:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Validated
@Service
public class PaymentService {
    // Can participate in method validation
}
~~~

The purpose here differs from:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @NotBlank String merchantId
) {}
~~~

With `PaymentProperties`, you want to guarantee the newly constructed configuration bean does not contain a blank merchant ID. On a service, method validation (when configured) validates method calls against matching parameter/return constraints.

Do not confuse startup configuration errors with request DTO validation errors or service method validation errors. They share Bean Validation yet run at different points in the application lifecycle.

## 22. When Does Validation Execute?

For `@ConfigurationProperties` beans created and bound during normal startup, validation runs as part of bean construction. If a bean violates a constraint, application context initialization typically fails.

However, do not state absolutely that "every validation error always appears on line one of program execution." Exact timing depends on:

- Whether the bean is created eagerly or initialized lazily.
- How the `@ConfigurationProperties` class is registered.
- Whether a Bean Validation provider is actually available.
- Whether special bean-creation or refresh mechanisms are used.
- Whether constraints are placed in the right locations.

For applications requiring fail-fast behavior, ensure critical configuration beans are instantiated during normal startup and write tests proving it.

Also, do not assume editing `application.yml` after the Java process is running will automatically re-run validation; Config Data and configuration beans are normally loaded/bound at startup unless a separate refresh mechanism exists.

## 23. Common Errors When Validation Fails

A Bean Validation failure on `@ConfigurationProperties` can appear in the exception chain of binding or bean creation. Depending on the version, you may see `ConfigurationPropertiesBindException`, `BindException`, `BindValidationException`, or a message showing the field, rejected value, and violated constraint.

Illustrative example, **not a fixed message format**:

~~~text
Failed to bind properties under 'app.worker'
to com.example.demo.config.WorkerProperties

Property: app.worker.thread-count
Value: "0"
Reason: must be greater than or equal to 1
~~~

Wait—let's check the exact fence in `validation-003.md` lines 947-954! In the original file, lines 947-954 use `~~~text` and `~~~`, NOT triple backticks! Good thing I checked! Let's keep `~~~text` and `~~~`.

Continuing from line 956:
When seeing an error like this, do not just weaken the annotation so the app starts. Diagnostic workflow:

1. Identify the **prefix** of the properties class, e.g., `app.worker`.
2. Find the violated **property name**, e.g., `thread-count`.
3. Determine which source supplied the **final effective value**.
4. Check whether the failure is **conversion**, **Bean Validation**, or a constructor/bean-creation error.
5. Fix the configuration value or adjust the constraint if business requirements genuinely changed.
6. Re-run tests and startup against the relevant environment.

If you must log configuration data, avoid printing secrets or sensitive strings. Exception messages can include configuration values, so protect production logs.

## 24. `ignoreInvalidFields` Does Not Replace Validation

`@ConfigurationProperties` has Binder settings such as:

~~~java
@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = false,
        ignoreUnknownFields = true
)
~~~

These two flags are often confused with validation:

- `ignoreInvalidFields` controls how the Binder handles certain unbindable type errors; the default is `false`.
- `ignoreUnknownFields` controls properties without a matching target in the class; the default is `true`.
- `@Validated` and constraints validate values **after binding**.

For example, `thread-count=abc` is a type mismatch, whereas `thread-count=-3` is a valid `int` that violates `@Min(1)`.

Setting `ignoreInvalidFields=true` does not make constraints vanish. If the Binder skips an invalid value and leaves an initial default, validation still checks the **final object value**. If that default passes the constraint, the object may be accepted even though the operator supplied a malformed string—a risk you must understand clearly.

For critical operational settings, prefer keeping **strict binding** so type mismatches fail loudly, alongside validation to catch type-valid yet contract-invalid values.

## 25. Missing Properties and Primitive Defaults: A Common Trap

Suppose:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Min(0) int retryCount,
        @NotNull boolean enabled
) {}
~~~

This is **not** a way to ensure the two required keys are supplied. Why:

- Primitive `int` can receive `0` when the value is missing.
- `@Min(0)` accepts `0`.
- Primitive `boolean` cannot be null, so `@NotNull` cannot detect absence.

If you want to require the deployer to configure them:

~~~java
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull Integer retryCount,
        @NotNull Boolean enabled
) {}
~~~

When the property and any default are absent, the wrapper can be null, allowing the constraint to catch it.

If `retryCount` must be at least 1:

~~~java
@NotNull @Min(1) Integer retryCount
~~~

With `Boolean enabled`, `@NotNull` allows both `false` and `true`; it only requires a value to be present.

When you want a default rather than requiring explicit configuration, declare `@DefaultValue` or a config default. **Required** and **defaulted** are two different intents—choose one deliberately.

## 26. Cross-Field Validation: When Single-Field Constraints Are Not Enough

Some rules inspect **multiple properties together**, for example:

- If TLS is enabled, a trust store must be provided.
- If retry is enabled, retry count must be positive.
- When `mode=REMOTE`, endpoint must not be blank.
- If a feature is allowed only in production, the active profile must match.

Single-field constraints like `@NotBlank` or `@Min` cannot express these relationships completely. For example:

~~~yaml
app:
  sender:
    mode: REMOTE
    endpoint: ""
~~~

You can create a configuration object with a custom class-level constraint or a constructor invariant check:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.sender")
public record SenderProperties(
        Mode mode,
        String endpoint
) {
    public enum Mode { LOCAL, REMOTE }

    public SenderProperties {
        if (mode == Mode.REMOTE &&
                (endpoint == null || endpoint.isBlank())) {
            throw new IllegalArgumentException(
                    "app.sender.endpoint is required in REMOTE mode");
        }
    }
}
~~~

This is a **constructor invariant**, not a `@Validated` constraint. If a project wants errors reported through Jakarta Bean Validation, it can define a **class-level custom constraint** with a `ConstraintValidator`.

When to use which approach?

| Approach | Best Suited When |
| --- | --- |
| Standard field constraint | A single property has an independent rule |
| Constructor check | Simple invariant needing immediate rejection upon object creation |
| Class-level custom Bean Validation constraint | Rule spans multiple fields and needs uniform violations or reuse |

Do not write complex business logic inside configuration getters merely to mask missing validation.

## 27. Custom Constraint Example for Positive Timeout

If multiple properties classes must require `Duration` greater than 0, you can define a dedicated annotation.

Annotation:

~~~java
package com.example.demo.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.RECORD_COMPONENT,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = PositiveDurationValidator.class)
public @interface PositiveDuration {
    String message() default "must be a positive duration";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
package com.example.demo.validation;

import java.time.Duration;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class PositiveDurationValidator
        implements ConstraintValidator<PositiveDuration, Duration> {

    @Override
    public boolean isValid(
            Duration value,
            ConstraintValidatorContext context) {
        // Null is handled by @NotNull when the property is required.
        return value == null || (!value.isZero() && !value.isNegative());
    }
}
~~~

Usage:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import com.example.demo.validation.PositiveDuration;

@Validated
@ConfigurationProperties(prefix = "app.transport")
public record TransportProperties(
        @NotNull @PositiveDuration Duration timeout
) {}
~~~

When `timeout=0s`, conversion succeeds, yet the custom validator rejects it.

Two principles:

1. Do not automatically treat null as invalid in every custom constraint when `@NotNull` already expresses presence; separating responsibilities promotes reuse.
2. Custom validators should never make network calls or cause side effects just to check a config value.

In real projects, custom constraints are production code and need dedicated tests for null, zero, negative, and positive values.

## 28. Testing Startup Failures with `ApplicationContextRunner`

A reliable way to verify validation works is to spin up a small application context in a Spring Boot unit/integration test.

Configuration class under test:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @NotBlank String serviceName,
        @Min(1) @Max(32) int threadCount
) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerPropertiesValidationTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void validValuesCreatePropertiesBean() {
        runner.withPropertyValues(
                "app.worker.service-name=invoice-worker",
                "app.worker.thread-count=6"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            WorkerProperties props =
                    context.getBean(WorkerProperties.class);

            assertThat(props.threadCount()).isEqualTo(6);
            assertThat(props.serviceName()).isEqualTo("invoice-worker");
        });
    }

    @Test
    void zeroThreadCountFailsValidation() {
        runner.withPropertyValues(
                "app.worker.service-name=invoice-worker",
                "app.worker.thread-count=0"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void blankServiceNameFailsValidation() {
        runner.withPropertyValues(
                "app.worker.service-name=   ",
                "app.worker.thread-count=3"
        ).run(context -> assertThat(context).hasFailed());
    }
}
~~~

This example assumes Spring Boot Test, AssertJ, JUnit 5, and a Bean Validation provider are properly declared on the test runtime classpath. When precision about the failure cause matters, inspect the startup failure and cause chain to prove it is a validation violation rather than an unrelated missing-bean error.

`ApplicationContextRunner` is especially well-suited for keeping tests small without launching a full web server or accessing a database.

## 29. Testing Nested Validation

With the class:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        @NotNull @Valid Remote remote
) {
    public record Remote(
            @NotBlank String host
    ) {}
}
~~~

You can test at least three scenarios:

| Test Case | Data | Expectation |
| --- | --- | --- |
| Valid nested | `app.gateway.remote.host=api.example.org` | Context creates the bean |
| Entire nested missing | No `app.gateway.remote.*` keys | `@NotNull` on `remote` catches it |
| Nested present, blank host | `app.gateway.remote.host=` | `@Valid` enters `Remote`, `@NotBlank` catches it |

If `@Valid` were removed from the root record, the blank nested host case might not be deeply validated; that is why testing cascaded validation is a vital part of the configuration contract.

For multi-level nested objects, place `@Valid` at each boundary Bean Validation needs to cross. Never assume one `@Valid` at the root automatically traverses arbitrary depths without cascade metadata at intermediate levels.

## 30. Does `@Validated` Support Validation Groups?

Jakarta Bean Validation supports **groups**—subsets of constraints evaluated depending on context. Spring's `@Validated` also has an attribute allowing you to specify groups in supported contexts.

Conceptual example:

~~~java
public interface ProductionChecks {}

public record ConnectionSettings(
        @NotBlank String host,
        @NotBlank(groups = ProductionChecks.class) String certificateAlias
) {}
~~~

In Bean Validation, constraints without `groups` belong to the default group, while constraints with `groups = ProductionChecks.class` are evaluated when that group is requested.

However, using groups on `@ConfigurationProperties` requires checking how your Spring Boot version builds the validator and evaluates annotations. Do not copy complex group examples from Spring MVC validation assuming they apply verbatim to every `@ConfigurationProperties` bean.

When a single configuration object must be valid across environments, simpler alternatives are usually:

- One set of constraints applying across all environments.
- Environment-specific options modeled as separate types or groups.
- A class-level custom constraint for environment-dependent rules, if truly needed.

Use groups only when your project has a clear need and tests confirming the behavior.

## 31. Common Errors When Enabling `@Validated`

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@Min(1)` present, yet `0` is accepted | Validation not enabled on config bean or missing provider | Check `@Validated`, validation dependency, and bean registration |
| `@Valid` on nested object, yet missing child group passes | Nested object is null; cascade does not require presence | Add `@NotNull` to child object |
| `@NotNull` present, yet whitespace-only string passes | `@NotNull` only checks for non-null | Use `@NotBlank` |
| `@NotNull boolean` misses missing key | Primitives cannot be null | Use `Boolean` and `@NotNull` |
| `@NotEmpty` on list, yet invalid items are accepted | Elements not cascaded | Use `List<@Valid Item>` or appropriate `@Valid` |
| `@NotNull Duration`, yet `0s` passes | Constraint only checks non-null | Use custom positive-duration constraint or constructor check |
| `thread-count=abc` fails before validation | Conversion to `int` failed | Fix wrong-typed input; this is a binding error |
| Added `@Validated`, yet context cannot find properties bean | `@ConfigurationProperties` class not registered | Use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Record with `@Component` and constructor binding behaves unexpectedly | Bean instantiated via standard dependency injection | Register record via configuration-properties mechanisms |
| Validation test passes even though constraint should fail | Test runtime lacks provider or instantiates with `new` instead of Binder | Test with context and full dependencies |
| YAML values valid, yet startup still fails | Higher-precedence source may be overriding | Check env vars, system properties, and CLI args |
| Valid default masks missing config | Default applied prior to validation | Decide explicitly between defaulting and failing when absent |
| `ignoreInvalidFields=true` lets bad config run | Conversion errors may be ignored | Prefer strict binding and enable validation |
| Validation does not run as tests expect | Wrong Jakarta version/namespace or cascade boundary | Check dependencies, imports, and nested tests |

## 32. Diagnosing in Docker/Kubernetes Environments

An application has the file:

~~~yaml
app:
  worker:
    service-name: invoice-worker
    thread-count: 6
~~~

Docker Compose might override it:

~~~yaml
services:
  worker:
    image: example/invoice-worker:latest
    environment:
      APP_WORKER_SERVICENAME: "invoice-worker"
      APP_WORKER_THREADCOUNT: "0"
~~~

`APP_WORKER_THREADCOUNT` maps via Spring Boot relaxed binding from `app.worker.thread-count` and usually takes precedence over config files inside the JAR. At startup, Bean Validation `@Min(1)` rejects `0`.

In Kubernetes:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: invoice-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: invoice-worker
  template:
    metadata:
      labels:
        app: invoice-worker
    spec:
      containers:
        - name: worker
          image: example/invoice-worker:latest
          env:
            - name: APP_WORKER_THREADCOUNT
              value: "0"
            - name: APP_WORKER_SERVICENAME
              value: "invoice-worker"
~~~

If required configuration beans bind at startup and validation is active, the container exits early due to invalid configuration. That signals operators to fix the manifest/ConfigMap/Secret or injected value, rather than disabling the constraint.

In real deployments:

- Document keys and valid ranges in operational runbooks.
- Lint manifests and environment variables before rollout.
- Inspect startup logs carefully without exposing secrets.
- Distinguish config failures from liveness/readiness failures or downstream connectivity errors.
- Fix the invalid source, then redeploy through your standard release process.

Bean Validation is a strong safety net, though it does not replace manifest validation and deployment testing.

## 33. Never Validate Secrets by Logging Them

Properties such as API keys, passwords, tokens, or private keys may require presence constraints:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @NotBlank String apiKey
) {}
~~~

`@NotBlank` catches a missing or whitespace-only API key. However, it does not prove the key is active, belongs to the right tenant, or has permissions on the external service.

Never write a custom validator that takes the key and makes an outbound internet request during binding to verify it—this makes startup network-dependent and risks credential exposure. Separate format/presence checks from actual connectivity checks.

When troubleshooting incidents, avoid logging entire configuration beans containing secrets. Java records generate a `toString()` that prints all components, so be especially careful when a record holds passwords or tokens.

## 34. Practice Exercises

### Exercise 1 — Right Type, Wrong Value

Given:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.pool")
public record PoolProperties(
        @Min(1) int minConnections,
        @Max(200) int maxConnections
) {}
~~~

YAML:

~~~yaml
app:
  pool:
    min-connections: 0
    max-connections: 100
~~~

Question: Does type conversion succeed? Should validation accept it?

**Answer:** Both `0` and `100` convert to `int`. However, `minConnections=0` violates `@Min(1)`, so validation rejects it when properly enabled.

### Exercise 2 — `@NotNull` with `boolean`

Given:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull boolean enabled
) {}
~~~

If `app.enabled` is omitted, does `@NotNull` guarantee the application reports an error?

**Answer:** No. Primitive `boolean` cannot be null; to detect a missing value, use `Boolean` with `@NotNull` or an explicit presence check.

### Exercise 3 — Validating a Child Group

Given:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull @Valid Client client
) {
    public record Client(@NotBlank String endpoint) {}
}
~~~

If only `app.client.endpoint=" "` is configured, which constraint detects the error?

**Answer:** `@Valid` tells validation to descend into `Client`, and then `@NotBlank` rejects the whitespace-only endpoint. `@NotNull` on `client` only requires the child object to exist.

### Exercise 4 — Empty List

A `List<Endpoint>` must not be empty and each `Endpoint` must have a name. Choose the annotations.

**Suggested Answer:**

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty java.util.List<@Valid Endpoint> endpoints
) {
    public record Endpoint(@NotBlank String name) {}
}
~~~

`@NotEmpty` checks that the list has elements, `@Valid` enables cascading, and `@NotBlank` checks each element's name.

### Exercise 5 — Wrong Type Value

A file contains `app.worker.thread-count=abc`, and the Java field is `int threadCount` with `@Min(1)`. Is this a conversion error or a `@Min` error?

**Answer:** First and foremost a conversion/binding error, because `abc` cannot convert to `int`. The validator may never get a chance to evaluate `@Min(1)`.

### Exercise 6 — Defaults and Validation

Record:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") @Min(1) int threadCount
) {}
~~~

When the key is absent, what happens? When `0` is supplied, what happens?

**Answer:** When the key is absent, default `4` is bound and passes the constraint. When `0` is supplied, the default does not override it, so `@Min(1)` rejects it.

### Exercise 7 — Positive Timeout Constraint

Why is `@NotNull Duration timeout` insufficient to forbid `timeout=0s`?

**Answer:** `Duration.ZERO` is not null. You need a custom Bean Validation constraint for positive `Duration` or a constructor invariant check.

### Exercise 8 — From YAML to Runtime

`application-prod.yml` defines `app.worker.thread-count=8`, while an env var sets `APP_WORKER_THREADCOUNT=0`. If `@Min(1)` is properly enabled, what happens?

**Answer:** The environment variable typically takes precedence over Config Data and provides the final value `0`. The Binder converts the type cleanly, Bean Validation rejects it, and configuration bean creation/startup fails.

## 35. Project Adoption Checklist

When creating a new `@ConfigurationProperties` class:

1. Identify the **prefix** and canonical property names to bind.
2. Choose accurate Java types: `int`, `Integer`, `Duration`, `List`, `Map`, or nested records.
3. Add a Bean Validation provider dependency, typically via `spring-boot-starter-validation`.
4. Annotate the root properties class with **`@Validated`**.
5. Attach appropriate standard constraints: `@NotBlank`, `@NotNull`, `@Min`, `@Max`, `@NotEmpty`, etc.
6. For nested objects/collections, add **`@Valid`** to cascade and `@NotNull`/`@NotEmpty` when presence is required.
7. Specify defaults only when absence is valid; use nullable wrappers when missing configuration must be caught.
8. For cross-field rules or special types, add custom constraints or intentional invariant checks.
9. Register the bean properly via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
10. Write tests for **valid, missing, wrong-type, constraint-violating, and nested object cases**.
11. At deployment, ensure env/CLI values do not accidentally override valid YAML settings.
12. Never log sensitive values and never treat Bean Validation as a substitute for integration testing.

This checklist is a workflow for developers to follow; each application must define its own business rules and configuration strictness.

## 36. Key Takeaways

- **`@Validated` on `@ConfigurationProperties`** is the standard way to enable validation on Spring Boot configuration objects.
- A compatible **Bean Validation provider** is required; in Spring Boot 3.x, the standard approach is adding `spring-boot-starter-validation` and importing from `jakarta.validation`.
- **Binding/conversion** and **validation** are two distinct steps: `abc` for `int` is a conversion failure, whereas `0` violating `@Min(1)` is a validation failure.
- `@Validated` does not create constraints by itself. You must declare `@NotBlank`, `@Min`, `@NotNull`, and the rules actually needed.
- **`@NotNull` does not check for blank strings** or positive durations; pick the right constraint for each type.
- For nested config, **`@Valid` triggers cascading**, whereas `@NotNull`/`@NotEmpty` require the object/collection to exist.
- Use **wrapper types (`Integer`/`Boolean`)** if you need to detect missing keys instead of letting primitives default to `0`/`false`.
- `@DefaultValue` and placeholder defaults do not override validation for invalid supplied values.
- Validation inspects **values after the Binder resolves effective configuration sources**, including environment variables and CLI flags.
- Test with `ApplicationContextRunner` to verify that valid configs initialize cleanly and invalid configs intentionally fail the context.
- Preserve **fail-fast** behavior for critical settings; do not use `ignoreInvalidFields` to hide type mismatches or missing constraints.

## References

- [Spring Boot 3.3 Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 Reference — Type-safe Configuration Properties and Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)