# Why Is `uuuu` More Suitable Than `yyyy` in Many Strict Parsing Patterns?

## A Valid String Can Still Fail to Create a `LocalDate`

Suppose an input file records dates in the format `2024-02-29`. You create the pattern `yyyy-MM-dd`, enable `ResolverStyle.STRICT` to reject invalid dates, and then find that even this valid date fails to parse into a `LocalDate`.

The problem is not the hyphens or the leap year. In `java.time.format.DateTimeFormatter`, `yyyy` represents the **year-of-era**; whereas `uuuu` represents the **proleptic year on the calendar's continuous timeline**. For a pattern consisting only of year, month, and day without an era, `uuuu-MM-dd` usually provides the exact set of fields required to create an ISO date.

This article covers `DateTimeFormatter` in `java.time`, ISO calendar date inputs, and `LocalDate` results. Do not mechanically apply this pattern-letter swap to `SimpleDateFormat` or all other calendar systems.

## 1. Distinguishing Three Concepts: Year, Year-of-Era, and Era

In the pattern syntax of `DateTimeFormatter`:

| Pattern letter | Field/concept | Question answered |
| --- | --- | --- |
| `u`, commonly written `uuuu` | `YEAR`, proleptic year | Which year on the calendar's year timeline? |
| `y`, commonly written `yyyy` | `YEAR_OF_ERA`, year-of-era | Which year within the era? |
| `G` | `ERA`, era | Which era does it belong to? |

The number of repeated pattern letters determines how the number is formatted/parsed; it does not turn `yyyy` into the `YEAR` field. [`DateTimeFormatter` pattern letters table](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

For the ISO calendar system, the two eras are Common Era (CE/AD) and Before Common Era (BCE/BC). Their relationship can be seen in the following table:

| Date by era | `YEAR_OF_ERA` | `YEAR` in `LocalDate` |
| --- | ---: | ---: |
| Year 2024 AD | 2024 | 2024 |
| Year 1 AD | 1 | 1 |
| Year 1 BC | 1 | 0 |
| Year 2 BC | 2 | -1 |

The ISO year timeline of `LocalDate` includes year `0`. In era-based year numbering, the first year of each era is `1`. Therefore, "year 1" without knowing the era does not uniquely identify the same year on the continuous timeline. [ISO chronology documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/IsoChronology.html), [`ChronoField` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoField.html)

In most modern real-world data, the numeric values of `YEAR` and `YEAR_OF_ERA` are identical. That exact overlap is what makes pattern authors easily assume the two letters are equivalent.

## 2. Mechanism: Reading Enough Digits Does Not Guarantee Enough Information to Create a Date

Date-time parsing has two key stages:

1. Parsing the text according to the pattern into fields and values.
2. Resolving the fields into a complete date-time.

`ResolverStyle` controls the resolution stage. With the pattern `yyyy-MM-dd`, the string `2024-02-29` produces the following information:

```text
YEAR_OF_ERA = 2024
MONTH_OF_YEAR = 2
DAY_OF_MONTH = 29
ERA = missing
```

When only `YEAR_OF_ERA` is present, `STRICT` mode in the ISO calendar system does not assume an era. In this situation, the fields are insufficient to create a `LocalDate`. With `SMART` or `LENIENT`, the Common Era (CE) is assumed if missing. [`IsoChronology` resolution rules](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/IsoChronology.html#resolveDate(java.util.Map,java.time.format.ResolverStyle))

Conversely, the pattern `uuuu-MM-dd` provides:

```text
YEAR = 2024
MONTH_OF_YEAR = 2
DAY_OF_MONTH = 29
```

This trio directly identifies an ISO date; strict mode can then check whether day 29 is valid in February of year 2024.

The key takeaway is that **an error caused by missing information for resolution** is different from **an error caused by a nonexistent date**. Both can appear as a `DateTimeParseException` when calling `LocalDate.parse`, but the fix is not the same.

## 3. Complete Program Demonstrating Each Case

Save this as `StrictYearDemo.java`. The program uses the standard library and compiles with Java 17 or later:

```java
import java.time.LocalDate;
import java.time.chrono.IsoEra;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;

public class StrictYearDemo {
    private static void show(
            String label, String text, DateTimeFormatter formatter) {
        try {
            System.out.println(label + "=" + LocalDate.parse(text, formatter));
        } catch (DateTimeParseException ex) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        DateTimeFormatter strictU =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter strictY =
                DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter smartY =
                DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ROOT);

        DateTimeFormatter smartU =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);

        show("strictUValid", "2024-02-29", strictU);
        show("strictUInvalid", "2023-02-29", strictU);
        show("strictYWithoutEra", "2024-02-29", strictY);
        show("smartYValid", "2024-02-29", smartY);
        show("smartUInvalid", "2023-02-29", smartU);

        TemporalAccessor fields = strictY.parse("2024-02-29");
        System.out.println("hasYear="
                + fields.isSupported(ChronoField.YEAR));
        System.out.println("hasYearOfEra="
                + fields.isSupported(ChronoField.YEAR_OF_ERA));

        DateTimeFormatter strictWithEra =
                DateTimeFormatter.ofPattern("yyyy-MM-dd G", Locale.ENGLISH)
                        .withResolverStyle(ResolverStyle.STRICT);

        show("strictYWithAD", "2024-02-29 AD", strictWithEra);
        show("strictYWithBC", "0001-01-01 BC", strictWithEra);
        show("strictUYearZero", "0000-01-01", strictU);
        show("strictUNegativeYear", "-0001-01-01", strictU);
        show("strictYZeroWithAD", "0000-01-01 AD", strictWithEra);

        DateTimeFormatter strictDefaultCE =
                new DateTimeFormatterBuilder()
                        .appendPattern("yyyy-MM-dd")
                        .parseDefaulting(ChronoField.ERA, IsoEra.CE.getValue())
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        show("strictYDefaultCE", "2024-02-29", strictDefaultCE);
    }
}
```

Compile and run:

```shell
javac --release 17 StrictYearDemo.java
java StrictYearDemo
```

Stdout:

```text
strictUValid=2024-02-29
strictUInvalid=REJECTED
strictYWithoutEra=REJECTED
smartYValid=2024-02-29
smartUInvalid=2023-02-28
hasYear=false
hasYearOfEra=true
strictYWithAD=2024-02-29
strictYWithBC=0000-01-01
strictUYearZero=0000-01-01
strictUNegativeYear=-0001-01-01
strictYZeroWithAD=REJECTED
strictYDefaultCE=2024-02-29
```

The `REJECTED` labels are printed by the program itself to keep the output stable; the program does not depend on the exact exception message text of a specific JDK version.

## 4. Reading the Results: `uuuu` and `STRICT` Solve Two Separate Things

The first group shows:

- `strictUValid`: has the direct year field and the date exists, so it succeeds.
- `strictUInvalid`: the year field is sufficient, but year 2023 does not have February 29, so it is rejected.
- `strictYWithoutEra`: the date is valid under a Common Era interpretation, but the strict configuration does not automatically fill in the missing era.
- `smartYValid`: the default configuration of `ofPattern` is `SMART`, so the example succeeds by assuming the era.
- `smartUInvalid`: switching to `uuuu` alone without enabling `STRICT` still accepts `2023-02-29` and adjusts it to `2023-02-28`.

Therefore, if the goal is to parse ISO dates without an era and reject nonexistent dates, both choices are required:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

This is a configuration snippet using the same imports as the complete program.

`uuuu` selects the right **year-field semantics**; `STRICT` selects **strict resolution rules**. Neither choice replaces the other. Date adjustment behavior in `SMART` mode and date validation in `STRICT` mode are described in the [`ResolverStyle` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html).

## 5. Why Might `formatter.parse(text)` Not Throw an Exception?

In the program, the line:

```java
TemporalAccessor fields = strictY.parse("2024-02-29");
```

does not require the result to be a `LocalDate`. It can return an object holding the parsed fields that have not yet been resolved into a date. The check output:

```text
hasYear=false
hasYearOfEra=true
```

shows that the digits `2024` were parsed, but they are stored in `YEAR_OF_ERA`, not `YEAR`.

When you call:

```java
LocalDate.parse("2024-02-29", strictY);
```

you additionally request the step of creating a concrete date, and that request fails in this era-less configuration.

Therefore, a validation check that only calls `formatter.parse(text)` and concludes "the string is definitely a valid date" may not be checking the actual output the application needs. If you need a date, verify the creation of `LocalDate`, and then check the resulting value.

## 6. `yyyy` Is Still Appropriate When the Data Actually Speaks in Terms of Eras

There are two valid approaches if the data contract has year-of-era semantics.

### Input Provides the Era

The pattern `yyyy-MM-dd G` paired with `Locale.ENGLISH` in the program can parse:

```text
2024-02-29 AD
0001-01-01 BC
```

The second result is `0000-01-01` when converted to the proleptic year representation of `LocalDate`. This does not mean the program mistakenly subtracted a year: the two numbering systems are describing the same year.

Textual era symbols depend on the formatter's locale. Choose a `Locale` that matches your data; do not assume `AD`/`BC` works for every language.

### Contract Explicitly Defaults an Era

If an interface intentionally uses year-of-era and specifies that any year missing an era is Common Era, you can configure this explicitly:

```java
DateTimeFormatter formatter =
        new DateTimeFormatterBuilder()
                .appendPattern("yyyy-MM-dd")
                .parseDefaulting(ChronoField.ERA, IsoEra.CE.getValue())
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

This is a snippet from the complete program. This option adds an intentional default; it does not make `yyyy` mean the same thing as `uuuu`.

For a simple interface accepting ISO `year-month-day` dates without a separate era concept, using the proleptic year directly is usually clearer than adding a default value just to make a `yyyy` pattern work.

## 7. Valid Parsing Does Not Replace Business Rules

In the program, both `strictUYearZero` and `strictUNegativeYear` succeed. This is a capability of the calendar model, not automatically valid data for every application.

For example, a system that only allows course schedules from year 2000 to 2099 needs a separate check after parsing:

```java
static LocalDate parseCourseDate(String text) {
    LocalDate date = LocalDate.parse(
            text,
            DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT));

    if (date.getYear() < 2000 || date.getYear() > 2099) {
        throw new IllegalArgumentException("Nam hoc ngoai pham vi 2000..2099");
    }
    return date;
}
```

This is an illustrative method that should be placed in a class using the same imports as the full program. In frequently executed code, the formatter can be declared as a shared constant.

Two layers of validation should be distinguished:

- **Calendar validity:** the fields can be parsed and form an existing date.
- **Business validity:** the date falls within the range and conditions permitted by the system.

Nor should four `u` letters be misunderstood as a business rule forcing the year to be within `0000..9999`. Rules about year width and sign belong to the pattern syntax; the product's allowed year range must be specified and verified separately if required.

## 8. Quick Fixes That Easily Hide the Root Cause

| Fix | Problem | Meaningful approach |
| --- | --- | --- |
| Remove `STRICT` so valid dates stop failing | May allow invalid dates to be silently adjusted in `SMART` | Choose the right year field, keep the required resolution rules |
| Change every `yyyy` to `uuuu` across all APIs | Different APIs may define pattern letters differently | Verify the library and contract first |
| Switch to `YYYY` thinking uppercase is "more standard" | `Y` is week-based-year, not ordinary calendar year | Use `u` or `y` according to the intended meaning |
| Test only a mid-year date | Misses leap days, year 0, or missing eras | Include valid, invalid, and appropriate boundary cases |
| Test only formatting a date to a string | Modern dates can format identically with `uuuu` and `yyyy` | Test the actual parsing direction into the target type |

Specifically, `SimpleDateFormat` from the legacy API uses `u` for the day number of week. Do not copy a `DateTimeFormatter` pattern like `uuuu-MM-dd` verbatim to that API. [`SimpleDateFormat` pattern table](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html)

If the input is already a standard ISO date, `LocalDate.parse(text)` is the direct choice; there is no need to recreate a custom pattern just to use `uuuu`. A custom pattern should be justified by the data format.

## 9. Self-Check

1. Why can `yyyy-MM-dd` with `STRICT` reject `2024-02-29` even though that date exists?
2. Does changing `yyyy` to `uuuu` alone while keeping `SMART` guarantee rejecting `2023-02-29`?
3. When the input is `0001-01-01 BC`, should you use the proleptic year field directly or year-of-era together with era?
4. Does `formatter.parse(text)` not throwing an exception prove that a `LocalDate` can be created?

Suggested answers:

1. Because `YEAR_OF_ERA` is present while `ERA` is missing; strict mode does not assume the era.
2. No; the program shows that `SMART` can adjust it to `2023-02-28`.
3. This data expresses year-of-era, so `yyyy` paired with `G` is the meaningful choice.
4. Not yet; you need to verify the result in the exact target type that the application uses.

When writing a date parser without an era, choose the year field that the data actually carries, keep the appropriate resolver style, and check both date creation and business constraints.
