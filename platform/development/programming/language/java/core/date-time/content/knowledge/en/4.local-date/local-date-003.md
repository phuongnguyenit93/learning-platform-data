# Reading Year, Month, Day, Day of Week, and Day of Year with `LocalDate`

`java.time.LocalDate` represents **a date in the ISO-8601 calendar** consisting of year, month, and day, **without time-of-day, UTC offset, or time zone**. Once you have a `LocalDate`, Java lets you read the year–month–day components, determine the day of the week, and get the day-of-year ordinal without manually splitting strings or computing calendar dates.

This lesson directly answers six questions: which year, which month, which day of the month, which day of the week, which day of the year a `LocalDate` represents, and how to interpret those results in leap years.

## 1. Creating a `LocalDate` Value to Read

```java
import java.time.LocalDate;

LocalDate date = LocalDate.of(2024, 2, 29);
LocalDate parsed = LocalDate.parse("2024-02-29");

System.out.println(date);                 // 2024-02-29
System.out.println(date.equals(parsed));  // true
```

`LocalDate.of(year, month, dayOfMonth)` takes a **numeric month from 1 to 12**. `LocalDate.parse(...)` by default expects the ISO format `uuuu-MM-dd` such as `2024-02-29`, and does not automatically parse `29/02/2024`. Both methods validate the date: `LocalDate.of(2025, 2, 29)` throws a `DateTimeException` because 2025 has no February 29.

The read methods below do not mutate `date`: `LocalDate` is immutable. If you want a different date, produce a new result using `plusDays`, `withDayOfMonth`, `withDayOfYear`, etc., and keep the returned value.

## 2. Reading Year, Month, and Day of Month

| Purpose | Method | Result for `2024-02-29` | Return type |
| --- | --- | --- | --- |
| ISO calendar year | `getYear()` | `2024` | `int` |
| Month as a number | `getMonthValue()` | `2` | `int` |
| Month as an enum | `getMonth()` | `FEBRUARY` | `Month` |
| Day of the month | `getDayOfMonth()` | `29` | `int` |

```java
LocalDate date = LocalDate.of(2024, 2, 29);

int year = date.getYear();              // 2024
int monthNumber = date.getMonthValue(); // 2
Month month = date.getMonth();          // FEBRUARY
int dayOfMonth = date.getDayOfMonth();  // 29
```

The snippet also requires `import java.time.Month;` when placed in a Java program.

**The numeric month and `Month` serve two different purposes.** `getMonthValue()` is useful for forms, APIs, comparisons against a specific month number, and numeric data; `getMonth()` is useful when you want an enum value with clear meaning, such as `date.getMonth() == Month.FEBRUARY`.

`Month` has 12 constants from `JANUARY` to `DECEMBER`; `Month.FEBRUARY.getValue()` returns `2`. Do not use `month.ordinal()` as the month number: `ordinal()` is the **0-based** enum index, whereas ISO months start at **1**.

`getDayOfMonth()` returns a value from 1 to the length of the corresponding month. For example, February 2024 has 29 days, February 2025 has 28 days, April has 30 days, and December has 31 days. Avoid assuming all months have 30 days.

### Formatting the Month Name for Humans

The enum name `FEBRUARY` is meant for source code and is not always suitable for UI display. To display it, you can use:

```java
String monthName = date.getMonth()
        .getDisplayName(TextStyle.FULL, Locale.ENGLISH);
System.out.println(monthName); // February
```

This requires `import java.time.format.TextStyle;` and `import java.util.Locale;`. Use `Locale.forLanguageTag("vi-VN")` when you need Vietnamese month names; the display form may depend on the Java environment's locale data. Do not compare display names to drive business logic: compare `Month` or the numeric month instead.

## 3. Reading the Day of the Week: `getDayOfWeek()`

`LocalDate.getDayOfWeek()` returns a `DayOfWeek`, an enum from `MONDAY` to `SUNDAY`. By ISO-8601 convention, **Monday is 1, Tuesday is 2, …, Sunday is 7**.

```java
LocalDate date = LocalDate.of(2024, 2, 29);

DayOfWeek day = date.getDayOfWeek(); // THURSDAY
int isoDayNumber = day.getValue();   // 4
```

The snippet requires `import java.time.DayOfWeek;`.

| Day | `DayOfWeek` | ISO `getValue()` |
| --- | --- | ---: |
| Monday | `MONDAY` | 1 |
| Tuesday | `TUESDAY` | 2 |
| Wednesday | `WEDNESDAY` | 3 |
| Thursday | `THURSDAY` | 4 |
| Friday | `FRIDAY` | 5 |
| Saturday | `SATURDAY` | 6 |
| Sunday | `SUNDAY` | 7 |

Use the enum directly to express business rules:

```java
DayOfWeek dow = date.getDayOfWeek();

boolean weekend = dow == DayOfWeek.SATURDAY
               || dow == DayOfWeek.SUNDAY;
```

This defines a **weekend by the Saturday/Sunday rule**; an organization's or country's work schedule may differ. `DayOfWeek` only returns the **day of the week** and does not determine public holidays.

Keep two concepts separate:

- **Day of the week:** `getDayOfWeek()` always follows the ISO enum, and `DayOfWeek.getValue()` always defines Monday = 1.
- **Which day starts the week when rendering a calendar or computing week numbers:** this can depend on country/locale and uses `WeekFields`; configuring a locale for formatting does not change the enum value returned by `getDayOfWeek()`.

To display the day name instead of `THURSDAY`:

```java
String englishDay = date.getDayOfWeek()
        .getDisplayName(TextStyle.FULL, Locale.ENGLISH);
System.out.println(englishDay); // Thursday
```

If you need Vietnamese, use `Locale.forLanguageTag("vi-VN")` and `TextStyle.FULL` or `SHORT`. Do not slice the string `"THURSDAY"` yourself or rely on `ordinal()` to get the weekday number.

## 4. Reading the Day of the Year: `getDayOfYear()`

`getDayOfYear()` returns the **1-based day ordinal counted from January 1 of the same year**, starting at **1**, not 0.

```java
LocalDate jan1 = LocalDate.of(2024, 1, 1);
LocalDate feb29 = LocalDate.of(2024, 2, 29);
LocalDate dec31 = LocalDate.of(2024, 12, 31);

System.out.println(jan1.getDayOfYear());  // 1
System.out.println(feb29.getDayOfYear()); // 60
System.out.println(dec31.getDayOfYear()); // 366
```

In a **common year**, `getDayOfYear()` ranges from **1 to 365**; in a **leap year**, from **1 to 366**. The ordinal is shifted by February 29:

| Date | Year | `getDayOfYear()` | Explanation |
| --- | ---: | ---: | --- |
| 01/01/2024 | Leap | 1 | First day of the year |
| 28/02/2024 | Leap | 59 | Before leap day |
| 29/02/2024 | Leap | 60 | Leap day |
| 01/03/2024 | Leap | 61 | After leap day |
| 28/02/2025 | Common | 59 | No February 29 |
| 01/03/2025 | Common | 60 | One fewer day than in a leap year |
| 31/12/2024 | Leap | 366 | Last day of the year |
| 31/12/2025 | Common | 365 | Last day of the year |

Two dates with the same day-of-year ordinal **do not necessarily share the same month and day**. Day 60 of 2024 is **February 29**, whereas day 60 of 2025 is **March 1**. When storing data by day-of-year, you must keep the **year** alongside it; the ordinal alone does not uniquely identify a date.

**`getDayOfYear()` is not `getDayOfMonth()`**: on 2024-02-29, `getDayOfMonth() == 29` while `getDayOfYear() == 60`.

### Creating a Date from the Day-of-Year Ordinal

The inverse of `getDayOfYear()` is `LocalDate.ofYearDay(year, dayOfYear)`:

```java
LocalDate a = LocalDate.ofYearDay(2024, 60); // 2024-02-29
LocalDate b = LocalDate.ofYearDay(2025, 60); // 2025-03-01
```

`LocalDate.ofYearDay(2025, 366)` is invalid and throws `DateTimeException`. Given an existing date, `date.withDayOfYear(1)` returns January 1 of the **same year** without modifying `date`.

Do not conflate "day of the year" with "week of the year" or "business day of the year". Holidays, weekends, fiscal calendars, and week definitions are separate rules that `getDayOfYear()` does not automatically exclude or compute.

## 5. Checking Leap Years and Month/Year Lengths

To inspect the valid range of a date, use the API directly:

```java
LocalDate leap = LocalDate.of(2024, 2, 29);
LocalDate normal = LocalDate.of(2025, 2, 28);

System.out.println(leap.isLeapYear());   // true
System.out.println(leap.lengthOfYear()); // 366
System.out.println(leap.lengthOfMonth());// 29

System.out.println(normal.isLeapYear());   // false
System.out.println(normal.lengthOfYear()); // 365
System.out.println(normal.lengthOfMonth());// 28
```

In the Gregorian/ISO calendar used by `LocalDate`, a year divisible by 4 is generally a leap year, **except** years divisible by 100 that are **not** divisible by 400. For example, 2000 is a leap year, 1900 is not, 2024 is a leap year, and 2025 is not. Prefer `isLeapYear()` over reimplementing the rule yourself when you already have a `LocalDate`.

For any month, `lengthOfMonth()` reflects that month in its specific year. To get the last day of the month:

```java
LocalDate lastDay = date.withDayOfMonth(date.lengthOfMonth());
```

This works safely for February in both leap and common years; do not hardcode constants like 28/29/30/31 across months.

## 6. Reading Fields via `ChronoField` for Generic APIs

Direct getters are the most readable choice for everyday code. However, `LocalDate` also provides the generic `TemporalAccessor.get(TemporalField)` API:

| Direct getter | Equivalent field API |
| --- | --- |
| `getYear()` | `get(ChronoField.YEAR)` |
| `getMonthValue()` | `get(ChronoField.MONTH_OF_YEAR)` |
| `getDayOfMonth()` | `get(ChronoField.DAY_OF_MONTH)` |
| `getDayOfWeek().getValue()` | `get(ChronoField.DAY_OF_WEEK)` |
| `getDayOfYear()` | `get(ChronoField.DAY_OF_YEAR)` |

```java
LocalDate date = LocalDate.of(2024, 2, 29);
int ordinal = date.get(ChronoField.DAY_OF_YEAR); // 60
```

(Requires `import java.time.temporal.ChronoField;`.)

`ChronoField` is suitable for functions that process temporal fields dynamically, though not every `TemporalAccessor` supports every field. For example, `LocalTime` does not have a `YEAR` field; when writing generic code, check `isSupported(field)` or handle `UnsupportedTemporalTypeException`.

The day-of-week number from `ChronoField.DAY_OF_WEEK` is still Monday = 1, Sunday = 7. If you need the **locale-specific day-of-week number**, you can use `WeekFields.of(locale).dayOfWeek()`, whose result depends on the first day of the week in that locale. That field has different semantics from `ChronoField.DAY_OF_WEEK`; do not silently interchange them.

## 7. Reading from a Fixed Date vs. Reading "Today"

`LocalDate.of(2024, 2, 29)` is a fixed value, and its getters always return the same results. `LocalDate.now()`, on the other hand, reads the date using the **JVM's default time zone** and the system clock at the time of the call. If the system runs on a machine with a different time zone, the same UTC instant can yield a different calendar date.

For example, at `2024-02-29T18:30:00Z`:

- In UTC: it is still **2024-02-29**.
- In `Asia/Ho_Chi_Minh` (UTC+07 at this time): it is already **2024-03-01**.

```java
Instant instant = Instant.parse("2024-02-29T18:30:00Z");

LocalDate utcDate = LocalDate.ofInstant(instant, ZoneOffset.UTC);
LocalDate vietnamDate = LocalDate.ofInstant(
        instant, ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(utcDate);     // 2024-02-29
System.out.println(vietnamDate); // 2024-03-01
```

This requires `import java.time.Instant;`, `import java.time.ZoneOffset;`, and `import java.time.ZoneId;`. `LocalDate.ofInstant` was added in Java 9, so it is available in Java 17+. It converts **an instant to a calendar date in a specific zone**; the resulting `LocalDate` itself still stores no time zone.

For business logic meaning "today in the Vietnam market", specify the zone explicitly, such as `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))`. To test without depending on real wall-clock time, pass a fixed `Clock`:

```java
Clock clock = Clock.fixed(
        Instant.parse("2024-02-29T18:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate today = LocalDate.now(clock); // 2024-03-01
```

Note that `LocalDate.now()` does not expose hours or minutes; calling `getDayOfWeek()` or `getDayOfYear()` on a chosen date always reflects that **calendar date**, not a duration from the start of the year in seconds. If your input is an `Instant` or `ZonedDateTime`, decide on the business time zone **before** converting to `LocalDate`.

## 8. Complete Java 17+ Example

Create the file **`LocalDateFieldsDemo.java`**:

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.DayOfWeek;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Month;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class LocalDateFieldsDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);

        System.out.println("date = " + date);
        System.out.println("year = " + date.getYear());
        System.out.println("month value = " + date.getMonthValue());
        System.out.println("month enum = " + date.getMonth());
        System.out.println("day of month = " + date.getDayOfMonth());
        System.out.println("day of week = " + date.getDayOfWeek());
        System.out.println("ISO weekday number = "
                + date.getDayOfWeek().getValue());
        System.out.println("day of year = " + date.getDayOfYear());
        System.out.println("ChronoField ordinal = "
                + date.get(ChronoField.DAY_OF_YEAR));
        System.out.println("leap year = " + date.isLeapYear());
        System.out.println("days in month = " + date.lengthOfMonth());
        System.out.println("days in year = " + date.lengthOfYear());

        System.out.println("month in English = "
                + date.getMonth().getDisplayName(
                        TextStyle.FULL, Locale.ENGLISH));
        System.out.println("weekday in English = "
                + date.getDayOfWeek().getDisplayName(
                        TextStyle.FULL, Locale.ENGLISH));

        LocalDate day60Leap = LocalDate.ofYearDay(2024, 60);
        LocalDate day60Normal = LocalDate.ofYearDay(2025, 60);
        System.out.println("2024 day 60 = " + day60Leap);
        System.out.println("2025 day 60 = " + day60Normal);

        boolean invalidDay366 = false;
        try {
            LocalDate.ofYearDay(2025, 366);
        } catch (DateTimeException ex) {
            invalidDay366 = true;
        }
        System.out.println("2025 day 366 invalid = " + invalidDay366);

        DayOfWeek weekday = date.getDayOfWeek();
        boolean weekend = weekday == DayOfWeek.SATURDAY
                || weekday == DayOfWeek.SUNDAY;
        System.out.println("weekend by Sat/Sun rule = " + weekend);
        System.out.println("month enum comparison = "
                + (date.getMonth() == Month.FEBRUARY));

        Instant instant = Instant.parse("2024-02-29T18:30:00Z");
        System.out.println("UTC date = "
                + LocalDate.ofInstant(instant, ZoneOffset.UTC));
        System.out.println("Vietnam date = "
                + LocalDate.ofInstant(
                        instant, ZoneId.of("Asia/Ho_Chi_Minh")));

        Clock fixedClock = Clock.fixed(
                instant, ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("fixed today = " + LocalDate.now(fixedClock));
        System.out.println("original unchanged = " + date);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LocalDateFieldsDemo.java
java LocalDateFieldsDemo
```

Expected output on a JDK with standard locale data:

```text
date = 2024-02-29
year = 2024
month value = 2
month enum = FEBRUARY
day of month = 29
day of week = THURSDAY
ISO weekday number = 4
day of year = 60
ChronoField ordinal = 60
leap year = true
days in month = 29
days in year = 366
month in English = February
weekday in English = Thursday
2024 day 60 = 2024-02-29
2025 day 60 = 2025-03-01
2025 day 366 invalid = true
weekend by Sat/Sun rule = false
month enum comparison = true
UTC date = 2024-02-29
Vietnam date = 2024-03-01
fixed today = 2024-03-01
original unchanged = 2024-02-29
```

The example demonstrates both direct getters and `ChronoField`, the difference in day-of-year ordinals between leap and common years, handling invalid dates, and the effect of time zones when converting an `Instant` to a calendar date. The input `LocalDate` is always immutable; read-only operations cannot alter it.

## 9. Common Pitfalls and How to Handle Them

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Using `getMonth().ordinal()` for the month number | January becomes 0, December becomes 11 | Use `getMonthValue()` or `getMonth().getValue()` |
| Assuming `getDayOfWeek().getValue()` returns Sunday = 1 | Off-by-one mismatch with ISO convention | ISO: Monday = 1, Sunday = 7 |
| Counting `getDayOfYear()` from 0 | Off by one starting from January 1 | January 1 has ordinal = 1 |
| Confusing `getDayOfMonth()` and `getDayOfYear()` | February 29 is treated as day 29 of the year | Choose the getter matching the unit you want |
| Assuming March 1 is always day 60 | Leap years have February 29 | Check `isLeapYear()` and `getDayOfYear()` |
| Calling `ofYearDay(year, 366)` for any year | Common years throw an exception | Check `lengthOfYear()` or handle `DateTimeException` |
| Reading "today" with the default time zone in multi-zone systems | May differ from the business date | Specify a `ZoneId` or pass a `Clock` |
| Using localized day/month names in business logic | Fragile across locales, casing, and abbreviations | Use the `DayOfWeek`/`Month` enums |
| Assuming `LocalDate` stores time or offset | Cannot derive an instant from a pure date | Keep zone/time in another business layer when needed |
| Manually splitting `"2024-02-29"` to compute weekday or ordinal | Error-prone leap-year and calendar logic | Parse into `LocalDate` and use the dedicated API |

## 10. Practical Applications

### Displaying Calendar Date Information

When a user selects a date, you can extract numeric day/month/year values for forms, read the weekday enum, and format localized day/month names for the UI. Business data should store `LocalDate` rather than pre-translated weekday names as the source of truth, since user language settings can change.

### Indexing by Day of Year

If a report needs to identify "the 120th day of the year", use `getDayOfYear()`. When storing or grouping, use the composite key **(year, day of year)** or the full ISO date. The calendar month/day corresponding to a given ordinal can differ between leap and common years.

### End-of-Month Checks

If a payroll schedule runs on the last day of the month, use `date.getDayOfMonth() == date.lengthOfMonth()` instead of `getDayOfMonth() == 31`. This works accurately for February and 30-day months alike.

### Weekday-Based Work Schedules

If you only need to exclude Saturdays and Sundays, compare directly against `DayOfWeek.SATURDAY` and `DayOfWeek.SUNDAY`. If you need public holidays or custom workweeks, add a business calendar; `LocalDate.getDayOfWeek()` does not know which days are holidays.

## 11. Self-Check

1. What is `LocalDate.of(2024, 2, 29).getDayOfMonth()`? → **29**.
2. For the same date, what is `getDayOfYear()`? → **60**.
3. What does `getDayOfWeek()` return for 2024-02-29? → `THURSDAY`, `getValue() == 4`.
4. Why does `LocalDate.ofYearDay(2024, 60)` differ from `LocalDate.ofYearDay(2025, 60)`? → 2024 is a leap year so day 60 is Feb 29; 2025 is a common year so day 60 is Mar 1.
5. Should you call `getMonth().ordinal() + 1` to get the month number? → Even though it yields 1–12 for the current enum, use **`getMonthValue()`** because it expresses the intent directly and avoids depending on enum ordinals.
6. At the same instant, why can the UTC date and Vietnam date differ? → One instant can fall on two different calendar dates when converted to different time zones.
7. When you want the current date for a specific business zone, what should you use? → `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))`, or `LocalDate.now(clock)` for testability.

**Takeaway:** `getYear()`, `getMonthValue()`/`getMonth()`, `getDayOfMonth()`, `getDayOfWeek()`, and `getDayOfYear()` read **different aspects of a calendar date**. ISO days of the week start with Monday = 1; day-of-year ordinals start at 1 and depend on leap years. When determining "today" from a real-world instant, choose the time zone before reading `LocalDate`.
