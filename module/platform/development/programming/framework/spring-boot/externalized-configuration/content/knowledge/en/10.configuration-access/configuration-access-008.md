# Name Binding and Complex Structure Limits of `@Value` in Spring Boot 3.3

## 1. Goal and context

Spring Boot lets you bring configuration from `application.properties`, YAML, environment variables, JVM properties, and command-line arguments into Java code. One simple approach is `@Value`:

```java
@Value("${app.name}")
private String name;
```

For a few standalone keys, this syntax is concise. But when a system has dozens of properties, key names vary across `kebab-case`, `camelCase`, and environment variables, or configuration starts containing **lists, `Map`s, nested objects, and data constraints**, `@Value` is no longer as convenient as `@ConfigurationProperties`.

This article clarifies the **name binding and complex structure limits of `@Value`** in Spring Boot 3.3, focusing on these questions:

1. Are `@Value("${demo.item-price}")` and `@Value("${demo.itemPrice}")` truly equivalent?
2. Why can a YAML list be accessed element-by-element yet not automatically bind to `List<Endpoint>` via a simple `@Value`?
3. Why do `Map<String, String>`, `Map<String, Object>`, and lists of objects bind differently?
4. When should you keep using `@Value`, and when should you switch to `@ConfigurationProperties`?
5. How do you use typed configuration, defaults, validation, and inspect final values?

The illustrative examples use **Java 17 or later**, **Spring Boot 3.3.x**, and corresponding Spring Framework syntax. Learners should already know Java records/classes, constructor injection, beans, and basic configuration formats.

**Main message:** `@Value` is a mechanism for **injecting an expression/value into a Spring injection point**; it is not a lightweight equivalent of the **Binder** used for `@ConfigurationProperties`.

## 2. Three configuration access mechanisms to distinguish

Spring Boot offers multiple ways to read configuration, yet they do not share the same interface or abstraction level.

| Access mechanism | Example | Suitable scenario |
| --- | --- | --- |
| `@Value` | `@Value("${app.timeout:5s}")` | One or a few standalone values; occasionally SpEL |
| `Environment` | `env.getProperty("app.timeout")` | Dynamic key-based lookups, conditional logic in code |
| `@ConfigurationProperties` | `@ConfigurationProperties(prefix = "app.client")` | Whole typed configuration groups, many fields, `List`, `Map`, nested objects |

All of them work with Spring's configuration system, however:

- `Environment` allows programmatic key lookup. It does not automatically turn an entire tree of keys into a business Java object.
- `@Value` uses `${...}` placeholders or `#{...}` SpEL expressions at the **injection point**. It depends on expression resolution and type conversion at that point.
- `@ConfigurationProperties` uses Spring Boot's Binder to **bind a prefix-grouped set of keys** into typed Java structures. It supports relaxed binding, complex structures, configuration metadata, and validation integration.

Example flat data:

```properties
app.title=Inventory API
app.retry-count=3
```

Using `@Value` is straightforward:

```java
@Component
public class Banner {

    private final String title;
    private final int retryCount;

    public Banner(
            @Value("${app.title}") String title,
            @Value("${app.retry-count:3}") int retryCount
    ) {
        this.title = title;
        this.retryCount = retryCount;
    }
}
```

Using constructor injection keeps dependencies and required values explicit right when the bean is created. When a bean only needs two independent values, this approach makes complete sense.

However, if `app` has 20 fields and multiple nesting levels, a constructor full of individual `@Value` parameters becomes hard to read, hard to test, and hard to evolve consistently.

## 3. `@Value` uses placeholders, not a `@ConfigurationProperties`-style Binder

Basic placeholder syntax:

```java
@Value("${app.title}")
String title;
```

Spring looks up property `app.title` and uses the found value for injection. Common default syntax:

```java
@Value("${app.retry-count:3}")
int retryCount;
```

If the property has no value and is not provided by another source, the placeholder can use `3`. The string value converts to `int` during injection via the appropriate type conversion mechanism.

Without declaring a default:

```java
@Value("${app.required-name}")
String requiredName;
```

an unresolved placeholder normally causes bean creation to fail in a standard Spring Boot application context. Thus, `@Value` can also make the application fail early when a mandatory key is missing.

What must be distinguished is that **resolving a placeholder** is not the same as **scanning multiple properties under a prefix, constructing Java structures, and binding each component property**.

Example:

```yaml
app:
  mail:
    from: noreply@example.test
    timeout: 5s
    recipients:
      - ops@example.test
      - support@example.test
```

`@Value("${app.mail.from}")` normally accesses a single scalar key. `@Value("${app.mail.recipients[0]}")` can access an element at a specific index if the configuration source generates the corresponding key. However, `@Value("${app.mail}")` does **not mean** Spring automatically builds a full `MailProperties` containing `from`, `timeout`, and `recipients`.

### 3.1. Do not confuse property names with Java field names

A Java field name:

```java
private int retryCount;
```

does not guarantee `@Value("${app.retryCount}")` has the same ability to pick up environment variables or all key variants as the Binder. In `@Value`, **the string inside `${...}`** is what determines the lookup.

Therefore, write placeholder names in canonical form instead of arbitrarily copying Java variable names.

## 4. Relaxed binding limits of `@Value`

### 4.1. What is relaxed binding?

Relaxed binding allows different naming conventions to represent the same logical property when the Binder binds configuration.

For example, `app.client.connect-timeout` can appear in a file as:

```properties
app.client.connect-timeout=3s
```

or:

```properties
app.client.connectTimeout=3s
```

And the corresponding canonical environment variable is:

```text
APP_CLIENT_CONNECTTIMEOUT
```

When using `@ConfigurationProperties(prefix = "app.client")`, the Spring Boot Binder understands those valid variants to populate the Java field `connectTimeout`.

### 4.2. Key point: `@Value` has only limited support

The **Spring Boot 3.3 — Externalized Configuration** documentation explicitly states that `@Value` is a Spring container feature and **does not have the full feature set** of type-safe configuration properties. For `@Value`, Spring Boot recommends referencing properties using **canonical lowercase kebab-case names**.

Compare:

```java
@Value("${demo.item-price}")
private BigDecimal price;
```

and:

```java
@Value("${demo.itemPrice}")
private BigDecimal price;
```

Suppose configuration has:

```properties
demo.itemPrice=12.50
```

Or another environment only supplies:

```text
DEMO_ITEMPRICE=12.50
```

With canonical `${demo.item-price}`, Spring Boot can apply relaxed-binding-compatible lookup logic to match eligible variants.

Conversely, if you write `${demo.itemPrice}`, **you cannot assume** it checks both `demo.item-price` and `DEMO_ITEMPRICE` in the same way. This is the official example demonstrating `@Value`'s limitation.

**Practical rule:**

```java
// Prefer canonical form for placeholders
@Value("${app.client.connect-timeout:5s}")
private Duration timeout;
```

Instead of:

```java
// Avoid relying on arbitrary name forms
@Value("${app.client.connectTimeout:5s}")
private Duration timeout;
```

Canonical form does not turn `@Value` into a full Binder, but it prevents a major class of bugs when configuration moves from files to environment variables.

### 4.3. Key-naming capability comparison table

| Capability | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- |
| Read an exact key | Yes | Yes, through group binding |
| Accept multiple property name variants | **Limited**, prefer canonical placeholders | **Yes**, relaxed binding is a core feature |
| Automatically bind an entire property group | Not in the Binder's manner | Yes |
| Configuration metadata generated for IDEs | Not from `@Value` itself | Possible via configuration processor |
| SpEL | Yes | Does not support SpEL like `@Value` |
| Bind nested objects | Not automatically from a single placeholder | Yes |
| Bind `List`/`Map` structures | Only specific manual cases or via conversion/SpEL | Officially supported |
| Structural validation | No direct equivalent on `@Value` | Integrates with Bean Validation |

Therefore, a `${app.some-key}` string working today does not guarantee every naming variant or configuration source format will behave identically later.

## 5. Environment variable names: the clearest place this limit appears

Spring Boot has environment variable naming rules for the Binder:

1. Replace `.` with `_`.
2. Remove `-`.
3. Convert the name to uppercase.

Examples:

| Canonical property | Corresponding environment variable |
| --- | --- |
| `app.region` | `APP_REGION` |
| `app.mail.retry-count` | `APP_MAIL_RETRYCOUNT` |
| `app.client.connect-timeout` | `APP_CLIENT_CONNECTTIMEOUT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |

Example in Bash:

```bash
export APP_MAIL_RETRYCOUNT=6
java -jar app.jar
```

In PowerShell:

```powershell
$env:APP_MAIL_RETRYCOUNT = '6'
java -jar .\app.jar
```

An injection point using canonical form:

```java
@Value("${app.mail.retry-count:3}")
int retryCount;
```

can match the appropriate variant. Yet if you write a non-canonical placeholder:

```java
@Value("${app.mail.retryCount:3}")
int retryCount;
```

you cannot infer that it checks all variants like the Binder.

### Lists in environment variables

With the Binder, list indices sit between `_` characters. Example:

```text
app.nodes[0].host  -> APP_NODES_0_HOST
app.nodes[1].host  -> APP_NODES_1_HOST
```

This is `@ConfigurationProperties`'s list binding mechanism. Do not turn it into a fixed series of `@Value("${app.nodes[0].host}")`, `@Value("${app.nodes[1].host}")` when the number of elements can vary. List configuration should be modeled as `List<Node>`.

## 6. How well does `@Value` handle single values?

Simple data types usually fit well:

```properties
app.display-name=Demo API
app.enabled=true
app.retry-count=4
app.request-timeout=3s
app.endpoint=https://api.example.test
```

Example:

```java
@Component
public class SimpleOptions {

    private final String displayName;
    private final boolean enabled;
    private final int retryCount;
    private final Duration timeout;
    private final URI endpoint;

    public SimpleOptions(
            @Value("${app.display-name}") String displayName,
            @Value("${app.enabled:false}") boolean enabled,
            @Value("${app.retry-count:3}") int retryCount,
            @Value("${app.request-timeout:5s}") Duration timeout,
            @Value("${app.endpoint}") URI endpoint
    ) {
        this.displayName = displayName;
        this.enabled = enabled;
        this.retryCount = retryCount;
        this.timeout = timeout;
        this.endpoint = endpoint;
    }
}
```

Related imports:

```java
import java.net.URI;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
```

Converting strings to `int`, `boolean`, `Duration`, or `URI` depends on type converters available in the `ApplicationContext`. In a standard Spring Boot application, many common conversions are supported.

However, **being able to convert single types** does not mean **being able to bind arbitrary structures**. Converting `"3s"` into `Duration` is much simpler than reading dozens of nested keys into `List<Gateway>`.

### Defaults do not replace validation

Example:

```java
@Value("${app.pool-size:10}")
private int poolSize;
```

Default `10` only resolves the missing-value case. It does **not** automatically ensure `poolSize > 0`. If configuration sets `-4`, a successful conversion can still yield a business-invalid value. Validation at the configuration level or separate logic is needed to enforce this condition.

## 7. Lists: why one placeholder is not `List<T>` binding

Consider YAML:

```yaml
app:
  notification:
    recipients:
      - ops@example.test
      - support@example.test
```

Spring Boot loads YAML into properties accessible by appropriate paths/elements. If you know the exact index, you can write:

```java
@Value("${app.notification.recipients[0]}")
String firstRecipient;
```

This is completely different from the goal:

```java
List<String> recipients;
```

You should not assume that:

```java
@Value("${app.notification.recipients}")
List<String> recipients;
```

will pull the entire YAML list structure like the Binder. With YAML flattened by index, there is not necessarily a scalar key `app.notification.recipients` holding the entire string for a single placeholder to resolve.

### 7.1. Why can CSV examples create misconceptions?

If a `.properties` file contains:

```properties
app.notification.recipients=ops@example.test,support@example.test
```

then depending on the `ConversionService`, a `List<String>` or array injection point can convert from **one CSV string** into multiple elements:

```java
@Value("${app.notification.recipients}")
private List<String> recipients;
```

That is **converting a single string value**, not the Binder traversing a complex YAML configuration tree. If you switch from CSV to a YAML list, the same `@Value` snippet may stop working as expected.

In systems that genuinely need lists, use:

```java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(List<String> recipients) {
}
```

The Binder handles list representations supported by Spring Boot across properties, YAML, and environment variables.

### 7.2. Lists of objects are even further from CSV

Consider:

```yaml
app:
  integrations:
    gateways:
      - id: primary
        url: https://primary.example.test
        timeout: 2s
      - id: backup
        url: https://backup.example.test
        timeout: 5s
```

In Java you want:

```java
List<Gateway> gateways;
```

Here each element has **multiple fields and multiple types**, which cannot be parsed meaningfully from a plain `app.integrations.gateways` string.

Using only `@Value`:

```java
@Value("${app.integrations.gateways[0].id}")
String primaryId;
```

you have to pick fixed indices and write an extra injection point per field. Adding a third element in configuration forces Java code changes, defeating the goal of externalized configuration.

## 8. `Map`: reading a single subkey is not binding the whole table

YAML:

```yaml
app:
  limits:
    standard: 50
    premium: 500
    enterprise: 5000
```

An individual value can be looked up like:

```java
@Value("${app.limits.standard}")
private int standardLimit;
```

Yet the real requirement is usually:

```java
Map<String, Integer> limits;
```

so the application can read an unfixed number of tiers dynamically.

`@Value("${app.limits}")` does not automatically traverse `app.limits.standard`, `app.limits.premium`, `app.limits.enterprise` and build a `Map` according to official Binder rules. If some SpEL expression or specialized converter achieves something similar, that is a bespoke workaround with custom data conventions—not to be confused with the structural mechanism of `@ConfigurationProperties`.

Use the Binder:

```java
@ConfigurationProperties(prefix = "app")
public record LimitsProperties(Map<String, Integer> limits) {
}
```

### 8.1. `Map` keys with special characters

Spring Boot has **bracket notation** rules to preserve special characters in `Map` keys.

`.properties` example:

```properties
app.labels[/red]=high
app.labels[/blue]=low
```

Or YAML (wrapping brackets in quotes):

```yaml
app:
  labels:
    "[/red]": high
    "[/blue]": low
```

With `Map<String, String> labels`, keys `/red` and `/blue` are preserved intact. If brackets are omitted, characters that are not alphanumeric, hyphens, or dots can be stripped during binding.

Another special case is `.` inside keys: with `Map<String, String>`, dots can be preserved in scalar keys, whereas with `Map<String, Object>`, dots can create nested structures unless brackets are used.

This illustrates that **`Map` binding has dedicated rules** that cannot be replaced by the idea "just read a string with `@Value`".

## 9. `@Value` and SpEL: strong at expressions, not a replacement for object binding

`@Value` can also use **Spring Expression Language (SpEL)**:

```java
@Value("#{2 * 3}")
int six;
```

Or compute from a placeholder value:

```java
@Value("#{'${app.allowed-regions:us,eu}'.split(',')}")
List<String> regions;
```

If `app.allowed-regions` is a CSV string such as:

```properties
app.allowed-regions=us,eu,apac
```

that expression can produce a list of strings via `split(',')`.

However:

- SpEL only sees the data you place into the expression; it does not become Spring Boot's Binder.
- Values containing quotes or special characters can make manual expression interpolation brittle.
- `split(',')` is not a general CSV parser for quoted fields, escaped commas, or nested structures.
- If data shifts from CSV to a YAML list, the old expression may break.
- Long expressions duplicated across multiple beans make configuration hard to trace, hard to reuse, and hard to diagnose.

Some codebases use:

```java
@Value("#{${app.prices}}")
Map<String, Integer> prices;
```

This only works if `app.prices` is supplied in **compatible SpEL syntax**, not because arbitrary YAML maps automatically convert into matching expressions.

When the requirement is a genuine **configuration map**, `@ConfigurationProperties` is much more predictable.

### 9.1. Spring Boot official feature matrix

| Feature | `@ConfigurationProperties` | `@Value` |
| --- | --- | --- |
| Relaxed binding | Yes | Limited |
| Configuration metadata | Yes | No |
| SpEL expression evaluation | No | Yes |

This difference is **by design**. It is not that `@Value` is "broken" because it does not bind configuration trees; it was designed for value and expression injection, whereas `@ConfigurationProperties` was designed for typed configuration.

## 10. Standard choice: `@ConfigurationProperties` for structured configuration

Build a realistic service gateway example with these parts:

- `enabled`: enable/disable a feature.
- `retryCount`: retry count.
- `connectTimeout`: connection timeout.
- `gateways`: list of gateways with `name`, `url`, `timeout`.
- `quotas`: `Map` from tier name to a quota object.

YAML configuration:

```yaml
app:
  access:
    enabled: true
    retry-count: 3
    connect-timeout: 2s

    gateways:
      - name: primary
        url: https://primary.example.test
        timeout: 2s
      - name: backup
        url: https://backup.example.test
        timeout: 5s

    quotas:
      standard:
        max-requests: 100
        window: 1m
      premium:
        max-requests: 1000
        window: 10m
```

Java record:

```java
package example.configaccess;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.access")
public record AccessProperties(
        boolean enabled,
        int retryCount,
        Duration connectTimeout,
        List<Gateway> gateways,
        Map<String, Quota> quotas
) {
    public record Gateway(
            String name,
            URI url,
            Duration timeout
    ) {
    }

    public record Quota(
            int maxRequests,
            Duration window
    ) {
    }
}
```

Meaning:

- `retry-count` binds to record field `retryCount`.
- `connect-timeout` binds to `Duration connectTimeout`.
- Elements under `gateways` bind to `List<Gateway>` with two objects.
- Keys `standard` and `premium` bind into `Map<String, Quota>` with `Quota` record values.
- The configuration class provides **one clear data model**, rather than scattered injection points.

In Spring Boot 3.3, a record with a matching single constructor can use constructor binding without adding `@ConstructorBinding` separately. If a class has multiple constructors, you may need to indicate which constructor to use; constructor-bound configuration beans must be registered through the appropriate configuration properties mechanism.

### 10.1. Registering configuration properties

Application class:

```java
package example.configaccess;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigAccessApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigAccessApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` lets Spring Boot discover and register configuration types within the scan scope. In projects with few classes, you can use `@EnableConfigurationProperties(AccessProperties.class)` on an appropriate configuration class.

**Note:** do not arbitrarily add `@Component` to a record intended for Spring Boot constructor binding. Constructor binding for `@ConfigurationProperties` has a different registration mechanism than creating beans with `@Component`, `@Bean`, or `@Import`.

### 10.2. Using constructor injection in other beans

```java
package example.configaccess;

import org.springframework.stereotype.Service;

@Service
public class GatewaySummaryService {

    private final AccessProperties properties;

    public GatewaySummaryService(AccessProperties properties) {
        this.properties = properties;
    }

    public int gatewayCount() {
        return properties.gateways().size();
    }

    public int standardQuota() {
        return properties.quotas().get("standard").maxRequests();
    }
}
```

A bean only needs a dependency on `AccessProperties`, rather than six or eight `@Value` parameters. If configuration adds another `Gateway`, Spring Boot binds the list from external content without adding new `@Value` fields per element.

In the example, values are fully defined. In a real app where the list or `standard` key might be missing, combine validation and appropriate missing-value handling to avoid dereferencing `null`.

## 11. The same structure in `.properties`

YAML is not required to use the Binder. The same configuration can be written as:

```properties
app.access.enabled=true
app.access.retry-count=3
app.access.connect-timeout=2s

app.access.gateways[0].name=primary
app.access.gateways[0].url=https://primary.example.test
app.access.gateways[0].timeout=2s

app.access.gateways[1].name=backup
app.access.gateways[1].url=https://backup.example.test
app.access.gateways[1].timeout=5s

app.access.quotas.standard.max-requests=100
app.access.quotas.standard.window=1m
app.access.quotas.premium.max-requests=1000
app.access.quotas.premium.window=10m
```

The Binder understands indices `[0]`, `[1]` to build the list; and `standard`, `premium` to build the `Map`.

If you switch `.properties` to YAML, the `AccessProperties` Java code stays unchanged. That is the value of typed configuration: **a stable Java model while data can come from many sources**.

If you used `@Value` per element, you would have to know every element's name and position upfront—defeating the benefit of externalizing lists into configuration.

## 12. Multiple configuration sources: lists and Maps do not override the same way

Consider base configuration:

```yaml
app:
  access:
    gateways:
      - name: primary
        url: https://primary.example.test
        timeout: 2s
      - name: backup
        url: https://backup.example.test
        timeout: 5s

    quotas:
      standard:
        max-requests: 100
        window: 1m
```

Add a profile-specific document for `dev`:

```yaml
---
spring:
  config:
    activate:
      on-profile: dev

app:
  access:
    gateways:
      - name: local
        url: http://localhost:8081
        timeout: 1s

    quotas:
      standard:
        max-requests: 20
```

With Spring Boot's Binder:

- A **`List`** in a higher-precedence source normally **replaces the entire list** from lower sources; it does not merge `local` with `primary` and `backup`. In the `dev` example, `gateways` will contain only `local` if no higher-precedence source intervenes.
- A **`Map`** can receive entries from multiple sources at the subkey level. `standard.max-requests` from `dev` can override to `20`, while `standard.window` from the base document can still contribute `1m`.

This is Spring Boot's structured binding rule. Manually accessing individual keys like `app.access.gateways[0].name` or `app.access.quotas.standard.max-requests` with `@Value` can obscure the big picture and make override reasoning difficult.

**Important:** the final outcome also depends on file locations, active profiles, environment variables, startup arguments, and other `PropertySource`s. Do not judge precedence from a single YAML snippet alone.

## 13. Defaults and missing configuration: difference between single values and data groups

### 13.1. `@Value` has simple defaults

```java
@Value("${app.retry-count:3}")
private int retryCount;
```

When the key is missing, `3` is a usable default. This is concise when you have one small, independent value.

But with multiple related fields:

```java
@Value("${app.tls.enabled:false}")
private boolean tlsEnabled;

@Value("${app.tls.keystore:}")
private String keystore;

@Value("${app.tls.protocol:TLSv1.3}")
private String protocol;
```

it is easy to produce inconsistent combinations, such as `tlsEnabled=true` while `keystore` is empty. Per-field defaults cannot solve **validating the consistency of a configuration group**.

### 13.2. `@DefaultValue` for constructor binding

With `@ConfigurationProperties`, Spring Boot provides `@DefaultValue` for constructor parameters or record components:

```java
package example.configaccess;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("3") int maxRetries,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("true") boolean enabled
) {
}
```

Here defaults belong to the **configuration data type**, instead of being scattered across multiple injection points in business beans.

When you have complex structures or need to guarantee certain fields always have values, design appropriate constructors/records and constraints rather than inserting strings of `${...:...}` defaults everywhere.

### 13.3. `null` values and missing documents are not identical

When a nested configuration group is missing, the Binder may leave the reference field as `null` if no default or initialization mechanism is defined. Do not assume `List`, `Map`, or nested records are always non-null.

With `@Value`, a missing placeholder can fail bean creation if no default exists. With `@ConfigurationProperties`, missing values are governed by binding and validation rules. Because the two mechanisms follow different rules, do not assume that using the Binder automatically accepts or rejects all missing data.

## 14. Validation: a strength of typed configuration

A configuration group might have constraints such as:

- Retry count must be non-negative.
- Gateway name must not be blank.
- Gateway list must contain at least one element.
- Every quota must be greater than 0.

When the application includes `spring-boot-starter-validation`, you can combine Bean Validation with `@ConfigurationProperties`.

Example:

```java
package example.configaccess;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @Min(0) int retryCount,
        @NotEmpty List<@Valid Gateway> gateways
) {
    public record Gateway(
            @NotBlank String name,
            @NotNull URI url,
            @NotNull Duration timeout
    ) {
    }
}
```

Explanation:

- `@Validated` requests validation for the configuration properties.
- `@Min(0)` checks `retryCount`.
- `@NotEmpty` requires the list to be non-empty.
- `@Valid` cascades validation into complex elements inside the list.
- `@NotBlank` and `@NotNull` express required fields.

If configuration violates constraints, the application can fail during binding/validation with a message pointing directly to the configuration group. This is much more helpful than a business bean discovering late that `url` is empty or the list is missing.

Sample configuration:

```yaml
app:
  integration:
    retry-count: 2
    gateways:
      - name: primary
        url: https://primary.example.test
        timeout: 2s
```

Constraints for `IntegrationProperties` live in one central place, rather than being duplicated across multiple constructors or `@Value`-annotated fields.

**Limit to remember:** Bean Validation checks declared constraints and requires an appropriate provider. It does not guarantee that a URL is actually reachable or that an external system is up.

## 15. Configuration metadata and IDE support

`@ConfigurationProperties` can be paired with **Spring Boot Configuration Processor** to generate configuration metadata. In Maven projects, you can configure the annotation processor according to the build setup; in Gradle, the appropriate `annotationProcessor` configuration is typically used.

Metadata helps IDEs recognize keys such as:

```text
app.access.retry-count
app.access.connect-timeout
app.access.gateways
app.access.quotas
```

and provide autocompletion, descriptions, data types, or defaults depending on declared info.

With `@Value("${app.retry-count}")`, the annotation itself **does not generate equivalent configuration group metadata**. If a system defines many custom keys, this is a practical reason to group them under `@ConfigurationProperties`.

Metadata aids development and documentation, yet **does not replace runtime value checks**. IDE autocompletion for a key does not guarantee the deployment environment supplied a valid value.

## 16. Hands-on lab: comparing the same data with `@Value` and `@ConfigurationProperties`

This lab uses Java 17, Spring Boot 3.3.x with `spring-boot-starter`. All files and classes live in package `example.bindinglab`.

### Step 1 — create `application.yaml`

At `src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: binding-lab

demo:
  item-price: 12.50

app:
  access:
    enabled: true
    retry-count: 4
    connect-timeout: 3s

    gateways:
      - name: primary
        url: https://primary.example.test
        timeout: 2s
      - name: backup
        url: https://backup.example.test
        timeout: 5s

    quotas:
      standard:
        max-requests: 50
        window: 1m
      premium:
        max-requests: 500
        window: 5m
```

### Step 2 — create a record holding structured configuration

`src/main/java/example/bindinglab/AccessProperties.java`:

```java
package example.bindinglab;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.access")
public record AccessProperties(
        boolean enabled,
        int retryCount,
        Duration connectTimeout,
        List<Gateway> gateways,
        Map<String, Quota> quotas
) {
    public record Gateway(
            String name,
            URI url,
            Duration timeout
    ) {
    }

    public record Quota(
            int maxRequests,
            Duration window
    ) {
    }
}
```

### Step 3 — application demonstrating both access methods

`src/main/java/example/bindinglab/BindingLabApplication.java`:

```java
package example.bindinglab;

import java.math.BigDecimal;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class BindingLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfig(
            AccessProperties access,
            @Value("${demo.item-price}") BigDecimal itemPrice,
            @Value("${app.access.retry-count}") int retries,
            @Value("${app.access.gateways[0].name}") String firstGateway
    ) {
        return args -> {
            System.out.println("itemPrice=" + itemPrice);
            System.out.println("retryCountByValue=" + retries);
            System.out.println("firstGatewayByValue=" + firstGateway);

            System.out.println("enabled=" + access.enabled());
            System.out.println("connectTimeout=" + access.connectTimeout());
            System.out.println("gateways=" + access.gateways().size());
            System.out.println("firstGatewayUrl="
                    + access.gateways().get(0).url());
            System.out.println("standardQuota="
                    + access.quotas().get("standard").maxRequests());
        };
    }
}
```

Observations:

- `@Value` reads three single values, including one key indexed by `[0]`.
- `AccessProperties` represents the entire configuration tree.
- `List<Gateway>` and `Map<String, Quota>` structures are handled by the Binder.
- The same `Environment` provides the data, while the two APIs have different capabilities and purposes.

### Step 4 — run the application

Via Maven wrapper:

```bash
./mvnw spring-boot:run
```

Or package and run the project's actual JAR name:

```bash
java -jar app.jar
```

Expected key output lines:

```text
itemPrice=12.50
retryCountByValue=4
firstGatewayByValue=primary
enabled=true
connectTimeout=PT3S
gateways=2
firstGatewayUrl=https://primary.example.test
standardQuota=50
```

This is non-sensitive sample data for illustration; never print passwords or tokens when experimenting in real projects.

### Step 5 — try overriding via environment variable

For property `app.access.retry-count`, the canonical environment variable is:

```text
APP_ACCESS_RETRYCOUNT
```

Bash:

```bash
APP_ACCESS_RETRYCOUNT=9 java -jar app.jar
```

PowerShell:

```powershell
$env:APP_ACCESS_RETRYCOUNT = '9'
java -jar .\app.jar
```

When no higher-precedence source intervenes, both the Binder and the canonical placeholder can receive `9`.

This example shows the benefit of writing:

```java
@Value("${app.access.retry-count}")
```

instead of coupling Java code to camelCase `retryCount`.

### Step 6 — add another gateway

Append an element:

```yaml
      - name: reporting
        url: https://reporting.example.test
        timeout: 10s
```

to the `gateways` list at the proper YAML indentation level. After restarting the application, `AccessProperties.gateways()` can hold three elements without adding a new injection point for each field.

This is the scalability difference: **data size can change while the Java model remains untouched**.

### Step 7 — add more quota tiers

Add under `quotas`:

```yaml
      enterprise:
        max-requests: 5000
        window: 10m
```

When the Binder picks up the new configuration, `access.quotas()` includes the `enterprise` entry. With individual `@Value` fields, you would have to write additional code for the new key or build a dynamic lookup mechanism manually.

## 17. Are there still times to use `@Value`?

Yes. Do not go to the extreme of creating a `@ConfigurationProperties` class for every single configuration read.

Cases where `@Value` fits:

- A small bean needs one known string such as a test bucket name, simple flag, or timeout.
- A setting is used in exactly one place with no nested structure.
- A SpEL expression is genuinely needed, such as a computation or accessing a bean per Spring Framework rules.
- A single parameter in a `@Bean` method configuring a third-party component.

Example:

```java
@Configuration
class HttpClientSetup {

    @Bean
    MyClient myClient(
            @Value("${app.client.base-url}") String baseUrl
    ) {
        return new MyClient(baseUrl);
    }
}
```

Here `MyClient` is an illustrative class provided by the project or a library. When there is only one clear key, adding a new configuration class may be unnecessary.

However, if `MyClient` needs `baseUrl`, `readTimeout`, `connectTimeout`, `retryCount`, a header list, proxy settings, and TLS, creating a `@ConfigurationProperties` group is usually beneficial.

An intermediate option is injecting `Environment` when you truly need key lookup determined at runtime:

```java
@Service
class DynamicLookupService {

    private final Environment environment;

    DynamicLookupService(Environment environment) {
        this.environment = environment;
    }

    String getLabel(String name) {
        return environment.getProperty("app.labels." + name);
    }
}
```

This illustrates **dynamic lookup**, not a general replacement for type-safe binding. When key names are determined by external input, validate the input and never allow callers to freely query configuration secrets.

## 18. Common mistakes when using `@Value`

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Environment variable is set, yet `@Value` misses it | Placeholder does not use canonical form | Write `${app.item-price}` instead of `${app.itemPrice}` when canonical key is `item-price` |
| Can read `list[0]`, yet cannot get `List<...>` | Placeholder accesses only a single element | Use `@ConfigurationProperties` for lists |
| `@Value("${app.map}")` does not produce a Map | There is no single scalar key holding the entire Map | Use the Binder to bind subkeys |
| JSON/SpEL with complex quotes fails | Manual string concatenation inside expression | Use typed configuration instead of nested SpEL strings |
| Bean reports missing placeholder | Key has no value or is misspelled | Check sources, canonical name, and appropriate default |
| Converting string to number/Duration fails | Wrong-type value or missing converter | Fix source value, declare explicit type, add validation |
| `@Value` value differs from YAML | Another source has higher precedence | Check profiles, environment variables, JVM flags, and CLI args |
| Profile-specific list loses previous elements | Binder replaces the entire list from higher-precedence source | Declare the complete list for the profile or redesign |
| `Map` loses `/` in keys | Missing bracket notation | Use `[/key]` or YAML `"[/key]"` |
| IDE does not autocomplete custom keys | Only using `@Value`, lacking metadata | Group config into `@ConfigurationProperties`, configure processor |
| Field injection is hard to test | Bean is tied to Spring context | Prefer constructor injection or configuration beans |
| Value is present yet business rules fail | Missing group-level configuration validation | Apply `@Validated` and appropriate constraints |

### 18.1. When diagnosing, distinguish naming errors from precedence errors

Example:

```properties
app.client.connect-timeout=3s
```

And:

```bash
java -jar app.jar --app.client.connect-timeout=8s
```

If the application receives `8s`, that is **source precedence**, not a name-binding bug. Conversely, if `APP_CLIENT_CONNECTTIMEOUT` is present in the environment yet a camelCase placeholder misses it, the cause may be **how the placeholder was written**.

Separating the root cause correctly prevents changing file formats unnecessarily or adding duplicate keys to "patch" a different issue.

### 18.2. Observing the final value via `Environment`

Inside a bean in a test environment:

```java
@Bean
ApplicationRunner inspect(Environment env) {
    return args -> {
        System.out.println(
                env.getProperty("app.access.retry-count")
        );
    };
}
```

This is a `@Bean` method placed inside a `@Configuration` or `@SpringBootApplication` class, not a standalone Java program. It lets you inspect one key. When investigating causes, you can pair it with the `env` and `configprops` actuator endpoints if enabled and properly secured.

**Security note:** never expose secrets in logs or leave sensitive actuator endpoints open to public access. Diagnostic endpoints can reveal configuration structure and metadata if not properly restricted.

## 19. How to migrate from multiple `@Value` annotations to a typed model

Initial code might look like:

```java
@Service
public class MailSender {

    @Value("${app.mail.host}")
    private String host;

    @Value("${app.mail.port:25}")
    private int port;

    @Value("${app.mail.retry-count:3}")
    private int retryCount;

    @Value("${app.mail.from-address}")
    private String fromAddress;
}
```

As the number of values grows, changing the prefix requires editing every injection point. Group them into:

```java
package example.mail;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        String host,
        @DefaultValue("25") int port,
        @DefaultValue("3") int retryCount,
        String fromAddress
) {
}
```

After registering with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, switch the bean to constructor injection:

```java
@Service
public class MailSender {

    private final MailProperties config;

    public MailSender(MailProperties config) {
        this.config = config;
    }

    // When sending mail, use config.host(), config.port(), ...
}
```

As the application adds recipient settings, TLS, or connection pooling, you can expand `MailProperties` instead of attaching dozens of `@Value` fields to business beans.

Practical migration steps:

1. List the `@Value` keys currently used within the same functional group.
2. Standardize canonical names (`app.mail.retry-count`) and prefix (`app.mail`).
3. Create a `@ConfigurationProperties` type with the corresponding fields.
4. Move defaults into the configuration model or config documents per project conventions.
5. Add validation if business constraints apply.
6. Register the configuration bean.
7. Inject the configuration model into beans consuming those values.
8. Run the application with default configuration and a profile configuration to verify actual values.

Do not create two competing models—half the settings in scattered `@Value` annotations and half in `@ConfigurationProperties`—when the values belong to the same business domain.

## 20. Knowledge check through scenarios

### Scenario 1 — writing key names

Given sources:

```properties
demo.itemPrice=14.50
```

or:

```text
DEMO_ITEMPRICE=14.50
```

You have two injection points:

```java
@Value("${demo.item-price}")
BigDecimal a;
```

```java
@Value("${demo.itemPrice}")
BigDecimal b;
```

**Question:** Which style is recommended by Spring Boot when Binder-compatible relaxed lookup logic is needed?

**Answer:** `${demo.item-price}`, because it is the canonical kebab-case form. `${demo.itemPrice}` should not be assumed to match all variants of `demo.item-price` and `DEMO_ITEMPRICE`.

### Scenario 2 — YAML list

```yaml
app:
  regions:
    - apac
    - eu
```

**Question:** Why should you not assume `@Value("${app.regions}") List<String>` always works like `@ConfigurationProperties`?

**Answer:** YAML list data is typically represented via indexed keys when generating properties, with no guaranteed scalar `app.regions` for a placeholder to convert. The Binder has dedicated logic to read the entire list; `@Value` does not provide the same capability on its own.

### Scenario 3 — list of objects

```yaml
app:
  nodes:
    - host: a.example.test
      weight: 3
    - host: b.example.test
      weight: 1
```

**Question:** Which model makes sense?

**Answer:**

```java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Node> nodes) {
    public record Node(String host, int weight) {}
}
```

Because element count and structure can change without adding hardcoded index-based `@Value` code.

### Scenario 4 — Map with special characters

```yaml
app:
  labels:
    "[/core]": critical
```

**Question:** Why must `[/core]` be kept as a quoted YAML key?

**Answer:** Bracket notation instructs the Binder to preserve the `/` character in the Map key; YAML requires quoting the bracketed key to represent it properly.

### Scenario 5 — CSV and YAML are not identical sources

Source A:

```properties
app.names=a,b,c
```

Source B:

```yaml
app:
  names:
    - a
    - b
    - c
```

**Question:** If `@Value` converts Source A's string into `List<String>`, can you conclude it automatically binds Source B's data too?

**Answer:** No. Source A is a CSV scalar, while Source B is a YAML list structure. `@ConfigurationProperties` is the more stable choice when list data needs to support multiple formats.

### Scenario 6 — list overridden by profile

Base configuration has 2 nodes; the `dev` document declares only 1 node. What list does the Binder typically produce for `List<Node>` in `dev`?

**Answer:** A one-element list from the higher-precedence source, without appending elements from the base list. The profile document must declare the complete list as needed.

### Scenario 7 — SpEL capability

**Question:** If the application genuinely needs to evaluate a SpEL expression at bean creation, does `@ConfigurationProperties` directly replace `@Value("#{...}")`?

**Answer:** No. SpEL is a capability of `@Value`, whereas the `@ConfigurationProperties` Binder does not evaluate expressions the same way. Choose based on actual need; avoid using SpEL as a complex substitute for structured configuration.

### Scenario 8 — constrained configuration

A service requires `retry-count >= 0` and every gateway must have a URL. Is putting defaults in `@Value` enough?

**Answer:** Not yet. Defaults only cover missing values; they do not replace validation. Model the configuration group with types, add the corresponding Bean Validation constraints, and fail configuration errors at startup.

## 21. Selection rules for projects

When adding configuration, walk through this decision chain:

```text
Only a single standalone scalar value?
      |
      +-- Yes --> Can use @Value or Environment
      |
      +-- No
            |
            v
Multiple fields with the same prefix / same domain?
      |
      +-- Yes --> @ConfigurationProperties
            |
            v
Has List / Map / nested objects / validation?
      |
      +-- Yes --> Prefer @ConfigurationProperties
```

Practices to maintain:

1. Use **canonical kebab-case names** for keys in files and `@Value` placeholders.
2. Do not assume `@Value` has **full relaxed binding** like the Binder.
3. Do not use a single placeholder to implicitly convert an entire YAML tree into a Java object.
4. For configuration lists, bind `List<T>` with the Binder; do not hardcode indices across multiple `@Value` annotations.
5. For `Map`s, pay attention to bracket notation when keys contain special characters.
6. If SpEL is truly needed, use `@Value` deliberately and avoid unnecessary expressions.
7. For property groups, use `@ConfigurationProperties` and constructor injection to reduce scattering.
8. Treat defaults and validation as two distinct mechanisms.
9. Check effective configuration sources before concluding the error lies in the key name.
10. Never print or expose secrets during diagnostics.

## 22. Summary

The most important point is not how many string types `@Value` can convert, but that **it does not share the same configuration binding model as `@ConfigurationProperties`**.

```text
@Value("${app.some-key}")
       |
       v
Resolve placeholder / SpEL
       |
       v
Convert value for a single injection point
```

Whereas:

```text
@ConfigurationProperties(prefix = "app")
       |
       v
Binder reads a prefix-grouped set of keys
       |
       +-- relaxed binding
       +-- simple data types
       +-- List / Map
       +-- nested objects
       +-- appropriate defaults / validation
       |
       v
A typed Java configuration object
       |
       v
Other beans consume it via DI
```

In Spring Boot 3.3, treat `@Value` as a great tool for **a few standalone values or SpEL**, and `@ConfigurationProperties` as the primary tool for **structured application configuration**. Canonical placeholders help `@Value` avoid name-binding pitfalls, yet do not turn it into a full Binder. As configuration grows into lists, maps, nested objects, and constraints, move to a typed model to minimize code changes and make final values easier to reason about.

## References

- Spring Boot 3.3 Reference — Externalized Configuration, sections **@ConfigurationProperties vs. @Value**, **Relaxed Binding**, **Binding Maps**, **Merging Complex Types**: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — Constructor Binding and Default Values: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework Reference — Using `@Value`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html