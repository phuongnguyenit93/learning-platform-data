# Formatting `Duration` Using APIs Supported by Your Spring Version

## 1. Objectives and context

`java.time.Duration` describes **an amount of time**: a 30-second timeout, a 5-minute retry delay, a 1-hour-30-minute processing window. When a `Duration` field appears in a Spring form or request parameter, the application needs two-way conversion:

```text
Submitted input "90s" --parse--> Duration.ofSeconds(90)
Duration.ofSeconds(90) --print--> "90s" for re-display
```

The single most important point of **"Formatting Duration Using APIs Supported by Your Spring Version"** is **distinguishing APIs by version**. `@DurationFormat`, `DurationFormatter`, and `DurationFormatterUtils` were introduced in **Spring Framework 6.2**; these API examples cannot be used as-is on Spring Framework 6.1 or earlier. In addition, **Spring Boot**'s `DurationStyle`/`@DurationUnit` APIs serve Boot's conversion system; they are not automatically synonymous with Spring MVC field formatting.

After this lesson, you can:
- Identify the Spring Framework version on the classpath and pick the right solution.
- Distinguish Java's ISO-8601 format from Spring Framework 6.2+'s `SIMPLE` and `COMPOSITE` formats.
- Apply `@DurationFormat`, `DurationFormatter`, and `defaultUnit` to parse/print needs accurately.
- Use a custom `Formatter<Duration>` when the Framework lacks 6.2 APIs or requires custom syntax.
- Test round-trips, precision, invalid input errors, and real data binding through Spring.

## 2. Understanding `Duration` before formatting

`java.time.Duration`, available since Java 8, represents a time-based amount in seconds and nanoseconds, which may be negative or zero. This type represents a **length of time**, not a point on the calendar.

The following Java expressions illustrate values (requires `import java.time.Duration;`):

```java
Duration.ofSeconds(90);       // 90 seconds
Duration.ofMinutes(90);       // 1 hour 30 minutes
Duration.ofMillis(250);       // 250 milliseconds
Duration.parse("PT1H30M");    // 1 hour 30 minutes, ISO-8601 syntax
Duration.ofMinutes(90).toString(); // "PT1H30M"
```

- `Duration`: timeouts, delays, time-to-live, execution durations.
- `Period`: calendar years/months/days. A month has no fixed number of seconds, so `Duration` does not replace every "add 1 month" requirement.
- `Instant`, `LocalDateTime`, `ZonedDateTime`: a point or moment in time, not a duration. Date/time formatters do not replace `Duration` formatters.
- A 1-day `Duration` equals a fixed 24 hours; crossing time zone boundaries or daylight saving transitions belongs to timeline/calendar calculations.
- Java's `Duration.parse("PT30S")` understands ISO-8601; **it does not by default understand** Spring's short syntax like `"30s"` or `"1h30m"`.

`Duration.ofMinutes(90).equals(Duration.parse("PT90M"))` evaluates to `true`: it compares duration lengths, not string spelling. `Duration.toString()` may normalize the representation.

## 3. Version-based API selection table

| Environment | Recommended approach | What NOT to assume |
| --- | --- | --- |
| Standalone Java 8+ | `Duration.parse(String)` and `Duration.toString()` using ISO-8601 | That the JDK understands `30s`, `2m`, `1h30m` |
| Spring Framework **6.1 and earlier** | Define/register a custom `Formatter<Duration>` or `Converter` for the desired contract; may delegate to JDK ISO | That `org.springframework.format.annotation.DurationFormat` exists |
| Spring Framework **6.2.x** | `@DurationFormat`, `DurationFormatter`, `DurationFormatterUtils`, `DurationFormat.Style/Unit` enums | That all styles preserve nanoseconds or follow locale rules identically |
| Spring Framework **7.x** | Duration formatter APIs remain supported; cross-check the running version's Javadoc | That an example for a newer version compiles automatically on 6.1 |
| Spring Boot | `DurationStyle`, `@DurationUnit`, `ApplicationConversionService` for Boot-specific conversion cases | That `@ConfigurationProperties` conversion applies identically to `@ModelAttribute`/JSON |

**Note:** Spring Framework 6.2 introduced these APIs; merely seeing "Spring Boot 3.x" is not enough to infer the Framework version. Check the actual dependency tree or runtime version:

```java
System.out.println(org.springframework.core.SpringVersion.getVersion());
```

In Maven use `mvn dependency:tree`; in Gradle use `dependencyInsight` for `org.springframework:spring-context`. Spring Boot typically manages the Spring Framework version via its BOM; do not bump `spring-context` alone to 6.2 while other Framework modules remain on 6.1.

## 4. Key Spring Framework 6.2+ APIs to remember

Primary imports:

```java
import org.springframework.format.annotation.DurationFormat;
import org.springframework.format.datetime.standard.DurationFormatter;
import org.springframework.format.datetime.standard.DurationFormatterUtils;
```

`DurationFormat` is the annotation describing how a `Duration` field/parameter is formatted. `DurationFormatter` implements `Formatter<Duration>` with `parse(String, Locale)` / `print(Duration, Locale)`. `DurationFormatterUtils` provides static helpers to parse/print by style or detect style.

`DurationFormatter` has constructors taking `DurationFormat.Style`, or both `DurationFormat.Style` and a fallback `DurationFormat.Unit`. `@DurationFormat` has two key attributes:

```java
@DurationFormat(
    style = DurationFormat.Style.SIMPLE,
    defaultUnit = DurationFormat.Unit.SECONDS
)
private Duration timeout;
```

By default, the annotation uses `Style.ISO8601`, and the default fallback unit is `Unit.MILLIS` when a style needs a unit. The chosen style governs input syntax; setting `defaultUnit=SECONDS` does not make `Style.ISO8601` parse `"90"`.

### 4.1. `Style.ISO8601`: the JDK standard

| String | Duration |
| --- | --- |
| `PT30S` | 30 seconds |
| `PT1H30M` | 1 hour 30 minutes |
| `PT0.25S` | 250 milliseconds |
| `P2D` | 2 days, 24 hours each in duration terms |

ISO-8601 works well when you want an unambiguous representation capable of fractional seconds down to `Duration`'s nanosecond precision. `DurationFormatter(Style.ISO8601)` follows JDK parse and print syntax. For instance, `Duration.parse("PT90S").toString()` normalizes to `"PT1M30S"`; do not require printed text to match raw input text character for character.

### 4.2. `Style.SIMPLE`: one integer and one unit

Supported suffixes:

| Suffix | Unit | Example |
| --- | --- | --- |
| `ns` | nanoseconds | `500ns` |
| `us` | microseconds | `250us` |
| `ms` | milliseconds | `750ms` |
| `s` | seconds | `90s` |
| `m` | minutes | `5m` |
| `h` | hours | `2h` |
| `d` | 24-hour days | `1d` |

`SIMPLE` does not support decimals like `"1.5s"`. Express 1.5 seconds as `"1500ms"`, or switch to `ISO8601` with `"PT1.5S"`.

When `DurationFormatter(Style.SIMPLE, Unit.SECONDS)` prints 90 seconds, it returns `"90s"`; when parsing a **suffixless** string `"90"`, it uses `defaultUnit=SECONDS` to interpret 90 seconds. Yet `"90ms"` remains 90 milliseconds, because an **explicit suffix unit** is not overridden by the default unit.

**Precision:** `SIMPLE` prints in one fixed unit and can drop sub-unit precision. For example:

```java
Duration precise = Duration.ofMillis(5).plusNanos(1234);
DurationFormatter formatter = new DurationFormatter(
    DurationFormat.Style.SIMPLE,
    DurationFormat.Unit.MILLIS);
String printed = formatter.print(precise, Locale.US); // "5ms"
```

This is an illustrative snippet requiring `java.time.Duration`, `java.util.Locale`, and the Spring classes. The **1234 nanoseconds** cannot be recovered when parsing `"5ms"`. If nanoseconds must be preserved, pick an appropriate style/unit and test boundary values; also watch for `long` overflow risk when expressing very long durations as integer nanoseconds.

### 4.3. `Style.COMPOSITE`: multiple duration segments

Example syntax:

```text
1h30m
2h15m10s
1h 30m
-(34m 57s)
```

`COMPOSITE` allows multiple units combined in **largest-to-smallest** order. This style suits displaying long durations in human-readable form. Spring accepts certain whitespace variations and negative signs per its grammar; that does not make it a natural-language parser. The string `"1 hour 30 minutes"` is not supported by default.

`DurationFormatterUtils.parse("1h30m", DurationFormat.Style.COMPOSITE)` returns a duration equivalent to 90 minutes. When you call `Duration.toString()` on the result, Java still prints ISO-8601 (`PT1H30M`); that is **not** the output of the COMPOSITE printer.

### 4.4. Spring's `Unit` vs `ChronoUnit`

The `DurationFormat.Unit` enum values are `NANOS`, `MICROS`, `MILLIS`, `SECONDS`, `MINUTES`, `HOURS`, `DAYS`. This is a **Spring Framework** type in `org.springframework.format.annotation.DurationFormat`, not `java.time.temporal.ChronoUnit`, even though the units correspond.

`defaultUnit` acts as a fallback when a style allows unitless strings, and also chooses the output unit when `SIMPLE` prints values. Specify it explicitly on fields receiving unitless numbers; defaulting to milliseconds can cause severe business bugs if users think `"90"` means 90 seconds.

## 5. Using the annotation on Spring MVC fields

On Spring Framework **6.2+**, a form model can declare:

```java
import java.time.Duration;
import org.springframework.format.annotation.DurationFormat;

public class JobForm {
    @DurationFormat(
        style = DurationFormat.Style.SIMPLE,
        defaultUnit = DurationFormat.Unit.SECONDS
    )
    private Duration timeout;

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

With a default `FormattingConversionService` supporting the annotation, input `"90"` binds to `Duration.ofSeconds(90)`; when printed in this style, 90 seconds renders as `"90s"`. Input `"2m"` becomes two minutes because a suffix is present.

You can also place `@DurationFormat` on a Spring MVC controller parameter (**illustrative snippet**, requires Spring Web MVC dependency):

```java
@GetMapping("/preview")
String preview(
        @RequestParam
        @DurationFormat(style = DurationFormat.Style.COMPOSITE)
        Duration delay) {
    return "delay=" + delay;
}
```

Web imports are `org.springframework.web.bind.annotation.GetMapping` and `RequestParam`. Request `/preview?delay=1h30m` can parse into `Duration` when running on Framework 6.2+ with the proper MVC formatting setup. On parse failure, handle binding/HTTP results according to your API policy.

A shared formatter for all `Duration` values can be registered via `WebMvcConfigurer.addFormatters(FormatterRegistry)`, e.g. `registry.addFormatter(new DurationFormatter(Style.COMPOSITE))`. Use global configuration only when fields genuinely share a contract; when fields differ in style/defaultUnit, field-level annotations are clearer.

## 6. Complete Java 17+ example: testing Spring 6.2 APIs and DataBinder

This example pins **Spring Framework 6.2.14**, uses Maven, and requires Java 17+. It tests ISO-8601, SIMPLE, and COMPOSITE formatters, annotation-driven data binding, and conversion errors. No Spring Boot or web server is needed.

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>duration-format-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/example/DurationFormattingDemo.java`:

```java
package example;

import java.text.ParseException;
import java.time.Duration;
import java.util.Locale;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.format.annotation.DurationFormat;
import org.springframework.format.datetime.standard.DurationFormatter;
import org.springframework.format.datetime.standard.DurationFormatterUtils;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.DataBinder;

public final class DurationFormattingDemo {

    public static final class JobForm {
        @DurationFormat(
                style = DurationFormat.Style.SIMPLE,
                defaultUnit = DurationFormat.Unit.SECONDS)
        private Duration timeout;

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws ParseException {
        Locale locale = Locale.US;

        // 1. ISO-8601: JDK duration format.
        DurationFormatter iso =
                new DurationFormatter(DurationFormat.Style.ISO8601);
        Duration ninetyMinutes = Duration.ofMinutes(90);
        String isoText = iso.print(ninetyMinutes, locale);
        check("PT1H30M".equals(isoText), "ISO print differs");
        check(ninetyMinutes.equals(iso.parse(isoText, locale)),
                "ISO round-trip failed");
        System.out.println("ISO: " + isoText);

        // 2. SIMPLE, choosing the unit when printing and when input omits a suffix.
        DurationFormatter simple = new DurationFormatter(
                DurationFormat.Style.SIMPLE,
                DurationFormat.Unit.SECONDS);
        String simpleText = simple.print(Duration.ofSeconds(90), locale);
        check("90s".equals(simpleText), "SIMPLE print differs");
        check(Duration.ofSeconds(90).equals(
                simple.parse(simpleText, locale)),
                "SIMPLE round-trip failed");
        check(Duration.ofSeconds(90).equals(
                simple.parse("90", locale)),
                "Wrong defaultUnit");
        System.out.println("SIMPLE: " + simpleText);

        // 3. COMPOSITE parses multi-segment durations.
        Duration composite = DurationFormatterUtils.parse(
                "1h30m", DurationFormat.Style.COMPOSITE);
        check(ninetyMinutes.equals(composite),
                "COMPOSITE parse failed");
        System.out.println("COMPOSITE: " + composite);

        // 4. DataBinder uses the field annotation.
        DefaultFormattingConversionService conversionService =
                new DefaultFormattingConversionService();

        JobForm form = new JobForm();
        DataBinder binder = new DataBinder(form);
        binder.setConversionService(conversionService);
        binder.bind(new MutablePropertyValues(Map.of("timeout", "90")));
        check(!binder.getBindingResult().hasErrors(),
                "Unexpected binding error");
        check(Duration.ofSeconds(90).equals(form.getTimeout()),
                "Wrong annotated timeout");
        System.out.println("FIELD: " + form.getTimeout());

        // 5. Invalid input must produce a FieldError, not become zero.
        JobForm invalidForm = new JobForm();
        DataBinder invalidBinder = new DataBinder(invalidForm);
        invalidBinder.setConversionService(conversionService);
        invalidBinder.bind(new MutablePropertyValues(
                Map.of("timeout", "not-a-duration")));
        boolean badInputRejected = invalidBinder
                .getBindingResult().hasFieldErrors("timeout");
        check(badInputRejected, "Expected field conversion error");
        System.out.println("INVALID_BINDING: " + badInputRejected);

        System.out.println("CHECKS: PASS");
    }
}
```

Run with Maven 3.9+:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.DurationFormattingDemo
```

Expected output when all checks pass:

```text
ISO: PT1H30M
SIMPLE: 90s
COMPOSITE: PT1H30M
FIELD: PT1M30S
INVALID_BINDING: true
CHECKS: PASS
```

Explanation:
1. `ISO` returns `"PT1H30M"` and parses back to the same 90-minute `Duration`.
2. `SIMPLE` returns `"90s"` because the display unit is seconds; suffixless input `"90"` is also read as seconds thanks to `defaultUnit=SECONDS`.
3. `COMPOSITE` parses `"1h30m"` into a 90-minute `Duration`. `System.out.println` prints **`Duration.toString()` in ISO**, not `DurationFormatterUtils.print(..., COMPOSITE)`.
4. `FIELD` verifies the `DataBinder` path reads the annotation and binds `"90"` to 90 seconds; `Duration.toString()` prints 90 seconds as `"PT1M30S"`.
5. `"not-a-duration"` must record a field error in `BindingResult`. In a real app, present user-friendly error messages.

This example uses Spring classes documented in **6.2.14** Javadoc. Compiling against **6.1** will fail because the new APIs are absent. When changing patch versions, re-run parse/print and binding tests against the exact runtime dependencies.

## 7. Alternative on Spring Framework 6.1 and earlier

Without 6.2's `@DurationFormat`/`DurationFormatter`, you can write a `Formatter<Duration>` using the long-standing Spring SPI. This example **only supports ISO-8601**, and does not accept `30s` or `1h30m`.

File `src/main/java/example/IsoDurationFormatter.java`:

```java
package example;

import java.time.Duration;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import org.springframework.format.Formatter;

public final class IsoDurationFormatter implements Formatter<Duration> {
    @Override
    public String print(Duration value, Locale locale) {
        return value.toString();
    }

    @Override
    public Duration parse(String text, Locale locale) {
        try {
            return Duration.parse(text);
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Expected ISO-8601, e.g. PT30S", ex);
        }
    }
}
```

This class uses JDK APIs and Spring's `Formatter` interface available in older versions; `parse` may throw `IllegalArgumentException`, matching Spring formatter's error contract.

Register in Spring MVC via configuration (**illustrative snippet**, requires `spring-webmvc` dependency and imports):

```java
@Configuration
class DurationWebConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new IsoDurationFormatter());
    }
}
```

Imports are `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`, and `org.springframework.format.FormatterRegistry`. Outside Spring MVC, you can register it on a `FormattingConversionService` and attach that to `DataBinder`.

With ISO configured, `parse("PT30S", ...)` yields 30 seconds, while `parse("30s", ...)` must fail. To support suffixes, design a parser with an explicit grammar, test overflow/precision, and register it in the conversion service. Do not put `@DurationFormat` on a Spring 6.1 project expecting the framework to pick it up.

## 8. Avoid confusing Spring Boot's conversion system

Spring Boot provides different APIs:

```java
org.springframework.boot.convert.DurationStyle
org.springframework.boot.convert.DurationUnit
```

These commonly appear when binding configuration properties, for example:

```yaml
app:
  timeout: 30s
```

Distinguish clearly:
- **Boot**'s `@DurationUnit` sets the unit for Boot's own conversion mechanism; **Framework 6.2+**'s `@DurationFormat(defaultUnit=...)` describes field/parameter formatting.
- Boot's `ApplicationConversionService` has its own set of converters; do not assume Spring MVC's `FormatterRegistry` shares all those rules without verifying.
- JSON `@RequestBody` is normally handled via `HttpMessageConverter`/Jackson, distinct from `@ModelAttribute` or `@RequestParam` string conversion. If a JSON API should accept `"30s"`, define the JSON contract and test it independently.
- Spring Boot can run alongside different Spring Framework versions; always check the actual version rather than guessing from the word "Boot".

## 9. Round-trip checks and precision impact

Let `P_s(d)` denote printing duration `d` in style `s`, and `Q_s(t)` denote parsing string `t` in the same style/unit.

**Value → string → value:**

```text
Q_s(P_s(d)) == d
```

This holds only if printing retains sufficient resolution. For instance, `Duration.ofMillis(5).plusNanos(1234)` printed in SIMPLE with `Unit.MILLIS` truncates to `5ms`; parsing it back **differs** from the original value. If nanosecond loss is unacceptable, use ISO-8601 or choose an appropriate unit and test remainder/overflow behavior.

**String → value → canonical string:**

```text
P_s(Q_s(text)) == canonical_s(text)
```

Input strings need not match printed strings character-for-character. `"90"` with SIMPLE/SECONDS may re-print as `"90s"`, and `"PT90S"` in ISO normalizes to `"PT1M30S"`. Only require exact text preservation if a single canonical input form is demanded and validated.

**Locale does not translate suffixes into Vietnamese.** `Formatter` receives a `Locale` per the SPI, yet `ISO8601`/`SIMPLE`/`COMPOSITE` are temporal token syntaxes; `Locale.forLanguageTag("vi-VN")` does not turn `"1h30m"` into `"1 giờ 30 phút"`. If the UI needs natural language, build a dedicated localized formatter and test across locales.

## 10. Practical test matrix

| Category | Suggested cases | Expectation |
| --- | --- | --- |
| Basic ISO | `PT0S`, `PT30S`, `PT1H30M` | Parse/print accurately per JDK |
| High-precision ISO | `PT0.123456789S` | No nanosecond loss |
| SIMPLE with suffix | `500ms`, `90s`, `2m`, `1h` | Recognizes exact unit |
| SIMPLE without suffix | `"90"` with fallback `SECONDS` vs `MILLIS` | Catches 1000x scaling mistakes |
| SIMPLE decimals | `1.5s`, `1500ms` | `1.5s` invalid in SIMPLE; `1500ms` valid |
| COMPOSITE | `1h30m`, `2h15m10s` | Sums components properly in valid order |
| Whitespace and negatives | `1h 30m`, `-(34m 57s)` | Accepts only style-supported forms |
| Precision | `Duration.ofMillis(5).plusNanos(1234)` | Detects nanosecond loss when printing in ms |
| Zero/negative | `PT0S`, `-PT5S`, plus domain inputs | Distinguishes parseable from domain-valid |
| Bad strings | `n/a`, `1hour`, trailing chars, unsupported units | Produces `FieldError`, never silently zero |
| Blank/null | `""`, whitespace, missing field | Verifies required/null policy at binding layer |
| Runtime | Running Spring 6.1, 6.2, 7, or Boot | No missing API imports; formatter wired on real path |
| Real forms | `@ModelAttribute`, `@RequestParam` | Verifies model value and `BindingResult`/HTTP errors |

**Separate two error classes:** Successfully parsing `PT0S` or `-PT5S` does not make them valid timeouts. After conversion to `Duration`, use business validation to reject negative, zero, or out-of-range durations. Before parsing succeeds, handle `typeMismatch` at the binding layer; validation on already-typed objects cannot replace proper parsing.

## 11. Diagnosing common errors

**`Cannot resolve symbol DurationFormat`**: using Spring Framework older than 6.2, missing `spring-context` dependency, wrong package import, or multiple Spring versions on the classpath. Inspect the dependency tree before changing code.

**Typed `90` but got 90 ms instead of 90 s**: forgot `defaultUnit=SECONDS`, while the default fallback is `MILLIS`. Label units clearly in the UX or require explicit suffixes.

**Using `@DateTimeFormat(pattern = ...)` on `Duration`**: that annotation is for dates/times, not the primary choice for durations. Spring 6.2+ provides `@DurationFormat`; older versions use custom formatters.

**`Duration.parse("1h30m")` fails**: the JDK parser uses ISO-8601, whereas COMPOSITE is a Spring 6.2+ feature. Choose `DurationFormatterUtils.parse(text, Style.COMPOSITE)` or an appropriate formatter API.

**Round-trip loses fractional nanoseconds**: `SIMPLE` prints in a fixed unit and may truncate. Use a precision-preserving style or normalize data before printing under a clear contract.

**Parser unit test passes, MVC still fails**: check whether the formatter/annotation is actually registered in MVC's `FormattingConversionService`, field/getter types, binding result placement, and whether another converter overrides it. Do not judge from a standalone parser call alone.

**Form and JSON accept different syntaxes**: do not conflate form conversion with Jackson JSON. To share a contract, define and test both ingestion paths and their error handling.

## 12. Solution selection checklist

1. Identify the **actual Spring Framework version** and Java runtime; check the matching Javadoc branch.
2. Identify the **input path**: form, request parameter, configuration properties, or JSON.
3. Pick one **documented syntax**: `ISO8601`, `SIMPLE`, `COMPOSITE`, or a custom contract.
4. Set `defaultUnit` and print resolution explicitly; avoid accepting unitless numbers that users might misread.
5. Use `@DurationFormat`/`DurationFormatter` on Framework 6.2+; on 6.1 or earlier, write a custom `Formatter<Duration>`.
6. Test parse/print, canonicalization, precision, overflow, negative/zero, invalid inputs, and `DataBinder` or real HTTP requests.
7. Keep business validation separate from type conversion, and report clear input errors to users.

## References

- Spring Framework 6.2 — Field Formatting: https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html
- Spring Framework 6.2 — MVC Type Conversion: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html
- Spring Framework 6.2.14 — `DurationFormatter`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/datetime/standard/DurationFormatter.html
- Spring Framework 6.2.4 — `DurationFormat` and `Style`: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/format/annotation/DurationFormat.html
- Spring Framework 6.2.4 — `DurationFormat.Style`: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/format/annotation/DurationFormat.Style.html
- Spring Framework 6.2.14 — `DurationFormat.Unit`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/annotation/DurationFormat.Unit.html
- Java SE 17 — `java.time.Duration`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html
- Spring Boot — `DurationStyle` (Boot API, distinct from Framework): https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/convert/DurationStyle.html
