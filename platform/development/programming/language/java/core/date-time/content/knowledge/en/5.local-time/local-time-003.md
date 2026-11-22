# Reading Hours, Minutes, Seconds, and Fractional Seconds with LocalTime

In Java, `java.time.LocalTime` represents a **time of day** on a 24-hour clock, without a date, time zone, or UTC offset. Given a value such as `09:07:05.123456789`, you can read the **hour** (`09`), **minute** (`07`), **second** (`05`), and **fractional second** (`123456789` nanoseconds) separately. Understanding the fractional part accurately is especially useful when working with logs, protocol data, time forms, and sub-second time comparisons.

## 1. What Does LocalTime Store?

A `LocalTime` has four key components:

| Component | Getter | Value Range | In `09:07:05.123456789` |
| --- | --- | --- | --- |
| Hour | `getHour()` | 0–23 | `9` |
| Minute | `getMinute()` | 0–59 | `7` |
| Second | `getSecond()` | 0–59 | `5` |
| Nanosecond within the current second | `getNano()` | 0–999,999,999 | `123456789` |

**Note:** `getNano()` does not return the total number of nanoseconds since the start of the day. It is the **fractional part of a single second**, ranging from 0 to 999,999,999. For example, for `09:07:05.123456789`, it returns `123456789` rather than `32825123456789`. To get the total nanoseconds since `00:00`, use `toNanoOfDay()`; to get the total seconds since the start of the day, use `toSecondOfDay()`.

The data resolution of `LocalTime` is **nanosecond (10⁻⁹ seconds)**. This describes its representational capability; it **does not guarantee** that the hardware clock or a value received from an external source is actually accurate to one nanosecond.

This type only describes a time on a clock. It does not distinguish `09:00` today from `09:00` tomorrow, does not indicate whether `09:00` is in Hanoi or London, and does not convert directly to an `Instant`. When you need to include a date, use `LocalDateTime`; when you need a time zone, use `ZonedDateTime` or `OffsetTime` depending on the requirement.

## 2. Creating a Time Value and Reading Each Component

Create a `LocalTime` using `of`:

~~~java
LocalTime time = LocalTime.of(9, 7, 5, 123_456_789);
int hour = time.getHour();     // 9
int minute = time.getMinute(); // 7
int second = time.getSecond(); // 5
int nano = time.getNano();     // 123456789
~~~

Underscores in Java integer literals only make them easier for humans to read, so `123_456_789` is the same as `123456789`. The `nanoOfSecond` value must be in the range 0–999,999,999.

Common overloads and constants:

~~~java
LocalTime.of(9, 7);                   // 09:07
LocalTime.of(9, 7, 5);                // 09:07:05
LocalTime.of(9, 7, 5, 123_000_000);   // 09:07:05.123
LocalTime.MIDNIGHT;                   // 00:00
LocalTime.NOON;                       // 12:00
LocalTime.MAX;                        // 23:59:59.999999999
~~~

If seconds or nanoseconds are not passed, Java uses **0** for the omitted components. For instance, `LocalTime.of(9, 7).getSecond()` equals `0`. However, the default `toString()` output may omit zero components; do not confuse "not printed" with "not present in the object."

`LocalTime` validates value ranges and throws an error if any are invalid. `LocalTime.of(24, 0)`, `LocalTime.of(9, 60)`, and `LocalTime.of(9, 7, 60)` all throw `DateTimeException`. It has no representation for `24:00` or a "60th second" to model a leap second. A day on a `LocalTime` clock runs from `00:00` to `23:59:59.999999999`.

## 3. Fractional Seconds: Nano, Micro, and Milli

A second can be divided into the following units:

| Unit | Conversion | Value for `.123456789` |
| --- | --- | --- |
| Second | 1 second | Whole part is `5`, fractional part is `0.123456789` |
| Millisecond (ms) | 1 ms = 1,000,000 ns | `123` whole ms |
| Microsecond (µs) | 1 µs = 1,000 ns | `123456` whole µs |
| Nanosecond (ns) | 1 ns = 10⁻⁹ seconds | `123456789` ns |

Reading methods:

~~~java
LocalTime time = LocalTime.parse("09:07:05.123456789");

int nano = time.getNano();                           // 123456789
int milli = time.get(ChronoField.MILLI_OF_SECOND);   // 123
int micro = time.get(ChronoField.MICRO_OF_SECOND);   // 123456
~~~

The `MILLI_OF_SECOND` and `MICRO_OF_SECOND` getters **extract the corresponding integer part** without rounding up. For example, `123456789` ns corresponds to `123.456789` ms; the `MILLI_OF_SECOND` field returns `123`.

Compute manually from `getNano()` if needed:

~~~java
int millis = time.getNano() / 1_000_000; // 123
int micros = time.getNano() / 1_000;     // 123456
int nanoRemainderAfterMillis =
        time.getNano() % 1_000_000;       // 456789
~~~

Do not confuse `getNano()` with the seconds value `getSecond()`, or `ChronoField.NANO_OF_SECOND` with `ChronoField.NANO_OF_DAY`. When reading the total nanoseconds of the day, `LocalTime.toNanoOfDay()` returns `long` because the value can exceed the `int` range.

## 4. Complete Java 17+ Example and Output

Save the following program in `LocalTimePartsDemo.java`:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class LocalTimePartsDemo {
    public static void main(String[] args) {
        LocalTime time = LocalTime.of(9, 7, 5, 123_456_789);

        System.out.println("time=" + time);
        System.out.println("hour=" + time.getHour());
        System.out.println("minute=" + time.getMinute());
        System.out.println("second=" + time.getSecond());
        System.out.println("nano=" + time.getNano());

        System.out.println("milli="
                + time.get(ChronoField.MILLI_OF_SECOND));
        System.out.println("micro="
                + time.get(ChronoField.MICRO_OF_SECOND));

        LocalTime onlyHourMinute = LocalTime.parse("09:07");
        System.out.println("onlyMinute=" + onlyHourMinute);
        System.out.println("onlyMinuteSecond="
                + onlyHourMinute.getSecond());

        System.out.println("frac3="
                + LocalTime.parse("09:07:05.123").getNano());
        System.out.println("frac2="
                + LocalTime.parse("09:07:05.12").getNano());

        DateTimeFormatter threeDigits =
                DateTimeFormatter.ofPattern(
                        "HH:mm:ss.SSS", Locale.ROOT);
        DateTimeFormatter nineDigits =
                DateTimeFormatter.ofPattern(
                        "HH:mm:ss.SSSSSSSSS", Locale.ROOT);

        System.out.println("format3=" + time.format(threeDigits));
        System.out.println("format9=" + time.format(nineDigits));
        System.out.println("rollover=" + LocalTime.MAX.plusNanos(1));
        System.out.println("dayNano=" + time.toNanoOfDay());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac LocalTimePartsDemo.java
java LocalTimePartsDemo
~~~

Output:

~~~text
time=09:07:05.123456789
hour=9
minute=7
second=5
nano=123456789
milli=123
micro=123456
onlyMinute=09:07
onlyMinuteSecond=0
frac3=123000000
frac2=120000000
format3=09:07:05.123
format9=09:07:05.123456789
rollover=00:00
dayNano=32825123456789
~~~

As shown, `getNano()` returns the nanosecond value within the second; `09:07:05.123` is normalized to `123000000` ns and `09:07:05.12` to `120000000` ns. The `format` methods only control the **display string** and do not modify the `time` object. The `rollover` line is a reminder that `LocalTime` holds no date to record crossing midnight.

## 5. Parsing Time Strings: Missing Seconds, Fractional Parts, Precision

`LocalTime.parse(text)` uses `DateTimeFormatter.ISO_LOCAL_TIME` by default. Examples:

| String | `getHour()` | `getMinute()` | `getSecond()` | `getNano()` |
| --- | ---: | ---: | ---: | ---: |
| `09:07` | 9 | 7 | 0 | 0 |
| `09:07:05` | 9 | 7 | 5 | 0 |
| `09:07:05.1` | 9 | 7 | 5 | 100000000 |
| `09:07:05.12` | 9 | 7 | 5 | 120000000 |
| `09:07:05.123` | 9 | 7 | 5 | 123000000 |
| `09:07:05.123456` | 9 | 7 | 5 | 123456000 |
| `09:07:05.123456789` | 9 | 7 | 5 | 123456789 |

**Explanation:** The dot starts the decimal fractional part of a **second**. `.1` means **one-tenth of a second** = 100 million ns; `.12` means 120 million ns. The digits after the dot are **not** a raw "nanosecond count" written directly. Java normalizes the fractional part into a 9-digit nanosecond integer.

`LocalTime.parse("09:07")` is valid and automatically sets seconds and nanoseconds to 0. Conversely, strings like `9:7` or `09:07:05.1234567890` do not match the default ISO format; having more than 9 fractional digits or out-of-range components throws `DateTimeParseException`. For user-supplied input, validate the format and handle exceptions at the system boundary.

**Note on output strings:** `LocalTime.toString()` may omit zero seconds and display the fractional part using 3, 6, or 9 digits as needed depending on precision. Therefore, parsing and then calling `toString()` is not guaranteed to return the **exact same number of digits** or the original input representation, even though the time value is equivalent. If an API contract requires a specific number of digits, specify a `DateTimeFormatter`.

## 6. Fixed Formatting for Hours, Minutes, Seconds, and Fractional Parts

`DateTimeFormatter` supports patterns:

| Symbol | Meaning | Example |
| --- | --- | --- |
| `HH` | Hour 00–23, always two digits | `09` |
| `mm` | Minute, always two digits | `07` |
| `ss` | Second, always two digits | `05` |
| `S` | One fractional-second digit | `1` |
| `SSS` | Three fractional digits (milliseconds) | `123` |
| `SSSSSS` | Six fractional digits (microseconds) | `123456` |
| `SSSSSSSSS` | Nine fractional digits (nanoseconds) | `123456789` |
| `hh` and `a` | Hour 01–12 and locale-specific AM/PM marker | `09 AM` |

Example:

~~~java
LocalTime time = LocalTime.of(9, 7, 5, 123_456_789);

String milliPrecision = time.format(
        DateTimeFormatter.ofPattern("HH:mm:ss.SSS")); // 09:07:05.123

String nanoPrecision = time.format(
        DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS"));
// 09:07:05.123456789
~~~

Uppercase `S` represents fractional seconds; lowercase `s` represents whole seconds. Lowercase `m` is **minute**; uppercase `M` is **month** in date formatters. Confusing `MM` with `mm` is a very common mistake.

The `SSS` pattern only prints the first three digits of the fractional part; it **does not automatically round** the value to milliseconds. For `.123456789`, the result is `.123`, not `.124`. If business logic requires rounding according to a specific rule, perform the rounding/calculation separately and also handle the possibility of rolling over to the next second or day.

If you want to **parse back** a string generated by a specific pattern, use the same formatter when parsing:

~~~java
DateTimeFormatter fixedMillis =
        DateTimeFormatter.ofPattern("HH:mm:ss.SSS");
LocalTime parsed = LocalTime.parse("09:07:05.123", fixedMillis);
~~~

A pattern with exactly three `S`s typically requires three fractional digits; if the data has a variable number of digits, `ISO_LOCAL_TIME` is more convenient when the string is in ISO format.

## 7. Reading from ChronoField and Unit Conversions

In addition to direct getters, `LocalTime` supports `ChronoField`:

~~~java
LocalTime time = LocalTime.of(9, 7, 5, 123_456_789);

int hour = time.get(ChronoField.HOUR_OF_DAY);         // 9
int minute = time.get(ChronoField.MINUTE_OF_HOUR);    // 7
int second = time.get(ChronoField.SECOND_OF_MINUTE);  // 5
int nano = time.get(ChronoField.NANO_OF_SECOND);      // 123456789
long totalNanos = time.toNanoOfDay();                // 32825123456789
int totalSeconds = time.toSecondOfDay();             // 32825
~~~

The methods `getHour()`, `getMinute()`, `getSecond()`, and `getNano()` are usually more readable when you already know the data is a `LocalTime`. Use `ChronoField` when writing generic logic based on `TemporalAccessor` fields.

Do not use `get(ChronoField.NANO_OF_DAY)` for values that exceed the `int` range; if you need this field, use `getLong(ChronoField.NANO_OF_DAY)` or the convenient `toNanoOfDay()`.

Addition and subtraction methods such as `plusHours`, `plusMinutes`, `plusSeconds`, and `plusNanos` return a new object without mutating the original `LocalTime`. They **wrap around within a 24-hour day**: `LocalTime.MAX.plusNanos(1)` becomes `00:00`. Because `LocalTime` has no date, the information that it "crossed into the next day" is lost if you only keep this type.

When comparing two times within the same calendar day, use `isBefore` or `isAfter`. When calculating a time span, `Duration.between(start, end)` does not automatically infer that `end` belongs to the next day. For example, 23:59 to 00:01 can yield a negative `Duration` if you only use two `LocalTime` values; attach the appropriate date when business logic spans midnight.

## 8. System Time and the Effect of Time Zone When Fetching the Value

`LocalTime.now()` gets the current time in the system's default time zone. `LocalTime.now(ZoneId.of("Asia/Ho_Chi_Minh"))` gets the time in the Vietnam time zone. **The resulting `LocalTime` object does not store the zone**, even though the zone was used to compute the time.

Some applications need the display time according to local working schedules:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalTime currentBusinessTime = LocalTime.now(businessZone);
~~~

The snippet above is used inside a method with `java.time` imported; the value changes depending on when it runs, so there is no fixed stdout. When writing unit tests for time logic, use a fixed `Clock` via `LocalTime.now(clock)` to avoid flaky test failures.

A display time of `09:00` does not by itself indicate an absolute point in time. To construct a specific instant from a business hour, you need to add a **date** and a **time zone**:

~~~java
LocalDate date = LocalDate.of(2025, 4, 9);
LocalTime time = LocalTime.of(9, 0);
ZonedDateTime meeting =
        ZonedDateTime.of(date, time,
                ZoneId.of("Asia/Ho_Chi_Minh"));
Instant meetingInstant = meeting.toInstant();
~~~

This is an illustrative snippet inside a method with the corresponding imports. In zones with DST, a local time can **not exist** or be **repeated** on a transition day. Therefore, you cannot rely on `LocalTime` alone to determine global appointment times.

## 9. Common Mistakes

| Mistake | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| Reading `getNano()` as milliseconds | Nano and milli differ by a factor of one million | Use `get(ChronoField.MILLI_OF_SECOND)` or divide by 1,000,000 |
| Assuming `.1` equals one nanosecond | It is one-tenth of a second | `.1` = 100,000,000 ns |
| Thinking `09:07` has no second field | `LocalTime` stores second as 0; `toString()` may hide it | `getSecond()` still returns 0 |
| Appending `Z` to a `LocalTime` string to make it UTC | Missing date and zone/offset rules | Add date + zone, then convert to an instant when needed |
| Expecting `plusNanos(1)` on `LocalTime.MAX` to indicate tomorrow | `LocalTime` has no date and wraps around | Use `LocalDateTime`/`ZonedDateTime` if a date is also needed |
| Confusing `mm` with month | `mm` is minute, `MM` is month | Write the pattern appropriate to the context |
| Thinking `SSS` rounds automatically | The formatter prints the leading digits of the fractional value | Handle rounding separately if required |
| Treating nanosecond resolution as clock accuracy | The data source may only be accurate to milli/microseconds | Distinguish between **resolution** and **accuracy** |
| Comparing two `LocalTime` values to infer which event happened first across two days | No date information is present | Store the date or an instant as well |

## 10. Self-Check

**Question 1.** What does `LocalTime.parse("08:15:30.25").getNano()` return?

**Answer:** `250000000`, because `.25` seconds equals 250,000,000 nanoseconds, or 250 ms.

**Question 2.** From `LocalTime.of(15, 20)`, what are `getSecond()` and `getNano()`?

**Answer:** Both are `0`. Those two fields are not specified in the `of` call, so they default to 0.

**Question 3.** What does `LocalTime.of(23, 59, 59, 999_999_999).plusNanos(1)` produce, and does the date increment?

**Answer:** `00:00`; no date is stored in `LocalTime` to increment. If you need to track the next day, use a type that includes a date.

**Question 4.** In `09:07:05.123456789`, how many milliseconds are in the fractional part, and what is `getNano()`?

**Answer:** `get(ChronoField.MILLI_OF_SECOND)` is `123`; `getNano()` is `123456789`.

**Question 5.** For an API that requires a time string to always include seconds and exactly three millisecond digits, what should you do?

**Answer:** Use the `HH:mm:ss.SSS` formatter to produce `09:07:05.123`. Do not rely on `LocalTime.toString()` because the default output may omit zero seconds or have a varying number of fractional digits.

**Takeaway:** `LocalTime` answers **"what hour, minute, second, and nanosecond of the day is it?"**. `getNano()` always measures the fractional part **within a single second**, with no date or zone information. Choose the right unit and formatter when passing data between Java, APIs, and the user interface.