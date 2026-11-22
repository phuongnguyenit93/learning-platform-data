# Leap Years, Days in a Month, and Invalid Dates

A calendar date is valid only when **the year, month, and day are consistent with each other**. For example, February does not always have 29 days; the 31st does not exist in some months; and month 13 does not exist. Java provides the `java.time` API to validate these rules directly, avoiding the need to maintain a manual condition table.

This lesson belongs to the time foundations of **Java core – date-time**, focusing on the ISO/Gregorian calendar, how to determine leap years, the number of days in a month, invalid dates, and how to handle them in Java 17+.

## 1. Leap Year Rules

Under the **Gregorian calendar**, a year is a leap year when:

1. The year is **divisible by 400**; or
2. The year is **divisible by 4 but not divisible by 100**.

Expressed as a Boolean expression:

```java
boolean leap = year % 400 == 0
        || (year % 4 == 0 && year % 100 != 0);
```

A common year has **365 days**; a leap year has **366 days** due to the extra day **February 29 (29/02)**. Checking only `year % 4 == 0` will be wrong for century years not divisible by 400.

| Year | Divisible by 4? | Divisible by 100? | Divisible by 400? | Result |
| --- | --- | --- | --- | --- |
| 1896 | Yes | No | No | Leap |
| 1900 | Yes | Yes | No | Not leap |
| 2000 | Yes | Yes | Yes | Leap |
| 2024 | Yes | No | No | Leap |
| 2025 | No | No | No | Not leap |
| 2100 | Yes | Yes | No | Not leap |

Java has built-in APIs to determine leap years; for practical problems, prefer them:

```java
System.out.println(Year.isLeap(1900));          // false
System.out.println(Year.isLeap(2000));          // true
System.out.println(Year.of(2024).isLeap());     // true
System.out.println(YearMonth.of(2024, 2).isLeapYear()); // true
```

The lines above are an **illustrative snippet**, which must be placed inside a Java method and import `java.time.Year` and `java.time.YearMonth`. `Year.isLeap(long)` and `YearMonth.isLeapYear()` use ISO rules with the *proleptic* Gregorian calendar, meaning Gregorian rules are applied consistently even when considering years before this calendar was historically adopted. That is useful for machine computation; do not confuse it with simulating every historical local calendar.

## 2. How Many Days Does a Month Have?

| Month | Number of days |
| --- | --- |
| 1 – January | 31 |
| 2 – February | 28 in a common year; **29 in a leap year** |
| 3 – March | 31 |
| 4 – April | 30 |
| 5 – May | 31 |
| 6 – June | 30 |
| 7 – July | 31 |
| 8 – August | 31 |
| 9 – September | 30 |
| 10 – October | 31 |
| 11 – November | 30 |
| 12 – December | 31 |

Because February depends on the year, **the year and month must be considered together**. The `YearMonth` class expresses this exact meaning:

```java
YearMonth feb2023 = YearMonth.of(2023, 2);
YearMonth feb2024 = YearMonth.of(2024, 2);

System.out.println(feb2023.lengthOfMonth()); // 28
System.out.println(feb2024.lengthOfMonth()); // 29
System.out.println(feb2024.atEndOfMonth());  // 2024-02-29

LocalDate april = LocalDate.of(2024, 4, 15);
System.out.println(april.lengthOfMonth());   // 30
```

This is an illustrative snippet requiring imports for `YearMonth` and `LocalDate`. `lengthOfMonth()` gets the number of days in that exact month/year. `atEndOfMonth()` returns the last day of the month as a `LocalDate`; it is very suitable for period closing, payment due dates, or month-end reporting logic.

`Month.FEBRUARY.length(true)` returns 29 and `Month.FEBRUARY.length(false)` returns 28, but calling this API requires you to **compute the leap year flag yourself correctly**. For specific year–month input, `YearMonth.of(year, month).lengthOfMonth()` is easier to use and less error-prone.

## 3. Valid Dates and Invalid Dates

For the ISO calendar, a triple of integers `(year, month, day)` forms a valid date if:

- `year` is within the range supported by `LocalDate`: from **−999,999,999** to **+999,999,999**.
- `month` is between **1 and 12**.
- `day` is between **1 and the number of days in that month in that year**, i.e., `YearMonth.of(year, month).lengthOfMonth()`.

You cannot just check `1 <= day && day <= 31`: February does not have day 30/31, April does not have day 31, and February 29 only appears in leap years.

| ISO Date | Valid? | Explanation |
| --- | --- | --- |
| `2024-02-29` | Yes | 2024 is a leap year |
| `2023-02-29` | No | February 2023 only has 28 days |
| `1900-02-29` | No | 1900 is divisible by 100, not divisible by 400 |
| `2000-02-29` | Yes | 2000 is divisible by 400 |
| `2024-04-30` | Yes | April has 30 days |
| `2024-04-31` | No | April does not have day 31 |
| `2024-00-10` | No | There is no month 0 |
| `2024-13-01` | No | There is no month 13 |
| `2024-01-00` | No | There is no day 0 |
| `2024-12-31` | Yes | Last day of December |

### Using `LocalDate.of` to Let Java Validate

```java
LocalDate valid = LocalDate.of(2024, 2, 29); // succeeds
LocalDate invalid = LocalDate.of(2023, 2, 29); // DateTimeException
```

The second line intentionally demonstrates an error; it will throw `java.time.DateTimeException` and must be handled if you want the program to continue running. `LocalDate.of` does not automatically roll an invalid date into another date. Therefore, constructing a `LocalDate` is a clear way to verify that a date exists without rewriting calendar algorithms.

If an API contract requires a `boolean` result, you can wrap the date construction:

```java
public static boolean isValidDate(int year, int month, int day) {
    try {
        LocalDate.of(year, month, day);
        return true;
    } catch (DateTimeException ex) {
        return false;
    }
}
```

This is a **method placed inside a Java class**, requiring imports for `java.time.LocalDate` and `java.time.DateTimeException`. It returns `false` for any year, month, or day outside the allowed range. If the application needs specific messages such as "invalid month" or "February of this year only has 28 days", classify the error according to the business contract after validating the input; avoid creating a mechanism that accepts dates differing from `java.time`.

## 4. Compilable and Runnable Java 17+ Example

Create a file named **`DateValidityDemo.java`** with the following content:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Year;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;

public class DateValidityDemo {
    public static void main(String[] args) {
        for (int year : new int[] {1900, 2000, 2024, 2025}) {
            System.out.printf("%d | leap=%s | February=%d%n",
                    year, Year.isLeap(year), YearMonth.of(year, 2).lengthOfMonth());
        }

        checkDate(2024, 2, 29);
        checkDate(2023, 2, 29);
        checkDate(2024, 4, 31);
        checkDate(2024, 0, 10);

        DateTimeFormatter strict = new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM-dd")
                .toFormatter()
                .withResolverStyle(ResolverStyle.STRICT);

        checkIso("2024-02-29", strict);
        checkIso("2023-02-29", strict);
    }

    private static void checkDate(int year, int month, int day) {
        try {
            LocalDate date = LocalDate.of(year, month, day);
            System.out.printf("%04d-%02d-%02d: VALID (%s)%n",
                    year, month, day, date);
        } catch (DateTimeException ex) {
            System.out.printf("%04d-%02d-%02d: INVALID%n",
                    year, month, day);
        }
    }

    private static void checkIso(String text, DateTimeFormatter formatter) {
        try {
            LocalDate date = LocalDate.parse(text, formatter);
            System.out.printf("%s (STRICT parse): VALID (%s)%n", text, date);
        } catch (DateTimeException ex) {
            System.out.printf("%s (STRICT parse): INVALID%n", text);
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac DateValidityDemo.java
java DateValidityDemo
```

**Expected stdout:**

```text
1900 | leap=false | February=28
2000 | leap=true | February=29
2024 | leap=true | February=29
2025 | leap=false | February=28
2024-02-29: VALID (2024-02-29)
2023-02-29: INVALID
2024-04-31: INVALID
2024-00-10: INVALID
2024-02-29 (STRICT parse): VALID (2024-02-29)
2023-02-29 (STRICT parse): INVALID
```

**Execution flow explanation:**

1. `Year.isLeap(year)` determines whether a year is a leap year, and `YearMonth.of(year, 2).lengthOfMonth()` gets the number of days in February.
2. `checkDate` attempts to construct a `LocalDate` from three numbers; valid values are printed, while invalid values enter `catch (DateTimeException)`.
3. `checkIso` parses a string using a `STRICT` formatter; non-existent dates are rejected.
4. The program prints the `INVALID` label instead of printing the exception message, because the JDK error message text is not a stable interface to match against in examples.

## 5. Parsing Strings: Correct Format Is Not Enough

A string like `"2023-02-29"` has the right **year-month-day** structure yet still **does not exist** in the calendar. Input from forms, JSON, CSV, or APIs needs to be validated for both syntax and semantics.

For simple ISO strings:

```java
LocalDate.parse("2024-02-29"); // returns LocalDate for 2024-02-29
LocalDate.parse("2023-02-29"); // DateTimeParseException
```

`LocalDate.parse(text)` uses the ISO local date formatter with strict resolution by default. `DateTimeParseException` is a subclass of `DateTimeException`.

When an application needs a custom pattern formatter, explicitly specify `ResolverStyle.STRICT` if **rejecting** non-existent dates is required:

```java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate.parse("2024-02-29", strict); // succeeds
LocalDate.parse("2023-02-29", strict); // DateTimeParseException
```

The resolver modes have different meanings:

| Mode | Typical behavior |
| --- | --- |
| `STRICT` | Requires date fields to form a valid date; rejects 2023-02-29 |
| `SMART` | May adjust days past the end of the month, e.g., 2023-02-29 becomes 2023-02-28 |
| `LENIENT` | May allow day/month overflow to roll over into other days or months |

`DateTimeFormatter.ofPattern(...)` defaults to the **`SMART`** resolver style, so a custom formatter must not be assumed to be `STRICT` unless configured.

Pattern symbols must be distinguished:

- **`uuuu`**: proleptic year, suitable when parsing ISO `LocalDate` dates with `STRICT` without requiring an era.
- **`yyyy`**: year-of-era. When using `STRICT` and the string does not provide an era, there may be insufficient data to resolve into a `LocalDate`. For pure ISO dates, prefer `uuuu-MM-dd`.
- **`MM`** is month, **`mm`** is minute. **`YYYY`** is week-based-year, not the ordinary calendar year.
- If you also want to reject strings with a different pattern (for example, `"2024/02/29"` against pattern `uuuu-MM-dd`), use the exact chosen formatter and handle `DateTimeParseException`.

## 6. Creating an Invalid Date vs. Adding/Subtracting Months and Years

`LocalDate.of(2025, 2, 29)` is an **invalid date**. However, `LocalDate.plusYears` and `plusMonths` have adjustment rules when the original day does not exist in the target month/year:

```java
System.out.println(LocalDate.of(2024, 2, 29).plusYears(1));  // 2025-02-28
System.out.println(LocalDate.of(2024, 1, 31).plusMonths(1)); // 2024-02-29
```

That adjustment serves **date arithmetic**, and does not prove that the input `2025-02-29` is valid. For instance, the policy for a Feb 29 birthday in a common year (Feb 28 or Mar 1) or month-end payment due dates must be explicitly decided by business rules.

When you need the last day of the month, choose `YearMonth.atEndOfMonth()` or `TemporalAdjusters.lastDayOfMonth()` instead of hardcoding adding 30 or 31 days.

## 7. Common Pitfalls and How to Avoid Them

1. **Checking only divisibility by 4**: gives wrong conclusions for 1900 or 2100. Use `Year.isLeap`.
2. **Hardcoding February to 28 days**: will reject Feb 29 in leap years. Use `YearMonth.lengthOfMonth`.
3. **Allowing all days 1–31**: misses April/June/September/November and February. Construct `LocalDate` to validate the whole date.
4. **Using 0-based months**: `LocalDate.of` and `YearMonth.of` accept month numbers **1–12**, unlike older APIs that may use 0-based indexing.
5. **Letting the formatter auto-correct dates**: `SMART`/`LENIENT` may return a different date than the input. Choose `STRICT` if the goal is validation.
6. **Confusing `yyyy`, `uuuu`, `YYYY` or `MM`, `mm`**: the symbols have different meanings, especially under strict parsing.
7. **Using `SimpleDateFormat` and forgetting leniency**: some legacy parsing operations may adjust invalid dates by default; for new code, prefer `java.time`.
8. **Adding milliseconds to infer months/years**: months have different lengths and local day lengths can be affected by DST. Use calendar date APIs.

`LocalDate` represents a **calendar date**, with no time of day or time zone. The validity of `2024-02-29` does not depend on time zone; a time zone is only needed when converting an **instant in time** (e.g., `Instant`) into a local date, because the same instant may fall on two different dates in two regions.

## 8. Testing Key Boundaries

| Test case | Input | Expected |
| --- | --- | --- |
| Normal leap year | `2024-02-29` | Valid |
| Common year | `2023-02-29` | Rejected |
| Non-leap century | `1900-02-29`; `2100-02-29` | Rejected |
| Leap century | `2000-02-29` | Valid |
| 30-day month | `2024-04-30`; `2024-04-31` | Valid; rejected |
| Month number bounds | `2024-12-31`; `2024-13-01` | Valid; rejected |
| Day number bounds | `2024-01-01`; `2024-01-00` | Valid; rejected |
| Strict pattern parsing | `2024-02-29`; `2024/02/29` | Valid; rejected |
| Adding one year from leap day | `2024-02-29` plus 1 year | `2025-02-28` |

In JUnit, you can use `assertThrows(DateTimeException.class, () -> LocalDate.of(2023, 2, 29))` for date construction and `assertThrows(DateTimeParseException.class, () -> LocalDate.parse("2023-02-29"))` for invalid date strings; for valid cases, compare `LocalDate` values directly.

## 9. Choosing the Right API for the Job

| Requirement | Recommended API |
| --- | --- |
| Is the year a leap year? | `Year.isLeap(year)` |
| How many days does a month in a year have? | `YearMonth.of(year, month).lengthOfMonth()` |
| What is the last day of the month? | `YearMonth.of(year, month).atEndOfMonth()` |
| Do three numbers (year, month, day) form a real date? | `LocalDate.of(year, month, day)`; handle `DateTimeException` |
| Is an ISO date string valid? | `LocalDate.parse(text)` |
| Parse dates with a custom pattern without adjusting invalid dates | `DateTimeFormatter` with `ResolverStyle.STRICT` |
| Add days/months/years | `LocalDate.plusDays/plusMonths/plusYears` with explicit business rules |

**Key takeaway:** determine leap years using the full 4/100/400 rule; compute day counts using **a specific year and month**; use `LocalDate` and strict parsing to **reject non-existent dates**. Do not confuse the valid adjustment behavior of date arithmetic with accepting an invalid date input.
