# WeekFields: First Day of Week and Minimal Days in First Week

In Java, `java.time.temporal.WeekFields` describes **week-numbering rules based on the calendar conventions of a locale**. Its two foundational parameters are:

1. **First day of the week** (`firstDayOfWeek`): does a week start on **Monday**, **Sunday**, or another day?
2. **Minimal days in the first week** (`minimalDaysInFirstWeek`): how many days of the new month/year must the first week contain to count as week 1 of that month/year?

These two choices directly affect **week-of-month**, **week-of-year**, and especially **week-based year** at year boundaries. A day in December can belong to **week 1 of the next week-based year**; an early January day can belong to **the final week of the previous week-based year**.

For example, for **2021-01-01 (Friday)**:

- Common US rule: weeks start on **Sunday**, requiring **at least 1 day** in the new year to form week 1. Result: **week 1, week-based year 2021**.
- ISO 8601 rule: weeks start on **Monday**, requiring **at least 4 days** in the new year. Result: **week 53, week-based year 2020**.

This is not a JDK bug. It is **two different week definitions** applied to **the same date**. In international applications, you must agree on the definition before grouping data by week, printing reports, or generating week keys.

This lesson uses Java 17+ to clarify both parameters, the week fields of `WeekFields`, selecting by `Locale`, ISO vs. US differences, the relationship with `DateTimeFormatter`, and common pitfalls.

## 1. What `WeekFields` Is and Is Not

`WeekFields` resides in the `java.time.temporal` package and represents a **set of week calendar rules**. It is **not** a class holding a date, does not alter the system clock, and does not convert instants or time zones.

Common ways to obtain one:

~~~java
WeekFields iso = WeekFields.ISO;
WeekFields sunday = WeekFields.SUNDAY_START;
WeekFields us = WeekFields.of(Locale.US);
WeekFields germany = WeekFields.of(Locale.GERMANY);
WeekFields custom = WeekFields.of(DayOfWeek.MONDAY, 1);
~~~

This is an **in-method snippet**, requiring imports:

~~~java
import java.time.DayOfWeek;
import java.time.temporal.WeekFields;
import java.util.Locale;
~~~

Meanings:

- `WeekFields.ISO` defines **Monday** as the first day of the week and requires **4 days** in the first week.
- `WeekFields.SUNDAY_START` defines **Sunday** as the first day of the week and requires **1 day** in the first week.
- `WeekFields.of(locale)` queries the JDK's locale data/provider for the appropriate week convention.
- `WeekFields.of(DayOfWeek, int)` lets you define a locale-independent policy.

`WeekFields` instances are **immutable** and thread-safe; they can be reused across configurations. More importantly, the `TemporalField` instances obtained from them also embody the chosen week rules.

## 2. First Day of the Week: `firstDayOfWeek`

This parameter determines the **boundary between two consecutive weeks**. If a week starts on **Monday**, a week runs from Monday through Sunday. If it starts on **Sunday**, a week runs from Sunday through Saturday.

Create `WeekStartDemo.java`:

~~~java
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekStartDemo {
    public static void main(String[] args) {
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields de = WeekFields.of(Locale.GERMANY);
        WeekFields iso = WeekFields.ISO;

        System.out.println("US: " + us.getFirstDayOfWeek()
                + ", " + us.getMinimalDaysInFirstWeek());
        System.out.println("DE: " + de.getFirstDayOfWeek()
                + ", " + de.getMinimalDaysInFirstWeek());
        System.out.println("ISO: " + iso.getFirstDayOfWeek()
                + ", " + iso.getMinimalDaysInFirstWeek());
    }
}
~~~

~~~bash
javac WeekStartDemo.java
java WeekStartDemo
~~~

In a JDK 17+ environment with standard week data:

~~~text
US: SUNDAY, 1
DE: MONDAY, 4
ISO: MONDAY, 4
~~~

The strings `SUNDAY` and `MONDAY` are `DayOfWeek` enum constant names, not day names translated into a locale. For other locales, inspect the data directly on the runtime your application uses; do not guess from the language code.

**Key distinction:** Choosing the English language does not mean a user wants weeks starting on Sunday. Week rules are usually tied to **region/country, product settings, or business requirements**, not just the language name.

## 3. What Is Minimal Days in the First Week?

Suppose the new year begins on **Friday**, as on 2021-01-01.

With weeks starting on **Monday**, the week containing that date is:

~~~text
Monday    2020-12-28
Tuesday   2020-12-29
Wednesday 2020-12-30
Thursday  2020-12-31
Friday    2021-01-01
Saturday  2021-01-02
Sunday    2021-01-03
~~~

This week contains exactly **3 days of the new year**: January 1, 2, and 3.

- If `minimalDaysInFirstWeek = 4`, **3 is fewer than 4**, so this is **not yet week 1 of week-based year 2021**. Week 1 begins on **Monday 2021-01-04**; 2021-01-01 remains in the last week of **week-based year 2020**.
- If `minimalDaysInFirstWeek = 1`, **3 meets 1**, so the week starting 2020-12-28 already counts as week 1 of **week-based year 2021** (if using **Monday** as the first day of the week).

Therefore, **not only the first day of the week**, but **also the minimal days count** determines the week-based year.

### Validity constraints

`WeekFields.of(DayOfWeek firstDay, int minimalDays)` accepts `minimalDays` in the range **1–7**. If the value is outside this range, the method throws `IllegalArgumentException`; the first day of the week must be valid and non-null.

Example:

~~~java
WeekFields custom = WeekFields.of(DayOfWeek.MONDAY, 1);
~~~

This configuration differs from `WeekFields.ISO` even though **both start on Monday**: ISO requires 4 days, whereas the custom configuration requires only 1 day.

## 4. How the Two Parameters Work Together

To determine week 1 of a month or year, Java checks how many days of that period fall inside **the week containing the first day of the period**:

1. Determine the week boundaries using `firstDayOfWeek`.
2. Find the week containing day 1 of the month/year.
3. Count how many days of the new month/year lie in that week.
4. If the count is **at least** `minimalDaysInFirstWeek`, that week is **week 1**.
5. If it falls short, the following week becomes **week 1**.

This rule applies at month boundaries for `weekOfMonth()` and year boundaries for `weekOfYear()`; **week-based-year** assignment additionally allows late December days to move into the **next week-based year**.

**Example with 2021-05-01 (Saturday)**:

- Under ISO (Monday, 4 days), the week 2021-04-26 to 2021-05-02 has only **2 days** in May. Thus it is **not yet week 1 of May**, and `weekOfMonth()` returns **0**.
- Under US (Sunday, 1 day), the week 2021-04-25 to 2021-05-01 has **1 day** in May. Since 1 day suffices, `weekOfMonth()` returns **1**.

Having different results for the same date 2021-05-01 is completely logical.

## 5. The `TemporalField` Objects Provided by `WeekFields`

`WeekFields` does not directly expose a `weekNumber(LocalDate)` method. Instead, it provides `TemporalField` instances to query `LocalDate.get(field)` or use with `DateTimeFormatterBuilder`.

| Method | Meaning | Notes |
| --- | --- | --- |
| `dayOfWeek()` | Day number **within the localized week** | First day of week has value 1 |
| `weekOfMonth()` | Week number of the **calendar month** | Can be **0** near the start of the month |
| `weekOfYear()` | Week number of the **calendar year** | Can be **0** near the start of the year |
| `weekOfWeekBasedYear()` | Week number of the **week-based year** | Usually 1 to 52/53 |
| `weekBasedYear()` | Corresponding **week-based year** | Can differ from calendar year |

Make sure to distinguish:

- `weekOfYear()` is tied to the **calendar year** of that date; at the year boundary, it can be 0 or a late-year value.
- `weekOfWeekBasedYear()` is tied to the **week-based year**; it must be paired **with** `weekBasedYear()` to form a valid week identifier.
- `dayOfWeek()` of `WeekFields` is the **ordinal position starting from the chosen first day of week**; it does not alter the `DayOfWeek` enum's values.

Example for retrieving ISO week fields:

~~~java
LocalDate date = LocalDate.of(2021, 1, 1);
WeekFields rule = WeekFields.ISO;

int weekYear = date.get(rule.weekBasedYear());       // 2020
int week = date.get(rule.weekOfWeekBasedYear());     // 53
int localDay = date.get(rule.dayOfWeek());           // 5
~~~

The above is an **in-method snippet**, requiring imports `java.time.LocalDate` and `java.time.temporal.WeekFields`.

## 6. `dayOfWeek()`: Localized Ordering Differs from `DayOfWeek.getValue()`

Java's `DayOfWeek` enum follows ISO ordering:

~~~text
MONDAY=1, TUESDAY=2, ..., SUNDAY=7
~~~

However, with `WeekFields.of(Locale.US)`, **Sunday** is the first day of the week, so:

~~~text
SUNDAY=1, MONDAY=2, ..., SATURDAY=7
~~~

For the same date **Sunday 2021-01-03**:

- `date.getDayOfWeek().getValue()` returns **7** per enum/ISO.
- `date.get(WeekFields.ISO.dayOfWeek())` returns **7**.
- `date.get(WeekFields.of(Locale.US).dayOfWeek())` returns **1**.

Create standalone program **`LocalizedDayNumberDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class LocalizedDayNumberDemo {
    public static void main(String[] args) {
        LocalDate sunday = LocalDate.of(2021, 1, 3);
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields iso = WeekFields.ISO;

        System.out.println(sunday.getDayOfWeek());
        System.out.println(sunday.getDayOfWeek().getValue());
        System.out.println(sunday.get(us.dayOfWeek()));
        System.out.println(sunday.get(iso.dayOfWeek()));
    }
}
~~~

~~~bash
javac LocalizedDayNumberDemo.java
java LocalizedDayNumberDemo
~~~

Output:

~~~text
SUNDAY
7
1
7
~~~

**Do not** use `getDayOfWeek().getValue()` directly to lay out a calendar whose first column is **Sunday**, if the algorithm expects column numbers starting at 1 according to the locale. Use `WeekFields.dayOfWeek()` or convert explicitly.

Conversely, if an application protocol defines days of the week as ISO 1–7, keep `DayOfWeek.getValue()` and do not change its semantics just because of the user's locale.

## 7. `weekOfMonth()`: Why Week 0 Exists

Under `WeekFields.ISO`, May 2021 begins on **Saturday**. May 1 and May 2 belong to a week starting **Monday, April 26**, which contains only **2 days of the new month**. Thus that week does not reach 4 days to become week 1 of May.

Example **`WeekOfMonthDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekOfMonthDemo {
    public static void main(String[] args) {
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields iso = WeekFields.ISO;

        for (int day : new int[]{1, 2, 3}) {
            LocalDate date = LocalDate.of(2021, 5, day);
            System.out.printf("%s US=%d ISO=%d%n",
                    date,
                    date.get(us.weekOfMonth()),
                    date.get(iso.weekOfMonth()));
        }
    }
}
~~~

~~~bash
javac WeekOfMonthDemo.java
java WeekOfMonthDemo
~~~

Output with common US rules:

~~~text
2021-05-01 US=1 ISO=0
2021-05-02 US=2 ISO=0
2021-05-03 US=2 ISO=1
~~~

**Week 0 is not corrupt data.** It represents the initial days of the month that do not yet meet the criterion for the first week. When displaying "week of month", the application must decide whether to:
- preserve the exact `WeekFields.weekOfMonth()` value, including week 0;
- number the **calendar grid rows** starting from 1 (a different UI convention);
- or display **date ranges** instead of just a week number.

Avoid mechanically adding 1 to the result: doing so masks rule differences and can produce duplicate week numbers.

## 8. `weekOfYear()` Is Not Equivalent to `weekOfWeekBasedYear()`

This is the most critical error when aggregating weekly reports.

For **2021-01-01** under ISO:

- Calendar year: **2021**.
- `weekOfYear()`: **0**, because the week containing Jan 1 lacks 4 days in 2021.
- `weekBasedYear()`: **2020**.
- `weekOfWeekBasedYear()`: **53**.

Under common US rules for that exact same date:

- Calendar year: **2021**.
- `weekOfYear()`: **1**.
- `weekBasedYear()`: **2021**.
- `weekOfWeekBasedYear()`: **1**.

In reporting logic:
- If you need **a consistent week label that spans seamlessly across December/January**, use **the `weekBasedYear + weekOfWeekBasedYear` pair**.
- If you are genuinely asking "which week **within this calendar year**", `weekOfYear` has its own semantics, including the possibility of week 0.
- Never pair `date.getYear()` with `weekOfWeekBasedYear()` and treat it as a standard week identifier.

### Runnable example

Create **`WeekFieldsBoundaryDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekFieldsBoundaryDemo {
    private static String label(LocalDate date, WeekFields fields) {
        int weekBasedYear = date.get(fields.weekBasedYear());
        int week = date.get(fields.weekOfWeekBasedYear());
        int calendarWeek = date.get(fields.weekOfYear());

        return weekBasedYear + "-W" + week + " / y" + calendarWeek;
    }

    public static void main(String[] args) {
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields iso = WeekFields.ISO;

        for (String input : new String[]{
                "2020-12-31", "2021-01-01", "2021-01-04"}) {
            LocalDate date = LocalDate.parse(input);
            System.out.println(date + " US=" + label(date, us)
                    + " ISO=" + label(date, iso));
        }
    }
}
~~~

~~~bash
javac WeekFieldsBoundaryDemo.java
java WeekFieldsBoundaryDemo
~~~

Output on a JDK with common US rules:

~~~text
2020-12-31 US=2021-W1 / y53 ISO=2020-W53 / y53
2021-01-01 US=2021-W1 / y1 ISO=2020-W53 / y0
2021-01-04 US=2021-W2 / y2 ISO=2021-W1 / y1
~~~

The first line is especially noteworthy: **2020-12-31 belongs to calendar year 2020**, yet under US rules it already lies in **week-based year 2021**. Thus grouping by `calendarYear=2020, week=1` can produce an incorrect or colliding report group.

## 9. ISO First Week of the Year: The "At Least 4 Days" Rule

The ISO 8601 rule is commonly stated in three equivalent ways:

- Weeks start on **Monday**, and week 1 is the week with **at least four days in the new year**.
- Week 1 is the week containing **January 4**.
- Week 1 is the week containing the **first Thursday of the year**.

Example for 2021:
- 2021-01-01 is a Friday.
- The week 2020-12-28 through 2021-01-03 has only three days in 2021.
- Week 1 of week-based year 2021 begins on **2021-01-04**.
- Date 2021-01-01 belongs to **2020-W53**.

A week-based year can have **52 or 53 weeks**. That is why a code like "2021-W53" cannot automatically be assumed valid under every definition. Validate whether the week number exists under the actual week-based year and rules in use.

`WeekFields.ISO` is the clear choice when **data contracts require ISO weeks**, regardless of which country the user is in. `WeekFields.of(locale)` is the choice when **calendar UIs should follow the user's local convention**.

## 10. `WeekFields.of(Locale)` and Locale Stability

Different locales can use different week-start days and minimal-days rules. Java obtains these from the runtime's locale service:

~~~java
WeekFields fields = WeekFields.of(locale);
DayOfWeek first = fields.getFirstDayOfWeek();
int minimal = fields.getMinimalDaysInFirstWeek();
~~~

This is a snippet; `locale` must be supplied at the call site. Locales such as `en-US` and `de-DE` typically yield the rules illustrated above, but JDK/provider data can vary across versions or runtime configurations.

**Do not equate language with country.** Locales `en-US` and `en-GB` can have different week rules; a locale without a region can use fallback data. If the system requires an invariant business-defined week rule, configure **first day of week + minimal days** explicitly, or use `WeekFields.ISO`.

For applications:
1. **Personal calendar UI**: can rely on `WeekFields.of(userLocale)`.
2. **Enterprise standard reports**: should use the rule documented in the contract, such as ISO even if the user's locale differs.
3. **Cross-system synchronization**: exchange the rule identifier as well, or standardize on ISO to avoid mismatches when decoding week numbers.

Never use "the device's first day of week" as the standard for all business reports if the system already has a fixed specification.

## 11. Customizing First Day of Week and Minimal Days

You can define a custom policy:

~~~java
WeekFields mondayOneDay = WeekFields.of(DayOfWeek.MONDAY, 1);
WeekFields mondayFourDays = WeekFields.of(DayOfWeek.MONDAY, 4);
~~~

Both start on **Monday**, yet their selection of week 1 differs. For New Year's Day 2021:

- `mondayOneDay`: the week starting 2020-12-28 has three days in 2021, which meets **1** ⇒ belongs to week 1 of **week-based year 2021**.
- `mondayFourDays`: three days do not meet **4** ⇒ belongs to week 53 of **week-based year 2020**.

Create **`CustomWeekRuleDemo.java`**:

~~~java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.WeekFields;

public class CustomWeekRuleDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);

        WeekFields one = WeekFields.of(DayOfWeek.MONDAY, 1);
        WeekFields four = WeekFields.of(DayOfWeek.MONDAY, 4);

        System.out.println(one.getFirstDayOfWeek());
        System.out.println(one.getMinimalDaysInFirstWeek());
        System.out.println(date.get(one.weekBasedYear())
                + "-W" + date.get(one.weekOfWeekBasedYear()));
        System.out.println(date.get(four.weekBasedYear())
                + "-W" + date.get(four.weekOfWeekBasedYear()));
    }
}
~~~

~~~bash
javac CustomWeekRuleDemo.java
java CustomWeekRuleDemo
~~~

Output:

~~~text
MONDAY
1
2021-W1
2020-W53
~~~

This experiment proves **you cannot deduce week numbers from the week start day alone**. You need the second parameter as well.

If a project builds a "fiscal calendar" or "retail week", check whether that policy actually matches a `WeekFields` configuration. Some fiscal calendars use 4-4-5 periods or custom rules that require a dedicated domain model rather than forcing them into `WeekFields`.

## 12. Naming Weeks Properly When Storing Reports or Building Keys

Suppose a system stores weekly aggregated data. An error-prone design:

~~~text
key = calendarYear + "-" + weekOfWeekBasedYear
~~~

On `2021-01-01` under ISO, this produces `2021-53`. Yet this date belongs to **week-based year 2020**, not 2021.

A better design under ISO rules:

~~~java
WeekFields fields = WeekFields.ISO;

int year = date.get(fields.weekBasedYear());
int week = date.get(fields.weekOfWeekBasedYear());

String key = "%04d-W%02d".formatted(year, week);
~~~

This is an in-method **snippet**, requiring `WeekFields` imported; `date` is a validated `LocalDate`. For 2021-01-01, `key` is:

~~~text
2020-W53
~~~

If the product uses US rules, both `weekBasedYear` and `weekOfWeekBasedYear` must come from **the same** `WeekFields.of(Locale.US)`. Never take the ISO week-based year and combine it with a US week number, or mix in a calendar year from another context.

Moreover, if the same system allows **multiple week rules**, then the same label such as `2021-W01` can represent **different date ranges**. Data keys should include the rule name, or better yet **the week's start and end dates**, computed under an explicitly recorded policy.

## 13. `DateTimeFormatter` and the Pattern Letters `Y`, `w`, `e`

Java can apply locale week rules directly inside date-time patterns:

| Pattern Symbol | Meaning in `DateTimeFormatter` |
| --- | --- |
| `u` | ISO proleptic year |
| `y` | Year within an era (*year-of-era*) |
| `Y` | **Localized week-based year** |
| `w` | **Localized week of week-based year** |
| `W` | **Localized week of month** |
| `e` / `c` | Localized day of week |
| `E` | Day-of-week name (e.g. Mon, Monday) |

The `Y` syntax is **not synonymous** with `y` or `u`. A pattern like `YYYY-MM-dd` uses **week-based year** together with **calendar month and day**, mixing two conceptual models.

In late December, `YYYY` can roll over to **the next year**. This is a formatting bug frequently seen in log filenames or form exports due to confusing `YYYY` with `yyyy`/`uuuu`.

### Runnable example

Create **`LocalizedWeekPatternDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocalizedWeekPatternDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2020, 12, 31);

        DateTimeFormatter us =
                DateTimeFormatter.ofPattern(
                        "YYYY-'W'ww-e", Locale.US);

        DateTimeFormatter de =
                DateTimeFormatter.ofPattern(
                        "YYYY-'W'ww-e", Locale.GERMANY);

        DateTimeFormatter mixed =
                DateTimeFormatter.ofPattern(
                        "YYYY-MM-dd", Locale.US);

        System.out.println(us.format(date));
        System.out.println(de.format(date));
        System.out.println(mixed.format(date));
    }
}
~~~

~~~bash
javac LocalizedWeekPatternDemo.java
java LocalizedWeekPatternDemo
~~~

Output with common US/DE rules:

~~~text
2021-W01-5
2020-W53-4
2021-12-31
~~~

The final line is a **cautionary example**: the actual date is **2020-12-31**, yet `YYYY-MM-dd` produces `2021-12-31` because `YYYY` is the US week-based year.

When you only need a stable calendar date, you can use:

~~~java
DateTimeFormatter dateFormat =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");
~~~

Or for `LocalDate`, prefer `LocalDate.toString()` or `DateTimeFormatter.ISO_LOCAL_DATE` for ISO strings. When you need **week** labels, use `Y`/`w`/`e` consistently or the fields from an explicit `WeekFields`.

## 14. Comparing `WeekFields.ISO` with `IsoFields` and `ChronoField`

Java offers several ways to access "week"; their names look similar, yet their meanings differ.

| API | Definition |
| --- | --- |
| `WeekFields.ISO` | ISO week rules: Monday, minimum 4 days |
| `WeekFields.of(locale)` | Week rules from locale data |
| `IsoFields.WEEK_OF_WEEK_BASED_YEAR` | ISO week number, equivalent in purpose to ISO week of week-based year |
| `IsoFields.WEEK_BASED_YEAR` | ISO week-based year |
| `ChronoField.ALIGNED_WEEK_OF_YEAR` | Splits days of the year into consecutive 7-day blocks from Jan 1, **not based on locale week start** |
| `ChronoField.ALIGNED_WEEK_OF_MONTH` | Consecutive 7-day blocks from the start of the month, **different from `WeekFields.weekOfMonth()`** |

Example for **2021-01-01**:

~~~text
ISO weekOfYear:                 0
ISO weekOfWeekBasedYear:       53
ISO weekBasedYear:           2020
ALIGNED_WEEK_OF_YEAR:          1
~~~

`ALIGNED_WEEK_OF_YEAR` counts days 1–7 as group 1, days 8–14 as group 2, and so on; this is **not** a "Monday-to-Sunday week" definition. Therefore do not use `ALIGNED_WEEK_OF_YEAR` in place of `WeekFields.weekOfWeekBasedYear()` when the product requires calendar weeks.

### Confirming with code

~~~java
LocalDate date = LocalDate.of(2021, 1, 1);

System.out.println(date.get(
        java.time.temporal.ChronoField.ALIGNED_WEEK_OF_YEAR));
System.out.println(date.get(WeekFields.ISO.weekOfYear()));
System.out.println(date.get(WeekFields.ISO.weekOfWeekBasedYear()));
~~~

This is a **snippet**, requiring `LocalDate` and `WeekFields` imported. Output:

~~~text
1
0
53
~~~

`WeekFields.ISO` is a rule configuration; `IsoFields` is a set of dedicated ISO fields; `ChronoField.ALIGNED_*` groups days from the start of the period. Choose the right tool for the problem.

## 15. Formatting and Parsing Unambiguous Week Labels

A week label typically includes:
- **Week-based year**, not necessarily the calendar year;
- **Week number** within that week-based year;
- If identifying a single day is required, the **day of the week**.

Java provides a standard ISO formatter:

~~~java
DateTimeFormatter.ISO_WEEK_DATE
~~~

It uses ISO week rules and formats dates like:

~~~text
2020-W53-5
~~~

This means ISO week-based year 2020, week 53, ISO day 5 of the week, corresponding to **2021-01-01**.

Create **`IsoWeekParseDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public class IsoWeekParseDemo {
    public static void main(String[] args) {
        String source = "2020-W53-5";
        LocalDate parsed =
                LocalDate.parse(source, DateTimeFormatter.ISO_WEEK_DATE);

        System.out.println(parsed);
        System.out.println(DateTimeFormatter.ISO_WEEK_DATE.format(parsed));
    }
}
~~~

~~~bash
javac IsoWeekParseDemo.java
java IsoWeekParseDemo
~~~

Output:

~~~text
2021-01-01
2020-W53-5
~~~

**Note:** A label with only `2020-W53` describes **an entire week**, not a single day. To convert it to a `LocalDate`, you must explicitly pick which day of the week (such as Monday starting the week) and the appropriate week rule set. Never guess the day.

### Locale-based patterns can be parsed back with the same locale

Example:

~~~java
DateTimeFormatter us =
        DateTimeFormatter.ofPattern(
                "YYYY-'W'ww-e", Locale.US);

DateTimeFormatter de =
        DateTimeFormatter.ofPattern(
                "YYYY-'W'ww-e", Locale.GERMANY);

System.out.println(LocalDate.parse("2021-W01-6", us));
System.out.println(LocalDate.parse("2020-W53-5", de));
~~~

This is an **in-method snippet**, requiring `LocalDate`, `DateTimeFormatter`, and `Locale` imported. Under common US/DE rules, the output is:

~~~text
2021-01-01
2021-01-01
~~~

Each input uses **its respective locale's day-of-week numbering and week-based year**. Do not take US `2021-W01-6` and parse it with an ISO formatter, because `6` means different days of the week in the two systems.

## 16. Computing the Start Date of a Week to Build a Calendar

Many UIs care more about **the first day of the week** than the week number. You can use `TemporalAdjusters.previousOrSame(fields.getFirstDayOfWeek())`.

Create **`WeekStartDateDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekStartDateDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields iso = WeekFields.ISO;

        LocalDate usStart = date.with(
                TemporalAdjusters.previousOrSame(
                        us.getFirstDayOfWeek()));

        LocalDate isoStart = date.with(
                TemporalAdjusters.previousOrSame(
                        iso.getFirstDayOfWeek()));

        System.out.println(usStart);
        System.out.println(isoStart);
    }
}
~~~

~~~bash
javac WeekStartDateDemo.java
java WeekStartDateDemo
~~~

Output:

~~~text
2020-12-27
2020-12-28
~~~

This is the one-day offset between the US week and the ISO week containing 2021-01-01.

**Clear distinction:** `getFirstDayOfWeek()` **alone** defines week boundaries; it does **not** need `minimalDaysInFirstWeek` to compute the start date of **the week containing `date`**. The minimal days parameter is still required to determine the **week number and week-based year label** for that week.

To get the end date of the week, add six days to the start date just found:

~~~java
LocalDate end = start.plusDays(6);
~~~

This is a snippet; `start` is the computed `LocalDate`. The UI should format the date range per locale, while the system stores canonical identifiers or ISO dates.

## 17. Applying the Same Rules Across UI, API, and Reports

A project typically uses weeks in many places:

- **Date picker**: whether Monday or Sunday is the first column;
- **Work schedule**: start and end dates of a week;
- **Sales reports**: week labels and aggregations;
- **CSV/JSON exports**: week identifiers;
- **Database queries**: grouping by week;
- **External synchronization**: matching ISO weeks or partner conventions.

If the UI uses `WeekFields.of(userLocale)`, while the backend defaults to ISO and the database uses a week function with another default rule, **labels and date ranges can diverge**. For instance, a transaction on 2020-12-31 might fall in `2021-W01` on a US UI but `2020-W53` in an ISO report.

Sustainable design guidelines:

1. Specify **which features use ISO weeks** and which allow localized calendars.
2. Store/transmit **the week rule** whenever week labels carry long-term business meaning.
3. For data exchange, consider storing the **week start date** or `[start, end)` interval as ISO dates, along with the time zone if data originates from timestamps.
4. Take `weekBasedYear + weekOfWeekBasedYear` from **the same `WeekFields`** when building labels.
5. Test year-boundary and month-boundary dates, not just mid-year dates.

### Separating a date's week from a timestamp's time zone

`WeekFields` operates on **calendar dates**, whereas `Instant` is an absolute point in time. If the input is a timestamp, determine the `ZoneId` first and then convert:

~~~java
LocalDate localDate = instant.atZone(zone).toLocalDate();
int weekYear = localDate.get(fields.weekBasedYear());
int week = localDate.get(fields.weekOfWeekBasedYear());
~~~

This is a snippet; `instant`, `zone`, and `fields` must be provided explicitly. The same `Instant` can fall on **two different dates in two zones**, and therefore into **two different weeks**. `WeekFields` does not choose a zone automatically; never pass a time zone implicitly via locale.

## 18. Performance, Immutability, and Caching

`WeekFields` is immutable. Calling `WeekFields.ISO` or `WeekFields.of(locale)` is not something to optimize inside loops at all costs; you can store the configuration in a variable and reuse it:

~~~java
private static final WeekFields BUSINESS_WEEK =
        WeekFields.ISO;
~~~

This is a snippet placed inside a class.

If the application caches weekly aggregation results, treat the **week rule** as a key dimension:
- Source date or date range;
- `firstDayOfWeek`;
- `minimalDaysInFirstWeek`;
- Time zone applied when the source is a timestamp;
- Policy version if the business changes rules.

Caching only by `weekNumber` without `weekBasedYear` is wrong; week 1 occurs in many years. Caching only by `year + week` without knowing whether ISO or US rules apply can also be wrong because **date ranges differ**.

Week formatters built on `DateTimeFormatter` should also specify an explicit locale. `DateTimeFormatter` is immutable and can be shared once configured; never abuse `Locale.setDefault(...)` to switch rules per request.

## 19. Testing: Minimum Test Cases

| Case | What to Verify |
| --- | --- |
| `WeekFields.ISO` | `MONDAY`, minimal days = 4 |
| `WeekFields.SUNDAY_START` | `SUNDAY`, minimal days = 1 |
| `WeekFields.of(Locale.US)` | Runtime data is typically Sunday / 1 |
| `WeekFields.of(Locale.GERMANY)` | Runtime data is typically Monday / 4 |
| 2021-01-01 under ISO | `2020-W53`, `weekOfYear() == 0` |
| 2021-01-01 under US | `2021-W1` |
| 2020-12-31 under US | Calendar year 2020, week-based year 2021 |
| 2021-05-01 under ISO | `weekOfMonth() == 0` |
| Sunday under US | `fields.dayOfWeek() == 1` |
| `ALIGNED_WEEK_OF_YEAR` vs `weekOfYear` | Do not confuse the two definitions |
| `YYYY` at year end | Can shift into the next week-based year |
| Parsing weeks | Uses matching locale rules and validates week existence |
| Timestamp to week | Explicit zone before obtaining `LocalDate` |
| JDK/provider change | Re-verify locale week data if using localized rules |

### Simple Java test with no external libraries

Create **`WeekFieldsAssertions.java`**:

~~~java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekFieldsAssertions {
    public static void main(String[] args) {
        LocalDate boundary = LocalDate.of(2021, 1, 1);
        WeekFields iso = WeekFields.ISO;
        WeekFields us = WeekFields.of(Locale.US);

        if (boundary.get(iso.weekBasedYear()) != 2020
                || boundary.get(iso.weekOfWeekBasedYear()) != 53) {
            throw new AssertionError("Unexpected ISO week");
        }

        if (boundary.get(us.weekBasedYear()) != 2021
                || boundary.get(us.weekOfWeekBasedYear()) != 1) {
            throw new AssertionError("Unexpected US week");
        }

        LocalDate monthStart = LocalDate.of(2021, 5, 1);
        if (monthStart.get(iso.weekOfMonth()) != 0) {
            throw new AssertionError("Unexpected ISO week of month");
        }

        System.out.println("PASS");
    }
}
~~~

~~~bash
javac WeekFieldsAssertions.java
java WeekFieldsAssertions
~~~

Output on a runtime using the stated US week rules:

~~~text
PASS
~~~

To avoid depending on JDK locale data when testing fixed algorithms, use `WeekFields.SUNDAY_START` instead of `WeekFields.of(Locale.US)` in tests that require the **Sunday / 1 day** rule, and keep a separate test to verify the active locale data.

## 20. Common Pitfalls

1. **"Everywhere starts the week on Monday."** False. The first day of the week varies by region or product policy.
2. **"Knowing the first day of the week is enough to calculate all week numbers."** False. `minimalDaysInFirstWeek` also determines week 1.
3. **"The first week of the year always contains January 1."** Not in the sense of `weekOfWeekBasedYear() == 1` for Jan 1. Under ISO, 2021-01-01 is in `2020-W53`.
4. **"Week-based year always matches calendar year."** False at boundaries; under US rules, 2020-12-31 can be in week-based year 2021.
5. **"`weekOfYear()` and `weekOfWeekBasedYear()` are the same."** False; they handle year boundaries differently.
6. **"Week 0 is invalid data."** False; `weekOfMonth` or `weekOfYear` can legitimately return 0 under minimal-days rules.
7. **"`DayOfWeek.getValue()` is always the locale's calendar column index."** False; the enum uses ISO with Monday = 1, whereas `WeekFields.dayOfWeek()` is localized.
8. **"`ChronoField.ALIGNED_WEEK_OF_YEAR` uses ISO weeks."** False; aligned fields split the year into 7-day blocks starting from Jan 1.
9. **"`YYYY-MM-dd` is the standard calendar date format."** False; `YYYY` is **week-based year** and can print the wrong year for a calendar date.
10. **"Locale and zone are the same."** False; locale governs week/display conventions, while zone converts timestamps into local dates.
11. **"Storing only the week number is enough for reports."** False; you also need the week-based year and the week rule.
12. **"ISO weeks and US weeks can be converted by adding/subtracting 1."** False; week start days and year boundaries differ.
13. **"Every month starts in week 1."** `weekOfMonth()` can be 0 when the start of the month lacks enough minimal days.
14. **"If `Locale.US` is present, the business system must use US weeks."** No; business data may mandate fixed ISO weeks.

## 21. Self-Check Exercises

**Q1.** What first day of week and minimal days in the first week does `WeekFields.ISO` use?

**Answer:** `MONDAY` and `4`.

**Q2.** Why is `2021-01-01` in `2020-W53` under ISO even though its calendar year is 2021?

**Answer:** The week 2020-12-28 to 2021-01-03 has only three days in 2021, fewer than four, so it belongs to week-based year 2020.

**Q3.** For a Sunday, why does `DayOfWeek.getValue()` return 7 while `WeekFields.SUNDAY_START.dayOfWeek()` returns 1?

**Answer:** The `DayOfWeek` enum uses ISO ordering, while `WeekFields.dayOfWeek()` numbers days starting from the chosen first day of the week.

**Q4.** Why can `weekOfMonth()` under ISO return 0 for `2021-05-01`?

**Answer:** The week containing May 1 has only two days in May, failing the four-day requirement.

**Q5.** To store the ISO week code for `2021-01-01`, which `year` and `week` should you use?

**Answer:** `weekBasedYear=2020` and `weekOfWeekBasedYear=53`, producing the label `2020-W53`.

**Q6.** If you only want the start date of the week containing `2021-01-01` under US rules, what should you use?

**Answer:** `date.with(TemporalAdjusters.previousOrSame(fields.getFirstDayOfWeek()))`, returning `2020-12-27` for a Sunday-start configuration.

**Q7.** When should you use `WeekFields.of(locale)` and when should you use `WeekFields.ISO`?

**Answer:** Use the locale-based one for user-facing local calendar UIs; use ISO when reporting or exchange contracts require stable ISO weeks.

**Q8.** When a system processes an `Instant`, why can't it apply week rules directly without a `ZoneId`?

**Answer:** `Instant` is an absolute point in time; the calendar date can vary by zone. You must convert it to a `LocalDate` in the business zone before computing weeks.

**Q9.** What is wrong with the pattern `YYYY-MM-dd` if the goal is a calendar date?

**Answer:** Uppercase `Y` is the localized week-based year; `MM-dd` are calendar month and day, which can produce a string whose year does not match the actual date.

**Q10.** Do minimal days = 1 and 4 produce the same result when both start the week on Monday?

**Answer:** Not necessarily. `2021-01-01` is an example: with 1 day it belongs to week-based year 2021; with 4 days it belongs to week-based year 2020.

## 22. Proper Project Workflow

1. **Define what "week" means per feature**: UI calendar week, reporting week, partner exchange week, or fiscal week.
2. **Decide the two core parameters**: first day of week and minimal days in first week; use `WeekFields.ISO` or an explicit configuration when stability is required.
3. **If using locale**, obtain `WeekFields.of(userLocale)`, and test across target locales and runtime versions.
4. **When constructing week labels**, read `weekBasedYear()` and `weekOfWeekBasedYear()` from **the same** `WeekFields`.
5. **When rendering calendars**, get the week start day via `getFirstDayOfWeek()` and `TemporalAdjusters` rather than deriving column order from ISO enum ordinals if the calendar starts on Sunday.
6. **When the source is a timestamp**, convert to a date in the proper `ZoneId` before applying week rules.
7. **When exporting data**, use ISO identifiers when partners expect ISO; document the week rule explicitly if non-ISO, and avoid `YYYY-MM-dd` for calendar dates.
8. **Test boundary dates**, such as late December / early January, month starts falling on Saturday/Sunday, and years containing week 53.
9. **Keep rules consistent** across backend, UI, and database grouping functions.

**Takeaway:** `WeekFields` is defined by **two parameters** — **first day of the week** and **minimal days in the first week**. `weekOfYear` is the week within the **calendar year**; `weekBasedYear` pairs with `weekOfWeekBasedYear` to identify a **week-based year** that may differ from the calendar year. These distinctions determine the correctness of calendars, reports, and weekly aggregated data.

**Java SE 17 Documentation:** [WeekFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html), [IsoFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/IsoFields.html), [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).
