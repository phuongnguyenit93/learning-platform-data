# @DateTimeFormat with ISO, pattern, and style in Spring Framework

> **Topic:** Spring Framework – validation-data-binding → Date and Time Formatting. This lesson focuses on how Spring converts date/time strings to Java types and formats them back using `@DateTimeFormat`.

## 1. Objectives

After this lesson, you can:

- Explain the role of `@DateTimeFormat` in Spring's data binding and formatting process.
- Distinguish the three configuration options `iso`, `pattern`, and `style`, choosing the right one for each data source.
- Apply the annotation to `@RequestParam`, `@ModelAttribute` fields, and `java.time` types.
- Predict valid parse results and recognize formatting, locale, time zone, and pattern errors.
- Know when `fallbackPatterns`, `BindingResult`, or other mechanisms such as JSON/Jackson are needed.

## 2. What problem does `@DateTimeFormat` solve?

HTTP query parameters, path variables, and form data usually arrive as **strings**. However, Java code needs `LocalDate`, `LocalTime`, `LocalDateTime`, or another temporal type. Spring uses `ConversionService` and `Formatter` implementations to perform conversion during binding. `@DateTimeFormat` declares the parsing (string → temporal object) and printing (object → string) rules for the annotated field or parameter.

For example, the client sends `date=05/11/2026`; a `LocalDate` field with `@DateTimeFormat(pattern = "dd/MM/yyyy")` is bound to **November 5, 2026**, not May 11. This rule belongs to the **data formatting/conversion** layer; it does not check whether a date is in the future. Business constraints such as `@Future`, `@Past`, or `@NotNull` belong to Bean Validation.

The annotation is in the package:

```java
import org.springframework.format.annotation.DateTimeFormat;
```

It can be placed on a field, method, or method parameter; in Spring MVC, common locations are `@RequestParam` parameters, `@PathVariable` parameters, and fields of a `@ModelAttribute` object. Supported types include `java.util.Date`, `Calendar`, `Long` representing an instant in milliseconds, as well as `java.time` temporal types such as `LocalDate`, `LocalTime`, `LocalDateTime`, and `OffsetDateTime` when supported by the corresponding formatter.

Typical processing flow:

```text
String from query/form/path
    → Spring MVC WebDataBinder
    → ConversionService / Formatter based on @DateTimeFormat
    → LocalDate, LocalDateTime, ...
    → controller / model
```

When a value cannot be parsed, binding creates a conversion error; the error reporting behavior depends on the annotation's location and how the controller handles it.

## 3. Three options: `iso`, `pattern`, `style`

| Attribute | Characteristics | Declaration example | Sample string | When to use |
| --- | --- | --- | --- | --- |
| `iso` | Uses Spring-supported ISO date/time standard; stable for machine-to-machine communication | `iso = DateTimeFormat.ISO.DATE` | `2026-11-05` | Query/form/API with a defined ISO format |
| `pattern` | Custom pattern with date/time pattern letters | `pattern = "dd/MM/yyyy"` | `05/11/2026` | Forms or systems with a clear input convention |
| `style` | Short/medium/long/full formatting by locale | `style = "M-"` | May be `Nov 5, 2026` with US English locale | UI input/output by language and region |

**Configure only one of the three main attributes per annotation.** If multiple attributes are accidentally declared, the precedence order in Spring is **`pattern` > `iso` > `style`**. Do not rely on this precedence to write confusing annotations. When nothing is specified, the default is style `"SS"` (short date, short time).

### 3.1. `iso`: standard format

```java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate startDate;

@DateTimeFormat(iso = DateTimeFormat.ISO.TIME)
private LocalTime startTime;

@DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
private LocalDateTime createdAt;
```

The three typical values of the `DateTimeFormat.ISO` enum are `DATE`, `TIME`, and `DATE_TIME`; `NONE` is the default value when ISO is not requested.

- `DATE`: date in `yyyy-MM-dd` form, e.g. `2026-11-05`.
- `TIME`: time in ISO form, e.g. `14:30:45` (component details depend on the target type and string).
- `DATE_TIME`: ISO date and time, e.g. `2026-11-05T14:30:45`, separated by the character `T`.

Choose the Java type matching the semantics: `LocalDate` for a date without time; `LocalDateTime` for a date-time **without time zone/offset**; `OffsetDateTime` or `ZonedDateTime` when the data actually contains an offset or zone. Do not assume `LocalDateTime` automatically knows which time zone the user is in.

### 3.2. `pattern`: specific pattern controlled by the application

```java
@DateTimeFormat(pattern = "dd/MM/yyyy")
private LocalDate birthday;

@DateTimeFormat(pattern = "dd/MM/yyyy HH:mm")
private LocalDateTime appointmentAt;
```

With the second pattern, `05/11/2026 14:30` means 14:30 on November 5, 2026. Patterns use the familiar symbols of Java date/time formatting; Spring selects a formatter suitable for the target type. Fixing a pattern keeps the UI and backend aligned, but the client must send the **exact** day/month/year order and separator.

Important pattern letters:

| Symbol | Meaning | Common confusion to avoid |
| --- | --- | --- |
| `dd` | Day of month, two digits | `DD` is day of year |
| `MM` | Month, two digits | `mm` is minute |
| `yyyy` | Calendar year | `YYYY` is week-based year, which can differ near New Year's |
| `HH` | Hour 00–23 | `hh` is hour 01–12, usually needs `a` (AM/PM) |
| `mm` | Minute | `MM` is month |
| `ss` | Second | Only include if input contains seconds |

Valid example: `dd/MM/yyyy HH:mm`. Error-prone example: `dd/mm/YYYY HH:MM` due to swapping month/minute and using week-based year. Do not apply a date-time pattern to a `LocalDate` type that only stores a date.

### 3.3. `style`: locale-based formatting

`style` is a **two-character** string. The first character controls the date, and the second character controls the time:

- `S` = short, `M` = medium, `L` = long, `F` = full.
- `-` = omit that component: `"M-"` is medium date only, `"-S"` is short time only, `"SS"` includes both short date and short time.

```java
@DateTimeFormat(style = "M-")
private LocalDate day;

@DateTimeFormat(style = "-S")
private LocalTime time;
```

With `style`, **there is no single fixed input string across all machines and users**. Results are affected by locale (e.g., `en_US` differs from `vi_VN`) and JDK data/version. Spring warns that locale formatting can change across JDKs, especially starting from JDK 20. If the API contract needs stability, prefer `iso` or a concrete `pattern`; only choose `style` when locale-sensitive communication is intentional.

## 4. Runnable Spring MVC example

The example below is for a **Spring Boot project with `spring-boot-starter-web` and Java 17+**. Place the entire code in `src/main/java/com/example/dates/DateTimeFormatDemoApplication.java`; this is a complete Java file for a Spring Boot application (run with `./gradlew bootRun` or the corresponding Spring Boot run command for your project).

```java
package com.example.dates;

import java.time.LocalDate;
import java.time.LocalDateTime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DateTimeFormatDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DateTimeFormatDemoApplication.class, args);
    }

    @RestController
    @RequestMapping("/dates")
    public static class DateController {

        @GetMapping("/iso")
        public String iso(
                @RequestParam("date")
                @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date) {
            return date.toString();
        }

        @GetMapping("/custom")
        public String custom(
                @RequestParam("date")
                @DateTimeFormat(pattern = "dd/MM/yyyy") LocalDate date) {
            return date.toString();
        }

        @GetMapping("/time")
        public String time(
                @RequestParam("at")
                @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
                LocalDateTime at) {
            return at.toString();
        }

        @GetMapping("/style")
        public String style(
                @RequestParam("date")
                @DateTimeFormat(style = "M-") LocalDate date) {
            return date.toString();
        }

        @PostMapping("/form")
        public String form(
                @ModelAttribute ScheduleForm form, BindingResult result) {
            if (result.hasErrors()) {
                return "invalid-date";
            }
            return form.getStartDate().toString();
        }
    }

    public static class ScheduleForm {

        @DateTimeFormat(pattern = "dd/MM/yyyy")
        private LocalDate startDate;

        public LocalDate getStartDate() {
            return startDate;
        }

        public void setStartDate(LocalDate startDate) {
            this.startDate = startDate;
        }
    }
}
```

Use the following requests after the server is running on port `8080`:

```bash
curl -G --data-urlencode "date=2026-11-05" http://localhost:8080/dates/iso
curl -G --data-urlencode "date=05/11/2026" http://localhost:8080/dates/custom
curl -G --data-urlencode "at=2026-11-05T14:30:45" http://localhost:8080/dates/time
curl -X POST --data-urlencode "startDate=05/11/2026" http://localhost:8080/dates/form
```

When running with standard Spring MVC configuration, the response bodies of the four requests above are respectively:

```text
2026-11-05
2026-11-05
2026-11-05T14:30:45
2026-11-05
```

**Explanation:** `@DateTimeFormat` determines how input strings are **read**. In the example, `return date.toString()` is `LocalDate`'s Java method, so the body displays ISO format even when input uses `dd/MM/yyyy`. Do not mistake that result for `@DateTimeFormat` automatically controlling JSON or every response string. The `/style` method can be called after determining the date string for the active locale; because a fixed input string cannot be guaranteed across environments, the example does not assert a literal applicable to every locale.

In `/form`, Spring binds the `startDate` property of `ScheduleForm` using the field annotation. `BindingResult` is placed **immediately after** `@ModelAttribute` to capture binding errors (such as a wrong pattern) instead of being handled as an independent argument.

## 5. Distinguishing parse errors from validation errors

Suppose the controller receives `@RequestParam("date") @DateTimeFormat(iso = ISO.DATE) LocalDate date`:

| Input | What happens |
| --- | --- |
| `2026-11-05` | Parsed into `LocalDate.of(2026, 11, 5)` |
| `05/11/2026` | Invalid ISO DATE format: conversion error |
| `2026-02-30` | Non-existent date: parse error |
| Omitting `date` parameter | By default `@RequestParam` requires the parameter: missing parameter error |

In a typical Spring MVC application, a conversion error or missing required `@RequestParam` results in an HTTP 400 response (unless the application configures custom error handling). With a `@ModelAttribute` object, field conversion errors can be inspected via `BindingResult`. To validate future dates or requirements beyond syntax, use the appropriate Bean Validation annotations and trigger validation according to the application's needs.

If users must enter multiple legacy formats, you can allow **fallback when parsing**:

```java
@DateTimeFormat(
    iso = DateTimeFormat.ISO.DATE,
    fallbackPatterns = {"dd/MM/yyyy", "M/d/yyyy"}
)
private LocalDate dueDate;
```

`fallbackPatterns` (Spring Framework 5.3.5+) tries fallback patterns when the primary format fails to parse; **printing still uses the primary format** (`ISO.DATE` here). Do not overuse fallbacks if formats can be ambiguous—for example, `03/04/2026` could mean March 4 or April 3 depending on convention.

## 6. Locale, time zone, and data type

These three concepts are distinct:

- **Locale** determines text conventions and language for `style`-based formats; for example, month names and component order can differ.
- **Time zone / offset** determines how an absolute instant is represented in local time. `LocalDateTime` does not store an offset; `OffsetDateTime` has an offset; `Instant` represents a UTC point on the timeline.
- **Pattern** determines the string shape. The same pattern does not automatically add a time zone to a type without a time zone.

Specifically for **`java.util.Date`** in `@DateTimeFormat`, Spring documentation states that `iso` uses **UTC**, while `pattern` and `style` use the JVM's default time zone when formatting. Thus, a `Date` holding the same instant can display a different date/time across servers with different time zones. For consistency, configure the time zone explicitly, such as `-Duser.timezone=UTC` if appropriate for the whole application; do not extrapolate this `Date` rule to the behavior of all `java.time` types.

When data contains an offset like `2026-11-05T14:30:45+07:00`, consider `OffsetDateTime` and the appropriate ISO formatter. When only a birth date, booking date, or due date is needed, `LocalDate` is usually clearer than a `Date` carrying an unnecessary time of day and time zone.

## 7. How does `@DateTimeFormat` differ from `@JsonFormat`?

`@DateTimeFormat` participates in **Spring formatting/binding** for string values in query/path/form/model. With `@RequestBody` containing JSON, the request body is usually deserialized by **Jackson `HttpMessageConverter`**, not going through the same binding pipeline as form parameters. Therefore, placing `@DateTimeFormat` on a field does not automatically make Jackson accept JSON like `"05/11/2026"` or serialize JSON with that pattern.

For example, requirements for custom-formatted JSON typically use Jackson annotations/configuration such as:

```java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;

public class CreateEventJson {
    @JsonFormat(pattern = "dd/MM/yyyy")
    public LocalDate startDate;
}
```

This snippet only illustrates **Jackson JSON configuration**, not a standalone application; Jackson support for `java.time` types is required (normally configured in Spring Boot projects using Jackson). If you can design the API from scratch, choose a consistent ISO date/time format for both JSON and queries rather than creating multiple ambiguous date patterns.

## 8. Verifying patterns with plain Java

This is a **Spring-independent** Java 17+ example to verify exactly how `dd/MM/yyyy` represents a date. Save it in `PatternCheck.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public class PatternCheck {
    public static void main(String[] args) {
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd/MM/yyyy");
        LocalDate day = LocalDate.parse("05/11/2026", formatter);
        System.out.println(day);
        System.out.println(day.format(formatter));
    }
}
```

```bash
javac PatternCheck.java
java PatternCheck
```

Stdout:

```text
2026-11-05
05/11/2026
```

This example verifies date formatting in Java; `@DateTimeFormat` integration must run inside Spring `ConversionService`/MVC as shown in section 4.

## 9. Common mistakes and fixes

1. **Using `MM` instead of `mm` or `yyyy` instead of `YYYY` improperly.** Check each pattern symbol and test dates near New Year's.
2. **Using `style` for a fixed API contract.** Locale/JDK can alter the format; use `iso` or an explicit `pattern`.
3. **Sending `dd/MM/yyyy` to an endpoint expecting `ISO.DATE`.** The two formats differ; align with the client or add fallbacks if the contract allows.
4. **Confusing `LocalDateTime` with a time-zoned instant.** If an offset/zone is needed, choose the appropriate type and standardize time zones when storing.
5. **Assuming the annotation performs business validation.** `@DateTimeFormat` only handles representation/parsing; apply validation separately.
6. **Expecting the annotation on a DTO to change JSON `@RequestBody`.** Check Jackson's mechanism and `@JsonFormat`.
7. **Ignoring binding errors.** With a form DTO, place `BindingResult` immediately after `@ModelAttribute` and return specific errors to the user.
8. **Using `fallbackPatterns` for ambiguous formats.** Only accept multiple formats when there is a priority order and a consistent data convention.

## 10. Self-practice

**Exercise 1.** An endpoint receives `?birthday=20/09/2000` into a `LocalDate`. Write the appropriate annotation.

```java
@RequestParam("birthday")
@DateTimeFormat(pattern = "dd/MM/yyyy") LocalDate birthday
```

**Exercise 2.** An endpoint receives `?due=2026-12-31` into a `LocalDate` using a stable standard. Choose `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`.

**Exercise 3.** Why should you not write `@DateTimeFormat(pattern = "dd/mm/YYYY")` if users enter day/month/year? Because `mm` is minutes and `YYYY` is week-based year; `dd/MM/yyyy` is required.

**Exercise 4.** A form using `style = "M-"` works on machine A but fails on machine B with legacy date strings. Check the locale, JDK version, and actual pattern; if stable data is needed, switch to ISO or an explicit pattern, or add a fallback only when input conventions allow.

## 11. Takeaways to apply

- **ISO** for communication requiring consistency; **pattern** for forms with an agreed syntax; **style** for locale-dependent UI.
- Choose only **one** of the three options per annotation. On conflict: `pattern > iso > style`.
- Use the right data type, distinguishing plain dates, date-times without offset, and instants with offset.
- Test valid inputs, invalid formats, non-existent dates, different locales, and binding errors.
- `fallbackPatterns` only adds **parse** options; it does not change the **print** format.

### References

- Spring Framework — `@DateTimeFormat` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html
- Spring Framework — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring MVC — `@ModelAttribute` and data binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
