# Handling Wrongly Typed Values with `ignoreInvalidFields` in Spring Boot

## 1. The problem: configuration exists but cannot bind to the Java type

In Spring Boot, an application can receive configuration from `application.yml`, `application.properties`, environment variables, Java system properties, or command-line arguments. When using `@ConfigurationProperties`, Spring Boot attempts to **bind** these configuration values to fields or constructor parameters of a Java class.

For example, a config file declares:

~~~yaml
app:
  worker:
    thread-count: 8
    timeout: 15s
    enabled: true
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private int threadCount = 4;
    private Duration timeout = Duration.ofSeconds(5);
    private boolean enabled = false;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

When values are valid, the Binder can convert:

- `8` → `int`.
- `15s` → `java.time.Duration`.
- `true` → `boolean`.

But suppose production supplies:

~~~yaml
app:
  worker:
    thread-count: "many"
    timeout: "15s"
    enabled: true
~~~

`many` is not a valid integer. The Binder locates the key `app.worker.thread-count` but cannot convert the string to `int`.

By default, Spring Boot typically **reports a binding error and halts creation of the configuration bean** rather than silently substituting another value. Nevertheless, the `@ConfigurationProperties` annotation provides the `ignoreInvalidFields` attribute to choose less strict handling for certain binding errors.

This topic requires clearly distinguishing three questions:

1. **Does the property exist?**
2. **Does the property name belong to the Java model being bound?**
3. **Can the property value be converted to the target Java type?**

`ignoreInvalidFields` relates primarily to the third category. It is not a mechanism that turns invalid configuration into valid values, and it must not be treated as a validation system.

## 2. What is `ignoreInvalidFields`?

`ignoreInvalidFields` is an attribute of the annotation:

~~~java
org.springframework.boot.context.properties.ConfigurationProperties
~~~

Syntax:

~~~java
@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public class WorkerProperties {
    // ...
}
~~~

The default value of `ignoreInvalidFields` is **`false`**.

| Value | Meaning |
| --- | --- |
| `ignoreInvalidFields = false` | Default. Errors binding/converting invalid values are normally reported rather than ignored. |
| `ignoreInvalidFields = true` | Instructs the Binder to ignore ignorable invalid-field errors during configuration binding. |

Treat `true` as **relaxing binding error handling**, not as an option that makes input data valid.

Example:

~~~java
@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public class WorkerProperties {
    private int threadCount = 4;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }
}
~~~

If input is `app.worker.thread-count=many`, the Binder can ignore that property's conversion error, leaving `threadCount` initialized in the object as `4`. However, this is **behavior to understand within a specific JavaBean binding context**: do not generalize that every configuration kind or every constructor-bound object automatically gets a valid default value.

Reason: when a field is ignored, the resulting value depends on how the object is created, initial field state, primitive vs reference types, binding style, and subsequent constraints.

## 3. Strict default: `ignoreInvalidFields = false`

Configuration example:

~~~properties
app.worker.thread-count=not-a-number
app.worker.enabled=true
~~~

Class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = false
)
public class WorkerProperties {
    private int threadCount = 4;
    private boolean enabled;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

When Spring Boot creates the `WorkerProperties` bean through `@ConfigurationProperties`, it attempts to convert `not-a-number` to `int` and typically fails.

An error message may look like:

~~~text
Failed to bind properties under 'app.worker.thread-count'
to int

Property: app.worker.thread-count
Value: "not-a-number"
Reason: failed to convert ...
~~~

Actual messages depend on the Spring Boot version, config source, converter, and bean location. You may encounter `ConfigurationPropertiesBindException`, `BindException`, or conversion exceptions in the cause chain.

**This is usually desirable behavior for production.** Instead of running with the wrong thread count, the application stops early so operators can fix the configuration.

In code, you do not need to write `ignoreInvalidFields = false` explicitly because it is already the default:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    // ...
}
~~~

Writing `false` explicitly is only useful when emphasizing project policy or for teaching.

## 4. When `ignoreInvalidFields = true` is enabled

Update the annotation:

~~~java
@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public class WorkerProperties {
    private int threadCount = 4;
    private boolean enabled = false;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

File:

~~~yaml
app:
  worker:
    thread-count: invalid
    enabled: true
~~~

With this style of JavaBean binding, a commonly observed outcome is:

- The Binder cannot convert `invalid` to `int`.
- That property's error is ignored thanks to `ignoreInvalidFields=true`.
- `threadCount` may retain its initial value of `4`.
- `enabled=true`, if bound normally, can still be applied.

However, **do not treat the final state of every field as a contractual guarantee that the Binder always skips one bad property and continues applying all others**. Which errors are ignored and the resulting state depend on the binding mechanism—especially with nested objects, collections, constructor binding, or custom conversions.

For the engineering goal "invalid values must be detected immediately", keep the default `false` rather than relying on `ignoreInvalidFields=true`.

## 5. Wrong type (invalid) vs unrecognized name (unknown)

The `@ConfigurationProperties` annotation has **two independent attributes** that are easily confused:

~~~java
@ConfigurationProperties(
        prefix = "app",
        ignoreInvalidFields = false,
        ignoreUnknownFields = true
)
public class AppProperties {
    // ...
}
~~~

Common defaults are:

- `ignoreInvalidFields = false`.
- `ignoreUnknownFields = true`.

Distinguish:

**Wrong type or unbindable value (invalid field)**

~~~yaml
app:
  retry:
    max-attempts: "a lot"
~~~

Java:

~~~java
private int maxAttempts;
~~~

The name `max-attempts` has a binding target `int maxAttempts`, but the value `a lot` cannot be converted to `int`. This situation involves `ignoreInvalidFields`.

**Name with no matching target (unknown field)**

~~~yaml
app:
  retry:
    max-attempts: 3
    experimental-toggle: true
~~~

Java only has:

~~~java
private int maxAttempts;
~~~

If `experimental-toggle` has no matching field in the configuration model, it may be treated as an unbound property. This is an `ignoreUnknownFields` issue, not a `String`-to-`int` conversion error.

| Situation | Primary attribute involved |
| --- | --- |
| `max-attempts=abc` while Java needs `int` | `ignoreInvalidFields` |
| `max-attempts=3` while Java has no matching field | `ignoreUnknownFields` |
| `timeout=oops` while Java needs `Duration` | `ignoreInvalidFields` |
| Extra `debug-extra` not declared in class | `ignoreUnknownFields` |
| Required key completely missing | Defaults, nullability, validation; not automatically solved by `ignoreInvalidFields` |
| Right type, violates business rule | Bean Validation or business logic check |

Do not set `ignoreUnknownFields=false` expecting it to handle `int` parsing errors. Conversely, enabling `ignoreInvalidFields=true` is not meant to "allow extra unknown keys in configuration".

## 6. Example comparing four scenarios

Suppose the configuration bean is:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private int maxConnections = 10;
    private Duration timeout = Duration.ofSeconds(5);

    public int getMaxConnections() {
        return maxConnections;
    }

    public void setMaxConnections(int maxConnections) {
        this.maxConnections = maxConnections;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Consider these cases, assuming no higher-precedence property source exists:

| Case | Configuration | Interpretation |
| --- | --- | --- |
| Valid | `max-connections=20`, `timeout=8s` | Both fields can be converted and bound |
| Missing key | No `max-connections` | JavaBean can retain its initialized value `10` |
| Wrong type | `max-connections=lots` | Reports type conversion error by default |
| Unknown | `connection-label=primary`, undeclared in class | Default `ignoreUnknownFields=true` usually ignores unbindable keys |

When `ignoreInvalidFields=true` is enabled, the "wrong type" case may be ignored. Yet ignoring one field **does not certify that the whole object is valid**.

For example, if `timeout` is ignored and stays `5s`, that value might suit dev while being inappropriate for production. Thus an application needs its own policy deciding which settings are optional and which defaults are truly safe.

## 7. How to register the configuration bean so binding runs

`@ConfigurationProperties` is not enough if the class is not registered as a Spring bean appropriately. A common way is enabling scanning.

File `src/main/java/com/example/demo/config/ClientProperties.java`:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private int maxConnections = 10;
    private Duration timeout = Duration.ofSeconds(5);

    public int getMaxConnections() {
        return maxConnections;
    }

    public void setMaxConnections(int maxConnections) {
        this.maxConnections = maxConnections;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Application file:

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

An alternative is using `@EnableConfigurationProperties(ClientProperties.class)` on a `@Configuration` or application class.

Then a service can consume the configuration via constructor injection:

~~~java
import org.springframework.stereotype.Service;
import com.example.demo.config.ClientProperties;

@Service
public class ClientService {
    private final ClientProperties properties;

    public ClientService(ClientProperties properties) {
        this.properties = properties;
    }

    public int configuredPoolSize() {
        return properties.getMaxConnections();
    }
}
~~~

Here the Binder binds **configuration data** into `ClientProperties`, and the Spring container injects the constructed `ClientProperties` bean into `ClientService`.

The `ignoreInvalidFields` setting only matters if the bean actually goes through configuration properties binding.

## 8. Example with `Duration` and `DataSize`: wrong units are also invalid data

Spring Boot can convert strings with units into appropriate Java types:

~~~yaml
app:
  transport:
    timeout: 5s
    max-payload: 10MB
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.transport")
public class TransportProperties {
    private Duration timeout = Duration.ofSeconds(3);
    private DataSize maxPayload = DataSize.ofMegabytes(1);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public DataSize getMaxPayload() {
        return maxPayload;
    }

    public void setMaxPayload(DataSize maxPayload) {
        this.maxPayload = maxPayload;
    }
}
~~~

The values `5s` and `10MB` are valid under unit syntaxes supported by Spring Boot.

However:

~~~yaml
app:
  transport:
    timeout: "soon"
    max-payload: "lots-of-data"
~~~

cannot express a valid `Duration` or `DataSize`. The error is in **conversion/binding**.

If `ignoreInvalidFields=true` is enabled:

- The corresponding binding failure may be avoided.
- That does not convert the wrong values into valid types.
- Initialized defaults may remain intact in the JavaBean, though you should not assume the same across all binding styles.

For timeouts or payload limits affecting performance, cost, or system safety, **detecting the error and fixing the input data** is usually far more reliable than silently ignoring it.

## 9. When a value has the right type yet violates business rules

Suppose:

~~~yaml
app:
  worker:
    thread-count: -4
    timeout: 0s
~~~

`-4` is a valid integer. `0s` is a convertible duration value. Therefore they may **not trigger a type conversion error**.

Yet in a worker pool application:

- A negative thread count may be invalid.
- A zero timeout may violate processing requirements.
- An overly large retry threshold may overload the system.

`ignoreInvalidFields` is not responsible for defining these constraints. Use **Bean Validation** or checks in Java code.

Example:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    @Min(1)
    private int threadCount = 4;

    @NotNull
    private Duration timeout = Duration.ofSeconds(5);

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

The project needs an appropriate Bean Validation provider, such as the `spring-boot-starter-validation` dependency in Spring Boot 3.x.

`@Min(1)` checks that the thread count is at least 1. `@NotNull` only checks that `timeout` is not null; it does **not** ensure `timeout` is greater than 0. If `timeout > 0` is required, add a suitable constraint or extra check.

**Important:** even with `ignoreInvalidFields=true`, validation can still fail startup if the final object violates constraints. Never treat the ignore flag as a switch to disable all validation.

## 10. Combining `ignoreInvalidFields` with `@Validated`

Some projects may want to ignore conversion errors on non-critical fields while still rejecting an invalid final state:

~~~java
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public class WorkerProperties {
    @Min(1)
    private int threadCount = 4;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }
}
~~~

Suppose the file has `thread-count=invalid`. If the conversion error is ignored and the field keeps its default `4`, `@Min(1)` still passes.

This does not prove production configuration was supplied accurately. It only proves that **the final object satisfies a post-binding condition**.

If the JavaBean does not set a default for `threadCount`:

~~~java
@Min(1)
private int threadCount;
~~~

the Java default of primitive `int` is `0`. When conversion is ignored and the field stays 0, `@Min(1)` validation can reject the bean.

Visualize three layers of responsibility:

~~~text
Property sources
      ↓
Binder + conversion
      ↓
ignoreInvalidFields?  → ignore ignorable binding errors
      ↓
Final value in object
      ↓
Bean Validation / invariant checks
      ↓
Is the bean valid for the application to use?
~~~

`ignoreInvalidFields` only affects how **a group of Binder-layer errors** is handled. It does not guarantee subsequent layers succeed.

## 11. Missing property is not the same as wrong type

Class example:

~~~java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private int maxRetries = 3;

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

If the key `app.client.max-retries` is completely absent:

- No conversion fails because there is no `abc` value to convert.
- With JavaBean binding, `maxRetries` can retain its default `3`.
- `ignoreInvalidFields` is not needed for this default retention to happen.

In an immutable class using constructor binding:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(int maxRetries) {}
~~~

There are no setters or JavaBean-style field initializers. Missing values depend on constructor-binding semantics, parameter types, and declared defaults. For an explicit default:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @DefaultValue("3") int maxRetries
) {}
~~~

`@DefaultValue` is a **binding-layer default mechanism**, not an error-ignoring flag. If the deployer supplies `max-retries=abc`, `@DefaultValue("3")` itself is not a promise to fix bad values.

## 12. Constructor binding and error-ignoring capabilities

In Spring Boot 3.x, a `@ConfigurationProperties` class with a single parameterized constructor, or a record with a canonical constructor, can generally be constructor-bound without an explicit `@ConstructorBinding`.

Example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public record WorkerProperties(
        @DefaultValue("4") int threadCount,
        @DefaultValue("5s") Duration timeout
) {}
~~~

Unlike JavaBean binding:

- The object is instantiated after the Binder prepares its arguments.
- There is no pre-existing instance with setters and field initializers to "leave untouched" when a value is ignored.
- When a value is ignored, the Binder may have to resolve the missing parameter or build a nested object.
- Constructor or validation logic can still reject the data, even with `ignoreInvalidFields=true`.

Therefore, **do not treat `ignoreInvalidFields=true` on a record as a guarantee that bad values always fall back to `@DefaultValue`**, especially with nested objects or complex structures.

If a specific fallback policy for invalid data is required, implement and test it explicitly in code. For required properties, it is usually better to let conversion fail and report the error.

## 13. Collections, lists, and Maps: ignoring errors can leave configuration inconsistent

Suppose there is a list of endpoints:

~~~yaml
app:
  endpoints:
    - name: primary
      timeout: 5s
    - name: backup
      timeout: invalid
~~~

Java record:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Endpoint> endpoints) {
    public record Endpoint(String name, Duration timeout) {}
}
~~~

The Binder tries to construct `List<Endpoint>`; one element has a wrongly typed timeout.

From this, you cannot naively assume `ignoreInvalidFields=true` will:

- Simply drop the `backup` element.
- Automatically convert `backup`'s timeout to 0.
- Always keep the `backup` element with a default timeout.
- Merge the valid elements with a list in a lower-precedence config file.

None of the above is a **universal contract** across all cases. Ignoring errors can affect binding of part or all of the structure depending on types, converters, and `BindHandler`.

If the endpoint list is critical business configuration, **keep strict binding**, catch the bad element, and fix the input data. If malformed elements from external sources must be tolerated, design a dedicated parsing/validation step with explicit skip or fail rules and tests.

Similarly for `Map<String, Duration>`: a value with a bad unit does not automatically become a valid map entry just because ignore is enabled.

## 14. `ignoreInvalidFields` does not fix broken YAML or rescue all exceptions

Consider syntactically invalid YAML:

~~~yaml
app:
  worker:
    thread-count: [not, closed
~~~

This is a **YAML parsing** problem occurring before properties can be bound to Java. `ignoreInvalidFields` sits on a Java class annotation and plays no role in fixing missing square brackets in a file.

Other scenarios to distinguish:

| Scenario | Is `ignoreInvalidFields` the solution? |
| --- | --- |
| String `abc` bound to `int` | Can affect how the Binder handles conversion errors |
| String `tomorrow` bound to `Duration` | Can affect how the Binder handles conversion errors |
| Malformed YAML file syntax | No |
| Required `spring.config.import` file missing | No; Config Data resolution error |
| Bean needs a missing dependency in the container | No |
| Constructor throws `IllegalArgumentException` for business rules | Cannot expect the ignore flag to suppress it |
| Bean Validation reports invalid configuration | Not the job of the ignore flag |
| Wrong database password | No; typically a connection/auth error at usage time |
| Typo creates a key with no target field | See `ignoreUnknownFields` |
| Converted value succeeds but is blank/invalid per business rules | Use validation or business checks |

Do not use `ignoreInvalidFields=true` as a "keep starting at all costs mode". Failures outside binding can still prevent the application context from starting.

## 15. Are `@Value` and `Environment` affected?

`ignoreInvalidFields` is an attribute **of `@ConfigurationProperties`**. It is not a global switch changing every configuration read.

Example:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WorkerLimits {
    private final int threadCount;

    public WorkerLimits(
            @Value("${app.worker.thread-count:4}") int threadCount) {
        this.threadCount = threadCount;
    }
}
~~~

If the environment provides `app.worker.thread-count=invalid`, converting `invalid` to `int` at the constructor parameter can still fail. Enabling `ignoreInvalidFields=true` on **another configuration class** does not make every `@Value` in the application ignore conversion errors.

Similarly, code:

~~~java
import org.springframework.core.env.Environment;

public int readThreadCount(Environment environment) {
    Integer count = environment.getProperty(
            "app.worker.thread-count", Integer.class, 4);
    return count;
}
~~~

The `Environment#getProperty(...)` API has its own lookup and type-conversion logic; `ignoreInvalidFields` does not apply automatically to every call.

If the goal is merely "read a key, and if absent use a fallback", use a placeholder with default, `Environment#getProperty(key, default)`, or `@DefaultValue` at the right layer. **Wrongly typed values** remain a separate issue from **missing keys**.

## 16. Configuration source precedence still applies

Spring Boot supports multiple configuration sources. For instance, `application.yml`:

~~~yaml
app:
  worker:
    thread-count: 4
~~~

Profile file `application-prod.yml`:

~~~yaml
app:
  worker:
    thread-count: 8
~~~

Environment variable:

~~~bash
APP_WORKER_THREADCOUNT=invalid
~~~

When profile `prod` is active and the environment variable is set, under normal precedence order, the environment variable can be the **selected source** for `app.worker.thread-count`.

This creates a notable situation: the YAML files still contain valid `4` and `8`, yet the winning highest-precedence value is `invalid`.

`ignoreInvalidFields=false` can cause binding to fail. Meanwhile `ignoreInvalidFields=true` **does not mean the Binder walks backward down lower-precedence sources until it finds a valid `int`**.

Do not infer that in this example the result is guaranteed to be `8`. When a value from a higher-precedence source fails conversion, error handling is not equivalent to "falling back to a lower-precedence property source".

The safe fix is correcting or removing the invalid environment variable so valid sources take effect under normal precedence.

## 17. What happens to primitive vs reference types?

With JavaBean binding:

~~~java
@ConfigurationProperties(prefix = "app.limit", ignoreInvalidFields = true)
public class LimitProperties {
    private int maxConnections;
    private Integer retryCount;
    private boolean enabled = true;

    // appropriate getters and setters
}
~~~

Before binding:

- Primitive `int` `maxConnections` has the Java default `0`.
- `Integer` `retryCount` has the value `null`.
- `enabled` is explicitly initialized to `true`.

If the Binder ignores a per-field conversion error, the object **can retain different initial states per field**: `0`, `null`, or `true`.

This is an important risk, because those values can look valid in logs when they are actually the result of failed binding.

Recommended practices:

1. Do not use `0` or `null` as proof that an operator intentionally configured them.
2. If defaults exist, set defaults with **business meaning** and document them clearly.
3. Enforce minimum invariants with validation.
4. If final state differs across versions/binders or sources, write integration tests to lock down expected behavior.
5. For critical configuration, reject bad data rather than silently keeping initial values.

Just because a class has getters and setters does not mean you should turn on ignore.

## 18. Enums and out-of-range values

Suppose the application has an enum:

~~~java
public enum ProcessingMode {
    SAFE,
    FAST,
    AUDIT
}
~~~

Configuration class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.processing")
public class ProcessingProperties {
    private ProcessingMode mode = ProcessingMode.SAFE;

    public ProcessingMode getMode() {
        return mode;
    }

    public void setMode(ProcessingMode mode) {
        this.mode = mode;
    }
}
~~~

Configuration file:

~~~yaml
app:
  processing:
    mode: FAST
~~~

The Binder can convert `FAST` to `ProcessingMode.FAST`.

However, `mode=UNKNOWN` is not in the enum. By default, conversion fails. With `ignoreInvalidFields=true`, the error may be ignored and the JavaBean left with `SAFE` under suitable conditions.

If `SAFE` is truly a designed fallback, that decision might suit a non-critical feature. Yet in a payment or data-processing system, silently reverting an invalid mode to `SAFE` can alter behavior without the deployer knowing.

Consider:

- Keeping strict binding.
- Documenting valid enum values.
- Using validation if extra conditions apply.
- Writing tests for unsupported mode values.
- Allowing fallback only if it is an agreed requirement, not a temporary workaround.

## 19. Where to look when binding errors occur?

When the application stops because binding failed, logs typically identify:

- **Prefix** of `@ConfigurationProperties`, e.g., `app.worker`.
- Specific **property name**, e.g., `app.worker.thread-count`.
- Input **value** if appropriate and not masked by policy.
- **Target type** such as `int` or `Duration`.
- **Configuration source** if the source provides origin metadata.
- **Cause** of conversion or validation failure.

Illustrative example, not a fixed log format across all versions:

~~~text
Failed to bind properties under 'app.worker.thread-count'
to int:

Property: app.worker.thread-count
Value: "lots"
Origin: class path resource [application.yml]
Reason: failed to convert java.lang.String to int
~~~

Diagnostic workflow:

1. Confirm which bean and `prefix` are binding.
2. Check the canonical key name (usually kebab-case).
3. Identify the **final configuration source** supplying the value, including env vars and CLI.
4. Check the target Java type, e.g., `Duration` needs a valid duration string.
5. Fix bad data instead of immediately turning on ignore.
6. If ignore is intentionally used, verify the **resulting value** after ignoring with a specific test.
7. Ensure validation still guards required constraints.

If using Spring Boot Actuator, the `env` and `configprops` endpoints can help locate property sources/values when enabled. Restrict access and avoid exposing secrets.

## 20. When to keep strict binding in production?

The following properties usually require strict handling:

| Config group | Example | Risk if wrong type is ignored |
| --- | --- | --- |
| Resources | `app.worker.thread-count` | Too few or too many workers, unpredictable performance |
| Timeout | `app.gateway.timeout` | Requests hang too long or fail prematurely |
| Retry count | `app.retry.max-attempts` | Unintended load on downstream services |
| Security | `app.security.session-ttl` | Authentication lifetimes violate policy |
| Payload limits | `app.upload.max-size` | Accepts oversized requests or blocks valid ones |
| Feature flags | `app.payment.enabled` | Feature enabled/disabled incorrectly |
| Connection pool | `app.database.max-connections` | Wastes resources or bottlenecks connections |

For most **operationally meaningful** configuration, the default `ignoreInvalidFields=false` is more reliable. Wrong types produce clear startup failures, matching the **fail fast** principle.

`ignoreInvalidFields=true` can be considered when several conditions are met:

- The configuration field is genuinely non-essential.
- Defaults/initial values are safely designed.
- Tests verify the resulting object under bad data.
- Alerts or observability exist to flag that configuration was ignored.
- Ignoring it creates no security gap, data corruption, or SLA breach.

Do not use this flag to paper over widespread typos in production environment variables.

## 21. Another strategy: explicit defaults and validation

Instead of relaxing binding, use intentional defaults:

~~~yaml
app:
  worker:
    thread-count: "${WORKER_COUNT:4}"
    timeout: "${WORKER_TIMEOUT:5s}"
~~~

This handles the **missing environment variable** case: when `WORKER_COUNT` is absent, `4` is used. But if `WORKER_COUNT=invalid` exists, `${WORKER_COUNT:4}` still resolves to `invalid`, failing at bind time.

That is helpful behavior: an absent env var uses a default, while a wrongly typed env var is **an error to fix**.

Another way with constructor binding:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") int threadCount,
        @DefaultValue("5s") Duration timeout
) {}
~~~

`@DefaultValue` defines a default when the parameter is not configured. It is likewise not a tool that automatically replaces every wrongly typed value.

When strong constraints are needed, combine `@Validated` with appropriate constraints. This separates:

- Missing value with a safe default.
- Present valid value.
- Present wrongly typed value.
- Rightly typed value violating business rules.

These four states should not be collapsed into a single "just use the default" branch.

## 22. Testing with Spring Boot `ApplicationContextRunner`

Spring Boot Test's `ApplicationContextRunner` is handy for running a small application context with chosen property values and observing bean creation.

Example testing strict binding behavior:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfig {}

    @Test
    void invalidIntegerShouldFailWhenBindingIsStrict() {
        runner.withPropertyValues(
                "app.worker.thread-count=not-a-number"
        ).run(context -> assertThat(context).hasFailed());
    }
}
~~~

With `WorkerProperties` defaulting to `ignoreInvalidFields=false`, this test locks down the requirement "wrongly typed input must fail the context".

To test a JavaBean type allowing ignore, create a separate class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public class LenientWorkerProperties {

    private int threadCount = 4;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class LenientWorkerPropertiesBindingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(LenientWorkerProperties.class)
    static class TestConfig {}

    @Test
    void checkResultAfterInvalidPropertyWasIgnored() {
        new ApplicationContextRunner()
                .withUserConfiguration(TestConfig.class)
                .withPropertyValues(
                        "app.worker.thread-count=not-a-number"
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    LenientWorkerProperties props =
                            context.getBean(LenientWorkerProperties.class);
                    assertThat(props.getThreadCount()).isEqualTo(4);
                });
    }
}
~~~

This example illustrates **how to test a specific JavaBean's behavior**; it does not mean every binding, constructor, or list error yields the same result. If a test fails on real configuration, investigate rather than changing expectations to mask the error.

Common test dependencies include `spring-boot-starter-test` in test scope, depending on your project build setup.

## 23. Tests distinguishing missing, invalid, and unknown

A solid test suite should cover at least these categories:

| Case | Input data | What to assert |
| --- | --- | --- |
| Valid | `thread-count=8` | Final value is 8 |
| Missing | No `thread-count` | Is any default applied? |
| Wrong type | `thread-count=lots` | Does strict binding fail? |
| No Java field | `new-flag=true` | How is an unknown field handled per config? |
| Right type, invalid value | `thread-count=-2` | Does validation reject it? |
| Overridden by higher source | YAML 8, env `invalid` | Is the final offending source caught? |
| Nested/list wrong type | `endpoints[1].timeout=bad` | How is the entire structure handled? |

You do not need dozens of tests for every property, but for operationally significant settings, include representative tests for **missing values, wrongly typed values, and valid values**.

Especially if the project permits `ignoreInvalidFields=true`, tests become even more crucial because the app can keep running without surfacing an immediate startup error.

## 24. Common misconceptions

| Misconception | Accurate explanation |
| --- | --- |
| "`ignoreInvalidFields=true` makes every bad value valid." | It can ignore certain binding errors; bad values are not converted into valid types. |
| "Enabling ignore means using the value from a lower-precedence YAML." | There is no guarantee of falling back across property sources when a higher source fails conversion. |
| "`ignoreInvalidFields` and `ignoreUnknownFields` are the same." | One relates to invalid binding; the other relates to unbindable property names. |
| "A missing key is also an invalid field." | A missing property is a separate case needing defaults, nullability, or validation. |
| "`ignoreInvalidFields` replaces Bean Validation." | It does not enforce rules like positive numbers or valid URLs. |
| "As long as a JavaBean has field initializers, every error is safe." | Defaults may not suit the environment, and other errors can still occur. |
| "Enabling ignore fixes syntactically broken YAML." | The YAML parser must read the file successfully before the Binder operates. |
| "`@Value` automatically obeys the ignore flag on another `@ConfigurationProperties`." | This is not a global option across all configuration-reading paths. |
| "With a record, ignore always keeps `@DefaultValue`." | Constructor binding has different semantics from JavaBeans; do not assume. |
| "Application starts successfully means configuration is right." | Wrong values may have been ignored, or business errors may appear later. |

## 25. Self-check exercises

### Exercise 1 — Wrongly typed value

File:

~~~properties
app.retry.max-attempts=abc
~~~

Class:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public class RetryProperties {
    private int maxAttempts = 3;

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
~~~

Question: With `@ConfigurationProperties` defaults, how should the Binder handle this?

**Answer:** `ignoreInvalidFields=false` by default, so converting `abc` to `int` usually causes binding to fail and report an error. An initial value of `3` does not mean errors are ignored.

### Exercise 2 — Enabling ignore

Add:

~~~java
@ConfigurationProperties(
        prefix = "app.retry",
        ignoreInvalidFields = true
)
~~~

With the JavaBean class from Exercise 1, what outcome can be observed?

**Answer:** the conversion error may be ignored, and the `maxAttempts` field initialized to `3` may be preserved. Test the specific bean; do not generalize across all data types and constructor-binding setups.

### Exercise 3 — Unknown or invalid?

The class only has `int maxAttempts`. YAML:

~~~yaml
app:
  retry:
    max-attempts: 5
    max-extra: true
~~~

Question: `max-extra` has no matching field, so which category does it fall into?

**Answer:** unknown/unbound property. It relates to `ignoreUnknownFields` rather than `ignoreInvalidFields`.

### Exercise 4 — Right type, violates business rules

With `thread-count=-5` and Java `int threadCount`, does enabling `ignoreInvalidFields=true` automatically ensure a positive thread count?

**Answer:** no. `-5` converts to `int`, so it is not a conversion error. Use `@Min(1)` with validation or an explicit check in code.

### Exercise 5 — File error vs binding error

An `application.yml` file is missing a YAML bracket and the application fails to start. Does adding `ignoreInvalidFields=true` fix it?

**Answer:** no. This is a file parsing error before the Binder has data to bind to the class.

### Exercise 6 — Wrong value from an environment variable

Profile file `application-prod.yml` has `app.worker.thread-count=8`, yet the environment supplies `APP_WORKER_THREADCOUNT=invalid`. Why can't you conclude that enabling ignore makes `threadCount` equal `8`?

**Answer:** environment variables normally take precedence over Config Data. The ignore flag is not an algorithm that searches lower sources for a valid value. Fix or remove the bad variable and verify behavior in a test.

### Exercise 7 — Defaults by binding style

A record:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
        @DefaultValue("3") int maxAttempts
) {}
~~~

When `app.retry.max-attempts` is absent, what is the expected value? What if `abc` is supplied?

**Answer:** when missing, the default `3` can apply. When `abc` is supplied, that is a conversion error; `@DefaultValue` is not a tool that automatically replaces invalid values.

## 26. Key takeaways

- `@ConfigurationProperties(ignoreInvalidFields = true)` tells the Binder to **ignore invalid-value errors that the binding mechanism allows ignoring**; the default is **`false`**.
- Wrong type (`"abc"` into `int`) differs from an unknown field (no matching Java property) and from a missing key.
- `ignoreUnknownFields` is a separate flag; its default is normally **`true`**.
- With JavaBean binding, an ignored field **can retain its initialized value** such as `4`, `false`, or `null`; that does not guarantee business correctness.
- Constructor binding, records, collections, and nested objects have different semantics; do not assume identical fallback results.
- **Rightly typed values can still violate business rules**: use Bean Validation or invariant checks.
- `ignoreInvalidFields` does not fix broken YAML syntax, missing Config Data, replace `@Value`/`Environment`, or guarantee startup succeeds.
- When a higher-precedence environment variable contains invalid data, do not expect ignore to fall back to a lower-precedence file.
- **Production should usually keep strict binding and fail fast** for critical operational values.
- If choosing to ignore errors on a non-essential field, ensure safe defaults, tests demonstrating behavior, and reasonable observability.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
