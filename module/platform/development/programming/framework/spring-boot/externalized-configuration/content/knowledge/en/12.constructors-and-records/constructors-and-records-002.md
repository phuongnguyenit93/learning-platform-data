# Inferring Constructor Binding for a Single Eligible Constructor in Spring Boot

## 1. Goal: Creating Immutable Configuration Objects Without Setters

Spring Boot supports **Externalized Configuration** to read properties from `application.yml`, `application.properties`, environment variables, Java system properties, command-line arguments, and other sources. When a group of properties shares a prefix, we commonly map them to a Java type annotated with `@ConfigurationProperties`.

There are two familiar binding approaches:

- **JavaBean binding**: Spring creates the object and then invokes setters to populate properties.
- **Constructor binding**: Spring reads and converts configuration values, then passes them into a constructor to create a complete object.

JavaBean binding example:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private String baseUrl;
    private int maxRetries;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

This works for mutable properties, but the object exposes public setters and can be modified after creation.

With constructor binding, we can use `final` fields and omit setters:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;
    private final int maxRetries;

    public ClientProperties(String baseUrl, int maxRetries) {
        this.baseUrl = baseUrl;
        this.maxRetries = maxRetries;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

In **Spring Boot 3.x**, when a `@ConfigurationProperties` type is registered via a mechanism that supports constructor binding and **has exactly one suitable parameterized constructor**, Spring Boot can **infer that constructor for binding configuration**, without requiring `@ConstructorBinding`.

This is the focus of this lesson: **when a constructor is inferred, when it must be specified explicitly, and why bean registration affects the binding mechanism**.

## 2. What Does "Inferring Constructor Binding" Actually Mean?

Suppose `application.yml` contains:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
    max-retries: 4
~~~

The corresponding flat properties:

~~~properties
app.client.base-url=https://api.example.org
app.client.max-retries=4
~~~

With the `ClientProperties` class above, Spring Boot conceptually performs:

~~~text
app.client.base-url
          │
          └────► constructor parameter baseUrl (String)

app.client.max-retries
          │
          └────► constructor parameter maxRetries (int)

                   ▼
     new ClientProperties(
         "https://api.example.org",
         4
     )
                   ▼
        ClientProperties Bean
~~~

Spring Boot does not need setters to populate data after the object is created. It inspects constructor parameter names, looks up the matching configuration keys under the `app.client` prefix, converts values to target types, and invokes the constructor.

Distinguish between:

1. **Constructor injection** by the Spring container: passes **dependent beans** into a constructor, such as `DataSource` or `PaymentService`.
2. **Constructor binding** for `@ConfigurationProperties`: passes **configuration property values** into a constructor, such as `String baseUrl`, `int maxRetries`, or `Duration timeout`.

Both use Java constructors, but **their parameter sources and initialization workflows differ**. Do not confuse having a single constructor with Spring looking up a `String` bean or an `int` bean to inject into an immutable configuration object.

## 3. Conditions for Inferring a Single Parameterized Constructor

With Spring Boot 3.x, the most common case is:

~~~java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    private final String baseUrl;
    private final int maxRetries;

    public ClientProperties(String baseUrl, int maxRetries) {
        this.baseUrl = baseUrl;
        this.maxRetries = maxRetries;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

If this is **the class's only constructor**, has parameters, and is not marked for another injection mechanism, Spring Boot can choose it for constructor binding. You **do not need** to write:

~~~java
@ConstructorBinding
public ClientProperties(String baseUrl, int maxRetries) { ... }
~~~

Accompanying conditions to remember:

- The type must be annotated with `@ConfigurationProperties` and an appropriate prefix.
- The bean must be registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, rather than relying on a plain `@Component` if constructor binding is desired.
- Constructor parameter names must be recognizable by Spring Boot to map property names.
- Values must be convertible to the corresponding parameter types.
- If there are **multiple constructors**, the "only one so auto-select" rule no longer suffices; `@ConstructorBinding` may be needed to specify which constructor to use.
- If the constructor is annotated with `@Autowired`, that signals using the constructor for dependency injection instead of inferring it for constructor binding.

The accurate statement is: **Spring Boot infers an eligible parameterized constructor in the context of creating a `@ConfigurationProperties` bean that supports constructor binding**. Not every Java class with one constructor automatically becomes a configuration object.

## 4. Registering the Bean Properly: `@ConfigurationPropertiesScan`

Putting an annotation on a class does not necessarily turn that class into a Spring bean. With constructor binding, a direct registration approach is scanning `@ConfigurationProperties` types.

Example project structure:

~~~text
src/main/java/com/example/catalog/
  CatalogApplication.java
  config/
    ClientProperties.java
  service/
    CatalogClient.java

src/main/resources/
  application.yml
~~~

`ClientProperties.java`:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;
    private final Duration timeout;
    private final int maxRetries;

    public ClientProperties(
            String baseUrl,
            Duration timeout,
            int maxRetries) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
        this.maxRetries = maxRetries;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

`application.yml`:

~~~yaml
app:
  client:
    base-url: "https://catalog.example.org"
    timeout: 5s
    max-retries: 3
~~~

Application class:

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

Spring Boot locates `@ConfigurationProperties` classes within the scan scope, registers them, and uses the Binder to construct parameter values for the constructor.

A service using the bean:

~~~java
package com.example.catalog.service;

import com.example.catalog.config.ClientProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogClient {
    private final ClientProperties properties;

    public CatalogClient(ClientProperties properties) {
        this.properties = properties;
    }

    public String endpointDescription() {
        return properties.getBaseUrl()
                + " (timeout=" + properties.getTimeout() + ")";
    }
}
~~~

In `CatalogClient`, Spring performs **constructor injection of the `ClientProperties` bean** created earlier. Inside `ClientProperties` creation, the Binder performs **constructor binding from configuration values**.

The two mechanisms operate sequentially, but they must not be conflated.

## 5. Alternative Registration: `@EnableConfigurationProperties`

If you do not want to scan an entire package or want to explicitly choose classes to register, you can use:

~~~java
import com.example.catalog.config.ClientProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {
}
~~~

Or place it directly on the application class:

~~~java
@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

For the `ClientProperties` class with a single parameterized constructor, this registration method still works for constructor binding.

Comparison:

| Registration Approach | Characteristics |
| --- | --- |
| `@ConfigurationPropertiesScan` | Finds and registers `@ConfigurationProperties` types within scanned packages |
| `@EnableConfigurationProperties(MyProperties.class)` | Explicitly registers the specified configuration type |
| `@Component` on the configuration class | Registers a regular bean; **not suitable for immutable constructor binding** when relying on a constructor receiving configuration values |
| `@Bean` returning a configuration object | A bean created by a factory method; typically uses JavaBean binding after creation, not constructor binding selected directly by the Binder |

If a class already has `@Component`, do not assume `@ConfigurationPropertiesScan` will create another separate bean for it. The scanner has rules that skip types already marked as regular components. For constructor binding designs, omit `@Component` and register via one of the first two approaches.

## 6. Why Are `@Component` and Constructor Binding Easily Confused?

Suppose you write:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;

    public ClientProperties(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getBaseUrl() {
        return baseUrl;
    }
}
~~~

This is a common source of confusion. Because the class is annotated with `@Component`, Spring may instantiate the bean through the **normal container mechanism** and treat `String baseUrl` as a dependency to inject via constructor. However, a `String` from a YAML file does not automatically become a `String` bean for constructor injection to find.

The result can be a bean creation failure due to a missing dependency or unintended bean instantiation.

The proper approach for constructor binding:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;

    public ClientProperties(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getBaseUrl() {
        return baseUrl;
    }
}
~~~

Register it with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(ClientProperties.class)`.

Conversely, `@Component` can still be combined with `@ConfigurationProperties` using **JavaBean binding**, provided the bean has a no-args constructor or valid instantiation mechanism and the properties have suitable setters:

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class MutableClientProperties {
    private String baseUrl;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }
}
~~~

In short, **`@Component` is not forbidden with every `@ConfigurationProperties`**; the issue is that constructor binding is not applied to beans created through regular bean creation mechanisms like `@Component`, `@Bean`, or `@Import`.

## 7. What About a Class with a Single No-Args Constructor?

A class with only a no-args constructor is not a case of "having a single parameterized constructor inferred for binding."

Example:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private String baseUrl;
    private int maxRetries;

    public ClientProperties() {
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Spring Boot can instantiate the object using the no-args constructor and then call setters. This is **JavaBean binding**.

Comparison table:

| Class Design | Typical Binding Direction |
| --- | --- |
| One eligible parameterized constructor, no setters | Implicit constructor binding |
| One no-args constructor with setters | JavaBean binding |
| Multiple parameterized constructors | Need to specify constructor binding with `@ConstructorBinding` when constructor binding is desired |
| Constructor with `@Autowired` | Directed toward dependency injection |
| Record with eligible canonical constructor | Constructor binding is typically inferred |

Do not deduce that "having exactly one constructor means Spring Boot will bind via constructor" while ignoring whether that constructor has parameters, how the bean is registered, and whether any annotation requests a different mechanism.

## 8. When a Class Has Multiple Constructors: Explicit Selection Is Needed

Consider an immutable class with two constructors:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;
    private final int maxRetries;

    public ClientProperties(String baseUrl, int maxRetries) {
        this.baseUrl = baseUrl;
        this.maxRetries = maxRetries;
    }

    public ClientProperties(String baseUrl) {
        this(baseUrl, 3);
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

There is no longer a single constructor to infer. If you want the Binder to use the constructor accepting both `baseUrl` and `maxRetries`, in Spring Boot 3.x you can annotate **that specific constructor**:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;
    private final int maxRetries;

    @ConstructorBinding
    public ClientProperties(String baseUrl, int maxRetries) {
        this.baseUrl = baseUrl;
        this.maxRetries = maxRetries;
    }

    public ClientProperties(String baseUrl) {
        this(baseUrl, 3);
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

Here, `@ConstructorBinding` is not used to "enable" binding on every constructor. It **specifies which constructor** the Binder uses when multiple choices exist.

**Version note:** In Spring Boot 3.x, the `@ConstructorBinding` annotation resides in the `org.springframework.boot.context.properties.bind` package and is placed on the **constructor**. When reading Spring Boot 2.x examples, you may see a different syntax or package, or even the annotation placed on the **class**. Do not copy imports or annotation placements verbatim from older versions into a new project without checking the API of the version in use.

If the class has only one suitable parameterized constructor, adding `@ConstructorBinding` is usually unnecessary in Spring Boot 3.x.

## 9. A Constructor with `@Autowired`: A Different Intent

The `@Autowired` annotation tells the Spring container that the constructor should be used for **dependency injection**.

Regular bean example:

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

This is constructor injection of `OrderRepository`, not constructor binding of YAML properties.

If a class has a constructor annotated with `@Autowired`, Spring Boot should not infer that constructor as the constructor binding for `@ConfigurationProperties` under the single-parameterized-constructor rule.

A confusing case:

~~~java
@ConfigurationProperties(prefix = "app.service")
public class ServiceProperties {
    private final SomeDependency dependency;

    @Autowired
    public ServiceProperties(SomeDependency dependency) {
        this.dependency = dependency;
    }
}
~~~

This example does not describe a pure configuration object. It mixes a bean dependency into a configuration value class.

A clearer practice is:

- Keep `@ConfigurationProperties` holding only **configuration data**.
- Keep `@Service`/`@Component` holding **logic and dependencies**.
- Inject the configuration bean into the service via a regular constructor.

Example:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;
    private final ClientProperties properties;

    public OrderService(
            OrderRepository repository,
            ClientProperties properties) {
        this.repository = repository;
        this.properties = properties;
    }
}
~~~

Separating the two responsibilities helps Spring know which parameters come from the Binder and which come from the BeanFactory.

## 10. Java Records: The Natural Case for Constructor Binding

Since Java 16, `record` provides a concise syntax to describe data objects that are immutable at the field-reference level.

Same configuration:

~~~yaml
app:
  client:
    base-url: "https://catalog.example.org"
    timeout: 5s
    max-retries: 3
~~~

Can be declared as:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Duration timeout,
        int maxRetries
) {}
~~~

A record has a canonical constructor matching its components. For a record that only has the required constructor, Spring Boot can use **implicit constructor binding** without `@ConstructorBinding`.

Differences from regular Java classes:

- The constructor and accessors are generated from the record structure.
- No need to manually write three `private final` fields.
- No need to write JavaBean-style getters; the record's accessors are `baseUrl()`, `timeout()`, and `maxRetries()`.
- Java records provide `equals`, `hashCode`, and `toString` based on their components.
- The Binder maps by component/constructor parameter names instead of requiring setters.

A bean using the record:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ClientService {
    private final ClientProperties properties;

    public ClientService(ClientProperties properties) {
        this.properties = properties;
    }

    public int configuredRetries() {
        return properties.maxRetries();
    }
}
~~~

This record form is well suited when the goal is to **read configuration data and keep it stable inside an object**.

Keep in mind that a record's immutability is **shallow immutability**. If a component is a mutable `List` or `Map`, the record does not automatically turn that collection into a deeply immutable one. When you need absolute assurance that no one can mutate the collection, make a defensive copy in the canonical or compact constructor.

## 11. What About a Record with Additional Constructors?

A Java record can declare additional constructors alongside its canonical constructor. Example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {

    public ClientProperties(String baseUrl) {
        this(baseUrl, Duration.ofSeconds(5));
    }
}
~~~

Now there are multiple constructors. If the Spring Boot version needs explicit guidance to choose the binding constructor, you can declare the canonical constructor explicitly and annotate it with `@ConstructorBinding`:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {

    @ConstructorBinding
    public ClientProperties(String baseUrl, Duration timeout) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }

    public ClientProperties(String baseUrl) {
        this(baseUrl, Duration.ofSeconds(5));
    }
}
~~~

Explicitly declaring the canonical constructor lets you place the annotation right where the Binder looks. When an overload is not needed, the clearest approach is still keeping **one canonical constructor** and using `@DefaultValue` to express defaults at the binding point.

Do not add an auxiliary constructor just to supply defaults if the sole purpose is providing a default value for a configuration parameter.

## 12. Defaults with Constructor Binding: `@DefaultValue`

When binding via a constructor, fields in an immutable object usually have no setters and are assigned once. Spring Boot can use `@DefaultValue` on parameters to provide fallback values when the corresponding property is absent.

Example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("3") int maxRetries,
        @DefaultValue("false") boolean debugEnabled
) {}
~~~

YAML only needs to declare the URL:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
~~~

When binding succeeds:

~~~text
baseUrl       → https://api.example.org
timeout       → PT5S (Duration = 5 seconds)
maxRetries    → 3
debugEnabled  → false
~~~

Distinguish `@DefaultValue` from property placeholders:

~~~yaml
app:
  client:
    timeout: "${CLIENT_TIMEOUT:5s}"
~~~

A placeholder describes a **fallback value when resolving a configuration reference** inside a file; `@DefaultValue("5s")` describes a **fallback value for a constructor parameter during binding**. Both can serve similar needs, but they operate at two different layers.

When an invalid value is supplied, such as `timeout=bad-duration`, a default of `5s` is not an error-recovery mechanism for bad data. The Binder can fail during type conversion.

## 13. Constructor Binding with Nested Objects

A configuration class can contain multiple subgroups. Example:

~~~yaml
shop:
  name: "Demo Shop"
  checkout:
    timeout: 8s
    retries: 2
  shipping:
    provider: fast
    tracking-enabled: true
~~~

This can be modeled with nested records:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop")
public record ShopProperties(
        String name,
        Checkout checkout,
        Shipping shipping
) {
    public record Checkout(Duration timeout, int retries) {}

    public record Shipping(
            String provider,
            boolean trackingEnabled
    ) {}
}
~~~

Spring Boot can bind:

~~~text
shop.name                     → ShopProperties.name()
shop.checkout.timeout         → ShopProperties.checkout().timeout()
shop.checkout.retries         → ShopProperties.checkout().retries()
shop.shipping.provider        → ShopProperties.shipping().provider()
shop.shipping.tracking-enabled → ShopProperties.shipping().trackingEnabled()
~~~

Each nested record has a canonical constructor to receive data. No setters are needed to populate values on an existing object.

If the `shipping` group has no properties at all, depending on the declaration and binding setup, `shipping` may be `null` rather than an object constructed with empty/default values. If the application requires the subgroup object to always be present, you can use an empty `@DefaultValue` on the subgroup parameter and suitable defaults on its inner components:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "shop")
public record ShopProperties(
        String name,
        @DefaultValue Checkout checkout
) {
    public record Checkout(
            @DefaultValue("8s") Duration timeout,
            @DefaultValue("2") int retries
    ) {}
}
~~~

An empty `@DefaultValue` on the subgroup tells the Binder to create the nested object even when no properties exist for that group, as long as its inner parameters can be bound or have appropriate values.

Do not assume every nested object is automatically non-null just because the parameter type is declared.

## 14. Constructor Binding with List and Map

Configuration data often contains lists or maps:

~~~yaml
app:
  clients:
    - name: primary
      url: "https://primary.example.org"
      timeout: 3s
    - name: backup
      url: "https://backup.example.org"
      timeout: 7s
  labels:
    region: asia
    tier: gold
~~~

Record type:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<Client> clients,
        Map<String, String> labels
) {
    public record Client(
            String name,
            String url,
            Duration timeout
    ) {}
}
~~~

Typical flat property names:

~~~properties
app.clients[0].name=primary
app.clients[0].url=https://primary.example.org
app.clients[0].timeout=3s
app.clients[1].name=backup
app.clients[1].url=https://backup.example.org
app.clients[1].timeout=7s
app.labels.region=asia
app.labels.tier=gold
~~~

In constructor binding, `List<Client>` and `Map<String, String>` parameters can be constructed from the matching property groups.

Distinguish between:

- **Collection binding**: the Binder knows how to build `List`/`Map` from key-naming structure.
- **Constructor selection**: determines which constructor is called to receive the `List`/`Map`.
- **Property source precedence**: determines which source supplies the final values.

If a list is redeclared in a higher-precedence profile or source, the binder typically **replaces the list** from the lower-precedence source instead of intuitively merging elements. This is a multi-source configuration rule, not a constructor inference bug.

For mutable collections, if true immutability is needed, consider defensive copying and appropriate rules inside the record or class.

## 15. Type Conversion: Constructor Parameters Are a Data Contract

Spring Boot provides conversion mechanisms to transform configuration values into appropriate Java types. Example:

~~~yaml
app:
  worker:
    threads: 8
    enabled: true
    timeout: 15s
    buffer-size: 4MB
~~~

Record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int threads,
        boolean enabled,
        Duration timeout,
        DataSize bufferSize
) {}
~~~

Value pairs:

| Property | Constructor Parameter Type | Value |
| --- | --- | --- |
| `threads=8` | `int` | `8` |
| `enabled=true` | `boolean` | `true` |
| `timeout=15s` | `Duration` | 15 seconds |
| `buffer-size=4MB` | `DataSize` | 4 megabytes in Spring's unit syntax |

Using `Duration` or `DataSize` is more expressive than storing `long timeoutMillis` or a unit-ambiguous `String bufferSize`.

With primitive types such as `int` and `boolean`, when a property is missing and has no default, Java/binding default rules can result in `0` or `false`. **Do not use a primitive type as a guarantee that required configuration was provided**.

If the requirement is "threads must be present and greater than 0", use validation and/or a target type that can detect missing values, rather than relying solely on constructor binding.

## 16. Constructor Parameter Names Must Be Preserved or Discoverable

The Binder needs to know that the `baseUrl` parameter corresponds to the `base-url` property, and `maxRetries` corresponds to `max-retries`. The Java compiler does not always preserve full parameter names of regular classes in bytecode without proper configuration.

For constructor binding on Java classes, compile with the option:

~~~text
-parameters
~~~

Maven configuration example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

For projects using Spring Boot's standard build setup, many related settings may already be configured; it is still important to understand the purpose of `-parameters` when encountering errors about missing constructor parameter names.

In Gradle, a general Java configuration:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ["-parameters"]
}
~~~

For Java records, record component names are recorded directly in record metadata; nevertheless, projects should still use compiler/build plugins suitable for their Spring Boot version.

**Possible symptom** when parameter-name metadata is missing: the Binder cannot determine the right property name to match a constructor parameter or reports an error related to parameter-name discovery. Do not try to fix this by adding setters if the original intent was keeping the object immutable; inspect compiler flags and registration instead.

## 17. Relaxed Binding: YAML Names and Constructor Parameter Names Can Differ in Formatting

Spring Boot supports relaxed binding between canonical property names and Java property names.

Example:

~~~yaml
app:
  http-client:
    base-url: "https://api.example.org"
    max-connections: 20
    read-timeout: 5s
~~~

Record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.http-client")
public record HttpClientProperties(
        String baseUrl,
        int maxConnections,
        Duration readTimeout
) {}
~~~

Comparison table:

| YAML Property Name | Flat Name | Java Parameter Name |
| --- | --- | --- |
| `base-url` | `app.http-client.base-url` | `baseUrl` |
| `max-connections` | `app.http-client.max-connections` | `maxConnections` |
| `read-timeout` | `app.http-client.read-timeout` | `readTimeout` |

The `app.http-client` prefix is declared in canonical kebab-case. You do not change Java components to hyphenated names; hyphens are not valid in Java identifiers.

When providing configuration via environment variables, standard conversion rules use:

~~~text
APP_HTTPCLIENT_BASEURL
APP_HTTPCLIENT_MAXCONNECTIONS
APP_HTTPCLIENT_READTIMEOUT
~~~

Do not confuse "Spring Boot infers the constructor" with "Spring Boot guesses any arbitrary key name." Constructor binding still depends on matching property names and values convertible to parameter types.

## 18. When Is Validation Needed?

A constructor can receive a business-invalid value even if conversion succeeds. Example:

~~~yaml
app:
  worker:
    threads: -3
    timeout: 0s
~~~

Both values can be converted to `int` and `Duration`, yet they are invalid for creating a worker pool.

Bean Validation can be added with `@Validated`:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @Min(1) int threads,
        @NotNull Duration timeout
) {}
~~~

The application needs a Bean Validation implementation dependency, such as `spring-boot-starter-validation` matching the Spring Boot version.

Note that `@NotNull` only checks for non-null; it **does not guarantee that timeout is greater than 0**. If that constraint is needed, add appropriate validation or check it inside a constructor/validator.

With nested objects:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull @Valid Client client
) {
    public record Client(
            @NotBlank String baseUrl
    ) {}
}
~~~

`@Valid` enables validation to descend into the nested object, while `@NotNull` requires that object to exist. Combined, they express a clearer contract than simply having a parameterized constructor.

**Constructor binding does not automatically validate every property.** If you want to fail fast on missing or invalid values, design validation accordingly.

## 19. About null, Optional, and Missing Parameters

When a constructor parameter has no property source value, the exact behavior depends on the target type, default annotations, and the binder. For a reference parameter without a default, the result can be `null`.

Example:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        String displayName
) {}
~~~

If only `base-url` is configured, do not assume `displayName` automatically receives an empty string. When a default is needed, use `@DefaultValue("Client")`. When required, use `@NotBlank` or equivalent validation.

Another pitfall is using `Optional<String>` directly inside `@ConfigurationProperties` classes. Spring Boot does not recommend `Optional` as a configuration property type; when absent, the Binder may supply `null` rather than `Optional.empty()` as expected.

More predictable practices:

- Use `@DefaultValue` for values with clear defaults.
- Use validation for required values.
- Use nullable reference types when absence is genuinely meaningful, and handle it intentionally.
- Do not rely on primitive types to distinguish missing configuration from `0`/`false`.

## 20. Lombok and Auto-Generated Constructors

A class might use Lombok to generate constructors, such as `@RequiredArgsConstructor` or `@AllArgsConstructor`. This can change the actual number of constructors present in bytecode.

Example:

~~~java
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Getter
@RequiredArgsConstructor
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final String baseUrl;
    private final int maxRetries;
}
~~~

Conceptually, Lombok generates a two-parameter constructor, which could be the sole eligible constructor for the Binder to infer. However, you must ensure **generated parameter names are preserved and recognized by Spring Boot**, and that annotation processors and build configurations work properly.

A common mistake is later adding another constructor or another Lombok annotation that generates a no-args constructor, turning "one constructor" into "multiple constructors" in a way that is not immediately obvious from reading the source without knowing Lombok's behavior.

For simple configuration DTOs, Java records are often easier to inspect because the parameter list and component names are part of the language syntax. For regular classes, an explicit constructor is also a clear choice when initialization logic is needed.

Do not add `@ConstructorBinding` merely to work around missing parameter-name metadata or improper bean registration.

## 21. Can a Constructor Contain Invariant Validation Logic?

Yes. One benefit of constructor binding is that the object is only created once parameters pass through the constructor, allowing invariant checks.

Example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private final int threads;
    private final Duration timeout;

    public WorkerProperties(int threads, Duration timeout) {
        if (threads < 1) {
            throw new IllegalArgumentException(
                    "app.worker.threads must be >= 1");
        }
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.worker.timeout must be positive");
        }
        this.threads = threads;
        this.timeout = timeout;
    }

    public int getThreads() {
        return threads;
    }

    public Duration getTimeout() {
        return timeout;
    }
}
~~~

If the configuration is invalid, the constructor can throw an exception and cause application startup to fail during bean creation. This fits simple conditions that are mandatory invariants of the object.

However:

- Do not make network calls or database queries inside a constructor just to bind configuration.
- Avoid side-effecting logic in constructors.
- With many data constraints, Bean Validation may produce clearer configuration error messages.
- Type conversion typically occurs **before the constructor is called**; if the `timeout` string cannot be converted to `Duration`, the constructor is not invoked.

Records can also use a compact constructor for checks:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int threads, Duration timeout) {

    public WorkerProperties {
        if (threads < 1) {
            throw new IllegalArgumentException("threads must be positive");
        }
        if (timeout == null || timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }
}
~~~

A compact constructor does not need assignment statements for record components; Java performs the assignments after the validation body finishes.

## 22. Constructor Binding and Profile-Specific Configuration

How Spring Boot **chooses a constructor** is independent of whether values come from a base file, a profile-specific file, or environment variables.

Suppose:

~~~yaml
# application.yml
app:
  client:
    base-url: "https://dev.example.org"
    timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    base-url: "https://api.example.org"
    timeout: 12s
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        java.time.Duration timeout
) {}
~~~

Run:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

If no higher-precedence source overrides them, the Binder receives final values `https://api.example.org` and `12s`. Then the record's constructor is invoked with those values.

If an environment variable supplies:

~~~bash
APP_CLIENT_TIMEOUT=3s
~~~

in the runtime environment, the final timeout can become `3s`, while the base URL still comes from the profile file.

**The constructor does not know which source a value came from.** It receives Java objects prepared by the Binder after resolving sources and converting types.

Similarly, if a configuration list from a higher-precedence profile replaces the default list, the constructor still receives the final resulting list rather than deciding the list-merging strategy.

## 23. Version Differences to Know

When looking up documentation on constructor binding, distinguish between Spring Boot versions:

### Spring Boot 2.2 through 2.x

Constructor binding was introduced in the Spring Boot 2.x line, and many older examples use `@ConstructorBinding` following the mechanics and annotation placement of that generation. Older 2.x releases commonly show placing the annotation at the class level or importing from a different package than Spring Boot 3.

Do not copy code directly from a Boot 2.3 guide into a Boot 3 project assuming imports and annotation placement are completely compatible.

### Spring Boot 3.x

In common usage:

- An eligible single parameterized constructor of a `@ConfigurationProperties` class can be **inferred automatically**.
- A record with a suitable canonical constructor is also normally bound without an explicit annotation.
- If multiple constructors need disambiguation, use `org.springframework.boot.context.properties.bind.ConstructorBinding` on the chosen constructor.
- Types using constructor binding are registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
- For validation, projects use the Jakarta namespace, such as `jakarta.validation.constraints.NotBlank` instead of the older `javax.validation` package.

For newer versions, consult documentation matching **the exact dependency version in your application**. The core rule to learn is understanding that inference **depends on the number and type of constructors together with bean registration**, rather than memorizing a single annotation in isolation from version context.

## 24. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Immutable class has one constructor, but startup fails due to missing `String` bean | Class was registered with `@Component`, so the constructor was used for dependency injection | Remove `@Component`; use `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` |
| Placing `@ConstructorBinding` on the class causes an IDE target error | Using Spring Boot 2.x import or syntax in a 3.x project | Use the right package and place the annotation on the constructor when needed |
| Class has two constructors and Binder does not know which to pick | No longer a single eligible constructor to infer | Specify the intended constructor with `@ConstructorBinding` |
| Using a record, but Spring does not create the configuration bean | Record not registered with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` | Add a registration mechanism |
| `base-url` property does not bind to `baseUrl` | Parameter name, metadata, or configuration mismatch | Check prefix, relaxed binding, and `-parameters` |
| `Duration` parameter fails to bind | Value has an invalid format | Fix duration string/unit and verify conversion |
| A required field ends up `null` | No value supplied and no validation declared | Add validation or a meaningful default |
| Environment variable changes, yet bean keeps old value | Object was created at startup | Restart or design a dedicated refresh mechanism |
| Configuration field is `final`, yet JavaBean binding fails to set it | Bean instantiated via no-args constructor without setters | Choose constructor binding and register properly |
| Placing `@Autowired` on configuration constructor | Accidentally requests dependency injection instead of constructor binding | Separate business beans from configuration data; remove unnecessary annotation |
| Configuration list loses elements when a profile is active | List from higher-precedence source replaces the old list | Declare the complete list in the overriding source |
| `Optional` receives null | `Optional` is not a recommended property type for binding | Use defaults/validation or an appropriate type |

When troubleshooting, check in order: **how the bean is registered → number of constructors → constructor-selection annotation → parameter names → prefix and property sources → conversion → validation**. This usually separates bean-creation issues from configuration-data issues.

## 25. Practice Exercises

### Exercise 1 — Single Constructor

Given:

~~~java
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int maxEntries;

    public CacheProperties(int maxEntries) {
        this.maxEntries = maxEntries;
    }

    public int getMaxEntries() {
        return maxEntries;
    }
}
~~~

Configuration:

~~~yaml
app:
  cache:
    max-entries: 200
~~~

The application has `@ConfigurationPropertiesScan` properly configured. Is `@ConstructorBinding` mandatory on the constructor?

**Answer:** In Spring Boot 3.x in this context, normally **no**. The class has a single eligible parameterized constructor for the Binder to infer automatically. `maxEntries` will be `200` if binding succeeds with no other overrides.

### Exercise 2 — Two Constructors

Given:

~~~java
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int maxEntries;

    public CacheProperties() {
        this(100);
    }

    public CacheProperties(int maxEntries) {
        this.maxEntries = maxEntries;
    }
}
~~~

If you want the Binder to use the parameterized constructor, what must you do?

**Answer:** Because the class has multiple constructors, annotate `CacheProperties(int maxEntries)` with `@ConstructorBinding` from the Spring Boot 3.x package. Keeping the no-args constructor for JavaBean binding would require appropriate mutable fields and setters; the class above has a `final` field, so it does not fit setter binding.

### Exercise 3 — Component or Configuration Properties Scan?

Given:

~~~java
@Component
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int maxEntries;

    public CacheProperties(int maxEntries) {
        this.maxEntries = maxEntries;
    }
}
~~~

Why might you encounter a missing `int` dependency error?

**Answer:** `@Component` causes the bean to be created through the standard container mechanism; the constructor parameter can be treated as a dependency to autowire rather than supplied by the Binder from `app.cache.max-entries`. For constructor binding, remove `@Component` and register via `@ConfigurationProperties` scanning or enabling.

### Exercise 4 — Record and Defaults

Given:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") int threads,
        @DefaultValue("10s") java.time.Duration timeout
) {}
~~~

There are no keys under `app.worker`. What two values can be received?

**Answer:** `threads=4` and `timeout=10 seconds`, when the class is registered and the binder has suitable conversion.

### Exercise 5 — Nested Object

Given YAML:

~~~yaml
app:
  gateway:
    endpoint: "https://gateway.example.org"
    retry:
      max-attempts: 5
~~~

Write a record that can be bound via constructor with a nested `Retry` record.

**Suggested answer:**

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        String endpoint,
        Retry retry
) {
    public record Retry(int maxAttempts) {}
}
~~~

### Exercise 6 — Distinguishing Two Constructors

A service has constructor `OrderService(OrderRepository repo, ClientProperties config)`, while `ClientProperties` has constructor `ClientProperties(String baseUrl, int maxRetries)`. Which constructor does the Binder invoke?

**Answer:** The Binder uses the `ClientProperties` constructor to create the configuration bean if the type is registered properly. Afterward, the Spring container uses the `OrderService` constructor to inject `OrderRepository` and the `ClientProperties` bean. They are not the same mechanism.

### Exercise 7 — Validation

Given `@ConfigurationProperties` with a constructor taking `int threads`. The YAML file has `threads=-2`. Does constructor binding automatically reject the configuration?

**Answer:** Not by default merely from using constructor binding. `-2` is still a valid integer by type. You need `@Min(1)` with validation, or invariant-checking logic in the constructor, to reject values that violate business rules.

## 26. Takeaways

- In Spring Boot 3.x, a `@ConfigurationProperties` class with **a single eligible parameterized constructor** is normally **implicitly constructor-bound**, without requiring `@ConstructorBinding`.
- **Constructor count is only part of the condition.** You must consider how the bean is registered, constructor annotations, parameter names, and conversion capability.
- `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` are the two proper registration approaches for constructor binding.
- `@Component`/`@Bean` create beans via normal Spring mechanisms; do not mix immutable constructor binding with dependency constructor injection.
- If there are **multiple constructors**, specify the binding constructor using `@ConstructorBinding` (Spring Boot 3.x: `org.springframework.boot.context.properties.bind` package).
- A **record** with a suitable canonical constructor is a concise choice for immutable configuration; no setters are required.
- Use **`@DefaultValue`** to declare default values on constructor parameters, and **Bean Validation** to enforce required values or business limits.
- Nested groups, lists, maps, and types like `Duration`/`DataSize` can be constructed and converted by the Binder before invoking the constructor.
- Compiler metadata such as **`-parameters`** must be kept in mind for constructor binding on regular Java classes.
- Always consult documentation matching **your project's Spring Boot version**, because the placement and usage of `@ConstructorBinding` vary across version lines.

## References

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Constructor Binding](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot API — ConstructorBinding](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/ConstructorBinding.html)
