# Nested Objects When an Entire Property Group Is Absent

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Constructors and records

## 1. Problem: Where Does the Nested Object Go When an Entire Property Group Is Missing?

Spring Boot supports binding configuration from `Environment` into Java objects with `@ConfigurationProperties`. When configuration has multiple levels, a field on the parent object can be a **nested object**.

Example `application.yml`:

~~~yaml
client:
  endpoint: "https://api.example.test"
  retry:
    max-attempts: 3
    backoff: 200ms
~~~

Java record:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        URI endpoint,
        Retry retry
) {
    public record Retry(int maxAttempts, Duration backoff) {}
}
~~~

When `client.retry.max-attempts` and `client.retry.backoff` are present, the Binder has data to create `Retry`. However, if an environment **provides no properties at all in the `client.retry.*` group**:

~~~yaml
client:
  endpoint: "https://api.example.test"
  # No retry:
~~~

then under standard **constructor binding**, the `retry` field can become **`null`**. Do not assume Spring Boot always creates an empty `Retry` or initializes every field to zero.

There are three scenarios to distinguish:

1. **The entire nested group is absent:** no property under `client.retry.*` exists across effective sources.
2. **Only some fields are missing:** `client.retry.max-attempts` is present, while `client.retry.backoff` is absent.
3. **A default nested object is desired:** the constructor parameter/record component is configured with an empty `@DefaultValue`, or a JavaBean uses an appropriate field initializer.

In real applications, this distinction governs `NullPointerException` risk, validation requirements, and default behavior.

### Learning Objectives

- Understand why a nested constructor-bound property can be `null` when the entire group is absent.
- Use **argument-less** `@DefaultValue` to instantiate nested objects when a property group is omitted.
- Set defaults for child fields, including `Duration`, integers, and booleans.
- Compare constructor/record binding with JavaBean binding that uses field initializers.
- Use `@NotNull`, `@Valid`, and `@Validated` when a nested group is required.
- Inspect configuration across sources of varying precedence and test missing-group behavior.

## 2. How Nested Properties Binding Works

`@ConfigurationProperties` is not an ad-hoc YAML parser inside service code. Spring Boot reads configuration sources, resolves properties by precedence, and uses the **Binder** to map key names to fields or constructor parameters.

Example:

~~~yaml
mail:
  sender:
    address: "noreply@example.test"
    display-name: "My App"
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(Sender sender) {
    public record Sender(String address, String displayName) {}
}
~~~

Mapping:

~~~text
mail.sender.address       -> sender.address()
mail.sender.display-name  -> sender.displayName()
~~~

If there is no `mail.sender.*` property and no default on `sender`, the Binder does not necessarily create `Sender`. With a constructor-bound record, the `sender` argument can receive `null`.

**An absent YAML object** is not a guarantee that **an empty Java object is always created**.

### 2.1. A Group Can Come from Multiple Sources

Properties can originate from:

- `application.yml` or `application.properties` on the classpath;
- external configuration files outside the JAR and `spring.config.import`;
- OS environment variables and Java system properties;
- `SPRING_APPLICATION_JSON`;
- command-line arguments;
- test property sources or custom sources.

Therefore, "completely absent group" must be evaluated against **all data visible to the Binder**, not just the contents of a single YAML file. An environment variable like `MAIL_SENDER_ADDRESS` can supply a value even if the main file omits the `sender` branch.

### 2.2. Records and Constructor Binding

In Spring Boot 3, a record with a standard canonical constructor supports constructor binding without needing `@ConstructorBinding`.

~~~java
@ConfigurationProperties(prefix = "sample")
public record SampleProperties(String name, Nested nested) {
    public record Nested(String label) {}
}
~~~

A record has no setters for the Binder to populate fields after creating the object. The Binder must prepare constructor arguments. If the entire nested group is missing, the reference argument can be `null`.

This mechanism **differs** from Spring dependency-injecting a `Nested` bean into a service. This is configuration-data binding, not automatically looking up a Spring bean for every record parameter.

## 3. When the Entire Nested Group Is Absent and No Default Is Declared

### 3.1. Concrete Example

`application.yml`:

~~~yaml
report:
  title: "Daily Report"
~~~

Record:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "report")
public record ReportProperties(
        String title,
        Export export
) {
    public record Export(String format, String directory) {}
}
~~~

When neither `report.export.format` nor `report.export.directory` exists in any source:

~~~text
report.title   -> "Daily Report"
report.export  -> null
~~~

The following code is unsafe without extra guards:

~~~java
public String exportFormat(ReportProperties config) {
    return config.export().format(); // Possible NullPointerException.
}
~~~

This is not a YAML parsing bug. The code assumes the nested object exists, while the configuration contract never required that group to be present.

### 3.2. Missing One Field vs. Missing the Entire Group

If changed to:

~~~yaml
report:
  title: "Daily Report"
  export:
    format: "csv"
~~~

now `report.export.format` exists, giving the Binder a basis to construct the `Export` object. The `directory` field is an unsupplied `String`, so it can be `null` without other defaults or validation:

~~~text
report.export              -> Export(...)
report.export.format       -> "csv"
report.export.directory    -> null
~~~

Do not equate "non-null object" with "all fields populated."

### 3.3. Primitive Types Do Not Force the Parent Object to Exist

Example:

~~~java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(Queue queue) {
    public record Queue(int capacity, boolean enabled) {}
}
~~~

When all `worker.queue.*` keys are absent, `queue` can be `null`. You cannot read `queue.capacity()` to get `0` when `Queue` itself was never created.

When `Queue` is created and a primitive field is missing, primitive default values may be `0` or `false`. However, `0` often makes no sense as a business default; declare defaults explicitly if you need a different value.

## 4. Empty `@DefaultValue`: Creating the Nested Object When the Entire Group Is Missing

Spring Boot supports `@DefaultValue` on constructor parameters or record components. Placing this annotation **without arguments** on a nested-object parameter tells the Binder to instantiate the nested object even when no properties exist for that group.

Spring Boot 3, Java 17+ example:

~~~java
package com.example.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @DefaultValue Queue queue
) {
    public record Queue(
            @DefaultValue("10") int capacity,
            @DefaultValue("false") boolean enabled,
            @DefaultValue("250ms") Duration pollInterval
    ) {}
}
~~~

An `application.yml` with no `worker` branch at all can still yield a `WorkerProperties` bean like:

~~~text
properties.queue()                -> non-null
properties.queue().capacity()     -> 10
properties.queue().enabled()      -> false
properties.queue().pollInterval() -> PT0.25S (Duration 250 ms)
~~~

This illustrates **two levels of defaults**:

1. `@DefaultValue Queue queue` with no string instructs creating `Queue`.
2. `@DefaultValue("10")` and the string-valued annotations on child fields supply default values when corresponding child properties are absent.

### 4.1. Distinguishing `@DefaultValue` Forms

| Syntax | Placed On | Meaning |
| --- | --- | --- |
| `@DefaultValue Queue queue` | Nested object | Instantiate the nested object when no properties exist for the whole group |
| `@DefaultValue("10") int capacity` | Numeric scalar | Use 10 if the field is not provided |
| `@DefaultValue("false") boolean enabled` | Boolean | Use false when the field is not provided |
| `@DefaultValue("250ms") Duration pollInterval` | Duration | Use a 250 ms duration via conversion |

An empty annotation on the object **does not automatically invent meaningful values** for every field inside that object. Configure individual defaults if fields need specific values.

### 4.2. Empty `@DefaultValue` When Child Fields Have No Defaults

~~~java
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        @DefaultValue Credentials credentials
) {
    public record Credentials(String username, String password) {}
}
~~~

If `service.credentials.*` is absent, `Credentials` may still be created, yet the two unsupplied Strings can be `null`:

~~~text
service.credentials            -> non-null object
service.credentials.username   -> null
service.credentials.password   -> null
~~~

**Creating an object != having valid configuration.** If credentials are required, use validation to fail early rather than forcing an empty object into existence.

### 4.3. When Nested Defaults Are Appropriate

Groups that are **optional yet have a default policy** fit this technique: cache policies, retry policies, polling intervals, UI options, or demo-level logging settings.

If `worker.queue.*` is absent, the application still gets `capacity=10`, `enabled=false`, and `pollInterval=250ms`. Services use `properties.queue().capacity()` without repeating fallback logic in many places.

Conversely, a required group holding endpoints or secrets should normally **fail fast when missing**, rather than silently receiving an empty object.

## 5. Multi-Level Nested Trees

Configuration can span multiple levels:

~~~yaml
notifier:
  enabled: true
  channel:
    kind: "email"
  # No notifier.channel.retry group
~~~

Record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "notifier")
public record NotifierProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue Channel channel
) {
    public record Channel(
            @DefaultValue("console") String kind,
            @DefaultValue Retry retry
    ) {}

    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("1s") Duration backoff
    ) {}
}
~~~

Here:

- `channel` has an empty `@DefaultValue` and can be created even without `notifier.channel.*`.
- `retry` inside `Channel` also has an empty `@DefaultValue` so it does not become null when the entire retry group is missing.
- `kind` defaults to `console`, yet the YAML value `email` overrides the default.
- `maxAttempts=3` and `backoff=1s` are used if no source supplies those two fields.

Key takeaway: **each nesting level has its own absence semantics**. If you want a lower-level object to also exist when its group is missing, configure the default on the **parameter at that level**.

### 5.1. Do Not Force Every Optional Group to Have a Default Object

Suppose the notifier has SMS configuration used only when the SMS channel is enabled:

~~~java
@ConfigurationProperties(prefix = "notifier")
public record NotifierProperties(
        @DefaultValue Channel channel,
        Sms sms
) {
    public record Channel(@DefaultValue("console") String kind) {}
    public record Sms(String senderId, String providerUrl) {}
}
~~~

Without `notifier.sms.*`, `sms` can be `null`. That is sensible semantics if the SMS feature is genuinely unconfigured. However, any code using SMS must verify the required configuration is present or add appropriate validation.

## 6. Constructor Binding with Regular Classes

The empty `@DefaultValue` mechanism is not exclusive to records. A constructor-bound class can use it as well:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "batch")
public class BatchProperties {

    private final Retry retry;

    public BatchProperties(@DefaultValue Retry retry) {
        this.retry = retry;
    }

    public Retry getRetry() {
        return retry;
    }

    public static class Retry {
        private final int count;
        private final Duration delay;

        public Retry(
                @DefaultValue("3") int count,
                @DefaultValue("500ms") Duration delay) {
            this.count = count;
            this.delay = delay;
        }

        public int getCount() { return count; }
        public Duration getDelay() { return delay; }
    }
}
~~~

With a single eligible constructor, Spring Boot 3 can perform constructor binding. If the class has multiple constructors, selecting the constructor and placing `@ConstructorBinding` must match your Boot version. Records with a single canonical constructor are usually simpler.

Do not place `@Component` on a constructor-bound record and expect Spring DI to turn parameters into properties automatically. Register the configuration class via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` so Spring Boot uses the Binder properly.

## 7. JavaBean: Nested Field Initializers

JavaBean binding is another approach. The class has a no-args constructor and getters/setters, where the nested field can be **initialized as soon as the parent object is constructed**.

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker")
public class WorkerBeanProperties {

    private Queue queue = new Queue();

    public Queue getQueue() { return queue; }
    public void setQueue(Queue queue) { this.queue = queue; }

    public static class Queue {
        private int capacity = 10;
        private boolean enabled = false;
        private Duration pollInterval = Duration.ofMillis(250);

        public int getCapacity() { return capacity; }
        public void setCapacity(int capacity) {
            this.capacity = capacity;
        }
        public boolean isEnabled() { return enabled; }
        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
        public Duration getPollInterval() { return pollInterval; }
        public void setPollInterval(Duration pollInterval) {
            this.pollInterval = pollInterval;
        }
    }
}
~~~

When `worker.queue.*` is absent, the `new Queue()` initializer still runs. The `Queue` object already exists with field defaults. The Binder can update child fields later if provided.

Comparison:

| Criterion | Record/constructor binding | JavaBean binding |
| --- | --- | --- |
| How nested object is created when group is absent | Empty `@DefaultValue` on parameter | Field initializer such as `new Queue()` |
| How field values are populated | Constructor arguments | Setters/JavaBean properties |
| Mutable after initialization | Record components have no setters | Can be modified via setters |
| Scalar defaults | `@DefaultValue("...")` | Field initializer or configuration sources |
| Primary purpose | Immutability-oriented typed model | Mutable model following JavaBean conventions |

If a JavaBean declares `private Queue queue;` **without an initializer**, then when the property group is absent, the getter can also return `null`. Using a JavaBean does not automatically guarantee the nested object is always non-null.

### 7.1. `@NestedConfigurationProperty` Does Not Create Instances

`@NestedConfigurationProperty` is an annotation for **configuration metadata** tooling. It does not tell the Binder to instantiate a nested object when the group is absent.

When you want a constructor-bound nested object present, the approach covered in this lesson is empty `@DefaultValue`. With JavaBeans, you can use a field initializer.

## 8. Validation: Required or Optional Group?

Choose one of two policies:

- **Optional with defaults:** if the retry group is absent, create a default policy.
- **Required:** if connection details are missing, startup must report a configuration error.

Do not use an empty default object to mask a case where required data has not been provided.

### 8.1. Enabling Bean Validation

In Spring Boot 3, typically add the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Annotations use the `jakarta.validation` package. The `@ConfigurationProperties` class can use `@Validated` to request validation during binding.

### 8.2. Required Nested Object: `@NotNull` and `@Valid`

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "payment")
@Validated
public record PaymentProperties(
        @Valid @NotNull Gateway gateway
) {
    public record Gateway(
            @NotBlank String endpoint,
            @NotBlank String apiKey
    ) {}
}
~~~

If all of `payment.gateway.*` is absent:

- Under constructor binding without empty `@DefaultValue`, `gateway` can be `null`.
- `@NotNull` reports an error because the required object was not supplied.
- `@Valid` asks validation to recurse into the nested object **when an object is present**, checking the constraints on `endpoint` and `apiKey`.

Putting `@Valid` alone does not make a null field required. You need `@NotNull` or an equivalent constraint to reject absence of the whole object.

For sensitive data, do not print `apiKey` in logs or a record's `toString()`.

### 8.3. Nested Object Created by Default Must Still Be Valid

~~~java
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "task")
@Validated
public record TaskProperties(
        @Valid @DefaultValue Retry retry
) {
    public record Retry(
            @Min(1) @DefaultValue("3") int maxAttempts,
            @NotNull @DefaultValue("100ms") Duration backoff
    ) {}
}
~~~

If all of `task.retry.*` is absent, `Retry` is created with `3` and `100ms`; validation runs via `@Valid`.

If a deployment sets `task.retry.max-attempts=0`, `0` is bound instead of the default `3`, and `@Min(1)` catches the violation. Defaults **do not disable validation constraints**.

### 8.4. A Default Object Does Not Guarantee Non-Null Fields

~~~java
@ConfigurationProperties(prefix = "security")
@Validated
public record SecurityProperties(
        @Valid @DefaultValue Credentials credentials
) {
    public record Credentials(
            @NotBlank String username,
            @NotBlank String password
    ) {}
}
~~~

If `security.credentials.*` is absent, `Credentials` may be instantiated, yet `username` and `password` are still missing. Validation will report errors due to `@NotBlank`.

In systems with required credentials, do not assign dummy passwords just to make startup succeed. Pull secrets from proper secret management and validate configuration at startup.

## 9. Optional Nested Objects Need Clear Semantics

Suppose we have notification settings:

~~~java
@ConfigurationProperties(prefix = "notifications")
public record NotificationProperties(
        boolean enabled,
        Smtp smtp
) {
    public record Smtp(String host, int port) {}
}
~~~

When `notifications.smtp.*` is absent, `smtp` can be `null`. That works if `enabled=false` means the application does not use SMTP. Yet when the feature is turned on, SMTP details must exist:

~~~java
if (properties.enabled()) {
    NotificationProperties.Smtp smtp = properties.smtp();
    if (smtp == null) {
        throw new IllegalStateException(
                "SMTP must be configured when notifications.enabled=true");
    }
    // Use smtp.host() and smtp.port().
}
~~~

Checking inside the service is a basic example. In larger applications, you can use cross-field validation or dedicated configuration structures so errors fail early and consistently.

### 9.1. Should You Use `Optional<Nested>`?

Java `Optional` is an API tool for presence/absence. However, do not assume the Spring Boot Binder treats every `Optional<Nested>` as `Optional.empty()` when configuration is missing. Spring Boot notes that `Optional` should not be used casually in `@ConfigurationProperties`: an absent property can be bound as `null`.

A nullable nested field paired with clear validation or defaults is usually easier to predict and test. If you truly want to use `Optional`, verify the exact behavior in the Boot version you run.

## 10. Scalar Defaults and the Difference Between Missing and Invalid

### 10.1. Defaults from `application.yml`

~~~yaml
worker:
  queue:
    capacity: 10
    enabled: false
    poll-interval: 250ms
~~~

If this file is loaded, the nested values exist and can be overridden by higher-precedence sources. Yet if the file is absent in an environment or config data locations change, the entire group can vanish. File defaults alone do not guarantee the nested object will exist in **every deployment setup**.

### 10.2. Defaults on Constructor Parameters

~~~java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(@DefaultValue Queue queue) {
    public record Queue(
            @DefaultValue("10") int capacity,
            @DefaultValue("false") boolean enabled
    ) {}
}
~~~

The goal is an explicit fallback contract right in the Java type. If a deployment sets `worker.queue.capacity=25`, `25` wins over the default `10`.

### 10.3. Primitive Defaults Can Mislead

If a nested object is created without explicit defaults, primitive components can receive `0` or `false`. However:

- `max-attempts=0` might be an invalid setting.
- `port=0` can carry a special meaning, not "default port."
- `timeout=0` can cause unintended behavior.
- `enabled=false` might be safe, yet should be chosen intentionally.

For real policies, use meaningful `@DefaultValue` annotations or validation bounding allowed ranges.

### 10.4. Invalid Property Is Not Equivalent to Missing Property

Example:

~~~properties
worker.queue.poll-interval=not-a-duration
~~~

If the target field is `Duration`, this is a conversion error. Do not expect the Binder to ignore invalid strings and substitute `@DefaultValue("250ms")`. Defaults are for **unprovided values**, not a mechanism to swallow bad input.

## 11. Group Absence Across the Entire Environment

Suppose `application.yml` omits `client.retry`:

~~~yaml
client:
  endpoint: "https://api.example.test"
~~~

Yet CLI supplies:

~~~bash
java -jar app.jar --client.retry.max-attempts=5
~~~

or an environment variable supplies the matching relaxed-binding name. Now `client.retry` **is no longer completely absent** from the data the Binder sees. Even without that branch in YAML, the nested object can be created from the supplied field.

### 11.1. Overriding a Single Field

Default YAML:

~~~yaml
client:
  retry:
    max-attempts: 3
    backoff: 500ms
~~~

CLI:

~~~bash
java -jar app.jar --client.retry.max-attempts=6
~~~

In standard setups:

~~~text
client.retry.max-attempts = 6      (CLI)
client.retry.backoff      = 500ms  (YAML)
~~~

The Binder can combine nested data property by property. Do not assume setting one child key in a higher-precedence source wipes out all other child keys of that object from lower-precedence sources.

### 11.2. Empty Strings and JSON null

Environment variable:

~~~bash
export CLIENT_RETRY_BACKOFF=''
~~~

is not necessarily equivalent to **the property not existing at all**. The Binder may observe an empty value and attempt conversion or handle it via active converters.

Similarly, JSON `null` has specific semantics in Spring Boot externalized configuration: do not rely on it as a guaranteed way to erase values from lower-precedence sources. To disable a feature, use an explicit property such as `enabled=false` instead of relying on null semantics.

## 12. Collections Inside Nested Objects

A present nested object does not guarantee inner `List`/`Map` components are initialized as empty.

~~~java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @DefaultValue Rules rules
) {
    public record Rules(
            List<String> regions,
            Map<String, String> tags
    ) {}
}
~~~

If `routing.rules.*` is absent, `Rules` can be created via the empty `@DefaultValue`, yet you cannot assume `regions` is guaranteed to be `List.of()` and `tags` is guaranteed to be `Map.of()`.

If code needs non-null collections, design controlled defaults/initialization and test the Binder on your target version. Do not assume an annotation on a parent object automatically initializes every child collection.

### 12.1. Lists and Maps Have Different Override Rules

Suppose a lower-precedence source declares:

~~~yaml
routing:
  rules:
    regions: ["a", "b"]
    tags:
      owner: "backend"
      region: "local"
~~~

A higher-precedence source declares regions `["c"]` and only tag `region=apac`. In `@ConfigurationProperties`, lists are usually **replaced** by the list from the higher-precedence source, while maps can be merged entry by entry (keeping `owner`, overriding `region`).

These are collection binding rules, separate from whether a nested object is created when the whole group is absent.

## 13. Registering the Properties Bean Properly

A record with `@ConfigurationProperties` is not enough for Spring to create a bean if the application does not register it.

Option 1, scanning:

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

Option 2, explicit enabling:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(WorkerProperties.class)
class WorkerConfig {}
~~~

You do not need both options for the same class. For constructor-bound records, choose one appropriate mechanism and ensure the scanned packages cover the properties class.

**Two independent questions:**

- Has the `WorkerProperties` bean been registered?
- Will the `queue` field on that bean be null or have defaults when `worker.queue.*` is absent?

Adding `@DefaultValue` does not fix an unregistered class; conversely, registering the bean does not ensure nested fields automatically exist.

## 14. Practical Example: HTTP Client with Default Retry

Suppose every HTTP client requires a base URL, yet can omit the entire retry group to receive a default policy.

~~~java
package com.example.http;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "outbound.http")
@Validated
public record HttpClientProperties(
        @NotNull URI baseUrl,
        @Valid @DefaultValue Retry retry
) {
    public record Retry(
            @Min(1) @DefaultValue("3") int maxAttempts,
            @NotNull @DefaultValue("200ms") Duration delay
    ) {}
}
~~~

Minimal configuration:

~~~yaml
outbound:
  http:
    base-url: "https://partner.example.test"
~~~

Expected result:

~~~text
baseUrl            = https://partner.example.test
retry              = non-null object
retry.maxAttempts  = 3
retry.delay        = 200ms
~~~

If staging sets:

~~~properties
outbound.http.retry.max-attempts=5
~~~

then `maxAttempts` is overridden to `5`, while `delay` continues using `200ms`.

If production sets `outbound.http.retry.max-attempts=0`, `@Min(1)` reports a configuration error instead of letting an invalid policy reach the service at runtime. This is a typical example of combining **defaults for an optional group** with **validation for configured fields**.

## 15. Testing Missing Nested Groups

When a service depends on null/default behavior of a nested object, include binding tests for all three scenarios: completely absent group, single-property group, and full group.

### 15.1. `ApplicationContextRunner`

With Spring Boot Test, you can create a lightweight context without starting a web server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

class WorkerPropertiesBindingTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfig {}

    @Test
    void absentQueueGroupUsesDefaults() {
        runner.run(context -> {
            WorkerProperties props =
                    context.getBean(WorkerProperties.class);

            assertThat(props.queue()).isNotNull();
            assertThat(props.queue().capacity()).isEqualTo(10);
            assertThat(props.queue().enabled()).isFalse();
        });
    }

    @Test
    void partialGroupOverridesOnlyProvidedField() {
        runner.withPropertyValues("worker.queue.capacity=25")
                .run(context -> {
                    WorkerProperties props =
                            context.getBean(WorkerProperties.class);

                    assertThat(props.queue().capacity()).isEqualTo(25);
                    assertThat(props.queue().enabled()).isFalse();
                });
    }
}
~~~

The test uses `WorkerProperties` from Section 4. It checks the result **after binding**, rather than guessing mechanics from YAML syntax. When testing real `application.yml` file loading, use a test setup with config data loading enabled.

### 15.2. Testing the No-Default Case

~~~java
@ConfigurationProperties(prefix = "plain")
public record PlainProperties(Nested nested) {
    public record Nested(String label) {}
}
~~~

When the context has no `plain.nested.*` and no default on `nested`, constructor binding typically yields:

~~~text
plainProperties.nested() == null
~~~

If the application adopts an "optional group" policy, verify this behavior with a test and handle it at usage sites. If you want non-null, change the configuration contract rather than scattering inconsistent null checks across many services.

### 15.3. Testing a Required Group

For `PaymentProperties` with `@NotNull Gateway gateway`, start a context without `payment.gateway.*` and assert that the application fails binding/validation when validation infrastructure is present.

Do not couple tests to an exact exception text snippet; exception names or message formatting can change across framework versions. Assert that the context fails to start normally when required configuration is missing.

## 16. Common Mistakes and Diagnostics

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `properties.retry()` is null | Entire `retry` group is absent and no empty `@DefaultValue` | Decide optional/required; add default or validation |
| Retry object exists yet fields are null | Empty annotation only creates the object; fields lack defaults | Add individual defaults or validation |
| `NullPointerException` in service | Code assumes nested field is always present | Design configuration contract or handle null explicitly |
| Test sees different nested state than expected | Test picks up properties from env/profile/another source | Use an isolated context and check actual sources |
| `@NotNull` fails to catch missing group | Validation not configured properly or bean not bound | Check `@Validated`, validation starter, registration |
| Nested field constraints do not run | Missing cascade `@Valid` | Place `@Valid` on the nested component |
| Primitive field receives 0 | No default on the field being constructed | Use `@DefaultValue("...")` and validation |
| `@NestedConfigurationProperty` did not create object | Annotation is for metadata | Use empty `@DefaultValue` or initializer |
| Cannot inject properties class | Not scanned/enabled properly | `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` |
| Group absent in YAML yet object still exists | Another source supplies a key or default is present | Inspect entire `Environment` and precedence |
| Child list/map behaves unexpectedly | Collections have specific binder semantics | Check source priority and test collection binding |
| Credentials missing yet app still starts | Required group lacks validation | Add constraints and supply secrets securely |

### 16.1. Observing a Non-Sensitive Property

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class ConfigProbe implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    public ConfigProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(org.springframework.boot.ApplicationArguments args) {
        String key = "worker.queue.capacity";
        System.out.println(key + " = " + environment.getProperty(key));
    }
}
~~~

Only use demo keys for diagnostics. Never log passwords, tokens, or configuration objects containing secrets; if using Actuator `env`/`configprops`, secure those endpoints and sanitize sensitive data.

### 16.2. Checklist When a Nested Object Is Unexpectedly Null

1. Check whether the class is bound via `@ConfigurationProperties` and properly scanned/enabled.
2. Check prefix, field names, and relaxed binding.
3. Determine whether **any** matching property exists for the nested group in any source.
4. Check whether the nested constructor parameter/record component has an empty `@DefaultValue`.
5. Check defaults on child fields, especially reference types, `Duration`, lists, and maps.
6. Check validation: `@Validated`, `@Valid`, `@NotNull`, and child constraints.
7. If results differ across environments, check profiles, imports, environment variables, CLI, and test properties.
8. Write binding tests to lock down the semantics the application actually relies on.

## 17. Practice Exercises

### Exercise A — Group Without Defaults

Define:

~~~java
@ConfigurationProperties(prefix = "lesson")
public record LessonProperties(Info info) {
    public record Info(String title, String author) {}
}
~~~

Run with no `lesson.info.*`; observe `info`. Then add `lesson.info.title=Hello` and observe the nested object and the `author` field.

### Exercise B — Empty `@DefaultValue`

Change `Info info` to `@DefaultValue Info info`, add `@DefaultValue("Untitled") String title` and `@DefaultValue("Unknown") String author`. Run with no `lesson.info.*` properties at all. Predict the object and its fields.

### Exercise C — Partial Override

Provide `lesson.info.title=Spring Boot` without supplying `lesson.info.author`. Using the defaulted class from Exercise B, predict the final title and author, and explain why only one field was overridden.

### Exercise D — Required Group

Create `DatabaseProperties` with a required nested `Credentials`, using `@NotNull` and `@Valid`. When the whole group is missing, the application must fail. When only username is supplied, use `@NotBlank` on password to catch the missing field.

### Exercise E — Record vs. JavaBean

Write two versions of `CacheProperties`: a record using empty `@DefaultValue` on nested `Policy` and a JavaBean using `private Policy policy = new Policy()`. Test when the policy group is absent, then test when only one field is supplied.

### Exercise F — Other Configuration Sources

Remove the `lesson.info` group from YAML, yet run with `--lesson.info.title=FromCLI`. Explain why the nested object is still created even though the main file lacks the `info` branch. Try adding an environment variable and check precedence.

## 18. Takeaways

- **Constructor-bound `@ConfigurationProperties` / records:** if the entire nested group is absent and no default is set, the nested object can be **`null`**.
- **Empty `@DefaultValue`** on a nested parameter/record component tells the Binder to instantiate the object even when no properties exist for the whole group.
- **Scalar `@DefaultValue("...")`** on child fields provides default values; creating the object does not mean all child fields are populated.
- **Validation:** use `@NotNull` if the nested object is required, `@Valid` to validate recursively, and `@Validated` with a validator to enforce constraints.
- **JavaBean initializers** like `new Retry()` can create a default nested object, yet follow a different binding lifecycle than records.
- **All configuration sources:** a group missing from YAML may still be present via CLI, env vars, config imports, or other property sources.
- **Explicit design intent:** optional groups should have consistent default/null semantics; required groups should fail startup when missing.

## References

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding typed configuration objects.
- [Spring Boot Reference — Constructor Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding): constructor/record binding and empty `@DefaultValue` for absent nested groups.
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): `@Validated`, `@Valid`, and constraints on nested properties.
- [Spring Boot Reference — Relaxed Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding): mapping property names across sources.
- [Spring Boot Reference — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html): metadata role of `@NestedConfigurationProperty`.
