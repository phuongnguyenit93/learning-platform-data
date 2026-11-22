# LocalDate: Creating a Date from Year, Month, Day, and Day of Year

`LocalDate` in the Java Date-Time API (`java.time`) represents **a date in the ISO-8601 calendar**, for example `2024-02-29`. It has a year, month, and day, but **contains no time of day, time zone, or UTC offset**. When a system receives date data in two different forms — **year/month/day** or **year/day-of-year** — we can create the same `LocalDate` using different factory methods.

After this lesson, you can:
- Use `LocalDate.of(year, month, dayOfMonth)` and its `Month` overload to create a calendar date.
- Use `LocalDate.ofYearDay(year, dayOfYear)` when the input is an ordinal day number within the year.
- Convert between the two representations via `getYear()`, `getMonthValue()`, `getDayOfMonth()`, and `getDayOfYear()`.
- Properly handle leap years, February 29, and invalid inputs, avoiding confusing day-of-year with epoch day.

## 1. Two Ways to Describe the Same Date

Suppose we have the date **29/02/2024**. That date can be described in two ways:

| Representation | Input data | Meaning |
|---|---|---|
| Year, month, day of month | `year=2024`, `month=2`, `dayOfMonth=29` | Day 29 of month 2 in year 2024 |
| Year and day of year | `year=2024`, `dayOfYear=60` | The 60th day counting from 01/01/2024 |

Both are **the same calendar date**: because 2024 is a leap year, February has 29 days. Counting from 01/01: 31 days in January + 29 days in February = **day 60 is 29/02**.

The `dayOfYear` ordinal is **1-based**, so 01/01 is always day 1. The maximum value is **365** in a common year or **366** in a leap year. This is not a 0-based array index.

## 2. Creating a Date from Year, Month, Day: `LocalDate.of(...)`

Java provides two main overloads:

~~~java
LocalDate date1 = LocalDate.of(2024, 2, 29);
LocalDate date2 = LocalDate.of(2024, Month.FEBRUARY, 29);
~~~

Required imports:

~~~java
import java.time.LocalDate;
import java.time.Month;
~~~

**Overload 1 — month as an integer:**

~~~java
LocalDate.of(int year, int month, int dayOfMonth)
~~~

- `year`: year in the ISO calendar (e.g., 2024).
- `month`: **1 to 12**; `1` is January, `12` is December.
- `dayOfMonth`: day from 1 to the actual number of days in **the specific month of the specific year**. Values 1–31 are not always valid.
- Result: a `LocalDate` object, e.g., `2024-02-29`.

**Overload 2 — month as the `Month` enum:**

~~~java
LocalDate.of(int year, Month month, int dayOfMonth)
~~~

- `Month.JANUARY`, `Month.FEBRUARY`, ..., `Month.DECEMBER` describe the month using a strongly typed name.
- Use this when the code already has a `Month` variable or when you want more self-documenting code: `LocalDate.of(2024, Month.FEBRUARY, 29)`.
- `Month.FEBRUARY.getValue()` returns `2`; conversely, `Month.of(2)` returns `Month.FEBRUARY`.
- Both overloads create the same date; do not write `Month` and add/subtract 1 like an array index.

`LocalDate.of` **validates the date**. Cases such as `month=0`, `month=13`, `dayOfMonth=0`, `2023-02-29`, and `2024-04-31` are rejected with `DateTimeException`. A valid date depends on **both the month and the year**, not just whether the day is in the range 1–31.

`LocalDate` objects are *immutable*; creating or computing a new date does not modify an existing date.

## 3. Creating a Date from Year and Day of Year: `ofYearDay(...)`

When the input data contains the year and the ordinal day number within the year, use:

~~~java
LocalDate.ofYearDay(int year, int dayOfYear)
~~~

Examples:

~~~java
LocalDate first = LocalDate.ofYearDay(2024, 1);    // 2024-01-01
LocalDate sixtieth = LocalDate.ofYearDay(2024, 60); // 2024-02-29
LocalDate last = LocalDate.ofYearDay(2024, 366);    // 2024-12-31
~~~

In the common year `2023`, the same `dayOfYear=60` is **01/03/2023**. The ordinal day **depends on the year**, especially for dates from March onward when comparing a leap year and a common year.

| `dayOfYear` | Year 2023 (non-leap) | Year 2024 (leap) |
|---:|---|---|
| `1` | `2023-01-01` | `2024-01-01` |
| `31` | `2023-01-31` | `2024-01-31` |
| `32` | `2023-02-01` | `2024-02-01` |
| `59` | `2023-02-28` | `2024-02-28` |
| `60` | `2023-03-01` | `2024-02-29` |
| `61` | `2023-03-02` | `2024-03-01` |
| `365` | `2023-12-31` | `2024-12-30` |
| `366` | **Invalid** | `2024-12-31` |

`LocalDate.ofYearDay(2023, 366)` throws `DateTimeException`. Similarly, `dayOfYear=0` or negative values are always invalid.

**Do not confuse `ofYearDay` with `ofEpochDay`.** `LocalDate.ofYearDay(2024, 60)` means "the 60th day of the year 2024". `LocalDate.ofEpochDay(60)` means "60 days after 1970-01-01 under epoch-day counting"; that is a different coordinate system.

## 4. Reading Fields to Verify Results or Convert Both Ways

After creating a `LocalDate`, use the corresponding getters:

| Method | For `2024-02-29` | Meaning |
|---|---|---|
| `getYear()` | `2024` | Year |
| `getMonth()` | `Month.FEBRUARY` | Month as an enum |
| `getMonthValue()` | `2` | Month as a number 1–12 |
| `getDayOfMonth()` | `29` | Day of month |
| `getDayOfYear()` | `60` | Day of year |

~~~java
LocalDate original = LocalDate.of(2024, 2, 29);

int year = original.getYear();             // 2024
int ordinal = original.getDayOfYear();     // 60
LocalDate restored = LocalDate.ofYearDay(year, ordinal);
// restored.equals(original) == true
~~~

In the reverse direction:

~~~java
LocalDate fromOrdinal = LocalDate.ofYearDay(2024, 60);
LocalDate fromParts = LocalDate.of(
        fromOrdinal.getYear(),
        fromOrdinal.getMonthValue(),
        fromOrdinal.getDayOfMonth());
// fromParts.equals(fromOrdinal) == true
~~~

This is a useful property when reading/writing CSV or JSON that stores year + ordinal day: if both the year and the ordinal day are valid, you can construct a `LocalDate` and then extract the exact year/month/day components back.

**Distinguish three easily confused concepts:**

- `getDayOfMonth()`: the day number **within the month**, e.g., 29.
- `getDayOfYear()`: the day number **within the year**, e.g., 60.
- `getDayOfWeek()`: **the day of the week**, returning a `DayOfWeek` such as `THURSDAY` for 29/02/2024. This is not the number of days elapsed in the year.

## 5. Leap Years: Why Do They Affect `dayOfYear`?

According to the proleptic ISO/Gregorian calendar rules used by `LocalDate`:
- A year divisible by 4 is generally a leap year.
- A year divisible by 100 is **not** a leap year, unless it is also divisible by 400.
- Therefore, 2024 and 2000 are leap years; 2023 and 1900 are not.

Java already provides APIs to handle these rules; there is no need to write the calculation yourself to create a date:

~~~java
boolean leap = Year.isLeap(2024); // true
LocalDate date = LocalDate.of(2024, 2, 29);
boolean dateYearIsLeap = date.isLeapYear(); // true
int daysInYear = date.lengthOfYear();       // 366
int daysInMonth = date.lengthOfMonth();     // 29
~~~

You must import `java.time.Year` if using `Year.isLeap(...)`.

Valid values for `dayOfYear` can be checked using `lengthOfYear()` on a date in that year, or using `Year.of(year).length()`, which returns 365 or 366. `YearMonth.of(year, month).isValidDay(day)` helps validate year/month/day input before creating the object.

**Do not manually add fixed day counts to convert `dayOfYear` to month and day**, especially after February. Use `LocalDate.ofYearDay`: the library automatically handles leap years and month boundaries.

## 6. Standalone Java 17 Program

Create the file **`LocalDateCreationDemo.java`**:

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Month;
import java.time.Year;
import java.time.YearMonth;

public class LocalDateCreationDemo {
    public static void main(String[] args) {
        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        LocalDate byMonth = LocalDate.of(2024, Month.FEBRUARY, 29);
        LocalDate byDayOfYear = LocalDate.ofYearDay(2024, 60);

        System.out.println("from parts = " + leapDay);
        System.out.println("from Month = " + byMonth);
        System.out.println("from day-of-year = " + byDayOfYear);
        System.out.println("three dates equal = "
                + (leapDay.equals(byMonth) && byMonth.equals(byDayOfYear)));
        System.out.println("2024-02-29 ordinal = " + leapDay.getDayOfYear());
        System.out.println("2024-03-01 ordinal = "
                + LocalDate.of(2024, 3, 1).getDayOfYear());
        System.out.println("2023 ordinal 60 = " + LocalDate.ofYearDay(2023, 60));
        System.out.println("2024 ordinal 366 = " + LocalDate.ofYearDay(2024, 366));
        System.out.println("2024 is leap = " + Year.isLeap(2024));
        System.out.println("2023 is leap = " + Year.isLeap(2023));
        System.out.println("2024 Feb 29 valid = "
                + YearMonth.of(2024, 2).isValidDay(29));
        System.out.println("2023 Feb 29 valid = "
                + YearMonth.of(2023, 2).isValidDay(29));
        System.out.println("2024 length = " + leapDay.lengthOfYear());

        try {
            LocalDate.of(2023, 2, 29);
        } catch (DateTimeException e) {
            System.out.println("invalid calendar date rejected");
        }

        try {
            LocalDate.ofYearDay(2023, 366);
        } catch (DateTimeException e) {
            System.out.println("invalid ordinal day rejected");
        }
    }
}
~~~

Run in the directory containing the file using JDK 17 or later:

~~~bash
javac LocalDateCreationDemo.java
java LocalDateCreationDemo
~~~

Verified output when compiled with `javac --release 17`:

~~~text
from parts = 2024-02-29
from Month = 2024-02-29
from day-of-year = 2024-02-29
three dates equal = true
2024-02-29 ordinal = 60
2024-03-01 ordinal = 61
2023 ordinal 60 = 2023-03-01
2024 ordinal 366 = 2024-12-31
2024 is leap = true
2023 is leap = false
2024 Feb 29 valid = true
2023 Feb 29 valid = false
2024 length = 366
invalid calendar date rejected
invalid ordinal day rejected
~~~

**Output explanation:**

1. All three ways of constructing `2024-02-29` produce objects with equal values.
2. 29/02 is day **60** in the leap year 2024; the next day (01/03) is day **61**.
3. The common year 2023 has no 29/02; day 60 falls on **01/03**.
4. A leap year is 366 days long, with day 366 being 31/12; a common year has only 365 days.
5. Validation APIs help avoid creating invalid dates; if invalid data is still passed to a factory, `DateTimeException` is thrown and the program can handle it at the input boundary.

Catching `DateTimeException` in the example is used to demonstrate error behavior. In a real application, you should explain the input error to the user or return a validation message in the API, rather than silently ignoring it.

## 7. Applying with Input Data and Common Pitfalls

### Case: Receiving Three Components from a Form

For example, a form provides `year=2024`, `month=2`, `day=29`. With data already parsed into integers and checked for input constraints, you can use:

~~~java
int year = 2024;
int month = 2;
int day = 29;
YearMonth yearMonth = YearMonth.of(year, month);
if (!yearMonth.isValidDay(day)) {
    throw new IllegalArgumentException("Ngày không tồn tại trong tháng và năm");
}
LocalDate result = LocalDate.of(year, month, day);
~~~

*This snippet is illustrative code inside a method* and requires importing `LocalDate` and `YearMonth`. If `month` or `year` itself is out of valid range, `YearMonth.of(...)` can also throw `DateTimeException`; exceptions must be handled at the input boundary. `isValidDay(...)` is a way to query whether a day of month is valid, but it does not completely replace handling invalid input data.

### Case: Receiving Year and Ordinal Day

A data source might store two columns `year=2024` and `ordinalDay=60`, instead of three columns year/month/day:

~~~java
int year = 2024;
int ordinalDay = 60;
int daysInYear = Year.of(year).length();
if (ordinalDay < 1 || ordinalDay > daysInYear) {
    throw new IllegalArgumentException("Ngày thứ tự ngoài phạm vi của năm");
}
LocalDate result = LocalDate.ofYearDay(year, ordinalDay);
~~~

*This snippet is also illustrative code inside a method*, with imports `java.time.Year` and `java.time.LocalDate`. `Year.of(year)` can throw an exception if the year is outside the supported range. The key point is that the length of the year must be determined by **the specific year under consideration**.

### Common Mistakes

| Mistake | What happens | How to handle |
|---|---|---|
| Using month `0` for January | Months in `LocalDate.of` start at 1; `0` is invalid | Use `1` for January |
| Using day `0` for 01/01 | `ofYearDay(year, 0)` is invalid | Use `1` for 01/01 |
| Assuming 29/02 is valid in every year | `LocalDate.of(2023, 2, 29)` throws `DateTimeException` | Check leap year or use `YearMonth.isValidDay` |
| Assuming day 60 is always 01/03 | Wrong in leap years | Call `ofYearDay(year, 60)` with the corresponding year |
| Assuming day 366 exists in every year | Common years only have 365 days | Use `Year.of(year).length()` or handle the exception |
| Confusing `dayOfYear` and `dayOfMonth` | One is within the year, the other within the month | Use `getDayOfYear()` and `getDayOfMonth()` properly |
| Confusing `ofYearDay` and `ofEpochDay` | Epoch day counts from 1970-01-01, not reset each year | Use the factory matching the data contract |
| Calculating day count manually with `(month-1)*30+day` | Months have different lengths and leap years exist | Use `LocalDate` to convert |
| Using `LocalDate.now()` to verify fixed examples | Results depend on the environment clock/time zone | Use `of` / `ofYearDay` with fixed data when learning and testing |
| Thinking `LocalDate` contains UTC time | It is only a calendar date, with no time zone | Only attach a `ZoneId` when interpreting it as an actual instant |

**Scope note:** A calendar date is different from a timestamp. Both `LocalDate.of(2024, 2, 29)` and `LocalDate.ofYearDay(2024, 60)` create a **date**, not a unique UTC instant. To convert a calendar date to a specific instant, you must have rules for the time zone and time of day, for example `date.atStartOfDay(zone)`. Such interpretation is a separate business step.

## 8. Self-Check

1. What is `getDayOfYear()` for `2024-01-01`? **1**, not 0.
2. What date does `LocalDate.ofYearDay(2024, 60)` create? **2024-02-29**.
3. What date does `LocalDate.ofYearDay(2023, 60)` create? **2023-03-01**.
4. Given `year=2024, month=2, day=29`, are the two overloads `of(2024,2,29)` and `of(2024, Month.FEBRUARY,29)` equal? **Yes**.
5. Why does `LocalDate.ofYearDay(2023, 366)` fail? Because **2023 is not a leap year** and only has **365** days.
6. Which method gets the number of days in the current year from a `LocalDate`? **`lengthOfYear()`**; to check for a leap year, use **`isLeapYear()`**.
7. If the input is `year=2024, ordinalDay=61`, what is the date? **2024-03-01**.
8. Can `LocalDate.ofYearDay(2024, 60)` be replaced by `LocalDate.ofEpochDay(60)`? **No**, because the meanings of the two `60` values are different.

**Key takeaway:** Create a date from **year–month–day** with `LocalDate.of(...)`; create a date from **year–day-of-year** with `LocalDate.ofYearDay(...)`. Use `getDayOfYear()` to read back the ordinal day, which is always **1-based**, and always account for **leap years** when working with 29/02 or day 366.

### References

- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html)
- [Java SE 17 — Year](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Year.html)
- [Java SE 17 — YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html)
- [Java SE 17 — Month](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Month.html)
