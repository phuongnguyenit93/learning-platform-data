# DateFormatter and DateTimeFormatterRegistrar in Spring: Date/Time Formatting and Data Binding

## 1. Why does Spring need date/time formatters?

When a user sends `2026-11-05` in a query parameter, path variable, or HTML form, the raw data arrives as a string. Meanwhile, the controller or model may require `java.util.Date`, `LocalDate`, `LocalDateTime`, or `OffsetDateTime`. Spring must **parse** the string into an object of the target type; when rendering the object in a form or view, Spring may **print** the object back into a string.

These date/time types differ fundamentally: `Date` represents an instant on the timeline; `LocalDate` only holds a calendar date with no time, offset, or time zone. Therefore, **a single formatting rule cannot be applied to all types without considering the value's semantics**.

This lesson focuses on two APIs:
- `org.springframework.format.datetime.DateFormatter`: a `Formatter<Date>` for the legacy `java.util.Date` system.
- `org.springframework.format.datetime.standard.DateTimeFormatterRegistrar`: a **formatter registrar** for using `java.time.format.DateTimeFormatter`-based formats across `java.time` types.

Easily confused names: `DateFormatter` is the **object that directly parses/prints `Date`**; `DateTimeFormatterRegistrar` is the **object that configures and registers formatters**. `DateTimeFormatter` (without `Registrar`) is a **JDK** formatting class, not a Spring class.

## 2. Where do Formatters sit in the conversion mechanism?

Spring has two related concepts:

- `Converter<S,T>` primarily describes a type conversion from `S` to `T`, without needing a `Locale` parameter.
- `Formatter<T>` consists of `Parser<T>.parse(String, Locale)` and `Printer<T>.print(T, Locale)`, suited for locale-sensitive display data such as numbers, dates, and times.

`FormattingConversionService` combines converters and formatters. `FormatterRegistry` is the registration API: `addFormatter(...)`, `addFormatterForFieldType(...)`, plus converter registration methods. `FormatterRegistrar` has one method `registerFormatters(FormatterRegistry registry)` to register a group of formatters/converters under a shared policy.

```text
HTTP query / path / form (String)
               |
               v
     Spring MVC WebDataBinder
               |
               v
     FormattingConversionService
               |
     select rule by target type
           /                    \
  java.util.Date             java.time.*
       |                         |
 DateFormatter             formatters from
 (DateFormatterRegistrar)  DateTimeFormatterRegistrar
       |                         |
   parse(text, Locale)      parse(text, Locale)
           \                    /
                Java object
                     |
            Controller / Model
```

The reverse direction (printing a value to a form or view) uses `print(value, Locale)` when the rendering flow integrates Spring formatting. Do not assume that returning JSON via `@ResponseBody` uses this formatter too: JSON is usually handled separately by Jackson.

## 3. DateFormatter: for java.util.Date

`DateFormatter` implements `Formatter<java.util.Date>` and is backed by `java.text.DateFormat`/`SimpleDateFormat`. It can accept a specific pattern:

```java
import java.util.TimeZone;
import org.springframework.format.datetime.DateFormatter;

DateFormatter formatter = new DateFormatter("yyyy-MM-dd");
formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
formatter.setLenient(false);
```

This is a **fragment** creating a formatter inside a project that already has Spring libraries; it is not a standalone Java file. Meaning of each option:

- `"yyyy-MM-dd"` specifies the date pattern, e.g. `2026-11-05`. `MM` is **month**; `mm` is **minute**.
- `setTimeZone(UTC)` specifies the time zone used when converting between a **calendar date string** and a `Date` (an absolute instant). If unset, behavior can depend on the JVM default time zone.
- `setLenient(false)` rejects out-of-range dates like Feb 30 instead of rolling them over to another date. This is also `DateFormatter`'s default.
- `DateFormatter` can be configured via `setPattern(...)`, `setIso(...)`, `setStyle(...)`/`setStylePattern(...)`, and `setFallbackPatterns(...)`. Fallback patterns are only tried when **parsing** fails; they do not govern **printing**.

In essence, `java.util.Date` stores an instant. Parsing `"2026-11-05"` with a date-only pattern in UTC means **00:00 UTC on 2026-11-05**, whereas parsing the same string in another time zone yields a different `Date.getTime()`. That is why **birth dates, booking dates, and due dates** usually fit `LocalDate` better than `Date`.

### What is DateFormatterRegistrar?

`org.springframework.format.datetime.DateFormatterRegistrar` is the corresponding registrar for legacy date/time types. Main API:

```java
import org.springframework.format.datetime.DateFormatter;
import org.springframework.format.datetime.DateFormatterRegistrar;
import org.springframework.format.FormatterRegistry;

void registerLegacyDates(FormatterRegistry registry) {
    DateFormatterRegistrar registrar = new DateFormatterRegistrar();
    registrar.setFormatter(new DateFormatter("yyyy-MM-dd"));
    registrar.registerFormatters(registry);
}
```

When `setFormatter(...)` is called, the registrar registers a global formatter for `Date`/`Calendar` fields without a specific formatting annotation, along with annotation support and converters for the legacy group. If `setFormatter(...)` is **not** called, the registrar does **not** automatically add a global formatter for unannotated `Date` and `Calendar` fields. Details regarding `long`/`Long` support depend on the converter or `@DateTimeFormat` context; do not assume every epoch number is automatically parsed with a date pattern.

For new code, prefer `java.time`; you still need to know `DateFormatter` when integrating with legacy APIs and entities.

## 4. DateTimeFormatterRegistrar: for java.time

`DateTimeFormatterRegistrar` implements `FormatterRegistrar` and registers formatters for the Java Time API types. Key API:

| Method | Effect |
| --- | --- |
| `setUseIsoFormat(true)` | Uses ISO formatting for date, time, and date-time groups; defaults to `false` |
| `setDateStyle(FormatStyle)` | Selects locale-based display style for dates; defaults to `SHORT` |
| `setTimeStyle(FormatStyle)` | Selects locale-based display style for times; defaults to `SHORT` |
| `setDateTimeStyle(FormatStyle)` | Selects locale-based display style for date and time |
| `setDateFormatter(DateTimeFormatter)` | Uses a specific formatter for `LocalDate` |
| `setTimeFormatter(DateTimeFormatter)` | Uses a specific formatter for `LocalTime`, `OffsetTime` |
| `setDateTimeFormatter(DateTimeFormatter)` | Uses a specific formatter for `LocalDateTime`, `ZonedDateTime`, `OffsetDateTime` |
| `registerFormatters(registry)` | Actually registers the formatters/converters into the registry |

Formatters passed directly via `setDateFormatter`/`setTimeFormatter`/`setDateTimeFormatter` **take precedence over** style options and `useIsoFormat` for their respective groups. `setUseIsoFormat(true)` renders group styles inactive unless an explicit formatter is set. Choose a clear policy and test with real data types.

Example of a concise ISO configuration:

```java
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;

void registerModernDates(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
    registrar.setUseIsoFormat(true);
    registrar.registerFormatters(registry);
}
```

Once registered as above, common forms include:

| Java type | Sample ISO string value | What to understand |
| --- | --- | --- |
| `LocalDate` | `2026-11-05` | Calendar date; no time zone |
| `LocalTime` | `09:30:00` | Time of day; no date or time zone |
| `LocalDateTime` | `2026-11-05T09:30:00` | Local date and time; still no offset |
| `OffsetDateTime` | `2026-11-05T09:30:00+07:00` | Has UTC offset |
| `ZonedDateTime` | `2026-11-05T09:30:00+07:00[Asia/Ho_Chi_Minh]` | Has zone/offset info in full representation |
| `OffsetTime` | `09:30:00+07:00` | Has time and offset, no date |

The strings above illustrate valid representations; fractional second length and offset/zone printing depend on the specific formatter. Do not treat `LocalDateTime` as an absolute instant without knowing the time zone/offset.

### How do ISO, pattern, and style differ?

- **ISO** suits machine-to-machine communication and standard values sent by browsers, especially HTML `<input type="date">` sending `yyyy-MM-dd`.
- **Pattern** is an explicit character contract, e.g. `DateTimeFormatter.ofPattern("dd/MM/uuuu")` for `05/11/2026`. You must specify language/locale clearly if using month or weekday names.
- **Style** (`SHORT`, `MEDIUM`, `LONG`, `FULL`) is intended for human display and depends on locale/JDK. Do not treat style as a stable API data format.

For `java.time`, pattern `uuuu` represents the proleptic year and works well for strict parsing; `yyyy` is year-of-era and may need adjustment under `ResolverStyle.STRICT`. For legacy `SimpleDateFormat`, `yyyy` is the familiar year convention. Do not copy patterns across the two APIs without checking symbol meanings.

## 5. Complete Spring MVC configuration for both groups

Below is a Java configuration using both registrars via `WebMvcConfigurer.addFormatters`. It is suitable for adding a formatting policy to request data binding in a **Spring Web MVC application**:

**File `src/main/java/com/example/demo/WebDateFormatConfig.java`:**

```java
package com.example.demo;

import java.util.TimeZone;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.DateFormatter;
import org.springframework.format.datetime.DateFormatterRegistrar;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebDateFormatConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        // java.time: ISO for LocalDate, LocalTime, LocalDateTime, ...
        DateTimeFormatterRegistrar modern = new DateTimeFormatterRegistrar();
        modern.setUseIsoFormat(true);
        modern.registerFormatters(registry);

        // java.util.Date (legacy): yyyy-MM-dd, interpreted in UTC.
        DateFormatter legacyDate = new DateFormatter("yyyy-MM-dd");
        legacyDate.setTimeZone(TimeZone.getTimeZone("UTC"));
        legacyDate.setLenient(false);

        DateFormatterRegistrar legacy = new DateFormatterRegistrar();
        legacy.setFormatter(legacyDate);
        legacy.registerFormatters(registry);
    }
}
```

**File `src/main/java/com/example/demo/DateController.java`:**

```java
package com.example.demo;

import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Date;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DateController {

    @GetMapping("/dates")
    public String inspect(
            @RequestParam LocalDate day,
            @RequestParam Date legacy) {

        LocalDate legacyDay = legacy.toInstant()
                .atZone(ZoneOffset.UTC)
                .toLocalDate();

        return "day=" + day + ";legacyDay=" + legacyDay;
    }
}
```

These snippets are **two files in a Spring MVC/Spring Boot application with the `spring-webmvc` dependency**; they cannot be run with `javac` alone because they require Spring libraries and an HTTP server.

Assuming the classes are covered by component scan, call:

```http
GET /dates?day=2026-11-05&legacy=2026-11-05
```

Text response body returned by the controller above:

```text
day=2026-11-05;legacyDay=2026-11-05
```

Explanation: `day` is parsed into `LocalDate` via `DateTimeFormatterRegistrar`'s ISO policy. `legacy` is parsed into `Date` via `DateFormatter` with pattern `yyyy-MM-dd` in UTC. The controller converts `Date` to `LocalDate` in UTC to illustrate instant semantics. If a request uses `day=05/11/2026`, the ISO formatter will reject it under the same contract.

**Scope note:** `WebMvcConfigurer` configures Spring MVC's registry. A standalone `ConversionService` in the service layer, WebFlux, or Spring Boot's configuration binder may use different settings. Do not assume the entire application shares one registry automatically.

## 6. When to choose specific formatters per java.time type?

Beyond general ISO, you can supply specific formatters:

```java
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;

DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();

// Date-only string dd/MM/yyyy for LocalDate:
registrar.setDateFormatter(
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT));

// Example display-style formatter for LocalTime / OffsetTime:
registrar.setTimeStyle(FormatStyle.SHORT);

// Groups not overridden by a specific formatter can still use ISO:
registrar.setUseIsoFormat(true);
```

This is a **configuration fragment**; you must call `registrar.registerFormatters(registry)` where `FormatterRegistry` is available for it to take effect. In the example, the explicit `LocalDate` formatter takes precedence over ISO, while ISO takes precedence over style for the time group. Therefore, `setTimeStyle(SHORT)` **has no effect** while `useIsoFormat(true)` remains enabled. If you truly want a time style, omit `setUseIsoFormat(true)` or configure a formatter for time separately.

For offset/zone-bearing types, do not blindly apply a pattern with only `dd/MM/uuuu HH:mm`; a pattern lacking offset/zone info can cause `OffsetDateTime` or `ZonedDateTime` parsing to fail. For APIs requiring exact instants, specify which offset the client supplies and choose `OffsetDateTime`/`Instant` per the contract.

## 7. @DateTimeFormat vs global policy

`@DateTimeFormat` (Spring) applies directly to a field or parameter; it is the *local* way to pick a format when a specific endpoint has special requirements:

```java
import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/reports")
    String report(
            @RequestParam
            @DateTimeFormat(pattern = "dd/MM/uuuu")
            LocalDate since) {

        return since.toString();
    }
}
```

With this declaration, the query `/reports?since=05%2F11%2F2026` is parsed into `LocalDate.of(2026,11,5)` and the method returns `2026-11-05`, **even when** the global formatter for `LocalDate` uses ISO. The field/parameter annotation takes precedence over the global formatter when Spring applies annotation-driven formatting.

Annotation options:
- `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`: ISO date format.
- `@DateTimeFormat(pattern = "dd/MM/uuuu")`: explicit pattern for `java.time` in Spring Framework.
- `@DateTimeFormat(style = "S-")`: short locale-based date style, prone to change across locales/JDKs.
- `fallbackPatterns`: supports backup patterns **when parsing**, while printing still uses the primary format.

Do not arbitrarily combine `pattern`, `iso`, and `style` on the same annotation: use **one primary policy**. Per Spring's precedence, pattern overrides ISO, and ISO overrides style.

## 8. Standalone Java 17+ example: differences between the two JDK APIs

To observe formatting without depending on Spring or a web server, create `DateFormatPlainJavaDemo.java`:

```java
import java.text.SimpleDateFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.TimeZone;

public class DateFormatPlainJavaDemo {
    public static void main(String[] args) throws Exception {
        DateTimeFormatter modern = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        LocalDate day = LocalDate.parse("05/11/2026", modern);
        System.out.println(day);
        System.out.println(modern.format(day));

        SimpleDateFormat legacy =
                new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
        legacy.setTimeZone(TimeZone.getTimeZone("UTC"));
        legacy.setLenient(false);

        System.out.println(legacy.format(legacy.parse("2026-11-05")));

        try {
            LocalDate.parse("31/02/2026", modern);
        } catch (DateTimeParseException ex) {
            System.out.println("INVALID_DATE");
        }
    }
}
```

Compile/run (JDK 17+):

```bash
javac DateFormatPlainJavaDemo.java
java DateFormatPlainJavaDemo
```

Exact stdout:

```text
2026-11-05
05/11/2026
2026-11-05
INVALID_DATE
```

`SimpleDateFormat` used for legacy dates is mutable and not thread-safe when sharing the same instance across threads; Java Time's `DateTimeFormatter` is immutable/thread-safe and suited for modern applications. In Spring, `DateFormatter` creates a `DateFormat` when formatting/parsing; this Java example directly creates a `SimpleDateFormat` to illustrate patterns and time zones.

## 9. Testing Spring FormattingConversionService directly

You can decouple registrar verification from HTTP. JUnit Jupiter example, assuming the classpath includes Spring Context and JUnit 5:

**File `DateRegistrarsTest.java` (in the project's test package):**

```java
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Date;
import java.util.TimeZone;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.format.datetime.DateFormatter;
import org.springframework.format.datetime.DateFormatterRegistrar;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.format.support.DefaultFormattingConversionService;

import static org.junit.jupiter.api.Assertions.*;

class DateRegistrarsTest {

    private DefaultFormattingConversionService newService() {
        // Standalone test service, avoiding implicit MVC registry defaults.
        var service = new DefaultFormattingConversionService(false);

        var modern = new DateTimeFormatterRegistrar();
        modern.setUseIsoFormat(true);
        modern.registerFormatters(service);

        var legacyDate = new DateFormatter("yyyy-MM-dd");
        legacyDate.setTimeZone(TimeZone.getTimeZone("UTC"));
        var legacy = new DateFormatterRegistrar();
        legacy.setFormatter(legacyDate);
        legacy.registerFormatters(service);

        return service;
    }

    @Test
    void isoLocalDateAndUtcLegacyDate() {
        var service = newService();

        assertEquals(
                LocalDate.of(2026, 11, 5),
                service.convert("2026-11-05", LocalDate.class));

        Date legacyDate = service.convert("2026-11-05", Date.class);
        assertNotNull(legacyDate);
        assertEquals(
                LocalDate.of(2026, 11, 5),
                legacyDate.toInstant()
                        .atZone(ZoneOffset.UTC)
                        .toLocalDate());
    }

    @Test
    void incorrectPatternFailsInsteadOfGuessing() {
        var service = newService();

        assertThrows(
                ConversionFailedException.class,
                () -> service.convert("05/11/2026", LocalDate.class));
    }
}
```

`DefaultFormattingConversionService(false)` is used here to test registrar policies against a clean registry without relying on default formatters. When configuring a replacement `FormattingConversionService` for a real application, you must register all other required formatters/annotation factories; this test setup does not represent the full default configuration of Spring MVC/Boot.

Beyond unit tests, write integration tests using `MockMvc` or real HTTP calls to verify that `WebMvcConfigurer` is scanned, URLs are parsed, and conversion errors are reflected accurately. Test valid dates, invalid patterns, non-existent dates, time zones, and missing strings.

## 10. Rules for choosing data types and handling binding errors

| Business data | Type to consider | Reason |
| --- | --- | --- |
| Birth date, delivery date | `LocalDate` | Time zone independent |
| Opening hours (date-independent) | `LocalTime` | No date/offset |
| Local appointment without assigned zone | `LocalDateTime` | Stores local date + time; does not define an instant yet |
| Event with offset in request | `OffsetDateTime` | String contains offset to identify an instant |
| Absolute log/event timestamp | `Instant` | UTC point on the timeline |
| Legacy system using `java.util.Date` | `Date` | Requires attention to time zone when parsing/printing |

When parsing fails due to a pattern mismatch—such as sending `day=05/11/2026` to an ISO formatter—Spring cannot construct a `LocalDate`. In `ConversionService`, the failure may be wrapped in `ConversionFailedException`; in an MVC controller with `@RequestParam`, a type error typically results in HTTP 400; in `@ModelAttribute`, it can record a `typeMismatch` error in `BindingResult`. Bean Validation only validates objects that have already been bound; it does not fix malformed date strings.

For JSON bodies (`@RequestBody`), Jackson usually deserializes date/time strings according to `ObjectMapper`/Java Time module configuration. `@JsonFormat` is a Jackson annotation, distinct from Spring's `@DateTimeFormat`. Do not conclude that configuring `DateTimeFormatterRegistrar` in MVC automatically changes how Jackson reads JSON. Likewise, Spring WebFlux and Spring Boot configuration binding have their own configuration mechanisms.

## 11. Common implementation mistakes

1. **Confusing `DateFormatter` with `DateTimeFormatter`:** the former is Spring's `Date` formatter, the latter is JDK's Java Time formatter; `DateTimeFormatterRegistrar` registers Java Time formatters.
2. **Creating a registrar without calling `registerFormatters(registry)`:** the configuration is never added to the conversion service.
3. **Registering properly but in the wrong registry:** MVC, WebFlux, Jackson, and configuration binding do not necessarily share a conversion service.
4. **Using `dd/MM/yyyy` for HTML `input type="date"` clients:** browsers submit `yyyy-MM-dd` regardless of local display; choose ISO where appropriate.
5. **Confusing `MM` with `mm`, or `yyyy` with `YYYY`:** `MM` is month, `mm` is minute, and `YYYY` is usually *week-based-year* in the JDK, which can break around New Year's.
6. **Parsing date-only strings into `Date` without specifying a time zone:** the same string can produce different timestamps on servers in different time zones.
7. **Using `LocalDateTime` as an instant:** this type has no offset/zone and is insufficient to pinpoint an absolute moment.
8. **Expecting `@DateTimeFormat` to fix JSON:** JSON requires separate Jackson configuration.
9. **Relying on locale/JDK-dependent styles:** display formats can change across runtimes; API data should use ISO or explicit patterns.
10. **Creating a custom singleton `SimpleDateFormat`:** this class is mutable and unsafe across concurrent threads; prefer `DateTimeFormatter` for modern projects.

## 12. Date/time formatting design checklist

- Choose the **Java type matching business semantics** before choosing a pattern.
- Identify whether data comes from **query/path/form** or a **JSON body**, as parser pipelines differ.
- For `java.time`, register `DateTimeFormatterRegistrar`; for legacy `Date`, use `DateFormatter` and `DateFormatterRegistrar` when needed.
- Prefer ISO for system-to-system communication; use locale-based patterns only when UI requirements genuinely call for them.
- For `Date`, pin the time zone if consistent results across environments are required.
- Define error reporting for malformed strings, non-existent dates, and invalid time zones; never guess dates.
- Write unit tests for conversion and integration tests for data binding/controllers; always verify against the target Spring version and runtime configuration.

### Official references

- [Spring Framework — Configuring a Global Date and Time Format](https://docs.spring.io/spring-framework/reference/core/validation/format-configuring-formatting-globaldatetimeformat.html).
- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html).
- [Spring Framework — Spring MVC Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html).
- [Spring Framework Javadoc — DateFormatter](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/format/datetime/DateFormatter.html).
- [Spring Framework Javadoc — DateFormatterRegistrar](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/format/datetime/DateFormatterRegistrar.html).
- [Spring Framework Javadoc — DateTimeFormatterRegistrar](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/format/datetime/standard/DateTimeFormatterRegistrar.html).
