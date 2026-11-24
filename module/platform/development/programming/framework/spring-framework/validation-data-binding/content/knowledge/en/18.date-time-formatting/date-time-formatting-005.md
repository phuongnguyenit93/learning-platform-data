# Configuring Global Date and Time Formatting in Spring Framework

## 1. The problem and desired outcome

An application has many controllers, forms, and URL parameters containing dates and times. If every field must declare `@DateTimeFormat` individually, formats easily become inconsistent: one place accepts `2026-11-05`, another accepts `05/11/2026`, and another accepts `11/05/2026`. Spring Framework lets you **centrally register date/time formatters** in a `FormatterRegistry` to apply default parse and print rules for matching data types.

For example, with a consistent ISO rule:

| Java type | Sample input string | Result after parsing |
| --- | --- | --- |
| `LocalDate` | `2026-11-05` | November 5, 2026 |
| `LocalTime` | `14:30:45` | 14 hours 30 minutes 45 seconds |
| `LocalDateTime` | `2026-11-05T14:30:45` | Local date and time, no time zone attached |
| `OffsetDateTime` | `2026-11-05T14:30:45+07:00` | Date and time with UTC offset +07:00 |

**Global configuration** means default rules inside the **specific conversion service/formatter registry** being configured; it does not mean every part of the application automatically uses the same format. You must identify the registration site and data pipeline: Spring MVC, Spring WebFlux, plain Java conversions, JSON payloads, or `application.properties` configuration.

Objectives after this lesson:

1. Understand `Formatter` parse/print and the relationship between `FormattingConversionService`, `FormatterRegistry`, and `DateTimeFormatterRegistrar`.
2. Register ISO or custom patterns **once** for Spring MVC.
3. Know how to configure quickly using Spring Boot's `spring.mvc.format.*` properties when appropriate.
4. Distinguish `java.time` from `java.util.Date`; global formatting from `@DateTimeFormat`; and form/query from JSON.
5. Test valid inputs, malformed formats, leap years, locales, and offsets/time zones.

## 2. Where does Spring apply formatters?

For text values at the application boundary, Spring needs two conversion directions:

~~~text
HTTP query / path variable / form field
              |
      string from client
              |
       Formatter.parse(...)
              |
    LocalDate / LocalTime / ...
              |
    controller, bean property
              |
       Formatter.print(...)
              |
       display string
~~~

`Formatter<T>` consists of `Parser<T>` and `Printer<T>`. It accepts a `Locale`, because textual date/time formats (month names, AM/PM, etc.) can depend on language/region. `FormattingConversionService` combines formatters with the `Converter` system, and `FormatterRegistry` is the interface for registering these rules. Registering by data type establishes shared defaults; `@DateTimeFormat` on a field or parameter selects a specific rule.

Common classes:

- `DateTimeFormatterRegistrar`, package `org.springframework.format.datetime.standard`: registers formatters for `java.time` types such as `LocalDate`, `LocalTime`, `LocalDateTime`, and offset types.
- `DateFormatterRegistrar`, package `org.springframework.format.datetime`: serves legacy `Date`/`Calendar` types and configures `DateFormatter`; does not replace the `java.time` registrar.
- `WebMvcConfigurer.addFormatters(FormatterRegistry)`: hooks registrations into **Spring MVC**'s binding/formatting infrastructure.
- `WebFluxConfigurer.addFormatters(FormatterRegistry)`: the corresponding extension point in **Spring WebFlux**.
- `DefaultFormattingConversionService`: convenient when a standalone `ConversionService` is needed outside MVC requests.

A `String → LocalDate` converter can handle parsing, but `Formatter` is more convenient when both printing back to `String` and `Locale` handling are needed. For date/time handling, prefer the built-in formatter APIs over repeating `LocalDate.parse(...)` across controllers.

## 3. Choosing a unified standard before configuring

No single text format is optimal for every interface. Choose based on data type and client contract:

| Context | Typically suitable format | Notes |
| --- | --- | --- |
| `<input type="date">` in HTML | `yyyy-MM-dd` | Submitted value follows the HTML spec; how the browser *displays* it can vary by language. |
| `<input type="time">` | `HH:mm` or `HH:mm:ss` | Clarify whether seconds are sent. |
| `<input type="datetime-local">` | `yyyy-MM-dd'T'HH:mm`, optionally with seconds | Carries no offset or time zone name. |
| Internal queries/forms needing stable machine reading | ISO-8601 | Avoids regional day/month confusion. |
| Manual entry forms for Vietnamese users | `dd/MM/yyyy` | Requires guidance and validation for non-existent dates. |
| Transaction timestamps across systems | ISO-8601 with offset or UTC | Use `OffsetDateTime`/`Instant` appropriately; do not treat `LocalDateTime` as a global instant. |

`LocalDate` has only a date; `LocalTime` has only a time; `LocalDateTime` is a date-time *without a time zone/offset*. `OffsetDateTime` has a UTC offset; `ZonedDateTime` has a `ZoneId`. The two strings `2026-11-05T14:30:45` and `2026-11-05T14:30:45+07:00` carry different meanings. A global formatter must preserve this distinction.

When exchanging instants across multiple time zones, usually exchange strings with an offset or UTC; selecting a display time zone belongs at the UI/application boundary. Do not bake `ZoneId.systemDefault()` into every parse call without an explicit requirement, since each server may have a different time zone.

## 4. Recommended approach in Spring MVC: register ISO once

In a Spring MVC application, write a configuration class picked up by component scanning:

~~~java
package demo.web;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class GlobalDateTimeWebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
~~~

This is a **Spring MVC integration snippet**, requiring `spring-webmvc` and a web application. It is not a standalone Java program runnable with `java GlobalDateTimeWebConfig`.

Mechanism:

1. Spring MVC initializes the conversion service used for web binding.
2. `WebMvcConfigurer.addFormatters` lets you add formatters to that registry.
3. `DateTimeFormatterRegistrar` registers `java.time` formatters configured for ISO.
4. When binding a parameter or user-submitted string to a matching `LocalDate`, `LocalTime`, or `LocalDateTime` property, Spring uses this config unless a more specific field/parameter rule applies.

You do not need `@DateTimeFormat` on every parameter when all follow one convention. Spring MVC already comes with many default formatters; the code above explicitly sets a shared ISO rule for the date/time group.

Example controller using the default format:

~~~java
package demo.web;

import java.time.LocalDate;
import java.time.LocalTime;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ScheduleController {

    @GetMapping("/schedule")
    public String schedule(
            @RequestParam LocalDate date,
            @RequestParam LocalTime time) {
        return date + " " + time;
    }

    @GetMapping("/schedule/legacy-input")
    public String legacyInput(
            @RequestParam
            @DateTimeFormat(pattern = "dd/MM/yyyy") LocalDate date) {
        return date.toString();
    }
}
~~~

This is also an **integration snippet** in the same MVC application. Once ISO is registered above:

~~~http
GET /schedule?date=2026-11-05&time=14%3A30%3A45
~~~

The returned response body is:

~~~text
2026-11-05 14:30:45
~~~

The second endpoint demonstrates a per-annotation exception:

~~~http
GET /schedule/legacy-input?date=05%2F11%2F2026
~~~

Body:

~~~text
2026-11-05
~~~

`@DateTimeFormat(pattern = "dd/MM/yyyy")` applies specifically to that parameter, while unannotated locations continue using the global registry. Printing `date.toString()` in the controller comes from Java's `LocalDate`, not proof that the global formatter handled printing; to verify printing, use `ConversionService.convert(value, String.class)` or real data binding/views.

In Spring Boot, adding a `WebMvcConfigurer` like this preserves MVC auto-configuration. Avoid adding `@EnableWebMvc` just to configure formatters, as that annotation requires managing much of MVC manually and can disable Boot's auto-configurations.

## 5. Choosing custom patterns instead of ISO

If UI rules require entering `05/11/2026` and `14:30:45`, use the setters on `DateTimeFormatterRegistrar`:

~~~java
package demo.web;

import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CustomDateTimeWebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();

        registrar.setDateFormatter(
            DateTimeFormatter.ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT));

        registrar.setTimeFormatter(
            DateTimeFormatter.ofPattern("HH:mm:ss")
                .withResolverStyle(ResolverStyle.STRICT));

        registrar.setDateTimeFormatter(
            DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm:ss")
                .withResolverStyle(ResolverStyle.STRICT));

        registrar.registerFormatters(registry);
    }
}
~~~

**Use either `GlobalDateTimeWebConfig` or `CustomDateTimeWebConfig`** as the global policy for that group of types. Avoid registering two overlapping sets of rules for the same target types and relying on implicit ordering.

Explanation:

- `setDateFormatter(...)` affects formatting for `LocalDate`.
- `setTimeFormatter(...)` applies to `LocalTime` **and `OffsetTime`**.
- `setDateTimeFormatter(...)` applies to `LocalDateTime`, `OffsetDateTime`, and `ZonedDateTime`.
- An explicit formatter setter takes precedence over `setUseIsoFormat(true)` or the default style for its type group. Therefore, do not mix them without specifying the exact behavior.
- `ResolverStyle.STRICT` rejects invalid calendar dates. In `DateTimeFormatter`, `uuuu` is the proleptic year, suitable for strict parsing of modern ISO dates; `yyyy` represents year-of-era and may require era info in strict mode.

**Important warning about offsets:** The patterns `HH:mm:ss` and `dd/MM/uuuu HH:mm:ss` **do not contain an offset**. They suit `LocalTime` and `LocalDateTime` but can cause parse failures for `OffsetTime`/`OffsetDateTime`/`ZonedDateTime` because required offset/time zone info is missing. If the application uses those types, prefer offset-aware ISO or register per-type policies; do not assume a local pattern suffices for every temporal type.

If you need a strict rule that "clients send ISO only" with no exceptions, `setUseIsoFormat(true)` in section 4 is clearer, safer, and aligns with standard HTML inputs.

## 6. Spring Boot: global configuration via application.properties

With Spring Boot MVC, you can declare default formats without writing a Java configuration class:

~~~properties
# application.properties
spring.mvc.format.date=dd/MM/yyyy
spring.mvc.format.time=HH:mm:ss
spring.mvc.format.date-time=yyyy-MM-dd HH:mm:ss
~~~

Or in `application.yml`:

~~~yaml
spring:
  mvc:
    format:
      date: "dd/MM/yyyy"
      time: "HH:mm:ss"
      date-time: "yyyy-MM-dd HH:mm:ss"
~~~

These properties define **formatting for Spring MVC**:

| Property | Typical target types |
| --- | --- |
| `spring.mvc.format.date` | `java.util.Date` and `LocalDate` |
| `spring.mvc.format.time` | `LocalTime` and `OffsetTime` |
| `spring.mvc.format.date-time` | `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime` |

In the properties snippet above, `date-time` is chosen for date-time data **without an offset**, so it is insufficient for offset/zoned types when parsing corresponding timestamps; design separately if those are used. For APIs exchanging time-zoned values, an explicit ISO rule is more convenient.

Why does the Boot example use `yyyy` while the strict `DateTimeFormatter` code above uses `uuuu`? The `spring.mvc.format.date` property also serves `java.util.Date` via `java.text`, where `yyyy` is the normal year; `DateTimeFormatter` with `ResolverStyle.STRICT` has different semantics as explained in section 5. **Do not blindly replace `yyyy` with `uuuu` in every parser**, because `SimpleDateFormat` gives `u` a different meaning.

Property configuration is a quick option when one pattern set suffices and the application already uses Spring Boot auto-configuration. `WebMvcConfigurer` fits better when you need a special `DateTimeFormatter`, `ResolverStyle`, type-specific rules, or custom formatters. If you both set properties and register formatters for the same types, test which rule takes effect instead of assuming a universal precedence across versions and setups.

**Distinguishing conversion services:** Spring MVC has its own conversion service, which is not necessarily the service used to read and bind `application.properties`/`@ConfigurationProperties`. Thus, changing `spring.mvc.format.*` does not change how Spring Boot parses environment configuration properties.

## 7. Runnable Java 17+: a shared formatting service

We can verify exact parse/print behavior with a small Spring Core program **without a web server**. The example uses **Java 17** and **Spring Framework 6.2.19**; it runs independently of the MVC sections above.

Structure:

~~~text
global-date-time/
├── pom.xml
└── src/
    ├── main/java/demo/GlobalDateTimeDemo.java
    └── test/java/demo/GlobalDateTimeDemoTest.java
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>global-date-time</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/GlobalDateTimeDemo.java`:

~~~java
package demo;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.format.support.FormattingConversionService;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;

public class GlobalDateTimeDemo {

    static FormattingConversionService buildService() {
        // Do not load default formatters:
        // explicitly register a shared ISO formatting policy.
        var service = new DefaultFormattingConversionService(false);

        var registrar = new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(service);
        return service;
    }

    public static void main(String[] args) {
        var conversionService = buildService();

        LocalDate date =
            conversionService.convert("2026-11-05", LocalDate.class);
        LocalTime time =
            conversionService.convert("14:30:45", LocalTime.class);
        LocalDateTime dateTime =
            conversionService.convert(
                "2026-11-05T14:30:45", LocalDateTime.class);

        System.out.println("date=" + date);
        System.out.println("time=" + time);
        System.out.println("dateTime=" + dateTime);

        String printed =
            conversionService.convert(dateTime, String.class);
        System.out.println("printed=" + printed);
    }
}
~~~

Run in the directory containing `pom.xml` (requires JDK 17+, Maven, and dependency download access on first run):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.GlobalDateTimeDemo
~~~

Stdout produced by the program (excluding any Maven-specific messages):

~~~text
date=2026-11-05
time=14:30:45
dateTime=2026-11-05T14:30:45
printed=2026-11-05T14:30:45
~~~

Explanation:

1. `DefaultFormattingConversionService(false)` does not auto-register **default formatters**; we intentionally add the ISO registrar. It still retains the underlying converter system.
2. `convert(String, LocalDate.class)`/`convert(String, LocalTime.class)`/`convert(String, LocalDateTime.class)` verify the parsing direction.
3. `convert(dateTime, String.class)` verifies the printing direction, which differs from calling `dateTime.toString()` directly.
4. No pattern is needed at individual call sites. All share the single registered service.
5. Configuring a service like this **only affects conversions routed through that exact service**. Do not assume an arbitrary bean in Spring Core automatically replaces Spring MVC's service.

If using the service as a Spring bean for core formatting outside web requests, you can declare `@Bean FormattingConversionService` inside `@Configuration`; verify which components actually inject that bean. If disabling default formatters with `false` in a large application, re-register other needed default formatters such as `@NumberFormat` support. Spring MVC already provides extension hooks, so there is no need to replace the entire service just for this task.

## 8. Testing parsing, printing, and invalid inputs

Create `src/test/java/demo/GlobalDateTimeDemoTest.java`:

~~~java
package demo;

import java.time.LocalDate;
import java.time.LocalDateTime;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.ConversionFailedException;

import static org.junit.jupiter.api.Assertions.*;

class GlobalDateTimeDemoTest {

    @Test
    void parsesAndPrintsDateWithGlobalIsoFormat() {
        var service = GlobalDateTimeDemo.buildService();

        LocalDate date = service.convert("2026-11-05", LocalDate.class);

        assertEquals(LocalDate.of(2026, 11, 5), date);
        assertEquals("2026-11-05", service.convert(date, String.class));
    }

    @Test
    void parsesDateTimeWithTimeSeparatorT() {
        var service = GlobalDateTimeDemo.buildService();

        var result =
            service.convert("2026-11-05T14:30:45", LocalDateTime.class);

        assertEquals(LocalDateTime.of(2026, 11, 5, 14, 30, 45),
                     result);
    }

    @Test
    void rejectsImpossibleCalendarDate() {
        var service = GlobalDateTimeDemo.buildService();

        assertThrows(
            ConversionFailedException.class,
            () -> service.convert("2026-02-30", LocalDate.class)
        );
    }

    @Test
    void rejectsWrongDateSyntax() {
        var service = GlobalDateTimeDemo.buildService();

        assertThrows(
            ConversionFailedException.class,
            () -> service.convert("05/11/2026", LocalDate.class)
        );
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Maven Surefire should report **4 tests run, 0 errors/0 failures** when configuration and dependencies are intact. These are `FormattingConversionService`-level integration tests: a Spring-style formatter set is registered in the service, whereas real HTTP handling should also be covered by controller/MockMvc tests in an MVC app.

Do not write a test that only verifies `LocalDate.parse("2026-11-05")` and conclude Spring configuration is right: such a test bypasses the formatter registry even though Java parses it.

If changing the policy from ISO to `dd/MM/yyyy`, update test data, expected outputs, API consumers, and contract documentation together. Both "valid date in wrong format" and "valid syntax for non-existent calendar date" must be tested.

## 9. Configuring legacy java.util.Date and Calendar

`DateTimeFormatterRegistrar` targets `java.time`. If the project still uses `java.util.Date`/`Calendar`, configure `DateFormatterRegistrar` separately.

Illustrative snippet for adding inside `addFormatters`, with corresponding imports:

~~~java
import java.util.TimeZone;

import org.springframework.format.datetime.DateFormatter;
import org.springframework.format.datetime.DateFormatterRegistrar;

// Inside addFormatters(FormatterRegistry registry):
DateFormatter dateFormatter = new DateFormatter("dd/MM/yyyy");
dateFormatter.setLenient(false);
dateFormatter.setTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));

DateFormatterRegistrar legacyRegistrar = new DateFormatterRegistrar();
legacyRegistrar.setFormatter(dateFormatter);
legacyRegistrar.registerFormatters(registry);
~~~

`setFormatter` is essential: without setting a specific formatter, the registrar does not add a global formatter for unannotated `Date`/`Calendar` fields. This registration does not alter `LocalDate` configuration in `DateTimeFormatterRegistrar`.

Note that `Date` represents an **instant/timestamp**, while calendar day/month representation during parsing/printing depends on time zone. `LocalDate` represents only a calendar date and does not depend on time zone in the same way. When converting between them, specify the time zone rule to avoid "off-by-one-day" bugs on servers in different time zones.

New projects are generally easier to maintain with `java.time` types such as `LocalDate`, `LocalDateTime`, and `Instant`. Use legacy formatters only when legacy properties truly require compatibility.

## 10. Scope of impact: Form, URL, JSON, and application config

A common implementation mistake is defining "global" too broadly. Temporal data flows through different layers:

| Data flow | Primary mechanism | Appropriate configuration |
| --- | --- | --- |
| `@RequestParam LocalDate` | Spring MVC argument binding | `WebMvcConfigurer.addFormatters` or `spring.mvc.format.date` |
| `@PathVariable LocalDate` | Spring MVC type conversion | MVC formatter registry; watch URL encoding |
| `@ModelAttribute` with dates | `WebDataBinder` / conversion/formatting | MVC registry and/or `@DateTimeFormat` on field |
| HTML form input | Browser-defined submitted value, via binder | Align submitted format with MVC formatter |
| `@RequestBody` JSON | Jackson or JSON codec/message converter | Configure serializer/deserializer, `@JsonFormat`, or Jackson modules |
| `@ResponseBody` returning JSON object | Jackson or JSON codec | Configure JSON serialization |
| `@ConfigurationProperties` | Spring Boot application property binding | Application conversion service, does not use MVC registry by default |
| Plain Java logic calling `ConversionService` | Injected/constructed conversion service | Register formatters on that exact instance |
| Spring WebFlux web binding | WebFlux formatter registry | `WebFluxConfigurer.addFormatters` |

**Spring MVC's global formatter does not automatically change JSON formatting.** For example:

~~~java
record Appointment(LocalDate date, LocalDateTime startAt) {}
~~~

If a controller returns `Appointment` as JSON, whether the JSON contains `"2026-11-05"` and `"2026-11-05T14:30:45"` or another representation is determined by Jackson/modules/JSON config, not merely by `DateTimeFormatterRegistrar` in MVC.

Similarly, Jackson's annotation:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;

record DatePayload(
    @JsonFormat(pattern = "dd/MM/yyyy") LocalDate date) {}
~~~

This is an illustrative snippet for JSON with Jackson dependencies, **not a standalone program**. `@JsonFormat` handles JSON serialization/deserialization on the target type/property; `@DateTimeFormat` handles Spring field formatting and type conversion.

In applications using both query parameters and JSON, test **both paths** to make sure each uses its documented standard.

## 11. @DateTimeFormat is a local exception, not a global replacement

Suppose most forms use ISO, while one manual-entry screen needs `dd/MM/yyyy`. Keep global ISO and place the annotation only where needed:

~~~java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public class SearchForm {
    @DateTimeFormat(pattern = "dd/MM/yyyy")
    private LocalDate fromDate;

    public LocalDate getFromDate() {
        return fromDate;
    }

    public void setFromDate(LocalDate fromDate) {
        this.fromDate = fromDate;
    }
}
~~~

This is a bean for MVC binding, not a standalone program. On `fromDate`, `@DateTimeFormat` declares how that field is parsed/printed; unannotated fields still follow the global rule for their type.

Three common ways to write the annotation:

- `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`: uses the ISO date standard.
- `@DateTimeFormat(pattern = "dd/MM/yyyy")`: explicit pattern on the field.
- `@DateTimeFormat(style = "S-")`: short style, dependent on locale/JDK and suited for localized UIs.

Avoid assuming default styles are identical across every JDK version and locale. Spring Framework notes that style-based formats can change across Java runtimes (especially from JDK 20 onward), so for machine-readable protocols prefer ISO or an explicit pattern. The annotation also supports `fallbackPatterns` when backward compatibility with legacy input formats is needed; fallbacks apply to **parsing**, while printing still uses the primary format.

Place the annotation deliberately for exceptions; do not put `@DateTimeFormat` on every field simply for lack of a shared configuration.

## 12. Locale, time zone, and format accuracy

### Locale does not mean time zone

`Locale` selects language/region for display patterns such as month or weekday names; `TimeZone`/`ZoneId` defines the relationship between an instant and wall-clock time in a region. The two concepts are distinct. You can use `Locale.forLanguageTag("vi-VN")` while choosing the `UTC` time zone; locale does not shift data to UTC+7.

`DateTimeFormatter.ofPattern("dd/MM/uuuu")` uses fixed numeric tokens so strings vary little by locale; localized formatters like `ofLocalizedDate(FormatStyle.SHORT)` can vary across locales and change with runtime locale data.

For `Instant`, `OffsetDateTime`, or `ZonedDateTime`, to display an instant in Vietnam time you must specify the zone, for example:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

Instant instant = Instant.parse("2026-11-05T07:30:45Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

String display = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm:ss")
        .withZone(zone)
        .format(instant);

// display = "05/11/2026 14:30:45"
~~~

This snippet can be placed in a Java method and run with JDK 17 (with the imports shown); it illustrates **formatting an instant for a zone**. Configuring a pattern with only `dd/MM/uuuu` on `LocalDate` cannot substitute for time zone handling on instants.

### Using the right pattern symbols

| Symbol | Meaning | Warning |
| --- | --- | --- |
| `dd` | Day of month (2 digits) | Not "day of week". |
| `MM` | Month (2 digits) | `mm` is minute, not month. |
| `uuuu` | Proleptic year in `java.time` | Useful for strict parsing with `DateTimeFormatter`. |
| `yyyy` | Year-of-era in `DateTimeFormatter`; normal year in `SimpleDateFormat` | Choose according to the actual engine and resolver style. |
| `HH` | Hour 0–23 | `hh` is hour 1–12, usually needs AM/PM. |
| `mm` | Minute | Do not confuse with `MM`. |
| `ss` | Second | Agree on whether seconds are required. |
| `XXX` | Offset in `+07:00` form | Use when the pattern must include an offset. |
| `'T'` | Literal letter T between date and time | E.g. `yyyy-MM-dd'T'HH:mm:ss`; quotes in patterns mark literal text. |

A common mistake: using `YYYY` instead of `yyyy`/`uuuu`. `YYYY` is week-based year; near year-end/New Year's, it can differ from the calendar year and corrupt data.

### Do not turn a "time without time zone" into an absolute instant

Parsing `2026-11-05 14:30:45` into `LocalDateTime` only means a local wall-clock time. Deriving an instant requires knowing the `ZoneId`, and in regions with daylight saving time you must handle nonexistent or repeated hours. Global configuration should clearly state target data types, time zones, and exchange conventions.

## 13. Invalid data and validation

A formatter is responsible for **whether a string can be parsed into the target type**. Validation is responsible for **whether the parsed value satisfies business rules**.

Examples:

1. `"2026-11-05"` parses cleanly into `LocalDate` under ISO.
2. `"05/11/2026"` violates ISO syntax; conversion fails unless a specific rule allows it.
3. `"2026-02-30"` looks like ISO but is a nonexistent date; strict parsing fails.
4. `"2026-11-05"` may be type-valid yet disallowed if scheduling in the past is forbidden; that rule belongs to validation/business logic.
5. **Missing** or **blank** values depend on request binding/required/validation rules; you cannot assume from a formatter alone that every empty string becomes a default value.

In controllers, Bean Validation can be used—such as `@FutureOrPresent` on a `LocalDate` inside a suitable DTO. On parse failure, Spring MVC can raise a binding/argument conversion error before business validation runs; the exact HTTP status and response body depend on configured handlers and exception handling.

Do not fall back to a default such as today's date whenever parsing fails unless business rules explicitly require it; doing so hides bad inputs and causes untraceable behavior changes.

## 14. HTML forms: why does global dd/MM/yyyy sometimes fail?

Suppose the browser renders a date picker in Vietnamese. The user sees `05/11/2026`, yet standard HTML:

~~~html
<input type="date" name="date">
~~~

submits **the date value as `yyyy-MM-dd`**, e.g. `date=2026-11-05`. Browsers displaying one format while submitting another is normal. If Spring MVC is configured to parse only `dd/MM/yyyy`, standard HTML forms can fail binding.

Similarly:

~~~html
<input type="datetime-local" name="startsAt">
~~~

submits values typically containing `T`, e.g. `2026-11-05T14:30`, and **no offset**. A custom pattern expecting a space (`dd/MM/yyyy HH:mm:ss`) will not match. You must also agree on whether missing seconds are accepted.

How to handle it:

- For `type=date`, `type=time`, and `type=datetime-local` controls, prefer ISO matching HTML standards.
- If you want to display `dd/MM/yyyy`, format separately in labels/views or use a text input with clear instructions.
- If the API must accept multiple legacy formats, decide compatibility policies at the boundary (`fallbackPatterns` annotation or specific parser/formatter) rather than silently altering the global app config.
- Test with a real browser request; do not guess solely from how the input box renders visually.

## 15. If the application uses Spring WebFlux

Replace Spring MVC's registration point with `WebFluxConfigurer`:

~~~java
package demo.webflux;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class DateTimeWebFluxConfig implements WebFluxConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        var registrar = new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
~~~

This requires Spring WebFlux dependencies and is an **integration configuration** replacing `WebMvcConfigurer` in reactive apps; do not register both expecting them to share one registry. WebFlux query/path/form parameters and JSON codecs remain separate mechanisms.

## 16. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting `@DateTimeFormat` on every controller with different styles | Fragmented format contract, hard to change | Pick an appropriate global rule and annotate only exceptions. |
| Registering formatters on a `ConversionService` other than Spring MVC's | Controllers do not see expected rules | Configure via `WebMvcConfigurer.addFormatters` and test requests. |
| Assuming `spring.mvc.format.*` also applies to JSON | JSON responses ignore the configured pattern | Configure Jackson/JSON codec separately. |
| Enforcing `dd/MM/yyyy` for `<input type=date>` | Browsers submit `yyyy-MM-dd`, causing parse errors | Use ISO for HTML date fields or adjust boundary handling. |
| Using `LocalDateTime` instead of an absolute instant | Time zone confusion, cross-region data errors | Use `Instant`/`OffsetDateTime` or add a `ZoneId` policy. |
| Local pattern without offset for `OffsetDateTime` | Missing info to construct target value | Use offset-aware ISO or a pattern with offset. |
| Mixing up `MM` and `mm` | Wrong month/minute | Review and test patterns with distinguishable values. |
| Mixing up `YYYY` with calendar year | Wrong year near week-year boundaries | Use `uuuu` or `yyyy` appropriate to the engine. |
| Blindly mixing `yyyy`/`uuuu` across `java.time` and `java.text` | Strict parsing or legacy formatter yields unexpected results | Know each formatter's syntax and write tests. |
| Using locale-based styles as long-term API contracts | Output differs across locales/JDKs | Use ISO or fixed patterns for machine protocols. |
| Testing only the parse direction | UI prints a different format than expected | Test both `String → T` and `T → String`. |
| Registering multiple formatters for the same type without controlling order | Behavior depends on registration order | Establish one source of configuration and verify empirically. |
| Catching parse errors and defaulting to today's date | Masks invalid user input | Report clear binding errors and preserve semantics. |
| Adding `@EnableWebMvc` to Boot just for formatters | Alters MVC auto-configuration behavior | Use `WebMvcConfigurer` or properties. |

## 17. Implementation checklist

1. List all `LocalDate`, `LocalTime`, `LocalDateTime`, and offset types accepted at the web boundary.
2. Finalize the **string standard** for each type (ISO or business pattern) and clarify whether HTML forms, API queries, and JSON share the same standard.
3. Choose configuration approach: `spring.mvc.format.*` (simple Boot MVC) or `WebMvcConfigurer.addFormatters` (custom registrars needed).
4. If using legacy `Date`/`Calendar`, check `DateFormatterRegistrar` and a separate time zone policy.
5. Keep `@DateTimeFormat` on fields truly needing exceptions; verify interaction with global formatters.
6. Write tests for both parsing and printing; cover at minimum valid dates, invalid dates, bad syntax, leap years, offset values, and browser requests.
7. Write separate tests for JSON and configuration properties if used by the project.
8. Verify server time zone, UTC/offset contract, and actual user locales.
9. Document published patterns; changing a pattern in a registry can be a breaking change for clients.

**Self-check:** (a) Why can `@RequestParam LocalDate` follow global ISO while JSON `@RequestBody` still uses separate Jackson config? (b) When `<input type=date>` displays a date in Vietnamese, does it submit `dd/MM/yyyy` or `yyyy-MM-dd`? (c) Why is `LocalDateTime` insufficient to pinpoint an instant? (d) Where should you configure a shared formatter for MVC only? Answers respectively: they are two different conversion/serialization pipelines; HTML date inputs submit `yyyy-MM-dd`; `LocalDateTime` has no offset/zone; register in MVC via `WebMvcConfigurer.addFormatters` or use `spring.mvc.format.*` properties.

## 18. Official documentation

- Spring Framework, *Spring Field Formatting*: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework 6.2, *Configuring a Global Date and Time Format*: https://docs.spring.io/spring-framework/reference/6.2/core/validation/format-configuring-formatting-globaldatetimeformat.html
- Spring Framework, *Spring MVC Type Conversion*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
- Spring Boot, *Servlet Web Applications — Spring MVC Conversion Service*: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Framework, *WebFlux Config*: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Javadoc `DateTimeFormatterRegistrar`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/format/datetime/standard/DateTimeFormatterRegistrar.html
- Javadoc `DateFormatterRegistrar`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/datetime/DateFormatterRegistrar.html
- Javadoc `@DateTimeFormat`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html
