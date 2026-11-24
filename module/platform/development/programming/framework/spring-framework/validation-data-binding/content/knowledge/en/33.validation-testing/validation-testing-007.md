# Testing Locale-Aware Parsing and Printing in Spring Framework

## 1. Objective: same data, multiple representations

In multilingual applications, the Java value stays **unchanged**, while input and display strings vary by `Locale`. Take the same monetary amount `1234.50`:

| Locale | Common string | Meaning |
| --- | --- | --- |
| `en-US` | `1,234.50` | Comma thousands separator, dot decimal separator |
| `de-DE` | `1.234,50` | Dot thousands separator, comma decimal separator |
| `fr-FR` | May use non-breaking/narrow no-break space for grouping | Do not assume an ASCII space |
| `vi-VN` | Grouping and decimal separators per JDK locale data | Test against the real locale, do not guess from UI |

If `@ModelAttribute` receives `1.234,50` from a German user while the parser runs with `Locale.US`, it may fail **or misinterpret the value** depending on the parser and leniency. A test running only under `Locale.getDefault()` on a developer machine will miss this difference.

For dates, `15 Sep 2026` and a string using a German/French/Vietnamese month name can all represent `LocalDate.of(2026,9,15)`. Yet you should not assert that a localized date string is invariant across all JDKs, CLDR providers, and locale-data versions.

**Lesson goal:** test both directions of Spring `Formatter<T>`:
- `parse(String text, Locale locale)`: user string → Java value.
- `print(T value, Locale locale)`: Java value → display string.
- `parse(print(value, locale), locale)`: *round-trip* must preserve semantics.
- `print(parse(text, locale), locale)`: verify text normalized per defined rules.
- Test across multiple explicit locales, including invalid inputs, wrong separators, missing data, and JDK locale-data differences.

Examples use **Java 17, Spring Boot 3.5.7, Spring Framework 6.2**, two custom formatters, and JUnit 5/MockMvc. Direct formatter calls, `FormattingConversionService`, `WebDataBinder`, and HTTP `@ModelAttribute` are all tested. Test outcomes are described as **expected**, not disguised as execution logs.

## 2. Concept: Locale differs from message language

### 2.1. `Locale` is formatting input data

`java.util.Locale` carries language, region, and optionally script/variants/extensions:

~~~java
Locale us = Locale.US;
Locale de = Locale.GERMANY;
Locale fr = Locale.FRANCE;
Locale vi = Locale.forLanguageTag("vi-VN");

System.out.println(us.toLanguageTag()); // en-US
System.out.println(de.toLanguageTag()); // de-DE
System.out.println(fr.toLanguageTag()); // fr-FR
System.out.println(vi.toLanguageTag()); // vi-VN
~~~

This is an **illustrative snippet inside a method**, not a full Java class. Tags are chosen explicitly; never pass `Locale.getDefault()` as a test parameter because JVM/CI may run in another region.

Locale affects grouping separators, decimal separators, digits, month names, day/month/year order, and formatting rules. However, it **does not carry a time zone**. `Locale` and `ZoneId` are distinct pieces of information: for `Instant`/`ZonedDateTime`, you must also test zones and DST if business rules require them.

### 2.2. Spring `Formatter<T>`

Spring `Formatter<T>` combines `Printer<T>` and `Parser<T>`:

~~~java
public interface Printer<T> {
    String print(T object, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale)
            throws java.text.ParseException;
}

public interface Formatter<T>
        extends Printer<T>, Parser<T> {
}
~~~

These are **abbreviated API signatures for study**; do not create files redeclaring Spring's interfaces. `Formatter<T>` is more suitable than `Converter<S,T>` when both directions and locale are needed. A `Converter<String, BigDecimal>` normally has no locale parameter in its signature.

A `Formatter` should be **thread-safe** because it can be registered once in a shared `ConversionService`. If using `DecimalFormat` or `SimpleDateFormat`, which are mutable, create a new instance per `parse`/`print` call or manage lifecycle safely. Never store a `DecimalFormat` in a field and call it concurrently across requests.

### 2.3. `FormattingConversionService`

`FormattingConversionService` is a `ConversionService` that also implements `FormatterRegistry`. Calling `addFormatter(new CustomFormatter())` registers both `String → T` and `T → String` conversions. When invoked via adapters, Spring obtains the locale from the appropriate `LocaleContextHolder`.

Useful classes:

| API | Role in tests |
| --- | --- |
| `Formatter<T>.parse` | Test parser directly with an explicit locale |
| `Formatter<T>.print` | Test printer directly with an explicit locale |
| `FormattingConversionService#addFormatter` | Test formatter registration |
| `ConversionService#convert` | Test real adapter, both `String→T` and `T→String` |
| `LocaleContextHolder` | Temporarily set locale for the adapter in synchronous tests |
| `WebDataBinder#setConversionService` | Test property binding with registered formatters |
| `WebMvcConfigurer#addFormatters` | Register formatters into MVC |
| `WebFluxConfigurer#addFormatters` | Register formatters into WebFlux |
| `MockMvc` | Test HTTP request locale handling in Spring MVC |
| `WebTestClient` | Test HTTP in WebFlux or MVC depending on setup |

**Note:** `@DateTimeFormat`, `@NumberFormat`, and Spring's built-in formatters already cover many cases. This lesson writes custom formatters to make pass/fail conditions explicit; in production code, prefer built-in APIs when they meet requirements.

## 3. Defining exact invariants to prove

### 3.1. Value-type round-trip

For every supported `Locale` and valid value `x`:

~~~text
parse(print(x, locale), locale) ≈ x
~~~

The symbol `≈` means **semantic equivalence**, not always `Object.equals`:
- For `LocalDate` and a record wrapping it, equality is exact.
- For `BigDecimal`, `equals` also compares scale, so `1.0` does not equal `1.00`; use `compareTo(...) == 0` when the contract only cares about numeric value.
- For amounts requiring exact scale/currency, the contract may be stricter and require scale equality too.
- For date/times with time zones, epoch, offset, and instant are distinct concepts.

Do not assume a formatter that rounds or drops decimal places preserves data. If a formatter prints only 2 decimal digits, `1.234` cannot round-trip to itself. Decide explicitly: **reject** over-precise input or accept rounding as a documented business rule.

### 3.2. Text round-trip can mean canonicalization

~~~text
print(parse(text, locale), locale) == canonical(text, locale)
~~~

It does not have to equal the raw input. A lenient parser may accept `"1234.5"` while the printer outputs `"1,234.50"`. If a system requires input to already match one canonical form, the parser must re-check **the printed string** and reject unwanted variants.

This lesson chooses a **strict** contract for amounts: locale grouping and always two decimal digits, rejecting trailing garbage or non-canonical forms. That is an example rule to keep tests transparent, not a mandatory format for every website.

### 3.3. Invalid parses must fail, never guess

Suppose the Java object requires `LocalizedAmount(1234.50)`:

~~~text
en-US valid: 1,234.50
de-DE valid: 1.234,50

en-US input: 1.234,50
=> reject, do not silently interpret as 1.23450 or 123450.
~~~

In production, some forms allow omitting grouping or trailing zeros. In that case, **define the accepted input set explicitly** rather than letting `NumberFormat` defaults decide unpredictably. Test cases should verify both accepted and rejected inputs.

### 3.4. Minimum locale matrix

| Data type | `en-US` | `de-DE` | `fr-FR` | `vi-VN` |
| --- | --- | --- | --- | --- |
| Decimal amount | Parse + print + round-trip | Parse + print + round-trip | Parse + print + round-trip | Parse + print + round-trip |
| Localized day | Parse + print + round-trip | Parse + print + round-trip | Parse + print + round-trip | Parse + print + round-trip |
| Wrong format | Test wrong separator | Test wrong separator | Test whitespace/different grouping | Test locale data |
| Spring ConversionService | Test explicit locale context | Test explicit locale context | Test if product supports it | Test if product supports it |
| HTTP binding | Send corresponding locale | Send corresponding locale | Send corresponding locale | Send corresponding locale |

Do not overlook `fr-FR`: the thousands separator can be **U+202F NARROW NO-BREAK SPACE** or another variant depending on locale data. Tests should not hardcode an ASCII space `" "` assuming it is always valid. For `vi-VN`, likewise do not hardcode a locale string "from memory" as the expected value across all JDKs without locking the environment.

## 4. Formatter for two-decimal monetary amounts

### 4.1. Domain type: `LocalizedAmount`

~~~java
package com.example.localeformat;

import java.math.BigDecimal;
import java.util.Objects;

public record LocalizedAmount(BigDecimal value) {
    public LocalizedAmount {
        Objects.requireNonNull(value, "value");
    }
}
~~~

This is a standalone Java 17 record. It represents the value and **stores no locale formatting**. `BigDecimal` is better than `double` when exact decimal digits matter. The demo does not model currency, tax, or business rounding; `LocalizedAmount` is strictly a value object for learning formatting.

### 4.2. Designing parser/printer with explicit rules

~~~java
package com.example.localeformat;

import org.springframework.format.Formatter;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public final class LocalizedAmountFormatter
        implements Formatter<LocalizedAmount> {

    private static final String PATTERN = "#,##0.00";

    private DecimalFormat newFormat(Locale locale) {
        DecimalFormat format = new DecimalFormat(
                PATTERN, DecimalFormatSymbols.getInstance(locale));
        format.setParseBigDecimal(true);
        return format;
    }

    @Override
    public String print(LocalizedAmount amount, Locale locale) {
        if (amount.value().scale() > 2) {
            throw new IllegalArgumentException(
                    "Amount has more than 2 fraction digits");
        }
        return newFormat(locale).format(amount.value());
    }

    @Override
    public LocalizedAmount parse(String text, Locale locale)
            throws ParseException {

        DecimalFormat format = newFormat(locale);
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(text, position);

        if (!(parsed instanceof BigDecimal decimal)
                || position.getIndex() != text.length()
                || decimal.scale() > 2
                || !format.format(decimal).equals(text)) {
            throw new ParseException(
                    "Amount must have canonical locale format", 0);
        }

        return new LocalizedAmount(decimal);
    }
}
~~~

This is a **complete compilable class** alongside `LocalizedAmount` and the `spring-context` dependency (pulled in by starter-web in the project).

Design rationale:
- `new DecimalFormat(PATTERN, DecimalFormatSymbols.getInstance(locale))` selects locale-appropriate separators.
- `PATTERN="#,##0.00"` enforces grouping and **exactly two decimal digits** on output.
- `setParseBigDecimal(true)` makes the parser return `BigDecimal` instead of binary floating-point.
- `ParsePosition` checks that the parser consumed the **entire** input. Java number parsers can accept a valid prefix and ignore trailing text if unchecked.
- `format.format(decimal).equals(text)` enforces canonical format: if input differs from the defined display form, parsing rejects it.
- `scale()>2` prevents silent rounding when printing/parsing values with more than two fractional digits.
- Each invocation creates a fresh `DecimalFormat`, because `DecimalFormat` is **not thread-safe**.
- Never call JVM-wide `Locale.setDefault` or `DecimalFormatSymbols.set...` inside a parser.

With `Locale.US`:

~~~text
print(LocalizedAmount(1234.50), en-US) -> "1,234.50"
parse("1,234.50", en-US) -> LocalizedAmount(BigDecimal("1234.50"))
~~~

With `Locale.GERMANY`:

~~~text
print(LocalizedAmount(1234.50), de-DE) -> "1.234,50"
parse("1.234,50", de-DE) -> LocalizedAmount(BigDecimal("1234.50"))
~~~

These two examples use common separators in Java 17's JDK. For French and Vietnamese, tests take the output from the running `DecimalFormatSymbols`/formatter and verify round-trip rather than hardcoding thousands-grouping glyphs across every CLDR version.

**Intentional limitations:** the example formatter does not handle currency codes, negative zero, arbitrary whitespace, more than two decimals, or oversized quantitative values. For real financial products, consider JSR-354/Moneta, currency codes/scales, rounding policies, negative-number policies, and international input formats.

### 4.3. Wrong locale and non-canonical input

Test table:

| Locale used to parse | Input | Expected |
| --- | --- | --- |
| `en-US` | `1,234.50` | Valid |
| `de-DE` | `1.234,50` | Valid |
| `en-US` | `1.234,50` | `ParseException` |
| `de-DE` | `1,234.50` | `ParseException` |
| `en-US` | `1,234.50xyz` | `ParseException` |
| `en-US` | `1234.50` | `ParseException` (non-canonical) |
| `en-US` | `1,234.567` | `ParseException` (more than two decimals) |
| `en-US` | Empty string | Parse fails; with Spring binder, test null/empty handling separately |

Requiring grouping in this example is a policy choice, not a universal rule of every Locale. Form UX might accept `1234.50` and normalize it to `1,234.50`; in that case remove the exact canonical check and write matching tests.

## 5. Formatter for dates with localized month names

To test date localization without time-zone dependencies, use `LocalDate`. Record:

~~~java
package com.example.localeformat;

import java.time.LocalDate;
import java.util.Objects;

public record ScheduleDay(LocalDate value) {
    public ScheduleDay {
        Objects.requireNonNull(value, "value");
    }
}
~~~

Formatter:

~~~java
package com.example.localeformat;

import org.springframework.format.Formatter;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public final class ScheduleDayFormatter
        implements Formatter<ScheduleDay> {

    private DateTimeFormatter newFormat(Locale locale) {
        return DateTimeFormatter.ofPattern(
                        "dd MMM uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public String print(ScheduleDay day, Locale locale) {
        return day.value().format(newFormat(locale));
    }

    @Override
    public ScheduleDay parse(String text, Locale locale)
            throws ParseException {
        try {
            return new ScheduleDay(
                    LocalDate.parse(text, newFormat(locale)));
        } catch (DateTimeParseException badDate) {
            throw new ParseException(
                    "Invalid day for selected locale", 0);
        }
    }
}
~~~

- `dd`: two-digit day.
- `MMM`: **locale-dependent** abbreviated month name, highlighting language differences.
- `uuuu`: proleptic year, suitable for strict date parsing when the pattern omits era.
- `ResolverStyle.STRICT`: rejects impossible dates such as Feb 31 instead of adjusting them automatically.
- `DateTimeFormatter` is immutable and thread-safe; created per locale here to keep the contract explicit. If caching, design a safe cache and check memory footprint.
- Throws `ParseException` on invalid input to match `Formatter.parse` conventions and Spring binding errors.

Do not hardcode expected `fr-FR` and `vi-VN` date strings across all builds. Month abbreviations, periods, and spacing can vary across JDK/CLDR versions. The reliable test is generating output with the locale's active formatter and parsing it back to **the same date**, while testing exact formats/differences separately when a fixed product contract requires them.

If an API requires a **locale-invariant date format**, prefer ISO `2026-09-15` with `DateTimeFormatter.ISO_LOCAL_DATE` instead of localized month names. Separating display formatting from wire-protocol types is an important API decision.

## 6. Spring integration: ConversionService, DataBinder, and MVC

### 6.1. Difference between direct formatter and adapter

When calling directly:

~~~java
LocalizedAmountFormatter formatter =
        new LocalizedAmountFormatter();

String german = formatter.print(
        new LocalizedAmount(
                new BigDecimal("1234.50")),
        Locale.GERMANY);
~~~

you pass `Locale.GERMANY` explicitly. Yet `ConversionService#convert` does not take a locale parameter:

~~~java
<T> T convert(Object source, Class<T> targetType);
~~~

Spring's adapter reads the locale from `LocaleContextHolder` when applying a formatter. Therefore tests must configure the locale context properly instead of relying on the JVM default.

### 6.2. Global MVC registration

~~~java
package com.example.localeformat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebFormattingConfig implements WebMvcConfigurer {

    @Bean
    public LocalizedAmountFormatter amountFormatter() {
        return new LocalizedAmountFormatter();
    }

    @Bean
    public ScheduleDayFormatter dayFormatter() {
        return new ScheduleDayFormatter();
    }

    private final LocalizedAmountFormatter amounts;
    private final ScheduleDayFormatter days;

    public WebFormattingConfig(
            LocalizedAmountFormatter amounts,
            ScheduleDayFormatter days) {
        this.amounts = amounts;
        this.days = days;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(amounts);
        registry.addFormatter(days);
    }
}
~~~

**Note on wiring:** the configuration above illustrates **a reasonable idea**, but contains a subtle dependency cycle: this `@Configuration` class itself has a constructor requiring the `amountFormatter`/`dayFormatter` beans declared as non-static `@Bean` methods within the same class. When creating the configuration instance, Spring needs constructor dependencies before invoking bean methods, which can cause a circular dependency. **To ensure a reliably runnable project, section 7 uses the safe approach: declaring each formatter as an independent `@Component`, and constructor-injecting them into the config without declaring `@Bean` methods in the same class.** Do not copy the config above into section 7's project.

The `addFormatters` principle still holds: Spring MVC uses a configured `FormattingConversionService` for binding. In WebFlux, the counterpart is `WebFluxConfigurer#addFormatters(FormatterRegistry)`, while HTTP integration and exception handling must use the reactive stack.

### 6.3. `@InitBinder` and formatter scope

If a specific form needs local rules, `WebDataBinder` can register formatters per field:

~~~java
@InitBinder("bookingForm")
void initBooking(WebDataBinder binder) {
    binder.setAllowedFields("amount", "day");
}
~~~

No local formatter is needed here because formatters for `LocalizedAmount` and `ScheduleDay` are already registered in the MVC ConversionService. Do not mix overlapping formatters for the same type/path without testing precedence; a single clear conversion policy is easier to maintain.

If using `binder.addCustomFormatter(formatter, "fieldName")` for a single field, verify Spring versions and scope. Do not expect `@InitBinder` to make Jackson JSON `@RequestBody` pass through form formatters.

### 6.4. `@NumberFormat`, `@DateTimeFormat`, and annotation formatting

Spring provides:

~~~java
@NumberFormat(pattern = "#,##0.00")
private BigDecimal amount;

@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate day;
~~~

These are **illustrative fields** inside a DTO, requiring imports for `org.springframework.format.annotation.NumberFormat` and `DateTimeFormat`. `@NumberFormat` accepts `style` or `pattern`; `@DateTimeFormat` accepts `iso` and `pattern`. Using ISO DATE selects `yyyy-MM-dd` for stable interchange rather than localized month names.

However, do not assume these annotations make Jackson deserialize JSON the same way. Jackson/`HttpMessageConverter` has its own settings like `@JsonFormat`/modules, so test `@RequestBody` independently.

## 7. Runnable project: structure and dependencies

The project uses **Spring MVC** and `spring-boot-starter-web` to demonstrate form binding; do not add the WebFlux starter to the same example.

~~~text
pom.xml
src/main/java/com/example/localeformat/
  LocaleFormatApplication.java
  LocalizedAmount.java
  ScheduleDay.java
  LocalizedAmountFormatter.java
  ScheduleDayFormatter.java
  WebFormattingConfig.java
  BookingForm.java
  BookingController.java
src/test/java/com/example/localeformat/
  LocalizedFormatterTest.java
  ConversionServiceLocaleTest.java
  BookingControllerLocaleTest.java
~~~

### 7.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>locale-format-test-demo</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-test` provides JUnit Jupiter, parameterized tests, and MockMvc. `spring-boot-starter-validation` enables Jakarta `@NotNull` in the form DTO. The demo has no database.

### 7.2. Main application

~~~java
// src/main/java/com/example/localeformat/LocaleFormatApplication.java
package com.example.localeformat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LocaleFormatApplication {
    public static void main(String[] args) {
        SpringApplication.run(LocaleFormatApplication.class, args);
    }
}
~~~

### 7.3. `LocalizedAmount.java`

~~~java
// src/main/java/com/example/localeformat/LocalizedAmount.java
package com.example.localeformat;

import java.math.BigDecimal;
import java.util.Objects;

public record LocalizedAmount(BigDecimal value) {
    public LocalizedAmount {
        Objects.requireNonNull(value, "value");
    }
}
~~~

### 7.4. `ScheduleDay.java`

~~~java
// src/main/java/com/example/localeformat/ScheduleDay.java
package com.example.localeformat;

import java.time.LocalDate;
import java.util.Objects;

public record ScheduleDay(LocalDate value) {
    public ScheduleDay {
        Objects.requireNonNull(value, "value");
    }
}
~~~

### 7.5. `LocalizedAmountFormatter.java`

~~~java
// src/main/java/com/example/localeformat/LocalizedAmountFormatter.java
package com.example.localeformat;

import org.springframework.format.Formatter;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

@Component
public final class LocalizedAmountFormatter
        implements Formatter<LocalizedAmount> {

    private DecimalFormat newFormat(Locale locale) {
        DecimalFormat result = new DecimalFormat(
                "#,##0.00", DecimalFormatSymbols.getInstance(locale));
        result.setParseBigDecimal(true);
        return result;
    }

    @Override
    public String print(LocalizedAmount amount, Locale locale) {
        if (amount.value().scale() > 2) {
            throw new IllegalArgumentException(
                    "More than 2 decimal places");
        }
        return newFormat(locale).format(amount.value());
    }

    @Override
    public LocalizedAmount parse(String text, Locale locale)
            throws ParseException {
        DecimalFormat format = newFormat(locale);
        ParsePosition position = new ParsePosition(0);
        Number value = format.parse(text, position);

        if (!(value instanceof BigDecimal amount)
                || position.getIndex() != text.length()
                || amount.scale() > 2
                || !format.format(amount).equals(text)) {
            throw new ParseException(
                    "Non-canonical localized amount", 0);
        }

        return new LocalizedAmount(amount);
    }
}
~~~

### 7.6. `ScheduleDayFormatter.java`

~~~java
// src/main/java/com/example/localeformat/ScheduleDayFormatter.java
package com.example.localeformat;

import org.springframework.format.Formatter;
import org.springframework.stereotype.Component;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

@Component
public final class ScheduleDayFormatter
        implements Formatter<ScheduleDay> {

    private DateTimeFormatter newFormat(Locale locale) {
        return DateTimeFormatter.ofPattern(
                        "dd MMM uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public String print(ScheduleDay day, Locale locale) {
        return day.value().format(newFormat(locale));
    }

    @Override
    public ScheduleDay parse(String text, Locale locale)
            throws ParseException {
        try {
            return new ScheduleDay(
                    LocalDate.parse(text, newFormat(locale)));
        } catch (DateTimeParseException ex) {
            throw new ParseException(
                    "Invalid localized day", 0);
        }
    }
}
~~~

### 7.7. `WebFormattingConfig.java` — proper lifecycle configuration

~~~java
// src/main/java/com/example/localeformat/WebFormattingConfig.java
package com.example.localeformat;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfig implements WebMvcConfigurer {

    private final LocalizedAmountFormatter amounts;
    private final ScheduleDayFormatter days;

    public WebFormattingConfig(
            LocalizedAmountFormatter amounts,
            ScheduleDayFormatter days) {
        this.amounts = amounts;
        this.days = days;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(amounts);
        registry.addFormatter(days);
    }
}
~~~

Both formatters are `@Component` beans in separate classes, so `WebFormattingConfig`'s constructor injects those singletons without creating a `@Bean` cycle. **This is the actual configuration used in the runnable project**. Spring MVC registers the formatters in the binding ConversionService. They are thread-safe because each parse/print creates its own formatter/parser state instead of sharing a mutable `DecimalFormat`.

### 7.8. `BookingForm.java`

~~~java
// src/main/java/com/example/localeformat/BookingForm.java
package com.example.localeformat;

import jakarta.validation.constraints.NotNull;

public class BookingForm {

    @NotNull
    private LocalizedAmount amount;

    @NotNull
    private ScheduleDay day;

    public BookingForm() {}

    public LocalizedAmount getAmount() {
        return amount;
    }

    public void setAmount(LocalizedAmount amount) {
        this.amount = amount;
    }

    public ScheduleDay getDay() {
        return day;
    }

    public void setDay(ScheduleDay day) {
        this.day = day;
    }
}
~~~

`@NotNull` ensures both fields have values **after conversion** when validation actually runs. It does not replace checking malformed numbers or malformed dates; those errors arise during binding before validation. The DTO exposes only two public fields, avoiding direct binding onto domain/JPA entities.

### 7.9. `BookingController.java`

~~~java
// src/main/java/com/example/localeformat/BookingController.java
package com.example.localeformat;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Locale;
import java.util.Map;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {

    private final LocalizedAmountFormatter amounts;
    private final ScheduleDayFormatter days;

    public BookingController(
            LocalizedAmountFormatter amounts,
            ScheduleDayFormatter days) {
        this.amounts = amounts;
        this.days = days;
    }

    @InitBinder("bookingForm")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields("amount", "day");
    }

    @PostMapping(path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> create(
            @Valid @ModelAttribute("bookingForm") BookingForm form,
            BindingResult errors,
            Locale locale) {

        if (errors.hasErrors()) {
            List<String> fields = errors.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest()
                    .body(Map.of("invalidFields", fields));
        }

        return ResponseEntity.ok(Map.of(
                "amount", form.getAmount().value().toPlainString(),
                "date", form.getDay().value().toString(),
                "amountText", amounts.print(form.getAmount(), locale),
                "dateText", days.print(form.getDay(), locale)
        ));
    }
}
~~~

The controller demonstrates **both synchronous directions in Spring MVC**:
1. Spring resolves the locale from the request resolver and converts form strings into `LocalizedAmount`/`ScheduleDay` using the registered formatters.
2. The controller calls `print` with the request `Locale` to return normalized strings.
3. On conversion or `@NotNull` errors, `BindingResult` sits right after `@ModelAttribute`, allowing it to return HTTP 400 with field names.
4. `allowedFields` permits only `amount`/`day` in property binding. Extra fields outside the contract may be suppressed; the demo focuses on parse/print testing and does not add a dedicated handler for `getSuppressedFields()`.

**Do not look at `amountText` in the JSON response and assume Jackson automatically called the Formatter.** Here the controller calls `amounts.print(...)` explicitly. For `@RequestBody` JSON, Jackson deserialization is a separate pipeline from `@ModelAttribute`'s `WebDataBinder`.

## 8. Unit tests: parse, print, and round-trip across four Locales

### 8.1. `LocalizedFormatterTest.java`

~~~java
// src/test/java/com/example/localeformat/LocalizedFormatterTest.java
package com.example.localeformat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

import java.math.BigDecimal;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.time.LocalDate;
import java.util.Locale;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LocalizedFormatterTest {

    private final LocalizedAmountFormatter amounts =
            new LocalizedAmountFormatter();
    private final ScheduleDayFormatter days =
            new ScheduleDayFormatter();

    static Stream<Locale> locales() {
        return Stream.of(
                Locale.US,
                Locale.GERMANY,
                Locale.FRANCE,
                Locale.forLanguageTag("vi-VN"));
    }

    @ParameterizedTest
    @MethodSource("locales")
    void amountPrintParseRoundTrip(Locale locale)
            throws ParseException {

        LocalizedAmount original =
                new LocalizedAmount(new BigDecimal("1234.50"));

        String printed = amounts.print(original, locale);
        LocalizedAmount parsed = amounts.parse(printed, locale);

        assertEquals(0,
                parsed.value().compareTo(original.value()));
        assertEquals(printed,
                amounts.print(parsed, locale));

        // Ensure grouping/decimal separators match the locale.
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        assertTrue(printed.contains(
                String.valueOf(symbols.getGroupingSeparator())));
        assertTrue(printed.contains(
                String.valueOf(symbols.getDecimalSeparator())));
    }

    @ParameterizedTest
    @MethodSource("locales")
    void dayPrintParseRoundTrip(Locale locale)
            throws ParseException {

        ScheduleDay original =
                new ScheduleDay(LocalDate.of(2026, 9, 15));

        String printed = days.print(original, locale);
        ScheduleDay parsed = days.parse(printed, locale);

        assertEquals(original, parsed);
        assertEquals(printed, days.print(parsed, locale));
    }

    @Test
    void knownUsAndGermanAmountRepresentations()
            throws ParseException {

        LocalizedAmount amount =
                new LocalizedAmount(new BigDecimal("1234.50"));

        assertEquals("1,234.50",
                amounts.print(amount, Locale.US));
        assertEquals("1.234,50",
                amounts.print(amount, Locale.GERMANY));

        assertEquals(amount,
                amounts.parse("1,234.50", Locale.US));
        assertEquals(amount,
                amounts.parse("1.234,50", Locale.GERMANY));
        assertNotEquals(
                amounts.print(amount, Locale.US),
                amounts.print(amount, Locale.GERMANY));
    }

    @Test
    void wrongLocaleSeparatorsAreRejected() {
        assertThrows(ParseException.class,
                () -> amounts.parse(
                        "1.234,50", Locale.US));
        assertThrows(ParseException.class,
                () -> amounts.parse(
                        "1,234.50", Locale.GERMANY));
    }

    @Test
    void trailingGarbageCannotBeSilentlyIgnored() {
        assertThrows(ParseException.class,
                () -> amounts.parse(
                        "1,234.50ignored", Locale.US));
    }

    @Test
    void nonCanonicalAndTooPreciseInputAreRejected() {
        assertThrows(ParseException.class,
                () -> amounts.parse(
                        "1234.50", Locale.US));
        assertThrows(ParseException.class,
                () -> amounts.parse(
                        "1,234.567", Locale.US));
    }

    @Test
    void printingDoesNotRoundAwayExtraPrecision() {
        LocalizedAmount tooPrecise =
                new LocalizedAmount(new BigDecimal("1.234"));

        assertThrows(IllegalArgumentException.class,
                () -> amounts.print(tooPrecise, Locale.US));
    }

    @Test
    void strictDateParserRejectsImpossibleDay() {
        assertThrows(ParseException.class,
                () -> days.parse(
                        "31 Feb 2026", Locale.US));
    }
}
~~~

In `@ParameterizedTest`, **each locale is a separate invocation**. The two round-trip methods produce eight invocations total, and six regular `@Test` methods check boundary conditions. Do not confuse "two methods" with "two test executions".

**Why not assert specific French/Vietnamese date strings?** Because the goal here is round-trip consistency under the active formatter/JDK. When a product requires a fixed UI string, use separate snapshot/contract tests pinned to a specific JDK version and approved locale data; do not tie core unit tests to a Unicode glyph that might vary across providers.

### 8.2. Testing empty and negative inputs

Additional cases to include in an application test suite:
- `""`, `" "`, `null`: during binding, Spring may treat empty input as null before invoking a formatter; use `@NotNull` to catch required fields.
- `-1,234.50`, `(1,234.50)`: handle negative numbers per product rules; do not assume every locale shares one syntax.
- `0.00`: parses to zero, and business validation decides whether zero is allowed.
- Plus signs, Unicode minus signs, non-breaking spaces, and zero-width characters.
- Oversized numbers impacting budget limits/BigDecimal scale and DoS.
- Unsupported locales: define fallback or HTTP 400 behavior per policy.

A "well-tested" parser does not only parse valid values successfully; it must also **accurately reject inputs outside the contract**.

## 9. Unit tests: which Locale do ConversionService and WebDataBinder use?

### 9.1. `ConversionServiceLocaleTest.java`

~~~java
// src/test/java/com/example/localeformat/ConversionServiceLocaleTest.java
package com.example.localeformat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.format.support.FormattingConversionService;
import org.springframework.web.bind.WebDataBinder;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ConversionServiceLocaleTest {

    private static FormattingConversionService service() {
        FormattingConversionService service =
                new FormattingConversionService();
        service.addFormatter(new LocalizedAmountFormatter());
        service.addFormatter(new ScheduleDayFormatter());
        return service;
    }

    @Test
    void conversionServiceUsesLocaleContextForBothDirections() {
        FormattingConversionService conversion = service();

        LocalizedAmount original =
                new LocalizedAmount(new BigDecimal("1234.50"));
        LocaleContext previous =
                LocaleContextHolder.getLocaleContext();

        try {
            for (Locale locale : new Locale[]{
                    Locale.US, Locale.GERMANY,
                    Locale.FRANCE,
                    Locale.forLanguageTag("vi-VN")}) {

                LocaleContextHolder.setLocale(locale);

                String printed = conversion.convert(
                        original, String.class);
                LocalizedAmount parsed = conversion.convert(
                        printed, LocalizedAmount.class);

                assertEquals(original, parsed);
                assertEquals(printed, conversion.convert(
                        parsed, String.class));
            }
        } finally {
            LocaleContextHolder.setLocaleContext(previous);
        }
    }

    @Test
    void webDataBinderUsesRegisteredFormattersForFields() {
        BookingForm form = new BookingForm();
        WebDataBinder binder =
                new WebDataBinder(form, "bookingForm");
        binder.setConversionService(service());

        LocaleContext previous =
                LocaleContextHolder.getLocaleContext();

        try {
            LocaleContextHolder.setLocale(Locale.GERMANY);

            ScheduleDayFormatter days =
                    new ScheduleDayFormatter();
            String localizedDate = days.print(
                    new ScheduleDay(LocalDate.of(2026, 9, 15)),
                    Locale.GERMANY);

            binder.bind(new MutablePropertyValues(Map.of(
                    "amount", "1.234,50",
                    "day", localizedDate
            )));

            assertFalse(binder.getBindingResult().hasErrors());
            assertEquals(new LocalizedAmount(
                            new BigDecimal("1234.50")),
                    form.getAmount());
            assertEquals(new ScheduleDay(
                            LocalDate.of(2026, 9, 15)),
                    form.getDay());
        } finally {
            LocaleContextHolder.setLocaleContext(previous);
        }
    }
}
~~~

`FormattingConversionService` is the right type for registry tests because it implements `FormatterRegistry`. `LocaleContextHolder.setLocale(...)` drives adapter parse/print in synchronous test threads. The `finally` block restores the **previous LocaleContext**, preventing state leakage across tests.

`WebDataBinder` in this test wires the conversion service manually; if you test only `Formatter.parse` directly and skip these two layers, you can miss formatter-registration bugs (such as a class not being scanned or `addFormatters` not being called).

**Warning:** `LocaleContextHolder` uses thread-bound context, not a mechanism that automatically propagates across every Reactor scheduler. In WebFlux, test via `WebTestClient` and appropriate context propagation; do not call `setLocale` and expect every async thread to see it.

## 10. HTTP integration tests with MockMvc across multiple Locales

### 10.1. `BookingControllerLocaleTest.java`

~~~java
// src/test/java/com/example/localeformat/BookingControllerLocaleTest.java
package com.example.localeformat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Locale;
import java.util.stream.Stream;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingControllerLocaleTest {

    @Autowired MockMvc mvc;
    @Autowired LocalizedAmountFormatter amounts;
    @Autowired ScheduleDayFormatter days;

    static Stream<Locale> locales() {
        return Stream.of(
                Locale.US, Locale.GERMANY,
                Locale.FRANCE, Locale.forLanguageTag("vi-VN"));
    }

    @ParameterizedTest
    @MethodSource("locales")
    void formBindingAndPrintingUseRequestLocale(Locale locale)
            throws Exception {

        LocalizedAmount amount =
                new LocalizedAmount(new BigDecimal("1234.50"));
        ScheduleDay day =
                new ScheduleDay(LocalDate.of(2026, 9, 15));

        String amountText = amounts.print(amount, locale);
        String dayText = days.print(day, locale);

        mvc.perform(post("/api/bookings/form")
                    .locale(locale)
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("amount", amountText)
                    .param("day", dayText))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.amount")
                        .value("1234.50"))
                .andExpect(jsonPath("$.date")
                        .value("2026-09-15"))
                .andExpect(jsonPath("$.amountText")
                        .value(amountText))
                .andExpect(jsonPath("$.dateText")
                        .value(dayText));
    }

    @Test
    void wrongNumberForGermanLocaleIsBindingError()
            throws Exception {

        String correctDay = days.print(
                new ScheduleDay(LocalDate.of(2026, 9, 15)),
                Locale.GERMANY);

        mvc.perform(post("/api/bookings/form")
                    .locale(Locale.GERMANY)
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("amount", "1,234.50")
                    .param("day", correctDay))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.invalidFields",
                        hasItem("amount")));
    }

    @Test
    void wrongDateIsBindingError() throws Exception {

        mvc.perform(post("/api/bookings/form")
                    .locale(Locale.US)
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("amount", "1,234.50")
                    .param("day", "31 Feb 2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.invalidFields",
                        hasItem("day")));
    }

    @Test
    void missingRequiredAmountIsValidationError()
            throws Exception {

        String correctDay = days.print(
                new ScheduleDay(LocalDate.of(2026, 9, 15)),
                Locale.US);

        mvc.perform(post("/api/bookings/form")
                    .locale(Locale.US)
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("day", correctDay))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.invalidFields",
                        hasItem("amount")));
    }
}
~~~

Use `.locale(locale)` on `MockHttpServletRequestBuilder` to test the request locale explicitly. That differs from instantiating `Locale.US` in a unit test and assuming the controller picks it up automatically.

The test uses the Spring-injected formatters to build runtime-compatible input for each locale, then asserts the **normalized output**. This test does not confirm an external client generates the exact glyphs for each locale; to cover wire interoperability, add contract tests with input fixtures captured from that locale's UI/product.

### 10.2. Run commands

~~~bash
mvn test
~~~

Run an individual test class:

~~~bash
mvn -Dtest=LocalizedFormatterTest test
mvn -Dtest=ConversionServiceLocaleTest test
mvn -Dtest=BookingControllerLocaleTest test
~~~

The source suite contains:
- `LocalizedFormatterTest`: 2 parameterized methods × 4 locales = 8 invocations, plus 6 unit tests = **14 invocations**.
- `ConversionServiceLocaleTest`: 2 tests.
- `BookingControllerLocaleTest`: 1 parameterized method × 4 locales = 4 invocations, plus 3 tests = 7 invocations.

**Total 23 expected JUnit invocations.** This count is derived from the provided code; PASS results are expected when built in a compatible Spring Boot/JDK environment, **not a report of an executed Maven run**.

If tests fail, inspect package scanning, Spring 6.2 version, JDK locale/CLDR data, the conversion service active in MVC, and the specific parsing errors. Never delete a failing locale test just to turn CI green: it may be revealing user data interpreted differently in one environment.

### 10.3. Starting the server and testing via HTTP

~~~bash
mvn spring-boot:run
~~~

For example with `en-US`, you can send:

~~~bash
curl -i -X POST http://localhost:8080/api/bookings/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: en-US" \
  --data-urlencode "amount=1,234.50" \
  --data-urlencode "day=15 Sep 2026"
~~~

Expected JSON output when the active formatting/JDK matches `en-US`:

~~~json
{
  "amount": "1234.50",
  "date": "2026-09-15",
  "amountText": "1,234.50",
  "dateText": "15 Sep 2026"
}
~~~

For `de-DE`, send amount `1.234,50` and a day produced by the German formatter. Do not guess a German replacement for `Sep`: use output from the real formatter/JDK or an approved fixture.

Note that `\` line continuation works in Linux/macOS/Git Bash. PowerShell requires its own line-continuation syntax or a single-line `curl.exe` command.

## 11. Things that can break multi-Locale tests even when code is right

### 11.1. Different JDK/CLDR/locale providers

Java ships locale data that changes across providers and versions. For instance, French month abbreviations, `fr-FR` thousands separators, or script glyphs can differ between runtimes. Therefore split tests into two categories:
- **Behavioral/round-trip tests:** values print and parse equivalently, working against the current runtime's locale data.
- **Golden-output/contract tests:** compare exact product-approved strings; pin the JDK, locale provider, and update snapshots intentionally under review on upgrades.

Do not use `String.replace(" ", "")` to force a test to "pass" on non-breaking spaces: that masks real Unicode differences. If a product-approved normalization exists, implement and test it explicitly rather than hiding it in assertions.

### 11.2. Default locale makes tests machine-dependent

~~~java
// Bad for stable tests:
Locale locale = Locale.getDefault();
~~~

On an English-locale laptop, the test may pass; on a German or Vietnamese runner, parsing/printing differs. In tests, pass `Locale.US`/`Locale.GERMANY`/`Locale.FRANCE`/`Locale.forLanguageTag("vi-VN")` explicitly. For `LocaleContextHolder`, save the previous state and restore it in `finally`.

Avoid running tests in parallel if any of them mutate the **global** `Locale.setDefault(...)`. Even if reset afterward, changing the JVM default affects other tests/threads during that window.

### 11.3. Separating parse from binding/validation

~~~text
Input "1,234.50junk"
  |
  v
Formatter.parse -> ParseException
  |
  v
Spring DataBinder -> typeMismatch field error
  |
  v
BindingResult -> HTTP 400 decided by controller
~~~

And missing amount:

~~~text
Missing input field "amount"
  |
  v
BookingForm.amount == null
  |
  v
@Valid + @NotNull
  |
  v
BindingResult -> validation field error
~~~

Do not assert that every bad input produces an `@NotNull` error. Conversion failures and constraint violations come from two different sources. For `@RequestBody` JSON, Jackson parsing and `HttpMessageNotReadableException` follow yet another path.

### 11.4. Locale is not time zone

`LocalDate` represents a calendar date without an instant or time zone. `Instant`, `OffsetDateTime`, and `ZonedDateTime` carry zone/offset semantics. If a form captures `15/09/2026 23:30` in one zone, a round-trip can shift the date when changing zones; tests must cover `ZoneId`/DST too. Do not extend `ScheduleDayFormatter` to `Instant` simply by swapping the generic type.

### 11.5. Grouping/decimal precision and BigDecimal scale

With `BigDecimal("1.0")` and `BigDecimal("1.00")`:

~~~java
new BigDecimal("1.0").equals(
        new BigDecimal("1.00")); // false
new BigDecimal("1.0").compareTo(
        new BigDecimal("1.00")); // 0
~~~

This snippet illustrates Java expressions. If unit tests check monetary values by numeric semantics, `compareTo` may be more accurate than `equals`; if legal scale must be preserved, the contract must specify scale and serialization. The example formatter prints exactly two decimals, so a value `1.0` can normalize to `1.00` across a round-trip.

### 11.6. Thread safety and concurrent requests

`DecimalFormat` is not thread-safe; the example formatter creates a fresh instance on every `parse`/`print`. If a formatter caches a shared `DecimalFormat`, single-threaded tests pass while concurrent production requests corrupt formatting. You can add a test using `ExecutorService` to invoke parse/print concurrently on a singleton formatter across multiple locales, while avoiding false positives/flaky assertions and never sharing mutable number formatters.

### 11.7. Message locale vs value locale

`MessageSource` controls error message language, whereas `Formatter` controls locale-specific parsing/printing. Both often use the request locale, though business rules can fix one: e.g., imported CSV files always follow ISO/US format even when the UI is in Vietnamese. Document both policies:
- **UI display locale:** for frontend presentation and messages.
- **Data wire format:** can be fixed and locale-independent.

For machine-to-machine JSON APIs, prefer a stable wire format over localized text for numbers/dates. Localized formatting fits forms and UI rendering.

## 12. Deeper testing: property-specific, annotations, and HTTP stack

### 12.1. Per-field annotations

If a single object has two `LocalDate` fields where one should be ISO and one localized, field-level `@DateTimeFormat` may fit better than a global `Formatter<LocalDate>`. When designing tests:
1. Define exact source/target types and annotations.
2. Test conversion both with the annotation present and absent.
3. Ensure `@InitBinder`/global formatters do not unexpectedly override it.
4. Test that invalid input becomes a `FieldError` at the right path.

### 12.2. Indexed fields/nested objects

A form with `List<LineItem>` may submit `items[0].price=1.234,50`, `items[1].price=2.345,60`. If `price` is `LocalizedAmount`, Spring applies that type's formatter when binding nested elements. Tests need to check:
- Exact locale.
- Accurate `items[0].price`/`items[1].price` indexes.
- Allowed field paths such as `items[*].price`.
- Auto-grow limits via `setAutoGrowCollectionLimit` and request body size limits.
- Not binding `items[*].approved` or role/owner fields from clients.

Suppressed field paths do not necessarily set `BindingResult#hasErrors()` to true; if security policy requires rejecting extra fields, inspect `getSuppressedFields()` separately.

### 12.3. MVC and WebFlux differ at the HTTP layer, share the formatter SPI

In MVC, `MockMvc` tests locale resolvers/formatting on the Servlet stack. In WebFlux, use `WebTestClient` and `WebFluxConfigurer#addFormatters`. `Formatter<T>`/`ConversionService` is Spring's shared SPI, yet how locale is retrieved in a reactive chain must be verified; do not rely on ThreadLocal `LocaleContextHolder` propagating implicitly across every scheduler.

If production runs WebFlux, move HTTP integration tests to a real reactive context; never use `MockMvc` to claim WebFlux works.

## 13. Debugging common issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Locale=en-US yet values parse as de-DE | Wrong request LocaleResolver or default locale | Test `.locale(Locale.US)`, inspect `LocaleContextHolder` |
| Direct formatter test passes, MVC fails | Forgot `WebMvcConfigurer#addFormatters` | Check registry and integration tests |
| Number with `junk` suffix still parses | `NumberFormat` parses only prefix | Use `ParsePosition` and check `index == length` |
| `1234.50` is rejected | Demo requires canonical grouping | Loosen policy intentionally and update tests |
| `fr-FR` fails on spaces | U+202F vs U+0020 or JDK locale provider | Inspect Unicode code points; do not blindly alter regex |
| Upgrading JDK breaks date snapshots | CLDR abbreviations/locale data changed | Separate behavioral tests from golden contract tests |
| Formatter outputs numbers missing decimals | Rounding/DecimalFormat pattern | Define scale and test full precision |
| `BigDecimal.equals` fails despite equal numeric values | Different scale | Use `compareTo` if contract only cares about numeric value |
| Singleton formatter fails intermittently | Shared mutable `DecimalFormat`/`SimpleDateFormat` | Create a new parser per call or use immutable formatters |
| `FieldError#typeMismatch` appears | `ParseException` during binding | Test formatter separately, check input locale |
| Missing field produces no error | Missing `@NotNull`/validation | Add constraint and test missing-field case |
| JSON ignores custom formatter | `@RequestBody` goes through Jackson | Use DTOs/Jackson modules and test separately |
| API returns ISO date even though formatter is localized | JSON serializer does not call `Formatter.print` | Print explicitly for UI or configure JSON serializer |
| One test breaks another test's locale | Used `Locale.setDefault` or forgot context cleanup | Scope `LocaleContextHolder` with `finally` |
| Dots and commas cause confusion | Client sent wrong locale | Document accepted locales and add negative tests |
| Controller uses `@Validated`/different validator | Different binding and validation lifecycles | Test against the right Spring app context |
| Nested form field fails to parse | Missing formatter for target type or wrong path | Test type/field registration and nested indices |
| Locale differs between parse and print | Inconsistent locales used | Round-trip with the same Locale and test mismatch |
| Strict `DateTimeFormatter` fails with `yyyy` | Year-of-era missing era | Use `uuuu` for strict year parsing |
| Renderer uses default time zone | Confused Locale with ZoneId | Test time zone independently if type holds an instant |

## 14. Code review checklist for multi-Locale testing

- [ ] Clearly distinguish which formats depend on `Locale` and which are locale-independent wire formats.
- [ ] Test **parse**, **print**, **parse(print(x))**, and **print(parse(text))** per canonical rules.
- [ ] Cover at least `en-US`/`de-DE` plus the locales your product actually supports, e.g., `fr-FR`/`vi-VN`.
- [ ] Test grouping separators, decimal separators, abbreviated months, and invisible Unicode characters.
- [ ] Test wrong separators, trailing garbage, excess fractional digits, impossible dates, and missing values.
- [ ] Use `BigDecimal` where precision matters, distinguishing numeric equality from scale equality.
- [ ] Never share mutable `DecimalFormat`/`SimpleDateFormat` across threads.
- [ ] Configure `FormatterRegistry` for the right MVC/WebFlux stack, then test via `FormattingConversionService` and HTTP.
- [ ] Avoid global `Locale.setDefault` in tests; use `LocaleContextHolder` with context restoration.
- [ ] Do not hardcode locale strings for `fr-FR`/`vi-VN` unless JDK/CLDR and contract are pinned.
- [ ] Maintain separate golden tests for UI strings that genuinely must stay fixed across releases.
- [ ] `@Valid`/`@NotNull` handle missing data while `BindingResult` handles conversion errors; do not confuse the two.
- [ ] Do not assume Jackson JSON goes through `Formatter`/`@ModelAttribute` binders.
- [ ] Control allowed field paths, input size, and collection indexes when forms contain nested objects.
- [ ] When upgrading Java/Spring, re-run the locale matrix and review differences intentionally.

## 15. Practice exercises

1. Change `LocalizedAmountFormatter` to accept both `1234.50` and `1,234.50` in `en-US`, while always printing `1,234.50`. Write assertions separating accepted inputs from canonical output.
2. Add `ja-JP` and `ar-EG` to the locale matrix. Test native digits, bidi, and Unicode; do not assume Latin digits.
3. Write a `Formatter<LocalDate>` using `FormatStyle.SHORT`, compare round-trip tests with `dd MMM uuuu`, and discuss JDK/CLDR snapshot risks.
4. Test boundaries `BigDecimal("1.00")`, `1.0`, `1.234`, negative numbers, and zero. Define a rounding/scale policy before modifying the parser.
5. Create a form with `List<LocalizedAmount>`, sending `items[0]` and `items[1]`. Test paths and allowlist while enforcing collection limits.
6. Build a screen with two date fields—one ISO and one user-locale—using field-level `@DateTimeFormat`, and test independently.
7. Port the project to WebFlux with `WebFluxConfigurer#addFormatters`, writing `WebTestClient` tests with locale headers; do not copy `MockMvc`.
8. Use `LocaleContextHolder` in a multithreaded test and explain why thread-local state does not automatically follow all tasks.
9. Design Vietnamese/English error messages for amount parse failures using `MessageSource`; never expose raw exception text or rejected values in public responses.

## 16. Conclusion

Testing localized formatting is not just checking whether a string contains a comma or a dot. A reliable Spring system tests **both directions**, **multiple Locales**, **failure cases**, and **real integration** from Formatter through ConversionService to DataBinder/HTTP requests.

Easy rule to remember:

~~~text
value -> print(value, locale) -> localized text
localized text -> parse(text, locale) -> value

SAME locale + explicit contract + no silent truncation
    = predictable form binding and display
~~~

Pin *semantic values* in behavioral tests, and pin *exact localized strings* only when the product truly requires them and runtime locale data is governed. `Locale` is part of the input contract, not a "harmless global variable".

## 17. References

- Spring Framework 6.2, **Spring Field Formatting** (Formatter/Printer/Parser): https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html
- Spring Framework 6.2, **Web MVC Type Conversion**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html
- Spring Framework 6.2, **FormattingConversionService Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/format/support/FormattingConversionService.html
- Spring Framework 6.2, **DefaultFormattingConversionService Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/format/support/DefaultFormattingConversionService.html
- Spring Framework 6.2, **NumberFormat Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/format/annotation/NumberFormat.html
- Spring Framework 6.2, **DateTimeFormat Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html
- Spring Framework 6.2, **WebMvcConfigurer.addFormatters Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html
- Spring Framework 6.2, **MVC @ModelAttribute**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Boot 3.5, **Spring MVC Conversion Service**: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Java 17, **DecimalFormat**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html
- Java 17, **DateTimeFormatter**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java 17, **Locale**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
