# Distinguishing Successful Binding from Business-Valid Configuration — Spring Boot 3.3

## 1. The problem: does "Spring Boot bound it" mean the system is ready to run?

In Spring Boot, configuration can come from `application.properties`, `application.yaml`, files outside the JAR, environment variables, JVM system properties, and command-line arguments. When using `@ConfigurationProperties`, Spring Boot **binds** these values into a typed Java object. This is very useful, yet successful binding alone does not prove the configuration values are **reasonable, safe, or compliant with business requirements**.

Consider an example:

```yaml
app:
  payment:
    enabled: true
    retry-count: -3
    timeout: -2s
    endpoint: http://payments.example.test
```

A Binder can read these keys and convert their values into:

- `enabled`: `boolean` equal to `true`.
- `retryCount`: `int` equal to `-3`.
- `timeout`: `Duration` representing minus two seconds.
- `endpoint`: `URI` pointing to an `http` address.

Yet business rules might require:

- Negative retry counts are forbidden.
- Timeout must be **greater than 0**.
- When payments are enabled, the endpoint must use HTTPS.
- A critical endpoint must be configured and have a valid host.

**Successful binding only proves data was mapped and type-converted according to Binder rules; it does not mean the business rules above are satisfied.**

This is the focus of "Distinguishing Successful Binding from Business-Valid Configuration", part of **Binding Rules** in **Spring Boot Externalized Configuration**. Examples use Spring Boot **3.3.x**, Java **17+**, `@ConfigurationProperties`, and Jakarta Bean Validation.

## 2. Separating four independent questions

When an application starts, there are at least four distinct questions:

| Layer | Question | Example |
| --- | --- | --- |
| 1. Config source | Did the app receive the right final value? | Was `app.payment.timeout=5s` overridden by an env var? |
| 2. Binding / conversion | Can the data map to Java types? | Can string `5s` convert to `Duration`? |
| 3. Validation / config rules | Do converted values satisfy constraints? | Is timeout greater than 0? |
| 4. Business / operations | Does valid-on-paper config actually work? | Does the HTTPS endpoint have valid certs, access rights, connectivity, and capacity? |

The four layers cannot be conflated. An application can:

- **Read the right source but fail binding** because `max-workers=abc` cannot convert to `int`.
- **Bind successfully but fail validation** because `max-workers=0` violates `@Min(1)`.
- **Pass binding and validation but violate business policy** because `endpoint=http://...` while production mandates HTTPS.
- **Pass static checks yet still fail at runtime** because DNS, firewall, TLS certificates, remote services, or credentials are unavailable.

Mental diagram:

```text
PropertySource / Config Data / Environment
                 |
                 v
      Select effective value
                 |
                 v
      Binder + ConversionService
           |              |
         fails         succeeds
           |              |
   Type conversion        v
        error       Bean Validation
                      |         |
                  violated    valid
                      |         |
                  Startup     v
                  failure   Business rules
                              |        |
                          violated   passes
                              |        |
                           Reject      v
                                  Operational checks
                                        |
                                        v
                                Ready to serve?
```

Not every application needs to perform full connectivity checks when creating configuration beans. **The timing and error-handling policy** for operational checks is a separate architectural decision.

## 3. What does binding in Spring Boot 3.3 actually do?

The Spring Boot Binder reads configuration keys under a matching prefix and attempts to construct or populate a `@ConfigurationProperties` object.

Example:

```yaml
app:
  worker:
    threads: 4
    shutdown-timeout: 30s
    endpoint: https://worker.example.test
```

Java model:

```java
package example.validationlab;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int threads,
        Duration shutdownTimeout,
        URI endpoint
) {
}
```

With record constructor binding, the Binder can:

1. Recognize the keys `app.worker.threads`, `app.worker.shutdown-timeout`, `app.worker.endpoint`.
2. Map `shutdown-timeout` to Java parameter `shutdownTimeout` via **relaxed binding**.
3. Convert `4` into an integer.
4. Convert `30s` into a `Duration`.
5. Convert the URL string into a `URI`.
6. Instantiate `WorkerProperties` carrying those values.

Within that scope, **successful binding** is reliable: Spring Boot loaded, matched names, and converted types according to Binder capabilities.

Yet `threads=-20` is still a valid `int`; `shutdown-timeout=-3s` can still be a valid `Duration`; and `URI.create("relative-path")` constructs a syntactically valid relative URI, even though business logic wants an absolute HTTPS URL. Those constraints do not appear automatically just from declaring Java types.

### 3.1. What do data types guarantee?

| Target type | What Binder/conversion provides | What is not guaranteed |
| --- | --- | --- |
| `int` | Converts valid integer values | Positive, within system limits |
| `long` | Accepts integers within type range | Unit meaning, resource limits |
| `boolean` | Converts supported boolean values | Whether enabling the feature is safe in this environment |
| `Duration` | Accepts durations like `5s`, `250ms` | Positive, not excessively large, fits SLA |
| `DataSize` | Accepts data sizes like `10MB` | Enough RAM/disk, within quota |
| `URI` | Accepts syntactically convertible URIs | HTTPS, valid host, reachable |
| `String` | Accepts text | Non-empty, valid identifier, no forbidden values |
| `List<T>` | Binds elements from config | Non-empty, no duplicates, valid order |
| `Map<K,V>` | Binds by keys and values | Required keys present, valid relationships across entries |

Do not confuse **type safety** with **business validity**. Type `int` cannot natively express "between 1 and 16"; type `URI` does not natively express "must be HTTPS and point to an authorized service".

### 3.2. Conversion failure is a different case

```properties
app.worker.threads=four
```

Without a matching custom converter, the Binder cannot convert `four` to `int` and can throw a binding error when creating the configuration bean.

Compare:

```properties
app.worker.threads=0
```

`0` **converts cleanly to `int`**. To reject zero, you need a constraint like `@Min(1)` or equivalent checking logic.

## 4. Four examples of "binds cleanly, should not run"

### 4.1. Worker count of 0

```properties
app.worker.threads=0
```

`int threads` accepts `0`. However, a service needing at least one worker to process tasks will not function properly.

An appropriate constraint:

```java
@Min(1)
int threads
```

If resource limits are needed:

```java
@Min(1)
@Max(16)
int threads
```

This states **the valid configuration range is 1–16**, distinct from the Binder's type-conversion capability.

### 4.2. Negative timeout

```properties
app.worker.shutdown-timeout=-2s
```

`Duration` can represent negative values. Many time-handling APIs reject negative timeouts or behave specially on zero/negative values.

A "greater than 0" rule is needed rather than relying solely on `Duration.class`. You can use a custom validator or an `@AssertTrue` method checking:

```java
@AssertTrue(message = "shutdownTimeout must be positive")
public boolean isShutdownTimeoutPositive() {
    return shutdownTimeout != null
            && shutdownTimeout.compareTo(Duration.ZERO) > 0;
}
```

### 4.3. Syntactically valid URI violating security policy

```properties
app.payment.endpoint=http://payments.example.test
```

The string above converts to `URI` cleanly. Yet if the payment service requires HTTPS, the configuration is still business-invalid.

Additional checks:

- The URI must be an **absolute URI**.
- The scheme must be `https`.
- The host must be present.
- If needed, the host must belong to an allowlist.

Checking the URI with these rules still **does not** confirm DNS resolution, TLS certificates, network connectivity, or service authorization.

### 4.4. Empty list

```yaml
app:
  notification:
    recipients: []
```

An empty list can bind to a valid `List<String>`. Yet a notification feature that requires recipients cannot fulfill its purpose.

Use `@NotEmpty` to require at least one element; use `@NotBlank` on elements to forbid empty or whitespace-only strings.

These are two distinct constraints:

```java
@NotEmpty
List<@NotBlank String> recipients
```

- `@NotEmpty`: the list cannot be `null` or empty.
- `@NotBlank` on elements: each address string cannot be blank.

Furthermore, "non-blank" does not mean **valid email** or **deliverable address**. You can add `@Email` for email syntax or corresponding business rules.

## 5. `@ConfigurationProperties` does not automatically activate Bean Validation for every class

For Spring Boot to check constraints during binding, you typically need:

1. A Jakarta Bean Validation implementation on the classpath, such as the `spring-boot-starter-validation` dependency.
2. `@Validated` on the `@ConfigurationProperties` type (or an equivalent mechanism allowed by documentation).
3. Constraints like `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@NotEmpty`, `@Valid`, `@AssertTrue` placed in the right positions.
4. Registering the configuration bean via Spring Boot mechanisms (`@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`).

**Merely declaring a record type or adding `@ConfigurationProperties` does not automatically enforce your organization's validation policy.**

### 5.1. Maven dependency

If the project uses Spring Boot parent or appropriate dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

The validation dependency is needed alongside `spring-boot-starter` or whichever starter the application uses.

Spring Boot 3 uses the Jakarta namespace:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
```

Do not copy `javax.validation.*` imports from Spring Boot 2.x examples into a Spring Boot 3.3 app without accounting for version differences.

### 5.2. `@Validated` and constraints have different roles

```java
@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @Min(1) int threads,
        @NotNull Duration timeout
) {
}
```

- `@ConfigurationProperties` declares that this type represents a configuration group.
- `@Validated` requests constraint verification through the validation mechanism.
- `@Min(1)` states the rule for `threads`.
- `@NotNull` states the presence requirement for `timeout`.

Without `@Min(1)`, there is no automatic rule that "`threads` must be positive". Without `@NotNull`, `timeout=null` may be permitted if absent with no default.

## 6. Common constraints and what they actually enforce

| Constraint | Used for | Does not guarantee by itself |
| --- | --- | --- |
| `@NotNull` | Reference value must be present | Non-empty string, HTTPS URI |
| `@NotBlank` | String has non-whitespace characters | Valid business format |
| `@NotEmpty` | String/collection/map/array is non-empty | Individual elements are valid |
| `@Min(n)` | Number is not less than `n` | Number does not exceed maximum |
| `@Max(n)` | Number is not greater than `n` | Number meets minimum |
| `@Positive` | Number must be positive | Fits budget/capacity limits |
| `@PositiveOrZero` | Number is non-negative | Within upper limit |
| `@Size(min,max)` | Length or element count within range | No duplicate elements |
| `@Pattern` | String matches given regex | Service reachable, data legitimate |
| `@Email` | String matches validator's email format | Mailbox actually receives mail |
| `@Valid` | Triggers nested validation | Creates a missing nested object |
| `@AssertTrue` | Boolean value or JavaBean property must be `true` | Undeclared business rules satisfied |

For instance, `@NotBlank` and `@NotNull` are not equivalent:

```java
@NotNull String tenant;
```

can allow an empty string `""`.

```java
@NotBlank String tenant;
```

rejects `null`, empty strings, and whitespace-only strings where supported by the validator.

A converted `URI` should use `@NotNull` for presence, then verify scheme/host via appropriate rules. Do not assume `@Pattern` applies directly to arbitrary Java types like `URI`.

## 7. Designing a configuration class with complete binding and validation

Suppose an application sends requests to a gateway. Business requirements:

- The feature can be enabled or disabled.
- When enabled, the endpoint must be an absolute HTTPS URI with a host.
- Worker parallelism must be between 1 and 16.
- Timeout must be positive.
- Retry configuration must exist, with attempts between 0 and 10 and non-negative backoff.
- There must be at least one target.
- Each target has a non-blank name and non-null URI.

### 7.1. Valid YAML

`src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: config-business-validation-demo

app:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test/api
    parallelism: 4
    timeout: 5s
    retry:
      attempts: 2
      backoff: 250ms
    targets:
      - name: primary
        url: https://primary.example.test
      - name: backup
        url: https://backup.example.test
```

### 7.2. Java `@ConfigurationProperties` record

`src/main/java/example/validationlab/DeliveryProperties.java`:

```java
package example.validationlab;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        boolean enabled,
        URI endpoint,
        @Min(1) @Max(16) int parallelism,
        @NotNull Duration timeout,
        @NotNull @Valid Retry retry,
        @NotEmpty List<@Valid Target> targets
) {
    @AssertTrue(message = "timeout must be greater than zero")
    public boolean isTimeoutPositive() {
        return timeout != null
                && timeout.compareTo(Duration.ZERO) > 0;
    }

    @AssertTrue(message = "enabled delivery requires an absolute HTTPS endpoint")
    public boolean isEndpointPolicyValid() {
        if (!enabled) {
            return true;
        }
        return endpoint != null
                && endpoint.isAbsolute()
                && "https".equalsIgnoreCase(endpoint.getScheme())
                && endpoint.getHost() != null;
    }

    public record Retry(
            @Min(0) @Max(10) int attempts,
            @NotNull Duration backoff
    ) {
        @AssertTrue(message = "retry backoff cannot be negative")
        public boolean isBackoffNonNegative() {
            return backoff != null && !backoff.isNegative();
        }
    }

    public record Target(
            @NotBlank String name,
            @NotNull URI url
    ) {
    }
}
```

In this record:

- The Binder reads data under prefix `app.delivery` and builds a typed object.
- `@Min`/`@Max` constrain integers.
- `@NotNull` guarantees nested `retry` and `timeout` exist.
- `@Valid` on `retry` and `Target` elements cascades validation into nested structures.
- `@NotEmpty` forbids an empty target list.
- Two `is...()` methods annotated with `@AssertTrue` express rules hard to capture with single numeric or string annotations.
- `enabled=false` intentionally permits omitting `endpoint` per `isEndpointPolicyValid()`.

`@AssertTrue` applies to JavaBean boolean properties with `is...` methods. The Spring Boot Binder does not infer `isTimeoutPositive()` and `isEndpointPolicyValid()` rules; verification is performed by **Bean Validation**.

### 7.3. Multiple constraints can be combined on one component

Example:

```java
@Min(1) @Max(16) int parallelism
```

Means "minimum 1 thread, maximum 16", not "Java can only bind numbers from 1 to 16".

Both `0` and `100` convert to `int` fine. They are rejected when **validation** enforces the declared constraints.

Similarly:

```java
@NotEmpty List<@Valid Target> targets
```

- The list must contain elements.
- Each element must pass `Target` validation.

If duplicate target `name` values must be forbidden, add another rule; `@NotEmpty` and `@NotBlank` do not check uniqueness.

## 8. Registering the configuration bean properly

Application class example:

`src/main/java/example/validationlab/ValidationLabApplication.java`:

```java
package example.validationlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ValidationLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showSummary(DeliveryProperties properties) {
        return args -> {
            System.out.println("enabled=" + properties.enabled());
            System.out.println("parallelism=" + properties.parallelism());
            System.out.println("timeout=" + properties.timeout());
            System.out.println("targets=" + properties.targets().size());
        };
    }
}
```

`@ConfigurationPropertiesScan` registers `DeliveryProperties` so Spring Boot can bind it from configuration. For a record with a single canonical constructor, `@ConstructorBinding` is not needed.

Using `@EnableConfigurationProperties(DeliveryProperties.class)` is also an option when specifying types explicitly, such as in a dedicated configuration module.

**Do not attach `@Component` casually to a constructor-bound record** expecting the Spring container to instantiate it via standard autowiring. `@ConfigurationProperties` constructor binding requires registration via the appropriate Spring Boot mechanism.

The `ApplicationRunner` method prints only non-sensitive sample values. Never print passwords, tokens, API keys, or values that could expose real infrastructure.

## 9. Running the example and interpreting results

With Maven wrapper on Unix systems:

```bash
./mvnw spring-boot:run
```

Or package as a JAR and run:

```bash
java -jar app.jar
```

Replace `app.jar` with your project's actual JAR path. With valid YAML, lines printed by `ApplicationRunner` look like:

```text
enabled=true
parallelism=4
timeout=PT5S
targets=2
```

This output shows configuration bound and passed declared validation constraints—it does not mean **the real gateway is reachable**. To know whether remote services are working, dedicated checks in the app or infrastructure are required.

### Trial 1 — type conversion error

```bash
java -jar app.jar --app.delivery.parallelism=abc
```

`abc` is not an integer. The error belongs to **binding/conversion**, occurring before a valid `int` exists to evaluate `@Min` and `@Max`.

### Trial 2 — binds cleanly, violates range

```bash
java -jar app.jar --app.delivery.parallelism=0
```

`0` is a valid integer, so the Binder converts it cleanly. Yet `@Min(1)` is violated; the app can fail during configuration validation.

### Trial 3 — negative Duration

```bash
java -jar app.jar --app.delivery.timeout=-2s
```

`-2s` is a representable duration. The `isTimeoutPositive()` constraint returns `false`, rejecting this configuration.

### Trial 4 — URI violates policy

```bash
java -jar app.jar --app.delivery.endpoint=http://gateway.example.test/api
```

The URI parses and binds normally. Yet with `enabled=true`, `isEndpointPolicyValid()` requires HTTPS, so validation fails.

### Trial 5 — reducing concurrency to a valid level

```bash
java -jar app.jar --app.delivery.parallelism=2
```

With other properties matching valid YAML, `2` falls within 1–16. The app passes static validation.

**Note:** the examples do not assume every error throws the same exception class or uses the exact same message format. Wrapper exception types can vary by converter, bean style, and startup phase; read the cause chain in the startup log.

## 10. Diagnostic table for four states

| Config value | Binding / conversion | Validation | Assessment |
| --- | --- | --- | --- |
| `parallelism=abc` | Fails | No valid value to check yet | Wrong type |
| `parallelism=0` | Succeeds (`int`) | Fails `@Min(1)` | Out of bounds |
| `parallelism=4` | Succeeds | Passes declared constraints | Does not guarantee sufficient CPU |
| `timeout=-2s` | Can succeed (`Duration`) | Fails `@AssertTrue` | Violates timeout policy |
| `endpoint=http://...` | Can succeed (`URI`) | Fails HTTPS policy when enabled | Violates transport policy |
| `endpoint=https://...` | Succeeds | Can pass static policy | DNS/TLS/service can still fail |
| `targets=[]` | Can succeed (`List`) | Fails `@NotEmpty` | No targets |
| `target.name="   "` | Succeeds (`String`) | Fails `@NotBlank` | Unusable name |
| `retry.attempts=2` | Succeeds | Passes `@Min(0) @Max(10)` | Does not prove retry strategy helps |

When an application starts cleanly, the next question is not just **"Did it bind?"**, but **"Which constraints were actually verified?"**

## 11. Missing keys do not necessarily fail binding

Suppose the record is:

```java
@ConfigurationProperties(prefix = "app.queue")
public record QueueProperties(
        int capacity,
        boolean enabled,
        String name
) {
}
```

If some keys are missing:

- `int` can receive the primitive default (`0`) in appropriate binding.
- `boolean` can receive `false`.
- `String` can be `null`.
- For many other reference types, missing values can become `null` without defaults or special handling.

Do not assume that because a record constructor has parameters, **every parameter is required** and Spring Boot will reject missing keys. Constructor binding governs how arguments are supplied, not whether they are mandatory in business rules.

If `capacity=0` is dangerous, declare:

```java
@Min(1) int capacity
```

If `name` is required:

```java
@NotBlank String name
```

If `enabled=false` is an acceptable default, express that intent clearly in the model or configuration documentation.

### 11.1. Defaults can mask missing configuration

Example:

```java
@ConfigurationProperties(prefix = "app.queue")
public record QueueProperties(
        @DefaultValue("100") int capacity
) {
}
```

When `app.queue.capacity` is absent, the Binder can supply `100`. This fits if `100` is a business-approved default. Yet if production **must** specify capacity after capacity sizing, a silent default can leave the system running at an unintended resource level.

`@DefaultValue` answers "what to use when the key is absent", **not** "whether the key is allowed to be absent in this environment".

### 11.2. Do not treat defaults as a cure-all

The value:

```properties
app.queue.capacity=-3
```

is still a concrete integer. `@DefaultValue("100")` does not replace `-3` because the number exists. To reject negative numbers, you still need `@Min(1)` or an equivalent rule.

If the user enters:

```properties
app.queue.capacity=not-a-number
```

the issue is type conversion; defaults do not turn invalid strings into valid numbers.

## 12. Do not ignore unrecognized configuration keys

Spring Boot `@ConfigurationProperties` has an important option:

```java
@ConfigurationProperties(
        prefix = "app.delivery",
        ignoreUnknownFields = false
)
```

By default, `ignoreUnknownFields` is `true`. This lets the Binder tolerate keys without matching properties on the target type, yet can allow **typos** or leftover keys to go unnoticed.

Example:

```properties
app.delivery.paralellism=8
```

`paralellism` is misspelled. Because it does not match `parallelism`, the Binder can ignore the unrecognized key while `parallelism` gets a default or missing value depending on type.

Two layers of failure occur:

1. The source configuration contains an **unknown** key.
2. The intended field is **missing**.

When a configuration model represents a clearly owned schema, consider `ignoreUnknownFields=false` to catch extra keys. Understand prefix scopes and active config sources before turning on strict mode, especially if multiple components consume keys under a shared prefix.

Another option:

```java
@ConfigurationProperties(ignoreInvalidFields = false, prefix = "app.delivery")
```

`ignoreInvalidFields` defaults to `false`, meaning binding/conversion errors are not ignored. It **does not replace business validation**. Turning on `ignoreInvalidFields=true` recklessly can mask wrongly typed data rather than making the application "more resilient".

Decisions on unknown fields and invalid fields belong to **input configuration policy**, whereas rules like "timeout > 0" still need a dedicated validation layer.

## 13. Cross-field rules cannot be inferred from single-field types

Many business rules take the form "if A then B", for example:

- If email sending is enabled, `from-address` and `smtp.host` must exist.
- If `retry.attempts > 0`, `retry.backoff > 0`.
- If `enabled=true`, the endpoint must use HTTPS.
- `min-size` must not exceed `max-size`.
- If `mode=EXTERNAL`, `provider-id` is required.
- If `primary` exists, a backup route matching policy must exist.

`@NotNull`, `@Min`, and `@Max` on individual fields cannot fully express **relationships between fields**.

### 13.1. Use `@AssertTrue` for small, readable rules

Suppose:

```java
@Validated
@ConfigurationProperties(prefix = "app.pool")
public record PoolProperties(
        @Min(1) int minSize,
        @Min(1) int maxSize
) {
    @AssertTrue(message = "minSize must not exceed maxSize")
    public boolean isRangeConsistent() {
        return minSize <= maxSize;
    }
}
```

Configuration:

```properties
app.pool.min-size=10
app.pool.max-size=3
```

Both numbers are >= 1, yet `minSize <= maxSize` is violated.

Thus:

- Per-field validation: **passes**.
- Cross-field validation: **fails**.
- Binding: **succeeds**.

This cleanly illustrates separating type-conversion results from business correctness.

### 13.2. When do you need a custom constraint?

If a cross-field rule is complex, a lengthy `@AssertTrue` method makes the record hard to maintain. You can build a **custom Jakarta Bean Validation constraint** at the class level with a dedicated `ConstraintValidator`.

A custom validator typically receives the entire configuration object, compares fields, and emits a meaningful violation message. It is useful when:

- The rule is reused across multiple configuration groups.
- The rule involves many fields and conditions.
- You want clear error reporting on the right property.
- You want to separate configuration business logic from model data.

**Avoid putting I/O, HTTP calls, database connections, or remote secret lookups inside a `ConstraintValidator` as a general practice.** Configuration validation happens very early; heavy or flaky external checks can cause hard-to-explain startup failures.

## 14. Nested object validation must be enabled explicitly

An example:

```java
@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        @NotNull @Valid Smtp smtp
) {
    public record Smtp(
            @NotBlank String host,
            @Min(1) @Max(65535) int port
    ) {
    }
}
```

`@NotNull` on `smtp` ensures the nested object is not missing.

`@Valid` tells Bean Validation to descend into `Smtp` to validate `host` and `port`.

**If you omit `@Valid`**, do not assume constraints inside nested objects will always be checked as expected. Spring Boot documentation highlights `@Valid` for nested property validation, especially when validating even if corresponding child keys were not found.

### 14.1. Lists of nested structures

```java
public record MailProperties(
        @NotEmpty List<@Valid Recipient> recipients
) {
    public record Recipient(
            @NotBlank String name,
            @NotBlank @Email String address
    ) {}
}
```

Required imports:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
```

- `@NotEmpty` on the list forbids having zero recipients.
- `@Valid` enters each `Recipient`.
- `@NotBlank` forbids blank names and addresses.
- `@Email` checks **format**, not whether mail is actually deliverable.

If business rules forbid duplicate addresses, add another rule; the annotations in this example do not check uniqueness.

### 14.2. Missing nested object vs nested object with invalid values

Consider:

```yaml
app:
  mail:
    smtp:
      host: ""
      port: 0
```

The Binder can instantiate `Smtp`, after which constraints on `host` and `port` fail.

If `smtp` is completely absent, a reference type inside the record can be `null`; `@NotNull` rejects that state. `@Valid` does not turn `null` into a new object. Combine presence requirements and cascade validation to fit the model.

## 15. Do `@Value` and `Environment` guarantee business validation automatically?

No.

Example:

```java
@Component
public class BatchWorker {

    @Value("${app.worker.threads:0}")
    private int threads;
}
```

`0` can convert to `int` and be injected cleanly. Using `@Value` does not automatically provide configuration validation equivalent to a properly registered and bound `@Validated @ConfigurationProperties` bean.

Similarly:

```java
int threads = environment.getProperty(
        "app.worker.threads", Integer.class, 0);
```

reading `0` does not mean `0` is appropriate for a worker pool.

For one or two small scalar values, you can validate business rules where they are used. But when a configuration group has multiple fields, relationships, and consumers, centralized `@ConfigurationProperties` + validation prevents every bean from inventing different rules.

One point to remember: `@Value` uses placeholder syntax and supports SpEL, yet **its relaxed binding is more limited** than `@ConfigurationProperties`. Use canonical `kebab-case` key names in placeholders; that is a **name-mapping** concern, entirely separate from business requirements.

## 16. The "right" value also depends on which source won

Suppose:

`application.yaml`:

```yaml
app:
  delivery:
    parallelism: 4
```

Yet the deployment environment sets:

```text
APP_DELIVERY_PARALLELISM=100
```

Or the launch command runs:

```bash
java -jar app.jar --app.delivery.parallelism=100
```

Under normal precedence rules, environment/CLI sources override file values. When the Binder binds, it does not "pick" `4` simply because YAML says `4`; it uses the **effective value** after `Environment` precedence rules.

With `@Max(16)`, validation can reject `100`. That is desirable: validation must run against the **final effective configuration**, not just default file values.

A configuration system can change values across:

- `application.yaml` packaged inside the JAR.
- `application-prod.yaml`.
- External configuration files.
- `spring.config.import`.
- Environment variables.
- JVM properties.
- Command-line arguments.

Finding "which source caused the bad value?" requires checking **source precedence**, not just comparing the Java class against one specific file.

### 16.1. Environment variable names must be exact

The canonical name `app.delivery.parallelism` corresponds to environment variable:

```text
APP_DELIVERY_PARALLELISM
```

For `app.delivery.retry-count`, the corresponding environment variable is:

```text
APP_DELIVERY_RETRYCOUNT
```

Spring Boot applies relaxed binding rules: replace `.` with `_`, remove `-`, and uppercase. Using the wrong environment variable name can cause the value not to bind as expected—which is a **binding/name-mapping** issue rather than business validation.

## 17. Not every constraint applies equally across all environments

Some values are valid only in a specific environment. For example:

- `http://localhost` may suit local development, while production mandates HTTPS.
- Worker count might be capped at 2 in test environments, yet allow up to 16 in production.
- A feature may omit its endpoint when disabled.
- One profile uses a stub service in development, while production requires a real endpoint.

Values can be organized by profile:

```yaml
app:
  delivery:
    enabled: false
    parallelism: 2
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test/api
    parallelism: 8
```

In this example, the `prod` document overrides `enabled`, `endpoint`, and `parallelism`.

However, **profiles do not create business constraints automatically**. If production requires HTTPS, use a conditional policy when `enabled=true` like `isEndpointPolicyValid()` above, or a dedicated validation mechanism.

Do not use `spring.profiles.active` inside a document activated by `spring.config.activate.on-profile` to re-control profile activation. Select profiles in a valid source and let conditional documents supply only the overriding settings.

### When should you use defaults?

If a value has a safe default identical across all environments, put it in shared configuration or `@DefaultValue`.

If a value must be supplied explicitly in production, avoid defaults that accidentally let the application start with the wrong configuration. Express "missing is an error" via validation or startup checks.

## 18. A syntactically valid URI may still be disallowed by security policy

Consider three values:

```properties
app.delivery.endpoint=relative/path
```

```properties
app.delivery.endpoint=http://gateway.example.test
```

```properties
app.delivery.endpoint=https://gateway.example.test
```

With `URI`, all three can parse successfully with different semantics.

Yet a gateway needing absolute HTTPS:

- `relative/path`: lacks scheme and host; unsuitable.
- `http://gateway.example.test`: has scheme/host, wrong protocol.
- `https://gateway.example.test`: meets declared syntactic policy.

Even the third URI can still:

- Point to a host that fails DNS resolution.
- Have an expired TLS certificate.
- Be blocked by a firewall.
- Lack valid authentication credentials.
- Respond with the wrong protocol or miss SLAs.

**Format checks** should happen before use. **External dependency checks** need appropriate timeout, retry, circuit-breaker, readiness, and error-reporting policies.

Never put an unbounded HTTP call or multiple connection retries inside a `@ConfigurationProperties` constructor just to prove a URI is "valid".

## 19. Three error types to report clearly in logs and operations

### Type A — type-conversion or key-resolution error

Example:

```properties
app.delivery.timeout=tomorrow
```

If the Binder has no way to convert `"tomorrow"` to `Duration`, configuration fails at the **type conversion** layer.

Helpful error messages should name the configuration key, expected type, and conversion cause. Do not try to "fix" this with `ignoreInvalidFields=true` if `timeout` is required.

### Type B — rightly typed value violating a constraint

Example:

```properties
app.delivery.parallelism=0
```

The integer value is valid, yet violates `@Min(1)`.

Messages should clearly state the allowed range for `parallelism`, avoiding vague messages like "Configuration invalid" that leave operators guessing which field to fix.

### Type C — passes static validation, external dependency unavailable

For example, a valid HTTPS endpoint where the server returns 503.

This is not a URI parsing error and not necessarily bad configuration. The remote service may be in maintenance or the network unready.

Handling depends on requirements:

- Mission-critical services may **fail fast** or mark themselves **not ready**.
- Optional features may run in an explicit degraded mode.
- The system can use bounded retries with backoff and observability metrics.

If every error is lumped together as "bind failed", operators will try to change valid config when the real issue is connectivity.

## 20. Deciding between fail-fast and graceful degradation

Not every discrepancy should be handled identically.

| Situation | Suggested policy |
| --- | --- |
| Required value fails type conversion | Typically fail startup |
| Value exceeds dangerous bounds | Typically fail startup |
| Missing critical details to enable a feature | Refuse to enable or fail per criticality |
| Feature disabled and endpoint unused | Endpoint may be optional |
| Auxiliary service temporarily unreachable | Rely on readiness, bounded retries, and degraded mode |
| Minor optional setting missing | Use an approved default |
| Config could cause data leaks | Never silently proceed with unsafe defaults |

A helpful guideline: **fail fast on clearly invalid configuration**; for dynamic dependencies, define deliberate fault-tolerance and readiness policies. Do not turn startup into endless connection retries against every external service.

In systems with feature toggles, validation should reflect conditional business rules. For instance, "`endpoint` required when `enabled=true`" is more accurate than "`endpoint` always required" if disabling the feature is allowed.

## 21. Configuration changing over time

Normally, `@ConfigurationProperties` is bound when the application context initializes. Changing an environment variable or configuration file after the Java process is running **does not mean** every bean automatically receives new data.

Example:

1. Application starts with `parallelism=4`.
2. Operator edits an environment variable in a terminal to `parallelism=16`.
3. The running process does not automatically update bean values.

If a system needs **dynamic configuration**, it must have a dedicated refresh mechanism and clearly specify:

- Which settings are allowed to refresh.
- When validation runs again.
- Whether old values stay in effect if new values are invalid.
- How application health is reported when reload fails.
- Whether locking or atomic swaps are needed when multiple beans read configuration.

**A value that bound and validated cleanly at startup does not prove all configuration stays valid if the environment changes.**

## 22. Testing configuration correctness

A clear test strategy separates test cases cleanly.

### 22.1. Minimal test matrix

| Test | Changed value | Expectation |
| --- | --- | --- |
| Valid values | `parallelism=4`, `timeout=5s`, HTTPS | Starts cleanly |
| Unconvertible type | `parallelism=abc` | Binding error |
| Below lower bound | `parallelism=0` | Validation error |
| Above upper bound | `parallelism=100` | Validation error |
| Negative timeout | `timeout=-1s` | Business validation error |
| Missing retry | Omit entire `retry` group | `@NotNull` error if required |
| Empty targets | `targets=[]` | `@NotEmpty` error |
| Blank target name | `targets[0].name=""` | Element `@NotBlank` error |
| HTTP when enabled | `enabled=true`, `endpoint=http://...` | HTTPS policy error |
| Feature disabled | `enabled=false`, endpoint may be absent | Depends on declared policy |
| HTTPS with server down | `endpoint=https://...` | Static validation can pass, operational check fails |

These cases test **three distinct categories of behavior**, not merely whether a bean can be instantiated.

### 22.2. Unit testing rules with Jakarta Validator

You can validate a configuration object with Bean Validation without booting the entire application. Example with JUnit 5/AssertJ and the validation dependency in tests:

```java
package example.validationlab;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;

class DeliveryPropertiesValidationTest {

    @Test
    void rejectsHttpEndpointWhenEnabled() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            DeliveryProperties properties = new DeliveryProperties(
                    true,
                    URI.create("http://gateway.example.test"),
                    4,
                    Duration.ofSeconds(5),
                    new DeliveryProperties.Retry(
                            2, Duration.ofMillis(250)),
                    List.of(new DeliveryProperties.Target(
                            "primary",
                            URI.create("https://primary.example.test")))
            );

            var violations = validator.validate(properties);
            assertThat(violations)
                    .anyMatch(v -> v.getMessage()
                            .contains("absolute HTTPS endpoint"));
        }
    }
}
```

The test above constructs the Java object directly and invokes Bean Validation; it **tests validation rules**, and does not prove binding from YAML or environment variables works.

### 22.3. Integration testing the Binder

A separate test needs to load real configuration sources and verify:

- Keys are bound properly by the Binder under the prefix.
- `Duration` units and complex types convert accurately.
- Wrong types trigger binding errors.
- Bound values violating constraints prevent the application context from starting or surface appropriate validation errors.
- Higher-precedence profiles or arguments are respected.

In Spring Boot, you can use `ApplicationContextRunner` with `@EnableConfigurationProperties`/appropriate auto-configuration, or test a Spring Boot context with test properties. When writing tests, make sure validation infrastructure is actually configured rather than only checking bean creation.

**Rule unit tests** and **binding integration tests** complement each other; do not use one test's result to claim both mechanisms work.

### 22.4. Testing business behavior after configuration is valid

If the requirement is "the endpoint must work", also test interaction with a mock server or test environment:

- Requests are accepted using the expected protocol.
- Failures are handled cleanly when the endpoint returns errors.
- Timeouts and retries are actually applied.
- Sensitive data is never sent to hosts outside allowed scope.

These tests belong to **system behavior**, not the automatic responsibility of the Spring Boot Binder.

## 23. Finding root causes when configuration fails at startup

A diagnostic workflow:

```text
Application fails to start / misbehaves
             |
             v
1. Determine effective value
   - active profile?
   - default file / import / external config?
   - environment / JVM / CLI override?
             |
             v
2. Determine Binding status
   - key recognized properly?
   - converter handles target type?
             |
             v
3. Read Validation result
   - which field violated?
   - nested @Valid enabled?
   - default masking missing data?
             |
             v
4. Review business policy
   - cross-field? HTTPS? min <= max?
   - feature enabled or disabled?
             |
             v
5. Inspect operational state
   - DNS/TLS/network/credentials/remote service
             |
             v
Fix the true root cause instead of changing config blindly
```

Example reading the final value in development:

```java
@Bean
ApplicationRunner showEffectiveConfiguration(Environment env) {
    return args -> {
        System.out.println(
                "parallelism="
                + env.getProperty("app.delivery.parallelism"));
    };
}
```

This `@Bean` method **lives inside** a `@Configuration` or `@SpringBootApplication` class, not as a standalone Java file containing only a method.

When using Spring Boot Actuator, endpoints like `/actuator/configprops` and `/actuator/env` can inspect configuration, provided they are secured and configured with appropriate sensitive-data sanitization. Never expose these endpoints publicly just for debugging, and never print passwords, tokens, private keys, or connection strings containing secrets to logs.

### 23.1. Do not diagnose from a single file's value

Suppose `application.properties` has:

```properties
app.delivery.parallelism=4
```

yet the bean receives `8`. The cause may be completely valid: a profile or environment variable supplied a higher-precedence value. The Binder is doing its job properly.

Before changing the configuration class, find **the winning PropertySource**. Adjusting `@Min` or `@Max` to force a value without understanding the override source can mask environment misconfigurations.

### 23.2. Binder errors differ from validation errors

Do not label every property-related startup failure a "binding error" in the narrow sense. For example:

```text
parallelism=abc
    -> cannot convert to int

parallelism=0
    -> valid int, yet violates @Min(1)

endpoint=https://gateway.example.test
    -> URI and static validation may pass, yet remote may be unreachable
```

They happen near startup, yet their causes and fixes differ.

## 24. Common mistakes

| Misconception | Reality | Correct approach |
| --- | --- | --- |
| "Having a `@ConfigurationProperties` bean means config is valid" | The bean can hold nonsensical values | Define and enforce constraints |
| "Converting to `Duration` means valid timeout" | `Duration` can be 0 or negative | Check duration bounds |
| "Parsable URI means the service can be called" | A URI is only an address descriptor | Validate scheme, host; check connectivity separately |
| "`@NotNull` suffices for all strings" | Empty strings are non-null | Use `@NotBlank` |
| "`@NotEmpty` validates every element" | It only checks the collection is non-empty | Use `@Valid` and element constraints |
| "`@DefaultValue` fixes invalid configuration" | Only handles missing values during binding | Use validation for invalid values |
| "Parameterized constructor makes fields required" | Parameters can receive defaults or null | Declare required constraints |
| "Unknown fields always cause errors" | Default option ignores them | Consider strict schema intentionally |
| "Disabled features still require endpoints" | Depends on real rules | Conditional validation based on `enabled` |
| "`@Value` enforces business validation like the Binder" | No equivalent automatic structural validation layer | Create `@ConfigurationProperties` models |
| "Validation passing means downstream is healthy" | External service can be down or have TLS issues | Readiness and operational error handling |
| "Editing an env var updates the bean" | Running JVM does not auto-refresh | Restart or designed refresh mechanism |
| "Unit tests instantiating objects prove YAML binds" | Such tests bypass the Binder path | Add integration tests |
| "Having `@Validated` checks all nested objects" | Missing `@Valid` can skip nested validation | Place `@Valid` at the right levels |
| "Having defaults means requirements are clear" | Defaults can mask missing required values | Separate required vs optional |

## 25. Project configuration design conventions

A well-designed configuration group should have a clear "contract":

| Contract element | Question to answer |
| --- | --- |
| Key names | What are the prefix and canonical `kebab-case` names? |
| Data types | `int`, `Duration`, `URI`, `List`, `Map`, or nested records? |
| Defaults | Are defaults reasonable and safe? |
| Requiredness | When should a missing key trigger an error? |
| Value ranges | Min/max, positive, non-blank, non-empty list? |
| Cross-field rules | If a feature is enabled, which fields are needed? |
| Environment differences | Do some profiles require stricter policies? |
| External dependencies | Are there endpoints, DNS, certs, or credentials to verify? |
| Failure response | Fail-fast, not-ready, or controlled degradation? |
| Testing | Which conversion, validation, profile, and operational tests exist? |

Think of designing configuration as designing an **input interface for the application**, not merely jotting down keys in YAML.

Recommendations:

1. **Prefer `@ConfigurationProperties`** for structured configuration groups.
2. **Use appropriate Java types**, especially `Duration`, `DataSize`, `URI` instead of raw strings when converters exist.
3. **Enable validation deliberately** with `@Validated` and Jakarta Bean Validation.
4. **Place constraints at the right level:** field, collection element, nested object, and cross-field.
5. **Avoid using defaults to mask missing required values.**
6. **Separate static validation from external connectivity checks.**
7. **Clarify fail-fast vs graceful degradation** based on feature criticality.
8. **Evaluate unknown fields** if configuration requires a strict schema.
9. **Test the full path from configuration sources to Java models**, not only manually constructed objects.
10. **Never expose secrets in logs or public debug endpoints.**

## 26. Self-check exercises

### Exercise 1 — negative integer

```properties
app.worker.threads=-4
```

Record:

```java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int threads) {}
```

**Question:** Can the Binder construct the object? If the app needs at least one worker, is this safe enough?

**Answer:** `-4` is a valid `int`, so type conversion succeeds. Not safe enough. Add a constraint such as `@Min(1)` and enable validation.

### Exercise 2 — an unwanted duration

```properties
app.worker.timeout=-5s
```

**Question:** Why is `Duration timeout` not enough?

**Answer:** `Duration` can represent negative amounts. If timeout must be positive, add an explicit constraint or custom rule. Type conversion and business correctness are two separate checks.

### Exercise 3 — missing required field

```yaml
app:
  worker:
    enabled: true
```

Record:

```java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(boolean enabled, URI endpoint) {}
```

**Question:** Can you conclude the Binder automatically rejects this because `endpoint` is a constructor parameter?

**Answer:** No. Missing configuration can leave a reference parameter as `null`. If `endpoint` is required, use `@NotNull` or an appropriate cross-field condition and enable validation.

### Exercise 4 — two valid numbers with an invalid relationship

```properties
app.pool.min-size=10
app.pool.max-size=5
```

**Question:** If both fields only have `@Min(1)`, does the configuration satisfy business rules?

**Answer:** Not yet. Both individually are >= 1, yet `minSize > maxSize`. Cross-field validation is needed.

### Exercise 5 — empty targets

```yaml
app:
  delivery:
    targets: []
```

**Question:** Does `List<Target>` binding cleanly prove there is a destination to send messages to?

**Answer:** No. The list can be empty; use `@NotEmpty` and `@Valid` on elements if the feature requires at least one valid target.

### Exercise 6 — HTTPS does not prove readiness

```properties
app.delivery.endpoint=https://gateway.example.test
```

**Question:** The URI parsed and passed HTTPS policy, so is the system guaranteed to connect successfully?

**Answer:** No. DNS, TLS, network, authorization, and the external service can still fail. Separate operational checks with timeouts and proper error handling are required.

### Exercise 7 — defaults vs missing

```java
@DefaultValue("8") int parallelism
```

**Question:** If production requires `parallelism` to be explicitly provided by infrastructure, does default `8` satisfy that requirement?

**Answer:** No. Defaults provide values when absent, which can mask missing required configuration. Enforce the required policy for the corresponding environment.

### Exercise 8 — nested validation

A nested `Retry` has `@Min(0)`, yet the parent class only has `@Validated` without `@Valid` on the nested property. Can you assume child validation always runs completely?

**Answer:** No. Mark cascade validation properly, and ensure the nested object is present if required.

### Exercise 9 — configuration running in another environment

`application.yaml` sets `parallelism=4`, while argument `--app.delivery.parallelism=100` is passed at launch.

**Question:** If the bean has `@Max(16)`, what outcome should the application produce?

**Answer:** Under normal precedence, the command-line argument supplies effective value `100`; binding to `int` succeeds, yet validation can reject it for exceeding 16. Always inspect the final winning source, not only YAML.

### Exercise 10 — three kinds of testing

You have a unit test confirming `isEndpointPolicyValid()` returns `false` for HTTP URLs. Is that enough to prove Spring Boot reads environment variables properly?

**Answer:** No. Unit tests verify Java rules; binding/integration tests are needed to prove source loading and relaxed binding, and separate operational tests are needed if real connectivity is required.

## 27. Design checklist before introducing a configuration group

This is a checklist for design engineers, not an automatic guarantee from the Binder:

- [ ] Identify the property group and canonical prefix.
- [ ] Choose appropriate Java types for each value.
- [ ] Classify required values vs optional values.
- [ ] Specify defaults only when defaults are truly safe.
- [ ] Declare range, positive, not-blank, and size constraints as needed.
- [ ] Validate nested structures and collections with `@Valid`.
- [ ] Validate cross-field constraints.
- [ ] Define profile-specific conditions and feature-toggle behavior.
- [ ] Separate static checks from external system checks.
- [ ] Test unconvertible data, convertible-but-invalid data, and valid data.
- [ ] Verify final winning configuration sources during deployment.
- [ ] Never expose secrets in logs or public error messages.

Answering these questions forms the application's **configuration contract**. A strong contract helps operations distinguish configuration mistakes, application code bugs, and external dependency failures.

## 28. Summary

Remember three statements:

**First — Binding succeeded:** Spring Boot found matching values from sources, matched property names, and converted them to Java types per Binder capabilities. It does not automatically understand all business conditions.

**Second — Validation succeeded:** the constraints the application **declared and enabled** are satisfied. This is more valuable than binding alone, yet does not prove undeclared constraints hold.

**Third — Operations succeeded:** the system uses the configuration in real conditions, with external services, data, permissions, resources, and SLAs. That is a higher verification bar, typically requiring integration tests, readiness checks, and monitoring.

```text
"Right type"
    does not mean
"Follows business rules"
    does not mean
"Works in a live environment"
```

With Spring Boot 3.3, good practice is using `@ConfigurationProperties` for structured configuration, declaring validation via `@Validated` and Jakarta Bean Validation, adding cross-field rules where needed, and separating operational dependency checks. **Never treat successful bean creation as proof that configuration fully meets business requirements.**

## References

- Spring Boot 3.3 Reference — **Externalized Configuration**, sections *Type-safe Configuration Properties*, *Properties Conversion*, *@ConfigurationProperties Validation*, *Relaxed Binding*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 API — `ConfigurationProperties`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Boot 3.3 Reference — **Actuator Endpoints**: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Jakarta Validation specification — Bean Validation constraints and cascade validation: https://jakarta.ee/specifications/bean-validation/
