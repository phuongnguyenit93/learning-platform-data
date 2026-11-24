# ConversionService and the convert API in Spring Framework

## 1. What Problem Does ConversionService Solve?

Spring applications often receive data as strings, while Java objects require specific data types. For example:

- Query parameter `?page=3` needs to become `Integer`.
- String `"2026-12-31"` needs to become `LocalDate`.
- Code `"PENDING"` needs to become the `OrderStatus` enum.
- A list of strings needs to become `List<Long>`.
- A customer code needs to become the domain type `CustomerCode`.

If every controller, service, or DataBinder wrote its own parsing logic, the system would have multiple conversion approaches, making it hard to reuse and hard to control errors. **`org.springframework.core.convert.ConversionService`** provides a unified API to query conversion capability and perform conversion from a source type to a target type.

Key points:

- `ConversionService` is the **consumer API** for converters: `canConvert(...)` and `convert(...)`.
- `Converter<S,T>`, `ConverterFactory<S,R>`, `GenericConverter`, and `ConditionalGenericConverter` are the **SPIs for implementing conversion logic**.
- `ConverterRegistry` is the API for registering converters into a configurable implementation.
- `GenericConversionService` is the general-purpose implementation providing mechanisms to register, look up, and execute converters.
- `DefaultConversionService` is the implementation pre-configured with Spring's common built-in converters.
- `TypeDescriptor` carries type information and declaration-site metadata, including generic types and annotations.

ConversionService is commonly used in Spring Core, DataBinder, Spring MVC, and components that need to convert data from one type to another.

## 2. The ConversionService API Contract

The core overloads of the interface look like this:

```java
public interface ConversionService {
    boolean canConvert(Class<?> sourceType, Class<?> targetType);

    <T> T convert(Object source, Class<T> targetType);

    boolean canConvert(
        TypeDescriptor sourceType, TypeDescriptor targetType
    );

    Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType
    );
}
```

This is the core part of the API; depending on the Spring version, there may be additional default methods and nullable annotations.

### canConvert(sourceType, targetType)

Asks whether the implementation is capable of performing a conversion from the source type to the target type:

```java
boolean supported =
    conversionService.canConvert(String.class, Integer.class);
```

This method is useful when you want to check capability before calling convert. However, **`true` does not guarantee that every input value can be converted**. For example, `String → Integer` is a supported type pair, yet `"abc"` still cannot be parsed into an integer. For arrays, collections, and maps, Spring may also return `true` because it can convert elements by type, even if a specific element causes an error at runtime.

If `sourceType` is `null`, the API allows checking whether conversion from a null value is possible depending on the implementation/target. `targetType` is required; passing a null target type is an argument error.

### convert(source, targetType)

This is the most common overload when the target type is known at compile time:

```java
Integer page = conversionService.convert("3", Integer.class);
LocalDate date =
    conversionService.convert("2026-12-31", LocalDate.class);
```

- `source` is the object to convert.
- `targetType` is the target class to obtain.
- The result has type `T` corresponding to the target class.
- If a conversion exception occurs, the method may throw `ConversionException`.
- If the source/target pair has no matching converter, you may encounter `ConverterNotFoundException`.
- If a converter is found but the specific data is invalid, you typically encounter `ConversionFailedException` containing the cause.

### convert(source, sourceType, targetType)

Overload using `TypeDescriptor` when more precise metadata is needed:

```java
Object converted = conversionService.convert(
    rawValue,
    sourceDescriptor,
    targetDescriptor
);
```

`TypeDescriptor` lets Spring know not only the Java class but also the **generic element type**, annotations, and the field/method location where conversion occurs. This is especially useful when converting `String[]` to `List<Integer>` or when a converter needs to inspect annotations on the target field to decide its logic.

Since Spring Framework 6.1, there is also the overload `convert(Object source, TypeDescriptor targetType)` that allows providing only the target descriptor; Spring infers the source descriptor from the actual object using `TypeDescriptor.forObject(source)`. When source is null and the caller needs to describe a specific source type, the overload taking both source and target descriptors can supply additional context.

## 3. TypeDescriptor: More Than Just a Class

Using `Class<?>` alone, `List.class` cannot tell whether the list holds `String`, `Integer`, or another type. `TypeDescriptor` additionally retains generic information and annotations from the declaration site.

For example:

```java
final class SearchRequest {
    private List<Integer> pageNumbers;

    public List<Integer> getPageNumbers() {
        return pageNumbers;
    }
}
```

For the `pageNumbers` field, we can obtain the descriptor:

```java
Field field = SearchRequest.class.getDeclaredField("pageNumbers");
TypeDescriptor descriptor = new TypeDescriptor(
    new Property(field)
);
```

The snippet above requires importing `java.lang.reflect.Field` and `org.springframework.core.convert.TypeDescriptor`; `Property` can be used from `org.springframework.core.convert.Property`. The descriptor can retain the `List<Integer>` information that `List.class` alone cannot express.

In practice, converting collections/maps often requires knowing the **element type or key/value types**. For example, when converting `String[]` to `List<Integer>`, Spring converts each element to `Integer`. The target field's TypeDescriptor makes it possible to discover that the element type is `Integer`.

### Obtaining Descriptors Directly

Some useful ways to create descriptors:

```java
TypeDescriptor.valueOf(String.class);
TypeDescriptor.forObject("hello");
TypeDescriptor.collection(List.class, TypeDescriptor.valueOf(Integer.class));
TypeDescriptor.map(
    Map.class,
    TypeDescriptor.valueOf(String.class),
    TypeDescriptor.valueOf(Long.class)
);
```

The factory methods above create descriptors for regular types, types inferred from an object, collection elements, and map keys/values. For objects with complex generics or specific annotations, you should obtain the descriptor from the field, constructor parameter, or method parameter instead of guessing metadata manually.

TypeDescriptor also has APIs to read annotations and describe object/generic types, supporting converters that rely on metadata. If two fields both have Java type `String` but one field carries a specific annotation, a converter can distinguish them when invoked through the TypeDescriptor overload.

## 4. Common Implementations

### GenericConversionService

`org.springframework.core.convert.support.GenericConversionService` is the general-purpose implementation of ConversionService/ConverterRegistry. It provides the following capabilities:

- Registering and removing converters.
- Storing mappings between source/target types and converters.
- Looking up matching converters based on `TypeDescriptor`.
- Caching lookup results to reduce repeated overhead.
- Allowing converters to expose multiple source/target pairs or matching conditions.

It is the right foundation when you want to configure a converter registry yourself.

### DefaultConversionService

`org.springframework.core.convert.support.DefaultConversionService` extends the functionality of GenericConversionService and registers many standard converters used in typical applications. For example, it can convert numeric strings, enums, booleans, collections/maps, and common types. For quick usage:

```java
ConversionService service = new DefaultConversionService();
```

A pre-configured `DefaultConversionService` instance is useful for plain Java programs or tests without needing to create a Spring ApplicationContext.

### DefaultFormattingConversionService

`org.springframework.format.support.DefaultFormattingConversionService` extends conversion with support for formatting and annotation-driven formatting. In web/form applications, formatters help convert data with display rules such as numbers and dates according to locale. Formatters should not be confused with all converters; a formatter focuses on converting between text and objects in a display context.

### Not Every ConversionService Automatically Has Custom Converters

A `ConversionService` interface does not automatically know every domain type defined by an application. If you want to convert `String → CustomerId`, you must register an appropriate converter into the registry actually being used. Registering a converter into a standalone instance while a controller or binder uses a different instance will prevent the conversion from appearing in the request flow.

## 5. Ways to Define Converters and When to Choose Each

Spring provides several SPIs with increasing flexibility.

| SPI | Use when | Example |
| --- | --- | --- |
| `Converter<S,T>` | A simple single source → target type pair | `String → CurrencyCode` |
| `ConverterFactory<S,R>` | One source converts to multiple subtypes of a target base type | `String → Enum subclasses` |
| `GenericConverter` | Need to support multiple type pairs, generics, or source/target metadata | `String[] → Collection<E>` |
| `ConditionalGenericConverter` | Need a condition to select the converter based on descriptors | Only convert when the target field has a specific annotation |

Prefer the simplest SPI that meets the requirement. Do not choose `GenericConverter` just because it is more flexible; matching logic and descriptor handling are more complex, harder to read, and harder to maintain.

### Converter<S,T>

Example:

```java
public record CurrencyCode(String value) {}

public final class StringToCurrencyCode
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        if (source == null || !source.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Currency code must contain 3 uppercase letters"
            );
        }
        return new CurrencyCode(source);
    }
}
```

This is a single type-pair converter. When the source is invalid, throw `IllegalArgumentException` to report that the value cannot be converted. Do not return `null` or a default value to mask a parsing error.

### ConverterFactory<S,R>

Used when one source type converts into many related types sharing a common base type. Enums are the classic example:

```java
public final class StringToEnumConverterFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {

        return source -> Enum.valueOf(targetType, source.trim());
    }
}
```

This is an illustrative snippet; production code must clearly decide how to handle empty strings, letter casing, and exceptions for non-existent values. The factory returns a specific converter for the requested target enum.

### GenericConverter

`GenericConverter` declares the type pairs the implementation supports via `getConvertibleTypes()` and a conversion method using descriptors. It is useful when the logic needs to know the generic element type or source/target location metadata.

```java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType
    );
}
```

This is an abridged signature highlighting the essential parts. For example, an array → collection converter needs to know the target collection's element type and then ask the ConversionService to convert each element. For simple use cases, `Converter<S,T>` is less complex and should be preferred.

### ConditionalGenericConverter

Some converters should only be selected when a condition is satisfied. `ConditionalGenericConverter` combines GenericConverter and ConditionalConverter, allowing you to implement `matches(sourceType, targetType)`.

Conceptual example: only convert `String → CustomerId` when the target field is annotated with `@ExternalId`. This condition relies on `TypeDescriptor` metadata, allowing the same Java type pair to behave differently at different declaration sites. Do not use conditional matching if a simple converter is sufficient.

## 6. Registering Converters into the Registry

`GenericConversionService` and configurable implementations provide registration methods such as `addConverter`, `addConverterFactory`, and `addGenericConverter`.

```java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToCurrencyCode());

CurrencyCode code =
    service.convert("USD", CurrencyCode.class);
```

This illustrates registration and usage on the same instance. If you create a converter without registering it into the service actually being used, calling convert will not find that custom logic.

### In a Spring ApplicationContext

In a Spring application, the ConversionService is typically configured and shared at container scope. You can register a bean named `conversionService` or configure it via Spring MVC/WebFlux mechanisms depending on the application type.

Java configuration example:

```java
@Configuration
public class ConversionConfig {

    @Bean
    public FormattingConversionService conversionService() {
        DefaultFormattingConversionService service =
            new DefaultFormattingConversionService();

        service.addConverter(new StringToCurrencyCode());
        return service;
    }
}
```

This snippet is a Spring configuration example using `@Configuration` and `@Bean`; the corresponding types must be imported. In Spring MVC, there is a mechanism to register formatters/converters in MVC configuration such as `WebMvcConfigurer#addFormatters(FormatterRegistry)`. Depending on the ApplicationContext configuration, avoid registering two competing service beans or accidentally using an instance different from the one the framework selects.

### WebMvcConfigurer

A common way to add converters for Spring MVC:

```java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCurrencyCode());
    }
}
```

This illustrates configuration in a Spring MVC application that already includes Spring Web. `FormatterRegistry` lets you add converters/formatters to the MVC formatting/conversion system. Controllers can use custom types in `@RequestParam`, `@PathVariable`, or model binding if the corresponding conversion path is used.

**Note:** registering via `WebMvcConfigurer` is an MVC configuration approach; it does not automatically register the converter into a separate `DefaultConversionService` that you instantiate directly in Java code.

## 7. Complete Java 17 Example with DefaultConversionService

The following example runs standalone on Java 17 using Spring Framework 6.1.14. The converter parses an order code string formatted as `ORD-12345` into the `OrderCode` record; the program queries `canConvert`, converts a valid value, and then demonstrates an error when given an invalid value.

Structure:

```text
conversion-service-demo/
├── pom.xml
└── src/main/java/demo/ConversionServiceDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conversion-service-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ConversionServiceDemo.java`:

```java
package demo;

import org.springframework.core.convert.ConversionException;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ConversionServiceDemo {

    public record OrderCode(String value) {}

    public static final class StringToOrderCode
            implements Converter<String, OrderCode> {

        @Override
        public OrderCode convert(String source) {
            if (source == null || !source.matches("ORD-\\d{5}")) {
                throw new IllegalArgumentException(
                    "Expected order code format ORD-12345"
                );
            }
            return new OrderCode(source);
        }
    }

    public static void main(String[] args) {
        DefaultConversionService service =
            new DefaultConversionService();

        service.addConverter(new StringToOrderCode());

        System.out.println("canConvert="
            + service.canConvert(String.class, OrderCode.class));

        OrderCode code =
            service.convert("ORD-12345", OrderCode.class);
        System.out.println("converted=" + code.value());

        try {
            service.convert("BAD", OrderCode.class);
        } catch (ConversionException ex) {
            System.out.println("failure="
                + ex.getClass().getSimpleName());
            System.out.println("cause="
                + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

From the directory containing `pom.xml`, run with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConversionServiceDemo
```

Lines printed by the program (excluding Maven logging, if any):

```text
canConvert=true
converted=ORD-12345
failure=ConversionFailedException
cause=IllegalArgumentException
```

Explanation:

1. `DefaultConversionService` already includes standard converters; we add the custom pair `String → OrderCode` via `addConverter`.
2. `canConvert(String.class, OrderCode.class)` returns `true` because the registry has a matching converter. This is a type-pair check and does not inspect the contents of `"BAD"` ahead of time.
3. `convert("ORD-12345", OrderCode.class)` invokes the converter; the string matches the pattern and is wrapped in `OrderCode`.
4. `convert("BAD", OrderCode.class)` still locates the converter, but the converter throws `IllegalArgumentException`.
5. ConversionService wraps the failure into `ConversionFailedException`; the cause preserves `IllegalArgumentException` so the caller can diagnose it.
6. The calling code catches `ConversionException`, allowing conversion failures to be handled according to the use case's contract.

## 8. canConvert Does Not Guarantee Data Is Always Valid

This point is especially important for collections, arrays, and maps.

For example, a service is capable of converting `String[] → List<Integer>`. The source and target types form a supported pair; however, the input:

```text
["10", "20", "not-a-number"]
```

cannot complete because the third element cannot be converted to `Integer`. Therefore `canConvert(...)` can return `true` while `convert(...)` still throws `ConversionException`.

The right mental model:

- `canConvert` answers the question: **is there a conversion path for this descriptor pair?**
- `convert` performs conversion on a **concrete value**, so it can still fail due to content.
- For generic/container types, conversion may proceed element by element, and an exception can originate from an inner converter.
- Do not use `canConvert` in place of input validation; nor should you call `convert` just to "try" and ignore exceptions without handling them.

If `canConvert` returns false, a suitable converter may be missing. If it returns true but convert fails, inspect the concrete value, the converter implementation, and nested element conversion.

## 9. Null, Primitives, and Target Types

`ConversionService` allows a nullable source; null handling depends on the API overload and implementation. Some principles:

- The target type must be provided; you cannot call convert with a null target class.
- The source `TypeDescriptor` can be null when the source object is null; if the source is non-null but the source descriptor is null in the full overload, that is an invalid case.
- Do not assume `null` is always equivalent to the empty string `""`. The two values have different semantics and converters may handle them differently.
- For primitive types like `int.class`, the actual target cannot hold null under Java semantics; when working with optional data, wrapper `Integer` or nullable types are usually more appropriate.
- `DefaultConversionService` has specific null conversion rules, but business logic regarding required fields should be handled in the validation layer.

When using `convert(source, targetType)` with a null source, the source descriptor is inferred according to the API rules; when the target descriptor comes from a generic/annotated field, use the TypeDescriptor overload to preserve the necessary context. If you have special nullable requirements, check the Javadoc of the active implementation and write explicit tests.

## 10. Exceptions in Conversion

Spring uses the exception hierarchy under `org.springframework.core.convert`:

| Exception | Meaning |
| --- | --- |
| `ConversionException` | Base exception class for conversion errors |
| `ConversionFailedException` | A converter was found, but the specific conversion failed |
| `ConverterNotFoundException` | No converter was found for the requested type pair |
| `ConversionService` exception contract | Convert methods may throw `ConversionException`; a null target type throws `IllegalArgumentException` |

When writing your own `Converter<S,T>`, the proper rule for unconvertible source data is to throw `IllegalArgumentException`. ConversionService normally wraps it into `ConversionFailedException` with source/target types and value metadata.

Avoid:
- Returning `null` to hide invalid input data.
- Returning a default object when parsing fails without an explicit policy.
- Throwing HTTP exceptions inside a Spring Core converter.
- Catching all `RuntimeException`s and reporting "invalid input", because the error could be a bug or misconfiguration.
- Confusing conversion errors with constraint violations: `0` converts to `Integer` successfully but may violate `@Min(1)`.

At the web layer, MVC can turn errors into `MethodArgumentTypeMismatchException`, binding errors, or request-body read exceptions depending on where the data arrives. Converters do not need to depend on HTTP; controller advice or the API boundary decides the status and response body.

## 11. Performance, Lifecycle, and Thread Safety

Spring documentation describes ConversionService as a **stateless** object by design, typically initialized at application startup and shared across multiple threads. This avoids creating a new registry per request and keeps conversion behavior consistent across the application.

Some principles:

- Register converters during startup configuration, before concurrent threads use the service.
- Once registration is complete, share the configured service; do not mutate the registry arbitrarily during individual requests.
- Converters should remain immutable or thread-safe; avoid storing request-specific data in fields of a singleton converter.
- Conversion logic should be deterministic: the same source and descriptor should yield the same result, unless a policy explicitly depends on locale/time zone.
- Do not put database lookups or remote network calls into a converter arbitrarily. A converter is usually a lightweight type-conversion step; entity lookup may require repositories/services and a different error-handling mechanism.
- GenericConversionService caches converter lookups; this helps reuse matching results, but does not guarantee that input values are always valid.

If conversion needs to vary by user/session, do not stuff state into a shared ConversionService. Create an abstraction per use case or configure clear service scopes; avoid making conversion depend on uncontrolled thread-locals.

## 12. When to Use ConversionService vs. Formatter?

**ConversionService** focuses on general-purpose type conversion, such as `String → LocalDate` or `String → CustomerId`.

**Formatter<T>** is bidirectional:
- `parse(String text, Locale locale)`: text to object.
- `print(T object, Locale locale)`: object to text.

Formatters are suited for locale-sensitive presentation data such as dates, decimals, or currencies. Spring's formatting infrastructure can register formatters with `FormattingConversionService` and integrate with MVC. If you only need one-way domain type conversion, a Converter is usually simpler.

A converter does not receive Locale information in its `convert(S source)` signature. When logic depends on locale, a formatter is the more natural choice. Avoid parsing dates with a hardcoded format inside a converter if users enter values across multiple locales.

## 13. Common Errors and Debugging

| Symptom | Cause | Where to check |
| --- | --- | --- |
| `ConverterNotFoundException` | Converter not registered or registered on the wrong instance | Check the actual registry used by the framework |
| `canConvert` returns true but convert fails | Specific value is malformed or a collection element failed | Inspect `ConversionFailedException` and `getCause()` |
| Custom converter does not run in MVC | Converter registered on a different service than MVC's service | Use `WebMvcConfigurer.addFormatters` or official MVC config |
| `List<Integer>` receives wrong elements | Generic target descriptor not provided/inferred | Check `TypeDescriptor` and nested conversion |
| Enum parsing fails due to casing | Enum conversion rules do not match input data | Normalize in converter and define a clear case policy |
| `null` produces unexpected results | Confusing null with empty string or primitive target | Check nullable semantics and write dedicated tests |
| Converter using current user data fails across requests | Singleton converter holds mutable state | Keep converters stateless/thread-safe |
| Two converters compete for the same type pair | Registry has multiple candidates or overlapping matching rules | Narrow source/target pairs or matching conditions |
| Error message returns raw input | Exception handler exposes raw data | Return stable messages, filter rejected values, and log safely internally |
| Using ConversionService to check business rules | Mixing type conversion with validation | Move business rules to Spring Validator/Bean Validation |

When debugging a conversion error, follow this sequence:

1. Note the expected **source type** and **target type**.
2. Confirm the corresponding converter is registered in the right registry.
3. Call `canConvert` to see whether the type pair is supported.
4. Call `convert` with a valid sample value and an invalid sample value.
5. If an error occurs, inspect the `ConversionException` type and `getCause()`.
6. For collections/maps, inspect element/key/value descriptors and individual elements.
7. If it only happens in MVC, verify the service used by MVC and the actual binding/argument conversion path.

## 14. Self-Check Questions

1. Is `ConversionService` a consumer API or a converter implementation SPI? What role does `Converter<S,T>` play?
2. Does `canConvert(String.class, Integer.class)` returning true guarantee that `"abc"` can be converted?
3. When should you use the `convert(Object, Class<T>)` overload, and when do you need the `TypeDescriptor` overload?
4. Why is `TypeDescriptor` useful when converting `String[]` to `List<Integer>`?
5. How does `DefaultConversionService` differ from `GenericConversionService` in terms of pre-configuration?
6. When should you use `ConverterFactory` instead of a single `Converter`?
7. What is the difference between `GenericConverter` and `ConditionalGenericConverter`?
8. Why might a custom converter registered on a standalone service not run in Spring MVC?
9. How does `ConversionFailedException` differ from `ConverterNotFoundException`?
10. Why should ConversionService be configured at startup and used as a stateless service?
11. Is a value that parses into a Java type but violates `@Min` a conversion error or a validation error?
12. Why should you not keep mutable request-specific state in a singleton converter?

**Remember:** `ConversionService` is a facade for querying capability and performing conversion. `convert` dispatches to registered converters; `TypeDescriptor` carries additional generic/annotation metadata. `canConvert` only tells you whether a conversion path exists for a type pair, not that every concrete value is valid. Choose the right SPI, register it on the same service the framework uses, and keep conversion errors separate from validation errors.

## References

- Spring Framework — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework 6.1.14 — ConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/ConversionService.html
- Spring Framework 6.1.14 — GenericConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html
- Spring Framework 6.1.14 — DefaultConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html
- Spring Framework 6.1.14 — TypeDescriptor Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html
- Spring Framework — Formatting Conversion Service: https://docs.spring.io/spring-framework/reference/core/validation/format.html
