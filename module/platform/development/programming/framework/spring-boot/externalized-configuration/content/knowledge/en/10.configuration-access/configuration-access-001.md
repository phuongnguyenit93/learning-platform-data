# Choosing Environment, @Value, or @ConfigurationProperties Based on Your Needs

In Spring Boot, configuration can come from many sources: `application.properties`, `application.yml`, profile-specific files, environment variables, JVM system properties, command-line arguments, or imported Config Data. When writing Java code, you commonly encounter three ways to retrieve these values:

1. **`Environment`**: looks up a key by name at the time the code calls the API.
2. **`@Value`**: injects a value or expression into a constructor, field, or parameter.
3. **`@ConfigurationProperties`**: binds a **group of keys sharing a common meaning** into a typed Java object.

No single approach is best for every situation. Choosing the right one depends on **the number of keys, how they are used, the level of validation needed, the stability of the configuration model, testability, and when the values are read**. This article builds a decision map, provides equivalent examples for the same group of properties, and then applies them to real-world scenarios in a Spring Boot application.

## 1. From configuration sources to Java code

~~~text
application.yml / application.properties / profile config
                  |
Environment variables / -D / --key=value / Config Data import
                  |
                  v
           Spring Environment
           - PropertySources with precedence order
           - Key lookup and basic types
                  |
         +--------+----------------+
         |        |                |
         v        v                v
   Environment   @Value    @ConfigurationProperties
   getProperty   injection       Boot Binder
         |        |                |
         v        v                v
   Value by      A few          Typed, validatable
   key name      values         configuration object
         |        |                |
         +--------+----------------+
                  |
                  v
             Business bean
~~~

**All three approaches can observe the effective value of the same key**. They do not represent three different configuration files. Spring Boot combines sources according to precedence order; which access mechanism you choose only determines *how application code represents and uses that value*.

Shared example used in this article:

~~~yaml
# application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 3
    enabled: true
~~~

The corresponding canonical names are `app.client.base-url`, `app.client.connect-timeout`, `app.client.read-timeout`, `app.client.max-retries`, and `app.client.enabled`.

If you run:

~~~bash
java -jar order-service.jar --app.client.connect-timeout=500ms
~~~

then `app.client.connect-timeout` normally has the effective value `500ms`, because application arguments take precedence over standard Config Data. All three mechanisms can use that effective value in their own way; there is no need to rewrite source precedence logic in Java.

## 2. Quick selection table

| Criterion | `Environment` | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- | --- |
| Primary need | Look up a key by name in code | Inject a few individual values | Model an entire configuration group |
| Where is the key placed? | In the `getProperty` call | In the annotation expression | Set prefix once; the rest maps by property name |
| Typical timing | When the lookup method runs | When Spring creates/injects the bean | When Spring Boot creates and binds the configuration bean |
| Type conversion | Via overloads with a `Class<T>` parameter | Via conversion during injection | Binder supports many types and structures |
| Default value | Overloads with a default or manual handling in code | Placeholders such as `${key:default}` | Designed with defaults/constructors/appropriate binding |
| Group-wide validation | Written manually in the consumer | Scattered, inconvenient for large groups | Well suited for combining with Bean Validation |
| Nested configuration/list/map | Must traverse or bind manually | Inconvenient for complex models | Primary purpose of the Binder |
| Reusability | Easily turns into repeated key strings | Suitable when using few keys | Standalone object injectable in many places |
| Choose when | Dynamic key names or infrastructure operations are needed | 1–2 simple values are needed | There is a configuration group with clear meaning |

**Practical rule:** when multiple parameters describe the same connection, feature, or business component, think of `@ConfigurationProperties` first; when only a single value is needed, `@Value` may suffice; when you need to determine keys at runtime or work directly with `PropertySource`, use `Environment`.

This is a selection guideline, not a ban on the other options.

## 3. Environment: look up keys when needed

`org.springframework.core.env.Environment` is a Spring Framework interface that provides property lookup and profile reading capabilities. You can inject it via constructor:

~~~java
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ClientSettingLookup {
    private final Environment environment;

    public ClientSettingLookup(Environment environment) {
        this.environment = environment;
    }

    public Duration connectTimeout() {
        return environment.getProperty(
            "app.client.connect-timeout",
            Duration.class,
            Duration.ofSeconds(2)
        );
    }

    public boolean isEnabled() {
        return environment.getProperty(
            "app.client.enabled",
            Boolean.class,
            false
        );
    }
}
~~~

Its strongest point is that **the key can be determined in program logic**, and the method can call `getProperty(...)` at the moment the result is needed.

Commonly used read methods:

~~~java
String raw = environment.getProperty("app.client.base-url");

Duration timeout = environment.getProperty(
    "app.client.connect-timeout", Duration.class);

int retries = environment.getProperty(
    "app.client.max-retries", Integer.class, 3);

String required = environment.getRequiredProperty(
    "app.client.base-url");

String[] activeProfiles = environment.getActiveProfiles();
~~~

Meaning:

- `getProperty(key)` gets the value by key name, typically as a `String` or `null` if no value exists.
- `getProperty(key, Type.class)` uses the conversion service to convert to the appropriate target type; when missing it can be `null` if the type is an object.
- `getProperty(key, Type.class, defaultValue)` returns the default value when the property is not found.
- `getRequiredProperty(key)` expresses a required key and can throw an exception when missing.
- `getActiveProfiles()` is for observing profiles, not for retrieving the value of a business property.

### When the key name changes at runtime

An example is multiple connections to systems with different identifiers:

~~~properties
app.targets.alpha.timeout=2s
app.targets.beta.timeout=5s
~~~

You can look up based on a selection:

~~~java
import java.time.Duration;

public Duration timeoutFor(String target) {
    String key = "app.targets." + target + ".timeout";
    return environment.getProperty(
        key, Duration.class, Duration.ofSeconds(3));
}
~~~

In this situation, the code knows `target` at runtime so there is a reason to use the lookup API. However, if the set of targets is statically defined in configuration, a `Map<String, TargetProperties>` bound with `@ConfigurationProperties` can also be clearer. Do not confuse "needing to look up by dynamic name" with "having to use manual key strings everywhere".

### Limitations of manual lookup

If every service writes strings like `app.client.connect-timeout` and `app.client.max-retries` in many places, changing the prefix becomes difficult. One service might handle a missing key with a different fallback than another. Value validation also becomes scattered.

`Environment` is very suitable for infrastructure configuration components, components that need to know active profiles, or a logic branch that genuinely needs to look up a key by name. For a *fixed and structured configuration set*, a typed solution is usually easier to evolve.

## 4. @Value: inject one or a few individual values

`@Value` can accept a `${...}` placeholder in the annotation. Common form:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class AuditFeature {
    private final boolean enabled;

    public AuditFeature(
        @Value("${app.client.enabled:false}") boolean enabled
    ) {
        this.enabled = enabled;
    }

    public boolean enabled() {
        return enabled;
    }
}
~~~

In `${app.client.enabled:false}`:

- `app.client.enabled` is the property name.
- `false` after `:` is the fallback when the placeholder cannot find the key under the applicable resolution mechanism.
- The value is injected into the constructor as a `boolean`.

Another example for a duration value:

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class TimeoutReporter {
    private final Duration timeout;

    public TimeoutReporter(
        @Value("${app.client.connect-timeout:3s}") Duration timeout
    ) {
        this.timeout = timeout;
    }

    public Duration value() {
        return timeout;
    }
}
~~~

`@Value` does not require field injection:

~~~java
@Value("${app.client.max-retries:3}")
private int maxRetries;
~~~

The field form still works in Spring-managed beans, but **constructor injection** usually helps declare dependencies clearly and makes creating objects in unit tests easier.

### Single value, minimal logic, minimal constraints

For example, you have a bean that only needs one small flag:

~~~properties
app.feature.email-preview-enabled=true
~~~

~~~java
@Component
public class EmailPreviewPolicy {
    private final boolean previewEnabled;

    public EmailPreviewPolicy(
        @Value("${app.feature.email-preview-enabled:false}")
        boolean previewEnabled
    ) {
        this.previewEnabled = previewEnabled;
    }
}
~~~

This is a situation where `@Value` makes sense: a simple property, no configuration group to model, and no cross-field validation needed.

### @Value supports SpEL

Besides placeholders, `@Value` is also used with Spring Expression Language (SpEL), for example:

~~~java
@Value("#{2 * 60}")
private int seconds;
~~~

SpEL is a tool for certain specific expression cases, not a reason to put complex business logic into annotations. For grouped configuration, the clear structures and type checking of `@ConfigurationProperties` are usually easier to read.

### When does @Value start becoming hard to manage?

Suppose an HTTP client has five properties:

~~~java
public RemoteClient(
    @Value("${app.client.base-url}") URI baseUrl,
    @Value("${app.client.connect-timeout:2s}") Duration connectTimeout,
    @Value("${app.client.read-timeout:5s}") Duration readTimeout,
    @Value("${app.client.max-retries:3}") int maxRetries,
    @Value("${app.client.enabled:true}") boolean enabled
) {
    // ...
}
~~~

This code can still work, but the prefix and fallbacks are repeated, the constructor becomes hard to scan, and validation such as "max retries must be within an allowed range" has no centralized place to be expressed. When multiple beans need those same properties, the risk of defining inconsistent fallbacks grows even larger.

At this threshold, a `ClientProperties` object makes clearer sense.

## 5. @ConfigurationProperties: map a group of keys to a typed object

`@ConfigurationProperties` is the Spring Boot Binder mechanism for configuration groups sharing a common prefix.

Source file:

~~~yaml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 3
    enabled: true
~~~

Java record:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    Duration readTimeout,
    int maxRetries,
    boolean enabled
) {}
~~~

Spring Boot Binder resolves the corresponding keys and converts their types:

| Key name | Record component | Type |
| --- | --- | --- |
| `app.client.base-url` | `baseUrl` | `URI` |
| `app.client.connect-timeout` | `connectTimeout` | `Duration` |
| `app.client.read-timeout` | `readTimeout` | `Duration` |
| `app.client.max-retries` | `maxRetries` | `int` |
| `app.client.enabled` | `enabled` | `boolean` |

You can inject that record into multiple beans without repeating key strings:

~~~java
import org.springframework.stereotype.Service;

@Service
public class RemoteOrderClient {
    private final ClientProperties properties;

    public RemoteOrderClient(ClientProperties properties) {
        this.properties = properties;
    }

    public void describeNonSensitiveConfig() {
        System.out.println("Target: " + properties.baseUrl());
        System.out.println("Timeout: " + properties.connectTimeout());
        System.out.println("Retries: " + properties.maxRetries());
    }
}
~~~

A typed object centralizes the component's configuration interface. When changing how values are supplied from YAML to environment variables or system properties, `RemoteOrderClient` continues using `ClientProperties`.

### Registering the configuration bean properly

Simply adding `@ConfigurationProperties` onto a record is not enough for Spring to create a bean. With Spring Boot, you can enable scanning:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` scans configuration classes/records within the appropriate package scope. Another option when you want explicit registration:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(ClientProperties.class)
public class ClientPropertiesConfiguration {
}
~~~

You can use the registration style that fits the project's module structure. There is no need to add both approaches for the same properties type just "to be sure".

### Record or mutable JavaBean?

With configuration suitable for constructor binding, a Java `record` expresses an immutable object cleanly. Spring Boot 3.x can infer constructor binding for a record with a suitable single constructor when the bean is registered via standard configuration properties mechanisms.

A JavaBean form can also be bound:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private int concurrency = 4;
    private Duration pollInterval = Duration.ofSeconds(5);

    public int getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(int concurrency) {
        this.concurrency = concurrency;
    }

    public Duration getPollInterval() {
        return pollInterval;
    }

    public void setPollInterval(Duration pollInterval) {
        this.pollInterval = pollInterval;
    }
}
~~~

The JavaBean form can keep defaults in field initializers and setters for the Binder. The immutable form is suitable when you do not want consumers to accidentally mutate configuration after bean creation. Both styles have value, depending on how the application wants to design its contract.

## 6. Type conversion: differences in ergonomics

All three mechanisms can produce types other than `String`, but the developer experience is not the same.

### Environment: caller specifies the type at each call

~~~java
Duration duration = environment.getProperty(
    "app.client.connect-timeout",
    Duration.class);
~~~

The caller must know the exact key and type. With many keys, you have to call it multiple times or write an adapter layer.

### @Value: type is expressed at the injection point

~~~java
public ClientProbe(
    @Value("${app.client.max-retries:3}") int retries,
    @Value("${app.client.connect-timeout:2s}") Duration timeout
) {
    // ...
}
~~~

This is convenient when there are only one or two values.

### @ConfigurationProperties: types belong to the model

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Types and property names coexist in one structure. The Binder also supports nested objects, collections, maps, and specialized data types when an appropriate converter is available.

Example of a configuration group with a nested part:

~~~yaml
app:
  storage:
    endpoint: https://storage.example.test
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
    URI endpoint,
    Retry retry
) {
    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}
}
~~~

A consumer only needs `storageProperties.retry().maxAttempts()` instead of concatenating long key strings manually.

## 7. Relaxed binding and key naming

Spring Boot Binder understands common naming conventions when binding, such as `connect-timeout` in files and `connectTimeout` in Java. You should write keys in configuration files in **lowercase kebab-case**:

~~~properties
app.client.connect-timeout=500ms
app.client.max-retries=3
~~~

When using environment variables, the rules for converting from canonical names to environment variable names may use different separators:

~~~text
app.client.connect-timeout -> APP_CLIENT_CONNECTTIMEOUT
app.client.max-retries     -> APP_CLIENT_MAXRETRIES
~~~

`@ConfigurationProperties` is designed to support relaxed binding with appropriate configuration sources. `@Value` does not have the same level of relaxed binding support as the Binder; when writing placeholders for `@Value`, you should use the canonical name:

~~~java
@Value("${app.client.connect-timeout:2s}")
private Duration timeout;
~~~

Using consistent key spelling gives placeholder resolution the opportunity to apply name variants from `Environment` according to the corresponding Spring Boot rules. Do not rely on arbitrary key spellings like `connectTimeout` in one place and `connect_timeout` in another if you want maintainable configuration.

**Agreed property names** are not a typo-correction feature. `app.client.connect-timeout` and `app.clients.connect-timeout` are two different prefixes; no mechanism automatically infers that you mistyped `client` as `clients`.

## 8. Missing, null, empty values, and fallbacks

Distinguish three situations:

1. The key is not declared in the effective sources.
2. The key exists with an empty value, such as `app.client.base-url=`.
3. The key has text that cannot be converted to the required Java type, such as `app.client.max-retries=several`.

### With Environment

~~~java
String url = environment.getProperty("app.client.base-url");

Duration timeout = environment.getProperty(
    "app.client.connect-timeout",
    Duration.class,
    Duration.ofSeconds(3));
~~~

`getProperty` can return `null` when the key is missing and there is no default. With an overload that has a default, the fallback is applied when the lookup yields no value; if there is a malformed value, the conversion step can still fail. Do not treat fallback as a mechanism to silently ignore all data errors.

### With @Value

~~~java
@Value("${app.client.connect-timeout:3s}")
private Duration timeout;
~~~

The `:3s` placeholder part is the default when no value is found. It does not mean every malformed string is replaced with `3s`.

If you want to require a key, you can omit the default:

~~~java
@Value("${app.client.base-url}")
private String baseUrl;
~~~

Depending on the context and placeholder resolution configuration, an unresolved placeholder can cause bean initialization to fail. For required values and multiple constraints, a configuration model with Bean Validation is usually more transparent.

### With @ConfigurationProperties

The JavaBean form can retain defaults:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private int concurrency = 4;

    public int getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(int concurrency) {
        this.concurrency = concurrency;
    }
}
~~~

If the `app.worker.concurrency` key is not provided, the field can retain the default `4` in this JavaBean binding approach. If a valid value is present, the Binder updates it to that value.

With record/constructor binding, defaults must be designed appropriately for the types and Binder mechanism in use; do not assume a default in a `@Value` annotation automatically carries over to record properties. If a field is required, use validation rather than an arbitrary default.

## 9. Validation: why should configuration groups be validated together?

Suppose an SMTP client requires:

- `host` must not be blank.
- `port` is between 1 and 65535.
- `max-retries` must not be negative.
- `connect-timeout` must be valid for conversion to `Duration`.

A model can express the basic constraints using Bean Validation:

~~~java
import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
    @NotBlank String host,
    @Min(1) @Max(65535) int port,
    @Min(0) int maxRetries,
    @NotNull Duration connectTimeout
) {}
~~~

When using Jakarta Validation in Spring Boot 3.x, the project needs an appropriate validation dependency, such as `spring-boot-starter-validation` in the dependent application. Register the `MailProperties` bean via scanning or `@EnableConfigurationProperties` as shown earlier.

Example file:

~~~properties
app.mail.host=smtp.example.test
app.mail.port=587
app.mail.max-retries=3
app.mail.connect-timeout=3s
~~~

If `app.mail.port=70000`, the `@Max(65535)` constraint catches the invalid value during binding/validation. If `app.mail.connect-timeout=tomorrow`, conversion to `Duration` can fail immediately during initialization.

If a configuration group has cross-field rules, such as read timeout having to be greater than connect timeout, you can design class-level validation or an appropriate constraint. A collection of `@Value` annotations across multiple services is inconvenient for expressing such a unified configuration contract.

### Where should configuration errors appear?

For an application requiring mandatory keys, **detecting misconfiguration right at startup** usually makes operations easier than waiting for the first request to encounter a `NullPointerException` or format error. `@ConfigurationProperties` combined with validation is the right tool for this goal.

Even so, simply annotating a class does not guarantee validation runs: the class must be registered as a configuration properties bean and the validation dependencies/mechanisms must be available.

## 10. Configuration properties vs. business beans

Responsibilities can be clearly separated:

~~~text
Configuration sources
  -> ClientProperties (holds only the data contract)
      -> RemoteOrderClient (executes business logic)
          -> Controller / Service
~~~

Configuration beans should describe **configuration values and constraints**, while business beans decide how to use those values to open HTTP connections, call APIs, choose retries, or toggle features.

Example:

~~~java
import org.springframework.stereotype.Service;

@Service
public class RemoteOrderClient {
    private final ClientProperties settings;

    public RemoteOrderClient(ClientProperties settings) {
        this.settings = settings;
    }

    public boolean shouldCallRemote() {
        return settings.enabled();
    }
}
~~~

This keeps business code decoupled from file paths: the same record can receive values from YAML, external property sources outside the JAR, profiles, or test properties.

If a `@ConfigurationProperties` class becomes the place that initializes an HTTP client or executes network calls, it is taking on extra responsibility. Usually, you should keep this kind of object as typed configuration and inject it into the executing component.

## 11. When conditional bean creation is needed, must you read via Environment?

Not always. If the goal is "only create a bean when a key has a specific value", Spring Boot has conditional annotations such as `@ConditionalOnProperty`:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.feature",
        name = "audit-enabled",
        havingValue = "true"
    )
    AuditService auditService() {
        return new AuditService();
    }
}
~~~

`AuditService` here is an application-defined type. `@ConditionalOnProperty` checks `Environment` during bean condition evaluation. This is a **bean selection mechanism**, not a fourth way to arbitrarily read properties into business logic.

If you need to check profile state to decide on a bean, `@Profile` can also be suitable:

~~~java
@Bean
@Profile("dev")
ClientTransport localClientTransport() {
    return new LocalClientTransport();
}
~~~

There is no need to write a component that reads `Environment.getActiveProfiles()` and manually registers beans in every case. Choose conditional annotations if it is a structural decision at startup; choose a config-reading API if the bean already exists and needs values.

## 12. When values are read: runtime lookup does not mean automatic refresh

One reason to use `Environment` is being able to call `getProperty` multiple times:

~~~java
public boolean enabledNow() {
    return environment.getProperty(
        "app.feature.enabled", Boolean.class, false);
}
~~~

However, reading on every call **does not automatically make Spring Boot reload a YAML/properties file just edited on disk**. Standard Config Data is processed when the application starts. For `@Value` and `@ConfigurationProperties` beans, injected/bound values generally remain unchanged for the bean's lifecycle unless a specialized refresh/rebind mechanism is in place.

Distinguish:

- **API call time**: `Environment.getProperty` executes when the method runs.
- **Configuration source update time**: depends on how each `PropertySource` is created or modified.
- **Bean value reception time**: `@Value` and Binder typically produce results during bean initialization; changing a file does not mean values are re-injected.

If there is a genuine dynamic configuration requirement, establish a dedicated management/refresh mechanism and verify synchronization, safety, and consistency conditions. Do not choose `Environment` just because you expect it to watch all config files automatically.

## 13. Diagnostics: System.getProperty, Environment, and Binder

The following three calls are not equivalent:

~~~java
System.getProperty("app.client.connect-timeout");

environment.getProperty("app.client.connect-timeout");

clientProperties.connectTimeout();
~~~

- `System.getProperty(...)` only reads JVM system properties, for example a key passed via `-Dapp.client.connect-timeout=1s`.
- `environment.getProperty(...)` looks up across Spring `PropertySource`s, comprising multiple configuration sources.
- `clientProperties.connectTimeout()` reads the value already bound into the object during bean creation.

Example:

~~~properties
# application.properties
app.client.connect-timeout=3s
~~~

When there is no corresponding `-D`:

~~~text
System.getProperty("app.client.connect-timeout")
  -> null

Environment.getProperty("app.client.connect-timeout")
  -> "3s"

ClientProperties.connectTimeout()
  -> Duration of 3 seconds
~~~

If you run:

~~~bash
java -Dapp.client.connect-timeout=1s -jar order-service.jar
~~~

the effective value in Spring Boot normally becomes `1s`, unless a higher-precedence source overrides it. The `ClientProperties` object receives a `Duration` corresponding to 1 second.

### Do not assume every source creates a system property

YAML loaded by Spring Boot does not automatically populate `System.getProperty(...)`. If you are using Spring Boot, prefer `Environment` or typed configuration beans to observe effective configuration instead of directly reading `System.getProperty` for business keys.

Similarly, OS environment variables are read with `System.getenv(...)`, whereas Java system properties are read with `System.getProperty(...)`. Spring `Environment` brings these sources into a single lookup system with precedence ordering.

## 14. Testing: which approach keeps tests simple?

### A bean using @Value

With constructor injection, you can test the bean directly without a Spring context:

~~~java
AuditFeature feature = new AuditFeature(true);
assertTrue(feature.enabled());
~~~

That is the benefit of declaring required values in the constructor: unit tests can pass regular arguments. An integration test can ask Spring to resolve real placeholders.

### A bean using Environment

When testing a component that requires `Environment`, you can create a `MockEnvironment` or a test context:

~~~java
import org.springframework.mock.env.MockEnvironment;

MockEnvironment env = new MockEnvironment()
    .withProperty("app.client.connect-timeout", "500ms")
    .withProperty("app.client.enabled", "true");

ClientSettingLookup lookup = new ClientSettingLookup(env);
~~~

`MockEnvironment` is a Spring test utility. For specialized conversions like `Duration`, `MockEnvironment`'s conversion service configuration may not match the Spring Boot runtime identically; if you need to prove exact Boot conversion behavior, run an integration test with a Spring Boot context.

### A bean using @ConfigurationProperties

The record object can be instantiated directly in consumer unit tests:

~~~java
ClientProperties properties = new ClientProperties(
    URI.create("https://api.example.test"),
    Duration.ofMillis(500),
    Duration.ofSeconds(3),
    2,
    true
);
RemoteOrderClient client = new RemoteOrderClient(properties);
~~~

There is no need to force consumer tests to know file paths or key strings. To verify that the Binder works from property sources, use an appropriate Spring Boot context test.

Integration example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "app.client.base-url=https://api.example.test",
    "app.client.connect-timeout=750ms",
    "app.client.read-timeout=4s",
    "app.client.max-retries=5",
    "app.client.enabled=true"
})
class ClientPropertiesIntegrationTest {

    @Autowired
    ClientProperties properties;

    @Test
    void bindsTimeoutAndRetryCount() {
        assertThat(properties.connectTimeout())
            .isEqualTo(Duration.ofMillis(750));
        assertThat(properties.maxRetries()).isEqualTo(5);
    }
}
~~~

This test assumes the application's Spring Boot test context has scanned or enabled `ClientProperties`. Because test properties also participate in precedence order, you can verify binding without modifying real YAML files.

### When tests need minimal infrastructure

Plain Java tests are sufficient to verify consumer logic using a pre-constructed `ClientProperties` object. Only use a Spring Boot context when you need to verify actual property loading, binding, validation, or integration. Avoid routing every unit test through full application startup without reason.

## 15. Choosing by real-world scenario

### Scenario A: a feature toggle flag

~~~properties
app.feature.preview-enabled=false
~~~

A single bean needs this flag:

~~~java
public PreviewController(
    @Value("${app.feature.preview-enabled:false}") boolean enabled
) {
    this.enabled = enabled;
}
~~~

**Suitable choice:** `@Value`, because there is only one scalar and no separate configuration model is needed. If flags grow into a large group used in many places, consider `FeatureProperties`.

### Scenario B: an HTTP client with URL, timeouts, and retries

~~~properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=1s
app.client.read-timeout=4s
app.client.max-retries=3
~~~

**Suitable choice:** `@ConfigurationProperties`. The keys form a shared contract, have multiple types, may need validation, and are injected into multiple components.

### Scenario C: an infrastructure component needing active profiles

~~~java
String[] profiles = environment.getActiveProfiles();
~~~

**Suitable choice:** `Environment` for observing profile state. If the goal is creating beans per profile, using `@Profile` can express intent more clearly.

### Scenario D: needing to read a key chosen by a user in an admin system

~~~java
String key = "app.tenant." + tenant + ".quota";
Integer quota = environment.getProperty(key, Integer.class);
~~~

**Potentially suitable choice:** `Environment`, provided the tenant name is restricted to a valid set and the code understands the fallback policy. If tenants are fully enumerated upfront in configuration, binding a `Map` is also a design worth considering.

### Scenario E: required SMTP, database, or storage config

~~~properties
app.mail.host=smtp.example.test
app.mail.port=587
app.mail.connect-timeout=3s
~~~

**Suitable choice:** `@ConfigurationProperties` accompanied by `@Validated` and necessary constraints. The goal is failing clearly on bad configuration before business logic starts handling requests.

### Scenario F: needing a fallback for a single value

~~~java
@Value("${app.retry.delay:2s}")
Duration retryDelay;
~~~

**Suitable choice:** `@Value` if it is just one property and a simple fallback. When multiple retry parameters are related, grouping them into `RetryProperties` helps ensure consistent checking.

### Scenario G: reusing the same configuration across multiple modules

Several beans all need `app.auth.issuer-uri`, `app.auth.audience`, and `app.auth.clock-skew`.

**Suitable choice:** `@ConfigurationProperties(prefix = "app.auth")` provides a single typed API. Consumers should depend on the configuration record/class rather than declaring three separate `@Value` strings in each place.

### Scenario H: whether a bean is created based on a property

~~~java
@ConditionalOnProperty(
    prefix = "app.feature",
    name = "audit-enabled",
    havingValue = "true"
)
~~~

**Suitable mechanism:** bean creation conditions such as `@ConditionalOnProperty` if this is a structural decision during startup. Once the bean is created, it can still inject typed properties for other values it needs.

## 16. Comparing common failure modes

| Symptom | Environment | @Value | @ConfigurationProperties |
| --- | --- | --- | --- |
| Key does not exist | `getProperty` may return null; `getRequiredProperty` throws | Missing placeholder may cause injection failure depending on resolution | Component may receive null/default; validation is needed to enforce required keys |
| Misspelled key prefix | Lookup finds nothing | Placeholder does not resolve properly | Model fails to bind the intended field; validation helps detect missing required keys |
| Unconvertible value | Fails at the typed lookup call | Fails during injection/conversion | Binding fails during bean creation |
| Multiple fields need constraints | Caller must validate manually | Validation is scattered | Fits group-level Bean Validation |
| Same key is overridden | Value from `Environment` already follows precedence | Placeholder takes result from corresponding source | Binder receives effective value |
| A Java field is renamed | No field mapping if using direct name lookup | Annotation string must be adjusted if key changes | Binder maps by property name and prefix, easier to manage centrally |
| Value needed at method run time | Looked up when called | Value is usually already injected | Value is usually already bound |

The difference in **when errors are detected** has operational significance: critical configuration groups should be validated at bean creation, while on-demand `Environment` lookups need clear error handling at the call site.

## 17. Migrating from multiple @Value annotations to @ConfigurationProperties

Suppose initially you have:

~~~java
@Component
public class ExportService {
    public ExportService(
        @Value("${app.export.path}") String path,
        @Value("${app.export.batch-size:100}") int batchSize,
        @Value("${app.export.enabled:true}") boolean enabled
    ) {
        // ...
    }
}
~~~

As more parameters are added, you can design a typed group:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.export")
public record ExportProperties(
    String path,
    int batchSize,
    boolean enabled
) {}
~~~

After registering the properties bean:

~~~java
@Component
public class ExportService {
    private final ExportProperties properties;

    public ExportService(ExportProperties properties) {
        this.properties = properties;
    }
}
~~~

On the configuration provider side:

~~~properties
app.export.path=/var/app/exports
app.export.batch-size=100
app.export.enabled=true
~~~

This transition makes `ExportService` depend on one model instead of three annotations. If you want to preserve the `batch-size=100` fallback when the key is absent, you must define the corresponding default in the model/binding to avoid accidentally changing from `100` to the primitive `int` default `0`. When refactoring, move meaningful defaults to the right place.

Do not rename a group of keys already used in deployed systems without a compatibility plan. Changing the injection style inside Java does not necessarily require changing public property names.

## 18. Should all keys be placed into one global ConfigurationProperties?

No. If you create an `ApplicationSettings` class with dozens of unrelated groups (mail, payment, storage, feature flags, cache), it easily becomes a hard-to-manage "configuration bag". It is much cleaner to organize by **functional boundaries**:

~~~text
app.mail.*       -> MailProperties
app.storage.*    -> StorageProperties
app.client.*     -> ClientProperties
app.export.*     -> ExportProperties
~~~

A service only injects the model suited to its responsibility. This keeps tests smaller and reduces accidental coupling to another feature's configuration.

Nor do you need to create a `@ConfigurationProperties` class just to hold a single property in every case. Prioritize clarity, testability, and how frequently the configuration group is reused.

## 19. Tracing when the three approaches return unexpected results

When you see an unexpected `connect-timeout` value, check in order:

1. **Canonical key name:** is the code reading `app.client.connect-timeout` or a different prefix?
2. **Loaded documents:** which `application.yml`, profile-specific files, and Config Data imports are present?
3. **Higher-precedence sources:** do environment variables, `-D` JVM system properties, `--key=value` arguments, or test properties set the same key?
4. **Access timing:** when does the `Environment`-using component perform its lookup; when are the `@Value`/`@ConfigurationProperties` beans created?
5. **Type conversion:** is `500ms` converted to `Duration`; is the number valid; is the URI syntactically correct?
6. **Fallbacks and validation:** is the code choosing a default for a missing key or ignoring bad data?
7. **Bean registration scope:** does `@ConfigurationPropertiesScan` scan the configuration record/class?
8. **Refresh expectations:** are you expecting edits to the config file at runtime to automatically update all beans without a refresh mechanism?

With Spring Boot Actuator, `env` and `configprops` (if enabled, secured, and authorized) can help inspect sources and bindings. Do not expose sensitive endpoints publicly or log passwords, tokens, or private keys for debugging. Many sensitive values are sanitized according to configuration.

### When you need to know which source provided a value

`Environment.getProperty` returns the effective value, not always the full origin. Some Config Data mechanisms and Spring Boot observability tools can provide origin/source information. When investigating precedence, use the appropriate tool in a safe environment; do not guess based on the order YAML lines appear in source code.

## 20. Decision-making exercises

**Exercise 1.** A controller only needs the string `app.ui.title` to display a title, with no other constraints.

**Suggested answer:** `@Value("${app.ui.title:Order Service}")` can be a concise solution. If UI settings keep growing, group them into `UiProperties`.

**Exercise 2.** A payment module has an API URL, connect/read timeouts, an API audience, and a retry policy; some fields are required and retry count cannot be negative.

**Suggested answer:** `@ConfigurationProperties(prefix = "app.payment")` combined with Bean Validation, with payment beans injecting the typed object.

**Exercise 3.** A custom framework component needs to read key `app.targets.<name>.endpoint` where `<name>` is a runtime value.

**Suggested answer:** `Environment.getProperty(dynamicKey)` fits when dynamic-name lookup is genuinely required. If the set of targets is provided upfront in configuration, moving to typed `Map` binding is worth considering.

**Exercise 4.** One service uses `@Value("${app.retry.count:3}")` and another uses `Environment.getProperty("app.retry.count", Integer.class, 5)`. When the key is missing, do both services have the same fallback?

**Answer:** no. The first service has fallback `3`; the second service has fallback `5`. This is why grouping semantically shared config helps centralize defaults when needed.

**Exercise 5.** You set `app.client.connect-timeout=2s` in a file and run `java -jar app.jar --app.client.connect-timeout=500ms`. Which timeout does the `ClientProperties` bean receive?

**Answer:** `500ms` assuming no higher-precedence source exists and binding succeeds. The configuration value is resolved by precedence before the Binder converts it into `Duration`.

**Exercise 6.** You change `application.yml` on disk from `2s` to `1s` while the application is already running; can you assert that all `@Value` and `@ConfigurationProperties` beans update automatically?

**Answer:** no. Reloading Config Data and rebinding require a separate mechanism; editing the file does not perform those steps automatically.

**Exercise 7.** You declare a `@ConfigurationProperties` record but forget to scan or enable it. A business bean fails to inject the record. Is it because the YAML file has a syntax error?

**Answer:** not necessarily. Check whether the bean has been registered; merely placing the annotation on the record does not guarantee Spring automatically creates the configuration properties bean.

**Exercise 8.** You need to decide whether to create a bean when `app.feature.audit-enabled=true`. Which approach expresses the intent more accurately: creating the bean and checking inside its constructor, or using `@ConditionalOnProperty`?

**Suggested answer:** `@ConditionalOnProperty` fits if the condition decides **whether to create the bean at startup or not**. Once created, the bean can still inject typed properties for business parameters.

## 21. Decision-making cheat sheet

| Question | Consider first |
| --- | --- |
| "I need to read a key whose name is computed at runtime?" | `Environment` |
| "I only need one simple value in a constructor?" | `@Value` |
| "I need multiple keys belonging to the same configuration?" | `@ConfigurationProperties` |
| "I want to convert from String to Duration, URI, list, or nested object?" | `@ConfigurationProperties` is usually convenient |
| "I want consistent validation for a group of keys?" | `@ConfigurationProperties` + `@Validated` |
| "I want to query active profiles?" | `Environment.getActiveProfiles()` |
| "I want to decide whether a bean should be created?" | `@ConditionalOnProperty` or `@Profile` depending on the situation |
| "I want to test consumers without starting the whole Spring context?" | Inject typed properties or constructor scalars for plain Java tests |
| "I want to know if a value is overridden by another source?" | Inspect `Environment` and the corresponding sources/precedence |
| "I want beans to update automatically when I edit a file at runtime?" | Requires designing refresh/rebind; none of the three mechanisms guarantees that by default |

Follow this final principle: **`Environment` for on-demand queries; `@Value` for injecting small, standalone values; `@ConfigurationProperties` for creating a typed, validatable configuration interface for a functional group**. For the same key, Spring Boot still resolves source precedence before the consumer uses the value. The best choice is the one that gives components clear dependencies, consistent handling of missing/invalid configuration, and straightforward testing.