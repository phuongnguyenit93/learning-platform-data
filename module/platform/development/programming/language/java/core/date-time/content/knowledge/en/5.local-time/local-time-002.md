# LocalTime: Creating a Time with Nanosecond Precision

## 1. What Does `LocalTime` Represent?

`java.time.LocalTime` is an *immutable* date-time type introduced in Java 8+ used to store **a time of day**, consisting of hour, minute, second, and fractional second with a resolution down to **1 nanosecond (1 ns = 10⁻⁹ seconds)**. It contains no date, UTC offset, time zone, or absolute instant.

For example, `09:05:07.123456789` means 9 hours, 5 minutes, 7 seconds, and **123,456,789 nanoseconds** within that second. You can create this value without knowing what date today is or which time zone the server is in.

Points to distinguish right from the start:

- **Representation resolution:** the `LocalTime` type can store values at 1 ns increments.
- **Clock source accuracy:** `LocalTime.now()` is not guaranteed to measure real time accurately to 1 ns. The platform may only provide microsecond/millisecond steps or lower precision.
- **Exchange/storage precision:** string formats, APIs, databases, or drivers may only retain 3 or 6 fractional-second digits, losing nanosecond information.

This lesson focuses on how to **create a known time, accurate down to the nanosecond field**, and then validate, read, convert, format, and manipulate the value. When a date or time zone is needed, you must combine it with the appropriate temporal types.

## 2. Four Components and Valid Ranges

| Component | Range | Getter | Example |
|---|---:|---|---:|
| Hour | 0–23 | `getHour()` | 9 |
| Minute | 0–59 | `getMinute()` | 5 |
| Second | 0–59 | `getSecond()` | 7 |
| Nano of second | 0–999,999,999 | `getNano()` | 123,456,789 |

Built-in special constants:

- `LocalTime.MIN` = `00:00`.
- `LocalTime.MIDNIGHT` = `00:00`.
- `LocalTime.NOON` = `12:00`.
- `LocalTime.MAX` = `23:59:59.999999999`.

`LocalTime` does not accept `24:00`, hour 24, minute 60, second 60, or nano equal to 1,000,000,000. The factory will throw `DateTimeException` if a component is out of range. For dates/times requiring leap seconds or specialized historical records, a dedicated model is needed; do not pass 60 into the second field of `LocalTime`.

### 2.1. Distinguishing Nano, Micro, and Milli

| One unit | Number of nanoseconds |
|---|---:|
| 1 second (s) | 1,000,000,000 |
| 1 millisecond (ms) | 1,000,000 |
| 1 microsecond (µs) | 1,000 |
| 1 nanosecond (ns) | 1 |

Therefore:

~~~java
LocalTime nano123 = LocalTime.of(9, 5, 7, 123);
LocalTime milli123 = LocalTime.of(9, 5, 7, 123_000_000);
LocalTime micro123 = LocalTime.of(9, 5, 7, 123_000);
~~~

The `toString()` results are respectively:

~~~text
09:05:07.000000123
09:05:07.123
09:05:07.000123
~~~

**The last parameter of `of(hour, minute, second, nanoOfSecond)` is always in nanoseconds**, even if the original business source variable stores milliseconds or microseconds. The `_` separator between digits in Java only improves readability and does not change the value.

## 3. Factory `of(...)`: Direct Creation

Common overloads:

~~~java
LocalTime onlyHourMinute = LocalTime.of(9, 5);
LocalTime withSecond = LocalTime.of(9, 5, 7);
LocalTime withNanos = LocalTime.of(9, 5, 7, 123_456_789);
~~~

| Call | Components provided | `toString()` value |
|---|---|---|
| `of(9, 5)` | Hour, minute; second and nano default to 0 | `09:05` |
| `of(9, 5, 7)` | Hour, minute, second; nano defaults to 0 | `09:05:07` |
| `of(9, 5, 7, 123_456_789)` | All four components | `09:05:07.123456789` |

If you want to set 250 milliseconds at 08:15:30, call:

~~~java
LocalTime meeting = LocalTime.of(8, 15, 30, 250_000_000);
// 08:15:30.250
~~~

If an input field records `nanos=1_000_000_000`, that value already equals one second and **cannot** be passed as `nanoOfSecond`. You must normalize the second component in the input logic or use addition on a valid `LocalTime`.

**Error check:** `LocalTime.of(23, 59, 59, 999_999_999)` is valid; `LocalTime.of(23, 59, 59, 1_000_000_000)` throws `DateTimeException`. `LocalTime.of(24, 0)` and `LocalTime.of(12, 0, 60)` are also invalid.

## 4. Creating from Start of Day with `ofSecondOfDay()` and `ofNanoOfDay()`

Sometimes a data source provides a single number: the number of seconds or nanoseconds since `00:00`. `LocalTime` has two corresponding factories:

~~~java
LocalTime fromSeconds = LocalTime.ofSecondOfDay(3_661L);
LocalTime fromNanos = LocalTime.ofNanoOfDay(32_707_123_456_789L);
~~~

- `fromSeconds` = `01:01:01` because 3,661 seconds = 1 hour + 1 minute + 1 second.
- `fromNanos` = `09:05:07.123456789`.

Limits:

| Factory | Minimum value | Maximum value | Unit |
|---|---:|---:|---|
| `ofSecondOfDay(long)` | 0 | 86,399 | seconds |
| `ofNanoOfDay(long)` | 0 | 86,399,999,999,999 | nanoseconds |

A standard day has `24 × 60 × 60 = 86,400` seconds, or `86,400,000,000,000` nanoseconds. The largest valid nanosecond count must be **less than** the total duration of a day; equal to that number is midnight of the next day, which is outside the time range of a single `LocalTime` day.

Two inverse methods:

~~~java
LocalTime time = LocalTime.of(9, 5, 7, 123_456_789);
long nanosFromMidnight = time.toNanoOfDay();
int nanosWithinSecond = time.getNano();
~~~

Values:

~~~text
nanosFromMidnight = 32707123456789
nanosWithinSecond = 123456789
~~~

Formula:

~~~text
secondOfDay = hour * 3600 + minute * 60 + second
             = 9 * 3600 + 5 * 60 + 7 = 32707

nanoOfDay = secondOfDay * 1_000_000_000 + nanoOfSecond
          = 32707 * 1_000_000_000 + 123456789
          = 32707123456789
~~~

**Use `long` when computing total nanoseconds:** the maximum value exceeds the 32-bit `int` limit. `getNano()` returns `int` because it only holds nanoseconds *within a second*; `toNanoOfDay()` returns `long` because it holds nanoseconds *within the entire day*. If reading via `ChronoField.NANO_OF_DAY`, use `getLong(ChronoField.NANO_OF_DAY)`.

An important round-trip operation:

~~~java
LocalTime time = LocalTime.of(9, 5, 7, 123_456_789);
LocalTime restored = LocalTime.ofNanoOfDay(time.toNanoOfDay());
boolean same = restored.equals(time); // true
~~~

Converting from `LocalTime` to total nanoseconds of day and back **does not lose the fractional second**. Conversely, going through `toSecondOfDay()` drops the nanoseconds because the result only contains whole seconds.

### 4.1. Complete Java 17+ Program

Save the code as **`LocalTimeNanoDemo.java`**:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public class LocalTimeNanoDemo {
    public static void main(String[] args) {
        LocalTime time = LocalTime.of(9, 5, 7, 123_456_789);
        long nanoOfDay = time.toNanoOfDay();
        LocalTime restored = LocalTime.ofNanoOfDay(nanoOfDay);

        System.out.println("Time: " + time);
        System.out.println("Nano in second: " + time.getNano());
        System.out.println("Nano of day: " + nanoOfDay);
        System.out.println("Round trip: " + restored.equals(time));
        System.out.println("From seconds: "
                + LocalTime.ofSecondOfDay(3_661));
        System.out.println("Plus one nano: " + time.plusNanos(1));
        System.out.println("Truncated to millis: "
                + time.truncatedTo(ChronoUnit.MILLIS));
        System.out.println("Nine digits: " + time.format(
                DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS")));
    }
}
~~~

Compile and run:

~~~bash
javac LocalTimeNanoDemo.java
java LocalTimeNanoDemo
~~~

Deterministic stdout:

~~~text
Time: 09:05:07.123456789
Nano in second: 123456789
Nano of day: 32707123456789
Round trip: true
From seconds: 01:01:01
Plus one nano: 09:05:07.123456790
Truncated to millis: 09:05:07.123
Nine digits: 09:05:07.123456789
~~~

The commands do not depend on the current clock, machine time zone, or external data. The `LocalTime` values are created directly, making this a good verification test for nanosecond storage and `toNanoOfDay()` conversion.

## 5. `parse()`: Creating a Time from a String with Nanoseconds

`LocalTime.parse(String)` accepts ISO local time formats, for example:

~~~java
LocalTime a = LocalTime.parse("09:05");
LocalTime b = LocalTime.parse("09:05:07");
LocalTime c = LocalTime.parse("09:05:07.1");
LocalTime d = LocalTime.parse("09:05:07.123");
LocalTime e = LocalTime.parse("09:05:07.123456");
LocalTime f = LocalTime.parse("09:05:07.123456789");
~~~

Meaning of the fractional part after the decimal point:

| String | `getNano()` | Explanation |
|---|---:|---|
| `09:05:07` | 0 | No fractional part |
| `09:05:07.1` | 100,000,000 | 0.1 seconds |
| `09:05:07.123` | 123,000,000 | 123 milliseconds |
| `09:05:07.123456` | 123,456,000 | 123,456 microseconds |
| `09:05:07.123456789` | 123,456,789 | Nine nanosecond digits |

**`.1` after the seconds means 0.1 seconds, not 1 ns.** The parser converts that fractional value into nanoseconds. If you want 1 ns, the string is `09:05:07.000000001`.

Invalid values such as `25:05:07`, `09:61:00`, or a fractional second with more than 9 digits typically throw `DateTimeParseException` with `LocalTime`'s ISO formatter.

### 5.1. `toString()` and the Number of Fractional-Second Digits

`LocalTime.toString()` prints as many digits as needed: it may omit seconds if both second and nano are 0, or use groups of 3, 6, or 9 fractional-second digits depending on the value. For example:

~~~java
System.out.println(LocalTime.of(9, 5));                    // 09:05
System.out.println(LocalTime.of(9, 5, 7));                 // 09:05:07
System.out.println(LocalTime.of(9, 5, 7, 123_000_000));   // 09:05:07.123
System.out.println(LocalTime.of(9, 5, 7, 123_400_000));   // 09:05:07.123400
System.out.println(LocalTime.of(9, 5, 7, 123_456_789));   // 09:05:07.123456789
~~~

Therefore, an initial string with `.123000000` may still print back as `.123`; **the nanosecond value is not lost**, only its text representation is shortened.

### 5.2. Fixed Formatting to Nine Digits

When another system requires the exact `HH:mm:ss.SSSSSSSSS` format with **nine digits after the decimal point**, use `DateTimeFormatter`:

~~~java
DateTimeFormatter fullNanos =
        DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS");

LocalTime time = LocalTime.of(9, 5, 7, 123_000_000);
String text = time.format(fullNanos);
// text = "09:05:07.123000000"
~~~

Common pattern letters table:

| Pattern | Meaning |
|---|---|
| `HH` | 24-hour clock (`00..23`) |
| `hh` | 12-hour clock (`01..12`), requires AM/PM context |
| `mm` | Minute |
| `ss` | Second |
| `SSS` | First three digits of fractional second |
| `SSSSSS` | First six digits of fractional second |
| `SSSSSSSSS` | Nine digits of fractional second |

The letter `S` represents **fraction-of-second**; three digits correspond to millisecond level, six digits to microsecond level, and nine digits to nanosecond level. The number of `S` characters determines the formatting width. It does not turn a less precise value into a measurement with better actual accuracy.

To parse ISO strings with an optional fractional second from 0 to 9 digits, `DateTimeFormatter.ISO_LOCAL_TIME` is more suitable than a pattern requiring nine digits. If a custom input format is needed, you can use `DateTimeFormatterBuilder.appendFraction(ChronoField.NANO_OF_SECOND, minWidth, maxWidth, true)` and explicitly declare the accepted width.

### 5.3. Standalone Parse/Format Example

Save as **`ParseNanoDemo.java`**:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public class ParseNanoDemo {
    public static void main(String[] args) {
        LocalTime a = LocalTime.parse("09:05:07.123456789");
        LocalTime b = LocalTime.parse("09:05:07.123");
        DateTimeFormatter nine =
                DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS");

        System.out.println("Nano of a: " + a.getNano());
        System.out.println("Nano of b: " + b.getNano());
        System.out.println("Fixed width: " + b.format(nine));

        try {
            LocalTime.parse("25:05:07.123456789");
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid hour rejected");
        }
    }
}
~~~

~~~bash
javac ParseNanoDemo.java
java ParseNanoDemo
~~~

Stdout:

~~~text
Nano of a: 123456789
Nano of b: 123000000
Fixed width: 09:05:07.123000000
Invalid hour rejected
~~~

Choose a formatter compatible with the data format at API, CSV, or database boundaries. Do not arbitrarily truncate strings to fix an invalid time and continue with corrupted data.

## 6. Manipulating Nanoseconds

`LocalTime` is immutable: `plusNanos`, `minusNanos`, `withNano`, and `truncatedTo` always return a resulting `LocalTime`; the original object is not modified.

~~~java
LocalTime source = LocalTime.of(9, 5, 7, 123_456_789);
LocalTime next = source.plusNanos(1);
LocalTime previous = source.minusNanos(1);
LocalTime withZeroNanos = source.withNano(0);
LocalTime millis = source.truncatedTo(ChronoUnit.MILLIS);
LocalTime micros = source.truncatedTo(ChronoUnit.MICROS);
~~~

Corresponding results:

| Expression | Result |
|---|---|
| `source` | `09:05:07.123456789` |
| `next` | `09:05:07.123456790` |
| `previous` | `09:05:07.123456788` |
| `withZeroNanos` | `09:05:07` |
| `millis` | `09:05:07.123` |
| `micros` | `09:05:07.123456` |

**Truncation differs from rounding:** `truncatedTo(ChronoUnit.MILLIS)` drops everything smaller than a millisecond. For `123_999_999` ns, truncating to millis yields `123_000_000` ns, **not** `124_000_000` ns. If the system requires rounding, you must define a rounding rule and handle second/day overflow separately.

Units supported by `truncatedTo` must have a duration that divides evenly into a standard day. Nanos, micros, millis, seconds, minutes, and hours meet this condition. Do not assume every `TemporalUnit` is valid.

### 6.1. Crossing Midnight: Value Wrap-Around

~~~java
LocalTime last = LocalTime.MAX;
LocalTime nextDayClockTime = last.plusNanos(1);

System.out.println(last);
System.out.println(nextDayClockTime);
~~~

Stdout:

~~~text
23:59:59.999999999
00:00
~~~

This is **24-hour clock wrap-around**. `LocalTime` does not record that it has rolled over into the next day. To preserve the date as well:

~~~java
LocalDateTime lastMoment = LocalDateTime.of(
        2024, 2, 29, 23, 59, 59, 999_999_999);
LocalDateTime nextDay = lastMoment.plusNanos(1);
// 2024-03-01T00:00
~~~

If time-zone rules also matter, use `ZonedDateTime`/`Instant` as appropriate for the business logic; a standalone `LocalTime` is insufficient to determine whether an event occurred before or after another event on a different day.

### 6.2. Calculating the Distance Between Two Times

~~~java
LocalTime start = LocalTime.of(23, 59, 59);
LocalTime end = LocalTime.of(0, 0, 1);
Duration diff = Duration.between(start, end);
~~~

`diff` equals `PT-23H-59M-58S`, rather than automatically knowing the user meant **two seconds across midnight**. If a work shift runs from 23:59:59 yesterday to 00:00:01 today, you must add the **date** or a rule such as "an earlier end time means the next day," and then compute on values that include the date/instant.

`ChronoUnit.NANOS.between(a, b)` also compares the distance between two times within `LocalTime`'s representation domain; it cannot infer date history.

## 7. `now()`, `Clock`, and Practical Precision Limits

`LocalTime.now()` creates the current time using the JVM's default clock and time zone; `LocalTime.now(ZoneId)` uses the specified zone; `LocalTime.now(Clock)` uses the provided clock.

~~~java
LocalTime system = LocalTime.now();
LocalTime inVietnam =
        LocalTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Both results depend on **the time of execution**, so a fixed stdout cannot be published. On a machine using UTC, `LocalTime.now()` does not necessarily equal Vietnam time. If processing business logic for a specific region, specify `ZoneId` explicitly.

For testing, create `Clock.fixed(instant, zone)`:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2024-02-29T23:30:00.987654321Z"),
        ZoneOffset.UTC);
LocalTime value = LocalTime.now(fixed);
// 23:30:00.987654321
~~~

Save a complete example as **`ClockNanoDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class ClockNanoDemo {
    public static void main(String[] args) {
        Instant point =
                Instant.parse("2024-02-29T23:30:00.987654321Z");
        Clock utc = Clock.fixed(point, ZoneOffset.UTC);
        Clock hcm = Clock.fixed(
                point, ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("UTC: " + LocalTime.now(utc));
        System.out.println("HCM: " + LocalTime.now(hcm));
        System.out.println("Instant: " + Instant.now(utc));
    }
}
~~~

~~~bash
javac ClockNanoDemo.java
java ClockNanoDemo
~~~

Stdout with `Asia/Ho_Chi_Minh` rules on the example date:

~~~text
UTC: 23:30:00.987654321
HCM: 06:30:00.987654321
Instant: 2024-02-29T23:30:00.987654321Z
~~~

In Vietnam, this instant falls on **2024-03-01**, but `LocalTime` only holds the time part `06:30:00.987654321`. To get both date and time, use `LocalDateTime.now(hcm)` or `ZonedDateTime.now(hcm)`.

**Do not confuse with `System.nanoTime()`:** it provides a relative counter for measuring elapsed time, not nanoseconds since the start of the day and not an epoch timestamp. Do not pass `System.nanoTime()` directly into `LocalTime.ofNanoOfDay`.

Furthermore, `now().getNano()` may have 9 digits, but that does not prove the system clock is actually accurate to 1 ns. Display resolution and measurement error are two different factors; when strict scientific measurement or regulated transactions are required, the clock source and measurement characteristics must be determined separately.

## 8. Comparison and Preserving Precision Across Systems

`LocalTime` compares hour, minute, second, and nano fields in order, so it can distinguish two times that are only 1 ns apart:

~~~java
LocalTime a = LocalTime.of(9, 5, 7, 123_456_788);
LocalTime b = LocalTime.of(9, 5, 7, 123_456_789);
boolean before = a.isBefore(b);  // true
boolean after = b.isAfter(a);    // true
~~~

`equals()` compares values, not the original character strings:

~~~java
LocalTime.parse("09:05:07.123").equals(
        LocalTime.parse("09:05:07.123000000")); // true
~~~

The two strings above represent the same **123,000,000 ns** within the second. However, comparing two `LocalTime` instances only compares **order within a day**, not the absolute order of two events if they occurred on different days.

When exchanging or storing data:

- **Data accurate only to seconds:** format as `HH:mm:ss` and document that fractional seconds are absent.
- **Millisecond data:** three fractional-second digits (`SSS`); converting from nanoseconds may lose the last six digits.
- **Microsecond data:** six digits (`SSSSSS`); may lose the last three nanosecond digits.
- **Nanosecond data:** requires a formatter or storage type that retains nine digits; test actual round-trip behavior.
- **SQL `TIME` column:** fractional-second storage capability depends on the DBMS, column precision, JDBC driver, and mapping. Do not assume every database's `TIME` type stores all nine digits.

When receiving a source in milliseconds/microseconds, convert intentionally by multiplying by the unit factor before calling `LocalTime.of`. Nanosecond data that has already been rounded or truncated by the source cannot be recovered.

## 9. Common Mistakes

1. **Passing 123 as 123 milliseconds:** the `nanoOfSecond=123` parameter is only 123 ns. Use `123_000_000` for 123 ms.
2. **Computing total nanoseconds with `int`:** the number of nanoseconds in a day exceeds the `int` limit; use `long` right in the multiplication.
3. **Treating `1_000_000_000` as a valid nanosecond in a second:** the limit is `999_999_999`. One billion nanoseconds equals one full second and must be handled as second addition.
4. **Assuming `toString()` always has all nine digits:** Java may omit unnecessary trailing zeros. Use a formatter when fixed width is required.
5. **Treating `.1` in a string as one nanosecond:** it is one-tenth of a second, i.e., 100,000,000 ns.
6. **Confusing `truncatedTo` with rounding:** truncation discards anything smaller than the selected resolution.
7. **Forgetting wrap-around at 00:00:** adding one nanosecond to `LocalTime.MAX` returns `00:00` and does not track the incremented day count.
8. **Calling `Duration.between` across midnight without knowing the date:** the result can be negative or not match the intended business duration.
9. **Assuming 9 digits means 1 ns physical accuracy:** you must inspect the actual clock and measurement source.
10. **Passing `System.nanoTime()` into `ofNanoOfDay`:** the two values have completely different reference points and semantics.
11. **Using `LocalTime` as the sole timestamp:** an event timestamp needs at least date information and usually an offset/zone or `Instant`.
12. **Ignoring database/driver precision:** you must write and read back to verify whether all 9 digits are preserved.

## 10. Self-Check

**Question 1.** What does `LocalTime.of(12, 0, 0, 5)` print?  
**Answer:** `12:00:00.000000005`, because the last parameter is **5 nanoseconds**, not 5 milliseconds.

**Question 2.** How do you create `08:15:30.250` using `of`?  
**Answer:** `LocalTime.of(8, 15, 30, 250_000_000)`.

**Question 3.** What does `LocalTime.parse("10:20:30.123").getNano()` return?  
**Answer:** `123_000_000`.

**Question 4.** What value does `LocalTime.MAX.plusNanos(1)` produce?  
**Answer:** `00:00`. The time wraps around and does not store the date.

**Question 5.** What should you use to store a `LocalTime` value with full nanosecond precision as an integer?  
**Answer:** `toNanoOfDay()`, which returns a `long`; reconstruct it with `LocalTime.ofNanoOfDay(long)`.

**Question 6.** Does `truncatedTo(ChronoUnit.MILLIS)` round `123_999_999` ns up to 124 ms?  
**Answer:** No, it **truncates** down to `123_000_000` ns.

**Question 7.** Why does `LocalTime.now().getNano()` not prove a machine has a 1 ns accurate clock?  
**Answer:** Because the data type's ability to store 9 digits is different from the clock source's resolution and error. Java can represent a value down to the nanosecond even when hardware cannot measure at that precision.

**Question 8.** When you need both date and time to track a shift crossing midnight, which type is better than a standalone `LocalTime`?  
**Answer:** `LocalDateTime` if only local date/time is needed, or `ZonedDateTime`/`Instant` if time-zone rules or absolute elapsed time are required.

## 11. Key Takeaways

- `LocalTime.of(hour, minute, second, nanoOfSecond)` creates a **known time with nanosecond resolution**; valid nano values range from 0 to 999,999,999.
- `ofNanoOfDay(long)` and `toNanoOfDay()` allow lossless nanosecond conversion within the same day, using `long` to hold the large value.
- `parse()` and `DateTimeFormatter` define the meaning of fractional seconds and display width; `toString()` may shorten output without losing value precision.
- `plusNanos()`, `withNano()`, and `truncatedTo()` operate on immutable values; time wraps around past 24 hours **without carrying a date**.
- The ability to **represent 1 ns** does not mean a clock or database **measures/stores 1 ns accurately**. Verify each data conversion boundary when nanosecond preservation is required.
