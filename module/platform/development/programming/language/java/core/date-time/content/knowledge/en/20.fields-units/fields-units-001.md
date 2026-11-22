# TemporalAccessor for Reading and Temporal for Modifying Values

## 1. Two Contracts on the Same Temporal Value

When writing a function to handle dates and times, determine whether the function needs to **read information** or **compute a new value**. `TemporalAccessor` provides the read contract; `Temporal` extends that contract with adjustment, addition, subtraction, and distance calculation. A `LocalDate` object has both capabilities, but variables declared with each interface will allow calling different methods.

```text
TemporalAccessor
      ↑ extends
   Temporal
```

`Temporal` extends `TemporalAccessor`, so a `Temporal` can always be used where a `TemporalAccessor` is expected. The reverse is not true: `MonthDay` can provide month and day, but it is not a `Temporal`. [TemporalAccessor contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAccessor.html)

Key point in the article title: **“modifying values” means receiving an adjusted result, not mutating the original object**. Familiar value types such as `LocalDate` are immutable; after `plus` or `with`, you need to keep the returned result. Declaring a variable by an interface also does not turn the object into a different data type.

## 2. Reading with Fields and Queries

A **temporal field** (`TemporalField`) answers “which component?”; for example, `ChronoField.YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH`. A **temporal unit** (`TemporalUnit`) answers “add/subtract by which unit?”; for example, `ChronoUnit.DAYS`, `MONTHS`. These two concepts are not interchangeable.

| Reading need | `TemporalAccessor` method |
| --- | --- |
| Check whether a field is present | `isSupported(TemporalField)` |
| Read a value that fits in `int` range | `get(TemporalField)` |
| Read as `long` | `getLong(TemporalField)` |
| Inspect the valid value range of a field in the current context | `range(TemporalField)` |
| Retrieve information via a query strategy | `query(TemporalQuery<R>)` |

For example, `LocalDate.of(2024, 2, 10).range(DAY_OF_MONTH)` returns the range `1 - 29`, because the day-of-month range depends on the current month and year. `getLong` solves the need for large numbers; it does **not** make an unsupported field readable.

Not every temporal value has a year, hour, or time zone. `LocalDate` has a date but no time; `LocalTime` has a time but no date; `Instant` represents a point on the timeline. With `Instant`, you can read `INSTANT_SECONDS` using `getLong`; you cannot infer `YEAR` without choosing a time zone. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

Time zones and calendar systems are not just integers, so they are usually retrieved via `TemporalQueries`. For instance, `date.query(TemporalQueries.zone())` returns `null` for `LocalDate`. However, **not every query with missing data returns `null`**: `LocalDate.from(accessor)` can throw `DateTimeException` if the source lacks sufficient date information.

## 3. Creating New Results with Temporal

| Operation | Meaning | Example |
| --- | --- | --- |
| `with(field, value)` | Set a field according to the type/field rules | Change month to February |
| `with(adjuster)` | Apply an adjustment rule | Pick the last day of the month |
| `plus(amount, unit)` | Add a number of units | Add 3 days |
| `minus(amount, unit)` | Subtract a number of units | Subtract 2 months |
| `plus(amount)` / `minus(amount)` | Apply a temporal amount such as `Period` | Add a calendar period |
| `until(end, unit)` | Count the number of complete units until the end point | Number of days between two dates |

Check `isSupported(TemporalUnit)` before adding/subtracting in a general-purpose algorithm. This is a different overload from `isSupported(TemporalField)` used for reading fields. A `Temporal` is not required to support every unit: `LocalDate` supports `DAYS`, but does not support `HOURS`.

Do not think of `with` as always just replacing one number without regard to the remaining fields. For example, changing the month of `2024-01-31` to February yields `2024-02-29`; setting `DAY_OF_MONTH` directly to 30 on a February date is invalid. The handling rules depend on the specific operation. `until` counts complete units rather than rounding intuitively: from 11:30 to 13:29 there is 1 complete hour. [Temporal contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/Temporal.html)

## 4. Demonstration Program: Reading, Computing Results, and Checking Capabilities

Save as `TemporalContractsDemo.java`. The program uses fixed dates, so it does not depend on the run date or the machine's time zone.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.MonthDay;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.Temporal;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalQueries;
import java.time.temporal.UnsupportedTemporalTypeException;

public class TemporalContractsDemo {
    static String readYear(TemporalAccessor value) {
        if (!value.isSupported(ChronoField.YEAR)) {
            return "YEAR unsupported";
        }
        return Long.toString(value.getLong(ChronoField.YEAR));
    }

    static Temporal addDays(Temporal value, long days) {
        if (!value.isSupported(ChronoUnit.DAYS)) {
            throw new IllegalArgumentException("DAYS unsupported");
        }
        return value.plus(days, ChronoUnit.DAYS);
    }

    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2024, 1, 31);
        TemporalAccessor readable = original;
        Temporal adjustable = original;

        System.out.println("year=" + readYear(readable));
        System.out.println("hourSupported="
                + readable.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("zone=" + readable.query(TemporalQueries.zone()));
        System.out.println("changed="
                + adjustable.with(ChronoField.MONTH_OF_YEAR, 2));
        System.out.println("next=" + addDays(adjustable, 1));
        System.out.println("original=" + original);
        System.out.println("hoursSupported="
                + adjustable.isSupported(ChronoUnit.HOURS));
        System.out.println("februaryRange="
                + LocalDate.of(2024, 2, 10).range(ChronoField.DAY_OF_MONTH));
        System.out.println("fullHours="
                + LocalTime.of(11, 30).until(LocalTime.of(13, 29), ChronoUnit.HOURS));

        TemporalAccessor anniversary = MonthDay.of(2, 29);
        System.out.println("month=" + anniversary.get(ChronoField.MONTH_OF_YEAR));
        System.out.println(readYear(anniversary));

        TemporalAccessor moment = Instant.parse("2024-01-01T00:00:00Z");
        System.out.println("epochSeconds="
                + moment.getLong(ChronoField.INSTANT_SECONDS));
        try {
            moment.get(ChronoField.INSTANT_SECONDS);
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("use getLong for INSTANT_SECONDS");
        }
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 TemporalContractsDemo.java
java TemporalContractsDemo
```

Exact stdout:

```text
year=2024
hourSupported=false
zone=null
changed=2024-02-29
next=2024-02-01
original=2024-01-31
hoursSupported=false
februaryRange=1 - 29
fullHours=1
month=2
YEAR unsupported
epochSeconds=1704067200
use getLong for INSTANT_SECONDS
```

`readYear` accepts `TemporalAccessor` because it only reads. `addDays` accepts `Temporal` because it needs to add days. `next` and `changed` are both computed from `original`, so the two results do not chain; to chain them, call the operation on the previous result.

`INSTANT_SECONDS` is supported, yet `get` still fails: the field's range exceeds `int`, even though a specific value like `1704067200` fits in `int`. Therefore, `isSupported(field) == true` does not mean `get(field)` can always be used.

## 5. Declared Type, Result Type, and Immutability

When holding `LocalDate`, you can write `LocalDate next = date.plusDays(1)` directly. When holding `Temporal`, the `plus` signature returns `Temporal`; the compiler no longer knows that the result is a `LocalDate`.

The following snippet belongs inside a method, not a standalone program:

```java
LocalDate date = LocalDate.of(2024, 1, 31);

date.plusDays(1);                    // Discards the result: date is still 2024-01-31.
LocalDate next = date.plusDays(1);   // next is 2024-02-01.

Temporal general = date;
Temporal result = general.plus(1, ChronoUnit.DAYS);
LocalDate restored = LocalDate.from(result);

TemporalAccessor view = date;
// view.plus(1, ChronoUnit.DAYS);    // Does not compile: the interface has no plus method.
```

`LocalDate.from(result)` is appropriate here because the original input was a `LocalDate`. You should not apply this conversion to an arbitrary `Temporal` result: if the result is a `LocalTime`, date information does not exist. When business logic needs an ISO date, using `LocalDate` directly in the signature is usually clearer. [LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html)

`TemporalAccessor` is a **read interface**, not a guarantee that every implementing class is immutable or thread-safe. With `java.time`, rely on the contract of the concrete type; value types such as `LocalDate` and `MonthDay` document immutability. Do not infer that property for a custom class just because it implements the interface.

## 6. Why Is MonthDay Readable but Not a Temporal?

`MonthDay.of(2, 29)` stores February 29 without a year attached. It cannot automatically determine what date adding one day should produce in a specific year. This type has its own methods such as `withMonth` and `withDayOfMonth`, but it does not provide the `Temporal` contract for general addition/subtraction operations.

That also shows “not a `Temporal`” does not mean “cannot create a new variant”. If you need a date with a full year, choose a year with `atYear(year)` and then work with `LocalDate`. For February 29 in a non-leap year, `atYear` adjusts to February 28; if business rules forbid adjustment, check `isValidYear(year)` first. [MonthDay](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/MonthDay.html)

## 7. When Should You Use the Two Interfaces?

- Use concrete types in most business code: `LocalDate` for calendar dates, `Instant` for points in time, `ZonedDateTime` when time zone rules are needed.
- Use `TemporalAccessor` at utility boundaries that genuinely need to read multiple types, while clearly specifying which fields are required and handling missing fields.
- Use `Temporal` when an algorithm genuinely needs to adjust multiple types, while specifying supported units/fields and business semantics.

A built-in example is `DateTimeFormatter.format(TemporalAccessor)`: the formatter needs to read information, not modify it. However, accepting the right interface does not guarantee formatting will succeed; a pattern with a time part still cannot extract an hour from `LocalDate`. When parsing strings, prefer `LocalDate.parse` or `formatter.parse(text, LocalDate::from)` if the business result is already known to be a date. [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

Do not use casting `(Temporal) accessor` as a data conversion. If `accessor` is a `MonthDay`, that cast throws `ClassCastException`. Choose the right input contract from the start, or perform a rule-based conversion with sufficient data.

## 8. Self-Check

1. Why can `TemporalAccessor value = LocalDate.of(2024, 1, 31)` read the year, yet `plus` cannot be called through the `value` variable?
2. Why is `Instant.isSupported(INSTANT_SECONDS)` true while `get(INSTANT_SECONDS)` still fails?
3. Why does `date.plusDays(1)` not change the value of `date`?
4. Which interface should a function that only displays the month of `LocalDate` and `MonthDay` accept?

Reference hints: (1) callable methods depend on the declared type; (2) field support and `int` range are two different conditions; (3) you must keep the returned result of an immutable type; (4) `TemporalAccessor`, with a contract requiring `MONTH_OF_YEAR`.