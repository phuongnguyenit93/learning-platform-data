# Using `@ConfigurationProperties` on `@Bean` Methods for Third-Party Libraries in Spring Boot

## 1. The Problem to Solve

`@ConfigurationProperties` is Spring Boot's mechanism for mapping external configuration onto Java objects. In basic examples, we write our own `AppProperties` class, place `@ConfigurationProperties(prefix = "app")` on it, and register it with Spring.

However, real-world projects often use **objects provided by external libraries**, such as:

- `HikariDataSource` or `HikariConfig` from HikariCP for database connection pooling.
- A pool, cache, or HTTP client configuration bean with setters defined by the library author.
- An infrastructure component whose source code the project **does not own**, so annotations cannot simply be added to its class.

The question is: how do we pull values from `application.yml`, environment variables, or Spring Boot configuration sources and **bind them directly onto a third-party bean**, without modifying library source code and without writing dozens of manual setter calls?

Spring Boot supports placing `@ConfigurationProperties` **on a `@Bean` method**:

~~~java
@Configuration(proxyBeanMethods = false)
public class ThirdPartyConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.datasource.reporting")
    public HikariDataSource reportingDataSource() {
        return new HikariDataSource();
    }
}
~~~

Spring instantiates the object via the factory method, and the `@ConfigurationProperties` infrastructure assigns properties under the matching prefix onto that instance's JavaBean properties.

> **Core idea:** for third-party library beans, the annotation goes at the **bean registration point**, not on the library class itself. This pattern fits **JavaBean/setter binding on an already-created object**, rather than constructor binding where Spring Boot constructs an immutable object itself.

## 2. Two Places to Put `@ConfigurationProperties`

There are two patterns to distinguish clearly.

### 2.1. On an Application-Owned Class

For example, the application defines its own class:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.remote")
public class RemoteProperties {
    private String baseUrl;
    private Duration timeout = Duration.ofSeconds(3);

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Register it with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(RemoteProperties.class)`, then inject `RemoteProperties` into business beans. This makes sense when you control the structure and want to declare types, defaults, and validation directly on the class.

### 2.2. On a `@Bean` Method When the Class Belongs to Another Library

When the class comes from an external JAR, you cannot write:

~~~java
// Cannot edit HikariCP source code to add arbitrary annotations.
@ConfigurationProperties(prefix = "app.datasource.reporting")
public class HikariDataSource { /* ... */ }
~~~

Instead:

~~~java
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportingDataSourceConfiguration {

    @Bean("reportingDataSource")
    @ConfigurationProperties(prefix = "app.datasource.reporting")
    public HikariDataSource reportingDataSource() {
        return new HikariDataSource();
    }
}
~~~

The `@Bean` method is where the application registers the object into the Spring container. Placing `@ConfigurationProperties` on that method instructs Spring Boot to bind matching properties onto the returned bean.

Having the `@Configuration` class inside the application's component scan (or explicitly imported/registered) is sufficient for Spring to pick up the `@Bean` method. **You do not need `@ConfigurationPropertiesScan` just to recognize the annotation on a `@Bean` method.** Annotation scanning primarily discovers application-declared `@ConfigurationProperties` *types*.

## 3. Binding Mechanics at Bean Creation Time

General model:

~~~text
application.yml / application.properties
OS environment / JVM -D / command-line args
                 |
                 v
             Environment
       (values by precedence)
                 |
                 v
        @Configuration + @Bean
                 |
                 v
        reportingDataSource()
           new HikariDataSource()
                 |
                 v
    @ConfigurationProperties binding
  app.datasource.reporting.jdbc-url
  app.datasource.reporting.username
  app.datasource.reporting.maximum-pool-size
                 |
                 v
   setters on HikariDataSource
                 |
                 v
   configured bean injected / used
~~~

Key points to understand:

1. The `@Bean` method **creates the object first**. Here, that is `new HikariDataSource()`.
2. Spring Boot binds properties matching the prefix onto the object after the factory method returns, during bean post-processing.
3. The bound bean is exposed for dependency injection and consumed by dependent beans.
4. Spring Boot relies on **JavaBean properties** (typically getters/setters) and the conversion service to map data to Java types.
5. Binding can only affect properties that the external object **actually supports configuring**. The annotation does not generate setters or alter the library's API.

Because binding runs after the factory method creates the object, **do not execute operations requiring complete configuration inside the factory method itself**. For instance, calling `getConnection()` on the datasource before returning it will use values that have not yet been bound.

## 4. Practical Example: Configuring HikariCP from `application.yml`

HikariCP is a widely used connection pool in the Spring Boot ecosystem. It provides `HikariDataSource` with JavaBean properties like `jdbcUrl`, `username`, `password`, `maximumPoolSize`, `minimumIdle`, and `connectionTimeout`.

### 4.1. Dependencies

In a Spring Boot 3.x Maven application, the JDBC starter already brings in HikariCP by default:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

The second entry is an example PostgreSQL JDBC driver. Choose the actual driver matching your database. When the project already includes the starter or HikariCP dependency, do not add duplicates.

### 4.2. External Configuration

`src/main/resources/application.yml`:

~~~yaml
app:
  datasource:
    reporting:
      jdbc-url: jdbc:postgresql://localhost:5432/reporting
      username: report_user
      password: "${REPORTING_DB_PASSWORD}"
      maximum-pool-size: 8
      minimum-idle: 2
      connection-timeout: 30000
      pool-name: reporting-pool
~~~

Properties under `app.datasource.reporting` are applied to `HikariDataSource` according to matching property names. `connection-timeout` in this example uses an integer representing **milliseconds**, matching `HikariConfig#setConnectionTimeout(long)`.

The `REPORTING_DB_PASSWORD` environment variable must be provided via a proper secret management mechanism. Never commit real passwords to a repository or print passwords to logs.

### 4.3. Registering the Third-Party Bean

~~~java
package com.example.config;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportingDataSourceConfiguration {

    @Bean(name = "reportingDataSource", destroyMethod = "close")
    @ConfigurationProperties(prefix = "app.datasource.reporting")
    public HikariDataSource reportingDataSource() {
        return new HikariDataSource();
    }
}
~~~

Explanation:

- `@Configuration`: declares Spring beans.
- `proxyBeanMethods = false`: appropriate when factory methods do not directly invoke other `@Bean` methods; unrelated to binding itself.
- `@Bean(name = "reportingDataSource")`: registers a bean with an explicit name, helpful when the application has multiple datasources.
- `destroyMethod = "close"`: ensures the datasource/pool closes when the bean is destroyed. Spring can often infer an appropriate destroy method; writing it explicitly makes the lifecycle clear.
- `@ConfigurationProperties(prefix = "app.datasource.reporting")`: binds properties sharing that prefix onto the returned instance.
- `new HikariDataSource()`: uses the no-arg constructor; setters are called afterwards by the binder.

If a library bean lacks a no-arg constructor, you can invoke a suitable constructor **inside the factory method**, but constructor parameters **are not automatically supplied by the binder** merely because `@ConfigurationProperties` is on the method. When constructor arguments must come from configuration, use the intermediate properties object pattern shown later.

### 4.4. Consuming the Bean from Another Service

~~~java
package com.example.service;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class ReportingService {
    private final DataSource reportingDataSource;

    public ReportingService(
            @Qualifier("reportingDataSource") DataSource reportingDataSource) {
        this.reportingDataSource = reportingDataSource;
    }

    // Use reportingDataSource to query reporting data.
}
~~~

You can inject via the `javax.sql.DataSource` interface because `HikariDataSource` implements it. `@Qualifier` tells Spring which bean to select when multiple datasources exist.

**Integration note:** registering a custom `DataSource` bean can cause Spring Boot's DataSource auto-configuration to back off or change behavior. In multi-datasource applications, explicitly design the primary datasource, `@Qualifier`s, transaction managers, and JPA/JDBC integration. This example focuses on binding third-party beans, not a complete multi-datasource setup.

## 5. Mapping Table: YAML → JavaBean Setters

In the HikariCP example:

| YAML Key | JavaBean Property | Typical Setter |
| --- | --- | --- |
| `app.datasource.reporting.jdbc-url` | `jdbcUrl` | `setJdbcUrl(String)` |
| `app.datasource.reporting.username` | `username` | `setUsername(String)` |
| `app.datasource.reporting.password` | `password` | `setPassword(String)` |
| `app.datasource.reporting.maximum-pool-size` | `maximumPoolSize` | `setMaximumPoolSize(int)` |
| `app.datasource.reporting.minimum-idle` | `minimumIdle` | `setMinimumIdle(int)` |
| `app.datasource.reporting.connection-timeout` | `connectionTimeout` | `setConnectionTimeout(long)` |
| `app.datasource.reporting.pool-name` | `poolName` | `setPoolName(String)` |

Spring Boot supports **relaxed binding**, so `maximum-pool-size` in config matches Java property `maximumPoolSize`. Keys should use **lowercase kebab-case** in YAML/Properties for readability and consistency.

The annotation prefix must follow canonical syntax:

~~~java
@ConfigurationProperties(prefix = "app.datasource.reporting")
~~~

Do not write prefixes in uppercase or non-standard casing just because the library's Java properties use camelCase.

### 5.1. Watch Out for the Exact Library Property Name

A common mistake when configuring HikariCP:

~~~yaml
app:
  datasource:
    reporting:
      url: jdbc:postgresql://localhost:5432/reporting
~~~

`HikariDataSource` has property `jdbcUrl`, not a JavaBean property `url` for the binder to populate directly in this pattern. Use:

~~~yaml
app:
  datasource:
    reporting:
      jdbc-url: jdbc:postgresql://localhost:5432/reporting
~~~

This is the difference between **binding directly onto a vendor class** and **binding onto Spring Boot's own properties class** that performs translation or name mapping.

For example, `spring.datasource.url` is supported via Spring Boot's own auto-configuration/properties classes. That does not mean any custom `HikariDataSource` bean automatically recognizes `url` under a custom prefix.

## 6. Configuration Source Precedence Still Applies

`@ConfigurationProperties` does not define a new source ordering. It binds the **resolved values** from `Environment`.

YAML example:

~~~yaml
app:
  datasource:
    reporting:
      maximum-pool-size: 8
      minimum-idle: 2
~~~

Environment variable:

~~~bash
APP_DATASOURCE_REPORTING_MAXIMUMPOOLSIZE=12 java -jar app.jar
~~~

In standard env var format, dots become underscores, dashes inside field names are removed, and everything becomes uppercase.

Unless a higher-precedence property source overrides it, `maximumPoolSize` receives `12` from the env var while `minimumIdle` still gets `2` from YAML. Fields resolve per property, not by one "winning file" taking over everything.

Likewise, under Spring Boot defaults:

~~~bash
java -jar app.jar --app.datasource.reporting.maximum-pool-size=16
~~~

command-line arguments override matching values in files. If the application disables the command-line property source via `setAddCommandLineProperties(false)`, values from that channel no longer enter `Environment`.

Whether settings arrive from files, JVM system properties, or environment variables, `@ConfigurationProperties` on `@Bean` binds onto the **same object**.

## 7. Difference from Manually Calling `setXxx(...)`

You could configure a library object by reading `Environment` manually:

~~~java
@Bean
public HikariDataSource reportingDataSource(Environment environment) {
    HikariDataSource ds = new HikariDataSource();
    ds.setJdbcUrl(environment.getRequiredProperty(
            "app.datasource.reporting.jdbc-url"));
    ds.setUsername(environment.getRequiredProperty(
            "app.datasource.reporting.username"));
    ds.setMaximumPoolSize(environment.getProperty(
            "app.datasource.reporting.maximum-pool-size",
            Integer.class, 8));
    return ds;
}
~~~

This can work when custom logic is required. However, as the number of fields grows, it leads to:

- Repeating many string property keys in Java code.
- Repeating default and type-conversion handling manually.
- Easily forgetting to bind new fields when the library adds properties.
- Difficulty seeing the entire configuration group under one prefix.

For JavaBeans with matching setters, annotation-based binding is much shorter:

~~~java
@Bean
@ConfigurationProperties(prefix = "app.datasource.reporting")
HikariDataSource reportingDataSource() {
    return new HikariDataSource();
}
~~~

Yet shorter code **does not automatically ensure values are properly validated**. Binding does not replace application-required constraints, and properties without setters do not gain automatic support.

## 8. `@ConfigurationPropertiesScan` Is Not Needed for `@Bean` Methods

Comparison of registration forms:

| Case | Registration Mechanism | Role |
| --- | --- | --- |
| Custom `AppProperties` class with `@ConfigurationProperties` | `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(AppProperties.class)` | Registers the properties type in the Spring context |
| Third-party class created by `@Bean` | `@Configuration` + `@Bean` + `@ConfigurationProperties` on method | Binds properties directly onto the created bean |
| Properties type annotated with `@Component` | Component scanning + JavaBean binding if eligible | Standard bean creation; not dedicated constructor binding |

Minimal setup for Spring Boot to handle a library bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class VendorConfiguration {
    @Bean
    @ConfigurationProperties("third-party.client")
    VendorClientConfig vendorClientConfig() {
        return new VendorClientConfig();
    }
}
~~~

`VendorClientConfig` is an illustrative name for a library class with getters/setters. You do not need `@ConfigurationPropertiesScan` just because the annotation sits on `@Bean`.

Of course, `VendorConfiguration` itself must be registered by Spring. If placed outside component scan scope, import it via `@Import(VendorConfiguration.class)` or register it explicitly.

## 9. What Does JavaBean Binding Require from an External Object?

Not every library class works with this approach.

### 9.1. Suitable Case: Mutable JavaBean

Suppose a library provides:

~~~java
// Illustrative simulation of an external library API.
public class VendorClientConfig {
    private String endpoint;
    private int maxConnections = 5;
    private boolean enabled;

    public String getEndpoint() {
        return endpoint;
    }
    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getMaxConnections() {
        return maxConnections;
    }
    public void setMaxConnections(int maxConnections) {
        this.maxConnections = maxConnections;
    }

    public boolean isEnabled() {
        return enabled;
    }
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

When the library provides a structure like this:

~~~java
@Configuration(proxyBeanMethods = false)
public class VendorConfiguration {
    @Bean
    @ConfigurationProperties(prefix = "vendor.client")
    public VendorClientConfig vendorClientConfig() {
        return new VendorClientConfig();
    }
}
~~~

And YAML:

~~~yaml
vendor:
  client:
    endpoint: https://api.example.test
    max-connections: 20
    enabled: true
~~~

The binder invokes setters to assign `endpoint`, `maxConnections`, and `enabled`.

### 9.2. Unsuitable Case: Immutable Objects

Some libraries use immutable classes:

~~~java
// Illustrative example of an external API style.
public final class ImmutableVendorClient {
    private final String endpoint;
    private final int maxConnections;

    public ImmutableVendorClient(String endpoint, int maxConnections) {
        this.endpoint = endpoint;
        this.maxConnections = maxConnections;
    }

    // Getters only, no setters.
}
~~~

You cannot expect:

~~~java
@Bean
@ConfigurationProperties(prefix = "vendor.client")
public ImmutableVendorClient client() {
    return new ImmutableVendorClient("default", 5);
}
~~~

to mutate the two `final` fields merely via the annotation. **Constructor binding does not apply to beans created by regular `@Bean` methods.**

The proper solution is binding an **application-owned properties object**, then using it to call the library's constructor or builder:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "vendor.client")
public record VendorClientProperties(
        String endpoint,
        int maxConnections) {
}
~~~

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(VendorClientProperties.class)
public class VendorClientConfiguration {

    @Bean
    public ImmutableVendorClient vendorClient(VendorClientProperties properties) {
        return new ImmutableVendorClient(
                properties.endpoint(),
                properties.maxConnections());
    }
}
~~~

This model illustrates how to handle immutable classes; in a real project, replace `ImmutableVendorClient` with the library's actual constructor or builder.

**Rule of thumb:** if the library exposes JavaBean setters, you can bind directly on `@Bean`. If it only offers constructors or builders, bind onto an intermediate properties class and construct the vendor object explicitly.

## 10. Two-Step Pattern: Bind `HikariConfig`, Then Build `HikariDataSource`

When complete configuration is needed before component initialization, rather than binding directly onto the datasource, you can bind onto **HikariCP's config bean** and then instantiate the datasource.

~~~java
package com.example.config;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AnalyticsDataSourceConfiguration {

    @Bean("analyticsHikariConfig")
    @ConfigurationProperties(prefix = "app.datasource.analytics")
    public HikariConfig analyticsHikariConfig() {
        return new HikariConfig();
    }

    @Bean(name = "analyticsDataSource", destroyMethod = "close")
    public HikariDataSource analyticsDataSource(
            @Qualifier("analyticsHikariConfig") HikariConfig config) {
        return new HikariDataSource(config);
    }
}
~~~

YAML:

~~~yaml
app:
  datasource:
    analytics:
      jdbc-url: jdbc:postgresql://localhost:5432/analytics
      username: analytics_user
      password: "${ANALYTICS_DB_PASSWORD}"
      maximum-pool-size: 6
      pool-name: analytics-pool
~~~

Execution flow:

~~~text
Spring creates HikariConfig via @Bean
                |
                v
@ConfigurationProperties binds app.datasource.analytics.*
                |
                v
HikariConfig has jdbcUrl, username, pool size...
                |
                v
Spring creates analyticsDataSource(HikariConfig config)
                |
                v
new HikariDataSource(config)
                |
                v
injects configured datasource
~~~

The benefit of the two-step pattern is having a **fully bound config bean** ready to pass to the library component's constructor. It is especially useful when the constructor initializes resources that require accurate settings immediately at creation time.

HikariCP has its own validation constraints and pool startup timing; manage its lifecycle and actual connectivity according to application goals. Not every library has a separate `Config` class, so the two-step pattern is a strategy when the API supports it, not a universal rule.

## 11. Default Values and Configuration Precedence

When placing `@ConfigurationProperties` on `@Bean`, the binder normally sets only properties present in matching configuration data. Unbound fields keep default values established by the constructor or library.

Example:

~~~java
@Bean
@ConfigurationProperties("vendor.client")
VendorClientConfig vendorClientConfig() {
    VendorClientConfig config = new VendorClientConfig();
    config.setMaxConnections(5);
    return config;
}
~~~

If YAML only contains:

~~~yaml
vendor:
  client:
    endpoint: https://api.example.test
~~~

then `maxConnections` stays `5` as set in the factory method, while `endpoint` is populated from YAML by the binder.

However, if YAML has:

~~~yaml
vendor:
  client:
    max-connections: 20
~~~

the binder overrides the default `5` with `20`.

Keep in mind that **object-level defaults** differ from a default property in `Environment`. Calling a setter inside `new VendorClientConfig()` does not create a `vendor.client.max-connections` entry in `Environment`. This matters if code elsewhere calls `Environment.getProperty(...)` to check whether a setting was supplied.

For fields that are genuinely mandatory, do not rely on vague library defaults. Verify business requirements and deployment configuration explicitly.

## 12. Configuring via Environment Variables

With prefix:

~~~java
@ConfigurationProperties(prefix = "app.datasource.reporting")
~~~

and Java field `maximumPoolSize`, the canonical environment variable is:

~~~bash
APP_DATASOURCE_REPORTING_MAXIMUMPOOLSIZE=12
~~~

Illustrative Unix command:

~~~bash
APP_DATASOURCE_REPORTING_MAXIMUMPOOLSIZE=12 \
REPORTING_DB_PASSWORD=example-secret \
java -jar app.jar
~~~

In PowerShell:

~~~powershell
$env:APP_DATASOURCE_REPORTING_MAXIMUMPOOLSIZE = "12"
$env:REPORTING_DB_PASSWORD = "example-secret"
java -jar app.jar
~~~

Secret values here are illustrative examples only. In production, supply them via a secret manager, mounted file, or appropriate protection mechanism; never paste real credentials into shell history or logs.

Corresponding table:

| YAML Property | Canonical Environment Variable |
| --- | --- |
| `app.datasource.reporting.jdbc-url` | `APP_DATASOURCE_REPORTING_JDBCURL` |
| `app.datasource.reporting.maximum-pool-size` | `APP_DATASOURCE_REPORTING_MAXIMUMPOOLSIZE` |
| `app.datasource.reporting.minimum-idle` | `APP_DATASOURCE_REPORTING_MINIMUMIDLE` |
| `app.datasource.reporting.pool-name` | `APP_DATASOURCE_REPORTING_POOLNAME` |

Spring Boot supports **relaxed binding**: dashes in kebab-case field names are removed when converting to environment variable names, while dots between prefix segments become underscores. This is the canonical binding rule; do not arbitrarily insert underscores between camelCase words assuming they are equivalent.

## 13. Limitations and Unbindable Cases

### 13.1. Missing Setters or Non-Writable Properties

If a class exposes only getters without setters, the binder cannot arbitrarily modify values like a normal mutable JavaBean. Some nested collections can be updated when pre-initialized and exposed via getters returning mutable collections, but not every read-only field can be bound.

For third-party components that do not support JavaBean binding, use intermediate properties or an adapter/factory instead of trying to force the annotation to work directly.

### 13.2. Mismatched Property Names

For example, `jdbc-url` matches `jdbcUrl`, whereas `url` does not magically map to `jdbcUrl` just because they mean the same thing. When a library uses specific field names, consult its API documentation.

### 13.3. Object Already Active Before Binder Assigns Values

Never open connections, bind sockets, start threads, or use a pool directly inside the `@Bean` method when they depend on properties the binder **has not yet populated**:

~~~java
@Bean
@ConfigurationProperties("app.datasource.reporting")
HikariDataSource reportingDataSource() throws Exception {
    HikariDataSource ds = new HikariDataSource();

    // Avoid: may initialize pool before @ConfigurationProperties binds.
    // ds.getConnection();

    return ds;
}
~~~

If the object must be constructed with bound values upfront, use the `HikariConfig` pattern or an intermediate properties class and create the dependent bean from it.

### 13.4. Mistyped Configuration

If `maximum-pool-size: abc` is set while the setter expects `int`, conversion fails and halts startup. If `maximum-pool-size: -5` converts to `int`, the library class may still reject it in its own validation. Distinguish **type conversion** from **library validity constraints**.

### 13.5. Unknown Properties Are Ignored

Some `@ConfigurationProperties` binding modes ignore unmapped properties per the annotation's `ignoreUnknownFields` attribute. Thus a typo like `maximun-pool-size` may silently fail to take effect without an obvious error.

Use vendor-supported property names, verify effective configuration in test environments, and add validation for mandatory fields.

### 13.6. Multiple Beans of the Same Type

Registering a custom `HikariDataSource` bean can affect Spring DataSource/JPA auto-configuration bean selection. When multiple `DataSource` beans exist, manage bean names, `@Primary` for the default datasource, `@Qualifier` for explicit dependencies, and corresponding transaction managers. Avoid colliding bean names or leaving multiple indistinguishable beans when the application expects to autowire a single instance.

## 14. Validation for Third-Party Library Objects

Placing `@ConfigurationProperties` on a method does not let you add `@NotBlank`, `@Min`, or other constraints onto fields inside a library JAR. Therefore, do not assume vendor beans enforce **your application's business Bean Validation**.

A safe approach is creating an **application-owned properties class** with explicit constraints, then using the validated data to construct the vendor bean.

Example:

~~~java
package com.example.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "vendor.client")
public record VendorClientProperties(
        @NotBlank String endpoint,
        @Min(1) int maxConnections) {
}
~~~

Register this type using `@EnableConfigurationProperties(VendorClientProperties.class)` or `@ConfigurationPropertiesScan`. In Spring Boot 3.x, an appropriate Bean Validation implementation is needed, usually provided by `spring-boot-starter-validation`.

Constructing the vendor bean:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(VendorClientProperties.class)
public class VendorClientConfiguration {

    @Bean
    public ImmutableVendorClient vendorClient(VendorClientProperties props) {
        return new ImmutableVendorClient(
                props.endpoint(),
                props.maxConnections());
    }
}
~~~

This pattern is especially valuable when you need fail-fast checks for missing, blank, out-of-range, or security-sensitive values. It also works for mutable vendor objects if you prefer validating settings before calling setters.

For HikariCP, the library class performs some internal pool validation, which still does not cover all business rules such as "allow HTTPS only" for an HTTP client or "permit only approved database hosts."

## 15. Comparing `@ConfigurationProperties` on `@Bean` with `@Value`

Another approach is manual assignment using `@Value`:

~~~java
@Bean
VendorClientConfig vendorClientConfig(
        @Value("${vendor.client.endpoint}") String endpoint,
        @Value("${vendor.client.max-connections:5}") int maxConnections) {

    VendorClientConfig config = new VendorClientConfig();
    config.setEndpoint(endpoint);
    config.setMaxConnections(maxConnections);
    return config;
}
~~~

For one or two values with simple object construction, `@Value` can be acceptable. As property count grows, it becomes cumbersome.

| Criterion | `@ConfigurationProperties` on `@Bean` | `@Value` in Factory Method |
| --- | --- | --- |
| Groups properties by prefix | Yes | Must write each placeholder manually |
| Relaxed binding | Yes | More limited per placeholder mechanics |
| Type conversion | Binder / ConversionService | Placeholders and type conversion |
| Line count with many setters | Usually concise | Scales with field count |
| Requires mutable JavaBean vendor class | Typically yes | Not required if calling constructor/builder directly |
| Business validation | Requires extra config/checks | Requires extra checks |
| Works for immutable constructor-only classes | Not directly | Can instantiate via injected parameters |

No single rule fits every library. Choose based on the vendor API, mutability, clarity, and validation requirements.

## 16. Multiple Configurations for the Same Library Type

Suppose a system has two HikariCP datasources:

~~~yaml
app:
  datasource:
    reporting:
      jdbc-url: jdbc:postgresql://localhost:5432/reporting
      maximum-pool-size: 8

    analytics:
      jdbc-url: jdbc:postgresql://localhost:5432/analytics
      maximum-pool-size: 4
~~~

You can create two beans using two distinct prefixes:

~~~java
@Configuration(proxyBeanMethods = false)
public class MultipleDataSourceConfiguration {

    @Bean(name = "reportingDataSource", destroyMethod = "close")
    @ConfigurationProperties(prefix = "app.datasource.reporting")
    public HikariDataSource reportingDataSource() {
        return new HikariDataSource();
    }

    @Bean(name = "analyticsDataSource", destroyMethod = "close")
    @ConfigurationProperties(prefix = "app.datasource.analytics")
    public HikariDataSource analyticsDataSource() {
        return new HikariDataSource();
    }
}
~~~

Consuming bean:

~~~java
@Service
public class AnalyticsJob {
    private final DataSource analyticsDataSource;

    public AnalyticsJob(
            @Qualifier("analyticsDataSource") DataSource analyticsDataSource) {
        this.analyticsDataSource = analyticsDataSource;
    }
}
~~~

The two beans share the same class yet read from **two separate namespaces**, so they do not overwrite each other merely because both use `HikariDataSource`. However, as noted earlier, multi-datasource applications also require properly configured transaction managers, repository/JPA mappings, primary selection, and startup handling.

If you do not need multiple separate datasources, do not create extra beans just to demonstrate the annotation; this scenario illustrates how choosing **prefix + bean name** impacts architecture.

## 17. How to Verify Bound Values

In development environments, you can inject the vendor bean and print non-sensitive properties:

~~~java
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportingDiagnostics {

    @Bean
    ApplicationRunner printPoolSettings(
            @Qualifier("reportingDataSource") HikariDataSource ds) {

        return args -> {
            System.out.println("Pool name = " + ds.getPoolName());
            System.out.println("Max size = " + ds.getMaximumPoolSize());
            System.out.println("JDBC URL = " + ds.getJdbcUrl());
        };
    }
}
~~~

This example is strictly for observing binding in test environments. Database URLs can expose infrastructure details, so production should restrict logging and access. Never log `ds.getPassword()`.

Spring Boot Actuator, when enabled and properly secured, helps inspect bound configuration via `/actuator/configprops` and property sources via `/actuator/env`. Because these endpoints can expose sensitive data, never leave them publicly accessible just for debugging.

A diagnostic checklist:

1. Was `@Configuration` component-scanned or imported into the context?
2. Was `@Bean` actually created, or excluded by a condition?
3. Does the prefix exactly match the YAML/Properties structure?
4. Does the vendor class expose matching getters/setters accepting convertible types?
5. Is another configuration source overriding the key unexpectedly?
6. Is the bean being used before binding finishes?
7. Are multiple beans of the same type causing ambiguous injection?
8. Does the vendor enforce validation or lifecycle limits on values or when setters can be called?

When errors occur, check **effective property sources**, **JavaBean property names**, and **initialization timing** before assuming `@ConfigurationProperties` was ignored.

## 18. Practice Exercise

Suppose a library provides:

~~~java
public class VendorSchedulerConfig {
    private int workerCount = 2;
    private boolean enabled = false;
    private String queueName;

    public int getWorkerCount() { return workerCount; }
    public void setWorkerCount(int workerCount) {
        this.workerCount = workerCount;
    }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getQueueName() { return queueName; }
    public void setQueueName(String queueName) {
        this.queueName = queueName;
    }
}
~~~

The project registers the bean:

~~~java
@Configuration(proxyBeanMethods = false)
class SchedulerConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "vendor.scheduler")
    VendorSchedulerConfig vendorSchedulerConfig() {
        return new VendorSchedulerConfig();
    }
}
~~~

`application.yml`:

~~~yaml
vendor:
  scheduler:
    worker-count: 6
    enabled: true
    queue-name: priority
~~~

**Question 1:** once bound, what values do the three fields hold?

**Answer:** `workerCount=6`, `enabled=true`, `queueName=priority`. The binder uses prefix `vendor.scheduler` and relaxed binding to map `worker-count` to `workerCount`.

**Question 2:** if `worker-count` is removed from YAML, which value is retained?

If no other source provides the property, `workerCount` retains the default `2` initialized by the library's constructor/field initializer. The binder does not turn that default into a key inside `Environment`.

**Question 3:** what happens if YAML changes to `workers-count: 6`?

The name `workers-count` does not match JavaBean property `workerCount`. If unknown fields are ignored, `workerCount` remains `2` with no obvious error. You must use the exact name supported by the library or enable strict/validation rules as appropriate.

**Question 4:** if `VendorSchedulerConfig` has no setters and only takes constructor `VendorSchedulerConfig(int, boolean, String)`, does putting the annotation on `@Bean` automatically supply those three constructor arguments?

**No.** The factory method must instantiate the object itself. Bind an application-owned properties class (such as a record with constructor binding), then pass the bound values to the vendor constructor inside a `@Bean` method.

## 19. Summary

- **Use `@ConfigurationProperties` on `@Bean`** when binding configuration onto a JavaBean object provided by an external library without modifying its class.
- **The annotation sits at the bean registration point:** Spring invokes the factory method, creates the instance, and the binder sets properties on the object by prefix.
- **Use exact vendor setter and property names:** e.g., HikariCP uses `jdbc-url` to bind `jdbcUrl`; do not arbitrarily substitute `url`.
- **Configuration still comes from `Environment` in source precedence order** and supports relaxed binding.
- **Do not rely on direct constructor binding for beans created via `@Bean`**. For immutable or builder-only classes, bind an intermediate properties class and construct the vendor object explicitly.
- **Do not assume business validation is built in:** explicitly check required fields, type errors, ranges, and security constraints.
- **Manage bean lifecycle and conflicts:** especially for datasources, connection pools, and multiple instances of the same class.

### References

- Spring Boot Reference — Externalized Configuration, Third-party Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.third-party-configuration
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot Reference — Relaxed Binding: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding
- HikariCP: https://github.com/brettwooldridge/HikariCP
