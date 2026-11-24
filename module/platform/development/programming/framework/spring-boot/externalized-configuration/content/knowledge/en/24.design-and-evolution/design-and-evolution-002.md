# Choosing Configuration Group Boundaries by Functional Responsibility

## 1. Why Does Configuration Need Architectural Boundaries?

A Spring Boot system might start with a few properties like **app.url**, **app.timeout**, and **app.enabled**. As payment gateway, inventory, email, search, fulfillment, and multiple deployment environments are added, generic names become hard to manage.

For example:

~~~yaml
app:
  url: "https://gateway.example.invalid"
  timeout: 5s
  enabled: true
  retry-count: 3
  stock-threshold: 10
  email-host: "smtp.example.invalid"
  payment-api-key: ""
~~~

Questions that become very hard to answer:

- Is **timeout** for payment, email, or inventory?
- Which feature does **enabled** turn on?
- Who is allowed to adjust timeout without breaking another feature?
- Should payment secrets be passed around inside the same object that holds inventory settings?
- If payment is extracted into an independent module, which keys move with it?
- Why does changing the email provider require re-running payment tests?
- Could a dev environment default accidentally affect production?

Spring Boot provides **@ConfigurationProperties** to group keys sharing a common prefix into typed Java objects, rather than scattering numerous **@Value** annotations across services.

Therefore, how you choose **prefixes**, **configuration classes**, and **nested objects** directly impacts cohesion, coupling, validation, security, testability, and evolvability.

This lesson guides you through designing configuration groups **by functional responsibility**: each group has a clear purpose, consumer, owner, and change rules.

Context: **Spring Boot 3.3.x**, **Java 21**, **Config Data**, **@ConfigurationProperties**, **Bean Validation**, and **Spring Boot Test**. The **example.invalid** domains are for illustration only.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **functional** boundaries from **file**, **profile**, and **environment** boundaries.
2. Choose contextual and stable canonical prefixes.
3. Group properties that share consumers and responsibilities.
4. Separate payment, inventory, and notification groups into independent configuration beans.
5. Decide when to use a nested record versus a separate class.
6. Use Duration, URI, DataSize, enum, and List/Map in line with the contract.
7. Distinguish a genuine shared policy from two subsystems accidentally sharing the same default.
8. Place validation and secret ownership into the right group.
9. Rename prefixes without breaking existing deployments.
10. Test groups independently and check cross-cutting relationships at the owning layer.
11. Avoid a bloated AppProperties as well as pointless micro-splitting of configuration.
12. Design a configuration API that works well for both developers and operators.

## 3. Principle: Group by a Single Reason to Change

A good configuration group typically contains values that:

- Control **the same capability** of the application.
- Are read by a single subsystem or a closely related set of consumers.
- Share the same owner for documentation and changes.
- Are reviewed together when shipping a feature.
- May require validating constraints against one another.
- Can move together with the module if the system is split apart.

For example:

~~~text
shop.checkout.payment.*
    Gateway configuration, retries, timeouts, payment authentication.

shop.inventory.*
    Stock threshold, cache, and inventory synchronization settings.

shop.notification.email.*
    Email provider, sender, timeout, token settings.

shop.search.*
    Search engine, index, batch, cache settings.
~~~

The fields in the payment group clearly belong together functionally, whereas email provider and stock threshold have no reason to live alongside payment.

### 3.1. Cohesion

High cohesion means fields within the same object serve a relatively unified purpose:

~~~yaml
shop:
  checkout:
    payment:
      gateway-url: "https://gateway.example.invalid"
      connect-timeout: 2s
      request-timeout: 8s
      retry:
        max-attempts: 3
        initial-delay: 200ms
~~~

### 3.2. Coupling

Low coupling means `InventoryService` does not have to depend on an object containing payment's API key, URL, or retry policy.

Instead of:

~~~java
public InventoryService(AppProperties everything) {
    this.everything = everything;
}
~~~

prefer:

~~~java
public InventoryService(InventoryProperties properties) {
    this.properties = properties;
}
~~~

Benefit: reduces dependency surface area and lowers the risk of a module accidentally accessing unrelated data.

### 3.3. The Decision Question

Ask: *If this entire capability were replaced with another implementation, which properties should move with it without affecting other features?*

That set is usually a sound boundary for a configuration group.

## 4. The YAML Tree Is Not an Ownership Map

A single **application.yml** file can contain multiple groups:

~~~yaml
spring:
  application:
    name: shop-api

shop:
  checkout:
    payment:
      request-timeout: 8s

  inventory:
    cache-ttl: 45s

  notification:
    email:
      enabled: false
~~~

Even though they all live in one file, you can still create three independent classes:

~~~text
PaymentProperties
InventoryProperties
EmailProperties
~~~

Conversely, keys for a single group can come from multiple sources:

~~~text
application.yml                       -> payment timeout default
application-prod.yml                  -> production payment gateway
Kubernetes Secret/configtree volume   -> payment api-key
command-line                          -> payment retry override
~~~

When Spring Boot binds **@ConfigurationProperties**, it uses the effective values in **Environment** according to source precedence, not just one standalone file.

**File boundaries are a packaging and deployment concern. Functional boundaries are the module's contract with the application.**

## 5. Example Model: shop-api

Suppose an application has these capabilities:

| Capability | Primary Function | Configuration Owner |
| --- | --- | --- |
| Checkout/payment | Send requests to payment gateway | Payment integration |
| Inventory | Read and synchronize stock levels | Inventory module |
| Notification/email | Send emails to customers | Notification module |
| Search | Index and query products | Search module |
| Platform HTTP | Provide shared HTTP client factory | Platform/infrastructure |

A proposed namespace:

~~~text
shop.checkout.payment.gateway-url
shop.checkout.payment.connect-timeout
shop.checkout.payment.request-timeout
shop.checkout.payment.retry.max-attempts
shop.checkout.payment.retry.initial-delay
shop.checkout.payment.api-key

shop.inventory.cache-ttl
shop.inventory.low-stock-threshold
shop.inventory.sync.batch-size
shop.inventory.sync.interval

shop.notification.email.enabled
shop.notification.email.provider-url
shop.notification.email.sender-address
shop.notification.email.request-timeout
shop.notification.email.api-token

shop.search.index-name
shop.search.batch-size
shop.search.cache-ttl
~~~

There is no requirement for every capability to have the same prefix depth. However, **the full name must make clear which subsystem owns the property**.

### 5.1. shop.checkout.payment or shop.payment?

If payment serves only checkout and falls under checkout's ownership, **shop.checkout.payment** expresses that.

If payment is also used for refunds, subscriptions, and multiple other products, **shop.payment** may be a more durable boundary.

Choose names based on **domain language and actual responsibility**, not mechanically from the current Java package structure.

## 6. Seven Criteria for Evaluating a Boundary

### 6.1. Purpose

Do the keys together control a single capability explainable in one short sentence? If you have to say "this is the bucket for things we didn't know where to put", it is likely a poor grouping.

### 6.2. Consumer

Are the keys consumed primarily by a single component or subsystem? If only one service needs payment's timeout and API key, keep them close to payment.

### 6.3. Change Ownership

Who needs to approve a configuration edit? If the payment team modifying a field forces the email module to review it too, the object may hold too many responsibilities.

### 6.4. Deployment Lifecycle

Which fields typically change together with a feature release or operate the same integration? They likely belong in the same group.

### 6.5. Validation

Fields that must be compared against each other, such as **request-timeout > connect-timeout**, generally benefit from residing in the same object.

### 6.6. Security

Do the values share the same sensitivity level and consumer? A payment API key should not travel with every other setting and get injected into modules that do not need it.

### 6.7. Portability

If a module is extracted into a library or microservice, can its configuration model and namespace move relatively independently?

A design rarely optimizes all seven criteria simultaneously. Prioritize the criteria tied to real-world changes and ownership.

## 7. Anti-Pattern 1: AppProperties Containing Everything

Example:

~~~java
package com.example.shop.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String paymentUrl,
        Duration paymentTimeout,
        String paymentApiKey,
        Duration inventoryCacheTtl,
        int inventoryThreshold,
        String emailProviderUrl,
        boolean emailEnabled,
        String emailToken,
        String searchIndex,
        int searchBatchSize) {
}
~~~

This class can still bind, yet causes issues:

1. Needing a single field requires injecting the entire object.
2. Adding features makes the constructor grow endlessly.
3. Validation across multiple modules gets tangled together.
4. A bad email default can break inventory tests.
5. Secrets can be logged by the record's **toString()**.
6. A module cannot be extracted without dragging the shared class along.
7. Ownership disappears under the vague **app** prefix.
8. Metadata and documentation become hard to navigate as field counts grow.

**Fix:** split into PaymentProperties, InventoryProperties, EmailProperties, and SearchProperties with capability-specific prefixes.

## 8. Anti-Pattern 2: One Configuration Bean per Primitive

The other extreme is over-splitting:

~~~text
ConnectTimeoutProperties
ReadTimeoutProperties
RetryEnabledProperties
RetryMaxAttemptsProperties
RetryDelayProperties
~~~

If all belong to one payment client, splitting them leads to:

- Unnecessary beans and constructor parameters.
- Difficulty validating relationships across fields.
- Unclear which group represents a complete capability.
- Fragmented metadata lacking clear structure.
- Operators having to look up many classes to understand a single client.

Usually much better:

~~~text
PaymentProperties
  gatewayUrl
  connectTimeout
  requestTimeout
  Retry retry
    enabled
    maxAttempts
    initialDelay
    maxDelay
~~~

**A good group is not the smallest possible group.** It is narrow enough to have a single responsibility, and wide enough to keep logically coupled fields together.

## 9. PaymentProperties: Boundary of the Payment Integration

Using an immutable Java record:

~~~java
package com.example.shop.payment;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.checkout.payment")
public record PaymentProperties(
        @NotNull URI gatewayUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry,
        String apiKey) {

    public record Retry(
            boolean enabled,
            @Min(1) int maxAttempts,
            @DefaultValue("250ms") Duration initialDelay,
            @DefaultValue("3s") Duration maxDelay) {
    }
}
~~~

Corresponding YAML:

~~~yaml
shop:
  checkout:
    payment:
      gateway-url: "https://gateway.example.invalid"
      connect-timeout: 2s
      request-timeout: 8s
      retry:
        enabled: true
        max-attempts: 3
        initial-delay: 250ms
        max-delay: 3s
~~~

### 9.1. Why Is retry a Nested Object?

The retry fields all belong to a single **payment gateway client** policy, share the same consumer, and often require mutual validation.

Just because the word **retry** appears across multiple modules does not mean you should create a global **shop.retry**. Payment retries and inventory retries can have very different needs.

### 9.2. Why Do Data Types Matter?

- **URI** for `gatewayUrl` avoids manipulating URLs as raw strings.
- **Duration** for timeouts/delays clarifies time units; configs can use **2s**, **250ms**.
- **int** for `maxAttempts` works when a value is always expected, though **Integer @NotNull @Min(1)** can be used if missing must be distinguished from 0.
- **boolean** for `enabled` defaults to false if omitted; document the default rule clearly.

### 9.3. The API Key Belongs to Payment, Not Source Code

The property:

~~~text
shop.checkout.payment.api-key
~~~

names the secret used by `PaymentClient`. Never place real secrets in `application.yml` or Java classes. At runtime it can be supplied via an environment variable:

~~~text
SHOP_CHECKOUT_PAYMENT_APIKEY
~~~

or a configtree file mounted from a secret volume.

**Note:** a record's default `toString` includes its components. Never log the entire `PaymentProperties` when `apiKey` is present.

## 10. InventoryProperties: Independent Ownership

~~~java
package com.example.shop.inventory;

import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.inventory")
public record InventoryProperties(
        @NotNull Duration cacheTtl,
        @Min(0) int lowStockThreshold,
        @Valid @NotNull Sync sync) {

    public record Sync(
            @Min(1) int batchSize,
            @DefaultValue("5m") Duration interval) {
    }
}
~~~

Config:

~~~yaml
shop:
  inventory:
    cache-ttl: 45s
    low-stock-threshold: 10
    sync:
      batch-size: 200
      interval: 5m
~~~

Inventory has its own rules:

- TTL must match inventory data freshness requirements.
- Batch size must be positive.
- Low-stock threshold must be non-negative.
- Sync interval expresses the time between sync runs.

Inventory needs no knowledge of the payment gateway URL, token, or retry policy. That is evidence of a proper boundary.

### 10.1. Should Sync Be Nested or a Separate Bean?

If inventory synchronization is purely an internal mechanism of Inventory, a nested **InventoryProperties.Sync** suffices.

If it becomes a subsystem with its own queue, workers, lifecycle, and operators, consider extracting it into **InventorySyncProperties** with its own prefix, such as **shop.inventory.sync**.

Base the decision on **ownership and lifecycle**, not merely field count.

## 11. EmailProperties: Boundary of the Notification Feature

~~~java
package com.example.shop.notification.email;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Email;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.notification.email")
public record EmailProperties(
        boolean enabled,
        URI providerUrl,
        @Email String senderAddress,
        @DefaultValue("5s") Duration requestTimeout,
        String apiToken) {
}
~~~

Config:

~~~yaml
shop:
  notification:
    email:
      enabled: false
      sender-address: "noreply@example.invalid"
      request-timeout: 5s
~~~

When email is disabled, `providerUrl` and `apiToken` may be unneeded. When enabled, those fields may be required. Constraints depending on `enabled` require a custom class-level validator or an appropriate method.

**Do not slap `@NotNull` unconditionally on the token and break every environment just because the feature is off.** The contract must describe conditions.

### 11.1. Secrets and Ownership

The email provider token belongs under **shop.notification.email.api-token**, yet real security comes from secret managers, runtime read permissions, and no-logging policies. A prefix is not an OS-level security boundary.

## 12. Registering Configuration Properties in Spring Boot 3.3

For constructor-bound records, scanning can be enabled:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan("com.example.shop")
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Or a module can register explicitly:

~~~java
package com.example.shop.payment;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {
}
~~~

### 12.1. When to Choose Scan?

**@ConfigurationPropertiesScan** works well when the application owns all packages and wants automatic discovery of configuration properties classes.

### 12.2. When to Choose EnableConfigurationProperties?

**@EnableConfigurationProperties** suits modular configurations or auto-configurations that want to activate exact types. It lets a module explicitly declare the configuration contract it owns.

### 12.3. Do Not Rely Solely on @Component for Records

A record annotated with **@ConfigurationProperties** does not automatically become a bean without registration. Constructor binding should not be mixed up with ordinary component bean creation and Spring bean injection parameters.

## 13. Services Inject Only the Group They Use

Payment:

~~~java
package com.example.shop.payment;

import java.net.URI;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final PaymentProperties properties;

    public PaymentService(PaymentProperties properties) {
        this.properties = properties;
    }

    public URI gateway() {
        return properties.gatewayUrl();
    }
}
~~~

Inventory:

~~~java
package com.example.shop.inventory;

import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final InventoryProperties properties;

    public InventoryService(InventoryProperties properties) {
        this.properties = properties;
    }

    public Duration cacheTtl() {
        return properties.cacheTtl();
    }
}
~~~

Notification:

~~~java
package com.example.shop.notification.email;

import org.springframework.stereotype.Service;

@Service
public class EmailSender {

    private final EmailProperties properties;

    public EmailSender(EmailProperties properties) {
        this.properties = properties;
    }

    public boolean enabled() {
        return properties.enabled();
    }
}
~~~

There is no need to inject **AppProperties everything**. If checkout orchestration uses both payment and inventory, it should normally inject **PaymentService** and **InventoryService**, rather than reaching into internal configuration of both modules to perform their business logic for them.

## 14. Configuration Models Are Not Services

An anti-pattern:

~~~java
@ConfigurationProperties(prefix = "shop.checkout.payment")
public class PaymentProperties {
    private final PaymentClient client;

    public PaymentProperties(PaymentClient client) {
        this.client = client;
    }
}
~~~

The configuration class is requesting a runtime service as a dependency; those are two separate responsibilities.

Layer them cleanly:

~~~text
Environment and PropertySources
            |
            v
       PaymentProperties
            |
            v
      @Bean PaymentClient
            |
            v
        PaymentService
~~~

Per Spring Boot guidance, configuration properties classes should primarily work with `Environment` and avoid injecting other beans.

Factory example:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentClientConfiguration {

    @Bean
    public PaymentClient paymentClient(
            PaymentProperties properties) {

        return new PaymentClient(
                properties.gatewayUrl(),
                properties.connectTimeout(),
                properties.requestTimeout());
    }
}
~~~

**`PaymentClient` here is an application-defined hypothetical type**, not a built-in Spring Boot API. The example simply demonstrates proper wiring placement.

## 15. Framework Properties Differ from Custom Properties

Spring Boot already provides standard namespaces:

~~~text
spring.datasource.*
spring.kafka.*
spring.mail.*
server.*
management.*
logging.*
~~~

If the framework already supports a property you need, usually use the standard key directly.

For example:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
~~~

is understood by Spring Boot's `DataSource` auto-configuration. Renaming it yourself to:

~~~properties
shop.database.url=jdbc:postgresql://localhost:5432/shop
~~~

does not make Spring Boot automatically forward it to **spring.datasource.url** without explicit bridging logic.

Conversely, a custom payment SDK's URL and retry policy have no built-in framework keys; the **shop.checkout.payment** namespace makes full sense.

### 15.1. Do Not Gratuitously Wrap All Framework Keys

Creating **shop.platform.database.url** solely to forward to **spring.datasource.url** adds a second contract to document, test, and migrate.

Such an abstraction should exist only when genuinely required—for example, when a platform provides one stable configuration API across diverse runtimes.

## 16. Nested Group or Separate Bean?

A nested group fits when:

- It exists solely to serve the parent.
- It has the same consumer and the same owner.
- It is usually configured and validated alongside the parent.
- It does not need to be injected directly in many places.
- It has a clear internal group name: retry, pool, tls, circuit-breaker.

For example:

~~~text
shop.checkout.payment.retry.*
~~~

is a nested **PaymentProperties.Retry**.

A separate bean fits when:

- The subsystem has an independent owner or lifecycle.
- Multiple consumers need that specific group, not the parent.
- It may be deployed or extracted as a separate module.
- It has its own validation, config API, and documentation.
- It is used across more use cases than the parent.

For example, **shop.notification.email** can cleanly be a dedicated **EmailProperties**, even though the prefix tree has multiple levels.

### 16.1. @NestedConfigurationProperty

Spring Boot provides **@NestedConfigurationProperty** to help the **configuration metadata processor** recognize a field or record component as a nested type when hints are needed.

**This annotation does not alter binding behavior.** Do not expect adding it to create beans, trigger nested validation, or fix prefix errors.

For nested validation, use **@Valid** per Jakarta Bean Validation; for registration, use appropriate scanning or enabling.

## 17. Shared Defaults Do Not Mean Shared Ownership

Suppose both payment and inventory use a 10s default timeout.

A hasty design:

~~~yaml
shop:
  common:
    timeout: 10s
~~~

and both read **shop.common.timeout**.

Problem: if payment later needs a shorter timeout while inventory needs a longer one, one change impacts both.

**Coincidental identical values today do not prove two subsystems share a single policy.**

Separate them:

~~~yaml
shop:
  checkout:
    payment:
      request-timeout: 10s

  inventory:
    remote-request-timeout: 10s
~~~

If values diverge later, the two modules remain independent.

### 17.1. When Is a Shared Group Appropriate?

If the platform provides **a shared HTTP client factory** where every subsystem genuinely follows one policy:

~~~text
shop.platform.outbound-http.default-connect-timeout
shop.platform.outbound-http.default-max-connections
~~~

then this is a boundary with a real owner: **platform HTTP infrastructure**.

Functional groups can opt into the shared default and override locally when needed.

### 17.2. Placeholders to Share Defaults

For example:

~~~yaml
shop:
  platform:
    outbound-http:
      default-connect-timeout: 2s

  checkout:
    payment:
      connect-timeout: "${shop.platform.outbound-http.default-connect-timeout:2s}"

  inventory:
    remote-connect-timeout: "${shop.platform.outbound-http.default-connect-timeout:2s}"
~~~

Each subsystem retains its own key while referencing the platform default.

However, avoid deeply nested placeholders that obscure the origin of values. Use only when a shared policy is explicitly governed.

### 17.3. Reusing a Java Type Without Sharing Values

You can reuse:

~~~java
public record RetryOptions(
        int maxAttempts,
        Duration initialDelay,
        Duration maxDelay) {
}
~~~

across multiple modules, while each module still binds values from its own prefix.

**Shared structure** is different from **shared configuration instance**.

## 18. Secrets Follow Functional Boundaries, Yet Must Be Protected at Runtime

Property names such as:

~~~text
shop.checkout.payment.api-key
shop.notification.email.api-token
shop.inventory.supplier.password
~~~

indicate each secret's consumer. However, **a prefix is not a security boundary**: if all objects live in the same process and can read `Environment`, another module could still access the secret.

Protect secrets via:

- Secret manager or container secret volumes.
- Least-privilege workload identity.
- RBAC and filesystem permissions.
- Never committing secret values to Git, JARs, or images.
- Never logging `Environment` or `toString` of records containing tokens.
- Rotation and revocation.
- Isolating service identities or processes when strong isolation is required.

Runtime env example:

~~~text
SHOP_CHECKOUT_PAYMENT_APIKEY=<runtime-secret>
~~~

Or configtree:

~~~text
/etc/shop-secrets/shop.checkout.payment.api-key
~~~

and:

~~~properties
spring.config.import=configtree:/etc/shop-secrets/
~~~

**configtree** is a mechanism for loading data from files named after property keys; it does not automatically encrypt or manage secret lifecycles.

## 19. Validation Belongs with the Module Owning the Rule

Payment may require:

~~~text
request-timeout > connect-timeout
retry.max-attempts >= 1
retry.initial-delay <= retry.max-delay
api-key required when live-mode is enabled
~~~

Inventory:

~~~text
cache-ttl > 0
low-stock-threshold >= 0
sync.batch-size >= 1
sync.interval > 0
~~~

Email:

~~~text
enabled=false -> provider-url and api-token may be absent
enabled=true  -> provider-url and api-token required
~~~

These are distinct contracts; there is no need for a giant **GlobalPropertiesValidator** that knows every subsystem.

### 19.1. @Validated and @Valid

Spring Boot can trigger Jakarta Bean Validation on **@ConfigurationProperties** annotated with **@Validated** when a compatible implementation is present.

~~~java
@Validated
@ConfigurationProperties(prefix = "shop.inventory")
public record InventoryProperties(
        @NotNull Duration cacheTtl,
        @Valid @NotNull Sync sync) {

    public record Sync(
            @Min(1) int batchSize) {
    }
}
~~~

When validation is needed, add **spring-boot-starter-validation**.

### 19.2. Cross-Field Validation

Two individually valid `Duration` values do not prove their relationship is valid. For example:

~~~text
connect-timeout=8s
request-timeout=3s
~~~

If the actual payment client enforces **requestTimeout > connectTimeout**, you can write a class-level constraint using **@Constraint** and **ConstraintValidator**, or **@AssertTrue** on an appropriate boolean getter.

Apply the rule only when the underlying library's contract actually requires it; not all HTTP clients define request and connect timeouts identically.

## 20. Cross-Module Relationships Belong in the Orchestration Layer

Suppose checkout has an overall processing budget:

~~~text
shop.checkout.total-timeout
shop.checkout.payment.request-timeout
shop.inventory.remote-request-timeout
~~~

A rule may require **checkout total timeout** to accommodate sequential steps in the order flow.

Who owns this rule? Neither payment nor inventory alone. It belongs to **checkout orchestration**.

You can have a startup guard:

~~~java
@Component
public class CheckoutConfigurationGuard {

    public CheckoutConfigurationGuard(
            CheckoutProperties checkout,
            PaymentProperties payment,
            InventoryProperties inventory) {

        // Compare bound Duration values.
        // If total duration is inconsistent, fail startup.
    }
}
~~~

This is a sketch, not a complete validator. `CheckoutProperties` must be defined and registered appropriately.

Design point: **do not inject `InventoryProperties` into `PaymentProperties`** just to validate a relationship outside payment's responsibility.

Guards or orchestration validation must run at a lifecycle phase ensuring dependent components have not yet acted on invalid configuration. Do not rely on accidental singleton initialization order.

## 21. Naming Rules for Prefixes and Fields

Best practices:

- **lowercase kebab-case** for canonical names.
- Prefixes express domain/capability, not just "config".
- Field names express meaning, units, and consumer.
- Do not embed environment names in keys when profile/source overrides can be used.
- Avoid team or individual names as namespaces if organizations may change.
- Keep domain vocabulary consistent.
- Treat prefixes as an API for developers, operators, and deployment scripts.

Good names:

~~~text
shop.checkout.payment.request-timeout
shop.checkout.payment.retry.max-attempts
shop.inventory.low-stock-threshold
shop.notification.email.sender-address
~~~

Confusing names:

~~~text
app.timeout
app.flag1
app.common.password
app.config.settings.value
app.prod.gateway-host
~~~

### 21.1. Environment Variables

Under Spring Boot's environment variable rules:

1. Dot **.** → underscore **_**.
2. Hyphen **-** → removed.
3. Letters → uppercase.

For example:

~~~text
shop.checkout.payment.gateway-url
    -> SHOP_CHECKOUT_PAYMENT_GATEWAYURL

shop.inventory.low-stock-threshold
    -> SHOP_INVENTORY_LOWSTOCKTHRESHOLD

shop.notification.email.sender-address
    -> SHOP_NOTIFICATION_EMAIL_SENDERADDRESS
~~~

Do not assume every kebab-case segment needs an underscore between words. The standard rule is **remove hyphens**.

### 21.2. Root Names Should Not Be Too Generic

If an application or library is embedded inside a larger host, an overly generic **app** prefix can cause collisions. A namespace like **shop** or **acme.payment** is more resilient across multiple modules/starters.

## 22. List, Map, and Config Structure Are Also Responsibility Decisions

Payment has regional routing.

If order matters:

~~~yaml
shop:
  checkout:
    payment:
      gateways:
        - region: asia
          url: "https://asia.example.invalid"
        - region: europe
          url: "https://europe.example.invalid"
~~~

**List<Gateway>** fits well.

If region names are identifying lookup keys:

~~~yaml
shop:
  checkout:
    payment:
      gateways:
        asia:
          url: "https://asia.example.invalid"
        europe:
          url: "https://europe.example.invalid"
~~~

**Map<String, Gateway>** may be better.

Questions:

- Does ordering affect processing?
- Are keys stable?
- Do individual entries need environment-specific overrides?
- Is uniqueness required?
- Are there many dynamic entries whose count is unknown upfront?

In Spring Boot, **a higher-priority List replaces the entire list** rather than merging elements piecemeal. Maps have different binding rules. Thus data-shape choices affect how operators supply overrides.

Whether List or Map, payment gateway routes remain **payment's** responsibility, not a global group.

## 23. Property Prefixes Are External Configuration APIs

The key:

~~~text
shop.checkout.payment.gateway-url
~~~

may appear in:

- application.yml / application-prod.yml.
- Docker Compose environment.
- Kubernetes ConfigMaps and Secret file names.
- Helm templates/values.
- Terraform/deployment scripts.
- CI/CD variables.
- Test fixtures.
- Operations documentation.

Changing a prefix affects many places outside Java source. **A successful compile does not prove deployments have migrated.**

### 23.1. Renaming a Class Differs from Renaming a Prefix

Renaming a Java class:

~~~text
PaymentProperties -> PaymentGatewayProperties
~~~

while keeping:

~~~java
@ConfigurationProperties(prefix = "shop.checkout.payment")
~~~

usually affects external configs far less than changing the prefix to **shop.integrations.gateway**.

The class name is a Java API; the prefix is a deployment API. Both must be managed with their respective consumers in mind.

## 24. Refactoring a Legacy Configuration Group

Suppose the legacy version had:

~~~properties
app.payment-url=https://gateway.example.invalid
app.payment-timeout=8s
app.payment-retry-count=3
app.inventory-ttl=45s
app.email-enabled=true
~~~

And you want to move to:

~~~properties
shop.checkout.payment.gateway-url=https://gateway.example.invalid
shop.checkout.payment.request-timeout=8s
shop.checkout.payment.retry.max-attempts=3
shop.inventory.cache-ttl=45s
shop.notification.email.enabled=true
~~~

This is a valuable refactor, yet risks breaking backward compatibility.

### 24.1. Relaxed Binding Does Not Create Semantic Aliases

Spring Boot supports equivalent spelling variants in relaxed binding, yet **app.payment-timeout** is not automatically an alias for **shop.checkout.payment.request-timeout**.

The two keys have different namespaces and meanings. A real migration is required.

### 24.2. Migration Plan

1. Inventory every use of the old keys in deployments and tests.
2. Publish the new keys and old → new mapping.
3. Define the support window for old keys.
4. If concurrent support is required, design a compatibility adapter or migration layer.
5. Specify **which key wins when both old and new are present**.
6. Emit deprecation warnings without exposing secret values.
7. Update ConfigMaps, Helm, env, and docs.
8. Test old-only, new-only, both, and neither.
9. After the window ends, remove old keys with proper notice.

### 24.3. Compatibility Helper Example

~~~java
package com.example.shop.migration;

import java.time.Duration;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public final class TimeoutCompatibility {

    private TimeoutCompatibility() {
    }

    public static Duration resolve(Environment env) {
        Binder binder = Binder.get(env);

        Duration modern = binder.bind(
                "shop.checkout.payment.request-timeout",
                Duration.class).orElse(null);

        if (modern != null) {
            return modern;
        }

        return binder.bind(
                "app.payment-timeout",
                Duration.class).orElse(Duration.ofSeconds(8));
    }
}
~~~

This helper illustrates a **migration idea**; it does not mutate an already bound `PaymentProperties` object. It needs explicit integration with client creation or a suitable configuration factory.

### 24.4. @DeprecatedConfigurationProperty Is Not a Runtime Alias

Spring Boot provides **@DeprecatedConfigurationProperty** and configuration metadata to inform tooling that an old property is deprecated.

**Metadata does not automatically rewrite old keys into new keys** when `Binder` runs. If runtime support for old names is still needed, build a dedicated compatibility mechanism.

## 25. A Default May Belong to Framework, Platform, or Module

Distinguish three layers:

**Framework default:** Spring Boot already supplies defaults for certain **server.*** and **spring.*** keys.

**Platform policy:** the organization defines default timeouts for a shared HTTP client factory.

**Module default:** payment defines its own retry/backoff, and inventory defines its cache TTL.

Do not copy framework defaults into a **GlobalApplicationDefaults** without a real reason.

### 25.1. @DefaultValue

With constructor binding/records, you can use:

~~~java
@ConfigurationProperties(prefix = "shop.inventory")
public record InventoryOptions(
        @DefaultValue("30s") Duration cacheTtl,
        @DefaultValue("10") int lowStockThreshold) {
}
~~~

This default belongs to the **configuration object** and does not automatically become a new property inside `Environment`.

If operators should see defaults directly in Config Data, document them in `application.yml`. Pick one clear strategy and avoid conflicting defaults.

### 25.2. Avoid Dangerous Defaults

If payment live mode requires an API key, never set **api-key=changeme** so every environment starts. Fail fast if required credentials are missing.

## 26. Which Capability Do Feature Flags Belong To?

For example:

~~~text
shop.notification.email.enabled
shop.checkout.payment.retry.enabled
shop.search.indexing.enabled
~~~

An **enabled** field makes sense within its own group.

Do not lump them into:

~~~text
app.flags.email
app.flags.payment-retry
app.flags.indexing
~~~

just because they are all booleans—unless the application genuinely has an independent **feature flag platform** managing the lifecycle, auditing, and rollout of all flags.

**Sharing a data type is not sharing a functional responsibility.**

### 26.1. @ConditionalOnProperty

~~~java
@ConditionalOnProperty(
        prefix = "shop.notification.email",
        name = "enabled",
        havingValue = "true")
~~~

is used for conditional bean registration.

Note: this condition reads `Environment`; it does not know defaults inside Java records. If `enabled` should default to true, use **matchIfMissing** appropriately or declare the default in Config Data.

## 27. Configuration Metadata Helps Discover Boundaries

Spring Boot can generate metadata for **@ConfigurationProperties** types, enabling IDE completion and property descriptions.

Gradle:

~~~groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Tooling can then surface:

~~~text
shop.checkout.payment.gateway-url     URI
shop.checkout.payment.request-timeout  Duration
shop.inventory.cache-ttl               Duration
shop.notification.email.enabled        boolean
~~~

When groups are well-designed by capability, metadata is much easier to read.

**@NestedConfigurationProperty** can hint the metadata processor when certain nested types are not automatically inferred; it does not affect binding.

Metadata also does not replace validation, runtime aliases, or secret management.

## 28. Independent Testing with ApplicationContextRunner

Clean boundaries allow testing one group without booting the entire application.

Example for `InventoryProperties`:

~~~java
package com.example.shop.inventory;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(InventoryProperties.class)
    static class TestConfig {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfig.class);

    @Test
    void bindsInventoryGroup() {
        runner.withPropertyValues(
                "shop.inventory.cache-ttl=30s",
                "shop.inventory.low-stock-threshold=5",
                "shop.inventory.sync.batch-size=100",
                "shop.inventory.sync.interval=2m"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            InventoryProperties p =
                    context.getBean(InventoryProperties.class);

            assertThat(p.cacheTtl())
                    .isEqualTo(Duration.ofSeconds(30));
            assertThat(p.lowStockThreshold()).isEqualTo(5);
            assertThat(p.sync().batchSize()).isEqualTo(100);
            assertThat(p.sync().interval())
                    .isEqualTo(Duration.ofMinutes(2));
        });
    }
}
~~~

This test needs no payment token or email provider, and connects to no external service. It proves `InventoryProperties` binding alone.

### 28.1. Testing PaymentProperties Separately

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
static class PaymentTestConfig {
}
~~~

Runner:

~~~java
new ApplicationContextRunner()
    .withUserConfiguration(PaymentTestConfig.class)
    .withPropertyValues(
        "shop.checkout.payment.gateway-url=https://test.example.invalid",
        "shop.checkout.payment.connect-timeout=1s",
        "shop.checkout.payment.request-timeout=4s",
        "shop.checkout.payment.retry.enabled=true",
        "shop.checkout.payment.retry.max-attempts=2",
        "shop.checkout.payment.retry.initial-delay=100ms",
        "shop.checkout.payment.retry.max-delay=1s")
    .run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).hasSingleBean(PaymentProperties.class);
    });
~~~

This verifies the group without hitting a real gateway.

### 28.2. Validation Tests

If a group uses **@Validated** and Jakarta constraints, ensure **spring-boot-starter-validation** and its infrastructure are present in the test context.

Test:

- Missing required fields.
- Unconvertible `Duration` or integer values.
- Constraints such as `maxAttempts >= 1`.
- Nested validation via **@Valid**.
- Condition where `enabled=true` requires credentials.
- Timeout/delay relationships if a validator is implemented.
- Env/profile sources in integration tests when proving runtime overrides.

`ApplicationContextRunner` excels at testing binding with **withPropertyValues**, yet does not replace full `SpringApplication` Config Data bootstrap by default.

## 29. Testing Cross-Group Isolation

Useful architectural assertions:

~~~text
Payment:
  request-timeout = 3s

Inventory:
  remote-request-timeout = 20s

Expectation:
  PaymentClient uses 3s
  InventoryClient uses 20s
~~~

If changing payment's timeout causes `InventoryClient` to change timeout, you may have introduced coupling through a global default, bound the wrong key, or misapplied a policy in a client factory.

Consider adding:

- Architecture tests on package dependencies.
- Integration tests for configuration wiring.
- Tests when renaming a prefix.
- Old/new key migration tests.
- Profile and env override tests.
- Tests asserting secrets are not logged.

**Green tests verify the specified behavior**, not that architectural boundaries are perfect. Ownership decisions still require team alignment.

## 30. When a Module Becomes a Library or Starter

A public library might use the namespace:

~~~text
acme.payments.gateway-url
acme.payments.request-timeout
acme.payments.retry.max-attempts
~~~

A prefix carrying the capability or vendor name prevents collisions when multiple libraries coexist in one app.

The module can register the type via:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AcmePaymentProperties.class)
public class AcmePaymentConfiguration {
}
~~~

In a Spring Boot starter, standard Spring Boot 3.x auto-configuration requires **@AutoConfiguration** and registering the class in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The `@Configuration` snippet above only illustrates registration, not a starter's full auto-configuration code.

### 30.1. Public Config Is an API That Needs Stability

A prefix consumed by dozens of applications is far harder to change than an internal prefix. Publish deprecations, defaults, units, validation, and migration paths when renaming.

### 30.2. Do Not Expose Implementation Details

A name like:

~~~text
acme.payment.okhttp3.internal-worker-threads
~~~

couples the public API to a specific HTTP library. Better to expose operator-meaningful behavior, such as **max-connections** if that is truly a parameter users need.

## 31. When a Capability Has Multiple Providers

For example, payment has primary and backup providers:

~~~yaml
shop:
  checkout:
    payment:
      providers:
        primary:
          base-url: "https://primary.example.invalid"
          connect-timeout: 2s
        backup:
          base-url: "https://backup.example.invalid"
          connect-timeout: 3s
      failover:
        enabled: true
        max-switches: 1
~~~

Keeping them nested under payment makes sense if:

- The same payment team manages them.
- Failover policy needs visibility into both providers.
- They both serve the single payment capability.
- Unrelated modules never need provider configs injected.

If providers are independent integrations shared across multiple domains, consider giving them their own group.

If the provider list varies, a `Map` keyed by provider name may fit better than fixed `primary`/`backup` fields, provided fallback ordering and constraints are defined.

## 32. Field Names Can Repeat Across Groups

This is completely normal:

~~~text
shop.checkout.payment.enabled
shop.notification.email.enabled

shop.checkout.payment.request-timeout
shop.notification.email.request-timeout
~~~

There is no conflict because the prefix supplies context.

Inside `EmailProperties`, the field **enabled** is clearer than **shopNotificationEmailEnabled**. However, if a single group has multiple timeout types, name them specifically:

~~~text
connect-timeout
read-timeout
request-timeout
idle-timeout
~~~

An overly generic **timeout** in a multi-stage group invites confusion.

## 33. Signs a Boundary Needs Adjustment

Consider refactoring when:

1. One config bean is injected across many unrelated modules.
2. A class holds dozens of fields spanning multiple capabilities.
3. One team editing a property repeatedly breaks another team's tests.
4. Payment secrets are passed around widely just because an object holds everything.
5. A nested group acquires its own owner, consumers, and lifecycle.
6. A module is about to be extracted into an independent service or library.
7. Provider-specific rules make the current object overly complex.
8. The prefix no longer reflects the domain language.
9. Deployment scripts struggle to tell which feature owns a key.
10. Nobody has clear responsibility for a configuration group.
11. Validation has to inspect a large number of unrelated fields.
12. Rolling back one feature forces rolling back configs of other features.

Do not refactor just because a class exceeds an arbitrary field count. If all fields share one responsibility and a clear contract, a relatively large class can still be sound.

## 34. Documentation Template for a Configuration Boundary

**Group name:** shop.checkout.payment

**Owner:** Payment Integration

**Purpose:** controls how the application calls the payment gateway.

**Contract:**

| Key | Type | Suggested Default | Required? |
| --- | --- | --- | --- |
| gateway-url | URI | None | Yes when live |
| connect-timeout | Duration | 2s | Yes/default |
| request-timeout | Duration | 8s | Yes/default |
| retry.enabled | boolean | true | Yes/default |
| retry.max-attempts | int | 3 | Yes/default |
| retry.initial-delay | Duration | 250ms | Yes/default |
| retry.max-delay | Duration | 3s | Yes/default |
| api-key | secret/String | None | Yes when live |

**Override sources:** Config Data, profiles, OS env, system properties, and CLI per Spring Boot rules.

**Validation:** valid timeouts and retries; endpoint and key required when live.

**Security:** token comes from a runtime secret source; never logged.

**Versioning:** list of legacy keys and migration plan if applicable.

A table like this lets operators use the contract without reading the implementation class.

## 35. Exercise A — Classifying Keys by Responsibility

Given:

~~~text
app.url
app.payment-timeout
app.payment-api-key
app.inventory-cache-ttl
app.inventory-batch
app.email-enabled
app.email-token
app.low-stock-threshold
~~~

Do the following:

1. Identify the consumer of each key.
2. Identify the owner and change frequency.
3. Group payment, inventory, and email.
4. Propose new prefixes.
5. Flag secrets.
6. Specify types and units.
7. Explain why a single `AppProperties` should not be used.

Example result:

~~~text
shop.checkout.payment.gateway-url
shop.checkout.payment.request-timeout
shop.checkout.payment.api-key

shop.inventory.cache-ttl
shop.inventory.sync.batch-size
shop.inventory.low-stock-threshold

shop.notification.email.enabled
shop.notification.email.api-token
~~~

## 36. Exercise B — Splitting a Large AppProperties

1. Create `AppProperties` containing the example keys.
2. Create `PaymentProperties`, `InventoryProperties`, and `EmailProperties`.
3. Move fields into their appropriate types.
4. Register via `@ConfigurationPropertiesScan`.
5. Update service constructors to inject only the needed group.
6. Add Bean Validation for independent constraints.
7. Test binding for each group.
8. Verify records containing secrets are not logged.

**Goal:** observe architectural benefits beyond merely reorganizing YAML.

## 37. Exercise C — Nested or Independent Bean?

Evaluate:

~~~text
payment.retry.*
payment.fraud-detection.*
notification.email.*
~~~

Determine:

- Is retry strictly part of the payment client?
- Does fraud detection have an independent owner and lifecycle?
- Is email used in flows outside checkout?
- Which values typically change together at deployment?

A reasonable outcome:

- **payment.retry** nested inside `PaymentProperties`.
- **payment.fraud-detection** as a separate bean if it is truly an independent subsystem.
- **notification.email** as its own `EmailProperties`.

## 38. Exercise D — Shared Default and Per-Module Overrides

1. Create a default connect timeout owned by the platform HTTP factory.
2. Keep separate timeout keys for Payment and Inventory.
3. Allow falling back to the platform default when no override is supplied.
4. Change payment's timeout while keeping inventory unchanged.
5. Test both clients together.

**Goal:** avoid turning matching default values into tight coupling.

## 39. Exercise E — Prefix Migration

1. Migrate **app.payment-timeout** to **shop.checkout.payment.request-timeout**.
2. List affected files and manifests.
3. Define old/new precedence.
4. Write a compatibility layer if both must be supported.
5. Test old-only, new-only, both, and neither.
6. Add deprecation metadata where appropriate.
7. Document the sunset schedule for the old key.

**Goal:** treat property names as a public external contract.

## 40. Exercise F — Testing by Module

1. Use `ApplicationContextRunner` for `InventoryProperties`.
2. Supply only inventory keys.
3. Assert `Duration` and `int` conversions.
4. Create a separate runner for `PaymentProperties`.
5. Test missing required properties and constraint violations.
6. Verify inventory tests need no payment token.
7. Add integration wiring tests if needed.

**Goal:** minimize test setup when modules are genuinely independent.

## 41. Checklist for Designing a New Boundary

Before adding or modifying a configuration group:

- Does the group have a clear capability or technical responsibility?
- Who owns the keys?
- Which consumers need this group?
- Do these fields change together?
- Do the fields have cross-field validation?
- Are unrelated fields lumped in simply because they share a file?
- Are you creating an overly tiny bean for a single primitive?
- Does a nested group share the parent's lifecycle?
- Does the prefix reflect stable domain vocabulary?
- Should a standard framework key be used instead of a custom key?
- Do Duration/URI/DataSize/enum fields have accurate types?
- Do key names clarify units and timeout semantics?
- Are defaults safe across environments?
- When a feature is disabled, may some fields be absent?
- Are there secrets, and which runtime source supplies them?
- Is any module injecting an object with secrets unnecessarily?
- Does validation live with the rule's owner?
- Are cross-module relationships checked at the orchestration layer?
- Is there an oversized global `AppProperties`?
- Is a shared default merely a coincidence today?
- Do List/Map fields need override behavior considered?
- Are keys referenced in Helm, CI, Terraform, or ConfigMaps?
- If renaming keys, is there a migration plan?
- Are configuration metadata and documentation complete?
- Are there independent binding/validation tests per group?
- Are there integration tests for profile/env/runtime secret values?

## 42. Summary

- Choosing **configuration group boundaries by functional responsibility** delivers high cohesion, low coupling, and clear ownership.
- **@ConfigurationProperties** binds a namespace into typed, validated Java objects.
- **Files and environments are not functional boundaries**; a single group can receive values from multiple `PropertySources`.
- Avoid a catch-all **AppProperties**, and avoid splitting every primitive into its own bean unnecessarily.
- Nested records suit sub-groups that exist only inside a parent, while independent capabilities deserve separate configuration beans.
- Matching defaults do not justify sharing a property key; share keys only when a real policy owner exists.
- Secret keys live under their consumer's namespace, while actual security rests on runtime and secret infrastructure.
- Validation belongs in the module owning the rule; cross-module rules belong in the orchestration layer.
- A prefix is an **external configuration API** relied upon by deployments; renames require a migration plan and tests.
- Relaxed binding supports spelling variants, **not automatic aliasing of differently named keys**.
- Configuration metadata aids IDEs and docs; it does not replace runtime validation or compatibility.
- Well-designed groups can be tested and moved alongside their modules, supporting long-term evolution.

## Official References

- Spring Boot 3.3 — Externalized Configuration, Type-safe Configuration Properties, Relaxed Binding, and Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata/index.html
- Spring Boot 3.3 API — NestedConfigurationProperty: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/NestedConfigurationProperty.html
- Spring Boot 3.3 — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Framework — Environment Abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
