# Handling Properties Missing from the Class with `ignoreUnknownFields`

## 1. The problem: YAML has a key, but the Java class has no matching field

When using Spring Boot Externalized Configuration, we often map a group of properties in `application.yml` or `application.properties` into a Java class via `@ConfigurationProperties`.

Example:

```yaml
mailer:
  enabled: true
  max-attempts: 3
  connect-timeout: 2s
```

And the Java class:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(
        boolean enabled,
        int maxAttempts,
        Duration connectTimeout
) {}
```

The three keys in YAML can bind to the three record components. But what happens if a teammate adds a key that does not exist in the class?

```yaml
mailer:
  enabled: true
  max-attempts: 3
  connect-timeout: 2s
  debug-mode: true
```

The record above **has no** `debugMode` component. The key `mailer.debug-mode` belongs to the same `mailer` prefix, yet has no corresponding destination in the Java object. Spring Boot must decide whether to:

- **Ignore** the extra property and continue starting up; or
- **Report an error** so developers notice the configuration is out of sync with the Java class?

The `@ConfigurationProperties` annotation provides the `ignoreUnknownFields` attribute to control this choice.

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = true
)
```

The default value of `ignoreUnknownFields` is **`true`**: properties that are not bound under this mechanism are generally ignored. When set to **`false`**, Spring Boot performs stricter binding and can fail configuration-properties bean creation when unbound configuration elements are detected under the prefix.

That is the core focus of this lesson: **an extra property differs from a missing or wrongly typed property**, and `ignoreUnknownFields` addresses only one specific category of issues.

## 2. Where does `ignoreUnknownFields` live?

`ignoreUnknownFields` is an attribute of Spring Boot's `@ConfigurationProperties` annotation:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false
)
public record MailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

Meaning of the components:

| Component | Role |
| --- | --- |
| `@ConfigurationProperties` | Marks a type/bean to be bound from external configuration |
| `prefix = "mailer"` | Identifies the property group being bound |
| `ignoreUnknownFields = true` | Allows ignoring properties without a binding target; the default |
| `ignoreUnknownFields = false` | Requests detection of extra properties the binder cannot bind |
| `enabled`, `maxAttempts` | Java properties with targets to receive values |

Configuration key names do not always match Java names verbatim. Spring Boot supports **relaxed binding**. For example, `max-attempts` in YAML matches `maxAttempts` in the record. Hence, `max-attempts` is not treated as unknown simply because it contains a hyphen.

**Unknown field** here does not mean "a key unknown to the entire application". It means **a property within the binding scope of a `@ConfigurationProperties` type that the binder cannot map onto the target object in that specific context**.

This distinguishes `ignoreUnknownFields` from a tool that scans every key across the entire `Environment`. It does not act as a global schema checker for all libraries and all prefixes.

## 3. Default behavior: `ignoreUnknownFields = true`

Shorthand:

```java
@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

Equivalent regarding ignoring extra properties:

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = true
)
public record MailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

With configuration:

```yaml
mailer:
  enabled: true
  max-attempts: 4
  debug-mode: true
```

Assuming no other issues, the binding result is:

```text
MailerProperties.enabled()     = true
MailerProperties.maxAttempts() = 4
mailer.debug-mode              = no target field in the record
```

The application can continue starting up. The `mailer.debug-mode` property does not become a new field, does not generate a getter, and does not add extra data to the record. It is simply unused by this record's binding.

Do not confuse "ignored during binding" with "removed from the configuration environment". The `mailer.debug-mode` value may still exist in `Environment` if its source is loaded; another component looking up the same key differently can still read it. `ignoreUnknownFields` is an option of the **object binding process**, not a command to delete keys from all sources.

### Why does Spring Boot ignore by default?

In configuration ecosystems, the same prefix is sometimes shared among multiple components or an object structure evolves over time. A class may only need a subset of properties. Allowing extra keys to be ignored helps a class remain compatible with richer configuration sources.

For instance, a config file might have:

```yaml
mail:
  smtp:
    host: smtp.example.invalid
    port: 2525
    protocol: smtp
```

If a class only binds `mail.smtp.host` and `mail.smtp.port`, lenient mode allows that class to keep working even when the file also contains `protocol`.

However, **this flexibility is a trade-off**. A misspelled key may be silently ignored, leaving the application using a default or missing value without the YAML author noticing.

## 4. Strict mode: `ignoreUnknownFields = false`

Update the annotation:

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false
)
public record MailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

Keep the same YAML with the extra key:

```yaml
mailer:
  enabled: true
  max-attempts: 4
  debug-mode: true
```

During binding, Spring Boot checks whether properties under the `mailer` scope were all bound to the target object. `mailer.debug-mode` has no matching field, so bean creation can fail with an error related to **unbound properties**.

The exact message depends on the Spring Boot version and configuration, but typically resembles:

```text
Failed to bind properties under 'mailer'
...
The elements [mailer.debug-mode] were left unbound.
```

This message is an illustration, not a guarantee that every log line looks identical. The technical meaning is: **a configuration element within the bound scope was not consumed by the target object**.

If you remove `mailer.debug-mode` or add the corresponding Java component `boolean debugMode` (if the application actually needs it), binding can succeed again.

A mental model:

```text
Configuration under prefix mailer
              |
              v
       Spring Boot Binder
              |
    +---------+---------+
    |                   |
Mappable            Unmappable
    |                   |
    v                   v
Write to object    ignoreUnknownFields?
                        |
                +-------+-------+
                |               |
               true            false
                |               |
             Ignore      Report unbound / fail
```

This is the right tool when you want configuration to adhere closely to **the Java class's contract** rather than silently accepting misspelled keys.

## 5. Runnable hands-on lab: create a properties class and observe both modes

To see the difference, create a small Spring Boot application (e.g., Spring Boot 3.x, Java 17 or higher). No database or HTTP server is required.

### 5.1. Project structure

```text
unknown-field-lab/
└── src/main/
    ├── java/com/example/unknown/
    │   ├── UnknownFieldApplication.java
    │   └── MailerProperties.java
    └── resources/
        └── application.yml
```

The project needs the basic Spring Boot dependencies to run, such as `spring-boot-starter`. You can generate it via Spring Initializr and select Java and a compatible Spring Boot version.

### 5.2. Configuration class in default mode

`MailerProperties.java`:

```java
package com.example.unknown;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(
        boolean enabled,
        int maxAttempts,
        Duration timeout
) {}
```

`UnknownFieldApplication.java`:

```java
package com.example.unknown;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableConfigurationProperties(MailerProperties.class)
public class UnknownFieldApplication {

    public static void main(String[] args) {
        SpringApplication.run(UnknownFieldApplication.class, args);
    }

    @Bean
    ApplicationRunner printBoundValues(MailerProperties properties) {
        return args -> {
            System.out.println("=== UNKNOWN FIELD LAB ===");
            System.out.println("enabled     = " + properties.enabled());
            System.out.println("maxAttempts = " + properties.maxAttempts());
            System.out.println("timeout     = " + properties.timeout());
            System.out.println("=========================");
        };
    }
}
```

`@EnableConfigurationProperties` registers the record so Spring Boot creates the object via constructor binding. Do not attach `@Component` to the record in this example; properties records are instantiated through configuration binding, not ordinary service constructor injection.

### 5.3. YAML with an extra key

Create `application.yml`:

```yaml
mailer:
  enabled: true
  max-attempts: 5
  timeout: 2s
  trace-mode: verbose
```

The key `mailer.trace-mode` **has no** `traceMode` component in the record. Package an executable JAR using Gradle or Maven as appropriate, then run it. Commands use `app.jar` as an illustrative name; replace it with the actual build path.

```bash
java -jar app.jar
```

With the default `ignoreUnknownFields=true`, expected output:

```text
=== UNKNOWN FIELD LAB ===
enabled     = true
maxAttempts = 5
timeout     = PT2S
=========================
```

`timeout` is `Duration.ofSeconds(2)`, and when printed with `toString()` typically shows `PT2S`. The `trace-mode` key does not appear in the output because the record does not retain it.

### 5.4. Enable strict mode

Edit only the annotation in `MailerProperties.java`:

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false
)
public record MailerProperties(
        boolean enabled,
        int maxAttempts,
        Duration timeout
) {}
```

Repackage and run with the **same YAML**.

Expectation: the application **fails to create the `MailerProperties` bean** because `mailer.trace-mode` has no binding target. Spring Boot may display a bind/unbound error during context initialization. `ApplicationRunner` will not print the usual three lines because the context did not finish starting.

That is the observable difference: **without changing YAML, only switching `ignoreUnknownFields` from `true` to `false`**.

### 5.5. Keep strict mode and remove the extra key

Delete the line:

```yaml
trace-mode: verbose
```

Leaving YAML as:

```yaml
mailer:
  enabled: true
  max-attempts: 5
  timeout: 2s
```

Repackage. Provided there are no other errors, the application starts normally again and prints the same three bound values.

These three steps demonstrate:

| Configuration | `ignoreUnknownFields` | Result |
| --- | --- | --- |
| Has `mailer.trace-mode` with no target field | `true` | Can start; extra key is ignored |
| Same YAML, extra key still present | `false` | Unbound/binding error |
| Extra key removed | `false` | Binding succeeds |

## 6. Key typos: the bug most easily hidden

Suppose the developer expects configuration:

```yaml
mailer:
  max-attempts: 5
```

but the YAML author mistypes:

```yaml
mailer:
  max-atempt: 5
```

In the Java class, the field name remains `maxAttempts`. This is **not** merely a difference in hyphens or casing; `max-atempt` is missing a `t` and the trailing `s` of the real name.

With `ignoreUnknownFields=true`:

- The Binder has no target for `mailer.max-atempt`.
- The `maxAttempts` component may take the type's default value if the key is missing and no other binding/validation rules exist.
- If `maxAttempts` is a primitive `int`, the default when constructor binding lacks data can be `0`.
- The application can start and behave incorrectly without a clear signal from the mistyped key.

With `ignoreUnknownFields=false`, Spring Boot gets the chance to report `mailer.max-atempt` as unbound. Developers can catch the mistake immediately at startup.

However, **strict mode still does not prove every required key is present**. If the author **completely forgets** `mailer.max-attempts` and declares no extra keys, there may be no unbound property to detect.

Therefore, separate two requirements:

1. **No extra or misspelled keys:** use `ignoreUnknownFields=false` where appropriate.
2. **Required values must exist and be valid:** use validation, suitable types, and explicit rules.

Setting `ignoreUnknownFields=false` does not replace constraints like requiring retry count to be greater than 0.

## 7. Unknown, missing, and invalid: three distinct states

Three easily confused error categories:

### 7.1. Unknown property — key has no target

```yaml
mailer:
  old-retry-setting: 3
```

The class has no `oldRetrySetting` field or corresponding receiving structure. This situation falls under `ignoreUnknownFields`.

### 7.2. Missing property — class expects it, source does not supply it

```java
@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(
        String senderAddress
) {}
```

If `mailer.sender-address` is completely absent, this is a **missing property**. There is no extra key for `ignoreUnknownFields=false` to catch. The record may receive `null` unless other requirements apply.

To require `senderAddress` to be provided, use validation such as `@NotBlank` or an explicit check.

### 7.3. Invalid property — right key, unconvertible value

```yaml
mailer:
  max-attempts: many
```

If the record has `int maxAttempts`, this key has the **right name**, yet the value `many` does not match `int`. Normally, binding fails due to type conversion regardless of whether `ignoreUnknownFields` is `true` or `false`.

Comparison table:

| Situation | Example | Mechanism involved |
| --- | --- | --- |
| Key has no target field | `mailer.debug-mode` | `ignoreUnknownFields` |
| Required key is missing | Absent `mailer.sender-address` | Validation / precondition check |
| Key has wrong value type | `mailer.max-attempts=many` | Type conversion |
| Right type, nonsensical value | `mailer.max-attempts=-3` | Validation / business constraint |
| Key outside bound prefix | `payment.debug-mode` when binding `mailer` | Outside `MailerProperties` scope |
| Name difference supported by relaxed binding | `max-attempts` ↔ `maxAttempts` | Not unknown |

**The meaning of `ignoreUnknownFields` is narrow and specific:** it is not a switch to "fail on every unusual configuration".

## 8. Comparing `ignoreUnknownFields` and `ignoreInvalidFields`

`@ConfigurationProperties` has two similarly named attributes:

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false,
        ignoreInvalidFields = false
)
```

The two attributes are not synonymous:

- `ignoreUnknownFields`: handles properties **without a binding target** in the structure.
- `ignoreInvalidFields`: governs whether to ignore errors where **a value cannot be bound/converted** in certain situations.

Common defaults:

```text
ignoreUnknownFields = true
ignoreInvalidFields = false
```

Suppose:

```java
@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(
        int maxAttempts
) {}
```

Case A:

```properties
mailer.max-attempts=5
mailer.unknown-switch=on
```

`max-attempts` has a target; `unknown-switch` does not. `ignoreUnknownFields` is the attribute of interest.

Case B:

```properties
mailer.max-attempts=not-a-number
```

The key exists and has target `int maxAttempts`, yet `not-a-number` cannot convert to an integer. This error belongs to **invalid conversion/binding**, which is not fixed by `ignoreUnknownFields=true`.

Do not turn on `ignoreInvalidFields=true` merely because you want the application to always start. Ignoring wrongly typed values can leave objects in default states, missing data, or behaving unpredictably across different structures. For important data, **failing fast** is usually safer.

When investigating a failure, ask in order:

```text
1. Does the key belong to the right prefix?
2. Does the key map to a field/path in the class?
3. If so, does the value convert to the right type?
4. If converted, does the value satisfy business constraints?
```

Each question corresponds to a different verification layer.

## 9. Strict mode only checks within the bound prefix scope

Suppose:

```java
@ConfigurationProperties(
        prefix = "mail",
        ignoreUnknownFields = false
)
public record MailProperties(
        String host,
        int port
) {}
```

Configuration:

```yaml
mail:
  host: smtp.example.invalid
  port: 2525

payment:
  endpoint: https://payments.example.invalid
  experimental-flag: true
```

`MailProperties` only binds the `mail` group. It has no responsibility to accept or inspect keys in the `payment` group. Thus, strict mode on `MailProperties` is not a tool to detect mistakes in `payment.experimental-flag`.

To validate `payment`, you need a configuration model and corresponding rules for that group itself, if it belongs to the application and truly needs strict binding.

Also understand that a Spring Boot application has **many configuration sources used by the framework and libraries**. It makes no sense for a `@ConfigurationProperties(prefix="mail")` class to validate every key starting with `server.`, `spring.`, or `management.`.

### One prefix shared by multiple beans

If two beans bind the same `mail` prefix while each only accepts a different subset, strict mode can become a problem:

```java
@ConfigurationProperties(prefix = "mail", ignoreUnknownFields = false)
public record MailTransportProperties(String host, int port) {}

@ConfigurationProperties(prefix = "mail", ignoreUnknownFields = false)
public record MailPolicyProperties(int maxAttempts) {}
```

In YAML:

```yaml
mail:
  host: smtp.example.invalid
  port: 2525
  max-attempts: 4
```

Each class covers only part of the properties under the same prefix. If the binder performs strict unbound checks per bean, each class may treat the other class's keys as unbound.

When separating responsibilities cleanly, separate the prefixes as well:

```yaml
mail:
  transport:
    host: smtp.example.invalid
    port: 2525
  policy:
    max-attempts: 4
```

```java
@ConfigurationProperties(
    prefix = "mail.transport",
    ignoreUnknownFields = false
)
public record MailTransportProperties(String host, int port) {}

@ConfigurationProperties(
    prefix = "mail.policy",
    ignoreUnknownFields = false
)
public record MailPolicyProperties(int maxAttempts) {}
```

This gives each class an independent configuration contract and avoids strict mode conflicting with how classes are split.

## 10. Nested configuration and extra properties

A property is not limited to top-level fields. With nested configuration groups:

```yaml
transfer:
  endpoint:
    host: transfer.example.invalid
    port: 8443
    protocol: https
  retries: 3
```

You can use a nested record:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "transfer",
        ignoreUnknownFields = false
)
public record TransferProperties(
        Endpoint endpoint,
        int retries
) {
    public record Endpoint(
            String host,
            int port
    ) {}
}
```

The `Endpoint` class has only `host` and `port`, not `protocol`. Thus, `transfer.endpoint.protocol` is an extra-property candidate within the structure under prefix `transfer`.

Add the corresponding field:

```java
public record Endpoint(
        String host,
        int port,
        String protocol
) {}
```

and the binder has a target for `protocol`. Or remove that key if unused. Decide based on the configuration contract; do not add fields just to "make the error go away" when the feature does not need that value.

### Deep paths do not equate to unknown keys at the root

Even if the top-level record has `Endpoint endpoint`, not every `transfer.endpoint.*` key is accepted unconditionally. The Binder must descend into `Endpoint`'s structure to determine which properties have targets.

Conversely, a field designed as `Map<String, String>` can accept many dynamic keys without declaring each name upfront in the class. With a map structure, an "unknown key" may be **valid data** because the model allows an open set of names.

## 11. Maps, lists, and models with dynamic keys

Consider declaring endpoints for multiple regions:

```yaml
regions:
  endpoints:
    ap-southeast-1: https://ap.example.invalid
    eu-west-1: https://eu.example.invalid
```

An appropriate class:

```java
import java.net.URI;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "regions",
        ignoreUnknownFields = false
)
public record RegionProperties(
        Map<String, URI> endpoints
) {}
```

With `Map<String, URI>`, region names are **data keys**, and do not need Java fields named `apSoutheast1` or `euWest1`. Therefore, strict mode cannot be interpreted simply as "only allow key names that appear in Java code along every path segment".

If the application must forbid unsupported regions, enforce the allowed set via a separate validation mechanism: an enum, custom validator, allowlist, or appropriate business rule.

For example, if the config accidentally writes:

```yaml
regions:
  endpoints:
    ap-southeast-2: https://ap2.example.invalid
```

The Binder can treat `ap-southeast-2` as a valid map entry. `ignoreUnknownFields=false` is not responsible for verifying whether that region name is on the company's approved list.

Similarly, lists have their own indexes and elements; do not treat strict mode as a full schema validator like JSON Schema for all collection structures.

## 12. Using relaxed binding to avoid wrong conclusions

Spring Boot uses relaxed binding to map equivalent naming styles in appropriate sources.

Java example:

```java
@ConfigurationProperties(prefix = "order")
public record OrderProperties(
        int maxAttempts,
        boolean dryRun
) {}
```

Key forms Spring Boot can recognize depending on source:

```text
order.max-attempts
order.maxAttempts
order.dry-run
order.dryRun
```

When using environment variables, Spring Boot applies specific naming rules; for instance, canonical `order.max-attempts` can map to `ORDER_MAXATTEMPTS` in the standard environment source. Do not arbitrarily insert underscores everywhere and assume every system produces the same result.

When diagnosing an unbound property:

1. Read the exact key being supplied.
2. Read the prefix and actual field names in the class.
3. Check whether that name is merely a variant supported by relaxed binding.
4. If not, confirm whether it is a new key, an unremoved old key, or a typo.

For example, `order.max-attemtps` is a character-transposition typo; it is not an equivalent naming style for `order.maxAttempts`.

Enabling strict mode is often helpful when a team wants to catch typos like this right at startup.

## 13. Automated tests: catching extra keys with `ApplicationContextRunner`

Besides running the JAR manually, you can verify binding rules with Spring Boot Test. `ApplicationContextRunner` lets you spin up a lightweight application context with test-supplied properties.

Suppose we have:

```java
package com.example.unknown;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false
)
public record MailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

A test class:

```java
package com.example.unknown;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.context.PropertyPlaceholderAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class MailerPropertiesTest {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(PropertiesTestConfig.class);

    @Test
    void bindsKnownProperties() {
        contextRunner
            .withPropertyValues(
                "mailer.enabled=true",
                "mailer.max-attempts=4"
            )
            .run(context -> {
                assertThat(context.getStartupFailure()).isNull();
                MailerProperties properties =
                    context.getBean(MailerProperties.class);
                assertThat(properties.maxAttempts()).isEqualTo(4);
            });
    }

    @Test
    void rejectsUnknownPropertyWhenStrict() {
        contextRunner
            .withPropertyValues(
                "mailer.enabled=true",
                "mailer.max-attempts=4",
                "mailer.trace-mode=verbose"
            )
            .run(context -> {
                assertThat(context.getStartupFailure()).isNotNull();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(MailerProperties.class)
    static class PropertiesTestConfig {
    }
}
```

The test requires the `spring-boot-starter-test` dependency (which includes the needed testing tools). `PropertyPlaceholderAutoConfiguration` is imported in the example but is not required to demonstrate this check; that import can be removed if the IDE flags it as unused.

What the test proves:

- When only matching keys exist, the bean is created with the expected values.
- When an unmapped key is present with `ignoreUnknownFields=false`, the context can fail to start.
- No large application or real network call is needed to prove the annotation's difference.

This is a **binding contract** test. It does not test mailer business logic or email content.

### Separate test for default mode

To verify lenient mode, change the annotation on another test type to:

```java
@ConfigurationProperties(prefix = "mailer")
public record LenientMailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

Register this type in a separate test context. With `mailer.enabled=true`, `mailer.max-attempts=4`, `mailer.trace-mode=verbose`, the binder can create the object successfully and ignore the extra key.

Do not register two different records with the same prefix simultaneously in a single test if the goal is simply to compare each class's behavior; each test should enable only one contract for clear results.

## 14. Does strict mode catch all unused configuration?

Do not treat `ignoreUnknownFields=false` as a static linter for an entire YAML file.

There are several limitations to recognize:

- It applies when a **`@ConfigurationProperties` object is actually bound**. If the class is unregistered, no binding occurs for it to detect extra keys.
- Its scope is **the target object's prefix**, not every prefix in `Environment`.
- Different configuration sources supply and enumerate properties differently; do not assume every key variant from every external source is checked identically.
- Open structures like `Map` allow dynamic keys and can validly consume them.
- A property might be handled separately by another bean, even without a target in the bean under inspection.
- There is no guarantee that missing a required key will be detected solely by strict mode.
- There is no guarantee that a syntactically valid value satisfies business requirements.

Therefore, combine:

```text
strict binding           -> limits extra/misspelled keys
type conversion          -> blocks wrongly typed data
Bean Validation          -> checks required keys / value ranges
tests                    -> verifies the contract per config source
code review / docs       -> clarifies supported key names
```

These are complementary layers of defense, not interchangeable ways of achieving the same goal.

## 15. Combining `ignoreUnknownFields` with validation

Suppose a configuration must have an HTTPS endpoint, a positive timeout, and at least 1 retry attempt.

The record can start with:

```java
package com.example.unknown;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "gateway",
        ignoreUnknownFields = false
)
public record GatewayProperties(
        @NotNull URI endpoint,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts
) {}
```

YAML example:

```yaml
gateway:
  endpoint: https://gateway.example.invalid/api/
  timeout: 3s
  max-attempts: 4
```

With an appropriate validation dependency such as `spring-boot-starter-validation`:

- If YAML has `gateway.timeot: 3s` instead of `gateway.timeout`, strict binding can catch the unmapped `timeot` key.
- If `gateway.timeout` is completely absent, `@NotNull` detects the missing required value.
- If `gateway.max-attempts=0`, `@Min(1)` detects the out-of-range value.
- If `gateway.max-attempts=abc`, conversion to `int` can fail before validation can treat it as a valid number.

This design ensures **configuration mistakes surface at startup**, instead of waiting until a critical request uses a wrong field.

### Do not treat `@NotNull` on `URI` as HTTPS verification

`URI` can represent many URI schemes, including non-HTTPS ones. `@NotNull` only requires non-null. If business rules require HTTPS or an allowlisted host, use appropriate custom validation.

Similarly, `Duration` can represent negative numbers or zero; `@NotNull` does not guarantee a positive timeout. Use a dedicated check or constraint matching your design.

## 16. When should you set `ignoreUnknownFields = false`?

Strict mode is most useful when a configuration group is defined as a **complete contract**, owned by a single application or module.

Examples:

- `billing.*` contains regulated operational parameters where a wrong key name could lead to unintended payment decisions.
- `shipping.*` is a standalone configuration object where every key in the group is modeled in the properties class.
- An internal library exposes public configuration with a clearly documented list of supported keys and wants to fail fast if deprecated keys linger after an upgrade.
- A service needs to verify that deployment configuration matches the current code version.

In those situations, advantages include:

1. Catching typos early.
2. Preventing obsolete configuration from lingering unnoticed.
3. When field names change, forcing related configuration files to be updated.
4. Providing clear signals to testing or deployment pipelines.
5. Helping govern a bounded, documented configuration contract.

However, strict mode can be inconvenient when a prefix is **intentionally shared** among multiple consumers or has keys that cannot be enumerated beforehand. In such designs, revisit prefix boundaries or data types rather than enabling strict mode everywhere.

## 17. When should you keep the default `true`?

Lenient mode fits when the goal is to **read a subset of configuration** without owning the entire key space.

Examples:

- A module only cares about a few properties under a shared prefix.
- The configuration source contains extra keys meant for another deployment component.
- The configuration model evolves incrementally and needs compatibility with older source versions.
- An integration needs to read a typed subset of data whose remaining parts are handled differently.

Downside: it is harder to spot extra keys or misspelled names merely from the app starting successfully.

To mitigate risk, you can:

- Define dedicated, clear prefixes for each properties group.
- Use validation annotations on required fields.
- Write integration tests binding supported config files.
- Document the key set per module.
- Leverage metadata to help IDEs suggest property names.

The key is to **choose based on the configuration contract**. `true` is not always wrong; `false` is not always right.

## 18. Impact when upgrading versions or renaming properties

Suppose version 1 of the application uses:

```yaml
mailer:
  retry-count: 3
```

And Java:

```java
@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(int retryCount) {}
```

In a later version, the team renames it to `max-attempts`:

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false
)
public record MailerProperties(int maxAttempts) {}
```

If deployment still keeps the old key `mailer.retry-count`, strict mode can stop the application at startup and point out the un-updated old key.

With default `true`, the old key may be ignored; `maxAttempts` receives no explicit value and may end up with a missing or unsuitable default. Here strict mode delivers significant operational benefit.

However, if a transition period requires supporting **both key names**, do not simply enable strict mode and break older deployments. Establish an **intentional migration plan**, for example:

- Temporarily accept both keys via a suitable transitional configuration model.
- Mark the old name deprecated in docs/metadata if supported.
- Update configuration files and deployment systems.
- Remove the old name once the compatibility window ends.
- Enable strict mode as readiness allows, rather than unexpectedly breaking deployments.

Do not assume Spring Boot converts every old name to a new name automatically. Relaxed binding supports **spelling variants of a single property name**, not arbitrary semantic renames between versions.

## 19. Configuration metadata helps catch errors earlier

Spring Boot has an annotation processor that generates metadata for `@ConfigurationProperties`. When a project uses `spring-boot-configuration-processor`, IDEs can use the metadata to suggest property names, data types, and descriptions.

For example, when typing:

```yaml
mailer:
  max-attempts:
```

the IDE can suggest `max-attempts` if metadata for `MailerProperties` has been generated and the IDE supports it. This reduces typos like `max-atempt` or `retry-cout`.

Still, there are differences:

- **Metadata/IDE:** assists config authors during development; warning levels vary by IDE and build.
- **`ignoreUnknownFields=false`:** affects runtime binding behavior of the properties class.
- **Validation:** checks values against type and business rules.

Do not treat metadata as proof that the application checked all files and properties at runtime. They are complementary tools operating at different stages.

## 20. Reading unbound errors and identifying root causes

When an application fails with a binding error mentioning unbound elements, analyze step by step rather than rushing to disable strict mode.

### Step 1: identify the bean and prefix

Does the error belong to `MailerProperties` with prefix `mailer` or another class? Check the annotation:

```java
@ConfigurationProperties(
    prefix = "mailer",
    ignoreUnknownFields = false
)
```

### Step 2: locate the specific key

Suppose the message mentions `mailer.trace-mode`. Find this exact key in the provided configuration sources. It might appear in YAML, properties, environment variables, or command-line arguments depending on the source.

### Step 3: compare with the Java class structure

Does the class have `traceMode`? Is there a nested structure or map consuming it? If the key is a typo, fix it to the proper canonical name.

### Step 4: inspect source precedence

A value can exist in multiple sources. When diagnosing, note which source declares the key and the precedence order. Do not open only one YAML file and assume it represents the entire process configuration.

### Step 5: decide whether to fix the file or the class

If the extra key is no longer used: remove it from configuration.

If the key is a new requirement: add a properly typed field along with the necessary usage logic and validation.

If the key belongs to a different domain: separate the prefixes so binders do not overlap.

If the prefix is designed to be shared: evaluate whether strict mode fits that usage scope.

### Step 6: perform a clean restart

After editing YAML or classes, repackage as needed and start a fresh process. Do not expect Spring to automatically rebind an already-created record when a file is edited while running.

### Why shouldn't you immediately switch to `ignoreUnknownFields = true`?

Changing `false` to `true` can hide typos and let the application start even though the intended configuration was never applied. If you genuinely want to change the policy for accepting extra keys, document the design reason rather than treating turning off strictness as a universal fix.

## 21. Questions to avoid misinterpreting

### "Turning on `false` means every key in the YAML file must have a field?"

No. It applies only to **the bound prefix scope and registered object binding**. Having `server.*`, `spring.*`, and `mailer.*` groups in one file is normal.

### "If a field is missing from YAML, will strict mode detect it?"

Not necessarily. That is a **missing property**, not an unknown property. To require a value to be present, use validation or another contract mechanism.

### "If YAML contains text instead of an `int`, will `true` ignore it?"

`ignoreUnknownFields=true` is not a mechanism for ignoring type conversion errors. Wrong types are a type-conversion concern; `ignoreInvalidFields` is a separate attribute whose consequences must be weighed before use.

### "Does a hyphen make a key name unknown?"

Not necessarily. Spring Boot supports relaxed binding between spellings like `max-attempts` and the Java component `maxAttempts` under the appropriate rules.

### "Can `false` be used as a security filter for all environment variables?"

No. It is not a configuration firewall or secret filter. Bound sources and structures have limits; security policies require dedicated safeguards.

### "Does enabling `false` remove all unused values from `Environment`?"

No. Unbound checks concern bean-binding integrity; they are not commands to mutate raw `PropertySource` data.

### "Is a key inside a `Map` treated as unknown?"

You cannot conclude that merely because the key name does not appear as a Java field. `Map<String, ...>` is designed to accept dynamic data keys.

## 22. Practice exercises

### Exercise 1: predict behavior

Given the record:

```java
@ConfigurationProperties(prefix = "queue")
public record QueueProperties(
        String name,
        int capacity
) {}
```

And configuration:

```yaml
queue:
  name: inbound
  capacity: 100
  durable: true
```

Questions:

1. Does `queue.durable` have a target in the record?
2. With the annotation above, can the application continue starting?
3. If `ignoreUnknownFields=false` is added, what error can occur?
4. If a `boolean durable` field is added, how does the situation change?

### Exercise 2: distinguish missing from misspelled

Class:

```java
@ConfigurationProperties(
    prefix = "cache",
    ignoreUnknownFields = false
)
public record CacheProperties(
        String host,
        int port
) {}
```

Compare two files:

```yaml
# File A: port is not declared at all
cache:
  host: localhost
```

```yaml
# File B: misspelled name
cache:
  host: localhost
  prot: 6379
```

Why are A and B not handled the same way? Strict mode can detect `prot`, whereas requiring `port` needs a separate constraint.

### Exercise 3: wrongly typed value

```yaml
cache:
  host: localhost
  port: seven
```

Explain why `ignoreUnknownFields=true` does not automatically turn `seven` into a default value. This is a correctly named key whose value cannot be converted to `int`.

### Exercise 4: nested properties

```java
@ConfigurationProperties(
    prefix = "storage",
    ignoreUnknownFields = false
)
public record StorageProperties(
        Connection connection
) {
    public record Connection(
            String host,
            int port
    ) {}
}
```

```yaml
storage:
  connection:
    host: storage.example.invalid
    port: 9000
    secure: true
```

Identify which key lacks a target. Then propose a fix: add `boolean secure` if meaningful, or remove the key from the source if unused.

### Exercise 5: organize independent prefixes

An application has `AuditProperties` and `AuditSinkProperties` both reading prefix `audit`. Both enable strict mode and each accepts only a subset. Redesign them into `audit.policy.*` and `audit.sink.*` to separate the groups and avoid conflicts caused by properties belonging to the other class.

### Exercise 6: write contract tests

Using `ApplicationContextRunner`, write two tests:

- Data with only valid keys must bind successfully.
- Data with an extra `mailer.trace-mode` must cause startup failure when `ignoreUnknownFields=false`.

Then create a lenient version with the same prefix registered in a separate context and observe the difference.

### Exercise 7: key-name migration

Suppose the old version used `retry-count` and the new version uses `max-attempts`. Plan deployment updates and tests so that enabling strict mode does not break deployments still using the old key.

## 23. Summary

`ignoreUnknownFields` defines the policy for handling **properties within binding scope that have no corresponding target in the `@ConfigurationProperties` class**.

```text
@ConfigurationProperties(prefix = "mailer")
          |
          v
      mailer.* config
          |
          v
          Binder
          |
     +----+----+
     |         |
Has target   No target
     |         |
     v         v
   Bind     ignoreUnknownFields
                 |
            +----+----+
            |         |
          true      false
            |         |
         Ignore   Report unbound
```

Key points to remember:

1. **Default is `ignoreUnknownFields=true`**, so extra keys can be ignored.
2. **`ignoreUnknownFields=false`** helps detect unbound keys and can stop application startup.
3. **Unknown is not missing.** Missing required properties need validation, not just strict mode.
4. **Unknown is not invalid.** Wrongly typed values are handled by type conversion and binding.
5. **Strict mode does not inspect the entire `Environment`**; it operates within the bound object/prefix scope, subject to source and data-model boundaries.
6. **Clearly scoped prefixes** make strict mode reliable and reduce conflicts across configuration beans.
7. **Validation and tests** complete the contract: not just right key names, but sufficient values fitting business rules.

For an independently owned, tightly governed configuration group with few dynamic keys, `ignoreUnknownFields=false` can be an effective way to **catch typos and obsolete settings early**. For an intentionally shared prefix or an open-key model, keeping the default may be more appropriate, paired with validation and clear documentation.

References: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Spring Boot — ConfigurationProperties API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html), and [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).
