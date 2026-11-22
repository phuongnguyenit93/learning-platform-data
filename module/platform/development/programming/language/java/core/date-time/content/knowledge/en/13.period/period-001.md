# `Period` represents an amount of time in calendar years, months, and days

`java.time.Period` represents **a calendar-based amount of time** using three components: years, months, and days. It is useful when business logic says "add one month", "subtract two years", or "after 3 months and 5 days", because these units depend on the calendar and do not correspond to a fixed number of seconds.

Unlike `Duration`, which is represented in seconds and nanoseconds, `Period` does not store a total number of days or an overall number of seconds. `Period.ofMonths(1)` is one calendar month, not always 30 days; `Period.ofDays(1)` is one calendar day, not always 24 hours when applied in a zone with DST.

## 1. Structure and how to create a `Period`

A `Period` has three integer components:

- **Years** — number of years.
- **Months** — number of months.
- **Days** — number of days.

It can be created via factory methods:

```java
import java.time.Period;

Period years = Period.ofYears(2);
Period months = Period.ofMonths(3);
Period days = Period.ofDays(10);
Period combined = Period.of(1, 2, 10);

System.out.println(years);    // P2Y
System.out.println(months);   // P3M
System.out.println(days);     // P10D
System.out.println(combined); // P1Y2M10D
```

`Period.of(years, months, days)` accepts three independent components. `P1Y2M10D` is the ISO-8601 representation: the letter `P` starts the period designator, `Y` is years, `M` in this position is months, and `D` is days.

Main factory methods:

| Method | Meaning |
| --- | --- |
| `Period.ofYears(n)` | Creates an amount of `n` years |
| `Period.ofMonths(n)` | Creates an amount of `n` months |
| `Period.ofWeeks(n)` | Creates an amount of `7n` days |
| `Period.ofDays(n)` | Creates an amount of `n` days |
| `Period.of(y, m, d)` | Creates the three components: years, months, and days |
| `Period.ZERO` | A zero-length period |

Factory methods accept negative numbers. For example, `Period.ofMonths(-2)` represents subtracting two months when applied to a date. `Period` values are immutable; operations return a new `Period` without modifying the existing instance.

## 2. Why is one month not equal to a fixed number of days?

Month length depends on the specific year and month:

| Month | Number of days |
| --- | ---: |
| January | 31 |
| February (common year) | 28 |
| February (leap year) | 29 |
| April, June, September, November | 30 |
| March, May, July, August, October, December | 31 |

Therefore, `Period.ofMonths(1)` cannot be accurately converted to "30 days" for every start date. For example:

```java
import java.time.LocalDate;
import java.time.Period;

LocalDate start = LocalDate.of(2024, 1, 31);

System.out.println(start.plus(Period.ofMonths(1)));
// 2024-02-29

System.out.println(start.plusDays(30));
// 2024-03-01
```

In the leap year 2024, adding one month to January 31 results in the last day of February, whereas adding 30 days results in March 1. These are two different business requirements.

### Adding one month when the target day does not exist

When adding months or years to a date results in an invalid day-of-month, `java.time` date-time types adjust to the nearest valid day in the target month. For example:

```java
LocalDate jan31 = LocalDate.of(2025, 1, 31);
LocalDate feb = jan31.plus(Period.ofMonths(1));
System.out.println(feb); // 2025-02-28

LocalDate leapDay = LocalDate.of(2024, 2, 29);
System.out.println(leapDay.plus(Period.ofYears(1)));
// 2025-02-28
```

There is no February 29 in 2025, so adding one year yields 2025-02-28. This is `LocalDate`'s calendar adjustment rule; if business logic requires a different rule (such as end-of-month, next business day, or keeping the 29th when available), encode that rule explicitly and test it clearly.

## 3. Reading the components of a `Period`

`Period` provides getters for each component:

```java
Period p = Period.of(2, 14, 40);

System.out.println(p.getYears());  // 2
System.out.println(p.getMonths()); // 14
System.out.println(p.getDays());   // 40
System.out.println(p);             // P2Y14M40D
```

The getters return the **stored components** without automatically normalizing months into years or days into months. Thus, `getMonths()` can return 14 and `getDays()` can return 40. This is valid because a `Period` maintains its components separately.

### `normalized()` normalizes years and months

`normalized()` converts the total months into years and months within the standard range, but **does not convert days into months**, because the number of days in a month depends on the calendar:

```java
Period p = Period.of(2, 14, 40);

System.out.println(p.normalized()); // P3Y2M40D
```

This operation does not mutate `p`; it returns a new normalized `Period`. The `40D` part remains unchanged. Do not expect `normalized()` to return a single total number of days or convert to a `Duration`.

**Important:** `Period.ofMonths(12)` and `Period.ofYears(1)` applied to a calendar date usually produce equivalent results in many cases, but the `Period` values are not necessarily equal according to `equals()`:

```java
System.out.println(Period.ofMonths(12).equals(Period.ofYears(1)));
// false

System.out.println(Period.ofMonths(12).normalized());
// P1Y
System.out.println(Period.ofMonths(12).normalized()
        .equals(Period.ofYears(1))); // true
```

If you need to compare the normalized representation of the years/months parts, use `normalized()`. If you need to compare the effect after applying to a specific date, apply it to the date and compare the results; the start date can affect how the amount of time is interpreted.

## 4. Applying `Period` to dates and times

With `LocalDate`, `plus(Period)` and `minus(Period)` are common:

```java
LocalDate today = LocalDate.of(2026, 10, 24);
Period trial = Period.ofMonths(1).plusDays(14);

LocalDate endDate = today.plus(trial);
System.out.println(endDate); // 2026-12-08

LocalDate back = endDate.minus(trial);
System.out.println(back); // 2026-10-24
```

This example is reversible at this specific date. However, not every sequence of adding and then subtracting separate components restores the original date due to end-of-month clamping. For example:

```java
LocalDate jan31 = LocalDate.of(2025, 1, 31);
LocalDate feb28 = jan31.plusMonths(1);
LocalDate back = feb28.minusMonths(1);

System.out.println(feb28); // 2025-02-28
System.out.println(back);  // 2025-01-28
```

After moving from Jan 31 to Feb 28, the information that "the original day was 31" is not stored in the Feb 28 value; subtracting one month yields Jan 28. If a consistent "end-of-month" rule is required, store it explicitly as a business rule rather than expecting `Period` to remember the start date.

### Applying to `LocalDateTime` or `ZonedDateTime`

`Period` can be added to many types in `java.time` that support calendar arithmetic, including `LocalDate`, `LocalDateTime`, and `ZonedDateTime`. The result depends on the target type:

- For `LocalDate`, only the calendar date fields change.
- For `LocalDateTime`, the local date-time fields are recalculated, though this type has no time zone to determine an instant.
- For `ZonedDateTime`, adding days/months/years operates on the local date-time timeline; then the time zone resolves the offset and DST at the target date.

```java
ZonedDateTime meeting = ZonedDateTime.of(
        2024, 3, 9, 9, 0, 0, 0,
        ZoneId.of("America/New_York"));

System.out.println(meeting.plus(Period.ofDays(1)));
// 2024-03-10T09:00-04:00[America/New_York]
```

In this example, the meeting time remains 09:00 local time. The actual elapsed time between the two instants is 23 hours due to spring DST. If the requirement is "after exactly 24 hours", use `Duration.ofHours(24)`, not `Period.ofDays(1)`.

## 5. Distinguishing `Period` and `Duration`

Both classes can express "an amount of time", but their underlying units differ:

| Characteristic | `Period` | `Duration` |
| --- | --- | --- |
| Components | Years, months, days | Seconds and nanoseconds |
| Interpretation | Calendar-based amount | Second-based amount of time |
| `ofDays(1)` means | One calendar day | Exactly 86,400 seconds |
| Has months/years | Yes | No |
| Fixed conversion from days to seconds | Cannot be converted generally for all dates | Yes: 1 day = 86,400 seconds |
| Suitable for | Monthly billing cycles, age, calendar terms, anniversaries | Timeouts, 24-hour TTL, measuring elapsed intervals |

Example across spring DST in New York:

```java
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime byPeriod = start.plus(Period.ofDays(1));
ZonedDateTime byDuration = start.plus(Duration.ofDays(1));

System.out.println(byPeriod);
// 2024-03-10T12:00-04:00[America/New_York]

System.out.println(byDuration);
// 2024-03-10T13:00-04:00[America/New_York]
```

The `Period` result is noon on the next calendar day; the `Duration` result is exactly 86,400 seconds later, which is 13:00. Both are valid, so choose according to intent.

Do not use `Period.getDays()` to calculate the total number of days in an entire period. For example, `Period.of(1, 2, 3).getDays()` returns 3, not the total days in 1 year, 2 months, and 3 days. Years and months cannot be converted into a single total number of days without choosing a start date and calendar.

## 6. Creating a `Period` from two dates

`Period.between(startDate, endDate)` calculates the difference in years/months/days between two `LocalDate` values. The components are broken down by calendar, not total days:

```java
LocalDate start = LocalDate.of(2024, 1, 31);
LocalDate end = LocalDate.of(2024, 3, 2);

Period p = Period.between(start, end);

System.out.println(p);             // P1M2D
System.out.println(p.getYears());  // 0
System.out.println(p.getMonths()); // 1
System.out.println(p.getDays());   // 2
System.out.println(start.plus(p).equals(end)); // true
```

With dates in reverse order, `Period.between` produces a negative result per the API contract:

```java
Period reverse = Period.between(
        LocalDate.of(2024, 3, 2),
        LocalDate.of(2024, 1, 31));

System.out.println(reverse); // P-1M-2D
```

Do not interpret this negative value as simple arithmetic on total days; it represents calendar components between the start and end dates. If you need the total number of elapsed days between two dates, use `ChronoUnit.DAYS.between(start, end)` instead of summing the three getters.

```java
long elapsedDays = ChronoUnit.DAYS.between(start, end);
```

(Requires `import java.time.temporal.ChronoUnit;`.) `ChronoUnit.DAYS.between` returns the number of calendar days between two dates, which is suitable when you only need the total day difference rather than years/months/days.

## 7. Parsing and formatting `Period`

`Period.parse(String)` reads ISO-8601 strings, for example:

```java
Period p1 = Period.parse("P2Y3M4D");
Period p2 = Period.parse("P6M");
Period p3 = Period.parse("P10D");
Period negative = Period.parse("P-1Y-2M-3D");

System.out.println(p1);       // P2Y3M4D
System.out.println(p2);       // P6M
System.out.println(p3);       // P10D
System.out.println(negative); // P-1Y-2M-3D
```

`Period.toString()` produces the ISO representation of the three components. `P1Y2M10D` contains no start date, time zone, or instant; it only denotes a calendar amount. Do not confuse a period string with a timestamp like `2026-10-24T09:00:00Z`.

The parser also supports week amounts such as `P2W`; the factory `Period.ofWeeks(2)` converts to 14 days. `Period.parse` can throw `DateTimeParseException` on invalid syntax. When receiving input from an API, validate and handle errors rather than assuming every string is a valid period.

## 8. Operations on `Period`

Commonly used methods:

| Method | Result |
| --- | --- |
| `plus(other)` | Adds each corresponding component |
| `minus(other)` | Subtracts each component |
| `multipliedBy(n)` | Multiplies each component |
| `negated()` | Negates each component |
| `normalized()` | Normalizes total years/months, keeping the days part |
| `isZero()` | Checks whether all components are 0 |
| `isNegative()` | Checks whether the value is considered negative per the API contract |

Examples:

```java
Period base = Period.of(1, 2, 3);

System.out.println(base.plus(Period.ofMonths(2)));
// P1Y4M3D

System.out.println(base.minus(Period.ofDays(5)));
// P1Y2M-2D

System.out.println(base.multipliedBy(2));
// P2Y4M6D

System.out.println(base.negated());
// P-1Y-2M-3D

System.out.println(Period.ZERO.isZero()); // true
```

These operations act on the year/month/day components themselves, without adding or subtracting on a specific date. When applying a period with mixed-sign components (for example, positive years but negative days), the result can be hard to reason about by inspection; prefer building periods with clear rules and testing them against real start dates.

### Using `withDays`, `withMonths`, and `withYears`

If you need to replace a single component:

```java
Period p = Period.of(1, 2, 3);

System.out.println(p.withDays(10));   // P1Y2M10D
System.out.println(p.withMonths(6));  // P1Y6M3D
System.out.println(p.withYears(4));   // P4Y2M3D
System.out.println(p);               // P1Y2M3D
```

These methods return a new value without modifying `p`. Distinguish between "replace the months component with 6" and "add 6 months": `withMonths(6)` sets the component, whereas `plusMonths(6)` adds six months.

## 9. Notes on negative signs, normalization, and comparison

`Period` does not require all components to have the same sign. For example, `Period.of(1, -2, 3)` can still be created. `isNegative()` and `isZero()` are not general comparisons of total days, because a period has no total number of days independent of a start date. If you need to compare two periods to decide "which interval is longer", there is no universally accurate way when one period contains months/years without knowing the reference date.

For example, you cannot say `P1M` is always longer than `P28D`: from 2025-02-01, adding 1 month to 2025-03-01 is 28 days; from 2025-01-01, adding 1 month to 2025-02-01 is 31 days. To compare intervals by actual outcome, pick a clear start date, apply each period, and compare the resulting dates—or compute a `Duration` when full instants are available.

### Immutability does not mean operations are always reversible

Factory methods and operations return an immutable `Period`, but when applied to end-of-month dates, adding a month and then subtracting a month may not restore the original date. Immutability means the object itself is not mutated; it does not guarantee that every calendar operation is a perfect inverse.

For large amounts, multiplying or adding components can overflow the `int` range and throw `ArithmeticException`. Do not clamp results to a smaller number to avoid exceptions without an explicit business rule.

## 10. Standalone Java 17+ example

Create the file **`PeriodCalendarDemo.java`**:

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;

public class PeriodCalendarDemo {
    public static void main(String[] args) {
        Period p = Period.of(1, 14, 40);
        System.out.println("period = " + p);
        System.out.println("years = " + p.getYears());
        System.out.println("months = " + p.getMonths());
        System.out.println("days = " + p.getDays());
        System.out.println("normalized = " + p.normalized());

        LocalDate jan31Leap = LocalDate.of(2024, 1, 31);
        LocalDate jan31Normal = LocalDate.of(2025, 1, 31);
        System.out.println("2024 plus month = "
                + jan31Leap.plus(Period.ofMonths(1)));
        System.out.println("2025 plus month = "
                + jan31Normal.plus(Period.ofMonths(1)));
        System.out.println("2024 plus 30 days = "
                + jan31Leap.plusDays(30));

        LocalDate start = LocalDate.of(2024, 1, 31);
        LocalDate end = LocalDate.of(2024, 3, 2);
        Period between = Period.between(start, end);
        System.out.println("between = " + between);
        System.out.println("between days = "
                + ChronoUnit.DAYS.between(start, end));

        ZonedDateTime zoned = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0,
                ZoneId.of("America/New_York"));
        System.out.println("period one day = "
                + zoned.plus(Period.ofDays(1)));
        System.out.println("duration one day = "
                + zoned.plus(Duration.ofDays(1)));

        System.out.println("negative period = "
                + Period.parse("P-1Y-2M-3D"));
    }
}
```

Compile and run:

```bash
javac PeriodCalendarDemo.java
java PeriodCalendarDemo
```

Expected output on JDK 17+ with standard time-zone data:

```text
period = P1Y14M40D
years = 1
months = 14
days = 40
normalized = P2Y2M40D
2024 plus month = 2024-02-29
2025 plus month = 2025-02-28
2024 plus 30 days = 2024-03-01
between = P1M2D
between days = 31
period one day = 2024-03-10T12:00-04:00[America/New_York]
duration one day = 2024-03-10T13:00-04:00[America/New_York]
negative period = P-1Y-2M-3D
```

The output illustrates that `Period` preserves its components, `normalized()` only converts months into years, adding months adjusts end-of-month dates, and there is a difference between a calendar day and 86,400 seconds. The code uses fixed dates so it does not depend on the current time or default time zone.

## 11. Common mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Treating `Period.ofMonths(1)` as 30 days | Months have different lengths | Apply it to an actual date or preserve calendar rules |
| Assuming `Period.ofDays(1)` is always 24 hours | Across DST, a local day can be 23 or 25 hours | Use `Duration` for a fixed elapsed time |
| Calling `getDays()` to get the total days of a period | It only returns the days component without converting months/years | Use `ChronoUnit.DAYS.between(start, end)` when you need the number of days between two dates |
| Thinking `normalized()` also converts days into months | Months do not have a fixed number of days | Only years/months are normalized |
| Adding a month to the 31st and subtracting a month expecting the 31st back | The original date may have been clamped to the end of the month | Define explicit end-of-month rules |
| Using `equals()` to assert two periods give the same result on all dates | Representations can differ even when applying them to a given date yields the same result | Compare normalized values or the results when applied to specific dates |
| Directly comparing `P1M` and `P30D` to decide which period is larger | There is no single fixed length for a month | A start date and specific calendar are required |
| Assuming `Period` contains a time zone | It only holds years/months/days | Use `ZonedDateTime` or attach `ZoneId` at the business layer |
| Parsing arbitrary strings as ISO periods | Invalid syntax can throw an exception | Validate and handle `DateTimeParseException` |
| Treating immutability as meaning addition and subtraction are always reversible | End-of-month clamping discards the original day | Test calendar boundaries and define business rules |

## 12. Choosing `Period` for the right requirement

- **Monthly billing cycles:** store the cycle definition, start date, and the rule for when the billing day does not exist (e.g., the 31st in a 30-day month).
- **Age or anniversaries:** use calendar years/months/days; do not convert age into total seconds.
- **One-month renewal:** `date.plus(Period.ofMonths(1))`, with a clear rule for end-of-month dates.
- **Expiration in 30 × 24 hours:** use `Instant.plus(Duration.ofHours(720))` or a fixed duration; do not assume "1 month".
- **Business days:** `Period` has no knowledge of weekends, public holidays, or company schedules; an external business calendar is required.
- **Comparing two intervals by day count:** use specific start/end dates with `ChronoUnit.DAYS.between`, rather than inferring from period getters.

### Self-check questions

1. What does `Period.of(1, 14, 40).normalized()` return?  
   → `P2Y2M40D`; months are converted into years, while days remain unchanged.
2. Is `Period.ofMonths(1)` always equivalent to 30 days?  
   → No. The starting day, month, and year must be considered.
3. How does `Period.ofDays(1)` differ from `Duration.ofDays(1)`?  
   → One calendar day versus a fixed 86,400 seconds.
4. Is `Period.between(start, end).getDays()` the total number of days between two dates?  
   → No; it is only the days component after breaking the difference down into years/months/days.
5. Why can Jan 31 + 1 month − 1 month become Jan 28?  
   → Adding a month clamped the 31st to the last day of February; the "31" information is not retained in the resulting date.
6. Why can't the total lengths of `P1M` and `P30D` be compared in all cases?  
   → Months have varying numbers of days; a specific start date is required.
7. When a requirement specifies expiration after exactly 24 hours, what should you use?  
   → `Duration` on `Instant` or a timestamp, not `Period`.

### Official API documentation

- [Java SE 17 — `Period`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html): factories, components, normalization, arithmetic, parsing, and `between`.
- [Java SE 17 — `LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): month/year addition behavior and end-of-month adjustment.
- [Java SE 17 — `Duration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): second-based amount of time.
- [Java SE 17 — `ChronoUnit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html): measuring differences in time units.

**Key takeaway:** `Period` stores an amount of time in **calendar years, months, and days**, not a fixed total number of seconds or days. Choose `Period` for calendar-based requirements and `Duration` for fixed elapsed durations; the start date, leap years, end-of-month rules, and time-zone rules determine the actual result.
