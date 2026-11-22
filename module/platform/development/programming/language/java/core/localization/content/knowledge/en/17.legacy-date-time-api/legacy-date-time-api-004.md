# Distinguishing SimpleDateFormat Patterns from DateTimeFormatter in Java

In localized applications, a date might be displayed as `28/10/2026`, `10/28/2026`, or with month names in the user's language. Two commonly encountered Java APIs are **`java.text.SimpleDateFormat`** (the legacy date-time API) and **`java.time.format.DateTimeFormatter`** (the modern Java Time API). Both use **patterns composed of letters** such as `y`, `M`, `d`, and `H`, but **they do not share the exact same pattern language**.

Key point: **replacing `new SimpleDateFormat(pattern)` with `DateTimeFormatter.ofPattern(pattern)` cannot be treated as a safe drop-in replacement in every case.** Some symbols have different semantics, such as `S` being **milliseconds** in `SimpleDateFormat` but **fraction-of-second digits** in `DateTimeFormatter`; handling of year, week-based year, time zone, strict parsing, and input temporal types also differs.

This lesson explains each symbol group, shows where patterns can be kept and where they must be converted, and provides **standalone Java 17+** examples. The goal is to know how to read, verify, and migrate patterns accurately, not just memorize an alphabet table.

## 1. What problems do the two APIs solve?

| Criterion | `SimpleDateFormat` | `DateTimeFormatter` |
| --- | --- | --- |
| Package | `java.text` | `java.time.format` |
| Introduced | Legacy Java | Java 8+ (`java.time`) |
| Typical data formatted | `java.util.Date`, via `Calendar` and `TimeZone` | `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime`, `ZonedDateTime` when sufficient fields exist |
| Pattern creation | `new SimpleDateFormat(pattern, locale)` | `DateTimeFormatter.ofPattern(pattern, locale)` |
| Choosing time zone | `setTimeZone(TimeZone)` on mutable formatter | `withZone(ZoneId)` returns a **new** formatter, or format a temporal that already has an offset/zone |
| Choosing locale | Constructor, `DateFormatSymbols` | `ofPattern(..., locale)`, `withLocale(locale)` |
| Formatter object | **Mutable**, not thread-safe if shared without synchronization | **Immutable**, thread-safe |
| Common type parsing | `Date` via `parse(...)` | `LocalDate.parse(...)`, `OffsetDateTime.parse(...)`, etc., with an appropriate formatter |
| Resolver | `setLenient(true/false)` via `Calendar` | `ResolverStyle.SMART` (typically default), `STRICT`, `LENIENT` |
| Recommended use | Compatibility with legacy systems/libraries | New code using `java.time` |

**Do not mix up data types:** `Date` fundamentally represents an instant; `LocalDate` represents a **calendar date without time zone or time of day**, `LocalDateTime` has no offset, and `Instant` is a UTC point in time. Choose the right type before formatting; the pattern only controls how available fields are presented.

## 2. Symbols that look similar

For ordinary dates, many letters correspond closely:

| Meaning | `SimpleDateFormat` | `DateTimeFormatter` | Notes |
| --- | --- | --- | --- |
| Year of era | `y`, `yyyy` | `y`, `yyyy` | Java Time also has `u` (proleptic year), important for STRICT parsing |
| **Week-based** year | `Y`, `YYYY` | `Y`, `YYYY` | Not calendar year; depends on week/locale rules |
| Month (formatting form) | `M`, `MM`, `MMM`, `MMMM` | Equivalent | Month names depend on locale |
| Day of month | `d`, `dd` | Equivalent | `dd` typically zero-pads if needed |
| Day of year | `D` | `D` | Distinct from `d` |
| Day of week as text | `E`, `EEEE` | `E`, `EEEE` | Text depends on locale |
| Hour 0–23 | `H`, `HH` | Equivalent | Distinguish from `h` |
| Hour 1–12 | `h`, `hh` | Equivalent | Usually needs `a` (AM/PM) |
| Minute | `m`, `mm` | Equivalent | `MM` is **month**, not minute |
| Second | `s`, `ss` | Equivalent | Excludes fractional seconds |
| AM/PM | `a` | `a` | Label depends on locale |
| Short/long time zone name | `z` | `z` | Name/abbreviation depends on zone and locale |
| ISO-style offset | `X`, `XX`, `XXX` | `X`, `XX`, `XXX` | Supported counts of `X` and parsing rules are not identical |
| Milliseconds vs. fraction-of-second | `S` | `S` | **Different semantics**, see section 5 |
| Astronomical / proleptic year | No `u` equivalent to Java Time | `u`, `uuuu` | `SimpleDateFormat` uses `u` for **day number of week** (1 = Monday) |

Pattern letters are **case-sensitive**. Common pitfalls: `MM` = month, `mm` = minute; `dd` = day of month, `DD` = day of year; `yyyy` = year of era, `YYYY` = week-based year. Even if the same pattern outputs the same string for today's date, that does not prove the pattern has identical semantics on every date.

## 3. Baseline example: formatting the same instant with both APIs

Create the file **`BasicPatternDemo.java`**:

```java
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class BasicPatternDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-10-28T10:07:06.123Z");

        SimpleDateFormat legacy = new SimpleDateFormat(
                "yyyy-MM-dd HH:mm:ss.SSS", Locale.ROOT);
        legacy.setTimeZone(TimeZone.getTimeZone("UTC"));

        DateTimeFormatter modern = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm:ss.SSS", Locale.ROOT)
                .withZone(ZoneOffset.UTC);

        System.out.println("Legacy: "
                + legacy.format(Date.from(instant)));
        System.out.println("Modern: "
                + modern.format(instant));
    }
}
```

```bash
javac -encoding UTF-8 BasicPatternDemo.java
java BasicPatternDemo
```

Stdout:

```text
Legacy: 2026-10-28 10:07:06.123
Modern: 2026-10-28 10:07:06.123
```

**Why are both lines identical?**

1. Both receive the same **`Instant`**, converted to `Date` for the legacy API.
2. Both use **UTC**, avoiding dependence on the machine's default time zone.
3. The year 2026 is in the Common Era, so `yyyy` in `SimpleDateFormat` and `uuuu` in `DateTimeFormatter` both display `2026`.
4. There are exactly **123 milliseconds**; with the three-letter `SSS` pattern, both interpretations produce `123`. When changing the number of `S` letters, the difference becomes clear in section 5.

**Do not conclude the two patterns are equivalent in general:** the example above is **one matching case**. When migrating, you must inspect every token, temporal type, time zone, locale, and parsing requirement.

## 4. Years `yyyy`, `uuuu`, and week-based year `YYYY`

### `yyyy` and `uuuu` are not unconditional substitutes

In `SimpleDateFormat`, `y` represents **year** via `Calendar`; in the usual Gregorian system, `yyyy` gives the year users expect to read. `SimpleDateFormat` does not define `u` as proleptic year: the letter `u` in the legacy API means **day number of week** (Monday = 1 ... Sunday = 7).

In `DateTimeFormatter`:

- `y` = **year-of-era**, a year counted within an era, requiring an era when parsing with **STRICT** in certain scenarios.
- `u` = **proleptic year**, which can represent year 0 and BCE years in the ISO system.
- `Y` = **week-based-year**, determined by the locale's week rules; it can differ from the calendar year around year-end/year-start.

For storing machine-readable ISO dates and strict parsing, the pattern `uuuu-MM-dd` is a suitable choice. `DateTimeFormatter.ISO_LOCAL_DATE` is an even better choice when the intent is standard ISO date format, because you do not have to maintain a custom pattern for it.

### Example of STRICT parsing with year-of-era

File **`StrictYearPatternDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class StrictYearPatternDemo {
    public static void main(String[] args) {
        String text = "2026-10-28";

        DateTimeFormatter yearOfEra = DateTimeFormatter
                .ofPattern("yyyy-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter proleptic = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        try {
            LocalDate.parse(text, yearOfEra);
            System.out.println("yyyy STRICT: accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("yyyy STRICT: rejected");
        }

        System.out.println("uuuu STRICT: "
                + LocalDate.parse(text, proleptic));
    }
}
```

```bash
javac -encoding UTF-8 StrictYearPatternDemo.java
java StrictYearPatternDemo
```

Stdout:

```text
yyyy STRICT: rejected
uuuu STRICT: 2026-10-28
```

**Why was `yyyy` rejected?** The pattern contains `YEAR_OF_ERA`, without supplying an **era**. When the resolver is in STRICT mode, Java Time does not automatically assume an era to construct `LocalDate`. `uuuu` sets `YEAR` (proleptic) directly, so the date resolves without missing an era.

**Important caveat:** `yyyy-MM-dd` can still format positive dates normally, and when parsing with `ofPattern`'s default `ResolverStyle.SMART`, it may behave differently. Do not say `yyyy` is "always wrong" in `DateTimeFormatter`; the issue is **semantics and resolver strictness**.

### Why not use `YYYY-MM-dd` for calendar dates?

`YYYY` represents the **week-based** year, not the calendar year; on the last few days of December, it can belong to the following week-year. In locales like `en-US`, the start of the week and first-week criteria can differ from ISO standards. Consequently, a late-December date can format with next year's week-year while `MM-dd` still shows the previous year's month/day. This combination makes no sense as an ISO calendar date.

**Rule:** use `yyyy` for era-based dates in UIs, `uuuu` for Java Time ISO proleptic years when needed; only use `YYYY` alongside **week-of-week-based-year** fields when the data genuinely represents a week calendar. Do not replace `yyyy` with `YYYY` just because uppercase looks nicer.

## 5. The biggest difference: the `S` symbol

Across the two APIs, `S` looks the same but is interpreted differently:

| API | `S` means | Longer pattern |
| --- | --- | --- |
| `SimpleDateFormat` | **Millisecond**, an integer typically in the 0–999 range within the second | The count of `S` determines the **minimum width** when rendering the millisecond number; it does not increase physical precision beyond milliseconds |
| `DateTimeFormatter` | **Fraction-of-second** (decimal fraction of a second) | The count of `S` determines the **fractional digit width**, from 1 to 9 digits in the pattern; uses nanosecond-of-second with matching precision |

For an instant with 123 milliseconds, the pattern `SSS` prints `123` in both APIs. However, with the pattern **`SSSSSS`**, the legacy API can zero-pad `123` to `000123`, while the modern API prints six fractional second digits `123000`. These are not the same displayed value, even for the exact same instant.

### Demonstration program — `FractionPatternDemo.java`

```java
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class FractionPatternDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-10-28T10:07:06.123Z");

        SimpleDateFormat legacy = new SimpleDateFormat(
                "HH:mm:ss.SSSSSS", Locale.ROOT);
        legacy.setTimeZone(TimeZone.getTimeZone("UTC"));

        DateTimeFormatter modern = DateTimeFormatter
                .ofPattern("HH:mm:ss.SSSSSS", Locale.ROOT)
                .withZone(ZoneOffset.UTC);

        System.out.println("Legacy: "
                + legacy.format(Date.from(instant)));
        System.out.println("Modern: "
                + modern.format(instant));
    }
}
```

```bash
javac -encoding UTF-8 FractionPatternDemo.java
java FractionPatternDemo
```

Stdout (standard JDK 17):

```text
Legacy: 10:07:06.000123
Modern: 10:07:06.123000
```

**Analysis:** `123 ms = 0.123 seconds`, which is **123000 microseconds**. `DateTimeFormatter` with `SSSSSS` writes six fractional digits `123000`. In `SimpleDateFormat`, `SSSSSS` does not mean "microseconds"; it simply pads the millisecond value `123` to six digits `000123`.

When migrating legacy code with `SSSSSS` or handling timestamps with microseconds/nanoseconds, **you must redefine precision**. Standard `java.util.Date` only stores instants to millisecond precision; changing the formatter cannot recover nanoseconds that were absent from the source. `Instant`, `LocalDateTime`, and `java.time` types can carry nanosecond precision, though true precision still depends on the upstream system providing the data.

**Symbol limit:** `DateTimeFormatter` supports up to 9 `S` letters for fraction-of-second; a pattern exceeding this limit can throw `IllegalArgumentException` when creating the formatter. Do not treat a long run of `S` characters from `SimpleDateFormat` as safe to copy to the new formatter.

## 6. Letters with different meanings or unsupported letters

Several letters carry very different meanings:

| Symbol | SimpleDateFormat (Java 17) | DateTimeFormatter (Java 17) |
| --- | --- | --- |
| `u` | **Day number of week** (Monday = 1) | **Proleptic year** |
| `F` | **Day of week in month** (`Calendar.DAY_OF_WEEK_IN_MONTH`) | **Aligned day-of-week in month** (1–7 within 7-day blocks) |
| `S` | Numeric milliseconds | Fraction-of-second |
| `Y` | Week-year via `Calendar` if the calendar supports it | Localized week-based-year |
| `e` | Not a defined pattern letter in `SimpleDateFormat` | Localized day-of-week (number/text depending on width) |
| `c` | Not a pattern letter in `SimpleDateFormat` | Stand-alone localized day-of-week |
| `n` | Not a pattern letter in `SimpleDateFormat` | Nano-of-second |
| `N` | Not a pattern letter in `SimpleDateFormat` | Nano-of-day |
| `V` | Not a pattern letter in `SimpleDateFormat` | Zone ID, commonly `VV` |
| `p` | Not a pattern letter in `SimpleDateFormat` | Padding modifier for the next field |
| `B` | Not a pattern letter in `SimpleDateFormat` | Period-of-day per locale (morning/noon/afternoon...) |

For example, a legacy pattern using `F` is not guaranteed to retain its meaning if copied straight to `DateTimeFormatter`. Before changing it, determine the desired data: *the Nth occurrence of a weekday in a month* is not synonymous with *the day index within each 7-day block of the month*.

**Note on the `L` symbol:** both APIs support stand-alone month in modern JDKs, but the difference between a stand-alone month name and a month name in context still depends on locale data. Do not assume replacing `MMMM` with `LLLL` always has the same effect in every language.

### Innocuous-looking letters that cause bugs

- `MM` is month, `mm` is minute.
- `D` is day of year, `d` is day of month.
- `H` is hour 0–23; `h` is hour 1–12, used with `a` to distinguish AM/PM when needed.
- `k` is hour 1–24; `K` is hour 0–11. They cannot be arbitrarily swapped with `H`/`h`.
- `E` is day of week, while `DateTimeFormatter` also has `e`/`c` following localized/stand-alone rules; legacy code may not understand them.
- `z` is zone name or time symbol; `Z` and `X` handle offsets by different rules, not merely different spelling.

When a pattern contains a letter unrecognized by the target API, the constructor or `ofPattern` typically throws `IllegalArgumentException`, which helps catch errors early. More dangerous are **letters present in both APIs with different meanings**, because the code keeps running while producing wrong results.

## 7. Offsets and time zones: `z`, `Z`, `X`, `x`, `VV`

### Choose the right meaning before writing the pattern

- An **offset** like `+07:00` states how far local time differs from UTC. It does not contain the full history of DST rules.
- A **Zone ID** like `Asia/Ho_Chi_Minh` or `Europe/Paris` contains region information and rules for calculating the offset at any point in time.
- A **display zone name** like `GMT+07:00`, `PDT`, or a full name depends on locale and zone data and can change.

With `SimpleDateFormat`:

- `z`: time zone name/symbol.
- `Z`: RFC 822-style numeric offset, e.g. `+0700`.
- `X`, `XX`, `XXX`: ISO 8601 offset (`+07`, `+0700`, `+07:00` depending on length); at UTC it can print `Z`.

With `DateTimeFormatter`:

- `X`: ISO 8601 offset, supporting multiple lengths; `XXX` typically renders `+07:00`.
- `x`: similar to ISO offset group, except **zero offset** does not use the letter `Z` like `X`; formatting depends on length.
- `Z`: offset in various formats depending on the number of `Z` letters.
- `O`: localized zone-offset, e.g. `GMT+7`, depending on locale.
- `VV`: **zone ID**; requires a temporal with an appropriate zone.
- `z`: text zone name, depending on locale and zone data.

**You cannot simply format a `LocalDateTime` with `XXX` and expect Java to infer an offset.** `LocalDateTime` carries no zone/offset. To output an offset, pass an `OffsetDateTime`/`ZonedDateTime` or build one from an instant with an explicit zone. For `Instant`, use `DateTimeFormatter.withZone(zone)` when the pattern requires local date/time fields.

### Example of `XXX` — `OffsetPatternDemo.java`

```java
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class OffsetPatternDemo {
    public static void main(String[] args) {
        OffsetDateTime date = OffsetDateTime.parse(
                "2026-10-28T17:30:00+07:00");

        DateTimeFormatter format = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.ROOT);

        System.out.println(format.format(date));
        System.out.println(date.toInstant());
    }
}
```

```bash
javac -encoding UTF-8 OffsetPatternDemo.java
java OffsetPatternDemo
```

Stdout:

```text
2026-10-28 17:30 +07:00
2026-10-28T10:30:00Z
```

`XXX` in the example displays the offset directly from the data; `toInstant()` gives the corresponding UTC point in time. If `date` were a `LocalDateTime`, formatting with `XXX` lacks enough information and would fail. **Do not use the machine's default time zone** as an implicit workaround, especially when processing multi-user data.

## 8. Parsing differences: SimpleDateFormat leniency and ResolverStyle

### SimpleDateFormat is fairly permissive by default

`SimpleDateFormat` uses a `Calendar`. By default, calendars are usually **lenient = true**, allowing invalid dates such as an out-of-month day to be normalized into another date. Calling `setLenient(false)` rejects date/time values outside the calendar's valid ranges.

However, `setLenient(false)` **does not mean** the parser requires consuming the entire input. `DateFormat.parse(String)` can read a valid prefix and ignore trailing characters. To validate the full string, use `ParsePosition`, check that the parsed index reached the end and check the error index, along with business validation.

### DateTimeFormatter: lexical parse then resolve

`DateTimeFormatter.ofPattern(...)` normally defaults to **ResolverStyle.SMART**, not STRICT. When resolving date fields, SMART can adjust certain out-of-range day-of-month values to the last valid day of the month. `ResolverStyle.STRICT` rejects such cases, while `LENIENT` applies looser resolution rules.

For machine-readable ISO dates, use `DateTimeFormatter.ISO_LOCAL_DATE` or a `"uuuu-MM-dd"` formatter with `ResolverStyle.STRICT` when invalid inputs must be rejected. Distinguish the builder's **`parseCaseInsensitive`/`parseLenient`** (how text/widths are read) from the **resolver style** (validating the combination of date fields).

### Verification example — `ParseStrictnessDemo.java`

```java
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.TimeZone;

public class ParseStrictnessDemo {
    public static void main(String[] args) {
        String text = "2026-02-30";

        SimpleDateFormat legacy = new SimpleDateFormat(
                "yyyy-MM-dd", Locale.ROOT);
        legacy.setTimeZone(TimeZone.getTimeZone("UTC"));
        legacy.setLenient(false);

        try {
            legacy.parse(text);
            System.out.println("Legacy strict: accepted");
        } catch (ParseException ex) {
            System.out.println("Legacy strict: rejected");
        }

        DateTimeFormatter smart = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd", Locale.ROOT);
        System.out.println("Modern SMART: "
                + LocalDate.parse(text, smart));

        DateTimeFormatter strict = smart.withResolverStyle(
                ResolverStyle.STRICT);
        try {
            LocalDate.parse(text, strict);
            System.out.println("Modern STRICT: accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("Modern STRICT: rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 ParseStrictnessDemo.java
java ParseStrictnessDemo
```

Stdout:

```text
Legacy strict: rejected
Modern SMART: 2026-02-28
Modern STRICT: rejected
```

In the example above:

1. `SimpleDateFormat.setLenient(false)` rejects Feb 30, 2026.
2. `DateTimeFormatter` in `SMART` mode adjusts day 30 to the end of February, i.e. `2026-02-28`.
3. `DateTimeFormatter` in `STRICT` mode rejects the same input.
4. A new formatter is created via `withResolverStyle(...)`; the original `smart` object **is not mutated**.

For machine-readable or sensitive business data, invalid dates should not be silently turned into valid ones. Choose and test strictness explicitly.

## 9. Locale and localization data when outputting month/day names

Both formatters can obtain month or weekday names by locale:

```java
// Fragment, requiring corresponding imports.
SimpleDateFormat legacy =
        new SimpleDateFormat("dd MMMM yyyy", Locale.FRANCE);
DateTimeFormatter modern = DateTimeFormatter.ofPattern(
        "dd MMMM uuuu", Locale.FRANCE);
```

The month name string will match French when the runtime has supporting data. **Do not assume** that changing the locale affects only month names: calendar system, week rules, digits, eras, and AM/PM phrasing can also differ.

- With `SimpleDateFormat`, pass `Locale` to the constructor. Use `setTimeZone` or an appropriate `Calendar` when formatting a `Date`. Omitting the timezone can make results depend on the JVM default.
- With `DateTimeFormatter`, pass the locale to `ofPattern(pattern, locale)` or use `withLocale(locale)`; formatting `LocalDate` needs no timezone, whereas `Instant` with a local date/time pattern requires a zone.
- When formatting for a user's UI, pass **an explicit locale**. Do not call `Locale.setDefault(...)` on each HTTP request because it affects the entire JVM.

### Why might month names not match despite identical patterns?

`SimpleDateFormat` uses `DateFormatSymbols` and the legacy calendar, while `DateTimeFormatter` relies on `java.time` locale data and fields. Across different JDKs/providers or chronologies, month spelling, stand-alone `L` vs. contextual `M` forms, eras, or weeks can differ. In tests, verify the right locale and semantically correct output; if exact string snapshots are a product requirement, pin the JDK/provider/locale-data version.

For text coming from a `ResourceBundle`, do not put a `"YYYY-MM-dd"` pattern in merely by copying older data. A pattern is a mini-language; translators may change ordering and separators, but token letters must be reviewed like code.

## 10. Step-by-step migration from a legacy SimpleDateFormat to DateTimeFormatter

Legacy code example:

```java
SimpleDateFormat format = new SimpleDateFormat(
        "yyyy-MM-dd HH:mm:ss.SSS", Locale.US);
format.setTimeZone(TimeZone.getTimeZone("UTC"));
String text = format.format(date);
```

This is a **fragment** with a `date` variable of type `java.util.Date` already declared. To migrate:

1. **Document the meaning of the input data**: `Date` (instant), calendar date, local datetime, or offset datetime.
2. **Read the entire pattern carefully**, identifying `yyyy`/`YYYY`, `S`, `F`, `u`, `X`, zone names, and any symbols whose meaning could change.
3. **Choose the appropriate Java Time type**: `Instant` for a point in time, `LocalDate` for a calendar date, `OffsetDateTime`/`ZonedDateTime` when an offset/zone is present.
4. **Choose an explicit locale** and **explicit zone** if formatting an instant into local date and time.
5. **Convert the pattern by semantics**, e.g. `yyyy` → `uuuu` when you want proleptic year and strict date parsing; `SSS` can remain for milliseconds, whereas a `SSSSSS` pattern must be redesigned for actual precision.
6. **Choose the resolver style when parsing**, without assuming `ofPattern` is STRICT.
7. **Test boundary cases**: New Year / week-year, leap years / invalid dates, Jan/Dec, timezone/DST transitions, UTC offsets, timestamps with milliseconds/microseconds/nanoseconds, multiple locales.
8. **Update formatter lifecycle**: `DateTimeFormatter` is immutable so it can be shared for fixed configurations; avoid reusing mutable `SimpleDateFormat` across threads.

### Java 17+ example converting Date to Instant

Save **`MigrationDemo.java`**:

```java
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class MigrationDemo {
    public static void main(String[] args) {
        Date date = Date.from(Instant.parse(
                "2026-10-28T10:07:06Z"));

        SimpleDateFormat legacy = new SimpleDateFormat(
                "yyyy-MM-dd HH:mm:ss", Locale.ROOT);
        legacy.setTimeZone(TimeZone.getTimeZone("UTC"));

        DateTimeFormatter modern = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm:ss", Locale.ROOT)
                .withZone(ZoneOffset.UTC);

        String first = legacy.format(date);
        String second = modern.format(date.toInstant());

        System.out.println("Legacy: " + first);
        System.out.println("Modern: " + second);
        System.out.println("Same text: " + first.equals(second));
    }
}
```

```bash
javac -encoding UTF-8 MigrationDemo.java
java MigrationDemo
```

Stdout:

```text
Legacy: 2026-10-28 10:07:06
Modern: 2026-10-28 10:07:06
Same text: true
```

This is a **migration with clear conditions**: same instant, same UTC timezone, same date/time fields, and same second precision. In new code, if standard machine-readable formatting is desired, consider using `Instant.toString()`/`DateTimeFormatter.ISO_INSTANT` or `ISO_LOCAL_DATE` instead of inventing custom date-time strings unnecessarily.

## 11. Thread safety: why prefer DateTimeFormatter

`SimpleDateFormat` extends `DateFormat` and carries mutable state such as `Calendar`, `NumberFormat`, `TimeZone`, and leniency settings. An instance **is not guaranteed to be safe** when multiple threads call `format`/`parse` concurrently without synchronization. Failure symptoms can vary under load and be hard to reproduce.

`DateTimeFormatter` is immutable and thread-safe. Methods such as `withLocale(...)`, `withZone(...)`, and `withResolverStyle(...)` return a new formatter (or equivalent effective instance) without mutating the original object. This allows using a `static final DateTimeFormatter` for an immutable configuration, or deriving per-request formatters when locales differ.

**Proper design:**

```java
// Fragment inside a Java class:
private static final DateTimeFormatter WIRE_DAY =
        DateTimeFormatter.ISO_LOCAL_DATE;

static String formatDay(java.time.LocalDate day) {
    return WIRE_DAY.format(day);
}
```

For user locales, do not share a formatter and change `Locale.setDefault`; use `BASE.withLocale(uiLocale)` or create a formatter per locale, and keep separate formatters if zones differ.

If `SimpleDateFormat` must be retained for legacy APIs, create an instance per operation/request, or use synchronization and an appropriate state-management strategy. `ThreadLocal<SimpleDateFormat>` can solve some cases at the cost of lifecycle management overhead; there is no reason to prefer it if migrating to `java.time` is possible.

## 12. Literals in patterns: single quotes and fixed text

Both APIs use single quotes to **quote literals**, though you should still check each API's docs for complex patterns. The `'` character opens/closes a literal string; to include an actual single quote in the output, use `''` in the pattern.

Example:

```java
DateTimeFormatter format = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd 'at' HH:mm", Locale.ROOT);
```

This is a **fragment**; formatting a `LocalDateTime` for Oct 28, 2026 at 10:30 outputs `2026-10-28 at 10:30`.

**Do not insert month/hour labels as unquoted text.** The letter `T` between date and time is a literal in ISO datetimes, yet a hand-written pattern like `uuuu-MM-ddTHH:mm` causes `DateTimeFormatter` to treat `T` as an invalid pattern letter. Write `"uuuu-MM-dd'T'HH:mm"` if you want a literal `T`; better yet, use predefined ISO formatters when appropriate.

**Note:** date-time strings from users or bundles may contain `'` characters from natural language. If content is literal data rather than a pattern, never pass it straight into `ofPattern`. Separate *trusted patterns* from *untrusted text* to avoid syntax errors and output corruption.

## 13. Common mistakes when copying patterns from the legacy API

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Copying `yyyy-MM-dd` and using STRICT parsing in DateTimeFormatter | Missing era, fails to resolve `LocalDate` | Use `uuuu-MM-dd` or predefined ISO |
| Using `YYYY-MM-dd` for calendar dates | Wrong year near week-year boundaries | Use calendar year; avoid `Y` unless representing a week calendar |
| Copying `SSSSSS` | Zero-padded milliseconds differ from six fractional second digits | Redefine precision and convert the right field |
| Changing `SimpleDateFormat("u")` to `ofPattern("u")` | Changes from **day of week** to **proleptic year** | Convert by semantics, not by character |
| Keeping `F` without checking its meaning | The two APIs interpret it differently | Pick the temporal field matching business rules |
| Using `mm` to print month | Actually prints minutes | Use `MM` |
| Using `DD` instead of `dd` | Day of year instead of day of month | Use `dd` |
| Assuming `DateTimeFormatter.ofPattern` defaults to STRICT | SMART can adjust invalid dates | Use `withResolverStyle(STRICT)` when needed |
| Formatting `LocalDateTime` with `XXX` | No offset available to output | Pick `OffsetDateTime`/explicit zone |
| Formatting `Instant` with a local pattern without a zone | Missing local calendar fields | `withZone(ZoneId)` |
| Not specifying TimeZone on SimpleDateFormat | Output depends on JVM default | Explicit `setTimeZone` |
| Creating a static SimpleDateFormat shared across requests | Not thread-safe | Separate formatters or switch to immutable DateTimeFormatter |
| Using `DateFormat.parse(String)` to validate entire input | Can ignore trailing garbage | ParsePosition + validation |
| Forgetting to quote literal `T` | Invalid pattern error | `'T'` in pattern or ISO formatter |
| Using abbreviated timezone names as storage keys | Ambiguous/locale-dependent | Store ZoneId/offset/Instant per schema |
| Trusting a calendar date represented as UTC midnight | Meaning can shift when changing timezones | Use LocalDate for pure dates |

## 14. Testing patterns during migration

A thorough test suite should include:

1. **Normal dates:** compare the same instant, same zone, same locale, and precision across both formatters.
2. **Year-end / year-start dates:** check `yyyy`/`YYYY`/`uuuu`; test locales with different week rules.
3. **Invalid dates:** Feb 30, Apr 31, leap years, and STRICT vs. SMART vs. lenient parsing.
4. **Fractions:** 000 ms, 007 ms, 123 ms, 999 ms, and instants with micro/nanoseconds. Compare `SSS` and `SSSSSS`.
5. **Time zones/offsets:** UTC `Z`, `+07:00`, DST regions; format and parse offsets with matching patterns.
6. **Locales:** full and abbreviated month names; AM/PM; week calendars; test on target locale/provider data.
7. **Long/abnormal inputs:** extra trailing chars, missing fields, out-of-range values, literals in patterns.
8. **Multithreading:** only share immutable `DateTimeFormatter`; never share mutable `SimpleDateFormat` without synchronization.
9. **Legacy sources:** calendar settings (Gregorian cutover, other calendars) and timezones in legacy programs may differ from `java.time`'s ISO chronology. For historical dates before the Gregorian/Julian cutover or non-ISO calendars, do not expect identical results without explicit calendar conversion.
10. **Data contracts:** for files/APIs, prefer stable ISO formatters, use strict parsing for date fields, and never let default locale/timezone dictate how data is interpreted.

### Exercise 1 — Identify wrong tokens

Given the patterns `"YYYY-MM-dd"`, `"yyyy-MM-DD"`, `"yyyy-mm-dd"`, and `"uuuu-MM-dd"`. State which symbols represent calendar year, week-year, month, minute, day of month, and day of year. For `DateTimeFormatter`, which pattern is more suitable for STRICT ISO `LocalDate` parsing?

### Exercise 2 — Fractional seconds

Given `Instant.parse("2026-10-28T10:07:06.123Z")`. Predict the results of `SSS` and `SSSSSS` when formatted with `SimpleDateFormat` UTC/`Date` and `DateTimeFormatter` UTC/`Instant`. Change the input to an `Instant` with `123456789` nanoseconds and explain why `Date` cannot preserve full nanosecond precision.

### Exercise 3 — Parsing invalid dates

With `"2026-02-30"`, use `SimpleDateFormat.setLenient(false)`, default `DateTimeFormatter.ofPattern("uuuu-MM-dd")`, and that formatter with `ResolverStyle.STRICT`. Compare the behavior and identify the mode suitable for machine-readable data.

### Exercise 4 — Zone and Locale

Format the same instant in UTC and `+07:00` with a pattern containing offset `XXX`. Explain why `LocalDateTime` cannot provide an offset on its own. Then use locales `en-US` and `fr-FR` when printing month names, checking output on your JDK.

## 15. Official documentation

- [Java SE 21 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html): pattern letters, `S`, `u`, `F`, timezone, and non-synchronization.
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): pattern letters, `S`, `u`, `Y`, `X`, resolver style, `ofPattern`, `withZone`.
- [Java SE 21 — ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html): `STRICT`, `SMART`, `LENIENT`.
- [Java SE 21 — LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html): calendar date and parsing.
- [Java SE 21 — Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html): UTC point in time.

## 16. Key takeaways

- `SimpleDateFormat` and `DateTimeFormatter` patterns **partially overlap, and are not a 1–1 match**.
- `yyyy` in `DateTimeFormatter` is **year-of-era**; `uuuu` is **proleptic year**; `YYYY` is **week-based-year**. Meanwhile, `SimpleDateFormat` uses `u` for **day of week**.
- `S` in `SimpleDateFormat` is **milliseconds**; in `DateTimeFormatter` it is **fraction-of-second**. `SSS` may match, but `SSSSSS` produces two different representations.
- `SimpleDateFormat` is mutable and not thread-safe; `DateTimeFormatter` is immutable and thread-safe.
- `SimpleDateFormat` and `DateTimeFormatter` parsing have different policies: `setLenient(false)`, `ResolverStyle.SMART`, and `ResolverStyle.STRICT` are not direct drop-in switches.
- Offset and zone are not the same thing. `XXX` requires offset data; `Instant` requires a zone to format local date/time components.
- When migrating, **verify data semantics and each token**, choose explicit locale/zone, use predefined ISO formatters for machine-to-machine exchange, and test across many dates/locales/timezones, especially boundary cases.
