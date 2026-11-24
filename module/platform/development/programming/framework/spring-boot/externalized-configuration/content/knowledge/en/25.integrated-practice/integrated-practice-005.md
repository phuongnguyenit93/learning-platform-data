# Modeling Timeouts, Size Limits, and Server Lists with Records

In Spring Boot Externalized Configuration, a system often needs to read three kinds of data together: **wait durations (timeouts)**, **data size limits (data size)**, and **a list of target servers (servers)**. Using a `String` for every value and parsing it manually across multiple services is error-prone: timeouts get misread as milliseconds, size limits confuse MB with bytes, and server entries end up missing URLs or having inconsistent shapes.

An approach suited to Spring Boot 3.x and Java 17+ uses **immutable Java records** combined with `@ConfigurationProperties`, `Duration`, `DataSize`, `List<Server>`, `@DefaultValue`, and Bean Validation. The Spring Boot Binder reads configuration sources, converts values into Java types, builds the record via constructor binding, and—when validation is enabled—rejects configurations that violate the contract.

This practice builds the **`app.transfer`** model for a component that transfers data to multiple upstream servers. The goal is to create **one centralized, type-safe configuration object with clear rules**, avoiding scattered `@Value` annotations; then exercise valid and invalid cases, understand profile override behavior on lists, override via environment variables, read startup errors, and apply security practices.

**Expected learning outcomes:**

- Define an `application.yml` structure for timeouts, data sizes, and server lists.
- Build `TransferProperties` as a record with a nested `Server` record.
- Understand how the Binder converts `2s` to `Duration`, `20MB` to `DataSize`, and YAML sequences to `List<Server>`.
- Distinguish **missing values**, **wrong types**, and **business-rule violations**.
- Set safe defaults using `@DefaultValue`, while requiring a non-empty server list.
- Use `@Validated`, `@Valid`, and Jakarta Validation to check configuration after binding.
- Test binding, defaults, conversion, validation, and profile list replacement.
- Avoid hard-coding secrets in configuration and never log sensitive objects.

Examples use Spring Boot 3.x, Java 17+, Spring Boot configuration binding, and Jakarta Bean Validation. In a real project, keep all starters on the same Spring Boot version and verify specifics of the minor version you run.

---

## 1. Problem Statement: One Configuration with Three Data Types

Suppose an application receives files that must be transferred to different servers. It needs:

1. `connect-timeout`: maximum time allowed for establishing a connection.
2. `read-timeout`: limit for waiting to read data as defined by the application's HTTP client.
3. `max-payload-size`: maximum payload size permitted for processing.
4. `servers`: list of target servers, each having a name, base URL, priority, and its own health timeout.

A readable YAML file:

~~~yaml
app:
  transfer:
    connect-timeout: 2s
    read-timeout: 10s
    max-payload-size: 20MB
    servers:
      - name: primary
        base-url: https://primary.example.test
        priority: 10
        health-timeout: 3s
      - name: secondary
        base-url: https://secondary.example.test
        priority: 20
        health-timeout: 5s
~~~

In this example:

- `2s` represents **2 seconds**, not an ambiguous integer.
- `20MB` is a size value that the Binder converts into `DataSize`.
- `servers` is a **YAML sequence**, making it fit a `List`.
- Both server entries share the same structure and Java type.
- `priority` is an integer used by the application to sort attempt order—**not an automatic load balancer**.
- `base-url` is the target URL represented as a `URI`; whether the server is reachable at runtime is separate from bindability.

**Never put real credentials into URLs in examples.** If an upstream requires a token, manage credentials through a dedicated secret channel and avoid logging URLs carrying secrets.

## 2. Mapping from YAML to Java Record

~~~text
application.yml
  app.transfer
    connect-timeout: "2s"          ──> Duration
    read-timeout: "10s"            ──> Duration
    max-payload-size: "20MB"       ──> DataSize
    servers:                      ──> List<Server>
      - name: "primary"            ──> String
        base-url: "https://..."    ──> URI
        priority: 10               ──> int
        health-timeout: "3s"       ──> Duration
      - name: "secondary"          ──> String
        ...
                      |
                      v
              Spring Boot Binder
          property names + conversion
          record constructor binding
                      |
                      v
          TransferProperties object
             ├─ Duration
             ├─ Duration
             ├─ DataSize
             └─ List<Server> immutable view*
                      |
                      v
            Bean Validation (if enabled)
                      |
                      v
             Consumer service
~~~

Note `*`: Java records are **shallowly immutable**. Reference components like `List<Server>` do not automatically become deeply unmodifiable just by living in a record. Add a defensive copy if you want to prevent consumers from mutating the list.

## 3. Creating a Spring Boot Project with the Right Dependencies

With Maven, a project can use these main dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This example assumes the Spring Boot parent or dependency management manages versions. If the application is a web service, you can add `spring-boot-starter-web`, though configuration binding itself needs no controller.

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-validation` brings in the Bean Validation integration/provider needed so annotations like `@NotBlank`, `@NotEmpty`, and `@Min` are enforced. In Spring Boot 3.x, constraints belong to package `jakarta.validation.*`.

Do not mix legacy `javax.validation.*` imports with the Jakarta API in a Boot 3 application.

## 4. Suggested Source Structure

~~~text
src/
  main/
    java/
      com/example/transfer/
        TransferApplication.java
        config/
          TransferProperties.java
        service/
          TransferPlanner.java
    resources/
      application.yml
      application-dev.yml
      application-prod.yml
  test/
    java/
      com/example/transfer/
        config/
          TransferBindingTest.java
          TransferProfileTest.java
~~~

Keep the configuration group in `config/TransferProperties.java`, while upstream selection logic and data handling belong in `service/`. Do not put network I/O into the record just because it holds `baseUrl`.

## 5. Root Record: TransferProperties

First, build a version with typed fields only:

~~~java
package com.example.transfer.config;

import java.time.Duration;
import java.net.URI;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.transfer")
public record TransferProperties(
    Duration connectTimeout,
    Duration readTimeout,
    DataSize maxPayloadSize,
    List<Server> servers
) {
    public record Server(
        String name,
        URI baseUrl,
        int priority,
        Duration healthTimeout
    ) {}
}
~~~

The line:

~~~java
@ConfigurationProperties(prefix = "app.transfer")
~~~

defines the key namespace the Binder reads. Component `connectTimeout` maps to canonical property `app.transfer.connect-timeout`. Likewise, `maxPayloadSize` maps to `app.transfer.max-payload-size`.

The `record` provides the canonical constructor and accessors `connectTimeout()`, `readTimeout()`, `maxPayloadSize()`, and `servers()`. In Spring Boot 3.x, a record with a single appropriate constructor uses constructor binding automatically when registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

**No setters are needed.** That is a major benefit of records: configuration is instantiated once with clearly typed state.

## 6. Registering the Record Properly

Main application:

~~~java
package com.example.transfer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class TransferApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransferApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` scans eligible configuration properties classes within package scope, creates the beans, and triggers binding.

An alternative:

~~~java
package com.example.transfer.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(TransferProperties.class)
public class TransferConfig {}
~~~

Choose one proper registration mechanism. Do not annotate a constructor-bound record with `@Component` "just so Spring sees the bean": component scanning and Configuration Properties constructor binding construct objects through different paths. With `@Component`, Spring may attempt constructor dependency injection instead of binding values from property sources.

### When Is `@ConstructorBinding` Needed?

For a record with a single canonical constructor in Spring Boot 3.x, `@ConstructorBinding` is typically unnecessary. If a target type has multiple constructors and you must designate which one to bind, check your version's annotation rules; in Boot 3, usage differs from older online examples.

## 7. Writing `application.yml`

~~~yaml
spring:
  application:
    name: transfer-service

app:
  transfer:
    connect-timeout: 2s
    read-timeout: 10s
    max-payload-size: 20MB
    servers:
      - name: primary
        base-url: https://primary.example.test
        priority: 10
        health-timeout: 3s
      - name: secondary
        base-url: https://secondary.example.test
        priority: 20
        health-timeout: 5s
~~~

Indentation is critical. Keys inside a list element must align properly after the `-` marker. If you write:

~~~yaml
app:
  transfer:
    servers:
      name: primary
      base-url: https://primary.example.test
~~~

then `servers` is parsed as a mapping/object rather than the YAML sequence required for `List<Server>`.

A configuration file can parse as valid YAML yet still fail to bind to the Java model due to a shape mismatch. Always check both **YAML syntax** and the **target Java type**.

## 8. `Duration`: Using a Java Type to Avoid Unit Confusion

`Duration` belongs to `java.time.Duration` and represents a length of time. Spring Boot Binder supports unit-suffixed string formats such as:

| YAML/property value | Meaning |
| --- | --- |
| `500ms` | 500 milliseconds |
| `2s` | 2 seconds |
| `3m` | 3 minutes |
| `1h` | 1 hour |
| `PT5S` | ISO-8601 duration, 5 seconds |
| `PT1M` | ISO-8601 duration, 1 minute |

Example:

~~~yaml
app:
  transfer:
    connect-timeout: 750ms
    read-timeout: 2m
~~~

After binding:

~~~java
Duration connect = props.connectTimeout();
Duration read = props.readTimeout();

long connectMillis = connect.toMillis();
long readSeconds = read.toSeconds();
~~~

Avoid writing:

~~~java
int connectTimeout = 2; // 2 what?
~~~

and forcing every caller to remember whether it means seconds or milliseconds. `Duration` communicates semantics and eliminates unit-conversion bugs.

### Unit When Only a Number Is Provided

Spring Boot defines a default unit when binding a bare number to `Duration`; `@DurationUnit` can override that default if needed. However, in this lab's configuration files, **always write `ms`, `s`, `m`, or `h` explicitly** so files are easy to review and do not depend on unit assumptions.

For example:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
Duration connectTimeout
~~~

is an option if you deliberately support bare numbers meaning seconds. Imports:

~~~java
import java.time.temporal.ChronoUnit;
import org.springframework.boot.convert.DurationUnit;
~~~

You do not need this annotation when YAML explicitly writes `2s` and `750ms`.

## 9. Read Timeout and Connect Timeout Have Different Roles

**Connect timeout** normally governs how long establishing a network connection may take. **Read/response timeout** governs waiting for response data or read operations, depending on the HTTP client and transport.

These two properties:

~~~yaml
connect-timeout: 2s
read-timeout: 10s
~~~

do not automatically apply to any HTTP client. They are **typed configuration values** first. When creating `WebClient`, `RestClient`, Apache HttpClient, Reactor Netty, or another SDK client, you must map them onto that library's timeout controls.

Never assume a `readTimeout` API in framework X has identical semantics to `responseTimeout` in framework Y. Always consult the documentation of your actual HTTP client, especially regarding connection pooling, streaming, and idle timeouts.

### Do Not Make Network Requests Inside the Record

A record constructor should build a data object, not probe endpoints over the network. If the Binder pinged all servers on every startup, configuration binding would depend on network availability and risk hanging. Config syntax/value validity is separate from runtime network state.

## 10. `DataSize`: Expressing Sizes with the Right Type

Spring Boot supports binding size strings into `org.springframework.util.unit.DataSize`. Examples:

| Config value | Usage meaning |
| --- | --- |
| `512B` | 512 bytes |
| `256KB` | 256 kilobytes per `DataSize` unit |
| `20MB` | 20 megabytes per `DataSize` unit |
| `1GB` | 1 gigabyte per `DataSize` unit |

Example:

~~~java
import org.springframework.util.unit.DataSize;

DataSize max = props.maxPayloadSize();

long allowedBytes = max.toBytes();
long allowedMegabytes = max.toMegabytes();
~~~

With `max-payload-size: 20MB`, the application never parses `"20MB"` manually. The Binder uses its built-in converter to produce `DataSize`.

**Do not use `String maxPayloadSize` and call `Integer.parseInt(...)` in a service.** Unit-suffixed strings cannot be parsed by `Integer.parseInt`, and manual MB-to-bytes math invites bugs or integer overflow.

### MB, MiB, and Unit Conventions

Spring's `DataSize` uses specific unit definitions (for instance, `DataSize.ofMegabytes(n)` uses the API's binary power-of-two factor). Never write a business spec saying `"20 MB"` and assume every partner uses the same SI vs. IEC convention when exact byte limits matter. When integrating with external APIs, upload limits, or HTTP headers, **compare in bytes** and document the semantics.

Example:

~~~java
long maxBytes = props.maxPayloadSize().toBytes();
if (payloadBytes > maxBytes) {
    throw new IllegalArgumentException(
        "Payload exceeds configured maximum");
}
~~~

`payloadBytes` is the reliably measured byte count. Real measurements should avoid buffering an entire body into memory before checking the limit.

## 11. `DataSize` vs. Actual Web Server Upload Limits

Setting:

~~~yaml
app:
  transfer:
    max-payload-size: 20MB
~~~

**does not automatically change** multipart request limits in Spring MVC, a reverse proxy, an API Gateway, or the servlet container.

If the application accepts multipart uploads through Spring MVC, separate properties apply, such as:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 20MB
      max-request-size: 25MB
~~~

These are **two distinct policies**:

- `app.transfer.max-payload-size`: a business limit enforced by your application code.
- `spring.servlet.multipart.*`: multipart HTTP handling limits enforced by Spring Boot.

With Spring WebFlux, streaming, or external gateways, limits and APIs differ further. Never treat a custom `DataSize` in a record as automatic HTTP request-size protection.

## 12. `List<Server>`: Representing a Server List

Nested record:

~~~java
public record Server(
    String name,
    URI baseUrl,
    int priority,
    Duration healthTimeout
) {}
~~~

represents **one element**. Root property:

~~~java
List<Server> servers
~~~

represents the full list.

YAML requires a sequence:

~~~yaml
servers:
  - name: primary
    base-url: https://primary.example.test
    priority: 10
    health-timeout: 3s
  - name: secondary
    base-url: https://secondary.example.test
    priority: 20
    health-timeout: 5s
~~~

When bound successfully:

~~~java
List<TransferProperties.Server> servers =
    properties.servers();

for (TransferProperties.Server server : servers) {
    System.out.println(server.name());
}
~~~

This example prints only the non-sensitive server name. Never log raw URLs if they might carry tokens or signed query strings. Nor should you log the entire record if you add credentials later.

### Why Is Server `name` Still Useful?

`name` acts as a stable identifier for observability, health status, routing tables, and migrations. However, the Binder **does not enforce uniqueness of names**. If uniqueness is a business rule, add explicit domain validation.

## 13. Equivalent `.properties` Representation

A YAML sequence can also be written using indexed properties:

~~~properties
app.transfer.connect-timeout=2s
app.transfer.read-timeout=10s
app.transfer.max-payload-size=20MB

app.transfer.servers[0].name=primary
app.transfer.servers[0].base-url=https://primary.example.test
app.transfer.servers[0].priority=10
app.transfer.servers[0].health-timeout=3s

app.transfer.servers[1].name=secondary
app.transfer.servers[1].base-url=https://secondary.example.test
app.transfer.servers[1].priority=20
app.transfer.servers[1].health-timeout=5s
~~~

Note that `[0]` and `[1]` are list indices, not part of the Java accessor names. If you omit the index:

~~~properties
app.transfer.servers.name=primary
~~~

do not expect the Binder to assemble a `List<Server>` as intended.

When an application uses a Config Data source, pick one primary format—YAML or `.properties`—rather than maintaining both files with the same basename "just in case". If both exist, understand their format precedence and duplicate-key behavior.

## 14. Adding Defaults with `@DefaultValue` on Records

To avoid repeating every timeout and size across environments, supply explicit defaults for **truly optional values**:

~~~java
import java.time.Duration;
import java.net.URI;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.transfer")
public record TransferProperties(
    @DefaultValue("2s") Duration connectTimeout,
    @DefaultValue("10s") Duration readTimeout,
    @DefaultValue("20MB") DataSize maxPayloadSize,
    List<Server> servers
) {
    public record Server(
        String name,
        URI baseUrl,
        @DefaultValue("10") int priority,
        @DefaultValue("3s") Duration healthTimeout
    ) {}
}
~~~

`@DefaultValue` attaches to constructor parameters/record components in constructor binding. The Binder uses the default string when no property value is present and converts it to the target type.

For example, if YAML supplies only:

~~~yaml
app:
  transfer:
    servers:
      - name: primary
        base-url: https://primary.example.test
~~~

the defaults yield:

~~~text
connectTimeout  = 2s
readTimeout     = 10s
maxPayloadSize  = 20MB
servers[0].priority      = 10
servers[0].healthTimeout = 3s
~~~

**Never supply a default list if the server list is mandatory.** Rather than inventing a fictitious server, require deployments to declare at least one valid server.

### Do Not Confuse `@DefaultValue` with `@Value`

`@DefaultValue("2s")` here is not `@Value("\${...:2s}")`. It belongs to Binder constructor binding, not Spring bean field injection. Keep the two mechanisms distinct.

## 15. Should You Duplicate Defaults in `application.yml` When Using `@DefaultValue`?

Not required. Both work, yet repeating the same default in multiple places increases maintenance cost.

A clear policy example:

- **Type-level semantic defaults**: use `@DefaultValue` so the object behaves consistently when keys are absent.
- **Product operational defaults**: put in `application.yml` so they can change via Config Data without editing Java.
- **Mandatory environment values**: no default; fail fast via validation.
- **Profile-specific values**: put in profile-specific overrides.

In this practice, we use `@DefaultValue` to demonstrate the record binding mechanism. In production systems, pick **one primary source of truth** and write tests for missing-key behavior.

## 16. Records Are Immutable, Yet a `List` May Still Be Mutable

With:

~~~java
public record TransferProperties(
    Duration connectTimeout,
    Duration readTimeout,
    DataSize maxPayloadSize,
    List<Server> servers
) {}
~~~

Java makes the component fields `final`, yet `List<Server>` still references a collection object that may be mutable. A careless consumer calling:

~~~java
properties.servers().clear();
~~~

could succeed if the backing list implementation allows mutation. That breaks "immutable config" because the list contents changed even though the field reference cannot be reassigned.

Protect against this in the compact constructor:

~~~java
public TransferProperties {
    if (servers != null) {
        servers = List.copyOf(servers);
    }
}
~~~

This uses a record **compact canonical constructor**; reassigning parameter `servers` stores an unmodifiable copy into the component during initialization. `List.copyOf` rejects null elements, so if the Binder yields a null list element, the constructor fails early.

**Note:** this is a shallow copy of the list; `Server` records themselves hold immutable references in this example. If `Server` later adds a mutable collection, make a defensive copy there too.

## 17. Complete Model with Bean Validation

To ensure required configuration is never omitted, upgrade `TransferProperties`:

~~~java
package com.example.transfer.config;

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
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.transfer")
public record TransferProperties(
    @DefaultValue("2s") @NotNull Duration connectTimeout,
    @DefaultValue("10s") @NotNull Duration readTimeout,
    @DefaultValue("20MB") @NotNull DataSize maxPayloadSize,
    @NotEmpty List<@Valid Server> servers
) {
    public TransferProperties {
        if (servers != null) {
            servers = List.copyOf(servers);
        }
    }

    @AssertTrue(message = "timeouts must be positive")
    public boolean isValidTimeouts() {
        return connectTimeout == null
            || readTimeout == null
            || (connectTimeout.compareTo(Duration.ZERO) > 0
                && readTimeout.compareTo(Duration.ZERO) > 0);
    }

    @AssertTrue(message = "max-payload-size must be positive")
    public boolean isPositivePayloadLimit() {
        return maxPayloadSize == null
            || maxPayloadSize.toBytes() > 0;
    }

    public record Server(
        @NotBlank String name,
        @NotNull URI baseUrl,
        @DefaultValue("10") @Min(1) @Max(100) int priority,
        @DefaultValue("3s") @NotNull Duration healthTimeout
    ) {
        @AssertTrue(message = "server URL must use http or https")
        public boolean isHttpEndpoint() {
            if (baseUrl == null) {
                return true; // @NotNull handles missing value.
            }
            String scheme = baseUrl.getScheme();
            return "http".equalsIgnoreCase(scheme)
                || "https".equalsIgnoreCase(scheme);
        }

        @AssertTrue(message = "health-timeout must be positive")
        public boolean isPositiveHealthTimeout() {
            return healthTimeout == null
                || healthTimeout.compareTo(Duration.ZERO) > 0;
        }
    }
}
~~~

**Meaning of each annotation:**

- `@Validated` activates validation on the Spring-managed configuration properties bean.
- `@NotNull` checks required reference fields.
- `@NotEmpty` requires the list to be non-null and contain at least one element.
- `@Valid` on the element type cascades validation into each `Server` when the provider supports Bean Validation container element constraints.
- `@NotBlank` requires server names to be non-null and contain non-whitespace characters.
- `@Min(1) @Max(100)` bounds priority after the Binder converts it to `int`.
- `@AssertTrue` on JavaBean-style boolean getters expresses business rules without a built-in constraint.

In this example, `@AssertTrue` on `isValidTimeouts`, `isPositivePayloadLimit`, and the `is...` methods acts as Bean Validation **getter constraints**; real tests require an active provider and bean validation wiring. For complex rules or errors tied to specific property paths, create a custom **class-level constraint** and `ConstraintValidator`.

**Do not put `@Positive` directly on `Duration` or `DataSize`** without confirming validator support for those types. Bean Validation's `@Positive` applies to supported numeric types, not arbitrary value objects by default.

## 18. Why Use `@AssertTrue` for `Duration`/`DataSize`?

Values like:

~~~yaml
connect-timeout: -2s
max-payload-size: -10MB
~~~

are syntactically convertible to `Duration` and `DataSize`, yet negative numbers are invalid for timeouts and maximum payload limits.

Without validation, the application may only fail later when creating an HTTP client or handling a request. Checking early surfaces errors at startup instead of under live traffic.

Rules in the complete model:

~~~text
connectTimeout > 0
readTimeout > 0
maxPayloadSize > 0
servers non-empty
server.name non-blank
server.baseUrl non-null with http/https scheme
1 <= server.priority <= 100
server.healthTimeout > 0
~~~

These rules are **conventions of this lab**, not fixed Spring Boot rules. Another system might allow a zero timeout to mean "infinite" or "disabled", provided its semantics are explicit; never apply `> 0` blindly if your HTTP library assigns special meaning to zero.

## 19. Checking the Relationship Between Two Timeouts

This lab only requires both timeouts to be positive. Another domain might require `readTimeout >= connectTimeout`. That is **cross-field validation**, not type conversion.

You can add a method:

~~~java
@AssertTrue(message = "read-timeout must be >= connect-timeout")
public boolean isTimeoutOrderValid() {
    if (connectTimeout == null || readTimeout == null) {
        return true; // @NotNull handles missing values.
    }
    return readTimeout.compareTo(connectTimeout) >= 0;
}
~~~

However, **this relationship is not universally required in networking**. Connect timeout and read timeout govern different phases; some HTTP clients validly allow read timeout to be shorter than connect timeout. Enforce it only when it is a genuine business contract.

Custom class-level validation is useful when multiple cross-field rules or field-targeted error messages are needed.

## 20. Missing Group, Missing Field, Invalid Value

Compare three cases.

**A. No `app.transfer.*` keys at all.** With a registered configuration properties bean, Spring Boot attempts to instantiate/bind the target according to its mechanism and defaults. Because the model puts `@NotEmpty` on `servers`, the desired policy is startup failure due to the missing list. Test the context on your exact version and dependencies to verify behavior.

**B. `servers` present, timeouts omitted.**

~~~yaml
app:
  transfer:
    servers:
      - name: primary
        base-url: https://primary.example.test
~~~

`@DefaultValue` supplies the timeouts, `DataSize`, and server priority/health timeout.

**C. Syntactically invalid timeout.**

~~~yaml
app:
  transfer:
    connect-timeout: tomorrow
    servers:
      - name: primary
        base-url: https://primary.example.test
~~~

`tomorrow` is not a duration understood by standard converters; the Binder fails during conversion. **`@DefaultValue("2s")` does not ignore a declared value that has the wrong type.**

| Case | Layer involved |
| --- | --- |
| Missing key, has default | Constructor default |
| Missing key, no default, `@NotNull`/`@NotEmpty` | Constraint validation when bean is created/validated |
| Value `tomorrow` for `Duration` | Conversion |
| Value `many` for `int priority` | Conversion |
| Value `-2s` (valid `Duration` syntax) | Domain/constraint validation if policy forbids negative |
| Malformed list shape | Binding structure |
| Record not scanned | Bean registration |
| Object bound, yet consumer ignores it | Runtime integration |

## 21. When Does Startup Fail Due to Validation?

Example:

~~~yaml
app:
  transfer:
    servers:
      - name: " "
        base-url: ftp://legacy.example.test
        priority: 0
        health-timeout: -1s
~~~

When Bean Validation is properly enabled and the Binder constructs the target, multiple violations occur:

- `name` is blank.
- `baseUrl` scheme violates the HTTP/HTTPS rule.
- `priority` is below `@Min(1)`.
- `healthTimeout` is not positive.

These are **correctly typed values that violate domain constraints**. By contrast, `priority: many` is a conversion failure because `"many"` cannot convert to `int` for `@Min` to evaluate.

Bean Validation failures during configuration properties binding often surface wrapped in `BindException` or `ConfigurationPropertiesBindException`; inspect the deeper cause and failure analysis rather than stopping at the word "bind".

## 22. A `Map` Reports Duplicate Names More Clearly When Uniqueness Is Needed

`List<Server>` makes sense when YAML ordering matters. If you want unique server names in a list, add an explicit check:

~~~java
Set<String> names = new HashSet<>();

for (TransferProperties.Server server : properties.servers()) {
    if (!names.add(server.name())) {
        throw new IllegalStateException(
            "Duplicate server name: " + server.name());
    }
}
~~~

This is an example of a domain check run when initializing a consumer, not logic to cram into every record constructor. For sensitive data, avoid printing names if they are private identifiers.

An alternative is `Map<String, Server>`, expressing identity via map keys:

~~~yaml
app:
  transfer:
    servers:
      primary:
        base-url: https://primary.example.test
      secondary:
        base-url: https://secondary.example.test
~~~

With a map, key uniqueness is enforced structurally. When **ordering/priority selection** is primary, a list with explicit validation remains a good fit.

## 23. Using the Record in a Consumer Service

A service injects `TransferProperties` via constructor injection:

~~~java
package com.example.transfer.service;

import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Service;

import com.example.transfer.config.TransferProperties;

@Service
public class TransferPlanner {
    private final TransferProperties settings;

    public TransferPlanner(TransferProperties settings) {
        this.settings = settings;
    }

    public List<TransferProperties.Server> orderedServers() {
        return settings.servers().stream()
            .sorted(Comparator.comparingInt(
                TransferProperties.Server::priority))
            .toList();
    }
}
~~~

Here, **lower priority number comes first** is an application-defined rule; the Spring Boot Binder does not select upstreams itself. Modern Java's `stream().toList()` returns an unmodifiable list, and our defensive copy inside the record prevents consumers from mutating the source list.

For fallback when the primary server fails to respond, the real service needs retry/failover logic, health checks, and consistent policies. Never make network calls inside `TransferProperties` to pick servers during binding.

## 24. Using `Duration` and `DataSize` to Configure Clients

Suppose a business component needs `long timeoutMs` and `long maxBytes`:

~~~java
Duration connect = settings.connectTimeout();
Duration read = settings.readTimeout();
DataSize limit = settings.maxPayloadSize();

long connectMillis = connect.toMillis();
long readMillis = read.toMillis();
long maxBytes = limit.toBytes();
~~~

These lines belong in an HTTP client factory or transfer handler. The proper pipeline order is:

1. **Binder** converts external config into Java types.
2. **Validation** verifies typed values satisfy the contract.
3. **Factory/service** adapts them to the specific client API.
4. **Runtime client** enforces timeouts, payload limits, and server selection.

Do not cast `long` to `int` via `Math.toIntExact` without bounds checking if a library accepts only `int` milliseconds. A multi-gigabyte `DataSize` can easily overflow an `int` or buffer capacity.

### Do Not Confuse `maxPayloadSize` with Max Memory

`max-payload-size` is a **business limit per payload**; it does not prevent reading an entire file into RAM. A streaming application must count received bytes incrementally, bound buffers, and handle backpressure. Type-safe config is only the first step—not a substitute for resource management.

## 25. Java Records Do Not Refresh Dynamically by Default

`TransferProperties` is instantiated and bound during the Spring context lifecycle. Editing `application.yml` after startup:

~~~text
10:00 Spring Boot starts, timeout=2s
10:05 developer edits file to timeout=4s
10:06 TransferProperties still holds 2s
~~~

Spring Boot Config Data is normally loaded at startup; it does not watch files or rebind every record bean. Even if another mechanism updates `Environment`, already-constructed HTTP clients may still hold the old timeout.

Live reload requires explicit design covering update sources, bean/client rebinding or recreation, per-request consistency, and update authorization. Never treat `record` or `@ConfigurationProperties` as automatic hot reload.

## 26. Splitting Profile Files Without Copy-Pasting Everything

Base:

~~~yaml
# application.yml
app:
  transfer:
    connect-timeout: 2s
    read-timeout: 10s
    max-payload-size: 20MB
    servers:
      - name: primary
        base-url: https://primary.example.test
        priority: 10
        health-timeout: 3s
      - name: secondary
        base-url: https://secondary.example.test
        priority: 20
        health-timeout: 5s
~~~

Development delta:

~~~yaml
# application-dev.yml
app:
  transfer:
    connect-timeout: 500ms
    read-timeout: 3s
    max-payload-size: 5MB
~~~

Production delta:

~~~yaml
# application-prod.yml
app:
  transfer:
    read-timeout: 15s
    max-payload-size: 50MB
~~~

For scalars, profile-specific config overrides matching keys, while omitted keys continue coming from the base file if no higher-priority source intervenes.

**However, the `servers` list is not deep-merged element-by-element across profiles arbitrarily.** If production needs a different server list, declare the complete list or consider another model.

## 27. List Replacement Between `application.yml` and `application-prod.yml`

Suppose base defines:

~~~yaml
app:
  transfer:
    servers:
      - name: primary
        base-url: https://primary.example.test
        priority: 10
      - name: backup
        base-url: https://backup.example.test
        priority: 20
~~~

And production writes only:

~~~yaml
app:
  transfer:
    servers:
      - priority: 1
~~~

Do not expect production to update only the first server's `priority` while inheriting `name`/`base-url` and the second server. **Spring Boot list binding normally uses the list from the higher-priority source rather than merging nested elements across sources by index.**

The outcome can be a one-element list missing required fields, failing validation. When production truly needs a different list:

~~~yaml
# application-prod.yml
app:
  transfer:
    servers:
      - name: primary
        base-url: https://primary.example.test
        priority: 1
        health-timeout: 3s
      - name: backup
        base-url: https://backup.example.test
        priority: 20
        health-timeout: 5s
~~~

If the server list is large and you often override single entries by stable name, consider `Map<String, Server>` and test its binding behavior. Switching from list to map is a contract change; never do it casually.

## 28. Should Profile Files Contain Server URLs?

That is an operational choice:

- A sandbox URL may fit `application-dev.yml`.
- Production URLs may come from external Config Data or a config store supplied at deploy time.
- API credentials should stay out of version-controlled YAML.
- Environment-specific service DNS names and regions fit deployment-specific config.
- Non-secret values can live in profile files if your artifact and repository access policies allow it.

Never copy production credentials into YAML just to "make the example runnable". Throughout this guide, all URLs use `example.test` so nothing calls real services by mistake.

## 29. Overriding Scalars from Environment Variables

Spring Boot Binder supports relaxed binding for `@ConfigurationProperties`. For canonical keys:

| Property | Typical env var |
| --- | --- |
| `app.transfer.connect-timeout` | `APP_TRANSFER_CONNECTTIMEOUT` |
| `app.transfer.read-timeout` | `APP_TRANSFER_READTIMEOUT` |
| `app.transfer.max-payload-size` | `APP_TRANSFER_MAXPAYLOADSIZE` |
| `app.transfer.servers[0].name` | `APP_TRANSFER_SERVERS_0_NAME` |
| `app.transfer.servers[0].base-url` | `APP_TRANSFER_SERVERS_0_BASEURL` |
| `app.transfer.servers[0].priority` | `APP_TRANSFER_SERVERS_0_PRIORITY` |

Docker Compose example:

~~~yaml
services:
  transfer:
    image: example/transfer-service:local
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      APP_TRANSFER_CONNECTTIMEOUT: "3s"
      APP_TRANSFER_MAXPAYLOADSIZE: "50MB"
~~~

These variables enter the container environment, and Spring Boot binds them accordingly. **A separate Compose `.env` file only handles variable interpolation unless passed to the service via `environment` or `env_file`.**

List caution: supplying partial list indices from a higher-priority environment variable can trigger list replacement; verify the final bound list rather than assuming per-element merging.

## 30. Do Not Confuse `@Value` with `@ConfigurationProperties`

A scattered approach:

~~~java
@Value("\${app.transfer.connect-timeout:2s}")
Duration connectTimeout;

@Value("\${app.transfer.max-payload-size:20MB}")
DataSize maxPayloadSize;
~~~

For a large group with nested lists, multiple `@Value` fields quickly become unwieldy:

- No unified typed contract for the group.
- Placeholder defaults easily drift across consumers.
- Nested lists require manual handling or SpEL workarounds.
- Validation gets scattered across services.
- Tests struggle to assert group-wide invariants cleanly.

`@ConfigurationProperties` paired with records is the natural choice for **structured configuration**. For a single isolated scalar, `@Value` still has a valid place; it is not inherently "wrong".

## 31. Testing Successful Binding with `ApplicationContextRunner`

`ApplicationContextRunner` from `spring-boot-test` spins up a lightweight context with explicit properties to verify typed binding.

Example using the complete model from section 17:

~~~java
package com.example.transfer.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.unit.DataSize;

class TransferBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void bindsDurationsDataSizeAndServers() {
        runner.withPropertyValues(
                "app.transfer.connect-timeout=750ms",
                "app.transfer.read-timeout=8s",
                "app.transfer.max-payload-size=12MB",
                "app.transfer.servers[0].name=primary",
                "app.transfer.servers[0].base-url=https://primary.example.test",
                "app.transfer.servers[0].priority=5",
                "app.transfer.servers[0].health-timeout=2s",
                "app.transfer.servers[1].name=secondary",
                "app.transfer.servers[1].base-url=https://secondary.example.test"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                TransferProperties p =
                    context.getBean(TransferProperties.class);

                assertThat(p.connectTimeout())
                    .isEqualTo(Duration.ofMillis(750));
                assertThat(p.readTimeout())
                    .isEqualTo(Duration.ofSeconds(8));
                assertThat(p.maxPayloadSize())
                    .isEqualTo(DataSize.ofMegabytes(12));
                assertThat(p.servers()).hasSize(2);
                assertThat(p.servers().get(0).name())
                    .isEqualTo("primary");
                assertThat(p.servers().get(1).priority())
                    .isEqualTo(10); // @DefaultValue
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(TransferProperties.class)
    static class TestConfig {}
}
~~~

This test focuses on **binding and defaults**. To assert Bean Validation, include the validator/provider configuration as shown below. Never conclude from this test that `application-prod.yml` loads automatically, as properties are supplied inline.

## 32. Testing `@DefaultValue` When Timeouts and Size Are Omitted

Dedicated test:

~~~java
@Test
void defaultsWorkWhenOptionalScalarsAreMissing() {
    runner.withPropertyValues(
            "app.transfer.servers[0].name=primary",
            "app.transfer.servers[0].base-url=https://primary.example.test"
        )
        .run(context -> {
            assertThat(context).hasNotFailed();
            TransferProperties p =
                context.getBean(TransferProperties.class);

            assertThat(p.connectTimeout())
                .isEqualTo(Duration.ofSeconds(2));
            assertThat(p.readTimeout())
                .isEqualTo(Duration.ofSeconds(10));
            assertThat(p.maxPayloadSize())
                .isEqualTo(DataSize.ofMegabytes(20));
            assertThat(p.servers().get(0).priority())
                .isEqualTo(10);
            assertThat(p.servers().get(0).healthTimeout())
                .isEqualTo(Duration.ofSeconds(3));
        });
}
~~~

Here the list has one valid server, so the Binder constructs `TransferProperties` and fills omitted scalars from `@DefaultValue`.

If you edit an annotation default while a base YAML file still supplies that key, the YAML value overrides the annotation default. A "missing optional scalar" test must **truly omit that key**.

## 33. Testing Conversion Failure: Malformed `Duration`

~~~java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void invalidDurationFailsBinding() {
    runner.withPropertyValues(
            "app.transfer.connect-timeout=tomorrow",
            "app.transfer.servers[0].name=primary",
            "app.transfer.servers[0].base-url=https://primary.example.test"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

`"tomorrow"` cannot be converted to `Duration` by default converters. This is a **conversion error wrapped in a binding failure**; having `@DefaultValue("2s")` does not turn an invalid value into the default.

In real tests, inspect the root cause or exception type matching your Spring Boot version to classify failures accurately. Avoid asserting exact blocks of failure analyzer text, as wording can change.

## 34. Testing Conversion Failure: Malformed `DataSize`

~~~java
@Test
void invalidDataSizeFailsBinding() {
    runner.withPropertyValues(
            "app.transfer.max-payload-size=very-big",
            "app.transfer.servers[0].name=primary",
            "app.transfer.servers[0].base-url=https://primary.example.test"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

`"very-big"` is not a `DataSize` value understood by default conversion. Fix it to `5MB`, `512KB`, or another valid unit-suffixed value per policy.

Distinguish:

~~~text
max-payload-size: very-big  -> conversion failure
max-payload-size: -10MB     -> convertible, domain validation failure
max-payload-size: 0B        -> convertible, domain validation failure
max-payload-size: 12MB      -> valid if within allowed limits
~~~

## 35. Testing Validation: Missing Server List

To test Bean Validation, the context needs a validator enforcing Jakarta constraints. In a lightweight Boot test context, include `ValidationAutoConfiguration`:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;

private final ApplicationContextRunner validatedRunner =
    new ApplicationContextRunner()
        .withUserConfiguration(TestConfig.class)
        .withConfiguration(
            AutoConfigurations.of(ValidationAutoConfiguration.class)
        );
~~~

Then:

~~~java
@Test
void missingServersIsRejected() {
    validatedRunner.withPropertyValues(
            "app.transfer.connect-timeout=2s",
            "app.transfer.read-timeout=10s",
            "app.transfer.max-payload-size=20MB"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

When binding creates the root bean and Bean Validation is active, `@NotEmpty List<Server> servers` turns an omitted list into a startup failure.

If this test unexpectedly passes, check the validation provider dependency, record registration, and validation wiring in the context—never assume `@NotEmpty` does nothing.

## 36. Testing Validation: Blank Server Name and Invalid Priority

~~~java
@Test
void invalidServerConstraintsAreRejected() {
    validatedRunner.withPropertyValues(
            "app.transfer.servers[0].name= ",
            "app.transfer.servers[0].base-url=https://primary.example.test",
            "app.transfer.servers[0].priority=0"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

These values match the target Java types:

- `" "` is a `String`, yet violates `@NotBlank`.
- `0` is an `int`, yet violates `@Min(1)`.

To ensure nested elements are validated, both `@Valid` and an appropriate validation provider must be present. Putting `@Validated` only on the root without cascading may leave list element constraints unchecked.

## 37. Testing Validation: Payload Limit Must Be Positive

~~~java
@Test
void nonPositivePayloadSizeIsRejected() {
    validatedRunner.withPropertyValues(
            "app.transfer.max-payload-size=0B",
            "app.transfer.servers[0].name=primary",
            "app.transfer.servers[0].base-url=https://primary.example.test"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

This relies on the `@AssertTrue` getter `isPositivePayloadLimit()` in the complete model. `0B` converts to a zero-byte `DataSize`, then fails domain validation.

Unlike `"very-big"`, this is **not a `DataSize` parse error**. Separating conversion and validation tests clarifies logs and remediation steps.

## 38. Testing Validation: Syntactically Valid URI with Unsupported Scheme

~~~java
@Test
void unsupportedUriSchemeIsRejected() {
    validatedRunner.withPropertyValues(
            "app.transfer.servers[0].name=primary",
            "app.transfer.servers[0].base-url=ftp://legacy.example.test"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

`ftp://legacy.example.test` is a syntactically valid `URI`. Yet the lab's domain rule allows only HTTP/HTTPS, making this a **validation failure**, not a conversion failure.

If a real app needs gRPC, FTP, or a custom scheme, never copy this rule verbatim—tailor the constraint to your allowed protocols.

## 39. `@SpringBootTest` to Verify Real YAML and Profiles

`ApplicationContextRunner` tests typed binding from directly supplied properties well, but to verify that `application.yml` and `application-prod.yml` load under a real profile, use an integration test.

Example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("prod")
class TransferProfileTest {
    @Autowired
    TransferProperties transfer;

    @Test
    void usesProductionTimeout() {
        assertThat(transfer.readTimeout())
            .isEqualTo(Duration.ofSeconds(15));
    }
}
~~~

This test assumes the base and production YAML files from section 26 are on the test classpath, the record is scanned/enabled, and no higher-priority test source overrides it.

For profile list overrides, assert the full `servers()` list too: element count, names, URLs, priorities, and defaults—do not test one scalar and assume the whole production config is right.

## 40. Verifying Consumers Cannot Mutate the List

With a defensive copy in the record:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void serversListCannotBeMutated() {
    TransferProperties p = ...; // bound via Binder in the test.
    assertThatThrownBy(() -> p.servers().clear())
        .isInstanceOf(UnsupportedOperationException.class);
}
~~~

This is an **assertion pattern** using an existing bound instance `p`; the `...` placeholder represents the test setup and will not compile verbatim if pasted without setup. In a complete test, retrieve `p` via `context.getBean(TransferProperties.class)` inside an `ApplicationContextRunner` callback.

Defensive copying guarantees that a service accidentally calling `clear()` or `add()` on the configuration list cannot corrupt state seen by other beans sharing that configuration bean.

## 41. Testing Missing Config Files vs. Binding Errors

A common mistake: an app works locally with a complete `application.yml`, yet in a container only an external file exists containing:

~~~yaml
app:
  transfer:
    max-payload-size: 50MB
~~~

If that external file **replaces** the base location or another config fails to load, `servers` may be missing. Depending on the failure point:

- It could be a **Config Data location/loading** failure.
- Or a **missing property / Bean Validation** failure if no server list exists in effective sources.
- If the list structure is malformed, it is a **binding shape** error.
- If a URI fails to parse, it is **conversion**.
- If a parsed URI violates HTTP/HTTPS policy, it is **validation**.

Do not see `BindException` and jump to "YAML syntax is broken". Inspect the property path, origin/source, and root cause to fix the right layer.

## 42. Error Handling and Startup Messages

An illustrative failure:

~~~text
Failed to bind properties under 'app.transfer.connect-timeout'
to java.time.Duration

Property: app.transfer.connect-timeout
Value: "tomorrow"
Origin: class path resource [application.yml] - 5:22
Reason: failed to convert String to Duration
~~~

This is an **illustrative example**; exact logs depend on Spring Boot version and source. When debugging, check:

1. `Property`: which key failed?
2. `Value`: what raw value did the Binder receive?
3. `Origin`: which file/profile/env/CLI supplied it?
4. `Reason`: conversion error, missing required value, or validation?
5. **Target type**: `Duration`, `DataSize`, `URI`, or integer?
6. **Active profiles**: which documents were selected?
7. **Precedence**: is another source overriding the file you edited?

If a property holds credentials, never paste its value into issues or READMEs. In this lab, all values are non-sensitive examples.

## 43. A Java Record as a Configuration Object Is Not a Runtime Domain Model

A `Server` in the configuration record:

~~~java
public record Server(
    String name,
    URI baseUrl,
    int priority,
    Duration healthTimeout
) {}
~~~

**describes how the application is configured**. It does not represent:

- Current live health status.
- Error counters or circuit breaker state.
- DNS resolution results.
- Open connection counts.
- Latency metrics.
- Verified credentials or permissions.
- Whether the endpoint is currently reachable.

Those runtime concerns belong in dedicated runtime services/objects. Keeping configuration records pure data makes binding easy to test, keeps snapshots immutable, and eliminates startup side effects.

## 44. When to Choose `Map<String, Server>` Instead of `List<Server>`?

Use `List<Server>` when:

- Declaration order matters.
- Consumers iterate over servers in sequence.
- The contract allows duplicate entries or ordered fallbacks.
- Profile overrides usually replace the whole server set.

Use `Map<String, Server>` when:

- Server name/ID is a unique key.
- Profiles frequently override single server settings by identity.
- Lookup by server name matters more than sequence order.
- You want to avoid copying the entire list in profile overrides in many cases.

Map example:

~~~yaml
app:
  transfer:
    servers:
      primary:
        base-url: https://primary.example.test
        health-timeout: 2s
      secondary:
        base-url: https://secondary.example.test
        health-timeout: 5s
~~~

Maps have their own binding and precedence behavior and do not arbitrarily deep-merge every nested object. Switching from a list to a map changes the external contract—update code, docs, tests, and all external configs together.

## 45. Avoid Putting Credentials Inside Nested `Server` Records

In real systems, each upstream may require an API token. Never write:

~~~yaml
app:
  transfer:
    servers:
      - name: primary
        base-url: https://primary.example.test
        api-token: REAL_SECRET_VALUE
~~~

and commit it to Git. Tokens are secrets. Keep non-sensitive server URLs, names, and timeouts in Config Data, while provisioning tokens from a secret manager, secret mount, or secured runtime source.

If a record ends up holding a secret, **the record's default `toString()` prints all components**. Never log the whole record, expose it in debug endpoints, or serialize it to JSON for clients. Restrict Actuator `env`/`configprops` with masking and authentication.

## 46. Practice: Changing Size Limits in Runtime Deployments

Suppose base defines:

~~~yaml
app:
  transfer:
    max-payload-size: 20MB
~~~

Production needs `50MB`, and deployment sets an environment variable:

~~~text
APP_TRANSFER_MAXPAYLOADSIZE=50MB
~~~

In standard Spring Boot setups, an environment variable overrides the base Config Data file when using the canonical env name in the same process. However, changing a variable in the host shell **does not update the environment of a running container**, and an already-bound Spring record **does not auto-refresh**.

Safe rollout plan:

1. Identify the winning source and target instances.
2. Put the override in the deployment spec or runtime environment.
3. Recreate/roll out the process per your platform.
4. Verify startup binding and validation succeed.
5. Verify the consumer enforces the new limit.
6. Verify reverse proxies and HTTP servers have matching limits.
7. Keep a rollback plan if memory or throughput degrades.

Raising limits substantially can severely impact resource usage; typed config never replaces performance testing.

## 47. Practice: Tuning Timeouts per Environment

Base + delta pattern:

~~~yaml
# application.yml
app:
  transfer:
    connect-timeout: 2s
    read-timeout: 10s
~~~

~~~yaml
# application-dev.yml
app:
  transfer:
    connect-timeout: 500ms
    read-timeout: 3s
~~~

~~~yaml
# application-prod.yml
app:
  transfer:
    connect-timeout: 3s
    read-timeout: 15s
~~~

Do not duplicate the `servers` list into dev/prod if it is identical and does not need overriding. Conversely, if endpoint lists differ by environment, declare the full list in each needed source and test final binding.

**Never pick timeouts by habit.** Base them on network latency, SLAs, retry strategy, total request budget, and upstream processing time. 2s connect and 10s read are purely instructional examples.

## 48. Prefer Contract Tests Over Counting YAML Lines

An application may receive configuration from:

- Packaged `application.yml`.
- `application-prod.yml`.
- Config Data imports from classpath or external files.
- OS environment variables.
- JVM system properties.
- Spring command-line arguments.

Tests provide real value when asserting the **typed result**:

~~~java
assertThat(props.connectTimeout())
    .isEqualTo(Duration.ofSeconds(2));

assertThat(props.maxPayloadSize())
    .isEqualTo(DataSize.ofMegabytes(20));

assertThat(props.servers()).hasSize(2);
~~~

Grepping one file for `20MB` does not prove `20MB` is the final value if a higher-priority source overrode it to `50MB`.

## 49. Common Pitfalls

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Duration` is null despite timeout in YAML | Wrong prefix/name, file not loaded, record unbound | Check key, active profile, registration |
| `timeout=tomorrow` fails startup | Conversion failure | Use `ms`/`s`/`m` or valid ISO-8601 |
| `max-payload-size=very-big` fails | Cannot parse `DataSize` | Use valid unit-suffixed value |
| `max-payload-size=0B` binds despite policy | Domain validation not running | Enable `@Validated` and proper constraint |
| `@Positive DataSize` throws validation type error | Constraint does not support type | Use custom class-level or getter constraint |
| Server list missing | YAML object instead of sequence, wrong indices | Use YAML sequence (`-`) or `[0]`, `[1]` |
| Nested constraints skipped | Missing `@Valid` or validation provider | Configure cascading and provider |
| `@Component` on record causes injection error | Wrong registration path | Use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Backup server disappears in prod | Higher-priority source replaced the whole list | Declare full list or switch to `Map` |
| Consumer mutates record's list | Shallow immutability | Use `List.copyOf` in compact constructor |
| Using `server.port` to explain payload limits | Confused custom domain property with web server config | Configure the right layer |
| Custom `max-payload-size` fails to cap HTTP uploads | Transport/app limit not enforced | Configure multipart/proxy and streaming checks |
| Edited `.yml` at runtime, values unchanged | No live refresh/restart | Recreate/rebind explicitly by design |
| Valid config, unreachable URL | Runtime network/health issue, not Binder | Check DNS, TLS, firewall, availability |
| Debug logs expose tokens | Logged record/config/env verbatim | Redact, restrict access, never log secrets |

## 50. Exercise 1 — Identify Java Types

Given YAML:

~~~yaml
app:
  transfer:
    connect-timeout: 800ms
    max-payload-size: 8MB
    servers:
      - name: first
        base-url: https://first.example.test
~~~

**Question:** Which Java types should you choose?

**Answer:** `Duration connectTimeout`, `DataSize maxPayloadSize`, `List<Server> servers`; inside `Server`, `String name` and `URI baseUrl`. Remaining optional values can take `@DefaultValue` if the domain allows.

## 51. Exercise 2 — Why Are Unitless Numbers Dangerous?

~~~yaml
connect-timeout: 2000
~~~

**Answer:** Spring Boot applies default unit rules (or `@DurationUnit`), yet reviewers easily confuse 2000 seconds with 2000 milliseconds. Safer practice is writing `2000ms` or `2s` so the contract is unambiguous.

## 52. Exercise 3 — Conversion or Validation?

~~~yaml
max-payload-size: very-big
~~~

**Answer:** conversion failure because `"very-big"` cannot parse into a standard `DataSize`.

~~~yaml
max-payload-size: 0B
~~~

**Answer:** converts into `DataSize`, yet violates the `> 0` rule in the sample model, so validation fails when active.

## 53. Exercise 4 — Wrong List Shape

~~~yaml
servers:
  name: primary
  base-url: https://primary.example.test
~~~

**Answer:** this is a YAML mapping, not the sequence needed for `List<Server>`. Add `-` and indent properly.

## 54. Exercise 5 — Nested `@Valid`

The root has `@Validated` and `Server` has `@NotBlank name`, yet the list is not properly cascaded.

**Answer:** nested constraints may not run as expected. Use `List<@Valid Server>` with a proper validation provider, and write a test with a blank name to prove validation works.

## 55. Exercise 6 — Record vs. Mutable List

A consumer calls:

~~~java
properties.servers().clear();
~~~

**Answer:** a record does not automatically protect a list if the backing collection is mutable. `List.copyOf(servers)` in the compact constructor creates an unmodifiable list.

## 56. Exercise 7 — Profile Override

Base has 2 servers. Production declares:

~~~yaml
servers:
  - name: only
    base-url: https://prod.example.test
~~~

**Answer:** treat this as the complete production list replacing the base list—never assume a third server or inherited base entries remain. Test the full `servers()` list in the `prod` profile.

## 57. Exercise 8 — Secret in URL

A `base-url` contains `?token=...`.

**Answer:** the entire URL becomes sensitive; never log it or commit real tokens. When the protocol allows, use auth headers and a dedicated secret manager.

## 58. Exercise 9 — Missing Servers

Config supplies timeouts and `DataSize`, yet omits `servers`. **Answer:** this is a missing required configuration; test `@NotEmpty` to confirm startup fails when Bean Validation is active. Never invent a dummy default server.

## 59. Exercise 10 — HTTP Limit Not Enforced Automatically

`TransferProperties` sets `max-payload-size: 20MB`, yet the controller still accepts larger uploads.

**Answer:** custom properties do not automatically configure Spring multipart, streaming, or proxy limits. Configure the HTTP layer and enforce limits explicitly.

## 60. Pre-Deployment Checklist

- [ ] `TransferProperties` uses canonical prefix `app.transfer`.
- [ ] Record is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
- [ ] `Duration` values specify explicit units.
- [ ] `DataSize` values specify explicit units.
- [ ] `servers` uses a YAML sequence or proper indexed properties.
- [ ] Each `Server` specifies `name` and `base-url` per contract.
- [ ] `@DefaultValue` is used only for fields with safe defaults.
- [ ] Mandatory server list has `@NotEmpty`.
- [ ] Nested `Server` constraints cascade via `@Valid`.
- [ ] `@Validated` and a Bean Validation provider are configured.
- [ ] Positive `Duration`/`DataSize` rules are checked in a type-appropriate way.
- [ ] `@Positive` is not placed blindly on `Duration`/`DataSize`.
- [ ] Record uses a defensive copy where list immutability is required.
- [ ] `@Component` is not misused on constructor-bound records.
- [ ] Conversion failures and validation failures are tested separately.
- [ ] Default behavior is tested when optional scalars are missing.
- [ ] Profile overrides are tested against the entire list, not a single element.
- [ ] Effective property sources, env vars, and CLI args are verified per deployment.
- [ ] Secrets are never hard-coded or committed inside URLs.
- [ ] HTTP/server/proxy layers enforce upload/request limits independently.
- [ ] Consumer clients actually apply configured timeouts and failover policies rather than merely reading the record.

## 61. Summary

To model timeouts, size limits, and server lists in Spring Boot, a clean design looks like this:

~~~text
application.yml / profile / env / CLI
                    |
                    v
            Spring Boot Binder
                    |
                    v
       @ConfigurationProperties record
       ├── Duration connectTimeout
       ├── Duration readTimeout
       ├── DataSize maxPayloadSize
       └── List<Server>
           ├── String name
           ├── URI baseUrl
           ├── int priority
           └── Duration healthTimeout
                    |
                    v
         @Validated / @Valid rules
                    |
                    v
       Immutable configuration snapshot
                    |
                    v
       HTTP client / transfer service
~~~

**`Duration` handles time units; `DataSize` handles size units; `List<Server>` captures multi-endpoint structure; and a record unifies them into one typed contract.** `@DefaultValue` supplies deliberate defaults, `@Validated` and `@Valid` catch missing or invalid constraints, and `List.copyOf` shields lists from accidental mutation.

Most importantly: **successful binding does not prove consumers enforce timeouts or upload limits**, and **an immutable record does not make nested collections deeply immutable automatically**. Separating configuration, validation, and runtime behavior lets applications run cleanly across profiles and environments with typed data, stronger tests, and fewer hard-to-trace bugs.
