# ConvertiblePair and Declaring Conversion Scope in Spring Framework

In Spring's type conversion system, a converter needs to advertise **which source type can be converted into which target type**. For `GenericConverter`, this information is described by `GenericConverter.ConvertiblePair` and returned from `getConvertibleTypes()`.

A `ConvertiblePair` is a directed pair:

\[
(\text{sourceType},\ \text{targetType})
\]

For example, `String → Money` is different from `Money → String`. Registering the first direction does not automatically create a rule for the reverse direction.

This lesson covers the structure of `ConvertiblePair`, how to declare one or multiple pairs, the registry lookup mechanism, the role of `TypeDescriptor`, `ConditionalGenericConverter`, how to register in Spring MVC, and a runnable Java 17/Spring 6.2 program.

## 1. What Is ConvertiblePair?

`ConvertiblePair` is a static nested class inside `GenericConverter`, in the `org.springframework.core.convert.converter` package. It holds two Java classes: the source type and the target type. It does not parse data, does not hold input values, and is not a standalone converter.

Key signature of `GenericConverter`:

```java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
```

`getConvertibleTypes()` returns the set of type pairs supported by the converter. `convert(...)` receives the source object, metadata describing the source/target fields, and produces the target object.

How to create a pair:

```java
new GenericConverter.ConvertiblePair(
        String.class, Money.class);
```

Read in exact order: `String.class` is the source, `Money.class` is the target. Swapping the two arguments declares a different conversion.

A conditional converter may return `null` from `getConvertibleTypes()` to indicate that all type pairs should be considered conditionally. This case is only appropriate for converters implementing `ConditionalConverter`; in typical applications, advertise concrete pairs.

## 2. Conversion Scope Is a Directed Pair

| Type Pair | Meaning |
| --- | --- |
| `String → CurrencyCode` | Parse a string into a currency code |
| `CurrencyCode → String` | Print a currency code as a string |
| `String → Money` | Parse monetary text into a domain type |
| `BigDecimal → Money` | Convert a decimal number into a domain type |
| `String → LocalDate` | Parse a string into a date according to formatting rules |

The two conversion directions are two independent pairs. If the UI needs both input and display of data, register a reverse converter or consider `Formatter<T>`, which has both `parse` and `print`.

A converter should only declare pairs it can actually handle. Advertising `Object → Money` when the code only knows how to handle `String` and `BigDecimal` is a broken contract; the registry could pick the converter for an unsuitable source.

## 3. Declaring One Pair or Multiple Pairs?

### 3.1. Converter for a Single Pair

If there is only one fixed pair, prefer `Converter<S,T>`:

```java
public final class StringToCurrencyCode
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        return new CurrencyCode(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

Spring can infer the type pair from the class's generic arguments. This approach is more type-safe and concise than `GenericConverter` when metadata is unnecessary.

### 3.2. GenericConverter for Multiple Pairs

When a single component genuinely accepts multiple source or target types, declare a set of `ConvertiblePair`:

```java
private static final Set<ConvertiblePair> PAIRS = Set.of(
    new ConvertiblePair(String.class, Money.class),
    new ConvertiblePair(BigDecimal.class, Money.class)
);

@Override
public Set<ConvertiblePair> getConvertibleTypes() {
    return PAIRS;
}
```

This example advertises two different conversion paths that produce the same target type `Money`. Inside `convert(...)`, you must identify the source type and handle it accordingly.

`ConvertiblePair` is lookup metadata, not a guarantee that every value of the source type is valid. The string `"12.50"` can be parsed, whereas `"twelve"` can still be rejected by the converter.

## 4. How Does the Registry Use ConvertiblePair?

`ConverterRegistry` is the SPI for registering converters, factories, and removing rules by pair. Important methods include:

- `addConverter(Converter<?, ?> converter)`: registers a simple generic converter.
- `addConverter(sourceType, targetType, converter)`: registers a type pair explicitly.
- `addConverter(GenericConverter converter)`: registers a converter advertising one or more `ConvertiblePair`s.
- `addConverterFactory(ConverterFactory<?, ?> factory)`: registers a factory creating converters for a target type family.
- `removeConvertible(sourceType, targetType)`: removes a rule by pair.

General flow:

```text
GenericConverter
      |
      v
getConvertibleTypes()
      |
      +-- (String, Money)
      +-- (BigDecimal, Money)
      |
      v
ConverterRegistry.addConverter(...)
      |
      v
Registry stores the converter by its advertised pairs
      |
      v
ConversionService.canConvert(...) / convert(...)
      |
      v
Find a converter matching the actual source and target types
```

The pairs are used to identify candidates. When performing the actual conversion, `ConversionService` locates the converter and calls `convert(...)` with the source and target descriptors.

### 4.1. Lookup by Type Hierarchy

`GenericConversionService` can traverse the class and interface hierarchies of the source and target types. Thus, registering a pair with a supertype or interface can broaden applicability to corresponding subtypes.

For example, `CharSequence → Money` is broader than `String → Money` because many data types can implement `CharSequence`. Only choose a broad source type when the algorithm genuinely handles the entire scope.

Do not assume the registry only compares two classes with exact equality. Lookup behavior in `GenericConversionService` also considers inheritance relationships and conditional converters.

### 4.2. Multiple Converters for the Same Pair

If the same source/target is registered multiple times, converter selection is influenced by the registry, conditions, and registration order. Consolidate registrations into a deliberate configuration, avoiding multiple modules overwriting a type pair without an explicit contract.

If a pair should only be used in certain contexts, consider `ConditionalGenericConverter`. If two contexts need completely different rules, consider separate `ConversionService` instances.

## 5. What Metadata Does TypeDescriptor Add?

Unlike a simple `Converter<S,T>`, `GenericConverter` receives:

- `source`: the value to convert.
- `sourceType`: `TypeDescriptor` describing the source site.
- `targetType`: `TypeDescriptor` describing the target site.

`TypeDescriptor` can carry Java types, generic metadata of collections/maps/arrays, and annotations on fields or methods. Thanks to that, converters can make decisions based on declaration context.

For example, two fields both have collection types but different generic element types; looking only at `List.class` is not enough to know whether elements inside are `String` or `Integer`. With the right metadata, the converter can handle them accurately.

If the logic only needs to see whether the source is `String` and the target is a concrete class, `Converter<S,T>` is easier to read. Use `TypeDescriptor` when metadata truly affects conversion decisions.

## 6. ConditionalGenericConverter

`ConditionalGenericConverter` combines `GenericConverter` with the `matches(...)` condition:

```java
boolean matches(
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
```

The registry selects a conditional converter only when `matches(...)` returns `true`. For instance, the same `String → Money` pair might apply only to target fields marked with a custom annotation.

```java
public final class AccountingMoneyConverter
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(new ConvertiblePair(String.class, Money.class));
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return targetType.hasAnnotation(AccountingCurrency.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return Money.parse((String) source);
    }
}
```

This is a structural example; to compile it, you need to define the `AccountingCurrency` annotation, the `Money` type, and imports. `matches` decides whether the converter fits the metadata; `convert` must still validate the value's contents.

Do not use metadata conditions to replace string syntax checks. A converter that matches a field can still reject a malformed value at execution time.

## 7. Complete Example: Two ConvertiblePairs Producing One Money Type

The Java 17/Spring Framework 6.2 example below runs from the console, without needing Spring Boot or an HTTP server. It registers a `GenericConverter` accepting `String` and `BigDecimal` to construct the same domain type `Money`.

Project structure:

```text
convertible-pair-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/convert/ConvertiblePairDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'convertible-pair-demo'
```

`build.gradle`:

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
    mainClass = 'demo.convert.ConvertiblePairDemo'
}
```

`spring-context` pulls in the Spring modules needed for the conversion service and registry. In a Spring Boot project, let Boot manage Spring module versions instead of manually pinning a version different from the starters.

Create `src/main/java/demo/convert/ConvertiblePairDemo.java`:

```java
package demo.convert;

import java.math.BigDecimal;
import java.util.Set;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConvertiblePairDemo {

    public record Money(BigDecimal amount) {
        public Money {
            if (amount == null || amount.signum() < 0) {
                throw new IllegalArgumentException(
                        "Money amount must be non-negative");
            }
        }
    }

    public static final class MoneyConverter implements GenericConverter {

        private static final Set<ConvertiblePair> PAIRS = Set.of(
                new ConvertiblePair(String.class, Money.class),
                new ConvertiblePair(BigDecimal.class, Money.class)
        );

        @Override
        public Set<ConvertiblePair> getConvertibleTypes() {
            return PAIRS;
        }

        @Override
        public Object convert(
                Object source,
                TypeDescriptor sourceType,
                TypeDescriptor targetType) {

            if (source == null) {
                return null;
            }

            BigDecimal amount;
            if (sourceType.getObjectType() == String.class) {
                amount = new BigDecimal(((String) source).trim());
            } else if (sourceType.getObjectType() == BigDecimal.class) {
                amount = (BigDecimal) source;
            } else {
                throw new IllegalArgumentException(
                        "Unsupported source type: " + sourceType);
            }

            return new Money(amount);
        }
    }

    public static void main(String[] args) {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(new MoneyConverter());

        System.out.println("stringPair="
                + service.canConvert(String.class, Money.class));
        System.out.println("decimalPair="
                + service.canConvert(BigDecimal.class, Money.class));

        Money fromText = service.convert("125.50", Money.class);
        Money fromNumber = service.convert(
                new BigDecimal("80.25"), Money.class);

        System.out.println("fromText=" + fromText.amount().toPlainString());
        System.out.println("fromNumber="
                + fromNumber.amount().toPlainString());

        try {
            service.convert("-1.00", Money.class);
        } catch (ConversionFailedException exception) {
            System.out.println("negative=rejected");
        }
    }
}
```

Run from the project directory with Gradle installed:

```bash
gradle -q run
```

If you have the Gradle Wrapper, use `./gradlew -q run` on Unix/macOS or `gradlew.bat -q run` on Windows.

Stdout printed by the Java program:

```text
stringPair=true
decimalPair=true
fromText=125.50
fromNumber=80.25
negative=rejected
```

### Result Analysis

- `getConvertibleTypes()` advertises two pairs: `String → Money` and `BigDecimal → Money`.
- `addConverter(new MoneyConverter())` registers the converter and lets the registry read the pairs from `getConvertibleTypes()`.
- `canConvert(...)` checks whether the registry can convert the type pair.
- When the source is a String, the converter parses it into `BigDecimal`; when the source is already `BigDecimal`, it uses it directly.
- The `Money` constructor rejects negative numbers. The converter is found, but the specific value is rejected; Spring surfaces the error via `ConversionFailedException`.

Therefore, `ConvertiblePair` defines the **type scope**; `convert(...)` processes **concrete values**. These two steps cannot replace each other.

## 8. Registration in Spring Configuration and Spring MVC

### 8.1. ConversionService Bean

You can register converters in a Spring-managed conversion service:

```java
@Configuration
public class ConversionConfiguration {

    @Bean
    public ConfigurableConversionService conversionService() {
        DefaultConversionService service =
                new DefaultConversionService();
        service.addConverter(new MoneyConverter());
        return service;
    }
}
```

This is a Spring configuration class requiring imports and the `MoneyConverter` class in an appropriate package. `DefaultConversionService` both provides default conversions and implements the registry to add type pairs.

Spring uses a global conversion service bean convention named `conversionService` in mechanisms that look up this bean. Avoid declaring multiple beans for the same role without reason, and verify which bean the actual context uses.

### 8.2. Registration for Spring MVC

When you want a converter to serve Spring MVC binding, implement `WebMvcConfigurer.addFormatters(FormatterRegistry registry)`:

```java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new MoneyConverter());
    }
}
```

The converter is registered in the formatter registry used by MVC. Query parameters or form properties of type `Money` can be converted from strings when using binding paths that support that conversion service.

In Spring Boot, usually you only need to add a `WebMvcConfigurer` to extend MVC; do not add `@EnableWebMvc` solely to register a converter because it can alter Boot's auto-configuration mechanism.

Creating a standalone `GenericConverter` bean does not guarantee every registry in every application context will pick it up automatically. Register it with the exact conversion service or registry needed by the consuming layer.

### 8.3. DataBinder and JSON

`DataBinder` can use a conversion service to convert properties during binding. It can be configured manually before calling `bind(...)`:

```java
DataBinder binder = new DataBinder(form, "payment");
binder.setConversionService(conversionService);
binder.bind(propertyValues);
```

This is an excerpt requiring corresponding `form`, `PropertyValues`, and `ConversionService` objects. The converter must be present in the service attached to the binder.

For `@RequestBody` JSON, Spring typically uses an `HttpMessageConverter` such as Jackson to deserialize. A converter registered in MVC `FormatterRegistry` does not automatically become a Jackson deserializer. Configure a Jackson module/serializer/deserializer if the JSON type needs custom handling.

## 9. Distinguishing GenericConverter from ConverterFactory

`ConverterFactory<S,R>` is suitable when one source type converts to many target types in the same family. For example, `String → multiple concrete enums`: the factory receives the target class and creates the right converter for that enum.

`GenericConverter` is suitable when the converter needs to advertise multiple specific source/target pairs, possibly from different families, or needs `TypeDescriptor` metadata.

| Requirement | Suitable SPI |
| --- | --- |
| A single `String → CurrencyCode` pair | `Converter<S,T>` |
| One source converting to multiple enums | `ConverterFactory<S,R>` |
| Multiple pairs such as `String → Money`, `BigDecimal → Money` | `GenericConverter` |
| Depends on annotation/generic metadata | `ConditionalGenericConverter` |
| Locale-sensitive text parsing and printing | `Formatter<T>` |

Choose the simplest SPI that meets the requirement. `GenericConverter` is flexible but less type-safe than `Converter<S,T>` and requires managing casts yourself.

## 10. Notes When Declaring ConvertiblePair Sets

### 10.1. Do Not Advertise Pairs the Converter Cannot Handle

If advertising `String → Money`, the converter must handle any String within that contract or reject invalid values clearly. If the source is broad such as `Object`, ensure the algorithm genuinely supports the entire range.

### 10.2. Do Not Confuse the Two Conversion Directions

`String → Money` does not automatically provide `Money → String`. If display formatting is also needed, register the reverse direction separately or use `Formatter`.

### 10.3. Do Not Confuse ConvertiblePair with TypeDescriptor

`ConvertiblePair` declares a pair of classes. `TypeDescriptor` provides detailed metadata for a single conversion invocation. When generic types or annotations are needed, inspect the descriptor rather than just `source.getClass()`.

### 10.4. Null Differs from Empty String

`null` means no source object; `""` is a String of length 0. The conversion service has its own null rules. The converter still needs to define how to handle empty strings, whitespace, invalid formats, and boundary values; never manufacture fake values to mask errors.

### 10.5. Avoid Shared Mutable Converters

Conversion services are normally created at application startup and shared across threads. Converters should be stateless or have immutable state. Do not store per-request data or current user information in fields.

## 11. Testing Type Pairs and Converters

| Test | What to Verify |
| --- | --- |
| String source pair | `canConvert(String.class, Money.class)` is true |
| BigDecimal source pair | `canConvert(BigDecimal.class, Money.class)` is true |
| Valid string | Parses the number accurately and creates Money |
| BigDecimal | Preserves decimal precision |
| Negative number | Converter/constructor rejects with a cause error |
| Unsupported pair | Does not report unintended support |
| Supertype/interface | Applies only if the converter is designed for that scope |
| Metadata | Conditional converter matches only fields with the right annotation/generic |
| MVC | Converter is registered in the proper MVC registry |
| JSON | Test Jackson configuration separately |

Do not test only `canConvert(...)`. It indicates a type-level conversion path exists; it does not verify that every concrete value is accepted. You must call `convert(...)` with both valid and invalid data.

## 12. Common Mistakes

1. **Swapping source and target:** `(Money, String)` differs from `(String, Money)`.
2. **Forgetting to declare a pair:** the code has a BigDecimal branch, yet `getConvertibleTypes()` does not advertise that pair, preventing the registry from finding the converter for that source.
3. **Advertising a pair without handling it:** the registry finds the converter, yet `convert(...)` does not know how to process the source.
4. **Using GenericConverter for one simple pair:** `Converter<S,T>` is clearer and more type-safe.
5. **Ignoring TypeDescriptor:** logic depends on annotations/generics, yet only inspects runtime classes.
6. **Using matches() to check content:** `matches` fits metadata; `convert` checks concrete values.
7. **Advertising an overly broad Object pair:** can cause the converter to be selected for unexpected types.
8. **Assuming a pair is bidirectional:** the reverse direction must be registered separately.
9. **Creating a bean while forgetting the registry:** a converter not used by the conversion service has no effect.
10. **Duplicate registration in multiple places:** ordering and conditions can make converter selection unpredictable.
11. **Failing to distinguish missing converter from rejected value:** these are two distinct error categories.
12. **Assuming MVC converters automatically apply to Jackson:** JSON deserialization uses its own mechanism.

## 13. Self-Practice Exercises

1. Add a `Long → Money` pair and a corresponding branch in `convert(...)`. Verify `canConvert(Long.class, Money.class)`.
2. Call `Money → String` conversion before registering the reverse pair. Then add a reverse converter and compare.
3. Try a `CharSequence → Money` source pair. Explain why it is broader than `String → Money`.
4. Write a `ConditionalGenericConverter` that applies only when the target field carries a custom annotation.
5. Test null, empty string, whitespace, negative numbers, and oversized numbers; define the converter's policy.
6. Register the converter via `WebMvcConfigurer.addFormatters(...)` and test an endpoint accepting `Money` from a query parameter.

You have mastered this lesson when you can explain: **ConvertiblePair advertises scope; the registry uses pairs to locate converters; TypeDescriptor describes context; convert processes actual values.**

## References

- [Spring Framework 6.2 — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework — GenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [Spring Framework — GenericConverter.ConvertiblePair Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/GenericConverter.ConvertiblePair.html)
- [Spring Framework — ConditionalGenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [Spring Framework — TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Spring Framework — ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
