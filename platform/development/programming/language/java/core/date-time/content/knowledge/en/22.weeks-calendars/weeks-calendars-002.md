# `WeekFields` and `Locale`-Dependent Week Rules

## 1. The Same Date Can Have Different Week Numbers

A report stating "week 1 of 2021" does not fully describe the week-splitting rule. Does the week start on Monday or Sunday? Does a week with only a few days in the new year count as the first week yet? Two systems that answer differently can assign different week numbers to the same date while both still compute correctly according to their own contracts.

`WeekFields` describes a week rule and provides `TemporalField`s to read the day-of-week number, week of month, week of year, or week-based year. According to [Java SE 21 — WeekFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html), the rule is determined by two values: the first day of the week and the minimal number of days in the first week.

A distinction must be made between week rules and the display names of days of the week. Changing the language from "Monday" to "thứ Hai" only changes the spelling; changing the first day of the week or the minimal number of days changes how weeks are numbered.

## 2. The Two Components of the Rule

### First Day of the Week

`getFirstDayOfWeek()` indicates the starting point of the cycle. With a Monday-start rule, Monday has the localized number 1; with a Sunday-start rule, Sunday has the localized number 1. This is the numbering used by the `weekFields.dayOfWeek()` field.

### Minimal Days in the First Week

`getMinimalDaysInFirstWeek()` is in the range 1–7. It determines whether the partial week at the start of a year or month qualifies to receive number 1. If it does not qualify, the week-of-year or week-of-month field may return 0; in the week-based-year model, those days are assigned to the previous week-based year.

For example, ISO uses Monday and at least 4 days. The week containing `2021-01-01` starts on Monday `2020-12-28`; only three days of that week fall in 2021, so that week is not yet week 1 of 2021 under ISO. New Year's Day still belongs to week 53 of week-based year 2020.

If the rule starts on Sunday and requires only 1 day in the new year, the week starting `2020-12-27` already qualifies to become week 1 of week-based year 2021. A small decision about the minimal-days threshold changes the entire year associated with the week.

## 3. Creating Rules from a Contract or from a `Locale`

An illustrative example inside a method:

```java
WeekFields iso = WeekFields.ISO;
WeekFields sunday = WeekFields.of(DayOfWeek.SUNDAY, 1);
WeekFields userRule = WeekFields.of(userLocale); // userLocale has already been determined.
```

`WeekFields.ISO` fixes the Monday/4-day pair. `WeekFields.SUNDAY_START` is the Sunday/1-day rule. `WeekFields.of(firstDay, minimalDays)` is appropriate when a report has a contract explicitly specifying both parameters. `WeekFields.of(locale)` is appropriate when you want to apply the week conventions of the selected region, such as a calendar UI for a user.

Do not assume that all English-language Locales share the same week rule; the region information matters as well. Nor should you change the JVM-wide default Locale to compute a single user's report: passing the appropriate Locale or `WeekFields` into the computation makes the dependency explicit.

Rules obtained from a Locale rely on the runtime's localization data. For a fixed data-exchange contract, prefer an explicit rule such as ISO or an agreed-upon pair of parameters. When diagnosing results that differ across environments, print the two actual parameters rather than looking only at the language tag.

## 4. Choosing the Right Field, Especially at Year Boundaries

| Field | Intended Meaning to Use |
| --- | --- |
| `dayOfWeek()` | Day-of-week number 1–7 according to this rule's first day of week |
| `weekOfMonth()` | Week within the current calendar month; may have week 0 |
| `weekOfYear()` | Week within the current calendar year; may have week 0 |
| `weekOfWeekBasedYear()` | Week number belonging to a week-based year |
| `weekBasedYear()` | The week-based year paired with the week number on the row above |

### Calendar Year vs. Week-Based Year

The calendar year of `2021-01-01` is 2021. However, under ISO, the year–week pair is `2020-W53`. To construct a complete week identifier label, you must take `weekBasedYear()` together with `weekOfWeekBasedYear()` from the **same** `WeekFields`.

Do not combine `date.getYear()` with `weekOfWeekBasedYear()` and call that an ISO week. Doing so would mistakenly write `2021-W53` for New Year's Day in the example. Likewise, do not combine a week number from a Sunday-start rule with the week-based year from the ISO rule.

### Why Is There a Week 0?

`weekOfYear()` partitions within the calendar year, so days at the start of the year that do not yet meet the criteria for week 1 can fall into week 0. It does not automatically change the calendar year to place those days into week 53 of the previous year.

`weekOfWeekBasedYear()` and `weekBasedYear()` do something different: each week belongs to a week-based year, which can cross calendar-year boundaries. Therefore, `2021-01-01` simultaneously has `weekOfYear() == 0` and the ISO week-based year pair `2020-W53`. The two values do not contradict each other; they answer two different questions.

`weekOfMonth()` works similarly for the start of a month. For example, Saturday `2021-05-01` only accounts for two days at the start of the month in the week that began on the previous Monday; with the ISO 4-day threshold, the week-of-month field returns 0. Do not assume week numbers always start at 1 when using these fields.

## 5. Complete Verification Program

Save the code to `LocaleWeeksDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class LocaleWeeksDemo {
    private static void printRule(String name, WeekFields rule) {
        System.out.println(name + " = " + rule.getFirstDayOfWeek()
                + ", minimalDays=" + rule.getMinimalDaysInFirstWeek());
    }

    private static void printDate(LocalDate date, WeekFields rule, String name) {
        System.out.printf(Locale.ROOT,
                "%s %s -> day=%d, weekOfYear=%d, weekBased=%d-W%02d%n",
                date, name, date.get(rule.dayOfWeek()),
                date.get(rule.weekOfYear()),
                date.get(rule.weekBasedYear()),
                date.get(rule.weekOfWeekBasedYear()));
    }

    public static void main(String[] args) {
        WeekFields iso = WeekFields.ISO;
        WeekFields sunday = WeekFields.of(DayOfWeek.SUNDAY, 1);
        printRule("explicit ISO", iso);
        printRule("explicit Sunday", sunday);
        printRule("Locale.US", WeekFields.of(Locale.US));
        printRule("Locale.FRANCE", WeekFields.of(Locale.FRANCE));

        LocalDate[] dates = {
            LocalDate.of(2020, 12, 27),
            LocalDate.of(2021, 1, 1),
            LocalDate.of(2021, 1, 4)
        };
        for (LocalDate date : dates) {
            printDate(date, iso, "ISO");
            printDate(date, sunday, "Sunday");
        }

        LocalDate sundayDate = LocalDate.of(2021, 1, 3);
        System.out.println("ISO enum Sunday = "
                + sundayDate.getDayOfWeek().getValue());
        System.out.println("localized Sunday = "
                + sundayDate.get(sunday.dayOfWeek()));
        System.out.println("ISO weekOfMonth on 2021-05-01 = "
                + LocalDate.of(2021, 5, 1).get(iso.weekOfMonth()));

        LocalDate boundary = LocalDate.of(2021, 1, 1);
        String pattern = "YYYY-'W'ww-e";
        System.out.println("pattern US = "
                + boundary.format(DateTimeFormatter.ofPattern(pattern, Locale.US)));
        System.out.println("pattern France = "
                + boundary.format(DateTimeFormatter.ofPattern(pattern, Locale.FRANCE)));
        System.out.println("calendar year = " + boundary.getYear());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LocaleWeeksDemo.java
java LocaleWeeksDemo
```

Verified output on the runtime used in this article:

```text
explicit ISO = MONDAY, minimalDays=4
explicit Sunday = SUNDAY, minimalDays=1
Locale.US = SUNDAY, minimalDays=1
Locale.FRANCE = MONDAY, minimalDays=4
2020-12-27 ISO -> day=7, weekOfYear=52, weekBased=2020-W52
2020-12-27 Sunday -> day=1, weekOfYear=53, weekBased=2021-W01
2021-01-01 ISO -> day=5, weekOfYear=0, weekBased=2020-W53
2021-01-01 Sunday -> day=6, weekOfYear=1, weekBased=2021-W01
2021-01-04 ISO -> day=1, weekOfYear=1, weekBased=2021-W01
2021-01-04 Sunday -> day=2, weekOfYear=2, weekBased=2021-W02
ISO enum Sunday = 7
localized Sunday = 1
ISO weekOfMonth on 2021-05-01 = 0
pattern US = 2021-W01-6
pattern France = 2020-W53-5
calendar year = 2021
```

The explicit rules fix Monday/4 and Sunday/1. The lines obtained from `Locale.US`/`Locale.FRANCE` also print their configuration to inspect the actual Locale data. No current date or implicit machine zone participates in the program's `LocalDate` calculations.

`printf(Locale.ROOT, ...)` only stabilizes number formatting in the experiment's output lines; it does not alter the `WeekFields` passed into the method. This makes it clear to the reader that the Locale used for formatting strings and the rule used for computing weeks are two choices that can be specified independently.

## 6. ISO Day-of-Week and Localized Day-of-Week Are Not the Same Number

With `DayOfWeek`, `MONDAY.getValue()` is always 1 and `SUNDAY.getValue()` is 7. Configuring `WeekFields` does not modify these enum constants.

By contrast, `sundayRule.dayOfWeek()` takes Sunday as 1, Monday as 2, and so on. That is why the program produces two different numbers for the same Sunday `2021-01-03`: the ISO enum is 7, while the localized number is 1. When storing or receiving a day-of-week number from an external source, you must know which convention that number uses before converting it to `DayOfWeek`.

Do not use `ordinal()` to represent business day-of-week numbers. It is better to use enum constants when selecting a day, and when outputting a number, state clearly whether you are outputting the ISO number or a `WeekFields`-based number.

## 7. Pattern Letters `Y`, `w`, and `e` Also Have Locale-Dependent Rules

In [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html), `Y` is the week-based year, `w` is the week of the week-based year, and `e` has a localized day-of-week number form. Therefore, the same pattern `YYYY-'W'ww-e` with two Locales can produce different results.

The program outputs `2021-01-01` as `2021-W01-6` under the runtime's US configuration and `2020-W53-5` under the France configuration. This is not a formatting bug; the two formatters are using different week rules.

If you need ISO week formatting, use `DateTimeFormatter.ISO_WEEK_DATE` or explicitly specify the fields of the ISO rule. Do not treat `Locale.ROOT` or the presence of the letter `W` in the pattern as a guarantee of ISO rules.

Another common mistake is using `YYYY-MM-dd` for ordinary calendar dates: `Y` places the week-based year next to the calendar month and day, so the label can be wrong at the end or beginning of a year. For ISO calendar dates, the pattern typically needs `uuuu-MM-dd`. Only use `Y` when you intend the week-based year and pair it with the corresponding week fields.

## 8. Applying This to Report Keys and Self-Verification

If you group data by week, define a single shared rule for the entire aggregation. The key should contain both the week-based year and the week number from the same rule; if the data may use multiple rules, the rule configuration must also be known in order to interpret the key. Storing only the number `1` or `53` is not enough to identify a week.

If the initial input is an `Instant`, you must choose a reporting time zone to convert it to a local date before computing week fields. `WeekFields` does not replace `ZoneId`: the zone determines which date is under consideration, while the week rule determines that date's week number.

`WeekFields` is also not a holiday calendar, a 4-4-5 fiscal calendar, or a workweek definition. It partitions and numbers seven-day cycles using the two parameters described above. Specialized rules beyond that scope require their own business model.

When testing a week-reporting algorithm, do not test only mid-year dates. Test several dates at the end of December, the beginning of January, the first day of the week, and the day immediately before it. Cross-check three pieces of information: the calendar year, the year–week pair, and the two parameters of the rule.

Exercise: read `2021-01-03` using `WeekFields.ISO`. The result must have calendar year 2021, year–week pair `2020-W53`, and localized day-of-week number 7. Then read the next day, `2021-01-04`: the pair changes to `2021-W01`, and the day-of-week number returns to 1. Being able to explain this boundary is more important than memorizing a single week number.
