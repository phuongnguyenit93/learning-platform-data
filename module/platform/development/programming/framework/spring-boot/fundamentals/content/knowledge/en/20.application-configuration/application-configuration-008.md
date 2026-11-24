# Registering with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`

Spring Boot encourages grouping related configuration values into a strongly typed object using **@ConfigurationProperties**. Rather than reading scattered configuration strings with `@Value`, an application can define a class or record holding fields such as host, port, timeout, and retry, and let Spring Boot bind data from `Environment` into that object.

However, **putting @ConfigurationProperties on a type does not automatically guarantee that the type becomes a bean in the ApplicationContext**. Spring Boot needs to know which configuration types should be registered. Two common mechanisms are:

- **@ConfigurationPropertiesScan**: scans specified packages for eligible `@ConfigurationProperties` types and registers them.
- **@EnableConfigurationProperties**: explicitly registers one or more listed `@ConfigurationProperties` types.

Both support creating and binding configuration beans, yet differ in **how types are selected, scope of effect, and when to use each**. This lesson progresses from a small application to an auto-configuration library, covering JavaBean/record binding, validation, testing, and diagnosing common issues.

## 1. Distinguishing three steps: declaration, registration, and binding

Before picking a registration annotation, separate three concepts:

1. **Structure declaration**: a class with `@ConfigurationProperties` describes the prefix and the fields or constructor parameters to populate.
2. **Bean registration**: the Spring `ApplicationContext` must have a bean of that properties type.
3. **Binding**: Spring Boot reads values from `Environment` and assigns them to the bean using JavaBean setters or appropriate constructor binding.

For example:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    private String host;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }
}
~~~

This annotation states that `MailProperties` expects data under the **app.mail** prefix. To inject `MailProperties`:

~~~java
public MailService(MailProperties properties) {
    this.properties = properties;
}
~~~

Spring must also register a `MailProperties` bean via scanning, enabling, component scanning, or an appropriate factory method.

Without registration, you may encounter an exception such as:

~~~text
No qualifying bean of type 'com.example.demo.config.MailProperties'
available
~~~

This error is about a **missing bean**, not necessarily that the `app.mail.host` configuration key is missing. A binding error and a bean registration error are two distinct problems.

### 1.1. Flow from configuration to consumer

~~~text
application.yml / environment variables / command line
                         │
                         ▼
                 Spring Environment
                         │
                         ▼
@ConfigurationProperties(prefix = "app.mail")
                         │
                         ▼
Register MailProperties type as a bean
    ├── @ConfigurationPropertiesScan
    └── @EnableConfigurationProperties
                         │
                         ▼
      Spring Boot binds and converts types
                         │
                         ▼
    MailProperties is injected into service
~~~

Spring Boot has multiple property sources and value precedence rules. The two annotations in this lesson primarily decide **which properties types get registered**, not which specific YAML file is used.

## 2. Running example: mail connection configuration

Let us build an application structured as:

~~~text
src/main/java/com/example/demo/
├── DemoApplication.java
├── config/
│   └── MailProperties.java
└── mail/
    ├── MailEndpoint.java
    └── MailConfiguration.java

src/main/resources/
└── application.yml
~~~

`application.yml`:

~~~yaml
app:
  mail:
    host: smtp.example.internal
    port: 2525
    connect-timeout: 4s
~~~

Properties class using JavaBean binding:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host;
    private int port = 25;
    private Duration connectTimeout = Duration.ofSeconds(3);

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Spring Boot can bind:

| Property | Java field | Result |
|---|---|---|
| app.mail.host | host | smtp.example.internal |
| app.mail.port | port | 2525 |
| app.mail.connect-timeout | connectTimeout | Duration.ofSeconds(4) |

If `port` is omitted, the default value `25` in the object can be preserved. If `connect-timeout` is omitted, this example defaults to 3 seconds.

Key point: **@ConfigurationProperties is not a component stereotype annotation automatically picked up by regular component scanning**. We will choose one of two ways to register the properties bean.

## 3. Approach 1: @ConfigurationPropertiesScan

**@ConfigurationPropertiesScan** lives in the package:

~~~java
org.springframework.boot.context.properties.ConfigurationPropertiesScan
~~~

This annotation tells Spring Boot to find eligible `@ConfigurationProperties` types within the scanned packages and register them with the `ApplicationContext`.

Example placed on the main application class:

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

When no package is specified, scanning begins from the **package of the class annotated with @ConfigurationPropertiesScan**. In this example that is `com.example.demo`, so it covers `com.example.demo.config` and other subpackages.

Spring Boot discovers `MailProperties` annotated with `@ConfigurationProperties` and registers the bean for binding.

### 3.1. @SpringBootApplication does not replace @ConfigurationPropertiesScan by default

`@SpringBootApplication` includes key mechanisms like component scan and auto-configuration, **but it does not automatically scan and register every class annotated only with @ConfigurationProperties**.

For a `MailProperties` class without `@Component` and without a `@Bean` declaration, a registration mechanism such as `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` is needed.

If you only add `@ConfigurationProperties` to the class and wait for `@SpringBootApplication` to pick up all properties classes automatically, the application may lack the `MailProperties` bean.

### 3.2. Specifying packages with basePackages

You can specify the packages to scan explicitly:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan(
        basePackages = "com.example.demo.config")
public class DemoApplication {
    // ...
}
~~~

Spring Boot looks for properties types inside the specified package and its subpackages instead of relying on the default package of the annotated class.

This is useful when:

- Configuration is centralized in a separate package.
- The main application class sits in a package that does not cover the properties classes.
- You want to restrict which configuration properties types are auto-registered.

A drawback of package name strings is that they can break during package refactoring or module renaming if you forget to update the annotation.

### 3.3. Specifying packages with basePackageClasses

A more refactor-safe way is referencing a class:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan(
        basePackageClasses = MailProperties.class)
public class DemoApplication {
    // ...
}
~~~

Spring Boot uses the **package containing `MailProperties`** as the scan root, rather than scanning only that single class.

If you want to decouple the package reference from a concrete config type, you can create a marker class or interface in the target package:

~~~java
package com.example.demo.config;

public interface ConfigurationPackageMarker {
}
~~~

Then:

~~~java
@ConfigurationPropertiesScan(
        basePackageClasses = ConfigurationPackageMarker.class)
~~~

This works well when scanning an entire package with many properties classes without tying yourself to one specific class name.

### 3.4. Multiple packages can be declared

Both `basePackages` and `basePackageClasses` accept multiple locations:

~~~java
@ConfigurationPropertiesScan(
        basePackages = {
                "com.example.shared.config",
                "com.example.demo.config"
        })
~~~

Expand the scan scope deliberately. An overly broad scan root can register unneeded configuration properties or obscure which class is responsible for enabling a configuration group.

## 4. Approach 2: @EnableConfigurationProperties

**@EnableConfigurationProperties** lives in the package:

~~~java
org.springframework.boot.context.properties.EnableConfigurationProperties
~~~

This annotation lets you **explicitly** list the `@ConfigurationProperties` types to register.

For example:

~~~java
package com.example.demo;

import com.example.demo.config.MailProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(MailProperties.class)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Spring Boot registers the specified `MailProperties` type and binds values under the `app.mail` prefix.

Unlike `@ConfigurationPropertiesScan`, **Spring does not need to search for `MailProperties` via package scanning**. The type is named right in the annotation.

### 4.1. Registering multiple properties types

~~~java
@EnableConfigurationProperties({
        MailProperties.class,
        StorageProperties.class,
        ReportProperties.class
})
~~~

When you have three separate configuration groups, you can register all three on the same configuration class.

Advantages of this approach:

- The list of enabled types is visible directly in the source.
- Does not depend on which package the properties class lives in.
- Easy to control registration in a small module or auto-configuration.
- Behavior is unlikely to change unexpectedly when someone drops a new class into a scanned package.

The trade-off is that when adding a new properties class, the developer must remember to add that type to the appropriate annotation.

### 4.2. Placing it on a @Configuration class

You do not have to put `@EnableConfigurationProperties` on the main application class. For example:

~~~java
package com.example.demo.mail;

import com.example.demo.config.MailProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(MailProperties.class)
public class MailConfiguration {

    @Bean
    MailEndpoint mailEndpoint(MailProperties properties) {
        return new MailEndpoint(
                properties.getHost(),
                properties.getPort(),
                properties.getConnectTimeout());
    }
}
~~~

And `MailEndpoint` is an immutable value object:

~~~java
package com.example.demo.mail;

import java.time.Duration;

public record MailEndpoint(
        String host,
        int port,
        Duration connectTimeout) {
}
~~~

Spring processes `MailConfiguration` if it is component-scanned or imported into the context. `MailProperties` is then registered and `MailEndpoint` can receive the configuration object as a `@Bean` method parameter.

Note: **@EnableConfigurationProperties only takes effect when the annotated class itself is processed by Spring**. Placing it on a configuration class outside component scan that is never imported will not activate that class.

### 4.3. What does using it with no arguments mean?

You may encounter:

~~~java
@EnableConfigurationProperties
~~~

Using the annotation without listing types can enable infrastructure supporting configuration properties, **but it does not automatically scan and register every properties class in the application**.

When you need to register a specific type, list it:

~~~java
@EnableConfigurationProperties(MailProperties.class)
~~~

or use `@ConfigurationPropertiesScan` with an appropriate scan scope.

## 5. Comparing the two registration approaches

| Criterion | @ConfigurationPropertiesScan | @EnableConfigurationProperties |
|---|---|---|
| Type selection | Finds `@ConfigurationProperties` types in scanned packages | Lists exact types to register |
| Scope | Package-based, configurable via `basePackages`/`basePackageClasses` | Class list in the annotation |
| Adding a new properties class | Discovered automatically if within scan scope | Must be registered explicitly |
| Moving packages | Can be affected if scan root no longer covers it | Independent of package location of the listed type |
| Best suited for | Applications with many internal config groups | Dedicated configs, integration modules, auto-configurations |
| Primary risk | Scanning too broadly or wrong package | Forgetting to add a new type to the list |
| Bean created | Boot-registered configuration properties bean | Boot-registered configuration properties bean |
| Binding mechanism | Spring Boot Configuration Properties Binder | Same Spring Boot binding mechanism |

The two annotations differ in **registration strategy**, not in YAML parsing rules or data type conversion.

### 5.1. Use one clear owner for each type

Design-wise, do not try to register a properties class with both approaches at once.

Unnecessary example:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
@EnableConfigurationProperties(MailProperties.class)
public class DemoApplication {
    // ...
}
~~~

When both mechanisms detect the same configuration properties type, Spring Boot may deduplicate registration by canonical bean name, **but do not rely on redundant combinations as a design pattern**. Giving each type one clear registration owner is easier to read, test, and reason about.

### 5.2. Quick rule of thumb

If you are building a **Spring Boot application** with multiple internal properties classes under a well-defined package, `@ConfigurationPropertiesScan` is usually convenient.

If you are writing **a `@Configuration` or `@AutoConfiguration`** for a specific module or feature and know the exact properties classes it needs, `@EnableConfigurationProperties` usually makes more sense.

The key is avoiding unintended registration and making it clear which configuration owns the properties bean.

## 6. Why is @Component not an equivalent option?

You may encounter classes like:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    // Fields and setters.
}
~~~

If this class's package is within component scan, Spring can register it as a regular bean, and Spring Boot will bind properties appropriately.

So why still learn the two annotations above?

### 6.1. Component scanning and properties scanning are different

Component scan searches for Spring components annotated with stereotypes like `@Component`. `@ConfigurationPropertiesScan` searches for types annotated with `@ConfigurationProperties` according to its own rules.

In particular, **@ConfigurationPropertiesScan skips classes annotated with @Component or meta-annotated with @Component**. Thus, if you put `@Component` on `MailProperties`, the bean may appear via component scanning, **not via @ConfigurationPropertiesScan**.

This easily causes confusion: removing `@Component` later makes the bean suddenly vanish if no proper registration mechanism exists; or a class outside component scan fails to register even with `@Component`.

### 6.2. Constructor binding does not share the same model as @Component

An immutable configuration properties type requires Spring Boot to bind data via its constructor. For types registered with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, Spring Boot can use constructor binding.

By contrast, a bean registered via `@Component` component scanning is instantiated through regular Spring instantiation; its constructor is treated as normal dependency injection, **not automatically as configuration properties constructor binding**.

Therefore, record properties or immutable properties classes should not be registered with `@Component` if you rely on Spring Boot constructor binding.

### 6.3. Separating property holders from component logic

A properties class should focus on configuration data, validation, and defaults. It should not make network calls, initialize clients, or orchestrate workflows.

Separated design:

~~~text
MailProperties  --(injected into)--> MailConfiguration
                                          │
                                          ▼
                                      MailEndpoint
                                          │
                                          ▼
                                     Business Service
~~~

Business components are registered separately; properties classes are not services.

## 7. Binding immutable objects with Java records

In Spring Boot 3, a record with a suitable canonical constructor can be used for **constructor binding** without setters.

For example:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        String host,
        @DefaultValue("25") int port,
        @DefaultValue("3s") Duration connectTimeout) {
}
~~~

When `Environment` has:

~~~yaml
app:
  mail:
    host: smtp.example.internal
    connect-timeout: 5s
~~~

Boot can construct `MailProperties` via its constructor, with `host` from YAML, `port` defaulting to 25, and `connectTimeout` equal to 5 seconds.

With this record, pick **one of the two** registration methods:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
~~~

or:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(MailProperties.class)
class MailPropertiesConfiguration {
}
~~~

Record fields are final in Java, so no setters are needed. This reduces the risk of accidental configuration mutation after the bean is created.

### 7.1. @ConstructorBinding in Spring Boot 3

For a properties class with a single binding constructor, Boot 3 can infer constructor binding. When multiple constructors exist and you need to designate the constructor for binding, use **@ConstructorBinding** on the target constructor from:

~~~java
org.springframework.boot.context.properties.bind.ConstructorBinding
~~~

In Spring Boot 3, this annotation is placed on the constructor, rather than the class-level `@ConstructorBinding` pattern familiar from some Boot 2 versions.

Illustrative example:

~~~java
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int limit;

    @ConstructorBinding
    public CacheProperties(int limit) {
        this.limit = limit;
    }

    public CacheProperties() {
        this(100);
    }

    public int getLimit() {
        return limit;
    }
}
~~~

If there is only one constructor and no ambiguity, an explicit annotation is normally unnecessary.

### 7.2. Do not annotate records with @Component just for Spring discovery

Common mistake:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String host, int port) {
}
~~~

When regular component scanning creates the bean, Spring may try to resolve constructor parameters as `String` and `int` bean dependencies instead of binding from `app.mail.host` and `app.mail.port`. This typically fails bean creation.

For record configuration properties, use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

## 8. Validation of @ConfigurationProperties

Registration ensures the bean is known; binding populates data into the object. The application also needs to verify that the data **is valid**.

For instance, `host` must not be blank, `port` must fall between 1 and 65535, and timeout must have a sensible value.

With a JavaBean properties class:

~~~java
package com.example.demo.config;

import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    @NotBlank
    private String host;

    @Min(1)
    @Max(65535)
    private int port = 25;

    @NotNull
    private Duration connectTimeout = Duration.ofSeconds(3);

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

The application needs an appropriate Bean Validation provider, usually added via:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

In Spring Boot 3, constraint annotations use the **jakarta.validation** namespace. If the application binds an empty host and `@Validated` is applied, creating/binding the properties bean can fail with a validation message instead of continuing startup with invalid configuration.

### 8.1. Validation works with both scan and enable

Both `@ConfigurationPropertiesScan` and `@EnableConfigurationProperties` route types through Spring Boot's same configuration properties binding and validation infrastructure.

It is not the case that scanning validates while enabling skips validation, or vice versa. What matters is:

- Whether the properties bean is registered and bound.
- Whether appropriate validation annotations are declared.
- Whether a Bean Validation provider is on the classpath.
- Whether nested validation is configured properly.

### 8.2. Nested properties and @Valid

Suppose there is a credentials group:

~~~yaml
app:
  mail:
    host: smtp.example.internal
    credentials:
      username: mailer
      password: example-secret
~~~

You can organize the JavaBean properties as:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    @Valid
    private Credentials credentials = new Credentials();

    public Credentials getCredentials() {
        return credentials;
    }

    public void setCredentials(Credentials credentials) {
        this.credentials = credentials;
    }

    public static class Credentials {
        @NotBlank
        private String username;

        @NotBlank
        private String password;

        public String getUsername() { return username; }
        public void setUsername(String username) {
            this.username = username;
        }

        public String getPassword() { return password; }
        public void setPassword(String password) {
            this.password = password;
        }
    }
}
~~~

**@Valid** on the nested field instructs validation to descend into the child object. This example requires the imports from `jakarta.validation` and `org.springframework.validation.annotation.Validated` shown earlier.

Note: do not log the full properties object if it contains passwords, tokens, or secrets. Validation and debugging are not reasons to leak secrets into logs.

## 9. Relaxed binding does not depend on the registration method

Spring Boot supports relaxed binding for configuration properties. For instance, the Java field:

~~~java
private Duration connectTimeout;
~~~

can receive its value from a canonical kebab-case property:

~~~yaml
app:
  mail:
    connect-timeout: 4s
~~~

In OS environment variables, a corresponding name can be expressed as:

~~~text
APP_MAIL_CONNECTTIMEOUT=4s
~~~

Spring Boot applies naming rules and type conversion per property source. In official documentation and config files, use canonical kebab-case property names to avoid confusion.

Types supported by the Binder include:

- String, boolean, integer, floating-point numbers.
- Enums.
- `Duration`, e.g., `250ms`, `4s`, `2m`.
- `DataSize`, e.g., `10MB` or `512KB`.
- `List`, `Set`, `Map` with compatible structures.
- Nested objects.

For example:

~~~yaml
app:
  worker:
    enabled: true
    retry-count: 3
    timeout: 5s
    targets:
      - south
      - north
~~~

These values can bind into `WorkerProperties` if the corresponding fields, getters/setters, or constructor parameters are declared properly.

**@ConfigurationPropertiesScan and @EnableConfigurationProperties do not have different relaxed binding engines.** They merely choose how types are registered for the Binder to process.

## 10. Package layout and search scope

A common cause of missing beans is placing `@ConfigurationPropertiesScan` on a class in the wrong package.

For example:

~~~text
com.example.application
  └── DemoApplication.java

com.example.shared.config
  └── MailProperties.java
~~~

If `DemoApplication` resides in `com.example.application` and declares only:

~~~java
@ConfigurationPropertiesScan
~~~

the default scan does not cover `com.example.shared.config`. `MailProperties` will not be discovered by this mechanism.

You can fix it with:

~~~java
@ConfigurationPropertiesScan(
        basePackageClasses = MailProperties.class)
~~~

or register directly:

~~~java
@EnableConfigurationProperties(MailProperties.class)
~~~

### 10.1. In multi-module projects

Suppose:

~~~text
modules/
├── app/
│   └── com.example.app.DemoApplication
└── shared-config/
    └── com.example.shared.config.MailProperties
~~~

Having the `app` module depend on `shared-config` puts the class on the classpath, **but does not automatically expand the scan root** of `@ConfigurationPropertiesScan`.

To scan `shared-config`, specify its package or marker class. If you only need `MailProperties`, `@EnableConfigurationProperties(MailProperties.class)` may be clearer.

### 10.2. Scanning too broadly can cause unintended side effects

A very wide scan root such as `com.example` may pick up:

- Configuration properties for multiple in-development features.
- Properties classes used conditionally by other libraries.
- Classes the application does not intend to register yet.

If those classes carry mandatory validation, they can fail startup even when the related feature is disabled.

When features have independent lifecycles or activation conditions, explicit registration in `@Configuration`/`@AutoConfiguration` helps reduce coupling.

## 11. Using @EnableConfigurationProperties in auto-configuration

This is one scenario where `@EnableConfigurationProperties` is especially valuable. Suppose you develop a greeting library with properties:

~~~java
package com.example.greeting;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "greeting")
public class GreetingProperties {

    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

Auto-configuration:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingProperties;
import com.example.greeting.GreetingService;
import com.example.greeting.DefaultGreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
@ConditionalOnProperty(
        prefix = "greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(GreetingProperties properties) {
        return new DefaultGreetingService(properties.getPrefix());
    }
}
~~~

In this example:

1. Spring Boot processes the auto-configuration if registered through the library's imports mechanism.
2. `@EnableConfigurationProperties` registers the exact `GreetingProperties` type required by this configuration.
3. Property `greeting.enabled` conditionally controls whether this configuration applies.
4. `@ConditionalOnMissingBean` allows applications to replace the default `GreetingService`.

### 11.1. Why should auto-configuration avoid broad package scanning?

A library can be added to many different applications. If its auto-configuration scans too broadly, it could register unrelated properties types or trigger validation when features are turned off.

Explicit registration via `@EnableConfigurationProperties` makes clear **which properties types belong to that auto-configuration**.

### 11.2. Distinguishing properties registration from service creation

`@EnableConfigurationProperties` registers `GreetingProperties`, **but does not automatically create `GreetingService`**. The service is still registered via `@Bean`, `@Component`, or appropriate auto-configuration.

~~~text
@EnableConfigurationProperties(GreetingProperties.class)
                         │
                         ▼
                 GreetingProperties bean
                         │
                         ▼
@Bean GreetingService greetingService(GreetingProperties)
                         │
                         ▼
                  GreetingService bean
~~~

This separates **configuration data** from **application components**.

## 12. @Bean combined with @ConfigurationProperties: a third registration approach

Sometimes you need to bind configuration directly onto a third-party library object whose source you cannot edit to add `@ConfigurationProperties`.

In that case, you can place `@ConfigurationProperties` on a `@Bean` method:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.client")
    VendorClientOptions vendorClientOptions() {
        return new VendorClientOptions();
    }
}
~~~

Spring creates the bean via the factory method and then binds matching properties onto that object. This pattern fits third-party objects that have setters or compatible binding mechanisms.

This is **a different approach from registering a `@ConfigurationProperties` class via scan or enable**:

- `@ConfigurationPropertiesScan` discovers annotated classes.
- `@EnableConfigurationProperties` registers a list of classes.
- `@Bean` + `@ConfigurationProperties` declares a specific bean and requests binding onto that bean.

If you want constructor binding for an immutable record, use the appropriate scan/enable mechanism instead of assuming a `@Bean` factory method supports constructor binding the way Boot creates properties beans.

## 13. Bean names when registering with scan or enable

When Spring Boot registers a configuration properties class via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, it normally names the bean following the convention:

~~~text
<prefix>-<fully-qualified-class-name>
~~~

For example:

~~~text
app.mail-com.example.demo.config.MailProperties
~~~

This is the conventional bean name Boot uses for this kind of registration. If there is no prefix, the naming convention may consist solely of the fully qualified class name.

In business code, inject **by type** wherever possible:

~~~java
public MailService(MailProperties properties) {
    this.properties = properties;
}
~~~

Do not hard-code package-qualified bean names in most consumers, since renaming packages or changing registration mechanisms can affect bean names.

### 13.1. Can there be multiple beans of the same type?

Normally, registering a properties type once is enough. If you intentionally create multiple beans of the same type using `@Bean` or different mechanisms, injection by type may encounter ambiguity.

In that situation:

- Verify whether multiple instances are truly needed.
- Assign explicit bean names and `@Qualifier` annotations.
- Avoid duplicate registration caused by overlapping `@Component`, `@Bean`, and scan/enable.
- If you need multiple configurations with the same structure under different prefixes, consider separate types or `@Bean` methods with distinct names/qualifiers.

### 13.2. Do not use @Primary to mask overlapping registration bugs

`@Primary` chooses a bean for a single dependency, but does not fix why multiple properties beans exist for the same role.

If you accidentally registered one `MailProperties` via `@Component` and another via `@EnableConfigurationProperties`, pick one proper registration mechanism instead of slapping `@Primary` on to "make it work."

## 14. Testing registration with ApplicationContextRunner

When learning configuration properties, isolate registration and binding tests from the full web application. Spring Boot provides **ApplicationContextRunner** to assemble a small `ApplicationContext` with just the configuration classes and property values chosen by the test.

Examples use JUnit 5, AssertJ, and `spring-boot-test`. In Gradle this typically looks like:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 14.1. Testing @EnableConfigurationProperties

Assume `MailProperties` was declared as in Section 2. Create a test configuration registering only that type:

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(MailProperties.class)
class ExplicitMailPropertiesConfiguration {
}
~~~

Test:

~~~java
package com.example.demo.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class ExplicitPropertiesRegistrationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            ExplicitMailPropertiesConfiguration.class);

    @Test
    void registersAndBindsPropertiesExplicitly() {
        runner.withPropertyValues(
                        "app.mail.host=smtp.testing.internal",
                        "app.mail.port=587",
                        "app.mail.connect-timeout=7s")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(MailProperties.class);

                    MailProperties props =
                            context.getBean(MailProperties.class);

                    assertThat(props.getHost())
                            .isEqualTo("smtp.testing.internal");
                    assertThat(props.getPort()).isEqualTo(587);
                    assertThat(props.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(7));
                });
    }
}
~~~

This test verifies two essential things in isolation:

1. Explicit registration creates a `MailProperties` bean.
2. The bean receives property values and converts `Duration`.

It does not need to open an HTTP port or start any business functionality.

### 14.2. Testing @ConfigurationPropertiesScan

For the scan approach, the test configuration is:

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConfigurationPropertiesScan(
        basePackageClasses = MailProperties.class)
class ScannedMailPropertiesConfiguration {
}
~~~

Test:

~~~java
@Test
void registersPropertiesFoundByScan() {
    new ApplicationContextRunner()
            .withUserConfiguration(ScannedMailPropertiesConfiguration.class)
            .withPropertyValues(
                    "app.mail.host=smtp.scan.internal",
                    "app.mail.port=2526")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(MailProperties.class);

                MailProperties props =
                        context.getBean(MailProperties.class);
                assertThat(props.getHost())
                        .isEqualTo("smtp.scan.internal");
                assertThat(props.getPort()).isEqualTo(2526);
            });
}
~~~

This example is meaningful only if `MailProperties` actually resides in the package scanned by the test configuration and is not registered by another mechanism outside the test scope.

In a large codebase, you can isolate a dedicated test package to avoid scanning unrelated properties classes. The goal of the test is verifying **package-based registration**, not accidentally picking up a bean from `@Component` or another auto-configuration.

### 14.3. Verifying that the annotation alone does not register the bean

A test without registration:

~~~java
@Test
void annotationAloneDoesNotRegisterProperties() {
    new ApplicationContextRunner()
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(MailProperties.class);
            });
}
~~~

This test shows that a type in source code, even with `@ConfigurationProperties`, does not enter an empty test context unless scanned, imported, or explicitly registered.

### 14.4. Testing default values

With `MailProperties` defaulting `port` to 25 and `connectTimeout` to 3 seconds:

~~~java
@Test
void retainsDefaultsForMissingProperties() {
    new ApplicationContextRunner()
            .withUserConfiguration(ExplicitMailPropertiesConfiguration.class)
            .withPropertyValues("app.mail.host=smtp.defaults.internal")
            .run(context -> {
                assertThat(context).hasNotFailed();
                MailProperties props =
                        context.getBean(MailProperties.class);

                assertThat(props.getPort()).isEqualTo(25);
                assertThat(props.getConnectTimeout())
                        .isEqualTo(Duration.ofSeconds(3));
            });
}
~~~

Default values come from the Java class or record constructor. This behavior is not unique to either scan or enable.

## 15. Testing validation and invalid configuration

If `MailProperties` has `@Validated` and `@NotBlank` on `host`, verify that the application rejects configuration missing `host`.

~~~java
@Test
void failsWhenRequiredHostIsMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(ExplicitMailPropertiesConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure()).isNotNull();
            });
}
~~~

The test requires a Bean Validation provider and validation constraints declared on the properties class as in Section 8. Without validation enabled, omitting `host` might not fail at binding time since `String host` defaults to `null`.

### 15.1. Reading binding errors at the right layer

When `port` is a string that cannot convert to `int`:

~~~yaml
app:
  mail:
    host: smtp.example.internal
    port: not-a-number
~~~

The bean can fail during binding with details about the property path and conversion failure. The outermost exception may be wrapped in `BeanCreationException` or a binding-related exception, depending on how the bean is created and the Boot version.

When reading startup logs, distinguish:

- **No `MailProperties` bean**: registration never occurred.
- **Definition exists, but binding failed**: property value is invalid or unconvertible.
- **Binding succeeded, but validation failed**: structure has values, yet violates constraints.
- **Binding succeeded, but service failed to construct**: business bean lacks another dependency or failed in its own initialization.

Do not try to fix a binding error by adding `@Primary` or `@Qualifier`. Neither annotation converts a string to `Duration` or validates a port.

### 15.2. Testing with multiple profiles or property sources

In a real application, properties can come from `application.yml`, `application-dev.yml`, environment variables, or command-line arguments.

If you want to test a profile:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(ExplicitMailPropertiesConfiguration.class)
        .withPropertyValues(
                "spring.profiles.active=dev",
                "app.mail.host=smtp.dev.internal")
        .run(context -> {
            // Read and verify the properties bean.
        });
~~~

In `ApplicationContextRunner`, setting `spring.profiles.active` alone does not guarantee the runner loads all configuration files the way a full `SpringApplication` does. Supply concrete property values or use an integration test with full configuration loading when testing profile file resolution.

The purpose of the context runner is testing registration and binding in a small, controlled environment.

## 16. Using @SpringBootTest when verifying the real application

`ApplicationContextRunner` fits isolated configuration tests. When you want to verify package scanning, main application configuration, auto-configuration, and dependency injection across the whole app, use `@SpringBootTest`.

For example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.mail.host=smtp.integration.internal",
        "app.mail.port=1025"
})
class MailPropertiesIntegrationTest {

    @Autowired
    MailProperties mailProperties;

    @Test
    void applicationRegistersBoundMailProperties() {
        assertThat(mailProperties.getHost())
                .isEqualTo("smtp.integration.internal");
        assertThat(mailProperties.getPort()).isEqualTo(1025);
    }
}
~~~

This test passes only if the application actually registers `MailProperties`. In the example layout, that would be `@ConfigurationPropertiesScan` on `DemoApplication` or `@EnableConfigurationProperties` in a scanned/imported `MailConfiguration`.

Because `@SpringBootTest` can initialize many beans, web contexts, and external connections, use `ApplicationContextRunner` for focused tests and reserve `@SpringBootTest` for proving end-to-end wiring.

## 17. Conditional configuration and registration timing

In an auto-configuration, a properties bean may only be registered when conditions on the configuration class are satisfied.

For example:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.MailClient")
@ConditionalOnProperty(
        prefix = "feature.mail",
        name = "enabled",
        havingValue = "true")
@EnableConfigurationProperties(MailProperties.class)
public class MailFeatureAutoConfiguration {
    // Bean methods depending on the vendor library.
}
~~~

If the vendor class is absent or `feature.mail.enabled` is not `true`, this auto-configuration is skipped by its conditions. Registering `MailProperties` is tied to that configuration branch rather than running as an unconditional scan triggered by the main application class.

Conversely, if an application places:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
~~~

then a `MailProperties` inside the scan scope can be registered even when the feature using it is disabled by a condition on another auto-configuration. If `MailProperties` carries mandatory validation, this can force the application to supply configuration for a disabled feature.

This is a strong reason why **@EnableConfigurationProperties placed on the conditional configuration class itself** suits libraries and optional features well.

### 17.1. Registration does not guarantee business conditions

Even if `MailProperties` is registered, a `MailClient` is not automatically created unless a matching `@Bean`, `@Component`, or auto-configuration registers it.

Keep the steps distinct:

~~~text
Feature condition matches
           │
           ▼
Register MailProperties (config holder)
           │
           ▼
Bind + validate configuration data
           │
           ▼
Register MailClient (if bean condition matches)
           │
           ▼
MailService uses the client
~~~

Each stage can fail for different reasons; avoid blaming everything on "scan didn't work."

## 18. Common errors and how to fix them

### 18.1. Added @ConfigurationProperties but injection fails

**Symptom:** `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` for `MailProperties`.

**Cause:** The type was not registered as a bean; the annotation only describes binding.

**Fix:** Use `@ConfigurationPropertiesScan` on the package containing the type or `@EnableConfigurationProperties(MailProperties.class)` on a Spring-processed configuration class.

### 18.2. Scan placed in a package that does not cover the properties class

**Symptom:** Class has the right annotation, yet no `MailProperties` bean exists at startup.

**Cause:** `@ConfigurationPropertiesScan` without `basePackages` scans from the annotated class's package, not the entire classpath.

**Fix:** Move the scan root to an appropriate package, configure `basePackageClasses`, or register explicitly with `@EnableConfigurationProperties`.

### 18.3. @EnableConfigurationProperties sits in an unloaded class

**Symptom:** Code declares `@EnableConfigurationProperties(MailProperties.class)`, yet the context has no `MailProperties`.

**Cause:** The class carrying the annotation is not component-scanned, not imported, and not part of a Boot-processed auto-configuration.

**Fix:** Confirm the configuration class itself is registered with Spring. `@EnableConfigurationProperties` does not make its host class self-discoverable.

### 18.4. Putting @Component on record properties

**Symptom:** Spring reports it cannot find beans of type `String`, `int`, or the constructor parameter types.

**Cause:** Regular component creation attempts to inject constructor parameters as bean dependencies rather than constructor-binding from `Environment`.

**Fix:** Remove `@Component` and use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` for records.

### 18.5. Registering the same type through multiple mechanisms

**Symptom:** Context contains multiple `MailProperties` beans, injection is ambiguous, or configuration is bound twice along different paths.

**Cause:** Mixing `@Component`, `@Bean`, scan, and enable without clear ownership.

**Fix:** Establish a single registration owner per properties type; if multiple beans are intentional, use explicit bean names and qualifiers.

### 18.6. Wrong prefix or property name

**Symptom:** Bean exists, yet fields retain defaults or null.

**Cause:** Class uses prefix `app.mail` while YAML uses `mail.app` or a key outside the prefix.

**Fix:** Compare the annotation's prefix against actual property structure and relaxed binding rules.

### 18.7. Property has a value but fails to bind

**Symptom:** `BeanCreationException` with a conversion cause, such as cannot convert `String` to `Duration` or `int`.

**Cause:** Wrong data type, invalid format, or missing converter.

**Fix:** Supply values with explicit units like `5s` or `200ms`; verify types and conversions; register a converter for custom types.

### 18.8. Validation does not run

**Symptom:** Blank host is still accepted.

**Cause:** Class lacks `@Validated`, missing constraints, no validation provider, or missing nested validation setup.

**Fix:** Verify `jakarta.validation` constraints, `@Validated`, and the Bean Validation dependency.

### 18.9. Scanning picks up properties for a disabled feature

**Symptom:** Application reports missing properties or validation failures for an unused module.

**Cause:** `@ConfigurationPropertiesScan` scans the whole package and registers a properties type not tied to the feature's enablement condition.

**Fix:** Narrow the scan root or move registration of that type to `@EnableConfigurationProperties` on a suitably conditioned configuration class.

### 18.10. Confusing with @ConfigurationProperty or @PropertySource

**Symptom:** Adding a file-loading annotation and expecting a properties bean to appear automatically.

**Cause:** Conflating property source loading with object registration and binding.

**Fix:** Identify which step is missing: whether the property source loaded, whether the properties type is registered, and whether data binds cleanly.

### 18.11. Changing configuration at runtime does not update the bean

**Symptom:** Updating a YAML file after the process starts leaves `MailProperties` holding old values.

**Cause:** Configuration properties are normally bound during bean/context creation. Editing a file does not trigger dynamic refresh.

**Fix:** Restart/redeploy or use a dedicated dynamic refresh mechanism if runtime updates are truly required. Do not mistake `@ConfigurationPropertiesScan` for a file-watching feature.

### 18.12. Mistaking explicit registration for creating multiple instances

**Symptom:** Placing `@EnableConfigurationProperties` in two places and assuming each place creates a separate instance.

**Cause:** The annotation registers a configuration properties type via Boot's mechanism; it does not act as a fresh constructor/factory call every time it appears.

**Fix:** Inspect the actual bean definitions and unify registration ownership. If you need two objects of the same type with different prefixes, design two explicit registrations rather than expecting two `@Enable` annotations to create distinct configured copies.

## 19. Guide for choosing in real-world scenarios

### Scenario A: Web application with many internal properties classes

You have `UserProperties`, `EmailProperties`, and `ReportProperties` in `com.example.app.config`. The main application class is in `com.example.app`.

**Appropriate choice:** Place `@ConfigurationPropertiesScan` on the main class. Spring automatically discovers properties classes within the scan scope.

### Scenario B: A @Configuration needing only one type

`MailConfiguration` needs only `MailProperties`; the main application class sits in a different package.

**Appropriate choice:** `@EnableConfigurationProperties(MailProperties.class)` on `MailConfiguration`. No need to widen the entire application's scan root.

### Scenario C: Writing a Spring Boot starter

`GreetingAutoConfiguration` needs `GreetingProperties` and has `@ConditionalOnClass` or `@ConditionalOnProperty`.

**Appropriate choice:** `@EnableConfigurationProperties(GreetingProperties.class)` on the auto-configuration so registration is tied directly to that feature.

### Scenario D: Multiple properties classes in a shared module

A shared module sits in another package and holds multiple properties classes the application wants to use.

**Appropriate choice:** `@ConfigurationPropertiesScan(basePackageClasses = SharedConfigMarker.class)` if intentionally enabling the whole group. If using only one or two types, explicit `@EnableConfigurationProperties` gives tighter control.

### Scenario E: Immutable properties using records

The properties class is a record with a canonical constructor and no setters.

**Appropriate choice:** scan or enable so Spring Boot performs constructor binding. Avoid adding `@Component` just for bean discovery.

### Scenario F: Binding to a third-party class

A vendor class lacks `@ConfigurationProperties` and its source cannot be modified.

**Appropriate choice:** a `@Bean` method annotated with `@ConfigurationProperties` to bind using that object's supported mechanism, typically JavaBean setters.

## 20. Common misconceptions

**"@ConfigurationProperties is enough for a class to be injected."**  
No. Registration via scan, enable, `@Bean`, or an appropriate component mechanism is required.

**"@SpringBootApplication always scans all @ConfigurationProperties classes."**  
No. Component scanning is not the same as configuration properties scanning.

**"@ConfigurationPropertiesScan scans the entire classpath."**  
No. It scans from the annotated class's package by default, or from explicitly specified packages.

**"@EnableConfigurationProperties works regardless of whether its host configuration class is processed."**  
No. The annotation only takes effect when the class holding it is included in Spring's configuration processing.

**"@EnableConfigurationProperties with no arguments automatically finds every properties class."**  
No. For explicit registration, list the types; for package scanning, use `@ConfigurationPropertiesScan`.

**"Using both @Component and @ConfigurationPropertiesScan on the same class guarantees it registers via scan."**  
No. Classes annotated with `@Component` are excluded from `@ConfigurationPropertiesScan`'s targets; if a bean appears, it comes from component scanning.

**"Record properties should add @Component so they can be instantiated."**  
No. Configuration properties constructor binding and component constructor injection are two different mechanisms.

**"@ConfigurationPropertiesScan has a stronger Binder and validator than @EnableConfigurationProperties."**  
No. Both register properties types to use Boot's exact same binding and validation infrastructure.

**"Using basePackageClasses registers only the single class passed in."**  
No. That attribute determines which packages to scan. If you want a single type, use `@EnableConfigurationProperties(Type.class)`.

**"Having a MailProperties bean means every property is valid."**  
No. You still need clear defaults, conversion, constraints, and a validation policy.

**"@ConfigurationPropertiesScan makes the app re-read YAML whenever the file changes."**  
No. It is a registration mechanism; dynamic configuration refresh is a separate topic.

**"If @ConfigurationPropertiesScan is already present, auto-configurations never need @EnableConfigurationProperties."**  
No. A library should never assume consumers are scanning the library's internal packages. Auto-configurations should register the properties types they require when their conditions match.

## 21. Summary flowchart: how should you decide registration?

~~~text
You have a @ConfigurationProperties class
                   │
                   ▼
Does this class belong to the app's internal
properties and should it be auto-discovered by package?
             │                  │
            Yes                No
             │                  │
             ▼                  ▼
@ConfigurationPropertiesScan    Class is used by a specific
choose appropriate package      configuration/auto-configuration
                                       │
                                       ▼
                          @EnableConfigurationProperties
                          list the specific type
                                       │
                                       ▼
                          Spring Boot registers properties bean
                                       │
                                       ▼
                          Bind / convert / validate
                                       │
                                       ▼
                          Inject into service or @Bean method
~~~

If the object belongs to a third-party library and cannot have annotations on its class, consider a `@Bean` factory method with `@ConfigurationProperties` rather than trying to modify the vendor class.

## Core takeaways

**@ConfigurationProperties** describes how to bind data into a Java type; it does not automatically ensure that type is registered as a Spring bean. **@ConfigurationPropertiesScan** discovers properties types by package scope, making it well suited for an application's internal configuration groups. **@EnableConfigurationProperties** explicitly registers listed types, fitting dedicated configuration classes, standalone features, and conditional auto-configurations.

Both mechanisms share the same binding, type conversion, and validation infrastructure. For Java records or immutable properties, scan/enable is the right choice for Spring Boot constructor binding, rather than adding `@Component` and expecting regular dependency injection. When a properties bean is missing, check registration and package scope first; when the bean exists with wrong values, check prefix, property sources, conversion, and validation. Choosing the right registration strategy makes Spring Boot configuration easier to understand, safer to extend, and simpler to test.
