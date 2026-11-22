# FormatStyle: FULL, LONG, MEDIUM, and SHORT in Java

## 1. Why Does the Same Date-Time Have Multiple Presentations?

For the same instant, an application may need to show a full date in an email, a short date in a list, or a time with a time zone in an appointment. For example, a date is represented briefly in the US as `10/28/26`, whereas the full US format is `Wednesday, October 28, 2026`. Presentation rules also vary by language, region, JDK locale data, and date-time value type.

Modern Java uses `java.time.format.DateTimeFormatter` together with `java.time.format.FormatStyle` to request a **level of detail** rather than fixing one manual pattern for every language. The four levels are:

- `FormatStyle.FULL` — the fullest representation, usually including weekday/day/month names, and time-zone information when formatting times.
- `FormatStyle.LONG` — long and informative, though typically omitting some details compared to FULL.
- `FormatStyle.MEDIUM` — medium length, suitable for many everyday display contexts.
- `FormatStyle.SHORT` — compact, typically numeric and omitting seconds in the time component.

**Key point:** `FormatStyle` describes only the level of presentation detail; it is **not** a fixed pattern like `"dd/MM/yyyy"`, not a `Locale`, not a `ZoneId`, and it does not turn a zone-less date-time into a global instant.

Lesson goals: understand the four style levels, how to use them with date/time/date-time, choosing the right `LocalDate`/`LocalTime`/`LocalDateTime`/`ZonedDateTime` type, distinguishing locale from time zone, parsing with styles, testing, and avoiding bugs caused by expecting an invariant output string across all JDKs.

## 2. What Enum Is FormatStyle?

`FormatStyle` is an enum in `java.time.format`:

```java
import java.time.format.FormatStyle;

FormatStyle full = FormatStyle.FULL;
FormatStyle longStyle = FormatStyle.LONG;
FormatStyle medium = FormatStyle.MEDIUM;
FormatStyle shortStyle = FormatStyle.SHORT;
```

The names of the four constants indicate the **relative length** of the localized representation. The concrete meaning is decided by locale data. For example:

| Style | Illustrative date in `en-US` | Meaning |
| --- | --- | --- |
| `FULL` | `Wednesday, October 28, 2026` | Includes full weekday and month names |
| `LONG` | `October 28, 2026` | Full month name, not necessarily weekday |
| `MEDIUM` | `Oct 28, 2026` | Abbreviated month name |
| `SHORT` | `10/28/26` | Compact numeric form |

These are **examples based on en-US locale data in a modern JDK**, not four fixed strings mandated by the enum. For `vi-VN`, `de-DE`, `ja-JP`, and others, day/month/year order, separators, weekday names, 12/24-hour clock format, and connecting words can differ. The JDK can update CLDR data across versions, so changes in punctuation or abbreviations do not mean your code is broken.

There is no `FormatStyle.DEFAULT` value, and you cannot pass a string name `"FULL"` in place of the enum without explicit conversion. In application code, prefer using the constants `FormatStyle.FULL`, `LONG`, `MEDIUM`, and `SHORT`.

## 3. Three Main Factories of DateTimeFormatter

`DateTimeFormatter` provides dedicated factories:

| Factory | Data presented | Example |
| --- | --- | --- |
| `ofLocalizedDate(style)` | Date only | `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)` |
| `ofLocalizedTime(style)` | Time of day only, possibly with time zone depending on style | `DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)` |
| `ofLocalizedDateTime(style)` | Both date and time with the same style | `DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)` |
| `ofLocalizedDateTime(dateStyle, timeStyle)` | Both date and time, with separate styles chosen | `DateTimeFormatter.ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT)` |

**Locale is passed via `withLocale(...)`**, not as an argument to the four factories above:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

LocalDate date = LocalDate.of(2026, 10, 28);
DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.FULL)
        .withLocale(Locale.US);

String display = date.format(formatter);
```

This is a snippet placed inside a method. Typical output with `Locale.US` is `Wednesday, October 28, 2026`.

`DateTimeFormatter` is **immutable and thread-safe**. `withLocale(locale)` creates a formatter configured for that locale without mutating the original formatter. You do not need to call `Locale.setDefault(...)` per request, as that is JVM-wide state that can affect concurrent requests.

### Choosing the right input temporal type

| Input type | What information does it contain? | Suitable for |
| --- | --- | --- |
| `LocalDate` | Year/month/day, no time or zone | `ofLocalizedDate(...)` |
| `LocalTime` | Hour/minute/second, no date/zone | `ofLocalizedTime(SHORT/MEDIUM)` when the pattern does not require a zone |
| `LocalDateTime` | Local date and time, **no zone/offset** | Date/time with styles not needing a zone, depending on locale data |
| `OffsetDateTime` | Date-time and UTC offset | Formats needing an offset; full time-zone names may require `ZoneId` |
| `ZonedDateTime` | Date-time with `ZoneId`/offset | Safe for examples like FULL/LONG that may print zone information |
| `Instant` | A point on the UTC timeline | Convert via `atZone(zone)` to obtain local date-time before formatting |

**Do not assume every style will format every `TemporalAccessor` successfully.** For example, `LocalDate` has no time fields and `LocalTime` has no date fields; FULL/LONG time may require a zone name, whereas `LocalTime` and `LocalDateTime` lack that information. If a field required by the pattern is missing, Java can throw `DateTimeException`, typically `UnsupportedTemporalTypeException`.

## 4. Java 17+ Demo: Inspecting All Four Styles on One Date-Time

Create the file **`FormatStyleDemo.java`** (a standalone Java class):

```java
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class FormatStyleDemo {
    public static void main(String[] args) {
        ZonedDateTime moment = ZonedDateTime.of(
                2026, 10, 28, 14, 35, 6, 0,
                ZoneId.of("Asia/Ho_Chi_Minh"));
        Locale locale = Locale.US;

        for (FormatStyle style : FormatStyle.values()) {
            DateTimeFormatter date = DateTimeFormatter
                    .ofLocalizedDate(style).withLocale(locale);
            DateTimeFormatter time = DateTimeFormatter
                    .ofLocalizedTime(style).withLocale(locale);
            DateTimeFormatter dateTime = DateTimeFormatter
                    .ofLocalizedDateTime(style).withLocale(locale);

            System.out.println("Style: " + style);
            System.out.println("Date: " + date.format(moment));
            System.out.println("Time: " + time.format(moment));
            System.out.println("DateTime: " + dateTime.format(moment));
        }
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac -encoding UTF-8 FormatStyleDemo.java
java FormatStyleDemo
```

**Example output under JDK 24 en-US data** (the whitespace character before `PM` may be a narrow no-break space, not necessarily an ASCII space):

```text
Style: FULL
Date: Wednesday, October 28, 2026
Time: 2:35:06 PM Indochina Time
DateTime: Wednesday, October 28, 2026, 2:35:06 PM Indochina Time
Style: LONG
Date: October 28, 2026
Time: 2:35:06 PM GMT+07:00
DateTime: October 28, 2026, 2:35:06 PM GMT+07:00
Style: MEDIUM
Date: Oct 28, 2026
Time: 2:35:06 PM
DateTime: Oct 28, 2026, 2:35:06 PM
Style: SHORT
Date: 10/28/26
Time: 2:35 PM
DateTime: 10/28/26, 2:35 PM
```

**Do not write automated tests comparing this output table verbatim across all JDKs.** CLDR data and locale providers can change wording, punctuation, zone names, or space characters. What remains invariant is that the same date-time is expressed at different levels of detail; FULL is generally more detailed than SHORT, and the underlying date-time value does not change.

Explanation of each part:

1. `ZonedDateTime.of(...)` creates 2026-10-28 at 14:35:06 in time zone `Asia/Ho_Chi_Minh`. By passing an object **with a zone**, both FULL and LONG time have sufficient data if the pattern needs a zone name or offset.
2. `withLocale(Locale.US)` selects US English presentation rules. It does not change the time or time zone of `moment`.
3. `ofLocalizedDate(style)` omits the time from the string, `ofLocalizedTime(style)` omits the date, and `ofLocalizedDateTime(style)` displays both.
4. `SHORT` may omit seconds and use a two-digit year; this **does not mean** the time is rounded or the year data is truncated inside the `ZonedDateTime` object.
5. Strings like `Indochina Time` and `GMT+07:00` are time-zone/display data, not derived from `Locale.US`.

## 5. Comparing FULL, LONG, MEDIUM, and SHORT by UI Purpose

### FULL: prioritizes completeness and clarity for readers

`FULL` is suitable when readers need full weekday/month names and, in some languages, explicit time-zone information. For an important appointment or confirmation email, the long form can reduce ambiguity compared to `10/28/26`. However, FULL takes up more space and still depends on the selected language.

### LONG: still contextually clear, yet more compact than FULL

`LONG` usually retains full month names, and for times may include zone/offset information. It is a good fit for detailed explanations, detail pages, or reports, though you should not assume LONG is always identical to FULL minus the weekday name; pattern structure comes from locale data.

### MEDIUM: compromise between clarity and screen space

`MEDIUM` typically abbreviates the month or date separators while still showing hours/minutes/seconds depending on context. It can be a convenient default in tables and everyday UI when the product does not mandate an exact format. If zone information must appear, add a zone explanation per UI rules; MEDIUM does not guarantee zone output.

### SHORT: saves space, but can be ambiguous

`SHORT` typically uses numeric components, two-digit years, or times without seconds. For example, `10/11/26` can be read as October 11 or November 10 if shown to a user from another region. Use it only when the locale context is clear and cannot mislead the reader, especially in contracts, cross-timezone appointments, and legal content.

| UI requirement | Reference style | Considerations |
| --- | --- | --- |
| Important appointment details | `FULL` or `LONG` | Show time zone, day of week |
| Order information page | `LONG` or `MEDIUM` | Clear day/month/year |
| Lists or data tables | `MEDIUM` or `SHORT` | Column width, which locale viewers understand |
| Compact calendar time | `SHORT` | If seconds/zone are needed, style may be insufficient |
| Application logs / APIs | Do not prefer `FormatStyle` | Use stable ISO 8601 independent of locale |

These are selection suggestions by display level, not a rule that every style always contains the exact components shown in the table.

## 6. Locale and Time Zone Are Two Independent Concepts

- **`Locale`**: preferred language/region for **presentation**, such as `vi-VN`, `en-US`.
- **`ZoneId`**: time zone used to derive **local time from an `Instant`**, such as `Asia/Ho_Chi_Minh`, `Europe/Berlin`.
- **`Instant`**: a unique point on the UTC timeline, independent of locales.

A user who chooses a Vietnamese UI may be in Germany; a user who chooses an English UI may be viewing times in Ho Chi Minh City. Never infer a time zone solely from a language tag.

### Example: same Instant, two time zones

Create the standalone file **`TimeZoneFormatDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class TimeZoneFormatDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-10-28T07:35:06Z");

        ZonedDateTime inVietnam =
                instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        ZonedDateTime inUtc = instant.atZone(ZoneOffset.UTC);

        System.out.println("Vietnam: "
                + inVietnam.toLocalDateTime() + " " + inVietnam.getOffset());
        System.out.println("UTC: "
                + inUtc.toLocalDateTime() + " " + inUtc.getOffset());

        DateTimeFormatter visible = DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT)
                .withLocale(Locale.US);
        System.out.println("Vietnam formatted: " + visible.format(inVietnam));
        System.out.println("UTC formatted: " + visible.format(inUtc));
    }
}
```

Run:

```bash
javac -encoding UTF-8 TimeZoneFormatDemo.java
java TimeZoneFormatDemo
```

The first two lines are **stable per the `java.time` data in the example**:

```text
Vietnam: 2026-10-28T14:35:06 +07:00
UTC: 2026-10-28T07:35:06 Z
```

The two `formatted` lines for `Locale.US` on JDK 24 take an illustrative form such as:

```text
Vietnam formatted: Oct 28, 2026, 2:35 PM
UTC formatted: Oct 28, 2026, 7:35 AM
```

The displayed lines may differ in whitespace or punctuation on other JDK versions, yet both represent **the same `Instant`**. Separate the two levels: convert `Instant` to a zone to find local time, then format according to locale to produce a human-readable string.

### Why not use FULL time with LocalTime?

`LocalTime.of(14, 35)` only knows hour/minute/second; it does not know the date, offset, or zone. If the `FormatStyle.FULL` pattern in a given locale requires a zone name, the formatter cannot deduce it from `LocalTime`, leading to `DateTimeException`. `LocalDateTime` likewise carries no time zone. Use `ZonedDateTime` for FULL/LONG examples with a zone. Do not catch the exception and silently force `UTC` when the user's actual time zone has not been determined.

## 7. Combining Two Separate Styles for Date and Time

Sometimes the UI needs a fairly detailed date alongside a very compact time. The two-argument factory supports this:

```java
DateTimeFormatter mixed = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT)
        .withLocale(Locale.US);

String label = mixed.format(zonedDateTime);
```

This is a **snippet**; the variable `zonedDateTime` must have an appropriate type such as `ZonedDateTime`. Unlike the single-argument `ofLocalizedDateTime(FormatStyle.MEDIUM)` (where both date and time are MEDIUM), the two-argument overload allows:

- `LONG` date + `SHORT` time.
- `FULL` date + `MEDIUM` time.
- `SHORT` date + `LONG` time (which may require a time zone).

However, the chosen styles still result in a **locale-dependent pattern**. Do not predict the output by manually concatenating `ofLocalizedDate(...).format(value) + ", " + ofLocalizedTime(...).format(value)`: combining date and time in a language may involve connecting words or reordered components. Let `ofLocalizedDateTime(...)` apply the locale's combination rules.

If the product requires a fixed layout or a protocol format, use `DateTimeFormatter.ofPattern(pattern, locale)` or standard ISO formatters. Do not use localized styles for data fields that must be compared byte-for-byte between two systems.

## 8. Distinguishing FormatStyle from Custom Patterns

| Topic | `FormatStyle` with localized factories | `DateTimeFormatter.ofPattern(...)` |
| --- | --- | --- |
| Component ordering rules | Determined by locale/provider | Determined by the pattern author |
| Date/month/time symbols | Typically localized by locale | Controlled by pattern letters, while month/AM-PM names depend on locale |
| Can change with JDK locale data | Yes | Yes for translated/localized names, but pattern structure is fixed |
| Use for multilingual UI | Usually convenient | Useful when design requires a specific layout |
| Use as machine-to-machine protocol | Should not | Prefer ISO 8601 rather than ad-hoc locale patterns |
| Ability to specify exact seconds or zone | Depends on style and provider | Explicitly controllable via pattern |

Example:

```java
DateTimeFormatter localized = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(Locale.GERMANY);

DateTimeFormatter fixedPattern = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.GERMANY);
```

`localized` follows the SHORT rules defined by the locale provider; `fixedPattern` fixes the positions of day/month/year and a four-digit year width. Thus there is no guarantee the two formatters produce the same string.

An easy confusion: `MM` is **month**, `mm` is **minute**; `HH` is 24-hour clock, `hh` is 12-hour clock (usually needing `a` for AM/PM). Do not copy patterns from English examples while ignoring local reading conventions. For years, `uuuu` is proleptic year and `yyyy` is year-of-era. Choose based on your data model and system rules.

## 9. Parsing with Localized FormatStyle and Its Limitations

`DateTimeFormatter` not only provides `format`, it also supports `parse`. You can use the same style/locale to parse a date string:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

DateTimeFormatter parser = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(Locale.US);

String input = "10/28/26";
LocalDate parsed = LocalDate.parse(input, parser);
```

The example above corresponds to common en-US SHORT display and is a **snippet**; the expected result is `2026-10-28` in an environment using that pattern. However, SHORT patterns can use two-digit years, so parsing is subject to **reduced-year resolution rules**; if the input is legal data or machine-generated, avoid two-digit years and avoid implicit locale dependence.

Keep in mind:

1. **The locale must match** the entered string: US `10/28/26` should not be arbitrarily interpreted with a `vi-VN` or `de-DE` formatter.
2. **When parsing FULL/LONG with month/weekday names**, the language and word forms must be supported properly by the provider. A weekday that disagrees with the date can cause parsing to fail.
3. **Do not use localized text as a storage format**: it depends on JDK configuration, cultural symbols, and can be ambiguous.
4. `DateTimeFormatter` has a default resolver style and rules for resolving fields into `LocalDate`/`LocalTime`; if strict validation is needed, consider `withResolverStyle(ResolverStyle.STRICT)` and test the chosen fields.
5. A FULL/LONG time formatter may require a zone when parsing; you need an appropriate temporal model.
6. **Do not assume format -> parse is a lossless round-trip**: SHORT can drop seconds or full four-digit years, and a date-only formatter will not store times.

For APIs and data between services, use standard representations such as `Instant.toString()`/`Instant.parse(...)` or `DateTimeFormatter.ISO_OFFSET_DATE_TIME`, depending on the data contract. Localized styles are designed for **communicating with humans**.

## 10. Testing FormatStyle Properly

Good tests do not merely assert a single hardcoded string. You should test:

| Case | Check |
| --- | --- |
| Four `FormatStyle` values | All factories return valid formatters and format appropriate temporals |
| Dates with full day/month/year | Correct calendar date, not shifted by unintended time-zone conversion |
| FULL/LONG time | Temporal has a zone if the locale requires a zone |
| `LocalDate` with `ofLocalizedTime` | Receives an error due to missing time fields; does not silently assume 00:00 |
| `LocalTime` with `ofLocalizedDate` | Receives an error due to missing date |
| `en-US` and `vi-VN` locales | Observe day/month order, text, and 12/24-hour conventions |
| Different time zones | Same `Instant` shows different local times without changing the instant |
| Year transitions or DST | Instants near boundaries can fall on a different date depending on zone |
| Parsing SHORT | Watch out for two-digit years and ambiguous input strings |
| JDK/CLDR upgrades | Accept valid presentation changes; keep snapshot tests scoped with clear versions |

### Avoid overly brittle snapshot tests tied to locale data

A snapshot like "FULL is always `Wednesday, October 28, 2026 at ...`" will easily break when a provider changes punctuation, connectors, spacing, or zone names. If the test's goal is business logic, verify the input instant and locale are correct, and use output snapshots only in CI environments with a pinned JDK/provider. For products requiring exact wording as designed, consider custom patterns or resource-managed text.

### When backward compatibility is required

`java.time` and `FormatStyle` work from Java 8+; they are not exclusive to Java 17. For systems using `java.text.DateFormat`, there are `DateFormat.FULL`/`LONG`/`MEDIUM`/`SHORT` constants with a similar purpose, but that is **a different API whose legacy formatters are mutable and not generally thread-safe**. Do not mix up constants between the two APIs or assume a `DateFormat` and a `DateTimeFormatter` always produce byte-for-byte identical output.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `FULL`/`LONG` as fixed global patterns | Breaks when switching locale or JDK | Understand these are display levels, not fixed templates |
| Formatting `LocalTime` with FULL and getting an error | Temporal lacks a zone for the time pattern | Use `ZonedDateTime` or pick an appropriate style |
| Choosing `Locale.US` and thinking time automatically converts to US time | Locale only affects language/presentation | Convert `Instant` with a separate `ZoneId` |
| Using `LocalDateTime` to represent a UTC instant | Has no offset/zone so it does not identify an instant | Use `Instant`/`OffsetDateTime`/`ZonedDateTime` |
| Using `SHORT` when seconds and full time zone are needed | Important information may be omitted | Pick another style or a pattern with explicit requirements |
| Hardcoding `10/28/26` for all users | Readers in other regions misread day/month | Choose the right locale, or an unambiguous representation |
| Using localized formatters as a serialization standard | Strings change when JDK/locale changes | Use ISO 8601 and a time contract with zone/offset |
| Manually concatenating date + time strings | Wrong order or phrasing for a locale | Use `ofLocalizedDateTime(...)` |
| Calling `withLocale` and expecting the original object to change | Formatters are immutable | Capture and use the returned formatter object |
| Parsing two-digit SHORT years without checks | May resolve to a different year than intended | Use four-digit years per input contract |
| Changing `Locale.setDefault` per request | Affects multiple threads in the JVM | Pass locale explicitly to the formatter |
| Comparing exact output across multiple CLDR versions | Flaky tests, false failures | Pin the test environment or assert semantics |
| Confusing `FormatStyle` with `DateFormat` constants | Wrong API or parameter type | Use the right `java.time.format.FormatStyle` import |

## 12. Review Questions

**Question 1.** Does `FormatStyle.FULL` always include both weekday name and time-zone name in every formatter?

**Answer:** No. The content depends on the `Locale` and the date/time/date-time factory. Date-only formatters have no time-zone information; FULL time in many locales may require a zone to print the time-zone name.

**Question 2.** You want to display a LONG date with a SHORT time. Which API do you need?

**Answer:** `DateTimeFormatter.ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT).withLocale(locale)`. This uses the locale's date/time combination rules.

**Question 3.** Given only `LocalDate.of(2026, 10, 28)`, can you use `ofLocalizedTime(SHORT)` to default to 00:00?

**Answer:** No. `LocalDate` has no time fields. Java can throw `DateTimeException` because the temporal lacks the information; if you want to display 00:00, you must specify the time explicitly.

**Question 4.** Two users view the same `Instant` with different `ZoneId` values. Has the event data changed?

**Answer:** No. `Instant` does not change; only the local date-time and display change.

**Question 5.** Should `FormatStyle.SHORT` be used as a database storage format for dates?

**Answer:** No. It is a localized string for human readers, can be ambiguous, and can vary by JDK/provider. Machine data should store `LocalDate` or ISO 8601 per design.

**Question 6.** Why doesn't calling `withLocale(Locale.forLanguageTag("vi-VN"))` guarantee that the current time is Vietnam time?

**Answer:** Locale only selects display rules; you need `ZoneId.of("Asia/Ho_Chi_Minh")` or the user's actual zone to convert an `Instant`.

**Question 7.** Why can two JDKs produce different punctuation or spacing for DATE FULL given the same input?

**Answer:** The presentation is supplied by each JDK's locale data (usually from CLDR) and provider; updates may change patterns, month names, or punctuation.

## 13. Key Takeaways

- `FormatStyle` has four values—**FULL, LONG, MEDIUM, SHORT**—describing **locale-based** detail levels, not fixed patterns.
- Use `DateTimeFormatter.ofLocalizedDate`, `ofLocalizedTime`, and `ofLocalizedDateTime`; you can specify **two independent styles** for date and time.
- Always choose a temporal containing all fields the formatter needs. In particular, FULL/LONG time may require zone information.
- **`Locale` controls presentation; `ZoneId` controls local time**. The same `Instant` is unchanged when displayed in another region.
- Use localized styles for the **UI**; data and APIs should use ISO formats and clear time contracts. Do not compare localized output as an invariant string across all JDKs.

Official documentation:

- [Java SE 21 — FormatStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/FormatStyle.html)
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java SE 21 — ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)
- [Unicode CLDR — Date/Time patterns](https://cldr.unicode.org/translation/date-time/date-time-patterns)
