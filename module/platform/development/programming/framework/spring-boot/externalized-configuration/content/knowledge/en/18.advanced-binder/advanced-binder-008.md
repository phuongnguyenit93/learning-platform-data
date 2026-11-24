# Validation and Detecting Unbound Data via BindHandler in Spring Boot

## 1. Why Do We Need Deeper Checks Beyond a Normal Bind?

Spring Boot lets applications read configuration from many sources: `application.yml`, `application.properties`, environment variables, Java system properties, command-line arguments, and other `PropertySource`s. With `@ConfigurationProperties`, an application can map such property groups onto a strongly typed Java class or record.

Example:

~~~yaml
demo:
  worker:
    threads: 4
    timeout: 5s
    enabled: true
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.worker")
public record WorkerSettings(
        int threads,
        Duration timeout,
        boolean enabled
) {}
~~~

If everything aligns, Binder converts `threads` into `int`, `timeout` into `Duration`, and `enabled` into `boolean`.

However, simply binding data does not guarantee the configuration is valid:

**Scenario A — Type-valid value that breaks business rules**

~~~yaml
demo:
  worker:
    threads: 0
    timeout: 0s
    enabled: true
~~~

`0` is still a valid integer; `0s` still converts to `Duration.ZERO`. Yet both may be invalid for a worker pool.

**Scenario B — Deployer mistypes a property name**

~~~yaml
demo:
  worker:
    threads: 4
    timeout: 5s
    enabled: true
    threds: 12
~~~

`threds` is not a field name of `WorkerSettings`. Normal binding can ignore this unmapped property, leaving the deployer thinking 12 threads were configured while the app runs with 4.

**Scenario C — Wrong type right at conversion**

~~~yaml
demo:
  worker:
    threads: many
    timeout: 5s
~~~

`many` cannot convert to `int`, so binding can fail before business checks run.

Spring Boot provides the **`BindHandler`** interface and specialized implementations to intercept the binding lifecycle. Two key handlers for this lesson are:

- **`ValidationBindHandler`:** applies `Validator` instances to the bound result, catching values that violate rules.
- **`NoUnboundElementsBindHandler`:** detects properties under the configuration root that were not bound into the target.

These two mechanisms solve **two different classes of errors**; in certain cases they can be combined to build a stricter configuration pipeline.

## 2. Distinguishing Four States of a Property

| State | Example | Primary issue |
| --- | --- | --- |
| Bound and valid | `threads=4`, rule ≥ 1 | No error |
| Bound but violates constraint | `threads=0` with rule ≥ 1 | Validation |
| Cannot convert type | `threads=many`, target `int` | Conversion/binding failure |
| Property not bound | `threds=12` when class only has `threads` | Unbound/unknown property |

You should also distinguish **a completely missing required property**. For example, omitting `demo.worker.timeout` does not necessarily create an *unbound element*, because there is no input element to report as left over. Missing required properties should be caught using reference types, validation, or configuration contract checks.

Handling mechanisms:

| Goal | Commonly used tool |
| --- | --- |
| Detect wrong type | Default Binder and conversion |
| Detect type-valid value breaking rules | `ValidationBindHandler` or `@Validated` with Bean Validation |
| Detect config keys under root not bound | `NoUnboundElementsBindHandler` |
| Observe successfully bound properties | `BoundPropertiesTrackingBindHandler` or custom handler |
| Set defaults when properties are absent | `@DefaultValue`, code defaults, or placeholders |
| Perform structured binding | `Binder`/`@ConfigurationProperties` |

**Do not use a single handler to replace all other mechanisms.** For instance, `NoUnboundElementsBindHandler` does not decide that thread count must be positive, while `ValidationBindHandler` does not automatically infer that every typo key must be rejected.

## 3. Where Does `BindHandler` Fit in Binder's Architecture?

When invoking `Binder` directly, Spring Boot provides an overload accepting a handler:

~~~java
<T> BindResult<T> bind(
        String name,
        Bindable<T> target,
        BindHandler handler
);
~~~

Meaning:

- `name` is the root prefix, e.g., `"demo.worker"`.
- `target` describes the Java type to bind, e.g., `Bindable.of(WorkerSettings.class)`.
- `handler` receives callbacks during binding.
- `BindResult<T>` indicates whether a result was bound and exposes APIs to retrieve it.

Illustrative example:

~~~java
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;

Binder binder = /* Binder obtained from configuration sources */;

BindResult<WorkerSettings> result =
        binder.bind(
                "demo.worker",
                Bindable.of(WorkerSettings.class),
                BindHandler.DEFAULT
        );

WorkerSettings settings = result.get();
~~~

`BindHandler.DEFAULT` is a handler adding no special rules. If no data binds, `BindResult#get()` reports a missing result; for optional handling, use `isBound()`, `orElse(...)`, or equivalent `BindResult` methods.

In ordinary Spring Boot apps using `@ConfigurationProperties`, the framework already has its own binding workflow. **Constructing `Binder` manually** is useful when writing libraries, testing configuration independently, binding a special namespace, or applying a handler to one specific bind call.

You do not need to replace the application's entire `@ConfigurationProperties` mechanism just to turn on validation or reject unknown fields.

## 4. Callbacks of `BindHandler`

`BindHandler` is a callback interface. In Spring Boot 3.3, key methods include:

| Callback | When called | Purpose |
| --- | --- | --- |
| `onStart(...)` | Before binding an element | Observe name/target, adjust bindable if truly needed |
| `onSuccess(...)` | When an element binds successfully | Record result, add processing or validation |
| `onCreate(...)` | When a new instance is about to be returned for an unbound result | Process Binder-created instance |
| `onFailure(...)` | When a binding step encounters an error | Report, transform, or in special cases handle error |
| `onFinish(...)` | When element binding finishes normally | Perform final handling for the bind step |

Callbacks receive objects such as:

~~~java
ConfigurationPropertyName name
Bindable<?> target
BindContext context
Object result
Exception error
~~~

Where:

- `ConfigurationPropertyName` represents configuration names in Spring Boot's model.
- `Bindable<?>` represents the target type and related binding metadata.
- `BindContext` carries state/information for the ongoing binding pass.
- `result` is the result at callback time; it may be an intermediate object or the final object.
- `error` is the cause when binding fails.

**Do not assume every callback runs only once for the root.** Binder traverses fields, collection items, and nested objects, so callbacks can fire at multiple property-name levels.

Additionally, `onFinish` is not a Java `finally` block running regardless of errors: per the API contract, it is not invoked along failure paths even if a handler handles the error via `onFailure`. Do not rely on it as the sole place to release critical resources.

## 5. `AbstractBindHandler` and the Nested Handler Model

Instead of implementing every method of `BindHandler`, you can extend `AbstractBindHandler`:

~~~java
import org.springframework.boot.context.properties.bind.AbstractBindHandler;
import org.springframework.boot.context.properties.bind.BindHandler;

BindHandler observingHandler =
        new AbstractBindHandler(BindHandler.DEFAULT) {
            // Override only the callbacks actually needed.
        };
~~~

`AbstractBindHandler` supports a **parent/delegate** mechanism. To layer logic onto an existing handler, pass the old handler as parent:

~~~text
Outer Handler
      │
      ▼
Parent Handler
      │
      ▼
BindHandler.DEFAULT
~~~

This is particularly useful when composing multiple responsibilities:

- One handler for validation.
- One handler to detect unbound elements.
- One project-specific handler to record metrics or audit property names.

How handlers are nested affects callback order and which error surfaces first when multiple errors occur simultaneously. Do not assume swapping two handlers is always equivalent, especially if a custom handler swallows exceptions in `onFailure` or mutates results.

A safe rule: **observation handlers should delegate normally; handlers altering results or ignoring errors should only be used with specific requirements and clear tests**.

## 6. `ValidationBindHandler`: Applying Validators After Binding

Class:

~~~java
org.springframework.boot.context.properties.bind.validation.ValidationBindHandler
~~~

It is a `BindHandler` designed to run `org.springframework.validation.Validator` instances on bound results.

Two typical constructors:

~~~java
new ValidationBindHandler(validator);

new ValidationBindHandler(parentHandler, validator);
~~~

Here `validator` is one or more Spring `Validator` instances, not merely an annotation name.

Example:

~~~java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class WorkerSettingsValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return WorkerSettings.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        WorkerSettings settings = (WorkerSettings) target;

        if (settings.threads() < 1) {
            errors.rejectValue(
                    "threads",
                    "worker.threads.invalid",
                    "threads must be at least 1"
            );
        }

        if (settings.timeout() == null
                || settings.timeout().isZero()
                || settings.timeout().isNegative()) {
            errors.rejectValue(
                    "timeout",
                    "worker.timeout.invalid",
                    "timeout must be positive"
            );
        }
    }
}
~~~

This is a **custom Spring Validator** checking the object after values have been converted to Java types. It spares developers from manually parsing `"5s"`.

Example using the handler:

~~~java
BindHandler handler = new ValidationBindHandler(
        new WorkerSettingsValidator()
);

WorkerSettings settings = binder.bind(
        "demo.worker",
        Bindable.of(WorkerSettings.class),
        handler
).get();
~~~

If `threads=0` or `timeout=0s`, the validator can record errors; `ValidationBindHandler` feeds those errors into the binding flow, failing the call per the validation contract.

If `threads=many`, conversion to `int` can fail before the validator ever receives a complete object. That is a **binding/conversion failure**, not a "threads must be greater than 0" error.

## 7. Configuration Model Used in Examples

To keep subsequent examples consistent, we use the record:

~~~java
package com.example.demo.config;

import java.time.Duration;

public record WorkerSettings(
        int threads,
        Duration timeout,
        boolean enabled
) {}
~~~

When calling Binder manually, this record **does not require** `@ConfigurationProperties`, because `binder.bind("demo.worker", Bindable.of(WorkerSettings.class), handler)` explicitly passes the root prefix and type.

When using a standard `@ConfigurationProperties` bean, you can declare:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.worker")
public record WorkerSettings(
        int threads,
        Duration timeout,
        boolean enabled
) {}
~~~

In Spring Boot 3.x, a record with a suitable canonical constructor can be constructor-bound when registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

**Both examples share the same schema but follow different paths:** one **calls Binder directly**, while the other **lets Spring Boot manage the configuration bean**. Distinguish these two paths when enabling validation and handlers.

## 8. Creating Binder Directly from a MapPropertySource

To focus on handler behavior, the simplest setup uses an independent data source capable of enumerating keys.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;

Map<String, Object> values = new LinkedHashMap<>();

values.put("demo.worker.threads", "4");
values.put("demo.worker.timeout", "5s");
values.put("demo.worker.enabled", "true");

MapPropertySource propertySource =
        new MapPropertySource("example", values);

Binder binder = new Binder(
        ConfigurationPropertySources.from(propertySource)
);
~~~

Explanation:

1. `MapPropertySource` is a Spring `PropertySource` holding key/value pairs.
2. `ConfigurationPropertySources.from(propertySource)` provides an adapter so Binder reads them as `ConfigurationPropertySource`.
3. `new Binder(...)` constructs a Binder for that exact test source.
4. The handler passed to `binder.bind(...)` applies to that specific bind call.

Benefits of a dedicated test source:

- Does not accidentally pick up values from the machine's environment variables.
- Prevents other app properties from polluting the tested namespace.
- Easy to construct valid/invalid/unknown cases individually.
- Ideal for unit testing Binder/handler behavior without starting a web server.

`Binder` has other constructors and overloads, plus `Binder.get(Environment)` where appropriate. For handler lessons, however, an explicit Map source makes behavior easier to observe.

## 9. End-to-End Example Using `ValidationBindHandler`

Assume `WorkerSettings` and `WorkerSettingsValidator` from earlier sections.

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.validation.ValidationBindHandler;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;

public final class ValidationDemo {

    public static void main(String[] args) {
        Map<String, Object> data = Map.of(
                "demo.worker.threads", "6",
                "demo.worker.timeout", "8s",
                "demo.worker.enabled", "true"
        );

        Binder binder = new Binder(
                ConfigurationPropertySources.from(
                        new MapPropertySource("demo", data)
                )
        );

        BindHandler handler = new ValidationBindHandler(
                new WorkerSettingsValidator()
        );

        WorkerSettings settings = binder.bind(
                "demo.worker",
                Bindable.of(WorkerSettings.class),
                handler
        ).get();

        System.out.println(settings.threads());
        System.out.println(settings.timeout());
    }
}
~~~

When the supporting types and classes are on the classpath, the illustrative output is:

~~~text
6
PT8S
~~~

Change:

~~~java
"demo.worker.threads", "0"
~~~

and the `threads >= 1` rule is violated. The program receives a validation exception during binding instead of a valid `WorkerSettings`.

If you change to:

~~~java
"demo.worker.threads", "many"
~~~

the converter cannot produce an `int`, even though `WorkerSettingsValidator` exists. Inspect the error cause to distinguish **conversion** from **validation**.

## 10. `NoUnboundElementsBindHandler`: Detecting Unused Keys

Class:

~~~java
org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler
~~~

Primary role: **require all configuration properties under the bound root to be bound**.

Example source:

~~~properties
demo.worker.threads=4
demo.worker.timeout=5s
demo.worker.enabled=true
demo.worker.threds=12
~~~

Target:

~~~java
public record WorkerSettings(
        int threads,
        Duration timeout,
        boolean enabled
) {}
~~~

The first three keys have matching targets. The last key `threds` is a typo with no component in `WorkerSettings`.

When binding with a normal handler, depending on policy, the typo might not fail the call. However:

~~~java
BindHandler handler = new NoUnboundElementsBindHandler(
        BindHandler.DEFAULT
);
~~~

can detect that `demo.worker.threds` remained unbound and report an error.

**Checking scope:** this handler examines properties **under the root of the bind call**. It is not a tool to audit the application's entire `Environment`, and it does not detect missing properties that never existed in the source.

It requires a configuration source capable of enumerating/resolving property names appropriately. A `MapPropertySource` with explicit names is a good choice for illustration and testing.

## 11. Complete Example Detecting Unbound Elements

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;

Map<String, Object> data = new LinkedHashMap<>();
data.put("demo.worker.threads", "4");
data.put("demo.worker.timeout", "5s");
data.put("demo.worker.enabled", "true");
data.put("demo.worker.threds", "12"); // intentional typo

Binder binder = new Binder(
        ConfigurationPropertySources.from(
                new MapPropertySource("demo", data)
        )
);

BindHandler strictHandler =
        new NoUnboundElementsBindHandler(BindHandler.DEFAULT);

WorkerSettings settings = binder.bind(
        "demo.worker",
        Bindable.of(WorkerSettings.class),
        strictHandler
).get();
~~~

When the handler successfully identifies `demo.worker.threds` as unbound, the call throws an exception rather than returning `settings`.

The exception type that may appear in the cause chain is:

~~~text
UnboundConfigurationPropertiesException
~~~

This class has `getUnboundProperties()` to access the set of leftover `ConfigurationProperty` entries. At the Binder layer, the exception may be wrapped in `BindException` or another configuration exception. Do not assume that class appears at the top level; inspect the cause chain in tests.

**Important:** `NoUnboundElementsBindHandler` does not detect typos via fuzzy string matching. It identifies **properties that were not bound**. Recognizing it as a "typo" is a human interpretation when reading `threds`.

## 12. Comparing an Ignored Property vs. a Completely Missing Property

Two cases:

### 12.1. Extra property

~~~properties
demo.worker.threads=4
demo.worker.timeout=5s
demo.worker.enabled=true
demo.worker.unused-setting=hello
~~~

`unused-setting` is present but has no target in `WorkerSettings`. `NoUnboundElementsBindHandler` can report that it was not bound.

### 12.2. Missing required property

~~~properties
demo.worker.threads=4
demo.worker.enabled=true
~~~

`demo.worker.timeout` is absent. Because it does not exist, there is no "extra" key for the unbound handler to list.

If `timeout` is required, use one of these approaches:

- `@NotNull` on `Duration timeout` with validation on an appropriate bean creation path.
- A Spring `Validator` in `ValidationBindHandler` checking `settings.timeout() != null`.
- Invariant checks in the constructor.
- A schema/configuration validation mechanism with stricter rules.

**Conclusion:** "no extra keys" and "no missing required keys" are **two independent conditions**.

## 13. Combining `ValidationBindHandler` and `NoUnboundElementsBindHandler`

To validate values and detect leftover properties in one bind pass, nest handlers via parent delegation:

~~~java
BindHandler combined = new NoUnboundElementsBindHandler(
        new ValidationBindHandler(
                new WorkerSettingsValidator()
        )
);
~~~

Then:

~~~java
WorkerSettings settings = binder.bind(
        "demo.worker",
        Bindable.of(WorkerSettings.class),
        combined
).get();
~~~

Meaning:

1. `ValidationBindHandler` uses `WorkerSettingsValidator` to validate bound values.
2. `NoUnboundElementsBindHandler` requires no properties under the root are left behind.
3. If both sets of checks pass, Binder returns `WorkerSettings`.

This is a composition example using public constructors in Spring Boot 3.x. Wrapper ordering can affect which callback/error surfaces first when multiple errors exist simultaneously. Do not expect all errors to be aggregated into a single list in one bind pass.

Another possible nesting order:

~~~java
BindHandler combined = new ValidationBindHandler(
        new NoUnboundElementsBindHandler(BindHandler.DEFAULT),
        new WorkerSettingsValidator()
);
~~~

Both express handlers with a parent relationship, though callback ordering may differ. If a project requires an exact detection order or stable error format, write tests for the chosen order and actual Spring Boot version.

Do not swap handler order merely to "make a red test turn green" without understanding its impact on callbacks and error propagation.

## 14. Example of a Strict Bind Utility

A reusable utility for a standalone configuration group:

~~~java
package com.example.demo.config;

import java.util.Map;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler;
import org.springframework.boot.context.properties.bind.validation.ValidationBindHandler;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;

public final class StrictConfigLoader {

    private StrictConfigLoader() {}

    public static WorkerSettings load(Map<String, Object> properties) {
        Binder binder = new Binder(
                ConfigurationPropertySources.from(
                        new MapPropertySource("strict-config", properties)
                )
        );

        BindHandler handler = new NoUnboundElementsBindHandler(
                new ValidationBindHandler(
                        new WorkerSettingsValidator()
                )
        );

        return binder.bind(
                "demo.worker",
                Bindable.of(WorkerSettings.class),
                handler
        ).get();
    }
}
~~~

Call:

~~~java
Map<String, Object> config = Map.of(
        "demo.worker.threads", "4",
        "demo.worker.timeout", "5s",
        "demo.worker.enabled", "true"
);

WorkerSettings worker = StrictConfigLoader.load(config);
~~~

With valid values and no extra properties, the expected result is a record holding 4, 5 seconds, and `true`.

Changing `threads=0` causes validation to fail.

Adding `demo.worker.threds=12` allows the unbound handler to catch the extra key.

Changing `threads=abc` causes conversion to fail before the remaining checks run.

This illustrates a **design principle**: a utility taking an explicit source, explicit type, and two handlers with independent responsibilities. Do not blindly apply this utility across every namespace of a large application without establishing configuration key ownership.

## 15. `NoUnboundElementsBindHandler` and `ignoreUnknownFields=false`

For a Spring Boot-managed `@ConfigurationProperties` bean, you can disallow unknown fields via annotation:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "demo.worker",
        ignoreUnknownFields = false
)
public record WorkerSettings(
        int threads,
        java.time.Duration timeout,
        boolean enabled
) {}
~~~

This is a more concise declaration when **you only need strict unknown-field checking on a standard configuration properties bean**.

Comparison table:

| Situation | Approach to use |
| --- | --- |
| Class registered via `@ConfigurationPropertiesScan`, want to catch unknown fields | `ignoreUnknownFields = false` |
| Manually calling `Binder.bind(...)` for a custom source | `NoUnboundElementsBindHandler` |
| Want to validate values with `@Min`, `@NotNull`, etc. | `@Validated` and Jakarta Bean Validation |
| Manually calling Binder and want to check with a Spring `Validator` | `ValidationBindHandler` |
| Want to observe binding callbacks for a custom API | Custom `BindHandler` or tracking handler |

`ignoreUnknownFields` on `@ConfigurationProperties` and `NoUnboundElementsBindHandler` share the concept of **detecting unbindable properties**. However, do not assume every configuration/source/Binder path uses the exact same internal handler choice or produces identical error formats across all versions.

A `@ConfigurationProperties` class also has `ignoreInvalidFields`, which is a **different** option:

~~~java
@ConfigurationProperties(
        prefix = "demo.worker",
        ignoreUnknownFields = false,
        ignoreInvalidFields = false
)
~~~

- `ignoreUnknownFields=false`: does not permit unbindable keys within the applicable scope.
- `ignoreInvalidFields=false`: conversion/binding errors are not intentionally ignored by this option.

For critical configurations, keeping strict binding and validation helps catch errors early.

## 16. `@Validated` in Standard Bean Management

A configuration record can be declared as:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "demo.worker",
        ignoreUnknownFields = false
)
public record WorkerSettings(
        @Min(1) @Max(32) int threads,
        @NotNull Duration timeout,
        boolean enabled
) {}
~~~

Bean registration:

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

Validation dependency declaration (Spring Boot 3.x):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

If `application.yml` has `threads=0`, Bean Validation can reject the config via `@Min(1)`.

If `demo.worker.threds=12` is present, `ignoreUnknownFields=false` can reject the extra key.

If `timeout=tomorrow`, conversion to `Duration` fails without waiting for Bean Validation.

Key takeaway: **using `@Validated` on a `@ConfigurationProperties` bean and using `ValidationBindHandler` in manual Binder are two different usage paths**. They share validation infrastructure but must not be equated as the same API call.

## 17. Limitation: `@Validated` Does Not Guarantee Every Property Was Bound

Consider:

~~~yaml
demo:
  worker:
    threads: 4
    timeout: 5s
    enabled: true
    extra-key: ignored
~~~

Record:

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.worker")
public record WorkerSettings(
        @Min(1) int threads,
        @NotNull Duration timeout,
        boolean enabled
) {}
~~~

Without a policy rejecting unknown fields, `@Min`/`@NotNull` constraints can **pass** even though `extra-key` was ignored. Validation checks **the object after binding**, not inventorying every property name across all sources.

To protect both simultaneously:

1. Business-valid values.
2. No unbound keys within the root scope.

You can use:

~~~java
@Validated
@ConfigurationProperties(
        prefix = "demo.worker",
        ignoreUnknownFields = false
)
~~~

in the standard bean path, or compose the two handlers when invoking Binder directly.

Do not judge configuration completeness solely by whether a bean passed validation. A mistyped property may have zero effect on the object while the object still passes basic constraints thanks to other values or defaults.

## 18. `NoUnboundElementsBindHandler` Does Not Catch Every Typo in the System

The handler detects properties under **the root being bound** that were not consumed. For example:

~~~text
Root being bound: demo.worker

demo.worker.threads           → in scope
demo.worker.threds            → in scope, can be unbound
demo.worker-extra.threads     → not same root
demo.server.port              → not same root
spring.datasource.url         → belongs to another namespace
~~~

If a typo moves a property into a **different namespace**, a handler invoked for `demo.worker` will not necessarily catch it.

Example:

~~~properties
demo.workers.threads=4
~~~

while code binds `demo.worker`. This sits completely **outside the root**. If no keys exist under `demo.worker`, the result may simply be unbound rather than listing an unbound property.

Therefore, for mandatory configurations, combine:

- Checking that the root has data or an object was bound.
- Checking required fields/validation.
- Checking unbound properties under the exact root.
- Documenting prefixes and configuration schemas to reduce typos.

The handler is not a substitute for a system-wide schema linter inventorying every property.

## 19. Limitation: Configuration Sources Must Support Property Enumeration

`NoUnboundElementsBindHandler` needs to identify which properties under the root were not processed by Binder. Some sources support **enumerating property names**, while others only support lookup by name.

For instance, `MapPropertySource` has an explicit key set, ideal for tests. However, a custom source may not provide complete enumeration information. In that case, unbound property detection can be limited or behave differently than expected.

Do not write an integration test using `MapPropertySource` and conclude the handler will report every unused key from any arbitrary custom config backend.

For production configuration:

1. Know which property sources participate in Binder.
2. Know which sources can enumerate names.
3. Identify the root prefix to inspect.
4. Verify any filter if used.
5. Test with the real source type or a test accurately modeling its enumeration capability.

If a legal or operational requirement states "no leftover properties may exist in any source," add an out-of-band **source schema lint/validation** step rather than treating a runtime BindHandler as a global auditor.

## 20. Filtering Sources When Detecting Unbound Properties

`NoUnboundElementsBindHandler` has a constructor accepting a source filter function:

~~~java
new NoUnboundElementsBindHandler(
        parentHandler,
        source -> /* true if source should be checked */
);
~~~

In Spring Boot 3.3, the filter parameter has the conceptual form:

~~~java
Function<ConfigurationPropertySource, Boolean>
~~~

Depending on implementation, the filter lets you direct which configuration sources are examined when detecting unbound elements.

Syntax illustration:

~~~java
BindHandler handler = new NoUnboundElementsBindHandler(
        BindHandler.DEFAULT,
        source -> true
);
~~~

This example includes all sources matching the passed predicate, yet **does not magically make non-enumerable sources enumerable**. On a large `Environment`, `source -> true` may be inappropriate because many namespaces are shared and sources hold properties unrelated to the current bean.

Best practices:

- Prefer a `MapPropertySource` or isolated source set for specialized configuration libraries.
- If using a filter, state source-exclusion criteria clearly and write tests for the inspected property list.
- Avoid filters relying on unstandardized source names or unstable implementation details.
- Never pass `source -> false` thinking unknown-field checking is still active: that can effectively disable unbound detection.

## 21. A Handler Observing Bound Properties

Spring Boot provides a handler to observe successfully bound properties:

~~~java
org.springframework.boot.context.properties.bind.BoundPropertiesTrackingBindHandler
~~~

Usage idea:

~~~java
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.BoundPropertiesTrackingBindHandler;

BindHandler tracking = new BoundPropertiesTrackingBindHandler(
        property -> {
            System.out.println("Bound property: " + property.getName());
        }
);
~~~

`BoundPropertiesTrackingBindHandler` accepts a `ConfigurationProperty` consumer. It is useful for collecting the **names** of bound properties for diagnostics or metrics.

However, it does not validate values or reject extra properties. It can be combined with:

~~~java
new ValidationBindHandler(...)
new NoUnboundElementsBindHandler(...)
~~~

Security note: do not log all `ConfigurationProperty` values, as they can contain passwords, tokens, or sensitive data. Even property **names** might embed tenant IDs or internal paths. Observation must follow the system's logging policy.

## 22. Writing a Custom `BindHandler` to Add Auditing

A small custom handler can extend `AbstractBindHandler` and observe names only:

~~~java
import org.springframework.boot.context.properties.bind.AbstractBindHandler;
import org.springframework.boot.context.properties.bind.BindContext;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;

public final class LoggingBindHandler extends AbstractBindHandler {

    public LoggingBindHandler(BindHandler parent) {
        super(parent);
    }

    @Override
    public Object onSuccess(
            ConfigurationPropertyName name,
            Bindable<?> target,
            BindContext context,
            Object result) {

        System.out.println("Bound name: " + name);

        return super.onSuccess(name, target, context, result);
    }
}
~~~

Usage:

~~~java
BindHandler handler = new LoggingBindHandler(
        new NoUnboundElementsBindHandler(
                new ValidationBindHandler(
                        new WorkerSettingsValidator()
                )
        )
);
~~~

Here the outer handler prints successfully bound property names and delegates to parent. There is no need to override `onFailure` unless error handling must change.

**Crucial point:** do not accidentally write an `onFailure` that returns an arbitrary default for all exceptions; doing so can mask conversion, validation, or unknown-property errors and let misconfiguration proceed.

In production, logging property names for every bind operation can be noisy. Prefer controlled debug logging, aggregate metrics, or scoped audits instead of printing every name at startup.

## 23. Do Not Confuse `IgnoreErrorsBindHandler` with Validation or Strict Unknown Checking

Spring Boot provides handlers whose names reflect different error policies, such as:

~~~text
IgnoreErrorsBindHandler
IgnoreTopLevelConverterNotFoundBindHandler
ValidationBindHandler
NoUnboundElementsBindHandler
~~~

They are not interchangeable.

- `IgnoreErrorsBindHandler` ignores ignorable binding errors.
- `IgnoreTopLevelConverterNotFoundBindHandler` handles a specific root-level converter condition.
- `ValidationBindHandler` checks results with a validator.
- `NoUnboundElementsBindHandler` requires no properties under root are left unused.

Combining an error-ignoring handler with a strict handler can yield unpredictable semantics unless ordering and conditions are well-defined. For example, an ignored conversion error can leave a property without a value; whether it still counts as bound or gets flagged as unused depends on how handlers and Binder interact.

When **fail fast** on misconfiguration is required, do not add ignore handlers just to cut down exceptions.

## 24. Testing Handlers with Three Essential Cases

A minimal test suite should cover:

1. Valid configuration: binds successfully.
2. Type-valid configuration breaking rules: validation fails.
3. Configuration with extra properties: strict unbound checking fails.

JUnit 5/AssertJ tests for the `StrictConfigLoader` utility:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class StrictConfigLoaderTest {

    @Test
    void bindsValidConfiguration() {
        WorkerSettings settings = StrictConfigLoader.load(
                Map.of(
                        "demo.worker.threads", "4",
                        "demo.worker.timeout", "5s",
                        "demo.worker.enabled", "true"
                )
        );

        assertThat(settings.threads()).isEqualTo(4);
    }

    @Test
    void rejectsBusinessRuleViolation() {
        assertThatThrownBy(() -> StrictConfigLoader.load(
                Map.of(
                        "demo.worker.threads", "0",
                        "demo.worker.timeout", "5s",
                        "demo.worker.enabled", "true"
                )
        )).isInstanceOf(RuntimeException.class);
    }

    @Test
    void rejectsUnboundProperty() {
        assertThatThrownBy(() -> StrictConfigLoader.load(
                Map.of(
                        "demo.worker.threads", "4",
                        "demo.worker.timeout", "5s",
                        "demo.worker.enabled", "true",
                        "demo.worker.threds", "10"
                )
        )).isInstanceOf(RuntimeException.class);
    }
}
~~~

The tests use a very broad exception type to demonstrate behavior. In real projects, add assertions **on the cause chain and property names** per your Spring Boot version so tests prove the right root cause rather than any `RuntimeException`.

Beyond those three cases, also test:

- Conversion errors (e.g., `threads=many`).
- Missing required properties (e.g., timeout).
- Invalid nested objects.
- Extra properties inside a nested prefix.
- Multiple property sources sharing names with different precedence.
- Non-enumerable sources.
- Root having no properties at all.

You do not need to run every test for every configuration class, but maintain at least one representative suite for the strict-binding policy if it is part of the deployment contract.

## 25. Testing Nested Objects

Suppose the configuration is:

~~~yaml
demo:
  gateway:
    endpoint: https://gateway.example.org
    retry:
      max-attempts: 3
      backoff: 2s
~~~

Java:

~~~java
import java.time.Duration;

public record GatewaySettings(
        String endpoint,
        Retry retry
) {
    public record Retry(int maxAttempts, Duration backoff) {}
}
~~~

An extra property:

~~~properties
demo.gateway.retry.max-attempts=3
demo.gateway.retry.backoff=2s
demo.gateway.retry.max-attemtps=10
~~~

When binding root `demo.gateway` with `NoUnboundElementsBindHandler` and an enumerable source, the typo key under `retry` can be detected. This prevents settings from being silently skipped in multi-level structures.

However, **value validity inside nested objects** still belongs to the validator. For example, `max-attempts=-2` converts to `int` yet is invalid; `NoUnboundElementsBindHandler` does not decide that rule.

For nested validation, you can:

- Write a Spring `Validator` supporting `GatewaySettings` and inspecting `retry`.
- Use Jakarta Bean Validation with `@Valid` and `@Validated` in the `@ConfigurationProperties` pipeline.
- Or enforce validation invariants in constructors when rules are simple.

Do not assume a validator supporting only `WorkerSettings` will automatically check `GatewaySettings` and every nested type.

## 26. Testing Collections and Maps

Complex-structured sources:

~~~yaml
demo:
  destinations:
    - name: catalog
      timeout: 3s
    - name: inventory
      timeout: 5s
  labels:
    region: asia
    environment: prod
~~~

Java:

~~~java
public record RouteSettings(
        java.util.List<Destination> destinations,
        java.util.Map<String, String> labels
) {
    public record Destination(String name, Duration timeout) {}
}
~~~

With lists and maps:

- Flattened list names can use `destinations[0].name`.
- Scalar maps can use `labels.region`.
- When Map keys contain dots or special symbols, understand Binder's bracket notation rules.
- Unknown elements inside a list item can be caught when the source and handler support enumerating property names.
- Per-element validation requires an appropriate validator or cascaded Bean Validation in the bean model.

For instance, a typo `destinations[1].timeot=5s` has no matching field on `Destination.timeout`. The unbound handler can help catch it, while the validator can enforce that each item's timeout is non-null and positive.

For collections, avoid claiming Binder always merges lists from property sources. Lists usually follow replacement semantics from the highest-precedence source, whereas maps have different key-merging semantics. This affects the set of properties the handler sees during binding.

## 27. Property Source Precedence Still Matters

Suppose:

~~~yaml
# application.yml
demo:
  worker:
    threads: 4
~~~

An environment variable has:

~~~bash
DEMO_WORKER_THREADS=0
~~~

When Binder reads configuration from the Spring Boot app's `Environment`, environment variables usually take precedence over Config Data. The final value for `demo.worker.threads` can be 0, triggering a validator failure.

`ValidationBindHandler` checks the **effective bound result** according to Binder's source precedence, not merely one file's values.

With `NoUnboundElementsBindHandler`, distinguish:

- Same property name appearing in multiple sources: that is normally an **override**, not automatically an extra-property error.
- Different property names under the same namespace: possibly extra keys or typos.
- Aliases/canonical names and how adapters handle names can affect binding tracking.

Do not configure a handler to treat every property overridden by a higher-precedence source as "unbound." What operators need is **no unknown keys** in the schema, not disallowing shared names across sources.

## 28. Obtaining Binder from `Environment` in an Application

In Spring Boot 3.3, `Binder` has a method to obtain a Binder from `Environment`:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public class BinderUsage {

    public static Binder fromEnvironment(Environment environment) {
        return Binder.get(environment);
    }
}
~~~

This lets Binder see configurations loaded into `Environment` by Spring Boot.

However:

- This is a **broader set of sources** than an isolated test `MapPropertySource`.
- Keys under the same prefix may belong to other components.
- Precedence and aliases depend on sources in the real environment.
- Never run a global binder with a strict handler on an overly broad root like `"spring"` demanding zero unbound properties.
- Custom property sources may not enumerate keys like a test map.

For dedicated configuration libraries, a standalone `MapPropertySource` and narrow root are easier to control. For application `@ConfigurationProperties` beans, prefer Boot's standard mechanisms and annotations before building a custom Binder pipeline.

## 29. Distinguishing Spring Validator from Jakarta Bean Validation

There are two common validation approaches:

**A. Custom Spring `Validator`**

~~~java
public final class WorkerSettingsValidator
        implements org.springframework.validation.Validator {
    // supports(...) and validate(...) defined by the project.
}
~~~

Passed into:

~~~java
new ValidationBindHandler(new WorkerSettingsValidator())
~~~

**B. Jakarta Bean Validation on `@ConfigurationProperties`**

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.worker")
public record WorkerSettings(
        @Min(1) int threads,
        @NotNull Duration timeout
) {}
~~~

Approach B requires a suitable runtime Bean Validation provider, usually via `spring-boot-starter-validation` in Spring Boot 3.x.

If you want to integrate Jakarta Bean Validation into **manual Binder**, you must provide a compatible Spring `Validator` adapter or a properly initialized `LocalValidatorFactoryBean`. Do not merely add `@Validated` to the target class and assume `new Binder(...)` will discover the application context's validation infrastructure and run constraints.

A maintainable approach:

- Use `@Validated` and constraints for standard `@ConfigurationProperties` beans.
- Use `ValidationBindHandler` with a Spring `Validator` when controlling a single `Binder.bind(...)` call.
- Avoid duplicating identical validators if they can be reused cleanly.

## 30. When Should You Use `ConfigurationPropertiesBindHandlerAdvisor`?

For advanced framework extensions, Spring Boot provides:

~~~java
org.springframework.boot.context.properties.ConfigurationPropertiesBindHandlerAdvisor
~~~

This mechanism lets you add behavior to the `BindHandler` used by `ConfigurationPropertiesBindingPostProcessor`.

API shape example:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBindHandlerAdvisor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BindingCustomization {

    @Bean
    static ConfigurationPropertiesBindHandlerAdvisor bindingAdvisor() {
        return handler -> handler;
    }
}
~~~

This is a **no-op** advisor illustrating only the signature and registration point. An implementation can return a new handler wrapping the existing handler to add auditing, custom validation, or appropriate logic.

Because the advisor affects the **Spring Boot-managed binding pipeline**, it can influence multiple `@ConfigurationProperties` beans rather than a single bind call in a test. That is a huge difference from passing a handler directly to `binder.bind(...)`.

Do not add an advisor to the application context just to check a single property if `ignoreUnknownFields=false` or `@Validated` already suffices. When genuinely extending the pipeline, you should:

1. Preserve the supplied parent handler.
2. Never accidentally swallow errors from the parent handler.
3. Scope effects by root/target if needed.
4. Write integration tests for critical configuration beans.
5. Check advisor ordering if multiple extensions exist.
6. Document the Spring Boot version and behavioral contract in technical docs.

## 31. Reading Error Root Causes Instead of Just Startup Messages

Errors can originate from different layers:

| Error layer | Example cause | Possible symptom |
| --- | --- | --- |
| Conversion | `threads=many` | Failure converting `String` to `int` |
| Bean validation | `threads=0` with rule ≥ 1 | `BindValidationException` or constraint message |
| Unbound element | `threds=12` when class lacks field | `UnboundConfigurationPropertiesException` |
| Missing required | `timeout` absent | Validator reports null or missing per contract |
| Bean registration | Class not registered | `WorkerSettings` bean not found |
| Config Data | Required imported file missing | Config Data load/import error before Binder runs |

**The top-level exception class is not always the root cause.** When Binder or the Spring container wraps errors, a specialized exception may sit deeper in the cause chain.

A practical diagnostic workflow:

1. Identify the root prefix and target class.
2. Identify the property sources used by Binder.
3. Distinguish "key absent," "key present with wrong type," and "key has no target."
4. Inspect the exception chain to identify validation/unbound/conversion.
5. Never print secret values in logs.
6. Add a test for the exact scenario just discovered.
7. Fix the configuration source or schema rather than disabling strict mode without cause.

If errors are raised by a custom handler, do not assume the exception class matches built-in handlers; verify `onFailure`, `onSuccess`, and parent delegation order.

## 32. Do Not Overuse Strict Unbound Checking on Shared Namespaces

A namespace may be shared by multiple beans or subsystems. Example:

~~~properties
demo.notifications.email.enabled=true
demo.notifications.sms.enabled=false
demo.notifications.retry.max-attempts=3
~~~

If class A only binds `demo.notifications.email` yet a developer uses root `demo.notifications` and type A does not describe `sms` or `retry`, the strict unbound handler can flag keys **valid for another subsystem** as unbound.

The cause is not that those keys are wrong, but that **the root scope does not match schema ownership**.

Better options:

- Use a narrow root, e.g., `demo.notifications.email`.
- If a shared root is needed, build a parent properties model covering all sub-groups.
- Only enable strict handlers for sources that the subsystem truly owns.
- Separate configuration files/namespaces for independent groups.
- If filtering is needed, define explicit source criteria.
- Test across deployment environments rather than just a simple dev file.

A strict handler is a contract-checking tool; contracts only make sense when **data boundaries** are clearly defined.

## 33. Using Handlers in Tests Without ApplicationContext

Pure Binder unit test example:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class StrictBindingTest {

    @Test
    void rejectsUnusedProperty() {
        Map<String, Object> properties = Map.of(
                "demo.worker.threads", "4",
                "demo.worker.timeout", "5s",
                "demo.worker.enabled", "true",
                "demo.worker.threds", "12"
        );

        Binder binder = new Binder(
                ConfigurationPropertySources.from(
                        new MapPropertySource("test", properties)
                )
        );

        BindHandler handler =
                new NoUnboundElementsBindHandler(BindHandler.DEFAULT);

        assertThatThrownBy(() ->
                binder.bind(
                        "demo.worker",
                        Bindable.of(WorkerSettings.class),
                        handler
                ).get()
        ).isInstanceOf(RuntimeException.class);
    }
}
~~~

This example requires no full Spring application context; only the Spring Boot Binder libraries and appropriate test dependencies.

In real projects, do not stop at asserting `RuntimeException.class`. Once you know the exact exception chain in your Boot version, assert the specific unbound property name so the test cannot "pass" due to an unrelated error.

For example, if the exception has `UnboundConfigurationPropertiesException` in the cause chain, inspect the `ConfigurationProperty` entries from `getUnboundProperties()` per the actual API.

## 34. Using `ApplicationContextRunner` for `@ConfigurationProperties`

When testing Spring Boot's managed bean mechanism, `ApplicationContextRunner` from `spring-boot-test` is helpful.

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "demo.worker",
        ignoreUnknownFields = false
)
public record WorkerSettings(
        @Min(1) int threads,
        @NotNull Duration timeout,
        boolean enabled
) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerConfigurationTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerSettings.class)
    static class TestConfiguration {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void acceptsValidValues() {
        runner.withPropertyValues(
                "demo.worker.threads=4",
                "demo.worker.timeout=5s",
                "demo.worker.enabled=true"
        ).run(context -> {
            assertThat(context).hasNotFailed();
        });
    }

    @Test
    void rejectsUnknownField() {
        runner.withPropertyValues(
                "demo.worker.threads=4",
                "demo.worker.timeout=5s",
                "demo.worker.enabled=true",
                "demo.worker.threds=12"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void rejectsInvalidBusinessValue() {
        runner.withPropertyValues(
                "demo.worker.threads=0",
                "demo.worker.timeout=5s",
                "demo.worker.enabled=true"
        ).run(context -> assertThat(context).hasFailed());
    }
}
~~~

For validation tests to actually run, a compatible Bean Validation provider must be on the test runtime classpath. If the context fails because another bean is missing, `hasFailed()` alone is insufficient: add assertions on the failure cause.

This is the **auto configuration properties path**; not manually passing a `ValidationBindHandler` to `binder.bind(...)`. Both serve similar goals but differ in configuration and scope.

## 35. When Both Unbound and Invalid Occur: Which Error Appears?

Suppose the data is:

~~~properties
demo.worker.threads=0
demo.worker.timeout=5s
demo.worker.enabled=true
demo.worker.threds=12
~~~

Two problems exist at once:

1. `threads=0` fails rule ≥ 1.
2. `threds` is an unbound property.

Do not assume a single bind pass with two handlers will always return **both errors** inside one exception. A handler may throw inside a callback before the remaining check finishes. Wrapper order, bean type, and bind path can determine which error surfaces first.

For complete diagnostics:

- Run validation tests separately for values.
- Run unknown-field tests separately for schemas.
- Then test combined behavior to confirm the app's fail-fast strategy.
- For offline lint tools that must list multiple errors at once, design explicit error collection instead of relying on one `Binder.bind` pass.

**Fail-fast** and **collect-all-errors** are two different goals. `BindHandler` extends the binding pipeline, rather than automatically generating a comprehensive report of every configuration error across all sources.

## 36. When to Choose Which Implementation Approach?

| Context | Appropriate approach |
| --- | --- |
| Standard Spring Boot app with a few config beans | `@ConfigurationProperties` + `@Validated` + constraints |
| Want to reject typos in one bean's namespace | `ignoreUnknownFields=false` |
| Library needing to bind config from custom sources | `new Binder(...)` + handler |
| Need specialized validator in manual bind | `ValidationBindHandler` with Spring `Validator` |
| Need to catch leftover properties in manual bind | `NoUnboundElementsBindHandler` |
| Need both validation and unknown check in manual Binder | Compose two handlers, test order/exceptions |
| Need to log bound property names | Tracking handler or custom `AbstractBindHandler` |
| Need to customize pipeline for all `@ConfigurationProperties` beans | `ConfigurationPropertiesBindHandlerAdvisor` with clear scoping |
| Need to audit all config files across environments | Separate schema lint/CI, not just a runtime BindHandler |

For most applications, **annotation-level validation/strictness** is easier to maintain than building a custom binding pipeline. Manual handlers are mainly for libraries, configuration tools, and cases requiring low-level bind lifecycle control.

## 37. Common Mistakes

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| `threads=0` still binds successfully | No validator or validation not enabled | Use `@Validated`/`@Min(1)` or `ValidationBindHandler` |
| Property `threds` is ignored | Strict unknown-field checking not enabled | `ignoreUnknownFields=false` or `NoUnboundElementsBindHandler` |
| Has `@Validated` yet manual Binder does not validate | Manually built Binder lacks validator handler | Pass `ValidationBindHandler` with a suitable validator |
| `NoUnboundElementsBindHandler` flags key from another component | Root prefix too broad or shared source | Narrow root, separate sources/schemas |
| Unbound handler misses key in another namespace | Check only covers the root being bound | Validate namespaces and missing-root separately |
| Map test catches unknown keys but another source does not | Source not enumerable or different adapter | Check enumeration capability and test real source |
| `ValidationBindHandler` misses nested type errors as expected | Validator lacks target/nested type support | Update `supports`/validation cascade and test |
| Multiple errors exist yet only one shows | Fail-fast, callback order, and exception propagation | Test error classes individually, consider separate linter if collect-all needed |
| Handler logs leak sensitive values | Logging full properties/results | Log only safe info, redact secrets |
| Custom `onFailure` swallows all exceptions | Handler returns arbitrary defaults | Delegate or rethrow disallowed errors |
| `@ConfigurationProperties` creates no bean | Missing scan/enable registration or confused with `@Component` | Check bean registration |
| Turning on `ignoreInvalidFields=true` to fix typos | Wrong error category; can hide conversion errors | Distinguish unknown from invalid |
| Calling `Binder.get(environment)` and strict-checking root `spring` | Root too wide, multiple owners/schemas | Bind only narrow roots and identify sources |
| Checking missing properties with NoUnbound handler | No leftover key exists to detect | Use required constraints/intentional defaults |
| Asserting any `RuntimeException` in tests | Test can pass due to unrelated errors | Assert root cause and property names |
| Exception format changes across Boot versions | Relying on unstable message strings | Check APIs/cause chains instead of brittle text matching |

## 38. Self-Practice Exercises

### Exercise 1 — Error classification

Given:

~~~properties
demo.worker.threads=many
demo.worker.timeout=5s
demo.worker.enabled=true
~~~

Target `threads` has type `int`. What kind of error is this?

**Answer:** conversion/binding error. `many` cannot convert to `int`. An object may not even be constructed for a business validator to inspect.

### Exercise 2 — Type-valid value that is business-invalid

Given:

~~~properties
demo.worker.threads=0
demo.worker.timeout=5s
demo.worker.enabled=true
~~~

Validator requires `threads >= 1`. Which handler is responsible?

**Answer:** `ValidationBindHandler` with an appropriate Spring `Validator`, or Bean Validation via a standard `@Validated @ConfigurationProperties` bean.

### Exercise 3 — Extra property

Given:

~~~properties
demo.worker.threads=4
demo.worker.timeout=5s
demo.worker.enabled=true
demo.worker.threds=7
~~~

Target only has `threads`, `timeout`, `enabled`. Which handler detects `threds`?

**Answer:** `NoUnboundElementsBindHandler` when the source supports enumeration and root `demo.worker` is bound appropriately.

### Exercise 4 — Missing property

Given:

~~~properties
demo.worker.threads=4
demo.worker.enabled=true
~~~

`timeout` is missing. Is `NoUnboundElementsBindHandler` guaranteed to report an error?

**Answer:** no. This handler finds properties that are present yet unbound. Missing `timeout` requires validation or explicit required-field logic.

### Exercise 5 — Composing handlers

Write an expression creating a handler that performs both unbound checking and validation:

**Suggested answer:**

~~~java
BindHandler handler = new NoUnboundElementsBindHandler(
        new ValidationBindHandler(
                new WorkerSettingsValidator()
        )
);
~~~

Remember to test behavior when multiple errors appear simultaneously.

### Exercise 6 — Root of the bind call

If binding root `demo.worker` while data is mistyped as `demo.workers.threads=4`, will the strict unbound handler necessarily catch it?

**Answer:** no. A property in another namespace may sit outside root `demo.worker`. Check the root and presence of required values.

### Exercise 7 — Non-enumerable source

A custom `ConfigurationPropertySource` only supports key lookup and does not support enumeration. Can you claim `NoUnboundElementsBindHandler` will catch every unknown property?

**Answer:** no. Unbound detection depends on the source and appropriate enumeration capability.

### Exercise 8 — Annotations vs. manual Binder

A record has `@Validated` and `@Min(1)`, yet code directly calls:

~~~java
new Binder(sources).bind(
        "demo.worker",
        Bindable.of(WorkerSettings.class)
);
~~~

Should you assume validation runs automatically?

**Answer:** no. With manual Binder, you must pass an appropriate validator handler or use a validation-integrated pipeline. Annotations on the target class alone do not guarantee this call checks constraints.

### Exercise 9 — Handler advisor

For which case is `ConfigurationPropertiesBindHandlerAdvisor` better suited: (A) a single bind test from `MapPropertySource`, or (B) customizing the handler Spring Boot uses for `@ConfigurationProperties` beans?

**Answer:** (B). For (A), passing a handler directly to `Binder.bind(...)` is clearer and narrower.

### Exercise 10 — Two simultaneous errors

Configuration has `threads=0` and `threds=7`. Why should you not demand a single `Binder.bind` call always return both in one list?

**Answer:** handlers can fail fast at different callbacks; wrapper order and the binding flow affect which error surfaces first. If full reporting is needed, build a separate error-collecting linter/validator.

## 39. Practical Application Checklist

When using handlers to protect configuration:

1. Identify the **root prefix** and schema owned by the component.
2. Choose the path: standard `@ConfigurationProperties` bean or manual Binder.
3. Categorize errors to catch: conversion, validation, unbound, missing.
4. For standard beans, prefer `@Validated` and `ignoreUnknownFields=false` if sufficient.
5. For manual Binder, build explicit `ConfigurationPropertySource` instances.
6. Choose `ValidationBindHandler` and/or `NoUnboundElementsBindHandler`.
7. When combining handlers, establish parent relationships and write ordering tests.
8. Use validators whose conditions match actual target types.
9. Never ignore errors in `onFailure` without an explicit policy.
10. Verify sources support key enumeration so unbound handlers work.
11. Do not apply strict policies to overly broad shared prefixes.
12. Test valid config, conversion failures, validation failures, and unbound properties.
13. Separately test absent roots or missing required properties.
14. For nested objects/lists/maps, test child properties and special key characters.
15. Look for root causes in the exception chain rather than only the outermost exception name.
16. Ensure logs and error reporting do not leak secrets.
17. Check differences between test and production property sources.
18. Assign configuration ownership to the right module/owner to avoid over-scoped strict checks.
19. If collect-all errors across files are needed, add a schema lint/CI step.
20. Cross-check API docs with your project's exact Spring Boot version.

## 40. Key Takeaways

- **`BindHandler`** lets logic run during the binding lifecycle via callbacks such as `onStart`, `onSuccess`, `onFailure`, and `onFinish`.
- **`ValidationBindHandler`** applies Spring `Validator` instances to the bound result to check business rules.
- **`NoUnboundElementsBindHandler`** requires properties under the bound root to be consumed; it helps catch typos or extra settings.
- **Unbound** differs from **missing**. Extra keys are present yet unused; missing required keys are not unbound elements.
- **Conversion failure** differs from **validation failure**. String `many` fails conversion to `int`; number `0` converts fine yet violates `@Min(1)`.
- Two handlers can be **nested via parent delegation**; callback order affects which error appears first.
- For standard `@ConfigurationProperties` beans, usually prefer **`@Validated`** and **`ignoreUnknownFields=false`** before building a custom Binder pipeline.
- Manual Binder does not pick up a Bean Validation provider automatically just because the target class has `@Validated`; provide a suitable validator/handler.
- Unbound detection depends on **root prefix, configuration sources, and property enumeration capability**; it is not an audit of the entire Environment.
- `ConfigurationPropertiesBindHandlerAdvisor` is for broader customization of the configuration-properties pipeline; use with bounded scope and tests.
- Handlers must never accidentally log secrets or swallow critical configuration errors.

## References

- [Spring Boot 3.3 — Binder API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html)
- [Spring Boot 3.3 — BindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindHandler.html)
- [Spring Boot 3.3 — ValidationBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/validation/ValidationBindHandler.html)
- [Spring Boot 3.3 — NoUnboundElementsBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/handler/NoUnboundElementsBindHandler.html)
- [Spring Boot 3.3 — ConfigurationPropertiesBindHandlerAdvisor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBindHandlerAdvisor.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation.html)
