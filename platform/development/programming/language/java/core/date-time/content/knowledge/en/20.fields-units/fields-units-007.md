# TemporalAmount and its relationship with Duration and Period

## 1. Distinguishing between a point in time, a unit, and an amount of time

`2024-08-20` is a date; `DAYS` is the day unit; "add 3 days" is an amount of time. `TemporalAmount` represents the third kind of information: **an amount to add to or subtract from a temporal object**, not yet tied to a specific point in time.

For example, "extend by one month" and "expire after 24 hours" are both amounts of time, but they have different meanings. A calendar month depends on the start date, whereas 24 hours expresses an elapsed duration in hours. If you only store an integer and discard the unit semantics and rules, code can easily miscalculate deadlines.

```text
TemporalAmount
├── Duration                 amount in seconds and nanoseconds
└── ChronoPeriod
    └── Period               amount in years, months, and days of the ISO calendar
```

`Duration` and `Period` are two common implementations of `TemporalAmount`. They are not `Temporal`: "2 hours" by itself has no year, month, or hour of day to be read as a point in time. [TemporalAmount](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAmount.html)

## 2. The TemporalAmount contract

| Method | Meaning |
| --- | --- |
| `getUnits()` | The list of units that fully represent this amount |
| `get(unit)` | The value of a unit supported by the implementation |
| `addTo(temporal)` | Applies addition to a temporal point |
| `subtractFrom(temporal)` | Applies subtraction from a temporal point |

`getUnits()` returns an unmodifiable list ordered from largest to smallest unit. The list reflects the structure of the amount, not an arbitrary list of units that every conversion can use.

The idiomatic way to call this is `dateTime.plus(amount)` or `dateTime.minus(amount)`. The amount's contract defines how the adjustment is performed; you should not replace it with a manual loop adding each unit without understanding the implementation's rules.

Illustrative snippet inside a method:

```java
LocalDate start = LocalDate.of(2024, 8, 20);
TemporalAmount extension = Period.ofMonths(1);
LocalDate a = start.plus(extension);
Temporal b = extension.addTo(start);
// a and b both represent 2024-09-20.
```

In the interface signature, `addTo` returns `Temporal`, whereas `LocalDate.plus` returns `LocalDate`. Even though the call forms differ, the input object is not mutated; you must keep the returned result. [Temporal.plus](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/Temporal.html#plus(java.time.temporal.TemporalAmount))

## 3. Duration: an amount in seconds and nanoseconds

`Duration` stores seconds and a nanosecond part. Factories such as `ofHours`, `ofMinutes`, and `ofDays` are convenience constructors; one day in `Duration.ofDays(1)` is always equal to **24 hours**, carrying no rule for "the same local time tomorrow".

For example, `Duration.ofMinutes(90)` represents 5,400 seconds. Its `getUnits()` is `[Seconds, Nanos]`; `get(SECONDS)` reads the seconds component, whereas `get(MINUTES)` is not supported. To get the total number of whole minutes, use `toMinutes()`.

`toHours()` is the total number of whole hours, while `toHoursPart()` is the hour part after splitting into 24-hour days. Both differ from `get(HOURS)`. The factory name used to create an amount does not determine that amount's internal list of units.

`Duration` can be zero or negative and is an immutable type. Total-conversion methods such as `toNanos()` can overflow `long` for large amounts; do not convert everything to nanoseconds just for convenient comparison. `Duration` implements `compareTo` because it compares durations using the same seconds/nanoseconds model. [Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html)

## 4. Period: an amount in calendar years, months, and days

`Period` stores three components—years, months, and days—in the ISO calendar. `Period.of(1, 2, 3)` is 1 year, 2 months, and 3 days; `getUnits()` always lists `[Years, Months, Days]`, even when a component is 0.

`getDays()` only reads **the days component**, not the total number of days of the entire amount. There is no fixed total number of days for "1 month 3 days" without choosing a start date. `toTotalMonths()` combines years and months, excluding the days component.

`normalized()` rebalances years and months: `Period.of(1, 14, 40)` becomes `P2Y2M40D`. It does not automatically convert 40 days into a number of months, because month length requires context. `Period.ofMonths(12)` and `Period.ofYears(1)` are also not `equals` in their original structure.

When adding a `Period`, the years/months part is applied before the days part; years and months may be combined to adjust together. At the end of a month, addition may select the last valid day of the target month. Therefore, you must not assume that "adding and then subtracting the same amount is guaranteed to return to the original date." `Period` is also tied to the ISO calendar system; for dates in another calendar system, an appropriate amount contract is required. [Period](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html)

## 5. Sharing an interface does not mean interchangeable everywhere

| Target temporal | Illustrative amount | Capability outcome |
| --- | --- | --- |
| `LocalDate` | `Period.ofDays(1)` | Can be added by calendar days |
| `LocalDate` | `Duration.ofDays(1)` | Cannot be added: application uses seconds |
| `Instant` | `Duration.ofHours(2)` | Can be added along the timeline |
| `Instant` | `Period.ofMonths(1)` | Calendar months are not supported |
| `LocalTime` | `Duration.ofMinutes(30)` | Can be added, may wrap past midnight |
| `LocalTime` | `Period.ofDays(1)` | Calendar days are not supported |
| `ZonedDateTime` | One day as `Period` or `Duration` | Both can be added, but with different meanings |

The table applies specifically to the listed amounts; do not generalize this into "every `Period` fails on `Instant`." For instance, an amount containing only days is applied differently from an amount containing months. It is the units being applied, the calendar system, and the target type that determine compatibility.

`TemporalAmount` does not provide `isSupported(...)`. You can read `getUnits()` and component values to describe an amount, but checking units on the target temporal does not completely replace the rules of `addTo`, calendar checks, or result bounds. If business logic only accepts an expiration duration, a signature accepting `Duration` is usually clearer than accepting any `TemporalAmount`.

## 6. Demonstration program

Save as `AmountDemo.java`. The example uses Berlin's 2024 daylight saving time rules to show that one calendar day and 24 hours can lead to two different instants.

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAmount;
import java.time.temporal.UnsupportedTemporalTypeException;

public class AmountDemo {
    public static void main(String[] args) {
        TemporalAmount clockAmount = Duration.ofMinutes(90);
        TemporalAmount calendarAmount = Period.of(1, 2, 3);

        System.out.println("durationUnits=" + clockAmount.getUnits());
        System.out.println("durationSeconds=" + clockAmount.get(ChronoUnit.SECONDS));
        System.out.println("periodUnits=" + calendarAmount.getUnits());
        System.out.println("periodMonths=" + calendarAmount.get(ChronoUnit.MONTHS));

        Duration ninetyMinutes = Duration.ofMinutes(90);
        System.out.println("totalMinutes=" + ninetyMinutes.toMinutes());
        try {
            clockAmount.get(ChronoUnit.MINUTES);
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("getMinutesUnsupported");
        }

        LocalDate date = LocalDate.of(2024, 1, 31);
        Period month = Period.ofMonths(1);
        LocalDate advanced = date.plus(month);
        System.out.println("advanced=" + advanced);
        System.out.println("reverse=" + advanced.minus(month));
        System.out.println("original=" + date);
        System.out.println("normalized=" + Period.of(1, 14, 40).normalized());

        try {
            date.plus(Duration.ofDays(1));
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("dateRejectsDuration");
        }

        ZonedDateTime start = ZonedDateTime.of(
                2024, 3, 30, 12, 0, 0, 0, ZoneId.of("Europe/Berlin"));
        ZonedDateTime byCalendar = start.plus(Period.ofDays(1));
        ZonedDateTime byClock = start.plus(Duration.ofDays(1));
        System.out.println("byPeriod=" + byCalendar);
        System.out.println("byDuration=" + byClock);
        System.out.println("calendarElapsedHours="
                + Duration.between(start, byCalendar).toHours());
        System.out.println("durationElapsedHours="
                + Duration.between(start, byClock).toHours());
    }
}
```

Run with JDK 17 or later:

```shell
javac --release 17 AmountDemo.java
java AmountDemo
```

Stdout with IANA time zone data corresponding to Berlin's 2024 rules:

```text
durationUnits=[Seconds, Nanos]
durationSeconds=5400
periodUnits=[Years, Months, Days]
periodMonths=2
totalMinutes=90
getMinutesUnsupported
advanced=2024-02-29
reverse=2024-01-29
original=2024-01-31
normalized=P2Y2M40D
dateRejectsDuration
byPeriod=2024-03-31T12:00+02:00[Europe/Berlin]
byDuration=2024-03-31T13:00+02:00[Europe/Berlin]
calendarElapsedHours=23
durationElapsedHours=24
```

Adding one month to January 31 reaches February 29, because 2024 is a leap year. Subtracting one month from February 29 gives January 29; the information "originally day 31" is no longer stored in the result.

Across the daylight saving time transition, `Period` advances the calendar date and tries to keep the local time at 12:00; `Duration` advances a full 24 elapsed hours and thus reaches 13:00. This is a choice of business semantics, not a data-type optimization.

## 7. Creating an amount from two points in time

Illustrative snippet inside a method:

```java
Period calendarGap = Period.between(
        LocalDate.of(2024, 1, 15), LocalDate.of(2024, 3, 20));
// P2M5D: decomposed by calendar months and days.

Duration elapsed = Duration.between(
        java.time.Instant.parse("2024-01-15T00:00:00Z"),
        java.time.Instant.parse("2024-01-15T01:30:00Z"));
// PT1H30M: 90 minutes of duration.
```

`Period.between` takes two `LocalDate`s; `Duration.between` requires points in time compatible with seconds/nanoseconds arithmetic. Two plain `LocalDate` values do not yet tell the actual elapsed duration: you must choose a time of day and a time zone if you want to turn them into instants. If you only need the number of calendar days, use `ChronoUnit.DAYS.between` instead of calling `Period.getDays()`.

`Period` does not have a length ordering independent of the start date like `Duration`: one month can be shorter than, equal to, or longer than 30 days. If you need to compare two calendar amounts for a business rule, apply them to the same point in time under the same rules and then compare the results.

## 8. Choosing the right contract for your application

- "Lock verification code after 120 seconds", "measure task execution time", "wait another 30 minutes": use `Duration` and an appropriate point in time such as `Instant`.
- "Renew contract for one month", "anniversary after one year": use `Period` with a calendar date and explicit end-of-month rules.
- "Run again at the same time tomorrow in a location": use calendar-date rules with a time zone; define how to handle nonexistent or overlapping local times during DST transitions.
- Use `TemporalAmount` in utilities that genuinely need to accept multiple implementations; clearly document the accepted temporal types, units, and calendar systems.

Do not write a function that converts any `TemporalAmount` to seconds by multiplying each unit by `unit.getDuration()`: the durations of months and years are only estimates. Do not treat `Period` as a string or as a `Duration` under another name.

## 9. Self-practice

1. Why is `Duration.ofHours(2).get(HOURS)` not the way to read the total number of hours?
2. Does `Period.of(0, 1, 10).getDays()` return the total number of days?
3. Write two `ZonedDateTime` points before a daylight saving time transition, then compare adding `Period.ofDays(1)` and `Duration.ofDays(1)`.
4. Is a `TemporalAmount` parameter guaranteed to be addable to any `Temporal`?

Reference answers: (1) `get` only reads supported representation units, use `toHours`; (2) it only returns the 10-day component; (3) the local time and actual elapsed duration can differ; (4) no, a compatibility contract between the amount and the target temporal is required.