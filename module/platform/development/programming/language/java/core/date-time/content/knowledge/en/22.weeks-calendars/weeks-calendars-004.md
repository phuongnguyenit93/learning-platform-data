# IsoFields for Quarters and Week-Based Years

## 1. A Date Can Be Located in a Calendar in Multiple Ways

The date 2021-01-01 belongs to quarter 1 of calendar year 2021, but under ISO week numbering, it falls in week 53 of **week-based year 2020**. Both results are correct because they use two different calendar divisions.

`java.time.temporal.IsoFields` provides fields and units for the ISO calendar, complementing the common fields in `ChronoField`. Two prominent groups are:

- Quarter of year and day of quarter.
- Week-based year and week of week-based year.

They are useful when creating report aggregation keys, describing a date by its quarter/day-of-quarter, or exchanging ISO week codes. What matters is using the right **pair of fields that belong together**, avoiding mixing a calendar year with a week number belonging to a different week-based year.

## 2. Identifying the Fields and Units

| Member | Kind | Meaning |
|---|---|---|
| `QUARTER_OF_YEAR` | `TemporalField` | Quarter 1–4 in the ISO calendar year |
| `DAY_OF_QUARTER` | `TemporalField` | Day number counting from the start of the quarter, starting at 1 |
| `WEEK_BASED_YEAR` | `TemporalField` | ISO week-based year |
| `WEEK_OF_WEEK_BASED_YEAR` | `TemporalField` | Week number 1–52 or 1–53 of the week-based year |
| `QUARTER_YEARS` | `TemporalUnit` | Quarter unit, equal to 3 months in the ISO calendar |
| `WEEK_BASED_YEARS` | `TemporalUnit` | Week-based year unit, distinct from a fixed number of days |

Fields are used to read or adjust a value via `get`, `getLong`, `with`, or a builder. Units are used for addition/subtraction via `plus` or `minus` when the source type supports them.

Do not pass a field where a unit is expected or vice versa. `date.get(IsoFields.QUARTER_OF_YEAR)` reads the quarter; `date.plus(1, IsoFields.QUARTER_YEARS)` adds one quarter.

Not every `java.time` type has enough data for every ISO field. `LocalDate` has complete date information to compute the week number and day of quarter. A time-only value does not have enough information, while non-ISO calendar systems require checking support rather than applying them mechanically.

## 3. ISO Quarters Are Tied to the Calendar Year

Quarters are divided strictly by month:

| Quarter | Months | Number of Days |
|---|---|---|
| Q1 | Months 1–3 | 90 days in a common year, 91 days in a leap year |
| Q2 | Months 4–6 | 91 days |
| Q3 | Months 7–9 | 92 days |
| Q4 | Months 10–12 | 92 days |

Example:

```java
LocalDate date = LocalDate.of(2024, 3, 31);
int quarter = date.get(IsoFields.QUARTER_OF_YEAR); // 1
int dayInQuarter = date.get(IsoFields.DAY_OF_QUARTER); // 91
```

The snippet above illustrates code inside a Java method, requiring the corresponding imports. 2024 is a leap year, so the last day of March is day 91 of quarter 1.

A standalone quarter does not identify a unique reporting period: Q1 2024 differs from Q1 2025. The grouping key needs **calendar year + quarter number**, such as `(2024, 1)`. Do not use only the number `1`, and do not replace the calendar year with `WEEK_BASED_YEAR` in a quarter key.

ISO quarters also do not automatically represent every organization's fiscal quarters. If a fiscal year starts in April or has its own week structure, model the corresponding rules instead of relabeling the result of `QUARTER_OF_YEAR` and assuming it is calculated correctly.

### Reading the Value Range on a Specific Date

`date.range(IsoFields.DAY_OF_QUARTER)` reflects the actual number of days in that date's quarter. For Q1 2024 it is `1 - 91`; Q1 2023 only has 90 days.

The general range of a field can span multiple quarters of different lengths. To validate a value for a specific quarter, you must use that year and quarter, not merely observe that the field can sometimes take the value 92.

## 4. ISO Week-Based Year Can Differ from Calendar Year

ISO weeks follow these rules:

- A week starts on Monday.
- Days of the week are numbered 1–7, from Monday to Sunday.
- Week 1 is the week containing at least 4 days of the new year; equivalently, the week containing January 4 or the first Thursday of the year.
- A week-based year has 52 or 53 weeks.

Because a week is kept intact across the calendar year boundary, late December days can belong to week 1 of the following week-based year. Early January days can belong to the last week of the previous week-based year.

| Calendar Date | Calendar Year | ISO Week-Based Year | ISO Week | ISO Day of Week |
|---|---|---|---|---|
| `2019-12-30` | 2019 | 2020 | 1 | 1, Monday |
| `2021-01-01` | 2021 | 2020 | 53 | 5, Friday |
| `2024-03-31` | 2024 | 2024 | 13 | 7, Sunday |

Therefore, the grouping key for weekly reporting is **`WEEK_BASED_YEAR` + `WEEK_OF_WEEK_BASED_YEAR`**, not `getYear()` + ISO week number. To identify a specific date from the week system, `DAY_OF_WEEK` is also needed.

For example, 2021-01-01 is written `2020-W53-5`. Writing `2021-W53-5` does not simply change the year label: it requests a different week, and week-based year 2021 does not even have a week 53.

## 5. ISO Weeks, Locale Weeks, and Year Patterns Are Different Concepts

`IsoFields` uses fixed ISO rules; it does not change the first day of the week based on `Locale`. If you need locale-based week conventions, `WeekFields` lets you choose the first day of the week and the minimum number of days in the first week.

Do not use the pattern `YYYY` as an uppercase substitute for `yyyy` or `uuuu`. `Y` represents the week-based year, and week fields in patterns may follow locale-specific `WeekFields` rules. Thus, a pattern that looks like a week code does not automatically guarantee ISO week semantics across all machines.

When a contract requires an ISO week code, `DateTimeFormatter.ISO_WEEK_DATE` is the clear choice for formatting/parsing values like `2020-W53-5`. There is no need to manually prepend `getYear()` to the week number.

This is why a buggy reporting key may only surface for a few days around New Year's while all other days look reasonable. Testing mid-year dates is not enough to catch mixing calendar years with week-based years.

## 6. Adjusting a Field Does Not Mean Strict Input Validation

`with(IsoFields.QUARTER_OF_YEAR, 2)` shifts the month by the appropriate number of quarters and preserves what can be preserved; if the day of month no longer exists, it may be adjusted to the last day of the month according to the type's month arithmetic.

For example, changing 2026-01-31 to quarter 2 yields 2026-04-30. Adding one `QUARTER_YEARS` from that date also adds 3 months, yielding 2026-04-30. Although the results match in this example, one call sets the quarter number while the other adds an amount; they must not be treated as always equivalent for all inputs and values.

An important detail: setting `DAY_OF_QUARTER` allows values within the 1–92 range that exceed the actual length of the quarter, rolling over into the next quarter. For example:

```java
LocalDate adjusted = LocalDate.of(2023, 1, 1)
        .with(IsoFields.DAY_OF_QUARTER, 91);
// 2023-04-01, because Q1 2023 only has 90 days.
```

If the goal is to **validate that a year-quarter-day input belongs to that exact quarter**, do not use this `with` operation alone as a strict validator. You can parse the three fields with a formatter using `ResolverStyle.STRICT`, or check the actual length of the quarter before constructing the result.

Similarly, week 53 does not exist in every week-based year. When parsing externally supplied week codes, choose an explicit resolver policy and validate against the target year. Week-based year units are also not a fixed number of seconds or days; if you need to handle week-53 boundaries when adding years, check the contract of the specific operation rather than substituting `plusYears` or a constant number of days.

## 7. Complete Runnable Program

Save the following code to `IsoFieldsDemo.java`. The program uses Java 17 or later and requires no external libraries. The quarter formatter in the example restricts the year part to four unsigned digits.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.IsoFields;
import java.util.Locale;

public class IsoFieldsDemo {
    private static final DateTimeFormatter QUARTER_DATE =
            new DateTimeFormatterBuilder()
                    .appendValue(ChronoField.YEAR, 4)
                    .appendLiteral("-Q")
                    .appendValue(IsoFields.QUARTER_OF_YEAR)
                    .appendLiteral('-')
                    .appendValue(IsoFields.DAY_OF_QUARTER)
                    .toFormatter(Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) {
        for (LocalDate date : new LocalDate[]{
                LocalDate.of(2021, 1, 1),
                LocalDate.of(2019, 12, 30),
                LocalDate.of(2024, 3, 31)
        }) {
            System.out.println(date
                    + " quarter=" + date.get(IsoFields.QUARTER_OF_YEAR)
                    + " dayOfQuarter=" + date.get(IsoFields.DAY_OF_QUARTER)
                    + " weekYear=" + date.get(IsoFields.WEEK_BASED_YEAR)
                    + " week=" + date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR)
                    + " weekday=" + date.getDayOfWeek().getValue());
        }

        LocalDate leap = LocalDate.of(2024, 3, 31);
        System.out.println("quarterKey=" + leap.getYear() + "-Q"
                + leap.get(IsoFields.QUARTER_OF_YEAR));
        System.out.println("quarterDayRange="
                + leap.range(IsoFields.DAY_OF_QUARTER));
        System.out.println("quarterParsed="
                + LocalDate.parse("2024-Q1-91", QUARTER_DATE));
        try {
            LocalDate.parse("2023-Q1-91", QUARTER_DATE);
        } catch (DateTimeParseException e) {
            System.out.println("invalidQuarterDay=ERROR");
        }

        LocalDate jan31 = LocalDate.of(2026, 1, 31);
        System.out.println("setQuarter="
                + jan31.with(IsoFields.QUARTER_OF_YEAR, 2));
        System.out.println("plusQuarter="
                + jan31.plus(1, IsoFields.QUARTER_YEARS));
        System.out.println("setDay91="
                + LocalDate.of(2023, 1, 1)
                           .with(IsoFields.DAY_OF_QUARTER, 91));

        LocalDate boundary = LocalDate.of(2021, 1, 1);
        String weekText = DateTimeFormatter.ISO_WEEK_DATE.format(boundary);
        System.out.println("weekText=" + weekText);
        System.out.println("weekParsed="
                + LocalDate.parse(weekText, DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("actualWeekRange="
                + boundary.range(IsoFields.WEEK_OF_WEEK_BASED_YEAR));
        try {
            LocalDate.parse("2021-W53-1", DateTimeFormatter.ISO_WEEK_DATE);
        } catch (DateTimeParseException e) {
            System.out.println("invalidWeek53=ERROR");
        }
    }
}
```

Compile and run:

```shell
javac IsoFieldsDemo.java
java IsoFieldsDemo
```

Expected output:

```text
2021-01-01 quarter=1 dayOfQuarter=1 weekYear=2020 week=53 weekday=5
2019-12-30 quarter=4 dayOfQuarter=91 weekYear=2020 week=1 weekday=1
2024-03-31 quarter=1 dayOfQuarter=91 weekYear=2024 week=13 weekday=7
quarterKey=2024-Q1
quarterDayRange=1 - 91
quarterParsed=2024-03-31
invalidQuarterDay=ERROR
setQuarter=2026-04-30
plusQuarter=2026-04-30
setDay91=2023-04-01
weekText=2020-W53-5
weekParsed=2021-01-01
actualWeekRange=1 - 53
invalidWeek53=ERROR
```

`ERROR` is a label printed by the program when catching `DateTimeParseException`, not Java's default message.

The `QUARTER_DATE` formatter uses three fields—**calendar year, quarter, day of quarter**—to construct a date. `2024-Q1-91` is valid, whereas `2023-Q1-91` is rejected in strict mode. Compare this with the `setDay91` line to see clearly that field adjustment and input validation have different contracts.

`actualWeekRange` is queried on 2021-01-01 but returns a range up to 53 because that date belongs to week-based year 2020. To know the week count of a particular week-based year, you must choose the right context, not just look at the calendar year of the date at hand.

## 8. Use in Aggregation and Data Exchange

When grouping data, keep the components as a structured key—for example, a clearly named year-week or year-quarter record. Strings like `2024-Q1` or `2020-W53` can serve as interchange representations, but they should not obscure the meaning of the year type in processing code.

Before extracting `IsoFields` from an instant such as `Instant`, determine the local date in the report's time zone. The same instant can fall on two different dates across time zones, resulting in different quarters or week-based years. `Instant` does not have a single universal "business week."

If the data is already a `LocalDate`, it carries no time zone, and reading fields depends solely on that date. Do not attach the server's time zone to reinterpret a date that is already properly determined in the business domain.

## 9. Hands-On Practice

1. Read the week fields of `2021-01-04`. The result is week-based year 2021, week 1, Monday; compare it with `2021-01-01` to see the boundary.
2. Read the day of quarter of `2023-03-31` and `2024-03-31`. The two results are 90 and 91 because a leap year adds one day to Q1.
3. Group the three dates `2020-12-31`, `2021-01-01`, and `2021-01-03` using the ISO week field pair. All three belong to the same week 53 of week-based year 2020; using the calendar year would split them into the wrong groups.
4. Change `ResolverStyle.STRICT` on the quarter formatter to `SMART`, then observe `2023-Q1-91`. Check against your policy whether crossing outside the input quarter is allowed or must raise an error.

References: [IsoFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/IsoFields.html) and [DateTimeFormatter — ISO_WEEK_DATE](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#ISO_WEEK_DATE) in Java SE 21.
