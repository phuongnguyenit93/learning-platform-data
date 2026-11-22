# Reading Data with get...() and Checking Conditions with is...() in java.time

When working with the Java Date-Time API (`java.time`), we typically have two needs: **retrieving information inside a date-time object** and **checking a condition about a date or time**. Many methods are named after two easily recognizable families:

- `get...()`: returns a property or component, such as year, month, hour, nanoseconds, or UTC offset.
- `is...()`: typically returns a `boolean`, used to answer a true/false question, such as "is this a leap year?", "is this date before that date?", or "does this date-time type support the queried field?".

This is a **common naming convention**, not a rule that applies to every class. Each type in `java.time` models a different kind of data, so a method may exist in one class but not in another. For example, `LocalDate` knows the date but has no time; `Instant` describes a point on the timeline but does not carry a time zone of its own to provide a "local hour".

## 1. Reading the Right Data Type and Right Component

### Common Types in `java.time`

| Type | Representation | Example Read Methods |
|---|---|---|
| `LocalDate` | Date in the ISO calendar, without time or time zone | `getYear()`, `getMonth()`, `getDayOfMonth()` |
| `LocalTime` | Time of day, without date or time zone | `getHour()`, `getMinute()`, `getSecond()`, `getNano()` |
| `LocalDateTime` | Local date and time, without a specified time zone | Date and time getters |
| `OffsetDateTime` | Date and time with a fixed offset from UTC | `getOffset()` and date/time getters |
| `ZonedDateTime` | Date and time with a time-zone region and offset rules | `getZone()`, `getOffset()`, date/time getters |
| `Instant` | A point in time on the timeline | `getEpochSecond()`, `getNano()` |
| `YearMonth` | Year and month | `getYear()`, `getMonth()` |
| `MonthDay` | Month and day of month | `getMonth()`, `getDayOfMonth()` |

Example creating three objects:

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(14, 5, 6, 123_000_000);
LocalDateTime dateTime = LocalDateTime.of(date, time);
~~~

`LocalDate.of(...)` takes a year, a numeric month, and a day; `LocalTime.of(...)` takes hour, minute, second, and nanosecond within the second. An object is created only when the input values are valid: `LocalDate.of(2023, 2, 29)` will throw a `DateTimeException` because 2023 does not have February 29.

### Reading Date Components with `LocalDate`

| Method | Value for `2024-02-29` | Meaning |
|---|---|---|
| `getYear()` | `2024` | Year |
| `getMonth()` | `Month.FEBRUARY` | `Month` enum |
| `getMonthValue()` | `2` | Numeric month, 1–12 |
| `getDayOfMonth()` | `29` | Day of month |
| `getDayOfWeek()` | `DayOfWeek.THURSDAY` | Day-of-week enum |
| `getDayOfYear()` | `60` | The 60th day of the leap year 2024 |

It is important to distinguish `getMonth()` from `getMonthValue()`: the former returns an **enum** to make code more expressive, while the latter returns an **integer** for data output or calculation. Similarly, `getDayOfWeek()` returns `DayOfWeek`, not a localized text string or a number directly.

~~~java
Month month = date.getMonth(); // FEBRUARY
int monthNumber = month.getValue(); // 2
DayOfWeek dayOfWeek = date.getDayOfWeek(); // THURSDAY
int isoDayNumber = dayOfWeek.getValue(); // 4
~~~

According to ISO `DayOfWeek.getValue()`, **Monday = 1** and **Sunday = 7**. Do not assume 0–6 indexing or Sunday-first 1–7 indexing from other libraries. To **display localized names**, use formatting/locale APIs; the English enum names are machine-readable values.

### Reading Time Components with `LocalTime`

| Method | Value from `14:05:06.123` | Range |
|---|---:|---|
| `getHour()` | `14` | 0–23 |
| `getMinute()` | `5` | 0–59 |
| `getSecond()` | `6` | 0–59 |
| `getNano()` | `123_000_000` | 0–999,999,999 |

`getNano()` is the number of **nanoseconds within the current second**, not total nanoseconds since the epoch. `123_000_000` ns equals `123` milliseconds. `LocalDateTime` has both date and time getters, but it **does not represent a unique UTC instant** without an attached offset or time zone.

### Time Zones and Timestamps

~~~java
Instant instant = Instant.parse("2024-02-29T12:00:00Z");
long epochSeconds = instant.getEpochSecond(); // 1709208000
int nanoOfSecond = instant.getNano(); // 0

ZonedDateTime inHcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
int hour = inHcm.getHour(); // 19
ZoneId zone = inHcm.getZone(); // Asia/Ho_Chi_Minh
ZoneOffset offset = inHcm.getOffset(); // +07:00
~~~

One `Instant` and multiple `ZonedDateTime` objects can refer to the **same point in time**, yet have different local date/hour getters. `getZone()` retrieves the time-zone region ID, while `getOffset()` retrieves the UTC offset **in effect at that instant**. Offsets can change historically or for daylight saving time in regions that apply such rules.

## 2. Checking Conditions with `is...()`

### Comparing Dates or Instants

| Method | Question Answered | Notes |
|---|---|---|
| `a.isBefore(b)` | Is `a` earlier than `b`? | `false` if equal |
| `a.isAfter(b)` | Is `a` later than `b`? | `false` if equal |
| `a.isEqual(b)` | Does `a` represent the same date/instant per the type's contract? | Available on some types; see `ZonedDateTime`/`LocalDate` specifically |
| `a.equals(b)` | Are the two objects equal per the class definition? | May consider more properties than just the actual instant |

~~~java
LocalDate examDate = LocalDate.of(2024, 2, 29);
LocalDate deadline = LocalDate.of(2024, 3, 1);

boolean early = examDate.isBefore(deadline); // true
boolean late = examDate.isAfter(deadline); // false
boolean sameDay = examDate.isEqual(deadline); // false
~~~

**Key takeaway:** `isBefore`/`isAfter` are always **strict** comparisons: when equal, both return `false`. When the requirement is "on or before the deadline", you can write `!date.isAfter(deadline)` if `date` and `deadline` are appropriate values to compare.

For `LocalDate`, comparison is by ISO calendar date; for `LocalTime`, by time of day; for `LocalDateTime`, by **local** date and time. `LocalDateTime` lacks time-zone context, so it is insufficient for comparing **global points in time** between two locations. For `Instant`, `OffsetDateTime`, and `ZonedDateTime`, instant comparison is based on the timeline.

**`isEqual(...)` and `equals(...)` can differ.** Two `ZonedDateTime` objects in different time zones can represent the same `Instant`: `isEqual` returns `true`, whereas `equals` returns `false` because the two objects carry different local date-time/zone information. When business logic asks "did they happen at the same time?", you can convert both to `Instant` or use `isEqual` on types that support it.

### Checking Leap Years and Valid Dates

~~~java
LocalDate leapDate = LocalDate.of(2024, 2, 29);
boolean leap = leapDate.isLeapYear(); // true

boolean in2023 = MonthDay.of(2, 29).isValidYear(2023); // false
boolean in2024 = YearMonth.of(2024, 2).isValidDay(29); // true
~~~

- `LocalDate.isLeapYear()` indicates whether the year of that date is a leap year in the proleptic ISO calendar.
- `Year.isLeap(year)` checks for a leap year statically if you only have a year.
- `MonthDay.isValidYear(year)` checks whether a month/day is valid for the given year (very useful for February 29).
- `YearMonth.isValidDay(day)` checks whether a day number exists in that month and year.
- `YearMonth.lengthOfMonth()` and `LocalDate.lengthOfMonth()` return the number of days in the month, not a boolean.

Under ISO rules, a leap year is typically divisible by 4, except years divisible by 100 unless also divisible by 400; the ISO calendar APIs apply the proleptic Gregorian rules even to very distant years. For historical data, actual local calendar rules may differ.

If the input consists of separate day/month/year values, **do not construct a `LocalDate` from unvalidated data hoping `isValidDay` will catch it**. `LocalDate.of(...)` may throw an exception immediately during construction; you can use `YearMonth.isValidDay` beforehand, or handle `DateTimeException` at the input boundary.

### Checking Temporal Field Support

Sometimes an object is only known as a `TemporalAccessor`, and we need to verify whether it has the field we want to read:

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);
boolean daySupported = date.isSupported(ChronoField.DAY_OF_MONTH); // true
boolean hourSupported = date.isSupported(ChronoField.HOUR_OF_DAY); // false
~~~

`isSupported(TemporalField)` asks **whether this data type supports reading that field**. It does not ask "is this date valid?" and does not validate user-entered content.

For `LocalDate`, `YEAR` and `DAY_OF_MONTH` are supported, whereas `HOUR_OF_DAY` is not. For `Instant`, `INSTANT_SECONDS` is supported. Calling a getter for an unsupported field typically throws `UnsupportedTemporalTypeException`.

There is an easy-to-miss edge case: `Instant.isSupported(ChronoField.INSTANT_SECONDS)` is `true`, yet **`instant.get(ChronoField.INSTANT_SECONDS)` still cannot be used** because this field requires a `long` representation, exceeding the `int` range of the `get(...)` API; use `instant.getLong(ChronoField.INSTANT_SECONDS)` or `instant.getEpochSecond()` instead.

## 3. When to Use Dedicated Getters, `get(field)`, and `getLong(field)`?

`java.time` provides two ways to read values:

1. **Dedicated getters:** `date.getYear()`, `time.getHour()`, `instant.getEpochSecond()`. Readable, type-safe, and usually the first choice.
2. **Temporal field queries:** `temporal.get(ChronoField.YEAR)` or `temporal.getLong(ChronoField.INSTANT_SECONDS)`. Useful when working with `TemporalAccessor`, generic utilities, or dynamically chosen fields.

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);

int year = date.getYear(); // 2024
int yearFromField = date.get(ChronoField.YEAR); // 2024
long epochDay = date.getLong(ChronoField.EPOCH_DAY);
// EPOCH_DAY is the number of days since 1970-01-01, NOT epoch seconds.

Instant instant = Instant.parse("2024-02-29T12:00:00Z");
long seconds = instant.getLong(ChronoField.INSTANT_SECONDS); // 1709208000
~~~

`get(field)` returns `int`, and is only for fields that can be validly represented as `int`; `getLong(field)` returns `long`. **Not every supported field can be used with `get(field)`**, and `getLong(field)` will also fail if the type itself does not support that field.

Defensive pattern when handling a `TemporalAccessor` whose concrete type is unknown:

~~~java
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;

// Illustration inside a method; temporal has already been passed in.
if (temporal.isSupported(ChronoField.YEAR)) {
    long year = temporal.getLong(ChronoField.YEAR);
    System.out.println("year = " + year);
}
~~~

Note: for `ChronoField.YEAR`, the dedicated getter `LocalDate.getYear()` is more appropriate when you know for sure the input is a `LocalDate`. Repeatedly selecting fields by string name or casting unnecessarily often makes code harder to understand.

## 4. Complete Java 17 Example: Reading and Checking Multiple Types

Save as **`DateTimeAccessDemo.java`**:

~~~java
import java.time.*;
import java.time.temporal.ChronoField;

public class DateTimeAccessDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(14, 5, 6, 123_000_000);
        LocalDateTime dateTime = LocalDateTime.of(date, time);

        System.out.println("year = " + date.getYear());
        System.out.println("month = " + date.getMonth());
        System.out.println("month number = " + date.getMonthValue());
        System.out.println("day = " + date.getDayOfMonth());
        System.out.println("day of week = " + date.getDayOfWeek());
        System.out.println("day of year = " + date.getDayOfYear());
        System.out.println("leap year = " + date.isLeapYear());
        System.out.println("length of month = " + date.lengthOfMonth());
        System.out.println("hour = " + time.getHour());
        System.out.println("minute = " + time.getMinute());
        System.out.println("second = " + time.getSecond());
        System.out.println("nano = " + time.getNano());
        System.out.println("dateTime hour = " + dateTime.getHour());

        System.out.println("before Mar 1 = "
                + date.isBefore(LocalDate.of(2024, 3, 1)));
        System.out.println("after Feb 28 = "
                + date.isAfter(LocalDate.of(2024, 2, 28)));
        System.out.println("same day before? = " + date.isBefore(date));
        System.out.println("supports DAY_OF_MONTH = "
                + date.isSupported(ChronoField.DAY_OF_MONTH));
        System.out.println("supports HOUR_OF_DAY = "
                + date.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("Feb 29 valid in 2023 = "
                + MonthDay.of(2, 29).isValidYear(2023));
        System.out.println("Feb 29 valid in 2024 = "
                + YearMonth.of(2024, 2).isValidDay(29));

        Instant instant = Instant.parse("2024-02-29T12:00:00Z");
        System.out.println("instant seconds = " + instant.getEpochSecond());
        System.out.println("getLong seconds = "
                + instant.getLong(ChronoField.INSTANT_SECONDS));
        System.out.println("get(INSTANT_SECONDS) supported as int = "
                + instant.isSupported(ChronoField.INSTANT_SECONDS));

        ZonedDateTime utc = instant.atZone(ZoneOffset.UTC);
        ZonedDateTime hcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("UTC time = " + utc.toLocalTime());
        System.out.println("HCM time = " + hcm.toLocalTime());
        System.out.println("same instant = " + utc.isEqual(hcm));
        System.out.println("zoned objects equal = " + utc.equals(hcm));
    }
}
~~~

Compile/run:

~~~bash
javac DateTimeAccessDemo.java
java DateTimeAccessDemo
~~~

Output verified with `javac --release 17`:

~~~text
year = 2024
month = FEBRUARY
month number = 2
day = 29
day of week = THURSDAY
day of year = 60
leap year = true
length of month = 29
hour = 14
minute = 5
second = 6
nano = 123000000
dateTime hour = 14
before Mar 1 = true
after Feb 28 = true
same day before? = false
supports DAY_OF_MONTH = true
supports HOUR_OF_DAY = false
Feb 29 valid in 2023 = false
Feb 29 valid in 2024 = true
instant seconds = 1709208000
getLong seconds = 1709208000
get(INSTANT_SECONDS) supported as int = true
UTC time = 12:00
HCM time = 19:00
same instant = true
zoned objects equal = false
~~~

**Reading the output:** 2024 is a leap year, so Feb 29 exists and is day 60; the time `14:05:06.123` has a nanosecond component of `123_000_000`; `LocalDate` does not support `HOUR_OF_DAY`. Both `ZonedDateTime` objects refer to the same instant of 12:00 UTC, but in Ho Chi Minh City it displays as 19:00: `isEqual` is `true`, while `equals` is `false` because the two representations carry different time-zone information.

The line `get(INSTANT_SECONDS) supported as int = true` is merely an illustrative label for the result of **`isSupported(...)`**. It does not mean that `get(...)` can actually read this field as an `int`. That is why the program reads the seconds value using `getLong(...)`.

## 5. Common Mistakes When Using `get...()` and `is...()`

| Mistake | Why It Is Wrong | Correct Approach |
|---|---|---|
| Using `date.getMonth() == 2` | `getMonth()` returns the `Month` enum, not an `int` | Use `date.getMonthValue() == 2` or `date.getMonth() == Month.FEBRUARY` |
| Treating `getDayOfWeek()` as the day of month | It is the day-of-week enum | Use `getDayOfMonth()` for days 1–31; `getDayOfWeek()` for day of week |
| Assuming `getNano()` is epoch nanoseconds | It is nanoseconds within a single second | For timestamps, use `Instant` and the appropriate unit contract |
| Calling `LocalDate.getHour()` | A date does not carry a time | Use `LocalTime` or `LocalDateTime` |
| Assuming `isSupported(...)` validates an input date | It only confirms that a field can be accessed | Use `YearMonth.isValidDay(...)` or handle `DateTimeException` |
| Calling `get(ChronoField.INSTANT_SECONDS)` because `isSupported` returns true | The field can exceed the `int` range | Use `getLong(...)` or `Instant.getEpochSecond()` |
| Treating `isBefore` as "before or equal" | It is a strict comparison | Use `!isAfter(...)` if you want to include equality |
| Comparing two `LocalDateTime` objects as global timestamps | They lack an offset/zone to establish a shared timeline | Convert to `Instant` within a defined time-zone context |
| Assuming `ZonedDateTime.equals` only checks the timestamp | It also checks the date-time representation and time zone | Compare instants with `isEqual(...)` or `toInstant().equals(...)` |
| Thinking getters can mutate date/time objects | `java.time` mainly uses immutable objects | `with...()`, `plus...()`, `minus...()` return new values; assign the result if you need to keep it |

In real-world business logic, ask: **are we checking a calendar date, a time of day, or an actual instant in time?** For example, a registration deadline ending on Dec 31 in the local calendar can be handled with `LocalDate`; a trading deadline ending at an exact instant must be resolved to an `Instant` or a zone with rules. Choose the right type first, then choose the getters and checks.

## 6. Self-Practice

1. Given `LocalDate.of(2024, 12, 31)`, which getters retrieve the year, month number, month enum, and day of week? **`getYear()`, `getMonthValue()`, `getMonth()`, `getDayOfWeek()`**.
2. For `LocalTime.of(8, 30, 0)`, what do `getHour()` and `getNano()` return? **`8` and `0`**.
3. What does `LocalDate.of(2024, 2, 29).isBefore(LocalDate.of(2024, 2, 29))` return? **`false`** because the two dates are equal.
4. Which API checks whether Feb 29 is valid in 2023? **`MonthDay.of(2, 29).isValidYear(2023)`** returns `false`; or `YearMonth.of(2023, 2).isValidDay(29)`.
5. What does `date.isSupported(ChronoField.HOUR_OF_DAY)` check? **Whether the `date` object supports reading the hour field**, not whether the date is valid.
6. If two `ZonedDateTime` objects have the same `Instant` but different zones, which method checks whether they represent the same point in time? **`isEqual(...)`** or **`toInstant().equals(...)`**.
7. Can you use `instant.get(ChronoField.INSTANT_SECONDS)` when `isSupported(...) == true`? **No**: the field requires `long`; use `getLong(...)` or `getEpochSecond()`.

**Key takeaway:** Getters tell you **what information an object holds**, while `is...()` helps answer a **specific condition**. Always identify the right `java.time` type, understand the units/fields, and distinguish comparing local date-times from comparing instants on the UTC timeline.

### References

- [Java SE 17 — `LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html)
- [Java SE 17 — `LocalTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html)
- [Java SE 17 — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE 17 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
- [Java SE 17 — `TemporalAccessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAccessor.html)
