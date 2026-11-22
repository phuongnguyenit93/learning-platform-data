# SimpleDateFormat and DateFormatSymbols in Java: Locale-Based Date-Time Formatting with the Legacy API

## Objectives

Before Java 8 introduced `java.time` into the standard library, Java applications commonly used `java.util.Date`, `java.util.Calendar`, `java.text.DateFormat`, and `java.text.SimpleDateFormat` to format or parse dates and times. `java.text.DateFormatSymbols` supplies the localized display names — months, weekdays, AM/PM periods, eras, and time zone names — that `SimpleDateFormat` can use.

This lesson helps you:

- Distinguish **`SimpleDateFormat`, which decides how to assemble/parse dates and times by pattern**, from **`DateFormatSymbols`, which provides the localized names and symbols**.
- Create a formatter with an explicit `Locale`, set an appropriate `TimeZone`, and understand that `Date` represents an instant in time, not attached to any UI language or time zone.
- Read easily confused pattern letters such as `M`/`L`, `y`/`Y`, `H`/`h`, `a`, `E`, `z`, `Z`, `X`.
- Customize month names with `DateFormatSymbols` without altering calendar data or logic.
- Distinguish **valid date checking** from **consuming the entire string**, understanding `setLenient(false)`, `ParsePosition`, and two-digit year risks.
- Avoid sharing mutable `SimpleDateFormat` instances across threads; determine when to migrate to `java.time.format.DateTimeFormatter` on Java 17+.

This lesson covers the **legacy date-time API**. New projects generally prefer `java.time`, but understanding these two classes remains important when maintaining legacy applications, interacting with older libraries, or inspecting how date-time strings are handled across system layers.

## 1. Where the two classes sit in the legacy API model

`SimpleDateFormat` extends `DateFormat`; `DateFormatSymbols` is the class that holds the symbol/string information needed for date-time localization.

```text
Date / Calendar         Locale + TimeZone
       |                       |
       v                       v
    SimpleDateFormat <---- DateFormatSymbols
       |                         |
       |                         +-- month names / weekday names
       |                         +-- AM/PM / eras
       |                         +-- time zone names / local pattern chars
       |
       +-- format(Date) -> display String
       +-- parse(String) -> Date
```

Separating responsibilities:

| Component | Role |
| --- | --- |
| `Date` | Represents an instant on the timeline; does not store a `Locale` or display time zone name. |
| `Calendar` | Converts and computes calendar fields according to time zone, calendar rules, and related locale. |
| `Locale` | Language/region conventions to apply when formatting or parsing date/month names. |
| `TimeZone` | Offset/time zone rules to convert an instant into local date and time. |
| `SimpleDateFormat` | Pattern, date-time formatting and parsing; holds mutable state. |
| `DateFormatSymbols` | Set of localized names/strings and symbols serving the legacy formatter. |

**Do not equate language with time zone.** A Vietnamese reader might be in Paris; an English reader might want data presented in UTC. `Locale` determines cultural presentation style, while `TimeZone` determines converting an instant into local time.

For example, `2026-10-28T15:04:05Z` is a UTC instant. When formatted in UTC, the time fields are 15:04:05; when formatted in another time zone, those fields can change even though the input `Date` does not change.

## 2. SimpleDateFormat: pattern + Locale + TimeZone

One way to create a formatter:

```java
import java.text.SimpleDateFormat;
import java.util.Locale;
import java.util.TimeZone;

SimpleDateFormat format = new SimpleDateFormat(
        "dd MMMM yyyy HH:mm:ss", Locale.forLanguageTag("vi-VN"));
format.setTimeZone(TimeZone.getTimeZone("UTC"));
```

This is an illustrative snippet inside a method, not a standalone runnable program. Each operation has a distinct meaning:

- `"dd MMMM yyyy HH:mm:ss"` is the **format pattern**: two-digit day, full month name, year, 24-hour time, minutes, and seconds.
- `Locale.forLanguageTag("vi-VN")` requests Vietnamese month names and related conventions.
- `setTimeZone(...)` chooses the time zone used to interpret a `Date` when formatting or parsing.

`SimpleDateFormat` has multiple constructors, including `SimpleDateFormat(String pattern)` using the appropriate default locale, `SimpleDateFormat(String pattern, Locale locale)`, and `SimpleDateFormat(String pattern, DateFormatSymbols symbols)`. When you want consistent behavior across development/CI/production machines, **pass `Locale` explicitly** instead of relying entirely on the JVM default.

One point to remember: a formatter is built from those configurations at construction time. Changing `Locale.setDefault(...)` in the JVM later **does not mean an existing `SimpleDateFormat` object automatically updates** all of its patterns, symbols, and settings.

### Formatting a Date

```java
import java.time.Instant;
import java.util.Date;

Date moment = Date.from(
        Instant.parse("2026-10-28T15:04:05Z"));

String text = format.format(moment);
```

This is an illustrative snippet inside a method, using the `format` variable created earlier. `Date.from(Instant)` lets you pick a **fixed input instant** so the example does not depend on the system clock. `SimpleDateFormat` accepts a `Date` and returns a formatted `String`.

Even though `Date`'s name easily makes learners think of "a calendar date", `java.util.Date` carries instant information (millisecond precision), not a time-zone-independent `LocalDate`. Formatting it into day/month/year depends on the time zone the formatter is using.

## 3. Reading SimpleDateFormat patterns

Patterns consist of **letters with special meaning** and literal fixed text. The number of repeated letters can determine numeric form versus name form.

| Pattern letter | Typical meaning | Illustration |
| --- | --- | --- |
| `y` | Calendar year | `yyyy` → `2026` |
| `M` | Month, numeric or context-sensitive name | `MM` → `10`, `MMMM` → `October` |
| `L` | Stand-alone month, when locale data distinguishes it | `LLLL` → month name in stand-alone context |
| `d` | Day of month | `dd` → `28` |
| `E` | Day name in week | `EEEE` → `Wednesday` |
| `u` | Day number of week, Monday is 1 | `u` for Wednesday → `3` |
| `H` | Hour in day, 0–23 | `HH` → `15` |
| `h` | Hour in 1–12 cycle | `hh` → `03`, needs AM/PM context |
| `a` | AM/PM marker | `a` → `PM` in en-US |
| `m` | Minute | `mm` → `04` |
| `s` | Second | `ss` → `05` |
| `S` | Millisecond | `SSS` → `123` |
| `z` | Time zone name/general representation | `z` → name or offset form |
| `Z` | RFC 822 time zone offset | `Z` → `+0700` |
| `X` | ISO 8601 offset, depending on number of X letters | `XXX` → `+07:00`, UTC can be `Z` |
| `Y` | Week-based year | Can differ from `y` around New Year |

For example, in `Locale.US` and UTC, `"EEEE, dd MMMM yyyy HH:mm:ss XXX"` can produce:

```text
Wednesday, 28 October 2026 15:04:05 Z
```

### Easily confused pairs

**`M` vs. `m`:** uppercase `M` is month; lowercase `m` is minute. `"MM:mm"` is not "month:month", but "month:minute".

**`H` vs. `h`:** `H` is for 24-hour time; `h` is for 12-hour time. Using `hh` without `a` can make the string ambiguous between morning and afternoon.

**`y` vs. `Y`:** `Y` is the **week-based year**, tied to the first/last week of the year and the week rules of `Calendar`/locale. Near New Year's Eve, `YYYY` can produce a different number from the calendar year `yyyy`. For ordinary dates, you normally want `yyyy-MM-dd`, not `YYYY-MM-dd`.

**`M` vs. `L`:** in some languages, a month name in a phrase containing a day differs from a month name standing alone. `M` describes the formatting-context form; `L` describes the stand-alone form. Not every locale/provider exhibits a difference, and you should not assume that any custom `DateFormatSymbols` will replace all `L` forms properly.

**`u` in SimpleDateFormat differs from `u` in java.time:** in `SimpleDateFormat`, `u` is the day number of the week starting from Monday. In modern `DateTimeFormatter`, `u` represents the proleptic year. **Do not copy patterns between the two APIs without reviewing the meaning of each symbol.**

### Quotes and literal text

To insert fixed text containing letters that are pattern characters, enclose it in single quotes:

```java
new SimpleDateFormat("yyyy-MM-dd 'at' HH:mm", Locale.US);
```

If you want a literal single quote in the pattern, use `''`. A pattern with mismatched quotes or invalid pattern letters can lead to `IllegalArgumentException` or unexpected results.

Do not treat a pattern as arbitrary plain text: ASCII letters belonging to the pattern table have special semantics. In particular, legacy API date format patterns are not automatically fully compatible with ICU, JavaScript, or `java.time` syntax.

## 4. What is DateFormatSymbols?

`DateFormatSymbols` stores the localized string arrays/sets that a formatter can use to express **text-based calendar fields**.

Some important APIs:

| API | Information |
| --- | --- |
| `DateFormatSymbols.getInstance(locale)` | Gets the symbol set for the requested locale |
| `getMonths()` / `setMonths(...)` | Full month names |
| `getShortMonths()` / `setShortMonths(...)` | Abbreviated month names |
| `getWeekdays()` / `setWeekdays(...)` | Full weekday names |
| `getShortWeekdays()` / `setShortWeekdays(...)` | Abbreviated weekday names |
| `getAmPmStrings()` / `setAmPmStrings(...)` | Strings for AM/PM |
| `getEras()` / `setEras(...)` | Era names used in the related calendar |
| `getZoneStrings()` / `setZoneStrings(...)` | Table of time zone name strings for display |
| `getLocalPatternChars()` / `setLocalPatternChars(...)` | Localized pattern character set for `applyLocalizedPattern` |
| `clone()` | Creates a copy when state isolation is needed |

Example:

```java
import java.text.DateFormatSymbols;
import java.util.Calendar;
import java.util.Locale;

DateFormatSymbols us = DateFormatSymbols.getInstance(Locale.US);
String october = us.getMonths()[Calendar.OCTOBER];
String wednesday = us.getWeekdays()[Calendar.WEDNESDAY];
```

This is an illustrative snippet inside a method. In a typical en-US locale, `october` is `October` and `wednesday` is `Wednesday`.

### Array indices are not the same

This is a very easy mistake to make:

- The constants `Calendar.JANUARY` through `Calendar.DECEMBER` have values from **0 to 11**. Thus `months[Calendar.OCTOBER]` points to October.
- `Calendar.SUNDAY` through `Calendar.SATURDAY` use values from **1 to 7**. The `getWeekdays()` array typically leaves index 0 unused, and the actual positions correspond to the `Calendar` constants.

Do not write `weekdays[0]` thinking it is Sunday. Do not take `months[10]` thinking index 10 is October; according to the `Calendar` constants, October is index 9.

The legacy API month array may contain a 13th element for calendars supporting an extra month. Do not assume every locale has exactly 12 names or that any value beyond 12 should be arbitrarily mapped to other data. When you need a standard Gregorian month, use the appropriate `Calendar` constant.

### Do not use DateFormatSymbols as a time zone database

`getZoneStrings()` is primarily a table of **display names**, not a source for computing offsets, daylight saving time rules, or a canonical list of time zones for routing data. Those rules belong to `TimeZone` in the legacy API or `ZoneId`/`ZoneRules` in `java.time`.

Similarly, `DateFormatSymbols` does not replace your application's `ResourceBundle` for managing translated messages. It is the set of calendar symbols used by the formatter; screen titles, error messages, and button labels still need their own resource bundles.

## 5. How SimpleDateFormat uses DateFormatSymbols

When you create:

```java
SimpleDateFormat formatter = new SimpleDateFormat(
        "EEEE, dd MMMM yyyy", Locale.US);
```

`SimpleDateFormat` gets a symbol set appropriate for the locale to turn `EEEE` into a weekday name and `MMMM` into a month name. There is no need to look up names in arrays manually and concatenate strings.

`DateFormatSymbols` lets you **override the set of names and symbols** when there is a specific requirement, for instance a specialized report that wants to call October "Harvest" instead of "October". This is an intentional customization need, not the normal way to translate month names for the whole application.

### Customizing month names

```java
import java.text.DateFormatSymbols;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;

DateFormatSymbols symbols = DateFormatSymbols.getInstance(Locale.US);
String[] months = symbols.getMonths();

months[Calendar.OCTOBER] = "Harvest";
symbols.setMonths(months);

SimpleDateFormat custom = new SimpleDateFormat(
        "dd MMMM yyyy", symbols);
```

This is an illustrative snippet inside a method; to format an instant accurately, you need to set `TimeZone` and pass an appropriate `Date`.

Key points:

1. Obtain the month array from the symbol set you intend to use.
2. Modify the index via `Calendar.OCTOBER`, without guessing by the display month number.
3. Call `setMonths(...)` to supply the modified array back to `DateFormatSymbols`.
4. Pass the symbols to the `SimpleDateFormat(String, DateFormatSymbols)` constructor, or call `formatter.setDateFormatSymbols(symbols)` on an existing formatter.
5. Thereafter, the formatter is configured with the custom month name when handling month formats matched by the symbol set.

This customization can affect **both formatting and parsing of month names**. Therefore, if you only want to change text in a single report, isolate that formatter; do not alter a configuration shared with an input parser without evaluating the consequences.

`DateFormatSymbols` getters and setters handle arrays according to the class contract. Even with defensive copying mechanisms, the cleanest approach is to create a separate symbol set for each specialized configuration, modify the array, and call the setter, avoiding using a mutable symbols variable as a global resource that can be altered arbitrarily.

### Difference between changing the pattern and changing symbols

- **Changing the pattern:** determines **which fields, in what order, and whether month names are shown**. For example, `"dd/MM/yyyy"` → `"EEEE, dd MMMM yyyy"`.
- **Changing symbols:** determines **which month/weekday/AM-PM name strings** are used for the corresponding text fields.
- **Changing locale:** selects the set of localization conventions, typically including names and certain calendar/display rules.
- **Changing time zone:** determines the local date/time and corresponding offset when formatting/parsing.

Do not call `DateFormatSymbols.setMonths` and expect the pattern `"dd/MM/yyyy"` to suddenly display month names: the `MM` pattern still asks for a numeric month. For full names, use `MMMM` in the pattern.

## 6. Complete Java 17+ example: formatter, symbols, and parsing

The following example is designed to run standalone on JDK 17 or later, independent of the current clock or default time zone.

Create the file `LegacyDateFormattingDemo.java`:

```java
import java.text.DateFormatSymbols;
import java.text.ParseException;
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyDateFormattingDemo {
    public static void main(String[] args) {
        Date moment = Date.from(
                Instant.parse("2026-10-28T15:04:05Z"));
        TimeZone utc = TimeZone.getTimeZone("UTC");

        SimpleDateFormat standard = new SimpleDateFormat(
                "EEEE, dd MMMM yyyy HH:mm:ss XXX", Locale.US);
        standard.setTimeZone(utc);

        System.out.println(standard.format(moment));

        DateFormatSymbols symbols =
                DateFormatSymbols.getInstance(Locale.US);
        System.out.println(
                symbols.getMonths()[Calendar.OCTOBER]);
        System.out.println(
                symbols.getWeekdays()[Calendar.WEDNESDAY]);

        String[] months = symbols.getMonths();
        months[Calendar.OCTOBER] = "Harvest";
        symbols.setMonths(months);

        SimpleDateFormat custom = new SimpleDateFormat(
                "dd MMMM yyyy", symbols);
        custom.setTimeZone(utc);

        System.out.println(custom.format(moment));
        System.out.println(standard.format(moment));

        SimpleDateFormat parser = new SimpleDateFormat(
                "yyyy-MM-dd", Locale.US);
        parser.setLenient(false);
        parser.setTimeZone(utc);

        try {
            parser.parse("2026-02-30");
            System.out.println("Invalid date accepted");
        } catch (ParseException ex) {
            System.out.println("Invalid date rejected");
        }

        String input = "2026-10-28tail";
        ParsePosition position = new ParsePosition(0);
        Date parsed = parser.parse(input, position);

        System.out.println("Parsed prefix: "
                + (parsed != null)
                + ", index=" + position.getIndex()
                + "/" + input.length());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 LegacyDateFormattingDemo.java
java LegacyDateFormattingDemo
```

Stdout:

```text
Wednesday, 28 October 2026 15:04:05 Z
October
Wednesday
28 Harvest 2026
Wednesday, 28 October 2026 15:04:05 Z
Invalid date rejected
Parsed prefix: true, index=10/14
```

### Explaining each result

1. The pattern `EEEE, dd MMMM yyyy HH:mm:ss XXX` displays English weekday/month names, 24-hour time, and the UTC offset denoted `Z` for `XXX`.
2. `symbols.getMonths()[Calendar.OCTOBER]` returns `October`.
3. `symbols.getWeekdays()[Calendar.WEDNESDAY]` returns `Wednesday`.
4. After modifying its separate symbol set, the `custom` formatter uses the name `Harvest` for October and produces `28 Harvest 2026`.
5. The `standard` formatter created separately earlier still displays `October`. Modifying `symbols` for the new formatter does not change this formatter's state.
6. `setLenient(false)` causes the parser to reject the date `2026-02-30`, which does not exist in the Gregorian calendar used in the example.
7. However, `parse(input, position)` still reads the prefix `2026-10-28` and stops before `tail`. Index 10 out of a 14-character string means **the input was not fully consumed**, even though the date in the prefix is valid.

These are two separate groups of concerns: **display language** is governed by symbols and patterns; **input validation** requires checking both leniency and the number of characters consumed.

## 7. Parsing: what traps exist when going from String to Date?

`SimpleDateFormat.parse(String)` returns a `Date`; `parse(String, ParsePosition)` lets you track how far the parser read. You need to understand at least three issues:

### 7.1. Default leniency can turn a "wrong" date into another date

`DateFormat`/`Calendar` normally allow flexible interpretation during parsing if lenient mode has not been turned off. For example, a nonexistent date like "February 30" can be normalized into a March date if the parser is lenient.

```java
SimpleDateFormat parser = new SimpleDateFormat(
        "yyyy-MM-dd", Locale.US);
parser.setLenient(false);
```

An illustrative snippet inside a method. `setLenient(false)` enforces stricter date checking according to the calendar used by the formatter. A string `"2026-02-30"` will be rejected in a standard Gregorian calendar instead of silently rolling over into a new date.

However, **`setLenient(false)` does not mean parsing will consume the entire string**. For example, `"2026-10-28tail"` can still be parsed into a `Date` from its valid leading portion.

### 7.2. The parser may only read a prefix

Here is full-input checking logic:

```java
String input = "2026-10-28tail";

ParsePosition pos = new ParsePosition(0);
Date parsed = parser.parse(input, pos);

boolean complete = parsed != null
        && pos.getIndex() == input.length();
```

This snippet assumes the `parser` variable created above, with `ParsePosition` and `Date` imported. `complete` is `false` because the parser stops before `tail`.

When `parse(String)` fails to recognize input right at the start, it can throw `ParseException`; when the parser produces a result for the leading part and a suffix remains, that overload may still **not throw an error**. Therefore, you cannot rely solely on "no exception".

`ParsePosition.getErrorIndex()` helps diagnose when parsing fails. It does not replace checking `getIndex()` if trailing characters are disallowed.

### 7.3. Two-digit years depend on an interpretation window

With the `"yy"` pattern, `SimpleDateFormat` uses a **100-year window** to interpret two-digit years. The default for this window depends on when the formatter is created (typically starting about 80 years prior and ending about 20 years ahead), so the same string `"30"` may be interpreted differently when the program runs at a different point in time.

If you are forced to handle legacy two-digit years, you can control it with `set2DigitYearStart(Date startDate)` while clearly documenting the input contract. For new inputs, however, **prefer four-digit years** and require users to enter the full year instead of relying on an implicit year window.

### 7.4. Month and weekday names are language data

A parser using `"dd MMMM yyyy"` needs to recognize month names matching the formatter's locale and symbols. An English month-name string will not automatically parse properly with a formatter created using a Vietnamese locale, and vice versa.

If users/systems enter numeric dates like `yyyy-MM-dd` under a fixed machine-readable contract, there is no need to build a parser relying on translated month names. For inputs coming from external systems, use an ISO parsing API or an explicit schema rather than casually relying on the JVM default locale.

## 8. DateFormatSymbols: customizable, but not a substitute for business formatting

Some legacy applications customized `DateFormatSymbols` to change weekday names, month names, or AM/PM strings. This technique is still useful in narrow scenarios, but you should distinguish:

- **Standard language names:** usually `new SimpleDateFormat(pattern, locale)` is all you need. The JDK/providers already supply month/weekday name data for many locales.
- **Domain-specific names or custom requirements:** you can customize symbols on the formatter for that specific screen/report.
- **Calendar policies or date calculation rules:** cannot be solved merely by changing text in symbols.
- **Time zones and DST transitions:** cannot be controlled accurately by changing names in `getZoneStrings`.
- **Translating application messages:** use `ResourceBundle`/an i18n system instead of stuffing arbitrary strings into `DateFormatSymbols`.

Customizing month names can have side effects when inputs are parsed: a renamed month may require the parser to recognize the new name, while the standard name may no longer be accepted as before. Test both directions if the formatter is used for input.

### Time zone names can change across providers

The `z` pattern can display a time zone name or an offset form depending on the zone/locale/JDK data. Names can change across language data or time zone data updates. If you need stable machine-readable output, do not use `z` names as a protocol.

The `X` or `XXX` pattern produces offsets in ISO 8601 syntax, but a bare offset **does not contain the full ZoneId or historical DST rules**. For example, `+07:00` does not replace a region identifier like `Asia/Ho_Chi_Minh` when the system needs historical/regional rules.

When exchanging points in time between services, prefer ISO-8601 formats with an appropriate offset/UTC per schema, or use temporal types supported by your serialization library, rather than a UI `SimpleDateFormat` with translated month names.

## 9. Thread-safety risks: SimpleDateFormat is mutable

**`SimpleDateFormat` is not guaranteed to be safe when multiple threads format/parse on the same instance without synchronization.** The formatter stores state such as calendar, number format, and time zone, which can be mutated during processing. Sharing a formatter in a `static` field and using it concurrently across all requests can cause corrupted data, unexpected exceptions, or hard-to-reproduce bugs.

Anti-pattern:

```java
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("yyyy-MM-dd", Locale.US);
```

This is only an illustrative field declaration inside a class. `final` only prevents reassigning the reference; **it does not make `SimpleDateFormat` itself immutable or thread-safe**.

Mitigations:

1. **Create a separate instance per task:** simple and clear when traffic is not excessive.
2. **Use appropriate synchronization** if a shared formatter is unavoidable, while also guarding any calls that change configuration.
3. **Use `ThreadLocal` with discipline** in legacy systems if needed, evaluating thread-pool lifecycles and the risk of leaks/retained state.
4. **Prefer `DateTimeFormatter`** from `java.time` whenever migration is possible; this formatter is immutable and designed to be safe for concurrent use.

Do not attach a shared mutable `DateFormatSymbols` to multiple formatters and mutate it while requests are running. Build formatters locally/independently and treat published configuration data as fixed.

### Beware of changing configuration after use

`SimpleDateFormat` has setters such as `applyPattern(...)`, `setTimeZone(...)`, `setLenient(...)`, and `setDateFormatSymbols(...)`. A formatter could be mutated elsewhere without the caller realizing it. If an object needs to format in multiple locales/time zones, the safe approach is to create a formatter per request rather than mutating a global instance per user.

## 10. Key differences to remember when migrating to java.time

Since Java 8, the types in `java.time` separate roles clearly:

| Legacy API | Common modern replacement |
| --- | --- |
| `Date` representing an instant | `Instant` for a UTC point in time |
| `Calendar` + time zone | `ZonedDateTime` or `OffsetDateTime` depending on meaning |
| Date without time | `LocalDate` |
| `TimeZone` | `ZoneId`, `ZoneOffset` |
| `SimpleDateFormat` | `DateTimeFormatter` |
| Custom month/weekday names via symbols | Locale-based formatter or `DateTimeFormatterBuilder` with a text map if special needs exist |

Modern example:

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("EEEE, dd MMMM uuuu HH:mm:ss XXX", Locale.US)
        .withZone(ZoneOffset.UTC);

String text = formatter.format(
        Instant.parse("2026-10-28T15:04:05Z"));
```

This is an illustrative snippet inside a method. The result in en-US and UTC is:

```text
Wednesday, 28 October 2026 15:04:05 Z
```

Key points:

- With `DateTimeFormatter`, the proleptic year symbol is `u`/`uuuu`. Do not copy a `SimpleDateFormat` pattern verbatim out of habit if it uses symbols with different semantics.
- `DateTimeFormatter` is **immutable** and thread-safe; an appropriately configured instance can be stored and reused.
- `java.time` cleanly separates instants, dates, local date-times, and time zones. Choosing the right type helps avoid bugs like inferring a time zone from a locale.
- Strict parsing options and resolver styles of `DateTimeFormatter` have a different contract from `SimpleDateFormat#setLenient(false)`; migration requires testing real inputs and outputs, not just renaming classes.

If legacy code passes/returns `Date`, you can convert with `Date#toInstant()` and `Date.from(Instant)` at the integration boundary. You do not have to replace the entire codebase at once; you can migrate UI formatters and input parsers incrementally first.

## 11. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Using `new SimpleDateFormat(pattern)` everywhere | Output depends on the JVM default locale | Pass locale explicitly |
| Not setting `TimeZone` for data needing consistent conversion | The same Date can display different times across machines | Choose zone per business logic/user |
| Thinking `Date` carries a locale and zone | Confuses an instant with its presentation | Separate `Date/Instant`, `Locale`, and `TimeZone` |
| Using `MM` for month name | `MM` outputs numeric month, not name | Use `MMMM` or `MMM` |
| Using `mm` for month | `mm` is minutes | Use `MM` or `MMMM` |
| Using `YYYY` for ordinary calendar dates | Week-based year can diverge around New Year | Usually use `yyyy` in SimpleDateFormat |
| Using `hh` without `a` | Ambiguous AM/PM hour | Use `HH` or `hh a` |
| Thinking `DateFormatSymbols` determines the time zone | Display names differ from offset/DST rules | Use `TimeZone`/`ZoneId` in its proper role |
| Using index 0 for Sunday | Weekday array follows `Calendar.SUNDAY=1` | Use `Calendar` constants |
| Changing month names via symbols while pattern is still `MM` | Custom name does not appear | Use `MMMM` |
| Omitting `setLenient(false)` for strict date input parsing | Invalid dates may be normalized | Disable leniency and check remainder |
| Using only `parse(String)` as validation | May parse a prefix and ignore a suffix | Use `ParsePosition` to check full input |
| Using `yy` without controlling the year window | Result depends on when formatter was created | Use full year, or `set2DigitYearStart` |
| Sharing one `SimpleDateFormat` across multiple threads | Race conditions because formatter is mutable | Separate instances or switch to `DateTimeFormatter` |
| Copying patterns verbatim from SimpleDateFormat to DateTimeFormatter | Some pattern letters, like `u`, differ in meaning | Check each API's pattern table |
| Using `z` timezone names for API exchange | Text varies by locale/provider and lacks full ZoneId | Use ISO-8601 schemas / unambiguous zone IDs |

## 12. Self-check exercises

**Exercise 1 — Patterns.** For `"dd/MM/yyyy HH:mm"`, explain each pattern letter. If you want the full English month name and weekday name, write an appropriate pattern. Why does `MM` not display `October`?

**Exercise 2 — Symbol arrays.** Call `DateFormatSymbols.getInstance(Locale.US)`. State the indices to retrieve October and Wednesday using `Calendar` constants. Why can you not use index 0 as Sunday?

**Exercise 3 — Customization.** Rename October to `Harvest` via `getMonths`/`setMonths` and create `SimpleDateFormat("dd MMMM yyyy", symbols)`. If the pattern changes to `"dd/MM/yyyy"`, will `Harvest` still appear? Why?

**Exercise 4 — Locale vs. TimeZone.** A `Date` represents the instant `2026-10-28T15:04:05Z`. If you keep `Locale.US` and change `TimeZone` from UTC to another region, which parts of the output can change? If you keep UTC and change the locale, which parts change?

**Exercise 5 — Parsing.** `SimpleDateFormat("yyyy-MM-dd")` has `setLenient(false)`. How should it handle `2026-02-30`? If the input is `2026-10-28tail`, why is turning off leniency alone not enough to validate the entire string? Use `ParsePosition`.

**Exercise 6 — Year.** Explain why `YYYY-MM-dd` can be dangerous at year-end. Distinguish `y` and `Y` in `SimpleDateFormat`, then compare the meaning of `u` in `SimpleDateFormat` and `DateTimeFormatter`.

**Exercise 7 — Concurrency.** A backend declares a `static final SimpleDateFormat` used for all requests. Why does `final` not guarantee thread safety? Propose two solutions for legacy code and one approach using `DateTimeFormatter`.

**Exercise 8 — Migration.** Convert formatting a `Date` in UTC/Locale.US to `DateTimeFormatter`. Choose `Instant`, `ZoneOffset.UTC`, and a pattern with `uuuu`. In what cases is `Date.from(Instant)` still needed to interoperate with legacy libraries?

## 13. Key takeaways

**`SimpleDateFormat` is a mutable formatter/parser driven by pattern, `Locale`, and `TimeZone`; `DateFormatSymbols` is the customizable source of month/weekday/AM-PM names and localized calendar strings.** Both classes work together to turn temporal data into human-readable text, but they are not the source of truth for time zone rules or application message data.

When maintaining legacy applications:

1. Choose `Locale` and `TimeZone` explicitly.
2. Check pattern symbols carefully, especially `M`/`m`, `y`/`Y`, `H`/`h`, and quoting.
3. When parsing, combine `setLenient(false)` with `ParsePosition` if strings with trailing characters must be rejected.
4. Do not share mutable `SimpleDateFormat` instances across threads without synchronization.
5. For new designs, prefer `java.time` and `DateTimeFormatter`, and verify pattern differences when migrating code.

### API reference documentation

- [`SimpleDateFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html)
- [`DateFormatSymbols` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DateFormatSymbols.html)
- [`DateFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DateFormat.html)
- [`DateTimeFormatter` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
