# DefaultConversionService and Built-in Converters in Spring Framework

In Spring Framework, **`ConversionService`** is the unified interface for checking and performing conversions between Java types at runtime. Instead of writing custom logic to convert strings to numbers, enums, dates, or collections everywhere, an application can use a conversion service pre-registered with many common converters.

The key implementation is **`org.springframework.core.convert.support.DefaultConversionService`**. This class extends `GenericConversionService` and automatically registers a set of converters suitable for most applications. The main groups include **scalar converters**, **collection/array converters**, converters for certain date/time types, buffers, and common object conversions. When custom business types are needed, the application adds its own converters to the registry.

**Key takeaway:** `DefaultConversionService` includes many useful converters right after instantiation, yet it cannot guess every business rule, does not validate automatically, does not turn any string into any object, and does not guarantee that every Spring subsystem shares the exact same instance.

## 1. ConversionService and GenericConversionService

`ConversionService` is the API for executing conversions. Commonly used methods:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);

boolean canConvert(TypeDescriptor sourceType, TypeDescriptor targetType);
Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

- `canConvert(...)` asks whether the service has a suitable conversion path for the source and target types.
- `convert(...)` performs the conversion; if no matching converter exists or the data cannot be parsed, it may throw `ConversionException`, commonly `ConverterNotFoundException` or `ConversionFailedException`.
- Overloads accepting `TypeDescriptor` also retain metadata about generic types, annotations, and field/property characteristics; this is useful when converting typed collections or when conversion depends on context.

Roles in the `org.springframework.core.convert` package:

| Component | Role |
| --- | --- |
| `ConversionService` | Consumer API to check and perform conversions |
| `ConverterRegistry` | SPI to register converters, converter factories, or generic converters |
| `ConfigurableConversionService` | Combines conversion usage and converter registration capabilities |
| `GenericConversionService` | General-purpose implementation managing the registry and resolving converters |
| `DefaultConversionService` | `GenericConversionService` pre-registered with common converters |
| `ConversionServiceFactory` | Helps create a service from a configured set of converters |
| `TypeDescriptor` | Describes source/target types along with field/property/generic metadata |

A newly created `GenericConversionService` is the engine for resolving and managing converters, which **does not mean it already has the full standard converter suite**. When you need the default suite, instantiate `DefaultConversionService` or call the `DefaultConversionService.addDefaultConverters(registry)` helper on an appropriate registry.

## 2. What Does DefaultConversionService Register?

Direct usage:

~~~java
ConversionService service = new DefaultConversionService();
~~~

`DefaultConversionService`'s constructor calls `addDefaultConverters(this)`. The default suite is designed for many common scenarios. Spring documentation categorizes the notable converters into scalar, collection, and basic `Object`-to-`String` converters. Spring's source code also shows additional groups such as byte buffers, date/time, timezones, object-to-object, and Optional. The exact list depends on the Spring Framework version; when relying on a specific conversion pair, consult the Javadoc/source for the exact version your application runs.

### 2.1. Scalar Converters: Converting a Single Value

Scalars are single values such as strings, numbers, booleans, enums, locales, time types, and similar types. Common examples:

| Group | Example | Notes |
| --- | --- | --- |
| String → Number | `String -> Integer`, `String -> Long`, `String -> BigDecimal` | Malformed numeric strings will fail |
| Number → Number | `Integer -> Long`, `Integer -> Double` | Watch for overflow and precision loss |
| String → Boolean | `"true" -> Boolean` | Does not replace business validation |
| String → Character | `"A" -> Character` | Unsuitable strings may be rejected |
| String → Enum | `"ACTIVE" -> Status.ACTIVE` | Typically uses the enum constant name |
| String → UUID | `"..." -> UUID` | Requires valid UUID syntax |
| String → Locale/Currency | `"en-US" -> Locale`, `"USD" -> Currency` | Not equivalent to locale-aware currency formatting |
| String → URI/URL/Charset/Path/Pattern | Text → corresponding Java type | Each type has its own parsing rules |
| Date/time | Certain conversions between date/time types | Consider timezone, format, and version |

The table shows example groups, not a guarantee that every pair has a bidirectional converter or that every value will convert. `canConvert(true)` by type does not guarantee a concrete string can be parsed.

Example:

~~~java
DefaultConversionService service = new DefaultConversionService();

Integer age = service.convert("21", Integer.class);
Long count = service.convert(12, Long.class);
Status status = service.convert("ACTIVE", Status.class);
UUID id = service.convert(
        "123e4567-e89b-12d3-a456-426614174000", UUID.class);
~~~

This snippet assumes an enum `Status` and imports `java.util.UUID`. `age` receives 21, `count` receives 12L, `status` receives enum constant `ACTIVE`, and `id` receives the corresponding UUID. This is an illustrative snippet, not a standalone file.

### 2.2. Collection and Array Converters

DefaultConversionService registers converters to convert containers based on element converters. If Spring knows how to convert `String -> Integer`, the collection/array mechanism can reuse that rule. Common examples:

- `String[] -> List<Integer>`.
- `List<String> -> Set<Integer>`.
- `List<Integer> -> String[]` if a matching element converter exists.
- Converting between common array/collection forms.

You do not have to write a separate converter for every collection combination when element conversion is available and the container structure is supported. Spring provides converters such as `ArrayToCollectionConverter`, `CollectionToArrayConverter`, `CollectionToCollectionConverter`, and `ArrayToArrayConverter`.

Java type erasure means generic element types are not always available from raw classes. Looking at `List.class` alone does not tell whether the target list should hold Integer or String. When needed, pass `TypeDescriptor` to describe the element type.

Example converting a list of strings to a list of integers:

~~~java
DefaultConversionService service = new DefaultConversionService();

List<String> input = List.of("10", "20", "30");
TypeDescriptor sourceType = TypeDescriptor.forObject(input);
TypeDescriptor targetType = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));

@SuppressWarnings("unchecked")
List<Integer> result = (List<Integer>) service.convert(
        input, sourceType, targetType);

System.out.println(result);
~~~

Imports:

~~~java
import java.util.List;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;
~~~

Stdout:

~~~text
[10, 20, 30]
~~~

If you only call `service.convert(input, List.class)`, the target type is described too broadly; there is no information instructing Spring to convert each element to `Integer`. `TypeDescriptor.collection(...)` makes the target element type explicit.

### 2.3. Maps and Nested Objects

DefaultConversionService has converters for common Map/container scenarios depending on type pairs and version. For example, map-to-map conversion can apply element converters for keys/values when those conversion paths exist. However, converting an arbitrary Map into a DTO/entity with nested properties **is not** a general-purpose object mapping guarantee.

If you need to map key/value pairs into DTOs or transform business data structures, use schema-based data binding, a dedicated mapper, or explicit mapping code. Do not treat `DefaultConversionService` as a replacement for MapStruct, BeanUtils, or Jackson.

### 2.4. Additional Converters

Depending on the Spring version, the default suite may also register:

- Byte buffers and byte arrays/related buffer types.
- `Date -> Instant` and `Instant -> Date`.
- `String -> TimeZone`, `ZoneId -> TimeZone`.
- `ZonedDateTime -> Calendar`.
- `ObjectToObjectConverter` for certain target types having matching factory methods/constructors per Spring conventions.
- `Object -> Optional` and `Optional -> Object`.
- `IdToEntityConverter` when an entity exposes a compatible ID-lookup API.
- Fallback `Object -> String` for common string representations.

Do not treat these classes as an immutable whitelisted API. Several converters are internal implementations with conditional selection and can change across versions. Consult the Javadoc/source for your exact version when relying on a specific conversion.

## 3. Standalone Runnable Java 17+ Program

The following example uses Spring Framework `spring-core` without Spring Boot or an HTTP server. It demonstrates default conversion for numbers, enums, and collections.

Create `settings.gradle`:

~~~groovy
rootProject.name = 'default-conversion-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-core:6.2.0'
}

application {
    mainClass = 'example.DefaultConversionDemo'
}
~~~

Create `src/main/java/example/DefaultConversionDemo.java`:

~~~java
package example;

import java.util.List;
import java.util.UUID;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;

public class DefaultConversionDemo {

    enum Status {
        ACTIVE, DISABLED
    }

    public static void main(String[] args) {
        DefaultConversionService service =
                new DefaultConversionService();

        Integer age = service.convert("21", Integer.class);
        Long count = service.convert(12, Long.class);
        Status status = service.convert("ACTIVE", Status.class);
        UUID id = service.convert(
                "123e4567-e89b-12d3-a456-426614174000", UUID.class);

        List<String> source = List.of("10", "20", "30");
        TypeDescriptor sourceType = TypeDescriptor.forObject(source);
        TypeDescriptor targetType = TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(Integer.class));

        @SuppressWarnings("unchecked")
        List<Integer> numbers = (List<Integer>) service.convert(
                source, sourceType, targetType);

        System.out.println("age: " + age);
        System.out.println("count: " + count);
        System.out.println("status: " + status);
        System.out.println("uuid: " + id);
        System.out.println("numbers: " + numbers);
        System.out.println("string-to-integer: "
                + service.canConvert(String.class, Integer.class));
        System.out.println("string-to-status: "
                + service.canConvert(String.class, Status.class));
    }
}
~~~

Run from the root directory with Gradle Wrapper:

~~~bash
./gradlew run
~~~

If a compatible Gradle installation is present without a wrapper, use `gradle run`. On Windows you can use `.\gradlew.bat run`.

Expected stdout:

~~~text
age: 21
count: 12
status: ACTIVE
uuid: 123e4567-e89b-12d3-a456-426614174000
numbers: [10, 20, 30]
string-to-integer: true
string-to-status: true
~~~

The example demonstrates:

1. `DefaultConversionService`'s constructor registers the default converter suite, so there is no need to manually add a String-to-Integer converter.
2. An `Integer -> Long` converter is present, so numeric values are converted to the target type.
3. Constant name strings can be converted to enums.
4. Collection conversion reuses element converters; `TypeDescriptor` provides the target element type.
5. `canConvert(...)` checks capability by type without pre-parsing specific values.

The dependency version is pinned so the example specifies an exact version. Real projects should use a BOM/Spring Boot dependency management with project-managed versions; when upgrading versions, rerun tests to verify behavior.

## 4. Helpers for Registering the Default Converter Suite

### 4.1. `addDefaultConverters(ConverterRegistry)`

There is no need to instantiate a new `DefaultConversionService` if a suitable registry already exists. You can add the standard converter suite with:

~~~java
DefaultConversionService.addDefaultConverters(registry);
~~~

`registry` must satisfy the API requirement: not only implement `ConverterRegistry`, it must also be usable as a `ConversionService` (for example, `ConfigurableConversionService`). Therefore, do not pass an arbitrary registry that lacks conversion execution capability.

For normal usage, there is no need to call this helper after creating `new DefaultConversionService()`: the default constructor already registers those converters. Calling it repeatedly is unnecessary and can make the registry harder to reason about.

### 4.2. `addCollectionConverters(ConverterRegistry)`

There is a static method `addCollectionConverters(...)` to add the collection/array converter group. Normally, you should instantiate `DefaultConversionService` or call `addDefaultConverters(...)` to get both scalar converters and the other default groups. Only use the collection-specific helper if you thoroughly understand the existing registry and how element converters are registered.

### 4.3. `getSharedInstance()`

`DefaultConversionService.getSharedInstance()` returns a lazily initialized shared default instance. The API describes it as a fallback for code paths that cannot access a longer-lived service. When an application needs customization, the documentation recommends creating a dedicated instance rather than mutating the shared instance. This keeps configuration in tests or isolated components from altering the behavior of unrelated code sharing the process.

## 5. Using DefaultConversionService in a Spring ApplicationContext

If you want the Spring container to use a shared conversion service, you can register a bean named `conversionService`:

~~~java
@Configuration
public class ConversionConfig {

    @Bean("conversionService")
    public ConversionService conversionService() {
        return new DefaultConversionService();
    }
}
~~~

Required imports include `org.springframework.context.annotation.Configuration`, `Bean`, and `org.springframework.core.convert.ConversionService`. This is a configuration class inside a Spring application, not a standalone runnable program.

The Spring core container recognizes the special bean name `conversionService` when converting configuration/bean values. Certain other subsystems have their own registries or configuration lifecycles; do not assume this single bean automatically configures all HTTP input types, Jackson, or all PropertyEditors.

Corresponding XML example:

~~~xml
<bean id="conversionService"
      class="org.springframework.context.support.ConversionServiceFactoryBean"/>
~~~

`ConversionServiceFactoryBean` creates a service configured with default converters. Application-specific converters can be added through appropriate bean configuration.

### 5.1. Spring MVC

In Spring MVC, conversion and formatting for binding points can be configured via `WebMvcConfigurer.addFormatters(FormatterRegistry)`:

~~~java
@Configuration
public class WebConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToTicketCodeConverter());
    }
}
~~~

This snippet assumes `StringToTicketCodeConverter` already exists, along with imports for `Configuration`, `WebMvcConfigurer`, and `FormatterRegistry`. MVC also has default converters/formatters; application configuration adds custom rules to the appropriate registry.

Distinguish carefully:
- Query parameters, path variables, and form data generally go through argument resolvers/data binders, where the conversion service and formatters play a role.
- `@RequestBody` JSON is typically read by `HttpMessageConverter` and Jackson. Registering a converter in MVC's FormatterRegistry does not automatically configure Jackson to read every JSON field.
- `@ConfigurationProperties` in Spring Boot has its own configuration binding path and may require converters registered specifically for property binding.

## 6. Adding Business Converters

Suppose an application has a `TicketCode` type with format `TKT-123`. This is not a common type Spring understands out of the box. We create a converter:

~~~java
package example;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToTicketCodeConverter
        implements Converter<String, TicketCode> {

    @Override
    public TicketCode convert(String source) {
        return new TicketCode(
                source.strip().toUpperCase(Locale.ROOT));
    }
}
~~~

The snippet above is an illustrative class requiring a `TicketCode` type whose constructor validates format. Use `Locale.ROOT` for technical codes so normalization does not depend on the host machine's locale. You must also decide on a policy for null/empty strings before the converter is invoked; a separate validator handles required-field checks.

Registering the converter:

~~~java
DefaultConversionService service =
        new DefaultConversionService();

service.addConverter(new StringToTicketCodeConverter());
~~~

The service retains all default converters and adds the domain rule. If you need the reverse direction `TicketCode -> String`, create another converter; Spring does not automatically generate an inverse for a one-way converter.

### 6.1. Converter, ConverterFactory, and GenericConverter

| Kind | Use when | Example |
| --- | --- | --- |
| `Converter<S,T>` | A clear single source/target type pair | `String -> TicketCode` |
| `ConverterFactory<S,R>` | Multiple target types sharing a base type | Enum family |
| `GenericConverter` | Multiple type pairs, needing `TypeDescriptor` metadata | Rules depending on generics/annotations |
| `ConditionalGenericConverter` | Only apply when the descriptor meets a condition | Conditional conversion based on field metadata |

A small converter is usually easiest to read and test. Only use generic/conditional converters when you genuinely need multiple type pairs or metadata.

### 6.2. Do Not Accidentally Lose Default Converters

A common mistake is instantiating `new GenericConversionService()` and registering only domain converters, while the application still expects `String -> Integer` to work. `GenericConversionService` does not come with the full default suite like `DefaultConversionService`.

The simple approach:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToTicketCodeConverter());
~~~

If architectural reasons require using another registry, register default converters first and then add custom converters. Do not rewrite common numeric/collection converters if the default suite already meets your needs.

## 7. TypeDescriptor and Generic Types

Java type erasure prevents runtime code from always inferring generic element types from raw classes alone. For instance, `List<String>` and `List<Integer>` share the raw class `List.class`. The conversion service needs element type metadata to convert accurately.

Example:

~~~java
List<String> source = List.of("1", "2");
TypeDescriptor sourceDesc = TypeDescriptor.forObject(source);
TypeDescriptor targetDesc = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));

Object result = service.convert(source, sourceDesc, targetDesc);
~~~

If matching collection and element converters are registered, `result` is a list of integers. When working with JavaBean properties, Spring can read generic metadata from the property descriptor; `TypeDescriptor` also carries annotation metadata for conditional converters/formatters.

When writing generic code, avoid blind casts. Pass a target descriptor or use a helper accepting descriptors instead of only calling `convert(value, List.class)` when a list with a specific element type is required.

## 8. Null, Conversion Errors, and Limitations

### 8.1. Null Source

The `Converter<S,T>` contract guarantees that the source passed to `convert(S)` is non-null; null handling belongs to `ConversionService`'s mechanism. Many reference target types can receive null without invoking the converter. Therefore, do not use converters to replace required-field checks.

If an API requires `age`, use validation such as `@NotNull` or DTO checks. A null conversion result does not prove the request is valid.

### 8.2. Convertibility Does Not Equal Valid Value

~~~java
service.canConvert(String.class, Integer.class); // true
service.convert("not-a-number", Integer.class);  // conversion fails
~~~

`canConvert(...)` checks the type pair without pre-parsing the content. When a string is malformed, conversion fails and may be wrapped in `ConversionFailedException`. Applications should handle this appropriately at the call site: form binding may record an error in `BindingResult`, while direct service calls must handle the exception.

### 8.3. Successful Parsing Does Not Equal Valid Business Rules

The string `"0"` converts to Integer 0 successfully, yet quantity might need to be greater than 0. `"TKT-123"` may construct a TicketCode, but it does not prove the ticket exists or that the caller has permission to access it.

Distinguish clearly:
- **Conversion:** can the input be converted to the target Java type?
- **Validation:** does the data satisfy declared constraints?
- **Domain/service:** does the value satisfy system state and business invariants?
- **Authorization:** does the principal have permission to act on the resource?
- **Database:** do transactions and constraints preserve data integrity on write?

### 8.4. Precision, Locale, and Timezone

Do not use scalar conversion as a tool for locale-aware currency formatting. `BigDecimal` is suitable for decimals, but input formats and scale still need explicit rules. When parsing/printing by `Locale`, use `Formatter<T>` or a formatting service. When handling date/time, define timezone and format in the contract; do not assume converting between `LocalDate`, `Instant`, and `Date` has a single universal meaning in every context.

## 9. Thread Safety and Lifecycle

Spring describes `ConversionService` as a stateless object, typically initialized at startup and shared across multiple threads. Therefore, custom converters registered on the service should be stateless and thread-safe.

Converters should not:
- Store request-specific data in mutable fields.
- Use unguarded mutable formatters across threads.
- Call databases or networks while parsing a query parameter.
- Depend on SecurityContext to decide whether a type can be converted.
- Change behavior based on a previous request.

If rules require locale, use `Formatter<T>` with its locale parameter in `parse/print`. If database access or business state is needed, move it to the service/domain layer. Do not continuously mutate the registry after the application has started serving requests.

## 10. Testing Converters and Services

| Test case | Expectation |
| --- | --- |
| Valid String → Integer | Produces the right number |
| Integer → Long | Produces the target type |
| Valid enum name String → Enum | Produces the enum constant |
| Invalid enum name String → Enum | Controlled conversion failure |
| List<String> → List<Integer> | Elements converted using TypeDescriptor |
| Domain type with custom converter | Converts only after registration |
| `canConvert` | Accurate by type pair, independent of concrete value |
| Null | Follows null semantics; required validation still runs separately |
| Locale/timezone | Results follow the contract |
| Multi-threaded converter | No state leakage across conversions |

A simple JUnit unit test:

~~~java
@Test
void convertsStringToInteger() {
    DefaultConversionService service = new DefaultConversionService();

    assertTrue(service.canConvert(String.class, Integer.class));
    assertEquals(Integer.valueOf(21),
            service.convert("21", Integer.class));
}
~~~

This is an illustrative test method requiring JUnit 5, `DefaultConversionService`, and static assertions. For custom converters, test valid data, invalid data, and the case where the converter is not registered.

For MVC/Boot, run integration tests through the actual `MockMvc`, binder, or configuration binding if the service is registered in that subsystem. A unit test instantiating `new DefaultConversionService()` does not prove MVC or Jackson is using the same instance.

## 11. Common Errors and How to Fix Them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `ConverterNotFoundException` | Missing converter for type pair or wrong service injected | Check registry, bean, and `canConvert` |
| `ConversionFailedException` | Conversion path exists, but input failed to parse | Check format and root cause exception |
| `List.class` does not become `List<Integer>` | Target descriptor lacks element metadata | Use `TypeDescriptor.collection(...)` |
| Unit test converts, MVC does not see converter | Test uses its own instance; MVC uses another registry | Register into the right `FormatterRegistry`/MVC config |
| `@RequestBody` ignores custom converter | Jackson uses a separate deserialization pipeline | Configure Jackson/deserializer accordingly |
| Default converters disappear | Using empty `GenericConversionService` or overriding registry | Use `DefaultConversionService` or add default converters |
| `canConvert` true yet request still fails | Specific input value cannot be parsed | Test actual data, not only type pairs |
| Result depends on previous request | Converter is mutable or not thread-safe | Write stateless converters |
| Date/time shifts | Timezone/locale undefined | Use formatters and explicit time policies |
| Trying to auto-map JSON/map to entity | Conversion service is not a general object mapper | Use Jackson/DTO mapper or explicit mapping |

## 12. Adoption Checklist

1. Use `DefaultConversionService` when common Java conversions are needed without manually registering every converter.
2. Use `GenericConversionService` when intentionally managing an empty registry; register only the converters your application needs.
3. Use `ConversionService` for consuming, and `ConverterRegistry`/`ConfigurableConversionService` when registering.
4. Use `TypeDescriptor` when generic collections or field metadata affect conversion.
5. Add business converters for explicit type pairs; define the reverse direction separately when needed.
6. Register in the right scope: ApplicationContext, Spring MVC, configuration binding, or other subsystems.
7. Keep converters stateless, thread-safe, and free of I/O.
8. Separate conversion from validation, authorization, and domain rules.
9. Test both type pairs and real values, including invalid input, null, and collections.
10. Consult Javadoc/source for the exact version before relying on less common converters or internal implementation classes.

**Remember:** `DefaultConversionService` is a `GenericConversionService` pre-populated with common converters. Scalar converters handle single values, collection/array converters reuse element converters, and additional converters handle certain date/time, buffer, Optional, and common object types. Instantiating the default service and adding domain converters is a simple approach for most applications; be sure to configure and test the exact subsystem that uses it.

### References

- Spring Framework Reference — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework 6.2 Reference — Type Conversion: https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html
- Spring Framework 6.2 Javadoc — DefaultConversionService: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html
- Spring Framework 6.2 Source — DefaultConversionService.java: https://github.com/spring-projects/spring-framework/blob/6.2.x/spring-core/src/main/java/org/springframework/core/convert/support/DefaultConversionService.java
- Spring Framework Reference — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework Reference — Spring MVC Conversion and Formatting: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
