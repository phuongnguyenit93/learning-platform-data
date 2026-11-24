# Binding to a JavaBean, Constructor, or Record by Version

Spring Boot allows reading configuration from `application.yml`, `application.properties`, environment variables, command-line arguments, and other `PropertySource`s and **binding** (mapping/converting) it into strongly typed Java objects. This mechanism is commonly used through `@ConfigurationProperties`.

There are three common styles for organizing the target class:

1. **JavaBean binding:** instantiates the object via a no-argument constructor and populates properties through setters or compatible mutable properties.
2. **Constructor binding:** Spring Boot reads configuration values, converts types, and passes them into a constructor, making it ideal for immutable objects.
3. **Record binding:** Java records define immutable data more concisely; Spring Boot can use the record's canonical constructor to bind configuration.

The most important detail to note is that **how constructor binding is enabled and where the annotation goes differ by Spring Boot line**. In Boot 2.x, especially 2.2–2.7, regular immutable classes normally require `@ConstructorBinding` at the class level; starting in Boot 3, a single parameterized constructor is usually inferred automatically, while `@ConstructorBinding` moves to the constructor level when needed to specify which constructor to use.

## 1. What need does the binding mechanism serve?

Suppose an application has configuration:

~~~yaml
app:
  notification:
    enabled: true
    sender-name: "Catalog Service"
    retry-count: 3
    connect-timeout: 5s
~~~

You can read individual values using `Environment` or `@Value`, but when a configuration group has multiple properties, scattered reads make code harder to maintain:

~~~java
@Value("${app.notification.retry-count:3}")
private int retryCount;
~~~

Instead, a strongly typed configuration class:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {
    // enabled, senderName, retryCount, connectTimeout
}
~~~

Once properly registered, the Spring Boot Binder reads properties with the `app.notification` prefix and maps them to the matching fields or constructor parameters.

Mapping example:

| Property in YAML | Java property | Type |
|---|---|---|
| `app.notification.enabled` | `enabled` | `boolean` |
| `app.notification.sender-name` | `senderName` | `String` |
| `app.notification.retry-count` | `retryCount` | `int` |
| `app.notification.connect-timeout` | `connectTimeout` | `Duration` |

This is **relaxed binding**: `sender-name` in configuration binds to the Java property `senderName`. Using kebab-case in config files and prefixes keeps naming consistent.

### Binding is more than copying strings

The Binder also performs conversion:

- `"true"` to `boolean`.
- `"3"` to `int`.
- `"5s"` to `Duration.ofSeconds(5)`.
- Suitable values into enums, lists, maps, `DataSize`, and many other types.
- Custom converters can be used when a data type lacks an appropriate default conversion.

These typed bindings catch configuration errors during binding/validation rather than only failing when a service manually parses a string while handling a request.

## 2. @ConfigurationProperties and registering configuration classes

`@ConfigurationProperties` lives in:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
~~~

The annotation describes the **prefix and binding contract**. It does not necessarily register the class as a Spring bean without an appropriate registration mechanism.

Common approaches:

| Registration method | Purpose |
|---|---|
| `@ConfigurationPropertiesScan` | Discovers `@ConfigurationProperties` classes in scanned packages |
| `@EnableConfigurationProperties(MyProperties.class)` | Explicitly registers one or more properties types |
| `@Component` alongside `@ConfigurationProperties` | JavaBean created by component scanning and then bound |
| `@Bean` alongside `@ConfigurationProperties` | Binds onto a bean created by a factory method; useful for third-party types with setters |

**Constructor binding does not apply to beans created via regular Spring instantiation** such as `@Component` or a `@Bean` factory method. To use constructor binding for a configuration class, let Boot register it via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

### Example enabling configuration properties scanning

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` scans by default from the package of the annotated class down into subpackages. You can specify `basePackages` or `basePackageClasses` if properties classes live elsewhere.

### Explicit registration example

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {
}
~~~

When already registered via `@EnableConfigurationProperties`, do not also mark `NotificationProperties` with `@Component`. An application also does not need both scan and enable for the same properties class if only one bean is intended.

## 3. JavaBean binding: instantiate object then call setters

JavaBean binding is Spring Boot's traditional model. The class has a no-argument constructor and getter/setter methods for the Binder to populate properties.

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {

    private boolean enabled;
    private String senderName;
    private int retryCount = 3;
    private Duration connectTimeout = Duration.ofSeconds(5);

    public NotificationProperties() {
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getSenderName() {
        return senderName;
    }

    public void setSenderName(String senderName) {
        this.senderName = senderName;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

With the YAML from the start of this lesson, the Binder sets properties to the corresponding configured values. `retryCount` and `connectTimeout` keep their Java defaults if the properties are omitted.

### 3.1. JavaBean binding sequence

~~~text
Register NotificationProperties bean definition
                  |
                  v
       Create object (no-args ctor)
                  |
                  v
     Binder reads app.notification.*
                  |
                  v
     Convert values to Java types
                  |
                  v
      Invoke setters / bind properties
                  |
                  v
        Validation (if configured)
                  |
                  v
       Bean is used in services
~~~

This is a high-level overview. Binding is integrated into Spring Boot's lifecycle and processors.

Advantages:

- Familiar in projects using traditional JavaBeans.
- Can supply defaults via field initializers.
- Convenient when integrating mutable objects from external libraries.
- Suits many Spring Boot 1.x/2.x projects with setter-based configuration.

Limitations:

- The object can be mutated after binding due to public setters.
- Many fields and setters make classes verbose.
- When shared across multiple beans, code must avoid arbitrarily mutating configuration while running.
- Data immutability is hard to enforce at the constructor level.

### 3.2. Nested properties in JavaBean style

For example:

~~~yaml
app:
  mail:
    host: smtp.example.test
    retry:
      max-attempts: 4
      delay: 2s
~~~

JavaBean:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host;
    private Retry retry = new Retry();

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public Retry getRetry() {
        return retry;
    }

    public void setRetry(Retry retry) {
        this.retry = retry;
    }

    public static class Retry {
        private int maxAttempts = 3;
        private Duration delay = Duration.ofSeconds(1);

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public Duration getDelay() {
            return delay;
        }

        public void setDelay(Duration delay) {
            this.delay = delay;
        }
    }
}
~~~

The nested `Retry` object is pre-initialized so child properties can bind into that instance. For nested JavaBeans lacking suitable setters/constructors/instances, binding capability can be limited; design child object creation clearly.

### 3.3. Not every field needs its own setter

Some pre-initialized mutable structures, such as a `Map` or a nested object with a getter, can be updated by the Binder depending on type and binding rules. However, to avoid relying on subtle behavior, for regular mutable configuration provide setters for externally configured properties, or use constructor binding if immutability is desired.

## 4. Constructor binding: constructing the object from configuration values

Constructor binding passes converted values into a constructor. The object is constructed **after** the relevant configuration data has been resolved:

~~~java
public final class NotificationProperties {
    private final boolean enabled;
    private final String senderName;
    private final int retryCount;

    public NotificationProperties(
            boolean enabled,
            String senderName,
            int retryCount) {
        this.enabled = enabled;
        this.senderName = senderName;
        this.retryCount = retryCount;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public String getSenderName() {
        return senderName;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
~~~

Because fields are `final` and there are no setters, configuration cannot be modified via setters after the object is constructed.

In this section, `NotificationProperties` is illustrated separately per version. **Do not copy multiple versions of a class with the same name into one package in the same project**; the snippets represent alternative options.

## 5. Constructor binding in Spring Boot 2.2–2.7

Spring Boot 2.2 added constructor binding support for `@ConfigurationProperties`. For a regular Java class in the Boot 2.x line, the typical usage is placing `@ConstructorBinding` **on the class**:

~~~java
package com.example.catalog.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.ConstructorBinding;

@ConstructorBinding
@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {

    private final boolean enabled;
    private final String senderName;
    private final int retryCount;

    public NotificationProperties(
            boolean enabled,
            String senderName,
            int retryCount) {
        this.enabled = enabled;
        this.senderName = senderName;
        this.retryCount = retryCount;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public String getSenderName() {
        return senderName;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
~~~

Points to note:

- Boot 2.x import: `org.springframework.boot.context.properties.ConstructorBinding`.
- Annotation is declared at the **class** level under the Boot 2.x API.
- The properties class must be registered with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, not `@Component`.
- Constructor parameter names must match the properties. In regular Java classes, compilation must retain parameter name metadata, typically via the `-parameters` flag.
- When a constructor has multiple parameters, parameter order does not change property names; the Binder matches parameter names against property names after relaxed binding.

Bean registration example:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {
}
~~~

When using the Spring Boot plugin and standard build conventions, the `-parameters` flag is typically configured appropriately. With custom build setups, check compiler arguments if the binder cannot recognize parameter names.

### 5.1. Avoid @Component with constructor binding on Boot 2.x

Do not write:

~~~java
@Component
@ConstructorBinding
@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {
    // ...
}
~~~

A `@Component` class is created via regular bean constructor injection; Spring may interpret primitive or String constructor parameters as bean dependencies to inject rather than properties from `Environment` via constructor binding.

Use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` as in the earlier examples. This also applies when a class is registered by `@Bean` or regular import: constructor binding cannot replace how the container creates beans via factory methods.

## 6. Constructor binding in Spring Boot 3.x

Starting in Boot 3, for a `@ConfigurationProperties` class with **a single eligible parameterized constructor**, constructor binding is normally inferred automatically. `@ConstructorBinding` on the class is no longer needed.

~~~java
package com.example.catalog.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public final class NotificationProperties {

    private final boolean enabled;
    private final String senderName;
    private final int retryCount;

    public NotificationProperties(
            boolean enabled,
            String senderName,
            int retryCount) {
        this.enabled = enabled;
        this.senderName = senderName;
        this.retryCount = retryCount;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public String getSenderName() {
        return senderName;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
~~~

Simply register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. `enabled`, `senderName`, and `retryCount` are read from the same configuration prefix.

### 6.1. When a class has multiple constructors

If there are multiple constructors and you must specify which constructor the Binder should use, Boot 3 provides the annotation:

~~~java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
~~~

Place it on the chosen **constructor**:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public final class NotificationProperties {

    private final String senderName;
    private final int retryCount;

    @ConstructorBinding
    public NotificationProperties(
            String senderName,
            int retryCount) {
        this.senderName = senderName;
        this.retryCount = retryCount;
    }

    public NotificationProperties() {
        this("Catalog Service", 3);
    }

    public String getSenderName() {
        return senderName;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
~~~

Note that in Boot 3, the import `org.springframework.boot.context.properties.bind.ConstructorBinding` is used on constructors. Placing that annotation on the type as in Boot 2 can fail compilation because the annotation target changed.

If a class uses an `@Autowired` constructor to inject Spring beans, that is Spring bean instantiation rather than configuration properties constructor binding. Do not use constructor binding to try mixing Spring bean dependency injection into a properties holder.

### 6.2. Java 17 and version baselines

Spring Boot 3 requires Java 17 or newer. Therefore, Java records are a natural fit for immutable properties classes in Boot 3 projects.

If an application is still on Boot 2.x, check both your Java version and the record support level of that Boot release before adopting records. With Boot 2.7 on Java 17, record binding is a well-supported illustrative case.

## 7. Record binding: concise immutable properties

Java records express an immutable data set cleanly through record components and a canonical constructor.

Boot 3 example:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        boolean enabled,
        String senderName,
        int retryCount,
        Duration connectTimeout) {
}
~~~

When `NotificationProperties` is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, the Binder can use the record's canonical constructor to supply values.

Usage in a service:

~~~java
package com.example.catalog.service;

import com.example.catalog.config.NotificationProperties;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }

    public void printConfiguration() {
        System.out.println(properties.senderName());
        System.out.println(properties.retryCount());
        System.out.println(properties.connectTimeout());
    }
}
~~~

Notice the record accessor syntax: `properties.senderName()`, rather than `properties.getSenderName()` as in JavaBeans. A record automatically generates the constructor, accessors, `equals()`, `hashCode()`, and `toString()` matching its record components.

### 7.1. Records in Spring Boot 2.7

With Spring Boot 2.7 and a record having a single standard canonical constructor, Boot can also infer constructor binding without placing `@ConstructorBinding` on the record.

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        String senderName,
        int retryCount) {
}
~~~

Do not assume that "every Boot 2.x release binds records identically to Boot 3." Records are a newer Java feature than early Boot 2 releases; when supporting a specific older release, verify against that exact version's documentation and APIs.

### 7.2. Records have no setters

You cannot use JavaBean setter binding for a record because record components are final and have no setters. Nor should you expect to mutate fields after creating a record.

If you want configuration directly mutable via Spring-managed setters, a JavaBean is a more natural fit. However, dynamic runtime configuration is a separate concern: using a record or JavaBean does not make Spring Boot automatically rebind every bean when a YAML file changes.

### 7.3. Be careful with record toString()

Records auto-generate a `toString()` that displays component values. If a record holds a password, token, or secret key, **never log the raw object** just for quick debugging.

~~~java
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        String endpoint,
        String apiToken) {
}
~~~

`System.out.println(properties)` risks leaking `apiToken` into logs. Strip or mask sensitive values when logging, and consider dedicated handling for types holding secrets.

## 8. Comparison table across version lines

| Spring Boot line | JavaBean + setters | Regular class constructor binding | Record |
|---|---|---|---|
| Boot 1.x / 2.0–2.1 | Common approach | No `@ConstructorBinding` mechanism like Boot 2.2+ | Not a primary option for these lines |
| Boot 2.2–2.6 | Supported | Uses Boot 2 `@ConstructorBinding` placed on the type | Depends on Java and version-specific support |
| Boot 2.7 | Supported | `@ConstructorBinding` placed on the class | Record with single canonical constructor can be inferred |
| Boot 3.x | Supported | Single constructor normally inferred; multiple constructors can specify via constructor-level annotation | Preferred choice; usually needs no annotation with a single canonical constructor |

Key milestones:

- **Boot 2.2:** introduced constructor binding for `@ConfigurationProperties`.
- **Boot 2.7:** solid support for constructor/record binding in the Boot 2 branch.
- **Boot 3:** changed the namespace/target of `@ConstructorBinding` and infers constructor binding for a single parameterized constructor.
- **Java records:** require a Java version supporting records; Boot 3 has a Java 17 baseline.

Do not upgrade merely by bumping dependencies while keeping Boot 2's `@ConstructorBinding` import unchanged. Code may need to remove the class-level annotation or move it to the appropriate constructor in Boot 3.

## 9. Nested immutable properties with records

Records can contain nested records to express hierarchical configuration:

~~~yaml
app:
  client:
    base-url: https://api.example.test
    retry:
      max-attempts: 5
      backoff: 250ms
~~~

Java record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Retry retry) {

    public record Retry(
            int maxAttempts,
            Duration backoff) {
    }
}
~~~

Usage:

~~~java
String url = properties.baseUrl();
int attempts = properties.retry().maxAttempts();
Duration backoff = properties.retry().backoff();
~~~

If the entire `retry` group is absent from configuration, the nested object value may be `null` under constructor binding/default semantics. Avoid assuming all nested records are automatically instantiated with empty defaults.

You can request a default nested object or set explicit defaults via `@DefaultValue` in supporting versions:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        @DefaultValue Retry retry) {

    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("1s") Duration backoff) {
    }
}
~~~

`@DefaultValue` with no value on a nested parameter can instruct the Binder to instantiate the nested object even when child properties are absent, provided the nested type has a compatible binding structure. Defaults inside `Retry` are used when the corresponding values are omitted. For designs requiring `baseUrl`, add validation.

## 10. Default values: JavaBean vs. constructor/record differences

### 10.1. JavaBean: field initializers

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private int retryCount = 3;

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

If `app.mail.retry-count` is absent, the initialized value `3` is preserved as long as the binder does not overwrite it.

### 10.2. Record: @DefaultValue

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        @DefaultValue("3") int retryCount,
        @DefaultValue("5s") Duration timeout) {
}
~~~

This is the explicit way to declare defaults at constructor parameters or record components.

Without a default:

- Primitives like `int` take the primitive type's default if the property is absent.
- Reference types like `String` or `Duration` can be `null`.
- If a required value is missing, use validation rather than assuming the Binder always treats missing properties as errors.

Binder's `@DefaultValue` is not Spring injection's `@Value`. The two annotations serve different purposes.

### 10.3. Constructor computing default values itself

An immutable class can also handle defaults in its constructor:

~~~java
@ConfigurationProperties(prefix = "app.report")
public final class ReportProperties {

    private final String outputFolder;

    public ReportProperties(String outputFolder) {
        this.outputFolder = (outputFolder == null || outputFolder.isBlank())
                ? "reports"
                : outputFolder;
    }

    public String getOutputFolder() {
        return outputFolder;
    }
}
~~~

This helps when defaults require simple computation or normalization. However, keep logic in properties constructors simple—do not perform I/O or call Spring beans.

## 11. Validation with @Validated

Binding maps data into objects; **validation** checks whether that data satisfies application rules.

Boot 3 example with a record:

~~~java
package com.example.catalog.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        @NotBlank String senderName,
        @Min(1) int retryCount) {
}
~~~

When the bean is bound and appropriate validation is enabled, missing or constraint-violating values can fail context startup with configuration error details.

Typically the project needs a validation dependency, such as:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

In Boot 3, constraint annotations use the `jakarta.validation.*` namespace. In Boot 2.x based on Spring Framework 5 and older Bean Validation, they usually use `javax.validation.*`.

### 11.1. Nested validation

For nested configuration:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotBlank String baseUrl,
        @Valid Retry retry) {

    public record Retry(
            @Min(1) int maxAttempts) {
    }
}
~~~

`@Valid` cascades validation into the child object when it is present and a validator is available. If the nested property is mandatory, combine with `@NotNull` or an appropriate default; `@Valid` alone does not automatically reject `null`.

Do not use validation as a substitute for conversion. For example, a string that cannot convert to `Duration` fails during binding before validation constraints ever run.

## 12. Binding onto beans from third-party libraries

Some third-party classes lack `@ConfigurationProperties` and you cannot edit their source. If they have an appropriate constructor/factory and setters for properties, you can register them via `@Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.legacy-client")
    LegacyClientSettings legacyClientSettings() {
        return new LegacyClientSettings();
    }
}
~~~

Assume `LegacyClientSettings` has matching setters such as `setHost` and `setPort`. Boot binds values onto the object returned by the factory method.

This is **JavaBean/property binding**, not constructor binding, because the factory method already constructed the object.

Avoid trying to force constructor binding onto a class returned from `@Bean`:

~~~java
// Do not use @ConstructorBinding to ask the Binder to recreate an object
// already instantiated by a @Bean factory method.
@Bean
@ConfigurationProperties(prefix = "app.legacy-client")
LegacyClientSettings legacyClientSettings() {
    return new LegacyClientSettings();
}
~~~

If the third-party object is immutable and has no setters, bind into a record or properties class you control, then use those values to construct the immutable object inside the `@Bean` method.

~~~java
@ConfigurationProperties(prefix = "app.legacy-client")
public record LegacyClientProperties(String host, int port) {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(LegacyClientProperties.class)
class ClientConfiguration {

    @Bean
    LegacyClient legacyClient(LegacyClientProperties properties) {
        return new LegacyClient(properties.host(), properties.port());
    }
}
~~~

This cleanly separates **binding configuration data** from **constructing library instances**.

## 13. Relaxed binding and configuration sources

`@ConfigurationProperties` supports flexible property naming. For instance, the Java property `connectTimeout` can receive configuration from:

~~~properties
app.client.connect-timeout=5s
~~~

Or YAML:

~~~yaml
app:
  client:
    connect-timeout: 5s
~~~

With environment variables, follow Spring Boot's rule for converting canonical names to uppercase with underscores, such as:

~~~text
APP_CLIENT_CONNECTTIMEOUT=5s
~~~

In real environments, converting properties to environment variables follows specific rules for dots, dashes, and list indices; avoid guessing names from camelCase expressions if binding issues occur.

### 13.1. Property source precedence

If the same property exists in multiple sources (such as `application.yml`, environment variables, and command-line arguments), Spring Boot chooses the value based on the `PropertySource` precedence order for your version and launch setup.

You can inspect effective configuration via `Environment` or appropriate diagnostics. Avoid hard-coding a memorized precedence list when applications use config imports, profile files, or custom property sources.

### 13.2. Do not use @Value in place of a full properties group

`@Value` suits a few isolated expressions, but does not share the same relaxed binding model for a whole group of typed/nested properties as `@ConfigurationProperties`. With multiple related properties, a configuration class is easier to test, validate, and document.

### 13.3. Annotation processor for metadata

Projects can add `spring-boot-configuration-processor` to generate IDE completion metadata for configuration properties:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

The processor generates completion and metadata for property names and descriptions. It is **not required for runtime binding to work**. Without metadata, the application can still bind normally, though IDEs may offer fewer suggestions.

## 14. Common mistakes when migrating from Boot 2 to Boot 3

### 14.1. Wrong @ConstructorBinding import or placement

Boot 2.x:

~~~java
import org.springframework.boot.context.properties.ConstructorBinding;

@ConstructorBinding
@ConfigurationProperties(prefix = "app.report")
public class ReportProperties {
    // A constructor accepting the properties.
}
~~~

Boot 3.x:

~~~java
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.report")
public class ReportProperties {

    @ConstructorBinding
    public ReportProperties(String format) {
        // ...
    }
}
~~~

In Boot 3, if a class has only one parameterized constructor and no ambiguity, **removing the annotation altogether** usually works too. The Boot 3 snippet above merely demonstrates the annotation's new location; not every class needs it.

### 14.2. Forgetting to register the properties bean

~~~java
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(String format) {
}
~~~

Merely putting the annotation on the record does not guarantee the bean is registered. Add `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(ReportProperties.class)` on a Spring-processed configuration class.

### 14.3. Using @Component for immutable constructor binding

~~~java
@Component
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(String format) {
}
~~~

This routes the class through regular component bean creation rather than the constructor binding registration designed by Boot. Remove `@Component` and register the record via configuration-properties scan/enable.

### 14.4. Missing constructor parameter names

In regular Java classes, the Binder needs to know which property corresponds to each constructor parameter. When binding fails on an immutable class, check `-parameters` and compiler/plugin settings rather than merely renaming fields.

Records carry clearer canonical component metadata, yet still require a framework version that supports record binding.

### 14.5. Missing validation dependency

Having `@Validated` and constraint annotations does not guarantee validation runs if no compatible validator implementation is on the classpath. Check the validation starter, Javax/Jakarta namespace, and inspect the root cause during context startup.

### 14.6. Mistaking runtime config for mutable objects

Having setters does not mean the bean updates automatically when property files change. Spring Boot usually binds configuration during bean creation and does not watch and update all properties beans automatically. If an application needs runtime refresh, design a dedicated refresh/configuration mechanism addressing concurrency and state consistency.

## 15. Testing JavaBean, constructor, and record binding

You can use `ApplicationContextRunner` to test properties classes in a lightweight context:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class NotificationPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(NotificationProperties.class)
    static class TestConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsPropertiesFromEnvironment() {
        runner
                .withPropertyValues(
                        "app.notification.enabled=true",
                        "app.notification.sender-name=Catalog Service",
                        "app.notification.retry-count=4",
                        "app.notification.connect-timeout=2s"
                )
                .run(context -> {
                    NotificationProperties properties =
                            context.getBean(NotificationProperties.class);

                    assertThat(properties.enabled()).isTrue();
                    assertThat(properties.senderName())
                            .isEqualTo("Catalog Service");
                    assertThat(properties.retryCount()).isEqualTo(4);
                    assertThat(properties.connectTimeout())
                            .isEqualTo(java.time.Duration.ofSeconds(2));
                });
    }
}
~~~

This test assumes `NotificationProperties` is a **Boot 3 record** as in Section 7, since it uses accessors `enabled()` and `senderName()`. If testing a JavaBean, replace with `isEnabled()` and `getSenderName()` accordingly.

You can add tests for:

1. Full properties: all fields/record components bind accurately.
2. Missing properties: defaults apply as intended.
3. Invalid data types: binding reports clear failures.
4. Constraint violations: context rejects startup.
5. Nested objects: bind properly or become `null` when missing.
6. Beans created via `@Bean`: setter binding works for third-party library classes.
7. Boot upgrade: the same YAML file binds an equivalent data structure after updating annotations/namespaces.

Do not merely check that the constructor ran; verify that values from `Environment` were actually converted and stored in the properties object.

## 16. Distinguishing property binding from dependency injection

Consider two constructors:

~~~java
public NotificationService(NotificationProperties properties) {
    this.properties = properties;
}
~~~

and:

~~~java
public NotificationProperties(boolean enabled, int retryCount) {
    this.enabled = enabled;
    this.retryCount = retryCount;
}
~~~

The first constructor is **Spring constructor injection**: the container looks up the `NotificationProperties` bean and injects it into the service.

The second constructor, when the properties class is registered using the appropriate constructor-binding mechanism, is **Spring Boot Binder constructor binding**: the Binder reads configuration values such as `app.notification.enabled` and `app.notification.retry-count` and passes them into the constructor.

Both mechanisms work together in the same application while serving different roles. Constructor binding is not for injecting `DataSource`, `RestClient`, or service beans into a properties class. Keep `@ConfigurationProperties` classes as configuration data structures; inject business dependencies into services or configuration classes that use them.

~~~text
application.yml / ENV / command-line
                 |
                 v
          Spring Boot Binder
                 |
                 v
        NotificationProperties
                 |
            (Spring bean)
                 |
                 v
     constructor injection into
        NotificationService
                 |
                 v
          Business usage
~~~

## 17. When to choose which approach?

| Scenario | Approach to consider |
|---|---|
| Legacy Boot 2.x project with many existing mutable classes | JavaBean binding |
| Binding config into a library object with setters | `@Bean` + `@ConfigurationProperties` |
| Need immutable configuration in Boot 2.2–2.7 | Constructor binding per Boot 2 API |
| Need immutable class in Boot 3 | Single parameterized constructor; usually no annotation needed |
| Java 17+ project wanting concise properties classes | Record + configuration-properties scan/enable |
| Nested immutable configuration | Nested records/classes via constructor binding |
| Need clear defaults on constructor/record components | `@DefaultValue` or simple constructor logic |
| Need to catch missing/invalid config at startup | `@Validated` + Bean Validation |
| Config needing bean dependencies or opening connections | Bind properties separately, then construct functional beans in `@Configuration` |

**Design rule:** Choose a data style based on immutability requirements, version compatibility, and bean registration method. Do not pick an option purely for fewer lines of code if it obscures how binding or lifecycle behaves.

## 18. Principles to remember

- `@ConfigurationProperties` groups multiple properties into a strongly typed Java object.
- JavaBean binding typically uses mutable objects and setters; constructor binding constructs immutable objects from constructor parameters.
- Records suit immutable configuration and use canonical constructors.
- Boot 2.2–2.7 uses class-level `@ConstructorBinding` from `org.springframework.boot.context.properties` for traditional Java classes.
- Boot 3 normally infers a single parameterized constructor; when needed, the annotation is `org.springframework.boot.context.properties.bind.ConstructorBinding` **on the constructor**.
- Constructor-bound properties must be registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`; do not create beans via `@Component` or `@Bean` expecting the Binder to re-invoke the constructor.
- Setter binding remains useful for mutable JavaBeans and third-party library objects.
- Pay attention to defaults, nested nullability, validation, compiler metadata, and Java version baselines.
- In Boot 3, validation annotations belong to `jakarta.validation`; in Boot 2.x they typically belong to `javax.validation`.
- Properties objects are configuration data, not service locators or places for business execution.

Once you clearly understand **who creates the object** (Spring `BeanFactory` vs. Boot `Binder`), **whether it is populated via setters or constructor**, and **which version line you are using**, configuration binding becomes predictable, testable, and easy to maintain. New Spring Boot 3 applications usually prefer records or immutable classes for read-only configuration; applications upgrading from Boot 2 should carefully migrate `@ConstructorBinding`, bean registration, and validation namespaces to avoid startup issues.
