# Distinguishing `MM` vs `mm`, `dd` vs `DD` in Java

In `DateTimeFormatter`, date-time pattern letters are **case-sensitive**. Simply changing the letter case can produce wrong data without causing a syntax error: `MM` is **month**, `mm` is **minute**; `dd` is **day of month**, whereas `DD` is **day of year**.

For example, with date `2025-02-03` and time `16:07:09`:

| Pattern | Meaning | Result |
| --- | --- | --- |
| `MM/dd/yyyy` | Month / day of month / year | `02/03/2025` |
| `HH:mm:ss` | Hour / minute / second | `16:07:09` |
| `dd / DD` for 2025-02-03 | Day of month / day of year | `03 / 34` |
| `M / MM` | Month without leading zero / zero-padded | `2 / 02` |
| `m / mm` | Minute without leading zero / zero-padded | `7 / 07` |

Therefore, a familiar-looking pattern like `yyyy-mm-dd` is wrong if the goal is a year-month-day calendar date: the `mm` field will be the minute, not the month. Use `yyyy-MM-dd` for a calendar date, or prefer `DateTimeFormatter.ISO_LOCAL_DATE` when the contract requires an ISO date `uuuu-MM-dd`.

## 1. Four Symbols to Distinguish

### `M` and `MM` — Month

- `M`: month number without requiring a leading zero; for example, February prints as `2`.
- `MM`: month with a two-digit width; for example, February prints as `02`.
- `MMM`: abbreviated month name according to the locale; for example, in English this is usually `Feb`.
- `MMMM`: full month name according to the locale; for example, in English `February`.

Uppercase `M` symbols refer to the **month of the year**. When parsing, `MM` is the numeric month value, not the minute.

### `m` and `mm` — Minute

- `m`: minute without a leading zero; for example, minute 7 prints as `7`.
- `mm`: minute with a leading zero; for example, minute 7 prints as `07`.

Lowercase `m` is minute, unlike uppercase `M` which is month. A time like 16:07 must not format the minute using `MM`; the correct pattern for hour/minute is usually `HH:mm` or `H:mm` depending on the desired display format.

### `d` and `dd` — Day of Month

- `d`: day of month without a leading zero; for example, day 3 prints as `3`.
- `dd`: day of month with a leading zero; for example, day 3 prints as `03`.

Lowercase `d` represents the day of the month, typically in the range 1–28/29/30/31 depending on the month and year. This is the appropriate field when displaying a standard calendar date.

### `D` and `DD` — Day of Year

- `D`: day of year without a leading zero; for example, the 34th day prints as `34`.
- `DD`: day of year padded to at least two digits; the 34th day is still `34`, while the 3rd day is `03`.
- `DDD`: three-digit width, commonly used to represent the day of the year from `001` to `365` or `366`.

Uppercase `D` is **not the day of the month**. It is the ordinal day count from the start of the year: January 1 is `1`, and February 3, 2025 is the `34`th day.

## 2. Why Do `dd` and `DD` Produce Different Results?

The date 2025-02-03 (February 3) can be represented in two ways:

```java
LocalDate date = LocalDate.of(2025, 2, 3);

DateTimeFormatter dayInMonth =
        DateTimeFormatter.ofPattern("dd", Locale.ROOT);
DateTimeFormatter dayInYear =
        DateTimeFormatter.ofPattern("DD", Locale.ROOT);

System.out.println(date.format(dayInMonth)); // 03
System.out.println(date.format(dayInYear));  // 34
```

This snippet requires `import java.time.*;`, `import java.time.format.DateTimeFormatter;`, and `import java.util.Locale;`. Both formatters take the same `LocalDate` but request two different fields: day of month and day of year.

The day of year varies depending on leap years. For example:

| Date | `dd` — day of month | `DDD` — day of year |
| --- | ---: | ---: |
| 2025-01-01 | 01 | 001 |
| 2025-02-03 | 03 | 034 |
| 2024-02-29 | 29 | 060 |
| 2025-12-31 | 31 | 365 |
| 2024-12-31 | 31 | 366 |

The year 2024 is a leap year so it has 366 days, whereas 2025 has 365 days. When **formatting a calendar date**, almost always use `dd` for the day of month; do not use `DD` unless the business requirement genuinely calls for the day of the year (for example, a report keyed by day `034`).

## 3. Complete Java 17+ Example: Observing the Difference Directly

Save the following program with the exact filename **`DateTimePatternCaseDemo.java`**:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DateTimePatternCaseDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 2, 3);
        LocalTime time = LocalTime.of(16, 7, 9);
        LocalDateTime dateTime = LocalDateTime.of(date, time);

        System.out.println("MM/dd/yyyy       : "
                + date.format(DateTimeFormatter.ofPattern(
                        "MM/dd/yyyy", Locale.ROOT)));
        System.out.println("HH:mm:ss         : "
                + time.format(DateTimeFormatter.ofPattern(
                        "HH:mm:ss", Locale.ROOT)));
        System.out.println("Combined         : "
                + dateTime.format(DateTimeFormatter.ofPattern(
                        "yyyy-MM-dd HH:mm:ss", Locale.ROOT)));
        System.out.println("dd / DD          : "
                + date.format(DateTimeFormatter.ofPattern(
                        "dd / DD", Locale.ROOT)));
        System.out.println("M / MM           : "
                + date.format(DateTimeFormatter.ofPattern(
                        "M / MM", Locale.ROOT)));
        System.out.println("m / mm           : "
                + time.format(DateTimeFormatter.ofPattern(
                        "m / mm", Locale.ROOT)));
        System.out.println("Day-of-year parse: "
                + LocalDate.parse("2025-034",
                        DateTimeFormatter.ofPattern(
                                "yyyy-DDD", Locale.ROOT)));
        System.out.println("ISO safe pattern : "
                + dateTime.format(
                        DateTimeFormatter.ISO_LOCAL_DATE_TIME));

        DateTimeFormatter localized =
                DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US);
        System.out.println("Locale text      : "
                + date.format(localized));
        System.out.println("Month/day/year   : "
                + date.format(DateTimeFormatter.ofPattern(
                        "MM/dd/yyyy", Locale.US)));
        System.out.println("Day/month/year   : "
                + date.format(DateTimeFormatter.ofPattern(
                        "dd/MM/yyyy", Locale.US)));
        System.out.println("Week-based year  : "
                + date.format(DateTimeFormatter.ofPattern(
                        "YYYY-'W'ww-e", Locale.US)));
        System.out.println("Calendar year    : "
                + date.format(DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd", Locale.ROOT)));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac DateTimePatternCaseDemo.java
java DateTimePatternCaseDemo
```

Verified output from compiling and running the program:

```text
MM/dd/yyyy       : 02/03/2025
HH:mm:ss         : 16:07:09
Combined         : 2025-02-03 16:07:09
dd / DD          : 03 / 34
M / MM           : 2 / 02
m / mm           : 7 / 07
Day-of-year parse: 2025-02-03
ISO safe pattern : 2025-02-03T16:07:09
Locale text      : 3 February 2025
Month/day/year   : 02/03/2025
Day/month/year   : 03/02/2025
Week-based year  : 2025-W06-2
Calendar year    : 2025-02-03
```

Key lines to note:

- `MM/dd/yyyy` prints `02/03/2025`, meaning month 2, day 3, year 2025.
- `HH:mm:ss` prints `16:07:09`. Here lowercase `mm` keeps minute 07.
- `dd / DD` prints `03 / 34`. The day of month is 3; the 34th day of the year is a different value.
- `M / MM` shows the zero-padding difference: `2` and `02`.
- `m / mm` shows minute 7 printed as `7` and `07` respectively.
- `ISO_LOCAL_DATE_TIME` produces an ISO string like `2025-02-03T16:07:09` without needing to hand-pick a pattern.

## 4. Correct Format Patterns for Common Needs

| Goal | Example pattern | Result for 2025-02-03 at 16:07:09 |
| --- | --- | --- |
| ISO date | `uuuu-MM-dd` | `2025-02-03` |
| Day/month/year | `dd/MM/uuuu` | `03/02/2025` |
| Month/day/year | `MM/dd/uuuu` | `02/03/2025` |
| 24-hour and minute | `HH:mm` | `16:07` |
| Hour, minute, second | `HH:mm:ss` | `16:07:09` |
| Human-readable date & time | `dd/MM/uuuu HH:mm:ss` | `03/02/2025 16:07:09` |
| Day of year | `DDD` | `034` |
| Full month name | `d MMMM uuuu` with `Locale.US` | `3 February 2025` |

For machine-readable data or API contracts, prefer a standardized format such as `DateTimeFormatter.ISO_LOCAL_DATE`, `ISO_LOCAL_TIME`, or `ISO_LOCAL_DATE_TIME` when it matches the data type. Patterns like `dd/MM/uuuu` are useful for user interfaces, but should be explicitly specified to avoid confusion when data crosses regions with different date conventions.

**Note:** day/month/year and month/day/year patterns can be ambiguous when both components are between 1 and 12. For example, the string `03/02/2025` can be read as February 3 or March 2 depending on convention. Agree on the format contract between sender and receiver rather than relying on the machine's default locale.

## 5. Be Careful with `yyyy`, `uuuu`, and `YYYY`

Although the main focus is `MM/mm` and `dd/DD`, pattern letter casing also has other easily confused fields:

- `yyyy`: year-of-era.
- `uuuu`: ISO calendar proleptic year. This is usually the clear choice for ISO calendar formatting, especially when you want consistent interpretation outside the Common Era.
- `YYYY`: **week-based year**; not synonymous with `yyyy` or `uuuu`.
- `ww`: week number according to the week-based system and the corresponding locale/temporal field.
- `e`/`E`: day-of-week symbols, whose numeric/text display differs depending on the symbol and locale.

Because the week-based year can roll over to the next year before January 1 or still belong to the previous year in late December, `YYYY-MM-dd` is not a pattern to use for normal dates. For instance, dates near the start or end of a year may be formatted with a week-based year that differs from the calendar year.

For standard ISO dates, use `uuuu-MM-dd`; for example, `2025-02-03`. Use `YYYY` only when the business logic genuinely requires a **week-based year** field, typically paired with a well-defined week pattern.

## 6. Analyze Patterns Token by Token, Do Not Guess by Appearance

When reading `DateTimeFormatter.ofPattern(pattern, locale)`, do not look at the pattern string as plain text and guess its meaning. Each symbol corresponds to a specific field:

| Symbol | Field | Hint |
| --- | --- | --- |
| `M`, `MM` | Month of year | Uppercase M. |
| `m`, `mm` | Minute of hour | Lowercase m. |
| `d`, `dd` | Day of month | Lowercase d; commonly used for everyday calendar dates. |
| `D`, `DD`, `DDD` | Day of year | Uppercase D; values 1–365/366. |
| `H`, `HH` | Hour of day (0–23) | Uppercase H indicates the 24-hour clock. |
| `h`, `hh` | Clock-hour of am/pm (1–12) | Usually combined with an AM/PM marker. |
| `s`, `ss` | Second of minute | Lowercase s, not milliseconds. |
| `S`, `SSS` | Fraction of second by symbol width | Uppercase S, not seconds of minute. |
| `a` | AM/PM marker | Meaning depends on locale and hour type. |
| `z` / `VV` | Zone information by respective pattern type | Do not confuse with a fixed offset or local type name. |
| `X` / `x` | Offset representations | Output varies by the number of pattern letters. |

This table is a quick orientation, not a substitute for the full pattern specification; when using special symbols, choose an explicit pattern, verify with examples, and pass an explicit locale.

### Common Mistake: `yyyy-mm-dd`

With `LocalDateTime`, `yyyy-mm-dd` mixes year, **minute**, and day of month. For example, formatting `2025-02-03` with this pattern can output `2025-07-03` if the formatter is applied to a date-time whose minute is 7, because `mm` is the minute. Printing a string that looks like a date does not prove the month field is right.

The correct patterns are:

```java
DateTimeFormatter safeDate =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);
DateTimeFormatter safeDateTime =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm:ss", Locale.ROOT);
```

This code requires `import java.time.format.DateTimeFormatter;` and `import java.util.Locale;`. Using `MM` for month and `mm` for minute is a rule to check whenever `M`/`m` appears in a pattern.

## 7. Use Locale Intentionally

Locale affects text names such as abbreviated/full months, day-of-week names, and the representation of certain text-based fields. When a formatter uses month names:

```java
LocalDate date = LocalDate.of(2025, 2, 3);
DateTimeFormatter us = DateTimeFormatter.ofPattern(
        "d MMMM uuuu", Locale.US);
DateTimeFormatter french = DateTimeFormatter.ofPattern(
        "d MMMM uuuu", Locale.FRANCE);

System.out.println(date.format(us));
System.out.println(date.format(french));
```

This Java example requires `import java.time.*;`, `import java.time.format.DateTimeFormatter;`, and `import java.util.Locale;`. Text names depend on the chosen locale. For numeric-only values, locale generally does not change the rule that `MM` is month and `mm` is minute, though locale still matters when using text symbols or week rules such as `YYYY`.

Locale does not automatically fix a broken pattern: `yyyy-mm-dd` is still year-minute-day regardless of whether the locale is Vietnam or the United States. Check symbol meanings and display locale separately.

## 8. String Parsing Uses the Same Case Sensitivity

`DateTimeFormatter` works for both **formatting** (object to string) and **parsing** (string to object). Letter case determines which field is read when parsing, not just how it is displayed.

For example, parsing the 34th day of 2025:

```java
DateTimeFormatter ordinalDate = DateTimeFormatter.ofPattern(
        "uuuu-DDD", Locale.ROOT);
LocalDate parsed = LocalDate.parse("2025-034", ordinalDate);
// parsed = 2025-02-03
```

Here `DDD` is right because the input is day-of-year. If the input string is year-month-day, use `uuuu-MM-dd` instead. Do not swap patterns arbitrarily during parsing; inputs `"2025-034"` and `"2025-02-03"` have different structures.

User-entered date strings should be checked for parse errors and converted into appropriate messages. Do not try to fix data by replacing all `M` with `m` or vice versa, as that can change the meaning of other patterns.

## 9. Choosing Safe Fixed Formatters for APIs

- **UI formatting:** choose a pattern matching product conventions, such as `dd/MM/uuuu HH:mm`, and pass an explicit locale when displaying month names.
- **Machine-to-machine exchange:** prefer an ISO formatter when it fits the data type; do not generate a format dependent on the default locale and expect another system to guess correctly.
- **Absolute instants:** when the data is an `Instant` or a type with an offset/zone, preserve that information if the API contract requires a global timestamp. A pattern with only `uuuu-MM-dd HH:mm:ss` drops the offset and can make the output ambiguous.
- **Calendar dates:** `LocalDate` fits a date without a time; the pattern `uuuu-MM-dd` does not turn a date into a UTC instant.
- **Wall-clock times:** `LocalTime` uses patterns like `HH:mm:ss`; it does not add a date or time zone.
- **Testing patterns:** use a date and time with distinct values—such as month 2, day 3, minute 7. Do not test only when month and minute happen to have the same number, because an `MM/mm` bug can be masked.

`DateTimeFormatter` is immutable and thread-safe. Create a formatter once and reuse it if the application frequently formats or parses with the same pattern and locale.

## 10. Common Mistakes

1. **Writing `mm` instead of `MM` when you want the month.** The result uses minutes instead of months.
2. **Writing `DD` instead of `dd` when you want the day of the month.** The result becomes the day of the year.
3. **Using `yyyy-mm-dd` for a date.** The pattern mixes year, minute, and day; use `uuuu-MM-dd` or an appropriate ISO formatter.
4. **Using `YYYY` instead of `yyyy`/`uuuu`.** `YYYY` is the week-based year; dates near the start or end of the year can yield a different year.
5. **Testing only with numbers that happen to match.** Month 7 and minute 7 can hide the bug; test with month 2 and minute 7.
6. **Omitting an explicit locale when month/day names are needed.** Text output can vary across environments.
7. **Assuming locale will fix a pattern.** Locale does not change the meaning of `M`/`m` or `d`/`D`.
8. **Parsing a day-of-year string with a month/day pattern.** The format must match the actual structure of the input.
9. **Formatting a zoned timestamp into a string without an offset and treating it as a complete timestamp.** The displayed date-time remains ambiguous when sent across systems.
10. **Bulk-replacing letters in patterns via text operations.** This can break other valid symbols—for instance, `S`/`s` and `H`/`h` also have case-sensitive meanings.
11. **Not checking which fields the formatted data type holds.** Know whether the input is `LocalDate`, `LocalTime`, `LocalDateTime`, or a zoned type; not every type contains all fields.
12. **Confusing ordinal day-of-year with day-of-month.** `DDD` is useful for day-of-year data, but is not equivalent to `dd`.

## 11. Self-Check Exercises

**Question 1.** For the date `2025-02-03` and pattern `MM/dd/uuuu`, what is the result?

**Answer:** `02/03/2025`. `MM` is month 2, and `dd` is day 3.

**Question 2.** For the time `16:07:09`, how does the pattern `HH:mm:ss` format it?

**Answer:** `16:07:09`. `mm` is minute 07.

**Question 3.** For the date `2025-02-03`, why does `DD` produce `34`?

**Answer:** Because 2025-02-03 is the 34th day of 2025; `DD` is day-of-year, not day-of-month.

**Question 4.** What is wrong with the pattern `yyyy-mm-dd`?

**Answer:** The middle field is minute, because `mm` is lowercase. For a calendar date, use `uuuu-MM-dd` or an ISO formatter.

**Question 5.** Can `YYYY` and `uuuu` be used interchangeably for every date?

**Answer:** No. `YYYY` is the week-based year, whereas `uuuu` is the calendar proleptic year; dates near year boundaries can differ.

**Question 6.** What is the maximum day-of-year value a leap year can have?

**Answer:** `366`. December 31 of a leap year has `DDD` equal to 366.

## Key Takeaways

In `DateTimeFormatter` patterns, **letter case determines different fields**: `MM` is month, `mm` is minute; `dd` is day of month, `DD` is day of year. For standard calendar dates, prefer `uuuu-MM-dd`; for times, use `HH:mm:ss`. Also distinguish `YYYY` (week-based year) from `yyyy`/`uuuu` (calendar year according to their respective rules). Choose patterns based on the data type, specify a locale when text names are needed, and verify with examples where month, day, and minute have distinct values to avoid silent formatting bugs.
