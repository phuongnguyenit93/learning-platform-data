# Converting String Parameters with `Converter` and `Formatter` in Spring

## 1. Why does a request need type conversion?

HTTP transmits data through the URL, headers, cookies, or forms as text. But a Java controller usually needs to receive explicit data types: `Long`, `UUID`, `LocalDate`, an enum, or a business value object.

For example, a client calls:

```text
GET /orders?status=paid&from=15%2F03%2F2025
```

In the controller, we want to receive `OrderStatus` and `LocalDate`, rather than reading the two strings and parsing them ourselves in every method:

```java
@GetMapping("/orders")
Mono<OrderSummary> search(
        @RequestParam("status") OrderStatus status,
        @RequestParam("from") LocalDate from) {
    // Spring converts the String to the target type before calling the method.
}
```

Spring has a **type conversion** system to convert one Java type to another and a **formatting** system to parse/print values according to a format, with particular attention to `Locale`.

Two important SPIs:

- **`Converter<S, T>`**: converts an object of source type `S` into target type `T`. Suitable for pure type conversion, independent of language or display format.
- **`Formatter<T>`**: converts text into an object and prints an object as text. A formatter has both the parse and print directions, and receives the user's `Locale` to handle dates, numbers, and displayed content.

In Spring WebFlux, when a controller parameter receives string data but declares a type other than `String`, the framework automatically applies the configured conversion service. That is why `@RequestParam`, `@PathVariable`, `@RequestHeader`, and `@CookieValue` can receive the target type directly.

## 2. Distinguishing `Converter` and `Formatter`

| Criterion | `Converter<S, T>` | `Formatter<T>` |
|---|---|---|
| Purpose | Converts Java types | Parses/prints an object as text |
| Conversion direction | `S` → `T` | String → `T` and `T` → String |
| Locale | Does not receive `Locale` | Receives `Locale` in both `parse` and `print` |
| Typical scope | String → enum, ID → value object, entity → DTO | Locale-specific date/number strings, form input data |
| API | `convert(S source)` | `parse(String, Locale)` and `print(T, Locale)` |
| When to choose | The conversion rule does not depend on presentation | You need input/output formatting for users |

Examples:

- The string `"paid"` to `OrderStatus.PAID`: use `Converter<String, OrderStatus>`.
- The string `"15/03/2025"` to `LocalDate`, and printing it back in the user's date format: use `Formatter<LocalDate>`.
- The string `"42"` to `Integer`: Spring already has a default converter, so there is no need to write one.
- An amount of money that must be parsed/printed with a decimal separator and symbol by country: usually use a formatter or an appropriate currency API.

**Do not use `Formatter` for every conversion.** If you only need to transform a type and do not need a locale-specific representation, `Converter` is more concise and its purpose is clearer.

## 3. `Converter<S, T>`: one-way, explicitly typed conversion

The interface in the `org.springframework.core.convert.converter` package:

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

`S` is the source type and `T` is the target type. On each call to `convert`, the source is guaranteed to be non-null by Spring's contract. A converter should be safe for concurrent use from many requests; avoid keeping per-request mutable state in a shared bean.

Example of converting a string to an enum:

```java
public enum OrderStatus {
    PENDING, PAID, CANCELLED
}

public final class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        try {
            return OrderStatus.valueOf(
                    source.trim().toUpperCase(Locale.ROOT)
            );
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Expected PENDING, PAID or CANCELLED", ex
            );
        }
    }
}
```

`Locale.ROOT` is used when normalizing technical tokens such as enum names. Do not use the user's current locale to change the case of protocol codes or fixed status codes.

Principles:

1. **Validate and normalize input:** `trim()` if surrounding whitespace is allowed.
2. **Do not hide bad data:** if a token is invalid, throw `IllegalArgumentException` with a useful message.
3. **Do not return `null` arbitrarily:** define clearly whether empty input means missing data, a default value, or an error.
4. **Do not perform I/O in a converter:** a converter should be a fast, deterministic transformation; querying the database to turn an ID into an entity is the service's responsibility.
5. **Do not store request state:** a converter is usually registered for shared use and may be called concurrently.

Spring ships many converters in `core.convert.support`, for example converting String to numbers, Boolean, enums, collections, and other common types. Make use of the default converters before adding custom logic.

## 4. Extension SPIs: `ConverterFactory` and `GenericConverter`

### 4.1. `ConverterFactory<S, R>`

Use `ConverterFactory` when one source type can be converted into many target types belonging to the same family or base class.

For example, a factory that converts String into different enums:

```java
public interface ConverterFactory<S, R> {
    <T extends R> Converter<S, T> getConverter(Class<T> targetType);
}
```

Spring can use the factory to create a converter suited to a specific target enum type. For a single enum such as `OrderStatus`, `Converter<String, OrderStatus>` is usually enough; there is no need to write a factory.

### 4.2. `GenericConverter`

`GenericConverter` is more flexible but less type-safe. It can convert multiple source/target pairs and receives a `TypeDescriptor`:

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

`TypeDescriptor` provides generic type information and metadata on fields/methods, such as the element type of a `List<T>` or an annotation on the target field. This is why Spring can reuse an element converter to convert collections/arrays without needing a separate converter for every combination.

Use `GenericConverter` only when you need to handle multiple source/target types or read metadata. For simple conversions, prefer `Converter` or `ConverterFactory`.

### 4.3. `ConditionalGenericConverter`

If a converter applies only under a condition, for example the target field carries a specific annotation or the target type has a specific factory method, use `ConditionalGenericConverter`:

```java
public interface ConditionalConverter {
    boolean matches(TypeDescriptor sourceType, TypeDescriptor targetType);
}

public interface ConditionalGenericConverter
        extends GenericConverter, ConditionalConverter {
}
```

`matches(...)` lets Spring check the condition before choosing a converter. Do not use the conditional style merely to replace a simple parse; it is meant for cases where the choice of converter depends on the metadata of the source/target type.

## 5. `Formatter<T>`: parse and print by Locale

`Formatter<T>` is in the `org.springframework.format` package and extends two interfaces:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
```

Two methods:

```java
public interface Parser<T> {
    T parse(String text, Locale locale) throws ParseException;
}

public interface Printer<T> {
    String print(T object, Locale locale);
}
```

- `parse` receives text from the client and creates an object.
- `print` converts an object into a string for display.
- `Locale` indicates the language/regional rules to apply.

Example with dates:

```java
public final class LocalDateFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatter(Locale locale) {
        return DateTimeFormatter
                .ofPattern("dd/MM/uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        try {
            return LocalDate.parse(text.trim(), formatter(locale));
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Expected date in dd/MM/uuuu format", ex
            );
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatter(locale).format(value);
    }
}
```

In the example, `ResolverStyle.STRICT` requires a date to be valid according to the calendar, avoiding automatically adjusting a nonexistent date to another date. The formatter does not use a shared mutable `SimpleDateFormat`; `DateTimeFormatter` is immutable and thread-safe.

If you only need one direction, Spring lets you register a `Parser<T>` or `Printer<T>` separately instead of a full `Formatter<T>`.

## 6. `ConversionService` and `FormatterRegistry`

### 6.1. `ConversionService`

`ConversionService` is the unified API for checking and performing conversions at runtime:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);

boolean canConvert(
        TypeDescriptor sourceType,
        TypeDescriptor targetType
);

Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType
);
```

Example:

```java
ConversionService service = ...;

boolean supported = service.canConvert(String.class, LocalDate.class);

LocalDate date = service.convert(
        "15/03/2025", LocalDate.class
);
```

`canConvert` is useful when you want to check an optional conversion in advance. Do not use it as a substitute for error handling: between the check and the conversion, the data can still be invalid.

When you need to convert a generic type such as `List<Integer>` to `List<String>`, the overload that takes a `TypeDescriptor` lets Spring know the source and target element types. Passing only `List.class` is not enough to fully describe the generic element type.

### 6.2. `ConverterRegistry` and `FormatterRegistry`

`ConverterRegistry` is the SPI for registering converters. `FormatterRegistry` extends this registry and provides these additional methods:

```java
void addFormatter(Formatter<?> formatter);
void addFormatterForFieldType(
        Class<?> fieldType, Formatter<?> formatter
);
void addFormatterForFieldType(
        Class<?> fieldType, Printer<?> printer, Parser<?> parser
);
void addFormatterForFieldAnnotation(
        AnnotationFormatterFactory<? extends Annotation> factory
);
void addParser(Parser<?> parser);
void addPrinter(Printer<?> printer);
```

`FormattingConversionService` both performs conversion and is the place where formatters are registered. `DefaultFormattingConversionService` is an implementation preconfigured with common converters and formatters, suitable for most applications.

This is a stateless object designed to be created at startup and shared among many threads. Do not create a new conversion service for each request.

### 6.3. `FormatterRegistrar`

If a group of formats needs to register many related converters/formatters, you can gather the logic in a `FormatterRegistrar`:

```java
public interface FormatterRegistrar {
    void registerFormatters(FormatterRegistry registry);
}
```

This approach helps configure by group, for example dates, currencies, or identifiers, instead of scattering many registration lines throughout the configuration.

## 7. Built-in format annotations

Spring provides annotations to declare rules on a field or method parameter:

- `@DateTimeFormat`: formats date/time; can use ISO, a style, or a pattern.
- `@NumberFormat`: formats numbers; supports a style or a pattern.
- In newer versions, there are additional format annotations for some types such as `Duration`; check the API for the exact Spring version of your project.

Example:

```java
public class SearchCriteria {

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate from;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal minimumAmount;

    // getter/setter
}
```

The annotation describes a rule on a specific field. A formatter registered by type applies a general rule for that type. When you need a rule that depends on a custom annotation, use `AnnotationFormatterFactory`.

Do not put a format annotation on a field just to solve validation. `@DateTimeFormat` is about how to parse/print; `@NotNull`, `@Positive`, or a validator describe the validity conditions of the data.

## 8. WebFlux automatically applies conversion when binding parameters

Spring WebFlux converts the string values of annotated controller method arguments when the parameter type is not `String`. Common places:

- `@RequestParam`: query parameter.
- `@PathVariable`: variable in the URI template.
- `@RequestHeader`: HTTP header.
- `@CookieValue`: cookie.
- `@ModelAttribute`: binds request data into a command object.

Example:

```java
@GetMapping("/orders")
Mono<String> search(
        @RequestParam("status") OrderStatus status,
        @RequestParam("from") LocalDate from) {

    return Mono.just(status + "|" + from);
}
```

When the client sends `?status=paid&from=15%2F03%2F2025`, WebFlux takes the string values, uses the configured conversion service to create `OrderStatus` and `LocalDate`, and only then calls the method.

One difference to remember: in WebFlux, `@RequestParam` only accesses query parameters. Form data and multipart are accessed separately through `ServerWebExchange`; they can take part in binding a command object with `@ModelAttribute`.

**Conversion does not mean validation.** A converter/formatter determines whether a string can be represented as a Java type. Bean Validation or a Spring `Validator` checks business conditions after the data has been bound.

For example, the date `31/02/2025` cannot be parsed into a valid date; but a calendar-valid date can still violate business rules, such as a start date that falls after the end date. The latter case needs separate validation.

## 9. Registering a Converter and Formatter for Spring WebFlux

The standard way to configure is to implement `WebFluxConfigurer` and add converters/formatters through `addFormatters`:

```java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderStatusConverter());
        registry.addFormatter(new LocalDateFormatter());
    }
}
```

In a Spring Boot application using `spring-boot-starter-webflux`, you can register this configuration class as a `@Configuration` bean; Boot and WebFlux aggregate the `WebFluxConfigurer`s to configure the conversion service used for annotated controllers.

If you use plain WebFlux configuration with `@EnableWebFlux`, you can also implement `WebFluxConfigurer`. Avoid creating a local `DefaultFormattingConversionService` and then using it only in your own service if the goal is to change controller binding: that registry must be registered into the correct WebFlux infrastructure.

For a standard group of date formats, you can use `DateTimeFormatterRegistrar`:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar =
            new DateTimeFormatterRegistrar();

    registrar.setUseIsoFormat(true);
    registrar.registerFormatters(registry);

    registry.addConverter(new StringToOrderStatusConverter());
}
```

By default, WebFlux takes the request `Locale` into account when parsing/formatting date values. However, HTML `<input type="date">` and `<input type="time">` send a fixed format per the HTML specification; for those fields, the ISO format is usually more suitable. Agree on a consistent format between the browser, the API, and the server instead of depending on the locale implicitly.

## 10. Standalone Java 17+ example with `DefaultFormattingConversionService`

This example shows the same conversion service handling two kinds of rules:

- `Converter<String, OrderStatus>` converts the status code.
- `Formatter<LocalDate>` parses and prints dates in the chosen format.

Structure:

```text
converter-formatter-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

The `pom.xml` file:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>converter-formatter-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.11</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The `src/main/java/demo/Main.java` file:

```java
package demo;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;

enum OrderStatus {
    PENDING, PAID, CANCELLED
}

final class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        try {
            return OrderStatus.valueOf(
                    source.trim().toUpperCase(Locale.ROOT)
            );
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Expected PENDING, PAID or CANCELLED", ex
            );
        }
    }
}

final class LocalDateFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatter(Locale locale) {
        return DateTimeFormatter.ofPattern("dd/MM/uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        try {
            return LocalDate.parse(text.trim(), formatter(locale));
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Expected date in dd/MM/uuuu format", ex
            );
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatter(locale).format(value);
    }
}

public final class Main {
    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        service.addConverter(new StringToOrderStatusConverter());
        service.addFormatter(new LocalDateFormatter());

        LocaleContextHolder.setLocale(Locale.forLanguageTag("vi-VN"));
        try {
            OrderStatus status =
                    service.convert(" paid ", OrderStatus.class);

            LocalDate date =
                    service.convert("15/03/2025", LocalDate.class);

            String printedDate = service.convert(date, String.class);

            System.out.println("status=" + status);
            System.out.println("date=" + date);
            System.out.println("printed=" + printedDate);
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

From the `converter-formatter-demo/` directory, run with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

Stdout:

```text
status=PAID
date=2025-03-15
printed=15/03/2025
```

Explanation:

1. `DefaultFormattingConversionService` initializes the default converters and formatters.
2. `addConverter` registers the custom converter for `OrderStatus`.
3. `addFormatter` registers the parser/printer for `LocalDate`.
4. `convert(" paid ", OrderStatus.class)` calls the converter, normalizes the token, and creates `PAID`.
5. `convert("15/03/2025", LocalDate.class)` calls the formatter to parse the date.
6. `convert(date, String.class)` uses the formatter's printer; `LocaleContextHolder` provides the current locale for the console example.
7. `finally` resets the locale context so that no locale remains attached to the thread after the demo ends.

This is a console program that tests the conversion service. It does not start a WebFlux server; section 9 shows how to register those same converters/formatters into WebFlux.

## 11. Integration example in a WebFlux controller

After configuring `WebFluxConfigurer` in section 9, the controller can receive the target types directly:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping
    Mono<String> search(
            @RequestParam("status") OrderStatus status,
            @RequestParam("from") LocalDate from) {

        return Mono.just(status + "|" + from);
    }
}
```

With the server running at `localhost:8080`, send the request:

```bash
curl --get "http://localhost:8080/orders" \
  --data-urlencode "status=paid" \
  --data-urlencode "from=15/03/2025"
```

Response body:

```text
PAID|2025-03-15
```

This is an integration example that depends on a Spring Boot WebFlux application that already has `spring-boot-starter-webflux`, the `WebConfig` configuration, and the types `OrderStatus`, `StringToOrderStatusConverter`, and `LocalDateFormatter`. It is not a second standalone program.

If the client sends `status=unknown` or an invalid date, conversion fails before the controller receives the parameter. WebFlux handles it as an argument binding error; normally an invalid request is mapped to HTTP 400, unless the application changes exception handling. Do not catch every conversion error and then silently assign a default value.

## 12. `Converter` and `Formatter` do not replace HTTP message codecs

An easily confused point: conversion/formatting of controller parameters is not the same as handling a JSON body.

- `@RequestParam`, `@PathVariable`, `@RequestHeader`, `@CookieValue`, and data binding for `@ModelAttribute` usually start from string data; the conversion service is appropriate for this step.
- A JSON `@RequestBody` is read by an `HttpMessageReader`/codec, usually through Jackson. JSON serialization/deserialization configuration lives in the corresponding codec/ObjectMapper.
- A JSON `@ResponseBody` is also written by an `HttpMessageWriter`/codec; `Formatter` does not automatically format every JSON field.
- If you want to format a JSON field according to the API contract, configure a serializer/deserializer or an explicit DTO representation; do not assume `@DateTimeFormat` will automatically change how Jackson writes JSON.

Choosing the extension point at the right layer helps avoid the situation where a format works for a query parameter but does not apply to the JSON body.

## 13. Empty strings, parse errors, and validation

### 13.1. Missing parameters and empty parameters

Two different requests:

```text
GET /orders
GET /orders?limit=
```

- `limit` not sent: the parameter may be missing according to the `required` rule.
- `limit=` sent: the value is an empty string; the conversion process may treat it as missing if the conversion result is `null`.

For `Long`, `UUID`, and some other types, an empty string may be converted to `null`. If the parameter is required, WebFlux may report a missing parameter/value error after conversion. If the business rules allow it to be missing, use `required = false`, `Optional<T>`, or a nullable declaration appropriate to the codebase.

Do not return `null` from a converter just to dodge a data error if the business rule has not been clearly defined.

### 13.2. Actionable error messages

A converter/formatter should throw an exception that describes the expected value, for example:

```java
throw new IllegalArgumentException(
        "Expected status: PENDING, PAID or CANCELLED"
);
```

Do not put stack traces, internal information, or sensitive data into error messages sent to the client. Log details on the server according to the security policy, while the response should have a clear and safe message.

### 13.3. Conversion is not validation

Examples:

- `"100"` is successfully converted to `BigDecimal`.
- But a negative amount may be invalid for the business.
- `"2025-03-15"` is successfully parsed to `LocalDate`.
- But that date may fall outside the allowed range.

Use Bean Validation (`@NotNull`, `@Positive`, `@Size`, custom constraints) or a Spring `Validator` after binding to check business conditions. In a controller, `@Valid`/`@Validated` and `BindingResult`/`Errors` are used according to the handler method's rules.

Do not turn a converter into a place that accesses the database or checks access permissions. Those checks belong to the service/domain layer.

## 14. Common mistakes and how to fix them

| Mistake | Consequence | Fix |
|---|---|---|
| Writing a converter for a type Spring already supports | Duplication and may change default behavior | Check `canConvert` and the default converters first |
| Using `Converter` to handle locale-specific dates | No `Locale` parameter, making parse/print hard to manage | Use `Formatter<T>` |
| Using `Formatter` for a purely domain conversion | The code gains unnecessary print/locale logic | Use `Converter<S,T>` |
| Not normalizing enums/tokens | Input with whitespace or lowercase causes unexpected errors | `trim()` and use `Locale.ROOT` for technical tokens |
| Using a mutable `SimpleDateFormat` in a singleton formatter | May hit race conditions with concurrent requests | Use `DateTimeFormatter` or a thread-safe formatter |
| Catching an exception and returning `null` with no rule | A wrong value becomes missing data, hard to debug | Throw `IllegalArgumentException` or clearly define an empty policy |
| Registering the formatter only in a separate service | The WebFlux controller still uses the default registry | Register via `WebFluxConfigurer.addFormatters` |
| Creating a new `ConversionService` per request | Wastes resources and gives inconsistent configuration | Create a single instance shared across the application |
| Thinking a converter handles the JSON body | JSON is still read independently by the codec/Jackson | Configure the HTTP message codec/serializer |
| Using conversion to check business rules | The type conversion succeeds but the data is still wrong for the business | Use Bean Validation or service/domain validation |
| Using a date format inconsistent with the browser | `<input type=date>` sends ISO but the formatter expects a local format | Agree on ISO or configure an appropriate registrar |
| Overriding default converters without testing | Other APIs may change behavior | Limit the source/target and test boundary inputs |

## 15. Testing converters and formatters

You should test both valid and invalid cases:

| Case | Expectation |
|---|---|
| `"paid"` → `OrderStatus` | `PAID` |
| `" CANCELLED "` → `OrderStatus` | `CANCELLED` |
| `"unknown"` → `OrderStatus` | A conversion error is thrown |
| `"15/03/2025"` → `LocalDate` | `2025-03-15` |
| `LocalDate.of(2025, 3, 15)` → String | `"15/03/2025"` with the registered formatter |
| `"31/02/2025"` → `LocalDate` | Parse error because the date is invalid |
| Missing query param | Behavior follows `required`/`Optional` |
| Query param is an empty string | Behavior follows the conversion rules and nullability |

A unit test for a converter/formatter can call `convert`, `parse`, and `print` directly. A WebFlux integration test should send a real HTTP request through `WebTestClient` to verify that the registry has been configured and the argument resolver actually uses it.

Example test for the conversion service:

```java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

service.addConverter(new StringToOrderStatusConverter());
service.addFormatter(new LocalDateFormatter());

assertEquals(
        OrderStatus.PAID,
        service.convert("paid", OrderStatus.class)
);

assertEquals(
        LocalDate.of(2025, 3, 15),
        service.convert("15/03/2025", LocalDate.class)
);
```

This is a test snippet that needs JUnit and the imports of the types in the example; it is not a standalone runnable file. Additional integration tests should verify the response with `status=unknown`, an invalid date, a missing query param, and different locales.

## 16. Self-check exercises

**Question 1.** What should be used to convert `"paid"` to `OrderStatus.PAID`?

**Answer:** `Converter<String, OrderStatus>`, because this is a one-way type conversion that needs neither a locale nor printing back.

**Question 2.** Why might `Formatter<LocalDate>` be more suitable than `Converter<String, LocalDate>`?

**Answer:** A formatter has both `parse` and `print`, receives a `Locale`, and is suited to date data displayed/entered according to regional rules.

**Question 3.** Which interfaces does `Formatter<T>` extend?

**Answer:** `Printer<T>` and `Parser<T>`.

**Question 4.** To register a custom converter and formatter so WebFlux uses them for controller parameters, where do you configure it?

**Answer:** Implement `WebFluxConfigurer` and register through `addFormatters(FormatterRegistry registry)`.

**Question 5.** Does `ConversionService` automatically check `amount > 0`?

**Answer:** No. It converts types; business conditions need Bean Validation or a Spring Validator/domain logic.

**Question 6.** Does a JSON `@RequestBody` automatically use the Formatter registered for query parameters?

**Answer:** Not by default. The JSON body is handled through HTTP message codecs, usually Jackson; you need to configure the corresponding serializer/deserializer if you want custom JSON formatting.

**Question 7.** Why should converters/formatters be thread-safe?

**Answer:** Spring usually registers them in a conversion service shared across many concurrent requests.

**Question 8.** When a query param is an empty string, is it always equivalent to a missing parameter?

**Answer:** No. The behavior depends on the converter and the target type; some conversions return `null`, which makes Spring treat it as missing. You need to define required/nullable/Optional clearly.

## 17. Selection rules

- Choose **`Converter<S,T>`** for clear type conversion that does not depend on locale.
- Choose **`Formatter<T>`** when you need to parse and print text data by locale.
- Choose **`ConverterFactory`** for a family of target types; choose **`GenericConverter`** when you need multiple type pairs or a `TypeDescriptor`.
- Use **`DefaultFormattingConversionService`** for applications that need both default converters and formatters.
- Register the converters/formatters used in WebFlux with **`WebFluxConfigurer.addFormatters`**.
- Distinguish conversion, formatting, validation, and JSON codecs; each layer has its own job.
- Test empty input, wrong format, locale, missing parameters, and boundary values.

**Remember:** `Converter` converts types; `Formatter` parses and prints text by `Locale`. Spring WebFlux uses the conversion service to bind string data into controller parameters. Register rules once through `WebFluxConfigurer`, keep converters/formatters thread-safe, and use separate validation to check business conditions.

## 18. Official references

- [Spring Framework — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework — WebFlux Type Conversion](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/typeconversion.html)
- [Spring Framework — WebFlux `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html)
- [Spring Framework 6.1.11 — `DefaultFormattingConversionService` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/format/support/DefaultFormattingConversionService.html)
- [Spring Framework 6.1.11 — `Formatter` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework 6.1.13 — `WebFluxConfigurer` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html)
