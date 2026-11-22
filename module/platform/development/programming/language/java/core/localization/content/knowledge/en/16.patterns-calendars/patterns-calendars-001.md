# Distinguishing u, y, and Y in Java DateTimeFormatter Year Patterns

## 1. Why Are These Three Letters Not Interchangeable?

When working with dates and localization in Java, a very subtle bug is writing `YYYY-MM-dd` instead of `uuuu-MM-dd` or `yyyy-MM-dd`. For most days of the year they may display the same result, but **around the turn of the year**, `YYYY` can produce **a completely different year from the calendar year of that date**.

In the `java.time.format.DateTimeFormatter` API:

| Pattern Letter | Field Name | Meaning |
|---|---|---|
| `u` | *year* (proleptic year) | Continuous calendar year, including year 0 and negative years |
| `y` | *year-of-era* | Year number **within an era** (for example, AD/BC in the ISO calendar) |
| `Y` | *week-based-year* | Year according to the **week system** defined by the locale |

All three letters relate to "year", but they belong to **three different calendar models**. In particular, `Y` is an **uppercase** letter, not a capitalized decorative version of `y`.

For example, the date **2021-01-01** belongs to:

- Calendar year (proleptic year) **2021**: `u = 2021`.
- Year in the Common Era **2021**: `y = 2021`, era `AD`.
- Week-based year **2020** under ISO week rules (starting on Monday, with the first week having at least 4 days in the new year): `Y = 2020`.

If you use `YYYY-MM-dd` with a locale that uses ISO rules to format January 1, 2021, you can get a string like **`2020-01-01`** — a misleading combination because the month/day part is still 01/01 while the year is taken from the week system.

**Practical rule:** when formatting a normal ISO calendar date, prefer `uuuu-MM-dd`; only use `YYYY` when you **truly want to display the week number and the week-based year**, such as `2020-W53`.

## 2. Core Concepts: Proleptic Year, Era, and Week-Based Year

### 2.1. Proleptic year — the `u` letter

A *proleptic year* is a continuous sequence of year numbers crossing the boundary before and after the Common Era. For `LocalDate` in the ISO calendar:

- `0001` is year 1 AD.
- `0000` is year 1 BC.
- `-0001` is year 2 BC.

This model is convenient for date arithmetic and validation **without having to pair an era**. `LocalDate.getYear()` uses this year representation.

The pattern:

```text
uuuu-MM-dd
```

represents the proleptic year and month/day. For ordinary AD dates, `uuuu` looks very similar to `yyyy`, so the difference is easy to overlook.

### 2.2. Year-of-era — the `y` letter

*Year-of-era* is the **year counted within an era**. In the ISO calendar there are two main eras:

- `AD`/`CE`: calendar years from 1 upward.
- `BC`/`BCE`: years before 1 AD.

Year-of-era **has no year 0**. For example, a date in proleptic year 0 has `year-of-era = 1` and era BC. A date in proleptic year -1 has `year-of-era = 2` and era BC.

The pattern `yyyy-MM-dd` alone does not specify an era, so during strict parsing, the parser may lack enough data to construct a `LocalDate`. When genuinely handling eras, you usually need the `G` letter:

```text
G yyyy-MM-dd
```

`G` is the era name; `yyyy` is the year within the era. If the content is simply a computable ISO calendar date, `uuuu` is usually clearer.

### 2.3. Week-based-year — the `Y` letter

A week-based year does not necessarily change on **January 1**. A week can span across December and January. Week-numbering systems need to decide:

1. Which day is considered the first day of the week? Monday or Sunday?
2. How many days must a week have in the new year to count as the first week of the year?

Therefore, the last week of December can be **week 1 of the next year**, while the first week of January can still belong to **the last week of the previous year**.

The `Y` letter in `DateTimeFormatter` uses **locale-dependent week rules**, via `WeekFields`. Hence the same `LocalDate` can have different `Y` values when formatted with `Locale.UK` and `Locale.US`.

## 3. Week-Related Pattern Letters

You should not use `Y` alone and combine it with month/day as an ordinary calendar pattern. For weekly reports, the letters have specific meanings:

| Letter | Field | Example |
|---|---|---|
| `Y` | Localized week-based year | `2020` |
| `w` | Week of week-based year according to locale rules | `53` |
| `W` | Week of month according to locale rules | `1` |
| `e` or `c` | Day of week in localized order (numeric/text depending on width) | UK: Monday = `1`, US: Sunday = `1` |
| `E` | Name of day of week, e.g. `Mon`/`Monday` by locale | `Fri` |
| `M` | Month of calendar year | `01` |
| `d` | Day of month | `01` |

A more semantically appropriate pattern for expressing weeks:

```text
YYYY-'W'ww-e
```

For example, with `Locale.UK`, 2021-01-01 belongs to `2020-W53-5`: week-based year 2020, week 53, day 5 in a week starting on Monday.

**Case sensitivity:** `w` and `W` are not the same; `w` is week-of-week-based-year, while `W` is week-of-month. `M` is month, while `m` is minute. Java pattern letters **are case-sensitive** and must not be changed arbitrarily.

Fixed literal strings need to be enclosed in single quotes, such as `'W'` to print the literal letter `W`, preventing the parser from interpreting `W` as the week-of-month field.

## 4. Locale and Week Rules Determine the Result of Y

Two locales commonly used to observe the difference:

- `Locale.UK` has week rules matching standard ISO: the week starts on **Monday**, and the first week requires at least **4 days** in the new year.
- `Locale.US` typically starts the week on **Sunday**, and the first week requires at least **1 day** of the new year.

`WeekFields.of(locale)` shows the rules being used. That is why **you cannot simply say that every `YYYY` is an "ISO week-year"**. `YYYY` in `DateTimeFormatter.ofPattern(..., locale)` is the **locale-dependent week-based-year**.

For several dates around 2020–2021:

| Calendar Date | `u`/`y` with ISO AD | `Y` and week with UK | `Y` and week with US |
|---|---|---|---|
| 2020-12-27 | 2020 | `2020-W52` | `2021-W01` |
| 2020-12-28 | 2020 | `2020-W53` | `2021-W01` |
| 2020-12-31 | 2020 | `2020-W53` | `2021-W01` |
| 2021-01-01 | 2021 | `2020-W53` | `2021-W01` |
| 2021-01-03 | 2021 | `2020-W53` | `2021-W02` |
| 2021-01-04 | 2021 | `2021-W01` | `2021-W02` |

Thus, **December 31, 2020** can already carry week-based year 2021 in the US, whereas **January 1, 2021** still belongs to week-based year 2020 in UK/ISO.

You should not use the result from one country's week system to label weekly data for another country. When a report is computed under ISO 8601, explicitly choose ISO rules rather than letting the JVM's default locale decide implicitly.

## 5. Complete Java 17+ Example: Comparing u, y, Y at the Year Boundary

Create the file `YearPatternDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

public class YearPatternDemo {
    public static void main(String[] args) {
        DateTimeFormatter uk = DateTimeFormatter.ofPattern(
                "uuuu yyyy YYYY-'W'ww-e", Locale.UK);
        DateTimeFormatter us = DateTimeFormatter.ofPattern(
                "uuuu yyyy YYYY-'W'ww-e", Locale.US);

        List<LocalDate> days = List.of(
                LocalDate.of(2020, 12, 27),
                LocalDate.of(2020, 12, 28),
                LocalDate.of(2020, 12, 31),
                LocalDate.of(2021, 1, 1),
                LocalDate.of(2021, 1, 3),
                LocalDate.of(2021, 1, 4));

        for (LocalDate day : days) {
            System.out.printf(
                    "%s UK=%s US=%s%n",
                    day, day.format(uk), day.format(us));
        }
    }
}
```

Compile and run:

```bash
javac YearPatternDemo.java
java YearPatternDemo
```

Output verified with the JDK:

```text
2020-12-27 UK=2020 2020 2020-W52-7 US=2020 2020 2021-W01-1
2020-12-28 UK=2020 2020 2020-W53-1 US=2020 2020 2021-W01-2
2020-12-31 UK=2020 2020 2020-W53-4 US=2020 2020 2021-W01-5
2021-01-01 UK=2021 2021 2020-W53-5 US=2021 2021 2021-W01-6
2021-01-03 UK=2021 2021 2020-W53-7 US=2021 2021 2021-W02-1
2021-01-04 UK=2021 2021 2021-W01-1 US=2021 2021 2021-W02-2
```

Reading a key line:

```text
2021-01-01 UK=2021 2021 2020-W53-5 US=2021 2021 2021-W01-6
```

- `2021-01-01` at the start of the line is `LocalDate.toString()`, which uses the ISO calendar year.
- The first two numbers in the `UK` column correspond to `uuuu` and `yyyy`: both are 2021 because this is an AD date.
- `2020-W53-5` is the UK/ISO week-based year 2020.
- `2021-W01-6` is the US week-based year 2021, day 6 in a week starting on Sunday.

This shows that `Y` changes according to **week rules**, not because the formatter is broken or `LocalDate` holds two different dates.

## 6. When to Use u Instead of y?

For ISO `LocalDate` and storing/reading calendar dates:

```text
uuuu-MM-dd
```

is a solid choice. `u` directly represents the continuous year, including year 0 and negative years if the application domain supports them.

`y` is right when the data actually represents **year within an era**. For modern AD dates, the two letters look identical:

```text
Date 2024-02-29:
uuuu -> 2024
yyyy -> 2024
```

But the difference becomes apparent for historical BC dates. In the ISO proleptic calendar:

| `LocalDate.getYear()` | Era | `yyyy` | `uuuu` |
|---:|---|---|---|
| `1` | AD | `0001` | `0001` |
| `0` | BC | `0001` | `0000` |
| `-1` | BC | `0002` | `-0001` |

**There is no year 0 in year-of-era**, whereas there is a year 0 in proleptic-year. Therefore, `yyyy` is insufficient to describe a historical date if the era is missing.

### Complete Java 17+ example on year 0 and BC/AD

Create the file `EraYearDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class EraYearDemo {
    public static void main(String[] args) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern(
                        "G yyyy uuuu", Locale.US);

        int[] years = {1, 0, -1};

        for (int year : years) {
            LocalDate date = LocalDate.of(year, 1, 1);
            System.out.println(
                    "year=" + year + " -> " + date.format(formatter));
        }
    }
}
```

Compile/run:

```bash
javac EraYearDemo.java
java EraYearDemo
```

Output:

```text
year=1 -> AD 0001 0001
year=0 -> BC 0001 0000
year=-1 -> BC 0002 -0001
```

This example highlights the **difference in meaning**, not just zero-padding differences. If your system needs to exchange ISO calendar dates, standardize on proleptic year. If you need to display historical eras, use `G` together with `y` and an appropriate locale.

## 7. Risks When Parsing Dates with ResolverStyle.STRICT

`DateTimeFormatter` not only formats but also parses. When parsing into `LocalDate`, the formatter must **resolve the date fields into a concrete date**.

With `ResolverStyle.STRICT`:

- `uuuu-MM-dd` has the `YEAR` field + month + day: sufficient to construct a `LocalDate` and validate it.
- `yyyy-MM-dd` has `YEAR_OF_ERA` + month + day but **no ERA**: typically insufficient for a concrete date under the strict resolver.
- `YYYY-MM-dd` has `WEEK_BASED_YEAR` + month + day but **no week-of-year/day-of-week**: the fields do not combine into a unique date in the way the strict resolver requires.

Patterns using `yyyy` often *seem to parse* under some default configurations because `DateTimeFormatter` defaults to `ResolverStyle.SMART`; Smart can assume an appropriate era to resolve year-of-era. **Do not interpret this as `y` and `u` being completely equivalent**.

### Runnable Java 17+ program

Create the file `StrictYearParseDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class StrictYearParseDemo {
    public static void main(String[] args) {
        String input = "2024-02-29";

        for (String pattern : new String[] {
                "yyyy-MM-dd",
                "uuuu-MM-dd",
                "YYYY-MM-dd"
        }) {
            DateTimeFormatter formatter =
                    DateTimeFormatter.ofPattern(
                            pattern, Locale.UK)
                            .withResolverStyle(ResolverStyle.STRICT);

            try {
                LocalDate date = LocalDate.parse(input, formatter);
                System.out.println(pattern + " -> " + date);
            } catch (DateTimeParseException exception) {
                System.out.println(
                        pattern + " -> DateTimeParseException");
            }
        }
    }
}
```

Run:

```bash
javac StrictYearParseDemo.java
java StrictYearParseDemo
```

Output:

```text
yyyy-MM-dd -> DateTimeParseException
uuuu-MM-dd -> 2024-02-29
YYYY-MM-dd -> DateTimeParseException
```

Key point: the failure of `yyyy` here is not because February 29, 2024 is invalid. That date really exists in the ISO calendar. With `yyyy`, the parser has **YEAR_OF_ERA but lacks ERA** when using strict resolution.

Nor should `YYYY-MM-dd` be treated as a workaround when `yyyy-MM-dd` fails. `Y` is the week-based year and cannot be arbitrarily combined with `M`/`d` and expected to resolve into a normal calendar date.

### Parsing year-of-era properly with an explicit era

If the data actually contains an era, you can use:

```text
G yyyy-MM-dd
```

For example:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern(
                "G yyyy-MM-dd", Locale.US)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate firstBce =
        LocalDate.parse("BC 0001-01-01", formatter);
// firstBce = 0000-01-01 in proleptic ISO
```

This is an **illustrative Java snippet** with imports `LocalDate`, `DateTimeFormatter`, `ResolverStyle`, and `Locale`; the complete examples above can compile standalone. When using other locales, the representation of `AD`/`BC` can be localized; keep the formatter locale and input data consistent.

### STRICT differs from the year pattern letter

`ResolverStyle.STRICT` also checks valid day-of-month/year combinations, such as rejecting February 31 or February 29 of a non-leap year. `u`/`y`/`Y` determines the *type of year field*, while the resolver style determines *how fields are validated and combined*.

For an application requiring exact ISO dates, a clear example is:

```java
DateTimeFormatter isoStrict =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

Or use the built-in formatter `DateTimeFormatter.ISO_LOCAL_DATE` when the interface contract requires ISO 8601 dates. Do not add `Y` to a date format just because it mentions "year".

## 8. Parsing Week-Based Years Properly: Combining Y with w and e

If the data is genuinely organized by **week**, a pattern combining `Y`, `w`, and `e` makes sense:

```text
YYYY-'W'ww-e
```

Where:

- `YYYY`: week-based year (localized week-based-year).
- `ww`: week within that week-based year.
- `e`: day of week according to the locale's week start.

For example, the date 2021-01-01 can be represented as:

```text
UK: 2020-W53-5
US: 2021-W01-6
```

And these strings can be parsed back into the same ISO date using their corresponding locales:

```java
DateTimeFormatter uk =
        DateTimeFormatter.ofPattern(
                "YYYY-'W'ww-e", Locale.UK)
                .withResolverStyle(ResolverStyle.STRICT);

DateTimeFormatter us =
        DateTimeFormatter.ofPattern(
                "YYYY-'W'ww-e", Locale.US)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate ukDate = LocalDate.parse("2020-W53-5", uk);
LocalDate usDate = LocalDate.parse("2021-W01-6", us);
// Both are 2021-01-01
```

This is an **illustrative snippet**, meant for use inside a class with appropriate imports. It interprets a single date using two week systems, not two different dates.

**Warning:** when weekly data is stored for exchange between systems, the **WeekFields** (first day of week and minimum days in the first week) must be explicitly specified in the protocol. Storing only `2021-W01` without knowing whether US or ISO rules apply can skew reports.

## 9. Want ISO Week-Year Regardless of Locale: Use WeekFields.ISO

`Y` is a localized week-based-year, so if the requirement is **ISO week numbering**, you should not rely on the default locale.

`java.time.temporal.WeekFields.ISO` specifies:

- Monday is the first day of the week.
- The first week must have at least 4 days in the new year.

You can retrieve the ISO fields explicitly:

```java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.time.temporal.IsoFields;

LocalDate date = LocalDate.of(2021, 1, 1);

int isoWeekYear = date.get(
        IsoFields.WEEK_BASED_YEAR);
int isoWeek = date.get(
        IsoFields.WEEK_OF_WEEK_BASED_YEAR);
int isoDayOfWeek = date.getDayOfWeek().getValue();

// isoWeekYear = 2020
// isoWeek     = 53
// isoDayOfWeek = 5
```

This is an illustrative code snippet (the import lines and declarations can be placed in a full program). `IsoFields` is the direct API for ISO week numbers. `WeekFields.ISO.weekBasedYear()` and `WeekFields.ISO.weekOfWeekBasedYear()` are also explicit options, especially when a project prefers structuring code around `WeekFields`.

For user-visible input, the locale can determine month names and display formatting. However, **week rules used for computation/data aggregation** must be an explicit business choice and should not unconsciously change with the UI language.

## 10. Do Not Confuse DateTimeFormatter with SimpleDateFormat

In Java there are **two common date-formatting API systems**:

1. `java.time.format.DateTimeFormatter` (modern API since Java 8).
2. `java.text.SimpleDateFormat` (legacy API, mutable and not thread-safe).

**The same letter can have different meanings between the two APIs.** In particular:

| Pattern | `DateTimeFormatter` | `SimpleDateFormat` |
|---|---|---|
| `u` | Proleptic year | **Day number of week** with Monday = 1, Sunday = 7 |
| `y` | Year-of-era | Year according to the `Calendar` model |
| `Y` | Localized week-based-year | Week year according to `Calendar` and week settings |
| `d` | Day-of-month | Day-of-month |
| `M` | Month-of-year | Month |

Therefore, **you cannot migrate the `uuuu-MM-dd` pattern from DateTimeFormatter to SimpleDateFormat and expect the same meaning**: `u` in `SimpleDateFormat` is not a year. In projects migrating from `Date`/`Calendar` to `java.time`, every pattern must be reviewed rather than performing blind string search-and-replace.

For example, with 2021-01-01 being a Friday:

```text
DateTimeFormatter: uuuu = 2021
SimpleDateFormat: u = 5  (Friday)
```

With `SimpleDateFormat`, `Y` can be week-year and `y` is calendar year according to `Calendar`. This still causes the `YYYY` bug in date reports, but **do not project java.time's strict parsing or proleptic-year mechanics onto the legacy API**.

New programs should prefer `java.time` unless constrained by compatibility APIs. `DateTimeFormatter` is immutable and thread-safe; `SimpleDateFormat` is mutable and requires careful thread/concurrency management.

## 11. Letter Counts and Pattern Pitfalls

The repetition count of a letter in `DateTimeFormatter` affects formatting and parsing:

- `u` and `uuuu` both refer to the proleptic year field, but `uuuu` requires at least four digits in common usage.
- `y` and `yyyy` are both year-of-era, differing in padding/width.
- `Y` and `YYYY` are both localized week-based-year, differing in width.
- `yy`, `uu`, `YY` typically relate to reduced 2-digit years; they are not equivalent to four-digit patterns and require an explicit century-interpretation policy.

An easy mistake is assuming `YYYY` is capitalized to enforce four digits when lowercase `yyyy` is insufficient. In reality, **capitalization changes the field itself**, not just the formatting width.

Do not invent a convention like "always use YYYY for all years" in Java. When exchanging ISO dates with other systems, define the exact syntax and use the appropriate formatter.

### The "YYYY-MM-dd" pattern causes bugs even when formatting succeeds

`DateTimeFormatter.ofPattern("YYYY-MM-dd", Locale.UK)` can still **format** a `LocalDate` because the source object already contains every field. However, the output string mixes **week-year** with **calendar month/day**; when parsed back with the strict resolver, the data does not describe a valid date under that field combination. Even if another parse configuration "lets it pass", the meaning is still prone to error.

It is necessary to distinguish:

- **Format:** extracting fields from an already resolved date object.
- **Parse:** reconstructing a date object from fields in a string; the fields must combine into a consistent date.

Therefore, tests that merely check "the formatter returns a string" are insufficient; round-trip tests with realistic data (format then parse back to the exact same `LocalDate`) using the proper parser/resolver style are required.

## 12. Year-Boundary Testing Rules

Because differences among `u`/`y`/`Y` mostly surface in rare edge cases, maintain a fixed test suite:

| Case | Why It Matters |
|---|---|
| December 27–31 | Can belong to the next week-based year in some locales |
| January 1–4 | Can belong to the previous week-based year in ISO/UK |
| Years with week 53 | Tests the final week and early days of the following year |
| Leap years, e.g. `2024-02-29` | Checks calendar year and strict parsing |
| Year 0 / negative years if domain-supported | Distinguishes `u` and `y` |
| US versus UK/ISO | Proves `Y` depends on week rules |
| Format–parse round-trip | Detects patterns with missing fields or mixed models |
| Migrating SimpleDateFormat to DateTimeFormatter | Detects `u` changing meaning |

A worthwhile test is: every start-of-year and end-of-year date must be formatted with `uuuu-MM-dd` and then parsed back with the strict resolver to equal the exact original date. If reporting by ISO week, test `IsoFields.WEEK_BASED_YEAR` and `IsoFields.WEEK_OF_WEEK_BASED_YEAR` separately, rather than arbitrarily assigning the year from `LocalDate.getYear()` to a week.

## 13. Common Mistakes and How to Avoid Them

**Mistake 1 — Using `YYYY-MM-dd` for calendar dates.** Week-based year can differ from calendar year. Use `uuuu-MM-dd` when an ISO date is intended.

**Mistake 2 — Assuming `yyyy` always equals `uuuu`.** In modern AD dates they usually yield the same number, but the year models differ; before AD, `yyyy` needs era information.

**Mistake 3 — Parsing `yyyy-MM-dd` with STRICT and thinking a valid date failed because of a Java bug.** `YEAR_OF_ERA` may fail to resolve without `ERA`; use `uuuu` for ISO proleptic dates or add `G` when the model is year-of-era.

**Mistake 4 — Assuming `YYYY` is the ISO week-year in every Locale.** `DateTimeFormatter` uses localized week rules; for explicit ISO, use `WeekFields.ISO` or `IsoFields`.

**Mistake 5 — Using `YYYY` with month and day.** That mixes the week model with the calendar model; if weeks are wanted, use `Y` + `w` + the appropriate day-of-week field.

**Mistake 6 — Seeing 01/01 with a week-year from the previous year and "fixing" the data.** That may be the correct behavior of ISO week-year. Check the business rules before modifying anything.

**Mistake 7 — Copying `uuuu` into `SimpleDateFormat`.** `u` in SimpleDateFormat is the day number of week; re-verify patterns when switching APIs.

**Mistake 8 — Forgetting Locale when using `Y`/`w`/`e`.** The same date can receive different week labels if the locale changes.

**Mistake 9 — Testing only mid-year dates.** June rarely exposes `Y` bugs; always test late December and early January.

**Mistake 10 — Using weekly data to index calendar-year reports without clarifying rules.** The last and first weeks of the year can cross year boundaries; explicitly define whether "year" means calendar year or week-based-year.

## 14. Self-Check Q&A

**Q1.** What kind of year does the `uuuu-MM-dd` pattern use?  
**Answer:** Proleptic year; in the ISO calendar it includes year 0 and negative years.

**Q2.** How does `yyyy-MM-dd` differ from `uuuu-MM-dd`?  
**Answer:** `yyyy` is year-of-era, whereas `uuuu` is proleptic year. With a strict parser, `yyyy` may additionally require an era (`G`).

**Q3.** Why can 2021-01-01 display as `2020-W53`?  
**Answer:** Under ISO week rules, that date falls in week 53 of week-based year 2020.

**Q4.** Is `YYYY` always identical between `Locale.US` and `Locale.UK`?  
**Answer:** No. The locale defines the first day of the week and the minimum days in the first week.

**Q5.** To print a standard calendar date `2021-01-01`, should you use `YYYY-MM-dd`?  
**Answer:** No. Use `uuuu-MM-dd` or `DateTimeFormatter.ISO_LOCAL_DATE`.

**Q6.** Is `u` in `SimpleDateFormat` the proleptic year?  
**Answer:** No. In the legacy API, `u` is the day number of week, where 1 is Monday.

**Q7.** What year-of-era corresponds to year 0 of `LocalDate`?  
**Answer:** Era BC, year-of-era 1.

**Q8.** When wanting ISO week reports while the UI can change language, what should you use?  
**Answer:** `IsoFields` or `WeekFields.ISO` for calculations, avoiding reliance on the default locale.

## 15. Takeaways and References

**`u` = continuous proleptic year, `y` = year-of-era, `Y` = localized week-based year.** For ordinary calendar dates and strict parsing, `uuuu-MM-dd` is the clear choice; if historical eras must be displayed, use `G` with `y`; if reporting by week, combine `Y` with `w` and `e` according to the chosen week rules.

Do not treat `YYYY` as merely an uppercase spelling of `yyyy`: this difference can corrupt data on the most critical days of annual reporting.

**References:** [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) · [Java SE 17 — WeekFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html) · [Java SE 17 — IsoFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/IsoFields.html) · [Java SE 17 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html).
