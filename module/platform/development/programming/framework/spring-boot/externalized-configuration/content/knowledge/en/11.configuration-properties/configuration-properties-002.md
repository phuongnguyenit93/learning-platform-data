# Designing Functional-Domain Prefixes and Standard Naming Conventions

## 1. Why Design Prefixes Intentionally?

Spring Boot separates configuration from source code while mapping external properties into Java objects via **@ConfigurationProperties**. However, type-safe mapping solves only half the problem. The other half is **designing configuration names and boundaries so they are easy to understand, conflict-free, and stable across deployments**.

In a small application, keys like **app.url**, **app.timeout**, and **app.enabled** might seem convenient. Once the application has payments, shipping, email, search, and multiple external integrations, these names become ambiguous: which service's URL? Request timeout or connect timeout? Which feature is enabled?

A more manageable structure:

~~~text
shop.checkout.payment.base-url
shop.checkout.payment.connect-timeout
shop.checkout.payment.retry.max-attempts
shop.checkout.shipping.provider-url
shop.checkout.shipping.request-timeout
shop.notifications.email.enabled
shop.catalog.search.default-page-size
~~~

This lesson explains:

- What a prefix represents and how it relates to business domains.
- Rules for **lowercase kebab-case**, dots **.**, dashes **-**, and canonical names.
- When to split a group into a separate **@ConfigurationProperties** class versus using a nested object.
- How names in YAML, **.properties**, Java, and environment variables map to each other.
- How to register types, validation, metadata, testing, and manage compatibility during renames.
- Common mistakes when designing prefixes and how to avoid them.

Examples are based on **Spring Boot 3.3.x** and Java 21. Addresses using **example.invalid** are for illustration only, not real services.

## 2. Prefixes, Segments, and Field Names

Example property path:

~~~text
shop.checkout.payment.connect-timeout
|-------------------| |-------------|
        prefix          field name
~~~

Configuration class:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop.checkout.payment")
public record PaymentProperties(Duration connectTimeout) {
}
~~~

When this class is properly registered, Spring Boot binds the key **shop.checkout.payment.connect-timeout** to the Java field **connectTimeout**.

Meaning of the components:

| Component | Role |
| --- | --- |
| **shop** | Root namespace of the application or system |
| **checkout** | Order checkout business domain |
| **payment** | Payment integration configuration group |
| **connect-timeout** | Specific property, bindable to **Duration** |

A **prefix** does not have to match the Java package name, Gradle module name, or class name. It is part of the **external configuration interface** shared by operators, CI/CD pipelines, and deployment manifests.

If you later move the package from **com.example.shop.payment** to **com.example.payments**, you do not necessarily have to change the prefix; renaming configuration keys can break existing environment variables and config files in use.

## 3. Canonical Rule: Lowercase Kebab-Case

Spring Boot recommends writing keys in **.properties** and YAML files in **lowercase kebab-case**. For the **prefix** value in the **@ConfigurationProperties** annotation, names **must** follow kebab-case: lowercase letters with **-** separating words within the same segment.

Valid prefix examples:

~~~java
@ConfigurationProperties(prefix = "shop.checkout.payment")
@ConfigurationProperties(prefix = "shop.order-processing")
@ConfigurationProperties(prefix = "my.main-project.person")
~~~

Distinction:

- Dots **.** separate **hierarchy levels** of a property path.
- Dashes **-** separate **words within one level**.
- Lowercase makes canonical names stable and easy to search.
- Java camelCase remains appropriate for **Java field names**, thanks to the Binder's relaxed binding mechanism.

Names to avoid as prefixes:

~~~text
Shop.Checkout.Payment       -- uppercase letters
shop.checkoutPayment       -- camelCase in prefix
shop_checkout_payment      -- not separated into hierarchy by dots
shop.PaymentGateway        -- uppercase and camelCase
~~~

Change to one of these two forms depending on meaning:

~~~text
shop.checkout-payment      -- single segment checkout-payment
shop.checkout.payment      -- two segments checkout and payment
~~~

**Dots and dashes are not arbitrarily interchangeable.** **order-processing** is one concept in a single segment, whereas **order.processing** represents a different hierarchical structure.

### 3.1. Table of Standard Naming Examples

| Purpose | Canonical Property | Java Field |
| --- | --- | --- |
| Payment URL | **shop.checkout.payment.base-url** | **baseUrl** |
| Connection timeout | **shop.checkout.payment.connect-timeout** | **connectTimeout** |
| Retry count | **shop.checkout.payment.retry.max-attempts** | **maxAttempts** |
| Shipping enabled flag | **shop.checkout.shipping.enabled** | **enabled** |
| Request timeout | **shop.checkout.shipping.request-timeout** | **requestTimeout** |
| Search page size | **shop.catalog.search.default-page-size** | **defaultPageSize** |
| Reply-to email address | **shop.notifications.email.reply-to-address** | **replyToAddress** |

Use one official naming style in documentation and configuration files. Relaxed binding allows accepting syntax variants; it does not mean everyone should write a different style.

## 4. Divide by Functional Domain, Not Convenience

An example configuration tree for an e-commerce application:

~~~text
shop
├── checkout
│   ├── payment
│   │   ├── base-url
│   │   ├── connect-timeout
│   │   └── retry
│   │       ├── max-attempts
│   │       └── initial-delay
│   └── shipping
│       ├── provider-url
│       ├── enabled
│       └── request-timeout
├── catalog
│   ├── search
│   └── inventory
└── notifications
    ├── email
    └── sms
~~~

A property group should serve **one responsibility** or one subsystem managed as a unit:

- Payment client owns **shop.checkout.payment**.
- Shipping integration owns **shop.checkout.shipping**.
- Search module owns **shop.catalog.search**.
- Email notification owns **shop.notifications.email**.

If two integrations both use a **timeout** field, keep them under two separate branches:

~~~text
shop.checkout.payment.connect-timeout
shop.checkout.shipping.request-timeout
~~~

Do not place them under **app.timeout** just because both share the same data type.

### 4.1. Avoid Overly Broad Prefixes

~~~text
app.url
app.timeout
app.enabled
app.mode
app.options
~~~

These keys are not self-describing by domain. When changing an **APP_TIMEOUT** variable in a container, operators do not know which feature will be affected.

### 4.2. Avoid Overly Deep Prefixes

~~~text
shop.department.checkout.adapters.remote.payment.http-client.connection.settings.timeout
~~~

The path is overly long, with many levels adding no business value. A prefix should express the **configuration API**, not necessarily mirror the entire Java package tree or adapter classes in code.

A shorter structure:

~~~text
shop.checkout.payment.connect-timeout
~~~

How deep is reasonable depends on project scale. There is no Spring Boot rule mandating exactly three segments. Prioritize **clear meaning**, ownership boundaries, and stability.

### 4.3. Do Not Tightly Couple Prefixes to Organizational Structure

A name containing full department/team names may have to change when the organization restructures. Domains like **payment**, **shipping**, and **catalog** are usually more durable than team names. Only include organizational names in the namespace if they carry long-term technical/identity significance.

## 5. Keep Application Namespaces Separate from Framework Namespaces

Spring Boot and its libraries already reserve their own prefixes:

~~~text
spring.*
server.*
management.*
logging.*
~~~

For example, **spring.datasource.url**, **server.port**, or **management.endpoints.web.exposure.include** are keys with framework-defined meaning.

Avoid creating business keys such as:

~~~properties
spring.payment-timeout=5s
server.checkout-mode=fast
management.shipping-enabled=true
~~~

because readers can easily confuse them with framework properties and the risk of collisions during library upgrades increases.

Use your own namespace:

~~~properties
shop.checkout.payment.connect-timeout=5s
shop.checkout.mode=fast
shop.checkout.shipping.enabled=true
~~~

An internal library can choose its own prefix, such as **acme.notification-client**. If the library will be used across multiple applications, keep the prefix stable and non-overlapping with consuming applications' namespaces.

Conversely, do not copy standard Spring keys into redundant "custom" aliases with identical meaning. For example, if you just want to configure the Hikari pool, consider using **spring.datasource.hikari.maximum-pool-size** directly instead of creating a **shop.database.pool-size** alias that adds no value.

## 6. Java Example: Two @ConfigurationProperties Classes for Two Domains

Suppose the project uses Java 21, Spring Boot 3.3, and the **spring-boot-starter-web** dependency.

Code structure:

~~~text
src/main/java/com/example/shop/
├── ShopApplication.java
├── config/
│   ├── PaymentProperties.java
│   └── ShippingProperties.java
└── api/
    └── SettingsController.java
~~~

### 6.1. PaymentProperties

~~~java
package com.example.shop.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop.checkout.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration connectTimeout,
        Retry retry) {

    public record Retry(
            int maxAttempts,
            Duration initialDelay) {
    }
}
~~~

Bound names:

~~~text
shop.checkout.payment.base-url
shop.checkout.payment.connect-timeout
shop.checkout.payment.retry.max-attempts
shop.checkout.payment.retry.initial-delay
~~~

**retry** belongs to the payment group; in this example, it does not yet need a standalone **@ConfigurationProperties** class. A nested record is an appropriate representation.

### 6.2. ShippingProperties

~~~java
package com.example.shop.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop.checkout.shipping")
public record ShippingProperties(
        URI providerUrl,
        boolean enabled,
        Duration requestTimeout) {
}
~~~

Bound names:

~~~text
shop.checkout.shipping.provider-url
shop.checkout.shipping.enabled
shop.checkout.shipping.request-timeout
~~~

Separating the two records ensures payment and shipping logic depend only on their own configuration contracts.

### 6.3. Registering Configuration Properties Scanning

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

When **ShopApplication** is in the **com.example.shop** package, default scanning can discover classes in subpackages such as **com.example.shop.config**.

Spring Boot can bind **records** via constructor when they are registered by **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties**. Do not add **@Component** to a record expecting Spring to infer constructor binding for configuration parameters.

### 6.4. Explicit Registration Instead of Scanning

An alternative, well-suited for library modules or auto-configuration, is:

~~~java
package com.example.shop;

import com.example.shop.config.PaymentProperties;
import com.example.shop.config.ShippingProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties({
    PaymentProperties.class,
    ShippingProperties.class
})
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

This is an **alternative** to **@ConfigurationPropertiesScan** in the example, not a requirement to use both at the same time.

## 7. Corresponding YAML Configuration

**src/main/resources/application.yml**:

~~~yaml
shop:
  checkout:
    payment:
      base-url: "https://payments.example.invalid"
      connect-timeout: 3s
      retry:
        max-attempts: 3
        initial-delay: 250ms

    shipping:
      provider-url: "https://shipping.example.invalid"
      enabled: true
      request-timeout: 5s
~~~

This structure matches the Java records:

- **shop.checkout.payment** receives **baseUrl**, **connectTimeout**, **retry**.
- **shop.checkout.shipping** receives **providerUrl**, **enabled**, **requestTimeout**.
- Values **3s**, **250ms**, and **5s** can be converted by the binder to **Duration**.
- URLs are dummy data; no endpoint connection is needed.

Equivalent **application.properties** version:

~~~properties
shop.checkout.payment.base-url=https://payments.example.invalid
shop.checkout.payment.connect-timeout=3s
shop.checkout.payment.retry.max-attempts=3
shop.checkout.payment.retry.initial-delay=250ms

shop.checkout.shipping.provider-url=https://shipping.example.invalid
shop.checkout.shipping.enabled=true
shop.checkout.shipping.request-timeout=5s
~~~

When YAML is flattened into property paths by Spring Boot, prefixes and canonical names do not change. Prefer one consistent configuration format across the application to avoid unnecessary conflicts between files sharing the same basename in different formats.

## 8. Consuming Two Groups from Business Code

An illustrative controller:

~~~java
package com.example.shop.api;

import com.example.shop.config.PaymentProperties;
import com.example.shop.config.ShippingProperties;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SettingsController {

    private final PaymentProperties payment;
    private final ShippingProperties shipping;

    public SettingsController(
            PaymentProperties payment,
            ShippingProperties shipping) {
        this.payment = payment;
        this.shipping = shipping;
    }

    @GetMapping("/demo/settings")
    public Map<String, Object> settings() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("paymentBaseUrl", payment.baseUrl().toString());
        result.put("paymentConnectTimeoutMs",
                payment.connectTimeout().toMillis());
        result.put("paymentRetryCount", payment.retry().maxAttempts());
        result.put("shippingEnabled", shipping.enabled());
        result.put("shippingTimeoutMs",
                shipping.requestTimeout().toMillis());
        return result;
    }
}
~~~

When the application runs with the YAML above, an illustrative response is:

~~~json
{
  "paymentBaseUrl": "https://payments.example.invalid",
  "paymentConnectTimeoutMs": 3000,
  "paymentRetryCount": 3,
  "shippingEnabled": true,
  "shippingTimeoutMs": 5000
}
~~~

This API uses only non-sensitive dummy values for demonstration. In a real application, **never expose endpoints displaying internal configuration, tokens, or credentials**.

Note: the controller does not need to know whether properties came from YAML or environment variables. It only depends on configuration objects with clear names and types.

## 9. Relaxed Binding and Environment Variables

Spring Boot supports **relaxed binding**, because Java field names usually use camelCase while canonical property names use kebab-case.

For example, three forms in a properties file can bind to the same Java field **connectTimeout**:

~~~properties
shop.checkout.payment.connect-timeout=3s
shop.checkout.payment.connectTimeout=3s
shop.checkout.payment.connect_timeout=3s
~~~

Always **choose the canonical form** first in code, documentation, and examples.

### 9.1. Rules for Converting to Environment Variables

To convert from a canonical name to an env var:

1. Replace dots **.** with underscores **_**.
2. Remove dashes **-** within each segment.
3. Convert all letters to uppercase.

| Canonical | Environment |
| --- | --- |
| **shop.checkout.payment.base-url** | **SHOP_CHECKOUT_PAYMENT_BASEURL** |
| **shop.checkout.payment.connect-timeout** | **SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT** |
| **shop.checkout.payment.retry.max-attempts** | **SHOP_CHECKOUT_PAYMENT_RETRY_MAXATTEMPTS** |
| **shop.checkout.payment.retry.initial-delay** | **SHOP_CHECKOUT_PAYMENT_RETRY_INITIALDELAY** |
| **shop.checkout.shipping.provider-url** | **SHOP_CHECKOUT_SHIPPING_PROVIDERURL** |
| **shop.checkout.shipping.enabled** | **SHOP_CHECKOUT_SHIPPING_ENABLED** |
| **shop.checkout.shipping.request-timeout** | **SHOP_CHECKOUT_SHIPPING_REQUESTTIMEOUT** |

For example, **connect-timeout** converts to **CONNECTTIMEOUT**, not automatically to **CONNECT_TIMEOUT**. This is a common point of confusion between writing canonical keys and naming environment variables.

### 9.2. Runtime Override Example

In Bash:

~~~bash
SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT=8s java -jar shop.jar
~~~

In PowerShell:

~~~powershell
$env:SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT = "8s"
java -jar shop.jar
~~~

When the application starts with the appropriate env var and no higher-precedence source overrides the key, **PaymentProperties.connectTimeout()** receives a Duration of 8 seconds instead of the 3 seconds in YAML.

A clear prefix helps operators easily identify this environment variable as belonging to the payment group; there is no need to modify the JAR to change values per environment.

### 9.3. Detecting Potentially Colliding Names

Because dashes are removed when converting to env var names, these two properties produce the same name:

~~~text
app.rate-limit -> APP_RATELIMIT
app.ratelimit  -> APP_RATELIMIT
~~~

Avoid creating two distinct keys that differ only by dash placement. Define one canonical name and keep it consistent across all sources.

## 10. Nested Object or a New @ConfigurationProperties?

In PaymentProperties, the **retry** group is declared as a nested record:

~~~java
public record Retry(int maxAttempts, Duration initialDelay) {
}
~~~

This fits because the retry policy is a dedicated configuration part of the payment client.

You should **split into a separate configuration properties class** when:

- A group has a clearly distinct responsibility.
- It has an independent owner or change lifecycle.
- It is referenced by multiple components as an independent contract.
- It has significant validation rules, metadata, or defaults of its own.

You should **keep a nested object** when:

- Fields only make sense within the same subsystem.
- There is no operational reason for an independent namespace.
- Splitting would generate too many tiny classes and hard-to-read prefixes.

A structure like **shop.checkout.payment.retry.max-attempts** can make sense without adding a separate type annotated with prefix **shop.checkout.payment.retry**.

If the same retry concept is used by multiple integrations, decide whether they **share a genuine policy** or merely happen to have similarly named fields. Do not create a **global.timeout** just because several components happen to need a timeout.

## 11. Value Types and Naming

A good name expresses meaning, while the Java type expresses the value's contract.

For example:

~~~yaml
shop:
  checkout:
    payment:
      connect-timeout: 3s
      retry:
        max-attempts: 3
        initial-delay: 250ms
~~~

Use **Duration** instead of **String** if the value represents time. Use **URI** for endpoints or **boolean** for flags. The binder supports converting appropriate values.

Fields like **timeout1**, **timeout2**, and **option3** lack meaning. Name them **connect-timeout**, **read-timeout**, and **request-timeout** according to their actual purpose.

**Default values** can be configured in **application.yml** or set via an appropriate constructor binding mechanism, such as **@DefaultValue**:

~~~java
package com.example.shop.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "shop.checkout.payment")
public record PaymentTimeoutOnly(
        @DefaultValue("3s") Duration connectTimeout) {
}
~~~

This is **an alternative illustrative type**, not a requirement to register it alongside the full PaymentProperties sharing the same prefix.

Use defaults explicitly: a sensible timeout can have a default; required URLs or secrets should not silently fall back to dummy values in production.

## 12. Validation Along a Prefix Boundary

For essential configuration, Spring Boot supports Bean Validation when **spring-boot-starter-validation** is present.

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Example of a validated properties version:

~~~java
package com.example.shop.config;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.checkout.payment")
public record ValidatedPaymentProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @Valid @NotNull Retry retry) {

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration initialDelay) {
    }
}
~~~

**ValidatedPaymentProperties** is an alternative example to **PaymentProperties**. In an exercise project, register only one of the two types sharing the same prefix.

With validation, a missing **base-url** or setting **retry.max-attempts=0** can trigger a clear startup error instead of a late failure during a real request. A full property path such as **shop.checkout.payment.retry.max-attempts** helps operators pinpoint the exact group to fix.

**@Valid** indicates that Bean Validation should cascade into the nested object. A good prefix gives contextual error messages, but does not replace validation rules.

## 13. Configuration Metadata and IDE Support

Spring Boot provides **configuration metadata** to help IDEs suggest property names, data types, and descriptions when editing **application.yml** or **application.properties**.

To generate metadata for custom **@ConfigurationProperties** types, add **spring-boot-configuration-processor** according to your project's annotation processing setup.

Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Maven (a common declaration):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

In a build with custom annotation processor configuration, ensure the processor is actually invoked by the compiler.

Metadata typically resides in **META-INF/spring-configuration-metadata.json** of the build output, describing keys such as:

~~~text
shop.checkout.payment.base-url
shop.checkout.payment.connect-timeout
shop.checkout.payment.retry.max-attempts
shop.checkout.shipping.provider-url
shop.checkout.shipping.enabled
~~~

It is helpful when modules or starters are shared across multiple applications: consumers can discover available keys under the module's prefix.

Metadata **does not register beans automatically** and **does not replace runtime binding**. You still need **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties** as appropriate.

In each group's documentation, specify purpose, type, unit, default value, whether it is required, and how to supply it via environment variables.

## 14. Prefixes as a Configuration Contract with Deployment Systems

A property does not only live in source code. It can be written in:

- Config Data files outside the JAR.
- Docker Compose and Docker run environments.
- Kubernetes ConfigMaps, Secrets, Deployments.
- Helm values and templates.
- CI/CD pipelines.
- PowerShell/Bash scripts.
- Configuration management tools and operations runbooks.

Docker Compose example:

~~~yaml
services:
  shop:
    image: example/shop:1.0.0
    environment:
      SHOP_CHECKOUT_PAYMENT_BASEURL: "https://payments.example.invalid"
      SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT: "7s"
      SHOP_CHECKOUT_PAYMENT_RETRY_MAXATTEMPTS: "4"
      SHOP_CHECKOUT_PAYMENT_RETRY_INITIALDELAY: "500ms"
      SHOP_CHECKOUT_SHIPPING_PROVIDERURL: "https://shipping.example.invalid"
      SHOP_CHECKOUT_SHIPPING_ENABLED: "true"
      SHOP_CHECKOUT_SHIPPING_REQUESTTIMEOUT: "6s"
~~~

The keys above are actual environment variables passed into the container. Spring Boot uses them when binding by prefix. Grouping by name makes it easy to see at a glance what belongs to payment and what belongs to shipping.

A Kubernetes Pod template snippet might look like:

~~~yaml
containers:
  - name: shop
    image: example/shop:1.0.0
    env:
      - name: SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT
        value: "7s"
      - name: SHOP_CHECKOUT_PAYMENT_RETRY_MAXATTEMPTS
        value: "4"
      - name: SHOP_CHECKOUT_SHIPPING_ENABLED
        value: "true"
~~~

This is an illustrative snippet, not a complete Deployment manifest.

**Do not put real credentials in examples, public repositories, or debug endpoints**. If a property holds a secret, use a secret management mechanism and restrict access according to the deployment platform.

## 15. Managing Renames and Compatibility

Suppose a property has already been deployed:

~~~text
shop.checkout.payment.connect-timeout
~~~

Later, it is renamed to:

~~~text
shop.payment.gateway.timeout
~~~

This **is not merely renaming a class or field**. Deployment tooling may still be supplying **SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT**. If Java only binds the new prefix, the application could receive **null**, a default, or a validation error.

A sensible change process:

1. Identify the old key, new key, and reason for renaming.
2. List environments that may still be using the old key.
3. Update documentation, metadata, manifests, and tests.
4. If a transition period is needed, implement a mechanism to read the old key and log a clear warning.
5. Only after all environments have migrated, remove the old configuration support as planned.

**Relaxed binding is not an alias system across unrelated namespaces.** It helps map **base-url** to **baseUrl** in the right context, but it does not automatically know that **shop.payment.gateway** is the new name for **shop.checkout.payment**.

**@DeprecatedConfigurationProperty** can contribute deprecation info to configuration metadata, but by itself this annotation does not translate old keys to new keys at runtime. If backward compatibility is required, an actual mapping or migration mechanism must be designed.

## 16. Testing Domain-Scoped Binding

A Spring Boot test can pass properties directly with the exact prefix:

~~~java
package com.example.shop;

import com.example.shop.config.PaymentProperties;
import com.example.shop.config.ShippingProperties;
import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(properties = {
    "shop.checkout.payment.base-url=https://test-pay.example.invalid",
    "shop.checkout.payment.connect-timeout=2s",
    "shop.checkout.payment.retry.max-attempts=2",
    "shop.checkout.payment.retry.initial-delay=100ms",
    "shop.checkout.shipping.provider-url=https://test-ship.example.invalid",
    "shop.checkout.shipping.enabled=false",
    "shop.checkout.shipping.request-timeout=4s"
})
class DomainPropertiesTest {
    @Autowired PaymentProperties payment;
    @Autowired ShippingProperties shipping;

    @Test
    void bindsSeparateFunctionalGroups() {
        assertEquals(
            URI.create("https://test-pay.example.invalid"),
            payment.baseUrl());
        assertEquals(Duration.ofSeconds(2), payment.connectTimeout());
        assertEquals(2, payment.retry().maxAttempts());
        assertEquals(
            URI.create("https://test-ship.example.invalid"),
            shipping.providerUrl());
        assertFalse(shipping.enabled());
        assertEquals(Duration.ofSeconds(4),
            shipping.requestTimeout());
    }
}
~~~

The example assumes the application has registered both types via scanning or enabling as shown earlier, includes **spring-boot-starter-test**, and controllers/other beans do not require real infrastructure to start the context.

**Key takeaway:** payment and shipping properties are bound separately; a shipping key does not leak into the payment bean due to their distinct prefix paths.

To test the configuration class in isolation without launching the entire web application, you can use **ApplicationContextRunner** and register **@EnableConfigurationProperties** for the type under test.

## 17. Common Pitfalls

### 17.1. Writing camelCase in the Prefix

~~~java
@ConfigurationProperties(prefix = "shop.checkoutPayment")
~~~

Change this to canonical **shop.checkout-payment** or hierarchical **shop.checkout.payment** depending on the boundary being modeled.

### 17.2. One AppProperties Class Containing Everything

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
    String paymentUrl,
    String shippingUrl,
    String emailUrl,
    Duration paymentTimeout,
    Duration shippingTimeout) {
}
~~~

This works, but in large applications it becomes difficult to own and test. Split types by subsystem when groups have independent change lifecycles.

### 17.3. Assuming Java camelCase Must Be Preserved in YAML

Java's **connectTimeout** should have the canonical name **connect-timeout** in files. Spring Boot relaxed binding handles the mapping.

### 17.4. Adding Underscores Between Every Word in Env Vars

**SHOP_CHECKOUT_PAYMENT_CONNECT_TIMEOUT** is not the standard transformation of the canonical key **shop.checkout.payment.connect-timeout**. Under Spring Boot's rules, the standard name is **SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT**.

### 17.5. Confusing Dots with Dashes

**shop.checkout-payment** and **shop.checkout.payment** express different structures; do not swap them just because the names look similar.

### 17.6. Using spring.* for Business Keys

**spring.checkout.timeout** can easily be mistaken for framework configuration. Use the application's own namespace.

### 17.7. Forgetting to Register the Type

Simply putting **@ConfigurationProperties** on a record is not enough if it is not registered via scanning or **@EnableConfigurationProperties**. When a class sits outside the scanned package, declare the scan scope or register explicitly.

### 17.8. Using @Component on a Constructor-Bound Record

For immutable constructor-bound styles like the records in this lesson, register via the mechanisms Spring Boot supports for **@ConfigurationProperties**, rather than relying on standard **@Component** bean registration.

### 17.9. Changing a Prefix Without Updating Deployment

Code using a new key while Docker/Kubernetes/CI still supplies the old key will cause configuration not to work as expected. A clear migration is required.

### 17.10. Missing Validation for Critical Properties

Standard names help locate keys; they do not guarantee valid values. Use explicit types and appropriate constraints for URLs, retry counts, timeouts, or required fields.

## 18. Practice Exercises

### Exercise A — Converting Flat Configuration into Domain Groups

Given the initial configuration:

~~~properties
app.payment-url=https://pay.example.invalid
app.shipping-url=https://ship.example.invalid
app.payment-timeout=3s
app.shipping-timeout=5s
~~~

Convert it to:

~~~properties
shop.checkout.payment.base-url=https://pay.example.invalid
shop.checkout.payment.connect-timeout=3s
shop.checkout.shipping.provider-url=https://ship.example.invalid
shop.checkout.shipping.request-timeout=5s
~~~

Create separate **PaymentProperties** and **ShippingProperties**. Register them using **@ConfigurationPropertiesScan** and read values via constructor injection.

### Exercise B — Generating Environment Variable Names

Given three canonical keys:

~~~text
shop.checkout.payment.base-url
shop.checkout.payment.retry.max-attempts
shop.checkout.shipping.request-timeout
~~~

Convert them to:

~~~text
SHOP_CHECKOUT_PAYMENT_BASEURL
SHOP_CHECKOUT_PAYMENT_RETRY_MAXATTEMPTS
SHOP_CHECKOUT_SHIPPING_REQUESTTIMEOUT
~~~

Run the same JAR with the new env var values to observe each object receiving the correct values. Notice that dashes are **removed**.

### Exercise C — Adding Validation

1. Add **spring-boot-starter-validation**.
2. Use the properties version with **@Validated**, **@NotNull**, **@Min**.
3. Try omitting **base-url** and setting **retry.max-attempts=0**.
4. Observe the startup failure and identify the property paths belonging to the payment group.

### Exercise D — Comparing Two Independent Domains

1. Override only **shop.checkout.payment.connect-timeout** via env var.
2. Keep **shop.checkout.shipping.request-timeout** configured from YAML.
3. Use **PaymentProperties** and **ShippingProperties** to read the values after startup.

Key takeaway: the two groups have independent value sources and responsibilities.

### Exercise E — Testing an Incompatible Prefix Change

1. Keep the key **shop.checkout.payment.base-url** in YAML.
2. On an experimental branch, change the annotation to **shop.payments.gateway** without modifying the file.
3. Observe that the property no longer binds from the old path.
4. Restore the name or fully update documentation, deployment, and test configuration.

Key takeaway: a prefix is a configuration contract, not merely a name in Java.

## 19. Checklist Before Publishing a Configuration Group

A **@ConfigurationProperties** group should answer these questions:

1. Which domain/subsystem owns this group?
2. Does the prefix avoid collisions with framework and library namespaces?
3. Are the annotation prefix and keys written in lowercase kebab-case?
4. Is the hierarchy depth clear without being overly verbose?
5. Does each field name accurately describe its purpose?
6. Are data types appropriate, such as Duration or URI instead of generic String?
7. Is validation present for required or bounded values?
8. Is the class registered via scanning or enable within the proper scope?
9. Are env var names easy to trace and free from collisions caused by removing dashes?
10. Is metadata/documentation available explaining keys to operators?
11. If renamed, is there a plan to update environments still using the old prefix?
12. Are there secrets or sensitive data requiring protected runtime sources?

## 20. Key Takeaways

- **A prefix is the public namespace of application configuration**; it should be named after functional domains.
- **@ConfigurationProperties(prefix = "...")** requires prefixes to be written in lowercase kebab-case.
- Dots **.** represent hierarchy; dashes **-** join words within a single segment.
- **shop.checkout.payment** and **shop.checkout.shipping** should be two independent groups when they have distinct responsibilities and lifecycles.
- Spring Boot relaxed binding maps canonical properties to Java camelCase and uppercase environment variables.
- Env var names are generated by the rule: **dot → _; dash → remove; letters → uppercase**.
- Immutable records can use constructor binding when the type is registered via **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties**.
- Nested objects fit fields sharing a responsibility; separate classes fit independent subsystems.
- Validation and configuration metadata help users catch invalid config and discover the right keys.
- Renaming a prefix after deployment is an operational contract change and must be managed as a migration.

## Official References

- Spring Boot 3.3 — Externalized Configuration, *Type-safe Configuration Properties*, *Enabling @ConfigurationProperties Types*, *Relaxed Binding*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
- Spring Framework — Environment abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
