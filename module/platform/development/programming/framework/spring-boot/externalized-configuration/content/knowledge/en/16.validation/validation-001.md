# Why Configuration Validation Should Run at Startup

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Validation

## 1. Problem Statement: A Running Application Is Not Necessarily Ready to Serve

A Spring Boot application can compile successfully, package into a JAR successfully, and even open its HTTP port successfully, yet still contain **missing or invalid configuration**. For example:

- The payment gateway URL is left blank.
- The connection timeout is configured as a string that cannot be converted to `Duration`.
- The retry count is `0` while business policy requires at least one attempt.
- A partner property group is missing, but the code only accesses it when the first request arrives.
- An environment variable key has a typo, so the application silently falls back to an inappropriate default value.
- A required credential is not mounted in the container, yet the error only surfaces when the first transaction passes through that feature.

Without early validation, the system can enter a dangerous state: **the deployment reports success while part of its functionality is already broken**. The incident then escalates from a clear configuration error into timeouts, HTTP 500s, lost orders, corrupted data processing, or a difficult rollback during peak hours.

**Startup configuration validation** shifts statically detectable errors from the moment users start sending traffic back to the application initialization phase. This is a **fail-fast** principle: if required configuration is wrong, stop early and report the specific cause rather than continuing to run on unfounded assumptions.

In Spring Boot, the typical approach is to declare typed configuration with `@ConfigurationProperties`, then combine it with `@Validated`, Bean Validation, Binder type conversion, and business rule checks where needed.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the cost and risk of detecting configuration errors too late.
2. Distinguish between **missing values**, **type mismatches**, **constraint violations**, and **unmet runtime environment conditions**.
3. Design a typed configuration Java record, enable validation, and register the bean properly.
4. Apply `@NotBlank`, `@NotNull`, `@Min`, `@Max`, `@NotEmpty`, `@Valid`, and `@Validated` according to their exact semantics.
5. Identify defaults, primitive fields, nested objects, and configuration sources that can mask missing data.
6. Write tests verifying that the application refuses to start with invalid configuration.
7. Distinguish between **startup validation**, **readiness/health checks**, and monitoring of running dependencies.
8. Avoid leaking secrets in logs and validation error messages.

## 2. Why Is Startup Validation Better Than Request-Time Validation?

### 2.1. Errors Surface in One Observable Place

If a configuration bean is validated while building the `ApplicationContext`, the application can fail to start and record information about the invalid key. Deployment tooling can detect that the process exited, the container is not ready, or the rollout is not progressing.

Conversely, if left until the first request:

~~~java
@Service
public class OrderService {

    private final Environment environment;

    public OrderService(Environment environment) {
        this.environment = environment;
    }

    public String paymentEndpoint() {
        // If not configured, the value may be null.
        return environment.getProperty("payment.gateway.endpoint");
    }
}
~~~

then the error is only exposed when a business branch calls `paymentEndpoint()` and actually uses the value. The application may have already served significant traffic on other routes, creating a false sense of a successful deployment.

Validating at startup ensures errors are caught **before business processing paths depend on them**.

### 2.2. Reducing Ambiguity During Diagnosis

A binding error such as:

~~~text
Failed to bind properties under 'orders.client.retry.max-attempts'
~~~

is usually far more direct than a `NullPointerException` or a context-poor remote call failure appearing later. The actual exception names and message structure depend on the Spring Boot version, but the goal is to pinpoint the relevant **prefix**, **property**, **data type**, or **constraint**.

For example, when code encounters an HTTP timeout, the cause could be the network, DNS, an external service, or a timeout configured too short. If the timeout value is validated and constrained at startup, you have at least eliminated an entire class of invalid configuration causes.

### 2.3. Avoiding Unintended Partially Working States

A service might expose REST endpoints, send emails, process events, and run batch jobs. If email credentials are missing and only affect notification delivery, the application could process orders successfully while failing to send mandatory notifications.

When email is an essential part of the system, a missing credential should be a startup failure or a readiness failure according to a defined policy. When email is only an optional feature, the system may allow startup but should **explicitly disable the feature** in an observable way; it should not silently continue with a null configuration object.

### 2.4. Providing a Solid Basis for Rollback and Operations

In a deployment using Kubernetes or another orchestration platform, failing fast helps the rollout loop detect that a new container cannot run with the supplied configuration. Operations teams can inspect the configuration reason, restore the manifest/secret, or roll back to the previous release.

This does not guarantee a safe rollout by itself: restart policies, liveness/readiness probes, rollout strategies, and platform recovery capabilities must still be designed properly. However, refusing startup on invalid required configuration is usually a **more accurate** signal than keeping a broken process alive waiting for traffic.

## 3. Four Distinct Validation Layers

Not every kind of "problematic configuration" should be lumped into a single problem.

| Layer | Example | Common Mechanism |
| --- | --- | --- |
| **Presence** | Missing `orders.client.base-url` | `@NotNull`, `@NotBlank`, required binding contract |
| **Type conversion** | `orders.client.timeout=fast` when the field is `Duration` | Spring Boot Binder and converters |
| **Value constraints** | `retry.max-attempts=0` when at least 1 is required | Jakarta Bean Validation or custom validator |
| **Infrastructure readiness** | Well-formed URL, but the partner is unreachable | Health/readiness checks, policy-based connectivity checks |

The first three layers are where **startup validation** excels. The last layer depends on external system state, which can change immediately after the application starts. It requires runtime observability and resilience mechanisms.

### 3.1. A Missing Property Is Not the Same as a Type Mismatch

With the record:

~~~java
public record RetryProperties(int maxAttempts) {}
~~~

if `max-attempts` is absent, the primitive `int` can receive the default value `0` when the object is instantiated. That is **not proof** that the operator intentionally configured `0`.

If the value must be at least 1, `@Min(1)` will catch `0`. If you need to distinguish **absent** from **explicitly configured as 0**, consider using `Integer` with `@NotNull` and `@Min(1)`.

### 3.2. Invalid Format Is Not the Same as Invalid Business Rule

For example, `connect-timeout=not-a-duration` can fail when converting to `Duration`. Meanwhile, `connect-timeout=0ms` converts cleanly yet fails to satisfy the application's requirement for a positive timeout.

The Binder handles **type conversion**; validation or business checks handle **the semantic validity of the value**.

### 3.3. A URL Can Be Syntactically Valid Yet Unreachable

`https://partner.example.test` may be a valid URI, yet the remote service might not exist, DNS could be misconfigured, or a firewall could block it. `@NotNull URI` only guarantees the field is present and accepted by conversion; it **does not guarantee the endpoint works**.

For required dependencies, you can add readiness/health checks or early connectivity checks with appropriate timeouts. However, avoid hard-locking the entire application simply because an optional dependency is temporarily unavailable.

## 4. Typed Configuration as the Foundation for Early Validation

### 4.1. Example YAML File

An order-processing application needs an HTTP client to call a partner. In `src/main/resources/application.yml`:

~~~yaml
orders:
  client:
    base-url: "https://orders.partner.example"
    connect-timeout: 2s
    request-timeout: 5s
    enabled: true
    allowed-regions:
      - "apac"
      - "eu"
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

We want a configuration contract:

- `base-url` is required.
- `connect-timeout` and `request-timeout` are required and must have sensible values.
- `retry.max-attempts` is at least 1 and does not exceed operational limits.
- `retry.backoff` is required when retry is configured.
- `allowed-regions` must have at least one non-blank element.
- `enabled` is an intentional decision: if explicit declaration is desired, `Boolean` differs from primitive `boolean`.

### 4.2. Using `@ConfigurationProperties` with a Record

Example for Spring Boot 3.x and Java 17+:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "orders.client")
@Validated
public record OrderClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @NotNull Boolean enabled,
        @NotEmpty List<@NotBlank String> allowedRegions,
        @Valid @NotNull Retry retry
) {
    public record Retry(
            @Min(1) @Max(10) int maxAttempts,
            @NotNull Duration backoff
    ) {}
}
~~~

How each part works:

- `@ConfigurationProperties(prefix = "orders.client")` instructs the Binder to read keys under the `orders.client.*` group.
- `@Validated` enables validation of the bean properties when an appropriate validator mechanism is present.
- `@NotNull` on reference fields prevents a required value from being omitted.
- `@NotEmpty` on the list requires at least one element; `@NotBlank` on list elements requires each region not to consist solely of whitespace when container-element validation is supported.
- `@Min(1)` and `@Max(10)` constrain the allowed range for attempt count.
- `@Valid` on the nested `Retry` requests cascaded validation into its inner constraints.
- `@NotNull` on `Retry retry` handles the case where the entire nested group is missing.

With a concrete class, there is no need to scatter rules across YAML or inside services. The configuration contract is expressed cohesively in a Java type.

### 4.3. Adding the Bean Validation Dependency

In a Spring Boot application using Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

In Spring Boot 3, Bean Validation constraints normally live in `jakarta.validation.constraints`; `@Valid` lives in `jakarta.validation`.

Annotations alone do not constitute a complete validation setup. A matching validation provider implementation and integration must be present for them to actually be evaluated.

### 4.4. Registering the Properties Bean

Application class:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Or register explicitly with:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(OrderClientProperties.class)
class OrderClientConfiguration {}
~~~

Use an appropriate registration mechanism. With constructor-bound records, do not simply put `@Component` on the record expecting Spring to automatically interpret every constructor parameter as configuration properties; those are two different bean instantiation models.

When Spring Boot binds and validates this bean during context creation, required failures can prevent the application from **starting up successfully**.

### 4.5. Services Only Receive Already-Bound Configuration

~~~java
package com.example.orders.service;

import com.example.orders.config.OrderClientProperties;
import org.springframework.stereotype.Service;

@Service
public class OrderClientService {

    private final OrderClientProperties properties;

    public OrderClientService(OrderClientProperties properties) {
        this.properties = properties;
    }

    public int retryLimit() {
        return properties.retry().maxAttempts();
    }
}
~~~

The service reads typed values that have already been created and validated. There is no need to look up the `retry.max-attempts` string and parse it manually on every request.

This does not exempt the service from all runtime checks. An endpoint can lose connectivity after startup, or user-supplied payloads may be invalid; those cases must be handled in their respective layers.

## 5. Outcomes with Valid and Invalid Configurations

Consider the record from the previous section, assuming configuration sources are not unexpectedly overridden.

| Scenario | Example | Expected Behavior |
| --- | --- | --- |
| Fully valid | `max-attempts: 3`, valid timeouts | Binder and validation succeed |
| Missing `base-url` | Property absent from all sources | `@NotNull` detects missing value |
| Invalid timeout type | `connect-timeout: abc` | Conversion error to `Duration` |
| Retry equals 0 | `max-attempts: 0` | `@Min(1)` fails |
| Retry too large | `max-attempts: 99` | `@Max(10)` fails |
| Missing `allowed-regions` | List missing or empty | `@NotEmpty` fails |
| List contains blank string | `allowed-regions: [""]` | Element `@NotBlank` can detect it |
| Entire `retry` missing | No `orders.client.retry.*` keys | `@NotNull` on nested object detects it |
| Missing `retry.backoff` | Only `max-attempts` provided | `@NotNull` on nested field can detect it with `@Valid` |
| Valid URL but unresponsive host | Valid `base-url` | Startup config validation alone does not verify connectivity |

In actual error reports, you may see details such as `Failed to bind properties`, `BindException`, `BindValidationException`, or a wrapping bean creation exception. Do not write monitoring against a single exact English exception sentence; messages can vary across Spring Boot versions and Bean Validation providers.

## 6. Type Checking Does Not Replace Business Constraints

Spring Boot's Binder converts many text values into target types, such as:

~~~yaml
service:
  client:
    timeout: 3s
  upload:
    max-size: 10MB
~~~

Which can bind to:

~~~java
import java.time.Duration;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        Client client,
        Upload upload
) {
    public record Client(Duration timeout) {}
    public record Upload(DataSize maxSize) {}
}
~~~

If `timeout` is `not-a-duration`, the Binder can report a conversion error. But if a user enters `0s`, conversion succeeds even though business rules prohibit a zero timeout.

### 6.1. Constraining Duration to Be Greater Than Zero

One approach is to use a custom business check rather than relying solely on `@NotNull`:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "sample.http")
public record HttpPolicy(Duration timeout) {

    public HttpPolicy {
        if (timeout == null ||
                timeout.isZero() ||
                timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "sample.http.timeout must be greater than 0");
        }
    }
}
~~~

With a record compact constructor, the check runs when the object is instantiated. This is a clear **way to enforce invariants**, though the surfaced error may be wrapped in a binding/bean-creation exception and may not provide full constraint metadata like Bean Validation. For multiple validation rules, you can choose a custom Jakarta constraint or a dedicated validator.

Do not log sensitive values directly in exceptions. For non-sensitive timeouts or counts, you can include the key name and validity requirement in the message.

### 6.2. Cross-Field Relationships

Suppose a configuration contains:

~~~yaml
network:
  connect-timeout: 2s
  request-timeout: 5s
~~~

Each value may be valid individually, but policy requires `request-timeout >= connect-timeout`. Single-field constraints like `@NotNull` cannot verify this relationship on their own.

A record can enforce an invariant:

~~~java
@ConfigurationProperties(prefix = "network")
public record NetworkProperties(
        Duration connectTimeout,
        Duration requestTimeout
) {
    public NetworkProperties {
        if (connectTimeout == null ||
                requestTimeout == null ||
                connectTimeout.isNegative() ||
                requestTimeout.compareTo(connectTimeout) < 0) {
            throw new IllegalArgumentException(
                    "network.request-timeout must be >= connect-timeout");
        }
    }
}
~~~

In larger applications, if multiple cross-field rules become complex, consider class-level constraints or a custom `Validator` to centralize logic and provide clear error messages.

### 6.3. Scope of Validation

Startup validation is best suited for conditions that can be decided **based on the available configuration**, without requiring live transactions or repeated network calls.

Examples: `timeout > 0`, `retries >= 1`, non-empty URL, environment name in an allowed set, non-conflicting feature flags. These checks do not need to wait for a user request.

## 7. Nested Objects: Missing an Entire Group Also Needs a Policy

With the record:

~~~java
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(Gateway gateway) {
    public record Gateway(String endpoint, String token) {}
}
~~~

If no `payments.gateway.*` properties are present, the `gateway` field can be `null` under constructor binding. Placing `@Valid` alone only tells validation to descend into the object **when the object exists**; it does not force the object to be present.

If `gateway` is required:

~~~java
@ConfigurationProperties(prefix = "payments")
@Validated
public record PaymentProperties(
        @Valid @NotNull Gateway gateway
) {
    public record Gateway(
            @NotBlank String endpoint,
            @NotBlank String token
    ) {}
}
~~~

Combined:

- `@NotNull`: the gateway group cannot be completely absent.
- `@Valid`: continues checking the inner fields.
- `@NotBlank`: forbids empty or whitespace-only endpoint/token strings.

### 7.1. Empty `@DefaultValue` and Why It Needs Care

Spring Boot supports constructor binding instantiating a nested object when the entire group is absent using an empty `@DefaultValue`:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "scheduler")
public record SchedulerProperties(
        @DefaultValue Policy policy
) {
    public record Policy(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("500ms") Duration delay
    ) {}
}
~~~

This is reasonable when the scheduler policy group is **optional and has safe defaults**. It reduces the need for null checks in code.

However, if you use an empty `@DefaultValue` for a group containing required credentials, the nested object may still be created with null fields. That does not replace validation; in fact, it can obscure the fact that the deployment failed to supply the config group at all.

### 7.2. Optional Features Should Be Modeled Explicitly

For example, an SMS-sending feature is optional:

~~~yaml
notifications:
  sms:
    enabled: false
~~~

A possible design:

~~~java
@ConfigurationProperties(prefix = "notifications.sms")
@Validated
public record SmsProperties(
        boolean enabled,
        String endpoint,
        String apiKey
) {}
~~~

If `enabled=false`, the endpoint may be omitted; if `enabled=true`, `endpoint` and `apiKey` must be present. This rule requires **cross-field validation** or corresponding conditional configuration logic, not unconditional `@NotBlank` on both fields.

The key is that startup reflects the policy: **when a feature is enabled, its configuration is required**; when disabled, it can be skipped. Do not blindly validate every property such that an optional integration always prevents the application from starting.

## 8. Defaults: Convenient but Can Hide Missing Configuration

A property with a default can make local development easier to run:

~~~yaml
orders:
  client:
    connect-timeout: 3s
    retry:
      max-attempts: 3
~~~

However, if a value only makes sense when **explicitly supplied in production**, a default can allow a forgotten environment variable to go unnoticed.

### 8.1. Truly Safe Defaults

A default value is usually appropriate when it satisfies business policy across all environments the application supports, such as a reasonable demo timeout or a feature flag defaulting to off.

However, do not create defaults for:

- Token-signing secrets or production passwords.
- Environment-specific bank or partner URLs.
- Tenant IDs or data namespaces that must point to the right target.
- Persistent encryption keys.
- Values that must be identical across all instances rather than generated independently at startup.

A wrong default can be worse than a startup failure because the system keeps running with incorrect behavior.

### 8.2. Primitive Defaults and `@NotNull`

With:

~~~java
public record PoolProperties(int size) {}
~~~

`int` is a primitive and cannot be null, so `@NotNull` on it will not detect a missing property. Use `@Min(1)` if a size of at least 1 is required, or use `Integer` + `@NotNull` when you need to distinguish absence from `0`.

Example:

~~~java
@ConfigurationProperties(prefix = "pool")
@Validated
public record PoolProperties(
        @NotNull @Min(1) Integer size
) {}
~~~

In this setup, both an omitted `pool.size` and `pool.size=0` are treated as invalid, though they can produce different constraint violations.

### 8.3. Defaults on Constructor-Bound Fields

Spring Boot supports `@DefaultValue`:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "reports")
public record ReportsProperties(
        @DefaultValue("10s") Duration timeout,
        @DefaultValue("false") boolean enabled
) {}
~~~

`@DefaultValue` serves the case where no corresponding property is present. It does not mean "ignore any provided value that has the wrong type." If a deployment sets `reports.timeout=invalid`, the Binder can report an error rather than falling back to `10s`.

### 8.4. Avoid Silent Fallbacks for Required Config

In code:

~~~java
String url = environment.getProperty(
        "payment.endpoint",
        "https://sandbox.example.test");
~~~

if production forgets to provide the endpoint, the application could call the sandbox instead of failing. For a real payment system, such a default could cause data corruption or transactions in the wrong environment.

For required configuration, a clearer choice is a validated `@ConfigurationProperties` model with **no unsafe fallback**. For optional configuration, fallbacks should be intentionally designed.

## 9. Property Source Precedence: Values Can Change Outside YAML

`@ConfigurationProperties` binds from `Environment`, not by reading a single file in isolation. Therefore, inspecting one YAML file and concluding "the configuration is valid" can be wrong if a higher-precedence source overrides the key.

For example, `application.yml`:

~~~yaml
orders:
  client:
    retry:
      max-attempts: 3
~~~

But at runtime:

~~~bash
java -jar orders.jar \
  --orders.client.retry.max-attempts=0
~~~

command-line properties usually have higher precedence than config data. The Binder receives `0`, and `@Min(1)` will reject it if the properties class is properly registered and validated.

Similarly, sources can include:

| Source | Example |
| --- | --- |
| Config data inside the JAR | `classpath:/application.yml` |
| Profile-specific files | `application-prod.yml` |
| Externalized files outside the JAR | `./config/application.yml` |
| Config data imports | `spring.config.import` |
| OS environment | `ORDERS_CLIENT_RETRY_MAXATTEMPTS=5` |
| Java system properties | `-Dorders.client.retry.max-attempts=5` |
| JSON application properties | `SPRING_APPLICATION_JSON` |
| Command line | `--orders.client.retry.max-attempts=5` |
| Test property sources | `@SpringBootTest(properties = ...)` |

Which source wins depends on precedence and can be altered by custom configuration, test infrastructure, or disabling command-line properties.

**Startup validation must inspect the object built by the Binder from effective sources**, rather than merely linting a static YAML file.

### 9.1. Profile-Specific Configuration

Suppose:

~~~yaml
# application.yml
service:
  enabled: false
  endpoint: ""
~~~

~~~yaml
# application-prod.yml
service:
  enabled: true
  endpoint: "https://prod.example.test"
~~~

If the `prod` profile is active, the bean can bind from the profile-specific values; if the profile is inactive or the file is not found, other values apply. A validator that depends on `enabled` helps ensure the system cannot start in an "enabled with blank endpoint" state.

Also distinguish profile-specific files from documents activated via `spring.config.activate.on-profile` inside a multi-document file. Activation conditions determine which documents participate in configuration sources before precedence is applied.

### 9.2. Misspelled or Extraneous Key Names

If code expects `orders.client.retry.max-attempts`, but an operator writes:

~~~properties
orders.client.retry.max-atempt=5
~~~

then `max-atempt` is a different key and may be ignored during binding because many `@ConfigurationProperties` classes allow unknown fields by default. The required field may remain missing or take a default, so the typo is not necessarily caught.

You can consider strict unknown-field handling appropriate to your Spring Boot version:

~~~java
@ConfigurationProperties(
        prefix = "orders.client",
        ignoreUnknownFields = false
)
public record StrictClientProperties(
        String baseUrl
) {}
~~~

However, strict binding must be designed alongside your property structure and real environments; in setups with nested or optional keys under a shared prefix, test carefully to avoid rejecting legitimate keys. More importantly, **validation requiring mandatory fields** provides a direct safeguard when a typo drops a needed property.

### 9.3. Do Not Assume Environment Variable Names Are Automatically Safe

Relaxed binding lets environment variable names map to Java property names, for example:

~~~text
orders.client.retry.max-attempts
ORDERS_CLIENT_RETRY_MAXATTEMPTS
~~~

If CI/CD uses a name that violates the conversion rules, the application may fail to pick up the value. Document canonical variable names clearly and test a production-like deployment in a staging/integration environment.

## 10. Validate Early Without Turning Startup Into an Infinite Network Loop

An important boundary: **configuration validation** is distinct from **external resource verification**.

### 10.1. Intrinsic Checks: Do These Early

Questions answerable solely from property values:

- Is `endpoint` provided?
- Is `timeout` in a valid format?
- Is `max-attempts` within `[1,10]`?
- Is `mode` a valid enum value?
- If `feature.enabled=true`, is `feature.credentials` complete?
- If `tls.enabled=true`, are certificate/key paths provided?

These are ideal checks for the binding/validation phase or bean initialization.

### 10.2. Extrinsic Checks: Classify Dependencies Carefully

Questions that depend on the runtime environment:

- Does the endpoint's DNS resolve **right now**?
- Does the database respond to a health query?
- Is the remote API currently rate-limiting requests?
- Does the mounted certificate exist and remain unexpired?
- Have permissions been granted on the queue/topic?

Some checks may be appropriate at startup or readiness if the dependency is critical. However, making repeated network calls without timeouts or retrying indefinitely inside a `@ConfigurationProperties` constructor can hang startup, increase cascading failure risk, or hinder self-recovery.

**Principle:** catch static errors as early as possible; for dynamic dependencies, combine timeouts, retry policies, readiness/health probes, and operational observability.

### 10.3. Liveness vs. Readiness

In an orchestrated environment:

- **Liveness** roughly answers whether the process is still healthy enough to run or needs a restart.
- **Readiness** answers whether the instance is ready to receive traffic.
- **Startup probe** (when supported by the platform) gives the startup phase adequate time before liveness checks begin.

Do not let a temporarily unreachable external dependency cause liveness to fail repeatedly and trigger a restart loop if the process can recover without restarting. Conversely, a dependency required for every request can be reflected in readiness according to operational policy.

Configuration validation and readiness complement each other: one prevents running with **invalid configuration data**, while the other evaluates **current ability to serve**.

## 11. When to Fail Startup vs. When to Degrade Gracefully

Not every property is mandatory. A system can have multiple tiers:

| Scenario | Recommended Strategy |
| --- | --- |
| Missing database URL for core persistence service | Fail fast when required configuration is missing |
| Critical token-signing secret is missing | Fail fast; never generate a temporary secret on each startup |
| Optional email integration is disabled | Allow missing SMTP settings; log disabled state clearly |
| Optional email integration is enabled without credentials | Fail fast or block only that feature per policy |
| Negative timeout or nonsensical retry count | Fail fast via binding/validation |
| External service temporarily down, with retry/degraded mode | Readiness or controlled degradation |
| Feature flag not supplied | Use a safe, clearly defined default |
| Secret volume not mounted | Fail fast if the secret is required; re-check deployment/volume |
| Cache unreachable when system can run without cache | Design bounded fallback with observability |
| Malformed configuration file | Fail startup with a clear message |

The design principle is **setting policy based on criticality**. "Fail fast" does not mean "any missing optional config kills the whole system." It means the system **never hides an error that puts its current state in violation of its published operating contract**.

## 12. Investing in Startup Error Messages

Validation is effective when operators can understand and fix the error quickly.

A good message states:

1. **Property name**: `orders.client.retry.max-attempts`.
2. **Requirement**: must be between 1 and 10.
3. **Context source**: the `orders.client` group, along with origin metadata if available.
4. **Remediation action**: update the appropriate file/profile/env var/CLI flag.
5. **No leaked secrets**: never print passwords, tokens, or private keys.

Example message for a business check:

~~~text
Configuration invalid:
orders.client.retry.max-attempts must be between 1 and 10.
Review the effective value from active config sources.
~~~

Do not assume Spring Boot always prints this exact wording. This is a **desired phrasing pattern**, not a verbatim transcript of a specific stack trace.

### 12.1. Messages Must Not Reveal Secrets

A config class containing a token:

~~~java
@ConfigurationProperties(prefix = "payments.credentials")
public record CredentialsProperties(String apiKey) {}
~~~

A record has an auto-generated `toString()` that can include its fields. Therefore, do not log the entire configuration object for diagnostics, nor construct exceptions containing the `apiKey` value.

When reporting errors, prefer:

~~~text
payments.credentials.api-key must be configured
~~~

over:

~~~text
payments.credentials.api-key has invalid value: <actual secret>
~~~

Similarly, protect Actuator `env` and `configprops` endpoints, controlling access permissions and sensitive-value masking.

### 12.2. Where Did the Error Come From?

In Spring Boot, config data origin metadata can help identify which file or location a value came from. When investigating, inspect origin/`PropertySource` through controlled diagnostics instead of dumping the entire configuration.

Some property sources do not carry full origin metadata or represent it differently across versions, so diagnostic tooling should handle missing origins gracefully. Startup errors will not always point to a single file when multiple sources are merged.

## 13. Testing Startup Validation with `ApplicationContextRunner`

With a registered properties class and Bean Validation on the classpath, you can use `ApplicationContextRunner` to verify that the context starts or fails as expected.

### 13.1. Setting Up the Test Context

Example using JUnit 5, AssertJ, and Spring Boot Test:

~~~java
package com.example.orders.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class OrderClientPropertiesValidationTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(OrderClientProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ValidationAutoConfiguration.class))
                    .withUserConfiguration(TestConfig.class)
                    .withPropertyValues(
                            "orders.client.base-url=https://api.example.test",
                            "orders.client.connect-timeout=2s",
                            "orders.client.request-timeout=5s",
                            "orders.client.enabled=true",
                            "orders.client.allowed-regions[0]=apac",
                            "orders.client.retry.max-attempts=3",
                            "orders.client.retry.backoff=250ms"
                    );

    @Test
    void validConfigurationStarts() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getBean(OrderClientProperties.class)
                    .retry().maxAttempts()).isEqualTo(3);
        });
    }

    @Test
    void invalidRetryCountPreventsStartup() {
        runner.withPropertyValues(
                "orders.client.retry.max-attempts=0"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }
}
~~~

Here:

- `ApplicationContextRunner` builds a lightweight Spring context.
- `@EnableConfigurationProperties` registers the bean under test.
- `ValidationAutoConfiguration` enables test validation infrastructure when the validation dependency is present.
- Baseline test values are supplied via `withPropertyValues`.
- The failure case overrides only `max-attempts=0` to verify that the context fails to start.

There is no need to assert on an exact exception class name or the entire rendered error string, as messages can differ across versions.

### 13.2. Essential Test Cases

| Case | Property Changed | What to Verify |
| --- | --- | --- |
| Happy path | All valid values | Context starts successfully |
| Missing required | Omit `base-url` in test config | Context fails due to missing value |
| Wrong type | `connect-timeout=abc` | Context fails during binding |
| Constraint violation | `max-attempts=0` | Context fails during validation |
| Out of bounds | `max-attempts=100` | `@Max(10)` is enforced |
| Missing nested group | Do not provide `retry.*` | `@NotNull` protects the group |
| Missing nested field | Provide attempts, omit backoff | `@Valid` + `@NotNull` protects the field |
| Empty list | Missing regions or empty list | `@NotEmpty` is enforced |
| Invalid list element | Region is a blank string | Element constraint is enforced |
| Source override | Higher-precedence source has 0 | Validation inspects final bound value |

When constructing each test case, remove or replace baseline properties properly. Simply calling `withPropertyValues` to add another property does **not** remove unrelated properties already configured on the runner. For a "completely missing property" test, create a separate runner that omits that property from the start.

### 13.3. Do Not Only Test Annotation Presence

A reflection test asserting that `@NotNull` is present on a field only checks **code metadata**; it does not prove the framework registered the bean, loaded sources, bound properties, and ran the validator properly.

Actual context tests catch common integration mistakes:

- Scanning or `@EnableConfigurationProperties` not enabled.
- Missing validation dependency.
- `@Valid` not cascading as expected.
- Wrong prefix relative to deployment configuration.
- A default accidentally masking missing config.

### 13.4. Integration Testing in a Production-Like Profile

Alongside unit/context tests, you can run an integration or smoke test with production-like configuration **without real secrets**:

~~~bash
java -jar orders.jar \
  --spring.profiles.active=staging \
  --orders.client.retry.max-attempts=0
~~~

If validation requires at least 1, startup should fail. Do not run such intentionally broken configuration against live user-serving production. The goal is to verify that the packaged artifact and externalized configuration wiring work together in a test environment.

## 14. Validation and the Spring Boot Startup Lifecycle

To understand why startup validation is effective, distinguish the high-level phases:

~~~text
Read command-line / environment / config data
                     |
                     v
       Prepare Spring Environment
                     |
                     v
         Initialize ApplicationContext
                     |
                     v
   Register and instantiate configuration-properties beans
                     |
                     v
        Binder converts types and binds data
                     |
                     v
          Run validation if enabled
                     |
          valid? ----+---- no ---> startup failure
             |
            yes
             v
     Dependent beans receive typed config
             |
             v
       Application continues startup
~~~

This is a mental model, not an exact diagram of every framework hook or extension. Spring Boot has many phases, and certain beans can be instantiated in different orders depending on configuration. However, for configuration beans registered and bound during context initialization, a binding or validation failure can halt startup.

### 14.1. Configuration Must Be Checked at the Right Time

If a properties class is only created lazily very late, or configuration is queried directly at runtime instead of bound at startup, you cannot assume all errors will be caught right when the application launches.

To fail fast on required configuration, ensure the configuration bean is registered and initialized on the normal startup path—do not hide property lookups inside a rarely executed request branch.

### 14.2. Validation Does Not Magically Re-Run After Startup

`@ConfigurationProperties` beans are typically bound when created, and data inside a singleton bean does not automatically update simply because a config file, ConfigMap, or Kubernetes Secret is edited in the infrastructure. If you use a refresh/rebind mechanism, determine when validation re-runs and how invalid new values are handled.

Startup validation catches errors **for that specific startup**, and does not replace lifecycle configuration update and protection policies.

## 15. Kubernetes and Containers: Catching Misconfiguration Before Serving Traffic

In containerized environments, configuration can be supplied via env vars, ConfigMaps, Secrets, or mounted volume files. Just because an image runs fine on a developer's laptop does not prove those keys exist in the pod.

Consider a hypothetical deployment providing:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      containers:
        - name: app
          image: example/orders-service:1.0
          env:
            - name: ORDERS_CLIENT_BASEURL
              value: "https://orders.partner.example"
            - name: ORDERS_CLIENT_RETRY_MAXATTEMPTS
              value: "0"
~~~

If `orders.client.retry.max-attempts` binds to `0` and has `@Min(1)`, the application can fail during context initialization. Kubernetes then observes that the container is not behaving as expected; it does not automatically fix the bad value or automatically roll back.

### 15.1. Integrating Configuration Errors Into the Release Pipeline

A deployment pipeline can:

1. Validate Helm/chart/manifest syntax.
2. Verify that required variables and Secret references exist.
3. Start the application version in a staging/test environment.
4. Observe whether binding and validation succeed.
5. Roll out using a strategy with readiness checks and error monitoring.
6. If the new version fails to become ready, investigate the configuration and roll back per policy.

Startup validation adds **application-level configuration contracts** on top of manifest checks. It catches conditions only the JVM/Binder can fully evaluate, such as converting `250ms` to `Duration` or nested constraints.

### 15.2. Look Beyond Process Status Alone

A process can be running yet not ready; an application can bind configuration successfully yet be unable to reach the DB. Monitoring should clearly distinguish these states:

- **Startup failed**: invalid required configuration or initialization failure.
- **Started but not ready**: the process started, but a current serving prerequisite is unmet.
- **Ready but degraded**: an optional feature is intentionally limited by design.
- **Healthy and ready**: satisfies all operational conditions defined by the system.

Do not collapse everything into a single boolean if the system has multiple dependencies and different recovery policies.

## 16. Catching Profile- and Environment-Specific Misconfiguration

For example, development has:

~~~yaml
# application-dev.yml
mail:
  enabled: false
~~~

Production has:

~~~yaml
# application-prod.yml
mail:
  enabled: true
  smtp:
    host: "smtp.internal"
    port: 587
~~~

An application can start fine in dev because email is disabled. When prod enables email, `smtp.host`, `smtp.port`, and the corresponding credentials must also be validated. If you only test dev, production errors stay hidden.

### 16.1. Designing Validation Around Feature State

A class can model:

~~~java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        boolean enabled,
        Smtp smtp
) {
    public record Smtp(String host, Integer port) {}
}
~~~

Constraints to express:

- If `enabled=false`: `smtp` may be absent if mail is optional.
- If `enabled=true`: `smtp` must be present, `host` non-blank, and `port` valid.
- Specific SMTP secrets are only required when authentication is actually used per policy.

This is **conditional validation**. It can be implemented with a class-level constraint or explicit validator/service initialization logic, rather than placing unconditional `@NotNull` on every field and breaking optional dev setups.

### 16.2. Verifying the Final Profile State

`spring.profiles.active` can come from the CLI or other sources; a `spring.config.activate.on-profile` document only contributes keys when its condition matches. Therefore, startup validation must execute after effective documents have been resolved.

When a property appears "missing," inspect active profiles, imported configs, working directory, external config locations, and higher-precedence sources. A file existing on disk does not by itself prove Spring Boot loaded it.

## 17. Do Not Confuse Startup Validation with `@Valid` on Requests

In web applications, `@Valid` is commonly used on request DTOs:

~~~java
public record CreateOrderRequest(
        @NotBlank String customerId,
        @Min(1) int quantity
) {}
~~~

~~~java
@PostMapping("/orders")
public void create(@Valid @RequestBody CreateOrderRequest request) {
    // Process request.
}
~~~

This validates **runtime user-submitted data** when a request arrives. It is essential, yet it does nothing to verify that `orders.client.base-url` or `retry.max-attempts` was configured properly.

By contrast, `@Validated` on `@ConfigurationProperties` targets **configuration beans** bound during initialization. Both use Jakarta Bean Validation, yet their **timing and validation targets differ**.

A sound system typically needs both: startup validation for application configuration, request validation for user input, and domain invariants for business logic.

## 18. Systematic Startup Error Diagnosis

When an application fails to start due to binding or validation, inspect in order:

1. **Configuration bean registration:** does the class have `@ConfigurationProperties`? Is it scanned/enabled?
2. **Prefix:** does code use `orders.client` while the file wrote `order.client`?
3. **Files and locations:** correct `application.yml`, profile-specific file, external file outside JAR, or `spring.config.import`?
4. **Precedence:** did an environment variable, Java system property, JSON, or CLI flag override a valid value with an invalid one?
5. **Target types:** do `Duration`, `URI`, `DataSize`, `int`, enums, and lists/maps have matching conversion support?
6. **Missing values:** are required fields supplied? Are primitives silently defaulting to `0`/`false`?
7. **Nested fields:** is an entire child group absent? Are `@Valid` cascade and parent `@NotNull` present?
8. **Defaults:** is an unsafe default masking a missing environment setting?
9. **Validator dependency:** are a Bean Validation implementation, `@Validated`, and proper wiring present?
10. **Error messages:** do they include enough key and constraint info to fix without risking secret exposure?
11. **External connectivity:** if config is valid yet the service is still not ready, check actual health/DNS/network/credentials per operational policy.
12. **Reproducible tests:** use a context test with deterministic configuration sources rather than relying on a developer's local machine.

### 18.1. Common Pitfalls

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| Startup succeeds despite missing secret | Field lacks constraint or has unsafe default | Add required validation, remove bad fallback |
| Error appears only on first request | Property lookup or client init happens too late | Bind and validate at startup, separate runtime logic |
| Config bean cannot be injected | Properties class not registered | `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Value fails to bind | Wrong type or format | Fix source value, use explicit units |
| `@NotNull` misses absent primitive number | Primitives cannot be null and may default to 0 | `@Min` or `Integer` wrapper with `@NotNull` |
| Nested field not validated | Missing `@Valid` or Bean Validation provider | Add cascade and validator dependency |
| Map/list contains invalid entry | Collection binding and overrides have specific semantics | Check precedence, key names, element validation |
| Config works in dev, fails in prod | Different active profile or imports | Test with a production-like profile |
| Test does not fail as expected | Test properties still supply a default | Build context omitting the required key |
| Overridden by CLI | CLI usually takes precedence over config data | Check effective property sources |
| App fails when remote API has brief outage | Startup hard-fails on network check | Review dependency criticality and readiness policy |
| Secret printed in error | Logging raw config or exception with value | Log only property name/constraint, protect Actuator |

## 19. Hands-On Exercises

### Exercise A — Missing Required Property

Create an `application.yml` containing only:

~~~yaml
lesson:
  client:
    timeout: 3s
~~~

Create the record:

~~~java
@ConfigurationProperties(prefix = "lesson.client")
@Validated
public record LessonClientProperties(
        @NotBlank String endpoint,
        @NotNull Duration timeout
) {}
~~~

Register the bean with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, add the validation starter, and run the application. Predict the outcome when `endpoint` is absent. Then add a valid endpoint and retry.

### Exercise B — Type Mismatch vs. Constraint Violation

Use the record:

~~~java
@ConfigurationProperties(prefix = "lesson.retry")
@Validated
public record LessonRetryProperties(
        @Min(1) @Max(5) int attempts,
        @NotNull Duration backoff
) {}
~~~

Try `attempts=0` and `attempts=10`. Next try `backoff=not-a-duration`. Observe the difference between a constraint error and a conversion error.

### Exercise C — Entire Nested Group Missing

Create:

~~~java
@ConfigurationProperties(prefix = "lesson")
@Validated
public record LessonProperties(@Valid @NotNull Retry retry) {
    public record Retry(@Min(1) int attempts) {}
}
~~~

Run without any `lesson.retry.*` keys. Explain why `@NotNull` on the parent property is crucial, while `@Valid` checks inner fields once the nested object is present.

### Exercise D — Default Masking Missing Configuration

Create a `lesson.partner.endpoint` property with a default pointing to a sandbox in `application.yml`. Run a production-like profile while forgetting to override the endpoint. Observe the bound value, then redesign it so the production endpoint is required without an unsafe sandbox default.

### Exercise E — Testing Startup Failure

Use `ApplicationContextRunner` with a `@ConfigurationProperties` class annotated with `@Validated` and constraints. Write at least three cases: valid, missing required property, and constraint violation. Assert that the context fails to start in both error cases rather than merely checking reflection annotations.

### Exercise F — Distinguishing Startup from Readiness

A service has a valid remote API URL, but the API is shut down for five minutes. Decide which checks belong in startup binding, which belong in readiness, and how to handle API recovery. Do not let constructor-level connections retry indefinitely.

### Exercise G — Conditional Validation

A feature has `enabled=false` and no `credentials`. When switched to `enabled=true` while `credentials` is still missing, the application must report an error. Design a cross-field constraint or validator to enforce this policy.

## 20. Production Configuration Checklist

Before deploying a Spring Boot service with externalized configuration:

- [ ] Important configuration groups use `@ConfigurationProperties` with clear prefixes.
- [ ] Configuration beans are registered and bound during startup.
- [ ] All required keys have appropriate `@NotNull` or `@NotBlank` constraints.
- [ ] Counts and ranges have `@Min`, `@Max`, or equivalent constraints.
- [ ] Required nested objects have both `@NotNull` and `@Valid`.
- [ ] The validation dependency and `@Validated` are configured.
- [ ] Cross-field rules have an explicit validation mechanism.
- [ ] There are no dangerous defaults for secrets or production endpoints.
- [ ] Profiles, config imports, env vars, and command-line overrides have been verified.
- [ ] Tests verify that startup fails on missing or invalid configuration.
- [ ] A readiness/health strategy exists for external dependencies.
- [ ] Secrets and full credential-bearing objects are never logged.
- [ ] Error messages let operators locate the right property and valid policy.
- [ ] Rollback/rollout procedures handle a new release failing to start.

## 21. Key Takeaways

1. **Startup configuration validation turns hidden configuration mistakes into visible startup failures**, instead of letting them lurk until traffic hits a specific business branch.
2. `@ConfigurationProperties` + `@Validated` + Bean Validation provide a centralized, type-safe way to enforce most Spring Boot configuration contracts.
3. **Binding, conversion, Bean Validation, and external dependency checks are distinct layers**; no single mechanism replaces the others.
4. `@NotNull` does not work as expected on primitives; use range constraints or wrapper types when you need to detect missing fields.
5. **Nested objects can be completely absent**; `@Valid` does not replace `@NotNull` for required groups.
6. An inappropriate default can mask missing configuration; use defaults only when truly safe for business logic.
7. Validation must inspect **the final resolved values from all loaded Spring Boot sources**, including profiles, environment variables, system properties, JSON, and CLI arguments.
8. **Fail fast does not mean crashing on every external system outage**; readiness, liveness, retries, and degraded mode require separate policies.
9. Context startup tests are a practical way to prove validation **actually runs**.
10. Configuration errors should name the key/constraint without exposing secrets.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, precedence, profile-specific data, and configuration outside the JAR.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): defining, binding, and registering `@ConfigurationProperties`.
- [Spring Boot Reference — Configuration Properties Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): `@Validated`, nested validation, and constraints.
- [Spring Boot Reference — Configuration Properties Conversion](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion): converting `Duration`, `DataSize`, and other types.
- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint configuration, observability, and protecting sensitive data.
- [Spring Boot Reference — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): readiness, liveness, and deploying in orchestrated environments.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraint mechanisms and cascaded validation.
