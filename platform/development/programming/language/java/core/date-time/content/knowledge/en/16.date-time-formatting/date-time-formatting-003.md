# Creating Date-Time Format Patterns with `DateTimeFormatter.ofPattern()`

A date-time value can be displayed in many string formats depending on the purpose: `2026-10-24T09:05:07` for machine data, `24/10/2026 09:05` for Vietnamese forms, or `Sat, 24 Oct 2026` for an English UI. The temporal value does not change; the **pattern** determines how it is represented.

In Java, `DateTimeFormatter.ofPattern(pattern)` creates a formatter from a pattern string. This lesson explains pattern syntax, date and time symbols, fractional seconds, `Locale`, offset and zone, parsing strings back, and common mistakes that cause incorrect data. Examples use Java 17+ and `java.time`.

## 1. Formatting Is Converting a Value to a String

~~~java
LocalDateTime value = LocalDateTime.of(2026, 10, 24, 9, 5, 7);
DateTimeFormatter fmt =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm:ss");
String result = value.format(fmt);
System.out.println(result); // 24/10/2026 09:05:07
~~~

A pattern describes the order and display style of each field, not a sample date-time. Latin letters are normally pattern symbols; hyphens, colons, spaces, and commas are normally printed literally. If you want to print a letter that is normally a pattern symbol, enclose it in single quotes, such as `'T'`.

`DateTimeFormatter` is immutable and thread-safe. When the pattern and `Locale` are fixed, you can create the formatter once and reuse it.

## 2. Date, Month, and Year Patterns

| Symbol | Meaning | Example or Notes |
| --- | --- | --- |
| `u` / `uuuu` | Proleptic ISO year | Commonly `uuuu-MM-dd` for machine data |
| `y` / `yyyy` | Year-of-era | Differs from `u` in some special calendar cases |
| `Y` / `YYYY` | Week-based-year | Not synonymous with calendar year |
| `M` / `MM` | Month as a number | `M` can be 1; `MM` is 01 |
| `MMM` | Short month name | `Oct` with an English `Locale` |
| `MMMM` | Full month name | `October` with an English `Locale` |
| `L` | Stand-alone month | Useful in some languages |
| `d` / `dd` | Day of month | `4` or `04` |
| `D` / `DDD` | Day of year | 1–365 or 1–366 |
| `E` / `EEE` | Short day-of-week name | For example `Sat` |
| `EEEE` | Full day-of-week name | For example `Saturday` |
| `e` / `c` | Localized day of week | Display/resolution depends on `Locale` |

Uppercase and lowercase symbols cannot be swapped arbitrarily:

- `MM` is **month**, while `mm` is **minute**.
- `dd` is day of month, while `DD` is day of year.
- `uuuu` is proleptic ISO year; `yyyy` is year-of-era.
- `YYYY` is week-based-year. Near the start or end of a year, the week-based-year can differ from the calendar year. Do not use `YYYY-MM-dd` for a regular calendar date if the actual goal is year-month-day.

Pattern examples:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
System.out.println(date.format(
        DateTimeFormatter.ofPattern("uuuu-MM-dd"))); // 2026-10-24
System.out.println(date.format(
        DateTimeFormatter.ofPattern("dd/MM/uuuu"))); // 24/10/2026
~~~

## 3. Hour, Minute, Second, and Fractional Seconds

| Symbol | Meaning | Notes |
| --- | --- | --- |
| `H` / `HH` | Hour-of-day (0–23) | `HH` is usually zero-padded |
| `h` / `hh` | Clock-hour-of-am-pm (1–12) | Should be paired with `a` to show AM/PM |
| `k` | Clock-hour-of-day (1–24) | Has its own convention for midnight |
| `K` | Hour-of-am-pm (0–11) | Alone does not distinguish AM/PM |
| `m` / `mm` | Minute | Lowercase |
| `s` / `ss` | Second | Lowercase |
| `S` | Fraction-of-second digits | `SSS` usually displays milliseconds |
| `n` | Nano-of-second as a number | Not the same as the fraction symbol `S` |
| `N` | Nano-of-day | Counter from the start of the day |

~~~java
LocalTime time = LocalTime.of(9, 5, 7, 123_000_000);
System.out.println(time.format(
        DateTimeFormatter.ofPattern("HH:mm:ss")));
System.out.println(time.format(
        DateTimeFormatter.ofPattern("HH:mm:ss.SSS")));
System.out.println(time.format(
        DateTimeFormatter.ofPattern("hh:mm:ss a", Locale.US)));
~~~

Output:

~~~text
09:05:07
09:05:07.123
09:05:07 AM
~~~

`S` is the fraction of a second, whereas `s` is whole seconds. With `HH`, hours run from 00 to 23; with `hh`, hours follow a 12-hour cycle, so you should also include `a` if you need to distinguish morning and afternoon/evening. For example, `hh:mm` alone may not distinguish 09:00 from 21:00.

The number of `S` letters determines how many fractional-second digits are output. `SSS` only displays three digits; if a value has nanoseconds with higher precision, this formatter cannot represent the full fraction. When you need to preserve exact machine-to-machine data, choose a format with appropriate resolution.

## 4. Literals and Special Characters

To print a character that a pattern normally interprets as a symbol, put it inside single quotes. ISO date-times commonly use the letter `T` as a separator:

~~~java
DateTimeFormatter isoLike =
        DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss");
System.out.println(LocalDateTime.of(2026, 10, 24, 9, 5, 7)
        .format(isoLike));
// 2026-10-24T09:05:07
~~~

You can include labels in the pattern:

~~~java
DateTimeFormatter vietnameseLabel =
        DateTimeFormatter.ofPattern("'Ngày' dd 'tháng' MM 'năm' uuuu");
System.out.println(LocalDate.of(2026, 10, 24)
        .format(vietnameseLabel));
// Ngày 24 tháng 10 năm 2026
~~~

Two consecutive single quotes `''` represent a literal single quote. If you open a single quote without closing it properly, `ofPattern` may throw `IllegalArgumentException`. Write literals clearly, especially when a pattern mixes descriptive text with date-time symbols.

## 5. Locale Determines Month and Weekday Names

The pattern `EEE, d MMM uuuu` does not fix month or weekday names to any specific language. `Locale` controls the names and certain formatting conventions.

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
DateTimeFormatter english =
        DateTimeFormatter.ofPattern("EEE, d MMM uuuu", Locale.US);
DateTimeFormatter vietnamese =
        DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu",
                Locale.forLanguageTag("vi-VN"));

System.out.println(date.format(english));
System.out.println(date.format(vietnamese));
~~~

Example output with the corresponding `Locale` data:

~~~text
Sat, 24 Oct 2026
Thứ Bảy, 24 tháng 10 năm 2026
~~~

Names can depend on CLDR data and the JDK version. If output must match identically across environments, pin the JDK/`Locale` and write tests. Do not rely on the machine's default `Locale` because a developer laptop and a server may differ.

You can specify the `Locale` directly in `ofPattern(pattern, locale)` or call `formatter.withLocale(locale)`. The pattern controls structure; `Locale` controls language and certain regional rules. These two decisions should be controlled separately.

## 6. Offset and Time Zone in Patterns

| Symbol | Common Role | Notes |
| --- | --- | --- |
| `X`, `XX`, `XXX` | ISO-style offset | `XXX` typically produces `+07:00`; zero offset may print `Z` |
| `x`, `xx`, `xxx` | ISO-style offset with different zero rules from `X` | Choose according to the format contract |
| `Z` | Offset according to formatter rules | Not always the literal letter Z |
| `O` / `OOOO` | Localized offset | For example GMT style, depending on `Locale` |
| `z` / `zzzz` | Short/long zone name | Can be ambiguous or language-dependent |
| `V` | Zone ID | `VV` is used to print the zone ID |

A pattern can only print an offset or zone if the input data has the corresponding field. `LocalDateTime` does not contain an offset or zone; if a pattern requires `XXX` or `VV`, the formatter cannot guess it. Use `OffsetDateTime` or `ZonedDateTime` when the data actually carries that information.

~~~java
ZonedDateTime meeting = LocalDateTime.of(2026, 10, 24, 9, 30)
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
DateTimeFormatter zonedFmt =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX '['VV']'");
System.out.println(meeting.format(zonedFmt));
~~~

Output:

~~~text
2026-10-24 09:30 +07:00 [Asia/Ho_Chi_Minh]
~~~

`X`, `x`, `Z`, and `O` do not share the same rules. The zone name `z` should also not be used as a unique machine-to-machine identifier: abbreviations can collide across regions. For future schedules, keep a regional `ZoneId` to apply date-specific offset rules; a fixed offset does not carry history or DST.

## 7. Use Built-in Formatters When Possible

If you do not need a custom pattern, Java provides standard formatters:

| Constant | Suitable Data |
| --- | --- |
| `ISO_LOCAL_DATE` | ISO date without time/zone |
| `ISO_LOCAL_TIME` | Local time |
| `ISO_LOCAL_DATE_TIME` | Local date-time, no offset |
| `ISO_OFFSET_DATE_TIME` | Date-time with offset |
| `ISO_ZONED_DATE_TIME` | Date-time with zone representation |
| `ISO_INSTANT` | Instant in ISO-8601 UTC |

Example:

~~~java
Instant instant = Instant.parse("2026-10-24T02:30:00Z");
System.out.println(DateTimeFormatter.ISO_INSTANT.format(instant));
// 2026-10-24T02:30:00Z
~~~

`ofPattern` is well suited for custom UI formatting. Built-in ISO formatters are usually better suited for data exchange with a clear contract. Do not use `dd/MM/uuuu HH:mm` as a protocol between services without agreeing on `Locale`, zone, and parsing rules.

## 8. Parsing Strings with the Same Pattern

You can use a formatter to parse a string into the corresponding type:

~~~java
DateTimeFormatter parser =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");
LocalDateTime parsed = LocalDateTime.parse(
        "24/10/2026 09:30", parser);
System.out.println(parsed);
// 2026-10-24T09:30
~~~

This string only contains a date and time, so the result is `LocalDateTime`; it does not inherently have a zone or offset. If the string contains an offset, use `OffsetDateTime` and a pattern that provides the offset. If an instant is needed, there must be a suitable offset or zone to pinpoint the point on the timeline.

Formatting and parsing should be treated as two related but distinct contracts. A formatter's output can lose information if the pattern omits seconds, nanoseconds, offset, or zone. Data stripped from the string cannot be recovered.

## 9. ResolverStyle: STRICT, SMART, and LENIENT

Parsing consists of reading fields and resolving those fields into a date-time value. `ResolverStyle` determines the strictness level:

- `STRICT`: rejects invalid field combinations.
- `SMART`: the common default mode of `ofPattern`; handles certain cases using smart calendar rules, for example adjusting a day beyond the end of the month in supported contexts.
- `LENIENT`: allows normalizing out-of-range values using lenient rules, such as month or day fields overflowing into adjacent periods.

For date input forms that require strict validation, you can build a formatter with `DateTimeFormatterBuilder`:

~~~java
DateTimeFormatter strict = new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd")
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
~~~

This snippet requires importing `DateTimeFormatterBuilder` and `ResolverStyle` along with the types already used. Using `uuuu` interprets the ISO year directly; when using `yyyy` in `STRICT` mode, the year-of-era field may additionally require an era to resolve completely.

If input contains an invalid date such as `2025-02-30`, you must explicitly decide whether to reject it or apply an adjustment policy. For financial, contract, or record data, silently fixing input can hide business errors. Write tests for the chosen resolver mode and catch `DateTimeParseException` at the input boundary.

## 10. Common Pattern Mistakes

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Using `MM` instead of `mm` | Prints month instead of minutes | Check uppercase/lowercase letters |
| Using `DD` instead of `dd` | Prints day of year | Check field meanings |
| Using `YYYY` as calendar year | Year can be off near week/year boundaries | Use `uuuu` when a regular ISO calendar year is needed |
| Using `hh` without `a` | Loses AM/PM information | Use `HH` or add AM/PM |
| Using `SSS` when full nanoseconds are needed | Loses sub-millisecond fraction | Choose appropriate precision |
| Formatting `LocalDateTime` with an offset pattern | No offset data available to print | Choose a type with offset or zone |
| Relying on system `Locale` | Output differs across machines | Specify `Locale` explicitly |
| Using UI format as an API | Unstable or ambiguous parsing | Choose an ISO format/contract with clear rules |
| Confusing formatting and parsing | Stripped data cannot be recovered | Verify which fields are preserved |
| Leaving literals unescaped | Letters interpreted as symbols or formatter creation fails | Use single quotes for literals |

## 11. Standalone Runnable Java 17+ Example

The program below demonstrates numeric patterns, milliseconds, English/Vietnamese `Locale`, parsing back, and offset/zone formatting. All input values are fixed.

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class OfPatternDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 24);
        LocalTime time = LocalTime.of(9, 5, 7, 123_000_000);
        LocalDateTime local = LocalDateTime.of(date, time);

        DateTimeFormatter numeric =
                DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm:ss");
        DateTimeFormatter fraction =
                DateTimeFormatter.ofPattern("HH:mm:ss.SSS");
        DateTimeFormatter english =
                DateTimeFormatter.ofPattern("EEE, d MMM uuuu", Locale.US);
        DateTimeFormatter vietnamese =
                DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu",
                        Locale.forLanguageTag("vi-VN"));

        System.out.println("numeric=" + local.format(numeric));
        System.out.println("fraction=" + time.format(fraction));
        System.out.println("english=" + date.format(english));
        System.out.println("vietnamese=" + date.format(vietnamese));

        DateTimeFormatter parser =
                DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");
        LocalDateTime parsed =
                LocalDateTime.parse("24/10/2026 09:30", parser);
        System.out.println("parsed=" + parsed);

        ZonedDateTime meeting = local.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));
        DateTimeFormatter zonedPattern =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX '['VV']'");
        System.out.println("zoned=" + meeting.format(zonedPattern));
    }
}
~~~

Save as `OfPatternDemo.java`, then compile and run with JDK 17+:

~~~bash
javac OfPatternDemo.java
java OfPatternDemo
~~~

Typical output with the corresponding `Locale` data:

~~~text
numeric=24/10/2026 09:05:07
fraction=09:05:07.123
english=Sat, 24 Oct 2026
vietnamese=Thứ Bảy, 24 tháng 10 năm 2026
parsed=2026-10-24T09:30
zoned=2026-10-24 09:05 +07:00 [Asia/Ho_Chi_Minh]
~~~

Explanation:

1. The numeric pattern controls zero-padding and the order of date/time fields.
2. `SSS` prints three fractional digits; `123_000_000` nanoseconds correspond to `123` milliseconds.
3. The two day-name formatters use explicit `Locale`s, so they do not depend on the machine's default `Locale`.
4. `parsed` is a `LocalDateTime` because the input string contains no offset.
5. `zoned` includes both the offset and the zone because the value is attached to `Asia/Ho_Chi_Minh`.

Month and weekday names can depend on the JDK version's `Locale` data; if you need completely identical stdout, pin the test environment or use stable numeric formats for critical data.

## 12. Reusing Formatters and Checklist

When the pattern and `Locale` are fixed, store the formatter as a shared constant:

~~~java
private static final DateTimeFormatter LOG_FORMAT =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss");
~~~

This avoids recreating the formatter repeatedly. If the pattern is user-configured, validate it when loading configuration; an invalid pattern can throw an exception as soon as the formatter is created.

Before shipping a pattern to production, check:

1. **Source type:** Does the value have the exact date/time/offset/zone fields the pattern requires?
2. **Symbols:** Month `MM` or minute `mm`; day of month `dd` or day of year `DD`; calendar year `uuuu` or week-based-year `YYYY`?
3. **Hour:** 24-hour `HH` or 12-hour `hh` + `a`?
4. **Precision:** Does the pattern drop nanoseconds/milliseconds that must be preserved?
5. **Locale:** Do month/weekday names require a fixed language?
6. **Offset/zone:** Do you need a numeric offset, a zone ID, or just local time?
7. **Parsing:** Is the resolver style appropriate? Should invalid data be rejected or adjusted?
8. **Contract:** Is this a UI string or an inter-service exchange format?
9. **Boundaries:** Test month-end, leap years, year start/end, zero offset, and DST transitions when a zone is present.

## 13. Self-Check Exercises

1. Create a pattern for `24/10/2026 09:05:07` from a `LocalDateTime`.
2. Use `HH:mm` and `hh:mm a` to display 09:00 and 21:00. Why do the results differ?
3. Why can `YYYY-MM-dd` produce a different year from `uuuu-MM-dd` near year boundaries?
4. Create Vietnamese and English formatters for the same date; explain the role of `Locale`.
5. Why can't `LocalDateTime` format a real offset/zone just by adding `XXX` or `VV` to the pattern?
6. Parse `2025-02-30` with `SMART` and `STRICT` formatters; decide the right policy for your form.
7. Create a pattern with a literal `T` and the label `'Ngày'`. Why do you need to escape letters that are normally pattern symbols?
8. Design a format for an API timestamp that needs to preserve instant, offset, and zone; choose between a built-in ISO formatter or a custom pattern and explain.

**Key takeaway:** `DateTimeFormatter.ofPattern()` turns a pattern string into formatting/parsing rules. Understand uppercase and lowercase symbols accurately, specify `Locale` explicitly, do not use week-based-year in place of calendar year, and only request an offset/zone when the source type actually carries that information. For machine-to-machine data exchange, prefer a well-defined ISO contract; for UI, choose a pattern based on language and display purpose.
