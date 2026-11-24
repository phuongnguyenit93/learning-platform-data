# Unread Properties, Binding Errors, or Wrong Profile

A Spring Boot application can start successfully yet run with the wrong configuration: the server listens on the wrong port, a client uses the default timeout, a bean is not created, or a production service uses an implementation meant for development. These issues usually fall into three groups:

1. **Unread property:** the key is missing from `Environment`, the configuration file is not loaded, the key name is wrong, or another source overrides the intended value.
2. **Binding error:** the property is present in `Environment` but is not converted into the Java object as expected due to the wrong prefix, data type, nested/list/map structure, bean registration, or validation.
3. **Wrong profile:** the profile is not activated, the `application-{profile}` file is not loaded, the `@Profile` condition does not match, or multiple profiles are active at once and cause the wrong bean to be chosen.

These three groups are related but not identical. **The existence of a property does not guarantee it is bound into an object; a bound object does not guarantee the bean creation condition matches; declaring a profile in a file does not guarantee that profile is actually active.**

This lesson guides you through tracing the root cause from configuration sources to runtime behavior, reading binding/profile errors, and verifying results with tests.

## 1. Configuration flow from source to bean

Picture the processing flow:

```text
application.yml / environment / command line / system properties
                         │
                         ▼
                 Spring Environment
                 PropertySources
                         │
              ┌──────────┴───────────┐
              │                      │
              ▼                      ▼
       @Value placeholder     @ConfigurationProperties
              │                      │
              ▼                      ▼
       Field/constructor       Binder type conversion
              │                      │
              └──────────┬───────────┘
                         ▼
               Configuration / Bean
                         │
                         ▼
              Conditions and dependencies
                         │
                         ▼
                Application behavior
```

If the result is wrong, identify the failing layer:

- Key missing in `Environment`: investigate config data, key name, profile, import, and property sources.
- Key exists but field is wrong: investigate binding, conversion, prefix, and object registration.
- Field is right but bean is missing: investigate `@Profile`, `@Conditional...`, component scanning, and dependencies.
- Bean is right but behavior is wrong: investigate consumers, default logic, cache, runtime state, or business code.

Avoid changing multiple properties at once before knowing which layer the error is in.

## 2. Distinguishing three concepts

| Concept | Question | Inspection tool |
|---|---|---|
| Property resolution | Which key does Spring read and what value does it resolve? | `Environment`, Actuator `env` |
| Property binding | Which Java object is the value converted into, and into what type? | `@ConfigurationProperties`, `configprops`, binding tests |
| Profile/condition evaluation | Which configuration or bean is registered? | Active profiles, `@Profile`, condition report, `beans` |

Example:

```yaml
app:
  client:
    timeout: 5s
```

`Environment` can resolve `app.client.timeout` to the string `5s`. The binder can convert that value into a five-second `Duration`. However, if the `ClientProperties` class is not registered, no object automatically appears just because the key exists.

Similarly, `@Profile("prod")` only applies when the `prod` profile is active. Having an `application-prod.yml` file in the project does not automatically activate that profile.

## 3. Unread property: check the key name

A common cause is that **the property name does not match the name the code reads**.

YAML:

```yaml
app:
  client:
    read-timeout: 5s
```

Code:

```java
@Value("${app.client.timeout}")
private Duration timeout;
```

The two keys are different:

- YAML declares `app.client.read-timeout`.
- Code requests `app.client.timeout`.

Spring does not automatically guess that `read-timeout` and `timeout` are the same property.

Compare keys segment by segment, including dots, hyphens, plurals, and prefixes. Even a minor typo is enough to prevent a property from being found.

**How to handle:** locate where the property is declared and where it is used; compare exact canonical keys before inspecting more complex layers.

## 4. Inspecting properties with Environment

`Environment` is the direct API to inspect what Spring resolves at runtime.

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationInspector {

    private final Environment environment;

    public ConfigurationInspector(Environment environment) {
        this.environment = environment;
    }

    public void inspect() {
        String timeout =
                environment.getProperty("app.client.timeout");

        boolean present =
                environment.containsProperty("app.client.timeout");

        System.out.println("timeout present: " + present);
        System.out.println("timeout value: " + timeout);
    }
}
```

Useful APIs:

| API | Meaning |
|---|---|
| `getProperty("key")` | Gets the resolved value as a String |
| `getProperty("key", Type.class)` | Gets and converts to the requested type if an appropriate conversion exists |
| `containsProperty("key")` | Checks whether the key is found |
| `getActiveProfiles()` | List of explicitly active profiles |
| `getDefaultProfiles()` | List of default profiles |

Conversion example:

```java
Duration timeout = environment.getProperty(
        "app.client.timeout",
        Duration.class
);
```

Use this approach in tests or diagnostic code. Do not create a public endpoint to print the entire `Environment` because it can expose secrets.

## 5. Properties can come from multiple sources

Spring Boot does not read only `application.yml`. Runtime configuration can come from:

- `application.properties` or `application.yml`.
- Profile-specific files such as `application-prod.yml`.
- Operating system/container environment variables.
- Java system properties (`-Dname=value`).
- Command-line arguments (`--name=value`).
- Config data imports or external config locations.
- Test properties, dynamic properties, and custom property sources.

File example:

```yaml
# application.yml
app:
  client:
    timeout: 10s
```

Environment variable:

```text
APP_CLIENT_TIMEOUT=5s
```

Command line:

```bash
java -jar app.jar --app.client.timeout=2s
```

In typical Spring Boot configuration, command-line properties can override values from environment variables and config files. Therefore, YAML saying `10s` does not guarantee runtime definitely uses `10s`.

## 6. Property precedence: which source wins?

Spring Boot aggregates multiple sources in precedence order. Common sources:

| Source | Example | Role |
|---|---|---|
| Default properties | `SpringApplication.setDefaultProperties(...)` | Fallback values |
| Config data | `application.yml`, profile-specific files, imports | Packaged/external configuration |
| OS environment | `APP_CLIENT_TIMEOUT` | Deployment configuration |
| JVM system property | `-Dapp.client.timeout=3s` | Process configuration |
| Command-line property | `--app.client.timeout=2s` | Launch-time override |
| Test-specific property | `@SpringBootTest(properties=...)` | Override in test context |

These are illustrative sources, not an exhaustive list or absolute ordering for every case. Spring Boot has detailed precedence rules; test properties, dynamic properties, servlet sources, and custom sources can also participate.

When facing an unexpected override:

1. Identify the canonical key.
2. Check the effective value in `Environment`.
3. Identify the property source providing the value.
4. Find where deployment/IDE/build tool sets the same key.
5. Only fix the source responsible for providing that value.

Do not edit YAML if the command line or environment variables still override it.

## 7. Using Actuator env to find property sources

If the application has Spring Boot Actuator and the endpoint is appropriately exposed/secured, the `env` endpoint helps inspect Spring Environment and property sources.

```bash
curl http://localhost:8080/actuator/env/app.client.timeout
```

The actual path may differ if the management port or base path has been changed.

The endpoint can provide:

- Property key.
- Relevant property sources.
- Sanitized value.
- Origin metadata such as file/line if supported by the source.

Sensitive values may be masked. `******` is the sanitized representation, not the actual property value.

If the endpoint is not enabled/exposed yet, use `Environment` in tests or diagnostic code. Do not publicly expose all Actuator endpoints just to investigate a single property.

## 8. Property file not loaded

Spring Boot typically searches for configuration in default locations, including config data on the classpath and several external filesystem locations such as the working directory or the `config` directory.

Common filenames:

```text
application.properties
application.yml
application.yaml
application-dev.properties
application-dev.yml
application-prod.yml
```

If a file sits outside searched locations or is not imported, its contents may not participate in Environment.

For example, the file actually resides at:

```text
./deployment/config/application.yml
```

but the application is not configured to search that directory. The file existing on disk does not prove Spring Boot read it.

Check:

1. Is the file on the classpath or in a declared config location?
2. Is the file packaged into the artifact?
3. Is the working directory correct?
4. Are the filename and extension correct?
5. For a profile-specific file, is the corresponding profile active?
6. Does the file have syntax or encoding errors?
7. Is a config import missing or marked optional?

## 9. spring.config.location and spring.config.additional-location

These two properties are easily confused:

- `spring.config.location`: specifies configuration locations and can **replace** the default search locations.
- `spring.config.additional-location`: adds search locations alongside the default locations.

Example:

```bash
java -jar app.jar --spring.config.additional-location=file:./deployment/config/
```

The application continues using the default locations and adds the `deployment/config` directory.

Whereas:

```bash
java -jar app.jar --spring.config.location=file:./deployment/config/
```

can replace the default locations with the specified location, causing `application.yml` on the classpath to no longer be loaded as you expected.

This is a common cause when an application "reads some properties but loses default properties."

`spring.config.name`, `spring.config.location`, and `spring.config.additional-location` need to be known very early when Boot prepares config data. Pass them via environment, system properties, or command line; do not put them inside the very configuration file you expect them to help Spring find.

## 10. Using spring.config.import

Spring Boot supports importing additional config data from other sources.

```yaml
spring:
  config:
    import: "optional:file:./config/extra.properties"
```

`optional:` allows the application to continue when the import source does not exist, per the Config Data contract. If `optional:` is omitted and a required location does not exist, startup may fail while loading config.

YAML import example:

```yaml
spring:
  config:
    import: "optional:file:./config/extra.yml"
```

When a property does not appear, check the import path, `file:` prefix, file existence/permissions, optional marker, and whether another source overrides the property afterward.

Do not confuse `spring.config.import` with Java `@Import`: one loads **config data**, while the other registers configurations/beans into the Spring context.

## 11. YAML syntax errors and indentation structure

YAML depends on indentation. Valid example:

```yaml
app:
  client:
    timeout: 5s
    max-attempts: 3
```

Structurally broken example:

```yaml
app:
client:
  timeout: 5s
    max-attempts: 3
```

The YAML parser may fail immediately at startup, or a structure may be valid YAML yet not produce the key you expect.

Key points to watch:

- Use spaces consistently; do not mix tabs.
- Indentation expresses hierarchy.
- `:` and `#` carry syntactic meaning in certain positions.
- Values with special characters should be quoted when needed.
- Duplicate keys should be avoided because they can cause confusing behavior depending on the parser.
- Lists must use `-` at the proper level.
- Do not mistakenly place a sibling key as a nested property.

List example:

```yaml
app:
  allowed-origins:
    - https://dev.example.invalid
    - https://test.example.invalid
```

If the structure is wrong, inspect the full startup error and identify the file/line mentioned instead of just renaming the property.

## 12. application.properties and application.yml

Both formats can express the same configuration.

Properties:

```properties
app.client.timeout=5s
app.client.max-attempts=3
```

YAML:

```yaml
app:
  client:
    timeout: 5s
    max-attempts: 3
```

Avoid declaring the same key in both formats without a reason. If both exist, the effective value also depends on property source ordering and config data locations.

In YAML, hierarchy is easier to read, though wrong indentation can alter the key. In properties, hierarchy is represented with dots, making it easy to cross-check with keys in code.

When migrating between formats, verify canonical properties after parsing, not merely by comparing textual appearance.

## 13. Relaxed binding and environment variable names

Spring Boot supports relaxed binding for `@ConfigurationProperties`, allowing multiple equivalent spellings under binding rules.

Canonical property example:

```properties
app.client.max-retries=4
```

Environment variable name under common conversion rules:

1. Replace dots `.` with underscores `_`.
2. Remove hyphens `-`.
3. Convert to uppercase.

Result:

```text
APP_CLIENT_MAXRETRIES=4
```

This is easy to get wrong: it is not necessarily `APP_CLIENT_MAX_RETRIES`.

Other examples:

| Canonical property | Environment variable |
|---|---|
| `server.port` | `SERVER_PORT` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `app.client.base-url` | `APP_CLIENT_BASEURL` |
| `app.client.max-retries` | `APP_CLIENT_MAXRETRIES` |
| `integration.payment.api-key` | `INTEGRATION_PAYMENT_APIKEY` |

With `@Value`, do not rely on the full relaxed binding capabilities of `@ConfigurationProperties`; placeholders should point to an appropriate property name. When binding multiple fields, prefer `@ConfigurationProperties`.

## 14. Distinguishing @Value and @ConfigurationProperties

`@Value` is suitable when injecting a few individual properties:

```java
@Component
public class GreetingService {

    private final String prefix;

    public GreetingService(
            @Value("${app.greeting.prefix:Hello}") String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + " " + name;
    }
}
```

`@ConfigurationProperties` is suitable for a structured group of configuration under a prefix:

```java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration timeout,
        int maxRetries
) {
}
```

| Criterion | `@Value` | `@ConfigurationProperties` |
|---|---|---|
| Single value | Very suitable | Can be used, though often excessive |
| Configuration group | Scattered individual annotations | One structured object |
| Relaxed binding | More limited | Supported |
| Nested object/list/map | Inconvenient | Supports binding |
| Type conversion | Has conversion | Binder supports many types |
| Object-level validation | Not centralized | Can use `@Validated` |
| IDE metadata | Limited | Can generate configuration metadata |

Placeholder with default example:

```java
@Value("${app.client.timeout:3s}")
private Duration timeout;
```

If the property is missing, the default `3s` is used. Without a default and without resolving the placeholder, bean creation can fail with an unresolved placeholder error.

## 15. @ConfigurationProperties needs to be registered

A class annotated solely with `@ConfigurationProperties` does not automatically become a bean in every case.

It can be registered via scanning:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Or explicitly enabled:

```java
@Configuration
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {
}
```

If registration is missing, you may encounter the error:

```text
No qualifying bean of type 'ClientProperties' available
```

This is not necessarily a property file error. The key may already exist in Environment while the target bean has not been registered yet.

If the properties class lies outside the scanned package, check the main application package and the scope of `@ConfigurationPropertiesScan`.

## 16. Binding into a record or constructor-bound properties

Example using a Java record:

```java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration timeout,
        int maxRetries
) {
}
```

Register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

YAML:

```yaml
app:
  client:
    base-url: https://catalog.example.invalid
    timeout: 5s
    max-retries: 3
```

The Spring Boot binder maps `base-url` to `baseUrl`, `timeout` to `Duration`, and `max-retries` to `maxRetries`.

With constructor binding, constructor parameters need to be bound according to corresponding rules. Missing required values or wrong types can cause properties bean creation errors, depending on the type, defaults, and validation configuration.

In modern Spring Boot versions, a record with a canonical constructor typically supports constructor binding without needing an extra dedicated annotation. For classes with multiple constructors or different versions, follow the exact contract of the Boot version in use.

## 17. Binding into a mutable JavaBean

Another option is a class with a no-args constructor and setters:

```java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    private URI baseUrl;
    private Duration timeout;
    private int maxRetries;

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
```

This binding style requires the class to be registered and to have appropriate accessors/setters.

If a field lacks a setter or constructor binding is not configured as intended, the binder may fail to update the value the way you think.

When debugging, check bean registration, prefix, field names, setters/constructors, conversion, and default values.

## 18. Type conversion: String is not always the final type

The Spring Boot Binder can convert text properties into common Java types.

Example:

```yaml
app:
  client:
    endpoint: https://catalog.example.invalid
    timeout: 5s
    max-response-size: 10MB
    enabled: true
```

Properties:

```java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI endpoint,
        Duration timeout,
        DataSize maxResponseSize,
        boolean enabled
) {
}
```

Common types:

| Java type | Configuration example |
|---|---|
| `int`, `long` | `3`, `5000` |
| `boolean` | `true`, `false` |
| `Duration` | `5s`, `500ms`, `2m` |
| `DataSize` | `10MB`, `512KB` |
| `URI`/`URL` | `https://service.example.invalid` |
| `List<String>` | YAML sequence or indexed properties |
| `Map<String, String>` | YAML mapping |
| `enum` | Enum name matching conversion rules |

Use explicit units for `Duration` and `DataSize`, avoiding making readers guess. Default units can depend on annotations/configuration; explicit units prevent misunderstandings.

## 19. Duration and DataSize wrong units

Example:

```yaml
app:
  client:
    timeout: 500ms
    max-response-size: 10MB
```

Avoid ambiguous values:

```yaml
app:
  client:
    timeout: 500
    max-response-size: 10
```

Values without a unit may be interpreted using Spring Boot's default unit or the `@DurationUnit`/`@DataSizeUnit` annotation on the field/constructor parameter. Do not assume `500` means 500 seconds or `10` means 10 megabytes.

Example specifying the default unit for Duration:

```java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration timeout = Duration.ofSeconds(3);

    // Getter/setter.
}
```

If precision matters, use suffixes in config and verify typed values in tests.

## 20. Data type conversion errors

Property example:

```properties
app.client.max-retries=three
```

but the Java field is:

```java
private int maxRetries;
```

The binder cannot convert the string `three` into an integer. Startup can fail with a binding/conversion error, typically wrapped in a higher-level exception such as `ConfigurationPropertiesBindException` or `BeanCreationException`.

Similar causes:

- `timeout=soon` while the field is `Duration`.
- Invalid URL for type `URI`.
- Invalid enum value.
- Boolean with a string not accepted by the converter.
- Malformed list/map structure.
- Property with a placeholder referencing a nonexistent key.

Read the **root cause** in the exception chain; do not stop at the first line `Failed to bind properties`.

## 21. Validation: value binds but is still invalid

A value can convert types successfully yet violate business requirements.

```yaml
app:
  client:
    timeout: 0s
    max-retries: -2
```

Both values can parse into `Duration` and `int`, but the system may require a positive timeout and non-negative retries.

Validation can be added:

```java
@ConfigurationProperties(prefix = "app.client")
@Validated
public record ClientProperties(
        @NotNull URI baseUrl,
        @NotNull @Positive Duration timeout,
        @Min(0) int maxRetries
) {
}
```

The example requires Jakarta Bean Validation imports and a validation provider/dependency matching the Spring Boot version. Whether `@Positive` works on `Duration` depends on provider support; if the provider does not support that type, use a custom validator or check inside an appropriate validation method.

For nested properties, use `@Valid` when you want cascading validation.

Binding and validation are two distinct steps:

- Binding checks whether data can be transferred/converted into the object.
- Validation checks whether the object satisfies constraints.

## 22. Misspelled property without an error

A hard-to-spot case: a key in the file has a typo, yet the application still runs and uses defaults.

```yaml
app:
  client:
    max-retyrs: 5
```

While Java properties expect `maxRetries`.

Depending on binder configuration, unknown fields may be ignored by default. Consequently, not every misspelled key fails startup.

Strict handling for unknown fields can be requested:

```java
@ConfigurationProperties(
    prefix = "app.client",
    ignoreUnknownFields = false
)
public class ClientProperties {
    // Fields and accessors.
}
```

This helps detect unbound properties within the scope of that object. However, before enabling it, ensure config files do not intentionally contain extension keys not managed by the current class.

## 23. Nested properties

YAML:

```yaml
app:
  client:
    connection:
      connect-timeout: 2s
      read-timeout: 5s
```

Java:

```java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        Connection connection
) {
    public record Connection(
            Duration connectTimeout,
            Duration readTimeout
    ) {
    }
}
```

The binder maps `connection.connect-timeout` to `connection.connectTimeout`.

If the nested object is null or missing fields, check YAML indentation, root prefix, nested property name, constructor binding, defaults, `@Valid`, and registration.

Do not confuse a nested object not being created with the YAML file not being read at all.

## 24. List binding and override

YAML:

```yaml
app:
  allowed-origins:
    - https://dev.example.invalid
    - https://test.example.invalid
```

Indexed properties:

```properties
app.allowed-origins[0]=https://dev.example.invalid
app.allowed-origins[1]=https://test.example.invalid
```

Java:

```java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<String> allowedOrigins
) {
}
```

When the same list is supplied from multiple property sources, **a list from a higher-precedence source usually replaces the entire list**, rather than appending elements from lower-precedence sources.

For example, the default file has two origins, while the production profile declares only one origin; the effective list may contain only the origin from the production source.

If you want to add elements, configure the complete effective list or design a dedicated merging mechanism. Do not assume lists merge like maps.

## 25. Map binding and special keys

YAML:

```yaml
app:
  client:
    headers:
      X-Region: ap-southeast-1
      X-Mode: safe
```

Java:

```java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        Map<String, String> headers
) {
}
```

If a map key contains special characters such as `/` or dots or characters that must be preserved verbatim, bracket notation may be required when declaring the property key.

Properties example:

```properties
app.client.labels.[/v1/orders]=orders-api
```

With YAML, you can quote the bracketed key:

```yaml
app:
  client:
    labels:
      "[/v1/orders]": orders-api
```

If keys disappear or get transformed, inspect how the parser/binder normalizes keys and use bracket notation to preserve characters.

## 26. Placeholder ${...} referencing another property

A property can reference another property:

```properties
app.client.host=localhost
app.client.base-url=https://${app.client.host}:8443
```

Or YAML:

```yaml
app:
  client:
    host: localhost
    base-url: "https://${app.client.host}:8443"
```

If the referenced key does not exist, the placeholder may fail to resolve and cause bean/configuration failure, unless an appropriate default is provided:

```properties
app.client.timeout=${APP_TIMEOUT:5s}
```

In the last example, `5s` is the fallback if property `APP_TIMEOUT` is not found. Distinguish placeholder defaults from default values in Java constructors/fields.

When a property exists in the file but the bean fails, check the placeholder chain. The outer key may exist while a key it references is missing.

## 27. What is a Profile in Spring?

A profile is a logical name for a set of configurations or bean conditions. Common names:

```text
dev
test
staging
prod
local
cloud
```

Profiles can affect:

- `application-{profile}.yml` files.
- Beans annotated with `@Profile`.
- Config documents with `spring.config.activate.on-profile`.
- Certain application auto-configurations/conditions.

Profile names have no special built-in meaning beyond conventions and the configuration you define. Spring does not by default treat `dev`, `test`, and `prod` as mutually exclusive; multiple profiles can be active simultaneously.

## 28. Activating a profile properly

It can be activated via command line:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Environment variable:

```text
SPRING_PROFILES_ACTIVE=prod
```

Or in base configuration `application.yml`:

```yaml
spring:
  profiles:
    active: prod
```

In an IDE, `--spring.profiles.active=dev` is an application argument; `SPRING_PROFILES_ACTIVE=dev` is an environment variable.

Do not confuse:

- `--spring.profiles.active=prod`: application argument for Spring Boot.
- `-Dspring.profiles.active=prod`: JVM system property if passed to the application JVM.
- `-Pprod`: Maven build profile, not automatically a Spring profile.
- Gradle project property `-P...`: build configuration, not automatically a runtime profile.

## 29. application-prod.yml does not automatically activate prod

Suppose the project has:

```text
application.yml
application-dev.yml
application-prod.yml
```

Spring Boot only loads profile-specific configuration when the corresponding profile is activated.

If you run:

```bash
java -jar app.jar
```

you cannot assume `application-prod.yml` is loaded just because it exists.

You need:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Or configure the active profile through another valid source.

If the app is using `dev` when you expect `prod`, inspect the startup log and `Environment.getActiveProfiles()` before editing `application-prod.yml`.

## 30. Do not place spring.profiles.active inside a profile-specific file

A common mistake is writing:

```yaml
# application-prod.yml
spring:
  profiles:
    active: prod
```

`spring.profiles.active` cannot be used to activate profiles from a document that is already profile-specific or conditioned by `spring.config.activate.on-profile`.

Declare active profiles in a valid startup configuration source, such as command line, environment variables, JVM system properties, or a non-profile-specific base configuration document.

`application-prod.yml` should hold configuration meant for the `prod` profile, not decide to enable that profile itself.

## 31. Default profile and active profiles

When no explicit active profile is set, Spring uses **default profiles**. The default name is typically `default`.

You can change the default profile:

```properties
spring.profiles.default=local
```

When there is no explicit active profile, `local` can be the effective default profile.

Distinguish:

```java
@Profile("default")
```

from:

```java
@Profile("!prod")
```

`default` checks the default profile name; `!prod` is a negation expression, true when `prod` is not active.

When the active profile is `dev`, `!prod` still matches, whereas `default` normally does not match because default profiles are only used when no active profile is explicitly set.

If a bean is intended only for local/test, avoid using `!prod` without considering new profiles that might appear in the future.

## 32. Multiple profiles can be active simultaneously

Example:

```bash
java -jar app.jar --spring.profiles.active=prod,cloud,metrics
```

The active profile set contains three names. Conditions are evaluated against this set.

```java
@Profile("prod & cloud")
```

matches because both `prod` and `cloud` are active.

Whereas:

```java
@Profile("dev | test")
```

does not match if both `dev` and `test` are absent.

A profile array:

```java
@Profile({"dev", "test"})
```

is an OR across expressions, not an AND.

If you need both:

```java
@Profile("dev & cloud")
```

When mixing AND and OR, group with parentheses:

```java
@Profile("(dev | staging) & cloud")
```

## 33. Profile groups

Profile groups allow activating a group of profiles via a single representative name.

```yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - observability
```

When running:

```bash
java -jar app.jar --spring.profiles.active=production
```

Spring Boot activates the group profile along with its member profiles per configuration.

This is useful when production needs a consistent set of features. Check `Environment.getActiveProfiles()` to confirm the actual list, especially when multiple profiles or groups are combined.

Do not declare profile groups inside profile-specific documents or documents activated by `spring.config.activate.on-profile`; profile-controlling properties belong in valid configuration documents per Boot rules.

## 34. Profile-specific config documents

Besides `application-prod.yml` files, Spring Boot supports multiple YAML documents in the same file, separated by `---`.

```yaml
app:
  banner: default

---
spring:
  config:
    activate:
      on-profile: prod

app:
  banner: production
```

The second document is only activated when the `prod` profile is active.

Expressions can be used:

```yaml
---
spring:
  config:
    activate:
      on-profile: "(staging | prod) & cloud"

app:
  client:
    remote-mode: true
```

Do not confuse `spring.config.activate.on-profile` with `spring.profiles.active`:

- `spring.profiles.active` selects the active profile set.
- `spring.config.activate.on-profile` conditions the loading of a config document.

## 35. Wrong profile due to spelling or source override

Suppose deployment sets:

```text
SPRING_PROFILE=prod
```

but the Spring Boot property is `spring.profiles.active`.

The standard environment variable name under conversion rules is:

```text
SPRING_PROFILES_ACTIVE=prod
```

A similarly named variable does not mean Spring will automatically understand it.

Beyond spelling, profiles can be overridden by command-line arguments, JVM system properties, other environment variables, test configurations, or custom property sources.

Check the effective profiles with:

```java
Environment environment = ...;

System.out.println(
    Arrays.toString(environment.getActiveProfiles())
);
```

In real code, inject `Environment` rather than pulling a global variable manually.

## 36. Profile conditions and beans not created

Example:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @Profile("prod")
    PaymentGateway remoteGateway() {
        return new RemotePaymentGateway();
    }

    @Bean
    @Profile("!prod")
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }
}
```

Without `prod`, the local bean is registered. With `prod`, the remote bean is registered.

However, if remote also has:

```java
@Bean
@Profile("prod")
@ConditionalOnProperty(
    prefix = "payment.remote",
    name = "enabled",
    havingValue = "true"
)
PaymentGateway remoteGateway() {
    return new RemotePaymentGateway();
}
```

then both conditions must be satisfied.

In `prod` when `payment.remote.enabled=false`, local is excluded and remote is also excluded. The result is no `PaymentGateway`.

When encountering `NoSuchBeanDefinitionException`, inspect the entire condition chain rather than looking only at the profile.

## 37. Reading the condition evaluation report

When the application starts successfully and Actuator is safely enabled/exposed, the `conditions` endpoint helps inspect conditional configuration:

```bash
curl http://localhost:8080/actuator/conditions
```

When startup fails before management endpoints are ready, use the debug flag:

```bash
java -jar app.jar --debug
```

Or with Gradle:

```bash
./gradlew bootRun --args="--debug"
```

Or Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--debug"
```

`--debug` makes Spring Boot print the condition evaluation report for auto-configurations. It does not automatically enable TRACE for all loggers and does not replace reading the root exception.

A negative match is not necessarily an error: Boot ships many auto-configurations for stacks the application does not use.

## 38. Property present in env but missing in configprops

`env` and `configprops` answer two different questions.

- `env`: does the key exist in Environment, and what value/source is effective?
- `configprops`: which `@ConfigurationProperties` objects have been bound?

Suppose the key is in YAML:

```yaml
app:
  client:
    timeout: 5s
```

Yet there is no properties bean because the class is not registered. In that case, `env` can see the key, while `configprops` has no corresponding object.

Check:

1. Does the class have `@ConfigurationProperties(prefix="app.client")`?
2. Is `@ConfigurationPropertiesScan` present?
3. Or was `@EnableConfigurationProperties(ClientProperties.class)` used?
4. Is the class within the scan scope?
5. Do profiles/conditions exclude the bean?

Do not conclude that YAML is unread merely because `configprops` lacks a class.

## 39. configprops has the object but the value is wrong

If the properties bean is present yet the field is wrong, compare:

1. `env`: effective value of the key.
2. `configprops`: bound typed value.
3. Java class: field name, prefix, constructor/setter, defaults.
4. Validation: whether constraints are applied.

For example, `env` shows `app.client.timeout=5s`, yet the object still has `Duration.ZERO`. The object may be instantiated another way, the bean may not use the prefix you think, the field may not participate in binding, a constructor/default may be used unexpectedly, or you may be observing the wrong instance/context.

Identify the exact bean injected into the consumer; do not merely inspect an object with the same class name.

## 40. Unresolved placeholder errors

Example:

```properties
app.client.base-url=${APP_CLIENT_BASE_URL}
```

If `APP_CLIENT_BASE_URL` does not exist and has no default, the placeholder may fail to resolve and break the bean/configuration.

Add a default if that is a valid policy:

```properties
app.client.base-url=${APP_CLIENT_BASE_URL:https://localhost:8443}
```

However, do not set a fake default for a production endpoint if a missing URL ought to fail fast. Defaults should only be used when the fallback value is genuinely safe and meaningful.

When you see `Could not resolve placeholder`, look for the key inside `${...}` in the exception; that is usually the missing property, not necessarily the outer property you see in the file.

## 41. Common exceptions and their meanings

| Exception/message | Possible meaning | Next investigation |
|---|---|---|
| `Could not resolve placeholder ...` | Placeholder cannot find key and has no fallback | Property sources, spelling, imports |
| `ConfigurationPropertiesBindException` | Cannot bind properties bean | Prefix, fields, constructor, types |
| `BindException` | Binder encountered an error during binding | Root cause, property path |
| `ConversionFailedException` | Cannot convert type | Format, converter, target type |
| `BeanCreationException` | Bean creation failed; may wrap binding error | Inspect nested cause |
| `NoSuchBeanDefinitionException` | Cannot find dependency bean | Component scan, profile, conditions |
| `NoUniqueBeanDefinitionException` | Multiple candidates of the same type | `@Primary`, `@Qualifier`, conditions |
| `Failed to bind properties under ...` | A prefix/field cannot bind | Check property name and exception chain |
| YAML parse error | Invalid file structure | File/line/indentation |
| Profile-specific file has no effect | Profile not active or file not found | Active profiles, config locations |

Do not copy only the outermost exception. Use the stack trace to locate the deepest meaningful `Caused by`; that is usually the concrete cause such as parsing, conversion, or missing dependency.

## 42. Distinguishing startup failure and runtime wrong value

The two situations call for different approaches.

**Startup failure:**

- YAML parse error.
- Required placeholder unresolved.
- Type conversion failure.
- Validation failure.
- Required bean missing.
- Two beans of the same type causing ambiguous injection.

Use startup logs, stack traces, `--debug`, and test contexts.

**Application starts but values are wrong:**

- Another property source overrides it.
- Profile differs from expected.
- Java default masks an unbound property.
- A list from a profile-specific source replaces the whole list.
- Bean is created, yet consumer uses a different bean.
- Configuration is read at startup and stored in state.

Use `Environment`, `configprops`, `beans`, instance identity, and integration tests.

## 43. Diagnostic workflow: property not read

Scenario: a service always uses the default timeout even though the YAML file has a different value.

1. **Identify the key the code reads.** For example `app.client.timeout`.
2. **Locate the key in configuration files.** Check spelling, hierarchy, and indentation.
3. **Confirm the file is loaded.** Check name, location, import, profile.
4. **Read the effective value from Environment.** If null, the key is unresolved; if different from expected, there is an override.
5. **Find the winning property source.** Environment variable, command line, system property, test override.
6. **Check object binding.** If code uses `@ConfigurationProperties`, inspect the bean and typed fields.
7. **Check the consumer.** Ensure the service uses the right properties bean/field.
8. **Write a reproduction test.** Set profile and properties explicitly, assert the final value.

Do not change both config files and code at the same time before identifying the failing layer.

## 44. Diagnostic workflow: binding error

Scenario: startup reports `Failed to bind properties under 'app.client'`.

1. Find the exact prefix in the exception.
2. Identify the offending property path.
3. Check the raw value from Environment if available.
4. Check the Java target type.
5. Check formatting for `Duration`, `DataSize`, enum, URI, number, boolean.
6. Check nested structure/list/map and YAML indentation.
7. Check `@ConfigurationProperties` registration.
8. Check constructor/setter/record parameters.
9. Check Bean Validation and nested `@Valid`.
10. If the value binds yet is invalid for business rules, add validation and tests.

If the exception includes an `origin`, use that file/line to locate the specific configuration source.

## 45. Diagnostic workflow: wrong profile

Scenario: the application uses the `dev` bean even when deployed to production.

1. Read active profiles from the startup log or `Environment`.
2. Check whether deployment passes `SPRING_PROFILES_ACTIVE` or `--spring.profiles.active` properly.
3. Check whether command-line/JVM/environment sources override each other.
4. Check whether `application-prod.yml` has the right name and location.
5. Check whether `spring.profiles.active` was mistakenly placed inside a profile-specific document.
6. Check whether multiple profiles are active simultaneously.
7. Read `@Profile` expressions on classes and `@Bean` methods.
8. Check property conditions combined with profiles.
9. Use `beans`/context tests to confirm the actual implementation.
10. Write tests for the exact deployment profile set.

Do not look solely at environment variables in the pipeline; confirm the value **actually entered the instance's Spring Environment**.

## 46. Testing property resolution and binding

A narrow test using `ApplicationContextRunner`:

```java
class ClientPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(ClientPropertiesConfiguration.class);

    @Test
    void bindsTimeoutAndRetryCount() {
        runner
            .withPropertyValues(
                "app.client.timeout=5s",
                "app.client.max-retries=3"
            )
            .run(context -> {
                assertThat(context)
                        .hasSingleBean(ClientProperties.class);

                ClientProperties properties =
                        context.getBean(ClientProperties.class);

                assertThat(properties.timeout())
                        .isEqualTo(Duration.ofSeconds(5));

                assertThat(properties.maxRetries())
                        .isEqualTo(3);
            });
    }
}
```

This test assumes `ClientPropertiesConfiguration` registers `ClientProperties` with `@EnableConfigurationProperties`.

It verifies the binder and typed values without starting the entire web application. Add tests for missing properties, malformed values, and overrides to guard error-prone cases.

## 47. Testing profile and implementation selection

Example:

```java
@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "integration.notifications.enabled=true"
)
@ActiveProfiles("prod")
class ProductionNotificationSelectionTest {

    @Autowired
    ApplicationContext context;

    @Test
    void selectsRemoteImplementation() {
        NotificationChannel channel =
                context.getBean(NotificationChannel.class);

        assertThat(channel)
                .isInstanceOf(RemoteNotificationChannel.class);

        assertThat(context.getBeansOfType(NotificationChannel.class))
                .hasSize(1);
    }
}
```

Tests must verify both the type and bean count if the contract requires exactly one implementation.

Additional tests should cover dev profile/missing property, prod true, prod false, prod missing, multiple active profiles, profile-specific YAML overrides, and missing beans causing the consumer to fail fast if that is the policy.

Do not mock the implementation whose selection is under test, as mocks can mask real conditions.

## 48. Actuator endpoints that aid investigation

If Actuator is installed and safely exposed, the following endpoints are helpful:

| Endpoint | Question |
|---|---|
| `/actuator/env` | What are the effective property key/source/value? |
| `/actuator/configprops` | How are `@ConfigurationProperties` beans bound? |
| `/actuator/conditions` | Did conditional configurations match or not? |
| `/actuator/beans` | Which beans actually exist in the context? |

A workflow:

```text
env
 │
 ├── Does the key exist?
 ├── Which source wins?
 └── Which profiles are active?
       │
       ▼
configprops
 │
 └── Is the typed bean bound correctly?
       │
       ▼
conditions
 │
 └── Do bean creation conditions match?
       │
       ▼
beans
   └── Which implementation is actually registered?
```

If the application fails to start, these HTTP endpoints may not be ready. In that case, use logs, `--debug`, and tests.

These endpoints can reveal property names, classes, packages, bean structures, and internal details. Keep sensitive values masked, restrict network and authorization, and do not expose them broadly just for debugging.

## 49. Common mistakes

| Symptom | Possible cause | How to fix |
|---|---|---|
| `Environment.getProperty(...)` returns null | Wrong key or config file not loaded | Check key, location, imports |
| YAML file has a value yet runtime differs | Higher-precedence property source overrides it | Identify the effective source |
| `@Value` uses default | Placeholder key missing or wrong | Check spelling and sources |
| `@ConfigurationProperties` bean missing | Properties class not scanned/enabled | Use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Binder reports Duration error | Value has invalid format | Use `5s`, `500ms` and check type |
| Property typo yet app still runs | Unknown fields ignored | Consider `ignoreUnknownFields=false` |
| Nested field is null | Wrong YAML hierarchy or constructor | Check indentation/prefix/binding model |
| List loses default elements | List in higher-precedence source replaces lower list | Declare the full effective list |
| Map key is altered | Special characters unescaped | Use bracket notation |
| `application-prod.yml` has no effect | `prod` profile not active or file not found | Confirm active profiles and config locations |
| `prod` profile not active | Env var/argument misspelled or overridden | Check `SPRING_PROFILES_ACTIVE` and Environment |
| `@Profile` does not match | Wrong expression or missing profile | Check the entire active set |
| Bean missing despite right profile | Another property condition does not match | Check conditions and properties |
| Two beans of the same type | Overlapping profile expressions | Use mutually exclusive conditions or `@Qualifier` |
| Startup fails on placeholder | Required placeholder unresolved | Supply key or valid default |
| Tests pass yet deployment fails | Test context differs from real config/runtime | Add integration tests and compare property sources |
| Actuator returns 404 | Endpoint not enabled/exposed or different path | Check exposure/base path |
| Actuator returns 401/403 | Security requires authentication/role | Use proper admin credentials; do not disable security |

## 50. Ordered investigation checklist

When encountering a property/profile issue, you can walk through these questions:

```text
[ ] Which key is the code reading?
[ ] Does the key exist in Environment?
[ ] Which file/source provides the effective value?
[ ] Is there a command-line, system property, or env var override?
[ ] Is the config file loaded from the right location/import?
[ ] Are YAML hierarchy and spelling correct?
[ ] Which profiles are active/default?
[ ] Is the profile-specific file named correctly?
[ ] Is the @ConfigurationProperties bean registered?
[ ] Do prefix, constructor, setter, and field names match?
[ ] Can the value convert to the Java type?
[ ] Does validation pass?
[ ] Do @Profile and @Conditional... match?
[ ] Does the consumer receive the right implementation?
[ ] Do tests simulate the runtime configuration accurately?
```

You do not have to run every step for a simple error. Use the checklist as a map so you do not overlook a related configuration layer.

## 51. Practice exercises

### Exercise A — Unread property

Create property `app.client.timeout=5s`, while code reads `app.client.read-timeout`. Use `Environment.containsProperty()` and `getProperty()` to identify which key exists. Fix one side and verify again.

### Exercise B — Overridden property

Set timeout `10s` in `application.yml`, then run:

```bash
java -jar app.jar --app.client.timeout=2s
```

Confirm the effective value and explain why editing YAML does not change the result while the command line still overrides it.

### Exercise C — Environment variable naming

Create property `app.client.max-retries`. Set an environment variable following relaxed binding rules and verify the binder receives it properly. Try a name with an extra underscore between `MAX` and `RETRIES` and observe the difference.

### Exercise D — Binding Duration

Bind `app.client.timeout=500ms` into `Duration`. Try `5s`, `500ms`, `soon`, and a missing value. Record which cases bind successfully and which fail.

### Exercise E — Unregistered properties bean

Create a `@ConfigurationProperties(prefix="app.client")` class without scanning/enabling it. Set the property in YAML and observe why the key can exist in Environment without a bean. Then register the class properly.

### Exercise F — Unknown property

Intentionally write `max-retyrs` instead of `max-retries`. Observe the default behavior, then try strict binding with `ignoreUnknownFields=false`. Record the trade-offs.

### Exercise G — Inactive profile

Create `application-dev.yml` and `application-prod.yml` with a differing property. Run the app without passing a profile, then with `--spring.profiles.active=prod`. Compare effective values.

### Exercise H — Multiple active profiles

Create a `@Profile("dev | test")` bean and a `@Profile("prod & cloud")` bean. Run with `dev,prod,cloud`. Determine which conditions match; explain why profile names are not mutually exclusive on their own.

### Exercise I — Profile placed in the wrong location

Put `spring.profiles.active=prod` inside `application-prod.yml`. Observe the error/behavior for your Boot version. Move the active profile to environment or command line and explain the difference.

### Exercise J — Placeholder chain

Set `app.client.url=${CLIENT_URL}` without providing `CLIENT_URL`. Observe the startup error. Try a valid default and discuss when fail-fast is better than fallback.

### Exercise K — List override

Declare two origins in `application.yml` and one origin in `application-prod.yml`. Activate `prod` and observe the effective list. Explain why you should not expect lists to concatenate automatically.

### Exercise L — End-to-end diagnosis

Create a scenario where production uses the local implementation due to a wrong profile or missing property flag. Investigate from Environment, configprops, conditions to beans. Write a report covering symptom, effective profile, property source, binding result, bean selection, root cause, and fix.

## 52. Key takeaways

1. **Property resolution, binding, and condition evaluation are three distinct steps.**
2. `Environment` reports effective properties; the `@ConfigurationProperties` binder converts properties into typed objects.
3. Having a key in a YAML file does not prove the file was loaded or the value was not overridden.
4. Property sources have precedence; command line, system properties, and environment variables can make runtime values differ from configuration files.
5. `spring.config.location` can replace default locations; `spring.config.additional-location` adds locations.
6. `spring.config.import` loads additional config data; `optional:` controls behavior when the source does not exist.
7. YAML indentation, spelling, nested structure, lists/maps, and quoting can all cause keys to parse differently than expected.
8. The environment variable for canonical property `app.client.max-retries` is typically `APP_CLIENT_MAXRETRIES`.
9. `@Value` suits a few single properties; `@ConfigurationProperties` suits structured configuration groups and relaxed binding.
10. A `@ConfigurationProperties` class must be registered via scanning, enabling, or an appropriate bean mechanism.
11. Binding failure differs from validation failure: successful type conversion does not guarantee business validity.
12. Unknown fields may be ignored by default; strict handling helps catch typos when appropriate.
13. `application-prod.yml` does not automatically activate the `prod` profile.
14. `spring.profiles.active` must be declared in a valid configuration source, not inside a profile-specific document.
15. Multiple profiles can be active simultaneously; `@Profile` expressions must be evaluated across the entire active profile set.
16. `@Profile({"dev","test"})` is OR; `@Profile("dev & test")` is AND.
17. `spring.config.activate.on-profile` conditions a config document; it does not replace `spring.profiles.active`.
18. When a bean is missing, check profile and property conditions together with component scanning, not just a single annotation.
19. When startup fails, read nested causes and use `--debug`; Actuator HTTP endpoints may not be ready yet.
20. Use `env`, `configprops`, `conditions`, and `beans` to piece together evidence, while securing endpoints and sensitive values.
21. Tests must verify effective properties, typed binding, and the selected implementation, not just that a file contains a key.
22. For configuration issues, find the effective source and failing layer before making changes; avoid editing multiple places at once.

**Core mindset:** when a property is unread, look for it in **Environment**; when binding fails, check the **prefix, Java type, and properties bean**; when the profile is wrong, confirm the **active profile set and conditions**. Tracing the flow from configuration source to injected bean finds the exact cause instead of randomly tweaking YAML or annotations.
