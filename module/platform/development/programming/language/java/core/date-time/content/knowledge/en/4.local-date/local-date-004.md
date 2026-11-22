# Checking Leap Years, Month Lengths, and Year Lengths with LocalDate in Java

## 1. Objectives and Scope

In applications that manage orders, contracts, reports, or appointments, the number of days in a **month** and **year** determines whether a date is valid, which date is the end of a period, and how date addition must handle cases such as 29/02. Java provides expressive APIs in **java.time** instead of forcing developers to build day-count tables and apply leap-year formulas in multiple places.

After this lesson, you can:

- Explain the **leap year rules in the ISO/Gregorian calendar**, including century years.
- Use **LocalDate.isLeapYear()**, **LocalDate.lengthOfMonth()**, and **LocalDate.lengthOfYear()**.
- Choose **Year**, **YearMonth**, or **Month** when you only know the year, year-month, or month.
- Validate February 29, days 30/31 of months, and handle **DateTimeException**.
- Compute the last day of a month, the last day of a year, the day-of-year position, and the number of days between two dates.
- Distinguish **calendar year length** from **actual elapsed duration in seconds**, avoiding confusion in business logic.

The scope of this lesson is **LocalDate** and the standard ISO calendar used in Java Core. When a specific time of day or instant is needed, the corresponding type must be added; a calendar date itself does not contain a time zone or UTC instant.

## 2. What Is a Leap Year?

In the Gregorian calendar (extended backward according to java.time's **proleptic Gregorian** convention), a normal year has **365 days**; a leap year has **366 days** because February has an extra day, **29/02**.

Rules for determining a leap year:

1. A year **divisible by 400**: it is a leap year.
2. If not divisible by 400, but **divisible by 100**: not a leap year.
3. If neither of the above applies, but **divisible by 4**: it is a leap year.
4. All remaining years: not a leap year.

An equivalent boolean expression can be written as:

~~~java
boolean leap = (year % 4 == 0)
        && (year % 100 != 0 || year % 400 == 0);
~~~

This is an **illustrative expression** that must be placed inside a method with the **year** variable declared. In application code, you should use **Year.isLeap(year)** or the corresponding date/year object method to express business intent and avoid repeating the formula.

| Year | Divisible by 4 | Divisible by 100 | Divisible by 400 | Conclusion |
| --- | --- | --- | --- | --- |
| 2024 | Yes | No | No | Leap, 366 days |
| 2025 | No | No | No | Not leap, 365 days |
| 2028 | Yes | No | No | Leap, 366 days |
| 1900 | Yes | Yes | No | **Not leap**, 365 days |
| 2000 | Yes | Yes | Yes | **Leap**, 366 days |
| 2100 | Yes | Yes | No | **Not leap**, 365 days |
| 2400 | Yes | Yes | Yes | **Leap**, 366 days |

The key point is that **“divisible by 4” is not enough**: the years 1900 and 2100 are counterexamples. These examples follow Java's ISO proleptic Gregorian rules; do not use these rules as-is to infer how different countries actually numbered dates in all historical periods.

## 3. Three Core Methods of LocalDate

**java.time.LocalDate** represents a **date**, consisting of year, month, and day-of-month in the ISO calendar. The object has no time of day, offset, ZoneId, or Instant, and is **immutable**.

~~~java
LocalDate date = LocalDate.of(2024, 2, 10);
boolean leap = date.isLeapYear();   // true
int daysInMonth = date.lengthOfMonth(); // 29
int daysInYear = date.lengthOfYear();   // 366
~~~

This is a code snippet; you need to import **java.time.LocalDate** and place it inside a method if you want to compile it standalone.

### LocalDate.isLeapYear()

Returns a **boolean** based on the **year** of the LocalDate object; the current day and month do not change the result. For example:

- **LocalDate.of(2024, 1, 1).isLeapYear()** returns **true**.
- **LocalDate.of(2024, 12, 31).isLeapYear()** also returns **true**.
- **LocalDate.of(2025, 2, 1).isLeapYear()** returns **false**.

This method does not create or modify a date; it only queries information about the year. A LocalDate always holds a valid date, so there is no need to use this method as a step to verify whether the object itself is valid.

### LocalDate.lengthOfMonth()

Returns the number of days in the **month containing that date**: one of 28, 29, 30, or 31.

~~~java
LocalDate feb2024 = LocalDate.of(2024, 2, 1);
LocalDate feb2025 = LocalDate.of(2025, 2, 1);

System.out.println(feb2024.lengthOfMonth()); // 29
System.out.println(feb2025.lengthOfMonth()); // 28
~~~

This is a snippet used inside a method; import LocalDate. Because leap years only affect February in the ISO calendar, **lengthOfMonth()** is especially useful when building monthly calendars, picking valid transaction dates, or determining the last day of a month.

Do not confuse **lengthOfMonth()** with the number of days **remaining** from the current date to the end of the month. For example, 10/02/2024 has lengthOfMonth() = 29, but the number of days after 10/02 through 29/02 is **19**; if 10/02 itself is included, there are **20** days. Always define the inclusive/exclusive rule for the start and end dates.

### LocalDate.lengthOfYear()

Returns **365** for a normal year and **366** for a leap year.

~~~java
LocalDate firstDay2024 = LocalDate.of(2024, 1, 1);
System.out.println(firstDay2024.lengthOfYear()); // 366
~~~

The number of days in a year does not depend on whether you call it on 01/01 or 31/12 of the same year. **lengthOfYear()** is the **calendar year** length, not a measurement of actual elapsed duration between two Instants across time zones.

## 4. Choosing Year, YearMonth, or Month When the Day Is Not Yet Known

There is no need to “fabricate” day 01/01 or day 01 of a month if the requirement only provides a year or a year-month.

| Known data | Java type | Appropriate API | Example |
| --- | --- | --- | --- |
| Year only | **Year** | **Year.isLeap(long)**, **Year.of(y).isLeap()**, **Year.of(y).length()** | Check whether 2100 is a leap year |
| Year and month | **YearMonth** | **isLeapYear()**, **lengthOfMonth()**, **lengthOfYear()**, **isValidDay(d)** | Number of days in Feb 2024 |
| Month only, year unknown | **Month** | **length(boolean leapYear)**, **minLength()**, **maxLength()** | February can have 28/29 days |
| Year-month-day | **LocalDate** | **isLeapYear()**, **lengthOfMonth()**, **lengthOfYear()** | Query from an invoice date |

Example:

~~~java
Year year = Year.of(2100);
boolean leap = year.isLeap();                 // false
int daysInYear = year.length();               // 365

YearMonth february = YearMonth.of(2024, 2);
int monthDays = february.lengthOfMonth();      // 29
boolean valid29 = february.isValidDay(29);     // true
LocalDate monthEnd = february.atEndOfMonth();  // 2024-02-29

int febNormal = Month.FEBRUARY.length(false);  // 28
int febLeap = Month.FEBRUARY.length(true);     // 29
~~~

These expressions are snippets requiring `import java.time.*` and placed inside a method. **Month.length(boolean)** requires passing leap-year information when checking February, because a standalone Month does not know which year it belongs to. With a YearMonth object, Java infers leap-year status automatically, making it a good choice when building a calendar for a specific month.

**Year.isLeap(long)** is a static method that checks the rule by year without creating a LocalDate. If you only need to answer “is 2028 a leap year?”, this is the right level of abstraction.

## 5. Length of Each Month in the ISO Calendar

| Month | Days in a normal year | Days in a leap year |
| --- | ---: | ---: |
| January | 31 | 31 |
| **February** | **28** | **29** |
| March | 31 | 31 |
| April | 30 | 30 |
| May | 31 | 31 |
| June | 30 | 30 |
| July | 31 | 31 |
| August | 31 | 31 |
| September | 30 | 30 |
| October | 31 | 31 |
| November | 30 | 30 |
| December | 31 | 31 |
| **Total** | **365** | **366** |

Every month other than February has a fixed number of days under this rule; only February requires knowing the year.

Do not confuse this with a rule like **“even months have 30 days, odd months have 31 days”**: both July and August have 31 days, and December also has 31. In application code, use the API instead of manual memorization rules.

You can obtain the last day of a month without calculating it manually:

~~~java
YearMonth month = YearMonth.of(2026, 4);
LocalDate last = month.atEndOfMonth(); // 2026-04-30

LocalDate date = LocalDate.of(2024, 2, 10);
LocalDate end = date.withDayOfMonth(date.lengthOfMonth());
// 2024-02-29
~~~

With LocalDate, you can also use **date.with(TemporalAdjusters.lastDayOfMonth())** after importing **java.time.temporal.TemporalAdjusters**. The advantage is that it directly expresses the “last day of the month” policy and handles February automatically.

## 6. Complete Java 17+ Example and Deterministic Output

Create the file **LeapYearAndMonthLength.java**:

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Month;
import java.time.Year;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;

public class LeapYearAndMonthLength {
    public static void main(String[] args) {
        System.out.println("2024 nhuận: " + Year.isLeap(2024));
        System.out.println("1900 nhuận: " + Year.isLeap(1900));
        System.out.println("2000 nhuận: " + Year.isLeap(2000));
        System.out.println("2100 nhuận: " + Year.isLeap(2100));

        LocalDate inLeapYear = LocalDate.of(2024, 2, 10);
        LocalDate inNormalYear = LocalDate.of(2025, 2, 10);
        System.out.println("Tháng 2/2024: " + inLeapYear.lengthOfMonth());
        System.out.println("Tháng 2/2025: " + inNormalYear.lengthOfMonth());
        System.out.println("Năm 2024: " + inLeapYear.lengthOfYear());
        System.out.println("Năm 2025: " + inNormalYear.lengthOfYear());

        YearMonth february = YearMonth.of(2024, Month.FEBRUARY);
        YearMonth april = YearMonth.of(2026, Month.APRIL);
        System.out.println("29/02/2024 hợp lệ: " + february.isValidDay(29));
        System.out.println("Cuối tháng 2/2024: " + february.atEndOfMonth());
        System.out.println("Cuối tháng 4/2026: " + april.atEndOfMonth());

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        System.out.println("29/02 cộng 1 năm: " + leapDay.plusYears(1));
        System.out.println("Ngày thứ mấy trong năm: " +
                LocalDate.of(2024, 12, 31).getDayOfYear());
        long daysIn2024 = ChronoUnit.DAYS.between(
                LocalDate.of(2024, 1, 1),
                LocalDate.of(2025, 1, 1));
        System.out.println("Khoảng năm 2024 (ngày): " + daysIn2024);

        try {
            LocalDate.of(2025, 2, 29);
        } catch (DateTimeException exception) {
            System.out.println("29/02/2025: ngày không hợp lệ");
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 LeapYearAndMonthLength.java
java LeapYearAndMonthLength
~~~

**Exact stdout**:

~~~text
2024 nhuận: true
1900 nhuận: false
2000 nhuận: true
2100 nhuận: false
Tháng 2/2024: 29
Tháng 2/2025: 28
Năm 2024: 366
Năm 2025: 365
29/02/2024 hợp lệ: true
Cuối tháng 2/2024: 2024-02-29
Cuối tháng 4/2026: 2026-04-30
29/02 cộng 1 năm: 2025-02-28
Ngày thứ mấy trong năm: 366
Khoảng năm 2024 (ngày): 366
29/02/2025: ngày không hợp lệ
~~~

Explanation:

- **1900** is a century year not divisible by 400, so it is not a leap year; **2000** is divisible by 400, so it is a leap year.
- **YearMonth.isValidDay(29)** checks whether day 29 is valid in February 2024.
- **plusYears(1)** on 29/02/2024 produces **28/02/2025** because the target year does not have February 29. This is standard LocalDate behavior, though anniversary applications must decide on their own policy if they want to move to 01/03 instead.
- **getDayOfYear()** gives the ordinal day 1–365 or 1–366; 31/12/2024 is day 366.
- **ChronoUnit.DAYS.between(start, end)** with start **01/01/2024** and end **01/01/2025** returns 366 under start-inclusive, end-exclusive semantics.
- Calling **LocalDate.of(2025, 2, 29)** throws DateTimeException because the date does not exist; the try/catch block prints a stable message without depending on the exact error message generated by the JDK.

The example uses fixed dates throughout and does not depend on the system clock, time zone, or runtime instant.

## 7. Validating Dates: Do Not Just Check 1–31

A valid year-month-day tuple must simultaneously satisfy:

- The year is within the range supported by the data type.
- The month is within 1–12.
- The day is within 1 to **the actual number of days in that month in that year**.

Examples:

| Input | Valid? | Reason |
| --- | --- | --- |
| 29/02/2024 | Yes | 2024 is a leap year |
| 29/02/2025 | No | 2025 has 28 days in February |
| 31/04/2026 | No | April has 30 days |
| 30/04/2026 | Yes | Last day of April |
| 31/12/2026 | Yes | December has 31 days |
| 00/01/2026 | No | Day-of-month starts at 1 |
| 01/13/2026 | No | There is no month 13 |

**Approach A: construct a LocalDate and catch the exception.** This is the simplest option when you want to turn input into a valid date object:

~~~java
try {
    LocalDate parsed = LocalDate.of(year, month, day);
    // parsed exists only if year-month-day is valid
} catch (DateTimeException invalidDate) {
    // Return validation error to the user
}
~~~

This is a snippet; declare appropriate year, month, and day variables and import `java.time.*`. This approach validates month, day, and year range together.

**Approach B: use YearMonth.isValidDay(day).** Suitable when the year and month have already been constructed validly:

~~~java
YearMonth ym = YearMonth.of(2025, 2);
boolean possible = ym.isValidDay(29); // false
~~~

If the input month is invalid, **YearMonth.of(year, month)** also throws DateTimeException. Therefore, isValidDay cannot be treated as a tool that accepts arbitrary unvalidated inputs.

**Approach C: parse with a strict formatter.** When receiving a string formatted as **dd/MM/uuuu**, avoid splitting it manually and assembling an invalid default date:

~~~java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu")
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed = LocalDate.parse("29/02/2024", formatter);
// LocalDate.parse("29/02/2025", formatter) throws DateTimeParseException.
~~~

This is a snippet; you need to import **java.time.LocalDate**, **java.time.format.DateTimeFormatter**, and **java.time.format.ResolverStyle**. With **ResolverStyle.STRICT**, strings representing nonexistent dates are rejected; use the pattern letter **uuuu** to represent the ISO proleptic year. **yyyy** is year-of-era, which requires attention to era fields under STRICT parsing.

Never swallow exceptions and replace an invalid date input with the current date; doing so corrupts business data. If an API needs to report an error, preserve the input context and return a clear message about the day/month/year.

## 8. End of Month and Rules for Adding Months and Years

Methods such as **plusDays**, **plusMonths**, **plusYears**, **minusDays**, and **withYear** return a new LocalDate object; they do not mutate the original object.

~~~java
LocalDate base = LocalDate.of(2024, 2, 29);
LocalDate nextYear = base.plusYears(1);       // 2025-02-28
LocalDate afterFourYears = base.plusYears(4); // 2028-02-29
LocalDate nextDay = base.plusDays(1);         // 2024-03-01
~~~

When adding months, Java tries to preserve the day-of-month; if that day does not exist in the target month, the result is clamped to the **last valid day of the target month**:

~~~java
LocalDate january31 = LocalDate.of(2025, 1, 31);
LocalDate nextMonth = january31.plusMonths(1);
// 2025-02-28

LocalDate leapJanuary31 = LocalDate.of(2024, 1, 31);
LocalDate leapFebruary = leapJanuary31.plusMonths(1);
// 2024-02-29
~~~

**Business note:** “Every month on the 31st” is not quite the same as repeatedly “taking the previous date and adding one month.” For example:

- 31/01/2025 + 1 month = 28/02/2025.
- 28/02/2025 + 1 month = 28/03/2025.
- However, if the policy is the **last day of every month**, the March occurrence must fall on **31/03/2025**.

Therefore, for a recurring “end of month” schedule, store the **end-of-month rule** and compute each month using **YearMonth.atEndOfMonth()**; do not chain additions from a date that was already clamped down to 28. For an anniversary policy on 29/02 in non-leap years, explicitly define whether to use 28/02 or 01/03; Java does not choose an organization's legal or business rule on its own.

## 9. Year Length, Day-of-Year Position, and Counting Day Intervals

A leap year has 366 days, while **day-of-year** is the 1-based ordinal position of a specific date. A few examples:

| LocalDate | getDayOfYear() |
| --- | ---: |
| 2024-01-01 | 1 |
| 2024-02-28 | 59 |
| 2024-02-29 | 60 |
| 2024-03-01 | 61 |
| 2025-03-01 | 60 |
| 2024-12-31 | 366 |
| 2025-12-31 | 365 |

To convert from a day-of-year ordinal back to a date, use **LocalDate.ofYearDay(year, dayOfYear)**. For example:

~~~java
LocalDate sixtieth2024 = LocalDate.ofYearDay(2024, 60);
// 2024-02-29

LocalDate sixtieth2025 = LocalDate.ofYearDay(2025, 60);
// 2025-03-01
~~~

Passing 366 to **LocalDate.ofYearDay(2025, 366)** throws DateTimeException because a normal year has only 365 days.

**Counting days between two LocalDates:** use **ChronoUnit.DAYS.between(startInclusive, endExclusive)** or **start.until(end, ChronoUnit.DAYS)**. If a problem requires counting both the start date and the end date (for example, the number of calendar days of a trip), state the inclusive rule explicitly and calculate accordingly. Not every problem adds one day.

**A calendar year is not 365 × 24 hours.** LocalDate.lengthOfYear() returns 365 or 366 days in the ISO calendar. When considering a local year in a region with daylight saving time transitions, the number of elapsed hours depends on offset changes; in special regions, even a single local day may not be 24 hours long. If you need to measure the actual number of seconds between two points in time, create Instants using the appropriate zone and use Duration. Never multiply calendar days by 86,400 to conclude the exact number of seconds in an interval across all time zones.

## 10. Applications: Generating Monthly Calendars and Determining Period End Dates

### Printing All Days in a Month

When you need to generate the day choices for February 2024, **YearMonth.lengthOfMonth()** is the natural approach:

~~~java
YearMonth ym = YearMonth.of(2024, 2);
for (int day = 1; day <= ym.lengthOfMonth(); day++) {
    LocalDate calendarDate = ym.atDay(day);
    // Use calendarDate to build calendar entries or display dates.
}
~~~

This is a snippet; import `java.time.*` and place it inside a method. This approach automatically includes 29/02/2024 without accidentally generating 29/02/2025. When building multi-year calendars, avoid hardcoding or caching the number of days in February.

### Getting the Date Range of a Monthly Period

A reporting period for February 2024 can be represented as the interval **[2024-02-01, 2024-03-01)**:

~~~java
YearMonth period = YearMonth.of(2024, 2);
LocalDate startInclusive = period.atDay(1);
LocalDate endExclusive = period.plusMonths(1).atDay(1);
// startInclusive = 2024-02-01
// endExclusive   = 2024-03-01
~~~

Every LocalDate satisfying **!date.isBefore(startInclusive) && date.isBefore(endExclusive)** falls within the period. A **start-inclusive, end-exclusive** interval lets you chain consecutive monthly periods without overlapping boundary dates.

If you query **timestamps** for a local month, you must first convert the LocalDate boundaries to Instants using the business ZoneId; lengthOfMonth() alone is not enough to determine how many seconds elapse in a month across all regions.

### Birthdays and Age

A date of birth should be a **LocalDate**. To calculate age on a reference date, use **Period.between(dateOfBirth, referenceDate).getYears()** if the age policy counts full years based on the ISO calendar; individuals born on 29/02 may be subject to different legal regulations or organizational policies in non-leap years. **getYear()** is not age; it returns the absolute year of the LocalDate.

### Due Dates and Payment Dates

If an invoice is due on “the last day of the month,” calculate it with **YearMonth.atEndOfMonth()**. If a contract specifies “after exactly 365 days,” use explicit day addition **date.plusDays(365)**; if it specifies “after one calendar year,” use **date.plusYears(1)**. For 29/02, the two approaches can yield different results, so contract wording must be translated accurately into a date-calculation policy.

## 11. Limits and Edge Cases

- **There is no day 0 or month 0** in ISO LocalDate. Day-of-month ranges from 1 to lengthOfMonth(); month ranges from 1 to 12.
- **Java supports year 0 and negative years** under the ISO proleptic year numbering system, with a LocalDate year range from **-999999999 to +999999999**. Year 0 does not match historical year naming conventions (BC/AD); when displaying historical data, define the convention explicitly.
- **Year.isLeap(0)** returns **true** under ISO proleptic Gregorian rules. Negative years follow the same arithmetic rules. This is a programming convention and does not imply that all historical societies used the Gregorian calendar.
- Non-ISO calendar systems have different leap-year rules and month lengths. **LocalDate** is an ISO type; if you need the Japanese, Hijrah, or another calendar system, explore **java.time.chrono** and use the appropriate types/methods instead of applying ISO formulas to every Chronology.
- **YearMonth.of(...)**, **LocalDate.of(...)**, and **LocalDate.ofYearDay(...)** can all throw **DateTimeException** when an input field is out of range or the date is invalid.
- Using **LocalDate.now()** to get “today” depends on the system clock and time zone. When checking whether a user-entered year is a leap year, build the date/year from that input without needing the machine clock. In logic involving “today,” use an explicit **Clock** or ZoneId for reliable testing.
- **LocalDate.isLeapYear()** operates on the year of the object itself; calling it on **LocalDate.of(2024, 6, 1)** still checks the year 2024, not whether June has a leap day.

## 12. Common Mistakes and How to Fix Them

| Wrong or error-prone approach | Consequence | Correct approach |
| --- | --- | --- |
| Using only **year % 4 == 0** | Misclassifies 1900/2100 | Use **Year.isLeap(year)** |
| Assuming **February always has 28 days** | Misses 29/02 in leap years | Use **YearMonth.lengthOfMonth()** |
| Assuming every year has **365 days** | Miscounts days and day-of-year | Use **LocalDate.lengthOfYear()** |
| Allowing days **1..31** for every month | Produces nonexistent 31/04, 30/02 | Use **LocalDate.of(...)** or **YearMonth.isValidDay(...)** |
| Adding 86,400 seconds to reach “tomorrow” in all regions | Can drift across DST transitions | Use calendar **plusDays(1)** and a zone when Instant is needed |
| Calling **plusMonths(1)** repeatedly for an “end-of-month” schedule | After February, loses the 31st anchor | Store the end-of-month policy and use **atEndOfMonth()** |
| Calling **date.plusDays(1)** and expecting date to mutate | No change observed because LocalDate is immutable | Use the returned new value |
| Catching all Exceptions and treating an invalid date as today | Masks input errors | Catch **DateTimeException** and report the validation reason |
| Applying Gregorian rules to all histories and calendar systems | Incorrect calendar semantics | State **ISO proleptic Gregorian** and choose the appropriate Chronology |
| Comparing “dd/MM/yyyy” strings instead of actual dates | Wrong chronological order | Parse into **LocalDate**, then use **isBefore/isAfter** |

## 13. Self-Check Questions

**Question 1.** Does the year 2100 have 366 days?

No. 2100 is divisible by 100 but not by 400, so it is a normal year with **365 days**; February has 28 days.

**Question 2.** What does LocalDate.of(2028, 2, 1).lengthOfMonth() return?

**29**, because 2028 is divisible by 4, not divisible by 100, and is a leap year.

**Question 3.** What date does LocalDate.of(2025, 2, 28).plusDays(1) return?

**2025-03-01**, because 2025 is not a leap year.

**Question 4.** Do January 31, 2024 plus one month and the last day of February 2024 match?

Yes. **LocalDate.of(2024, 1, 31).plusMonths(1)** gives **2024-02-29**; **YearMonth.of(2024, 2).atEndOfMonth()** also gives **2024-02-29**. However, chained month additions do not always preserve an “end-of-month” policy, as explained in Section 8.

**Question 5.** If you have 2024 and 02 but no day yet, which type should you use?

**YearMonth**, because it accurately represents the input data; use **lengthOfMonth()** or **isValidDay(29)** without constructing a dummy LocalDate.

**Question 6.** Are the 60th days of 2024 and 2025 the same?

No. In 2024, it is **29/02**; in 2025, it is **01/03**.

**Question 7.** Can you multiply lengthOfYear() by 86,400 to find the exact number of seconds in a year in every time zone?

No. **lengthOfYear()** returns the number of calendar days, whereas the boundaries of a year in a time zone and offset-transition rules determine the actual duration between two Instants.

## 14. Implementation Takeaways

- **To check for a leap year:** **Year.isLeap(year)** or **LocalDate.isLeapYear()**.
- **To get the number of days in a month:** **YearMonth.lengthOfMonth()** or **LocalDate.lengthOfMonth()**.
- **To get the number of days in a year:** **Year.of(year).length()**, **YearMonth.lengthOfYear()**, or **LocalDate.lengthOfYear()**.
- **To validate a day in a year-month:** **YearMonth.isValidDay(day)**; to construct a full valid date, use **LocalDate.of(year, month, day)**.
- **To find the last day of a month:** **YearMonth.atEndOfMonth()** or **TemporalAdjusters.lastDayOfMonth()**.
- **To get the day-of-year ordinal:** **LocalDate.getDayOfYear()**; to construct a date from that ordinal, use **LocalDate.ofYearDay(year, day)**.
- **To measure the number of days between two dates:** **ChronoUnit.DAYS.between(start, end)**, and explicitly decide whether the boundaries are inclusive.

## Official References

- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): isLeapYear, lengthOfMonth, lengthOfYear, getDayOfYear, and date operations.
- [Java SE 17 — Year](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Year.html): leap-year rules, Year.isLeap, and Year.length.
- [Java SE 17 — YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html): isValidDay, atEndOfMonth, lengthOfMonth, and lengthOfYear.
- [Java SE 17 — Month](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Month.html): month lengths by leap-year status.
- [Java SE 17 — ChronoUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html): counting days in calendar time units.
