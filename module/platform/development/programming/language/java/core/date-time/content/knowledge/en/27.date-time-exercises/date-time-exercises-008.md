# Migrating Date, Calendar, and SimpleDateFormat Code to java.time

## 1. The Goal Is Preserving Semantics, Not Just Replacing Class Names

`java.util.Date` represents an instant in time with millisecond precision; `Calendar` associates an instant with calendar fields and a time zone; `SimpleDateFormat` formats and parses strings according to its configuration. Legacy code might use them for a birth date, an event instant, or a local date-time.

Before editing, identify what the data actually represents and document the behavior that must be preserved: time zone, locale, format, parsing strictness, calendar arithmetic, and precision. Do not mechanically replace every `Date` variable with `LocalDateTime`.

| Identified meaning | Common `java.time` type |
| --- | --- |
| An instant that occurred | `Instant` |
| A pure calendar date | `LocalDate` |
| A local date-time without a time zone | `LocalDateTime` |
| A date-time governed by a location's rules | `ZonedDateTime` or date-time + `ZoneId` |
| Formatting/parsing strings | `DateTimeFormatter` |

## 2. Bridging at Legacy API Boundaries

For a standard `java.util.Date`:

```java
Instant instant = legacyDate.toInstant();
java.util.Date legacyAgain = java.util.Date.from(instant);

Instant fromMillis = Instant.ofEpochMilli(epochMillis);
long millisAgain = instant.toEpochMilli();
```

This is an illustrative snippet inside a method. `epochMillis` is in milliseconds; do not pass it directly to `Instant.ofEpochSecond`, as that would shift the value by a factor of 1,000.

`Date` does not store a `ZoneId`; `Date.toString()` may display in the default time zone without changing the instant it holds. To obtain a date from a `Date`, choose a time zone first and then use `date.toInstant().atZone(zone).toLocalDate()`.

`Instant` can hold nanoseconds, whereas `java.util.Date` only holds milliseconds. When converting an `Instant` with sub-millisecond precision through `Date`, that information is lost; do not promise that every round-trip conversion restores the original value intact. [java.util.Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html)

`java.sql.Date` in particular does not follow the same contract: use `toLocalDate()` for SQL dates; its `toInstant()` always throws `UnsupportedOperationException`. If an API declares `java.util.Date` but actually returns a JDBC subclass, check the type/semantics at the boundary. [java.sql.Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Date.html#toInstant())

## 3. Calendar: From Mutating State to Receiving New Values

Legacy code may mutate an object directly:

```java
calendar.add(Calendar.DAY_OF_MONTH, 1);
```

With immutable types, capture the returned value:

```java
ZonedDateTime next = current.plusDays(1);
```

Calling `current.plusDays(1)` and discarding the return value does not modify `current`. Check places where legacy code relied on passing a `Calendar` and mutating it through a shared reference.

Some differences to cross-check:

- `Calendar.MONTH` typically uses 0–11 months; `Month.getValue()` and `getMonthValue()` use 1–12.
- `Calendar.DAY_OF_WEEK` uses a different numbering scheme from ISO `DayOfWeek`; do not pass raw numbers directly between the two APIs.
- `Calendar.HOUR` is the hour within a 12-hour cycle, distinct from `HOUR_OF_DAY`; do not mistakenly convert it to a 24-hour value while dropping AM/PM.
- `add` and `roll` are not synonymous; do not replace every `roll` with `plus`, because the rules for rolling over larger fields differ.
- Adding one calendar day in a time zone is not always equivalent to adding 86,400,000 milliseconds.

`Calendar` can operate in lenient mode and normalize out-of-range values. If you need to preserve that behavior or intentionally change it, state so explicitly and test it separately. [Calendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html)

## 4. SimpleDateFormat: Reviewing Patterns and Parsing Policies

`DateTimeFormatter` is immutable and thread-safe, making it suitable as a shared constant. `SimpleDateFormat` has mutable state and is not safe when multiple threads use the same instance without synchronization.

Do not copy pattern characters verbatim while ignoring their meaning:

| Issue | What to do when migrating? |
| --- | --- |
| Ordinary year | Usually choose `uuuu` for the ISO year when parsing strictly |
| `yyyy` | Year-of-era in the new formatter; era information must be considered |
| `YYYY` | Week-based year, not an uppercase calendar year |
| `u` | Day number of week in `SimpleDateFormat`; year in `DateTimeFormatter` |
| `S` | Legacy API expresses milliseconds; the new formatter uses fraction-of-second, where width matters |
| Time zone/offset | Cross-check pattern letters against input data rather than guessing equivalence |

`DateTimeFormatter.ofPattern` defaults to `SMART` resolution; `setLenient(false)` in legacy code is not automatically carried over to the new configuration. If nonexistent dates must be rejected, use `withResolverStyle(ResolverStyle.STRICT)` with an appropriate pattern.

Full-string parsing also needs checking: legacy code using `ParsePosition` might have had to verify that the entire input was consumed; `LocalDateTime.parse` with a formatter reads the entire string. Differences in field widths or trailing characters can cause the new parser to reject input that the legacy code accepted. [SimpleDateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html), [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

## 5. Before-and-After Comparison Program

This example processes a date-time string in Vietnam, adds one calendar day, and formats it again. Both branches explicitly select the time zone, locale, and date validation; the sample data does not fall within a gap or overlap.

Save as `LegacyTimeMigrationDemo.java`:

```java
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyTimeMigrationDemo {
    static Date parseLegacy(String text, SimpleDateFormat format) {
        ParsePosition position = new ParsePosition(0);
        Date value = format.parse(text, position);
        if (value == null || position.getIndex() != text.length()) {
            throw new IllegalArgumentException("Invalid legacy input");
        }
        return value;
    }

    public static void main(String[] args) {
        String input = "2024-02-29 23:30:00";
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        TimeZone legacyZone = TimeZone.getTimeZone(zone);

        SimpleDateFormat oldFormat =
                new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ROOT);
        oldFormat.setLenient(false);
        oldFormat.setTimeZone(legacyZone);
        Date oldParsed = parseLegacy(input, oldFormat);
        Calendar oldCalendar = new GregorianCalendar(legacyZone, Locale.ROOT);
        oldCalendar.setLenient(false);
        oldCalendar.setTime(oldParsed);
        oldCalendar.add(Calendar.DAY_OF_MONTH, 1);
        Instant oldResult = oldCalendar.toInstant();

        DateTimeFormatter newFormat =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);
        LocalDateTime local = LocalDateTime.parse(input, newFormat);
        ZonedDateTime current = local.atZone(zone);
        ZonedDateTime next = current.plusDays(1);
        Instant newResult = next.toInstant();

        System.out.println("oldInstant=" + oldResult);
        System.out.println("newInstant=" + newResult);
        System.out.println("sameInstant=" + oldResult.equals(newResult));
        System.out.println("oldText=" + oldFormat.format(oldCalendar.getTime()));
        System.out.println("newText=" + newFormat.withZone(zone).format(newResult));
        System.out.println("legacyMonthIndex=" + oldCalendar.get(Calendar.MONTH));
        System.out.println("modernMonthValue=" + next.getMonthValue());
        System.out.println("currentUnchanged=" + current.toLocalDateTime());

        Date boundary = Date.from(newResult);
        System.out.println("millisecondRoundTrip="
                + newResult.equals(boundary.toInstant()));
        Instant precise = Instant.parse("2024-02-29T16:30:00.123456789Z");
        System.out.println("afterLegacyPrecision=" + Date.from(precise).toInstant());

        try {
            parseLegacy("2023-02-29 23:30:00", oldFormat);
        } catch (IllegalArgumentException ex) {
            System.out.println("legacyRejectsInvalidDate");
        }
        try {
            LocalDateTime.parse("2023-02-29 23:30:00", newFormat);
        } catch (DateTimeParseException ex) {
            System.out.println("modernRejectsInvalidDate");
        }
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 LegacyTimeMigrationDemo.java
java LegacyTimeMigrationDemo
```

Exact stdout under Vietnam's time-zone rules for the dates in the example:

```text
oldInstant=2024-03-01T16:30:00Z
newInstant=2024-03-01T16:30:00Z
sameInstant=true
oldText=2024-03-01 23:30:00
newText=2024-03-01 23:30:00
legacyMonthIndex=2
modernMonthValue=3
currentUnchanged=2024-02-29T23:30
millisecondRoundTrip=true
afterLegacyPrecision=2024-02-29T16:30:00.123Z
legacyRejectsInvalidDate
modernRejectsInvalidDate
```

`millisecondRoundTrip` is true because `newResult` has no sub-millisecond precision. The next line demonstrates that you cannot generalize that result to every `Instant`.

## 6. Do Not Hide Time-Zone or DST Changes Inside an API Swap

For local time data, `local.atZone(zone)` has default behavior when encountering nonexistent or overlapping times. Legacy code also has its own resolution rules, so do not assume both branches choose the same instant for every DST case.

Test inputs in gaps and overlaps, preserve the chosen offset if needed, and decide explicitly when to report an error. If the policy changes, treat it as a business-logic change that must be documented, not an invisible detail of the migration.

If legacy code uses `TimeZone.getDefault()`, identify the actually intended time zone before replacing it with a `ZoneId`. Keeping or removing the dependency on the default must be a deliberate decision.

## 7. Keep Bridges Narrow and Test Meaningful Behavior

During a gradual migration, you can keep `Date` in the signature of a legacy library, convert to `Instant` as soon as execution enters the new code, and convert back at the exit. There is no need to scatter conversions back and forth across every operation.

For `GregorianCalendar`, `toZonedDateTime()` is a useful bridge. However, the legacy Gregorian calendar can use a Julian/Gregorian cutover, whereas the ISO types in `java.time` apply proleptic Gregorian rules. Historical dates or other calendar systems must be tested separately rather than inferred from a 2024 example. [GregorianCalendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html)

Valuable checks during migration include:

- Same instant before and after passing through supported bridges.
- Same display text when time zone, locale, and formatting contract must be preserved.
- Month-end dates, leap years, year-end boundaries, and week numbers.
- Invalid dates/times, trailing characters, and input that used to be parsed leniently.
- DST and precision lost when passing through legacy APIs.
- Code sharing a formatter across multiple threads and code that previously relied on mutable state.

Do not merely compare `toString()` of objects of different types: they may represent the same instant differently. Compare `Instant`, calendar dates, or explicitly formatted strings depending on what needs to be preserved.

## 8. Extension Exercises

1. Migrate a birth date from `Date` to `LocalDate`, explicitly stating the time zone used to interpret the legacy data.
2. Replace day addition with adding 24 hours in an experiment across DST and observe the difference.
3. Add input with trailing characters to verify that both branches reject it according to the chosen contract.
4. Test nanosecond fractions and verify where the boundary lies that still preserves milliseconds.

The desired outcome is new code with semantically accurate types and verified behavior; any changes in parsing, calendar rules, or time zones must be clearly identified.