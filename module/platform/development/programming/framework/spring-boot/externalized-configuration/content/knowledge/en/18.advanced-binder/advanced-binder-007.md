# Customizing the Binding Process with BindHandler in Spring Boot

In Spring Boot, `@ConfigurationProperties` and `Binder` convert properties from `Environment` into typed Java objects. When a large application needs **observability, extra validation, error control, or tracking during binding**, merely declaring fields/record components is sometimes not enough.

The **`org.springframework.boot.context.properties.bind.BindHandler`** interface provides callbacks to intercept each stage of binding. Spring Boot also offers `AbstractBindHandler` to build handlers in a *decorator* pattern: attaching new behavior while still forwarding callbacks to the parent handler, preserving existing functionality.

This lesson uses **Spring Boot 3.3.x and Java 21**. It covers:

- When `BindHandler` is needed and when `@ConfigurationProperties` or Bean Validation alone suffices.
- The roles of `onStart`, `onSuccess`, `onCreate`, `onFailure`, and `onFinish`.
- How to write a custom handler based on `AbstractBindHandler`.
- How to use a handler in a single `Binder.bind(...)` call.
- How to apply it to `@ConfigurationProperties` binding via `ConfigurationPropertiesBindHandlerAdvisor`.
- How to combine with built-in handlers, testing, and risks of mutating data or swallowing errors.

## 1. Where Does BindHandler Sit in the Configuration Loading Flow?

Suppose `src/main/resources/application.yml` is:

~~~yaml
app:
  client:
    endpoint: https://api.example.org
    connect-timeout: 3s
    max-connections: 12
    enabled: true
~~~

And the configuration class is:

~~~java
package com.example.configdemo.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int maxConnections,
        boolean enabled) {
}
~~~

Spring Boot reads configuration sources, selects values by precedence order, converts them into `URI`, `Duration`, `int`, `boolean`, and constructs a `ClientProperties`.

`BindHandler` is an extension point of **Binder**. It is called while Binder processes target elements—it is **not a new type of `PropertySource`** and does not change YAML loading in the Config Data phase.

Conceptual diagram:

~~~text
application.yml / environment / CLI / imported Config Data
                           |
                           v
                      Environment
                           |
                           v
               Binder.bind(prefix, type, handler)
                           |
             +-------------+--------------+
             |         BindHandler         |
             | onStart / onSuccess         |
             | onCreate / onFailure        |
             | onFinish                    |
             +-------------+--------------+
                           |
                           v
               ClientProperties object
                           |
                           v
                       Service
~~~

Callbacks can be invoked for **multiple elements**: the root group, child properties, collection items, or nested structures. One callback does not necessarily correspond to a single invocation for the whole object.

## 2. When Should You Customize with BindHandler?

Suitable scenarios include:

1. **Observing binding:** recording which property names were processed or succeeded, without logging sensitive values.
2. **Error diagnostics:** adding property-name context when conversion or binding fails.
3. **Result checking:** enforcing a very specific rule right after a property binds successfully.
4. **Customizing error policy:** choosing how to handle known, safe binding errors while avoiding masking misconfiguration.
5. **Applying policy across multiple beans:** attaching a handler to Spring Boot's managed binding pipeline using an advisor.
6. **Tracking bound properties:** combining with built-in handlers to collect information within a valid scope.

`BindHandler` is usually **not the first choice** if the goal is merely:

- Declaring configuration values: use `application.yml`, `application.properties`, or environment variables.
- Standard type conversion: Binder already supports numbers, booleans, enums, `Duration`, `DataSize`, `URI`, etc.
- Converting a String to a custom domain type: use a `Converter` annotated with `@ConfigurationPropertiesBinding` when appropriate.
- Checking `maxConnections >= 1`: prefer Bean Validation (`@Min`, `@NotNull`, ...).
- Setting record defaults: use `@DefaultValue` or per-environment configuration.
- Selecting files by profile: use `spring.profiles.active`, `spring.config.import`, and Config Data.

Handlers are powerful because they intercept deep inside the binding lifecycle. For that very reason, keep their scope small and easy to control.

## 3. BindHandler API: Main Callbacks

Package:

~~~java
import org.springframework.boot.context.properties.bind.BindHandler;
~~~

In Spring Boot 3.3, this interface has these callback methods:

~~~java
<T> Bindable<T> onStart(
        ConfigurationPropertyName name,
        Bindable<T> target,
        BindContext context);

Object onSuccess(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Object result);

Object onCreate(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Object result);

Object onFailure(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Exception error) throws Exception;

void onFinish(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Object result) throws Exception;
~~~

These are **conceptual signatures**; in the interface the methods are default methods. `BindHandler.DEFAULT` is the default handler that adds no special behavior.

### 3.1. onStart — before binding an element

`onStart` is called when Binder begins processing an element, before determining the result. It receives `name`, `target`, and `context`.

It returns a `Bindable<T>` representing the target to continue with. It **can be modified** if the handler has a very specific reason. Returning `null` has special meaning and can stop binding that element; never return null arbitrarily just to "skip logging."

### 3.2. onSuccess — after a successful binding result

`onSuccess` additionally receives `result`. The handler can:

- Record the property name that bound successfully.
- Inspect the final result per a specific policy.
- In advanced cases, replace the returned result with a compatible object.

If you arbitrarily return a type incompatible with `target`, parent object construction can fail or data can mutate unexpectedly. For observation handlers, **return the result of `super.onSuccess(...)`** to preserve the parent handler chain.

### 3.3. onCreate — creating an object even without bound data

`onCreate` is called when an element finishes **unbound**, yet a new instance was created and is about to be returned. The passed-in result is non-null; the handler may inspect or replace the instance per the API contract.

Do not confuse `onCreate` with `onSuccess`. `onCreate` does not mean the property appeared in Environment; it describes the object-creation path even when no configuration data was received for that element.

### 3.4. onFailure — when binding fails

`onFailure` receives the original exception from the binding process, including errors thrown by certain result-handling callbacks. The handler can:

- Log additional context.
- Propagate the error.
- In special cases, choose a replacement result or suppress the error.

**By default, preserve the error.** Silently returning null or a fallback value can let the application start with invalid configuration, which is especially dangerous for timeouts, access controls, endpoints, or secrets.

### 3.5. onFinish — finishing an element

`onFinish` is called when binding finishes with a bound or unbound result. `result` can be null. Per Spring Boot 3.3 documentation, this callback **is not called when binding fails**, even if `onFailure` chooses to return a replacement result.

Do not think of `onFinish` as a Java `finally` block that runs for every path. If you need to track errors too, observe `onFailure` separately.

### Summary table

| Callback | Timing | Return value | Notes |
| --- | --- | --- | --- |
| `onStart` | Before processing element | `Bindable<T>` or null | Can swap target or halt binding |
| `onSuccess` | Successful bind | `Object` | Can alter result, must keep compatible type |
| `onCreate` | Unbound yet instance created | `Object` | Does not imply property exists |
| `onFailure` | Exception during bind | `Object` or throw exception | Do not accidentally swallow errors |
| `onFinish` | Normal completion (bound or unbound) | `void` | Does not run on failure path |

## 4. Objects Passed into Callbacks

### ConfigurationPropertyName

~~~java
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
~~~

This is Spring Boot's canonical property name, for example:

~~~text
app.client
app.client.endpoint
app.client.connect-timeout
app.client.max-connections
~~~

You can use `name.toString()` to identify the element being processed. For collections or Maps, paths may contain indices/keys; do not assume only simple fields appear.

### Bindable<T>

~~~java
import org.springframework.boot.context.properties.bind.Bindable;
~~~

`Bindable` describes the target Binder is operating on, including type info and binding metadata. In manual calls, you can construct:

~~~java
Bindable.of(ClientProperties.class)
~~~

For generic structures, use `Bindable.listOf(...)`, `Bindable.mapOf(...)`, or `Bindable.of(ResolvableType)` per API needs. Do not drop generic information when binding `List<ClientSettings>` or `Map<String, Endpoint>`.

### BindContext

~~~java
import org.springframework.boot.context.properties.bind.BindContext;
~~~

`BindContext` holds contextual state during binding, such as current configuration property details and depth in the bind tree. It **is not a Spring ApplicationContext** and should not be used to run business logic, query databases, or make network calls inside callbacks.

You can use info from the context for logging/diagnostics, but check for nulls and never leak values of properties containing secrets.

### result and error

`result` in `onSuccess` is an already-bound object, not always the raw original String. For example, it may be an `Integer`, `Duration`, `URI`, a record, or a collection.

`error` in `onFailure` is the exception associated with the element being bound. To troubleshoot, log the property name, exception class, and minimal diagnostic info; never automatically log source values as they may be tokens or passwords.

## 5. Writing an Observation Handler with AbstractBindHandler

`AbstractBindHandler` is a convenient base class when you only want to add behavior to a few callbacks:

~~~java
import org.springframework.boot.context.properties.bind.AbstractBindHandler;
~~~

This class supports a constructor taking a `BindHandler parent` to form a decorator chain. Example of a handler recording property names in the `app.client` group:

~~~java
package com.example.configdemo.bind;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.context.properties.bind.AbstractBindHandler;
import org.springframework.boot.context.properties.bind.BindContext;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;

public final class ClientTraceBindHandler extends AbstractBindHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ClientTraceBindHandler.class);

    public ClientTraceBindHandler(BindHandler parent) {
        super(parent);
    }

    @Override
    public <T> Bindable<T> onStart(
            ConfigurationPropertyName name,
            Bindable<T> target,
            BindContext context) {

        if (isClientProperty(name)) {
            log.debug("Begin binding property {}", name);
        }

        return super.onStart(name, target, context);
    }

    @Override
    public Object onSuccess(
            ConfigurationPropertyName name,
            Bindable<?> target,
            BindContext context,
            Object result) {

        if (isClientProperty(name)) {
            // Only log property name, not value.
            log.debug("Successfully bound property {}", name);
        }

        return super.onSuccess(name, target, context, result);
    }

    @Override
    public Object onFailure(
            ConfigurationPropertyName name,
            Bindable<?> target,
            BindContext context,
            Exception error) throws Exception {

        if (isClientProperty(name)) {
            log.warn(
                    "Binding failed for {}, exception type {}",
                    name, error.getClass().getSimpleName());
        }

        // Preserve parent's error-handling policy.
        return super.onFailure(name, target, context, error);
    }

    private static boolean isClientProperty(
            ConfigurationPropertyName name) {

        String path = name.toString();
        return path.equals("app.client")
                || path.startsWith("app.client.");
    }
}
~~~

### Key observations in the code

- `super(parent)` ensures this handler **wraps another handler**, rather than replacing the entire chain.
- `onStart` only logs and delegates to `super.onStart`, preserving whatever `Bindable` the parent wants to use.
- `onSuccess` calls `super.onSuccess` so the final result still flows through the parent handler.
- `onFailure` logs only the exception type, then forwards to parent without suppressing the error.
- No method alters `result`, so the handler is strictly observational.
- Neither `result` nor `error.getMessage()` is printed in logs in the example to avoid accidentally exposing sensitive configuration values.
- Path names are filtered by prefix to avoid logging every framework and library setting.

### Why extend AbstractBindHandler?

You can implement `BindHandler` directly. However, when composing with an existing handler, `AbstractBindHandler` makes callback forwarding simpler and avoids accidentally skipping the parent's validation or error handling.

## 6. Manually Calling Binder.bind(...) with BindHandler

A simple way to learn and test a handler is passing it directly into a Binder call.

Example bean observing after Spring Boot initialization:

~~~java
package com.example.configdemo;

import com.example.configdemo.bind.ClientTraceBindHandler;
import com.example.configdemo.config.ClientProperties;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ManualBindingDemo {

    @Bean
    ApplicationRunner inspectManualBinding(Environment environment) {
        return args -> {
            Binder binder = Binder.get(environment);

            BindHandler handler =
                    new ClientTraceBindHandler(BindHandler.DEFAULT);

            ClientProperties config = binder.bind(
                    "app.client",
                    Bindable.of(ClientProperties.class),
                    handler
            ).get();

            System.out.println(
                    "Endpoint scheme: "
                            + config.endpoint().getScheme());
            System.out.println(
                    "Connect timeout: "
                            + config.connectTimeout());
        };
    }
}
~~~

If `app.client` exists with valid data, this example constructs a `ClientProperties` object via one manual bind; the handler observes the elements processed.

`BindResult.get()` is used when a result is expected; if binding yields no value, it throws instead of silently returning null. In real applications, handle `BindResult` according to requirements.

**Very important point:** passing a handler into `binder.bind(...)` **only applies to that single call**. It does not attach the handler to every `@ConfigurationProperties` bean created by Spring Boot at startup.

The example above runs in `ApplicationRunner`, i.e., **after the context has initialized**. Thus it is an isolated bind pass for demonstration. If the goal is customizing when Spring Boot creates configuration-properties beans, you need the advisor mechanism in the next section.

## 7. Applying a Handler When Spring Boot Binds @ConfigurationProperties

Spring Boot provides the interface:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBindHandlerAdvisor;
~~~

`ConfigurationPropertiesBindHandlerAdvisor` is a functional interface with the method:

~~~java
BindHandler apply(BindHandler bindHandler);
~~~

It allows decorating the handler used by `ConfigurationPropertiesBindingPostProcessor`, i.e., Spring Boot's binding pipeline for `@ConfigurationProperties` beans.

Configuration example:

~~~java
package com.example.configdemo.bind;

import org.springframework.boot.context.properties.ConfigurationPropertiesBindHandlerAdvisor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BindingAdviceConfiguration {

    @Bean
    static ConfigurationPropertiesBindHandlerAdvisor traceClientBinding() {
        return existing ->
                new ClientTraceBindHandler(existing);
    }
}
~~~

When Spring Boot initializes eligible configuration properties beans, the advisor wraps `existing` with `ClientTraceBindHandler`. The inner handler only logs `app.client...` property names, avoiding impact on other groups.

### Why must you pass existing into the constructor?

Correct way:

~~~java
return existing -> new ClientTraceBindHandler(existing);
~~~

Avoid doing:

~~~java
return existing ->
        new ClientTraceBindHandler(BindHandler.DEFAULT);
~~~

if the goal is preserving the existing processing chain. Using `BindHandler.DEFAULT` instead of `existing` can bypass behavior already added by Spring Boot or other advisors, such as validation and special handling.

### Scope of an advisor

An advisor bean can affect the binding of many `@ConfigurationProperties` beans managed by Spring Boot. Therefore:

- Only add policies that genuinely need broad application.
- Filter by prefix or target type inside the handler.
- Avoid logging all names/values of system configurations.
- Do not run heavy I/O or complex bean lookups inside callbacks.
- Do not use an advisor as a substitute for editing a specific value in configuration files.

**The advisor mechanism differs from a manual Binder.bind call:** an advisor affects the pipeline managed by `ConfigurationPropertiesBindingPostProcessor`; it does not alter standalone Binders created manually by application code unless that code explicitly uses the corresponding handler.

## 8. Handler Chains and Callback Invocation Order

One `BindHandler` can wrap another handler:

~~~text
CustomTraceHandler
        |
        v
ExistingHandler
        |
        v
Handlers configured by Spring Boot
~~~

With `new ClientTraceBindHandler(existing)`, `ClientTraceBindHandler` is the outer layer. When a callback fires, its implementation can invoke `super.onStart(...)`, `super.onSuccess(...)`, or `super.onFailure(...)` to delegate to parent.

This lets you add functionality without breaking the original pipeline.

### Observation order may differ from field order

Binder may traverse elements according to a strategy matching the type, constructor, or collection. If a handler logs:

~~~text
Begin binding property app.client
Begin binding property app.client.endpoint
Successfully bound property app.client.endpoint
Begin binding property app.client.max-connections
Successfully bound property app.client.max-connections
Successfully bound property app.client
~~~

that is only an **illustrative trace**, not a callback order guaranteed across all versions and types. Some elements may remain unbound, be default-created, or be absent depending on configuration sources.

Do not write business logic assuming `endpoint` is guaranteed to bind before `maxConnections`, or that the callback count equals the number of record fields.

### Avoid double-counting mistakes

`onSuccess` can be called for both the parent object and multiple child properties. If you increment a counter on every callback and call the result "number of @ConfigurationProperties beans bound," the count will be wrong. To count root beans, filter specifically on root names or target scope.

## 9. Checking a Value After Binding with onSuccess

A handler can add result checks. For example, rejecting zero or negative connection counts **during a manual bind**:

~~~java
package com.example.configdemo.bind;

import org.springframework.boot.context.properties.bind.AbstractBindHandler;
import org.springframework.boot.context.properties.bind.BindContext;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;

public final class PositiveConnectionsBindHandler
        extends AbstractBindHandler {

    public PositiveConnectionsBindHandler(BindHandler parent) {
        super(parent);
    }

    @Override
    public Object onSuccess(
            ConfigurationPropertyName name,
            Bindable<?> target,
            BindContext context,
            Object result) {

        if (name.toString().equals("app.client.max-connections")
                && result instanceof Integer value
                && value < 1) {

            throw new IllegalStateException(
                    "app.client.max-connections must be positive");
        }

        return super.onSuccess(name, target, context, result);
    }
}
~~~

Usage:

~~~java
Binder binder = Binder.get(environment);

ClientProperties config = binder.bind(
        "app.client",
        Bindable.of(ClientProperties.class),
        new PositiveConnectionsBindHandler(BindHandler.DEFAULT)
).get();
~~~

If an operator sets `app.client.max-connections=-2`, the callback can raise an error to prevent using that configuration.

**In practice:** a standalone rule like `max-connections >= 1` should be solved with Bean Validation:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @Min(1) int maxConnections) {
}
~~~

along with the required imports and validation dependency. `PositiveConnectionsBindHandler` only illustrates the ability to intercept `onSuccess`. Do not turn all validation into handler code when standard annotations already handle it.

### Note the failure path when throwing exceptions inside callbacks

`BindHandler` documentation notes that errors in `onSuccess` or `onCreate` can feed into `onFailure`. Therefore, if another handler chooses to suppress errors, the final result may differ from expectations. For mandatory configurations, preserve fail-fast behavior and test the entire handler chain.

## 10. onFailure: Do Not Automatically Swallow Configuration Errors

A dangerous mistake is overriding `onFailure` like this:

~~~java
@Override
public Object onFailure(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Exception error) {

    return null;
}
~~~

The snippet above can hide conversion errors or misconfigurations, depending on element position and how Binder uses the replacement result. The application risks creating objects with missing values, retaining improper defaults, or starting with unintended configuration.

For example, an operator sets:

~~~properties
app.client.max-connections=many
~~~

If the application should have halted due to an invalid connection count, swallowing the error can cause the configuration class to receive a default value or missing state. That makes operations hard to debug.

### Usually safer approach: minimal logging then forward

~~~java
@Override
public Object onFailure(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Exception error) throws Exception {

    logger.warn("Failed to bind property {}", name);
    return super.onFailure(name, target, context, error);
}
~~~

When a parent exists, `super.onFailure` preserves the existing handler chain's policy. Logging should mask/omit sensitive values, because conversion error messages sometimes include raw input data.

### When can errors be ignored?

Only when a configuration group is genuinely **optional** and the application has a designed fallback path—for example, when an auxiliary module is disabled, bad data in it should not break the main module. Even then, you must:

- Identify the exact prefix and error types allowed to be ignored.
- Provide safe fallback behavior with no half-baked state.
- Emit logs/metrics so operators know the configuration was unused.
- Have tests for invalid values, missing values, and conflicting configs.
- Never ignore errors on secrets, access controls, or critical transaction settings just so the app starts.

## 11. Built-in Handler: IgnoreErrorsBindHandler

Spring Boot provides:

~~~java
import org.springframework.boot.context.properties.bind.handler.IgnoreErrorsBindHandler;
~~~

This handler implements a **ignore binding errors** policy. Example scoped to a single Binder.bind call:

~~~java
Binder binder = Binder.get(environment);

BindHandler ignoreErrors = new IgnoreErrorsBindHandler(
        BindHandler.DEFAULT);

ClientProperties config = binder.bind(
        "app.client",
        Bindable.of(ClientProperties.class),
        ignoreErrors
).orElse(null);
~~~

This is an API-illustration example, **not a recommended production setup** for general applications. If a property has the wrong type, ignoring it can leave the final object different from expectations, including unbound results or defaulted fields. If the whole object yields no result, `orElse(null)` can return null.

If data is critical, preserve errors so the application fails fast. Do not use `IgnoreErrorsBindHandler` as a blanket fix for invalid YAML files.

### Comparison with ignoreInvalidFields

`@ConfigurationProperties` has an `ignoreInvalidFields` attribute to handle certain unbindable value cases under the annotation contract. That lives inside configuration-properties bean creation; `IgnoreErrorsBindHandler` is a handler used when constructing a pipeline. Do not treat the two as identical in scope and behavior.

## 12. Built-in Handler: NoUnboundElementsBindHandler

Another class of problem is **having properties under the prefix that do not match any bound field**. For example:

~~~yaml
app:
  client:
    endpoint: https://api.example.org
    max-connetions: 12  # Typo
~~~

The actual record expects `maxConnections`, matching `max-connections`. In some setups, unknown `max-connetions` may be ignored.

Spring Boot has:

~~~java
import org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler;
~~~

`NoUnboundElementsBindHandler` enforces that properties under the bound root are consumed, helping catch extra keys or typos when the property source supports enumeration.

Example:

~~~java
Binder binder = Binder.get(environment);

BindHandler strict = new NoUnboundElementsBindHandler(
        BindHandler.DEFAULT);

ClientProperties config = binder.bind(
        "app.client",
        Bindable.of(ClientProperties.class),
        strict
).get();
~~~

If `app.client.max-connetions` is present and cannot bind to a field, the handler can reject it instead of silently ignoring it, depending on source characteristics and the element scope being checked.

### Do not apply strictness system-wide by default

If `NoUnboundElementsBindHandler` is applied to an overly broad root, the application may trip over properties used by other components, or sources that cannot enumerate all keys. Pick a specific prefix and understand `ConfigurationPropertySource` enumeration capabilities.

With `@ConfigurationProperties`, the annotation provides `ignoreUnknownFields` and Spring Boot's matching mechanism to control certain mismatches. Strictness choices must fit the project's actual structure.

## 13. Built-in Handler: ValidationBindHandler

To validate configuration, Spring Boot provides:

~~~java
import org.springframework.boot.context.properties.bind.validation.ValidationBindHandler;
~~~

This handler collaborates with an appropriate `Validator` to check binding results. In standard applications, the most convenient way remains:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotNull URI endpoint,
        @Min(1) int maxConnections) {
}
~~~

and ensuring a Bean Validation provider is present, such as `spring-boot-starter-validation`. Spring Boot applies validation appropriately during configuration-properties binding.

If you build a Binder manually and manage your own handler chain, you can use `ValidationBindHandler` with prepared validators. However, do not instantiate an arbitrary validator and assume it applies all validation annotations in all conditions. Verify validator registration, validation groups, and framework version compatibility.

**Distinctions:**

- `Conversion`: string `many` fails to convert to `int`.
- `Validation`: number `-2` converts to `int` but violates `@Min(1)`.
- `Unknown/unbound`: key `max-connetions` matches no `maxConnections` component.

Different handlers address different problems; no single handler "fixes all configuration mistakes."

## 14. Observing Callbacks Without Exposing Sensitive Data

An application can contain properties like:

~~~yaml
app:
  payment:
    api-key: "example-only"
    token: "not-a-real-token"
    enabled: true
~~~

If a handler logs everything:

~~~java
log.info("{} = {}", name, result);
~~~

it can write tokens, passwords, or bound objects containing secrets into logs. That is a serious security risk.

Design handlers according to these principles:

- Log **property names** or result types, not values.
- Only log prefixes you own.
- Do not automatically log the entire `error.getMessage()` if the message might contain source data.
- Avoid calling `toString()` on records containing sensitive fields.
- Keep logging at an appropriate level, such as `DEBUG` in development environments.
- If production config analysis is needed, use inspection tools with redaction and access control.

Do not place dynamic configuration values into metric names or high-cardinality labels, as they explode time-series cardinality and leak data.

## 15. When to Use onCreate?

`onCreate` appears less frequently in application code than `onSuccess`, yet it matters when Binder can instantiate an object even without matching properties.

Example of a nested record with defaults:

~~~java
package com.example.configdemo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        @DefaultValue Retry retry) {

    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("250ms") java.time.Duration delay) {
    }
}
~~~

When `app.notification.retry.*` is absent, empty `@DefaultValue` allows Binder to create nested `Retry` with its defaults. On object-creation paths supported by Binder, `onCreate` can observe when a new instance is created without a direct bind result.

Avoid rigidly assuming "`onCreate` definitely runs once for every `@DefaultValue`." Ordering and internal paths depend on Binder, object type, and configuration. In tests, focus on documented callback semantics rather than guessing exact invocation counts in every scenario.

### An implementation note

`onCreate` has a default method on `BindHandler`. If you override a callback not separately declared on `AbstractBindHandler` in your version, check the exact API and ensure proper delegation. Never return null arbitrarily because `onCreate`'s contract requires a non-null replacement result.

## 16. Do Custom Handlers Make @ConfigurationProperties Auto-Reload?

No. `BindHandler` is a callback **within a single binding pass**. If `application.yml` changes after context initialization, having a handler does not cause Spring Boot to automatically re-read Config Data and recreate `@ConfigurationProperties` objects.

In a standard Spring Boot application:

~~~text
Startup
  → load Config Data
  → build Environment
  → bind @ConfigurationProperties
  → create beans
  → application runs
~~~

The handler participates in the bind stage; it does not turn the whole system into a hot-reload engine.

If dynamic configuration updates are required, design a dedicated refresh/lifecycle mechanism with proper synchronization and suitable data sources. Do not use `onSuccess` to swap live beans or "self-update" while requests are being served.

## 17. Testing Handlers Independently with MockEnvironment

To test a handler in isolation, use `MockEnvironment` from `spring-test`. Example testing a handler that observes property names:

~~~java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;

import com.example.configdemo.config.ClientProperties;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.AbstractBindHandler;
import org.springframework.boot.context.properties.bind.BindContext;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
import org.springframework.mock.env.MockEnvironment;

class BindHandlerTest {

    @Test
    void countsSuccessfulClientBindings() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty(
                        "app.client.endpoint",
                        "https://api.example.org")
                .withProperty(
                        "app.client.connect-timeout",
                        "3s")
                .withProperty(
                        "app.client.max-connections",
                        "12")
                .withProperty(
                        "app.client.enabled",
                        "true");

        AtomicInteger count = new AtomicInteger();

        BindHandler counter = new AbstractBindHandler(
                BindHandler.DEFAULT) {

            @Override
            public Object onSuccess(
                    ConfigurationPropertyName name,
                    Bindable<?> target,
                    BindContext context,
                    Object result) {

                if (name.toString().startsWith("app.client.")) {
                    count.incrementAndGet();
                }

                return super.onSuccess(name, target, context, result);
            }
        };

        ClientProperties properties = Binder.get(environment)
                .bind(
                        "app.client",
                        Bindable.of(ClientProperties.class),
                        counter)
                .get();

        assertThat(properties.maxConnections()).isEqualTo(12);
        assertThat(properties.connectTimeout().toSeconds())
                .isEqualTo(3);
        assertThat(count.get()).isGreaterThan(0);
    }
}
~~~

This test does not assume an exact callback count because element counts and traversal may depend on Binder. It verifies the handler observed at least one successful bind under the expected prefix and final data was unaltered.

The test assumes `spring-boot-starter-test`, JUnit Jupiter, and AssertJ. `MockEnvironment` supplies properties without starting a full Spring context.

### Testing conversion failure

Replace:

~~~text
app.client.max-connections=12
~~~

with:

~~~text
app.client.max-connections=many
~~~

If the handler only logs and forwards the error, Binder can throw an exception. Use AssertJ to verify:

~~~java
assertThatThrownBy(() -> Binder.get(environment).bind(
        "app.client",
        Bindable.of(ClientProperties.class),
        handler))
    .isInstanceOf(RuntimeException.class);
~~~

Import `assertThatThrownBy` and create the appropriate `handler` in the test. This snippet illustrates testing the failure path; do not rely on one specific wrapper exception if you want tests to remain stable across framework upgrades.

## 18. Testing an Advisor in a Lightweight Spring Context

To test that a handler is applied **automatically** to configuration properties beans, test with `ApplicationContextRunner` and a configuration containing the advisor.

Configuration example:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
@Import(BindingAdviceConfiguration.class)
class BindingTestConfiguration {
}
~~~

Imports:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
~~~

Conceptual test:

~~~java
ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withUserConfiguration(BindingTestConfiguration.class);

runner.withPropertyValues(
        "app.client.endpoint=https://api.example.org",
        "app.client.connect-timeout=3s",
        "app.client.max-connections=12",
        "app.client.enabled=true")
    .run(context -> {
        ClientProperties properties =
                context.getBean(ClientProperties.class);

        assertThat(properties.maxConnections()).isEqualTo(12);
    });
~~~

The test above verifies runtime binding of the configuration bean. If you need to confirm the advisor was actually invoked, add a test-scoped counter/hook rather than relying on console logs or exact callback counts.

Remember that calling `Binder.get(environment)` manually in a test does not test the advisor; the advisor only affects the configuration pipeline managed by Spring Boot.

## 19. Troubleshooting When a Handler Does Not Run

### 19.1. Forgot to pass handler into Binder.bind

~~~java
Binder.get(environment)
        .bind("app.client", ClientProperties.class);
~~~

This overload does not take a custom handler. To test a dedicated handler, use:

~~~java
Binder.get(environment).bind(
        "app.client",
        Bindable.of(ClientProperties.class),
        handler);
~~~

### 19.2. Confusing manual Binder with @ConfigurationProperties bean

The configuration properties bean was already bound by Spring Boot during bootstrap. Calling `Binder.bind(...)` afterward only creates a second object rather than replacing the existing bean. To apply broadly, use an appropriate `ConfigurationPropertiesBindHandlerAdvisor`.

### 19.3. Wrong prefix filter

A handler filtering `app.clients.` while configuration uses `app.client.` will not log. Verify the exact canonical property name via `name.toString()`.

### 19.4. Callbacks may not fire as expected

`onSuccess` only applies on successful bind, `onCreate` for unbound instance creation, `onFailure` on error paths, and `onFinish` does not run on errors per the API contract. If a property does not exist, do not expect `onSuccess` for that property.

### 19.5. Insufficient log level

In the handler you used:

~~~java
log.debug("Bound {}", name);
~~~

while the application runs with DEBUG disabled. The code executes, just without emitting log lines. In development, you can configure:

~~~yaml
logging:
  level:
    com.example.configdemo.bind: DEBUG
~~~

Do not turn on DEBUG for all framework packages just to observe one small handler unless necessary.

### 19.6. Advisor not registered as a bean

If the factory method for `ConfigurationPropertiesBindHandlerAdvisor` lacks `@Bean` or its class is outside component scan / not imported, the advisor is not applied. Ensure Spring registers the configuration containing the advisor.

### 19.7. Lost parent chain

If you create a new handler and drop `existing`, you risk losing behaviors provided by the existing pipeline. Always use `new ClientTraceBindHandler(existing)` and call `super` in callbacks you want preserved.

### 19.8. Value was overridden by another source

The handler sees the effective binding result, not necessarily a specific YAML file. If CLI supplies `--app.client.max-connections=20`, the result can be 20 instead of 12 in the shared file. Do not blame the handler for "changing the value" when the real cause is PropertySource precedence.

## 20. Comparing BindHandler with Other Extension Mechanisms

| Need | Mechanism to consider |
| --- | --- |
| Define which group a configuration belongs to | `@ConfigurationProperties` |
| Resolve diverse property names | Binder's relaxed binding |
| Convert String to a custom domain type | `Converter` + `@ConfigurationPropertiesBinding` |
| Standard validation | `@Validated` and Jakarta Bean Validation |
| Provide defaults for missing properties | `@DefaultValue` |
| Intercept callbacks in one manual bind | `BindHandler` passed to `Binder.bind` |
| Customize handler for Boot-managed config beans | `ConfigurationPropertiesBindHandlerAdvisor` |
| Detect unbound properties under root | `NoUnboundElementsBindHandler` |
| Ignore specific binding errors per special policy | `IgnoreErrorsBindHandler`, with great caution |
| Load additional config files | `spring.config.import`/Config Data |
| Change source precedence | PropertySource mechanism and startup config |
| Generate IDE suggestion metadata | `spring-boot-configuration-processor` |

From this table, `BindHandler` should not be used as a "Swiss Army knife" for every externalized configuration task. It is useful when the requirement genuinely relates to the **binding lifecycle**.

## 21. Operational and Design Considerations

1. **Never log sensitive values.** Handlers may encounter bound objects or errors holding private data; logging property names is usually enough.
2. **Keep callbacks fast and side-effect-free.** One bind call can cover many elements; heavy I/O in callbacks slows down bootstrap.
3. **Do not assume a fixed callback order.** Never design business state machines around the traversal order of fields in Binder.
4. **Do not modify results arbitrarily.** If `onSuccess` returns an object incompatible with the target type, errors can occur deep inside Binder.
5. **Preserve exceptions unless a clear recovery policy exists.** Swallowing critical configuration errors is usually more dangerous than failing fast.
6. **Preserve the parent handler.** When using an advisor, always wrap the existing handler instead of creating an unrelated pipeline.
7. **Distinguish root from child properties.** Handlers are invoked at multiple levels; filter appropriately when collecting metrics/counts.
8. **Do not use handlers to reload Config Data.** They participate in binding, not file-change monitoring.
9. **Test both success and failure.** Test mistyped conversions, missing properties, unknown properties, and chain behavior.
10. **Enforce policies at the right layer.** Defaults, converters, validation, PropertySources, and BindHandler each have distinct responsibilities.

## 22. Practice Exercises

### Exercise 1 — Log successful property names

Create `ClientTraceBindHandler` extending `AbstractBindHandler`, override `onSuccess`, and log only properties prefixed with `app.client`. Call `super.onSuccess(...)` to preserve the parent. Supply valid YAML, run manual Binder.bind, and observe DEBUG logs.

### Exercise 2 — Inspect conversion errors

Set:

~~~properties
app.client.max-connections=unknown
~~~

Use a handler overriding `onFailure`, logging only the property name and exception class, then calling `super.onFailure(...)`. Explain why errors should not be ignored automatically.

### Exercise 3 — Use an advisor

Register:

~~~java
@Bean
static ConfigurationPropertiesBindHandlerAdvisor advisor() {
    return parent -> new ClientTraceBindHandler(parent);
}
~~~

Enable `@ConfigurationPropertiesScan` and verify the handler runs when Spring Boot creates the `ClientProperties` bean.

### Exercise 4 — Check validation

With `@Min(1) int maxConnections`, set `-2`. Compare using Bean Validation vs. throwing `IllegalStateException` inside `onSuccess`. Choose Bean Validation when only a standard numeric constraint is needed.

### Exercise 5 — Detect unknown keys

Set `app.client.max-connetions=12` (typo). Use `NoUnboundElementsBindHandler` for a manual bind against an enumerable property source and observe the outcome. Explain why strictness should be scoped by prefix.

### Exercise 6 — Try IgnoreErrorsBindHandler

Create a secret-free example with a mistyped value. Compare normal binding vs. `IgnoreErrorsBindHandler`. Identify what can be skipped/null and explain the risk for production configuration.

### Exercise 7 — Test onFinish

Record `onFinish` for a valid property and a mistyped property. Explain why `onFinish` cannot be treated as a `finally` block running on every error per Spring Boot 3.3 documentation.

### Exercise 8 — Count elements, not beans

Override `onSuccess` and increment a counter. Use a record with four components. Observe the callback count and explain why you should not report that counter as "number of `@ConfigurationProperties` beans" without filtering the root.

### Exercise 9 — BindResult when prefix is missing

Call:

~~~java
Binder.get(environment).bind(
        "app.missing",
        Bindable.of(ClientProperties.class),
        new ClientTraceBindHandler(BindHandler.DEFAULT)
);
~~~

When no properties exist under root, inspect `BindResult` status and choose `orElse(...)`/`get()` appropriately. Never assume an object is always returned.

### Exercise 10 — Design question

A team wants to:
- Convert string `vnm` to `RegionCode("VNM")`.
- Reject `max-connections=0`.
- Log property names without secrets.
- Get property suggestions in the IDE.

Pick the right mechanism for each: `Converter`, Bean Validation, `BindHandler`, and `spring-boot-configuration-processor`. Explain why using a single handler for all four is poor design.

## 23. Key Takeaways

- `BindHandler` provides callbacks to customize the **binding lifecycle**, without altering how Spring Boot loads Config Data or `PropertySource` precedence.
- In Spring Boot 3.3, callbacks include `onStart`, `onSuccess`, `onCreate`, `onFailure`, and `onFinish`.
- `AbstractBindHandler` helps build decorators with a parent; for observational handlers, call `super` to preserve original behavior.
- `Binder.get(environment).bind(prefix, Bindable.of(Type.class), handler)` applies the handler only to **that bind call**.
- `ConfigurationPropertiesBindHandlerAdvisor` lets you wrap the handler Spring Boot uses when creating `@ConfigurationProperties` beans. Never replace parent with `BindHandler.DEFAULT` when the existing pipeline must be preserved.
- `onSuccess` can add checks or transform results; `onFailure` can handle errors but should not swallow them arbitrarily. `onFinish` is not called on failed bindings.
- `IgnoreErrorsBindHandler` and `NoUnboundElementsBindHandler` are built-in handlers for different policies; understand their scope before using them.
- For straightforward validation, prefer `@Validated` + Bean Validation. For custom domain types, prefer converters. Only use custom handlers when you genuinely need to intercept the Binder lifecycle.
- Never log sensitive configuration values, do not rely on callback order, and do not treat BindHandler as a hot-reload mechanism.

## References

- [Spring Boot 3.3 — BindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindHandler.html)
- [Spring Boot 3.3 — AbstractBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/AbstractBindHandler.html)
- [Spring Boot 3.3 — Binder API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html)
- [Spring Boot 3.3 — ConfigurationPropertiesBindHandlerAdvisor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBindHandlerAdvisor.html)
- [Spring Boot 3.3 — NoUnboundElementsBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/handler/NoUnboundElementsBindHandler.html)
- [Spring Boot 3.3 — IgnoreErrorsBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/handler/IgnoreErrorsBindHandler.html)
- [Spring Boot 3.3 — ValidationBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/validation/ValidationBindHandler.html)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
