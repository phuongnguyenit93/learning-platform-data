# Handling BindResult and Missing Data Cases in Spring Boot Binder

## 1. Why Do We Need a "Data Present / No Data" Result?

When a Spring Boot application reads configuration, not every property group is required to appear. For example:

- A report export feature may only be configured in the production environment.
- A connection to an external service may be optional.
- A list of secondary servers may not be declared on a personal machine.
- A configuration group may be supplied via `application.yaml`, environment variables, or command line; in some runs, no source contains that group.

Suppose the application has:

~~~yaml
app:
  primary:
    endpoint: https://primary.example.test
~~~

But there are **no** keys starting with `app.secondary`.

If Java code tries to bind `app.secondary` to a record, we must distinguish:

1. No matching data to bind: the secondary feature can be disabled, use defaults, or report missing configuration per policy.
2. Data exists and binds successfully: use the type-converted value.
3. Data exists but has the wrong type or cannot be bound: this is a configuration error, **not** an "undeclared" case.

Spring Boot provides `Binder` and `BindResult<T>` to make that distinction.

Conceptual example:

~~~java
Binder binder = Binder.get(environment);

BindResult<SecondaryProperties> result =
        binder.bind("app.secondary", SecondaryProperties.class);

if (result.isBound()) {
    SecondaryProperties properties = result.get();
    // Use secondary configuration.
} else {
    // No configuration for the secondary group.
}
~~~

Note: `SecondaryProperties` is an application-defined Java type; full examples will appear in later sections.

**Lesson objectives:**

- Understand how `Binder.bind(...)` returns `BindResult<T>`.
- Know how to use `isBound()`, `get()`, `orElse()`, `orElseGet()`, `orElseThrow()`, `ifBound()`, and `map()`.
- Choose an appropriate policy when the source has no data.
- Avoid confusing "unbound" with conversion errors, validation errors, empty configuration, or a partially bound object.
- Distinguish `bind(...)` from `bindOrCreate(...)`.
- Know how to bind typed collections and how to test results with `MapConfigurationPropertySource`.
- Know when to use programmatic Binder and when to let Spring Boot's `@ConfigurationProperties` manage it.

## 2. What Is Binder and at Which Layer Does It Operate?

`org.springframework.boot.context.properties.bind.Binder` is Spring Boot's API for binding `ConfigurationPropertySource` entries into a desired Java type.

It performs tasks such as:

- Looking up configuration keys by prefix.
- Applying relaxed binding rules to property names.
- Retrieving values from the relevant configuration sources.
- Resolving placeholders when configured to support them.
- Converting strings/numbers to `Duration`, `DataSize`, `URI`, `Enum`, lists, maps, or structured objects.
- Creating or updating the target object using the appropriate binding mechanism.
- Returning a stateful result rather than forcing the caller to always receive an object.

With a started Spring Boot application, the familiar way to obtain it is:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

Binder binder = Binder.get(environment);
~~~

`Binder.get(Environment)` constructs a binder from an `Environment` that Spring Boot has prepared and attached appropriate `ConfigurationPropertySource` instances to. For an `Environment` created manually outside Boot's flow, ensure configuration sources are properly attached; in standalone tests, it is simpler to construct a binder from `MapConfigurationPropertySource`.

### Processing flow

~~~text
application.yaml / application-prod.yaml
system environment / Java System properties
--key=value and other PropertySources
                   |
                   v
       Environment / configuration sources
                   |
                   v
        Binder.bind("app.secondary",
                    SecondaryProperties.class)
                   |
          +--------+---------+
          |                  |
          v                  v
   Matching data found    No data to bind
   and bindable           the target
          |                  |
          v                  v
  BindResult bound     BindResult unbound
          |
          +---- if conversion/binding fails ----> Exception
~~~

Avoid mistakenly inferring that `BindResult` is "a box that always holds an error when the process fails." It primarily represents **a result with or without a bound value**. A normal binding error can still be thrown directly from the `bind(...)` call.

## 3. Basic bind Call

An example with data:

~~~properties
report.timeout=15s
~~~

Code:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public final class ReportConfigReader {

    private final Binder binder;

    public ReportConfigReader(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public Duration timeout() {
        BindResult<Duration> result =
                binder.bind("report.timeout", Duration.class);

        return result.orElse(Duration.ofSeconds(5));
    }
}
~~~

When `report.timeout=15s` is active:

~~~text
result.isBound() = true
result.get() = PT15S
timeout() = PT15S
~~~

If `report.timeout` does not exist in relevant sources:

~~~text
result.isBound() = false
timeout() = PT5S
~~~

The 5-second value comes from `orElse(Duration.ofSeconds(5))`, **not a value guessed by Spring Boot**.

### Three conceptual parts

~~~java
binder.bind("report.timeout", Duration.class)
            |               |
            |               +-- target type
            +------------------ configuration name to bind
~~~

- Property names should be written in canonical lowercase kebab-case, dot-separated.
- The target type determines the conversion rules.
- The result is `BindResult<Duration>`, not `Duration` directly.

If you only need a single key and do not need bound/unbound status, `Environment.getProperty(...)` may suffice. When handling a structured object or collection and controlling absence policies, `BindResult` expresses intent more clearly.

## 4. BindResult<T> Is Not Optional<T>

`BindResult<T>` is a dedicated Spring Boot class:

~~~java
org.springframework.boot.context.properties.bind.BindResult<T>
~~~

It resembles `Optional<T>` in some operations, but **it is not `java.util.Optional<T>`** and cannot be assigned directly:

~~~java
// Wrong type:
Optional<Duration> result =
        binder.bind("report.timeout", Duration.class);
~~~

Correct form:

~~~java
BindResult<Duration> result =
        binder.bind("report.timeout", Duration.class);
~~~

Main API table in Spring Boot 3.x:

| Method | Meaning when bound | Meaning when unbound |
| --- | --- | --- |
| `isBound()` | Returns `true`. | Returns `false`. |
| `get()` | Returns the bound object. | Throws `NoSuchElementException`. |
| `orElse(other)` | Returns the bound object. | Returns `other`. |
| `orElseGet(supplier)` | Returns the bound object without calling supplier. | Calls supplier and returns its result. |
| `orElseThrow(supplier)` | Returns the bound object. | Throws the exception created by supplier. |
| `ifBound(consumer)` | Runs consumer with the value. | Does nothing. |
| `map(function)` | Applies function to the value and returns a new `BindResult`. | Remains unbound without calling function. |

How you handle it should be based on the **business meaning** of missing configuration: acceptable, defaulted, or fail startup.

## 5. isBound(): Checking Before Retrieving the Value

Example:

~~~java
BindResult<String> result =
        binder.bind("app.region", String.class);

if (result.isBound()) {
    String region = result.get();
    System.out.println("Configured region: " + region);
} else {
    System.out.println("app.region is not declared");
}
~~~

Here `isBound()` prevents calling `get()` on an empty result.

If YAML has:

~~~yaml
app:
  region: apac
~~~

then `isBound()` is true and `get()` returns `apac`.

If YAML has no `app.region` and no other source provides it, the result is unbound.

### Do not confuse with a Boolean check

Suppose:

~~~properties
feature.export.enabled=false
~~~

And:

~~~java
BindResult<Boolean> result =
        binder.bind("feature.export.enabled", Boolean.class);
~~~

When `false` is bound successfully:

~~~text
result.isBound() = true
result.get() = false
~~~

**A Boolean false value is present data, not an unbound state.**

Similarly:

~~~properties
app.retry-count=0
~~~

when bound successfully to `Integer`, the result is **bound with value 0**, not unbound.

Do not write:

~~~java
if (Boolean.TRUE.equals(result.orElse(false))) {
    // ...
}
~~~

and assume the false branch indicates the property is absent. It conflates two distinct cases: no configuration vs. the operator explicitly disabled the feature.

## 6. get(): Use Only When There Is Evidence the Value Exists

`BindResult.get()` returns the bound object, but **throws `NoSuchElementException` if there is no value**.

Unsafe example:

~~~java
Duration timeout =
        binder.bind("remote.timeout", Duration.class)
                .get();
~~~

If `remote.timeout` does not exist, the code throws an exception. That may be intentional if you want the app to fail, but the default exception message rarely expresses the business requirement clearly.

When missing configuration is a domain-specific error, use:

~~~java
Duration timeout =
        binder.bind("remote.timeout", Duration.class)
                .orElseThrow(() -> new IllegalStateException(
                        "Missing required configuration remote.timeout"));
~~~

When you want to check and then handle multiple branches:

~~~java
BindResult<Duration> result =
        binder.bind("remote.timeout", Duration.class);

if (!result.isBound()) {
    throw new IllegalStateException(
            "remote.timeout is not configured");
}

Duration timeout = result.get();
~~~

The first approach is shorter; the second works well when you need extra logging, state setup, or multi-branch handling.

**Do not catch `NoSuchElementException` from `get()` as a default control-flow mechanism** when `isBound()` and `orElseThrow()` with clear messages already exist.

## 7. orElse(): Simple Fallback Value

The most common case: optional configuration with a clear default.

~~~java
Duration retryDelay =
        binder.bind("jobs.retry-delay", Duration.class)
                .orElse(Duration.ofMillis(250));
~~~

With:

~~~properties
jobs.retry-delay=2s
~~~

the result is `Duration.ofSeconds(2)`.

Without `jobs.retry-delay`, `Duration.ofMillis(250)` is used.

### Note: orElse only applies when BindResult is unbound

Suppose:

~~~properties
jobs.retry-delay=0ms
~~~

Binder can produce a valid `Duration.ZERO`. Because it is bound, `orElse(Duration.ofMillis(250))` **does not replace 0 with the default**.

If 0 is disallowed by business rules, separate validation is needed:

~~~java
Duration delay =
        binder.bind("jobs.retry-delay", Duration.class)
                .orElse(Duration.ofMillis(250));

if (delay.isZero() || delay.isNegative()) {
    throw new IllegalArgumentException(
            "jobs.retry-delay must be greater than 0");
}
~~~

Separate the two questions:

- Key not declared → default can be used.
- Key declared with an out-of-range value → report a validation error.

### Eagerly evaluated fallback value

In Java:

~~~java
ServiceOptions value = result.orElse(createDefaultOptions());
~~~

`createDefaultOptions()` is evaluated **before** `orElse(...)` receives the argument, even when `result` is already bound.

This is harmless for a simple `Duration.ofSeconds(5)`, but if creating the default is expensive, hits files/network, or has side effects, use `orElseGet(...)`.

## 8. orElseGet(): Create the Fallback Value Only When Truly Needed

~~~java
ServiceOptions options =
        binder.bind("service.backup", ServiceOptions.class)
                .orElseGet(() -> loadLocalDefaultOptions());
~~~

`loadLocalDefaultOptions()` is only called if binding yielded no value.

Example record:

~~~java
import java.time.Duration;

public record ServiceOptions(
        String endpoint,
        Duration timeout) {
}
~~~

Default value:

~~~java
private ServiceOptions defaultOptions() {
    return new ServiceOptions(
            "http://localhost:8089",
            Duration.ofSeconds(3));
}
~~~

Usage:

~~~java
ServiceOptions options =
        binder.bind("service.backup", ServiceOptions.class)
                .orElseGet(this::defaultOptions);
~~~

Comparison:

| Usage | When bound | When unbound |
| --- | --- | --- |
| `orElse(defaultOptions())` | Still calls `defaultOptions()` and discards result. | Calls and uses default. |
| `orElseGet(this::defaultOptions)` | Does not call `defaultOptions()`. | Calls and uses default. |

Prefer `orElseGet` if the default has a cost or requires initialization logic. However, **do not perform network calls inside a configuration fallback supplier** unless you have a very clear requirement and error handling; configuration defaults should generally be deterministic and independent of external connectivity.

## 9. orElseThrow(): Required Configuration

Some parameters should never have an arbitrary default. For example, a payment service URL:

~~~java
URI paymentEndpoint =
        binder.bind("payment.endpoint", URI.class)
                .orElseThrow(() -> new IllegalStateException(
                        "payment.endpoint is a required configuration"));
~~~

When no bound data exists, the application reports a business-meaningful error.

When valid data exists:

~~~properties
payment.endpoint=https://payment.example.test
~~~

Binder converts it to `URI` and returns it via `orElseThrow(...)` without invoking the exception supplier.

### Important note on conversion errors

If the configuration is:

~~~properties
jobs.max-attempts=abc
~~~

and the code runs:

~~~java
int attempts =
        binder.bind("jobs.max-attempts", Integer.class)
                .orElseThrow(() -> new IllegalStateException(
                        "Missing jobs.max-attempts"));
~~~

The error is **not** "missing jobs.max-attempts": the key is present, but `abc` cannot be converted to `Integer`. Binder typically throws a binding error, such as `BindException`, **before** you even receive a `BindResult` on which to call `orElseThrow(...)`.

Therefore, do not view `orElseThrow` as handling all data errors. It handles the **unbound result**, not replacing conversion/validation error reporting.

## 10. ifBound(): Perform an Action Only When Configuration Exists

~~~java
binder.bind("diagnostics.label", String.class)
        .ifBound(label -> System.out.println(
                "Label: " + label));
~~~

If `diagnostics.label` is not declared, the consumer does not run.

This is useful when:

- There is an optional display label.
- A configuration value triggers a secondary setup step.
- You want to add behavior when a property is present without needing an `else` branch.

Example in an `ApplicationRunner`:

~~~java
@Override
public void run(ApplicationArguments args) {
    Binder binder = Binder.get(environment);

    binder.bind("app.startup-note", String.class)
            .ifBound(note ->
                    System.out.println("Startup note: " + note));
}
~~~

Do not use `ifBound` as a way to hide the absence of required configuration. If `app.startup-note` is truly required, `orElseThrow` makes that requirement explicit.

### ifBound does not start a "watcher"

`ifBound` executes the consumer **only at call time**. It does not subscribe to YAML file changes, does not rerun when environment variables change, and does not auto-reload configuration while the application runs.

## 11. map(): Transform a Value When Binding Succeeds

`BindResult.map(...)` can transform a `BindResult<T>` into a `BindResult<U>`.

Example:

~~~java
BindResult<Integer> retryLimit =
        binder.bind("jobs.retry-limit", Integer.class);

BindResult<String> description =
        retryLimit.map(value -> "Limit: " + value);
~~~

If `jobs.retry-limit=5`:

~~~text
retryLimit.isBound() = true
description.isBound() = true
description.get() = "Limit: 5"
~~~

If there is no configuration:

~~~text
retryLimit.isBound() = false
description.isBound() = false
~~~

The function is not called in the unbound case.

A concise pattern:

~~~java
String description =
        binder.bind("jobs.retry-limit", Integer.class)
                .map(value -> "Limit: " + value)
                .orElse("Using default policy");
~~~

`map` is useful when you want to enrich a bound value before deciding on a fallback.

**Note:** `map` is not an error handler for Binder conversion failures. If `retry-limit=abc` and integer binding fails, the function gets no chance to "fix" that data via `map`.

## 12. Summary of Ways to Handle a Key

Suppose:

~~~java
BindResult<Duration> result =
        binder.bind("client.timeout", Duration.class);
~~~

| Business requirement | Appropriate code |
| --- | --- |
| Only want to know if data exists | `result.isBound()` |
| Already certain data exists | `result.get()` |
| Simple default | `result.orElse(Duration.ofSeconds(5))` |
| Need to construct default when missing | `result.orElseGet(this::defaultTimeout)` |
| Required configuration | `result.orElseThrow(() -> new IllegalStateException("..."))` |
| Run an action only if present | `result.ifBound(this::useTimeout)` |
| Transform to descriptive type then default | `result.map(Duration::toString).orElse("unspecified")` |

Do not write a long `if/else` chain just because you haven't used `BindResult`'s built-in API. Conversely, do not cram every business policy into an overly long one-line chain that makes error messages and validation logic hard to read.

## 13. Four Distinct States: Missing, Empty, Special Value, Invalid Data

This is the most critical part of handling "no data".

### State A — property does not exist

~~~properties
# No jobs.enabled in any source
~~~

~~~java
BindResult<Boolean> result =
        binder.bind("jobs.enabled", Boolean.class);
~~~

When no matching key exists, the result is normally unbound.

### State B — Boolean false or number 0 present

~~~properties
jobs.enabled=false
jobs.retry-count=0
~~~

This is valid, present data. Binder can convert them into `Boolean.FALSE` and `Integer.valueOf(0)`.

~~~text
isBound() = true
get() = false or 0
~~~

Do not use a condition like `if (result.orElse(false))` to infer whether **the operator supplied the key**.

### State C — empty string

~~~properties
jobs.label=
~~~

If bound to `String`, an empty string can be a bound value. If bound to another type, an empty string may convert differently or cause issues depending on the converter.

Therefore, **"key present with empty string" should not automatically be treated as "no data source"**. When a string must have content:

~~~java
String label = binder.bind("jobs.label", String.class)
        .orElseThrow(() -> new IllegalStateException(
                "Missing jobs.label"));

if (label.isBlank()) {
    throw new IllegalStateException(
            "jobs.label must not be blank");
}
~~~

### State D — data present but cannot be converted

~~~properties
jobs.retry-count=abc
~~~

~~~java
binder.bind("jobs.retry-count", Integer.class);
~~~

This is a binding/conversion error. `orElse(3)` **does not mean** "if the operator typed the wrong type, silently use 3."

### Inference table

| Source | Target type | Handling direction |
| --- | --- | --- |
| No `jobs.enabled` | `Boolean` | Unbound; choose default or report missing. |
| `jobs.enabled=false` | `Boolean` | Bound with false. |
| `jobs.retry-count=0` | `Integer` | Bound with 0. |
| `jobs.label=` | `String` | Check blankness per business policy. |
| `jobs.retry-count=abc` | `Integer` | Conversion/binding error, not fallback due to absence. |
| `jobs.timeout=5s` | `Duration` | Bound if converter supports it, as 5 seconds. |

Conclusion: `BindResult.isBound()` answers **"was a result bound?"**, not **"is that value sensible for the application?"**.

## 14. When the Entire Prefix Is Absent

Consider the record:

~~~java
package com.example.demo.config;

import java.time.Duration;

public record ExportOptions(
        boolean enabled,
        String outputDirectory,
        Duration timeout) {
}
~~~

Code:

~~~java
BindResult<ExportOptions> result =
        binder.bind("feature.export", ExportOptions.class);
~~~

The current sources only have:

~~~yaml
feature:
  notifications:
    enabled: true
~~~

No keys belong to `feature.export.*`.

In normal binding, `result` is unbound. Handling depends on business logic:

**Optional export feature:**

~~~java
ExportOptions options = result.orElseGet(() ->
        new ExportOptions(
                false,
                "./out",
                Duration.ofSeconds(10)));
~~~

**Required export feature:**

~~~java
ExportOptions options = result.orElseThrow(
        () -> new IllegalStateException(
                "Missing feature.export configuration group"));
~~~

**Initialize a component only if configured:**

~~~java
result.ifBound(options ->
        System.out.println("Export config: " + options));
~~~

### Be careful with prefix names

`feature.export` is a namespace. Having `feature.enabled` or `feature.notifications.enabled` **does not mean** the `feature.export` group was supplied.

For nested objects, Binder examines paths under the target group. Do not rely on the existence of a similar-looking key to conclude the group was bound.

## 15. When Partial Data Exists: Bound Does Not Mean Every Field Is Populated

Suppose the source only has:

~~~yaml
feature:
  export:
    enabled: true
~~~

While the target type is:

~~~java
public record ExportOptions(
        boolean enabled,
        String outputDirectory,
        Duration timeout) {
}
~~~

Binder can create an `ExportOptions` object once it finds data for `enabled`. Because `output-directory` and `timeout` have no values, reference members can receive `null` under constructor binding.

Therefore:

~~~java
BindResult<ExportOptions> result =
        binder.bind("feature.export", ExportOptions.class);
~~~

can return **bound** even though the object **does not yet have enough data for the export workflow**.

And:

~~~java
ExportOptions options = result.orElseGet(() ->
        new ExportOptions(
                false, "./out", Duration.ofSeconds(10)));
~~~

will **not** use the default because `result` is already bound via `enabled=true`. It does not take the fallback to fill in missing individual fields of an already created object.

This is the biggest mistake to avoid when applying fallbacks to an **entire configuration group**.

### Two levels of missing data

1. **Entire group missing:** target cannot be bound → `BindResult` unbound.
2. **Group has a few properties:** object can be bound → `BindResult` bound, yet some members remain missing/defaulted.

These two levels must be handled separately.

### When per-field defaults are needed

You can use `@DefaultValue` in constructor binding:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.bind.DefaultValue;

public record ExportOptions(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("./out") String outputDirectory,
        @DefaultValue("10s") Duration timeout) {
}
~~~

With proper registration and binder supporting constructor binding, `@DefaultValue` supplies defaults for missing members when constructing the object.

Key distinction:

- `@DefaultValue` on **constructor/record components**: field/parameter-level default when binder constructs the object.
- `BindResult.orElse(...)`: default for the **entire result**, only when no target value was bound.

Even when using `@DefaultValue` on members, still define a policy for when the **entire prefix has no data**; do not assume field-level defaults always force Binder to create an object if the whole group is absent.

## 16. JavaBean Defaults and the Binding Mechanism

With a mutable class:

~~~java
import java.time.Duration;

public class ExportOptions {

    private boolean enabled = false;
    private String outputDirectory = "./out";
    private Duration timeout = Duration.ofSeconds(10);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getOutputDirectory() {
        return outputDirectory;
    }

    public void setOutputDirectory(String outputDirectory) {
        this.outputDirectory = outputDirectory;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

If Binder constructs and populates the mutable instance via JavaBean binding, initial field values can be preserved for properties that do not appear. This is an object-level way to provide defaults.

However, distinguish:

- JavaBean field initializers: defaults **inside the object when instantiated**.
- `orElseGet(() -> new ExportOptions())`: default **when the bind result is completely unbound**.
- `bindOrCreate(...)`: direct API asking to return a bound instance or create one if there is no result.

A solid model clearly states when absent configuration is allowed and which fields are required.

## 17. bindOrCreate(): Bind If Possible, Otherwise Create New

`Binder` also has:

~~~java
<T> T bindOrCreate(String name, Class<T> target);
~~~

Example with a JavaBean that has a no-arg constructor like `ExportOptions` above:

~~~java
ExportOptions options =
        binder.bindOrCreate("feature.export", ExportOptions.class);
~~~

If sources provide matching keys, Binder binds as usual. If the bind result is `null`, the method attempts to instantiate a new instance of the target type.

Compare:

~~~java
BindResult<ExportOptions> result =
        binder.bind("feature.export", ExportOptions.class);
~~~

and:

~~~java
ExportOptions options =
        binder.bindOrCreate("feature.export", ExportOptions.class);
~~~

| Call | Return type | When no data exists |
| --- | --- | --- |
| `bind(name, type)` | `BindResult<T>` | Unbound; caller chooses policy. |
| `bindOrCreate(name, type)` | `T` | Attempts to create a new instance of the type. |

### When does bindOrCreate make sense?

When a type can be safely instantiated with its own defaults, such as a JavaBean with a default constructor:

~~~java
public class OptionalCacheSettings {
    private boolean enabled = false;
    private int capacity = 100;

    public OptionalCacheSettings() {
    }

    // getters / setters
}
~~~

`bindOrCreate("cache.optional", OptionalCacheSettings.class)` is a way to always obtain a settings object if instantiation succeeds.

### Important limitations

- Not every type can be created when configuration is absent. An immutable class with required constructor arguments, an interface, or an abstract type may have no suitable instantiation path; the operation can fail.
- `bindOrCreate` does not guarantee an object satisfies all business constraints. It primarily addresses whether an instance exists.
- It does not convert **mistyped** configuration values into a default object; bind errors must still be handled as errors.
- If you need to distinguish "undeclared" from "declared", `bind(...)` and `BindResult.isBound()` are more transparent.

Do not replace all `bind(...)` calls with `bindOrCreate(...)` just to avoid handling absent-data branches. Always creating an object can cause the application to overlook a configuration group that should have been mandatory.

## 18. Strategies for Handling Missing Data by Feature Nature

Suppose there is configuration for an external monitoring service:

~~~text
monitoring.remote.*
~~~

There are three main strategies.

### 18.1. Optional feature: skip when unconfigured

~~~java
BindResult<RemoteMonitorProperties> result =
        binder.bind("monitoring.remote",
                RemoteMonitorProperties.class);

if (!result.isBound()) {
    System.out.println(
            "Remote monitoring is not configured");
    return;
}

RemoteMonitorProperties config = result.get();
startRemoteMonitor(config);
~~~

The application does not need to start a remote connection if configuration is completely absent.

### 18.2. Feature with safe default: use fallback

~~~java
RemoteMonitorProperties config =
        binder.bind("monitoring.remote",
                RemoteMonitorProperties.class)
                .orElseGet(this::localMonitorDefaults);
~~~

This applies when a valid default design exists, such as local monitoring or disabled mode.

### 18.3. Required feature: fail fast

~~~java
RemoteMonitorProperties config =
        binder.bind("monitoring.remote",
                RemoteMonitorProperties.class)
                .orElseThrow(() -> new IllegalStateException(
                        "monitoring.remote is a required configuration"));
~~~

When configuration is necessary for the system to function properly, failing fast is safer than substituting a fake URL.

### Design questions

Before choosing a method, answer:

1. Without this group, can the application run correctly from a business perspective?
2. Could a default reduce security or send data to the wrong destination?
3. If some fields are present but an essential field is missing, how should the application behave?
4. If a field is configured with the wrong type, should it fail instead of falling back?
5. Should defaults depend on environment/profiles, or be a stable constant?

`BindResult` lets you implement these decisions, but it does not decide for the application.

## 19. A Complete Programmatic Binder Example

Suppose an export module only operates when configured. Object:

~~~java
package com.example.demo.export;

import java.time.Duration;

public record ExportProperties(
        boolean enabled,
        String outputDirectory,
        Duration timeout) {
}
~~~

An `ApplicationRunner` reading from `Environment`:

~~~java
package com.example.demo.export;

import java.time.Duration;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ExportStartupReporter implements ApplicationRunner {

    private final Environment environment;

    public ExportStartupReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        Binder binder = Binder.get(environment);

        BindResult<ExportProperties> result =
                binder.bind("feature.export",
                        ExportProperties.class);

        if (!result.isBound()) {
            System.out.println(
                    "Export module: unconfigured, staying disabled");
            return;
        }

        ExportProperties properties = result.get();

        if (!properties.enabled()) {
            System.out.println(
                    "Export module: configured but disabled");
            return;
        }

        if (properties.outputDirectory() == null
                || properties.outputDirectory().isBlank()) {
            throw new IllegalStateException(
                    "Missing feature.export.output-directory");
        }

        if (properties.timeout() == null
                || properties.timeout().isZero()
                || properties.timeout().isNegative()) {
            throw new IllegalStateException(
                    "feature.export.timeout must be a positive Duration");
        }

        System.out.println(
                "Export module: enabled, directory="
                        + properties.outputDirectory()
                        + ", timeout=" + properties.timeout());

        // Example only illustrates classification and validation.
        // Does not read/write any output files.
    }
}
~~~

Scenarios:

**No `feature.export.*`:**

~~~text
Export module: unconfigured, staying disabled
~~~

**Only:**

~~~properties
feature.export.enabled=false
~~~

then an object can be bound with `enabled=false`; the application recognizes that the operator **declared the configuration but explicitly disabled it**.

**With:**

~~~yaml
feature:
  export:
    enabled: true
    output-directory: ./reports
    timeout: 30s
~~~

then a valid object can be bound and used.

**With:**

~~~yaml
feature:
  export:
    enabled: true
~~~

then the result can be bound yet lack the two reference fields. The Runner checks explicitly and fails clearly rather than assuming `result.isBound()` guaranteed the entire configuration was valid.

### Why didn't the example use a fallback for the whole record?

Because report export is only safe when the required fields have values. Creating a default for the whole record on any omission could cause the application to write data to an unexpected directory or hide a deployment error.

## 20. Moving Defaults Down to Individual Fields with @DefaultValue

If configuration allows some fields to be absent, you can design a record using `@DefaultValue` on constructor parameters:

~~~java
package com.example.demo.export;

import java.time.Duration;

import org.springframework.boot.context.properties.bind.DefaultValue;

public record ExportProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("./reports") String outputDirectory,
        @DefaultValue("30s") Duration timeout) {
}
~~~

Suppose the source has:

~~~yaml
feature:
  export:
    enabled: true
~~~

If Binder constructs the record via constructor binding, the remaining missing members can receive the declared default values.

Points to clarify:

- Once the group has enough data to bind and the object is created, `@DefaultValue` resolves the value of **each missing parameter**.
- If there is completely no data for the prefix, do not assume a record with all defaults will be created by `bind(...)`. If a guaranteed fallback is desired, handle `BindResult` or use `bindOrCreate` for compatible types.
- `@DefaultValue("30s")` provides a **default value**, not the same concept as `@DurationUnit`, which only changes the **default unit of a bare number**.

If a field is truly required when `enabled=true`, it may be better not to give it a default. Instead of masking the requirement with a dummy value, validate when the feature is enabled.

## 21. Collections: Using Bindable to Preserve Element Types

For a List:

~~~properties
app.backends[0]=alpha.example.test
app.backends[1]=beta.example.test
~~~

You want `List<String>`, not a raw `List`.

Use:

~~~java
import java.util.List;

import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;

BindResult<List<String>> result =
        binder.bind(
                "app.backends",
                Bindable.listOf(String.class));
~~~

When elements exist, Binder can construct the corresponding list.

When no data exists:

~~~java
List<String> backends =
        binder.bind("app.backends", Bindable.listOf(String.class))
                .orElseGet(List::of);
~~~

When configuration is absent, you obtain an empty list chosen by the application. This is a fallback evaluated at the **result level**.

### Why not use bind("app.backends", List.class)?

Because `List.class` does not fully describe the element type to convert. `Bindable.listOf(String.class)` tells Binder that `String` is the type of each element.

Similar APIs exist for other collections:

~~~java
Bindable.setOf(String.class);
Bindable.mapOf(String.class, Integer.class);
~~~

With a map:

~~~properties
app.quotas.alpha=5
app.quotas.beta=10
~~~

~~~java
import java.util.Map;

Map<String, Integer> quotas =
        binder.bind(
                "app.quotas",
                Bindable.mapOf(String.class, Integer.class))
                .orElseGet(Map::of);
~~~

### Absent List differs from empty List

- **No source for `app.backends`:** can be unbound; the application uses `List.of()` by policy.
- **Source representing an empty list:** exact behavior depends on source format and conversion/binding rules; do not assume every empty representation behaves identically to an absent prefix.
- **List present with unconvertible element:** that is a binding error, not a default empty list.

Additionally, when multiple `PropertySource` entries define a list, Spring Boot has its own precedence/replacement rules. Do not treat `orElseGet(List::of)` as meaning "merge lists across sources"—those are two separate matters.

## 22. Bindable.ofInstance(): Binding into an Existing Object

Another Binder capability is working with a `Bindable` wrapping an instance:

~~~java
MutableOptions current = new MutableOptions();

BindResult<MutableOptions> result =
        binder.bind(
                "feature.export",
                Bindable.ofInstance(current));
~~~

Assume `MutableOptions` has appropriate getters/setters. This supplies an **existing object** as the target for binding instead of always asking Binder to create a new record.

This is useful when you need control over the updated object, though care is required:

- Mutable objects may be modified during binding.
- Pre-existing defaults on the object and overridden data need a clear contract.
- Absence of data for the group should still be handled via `BindResult` status or explicit policy, rather than assuming the created target becomes bound.
- Do not arbitrarily reuse a shared mutable instance across multiple threads or binding runs.

For ordinary application configuration, a `@ConfigurationProperties` bean or immutable record is usually easier to manage than updating a shared object manually.

## 23. Conversion Errors Are Not Equivalent to Unbound

Example:

~~~properties
server.client.timeout=not-a-duration
~~~

Code:

~~~java
Duration timeout =
        binder.bind(
                "server.client.timeout",
                Duration.class)
                .orElse(Duration.ofSeconds(5));
~~~

You might wish "if it cannot bind, use 5 seconds." Yet here **the data actually exists and has invalid syntax**, so Binder typically throws `BindException` or a related binding error.

`orElse` is not guaranteed to run when that exception occurs.

This is a good behavior to keep for critical configurations. If mistyped values were silently ignored, the system could run with a completely unexpected timeout.

### Explicit error handling when genuinely needed

~~~java
try {
    return binder.bind(
            "server.client.timeout",
            Duration.class)
            .orElse(Duration.ofSeconds(5));
} catch (org.springframework.boot.context.properties.bind.BindException ex) {
    throw new IllegalStateException(
            "Invalid server.client.timeout configuration", ex);
}
~~~

When catching, preserve the original exception in the cause chain to keep key and conversion details.

### Do not turn errors into "missing data"

The following pattern should generally be avoided:

~~~java
try {
    return binder.bind("server.client.timeout", Duration.class)
            .orElse(Duration.ofSeconds(5));
} catch (Exception ignored) {
    return Duration.ofSeconds(5);
}
~~~

It hides programming bugs, conversion errors, validation failures, or other system errors. If there is a requirement to fall back after a specific error, narrow the exception type, log diagnostics safely, and document the business policy clearly.

## 24. BindHandler and Controlling How Binder Handles Errors

At an advanced level, `Binder.bind(...)` has an overload accepting `BindHandler`:

~~~java
binder.bind(
        "app.settings",
        Bindable.of(Settings.class),
        handler);
~~~

`BindHandler` allows intercepting steps of the binding process. Spring Boot provides implementations for checking, validation, or error policies in specific contexts.

However, `BindHandler` **is not** an alternative return value for `BindResult`. Its role is to alter or observe the binding process before the result emerges.

For the question "what to do if a key has no data?", most cases should start with:

~~~java
bind(...).orElse(...)
bind(...).orElseGet(...)
bind(...).orElseThrow(...)
~~~

instead of writing a complex `BindHandler`.

In particular, error-ignoring handlers (if used) can obscure invalid configuration data. Only use them when genuinely necessary and verified by tests proving the final state is valid.

## 25. Validation Is a Separate Step from BindResult Status

Suppose the object is:

~~~java
public record ConnectionOptions(
        String host,
        int port) {
}
~~~

and the source only has:

~~~properties
connection.port=0
~~~

An object can be bound with `host=null` and `port=0`. `BindResult.isBound()` can be true, yet that configuration is unsafe to connect with.

With `@ConfigurationProperties`, Bean Validation can be used:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "connection")
public record ConnectionProperties(
        @NotBlank String host,
        @Min(1) int port) {
}
~~~

When the bean is registered appropriately and a validation provider is present, Spring Boot can catch constraint violations right at startup.

When calling Binder directly outside the configuration bean mechanism, **do not assume validation annotations always execute automatically along the exact `@ConfigurationProperties` path**. If validation is needed, provide an appropriate handler/validator or check the result with explicit logic.

### Two different questions

- `result.isBound()`: was an object produced from binding?
- Is the object valid?: is host non-blank, port in range, retry positive?

A serious system may need both.

## 26. Comparing Manual Binder with @ConfigurationProperties

When the whole application needs a stable configuration group, we usually use:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String host,
        Duration timeout) {
}
~~~

Then register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` and inject the bean:

~~~java
@Service
public class ClientService {
    private final ClientProperties properties;

    public ClientService(ClientProperties properties) {
        this.properties = properties;
    }
}
~~~

Suitable when:

- The configuration group is part of module design.
- Startup validation is needed.
- Multiple services share the bean.
- Configuration metadata for IDEs is needed.
- You want Spring Boot to manage lifecycle and DI.

By contrast, programmatic Binder:

~~~java
BindResult<ClientProperties> result =
        Binder.get(environment)
                .bind("app.client", ClientProperties.class);
~~~

is suitable when:

- You need to read an optional configuration group inside a specific processing flow.
- You want to check **whether a namespace exists** before deciding behavior.
- You need to dynamically bind a target type or collection that is inconvenient as a fixed bean.
- You are building an infrastructure module handling multiple configuration groups of different shapes.
- You need custom fallback choices right at read time.

**Do not use manual Binder merely because @ConfigurationProperties did not work**, when the real cause was forgetting to register the bean or using the wrong prefix. That is a wiring issue, not a limitation of `@ConfigurationProperties`.

## 27. How Do Environment.getProperty and Binder.bind Differ?

You can read a single key:

~~~java
String host = environment.getProperty("app.client.host");
~~~

or:

~~~java
BindResult<String> result =
        Binder.get(environment)
                .bind("app.client.host", String.class);
~~~

Yet the two APIs have different focuses:

| Mechanism | Primary purpose |
| --- | --- |
| `Environment.getProperty(key)` | Fetch a single property from config sources following property resolution rules. |
| `Environment.getProperty(key, type)` | Fetch a single property and convert it via the appropriate conversion service. |
| `Binder.bind(prefix, target)` | Bind structurally with relaxed binding into a typed target, returning `BindResult`. |
| `@ConfigurationProperties` | Declare a configuration group as an application bean with binding, validation, and DI. |

For a record with multiple fields, `Binder.bind("app.client", ClientProperties.class)` is usually more useful than calling `Environment.getProperty(...)` per key and assembling the object manually.

If you only need a single String value, `Environment.getProperty(...)` may be the simplest tool.

### BindResult is not just an "exists" check for a key

For objects and collections, Binder must also bind onto the target structure. Therefore, do not infer binding outcome solely from `environment.containsProperty("prefix")`.

Namespace example:

~~~properties
app.client.host=api.example.test
app.client.timeout=5s
~~~

There does not have to be a **literal key** named `app.client`. Binder can still bind `ClientProperties` from child keys. Checking `containsProperty("app.client")` directly is not equivalent to `binder.bind("app.client", target).isBound()`.

## 28. PropertySource Order and Missing Data Cases

Spring Boot merges configuration sources by precedence. One source lacking a key does not mean the key is absent from the entire environment.

Example:

~~~yaml
# application.yaml
feature:
  export:
    enabled: false
~~~

But when running:

~~~bash
java -jar app.jar --feature.export.enabled=true
~~~

Binder can take `true` from the CLI because command-line arguments generally have higher precedence than Config Data.

If you remove `feature.export.enabled` from a YAML file, an environment variable or system property can still provide it. Thus, when `BindResult.isBound()` is true even though the current file lacks the key, check:

- Profile-specific config files.
- External Config Data outside the JAR.
- Process environment variables.
- Java System properties.
- Command-line properties.
- Sources added by the application or tests.

Similarly, a key in YAML can be overridden by a higher-precedence source with another value, including an empty value; conversion rules depend on the target type.

**Do not diagnose "unbound" simply by opening one file and not seeing the prefix.** Binder works with the effective set of configuration sources, not a single file.

## 29. Attaching Binder to a Controlled Source in Unit Tests

To test without starting all of Spring Boot, you can construct Binder directly from `MapConfigurationPropertySource`.

### 29.1. Data present

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(Map.of(
                "client.timeout", "12s"));

Binder binder = new Binder(source);

BindResult<Duration> result =
        binder.bind("client.timeout", Duration.class);

System.out.println(result.isBound()); // true
System.out.println(result.get());     // PT12S
~~~

Here `MapConfigurationPropertySource` supplies a controlled property set independent of the test runner machine's environment variables.

### 29.2. No data

~~~java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(Map.of());

Binder binder = new Binder(source);

BindResult<Duration> result =
        binder.bind("client.timeout", Duration.class);

System.out.println(result.isBound()); // false
~~~

You can obtain a fallback:

~~~java
Duration timeout =
        result.orElse(Duration.ofSeconds(3));
~~~

The result is 3 seconds.

### 29.3. Data present but wrong type

~~~java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(Map.of(
                "client.timeout", "invalid-duration"));

Binder binder = new Binder(source);

binder.bind("client.timeout", Duration.class);
~~~

The call can throw `BindException` because the data cannot be converted to `Duration`. This is an essential test to confirm the application does not confuse configuration errors with undeclared properties.

## 30. JUnit Testing: Distinguishing Results and Exceptions

A sample test class:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.Map;
import java.util.NoSuchElementException;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class BinderResultTest {

    @Test
    void absentPropertyIsUnbound() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(Map.of()));

        BindResult<Duration> result =
                binder.bind("client.timeout", Duration.class);

        assertFalse(result.isBound());
        assertEquals(Duration.ofSeconds(5),
                result.orElse(Duration.ofSeconds(5)));

        assertThrows(NoSuchElementException.class, result::get);
    }

    @Test
    void validPropertyIsBound() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(
                        Map.of("client.timeout", "12s")));

        BindResult<Duration> result =
                binder.bind("client.timeout", Duration.class);

        assertTrue(result.isBound());
        assertEquals(Duration.ofSeconds(12), result.get());
    }

    @Test
    void invalidPropertyDoesNotUseFallback() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(
                        Map.of("client.timeout", "not-a-duration")));

        assertThrows(BindException.class, () ->
                binder.bind("client.timeout", Duration.class)
                        .orElse(Duration.ofSeconds(5)));
    }
}
~~~

The three tests verify three independent branches:

- Missing key → unbound.
- Valid value → bound.
- Wrong-type value → bind error.

If the last test uses a different wrapper exception in a specific context, check the cause corresponding to `BindException`; the key point is distinguishing errors from fallbacks.

### Testing that false is not unbound

~~~java
@Test
void falseIsStillBound() {
    Binder binder = new Binder(
            new MapConfigurationPropertySource(
                    Map.of("feature.enabled", "false")));

    BindResult<Boolean> result =
            binder.bind("feature.enabled", Boolean.class);

    assertTrue(result.isBound());
    assertFalse(result.get());
}
~~~

### Testing that supplier only runs when needed

~~~java
@Test
void fallbackSupplierIsLazy() {
    Binder binder = new Binder(
            new MapConfigurationPropertySource(
                    Map.of("client.timeout", "12s")));

    Duration timeout = binder
            .bind("client.timeout", Duration.class)
            .orElseGet(() -> {
                throw new AssertionError(
                        "Supplier must not be called when bound");
            });

    assertEquals(Duration.ofSeconds(12), timeout);
}
~~~

This test directly demonstrates the lazy nature of `orElseGet`.

## 31. Checking Partially Bound Objects

A test on a prefix:

~~~java
public record ClientOptions(
        String host,
        Integer port) {
}
~~~

Source:

~~~properties
client.host=api.example.test
~~~

Code:

~~~java
Binder binder = new Binder(
        new MapConfigurationPropertySource(Map.of(
                "client.host", "api.example.test")));

BindResult<ClientOptions> result =
        binder.bind("client", ClientOptions.class);
~~~

When Binder builds the object from present data, `result.isBound()` can be true while `result.get().port()` has no value.

Therefore, tests should verify both:

~~~java
assertTrue(result.isBound());
assertEquals("api.example.test", result.get().host());
~~~

and the policy for missing members:

~~~java
if (result.get().port() == null) {
    // Missing port configuration: report error or use default by design.
}
~~~

Object completeness cannot be verified with `isBound()` alone.

### Use wrappers instead of primitives when absence must be distinguished

If the record type is:

~~~java
public record ClientOptions(String host, int port) {
}
~~~

a missing `int` member can receive default 0 depending on how the object is created. That makes it hard to distinguish "operator intentionally set 0" from "port was not supplied."

If that distinction matters, use `Integer`, `@NotNull`, or explicit validation. Do not rely on primitive default values as an indicator of key presence.

## 32. BindResult vs. Optional in Configuration: Which to Choose?

One might think of writing:

~~~java
Optional<String> endpoint;
~~~

inside a `@ConfigurationProperties` class to express an optional value.

However, Spring Boot documentation recommends **not using `Optional` as fields of `@ConfigurationProperties`**. When data is missing, binder behavior may not match the intuition of "always producing `Optional.empty()`."

In a configuration class, you can use:

- `String` or nullable wrapper types with validation as required.
- `@DefaultValue` in constructor binding when a valid default exists.
- `@NotNull` for required properties.
- `@Valid` to validate nested objects.

For a **manual** Binder call, `BindResult<T>` itself is the right abstraction to know whether a result exists.

If an external API genuinely requires `Optional<T>`, convert explicitly:

~~~java
BindResult<String> result =
        binder.bind("app.label", String.class);

Optional<String> label =
        result.isBound()
                ? Optional.of(result.get())
                : Optional.empty();
~~~

This snippet requires importing `java.util.Optional`. This is a state conversion for **a Binder call**, not a recommendation to put `Optional` directly as `@ConfigurationProperties` members.

## 33. Safety When Choosing Default Values

A default is not always a safe choice.

**Good candidates for fallback:**

- Reasonable small trial retry counts.
- Optional display names.
- Disabling a secondary feature when unconfigured.
- Local demo directories that do not affect production systems.
- Approved policy-based timeouts.

**Be careful with fallbacks for:**

- Payment endpoints or production services.
- Passwords, tokens, signing keys.
- TLS or certificate verification settings.
- Destinations for sensitive data storage.
- Region/partner codes deciding where data is routed.

Dangerous example:

~~~java
URI endpoint = binder.bind(
        "payments.endpoint", URI.class)
        .orElse(URI.create("http://localhost:8080"));
~~~

If production omits configuration, the app could mistakenly call localhost. For required configurations, `orElseThrow` with a clear message is usually better.

### Do not let fallbacks hide operational errors

`orElse(default)` is a decision that only applies to unbound results. If configuration is malformed, keep the error or wrap it in a context-rich exception rather than catching all exceptions and replacing them with a default.

A good policy should be recorded in operational documentation: which keys are optional, which are required, what defaults are, and what missing data means.

## 34. Practice Exercises

### Exercise 1 — predict the state

Source:

~~~properties
app.name=demo
~~~

Code:

~~~java
BindResult<String> a =
        binder.bind("app.name", String.class);

BindResult<String> b =
        binder.bind("app.region", String.class);
~~~

**Answer:** `a.isBound()` is true; `b.isBound()` is normally false if no other source provides `app.region`.

### Exercise 2 — false is present data

~~~properties
feature.enabled=false
~~~

Code:

~~~java
BindResult<Boolean> result =
        binder.bind("feature.enabled", Boolean.class);
~~~

**Answer:** `isBound()` is true, `get()` is false.

### Exercise 3 — simple fallback

No `app.timeout`:

~~~java
Duration value =
        binder.bind("app.timeout", Duration.class)
                .orElse(Duration.ofSeconds(10));
~~~

**Answer:** 10 seconds.

### Exercise 4 — fallback does not apply when bound

~~~properties
app.timeout=0ms
~~~

Code:

~~~java
Duration value =
        binder.bind("app.timeout", Duration.class)
                .orElse(Duration.ofSeconds(10));
~~~

**Answer:** `Duration.ZERO`, not 10 seconds. If 0 is invalid, validate separately.

### Exercise 5 — fallback does not rescue wrong types

~~~properties
app.timeout=bad-duration
~~~

Code uses `bind(..., Duration.class).orElse(Duration.ofSeconds(10))`.

**Answer:** Binder can throw a conversion error, rather than defaulting to 10 seconds.

### Exercise 6 — orElse vs. orElseGet

Two snippets:

~~~java
result.orElse(makeDefaults());
result.orElseGet(this::makeDefaults);
~~~

If result is bound, which one still calls `makeDefaults()`?

**Answer:** `orElse(makeDefaults())` because Java arguments are evaluated upfront. `orElseGet(...)` does not call the supplier when bound.

### Exercise 7 — completely missing group configuration

No `feature.export.*` properties exist. To disable the feature safely, use `result.isBound()` to decide to skip or `orElseGet(...)` to create an object with `enabled=false` per policy.

### Exercise 8 — partial binding

Source:

~~~properties
feature.export.enabled=true
~~~

Type:

~~~java
public record ExportOptions(
        boolean enabled,
        String outputDirectory,
        Duration timeout) {
}
~~~

**Question:** If result is bound, does `orElseGet(...)` fill in `outputDirectory` and `timeout`?

**Answer:** No. `orElseGet` only provides fallback when the entire result is unbound. Missing values inside an object must be handled via `@DefaultValue`, field initializers, or validation by design.

### Exercise 9 — get() when unbound

No `app.name`:

~~~java
binder.bind("app.name", String.class).get();
~~~

**Answer:** Can throw `NoSuchElementException`. Use `orElseThrow` if a tailored error message is desired.

### Exercise 10 — binding typed collections

To bind `List<String>` at `app.backends`, choose:

~~~java
binder.bind("app.backends", Bindable.listOf(String.class));
~~~

Do not use plain `List.class` if you want to preserve the element type.

### Exercise 11 — checking namespace

Source:

~~~properties
app.client.host=api.example.test
app.client.timeout=5s
~~~

There is no literal key `app.client`. Can `ClientProperties` be bound with prefix `app.client`?

**Answer:** Yes, because Binder looks for members under the namespace. `environment.containsProperty("app.client")` is not an equivalent check.

### Exercise 12 — three input states

Design a test for:

1. Missing `app.max-attempts`.
2. `app.max-attempts=0`.
3. `app.max-attempts=abc`.

**Expected result:** first is unbound; second is bound with 0 if type is `Integer`; third is a conversion error. All three branches need distinct handling.

### Exercise 13 — required policy

With `payment.endpoint` required and no safe default:

~~~java
binder.bind("payment.endpoint", URI.class)
        .orElseThrow(() ->
                new IllegalStateException(
                        "Missing payment.endpoint"));
~~~

Use `orElseThrow` instead of an arbitrary default URL.

### Exercise 14 — using map()

~~~properties
jobs.retry-limit=5
~~~

~~~java
String label =
        binder.bind("jobs.retry-limit", Integer.class)
                .map(x -> "Retry: " + x)
                .orElse("No configuration");
~~~

**Answer:** `Retry: 5`.

### Exercise 15 — is adding a handler reasonable?

A configuration group has no data and you only want a 10-second default.

**Answer:** No need to write a custom `BindHandler`. Calling `binder.bind(...).orElse(Duration.ofSeconds(10))` is sufficient and clear.

## 35. Troubleshooting Checklist When BindResult Is Unexpected

When `isBound()` is false even though you think you configured it, follow this order:

1. **Key/prefix name**: does it use canonical form and the right member path?
2. **Data source**: is the value in `application.yaml`, a profile file, env vars, or CLI?
3. **Active profile**: was the configuration document containing the key actually loaded?
4. **Environment variable name**: does it follow Spring Boot's relaxed binding rules?
5. **Bind target**: can the target type be converted from the source? Does the object have matching members?
6. **Whole group state**: completely no properties, or just missing a few members?
7. **Binding exception**: did an error occur before returning a result?
8. **Fallback**: does using `orElse`, `orElseGet`, or `orElseThrow` match the policy?
9. **Validation**: if the object is bound, does it have all fields and fall within business bounds?
10. **Read timing**: were `Environment` and binder created in the right Spring Boot lifecycle phase?

Common errors and how to handle them:

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `isBound=false`, no prefix | Optional config is truly absent | Default/skip/report missing. |
| `get()` throws `NoSuchElementException` | Called get when unbound | Check first or use `orElseThrow`. |
| One field present but another is null | Partially bound object | Member-level default/validation. |
| Boolean false treated as "unconfigured" | Confusing value with status | Use `isBound()`. |
| `orElse` doesn't rescue mistyped data | Binder threw before returning `BindResult` | Fix data or handle `BindException`. |
| `orElseGet` is not invoked | Result was already bound | Expected behavior; inspect the object. |
| `bindOrCreate` fails to instantiate | Type cannot be created in a supported way | Pick a suitable type/factory/fallback. |
| YAML exists but CLI overrides value | `PropertySource` precedence | Inspect higher-precedence sources. |
| List is unexpectedly empty | List source and binding rules | Check actual data and source order. |

## 36. Quick Decision Table

| Goal | Recommended API |
| --- | --- |
| Read an optionally absent scalar | `binder.bind(name, Type.class)` + `BindResult`. |
| Check absent status | `isBound()`. |
| Require a value, fail otherwise | `orElseThrow(...)`. |
| Simple default | `orElse(defaultValue)`. |
| Computed default when needed | `orElseGet(supplier)`. |
| Run an action when bound | `ifBound(consumer)`. |
| Transform result preserving unbound logic | `map(function)`. |
| Always try to obtain an instance of a creatable type | `bindOrCreate(...)`. |
| Bind list/map with generic element types | `Bindable.listOf(...)` / `Bindable.mapOf(...)`. |
| Fixed config shared across services | `@ConfigurationProperties` + bean registration. |
| Verify object completeness and policy compliance | Separate validation, not just `isBound()`. |
| Mistyped data | Investigate/report binding error, do not silently fall back. |

## 37. Final Takeaways

`BindResult<T>` lets developers explicitly distinguish **when binding produced a result** from **when no data existed to bind**. Methods `isBound`, `get`, `orElse`, `orElseGet`, `orElseThrow`, `ifBound`, and `map` correspond to policies for reading, defaulting, requiring, or acting only when configured.

However, always separate **three axes**:

1. **Is there source data?** → `BindResult` expresses bound/unbound.
2. **Can the data be converted to the target type?** → Binder and conversion handle this; errors can throw exceptions.
3. **Is the bound object complete and business-valid?** → member-level defaults, validation, and business logic handle this.

An object with just a few members can already be considered bound; therefore `orElseGet(...)` does not populate missing fields. A `false` or `0` value is still bound data. A mistyped string does not become "no data" just because you added a fallback.

When optional configuration is needed, choose `orElse` or `orElseGet` with a safe default. When configuration is required, use `orElseThrow` with a specific message. When an object is desired even without data, consider `bindOrCreate`, ensuring the type can be created and its defaults are valid.

That is how to use `Binder` at an advanced level while keeping the system easy to diagnose, without hiding deployment errors or creating surprising behavior across environments.

## References

- [Spring Boot 3.3 — Binder API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html).
- [Spring Boot 3.x — BindResult API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindResult.html).
- [Spring Boot 3.3 — Bindable API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Bindable.html).
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot 3.3 — MapConfigurationPropertySource API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/source/MapConfigurationPropertySource.html).
