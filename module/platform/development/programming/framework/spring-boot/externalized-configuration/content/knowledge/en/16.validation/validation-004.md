# Constraining Strings, Numbers, Addresses, and Required Values

## 1. Why Does Configuration Need Validation?

In Spring Boot, configuration data can come from `application.yml`, `application.properties`, profile-specific documents, environment variables, Java system properties, command-line arguments, or external Config Data sources. Spring Boot can **bind** these values into a Java object via `@ConfigurationProperties`, yet successful type conversion **does not guarantee the values satisfy application rules**.

For example, consider:

```yaml
delivery:
  sender-name: "Order Service"
  sender-email: ""
  callback-uri: "http://example.invalid/callback"
  max-attempts: -4
  retry-ratio: 1.8
```

All of the values above can be read as strings, a URI, an integer, or a decimal. However, the application may require:

- Sender name must not be missing or whitespace-only.
- Sender email must have a valid email format.
- Callback address must be an HTTPS URI with a hostname.
- Attempt count must fall within 1 to 20.
- Retry ratio must fall within 0 to 1.

Without validation, the application may start up and only fail later when sending notifications, misrouting traffic, or performing an unexpected number of retries.

**Bean Validation combined with `@ConfigurationProperties`** catches unsuitable configurations during Spring context startup. The goal is not merely "successfully reading config" but "only creating the configuration bean when data satisfies the published contract."

## 2. Distinguishing Four Configuration Processing Stages

Configuration-related failures can happen at different layers:

```text
YAML / Properties files / environment / CLI
                     |
                     v
       Spring Environment and Config Data
                     |
          select effective values
                     |
                     v
       ConfigurationProperties Binder
                     |
          match key names / prefix
                     |
                     v
              Type conversion
                     |
          "5" -> int; "3s" -> Duration
                     |
                     v
              Bean Validation
                     |
          maxAttempts >= 1?
          valid email?
          URI meets requirements?
                     |
                +----+----+
                |         |
              Valid    Invalid
                |         |
                v         v
          Create       Halt initialization,
          valid bean   report config error
```

Four key concepts:

| Concept | Question Answered | Example |
| --- | --- | --- |
| Source resolution | Which value takes effect? | CLI overrides YAML |
| Name binding | Which key maps to which Java member? | `max-attempts` ↔ `maxAttempts` |
| Type conversion | Can the string convert to the target type? | `"4"` → `int 4` |
| Validation | Does the typed value satisfy business rules? | `4` is within `1..20` |

For instance, `max-attempts=many` cannot convert to an integer, which is a **type conversion error**. By contrast, `max-attempts=-4` converts to `int` cleanly yet violates `@Min(1)`, which is a **validation error**.

Both error types can prevent startup, yet their causes and fixes are different.

## 3. Setting Up the Bean Validation Library

These examples use **Spring Boot 3.x**, Java 17 or later, and Jakarta Validation. With Spring Boot 3.x, common constraints are imported from `jakarta.validation.constraints`.

If your project does not yet include a validation library, add the starter:

**Maven:**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

**Gradle (Groovy DSL):**

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

The starter brings in a Jakarta Bean Validation provider, typically Hibernate Validator, along with the components needed to evaluate constraints.

Adding Jakarta Validation API annotations alone without a runtime provider means annotating fields with `@NotBlank`, `@Min`, etc. **does not guarantee** constraints are enforced across all application setups.

Some older Spring Boot 2.x projects use `javax.validation.*`. Do not copy those imports directly into Spring Boot 3.x without accounting for the Java EE to Jakarta EE migration.

## 4. Enabling Validation for `@ConfigurationProperties`

Consider a simple configuration record:

```java
package com.example.configdemo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotBlank String senderName,
        @Min(1) @Max(20) int maxAttempts) {
}
```

Each piece has a specific role:

- `@ConfigurationProperties(prefix = "delivery")`: specifies the input key group bound by the Binder.
- `@Validated`: asks the validation mechanism to inspect the configuration bean when Spring Boot binds it.
- `@NotBlank`: constrains the string not to be null, empty, or whitespace-only.
- `@Min(1)`: requires the numeric value to be at least 1.
- `@Max(20)`: requires the numeric value not to exceed 20.

`application.yml`:

```yaml
delivery:
  sender-name: "Order Service"
  max-attempts: 4
```

When the configuration bean is properly registered, the Binder passes both properties into the record constructor, and validation enforces the declared constraints.

If `max-attempts` is changed to `-2`, the number still converts cleanly yet fails `@Min(1)`. Bean initialization can fail with a configuration-binding/validation error report.

**Note:** putting annotations on a class that Spring never registers as a `@ConfigurationProperties` bean does not trigger validation automatically.

## 5. Registering the Configuration Bean Before Expecting Validation

For a constructor-bound record `DeliveryProperties`, a common approach is placing `@ConfigurationPropertiesScan` on the application class.

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Place `DeliveryProperties` in the same package or a scanned subpackage.

If explicit registration is preferred, you can choose:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(DeliveryProperties.class)
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

These two snippets are **alternatives**, not two main classes coexisting in one project.

For constructor-bound configuration properties in Spring Boot 3.x, avoid putting `@Component` on the record just to "get scanned," because regular component registration differs from constructor-bound configuration-properties registration.

## 6. String Constraints

Configuration strings often represent display names, tenant names, region codes, logical paths, queue names, or identifiers.

Five commonly used constraints:

| Constraint | Core Meaning | Common Targets |
| --- | --- | --- |
| `@NotNull` | Must not be `null` | Many reference types |
| `@NotEmpty` | Must not be null or empty | `String`, collections, maps, arrays |
| `@NotBlank` | String not null, empty, or whitespace-only | `CharSequence` |
| `@Size(min, max)` | String length or collection size within bounds | `String`, collections, etc. |
| `@Pattern(regexp = "...")` | String must match regular expression | `CharSequence` |

Example:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record IdentificationProperties(
        @NotBlank
        @Size(max = 80)
        String displayName,

        @NotBlank
        @Pattern(regexp = "^[A-Z]{2}-[0-9]{4}$")
        String locationCode) {
}
```

These annotations take effect only when the object passes through an active validation pipeline. The record above illustrates the constraints; for actual binding, put it inside a registered `@Validated` `@ConfigurationProperties` class as in the main examples.

Example values:

```yaml
identification:
  display-name: "Payment Gateway"
  location-code: "VN-0024"
```

With `@Pattern(regexp = "^[A-Z]{2}-[0-9]{4}$")`, codes like `VN-0024` pass, whereas `vn-0024` or `VN-24` fail.

**Do not confuse validation with data normalization.** `@Pattern` does not transform `vn-0024` into `VN-0024`. If the system should accept lowercase and normalize it, design an explicit conversion or consistent input rule.

## 7. Differences Between `@NotNull`, `@NotEmpty`, and `@NotBlank`

These three constraints are often treated as interchangeable, yet differ significantly.

Suppose we validate a `String` value:

| Value | `@NotNull` | `@NotEmpty` | `@NotBlank` |
| --- | --- | --- | --- |
| `null` | Fails | Fails | Fails |
| `""` | Passes | Fails | Fails |
| `"   "` | Passes | Passes | Fails |
| `"abc"` | Passes | Passes | Passes |

Therefore:

- If you only require an object reference to exist, use `@NotNull`.
- If you want a string with at least one character, `@NotEmpty` suffices, though it **allows whitespace-only strings**.
- If you want a meaningful non-empty name, label, or email, `@NotBlank` is usually more appropriate.

Example:

```java
@Validated
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        @NotBlank String name) {
}
```

Invalid configurations under this constraint:

```yaml
service:
  name: ""
```

Or:

```yaml
service:
  name: "   "
```

**Important detail:** setting a default via `@DefaultValue` or YAML does not remove the need for validation. A meaningless default such as an empty string will still violate `@NotBlank`.

## 8. Length Bounds with `@Size`

Some settings need length limits:

- Service name at most 80 characters.
- Identifier between 3 and 16 characters.
- Recipient list containing 1 to 10 items.

Example:

```java
@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotBlank
        @Size(min = 3, max = 16)
        String regionCode) {
}
```

With:

```properties
routing.region-code=VN
```

the string has two characters and fails `@Size(min = 3)`.

With:

```properties
routing.region-code=VN-SG
```

the length satisfies the bounds.

**Note:** `@Size` is not a constraint for numeric values. To ensure `retry-count` is between 1 and 20, use `@Min` and `@Max` rather than `@Size`.

An absent string value may receive a default or `null`; if the field is required, combine `@Size` with `@NotBlank` or an appropriate null constraint, because `@Size` alone does not forbid `null`.

## 9. Constraining Integers with `@Min` and `@Max`

Many operational settings are integers: thread counts, connection counts, retry counts, batch limits, network ports.

Example:

```yaml
worker:
  min-threads: 2
  max-threads: 16
  max-attempts: 4
```

Record:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @Min(1) int minThreads,
        @Min(1) @Max(256) int maxThreads,
        @Min(1) @Max(20) int maxAttempts) {
}
```

If an operator declares:

```yaml
worker:
  min-threads: 0
  max-threads: 500
  max-attempts: -3
```

the numbers still convert to `int`, yet each violates its respective constraint.

Keeping bounds on the configuration model lets anyone reading the Java class see the input contract immediately.

### 9.1. `@Positive` and `@PositiveOrZero`

Two other helpful constraints:

```java
@Positive int threadCount;
@PositiveOrZero int backlogSize;
```

- `@Positive`: strictly greater than 0.
- `@PositiveOrZero`: greater than or equal to 0.

Correspondingly, `@Negative` and `@NegativeOrZero` exist for matching use cases.

For a rule like "attempts from 1 to 20," `@Min(1) @Max(20)` communicates the range more clearly than `@Positive` alone.

### 9.2. Primitives Can Mask Missing Values

Consider:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

If `worker.max-threads` is absent, primitive `int` can receive the default `0` during object instantiation. It cannot represent `null`.

Putting `@NotNull` on `int` does not catch missing keys the way reference types do, because `int` cannot be null.

If you want to require an explicit numeric setting even when `0` could be valid, consider:

```java
@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @NotNull Integer maxThreads) {
}
```

With `Integer`, an absent value can be represented as `null` and caught by `@NotNull`. If business logic requires a positive integer, add `@Min(1)`.

## 10. Decimals, Ratios, and `BigDecimal`

Ratios, thresholds, or multipliers often need a range such as `0..1`.

Example:

```yaml
fraud:
  risk-threshold: 0.75
```

Prefer `BigDecimal` when exact decimal values are needed for business calculations.

```java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "fraud")
public record FraudProperties(
        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        BigDecimal riskThreshold) {
}
```

Cases:

| `risk-threshold` | Expected Result |
| --- | --- |
| `0.0` | Valid |
| `0.75` | Valid |
| `1.0` | Valid |
| `-0.1` | Invalid |
| `1.5` | Invalid |
| Missing | Invalid due to `@NotNull` |

`@DecimalMin` and `@DecimalMax` take string bounds to preserve exact precision. You can set `inclusive = false` when open bounds are needed, such as strictly greater than 0 rather than greater than or equal to 0.

Do not put `@Min(0) @Max(1)` on a `double` or `float` assuming all providers evaluate floating-point bounds accurately. For decimals, `@DecimalMin` and `@DecimalMax` with `BigDecimal` are clearer and more reliable.

## 11. Constraining Email Addresses with `@Email`

Email addresses are a classic example of strings with a dedicated format rule.

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record MailProperties(
        @NotBlank @Email String fromAddress) {
}
```

With data:

```yaml
mail:
  from-address: "ops@example.invalid"
```

A `@ConfigurationProperties(prefix = "mail")` bean binds `fromAddress` and applies the constraints.

States to distinguish:

- `""`: rejected by `@NotBlank`.
- `"   "`: rejected by `@NotBlank`.
- `"not-an-email"`: rejected by `@Email` as invalid email syntax.
- `"ops@example.invalid"`: formatted like an email for illustration, yet **does not guarantee the mailbox exists**.

**`@Email` checks syntax per the Bean Validation provider's rules; it does not verify that the email account works, the domain has MX records, or the user owns the address.** Verifying live email ownership belongs in a separate workflow, not binding.

Also, constraints like `@Email` treat `null` as valid per Bean Validation conventions; when the address is required, pair it with `@NotBlank` or `@NotNull` rather than using `@Email` alone.

## 12. Constraining URLs, URIs, and Callback Endpoints

In Java, network addresses should usually use `URI` instead of being passed across layers as `String`.

Example:

```yaml
webhook:
  callback-uri: "https://hooks.example.invalid/events"
```

Record:

```java
import java.net.URI;
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "webhook")
public record WebhookProperties(
        @NotNull URI callbackUri) {
}
```

Spring Boot can convert a syntactically valid URI string into `java.net.URI`.

However, a `URI` **is not necessarily** an absolute HTTPS URL. Values like `file:/tmp/example` or `/relative/path` are syntactically valid URIs yet unsuitable when the application requires an HTTPS callback.

Add explicit business checks:

- `callbackUri` must not be null.
- Scheme must be `https`.
- Address must have a hostname.
- If business rules require it, port and path must satisfy specific limits.

### 12.1. Validating an HTTPS URI Inside a Record

You can use a record's compact constructor to guard the invariant:

```java
package com.example.configdemo;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "webhook")
public record WebhookProperties(URI callbackUri) {

    public WebhookProperties {
        if (callbackUri == null
                || !"https".equalsIgnoreCase(callbackUri.getScheme())
                || callbackUri.getHost() == null) {
            throw new IllegalArgumentException(
                    "webhook.callback-uri must be an HTTPS URI with a hostname");
        }
    }
}
```

When Spring Boot constructor-binds this record, the constructor checks the already-converted `URI`. If it fails, object instantiation fails and the error surfaces during initialization.

Constructor validation is a **complementary approach** alongside Jakarta Bean Validation; it is not a standard constraint annotation.

In production systems, checking `https` and hostname alone does not guarantee connection security: if endpoints come from untrusted sources, consider SSRF, redirects, host allowlists, DNS, and network policies. Config validation does not replace HTTP client security controls.

### 12.2. Is `@Pattern` Enough for URL Strings?

You could write:

```java
@Pattern(regexp = "^https://.+")
String callbackUrl;
```

yet that regex only proves the string starts with a prefix; it does not validate full URI structure, hostname, port, or security requirements.

For connection addresses, prefer **converting to `URI`** and validating meaningful components. Reserve simple regexes for genuinely simple text conventions.

### 12.3. IP Addresses and Hostnames

A configuration may include `server-host` or an internal IP address.

- `@NotBlank` only ensures non-whitespace text.
- `@Pattern` can restrict character patterns, yet hand-rolled regexes for all IPv4/IPv6 forms are notoriously error-prone.
- Resolving DNS and testing host reachability is distinct from syntax validation.

For network data, clarify the exact need: domain name, absolute URI, IP literal, or internal hostname. Choose the right type, validator, or library rather than a catch-all regex.

## 13. Constraining Required Values

In any system, some keys have no safe default: payment gateway URLs, tenant IDs, notification sender emails, storage bucket names, authentication credentials.

Example:

```yaml
payment:
  provider-id: "gateway-a"
  callback-uri: "https://pay.example.invalid/callback"
```

Declaration:

```java
import java.net.URI;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        @NotBlank String providerId,
        @NotNull URI callbackUri) {
}
```

If `provider-id` is missing, `String` can become null during binding; `@NotBlank` catches it.

If `callback-uri` is missing, `@NotNull` catches the absent `URI` object.

**Required does not mean checking whether the key appears in a specific file.** What matters is that the final effective value meets requirements. A property might come from an environment variable or CLI flag instead of YAML and still be completely valid.

For passwords or tokens, avoid printing secret values in custom diagnostic messages. Bean Validation is only one piece of protecting sensitive configuration.

## 14. Default Values and Required Constraints

Spring Boot supports `@DefaultValue` for constructor binding. For instance:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "job")
public record JobProperties(
        @NotBlank String queueName,
        @DefaultValue("3") @Min(1) int maxAttempts) {
}
```

If `job.max-attempts` is absent from config, the Binder uses `3`. `@Min(1)` remains valuable because other sources can supply `0` or a negative number.

Since `job.queue-name` is required and has no default, `@NotBlank` makes the application reject missing or empty values.

Classify configuration keys into three tiers:

1. **Must be supplied by the deployer:** `queueName`, specific endpoints, tenant identifiers.
2. **Have sensible defaults:** retry counts, batch sizes, certain timeouts.
3. **Truly optional:** properties that can remain null or omitted while the application works normally.

Do not add dummy defaults to required properties just to let the app boot; for instance, `payment.api-key=placeholder` causes misconfiguration to surface later and more confusingly.

### 14.1. Missing vs. Empty Are Distinct Cases

For `String`, three cases:

```properties
# Key omitted
```

```properties
job.queue-name=
```

```properties
job.queue-name=   
```

can travel through different conversion/binding paths, yet if the final result is null, empty, or whitespace-only, `@NotBlank` catches all three.

For `Integer`, `@NotNull` catches missing values; for primitive `int`, account for default `0` or add numeric range constraints.

## 15. Complete Example: Multi-Type Configuration Group

Now let's build a comprehensive example combining strings, email, URI, integers, decimals, and nested objects.

### 15.1. `application.yml`

```yaml
delivery:
  sender-name: "Order Service"
  sender-email: "ops@example.invalid"
  callback-uri: "https://hooks.example.invalid/delivery"
  max-attempts: 4
  retry-ratio: 0.50
  recipients:
    - billing
    - operations
  proxy:
    host: "proxy.internal"
    port: 8080
```

### 15.2. Record Using Bean Validation

```java
package com.example.configdemo;

import java.math.BigDecimal;
import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotBlank @Size(max = 80) String senderName,
        @NotBlank @Email String senderEmail,
        @NotNull URI callbackUri,
        @Min(1) @Max(20) int maxAttempts,
        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        BigDecimal retryRatio,
        @NotEmpty
        List<@NotBlank String> recipients,
        @NotNull @Valid Proxy proxy) {

    public record Proxy(
            @NotBlank String host,
            @Min(1) @Max(65535) int port) {
    }
}
```

Key points:

- `senderName` must have non-whitespace content and be at most 80 characters.
- `senderEmail` must have content and match provider email syntax.
- `callbackUri` must exist and bind to `URI`.
- `maxAttempts` must be between 1 and 20.
- `retryRatio` must exist and lie in `[0,1]`.
- `recipients` must not be empty; each string element carries `@NotBlank`.
- `proxy` must exist, and its inner fields are validated via `@Valid`.

`@Valid` on the nested object is critical: it asks Bean Validation to cascade into `Proxy`'s constraints. `@NotNull` adds the requirement that the nested object itself cannot be omitted.

**Note:** `@NotNull URI callbackUri` does not check the HTTPS scheme; add a dedicated constraint or constructor check as shown earlier if business rules require it.

### 15.3. Registration and Usage

In the application class:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

With imports:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
```

A service using the configuration:

```java
package com.example.configdemo;

import org.springframework.stereotype.Service;

@Service
public class DeliveryService {

    private final DeliveryProperties properties;

    public DeliveryService(DeliveryProperties properties) {
        this.properties = properties;
    }

    public boolean canRetry(int currentAttempt) {
        return currentAttempt < properties.maxAttempts();
    }

    public String senderName() {
        return properties.senderName();
    }
}
```

The configuration bean has already been converted and validated before the service reads its values during normal Spring initialization.

Do not invoke Bean Validation manually on every incoming request just to re-check immutable configuration data.

## 16. Validation on Nested Configuration Objects

Nested configuration is very common:

```yaml
gateway:
  endpoint: "https://gateway.example.invalid"
  retry:
    attempts: 3
    delay: 2s
```

Java:

```java
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        @NotNull String endpoint,
        @NotNull @Valid Retry retry) {

    public record Retry(
            @Min(1) int attempts,
            @NotNull Duration delay) {
    }
}
```

When `gateway.retry.attempts=0`, the constraint on the nested record must be evaluated. `@Valid` tells validation to descend into `Retry`.

If the entire `gateway.retry` branch is absent, the Binder can create the parent record with `retry=null`. In that case:

- `@Valid` alone does not require a null reference to be present.
- `@NotNull` on `retry` is what requires the branch to exist.

This is a very common mistake: placing constraints on the child class while **forgetting both `@NotNull` and cascaded `@Valid` on the parent**.

For optional branches, omit `@NotNull` while keeping `@Valid` so the branch is validated when present. The right design depends on business semantics.

## 17. Constraining Lists and Their Elements

A collection can satisfy a size constraint while its elements remain invalid.

Example:

```yaml
access:
  allowed-groups:
    - billing
    - ""
    - audit
```

Record:

```java
import java.util.List;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "access")
public record AccessProperties(
        @NotEmpty
        @Size(max = 10)
        List<@NotBlank String> allowedGroups) {
}
```

Constraints:

- `@NotEmpty`: the list must exist and contain at least one element.
- `@Size(max = 10)`: the list cannot exceed 10 elements.
- `List<@NotBlank String>`: each string value must not be null, empty, or whitespace-only.

This combination validates both **collection shape** and **individual element values**.

If elements are complex objects, use cascaded validation `List<@Valid Entry>` to evaluate each object's constraints.

Rules such as "no duplicate groups" or "elements must belong to an allowed permission catalog" are not automatically enforced by `@NotBlank` and `@Size`; add custom constraints or business logic for those.

## 18. Type Conversion vs. Address and Duration Validation

Consider:

```yaml
gateway:
  timeout: -5s
  endpoint: "/relative/path"
```

Java:

```java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        java.time.Duration timeout,
        java.net.URI endpoint) {
}
```

Spring Boot's converters can create a negative `Duration` and a relative `URI`; they are **type-valid** yet unsuitable for their intended purpose.

If business logic requires:

- Timeout must be greater than 0.
- Endpoint must use HTTPS and have a host.

check these conditions explicitly, for example in a compact constructor:

```java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        java.time.Duration timeout,
        java.net.URI endpoint) {

    public GatewayProperties {
        if (timeout == null
                || timeout.isZero()
                || timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "gateway.timeout must be a positive duration");
        }
        if (endpoint == null
                || !"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null) {
            throw new IllegalArgumentException(
                    "gateway.endpoint must be an HTTPS URI with a host");
        }
    }
}
```

Constructor checks guard the **Java object's invariants**, even when the record is instantiated directly in unit tests. If you want errors surfaced as Bean Validation constraints, write a custom constraint or `@AssertTrue` method as appropriate.

Whichever option you choose, keep messages clear and avoid revealing secrets.

## 19. Cross-Property Constraints

Some rules cannot be expressed using `@Min` or `@NotBlank` on a single field:

- `minThreads` must be less than or equal to `maxThreads`.
- If proxy is enabled, `proxyHost` must be provided.
- If OAuth is enabled, both client ID and secret must be present.
- If retry is enabled, delay must be positive.

Example:

```java
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "pool")
public record PoolProperties(
        @Min(1) int minThreads,
        @Min(1) int maxThreads) {

    public PoolProperties {
        if (minThreads > maxThreads) {
            throw new IllegalArgumentException(
                    "pool.min-threads must be <= pool.max-threads");
        }
    }
}
```

Field-level constraints block numbers under 1, while the constructor blocks inconsistent pairs.

In larger projects, you can create a **class-level custom Bean Validation constraint** to express multi-property relationships uniformly alongside standard Jakarta Validation constraints.

Avoid forcing multi-field relationships into convoluted single-field regexes; that quickly becomes unreadable and bug-prone.

## 20. Distinguishing Nulls, Primitive Defaults, and Blank Values

Consider three declarations:

```java
int maxAttempts;
Integer maxAttemptsBoxed;
String senderName;
```

With `int`, there is no null state; if a property is omitted, binding may yield `0` in some scenarios.

With `Integer`, null is possible; `@NotNull` is the right tool when a value is mandatory:

```java
@NotNull
@Min(1)
Integer maxAttempts;
```

With `String`, decide whether you want to forbid null, empty strings, or whitespace-only strings:

```java
@NotBlank
String senderName;
```

**If you need to distinguish "property omitted" from "explicitly set to 0," use the `Integer` reference type with an appropriate null constraint** instead of a primitive `int`.

However, if `0` is invalid anyway, `@Min(1)` on `int` still rejects missing properties whenever the resulting value is `0`. That design expresses a numeric domain requirement rather than key presence directly.

## 21. Constraints That Permit Null When Used Alone

A core Bean Validation rule: **many specialized constraints accept null**, because detecting missing values is delegated to `@NotNull`, `@NotBlank`, or `@NotEmpty`.

Examples:

```java
@Email String contactEmail;
@Size(max = 30) String label;
@Pattern(regexp = "[A-Z]+") String code;
@Min(1) Integer retryCount;
```

In these cases, using the specialized constraint alone does not make null an error.

To make them required, combine them:

```java
@NotBlank @Email String contactEmail;
@NotBlank @Size(max = 30) String label;
@NotBlank @Pattern(regexp = "[A-Z]+") String code;
@NotNull @Min(1) Integer retryCount;
```

Treat "must be present" and "if present, must match format/range" as two separate conditions. That separation makes optional properties easy to model cleanly.

## 22. Key Typos Are Not Value Validation Errors

Suppose the bean expects:

```java
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(int maxAttempts) {
}
```

Yet YAML has:

```yaml
delivery:
  max-attempst: 4
```

This is a **key name error**. The Binder does not guess that `max-attempst` means `max-attempts`.

If the field is `int`, `maxAttempts` may end up as `0`. `@Min(1)` can indirectly catch the invalid `0`, yet the reported error says "value out of range" rather than pointing out the misspelled key.

Spring Boot provides:

```java
@ConfigurationProperties(
        prefix = "delivery",
        ignoreUnknownFields = false)
```

which tells the Binder not to ignore unbound keys within that bean's scope.

However, **`ignoreUnknownFields = false` does not scan every property across all sources or all prefixes**. If an operator misspells the prefix itself (`delivary` instead of `delivery`), the bean prefixed `delivery` never sees those keys. Required-value validation and configuration tests remain essential.

A sound design combines:

- Clear prefixes in kebab-case.
- Strict unknown-field checks on tightly controlled groups.
- Validation on required properties.
- Deliberate startup tests for valid and invalid configurations.

## 23. Type Conversion Errors vs. Numeric Constraint Errors

These are two distinct scenarios.

**Case A — type mismatch:**

```yaml
delivery:
  max-attempts: many
```

Bean expects:

```java
int maxAttempts
```

The string `many` cannot convert to `int` under standard rules. An error occurs at the conversion/binding layer before numeric validation ever runs.

**Case B — right type, violated constraint:**

```yaml
delivery:
  max-attempts: -2
```

`-2` converts to `int`, and then `@Min(1)` rejects it.

The fixes differ:

- For A: fix the input value/format, or register a suitable converter if a custom domain type is genuinely needed.
- For B: fix the value to satisfy the contract, or update the constraint if business rules changed.

Do not paper over conversion errors on critical configuration by setting `ignoreInvalidFields = true` just to let the app boot, because ignoring malformed values leaves the app running in an unintended state.

## 24. How Does Spring Boot Report Validation Failures?

When Spring Boot binds a validated `@ConfigurationProperties` bean with invalid data, `ApplicationContext` creation typically fails. Logs may show:

- The prefix or configuration bean name being bound.
- The problematic configuration key.
- The rejected value or failure reason.
- The violated constraint and message.
- `PropertySource` origin info, when available.

Example configuration:

```yaml
delivery:
  sender-name: "   "
  max-attempts: -1
```

Bean:

```java
@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotBlank String senderName,
        @Min(1) int maxAttempts) {
}
```

A startup attempt can report failures along the lines of:

```text
delivery.sender-name: must not be blank
delivery.max-attempts: must be greater than or equal to 1
```

This is a **conceptual illustration of the error meaning**, not a verbatim guarantee across every Spring Boot version or Bean Validation provider. The outer exception may be `ConfigurationPropertiesBindException` or a bean-creation failure wrapping the underlying validation cause.

If an error occurs only when the production profile is active, inspect the sources loaded for that profile rather than editing a default YAML file that was overridden or unused.

## 25. Effective Values Determine Validation Outcomes

Suppose `application.yml` contains:

```yaml
delivery:
  max-attempts: 3
```

and the bean requires:

```java
@Min(1) @Max(20) int maxAttempts
```

Normal run:

```bash
java -jar app.jar
```

`3` is valid if no other source overrides it.

But if run with:

```bash
java -jar app.jar --delivery.max-attempts=-10
```

CLI arguments outrank Config Data in standard Spring Boot setups. The Binder takes `-10` as the effective value, and validation rejects it.

This shows **a valid `application.yml` does not guarantee a valid run**: environment variables, Java system properties, CLI flags, and external configs can all alter bound values.

When diagnosing, ask "what value did Spring actually resolve for this run?" instead of looking at only one file.

## 26. Writing Clear Error Messages

Jakarta Validation supports a `message` attribute:

```java
@Min(value = 1, message = "Attempt count must be at least 1")
@Max(value = 20, message = "Attempt count must not exceed 20")
int maxAttempts;
```

For strings:

```java
@NotBlank(message = "Sender name must not be blank")
String senderName;
```

Messages should state clearly:

1. What property or setting is affected.
2. Why the value is invalid.
3. What bounds or format are allowed.

For instance, "Attempt count must be between 1 and 20" is far more helpful than "invalid property."

Never include **tokens, passwords, or access keys** in custom error messages. When frameworks log property values automatically, control log levels and secret management carefully in real environments.

## 27. Testing Validation with `ApplicationContextRunner`

Testing configuration in a lightweight `ApplicationContext` catches mistakes before running the full app.

Suppose we have the record:

```java
package com.example.configdemo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotBlank String senderName,
        @Min(1) @Max(20) int maxAttempts) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class DeliveryPropertiesValidationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void acceptsValidConfiguration() {
        runner.withPropertyValues(
                "delivery.sender-name=Order Service",
                "delivery.max-attempts=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            DeliveryProperties properties =
                    context.getBean(DeliveryProperties.class);

            assertThat(properties.maxAttempts()).isEqualTo(4);
            assertThat(properties.senderName()).isEqualTo("Order Service");
        });
    }

    @Test
    void rejectsBlankSender() {
        runner.withPropertyValues(
                "delivery.sender-name=   ",
                "delivery.max-attempts=4"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void rejectsOutOfRangeAttempts() {
        runner.withPropertyValues(
                "delivery.sender-name=Order Service",
                "delivery.max-attempts=0"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class TestConfig {
    }
}
```

These tests verify:

- Valid data creates the bean.
- Whitespace-only strings are rejected.
- Numbers below the minimum are rejected.

Ensure tests have a compatible Bean Validation provider; without the validation dependency, cases expected to fail may pass unchecked.

`ApplicationContextRunner` focuses on binding and context creation, staying lighter than `@SpringBootTest` when testing a single configuration class.

### 27.1. Testing HTTPS URIs

With a record that validates a URI in its constructor:

```java
@ConfigurationProperties(prefix = "webhook")
public record WebhookProperties(URI callbackUri) {

    public WebhookProperties {
        if (callbackUri == null
                || !"https".equalsIgnoreCase(callbackUri.getScheme())
                || callbackUri.getHost() == null) {
            throw new IllegalArgumentException(
                    "Callback must be an HTTPS URI with a host");
        }
    }
}
```

Building a context with `webhook.callback-uri=https://hooks.example.invalid/events` satisfies the constructor check, while `webhook.callback-uri=http://hooks.example.invalid/events` fails the HTTPS requirement.

With constructor validation, errors occur during object instantiation before other Jakarta constraints are evaluated. Be clear about whether you are testing **Bean Validation** or **constructor invariants**, and write tests targeting that mechanism.

## 28. Testing Configuration Across Multiple Profiles

Suppose:

```yaml
# application.yml
delivery:
  max-attempts: 3
```

and:

```yaml
# application-prod.yml
delivery:
  max-attempts: 50
```

Record:

```java
@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @Min(1) @Max(20) int maxAttempts) {
}
```

If tests only run with the `dev` profile, the app looks valid. When `prod` is activated, `50` violates `@Max(20)`.

A full application test can activate a profile:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("prod")
class ProductionConfigurationTest {

    @Test
    void contextStartsWithProductionConfiguration() {
        // If production config is invalid, the context can
        // fail before the test method executes.
    }
}
```

When the goal is asserting that invalid config **makes the context fail** and inspecting the cause, `ApplicationContextRunner` with explicit properties is usually easier to control than a `@SpringBootTest` designed to fail during bootstrap.

Lesson: validate against the profiles and property sources actually used in deployment, not just values in the base file.

## 29. When Should You Write a Custom Bean Validation Constraint?

Built-in annotations cannot express every rule, especially for:

- HTTPS addresses belonging to a specific allowlist.
- Tenant codes matched against a business catalog.
- Relationships between `minThreads` and `maxThreads`.
- Consistency across an option group.
- Internal naming rules for queues, buckets, or regions.

You can create a custom annotation such as `@HttpsEndpoint` and a `ConstraintValidator` that parses the `URI` to check scheme and host.

Conceptual skeleton:

```java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

import java.net.URI;

public class HttpsEndpointValidator
        implements ConstraintValidator<HttpsEndpoint, URI> {

    @Override
    public boolean isValid(
            URI value, ConstraintValidatorContext context) {
        if (value == null) {
            return true; // @NotNull handles missing values.
        }
        return "https".equalsIgnoreCase(value.getScheme())
                && value.getHost() != null;
    }
}
```

To use it in a project, define the `@HttpsEndpoint` annotation with `@Constraint(validatedBy = HttpsEndpointValidator.class)`, along with `@Target`, `@Retention(RUNTIME)`, and `message`, `groups`, `payload` members per the Jakarta Validation contract.

The snippet above illustrates the **validator logic**; it is not a complete standalone annotation definition ready to copy and compile by itself.

Only create custom constraints when the rule is reusable or needs unified integration with validation. For a simple invariant on a single small record, a constructor check may be easier to read.

## 30. Immutable Configuration and Validation

Constructor binding with Java records or classes with `final` fields is a common choice for configuration.

Example:

```java
@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @Min(1) int threadCount,
        @NotBlank String queueName) {
}
```

Values are resolved, converted, and used to instantiate the object. Validation ensures the record is accepted only when values satisfy constraints.

Distinguish four properties:

- **Immutability:** record components cannot be reassigned after construction.
- **Validation:** data must satisfy application rules.
- **Presence/required:** keys must supply non-null/non-blank values as required.
- **Source precedence:** decides which values the Binder sees.

An immutable record does not automatically guarantee `queueName` is non-blank—the `@NotBlank` constraint does that.

Conversely, a mutable JavaBean can still be validated when bound as a Spring Boot configuration bean. Immutability and validation are independent, even though combining them produces clear models.

## 31. Common Misconceptions

### 31.1. Assuming `@NotNull` Blocks Empty Strings

`@NotNull` permits `""`. When a string needs actual text, use `@NotBlank`.

### 31.2. Using `@Size` for Integers

`@Size(min=1, max=20) int maxAttempts` is not a valid way to bound integers. Use `@Min(1) @Max(20)`.

### 31.3. Using `@Email` to Prove an Email Exists

`@Email` checks syntax per the provider; it never verifies the mailbox, domain, or ownership.

### 31.4. Using `@NotNull URI` to Guarantee HTTPS

`@NotNull` only forbids null. A `URI` can still use `http`, `file`, or be relative. Add explicit scheme and hostname constraints when required.

### 31.5. Omitting `@Validated` and Expecting Constraints to Run

For `@ConfigurationProperties` validation, `@Validated` and a validation provider are essential configuration. Never rely on `@NotBlank` sitting on a POJO instantiated manually with `new`.

### 31.6. Forgetting `@Valid` on Nested Objects

If `GatewayProperties` holds a `Retry` with inner constraints but lacks cascaded validation, those inner constraints may go unevaluated. Add `@Valid` at the nesting boundary.

### 31.7. Thinking `@Valid` Forces Nested Objects to Exist

`@Valid` does not replace `@NotNull`. If the nested branch must be present, use both.

### 31.8. Confusing Type Mismatches with Range Violations

`retry-count=many` is a conversion failure to `int`. `retry-count=-3` is a valid integer that violates `@Min`.

### 31.9. Using Primitives with `@NotNull` to Catch Missing Keys

`@NotNull int maxAttempts` cannot signal "missing" the way `@NotNull Integer maxAttempts` can. `int` cannot be null.

### 31.10. Checking Only `application.yml` and Ignoring Other Sources

Validation inspects values bound from all effective sources. Environment variables or CLI arguments can override valid defaults with invalid values.

### 31.11. Treating Regex Checks as Security Validation

A URL starting with `https://` can still point to disallowed targets. Network access controls, allowlists, DNS checks, and SSRF protections go beyond string format validation.

### 31.12. Logging the Entire Config Bean During Diagnosis

Records holding tokens or passwords auto-generate a `toString()` exposing sensitive contents. Never log the full bean if it contains secrets.

## 32. Diagnostic Workflow When Startup Fails Due to Configuration

When encountering a binding or validation error, work through it step by step:

1. **Identify the prefix** of the failing `@ConfigurationProperties` bean.
2. **Identify the effective source:** CLI, env var, profile-specific Config Data, YAML/Properties, or import.
3. **Check exact key spelling:** typos, hyphens, camelCase, and prefix differences.
4. **Check the target Java type:** `int`, `Integer`, `BigDecimal`, `URI`, `Duration`, `String`...
5. **Separate conversion from validation:** did the value fail to convert, or did it convert and violate `@Min`, `@NotBlank`, etc.?
6. **Check presence constraints:** null, empty strings, missing nested branches.
7. **Verify validation wiring:** `@Validated`, provider dependency, and `@Valid` for nested objects.
8. **Run focused binding tests:** valid, missing, malformed, out-of-range, and nested cases.
9. **Fix the failing source and restart:** avoid disabling constraints just to get past errors without understanding the impact.
10. **Avoid leaking secrets:** verify presence or metadata rather than printing sensitive values.

The closer to startup a misconfiguration is caught, the easier its blast radius is to contain compared to bugs surfacing after processing real data.

## 33. Exercise A: Empty, Whitespace, and Overly Long Strings

Record:

```java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotBlank @Size(max = 12) String displayName) {
}
```

Predict the outcome for each value:

| `app.display-name` | Outcome |
| --- | --- |
| `"Inventory"` | Valid |
| `""` | Invalid due to `@NotBlank` |
| `"   "` | Invalid due to `@NotBlank` |
| `"Inventory Service Platform"` | Invalid for exceeding `@Size(max=12)` |

Follow-up question: if only `@NotNull` were used, would `""` be rejected?

Answer: No. `@NotNull` only checks for null.

## 34. Exercise B: Numeric Constraints

Record:

```java
@Validated
@ConfigurationProperties(prefix = "pool")
public record PoolProperties(
        @Min(1) @Max(64) int maxConnections) {
}
```

Configurations:

```properties
pool.max-connections=8
```

```properties
pool.max-connections=0
```

```properties
pool.max-connections=100
```

```properties
pool.max-connections=many
```

Answers:

- `8`: right type, within bounds.
- `0`: right type, violates `@Min(1)`.
- `100`: right type, violates `@Max(64)`.
- `many`: cannot convert to `int` under normal rules; conversion/binding error.

## 35. Exercise C: Required Email

Configuration:

```yaml
mail:
  from-address: ""
```

Record:

```java
@Validated
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        @NotBlank @Email String fromAddress) {
}
```

**Question:** What causes the configuration to be rejected?

`@NotBlank` rejects the empty string. If a non-blank string has invalid email syntax, `@Email` rejects it per provider rules.

If `@NotBlank` were removed leaving only `@Email`, you should not assume null/empty would always be rejected the same way.

## 36. Exercise D: Type-Valid URI Violating Business Requirements

Record:

```java
@ConfigurationProperties(prefix = "hook")
public record HookProperties(java.net.URI callback) {
}
```

Configuration:

```yaml
hook:
  callback: "http://hooks.example.invalid/events"
```

**Question:** Why does using `URI` alone fail to block this address even though the system requires HTTPS?

Because the string is a syntactically valid URI. You must add rules requiring the scheme to equal `https`, a non-null hostname, and related security checks.

## 37. Exercise E: Missing Nested Configuration

Record:

```java
@Validated
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        @NotNull @Valid Retry retry) {

    public record Retry(@Min(1) int attempts) {
    }
}
```

Configuration:

```yaml
gateway:
  enabled: true
```

**Question:** If the Binder does not create `retry` because the branch is absent, which constraint rejects it?

`@NotNull` on `retry`. `@Valid`'s role is to check the **inner** constraints when a `Retry` object exists.

## 38. Exercise F: Command-Line Arguments Overriding Valid Data

`application.yml`:

```yaml
worker:
  thread-count: 8
```

Record:

```java
@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @Min(1) @Max(32) int threadCount) {
}
```

Run:

```bash
java -jar app.jar --worker.thread-count=64
```

**Question:** Is the application guaranteed valid because YAML says `8`?

No. Under standard Spring Boot precedence, the CLI flag overrides YAML with `64`, and `@Max(32)` rejects that effective value.

## 39. Key Takeaways

- `@ConfigurationProperties` binds structured configuration; `@Validated` pairs with Bean Validation to check data as the bean is created.
- In Spring Boot 3.x, import constraints from `jakarta.validation.constraints` alongside a Bean Validation provider, typically via `spring-boot-starter-validation`.
- For **strings**, distinguish `@NotNull`, `@NotEmpty`, and `@NotBlank`; use `@Size` and `@Pattern` for length and format.
- For **numbers**, use `@Min`, `@Max`, `@Positive`, or `@DecimalMin`/`@DecimalMax` depending on type and requirements.
- For **emails**, `@Email` checks syntax rather than verifying live mailboxes; pair with `@NotBlank` when required.
- For **URIs/addresses**, bind to the right Java type and enforce scheme, hostname, port, or allowlist rules per business policy. `@NotNull URI` does not guarantee HTTPS.
- For **required values**, apply `@NotBlank`, `@NotNull`, and `@NotEmpty` appropriately; remember primitives have no null state.
- For **nested objects**, `@Valid` requests cascaded validation; `@NotNull` requires the object to exist.
- **Binding, conversion, and validation are three distinct responsibilities.** Right type does not guarantee business validity; constraints do not fix misspelled keys either.
- Effective values can come from profiles, environment variables, or CLI flags; test validation against realistic deployment scenarios.
- Write `ApplicationContextRunner` tests for valid, blank, missing, malformed, out-of-range, and nested cases to catch misconfigurations early.