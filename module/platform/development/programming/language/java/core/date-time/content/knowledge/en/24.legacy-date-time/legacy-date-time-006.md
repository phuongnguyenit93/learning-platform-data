# `SimpleDateFormat`: format patterns, `Locale`, and time zones

## 1. Three settings working together to parse and format date-time

`SimpleDateFormat` is a formatter in the legacy `java.text` API that uses `Date` as the date-time value when converting between objects and strings. It still appears in libraries or legacy code, so it is important to understand how to configure it properly rather than copying a pattern that merely looks right.

Three questions must be kept separate:

- **Format pattern:** in what order and with which separators do the fields appear?
- **Locale:** which language/regional conventions are used for text elements such as month names, weekdays, and AM/PM?
- **Time zone:** where is an instant interpreted as local time, or which zone is a zone-less string understood to be in?

The same `Date` can be formatted as 02:15 UTC or 09:15 in Vietnam. Changing the `Locale` can turn `Jun` into `juin`, but it will not automatically convert 02:15 into 09:15.

[Java SE 21 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html) describes the pattern syntax and locale-aware formatting/parsing behavior. For new code using `java.time`, `DateTimeFormatter` is usually chosen; this article focuses on handling things correctly when you have to work with the legacy API.

## 2. Reading patterns with exact letter case

| Common symbol | Meaning in `SimpleDateFormat` | Example |
| --- | --- | --- |
| `yyyy` | Year | `2025` |
| `MM` | Numeric month when formatting | `06` |
| `MMM` / `MMMM` | Short / full month name | `Jun` / `June` with English Locale |
| `dd` | Day of month | `10` |
| `HH` | 24-hour hour, 0–23 | `09`, `21` |
| `hh` and `a` | 12-hour hour and AM/PM marker | `09 PM` |
| `mm` | Minute | `15` |
| `ss` | Second | `30` |
| `SSS` | Millisecond | `007` |
| `XXX` | ISO-style offset with `:` | `+07:00` or `Z` |
| `Z` | RFC 822-style offset | `+0700` |
| `z` | Zone name/description | Depends on zone and Locale data |

Pairs that are easy to confuse are `MM` vs. `mm`, `dd` vs. `DD`, and `yyyy` vs. `YYYY`. In this API, `D` is the day of the year, while `Y` is the week-based year. Therefore, `YYYY-MM-dd` can pair the wrong kind of year with the month/day around year boundaries.

Literal text segments must be enclosed in single quotes in the pattern, such as `"yyyy-MM-dd 'at' HH:mm"`. To represent a single quote in the text, the pattern uses two consecutive single quotes. For ISO strings containing the letter `T`, use `"yyyy-MM-dd'T'HH:mm:ssXXX"`.

The number of repeated pattern letters affects formatting, such as zero-padding or choosing the full name. However, when parsing numbers, `SimpleDateFormat` does not always enforce the exact width that a reader might infer from the letter count in the pattern. `setLenient(false)` checks calendar date validity, not a full format validation expression for the entire string.

## 3. Configuring `Locale` explicitly

You can create a formatter with:

```java
SimpleDateFormat format = new SimpleDateFormat(
        "dd MMM yyyy HH:mm:ss XXX", Locale.ENGLISH);
```

If month names or AM/PM markers in a specific language are used in the source contract, you must choose the matching `Locale`. Do not rely on the server's default `Locale` to parse English files and expect it to behave the same as on the author's machine.

Changing the `Locale` does not automatically reorder a fixed written pattern such as `dd MMM yyyy`. If you want to format dates according to a region's conventional style rather than a specific pattern contract, `DateFormat.getDateInstance()` / `getDateTimeInstance()` provide an alternative approach.

`Locale` can also affect supporting formatting/calendar components in the legacy API, so at data boundaries you need to know the source's calendar system. Do not assume that just because a month name looks right, all date fields have been interpreted according to the intended contract.

Avoid two-digit years if the source requires a stable year meaning. Interpreting `yy` relies on a century window that depends on the formatter configuration; four-digit year strings are usually clearer. If you are required to accept two-digit years, define the interpretation window and configure it explicitly rather than guessing.

## 4. Time zones affect both formatting and parsing

`Date` represents an instant in milliseconds; it does not hold its own time zone like `ZonedDateTime`. The formatter uses `setTimeZone(...)` to choose how that instant is viewed when outputting a string.

For example, the instant `2025-06-10T02:15:30Z` is formatted as `2025-06-10 09:15:30 +07:00` when the formatter uses `Asia/Ho_Chi_Minh`. The original instant object does not have seven hours added to it.

When parsing:

- If the string has no offset/zone, the configured zone provides the context to interpret the local time.
- If the pattern and string include an offset such as `+07:00`, that information participates in determining the instant; do not treat the configured time zone as an instruction to ignore the offset written in the string.

When receiving a zone name from configuration, note that [TimeZone.getTimeZone(String)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TimeZone.html#getTimeZone(java.lang.String)) can silently fall back to GMT for unrecognized IDs. The example below accepts a validated `ZoneId` and converts it using `TimeZone.getTimeZone(zone)` to prevent a typo in an ID from silently becoming GMT.

Do not use ambiguous abbreviations like `CST` when the contract requires a specific zone. Zone IDs like `Asia/Ho_Chi_Minh` or an explicit offset express the choice more clearly.

## 5. Complete verification program

Save the code to `LegacyFormatterSettingsDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.text.*;
import java.time.*;
import java.util.*;

public class LegacyFormatterSettingsDemo {
    private static SimpleDateFormat formatter(
            String pattern, Locale locale, ZoneId zone) {
        SimpleDateFormat format = new SimpleDateFormat(pattern, locale);
        format.setTimeZone(TimeZone.getTimeZone(zone));
        format.setLenient(false);
        return format;
    }

    private static Date parseAll(SimpleDateFormat format, String text)
            throws ParseException {
        ParsePosition position = new ParsePosition(0);
        Date result = format.parse(text, position);
        if (result == null || position.getIndex() != text.length()) {
            int error = position.getErrorIndex();
            throw new ParseException("Invalid complete date",
                    error >= 0 ? error : position.getIndex());
        }
        return result;
    }

    public static void main(String[] args) throws ParseException {
        ZoneId utc = ZoneOffset.UTC;
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        Date moment = Date.from(Instant.parse("2025-06-10T02:15:30Z"));

        SimpleDateFormat english = formatter(
                "dd MMM yyyy HH:mm:ss XXX", Locale.ENGLISH, utc);
        SimpleDateFormat french = formatter(
                "dd MMM yyyy HH:mm:ss XXX", Locale.FRENCH, utc);
        System.out.println("English UTC = " + english.format(moment));
        System.out.println("French UTC = " + french.format(moment));

        SimpleDateFormat local = formatter(
                "yyyy-MM-dd HH:mm:ss XXX", Locale.ROOT, hcm);
        System.out.println("HCM = " + local.format(moment));
        System.out.println("original instant = " + moment.toInstant());

        SimpleDateFormat source = formatter(
                "yyyy-MM-dd HH:mm", Locale.ROOT, hcm);
        Date parsed = parseAll(source, "2025-06-10 09:15");
        System.out.println("local input -> instant = " + parsed.toInstant());

        SimpleDateFormat withOffset = formatter(
                "yyyy-MM-dd'T'HH:mm:ssXXX", Locale.ROOT, utc);
        Date offsetParsed = parseAll(
                withOffset, "2025-06-10T09:15:30+07:00");
        System.out.println("offset input -> instant = "
                + offsetParsed.toInstant());

        SimpleDateFormat dateOnly = formatter("yyyy-MM-dd", Locale.ROOT, utc);
        try {
            parseAll(dateOnly, "2025-02-29");
        } catch (ParseException ex) {
            System.out.println("invalid date = ParseException");
        }
        try {
            parseAll(dateOnly, "2025-06-10tail");
        } catch (ParseException ex) {
            System.out.println("trailing input = ParseException");
        }

        Date fraction = Date.from(Instant.parse("2025-06-10T02:15:30.007Z"));
        System.out.println("legacy SSS = "
                + formatter("HH:mm:ss.SSS", Locale.ROOT, utc).format(fraction));
        SimpleDateFormat quoted = formatter(
                "yyyy-MM-dd 'at' HH:mm", Locale.ENGLISH, hcm);
        System.out.println("quoted text = " + quoted.format(moment));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LegacyFormatterSettingsDemo.java
java LegacyFormatterSettingsDemo
```

Verified output with the runtime's Locale data used in this article:

```text
English UTC = 10 Jun 2025 02:15:30 Z
French UTC = 10 juin 2025 02:15:30 Z
HCM = 2025-06-10 09:15:30 +07:00
original instant = 2025-06-10T02:15:30Z
local input -> instant = 2025-06-10T02:15:00Z
offset input -> instant = 2025-06-10T02:15:30Z
invalid date = ParseException
trailing input = ParseException
legacy SSS = 02:15:30.007
quoted text = 2025-06-10 at 09:15
```

The input instants are created from fixed ISO strings, and all formatters have explicit zones configured. Therefore, the hour differences in the example come from the chosen settings, not the machine's current clock.

## 6. Key observations from the program

### Same pattern, different Locale

`english` and `french` use the same pattern and the UTC zone. The time remains 02:15:30, while the month name changes from `Jun` to `juin`. Language and time zone serve two independent roles.

Displayed month names depend on the runtime's Locale data. For exchange contracts that need more stable strings, numeric month fields and clear time zone/offset conventions are usually preferred.

### Zone-less strings need the source's zone

`source` parses `2025-06-10 09:15` in the Vietnam zone and produces the instant `2025-06-10T02:15:00Z`. Seconds do not appear in the input pattern and default to 0 in the example. Parsing the same string in UTC would yield a different instant; you cannot choose a zone based merely on what is convenient for where the program runs.

`withOffset`, on the other hand, parses a string with `+07:00`, so the corresponding instant is 02:15:30 UTC. The program prints `Date.toInstant()` to clearly show the instant value; `Date.toString()` formats using the environment's default time zone and can mislead readers into thinking the data was altered.

### Invalid dates and trailing text are two separate checks

The `formatter()` helper calls `setLenient(false)` so that `2025-02-29` is rejected. However, setting that mode alone does not guarantee that the entire string is consumed.

[Java SE 21 — DateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DateFormat.html) supports parsing with a `ParsePosition`, which tracks how far the parser read. `parseAll()` requires a non-`null` result and a final index equal to the string length. That prevents `2025-06-10tail` from being treated as valid just because a date could be parsed at the beginning.

`parseAll()` still does not turn a legacy numeric pattern into a strict width validator for every field. If a contract requires an exact number of digits, validate the shape accordingly or choose a parser configured to enforce that requirement. Do not confuse three separate checks: parsing a prefix, having a valid calendar date, and matching the entire string format.

## 7. Do not copy patterns between the legacy and modern APIs without checking

In `SimpleDateFormat`, `S` is the millisecond field. `SSS` formats 7 milliseconds as `007`, as shown in the `legacy SSS` line above. In `DateTimeFormatter`, `S` represents fraction-of-second digits. Similarity in a three-digit pattern does not guarantee that every count of `S` or its parsing behavior is equivalent.

In particular, `u` in `SimpleDateFormat` is the day number of the week, not a proleptic year like `u` in `DateTimeFormatter`. Therefore, do not directly replace `yyyy` in a legacy pattern with `uuuu` from the modern API.

When migrating code, test actual patterns, year-end/start boundaries, fractional seconds, offsets, and inputs with month names. A pattern that looks identical is not proof that both APIs parse and format with the same meaning.

## 8. Using stateful formatters in legacy code

`SimpleDateFormat` can be mutated via `applyPattern()`, `setTimeZone()`, or other settings; it is not an immutable formatter that can be freely shared across multiple threads. Create a separate instance for an appropriate scope or use proper synchronization if sharing is unavoidable. A `static final` field only fixes the reference; it does not make the object thread-safe.

Parsing also uses internal `Calendar` state; zone information can be affected by parsed input. When reusing a formatter across different sources, keep its configuration and lifecycle explicit rather than assuming it shares the properties of `DateTimeFormatter`.

You do not need to rewrite an entire application just to read a single legacy interface. You can isolate the `Date`/string conversion at the boundary, keep business calculations on the appropriate `java.time` types, and convert back only when an external API requires it.

Exercise: keep `moment` unchanged, but change the output formatter to the UTC zone and the pattern `yyyy-MM-dd HH:mm:ss Z`. The offset part in the output should be `+0000`, whereas with `XXX` it is `Z`. Next, replace `HH:mm` with `hh:mm a` for a 21:00 time in the chosen zone and verify that the `PM` marker is preserved; do not omit `a` if the source uses a 12-hour clock and still needs to distinguish morning from evening.
