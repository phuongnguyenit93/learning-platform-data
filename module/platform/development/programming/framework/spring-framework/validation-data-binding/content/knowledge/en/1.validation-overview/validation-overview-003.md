# Type conversion and data formatting in Spring

## 1. Why are type conversion and formatting needed?

Data entering a Spring MVC application usually originates from URLs, query parameters, path variables, headers, or HTML forms. At the HTTP boundary, these values typically have a text representation, whereas Java code needs meaningful types such as `Integer`, `BigDecimal`, `LocalDate`, `UUID`, enums, or domain types. When rendering data back onto a form, the application also has to convert Java values into strings following date, number, and user language rules.

For example: the request `GET /orders?quantity=3&orderedOn=2026-11-02` has `quantity` as the text "3" and `orderedOn` as the text "2026-11-02". The controller wants to receive an integer and a date. Spring can convert them before invoking the handler method, instead of forcing the controller to call `Integer.parseInt` and `LocalDate.parse` for every parameter.

Four tasks should be distinguished:

| Concept | Question it solves | Example |
| --- | --- | --- |
| **Type conversion** | How to transform a value of type A into type B? | String "42" into `Integer`; product code string into `ProductCode` |
| **Formatting** | How to convert a value to or from a string according to presentation conventions? | `LocalDate` into a date displayed per `Locale`; "1,234.50" into a number per English settings |
| **Data binding** | How to map request parameters into method parameters or object properties? | `price=12.50` into the `price` property of a form object |
| **Validation** | Does the converted value satisfy business rules? | Quantity must be greater than 0; start date must not be after end date |

Type conversion and formatting participate in the binding process; validation usually runs after data has been bound or binding has been attempted. Invalid syntax (such as the string "abc" for an integer) is a type conversion error, distinct from the integer -2 which converted successfully yet violates `@Min(1)`.

Typical flow in Spring MVC:

~~~text
HTTP request (query/form/path/header)
        |
        v
HandlerMethodArgumentResolver / WebDataBinder
        |
        v
ConversionService / Converter / Formatter
        |
        +--> Success: Java type, bound to parameter or model attribute
        |
        +--> Failure: typeMismatch error / binding error handling
        |
        v
Validation if configured -> controller -> result/HTML
~~~

Specifically, `@RequestBody` containing JSON/XML goes primarily through `HttpMessageConverter` (typically Jackson for JSON). Jackson has its own deserialization system. Do not assume that registering a `Converter<String, T>` for Spring MVC will change how Jackson reads a field in JSON.

## 2. Core components

### 2.1. ConversionService and ConverterRegistry

`org.springframework.core.convert.ConversionService` is the unified API to ask whether a type conversion is supported and to request a conversion:

~~~java
boolean supported = conversionService.canConvert(String.class, Integer.class);
Integer value = conversionService.convert("42", Integer.class);
~~~

`ConversionService` only exposes usage capabilities. Registering converters belongs to `ConverterRegistry`. Some common implementations:

- `GenericConversionService`: engine that registers and executes converters.
- `DefaultConversionService`: comes pre-configured with common converters for numbers, strings, enums, collections, and standard types.
- `FormattingConversionService`: combines `ConversionService` with `FormatterRegistry` to handle both conversion and formatting.
- `DefaultFormattingConversionService`: installs default converters and formatters, including support for common formatting annotations.

Do not create a new `ConversionService` for every HTTP request. Normally, configure one shared instance at application startup. Converters that are stateless or hold read-only state are convenient and safer for concurrent reuse.

When richer type metadata than `Class<?>` is needed, Spring uses `TypeDescriptor`. It describes source/target types, including generics, properties, and annotations where applicable. This mechanism is important when converting `List<String>` into a list of another element type, or when a formatter depends on annotations on a field.

### 2.2. Choosing the right SPI

| SPI | Capability | When to use |
| --- | --- | --- |
| `Converter<S, T>` | Converts a specific source type to a specific target type via `T convert(S source)` | Most domain conversion rules |
| `ConverterFactory<S, R>` | Creates converters for a family of target types | For example, a family of enums or subclasses of a common base class |
| `GenericConverter` | Inspects `ConvertiblePair` and `TypeDescriptor` at runtime | Rules depending on generics/annotations or multiple type pairs |
| `ConditionalGenericConverter` | Adds a matching condition to a generic converter | Activate only when target type metadata meets a condition |
| `Formatter<T>` | Combines `Printer<T>` and `Parser<T>`, taking a `Locale` parameter | Parsing and printing dates, money, percentages, or locale-dependent display values |
| `AnnotationFormatterFactory<A>` | Selects parser/printer based on field annotation | Building custom annotation-driven formatting |

Prefer `Converter<S, T>` for presentation-independent conversions; prefer `Formatter<T>` when a value must be parsed and printed as a string, especially when `Locale` is needed. Only use `GenericConverter` when the simpler APIs cannot fully express the rule.

## 3. Runnable example: custom Converter<String, ProductCode>

This is a standalone Java 17+ application using Spring Core; no web server needs to be started. The rule of the example: product codes are always normalized to uppercase and must match `SKU-` followed by four alphanumeric characters.

Create `src/main/java/ConversionExample.java`:

~~~java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

record ProductCode(String value) {
    ProductCode {
        if (value == null || !value.matches("SKU-[A-Z0-9]{4}")) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}

final class ProductCodeConverter implements Converter<String, ProductCode> {
    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        return new ProductCode(normalized);
    }
}

public class ConversionExample {
    public static void main(String[] args) {
        DefaultConversionService conversions = new DefaultConversionService();
        conversions.addConverter(new ProductCodeConverter());

        Integer quantity = conversions.convert("42", Integer.class);
        ProductCode code = conversions.convert(" sku-a123 ", ProductCode.class);

        System.out.println(quantity);
        System.out.println(code);
        System.out.println(conversions.canConvert(String.class, ProductCode.class));
    }
}
~~~

Minimal `build.gradle` file:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-core:7.0.9'
}

application {
    mainClass = 'ConversionExample'
}
~~~

With JDK 17+ and Gradle installed, run:

~~~bash
gradle -q run
~~~

Standard output:

~~~text
42
ProductCode[value=SKU-A123]
true
~~~

Explanation:

1. `DefaultConversionService` already provides the `String -> Integer` conversion.
2. `addConverter` registers the custom `String -> ProductCode` rule. `Locale.ROOT` makes code normalization independent of the user's locale.
3. The record enforces input invariants. Strings not matching the pattern cause conversion to fail with an exception; in a web context, Spring can translate that failure into a binding error.
4. `canConvert` only indicates that a conversion path is registered; it **does not prove** every source value is valid. For instance, `SKU-ABCDEF` will still be rejected during actual conversion.

If the project uses Spring Boot or another Spring Framework version, use the `spring-core` version managed by the project's dependency management instead of the hardcoded version in this standalone example. Converters should handle a predictable rule; avoid database queries or network calls inside a simple value conversion.

## 4. Formatting: Formatter, Printer, Parser, and Locale

`Formatter<T>` has two directions:

- `T parse(String text, Locale locale)`: parses user-entered string into a typed value.
- `String print(T value, Locale locale)`: produces a display string from a typed value.

The example below is a formatter for `LocalDate` that displays dates in the locale's medium date style; place this class in a project with `spring-context` or the corresponding Spring formatting library:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import org.springframework.format.Formatter;

public final class LocalDateDisplayFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatFor(Locale locale) {
        return DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(locale);
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatFor(locale).format(value);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, formatFor(locale));
    }
}
~~~

`DateTimeFormatter` is immutable, which suits multi-threaded applications. For the same `LocalDate`, different locales may yield different display strings; do not assume a date string entered under locale A will parse properly under locale B. If an external API needs a fixed format, choose ISO-8601 rather than relying on locale or OS settings.

Spring also provides built-in formatters for numbers, currency, percentages, and date/time. You do not need to write a custom formatter just to read an ISO date or ordinary number. When writing a formatter for currency, pay attention to currency units, rounding, and `BigDecimal`; `double` is unsuitable for many exact monetary calculations.

`FormattingConversionService`/`FormatterRegistry` enables centralized registration of converters and formatters. Example in a Spring MVC project:

~~~java
import java.time.LocalDate;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class DateDisplayConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
                LocalDate.class, new LocalDateDisplayFormatter());
    }
}
~~~

This is an **integration snippet**, not a standalone program with `main`: place it in the same package as `LocalDateDisplayFormatter` and run inside a Spring MVC application. Registering by type can affect many `LocalDate` fields across MVC; if one field needs a different presentation style, consider formatting annotations or a local rule. Do not add a global formatter merely to work around an issue on a single endpoint.

## 5. @DateTimeFormat and @NumberFormat annotations

Spring supports formatting directly at the field/parameter level, which is often easier to read than configuring an application-wide formatter.

### 5.1. Dates and times

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import org.springframework.format.annotation.DateTimeFormat;

public class BookingForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate arrivalDate;

    @DateTimeFormat(pattern = "dd/MM/yyyy HH:mm")
    private LocalDateTime appointmentTime;

    public LocalDate getArrivalDate() {
        return arrivalDate;
    }

    public void setArrivalDate(LocalDate arrivalDate) {
        this.arrivalDate = arrivalDate;
    }

    public LocalDateTime getAppointmentTime() {
        return appointmentTime;
    }

    public void setAppointmentTime(LocalDateTime appointmentTime) {
        this.appointmentTime = appointmentTime;
    }
}
~~~

- `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` expresses an ISO date input contract, e.g., `2026-11-02` for `LocalDate`. This is a good choice for HTML `input type="date"` and query parameters needing a stable format.
- `pattern = "dd/MM/yyyy HH:mm"` is a specific pattern, e.g., `02/11/2026 09:30`; the sender must use the exact expected format.
- `LocalDate` does not contain a time zone or time of day. `LocalDateTime` also does not represent an offset/time zone; for real instants across time zones, consider `Instant` or `OffsetDateTime` and define explicit time zone conventions.
- Patterns for parsing and display belong to the same formatting context. An invalid date string still creates a binding error; the annotation does not automatically check business validity such as whether the booking date is in the future.

### 5.2. Numbers and currency

~~~java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;

public class PaymentForm {
    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal subtotal;

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal displayAmount;

    public BigDecimal getSubtotal() {
        return subtotal;
    }

    public void setSubtotal(BigDecimal subtotal) {
        this.subtotal = subtotal;
    }

    public BigDecimal getDisplayAmount() {
        return displayAmount;
    }

    public void setDisplayAmount(BigDecimal displayAmount) {
        this.displayAmount = displayAmount;
    }
}
~~~

`@NumberFormat` supports patterns or styles such as `NUMBER`, `CURRENCY`, `PERCENT`. Thousands separators, decimal separators, and currency symbols can vary by `Locale`. For instance, the string `1,234.50` typically matches US English settings; do not send this raw string assuming every locale interprets it the same way.

A `BigDecimal` value holds a number; **it does not by itself carry a currency unit**. `CURRENCY` is a locale-based display/input rule, not a currency exchange mechanism or multi-currency resolver. Stored values and interchange payloads should follow an explicit contract; keep presentation rules at the UI boundary.

## 6. Registering converters/formatters in Spring MVC

The standard way to register shared rules in Spring MVC is `WebMvcConfigurer.addFormatters(FormatterRegistry)`. The following example converts a product code in `@RequestParam` using a custom converter, while accepting an ISO date. The classes belong to the same package in a Spring MVC/Spring Boot application with the web starter; the code is an integration example, so the host application must have web startup configuration.

File `ProductCode.java`:

~~~java
package com.example.catalog;

public record ProductCode(String value) {
    public ProductCode {
        if (value == null || !value.matches("SKU-[A-Z0-9]{4}")) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}
~~~

File `StringToProductCode.java`:

~~~java
package com.example.catalog;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToProductCode
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

File `CatalogMvcConfig.java`:

~~~java
package com.example.catalog;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CatalogMvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCode());
    }
}
~~~

File `CatalogController.java`:

~~~java
package com.example.catalog;

import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog")
public class CatalogController {

    @GetMapping("/preview")
    public String preview(
            @RequestParam("code") ProductCode code,
            @RequestParam("date")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate date) {
        return code.value() + " @ " + date;
    }
}
~~~

With the server running on `localhost:8080`, request:

~~~http
GET /catalog/preview?code=sku-a123&date=2026-11-02 HTTP/1.1
Host: localhost:8080
~~~

Text body result:

~~~text
SKU-A123 @ 2026-11-02
~~~

Path taken: MVC reads the `code` and `date` strings; the registered converter normalizes `code`, while the date formatter handles `date` according to `@DateTimeFormat`. The controller receives two typed Java objects without parsing them itself. If the product code or date is malformed, argument resolution may fail before entering the controller method, typically producing HTTP 400 via default error handling. The application can standardize error messages with `@ControllerAdvice`, rather than turning every parse error into a 500.

Besides `@RequestParam`, many `@PathVariable`, `@RequestHeader`, `@CookieValue`, and other string-sourced parameters also use MVC's type conversion mechanism. Whether a formatter is used at a particular site depends on the source type, annotations, and request binder.

## 7. Data binding into @ModelAttribute

For forms with multiple fields, `WebDataBinder` creates/populates values onto a data-receiving object. Example of a form class with date and budget properties:

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class SearchFilter {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate from;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal budget;

    public LocalDate getFrom() {
        return from;
    }

    public void setFrom(LocalDate from) {
        this.from = from;
    }

    public BigDecimal getBudget() {
        return budget;
    }

    public void setBudget(BigDecimal budget) {
        this.budget = budget;
    }
}
~~~

Controller using a dedicated input DTO and catching binding errors:

~~~java
package com.example.catalog;

import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SearchController {

    @InitBinder("searchFilter")
    public void configureBinding(WebDataBinder binder) {
        binder.setAllowedFields("from", "budget");
    }

    @GetMapping("/catalog/search")
    public String search(
            @ModelAttribute("searchFilter") SearchFilter filter,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "Invalid filter";
        }

        return "from=" + filter.getFrom()
                + ", budget=" + filter.getBudget();
    }
}
~~~

For example, when the request locale is `en_US`, `/catalog/search?from=2026-11-02&budget=1%2C234.50` can bind `from` to `LocalDate.of(2026, 11, 2)` and `budget` to `BigDecimal("1234.50")`. If a value fails to parse, `BindingResult` placed **immediately after** the `@ModelAttribute` parameter lets the controller read errors; you can inspect `getFieldErrors()` and the `typeMismatch` code to return detailed messages. Do not assume parsing behaves identically under a different request locale.

`@InitBinder` only configures the binder within controller scope, or a targeted scope if placed on `@ControllerAdvice`; local `Formatter` or `PropertyEditor` instances can be registered when needed. For example, `binder.addCustomFormatter(...)` is an option for a specific formatting type. `setAllowedFields` restricts which properties may be assigned via property binding, preventing clients from modifying unintended fields; constructor binding and related rules must still be designed carefully. Use form DTOs rather than binding directly onto domain entities with sensitive attributes.

## 8. Type conversion errors and interaction with validation

Spring does not silently turn a wrong-typed value into a valid one. Cases to distinguish:

| Input or situation | Stage | Appropriate handling |
| --- | --- | --- |
| `quantity=abc` for `int` | Conversion failed | Return data-type error / prompt to enter a number |
| `date=2026-02-30` for an ISO date | Date parsing failed | Return format/nonexistent-date error |
| `quantity=-3` for `int` with `@Min(1)` | Type conversion succeeded, validation failed | Return minimum-value rule error |
| Required `@RequestParam` absent | Argument resolution / missing value | Return missing-parameter error |
| Empty string converted to `null` in a required parameter | Post-conversion resolution | May be treated as missing value |
| JSON contains invalid type in `@RequestBody` | JSON deserialization / message conversion | Handle body-reading error; do not expect MVC Converter to handle it |

In `@ModelAttribute`, field binding errors can appear in `BindingResult`. Only afterward does `@Valid` or `@Validated` trigger validation according to its configuration. A property that failed to parse may not yet have a valid value for business constraints; the UI should surface parse errors first and avoid confusing messages.

For single parameters like `@RequestParam`, type conversion errors are usually represented by Spring MVC via `MethodArgumentTypeMismatchException` or corresponding resolution exceptions, then routed through the exception resolver. `@ModelAttribute` can be handled via `BindingResult` directly in the controller if declared adjacent to that parameter; omitting an error-handling parameter/validation setup can lead to exceptions such as `MethodArgumentNotValidException` depending on the case. Do not hardcode a single exception type for every binding path or every Spring version.

Validation can be combined:

~~~java
import jakarta.validation.constraints.Min;

public class QuantityForm {
    @Min(1)
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

For Bean Validation to work, the application must have the Jakarta Validation API and a suitable provider (in Spring Boot, typically the validation starter dependency), and the controller needs to enable validation such as `@Valid @ModelAttribute`. `@Min(1)` does not replace a converter; it checks quantity after type conversion succeeds. If `null` is unacceptable, add `@NotNull` instead of relying only on `@Min`.

## 9. Configuration scope and easily confused boundaries

**Converters in the Spring container vs. MVC:** `ConversionService` is used by Spring in many places such as bean property binding or SpEL; MVC has a conversion service for argument binding. Configuring a bean named `conversionService` and adding formatters via `WebMvcConfigurer.addFormatters` are related, yet you should not assume they are the same instance in every application setup. Register converters in the registry actually used by the failing flow.

**Global vs. local:** `addFormatters` is appropriate for shared, consistent rules across controllers. `@InitBinder` is appropriate for rules specific to a controller/model attribute. Field annotations are appropriate when that specific field has its own formatting convention. Avoid changing global default converters just to accommodate one exceptional input pattern.

**Binding vs. serialization:** `@RequestBody` is read from HTTP content by a message converter, typically Jackson, so date formatting in JSON is governed by Jackson configuration or Jackson annotations. Likewise, returning JSON depends on the serializer, not the `Formatter.print` direction of MVC forms. Test form/query and JSON as two separate flows.

**Input vs. display:** An API shared across systems should define canonical formats such as ISO-8601 for date/time and locale-independent number formats. An HTML page may choose user-friendly formats based on `Locale`; parsing and printing must use the same rules. Do not use display strings as the canonical storage representation.

**Whitespace and emptiness:** Custom converters may choose to `trim`/normalize. Document the convention explicitly because whitespace can sometimes be significant. For required parameters, an empty string may be converted to `null` and then treated as missing; `Optional<T>` or `required=false` should only be used if business logic truly permits absence.

**Thread safety:** Avoid sharing mutable `SimpleDateFormat` instances across requests. Use immutable `DateTimeFormatter` or create formatters per request. Do not store request/locale state in a singleton converter; `Formatter` already receives `Locale` as a parameter.

**Bad formatting and security flaws:** A converter is not the right place to persist changes, bypass authorization checks, or resolve sensitive domain objects directly from user strings. For object binding, use DTOs and restrict bindable fields; validation and authorization remain independent steps.

## 10. Choosing in real-world scenarios

| Need | Usually suitable approach | Reason |
| --- | --- | --- |
| Standard numeric/date/enum query parameter | Use built-in conversion; add `@DateTimeFormat` when ISO/pattern is needed | Minimal config, clear input contract |
| Business code string to value object | `Converter<String, ValueObject>` registered in the right-scoped registry | Centralizes normalization and invariants |
| Locale-dependent number/currency/date form field | `@NumberFormat`, `@DateTimeFormat`, or `Formatter<T>` | Supports both parse and print |
| Multiple formats driven by a custom annotation | `AnnotationFormatterFactory` | Explicit rule per field |
| Converting collections or types depending on generics/annotations | `GenericConverter`/`TypeDescriptor` | Requires runtime type metadata |
| Only one form has an exceptional rule | `@InitBinder` / local formatter | Limits side effects outside scope |
| Structured JSON or dates in `@RequestBody` | Configure Jackson/message converter | Matches the body deserialization layer |

Example testing checklist for a form or endpoint:

1. **Right path:** confirm whether the source is query/form/path or JSON; configure the formatter/converter on the component actually used.
2. **Happy path:** integers, ISO dates, custom value objects; verify both resulting Java types and responses.
3. **Invalid input:** letters in numbers, nonexistent calendar dates, malformed codes; expect clear binding errors and an appropriate HTTP status.
4. **Locale:** test the same number/date string under two locales to catch inconsistent separators and month/day ordering.
5. **Boundary values:** absent, empty, whitespace, `null`, huge values, or many decimal places.
6. **Validation:** separate type mismatch errors from `@NotNull`, `@Min`, `@Past`/`@Future` business errors.
7. **Impact scope:** test other endpoints to confirm a global custom converter/formatter does not alter input semantics unexpectedly.
8. **Safe binding:** send an extra disallowed field and verify the object is not populated unexpectedly.

## 11. Key takeaways

Spring separates type conversion (`ConversionService`, `Converter`) from locale-aware string parsing/printing (`Formatter`), then uses them in the data binding pipeline. For most common data types, built-in converters and annotations suffice. When adding custom rules, choose the simplest SPI, register it in the right scope, test both input and display paths, and handle binding errors separately from business validation. This forms the foundation for controllers to receive cleanly typed Java data without repetitive parsing logic.

### Official reference documentation

- [Spring Framework - Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework - Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring MVC - Type Conversion configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
- [Spring MVC - Controller argument type conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html)
- [Spring MVC - @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring MVC - Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
