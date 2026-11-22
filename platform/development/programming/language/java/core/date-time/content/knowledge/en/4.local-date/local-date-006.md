# Replacing a Date Component and Handling End-of-Month Dates with `LocalDate`

Suppose an invoicing system generates bills on **January 31** and needs to determine the payment date for the next month. If you simply change the month from 1 to 2, February 31 does not exist. What should the application do: throw an error, use the last day of February, or shift the schedule to another day? The answer depends on the **Java method** used and the **business rule**.

`LocalDate` in `java.time` (Java 8+, with examples using Java 17+) represents a date in the ISO-8601 calendar system, containing only **year, month, and day**, without time-of-day or time zone. You can replace individual components using `with...()` methods, add/subtract calendar units with `plus...()`, or find landmarks such as the end of the month via `YearMonth` and `TemporalAdjusters`.

In this lesson, it is important to distinguish three behaviors:
- **Strictly replacing a day value:** if the value is invalid for the current month/year, Java throws an exception.
- **Replacing the month or year:** Java automatically adjusts the **day of month** to the last valid day if needed.
- **Shifting months/years:** Java keeps the day of month when possible, otherwise adjusting to the last day of the target month; multiple shifts can produce a different result from a single direct shift.

## 1. `LocalDate` is immutable: replacing a date creates a new object

A `LocalDate` has three main components: `getYear()`, `getMonthValue()`, and `getDayOfMonth()`. The `with...()` methods return a new `LocalDate` value; they **do not modify the original object**.

~~~java
LocalDate original = LocalDate.of(2026, 1, 20);
LocalDate changed = original.withDayOfMonth(31);

// original = 2026-01-20
// changed  = 2026-01-31
~~~

The small code snippets in this article are **illustrative** and may require `import java.time.LocalDate;` along with related imports. The complete example section below includes full imports, the class name, compilation commands, and execution output.

If you write `original.withDayOfMonth(31);` without capturing the return value, the `original` variable still holds the initial date. This is a common mistake when first getting used to an immutable API.

## 2. Replacing day, month, or year individually with `with...()`

### 2.1. `withDayOfMonth(int dayOfMonth)`: strictly validates the day

This method replaces the **day of month**, keeping the month and year unchanged:

~~~java
LocalDate date = LocalDate.of(2026, 5, 20);
LocalDate firstDay = date.withDayOfMonth(1);  // 2026-05-01
LocalDate lastDay = date.withDayOfMonth(31);  // 2026-05-31
~~~

The replacement day must exist in the current month/year. Since February 2025 has only 28 days:

~~~java
LocalDate feb = LocalDate.of(2025, 2, 10);
LocalDate invalid = feb.withDayOfMonth(31); // throws DateTimeException
~~~

`withDayOfMonth(31)` does **not** silently change to February 28. If the value is 0, negative, greater than 31, or exceeds the number of days in the month, the method throws `DateTimeException`. If you are processing user-entered dates, you need to validate or handle exceptions instead of assuming Java will auto-correct them.

### 2.2. `withMonth(int month)`: keeps the day if possible, adjusts if the month is shorter

`withMonth` replaces the month while keeping the year. If the **day of the old month exceeds the last day of the target month**, Java automatically clamps it down to the last valid day:

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);

LocalDate feb = jan31.withMonth(2); // 2025-02-28
LocalDate apr = jan31.withMonth(4); // 2025-04-30
LocalDate may = jan31.withMonth(5); // 2025-05-31
~~~

Leap years affect the result:

~~~java
LocalDate mar31LeapYear = LocalDate.of(2024, 3, 31);
LocalDate feb2024 = mar31LeapYear.withMonth(2); // 2024-02-29
~~~

**Key distinction:** `withDayOfMonth(31)` on February throws an error; `withMonth(2)` from January 31 can yield February 28 or February 29. `withMonth` only accepts months 1–12; month 0 or 13 still throws `DateTimeException`.

### 2.3. `withYear(int year)`: watch out for February 29

Similar to replacing the month, when replacing the year and the original day does not exist in the new year, Java adjusts the day to the valid boundary:

~~~java
LocalDate leapDay = LocalDate.of(2024, 2, 29);

LocalDate newYear = leapDay.withYear(2025); // 2025-02-28
LocalDate stillLeap = leapDay.withYear(2028); // 2028-02-29
~~~

The example above shows that replacing the **year** does not always preserve the exact day number. When managing February 29 birthdays, anniversaries, or billing cycles, the application must **choose a non-leap-year policy** (February 28, March 1, or another rule), rather than assuming `withYear` is the right policy for every business case.

### 2.4. `withDayOfYear(int dayOfYear)`: replaces the ordinal day of the year

This replaces the **ordinal day within the year**, not the day within the month:

~~~java
LocalDate first2024 = LocalDate.of(2024, 1, 1);
LocalDate day60 = first2024.withDayOfYear(60); // 2024-02-29

LocalDate first2025 = LocalDate.of(2025, 1, 1);
LocalDate day60Next = first2025.withDayOfYear(60); // 2025-03-01
~~~

A leap year has 366 days, and a common year has 365 days. `withDayOfYear(366)` in a non-leap year throws `DateTimeException`. Use this method when the input is genuinely the **day number within the year**, not as a substitute for `withDayOfMonth`.

### 2.5. `with(TemporalField, long)` and `with(TemporalAdjuster)`

Besides the specialized methods, `LocalDate` provides `with(TemporalField, long)` to replace a field and `with(TemporalAdjuster)` to apply an adjustment rule:

~~~java
LocalDate date = LocalDate.of(2025, 1, 31);

LocalDate anotherFebruary =
        date.with(ChronoField.MONTH_OF_YEAR, 2); // 2025-02-28
LocalDate firstOfMonth =
        date.with(ChronoField.DAY_OF_MONTH, 1); // 2025-01-01
LocalDate lastOfMonth =
        date.with(TemporalAdjusters.lastDayOfMonth()); // 2025-01-31
~~~

This snippet requires importing `java.time.temporal.ChronoField` and `java.time.temporal.TemporalAdjusters`. Replacing `MONTH_OF_YEAR` behaves like `withMonth`; replacing `DAY_OF_MONTH` behaves like `withDayOfMonth`. Use the specialized methods when you already know the field to change; use `TemporalAdjusters` for rules such as "last day of the month".

## 3. What is the end of the month and how to determine it accurately

Months have 28, 29, 30, or 31 days. February has 29 days in a **leap year** under the ISO calendar (divisible by 4, except century years not divisible by 400).

Instead of writing your own lookup table of days per month, `LocalDate` provides these methods:

| API | Result | Example |
| --- | --- | --- |
| `date.lengthOfMonth()` | Number of days in the month of `date` | February 2024 → 29 |
| `date.lengthOfYear()` | 365 or 366 | Year 2024 → 366 |
| `date.isLeapYear()` | Whether the year of `date` is a leap year | Year 2025 → false |
| `date.getDayOfMonth()` | Current day of the month | 28 on February 28 |
| `date.withDayOfMonth(date.lengthOfMonth())` | Last day of the current month | 2025-02-28 |
| `date.with(TemporalAdjusters.lastDayOfMonth())` | Last day of the month using an adjuster | 2024-02-29 |
| `YearMonth.from(date).atEndOfMonth()` | Last day of the month from a `YearMonth` | 2026-04-30 |

Example:

~~~java
LocalDate someDay = LocalDate.of(2024, 2, 10);

LocalDate lastDay1 =
        someDay.withDayOfMonth(someDay.lengthOfMonth());
LocalDate lastDay2 =
        someDay.with(TemporalAdjusters.lastDayOfMonth());

// lastDay1 = lastDay2 = 2024-02-29
~~~

Checking whether a date is the end of the month:

~~~java
boolean isMonthEnd =
        someDay.getDayOfMonth() == someDay.lengthOfMonth();
~~~

This is the exact comparison; you should not assume "day 30 or 31 is always the end of the month", because the end of February can be the 28th or 29th.

## 4. `YearMonth`: representing a month before choosing a day

If your business logic deals with **billing periods, payroll periods, end-of-month dates, or monthly recurring schedules**, `YearMonth` is the right tool. It holds **year and month** without attaching a specific day yet:

~~~java
YearMonth feb2025 = YearMonth.of(2025, 2);

int length = feb2025.lengthOfMonth(); // 28
LocalDate firstDay = feb2025.atDay(1); // 2025-02-01
LocalDate endDay = feb2025.atEndOfMonth(); // 2025-02-28
~~~

`YearMonth.atDay(int)` validates that the day exists: `YearMonth.of(2025, 2).atDay(31)` throws `DateTimeException`. Conversely, `atEndOfMonth()` automatically determines the last valid day. You can obtain `YearMonth.from(localDate)`, then call `plusMonths(n)` to pick the **target month first, and the day afterward**.

This option is usually clearer in intent than creating a dummy date on the 31st and repeatedly changing the month when the problem is really "which month, and the last day of that month".

## 5. `plusMonths()` and `withMonth()`: both can adjust the day, but their meanings differ

`withMonth(m)` sets the **month within the same year** to `m`. `plusMonths(n)` moves **n months forward/backward**, potentially crossing into another year. Both apply the rule of adjusting to the last day of the target month when the original day does not exist.

Example starting from `2025-12-31`:

~~~java
LocalDate dec31 = LocalDate.of(2025, 12, 31);

LocalDate changeToJanuary = dec31.withMonth(1); // 2025-01-31
LocalDate moveOneMonth = dec31.plusMonths(1);   // 2026-01-31
~~~

These two operations differ in **year**: `withMonth` does not mean "next month". If you want to actually shift by months, use `plusMonths` or `minusMonths`.

Example starting from `2025-01-31`:

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);

LocalDate nextMonth = jan31.plusMonths(1); // 2025-02-28
LocalDate twoMonthsDirect = jan31.plusMonths(2); // 2025-03-31
LocalDate twoSteps = jan31.plusMonths(1).plusMonths(1); // 2025-03-28
~~~

The results differ because the first addition changed 31 to 28; the second addition then adds from the 28th, no longer having the information that the original desired day was 31.

**Design takeaway:** Do not build a recurring schedule by using the previous period's adjusted date as the "base date" if you need to preserve a **fixed-day / end-of-month rule**. Keep the configured day or original base month, and compute each period directly.

The same thing can happen with `plusYears()`: adding 1 year to `2024-02-29` yields `2025-02-28`; adding 3 more years to that result yields `2028-02-28`, whereas adding 4 years directly from the original anchor yields `2028-02-29`. Therefore, annual anniversary schedules must preserve the original rule if February 29 should return in leap years.

## 6. Three different policies for "end of month"

There is no single policy that fits every problem. Write down the rule clearly before implementing it:

### Policy A: Last day of the month **regardless of the initial day**

For example, "close statements **on the last day of every month**". Take each `YearMonth` and call `atEndOfMonth()`:

~~~java
YearMonth start = YearMonth.of(2025, 1);

LocalDate jan = start.atEndOfMonth();              // 2025-01-31
LocalDate feb = start.plusMonths(1).atEndOfMonth(); // 2025-02-28
LocalDate mar = start.plusMonths(2).atEndOfMonth(); // 2025-03-31
LocalDate apr = start.plusMonths(3).atEndOfMonth(); // 2025-04-30
~~~

This approach always stays at **month-end**, even after February. Use it when the business rule is "end of the monthly period".

### Policy B: Fixed day of month, using the last day when a month is shorter

For example, "payment on the **30th** of every month; use the last day of the month in February". Keep `desiredDay=30` and compute against the **target month**:

~~~java
int desiredDay = 30;
YearMonth target = YearMonth.of(2025, 2);

int actualDay = Math.min(desiredDay, target.lengthOfMonth());
LocalDate payment = target.atDay(actualDay); // 2025-02-28
~~~

In March, recomputing from `desiredDay=30` gives **March 30**, instead of getting stuck on the 28th by inheriting February's value. The fixed day is a separate part of the business rule and should not be derived from a previously "clamped" date object.

### Policy C: Throw an error or choose another rule if the requested day does not exist

If a user selects "February 31" for an event that is only allowed on the exact day they entered, silently shifting it to the 28th hides the mistake. In that case, keep the strict validation of `LocalDate.of(year, month, day)` or `YearMonth.atDay(day)` and prompt the user to correct the date. Some domains such as contracts or legal regulations may require their own specific rule rather than clamping.

If the requirement is the **last business day of the month**, `atEndOfMonth()` is not enough: you must account for weekends, public holidays, and regional calendars. For instance, if month-end falls on a Sunday, a contract might require picking the preceding Friday or the next business day. Never automatically equate "end of month" with "last business day of month".

## 7. Standalone Java 17+ example with deterministic output

The following program demonstrates component replacement, adjusting day 31 into February, leap years, computing month-end from `YearMonth`, computing subsequent periods while **preserving the month-end rule**, and the exception thrown when requesting a non-existent day.

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.TemporalAdjusters;

public class LocalDateMonthEndDemo {
    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2025, 1, 31);

        System.out.println("Ban dau: " + original);
        System.out.println("Thay ngay: " + original.withDayOfMonth(15));
        System.out.println("Thay thang 2: " + original.withMonth(2));
        System.out.println("Cong 1 thang: " + original.plusMonths(1));
        System.out.println("Cong 2 thang: " + original.plusMonths(2));
        System.out.println("Cong 1 hai lan: "
                + original.plusMonths(1).plusMonths(1));

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        System.out.println("Thay nam: " + leapDay.withYear(2025));
        System.out.println("Cuoi thang 2/2024: "
                + leapDay.with(TemporalAdjusters.lastDayOfMonth()));

        YearMonth base = YearMonth.from(original);
        for (int i = 0; i < 4; i++) {
            System.out.println("Ky +" + i + ": "
                    + base.plusMonths(i).atEndOfMonth());
        }

        try {
            LocalDate.of(2025, 2, 1).withDayOfMonth(31);
            System.out.println("31/02 hop le");
        } catch (DateTimeException e) {
            System.out.println("31/02 khong hop le");
        }

        System.out.println("Ban dau van la: " + original);
    }
}
~~~

Save as `LocalDateMonthEndDemo.java`, then run:

~~~bash
javac LocalDateMonthEndDemo.java
java LocalDateMonthEndDemo
~~~

Exact output:

~~~text
Ban dau: 2025-01-31
Thay ngay: 2025-01-15
Thay thang 2: 2025-02-28
Cong 1 thang: 2025-02-28
Cong 2 thang: 2025-03-31
Cong 1 hai lan: 2025-03-28
Thay nam: 2025-02-28
Cuoi thang 2/2024: 2024-02-29
Ky +0: 2025-01-31
Ky +1: 2025-02-28
Ky +2: 2025-03-31
Ky +3: 2025-04-30
31/02 khong hop le
Ban dau van la: 2025-01-31
~~~

Line-by-line comparison with the rules:

1. `withDayOfMonth(15)` changes the day from 31 to 15 within January itself.
2. `withMonth(2)` and `plusMonths(1)` from 2025-01-31 both produce 2025-02-28; they match **only in this situation**, not because the two APIs are always equivalent.
3. `plusMonths(2)` computes directly from January 31 to yield March 31; calling `plusMonths(1)` twice loses day 31 after passing through February, yielding March 28.
4. `withYear(2025)` from 2024-02-29 adjusts to 2025-02-28.
5. `TemporalAdjusters.lastDayOfMonth()` and `YearMonth.atEndOfMonth()` find the last day of the month based on leap-year rules.
6. `YearMonth.from(original).plusMonths(i).atEndOfMonth()` generates the month-end sequence 2025-01-31, 2025-02-28, 2025-03-31, 2025-04-30 per target month without inheriting day 28.
7. `withDayOfMonth(31)` on February throws `DateTimeException` and is caught.
8. The value of `original` remains unchanged because `LocalDate` is immutable.

## 8. Be careful when modifying multiple components in sequence

The order of operations can affect the result, or even throw an exception:

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);

LocalDate a = jan31.withMonth(2).withDayOfMonth(20);
// 2025-02-20

LocalDate b = jan31.withDayOfMonth(20).withMonth(2);
// 2025-02-20
~~~

In this example, both paths produce the same result because day 20 is valid in both months. However, if you set day 31 after already switching to February:

~~~java
LocalDate feb28 = jan31.withMonth(2);
LocalDate invalid = feb28.withDayOfMonth(31);
// DateTimeException: February 2025 does not have day 31.
~~~

To construct a requested date explicitly, determine the **target year/month**, check the number of days in that month, and then build the date according to your policy:

~~~java
int targetYear = 2025;
int targetMonth = 2;
int requestedDay = 31;
YearMonth ym = YearMonth.of(targetYear, targetMonth);

LocalDate clamped = ym.atDay(
        Math.min(requestedDay, ym.lengthOfMonth())
); // 2025-02-28
~~~

This snippet assumes `requestedDay` has already been validated as a positive number (1–31); `Math.min` is not responsible for validating negative or zero inputs. If "February 31" must be rejected, call `ym.atDay(requestedDay)` directly and handle `DateTimeException` without clamping.

## 9. Edge cases worth testing

| Input | Operation | Notable result |
| --- | --- | --- |
| `2025-01-31` | `withMonth(2)` | `2025-02-28` |
| `2024-01-31` | `withMonth(2)` | `2024-02-29` |
| `2025-03-31` | `withMonth(4)` | `2025-04-30` |
| `2024-02-29` | `withYear(2025)` | `2025-02-28` |
| `2024-02-29` | `plusYears(4)` | `2028-02-29` |
| `2025-12-31` | `plusMonths(1)` | `2026-01-31` |
| `2025-12-31` | `withMonth(1)` | `2025-01-31` |
| `2025-02-01` | `withDayOfMonth(29)` | Throws `DateTimeException` |
| `2025-02-01` | `withDayOfYear(366)` | Throws `DateTimeException` |
| `2024-02-10` | `with(lastDayOfMonth())` | `2024-02-29` |
| `2025-01-31` | `plusMonths(1).plusMonths(1)` | `2025-03-28` |
| `2025-01-31` | `plusMonths(2)` | `2025-03-31` |

You should also verify the **business rules**: whether a shorter month should clamp, throw an error, or roll over to the next month; whether the schedule must always be at month-end; which holiday calendar determines business days; and whether a February 29 anniversary may change in common years.

## 10. Common misconceptions

**"`withDayOfMonth(31)` automatically picks the last day of the month."** False: it throws an exception if the month has fewer than 31 days. Use `with(TemporalAdjusters.lastDayOfMonth())` or `YearMonth.atEndOfMonth()` when you specifically want the end of the month.

**"`withMonth(2)` is the same as `plusMonths(1)`."** False: `withMonth(2)` always moves to **February of the same year**, whereas `plusMonths(1)` adds one month from the initial date.

**"Calling `plusMonths(1)` twice is equivalent to `plusMonths(2)`."** Not always true, because the day may be clamped when passing through a shorter month, losing the original target day.

**"Once clamped to the 28th, the recurring schedule must continue on the 28th."** Only true if the business actually wants that behavior. For schedules fixed on the 30th, 31st, or end of month, store the **original rule** and compute for each target month.

**"`LocalDate` knows which time zone the date is in."** No. `LocalDate` only holds a calendar date. Converting a date to the start of day in a region, if needed, is a separate operation with `ZoneId`; some regions have historical time transitions where the start of day is not necessarily 00:00.

**"If a month has 30 days, the 30th is also the last business day of the month."** No. `LocalDate` does not know about weekends, national holidays, or custom business calendars.

## 11. Practice exercises

1. Given `LocalDate.of(2026, 1, 31)`, predict `withMonth(2)`, `plusMonths(1)`, `plusMonths(2)`, and `plusMonths(1).plusMonths(1)`; explain why the last two additions can yield different dates.
2. Write a method `lastDayOfMonth(int year, int month)` returning a `LocalDate` using `YearMonth`; test it with February 2024, February 2025, and April 2026.
3. Write a method that returns the payment date under the rule "the 30th of every month, or the last day of the month if shorter". Use `YearMonth` and test February and March in both a leap year and a non-leap year. Ensure the schedule returns to the 30th after February.
4. Starting from `2024-02-29`, call `withYear(2025)` and then `withYear(2028)`; compare with `LocalDate.of(2024, 2, 29).withYear(2028)`. From this, explain why an annual schedule needs to keep the original anchor.
5. An application only allows selecting valid dates and does not auto-clamp them. Try calling `YearMonth.of(2025, 2).atDay(31)` and handle the error to display a message to the user.
6. Write a method to find the **last business day of the month** under the simple assumption that Saturdays and Sundays are non-working days. Start from `YearMonth.atEndOfMonth()` and step backward one day at a time while it falls on a weekend; explain why a real-world implementation also needs to account for holidays.

**Remember:** With `LocalDate`, replacing the **day of month** is strictly validated; replacing the **month/year** or adding months/years may automatically adjust the day. When you need "end of month", use `YearMonth.atEndOfMonth()` or `TemporalAdjusters.lastDayOfMonth()`; when you need a recurring schedule, preserve the **original business rule** and compute each period from the target year and month.
