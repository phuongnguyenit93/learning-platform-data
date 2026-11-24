# Relaxed Binding and Naming Conventions for Properties and Environment Variables

In a Spring Boot application, the same configuration setting can appear in several places: `application.properties`, `application.yml`, operating system environment variables, Java system properties, or command-line arguments. Each place has its own naming conventions. For example, a property name in a file is commonly written as `app.mail.sender-address`, in Java as `senderAddress`, and in an environment variable as `APP_MAIL_SENDERADDRESS`.

Spring Boot provides **relaxed binding** to map these different representations onto the same configuration structure, especially through `@ConfigurationProperties`. This lets applications maintain one clear configuration model without inventing a separate name per runtime environment.

However, **relaxed does not mean any arbitrary insertion of underscores or dashes is equivalent**. In particular, when translating properties containing dots and dashes into environment variables, you must follow standard rules so configuration is not ignored or interpreted as a different path.

This lesson belongs to **Spring Boot Fundamentals → Application Configuration**, focusing on:

- Understanding what relaxed binding is and where it applies.
- Distinguishing **kebab-case**, **camelCase**, **underscore notation**, and **UPPER_CASE**.
- Accurately converting property names into environment variable names.
- Using `@ConfigurationProperties` for structured configuration.
- Understanding limitations with `@Value`, lists, maps, and multiple configuration sources.
- Investigating common configuration issues without guessing naming combinations at random.

## 1. The problem: one setting, multiple representations

Suppose an application sends email and configures the sender address. The canonical property name we choose is:

~~~properties
app.mail.sender-address=no-reply@example.org
~~~

In Java, the corresponding field might be named:

~~~java
private String senderAddress;
~~~

In production, instead of editing files packaged in the JAR, the operations team wants to supply the configuration via an environment variable:

~~~bash
export APP_MAIL_SENDERADDRESS=notifications@example.org
~~~

The three representations above describe the same logical setting:

~~~text
application.properties     app.mail.sender-address
                                  |
                                  | relaxed binding
                                  v
Java configuration bean    senderAddress
                                  ^
                                  | relaxed binding
                                  |
Environment variable      APP_MAIL_SENDERADDRESS
~~~

The goal is for Java code to read **one strongly typed property** while Spring Boot handles interpreting property names according to each configuration source's convention.

Without this mechanism, applications could end up writing manual branches calling `System.getenv(...)`, parsing strings, checking defaults, and resolving conflicts between files and environment variables.

### Property name vs. property value

Relaxed binding primarily concerns **how names are matched**. After identifying the property, Spring Boot also performs **value conversion** into Java types such as `int`, `Duration`, `DataSize`, `boolean`, enums, or lists.

For example:

~~~properties
app.mail.retry-interval=15s
~~~

The name `retry-interval` binds to the `retryInterval` field, while the string `15s` converts to `Duration`. These are two related yet distinct capabilities: **name normalization** and **value type conversion**.

## 2. What is relaxed binding?

**Relaxed binding** is the Spring Boot Binder's ability to accept valid naming variants when mapping properties from `PropertySource`s onto a configuration object.

Example class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String senderAddress;

    public String getSenderAddress() {
        return senderAddress;
    }

    public void setSenderAddress(String senderAddress) {
        this.senderAddress = senderAddress;
    }
}
~~~

Once registered as a configuration properties bean, this class can receive values across variants of the same property, depending on the source:

| Declaration site | Illustrative syntax |
|---|---|
| `application.properties` | `app.mail.sender-address=...` |
| `application.properties` | `app.mail.senderAddress=...` |
| `application.properties` | `app.mail.sender_address=...` |
| Environment variable | `APP_MAIL_SENDERADDRESS=...` |
| Java field | `senderAddress` |

You can picture the binder matching the `app.mail` namespace and then resolving the `senderAddress` field name according to the source's valid conventions.

**Distinction required:** this example illustrates `@ConfigurationProperties` relaxed binding; it does not assert that every property lookup API or every `PropertySource` type shares identical behavior.

### Relaxed binding is not arbitrary renaming

Names carrying different meanings do not automatically collapse into one just because they look similar:

- `app.mail.sender-address` and `app.mail.server-address` describe two different properties.
- `app.mail.sender-address` and `app.mails.sender-address` belong to different namespaces.
- `app.mail.sender-address` and `app.mail.sender.address` have different dot structures.
- `app.mail.timeout` and `app.mail.timeouts` are not the same.

Relaxed binding exists to support **syntactic variants of the same property**, not to guess intent when someone changes structure or makes a typo.

## 3. Kebab-case is the canonical standard to use

In documentation and application property names, choose **lowercase kebab-case**:

~~~properties
app.mail.sender-address=no-reply@example.org
app.mail.retry-interval=10s
app.mail.max-attempts=3
~~~

This style has clear advantages:

- Namespace segments are separated by dots: `app.mail`.
- Words within a segment are separated by dashes: `sender-address`.
- Lowercase avoids ambiguity.
- Readable and aligned with the canonical naming recommended by Spring Boot.

Comparing naming styles:

| Style | Example | Where commonly used? |
|---|---|---|
| Kebab-case | `sender-address` | Canonical property names in files |
| camelCase | `senderAddress` | Variable/field names in Java |
| Underscore notation | `sender_address` | Variant supported by the binder in certain sources |
| Uppercase env convention | `APP_MAIL_SENDERADDRESS` | Operating system environment variables |

With `@ConfigurationProperties(prefix = "...")`, the **prefix** should also be written in canonical kebab-case: lowercase, dots separating namespaces, and dashes separating words inside each segment.

For example:

~~~java
@ConfigurationProperties(prefix = "integration.mail-service")
public class MailServiceProperties {
    // ...
}
~~~

Writing `integration.mail-service` is clearer than putting camelCase or uppercase characters into the prefix.

## 4. Rules for converting property names to environment variables

Spring Boot defines a standard rule for converting a canonical property name into an environment variable form:

1. **Replace dots (`.`) with underscores (`_`)** to separate namespace segments.
2. **Remove dashes (`-`)** inside property segments; do not turn each dash into a new underscore.
3. **Convert all letters to uppercase**.

Starting from:

~~~text
spring.main.log-startup-info
~~~

Apply step by step:

~~~text
Step 1. Dots become underscores:
spring_main_log-startup-info

Step 2. Remove dashes:
spring_main_logstartupinfo

Step 3. Convert to uppercase:
SPRING_MAIN_LOGSTARTUPINFO
~~~

Result:

~~~bash
export SPRING_MAIN_LOGSTARTUPINFO=false
~~~

More examples:

| Canonical property name | Environment variable per rule |
|---|---|
| `server.port` | `SERVER_PORT` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `app.mail.sender-address` | `APP_MAIL_SENDERADDRESS` |
| `app.mail.retry-interval` | `APP_MAIL_RETRYINTERVAL` |
| `app.report.max-file-size` | `APP_REPORT_MAXFILESIZE` |
| `app.feature.new-dashboard-enabled` | `APP_FEATURE_NEWDASHBOARDENABLED` |
| `integration.mail-service.connect-timeout` | `INTEGRATION_MAILSERVICE_CONNECTTIMEOUT` |

**Common mistake:** `app.mail.sender-address` does not convert under the standard rule to `APP_MAIL_SENDER_ADDRESS`. The `_` character in the env convention replaces **dots**, whereas dashes in `sender-address` must be **removed**.

In other words:

~~~text
app.mail.sender-address
       ^      ^
       |      +-- "-" is removed
       +--------- "." becomes "_"

=> APP_MAIL_SENDERADDRESS
~~~

If an env variable is named `APP_MAIL_SENDER_ADDRESS`, underscore-separated parts can be interpreted as a different property path, such as `app.mail.sender.address`. Avoid naming variables arbitrarily and counting on relaxed binding to guess correctly.

### Why do some env names look long and run together?

For example, `APP_FEATURE_NEWDASHBOARDENABLED` looks less readable than `APP_FEATURE_NEW_DASHBOARD_ENABLED`. This is a consequence of translating from **property structure** to **env structure**.

That does not stop you from designing concise, sensible configuration names. You can choose simpler canonical property names up front. Once a property is published, however, follow the matching env name so two systems do not adopt conflicting conventions.

## 5. Environment variables are not property files

Environment variables belong to a process's execution environment. They do not live inside the JAR and do not need to be declared in `application.properties` for Spring Boot to read them from the environment.

Example in a Linux/macOS shell:

~~~bash
export APP_MAIL_SENDERADDRESS=alerts@example.org
export APP_MAIL_RETRYINTERVAL=20s

java -jar app.jar
~~~

If you only want to set them for a single run:

~~~bash
APP_MAIL_RETRYINTERVAL=20s java -jar app.jar
~~~

In Windows PowerShell:

~~~powershell
$env:APP_MAIL_SENDERADDRESS = "alerts@example.org"
$env:APP_MAIL_RETRYINTERVAL = "20s"

java -jar app.jar
~~~

The values must exist in the **Java process's environment** when the application starts. Changing a variable in a different shell generally does not update a running Java process's environment.

When running via Docker, Kubernetes, an IDE, or a service manager, pass variables to the actual process/container. Having a variable set on the host machine does not mean your container or service automatically receives it.

### Docker Compose example

~~~yaml
services:
  backend:
    image: example/backend:latest
    environment:
      APP_MAIL_SENDERADDRESS: alerts@example.org
      APP_MAIL_RETRYINTERVAL: 20s
~~~

Compose's `environment` section places those variables into the container process's environment. Spring Boot can read them via the corresponding property source as long as the names match application configuration.

For passwords or tokens, use an appropriate secret management mechanism rather than placing real values directly into committable configuration files.

## 6. @ConfigurationProperties: the center of relaxed binding

The clearest way to leverage relaxed binding is grouping related properties into a configuration properties type.

Suppose an application integrates with a notification service. We choose the properties:

~~~properties
app.notification.sender-address=no-reply@example.org
app.notification.retry-interval=5s
app.notification.max-attempts=3
~~~

In Spring Boot 3.x, you can use a Java record:

~~~java
package com.example.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        String senderAddress,
        Duration retryInterval,
        int maxAttempts
) {
}
~~~

Mapping breakdown:

| Canonical property | Record component | Java type |
|---|---|---|
| `app.notification.sender-address` | `senderAddress` | `String` |
| `app.notification.retry-interval` | `retryInterval` | `Duration` |
| `app.notification.max-attempts` | `maxAttempts` | `int` |

The Binder reads the properties and converts values to the target types. For example, `5s` converts to a 5-second `Duration`.

### Registering the configuration properties bean

On the main class:

~~~java
package com.example;

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

`@ConfigurationPropertiesScan` discovers classes annotated with `@ConfigurationProperties` in matching packages and registers them as beans.

Another option is `@EnableConfigurationProperties(NotificationProperties.class)` on a configuration class:

~~~java
@Configuration
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {
}
~~~

When using constructor-bound records as in this example, register them via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, rather than constructing the record yourself in a `@Bean` method and expecting the binder to handle that constructor the same way.

### Using in a service

~~~java
package com.example.notification;

import org.springframework.stereotype.Service;
import com.example.config.NotificationProperties;

@Service
public class NotificationService {

    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }

    public void showRetrySettings() {
        System.out.println(
                "Retry interval: " + properties.retryInterval());
        System.out.println(
                "Max attempts: " + properties.maxAttempts());
    }
}
~~~

The service receives bound, type-converted configuration via dependency injection. It does not need to know whether properties came from YAML, `.properties`, or environment variables.

**Do not print email passwords, access tokens, or secrets** in demo logic or production logs. Here only non-sensitive retry parameters are printed.

## 7. YAML and .properties are equivalent representations

For the `NotificationProperties` example, `application.properties`:

~~~properties
app.notification.sender-address=no-reply@example.org
app.notification.retry-interval=5s
app.notification.max-attempts=3
~~~

Can be written equivalently in `application.yml`:

~~~yaml
app:
  notification:
    sender-address: no-reply@example.org
    retry-interval: 5s
    max-attempts: 3
~~~

In YAML, nested structures represent dot-separated segments. Spring Boot processes the configuration data and the binder maps it to the record:

~~~text
app
 +-- notification
      +-- sender-address  ---> senderAddress
      +-- retry-interval  ---> retryInterval
      +-- max-attempts    ---> maxAttempts
~~~

Do not think of YAML as a completely separate binding mechanism. The end result is still property names and property values.

To avoid confusing conflicts, a project should follow a consistent convention for configuration files and source ordering. Do not declare the same setting in both `application.properties` and `application.yml` just to test whether relaxed binding works.

## 8. Overriding configuration with environment variables

Continuing the example, to keep defaults in a file and override them in deployment environments:

~~~properties
app.notification.sender-address=no-reply@example.org
app.notification.retry-interval=5s
app.notification.max-attempts=3
~~~

Set environment variables:

~~~bash
export APP_NOTIFICATION_SENDERADDRESS=ops@example.org
export APP_NOTIFICATION_RETRYINTERVAL=30s
~~~

When the application runs in a typical Spring Boot setup, values from environment variables can override the corresponding values from the file:

~~~text
notification.senderAddress  = "ops@example.org"
notification.retryInterval  = PT30S
notification.maxAttempts    = 3
~~~

`PT30S` is how `Duration.toString()` formats a 30-second duration, not a requirement on how the source must be written.

An important distinction: **relaxed binding determines which names refer to the same property; property-source precedence determines which value wins when multiple sources declare that property**. These are two independent mechanisms.

### Command-line arguments can also override

For example:

~~~bash
java -jar app.jar --app.notification.retry-interval=45s
~~~

In Spring Boot's normal configuration source order, command-line properties take higher precedence than environment variables and application config files. Thus it normally yields a final value of `45s`.

Do not invent a "global precedence order" based on property spelling. Precedence comes from how `PropertySource`s are ordered by Spring Boot, profiles, config imports, and application customizations. If a project alters property source order, check the actual configuration.

## 9. Does @Value use the same relaxed binding as @ConfigurationProperties?

`@Value` lets you retrieve a property value using a placeholder:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class MailSender {

    @Value("${app.notification.sender-address}")
    private String senderAddress;
}
~~~

Points to keep in mind:

- `@Value` suits a few isolated values.
- `@ConfigurationProperties` suits structured property groups and provides dedicated relaxed binding support.
- Placeholder resolution in `@Value` is **not completely identical** to the binder used by `@ConfigurationProperties`.
- Spring Boot recommends using **canonical kebab-case** names in placeholders to benefit from better lookup across naming variants.

Write:

~~~java
@Value("${app.notification.sender-address}")
private String senderAddress;
~~~

Instead of relying on camelCase:

~~~java
@Value("${app.notification.senderAddress}")
private String senderAddress;
~~~

CamelCase names inside `@Value` may not resolve across the same set of relaxed variants as canonical names. Therefore, stay consistent with canonical spelling even when Java fields use camelCase.

### Default values in @Value

You can supply a simple fallback:

~~~java
@Value("${app.notification.max-attempts:3}")
private int maxAttempts;
~~~

`:3` specifies the default if the placeholder cannot find the property. For multiple related properties, immutable configuration properties and validation are easier to maintain than scattering `@Value` across many beans.

### When to choose which?

| Scenario | Suggestion |
|---|---|
| A single flag or isolated value | `@Value` may suffice |
| A group of related settings | `@ConfigurationProperties` |
| Nested configuration | `@ConfigurationProperties` |
| Structured `List`, `Map`, `Duration`, `DataSize` | `@ConfigurationProperties` |
| Need configuration validation | `@ConfigurationProperties` with Bean Validation |
| Need SpEL expressions | `@Value` supports expressions; `@ConfigurationProperties` binder is not designed to evaluate SpEL |

This lesson focuses on property naming; the final choice also depends on your application's configuration object design.

## 10. Property binding to nested objects

In practice, configuration often has multiple levels:

~~~yaml
app:
  mail:
    smtp:
      host: smtp.example.org
      port: 587
      connect-timeout: 10s
~~~

You can model the corresponding configuration as:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(Smtp smtp) {

    public record Smtp(
            String host,
            int port,
            Duration connectTimeout
    ) {
    }
}
~~~

Properties bind along the paths:

~~~text
app.mail.smtp.host                 -> smtp.host
app.mail.smtp.port                 -> smtp.port
app.mail.smtp.connect-timeout      -> smtp.connectTimeout
~~~

And environment variables can be:

~~~bash
export APP_MAIL_SMTP_HOST=smtp.internal.example.org
export APP_MAIL_SMTP_PORT=2525
export APP_MAIL_SMTP_CONNECTTIMEOUT=15s
~~~

Notice the underscore placement:

- `APP_MAIL_SMTP` corresponds to the `app.mail.smtp` namespace.
- `HOST` or `PORT` are the member names underneath.
- `CONNECTTIMEOUT` corresponds to the single-segment property name `connect-timeout`.

Do not turn `connect-timeout` into `CONNECT_TIMEOUT` out of habit and assume the binder treats it as a single property segment.

## 11. List binding: index rules

For lists, indices sit inside square brackets in canonical property notation:

~~~properties
app.clients[0].base-url=https://api-one.example.org
app.clients[0].max-connections=4
app.clients[1].base-url=https://api-two.example.org
app.clients[1].max-connections=6
~~~

In environment variables, the convention for list indices uses digits surrounded by underscores to represent positions in the path.

For example:

~~~text
app.clients[0].base-url        -> APP_CLIENTS_0_BASEURL
app.clients[0].max-connections -> APP_CLIENTS_0_MAXCONNECTIONS
app.clients[1].base-url        -> APP_CLIENTS_1_BASEURL
~~~

In Java:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ClientProperties(List<Client> clients) {

    public record Client(String baseUrl, int maxConnections) {
    }
}
~~~

Here:

- `clients` is the list.
- `0` and `1` are the element indices.
- `base-url` binds to the Java component `baseUrl`.
- `max-connections` binds to `maxConnections`.

### Writing lists in YAML

~~~yaml
app:
  clients:
    - base-url: https://api-one.example.org
      max-connections: 4
    - base-url: https://api-two.example.org
      max-connections: 6
~~~

This is much easier to read when a list contains many objects or fields.

### Note on list overriding

One critical detail: **when the same list is defined in multiple property sources, Spring Boot normally selects the list from the higher-precedence source rather than merging individual items across sources as an arbitrary merge**.

Suppose a YAML file declares two clients, while an environment variable specifies a client at index 0. Do not assume the client at index 1 in YAML will remain intact as you might guess.

When overriding lists from the environment, confirm the override rules and provide the complete list in the higher-precedence source. For complex lists, a profile-specific config file or `SPRING_APPLICATION_JSON` can be easier to manage than scattered environment variables.

## 12. Maps: key names do not have to be Java property names

Suppose an application maps route names to URLs:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RouteProperties(Map<String, String> routes) {
}
~~~

In `application.properties`, if a map key contains special characters that must be preserved verbatim, use **bracket notation**:

~~~properties
app.routes.[/payments]=https://payments.example.org
app.routes.[/orders]=https://orders.example.org
~~~

In `application.yml`, keys with brackets should be wrapped in quotes:

~~~yaml
app:
  routes:
    "[/payments]": https://payments.example.org
    "[/orders]": https://orders.example.org
~~~

Then the resulting keys are `/payments` and `/orders`, rather than being normalized and stripped of special characters.

Without brackets, the binder may strip unsupported characters from map keys during binding, causing actual keys to differ from what you expect.

### Limitations when map keys come from environment variables

Traditional environment variable names support only a restricted character set. Expressing keys with `/`, dots, or case sensitivity accurately can be difficult or impossible through simple env name conversion.

In particular, when binding maps from system environment variables, keys may be lowercased. If business logic requires **preserving exact key characters**, use YAML/properties with bracket notation, appropriate JSON configuration, or a specialized configuration source.

Do not treat bean-field env naming rules as a universal solution for arbitrary map keys.

## 13. Java fields, prefixes, and env names must align structurally

Given configuration:

~~~java
@ConfigurationProperties(prefix = "payment.gateway")
public record GatewayProperties(
        String apiEndpoint,
        String clientId,
        Duration connectionTimeout
) {
}
~~~

Corresponding canonical properties:

~~~properties
payment.gateway.api-endpoint=https://pay.example.org
payment.gateway.client-id=demo-client
payment.gateway.connection-timeout=5s
~~~

And environment variables:

~~~text
PAYMENT_GATEWAY_APIENDPOINT
PAYMENT_GATEWAY_CLIENTID
PAYMENT_GATEWAY_CONNECTIONTIMEOUT
~~~

Diagram:

~~~text
prefix                         property name
payment.gateway                connection-timeout
       |                              |
       v                              v
PAYMENT_GATEWAY                CONNECTIONTIMEOUT
       |                              |
       +--------------+---------------+
                      |
                      v
       PAYMENT_GATEWAY_CONNECTIONTIMEOUT
~~~

Common mistakes:

- Misspelling the prefix: `payments.gateway` instead of `payment.gateway`.
- Mismatched field name: `connectTimeout` when config uses `connection-timeout`.
- Adding an extra segment: `PAYMENT_GATEWAY_CONNECTION_TIMEOUT` and expecting the third underscore to mean a dash.
- Failing to register the `@ConfigurationProperties` bean.
- Configuration value overridden by a higher-precedence source.

Relaxed binding reduces sensitivity to formatting **within the same logical name**, rather than fixing namespace mismatches.

## 14. How does value type conversion relate?

A few examples:

| Canonical property | Sample value | Suitable Java type |
|---|---|---|
| `app.retry.max-attempts` | `4` | `int` |
| `app.retry.enabled` | `true` | `boolean` |
| `app.retry.delay` | `250ms` | `Duration` |
| `app.upload.max-size` | `10MB` | `DataSize` |
| `app.mode` | `SAFE` | Application enum |
| `app.tags` | Depends on source syntax | `List<String>` |

For example:

~~~java
import java.time.Duration;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.limits")
public record LimitProperties(
        Duration requestTimeout,
        DataSize maxPayloadSize
) {
}
~~~

And:

~~~properties
app.limits.request-timeout=2s
app.limits.max-payload-size=10MB
~~~

In this case:

- `request-timeout` binds to `requestTimeout` via relaxed binding.
- `max-payload-size` binds to `maxPayloadSize`.
- Binder converts `2s` to `Duration`.
- Binder converts `10MB` to `DataSize`.

The `@DataSizeUnit` annotation is only needed when an application specifies a default unit for unitless numbers; it is not required in the example above since `10MB` already carries a unit. That import can be omitted from the illustrative class.

### Value type errors are not property name errors

If you write:

~~~properties
app.limits.request-timeout=tomorrow
~~~

the property name may be completely correct, yet the value cannot convert to `Duration`. When troubleshooting startup failures, distinguish:

- Property not found due to wrong name or wrong source.
- Property found, but value cannot be converted.
- Found and converted, but value violates validation rules.

These are three distinct categories of issues.

## 15. Validation catches missing or invalid configuration

Relaxed binding makes configuration flexible, but does not ensure required properties have valid values. A misspelled property name can leave a field `null` or at an unintended default.

With Spring Boot and Bean Validation, you can constrain a configuration properties record:

~~~java
package com.example.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        @NotBlank String senderAddress,
        @Min(1) int maxAttempts
) {
}
~~~

If the project uses standard Spring Boot starters, ensure an appropriate Bean Validation dependency such as `spring-boot-starter-validation` is present.

Configuration example:

~~~properties
app.notification.sender-address=
app.notification.max-attempts=0
~~~

The configuration binds, yet validation detects values violating constraints. As a result, the application can fail immediately on startup instead of silently running with invalid configuration.

Note that validation does not automatically flag unknown extra properties or every typo. Design configuration clearly and choose a policy for handling unbound values that fits your system requirements.

## 16. PropertySource precedence: one name can have multiple values

Suppose the same property appears in three places:

~~~properties
# application.properties
app.notification.max-attempts=3
~~~

~~~bash
# Process environment
export APP_NOTIFICATION_MAXATTEMPTS=5
~~~

~~~bash
# Command-line args
java -jar app.jar --app.notification.max-attempts=7
~~~

In a typical Spring Boot setup, command-line values take precedence over environment variables, which in turn take precedence over config data packaged inside the application. Thus, the final value is normally `7`.

Important: Spring Boot does not pick based on whether a name is uppercase, camelCase, or kebab-case. It checks the value's source and precedence order once names are matched as equivalent.

### Profiles affect the outcome

Suppose you have:

~~~properties
# application.properties
app.notification.max-attempts=3
~~~

~~~properties
# application-prod.properties
app.notification.max-attempts=6
~~~

When the `prod` profile is activated, profile-specific config can override the base configuration. Higher-precedence sources such as environment or command-line args can still override the result afterward.

Environment variable commonly used to select profiles:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
~~~

However, exact ordering also depends on how the application loads config imports, profiles, external files, and additional `PropertySource`s. When debugging, do not inspect a single property in one file and conclude it is the effective value.

## 17. SPRING_APPLICATION_JSON when env names are not flexible enough

For nested structures or keys awkward to represent as standard env variable names, Spring Boot can read JSON data from `SPRING_APPLICATION_JSON`.

For example:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"notification":{"sender-address":"alerts@example.org","max-attempts":4}}}'
java -jar app.jar
~~~

Equivalent to the property structure:

~~~text
app.notification.sender-address = alerts@example.org
app.notification.max-attempts   = 4
~~~

The advantage is preserving dashes and nesting without reasoning through many underscores.

Keep in mind:

- JSON must be syntactically valid.
- Quoting rules differ across shells and platforms.
- Values are still subject to property-source precedence rules.
- Do not place secrets in publicly visible commands, shell history, or logs.
- A `null` value in JSON does not always "erase" a property present in another source, because property resolution handles null specially.

For complex applications, mounting config files into containers or using a dedicated configuration store remains clearer.

## 18. Comprehensive example: Java record, YAML, and environment variables

Let us configure a service that calls an external API.

### 18.1. Base configuration file

`src/main/resources/application.yml`:

~~~yaml
integration:
  inventory:
    base-url: https://inventory.example.org
    connect-timeout: 3s
    max-retries: 2
    enabled: true
~~~

### 18.2. Record binding the configuration

`InventoryClientProperties.java`:

~~~java
package com.example.inventory;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integration.inventory")
public record InventoryClientProperties(
        String baseUrl,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled
) {
}
~~~

Register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(InventoryClientProperties.class)`.

### 18.3. Service using the configuration

~~~java
package com.example.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryClient {

    private final InventoryClientProperties properties;

    public InventoryClient(InventoryClientProperties properties) {
        this.properties = properties;
    }

    public String targetDescription() {
        return "Inventory endpoint: " + properties.baseUrl()
                + "; timeout: " + properties.connectTimeout()
                + "; retry count: " + properties.maxRetries()
                + "; enabled: " + properties.enabled();
    }
}
~~~

This illustrates reading bound configuration; the service does not perform actual network requests.

### 18.4. Overriding at deployment time

Corresponding environment variable names:

~~~text
integration.inventory.base-url          -> INTEGRATION_INVENTORY_BASEURL
integration.inventory.connect-timeout   -> INTEGRATION_INVENTORY_CONNECTTIMEOUT
integration.inventory.max-retries       -> INTEGRATION_INVENTORY_MAXRETRIES
integration.inventory.enabled           -> INTEGRATION_INVENTORY_ENABLED
~~~

For example:

~~~bash
export INTEGRATION_INVENTORY_BASEURL=https://inventory.internal.example.org
export INTEGRATION_INVENTORY_CONNECTTIMEOUT=8s
export INTEGRATION_INVENTORY_MAXRETRIES=5
export INTEGRATION_INVENTORY_ENABLED=true

java -jar app.jar
~~~

If the environment variables exist in the right process and no higher-precedence source overrides them, the bean receives:

~~~text
baseUrl        = https://inventory.internal.example.org
connectTimeout = PT8S
maxRetries     = 5
enabled        = true
~~~

This lets you deploy the same artifact to multiple environments without recompiling just to change URLs and timeouts.

## 19. When an env var "has no effect", what should you check?

Suppose you set:

~~~bash
export APP_NOTIFICATION_RETRY_INTERVAL=20s
~~~

yet the application still reads the YAML default for `app.notification.retry-interval`. Do not immediately conclude Spring Boot is broken. Check systematically.

### Step 1: identify the actual canonical name

Locate the prefix and Java field:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(Duration retryInterval) {}
~~~

From this, the canonical name is:

~~~text
app.notification.retry-interval
~~~

### Step 2: convert the name per the standard rule

~~~text
app.notification.retry-interval
          |
          v
APP_NOTIFICATION_RETRYINTERVAL
~~~

Avoid inserting underscores in place of dashes.

### Step 3: verify the right process has the variable

On Linux/macOS, before running the application, check:

~~~bash
printenv APP_NOTIFICATION_RETRYINTERVAL
~~~

In PowerShell:

~~~powershell
$env:APP_NOTIFICATION_RETRYINTERVAL
~~~

When running inside a container, inspect the environment inside the container or service config rather than checking only on the host machine.

### Step 4: verify configuration properties registration

If you forgot `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an appropriate registration mechanism, the configuration properties bean may not exist at all.

### Step 5: check for higher-precedence sources

A command-line argument or special configuration source may be overriding the environment value. Identify the **effective value** and which source supplies it.

### Step 6: check conversion and validation errors

The variable may be read, yet its value fails to convert to `Duration` or the target Java type. Inspect stack traces and Spring Boot binding/validation messages.

### Step 7: check when the value is read

If code reads configuration only at startup, changing an environment variable after the application is running will not update Java fields automatically. Some systems use dedicated refresh mechanisms, but that is not automatic behavior for all configuration properties beans.

## 20. Inspecting configuration safely

In development environments, Spring Boot Actuator offers endpoints for viewing configuration details and property bindings, such as `/actuator/env` and `/actuator/configprops`, provided the project includes the Actuator starter and endpoints are configured to allow access.

These endpoints help verify:

- Whether a property name was recognized.
- Which source supplied the final value.
- Which groups configuration properties beans bound into.
- Whether any setting was unexpectedly overridden.

However, **this is potentially sensitive operational data**. Do not expose these endpoints to the public Internet just to debug; Spring Boot provides value masking, yet you still need proper authorization, access limits, and display configuration.

Safety practices:

- Avoid dumping the entire `Environment` into logs.
- Never print passwords, tokens, or connection strings containing credentials.
- When explaining bound values, log only property names, source types, and safe fields.
- Use environment-separated configuration and secret management in production.

## 21. Common mistakes and misconceptions

| Misconception | Why it is wrong | Proper approach |
|---|---|---|
| "Dashes turn into underscores" | Canonical env rule **removes** dashes | `retry-interval` produces `RETRYINTERVAL` |
| "Extra underscores in env are harmless" | Underscores separate namespace segments | Start from canonical property name and convert |
| "@Value is completely identical to @ConfigurationProperties" | Placeholder lookup and Binder do not share identical capabilities | Use `@ConfigurationProperties` for configuration groups |
| "If a property is in the file, it is guaranteed to be used" | Higher-precedence sources can override it | Inspect property sources and active profiles |
| "Changing env while the app runs updates beans automatically" | Binding normally happens when beans are created | Restart or design a dedicated refresh mechanism |
| "Lists from YAML and env always merge item by item" | Lists have different override rules than maps | Check which source wins and declare the full list |
| "Relaxed binding fixes misspelled names" | Binder does not guess new namespaces | Match prefix and field names accurately |
| "Java fields must be written in kebab-case" | Java uses camelCase; kebab-case is for canonical property names | Keep Java idiomatic and canonical properties consistent |
| "Special map keys are always preserved without brackets" | Binder may normalize or strip characters | Use bracket notation and YAML quoting |
| "If the property name is right, it will definitely run" | Values can still fail conversion or validation | Verify conversion and constraints |

## 22. Practice exercises

### Exercise 1: Converting property names to env

Without code generation tools, convert by hand:

1. `server.port`
2. `app.payment.max-retries`
3. `feature.user-profile.show-avatar`
4. `spring.main.log-startup-info`

**Answers:**

~~~text
server.port                     -> SERVER_PORT
app.payment.max-retries         -> APP_PAYMENT_MAXRETRIES
feature.user-profile.show-avatar -> FEATURE_USERPROFILE_SHOWAVATAR
spring.main.log-startup-info    -> SPRING_MAIN_LOGSTARTUPINFO
~~~

Check: only dots become underscores; dashes are removed.

### Exercise 2: Binding Duration and boolean

Create record:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        Duration pollInterval,
        boolean enabled
) {
}
~~~

Then declare:

~~~properties
app.worker.poll-interval=1500ms
app.worker.enabled=true
~~~

Register the configuration properties bean and inject it into a service. Try overriding with:

~~~bash
export APP_WORKER_POLLINTERVAL=3s
export APP_WORKER_ENABLED=false
~~~

Observe the bound values of `pollInterval` and `enabled`. No Java code changes are needed when moving from the config file to environment variables.

### Exercise 3: Checking precedence

Keep in the file:

~~~properties
app.worker.enabled=true
~~~

Set in the environment:

~~~bash
export APP_WORKER_ENABLED=false
~~~

And run:

~~~bash
java -jar app.jar --app.worker.enabled=true
~~~

Predict the outcome and explain why. With standard default source configuration, command-line arguments have higher precedence than env and files.

### Exercise 4: Spotting configuration mistakes

A teammate declares:

~~~java
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(int maxFileSize) {
}
~~~

Then sets:

~~~bash
export APP_REPORT_MAX_FILE_SIZE=10
~~~

Tasks:

1. Write the canonical property name for `maxFileSize`.
2. Convert it following the proper env rule.
3. Explain why the env name the teammate used does not follow the standard conversion.
4. Add appropriate validation if the maximum size must be greater than 0.

**Hint:** canonical property is `app.report.max-file-size`; the standard env name is `APP_REPORT_MAXFILESIZE`.

### Exercise 5: Endpoint lists

Write YAML configuration:

~~~yaml
app:
  destinations:
    - name: primary
      url: https://primary.example.org
    - name: secondary
      url: https://secondary.example.org
~~~

Create `@ConfigurationProperties(prefix = "app")` with `List<Destination> destinations`. Then determine the env names for `app.destinations[0].url` and `app.destinations[1].name`.

**Answer:**

~~~text
APP_DESTINATIONS_0_URL
APP_DESTINATIONS_1_NAME
~~~

Try overriding the list from env and observe replacement behavior across property sources rather than assuming Spring Boot merges element by element.

## 23. Best practices in real projects

A Spring Boot project spanning multiple environments is easier to maintain when adopting these rules:

1. **Name canonical properties in lowercase kebab-case**, under an application namespace prefix such as `app.mail` or `integration.inventory`.
2. **Use `@ConfigurationProperties` for groups of related properties**, especially when nested structure, conversion, and validation are needed.
3. **Derive environment variable names from canonical names using the official rule**: dots → underscores, dashes → removed, uppercase.
4. **Avoid writing direct `System.getenv(...)` calls for every setting** unless specifically required; let Spring Boot merge sources.
5. **Do not confuse naming with precedence**: multiple sources can supply the same property, and the effective value depends on source order.
6. **Be careful with lists and maps**: indices, keys with special characters, and merge rules have specific behaviors.
7. **Validate essential configuration** so missing or invalid data is caught as early as possible.
8. **Limit exposing configuration in logs and Actuator**, especially secrets.
9. **Document canonical property names in deployment docs**, alongside matching env names, so dev and ops teams do not have to guess.

A minimal deployment reference table might look like:

| Property | Environment variable | Example | Meaning |
|---|---|---|---|
| `app.notification.sender-address` | `APP_NOTIFICATION_SENDERADDRESS` | `noreply@example.org` | Sender address |
| `app.notification.retry-interval` | `APP_NOTIFICATION_RETRYINTERVAL` | `10s` | Retry backoff duration |
| `app.notification.max-attempts` | `APP_NOTIFICATION_MAXATTEMPTS` | `3` | Maximum retry attempts |
| `app.notification.enabled` | `APP_NOTIFICATION_ENABLED` | `true` | Enable/disable feature |

Tables like this are invaluable in Docker Compose, Kubernetes manifests, Helm values, CI/CD pipelines, and project onboarding docs.

## Conclusion

**Relaxed binding** enables Spring Boot to map multiple valid property name variants onto the same Java field, especially when using `@ConfigurationProperties`. As a result, code can keep natural camelCase names while config files use canonical kebab-case.

For environment variables, the most important rule is: **replace dots with underscores, remove dashes, and convert to uppercase**. For instance, `app.mail.sender-address` becomes `APP_MAIL_SENDERADDRESS`, not automatically `APP_MAIL_SENDER_ADDRESS`.

Distinguish **name matching** from **configuration source precedence** and **value type conversion**. Combining consistent property names, `@ConfigurationProperties`, validation, and safe configuration inspection allows a Spring Boot application to run the same artifact across environments while remaining clear, deployable, and easy to troubleshoot.
