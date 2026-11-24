# Spring MVC — Converter, Formatter, ConversionService, and Date/Time Formatting

## 1. Goal and Context

When an HTTP client sends `?quantity=3&deliveryDate=2026-12-31`, the raw data arrives as **strings**. A controller may want `int`, `LocalDate`, or a domain type like `ProductCode`. Spring performs data conversion during binding before invoking the handler.

After this lesson, you will be able to:

- Distinguish `Converter<S,T>` (type conversion), `Formatter<T>` (locale-aware parse/print), `ConversionService` (coordinating service), and `FormatterRegistry` (component registration).
- Write, register, and use custom converters/formatters for controller parameters and `@ModelAttribute` fields.
- Use `@DateTimeFormat` and `@NumberFormat` with Java Time and numbers; recognize formatting issues related to locale, time zones, offsets, and HTML forms.
- Understand type conversion errors, how they differ from Bean Validation, and how to test errors and real outputs.
- Configure Spring MVC using `WebMvcConfigurer#addFormatters` in a Spring Boot application without replacing the entire MVC configuration.

The scope is **Spring MVC Servlet stack** with Java 17+; the complete example uses Spring Boot 3.5.0 (Spring Framework 6.2). Several general Spring Core mechanisms also apply in other layers.

## 2. How Does Data Binding Need Conversion?

Consider the handler:

~~~java
@GetMapping("/search")
public String search(
        @RequestParam int page,
        @RequestParam LocalDate date) {
    return page + " / " + date;
}
~~~

This is a signature illustration without a class/config or date-format annotation. Request:

~~~http
GET /search?page=2&date=2026-12-31
~~~

The string `"2"` must become `int 2`; the date string must become `LocalDate`. When binding `@ModelAttribute`, similar conversion happens on properties:

~~~java
public class SearchForm {
    private Integer page;
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate date;

    public Integer getPage() { return page; }
    public void setPage(Integer page) { this.page = page; }
    public LocalDate getDate() { return date; }
    public void setDate(LocalDate date) { this.date = date; }
}
~~~

This form class snippet requires importing `java.time.LocalDate` and `org.springframework.format.annotation.DateTimeFormat`. It can be bound via `@ModelAttribute SearchForm form` in a controller.

Main flow:

1. Spring MVC identifies the controller method and the field names to extract from the request.
2. `WebDataBinder` determines the target type (`int`, `LocalDate`, `ProductCode`, etc.).
3. The `ConversionService`/formatting system looks up a converter or parser matching the type and annotations.
4. If conversion succeeds, Spring assigns the value to the method argument, JavaBean property, or constructor argument.
5. If it fails, Spring records a binding error or handles an exception depending on the handler signature; Bean Validation, if present, evaluates constraints afterward.

**Conversion is not business validation:** `age=17` converts successfully to `int 17` yet violates `@Min(18)`; `age=abc` fails right at the type conversion step.

## 3. API Map

| API | Purpose | Locale-aware? | Example usage |
| --- | --- | --- | --- |
| `Converter<S,T>` | Converts from a source type S to a target type T | No `Locale` parameter | `String → ProductCode`, `String → Enum` |
| `ConverterFactory<S,R>` | Supplies converters for target types in a family R | Not directly | One factory for enum types |
| `GenericConverter` | Complex conversion using `TypeDescriptor` | Not directly; has type/annotation metadata | Collections, generic fields, or annotation-driven |
| `Formatter<T>` | `parse(String, Locale) → T` and `print(T, Locale) → String` | Yes | Numbers, currency, dates/times by locale |
| `ConversionService` | Unified API: `canConvert`, `convert` | No Locale passed directly in common signatures | Provides conversion to binders/services |
| `FormatterRegistry` | Registers converters, formatters, annotation formatters | Not a direct conversion tool | `addConverter`, `addFormatter` |
| `FormattingConversionService` | `ConversionService` capable of registering and using formatters | Formatter looks up locale via formatting context | Spring MVC form binding |

`ConversionService` is a **facade**; `Converter`/`Formatter` supply the implementations. Spring already provides many built-in conversions (strings, numbers, booleans, enums, collections, dates/times). Write a new converter only when the type or business rule is not yet supported as needed.

### 3.1. Choosing Converter or Formatter?

- Use `Converter` when you want a **type-based** rule independent of language/locale, e.g., product code `ab-123 → ProductCode("AB-123")`.
- Use `Formatter` when display strings and user-entered strings depend on locale, e.g., `1,234.50` (en-US) vs `1.234,50` (vi-VN).
- For date/time, prefer built-in formatters and `@DateTimeFormat` instead of writing custom parsers when standard formats suffice.
- Do not rewrite `String → Integer` or `String → LocalDate` when default configuration or annotations already meet your needs.

## 4. Converter<S,T> — Simple Type Conversion

Interface declaration (summary):

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Example: a product code requiring three letters and three digits, independent of locale:

~~~java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class ProductCodeConverter implements Converter<String, ProductCode> {
    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z]{3}-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "Product code must match AAA-123");
        }
        return new ProductCode(normalized);
    }
}
~~~

Target type (Java 17 record):

~~~java
package demo;

public record ProductCode(String value) {
}
~~~

- `source="ab-123"` → `ProductCode("AB-123")`.
- `source="a-123"` → converter throws `IllegalArgumentException`.
- Spring typically calls the converter after resolving a source value; the `Converter` API contract guarantees the `source` parameter on each call is non-null.
- Converters are reused across requests, so write them **stateless and thread-safe**; `Locale.ROOT` avoids server-locale-dependent uppercasing.

One converter supports `String → ProductCode`; it does **not** automatically convert backward `ProductCode → String` under the same rule. If you need both directions in a purely type-based context, register a reverse converter; if you need locale-aware parse/print, see `Formatter`.

### 4.1. When to Use ConverterFactory and GenericConverter?

`ConverterFactory<S,R>` creates converters for subtypes within the same target family, such as one factory handling enums instead of writing a converter per enum. Spring already provides built-in enum handling, so you rarely need to write your own.

`GenericConverter` has a general signature:

~~~java
Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

Each `TypeDescriptor` exposes the concrete type, generic information, and field/annotation metadata; this is useful when conversion depends on structure like `List<String> → List<Integer>`. It is more complex than `Converter<S,T>`; use it only when you need that metadata. `ConditionalGenericConverter` can further restrict application via `matches(sourceType, targetType)`.

## 5. ConversionService — Usage and Registration

Core interface:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);
boolean canConvert(TypeDescriptor sourceType, TypeDescriptor targetType);
Object convert(Object source, TypeDescriptor sourceType, TypeDescriptor targetType);
~~~

Standalone Spring Core example (requires Spring libraries on the classpath):

~~~java
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService conversion = new DefaultConversionService();
conversion.addConverter(new ProductCodeConverter());

System.out.println(conversion.canConvert(String.class, ProductCode.class));
ProductCode code = conversion.convert("ab-123", ProductCode.class);
System.out.println(code.value());
~~~

Printed output:

~~~text
true
AB-123
~~~

This snippet runs in a context where `ProductCodeConverter` and `ProductCode` are already declared, not as a standalone Java file containing only those lines.

`canConvert` only confirms a matching conversion path exists by type; it does **not guarantee** a specific value is valid. `canConvert(String.class, ProductCode.class) == true`, yet `"123"` still causes the converter to fail.

When working with `List<String> → List<Integer>` in Java code, specifying `List.class` alone loses the generic element type. Use `TypeDescriptor`:

~~~java
import java.util.List;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService service = new DefaultConversionService();
Object converted = service.convert(
    List.of("10", "20"),
    TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(String.class)),
    TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class)));
System.out.println(converted);
~~~

Output:

~~~text
[10, 20]
~~~

In Spring MVC, conversion happens automatically when binding HTTP requests. **Do not assume a `ConversionService` bean you define yourself is automatically the exact instance MVC uses**; register converters/formatters in the supported MVC configuration (Section 7) when the goal is converting controller arguments.

## 6. Formatter<T> — Locale-Aware Parse and Print

Interface:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Two operations:

~~~java
String print(T value, Locale locale);
T parse(String text, Locale locale) throws ParseException;
~~~

`parse` reads a client value into a Java object, whereas `print` formats an object into a display string for the client. Both operations should be consistent for the same locale so users can re-submit a value just displayed to them. `Formatter` can be used in MVC form binding, view rendering, or programmatically after registration.

Example with the same numeric value `1234.50`:

| Locale | Common string | Meaning |
| --- | --- | --- |
| `en-US` | `1,234.50` | Comma grouping; dot decimal |
| `vi-VN` | `1.234,50` | Dot grouping; comma decimal |

Never write `replace(",", ".")` to handle all locales: this easily turns `1,234.50` into invalid data or misinterprets thousands vs. decimal separators.

`java.text.NumberFormat` and `DecimalFormat` can express locale-specific rules, but **these formatter types are not safe when sharing mutable instances across threads**. Create a new `DecimalFormat` per `parse`/`print` call or design another thread-safe mechanism.

## 7. Registering Converters and Formatters in Spring MVC

With Spring Boot and Java config:

~~~java
@Configuration
public class WebConversionConfig implements WebMvcConfigurer {
    private final AmountFormatter amountFormatter;

    public WebConversionConfig(AmountFormatter amountFormatter) {
        this.amountFormatter = amountFormatter;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
        registry.addFormatter(amountFormatter);
    }
}
~~~

Corresponding imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
~~~

This example class assumes `AmountFormatter` is registered as a Spring bean (see the complete project in Section 10). `addFormatters` is Spring MVC's recommended way to add converters/formatters while keeping necessary defaults. With Spring Boot MVC, you normally **do not need `@EnableWebMvc`**; adding it can disable helpful MVC auto-configurations provided by Boot.

`FormatterRegistry` extends converter registration capabilities; calls to `registry.addConverter(...)` and `registry.addFormatter(...)` contribute rules to MVC's conversion system. Avoid accidentally registering two competing strategies for the same source/target types without controlling precedence.

### 7.1. Per-Controller Configuration with @InitBinder

When a specialized rule applies only to a single model/controller, you can configure the binder:

~~~java
@InitBinder("filter")
public void bindFilter(WebDataBinder binder) {
    binder.addCustomFormatter(new CustomFilterFormatter());
}
~~~

This is an illustrative snippet (requiring class `CustomFilterFormatter` and full imports). `@InitBinder` can register formatters, converters, or editors depending on API and scope. If a type is used broadly across MVC, `WebMvcConfigurer#addFormatters` is usually clearer and more reusable.

Avoid using `PropertyEditor` in new code solely for routine type conversions: `ConversionService` and `Formatter` offer strongly typed, cleanly configurable APIs. If using legacy `PropertyEditor`, watch out for mutable state and instance lifecycle.

## 8. @DateTimeFormat with Java Time

Common `java.time` types:

| Type | What does it hold? | When to use |
| --- | --- | --- |
| `LocalDate` | Date; no time or time zone | Birthdays, delivery dates |
| `LocalTime` | Time of day; no date or time zone | Opening hours |
| `LocalDateTime` | Date + time, but **no** offset/zone | Appointment time at a location with an agreed timezone |
| `OffsetDateTime` | Date + time + UTC offset (e.g., +07:00) | APIs that must preserve the client's offset |
| `ZonedDateTime` | Date + time + region time zone with rules (e.g., Asia/Ho_Chi_Minh) | Schedules tied to a local time zone |
| `Instant` | A UTC point on the timeline | Logs, creation/update timestamps, system-to-system exchange |
| `Duration` / `Period` | Time duration / date-based period | Lengths and time arithmetic, not appointment dates |

`LocalDateTime` carries no offset; never guess whether `2026-12-31T09:30` is UTC or Vietnam time without a documented convention. An offset `+07:00` is not a time zone with historical/future DST rules.

### 8.1. Explicit ISO Formatting

~~~java
@GetMapping("/events")
public String events(
        @RequestParam("day")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate day,
        @RequestParam("at")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
        OffsetDateTime at) {
    return day + " | " + at;
}
~~~

Required imports:

~~~java
import java.time.LocalDate;
import java.time.OffsetDateTime;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
~~~

Corresponding data:

~~~text
/events?day=2026-12-31&at=2026-12-31T09:30:00.000%2B07:00
~~~

Note that `+` must be URL-encoded as `%2B` in query strings. Writing `+07:00` directly in URL form-encoding can cause `+` to be decoded as a space and trigger a parse error.

`@DateTimeFormat` works on **fields or method parameters**, for example:

~~~java
public class BookingForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    // Getters and setters...
}
~~~

If a client sends a JSON body and the controller uses `@RequestBody`, JSON is handled by an HTTP message converter (usually Jackson). **`@DateTimeFormat` belongs to Spring's formatting/binding mechanism**, not the sole or default way to customize JSON formats. For JSON, see Jackson configuration and `@JsonFormat` where needed.

### 8.2. Pattern, ISO, Style, and fallbackPatterns

~~~java
@DateTimeFormat(pattern = "dd/MM/uuuu")
private LocalDate visitDate;
~~~

With Java Time, the expected string is `31/12/2026`. Uppercase `M` denotes **month**, whereas lowercase `m` denotes **minute**. `HH` is 0–23 hour; `hh` is 1–12 hour, usually needing a.m./p.m. Pattern symbols differ in details between `java.time.format.DateTimeFormatter` and legacy `java.text.SimpleDateFormat`; do not copy patterns blindly between the two.

Three primary attributes of `@DateTimeFormat`:

- `iso = DateTimeFormat.ISO.DATE`, `ISO.TIME`, or `ISO.DATE_TIME`: preferred for APIs needing clear standard formats.
- `pattern = "..."`: uses an application-controlled layout, e.g., `dd/MM/uuuu` for a date form using `LocalDate`.
- `style = "..."`: relies on locale-based date/time styles; suitable for UI, though representations can vary across environments/JDKs.

Use **one clear primary rule**; avoid declaring conflicting `pattern`, `iso`, and `style`. Since Spring 5.3.5, `fallbackPatterns` lets you specify additional patterns accepted during parsing if the primary pattern does not match, for example (illustrative; weigh carefully before loosening an input contract):

~~~java
@DateTimeFormat(
        iso = DateTimeFormat.ISO.DATE,
        fallbackPatterns = {"dd/MM/uuuu"})
private LocalDate date;
~~~

Fallback patterns allow parsing legacy formats, but broaden what the API accepts. For machine-to-machine inputs, a single consistent ISO standard is usually better. Style-based formatting is affected by locale and JDK/CLDR; do not use it as a storage format or stable API contract.

### 8.3. HTML input date/datetime-local

~~~html
<input type="date" name="startDate">
<input type="datetime-local" name="appointment">
~~~

- Input `type="date"` typically submits `yyyy-MM-dd` even though browsers may render the date according to local display settings.
- Input `type="datetime-local"` submits local date + time **without a time zone**. It fits `LocalDateTime`, but the server needs an explicit rule to determine the time zone if converting to `Instant`.
- Pick `@DateTimeFormat(iso = DATE)` for `LocalDate` bound from a date input; for local date-time, pick `LocalDateTime` and the matching ISO format; if an absolute instant is needed, accept an offset/zone or supplementary time zone info.

If you want default ISO configuration for Java Time in MVC (without annotating every endpoint):

~~~java
@Configuration
public class IsoDateMvcConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
~~~

Additional import: `org.springframework.format.datetime.standard.DateTimeFormatterRegistrar`. This configuration example registers ISO globally at the MVC level; you do not need to merge this class directly into the Section 10 project since fields there are already explicitly annotated.

### 8.4. Time Zones and Offset Handling

For example, `2026-12-31T09:30:00+07:00` represents the same point in time as `2026-12-31T02:30:00Z`. However, `2026-12-31T09:30` (`LocalDateTime`) **does not identify a unique Instant** without an offset or zone.

For pure dates `LocalDate` (birthdays/delivery dates), do not coerce them to `Instant` when business logic does not require time; time-zone conversion can inadvertently shift the calendar day. For scheduled appointments, store the time-zone rule and decide explicitly how to handle ambiguous or non-existent local times caused by DST in other regions.

## 9. @NumberFormat and Locale

`@NumberFormat` supports formatting/parsing numeric values by type and locale:

~~~java
public class PricingForm {
    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal price;

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
}
~~~

Required imports:

~~~java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;
~~~

The number format `pattern` is interpreted within a locale context. The pattern `#,##0.00` describes grouping positions and fractional digits; grouping and decimal characters **are rendered differently** per locale. You can use `@NumberFormat(style = NumberFormat.Style.NUMBER)` or `Style.CURRENCY` when appropriate for the data type and UX.

Be careful: monetary values should not be stored or calculated with `double` when decimal precision is a business requirement; `BigDecimal` is generally appropriate. A UI formatter does not define rounding rules, currency units, or business validation. Do not use UI-locale grouping separators as an internal API protocol when you can transmit plain standard numbers (such as JSON numbers or fixed-contract decimal strings).

## 10. Runnable Project: Custom Converter + Formatter + Date/Time

This example combines all four concepts in Spring MVC. One endpoint accepts query parameters:
`code=ab-123` (custom `Converter`), `amount=1,234.50` (locale-aware custom `Formatter`), `deliveryDate=2026-12-31`, and `meetingAt=2026-12-31T09:30:00.000+07:00` (`@DateTimeFormat`).

Layout:

~~~text
conversion-demo/
├── pom.xml
├── src/main/java/demo/
│   ├── ConversionDemoApplication.java
│   ├── ProductCode.java
│   ├── ProductCodeConverter.java
│   ├── Amount.java
│   ├── AmountFormatter.java
│   ├── WebConversionConfig.java
│   └── QuoteController.java
└── src/test/java/demo/
    └── QuoteControllerTest.java
~~~

### 10.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conversion-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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
~~~

### 10.2. ConversionDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConversionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConversionDemoApplication.class, args);
    }
}
~~~

### 10.3. ProductCode.java

~~~java
package demo;

public record ProductCode(String value) {
}
~~~

### 10.4. ProductCodeConverter.java

~~~java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class ProductCodeConverter implements Converter<String, ProductCode> {
    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z]{3}-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "Product code must match AAA-123");
        }
        return new ProductCode(normalized);
    }
}
~~~

### 10.5. Amount.java

~~~java
package demo;

import java.math.BigDecimal;

public record Amount(BigDecimal value) {
}
~~~

### 10.6. AmountFormatter.java

~~~java
package demo;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

import org.springframework.format.Formatter;
import org.springframework.stereotype.Component;

@Component
public final class AmountFormatter implements Formatter<Amount> {

    @Override
    public Amount parse(String text, Locale locale) throws ParseException {
        DecimalFormat format = decimalFormat(locale);
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(text, position);

        if (parsed == null || position.getIndex() != text.length()) {
            int at = position.getErrorIndex() >= 0
                    ? position.getErrorIndex()
                    : position.getIndex();
            throw new ParseException("Invalid localized amount", at);
        }

        return new Amount((BigDecimal) parsed);
    }

    @Override
    public String print(Amount amount, Locale locale) {
        return decimalFormat(locale).format(amount.value());
    }

    private DecimalFormat decimalFormat(Locale locale) {
        DecimalFormat format =
                (DecimalFormat) NumberFormat.getNumberInstance(locale);
        format.setParseBigDecimal(true);
        format.setGroupingUsed(true);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        return format;
    }
}
~~~

Explanation:

- `parse` receives the request's locale from MVC; it creates a dedicated `DecimalFormat` per invocation, avoiding sharing a mutable formatter across threads.
- `setParseBigDecimal(true)` parses numbers as `BigDecimal`, avoiding conversion via `double`.
- `ParsePosition` rejects inputs that are not fully consumed; for real monetary data, also validate currency, scale, range, and stricter syntax.
- `print` uses the same locale rules and fixes **two decimal digits** for display.
- `@Component` allows MVC configuration and controllers to share a stateless bean. The bean holds only logic and no shared `DecimalFormat` instance.

### 10.7. WebConversionConfig.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConversionConfig implements WebMvcConfigurer {
    private final AmountFormatter amountFormatter;

    public WebConversionConfig(AmountFormatter amountFormatter) {
        this.amountFormatter = amountFormatter;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
        registry.addFormatter(amountFormatter);
    }
}
~~~

With this registration, Spring MVC knows how to accept `ProductCode` and `Amount`. The date types in the example use built-in formatters with `@DateTimeFormat`.

### 10.8. QuoteController.java

~~~java
package demo;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class QuoteController {
    private final AmountFormatter amountFormatter;

    public QuoteController(AmountFormatter amountFormatter) {
        this.amountFormatter = amountFormatter;
    }

    @GetMapping("/quote")
    public Map<String, String> quote(
            @RequestParam("code") ProductCode code,
            @RequestParam("amount") Amount amount,
            @RequestParam("deliveryDate")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate deliveryDate,
            @RequestParam("meetingAt")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            OffsetDateTime meetingAt,
            Locale locale) {

        Map<String, String> response = new LinkedHashMap<>();
        response.put("code", code.value());
        response.put("amount", amount.value().toPlainString());
        response.put("formattedAmount", amountFormatter.print(amount, locale));
        response.put("deliveryDate", deliveryDate.toString());
        response.put("meetingAt", meetingAt.toString());
        response.put("locale", locale.toLanguageTag());
        return response;
    }
}
~~~

The handler signature shows that parsing **has already occurred before entering the method body**. `Locale` is an MVC argument resolvable from the request, defaulting to `Accept-Language` in standard MVC config. Calling `amountFormatter.print(...)` explicitly here lets us observe the formatting direction; in MVC views, formatters can be invoked automatically when rendering fields.

### 10.9. Running and Observing

In the `conversion-demo` directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Send values using the US locale (`--data-urlencode` automatically encodes `+`, commas, dots, and the rest of the parameter):

~~~bash
curl -i -G 'http://localhost:8080/api/quote' \
  -H 'Accept-Language: en-US' \
  --data-urlencode 'code=ab-123' \
  --data-urlencode 'amount=1,234.50' \
  --data-urlencode 'deliveryDate=2026-12-31' \
  --data-urlencode 'meetingAt=2026-12-31T09:30:00.000+07:00'
~~~

HTTP **200 OK**, equivalent response body (JSON object key order may differ if serialization changes):

~~~json
{
  "code": "AB-123",
  "amount": "1234.50",
  "formattedAmount": "1,234.50",
  "deliveryDate": "2026-12-31",
  "meetingAt": "2026-12-31T09:30+07:00",
  "locale": "en-US"
}
~~~

`OffsetDateTime.toString()` may omit `:00` seconds when zero; do not compare verbatim against the raw input string when both represent the same instant.

Try values using the Vietnamese locale:

~~~bash
curl -i -G 'http://localhost:8080/api/quote' \
  -H 'Accept-Language: vi-VN' \
  --data-urlencode 'code=abc-123' \
  --data-urlencode 'amount=1.234,50' \
  --data-urlencode 'deliveryDate=2026-12-31' \
  --data-urlencode 'meetingAt=2026-12-31T09:30:00.000+07:00'
~~~

The two key numeric fields in the JSON will represent the corresponding values:

~~~json
{
  "amount": "1234.50",
  "formattedAmount": "1.234,50"
}
~~~

The other fields are still present in the response; this trimmed JSON snippet highlights only the two numeric fields. Grouping/decimal symbol behavior comes from the Java runtime's locale data; this example uses standard common locale data.

Invalid product code:

~~~bash
curl -i -G 'http://localhost:8080/api/quote' \
  -H 'Accept-Language: en-US' \
  --data-urlencode 'code=wrong' \
  --data-urlencode 'amount=1,234.50' \
  --data-urlencode 'deliveryDate=2026-12-31' \
  --data-urlencode 'meetingAt=2026-12-31T09:30:00.000+07:00'
~~~

Spring MVC cannot convert `"wrong"` to `ProductCode`, so the request normally returns **400 Bad Request**; the `quote` handler does not run. Similarly, `deliveryDate=31/12/2026` does not match `ISO.DATE`, and `amount=abc` fails `AmountFormatter`. Exact error JSON content depends on Spring Boot configuration and exception handling, so do not rely on default messages being stable.

In Windows PowerShell, use `curl.exe` on a single line or replace Bash's `\` line continuation with appropriate PowerShell syntax.

### 10.10. Testing HTTP Binding with MockMvc

File `src/test/java/demo/QuoteControllerTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void acceptsEnglishLocale() throws Exception {
        mvc.perform(get("/api/quote")
                .header("Accept-Language", "en-US")
                .param("code", "ab-123")
                .param("amount", "1,234.50")
                .param("deliveryDate", "2026-12-31")
                .param("meetingAt", "2026-12-31T09:30:00.000+07:00"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("AB-123"))
            .andExpect(jsonPath("$.amount").value("1234.50"))
            .andExpect(jsonPath("$.formattedAmount").value("1,234.50"))
            .andExpect(jsonPath("$.deliveryDate").value("2026-12-31"))
            .andExpect(jsonPath("$.locale").value("en-US"));
    }

    @Test
    void rejectsInvalidProductCode() throws Exception {
        mvc.perform(get("/api/quote")
                .header("Accept-Language", "en-US")
                .param("code", "bad")
                .param("amount", "1,234.50")
                .param("deliveryDate", "2026-12-31")
                .param("meetingAt", "2026-12-31T09:30:00.000+07:00"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidDate() throws Exception {
        mvc.perform(get("/api/quote")
                .header("Accept-Language", "en-US")
                .param("code", "abc-123")
                .param("amount", "1,234.50")
                .param("deliveryDate", "31/12/2026")
                .param("meetingAt", "2026-12-31T09:30:00.000+07:00"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The three tests check **HTTP status and bound values**; these are functional checks of the sample application, not tests merely inspecting converter method source code. When a test fails, inspect the type conversion cause, MVC configuration, and locale resolver before changing expected strings arbitrarily.

## 11. Where Are Conversion Errors Reported?

| Context | Error example | Typical handling path |
| --- | --- | --- |
| `@RequestParam int quantity` | `quantity=abc` | Spring MVC throws an argument conversion exception, typically returning HTTP 400 |
| `@RequestParam ProductCode code` | `code=bad` | Converter throws `IllegalArgumentException`; argument binding typically returns HTTP 400 |
| `@ModelAttribute FormDto form` | `price=abc` in a numeric field | Binding error can be captured in `BindingResult` if the handler declares it properly |
| `@Valid @ModelAttribute FormDto` | `age=17` with `@Min(18)` | That is a validation error, distinct from type mismatch |
| `@DateTimeFormat(iso=DATE)` | `31/12/2026` | Parse mismatch against format; binding error |
| `@RequestBody JsonDto` | Invalid date in JSON | Jackson/HTTP message converter, does not necessarily use Spring Formatter like form binding |

Form binding example:

~~~java
@PostMapping("/submit")
public String submit(@Valid @ModelAttribute("form") FormDto form,
                     BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "form";
    }
    return "success";
}
~~~

This is a signature sample for an MVC app with views and a `FormDto` class, not an endpoint from the Section 10 project. `BindingResult` must immediately follow the model attribute it handles. `BindingResult#getFieldErrors()` typically contains a `typeMismatch` error when conversion fails. Never use `@Valid` as a substitute for a converter or treat a converter as a replacement for validation: they solve different stages.

## 12. Common Implementation Mistakes

1. **Creating a converter without registering it in the right MVC registry.** Calling `new ProductCodeConverter()` in a service does not make controllers aware of it. Register via `WebMvcConfigurer#addFormatters` (or an appropriate integration mechanism).
2. **Using Converter when Locale is needed.** `Converter<String,Amount>` receives no Locale directly; use `Formatter<Amount>` when user formatting varies by region.
3. **Sharing mutable `SimpleDateFormat`/`DecimalFormat` in a singleton.** Those objects are generally not thread-safe; create one per invocation or use immutable `DateTimeFormatter` for Java Time.
4. **Confusing `MM` with `mm`**, `HH` with `hh`, `yyyy` with `uuuu` in Java Time, or forgetting to escape literals according to pattern syntax.
5. **Treating `LocalDateTime` as a UTC instant.** You need an offset/zone to establish a global instant; if input carries an offset, retain `OffsetDateTime` or convert explicitly to `Instant`.
6. **Forgetting to encode `+` in query parameters.** When sending an offset like `+07:00`, use `--data-urlencode` or `%2B07:00`.
7. **Assuming client Locale always matches server Locale.** Check your locale resolver, `Accept-Language` header, or language selector, and constrain accepted locales.
8. **Sending JSON to a controller while only adding `@DateTimeFormat`.** JSON bodies follow Jackson/message converters; request params/form fields belong to MVC conversion/formatting.
9. **Using locale styles as storage formats.** Default styles can change across JDK/CLDR/locales; use ISO or fixed patterns for API contracts.
10. **Confusing type conversion with validation.** Parsing a `BigDecimal` successfully does not mean the amount is ≥ 0 or valid for the currency.
11. **Letting a formatter silently ignore trailing characters.** When parsing manually, verify the parser consumed the entire input.
12. **Creating a new `ConversionService` and assuming MVC uses that exact instance.** Distinguish an application/service-layer conversion service from the conversion/formatting system wired into the MVC data binder.

## 13. Self-Practice Exercises

**Exercise 1 — Converter:** Create `Converter<String, OrderId>` accepting `ORD-12345`, normalizing to uppercase and rejecting invalid strings. Register via `addFormatters` and test `@RequestParam OrderId orderId`.

**Exercise 2 — Formatter:** Write `Formatter<Area>` wrapping `BigDecimal squareMeters`. Accept `1,234.50` for `en-US` and `1.234,50` for `vi-VN`. Implement `parse` and `print`; reject trailing non-numeric text.

**Exercise 3 — Date:** Create `BookingForm` with `LocalDate startDate` annotated with `@DateTimeFormat(iso=DATE)`. Predict what happens for `2026-02-28`, `2026-02-30`, and `28/02/2026`; do not confuse a non-existent calendar date with a format error.

**Exercise 4 — Timezone:** Explain why `2026-12-31T09:30` does not identify a unique `Instant`. Convert `2026-12-31T09:30+07:00` to UTC (result: `2026-12-31T02:30Z`).

**Exercise 5 — Debugging:** Given `@RequestParam Price price`, a client sends `price=1,234.50`, the app uses locale `vi-VN`, and an error occurs. Inspect the formatter type, locale resolver, input string, converter/formatter registration, and test data; avoid fixing it with ad-hoc character replacement.

**Exercise 6 — Distinguishing Pipelines:** Write a GET endpoint accepting `@RequestParam @DateTimeFormat LocalDate` and a POST endpoint accepting JSON with a `LocalDate` field. Compare where formatting is configured and how parse errors behave in both endpoints.

## 14. Key Takeaways

- `Converter` handles **type-to-type** conversion rules; `Formatter` handles **Locale-aware** parse/print.
- `ConversionService` coordinates conversions; `FormattingConversionService` integrates formatters; `FormatterRegistry` handles registration.
- `WebMvcConfigurer#addFormatters` integrates custom conversion into Spring MVC; `@DateTimeFormat`/`@NumberFormat` apply to fields or method parameters.
- Date/time standards require distinguishing **date**, **local time**, **offset**, **time zone**, and **instant**.
- Combine binding error handling with Bean Validation and define explicit format contracts for clients.

## 15. Spring Framework Documentation

- [Spring Core — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html): Converter, ConverterFactory, GenericConverter, ConversionService, TypeDescriptor.
- [Spring Core — Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html): Formatter, Printer, Parser, AnnotationFormatterFactory, registry.
- [Spring MVC — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html): registering via WebMvcConfigurer, default formatters, ISO config for forms.
- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding and converting controller arguments.
- [Spring API — DateTimeFormat](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html): iso, pattern, style, fallbackPatterns.
