# Month and DayOfWeek Are Calendar-Aware Enums

## 1. Why not just use numbers or strings?

`Month.MARCH` clearly states "March"; `DayOfWeek.MONDAY` clearly states "Monday". In a call such as `LocalDate.of(2024, Month.MARCH, 15)`, the enum type helps the reader understand the role of the data right at the call site and avoids passing an unnamed number by mistake.

These are not just two lists of constants. They know ISO calendar values, how to shift cyclically, how to retrieve display names, and how to adjust a date. However, each enum still represents only **part of a date**, not a complete date.

| Type | Represents | What is missing |
| --- | --- | --- |
| `Month` | One of the 12 months | Year and day of month |
| `DayOfWeek` | One of the 7 days of the week | Which week, which month, which year |
| `LocalDate` | A specific date in the ISO calendar | Time of day and time zone |

For example, `Month.FEBRUARY` cannot answer whether February has 28 or 29 days without knowing whether it is a leap year. Likewise, `DayOfWeek.FRIDAY` is not yet an appointment for "next Friday".

## 2. ISO values differ from ordinal

`Month.getValue()` returns 1 to 12, with January as 1. `DayOfWeek.getValue()` returns 1 to 7, with Monday as 1 and Sunday as 7.

```java
Month month = Month.of(3);                   // MARCH
int monthNumber = Month.MARCH.getValue();    // 3
DayOfWeek day = DayOfWeek.of(1);             // MONDAY
int sundayNumber = DayOfWeek.SUNDAY.getValue(); // 7
```

The snippet above is illustrative code inside a method and requires importing `java.time.Month` and `java.time.DayOfWeek`.

`ordinal()` is the zero-based enum declaration position, not the calendar number. `Month.JANUARY.ordinal()` is 0, whereas the actual month number is 1. Use `getValue()` for numeric representation according to the calendar contract, and `of(number)` to convert back with range validation. [Month](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Month.html)

`Month.of(0)`, `Month.of(13)`, or `DayOfWeek.of(0)` are invalid and throw `DateTimeException`. Do not use `values()[number]` as a calendar-number conversion: that approach both uses the wrong index base and produces an error type that does not reflect the data domain.

When integrating with legacy APIs, map explicitly: `Calendar` uses zero-based months and a different day-of-week numbering convention than `DayOfWeek`. Do not pass those numbers directly into `java.time` APIs without checking the source contract.

## 3. Converting from a date, comparing, and identifying

From a `LocalDate`, retrieve the enums via `getMonth()` and `getDayOfWeek()`. You can use `Month.from(date)` or `DayOfWeek.from(date)` when receiving a general temporal source that contains sufficient information.

Enums can be compared with `==`, used in `switch`, or used as `EnumMap` keys or `EnumSet` elements. For example, a set of closed days does not need to be a hard-to-read set of numbers 6 and 7.

`valueOf("MARCH")` parses the **exact constant name** and is case-sensitive; it does not understand `"March"`, `"tháng 3"`, or `"03"`. A string that does not match a constant name throws `IllegalArgumentException`, unlike an out-of-range number passed to `of`.

`name()` and `toString()` represent the constant name such as `MONDAY`; they are not localized names for a user interface. If you store constant names in interchange data, clearly document that convention and validate inputs.

## 4. Addition and subtraction on enums wrap around

`Month.DECEMBER.plus(2)` yields `FEBRUARY`; `DayOfWeek.SUNDAY.plus(1)` yields `MONDAY`. The `plus(long)`/`minus(long)` operations work cyclically over 12 months or 7 days and also accept negative amounts.

They **do not track the number of cycles elapsed**: adding two months to the December enum does not produce a new year; adding 7 to a day of the week returns that exact same day. To advance an actual date and preserve the year and month, perform the operation on `LocalDate`.

Similarly, the natural order of the enums from January to December or Monday to Sunday does not tell you the nearest next occurrence from today. Sunday has a higher number than Monday, yet the next Monday may be only one day after Sunday. [DayOfWeek](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html)

## 5. Month provides month information but needs year context

| Method | Purpose |
| --- | --- |
| `length(leapYear)` | Number of days in the month given whether it is a leap year |
| `minLength()` / `maxLength()` | Minimum and maximum number of days in the month |
| `firstDayOfYear(leapYear)` | Day-of-year number for the first day of the month |
| `firstMonthOfQuarter()` | First month of the quarter containing the current month |

For February, `length(false)` is 28 and `length(true)` is 29. The `leapYear` flag is information supplied by the caller; `Month` does not know the year on its own. When you already have a date, `date.lengthOfMonth()` or `YearMonth.lengthOfMonth()` usually expresses the intent more clearly.

Illustrative snippet inside a method:

```java
int year = 2024;
int days = Month.FEBRUARY.length(java.time.Year.isLeap(year)); // 29.
Month firstInQuarter = Month.AUGUST.firstMonthOfQuarter();   // JULY.
```

## 6. Adjusting a date is different from finding the next occurrence

Both enums implement `TemporalAdjuster`, so they can be passed to `LocalDate.with(...)`. The original date object is not modified.

- `date.with(Month.FEBRUARY)` sets the month to February, keeping the year and clamping the end-of-month day when needed.
- `date.with(DayOfWeek.MONDAY)` sets Monday within the same ISO week of that date; the result may move backward into the past.
- `date.with(TemporalAdjusters.next(MONDAY))` finds the next Monday, always after the current date.
- `date.with(TemporalAdjusters.nextOrSame(MONDAY))` keeps the current date if it is already Monday; otherwise it finds the next occurrence.

Do not substitute `with(dayOfWeek)` for `next` when writing a reminder schedule. To get the first or last Friday of a month, use adjusters such as `firstInMonth(FRIDAY)` or `lastInMonth(FRIDAY)`. [TemporalAdjusters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html)

## 7. Runnable program

Save as `CalendarEnumsDemo.java`. The `isClosed` method below illustrates a Saturday/Sunday closing schedule chosen specifically for this example.

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.Month;
import java.time.temporal.TemporalAdjusters;
import java.util.EnumSet;
import java.util.Set;

public class CalendarEnumsDemo {
    private static final Set<DayOfWeek> CLOSED_DAYS =
            EnumSet.of(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY);

    static boolean isClosed(LocalDate date) {
        return CLOSED_DAYS.contains(date.getDayOfWeek());
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, Month.JUNE, 19);
        LocalDate endOfJanuary = LocalDate.of(2024, Month.JANUARY, 31);

        System.out.println("month=" + date.getMonth());
        System.out.println("dayOfWeek=" + date.getDayOfWeek());
        System.out.println("marchValue=" + Month.MARCH.getValue());
        System.out.println("sundayValue=" + DayOfWeek.SUNDAY.getValue());
        System.out.println("monthWrap=" + Month.DECEMBER.plus(2));
        System.out.println("dayWrap=" + DayOfWeek.SUNDAY.plus(1));
        System.out.println("februaryCommon=" + Month.FEBRUARY.length(false));
        System.out.println("februaryLeap=" + Month.FEBRUARY.length(true));
        System.out.println("quarterStart=" + Month.AUGUST.firstMonthOfQuarter());

        System.out.println("setFebruary=" + endOfJanuary.with(Month.FEBRUARY));
        System.out.println("sameWeekMonday=" + date.with(DayOfWeek.MONDAY));
        System.out.println("nextMonday="
                + date.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("nextWednesday="
                + date.with(TemporalAdjusters.next(DayOfWeek.WEDNESDAY)));
        System.out.println("sameWednesday="
                + date.with(TemporalAdjusters.nextOrSame(DayOfWeek.WEDNESDAY)));
        System.out.println("firstFriday="
                + date.with(TemporalAdjusters.firstInMonth(DayOfWeek.FRIDAY)));
        System.out.println("sundayClosed="
                + isClosed(LocalDate.of(2024, Month.JUNE, 23)));
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 CalendarEnumsDemo.java
java CalendarEnumsDemo
```

Exact stdout:

```text
month=JUNE
dayOfWeek=WEDNESDAY
marchValue=3
sundayValue=7
monthWrap=FEBRUARY
dayWrap=MONDAY
februaryCommon=28
februaryLeap=29
quarterStart=JULY
setFebruary=2024-02-29
sameWeekMonday=2024-06-17
nextMonday=2024-06-24
nextWednesday=2024-06-26
sameWednesday=2024-06-19
firstFriday=2024-06-07
sundayClosed=true
```

`sameWeekMonday` moves backward from Wednesday, June 19 to Monday, June 17; `nextMonday` moves forward to June 24. `firstFriday` is the first Friday **of the current month**, so it can also fall before the original date.

## 8. Display names and locale-specific week rules

To display in Vietnamese, explicitly choose a `Locale` and `TextStyle`:

```java
java.util.Locale vi = java.util.Locale.forLanguageTag("vi-VN");
String monthLabel = Month.MARCH.getDisplayName(
        java.time.format.TextStyle.FULL, vi);
String dayLabel = DayOfWeek.MONDAY.getDisplayName(
        java.time.format.TextStyle.FULL, vi);
```

This is an illustrative snippet; the exact capitalization and abbreviation style may depend on the JDK's locale data. Use labels for display, and keep the contract-based enum or number for processing or data storage. Do not parse UI labels back with `valueOf`.

Changing the `Locale` of a display name does not change `DayOfWeek.SUNDAY.getValue()` to 1. Enum values are always ISO-based. If a UI needs weeks starting on Sunday or week numbering according to local conventions, use the appropriate `WeekFields`. For example, `WeekFields.SUNDAY_START.dayOfWeek()` provides a field that numbers Sunday as 1, without changing the enum definition.

The first day of the week and the minimal number of days in the first week of the year are the two parameters of a week rule. They also do not define business holidays. [WeekFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html)

## 9. Business boundaries to keep clear

`DayOfWeek` does not automatically know public holidays, shift schedules, or country-specific weekends. The `CLOSED_DAYS` set in the example is an illustrative configuration, not a universal rule. A real-world work calendar also requires public holidays and date-specific exceptions.

Both enums implement `TemporalAccessor` to provide their respective fields and `TemporalAdjuster` to adjust other objects; they do not implement `Temporal`. An enum's own `plus`/`minus` methods do not mean it can be used like a full date for every calculation.

Keep three questions separate when choosing an API: "what month/day of week is it?", "what month/day of week do I want to change it to?", and "what next occurrence am I looking for?". Each question leads to a different operation.

## 10. Practice

1. Convert the number 12 to `Month`, then add one month on the enum; compare that with adding one month on `LocalDate.of(2024, 12, 15)`.
2. For a Monday date, compare `next(MONDAY)` and `nextOrSame(MONDAY)`.
3. Create a custom closed-days schedule consisting of Friday and Saturday using `EnumSet`.
4. Explain why `DayOfWeek.SUNDAY.ordinal()` is not the ISO day number for Sunday.

Check your answers: (1) the enum yields `JANUARY` with no year; the full date yields `2025-01-15`; (2) 7 days later and today unchanged, respectively; (3) use the exact two enum constants; (4) `ordinal` is zero-based, whereas the ISO number must be retrieved with `getValue()`.