# ISO Weeks, First Day of Week, and Week-Based Year

## Why can a late-December date belong to week 1 of the next year?

A weekly report has the date `2019-12-30`. If we only call `date.getYear()`, we get the year 2019. However, according to ISO week numbering, this date is **Monday of week 1, week-based year 2020**.

Conversely, `2021-01-01` falls in calendar year 2021, but belongs to **week 53 of week-based year 2020**.

There is no contradiction: we are using two different ways of grouping dates. One groups by the month and day of the calendar year; the other groups by complete weeks. Understanding this boundary helps prevent reports from splitting weeks in half, keying data under the wrong year, and formatting bugs that only surface around New Year's Day.

This lesson uses `LocalDate` in the ISO calendar. First, you need to understand the week rules, and only then choose the fields or patterns for reading, writing, and grouping data.

## 1. Two parameters that define week numbering

A week is seven days long, but numbering weeks within a year requires two additional choices:

1. Which day is the first day of the week?
2. What is the minimum number of days the first week must have in the new year?

The ISO rules are:

- The week starts on **Monday**.
- Week 1 must have **at least four days** in the new year.

In Java, `WeekFields.ISO` expresses these exact two choices. A rule that only says "weeks start on Monday" is still not enough to derive ISO week numbering; you also need to know the minimum number of days in the first week. [`WeekFields` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html)

An easy-to-remember consequence: ISO week 1 is the week that contains **January 4**, which is also the week that contains the **first Thursday** of the year.

Week 1 does not necessarily start on January 1. Depending on the day of the week of January 1, the Monday that opens week 1 may be in late December of the previous year or in the first few days of January.

## 2. Calendar year and week-based year

The **calendar year** of a `LocalDate` is the year that the date belongs to when written as year–month–day. Read it with `getYear()`.

The **week-based year** is the year to which the entire week is assigned according to the week-numbering rules. In the ISO system, a week is not split across two week-based years just because it crosses December 31.

Each date can be represented by the ISO triplet:

```text
week-based year + week number in week-based year + ISO day of week
```

For example:

```text
2019-12-30 as a calendar date
2020-W01-1 as an ISO week date
     │   │
     │   └── Monday = 1
     └────── week 1 of week-based year 2020
```

`IsoFields.WEEK_BASED_YEAR` and `IsoFields.WEEK_OF_WEEK_BASED_YEAR` provide these year and week fields. The ISO day of week comes from `DayOfWeek`, where Monday is 1 and Sunday is 7. [`IsoFields` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/IsoFields.html)

The triplet must use the same rule set. Combining calendar year 2019 with ISO week 1 for `2019-12-30` produces a label that no longer points to the right week for that date.

## 3. Observing two year boundaries

### The 2019 to 2020 boundary

```text
Mon      Tue      Wed      Thu      Fri      Sat      Sun
30/12    31/12    01/01    02/01    03/01    04/01    05/01
└──────────────────── 2020-W01 ───────────────────────────┘
```

This week has five days in 2020, so it qualifies as week 1 of week-based year 2020. Both December 30 and December 31, 2019 belong to that same week.

### The 2020 to 2021 boundary

```text
Mon      Tue      Wed      Thu      Fri      Sat      Sun
28/12    29/12    30/12    31/12    01/01    02/01    03/01
└──────────────────── 2020-W53 ───────────────────────────┘

2021-01-04 is the Monday that starts 2021-W01
```

The week containing `2021-01-01` has only three days in calendar year 2021, so it does not qualify as week 1 of week-based year 2021. It is the final week of week-based year 2020.

These two examples show why testing only mid-year dates often misses week/year bugs.

## 4. Complete program

Save as `IsoWeekDemo.java`. The program uses Java 17 or later and the standard library:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.temporal.IsoFields;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.WeekFields;

public class IsoWeekDemo {
    private static void show(String text) {
        LocalDate date = LocalDate.parse(text);
        int weekYear = date.get(IsoFields.WEEK_BASED_YEAR);
        int week = date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);

        System.out.println(date
                + " calendarYear=" + date.getYear()
                + " weekYear=" + weekYear
                + " week=" + week
                + " weekday=" + date.getDayOfWeek().getValue());
    }

    private static int isoWeeksInYear(int weekYear) {
        return LocalDate.of(weekYear, 12, 28)
                .get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);
    }

    public static void main(String[] args) {
        show("2019-12-29");
        show("2019-12-30");
        show("2020-12-31");
        show("2021-01-01");
        show("2021-01-03");
        show("2021-01-04");

        System.out.println("isoFirstDay="
                + WeekFields.ISO.getFirstDayOfWeek());
        System.out.println("isoMinimalDays="
                + WeekFields.ISO.getMinimalDaysInFirstWeek());

        LocalDate date = LocalDate.of(2021, 1, 1);
        LocalDate weekStart = date.with(
                TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        LocalDate weekEndExclusive = weekStart.plusWeeks(1);

        System.out.println("weekStart=" + weekStart);
        System.out.println("weekEndExclusive=" + weekEndExclusive);

        LocalDate firstWeekStart = LocalDate.of(2021, 1, 4).with(
                TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        System.out.println("firstWeekStart2021=" + firstWeekStart);

        System.out.println("isoWeekDate="
                + LocalDate.of(2019, 12, 30)
                        .format(DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("parsedWeekDate="
                + LocalDate.parse("2020-W01-1", DateTimeFormatter.ISO_WEEK_DATE));

        try {
            LocalDate.parse("2021-W53-1", DateTimeFormatter.ISO_WEEK_DATE);
            System.out.println("invalidWeekAccepted");
        } catch (DateTimeParseException ex) {
            System.out.println("invalidWeekRejected");
        }

        System.out.println("weeks2020=" + isoWeeksInYear(2020));
        System.out.println("weeks2021=" + isoWeeksInYear(2021));

        LocalDate comparison = LocalDate.of(2020, 12, 27);
        WeekFields sundayStart = WeekFields.SUNDAY_START;
        System.out.println("isoComparison="
                + comparison.get(WeekFields.ISO.weekBasedYear())
                + "/" + comparison.get(WeekFields.ISO.weekOfWeekBasedYear()));
        System.out.println("sundayComparison="
                + comparison.get(sundayStart.weekBasedYear())
                + "/" + comparison.get(sundayStart.weekOfWeekBasedYear()));

        System.out.println("isoWeekOfCalendarYearJan1="
                + date.get(WeekFields.ISO.weekOfYear()));
        System.out.println("isoWeekOfWeekYearJan1="
                + date.get(WeekFields.ISO.weekOfWeekBasedYear()));
    }
}
```

Compile and run:

```shell
javac --release 17 IsoWeekDemo.java
java IsoWeekDemo
```

Stdout:

```text
2019-12-29 calendarYear=2019 weekYear=2019 week=52 weekday=7
2019-12-30 calendarYear=2019 weekYear=2020 week=1 weekday=1
2020-12-31 calendarYear=2020 weekYear=2020 week=53 weekday=4
2021-01-01 calendarYear=2021 weekYear=2020 week=53 weekday=5
2021-01-03 calendarYear=2021 weekYear=2020 week=53 weekday=7
2021-01-04 calendarYear=2021 weekYear=2021 week=1 weekday=1
isoFirstDay=MONDAY
isoMinimalDays=4
weekStart=2020-12-28
weekEndExclusive=2021-01-04
firstWeekStart2021=2021-01-04
isoWeekDate=2020-W01-1
parsedWeekDate=2019-12-30
invalidWeekRejected
weeks2020=53
weeks2021=52
isoComparison=2020/52
sundayComparison=2021/1
isoWeekOfCalendarYearJan1=0
isoWeekOfWeekYearJan1=53
```

## 5. Getting the start of a week vs. finding week 1 of a year

Starting from `2021-01-01`, find the nearest Monday on or before the source date:

```java
LocalDate start = date.with(
        TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
```

This snippet illustrates the operation using the existing `date` variable. The result in the program is `2020-12-28`. It is the start of the week containing the source date, but that week belongs to week-based year 2020.

To find the start date of **ISO week 1 of a week-based year**, use January 4 of that year as the anchor and step back to the nearest Monday:

```java
LocalDate weekOneStart = LocalDate.of(weekYear, 1, 4).with(
        TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
```

This snippet illustrates the operation where `weekYear` is the target week-based year.

These two operations answer different questions. Do not take the Monday before January 1 and assume it is always the start of week 1 of the new year.

When representing a week to filter dates, you can use the half-open interval:

```text
[startOfWeek, startOfWeek + 1 week)
```

In the example, the interval is `[2020-12-28, 2021-01-04)`. It spans a full week across the calendar year boundary. If your data consists of instants rather than dates, you also need to specify the time zone used to convert the date boundaries into instants.

## 6. A week-based year has 52 or 53 weeks

Do not assume every year has 52 weeks, or use "a leap year has 53 weeks." Those two properties are not equivalent.

In ISO weeks, a year has 53 weeks when January 1 is a Thursday, or when it is a Wednesday in a leap year. The program shows that week-based year 2020 has 53 weeks, while 2021 has 52 weeks.

The calculation in `isoWeeksInYear` relies on December 28: this date always lies in the last ISO week of the week-based year with the same number. The week number read from it is therefore the total number of weeks in that week-based year.

When receiving input such as `2021-W53-1`, you must validate that week 53 exists in that year. `ISO_WEEK_DATE` used in the program rejects invalid combinations; do not construct dates by adding weeks from an anchor and ignoring that the result spilled into the next week-based year.

If you build a helper from a year–week–weekday triplet yourself, verify the weekday range, the week number, and the round-tripped triplet after conversion. Do not only check `week <= 53`.

## 7. `weekOfYear()` vs. `weekOfWeekBasedYear()`

The API names look similar, but their models differ:

| Field | How it organizes weeks |
| --- | --- |
| `weekOfYear()` | Splits weeks within the calendar year; an initial partial week that does not qualify can be week 0 |
| `weekOfWeekBasedYear()` | Each week belongs entirely to a single week-based year |
| `weekBasedYear()` | The year paired with the week number in the week-based year model |

For `2021-01-01`, the program outputs:

```text
WeekFields.ISO.weekOfYear()          = 0
WeekFields.ISO.weekOfWeekBasedYear() = 53
WeekFields.ISO.weekBasedYear()       = 2020
```

Week 0 does not mean the date belongs to no week at all. It is the result of the first field splitting within the calendar year boundaries. In the week-based year model, this date belongs to week 53 of 2020. [Distinguishing week fields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html)

For continuous ISO weekly reporting, you typically need the pair `weekBasedYear` and `weekOfWeekBasedYear`. Never pair a week field from one model with the year from the other.

## 8. The first day of the week can vary by regional convention

`WeekFields.SUNDAY_START` uses Sunday as the first day of the week and requires only one day for the first week. The program applied both conventions to the same date, `2020-12-27`:

```text
ISO:             week-based year 2020, week 52
Sunday-start/1:  week-based year 2021, week 1
```

These are two different rule sets, not a case of one side miscomputing the date.

`WeekFields.of(locale)` selects rules based on the language/region of the `Locale`. This is useful for localized UIs, but when an integration or analytics contract commits to ISO, choose `WeekFields.ISO` or `IsoFields` explicitly. Never let the host machine's default locale silently determine the week code used as a data key.

Display day names and day numbering should also be kept distinct. `DayOfWeek.getValue()` always uses the ISO 1..7 numbering; it does not change Sunday to 1 just because a UI renders a Sunday-start calendar. If you need the day-of-week field according to a specific `WeekFields`, use that rule's `dayOfWeek()` field. [`DayOfWeek` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html)

## 9. Be careful with `YYYY` when formatting dates

In a `DateTimeFormatter` pattern:

| Symbol | Meaning |
| --- | --- |
| `u` | Year on the proleptic year axis |
| `y` | Year-of-era |
| `Y` | Week-based-year |
| `w` | Week of week-based-year |
| `e` | Localized day-of-week |

Therefore, `YYYY-MM-dd` mixes the week-based year with the month and day of the calendar date. Around year boundaries, it can print a string that no longer represents the intended date.

If you want a standard calendar date, use an appropriate pattern such as `uuuu-MM-dd` or `ISO_LOCAL_DATE`. If you want an ISO week date, prefer `DateTimeFormatter.ISO_WEEK_DATE`.

Also do not assume a custom pattern like `YYYY-'W'ww-e` always uses ISO weeks: localized week fields depend on the `Locale`. To configure exact ISO behavior in a custom format, you can build it from `IsoFields` and the specific ISO day-of-week; first, define the output contract. [Pattern table and `ISO_WEEK_DATE`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

In code that groups data, keeping year and week as explicit fields is usually easier to verify than formatting a string and parsing it back.

## 10. Designing report keys and test cases

An ISO weekly report key should contain at minimum:

```text
(isoWeekBasedYear, isoWeekNumber)
```

For example, `2019-12-30` and `2020-01-01` are both grouped under `(2020, 1)`. If you need a key down to the day within the week, add the ISO day of week.

Do not use only the week number: week 1 occurs in multiple years. Do not use the calendar year together with the ISO week number, because that splits a single week at the year boundary.

Useful test cases:

- December 29, 30, 31 and January 1 through 4.
- A 52-week year and a 53-week year.
- Adjacent Sunday and Monday across a week-based year boundary.
- Parsing and re-formatting a valid ISO week date.
- Week 53 in a year that only has 52 weeks.
- The same date under two different week conventions if the product supports both.

These checks target model boundaries, not just well-formed date string syntax.

## 11. Practice questions

1. Which day does an ISO week start on, and what is the minimum number of days required in week 1?
2. What are the calendar year and ISO week-based year of `2021-01-01`?
3. Is taking `date.getYear()` and pairing it with the ISO week number always right?
4. Why is knowing that a week starts on Monday not enough to determine week numbering?
5. Which formatter should you try for exchanging strings like `2020-W01-1`?

Suggested answers:

1. Monday and four days.
2. Calendar year 2021; week-based year 2020, week 53.
3. No; the two years can differ at the beginning and end of a calendar year.
4. You also need the minimum number of days required in the first week.
5. `DateTimeFormatter.ISO_WEEK_DATE`.

Choose your week rules explicitly, keep the week-based year paired with the week number, and verify dates around year boundaries.
