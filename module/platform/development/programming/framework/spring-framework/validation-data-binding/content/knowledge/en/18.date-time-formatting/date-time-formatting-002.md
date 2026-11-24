# LocalDate, LocalTime, LocalDateTime, and Time-Zoned Types — Date and Time Formatting in Spring Framework

## 1. Objectives and the most important principle

Date and time data in Java/Spring must answer **two different questions**:

1. What form does the string take when a user enters it or the application prints it? This is **formatting/parsing**.
2. Does the value represent a calendar date, a wall-clock time, or **a specific instant on the global timeline**? This is **data type and time zone semantics**.

`java.time` (Java 8+, works well on Java 17+) provides immutable, thread-safe types. Spring Framework uses `ConversionService` and `Formatter` to bind string data from query parameters, path variables, and forms into these types. Choose **the right Java type first**, and only then choose `@DateTimeFormat` or `DateTimeFormatter`.

**Overarching rule:** `LocalDateTime` contains no time zone/offset information; changing the display format cannot determine which UTC instant it represents. When a globally meaningful *instant* is required, there must be an offset or a `ZoneId` rule.

## 2. Map of `java.time` types

| Type | What does it contain? | Does it have enough information to identify an instant? | Example |
| --- | --- | --- | --- |
| `LocalDate` | Calendar date, without time | No | `2026-11-05` |
| `LocalTime` | Hour/minute/second, without date | No | `09:30:00` |
| `LocalDateTime` | Local date + time | No | `2026-11-05T09:30:00` |
| `OffsetTime` | Time of day + fixed offset | No, because date is missing | `09:30:00+07:00` |
| `OffsetDateTime` | Date + time + UTC offset | Yes | `2026-11-05T09:30:00+07:00` |
| `ZonedDateTime` | Date + time + time zone region with applied offset | Yes | `2026-11-05T09:30:00+07:00[Asia/Ho_Chi_Minh]` |
| `Instant` | Absolute instant on the UTC timeline | Yes | `2026-11-05T02:30:00Z` |
| `ZoneId` | Time zone region/rules identifier | Not a date/time | `Asia/Ho_Chi_Minh` |
| `ZoneOffset` | Fixed offset from UTC | Not a date/time | `+07:00` |

**Key differences to remember:**

- `LocalDate` suits birth dates, report dates, and holidays; by itself it has no concept of "00:00 UTC".
- `LocalTime` suits daily recurring opening hours; it must be paired with a date and zone to convert into an instant.
- `LocalDateTime` suits the intent "meeting at 09:30 on 05/11 locally", but determining the instant requires knowing *which locality*.
- `OffsetDateTime` preserves the UTC offset at the represented point, but a fixed offset does not carry a region's daylight saving time transition rules.
- `ZonedDateTime` preserves a region `ZoneId` such as `Europe/Paris`, thereby applying historical/DST rules; the string form containing `[Europe/Paris]` is Java's ISO extension.
- `Instant` suits event timestamps, logs, transaction timestamps, and absolute chronological ordering.

`Z` in a string like `2026-11-05T02:30:00Z` means UTC offset `+00:00`. `Asia/Ho_Chi_Minh` is a **zone ID**, whereas `+07:00` is an **offset**; do not use the two concepts interchangeably when scheduling in places with DST.

## 3. Parsing and formatting with `DateTimeFormatter`

**Parse**: `String → java.time`. **Format**: `java.time → String`. Formatters are immutable and safe to reuse, unlike legacy `SimpleDateFormat` which holds mutable state.

Built-in formatters (no need to write custom patterns):

| Formatter | Appropriate value | Sample string |
| --- | --- | --- |
| `ISO_LOCAL_DATE` | `LocalDate` | `2026-11-05` |
| `ISO_LOCAL_TIME` | `LocalTime` | `09:30:00` |
| `ISO_LOCAL_DATE_TIME` | `LocalDateTime` | `2026-11-05T09:30:00` |
| `ISO_OFFSET_TIME` | `OffsetTime` | `09:30:00+07:00` |
| `ISO_OFFSET_DATE_TIME` | `OffsetDateTime` | `2026-11-05T09:30:00+07:00` |
| `ISO_ZONED_DATE_TIME` | `ZonedDateTime` | `2026-11-05T09:30:00+07:00[Asia/Ho_Chi_Minh]` |
| `ISO_INSTANT` | `Instant` | `2026-11-05T02:30:00Z` |

Note: Java's ISO formatters may omit seconds/fractional seconds when unnecessary; the strings in the table are valid examples, **not a guarantee that every format call keeps the exact same character count**.

For custom formats, commonly used symbols:

| Symbol | Meaning | Example |
| --- | --- | --- |
| `uuuu` | ISO/proleptic calendar year | `2026` |
| `yyyy` | Year-of-era | `2026` |
| `MM`, `dd` | 2-digit month, day | `11`, `05` |
| `HH`, `mm`, `ss` | Hour 0–23, minute, second | `09:30:00` |
| `h`, `a` | Hour 1–12 and AM/PM | `9 AM` |
| `SSS` | Milliseconds | `123` |
| `XXX` | Offset in `+07:00` or `Z` form | `+07:00` |
| `VV` | Region `ZoneId` | `Asia/Ho_Chi_Minh` |
| `'T'` | Literal letter T separating date/time | `2026-11-05T09:30` |

`MM` is **month**, `mm` is **minute**; `HH` is 24-hour clock, `hh` is 12-hour clock. Do not use `YYYY` (week-based-year) instead of `yyyy`/`uuuu` for calendar date data. With `DateTimeFormatter` in `ResolverStyle.STRICT` mode, use `uuuu` for the ISO year to avoid `yyyy`'s era dependency.

### Complete Java 17+ example

Save as `JavaTimeFormatsDemo.java`:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class JavaTimeFormatsDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.parse("2026-11-05");
        LocalTime time = LocalTime.parse("09:30");
        LocalDateTime local = LocalDateTime.of(day, time);

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = local.atZone(zone);
        OffsetDateTime offset = OffsetDateTime.parse(
                "2026-11-05T09:30:00+07:00");

        DateTimeFormatter display = DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm", Locale.forLanguageTag("vi-VN"));
        DateTimeFormatter wire = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd'T'HH:mm:ssXXX");

        System.out.println("LocalDate = " + day);
        System.out.println("LocalTime = " + time);
        System.out.println("LocalDateTime = " + local);
        System.out.println("OffsetDateTime = " + wire.format(offset));
        System.out.println("ZonedDateTime = " + zoned);
        System.out.println("Instant = " + offset.toInstant());
        System.out.println("Display = " + display.format(zoned));

        DateTimeFormatter strictDate = DateTimeFormatter
                .ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);
        try {
            LocalDate.parse("31/02/2026", strictDate);
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid date: rejected");
        }
    }
}
```

Run:

```bash
javac JavaTimeFormatsDemo.java
java JavaTimeFormatsDemo
```

Output:

```text
LocalDate = 2026-11-05
LocalTime = 09:30
LocalDateTime = 2026-11-05T09:30
OffsetDateTime = 2026-11-05T09:30:00+07:00
ZonedDateTime = 2026-11-05T09:30+07:00[Asia/Ho_Chi_Minh]
Instant = 2026-11-05T02:30:00Z
Display = 05/11/2026 09:30
Invalid date: rejected
```

`display` only creates a human-readable string; **it does not shift the instant to another time**. `offset.toInstant()` is what converts to the UTC instant. Formatters are immutable, so they can be kept in `static final` fields and shared safely.

## 4. Offset, zone ID, instant, and time zone conversion

Suppose an appointment is entered as `2026-11-05T09:30:00+07:00`. Because the offset is known, this is `2026-11-05T02:30:00Z`. When displaying **the same instant** for Paris on that day, the local time is `03:30` at offset `+01:00`.

```java
OffsetDateTime appointment =
        OffsetDateTime.parse("2026-11-05T09:30:00+07:00");
Instant instant = appointment.toInstant();

ZonedDateTime inParis =
        instant.atZone(ZoneId.of("Europe/Paris"));
ZonedDateTime inSaigon =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

This is an **illustrative snippet**; it requires `java.time.*` imports and must be placed inside a method or initializer block. `inParis` and `inSaigon` have different displayed clock times, but their `toInstant()` values are equal.

Specifically:

- `withZoneSameInstant(otherZone)`: changes the displayed clock time to the new zone while **preserving the instant**.
- `withZoneSameLocal(otherZone)`: tries to preserve the wall-clock time, which **may change the instant**; the new zone may also adjust the time due to DST.
- `LocalDateTime.atZone(zone)`: **attaches a zone with its rules**, not converting from UTC; ensure the supplied zone is correct.
- `ZoneId.systemDefault()` depends on the host machine configuration; avoid relying on it in API communication or when storing schedules across multiple servers.
- `Locale` governs display language/conventions; `ZoneId` governs the applicable offset by location and instant. The two are independent.

When the business event is an instant that already occurred, store an `Instant` or timestamp with UTC semantics. When the business concept is a future appointment in local time, you usually need to store **local date-time + region zone ID** (and a DST handling policy); when confirming a single instant, store the computed instant or chosen offset as well. A fixed offset `+01:00` does not fully describe the historical/future rules of `Europe/Paris`.

## 5. Spring MVC binding strings to `java.time` with `@DateTimeFormat`

In Spring MVC, `@RequestParam`, `@PathVariable`, and fields bound from forms via `WebDataBinder` can use `@DateTimeFormat`; the annotation declares **how to parse and print the value**.

Depending on the data type, choose as follows:

- `LocalDate`: `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` when input is ISO `yyyy-MM-dd`.
- `LocalTime`: `@DateTimeFormat(pattern = "HH:mm")` when the UI sends `09:30`.
- `LocalDateTime`: `@DateTimeFormat(pattern = "yyyy-MM-dd'T'HH:mm")` when the UI sends `2026-11-05T09:30`.
- `OffsetDateTime` or `ZonedDateTime`: use `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)` when the client sends ISO date-time with an offset, and for `ZonedDateTime` it can also include the region ID in square brackets per Java's representation.
- `Instant`: prefer agreeing on a standard UTC string such as `2026-11-05T02:30:00Z` and verify how the system binds it; parse explicitly with `Instant.parse` if the endpoint design requires strict format control.

**Spring MVC controller class example**: the following `EventQueryController.java` file is valid in a Spring application with `spring-webmvc` and MVC configuration; it is not a standalone plain Java program with `main`.

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EventQueryController {
    @GetMapping("/events/preview")
    public String preview(
            @RequestParam("day")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate day,

            @RequestParam("time")
            @DateTimeFormat(pattern = "HH:mm")
            LocalTime time,

            @RequestParam("local")
            @DateTimeFormat(pattern = "yyyy-MM-dd'T'HH:mm")
            LocalDateTime local,

            @RequestParam("at")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            OffsetDateTime at) {

        return day + " | " + time + " | " + local
                + " | " + at.toInstant();
    }
}
```

Example HTTP GET to the running application (the `+` character in the offset must be URL-encoded as `%2B`):

```text
/events/preview?day=2026-11-05&time=09%3A30&local=2026-11-05T09%3A30&at=2026-11-05T09%3A30%3A00%2B07%3A00
```

Response body from the method (when the request binds successfully):

```text
2026-11-05 | 09:30 | 2026-11-05T09:30 | 2026-11-05T02:30:00Z
```

The query/form parameters in this example are **four independent values**; `local` does not automatically become an instant. `at` identifies an instant because the string includes an offset. Over HTTP, an unescaped `+` sign in `application/x-www-form-urlencoded` can be decoded into a space, causing a parse error.

### Model binding from an HTML form

Example form with three date/time/datetime-local fields:

```html
<input type="date" name="day">
<input type="time" name="time">
<input type="datetime-local" name="local">
```

Upon submission, browsers typically send `yyyy-MM-dd`, `HH:mm` (possibly with seconds), and `yyyy-MM-ddTHH:mm`. **`datetime-local` does not send an offset or zone**. The backend must also receive a business-determined zone, such as a `zoneId` field set to `Asia/Ho_Chi_Minh`, or look it up from the event configuration; never assume it is UTC time.

A field in the form model can be declared as:

```java
@DateTimeFormat(pattern = "yyyy-MM-dd'T'HH:mm")
private LocalDateTime local;
```

This is an **illustrative field snippet**; it must be placed inside a model with `java.time.LocalDateTime` and `org.springframework.format.annotation.DateTimeFormat` imports along with an appropriate property access mechanism (getters/setters or constructor binding).

## 6. `@DateTimeFormat`: `iso`, `pattern`, `style`, `fallbackPatterns`

`@DateTimeFormat` has three primary ways to declare a format:

| Attribute | Meaning | When to use |
| --- | --- | --- |
| `iso` | ISO patterns via `ISO.DATE`, `ISO.TIME`, `ISO.DATE_TIME` | Stable API contracts |
| `pattern` | Controlled pattern, e.g. `dd/MM/yyyy` | Forms/UI with an explicit format |
| `style` | Locale/JDK-dependent format, e.g. `"S-"` for short date | Language-adaptive UI |

If multiple attributes are declared, `pattern` takes precedence over `iso`, and `iso` takes precedence over `style`. You should **declare only one** based on intent. `fallbackPatterns` specifies additional formats tried when **parsing** fails; when **printing**, Spring still uses the primary format.

Example accepting ISO dates while supporting legacy user date input:

```java
@DateTimeFormat(
        iso = DateTimeFormat.ISO.DATE,
        fallbackPatterns = {"dd/MM/yyyy", "d/M/yyyy"})
private LocalDate day;
```

This is an **illustrative field snippet** inside a bean with appropriate imports. For instance, `05/11/2026` can be parsed via fallback, while standard printing remains ISO `2026-11-05`. Do not accept multiple input formats without clear rules, because `05/11/2026` can mean May 11 or November 5 across different systems.

**JDK 20+ note**: CLDR/locale-based style formats may change whitespace, AM/PM, and date/time representations across JDK releases. Spring recommends preferring ISO or application-controlled patterns, and using fallbacks only when legacy input compatibility is required.

In `@DateTimeFormat`'s Javadoc, the time zone rule applies to the legacy `java.util.Date` type: with `iso`, the formatter uses UTC; with `style`/`pattern`, it uses the JVM default time zone. **Do not misinterpret that statement as "all LocalDateTimes use UTC"**: `LocalDateTime` carries no zone. For `ZonedDateTime`/`OffsetDateTime`, strings with an offset or zone should accurately reflect business semantics.

## 7. Global formatting configuration in Spring

When many fields share one convention, you can configure `FormattingConversionService` instead of repeating the same pattern everywhere. `DateTimeFormatterRegistrar` registers formatters for `java.time` types, for example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class DateTimeMvcConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
```

This is a **Spring MVC configuration class**; it requires the corresponding dependencies and application context startup, and cannot be run with `java DateTimeMvcConfiguration`. `setUseIsoFormat(true)` selects standard ISO formatting instead of the registrar's default style. Whether this configuration is needed depends on the Spring version, MVC setup, and pre-registered formatters; **do not register duplicates just to follow a tutorial example**. For fields with specific contracts, `@DateTimeFormat` on the field/parameter is often clearer to read.

`DateTimeFormatterRegistrar` also supports `setDateFormatter(...)`, `setTimeFormatter(...)`, and `setDateTimeFormatter(...)` when a specific formatter is genuinely needed. Do not force every date/time type into a pattern requiring fields that type lacks: for example, `LocalDate` has no time, and `LocalDateTime` has no offset.

## 8. DST: a local date-time may not exist or may occur twice

The daylight saving time (DST) rules of a `ZoneId` make the `LocalDateTime → ZonedDateTime` mapping not always one-to-one:

- **Normal**: one valid offset.
- **Gap** (clocks spring forward): **no valid offset** for certain local times.
- **Overlap** (clocks fall back): **two valid offsets** for the same local time.

For `Europe/Paris` in 2026, 02:30 on **29/03/2026** falls in a *gap*; 02:30 on **25/10/2026** falls in an *overlap*. `atZone` has default behavior: it shifts gap times forward; for overlaps it picks the earlier of the two valid offsets. If scheduling business logic requires precision, you must check and apply an explicit rule rather than **silently accepting the default choice**.

Complete Java 17+ example `DstRulesDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;

public class DstRulesDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneRules rules = paris.getRules();

        LocalDateTime gap =
                LocalDateTime.of(2026, 3, 29, 2, 30);
        System.out.println("Gap offsets: " + rules.getValidOffsets(gap));
        System.out.println("Gap atZone: " + gap.atZone(paris));

        LocalDateTime overlap =
                LocalDateTime.of(2026, 10, 25, 2, 30);
        System.out.println("Overlap offsets: "
                + rules.getValidOffsets(overlap));

        ZonedDateTime earlier = overlap.atZone(paris);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
        System.out.println("Earlier instant: " + earlier.toInstant());
        System.out.println("Later instant: " + later.toInstant());
    }
}
```

```bash
javac DstRulesDemo.java
java DstRulesDemo
```

```text
Gap offsets: []
Gap atZone: 2026-03-29T03:30+02:00[Europe/Paris]
Overlap offsets: [+02:00, +01:00]
Earlier instant: 2026-10-25T00:30:00Z
Later instant: 2026-10-25T01:30:00Z
```

During an overlap, the two results are **exactly one hour apart** even though both read `02:30` on a clock in Paris. Therefore, you cannot derive a single exact instant from `LocalDateTime` and `ZoneId` without a policy for two-offset cases.

Example rejecting ambiguous times in business logic:

```java
var valid = zone.getRules().getValidOffsets(localDateTime);
if (valid.size() != 1) {
    throw new IllegalArgumentException(
            "Local date-time is ambiguous or invalid in this zone");
}
Instant instant = ZonedDateTime
        .ofStrict(localDateTime, valid.get(0), zone)
        .toInstant();
```

This is an **illustrative snippet**: `zone` is a valid `ZoneId`, `localDateTime` is a `LocalDateTime`; imports for `java.time` types are required. Depending on business rules, instead of rejecting an overlap you might ask the user to choose offset `+02:00` or `+01:00`; for a gap, you can suggest an alternative time.

## 9. Binding query/form vs JSON `@RequestBody`

This is a very common configuration mistake:

- `@DateTimeFormat` works in **Spring formatting/conversion when binding strings** (query params, paths, forms/models).
- JSON `@RequestBody` is usually handled by **Jackson `HttpMessageConverter`**; `@DateTimeFormat` is not the standard controller of the JSON serializer/deserializer.
- With Jackson, `java.time` types require Java Time module support, usually auto-configured by Spring Boot when the corresponding dependency is present. JSON formatting is governed by Jackson and Jackson configuration/annotations such as `@JsonFormat`, not automatically by MVC field formatters.

Example JSON payload passing an instant with an offset:

```json
{
  "name": "Daily sync",
  "day": "2026-11-05",
  "localTime": "09:30:00",
  "startsAt": "2026-11-05T09:30:00+07:00"
}
```

In the DTO, use `LocalDate`, `LocalTime`, and `OffsetDateTime` respectively when the API contract has these exact semantics. If the client sends `"2026-11-05T09:30:00"` when the DTO expects `OffsetDateTime`, **the missing offset** means the data is incomplete. Do not append `Z` to the end of the string unless the system has truly confirmed that the time is UTC.

Example of a Jackson-specific JSON display configuration (field snippet, not a standalone class):

```java
@com.fasterxml.jackson.annotation.JsonFormat(
        pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
private OffsetDateTime startsAt;
```

For REST systems, align JSON, query, form, and database rules around **the same date/time contract**; they may all use ISO format, though different layers do not necessarily use the same annotation.

## 10. Typical design workflow: user selects date, time, and zone

Suppose a scheduling application serves a branch in Paris. The form submits:

```text
date=2026-10-25
time=02:30
zoneId=Europe/Paris
```

**Data-correct workflow:**

1. Bind `date` into `LocalDate`, `time` into `LocalTime`, and `zoneId` into `ZoneId` (or look it up from a validated branch).
2. Construct `LocalDateTime.of(date, time)`. **There is no instant yet**.
3. Use `zone.getRules().getValidOffsets(local)` to check DST. In the example above, there are **two** valid offsets.
4. Apply policy: prompt for selection, reject ambiguous times, or pick an offset per product agreement. Once chosen, call `ZonedDateTime.ofStrict(local, chosenOffset, zone).toInstant()`.
5. Store the resolved instant for execution timing; keep the zone ID and local time if the local-time intent/schedule must be reproduced. When displaying to users elsewhere, convert the instant via `atZone(viewerZone)`.

If the system schedules **every Monday at 09:30 Paris time** across several months, storing only a recurring instant and adding 7 × 24 hours may fail to stay at 09:30 across DST transitions. That is a recurring schedule by **wall-clock time**, so it needs `LocalTime` + `ZoneId` + date recurrence rules, computing each instant for its respective date.

## 11. Common mistakes and how to avoid them

| Mistake | Why it is wrong | Solution |
| --- | --- | --- |
| Using `LocalDateTime` as a global timestamp | Lacks offset/zone to derive an instant | Choose `Instant`/`OffsetDateTime` or pair with `ZoneId` per business rules |
| Implicitly using `ZoneId.systemDefault()` | Results vary by server/container | Use an explicit zone from the contract or config |
| Treating `+07:00` as region `Asia/Ho_Chi_Minh` | Fixed offset lacks historical/DST rules | Keep region `ZoneId` if schedules follow local rules |
| Switching zones with `withZoneSameLocal` when intending the same instant | May change the instant's meaning | Use `withZoneSameInstant` |
| Writing `YYYY-MM-dd` or mixing up `MM`/`mm` | Produces wrong data near year-end or confuses month/minute | Use `uuuu`/`yyyy` and correct tokens |
| Forgetting to URL-encode `+` | `+07:00` may become ` 07:00` | Encode as `%2B` |
| Expecting `@DateTimeFormat` to format JSON | JSON is handled by converter/Jackson | Configure conventions in the right JSON layer |
| Assuming `datetime-local` carries a time zone | This control only sends local wall-clock time | Send the time zone region separately |
| Ignoring DST gaps/overlaps | Times may not exist or have two instants | Check `ZoneRules.getValidOffsets` |
| Sharing `SimpleDateFormat` across threads | Legacy formatter holds mutable state | Use immutable `DateTimeFormatter` |
| Parsing `"31/02"` without checking | Invalid calendar data | Use strict parser, test error cases |
| Relying on default locale/JDK `style` | Output can change across CLDR/JDK | Prefer ISO or controlled patterns |

In MVC, invalid type inputs typically produce binding/`typeMismatch` errors or HTTP 400 responses (depending on endpoint signature and exception handling). With `@ModelAttribute`, place `BindingResult` properly to read field errors; with JSON, parse errors occur in the HTTP message converter. Never handle errors by silently picking another time zone.

## 12. Practical testing

You should include at least the following scenarios for formatting and binding:

1. `LocalDate`: valid date `2024-02-29` and invalid date `2025-02-29`.
2. `LocalTime`: `09:30` vs `9:30 PM`, ensuring the pattern matches 24h/12h style.
3. `LocalDateTime`: input `2026-11-05T09:30` is not silently shifted to UTC.
4. `OffsetDateTime`: `2026-11-05T09:30+07:00` and `2026-11-05T02:30Z` must produce **the same instant**.
5. `ZonedDateTime`: test zone `Europe/Paris` at a gap and overlap; on overlap, do not guess the user's intended offset.
6. MVC query: verify `@DateTimeFormat` annotations, percent-encoded `+` characters; invalid inputs return proper errors.
7. JSON body: verify the Jackson module and expected format independently of query/form formatting configuration.
8. Multiple zones, locales, and environments: do not depend on the host machine's time zone; use `Clock.fixed(...)` when tests involve "now".

**Self-check:** If a form submits `2026-11-05T09:30`, can you immediately store `Instant.parse("2026-11-05T09:30Z")`? **No.** There is no evidence `09:30` is UTC; you must know the zone/offset and business policy first. If the form submits `2026-11-05T09:30+07:00`, it can be converted to `Instant` — because the offset determines the instant.

## References

- Spring Framework Reference — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework Reference — Configuring a Global Date and Time Format: https://docs.spring.io/spring-framework/reference/core/validation/format-configuring-formatting-globaldatetimeformat.html
- Spring Framework API — `DateTimeFormat`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html
- Spring Framework API — `DateTimeFormatterRegistrar`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/datetime/standard/DateTimeFormatterRegistrar.html
- Spring Framework wiki — Date and Time Formatting with JDK 20 and higher: https://github.com/spring-projects/spring-framework/wiki/Date-and-Time-Formatting-with-JDK-20-and-higher
- Java SE API — `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE API — `ZonedDateTime`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html
