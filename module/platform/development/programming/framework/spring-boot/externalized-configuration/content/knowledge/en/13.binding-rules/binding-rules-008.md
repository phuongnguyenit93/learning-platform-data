# Primitive Default Values and the Risk of Masking Missing Configuration

Spring Boot supports binding properties from `application.yml`, `application.properties`, environment variables, command-line arguments, and other sources into Java objects via `@ConfigurationProperties`. When declaring data types, we often pick `int`, `long`, or `boolean` because they are concise and familiar.

However, Java primitive types have an easily overlooked trait: **they cannot represent `null`**. When a property is not supplied, the configuration object can receive primitive defaults such as `0` or `false`. If those values still look plausible to application code, missing configuration can be **masked** instead of caught early.

For example:

- Missing `app.email.enabled` can make a feature appear **disabled** (`false`), even though the operator forgot to configure it.
- Missing `app.batch.max-items` can yield `0`, causing a batch job to process zero items.
- Missing `app.client.connect-timeout-ms` can yield `0`; depending on the library, this might mean no wait, infinite wait, or an invalid value.
- Missing `app.worker.concurrency` can become `0` and only fail later when creating a thread pool.

This lesson uses Spring Boot 3.3.x and Java 21. The focus is **distinguishing a missing property from an explicitly provided value**, choosing appropriate Java types, declaring intentional defaults, and using validation so the application *fails fast* when required configuration does not exist.

## 1. Recap: binding from configuration sources to Java

Suppose `src/main/resources/application.yml` has:

~~~yaml
app:
  worker:
    enabled: true
    concurrency: 4
    retry-count: 3
~~~

A corresponding configuration record:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        boolean enabled,
        int concurrency,
        int retryCount) {
}
~~~

The Spring Boot Binder finds properties under prefix `app.worker` and passes them as record constructor arguments:

~~~text
app.worker.enabled       → enabled       → boolean
app.worker.concurrency   → concurrency   → int
app.worker.retry-count   → retryCount    → int
~~~

When all three properties are present, the object receives:

~~~text
enabled = true
concurrency = 4
retryCount = 3
~~~

But if the file only has:

~~~yaml
app:
  worker:
    enabled: true
~~~

the two properties `concurrency` and `retry-count` are not supplied. For primitive components of the bound object, the missing values can appear as:

~~~text
enabled = true
concurrency = 0
retryCount = 0
~~~

**The problem:** these are not values intentionally chosen by an operator. They come from Java's type defaults during object construction.

## 2. Default values of primitives in Java

Primitives have no `null`. When a Java **field** is not explicitly initialized, Java uses a default value:

| Primitive | Field default value |
| --- | --- |
| `boolean` | `false` |
| `byte` | `0` |
| `short` | `0` |
| `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `char` | NUL character `'\u0000'` |

Precise Java note: local variables inside a method are **not automatically initialized** before use; the compiler requires definite assignment. The table above applies to fields/array components or primitive defaults produced when the framework constructs a configuration object, **not** every Java variable in every context.

JavaBean example:

~~~java
public class WorkerSettings {

    private int concurrency;
    private boolean enabled;

    public int getConcurrency() {
        return concurrency;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
~~~

If the object is constructed via `new WorkerSettings()` with no further assignment:

~~~text
concurrency = 0
enabled = false
~~~

In Spring Boot, if a property is not bound to the corresponding JavaBean field, the field's initial value can remain unchanged. With constructor/record binding, the Binder constructs constructor arguments; missing primitive arguments typically end up as the primitive default value.

### Why are `0` and `false` dangerous in configuration?

Both `0` and `false` are valid Java values. Java cannot tell from the constructed primitive value alone whether the user **configured `0`/`false`** or **forgot to configure it**.

~~~text
Case A: app.worker.concurrency=0
Case B: app.worker.concurrency is absent

Final primitive object:
concurrency == 0
~~~

If code only checks `concurrency == 0`, it no longer has information to distinguish the two cases.

## 3. Example of missing configuration causing wrong behavior

Consider an order-processing service:

~~~java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.orders")
public record OrdersProperties(
        boolean processingEnabled,
        int maxBatchSize) {
}
~~~

A service:

~~~java
package com.example.orders.service;

import com.example.orders.config.OrdersProperties;
import org.springframework.stereotype.Service;

@Service
public class OrderBatchService {

    private final OrdersProperties properties;

    public OrderBatchService(OrdersProperties properties) {
        this.properties = properties;
    }

    public void process() {
        if (!properties.processingEnabled()) {
            System.out.println("Processing is disabled");
            return;
        }

        for (int i = 0; i < properties.maxBatchSize(); i++) {
            // Process one order
        }
    }
}
~~~

If the operator forgets to declare `app.orders` altogether, the configuration object can have:

~~~text
processingEnabled = false
maxBatchSize = 0
~~~

The application can start normally and print `Processing is disabled`. This is a **silent bug** if business requirements mandate that deployers explicitly decide whether orders should be processed.

If the operator later sets `processing-enabled=true` while still omitting `max-batch-size`, the loop runs 0 times. No Java exception is guaranteed to appear in this example.

**Lesson:** successful binding does not prove input configuration is complete and valid for business logic.

## 4. How do primitives differ from wrappers?

Java provides *wrapper types*:

| Primitive | Wrapper |
| --- | --- |
| `boolean` | `Boolean` |
| `int` | `Integer` |
| `long` | `Long` |
| `double` | `Double` |
| `float` | `Float` |

Wrappers are reference types and can hold `null`. When a property is not supplied and there is no default or other value provider, a wrapper component can receive `null`.

Example:

~~~java
@ConfigurationProperties(prefix = "app.orders")
public record OrdersProperties(
        Boolean processingEnabled,
        Integer maxBatchSize) {
}
~~~

With missing configuration, you can observe:

~~~text
processingEnabled = null
maxBatchSize = null
~~~

This **does not fail by itself**: code still has to use or validate the value. But it provides distinct representations for the two states:

~~~text
null   → not configured
false  → explicitly configured as disabled
0      → explicitly configured as 0
~~~

When an application **needs to distinguish absent from valid values**, wrappers are usually better suited than primitives.

### Do not unbox a missing wrapper carelessly

Example:

~~~java
Boolean enabled = properties.processingEnabled();

if (enabled) {  // Can throw NullPointerException when enabled == null.
    // ...
}
~~~

Because `if` expects a `boolean`, Java must unbox `Boolean`. If the value is `null`, a `NullPointerException` occurs.

The solution is not always using primitives. If a property is required, **validate it as soon as the configuration properties bean is created** so the error appears before services use it.

## 5. Using `@NotNull` to require a property to be supplied

Spring Boot supports Bean Validation on `@ConfigurationProperties` when a Bean Validation provider is present. In typical Spring Boot projects, you can add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Create configuration:

~~~java
package com.example.orders.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.orders")
public record OrdersProperties(
        @NotNull Boolean processingEnabled,
        @NotNull @Min(1) Integer maxBatchSize) {
}
~~~

Meaning:

- `@Validated` requests validation when Spring Boot binds the configuration bean.
- `@NotNull Boolean processingEnabled`: the deployer must provide `true` or `false`; omitting it causes a validation error.
- `@NotNull Integer maxBatchSize`: missing is rejected.
- `@Min(1) Integer maxBatchSize`: value must be 1 or greater.

With file:

~~~yaml
app:
  orders:
    processing-enabled: false
    max-batch-size: 10
~~~

Both values are valid: `false` is an explicit choice, and `10` satisfies `@Min(1)`.

But if only:

~~~yaml
app:
  orders:
    processing-enabled: false
~~~

`maxBatchSize` is missing. When Bean Validation is enabled and the configuration properties bean is created, the application can stop starting with a binding/validation error mentioning `app.orders.max-batch-size`.

### Why not just put `@NotNull` on a primitive?

The following fails to distinguish "missing" from "`false`":

~~~java
@ConfigurationProperties(prefix = "app.orders")
public record OrdersProperties(
        @NotNull boolean processingEnabled) {
}
~~~

`boolean` can never be `null`. Thus `@NotNull` gives no mechanism for detecting a missing boolean property.

Similarly:

~~~java
@NotNull int maxBatchSize
~~~

cannot detect absence via null. If you require the operator **to specify a number**, use `Integer` + `@NotNull`. If you want the number to always be greater than 0 without distinguishing missing from 0, `@Min(1) int` catches `0`, though it still does not tell you separately whether the cause was "missing property" or "explicitly set to 0".

## 6. Do `@Min` and `@Positive` replace `@NotNull`?

Not completely. They are different constraint types:

- `@NotNull`: the value must exist.
- `@Min(1)`: a number must be greater than or equal to 1.
- `@Positive`: a number must be greater than 0.
- `@Max(100)`: a number must not exceed 100.
- `@NotBlank`: a string must not be null, empty, or whitespace-only.

Example:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @NotNull @Min(1) @Max(64) Integer concurrency) {
}
~~~

For `Integer`:

~~~text
Missing property → null → violates @NotNull
Value 0          → 0    → violates @Min(1)
Value 100        → 100  → violates @Max(64)
Value 8          → 8    → valid
~~~

Separating missing errors from out-of-range errors makes logs and operational guidance clearer.

Several Bean Validation constraints like `@Min` allow `null` to pass because requiring presence is the responsibility of `@NotNull`. Therefore, writing only `@Min(1) Integer concurrency` without `@NotNull` should not be relied upon to guarantee the property is declared.

### What if `0` is a valid value?

For example, some APIs treat timeout `0` specially, or `server.port=0` in web apps requests an ephemeral port. Do not slap `@Min(1)` onto every integer out of habit.

When `0` is valid yet the user **must declare it explicitly**, use a wrapper with `@NotNull`:

~~~java
@NotNull Integer port
~~~

Then add other constraints matching business rules. `Integer` lets you tell whether the property exists; `@Min(1)` would reject `0` and is therefore wrong if `0` is valid.

## 7. Booleans: `false` can be a business value, not an error

Suppose a processing mode must be chosen:

~~~yaml
app:
  settlement:
    enabled: false
~~~

`false` was intentionally set by the operator, e.g., to pause settlement. There is no default reason to call it an error.

Yet if `app.settlement.enabled` is completely absent, getting `false` from a primitive does not indicate whether disabling was **intentional** or **accidental**.

Two different contracts:

**Mode A — Optional feature, disabled by default**

~~~java
@ConfigurationProperties(prefix = "app.settlement")
public record SettlementProperties(
        @DefaultValue("false") boolean enabled) {
}
~~~

This is an explicit default in the design: when the property is missing, the app is allowed to disable the feature.

**Mode B — Explicit decision required**

~~~java
@Validated
@ConfigurationProperties(prefix = "app.settlement")
public record SettlementProperties(
        @NotNull Boolean enabled) {
}
~~~

In Mode B, a missing property is a configuration error, while both `true` and `false` are valid when supplied.

Neither choice is universally better. The decision depends on the operational contract: **is missing configuration valid or an error?**

## 8. `@DefaultValue`: declaring intentional default values

Spring Boot provides the annotation:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;
~~~

With constructor binding/records, you can write:

~~~java
package com.example.worker.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("4") int concurrency,
        @DefaultValue("3") int retryCount) {
}
~~~

If the corresponding properties are absent, the Binder uses `true`, `4`, `3` instead of non-semantic primitive defaults like `0` or `false`.

Benefits:

- Reading the record immediately reveals defaults the app accepts.
- Operators can still override via YAML, environment variables, or CLI.
- Easy to distinguish **designed defaults** from **implicit `0`/`false` values**.

However, `@DefaultValue` is only appropriate when omitting the property **is allowed**. If configuration is mandatory, do not add a default just to avoid errors.

### `@DefaultValue` works when the property is absent

Example:

~~~java
@DefaultValue("4") int concurrency
~~~

With:

~~~yaml
app:
  worker:
    concurrency: 8
~~~

the value is `8`, not `4`. The default only applies when the Binder **cannot find** the corresponding property.

### An empty value is not the same as missing

If the configuration source has:

~~~properties
app.worker.concurrency=
~~~

that is a present property with an empty string; do not assume `@DefaultValue("4")` will trigger. The outcome depends on conversion, target type, and how the Binder handles empty values; errors or unexpected values may occur.

A rule worth remembering: **fallback when a property is not found is not the same as fallback when a property exists but is empty, wrongly typed, or invalid for business rules**.

## 9. Comparing Java defaults, `@DefaultValue`, and defaults in YAML

All three can influence the final value, but operate at different layers.

### 9.1. Implicit primitive default

~~~java
private int concurrency;
~~~

If this is an unassigned field, Java leaves `0`. It does not express "0 is the application's default concurrency".

### 9.2. Explicit default on a JavaBean field

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {

    private int concurrency = 4;
    private boolean enabled = true;

    public int getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(int concurrency) {
        this.concurrency = concurrency;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

With JavaBean binding, fields are initialized and can keep their values if the Binder does not supply properties. When properties exist, setters override them.

### 9.3. Explicit default in constructor binding

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") int concurrency,
        @DefaultValue("true") boolean enabled) {
}
~~~

This is a clean option for records.

### 9.4. Default in a configuration file

~~~yaml
app:
  worker:
    concurrency: 4
    enabled: true
~~~

Values live in `Environment` and participate in precedence. Profile files, environment variables, or CLI arguments can override them.

| Approach | Where declared | When property is missing | Overridable by external property? |
| --- | --- | --- | --- |
| Implicit primitive | Java language behavior | `0`/`false` | Yes |
| JavaBean field initializer | JavaBean class | Keeps initial value if unbound | Yes |
| `@DefaultValue` | Constructor/record | Binder uses default if property missing | Yes |
| `application.yml` | Config Data | Property is already present in loaded source | Yes, per precedence order |

Choose one intentional primary source of defaults. Placing defaults in both YAML and annotations with conflicting values confuses readers, even though at runtime the Binder has a clear order.

## 10. Required configuration should fail fast

For a critical payment or data-processing system, many values must be provided:

- Is request processing allowed?
- What is the per-batch record limit?
- How many workers are allowed to run?
- What is the target endpoint or queue name?

A safer configuration:

~~~java
package com.example.payment.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @NotNull Boolean processingEnabled,
        @NotNull @Min(1) Integer batchSize,
        @NotNull @Min(1) Integer workerCount,
        @NotBlank String queueName) {
}
~~~

Add `spring-boot-starter-validation` and register the configuration class properly. When `batch-size`, `processing-enabled`, or `queue-name` is missing, the application fails during configuration bean creation, before running business tasks.

Valid file example:

~~~yaml
app:
  payment:
    processing-enabled: false
    batch-size: 100
    worker-count: 2
    queue-name: payment-events
~~~

Note that `processing-enabled=false` is still **valid** because the system requires an explicit decision. That is why `@NotNull Boolean` is used instead of an "always true" constraint.

### Registering the configuration properties bean

~~~java
package com.example.payment;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PaymentApplication {

    public static void main(String[] args) {
        SpringApplication.run(PaymentApplication.class, args);
    }
}
~~~

If `PaymentProperties` is under package `com.example.payment`, `@ConfigurationPropertiesScan` will find it. `@EnableConfigurationProperties(PaymentProperties.class)` can also be used.

With constructor-bound records, avoid putting `@Component` and expecting constructor parameters to be autowired like ordinary beans. The Binder must be activated through an appropriate registration mechanism.

## 11. Other risks of primitives beyond `0`/`false`

### 11.1. Logs look normal

A log like:

~~~text
workerCount=0
processingEnabled=false
~~~

carries no "property is missing" signal. A developer may assume the operator configured it intentionally. Design validation or explicit error messages upfront instead of relying on logging final values.

### 11.2. Configuration fails only in production

In development, `application-dev.yml` has all keys. At deployment, `application-prod.yml` might omit a value and primitive beans quietly pick up implicit defaults. The app starts, yet behaves unexpectedly.

### 11.3. Zero has different meanings across libraries

Across APIs, `0` can mean:

- Zero items.
- Run immediately with no wait.
- Unlimited or wait indefinitely by specific convention.
- Let the OS choose an ephemeral port.
- An invalid value throwing an exception.

You cannot apply one blanket conclusion to every API. **Design validation around each library's contract**, rather than assuming "0 is always wrong".

### 11.4. Default behavior can be unsafe

A missing `boolean auditEnabled` receiving `false` can silently disable auditing. Conversely, an ill-considered `true` default could trigger sending data externally. Configuration affecting security or production data should require explicit, validated values.

## 12. Nested objects: risk also lies in missing objects

A record with nested configuration:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        Retry retry) {

    public record Retry(
            int maxAttempts,
            boolean enabled) {
    }
}
~~~

If there are no `app.client.retry.*` properties at all, the Binder may not create the nested object; `retry` can be `null`. This differs from when the nested object is created and primitives inside receive `0`/`false`.

If a service calls:

~~~java
properties.retry().maxAttempts();
~~~

it can hit a `NullPointerException` when `retry()` is null.

### Required nested group

If the retry group must be present, combine validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @Valid @NotNull Retry retry) {

    public record Retry(
            @NotNull @Min(1) Integer maxAttempts,
            @NotNull Boolean enabled) {
    }
}
~~~

`@NotNull Retry retry` catches a missing object; `@Valid` enables checking inner constraints when the object is created.

### Optional nested group needing defaults

If retry is optional and you want the object instantiated with defaults when data is absent, place an empty `@DefaultValue` on the nested component:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @DefaultValue Retry retry) {

    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("true") boolean enabled) {
    }
}
~~~

In this model, `@DefaultValue` with no arguments on `Retry retry` tells the Binder to create the nested object even when no matching keys exist, while `Retry` components have explicit defaults.

**Do not mix the two policies—"must be supplied" vs "may be omitted and use defaults"—without clearly defining the business meaning.**

## 13. Constructor binding, JavaBean binding, and records

There are two common `@ConfigurationProperties` styles.

### 13.1. Mutable JavaBean

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {

    private int concurrency;
    private Boolean enabled;

    public int getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(int concurrency) {
        this.concurrency = concurrency;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

If `concurrency` is absent, the primitive field retains `0`. If `enabled` is absent, the wrapper field can be null. However, other code has setters and can still mutate the object after startup if uncontrolled.

### 13.2. Record constructor binding

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int concurrency,
        Boolean enabled) {
}
~~~

Records offer a concise API, clear components, and no setters. When properties are missing, `concurrency` can be `0` and `enabled` can be `null`. Thus, **switching from a JavaBean to a record does not automatically solve missing configuration**.

An important difference is that annotation defaults should use `@DefaultValue` on record components or constructor parameters, rather than relying on JavaBean field initializers.

### 13.3. Choosing types by contract

| Requirement | Suitable type/annotation |
| --- | --- |
| May be omitted, intentionally defaults to false | `@DefaultValue("false") boolean` |
| May be omitted, defaults to 4 workers | `@DefaultValue("4") int` |
| Deployer must choose true/false | `@NotNull Boolean` |
| Must supply a positive integer | `@NotNull @Min(1) Integer` |
| Required non-blank string | `@NotBlank String` |
| May be omitted and handled by app | Nullable `Integer`/`Boolean`, with explicit null handling |
| Required nested group | `@Valid @NotNull Nested` |
| Nested group with intentional defaults | `@DefaultValue Nested` combined with defaults on child components |

## 14. Distinguishing missing property, empty property, wrong type, and business-invalid value

Not every issue is "missing configuration".

| Situation | Example | Appropriate action |
| --- | --- | --- |
| Absent | No `app.worker.concurrency` | Use intentional default or fail validation |
| Empty string | `app.worker.concurrency=` | Do not assume equivalent to absent; check conversion and validation |
| Wrong type | `app.worker.concurrency=many` | Binder may report number-conversion error |
| Right type, invalid value | `app.worker.concurrency=-1` | Use `@Min(1)` or appropriate constraint |
| Valid false | `app.worker.enabled=false` | Allow if business accepts it; use `Boolean @NotNull` if declaration required |
| Valid zero | `app.service.port=0` | Do not apply `@Min(1)` if 0 is valid |
| Wrong key path | `app.workers.concurrency` instead of `app.worker.concurrency` | Fix property name, do not mask error with arbitrary default |

From the Java object's perspective, primitives lose the ability to distinguish **missing** from **`0`/`false`** after binding. That does not prevent the Binder from reporting other errors: type conversion and validation can still catch independent issues.

### Misspelled key name case

Example:

~~~yaml
app:
  worker:
    concurency: 8
~~~

Yet Java uses `concurrency`. Because YAML is missing an `r`, the expected property is not bound. If the Java type is `int` without a default or validation, the value may be read as `0`, causing confusion.

This is a real-world risk: **a typo can turn into "missing" configuration and be masked by primitives**.

For critical property sets, combine validation with key-name control, binding tests, and IDE configuration metadata support. Do not treat successful object creation as proof that every property in the file was accepted.

## 15. `@Value` has similar problems if defaults are unclear

A bean using:

~~~java
@Value("${app.worker.concurrency:0}")
private int concurrency;
~~~

can also mask a missing `app.worker.concurrency` with default `0`. The difference is that this fallback is **written explicitly** in the placeholder, yet it may still be invalid for business rules.

When migrating to `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int concurrency) {
}
~~~

if you remove `@Value` without redesigning defaults/validation, readers might not realize `0` can still appear due to the primitive type.

If the property is required:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @NotNull @Min(1) Integer concurrency) {
}
~~~

If default `4` is allowed:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") int concurrency) {
}
~~~

Each option expresses a different policy, not merely a change of annotation.

## 16. Impact of profiles, environment variables, and CLI

Suppose:

~~~java
@ConfigurationProperties(prefix = "app.batch")
public record BatchProperties(
        @DefaultValue("50") int maxItems,
        @NotNull Boolean enabled) {
}
~~~

Shared file:

~~~yaml
app:
  batch:
    enabled: false
~~~

File `application-prod.yml`:

~~~yaml
app:
  batch:
    max-items: 200
~~~

Running without a specific profile or override source:

~~~text
maxItems = 50     (default from @DefaultValue)
enabled  = false  (explicit value in shared file)
~~~

Running:

~~~bash
java -jar batch-app.jar --spring.profiles.active=prod
~~~

result:

~~~text
maxItems = 200    (application-prod.yml)
enabled  = false  (application.yml)
~~~

If CLI supplies:

~~~bash
java -jar batch-app.jar --spring.profiles.active=prod --app.batch.max-items=500
~~~

`maxItems` receives `500` per property source precedence. Using wrappers or primitives **does not change precedence order**; it only changes the ability to represent absence vs value and validity checks.

### When a file is no longer loaded

If `spring.config.location` is used to replace default Config Data search locations, the file containing `app.batch.enabled` may no longer be read. Then `@NotNull Boolean enabled` catches the missing configuration instead of letting a primitive default silently turn the feature off.

That is the operational benefit of fail-fast: an unintended change in file loading surfaces at startup rather than after business logic runs.

## 17. Testing missing-property scenarios with `ApplicationContextRunner`

A test should verify not only **correct values when fully configured**, but also how the application reacts **when configuration is missing**.

Use `ApplicationContextRunner` from `spring-boot-test` and register the configuration bean:

~~~java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "app.orders")
public record OrdersProperties(
        @NotNull Boolean processingEnabled,
        @NotNull @Min(1) Integer maxBatchSize) {
}
~~~

Test:

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.orders.config.OrdersProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

class OrdersPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BindingConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(OrdersProperties.class)
    static class BindingConfig {
    }

    @Test
    void missingRequiredPropertyFailsAtStartup() {
        runner.withPropertyValues(
                "app.orders.processing-enabled=false")
                .run(context -> {
                    assertThat(context).hasFailed();
                });
    }

    @Test
    void explicitFalseAndValidBatchSizeAreAccepted() {
        runner.withPropertyValues(
                "app.orders.processing-enabled=false",
                "app.orders.max-batch-size=100")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    OrdersProperties props =
                            context.getBean(OrdersProperties.class);

                    assertThat(props.processingEnabled()).isFalse();
                    assertThat(props.maxBatchSize()).isEqualTo(100);
                });
    }

    @Test
    void invalidNumberFailsAtStartup() {
        runner.withPropertyValues(
                "app.orders.processing-enabled=true",
                "app.orders.max-batch-size=0")
                .run(context -> {
                    assertThat(context).hasFailed();
                });
    }
}
~~~

This test assumes the project has `spring-boot-starter-test` and `spring-boot-starter-validation`. When applying it to a real codebase, ensure the configuration-properties class is in the right package and a validation provider is available in the test context.

The three cases answer three distinct questions:

1. Is missing `max-batch-size` caught?
2. Is an explicit `false` from the user accepted?
3. Is `0` rejected when the contract requires at least 1?

### Comparison test with primitives

To see the difference, create a record without validation:

~~~java
@ConfigurationProperties(prefix = "app.unsafe")
public record UnsafeProperties(
        boolean enabled,
        int concurrency) {
}
~~~

When the bean is bound without those two properties, you can observe `false` and `0`. A test asserting `assertThat(props.enabled()).isFalse()` and `assertThat(props.concurrency()).isZero()` only proves the object was constructed with those values—**not** that the operator intentionally configured them.

### Testing intentional `@DefaultValue`

~~~java
@ConfigurationProperties(prefix = "app.safe-default")
public record SafeDefaultProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("4") int concurrency) {
}
~~~

When properties are absent, the test should observe `enabled=true` and `concurrency=4`. If the test provides `app.safe-default.enabled=false` and `app.safe-default.concurrency=8`, those explicit values must take precedence over defaults.

## 18. Reading `Environment` for diagnostics vs binding primitives

When you need to check whether a property was actually supplied, you can use `Environment`:

~~~java
import org.springframework.core.env.Environment;

String rawConcurrency =
        environment.getProperty("app.worker.concurrency");

if (rawConcurrency == null) {
    System.out.println("app.worker.concurrency is not configured");
}
~~~

In simple cases, `getProperty` returns `null` when the property is not found. However, this check queries `Environment`, **which differs from reading a bound primitive component**.

Example:

~~~java
int fromRecord = workerProperties.concurrency();
String fromEnv = environment.getProperty("app.worker.concurrency");
~~~

When the property is missing:

~~~text
fromRecord = 0
fromEnv    = null
~~~

Thus, if you need to detect absence at a specific point, you can query `Environment`. Still, a more sustainable design for a **configuration group** is declaring the contract explicitly on `@ConfigurationProperties` and using validation, rather than scattering `getProperty(...) == null` checks throughout the codebase.

### Avoid printing sensitive data

To troubleshoot binding issues, printing only property names and "present/absent" status often suffices. Never print tokens, passwords, or secrets to logs. Spring Boot Actuator offers endpoints to inspect configuration, provided they are enabled, access-restricted, and properly masked.

## 19. Workflow for designing configuration data types

When adding a property, ask these questions in order:

**Question 1: Can this property be validly omitted?**

- If **no**: use a type that can represent null at binding time if absence must be distinguished, such as `Integer`/`Boolean`, then add `@NotNull` or equivalent validation.
- If **yes**: define an explicit default or intentional null handling.

**Question 2: Are zero/`false` valid values?**

- If **yes**: avoid constraints that reject them. If explicit declaration is still required, use a wrapper + `@NotNull`.
- If **no**: add constraints like `@Min(1)`/`@Positive` as appropriate.

**Question 3: Is there a clear business default?**

- If **yes**: for records, use `@DefaultValue` or put it in a config file under a consistent convention.
- If **no**: do not rely on implicit primitive defaults.

**Question 4: Which nested group does the property belong to?**

- Use nested records when keys share a common prefix.
- Choose `@NotNull`/`@Valid` if the nested object is required; choose empty `@DefaultValue` if there is a policy to create a default nested object.

**Question 5: Do tests for missing cases exist?**

- Test missing values, explicit `0`, explicit `false`, wrong types, and valid values.
- Do not test only the happy path with complete data.

The goal is not using wrappers on every single field; the goal is **accurately expressing the configuration contract and preventing hidden bugs**.

## 20. Common misconceptions

### "Application starts means all required properties were declared"

Incorrect. Using primitives without validation allows missing properties to produce a type-valid Java object that is wrong for business logic.

### "`@NotNull` on `int` catches missing properties"

No. `int` cannot be null. If you must know whether the property was supplied, use `Integer` + `@NotNull`.

### "`@Min(1)` on `Integer` catches all missing cases"

Not necessarily. For reference types, numeric range constraints generally do not treat `null` as invalid. Add `@NotNull` if presence is required.

### "`false` is always an error value"

No. `false` can be an operator's valid choice. What you need to catch is a **missing decision** when business rules require explicit configuration.

### "`@DefaultValue` guarantees valid values"

No. `@DefaultValue("0")` can still violate `@Min(1)`. A default supplies an input value to the Binder; it does not replace validation.

### "Setting `@DefaultValue` writes the value into `Environment`"

No. The annotation supplies a default when **binding** the object; it is not a command to insert a property into PropertySources. So `properties.concurrency()` may return `4`, while `environment.getProperty("app.worker.concurrency")` remains `null` if no source property exists.

### "Simply using `Boolean` makes the app fail fast when missing"

No. Wrappers allow representing `null`, but do not fail fast on their own. Use Bean Validation or explicit checks at the configuration boundary.

### "All missing configuration should have defaults"

No. For production endpoints, transaction limits, secrets, access rights, or critical business flags, absence should often be treated as a startup error.

## 21. Practice exercises

### Exercise 1 — Predict results from primitives

Given:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        int retries,
        boolean enabled) {
}
~~~

Neither `demo.retries` nor `demo.enabled` exists in configuration sources. Assuming the Binder constructs the object successfully, predict both components.

**Answer:** typically `0` and `false`. These two values do not prove an operator actively supplied them.

### Exercise 2 — Distinguish missing from `false`

A feature requires deployers to explicitly choose enabled or disabled. Choose the type and validation.

**Answer:**

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.feature")
public record FeatureProperties(
        @NotNull Boolean enabled) {
}
~~~

`null` represents missing; `false` is a valid choice.

### Exercise 3 — Zero is a business error

`demo.pool.size` must be between 1 and 32. Build the appropriate configuration.

**Answer:**

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.pool")
public record PoolProperties(
        @NotNull @Min(1) @Max(32) Integer size) {
}
~~~

If missing, `@NotNull` fails; if `0`, `@Min(1)` fails; if `64`, `@Max(32)` fails.

### Exercise 4 — Zero is a valid value

A port can be `0` to mean the framework picks a port automatically, yet users must supply it explicitly. Do not attach `@Min(1)`. Use `@NotNull Integer port` and add constraints matching valid system port values, including 0.

### Exercise 5 — Choose an intentional default

A job allows omitting `demo.job.max-items` and will use `500`.

**One way to write it:**

~~~java
@ConfigurationProperties(prefix = "demo.job")
public record JobProperties(
        @DefaultValue("500") int maxItems) {
}
~~~

Try overriding via `--demo.job.max-items=200`; the final value must be `200`.

### Exercise 6 — Spot the typo

YAML has:

~~~yaml
demo:
  worker:
    concurreny: 5
~~~

The record expects `concurrency`. Explain why an unvalidated primitive `int concurrency` can yield `0`, and fix the property name.

### Exercise 7 — Missing nested object

A record has `Retry retry` containing `int maxAttempts`. There are no `demo.client.retry.*` properties. Distinguish two scenarios:

- `retry` is `null` because the nested object does not exist.
- `retry` is created, yet `maxAttempts` has no source value and is `0`.

Then design one of two policies: require retry via `@Valid @NotNull` and wrappers, or use empty `@DefaultValue` with valid defaults.

### Exercise 8 — Test fail-fast

Write an `ApplicationContextRunner` test with `@NotNull Integer batchSize`; omit `demo.batch.batch-size`, then assert the context fails. Supply `batch-size=10` and assert the context starts successfully.

### Exercise 9 — Do not use defaults for secrets

A configuration `app.payment.api-token` is required. Choose `@NotBlank String apiToken` instead of `@DefaultValue("demo")`; explain the risk of using a dummy token when production configuration is missing.

## 22. Summary

Primitive types `int`, `long`, and `boolean` are convenient in Java, yet **cannot represent a "no value" state using null**. During binding, missing properties can silently become `0` or `false` without immediate errors, letting the application misbehave in hard-to-spot ways.

When missing values are **valid**, declare an intentional default via `@DefaultValue` or configuration files. When values are **required**, consider `Integer`/`Boolean` wrappers with `@NotNull` and constraints like `@Min`, `@Max`. For nested configuration, handle both nested object presence and child field validation.

Design principle: **never let implicit Java type defaults stand in for an operator's configuration decision**. Type selection, defaults, and validation must follow the business contract, backed by tests for missing settings, explicit `0`/`false`, and invalid data.

## References

- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 — Constructor Binding](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding)
- [Spring Boot 3.3 — Configuration Properties Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Boot 3.3 — @DefaultValue API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/DefaultValue.html)
- [Jakarta Bean Validation — Built-in Constraints](https://jakarta.ee/specifications/bean-validation/)
