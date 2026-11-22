# Year and Leap Year Validation

## 1. Year represents a year, not a full date

Among the types that represent individual parts of a date, `java.time.Year` is used when the data only needs **a year in the ISO calendar**, such as a reporting year, graduation year, or a year to check for leap-year status. It does not contain a month, day, time, or time zone.

Using `Year.of(2024)` clearly expresses "the year 2024". There is no need to create a dummy date such as January 1, 2024 just to carry the year part if the business domain does not have that date.

There are three different questions to separate:

| Question | Example | Appropriate API |
| --- | --- | --- |
| Is the year number within the representable range of `Year`? | 2024 is within range; 1,000,000,000 is not | `Year.of(number)` validates upon creation |
| Is that year a leap year? | 2024 is a leap year, 2023 is not | `year.isLeap()` or `Year.isLeap(number)` |
| Does a month-day exist in that year? | February 29 is valid in 2024 but not in 2023 | `year.isValidMonthDay(monthDay)` |

A **non-leap year is still a valid year**. A `false` result from `isLeap` does not mean the year data is invalid. Conversely, a number that satisfies the divisibility rules for a leap year is not necessarily within the range where a `Year` object can be created.

This lesson focuses on creating `Year`, determining leap years, and validating year-dependent dates. Historical rules of individual countries or lunar calendars do not belong to this model.

## 2. Creating and reading a Year

| Call | Meaning |
| --- | --- |
| `Year.of(2024)` | Creates a year from an integer, with range validation |
| `Year.parse("2024")` | Parses a year from a string using the default format |
| `Year.from(localDate)` | Extracts the year from an existing ISO date |
| `year.getValue()` | Gets the year number as an `int` |
| `year.plusYears(1)` | Creates the next year |
| `year.minusYears(1)` | Creates the previous year |

`Year` is immutable. If `year` is 2024, calling `year.plusYears(1)` returns 2025; the original variable and year object still hold the value 2024 unless reassigned.

The supported range is `Year.MIN_VALUE` to `Year.MAX_VALUE`, which is from -999,999,999 to +999,999,999. `Year.of` rejects out-of-range values with a `DateTimeException`. For string input, a parsing error throws `DateTimeParseException`; do not confuse a string parsing error with a "not a leap year" result.

In addition to Java's technical range, an application may have a narrower business range, such as only accepting years within a specific period. That constraint must be validated separately; `Year.of` does not know the year limits of a form.

`Year.now()` gets the current year according to the default clock and time zone. Because real time changes, the verification examples below use fixed years so that results do not depend on the execution date. When testing a "current year" feature, you can pass a deterministic `Clock` to `Year.now(clock)`; the resulting `Year` itself still does not store a time zone.

## 3. Leap year rules and two ways to call isLeap

The ISO/Gregorian calendar rules applied in this lesson:

1. A year divisible by 400 is a leap year.
2. Otherwise, a year divisible by 100 is not a leap year.
3. If not excluded by the century rule, a year divisible by 4 is a leap year.
4. All other years are not leap years.

This can be expressed as the condition:

```text
divisible by 4 AND (not divisible by 100 OR divisible by 400)
```

In application code, prefer `Year.isLeap` instead of duplicating the formula in multiple places. The formula helps explain the logic and choose test cases, not justify building another calendar library.

| Year | Divisible by 4? | Divisible by 100? | Divisible by 400? | Conclusion |
| --- | --- | --- | --- | --- |
| 2023 | No | No | No | Common year |
| 2024 | Yes | No | No | Leap year |
| 1900 | Yes | Yes | No | Common year |
| 2000 | Yes | Yes | Yes | Leap year |
| 2100 | Yes | Yes | No | Common year |
| 2400 | Yes | Yes | Yes | Leap year |

Testing only 2023 and 2024 is not enough to catch the "divisible by 4 is a leap year" bug. Cases like 1900 or 2100 catch a missing century-year exception; case 2000 catches mistakenly excluding all years divisible by 100.

Two common ways to call it:

- When you already have an object: `Year.of(2024).isLeap()`.
- When you only need the result from a year number: `Year.isLeap(2024)`.

The static form takes a `long` parameter. It evaluates the leap-year rule and does not serve to create or validate the range of a `Year` object. For example, `Year.isLeap(1_000_000_000L)` returns `true`, whereas `Year.of(1_000_000_000)` reports out of range. If the input needs to become a `Year`, validate it through the object creation step rather than using the `isLeap` result as a substitute.

`Year.length()` returns 366 in a leap year and 365 in a common year. This is the **number of calendar days**, not a guarantee of the number of seconds in the year in a specific time zone. The capabilities of the class are described in [Year](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Year.html).

## 4. Validating February 29 with Year and MonthDay

`MonthDay` represents a month and day without a year attached. `MonthDay.of(2, 29)` is a valid value because February 29 exists in some years. However, it is not yet a complete date.

Once the year is known, `year.isValidMonthDay(monthDay)` checks whether those two components combine into a real date:

| Year | Month-day | Result |
| --- | --- | --- |
| 2024 | February 29 | `true` |
| 2023 | February 29 | `false` |
| 1900 | February 29 | `false` |
| 2000 | February 29 | `true` |
| 2023 | February 28 | `true` |
| 2024 | December 31 | `true` |

You cannot create `MonthDay.of(4, 31)` and then ask which year accepts it: April 31 does not exist in any year, so creating `MonthDay` already throws an error.

This creates two layers of validation:

1. **Can the month-day possibly exist?** `MonthDay` validates this structure.
2. **Does it exist in the year under consideration?** `Year.isValidMonthDay` adds the year context.

Knowing `year.isLeap() == true` alone is not enough to conclude that every date in the year is valid. The year 2024 is a leap year, yet it still does not have February 30 or April 31. See how month-days are represented in [MonthDay](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/MonthDay.html).

## 5. Validation vs. automatic adjustment

This is the most important point when using the result to validate data.

`Year.atMonthDay` creates a date from a year and a month-day. If the month-day is February 29 but the year is not a leap year, the method **automatically falls back to February 28**. Similarly, `MonthDay.of(2, 29).atYear(2023)` produces February 28, 2023.

| Expression | Result |
| --- | --- |
| `Year.of(2023).isValidMonthDay(MonthDay.of(2, 29))` | `false` |
| `Year.of(2023).atMonthDay(MonthDay.of(2, 29))` | `2023-02-28` |
| `MonthDay.of(2, 29).atYear(2023)` | `2023-02-28` |
| `Year.of(2023).atMonth(2).atDay(29)` | `DateTimeException` |
| `LocalDate.of(2023, 2, 29)` | `DateTimeException` |

Therefore, "successfully creating a date" does not mean "the original input date is valid" if an adjusting API is being used.

The choice depends on the requirements:

- **To reject February 29 in a common year:** check `isValidMonthDay` and reject if false, or use strict date creation such as `LocalDate.of`.
- **To fall back an anniversary date to February 28:** you may use `atMonthDay` if that is the established policy.
- **To shift to March 1:** you must implement a custom rule; do not expect that behavior from `atMonthDay`.

In the example below, the `strictDate` method proactively validates before combining. When the input is February 29 of a common year, the method throws an error instead of silently changing it to February 28.

## 6. From Year to other parts of a date

`Year` can serve as a starting point to add information at the right level of granularity:

| Combination | Result | Meaning |
| --- | --- | --- |
| `year.atMonth(Month.FEBRUARY)` | `YearMonth` | Year-month, without a day |
| `year.atMonth(2).atDay(29)` | `LocalDate` if valid | Selects a specific day in February |
| `year.atMonthDay(monthDay)` | `LocalDate` | Combines month-day, with the February 29 fallback rule |
| `year.atDay(dayOfYear)` | `LocalDate` | Combines the day-of-year ordinal number |

If you only need to check a day number in a specific month, `year.atMonth(2).isValidDay(29)` is a way to validate without creating a full date. `YearMonth` has both year and month to evaluate month length and day validity; see [YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html).

Be careful with the parameter name of `atDay`: in `Year.atDay`, it is the **day of the year**, not the day of the month.

| Expression | Result |
| --- | --- |
| `Year.of(2024).atDay(60)` | `2024-02-29` |
| `Year.of(2023).atDay(60)` | `2023-03-01` |
| `Year.of(2024).atDay(366)` | `2024-12-31` |
| `Year.of(2023).atDay(366)` | `DateTimeException` |

Adding a leap day shifts the day-of-year ordinal numbers for all dates after February. If your data represents a fixed day of a month, do not convert it into a day-of-year number and apply that same number across all years.

## 7. Complete Java 17+ verification program

Save the entire code below into `YearLeapValidation.java`. The program requires no external libraries and does not depend on the current year.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Month;
import java.time.MonthDay;
import java.time.Year;
import java.util.Objects;

public class YearLeapValidation {
    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (DateTimeException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Expected DateTimeException");
    }

    private static LocalDate strictDate(Year year, MonthDay monthDay) {
        Objects.requireNonNull(year, "year");
        Objects.requireNonNull(monthDay, "monthDay");
        if (!year.isValidMonthDay(monthDay)) {
            throw new DateTimeException("Invalid month-day for year " + year);
        }
        return year.atMonthDay(monthDay);
    }

    public static void main(String[] args) {
        Year leap = Year.of(2024);
        Year common = Year.of(2023);
        MonthDay feb29 = MonthDay.of(2, 29);
        eq(Year.parse("2024"), leap);
        eq(Year.from(LocalDate.of(2024, 12, 31)), leap);
        eq(leap.getValue(), 2024);
        eq(leap.isLeap(), true);
        eq(common.isLeap(), false);
        eq(Year.isLeap(1900), false);
        eq(Year.isLeap(2000), true);
        eq(Year.isLeap(2100), false);
        eq(Year.isLeap(2400), true);
        eq(leap.length(), 366);
        eq(common.length(), 365);
        eq(leap.isValidMonthDay(feb29), true);
        eq(common.isValidMonthDay(feb29), false);
        eq(common.isValidMonthDay(MonthDay.of(2, 28)), true);
        eq(strictDate(leap, feb29), LocalDate.of(2024, 2, 29));
        rejects(() -> strictDate(common, feb29));
        eq(common.atMonthDay(feb29), LocalDate.of(2023, 2, 28));
        eq(feb29.atYear(2023), LocalDate.of(2023, 2, 28));
        rejects(() -> common.atMonth(Month.FEBRUARY).atDay(29));
        rejects(() -> LocalDate.of(2023, 2, 29));
        rejects(() -> MonthDay.of(4, 31));

        eq(leap.atDay(60), LocalDate.of(2024, 2, 29));
        eq(common.atDay(60), LocalDate.of(2023, 3, 1));
        eq(leap.atDay(366), LocalDate.of(2024, 12, 31));
        rejects(() -> common.atDay(366));
        eq(leap.plusYears(1), Year.of(2025));
        eq(leap, Year.of(2024));
        eq(Year.isLeap(0), true);
        eq(Year.isLeap(-4), true);
        eq(Year.of(Year.MIN_VALUE).getValue(), Year.MIN_VALUE);
        eq(Year.of(Year.MAX_VALUE).getValue(), Year.MAX_VALUE);
        rejects(() -> Year.of(Year.MAX_VALUE + 1));
        rejects(() -> Year.of(Year.MIN_VALUE - 1));
        eq(Year.isLeap(1_000_000_000L), true);
        rejects(() -> Year.of(1_000_000_000));

        int leapCount = 0;
        for (int number = 2000; number < 2400; number++) {
            Year year = Year.of(number);
            boolean hasFeb29 = year.atMonth(Month.FEBRUARY).isValidDay(29);
            eq(year.isLeap(), hasFeb29);
            eq(year.length(), year.isLeap() ? 366 : 365);
            if (year.isLeap()) {
                leapCount++;
            }
        }
        eq(leapCount, 97);

        for (int number : new int[] {1900, 2000, 2023, 2024, 2100}) {
            Year year = Year.of(number);
            System.out.println("year=" + year + " leap=" + year.isLeap()
                    + " days=" + year.length()
                    + " feb29=" + year.isValidMonthDay(feb29));
        }
        System.out.println("adjusted=" + common.atMonthDay(feb29));
        System.out.println("day60Leap=" + leap.atDay(60));
        System.out.println("day60Common=" + common.atDay(60));
        System.out.println("leapYearsIn400Years=" + leapCount);
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 YearLeapValidation.java
java YearLeapValidation
```

Stdout:

```text
year=1900 leap=false days=365 feb29=false
year=2000 leap=true days=366 feb29=true
year=2023 leap=false days=365 feb29=false
year=2024 leap=true days=366 feb29=true
year=2100 leap=false days=365 feb29=false
adjusted=2023-02-28
day60Leap=2024-02-29
day60Common=2023-03-01
leapYearsIn400Years=97
PASS checks=836
```

The `eq` method explicitly throws `AssertionError` when a result is wrong; the `-ea` flag is not needed. The `rejects` method verifies that operations must throw `DateTimeException`; if an operation silently accepts the input, the program fails.

The loop from year 2000 through 2399 checks consistency between the leap-year conclusion, year length, and whether February has a 29th day. In a 400-year cycle there are 97 leap years: multiples of 4 are included, multiples of 100 are excluded, and then multiples of 400 are included again. The total count of 97 complements the individual test cases and shows why you cannot replace the rule with "every four years always has exactly one leap year" across any calendar span.

Specific date cases such as 1900, 2000, and 2100 are still necessary: merely checking that APIs within the same library agree with each other does not replace verifying the expected results for each rule group.

## 8. Year 0, negative years, and historical limits

`Year` uses the ISO extended year numbering system: there is a year 0 before year 1, followed by year -1. The leap-year rule is applied consistently along that year axis. In the program, both year 0 and year -4 evaluate as leap years.

This does not mean every country in history used that exact numbering and rule at every point in time. It is the ISO calendar model extended backward into the past, commonly called the proleptic Gregorian calendar.

If an application processes historical records from before a region's calendar transition, you must determine the actual calendar system of the data. Do not use `Year.isLeap` results to assert historical dates for every country without context. For modern year data following the ISO calendar, these APIs provide the appropriate model.

There is no need to forbid year 0 or negative years just because they look different from modern years, unless a business constraint specifies otherwise.

## 9. Common mistakes

- **Using `year % 4 == 0` as the entire rule:** misses the century-year exception. Use `Year.isLeap` and include cases for 1900/2000/2100.
- **Assuming a non-leap year is an invalid year:** 2023 is completely valid; it simply does not have February 29.
- **Using `Year.isLeap` to validate the range of `Year`:** the static form takes `long` and does not replace the `Year` creation step.
- **Using `atMonthDay` to validate input:** the method can fall back February 29 to February 28. Choose a validation API or strict date creation if rejection is required.
- **Assuming `MonthDay.of(2, 29)` alone is enough:** a year is also needed to determine a complete date.
- **Confusing `Year.atDay(29)` with February 29:** that method selects the 29th day of the year, which is January 29.
- **Hardcoding year length as 365:** use `year.length()` when counting days in a specific year.
- **Ignoring the return value of `plusYears`:** `Year` is immutable; store or return the new value.
- **Automatically altering an invalid date so data is accepted:** only adjust dates when it matches the business policy; validation and adjustment are two separate concerns.

## 10. Practice with guided answers

1. **Check the years 2200 and 2400.** 2200 is not a leap year because it is divisible by 100 but not by 400; 2400 is a leap year. Both can be used to create `Year` objects.

2. **A form receives February 29 and the year 2100.** If the requirement is to reject non-existent dates, `isValidMonthDay` must return `false` and the form must report invalid data. Do not call `atMonthDay` and save February 28 as if the user had entered that date.

3. **Compare the 60th day of 2023 and 2024.** The results are March 1, 2023 and February 29, 2024. Explain why a day-of-year ordinal number does not guarantee the same month-day across years.

4. **Data only has the reporting year 2025.** Represent it with `Year.of(2025)` if month/day are not yet available; there is no need to create `LocalDate.of(2025, 1, 1)` to stand in for unprovided information.

5. **Check the year number 1,000,000,000.** The leap-year result from the static method is `true`, but creating a `Year` must be rejected as out of range. State clearly the two questions that the two APIs are answering.

When validating year-dependent dates, follow the right order: validate the year range, determine the leap-year rule when needed, and then validate the specific month-day. Only after that should you choose whether to reject the input or adjust it according to an established policy.
