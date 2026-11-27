# Separating Infrastructure Configuration from Business Parameters

## 1. Why Separate These Two Configuration Groups?

A Spring Boot/Spring Cloud application typically has multiple kinds of values that vary by environment or operational policy. They may live side by side in `application.yml`, yet their purpose and the people responsible for changing them differ.

**Infrastructure configuration** describes how the application connects to and operates within its runtime environment: service addresses, ports, timeouts, connection pools, registries, TLS, databases, message brokers, and resource limits.

**Business parameters** describe policies or limits enforced by the domain: free-shipping thresholds, maximum discount rates, transaction caps, maximum items per order, reservation hold times, or approval thresholds.

Example in an e-commerce application:

| Group | Example | Who Typically Owns Changes? | Question Answered |
| --- | --- | --- | --- |
| Infrastructure | Pricing service URL, connect timeout, pool size, database endpoint | Platform/operations or integration team | How does the application connect and handle load? |
| Business | Free-shipping threshold, discount limit, max items per order | Product/business owner or domain team | What commercial policy currently applies? |
| Operational secrets | Database password, API token, private key | Security/platform and secret manager | Who is authorized to read credentials? |

Both groups can be loaded into Spring's `Environment` and bound into strongly typed objects. However, stuffing everything into a single `AppProperties` class or scattering `@Value` across services makes it hard to tell who is allowed to change a value, which changes require a restart, and which values must obey domain rules.

The goal of this lesson in **SPRING_CLOUD_CORE** is designing structured configuration that cleanly separates infrastructure responsibilities from business policies, using Spring Boot `@ConfigurationProperties` together with Spring Cloud's external configuration mechanisms to manage them safely.

## 2. Classification Principles

Do not classify values solely by which file they live in. Consider **what the value means, who owns it, how often it changes, and the impact of changing it**.

### 2.1. Infrastructure Configuration

Values typically belonging here:

- Hostnames, URIs, and ports for databases, message brokers, registries, or external services.
- Connect/read timeouts, retry limits, connection pool sizes, thread pool sizes.
- TLS settings, certificate paths, proxies, and network behavior.
- Service discovery, instance registration, load balancers, and health checks.
- Management endpoints, log levels, metric exports, and resource limits.

This group primarily governs how the application integrates with the platform. Changing `server.port`, database addresses, or discovery registries may require restarts, rollouts, or recreating clients. Never assume every infrastructure property is safe to refresh at runtime.

### 2.2. Business Parameters

Values typically belonging here:

- Order value thresholds for free shipping.
- Maximum discount rates or maximum discount amounts.
- Maximum items allowed in a single order.
- Reservation hold durations or order confirmation windows.
- Transaction caps, business operation retry counts, or approval thresholds.

These express policies that change with markets, campaigns, or business decisions. They need clear names, precise data types, validation, and change-control processes. For policies affecting correctness or finances, consider versioning, effective dates, audit logs, and approval workflows.

### 2.3. Secrets Are Not a Business Group

Passwords, tokens, and private keys are **secrets**. They may serve infrastructure or business integrations, but storage and access control must be managed separately. Never commit secrets to Git, bake them into Docker images, print them to logs, or expose them via unsecured management endpoints.

Suitable sources include Kubernetes Secret volumes, Docker secrets, platform secret managers, or Spring Boot config trees. Secrets can still bind into typed configuration, provided read permissions and rotation lifecycles follow security policies.

## 3. Organizing Configuration Namespaces

Clear prefixes separate infrastructure configuration from business parameters. Example:

```yaml
spring:
  application:
    name: order-service

  datasource:
    url: jdbc:postgresql://postgres:5432/orders
    username: order_app
    # Password is supplied from a secret store, not written here.

  cloud:
    discovery:
      enabled: true

app:
  infrastructure:
    pricing-client:
      base-url: https://pricing.internal
      connect-timeout: 2s
      read-timeout: 5s
      max-connections: 40

  business:
    checkout:
      currency-code: VND
      free-shipping-threshold: 500000
      maximum-discount-rate: 0.20
      maximum-items-per-order: 30
```

In this example:

- `spring.*` is reserved for integrations defined by Spring Boot/Spring Cloud.
- `app.infrastructure.*` holds application-specific connection and operational parameters.
- `app.business.*` holds the application's business policy parameters.
- The database password comes from a separate secret source.

Do not invent custom properties under `spring.*` if they are not part of a namespace defined by Spring Boot or Spring Cloud. For application-owned settings, use an application-owned prefix such as `app.*`, `order.*`, or a specific domain name.

Namespace structure alone does not enforce architectural boundaries. What matters is that receiving classes, change owners, provisioning sources, and consuming code align with the prefix's meaning.

## 4. Using `@ConfigurationProperties` to Bind Typed Configuration

Spring Boot supports two common ways to read properties:

- `@Value` suits a few simple values at a single usage site.
- `@ConfigurationProperties` suits structured groups of properties needing relaxed binding, metadata, and validation.

For infrastructure settings and business parameters, group related keys into separate classes rather than injecting individual keys with `@Value` across multiple services.

### 4.1. Typed Configuration for Infrastructure

Example client configuration for calling the pricing service:

```java
package com.example.order.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.infrastructure.pricing-client")
@Validated
public record PricingClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Positive int maxConnections
) {
}
```

Fields use concrete types:

- `URI` parses addresses and avoids treating URLs as arbitrary strings.
- `Duration` expresses timeouts such as `2s`, `500ms`, or `1m`.
- `int` with `@Positive` enforces a connection count greater than 0.
- `@NotNull` ensures addresses and timeouts are supplied.

Records fit well when configuration objects should be immutable after startup. With a single canonical constructor, modern Spring Boot applies constructor binding without requiring `@ConstructorBinding`. Register this type via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`; do not annotate it with `@Component` to instantiate it as an ordinary component.

### 4.2. Typed Configuration for Business Parameters

Example checkout policy:

```java
package com.example.order.config;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Pattern;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.business.checkout")
@Validated
public record CheckoutPolicyProperties(
        @NotBlank
        @Pattern(regexp = "[A-Z]{3}")
        String currencyCode,

        @NotNull
        @PositiveOrZero
        BigDecimal freeShippingThreshold,

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        BigDecimal maximumDiscountRate,

        @Positive
        int maximumItemsPerOrder
) {
}
```

This example shows how validation protects policies:

- `currencyCode` must be present and match a three-uppercase-letter currency code pattern.
- `freeShippingThreshold` must be non-negative.
- `maximumDiscountRate` falls between 0 and 1.
- `maximumItemsPerOrder` must be greater than 0.

Use `BigDecimal` for money and rates requiring decimal precision; avoid `double` in financial calculations. To ensure the currency code genuinely exists, also validate via `Currency.getInstance(currencyCode)` in a factory or custom validator. Regex checks only character shape, not ISO recognition.

### 4.3. Registering Typed Configuration

On the application class:

```java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

Spring Boot scans `@ConfigurationProperties` classes in specified packages or from the application class's package downward. If you prefer not to scan, register explicitly:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties({
        PricingClientProperties.class,
        CheckoutPolicyProperties.class
})
public class PropertiesConfiguration {
}
```

A Jakarta Bean Validation implementation must be on the classpath for constraints like `@NotBlank`, `@Positive`, and `@DecimalMax` to run. In Spring Boot, add the validation starter matching your release version. Maven dependency example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

## 5. Passing Business Configuration to the Domain Without Pulling Spring Into the Domain

An important boundary: `@ConfigurationProperties` classes are adapters receiving data from the deployment environment. Domain models should not depend directly on Spring annotations or property-loading mechanics.

You can translate typed configuration into a domain policy object:

```java
package com.example.order.domain;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record CheckoutPolicy(
        Currency currency,
        BigDecimal freeShippingThreshold,
        BigDecimal maximumDiscountRate,
        int maximumItemsPerOrder
) {
    public CheckoutPolicy {
        Objects.requireNonNull(currency, "Currency is required");
        Objects.requireNonNull(freeShippingThreshold,
                "Free shipping threshold is required");
        Objects.requireNonNull(maximumDiscountRate,
                "Maximum discount rate is required");
        if (freeShippingThreshold.signum() < 0) {
            throw new IllegalArgumentException(
                    "Free shipping threshold must not be negative");
        }
        if (maximumDiscountRate.signum() < 0
                || maximumDiscountRate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "Maximum discount rate must be between 0 and 1");
        }
        if (maximumItemsPerOrder <= 0) {
            throw new IllegalArgumentException(
                    "Maximum items per order must be positive");
        }
    }
}
```

Create a converter bean in the configuration/adapter layer:

```java
package com.example.order.config;

import java.util.Currency;

import com.example.order.domain.CheckoutPolicy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CheckoutPolicyConfiguration {

    @Bean
    CheckoutPolicy checkoutPolicy(CheckoutPolicyProperties properties) {
        return new CheckoutPolicy(
                Currency.getInstance(properties.currencyCode()),
                properties.freeShippingThreshold(),
                properties.maximumDiscountRate(),
                properties.maximumItemsPerOrder()
        );
    }
}
```

The domain receives a converted `CheckoutPolicy` without knowing whether values originated from YAML, environment variables, Config Server, or a secret store. This allows standalone domain unit testing and keeps business classes decoupled from Spring Boot.

If policies have multiple versions or effective dates, model those details explicitly in the domain policy rather than piling boolean flags into YAML files.

## 6. Infrastructure Configuration Used at Adapters

Typed infrastructure properties are typically injected into components responsible for constructing clients or connections:

```java
package com.example.order.infrastructure.pricing;

import com.example.order.config.PricingClientProperties;
import org.springframework.stereotype.Component;

@Component
public class PricingEndpoint {

    private final PricingClientProperties properties;

    public PricingEndpoint(PricingClientProperties properties) {
        this.properties = properties;
    }

    public String baseUrl() {
        return properties.baseUrl().toString();
    }
}
```

In real applications, an HTTP client configuration bean uses `connectTimeout`, `readTimeout`, and `maxConnections` to configure a request factory or connection pool matching the chosen HTTP client. Never mix pricing math, free-shipping checks, or order limits into this HTTP configuration class.

Similarly, properties like `spring.datasource.*`, `spring.cloud.discovery.*`, and `management.*` belong to infrastructure integrations. Let Spring Boot/Spring Cloud auto-configuration consume those standard properties; only create custom prefixes for application-specific settings.

## 7. Configuration Sources and Environment Overrides

Spring Boot externalizes configuration so the same artifact runs across local, test, staging, and production. Properties can come from:

- `application.yml` and profile-specific files like `application-prod.yml`.
- Configuration files outside the image or JAR.
- OS environment variables.
- Java system properties.
- `SPRING_APPLICATION_JSON`.
- Command-line arguments.

Sources follow a precedence order. Among standard sources, config data loads before OS environment variables, Java system properties, and command-line arguments; higher-precedence sources override lower ones. Profile-specific config data overrides non-profile files per Spring Boot rules.

Example `application.yml` with default values:

```yaml
app:
  infrastructure:
    pricing-client:
      base-url: http://localhost:9090
      connect-timeout: 1s
      read-timeout: 3s
      max-connections: 10

  business:
    checkout:
      currency-code: VND
      free-shipping-threshold: 300000
      maximum-discount-rate: 0.15
      maximum-items-per-order: 20
```

`application-prod.yml` can adjust infrastructure per environment:

```yaml
app:
  infrastructure:
    pricing-client:
      base-url: https://pricing.internal
      connect-timeout: 2s
      read-timeout: 5s
      max-connections: 80
```

Production business parameters can come from a dedicated source with an approval workflow:

```yaml
app:
  business:
    checkout:
      currency-code: VND
      free-shipping-threshold: 500000
      maximum-discount-rate: 0.20
      maximum-items-per-order: 30
```

In production, committing files containing real production values into the repository is unnecessary. Use external config locations, Config Server, or platform-managed configuration sources. What matters is knowing which source owns each key and verifying final resolved values after precedence applies.

### 7.1. Environment Variables

Spring Boot relaxed binding maps kebab-case keys to environment variable names. Example:

```bash
APP_INFRASTRUCTURE_PRICINGCLIENT_BASEURL=https://pricing.internal
APP_INFRASTRUCTURE_PRICINGCLIENT_CONNECTTIMEOUT=2s
APP_INFRASTRUCTURE_PRICINGCLIENT_READTIMEOUT=5s
APP_BUSINESS_CHECKOUT_CURRENCYCODE=VND
APP_BUSINESS_CHECKOUT_FREESHIPPINGTHRESHOLD=500000
APP_BUSINESS_CHECKOUT_MAXIMUMDISCOUNTRATE=0.20
APP_BUSINESS_CHECKOUT_MAXIMUMITEMSPERORDER=30
```

Spring Boot's environment variable naming rule replaces dots with underscores, strips hyphens, and converts to uppercase. When working with lists or complex maps, consult the official relaxed binding rules rather than guessing names.

### 7.2. Profiles Should Not Become a Place to Duplicate Policies

Profiles work well for environment differences such as endpoints, timeouts, pool sizes, and log levels. If a business policy varies by country or tenant, consider a dedicated policy source and model its applicability scope explicitly. Avoid creating nearly identical profile files just to tweak a few business numbers without clear ownership or effective-date rules.

## 8. Combining Spring Cloud Config and External Sources

When multiple services share policies or per-environment configuration, Spring Cloud Config Server provides a centralized property source. Clients use the Config Client dependency and Config Data import, for example:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
```

In this model, Config Server can manage separate key groups:

- `app.infrastructure.*` for endpoints, timeouts, or connection settings.
- `app.business.*` for checkout policies, limits, and business thresholds.

Avoid dumping multiple services' configurations into one file without clear ownership. Use Config Server application names, profiles, and labels/versions to control which service receives which settings.

For secrets, consider config trees or secret managers instead of storing passwords and tokens directly in Git-backed config repositories. Config Server supports multiple backends and encryption, yet access control, key management, and rotation workflows must still be designed.

### 8.1. Source Separation Needs Governance Rules Too

A property can be defined simultaneously in `application.yml`, Config Server, and environment variables. Establish conventions such as:

| Prefix | Default Source | Allowed Override Source | Approver |
| --- | --- | --- | --- |
| `app.infrastructure.*` | Per-environment profile/config | Platform deployment variables or Config Server | Platform/operations |
| `app.business.*` | Config Server or policy repository | Audited policy-change workflow | Product/domain owner |
| `spring.datasource.password` | Secret manager / mounted secret | Secret rotation workflow | Security/platform |

This table illustrates governance, not Spring defaults. Decide clearly which values may be overridden and at what layer. When an environment variable accidentally overrides a business parameter, the application can end up running an unapproved policy.

## 9. Validation: Blocking Invalid Configuration at Startup

Validation checks more than whether a string parses into a type. It also checks whether **the value lies within a valid domain**.

Examples:

| Property | Type | Suggested Validation |
| --- | --- | --- |
| `connect-timeout` | `Duration` | `@NotNull`, custom constraint if strictly positive is required |
| `max-connections` | `int` | `@Positive` |
| `currency-code` | `String` | `@NotBlank`, `@Pattern`, then verify ISO currency code |
| `free-shipping-threshold` | `BigDecimal` | `@PositiveOrZero` |
| `maximum-discount-rate` | `BigDecimal` | `@DecimalMin("0.0")`, `@DecimalMax("1.0")` |
| `maximum-items-per-order` | `int` | `@Positive` |

For nested objects, use `@Valid` so validation descends into child objects. Required properties need `@NotNull` or `@NotBlank`; never assume `@Valid` makes a null object valid.

When a value is invalid, the application should fail fast at startup rather than booting partway and failing on the first request. For example, a discount rate of `1.5` would create a 150% discount policy if left unchecked.

For cross-field rules—such as `minimum-order-value` not exceeding `maximum-order-value`—use a class-level custom constraint or check inside the constructor/factory building the domain policy. Configuration-layer validation guards inputs; the domain model should still protect its own core invariants.

## 10. Choosing Mutable vs. Immutable When Runtime Refresh Is Needed

Not every parameter needs to change while the application runs. Determine the lifecycle before choosing a configuration style.

### 10.1. Immutable Records for Startup Configuration

Constructor-bound records fit configuration read only at startup, such as:

- HTTP client endpoints and timeouts.
- Ports, TLS, or infrastructure connections requiring client recreation.
- Pool or datasource parameters requiring restarts/rollouts to change safely.

Advantages include immutability, clean constructor injection, and fewer half-updated states. However, Spring Cloud Context cannot rebind constructor-bound objects, including Java records annotated with `@ConfigurationProperties`. Do not pick a record if the requirement is updating the bean directly via `EnvironmentChangeEvent` rebinding.

### 10.2. Mutable JavaBeans for Rebindable Configuration

For business parameter groups permitted to change at runtime, use JavaBean-style `@ConfigurationProperties`:

```java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Positive;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.business.dynamic-checkout")
@Validated
public class DynamicCheckoutProperties {

    @DecimalMin("0.0")
    private BigDecimal freeShippingThreshold = BigDecimal.ZERO;

    @DecimalMin("0.0")
    @DecimalMax("1.0")
    private BigDecimal maximumDiscountRate = BigDecimal.ZERO;

    @Positive
    private int maximumItemsPerOrder = 20;

    public BigDecimal getFreeShippingThreshold() {
        return freeShippingThreshold;
    }

    public void setFreeShippingThreshold(BigDecimal value) {
        this.freeShippingThreshold = value;
    }

    public BigDecimal getMaximumDiscountRate() {
        return maximumDiscountRate;
    }

    public void setMaximumDiscountRate(BigDecimal value) {
        this.maximumDiscountRate = value;
    }

    public int getMaximumItemsPerOrder() {
        return maximumItemsPerOrder;
    }

    public void setMaximumItemsPerOrder(int value) {
        this.maximumItemsPerOrder = value;
    }
}
```

When the application receives `EnvironmentChangeEvent` for changed keys, Spring Cloud Context can rebind `@ConfigurationProperties` beans in the context. Properties removed from Environment reset to class-level defaults before rebinding per documented behavior.

Rebinding a mutable bean updates fields on the same instance. If another thread reads the object mid-rebind, it can see intermediate state. When a consistent snapshot across a refresh is needed, consider `@RefreshScope` on the policy-consuming bean or an atomic policy-swap design.

### 10.3. `@RefreshScope` Is Not a Solution for Every Configuration

`@RefreshScope` invalidates the cached target bean so a new target is created on next use after refresh. This fits beans needing reinitialization from updated config, while requiring careful attention to lifecycles and held resources.

Do not assume every bean depending on a `@RefreshScope` bean is automatically recreated. If a service already cached values or objects derived from the old policy, it can keep using them. Place the scope on the right bean and test the dependency graph.

Settings such as server ports, database endpoints, certificates, or discovery clients may be unsafe to mutate via simple field rebinding. Some cases require recreating connection pools, closing old connections, updating service registrations, or rolling out new processes. Design the real transition mechanism rather than treating refresh as merely swapping YAML.

## 11. Propagating Changes Across Instances

Spring Cloud Config Client does not automatically poll Config Server for every change by default. With multiple application instances, changing config on the server does not guarantee every JVM received the new values.

A business-parameter change workflow might include:

1. Product/domain owner approves the new policy.
2. Configuration is updated with a version or audit record in a managed source.
3. Clients receive a refresh signal or roll out via deployment strategy.
4. Each instance updates Environment and emits required events.
5. Typed configuration is rebound or refresh-scoped target beans are recreated.
6. Non-sensitive metrics/logs confirm the applied policy version on each instance.

Spring Cloud Bus can broadcast environment-change events across instances. Without Bus, coordinate refreshes via your deployment platform or another event mechanism. Crucially, confirm every instance runs the same policy version before completing rollout.

For financial policies or transaction limits, consider storing `policy-version` and effective timestamps. If a request is in flight when policy changes, decide whether it uses the old or new version. `@RefreshScope` does not solve cross-request or cross-service business consistency on its own.

## 12. Testing Configuration Across Both Groups

Tests must prove proper binding, validation, and change behavior.

### 12.1. Testing Binding

Example using a Spring Boot test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "app.business.checkout.currency-code=VND",
        "app.business.checkout.free-shipping-threshold=500000",
        "app.business.checkout.maximum-discount-rate=0.20",
        "app.business.checkout.maximum-items-per-order=30"
})
class CheckoutPolicyPropertiesTest {

    @Autowired
    CheckoutPolicyProperties properties;

    @Test
    void bindsBusinessPolicyWithExpectedTypes() {
        assertThat(properties.currencyCode()).isEqualTo("VND");
        assertThat(properties.freeShippingThreshold())
                .isEqualByComparingTo("500000");
        assertThat(properties.maximumDiscountRate())
                .isEqualByComparingTo("0.20");
        assertThat(properties.maximumItemsPerOrder()).isEqualTo(30);
    }
}
```

This test verifies properties bind to the expected types and values. A suitable test dependency such as `spring-boot-starter-test` is required.

### 12.2. Testing Validation

Write tests with invalid values—such as `maximum-discount-rate=1.5` or `maximum-items-per-order=0`—and assert that the application context fails to start. This catches misconfiguration in CI rather than waiting until production.

### 12.3. Testing Responsibility Boundaries

Beyond binding tests, verify:

- Changing `pricing-client.base-url` does not alter discount policies.
- Changing `free-shipping-threshold` does not recreate the HTTP connection pool.
- Domain policies can be unit tested without a Spring context.
- Secrets never appear in logs, assertion messages, or test reports.
- When policies refresh, every instance converges on the same policy version after rollout/broadcast completes.

## 13. Observability and Operations

Actuator `configprops` helps inspect `@ConfigurationProperties` beans; the `env` endpoint helps identify property sources. Protect these endpoints with proper authentication, authorization, and exposure policies because metadata or configuration values can be sensitive.

Operational practices:

- Log property source names, active profiles, and policy versions; never log passwords or tokens.
- Distinguish desired configuration in Config Server from effective configuration resolved on each instance.
- Alert when validation or binding failures prevent instances from starting.
- Track infrastructure connectivity failures separately from business policy violations.
- For business parameters, retain change history and approvers in the policy management system.
- For infrastructure changes, track rollouts/restarts and verify connectivity after applying new settings.

## 14. Common Design Mistakes

| Mistake | Consequence | Improvement |
| --- | --- | --- |
| Putting endpoints, timeouts, and discount rates in one `AppProperties` class | Responsibilities and change ownership get tangled | Separate prefixes and typed configuration by group |
| Scattering `@Value` across services | Hard to audit full config; lacks centralized metadata and validation | Group properties with `@ConfigurationProperties` |
| Using `double` for money or financial rates | Floating-point precision errors | Use `BigDecimal` and explicit rounding rules |
| Skipping validation on business parameters | Invalid policies load and run silently | Use Jakarta Validation and enforce domain invariants |
| Committing passwords in `application-prod.yml` to Git | Secret leaks and difficult rotation | Use a secret manager or config tree |
| Assuming Config Server changes auto-reach every instance | Instances run inconsistent policies | Use refresh events, Bus, or controlled rollouts |
| Using records for properties needing Spring Cloud rebinding | Constructor-bound records do not refresh/rebind that way | Use mutable JavaBeans or an appropriate refresh bean design |
| Refreshing all infrastructure settings without checking lifecycles | Clients, pools, or registrations hold stale resources | Classify restart-required vs. runtime-refreshable settings |
| Letting the domain depend directly on `@ConfigurationProperties` | Domain becomes coupled to framework and config sources | Translate to domain policy/value objects in the adapter layer |

## 15. Design Workflow for a New Service

1. List all properties the service uses.
2. Classify each key as infrastructure, business, or secret.
3. Choose prefixes by responsibility and standardize canonical kebab-case names.
4. Pick appropriate data types: `Duration`, `URI`, `BigDecimal`, `int`, enums, or value objects.
5. Group them into independent `@ConfigurationProperties` classes.
6. Add validation for required fields, value domains, and cross-field invariants.
7. Choose immutable records for startup-only config; choose mutable beans when supported rebinding is required.
8. Define config sources, precedence, owners, override permissions, and audit trails.
9. Decouple domain policies from Spring configuration adapters.
10. Test binding, validation, refresh/restart behavior, and verify config per instance.

## 16. Self-Check Questions

1. Why does the pricing service URL belong to infrastructure configuration while the free-shipping threshold is a business parameter?
2. When should you use `@Value` versus `@ConfigurationProperties`?
3. Why should `BigDecimal` be used for monetary amounts and discount rates?
4. At what point do `@Validated` and Jakarta Validation constraints catch configuration errors?
5. Why should domain models avoid depending directly on Spring annotations?
6. How do constructor-bound records differ from JavaBean-style configuration properties in rebinding capability?
7. Why does changing Config Server not guarantee every instance received the updated policy?
8. When should you restart/roll out instead of using `@RefreshScope`?
9. How should versioning and auditing be handled for parameters affecting transactions?

## 17. Official References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — configuration sources, `@ConfigurationProperties`, constructor binding, validation, and property precedence.
- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html) — metadata and IDE support for custom configuration.
- [Spring Cloud Context — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html) — `EnvironmentChangeEvent`, `@ConfigurationProperties` rebinding, `@RefreshScope`, and refresh limitations.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html) — loading configuration from Config Server using Config Data.
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html) — Jakarta Bean Validation integration.

*This document focuses on the boundary between infrastructure configuration and business parameters. Decisions around refresh, restart, access control, and auditing must align with each service's requirements and actual Spring Boot/Spring Cloud versions.*
