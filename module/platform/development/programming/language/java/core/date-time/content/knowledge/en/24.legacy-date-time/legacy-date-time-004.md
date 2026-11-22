# `Calendar` Month Index and Common Off-by-One Month Bugs

## 1. January Is Represented by 0

In `GregorianCalendar`, the value of the `Calendar.MONTH` field is zero-based: January is 0, February is 1, ..., December is 11. This is an error-prone convention when input data or modern APIs use month numbers 1–12.

For example, `calendar.set(2025, 1, 15)` creates **February** 15, not January 15. The number 1 is a valid month index, so even strict mode cannot tell that the author actually meant January.

[Java SE 21 — Calendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html) describes the month field and constants such as `JANUARY`. For code that must use `Calendar`, prefer named constants or convert conventions explicitly at data boundaries.

| Conventional month number | `Calendar.MONTH` value in Gregorian | Named constant |
| --- | ---: | --- |
| 1 | 0 | `Calendar.JANUARY` |
| 2 | 1 | `Calendar.FEBRUARY` |
| 6 | 5 | `Calendar.JUNE` |
| 12 | 11 | `Calendar.DECEMBER` |

This article uses `GregorianCalendar` explicitly. `Calendar` is an abstract class that supports multiple calendar systems; do not assume every custom calendar system has only 12 months. The `UNDECIMBER` constant exists to represent the 13th month in an applicable calendar system, but it does not add a valid month to a standard Gregorian year.

## 2. Distinguishing the Field Name from the Field Value

Two kinds of constants appear together in `Calendar` but serve different roles:

| Constant | Role | Usage example |
| --- | --- | --- |
| `Calendar.MONTH` | Selects the month field to read/set/add | `get(Calendar.MONTH)` |
| `Calendar.JUNE` | Value for June in Calendar's convention | `set(Calendar.MONTH, Calendar.JUNE)` |

With the `set(year, month, day)` overload, the second parameter is the **month value**, not the field identifier. Therefore, writing `set(2025, Calendar.MONTH, 10)` confuses the roles of the constants; it is not a way to select "set month" for this overload.

Two common correct approaches:

```java
// Illustrated inside a method; cal is an already-prepared Calendar.
cal.set(2025, Calendar.JUNE, 10);
cal.set(Calendar.MONTH, Calendar.JUNE);
```

The first call sets the year/month/day tuple. The second call only sets the month field on the existing object, so the remaining fields still need to be considered. `Calendar` is mutable; do not treat `set()` calls as creating a new immutable value like `LocalDate`.

## 3. Converting Between External Conventions and Calendar Exactly Once

If a form or JSON specifies months 1–12, convert into `GregorianCalendar` using `month - 1`. When outputting a raw month value from `GregorianCalendar` to an interface expecting 1–12, convert using `get(MONTH) + 1`.

```text
Contract data 1..12  ── subtract 1 ──>  Calendar 0..11
Calendar 0..11       ── add 1 ───────>  Contract data 1..12
```

The prerequisite is that you already know the source's convention. Do not add or subtract across multiple layers "just to be sure," because you might convert twice. A variable like `calendarMonthIndex` and a variable like `monthNumber` should have distinct, clear meanings.

Do not subtract 1 from the `Calendar.JUNE` constant: it is already the right value for Calendar. Conversely, `Month.JUNE.getValue()` follows the modern API's 1–12 convention, so do not pass that raw number into the month parameter of `Calendar.set(year, month, day)`.

For month inputs following the 1–12 contract, validate the range at the input boundary before converting. That rejects month 0 or 13 according to the input semantics, rather than letting lenient mode interpret it as a date in another year.

## 4. Complete Verification Program

Save the following code to `CalendarMonthIndexDemo.java`. The program requires Java 17 or later and needs no external libraries:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;

public class CalendarMonthIndexDemo {
    private static GregorianCalendar calendar(boolean lenient) {
        GregorianCalendar value = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        value.clear();
        value.setLenient(lenient);
        return value;
    }

    private static String isoDate(Calendar value) {
        return value.toInstant().atZone(ZoneOffset.UTC)
                .toLocalDate().toString();
    }

    public static void main(String[] args) {
        GregorianCalendar correct = calendar(false);
        correct.set(2025, Calendar.JANUARY, 15);
        System.out.println("January raw = " + correct.get(Calendar.MONTH));
        System.out.println("January display = "
                + (correct.get(Calendar.MONTH) + 1));
        System.out.println("correct date = " + isoDate(correct));

        GregorianCalendar wrong = calendar(false);
        wrong.set(2025, 1, 15);
        System.out.println("set month 1 = " + isoDate(wrong));

        int userMonth = 6;
        GregorianCalendar fromInput = calendar(false);
        fromInput.set(2025, userMonth - 1, 10);
        System.out.println("human month 6 = " + isoDate(fromInput));
        System.out.println("Calendar.JUNE = " + Calendar.JUNE);
        System.out.println("Month.JUNE value = " + Month.JUNE.getValue());

        GregorianCalendar normalized = calendar(true);
        normalized.set(2025, 12, 15);
        System.out.println("lenient month 12 = " + isoDate(normalized));

        GregorianCalendar rejected = calendar(false);
        rejected.set(2025, 12, 15);
        System.out.println("strict set returned");
        try {
            rejected.getTimeInMillis();
        } catch (IllegalArgumentException ex) {
            System.out.println("strict read = IllegalArgumentException");
        }

        GregorianCalendar leap = calendar(false);
        leap.set(2024, Calendar.FEBRUARY, 29);
        System.out.println("leap date = " + isoDate(leap));

        LocalDate modern = LocalDate.of(2025, 6, 10);
        GregorianCalendar converted = GregorianCalendar.from(
                modern.atStartOfDay(ZoneOffset.UTC));
        System.out.println("conversion raw month = "
                + converted.get(Calendar.MONTH));
        System.out.println("modern month = " + modern.getMonthValue());
        System.out.println("round trip = "
                + converted.toZonedDateTime().toLocalDate());

        DateTimeFormatter output = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT);
        System.out.println("formatted modern = " + modern.format(output));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CalendarMonthIndexDemo.java
java CalendarMonthIndexDemo
```

Output:

```text
January raw = 0
January display = 1
correct date = 2025-01-15
set month 1 = 2025-02-15
human month 6 = 2025-06-10
Calendar.JUNE = 5
Month.JUNE value = 6
lenient month 12 = 2026-01-15
strict set returned
strict read = IllegalArgumentException
leap date = 2024-02-29
conversion raw month = 5
modern month = 6
round trip = 2025-06-10
formatted modern = 2025-06-10
```

## 5. Why Does the Example Call `clear()` and Choose UTC?

A new `Calendar` usually has its time fields already initialized. If you only set year/month/day on that object, old hour/minute/second or millisecond values may remain. Calling `clear()` in this article's helper clears previously set fields before constructing the target point in time, preventing the example from retaining components from the time the program ran.

UTC is chosen explicitly for `GregorianCalendar` and for converting to a display date. That way, stdout does not depend on the machine's default time zone. The `isoDate()` helper is only meant for the UTC values prepared in this article; for real data in another time zone, choose the display time zone according to the contract instead of blindly converting to UTC and expecting the calendar date to stay the same.

These choices isolate month-index bugs from bugs caused by leftover data or time zones. When investigating a shifted date, check them separately: adding or subtracting the month index cannot fix a date shifted by a time-zone conversion.

## 6. Lenient Mode Can Hide Bugs; Strict Mode Still Has Limits

In a lenient `GregorianCalendar`, a month value of 12 is interpreted as advancing 12 months from month 0 of the year, so `set(2025, 12, 15)` becomes `2026-01-15`. If the author thought 12 meant December, the bug not only shifts the date by one month but also changes the year.

`setLenient(false)` requires fields to be valid when `Calendar` computes the instant or recomputes fields. The program shows that `set()` can return first, and then `getTimeInMillis()` throws `IllegalArgumentException`. Therefore, do not conclude that data is validated just because the setter call did not throw an error.

However, the number 1 is still a valid February. Strict mode cannot know you meant January, so this convention-mismatch bug is not caught. You must verify the resulting date value against business expectations, not just check whether an exception was thrown.

Similarly, subtracting 1 to get the right month does not guarantee the date combination exists: February 2025 has no 29th day. The `2024-02-29` case in the article is valid because it is a leap year; validity checks must consider year, month, and day together.

## 7. Moving to `java.time`: Month Numbers Are 1–12

[Java SE 21 — Month](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Month.html) uses values 1 for January through 12 for December and recommends using `getValue()` instead of `ordinal()` to obtain the month number.

Modern ways to construct a date are more readable:

```java
LocalDate numeric = LocalDate.of(2025, 6, 10);
LocalDate named = LocalDate.of(2025, Month.JUNE, 10);
```

Both create the date `2025-06-10`. Do not apply Calendar's subtract-1 habit to the month parameter of `LocalDate.of()`: the number 5 there means May.

When you must bridge to legacy code, convert via API methods instead of copying fields one by one. In the program, `GregorianCalendar.from(modern.atStartOfDay(UTC))` creates the corresponding Calendar object, and `toZonedDateTime().toLocalDate()` retrieves the modern date back.

`LocalDate` does not contain a time or time zone, so calling `atStartOfDay(UTC)` is a deliberate choice of instant to convert to a Calendar type that carries an instant and time zone. If the application needs another time zone or time of day, choose according to that requirement. Do not treat the UTC choice in this example as a mandatory default for every conversion.

If you only need to output a date string, use a formatter with modern types or an appropriate formatter for legacy data, instead of manually concatenating `year + "-" + rawMonth + "-" + day`. Formatters understand field conventions; manually concatenated strings can have both the wrong month and missing leading zeros.

## 8. Common Mistakes to Keep Separate

| Code snippet / idea | Bug or meaning |
| --- | --- |
| `set(2025, 6, 10)` intending June | Calendar interprets it as July |
| `get(Calendar.MONTH)` then display directly | A 1–12 UI may display 0–11 |
| `set(2025, Calendar.JUNE - 1, 10)` | Calendar constant already follows the convention, subtracted an extra time |
| `LocalDate.of(2025, Calendar.JUNE, 10)` | Calendar's 5 is interpreted as May in LocalDate |
| `add(Calendar.MONTH, 1)` | Adds one month; do not subtract 1 from the amount to add |

The final `add()` row helps distinguish a **month position value** from a **number of months to add**. Zero-based indexing does not mean every month-related parameter must be decremented by one.

Do not use `Month.ordinal()` to bridge APIs just because it happens to be zero-based. Use `getValue()` per `Month`'s contract, and convert to the Calendar index at the right boundary if truly needed. That expresses intent better and avoids mixing enum positions with domain values.

Exercise: create the date `2025-12-31` using a strict `GregorianCalendar` with `Calendar.DECEMBER`, then convert it back to `LocalDate`. Verify that the raw month is 11 while the date string must be `2025-12-31`. Next, replace the month constant with the number 12 to see the data rejected when computing the instant; enabling lenient mode will roll over to January 2026 instead of keeping December as originally intended.
