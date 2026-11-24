# Providing Fallback Values with `${key:default}` in Spring Boot

## 1. The Problem: An Application Needs Configuration, but a Property May Not Be Provided Yet

When deploying Spring Boot across a laptop, staging machine, and production, the same property may or may not have a value depending on the environment. For instance, a service needs an HTTP port, retry count, timeout, or an external system address:

- On a developer's machine, default port `8080` and timeout `5s` are usually sufficient.
- In production, the deployment platform may provide `SERVER_PORT` and a different target URL.
- A non-critical feature can be disabled by default if no environment variable is set.
- Conversely, a database password or required signing key should not be replaced with a dummy value just to let the application start.

Spring supports **property placeholders** to reference a property from the configuration environment. The `${key:default}` syntax lets you declare a **fallback value** if the referenced property does not exist or cannot be resolved to a value.

Example:

~~~properties
app.retry.max-attempts=${MAX_ATTEMPTS:3}
~~~

When `MAX_ATTEMPTS` is not configured, the value of `app.retry.max-attempts` after placeholder resolution is `3`. When the environment provides `MAX_ATTEMPTS=7`, the value becomes `7`.

The goal of this lesson is to understand **the syntax, when fallback values are used, data types, how configuration sources combine, and the limits of defaults**. A single colon in a placeholder can change the startup behavior of the entire application.

## 2. Structure of a Property Placeholder

A property placeholder has the form:

~~~text
${key}
${key:default}
~~~

Components:

| Component | Meaning |
| --- | --- |
| `${` and `}` | Delimit the property placeholder expression |
| `key` | Name of the Spring property to look up in `Environment` or property sources |
| `:` | Separator between the property name and the default value |
| `default` | Value used when the `key` property cannot be resolved |

Examples:

~~~text
${server.port}                    → requires looking up server.port
${server.port:8080}               → uses 8080 if server.port is absent
${app.feature.enabled:false}     → defaults to false
${app.message:Hello}             → defaults to the string Hello
${app.timeout:5s}                → defaults to string 5s, convertible to Duration
${app.endpoint:http://localhost:8080} → defaults to a URL
~~~

This is a **property resolution** mechanism, not a global OS-level default assignment for the application. Placeholders are resolved based on the property sources Spring knows about at the time of use.

Note: `${...}` is not **Spring Expression Language**. SpEL uses `#{...}` syntax, typically to evaluate expressions. Both syntaxes can appear in the Spring ecosystem, but they have different meanings and should not be used interchangeably.

## 3. When the Property Is Present vs. Absent

Consider the code:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class RetryPolicy {
    private final int maxAttempts;

    public RetryPolicy(@Value("${app.retry.max-attempts:3}") int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public int maxAttempts() {
        return maxAttempts;
    }
}
~~~

In `application.yml`:

~~~yaml
app:
  retry:
    max-attempts: 6
~~~

The reference `${app.retry.max-attempts:3}` retrieves `6` because the key exists. If you remove `app.retry.max-attempts` from all sources, the placeholder uses the fallback value `3`.

| Scenario | Property found | Result when injected into `int` |
| --- | --- | --- |
| `app.retry.max-attempts=6` | Yes | `6` |
| `app.retry.max-attempts=0` | Yes | `0` |
| `app.retry.max-attempts` absent | No | `3` |
| `app.retry.max-attempts=invalid` | Yes, but wrong type | May fail type conversion; does not automatically fall back to `3` |
| `app.retry.max-attempts=` (empty string) | Present with empty value | Does not automatically fall back to `3`; may fail converting to `int` |

**Key point:** defaults handle **missing properties**, not automatic validation. Values like `0`, `false`, and empty strings can be genuine supplied values, not equivalent to "not found."

## 4. Using Placeholders in `application.properties`

In `src/main/resources/application.properties`:

~~~properties
server.port=${PORT:8080}
spring.application.name=${APP_NAME:catalog-service}

app.client.base-url=${CATALOG_API_URL:http://localhost:8081}
app.client.connect-timeout=${CONNECT_TIMEOUT:5s}
app.retry.max-attempts=${MAX_ATTEMPTS:3}
app.audit.enabled=${AUDIT_ENABLED:false}
~~~

Resolution when no environment variables are provided:

~~~properties
server.port=8080
spring.application.name=catalog-service

app.client.base-url=http://localhost:8081
app.client.connect-timeout=5s
app.retry.max-attempts=3
app.audit.enabled=false
~~~

If the deployment provides:

~~~bash
export PORT=9090
export APP_NAME=catalog-production
export CATALOG_API_URL=https://catalog.example.org
export CONNECT_TIMEOUT=2s
export MAX_ATTEMPTS=5
export AUDIT_ENABLED=true
java -jar catalog-service.jar
~~~

then the referenced values in the file can receive the new values.

One distinction to note: in this example, `PORT` is a property/environment variable name **placed inside a placeholder**. That differs from how Spring Boot maps `SERVER_PORT` directly to `server.port` via relaxed binding. Both approaches can work, but they have precedence rules and value sources that must be considered clearly.

## 5. Using Placeholders in YAML

YAML allows hierarchical configuration; property placeholders usually sit at the leaf values:

~~~yaml
server:
  port: "${PORT:8080}"

spring:
  application:
    name: "${APP_NAME:catalog-service}"

app:
  client:
    base-url: "${CATALOG_API_URL:http://localhost:8081}"
    connect-timeout: "${CONNECT_TIMEOUT:5s}"
  retry:
    max-attempts: "${MAX_ATTEMPTS:3}"
  audit:
    enabled: "${AUDIT_ENABLED:false}"
~~~

Spring Boot loads the YAML file into property names such as `app.client.base-url` and `app.retry.max-attempts`. When these values are requested, placeholders can reference other configuration sources.

**Put strings containing placeholders inside YAML quotes** if the value has special characters, colons, or needs to avoid misinterpretation by the YAML parser. In YAML, quotes around a value do not mean it becomes an unresolved literal for Spring; they mainly control how the YAML parser reads the string.

URL example:

~~~yaml
app:
  callback-url: "${CALLBACK_URL:http://localhost:8080/api/callback}"
~~~

The first colon after `CALLBACK_URL` is the delimiter for the default section. The colon inside `http://` is part of the fallback value.

## 6. Using `@Value` with Default Values

`@Value` is suitable when a bean needs a few simple values:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final String senderName;
    private final boolean enabled;
    private final int maxAttempts;

    public NotificationService(
            @Value("${app.notification.sender-name:system}") String senderName,
            @Value("${app.notification.enabled:false}") boolean enabled,
            @Value("${app.notification.max-attempts:3}") int maxAttempts) {
        this.senderName = senderName;
        this.enabled = enabled;
        this.maxAttempts = maxAttempts;
    }

    public String describe() {
        return senderName + ": enabled=" + enabled + ", maxAttempts=" + maxAttempts;
    }
}
~~~

When the application has:

~~~properties
app.notification.enabled=true
app.notification.max-attempts=8
~~~

then `senderName` receives `system`, `enabled` receives `true`, and `maxAttempts` receives `8`.

It is recommended to use **canonical lowercase kebab-case property names** in placeholders, such as `app.notification.sender-name`. This supports consistent property name lookup by Spring Boot, including when values are supplied via environment variables.

### When Using `@Value("${key}")` Without a Default

Example:

~~~java
public ConnectionInfo(@Value("${app.remote.url}") String url) {
    this.url = url;
}
~~~

If Spring cannot resolve `app.remote.url`, bean creation can fail with an unresolved placeholder error. For a **required** value, this can be desirable behavior: the application detects missing configuration immediately at startup.

If you want the value to be genuinely optional, add a meaningful default:

~~~java
public ConnectionInfo(@Value("${app.remote.url:http://localhost:8080}") String url) {
    this.url = url;
}
~~~

Do not add dummy defaults such as `changeme`, `password`, or unsafe production URLs just to hide missing critical configuration errors.

## 7. Defaults Can Be Strings, Numbers, Booleans, or Durations

Syntactically, the value after the colon is first and foremost **default content**; the final type depends on where it is used or the target binding type.

Example:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.time.Duration;

@Component
public class RuntimeOptions {
    private final String region;
    private final int workerCount;
    private final boolean metricsEnabled;
    private final Duration timeout;

    public RuntimeOptions(
            @Value("${app.region:local}") String region,
            @Value("${app.worker-count:4}") int workerCount,
            @Value("${app.metrics-enabled:false}") boolean metricsEnabled,
            @Value("${app.timeout:10s}") Duration timeout) {
        this.region = region;
        this.workerCount = workerCount;
        this.metricsEnabled = metricsEnabled;
        this.timeout = timeout;
    }
}
~~~

The values `4`, `false`, and `10s` need to be converted to `int`, `boolean`, and `Duration`, respectively. In a Spring Boot application with an appropriate conversion service, duration syntax like `10s` is supported; for configurations with many properties or where explicit conversion/validation control is needed, prefer `@ConfigurationProperties`.

If a source sets `app.worker-count=hello`, the default `4` **does not automatically replace the invalid value**. Spring finds `hello` and may report an error converting to `int`.

## 8. Placeholders Inside Values with Prefixes and Suffixes

A placeholder does not have to take up the entire value. It can be combined with fixed text:

~~~yaml
app:
  storage:
    root: "/srv/${APP_NAME:catalog}/data"
  client:
    endpoint: "https://${API_HOST:localhost}:${API_PORT:8443}/v1"
  welcome:
    message: "Hello ${DISPLAY_NAME:guest}"
~~~

If `APP_NAME=catalog-prod`, `API_HOST=api.example.org`, and `API_PORT=443`, the resolved values take the form:

~~~text
/srv/catalog-prod/data
https://api.example.org:443/v1
Hello guest
~~~

String composition keeps simple cases concise, but avoid building complex URLs out of many placeholders if it makes them hard to inspect or prone to missed escaping. When configuration varies substantially across environments, a complete `app.client.endpoint` property is often easier to manage.

## 9. Empty Default: `${key:}`

You can leave the part after the colon empty:

~~~text
${key:}
~~~

Example:

~~~java
@Value("${app.optional-label:}")
private String optionalLabel;
~~~

When `app.optional-label` is absent from configuration sources, the placeholder resolves to an **empty string** (`""`).

For a genuinely optional string, this can be appropriate. But for numbers, booleans, enums, or types with strict conversion rules, an empty string can cause a type conversion error or unexpected result.

Do not treat the following three cases as identical:

| Case | Meaning |
| --- | --- |
| `${app.label:guest}` and key is missing | Result is `guest` |
| `${app.label:}` and key is missing | Result is an empty string |
| `app.label=` is declared | The key exists with an empty value; default `guest` is not automatically applied |

If business logic requires "use default when the string is blank," "use default when a number is non-positive," or "use default when value is null," that is a **custom business/validation rule**, not the basic behavior of placeholder syntax.

## 10. Nested Defaults: Try the First Source, Then the Second

A default value can contain **another placeholder**. Example:

~~~yaml
app:
  client:
    base-url: "${PRIMARY_API_URL:${SECONDARY_API_URL:http://localhost:8080}}"
~~~

Meaning:

1. If `PRIMARY_API_URL` has a value, use it.
2. Otherwise, try `SECONDARY_API_URL`.
3. If neither exists, use `http://localhost:8080`.

You can visualize it as:

~~~text
PRIMARY_API_URL exists?
  ├─ Yes → use PRIMARY_API_URL
  └─ No
        SECONDARY_API_URL exists?
          ├─ Yes → use SECONDARY_API_URL
          └─ No → use http://localhost:8080
~~~

In `application.properties`:

~~~properties
app.client.base-url=${PRIMARY_API_URL:${SECONDARY_API_URL:http://localhost:8080}}
~~~

Nested placeholders are useful when migrating gradually from an old variable name to a new one or allowing multiple fallback levels.

However, a very long nested chain becomes hard to understand and prone to circular references. For complex configuration policies, consider applying explicit logic in code or a configuration management system, and use validation to ensure the final value is valid.

## 11. Referencing Another Spring Property as a Default

A default does not have to be a fixed literal string. One property can use another property as a fallback:

~~~yaml
app:
  http:
    default-timeout: 8s
  client:
    timeout: "${CLIENT_TIMEOUT:${app.http.default-timeout:5s}}"
~~~

With this example:

- If `CLIENT_TIMEOUT=3s`, the client timeout value is `3s`.
- If `CLIENT_TIMEOUT` is absent but `app.http.default-timeout=8s` is present, the value is `8s`.
- If neither referenced source is present, the value is `5s`.

Referencing `app.http.default-timeout` instead of hardcoding `8s` multiple times helps avoid duplicated configuration.

Note: although placeholders can look up keys from `Environment`, resolution must still follow property source precedence. Placing one key before another in a YAML file does not mean the earlier key is "resolved first and later keys are allowed to reference it."

**Avoid circular references**, for example:

~~~properties
app.a=${app.b}
app.b=${app.a}
~~~

When these keys are resolved, a circular reference can cause an error rather than producing a useful value.

## 12. Combining with Profiles: Defaults and Precedence Are Two Separate Layers

Suppose the common file in the JAR is:

~~~yaml
# application.yml
app:
  client:
    timeout: "${CLIENT_TIMEOUT:5s}"
    base-url: "${CLIENT_URL:http://localhost:8080}"
~~~

And the file for the prod profile is:

~~~yaml
# application-prod.yml
app:
  client:
    timeout: "${PROD_CLIENT_TIMEOUT:12s}"
    base-url: "${CLIENT_URL:https://api.example.org}"
~~~

When the `prod` profile is activated, the profile file can override keys from the common file. Spring then resolves the placeholder from **the winning final definition for the key being used**, rather than merging the defaults of the two files.

Example:

| Scenario | Value of `app.client.timeout` |
| --- | --- |
| No prod profile; no `CLIENT_TIMEOUT` | `5s` |
| No prod profile; `CLIENT_TIMEOUT=4s` | `4s` |
| With prod profile; no `PROD_CLIENT_TIMEOUT` | `12s` |
| With prod profile; `PROD_CLIENT_TIMEOUT=20s` | `20s` |

If another environment variable directly sets the property name `APP_CLIENT_TIMEOUT=30s`, the environment source can override both the common file and the profile file, because environment variables usually take precedence over Config Data.

These are two concepts to distinguish:

- **Property source precedence:** chooses the source containing the effective definition for `app.client.timeout`.
- **Placeholder default:** only applies when the placeholder inside the selected definition cannot find the referenced key.

`${CLIENT_TIMEOUT:5s}` is not a directive meaning "regardless of profile, set timeout to 5 seconds."

## 13. When Is a Default Ignored Due to a Higher-Precedence Source?

Suppose `application.yml` contains:

~~~yaml
server:
  port: "${PORT:8080}"
~~~

When the OS has `PORT=9090`, the placeholder usually resolves to port `9090`.

However, if you add:

~~~bash
java -jar app.jar --server.port=7070
~~~

then the command-line argument `--server.port=7070` usually has higher precedence than Config Data files. The effective value of `server.port` is `7070`; the application does not need to use `8080` or `9090` from the placeholder value in the file.

If the environment variable `SERVER_PORT=6060` is set, that name can map directly to `server.port`, whereas `PORT` only takes effect because the file is referencing `${PORT:8080}`.

Comparison example:

~~~text
application.yml:
  server.port = ${PORT:8080}

Variables:
  PORT=9090
  SERVER_PORT=6060

No CLI override:
  server.port → 6060 (SERVER_PORT variable overrides the property directly)
~~~

Therefore, if a default has no effect, check **which configuration source is winning**, not just whether the placeholder syntax is written correctly.

## 14. Placeholders Are Not a Replacement for All Required Configuration

Some properties can have safe defaults:

| Property | Suitable default in many apps | Condition |
| --- | --- | --- |
| `server.port` | `8080` | No strict port requirement |
| `app.retry.max-attempts` | `3` | Clear retry policy exists |
| `app.feature.enabled` | `false` | Disabling the feature is a safe state |
| `app.client.timeout` | `5s` | Evaluated as suitable for the environment |
| `app.logging.sample-rate` | `0.1` | Rate is bounded and its meaning is understood |

Conversely, the following values should usually be explicitly required rather than given fake defaults:

- Production database passwords.
- JWT signing keys, private keys, or authentication secrets.
- Real payment system URLs when no clear sandbox mode exists.
- Bucket/tenant names defining customer data boundaries.

Example requiring fail-fast when missing:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaymentCredentials {
    private final String apiKey;

    public PaymentCredentials(@Value("${payment.api-key}") String apiKey) {
        this.apiKey = apiKey;
    }
}
~~~

Here no default is declared, so missing configuration is detected when the bean is created. For larger applications, you can use `@ConfigurationProperties` and Bean Validation to check required status, format, or value ranges.

Do not record real passwords/tokens in examples, committed files, or diagnostic logs.

## 15. Distinguishing Placeholder Defaults from `@ConfigurationProperties` Defaults

For a group of clearly typed properties, Spring Boot usually recommends using `@ConfigurationProperties` instead of many individual `@Value` annotations.

YAML example using placeholders:

~~~yaml
app:
  worker:
    count: "${WORKER_COUNT:4}"
    timeout: "${WORKER_TIMEOUT:10s}"
~~~

Java record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int count, Duration timeout) {}
~~~

Enable configuration class scanning:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class WorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(WorkerApplication.class, args);
    }
}
~~~

During binding, the type converter can convert `4` to `int` and `10s` to `Duration`.

However, there is a **separate default mechanism** for constructor binding in Spring Boot: `@DefaultValue`. Example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerPropertiesWithDefaults(
        @DefaultValue("4") int count,
        @DefaultValue("10s") Duration timeout
) {}
~~~

Here, the default belongs to the **record binding rules**; it does not require writing placeholders in the YAML file. Both approaches can address default needs, but they have different responsibilities:

| Way to set default | Location | When suitable |
| --- | --- | --- |
| `${KEY:default}` in YAML/properties | Configuration file | Want to reference another source and provide a fallback at the property level |
| `@Value("${key:default}")` | Java injection point | A few isolated properties |
| `@DefaultValue` in `@ConfigurationProperties` | Typed configuration definition | Want defaults tied to the configuration/binding structure |

Do not arbitrarily mix multiple mechanisms for the same property, because determining the actual value at deployment time becomes harder.

## 16. Difference Between Placeholder Defaults and `Environment#getProperty`

`Environment` also has an API for retrieving a default value:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RegionResolver {
    private final Environment environment;

    public RegionResolver(Environment environment) {
        this.environment = environment;
    }

    public String region() {
        return environment.getProperty("app.region", "local");
    }
}
~~~

`getProperty("app.region", "local")` returns `local` when looking up `app.region` yields no result. In terms of usage goal, it is close to `${app.region:local}`.

However, you should distinguish:

- `${app.region:local}` is **property reference syntax**, used in strings where Spring resolves placeholders.
- `environment.getProperty("app.region", "local")` is a **Java API call** on `Environment` with a default parameter.
- `@DefaultValue` is a way to describe defaults in **`@ConfigurationProperties` binding**.

The three mechanisms belong to different layers. Use the mechanism that matches where you want to declare and control the default value.

## 17. Can Defaults Contain Colons, Spaces, or Slashes?

Yes. Fallback values can be URLs, file paths, or text strings:

~~~yaml
app:
  callback-url: "${CALLBACK_URL:http://localhost:8080/callback}"
  cache-dir: "${CACHE_DIR:/tmp/app-cache}"
  greeting: "${APP_GREETING:Hello user}"
~~~

The colon after the key name marks the **start of the default**; other colons inside the default string can be part of the value.

However, when a default contains characters like brackets, nested strings, escape sequences, or delimiters processed by external tools, you must distinguish three syntax layers:

1. Source file syntax (YAML, properties, or Java string).
2. Spring property placeholder syntax.
3. Shell/Compose/Kubernetes syntax if the value is defined externally.

For example, YAML quotes do not stop Spring from processing placeholders; conversely, Docker Compose files have their own variable interpolation mechanism using `$`. If you copy `${...}` verbatim into a Compose value, you may need to escape it according to Compose rules to prevent premature interpolation. Do not assume every tool interprets the same syntax.

When you need to store the **literal** text `${some.key}` without Spring resolving it, use an escape mechanism appropriate for Spring Framework and the file format in use; simply adding YAML quotes is not enough to express "do not process placeholder."

## 18. Verifying Behavior with a Small Spring Boot Example

Create `src/main/resources/application.yml`:

~~~yaml
app:
  profile-label: "${PROFILE_LABEL:local}"
  retries: "${APP_RETRIES:3}"
  display-url: "${APP_DISPLAY_URL:http://localhost:8080}"
~~~

Create a bean to observe the three values after Spring starts:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationPrinter implements CommandLineRunner {
    private final String label;
    private final int retries;
    private final String displayUrl;

    public ConfigurationPrinter(
            @Value("${app.profile-label}") String label,
            @Value("${app.retries}") int retries,
            @Value("${app.display-url}") String displayUrl) {
        this.label = label;
        this.retries = retries;
        this.displayUrl = displayUrl;
    }

    @Override
    public void run(String... args) {
        System.out.println("label = " + label);
        System.out.println("retries = " + retries);
        System.out.println("displayUrl = " + displayUrl);
    }
}
~~~

**Run 1 — no variables provided:**

~~~bash
java -jar demo.jar
~~~

Expected output:

~~~text
label = local
retries = 3
displayUrl = http://localhost:8080
~~~

**Run 2 — variables provided:**

~~~bash
export PROFILE_LABEL=production
export APP_RETRIES=6
export APP_DISPLAY_URL=https://example.org
java -jar demo.jar
~~~

Expected output:

~~~text
label = production
retries = 6
displayUrl = https://example.org
~~~

**Run 3 — directly overriding the property:**

~~~bash
java -jar app.jar --app.retries=9
~~~

If there is no special higher-precedence source, `app.retries` has the value `9` because the command-line argument wins over the value from YAML. This case illustrates that **a default inside a placeholder does not hardcode the value**.

The commands are illustrative examples; the JAR name should be adjusted to match your actual application. When logging configuration, only print non-sensitive values.

## 19. Common Errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `Could not resolve placeholder` error | Required key is absent and no default is declared | Provide the required configuration or a valid default |
| `@Value` uses default even though variable was supposedly set | Wrong variable name or variable not passed to the Java process | Verify the variable name and container export/configuration |
| Has `${key:3}` but bean still fails number parsing | Key exists with an invalid or empty value | Fix the value source and add validation; defaults do not replace invalid values |
| Changed YAML file but result did not change | A higher-precedence source overrides the property | Identify the winning property source |
| `${APP_PORT:8080}` receives a value other than 8080 | `APP_PORT` already has a value | Check the deployment environment |
| `server.port=${PORT:8080}` but server listens on port specified by `SERVER_PORT` | `SERVER_PORT` variable directly overrides `server.port` | Distinguish `PORT` reference from `SERVER_PORT` override |
| Placeholder in YAML has a syntax error | Invalid special characters/quotes/escapes | Use proper quotes and verify source formatting |
| Hardcoded password default | Missing secret is masked by a dummy value | Remove the default and require the secret explicitly |
| Default is empty string but code needs a number | No valid value to convert to a number | Pick a valid numeric default or handle optionality deliberately |
| Circular placeholder reference | Two or more keys depend on each other | Eliminate the cycle and define a clear default source |
| Docker Compose processes `${...}` before Spring | Two tools both have interpolation mechanisms | Escape or quote according to each configuration layer the placeholder passes through |

When investigating, work from **the property name being queried** to **the final configuration source**, and only then check the placeholder and value type. If the application uses Actuator, the `env` or `configprops` endpoints can help diagnose issues, but access must be restricted and sensitive data protected.

## 20. Self-Check Exercises

### Exercise 1 — Present vs. Absent Value

Code:

~~~java
@Value("${app.retry.max-attempts:3}")
private int maxAttempts;
~~~

Determine the result when:

- `app.retry.max-attempts` is absent.
- `app.retry.max-attempts=5` is present.
- `app.retry.max-attempts=0` is present.

**Answer:** `3`, `5`, and `0`, respectively. The default is only used when the property is not found.

### Exercise 2 — Nested Placeholder

Configuration:

~~~properties
app.api-url=${PRIMARY_URL:${FALLBACK_URL:http://localhost:8080}}
~~~

Determine the value when:

1. `PRIMARY_URL=https://primary.example.org`.
2. `PRIMARY_URL` is absent, but `FALLBACK_URL=https://backup.example.org`.
3. Neither variable is present.

**Answer:** `https://primary.example.org`, `https://backup.example.org`, and `http://localhost:8080`, respectively.

### Exercise 3 — Empty Value

In YAML:

~~~yaml
app:
  worker-count: "${WORKER_COUNT:4}"
~~~

If the environment has `WORKER_COUNT=` as an empty string, can we conclude the value will always be `4`?

**Answer:** **No.** The variable already exists with an empty value, so the default is not automatically used. If bound to `int`, converting from an empty string can even cause an error.

### Exercise 4 — Property Source Precedence Over Placeholders

In YAML:

~~~yaml
server:
  port: "${PORT:8080}"
~~~

The environment has `PORT=9090`. Launch command:

~~~bash
java -jar app.jar --server.port=7070
~~~

Which port takes effect if there is no special higher-precedence source?

**Answer:** `7070`. The `--server.port` argument usually wins over properties from Config Data; the placeholder in YAML does not take precedence over this argument.

### Exercise 5 — Choosing Where to Place Defaults

You have a configuration group containing `maxAttempts` and `timeout`, and you want the Java record to have default values even if the keys are not created in `application.yml`. Which mechanism is appropriate?

**Suggested answer:** use `@ConfigurationProperties` together with `@DefaultValue` on constructor parameters/record components when appropriate. That places defaults at the typed binding layer, whereas `${key:default}` is appropriate when you need to reference another source within configuration values.

## 21. Key Takeaways

- **`${key:default}`** syntax means look up `key`; if absent, use `default`.
- **`${key}`** without a default is usually suitable when a value is required; a missing property can cause bean creation to fail.
- Defaults only handle **keys that are not found**. Values that are present but have the wrong type, are empty, or fail business rules must be handled separately.
- In YAML/properties, placeholders can take values from environment variables or other Spring properties.
- You can write **nested placeholders**: `${PRIMARY:${FALLBACK:local}}`.
- **`${key:}`** allows an empty default, which is more suitable for optional strings than for required typed configuration.
- Selecting a value from a **higher-precedence property source** happens independently of the placeholder's default mechanism.
- `@Value`, `Environment#getProperty(key, default)`, and `@ConfigurationProperties`/`@DefaultValue` serve different configuration layers.
- Only provide defaults when absence is valid; for secrets or mandatory production properties, fail fast and validate explicitly.

**References:**

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Framework — PropertySource Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
- [Spring Framework — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
