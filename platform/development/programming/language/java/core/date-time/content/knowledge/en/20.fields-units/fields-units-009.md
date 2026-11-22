# UnsupportedTemporalTypeException When Choosing the Wrong Field or Unit

## 1. The Exception Describes the Operation's Contract

`UnsupportedTemporalTypeException` usually occurs when requesting a piece of information or a calculation that the temporal object does not support. For example, reading the hour from a `LocalDate` or adding months to an `Instant` both make a request that does not match the data model.

This is a runtime exception, in the hierarchy:

```text
RuntimeException
└── DateTimeException
    └── UnsupportedTemporalTypeException
```

You do not need to declare `throws` for the program to compile, but you still must fix the root cause or handle it at an appropriate boundary. It does not mean the date-time data is corrupted. [UnsupportedTemporalTypeException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/UnsupportedTemporalTypeException.html)

In the error message, “field” is a **field** such as `HourOfDay`; “unit” is a **unit** such as `Hours`. Do not change a field to a unit just because both contain the word “hour”: reading a component and adding an amount are two different tasks.

## 2. Scenarios to Distinguish

| Call | Why does it fail? | Meaningful fix |
| --- | --- | --- |
| `LocalDate.get(HOUR_OF_DAY)` | A date has no time-of-day part | Use a type with time or drop the hour requirement |
| `LocalDate.plus(1, HOURS)` | A date does not support adding hours | Choose a date-time type if business logic needs hours |
| `Instant.get(YEAR)` | No time zone to derive the local year | Choose a `ZoneId` and convert to a zoned type |
| `Instant.plus(1, MONTHS)` | A calendar month has no fixed duration on the timeline | Choose a calendar/time zone to add months |
| `LocalDate.get(EPOCH_DAY)` | Field range is too large for `get` returning `int` | Use `getLong(EPOCH_DAY)` |
| `Duration.get(MINUTES)` | `get` only supports the representation units of the amount | Use `toMinutes()` if total minutes are needed |

The `EPOCH_DAY` case is very easy to misdiagnose: **the field is supported, but the read method is inappropriate**. Not every `UnsupportedTemporalTypeException` is solved by checking `isSupported` and keeping the same call. [TemporalAccessor.get](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAccessor.html#get(java.time.temporal.TemporalField))

## 3. Finding the Exact Receiver Object and Failing Operation

When reading a stack trace, follow from the message and JDK frames to the first application code line. Record:

1. The actual type of the receiver object, such as `LocalDate`, `Instant`, or a string-parsing result.
2. The method being called: `get`, `getLong`, `with`, `plus`, `format`, `between`...
3. The requested field/unit and the intended business meaning.
4. Missing data or read-method limitations.

If the error is `HourOfDay`, check whether you are formatting a `LocalDate` with a pattern that includes hours. If the error is `Seconds` when adding a `Duration` to a date, remember that applying an amount may use a different unit from the factory name that created it.

Do not write control-flow logic by matching the entire `getMessage()`. The message content aids diagnosis, not a stable error code for business logic.

## 4. A Program That Reproduces Errors in a Controlled Way and Fixes Each Cause

Save as `UnsupportedDemo.java`. The invalid calls are isolated so the exception type is clear; the `show` method is only for demonstration, not an error-handling template for every application.

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;

public class UnsupportedDemo {
    static void show(String label, Runnable action) {
        try {
            action.run();
        } catch (DateTimeException ex) {
            System.out.println(label + ": " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 6, 15);
        Instant instant = Instant.parse("2024-06-15T12:30:00Z");
        Duration duration = Duration.ofMinutes(90);
        DateTimeFormatter dateAndTime =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");

        show("readHour", () -> date.get(ChronoField.HOUR_OF_DAY));
        show("addHour", () -> date.plus(1, ChronoUnit.HOURS));
        show("readYear", () -> instant.get(ChronoField.YEAR));
        show("addMonth", () -> instant.plus(1, ChronoUnit.MONTHS));
        show("readEpochInt", () -> date.get(ChronoField.EPOCH_DAY));
        show("durationGetMinutes", () -> duration.get(ChronoUnit.MINUTES));
        show("formatHour", () -> date.format(dateAndTime));

        System.out.println("epochSupported="
                + date.isSupported(ChronoField.EPOCH_DAY));
        System.out.println("epochLong=" + date.getLong(ChronoField.EPOCH_DAY));
        System.out.println("utcYear=" + instant.atZone(ZoneOffset.UTC).getYear());
        System.out.println("totalMinutes=" + duration.toMinutes());
        System.out.println("dateOnly="
                + date.format(DateTimeFormatter.ISO_LOCAL_DATE));
        System.out.println("explicitMidnight="
                + date.atStartOfDay().format(dateAndTime));

        show("invalidMonth", () -> date.with(ChronoField.MONTH_OF_YEAR, 13));
        show("beyondDateRange", () -> LocalDate.MAX.plusDays(1));
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 UnsupportedDemo.java
java UnsupportedDemo
```

Exact stdout:

```text
readHour: UnsupportedTemporalTypeException
addHour: UnsupportedTemporalTypeException
readYear: UnsupportedTemporalTypeException
addMonth: UnsupportedTemporalTypeException
readEpochInt: UnsupportedTemporalTypeException
durationGetMinutes: UnsupportedTemporalTypeException
formatHour: UnsupportedTemporalTypeException
epochSupported=true
epochLong=19889
utcYear=2024
totalMinutes=90
dateOnly=2024-06-15
explicitMidnight=2024-06-15 00:00
invalidMonth: DateTimeException
beyondDateRange: DateTimeException
```

`explicitMidnight` is an example of **explicitly supplying a chosen time**, not recovering an hour that already existed in `LocalDate`. Only use it when business logic truly specifies starting at midnight. The last two lines show that an invalid new value or an out-of-range result is a different issue from choosing the wrong field/unit type.

## 5. Where isSupported Helps, and What Is Still Missing

For general inputs, check the field before reading:

```java
// value has type TemporalAccessor; this is a snippet inside a method.
if (value.isSupported(ChronoField.HOUR_OF_DAY)) {
    long hour = value.getLong(ChronoField.HOUR_OF_DAY);
    System.out.println(hour);
} else {
    System.out.println("Không có trường giờ trong ngày");
}
```

For addition/subtraction, check the overload taking `TemporalUnit` on `Temporal`. Reading a field and calculating by unit do not imply each other: `Instant` can add `HOURS` but cannot directly read `HOUR_OF_DAY`. [Instant: fields and units](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

Even when `isSupported` returns `true`, you still must choose a read method matching the numeric range, validate the new value, and consider result bounds. `LocalDate.MAX` supports days but cannot advance by another day; `MONTH_OF_YEAR` is supported, yet month 13 is still invalid. [LocalDate: addition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#plus(long,java.time.temporal.TemporalUnit))

If the capability is required, you can reject unsuitable inputs before the operation with a clear error. If the information is optional, use a meaningful absent result. Do not return 0 by default when the hour cannot be read, because 0 is also a valid midnight.

## 6. Errors Can Appear Indirectly Through Formatter and Amount

### Formatter Requests a Missing Field

`DateTimeFormatter` reads fields from the input object. The pattern `uuuu-MM-dd HH:mm` requires both date and time, so it cannot directly format a `LocalDate` even though the pattern syntax is valid.

There are two fixes depending on the requirement: display only the date with a date formatter, or create data with time using an explicit rule. Adding `withZone` to the formatter does not automatically create an hour for a date without an instant in time; for `Instant`, specifying a time zone is the prerequisite to derive local calendar fields. [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

### Temporal Amount Uses Units When Applied

`Duration.ofDays(1)` represents 24 hours in seconds/nanoseconds. Adding it to a `LocalDate` can fail on the seconds unit, even though `LocalDate` can add `DAYS`. If you want to advance one calendar day on a `LocalDate`, use `plusDays(1)` or `Period.ofDays(1)`, because that is the intended meaning.

`Duration.ofMinutes(90)` also does not support `get(MINUTES)`: `get` reads representation units, not all conversions. Use `toMinutes()` for total whole minutes; use `getSeconds()` if you need the stored seconds part. [Duration.get](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html#get(java.time.temporal.TemporalUnit))

## 7. Catching Exceptions Without Hiding Design Bugs

Because `UnsupportedTemporalTypeException` extends `DateTimeException`, when there are multiple `catch` blocks, the specific branch must come before the parent branch:

```java
try {
    // A date-time operation at a boundary requiring error handling.
} catch (java.time.temporal.UnsupportedTemporalTypeException ex) {
    // Report that the data type does not satisfy the requested field/unit.
} catch (DateTimeException ex) {
    // Handle other date-time errors according to the contract.
}
```

The snippet above illustrates `catch` ordering, not a standalone program. Do not use a multi-catch containing both the parent class and subclass: Java does not allow alternatives with an inheritance relationship like that.

In business code where the input is known to be `LocalDate`, reading an hour field is usually a programming bug to fix. In a tool that accepts user-selected fields/units, you can check beforehand and report an unsuitable choice. Do not catch and randomly try conversions, do not silently use the system time zone, and do not add dummy data just to make the error disappear.

## 8. Self-Practice

1. Reproduce an error when reading `DAY_OF_MONTH` from `LocalTime`, then explain why replacing `get` with `getLong` does not help.
2. Read `EPOCH_DAY` from `LocalDate` using `get` and `getLong`; compare with `isSupported`.
3. Format an `Instant` using a date-time pattern with the UTC time zone explicitly chosen.
4. Distinguish an error caused by an unsupported field from an error creating February 30.

Reference: (1) the data has no date; `getLong` only changes the numeric range, it does not add information; (2) the field is supported, but `get` does not fit the range; (3) use a formatter with `withZone(ZoneOffset.UTC)` or convert `instant.atZone(ZoneOffset.UTC)`; (4) an incompatible request for the type differs from an invalid date value.