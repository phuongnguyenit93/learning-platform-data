# Custom Converters and Their Scope of Application

When Spring Boot reads configuration, receives HTTP parameters, or binds data into a Java object, inputs often arrive as strings while the program wants richer types such as `Duration`, `DataSize`, `UUID`, `LocalDate`, or an application-defined value object. **Spring `ConversionService`** provides the type-conversion infrastructure. When built-in conversions do not cover a requirement, you can write a **custom `Converter`**.

What matters is not just knowing how to write a `Converter<S, T>` class, but also understanding **where a converter is registered determines where it takes effect**:

- A converter registered for **`@ConfigurationProperties` binding** serves configuration value conversion.
- A converter registered in **Spring MVC's `ConversionService`** serves data binding for request parameters, path variables, and compatible form fields.
- A converter registered in a **manually created `ConversionService`** applies only to calls using that specific service.
- A Spring `Converter` does **not automatically** become a Jackson JSON deserializer, a JPA `AttributeConverter`, or a converter for every other subsystem.

Distinguishing these scopes avoids the "I created the converter bean, why isn't it working?" bug and prevents accidentally widening an internal conversion rule into application-wide behavior.

## 1. What Is ConversionService?

`ConversionService` belongs to Spring Core and provides the API for converting from a source type to a target type.

Example using a conversion service supporting numeric conversions:

~~~java
ConversionService conversionService = ...;

Integer port = conversionService.convert("8080", Integer.class);
~~~

The application does not have to write `Integer.parseInt(...)` at every binding site. Spring uses type metadata and registered converters to carry out conversion.

Key interface:

~~~java
package org.springframework.core.convert;

public interface ConversionService {
    boolean canConvert(Class<?> sourceType, Class<?> targetType);
    <T> T convert(Object source, Class<T> targetType);
}
~~~

For complex generic types such as collections, `ConversionService` also provides `TypeDescriptor`-based APIs describing source and target types in greater detail.

### Distinguishing three concepts

| Concept | Function |
|---|---|
| **Conversion** | Transforms a value from type A to type B, e.g., String → RegionCode |
| **Binding** | Maps data from a source (property/request) into constructors, bean properties, or an object graph |
| **Validation** | Checks whether the post-conversion value satisfies business constraints |

A binder may invoke a converter during binding. Validation is a separate step: successfully converting a string into an `int` does not guarantee that value is valid for business rules.

## 2. Converters Already Provided by Spring Boot

Spring Framework and Spring Boot support many common conversions out of the box, so you do not need custom converters for everything:

- Strings to numbers, booleans, enums, and many basic types.
- Strings to `UUID` when properly formatted.
- Strings to various date/time types depending on the conversion service and formatter config.
- Unit-qualified values like `5s` or `250ms` to `Duration` in Boot configuration binding.
- Values like `10MB` to `DataSize` under Boot's conversion service.
- Common collection, array, and built-in conversions.

Example:

~~~yaml
app:
  upload:
    timeout: 5s
    max-size: 10MB
~~~

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        Duration timeout,
        DataSize maxSize) {
}
~~~

With a properly registered `@ConfigurationProperties` bean, Spring Boot binds both properties without any custom converter.

**Rule of thumb:** before writing a new converter, verify whether the active conversion service already supports that target type, unit, and format. If you only need `5s` converted to `Duration`, a custom converter is unnecessary.

## 3. Writing a Simple Converter<S, T>

Suppose configuration contains region codes such as `vn`, `US`, or ` jp `. The application wants them converted into a `RegionCode` value object enforcing normalization and format rules.

### 3.1. Define the target data type

~~~java
package com.example.fulfillment.domain;

import java.util.Locale;

public record RegionCode(String value) {

    public RegionCode {
        if (value == null || !value.matches("[A-Z]{2}")) {
            throw new IllegalArgumentException(
                    "Region code must contain exactly two A-Z letters");
        }
    }

    public static RegionCode parse(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "Region code must not be blank");
        }

        return new RegionCode(raw.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

This record is an **illustrative value object**: it checks for two uppercase ASCII letters, not whether the code actually exists in a country/region catalog supported by the application. Validating against an allowed catalog requires separate business rules.

### 3.2. Create the Converter

~~~java
package com.example.fulfillment.config;

import com.example.fulfillment.domain.RegionCode;
import org.springframework.core.convert.converter.Converter;

public final class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return RegionCode.parse(source);
    }
}
~~~

The two generic parameters mean:

- `String`: input data type.
- `RegionCode`: target data type.
- `convert(String source)`: the concrete transformation.

Example:

~~~java
Converter<String, RegionCode> converter =
        new StringToRegionCodeConverter();

RegionCode region = converter.convert(" vn ");
System.out.println(region.value()); // VN
~~~

Such a converter should be **stateless**, perform no database queries, have no side effects, and hold no per-request state. Converters registered in Spring are typically shared singletons, so never assume a fresh instance per conversion.

## 4. Registering a Converter into a Manual ConversionService

To understand the mechanics before Spring Boot integration, instantiate a conversion service directly and register the converter:

~~~java
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(new StringToRegionCodeConverter());

RegionCode region =
        conversionService.convert("vn", RegionCode.class);

System.out.println(region.value()); // VN
~~~

Here the converter takes effect only on that newly created **`conversionService` instance**. It does not affect Spring MVC, `@ConfigurationProperties`, or any other application context.

### 4.1. Registering with explicit types

Spring inspects a converter's generic metadata to determine source and target types. When explicit control is needed, register directly:

~~~java
conversionService.addConverter(
        String.class,
        RegionCode.class,
        new StringToRegionCodeConverter()
);
~~~

This helps for implementations that do not expose generic type metadata in a way Spring can infer.

### 4.2. Calling a converter directly differs from ConversionService

Calling directly:

~~~java
new StringToRegionCodeConverter().convert("vn");
~~~

is an ordinary Java method call. Going through `ConversionService` lets the container select a converter by source/target type and compose it with other conversions where supported.

A converter only participates in data binding if the binder at that point **uses a conversion service that has registered it**.

## 5. Scope 1: @ConfigurationProperties Binding

Spring Boot uses a dedicated mechanism to bind externalized configuration into `@ConfigurationProperties` classes. A converter intended specifically for this process should be registered with `@ConfigurationPropertiesBinding`.

### 5.1. Define configuration properties

~~~yaml
app:
  fulfillment:
    origin: vn
    timeout: 2s
    max-payload: 5MB
~~~

~~~java
package com.example.fulfillment.config;

import java.time.Duration;
import com.example.fulfillment.domain.RegionCode;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.fulfillment")
public record FulfillmentProperties(
        RegionCode origin,
        Duration timeout,
        DataSize maxPayload) {
}
~~~

`Duration` and `DataSize` properties use Boot's built-in converters. `origin` is our application's `RegionCode` type, so we want the Binder to use `StringToRegionCodeConverter`.

### 5.2. Register the converter for configuration binding

~~~java
package com.example.fulfillment.config;

import com.example.fulfillment.domain.RegionCode;
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class FulfillmentConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, RegionCode> regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

`@ConfigurationPropertiesBinding` is the qualifier Spring Boot uses to discover converters dedicated to configuration-properties binding. It makes the scope explicit rather than expecting every conversion service in the app to auto-adopt the converter.

Declaring the `@Bean` method `static` is deliberate. Converters for configuration properties may be requested **very early** during bootstrap; a static factory method avoids instantiating the `@Configuration` class prematurely just to invoke the factory method.

### 5.3. Register the properties class

~~~java
package com.example.fulfillment;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class FulfillmentApplication {

    public static void main(String[] args) {
        SpringApplication.run(FulfillmentApplication.class, args);
    }
}
~~~

For the converter configuration to take effect, `FulfillmentConversionConfiguration` must also be processed by Spring. This example assumes it sits in a subpackage covered by component scanning or is imported via `@Import`.

At startup:

~~~text
application.yml
  app.fulfillment.origin=vn
            |
            v
@ConfigurationProperties Binder
            |
            v
StringToRegionCodeConverter
            |
            v
RegionCode("VN")
            |
            v
FulfillmentProperties.origin()
~~~

Other services can inject `FulfillmentProperties` just like any Spring bean.

### 5.4. Explicit registration when scanning is undesired

If the properties class is outside `@ConfigurationPropertiesScan` scope, you can use:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(FulfillmentProperties.class)
@Import(FulfillmentConversionConfiguration.class)
public class FulfillmentModuleConfiguration {
}
~~~

This is also a clean way to package shared modules: applications import a configuration class instead of widening component scanning into every library package.

### 5.5. @ConfigurationPropertiesBinding does not mean "everywhere"

Suppose `regionCodeConverter` is marked with `@ConfigurationPropertiesBinding` and works when binding `app.fulfillment.origin`. Never assume that automatically means:

- `@PathVariable RegionCode` in a controller will also work.
- A JSON request containing `"origin": "vn"` will be converted by Jackson into `RegionCode`.
- A JPA entity with a `RegionCode` field will automatically persist as a string.
- `@Value("${app.fulfillment.origin}")` is guaranteed to pass through that exact converter.

Those places have **separate binding or conversion mechanisms**. To apply the same rule elsewhere, register the converter in the conversion service used there or implement the corresponding extension point.

## 6. Why Should Configuration-Properties Converters Have Minimal Dependencies?

Spring Boot often binds configuration while constructing the context. Some config converters are needed before other beans finish initializing.

Example to avoid:

~~~java
@Component
@ConfigurationPropertiesBinding
public class DatabaseRegionConverter
        implements Converter<String, RegionCode> {

    private final RegionRepository repository;

    public DatabaseRegionConverter(RegionRepository repository) {
        this.repository = repository;
    }

    @Override
    public RegionCode convert(String source) {
        return repository.findByText(source);
    }
}
~~~

Why:

1. The Binder needs the converter to build `@ConfigurationProperties` beans.
2. The converter requires `RegionRepository`.
3. The repository may depend on a DataSource, transaction infrastructure, or a properties bean currently being bound.
4. Spring may force premature bean creation or hit a circular dependency.

Even if it happens to start up, binding now depends on a database or external service, complicating startup and testing.

**Better design:** the converter performs only value parsing/normalization. If you must check whether a region code exists in the database, run business validation in a service after the context has all dependencies ready.

### 6.1. Why is static @Bean recommended?

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class ConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, RegionCode> regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

does not require Spring to instantiate a `ConversionConfiguration` instance merely to invoke the factory method. This reduces the risk of triggering unnecessary early instantiation of the configuration class.

`static` does not mean the converter creates a "new object every run". The registered bean still follows its bean definition scope, which is singleton by default.

## 7. Scope 2: Data Conversion in Spring MVC

HTTP requests deliver query parameters and path variables as strings. Spring MVC maintains a conversion service for request data binding.

Desired endpoint:

~~~text
GET /shipping/options?region=vn
~~~

Controller:

~~~java
import com.example.fulfillment.domain.RegionCode;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ShippingController {

    @GetMapping("/shipping/options")
    public String options(@RequestParam RegionCode region) {
        return "Options for " + region.value();
    }
}
~~~

To bind `@RequestParam RegionCode` from `"vn"`, register the converter with **Spring MVC's formatter registry**.

~~~java
import com.example.fulfillment.config.StringToRegionCodeConverter;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ShippingWebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToRegionCodeConverter());
    }
}
~~~

Spring MVC uses the converter when binding the `region` parameter into `RegionCode`. If the input is invalid, binding raises a type-conversion failure; for ordinary request parameters, the app usually responds with 400 Bad Request via default error handling or `@ControllerAdvice`.

Registering on `WebMvcConfigurer` **does not automatically register the converter for `@ConfigurationProperties`**. If you want the same conversion in both places, reuse the `StringToRegionCodeConverter` class while registering it explicitly in each appropriate conversion service.

### 7.1. @PathVariable example

~~~java
@GetMapping("/shipping/regions/{region}")
public String detail(@PathVariable RegionCode region) {
    return "Region " + region.value();
}
~~~

With the MVC converter registered, `/shipping/regions/us` converts to `RegionCode("US")`.

### 7.2. This is not how JSON @RequestBody is read

JSON request example:

~~~json
{
  "region": "vn",
  "quantity": 5
}
~~~

~~~java
@PostMapping("/shipping/orders")
public void create(@RequestBody CreateOrderRequest request) {
}
~~~

With JSON `@RequestBody` in Spring MVC, payloads are typically deserialized by Jackson via an `HttpMessageConverter`, not routed through Spring MVC's `Converter<String, RegionCode>` the way `@RequestParam` is.

To have Jackson deserialize a JSON string into a value object, use `@JsonCreator`/`@JsonValue` where suitable or write a custom Jackson deserializer/module. That is a different extension point from Spring's `ConversionService`.

## 8. Scope 3: @InitBinder and Controller-Local Form Data

Spring MVC lets you customize data binding per controller with `@InitBinder`, such as registering a `PropertyEditor` for a specific type.

~~~java
import java.beans.PropertyEditorSupport;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RegionFormController {

    @InitBinder
    void configureBinder(WebDataBinder binder) {
        binder.registerCustomEditor(
                RegionCode.class,
                new PropertyEditorSupport() {
                    @Override
                    public void setAsText(String text) {
                        setValue(RegionCode.parse(text));
                    }
                }
        );
    }
}
~~~

This example uses JavaBeans **`PropertyEditor`** to illustrate a local binder customization, not a `Converter`. For rules shared across controllers, registering a `Converter` on MVC's `FormatterRegistry` is usually cleaner.

When using custom editors, watch out for lifecycle and thread safety. `PropertyEditor` instances are typically stateful (via `setValue`), so never share a single mutable instance across threads.

## 9. Converter, ConverterFactory, GenericConverter, and Formatter

Not every conversion problem calls for a single `Converter<S,T>`.

| Extension point | When to use | Example |
|---|---|---|
| `Converter<S,T>` | One concrete source–target conversion | String → RegionCode |
| `ConverterFactory<S,R>` | A family of target types sharing conversion logic | String → multiple related subtypes |
| `GenericConverter` | Multiple type pairs or source/target type metadata needed | Conversion depending on `TypeDescriptor` |
| `ConditionalGenericConverter` | Apply only if target metadata/element meets a condition | Check eligibility based on field/annotation |
| `Formatter<T>` | Locale-aware text ↔ object conversion | Dates, currencies, display formatting |
| `PropertyEditor` | Legacy JavaBeans mechanism, registrable on WebDataBinder | Binder-local string conversion |

### 9.1. Converter<S,T>

Interface:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Prefer this first for straightforward, explicit conversions like `StringToRegionCodeConverter`.

### 9.2. ConverterFactory<S,R>

`ConverterFactory` supplies converters for a hierarchy of target types sharing a common supertype. Spring uses converter factories for enum conversions.

Use it when you must choose conversion behavior by target subtype. If you have just one target type `RegionCode`, a `Converter<String, RegionCode>` is simpler and sufficient.

### 9.3. GenericConverter

`GenericConverter` works with `ConvertiblePair` and `TypeDescriptor`, letting you inspect generics, annotations, or multiple source/target pairs. It suits infrastructure binding libraries, though it is more complex than a normal converter. Avoid reaching for it just to parse a simple prefixed string.

### 9.4. Formatter<T>

`Formatter<T>` is bidirectional:

~~~java
public interface Formatter<T>
        extends Printer<T>, Parser<T> {
}
~~~

- `parse(String text, Locale locale)`: text → object.
- `print(T object, Locale locale)`: object → text.

When display formatting depends on locale—such as dates or monetary amounts—`Formatter` usually fits better than a locale-less `Converter`.

For example, a multi-locale application should not assume `01/02/2026` means the same calendar day in every country. For form/query parameters, prefer `@DateTimeFormat` and built-in formatters before writing custom ones.

## 10. Do Not Replace the Global conversionService Bean for a Narrow Scope

Spring and Spring Boot use different conversion services for different jobs. Specifically, a bean named `conversionService` in the application context can be used by Spring for bean factory conversion and related property values.

Example:

~~~java
@Bean(name = "conversionService")
ConversionService applicationConversionService() {
    // Think carefully before replacing the shared conversion service.
}
~~~

Replacing the shared conversion service can affect default converters or bean creation, and this bean may have to be instantiated very early. If you replace it without preserving required converters, previously working conversions can break.

For Spring Boot configuration properties, **prefer `@ConfigurationPropertiesBinding`** for type-specific converters. For Spring MVC request parameters, **prefer `WebMvcConfigurer.addFormatters`**. Avoid replacing the global conversion service merely to bind one `RegionCode` property.

Also do not assume that merely annotating a converter bean with `@Component` automatically registers it in every conversion service. Discovery depends on the specific framework component and configuration.

## 11. Boundary with Resource and ResourceLoader

In the Resources and Data chapter, you often encounter path-style configuration values:

~~~properties
app.templates.invoice=classpath:/templates/invoice.txt
app.archive.location=file:/var/app/archive/
~~~

Spring provides `Resource` and `ResourceLoader` abstractions to access resources from the classpath, filesystem, or supported protocols:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

public class InvoiceTemplateService {

    private final Resource invoiceTemplate;

    public InvoiceTemplateService(ResourceLoader resourceLoader) {
        this.invoiceTemplate = resourceLoader.getResource(
                "classpath:/templates/invoice.txt"
        );
    }
}
~~~

This mechanism **resolves a resource location** from a string. It does not mean custom converters should open files or read resource contents. If you only want to turn a config string into a `Resource`, rely on Spring's built-in resource conversion/editors before writing a custom converter.

Distinguish:

| Task | Suitable infrastructure |
|---|---|
| String → value object, e.g., RegionCode | `Converter` |
| String location → Resource handle | `ResourceLoader` / built-in resource conversion |
| Reading bytes/text from Resource | `Resource.getInputStream()` and I/O APIs |
| JSON → Java object | Jackson / matching `HttpMessageConverter` |
| Entity field → database column | JPA converter / JDBC mapping |
| YAML/property config → typed object | Spring Boot Binder + `ConversionService` |

**Security note:** if input comes from users, never pass an unvalidated path/URL string straight into `ResourceLoader` and open a stream. Restrict protocols, allowed directories, and permissions to avoid arbitrary file reads or SSRF. A converter should not perform unintended I/O when all it needs to do is parse data.

## 12. Spring Converter Differs from Jackson and JPA Converters

Three distinct systems are often confused because all use the word "converter":

### 12.1. Spring Converter

~~~java
import org.springframework.core.convert.converter.Converter;

class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {
    @Override
    public RegionCode convert(String source) {
        return RegionCode.parse(source);
    }
}
~~~

Used by any `ConversionService` in which it is registered.

### 12.2. Jackson deserializer

Jackson handles JSON requests/responses via `ObjectMapper` and serializers/deserializers. If an API wants JSON string `"vn"` turned into `RegionCode`, use Jackson annotations on the value object or a custom Jackson deserializer for that type.

A Spring converter does not automatically become a Jackson deserializer just by being a bean.

### 12.3. JPA AttributeConverter

~~~java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class RegionCodeJpaConverter
        implements AttributeConverter<RegionCode, String> {

    @Override
    public String convertToDatabaseColumn(RegionCode region) {
        return region == null ? null : region.value();
    }

    @Override
    public RegionCode convertToEntityAttribute(String value) {
        return value == null ? null : RegionCode.parse(value);
    }
}
~~~

JPA `@Converter` and `AttributeConverter` map between entity attributes and database column types in the persistence provider; they are distinct from Spring's `org.springframework.core.convert.converter.Converter`.

To avoid import name collisions, many projects use explicit class names like `RegionCodeJpaConverter` and keep the two annotations separate. Spring Boot 3 uses Jakarta Persistence (`jakarta.persistence.*`); older Boot 2/JPA projects use `javax.persistence.*`.

## 13. How Do Conversion Failures Happen?

Suppose the converter runs:

~~~java
RegionCode.parse(source)
~~~

and receives `"123"`. `RegionCode`'s constructor throws `IllegalArgumentException`. Inside a Spring conversion pipeline, the failure may be wrapped in a framework-specific exception such as `ConversionFailedException` or the corresponding binding error.

**Impact depends on scope**:

| Scope | Typical behavior on conversion failure |
|---|---|
| `@ConfigurationProperties` | Bean binding fails; application may fail to start if the properties bean is required |
| MVC `@RequestParam` or `@PathVariable` | Argument binding fails; typically mapped to a 400 response via MVC error handling |
| Manual `ConversionService` call | `convert(...)` throws the exception to the caller |
| JPA mapping | Failure during entity read/write per transaction and persistence provider |
| Jackson deserialization | Failure parsing JSON input; response depends on `HttpMessageConverter`/exception handler |

Never make a converter return HTTP status codes directly or handle transactions: its job is transforming values or clearly signaling invalid input. Controller advice, binders, and upper framework layers interpret errors in context.

### 13.1. Producing helpful error messages

A converter should reject invalid input consistently:

~~~java
@Override
public RegionCode convert(String source) {
    try {
        return RegionCode.parse(source);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Invalid region code: expected exactly two letters", ex);
    }
}
~~~

For sensitive data like tokens, passwords, or private keys, **do not include the raw input in the exception message**. Messages can end up in logs, startup failure reports, or HTTP error responses.

Never return a dummy placeholder object on invalid input, as doing so hides misconfigurations and feeds bad data downstream.

## 14. Startup Order and Early Dependencies

Configuration converters can be instantiated before most business beans. Design anti-patterns to avoid:

- Injecting `DataSource`, `EntityManager`, or repositories into a configuration-properties converter.
- Calling an HTTP client to validate a config value.
- Manually looking up beans from `ApplicationContext` inside `convert()`.
- Calling `@Transactional` logic assuming proxies are already active.
- Opening files or sockets on each conversion.
- Mutating global application state from a converter.

A **pure** converter relying solely on its input and fixed rules works cleanly across multiple scopes:

~~~text
String " vn "
      |
      v
Trim + normalize + validate
      |
      v
RegionCode("VN")
~~~

If validation requires checking database state, perform it in the validation/service layer after binding.

## 15. Testing a Converter in Isolation

Pure conversion logic is easy to test with JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class StringToRegionCodeConverterTest {

    private final StringToRegionCodeConverter converter =
            new StringToRegionCodeConverter();

    @Test
    void normalizesInput() {
        RegionCode actual = converter.convert(" vn ");
        assertEquals("VN", actual.value());
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("123")
        );
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("  ")
        );
    }
}
~~~

This unit test checks parsing/normalization logic. It does not prove Spring Boot's Binder or Spring MVC registered the converter in the right scope. To verify integration, write context tests where the converter will actually be used.

## 16. Testing @ConfigurationPropertiesBinding with ApplicationContextRunner

This example uses:

- The `FulfillmentProperties` record from section 5.
- `FulfillmentConversionConfiguration` declaring the static `@Bean` converter.
- A test configuration class registering the properties.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

class FulfillmentBindingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(FulfillmentProperties.class)
    @Import(FulfillmentConversionConfiguration.class)
    static class TestConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsRegionCodeUsingCustomConverter() {
        runner.withPropertyValues(
                "app.fulfillment.origin=vn",
                "app.fulfillment.timeout=2s",
                "app.fulfillment.max-payload=5MB"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            FulfillmentProperties properties =
                    context.getBean(FulfillmentProperties.class);

            assertThat(properties.origin().value()).isEqualTo("VN");
            assertThat(properties.timeout())
                    .isEqualTo(java.time.Duration.ofSeconds(2));
        });
    }

    @Test
    void rejectsInvalidRegionCode() {
        runner.withPropertyValues(
                "app.fulfillment.origin=123",
                "app.fulfillment.timeout=2s",
                "app.fulfillment.max-payload=5MB"
        ).run(context -> assertThat(context).hasFailed());
    }
}
~~~

This test fits a Spring Boot project with `spring-boot-starter-test`. It verifies two separate things:

1. Conversion logic inside `RegionCode.parse`.
2. Registration: Spring Boot's real Binder discovers the `@ConfigurationPropertiesBinding` converter and uses it during binding.

Testing only `converter.convert("vn")` leaves the second aspect unverified.

## 17. Testing a Converter in Spring MVC

Web-layer tests should exercise real HTTP binding, for example using `MockMvc` with web config including `WebMvcConfigurer.addFormatters(...)`.

Illustrative assertion snippet:

~~~java
mockMvc.perform(get("/shipping/options")
        .param("region", "vn"))
        .andExpect(status().isOk())
        .andExpect(content().string("Options for VN"));
~~~

This snippet assumes:

- `ShippingController` is included in the test context.
- `ShippingWebConfiguration` is imported or component-scanned.
- MockMvc is configured for the corresponding MVC stack.
- The controller returns the string from section 7.

Also test invalid input:

~~~java
mockMvc.perform(get("/shipping/options")
        .param("region", "123"))
        .andExpect(status().isBadRequest());
~~~

That is an integration test for request-parameter conversion. It is independent of `@ConfigurationProperties` tests and catches cases where a converter was registered in only one scope.

## 18. When Multiple Converters Share the Same Type Pair

Suppose an application registers two `Converter<String, RegionCode>` implementations with different rules:

~~~java
class StrictRegionConverter implements Converter<String, RegionCode> { ... }
class LenientRegionConverter implements Converter<String, RegionCode> { ... }
~~~

Avoid registering both into the same conversion service unintentionally. Depending on the registry and registration order, one converter may overwrite or take precedence over the other, causing unpredictable results.

Pick one canonical rule per source/target pair within each scope. If you need two interpretations by endpoint or field, consider:

- Two distinct target types reflecting different semantics.
- A `Formatter` or metadata/annotation-driven converter when genuinely appropriate.
- Parsing inside the service/controller when the rule is highly specialized.
- Separate conversion services per module if they should not share rules.

Adding `@Primary` to a converter bean is not a universal solution for duplicate type-pair converters in a registry; converter lookup relies on source/target type registration, not solely bean autowiring rules.

## 19. Do Not Mix Converters with Business Validation

Region code example:

- Conversion: `" vn "` → `RegionCode("VN")`.
- Structural validation: code must contain exactly two letters.
- Business validation: is shipping enabled for this region?
- Authorization: is this user allowed to use that region?

Keep these steps separate:

~~~text
Raw request/configuration
          |
          v
   Converter (parse + normalize)
          |
          v
   Value object RegionCode
          |
          v
   Validation / business policy
          |
          v
   Authorization / execution
~~~

If a Converter queries a database to decide whether shipping is permitted in a region, a simple type transformation becomes tightly coupled to business state. That hurts testability, adds I/O, and causes startup issues when used for configuration binding.

For HTTP input, deciding whether to return 400 or a business error belongs to the web/service layer, not as an excuse to make custom converters aware of `HttpServletResponse`.

## 20. Thread Safety and Performance Notes

A Spring converter registered as a singleton bean can be invoked concurrently. Design accordingly:

- Do not store mutable per-input fields.
- Never share an unsynchronized `SimpleDateFormat` across threads; prefer immutable `java.time` formatters or safe APIs.
- Never open DB/HTTP connections per `convert()` call.
- Do not perform unintended filesystem reads or resource loading.
- Do not maintain unbounded caches over untrusted input.
- If locale-aware formatting is required, pick `Formatter` using the framework-supplied `Locale` rather than mutable global state.
- For untrusted input, bound input length/complexity if parsing can consume excessive resources.

For configuration properties, values are usually bound when beans are created; however, converters can still be invoked in other contexts and repeatedly. Never rely on an assumption that "the converter only runs once".

## 21. Diagnosing a Converter That Does Not Take Effect

| Symptom | Possible cause | Approach |
|---|---|---|
| `@ConfigurationProperties` fails to bind `RegionCode` | Converter not registered via `@ConfigurationPropertiesBinding` or config class not loaded | Check `@Bean`, `@Import`, and package scan |
| Converter works in config properties but not in controller | Not registered in MVC `FormatterRegistry` | Use `WebMvcConfigurer.addFormatters` |
| MVC param still returns 400 though converter unit test passes | Web context registry lacks converter or input is invalid | Use MockMvc test to verify wiring |
| JSON field ignores converter | Jackson handles JSON via `HttpMessageConverter`/`ObjectMapper` | Use an appropriate Jackson extension point |
| JPA fails to persist/read custom type | Spring Converter does not apply to entity attributes | Declare a JPA `AttributeConverter` |
| Startup warns BeanPostProcessor skipped early bean | Converter/config class has heavy dependencies or non-static factory | Reduce dependencies, use static `@Bean` where fitting |
| Self-created `ConversionService` lacks Duration/DataSize conversion | Different service from Boot `ApplicationConversionService` | Use the right conversion service or register needed converters |
| Exception leaks sensitive input | Converter concatenates raw input into message | Replace with safe message omitting secrets |
| Two converters exist for the same type pair | Registry has duplicate-registration rules and unpredictable order | Design one canonical converter per scope |
| Property changed yet bean value stayed the same | Configuration properties do not auto-refresh at runtime | Use an intentional refresh/restart mechanism |

When troubleshooting, check in order: **data source → active binder → concrete conversion service → registered converters → source/target types → root exception**. Never see `StringToRegionCodeConverter` in the repo and assume Spring is automatically using it.

## 22. Choosing the Right Registration Scope

| Where do you want conversion? | Mechanism to use |
|---|---|
| `application.yml`/Environment values into `@ConfigurationProperties` | `@ConfigurationPropertiesBinding` on converter bean |
| Query parameters, path variables, or MVC form binding | `WebMvcConfigurer.addFormatters` |
| Manual conversion within a module/service | Dedicated `ConversionService` and `addConverter` |
| Locale-dependent text formatting in MVC | `Formatter<T>` and appropriate registry |
| JSON requests/responses | Jackson serializer/deserializer or Jackson annotations |
| Entity ↔ database column | JPA `AttributeConverter` / corresponding data mapping |
| Path string ↔ Spring Resource | `ResourceLoader` or built-in resource conversion |
| Common property formats like Duration, DataSize | Prefer Spring Boot's built-in converters |
| Business validation rules after conversion | Independent service/validator, not inside converter |

### Practical design principles

1. Clarify the **input source** and **target type** before writing a converter.
2. Check whether built-in conversions already satisfy the need.
3. Write pure, stateless, deterministic `Converter<S,T>` classes for single type pairs.
4. Register in **the right conversion service** rather than assuming one converter bean applies everywhere.
5. For `@ConfigurationProperties`, prefer `@ConfigurationPropertiesBinding` and static `@Bean`, avoiding heavy business beans.
6. For MVC, register in `FormatterRegistry`; for JSON/JPA, use their native extension points.
7. Separate parse/convert errors from business validation and authorization.
8. Test both unit conversion and Spring integration within the target scope.
9. Never log raw secrets or sensitive values in exceptions.
10. When different semantics are needed, design distinct target types or scoped registries deliberately.

**Conclusion:** Custom Converters are an important Spring extension mechanism, yet a `Converter<String, RegionCode>` alone only defines how one value transforms into another. **Its effective scope is decided by which conversion service or binder registered and uses it.** Understanding the boundaries across configuration properties, Spring MVC, JSON, persistence, and resource loading keeps conversions consistent, testable, and free of unintended side effects.
