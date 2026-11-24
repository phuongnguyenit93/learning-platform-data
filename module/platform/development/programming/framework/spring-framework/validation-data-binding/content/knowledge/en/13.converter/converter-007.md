# ConverterRegistry and Registering Converters by Type Pair in Spring Framework

Spring often receives data as strings from forms, query parameters, or configuration, while Java code needs explicit types such as numbers, dates, enums, or application-defined domain types. A **Converter** is responsible for converting a source type into a target type. **ConverterRegistry** is the interface for registering converters into Spring's type conversion system.

Once you understand how to declare converters and register the right type pairs, you can add conversions application-wide or for Spring MVC without scattering string-parsing logic across controllers and services.

This lesson focuses on:

- Distinguishing `ConverterRegistry` and `ConversionService`.
- Registering a converter for a `sourceType → targetType` pair using `addConverter(...)`.
- Registering a converter via its declared generic types.
- Choosing between `Converter`, `ConverterFactory`, `GenericConverter`, or `Formatter`.
- Wiring converters into the Spring Container and Spring MVC with Java Configuration.
- Checking conversion capability, handling invalid input, and testing.
- Avoiding converter conflicts, lost type metadata, and common configuration pitfalls.

## 1. What Is ConverterRegistry?

`org.springframework.core.convert.converter.ConverterRegistry` is an **SPI (Service Provider Interface)** defining how to add or remove converters from a conversion registry. It focuses on configuration operations:

```java
public interface ConverterRegistry {
    void addConverter(Converter<?, ?> converter);

    <S, T> void addConverter(
            Class<S> sourceType,
            Class<T> targetType,
            Converter<? super S, ? extends T> converter);

    void addConverter(GenericConverter converter);

    void addConverterFactory(ConverterFactory<?, ?> factory);

    void removeConvertible(
            Class<?> sourceType,
            Class<?> targetType);
}
```

These are the typical Spring API signatures; when using them in source code, import the exact `org.springframework.core.convert.converter.ConverterRegistry` package. Two concepts often go together yet hold different responsibilities:

| API | Responsibility | Where is it typically called? |
| --- | --- | --- |
| `ConverterRegistry` | Register and remove converters and converter factories | Java Configuration, MVC config |
| `ConversionService` | Query whether conversion is possible and perform conversion | `DataBinder`, controller, service |
| `GenericConversionService` | Core implementation of both APIs, providing registry and service | Used when building a custom conversion system |
| `DefaultConversionService` | Implementation pre-populated with standard converters | Typical applications needing common conversions |
| `DefaultFormattingConversionService` | Extends conversion with default formatters | Applications needing both conversion and text formatting |
| `FormatterRegistry` | Extended registry for both formatters and converters | Configuring conversion/formatting in MVC |

An object implementing `ConversionService` frequently implements `ConverterRegistry` as well. For example, `GenericConversionService` is the shared foundation; `DefaultConversionService` and `FormattingConversionService` extend/add default configuration.

**Rule of thumb:** the registry is where *conversion rules are registered*; the service is where *those rules are used*.

## 2. Source Type and Target Type Pair

A typical converter declares two generic parameters:

```java
Converter<S, T>
```

Where:

- `S` is the source type.
- `T` is the target type.
- `convert(S source)` accepts a source-typed object and returns a target-typed value.

For example, if a request supplies the string `"USD"` and the application uses a `CurrencyCode` domain type:

```text
String "USD"
    |
    v
Converter<String, CurrencyCode>
    |
    v
CurrencyCode("USD")
```

The `String.class → CurrencyCode.class` pair determines when the converter can be selected. The registry does not need to guess what a string means: you explicitly declare the input type, output type, and conversion logic.

A converter can be written as a class:

```java
public final class StringToCurrencyCode
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        return new CurrencyCode(source.trim().toUpperCase());
    }
}
```

This is an excerpt; the full `CurrencyCode` definition and input validation are shown in the runnable example in section 6.

A converter can also be registered with an explicit type pair:

```java
registry.addConverter(
        String.class,
        CurrencyCode.class,
        new StringToCurrencyCode());
```

This is useful when you want the source/target pair clearly stated at the registration site, or when the same converter must be bound to a specific pair. Spring also provides an overload that accepts the converter directly and infers the type pair from the implemented generics.

## 3. Two Ways to Register a Converter

### 3.1. Registering with Generic Types Declared on the Class

When a class implements `Converter<String, CurrencyCode>`, Spring can determine the type pair from the generics:

```java
ConverterRegistry registry = ...;
registry.addConverter(new StringToCurrencyCode());
```

This is concise, readable, and fits converters with a fixed type pair. Type information must be resolvable from the implementing class's generics. Avoid registering a raw-typed converter that erases generics, because the registry may fail to infer the desired type pair.

### 3.2. Registering with an Explicit Type Pair

The second overload takes two class types and a converter:

```java
registry.addConverter(
        String.class,
        CurrencyCode.class,
        new StringToCurrencyCode());
```

The benefit here is that the type pair is visible right at the configuration site. It is especially helpful when sharing a general converter across several type pairs or when avoiding reliance on generic type inference.

For instance, the same code-normalizing converter could be reused across multiple domain wrapper types, though only when the conversion rules are genuinely identical. If each type has different formatting or validation rules, create separate converters so the type names reflect their exact meaning.

### 3.3. Registering a Factory or Generic Converter

Not every requirement fits a single fixed type pair:

- `addConverterFactory(...)` registers a `ConverterFactory<S, R>`; the factory creates converters for multiple target subtypes of base type `R`. A typical case is converting strings to one of many enum types.
- `addConverter(GenericConverter)` registers a converter that can support multiple type pairs. `GenericConverter` declares convertible pairs and receives source/target `TypeDescriptor`s, useful when conversion decisions depend on annotations or collection metadata.
- `ConditionalConverter` can be additionally implemented to accept a type pair only when a specific condition holds.

Do not pick `GenericConverter` just because it is more flexible. For a simple single pair, `Converter<S,T>` is usually clearest and requires the least code.

## 4. How Do ConverterRegistry and ConversionService Work Together?

Once a converter is registered, the application typically uses `ConversionService`:

```java
ConversionService service = ...;

boolean supported =
        service.canConvert(String.class, CurrencyCode.class);

CurrencyCode code =
        service.convert("USD", CurrencyCode.class);
```

`canConvert(sourceType, targetType)` checks the service's conversion capability. `convert(source, targetType)` performs the conversion and returns the target type. Overloads accepting `TypeDescriptor` are also available when field, generic collection, or annotation metadata must be preserved.

An example path:

```text
Java Configuration
      |
      v
ConverterRegistry.addConverter(...)
      |
      v
ConversionService holds registered converters
      |
      +--> canConvert(String, CurrencyCode)
      |
      +--> convert("USD", CurrencyCode)
                    |
                    v
             CurrencyCode("USD")
```

`ConversionService` is designed as a stateless service initialized at application startup and shared across threads. Shared converters should likewise be stateless and thread-safe. Do not store request values, current users, or per-request mutable state in fields of a singleton converter.

### 4.1. Checking Before Converting

`canConvert(...)` is useful when an application needs to verify whether a type pair is supported. However, a `true` result does not guarantee every source value is valid. For example, `String → CurrencyCode` has a converter, yet the string `"US"` can still fail format rules.

Therefore, distinguish:

1. **No matching converter:** the service does not know how to convert that pair of types.
2. **Converter exists yet the specific value is invalid:** the converter is invoked and rejects the value, usually with `IllegalArgumentException`.
3. **Conversion succeeds:** a valid target object is returned.

When conversion fails through `ConversionService`, Spring typically wraps the converter error in `ConversionFailedException`; at higher binding layers, another type-conversion error may surface. At application boundaries, map errors to clear messages and never return stack traces.

## 5. Choosing the Right Kind of Converter

| Type | When to use | Characteristics |
| --- | --- | --- |
| `Converter<S,T>` | One concrete source/target pair | Simple, explicit generics |
| `ConverterFactory<S,R>` | One source type to many target types in the same family | Factory returns converter for subtypes of `R` |
| `GenericConverter` | Multiple type pairs or needing source/target metadata | Uses `ConvertiblePair` set and `TypeDescriptor` |
| `ConditionalConverter` | Conversion valid only under metadata conditions | Can be combined with `GenericConverter` |
| `Formatter<T>` | String-to-type parsing and locale-aware printing | Has both `parse(...)` and `print(...)` |

### 5.1. When to Use ConverterFactory?

Suppose an application receives strings to construct enums. Rather than writing a converter class for every enum, you can use one `ConverterFactory<String, Enum>` that returns the converter matching the requested enum type. This pattern works when target types share a common conversion mechanism.

Still, handle invalid enum names and input formatting intentionally. Never assume client strings are always valid; `Enum.valueOf(...)` can throw `IllegalArgumentException` if no matching constant exists.

### 5.2. When to Use GenericConverter?

`GenericConverter` is appropriate when a converter needs richer type details than plain `Class<?>`. Examples include converting collections based on generic element types, or operating only on fields carrying a specific annotation. `TypeDescriptor` can represent the object type, generics, annotations, and related metadata.

For a simple pair like `String → CurrencyCode`, there is no need to implement `GenericConverter` yourself; use `Converter` and register it in the registry.

### 5.3. When to Use Formatter?

`Converter` generally focuses on converting one type to another. `Formatter<T>` is designed for bidirectional text conversion: `parse(String, Locale)` for reading and `print(T, Locale)` for displaying. For dates, decimals, and locale-dependent text, a formatter is usually the more natural choice.

## 6. Complete Example: Registering Converter<String, CurrencyCode>

This example uses Java 17 and Spring Framework 6.2. It creates a `CurrencyCode` domain type, declares a converter, registers it with an explicit type pair, then performs a valid conversion and tests an invalid string. This console program requires no Spring Boot or HTTP server.

Structure:

```text
converter-registry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/conversion/ConverterRegistryDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'converter-registry-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.conversion.ConverterRegistryDemo'
}
```

`spring-context` brings in the modules required for Spring's conversion system. In an existing Spring Boot project, use the dependency version managed by Spring Boot rather than pinning a standalone Spring version that might clash with other starters.

File `src/main/java/demo/conversion/ConverterRegistryDemo.java`:

```java
package demo.conversion;

import java.util.Locale;
import java.util.regex.Pattern;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultFormattingConversionService;

public class ConverterRegistryDemo {

    public record CurrencyCode(String value) {
        public CurrencyCode {
            if (value == null || !Pattern.matches("[A-Z]{3}", value)) {
                throw new IllegalArgumentException(
                        "Currency code must contain exactly three uppercase letters");
            }
        }
    }

    public static final class StringToCurrencyCode
            implements Converter<String, CurrencyCode> {

        @Override
        public CurrencyCode convert(String source) {
            if (source == null) {
                throw new IllegalArgumentException("Source is required");
            }

            String normalized = source.trim().toUpperCase(Locale.ROOT);
            return new CurrencyCode(normalized);
        }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        // Explicitly register the String -> CurrencyCode type pair.
        service.addConverter(
                String.class,
                CurrencyCode.class,
                new StringToCurrencyCode());

        System.out.println("canConvert="
                + service.canConvert(String.class, CurrencyCode.class));

        CurrencyCode valid =
                service.convert(" usd ", CurrencyCode.class);
        System.out.println("converted=" + valid.value());

        try {
            service.convert("US", CurrencyCode.class);
        } catch (ConversionFailedException exception) {
            System.out.println("invalid=rejected");
        }
    }
}
```

Run from the project directory using an installed Gradle:

```bash
gradle -q run
```

If the project includes the Gradle Wrapper, use `./gradlew -q run` on Unix/macOS or `gradlew.bat -q run` on Windows. Output printed by the Java program:

```text
canConvert=true
converted=USD
invalid=rejected
```

Explanation:

- `DefaultFormattingConversionService` already includes common converters and formatters; the example merely adds a new domain type pair.
- `addConverter(String.class, CurrencyCode.class, ...)` explicitly registers the source/target type pair.
- `canConvert(...)` returns `true` because the registry has a converter for this type pair.
- `" usd "` is trimmed, normalized with `Locale.ROOT`, and produces `CurrencyCode("USD")`.
- `"US"` has an invalid length, so the record constructor throws `IllegalArgumentException`. The conversion service wraps the conversion failure into `ConversionFailedException`; the program catches it and prints a stable message.

Note that `source` passed by Spring to a converter is normally non-`null` under the `Converter` contract. The `null` check inside the example's converter is purely defensive for direct calls from Java code; null cases in the conversion system are normally handled by the service and the framework's null rules.

## 7. Registering Converters Using Java Configuration

In a Spring application, converters should be registered when the application context initializes. Two scenarios are common: using a `ConversionService` for the container and using the registry provided by Spring MVC.

### 7.1. Registering a ConversionService Bean in the Spring Container

Spring documentation establishes the convention of naming the global conversion bean `conversionService` so the container recognizes it. A configuration can look like:

```java
package demo.conversion;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultFormattingConversionService;

@Configuration
public class ConversionConfiguration {

    @Bean("conversionService")
    public ConversionService conversionService() {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        service.addConverter(
                new ConverterRegistryDemo.StringToCurrencyCode());

        return service;
    }
}
```

This configuration snippet assumes `StringToCurrencyCode` resides in its own accessible package. The snippet above reuses the inner class from `ConverterRegistryDemo` for illustration; in real projects, extract the converter into a top-level class or separate bean.

Spring can use the `conversionService` bean for container-wide conversion needs. Because the method declares return type `ConversionService` (the consumer API) while the concrete object is `DefaultFormattingConversionService` (which has the registry), converter configuration happens before returning the bean.

Do not create multiple `conversionService` beans unnecessarily. A system should have a consistent conversion strategy, and converters should be registered at startup rather than mutating the registry arbitrarily per request.

### 7.2. Registering Converters for Spring MVC

When the target is forms, query parameters, or MVC controller binding data, the direct extension point is implementing `WebMvcConfigurer` and overriding `addFormatters(FormatterRegistry registry)`:

```java
package demo.conversion;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new ConverterRegistryDemo.StringToCurrencyCode());
    }
}
```

Spring MVC uses this registry in its conversion/formatting system. Parameters like `@RequestParam CurrencyCode currency` or `CurrencyCode` properties inside `@ModelAttribute` objects can receive strings and convert them via the converter along matching MVC paths.

In a Spring Boot application, normally you only add a `WebMvcConfigurer` to extend the existing MVC configuration; do not add `@EnableWebMvc` solely to register a converter, as that annotation alters how Boot auto-configures MVC. Avoid creating two separate registries and assuming a converter registered in one automatically appears in the other.

### 7.3. Registering as a Spring-Managed Converter Bean

A converter can be declared as its own bean:

```java
@Bean
public Converter<String, CurrencyCode> currencyCodeConverter() {
    return new StringToCurrencyCode();
}
```

However, the mere existence of a `Converter` bean does **not mean** every `ConversionService` automatically picks it up across all application types. Integration depends on container configuration, Spring Boot, or the MVC registry. If you want certainty in MVC, register it inside `addFormatters(...)`; if you need a shared service, add it to the `conversionService` bean or an application-managed registry.

In Spring Boot, automatic collection of converter beans may be supported by auto-configuration specific to your Boot version. Verify your application's integration path rather than relying on one universal rule across every Spring context.

## 8. Using Converters with DataBinder and Controllers

`DataBinder` uses Spring's conversion mechanism to bind data to property types. Example DTO with a field:

```java
public class PaymentForm {
    private CurrencyCode currency;

    public CurrencyCode getCurrency() {
        return currency;
    }

    public void setCurrency(CurrencyCode currency) {
        this.currency = currency;
    }
}
```

When the binder receives `currency=usd`, if the conversion service is properly configured on the binder/MVC, the string can be converted to `CurrencyCode("USD")`. If no matching converter exists or the string is malformed, binding can record a type mismatch error in `BindingResult`.

The code to manually attach a conversion service to a binder is:

```java
DataBinder binder = new DataBinder(paymentForm, "payment");
binder.setConversionService(conversionService);
binder.bind(propertyValues);
```

This snippet assumes `PaymentForm`, `ConversionService`, and `PropertyValues` are already prepared. `DataBinder#setConversionService(...)` configures the service used during binding; call it when constructing the binder, before binding. Do not mutate the service's registry per binder.

In Spring MVC, `WebDataBinder` is created and configured per request. `WebMvcConfigurer.addFormatters(...)` is the right place to register shared conversions across MVC. `@InitBinder` can add local configuration for a single controller, yet do not confuse a validator with a converter: a converter transforms types, while a validator checks rules on already-converted values.

## 9. Registering Converter Factories and Generic Converters

### 9.1. ConverterFactory

When multiple target types belong to the same family, `ConverterFactory<S,R>` lets you create a concrete converter for each target type `T extends R`. For example, converting strings to multiple enum types:

```java
public final class StringToEnumConverterFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {

        return source -> {
            String value = source.trim();
            return (T) Enum.valueOf(targetType, value);
        };
    }
}
```

This illustrative snippet highlights the generic mechanism; production code must consider unchecked cast warnings, enum constant case-sensitivity, and error reporting when a name does not exist. Use helper methods that check or normalize values per API contract. Register via `registry.addConverterFactory(new StringToEnumConverterFactory())`.

A factory is useful when the same rule applies to a family of targets; do not use it to convert unrelated domain types merely to reduce class count.

### 9.2. GenericConverter

`GenericConverter` lets you declare multiple `ConvertiblePair`s and receive source/target `TypeDescriptor`s:

```java
Set<ConvertiblePair> pairs = Set.of(
        new ConvertiblePair(String.class, CurrencyCode.class));

@Override
public Set<ConvertiblePair> getConvertibleTypes() {
    return pairs;
}

@Override
public Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType) {
    // Convert according to declared metadata and types.
}
```

This is a structural excerpt: running it requires full `GenericConverter` implementation, imports, and conversion logic. `GenericConverter` is especially useful when conversion selection depends on generic element types or annotations on fields/parameters. If you only need a single simple pair, stick with `Converter<S,T>`.

### 9.3. removeConvertible

`ConverterRegistry` provides `removeConvertible(sourceType, targetType)` to remove registered converters for a type pair. Use it only when intentionally configuring or assembling a registry; mutating a global registry after the application is serving requests can cause conversion behavior to shift unexpectedly mid-operation.

If different converters are needed in different contexts, create separate registries/services per context rather than repeatedly adding and removing a shared converter pair.

## 10. Handling Null, Empty Strings, and Conversion Errors

A typical `Converter<S,T>` receives a non-null `source` under the API contract. Null handling is usually decided by `ConversionService` or the binding layer. An empty string `""`, however, is an actual `String` value, not null. Define rules explicitly:

- Is an empty string considered missing?
- Is leading/trailing whitespace trimmed?
- Is letter casing normalized?
- Is the code locale-sensitive?
- If syntax is invalid, does it throw `IllegalArgumentException` with a sufficiently clear message?

With the example converter, `trim()` removes outer whitespace and `Locale.ROOT` normalizes the code independently of machine locale. It accepts only three A–Z characters. That is the example's contract for alphabetic currency codes; it does not check whether the code exists in the ISO catalog or whether the application supports that currency. If catalog validation is required, consider an appropriately designed lookup service/cache; do not cram network/database calls into a shared converter without considering thread safety and performance.

When a converter cannot convert a value, throwing `IllegalArgumentException` is the Spring-supported signal. Do not return a fake value like `CurrencyCode("XXX")` just to avoid exceptions unless that is genuinely a valid default under the domain contract.

## 11. Converter and Formatter in Spring MVC

Spring MVC uses the conversion/formatting system to process data from request parameters and bound properties. `FormatterRegistry` extends converter registration to also support formatters.

Example:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(new StringToCurrencyCode());
    registry.addFormatter(new CurrencyCodeFormatter());
}
```

This illustrative snippet shows both types coexisting in the registry; `CurrencyCodeFormatter` needs a separate `Formatter<CurrencyCode>` implementation. Converters fit type transformation; formatters fit locale-aware parsing/printing.

For JSON requests via `@RequestBody`, Spring MVC normally uses an `HttpMessageConverter` (such as Jackson) to deserialize JSON. Registering a converter in `FormatterRegistry` **does not guarantee** Jackson automatically uses it when reading JSON. If JSON conversion is required, configure an appropriate Jackson serializer/deserializer/module or use well-structured JSON types. Do not extrapolate JSON behavior from `@RequestParam` or `@ModelAttribute` examples.

## 12. Testing ConverterRegistry

Converter tests should cover at least these cases:

| Case | What to verify |
| --- | --- |
| Registered type pair | `canConvert(String.class, CurrencyCode.class)` returns `true` |
| Valid conversion | `"usd"` produces `CurrencyCode("USD")` |
| Whitespace | Trimming behavior matches contract |
| Wrong length | Rejects `"US"` with an appropriate exception |
| Empty string | Follows defined policy, never fabricates a fake code |
| Unsupported type pair | `canConvert(...)` returns `false` or conversion fails per API |
| MVC query/form | Converter works through MVC's registry |
| JSON body | Test Jackson converter/deserializer separately |
| Multi-threaded use | Converter holds no request state and is thread-safe |
| Context configuration | No unintended duplicate registries or conflicting converters |

A unit test can instantiate `DefaultFormattingConversionService`, add the converter, and assert `convert(...)`. A Spring MVC integration test should bootstrap the application context and send real requests via `MockMvc` to ensure the converter is genuinely used by the MVC registry.

Do not test only `canConvert` and conclude the converter works: that method mainly answers whether the type pair is convertible, without testing every source value.

## 13. Common Mistakes

1. **Confusing ConverterRegistry with ConversionService:** the registry registers, the service converts. Knowing a type pair is registered does not mean every input value is valid.
2. **Registering the wrong direction:** `String → CurrencyCode` differs from `CurrencyCode → String`. Check source and target carefully.
3. **Not declaring generics explicitly:** raw converters obscure type-pair inference; use `Converter<S,T>` with proper type arguments.
4. **Assuming a Converter bean is automatically used by every service:** bean collection depends on configuration/Boot; in MVC use `addFormatters(...)`.
5. **Creating a ConversionService without the right bean name or without wiring it into the target context:** if you want the container to recognize a global service, follow the bean name/configuration Spring requires; for MVC, configure MVC's registry.
6. **Creating a new service for every request:** conversion services are designed to be initialized once and shared; recreating them repeatedly wastes resources and fragments converters.
7. **Stateful converters with mutable fields:** multiple requests may share the same converter; never store per-request data in fields.
8. **Not handling bad input:** a converter should throw an appropriate exception rather than silently returning an incorrect value.
9. **Confusing converters with validators:** converters produce target-typed values; validators check rules on values once obtained.
10. **Using Converter instead of Formatter for locale-sensitive data:** dates/numbers displayed by locale usually require `Formatter`.
11. **Assuming ConverterRegistry configures Jackson JSON:** Spring MVC message converters and Jackson have separate integration paths.
12. **Unintentionally registering multiple converters for the same pair:** can cause unpredictable behavior when contexts are configured multiple times. Centralize registration in one clear place and test it.
13. **Not separating “no converter” from “converter rejected value”:** one is a missing capability for the type pair; the other is a concrete value failing conversion.

## 14. Practice Roadmap

1. Create a `Converter<String, CurrencyCode>` and run the console example.
2. Replace generic registration with the `addConverter(String.class, CurrencyCode.class, converter)` overload; confirm identical output.
3. Add another domain type pair and its own converter, observing `canConvert` per pair.
4. Register the converter in `DefaultFormattingConversionService` as shown.
5. Move configuration to `WebMvcConfigurer.addFormatters(...)` and test `@RequestParam`/`@ModelAttribute`.
6. Write tests for empty strings, whitespace, invalid characters, and exceptions.
7. Try `ConverterFactory` for a group of enums, then evaluate whether generics genuinely reduce code.
8. Only move to `GenericConverter` when metadata or multiple conversion pairs are needed.

**Self-check:** If `registry.addConverter(String.class, CurrencyCode.class, converter)` has been called, what makes `canConvert(String.class, CurrencyCode.class)` return true? Why can the string `"US"` still fail? In MVC, why must you register the converter in the appropriate registry instead of merely instantiating a `Converter` object?

## Official References

- [Spring Framework 6.2 — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [Spring Framework 6.2 — Converter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/Converter.html)
- [Spring Framework 6.2 — ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
- [Spring Framework 6.2 — GenericConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
- [Spring Framework 6.2 — ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/ConversionService.html)
