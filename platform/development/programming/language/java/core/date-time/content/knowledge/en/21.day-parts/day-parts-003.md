# MonthDay for Yearless Anniversaries

## 1. A Recurring Day in a Year Differs from a Specific Date

“The anniversary is November 20” does not specify which year. This is the use case for `MonthDay`: a value consisting of **a month and a day of the month**, without a year, time, or time zone. Its standard text format is `--11-20`; the two leading hyphens indicate that the year part is absent.

Use `MonthDay` to store the month/day part of a birthday, a founding date, or a recurring annual Gregorian calendar milestone. Use `LocalDate` if you need to store the full date when an event occurred, such as an actual birth date for calculating age. Both types can appear together: store `LocalDate` as the source data, then extract `MonthDay.from(birthDate)` to match birthdays within a year.

| Data to Store | Suitable Type |
| --- | --- |
| November 20, without a year | `MonthDay` |
| November 20, 1995 | `LocalDate` |
| November 2025, without a day | `YearMonth` |
| An actual instant to send a greeting | Requires a date, time, and time zone |

`MonthDay` belongs to the ISO calendar, is immutable, and is thread-safe. It does not by itself represent lunar holidays, “the first Monday of the month”, or an absolute instant. [MonthDay](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/MonthDay.html)

## 2. Creating, Reading, and Converting

Illustrative snippet inside a method:

```java
MonthDay anniversary = MonthDay.of(11, 20);
MonthDay same = MonthDay.of(java.time.Month.NOVEMBER, 20);
MonthDay parsed = MonthDay.parse("--11-20");
MonthDay fromDate = MonthDay.from(LocalDate.of(1995, 11, 20));

int monthNumber = anniversary.getMonthValue(); // 11, not a 0-based index.
java.time.Month month = anniversary.getMonth();
int day = anniversary.getDayOfMonth();        // 20.
LocalDate in2025 = anniversary.atYear(2025);   // 2025-11-20.
```

`of` validates the existence of the month/day pair: month 13 or April 31 is invalid and throws `DateTimeException`. `parse` rejects malformed strings or invalid month/day pairs; a string parsing error is a `DateTimeParseException`.

You can display `dd/MM` using an appropriate `DateTimeFormatter`. However, do not put a year into the pattern and expect `MonthDay` to have a year for formatting. When exchanging data, the `--MM-dd` format conveys the absence of a year more clearly than a full date with a dummy year.

## 3. February 29 Is Valid in MonthDay

`MonthDay.of(2, 29)` is valid because no year has been chosen yet. February 30 remains invalid: no ISO year contains that date.

Once a year is chosen, three behaviors must be distinguished:

| Operation on `--02-29` | Leap Year 2024 | Common Year 2025 |
| --- | --- | --- |
| `isValidYear(year)` | `true` | `false` |
| `atYear(year)` | `2024-02-29` | `2025-02-28` |
| Requirement to keep exact Feb 29 | Corresponding date exists | No corresponding date |

`atYear` **adjusts February 29 to February 28** when needed, without throwing an error just because the year is not a leap year. If the system must skip common years or shift to March 1, a dedicated business rule is required.

The ISO leap year rule is divisible by 4, except for century years not divisible by 400. Therefore, 2100 is not a leap year while 2000 is. Do not find the next February 29 by always adding 4 to the year. [Year.isLeap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Year.html#isLeap(long))

The policy for a February 29 birthday is an application choice or a specific business requirement; the library's default behavior does not by itself establish a legal rule about birth dates or age.

## 4. Matching an Anniversary Today

The basic idea is to strip the year from today and compare values:

```java
MonthDay anniversary = MonthDay.of(11, 20);
LocalDate today = LocalDate.of(2025, 11, 20);
boolean isAnniversary = anniversary.equals(MonthDay.from(today)); // true.
```

This approach matches the **exact month/day**, so a February 29 birthday will not match any day in a common year. If the business logic has a fallback policy, compute the actual date for that year according to the policy and compare it against `today`.

“Today” depends on the time zone. In a real application, obtain `LocalDate.now(clock)` from a `Clock` with an explicit business time zone; passing the clock in makes it possible to test scenarios near midnight and year-end. `MonthDay.now()` implicitly uses the default clock/time zone, so you should not hide that choice in a job that sends greetings across multiple regions. [Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)

## 5. Computing the Next Occurrence with an Explicit Feb 29 Policy

The program below supports three rules: shifting to Feb 28, shifting to Mar 1, or accepting only Feb 29 itself. “Next occurrence” is defined **inclusively of today**. The method returns `LocalDate`, because once a year is chosen we have a concrete date.

Save as `AnniversaryDemo.java`:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.Year;
import java.util.Objects;
import java.util.Optional;

public class AnniversaryDemo {
    enum LeapPolicy { FEBRUARY_28, MARCH_1, LEAP_YEARS_ONLY }

    static Optional<LocalDate> occurrence(
            MonthDay anniversary, int year, LeapPolicy policy) {
        Objects.requireNonNull(anniversary, "anniversary");
        Objects.requireNonNull(policy, "policy");
        Year.of(year); // Validate that the year is within the valid representable range.
        if (anniversary.isValidYear(year)) {
            return Optional.of(anniversary.atYear(year));
        }
        // For a valid MonthDay, the remaining case is Feb 29 in a common year.
        return switch (policy) {
            case FEBRUARY_28 -> Optional.of(LocalDate.of(year, 2, 28));
            case MARCH_1 -> Optional.of(LocalDate.of(year, 3, 1));
            case LEAP_YEARS_ONLY -> Optional.empty();
        };
    }

    static LocalDate nextOccurrence(
            MonthDay anniversary, LocalDate today, LeapPolicy policy) {
        Objects.requireNonNull(today, "today");
        for (int year = today.getYear(); year <= Year.MAX_VALUE; year++) {
            Optional<LocalDate> candidate = occurrence(anniversary, year, policy);
            if (candidate.isPresent() && !candidate.get().isBefore(today)) {
                return candidate.get();
            }
        }
        throw new DateTimeException("No representable next occurrence");
    }

    public static void main(String[] args) {
        MonthDay anniversary = MonthDay.parse("--02-29");
        LocalDate today = LocalDate.of(2025, 2, 28);

        System.out.println("anniversary=" + anniversary);
        System.out.println("valid2024=" + anniversary.isValidYear(2024));
        System.out.println("valid2025=" + anniversary.isValidYear(2025));
        System.out.println("default2025=" + anniversary.atYear(2025));
        System.out.println("februaryPolicy="
                + nextOccurrence(anniversary, today, LeapPolicy.FEBRUARY_28));
        System.out.println("marchPolicy="
                + nextOccurrence(anniversary, today, LeapPolicy.MARCH_1));
        System.out.println("leapOnly="
                + nextOccurrence(anniversary, today, LeapPolicy.LEAP_YEARS_ONLY));
        System.out.println("afterMarch=" + nextOccurrence(anniversary,
                LocalDate.of(2025, 3, 2), LeapPolicy.FEBRUARY_28));
        System.out.println("ordinary=" + nextOccurrence(MonthDay.of(11, 20),
                LocalDate.of(2025, 12, 31), LeapPolicy.LEAP_YEARS_ONLY));
        System.out.println("adjustedMonth=" + MonthDay.of(1, 31).withMonth(4));
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac -encoding UTF-8 --release 17 AnniversaryDemo.java
java AnniversaryDemo
```

Exact stdout:

```text
anniversary=--02-29
valid2024=true
valid2025=false
default2025=2025-02-28
februaryPolicy=2025-02-28
marchPolicy=2025-03-01
leapOnly=2028-02-29
afterMarch=2026-02-28
ordinary=2026-11-20
adjustedMonth=--04-30
```

The method iterates starting from the current year: if the date has already passed, it checks the following year; if the policy accepts leap years only, it skips years that have no corresponding date. Thus it handles both year-end rollovers and non-leap century years.

The error branch at the year limit avoids assuming there is always a future result within `LocalDate`'s representable range. If you want “strictly after today”, change the condition to `candidate.get().isAfter(today)`; there is no need to add one day to `today`, which could overflow when `today` is `LocalDate.MAX`.

## 6. Adjusting and Comparing: Common Misconceptions

### Immutability and the End-of-Month Rule

`withMonth`/`withDayOfMonth` returns a new result. Changing the month of `--01-31` to April yields `--04-30`, because day 31 does not exist in the new month. Conversely, requesting `MonthDay.of(4, 30).withDayOfMonth(31)` directly is invalid and throws `DateTimeException`.

Therefore, validating input data with `of` is different from adjusting an existing value with `withMonth`; do not use an adjusted result as proof that the original input was valid.

### Order Within a Year Is Not Distance to the Next Occurrence

`compareTo`, `isBefore`, and `isAfter` compare by month then day. `--01-01` comes before `--12-31`, yet if today is December 31, the next January 1 is only one day away. To count the remaining days, first compute the `LocalDate` of the next occurrence, then use `ChronoUnit.DAYS.between(today, next)`.

### No General Day Addition

`MonthDay` implements `TemporalAccessor` and `TemporalAdjuster`, but does not implement `Temporal`; it has no `plusDays`. To add days, determine the year using an explicit policy and then work with `LocalDate`. Do not use casting or tricks to turn a month/day into a full date.

### Using as an Adjuster

For an ISO date, `date.with(monthDay)` sets the month/day part while keeping the year, adjusting when Feb 29 does not exist. For example, `LocalDate.of(2025, 8, 1).with(MonthDay.of(2, 29))` produces `2025-02-28`. It does not automatically pick “the next anniversary”: the result can fall before `date`. [LocalDate.with](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#with(java.time.temporal.TemporalAdjuster))

## 7. Checklist Before Using for Reminder Schedules

- Preserve the true meaning of the data: do not invent 1970 or 2000 as a dummy year and accidentally treat it as an actual birth date.
- Explicitly define the Feb 29 policy and whether today counts as the next occurrence.
- Test year-end boundaries, common years, leap years, century years such as 2100, and the anniversary day itself.
- If sending notifications at a specific hour, add the time and time zone after determining the date; `MonthDay` does not schedule jobs or prevent duplicate sends on its own.

To use lunar dates or specific religious rules, an appropriate calendar/conversion model is needed; an ISO month/day pair does not store enough information for those rules.

## 8. Self-Practice

1. Extract `MonthDay` from `LocalDate.of(2000, 7, 10)` and attach it to year 2026.
2. Given anniversary Feb 29 and today March 1, 2096, find the next occurrence under `LEAP_YEARS_ONLY`.
3. Replace the method's rule with a condition that only accepts dates strictly after today and test on the anniversary day itself.
4. Calculate the number of days remaining until January 1 when today is December 31, 2025.

Answers: (1) `--07-10`, then `2026-07-10`; (2) `2104-02-29`, because 2100 is not a leap year; (3) use `isAfter` comparison; (4) target date `2026-01-01`, distance 1 day.