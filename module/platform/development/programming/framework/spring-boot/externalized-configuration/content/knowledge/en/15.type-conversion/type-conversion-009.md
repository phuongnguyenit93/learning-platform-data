# Impact of a Bean Named conversionService and How to Avoid Unintended Changes

In Spring Boot, converting a string from `application.properties`, YAML, environment variables, or command-line arguments into `Duration`, `DataSize`, `URI`, enums, or application-defined types typically happens during `@ConfigurationProperties` **binding**. Spring Boot already supplies default converters for a wide range of common data types.

When adding custom conversion logic, you may run into a crucial detail: **a bean named `conversionService` specifically carries special meaning in Spring Boot's configuration property conversion mechanism**. Such a bean can be requested **very early in the startup lifecycle** and can change how properties are coerced. Consequently, adding a `ConversionService` bean and inadvertently naming it `conversionService` is not a harmless choice.

This lesson distinguishes the conversion mechanisms of Spring Framework and the Spring Boot Binder, explains the impact of the bean name, early initialization scenarios, the consequences of losing built-in converters, using `@ConfigurationPropertiesBinding` instead of altering the global converter registry, renaming business-only services, and verifying that configuration is unaffected by unintended changes.

Java examples follow Spring Boot 3.x and Java 17+.

## 1. Concepts Before Writing Code

| Component | Role |
| --- | --- |
| `Environment` | Supplies effective key/value pairs from multiple `PropertySource`s |
| `@ConfigurationProperties` | Defines a group of properties to bind into a Java class/record |
| Spring Boot `Binder` | Maps key names and converts values to target types |
| `ConversionService` | Spring Framework's type conversion interface |
| `ApplicationConversionService` | Spring Boot's implementation including common application conversion/formatting support |
| Bean named `conversionService` | A bean name recognized by Spring Boot when a `ConversionService` is needed for configuration properties |
| `@ConfigurationPropertiesBinding` | Qualifier for converters/formatters applied in configuration properties binding |
| Business converter with its own name | Used only where the application explicitly injects or calls it |

One key takeaway:

> **If you only need to convert a type for `@ConfigurationProperties`, prefer a converter annotated with `@ConfigurationPropertiesBinding`. If a `ConversionService` serves only business logic, do not accidentally name the bean `conversionService`.**

The bean name is a core part of this mechanism. You cannot look solely at a bean's Java type and conclude whether Spring Boot will or will not use it during binding.

## 2. Binding Flow and the Role of ConversionService

~~~text
application.yml / application.properties
          |
          +-- environment variables
          +-- JVM system properties (-D...)
          +-- command-line arguments (--...)
          +-- profile-specific Config Data
          |
          v
      Environment
          |
          v
      Boot Binder
          |
          +--> find properties by prefix and relaxed binding
          |
          +--> convert source String / value to Java type
                  |
                  +-- default converters (String -> Duration, DataSize, ...)
                  |
                  +-- dedicated @ConfigurationPropertiesBinding converter
                  |
                  +-- custom ConversionService used for binding,
                      if provided by the application per Spring Boot rules
          |
          v
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout, URI endpoint) {}
          |
          v
Business bean receives typed configuration
~~~

Example file:

~~~yaml
app:
  client:
    connect-timeout: 750ms
    endpoint: https://api.example.test
    max-retries: 3
~~~

Model:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    Duration connectTimeout,
    URI endpoint,
    int maxRetries
) {}
~~~

When the bean is properly registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, the binder can convert `750ms` to `Duration`, the URL string to `URI`, and `3` to `int`.

**Usually there is no need to define a `conversionService` bean to perform these conversions.** Spring Boot includes built-in application and configuration property type conversion.

## 3. What Is Special About the Bean Name conversionService?

Spring Framework identifies beans by name and type in different contexts. For Spring Boot configuration properties, the official documentation notes the option of providing **a `ConversionService` bean named `conversionService`** to customize property conversion.

The following configuration example intentionally defines a bean with that significant name:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

@Configuration(proxyBeanMethods = false)
public class ConversionConfiguration {

    @Bean
    ConversionService conversionService() {
        return new DefaultConversionService();
    }
}
~~~

With `@Bean` specifying no explicit name, the default bean name comes from the method name: here, **`conversionService`**. This name is not an arbitrary label to the configuration conversion infrastructure.

The `DefaultConversionService` bean in this example illustrates a hazard; it is **not the recommended pattern when you only want to add a small conversion**. It does not automatically carry the full set of specialized converters and formatters provided by Spring Boot's `ApplicationConversionService`.

### Not Every ConversionService Bean Is Used the Same Way

These two declarations differ in naming:

~~~java
@Bean
ConversionService conversionService() {
    return new DefaultConversionService();
}
~~~

~~~java
@Bean
ConversionService reportConversionService() {
    return new DefaultConversionService();
}
~~~

The first bean gets the default name `conversionService`; the second gets `reportConversionService`. If a component merely needs its own conversion service for reports and injects the second bean explicitly, renaming avoids colliding with the special infrastructure name.

**Renaming does not isolate a bean from every Spring mechanism completely.** If you mark it `@Primary`, inject by type elsewhere, or another component explicitly retrieves it, it can still affect those places. The first thing to avoid is **accidentally participating in the binder's `ConversionService` lookup via the special name**.

## 4. First Impact: Altering Conversion Used When Binding Configuration Properties

Suppose an application has several configuration groups:

~~~properties
app.client.connect-timeout=2s
app.upload.max-file-size=10MB
app.payment.currency=USD
app.worker.retry-delay=250ms
~~~

Typed models:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration connectTimeout) {}

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(DataSize maxFileSize) {}

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(Duration retryDelay) {}
~~~

`Duration` and `DataSize` are converted by Spring Boot out of the box in `@ConfigurationProperties`. If the application customizes the conversion service too broadly and accidentally replaces or drops needed converters, properties that previously bound cleanly can start failing.

Example error messages may look like:

~~~text
Failed to bind properties under 'app.client.connect-timeout'
to java.time.Duration
~~~

Or:

~~~text
Failed to convert from type [java.lang.String]
to type [org.springframework.util.unit.DataSize]
~~~

**Not every binding error like the above is caused by the `conversionService` name.** They can also result from malformed values, conflicting sources, constructor binding issues, or converter exceptions. However, when failures appear right after changing a `ConversionService` bean, check the bean name and registered converters.

### Type Conversion Does Not Alter Precedence

If a property appears in both YAML and on the command line:

~~~properties
# application.properties
app.client.connect-timeout=3s
~~~

~~~bash
java -jar app.jar --app.client.connect-timeout=500ms
~~~

Spring Boot's property source mechanism decides the effective value by precedence. `ConversionService` only **converts the chosen value to the target type**. It does not decide which source overrides another.

Do not try to fix property overrides by modifying `ConversionService`, and do not expect a new converter to alter which profile is active.

## 5. Second Impact: The Bean Is Requested Very Early

A warning in Spring Boot's documentation is that **beans used for property conversion may be requested very early in the application lifecycle**. That is when the `ApplicationContext` is setting up the infrastructure needed to instantiate subsequent beans.

Now imagine a `conversionService` that depends on too many things:

~~~java
@Configuration(proxyBeanMethods = false)
public class RiskyConfiguration {

    @Bean
    ConversionService conversionService(
        RemoteCatalogClient remoteCatalogClient,
        TenantRepository tenantRepository,
        ClientProperties clientProperties
    ) {
        // Example carrying the risk of depending on other beans and
        // @ConfigurationProperties right during binding preparation.
        var service = new DefaultConversionService();
        return service;
    }
}
~~~

This is an **anti-pattern to avoid**, not an implementation guide. To build `ConversionService`, Spring has to instantiate those dependencies. Meanwhile, `ClientProperties` itself may need the binder and `ConversionService` in order to initialize. The outcome can be a circular dependency, unintended early bean instantiation, or a component not being processed by all expected `BeanPostProcessor`s.

Even without a direct cycle, calling databases, HTTP services, caches, or complex business configuration inside a `conversionService` factory method is an unnecessary risk.

### Signs of Early Initialization Problems

- Startup fails with missing-bean or circular-dependency errors, even though those dependencies work fine elsewhere.
- Logs show warnings that a bean **is not eligible for getting processed by all `BeanPostProcessor`s**.
- Features relying on proxies, annotations, or auto-configuration behave differently after adding a custom converter.
- Errors happen very early, before your business services initialize.
- Failures only occur on startup runs with custom conversion enabled.

These signs alone are not definitive proof; read the actual stack trace and dependency chain.

## 6. Third Impact: Conversion Scope May Be Broader Than Intended

An application may need a dedicated converter for formatting reports, yet inadvertently create a globally named bean. For example, one module only wants to convert `String -> ReportStatus`:

~~~java
public enum ReportStatus {
    NEW, RUNNING, DONE
}
~~~

You might define a dedicated `ConversionService` to convert report values in code. However, if that bean is named `conversionService`, infrastructure can recognize it to serve configuration property conversion as well.

Unintended scope expansion can show up as:

- Other `@ConfigurationProperties` beans begin receiving new conversion behavior or fail due to missing built-in converters.
- Components looking up the `conversionService` bean by name also inherit the new behavior.
- Other Spring mechanisms may interact with the `ConversionService` bean added to the context, depending on the subsystem and configuration.

To state this precisely: **merely having a `conversionService` bean does not mean every conversion in MVC, JSON, databases, and all libraries instantly switches to it**. Those systems may maintain their own converter registries and configuration hooks. The specific risk to evaluate is **which beans consume that `ConversionService`**; for Spring Boot property binding, the name `conversionService` is a critical signal.

### Comparing a Single Converter vs. a Global Registry

| What You Want to Customize | What You Should Touch |
| --- | --- |
| Converting one type in `@ConfigurationProperties` | A converter qualified with `@ConfigurationPropertiesBinding` |
| Converting data per custom rules in one service | A converter or differently named `ConversionService`, explicitly injected |
| Converting Spring MVC input fields | MVC `Formatter`/`Converter` registration (e.g., `WebMvcConfigurer#addFormatters`) |
| Converting JSON | Jackson serialization/deserialization configuration |
| Changing type conversion policy across many configuration properties | Carefully designed, tested `ConversionService` for binding |
| Changing which value wins across YAML/profiles | Config Data/`PropertySource` precedence, not converters |

## 7. The Common Safe Approach: @ConfigurationPropertiesBinding

If you only need a custom conversion for configuration properties, register **a specific converter** with the `@ConfigurationPropertiesBinding` qualifier instead of replacing the entire registry.

Suppose configuration includes a region code like `ap-southeast-1` and the application wants a dedicated type:

~~~properties
app.routing.default-region=ap-southeast-1
~~~

Value object:

~~~java
package com.example.orders.config;

public record RegionCode(String value) {
    public RegionCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "RegionCode must not be blank");
        }
    }
}
~~~

A separate converter:

~~~java
package com.example.orders.config;

import org.springframework.core.convert.converter.Converter;

public final class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(source.trim());
    }
}
~~~

Registering the converter for configuration properties:

~~~java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class RegionBindingConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    public static Converter<String, RegionCode>
            regionCodeConfigurationConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

In this example, `RegionBindingConfiguration` must actually be processed by Spring—for example by residing within the application's component-scan scope or being imported by another configuration.

Bindable record:

~~~java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(
    RegionCode defaultRegion
) {}
~~~

When `RoutingProperties` is properly scanned or enabled, the binder can use the dedicated converter to construct `RegionCode` from `"ap-southeast-1"`.

### Why Is This Approach Better Scoped?

`@ConfigurationPropertiesBinding` marks the converter **specifically for binding configuration properties**. You do not have to introduce a new application-wide `conversionService` conversion registry into the context. Default converters continue working for other types via Spring Boot's standard mechanism.

When a converter only concerns `RegionCode`, keeping the logic in `Converter<String, RegionCode>` also makes the scope of the change much clearer than customizing a general-purpose registry.

### The Qualifier Does Not Restrict the Converter to One Key

A `Converter<String, RegionCode>` can be used at **every configuration properties location needing `String` to `RegionCode`**, not just `app.routing.default-region`. If you want different semantics for the same Java type on different property paths, design distinct types or explicit contracts; do not assume the converter knows which key originated the value.

## 8. Why Should @Bean @ConfigurationPropertiesBinding Be static?

Spring Boot documentation recommends that **`@Bean` methods annotated with `@ConfigurationPropertiesBinding` be `static`**, to avoid warnings about beans initialized too early before all `BeanPostProcessor`s have been registered.

Recommended example:

~~~java
@Configuration(proxyBeanMethods = false)
public class BindingConverters {

    @Bean
    @ConfigurationPropertiesBinding
    public static Converter<String, RegionCode>
            regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

Here `static` applies to the **converter bean's factory method**. It does not mean the `RegionCode` record, `StringToRegionCodeConverter` class, or every method in the application has to be `static`.

### Example Likely to Trigger Warnings

~~~java
@Configuration(proxyBeanMethods = false)
public class BindingConverters {

    private final TenantService tenantService;

    public BindingConverters(TenantService tenantService) {
        this.tenantService = tenantService;
    }

    @Bean
    @ConfigurationPropertiesBinding
    public Converter<String, RegionCode> regionCodeConverter() {
        return value -> tenantService.resolveRegion(value);
    }
}
~~~

This is a **risky** example. Because the factory method is an instance method, `BindingConverters` must be instantiated along with `TenantService`. Binding converters are requested early, making the bean-creation path complex or triggering warnings.

The safer pattern is **keeping the converter pure with no application dependencies** and registering it via a static factory method:

~~~java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, RegionCode> regionCodeConverter() {
    return source -> new RegionCode(source.trim());
}
~~~

When conversion work genuinely requires calling an API or repository, re-examine the boundary of responsibilities: configuration binding should parse and validate values; business queries or data enrichment should happen in a service initialized after configuration is ready.

## 9. Complete YAML and Java Example Without Replacing conversionService

Suppose we want to bind a list of configured endpoints, where each endpoint has a custom `RegionCode` and a standard Boot `Duration`:

~~~yaml
app:
  routing:
    endpoints:
      - name: primary
        region: ap-southeast-1
        url: https://primary.example.test
        timeout: 500ms
      - name: backup
        region: eu-west-1
        url: https://backup.example.test
        timeout: 2s
~~~

Model:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(
    List<Endpoint> endpoints
) {
    public record Endpoint(
        String name,
        RegionCode region,
        URI url,
        Duration timeout
    ) {}
}
~~~

The dedicated `StringToRegionCodeConverter` and `RegionBindingConfiguration` remain the same as in the previous section.

Main class:

~~~java
package com.example.orders;

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

Consumer:

~~~java
package com.example.orders.service;

import com.example.orders.config.RoutingProperties;
import org.springframework.stereotype.Service;

@Service
public class RoutingService {
    private final RoutingProperties properties;

    public RoutingService(RoutingProperties properties) {
        this.properties = properties;
    }

    public void printEndpointRegions() {
        for (var endpoint : properties.endpoints()) {
            System.out.println(
                endpoint.name() + ": " + endpoint.region().value());
        }
    }
}
~~~

When these beans fall within scan/registration scope, the binder uses the custom converter for `RegionCode` and the appropriate default converters for `Duration` and `URI`. There is no need to create a bean named `conversionService` just for a `RegionCode` field.

### Why Is This Example Notable?

The application uses **both built-in conversion and custom conversion inside the same object**:

- `String -> RegionCode`: custom converter for configuration binding.
- `"500ms"`/`"2s"` strings to `Duration`: Boot's built-in conversion.
- URL strings to `URI`: framework conversion.

Adding a small converter does not require replacing the entire conversion registry. This keeps the blast radius narrow.

## 10. When Should You Consider a Bean Named conversionService?

There are cases where an application needs **full control over a `ConversionService` used for property conversion**: registering many converters and formatters under a centralized policy, altering well-defined conversion behavior, or providing an internal framework managing the conversion model.

In such cases, supplying a bean named `conversionService` can be valid. Before doing so, clearly answer:

1. **Why** can't dedicated converters/formatters solve the problem?
2. Which **subsystems** will consume the bean?
3. Which **common Spring Boot converters** must be preserved?
4. Does the bean have **early initialization dependencies** on other services or properties beans?
5. Are there tests ensuring `Duration`, `DataSize`, enums, collections, and other typed properties are not broken?
6. Are the bean name and registration treated as an operational API decision rather than a temporary implementation detail?

An illustrative setup when intentionally customizing conversion for application properties:

~~~java
import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.support.ConfigurableConversionService;

@Configuration(proxyBeanMethods = false)
public class BroadConversionConfiguration {

    @Bean(name = "conversionService")
    public static ConfigurableConversionService conversionService() {
        ApplicationConversionService service =
            new ApplicationConversionService();

        service.addConverter(new StringToRegionCodeConverter());
        return service;
    }
}
~~~

This pattern is **only appropriate when you intentionally want to provide the registry named `conversionService`**. It builds on `ApplicationConversionService` to retain Spring Boot's common application converters/formatters, then adds the desired converter. If the whole requirement is just `RegionCode` inside `@ConfigurationProperties`, stick with `@ConfigurationPropertiesBinding` from earlier.

Not every application class should arbitrarily add converters to a shared `ConversionService`. In large systems, assign clear ownership of the `conversionService` bean to a specific module to prevent duplicate definitions or cross-module behavioral drift.

## 11. Difference Between DefaultConversionService and ApplicationConversionService

An important technical distinction:

~~~java
new DefaultConversionService()
~~~

and:

~~~java
new ApplicationConversionService()
~~~

do not share the exact same goal.

`DefaultConversionService` is Spring Framework's baseline implementation providing common framework converters. Spring Boot's `ApplicationConversionService` builds on it and adds conversion/formatting support used by Spring Boot in application contexts.

For example, Boot commonly supports configurations like:

~~~properties
app.retry.delay=250ms
app.upload.max-size=10MB
~~~

bound to:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(Duration delay) {}

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(DataSize maxSize) {}
~~~

If you build an overly bare `ConversionService` and hand it to the conversion infrastructure, you risk losing conversions the app depends on. Never replace the registry just to add one unrelated converter.

### Does This Mean DefaultConversionService Is Always Wrong?

No. It remains useful across many Spring Framework components and can be entirely appropriate for a **private** business conversion service. The issue is **usage context and bean name**—not that `DefaultConversionService` is a forbidden class.

A manually used reporting registry can still be completely valid:

~~~java
@Bean("reportConversionService")
ConversionService reportConversionService() {
    return new DefaultConversionService();
}
~~~

If you only need a small converter, injecting `Converter<A,B>` directly into the service may be even simpler than creating an entire registry.

## 12. Renaming the Bean to Avoid Participating in Configuration Binding

Suppose you need a conversion service for data inside a reporting module, and you do not want this bean to influence `@ConfigurationProperties`. Instead of:

~~~java
@Bean
ConversionService conversionService() {
    return new DefaultConversionService();
}
~~~

give it a descriptive name:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

@Configuration(proxyBeanMethods = false)
public class ReportConversionConfiguration {

    @Bean("reportConversionService")
    ConversionService reportConversionService() {
        return new DefaultConversionService();
    }
}
~~~

Consumer injects the bean explicitly:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.convert.ConversionService;
import org.springframework.stereotype.Service;

@Service
public class ReportValueMapper {
    private final ConversionService conversions;

    public ReportValueMapper(
        @Qualifier("reportConversionService")
        ConversionService conversions
    ) {
        this.conversions = conversions;
    }

    public Integer parseInteger(String value) {
        return conversions.convert(value, Integer.class);
    }
}
~~~

The name `reportConversionService` communicates that this belongs to the reporting module's internals rather than the framework's default conversion service.

**Renaming the method alone can also change the default bean name** if `@Bean` does not specify a name. Still, writing `@Bean("reportConversionService")` makes intent explicit and less fragile during method renames.

### Do Not Use @Primary as an Isolation Mechanism

`@Primary` affects bean resolution when injecting by type. It is not a guarantee of "never used by the framework". When you want clear separation, use a distinct name and `@Qualifier`; when you want a converter solely for binding, use `@ConfigurationPropertiesBinding`.

## 13. Using @Component on a Converter

You might write:

~~~java
@Component
public class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {
    @Override
    public RegionCode convert(String value) {
        return new RegionCode(value.trim());
    }
}
~~~

Having a converter discovered by component scanning **does not automatically specify which converter registry it joins or when**. One subsystem may auto-discover `Converter` beans; another requires an explicit qualifier or registration.

If the goal is specifically configuration properties binding, the clear approach is `@ConfigurationPropertiesBinding` with the matching bean registration (such as `static @Bean`).

If the goal is MVC, register it in the proper MVC configuration. If the goal is business logic, inject the converter or use a dedicated service. **Do not just add `@Component` and assume every layer automatically adopts the new converter.**

## 14. Distinguishing Conversion in @ConfigurationProperties vs. @Value

Both can read from `Environment`, yet they do not share identical capabilities.

`@ConfigurationProperties` uses the binder with relaxed binding and configuration-oriented type conversion. `@Value` is Spring Core's injection mechanism supporting placeholders and SpEL, and is not guaranteed to use a custom converter merely because it is qualified with `@ConfigurationPropertiesBinding`.

Example:

~~~properties
app.routing.default-region=ap-southeast-1
~~~

With a dedicated converter like `StringToRegionCodeConverter`:

~~~java
@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(RegionCode defaultRegion) {}
~~~

is the primary use case.

If a component instead writes:

~~~java
@Value("\${app.routing.default-region}")
private RegionCode region;
~~~

do not assume a converter meant solely for configuration properties binding is always used by `@Value` injection. If compatibility with both is required, design conversion for the scope and mechanisms actually supported by each call path, or inject the typed `RoutingProperties` instead of scattering `@Value`.

**Easier-to-maintain pattern:** consumers inject the `RoutingProperties` bean and read `routingProperties.defaultRegion()`. That avoids two injection paths having divergent conversion behavior.

## 15. Do Not Mix Conversion with Business Logic or I/O

An ideal converter has these characteristics:

- No dependency on databases or HTTP clients.
- No network or filesystem calls on every parse.
- Does not require another `@ConfigurationProperties` bean to instantiate.
- Holds no per-request mutable state.
- Produces consistent output for valid input.
- Throws a clear exception on invalid input so bad config fails early.

Example of a pure converter:

~~~java
public final class StringToPortRangeConverter
        implements Converter<String, PortRange> {

    @Override
    public PortRange convert(String source) {
        String[] parts = source.split("-", 2);
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                "Expected start-end, e.g. 8000-8010");
        }
        int start = Integer.parseInt(parts[0].trim());
        int end = Integer.parseInt(parts[1].trim());
        if (start < 1 || end > 65535 || start > end) {
            throw new IllegalArgumentException(
                "Port range must be within 1..65535");
        }
        return new PortRange(start, end);
    }
}
~~~

This converter is self-contained on its input data. If the resulting `PortRange` needs to check tenant permissions, quotas, or cluster existence, perform that step in a service layer or dedicated validator after typed settings are ready, avoiding pulling complex lifecycle dependencies into conversion.

## 16. When to Use Formatter Instead of Converter?

`Converter<S,T>` fits when a conversion has an explicit source type and target type, such as `String -> RegionCode`. `Formatter<T>` fits scenarios needing locale-aware parsing/printing or presentation semantics.

Still, distinguish **registering a formatter in MVC** from **registering a converter for configuration properties**.

For instance, a formatter for locale-sensitive form data is typically added in Spring MVC via `WebMvcConfigurer#addFormatters`, without having to replace the `conversionService` bean for the entire `ApplicationContext`.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebFormattingConfiguration
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToRegionCodeConverter());
    }
}
~~~

This example targets **MVC conversion** when a component needs it; it does not mean this converter is registered for `@ConfigurationProperties`.

If the same conversion is required in both places, register the same implementation intentionally in both registries rather than assuming a single `conversionService` bean unifies every subsystem automatically.

## 17. Anti-Pattern: Creating ConversionService Just for One Custom Converter

Suppose a project runs fine with:

~~~yaml
app:
  retry:
    backoff: 300ms
  storage:
    quota: 50MB
~~~

Typed configs:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(Duration backoff) {}

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(DataSize quota) {}
~~~

A developer wants to add support for `RegionCode`, so they add:

~~~java
@Configuration(proxyBeanMethods = false)
public class CustomConversionConfiguration {

    @Bean("conversionService")
    ConversionService conversionService() {
        DefaultConversionService service =
            new DefaultConversionService();
        service.addConverter(new StringToRegionCodeConverter());
        return service;
    }
}
~~~

**Risk:** a bean named `conversionService` can be picked up for configuration conversion, while the implementation chosen here does not necessarily preserve all of Boot's specialized converters/formatters. Adding a single converter now has a far wider blast radius than intended.

### Preferred Fix

~~~java
@Configuration(proxyBeanMethods = false)
public class CustomConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    public static Converter<String, RegionCode> regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

After this change, you no longer provide a registry under the special bean name. The converter is declared strictly for configuration binding needs, reducing the risk of breaking unrelated typed properties.

If the entire application truly requires a custom conversion service, retain Boot's essential converters as a foundation and verify existing configuration types before rolling it out broadly.

## 18. Anti-Pattern: ConversionService Depending on a Bean Being Bound

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class ConversionConfiguration {

    @Bean("conversionService")
    ConversionService conversionService(RoutingProperties routing) {
        // routing is a configuration properties bean,
        // which may need the Binder to be constructed.
        return new DefaultConversionService();
    }
}
~~~

This dependency chain looks like:

~~~text
Initialize conversion infrastructure
      -> needs RoutingProperties
             -> needs Binder
                    -> may need conversion infrastructure
~~~

Such a startup path risks circular dependencies or unexpected bean creation ordering. Spring Boot documentation recommends **limiting `ConversionService` dependencies** because it is requested early.

**Common resolution:** pure converter, static factory method, no dependency on other typed properties. If logic requires `RoutingProperties`, run it after binding inside a business bean.

A service needing both configuration and business conversion can accept them via standard constructor injection:

~~~java
@Service
public class RoutePlanner {

    private final RoutingProperties settings;
    private final RouteCatalog catalog;

    public RoutePlanner(
        RoutingProperties settings,
        RouteCatalog catalog
    ) {
        this.settings = settings;
        this.catalog = catalog;
    }
}
~~~

`RouteCatalog` is an illustrative business type requiring a matching bean. This happens **after** typed settings have been built, not inside the factory creating conversion infrastructure.

## 19. Renaming ConversionService If Used Only in a Service

If a module currently has:

~~~java
@Bean
ConversionService conversionService() {
    return new DefaultConversionService();
}
~~~

with no intention of influencing configuration key coercion, switch it to:

~~~java
@Bean("analyticsConversionService")
ConversionService analyticsConversionService() {
    return new DefaultConversionService();
}
~~~

Where needed, inject explicitly:

~~~java
public AnalyticsImporter(
    @Qualifier("analyticsConversionService")
    ConversionService conversions
) {
    this.conversions = conversions;
}
~~~

Benefits:

- Reduces the chance `BeanFactory` picks the wrong bean just because of the default name `conversionService`.
- Separates analytics conversion from typed configuration.
- Makes it easy to trace consumers via the qualifier.
- Makes module testing straightforward against its own contract rather than testing unrelated configuration types.
- Avoids coupling an infrastructure decision to an unreviewed method name.

### Do Not Rename While Another Consumer Depends on the Old Name

If other code injects `conversionService` via `@Qualifier("conversionService")` or name lookup, renaming affects those consumers. Rename deliberately alongside updating the matching injection points. Do not treat it as a harmless refactor of an application public contract.

## 20. How to Check Whether a Bean Named conversionService Exists

In an experimental app, you can list `ConversionService` bean names from `ApplicationContext`:

~~~java
import java.util.Arrays;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;

@Configuration(proxyBeanMethods = false)
public class ConversionProbeConfiguration {

    @Bean
    CommandLineRunner showConversionBeans(
        ApplicationContext context
    ) {
        return args -> {
            String[] names =
                context.getBeanNamesForType(ConversionService.class);
            System.out.println(
                "ConversionService beans: " + Arrays.toString(names));
            System.out.println(
                "Has bean named conversionService: "
                    + context.containsBean("conversionService"));
        };
    }
}
~~~

This is a probe for inspecting bean definitions in the context; run it in development or tests. To investigate initialization order, use appropriate logging and inspect stack traces. Never enable verbose logging or dump the entire `Environment` in production just to check whether a bean exists.

**Note:** `containsBean("conversionService")` checks bean name/alias presence in the `BeanFactory`; it does not prove a single service is used across every subsystem. To verify which conversion path a binder uses, test actual binding behavior.

## 21. Testing a Dedicated Converter with ApplicationContextRunner

A small test can verify that the converter is properly registered for configuration properties. Example using Spring Boot Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.example.orders.config.RegionCode;
import com.example.orders.config.RegionBindingConfiguration;
import com.example.orders.config.RoutingProperties;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class RegionBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(
                TestConfiguration.class,
                RegionBindingConfiguration.class
            )
            .withPropertyValues(
                "app.routing.default-region=ap-southeast-1"
            );

    @Test
    void usesDedicatedConverter() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(RoutingProperties.class);
            RegionCode region = context
                .getBean(RoutingProperties.class)
                .defaultRegion();
            assertThat(region.value()).isEqualTo("ap-southeast-1");
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RoutingProperties.class)
    static class TestConfiguration {}
}
~~~

The test assumes `RegionBindingConfiguration` registers a `static @Bean @ConfigurationPropertiesBinding` converter as shown earlier and `spring-boot-starter-test` is on the test classpath.

If a custom converter is a lambda returning an uncommon type, verify that the binder truly invokes the converter rather than matching an accidental built-in conversion for the same type. That check belongs in functional project tests and is separate from whether a special bean name exists.

## 22. Regression Testing for Standard Types

When a project introduces custom conversion, it is vital not to break types already supported by Boot.

A test configuration properties class:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.testing")
public record StandardTypeProperties(
    Duration timeout,
    DataSize limit,
    int maxRetries
) {}
~~~

An integration test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.util.unit.DataSize;

@SpringBootTest(properties = {
    "app.testing.timeout=1500ms",
    "app.testing.limit=10MB",
    "app.testing.max-retries=4"
})
class ConversionRegressionTest {

    @Autowired
    StandardTypeProperties values;

    @Test
    void standardTypeConversionStillWorks() {
        assertThat(values.timeout())
            .isEqualTo(Duration.ofMillis(1500));
        assertThat(values.limit())
            .isEqualTo(DataSize.ofMegabytes(10));
        assertThat(values.maxRetries()).isEqualTo(4);
    }
}
~~~

The test assumes `StandardTypeProperties` is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. It guards key behaviors alongside custom converters. If a change to a `conversionService` bean breaks this test, review the conversion registry or registration setup.

### Testing Custom and Default Converters Together

A thorough project test can declare all of:

~~~properties
app.routing.default-region=ap-southeast-1
app.testing.timeout=1500ms
app.testing.limit=10MB
~~~

and assert that `RegionCode`, `Duration`, and `DataSize` all bind cleanly. The goal is catching unexpected regressions in seemingly unrelated properties when modifying converters.

## 23. Startup Troubleshooting Procedure

If the app fails to start after adding a converter:

**Step 1 — Determine whether the error happens before or during binding.** If it is a circular dependency or a bean not processed by all processors, inspect the `ConversionService` dependency graph. If it is "Failed to bind", inspect conversion, source value, and target type.

**Step 2 — Check the exact bean name.** Is there a `@Bean` method named `conversionService()` or `@Bean("conversionService")`? Does another module define a bean with that name?

**Step 3 — Clarify intent.** Is this bean meant to replace configuration-property conversion, or does it only serve controllers, UI, reports, or data imports?

**Step 4 — If only custom binding is needed, use `@ConfigurationPropertiesBinding`.** Register a pure converter, prefer a static bean method, and avoid an unnecessary shared `ConversionService`.

**Step 5 — If conversion is purely for business logic, rename it.** Use a name like `reportConversionService` and inject with `@Qualifier`; do not rely on the special name.

**Step 6 — If a `conversionService` bean is still required, restrict dependencies.** Avoid injecting properties beans or repositories and avoid network I/O in the conversion service factory.

**Step 7 — Verify standard converters.** Test `Duration`, `DataSize`, enums, and other typed properties your app uses.

**Step 8 — Check scope rules.** A `String -> RegionCode` converter can affect every configuration property targeting `RegionCode`. Verify whether any other place expects different semantics.

**Step 9 — Inspect warnings.** Warnings like "not eligible for getting processed by all BeanPostProcessors" can point to the converter's factory method or an eagerly created dependency. For `@ConfigurationPropertiesBinding` converters, make the method `static` as documented.

**Step 10 — Check the value source.** Do not overlook environment variables, profiles, or command-line flags overriding keys with unparseable values.

## 24. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "For a `ConversionService` bean, the name doesn't matter." | The name `conversionService` carries special meaning in configuration property conversion. |
| "Adding one converter requires declaring a new `ConversionService` bean." | Usually `@ConfigurationPropertiesBinding` on a dedicated converter is the right choice. |
| "`DefaultConversionService` includes all of Spring Boot's custom converters." | Do not equate it with `ApplicationConversionService`. |
| "`conversionService` is only created after all business services are ready." | Beans used for property conversion can be requested very early. |
| "A converter may query the DB because it is a Spring bean." | Startup binding should use pure conversion with minimal dependencies to avoid lifecycle issues. |
| "Renaming a bean has no impact." | Consumers injecting by old name or qualifier are affected; update them explicitly. |
| "`@Primary` guarantees `conversionService` won't interfere with the Binder." | `@Primary` and name-based lookup are different mechanisms; never use `@Primary` for isolation. |
| "A `@ConfigurationPropertiesBinding` converter applies to only one property path." | Converters typically apply to any matching source/target type pair during binding, not just one key. |
| "`@Component` on a `Converter` makes every subsystem use it automatically." | Each subsystem has its own registration/discovery mechanism; verify the specific path. |
| "`@Value` and `@ConfigurationProperties` always use identical converters." | The two injection paths behave differently; binding-specific converters may not apply to `@Value`. |
| "`conversionService` alters config override precedence." | Source order is decided by `Environment`/Config Data; conversion handles value types. |
| "If startup succeeds, the custom converter didn't break anything." | Test important configuration types and other modules that use conversion. |

## 25. Scope-Distinction Exercises

### Exercise 1 — Default Name of @Bean

~~~java
@Bean
ConversionService conversionService() {
    return new DefaultConversionService();
}
~~~

**Question:** What default name does this bean get, and why does it matter?

**Answer:** `conversionService`, matching the name Spring Boot recognizes for configuration conversion. If you do not intend to affect the binder, rename it or use a dedicated converter.

### Exercise 2 — Service Used Only for Analytics

~~~java
@Bean("analyticsConversionService")
ConversionService analyticsConversionService() {
    return new DefaultConversionService();
}
~~~

**Question:** Does it carry the same special name as Exercise 1?

**Answer:** no. This bean is named `analyticsConversionService`. Consumers should inject it with `@Qualifier`, avoiding type ambiguity when multiple `ConversionService` beans exist.

### Exercise 3 — Only Need String -> RegionCode for @ConfigurationProperties

**Question:** Do you need to create a bean named `conversionService`?

**Answer:** not necessarily. Define `Converter<String, RegionCode>` and register `@Bean @ConfigurationPropertiesBinding`; a static factory method is recommended.

### Exercise 4 — Converter Requiring a Repository

~~~java
@Bean("conversionService")
ConversionService conversionService(TenantRepository repository) {
    // ...
}
~~~

**Question:** What risk does this design carry?

**Answer:** a `ConversionService` used for property conversion can be requested early and pull in an unready repository, risking dependency/lifecycle failures. Separate DB operations from configuration type conversion.

### Exercise 5 — Model Binding Duration and DataSize

~~~properties
app.worker.timeout=2s
app.worker.quota=8MB
~~~

**Question:** After adding a custom `conversionService`, what should you check?

**Answer:** verify that standard conversions for `Duration` and `DataSize` still work, along with all other typed fields used by the application. Do not assume a custom registry retains Boot's converters automatically.

### Exercise 6 — Using Custom Converter with @Value

You have a `Converter<String, RegionCode>` annotated with `@ConfigurationPropertiesBinding`, yet inject:

~~~java
@Value("\${app.routing.default-region}")
private RegionCode region;
~~~

**Question:** Is this converter guaranteed to be used automatically by `@Value`?

**Answer:** do not assume so. The qualified converter serves configuration properties binding; if the app uses `@Value`, check Spring Core's conversion path or inject the typed configuration bean for consistency.

### Exercise 7 — What Problem Does a Static Method Solve?

~~~java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, RegionCode> regionCodeConverter() {
    return new StringToRegionCodeConverter();
}
~~~

**Answer:** a static factory method avoids eagerly instantiating the configuration class and helps prevent `BeanPostProcessor` warnings as recommended by Spring Boot. It does not substitute for keeping the converter low-dependency.

### Exercise 8 — Does Converter Change Precedence?

A file has `app.retry.delay=3s`, and the command line passes `--app.retry.delay=500ms`.

**Question:** Does the converter decide whether `3s` or `500ms` wins?

**Answer:** no. `Environment`/`PropertySource` precedence decides the effective value; the converter converts that value to the Java type. Under standard precedence, command line `500ms` wins over the file.

### Exercise 9 — Accidental Special @Bean Name

During refactoring, a developer renames the method `reportConversionService()` to `conversionService()` without changing its body and without adding `@Bean(name=...)`.

**Question:** What is the risk?

**Answer:** the default bean name can change to `conversionService`, altering how the framework detects the conversion service. To keep the contract stable, use `@Bean("reportConversionService")` or preserve an explicit name.

### Exercise 10 — Avoiding Impact on MVC

A converter is meant specifically for Spring MVC request parameters.

**Question:** Do you need to name a bean `conversionService` for MVC to use it?

**Answer:** not necessarily. Register the converter/formatter through MVC configuration, such as `WebMvcConfigurer#addFormatters`, instead of interfering with the `conversionService` used for property binding.

## 26. Final Decision Table

| Actual Requirement | Preferred Option |
| --- | --- |
| Convert a custom type when binding `@ConfigurationProperties` | `@ConfigurationPropertiesBinding` + `Converter<String,T>` |
| Avoid instantiating converter bean too early via configuration class | `static @Bean` factory method for binding converter |
| Have a `ConversionService` solely for reports/business logic | Distinct name like `reportConversionService` + `@Qualifier` |
| Need custom conversion for Spring MVC requests/inputs | `WebMvcConfigurer#addFormatters` or appropriate MVC hook |
| Need JSON conversion | Matching Jackson serializer/deserializer |
| Need broad conversion control during binding | Intentional `conversionService` bean retaining default converters + regression tests |
| `conversionService` bean depends on other beans | Reduce dependencies, remove I/O and cycles; prefer pure converter |
| Typed `Duration`/`DataSize` configs fail after customization | Inspect custom registry and Boot converters |
| Prevent unintended config precedence changes | Check `Environment`/Config Data; do not confuse with type conversion |
| Verify registered bean name | `ApplicationContext.containsBean("conversionService")` and list `ConversionService` beans |
| Prove custom type binding | Context test with `@EnableConfigurationProperties` + binding converter |
| Avoid impacting unrelated property groups | Pick a small, well-scoped converter and test existing config types |

## 27. Further Reading

- Spring Boot Reference — *Externalized Configuration*, **Properties Conversion** section: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Framework Reference — *Type Conversion*, covering `Converter`, `ConverterFactory`, `GenericConverter`, and `ConversionService`.
- Spring Boot API — `ApplicationConversionService` and `ConfigurationPropertiesBinding`.

In Spring Boot's documentation, the *Properties Conversion* section highlights three points: you can customize via a `ConversionService` bean named `conversionService` or a `@ConfigurationPropertiesBinding` converter qualifier; beans used for conversion may be requested very early; and `static @Bean` methods help avoid `BeanPostProcessor` warnings when registering dedicated converters.

**Conclusion:** the name `conversionService` is more than a label. In Spring Boot configuration binding, it can designate a `ConversionService` bean used by infrastructure very early in startup. If you only need one custom type for `@ConfigurationProperties`, write a pure converter with `@ConfigurationPropertiesBinding`, prefer a static factory method, and keep Boot's default converters intact. If a `ConversionService` belongs solely to a business module, give it a different name and inject it explicitly. Separating scopes this way reduces startup failures, prevents breaking conversions of other typed properties, and keeps configuration easy to understand and maintain.