# 12-Hour, 24-Hour Time, and AM/PM Markers in Java

## 1. Two Ways to Represent Time

Java provides `java.time.LocalTime` to represent a time of day independent of a calendar date and time zone. A value such as `LocalTime.of(13, 5, 9)` stores hour 13, minute 5, and second 9. When displaying it, an application can choose either the **24-hour** format (13:05:09) or the **12-hour format with AM/PM** (01:05:09 PM).

These two representations are simply two presentation styles for the same time of day:

| 24-Hour Time | 12-Hour Time | Description |
|---|---|---|
| 00:00 | 12:00 AM | Midnight |
| 01:00 | 01:00 AM | One o'clock in the morning |
| 11:59 | 11:59 AM | Before noon |
| 12:00 | 12:00 PM | Noon |
| 12:01 | 12:01 PM | After noon |
| 13:00 | 01:00 PM | One o'clock in the afternoon |
| 23:59 | 11:59 PM | Before midnight |

In the 24-hour format, the hour field is normally in the range `00..23`. In the 12-hour format, the clock hour is in the range `1..12`, while AM/PM identifies the half of the day. **12 AM is midnight; 12 PM is noon.** Do not just compute `hour % 12` and forget to add AM/PM, because doing so turns both 00:00 and 12:00 into 12:00 and loses essential information.

This lesson uses `DateTimeFormatter` to convert between formats, read key pattern letters, parse 12-hour strings into a `LocalTime` value, handle locales, and check common pitfalls.

## 2. Important Pattern Letters

`DateTimeFormatter` uses case-sensitive pattern letters to select time fields. For hour formatting, the four most easily confused letters are `H`, `h`, `K`, and `k`:

| Pattern | Field Name | Hour Range | Midnight | Noon |
|---|---|---:|---|---|
| `H` / `HH` | Hour-of-day, 24-hour | 0–23 | 0 / 00 | 12 / 12 |
| `h` / `hh` | Clock-hour-of-am-pm, 12-hour | 1–12 | 12 | 12 |
| `K` / `KK` | Hour-of-am-pm, 0-based 12-hour | 0–11 | 0 | 0 |
| `k` / `kk` | Clock-hour-of-day, 1–24 24-hour | 1–24 | 24 | 12 |

In most general-purpose UIs, use `HH:mm` for 24-hour time and `hh:mm a` for 12-hour time with AM/PM. `H` is appropriate when hour 0 should be displayed as `0` rather than `00`; `HH` ensures two digits when formatting. Similarly, `h` produces hours 1–12 without zero-padding, while `hh` displays 01–12.

`K` and `k` are valid but less common in typical user interfaces. `K` counts 0–11 within a half-day; `k` counts 1–24 within a day and represents midnight as 24. For display or data exchange, only use those patterns when the format contract specifically requires their exact semantics.

Additional symbols:

| Pattern | Meaning | Example |
|---|---|---|
| `m` / `mm` | Minute | `5` / `05` |
| `s` / `ss` | Second | `9` / `09` |
| `a` | Locale-specific AM/PM marker | `AM` / `PM` in Locale.US |
| `'text'` | Quoted literal text | `hh 'hr' mm` |
| `'T'` | Literal letter T | Can be used when manually combining ISO date and time |

**Be careful:** `MM` is **month**, whereas `mm` is **minute**. `HH` is 24-hour time, and `hh` is 12-hour time; they differ only in letter case, yet produce completely different results.

## 3. Formatting 24-Hour Time

To display time in 24-hour format:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalTime time = LocalTime.of(13, 5, 9);
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("HH:mm:ss", Locale.ROOT);

System.out.println(time.format(formatter));
~~~

Stdout:

~~~text
13:05:09
~~~

`HH:mm:ss` means:

- `HH`: hour 00–23, always two digits when formatted.
- `mm`: minute 00–59.
- `ss`: second 00–59.

A few sample times:

~~~java
DateTimeFormatter f = DateTimeFormatter.ofPattern("HH:mm", Locale.ROOT);
System.out.println(LocalTime.MIDNIGHT.format(f));
System.out.println(LocalTime.NOON.format(f));
System.out.println(LocalTime.of(9, 7).format(f));
~~~

Stdout:

~~~text
00:00
12:00
09:07
~~~

`LocalTime.MIDNIGHT` represents `00:00`; `LocalTime.NOON` represents `12:00`. With 24-hour format, do not append `a` because the AM/PM marker is unnecessary and does not belong in this format.

In applications that need standardized machine-readable data, a 24-hour format such as `HH:mm:ss` avoids AM/PM ambiguity. If nanoseconds are needed, use a formatter with the corresponding fractional-second pattern, such as `HH:mm:ss.SSSSSSSSS`; that only formats the stored nanosecond field and does not increase the precision of the source clock.

## 4. Formatting 12-Hour Time with AM/PM

Commonly used pattern:

~~~java
DateTimeFormatter twelveHour =
        DateTimeFormatter.ofPattern("hh:mm:ss a", Locale.US);

LocalTime time = LocalTime.of(13, 5, 9);
System.out.println(time.format(twelveHour));
~~~

Stdout:

~~~text
01:05:09 PM
~~~

`hh` formats the 1–12 clock-hour field, `mm` is minutes, `ss` is seconds, and `a` outputs the locale-specific AM/PM marker. You can omit seconds when the UI only needs hours and minutes:

~~~java
DateTimeFormatter shortTwelve =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);
System.out.println(LocalTime.of(9, 5).format(shortTwelve));
System.out.println(LocalTime.of(13, 5).format(shortTwelve));
~~~

Stdout:

~~~text
9:05 AM
1:05 PM
~~~

`h:mm a` does not zero-pad the hour; `hh:mm a` does. Choose the pattern according to your UI design and data contract. When parsing, do not rely on the number of displayed digits to determine a time of day; use an explicit formatter to interpret the hour field and AM/PM marker.

### 4.1. Midnight and Noon

These are the edge cases to test specifically:

~~~java
DateTimeFormatter f =
        DateTimeFormatter.ofPattern("hh:mm a", Locale.US);

System.out.println(LocalTime.MIDNIGHT.format(f));
System.out.println(LocalTime.NOON.format(f));
System.out.println(LocalTime.of(0, 1).format(f));
System.out.println(LocalTime.of(12, 1).format(f));
~~~

Stdout:

~~~text
12:00 AM
12:00 PM
12:01 AM
12:01 PM
~~~

The hour conversion rules can be summarized as follows:

- Hour 00 in 24-hour format → 12 AM.
- Hours 01–11 → keep the hour, AM.
- Hour 12 → 12 PM.
- Hours 13–23 → subtract 12 to get 01–11 PM.

To convert back from 12-hour time to 24-hour time, use both the hour and AM/PM: for AM, 12 becomes 0; for PM, hours 1–11 have 12 added, while 12 PM remains 12. When parsing, let `DateTimeFormatter` handle these rules instead of splitting strings manually or writing ad-hoc arithmetic.

## 5. Parsing 12-Hour Strings into LocalTime

`LocalTime.parse(text, formatter)` parses a string using the specified format. Example:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter inputFormat =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);

LocalTime morning = LocalTime.parse("9:05 AM", inputFormat);
LocalTime afternoon = LocalTime.parse("1:05 PM", inputFormat);

System.out.println(morning);
System.out.println(afternoon);
~~~

Stdout:

~~~text
09:05
13:05
~~~

After parsing, `LocalTime` internally stores the 24-hour value in an hour field from 0 to 23. `toString()` outputs the ISO local time representation, so `13:05` appears instead of `1:05 PM`. To display it in 12-hour format again, format that value with a 12-hour formatter.

### 5.1. Parsing 12-Hour Time and Validating Invalid Input

Save this standalone example as **`TimeFormatDemo.java`**:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class TimeFormatDemo {
    public static void main(String[] args) {
        DateTimeFormatter twelve =
                DateTimeFormatter.ofPattern("hh:mm a", Locale.US);
        DateTimeFormatter twentyFour =
                DateTimeFormatter.ofPattern("HH:mm:ss", Locale.ROOT);

        LocalTime midnight = LocalTime.parse("12:00 AM", twelve);
        LocalTime noon = LocalTime.parse("12:00 PM", twelve);
        LocalTime afternoon = LocalTime.parse("01:05 PM", twelve);

        System.out.println("Midnight: " + midnight.format(twentyFour));
        System.out.println("Noon: " + noon.format(twentyFour));
        System.out.println("Afternoon: " + afternoon.format(twentyFour));
        System.out.println("Back to 12-hour: " + afternoon.format(twelve));

        try {
            LocalTime.parse("13:05 PM", twelve);
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid 12-hour time rejected");
        }
    }
}
~~~

Compile and run:

~~~bash
javac TimeFormatDemo.java
java TimeFormatDemo
~~~

Stdout:

~~~text
Midnight: 00:00:00
Noon: 12:00:00
Afternoon: 13:05:00
Back to 12-hour: 01:05 PM
Invalid 12-hour time rejected
~~~

This example tests `13:05 PM`: hour 13 is a 24-hour value, while the input pattern expects a 12-hour clock hour with AM/PM. A formatter should not be used to guess intent; define the accepted input format and report an error when input violates the contract.

## 6. How Locale Affects AM/PM

`DateTimeFormatter.ofPattern(pattern, locale)` uses the locale to render language-dependent fields, including the AM/PM marker. With `Locale.US`, the pattern `h:mm a` typically displays as `1:05 PM`. Other locales may use different scripts or formatting conventions.

~~~java
LocalTime time = LocalTime.of(13, 5);
DateTimeFormatter us =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);
DateTimeFormatter root =
        DateTimeFormatter.ofPattern("h:mm a", Locale.ROOT);

System.out.println(time.format(us));
System.out.println(time.format(root));
~~~

`Locale.ROOT` is mainly suitable for stable, language-neutral forms; for user-facing AM/PM data, choose the locale based on UI requirements. Do not assume every locale will always print the exact two ASCII letters `AM` and `PM`. The output depends on the JDK's locale data and the pattern used.

In multilingual products, clearly separate:

- **UI display format:** use the user's locale, which may translate markers and change conventions.
- **Storage or wire format:** use an agreed-upon pattern, typically a standardized 24-hour/ISO format, avoiding locale dependence.
- **User input:** know the accepted locale/format, parse with the appropriate formatter, and validate the resulting value.

Do not use localized strings as data keys or hardcode text comparisons against `"AM"`/`"PM"` when the application supports multiple languages.

## 7. DateTimeFormatter Is Immutable and Reusable

`DateTimeFormatter` is immutable and thread-safe, so shared formatters can be declared as constants:

~~~java
private static final DateTimeFormatter DISPLAY_12H =
        DateTimeFormatter.ofPattern("hh:mm a", Locale.US);

private static final DateTimeFormatter STORAGE_24H =
        DateTimeFormatter.ofPattern("HH:mm:ss", Locale.ROOT);
~~~

These declarations must be placed inside a Java class body; do not put `private static final` directly inside the `main` method. Reusing formatters avoids recreating the same pattern repeatedly and makes formatting conventions explicit.

Do not confuse `DateTimeFormatter` with the legacy `SimpleDateFormat`. `DateTimeFormatter` is immutable by design and safe to share; `SimpleDateFormat` is not thread-safe if shared without synchronization.

## 8. h/H Patterns and Common Pitfalls

### 8.1. Using H with a

`HH:mm a` combines a 24-hour clock with AM/PM. This pattern can produce confusing strings such as `13:05 PM`; avoid this combination in a standard UI when the goal is 12-hour time formatting.

Use:

~~~text
HH:mm       → 13:05
hh:mm a     → 01:05 PM
h:mm a      → 1:05 PM
~~~

### 8.2. Confusing Month with Minute

`MM` is month, `mm` is minute. The pattern `hh:MM a` attempts to print a month field where the author intended to display minutes. When working with `LocalTime`, the month field is unavailable and the formatter will throw an exception because the source type does not provide that field.

### 8.3. Omitting AM/PM When Parsing

The string `01:05` does not specify whether it is morning or afternoon on a 12-hour clock. If the actual data represents 12-hour time, you must either accept an AM/PM marker or have an explicit default rule; it cannot be inferred from the bare string alone.

### 8.4. Confusing 12 AM and 12 PM

`12:00 AM` is `00:00` on a 24-hour clock. `12:00 PM` is `12:00`. Test these two values specifically, along with adjacent times such as `11:59 AM` and `12:01 PM`.

### 8.5. Using Local Time as an Absolute Point in Time

`LocalTime` stores only a time of day. `13:05` does not tell you which date or which time zone; it does not contain enough information to identify an instant. If the data represents an event timestamp, use `Instant` or an offset/zoned date-time type, and choose the formatter with the appropriate zone.

### 8.6. Treating Patterns as Unconstrained Syntax

Pattern letters have specific meanings, and letter case matters. If patterns come from configuration, validate them at application startup; an invalid pattern can throw `IllegalArgumentException`. Text parsing failures typically throw `DateTimeParseException` (a subclass of `DateTimeException`); report invalid input clearly instead of falling back to the current time.

## 9. Quick Reference Conversion Table

The following table helps compare common values when switching formats:

| `LocalTime` | `HH:mm` | `hh:mm a` (Locale.US) |
|---|---|---|
| `00:00` | `00:00` | `12:00 AM` |
| `00:15` | `00:15` | `12:15 AM` |
| `06:30` | `06:30` | `06:30 AM` |
| `11:59` | `11:59` | `11:59 AM` |
| `12:00` | `12:00` | `12:00 PM` |
| `12:45` | `12:45` | `12:45 PM` |
| `13:05` | `13:05` | `01:05 PM` |
| `23:59` | `23:59` | `11:59 PM` |

Presentation format does not alter the `LocalTime` value. The same object can be formatted with multiple formatters without creating another object.

## 10. Self-Check Questions

**Question 1.** Which pattern is used for two-digit 24-hour time?

**Answer:** `HH:mm` or `HH:mm:ss`. `HH` represents hours 00–23.

**Question 2.** Which pattern represents 12-hour time with AM/PM?

**Answer:** For example, `hh:mm a` for zero-padded hours, or `h:mm a` without zero-padding. `a` outputs the locale-specific AM/PM marker.

**Question 3.** In 12-hour time, what 24-hour values do `12:00 AM` and `12:00 PM` correspond to?

**Answer:** `12:00 AM → 00:00`; `12:00 PM → 12:00`.

**Question 4.** Why does `LocalTime.parse("1:05 PM", formatter)` return an object whose `toString()` prints `13:05`?

**Answer:** `LocalTime` stores the hour in a 0–23 field and does not retain the original input text or AM/PM marker. To display it in 12-hour format again, you must format it with a 12-hour formatter.

**Question 5.** What is the difference between `HH` and `hh`?

**Answer:** `HH` uses hours 0–23; `hh` uses hours 1–12 and is typically paired with `a` to distinguish morning from afternoon.

**Question 6.** Why should you pass a `Locale` to `ofPattern`?

**Answer:** The locale determines language-dependent text such as AM/PM. This is important for multilingual UIs and when parsing locale-specific text.

**Question 7.** Should `hh:mm a` be used as the default data-exchange format between systems?

**Answer:** Only when both parties' contract explicitly specifies that format and locale. For machine-to-machine communication, a stable format such as ISO local time / 24-hour format is much less ambiguous.

## 11. Practical Guidelines

- Use `HH:mm:ss` for 24-hour time; use `hh:mm:ss a` or `h:mm a` for 12-hour time with AM/PM.
- Pay attention to letter case: `H` = 0–23, `h` = 1–12, `K` = 0–11, `k` = 1–24, `m` = minute, `M` = month.
- Always test midnight and noon, as the `12 AM/PM` rule is easy to get backwards.
- Parse using a known input format, specify the appropriate locale, and handle `DateTimeParseException` for invalid strings.
- Separate the **time value** from the **display string**: parse into `LocalTime`, keep the typed value, and format it as needed for the UI.
- For real-world events, remember that `LocalTime` has no date or time zone; choose a richer temporal type if you need a unique instant in time.

`DateTimeFormatter` lets applications switch between 12-hour and 24-hour time without changing the underlying time value. Choosing the right pattern and locale, handling 12 AM/PM edge cases properly, and standardizing input/output formats will prevent most time-formatting bugs.
