# `Formatter<T>` and `Locale`-Based Input/Output in Spring Framework

## 1. Problem: Same Value, Multiple Representations

A business domain value can be written differently depending on the user's language and geographic region:

| Value | `Locale.US` (`en-US`) | `Locale.GERMANY` (`de-DE`) |
| --- | --- | --- |
| Decimal number 1234.5 | `1,234.50` | `1.234,50` |
| Meaning of separators | Comma for grouping, dot for decimal | Dot for grouping, comma for decimal |

If a single fixed rule is always used, the application can misread data: the string `1.234,50` in a German UI cannot simply be interpreted using US number rules. When outputting data for display, the application also needs to present it in the format users are accustomed to reading.

In Spring, `Formatter<T>` is a **bidirectional** conversion mechanism between a UI string and a program type `T`, while accepting a `Locale`. It is especially suitable for form data, query parameters, and user-facing fields. Lesson objectives:

- Understand the roles of `parse`, `print`, `Locale`, and `FormattingConversionService`.
- Implement a custom `Formatter<T>` and register it so Spring MVC uses it during binding.
- Know the boundary between UI formatting, business validation, and JSON/API data.

`Locale` indicates language/region conventions (such as `en-US`, `de-DE`, `vi-VN`); it **does not by itself determine time zones**, transaction currencies, or all business rules. Two users with the same `Locale` may still use different time zones or currencies.

## 2. The `Formatter<T>` Contract

The core interfaces belong to the `org.springframework.format` package:

```java
public interface Printer<T> {
    String print(T object, java.util.Locale locale);
}

public interface Parser<T> {
    T parse(String text, java.util.Locale locale)
            throws java.text.ParseException;
}

public interface Formatter<T> extends Printer<T>, Parser<T> {
}
```

These are simplified API signatures for learning; in real code, `implements Formatter<T>` from Spring rather than redeclaring the interfaces.

- `parse(String, Locale)`: converts input text into an object of type `T`; for example, `"1.234,50"` with `de-DE` becomes a numeric value `1234.50`.
- `print(T, Locale)`: converts an object into a display string; for example, the same value `1234.50` becomes `"1,234.50"` in `en-US`.
- `T` is the **target type** to convert to/from, such as `LocalDate`, `Price`, `PhoneNumber`. It is not the type of the input string.
- If the input cannot be parsed, `parse` should throw a meaningful `ParseException` or `IllegalArgumentException`. Do not silently turn an invalid string into `0` or a fake default value.

The two operations complement each other, but they do not necessarily satisfy `print(parse(text)) == text` because input formatting can be normalized. A more useful criterion is that the domain value is preserved within the specified precision. For instance, the number `1,234.5` may be printed back as `1,234.50`.

### How is `Formatter` different from `Converter`?

| Mechanism | Typical Responsibility | Direct `Locale` Parameter? |
| --- | --- | --- |
| `Converter<S,T>` | General-purpose type conversion, e.g., identifier → domain object | No |
| `Formatter<T>` | Reading/writing user-facing text, sensitive to regional representation | Yes, on both `parse` and `print` |
| `PropertyEditor` | Legacy JavaBeans binding mechanism | Not the preferred choice for new designs with multiple `Locale`s |

`Formatter` can also be used alongside other converters: Spring unifies them inside a `ConversionService` system. A purely technical conversion that does not depend on how users write or read strings is usually better suited to `Converter`.

## 3. Processing Flow in Spring MVC

Typical input flow:

```text
HTTP request (text) + request Locale
          |
          v
@RequestParam / @ModelAttribute + WebDataBinder
          |
          v
FormattingConversionService
          |
          v
Formatter<Price>.parse(text, locale)
          |
          v
Price object in controller or form model
```

The presentation flow uses the reverse direction: when a view/binding component needs a **display string**, `FormattingConversionService` can call `Formatter<Price>.print(price, locale)`.

`WebDataBinder` handles binding and type conversion; when a value is invalid, Spring can record conversion errors into `BindingResult` for a form model. For a required `@RequestParam`, a type conversion error typically leads to a parameter-handling/bad-request error. User-friendly messages should be built in the controller/view layer and error-handling mechanism, rather than cramming all UI logic into the formatter.

`Locale` is resolved from the request context according to Spring MVC's locale resolution configuration (for example, based on the `Accept-Language` header). Where there is no HTTP request, Spring can obtain the `Locale` from `LocaleContextHolder`. Avoid assuming that the server's `Locale.getDefault()` is every user's locale.

An important limitation: `@RequestBody` reading JSON typically goes through `HttpMessageConverter` and Jackson. A `Formatter<T>` registered with MVC **does not automatically change how Jackson reads/writes JSON fields**. Machine-to-machine APIs should use stable conventions, such as JSON numbers and ISO 8601 dates.

## 4. Runnable Java 17 Example: Formatting `Price`

We create a `Price` type wrapping a `BigDecimal`, solely to demonstrate **a numeric value with two decimal places when displayed**; the example does not represent currency units yet. Using `BigDecimal` avoids binary floating-point rounding errors of `double` for data requiring decimal precision.

Create a small Gradle project with the two files below. This is a standalone example using Spring Framework 6.2.8; in a real Spring Boot application, let the BOM/Boot manage dependency versions instead of pinning the Spring Framework version manually.

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'FormatterDemo'
}
```

**`src/main/java/FormatterDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.Objects;

import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.context.i18n.LocaleContextHolder;

public class FormatterDemo {

    public record Price(BigDecimal amount) {
        public Price {
            Objects.requireNonNull(amount, "amount");
        }
    }

    public static final class PriceFormatter implements Formatter<Price> {

        private DecimalFormat numberFormat(Locale locale) {
            NumberFormat base = NumberFormat.getNumberInstance(locale);
            if (!(base instanceof DecimalFormat format)) {
                throw new IllegalStateException(
                        "JDK does not provide DecimalFormat for " + locale);
            }
            format.setParseBigDecimal(true);
            format.setMinimumFractionDigits(2);
            format.setMaximumFractionDigits(2);
            format.setRoundingMode(RoundingMode.HALF_UP);
            return format;
        }

        @Override
        public Price parse(String text, Locale locale) throws ParseException {
            if (text == null || text.isBlank()) {
                throw new ParseException("Value must not be blank", 0);
            }
            DecimalFormat format = numberFormat(locale);
            ParsePosition position = new ParsePosition(0);
            Number parsed = format.parse(text, position);

            // Disallow unparsed trailing characters.
            if (!(parsed instanceof BigDecimal amount)
                    || position.getIndex() != text.length()) {
                int index = position.getErrorIndex() >= 0
                        ? position.getErrorIndex() : position.getIndex();
                throw new ParseException("Invalid number format: " + text, index);
            }
            return new Price(amount);
        }

        @Override
        public String print(Price value, Locale locale) {
            return numberFormat(locale).format(value.amount());
        }
    }

    public static void main(String[] args) {
        var service = new DefaultFormattingConversionService();
        service.addFormatter(new PriceFormatter());

        try {
            LocaleContextHolder.setLocale(Locale.US);
            Price us = service.convert("1,234.50", Price.class);
            System.out.println(us.amount().toPlainString());
            System.out.println(service.convert(us, String.class));

            LocaleContextHolder.setLocale(Locale.GERMANY);
            System.out.println(service.convert(us, String.class));
            Price de = service.convert("1.234,50", Price.class);
            System.out.println(de.amount().toPlainString());
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

Run with `gradle run --quiet` (or `./gradlew run --quiet` if the project has a Gradle Wrapper). With JDK 17 using the standard number rules of the two locales above, **stdout**:

```text
1234.50
1,234.50
1.234,50
1234.50
```

Step-by-step explanation:

1. `service.addFormatter(...)` registers both `String → Price` and `Price → String` directions with the conversion service.
2. `LocaleContextHolder.setLocale(Locale.US)` sets the locale for the current conversion in this non-HTTP-request example; the parser interprets comma as grouping and dot as decimal.
3. Switching to `Locale.GERMANY` while keeping the **same `Price` object**: `print` outputs `1.234,50`.
4. Passing the German string into the parser produces the same `BigDecimal("1234.50")`.
5. `finally` clears the current thread's locale to avoid affecting subsequent operations.

In production code, separate `Price` and `PriceFormatter` into classes in appropriate domain packages. The example uses nested classes only so the entire mechanism can be run and observed in a single Java file.

### Why not keep a single shared `DecimalFormat`?

`DecimalFormat` is **stateful and not thread-safe**. A `Formatter` bean may be shared across multiple requests and locales. The example creates a new `DecimalFormat` on each `parse`/`print` call, so no mutable formatting variable is shared across threads. Do not cache formatters in a way that ignores locale.

The example also checks `ParsePosition` to reject strings with unparsed trailing characters such as `1,234.50abc`. However, `NumberFormat` can be lenient with certain digit grouping patterns. Checking that the entire string was consumed **is not the same** as checking all business rules. If the domain allows at most two decimal places or imposes value bounds, verify those separately with appropriate validation/domain rules. The rounding rule during `print` also needs an explicit decision; it does not automatically alter the number stored in the object.

## 5. Integrating with Spring MVC

In a Spring MVC/Spring Boot project with the Web MVC dependency, implement `WebMvcConfigurer` to register the formatter:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class PriceWebConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new PriceFormatter());
    }
}
```

This integration snippet **assumes** `PriceFormatter` from section 4 has been extracted into its own class in an appropriate package with matching imports. This is an integration illustration, not a standalone runnable file. `addFormatters` registers the formatter in the conversion service used for binding in Spring MVC; there is no need to call `parse` manually in every controller.

Example controller (assuming a standalone `Price` type exists):

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PriceController {
    @GetMapping("/price")
    public String readPrice(@RequestParam Price price) {
        return price.amount().toPlainString();
    }
}
```

Sample request:

```bash
curl -G 'http://localhost:8080/price' \
  -H 'Accept-Language: de-DE' \
  --data-urlencode 'price=1.234,50'
```

If the application resolves the request locale from `Accept-Language` and has registered the formatter as above, the response body is:

```text
1234.50
```

This response returns a technical string to verify the **input direction**. It does not prove that `Formatter.print` is automatically invoked when returning `@ResponseBody`. To print numbers according to locale in the UI, use a rendering/form-binding mechanism that supports formatting or call an explicit formatting service. To return structured JSON/API data, design appropriate DTOs and serialization.

For forms using `@ModelAttribute`, the formatter can also be used to convert text field values into `Price`; binding errors can be handled via `BindingResult`. Do not turn a formatter into a place to query the database, check permissions, or decide whether data satisfies every business rule.

## 6. Annotation-Based Formatters and Built-in Formatters

Spring already includes many formatters for numbers and dates, so **you do not always need to write a custom `Formatter<T>`**.

```java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class OrderForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate orderDate;

    // getters/setters for form binding
}
```

This is a **field-definition snippet**, not a standalone application: appropriate getters/setters or a binding mechanism are needed. When using `@NumberFormat`, number separator symbols are affected by locale, even though the pattern describes the formatting shape. `@DateTimeFormat(iso = ISO.DATE)` intentionally uses the ISO format (`yyyy-MM-dd`) for dates and reduces ambiguity such as `03/04/2026`.

How to choose:

- For numbers, percentages, currencies, and simple dates: check `@NumberFormat`, `@DateTimeFormat`, and built-in formatters first.
- For **custom domain types** with clear input/output syntax (like `Price`): write a custom `Formatter<Price>` and register it by field type.
- When formatting depends on a custom annotation attached to individual fields: consider `AnnotationFormatterFactory`.
- When registering a group of related formatters/converters: consider `FormatterRegistrar`.
- For standard machine-to-machine data exchange: prefer stable API formats; apply localization at the UI boundary.

Note that HTML `input type="date"` and `input type="time"` fields submit data in the HTML standard format, even though what the browser displays may differ by language. Do not force a locale-based display date formatter onto data that the browser submits in ISO format. Similarly, parsing date/time values also requires distinguishing between `LocalDate`, an instant (`Instant`), and a time zone (`ZoneId`).

## 7. Testing and Common Pitfalls

A minimal test matrix for the example formatter:

| Scenario | Expectation |
| --- | --- |
| `parse("1,234.50", Locale.US)` | `Price.amount = 1234.50` |
| `parse("1.234,50", Locale.GERMANY)` | `Price.amount = 1234.50` |
| `print(Price(1234.50), Locale.US)` | `"1,234.50"` |
| `print(Price(1234.50), Locale.GERMANY)` | `"1.234,50"` |
| `parse("1,234.50abc", Locale.US)` | Reports parse error; does not silently drop `abc` |
| `parse("", Locale.US)` | Reports parse error |
| Concurrent requests in different locales | Do not pollute each other's formatting |

When testing `FormattingConversionService` outside the web layer, set and restore `LocaleContextHolder` for each case, just like the `try/finally` in the example. With MVC, test HTTP parameters and `Accept-Language` together with the actual locale resolver configuration.

Pitfalls to avoid:

1. **Using `Double.parseDouble` for all users.** This only understands a fixed decimal point and does not handle locale conventions. For monetary amounts, use `BigDecimal` according to domain rules.
2. **Using `Locale.getDefault()` inside a formatter** when the request already has its own locale. Use the `locale` parameter passed by Spring.
3. **Sharing mutable `SimpleDateFormat`/`DecimalFormat`** in a singleton bean. Create a new instance each time, or use immutable/thread-safe formatters when appropriate.
4. **Confusing formatting with validation.** `Formatter.parse` is only responsible for reading a string into the target type; sign constraints, value ranges, digit counts, authorization, etc., must be checked via domain validation/Bean Validation or additional rules.
5. **Changing formatting rules by locale in public JSON payloads.** API consumers may not know the locale and may fail to parse strings. Use stable data types and representation standards.
6. **Ignoring JDK/CLDR variations.** Style-based formats can change across JDK versions or locale data. For protocols, exchange files, or stored data, use ISO or a controlled, explicitly tested pattern.

### Self-Check Questions

- If the same `Price(1234.50)` is displayed to US and German users, does the **in-memory value** need to change? No: only the string produced by `print` changes by locale.
- If the server receives `"1.234,50"` but the parser runs with `Locale.US`, where is the bug? Check the request locale resolution mechanism, registered formatters, and input conventions; do not fix it by arbitrarily altering strings.
- If a controller receives JSON `{ "amount": 1234.50 }`, does an MVC `Formatter<Price>` automatically control the JSON serializer? No: that is a separate message conversion/Jackson pipeline.
- When is `Converter` more suitable? When converting types without locale-dependent presentation rules, such as converting enum codes or internal identifiers.

## 8. References

- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, `Printer`, `Parser`, registration, and annotations.
- [Spring Framework — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): configuring formatters in Spring MVC and notes on HTML date/time fields.
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html): overall context of binding and type conversion.

Key takeaway for application: `Formatter<T>` preserves the meaning of the domain object while interpreting or presenting text according to `Locale`; it operates via `ConversionService` in appropriate binding contexts.