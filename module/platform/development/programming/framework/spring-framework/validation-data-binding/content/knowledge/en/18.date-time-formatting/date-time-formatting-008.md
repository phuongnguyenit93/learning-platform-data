# Impact of JDK Versions on Locale-Based Formatting Patterns

> **Scope:** Locale-based date/time formatting and parsing in Java and Spring Framework, especially during JDK upgrades. Focuses on `@DateTimeFormat`, `DateTimeFormatter`, locale data (CLDR), input compatibility, and testing strategy. Java examples run on JDK 17 or newer.

## 1. Why does the same `Locale` display dates/times differently across JDK upgrades?

A `Locale` (such as `en-US`, `vi-VN`, `fr-FR`) identifies language and regional conventions; it **does not itself contain a fixed date/time pattern**. When using *style*-based formatting like `SHORT`, `MEDIUM`, `LONG`, or `FULL`, the JDK's temporal library looks up locale data available at **runtime** to determine the exact pattern and symbols.

For example, two JDK versions receiving the same inputs:

- Value `LocalTime.of(13, 45)`.
- `Locale.US`.
- `DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)`.

**can** produce different strings because their locale data versions differ. Differences may involve component order, year length, punctuation, month spellings, AM/PM markers, whitespace, hour symbols, or calendar systems. Not every locale and style changes in every JDK release.

Data flow when Spring MVC receives/displays a temporal field:

```text
HTTP query/form field (String)         Java value (LocalDate/LocalTime/...)
           │                                       ▲
           ▼                                       │
   WebDataBinder + ConversionService + Formatter
           │
           └── @DateTimeFormat(style = "...") --> locale pattern from active JDK
                                                   │
                                            Request Locale
                                                   │
                                             CLDR/JDK data
```

- **Parsing:** converting a form/query string into a date/time object.
- **Printing:** generating a display string from a date/time object, e.g. to re-render a form.
- **Consequence of changing JDKs:** if an older server renders a string with one pattern and a newer server parses with another, round-trips across different runtimes can fail even when `Locale` is unchanged.

This is the behavior of locale-based formatters; do not equate it with time zone changes, DST, or JSON serialization. Those factors can also affect temporal data, but they belong to different technical boundaries.

## 2. Under the hood: JDK, CLDR, and locale providers

**CLDR** (*Unicode Common Locale Data Repository*) is the internationalization dataset providing language/region conventions: date/time patterns, month/weekday names, AM/PM, spacing, etc. Each JDK bundles a CLDR version appropriate to its release. `java.time.format.DateTimeFormatter` and several `java.text` APIs consume locale data through the JDK's provider mechanism.

| JDK era | Key change | Impact on date/time handling |
| --- | --- | --- |
| **JDK 8** | Legacy `JRE` data prioritized by default; CLDR selectable via config | Style-based output may differ from newer JDKs for the same locale |
| **JDK 9–19** | Under JEP 252, `CLDR` is prioritized by default from JDK 9; JDK updates can update locale data | Formatted/parsed values may differ from JDK 8 or across releases |
| **JDK 20–22** | JDK 20 integrates CLDR 42 with notable changes, including the character before AM/PM | Some stored or form-submitted date/time strings may parse differently than expected |
| **JDK 23 onward** | Legacy `JRE`/`COMPAT` locale data was removed starting in JDK 23 | Cannot rely on `COMPAT` to restore legacy locale output |

Key points to understand:

1. **`Locale.US` is not a pattern "version lock".** It is merely a lookup key for runtime formatting conventions.
2. **`FormatStyle.SHORT` does not guarantee a fixed byte sequence either.** The API preserves the short/compact intent, while the concrete pattern comes from locale data.
3. **`java.locale.providers` selects the lookup order of data sources**, not a switch to roll back to an arbitrary CLDR version. On JDK 9–22 you could prioritize `JRE`/`COMPAT` to ease migration; on JDK 23+ that legacy option has no effect.
4. **JDK vendor, patches, runtime images, and bundled locale data** can make runtime environments differ. Never hard-code one JDK's output as a mandatory standard for all JDKs.
5. `Locale` and `ZoneId` are distinct concepts: locale shapes phrasing/formatting; zone/offset and clock transitions alter the displayed time.

### JDK 20's specific change: whitespace before AM/PM

Spring Framework explicitly notes for JDK 20+: CLDR 42 changed the whitespace character preceding `AM`/`PM` labels in some formatted outputs from an **ordinary space** `U+0020` to a **narrow no-break space** `U+202F`.

Two sample strings may look almost identical:

```text
"1:45 PM"        -> between 45 and PM is U+0020
"1:45\u202FPM"  -> between 45 and PM is U+202F (escaped representation)
```

In the text above, `\u202F` is an *escape* notation to make the code point visible. In the actual string, it is **one Unicode character**, not six characters of backslash/letters/digits. Users may not visually notice any difference, yet the two strings are unequal under character comparison. If a parser demands an exact pattern literal, changing one whitespace character can cause a binding failure.

**Do not conclude that every JDK 20+ output contains `U+202F`.** Output depends on locale, style, data type, runtime version, and provider. Inspect actual values by *Unicode code point* rather than by eye.

## 3. Runnable Java 17+: observing runtime patterns

This example uses the same data and locale, prints the pattern looked up by the JDK, the formatted result, each Unicode code point, and compares against an ISO/explicit pattern. Run the same program on different JDKs to compare.

Save the following as **`LocaleJdkProbe.java`**:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.stream.Collectors;

public class LocaleJdkProbe {
    public static void main(String[] args) {
        Locale locale = Locale.US;
        LocalDate date = LocalDate.of(2026, 11, 5);
        LocalTime time = LocalTime.of(13, 45);

        DateTimeFormatter dateFormatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                                 .withLocale(locale);
        DateTimeFormatter timeFormatter =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)
                                 .withLocale(locale);

        String datePattern = DateTimeFormatterBuilder
                .getLocalizedDateTimePattern(
                        FormatStyle.SHORT, null,
                        IsoChronology.INSTANCE, locale);

        String timePattern = DateTimeFormatterBuilder
                .getLocalizedDateTimePattern(
                        null, FormatStyle.SHORT,
                        IsoChronology.INSTANCE, locale);

        System.out.println("JDK feature=" + Runtime.version().feature());
        System.out.println("Locale=" + locale.toLanguageTag());

        show("date.pattern", datePattern);
        show("date.value", dateFormatter.format(date));
        show("time.pattern", timePattern);
        show("time.value", timeFormatter.format(time));

        DateTimeFormatter explicit =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm", Locale.ROOT);

        System.out.println("ISO date="
                + DateTimeFormatter.ISO_LOCAL_DATE.format(date));
        System.out.println("Explicit="
                + explicit.format(LocalDateTime.of(date, time)));
    }

    private static void show(String name, String text) {
        String codePoints = text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));

        System.out.println(name + "=[" + text + "]");
        System.out.println(name + ".codePoints=" + codePoints);
    }
}
```

Compile and run with the configured JDK:

```bash
javac LocaleJdkProbe.java
java LocaleJdkProbe
```

The two lines **stable for the sample data** are:

```text
ISO date=2026-11-05
Explicit=2026-11-05 13:45
```

The lines containing `JDK feature`, `date.pattern`, `time.pattern`, `date.value`, `time.value`, and `codePoints` are printed based on the active runtime; **there is no single stdout valid across all JDKs**. For instance, seeing `U+202F` in `time.value.codePoints` means the formatted string contains a narrow no-break space. Seeing only `U+0020` there means an ordinary space. `getLocalizedDateTimePattern` is for *diagnosing the selected pattern*; do not grab the current JDK's pattern and assume every other JDK uses it.

Re-run those two commands on JDK 17, JDK 21, and a JDK 23+ in your test environment. Record `java -version`, runtime vendor, locale, and code point results. Compare application behavior, not only visual output strings.

## 4. Direct connection to Spring `@DateTimeFormat`

Spring Framework lets you declare how a field/argument is parsed and printed in three primary ways:

| Declaration | Meaning | Sensitivity to locale data |
| --- | --- | --- |
| `@DateTimeFormat(style = "S-")` | SHORT date; `-` omits the time part | **High:** pattern comes from runtime and locale |
| `@DateTimeFormat(style = "-S")` | SHORT time; omits the date part | **High:** subject to AM/PM and Unicode space changes |
| `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` | Date in ISO form, e.g. `2026-11-05` | **Low:** clear wire structure, no locale-based style |
| `@DateTimeFormat(pattern = "dd/MM/uuuu")` | App-defined explicit pattern for `java.time` | **Less sensitive** for order/separators; text fields like month names/AM-PM can still depend on locale |

`style` syntax has two positions: date then time. Codes `S`/`M`/`L`/`F` stand for SHORT/MEDIUM/LONG/FULL respectively; `-` omits that part. Choose only **one** of `style`, `iso`, `pattern` per declaration. `pattern` overrides `iso` and `style`; `iso` overrides `style` if declared together, though combining multiple modes is confusing and should be avoided.

### 4.1. Locale-dependent patterns: suitable for human display

The following is an example of fields in a Spring MVC DTO (not a standalone Java program):

```java
import java.time.LocalDate;
import java.time.LocalTime;
import org.springframework.format.annotation.DateTimeFormat;

public class BookingForm {
    @DateTimeFormat(style = "S-")
    private LocalDate bookingDate;

    @DateTimeFormat(style = "-S")
    private LocalTime bookingTime;

    public LocalDate getBookingDate() {
        return bookingDate;
    }

    public void setBookingDate(LocalDate bookingDate) {
        this.bookingDate = bookingDate;
    }

    public LocalTime getBookingTime() {
        return bookingTime;
    }

    public void setBookingTime(LocalTime bookingTime) {
        this.bookingTime = bookingTime;
    }
}
```

When a controller receives `@ModelAttribute BookingForm`, Spring uses the configured formatter and the request's locale to bind query/form strings to fields. In one locale/JDK, a 12-hour time string may use AM/PM; in another locale/JDK, it may be 24-hour format or use a different Unicode space. Hence, **never store strings from style-based fields as long-term data keys or fixed cross-system contracts**.

### 4.2. Stable patterns for data exchange, paths, or APIs

When the application controls input structure, prefer ISO for dates and explicit numeric patterns for times:

```java
import java.time.LocalDate;
import java.time.LocalTime;
import org.springframework.format.annotation.DateTimeFormat;

public class SearchFilter {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate fromDate;

    @DateTimeFormat(pattern = "HH:mm")
    private LocalTime fromTime;

    public LocalDate getFromDate() {
        return fromDate;
    }

    public void setFromDate(LocalDate fromDate) {
        this.fromDate = fromDate;
    }

    public LocalTime getFromTime() {
        return fromTime;
    }

    public void setFromTime(LocalTime fromTime) {
        this.fromTime = fromTime;
    }
}
```

Corresponding query/form input example:

```text
fromDate=2026-11-05
fromTime=13:45
```

`LocalDate` and `LocalTime` in this example **carry no time zone**. If business logic manages an absolute instant, choose an appropriate type like `Instant` or `OffsetDateTime` and specify zone/offset in the contract. Changing only the pattern or locale does not fix time zone discrepancies.

### 4.3. `fallbackPatterns` helps migrate legacy inputs

Spring `@DateTimeFormat` supports `fallbackPatterns` (Spring Framework 5.3.5+). When parsing with the primary `pattern`, `iso`, or `style` fails, the framework tries fallback patterns in declaration order.

```java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public class LegacySearchForm {
    @DateTimeFormat(
        iso = DateTimeFormat.ISO.DATE,
        fallbackPatterns = {"M/d/uuuu", "dd.MM.uuuu"}
    )
    private LocalDate date;

    public LocalDate getDate() {
        return date;
    }

    public void setDate(LocalDate date) {
        this.date = date;
    }
}
```

The application prefers accepting/printing dates in ISO like `2026-11-05`, while also accepting strings matching `M/d/uuuu` or `dd.MM.uuuu` during a transition period.

**Must distinguish:** `fallbackPatterns` **supports parsing only**; it does not alter the printed output string. The primary mode (`iso` here) still governs printing. Fallbacks also do not automatically handle every historical representation or Unicode character; if users truly supply incompatible inputs, test every pattern, every locale, and every JDK. Avoid ambiguous fallback pairs like `M/d/uuuu` and `d/M/uuuu` together without a rule disambiguating day and month.

### 4.4. Limitation: Spring formatters differ from Jackson JSON

`@DateTimeFormat` applies to Spring field binding/printing (such as query/form via `@ModelAttribute`); **it does not by default format JSON bodies** read/written by Jackson via `@RequestBody`/`@ResponseBody`. For JSON, use an appropriate data contract and Jackson configuration; if using `@JsonFormat`, test the JSON path separately.

A JDK upgrade can affect different date-time read/write paths, yet you should not try to fix a form-binding failure with a Jackson annotation, or vice versa.

## 5. Procedure to reproduce failures during a JDK upgrade

Suppose after upgrading from JDK 17 to JDK 21, an `en-US` time input form reports an error even though the displayed text looks identical. Follow these steps:

1. **Identify the data path:** query/form with `@DateTimeFormat` or JSON with Jackson? For field-binding errors, inspect `BindingResult`/field errors and type mismatches.
2. **Capture raw input:** log the exact input received at the HTTP boundary in UTF-8 and code point representation. For example, distinguish `U+0020` from `U+202F`; do not automatically `trim()` or normalize whitespace before checking business requirements.
3. **Record runtime details:** `java -version`, JDK vendor/build, request `Locale`, formatter style/pattern, configured provider, and sample data. If zones are involved, record `ZoneId` and relevant tzdb as well.
4. **Reproduce on old and new environments:** keep input, locale, Java type, endpoint, and config identical. Test both *format → parse in the same runtime* and *format in old runtime → parse in new runtime*.
5. **Compare patterns and code points:** run `LocaleJdkProbe`, inspect the resolved pattern and actual Unicode points. Distinguish punctuation/whitespace/month-name changes from time zone or validation errors.
6. **Choose a long-term fix:** machine-readable data should use ISO/explicit patterns; human-facing forms can keep localized formatting while accepting/migrating legacy inputs as needed.
7. **Regression-test** before rolling out the JDK upgrade in production, covering at least real user locales and boundary values.

Suggested test matrix:

| Test axis | Suggested values | Purpose |
| --- | --- | --- |
| JDK | 17, 21, 23+ or exact deployment targets | Catch CLDR/provider changes across runtimes |
| Locale | `en-US`, `vi-VN`, and actual product locales | Avoid assuming all locales share a pattern |
| Format | `SHORT`, `MEDIUM`, ISO, and custom patterns | Separate runtime-decided parts from fixed contracts |
| Data | Single-digit days, year rollovers, 12/24h, AM/PM, `U+0020`/`U+202F` | Catch parse failures and invisible characters |
| Path | Form/query, form re-render, JSON (if present) | Test the exact Spring mechanism in use |

With Spring MVC, you can use `MockMvc` and set an explicit request locale (e.g. `.locale(Locale.US)`) to test binding across JDKs. Tests should assert **parsed Java values and error outcomes**; when outputs are localized strings, verify and account for Unicode stability. Do not lock entire text snapshots to one JDK unless product requirements truly demand byte-for-byte strings.

## 6. Provider config: transition aid, not a long-term strategy

On **JDK 9–22** runtimes, the following startup flag can prioritize the legacy provider:

```bash
java -Djava.locale.providers=COMPAT,CLDR -jar app.jar
```

`JRE` was the corresponding legacy name, and `COMPAT` was an alias used during the transition period. **JDK 21 deprecated/warned about removing the legacy provider; starting in JDK 23, `JRE`/`COMPAT` no longer has legacy data to restore**, so adding this flag does not guarantee reproducing old outputs. The flag must also be passed at JVM startup; do not expect to toggle it per request.

Pinning an older JDK or selecting the legacy provider only mitigates risk during a controlled migration. For a durable contract:

- Use semantically accurate temporal types (`LocalDate`, `LocalTime`, `Instant`, `OffsetDateTime`, ...).
- Specify wire formats at system boundaries, preferring ISO 8601 or deliberate patterns, with explicit locale/zone when needed.
- Separate *temporal values* from *user-dependent display strings*.
- If legacy input compatibility is needed, define `fallbackPatterns` or a transparent migration parser with tests and a sunset date.
- Use UTF-8 from HTTP through logs/storage when storing multilingual display strings; proper encoding alone does not make `U+0020` and `U+202F` equal.

## 7. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "The locale is `vi-VN`, so the pattern will stay fixed forever" | Locale only picks conventions; JDK CLDR data can change |
| "With the same `DateTimeFormatter.ofLocalizedTime(SHORT)`, stdout is always identical" | Style is relative; literal patterns and Unicode characters can differ |
| "JDK 20 only changed UI rendering" | If previously stored strings are parsed by a new parser, binding failures can occur |
| "Using `COMPAT` is a permanent fix" | The legacy provider was removed starting in JDK 23 |
| "A fixed pattern with `MMM`/`a` is locale-independent" | Month names and AM/PM are still resolved from locale data |
| "`fallbackPatterns` reverts output to the old format too" | It is only tried during parsing; printing still uses the primary setting |
| "`@JsonFormat` fixes `@ModelAttribute` parse errors" | Jackson JSON and Spring field formatters are separate pipelines |
| "`Locale` implies time zone" | Locale, zone/offset, chronology, and tzdb data are separate factors |
| "Looking identical means two strings are equal" | Spaces `U+0020` and `U+202F` look similar yet have different code points |

Additional reminder on temporal patterns: `MM` is **month**, `mm` is **minute**; `HH` is 0–23 hour, `hh` is 1–12 hour and usually needs `a`; `YYYY` denotes *week-based year* rather than normal calendar year. In `java.time`, `uuuu` is the proleptic year, usually suited for ISO-like patterns. A wrong pattern letter can easily be mistaken for a JDK upgrade or CLDR bug.

## 8. Choosing the right approach for each need

- **Forms for local human users:** `@DateTimeFormat(style = ...)` can fit if locale-based output is acceptable and tested across target JDKs; add legacy-compatible parsing if necessary.
- **Query/API inputs needing stability:** `@DateTimeFormat(iso = ISO.DATE)` for `LocalDate`, or `pattern = "HH:mm"` for `LocalTime` if specified by the contract.
- **Long-term storage and service-to-service exchange:** store temporal/ISO types or timestamps with defined offset/zone; avoid storing display-style strings.
- **Upgrading JDK and seeing different parsing behavior:** verify CLDR version, code points, and request locale; never judge by visual space appearance.
- **Must retain a legacy format for compatibility:** define explicit tested patterns and parsers rather than counting on legacy providers remaining available.

**Conclusion:** The same `Locale` and style can still yield different date/time patterns when the JDK or CLDR data changes. With Spring `@DateTimeFormat`, the risk affects **both parsing and printing**. Separate human display formatting from stable exchange contracts, test actual Unicode and JDK behavior, and use explicit ISO/patterns with controlled fallbacks when needed.

### Official references

- [OpenJDK JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252)
- [Oracle Java Migration Guide — Changes to Internationalization and Locale Data](https://docs.oracle.com/en/java/javase/23/migrate/preparing-migration.html)
- [Spring Framework Wiki — Date and Time Formatting with JDK 20 and Higher](https://github.com/spring-projects/spring-framework/wiki/Date-and-Time-Formatting-with-JDK-20-and-higher)
- [Spring Framework 6.1 Javadoc — DateTimeFormat](https://www.springframework.org/spring/docs/6.1.19/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html)
- [Java SE Javadoc — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java SE Javadoc — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html)
