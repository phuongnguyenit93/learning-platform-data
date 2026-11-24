# Distinguishing Prefix Rules from Member Property Naming Rules in Spring Boot

## 1. Why distinguish the two sets of rules?

When using `@ConfigurationProperties`, we commonly see an annotation containing a `prefix` and a class with multiple fields or record components. These two kinds of names are related, yet they do not follow the same degree of flexibility.

Example:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "store.order-processing")
public record OrderProperties(
        int batchSize,
        String defaultCurrency,
        boolean auditEnabled) {
}
~~~

The `application.yaml` file:

~~~yaml
store:
  order-processing:
    batch-size: 100
    default-currency: VND
    audit-enabled: true
~~~

There are three naming layers here:

1. **Prefix in the annotation:** `store.order-processing` identifies the group of keys to read.
2. **Java member names:** `batchSize`, `defaultCurrency`, `auditEnabled` follow Java naming conventions.
3. **Key names from configuration sources:** `batch-size`, `default-currency`, `audit-enabled` represent the corresponding members in YAML.

Spring Boot has a **relaxed binding** mechanism that connects different spellings of source key names to Java members. However, the `prefix` value in the annotation **must be written in canonical, lowercase kebab-case**.

Visualize this:

~~~text
@ConfigurationProperties(prefix = "store.order-processing")
                                  |____________________|
                                         PREFIX

application.yaml:
store:
  order-processing:
    batch-size: 100
    default-currency: VND

store.order-processing.batch-size
|____________________| |________|
        prefix           member name

Java:
int batchSize;
    |_______|
  Java member
~~~

Core takeaway: **relaxed binding for property names does not mean every casing style is valid where the prefix is declared**.

## 2. Prefix is the namespace of a configuration group

A prefix defines the common leading portion of keys bound into a bean.

~~~java
@ConfigurationProperties(prefix = "payment.gateway")
public record GatewayProperties(
        String apiUrl,
        int connectionTimeout) {
}
~~~

Canonical configuration names:

~~~properties
payment.gateway.api-url=https://gateway.example.test
payment.gateway.connection-timeout=5
~~~

Breakdown:

~~~text
payment.gateway.api-url
|_____________| |_____|
     prefix      member

payment.gateway.connection-timeout
|_____________| |________________|
     prefix            member
~~~

The prefix is not a class name, package name, bean name, or field name. It is a **logical namespace** used to organize data inside `Environment`.

For example, two groups can both have a `timeout` member without colliding:

~~~properties
payment.gateway.timeout=10s
notification.email.timeout=3s
~~~

~~~java
@ConfigurationProperties(prefix = "payment.gateway")
public record GatewayProperties(Duration timeout) {
}

@ConfigurationProperties(prefix = "notification.email")
public record EmailProperties(Duration timeout) {
}
~~~

These are two separate configuration groups even though both have a record component named `timeout`.

### Prefix and bean name are not the same

When `@ConfigurationProperties` is registered via configuration scanning or `@EnableConfigurationProperties`, Spring Boot uses a bean-naming convention combining the prefix and the fully qualified class name. However, the **bean name** belongs to the `ApplicationContext` mechanism, while the **prefix** only specifies the property path for the Binder.

A prefix like `payment.gateway` does not force you to name the class `PaymentGateway` or place it in a `payment.gateway` package.

## 3. Canonical rules for the `@ConfigurationProperties` prefix

Spring Boot 3.3 documentation requires the annotation's `prefix` value to be written in **lowercase kebab-case**, optionally consisting of multiple dot-separated segments.

Valid examples:

~~~java
@ConfigurationProperties(prefix = "app")
@ConfigurationProperties(prefix = "app.mail")
@ConfigurationProperties(prefix = "my.main-project")
@ConfigurationProperties(prefix = "my.main-project.person")
@ConfigurationProperties(prefix = "service-client.http")
~~~

Forms to avoid in the **annotation prefix position**:

~~~java
// camelCase in prefix, not canonical
@ConfigurationProperties(prefix = "my.mainProject.person")

// Uppercase letters
@ConfigurationProperties(prefix = "My.MainProject.Person")

// Underscore within a segment
@ConfigurationProperties(prefix = "my.main_project.person")

// Written in environment-variable style
@ConfigurationProperties(prefix = "MY_MAINPROJECT_PERSON")
~~~

Where the annotation is declared, write:

~~~java
@ConfigurationProperties(prefix = "my.main-project.person")
~~~

Do not change it to camelCase just because the Java record has a `firstName` field.

### Different delimiters carry different meanings

- Dots `.` separate segments in a configuration name: `my`, `main-project`, `person`.
- Hyphens `-` separate words within the same segment: `main-project`.
- Underscores `_` are used according to the conventions of certain **data sources**, especially environment variables, not as an arbitrary substitute in the annotation prefix.

Choose prefixes based on the **configuration model**, not on Java class naming style.

## 4. How are Java member names mapped by relaxed binding?

Consider a JavaBean:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "my.main-project.person")
public class PersonProperties {

    private String firstName;

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }
}
~~~

The JavaBean property name is `firstName`. In a `.properties` file, the following representations can all bind to that member:

~~~properties
my.main-project.person.first-name=Lan
~~~

~~~properties
my.main-project.person.firstName=Lan
~~~

~~~properties
my.main-project.person.first_name=Lan
~~~

Spring Boot calls this relaxed binding: it does not require the name in the file to match the Java property name character for character.

| Location | Example | What does it mean? |
| --- | --- | --- |
| Annotation `prefix` | `my.main-project.person` | Group root; canonical required. |
| Java member | `firstName` | Field/JavaBean/record component name. |
| Properties or YAML | `first-name` | Recommended kebab-case source name. |
| Properties or YAML | `firstName` | Accepted camelCase variant. |
| Properties or YAML | `first_name` | Accepted underscore variant. |
| Environment variable | `MY_MAINPROJECT_PERSON_FIRSTNAME` | Corresponding OS representation. |

Flexibility at the **source** does not change the annotation:

~~~java
@ConfigurationProperties(prefix = "my.main-project.person")
~~~

### Why write kebab-case in files?

Spring Boot documentation recommends lowercase with hyphens:

~~~properties
my.main-project.person.first-name=Lan
~~~

With a consistent style, readers can easily locate keys in docs, compare YAML with Properties, and derive environment variable names. Relaxed binding is a compatibility tool across sources, not advice to mix every naming style in the same project.

Do not define all three of the following keys with different values in the same file:

~~~properties
my.main-project.person.first-name=Lan
my.main-project.person.firstName=Mai
my.main-project.person.first_name=Hoa
~~~

Even though those names can target the same member, configuring competing variants causes confusion and should not be used as a precedence mechanism.

## 5. Formula for combining prefix and member path

For a flat property, you can derive:

~~~text
Full key name = prefix + "." + member name in config format
~~~

Example:

~~~java
@ConfigurationProperties(prefix = "client.http")
public record HttpProperties(
        String baseUrl,
        int maxConnections) {
}
~~~

Result:

~~~text
client.http.base-url
client.http.max-connections
~~~

Diagram:

~~~text
client.http.max-connections
|_________| |_____________|
   prefix     member name

Java member:
maxConnections
~~~

Do not repeat the prefix inside the Java component name:

~~~java
// Unnecessarily verbose
String clientHttpBaseUrl;
~~~

Cleaner model:

~~~java
@ConfigurationProperties(prefix = "client.http")
public record HttpProperties(String baseUrl) {
}
~~~

You can call `properties.baseUrl()` in Java; the key name remains `client.http.base-url`.

### What if the prefix has no value?

Some configurations may declare `@ConfigurationProperties` without a prefix. In that case, the binder binds at the root of the configuration space. In real applications, however, specifying a clear prefix helps avoid conflicts and makes adding settings easier.

## 6. Complete Spring Boot example: record + scan + service

### 6.1. Define the configuration bean

~~~java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "store.order-processing")
public record OrderProperties(
        int batchSize,
        Duration requestTimeout,
        URI resultEndpoint) {
}
~~~

### 6.2. YAML source

~~~yaml
store:
  order-processing:
    batch-size: 200
    request-timeout: 15s
    result-endpoint: https://results.example.test
~~~

### 6.3. Register the configuration group

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

Place `OrderProperties` under a package scanned by `@ConfigurationPropertiesScan`, or register it explicitly with `@EnableConfigurationProperties(OrderProperties.class)`.

### 6.4. Service receiving the bean

~~~java
package com.example.demo.service;

import com.example.demo.config.OrderProperties;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderProperties properties;

    public OrderService(OrderProperties properties) {
        this.properties = properties;
    }

    public String summary() {
        return "batch=" + properties.batchSize()
                + ", timeout=" + properties.requestTimeout()
                + ", endpoint=" + properties.resultEndpoint();
    }
}
~~~

With the source above, the bound values are:

~~~text
batchSize = 200
requestTimeout = PT15S
resultEndpoint = https://results.example.test
~~~

Three distinct responsibilities:

1. `@ConfigurationPropertiesScan` causes `OrderProperties` to be registered as a configuration bean.
2. The Binder reads data by **prefix**, maps child keys to **members**, and performs type conversion.
3. Spring dependency injection passes the constructed configuration bean into `OrderService`.

Keeping these boundaries clear helps debug accurately: a missing bean is a registration issue, a wrong value is a key-name/source/binding issue, and a service not receiving the bean may be a DI issue.

## 7. Environment variables: how to convert from canonical names?

OS environment variables typically use uppercase and underscores rather than dots and hyphens like Properties names.

To convert a canonical name to an environment variable name, Spring Boot's rules are:

1. Replace dots `.` with underscores `_`.
2. **Remove** hyphens `-`, do not turn them into underscores.
3. Convert to uppercase.

Example:

~~~text
store.order-processing.batch-size
       |
       +-- dots -> underscores
       +-- dashes -> removed
       +-- uppercase
       v
STORE_ORDERPROCESSING_BATCHSIZE
~~~

Conversion table:

| Canonical property | Environment variable |
| --- | --- |
| `app.retry-count` | `APP_RETRYCOUNT` |
| `my.main-project.person.first-name` | `MY_MAINPROJECT_PERSON_FIRSTNAME` |
| `store.order-processing.request-timeout` | `STORE_ORDERPROCESSING_REQUESTTIMEOUT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `client.http.max-connections` | `CLIENT_HTTP_MAXCONNECTIONS` |

A common point of confusion is:

~~~text
app.retry-count  -> APP_RETRYCOUNT
~~~

Do not automatically infer:

~~~text
app.retry-count  -> APP_RETRY_COUNT
~~~

In the documented canonical rule, the `-` character is removed. An extra `_` can be interpreted as a boundary between two name segments and does not always produce the same binding result.

### Example with environment variables and YAML

File:

~~~yaml
store:
  order-processing:
    batch-size: 100
    request-timeout: 10s
~~~

Unix command:

~~~bash
STORE_ORDERPROCESSING_BATCHSIZE=500 \
STORE_ORDERPROCESSING_REQUESTTIMEOUT=30s \
java -jar app.jar
~~~

If no higher-precedence source overrides them, the binder uses:

~~~text
batchSize = 500
requestTimeout = PT30S
~~~

In code, the prefix remains:

~~~java
@ConfigurationProperties(prefix = "store.order-processing")
~~~

You do not need to change the prefix to an environment variable name. The Binder handles the representation matching the source.

**Note:** `System.getenv("STORE_ORDERPROCESSING_BATCHSIZE")` is a JVM API that reads the literal environment variable name. It does not implement Spring Boot's relaxed binding rules on its own.

## 8. Command-line `--key=value` and PropertySource order

By default, Spring Boot adds command-line options starting with `--` to `Environment`.

Example:

~~~bash
java -jar app.jar \
  --store.order-processing.batch-size=750 \
  --store.order-processing.request-timeout=45s
~~~

The command-line source usually has higher precedence than environment variables and Config Data during a normal run. Thus the two values from CLI can override YAML or the OS environment.

This does not change the `prefix` or Java member names. It only changes the **effective input value** for the logical key.

Example with the same property in multiple sources:

~~~text
application.yaml:
  store.order-processing.batch-size = 100

OS environment:
  STORE_ORDERPROCESSING_BATCHSIZE = 500

CLI:
  --store.order-processing.batch-size=750
~~~

In a normal run:

~~~text
OrderProperties.batchSize() = 750
~~~

Therefore, when a bean receives a different value from the file, check `PropertySource` ordering before concluding that the binder mapped it incorrectly.

## 9. Nested objects: shared prefix, multiple member paths

A namespace can contain a deeper structure.

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.messaging")
public record MessagingProperties(
        String senderName,
        Smtp smtp) {

    public record Smtp(
            String host,
            int port,
            Duration connectionTimeout) {
    }
}
~~~

YAML:

~~~yaml
app:
  messaging:
    sender-name: Operations
    smtp:
      host: smtp.example.test
      port: 2525
      connection-timeout: 5s
~~~

Keys:

~~~text
app.messaging.sender-name
app.messaging.smtp.host
app.messaging.smtp.port
app.messaging.smtp.connection-timeout
~~~

Distinguish:

- The prefix is `app.messaging`.
- Direct members are `senderName` and `smtp`.
- Members of the nested `Smtp` record are `host`, `port`, and `connectionTimeout`.

A `.` after the prefix can be the boundary stepping into a **member object**, without the annotation itself changing.

### Designing a deep prefix instead of a nested object

An alternative:

~~~java
@ConfigurationProperties(prefix = "app.messaging.smtp")
public record SmtpProperties(
        String host,
        int port,
        Duration connectionTimeout) {
}
~~~

The same `app.messaging.smtp.*` key group can be represented by a separate bean. This choice depends on your Java structure and how configuration is reused.

The number of levels in the prefix is **not required** to match the number of nested object levels.

## 10. Lists and indexes: segments of the path

Example:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<Server> servers) {

    public record Server(
            String host,
            int maxConnections) {
    }
}
~~~

YAML:

~~~yaml
app:
  servers:
    - host: host-a.example.test
      max-connections: 10
    - host: host-b.example.test
      max-connections: 20
~~~

Paths:

~~~text
app.servers[0].host
app.servers[0].max-connections
app.servers[1].host
app.servers[1].max-connections
~~~

Here:

- `app` is the prefix.
- `servers` is the list member.
- `[0]` and `[1]` denote elements.
- `max-connections` maps to the `maxConnections` member of `Server`.

### Environment variable form for List elements

Under environment rules, indexes are surrounded by underscores:

~~~text
app.servers[0].max-connections
      |
      v
APP_SERVERS_0_MAXCONNECTIONS
~~~

In practice, list configuration across multiple sources has its own override rules; Spring Boot may replace the entire list from a higher-precedence source rather than merging elements across sources by default. So do not infer from a single index that a list will merge as you might wish.

## 11. Map: distinguishing Java members from data keys

With a Map, distinguish three things:

1. The properties bean's prefix.
2. The Java member name holding the Map.
3. Each entry's data key.

Example:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service.gateway")
public record GatewayProperties(
        Map<String, String> routes) {
}
~~~

YAML:

~~~yaml
service:
  gateway:
    routes:
      north: https://north.example.test
      south: https://south.example.test
~~~

`routes` is the Java member; `north` and `south` are **Map keys**, not fields declared on the class.

### Bracket notation for special keys

If a key contains `/`, Spring Boot provides bracket syntax to preserve the key:

~~~properties
service.gateway.routes[/admin]=https://admin.example.test
service.gateway.routes[/public]=https://public.example.test
~~~

In YAML, keys with brackets must be quoted:

~~~yaml
service:
  gateway:
    routes:
      "[/admin]": https://admin.example.test
      "[/public]": https://public.example.test
~~~

Without brackets, characters outside alphanumeric characters, `-`, or `.` may be stripped from the key during binding.

For Maps whose keys contain dots, the rule also depends on the value type. In `Map<String, String>`, dots can be preserved for scalar keys; in `Map<String, Object>`, dots can create nested levels. Bracket notation makes the intent to preserve the exact key explicit.

Do not arbitrarily apply member-name conversion rules like `first-name` → `firstName` to **Map keys that are user-supplied data**.

## 12. Annotation prefix differs from package scanning

Two annotations can appear side by side:

~~~java
@ConfigurationPropertiesScan("com.example.config")
~~~

and:

~~~java
@ConfigurationProperties(prefix = "app.notifications")
~~~

However, the two strings serve different purposes:

| Mechanism | Path | Meaning |
| --- | --- | --- |
| `@ConfigurationPropertiesScan` | `com.example.config` | Java package to search for properties classes. |
| `@ConfigurationProperties` | `app.notifications` | Configuration namespace in `Environment`. |

A class can live in package `com.example.config` yet use prefix `payment.gateway`. And two classes in two different packages can read related configuration groups if registered properly.

Do not set the prefix to match the package just so "Spring finds the class". That is the responsibility of bean registration.

## 13. `@ConfigurationProperties` prefix differs from `SpringApplication` environment prefix

Spring Boot has another concept with a similar name:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setEnvironmentPrefix("input");
app.run(args);
~~~

`SpringApplication.setEnvironmentPrefix(...)` adjusts how the application reads **OS environment variables**. For instance, when the environment prefix is `input`, a `remote.timeout` property can be loaded from `INPUT_REMOTE_TIMEOUT`.

This differs from:

~~~java
@ConfigurationProperties(prefix = "remote")
public record RemoteProperties(Duration timeout) {
}
~~~

Here `remote` is the prefix selecting the **group of keys bound into an object**.

| Prefix type | Purpose |
| --- | --- |
| `@ConfigurationProperties(prefix="remote")` | Selects the `remote.*` property group for the binder. |
| `SpringApplication.setEnvironmentPrefix("input")` | Adds a prefix convention for OS environment variables read by the app. |

An environment prefix does not mean every key in `application.yaml` must change to `input.remote.timeout`. Spring Boot documentation specifies that this mechanism applies to the environment variable source.

## 14. Prefixes on `@Bean` and setter binding

Not every configuration-binding class uses a record. For a mutable object created by a factory method:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "client.http")
    ClientOptions clientOptions() {
        return new ClientOptions();
    }
}
~~~

Suppose `ClientOptions` is a JavaBean with:

~~~java
public void setBaseUrl(String baseUrl) { ... }
public void setReadTimeout(Duration readTimeout) { ... }
~~~

then:

~~~properties
client.http.base-url=https://api.example.test
client.http.read-timeout=5s
~~~

are bound by the binder through writable properties.

- `@Bean` is responsible for creating the bean.
- `@ConfigurationProperties(prefix = "client.http")` selects the namespace.
- JavaBean properties `baseUrl` and `readTimeout` are binding targets.
- Other beans receive `ClientOptions` via dependency injection.

The factory method name `clientOptions` is **not** a prefix; it relates to the bean name under Spring's rules.

### Constructor binding

With a record:

~~~java
@ConfigurationProperties(prefix = "client.http")
public record ClientProperties(
        String baseUrl,
        Duration readTimeout) {
}
~~~

when registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, the Binder can use the record's canonical constructor to create an immutable object.

In both setter binding and constructor binding, **prefix rules and relaxed member-name rules remain the same**. Only how values are passed into the object differs.

## 15. `@Value` and `Environment` are not identical to the Binder

Spring Boot also allows reading a single key with:

~~~java
@Value("${client.http.base-url}")
String baseUrl;
~~~

or:

~~~java
String baseUrl = environment.getProperty(
        "client.http.base-url");
~~~

These mechanisms read through the `Environment` / property resolution infrastructure. In contrast, `@ConfigurationProperties` uses the Binder to attach Java members according to object structure and relaxed binding.

Do not assume every key-name variant supported by the Binder behaves identically when you directly use `Environment.getProperty(...)` or `@Value` placeholders in all situations.

When writing placeholders, Spring Boot recommends using the canonical name:

~~~java
@Value("${client.http.base-url}")
~~~

instead of arbitrarily switching to camelCase:

~~~java
@Value("${client.http.baseUrl}")
~~~

For a group with many related values, `@ConfigurationProperties` is usually clearer than injecting a series of `@Value` annotations across each service.

## 16. Common errors: prefix or member?

### Error 1: prefix written in camelCase

~~~java
@ConfigurationProperties(prefix = "my.mainProject.person")
public record PersonProperties(String firstName) {
}
~~~

The annotation prefix is not in canonical form; change it to:

~~~java
@ConfigurationProperties(prefix = "my.main-project.person")
~~~

The Java name `firstName` does not need to change.

### Error 2: missing the entire prefix in the file

Java:

~~~java
@ConfigurationProperties(prefix = "data.pipeline")
public record PipelineProperties(String inputDir) {
}
~~~

Source:

~~~properties
input-dir=/tmp/data
~~~

This key is not under the `data.pipeline` namespace. It needs:

~~~properties
data.pipeline.input-dir=/tmp/data
~~~

### Error 3: misspelled member name, not just different casing

~~~properties
data.pipeline.input-dr=/tmp/data
~~~

`input-dr` is not automatically equivalent to `input-dir`. Relaxed binding handles naming variants, **it is not a spell-checker**.

### Error 4: thinking hyphens become underscores in environment variables

~~~text
Canonical: app.retry-count
Standard:  APP_RETRYCOUNT
~~~

Do not arbitrarily write `APP_RETRY_COUNT` and expect it to always match the same path.

### Error 5: YAML config has the right name, yet the bean is unregistered

A class annotated with `@ConfigurationProperties` is not necessarily managed by Spring automatically without `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an appropriate registration mechanism.

This is a **bean registration** issue, not a relaxed member-naming rule issue.

### Error 6: right name, wrong data type

~~~properties
client.http.max-connections=not-a-number
~~~

The Binder located the right `maxConnections` member, but cannot convert the value to `int`. This is a **conversion/binding** error, not a prefix error.

### Error 7: another source overrides it

~~~properties
client.http.max-connections=20
~~~

but run with:

~~~bash
java -jar app.jar --client.http.max-connections=80
~~~

The bean receives 80 due to standard command-line precedence. Inspect `PropertySource`, do not change the prefix.

### Error 8: treating a Map key like a Java field

A `/admin` key in a Map is not equivalent to a Java field named `admin`. If a key contains special characters, check Map binding rules and bracket notation.

### Error 9: primitive defaults hide missing configuration

If a record has `int maxRetries` and the key is absent, do not treat the primitive default as valid configuration. When data is critical, use validation or intentional defaults.

### Error 10: assuming runtime file edits automatically update beans

`@ConfigurationProperties` is typically bound at startup. Editing YAML on disk does not automatically refresh every existing bean; a dedicated refresh mechanism is required if the application needs it.

## 17. How does validation complement naming?

To constrain values:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment.gateway")
public record GatewayProperties(
        @NotBlank String apiUrl,
        @Min(1) int maxRetries) {
}
~~~

Data:

~~~properties
payment.gateway.api-url=https://gateway.example.test
payment.gateway.max-retries=3
~~~

If a compatible Bean Validation provider is present, Spring Boot can validate values at binding time:

- `apiUrl` must not be blank.
- `maxRetries` must be at least 1.

Validation **does not fix** a wrong prefix `payment.gateways` into `payment.gateway` or guess that `max-reties` means `max-retries`. It detects missing or invalid data at the step after the binder locates and assigns properties according to its rules.

## 18. How to diagnose step by step

If `@ConfigurationProperties` does not receive the expected value, check each layer in order:

**Step 1 — Annotation prefix**

~~~java
@ConfigurationProperties(prefix = "client.http")
~~~

Verify canonical form, spelling, dots, and hyphens.

**Step 2 — Java member**

~~~java
int maxConnections;
~~~

For JavaBeans, check getters/setters. For records, check component names and constructor binding.

**Step 3 — Assemble the canonical key**

~~~text
client.http.max-connections
~~~

This is the name to write in files and use as a CLI argument.

**Step 4 — Convert the name if using an environment variable**

~~~text
CLIENT_HTTP_MAXCONNECTIONS
~~~

Apply the exact dot/hyphen rules.

**Step 5 — Check the effective source**

Example with a non-sensitive value:

~~~java
Integer max = environment.getProperty(
        "client.http.max-connections", Integer.class);
~~~

If the value from `Environment` already differs from the file, investigate sources and precedence.

**Step 6 — Check bean/binding mechanics**

Is the bean registered via scan, enable, or factory? Is the record created with appropriate constructor binding? Does the JavaBean have setters and writable structures?

**Step 7 — Type conversion and validation**

If the Binder finds the right path but cannot convert the value, fix the data or target type. If conversion succeeds but the value is nonsensical, add constraints.

In Spring Boot logs, you may encounter missing-bean errors, bind errors, or validation errors. Do not assume every error is caused by `prefix`.

## 19. Practice exercises

### Exercise 1 — identify parts of the name

Class:

~~~java
@ConfigurationProperties(prefix = "shop.checkout")
public record CheckoutProperties(
        int maxItems,
        String defaultLocale) {
}
~~~

Write the two canonical keys.

**Answer:**

~~~properties
shop.checkout.max-items=20
shop.checkout.default-locale=vi-VN
~~~

Prefix = `shop.checkout`; members = `maxItems`, `defaultLocale`.

### Exercise 2 — choose the valid prefix

Options:

A. `my.mainProject.person`

B. `my.main-project.person`

C. `MY_MAINPROJECT_PERSON`

D. `my.main_project.person`

**Answer: B**, because it is the canonical lowercase kebab-case form for the annotation.

### Exercise 3 — relaxing member names

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String senderAddress) {
}
~~~

The following three forms in a Properties source:

~~~properties
app.mail.sender-address=team@example.test
app.mail.senderAddress=team@example.test
app.mail.sender_address=team@example.test
~~~

can all map to `senderAddress`. The **recommended style** for files is `sender-address`; do not use all three at once with different values.

### Exercise 4 — environment variables

Convert three keys:

~~~text
app.retry-policy.max-attempts
payments.credit-card.provider-name
client.http.max-connections
~~~

**Answer:**

~~~text
APP_RETRYPOLICY_MAXATTEMPTS
PAYMENTS_CREDITCARD_PROVIDERNAME
CLIENT_HTTP_MAXCONNECTIONS
~~~

### Exercise 5 — nested objects

~~~java
@ConfigurationProperties(prefix = "app.pipeline")
public record PipelineProperties(Worker worker) {
    public record Worker(int maxParallelJobs) {
    }
}
~~~

**Question:** what is the canonical key for `maxParallelJobs`?

**Answer:** `app.pipeline.worker.max-parallel-jobs`. `app.pipeline` is the prefix; `worker.max-parallel-jobs` is the member path.

### Exercise 6 — same member name in two namespaces

~~~java
@ConfigurationProperties(prefix = "http.client")
public record HttpProperties(int maxConnections) {
}

@ConfigurationProperties(prefix = "database.pool")
public record PoolProperties(int maxConnections) {
}
~~~

Data:

~~~properties
http.client.max-connections=40
database.pool.max-connections=15
~~~

**Answer:** the two beans receive independent values 40 and 15. Having the same Java member name causes no conflict because the prefixes differ.

### Exercise 7 — special Map key

~~~java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(Map<String, String> routes) {
}
~~~

Preserve the key `/v1` in YAML.

**Answer:**

~~~yaml
gateway:
  routes:
    "[/v1]": "https://api.example.test/v1"
~~~

### Exercise 8 — spotting a typo

~~~java
@ConfigurationProperties(prefix = "billing.invoice")
public record InvoiceProperties(int maxRetries) {
}
~~~

~~~properties
billing.invoice.max-retyries=10
~~~

**Answer:** `max-retyries` is a typo; the correct key is `billing.invoice.max-retries`. Relaxed binding does not guess a new name from a typo.

### Exercise 9 — higher-precedence source

~~~yaml
app:
  retry-policy:
    max-attempts: 2
~~~

Run:

~~~bash
java -jar app.jar --app.retry-policy.max-attempts=8
~~~

With a `@ConfigurationProperties(prefix = "app.retry-policy")` bean having `maxAttempts`, the typical effective value is 8, not 2. Prefix and member names are unchanged; the new value source has higher precedence.

### Exercise 10 — distinguishing bean scanning from property groups

~~~java
@ConfigurationPropertiesScan("com.example.config")
~~~

alongside:

~~~java
@ConfigurationProperties(prefix = "feature.delivery")
public record DeliveryProperties(String endpoint) {
}
~~~

**Answer:** `com.example.config` is the **scanned Java package**, while `feature.delivery` is the **configuration namespace**. One string does not replace the other.

## 20. Cheat sheet

| Where used | Rule to follow | Example |
| --- | --- | --- |
| `prefix` in `@ConfigurationProperties` | **Required** canonical lowercase kebab-case | `my.main-project.person` |
| Record/JavaBean member | Java naming, typically camelCase | `firstName` |
| Keys in Properties/YAML | Should use lowercase kebab-case | `my.main-project.person.first-name` |
| Environment variable | Dots to `_`, drop `-`, uppercase | `MY_MAINPROJECT_PERSON_FIRSTNAME` |
| CLI option | Full name in canonical form | `--my.main-project.person.first-name=Lan` |
| Nested object | Append member path after prefix | `app.messaging.smtp.connection-timeout` |
| List | Index between member segments | `app.servers[0].host` |
| Special Map key | Bracket notation when preservation needed | `gateway.routes[/admin]` |
| Java package scan | `@ConfigurationPropertiesScan`, independent of prefix | `com.example.config` |
| Application environment prefix | Applies to OS environment variable names | `input` |

## 21. Summary

When using `@ConfigurationProperties`, separate **two principles**:

- **The prefix is the group name declared in the annotation**. It must be in canonical lowercase kebab-case, e.g., `my.main-project.person`.
- **The member name is the binder's mapping target**. Java can use `firstName`, while Properties/YAML sources recommend `first-name` and the corresponding environment variable uses `FIRSTNAME` inside the full variable name.

Concise example:

~~~java
@ConfigurationProperties(prefix = "my.main-project.person")
public record PersonProperties(String firstName) {
}
~~~

~~~properties
my.main-project.person.first-name=Lan
~~~

~~~text
MY_MAINPROJECT_PERSON_FIRSTNAME=Lan
~~~

These are compatible representations of **one group and one member**, but they are **not directly interchangeable in every syntactic position**. If a bean receives the wrong value, inspect in order: prefix, member path, source spelling, `PropertySource` order, type conversion, and validation. This approach accurately distinguishes namespace errors from member-binding errors.

## References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot — @ConfigurationProperties API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html).
- [Spring Framework — Environment](https://docs.spring.io/spring-framework/reference/core/beans/environment.html).
