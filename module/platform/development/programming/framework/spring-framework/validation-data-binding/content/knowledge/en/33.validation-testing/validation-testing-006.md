# Testing Converter, ConverterFactory, and Conditional Converters in Spring Framework

## 1. Objectives and problem statement

Spring Framework provides a **type conversion** system in the `org.springframework.core.convert` package. Requests deliver values as strings, while controllers and domain models often use strong types: order numbers, enum states, annotated identifiers, or collection structures.

Examples:

```http
GET /api/orders?id=ord-0042
GET /api/levels?state=shipped&level=high
GET /api/code?value=VIP-A7
```

We want:
- `ord-0042` → `OrderNumber("ORD-0042")`; strings with a missing prefix, wrong length, or non-digit characters must be rejected.
- `shipped` → `OrderState.SHIPPED`, `high` → `ReviewLevel.HIGH` using **a single ConverterFactory** shared across multiple enums.
- `VIP-A7` → `PrefixedCode` **only** when the receiving target carries `@RequiredPrefix("VIP")`; without the annotation, the conditional converter should not match.
- Once registered with Spring MVC, valid query/form parameters bind properly and invalid parameters return 400 on the appropriate MVC path.

This requires three distinct testing levels:

1. **Unit tests for each converter**: verify algorithms, boundaries, and exceptions when invoked directly.
2. **Lightweight integration tests with `ConversionService`**: verify registration, source/target pairs, `TypeDescriptor`, `matches`, and exception wrapping. A correct converter that **is not selected** is still a bug.
3. **Web-layer tests with `MockMvc`**: verify conversion is actually applied by Spring MVC to `@RequestParam` and `@ModelAttribute`.

**This lesson belongs to the "Testing" section** of the **Spring Framework - validation-data-binding** module. The focus is a reliable testing strategy for `Converter<S,T>`, `ConverterFactory<S,R>`, and `ConditionalGenericConverter`, rather than merely showing how to write a converter.

Scope of the complete example: **Java 17+**, **Spring Boot 3.5.6**, **Spring Framework 6.2.x**, JUnit Jupiter, and MockMvc. Small snippets missing imports are explicitly marked as illustrative; the full project in section 9 (and tests in sections 10–14) is presented file by file so learners can create and run it.

## 2. How do the three conversion SPIs differ?

| SPI | Key method | What info does it have? | What should you test? |
| --- | --- | --- | --- |
| `Converter<S,T>` | `T convert(S source)` | Only declared S and T types and the source value | Normalization, valid/invalid data, domain invariants, exceptions |
| `ConverterFactory<S,R>` | `<T extends R> Converter<S,T> getConverter(Class<T>)` | Multiple target types in a family R | Producing the right converter per subclass/enum without mixing up target classes |
| `GenericConverter` | `getConvertibleTypes()` and `convert(Object, TypeDescriptor, TypeDescriptor)` | Source/target descriptors, annotations, generics | ConvertiblePair and field/method context |
| `ConditionalGenericConverter` | GenericConverter + `matches(TypeDescriptor,TypeDescriptor)` | Enough context to decide **whether to be selected** | `matches=true/false`, context-aware selection, conversion when selected |

### 2.1. `Converter<S,T>`

Basic contract:

```java
package org.springframework.core.convert.converter;

public interface Converter<S, T> {
    T convert(S source);
}
```

The Spring reference notes that when `ConversionService` invokes a converter, the `source` argument is guaranteed **non-null**; converters are designed to be thread-safe and may throw `IllegalArgumentException` on invalid input.

**Two different test styles:**

```java
// Direct unit test: observes the exception thrown by the converter.
assertThrows(IllegalArgumentException.class,
        () -> converter.convert("BAD"));

// Integration with ConversionService: wrapper can be
// ConversionFailedException with IllegalArgumentException as cause.
assertThrows(ConversionFailedException.class,
        () -> conversionService.convert("BAD", OrderNumber.class));
```

This is an **illustrative** snippet assuming `converter` and `conversionService` are already initialized. Both assertions are simultaneously true without contradiction: the service layer adds source/target metadata and wraps failures into a contextual exception.

### 2.2. `ConverterFactory<S,R>`

Contract:

```java
public interface ConverterFactory<S, R> {
    <T extends R> Converter<S, T> getConverter(Class<T> targetType);
}
```

A `ConverterFactory<String, Enum>` can serve multiple enum classes. Do not test only a single enum, because generic/target-type bugs can stay hidden if the factory hardcodes one target.

### 2.3. `ConditionalGenericConverter`

Spring defines:

```java
public interface ConditionalConverter {
    boolean matches(TypeDescriptor sourceType, TypeDescriptor targetType);
}

public interface ConditionalGenericConverter
        extends GenericConverter, ConditionalConverter {
}
```

`ConditionalGenericConverter` itself does not require adding a new `convert` method: it inherits `getConvertibleTypes`/`convert` from `GenericConverter` and `matches` from `ConditionalConverter`.

`TypeDescriptor` parameters carry **context**: fields, method parameters, annotations, or generic element types. When `matches` returns false, the converter is not a candidate for that site; this **does not mean** every conversion between those two Java classes must fail if the service has another eligible converter.

## 3. Why test both direct invocation and registration?

A unit test:

```java
assertEquals(new OrderNumber("ORD-0042"),
        new StringToOrderNumberConverter().convert("ord-0042"));
```

only proves the algorithm works when you **call the converter yourself**. It **does not** prove:
- The converter is registered in Spring's `ConversionService`.
- Source/target types match the MVC binder.
- Another default converter is not picked first.
- `ConditionalGenericConverter.matches` is invoked with the real target's annotation.
- Query/form binding through Spring MVC uses that conversion service.
- On invalid input, whether MVC returns 400 or how the controller handles it.

Conversely, a single MockMvc HTTP 200 test does not cover converter edge cases thoroughly either. A solid strategy is the **testing pyramid**:

```text
             MockMvc
       MVC request binding
       -------------------
       ConversionService
     registration + selection
     -----------------------
         Unit tests
    algorithm + bad inputs
```

**There is no need to boot the entire ApplicationContext** for every small boundary case. Each layer checks one responsibility, avoiding pointless duplication.

## 4. A test matrix before writing code

| Category | Positive | Negative | Integration |
| --- | --- | --- | --- |
| `Converter<String,OrderNumber>` | Trim, uppercase, 4-digit string | Missing prefix, bad digits, too long, blank | `canConvert`, `convert`, cause/error class |
| `ConverterFactory<String,Enum>` | At least 2 enum types, case-insensitive, trim | Unknown constant, empty | Registry picks the factory instead of the default converter |
| `ConditionalGenericConverter` | Target field/parameter has matching annotation | No annotation, different prefix, empty input | Accurate `TypeDescriptor`, `matches`, `canConvert`, and MVC annotated parameter |
| Spring MVC | Valid query/form | Invalid query, invalid form, missing required argument | HTTP status and response field values |
| Cross-cutting | Repeated calls with same input give same output | No request state stored, no implicit locale dependency | Tests do not pollute global ConversionService |

Each test should be **named by behavior**, e.g., `missingAnnotationIsNotMatched` is better than `testConverter1`.

## 5. Testing `Converter`: not just valid inputs

Suppose public order numbers must be `ORD-0000` through `ORD-9999`, with exactly 4 ASCII digits. The converter should normalize input with trim and fixed uppercase:

```java
String normalized = source.trim().toUpperCase(Locale.ROOT);
if (!normalized.matches("ORD-[0-9]{4}")) {
    throw new IllegalArgumentException("Expected ORD-0000");
}
return new OrderNumber(normalized);
```

This is a fragment from the complete file later.

### 5.1. Essential tests

1. `ord-0042` becomes `ORD-0042`.
2. `  ORD-0001  ` becomes `ORD-0001`.
3. `ORD-1234` stays unchanged.
4. `REF-0042` has the wrong prefix.
5. `ORD-42` has fewer than four digits.
6. `ORD-12345` has one extra digit.
7. `"   "` is invalid.
8. `ORD-１２３４` contains full-width Unicode digits, which do not satisfy `[0-9]`.

If business rules want Unicode digits, the regex and requirements must change, not just the test. In the demo, ASCII-only is the explicit contract.

### 5.2. Should you test null directly?

The Spring `Converter` contract states `ConversionService` does not pass null into `convert(S)`. When calling `conversionService.convert(null, SomeType.class)`, the framework can handle null at the service layer without invoking the converter.

Therefore:
- Test null through **`ConversionService`** if the application contract cares about it.
- Do not blindly force every `Converter` to handle null directly; direct tests should follow the contract declared by the converter itself.
- If a converter is a public API called outside Spring, you can explicitly enforce `Objects.requireNonNull(source)` or a clear null policy.

### 5.3. Watch locale and thread safety

`toUpperCase()` without specifying a locale can behave differently depending on the JVM locale. Use `toUpperCase(Locale.ROOT)` when normalizing identifiers. Converters must not hold unsynchronized counters or mutable request state.

Running once under a different default locale can catch subtle bugs; however, never mutate `Locale.setDefault(...)` arbitrarily in parallel tests because it is global process state.

## 6. Testing `ConverterFactory`: hitting the right target type

Our sample factory creates converters for multiple enums:

```java
public enum OrderState { NEW, SHIPPED }
public enum ReviewLevel { LOW, HIGH }
```

An easily testable implementation iterates `targetType.getEnumConstants()`:

```java
for (T constant : targetType.getEnumConstants()) {
    if (constant.name().equalsIgnoreCase(source.trim())) {
        return constant;
    }
}
throw new IllegalArgumentException("Unknown enum value");
```

The strength here is avoiding raw `Class` casts or hardcoding a single enum. For a `ConverterFactory<String, Enum>`, test:
- `getConverter(OrderState.class)` accepts `"shipped"` → `SHIPPED`.
- `getConverter(ReviewLevel.class)` accepts `"high"` → `HIGH`.
- Whitespace is trimmed.
- Unknown values are rejected with a clear exception.
- A converter for one enum does not produce values of another enum.

### 6.1. Default converter pitfall

`DefaultConversionService` already includes a String-to-Enum converter. The default converter usually handles enum names according to Spring's own rules. Because we want custom **case-insensitive** handling, a test calling `factory.getConverter(...)` directly is not enough.

Add a test:

```java
DefaultConversionService service = new DefaultConversionService();
service.addConverterFactory(new CaseInsensitiveEnumFactory());

assertEquals(OrderState.SHIPPED,
        service.convert("shipped", OrderState.class));
```

This test proves **the registry actually picks the custom factory** for String→Enum. When registering converters/factories on a service that already has defaults, registration order/overriding matters; do not check only `canConvert(String.class, OrderState.class)`, because the default also returns true.

### 6.2. Do not assume the factory handles null or every Enum subtype

`ConverterFactory<String, Enum>` declares range type `Enum`. The `getConverter(Class<T>)` parameter has bound `T extends Enum`. Tests must pass a **valid enum class**. If an application converts String into a non-enum interface, this is not the right factory; use another ConverterFactory, a single Converter, or a GenericConverter.

## 7. Testing conditional converters: pay special attention to `TypeDescriptor`

A conditional converter does not only inspect `source.getClass()` and `targetClass`. It can inspect **whether the target field/parameter carries a specific annotation**.

We design a custom annotation:

```java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface RequiredPrefix {
    String value();
}
```

And a value object:

```java
public record PrefixedCode(String value, boolean verified) {}
```

The converter supports `String→PrefixedCode` only when `targetType` has `@RequiredPrefix`. Inside `convert`, the annotation dictates whether the prefix must be `VIP-`, `STAFF-`, etc. This is an example **whose context can be tested accurately**, without external dependencies like a database.

### 7.1. `getConvertibleTypes()`: necessary, not sufficient

```java
@Override
public Set<ConvertiblePair> getConvertibleTypes() {
    return Set.of(new ConvertiblePair(
            String.class, PrefixedCode.class));
}
```

The pair declares the converter **is capable** of handling String→PrefixedCode. Yet `matches` decides whether it applies **to a specific site**.

### 7.2. `matches` inspects metadata

```java
@Override
public boolean matches(
        TypeDescriptor sourceType,
        TypeDescriptor targetType) {

    return sourceType.getType() == String.class
            && targetType.hasAnnotation(RequiredPrefix.class);
}
```

This condition relies on the **target annotation**. For a target field lacking `@RequiredPrefix`, the converter must not match even though the target Java class is still `PrefixedCode`.

### 7.3. Creating a `TypeDescriptor` from a real field in tests

Instead of:

```java
TypeDescriptor target = TypeDescriptor.valueOf(PrefixedCode.class);
```

(which loses field annotation info), build the descriptor from an annotated reflection field:

```java
TypeDescriptor target = new TypeDescriptor(
        ExampleFields.class.getDeclaredField("vipCode"));
```

This fragment assumes `ExampleFields` has a field `@RequiredPrefix("VIP") PrefixedCode vipCode;`. `TypeDescriptor` retains annotations attached to the field, giving `matches` full context. In real code, field/parameter annotations are precisely why `ConditionalGenericConverter` is used.

### 7.4. Why is testing `canConvert(Class,Class)` insufficient?

`service.canConvert(String.class, PrefixedCode.class)` only uses **class descriptors**, without a specific field's annotations. It can return false while:

```java
service.canConvert(
    TypeDescriptor.valueOf(String.class),
    new TypeDescriptor(
        ExampleFields.class.getDeclaredField("vipCode")));
```

returns true. This is the **expected** behavior for a metadata-based conditional converter.

On the other hand, a service with another String→PrefixedCode converter registered could return true even when the conditional converter does not match; therefore unit tests for `matches` remain necessary.

### 7.5. Condition is not the same as per-value validation

`matches` should evaluate conditions on **types/metadata**; it never receives the concrete String value. A rule such as "prefix must equal VIP-" reads the annotation in `convert` and compares it against the **input value**.

Separate the two responsibilities:
- `matches`: does this field/parameter have this special requirement?
- `convert`: does the runtime data satisfy the prefix, structure, and value domain?

If a site does not match, the conversion service may look for another converter; if none exists, it throws `ConverterNotFoundException`. If it matches but the text is invalid, `convert` throws an exception such as `IllegalArgumentException`, which the service can wrap in `ConversionFailedException`.

## 8. Choose `GenericConversionService` or `DefaultConversionService` when testing?

| Class | Characteristics | Goal |
| --- | --- | --- |
| `GenericConversionService` | Core registry/conversion engine without the rich default set | Isolated tests: only converters you add yourself |
| `DefaultConversionService` | Pre-registered converters for numbers, enums, collections, etc. | Test real behavior with defaults and precedence |
| `DefaultFormattingConversionService` | Common Spring MVC conversion + formatter infrastructure | Test formatters/annotation-driven formatting |
| MVC-configured conversion service | Web stack via `WebMvcConfigurer#addFormatters` | Verify end-to-end request binding |
| Direct unit call `new MyConverter().convert(...)` | No registry | Test exact converter logic and direct errors |

Do not automatically equate an empty `GenericConversionService` with Spring Boot MVC infrastructure. For instance, a class with a String constructor or suitable static factory method might be picked up by a default converter even if a conditional converter does not match. In unit tests, use an empty service to prove your own converter's selection, without assuming the full system has no other fallback.

### 8.1. `canConvert` does not mean every value is valid

`canConvert(String.class, OrderNumber.class)` only states that a conversion path exists at the **type** level. It does not check whether `"WRONG"` is valid content.

Example:

```java
assertTrue(service.canConvert(String.class, OrderNumber.class));

assertThrows(ConversionFailedException.class,
        () -> service.convert("WRONG", OrderNumber.class));
```

This is not an inconsistency in Spring: converter lookup and runtime value validation are two distinct phases.

For List/Map, `ConversionService` documentation also notes `canConvert` can return true even if element conversion later fails. Tests must pass real data, not just check metadata.

### 8.2. Avoid coupling to global state

Do not boot an entire ApplicationContext in unit tests just to convert a String. Instead:

```java
GenericConversionService service = new GenericConversionService();
service.addConverter(new StringToOrderNumberConverter());
```

Never call `removeConvertible(...)` on a singleton ConversionService shared across tests, as that can cause other cases to fail depending on execution order. Give each test its own instance or configure independently in `@BeforeEach`.

## 9. Organizing code and tests along real execution paths

The project will include:
- `StringToOrderNumberConverter` — `Converter<String,OrderNumber>`.
- `CaseInsensitiveEnumFactory` — `ConverterFactory<String,Enum>` for 2 enum classes.
- `PrefixedCodeConverter` — `ConditionalGenericConverter` driven by `@RequiredPrefix` on fields/parameters.
- `WebConversionConfig` — registers all 3 via `WebMvcConfigurer#addFormatters(FormatterRegistry)`.
- `ConversionController` — query and form endpoints demonstrating Spring MVC binding.
- Multiple JUnit test classes: per-converter unit tests, ConversionService selection, and MockMvc.

**About the Java 17 code:** use `record` for immutable value types; exception policy uses `IllegalArgumentException` on invalid input; no database or network calls inside converters. MVC tests use `@WebMvcTest` and `@Import` instead of starting every service.

### 9.1. Project tree

```text
conversion-tests-demo/
├── pom.xml
├── src/main/java/demo/converters/
│   ├── ConversionDemoApplication.java
│   ├── OrderNumber.java
│   ├── StringToOrderNumberConverter.java
│   ├── OrderState.java
│   ├── ReviewLevel.java
│   ├── CaseInsensitiveEnumFactory.java
│   ├── RequiredPrefix.java
│   ├── PrefixedCode.java
│   ├── PrefixedCodeConverter.java
│   ├── WebConversionConfig.java
│   └── ConversionController.java
└── src/test/java/demo/converters/
    ├── StringToOrderNumberConverterTest.java
    ├── CaseInsensitiveEnumFactoryTest.java
    ├── PrefixedCodeConverterTest.java
    ├── ConversionServiceTest.java
    └── ConversionControllerTest.java
```

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>conversion-tests-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

For testing **type conversion**, the project does not need `spring-boot-starter-validation`; binding a parameter in Spring can fail on conversion without needing a Bean Validation provider. If you add `@Valid`/`@Min` to test constraints, that is a **different test layer** and requires configuring Jakarta Validation properly.

### 9.3. `ConversionDemoApplication.java`

```java
package demo.converters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConversionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConversionDemoApplication.class, args);
    }
}
```

### 9.4. `OrderNumber.java`

```java
package demo.converters;

public record OrderNumber(String value) {
}
```

`OrderNumber` holds the canonical identifier. It is a simple value object for the conversion lesson, not yet representing a full database-backed aggregate ID.

### 9.5. `StringToOrderNumberConverter.java`

```java
package demo.converters;

import org.springframework.core.convert.converter.Converter;

import java.util.Locale;

public final class StringToOrderNumberConverter
        implements Converter<String, OrderNumber> {

    @Override
    public OrderNumber convert(String source) {
        String text = source.trim().toUpperCase(Locale.ROOT);

        if (!text.matches("ORD-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Expected an order number like ORD-0001");
        }

        return new OrderNumber(text);
    }
}
```

It is a **stateless** converter. Spring ConversionService guarantees `source` is non-null when calling `convert`; unit tests in this class focus on valid/malformed inputs. If the class is called outside the framework and needs an explicit null policy, you can add `Objects.requireNonNull` per application contract.

### 9.6. `OrderState.java`

```java
package demo.converters;

public enum OrderState {
    NEW, SHIPPED
}
```

### 9.7. `ReviewLevel.java`

```java
package demo.converters;

public enum ReviewLevel {
    LOW, HIGH
}
```

### 9.8. `CaseInsensitiveEnumFactory.java`

```java
package demo.converters;

import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.converter.ConverterFactory;

public final class CaseInsensitiveEnumFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {

        return source -> {
            String requested = source.trim();

            for (T constant : targetType.getEnumConstants()) {
                if (constant.name().equalsIgnoreCase(requested)) {
                    return constant;
                }
            }

            throw new IllegalArgumentException(
                    "Unknown " + targetType.getSimpleName()
                            + " constant");
        };
    }
}
```

**Why not cast raw Enum?** Iterating over `targetType`'s constants returns the exact `T` without casting from a raw `Class`. This is an intentionally simple example; real products may require stricter policies for aliases or Unicode whitespace.

This factory should not be used for enums requiring complex localized key names; when localization is needed, use explicit mappings, formatters, or appropriate dictionaries.

### 9.9. `RequiredPrefix.java`

```java
package demo.converters;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.PARAMETER})
public @interface RequiredPrefix {
    String value();
}
```

Targets include `FIELD` and `PARAMETER` so unit tests can extract descriptors from fields, while Spring MVC can inspect the annotation on a `@RequestParam` handler method parameter.

### 9.10. `PrefixedCode.java`

```java
package demo.converters;

public record PrefixedCode(String value, boolean verified) {
}
```

This record intentionally **lacks** a single-`String` constructor or static `valueOf(String)` so it does not introduce an alternate simple conversion route during converter-selection tests. `verified` only indicates the converter verified the prefix in the example; it is **not** proof of authorization or a security signature in a real system.

### 9.11. `PrefixedCodeConverter.java`

```java
package demo.converters;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.ConditionalGenericConverter;

import java.util.Set;

public final class PrefixedCodeConverter
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(new ConvertiblePair(
                String.class, PrefixedCode.class));
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {

        return sourceType.getType() == String.class
                && targetType.hasAnnotation(RequiredPrefix.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {

        RequiredPrefix annotation =
                targetType.getAnnotation(RequiredPrefix.class);

        if (annotation == null) {
            throw new IllegalArgumentException(
                    "RequiredPrefix annotation is missing");
        }

        String text = ((String) source).trim();
        String prefix = annotation.value() + "-";

        if (!text.startsWith(prefix)
                || text.length() == prefix.length()) {
            throw new IllegalArgumentException(
                    "Expected a nonempty code starting with " + prefix);
        }

        return new PrefixedCode(text, true);
    }
}
```

Behavior:
- `getConvertibleTypes()` registers the String→PrefixedCode pair.
- `matches` is true **only** when the target descriptor has `@RequiredPrefix`.
- `convert` reads the specific annotation's prefix value, so `VIP-A7` and `STAFF-B9` can enforce different policies.
- A string containing only `"VIP-"` is invalid because the suffix after the prefix is missing.
- `"STAFF-B9"` is rejected on a target annotated with `@RequiredPrefix("VIP")`.

In production, add **length/allowed-character limits** for the suffix if prefix alone is insufficient. `verified=true` from a converter **never replaces user permission checks**.

### 9.12. `WebConversionConfig.java`

```java
package demo.converters;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {

        registry.addConverter(new StringToOrderNumberConverter());
        registry.addConverterFactory(new CaseInsensitiveEnumFactory());
        registry.addConverter(new PrefixedCodeConverter());
    }
}
```

`FormatterRegistry` also exposes methods to register converters/factories. When Spring MVC builds its conversion infrastructure, these converters are added to the MVC conversion service.

**Do not confuse with Jackson:** This configuration handles conversion of query/form/path parameters and eligible Spring MVC binder paths. JSON bodies via Jackson/`HttpMessageConverter` follow a separate deserialization mechanism. Never use `@RequestBody` JSON behavior as proof that `Converter<String,OrderNumber>` was selected.

### 9.13. `ConversionController.java`

```java
package demo.converters;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class ConversionController {

    @GetMapping("/orders")
    public Map<String, String> order(
            @RequestParam("id") OrderNumber id) {

        return Map.of("id", id.value());
    }

    @GetMapping("/levels")
    public Map<String, String> enums(
            @RequestParam("state") OrderState state,
            @RequestParam("level") ReviewLevel level) {

        return Map.of(
                "state", state.name(),
                "level", level.name());
    }

    @GetMapping("/code")
    public Map<String, Object> code(
            @RequestParam("value")
            @RequiredPrefix("VIP") PrefixedCode code) {

        return Map.of(
                "value", code.value(),
                "verified", code.verified());
    }

    public static class Form {
        private OrderNumber order;
        private OrderState state;

        public OrderNumber getOrder() {
            return order;
        }

        public void setOrder(OrderNumber order) {
            this.order = order;
        }

        public OrderState getState() {
            return state;
        }

        public void setState(OrderState state) {
            this.state = state;
        }
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> form(
            @ModelAttribute("form") Form form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            var fields = errors.getFieldErrors().stream()
                    .map(error -> error.getField())
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "code", "BINDING_ERROR",
                    "fields", fields));
        }

        if (form.getOrder() == null || form.getState() == null) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "MISSING_FORM_FIELD",
                    "fields", java.util.List.of()));
        }

        return ResponseEntity.ok(Map.of(
                "order", form.getOrder().value(),
                "state", form.getState().name()));
    }
}
```

**Important testing points:**
- `@RequestParam OrderNumber` tests how MVC uses a plain converter.
- Two `@RequestParam` enum types prove the factory works across multiple targets.
- `@RequiredPrefix("VIP")` sits on the method parameter so `TypeDescriptor` carries the annotation when the converter is evaluated.
- `@ModelAttribute Form` uses `WebDataBinder` with two properties to test form binding.
- `BindingResult` immediately follows the form: when form field conversion fails, the controller can return code `BINDING_ERROR`.
- The demo places no Bean Validation constraints on Form, so `BINDING_ERROR` genuinely represents a conversion/binding failure without mixing in Jakarta constraint errors.

The `/code` endpoint only demonstrates context-driven conversion. If another MVC setup fails to propagate MethodParameter annotation metadata into TypeDescriptor properly, the MockMvc test will catch the integration bug; `TypeDescriptor` unit tests serve as the first diagnostic layer.

## 10. Unit tests for the plain converter

### 10.1. `StringToOrderNumberConverterTest.java`

```java
package demo.converters;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StringToOrderNumberConverterTest {

    private final StringToOrderNumberConverter converter =
            new StringToOrderNumberConverter();

    @Test
    void lowercaseInputIsCanonicalized() {
        assertEquals(new OrderNumber("ORD-0042"),
                converter.convert("ord-0042"));
    }

    @Test
    void surroundingWhitespaceIsTrimmed() {
        assertEquals(new OrderNumber("ORD-0001"),
                converter.convert("  ORD-0001  "));
    }

    @Test
    void canonicalInputIsPreserved() {
        assertEquals(new OrderNumber("ORD-9876"),
                converter.convert("ORD-9876"));
    }

    @Test
    void incorrectPrefixIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("REF-0042"));
    }

    @Test
    void tooFewDigitsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("ORD-42"));
    }

    @Test
    void tooManyDigitsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("ORD-12345"));
    }

    @Test
    void blankInputIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("   "));
    }

    @Test
    void nonAsciiDigitsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("ORD-１２３４"));
    }
}
```

These tests intentionally **do not** invoke Spring Test Context. The only test dependency is JUnit, with Spring's Converter SPI on the production class. Malformed text cases cause the converter to throw `IllegalArgumentException` directly.

**Note on test encoding:** Save Java files as UTF-8 when they contain full-width Unicode digits; Maven/JDK 17 in standard setups supports UTF-8 as configured. If a build tool or IDE uses a different encoding, configure source encoding explicitly.

## 11. Unit tests for `ConverterFactory`

### 11.1. `CaseInsensitiveEnumFactoryTest.java`

```java
package demo.converters;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CaseInsensitiveEnumFactoryTest {

    private final CaseInsensitiveEnumFactory factory =
            new CaseInsensitiveEnumFactory();

    @Test
    void convertsFirstEnumCaseInsensitively() {
        assertEquals(OrderState.SHIPPED,
                factory.getConverter(OrderState.class)
                       .convert("shipped"));
    }

    @Test
    void convertsSecondEnumIndependently() {
        assertEquals(ReviewLevel.HIGH,
                factory.getConverter(ReviewLevel.class)
                       .convert("high"));
    }

    @Test
    void trimsWhitespaceForAnyEnum() {
        assertEquals(OrderState.NEW,
                factory.getConverter(OrderState.class)
                       .convert("  new  "));
    }

    @Test
    void unknownConstantIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> factory.getConverter(OrderState.class)
                             .convert("deleted"));
    }

    @Test
    void emptyEnumNameIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> factory.getConverter(ReviewLevel.class)
                             .convert(""));
    }
}
```

If you test only `getConverter(OrderState.class)`, an implementation hardcoding OrderState would still pass. Using two target types catches target-selection bugs; the integration test in section 13 also proves the registry uses this factory even when the default String→Enum converter exists.

## 12. Unit tests for `ConditionalGenericConverter`

### 12.1. `PrefixedCodeConverterTest.java`

```java
package demo.converters;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.GenericConverter;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PrefixedCodeConverterTest {

    private final PrefixedCodeConverter converter =
            new PrefixedCodeConverter();

    // These fields exist solely to construct real TypeDescriptors.
    private static class Targets {
        @RequiredPrefix("VIP")
        private PrefixedCode vip;

        @RequiredPrefix("STAFF")
        private PrefixedCode staff;

        private PrefixedCode plain;
    }

    private static TypeDescriptor target(String field) throws Exception {
        return new TypeDescriptor(
                Targets.class.getDeclaredField(field));
    }

    private static TypeDescriptor source() {
        return TypeDescriptor.valueOf(String.class);
    }

    @Test
    void declaresExactlyOneConvertiblePair() {
        assertEquals(
                Set.of(new GenericConverter.ConvertiblePair(
                        String.class, PrefixedCode.class)),
                converter.getConvertibleTypes());
    }

    @Test
    void matchesAnnotatedVipField() throws Exception {
        assertTrue(converter.matches(source(), target("vip")));
    }

    @Test
    void matchesAnotherAnnotatedField() throws Exception {
        assertTrue(converter.matches(source(), target("staff")));
    }

    @Test
    void doesNotMatchUnannotatedField() throws Exception {
        assertFalse(converter.matches(source(), target("plain")));
    }

    @Test
    void annotatedFieldControlsAcceptedPrefix() throws Exception {
        assertEquals(new PrefixedCode("VIP-A7", true),
                converter.convert("  VIP-A7  ",
                        source(), target("vip")));

        assertEquals(new PrefixedCode("STAFF-X2", true),
                converter.convert("STAFF-X2",
                        source(), target("staff")));
    }

    @Test
    void wrongPrefixAndEmptySuffixAreRejected() throws Exception {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("STAFF-X2",
                        source(), target("vip")));

        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("VIP-",
                        source(), target("vip")));
    }

    @Test
    void directCallWithoutAnnotationHasExplicitFailure()
            throws Exception {

        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("VIP-A7",
                        source(), target("plain")));
    }
}
```

The `vip`, `staff`, and `plain` fields never need object instantiation; the test only grabs `java.lang.reflect.Field` to construct `TypeDescriptor`. Thus the test does not depend on bean property access or MVC. It proves:
1. The source→target pair is declared accurately.
2. The annotation flips `matches` from false to true.
3. The annotation's `value()` attribute drives conversion.
4. Inputs with the wrong prefix are still rejected **after** the converter is selected.
5. Calling `convert` directly with an unannotated target **bypasses selection**, so the implementation checks explicitly and fails cleanly.

## 13. Integration tests with `ConversionService`

### 13.1. `ConversionServiceTest.java`

```java
package demo.converters;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.ConverterNotFoundException;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.core.convert.support.GenericConversionService;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConversionServiceTest {

    private static class Fields {
        @RequiredPrefix("VIP")
        private PrefixedCode vip;

        private PrefixedCode unannotated;
    }

    private static TypeDescriptor field(String name) throws Exception {
        return new TypeDescriptor(
                Fields.class.getDeclaredField(name));
    }

    @Test
    void registeredPlainConverterIsUsed() {
        GenericConversionService service =
                new GenericConversionService();

        service.addConverter(new StringToOrderNumberConverter());

        assertTrue(service.canConvert(
                String.class, OrderNumber.class));
        assertEquals(new OrderNumber("ORD-0007"),
                service.convert("ord-0007", OrderNumber.class));
    }

    @Test
    void invalidValueBecomesConversionFailedException() {
        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new StringToOrderNumberConverter());

        assertThrows(ConversionFailedException.class,
                () -> service.convert(
                        "wrong", OrderNumber.class));
    }

    @Test
    void factoryOverridesDefaultEnumConversion() {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverterFactory(new CaseInsensitiveEnumFactory());

        // Lowercase succeeds only via the case-insensitive factory.
        assertEquals(OrderState.SHIPPED,
                service.convert("shipped", OrderState.class));
        assertEquals(ReviewLevel.HIGH,
                service.convert("high", ReviewLevel.class));
    }

    @Test
    void annotatedTargetCanBeConverted() throws Exception {
        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new PrefixedCodeConverter());

        TypeDescriptor source = TypeDescriptor.valueOf(String.class);
        TypeDescriptor target = field("vip");

        assertTrue(service.canConvert(source, target));

        Object actual = service.convert(
                "VIP-Z9", source, target);

        assertEquals(new PrefixedCode("VIP-Z9", true), actual);
    }

    @Test
    void unannotatedTargetIsNotConvertibleInIsolatedRegistry()
            throws Exception {

        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new PrefixedCodeConverter());

        TypeDescriptor source = TypeDescriptor.valueOf(String.class);
        TypeDescriptor target = field("unannotated");

        assertFalse(service.canConvert(source, target));
        assertThrows(ConverterNotFoundException.class,
                () -> service.convert("VIP-Z9", source, target));
    }

    @Test
    void typeLevelCanConvertDoesNotValidateInputValues() {
        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new StringToOrderNumberConverter());

        assertTrue(service.canConvert(
                String.class, OrderNumber.class));

        assertThrows(ConversionFailedException.class,
                () -> service.convert(
                        "ORD-NaN", OrderNumber.class));
    }

    @Test
    void nullInputMayBeHandledAtServiceBoundary() {
        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new StringToOrderNumberConverter());

        assertNull(service.convert(null, OrderNumber.class));
    }
}
```

**Why use `GenericConversionService` for conditional tests?** It is an isolated registry containing only the explicitly registered converters. When an unannotated target does not match, the test has grounds to expect `canConvert==false` and `ConverterNotFoundException`. Using `DefaultConversionService` could allow other default converters to create an alternate conversion route, leading to false conclusions.

**Why use `DefaultConversionService` for the enum factory?** It already has built-in String→Enum conversion. After registering the new factory, the lowercase enum test proves **the new factory actually wins selection**.

**Important about exceptions:** when calling `service.convert("wrong", OrderNumber.class)`, Spring can wrap the converter's `IllegalArgumentException` inside `ConversionFailedException`. Unit tests on `converter.convert("wrong")` verify the original exception. In advanced test suites, you can assert the cause class and sanitized message; avoid locking tests to Spring's full stack trace or exception wording.

## 14. MockMvc: proving MVC actually uses the converters

### 14.1. `ConversionControllerTest.java`

```java
package demo.converters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ConversionController.class)
@Import(WebConversionConfig.class)
class ConversionControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void queryParameterUsesPlainConverter() throws Exception {
        mvc.perform(get("/api/orders").param("id", "ord-0042"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ORD-0042"));
    }

    @Test
    void invalidOrderNumberFailsBeforeController() throws Exception {
        mvc.perform(get("/api/orders").param("id", "bad"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredOrderIdIsBadRequest() throws Exception {
        mvc.perform(get("/api/orders"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void bothEnumTypesUseCustomFactory() throws Exception {
        mvc.perform(get("/api/levels")
                        .param("state", "shipped")
                        .param("level", "high"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("SHIPPED"))
                .andExpect(jsonPath("$.level").value("HIGH"));
    }

    @Test
    void unknownEnumConstantIsRejected() throws Exception {
        mvc.perform(get("/api/levels")
                        .param("state", "retired")
                        .param("level", "low"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void annotatedRequestParameterUsesConditionalConverter()
            throws Exception {

        mvc.perform(get("/api/code").param("value", "VIP-A7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.value").value("VIP-A7"))
                .andExpect(jsonPath("$.verified").value(true));
    }

    @Test
    void wrongPrefixIsRejectedAfterConditionalSelection()
            throws Exception {

        mvc.perform(get("/api/code").param("value", "STAFF-A7"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void formObjectPropertiesUseRegisteredConverters()
            throws Exception {

        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("order", "ord-0008")
                        .param("state", "new"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.order").value("ORD-0008"))
                .andExpect(jsonPath("$.state").value("NEW"));
    }

    @Test
    void invalidFormFieldBecomesBindingResultError()
            throws Exception {

        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("order", "wrong")
                        .param("state", "new"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BINDING_ERROR"))
                .andExpect(jsonPath("$.fields[0]").value("order"));
    }

    @Test
    void missingFormFieldHasDifferentApplicationCode()
            throws Exception {

        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("order", "ord-0008"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_FORM_FIELD"));
    }
}
```

**Benefits of `@WebMvcTest`:** initializes only the web slice for MVC without a database or TCP server. `@Import(WebConversionConfig.class)` ensures the three converters/factories are present in the test context even if a test configuration does not scan `@Configuration` classes outside the web slice.

For an invalid `@RequestParam`, Spring MVC can raise `MethodArgumentTypeMismatchException` and return default HTTP 400. For an invalid `@ModelAttribute` form, placing `BindingResult` right after the DTO lets the controller respond with `BINDING_ERROR`.

**Most important test for the conditional converter:** `annotatedRequestParameterUsesConditionalConverter`. Even a misconfiguration in propagating MethodParameter annotations into TypeDescriptor can make this test fail while the `converter.matches` unit test still passes. That is precisely why the MVC layer is needed alongside unit tests.

## 15. Expected results and how to run

Total `@Test` methods across the five files:
- `StringToOrderNumberConverterTest`: 8 tests.
- `CaseInsensitiveEnumFactoryTest`: 5 tests.
- `PrefixedCodeConverterTest`: 7 tests.
- `ConversionServiceTest`: 7 tests.
- `ConversionControllerTest`: 10 tests.

**Total 37 test cases.** These are expected counts from the code above, not results of running Maven while writing the lesson.

Inside `conversion-tests-demo`, using JDK 17+ and Maven:

```bash
mvn test
```

You can run a single test class:

```bash
mvn -Dtest=StringToOrderNumberConverterTest test
mvn -Dtest=CaseInsensitiveEnumFactoryTest test
mvn -Dtest=PrefixedCodeConverterTest test
mvn -Dtest=ConversionServiceTest test
mvn -Dtest=ConversionControllerTest test
```

The test classes have no `@Disabled` annotations and do not rely on a database or credentials. If tests fail, inspect the stack trace and framework version before changing assertions arbitrarily.

Start the application:

```bash
mvn spring-boot:run
```

### 15.1. Trying the `Converter` endpoint

```bash
curl -i 'http://localhost:8080/api/orders?id=ord-0042'
```

Expected HTTP **200**:

```json
{"id":"ORD-0042"}
```

### 15.2. Trying the two-enum-types factory

```bash
curl -i 'http://localhost:8080/api/levels?state=shipped&level=high'
```

Expected HTTP **200**:

```json
{"state":"SHIPPED","level":"HIGH"}
```

### 15.3. Trying the conditional converter

```bash
curl -i 'http://localhost:8080/api/code?value=VIP-A7'
```

Expected HTTP **200**:

```json
{"value":"VIP-A7","verified":true}
```

With `value=STAFF-A7`, the converter was selected based on the annotation, yet **value validation** fails, so the request typically returns HTTP **400**. Contrast that with an unannotated target **not matching**: the result can be `ConverterNotFoundException`/conversion not supported if no other converter exists.

### 15.4. Trying form binding

```bash
curl -i -X POST \
  'http://localhost:8080/api/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'order=ord-0008' \
  --data-urlencode 'state=new'
```

Expected HTTP **200**:

```json
{"order":"ORD-0008","state":"NEW"}
```

Sending `order=bad`:
- `WebDataBinder` tries converting field `order`.
- The converter throws `IllegalArgumentException`.
- The binder records a type-conversion error into `BindingResult`.
- The controller sees `errors.hasErrors()==true` and returns `BINDING_ERROR` with `fields:["order"]`.

This illustrates the difference between a **conversion exception** in the service and a **binding error** in Spring MVC.

## 16. Why not rely on a single `canConvert` test?

`canConvert(Class,Class)` only reports **type-conversion capability** under the current configuration; it does not verify:
- Whether the input text is valid.
- Whether target annotations are inspected.
- Whether your converter or a default converter is selected.
- Whether output matches the canonical representation.
- Whether the MVC binder/formatter uses the same registry.
- How failed HTTP requests are handled.

A complete test checks at least:

```java
assertTrue(service.canConvert(String.class, OrderNumber.class));
assertEquals(new OrderNumber("ORD-0009"),
        service.convert("ord-0009", OrderNumber.class));
assertThrows(ConversionFailedException.class,
        () -> service.convert("invalid", OrderNumber.class));
```

For conditional converters, use a `TypeDescriptor` from an annotated field/parameter. Do not conclude `canConvert(String.class, PrefixedCode.class)==false` means a broken converter; for unannotated targets, that can be the exact intended behavior.

## 17. Distinguishing errors across the 3 layers

| Layer | Test input | Typically asserted result |
| --- | --- | --- |
| Direct `Converter.convert` call | `"bad"` | `IllegalArgumentException` |
| `ConversionService.convert` | `"bad"` | `ConversionFailedException` when a converter is selected |
| `ConversionService` without a route | String→unannotated PrefixedCode target | `ConverterNotFoundException` |
| Spring MVC `@RequestParam` | `?id=bad` | HTTP 400 via type mismatch |
| Spring MVC `@ModelAttribute` | `order=bad` | `FieldError` in `BindingResult`; controller may return 400 |
| Jackson JSON `@RequestBody` | JSON string→value object field | Jackson deserialization path, does not use ConverterRegistry by default |
| Jakarta Validation `@Valid` | Convertible data violating annotation constraint | Separate validation path, typically `MethodArgumentNotValidException` |

### 17.1. Do not assert the full exception message

Spring messages include source/target types and can change when upgrading Spring. Unit tests should assert exception **types**, root cause when needed, and machine-readable error codes if the app defines them. Never hardcode the full `ex.getMessage()` unless it is a contract you explicitly own and maintain.

### 17.2. Negative tests catch missing registration

A classic bug: your unit tests for a plain converter pass, yet you forgot to register it in `WebMvcConfigurer#addFormatters`. A MockMvc request `?id=ord-0042` might:
- Pass through another built-in converter if the target class happens to have a special constructor.
- Find no conversion path and fail.
- Return a value different from the expected canonical form.

Therefore assert the **output value** such as `ORD-0042`, not just status `200`. That confirms your converter actually ran rather than a fallback accidentally passing the test.

## 18. Table-driven tests with `@ParameterizedTest`

As edge cases grow, JUnit Jupiter parameterized tests come in handy.

```java
@ParameterizedTest
@ValueSource(strings = {
        "BAD", "ORD-1", "ORD-12345", "", "ORD-12AB"
})
void invalidOrderIdentifiersAreRejected(String input) {
    assertThrows(IllegalArgumentException.class,
            () -> converter.convert(input));
}
```

This is an illustrative fragment requiring imports:
`org.junit.jupiter.params.ParameterizedTest`,
`org.junit.jupiter.params.provider.ValueSource`,
`org.junit.jupiter.api.Assertions.assertThrows`, and an instantiated `converter`. It can replace multiple identically structured tests; in the complete project, we kept separate methods so the lesson makes each failure easy to trace.

For multiple enum targets, you can use `@MethodSource` streaming target class, input, and expected value. However, `ConverterFactory<String,Enum>` generics can get awkward: keeping separate unit tests is sometimes clearer than a parameterized test forced to use raw types.

## 19. MockMvc slice tests vs whole-context tests

### 19.1. When does `@WebMvcTest` fit?

Use it for:
- Query/path/form binding.
- Controller handler selection.
- MVC conversion/formatting/argument resolution.
- Error responses produced by MVC and controllers.

`@WebMvcTest(ConversionController.class)` typically does not instantiate all services/repositories. If a controller injects dependencies, provide appropriate mocks/test beans. In this example the controller has no external dependencies, keeping the web slice lean.

### 19.2. When is `@SpringBootTest` needed?

Add `@SpringBootTest` tests when you must prove:
- Real application component scanning and configuration.
- Multiple `WebMvcConfigurer` beans interacting with each other.
- Effects of security filters, custom conversion services, MVC advice, or other auto-configuration.
- Registration depending on auto-configured beans or profiles.

There is no need to replace every unit test with `@SpringBootTest`. Each test should cover its responsibility at the lowest reliable cost.

### 19.3. `@AutoConfigureMockMvc` vs `@WebMvcTest`

In a whole-context test:

```java
@SpringBootTest
@AutoConfigureMockMvc
class IntegrationTest {
    @Autowired MockMvc mvc;
}
```

This is an illustrative snippet; imports are required. With `@WebMvcTest`, Boot already provides matching MockMvc web-slice support, so manually building `MockMvcBuilders.standaloneSetup(...)` is unnecessary in the example. When using standalone setup, you must **configure** the conversion service/resolvers yourself; otherwise tests can diverge from production MVC.

## 20. Subtle edge cases easy to miss

### 20.1. Wrong converter selected due to lost metadata

`TypeDescriptor.valueOf(PrefixedCode.class)` carries no field annotations. When tests need `@RequiredPrefix`, use:
- `new TypeDescriptor(Field)` for annotated fields.
- `new TypeDescriptor(MethodParameter)` for annotated method parameters when applicable.
- Or a Spring MVC test against a real annotated handler parameter.

Never pass a fake `hasAnnotation=true` flag in tests when real reflection metadata can be used. Real TypeDescriptors catch annotation retention/target mistakes.

### 20.2. Multiple candidate converters

If multiple converters exist for the same String→Target pair, selection can depend on registration/specificity/conditions. Avoid assertions relying on order unless explicitly guaranteed by the application contract. Isolate conditional converters with `GenericConversionService` for unit selection; use `DefaultConversionService` to intentionally test interaction with defaults.

### 20.3. Empty strings and null

`source.trim()` can yield `""`; the project's converter rejects it via regex/prefix checks. Rejecting an empty string differs from `null` passed by the framework to controllers for optional arguments.

If the goal is "required field missing", that belongs to argument presence/Bean Validation, not converters guessing whether `null` is valid across every context.

### 20.4. Unicode whitespace

`String.trim()` only strips certain traditional whitespace characters; `strip()` uses `Character.isWhitespace` and has different semantics. Choose the one matching your API contract and write tests for `\u00A0`, `\u2003`, tabs, and newlines if canonicalization affects security.

### 20.5. Locale

`toUpperCase(Locale.ROOT)` avoids shifting behavior with the JVM locale. If a converter deals with user-visible currency/dates, a locale-aware `Formatter<T>` may fit better than `Converter<S,T>`, though that requires its own test suite.

### 20.6. Converter thread safety

Spring may share the same converter instance across concurrent requests. Single-threaded unit tests do not replace concurrency tests if a converter holds a mutable cache or performs I/O. For the project's stateless converters, there is no request state to race on; if adding a cache, use thread-safe or immutable structures and test under realistic load.

### 20.7. Value object invariants

Even with a converter, domain objects should enforce their own invariants if other code paths can construct them directly. In the sample project, `OrderNumber` is just a String-holding record while validation lives in the converter; real products may move the rule into the domain constructor/factory so `OrderNumber("BAD")` cannot be created anywhere else. When doing so, add direct domain constructor tests to preserve a single source of truth.

### 20.8. Do not conflate type conversion with business authorization

`@RequiredPrefix("VIP")` proves metadata-driven conversion; it does not mean a sender of a `VIP-` string holds VIP privileges. Actual authorization relies on authenticated identity and service-layer permissions, never on user-supplied strings.

### 20.9. ConversionService is a capability, not a validator

A converter should transform data and reject malformed syntax. Constraints like `@Min`, `@NotBlank`, and `@Valid` check domain validity afterward. Calling a database inside a converter to look up permissions on every request introduces opaque dependencies; separate syntactic conversion, validation, and authorization.

### 20.10. Collection/Map conversion

A `Converter<String,OrderNumber>` can be used indirectly to convert collection elements when DefaultConversionService has collection converters. Yet `canConvert(List.class,List.class)` is not enough to prove every element is valid: use `TypeDescriptor.collection(...)` with generic element types and test values.

Illustrative example:

```java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToOrderNumberConverter());

Object result = service.convert(
        java.util.List.of("ord-0001", "ord-0002"),
        TypeDescriptor.collection(
                java.util.List.class,
                TypeDescriptor.valueOf(String.class)),
        TypeDescriptor.collection(
                java.util.List.class,
                TypeDescriptor.valueOf(OrderNumber.class)));
```

With the default collection converters, the result can be a List of corresponding `OrderNumber` instances. This is an illustrative fragment **outside the main test suite**; if used in production, assert size, element types, values, and behavior when one element is malformed.

## 21. QA checklist when reviewing converter tests

1. Are the exact **source type** and **target type** of the converter/factory stated?
2. Do converter unit tests assert canonical output rather than just non-null?
3. Are boundary data, whitespace, casing, prefixes/regex, and invalid text tested?
4. Is direct `IllegalArgumentException` distinguished from service `ConversionFailedException`?
5. Do factory tests cover **at least two target subclasses** instead of one enum?
6. Is the factory tested when registered in `DefaultConversionService` alongside defaults?
7. Is `getConvertibleTypes()` of GenericConverter inspected and the declared pair asserted?
8. Is `matches` tested for both true and false?
9. For annotation-based conditions, does the `TypeDescriptor` actually carry the annotation?
10. Are runtime values tested after the condition matches?
11. Is it tested that Class descriptors are **not** equivalent to annotated field descriptors?
12. Is `canConvert` tested without treating it as input validation?
13. Does each test use a fresh registry instead of mutating a shared singleton?
14. Is there a MockMvc test proving Spring MVC **actually** invokes the converter?
15. Are invalid query params and invalid form binding tested separately?
16. Is `@RequestBody`/Jackson distinguished from binder conversion?
17. Do tests avoid claiming every conversion error is a Jakarta Bean Validation failure?
18. Do tests avoid asserting full Spring exception message text?
19. Is normalization with `Locale.ROOT` tested when stable identifiers are required?
20. If a converter has mutable state, are thread safety/invariants tested?
21. Does `mvn test` run cleanly with files/classes/paths matching packages?
22. Are expected results clearly stated as **expected**, without claiming execution?
23. When changing framework versions, are method annotation metadata and converter selection re-tested?
24. Is authorization kept separate from converting strings that look like roles/tokens?

## 22. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Testing only `convert()` and assuming Spring uses it automatically | Forgot registration or registry picks another converter | Add `ConversionService` + MockMvc tests |
| Testing only `canConvert` | Misses invalid inputs and wrong outputs | Assert `convert` with real values and negative inputs |
| Testing `ConverterFactory` with a single enum | Misses hardcoded target-class bugs | Test multiple target enum classes |
| Using `TypeDescriptor.valueOf(Target.class)` for conditional annotations | Loses field/parameter metadata | Use `new TypeDescriptor(Field/MethodParameter)` |
| `matches()` always returns true | Converter affects unannotated sites | Inspect target context properly |
| `matches()` inspects runtime source value | Interface does not provide the value | Check content in `convert`, metadata in `matches` |
| Not checking `getConvertibleTypes` | Registry never considers the converter a candidate | Test the String→target pair |
| Expecting `IllegalArgumentException` from `ConversionService.convert` | Usually receives wrapped `ConversionFailedException` | Assert the exception appropriate for the layer under test |
| Expecting `ConverterNotFoundException` when converter matched but text is invalid | Converter was found; conversion itself failed | Assert `ConversionFailedException` |
| Using `DefaultConversionService` to prove "non-matching conditional cannot convert" | Another fallback may exist | Use an isolated registry and assert `matches` |
| Hardcoding JVM locale in tests | Different CI locale causes failures | Normalize with `Locale.ROOT` |
| Using `@WebMvcTest` without converter config | MockMvc lacks the expected registry | `@Import(WebConversionConfig.class)` |
| Using standalone MockMvc without configuring conversion service | Behavior diverges from production | Configure MVC service or use web slice |
| Testing JSON `@RequestBody` to prove a String→value converter | Jackson has its own pipeline | Use query/form/path binding |
| Returning "invalid code" while logging raw input secrets | Data leak | Sanitize messages/logging |
| Confusing `@Min`/`@NotBlank` with conversion | Validation is a separate phase | Test binding vs constraints separately |
| Making a stateful converter a singleton | Race conditions across requests | Keep stateless/immutable or synchronize properly |
| Skipping business authorization because value converted | Syntactically valid string does not prove permission | Check principal/permissions in the service |

## 23. Practice exercises

1. Add tests for `ORD-0000` and `ORD-9999` covering both order-number boundaries.
2. Add a rule rejecting `ORD-9999` as a reserved ID; distinguish syntax conversion from domain policy.
3. Replace `trim()` with `strip()` and test Unicode whitespace such as `\u2003`, explaining the contract change.
4. Add enum `PaymentMethod { CARD, CASH }`; without changing the factory, write a test proving the third target still works.
5. Test enum input `"ShIpPeD"` and varied whitespace to verify case-insensitivity.
6. Write a `DefaultConversionService` test **without** registering the custom factory and compare `"shipped"` against the registered case.
7. Change `@RequiredPrefix` to another value such as `"PARTNER"`; use a field `TypeDescriptor` to test dynamic annotation attributes.
8. Remove the annotation from field `vip`; verify `matches=false` and contextual target `canConvert` changes.
9. Register an additional plain `Converter<String,PrefixedCode>` and observe fallback when the conditional converter does not match; do not assert precedence without verifying your framework version.
10. Add a `@RequestParam @RequiredPrefix("STAFF")` endpoint and test that a VIP prefix is rejected.
11. Write a collection conversion test `List<String> -> List<OrderNumber>` with two valid elements and one invalid element.
12. Create a Form DTO with a field annotated `@RequiredPrefix` and test whether WebDataBinder preserves field annotations during property binding.
13. Try sending multiple query parameters with the same name and observe what data type the argument resolver passes to the converter.
14. Add a JSON error response with a machine-readable code for `MethodArgumentTypeMismatchException` without echoing the raw value.
15. Add `@NotBlank`, `@Valid`, and a Jakarta Validation provider to test that syntax conversion succeeds while a constraint can still fail.
16. Use `@SpringBootTest + @AutoConfigureMockMvc` in one test to prove component scanning/auto-configuration in the full app.
17. Refactor `OrderNumber` so its constructor enforces invariants itself, then test direct construction and the converter.
18. Write parameterized tests for ten invalid code strings and analyze when one multi-case test method is better than separate test methods.
19. Compare a conditional converter driven by target annotations with a locale-aware `Formatter`: which problem fits each better?
20. Write a review checklist for converters added to the global ConversionService, especially where built-in types could accidentally be overridden.

**Conclusion:** Testing type conversion in Spring does not stop at calling `convert()`. For `Converter`, verify **values and errors**; for `ConverterFactory`, verify **multiple target types**; for `ConditionalGenericConverter`, verify **selection by TypeDescriptor and annotations**. Finally, test `ConversionService` and `MockMvc` to prove converters are **actually registered and used**. That is how you catch bugs that isolated unit tests cannot see.

## 24. Official references

- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — Converter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/Converter.html)
- [Spring Framework 6.2 — ConverterFactory API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConverterFactory.html)
- [Spring Framework 6.2 — ConditionalGenericConverter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [Spring Framework 6.2 — GenericConverter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [Spring Framework 6.2 — TypeDescriptor API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Spring Framework 6.2 — GenericConversionService API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
- [Spring Framework 6.2 — ConversionService API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework 6.2 — Spring MVC Conversion and Formatting](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [Spring Boot 3.5 — Testing Web Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [JUnit 5 — User Guide / Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests)