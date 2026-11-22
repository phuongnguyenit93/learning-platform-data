# New Year's Day and Week-Based-Year Boundaries

## 1. Why does the calendar year change while the week's year has not changed yet?

The date `2021-01-01` has a calendar year of 2021, but it belongs to ISO week `2020-W53`. Conversely, `2018-12-31` is still in calendar year 2018, yet it belongs to ISO week `2019-W01`. No date has been moved: the two descriptions are using two different kinds of years.

To understand the situation of "belonging to a week of the previous or next year" properly, look at the **boundary between two years**: some days in early January may belong to the previous week-based year, and some days in late December may belong to the next week-based year. There is no ISO rule stating that January 1 itself belongs to the week-based year of the year after next.

Distinguish two concepts:

- **Calendar year:** the year containing the date in month/day representation, read via `LocalDate.getYear()`.
- **Week-based year:** the year to which the entire week is assigned, paired with the week number within that year.

If revenue reports are grouped by week, this difference can place data into the wrong bucket in late December or early January, even though mid-year dates look completely normal.

## 2. The ISO rule keeps the entire week intact

According to [Java SE 21 — IsoFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/IsoFields.html), an ISO week starts on Monday; week 1 is the week that has at least four days in the new year. A week-based year usually has 52 weeks and occasionally 53 weeks.

You can identify ISO week 1 as the week containing January 4. Late December days falling in that week also carry the new week-based year. On the other hand, if the week containing January 1 does not have at least four days in the new year, it still belongs to the old week-based year.

For example, calendar year 2021 starts on a Friday:

```text
ISO week 2020-W53
Monday     ...  Thursday    Friday     Saturday   Sunday
2020-12-28 ...  2020-12-31  2021-01-01 2021-01-02 2021-01-03
                            └─── only 3 days in 2021 ──────┘

ISO week 2021-W01 starts on Monday 2021-01-04.
```

Keeping the whole week in 2020 prevents a week from being split into "half old, half new" in the week-based-year model. Even so, every early January date in the diagram still retains its month, day, and calendar year 2021.

The table below describes when ISO week 1 starts depending on the day of the week of January 1:

| January 1 is | Week 1 of the week-based year starts on |
| --- | --- |
| Monday | 1/1 |
| Tuesday | 12/31 of the previous calendar year |
| Wednesday | 12/30 of the previous calendar year |
| Thursday | 12/29 of the previous calendar year |
| Friday | 1/4 |
| Saturday | 1/3 |
| Sunday | 1/2 |

When January 1 is Friday, Saturday, or Sunday, the days before the start date in the right column belong to the previous week-based year. When week 1 starts in December, the corresponding late December days belong to the next week-based year relative to the calendar year in question.

## 3. Getting the right year–week pair in Java

For ISO requirements, read the two fields together:

```java
// Illustrated inside a method.
LocalDate date = LocalDate.of(2021, 1, 1);
int weekYear = date.get(IsoFields.WEEK_BASED_YEAR);       // 2020
int week = date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);  // 53
```

Equivalent approach via the ISO rule:

```java
WeekFields rule = WeekFields.ISO;
int weekYear = date.get(rule.weekBasedYear());
int week = date.get(rule.weekOfWeekBasedYear());
```

Do not build a key by combining `date.getYear()` with `weekOfWeekBasedYear()`: `2021-01-01` would be mislabeled as `2021-W53`. Also do not store only the week number 53, because it does not specify which year or which rule is being used.

The week-based year is a property read from a date, not a request to change the year of the `LocalDate` object. Calling `date.withYear(2020)` just to make the year match the week label will produce a different calendar date and corrupt the data.

## 4. A program to verify year boundaries

Save the code to `WeekYearBoundaryDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.time.temporal.IsoFields;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekYearBoundaryDemo {
    private static void show(LocalDate date) {
        System.out.printf(Locale.ROOT,
                "%s | calendar=%d | ISO=%d-W%02d | weekday=%s%n",
                date, date.getYear(),
                date.get(IsoFields.WEEK_BASED_YEAR),
                date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR),
                date.getDayOfWeek());
    }

    public static void main(String[] args) {
        LocalDate first = LocalDate.of(2020, 12, 28);
        for (int i = 0; i < 8; i++) {
            show(first.plusDays(i));
        }
        show(LocalDate.of(2018, 12, 31));
        show(LocalDate.of(2019, 1, 1));

        LocalDate january = LocalDate.of(2021, 1, 1);
        System.out.println("ISO string = "
                + january.format(DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("parsed back = "
                + LocalDate.parse("2020-W53-5", DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("hybrid pattern = " + january.format(
                DateTimeFormatter.ofPattern("YYYY-MM-dd", Locale.UK)));
        System.out.println("calendar pattern = " + january.format(
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)));

        WeekFields iso = WeekFields.ISO;
        System.out.println("calendar-year week = " + january.get(iso.weekOfYear()));
        System.out.println("week-year week = "
                + january.get(iso.weekOfWeekBasedYear()));
        LocalDate sunday = LocalDate.of(2020, 12, 27);
        System.out.println("same Sunday ISO = "
                + sunday.get(iso.weekBasedYear()) + "-W"
                + sunday.get(iso.weekOfWeekBasedYear()));
        WeekFields sundayRule = WeekFields.of(java.time.DayOfWeek.SUNDAY, 1);
        System.out.println("same Sunday Sunday/1 = "
                + sunday.get(sundayRule.weekBasedYear()) + "-W"
                + sunday.get(sundayRule.weekOfWeekBasedYear()));

        long days = ChronoUnit.DAYS.between(
                LocalDate.of(2020, 12, 31), LocalDate.of(2021, 1, 1));
        System.out.println("actual days = " + days);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 WeekYearBoundaryDemo.java
java WeekYearBoundaryDemo
```

Verified output:

```text
2020-12-28 | calendar=2020 | ISO=2020-W53 | weekday=MONDAY
2020-12-29 | calendar=2020 | ISO=2020-W53 | weekday=TUESDAY
2020-12-30 | calendar=2020 | ISO=2020-W53 | weekday=WEDNESDAY
2020-12-31 | calendar=2020 | ISO=2020-W53 | weekday=THURSDAY
2021-01-01 | calendar=2021 | ISO=2020-W53 | weekday=FRIDAY
2021-01-02 | calendar=2021 | ISO=2020-W53 | weekday=SATURDAY
2021-01-03 | calendar=2021 | ISO=2020-W53 | weekday=SUNDAY
2021-01-04 | calendar=2021 | ISO=2021-W01 | weekday=MONDAY
2018-12-31 | calendar=2018 | ISO=2019-W01 | weekday=MONDAY
2019-01-01 | calendar=2019 | ISO=2019-W01 | weekday=TUESDAY
ISO string = 2020-W53-5
parsed back = 2021-01-01
hybrid pattern = 2020-01-01
calendar pattern = 2021-01-01
calendar-year week = 0
week-year week = 53
same Sunday ISO = 2020-W52
same Sunday Sunday/1 = 2021-W1
actual days = 1
```

All dates are fixed, so the verification does not depend on when it is run. The lines using patterns with a Locale illustrate the runtime's week-rule data; reading `IsoFields` or `WeekFields.ISO` directly states the ISO requirement explicitly.

## 5. Key takeaways from the output

### The week changes its year at the start of the week, not necessarily on January 1

The seven days from `2020-12-28` through `2021-01-03` all belong to `2020-W53`. On Monday `2021-01-04`, the label changes to `2021-W01`. In the opposite example, Monday `2018-12-31` already opened week `2019-W01`, and Tuesday `2019-01-01` continues to belong to that same week.

This is why you should not reset the week number to 1 merely upon encountering January 1 in a data-processing loop. Read the fields of the chosen rule from each date instead.

### The date itself stays the same and intervals remain normal

The line `actual days = 1` measures from `2020-12-31` to `2021-01-01`. Week-based-year labels do not add or subtract elapsed time. Do not treat differences in week labels as day counts without understanding the week rule and year boundaries.

The string `2020-W53-5` parses back to `2021-01-01` with `ISO_WEEK_DATE`. The `5` is Friday in ISO numbering, which identifies a single day within the week. The pair `2020-W53` alone identifies the week rather than a unique day; if you want the first day of the week, you must apply an explicit convention to select Monday.

### Week 0 is not week 53

The date `2021-01-01` gives 0 for `WeekFields.ISO.weekOfYear()`, whereas `weekOfWeekBasedYear()` gives 53. [Java SE 21 — WeekFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html) distinguishes between the week field within a calendar year and the pair of fields for a week-based year.

`weekOfYear()` stays within the current calendar year and can number an incomplete leading part as week 0. The week-based-year pair instead places the entire week in the corresponding year. Do not turn 0 into 53 using a hardcoded formula: the previous year may have only 52 weeks, and any conversion must account for the actual year and rule.

## 6. Avoid mixing week-based year with calendar month/day

In the program, the pattern `YYYY-MM-dd` with the runtime's UK Locale produces the string `2020-01-01` from the source date `2021-01-01`. `Y` retrieves the week-based year, while `MM-dd` still retrieves the calendar month and day. Such a hybrid string can look like a normal date while misrepresenting the source date.

If you need a calendar date, use an appropriate pattern such as `uuuu-MM-dd`. If you need an ISO week date, use `DateTimeFormatter.ISO_WEEK_DATE`. For a custom week format, you must use the week-based year, week number, and day-of-week fields from the same rule.

Do not think of `YYYY` as an uppercase version of `yyyy` or `uuuu`. The difference only shows up easily near year boundaries, so a test suite using only June dates can miss this bug.

## 7. When the week rule is not ISO

The rule `WeekFields.of(DayOfWeek.SUNDAY, 1)` in the program treats Sunday `2020-12-27` as week 1 of week-based year 2021, whereas ISO treats the same date as week 52 of 2020. The two results differ because of the first day of the week and the minimum-days threshold, not because the date itself changed.

If business requirements call for weeks based on the user's region, you can use `WeekFields.of(locale)` and document that Locale. If the requirements specify ISO, use ISO explicitly rather than letting the default Locale decide. Do not use one rule when computing keys and another when displaying or parsing strings.

Reporting from an `Instant` also requires choosing a reporting time zone to convert the instant into a date before computing the week. Week-based-year boundaries are evaluated on the chosen local date and do not by themselves resolve which calendar date an instant falls on in different zones.

## 8. Self-check before using as a report key

A week-grouping key needs the week-based year and week number from the right rule. If chronological sorting is needed, you can keep the two numbers or keep the week's start date computed under the rule; avoid relying on arbitrary unpadded strings, because `W10` and `W2` do not sort numerically under standard character comparison.

Cases worth verifying include: December 31 belonging to the next week-based year, January 1 belonging to the previous week-based year, the first day of week 1, and a year with week 53. Also confirm that changing the label does not alter the source date.

Exercise: `2022-01-01` is a Saturday. Under ISO, it belongs to `2021-W52`; Monday `2022-01-03` starts `2022-W01`. Compare this with the 2021 example to see that early January belonging to the previous year does not always mean week 53. The final week number of the previous week-based year must be computed by the library from the right rule.
