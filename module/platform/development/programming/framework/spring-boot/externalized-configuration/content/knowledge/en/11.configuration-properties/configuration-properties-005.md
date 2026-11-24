# Registering JavaBean Types with `@Component` and the Scope of `@ConfigurationProperties`

## 1. Purpose and Context

Spring Boot supports **externalized configuration**: environment-varying values supplied from `application.properties`, `application.yml`, environment variables, system properties, command-line arguments, and other Config Data sources. When an application has many related settings, placing numerous `@Value` annotations on individual fields scatters configuration and makes it hard to validate.

`@ConfigurationProperties` lets you **bind a group of properties** sharing a common `prefix` into a typed Java object. One way to register this object is placing both annotations on a JavaBean class:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    // Fields, getters, and setters for Spring Boot binding.
}
~~~

- **`@Component`** makes the class a Spring Framework bean candidate when the component scan scope covers that class.
- **`@ConfigurationProperties(prefix = "app.mail")`** tells Spring Boot's binding mechanism that keys under `app.mail.*` should be mapped onto the JavaBean properties of this bean.
- **JavaBean binding** uses the bean structure and appropriate accessors, typically a no-arg constructor together with getters and setters.
- After Spring instantiates and binds the object, other services can receive `MailProperties` via dependency injection.

This pattern is very common in Spring Boot applications using Java classes whose configuration state is declared with fields and setters. It differs from **constructor binding** for records or immutable classes registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

## 2. Role of Each Annotation

### 2.1. `@Component`: Registering a Bean via Component Scanning

`@Component` is a Spring Framework stereotype annotation. When the application context runs component scanning, a class with this annotation is discovered and registered as a bean definition.

Example:

~~~java
package com.example.orders.config;

import org.springframework.stereotype.Component;

@Component
public class MailProperties {
}
~~~

If `com.example.orders.config` is within the component scan scope, Spring creates a `MailProperties` bean. Under standard default naming rules, the bean may be named `mailProperties`; the application should inject by type rather than relying on that default name.

`@Component` alone **does not specify which property group should be bound**. You need to add `@ConfigurationProperties` and bindable members.

### 2.2. `@ConfigurationProperties`: Describing Prefix and Binding

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    private String host;
    private int port;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
~~~

This annotation does not automatically cause a bean to appear in the application context merely because the class is on the classpath. The bean must be **registered via an appropriate mechanism**. One such mechanism is `@Component` combined with component scanning.

When Boot receives a bean like the example above, the Binder uses the `app.mail` prefix to look up keys:

~~~properties
app.mail.host=mail.example.test
app.mail.port=2525
~~~

After binding, `getHost()` returns `mail.example.test`, and `getPort()` returns `2525`.

### 2.3. Two Annotations Addressing Two Separate Responsibilities

| Component | Responsibility | Does Not Guarantee |
| --- | --- | --- |
| `@Component` | Allows component scanning to register the bean | Does not declare a prefix or how to bind properties |
| `@ConfigurationProperties` | Declares prefix and binding metadata | Does not automatically register every class as a bean |
| JavaBean getters/setters | Allows reading and updating properties | Does not load data from `Environment` on its own |
| Spring Boot Binder | Converts external values into the object | Does not instantiate classes outside bean registration |
| `Environment` | Supplies effective property sources | Does not create beans or decide validation |

In a normally configured Spring Boot application, these mechanisms collaborate to produce a bean populated with configuration values.

## 3. Complete Example: JavaBean Registered with `@Component`

Suppose the main package is `com.example.orders`. Project layout:

~~~text
src/main/java/com/example/orders/
├── OrdersApplication.java
├── config/
│   └── MailProperties.java
└── service/
    └── MailSender.java
src/main/resources/
└── application.yml
~~~

### 3.1. Creating the Configuration Class with Getters/Setters

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host = "localhost";
    private int port = 2525;
    private Duration connectTimeout = Duration.ofSeconds(3);
    private boolean enabled = true;

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

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

This class has an implicit no-arg constructor because no other constructor is declared. Fields have default values so that if the config file does not specify all values, the object can still initialize with sensible defaults.

### 3.2. Defining YAML Configuration

~~~yaml
# application.yml
app:
  mail:
    host: smtp.example.test
    port: 587
    connect-timeout: 5s
    enabled: true
~~~

Spring Boot can bind the values:

| Source Property | JavaBean Member | Value |
| --- | --- | --- |
| `app.mail.host` | `host` | `smtp.example.test` |
| `app.mail.port` | `port` | `587` |
| `app.mail.connect-timeout` | `connectTimeout` | `Duration.ofSeconds(5)` |
| `app.mail.enabled` | `enabled` | `true` |

This is **relaxed binding**: the kebab-case name `connect-timeout` in the configuration file is bound to camelCase `connectTimeout` in Java.

### 3.3. Main Class in the Parent Package

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

`@SpringBootApplication` includes `@ComponentScan` with default configuration. Because `OrdersApplication` resides in `com.example.orders`, component scanning includes the subpackage `com.example.orders.config` and detects `MailProperties`.

With this layout, there is no need to add `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(MailProperties.class)` to register a class that already carries `@Component`.

### 3.4. Injecting Configuration into a Service

~~~java
package com.example.orders.service;

import com.example.orders.config.MailProperties;
import org.springframework.stereotype.Service;

@Service
public class MailSender {

    private final MailProperties mailProperties;

    public MailSender(MailProperties mailProperties) {
        this.mailProperties = mailProperties;
    }

    public String endpoint() {
        return mailProperties.getHost() + ":" + mailProperties.getPort();
    }
}
~~~

Spring injects the `MailProperties` bean by type into `MailSender`. At usage time, standard properties have already been bound during bean initialization. `MailSender` does not have to read the YAML file or parse `"5s"` into `Duration`.

**Example scope note:** `MailSender` above only illustrates reading configuration; it does not open an SMTP connection or send emails.

## 4. JavaBean Binding: Why Are Getters and Setters Needed?

When a bean is created by Spring's standard mechanisms, such as component scanning via `@Component`, `@ConfigurationProperties` uses **JavaBean binding** to populate eligible fields.

Typical pattern:

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private String baseUrl;
    private int retries;

    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }

    public int getRetries() { return retries; }
    public void setRetries(int retries) { this.retries = retries; }
}
~~~

Configuration:

~~~properties
app.client.base-url=https://api.example.test
app.client.retries=3
~~~

The Binder matches key names to JavaBean properties and invokes the necessary setter methods. Getters allow other code to read values and support complex binding scenarios.

### 4.1. No-Argument Constructor

If no constructor is declared, Java generates a no-arg constructor for a standard class. Spring can use that constructor to instantiate the bean, and the Binder then populates values via setters.

You can declare it explicitly:

~~~java
public ClientProperties() {
}
~~~

If a class only has a constructor whose parameters are expected to come from properties, `@Component` **does not automatically turn that constructor into constructor binding**. Spring may try to resolve parameters as standard bean dependency injection. When immutable constructor binding is desired, choose the appropriate registration approach shown later.

### 4.2. Fields Without a Setter

For simple scalars like `String host` or `int port`, an accessible setter is the clearest approach for JavaBean binding.

However, for a pre-initialized, mutable nested object, the Binder can use the getter to access that object without needing a setter on the parent property. For example:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private final Security security = new Security();

    public Security getSecurity() {
        return security;
    }

    public static class Security {
        private boolean tlsEnabled;

        public boolean isTlsEnabled() {
            return tlsEnabled;
        }

        public void setTlsEnabled(boolean tlsEnabled) {
            this.tlsEnabled = tlsEnabled;
        }
    }
}
~~~

Configuration:

~~~yaml
app:
  mail:
    security:
      tls-enabled: true
~~~

The Binder can update `security.tlsEnabled` on the already-initialized `Security` instance. Even though the `security` field is `final`, fields inside the nested object can still be updated via its setters.

Do not generalize that every `final` field can be bound via setter binding; an immutable scalar without a setter requires a different instantiation mechanism.

### 4.3. Lists and Maps

JavaBean example:

~~~java
@Component
@ConfigurationProperties(prefix = "app.gateway")
public class GatewayProperties {

    private java.util.List<String> upstreams =
            new java.util.ArrayList<>();

    public java.util.List<String> getUpstreams() {
        return upstreams;
    }

    public void setUpstreams(java.util.List<String> upstreams) {
        this.upstreams = upstreams;
    }
}
~~~

YAML configuration:

~~~yaml
app:
  gateway:
    upstreams:
      - https://api-a.example.test
      - https://api-b.example.test
~~~

The result is a list with two endpoints. When a list is declared across multiple property sources, override/binding behavior follows Config Data and Binder rules; do not assume elements from all sources are concatenated.

## 5. Component Scan Scope Determines Whether `@Component` Is Registered

A frequent mistake is putting valid `@Component` and `@ConfigurationProperties` annotations on a class, only for startup to fail with:

~~~text
No qualifying bean of type 'com.example.shared.MailProperties'
~~~

The reason may be that the package containing the class is outside component scanning scope.

### 5.1. Default Scope of `@SpringBootApplication`

Example:

~~~text
com.example.orders
├── OrdersApplication
├── config
│   └── MailProperties
└── service
    └── MailSender
~~~

If `OrdersApplication` resides in `com.example.orders`, classes in that package and its subpackages are normally found by component scanning.

However, with:

~~~text
com.example.orders
└── OrdersApplication

com.example.shared.config
└── MailProperties
~~~

`MailProperties` sits outside the default scan scope. In this case, adding `@Component` alone is not enough for Spring to register the bean.

### 5.2. Adjusting Scan Scope When Needed

You can configure it explicitly:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.example.orders",
        "com.example.shared"
})
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Now component scanning can discover `MailProperties` in `com.example.shared.config`.

However, expanding component scan can also pull in unintended services, controllers, configurations, or other beans from that package. If you only want to register **a single configuration class**, consider registering it explicitly with `@EnableConfigurationProperties` and removing `@Component` from the properties class rather than widening component scan excessively.

### 5.3. `@ConfigurationPropertiesScan` Is a Different Scanning Mechanism

`@ConfigurationPropertiesScan` locates and registers `@ConfigurationProperties` classes that are not already managed via standard component mechanisms. It has its own package selection attributes, e.g., `@ConfigurationPropertiesScan(basePackages = "com.example.shared.config")`.

**Notable distinction:** classes annotated or meta-annotated with `@Component` **are not targets that `@ConfigurationPropertiesScan` registers through its dedicated scanning mechanism**. If you choose the `@Component` model, you must ensure **component scanning** finds the class.

Do not try to fix a `@Component` bean outside component scan scope by adding `@ConfigurationPropertiesScan` without understanding the two scanning mechanisms. The two annotations are designed for different registration approaches.

## 6. Prefix Scope: Which Keys Are Bound?

A class declared as:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    private String host;
    // Getters and setters...
}
~~~

looks up keys with the `app.mail` prefix. For example:

~~~properties
app.mail.host=smtp.example.test
app.mail.port=587
app.payment.host=payment.example.test
~~~

`app.payment.host` belongs to a different group and does not bind to `MailProperties`'s `host` field.

Prefixes should use **canonical kebab-case**, such as `app.mail` or `app.outbound-mail`. The internal JavaBean structure can use camelCase and is mapped by relaxed binding from corresponding property names.

A JavaBean class does not represent "the entire configuration file." It only receives the property group matching its prefix and bindable members. Properties belonging to other groups or lacking matching members are typically ignored under default binding settings unless stricter checking is configured.

### 6.1. Application Context Scope

The `MailProperties` bean is registered in Spring's **application context**, which does not mean every Java program running on the machine shares the same instance. If multiple independent application contexts exist, each context has its own beans and `Environment`.

In typical usage, `@Component` creates a bean with the default `singleton` scope: one instance per bean definition per Spring container. Services injecting the same bean see the same configuration object unless scope or context structure is intentionally altered.

Do not confuse "singleton" with a single instance across the entire JVM or across multiple processes/hosts.

### 6.2. `@Profile` and Conditional Bean Registration

`@Component` can be combined with `@Profile` if a class is used only in specific environments:

~~~java
@Component
@Profile("dev")
@ConfigurationProperties(prefix = "app.mock-client")
public class MockClientProperties {
    private String endpoint;
    public String getEndpoint() { return endpoint; }
    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }
}
~~~

If the `dev` profile is inactive, this bean will not be registered. Any service unconditionally injecting it will then fail with a missing bean error.

**Critical difference:** `@Profile` controls **whether the bean is created**; `@ConfigurationProperties` controls **which values are bound if the bean is created**. `application-dev.yml` files and conditional config data are handled by Config Data loading, not as replacements for bean conditions.

## 7. How Does JavaBean Binding Differ from Constructor Binding?

This is an important boundary when using `@Component`.

### 7.1. Mutable JavaBean Model with `@Component`

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    private String host;
    private int port;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
~~~

Spring creates the bean via normal component mechanics and the Binder assigns properties via JavaBean setters. This model is straightforward when using the bean alongside other Spring components or when compatibility with JavaBean-based libraries is needed.

### 7.2. Immutable Model with Constructor Binding

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String host, int port) {
}
~~~

This record can be registered via:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
}
~~~

Or:

~~~java
@Configuration
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {
}
~~~

In Spring Boot 3.x, a record with a single suitable constructor can normally be constructor-bound without placing `@ConstructorBinding` on that record. For multiple constructors or different Boot versions, rules and syntax may vary.

**Do not place `@Component` on a record expecting constructor binding to behave like `@ConfigurationPropertiesScan` registration.** Constructors on beans created through normal component scanning belong to Spring dependency injection. Constructor binding for configuration properties requires a registration mechanism supported by Boot for that model.

### 7.3. Comparison Table

| Criterion | `@Component` + JavaBean | `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` + Constructor Binding |
| --- | --- | --- |
| Registration method | Spring component scanning | Boot's configuration properties registration mechanism |
| Object instantiation | Spring container instantiates bean | Binder/Boot instantiates object via suitable constructor |
| Field updates | Typically via setters | Typically via constructor parameters |
| Mutability | Easy mutable beans | Suitable for records or immutable classes |
| Scan scope | Follows `@ComponentScan` | Follows configuration properties scan or class list |
| Best suited for | JavaBeans with getters/setters, simple app config | Immutable config, required fields via constructor |
| Risk | Public setters could be called unintentionally | Requires proper registration and clear constructor design |

Pick one consistent mechanism per class; avoid attempting to use both models to register the same configuration group.

## 8. When to Use `@EnableConfigurationProperties`?

You can omit `@Component` and register a JavaBean class explicitly:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host;
    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }
}
~~~

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MailProperties.class)
public class MailConfiguration {
}
~~~

`@EnableConfigurationProperties(MailProperties.class)` instructs Boot to register the configuration properties bean. This is helpful when:

- the class sits outside the application's component scan scope;
- you want the list of registered configuration classes stated clearly on a configuration class;
- building a starter/auto-configuration or module that must intentionally enable a group of settings;
- you want to use constructor binding on an eligible class.

**Do not use both `@Component` and `@EnableConfigurationProperties` for the same class.** Combining registration mechanisms can create two configuration beans of the same type with different names, causing ambiguous type-based injection or duplicate binding. When troubleshooting this, inspect bean definitions and remove duplicate registration.

## 9. When to Use `@ConfigurationPropertiesScan`?

If a project has many configuration classes and you want automatic registration by annotation:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
}
~~~

With classes:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    // JavaBean or record depending on binding model.
}
~~~

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(String endpoint, int retries) {
}
~~~

This avoids adding `@Component` to every configuration properties class.

When `@ConfigurationPropertiesScan` is placed without arguments, its search scope typically starts from the annotated class's package and its subpackages. You can supply `basePackages` or `basePackageClasses` when expanding scope is needed.

**Do not confuse the two scan types:**

- `@ComponentScan` finds Spring components such as `@Component`, `@Service`, `@Repository`, `@Controller`.
- `@ConfigurationPropertiesScan` finds `@ConfigurationProperties` classes matching Boot's dedicated scanning rules, and does not replace component scanning for stereotyped component classes.

Therefore, if you choose `@Component` + JavaBean, the most concise setup is usually placing the class under `@SpringBootApplication`'s root package.

## 10. `@Bean` + `@ConfigurationProperties`: Another Option

When you need to bind onto a third-party library object whose source you cannot edit to add annotations, you can place `@ConfigurationProperties` on a `@Bean` method:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClientOptionsConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.third-party")
    public ThirdPartyClientOptions thirdPartyOptions() {
        return new ThirdPartyClientOptions();
    }
}
~~~

This example assumes the library provides a `ThirdPartyClientOptions` class with suitable JavaBean setters. Boot binds `app.third-party.*` properties onto the object returned from `@Bean`.

This is JavaBean-style binding on a bean created by Spring; it **does not turn that object into constructor-bound configuration properties**. The pattern fits when you do not own the class source or must instantiate the object via a factory method.

Compared to `@Component`, `@Bean` gives explicit control over object construction, though it is more verbose for a simple application-owned configuration JavaBean.

## 11. Relaxed Binding in JavaBeans

Spring Boot Binder supports multiple property name variants, allowing configuration from different sources to map onto Java field names.

Suppose the class has:

~~~java
private Duration connectTimeout;

public Duration getConnectTimeout() {
    return connectTimeout;
}

public void setConnectTimeout(Duration connectTimeout) {
    this.connectTimeout = connectTimeout;
}
~~~

A canonical key in a file is:

~~~properties
app.mail.connect-timeout=3s
~~~

In YAML:

~~~yaml
app:
  mail:
    connect-timeout: 3s
~~~

When setting an environment variable, the name following Boot's canonical rule can be:

~~~text
APP_MAIL_CONNECTTIMEOUT=5s
~~~

For the canonical name `app.mail.connect-timeout`, the rule to convert to an environment variable typically replaces dots with underscores, strips dashes, and converts to uppercase. Avoid assuming that inserting underscores between every word works identically in all situations.

The Binder can convert many common types, for example:

- `String` from strings.
- `int`, `long`, or numeric wrappers from valid values.
- `boolean` from supported boolean representations.
- `Duration` from `3s`, `500ms`, `2m`.
- `DataSize` from supported data size units.
- `URI`, `URL`, and other types via the conversion service.
- `List`, `Map`, and nested JavaBeans when the source structure matches.

Not every string converts successfully. If `app.mail.port=not-a-number` is bound to an `int`, startup can fail with a binding error.

## 12. Default Values in JavaBeans

A JavaBean can declare defaults directly on fields:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host = "localhost";
    private int port = 2525;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
~~~

If `app.mail.host` or `app.mail.port` is absent from configuration sources, the bean retains its initialized values. If the keys are present, the Binder sets the supplied values.

This differs from defaults in placeholders:

~~~properties
app.mail.host=${MAIL_HOST:localhost}
~~~

Here, `localhost` belongs to the file's placeholder expression. Defaults on Java fields exist only in the instantiated object.

When defaults have operational significance, decide where to place them for visibility and maintainability. For truly required values, avoid defaults that mask missing config. Combine with validation so the application refuses to start when values are missing or invalid.

### 12.1. Nulls and Primitives

An `int port` field defaults to `0` in Java if uninitialized. If `port=0` is invalid in business logic, relying on a primitive alone can let misconfiguration go undetected.

You can use `Integer port` with `@NotNull` and `@Min(1)` validation, or set a sensible default and validate the value range. The Binder cannot know which ports are valid for business logic unless the application expresses that requirement.

## 13. Validation for Configuration JavaBeans

One benefit of `@ConfigurationProperties` is validating configuration early, before the application begins real work.

Example with Spring Boot 3.x and Jakarta Bean Validation:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@Component
@Validated
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    @NotBlank
    private String host;

    @Min(1)
    @Max(65535)
    private int port = 2525;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
~~~

With:

~~~properties
app.mail.host=
app.mail.port=70000
~~~

Validation can fail startup with messages pointing to the invalid fields. To enable Bean Validation, the application needs a provider and appropriate dependency, usually `spring-boot-starter-validation`.

Benefits:

1. Detects invalid configuration during startup.
2. Keeps validity rules close to the configuration class.
3. Avoids repeating identical checks across services.
4. Documents required fields and valid ranges clearly.

### 13.1. Validating Nested Objects

If there is a child object:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

@Component
@Validated
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    @Valid
    private final Authentication authentication = new Authentication();

    public Authentication getAuthentication() {
        return authentication;
    }

    public static class Authentication {
        @NotBlank
        private String username;

        public String getUsername() { return username; }
        public void setUsername(String username) {
            this.username = username;
        }
    }
}
~~~

`@Valid` enables validation to cascade into the nested object according to Bean Validation rules. When designing sensitive settings like credentials, never put real values in source code or logs. Validation annotations verify data, not encrypt passwords.

### 13.2. Do Not Use Validation as a Bean Selection Mechanism

Validation on `@ConfigurationProperties` checks the bean after it has been created and bound. It does not determine whether a `@Component` is scanned. To make a bean exist only under a profile, use `@Profile` or bean creation conditions; to keep the bean always present while enforcing valid values, use validation.

## 14. Initialization Order and Binding Timing

In a typical Spring Boot application, the general sequence is:

1. Boot prepares `Environment` and appropriate Config Data sources.
2. Spring container determines bean definitions from component scanning and configuration classes.
3. Container instantiates the `MailProperties` bean.
4. Configuration properties binding sets properties under prefix `app.mail` onto the object.
5. Validation runs if properly configured.
6. The bean can be injected into other components to consume the bound values.

This is a high-level model; lifecycle details and `BeanPostProcessor` ordering can vary depending on application configuration. Code should not rely on setters being invoked in any fixed order across properties.

### 14.1. Do Not Put Business Logic Inside Setters

Avoid opening network connections, sending notifications, or updating databases inside a configuration property setter:

~~~java
public void setHost(String host) {
    this.host = host;
    // Do not open connections or perform side-effect operations here.
}
~~~

Setters should only update data. Logic using configuration belongs in services or factory beans initialized after configuration is valid. This separates the binding phase from side effects.

### 14.2. Do Not Treat Mutable JavaBeans as Auto-Refreshing Configuration

After startup, a JavaBean bean remains an ordinary Java object. Having setters does not mean Spring Boot automatically invokes them whenever a file or environment variable changes.

For example, editing `app.mail.host` in a file outside the JAR while the process is running **does not automatically** update `MailProperties.host`. Normally a restart or a separately designed refresh mechanism is required.

If the application intentionally calls a setter at runtime, that mutates bean state; other components may observe the new value, but consistency and concurrency must be managed. For stable configuration, avoid letting services arbitrarily mutate active configuration beans.

## 15. Scope of Application in Multi-Module Projects

Example of a multi-module project:

~~~text
orders-app/
  com.example.orders.OrdersApplication

orders-core/
  com.example.orders.core.OrderService

shared-config/
  com.example.shared.config.MailProperties
~~~

Adding the `shared-config` dependency to the classpath **does not guarantee** `MailProperties` is component-scanned if its package falls outside `OrdersApplication`'s scope.

Options:

- Place the application class in a parent package covering the relevant packages when layout allows.
- Specify `scanBasePackageClasses` / `scanBasePackages` on `@SpringBootApplication` if you genuinely want to expand component scanning.
- Remove `@Component` and register `MailProperties` explicitly via `@EnableConfigurationProperties`.
- Use `@ConfigurationPropertiesScan` on the package containing classes without `@Component`.

When building a reusable Spring Boot starter across multiple applications, registering configuration properties via auto-configuration and `@EnableConfigurationProperties` is usually clearer than expecting consuming apps to pick up starter packages via default component scanning.

### 15.1. Scope of `@SpringBootApplication(scanBasePackages=...)`

Setting `scanBasePackages` primarily controls **component scanning**. It does not automatically widen every other mechanism such as JPA entity scanning or repository scanning. Therefore, when changing package layouts, do not assume every subsystem expands its scan scope under the same annotation.

### 15.2. Avoid Widening Scan Too Broadly Just to Find One Class

If you configure:

~~~java
@SpringBootApplication(scanBasePackages = "com")
~~~

the application can pick up unintended components from third-party libraries or other modules sharing that namespace. This causes duplicate bean errors, circular dependencies, or instantiating unwanted components.

Choose small, intentional package boundaries, or use explicit registration for configuration classes.

## 16. Cases Where `@Component` Should Not Be Used

### 16.1. Wanting Immutable Configuration Properties

If you require immutable data after initialization, a record or constructor-bound class registered via `@ConfigurationPropertiesScan` / `@EnableConfigurationProperties` is usually more appropriate.

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String host, int port) {
}
~~~

Using constructor binding properly reduces the surface for mutating objects after initialization. Do not mix it with `@Component` just to have the bean discovered automatically.

### 16.2. Configuration Class Comes from an Uneditable Library

If you do not own the class, you cannot add `@Component` and `@ConfigurationProperties` to it. Using `@Bean` with `@ConfigurationProperties` can bind a library JavaBean.

### 16.3. Conditional Registration Needed in Auto-Configuration

In starters or auto-configuration, consider `@EnableConfigurationProperties` paired with intentional conditions. An unscoped scanned `@Component` could create beans in applications where that feature is not meant to be enabled.

### 16.4. Only a Single Simple Property Is Needed

When a bean needs just one small value and does not form a configuration group, `@Value("${app.feature.enabled:false}")` may suffice. However, as the property group grows, switching to `@ConfigurationProperties` provides clearer structure.

## 17. Common Errors and How to Fix Them

### Error 1: Has `@ConfigurationProperties`, but No Bean

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    // No @Component, not scanned, not enabled.
}
~~~

**Symptom:** injecting `MailProperties` fails with no qualifying bean.

**Fix:** choose one registration mechanism: add `@Component` in a component-scanned package, register with `@EnableConfigurationProperties`, or use `@ConfigurationPropertiesScan`.

### Error 2: `@Component` Outside the Scanned Package

~~~text
com.example.orders.OrdersApplication
com.example.external.config.MailProperties
~~~

**Symptom:** annotations are valid, yet the bean is missing.

**Fix:** check the root package, component scan settings, and filters; if you only need one configuration properties bean, consider explicit registration.

### Error 3: Using a Record with `@Component` and Expecting Boot to Constructor-Bind

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String host, int port) {
}
~~~

**Symptom:** Spring tries to resolve constructor parameters as normal bean dependencies, or bean creation behaves unexpectedly.

**Fix:** remove `@Component`, and register the record using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` in a supported Spring Boot version.

### Error 4: Missing Setter for Scalar

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    private String host;
    public String getHost() { return host; }
}
~~~

**Symptom:** `host` is not bound via JavaBean setter as expected.

**Fix:** add an appropriate setter or switch to constructor binding if immutable config is desired.

### Error 5: Registering the Same Class via Multiple Mechanisms

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
}
~~~

and simultaneously:

~~~java
@EnableConfigurationProperties(MailProperties.class)
~~~

**Symptom:** multiple beans of the same type may appear, causing ambiguous injection.

**Fix:** pick one registration mechanism; if using component scanning, do not also enable the same class.

### Error 6: Using `@ConfigurationPropertiesScan` While the Class Still Has `@Component`

**Symptom:** the class is not discovered via configuration-properties scanning as expected.

**Fix:** understand that `@ConfigurationPropertiesScan` does not register `@Component` classes; remove `@Component` to use that mechanism, or ensure normal component scanning finds the class.

### Error 7: Mismatched Prefix or Property Name

~~~java
@ConfigurationProperties(prefix = "app.mail")
~~~

but the file contains:

~~~properties
app.email.host=smtp.example.test
~~~

**Symptom:** the bean is created, yet fields retain defaults or null.

**Fix:** use the exact `app.mail.host`, check relaxed binding, and inspect which property sources Boot actually loaded.

### Error 8: Reading the Bean Too Early or Instantiating with `new`

~~~java
MailProperties properties = new MailProperties();
~~~

That object is not managed by the Spring container, so Boot does not automatically bind it merely because the class has the annotation. Use constructor injection of the registered bean, or use the explicit Binder API when constructing objects outside the context.

### Error 9: Adding `@Scope("prototype")` and Expecting Singleton Behavior

`@Component` defaults to singleton, though Spring permits other scopes. Setting a non-default scope changes bean creation timing and instance count, so services no longer share the same configuration instance as in singleton examples.

Only change scope when genuinely required; configuration properties are normally used as stable context-wide configuration beans.

### Error 10: Missing Bean Validation Provider

When using `@Validated` and Jakarta constraints without a Bean Validation provider on the classpath, validation may not work as expected or fail. Include the dependency matching your Boot version, typically `spring-boot-starter-validation`.

## 18. Testing Component Scanning and Binding

A Spring Boot integration test can verify that the bean is registered and receives the expected values.

Suppose `MailProperties` in the `app.mail` example has `@Component`, getters/setters, and sits inside the application class's scan scope:

~~~java
import com.example.orders.config.MailProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(properties = {
    "app.mail.host=mail.test.example",
    "app.mail.port=2526",
    "app.mail.connect-timeout=750ms"
})
class MailPropertiesTest {

    @Autowired
    MailProperties properties;

    @Test
    void bindsProperties() {
        assertNotNull(properties);
        assertEquals("mail.test.example", properties.getHost());
        assertEquals(2526, properties.getPort());
        assertEquals(java.time.Duration.ofMillis(750),
                     properties.getConnectTimeout());
    }
}
~~~

Appropriate Spring Boot Test and JUnit dependencies are required. Because the test uses a Spring application context, it also depends on whether `MailProperties`'s package is scanned.

### 18.1. Testing When the Bean Is Not Scanned

If `MailProperties` is moved outside component scan scope, the context cannot inject the bean. That indicates you need to inspect scan scope and bean registration, not that the Binder fails to understand `app.mail.host`.

### 18.2. Testing Validation

When `@Validated` and constraints are enabled, you can supply missing or invalid values to verify startup fails immediately. Exception types may be wrapped across multiple layers by Spring Boot; in tests, check messages and root causes matching the configuration field rather than relying on one exact message string across all versions.

### 18.3. Binding Tests and Business Tests Are Two Separate Things

Testing `MailProperties` proves registration and binding work. Testing actual SMTP connections or sending emails requires separate tests, because a successfully bound URL or port does not guarantee the external system is reachable.

## 19. Diagnostic Procedure When a Bean Does Not Receive Values

When a `@Component` + `@ConfigurationProperties` bean receives null or unexpected defaults, check in sequence:

1. **Check whether the bean exists.** If injection reports a missing bean, inspect component scanning first; do not rush to edit YAML.
2. **Check packages.** Where is the application class? Is the properties class in a scanned package? Are there filters or `@Profile` conditions?
3. **Check annotations.** Are both `@Component` and `@ConfigurationProperties(prefix = "...")` present in the JavaBean model?
4. **Check the JavaBean class.** Does it have a suitable constructor, getters/setters for scalars, and proper nested object setup?
5. **Check the prefix.** Does `app.mail` match the prefix in files and environment variables?
6. **Check source data.** Was `application.properties`/YAML actually loaded? Are profiles or location overrides changing sources?
7. **Check precedence.** Are environment variables, JVM system properties, or command-line arguments overriding the file?
8. **Check relaxed binding names.** For `connectTimeout`, use `connect-timeout` in files and the standard convention in env vars.
9. **Check type conversion errors.** `Duration` requires valid values like `750ms`, `5s`; ports must parse as numbers.
10. **Check validation.** With `@NotBlank`/`@Min`, binding/validation errors can surface early during context creation.
11. **Check duplicate registration.** Are `@Component`, `@EnableConfigurationProperties`, and `@Bean` of the same type mixed?
12. **Check timing.** Instances created with `new` or used outside the Spring context are not automatically bound by the binder.
13. **Check runtime edits.** Editing files while the app is running does not automatically update beans.
14. **Inspect safely.** If using Actuator `/actuator/configprops` or `/actuator/env`, secure the endpoints and mask sensitive values.

For projects with many settings, the `spring-boot-configuration-processor` annotation processor can generate IDE metadata and key autocomplete. This processor **does not replace** `@Component`, `@EnableConfigurationProperties`, or the runtime binder.

## 20. Distinguishing the Different "Scopes" of Application

When asking "Within what scope does `@Component` register a JavaBean?", there are at least four scopes to distinguish:

| Scope | What Determines It? | Meaning |
| --- | --- | --- |
| **Component scan** scope | Location of `@SpringBootApplication`, `@ComponentScan`, packages, and filters | Whether Spring discovers the class to create a bean |
| **Prefix binding** scope | `@ConfigurationProperties(prefix="app.mail")` | Which group of configuration keys maps into the object |
| **Bean** scope | Defaults to singleton; `@Scope` if changed | How many instances exist and their lifecycle in a context |
| **Config Data** scope | File locations, profiles, imports, property-source precedence | Where final values come from and whether they are loaded |

An error in any one of these scopes can prevent configuration from working as expected. For example:

- Not scanned: **no bean**.
- Bean exists, wrong prefix: **bean exists, but receives wrong or missing values**.
- Right prefix, overridden by another source: **bean holds a different value from the file you are viewing**.
- Altered scope: **services may receive different instances**.
- Config Data edited after startup: **existing bean does not update automatically**.

Separating these four questions enables systematic debugging instead of adding annotations blindly.

## 21. Guide to Choosing a Registration Mechanism

| Requirement | Suitable Approach |
| --- | --- |
| Small app, JavaBean with setters, class inside component scan | `@Component` + `@ConfigurationProperties` |
| Want JavaBean registered even outside component scan | `@EnableConfigurationProperties` |
| Many properties classes that are not Spring components | `@ConfigurationPropertiesScan` |
| Want immutable record or constructor binding | `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, without `@Component` |
| Want to bind a third-party library class | `@Bean` + `@ConfigurationProperties` |
| Need bean only in a specific profile | Combine bean registration conditions, e.g., `@Profile` |
| Want data validated at startup | `@Validated` and appropriate Bean Validation |
| Only need one simple key | `@Value` may suffice; revisit if the config group grows |

No single mechanism fits every situation. For the focus of this lesson, the core pattern is **a mutable JavaBean with `@Component`, discovered by component scanning, with properties bound by prefix via the Binder**.

## 22. Key Takeaways

1. `@Component` registers a Spring bean when the class falls within **component scan scope**.
2. `@ConfigurationProperties(prefix = "...")` declares the **property group** mapped onto the bean by the Binder.
3. For beans created via `@Component`, **JavaBean binding** is the matching model: a no-arg constructor and clear getters/setters for scalar fields.
4. Pre-initialized nested mutable objects can be bound via getters; do not assume every `final` field can be bound like a setter.
5. Component scanning and configuration-properties scanning are **two separate mechanisms**; `@ConfigurationPropertiesScan` does not register `@Component` classes through its own dedicated scan.
6. Do not use `@Component` expecting constructor binding onto records or immutable classes.
7. Do not combine `@Component` with `@EnableConfigurationProperties` just to re-register the same class.
8. Prefix binding, component scan, bean scope, and property-source precedence are four distinct scopes of influence.
9. `@Validated` catches invalid configuration but requires a Bean Validation provider; `@ConfigurationProperties` does not validate strings by itself.
10. Configuration beans are singleton by default within an application context and normally do not auto-refresh when files change.

### References

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Enabling Configuration-annotated Types](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
