# Attaching a Day, Month, or Year to Create a LocalDate

## 1. Assembling the missing part to form a complete date

In the ISO calendar date model, `LocalDate` represents all three parts: **year, month, and day**. Types that hold only part of a date serve specific purposes:

- `Year`: a year, such as 2024.
- `YearMonth`: a year-month, such as 2024-02.
- `MonthDay`: a month-day without an attached year, such as February 29 (29/2).
- `Month`: a month of the year, such as `Month.FEBRUARY`.

To create a `LocalDate`, you need to supply the exact missing information. For example, a reporting period `2024-02` needs a day of the month; an anniversary on February 29 needs a specific year.

Supplying the missing part is not always just concatenating numbers. February 29 is valid in 2024 but invalid in 2023. Therefore, you need to know whether the API will **reject a non-existent date** or **adjust it to a valid date**.

`LocalDate` does not contain a time of day or a time zone. After assembling a complete date, we still do not have a point in time on the timeline. This lesson only covers assembling the parts of a date.

## 2. Choosing the assembly path based on available data

| Available data | Missing part | Assembly method | Result type |
| --- | --- | --- | --- |
| `YearMonth` | Day of month | `yearMonth.atDay(day)` | `LocalDate` |
| `YearMonth` | End-of-month selection rule | `yearMonth.atEndOfMonth()` | `LocalDate` |
| `MonthDay` | Year | `monthDay.atYear(year)` | `LocalDate` |
| `Year` | Month then day | `year.atMonth(month).atDay(day)` | `LocalDate` |
| `Year` and `MonthDay` | No missing components | `year.atMonthDay(monthDay)` | `LocalDate` |
| `Year` | Day-of-year ordinal | `year.atDay(dayOfYear)` | `LocalDate` |
| Three values: year, month, day | No missing components | `LocalDate.of(year, month, day)` | `LocalDate` |

A call chain can pass through an intermediate type. `year.atMonth(month)` only yields a `YearMonth`, not yet a `LocalDate`; chaining `atDay(day)` then supplies the day of the month.

If starting from `Month`, you can combine it with a day using `MonthDay.of(month, day)`, and then attach a year; or use `LocalDate.of(year, month, day)` directly when all three parts are already available. These two paths should be chosen according to the policy for handling invalid dates, as explained in the sections below.

## 3. YearMonth: supplying the day of the month

`YearMonth` already knows the year and month, so it has enough context to determine which days are valid in that month.

With `YearMonth.of(2024, 2)`:

- `atDay(1)` returns `2024-02-01`.
- `atDay(29)` returns `2024-02-29`.
- `atDay(30)` throws `DateTimeException`.

`atDay` does not silently roll February 30 into March or clamp it to the end of the month. The day must fall within the valid range of the given year-month. You can call `isValidDay(day)` beforehand if you need to return a UI validation message, or call `atDay` and handle the error as required.

If the requirement is the “last day of the period,” use `atEndOfMonth()` instead of hardcoding day 28, 30, or 31:

| Period | End-of-period date |
| --- | --- |
| `YearMonth.of(2023, 2)` | `2023-02-28` |
| `YearMonth.of(2024, 2)` | `2024-02-29` |
| `YearMonth.of(2024, 4)` | `2024-04-30` |
| `YearMonth.of(2024, 12)` | `2024-12-31` |

Choosing the last day of the month is an explicit rule, not a way to validate an arbitrary user-entered day. If a user enters day 31 for April and the requirement is to preserve the input as entered, do not silently substitute `atEndOfMonth()` just to make the data accepted.

The APIs for combining a year-month and a day are documented in [YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html).

## 4. MonthDay: supplying a year and handling February 29

`MonthDay` fits an annually recurring month-day before a specific year's occurrence is determined. `MonthDay.of(2, 29)` is allowed to exist because February 29 exists in leap years.

When attaching a year:

| Expression | Result |
| --- | --- |
| `MonthDay.of(2, 29).atYear(2024)` | `2024-02-29` |
| `MonthDay.of(2, 29).atYear(2023)` | `2023-02-28` |
| `MonthDay.of(12, 25).atYear(2024)` | `2024-12-25` |

Key point to remember: `atYear` **automatically adjusts February 29 to February 28 in a common year**. It does not throw an error in that situation.

If the requirement is to reject a month-day that does not exist in the target year, check first with `Year.of(year).isValidMonthDay(monthDay)`, and only assemble when valid. The `attachYearStrict` method in this lesson's program follows this exact rule.

A `MonthDay` does not accept every pair of numbers. For instance, `MonthDay.of(4, 31)` is rejected immediately because April never has 31 days. By contrast, February 29 requires a year before it can be known whether it can be kept as is. The year-attaching behavior is specified in [MonthDay](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/MonthDay.html).

Do not assume that every February 29 anniversary should move to February 28. That is merely the API's behavior; business rules might require reporting an error, skipping the period, or moving to another date. You must choose the policy explicitly before persisting the result.

## 5. Year: supplying month and day along two different paths

### 5.1. Attaching the month first, then the day

With `Year.of(2024)`, you can call:

```java
// Illustrative snippet inside a method.
Year year = Year.of(2024);
YearMonth february = year.atMonth(Month.FEBRUARY);
LocalDate date = february.atDay(29);
```

This can be written concisely as `year.atMonth(Month.FEBRUARY).atDay(29)`. Because the final step is `YearMonth.atDay`, this path rejects invalid days. Changing the year to 2023 causes `atDay(29)` to throw an error.

### 5.2. Combining with an existing MonthDay

If the initial data consists of a `Year` and a `MonthDay`, `year.atMonthDay(monthDay)` combines them directly into a `LocalDate`.

However, this method also follows the rule of adjusting February 29 back to February 28 in a common year. With the same parts—year 2023, month 2, day 29:

```text
Year.of(2023).atMonth(2).atDay(29)
→ DateTimeException

Year.of(2023).atMonthDay(MonthDay.of(2, 29))
→ 2023-02-28
```

Thus, two call chains that appear to differ only in syntax do not share the same validation contract. Do not swap between them just to shorten code if doing so changes the date-handling policy.

`Year` remains unchanged after these assembly operations. The methods create new result values rather than mutating fields on the original year object. See the assembly methods in [Year](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Year.html).

## 6. Year.atDay and YearMonth.atDay take two different kinds of “day”

This is an easy place to misread because the method names are identical.

| Method | Parameter meaning |
| --- | --- |
| `Year.atDay(int dayOfYear)` | Ordinal day number within the entire year |
| `YearMonth.atDay(int dayOfMonth)` | Day number within the known month |

Examples:

```text
Year.of(2024).atDay(29)          → 2024-01-29
YearMonth.of(2024, 2).atDay(29)  → 2024-02-29

Year.of(2024).atDay(60)          → 2024-02-29
Year.of(2023).atDay(60)          → 2023-03-01
```

`Year.atDay` cannot know that you meant February if you only pass the number 29. It counts from the first day of the year.

Day 366 is only valid in a leap year. `Year.of(2023).atDay(366)` throws an error, whereas 2024 yields December 31. If you already have the year and the day-of-year ordinal, `LocalDate.ofYearDay(year, dayOfYear)` also expresses that exact structure.

All calendar indices in use are 1-based: month 1, first day of month 1, first day of year 1. Do not pass 0 by confusing them with array indices.

## 7. When all three parts are available: use LocalDate.of

When the input consists of a specific year, month, and day, `LocalDate.of` creates a date directly and validates it:

- `LocalDate.of(2024, 2, 29)` is valid.
- `LocalDate.of(2023, 2, 29)` throws `DateTimeException`.
- `LocalDate.of(2024, Month.FEBRUARY, 29)` produces the same result as the numeric month form.

The overload taking `Month` makes the month explicit in code. If the month comes from numeric data, `Month.of(2)` is `Month.FEBRUARY`. Month numbers in `java.time` range from 1..12, not 0-based. To get the month number from the enum, use `getValue()`, not `ordinal()`; see [Month](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Month.html).

There is no need to create an arbitrary base date and sequentially call `withYear`, `withMonth`, and `withDayOfMonth` to assemble the three parts. Intermediate dates can cause unintended adjustments or errors. When all three parts come from the same input, use the direct assembly API that expresses the exact contract.

## 8. Do not auto-fill missing information with from()

`LocalDate.from(temporal)` attempts to extract a complete date from the given data; it does not automatically add day 1 for `YearMonth` or pick the current year for `MonthDay`.

Therefore:

- `LocalDate.from(YearMonth.of(2024, 2))` throws an error because the day is missing.
- `LocalDate.from(MonthDay.of(2, 29))` throws an error because the year is missing.
- `LocalDate.from(Year.of(2024))` throws an error because the month and day are missing.

You must supply the missing part intentionally via `atDay`, `atYear`, `atMonth`, or `of`. If business rules state that “a monthly period is represented by the first day of the month,” write `yearMonth.atDay(1)` and document that convention explicitly. Do not treat it as default conversion behavior.

In the reverse direction, extracting a part from a complete date is valid:

- `Year.from(date)` extracts the year.
- `YearMonth.from(date)` extracts the year-month.
- `MonthDay.from(date)` extracts the month-day.

After extraction, the discarded information is no longer present in the new value. If you need to reassemble the same original date later, you must retain or pass that part back in. The creation and extraction contracts are described in [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

## 9. Java 17+ program verifying the assembly paths

Save the following code as `AssembleLocalDate.java`. This is a standalone program requiring no external libraries.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Month;
import java.time.MonthDay;
import java.time.Year;
import java.time.YearMonth;
import java.util.Objects;

public class AssembleLocalDate {
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

    private static LocalDate attachYearStrict(MonthDay monthDay, int number) {
        Objects.requireNonNull(monthDay, "monthDay");
        Year year = Year.of(number);
        if (!year.isValidMonthDay(monthDay)) {
            throw new DateTimeException("Month-day is invalid in year " + year);
        }
        return year.atMonthDay(monthDay);
    }

    public static void main(String[] args) {
        Year year = Year.of(2024);
        YearMonth period = YearMonth.of(2024, 2);
        MonthDay recurringDay = MonthDay.of(Month.FEBRUARY, 29);
        LocalDate expected = LocalDate.of(2024, 2, 29);

        LocalDate fromYearMonth = period.atDay(29);
        LocalDate fromMonthDay = recurringDay.atYear(2024);
        LocalDate fromYear = year.atMonth(Month.FEBRUARY).atDay(29);
        LocalDate fromParts = LocalDate.of(2024, Month.FEBRUARY, 29);
        eq(fromYearMonth, expected);
        eq(fromMonthDay, expected);
        eq(fromYear, expected);
        eq(fromParts, expected);
        eq(year.atMonthDay(recurringDay), expected);
        eq(attachYearStrict(recurringDay, 2024), expected);

        eq(period.atEndOfMonth(), expected);
        eq(YearMonth.of(2023, 2).atEndOfMonth(), LocalDate.of(2023, 2, 28));
        eq(YearMonth.of(2024, 4).atEndOfMonth(), LocalDate.of(2024, 4, 30));
        eq(period.isValidDay(29), true);
        eq(YearMonth.of(2023, 2).isValidDay(29), false);
        eq(recurringDay.atYear(2023), LocalDate.of(2023, 2, 28));
        eq(Year.of(2023).atMonthDay(recurringDay), LocalDate.of(2023, 2, 28));
        rejects(() -> attachYearStrict(recurringDay, 2023));
        rejects(() -> YearMonth.of(2023, 2).atDay(29));
        rejects(() -> Year.of(2023).atMonth(2).atDay(29));
        rejects(() -> LocalDate.of(2023, 2, 29));
        rejects(() -> MonthDay.of(Month.APRIL, 31));
        rejects(() -> period.atDay(0));
        rejects(() -> YearMonth.of(2024, 13));

        eq(year.atDay(60), expected);
        eq(year.atDay(29), LocalDate.of(2024, 1, 29));
        eq(LocalDate.ofYearDay(2024, 60), expected);
        eq(Year.of(2023).atDay(60), LocalDate.of(2023, 3, 1));
        rejects(() -> Year.of(2023).atDay(366));
        rejects(() -> LocalDate.from(period));
        rejects(() -> LocalDate.from(recurringDay));
        rejects(() -> LocalDate.from(year));

        eq(Year.from(expected), year);
        eq(YearMonth.from(expected), period);
        eq(MonthDay.from(expected), recurringDay);
        eq(year, Year.of(2024));
        eq(period, YearMonth.of(2024, 2));
        eq(recurringDay, MonthDay.of(2, 29));
        eq(Month.of(2), Month.FEBRUARY);

        System.out.println("fromYearMonth=" + fromYearMonth);
        System.out.println("fromMonthDay=" + fromMonthDay);
        System.out.println("fromYear=" + fromYear);
        System.out.println("fromParts=" + fromParts);
        System.out.println("adjustedCommonYear=" + recurringDay.atYear(2023));
        System.out.println("yearAtDay29=" + year.atDay(29));
        System.out.println("yearAtDay60=" + year.atDay(60));
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 AssembleLocalDate.java
java AssembleLocalDate
```

Stdout:

```text
fromYearMonth=2024-02-29
fromMonthDay=2024-02-29
fromYear=2024-02-29
fromParts=2024-02-29
adjustedCommonYear=2023-02-28
yearAtDay29=2024-01-29
yearAtDay60=2024-02-29
PASS checks=35
```

The first four lines show that all assembly paths can produce the same date 2024-02-29 when all parts are present and the date is valid. The `adjustedCommonYear` line demonstrates the specific adjustment rule of attaching a year to `MonthDay`. The next two lines clarify the parameter meaning of `Year.atDay`.

The check helpers actively throw `AssertionError` on failure, so the `-ea` flag is not needed. The `rejects` helper requires an operation to throw `DateTimeException`; if the operation silently accepts the input, the program fails.

The test suite also verifies cases without dedicated print lines: day 0, month 13, April 31, February 29 in a common year via the strict assembly path, and that `LocalDate.from` does not fill in missing parts.

## 10. Choosing an assembly approach in practical scenarios

| Scenario | Suitable approach | Decision needed |
| --- | --- | --- |
| User selects a specific day in a monthly period | `YearMonth.atDay(day)` | Invalid days must report an error |
| Compute the last day of a reporting period | `YearMonth.atEndOfMonth()` | This is an end-of-month selection rule |
| Schedule an anniversary in a chosen year | `MonthDay.atYear(year)` or a pre-check helper | Should Feb 29 be adjusted back? |
| Receive all three fields: year, month, day | `LocalDate.of` | Validate the exact entered date |
| Receive a day-of-year ordinal | `Year.atDay` or `LocalDate.ofYearDay` | Do not confuse with day of month |
| Only have the reporting year, no day yet | Keep `Year` | No need to create `LocalDate` yet |

Not every partial date needs to be forced into a full date immediately. If you are only storing a monthly reporting period, keeping `YearMonth` can express the intent more accurately than adding a dummy day. Only create a `LocalDate` when the next operation genuinely needs a date and the missing part has a clear source or rule.

## 11. Common mistakes and practice

Mistakes to avoid:

- Using `Year.atDay(29)` to represent February 29: that method selects the 29th day of the year.
- Assuming every assembly method rejects invalid dates: `MonthDay.atYear` and `Year.atMonthDay` adjust leap days.
- Using the last day of the month to mask an invalid day entered by the user.
- Letting the current year or the first day of the month appear implicitly in data that only holds part of a date.
- Shifting month numbers from 1..12 to 0..11 due to conventions carried over from other APIs.
- Expecting the original partial objects to turn into fuller objects after a call: these types are immutable, so you must capture the return value.

Practice:

1. **Create the 15th day of period `2025-04`.** Use `YearMonth.of(2025, 4).atDay(15)`; the result is `2025-04-15`.

2. **Create the last day of period `2025-02`.** Use `atEndOfMonth()`; the result is `2025-02-28`. Do not try day 31 expecting the library to fix it.

3. **Attach year 2100 to month-day February 29.** The `atYear` path yields `2100-02-28`; `attachYearStrict` must throw an error. Choose the path matching your requirement before running.

4. **Predict `Year.of(2025).atDay(32)`.** The result is `2025-02-01`, because this is the 32nd day of the year.

5. **Given `Month.APRIL`, year 2025, and day 31.** `LocalDate.of` must reject it. The fact that individual parts look valid does not make their combination a valid date.

Before each assembly operation, identify the data you have, the missing part, and the policy when the combination does not exist. Those three pieces of information determine which `LocalDate` creation method to use.
