# Required Properties with `getRequiredProperty` and Checking `containsProperty` in Spring Boot

## 1. Problem: Is a configuration property actually provided?

Spring Boot can obtain configuration from many sources: `application.yml`, `application.properties`, files outside the JAR, OS environment variables, Java system properties, and command-line arguments. Applications often need to distinguish two situations:

- **Optional property:** if not provided, use a default or disable a feature.
- **Required property:** if the value is missing, fail early rather than starting up with invalid configuration and only hitting an issue when handling a request.

For example, an HTTP port can use a default, whereas a payment service address or a mandatory topic name may not be allowed to be missing.

Spring Framework provides the `PropertyResolver` interface, and `Environment` extends that interface. Two key methods are:

~~~java
boolean exists = environment.containsProperty("payment.gateway.url");
String required = environment.getRequiredProperty("payment.gateway.url");
~~~

`containsProperty` returns whether **a value can be looked up** for the property name; `getRequiredProperty` returns the value if present, or throws an exception if it cannot be looked up.

> Important distinction: **"Property exists" does not mean "the value is valid for business logic"**. Empty strings, whitespace, invalid URLs, and out-of-range numbers still need separate checks.

## 2. Where do `Environment` and `PropertyResolver` sit?

In a Spring Boot application, `Environment` is an abstraction for accessing effective configuration. It combines `PropertySource`s according to precedence order and returns the value of a specific property.

Conceptual diagram:

~~~text
                 Configuration sources
      +---------------------------------------+
      | --payment.gateway.url=...             |
      | -Dpayment.gateway.url=...             |
      | PAYMENT_GATEWAY_URL=...               |
      | application-prod.yml                  |
      | application.yml                       |
      | default properties                    |
      +---------------------------------------+
                          |
                          v
                     Environment
                          |
                 PropertyResolver API
                          |
           +--------------+----------------+
           |              |                |
      getProperty()  containsProperty() getRequiredProperty()
           |              |                |
     get value      check if value     fail if missing
                      is present
~~~

It is not the case that whichever file is loaded last beats every other source. Spring Boot applies **configuration source precedence**, then resolves each property by name. When looking up `payment.gateway.url`, a value from a higher-precedence source wins over a value with the same name in a lower-precedence source.

Example:

~~~yaml
# application.yml
payment:
  gateway:
    url: https://sandbox.example.test
    connect-timeout-ms: 2000
~~~

If the runtime environment has the variable `PAYMENT_GATEWAY_URL=https://payments.example.test`, `Environment` can return the production URL from the environment variable, while `connect-timeout-ms` still takes the value `2000` from the file.

Both `containsProperty` and `getRequiredProperty` operate on the **effective configuration system**, not limited solely to `application.yml`.

## 3. Comparing property access methods

| Method | When property is present | When property is missing | Purpose |
| --- | --- | --- | --- |
| `getProperty("app.name")` | Returns `String` | Returns `null` | Optional value |
| `getProperty("app.name", "default")` | Returns existing value | Returns `"default"` | Has fallback value |
| `containsProperty("app.name")` | Typically returns `true` when value can be looked up | Returns `false` | Presence check |
| `getRequiredProperty("app.name")` | Returns `String` | Throws `IllegalStateException` | Required value |
| `getRequiredProperty("app.port", Integer.class)` | Converts value to `Integer` | Throws error when missing; wrong-type value can also cause conversion error | Typed required value |

Commonly used overloads:

~~~java
environment.getProperty("app.name");
environment.getProperty("app.name", "Demo");
environment.getProperty("app.port", Integer.class);
environment.getProperty("app.port", Integer.class, 8080);

environment.containsProperty("app.name");
environment.getRequiredProperty("app.name");
environment.getRequiredProperty("app.port", Integer.class);
~~~

To understand more thoroughly:

- `getProperty` fits when the absence of a property is a valid state.
- `getProperty(..., defaultValue)` avoids forcing calling code to handle `null` when a fallback is intended.
- `containsProperty` only asks about presence; it does not evaluate URLs, passwords, or numeric ranges.
- `getRequiredProperty` fits when **having no value** is a configuration error.
- Typed overloads require an extra **type conversion** step; you cannot assume any arbitrary string converts to `Integer`, `Boolean`, or a custom type.

These methods belong to `org.springframework.core.env.PropertyResolver`; `Environment` is the interface usually injected to use them in a Spring application.

## 4. Checking presence with `containsProperty`

### 4.1. Simple example

File `application.yml`:

~~~yaml
app:
  region: vn
  feature:
    enabled: false
~~~

In a component:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class FeatureInspector {
    public FeatureInspector(Environment environment) {
        boolean hasRegion = environment.containsProperty("app.region");
        boolean hasFlag = environment.containsProperty("app.feature.enabled");
        boolean hasMissing = environment.containsProperty("app.unknown");

        System.out.println("region present: " + hasRegion);
        System.out.println("feature flag present: " + hasFlag);
        System.out.println("unknown present: " + hasMissing);
    }
}
~~~

If no additional source declares `app.unknown`, the results are `true`, `true`, and `false`, respectively.

Easy mistake: `app.feature.enabled=false` **is still a declared value**. Do not use `containsProperty("app.feature.enabled")` to conclude whether the feature is enabled or disabled. Read the **boolean value** instead:

~~~java
Boolean enabled = environment.getProperty(
        "app.feature.enabled", Boolean.class, false);
~~~

In the example, `enabled` is `false` even though `containsProperty` returns `true`.

### 4.2. Do not check a YAML branch name as a single value

With configuration:

~~~yaml
app:
  client:
    host: api.example.test
    port: 443
~~~

Leaf properties typically have names:

~~~text
app.client.host
app.client.port
~~~

Do not assume:

~~~java
environment.containsProperty("app.client")
~~~

must return `true` just because YAML has the parent key `client:`. When YAML is flattened into properties, the `app.client` branch may **have no direct scalar value**. Query the actual keys you need, such as `app.client.host` and `app.client.port`.

### 4.3. Check and then retrieve the value

Simple pattern:

~~~java
if (environment.containsProperty("app.region")) {
    String region = environment.getProperty("app.region");
    // Use region after validating if needed.
}
~~~

This pattern is useful when you need to distinguish "provided" from "not provided". However, if you only want to get a value with a default, it is shorter to write:

~~~java
String region = environment.getProperty("app.region", "vn");
~~~

For a **required** property, calling `getRequiredProperty` directly usually expresses intent more clearly than checking `containsProperty` and throwing an exception manually.

## 5. Using `getRequiredProperty` to fail when a key is missing

### 5.1. Basic syntax

~~~java
String gatewayUrl = environment.getRequiredProperty(
        "payment.gateway.url");
~~~

If the property exists in an effective configuration source, the method returns a `String`. If no suitable value is found, the method throws `IllegalStateException`.

For example, when the application has no `payment.gateway.url` in files, environment variables, system properties, or other sources:

~~~java
String gatewayUrl =
        environment.getRequiredProperty("payment.gateway.url");
~~~

Instead of receiving `null` as with `getProperty`, the application enters the exception path. This is useful to avoid silently using an empty configuration for a mandatory dependency.

The error message can indicate which property was not found. Do not rely on the exact error message text as a stable API for control-flow logic; rely on the **exception type and the missing-property rule**.

### 5.2. Typed version

~~~java
Integer timeoutMs = environment.getRequiredProperty(
        "payment.gateway.connect-timeout-ms", Integer.class);
~~~

With:

~~~properties
payment.gateway.connect-timeout-ms=2500
~~~

the returned value is the integer `2500`. If the property is missing, the method reports a required-property error. If the property has the value `abc`, conversion to `Integer` can fail with a type-conversion exception, **distinct** from the property-not-found error.

Therefore, distinguish:

| Situation | Expected behavior |
| --- | --- |
| Key `payment.gateway.connect-timeout-ms` is not declared | Missing required property error |
| Key has value `2500` | Converted to `Integer 2500` |
| Key has value `not-a-number` | Type conversion error |
| Key has value `-10` | Can be converted to `Integer -10`, yet **business-invalid** if timeout must be positive |

`getRequiredProperty` does not mean it automatically checks value ranges such as min/max. Semantic validation is the responsibility of the application or validation system.

## 6. Special cases: missing key, empty, blank, `false`, and `0`

One common source of configuration bugs is lumping every "unexpected" value together as "property does not exist".

Suppose an application requires `app.api-key`. Distinguish:

| Configuration value | `containsProperty` | `getRequiredProperty` | Valid as a required secret? |
| --- | --- | --- | --- |
| Property absent from all sources | `false` | Throws missing-property error | No |
| `app.api-key=` | Typically `true` because empty string is a present value | Can return `""` | **No**, must check blank |
| `app.api-key=   ` | Can be `true` | Can be whitespace string or subject to parser rules | **No**, must check blank |
| `app.feature.enabled=false` | `true` | Returns string `"false"` | Valid boolean value, not missing |
| `app.retry-count=0` | `true` | Returns `"0"` | Can be valid depending on requirements |
| `app.timeout-ms=-1` | `true` | Returns `"-1"` or number `-1` when converted | Invalid if timeout must be positive |

`containsProperty` checks **the presence of a resolvable value**; it does not perform `isBlank()` checks or verify API key strength.

To require a string with actual non-whitespace content:

~~~java
String apiKey = environment.getRequiredProperty("app.api-key");

if (apiKey.isBlank()) {
    throw new IllegalStateException(
            "Required configuration app.api-key must not be blank");
}
~~~

For strings with business-dependent semantics, beyond `isBlank()` you may need to check URL schemes, topic name patterns, min/max bounds, allowed enum values, or other security constraints.

**Never include secret values directly in exception messages or logs.** Only log the **property name** and the reason it is invalid.

## 7. Complete Spring Boot example: fail-fast on missing configuration

Suppose an application needs three values to connect to a payment system:

~~~yaml
# src/main/resources/application.yml
payment:
  gateway:
    connect-timeout-ms: 2500
~~~

The two values `payment.gateway.base-url` and `payment.gateway.api-key` are not packaged inside the JAR because they will be provided by the deployment environment.

### 7.1. Define the settings object

~~~java
package com.example.config;

import java.net.URI;
import java.time.Duration;

public record GatewaySettings(
        URI baseUrl,
        String apiKey,
        Duration connectTimeout) {
}
~~~

### 7.2. Verify when Spring creates the bean

~~~java
package com.example.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class GatewayConfiguration {

    @Bean
    GatewaySettings gatewaySettings(Environment environment) {
        String baseUrl = environment.getRequiredProperty(
                "payment.gateway.base-url");

        String apiKey = environment.getRequiredProperty(
                "payment.gateway.api-key");

        Integer timeoutMs = environment.getRequiredProperty(
                "payment.gateway.connect-timeout-ms", Integer.class);

        if (baseUrl.isBlank()) {
            throw new IllegalStateException(
                    "payment.gateway.base-url must not be blank");
        }
        if (apiKey.isBlank()) {
            throw new IllegalStateException(
                    "payment.gateway.api-key must not be blank");
        }
        if (timeoutMs <= 0) {
            throw new IllegalStateException(
                    "payment.gateway.connect-timeout-ms must be positive");
        }

        URI endpoint;
        try {
            endpoint = URI.create(baseUrl);
        } catch (IllegalArgumentException ex) {
            throw new IllegalStateException(
                    "payment.gateway.base-url is not a valid URI", ex);
        }

        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null) {
            throw new IllegalStateException(
                    "payment.gateway.base-url must be an absolute HTTPS URI");
        }

        return new GatewaySettings(
                endpoint, apiKey, Duration.ofMillis(timeoutMs));
    }
}
~~~

When Spring creates the `GatewaySettings` bean, the required properties are checked. For a regular non-lazy bean, invalid configuration causes context initialization to fail instead of only being discovered on the first gateway call. This is an example of **fail-fast** at startup time.

Unix command supplying configuration via environment variables:

~~~bash
export PAYMENT_GATEWAY_BASE_URL=https://payments.example.test
export PAYMENT_GATEWAY_API_KEY="example-secret-from-secret-manager"
java -jar app.jar
~~~

The illustrative value above is not a real key; in production, inject secrets from a protected environment or secret manager rather than hard-coding them into a repository or logging them.

In the example:

- `payment.gateway.connect-timeout-ms` comes from `application.yml`.
- `payment.gateway.base-url` is provided by the OS environment.
- `payment.gateway.api-key` is provided by the OS environment.
- `getRequiredProperty` retrieves the **effective value** after Spring evaluates property source precedence.
- `isBlank()`, checking `timeoutMs > 0`, and checking the HTTPS URI are **additional validation**, not built-in features of `getRequiredProperty`.

### 7.3. Where do errors appear?

If `PAYMENT_GATEWAY_API_KEY` is not provided and no other source declares `payment.gateway.api-key`, the `getRequiredProperty` call throws an exception. Because the configuration bean cannot be created, Spring Boot typically reports an application context startup failure.

If a value is provided as an empty string, `getRequiredProperty` can return that string, and the `isBlank()` check rejects it.

If `connect-timeout-ms` contains text that cannot be converted to an integer, the application can fail right at the type conversion step before reaching the `<= 0` check.

## 8. `containsProperty` for optional features

For an optional value, you might only enable logic when configuration is explicitly provided.

Example:

~~~yaml
app:
  reporting:
    enabled: false
~~~

In Java:

~~~java
Boolean enabled = environment.getProperty(
        "app.reporting.enabled", Boolean.class, false);

if (Boolean.TRUE.equals(enabled)) {
    // Enable reporting.
}
~~~

This is usually the more appropriate pattern over:

~~~java
if (environment.containsProperty("app.reporting.enabled")) {
    // Does not mean reporting is enabled.
}
~~~

Because the value `false` still makes `containsProperty` return `true`.

One reasonable case for `containsProperty` is wanting to know **whether the deployer declared an override or not**, for example:

~~~java
if (!environment.containsProperty("app.reporting.sample-rate")) {
    // No override; pick an appropriate internal policy.
} else {
    Integer sampleRate = environment.getRequiredProperty(
            "app.reporting.sample-rate", Integer.class);

    if (sampleRate < 0 || sampleRate > 100) {
        throw new IllegalStateException(
                "app.reporting.sample-rate must be between 0 and 100");
    }
}
~~~

Here `containsProperty` means "was a custom configuration declared?", while formatting and range checks belong to the subsequent steps.

## 9. Difference from `getProperty(..., defaultValue)`

If a property is genuinely optional and an acceptable fallback value exists, `getProperty` has overloads taking a default:

~~~java
String locale = environment.getProperty("app.locale", "vi-VN");

Integer retryCount = environment.getProperty(
        "app.retry-count", Integer.class, 3);
~~~

If `app.locale` is absent, Spring returns `vi-VN`. If `app.retry-count` is absent, it returns the integer `3`.

Do not use unconditional fallbacks for **required** configuration. For example:

~~~java
String gatewayUrl = environment.getProperty(
        "payment.gateway.base-url",
        "https://sandbox.example.test");
~~~

This snippet could cause production to silently connect to sandbox if someone forgets to inject the deployment URL. When a URL is required by policy, using `getRequiredProperty` and validation expresses intent more clearly.

Comparing the three approaches:

~~~java
// Null if missing: suitable for optional values.
String a = environment.getProperty("app.value");

// Default if missing: suitable when fallback is intentional.
String b = environment.getProperty("app.value", "fallback");

// Error if missing: suitable when omission is not allowed.
String c = environment.getRequiredProperty("app.value");
~~~

No single method is "best" in every case; they express **different configuration contracts**.

## 10. `containsProperty` does not tell you where a property came from

Suppose an application has:

~~~yaml
# application.yml
app:
  mode: sandbox
  timeout-ms: 1000
~~~

At startup:

~~~bash
APP_MODE=production java -jar app.jar --app.timeout-ms=2500
~~~

With default behavior and no higher-precedence source in the example:

~~~java
environment.containsProperty("app.mode");        // true
environment.getRequiredProperty("app.mode");      // "production"
environment.containsProperty("app.timeout-ms");  // true
environment.getRequiredProperty(
        "app.timeout-ms", Integer.class);         // 2500
~~~

Both properties "have a value", yet they come from **different sources**. `containsProperty` only tells you about presence, not whether the value came from YAML, an environment variable, or command-line arguments.

When you need to diagnose the origin, use controlled observability tools such as appropriate Spring Boot Actuator endpoints or inspect `PropertySources` via API. Access must be restricted and sensitive values masked. Never use debug output to expose secrets publicly.

### 10.1. Relaxed names and environment variable names

In Spring Boot, environment variables typically use uppercase and underscores to correspond to dot/hyphen property names. Example:

| Standard property form | Environment variable |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `app.mode` | `APP_MODE` |
| `payment.gateway.base-url` | `PAYMENT_GATEWAY_BASEURL` |
| `payment.gateway.connect-timeout-ms` | `PAYMENT_GATEWAY_CONNECTTIMEOUTMS` |

The canonical rule for binding from a canonical property name to an environment variable is to replace `.` with `_`, **remove** `-`, and convert to uppercase. Depending on the version, lookup APIs and binding may support certain name variants; for real configuration, use the standard form and verify in practice.

For example, when using `Environment.getRequiredProperty("payment.gateway.base-url")`, the environment source must provide a property that the system resolves under that name. Do not assume arbitrary variable names with extra underscores always map as expected.

## 11. Distinguishing `getRequiredProperty` from `@Value`

A familiar way to inject a property:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GatewayClient {

    public GatewayClient(
            @Value("${payment.gateway.base-url}") String baseUrl) {
        // Use baseUrl.
    }
}
~~~

If a required placeholder cannot be resolved, bean initialization normally fails when Spring processes injection. However, `@Value` is a **placeholder injection mechanism**, not the same API as `Environment.getRequiredProperty`.

Comparison:

| Approach | Strengths | Points to note |
| --- | --- | --- |
| `Environment.getRequiredProperty("key")` | Explicit, easy to place custom checks, has typed overloads | Must manage call sites and validation yourself |
| `@Value` | Concise when injecting a few properties | Many scattered properties hurt maintainability and complicate validation |
| `@ConfigurationProperties` | Binds a group of properties to clear Java types | Requires registering the configuration class and proper validation |

If configuration has many related fields, `@ConfigurationProperties` usually gives a cleaner structure than dozens of `getRequiredProperty` calls across different beans.

## 12. Grouping configuration with `@ConfigurationProperties` and Bean Validation

For larger-scale application configuration, Spring Boot supports binding a group of properties into a Java object and then checking constraints with Jakarta Bean Validation.

Example file:

~~~yaml
payment:
  gateway:
    base-url: https://payments.example.test
    connect-timeout: 5s
    max-retries: 3
~~~

Record:

~~~java
package com.example.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment.gateway")
public record GatewayProperties(
        @NotBlank String baseUrl,
        @NotNull Duration connectTimeout,
        @Min(0) int maxRetries) {
}
~~~

Register scanning:

~~~java
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

If the project uses Spring Boot 3.x, validation annotations are in `jakarta.validation.*`. For Bean Validation to run, a suitable implementation must be present, usually via the `spring-boot-starter-validation` dependency.

Benefits:

- `@NotBlank` rejects missing, empty, or whitespace-only strings per Bean Validation semantics.
- `@NotNull` rejects null values.
- `@Min(0)` checks the lower bound on retry count.
- `Duration` can bind values such as `5s` via Spring Boot's conversion mechanism.

A record configuration is one example; a Java class with getters/setters or constructor binding can also be used where appropriate. `@ConfigurationProperties` does not mean every constraint is enforced automatically: you still need **validation annotations** or custom validation logic for business rules.

### 12.1. When should you still use `getRequiredProperty`?

Use `getRequiredProperty` when:

- You need a few independent properties where declaring a whole configuration class is unnecessary.
- You want to check a value early at a specific initialization point.
- You need complex conditional checking algorithms before creating a dependency.
- You are writing an infrastructure component that interacts directly with `Environment`.

Use `@ConfigurationProperties` with validation when:

- There is a configuration group with multiple fields.
- You need type conversion, clear structure, and consistency.
- You want more centralized binding/validation error messages.
- You want to simplify business code and make configuration easier to test.

Both approaches can coexist in an application. There is no need to call `getRequiredProperty` for every field if a configuration properties bean already handles binding and validating those fields.

## 13. Where to place checks so errors fail early?

With the same `getRequiredProperty`, **when it is called** determines when the error surfaces.

| Call site | When it typically runs | Risks or benefits |
| --- | --- | --- |
| Constructor of an eager singleton bean | During context initialization | Can catch missing configuration at startup |
| `@Bean` method returning a required dependency | When Spring creates that bean | Convenient for fail-fast if the bean is not lazy |
| `ApplicationRunner` | After the context is created | Can still fail startup, though at a later stage |
| Business method running only per request | When the feature is invoked | Can discover issues far too late |
| `@Lazy` bean | When the bean is actually instantiated | Does not guarantee errors appear at startup |

Practical recommendation: service-wide required configuration should be **checked during dependency initialization** or in a validated `@ConfigurationProperties` class. Do not let a connection to a critical service fail only when the first production request arrives.

However, if a feature is **not always enabled**, required values for that feature may only need checking when the feature is turned on. For instance, `email.smtp.password` does not need to be required when email functionality is intentionally disabled.

## 14. Checking a set of required properties

When multiple properties are required, there are two strategies:

### 14.1. Fetch sequentially and fail on the first missing key

~~~java
String host = environment.getRequiredProperty("app.remote.host");
String user = environment.getRequiredProperty("app.remote.user");
String token = environment.getRequiredProperty("app.remote.token");
~~~

Advantage: short code, fails immediately. Disadvantage: you may have to fix and restart multiple times if several keys are missing at once.

### 14.2. Collect the list of missing keys before failing

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.core.env.Environment;

public final class RequiredConfigChecker {
    private RequiredConfigChecker() {}

    public static void verify(Environment environment) {
        List<String> missing = new ArrayList<>();

        for (String key : List.of(
                "app.remote.host",
                "app.remote.user",
                "app.remote.token")) {
            if (!environment.containsProperty(key)) {
                missing.add(key);
            }
        }

        if (!missing.isEmpty()) {
            throw new IllegalStateException(
                    "Missing required configuration keys: " + missing);
        }
    }
}
~~~

This collects **keys with no resolvable value**, but it does **not yet** catch empty/blank keys or malformed values. To aggregate those violations as well, add validation checks after lookup.

In a large system, Bean Validation on `@ConfigurationProperties` is usually a more effective way to express multiple group constraints.

## 15. `getRequiredProperty` and placeholder resolution

A configuration value can contain a placeholder referencing another property:

~~~properties
app.remote.url=https://${REMOTE_HOST}/api
~~~

`getRequiredProperty("app.remote.url")` finds the key `app.remote.url`, but resolving its value may additionally require `REMOTE_HOST`. If the placeholder cannot be resolved with the active configuration, the application can fail during resolution or binding.

Distinguish:

1. **Does the requested key itself exist?**
2. **Can placeholders inside its value be resolved?**
3. **Is the resolved value valid for business logic?**

These questions are not completely equivalent. A URL string containing an unresolved placeholder is not a valid URL for most applications.

Spring Framework also provides `resolvePlaceholders(...)` and `resolveRequiredPlaceholders(...)` when you need to process placeholders inside arbitrary strings directly. Do not confuse placeholder-resolution APIs with `getRequiredProperty`, which fetches a property's value by key name.

## 16. When properties come from sources of different precedence

### 16.1. Two sources declaring the same key

File:

~~~yaml
app:
  region: vn
  max-items: 100
~~~

Run command:

~~~bash
APP_REGION=apac java -jar demo.jar --app.max-items=200
~~~

With default behavior and no higher-precedence source:

~~~java
environment.getRequiredProperty("app.region");                // "apac"
environment.getRequiredProperty("app.max-items", Integer.class); // 200
~~~

`getRequiredProperty` does not pick a "config file" by name. It uses the effective value determined by `Environment`.

### 16.2. One source has the key with an unusable value

Suppose a file has:

~~~properties
app.max-items=100
~~~

but a higher-precedence source provides:

~~~bash
APP_MAXITEMS=invalid java -jar demo.jar
~~~

If the property resolves to `"invalid"`, calling:

~~~java
environment.getRequiredProperty("app.max-items", Integer.class);
~~~

will not skip the mistyped source and fall back to `100` from the lower-precedence source. First the property is selected by precedence; a failed conversion is a **configuration error that must be fixed**.

This behavior matters during diagnostics: do not assume that having a valid value in `application.yml` means the application will automatically use it if an override is broken.

### 16.3. Dynamic sources and lookup timing

`containsProperty` and `getRequiredProperty` are runtime calls into `Environment`. In applications with dynamically changing configuration sources, source data could differ between two calls. Therefore, if you need a value for use, **reading it once, validating it, and storing it in a settings object** is usually easier to control than calling `containsProperty` and `getRequiredProperty` at separate moments.

For standard Spring Boot Config Data, most values are loaded at startup and bound during bean creation; editing an external file at runtime does not automatically trigger bean refresh.

## 17. Common mistakes

| Misconception | Correct fact to remember |
| --- | --- |
| "`containsProperty(key) == true` means the value is valid." | Only indicates the property is present/resolvable; still need blank, format, range, and domain checks. |
| "`containsProperty(key)` returns false if the value is `false`." | `false` is a boolean value, not a missing property. |
| "`getRequiredProperty` always returns a non-empty string." | It ensures a resolvable value exists; an empty string can still be returned. |
| "Using `getRequiredProperty(key, Integer.class)` checks for a positive number." | It only converts the type; a negative number can still be a valid `Integer`. |
| "`getRequiredProperty` only searches `application.yml`." | It searches `Environment`, spanning multiple property sources. |
| "`containsProperty("app.client")` must be true when YAML has an `app.client:` branch." | A YAML branch may only contain leaf properties, with no scalar value at the parent key. |
| "Having a default in a file means a mistyped override will be ignored." | A mistyped higher-precedence override can cause conversion to fail. |
| "Any `getRequiredProperty` call guarantees startup fails immediately." | Depends on when the method is called; late calls fail late. |
| "`@Value` and `@ConfigurationProperties` work identically." | One injects placeholders; the other binds a configuration group with conversion/validation. |
| "Logging only the key name is enough to protect secrets." | You must still protect secret sources, access, and observability endpoints, and avoid logging secret **values**. |

## 18. Exercise: predict the results

Given `application.yml`:

~~~yaml
app:
  name: inventory
  feature:
    enabled: false
  workers: 0
  endpoint: ""
~~~

No other source overrides these keys.

### Question A

~~~java
environment.containsProperty("app.name");
environment.containsProperty("app.feature.enabled");
environment.containsProperty("app.workers");
environment.containsProperty("app.unknown");
~~~

The results are `true`, `true`, `true`, and `false`, respectively. Values `false` and `0` are still present properties.

### Question B

~~~java
environment.getRequiredProperty("app.endpoint");
~~~

The key has an empty-string value, so the requirement of **having the property** may still be satisfied. However, an empty endpoint is unusable; business logic needs to check `isBlank()` and reject it.

### Question C

~~~java
environment.getRequiredProperty("app.workers", Integer.class);
~~~

The result is `0`. If the application requires at least one worker, you must add `@Min(1)` or check `workers > 0` in Java.

### Question D

~~~java
environment.getRequiredProperty("app.unknown");
~~~

The call fails with `IllegalStateException` because the key is not found.

### Question E

Add the environment variable `APP_WORKERS=5` and run the application. Which value wins?

`getRequiredProperty("app.workers", Integer.class)` can return `5` because the OS environment source normally has higher precedence than Config Data in files. `containsProperty("app.workers")` still returns `true`; it does **not** tell you which source the key came from.

## 19. Key takeaways

1. `containsProperty(key)` checks whether a key has a resolvable value in `Environment`; do not use it to infer that a boolean flag is enabled.
2. `getRequiredProperty(key)` retrieves a **required** configuration value and throws `IllegalStateException` when not found.
3. `getRequiredProperty(key, Type.class)` also performs type conversion; a mistyped property and a missing property are different problems.
4. **Present does not equal valid**: always check empty strings, URLs, numeric bounds, security conditions, and required business rules.
5. Read and verify required configuration **during application initialization**, rather than waiting for the first request; for configuration groups, consider `@ConfigurationProperties` + Bean Validation.
6. Both methods use the **effective configuration** after `Environment` evaluates source precedence; they are neither origin-tracing tools nor guarantees that secrets are protected.

### References

- Spring Framework Javadoc — `PropertyResolver`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertyResolver.html
- Spring Framework Reference — Environment Abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties