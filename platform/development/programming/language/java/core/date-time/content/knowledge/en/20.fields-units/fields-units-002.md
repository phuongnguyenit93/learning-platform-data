# TemporalField and TemporalUnit

## 1. A component to read, a unit to compute

In `java.time`, asking "what is the current day of the month?" is different from requesting "add one day". The first needs a **temporal field** (`TemporalField`); the second needs a **temporal unit** (`TemporalUnit`). They are two objects that describe operations, not the date or time itself.

For example, with `2024-01-31`: the `DAY_OF_MONTH` field has value 31; the `DAYS` unit is used to add or count days. `DAY_OF_MONTH` does not mean "one day", and `DAYS` does not tell you what day of the month it currently is.

| Comparison | `TemporalField` | `TemporalUnit` |
| --- | --- | --- |
| Main question | Which component to read/set? | Which unit to add or measure by? |
| Examples | `DAY_OF_MONTH`, `HOUR_OF_DAY` | `DAYS`, `HOURS` |
| Commonly used standard type | `ChronoField` | `ChronoUnit` |
| Typical operations | `getLong(field)`, `with(field, value)` | `plus(amount, unit)`, `until(end, unit)` |

The interface describes the contract; the enum provides the standard set of values. Therefore, you can declare `TemporalField field = ChronoField.DAY_OF_MONTH` and `TemporalUnit unit = ChronoUnit.DAYS`. Do not use an enum's `ordinal()` to store the meaning of a field or unit in data.

## 2. TemporalField: a component with a name, range, and way to read

A field is not just a label. It knows how to check support, retrieve a value, and adjust a temporal object. [TemporalField](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalField.html)

| Method | Role |
| --- | --- |
| `isSupportedBy(temporal)` | Does the object have this field? |
| `getFrom(temporal)` | Read the value as a `long` |
| `adjustInto(temporal, newValue)` | Produce a result with the field set |
| `range()` | General range of the field |
| `rangeRefinedBy(temporal)` | Range refined by a specific object |
| `getBaseUnit()` | In what unit is the field measured? |
| `getRangeUnit()` | Within what unit does the field vary? |

`DAY_OF_MONTH` is measured in `DAYS`, bounded within `MONTHS`; `MINUTE_OF_HOUR` is measured in `MINUTES`, bounded within `HOURS`. The "range unit" is not the maximum value: for day of month, `getRangeUnit()` returns `MONTHS`, while `range()` describes the numeric values.

The general range of `DAY_OF_MONTH` is `1 - 28/31`: the minimum is always 1, and the maximum varies from 28 to 31. When bound to February of the leap year 2024, the refined range is `1 - 29`. Calling `ChronoField.DAY_OF_MONTH.checkValidValue(31)` only confirms that 31 belongs to the general range; it does not prove that day 31 exists in February.

`ChronoField` also includes combined fields such as `SECOND_OF_DAY` and `EPOCH_DAY`, not only year/month/day. Many fields belong to date or time, but not all belong to one of those two groups: for instance, UTC offset is a different kind of information. Do not assume every date field exists on every object. [ChronoField](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoField.html)

## 3. TemporalUnit: a unit is not a temporal amount

`ChronoUnit.DAYS` is only the day unit. Combining the number 3 with that unit expresses the request to add three days. `Period.ofDays(3)` and `Duration.ofHours(3)` are **temporal amounts** (`TemporalAmount`), not `TemporalUnit`.

| Method | Role |
| --- | --- |
| `isSupportedBy(temporal)` | Can this unit be added/subtracted? |
| `addTo(temporal, amount)` | Add the number of units and return the result |
| `between(start, end)` | Count the number of whole units between two points |
| `getDuration()` | Representative duration, which may be only an estimate |
| `isDurationEstimated()` | Is the representative duration an estimate? |
| `isDateBased()` / `isTimeBased()` | Classify as calendar-date-based / time-based |

For example, from 09:15 to 11:14 there is 1 whole hour. `HOURS.between` does not return 1.9833 and does not round to 2. When the end point is before the start point, the result can be negative. [TemporalUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalUnit.html)

Do not convert months to seconds by multiplying the number of months by `MONTHS.getDuration()`. Calendar months have different numbers of days; days in regions observing daylight saving time can also be longer or shorter than 24 hours. For `ChronoUnit`, date-based units have estimated durations; time-based units such as `HOURS` have exact durations by contract, ignoring leap seconds. `FOREVER` is a synthetic unit, not an option for adding infinity. [ChronoUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoUnit.html)

## 4. Two ways to write the same intent

Illustrative snippet inside a method, where `date` is a `LocalDate`:

```java
long day1 = date.getLong(ChronoField.DAY_OF_MONTH);
long day2 = ChronoField.DAY_OF_MONTH.getFrom(date);

LocalDate first1 = date.with(ChronoField.DAY_OF_MONTH, 1);
LocalDate first2 = ChronoField.DAY_OF_MONTH.adjustInto(date, 1);

LocalDate next1 = date.plus(3, ChronoUnit.DAYS);
LocalDate next2 = ChronoUnit.DAYS.addTo(date, 3);

long gap1 = date.until(next1, ChronoUnit.DAYS);
long gap2 = ChronoUnit.DAYS.between(date, next1);
```

`TemporalField.resolve(...)` is an advanced integration hook for the field resolution phase during string parsing; it is not a method you normally need to call in business code that reads or sets dates.

Each pair expresses the same intent with the types and values in the example. Usually you choose the form starting from the date-time object so readers clearly see the data being operated on.

This mechanism also makes the API extensible: date-time classes handle standard `ChronoField`/`ChronoUnit` constants directly; for other fields or units, the call is delegated to the corresponding method on the field/unit object. This is a double-dispatch mechanism that allows adding definitions without modifying every date-time class.

## 5. Runnable program

Save as `FieldUnitDemo.java`. The program contrasts setting a field with adding a unit, the general range with a refined range, and a calendar day with 24 hours.

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalField;
import java.time.temporal.TemporalUnit;

public class FieldUnitDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 1, 31);
        TemporalField field = ChronoField.DAY_OF_MONTH;
        TemporalUnit unit = ChronoUnit.DAYS;

        System.out.println("day=" + field.getFrom(date));
        System.out.println("base=" + field.getBaseUnit());
        System.out.println("rangeUnit=" + field.getRangeUnit());
        System.out.println("generalRange=" + field.range());
        System.out.println("februaryRange="
                + field.rangeRefinedBy(LocalDate.of(2024, 2, 10)));

        LocalDate setFirst = date.with(field, 1);
        LocalDate addOne = unit.addTo(date, 1);
        System.out.println("setFirst=" + setFirst);
        System.out.println("addOne=" + addOne);
        System.out.println("original=" + date);
        System.out.println("daysBetween=" + unit.between(date, addOne));
        System.out.println("fullHours=" + ChronoUnit.HOURS.between(
                LocalTime.of(9, 15), LocalTime.of(11, 14)));

        System.out.println("supportsHourField="
                + date.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("supportsHourUnit="
                + date.isSupported(ChronoUnit.HOURS));
        System.out.println("dayEstimated=" + ChronoUnit.DAYS.isDurationEstimated());
        System.out.println("hourEstimated=" + ChronoUnit.HOURS.isDurationEstimated());

        ZonedDateTime start = ZonedDateTime.of(
                2024, 3, 30, 12, 0, 0, 0, ZoneId.of("Europe/Berlin"));
        ZonedDateTime nextDay = start.plus(1, ChronoUnit.DAYS);
        ZonedDateTime next24Hours = start.plus(24, ChronoUnit.HOURS);
        System.out.println("calendarDay=" + nextDay);
        System.out.println("twentyFourHours=" + next24Hours);
        System.out.println("elapsedHours="
                + Duration.between(start, nextDay).toHours());
    }
}
```

Run with JDK 17 or later:

```shell
javac --release 17 FieldUnitDemo.java
java FieldUnitDemo
```

Stdout with IANA time-zone data corresponding to Berlin rules in 2024:

```text
day=31
base=Days
rangeUnit=Months
generalRange=1 - 28/31
februaryRange=1 - 29
setFirst=2024-01-01
addOne=2024-02-01
original=2024-01-31
daysBetween=1
fullHours=1
supportsHourField=false
supportsHourUnit=false
dayEstimated=true
hourEstimated=false
calendarDay=2024-03-31T12:00+02:00[Europe/Berlin]
twentyFourHours=2024-03-31T13:00+02:00[Europe/Berlin]
elapsedHours=23
```

`with(DAY_OF_MONTH, 1)` sets the day to 1 and keeps January. `plus(1, DAYS)` advances one day into February. Both return a new value; `original` remains January 31.

In the Berlin example, switching from standard time to daylight saving time causes a calendar day crossing the transition to have only 23 actual elapsed hours. Adding one `DAYS` keeps 12:00 on the next day; adding 24 `HOURS` moves along the timeline and arrives at 13:00. The meaning of an operation is determined by both the unit and the receiving type. [ZonedDateTime: plus](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#plus(long,java.time.temporal.TemporalUnit))

## 6. Checking support with the right type

A value may support certain fields and certain units, not the entire API. There are two overloads that are easy to confuse:

```java
date.isSupported(ChronoField.DAY_OF_MONTH); // Can the field be read/set?
date.isSupported(ChronoUnit.DAYS);          // Can this unit be added/subtracted?
```

In read-only algorithms, `TemporalAccessor` is enough to check fields. To add units, you need `Temporal`. Checking a field does not substitute for checking a unit; both return `false` in the hour example with `LocalDate` because that date does not store a time-of-day part.

When reading large numbers, prefer `getLong(field)` if the field contract requires it. `isSupported(field)` being true does not guarantee `get(field)` can return an `int`: the `EPOCH_DAY` field on `LocalDate` has a range larger than `int`. Do not catch all exceptions and silently return 0, because 0 can be a valid value and hides missing data.

## 7. The standard set is not the entire extensibility story

`ChronoField` and `ChronoUnit` cover most needs. Other definitions built into the JDK include `IsoFields.QUARTER_OF_YEAR`, `IsoFields.QUARTER_YEARS`, and fields from `WeekFields`. Week fields depend on week rules, so you must explicitly choose a business standard rather than assuming all calendars have the same week numbers.

Illustrative snippet inside a method:

```java
LocalDate date = LocalDate.of(2024, 5, 20);
long quarter = date.getLong(java.time.temporal.IsoFields.QUARTER_OF_YEAR);
LocalDate later = date.plus(1, java.time.temporal.IsoFields.QUARTER_YEARS);
// quarter = 2; later = 2024-08-20.
```

You do not need to implement the interfaces yourself just to add a few days. If you truly create a custom field or unit, you must define support checks, range, adjustment logic, immutability, and thread safety according to the contract, rather than just giving it a new name. [IsoFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/IsoFields.html)

## 8. Common mistakes and how to choose

- **Using `DAY_OF_MONTH` as a unit:** choose `with` when setting a component, choose `plus` with `DAYS` when advancing days.
- **Treating `range()` as a complete date-validity check:** use the object-refined range and actual date construction to enforce year/month/day relationships.
- **Treating a month as a fixed number of seconds:** use calendar addition on the appropriate date-time type.
- **Counting months by subtracting the month numbers of two dates:** this ignores years and whole units; use `MONTHS.between` according to the defined requirement.
- **Using overly broad interfaces in specific business logic:** if you only handle `LocalDate`, signatures and methods such as `getDayOfMonth` and `plusDays` are usually clearer.

## 9. Practice

1. For `2024-04-20`, predict the result of `with(DAY_OF_MONTH, 1)` and `plus(1, DAYS)`.
2. Print `DAY_OF_MONTH.rangeRefinedBy` for February 2023 and February 2024.
3. Count the whole minutes and whole hours between 08:40 and 10:05 using two different units.
4. Explain why `DAYS.getDuration()` is not enough to compute "12:00 tomorrow" in a time zone with daylight saving time transitions.

Answers: (1) `2024-04-01` and `2024-04-21`; (2) `1 - 28` and `1 - 29`; (3) 85 minutes, 1 hour; (4) that is a local calendar request, so time-zone rules must be applied when adding days.