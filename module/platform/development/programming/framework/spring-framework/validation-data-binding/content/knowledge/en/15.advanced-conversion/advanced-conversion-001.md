# GenericConverter and Multiple Source–Target Type Pairs in Spring

## 1. When Is GenericConverter Needed?

Spring has a type conversion system to transform an input value into the type required by a property, constructor, or API. For example, a form submits `"42"` while the Java object needs a `Long`; a query parameter sends `"SHIPPED"` while the model needs the `OrderStatus` enum.

For a simple type pair, the `Converter<S, T>` interface is the natural choice:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

If a class must handle **multiple source–target type pairs**, or if the conversion decision depends on field/parameter metadata, Spring provides **`GenericConverter`**. It is more flexible than `Converter`: it declares a set of `ConvertiblePair`, receives the source value as an `Object`, and is provided with the `TypeDescriptor` of both source and target.

For example, a single converter can simultaneously support:

| Source Type | Target Type | Meaning |
| --- | --- | --- |
| `String` | `CustomerId` | Convert a numeric string into a customer identifier |
| `Long` | `CustomerId` | Wrap an already-typed number into an identifier |
| `String` | `OrderStatus` | Convert a status code into an enum |

A single `GenericConverter` can implement all three pairs in the same class. Spring uses the list of type pairs to find a matching converter, then calls `convert(source, sourceType, targetType)`.

**`TypeDescriptor` is the key differentiator.** It carries additional information about generic types and declaration context such as field, method parameter, and annotations. Thanks to this, a converter can distinguish `List<Integer>` from `List<String>` even though both have the raw type `List.class`.

This lesson uses **Java 17+ and Spring Framework 6.2.x**. After finishing it, you will be able to:

- Declare multiple `ConvertiblePair` entries in `getConvertibleTypes()`.
- Write conversion logic using source and target `TypeDescriptor`s.
- Register a converter with a `ConversionService`.
- Understand when `ConditionalGenericConverter` and `matches(...)` are needed.
- Distinguish `GenericConverter` from `Converter`, `ConverterFactory`, and `ConversionService`.
- Test successful conversions, failures, and generic data.

## 2. Interfaces in the Conversion System

Spring provides several different SPIs, each suited to a different level of complexity:

| API | Scope | When to Use |
| --- | --- | --- |
| `Converter<S, T>` | A single source–target type pair | Simple logic, clear static types |
| `ConverterFactory<S, R>` | One source to a family of target types sharing a common base type | Multiple target subtypes sharing the same rule |
| `GenericConverter` | Multiple source–target type pairs, with `TypeDescriptor` metadata | Multiple types or needing generic/annotation context |
| `ConditionalGenericConverter` | Like GenericConverter, with an added converter selection condition | Apply only when the field/parameter satisfies a condition |
| `ConversionService` | Runtime API to query and perform conversion | Component that invokes conversion, not a required SPI for writing converters |

Do not choose `GenericConverter` just because it is more powerful. Spring documentation recommends preferring `Converter` or `ConverterFactory` when they already meet the requirements, as they are easier to read and more compile-time type-safe.

### What Methods Does GenericConverter Have?

Core signature:

~~~java
public interface GenericConverter {

    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
~~~

This is an API signature for study, not a custom class replacing Spring.

- `getConvertibleTypes()` returns the set of source class → target class pairs that the converter can handle.
- `convert(...)` performs the conversion. `source` has type `Object`; therefore, it must be checked/interpreted based on the descriptor or actual class.
- `sourceType` describes the source type and declaration context.
- `targetType` describes the target type, including generic or annotation metadata if present.
- If no pair matches, the converter should not be registered as if it supports that type.

`GenericConverter.ConvertiblePair` stores two classes: source and target. A pair `String.class → CustomerId.class` does not automatically mean the converter supports `Long.class → CustomerId.class`; to support both, both must be declared.

## 3. ConvertiblePair: Registering Multiple Type Pairs

A converter can return multiple pairs in a single set:

~~~java
@Override
public Set<ConvertiblePair> getConvertibleTypes() {
    return Set.of(
            new ConvertiblePair(String.class, CustomerId.class),
            new ConvertiblePair(Long.class, CustomerId.class),
            new ConvertiblePair(String.class, OrderStatus.class)
    );
}
~~~

This is a fragment inside a class implementing `GenericConverter`. The set of pairs must be consistent with the branches that `convert(...)` actually handles.

When `ConversionService` looks up a conversion:

1. Receives the source type and target type, optionally accompanied by `TypeDescriptor`.
2. Finds a converter with a compatible `ConvertiblePair`.
3. If the converter is conditional, also checks `matches(...)`.
4. Calls `convert(...)` with the source and both descriptors.
5. Returns an object of the target type or throws a conversion error if the data is invalid.

**Registering a type pair does not mean conversion will always succeed.** For example, `"abc"` still has source type `String` and target `CustomerId` matching the registered pair, yet the number-parsing logic can fail. Data errors must be represented by an appropriate conversion exception, not by returning a fake target object.

## 4. Complete Example: One GenericConverter Handling Three Type Pairs

The example uses a customer identifier and order status. The goal is to show that a single converter can handle multiple pairs without writing three separate `Converter` classes.

### 4.1. Create the Gradle Project

Structure:

~~~text
generic-converter-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/GenericConverterDemo.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'generic-converter-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-core:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.GenericConverterDemo'
}
~~~

`spring-core` contains the conversion system. The example pins Spring Framework 6.2.14 for reproducibility; in an actual Spring Boot project, let Boot's BOM manage compatible versions.

### 4.2. Runnable Java File

File `src/main/java/demo/GenericConverterDemo.java`:

~~~java
package demo;

import java.util.Set;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.core.convert.support.GenericConversionService;

public class GenericConverterDemo {

    public record CustomerId(long value) {}

    public enum OrderStatus {
        CREATED, SHIPPED, CANCELLED
    }

    public static final class CatalogConverter
            implements GenericConverter {

        @Override
        public Set<ConvertiblePair> getConvertibleTypes() {
            return Set.of(
                    new ConvertiblePair(
                            String.class, CustomerId.class),
                    new ConvertiblePair(
                            Long.class, CustomerId.class),
                    new ConvertiblePair(
                            String.class, OrderStatus.class)
            );
        }

        @Override
        public Object convert(
                Object source,
                org.springframework.core.convert.TypeDescriptor sourceType,
                org.springframework.core.convert.TypeDescriptor targetType) {

            if (source == null) {
                return null;
            }

            Class<?> target = targetType.getObjectType();
            Class<?> origin = sourceType.getObjectType();

            if (target == CustomerId.class) {
                if (origin == String.class) {
                    return new CustomerId(
                            Long.parseLong((String) source));
                }
                if (origin == Long.class) {
                    return new CustomerId((Long) source);
                }
            }

            if (target == OrderStatus.class
                    && origin == String.class) {
                return OrderStatus.valueOf(
                        ((String) source).trim().toUpperCase());
            }

            throw new IllegalArgumentException(
                    "Unsupported type pair: "
                    + origin.getSimpleName() + " -> "
                    + target.getSimpleName());
        }
    }

    public static void main(String[] args) {
        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new CatalogConverter());

        CustomerId fromText =
                service.convert("42", CustomerId.class);
        CustomerId fromNumber =
                service.convert(7L, CustomerId.class);
        OrderStatus status =
                service.convert("shipped", OrderStatus.class);

        System.out.println("fromText=" + fromText.value());
        System.out.println("fromNumber=" + fromNumber.value());
        System.out.println("status=" + status);
    }
}
~~~

Key components:

- `CatalogConverter` advertises three pairs in `getConvertibleTypes()`.
- `GenericConversionService` is the registry/service allowing calls to `addConverter(...)`.
- `convert("42", CustomerId.class)` selects the `String → CustomerId` pair.
- `convert(7L, CustomerId.class)` selects the `Long → CustomerId` pair.
- `convert("shipped", OrderStatus.class)` selects the `String → OrderStatus` pair.
- `getObjectType()` returns the actual boxed class for primitive types if applicable; this example only uses wrapper/record/enum types.

Run in the project directory that has the Gradle Wrapper:

~~~bash
./gradlew run
~~~

On Windows:

~~~powershell
.\gradlew.bat run
~~~

Stdout of the Java program:

~~~text
fromText=42
fromNumber=7
status=SHIPPED
~~~

`GenericConversionService` is used here to focus on the three custom pairs, avoiding mixing with built-in converters of `DefaultConversionService`. When an application also wants Spring's default conversions (String → number, enum, collection, etc.), consider `DefaultConversionService` and register additional converters.

### 4.3. Adding Conversion Error Handling

The current example uses `Long.parseLong` and `OrderStatus.valueOf`. If the input is invalid, these JDK methods can throw `NumberFormatException` or `IllegalArgumentException`. In a production system, ensure errors are wrapped/interpreted according to Spring's conversion contract.

You can explicitly throw `org.springframework.core.convert.ConversionFailedException` when you want to provide source/target metadata:

~~~java
throw new ConversionFailedException(
        sourceType,
        targetType,
        source,
        new IllegalArgumentException("Invalid identifier")
);
~~~

This is a fragment inside `convert(...)`; `sourceType` and `targetType` here are the `TypeDescriptor` parameters of the method. If an appropriate message is needed, do not include sensitive raw input in the exception message. For a short demo, JDK exceptions are enough to illustrate invalid data cases; Spring's conversion infrastructure can wrap them into conversion errors at the calling layer.

## 5. TypeDescriptor: Metadata Beyond Raw Class

`GenericConverter` receives both raw `Class` and `TypeDescriptor`. Therefore, it can use information that `Class<?>` alone cannot retain.

For example, two declarations:

~~~java
List<Integer> quantities;
List<String> labels;
~~~

Both have raw type `List.class` at runtime due to type erasure. However, `TypeDescriptor` can represent the element type:

- the descriptor for `List<Integer>` knows the desired element is `Integer`;
- the descriptor for `List<String>` knows the desired element is `String`.

Similarly, a descriptor can expose annotations on a field or method parameter. That allows a converter to differentiate conversion behavior based on **where the type is declared**, not just the class name.

### 5.1. Obtaining a TypeDescriptor for a Collection

Spring provides an API to build a descriptor for a collection:

~~~java
TypeDescriptor source = TypeDescriptor.valueOf(String[].class);

TypeDescriptor target = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(Integer.class));
~~~

This fragment requires importing `org.springframework.core.convert.TypeDescriptor` and `java.util.List`. The target descriptor represents `List<Integer>` rather than simply `List.class`.

### 5.2. Using ConversionService to Convert String[] to List<Integer>

The following snippet can run inside a Java method with `DefaultConversionService`:

~~~java
DefaultConversionService service =
        new DefaultConversionService();

TypeDescriptor source = TypeDescriptor.valueOf(String[].class);
TypeDescriptor target = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));

Object converted = service.convert(
        new String[]{"10", "20"},
        source,
        target);

System.out.println(converted);
~~~

Expected stdout:

~~~text
[10, 20]
~~~

Spring has a built-in converter for array → collection and converts each element according to the element descriptor. It is precisely the `Integer` metadata that makes the result a `List<Integer>`, not a `List<String>`.

The example above uses `DefaultConversionService`'s **built-in converters**. It is not the custom converter written in section 4; the purpose is to show the benefit of generic descriptors when calling `ConversionService`.

### 5.3. Field Annotations and Metadata

`TypeDescriptor` also provides annotation metadata through the source/target declaration site. For example, a custom converter can activate only if the target field carries a marker annotation; a converter can read the annotation from `targetType` and decide how to parse.

Do not write custom reflection logic to guess all metadata if `TypeDescriptor` already provides the corresponding API. When building an annotation-conditional converter, you should typically implement `ConditionalGenericConverter` and place the criteria in `matches(...)`.

## 6. ConditionalGenericConverter: Multiple Pairs That Match Only When Conditions Are Met

A `GenericConverter` is selected by class pair. Sometimes two fields share the same source/target classes but require different conversion depending on context, for example:

- `String → AccountId` is only allowed on fields annotated with `@ExternalId`.
- `String → AccountId` on another field must be handled by a different converter.
- A conversion rule applies only if the source/target descriptor contains a specific annotation.

Spring provides `ConditionalGenericConverter`, combining `GenericConverter` and `ConditionalConverter`:

~~~java
public interface ConditionalGenericConverter
        extends GenericConverter, ConditionalConverter {
}
~~~

It includes the method:

~~~java
boolean matches(
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

This is an interface signature for study, not code redefining Spring.

Formal example:

~~~java
@Override
public boolean matches(
        TypeDescriptor sourceType,
        TypeDescriptor targetType) {
    return targetType.hasAnnotation(ExternalCode.class);
}
~~~

This is a fragment inside a `ConditionalGenericConverter` implementation. `ExternalCode` is an application-defined annotation and must be declared runtime-retained with a target suitable for fields/parameters. In addition to the annotation condition, you should check the source/target descriptors or `getConvertibleTypes()` so as not to match too broadly.

The role of `matches(...)` is to **decide whether the converter applies in the current context**, before running `convert(...)`. It is not used to perform conversion, should not mutate data, and should return consistent results.

### Avoiding Overly Broad Conditions

If `matches` simply returns `true` for any target with the annotation while the converter does not support every source type, narrow the condition using `sourceType.getObjectType()` and `targetType.getObjectType()`. A converter that matches by mistake can cause the conversion service to pick the wrong strategy or throw unexpected exceptions.

Use `ConditionalGenericConverter` when there is a genuine condition. If you only have three fixed class pairs, a plain `GenericConverter` as in section 4 is sufficient.

## 7. Multiple Type Pairs or ConverterFactory?

Two ways of extending conversion need to be distinguished:

### Multiple Discrete Pairs: GenericConverter

For example:

~~~text
String -> CustomerId
Long   -> CustomerId
String -> OrderStatus
UUID   -> CustomerId
~~~

This is a set of pairs that do not necessarily belong to the same family. `GenericConverter` represents them naturally with `Set<ConvertiblePair>`.

### One Source to a Family of Target Types: ConverterFactory

For example, a factory converting `String` into different enum subtypes:

~~~java
public interface ConverterFactory<S, R> {
    <T extends R> Converter<S, T> getConverter(Class<T> targetType);
}
~~~

This is a **condensed signature** of `ConverterFactory`. If all targets are subtypes of the same base type `R` and the logic shares a common structure, `ConverterFactory` can be cleaner than declaring every individual pair.

Comparison:

| Requirement | Choice |
| --- | --- |
| String → any enum in a family | ConverterFactory |
| String → CustomerId; Long → CustomerId; String → OrderStatus | GenericConverter |
| One fixed source type, one fixed target type | Converter<S,T> |
| Multiple pairs used only when the field has an annotation | ConditionalGenericConverter |

Do not choose `GenericConverter` just because it has the word “generic”. Nor is `ConverterFactory` a generic collection converter; a factory addresses a family of target types parameterized by class.

## 8. Registering GenericConverter in an Application

### 8.1. Registering Directly via Registry

Example from section 4:

~~~java
GenericConversionService service =
        new GenericConversionService();
service.addConverter(new CatalogConverter());
~~~

This approach suits tests, utilities, or components that need an isolated conversion service. The converter must be registered before use.

### 8.2. Using DefaultConversionService

`DefaultConversionService` provides Spring's standard set of converters. Custom converters can be registered on it:

~~~java
DefaultConversionService service =
        new DefaultConversionService();
service.addConverter(new CatalogConverter());
~~~

When doing so, application converters augment the default conversion capabilities. If two converters support the same pair, ordering/specificity and the converter selection algorithm must be considered; avoid registering unintentionally conflicting converters.

### 8.3. Spring MVC via WebMvcConfigurer

In Spring MVC, converters can be added to the registry:

~~~java
@Configuration
public class WebConversionConfig
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new CatalogConverter());
    }
}
~~~

This is a **complete configuration class** once imports for `org.springframework.context.annotation.Configuration`, `org.springframework.format.FormatterRegistry`, and `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` are added along with the appropriate `CatalogConverter` class.

`addFormatters(...)` is the registration point for converters/formatters in MVC's conversion service. Once registered, the conversion can participate in binding request parameters, form fields, and other MVC points that use the conversion service.

**Do not create a new `GenericConversionService` in a controller per request.** Conversion services are designed to be configured at startup and reused. Spring documentation describes conversion services as stateless and suitable for sharing across threads; custom converters must also follow the rule of holding no per-request mutable state.

## 9. Using ConversionService to Query and Perform Conversion

`ConversionService` is the facade for querying capability and performing conversion:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);

boolean canConvert(
        TypeDescriptor sourceType,
        TypeDescriptor targetType);

Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

These are illustrative API signatures.

Example:

~~~java
if (service.canConvert(String.class, CustomerId.class)) {
    CustomerId id = service.convert("42", CustomerId.class);
}
~~~

This snippet uses a service registered with `CatalogConverter`. `canConvert` checks **whether a type-compatible converter exists**; it does not guarantee a specific string will parse successfully. `"abc"` can still cause `convert(...)` to fail even though `canConvert(String.class, CustomerId.class)` is `true`.

When the source/target needs generic or annotation metadata, use the overload taking `TypeDescriptor` instead of just class. That is how information like `List<Integer>` or field annotations is preserved.

### Null and Primitives

Conversion with `null` requires attention to the target type. `null` cannot be assigned to a primitive like `int`; conversion may fail. For wrapper `Integer`, `null` can generally be preserved according to converter/ConversionService rules. Custom converters should explicitly decide how to handle null, never parsing or calling methods on a null source.

In the section 4 example, `convert` returns `null` if the source is null. That fits wrapper/record/enum targets but may not suit primitive properties. Callers must choose the appropriate target type and null policy.

## 10. Conversion Exceptions and Diagnostics

Common errors:

| Error | Possible Cause |
| --- | --- |
| `ConverterNotFoundException` | No converter exists for the source–target type pair |
| `ConversionFailedException` | A matching converter exists, but conversion fails when processing the value |
| `IllegalArgumentException` in converter | Invalid input or thrown directly by converter code |
| Expected converter is not invoked | Type pair is undeclared or `matches(...)` returns false |
| Collection result has wrong element type | Target `TypeDescriptor` was built without generic element metadata |

In the section 4 example, `Long.parseLong("abc")` throws `NumberFormatException`. When invoked through the conversion service, the error may be wrapped as a conversion error depending on the call path. If you need to construct a `ConversionFailedException` explicitly, you can wrap the exception with source/target descriptors as follows:

~~~java
try {
    long value = Long.parseLong((String) source);
    return new CustomerId(value);
} catch (NumberFormatException ex) {
    throw new ConversionFailedException(
            sourceType, targetType, source, ex);
}
~~~

This fragment replaces the `String → CustomerId` branch. Client-facing messages should be decided at the binding/API layer; do not let internal exception strings become the public error contract.

When a converter is used from Spring MVC, conversion exceptions can be translated into binding errors in `BindingResult`. When calling `ConversionService` directly, the caller must catch/handle exceptions according to its own contract.

## 11. Testing GenericConverter

Every declared pair must be tested, not just one representative pair.

JUnit 5 example:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.support.GenericConversionService;

import static org.junit.jupiter.api.Assertions.*;

class CatalogConverterTest {

    private final GenericConversionService service =
            new GenericConversionService();

    CatalogConverterTest() {
        service.addConverter(
                new GenericConverterDemo.CatalogConverter());
    }

    @Test
    void convertsAllDeclaredPairs() {
        var fromText = service.convert(
                "42", GenericConverterDemo.CustomerId.class);
        var fromLong = service.convert(
                7L, GenericConverterDemo.CustomerId.class);
        var status = service.convert(
                "shipped", GenericConverterDemo.OrderStatus.class);

        assertEquals(42L, fromText.value());
        assertEquals(7L, fromLong.value());
        assertEquals(
                GenericConverterDemo.OrderStatus.SHIPPED,
                status);
    }

    @Test
    void rejectsInvalidIdentifier() {
        assertThrows(RuntimeException.class, () ->
                service.convert(
                        "not-a-number",
                        GenericConverterDemo.CustomerId.class));
    }
}
~~~

This is a standalone test file when the demo class and JUnit 5 are in the same package. In `build.gradle`, add:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

The test requires JUnit dependencies on the test classpath. Asserting `RuntimeException` in the example only demonstrates that invalid conversion is rejected; for a production contract, assert `ConversionFailedException` specifically if the converter wraps errors explicitly as in section 10.

Additional cases to include:

1. Every declared `ConvertiblePair` converts valid data.
2. Invalid input for each pair.
3. Unregistered source/target types: `canConvert` and `convert`.
4. `null` and primitive targets.
5. Collection generic element descriptor.
6. `matches` true/false with annotations or field context.
7. Converter holds no state and behaves stably under concurrent requests.

## 12. Thread Safety and Converter Design Principles

Spring describes `ConversionService` as stateless and designed to be initialized at application startup and then shared across threads. However, that does not automatically make a **custom converter with mutable state** thread-safe.

A good converter:

- Does not write the current input value into a field.
- Does not store the target descriptor/rejected value of the most recent request in a field.
- Uses local variables inside `convert`.
- Only holds immutable configuration or dependencies designed to be thread-safe.
- Does not turn conversion into a business data update with side effects.
- Performs necessary null, type, and input-bound checks.

The stateless converter example in section 4 only reads the source/descriptor and returns a new object; it can be registered once and reused.

If a converter needs to query a database to turn an ID into an entity, reconsider service and transaction boundaries. Basic type conversion should normally be a pure value mapping; entity loading and authorization should belong in a separate service to avoid hiding I/O and business errors inside conversion.

## 13. Common Mistakes and Fixes

**Missing a pair in ConvertiblePair declaration.** Even if `convert` has a `Long → CustomerId` branch, if `getConvertibleTypes` does not declare that pair, the registry may not select the converter. Always cross-check both places.

**Confusing multiple pairs with multiple method overloads.** `GenericConverter` uses a single `convert(Object, TypeDescriptor, TypeDescriptor)`; branching relies on the descriptors and source. Do not declare one convert method per pair like `Converter`.

**Ignoring TypeDescriptor.** Using only `source.getClass()` and `targetType.getType()` prevents the logic from leveraging generics, annotations, and field context. When metadata matters, use the descriptor.

**Using GenericConverter for simple logic.** A static `String → Money` pair can be clearer with `Converter<String, Money>`.

**Writing overly broad matches.** A conditional converter might accept unsuitable pairs and break conversion paths. Check the source type, target type, and annotation conditions.

**Assuming canConvert guarantees a valid value.** It confirms a converter supports the type pair, not that every actual data value will parse.

**Returning null without a policy.** Null into a primitive target is invalid; null behavior must be explicitly defined.

**Sharing mutable formatters/parsers.** `SimpleDateFormat` and stateful parsers can cause race conditions if kept as shared fields. Prefer immutable APIs like `DateTimeFormatter` or create objects per invocation.

**Converters with side effects.** Conversion can run across multiple layers/framework callbacks; do not use a converter to write to a database, send messages, or update aggregates.

**Not testing generic target descriptors.** Converting `String[] → List.class` without supplying an element type can produce unintended results. For generic types, construct a `TypeDescriptor` with element/key/value metadata.

## 14. Adoption Checklist

- Choose `Converter`/`ConverterFactory` first if only one pair or a simple target type family is needed.
- Declare all `ConvertiblePair` entries supported by the converter.
- Ensure every branch in `convert` corresponds to an advertised pair.
- Use `sourceType`/`targetType` when generic metadata or annotations are meaningful.
- Use `ConditionalGenericConverter` only when a `matches` condition is needed.
- Register converters with `ConversionService`/`FormatterRegistry` at startup.
- Design null handling, parse errors, and exception mapping explicitly.
- Do not store request-specific mutable state in singleton converters.
- Test all type pairs, invalid inputs, null, generic metadata, and `matches` conditions.

## 15. Key Takeaways

`GenericConverter` is Spring's flexible SPI for conversion between **multiple source–target type pairs**. `getConvertibleTypes()` advertises the supported pairs; `convert(...)` executes logic based on values and `TypeDescriptor`s; `ConditionalGenericConverter` adds conditions via `matches(...)`. `ConversionService` is the facade for registering, querying, and executing conversions.

Choose the simplest abstraction that meets your needs: `Converter` for a single pair, `ConverterFactory` for a target family, and `GenericConverter` when multiple pairs/metadata are genuinely needed. Register once, keep converters stateless, and test each pair so conversion stays consistent across the entire application.

### Official References

- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [GenericConverter API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [ConditionalGenericConverter API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [ConversionService API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [TypeDescriptor API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
