# Common ChronoField and ChronoUnit Values

## 1. Fields describe components; units describe amounts of change

When working with dates and times, the following two questions look similar but use two different API groups:

- "Which **month** is this date in?" reads a field: `ChronoField.MONTH_OF_YEAR`.
- "How many **months** are added to this date?" calculates by a unit: `ChronoUnit.MONTHS`.

For example, the date `2024-02-29` has a month field of 2. Adding 3 days to that date gives `2024-03-03`. The number 2 describes a component of a date; the number 3 is an offset in the day unit. Do not swap these two concepts.

`ChronoField` is a set of standard fields implementing `TemporalField`; `ChronoUnit` is a set of standard units implementing `TemporalUnit`. Both are `enum` types in the `java.time.temporal` package. They are objects that describe a type of field or unit, not containers holding a specific date or time.

| Need | Appropriate group | Example |
| --- | --- | --- |
| Read the day-of-month of the current date | Field | `date.get(ChronoField.DAY_OF_MONTH)` |
| Set the day-of-month to 1 | Field | `date.with(ChronoField.DAY_OF_MONTH, 1)` |
| Add 3 days | Unit | `date.plus(3, ChronoUnit.DAYS)` |
| Count the number of days between two dates | Unit | `ChronoUnit.DAYS.between(start, end)` |
| Find the valid day bounds of the current month | Field range | `date.range(ChronoField.DAY_OF_MONTH)` |

In simple application code, `date.getMonthValue()`, `date.withDayOfMonth(1)`, and `date.plusDays(3)` are usually easier to read. Use field/unit constants when you need to select an operation via parameters, iterate over components, or build shared date-time utilities.

## 2. Common ChronoField values

This table uses the ISO calendar semantics of `LocalDate`, `LocalTime`, and related types.

| Field | Meaning | Values / points to remember |
| --- | --- | --- |
| `YEAR` | Proleptic year on a continuous year axis | For example 2024; includes year 0 and negative years |
| `MONTH_OF_YEAR` | Month number within the year | 1..12; January is 1 |
| `DAY_OF_MONTH` | Day number within the month | Depends on month/year, maximum 28..31 |
| `DAY_OF_YEAR` | Ordinal day number within the year | 1..365 or 366 |
| `DAY_OF_WEEK` | Day of the week | Monday = 1, Sunday = 7 |
| `HOUR_OF_DAY` | Hour of the day | 0..23 |
| `MINUTE_OF_HOUR` | Minute within the hour | 0..59 |
| `SECOND_OF_MINUTE` | Second within the minute | 0..59 in the ISO types considered here |
| `NANO_OF_SECOND` | Nanosecond fraction within the current second | 0..999,999,999 |
| `SECOND_OF_DAY` | Number of seconds from the start of the day | 0..86,399 |
| `NANO_OF_DAY` | Number of nanoseconds from the start of the day | Large value; read with `getLong` |
| `EPOCH_DAY` | Number of days relative to the ISO epoch 1970-01-01 | The epoch day has value 0; not milliseconds |
| `INSTANT_SECONDS` | Number of seconds of the instant relative to the epoch | Used on types with instant information, such as `Instant` |
| `OFFSET_SECONDS` | UTC offset in seconds | Requires a type with an offset, such as `OffsetDateTime` |

For `2024-02-29`, `DAY_OF_MONTH` is 29 while `DAY_OF_YEAR` is 60. For `12:34:56`, `SECOND_OF_MINUTE` is 56 while `SECOND_OF_DAY` is `12 * 3600 + 34 * 60 + 56 = 45296`. Choosing the wrong field can still return a valid number but with the wrong meaning.

Do not use an enum's `ordinal()` as a calendar value. For example, to read the day of the week, use `DAY_OF_WEEK` or `getDayOfWeek().getValue()`, rather than inferring from enum declaration order.

`YEAR_OF_ERA` and `YEAR` are also not completely synonymous: one is the year within an era, and the other is the year on a continuous axis. For BCE data or year 0, keep the right model; do not substitute one constant for the other just because they match in modern years. Contract details are in [ChronoField](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoField.html).

## 3. Reading, setting, and checking field ranges

### 3.1. Reading with get or getLong

`get(field)` returns `int`; `getLong(field)` returns `long`. However, you must not assume `get` always works as long as the current value is small.

Some fields have a value range larger than `int`. `LocalTime.get(NANO_OF_DAY)` does not support reading as `int`; you must use `getLong(NANO_OF_DAY)`. This remains true even when the time being read is midnight and the current nanosecond count is 0. The limit depends on the contract of the field and type, not just the stored number.

For the time `12:34:56.123456789`:

```text
HOUR_OF_DAY      = 12
SECOND_OF_DAY    = 45296
NANO_OF_SECOND   = 123456789
NANO_OF_DAY      = 45296123456789
```

`getLong` only changes the numeric return representation; it does not supply a missing component. A `LocalDate` has no hour, so calling `getLong(HOUR_OF_DAY)` is still invalid. See the reading rules in [TemporalAccessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAccessor.html).

### 3.2. Setting a field with with

`date.with(DAY_OF_MONTH, 1)` requests a date whose day-of-month is 1. It does not mean "add one day"; adding uses `plus(1, DAYS)`.

The standard `java.time` types used here are immutable. The return value from `with` or `plus` must be captured; the original object is not modified.

Behavior when the target value is invalid depends on the field and type. For example, setting `DAY_OF_MONTH = 30` in February throws `DateTimeException`, whereas changing the month from the 31st to February using `MONTH_OF_YEAR` may adjust back to the last valid day of the month. Do not apply a single invalid-date rule to all fields.

### 3.3. General range vs. range for a specific date

- `ChronoField.DAY_OF_MONTH.range()` describes the general range of the field, with a maximum possible value of 31.
- `date.range(ChronoField.DAY_OF_MONTH)` considers that date's context. If `date` is in February 2024, the maximum is 29; in February 2023, it is 28.

For example, a date picker form for February 2024 should not take 31 from the general range and assume it is a valid day for the selected month. When the year-month is known, validate within that context.

`getBaseUnit()` and `getRangeUnit()` help explain a field's structure: for `DAY_OF_MONTH`, the base unit is `DAYS` and the enclosing range unit is `MONTHS`. This explains "counting days within a month"; it does not mean a month always has a fixed number of days.

## 4. Common ChronoUnit values

| Unit | When to use | Notes |
| --- | --- | --- |
| `NANOS` | Shift/measure in nanoseconds | 1 second = 1,000,000,000 nanoseconds |
| `MICROS` | Shift/measure in microseconds | 1 second = 1,000,000 microseconds |
| `MILLIS` | Shift/measure in milliseconds | 1 second = 1,000 milliseconds |
| `SECONDS` | Time in seconds | Often used with instants and times |
| `MINUTES` | Time in minutes | Time-based unit |
| `HOURS` | Time in hours | Time-based unit |
| `DAYS` | Shift/measure in days | Meaning must be tied to the type in use |
| `WEEKS` | Shift/measure in weeks | 7 days in the ISO calendar |
| `MONTHS` | Calendar months | Does not convert to a fixed number of seconds |
| `YEARS` | Calendar years | Must account for leap years and valid days |

Larger units such as `DECADES`, `CENTURIES`, and `MILLENNIA` exist but are less common in typical application calendar logic. `FOREVER` is an artificial unit used for modeling ranges; do not treat it as an amount that can be added to any date or time.

### 4.1. Adding, subtracting, and measuring distance

Three common API forms:

- `value.plus(amount, unit)` and `value.minus(amount, unit)`: produce a shifted value.
- `unit.between(start, end)`: measure the number of complete units between two values.
- `start.until(end, unit)`: the equivalent form to request the measurement from the start value.

For two `LocalDate` values 2024-02-28 and 2024-03-01, `DAYS.between` is 2. Reversing the two values gives -2. Two equal dates give 0. This is a day difference; if business logic counts calendar days covered inclusively at both ends, that is a different counting rule that must be stated explicitly.

Use endpoints of the same type and define the data semantics clearly. Some APIs allow converting the second endpoint to the type of the first, but you should not rely on implicit conversion when it can discard information.

### 4.2. between returns the number of complete units

From `2024-01-10T23:00` to `2024-01-11T01:00`:

| Measurement | Result | Which question is it answering? |
| --- | --- | --- |
| `HOURS.between` on two `LocalDateTime` values | 2 | How many complete hours are there? |
| `DAYS.between` on two `LocalDateTime` values | 0 | How many complete days are there according to this type's measurement? |
| `DAYS.between` on two `toLocalDate()` values | 1 | How many calendar-day steps apart are the two dates? |

There is no contradiction: when you drop the time-of-day part, the question changes. Do not convert to `LocalDate` if the requirement needs the number of full 24-hour periods.

Any remainder does not produce a decimal in the `long` result; complete-unit measurement truncates the incomplete part toward zero. For example, 2 hours in one direction and -2 hours in the opposite direction both correspond to 0 complete days for the two endpoints above.

Be careful with months as well: `2024-01-31.plusMonths(1)` gives `2024-02-29`, but `MONTHS.between` on these two `LocalDate` values returns 0. Adding months includes a clamping step for invalid dates; measuring complete months does not simply invert every addition. Verify the desired business outcome instead of assuming the two operations are always inverses.

### 4.3. Estimated duration is not a universal conversion rule

`ChronoUnit` has `isDateBased()`, `isTimeBased()`, `isDurationEstimated()`, and `getDuration()`. Day/month/year units are date-based; units from nanoseconds through half-days are time-based. `FOREVER` belongs to neither group.

`MONTHS.getDuration()` does not give the actual seconds of a specific month. Even `DAYS` is marked as having an estimated duration: a calendar day with a time zone can experience a UTC offset change. With `ZonedDateTime`, adding one calendar day and adding 24 hours can yield different results across a daylight saving time transition.

Therefore, you must choose both the **data type** and the **unit**. `DAYS` on a calendar date, `HOURS` on a time span, and `DAYS` on an instant do not automatically carry the same business meaning. The unit contract is documented at [ChronoUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html).

## 5. Each type only supports appropriate fields and units

| Type | Typical supported fields | Typical supported units | Unsupported examples |
| --- | --- | --- | --- |
| `LocalDate` | `YEAR`, `DAY_OF_MONTH`, `EPOCH_DAY` | `DAYS`, `MONTHS`, `YEARS` | `HOUR_OF_DAY`, `HOURS` |
| `LocalTime` | `HOUR_OF_DAY`, `NANO_OF_DAY` | `NANOS`, `SECONDS`, `HOURS` | `YEAR`, `DAYS` |
| `LocalDateTime` | Local date and time fields | `HOURS`, `DAYS`, `MONTHS` | `INSTANT_SECONDS`, `OFFSET_SECONDS` |
| `YearMonth` | `YEAR`, `MONTH_OF_YEAR` | `MONTHS`, `YEARS` | `DAY_OF_MONTH`, `DAYS` |
| `Instant` | `INSTANT_SECONDS`, `NANO_OF_SECOND` | `NANOS`, `SECONDS`, `HOURS` | `YEAR`, `MONTHS` |

This table lists common examples, not an exhaustive list.

An `Instant` represents a point on the timeline, but it does not pick a time zone on its own to return a local year or hour. To read the year of an instant at a location, convert it with an explicit time zone, such as `instant.atZone(zone).getYear()`. Do not assume UTC if the actual question refers to local date-time in another region.

There are two forms of support checks:

- `value.isSupported(ChronoField.DAY_OF_MONTH)`: asks about a field.
- `value.isSupported(ChronoUnit.DAYS)`: asks about a unit.

These are two distinct checks despite sharing the same method name. When the type and operation are known for sure, you can call the operation directly. When the field/unit is chosen dynamically, checking first helps produce meaningful error messages; there is no need to try calling and swallow every exception.

`isSupported` returning `true` also does not guarantee that every addition amount or every set value is valid. For example, `LocalDate` supports `DAY_OF_MONTH`, yet February still rejects day 30. Very large addition amounts can also overflow the representable range.

## 6. Java 17+ program to verify fields, units, and errors

Save the following code as `FieldsAndUnits.java`. This is a standalone program using JDK types, requiring no external libraries. The helper checks actively throw `AssertionError` if a result is wrong, so `-ea` does not need to be enabled.

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.YearMonth;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.Objects;

public class FieldsAndUnits {
    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Class<? extends RuntimeException> type,
                                Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError("Unexpected exception", ex);
            }
            checks++;
            return;
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(12, 34, 56, 123_456_789);
        eq(date.get(ChronoField.YEAR), 2024);
        eq(date.get(ChronoField.MONTH_OF_YEAR), 2);
        eq(date.get(ChronoField.DAY_OF_MONTH), 29);
        eq(date.get(ChronoField.DAY_OF_YEAR), 60);
        eq(date.get(ChronoField.DAY_OF_WEEK), 4);
        eq(time.get(ChronoField.HOUR_OF_DAY), 12);
        eq(time.get(ChronoField.SECOND_OF_DAY), 45_296);
        eq(time.getLong(ChronoField.NANO_OF_DAY), 45_296_123_456_789L);
        eq(ChronoField.DAY_OF_MONTH.range().getMaximum(), 31L);
        eq(date.range(ChronoField.DAY_OF_MONTH).getMaximum(), 29L);
        eq(ChronoField.DAY_OF_MONTH.getBaseUnit(), ChronoUnit.DAYS);
        eq(ChronoField.DAY_OF_MONTH.getRangeUnit(), ChronoUnit.MONTHS);

        eq(date.with(ChronoField.DAY_OF_MONTH, 1),
                LocalDate.of(2024, 2, 1));
        eq(date.plus(3, ChronoUnit.DAYS), LocalDate.of(2024, 3, 3));
        eq(date, LocalDate.of(2024, 2, 29));
        eq(date.isSupported(ChronoField.HOUR_OF_DAY), false);
        eq(date.isSupported(ChronoUnit.HOURS), false);
        eq(time.isSupported(ChronoUnit.DAYS), false);
        eq(YearMonth.of(2024, 2).isSupported(ChronoField.DAY_OF_MONTH), false);
        eq(YearMonth.of(2024, 2).isSupported(ChronoUnit.MONTHS), true);
        eq(Instant.EPOCH.isSupported(ChronoField.INSTANT_SECONDS), true);
        eq(Instant.EPOCH.isSupported(ChronoField.YEAR), false);
        eq(Instant.EPOCH.isSupported(ChronoUnit.MONTHS), false);
        eq(Instant.EPOCH.getLong(ChronoField.INSTANT_SECONDS), 0L);

        rejects(UnsupportedTemporalTypeException.class,
                () -> date.get(ChronoField.HOUR_OF_DAY));
        rejects(UnsupportedTemporalTypeException.class,
                () -> date.plus(1, ChronoUnit.HOURS));
        rejects(UnsupportedTemporalTypeException.class,
                () -> time.get(ChronoField.NANO_OF_DAY));
        rejects(DateTimeException.class,
                () -> date.with(ChronoField.DAY_OF_MONTH, 30));

        LocalDate start = LocalDate.of(2024, 2, 28);
        LocalDate end = LocalDate.of(2024, 3, 1);
        eq(ChronoUnit.DAYS.between(start, end), 2L);
        eq(start.until(end, ChronoUnit.DAYS), 2L);
        eq(ChronoUnit.DAYS.between(end, start), -2L);
        LocalDate jan31 = LocalDate.of(2024, 1, 31);
        eq(jan31.plus(1, ChronoUnit.MONTHS), date);
        eq(ChronoUnit.MONTHS.between(jan31, date), 0L);

        LocalDateTime night = LocalDateTime.of(2024, 1, 10, 23, 0);
        LocalDateTime morning = LocalDateTime.of(2024, 1, 11, 1, 0);
        eq(ChronoUnit.HOURS.between(night, morning), 2L);
        eq(ChronoUnit.DAYS.between(night, morning), 0L);
        eq(ChronoUnit.DAYS.between(night.toLocalDate(),
                morning.toLocalDate()), 1L);
        eq(ChronoUnit.DAYS.isDateBased(), true);
        eq(ChronoUnit.HOURS.isTimeBased(), true);
        eq(ChronoUnit.DAYS.isDurationEstimated(), true);
        eq(ChronoUnit.HOURS.isDurationEstimated(), false);

        System.out.println("dayOfYear=" + date.get(ChronoField.DAY_OF_YEAR));
        System.out.println("nanoOfDay=" + time.getLong(ChronoField.NANO_OF_DAY));
        System.out.println("maxDay=" + date.range(ChronoField.DAY_OF_MONTH).getMaximum());
        System.out.println("plus3Days=" + date.plus(3, ChronoUnit.DAYS));
        System.out.println("elapsedHours=" + ChronoUnit.HOURS.between(night, morning));
        System.out.println("completeDays=" + ChronoUnit.DAYS.between(night, morning));
        System.out.println("calendarDateSteps=" + ChronoUnit.DAYS.between(
                night.toLocalDate(), morning.toLocalDate()));
        System.out.println("completeMonths=" + ChronoUnit.MONTHS.between(jan31, date));
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 FieldsAndUnits.java
java FieldsAndUnits
```

Stdout:

```text
dayOfYear=60
nanoOfDay=45296123456789
maxDay=29
plus3Days=2024-03-03
elapsedHours=2
completeDays=0
calendarDateSteps=1
completeMonths=0
PASS checks=40
```

The last line confirms 40 checks completed, including operations required to throw exceptions. The `rejects` method fails the program if an operation does not throw or throws an unexpected exception type; catching errors in the example is not silently ignoring them.

The three lines `elapsedHours`, `completeDays`, and `calendarDateSteps` use the same pair of times to expose the difference between asking about complete hours, complete days, and calendar-date differences. The two lines `maxDay` and `completeMonths` verify points that are easy to reason about incorrectly at month boundaries.

## 7. Common pitfalls

- **Using a field instead of a unit:** `DAY_OF_MONTH` describes a component of a date; `DAYS` describes a unit of measurement. Choose the group based on whether you are "reading/setting a component" or "shifting/measuring distance".
- **Assuming month numbers start at 0:** `MONTH_OF_YEAR` in the ISO calendar starts at 1. Do not carry legacy API conventions into `java.time`.
- **Using `get` for every field:** for `NANO_OF_DAY`, `EPOCH_DAY`, or `INSTANT_SECONDS` on the corresponding types, use the `long` getter as specified by the contract.
- **Using `getLong` to fix a missing field:** widening the numeric type does not create an hour for `LocalDate` or a local year for `Instant`.
- **Using a field's general range to validate a specific date:** use the range attached to the object or validate against the specific year-month.
- **Confusing setting a field with adding an amount:** setting the day to 1 differs from adding one day; setting the hour to 3 differs from adding three hours.
- **Assuming `between` always equals the number of `plus` calls:** end-of-month clamping adjustments can falsify that assumption.
- **Converting months/years to a fixed number of seconds:** use a concrete calendar or two concrete endpoints instead.
- **Discarding the return value:** immutable standard types do not mutate the original variable through a `plus` or `with` call.

## 8. Practice choosing the API

1. **Read the month of `2024-11-05`.** Use `get(MONTH_OF_YEAR)` or `getMonthValue()`; the result is 11. `MONTHS` is not a field for reading the month.

2. **From `2024-11-05`, produce the first day of the same month and the date two weeks later.** The first uses `with(DAY_OF_MONTH, 1)`, yielding `2024-11-01`. The second uses `plus(2, WEEKS)`, yielding `2024-11-19`. Both leave the original object unchanged.

3. **Read the nanoseconds from the start of the day at `00:00:00`.** Use `getLong(NANO_OF_DAY)`, returning 0. Do not substitute `get` just because the current value is small.

4. **Count the months between two billing periods `2024-01` and `2024-02`.** If the data is truly monthly periods, use two `YearMonth` values; `MONTHS.between` returns 1. Do not turn them into Jan 31 and Feb 29 and expect complete-month measurement on `LocalDate` to always have the same meaning.

5. **A utility accepts a user-selected field, but the data is a `LocalDate`.** If the user selects `HOUR_OF_DAY`, the utility should report that the field is incompatible with the data; do not silently attach `00:00` to make the operation appear to succeed.

When choosing a constant, state the question first: which component is being read, which component is being replaced, which unit is being added, or how many complete units are being measured between two values. Then verify that the data type holds enough information to answer that question.
