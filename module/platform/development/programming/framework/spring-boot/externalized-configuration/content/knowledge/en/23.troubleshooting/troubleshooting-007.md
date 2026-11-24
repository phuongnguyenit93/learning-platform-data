# Analyzing Placeholder, Type Conversion, and ConfigurationPropertiesBindException Errors in Spring Boot 3.3

## 1. Lesson Objectives

When Spring Boot fails to start because of a property, logs often show multiple nested exception layers. The outermost line might merely be `BeanCreationException`; deeper inside sit `ConfigurationPropertiesBindException`, `BindException`, `ConversionFailedException`, or a validation error. Sometimes only a message like `Could not resolve placeholder '...' in value "${...}"` appears. If you only read the last line or look only at the first exception name, it is easy to edit the wrong file, change the wrong value, or mask the error with a default.

This lesson focuses on three categories:

1. **Placeholder errors:** a `${name}` expression cannot find a matching property, creates a circular reference, has a bad default, or uses a non-canonical name.
2. **Type conversion errors:** a value was found yet cannot be converted to `int`, `Duration`, `DataSize`, an enum, a collection, or the target Java type.
3. **Bean binding errors:** Spring Boot cannot complete binding/validation of a `@ConfigurationProperties` bean and may throw `ConfigurationPropertiesBindException` as an outer wrapper.

**Practical goal:** read logs and pinpoint **which property failed**, **which value source is effective**, **which Java type is required**, **which stage failed**, and **the right fix conditions**, while avoiding printing secrets in logs.

The scope is Spring Boot **3.3** and corresponding Spring Framework APIs; exact exception names, messages, and wrapping can vary by execution path, bean style, patch version, IDE, and logging setup. Illustrative logs in this lesson convey common structure rather than promising byte-for-byte identical output on every run.

## 2. The Big Picture from Config Data to Bean

Look at the typical flow:

```text
application.properties / application.yaml
profile-specific files / config imports
OS environment / JVM -D / CLI
                |
                v
      Environment + PropertySources
                |
                v
      Select effective property
                |
                v
        Placeholder resolution
      ${app.host}, ${app.port:8080}
                |
                v
      Binder / ConversionService
  String -> Integer / Boolean / Duration
         DataSize / enum / object
                |
                v
           Bean Validation
       @Min / @NotBlank / @Valid
                |
                v
       @ConfigurationProperties bean
                |
                v
      Other services inject and consume
```

This is a high-level diagram. `@Value`, `Environment.getProperty`, `@ConfigurationProperties`, and direct `Binder` overlap, yet **do not pass through identical callback paths and exception wrapping** in all cases.

A failure can happen at multiple layers:

| Layer | Example | Common symptom |
| --- | --- | --- |
| Config Data loading | Broken YAML syntax, missing import location | Config Data / YAML parsing exception |
| Source selection | Env overrides file with invalid value | Effective property differs from the file being viewed |
| Placeholder | `${service.host}` unresolvable | `Could not resolve placeholder` or literal placeholder kept on certain bind paths |
| Conversion | `server.port=abc` for `Integer` | Conversion / number format failure |
| Bean binding | `app.port=abc` for a `@ConfigurationProperties` bean | `ConfigurationPropertiesBindException` / `BindException` |
| Validation | `app.threads=0` with `@Min(1)` | Bean validation / bind validation error |
| Bean lifecycle | Setter/constructor throws exception | Bean creation failure, caused by user code |
| Downstream runtime | Binds fine yet timeout is 10ms instead of 10s | Not necessarily a startup exception |

**Important:** seeing `ConfigurationPropertiesBindException` does not automatically mean placeholders caused it. Seeing `BeanCreationException` does not automatically mean bean registration failed. Follow the `Caused by` chain and analyze the **root cause**.

## 3. Unified Example Set

Suppose the application has these files:

```text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/config/AppProperties.java
src/main/resources/application.yaml
pom.xml
```

JavaBean configuration model:

```java
package com.example.demo.config;

import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    @NotBlank
    private String serviceName = "catalog";

    @Min(1)
    @Max(64)
    private int workerCount = 4;

    @NotNull
    private Duration connectTimeout = Duration.ofSeconds(5);

    private boolean featureEnabled;

    public String getServiceName() { return serviceName; }
    public void setServiceName(String value) { serviceName = value; }

    public int getWorkerCount() { return workerCount; }
    public void setWorkerCount(int value) { workerCount = value; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration value) {
        connectTimeout = value;
    }

    public boolean isFeatureEnabled() { return featureEnabled; }
    public void setFeatureEnabled(boolean value) {
        featureEnabled = value;
    }
}
```

Application:

```java
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
```

Valid config:

```yaml
app:
  service-name: catalog
  worker-count: 4
  connect-timeout: 5s
  feature-enabled: false
```

To run Bean Validation, the app needs a compatible provider, usually via:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

If the provider is absent or validation setup is not applied, constraints like `@Min`/`@NotBlank` may **not be enforced as expected**. That is an infrastructure setup issue, not Binder ignoring numeric syntax.

## 4. Reading an Exception Chain Properly

An illustrative log when `app.worker-count` is set to `abc`:

```text
APPLICATION FAILED TO START

Description:
Failed to bind properties under 'app.worker-count' to int:

    Property: app.worker-count
    Value: "abc"
    Origin: class path resource [application.yaml] - 4:17
    Reason: failed to convert java.lang.String to int

Action:
Update your application's configuration
```

In the stack trace, a chain similar to this can appear:

```text
BeanCreationException
  caused by ConfigurationPropertiesBindException
    caused by BindException
      caused by ConversionFailedException
        caused by IllegalArgumentException
          caused by NumberFormatException
```

This is an **illustrative diagram**, not guaranteed to show all six layers or the exact order in every build. For instance, standalone `@Value` may not go through `ConfigurationPropertiesBindException`; with Bean Validation, the deep cause can be `BindValidationException` rather than `NumberFormatException`.

When analyzing, prioritize reading:

1. **The error closest to the data** at the bottom of `Caused by`.
2. **Property name and prefix** the app attempted to bind.
3. **Value** causing the error, if safe to display in logs.
4. **Origin** to locate the file, position, or environment source.
5. **Target type** required by the Java code.
6. **Validation message** if the value converted yet violated a constraint.
7. **Action** suggested by FailureAnalyzer, then verify it matches the real cause.

Do not blindly edit a file whose name looks related when the log clearly shows the value came from OS environment or CLI.

## 5. Placeholder Syntax and How Spring Resolves It

Spring Boot supports placeholders in configuration values using:

```properties
app.base-url=https://api.example.test
app.endpoint=${app.base-url}/v1
```

When `app.endpoint` is consumed via appropriate Environment/Binding, the expected value is:

```text
https://api.example.test/v1
```

Syntax:

| Syntax | Meaning |
| --- | --- |
| `${key}` | Reference the value of a property |
| `${key:default}` | Use default if property cannot be resolved |
| `${app.host}` | Reference a multi-segment canonical name |
| `${app.port:8080}` | Default port 8080 if source is missing |
| `https://${app.host:localhost}:${app.port:8080}/v1` | Combine multiple placeholders in one string |

**The default after the colon is not a value that overrides higher-precedence sources.** It is merely a fallback when resolution fails to find a matching property per resolver semantics. If the key exists with an empty value, do not assume the default will apply.

### 5.1. Placeholders in application.yaml

```yaml
app:
  host: "api.internal"
  port: 8443
  endpoint: "https://${app.host}:${app.port}/v1"
```

Quotes help YAML store values containing `:` or `${...}` unambiguously as text. Spring Boot uses Environment to resolve placeholders **when values are consumed**, not by transforming the entire config upfront as the file parser reads it.

### 5.2. Placeholder Referencing a Higher Source

File:

```properties
app.host=localhost
app.endpoint=https://${app.host}:8443
```

Env:

```bash
APP_HOST=api.production.internal
```

If no higher source overrides `app.endpoint`, when it is resolved via the appropriate Environment, `${app.host}` can pull `api.production.internal` from the OS environment. Editing `app.host` in a lower file will not change the endpoint while env still overrides host.

**Identify every reference inside the string**, not just the `app.endpoint` property.

## 6. Missing Placeholder Errors

### 6.1. The @Value Case

```java
@Component
public class ClientInfo {

    @Value("${client.api-url}")
    private String apiUrl;
}
```

If no source supplies `client.api-url`, injecting the required placeholder can fail. Typical message:

```text
Could not resolve placeholder 'client.api-url'
in value "${client.api-url}"
```

This error can be wrapped in `BeanCreationException` or another bean injection error. `ConfigurationPropertiesBindException` need not appear because this uses `@Value`.

Questions to answer:

- Is the key name canonical?
- Was the file holding that property actually loaded?
- Do active profiles match?
- Is the environment variable name right?
- Did YAML indentation place the property under a different path?
- Is code running before a custom source was added?

### 6.2. When a Default Exists

```java
@Value("${client.api-url:https://localhost:8443}")
private String apiUrl;
```

When the key is not found, the default is used. This can be handy for optional local development settings.

**However, not every property should have a default:** passwords, API keys, mandatory production addresses, or security-sensitive namespaces usually need fail-fast behavior. Using a default URL in production can make an app connect to the wrong system.

### 6.3. Missing vs. Empty

File:

```properties
client.api-url=
```

When the key is present with an empty value, `${client.api-url:...}` usually does not fall back to the default merely because the String is empty. If the app requires a non-blank URL, use `@NotBlank` or appropriate business checks. If the target is `URI`, type conversion/validation must also be considered.

### 6.4. Placeholders in @ConfigurationProperties Can Behave Differently

Example:

```properties
app.connect-timeout=${DEPLOY_TIMEOUT}
```

If `DEPLOY_TIMEOUT` is missing, the outcome depends on how the placeholder resolver, target type, and that binding path's `BindHandler` handle unresolved values. You might see an unresolved placeholder message or an error converting the placeholder-containing `String` to `Duration`.

**Do not assume every `${...}` error emits the exact string `Could not resolve placeholder`.** Read the stack trace and target type, especially when using Binder or a custom `PlaceholdersResolver`.

## 7. Canonical Names in Placeholders Matter

Spring Boot recommends referencing properties in placeholders using **lowercase kebab-case**.

Good:

```properties
app.display-name=Catalog
app.greeting=Hello, ${app.display-name}
```

Avoid:

```properties
app.greeting=Hello, ${app.displayName}
```

With `${app.display-name}`, Spring Boot can consider both `app.displayName` and OS environment `APP_DISPLAYNAME` under appropriate relaxed naming rules. Using camelCase in placeholders might miss the name variants you expect.

### 7.1. Converting Property Names to OS Env

Given a canonical property:

```text
app.connect-timeout
```

Standard environment variable name:

```text
APP_CONNECTTIMEOUT
```

Rules:

1. Replace `.` with `_`.
2. **Remove** `-`; do not replace with `_`.
3. Uppercase.

`APP_CONNECT_TIMEOUT` can be interpreted as a different hierarchical property and should not be assumed equivalent to `app.connect-timeout`.

### 7.2. An Example of a Apparent Bug Caused by Misnamed Env

File:

```properties
app.url=https://${app.backend-host}
app.backend-host=localhost
```

Operator sets:

```text
APP_BACKEND_HOST=api.example.test
```

This may fail to override `app.backend-host` as intended. The value to check per convention is:

```text
APP_BACKENDHOST=api.example.test
```

If the URL still points to localhost, it may be an **env name mapping** issue rather than the placeholder resolver.

## 8. Circular Placeholder Reference Errors

Self-referencing case:

```properties
app.host=${app.host}
```

Or a cycle between two keys:

```properties
app.host=${app.endpoint-host}
app.endpoint-host=${app.host}
```

When the resolver traces values, it can detect the cycle and throw a **circular placeholder reference** exception. Exact message, exception class, and detection timing vary by resolver and consumption path.

### Diagnosing Circular References

Draw the graph:

```text
app.host
   |
   v
app.endpoint-host
   |
   v
app.host  <-- cycle
```

The fix is to **break the cycle** and pick one source as the base value:

```properties
app.host=api.example.test
app.endpoint-host=${app.host}
```

Do not blindly add defaults to both keys to "hide" a circular reference. Defaults generally apply only when a key cannot be resolved, not to fix an already-existing cyclic reference structure.

### Self-Referencing to Override an Old Value

A tempting misconfiguration:

```properties
app.url=${app.url}/v2
```

The intent might be taking the lower source's value and appending `/v2`. However, a placeholder referencing the same property name can resolve back to the very value being selected and form a cycle. **Never use this syntax as a "fetch pre-override value" trick.** Use a distinct property name for the base URL, or perform the transformation in code.

## 9. Syntax Errors and Nested Placeholders

A string like:

```properties
app.base=https://api.example.test
app.url=${app.base/v1
```

is missing `}`. Processing may keep the literal text or fail to resolve as intended. With target `String`, this easily slips through until a request hits the broken URL; with target `URI`, an error can surface during conversion.

Write instead:

```properties
app.url=${app.base}/v1
```

### 9.1. Defaults Containing Colons

Example:

```properties
app.callback=${app.callback-url:https://localhost:9443/v1}
```

The first `:` after the key name separates the default; subsequent `:` characters inside the default can be preserved per resolver semantics. Nevertheless, deeply nested placeholders and varied escape sequences are hard to read. Verify directly with a configuration test and avoid treating placeholders as an arbitrary expression language.

### 9.2. Do Not Confuse Spring Syntax with Docker Compose or Shell

In `compose.yaml`:

```yaml
environment:
  APP_HOST: "${APP_HOST:-localhost}"
```

this is **Docker Compose interpolation syntax**, not a Spring placeholder. Compose processes it before creating the container.

In `application.properties`:

```properties
app.host=${APP_HOST:localhost}
```

this is a **Spring-resolved placeholder** evaluated when the value is consumed. Both mechanisms share `${...}` notation, yet default rules, escaping, processing timing, and value sources differ.

When a value travels through Compose YAML, then an app file, then Spring, determine **which layer interprets placeholders first**. Do not stack escaping by intuition without tests.

## 10. SpEL and Placeholders Are Two Different Mechanisms

Spring supports SpEL expressions in `@Value`, for example:

```java
@Value("#{2 * 3}")
private int computed;
```

This is an expression inside a Java annotation. It differs from:

```java
@Value("${app.worker-count:4}")
private int workerCount;
```

The second syntax looks up a property and uses a default if missing.

In `application.properties`:

```properties
app.count=#{2 * 3}
```

SpEL **is not automatically evaluated when the parser loads the file into Environment**. Spring Boot documents that SpEL is not processed when reading files into Environment, even though `@Value` can evaluate SpEL when consuming a value. Do not expect `@ConfigurationProperties` to evaluate SpEL expressions like `@Value` does.

**Practical rule:** use `@ConfigurationProperties` for typed configuration, placeholders for property references, and SpEL only where expression semantics are genuinely needed.

## 11. Conversion Failure: Value Present Yet Target Type Rejects It

Suppose model:

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private int workerCount = 4;

    public int getWorkerCount() { return workerCount; }
    public void setWorkerCount(int workerCount) {
        this.workerCount = workerCount;
    }
}
```

File:

```properties
app.worker-count=three
```

Binder reads the String `three` yet cannot convert it to `int` via standard converters. This is a **type conversion error**, not a missing placeholder or missing bean.

A failure analysis may state:

```text
Failed to bind properties under 'app.worker-count' to int

Property: app.worker-count
Value: "three"
Origin: class path resource [application.properties] - ...
Reason: failed to convert java.lang.String to int
```

The deep cause usually involves `ConversionFailedException` or a number parsing error. Do not try to fix it by adding `${app.worker-count:4}` when `"three"` **already exists**; defaults do not cure malformed values.

### 11.1. Numeric Examples

| `app.worker-count` value | Converts to int? | Interpretation |
| --- | --- | --- |
| `4` | Yes | Valid value |
| `0` | Yes | Conversion succeeds; policy may reject |
| `-1` | Yes | Conversion succeeds; policy may reject |
| `3.5` | No under standard String → Integer | Decimal does not fit int |
| `three` | No | Non-numeric string |
| `999999999999999999999` | No | Exceeds int range |
| Empty string | Depends on target/bind path | Not automatically treated as 0 |
| Missing property | May retain initializer/default | Not a conversion error itself |

### 11.2. Java Range Overflow vs. Business Range Violation

```properties
app.worker-count=100
```

Can convert to `int`. Yet if annotated:

```java
@Min(1)
@Max(64)
private int workerCount;
```

then 100 **violates validation**, not `NumberFormatException`.

Conversely:

```properties
app.worker-count=99999999999999999999999
```

can fail before validation because `int` cannot represent it. Investigating the right layer ensures accurate reporting and fixes.

## 12. Duration: Format Errors and Silent Unit Mistakes

Spring Boot 3.3 supports binding `java.time.Duration` from:

- An integer, defaulting to **milliseconds** unless `@DurationUnit` is present.
- ISO-8601 format, such as `PT5S` or `PT1M`.
- Compact format such as `500ms`, `5s`, `2m`, `1h`.

Units listed in Boot 3.3 documentation:

| Suffix | Unit |
| --- | --- |
| `ns` | Nanosecond |
| `us` | Microsecond |
| `ms` | Millisecond |
| `s` | Second |
| `m` | Minute |
| `h` | Hour |
| `d` | Day |

Example:

```properties
app.connect-timeout=5s
```

for Java field:

```java
private Duration connectTimeout;
```

is five seconds.

However:

```properties
app.connect-timeout=5
```

is interpreted as **5 milliseconds** by default, even though it binds cleanly. This is a **semantic/unit mistake** that no exception detects automatically.

### 12.1. Common Symptoms

| Input | Outcome / diagnosis |
| --- | --- |
| `5000ms` | Five-second Duration |
| `5s` | Five-second Duration |
| `PT5S` | Five-second Duration |
| `5` | 5ms Duration by default |
| `soon` | Invalid Duration format |
| `5seconds` | Not in compact syntax listed in 3.3 docs; use `5s` |
| `-5s` | Can represent negative Duration; business logic must check |
| Huge value | May fail conversion or downstream logic |

If you want suffixless numbers interpreted as seconds:

```java
@DurationUnit(ChronoUnit.SECONDS)
private Duration connectTimeout;
```

Requires importing `java.time.temporal.ChronoUnit` and `org.springframework.boot.convert.DurationUnit`.

**Do not use placeholder defaults to hide unit errors.** `${app.connect-timeout:5s}` provides a reasonable default when missing, yet if env supplies `5`, the env source still wins and yields 5ms.

## 13. DataSize: 64 Is Not 64MB

`org.springframework.util.unit.DataSize` is the type for data sizes. Without `@DataSizeUnit`:

```properties
app.cache-size=64
```

is interpreted as **64 bytes**, not 64 MB.

Prefer:

```properties
app.cache-size=64MB
```

Suffixes supported in Spring Boot 3.3 include `B`, `KB`, `MB`, `GB`, `TB`.

### 13.1. Converter/Annotation Example

```java
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize cacheSize = DataSize.ofMegabytes(64);
```

With this annotation, a bare value `64` is interpreted in MB. Even so, writing `64MB` in configuration files is usually clearer for operators.

### 13.2. Invalid Suffixes

```properties
app.cache-size=64Megabytes
```

does not match Boot 3.3's standard compact form and can trigger conversion failure. Use `64MB`.

Similarly `64MiB` is not in the `B/KB/MB/GB/TB` suffix list in Boot 3.3 docs; use supported suffixes and keep unit semantics consistent across the system.

## 14. Enum, Boolean, URI, and List/Map

### Enum

```java
enum Mode {
    SAFE, FAST
}

private Mode mode = Mode.SAFE;
```

Property:

```properties
app.mode=UNKNOWN
```

can fail conversion because no matching enum constant exists. Do not expect the `SAFE` default to apply when the key is present with an invalid value.

### Boolean

```properties
app.feature-enabled=false
```

is valid and explicit. Yet:

```properties
app.feature-enabled=perhaps
```

is not an unambiguous boolean and can fail conversion. For readable, unambiguous config, use `true`/`false`.

### URI/URL

```java
private URI baseUri;
```

```properties
app.base-uri=http://[invalid
```

Target `URI` can reject invalid syntax. Conversely, a syntactically valid URI does not guarantee a valid DNS record or TLS certificate. **Conversion success is not a connectivity test.**

### List and Map

```yaml
app:
  retries:
    billing: 3
    search: invalid
```

If the Java model is `Map<String,Integer>`, the error sits at `app.retries.search` rather than the entire Map. Read the child property path inside the bind failure.

For a List:

```properties
app.workers[0]=4
app.workers[1]=abc
```

target `List<Integer>` can fail at index 1. Check the actual value at the highest-precedence source; lists also follow replacement rules across PropertySources rather than necessarily appending elements from two sources.

## 15. What Is ConfigurationPropertiesBindException?

`org.springframework.boot.context.properties.ConfigurationPropertiesBindException` is the exception Spring Boot defines when **binding of a `@ConfigurationProperties` bean fails**.

It usually appears while Spring Boot creates or processes configuration beans in ApplicationContext. Do not read the class name and conclude it is the root cause; it may simply act as a **wrapper recording bean/prefix context** around an inner `BindException` or validation error.

Example:

```text
Error creating bean with name 'app-...AppProperties'
    ...
ConfigurationPropertiesBindException:
    Error creating bean with name ...:
    Could not bind properties to 'AppProperties'
Caused by: BindException:
    Failed to bind properties under 'app' ...
Caused by: ConversionFailedException:
    Failed to convert from String to Integer
Caused by: NumberFormatException:
    For input string: "many"
```

Generated bean names can vary by registration method, bean name strategy, and type; do not hardcode expectations based on illustrative examples.

### 15.1. Distinguish from BindException

| Exception | General role |
| --- | --- |
| `ConfigurationPropertiesBindException` | Context wrapper when `@ConfigurationProperties` bean binding fails |
| `org.springframework.boot.context.properties.bind.BindException` | Binding a target via `Binder` failed |
| `ConversionFailedException` | Converting a value from source type to target type failed |
| `BindValidationException` | Validation of a bind operation failed |
| `BeanCreationException` | Container failed to create/initialize bean; may wrap the errors above |
| `IllegalArgumentException` | May be parse, placeholder, constructor validation, or another cause |
| `NumberFormatException` | One numeric parse failure, often deep in the stack |

**Do not confuse the two `BindException` classes in different packages:**

- Spring Boot Binder: `org.springframework.boot.context.properties.bind.BindException`.
- Spring Framework data binding: `org.springframework.validation.BindException`.

They have different roles and APIs; when reading code/imports, check the **full package name**.

### 15.2. Reading Details from BindException

Spring Boot `BindException` exposes helpful details such as:

- `getName()`: configuration property name being bound.
- `getTarget()`: target bind metadata.
- `getProperty()`: specific related configuration property, if available.
- `getOrigin()`: origin, if determinable.

Example in custom Binder handling code:

```java
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.Binder;

try {
    int count = Binder.get(environment)
            .bind("app.worker-count", Integer.class)
            .orElse(4);
} catch (BindException ex) {
    System.err.println("Could not bind property: " + ex.getName());
    System.err.println("Target: " + ex.getTarget());
    System.err.println("Origin: " + ex.getOrigin());
    throw ex;
}
```

**Never log `getProperty().getValue()` unconditionally**: config can contain secrets. `getOrigin()` can be `null` if the source lacks origin metadata.

When code calls Binder directly, `BindException` can appear **without `ConfigurationPropertiesBindException`**, because it is not initializing a managed `@ConfigurationProperties` bean.

## 16. Bean Validation: Valid Type Yet Violates Constraints

In the example model:

```java
@Min(1)
@Max(64)
private int workerCount = 4;
```

Input:

```properties
app.worker-count=0
```

converts to int 0 cleanly. Yet with `@Validated` and a Bean Validation provider properly configured, 0 violates `@Min(1)`, causing bean binding to fail.

The cause can be `BindValidationException` carrying validation errors, rather than `NumberFormatException`.

### Comparison

| Input | Conversion | Validation `@Min(1)` | Outcome |
| --- | --- | --- | --- |
| `4` | Succeeds | Passes | Valid |
| `1` | Succeeds | Passes | Lower bound |
| `0` | Succeeds | Fails | Validation failure |
| `-1` | Succeeds | Fails | Validation failure |
| `abc` | Fails | Not checked | Conversion failure |
| `999999999999999999` | May fail for int | Not checked | Type overflow |

### Nested Validation

```java
@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    @Valid
    private final Server server = new Server();

    public Server getServer() { return server; }

    public static class Server {

        @Min(1)
        private int port = 8080;

        public int getPort() { return port; }
        public void setPort(int port) { this.port = port; }
    }
}
```

When wanting nested object constraints checked, `@Valid` and proper validation setup matter. Missing cascade validation can leave invalid nested fields undetected. Use Jakarta `jakarta.validation.Valid` with Spring Boot 3.3.

**Do not try applying `@Min` directly to arbitrary custom types or `Duration`:** constraints have specific supported data types. For positive durations, write a custom validator or domain checks.

## 17. Why Does a Valid File Property Still Fail?

A classic case:

```properties
# application.properties
app.worker-count=4
```

Yet the container has:

```text
APP_WORKERCOUNT=abc
```

OS environment normally has higher precedence than Config Data in Spring Boot 3.3. Binder can select `abc`, attempt conversion to `int`, and fail.

**The file value was not arbitrarily ignored.** That is source precedence; the higher source supplied invalid data.

Illustrative table:

| Source | Property | Value | Relative order |
| --- | --- | --- | --- |
| Packaged application.properties | `app.worker-count` | `4` | Low |
| External application-prod.yaml | `app.worker-count` | `8` | Higher than packaged file |
| OS environment | `APP_WORKERCOUNT` | `abc` | Higher than Config Data |
| JVM `-D` | Undeclared | — | No effect |
| Command-line | Undeclared | — | No effect |

Outcome can be a conversion failure on `abc`, **not automatically falling back to 8 or 4**.

### 17.1. Order Matters in Deployments

Under common default precedence:

```text
Config Data
    <
OS environment
    <
Java system properties (-D)
    <
SPRING_APPLICATION_JSON
    <
Command-line arguments (--key=value)
```

Test/DevTools sources and custom PropertySources can alter the actual environment. When working with an app with customized bootstrap, inspect the actual order rather than guessing solely from default docs.

### 17.2. Profiles and Config Data Imports

- `application-prod.yaml` is loaded only in the matching profile context.
- `spring.config.import` can bring in extra file/configtree sources.
- `spring.config.location` and `additional-location` can change where Boot looks for files.
- External Config Data files outside the JAR have their own precedence relative to packaged files.
- A missing non-optional import location can fail startup **before** bean binding.
- Multi-document YAML/properties and `spring.config.activate.on-profile` can toggle documents on/off.

To know the effective raw value, inspect **all loaded sources**, not just the file open in your IDE.

## 18. Distinguishing YAML Errors Before Binder Errors

Valid YAML example:

```yaml
app:
  worker-count: 4
  connect-timeout: 5s
```

Indentation error:

```yaml
app:
worker-count: 4
```

This snippet has structure that misses intent or can cause a parser error depending on context. It does not necessarily create `app.worker-count`; when YAML is flattened, the path name differs.

Syntax error:

```yaml
app:
  connect-timeout: [5s
```

Cannot parse as valid YAML, failing Config Data loading **before** `@ConfigurationProperties` binds.

Therefore:

- If the error says the YAML file cannot be parsed, fix YAML structure/syntax.
- If YAML parses yet the property is absent, check indentation/path and active documents.
- If the property is present yet conversion fails, check value/target type.
- If conversion succeeds yet validation fails, check constraints.

Never try to handle a YAML parser error with `@Min` or a custom Converter.

## 19. Origin: Source File, Position, and Effective Value

Spring Boot can retain **Origin** for certain Config Data properties, such as file path and line/column position. On binding errors, FailureAnalyzer can display this information.

Illustrative example:

```text
Property: app.worker-count
Value: "oops"
Origin: class path resource [application.yaml] - 5:17
Reason: failed to convert java.lang.String to int
```

Not every PropertySource knows file/line:

- OS environment may show only source/variable name.
- Java system properties carry no line numbers.
- A custom MapPropertySource may lack origin metadata.
- If logs are sanitized, Value may not print in full.
- If the failure occurs too early or outside Binder, FailureAnalyzer may not provide the same structure.

**No origin does not mean no property.** Origin aids investigation; it is not a prerequisite for a valid value.

### 19.1. Do Not Leak Secrets While Debugging

Properties such as:

```text
spring.datasource.password
client.api-token
app.private-key
```

must be treated as sensitive. Never print raw values from Environment, BindException, or Actuator to prove origin. Verify only key presence, source, data type, length when truly safe, and connectivity status.

## 20. Diagnosing with Environment Inside the Application

For **non-sensitive** keys, you can read both the effective value and bound target bean:

```java
package com.example.demo;

import com.example.demo.config.AppProperties;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ConfigDiagnostics {

    @Bean
    ApplicationRunner showSafeSettings(
            Environment env, AppProperties props) {
        return args -> {
            String raw = env.getProperty("app.connect-timeout");
            System.out.println("Raw timeout: " + raw);
            System.out.println("Typed timeout: "
                    + props.getConnectTimeout());
        };
    }
}
```

When `app.connect-timeout=5s`, the typed value normally prints as `PT5S`. When `5` without `@DurationUnit`, the typed value can be `PT0.005S` (5ms).

**Limitation:** `ApplicationRunner` runs only if the context initializes successfully. If startup fails during bean binding, the Runner never runs to print diagnostics. In that case read failure analysis, stack traces, and known config sources.

### 20.1. Inspecting Source Names Without Printing Values

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public void listPropertySources(ConfigurableEnvironment env) {
    for (PropertySource<?> source : env.getPropertySources()) {
        System.out.println("Source: " + source.getName());
    }
}
```

PropertySource order helps understand precedence. However, source names alone do not show how a key resolved through env var aliases/relaxed binding. **Do not search for a single raw key String across all sources and definitively conclude which source won.**

## 21. Using Actuator and Controlled Logging

If the app includes Spring Boot Actuator:

- `/actuator/env` can show PropertySources/effective values per exposure/sanitization config.
- `/actuator/configprops` helps inspect `@ConfigurationProperties` beans and binding data.

Both endpoints are operationally sensitive. Never expose them publicly; require authentication, authorization, enable only needed endpoints, and configure masking/sanitization before investigating.

In test or staging environments, you can raise logging on relevant packages:

```properties
logging.level.org.springframework.boot.context.config=DEBUG
logging.level.org.springframework.boot.context.properties=DEBUG
```

Spring Boot's `--debug` prints the condition evaluation report, yet **does not guarantee** printing all raw values or every conversion step. When details are lacking, raise targeted log levels in a controlled environment; avoid turning on full-application TRACE in production.

### 21.1. Startup Logging Does Not Resolve Circular Placeholders

If there is a cycle `app.a=${app.b}` and `app.b=${app.a}`, debug logging only helps identify keys; it does not break the cycle. Fix the relationship between property names.

### 21.2. Logs Can Mask Values

Values being sanitized in Actuator/failure analysis is a healthy security signal. Do not strip masking just for a quick answer; cross-check manifests, source paths, key presence, and value types in authorized places without dumping secrets to logs.

## 22. When Do You Need a Custom Converter?

Suppose a property is `RegionCode`:

```java
public record RegionCode(String value) {
    public RegionCode {
        if (value == null || !value.matches("[a-z]{2}-[a-z]+-[0-9]+")) {
            throw new IllegalArgumentException("Invalid region code");
        }
    }
}
```

A converter registered for `@ConfigurationProperties`:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public class RegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(source.trim());
    }
}
```

If the value does not match the pattern, the constructor throws `IllegalArgumentException` and binding fails. This is an **application-defined conversion/domain rule**, not a missing placeholder error.

### 22.1. Converters Are Needed Very Early

Spring Boot initializes configuration-properties conversion infrastructure early; custom Converters should have simple dependencies. If a Converter injects a service initialized late, it can trigger bean initialization/circular dependency errors distinct from value errors.

Do not add custom converters just to parse basic `Duration`/`DataSize`: Boot already supports those types and unit annotations.

### 22.2. Never Use Converters as Secret Loggers

Converter code must not log source values unconditionally. A converter handling tokens/passwords could leak data if it logs "Cannot convert value: ..." with raw credentials. Throw non-sensitive messages keeping metadata about property name/target type where safe.

## 23. @ConfigurationProperties and @Value Have Different Error Paths

| Feature | `@ConfigurationProperties` | `@Value` |
| --- | --- | --- |
| Purpose | Bind type-safe config groups | Inject a single value/expression |
| Relaxed binding | Yes | Limited; use canonical placeholders |
| IDE metadata | Yes via processor | Not via the same config-properties metadata mechanism |
| SpEL | Not automatically evaluated like `@Value` | Yes |
| Bean validation | `@Validated` and suitable provider | Does not automatically share configprops validation mechanism |
| Bind failure | Can throw `ConfigurationPropertiesBindException` | Usually bean injection / placeholder / conversion error |
| Nested object/Map/List | Well supported | Harder to manage |
| Default when missing | Initializer / `@DefaultValue` / model fallback | `${key:default}` |
| Recommended for many keys | Yes | Best reserved for simple scalars when appropriate |

### 23.1. @Value Missing Placeholder

```java
@Value("${app.service-name}")
private String name;
```

If the key is absent, a strict placeholder resolver can throw IllegalArgumentException, failing bean creation. The error is not necessarily wrapped by Spring Boot's configuration properties binder.

### 23.2. @Value Type Conversion Failure

```java
@Value("${app.worker-count}")
private int workerCount;
```

If the key exists with value `abc`, the resolver finds the String yet injection/conversion to int fails. The error can be `TypeMismatchException`/`ConversionFailedException` in the BeanCreationException chain; **`ConfigurationPropertiesBindException` need not appear**.

### 23.3. @ConfigurationProperties Wrong Type

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private int workerCount;
    // getters/setters
}
```

With `app.worker-count=abc`, Spring Boot Binder fails, and in managed bean lifecycle it can throw `ConfigurationPropertiesBindException`. Inspect the target bean and `BindException` to locate the bad value.

## 24. Exercise Reproducing Three Error Categories

### Scenario A — Missing Placeholder

In a bean:

```java
@Component
public class RemoteClientConfig {
    @Value("${remote.api-url}")
    private String apiUrl;
}
```

Do not set `remote.api-url` in any source. Expect an injection failure reporting an unresolved placeholder. Fix: provide the property in a loaded source, fix the key name, or add a default **if genuinely optional**.

### Scenario B — Conversion Failure

Using `AppProperties` from section 3, set:

```properties
app.worker-count=many
```

Expect bean binding failure converting String to int. Fix: supply a valid numeric value such as `4`; do not change `@Min(1)` because constraints do not solve syntax errors.

### Scenario C — Validation Failure

Set:

```properties
app.worker-count=0
```

Expect conversion to succeed yet validation to reject due to `@Min(1)`, assuming `@Validated`/provider are active. Fix: supply `1` or higher, unless business rules truly allow 0, in which case update contract/constraints and tests.

### Scenario D — Wrong Unit Throws No Error

Set:

```properties
app.connect-timeout=5
```

Binder succeeds yet produces 5ms instead of 5s. Fix: write `5s`. This scenario requires **asserting typed values**, since looking for exceptions will not catch it.

### Scenario E — Env Override Causes Error Differing from File

File:

```properties
app.worker-count=4
```

Environment:

```bash
APP_WORKERCOUNT=bad
```

Expect an error similar to B, even though the file is valid. Fix: correct or remove the higher-precedence env var.

## 25. Testing with ApplicationContextRunner

`ApplicationContextRunner` from `spring-boot-test` creates a lightweight context suitable for testing bean binding. With `AppProperties` from section 3:

```java
package com.example.demo;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.demo.config.AppProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class AppPropertiesBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(Config.class);

    @Test
    void validPropertyBinds() {
        runner.withPropertyValues(
                "app.worker-count=4",
                "app.connect-timeout=5s")
            .run(context -> {
                assertThat(context).hasNotFailed();
                AppProperties props =
                    context.getBean(AppProperties.class);
                assertThat(props.getWorkerCount()).isEqualTo(4);
                assertThat(props.getConnectTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(5));
            });
    }

    @Test
    void invalidIntegerFails() {
        runner.withPropertyValues("app.worker-count=many")
            .run(context ->
                assertThat(context).hasFailed());
    }

    @Test
    void invalidRangeFailsWithValidationProvider() {
        runner.withPropertyValues("app.worker-count=0")
            .run(context ->
                assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AppProperties.class)
    static class Config {
    }
}
```

Prerequisites: `AppProperties` has `@Validated`, a compatible Bean Validation provider is on the test classpath, along with Spring Boot test/JUnit/AssertJ. `hasFailed()` does not guarantee the exact wrapper exception across every patch; if needed, inspect the startup failure and cause chain in the test to distinguish conversion vs. validation.

### 25.1. Testing Placeholders

For a bean using `@Value("${remote.api-url}")`, a context runner can register the bean and run without supplying `remote.api-url`. When a strict placeholder is unresolved, the context fails. Then test `withPropertyValues("remote.api-url=https://example.test")` to confirm the bean initializes cleanly.

If the test runner automatically picks up another source providing the property, isolate the environment or use an unlikely-to-collide test key so you do not mistakenly conclude the placeholder is optional.

### 25.2. Testing Bare Duration

```java
runner.withPropertyValues("app.connect-timeout=5")
    .run(context -> {
        assertThat(context).hasNotFailed();
        AppProperties props = context.getBean(AppProperties.class);
        assertThat(props.getConnectTimeout())
            .isEqualTo(java.time.Duration.ofMillis(5));
    });
```

This is a helpful test proving **the value is parser-valid yet wrong in unit** if operators intended 5 seconds.

### 25.3. ApplicationContextRunner Does Not Replace All Bootstrap Tests

The runner supplies properties directly and builds a minimal context. It does not automatically reproduce full Config Data bootstrap, profile-specific external files, OS env/container secret mounts, and production command-line arguments.

If a bug appears only on Kubernetes, add integration/smoke tests running the application with matching profiles, Config Data imports, env var naming, and file volume layouts (using dummy secrets).

## 26. Checking Bean Registration and Binding Strategy

Sometimes developers see the right value in `Environment`, yet the bean property remains null/default. Possible causes:

- `@ConfigurationProperties` class **was not registered**.
- Wrong prefix.
- JavaBean lacks a setter for a scalar field.
- Constructor binding does not match model/constructor.
- Class was scanned in a different package.
- Multiple beans of the same type exist and the service injects a different one.
- Property name matches yet bean field/record component is named differently.
- Class was instantiated manually with `new` rather than bound by the container.
- Nested child properties lack getters/setters or proper instance setup.

Example:

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private int workerCount = 4;

    public int getWorkerCount() { return workerCount; }

    // No setter for JavaBean binding to update workerCount
}
```

If code uses JavaBean binding for a scalar field, having only a getter prevents Binder from updating the value. Fix by adding a setter or using constructor binding appropriately, rather than changing `app.worker-count` to a strange key.

### Constructor Binding

With a record:

```java
@ConfigurationProperties(prefix = "app")
public record WorkerOptions(int workerCount,
                            java.time.Duration timeout) {
}
```

constructor binding works when the bean type is registered via `@EnableConfigurationProperties` or scanning. Never create a record and expect `@Autowired` field injection or setter binding to occur.

## 27. BindResult and Direct Binder Differ from Managed Beans

Example:

```java
import org.springframework.boot.context.properties.bind.Binder;

Integer retryCount = Binder.get(environment)
    .bind("app.worker-count", Integer.class)
    .orElse(4);
```

This is a direct Binder call. If the value cannot bind, you can hit `org.springframework.boot.context.properties.bind.BindException`; `ConfigurationPropertiesBindException` will not appear outside it because the app is not initializing a managed `@ConfigurationProperties` bean.

An important point:

- Property not found: `BindResult` is unbound; `orElse(4)` uses the fallback.
- Property `app.worker-count=0` exists: bound result is 0; fallback is not used.
- Property `app.worker-count=abc` exists: conversion can throw; `orElse(4)` does not catch exceptions to rescue invalid values.

Additionally, a manually constructed Binder over a set of `ConfigurationPropertySources` does not automatically share the same converters, placeholder resolvers, validation handlers, or bean lifecycle as the Binder Spring Boot sets up in ApplicationContext. When debugging manual Binder usage, distinguish missing infrastructure from genuinely bad values.

## 28. Errors in Custom Converters, Placeholder Resolvers, or Early Lifecycle

An advanced case: the project registers a custom `@ConfigurationPropertiesBinding` converter, or a bean named `conversionService`.

Spring Boot can require conversion infrastructure very early. If a custom converter injects complex services, logs may show bean creation/circular dependency failures rather than simple value parse errors.

Similarly, an early `EnvironmentPostProcessor` may read values **before** all Config Data sources are prepared, depending on post-processor ordering. A custom placeholder resolver can alter how missing/default/circular references behave.

To isolate the right error:

1. Determine **when** the property is read.
2. Check whether Environment already contains the needed `PropertySources`.
3. Check whether custom Converter/BindHandler/PlaceholderResolver actually participates.
4. Ensure code creates no dependency cycles or side effects while reading config.
5. If using manual Binder, compare its infrastructure setup separately against managed binding.

Do not alter global `ConversionService`/PropertySource order just to patch a single misconfigured key, unless clearly required and covered by broad impact tests.

## 29. Symptom-Based Troubleshooting Table

| Symptom | Likely cause | Next diagnostic step |
| --- | --- | --- |
| `Could not resolve placeholder 'x'` | Missing key, wrong name, profile/source unloaded | Identify canonical key and actual source |
| `${x}` appears verbatim in String | Resolver did not run on that path or ignores unresolved | Check resolver, target type, and timing |
| Circular placeholder reference | `x` references `y` and loops back to `x` | Draw reference graph, break cycle |
| `NumberFormatException` | Non-numeric text or overflow | Check value and Java numeric target |
| `ConversionFailedException` | Converter from source type to target type failed | Read cause/target type |
| `ConfigurationPropertiesBindException` | Managed config bean failed to finish binding | Read nested `BindException`/validation |
| `BindValidationException` | Data bound yet constraint violated | Check `@Min`/`@Max`/`@NotBlank`/`@Valid` |
| `BeanCreationException` | Container failed to initialize bean | Inspect deep cause; do not jump to conclusions |
| `@Value` fails while config bean succeeds | Placeholder/injection path differs from Binder | Use canonical placeholder, check scope |
| File has valid int yet startup fails | Env/CLI overrides with invalid value | Check precedence and Origin |
| Bare Duration 5 runs as 5ms | Default unit is ms | Write `5s` |
| Bare DataSize 64 runs as 64B | Default unit is bytes | Write `64MB` |
| YAML parsed yet property missing | Wrong indentation/nested path | Inspect flattened keys |
| App runs yet `@Min(1)` does not reject 0 | Validation not applied | Check `@Validated` and provider |
| Nested `@Valid` not enforced | Missing cascade validation | Add `@Valid`/configure validation properly |
| Bean getter keeps default despite env override | Bean unregistered or JavaBean lacks setter | Check model |
| Error happens only in prod | Different active profiles, env, configtree/import, or `-D`/CLI | Reproduce deployment sources |
| Failure right at Config Data import | Location missing, invalid file format | Check `spring.config.import` and startup logs |
| Secret printed in failure analysis/logs | Missing masking or code logs raw values | Stop dumping values; secure Actuator |
| Edited file yet bean stays stale | No automatic hot reload | Restart/rollout or intentional refresh |

## 30. Step-by-Step Analysis Sequence

When seeing a startup exception, follow this sequence:

1. **Read the top message** to know whether failure occurred during Config Data loading, bean creation, or user code.
2. **Trace all `Caused by` entries** and identify the deepest meaningful root cause, not just wrappers.
3. **Record the canonical property name** and affected prefix.
4. **Identify the Java target type**: primitive, String, enum, Duration, DataSize, URI, List, Map, or custom type.
5. **Determine the effective source:** file, profile, OS env, `-D`, CLI, JSON, configtree, import.
6. **Check placeholders**: do all referenced keys exist? Are there defaults? Any circular references?
7. **Check env mapping names**: dot → underscore, dash → remove, uppercase.
8. **Check value syntax**: numeric, boolean, enum, Duration, URI parsing...
9. **Check units and representation bounds**: is `5` for Duration 5ms? Does the number overflow `int`?
10. **Check Bean Validation** if conversion succeeded: constraints, nested `@Valid`, provider.
11. **Check bean registration/lifecycle** if property exists yet did not bind: scanning, setters, constructors.
12. **Fix the precedence-winning source**, rather than editing a lower file hoping runtime changes.
13. **Create the smallest reproducible test**, asserting the post-conversion value too.
14. **Re-run in an equivalent environment** to verify startup and downstream behavior.
15. **Avoid leaking secrets** at every step and update runbooks if the root cause was how config was supplied.

Decision tree:

```text
APPLICATION FAILED TO START
             |
             v
   Is it Config Data parse/load?
       /                \
      Yes                No
      |                   |
      v                   v
 Fix file/location    Missing placeholder?
                          /       \
                         Yes       No
                         |           |
                         v           v
                  Fix key/source   Conversion error?
                     /default        /       \
                                    Yes       No
                                    |           |
                                    v           v
                              Fix format    Bind validation?
                              /target/unit      /      \
                                             Yes         No
                                             |             |
                                             v             v
                                       Fix constraint   Check bean
                                       /value           lifecycle
                                                        /code
```

The decision tree guides orientation; real stack traces can combine multiple errors, such as a missing placeholder followed by a converter trying to parse the literal placeholder string.

## 31. Common Mistakes When Fixing Errors

### 31.1. Enabling ignoreInvalidFields Just to Force Startup

`@ConfigurationProperties` has an `ignoreInvalidFields` option. However, if a higher source holds `app.worker-count=abc`, ignoring invalid bindings can make the app silently fall back to defaults, masking a deployment mistake. Usually you should fix the source value and let startup fail fast when critical config is invalid.

### 31.2. Removing Constraints Just Because @Min Fails Startup

If `@Min(1)` is a valid business rule, fix the input `worker-count=0` instead of removing validation. Only change constraints when business requirements genuinely change and tests accompany them.

### 31.3. Using Placeholder Defaults for Mandatory Passwords

`${db.password:secret}` can cause a system to run with a dangerous default password. For production credentials, use a secret manager/configtree and fail-fast validation; never hardcode secrets in sources.

### 31.4. Editing Only the application.yaml Open in the IDE

If `APP_WORKERCOUNT` or `--app.worker-count=...` wins, editing lower YAML will not change the runtime value. Inspect Origin/PropertySource precedence.

### 31.5. Using SpEL Instead of Placeholders in @ConfigurationProperties

`@ConfigurationProperties` does not process SpEL like `@Value`. If the goal is referencing another property, use placeholders in Config Data; if complex computation is needed, do it in code with a clear contract.

### 31.6. Ignoring Data Types

`app.connect-timeout=5` can bind cleanly yet run wrongly as 5ms. Do not look for exceptions in that situation; inspect typed values and units.

### 31.7. Hiding Bugs with a @Value Default Different from Real Config Defaults

`@Value("${app.worker-count:4}")` might suit one component while a `@ConfigurationProperties` bean has its own default. Maintain one consistent contract; avoid two components using conflicting fallbacks for the same key.

### 31.8. Printing Entire Environments and Exception Payloads Containing Secrets

This can leak sensitive info in logs/tickets/chats. Keep diagnostics scoped to non-sensitive keys and origins; never dump passwords/tokens.

## 32. Operations Checklist

- [ ] Identified the deepest root cause in `Caused by` rather than just the wrapper name.
- [ ] Distinguished Config Data parse, placeholder, conversion, validation, and bean lifecycle errors.
- [ ] `${name}` placeholders use canonical lowercase kebab-case.
- [ ] Every referenced key exists or has an appropriate default when optional.
- [ ] No circular placeholder references exist.
- [ ] Distinguished empty String, missing, `0`, and `false`.
- [ ] Checked profiles, external files, Config Data imports, OS env, JVM `-D`, and CLI.
- [ ] Environment variables renamed properly (dot/underscore/dash/uppercase).
- [ ] Checked Java target types and conversion rules.
- [ ] `Duration`/`DataSize` use explicit unit suffixes.
- [ ] Enum, Boolean, numeric, and URI values follow proper syntax.
- [ ] `@ConfigurationProperties` bean is registered.
- [ ] JavaBean setters/constructor binding work properly.
- [ ] Bean Validation provider present when constraints are needed.
- [ ] Nested objects validated via `@Valid` when required.
- [ ] `ignoreInvalidFields` not enabled merely to mask errors.
- [ ] Checked `Origin` when supported by the source.
- [ ] Never log raw credentials or publicly expose Actuator endpoints.
- [ ] Reproducible test exists with realistic non-sensitive/dummy values.
- [ ] Restarted/rolled out after fixes if the running process does not auto-refresh.
- [ ] Runbook clearly documents property owner and source to edit.

## 33. Official References

- **Spring Boot 3.3 — Externalized Configuration**, including *PropertySource Order*, *Property Placeholders*, *Type-safe Configuration Properties*, *Properties Conversion*, *ConfigurationProperties Validation*, *Config Data Imports*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 API — ConfigurationPropertiesBindException**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBindException.html
- **Spring Boot 3.3 API — BindException**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindException.html
- **Spring Boot 3.3 API — Binder**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- **Spring Boot 3.3 API — BindValidationException**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/validation/BindValidationException.html
- **Spring Boot 3.3 API — @ConfigurationProperties**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- **Spring Framework 6.1 — PropertyPlaceholderHelper**: https://docs.spring.io/spring-framework/docs/6.1.4/javadoc-api/org/springframework/util/PropertyPlaceholderHelper.html
- **Spring Framework — Environment Abstraction / PropertySources**: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- **Jakarta Bean Validation**: https://jakarta.ee/specifications/bean-validation/

## 34. Summary

In Spring Boot 3.3, to handle configuration errors effectively, always distinguish:

```text
Unresolved placeholder
     -> missing key / wrong name / circular reference / unloaded source
Value present yet unconvertible
     -> bad format / wrong type / Java type overflow
Value converted yet bean validation fails
     -> business constraint / @Validated / @Valid
Managed @ConfigurationProperties binding did not complete
     -> ConfigurationPropertiesBindException wrapping context
```

**Takeaway:** `ConfigurationPropertiesBindException` typically tells you *the configuration bean failed to finish binding*, not *why*. The reason lies in the cause chain, `Property`, `Origin`, source precedence, target type, and validation. Fix the exact failing layer, test with post-conversion values, and keep configuration secrets out of logs.
