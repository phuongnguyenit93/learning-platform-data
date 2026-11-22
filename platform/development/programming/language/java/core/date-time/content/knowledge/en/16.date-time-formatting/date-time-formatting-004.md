# Distinguishing uuuu, yyyy, and YYYY in DateTimeFormatter

## Objectives

In Java date-time format patterns, the letters `u`, `y`, and `Y` are not synonymous:

- `u` is the **proleptic ISO calendar year** (proleptic year), which includes year 0 and negative years.
- `y` is the **year-of-era**, commonly seen as a positive year in the CE/AD era.
- `Y` is the **week-based-year**, tied to the week of the year and the locale's week rules.

For most mid-year dates, `uuuu` and `yyyy` look the same. However, near the beginning or end of a year, `YYYY` may display a completely different year from the calendar year. Choosing the wrong pattern can cause reports, file names, invoices, or date keys to be stamped with the wrong year.

## 1. Three symbols, three meanings

| Pattern | Meaning | Used for |
|---|---|---|
| `uuuu` | Proleptic calendar year, which can be 0 or negative | Standard ISO dates; data requiring an unambiguous calendar year |
| `yyyy` | Year within the current era | Calendar dates tied to an era; when representing eras before/after CE, pair with `G` |
| `YYYY` | Week-based-year | Week codes such as `2020-W01`, weekly reports, calendars following week rules |
| `ww` | Week number of the week-based-year | Paired with `YYYY` when representing weeks |
| `G` | Era, e.g., AD/BC in an appropriate locale | Distinguishing CE and BCE years when using `yyyy` |

Patterns are case-sensitive. `yyyy` and `YYYY` are two different date fields; changing lowercase to uppercase changes the meaning of the data.

For the ISO calendar used by `LocalDate`, the calendar year of `2019-12-30` is 2019. However, this date is the Monday of ISO week 1 belonging to **week-based-year 2020**. Therefore, `uuuu`/`yyyy` may print 2019 while `YYYY` prints 2020.

## 2. uuuu: proleptic calendar year

`u` represents the proleptic calendar year, meaning the calendar rules are extended backward and forward across the era boundary. For ordinary CE dates, `uuuu` displays the familiar calendar year:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalDate date = LocalDate.of(2024, 6, 15);
DateTimeFormatter calendarYear =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);

System.out.println(calendarYear.format(date));
```

Output:

```text
2024-06-15
```

`uuuu` is particularly useful when you need to format/parse ISO dates unambiguously. Unlike year-of-era, proleptic year represents year 0 and negative years. In the proleptic Gregorian system used by Java, year 0 corresponds to 1 BCE; negative values represent subsequent earlier BCE years following the arithmetic convention of the calendar system.

Most business applications only work with modern positive dates, so `uuuu` and `yyyy` usually produce the same string. However, they are not equivalent in data model across the entire supported date range.

## 3. yyyy: year-of-era

`y` is the year-of-era. The year count resets when switching eras, so `yyyy` alone is not enough to distinguish two dates in different eras if the application handles historical or BCE/CE dates.

When an era is needed, pair it with `G`:

```java
DateTimeFormatter eraDate =
        DateTimeFormatter.ofPattern("G yyyy-MM-dd", Locale.US);
```

This pattern represents the era together with the year-of-era. Era names are localized by locale, for example commonly `AD` or `BC` in English locales; the exact formatting depends on locale/JDK data. Do not treat the era text as a fixed string constant across all languages.

For an ordinary CE date, `yyyy-MM-dd` usually prints the same year number as `uuuu-MM-dd`:

```java
LocalDate date = LocalDate.of(2024, 6, 15);
DateTimeFormatter yearOfEra =
        DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ROOT);
System.out.println(yearOfEra.format(date));
```

Output:

```text
2024-06-15
```

When the goal is an ISO date string without an era and you want to represent the calendar year directly, prefer `uuuu-MM-dd`. When the goal requires an era-based year, use `yyyy` together with `G` and define the corresponding parsing behavior.

## 4. YYYY: week-based-year, not a regular year

`Y` represents the year tied to weeks. It must be interpreted together with week fields such as `w` (week of week-based-year) and the rules defining weeks. A week-based-year can start before January 1 or extend into the first few days of the next calendar year.

Two main factors affect the week-based-year:

1. Which day is considered the first day of the week (e.g., Monday in ISO).
2. The minimum number of days in the first week that must fall in the new year (ISO requires at least four days).

In ISO week dates, the week starts on Monday; week 1 is the week with at least four days in the new year. Because of this, some days at the end of December already belong to the next week-based-year, and some days at the beginning of January still belong to the previous week-based-year.

`YYYY` **should not be used as an uppercase substitute for `yyyy`** in regular date patterns. Using it with `MM-dd` creates a string that mixes year-from-week with calendar month/day, which can produce a contradictory date display like `2020-12-30` when the actual input is `2019-12-30`.

## 5. Clear example at a year boundary

Create `YearPatternDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class YearPatternDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2019, 12, 30);

        DateTimeFormatter calendarU =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.UK);
        DateTimeFormatter calendarY =
                DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.UK);
        DateTimeFormatter weekYear =
                DateTimeFormatter.ofPattern("YYYY-'W'ww-e", Locale.UK);
        DateTimeFormatter mixed =
                DateTimeFormatter.ofPattern("YYYY-MM-dd", Locale.UK);

        System.out.println("Input:        " + date);
        System.out.println("uuuu-MM-dd:   " + calendarU.format(date));
        System.out.println("yyyy-MM-dd:   " + calendarY.format(date));
        System.out.println("Week pattern: " + weekYear.format(date));
        System.out.println("Mixed pattern:" + mixed.format(date));
    }
}
```

Compile and run with Java 17+:

```bash
javac YearPatternDemo.java
java YearPatternDemo
```

Output with `Locale.UK` (ISO week rules):

```text
Input:        2019-12-30
uuuu-MM-dd:   2019-12-30
yyyy-MM-dd:   2019-12-30
Week pattern: 2020-W01-1
Mixed pattern:2020-12-30
```

The `Week pattern` line is a valid week representation: the date belongs to week 1 of week-based-year 2020, and Monday is numbered 1 in this locale. The `Mixed pattern` line is intentionally created to illustrate the bug: `YYYY` takes week-based-year 2020, while `MM-dd` keeps the month/day of the input calendar date. The string `2020-12-30` **is no longer an accurate reformatting of the original date**; it mixes fields from two different reference systems.

To avoid output depending on the machine's default locale, the example explicitly specifies `Locale.UK`. In real applications, if you want ISO weeks, use an explicitly specified locale or ISO rules. Do not rely on the default locale, as the locale can change the rules for the first day of the week and the first week of the year.

## 6. Why does YYYY change by locale?

`YYYY` uses the week-based-year according to the formatter's week rules. For ISO-style locales (such as `Locale.UK`), the rules typically correspond to a week starting on Monday with at least four days in week 1 falling in the new year. Other locales may use a different week start day and minimum days rule, causing week/year boundaries to differ.

Overview example for the same calendar date:

| Meaning | Field to format |
|---|---|
| Calendar year of the date | `uuuu` or `yyyy` |
| Week-based-year according to locale rules | `YYYY` |
| Week number within week-based-year | `ww` |
| Localized day-of-week number | `e` |
| Fixed ISO day-of-week number | `c` depends on usage/pattern; for ISO applications, choose a consistent rule set |

If you need ISO results regardless of the application-wide locale, consider using `WeekFields.ISO` to extract `weekBasedYear()`, `weekOfWeekBasedYear()`, and `dayOfWeek()`, or using `DateTimeFormatter` with an explicit ISO locale/rules. The key is that the week-based-year, week number, and day-of-week fields must use **the same week rules**.

## 7. Correct patterns for common formats

| Intent | Recommended pattern | Notes |
|---|---|---|
| ISO date by calendar year | `uuuu-MM-dd` | Unambiguous choice for calendar dates |
| Calendar date with era | `G yyyy-MM-dd` | Era needed to distinguish BCE/CE |
| ISO week, e.g., week 1 of 2020 | `YYYY-'W'ww-e` with explicit ISO locale/rules | Use week-based fields consistently |
| ISO instant/time with offset | `uuuu-MM-dd'T'HH:mm:ssXXX` | If parsing/formatting offset, use an appropriate temporal type |
| Monthly file/report key | `uuuu-MM` | Avoid `YYYY-MM` unless intentionally using week-based-year, which is usually inappropriate for months |

Do not use `YYYY-MM-dd` for regular date file names, daily reports, databases, or invoice labels just because it "looks like yyyy-MM-dd". At year boundaries, the generated string can have the wrong year.

## 8. Parsing and ResolverStyle

Patterns do not only affect output; when parsing strings into dates, the year fields also determine the meaning. If a pattern contains `YYYY` alongside calendar month/day, the formatter may not provide a suitable combination of fields to construct a `LocalDate` as expected.

- Use `uuuu-MM-dd` to read/write ISO dates by calendar year.
- Use a week field set like `YYYY-'W'ww-e` for week date data, with consistent locale/rules.
- When accepting untrusted input, explicitly specify `ResolverStyle.STRICT`, `SMART`, or `LENIENT` depending on the parsing contract. `DateTimeFormatter` defaults to `SMART` resolver style, but the right pattern and data contract remain essential.

Example of a strict formatter for parsing by calendar year:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter strictCalendarDate = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed = LocalDate.parse("2024-02-29", strictCalendarDate);
```

This is an illustrative snippet used inside a method; it requires imports and a program entry point such as `main` to run standalone. For calendar years, `uuuu` avoids year-of-era ambiguity when using the strict resolver. If `yyyy` is used without providing an era in a strict parsing context, the formatter may fail to resolve the date due to missing era information.

## 9. Testing year boundaries

Do not test only mid-year dates. Test suites for formatters should include boundary dates such as December 28–31 and January 1–4, especially when week-based logic is involved. Tests must fix the locale/week rules and assert exact expectations.

Points to verify:

- Mid-year dates have the same calendar year between `uuuu` and `yyyy` patterns in CE.
- December 30, 2019 in ISO belongs to `2020-W01`.
- Calendar patterns do not use `YYYY` when the intended meaning is the calendar year.
- Week patterns consistently use `YYYY`, `ww`, and a day-of-week field.
- Strict parsing is tested with leap years and invalid strings like `2023-02-29`.
- Tests do not depend on the default locale or time zone of the runtime environment.

## 10. Common mistakes

1. **Using uppercase `Y` for a regular year.** `YYYY` is the week-based-year, not the calendar year.
2. **Mixing week-based-year with calendar month/day.** `YYYY-MM-dd` can produce strings that do not accurately represent the input date at year boundaries.
3. **Assuming uuuu and yyyy are always identical.** They match for most ordinary CE dates, but differ in meaning across the pre/post-era year range.
4. **Using yyyy without G when BCE/CE handling is needed.** Year-of-era does not distinguish the two eras on its own.
5. **Letting the default locale determine the first week of the year.** Week-based-year boundaries can vary by locale rules; set the locale explicitly or use ISO rules.
6. **Using a week-based pattern to parse calendar dates.** Week codes must have corresponding week and day-of-week fields; use `uuuu-MM-dd` for calendar dates.
7. **Testing only mid-year dates.** `YYYY` discrepancies often only surface at the end of December or beginning of January.
8. **Using formatted strings as canonical date keys without defining the pattern.** Clearly specify whether the data represents a calendar date, week date, or instant.

## 11. Self-check

**Q1.** To format the calendar date 2019-12-30, which pattern should be used between `uuuu-MM-dd` and `YYYY-MM-dd`?

**Answer:** `uuuu-MM-dd`. It represents the calendar year 2019. `YYYY-MM-dd` can produce `2020-12-30` because the week-based-year has already rolled over to 2020.

**Q2.** In `YYYY-'W'ww-e`, what do the fields represent?

**Answer:** The week-based-year, the week number within the week-based-year, and the day of the week according to the chosen locale's rules.

**Q3.** When you need to distinguish BCE/CE years in formatting, should you just write `yyyy-MM-dd`?

**Answer:** No. Year-of-era resets per era; use `G yyyy-MM-dd` if era information is needed.

**Q4.** Why should the formatter example specify `Locale.UK`?

**Answer:** To fix the week rules for the example and avoid depending on the machine's default locale.

**Q5.** How is `uuuu` helpful when using `ResolverStyle.STRICT` to parse calendar dates?

**Answer:** It represents the proleptic year directly, avoiding the need to resolve year-of-era when the pattern lacks an era and keeping the calendar date parsing model clear.

---

**Takeaway:** Use `uuuu` for calendar years, `yyyy` for year-of-era, and `YYYY` only when genuinely formatting week-based-years. If a pattern contains `YYYY`, pair it with week number and day-of-week; never accidentally mix it with calendar month/day.