# Default Values with `parseDefaulting()`

## Filling in Missing Information Requires a Clear Convention

A report file allows recording the reporting period as `2024-02`, but also allows recording a specific date such as `2024-02-20`. The application wants to convert both into `LocalDate` and specifies: if only year–month is provided, use the first day of the month as the anchor date.

The string `2024-02` has no syntax error under this contract; it is simply missing the day field that `LocalDate` requires. `DateTimeFormatterBuilder.parseDefaulting()` helps supply the missing field value during parsing.

However, day `01` is an application convention, not information sent by the source. Before using a default, confirm that filling it in makes business sense. If the data is truly just a month, keeping `YearMonth` may be more accurate than turning it into a date.

## 1. What Does `parseDefaulting(field, value)` Do?

The call looks like this:

```java
builder.parseDefaulting(ChronoField.DAY_OF_MONTH, 1);
```

It adds an instruction to the formatter. During parsing, at the point where that instruction is encountered:

- If the field already has a value, the existing value is kept.
- If the field does not yet have a value, the default value is inserted into the parsed result.
- The value is inserted immediately at that point, so parser components that run afterward can see it.

Therefore, defaults are usually placed **after components that may read that field**. In the formatting direction from a value to a string, this instruction has no effect. [`parseDefaulting` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html#parseDefaulting(java.time.temporal.TemporalField,long))

You can visualize the field set after reading as follows:

```text
Input 2024-02:
    YEAR=2024, MONTH_OF_YEAR=2
    ↓ default DAY_OF_MONTH=1
    YEAR=2024, MONTH_OF_YEAR=2, DAY_OF_MONTH=1
    ↓ resolve and validate against the calendar
    LocalDate 2024-02-01

Input 2024-02-20:
    YEAR=2024, MONTH_OF_YEAR=2, DAY_OF_MONTH=20
    ↓ default sees the day field is already present, keeps it
    LocalDate 2024-02-20
```

This is an operation on **temporal fields**, not concatenating the string `"-01"` to every input.

## 2. Separating Two Responsibilities: Allowing Omission and Supplying When Missing

To accept both `2024-02` and `2024-02-20`, we need two configurations:

1. The `-dd` section is optional in the syntax.
2. If that section is absent, supply a default day.

These two responsibilities correspond to `optionalStart()/optionalEnd()` and `parseDefaulting()`. Declaring a default alone does not automatically turn a required section into an optional one.

Main structure:

```java
DateTimeFormatter monthOrDate =
        new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM")
                .optionalStart()
                    .appendLiteral('-')
                    .appendPattern("dd")
                .optionalEnd()
                .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

This is an illustrative snippet; it requires the imports shown in the full program below.

The placement of `parseDefaulting` is outside and after the optional section. As a result, when the input does not have `-dd`, the instruction to supply the day is still executed.

## 3. Full Program: Reading Missing Parts, Keeping Present Parts, and Rejecting Invalid Data

Save as `ParseDefaultingDemo.java`. The program uses Java 17 or later:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class ParseDefaultingDemo {
    private static void showDate(
            String label, String text, DateTimeFormatter formatter) {
        try {
            System.out.println(label + "=" + LocalDate.parse(text, formatter));
        } catch (DateTimeException ex) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        DateTimeFormatter monthOrDate =
                new DateTimeFormatterBuilder()
                        .appendPattern("uuuu-MM")
                        .optionalStart()
                            .appendLiteral('-')
                            .appendPattern("dd")
                        .optionalEnd()
                        .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        showDate("missingDay", "2024-02", monthOrDate);
        showDate("explicitDay", "2024-02-20", monthOrDate);
        showDate("invalidDate", "2023-02-29", monthOrDate);
        showDate("malformedOptional", "2024-02-xx", monthOrDate);

        DateTimeFormatter requiredDay =
                new DateTimeFormatterBuilder()
                        .appendPattern("uuuu-MM-dd")
                        .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        showDate("defaultDoesNotMakeOptional", "2024-02", requiredDay);

        DateTimeFormatter tooEarly =
                new DateTimeFormatterBuilder()
                        .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                        .appendPattern("uuuu-MM-dd")
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        showDate("earlyDefaultConflict", "2024-02-20", tooEarly);

        DateTimeFormatter dayThirtyOne =
                new DateTimeFormatterBuilder()
                        .appendPattern("uuuu-MM")
                        .parseDefaulting(ChronoField.DAY_OF_MONTH, 31)
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        showDate("defaultValidInJanuary", "2024-01", dayThirtyOne);
        showDate("defaultInvalidInFebruary", "2024-02", dayThirtyOne);

        DateTimeFormatter dateOrMinute =
                new DateTimeFormatterBuilder()
                        .appendPattern("uuuu-MM-dd")
                        .optionalStart()
                            .appendLiteral('T')
                            .appendPattern("HH:mm")
                        .optionalEnd()
                        .parseDefaulting(ChronoField.HOUR_OF_DAY, 0)
                        .parseDefaulting(ChronoField.MINUTE_OF_HOUR, 0)
                        .parseDefaulting(ChronoField.SECOND_OF_MINUTE, 0)
                        .parseDefaulting(ChronoField.NANO_OF_SECOND, 0)
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println("missingTime="
                + LocalDateTime.parse("2024-06-15", dateOrMinute));
        System.out.println("explicitTime="
                + LocalDateTime.parse("2024-06-15T09:30", dateOrMinute));

        System.out.println("formatYearMonth="
                + monthOrDate.format(YearMonth.of(2024, 2)));
        System.out.println("formatResolvedDate="
                + monthOrDate.format(LocalDate.parse("2024-02", monthOrDate)));
    }
}
```

Compile and run:

```shell
javac --release 17 ParseDefaultingDemo.java
java ParseDefaultingDemo
```

Stdout:

```text
missingDay=2024-02-01
explicitDay=2024-02-20
invalidDate=REJECTED
malformedOptional=REJECTED
defaultDoesNotMakeOptional=REJECTED
earlyDefaultConflict=REJECTED
defaultValidInJanuary=2024-01-31
defaultInvalidInFebruary=REJECTED
missingTime=2024-06-15T00:00
explicitTime=2024-06-15T09:30
formatYearMonth=2024-02
formatResolvedDate=2024-02-01
```

The `REJECTED` labels are printed by the program itself; they do not depend on the error message text of a specific JDK version.

## 4. Keeping the Source Value Instead of Overwriting It

The first two outputs demonstrate an important rule:

```text
2024-02    → 2024-02-01
2024-02-20 → 2024-02-20
```

When day `20` has already been read before the defaulting instruction, the default `1` does not replace it. This is why using `parseDefaulting` is usually clearer than "parse first and then always call `withDayOfMonth(1)`".

The following snippet illustrates a transformation with a different meaning:

```java
LocalDate date = LocalDate.parse("2024-02-20");
LocalDate firstOfMonth = date.withDayOfMonth(1);
```

It actively turns day 20 into day 1. If the requirement is only to fill in when missing, that operation is not equivalent.

Similarly, the hour default `0` in the program does not turn an input with `09:30` into midnight. The hour/minute fields that are already present are preserved.

## 5. Why Placing a Default Too Early Can Cause Conflicts

The `tooEarly` formatter in the program executes in this order:

```text
Nothing read yet
    ↓ insert DAY_OF_MONTH=1 into the result
Read uuuu-MM-dd
    ↓ text wants DAY_OF_MONTH=20
Two values for the same field conflict
```

A default does not wait until the end of the entire process to decide whether a field is missing or present. It checks the state **at the exact position where it was added to the builder**. Therefore, a field appearing in a later part of the text cannot be considered "already read" at an earlier instruction position.

A practical rule of thumb for typical examples is:

```text
parts that read required fields
    → parts that read optional fields
    → defaults for fields still missing
    → toFormatter
    → resolver configuration
```

You should also avoid placing a default only inside an optional section where the entire section can be skipped. When the section is not read, an instruction inside that section is not a guarantee that the field will be supplied for the result outside the section.

For complex structures, test cases with the optional part present, with the optional part absent, and with the optional part present but malformed. Do not test only the shortest input.

## 6. Defaults Do Not Rescue Required Syntax or Invalid Data

Three situations must be distinguished:

| Situation | Example | Handling in This Lesson |
| --- | --- | --- |
| Field is allowed to be absent | `2024-02` with an optional day section | Supply day 1 |
| Field is required but absent | `2024-02` with full pattern `uuuu-MM-dd` | Reject |
| Input has an invalid part | `2024-02-xx` or `2023-02-29` | Reject |

With `requiredDay`, the parser still needs to read `-dd`; adding a default after the pattern does not change that syntax requirement.

With `2024-02-xx`, the optional section cannot be read completely and trailing characters remain; a full parse call does not ignore the trailing part to accept just `2024-02`.

With `2023-02-29`, the day field already has a value, so the default does not replace it with `1`. Strict mode then rejects the nonexistent date.

If a policy for correcting invalid data is needed, that is a different requirement and must be designed separately. It should not be hidden under the name "default value".

## 7. The Default Value Must Also Be Valid in Context

`DAY_OF_MONTH=31` is within the general range of the day field, but it does not exist in every month. The program gives:

```text
2024-01 + default day 31 → 2024-01-31
2024-02 + default day 31 → rejected with STRICT
```

The supplied value still participates in resolution and calendar validation. Therefore, defaulting day `1` is generally suitable for a first-of-month convention, whereas defaulting day `31` cannot be used to express "the last day of the month" for every month.

If the business logic wants **the last day of the month**, keep `YearMonth` and call:

```java
YearMonth month = YearMonth.parse("2024-02");
LocalDate lastDate = month.atEndOfMonth();
// lastDate = 2024-02-29
```

This is an illustrative snippet using `YearMonth` and `LocalDate` from `java.time`. It computes based on the specific month, not a constant default.

`toFormatter` creates a formatter with the default resolver style `SMART`. In the examples, `withResolverStyle(ResolverStyle.STRICT)` is set explicitly so invalid date combinations are not silently adjusted. [`toFormatter` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html#toFormatter(java.util.Locale)), [`ResolverStyle` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)

## 8. Supplying Time Does Not Automatically Create a Time Zone or Instant

In the `dateOrMinute` example, the contract is:

- Only the date may be sent.
- The date and hour/minute after the letter `T` may be sent.
- If the time is missing, the application interprets it as `00:00`.
- Seconds and nanoseconds are not entered in this syntax and default to zero.

The result is still a `LocalDateTime`. `2024-06-15T00:00` does not say which region's midnight it is. Adding time must not be treated as also adding UTC or the server's time zone.

Nor is it necessary to add defaults for every field a type can have. Supply only the fields that the contract requires and understand the resolution rules of the target type. The example explicitly sets hour, minute, second, and nanosecond to zero to make the policy clear, not to require every time parser to repeat that exact configuration.

If the source wants to express "time unknown", turning it into midnight may lose meaning. In that case, preserve the missing information in the data model instead of using defaults just so a parse operation always returns a value.

## 9. Defaults Have No Effect in the Formatting Direction

The last two lines of the program show:

```text
YearMonth 2024-02 → formatted as 2024-02
LocalDate 2024-02-01 → formatted as 2024-02-01
```

When formatting a `YearMonth`, the optional day section has no data to print. The defaulting instruction does not automatically add day 1 to the object to force printing that section.

Once the month string has been parsed into a `LocalDate`, the result has a day field equal to 1. Formatting that result can print the day as well, because the day is now actually present in the object.

This also points out a data limitation: after receiving `LocalDate 2024-02-01`, you cannot tell from that value alone whether the source sent `2024-02` or `2024-02-01`. If source granularity matters, also keep the input type or use a type such as `YearMonth` where appropriate.

## 10. Choosing Explainable and Verifiable Defaults

Before adding a `parseDefaulting`, determine:

1. Which field is actually allowed to be missing?
2. Which value is defaulted, and why does it make sense?
3. Is a present source value preserved?
4. Can the default create an invalid calendar combination?
5. Does the result lose information about the original granularity?

The value passed to `parseDefaulting(field, value)` is a number configured when building the formatter. It is not a function recomputed on each parse. If "current year" is used as the value when initializing a constant, that value may stay the same after the new year begins. For defaults that depend on context or the current time, design an explicit enrichment step with a testable time source instead of hiding it in an apparently static configuration.

A useful minimal test suite for the month/day example includes:

- Missing day as allowed by the specification.
- Explicit day different from the default day.
- Nonexistent date.
- Malformed optional part or trailing characters.
- Default day invalid for a given month.
- Misordered configuration to prove the test detects conflicts.

## 11. Practice Questions

1. Does `parseDefaulting(DAY_OF_MONTH, 1)` overwrite day `20` that was read earlier?
2. Why is adding a default after the required pattern `uuuu-MM-dd` not enough to accept `2024-02`?
3. Why can placing a default of day 1 before the `dd` section cause an input with day 20 to fail?
4. Is defaulting day 31 a way to compute the last day of the month?
5. After converting a month string to `LocalDate`, does it still retain the fact that the source omitted the day?

Answer hints:

1. No; a field that already has a value is kept.
2. Because the syntax rule still requires the day section; that section must be allowed to be absent separately.
3. Because the value 1 is inserted immediately, and then conflicts with the value 20 read afterward.
4. No; many months do not have 31 days. Use `YearMonth.atEndOfMonth()` when that is the requirement.
5. No; keep the granularity information separately if it is important.

Use `parseDefaulting` to implement a well-defined field-defaulting convention, place it in the right position, and still validate syntax, calendar rules, and the business meaning of the result.
