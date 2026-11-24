# `@ConfigurationProperties` and Input Configuration Validation

> **Chapter:** Connection Configuration  
> **Module:** `SPRING_BOOT_INTEGRATION` — organizing system integration in Spring Boot via HTTP clients, databases, caches, message brokers, and Spring Integration adapters. Emphasis is on configuration, data contracts, transactions, error handling, deduplication, testing, and observability of real integration flows.
>
> **Example scope:** Java 17+, Spring Boot 3 style with `jakarta.validation.*` and immutable `record` types. When using a different Spring Boot branch, verify packages, artifacts, APIs, and migration guides accordingly. The hostnames, IDs, and properties below are illustrative only; none are real credentials.

## 1. The problem: service starts up, but connects to the wrong system

A Spring Boot service receives shipping webhooks, writes inbox/outbox records to PostgreSQL, calls a partner API to query delivery status, and emits events to a broker. The system spans multiple environments: local, test, staging, and production.

Initially, the team writes:

```yaml
integration:
  partner:
    base-url: https://shipping.example.test
    timeout: 5000
    retry:
      max-retries: 12
```

At first glance the configuration looks complete, yet several questions remain unanswered:

- Does `timeout: 5000` mean **5,000 seconds, milliseconds, or another unit**?
- Is `base-url` a valid URI, required to use HTTPS, and free of accidental user-info/tokens?
- Does `max-retries: 12` exceed the retry budget and overload the partner API?
- If `retry` is omitted, does the application skip validating its nested fields?
- If an environment variable is missing, will the application **fail at startup** or crash only on the first request?
- Did the configuration bind into the injected bean, or is it sitting unused in YAML?
- Across multiple running instances, do total timeouts, retries, and concurrency exceed the partner system's limits?

In the `SPRING_BOOT_INTEGRATION` module, connection configuration is more than a few strings in `application.yml`. It is an **operational contract** connecting the application, HTTP clients, databases, caches, brokers, and external systems. A syntactically valid value is not necessarily valid semantically or safe to deploy.

`@ConfigurationProperties` groups related properties into a **typed** bean that can be validated and unit-tested independently. Bean Validation enables **fail-fast** checks when configuration violates constraints before the application begins processing work, instead of failing after data loss or calling the wrong system.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish `@ConfigurationProperties` from `@Value` and direct `Environment` lookups.
2. Bind nested structures, `Duration`, integers, URIs, and collections via relaxed binding rules.
3. Register configuration beans using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
4. Apply `@Validated`, `@NotBlank`, `@NotNull`, `@Valid`, `@Min`, `@Max`, and cross-field validation.
5. Understand the boundary between property bean validation, live connectivity checks, and integration contract checks.
6. Apply bound settings to `RestClient` rather than leaving them in YAML.
7. Test valid/invalid configurations, protect secrets, diagnose startup failures, and upgrade safely.

## 2. Role of @ConfigurationProperties in Spring Boot

Spring Framework provides `Environment`, property sources, the IoC container, and dependency injection. Spring Boot builds on this with **externalized configuration** and **type-safe configuration properties binding** to map values from config files, environment variables, command-line arguments, and supported sources into beans.

```mermaid
flowchart LR
    E["application.yml<br/>env / profile / command line"] --> P["Spring Environment<br/>property sources + precedence"]
    P --> B["Spring Boot Binder<br/>relaxed names + type conversion"]
    B --> V["Bean Validation<br/>@Validated + constraints"]
    V --> C["PartnerConnectionProperties<br/>immutable typed bean"]
    C --> A["RestClient adapter<br/>timeout + base URL"]
    C --> O["Observability / startup diagnostics"]
    A --> X["Partner HTTP API"]
```

Used properly:

- `@ConfigurationProperties` sets the **prefix** and defines the schema of a configuration group.
- The binder maps property names to constructor parameters/fields and performs supported type conversions.
- `@Validated` triggers constraint validation on the bound bean.
- `@Valid` cascades validation into nested objects.
- The container manages the configuration bean so services/adapters receive it via constructor injection.

**Key point:** `@ConfigurationProperties` does not open HTTP connections, create clients, or **automatically apply timeouts** to arbitrary libraries. Your adapter must read the bound values and configure the corresponding client APIs explicitly.

## 3. @ConfigurationProperties vs. @Value and Environment

| Access method | Best suited for | Limitations to remember |
|---|---|---|
| `@Value("${integration.partner.base-url}")` | One or a few isolated properties | Lacks structured group validation and nested objects |
| `Environment.getProperty(...)` | Dynamic lookups, special conditions, platform tooling | String-based keys, lacks centralized typing/validation |
| **`@ConfigurationProperties`** | A cohesive config group with a contract and multiple fields | Requires bean registration, binding, validation, and versioning |
| `@Bean @ConfigurationProperties` | Binding onto mutable third-party beans | Differs from constructor binding on immutable records |

Example using a single `@Value`:

```java
@Value("${integration.partner.base-url}")
private String partnerBaseUrl;
```

This can work for a single simple setting. Once you must verify that `base-url` uses HTTPS, `timeout.read` is positive, `retry.max-retries` stays bounded, and the entire group is consistent, scattering `@Value` across services becomes hard to maintain.

**Recommendation:** use `@ConfigurationProperties` to model connection contracts, reserving `@Value` for small cases that truly do not need a configuration group.

## 4. Designing the configuration contract for an HTTP partner

Suppose the service defines these fields:

| Property | Java type | Required? | Rules |
|---|---|---:|---|
| `integration.partner.base-url` | `String` | Yes | Absolute `https` URI with host; no user-info |
| `integration.partner.client-id` | `String` | Yes | Non-blank; technical identifier, not a secret |
| `integration.partner.timeout.connect` | `Duration` | Yes | Positive and within the defined upper bound |
| `integration.partner.timeout.read` | `Duration` | Yes | Positive and within the defined upper bound |
| `integration.partner.retry.max-retries` | `Integer` | Yes | Between `0` and `5` |
| `integration.partner.retry.backoff` | `Duration` | Yes | Non-negative; strictly positive if retries are enabled |

Create the configuration file:

```yaml
integration:
  partner:
    base-url: ${PARTNER_BASE_URL}
    client-id: ${PARTNER_CLIENT_ID}
    timeout:
      connect: 2s
      read: 5s
    retry:
      max-retries: 2
      backoff: 500ms
```

Environment values `PARTNER_BASE_URL` and `PARTNER_CLIENT_ID` must be provided in deployment configuration. Never leave a production URL as a source default just to make the app start.

You may set `PARTNER_BASE_URL=https://shipping.example.test` for testing, though that URL is strictly a placeholder and must not be treated as a real endpoint without explicit configuration. Values like `2s`, `5s`, and `500ms` carry **explicit units**, preventing confusion between milliseconds and seconds.

## 5. Declaring an immutable record with @ConfigurationProperties

Here is a complete example for Spring Boot 3 and the Bean Validation API:

```java
package com.example.integration.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "integration.partner")
public record PartnerConnectionProperties(
    @NotBlank String baseUrl,
    @NotBlank String clientId,
    @Valid @NotNull Timeouts timeout,
    @Valid @NotNull Retry retry
) {

    @AssertTrue(message = "base-url must be an absolute HTTPS URI without credentials")
    public boolean isSecureBaseUrl() {
        if (baseUrl == null || baseUrl.isBlank()) {
            return true; // @NotBlank handles missing/blank values.
        }
        try {
            URI uri = URI.create(baseUrl);
            return "https".equalsIgnoreCase(uri.getScheme())
                && uri.getHost() != null
                && uri.getUserInfo() == null
                && uri.getFragment() == null;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    public record Timeouts(
        @NotNull Duration connect,
        @NotNull Duration read
    ) {
        @AssertTrue(message = "connect/read timeouts must be positive and at most 30 seconds")
        public boolean isTimeoutRangeValid() {
            return valid(connect) && valid(read);
        }

        private static boolean valid(Duration d) {
            return d != null
                && d.compareTo(Duration.ZERO) > 0
                && d.compareTo(Duration.ofSeconds(30)) <= 0;
        }
    }

    public record Retry(
        @NotNull @Min(0) @Max(5) Integer maxRetries,
        @NotNull Duration backoff
    ) {
        @AssertTrue(message = "backoff must be nonnegative and positive when retry is enabled")
        public boolean isRetryPolicyValid() {
            if (backoff == null || maxRetries == null) {
                return true; // @NotNull handles missing data.
            }
            return backoff.compareTo(Duration.ZERO) >= 0
                && backoff.compareTo(Duration.ofSeconds(10)) <= 0
                && (maxRetries == 0 || backoff.compareTo(Duration.ZERO) > 0);
        }
    }
}
```

**Design explanation:**

- `record` produces an immutable value object for bound configuration; other code cannot mutate fields after initialization.
- `@ConfigurationProperties(prefix = "integration.partner")` defines the key group to bind.
- `@Validated` activates Spring validation when the bean is created/bound through the supporting infrastructure.
- `@NotBlank` applies to `String` fields requiring non-whitespace content, not merely non-`null`.
- `@NotNull` catches missing nested objects or required fields.
- `@Valid` ensures constraints **inside** `Timeouts` and `Retry` are evaluated.
- `@Min`/`@Max` apply to `Integer`; they are **not** the way to validate `Duration`.
- `@AssertTrue` on getter-style methods checks cross-field rules or specialized types.

The 30-second / 5-retry limits are **illustrative application rules**, not Spring Boot defaults. Choose limits based on real SLAs, partner rate limits, instance counts, and retry budgets.

### 5.1. Why use Integer instead of int for a required property?

If `maxRetries` is a primitive `int` and is omitted, constructor binding may receive the primitive default in some binding paths, causing `0` to look like "intentionally zero retries." With `Integer` and `@NotNull`, you state explicitly that the property **must be supplied**.

The same applies to three-state booleans: when "unconfigured" differs from `false`, use `Boolean` + validation or choose an intentional default.

### 5.2. @Valid does not replace @NotNull

A missing nested object may not be traversed by Bean Validation because there is no object instance to validate. Therefore:

```java
@Valid @NotNull Timeouts timeout
```

usually needs **both**: `@NotNull` catches an omitted group, and `@Valid` validates child fields when the group is present. Putting only `@Valid` on a nullable object does not imply the group itself is required.

## 6. Registering configuration beans so Spring performs binding

A class annotated only with `@ConfigurationProperties` does not automatically become a bean unless registered through the proper mechanism.

### 6.1. Option 1: @ConfigurationPropertiesScan

```java
package com.example.integration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class IntegrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IntegrationApplication.class, args);
    }
}
```

If `PartnerConnectionProperties` lives in `com.example.integration.config`, a subpackage of the main application class, the scanner discovers it automatically. If it resides in an external library/JAR outside the default package, use `@ConfigurationPropertiesScan(basePackageClasses = PartnerConnectionProperties.class)` or specify packages explicitly.

**Note:** `@ConfigurationPropertiesScan` does not scan arbitrary `@Component` classes; it looks for types marked as configuration properties. Do not add `@Component` to an immutable record just to register it.

### 6.2. Option 2: @EnableConfigurationProperties

Useful when you want to list the exact types to register:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerConnectionProperties.class)
class PartnerPropertiesConfiguration {
}
```

In an application, pick **one clear registration mechanism**; avoid both scanning and enabling the exact same type in multiple places. If another bean of the same type is declared manually alongside constructor binding, check which registration path is actually used.

### 6.3. Do not confuse with @ComponentScan

`@ComponentScan` discovers Spring stereotype beans like `@Service` or `@Component`. It is not a direct substitute for configuration properties scanning on immutable records. Place the application class in a sensible root package and register property beans using Spring Boot's dedicated APIs.

## 7. Dependencies needed for Bean Validation to actually run

Spring Boot can bind typed properties without every validation library, but `jakarta.validation.constraints.*` constraints require a **Bean Validation provider** and Spring's validation infrastructure to execute.

Gradle Groovy DSL:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    testImplementation("org.springframework.boot:spring-boot-starter-test")

    // Metadata for IDEs / config tooling; not a runtime validator.
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
```

This example assumes the build manages Spring Boot versions through an appropriate plugin/BOM. In Spring Boot 3 codebases, `jakarta.validation` is the active namespace; do not copy `javax.validation` from Spring Boot 2 tutorials without checking migration rules.

**Two tools with distinct responsibilities:**

- `spring-boot-starter-validation`: provides the runtime environment to evaluate constraints like `@NotBlank`, `@NotNull`, and `@Valid` for supported Bean Validation models.
- `spring-boot-configuration-processor`: generates metadata for IDE property autocomplete and type descriptions; it does **not** perform runtime validation.

If startup still accepts invalid properties, check whether the bean is managed via `@ConfigurationProperties` rather than instantiated manually with `new`, and verify `@Validated`, the validation provider, and nested `@Valid` annotations.

## 8. Relaxed binding: how YAML, environment, and Java names align

Spring Boot's binder supports flexible naming rules:

| YAML/property key | Java record component |
|---|---|
| `base-url` | `baseUrl` |
| `client-id` | `clientId` |
| `max-retries` | `maxRetries` |
| `timeout.connect` | `Timeouts.connect` |
| `timeout.read` | `Timeouts.read` |

When configuring via OS environment variables, follow your Boot version's canonical property-to-env conversion rules (typically replacing `.` with `_`, stripping `-`, and uppercasing), or use explicit placeholders like `PARTNER_BASE_URL` in YAML to remove ambiguity. Never assume every underscore-separated name maps identically across all contexts, especially for list/map keys.

### 8.1. Binding different types

```yaml
integration:
  partner:
    timeout:
      connect: 750ms
      read: 8s
    retry:
      max-retries: 3
      backoff: 1s
```

The binder converts values into `Duration` and `Integer` via supported converters. Avoid writing `timeout.read: 5000` without knowing the default unit; always include explicit `ms`, `s`, or `m` suffixes to prevent operational mistakes.

Commonly bindable types include `Duration`, `DataSize`, `URI`, enums, lists, maps, and primitives/wrappers. Conversion support depends on available modules and registered converters.

### 8.2. When Date/URI/enum/custom value objects are needed

Example:

```java
public enum PartnerMode {
    SANDBOX, LIVE
}
```

```yaml
integration:
  partner:
    mode: LIVE
```

A property maps to an enum when the record defines a matching component. However, an enum does not enforce **environment rules**: should `LIVE` mode be allowed in staging? Does the host match? Do secrets/tokens belong to that environment? Those rules require validation or deployment policies.

If a custom type has no built-in converter, Spring Boot supports registering converters for configuration binding via `@ConfigurationPropertiesBinding`. Converters must be **pure, unit-tested**, and fail clearly; never perform network calls or unpredictable external secret lookups during property binding.

## 9. Input validation: catching missing, mistyped, and semantically invalid values

There are at least **three validation layers**:

| Layer | Example error | Mechanism |
|---|---|---|
| **Binding/conversion** | `timeout.read: abc` cannot parse to `Duration` | Binder/type conversion, exception during bean creation |
| **Bean Validation** | `client-id` blank, `max-retries` exceeds `5` | `@Validated` and Jakarta Bean Validation constraints |
| **Semantic validation** | HTTP URL instead of HTTPS; retries enabled with `0` backoff | `@AssertTrue`, custom constraints, or application validators |

### 9.1. Type errors differ from constraint violations

`max-retries: ten` triggers a **binding failure** before `@Min`/`@Max` even run. `max-retries: 9` parses as an integer, then violates the constraint.

When diagnosing startup errors, inspect the **root cause** and exact property name: `BindException`, `ConfigurationPropertiesBindException`, `BindValidationException`, or the corresponding conversion/validation error. Exception classes can vary across versions and wrappers; do not stop reading at the first line "Application failed to start."

### 9.2. Do not apply type-mismatched constraints

```java
// Invalid: @Min/@Max target numeric types, not Duration.
@Min(1)
Duration readTimeout;
```

Use `@NotNull` for presence and custom validation for `Duration` bounds, or use specialized constraints supported by your **Bean Validation provider** after verifying its package and version. In the main example, `@AssertTrue` makes the positive check and 30-second cap explicit.

### 9.3. Multi-field validation needs clear messages

Validate `retry.max-retries` and `retry.backoff` together: enabling retries with zero backoff can trigger a retry storm. `@AssertTrue` in the nested record demonstrates this rule.

When a system has dozens of fields and complex invariants, consider a custom constraint like `@ValidPartnerRetryPolicy` backed by `ConstraintValidator<..., PartnerConnectionProperties.Retry>` to centralize logic and produce clearer error messages. Keep network connectivity checks out of validators; configuration validation should remain **pure and deterministic**.

## 10. Default values: convenient, yet able to mask missing configuration

Common ways to specify defaults:

1. Define defaults in `application.yml`.
2. Use `@DefaultValue` on constructor parameters/record components per Spring Boot's API.
3. Supply defaults in configuration classes/beans where the contract permits.

Example for an **optional** property in Boot 3:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.bind.DefaultValue;

public record OptionalTimeout(
    @DefaultValue("2s") Duration connect
) {}
```

Never use defaults just to "let the application start at all costs" for critical URLs, tenants, database names, or broker destinations. Falling back to a production URL in staging is far riskier than a clear startup failure.

### 10.1. Distinguishing defaults vs. required settings

| Property | Usually required? | Safe to default? |
|---|---|---|
| Partner base URL | **Yes** | Avoid production defaults |
| Target tenant/namespace | **Yes** if affecting data | Use controlled defaults only |
| Client ID | Yes | Should not default to an arbitrary local ID |
| Connect/read timeout | Yes or pre-approved default | Yes, if aligned with SLAs |
| Max retries | Per operational policy | Yes, within a budget |
| Logging verbosity | No | Yes |
| Tracing sampling | No | Yes, while controlling cost/performance |

### 10.2. Unexpected parameters

`@ConfigurationProperties` offers options for handling **unknown fields** and **invalid fields** in Boot's API, such as `ignoreUnknownFields = false` to tighten checks where the binder recognizes fields. However, **do not treat this as a foolproof detector for every typo** across all property sources, especially maps or dynamic keys. Combine metadata, config reviews, context tests, and deployment checks.

Never enable "ignore invalid fields" to suppress binding errors on critical connection settings; hiding conversion errors can make the system run with unintended parameters.

## 11. Applying validated configuration to the actual RestClient

Up to this point you only have a valid config object. For `timeout.connect` and `timeout.read` to take effect, they must be **applied to the HTTP client**. Example using Spring MVC/`RestClient` and a simple request factory:

```java
package com.example.integration.http;

import com.example.integration.config.PartnerConnectionProperties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class PartnerRestClientConfiguration {

    @Bean("partnerRestClient")
    RestClient partnerRestClient(
            RestClient.Builder builder,
            PartnerConnectionProperties properties) {

        SimpleClientHttpRequestFactory requestFactory =
            new SimpleClientHttpRequestFactory();

        requestFactory.setConnectTimeout(Math.toIntExact(
            properties.timeout().connect().toMillis()));
        requestFactory.setReadTimeout(Math.toIntExact(
            properties.timeout().read().toMillis()));

        return builder
            .baseUrl(properties.baseUrl())
            .requestFactory(requestFactory)
            .defaultHeader("X-Client-Id", properties.clientId())
            .build();
    }
}
```

What to understand:

- `RestClient.Builder` may be provided and customized by Boot depending on dependencies and version.
- `SimpleClientHttpRequestFactory` clearly illustrates applying timeouts; **it is not the optimal default for high-throughput production systems needing connection pooling and advanced HTTP features**.
- When production requires pooling, TLS, proxies, or advanced connection lifecycle control, pick an appropriate request factory/client stack, configure timeouts via its specific API, and test it.
- `Math.toIntExact(...)` catches integer overflow when converting durations to millisecond `int` values; our validation already caps `Duration`, making overflow unlikely.
- `X-Client-Id` is non-secret metadata. If using Bearer tokens or API keys, implement dedicated authentication and keep tokens out of logs.

An adapter can inject the client via qualifier:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PartnerStatusGateway {
    private final RestClient client;

    public PartnerStatusGateway(
            @Qualifier("partnerRestClient") RestClient client) {
        this.client = client;
    }

    public String fetchStatus(String shipmentId) {
        return client.get()
            .uri("/shipments/{id}/status", shipmentId)
            .retrieve()
            .body(String.class);
    }
}
```

`fetchStatus` only illustrates making an HTTP call; production code needs contract DTOs, HTTP error mapping, selective timeouts/retries, security, correlation IDs, and mock HTTP server tests.

### 11.1. A present property does not prove runtime behavior

`integration.partner.timeout.read: 5s` **does not enforce any timeout** if code merely runs:

```java
return builder.baseUrl(properties.baseUrl()).build();
```

You must test elapsed handling when an upstream deliberately delays its response. Likewise, `retry.max-retries` is just a number: it must be wired into an adapter or relay retry policy, otherwise nothing will retry automatically.

## 12. @ConfigurationProperties for databases, caches, and brokers

A similar pattern applies to auxiliary configuration groups, while separating **standard Spring Boot properties** from **application-defined properties**.

| Need | Common Boot/library properties | Application-defined properties |
|---|---|---|
| Database JDBC | `spring.datasource.*` | `integration.inbox.retention-days`, `integration.outbox.batch-size` |
| JPA/Hibernate | `spring.jpa.*` | `integration.reconciliation.max-age` |
| Redis/Cache | `spring.data.redis.*` / `spring.cache.*` by version | `integration.cache.default-ttl` |
| Kafka | `spring.kafka.*` | `integration.events.topic`, `integration.events.max-inflight` |
| RabbitMQ | `spring.rabbitmq.*` | `integration.messaging.retry-policy.*` |
| Partner HTTP client | Builder/client settings per actual API | `integration.partner.*` |
| Spring Integration | Dedicated channel/poller/adapter configs | `integration.flow.poll-delay`, `integration.flow.queue-capacity` |

For example, if you define:

```yaml
integration:
  events:
    topic: orders.events.v1
    max-inflight: 200
```

you need a `@ConfigurationProperties(prefix = "integration.events")` bean and producer code that actually reads those fields. Placing keys in YAML **does not create a Kafka topic** or update producer configuration by itself.

### 12.1. Do not replace Boot beans unnecessarily

If your goal is configuring the PostgreSQL pool, use `spring.datasource.hikari.*` when using Hikari via Boot rather than prematurely defining a new `@Bean DataSource`. Defining your own `DataSource` causes auto-configuration branches to **back off**, meaning default properties may no longer apply as before.

Similarly, if you only need an HTTP client for a partner, inject the Boot-configured builder to create your client bean rather than redefining `RestClient.Builder` application-wide.

### 12.2. Custom @Bean @ConfigurationProperties vs. immutable records

A mutable third-party bean can be bound directly:

```java
@Bean
@ConfigurationProperties(prefix = "integration.legacy-client")
LegacyClientSettings legacyClientSettings() {
    return new LegacyClientSettings();
}
```

`LegacyClientSettings` is an illustrative class with setters/getters from a library or application. This path **binds onto a bean returned by a factory method**, unlike constructor binding on immutable records in the main example. Validation rules still must be established; do not assume `@Validated` behaves identically across all bean creation mechanisms without verifying.

## 13. Environment configuration, profiles, and precedence

Spring Boot collects properties from multiple sources following the **precedence order** defined for your version. A value in `application.yml` can be overridden by environment variables, command-line arguments, or imported configuration sources.

Example:

```yaml
# application.yml
integration:
  partner:
    timeout:
      connect: 2s
      read: 5s
```

```yaml
# application-staging.yml (illustrating a profile)
integration:
  partner:
    timeout:
      read: 10s
```

When the `staging` profile is properly activated, `timeout.read` becomes `10s` while `timeout.connect` still comes from the base config. Still, a higher-precedence source can override both. **Never determine effective configuration by reading a single YAML file.**

### 13.1. Configuration binding can shift across deployments

- Activate profiles in the deployment environment per organizational process; avoid hard-coding `spring.profiles.active` indiscriminately in code.
- Never commit tokens or passwords in `application-prod.yml`.
- When using `spring.config.import` for external configs, understand behavior when sources are unavailable and how permissions are granted.
- When configuration changes, do not assume immutable beans refresh automatically at runtime. Design controlled refresh or restart workflows if dynamic updates are required.
- For versioned config maps/secrets, plan rollouts and test "two versions running concurrently" when changing endpoints or schemas.

### 13.2. Right environment endpoint matters more than clean startup

An HTTPS `base-url` whose DNS resolves **can still point to the wrong tenant or environment**. Enforce environment policies: production calls only approved production endpoints, and staging calls only sandbox or test tenants. This is **semantic/policy validation**, enforceable via configuration policies, host allowlists, deploy admission checks, or environment-specific config tests.

## 14. Secrets, logging, and Actuator configprops

Connection configurations frequently hold credentials, tokens, passwords, or sensitive endpoints. Protect them starting at binding time:

1. Retrieve secrets from an organization-managed secret manager or secure env; never hard-code or print them in example logs.
2. If a properties bean holds a secret field, avoid calling `toString()` on the record, which prints all fields.
3. Never embed credentials inside URIs like `https://user:pass@host`.
4. Mask sensitive values in exceptions, health diagnostics, and support bundles.
5. Ensure actuator endpoints, tracing, and logging do not inadvertently leak configuration.
6. Apply least-privilege permissions for databases, brokers, Redis, and partner APIs.

Actuator provides endpoints like `/actuator/configprops` (when dependency, exposure, and security permit) to inspect **configuration properties beans**. Yet that endpoint exposes bean structures and keys, with value-masking policies that vary by version. **Never expose it publicly** or disable masking just for debugging convenience.

### 14.1. Avoid logging bind failures that contain secrets

Validation messages should name the property and the **violated rule** (e.g. "must not be blank"), never the token or credential being bound. For custom `@AssertTrue` methods, return a clear static message like `base-url must be HTTPS`, without concatenating secret contents into the message.

## 15. Fail-fast validation vs. health checks and readiness

There are three distinct checking stages:

```mermaid
flowchart LR
    A["Startup: bind + validate config"] --> B["Initialize HTTP/DB/broker clients"]
    B --> C["Readiness: able to serve?"]
    C --> D["Runtime: requests/jobs/messages"]
    D --> E["Resilience: timeout/retry/circuit breaker"]
    E --> F["Metrics + alerts + reconciliation"]
```

| Mechanism | Question answered | Example |
|---|---|---|
| **Configuration validation** | "Are parameters present, properly typed, and sensible?" | `timeout.read > 0`, `base-url` is HTTPS |
| **Startup connectivity** | "Can an initial connection be established?" | Pinging DB or broker at initialization if designed |
| **Readiness/health** | "Is this instance currently able to serve traffic?" | Connection pool, essential dependencies |
| **Runtime resilience** | "What if a dependency fails mid-flight?" | Timeouts, retry budgets, circuit breakers, outbox |
| **End-to-end reconciliation** | "Did work actually complete downstream?" | Pending outbox, consumer processing status |

Avoid making network calls inside `ConstraintValidator` or `@AssertTrue` to "validate the URL is reachable" — external dependencies can flap, destabilizing startup and making validation logic hard to test. Validate URI syntax/allowlists in the configuration layer, and handle health/readiness/liveness according to system policy.

In particular, a temporarily unavailable HTTP partner should not necessarily fail **liveness** and cause continuous pod restarts. If the application can still accept requests into an inbox/outbox, define readiness and business degradation according to SLAs.

## 16. Configuration validation in a webhook → DB → outbox → broker flow

A typical integration sequence:

```mermaid
sequenceDiagram
    participant Boot as Spring Boot startup
    participant Binder as Binder + Bean Validation
    participant API as Webhook Controller
    participant Service as Application service
    participant DB as PostgreSQL
    participant Relay as Outbox relay
    participant Broker as Kafka / RabbitMQ

    Boot->>Binder: Bind integration.partner.*
    Binder-->>Boot: Validated PartnerConnectionProperties
    Boot->>API: Application ready
    API->>Service: receive webhook(eventId)
    Service->>DB: TX: inbox + state + outbox
    DB-->>Service: Commit
    Service-->>API: accepted / duplicate
    Relay->>DB: claim committed outbox
    Relay->>Broker: publish event
    Broker-->>Relay: publish acknowledgement
    Relay->>DB: mark published or retry
```

Configuration validation does not replace these responsibilities:

- **Inbound HTTP contract:** verifying signatures, payload schemas, tenant, and event IDs.
- **Database transaction:** UNIQUE constraint on `(partner, eventId)` and writing inbox/outbox in the same transaction.
- **HTTP client:** enforcing real timeouts/auth and handling uncertain outcomes.
- **Broker:** selecting the right topic/queue, serializers, ACKs, and retries.
- **Consumer:** idempotent processing; duplicate messages can arrive from relay retries/redeliveries.
- **Observability:** correlation IDs, event IDs, pending outbox counts, and per-boundary errors.

### 16.1. Do not confuse valid config with valid business behavior

`retry.max-retries = 5` may pass Bean Validation yet still overwhelm a partner API capped at 10 requests/minute. Choose retry budgets based on **real SLAs and rate limits**, factoring in backoff/jitter, concurrency, and cluster-wide load.

Similarly, a syntactically valid Kafka topic name does not prove the topic exists, publish ACLs are granted, or producer/consumer schemas are compatible.

## 17. Testing configuration with ApplicationContextRunner

Whenever writing a properties bean, add **lightweight context tests** covering three categories: valid values, missing fields, and invalid values.

Spring Boot 3 test example using `ApplicationContextRunner` and validation auto-configuration:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class PartnerPropertiesBindingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PartnerConnectionProperties.class)
    static class TestConfig {
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(ValidationAutoConfiguration.class))
            .withUserConfiguration(TestConfig.class);

    @Test
    void bindsAndValidatesCorrectValues() {
        runner.withPropertyValues(
            "integration.partner.base-url=https://partner.example.test",
            "integration.partner.client-id=order-service",
            "integration.partner.timeout.connect=2s",
            "integration.partner.timeout.read=5s",
            "integration.partner.retry.max-retries=2",
            "integration.partner.retry.backoff=500ms"
        ).run(context -> {
            assertThat(context.getStartupFailure()).isNull();

            PartnerConnectionProperties props =
                context.getBean(PartnerConnectionProperties.class);

            assertThat(props.timeout().read())
                .isEqualTo(java.time.Duration.ofSeconds(5));
            assertThat(props.retry().maxRetries()).isEqualTo(2);
        });
    }

    @Test
    void failsOnInvalidRetryAndTimeout() {
        runner.withPropertyValues(
            "integration.partner.base-url=https://partner.example.test",
            "integration.partner.client-id=order-service",
            "integration.partner.timeout.connect=0s",
            "integration.partner.timeout.read=5s",
            "integration.partner.retry.max-retries=9",
            "integration.partner.retry.backoff=0ms"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull()
        );
    }
}
```

This test demonstrates decoupling validation from real databases, brokers, and HTTP servers. It assumes the Bean Validation dependency is present, classes/configs are in compatible packages/imports, and test support APIs match your Boot version.

**Do not assert only "startup failed"** in real tests. Also check that the root cause points to the expected field/constraint, so an unrelated classpath or missing-bean error does not make a broken test pass falsely.

### 17.1. Additional test cases

| Test case | Expected result |
|---|---|
| Missing `base-url` | Fails via `@NotBlank` |
| `base-url` is HTTP instead of HTTPS | Fails via semantic validation |
| `base-url` has invalid URI syntax | Fails with static message leaking no secrets |
| Entire `timeout` block missing | Fails via nested `@NotNull` |
| `timeout.connect=0s` | Fails via positive duration rule |
| `timeout.read=31s` | Fails via illustrative 30-second limit |
| `max-retries=-1` or `6` | Fails via `@Min`/`@Max` |
| `max-retries=2`, `backoff=0ms` | Fails via cross-field policy |
| `max-retries=0`, `backoff=0ms` | Passes if permitted by contract |
| `timeout.read=not-a-duration` | Fails in binder/conversion |
| Env overrides YAML | Bound result reflects higher-precedence source |
| Valid config but slow HTTP | Real client times out per configured request factory |
| Two beans of same type | Explicit `@Qualifier` injection, no accidental selection |
| Custom DataSource/HTTP builder | Config uses intended bean without unintentionally dropping auto-customizers |

## 18. Integration testing: valid config must produce a working client

Unit validation only proves fields satisfy constraints; it **does not prove the adapter actually uses them**. Integration tests are needed at key boundaries.

Example with a test-owned mock HTTP server:

1. Point `base-url` to the mock server on its test port.
2. Obtain `RestClient` through `PartnerRestClientConfiguration`, without constructing a separate builder in the test.
3. Send a request and assert the exact path, headers, body, and authentication.
4. Have the mock server delay past `timeout.read` and verify the client times out.
5. Return HTTP 429/503/400 and verify retryable vs. non-retryable classification per policy.
6. Verify retries reuse the same command ID and stay within the retry budget.
7. Verify no secrets/tokens appear in logs, exceptions, or metrics.

For databases and brokers, test endpoint binding and permissions similarly: create a real datasource/consumer using test infrastructure, and verify schemas, unique constraints, producer ACKs, and duplicate handling. **Never treat a successful `ApplicationContext` startup as proof that the end-to-end integration works.**

## 19. Troubleshooting: where do configuration errors usually appear?

### 19.1. Startup missing PartnerConnectionProperties bean

Error such as:

```text
No qualifying bean of type
'com.example.integration.config.PartnerConnectionProperties'
```

Check `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, verify package scanning covers the class, and ensure the record is not instantiated manually with `new` outside the container. `@ConfigurationProperties` is **not** `@Component`.

### 19.2. Bean exists, but all fields are null

Check:

- Is the prefix exact (`integration.partner`)?
- Does the YAML structure match the key hierarchy?
- Which profile or property source currently has higher precedence?
- Was a mutable bean declared manually without binding it properly?
- Was constructor binding used in accordance with the Boot version?
- Was the bean created inside **the active ApplicationContext**?

With `@NotNull` and `@NotBlank` configured as shown, missing required fields should fail startup rather than silently passing; if not, validation may not be active.

### 19.3. Validation does not run or skips nested objects

Check:

1. Is a validation provider dependency on the runtime classpath?
2. Does the properties type have `@Validated` or the appropriate validation trigger?
3. Was the type bound via Spring Boot's binder rather than constructed via `new`?
4. Does the nested field have `@Valid` to cascade constraint checks?
5. Does a required nested object have `@NotNull`?
6. Is an exception being caught or an ignore-invalid-fields setting masking the error?

### 19.4. Timeout configured, yet requests still hang

A classic symptom is code reading `timeout.read` from properties to log it without applying it to the HTTP client. Inspect **the actually injected RestClient bean**, its request factory, interceptors/clients, and run a latency test. Many clients distinguish connect timeout, response/read timeout, connection acquisition timeout, and total deadline; one property does not cover all of them.

### 19.5. Env config looks "right", yet app uses another value

Check Spring Boot's precedence rules for your version, active profiles, imported sources, and placeholders. Never print secrets to stdout; during diagnostics, log only **non-sensitive property keys/sources, types, and validity state**, or use internal tools with masking.

### 19.6. Custom bean causes Boot to back off

When defining a custom `DataSource`, `RestClient.Builder`, or other infrastructure bean, auto-configuration conditions like `@ConditionalOnMissingBean` can cause Boot **not to create its default bean**. Read the Condition Evaluation Report (e.g. starting with `--debug` in a controlled environment) and verify actual bean wiring before adding annotations or enabling bean definition overriding.

## 20. Checklist for implementing reliable connection configuration

1. **Group properties** per adapter/partner (`integration.partner.*`, `integration.events.*`); avoid scattered magic strings.
2. **Choose exact types**: `Duration`, `Integer`, `URI`, enums, lists/maps; avoid ambiguous time units.
3. **Mark required fields** with `@NotBlank`/`@NotNull` and use boxed types when missing differs from a default.
4. **Validate nested objects** with `@Valid` plus `@NotNull` when the group is required.
5. **Validate semantics**: HTTPS, URL allowlists, positive timeouts, retry budgets, and cross-field invariants.
6. **Register beans properly** via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
7. **Include a validator provider** and test startup failures on invalid values; never rely on annotations that only look right in source code.
8. **Prefer Boot's standard config** for datasources/brokers/caches when sufficient; avoid manual beans that disable auto-config unnecessarily.
9. **Apply config to live clients**: pools, timeouts, TLS, auth, retries; never bind and leave unused.
10. **Keep secrets out of source/logs/public Actuator**; verify masking, permissions, and secret lifecycles.
11. **Manage environments**: profiles, placeholders, imports, precedence, tenants, and approved target endpoints.
12. **Separate validation from health**; do not turn external outages into unrelated configuration errors.
13. **Ensure business guarantees**: inbox/outbox, idempotency, transactions, consumer ACKs, and reconciliation remain essential.
14. **Test across layers**: binding unit tests, Spring contexts, mock HTTP, DB/broker integration, and crash/retry tests.
15. **Observe behavior**: config validation failures, timeouts, retry counts, pool saturation, outbox backlog, and correlation IDs.

### Knowledge check

**Q1:** How does `@ConfigurationProperties` differ from `@Value` when configuring an HTTP partner?  
**A:** It groups multiple properties into a typed bean supporting nested binding and centralized validation. `@Value` suits a few simple isolated values.

**Q2:** Is `@NotNull` on nested `Timeouts` enough to enforce `connect > 0`?  
**A:** No. You also need `@Valid` to trigger inner constraints plus a positive-value rule for `Duration`.

**Q3:** With `timeout.read: 5s` in YAML, will `RestClient` automatically time out after 5 seconds?  
**A:** Not automatically. Your adapter must apply the value to the underlying request factory/client and test the timeout behavior.

**Q4:** Is `@Min(1) Duration timeout` a proper way to validate a duration?  
**A:** No. `@Min` applies to numeric types; use a constraint suited to `Duration` or tested custom validation.

**Q5:** Why shouldn't a bean containing a token use `record.toString()` in logs?  
**A:** Records include all component values in their `toString()` output, which can leak secrets.

**Q6:** Does a validated properties bean guarantee the broker is up and permissions are valid?  
**A:** No. You still need connectivity/readiness checks and environment integration tests, alongside retry and alerting policies.

**Q7:** If an environment variable overrides YAML, which value is bound?  
**A:** The value from the higher-precedence property source according to your Spring Boot version's rules; verify the effective configuration.

---

In the **Connection Configuration** chapter of `SPRING_BOOT_INTEGRATION`, remember: **`@ConfigurationProperties` turns external configuration into a typed Java contract; `@Validated` and Bean Validation enforce that contract right at startup**. Still, a valid config bean **never replaces** configuring live clients, protecting secrets, defining transaction boundaries, designing idempotency/retries, and observing HTTP–database–cache–broker outcomes across the system.
