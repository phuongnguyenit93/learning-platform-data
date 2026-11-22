# Separating Field Parsing and Date-Time Field Resolution

## “Reading Numbers” Is Different from “Constructing a Date”

The string `2023-02-29` has a very clear year–month–day structure: we can read year 2023, month 2, and day 29. However, that combination cannot form a valid date, because the year 2023 does not have February 29.

Conversely, the string `2024-2-29` describes an existing date, but may fail to match a parser that requires a two-digit month.

These two scenarios help distinguish:

1. **Parsing fields from text:** recognizing digits and separators and storing them into temporal fields.
2. **Resolving date-time fields:** combining the fields according to the chronology's rules, validating them, and producing a meaningful value.

Understanding these two phases helps you fix the right configuration when parsing fails, instead of randomly changing field widths, adding defaults, or relaxing modes.

## 1. The Processing Picture from String to Target Type

```text
"2024-02-29"
      │
      │ parsed according to the formatter structure
      ▼
YEAR=2024
MONTH_OF_YEAR=2
DAY_OF_MONTH=29
      │
      │ resolved according to chronology and ResolverStyle
      ▼
Valid ISO date 2024-02-29
      │
      │ extracted as the exact type requested by the caller
      ▼
LocalDate
```

This is a conceptual model. High-level APIs like `LocalDate.parse(text, formatter)` perform that chain of work in a single call; you do not need to separate them manually when writing ordinary date input code.

`DateTimeFormatter` describes string parsing in two phases: parsing text into fields/values, and then resolving them into a date or time. Queries such as `LocalDate` require the result to contain sufficient matching information. [`DateTimeFormatter` resolution documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

## 2. What Does the Field Parsing Phase Care About?

The parser follows the declared components:

- Reading numeric fields according to width and sign rules.
- Reading month names, day-of-week names, or other symbols according to locale/configuration.
- Matching literal characters such as `-`, `:`, or `T`.
- Handling mandatory and optional sections.
- Recording the parsed fields, such as `YEAR`, `MONTH_OF_YEAR`, `HOUR_OF_DAY`.
- Tracking the parsed position and syntax error index when using positional APIs.

For example, with the pattern `uuuu-MM-dd`, the string `2023-02-29` can provide all three fields:

```text
YEAR = 2023
MONTH_OF_YEAR = 2
DAY_OF_MONTH = 29
```

Having all three values does not prove that the date combination exists. Meanwhile, the single-digit month in `2024-2-29` can cause a strict text parser to fail before a complete set of fields is even obtained.

Some conflicts when the same field is parsed multiple times can also be detected right during parsing. The two-phase model should not be understood as a guarantee that all kinds of validation are deferred until the end.

## 3. What Else Does the Resolution Phase Do?

Resolution does more than convert numbers into an object. For ordinary ISO dates and times, it also needs to:

- Determine the applicable chronology.
- Convert related fields into a specific year, month, and day if sufficient data is present.
- Validate field ranges and combinations according to `ResolverStyle`.
- Combine hour, minute, second, and fractional fields when sufficient information is present.
- Cross-check redundant fields against the resolved date-time—for example, day-of-year must match month/day.
- Combine instant or time-zone information when the data type and related fields allow.

These are responsibilities to help you visualize the process, not an exhaustive copy of the internal processing order. ISO date rules are defined in [`IsoChronology.resolveDate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/IsoChronology.html#resolveDate(java.util.Map,java.time.format.ResolverStyle)).

For example, `YEAR=2023`, `MONTH=2`, `DAY=29` will be handled differently depending on the mode:

| Resolution mode | Result for `2023-02-29` in the example |
| --- | --- |
| `STRICT` | Rejects the nonexistent date |
| `SMART` | Adjusts to the last day of the month: `2023-02-28` |
| `LENIENT` | Carries the excess days into the next month: `2023-03-01` |

Each mode has its own rules per field and chronology; `SMART` should not be interpreted as “always safe for every input.” [`ResolverStyle` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)

## 4. Two Kinds of “Strict” Are Not Synonymous

The naming is easy to confuse:

| Configuration | Primary responsibility |
| --- | --- |
| `DateTimeFormatterBuilder.parseStrict()` | Text matching rules, such as width and sign |
| `DateTimeFormatterBuilder.parseLenient()` | Relaxes text matching rules from the configured position onward |
| `formatter.withResolverStyle(STRICT)` | Strictly resolves fields into a date-time |
| `formatter.withResolverStyle(LENIENT)` | Resolves with rules that allow appropriate overflow values |

By default, the builder parses text in strict mode. Meanwhile, formatters created by `toFormatter` or `ofPattern` default to the `SMART` resolution mode. Therefore, “having called `parseStrict()`” does not mean “nonexistent dates are guaranteed to be rejected.” [`DateTimeFormatterBuilder` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html)

Conversely, you can allow single-digit months/days during the parsing phase while still requiring the combination to form an existing date during the resolution phase. A configuration is meaningful when it reflects the data contract, not because the word `STRICT` appears more times.

## 5. A Complete Program to Observe the Two Phases

Save as `ParsingPhasesDemo.java`. The program uses Java 17 or later and the standard library:

```java
import java.text.ParsePosition;
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;

public class ParsingPhasesDemo {
    private static void inspectRaw(
            String label, String text, DateTimeFormatter formatter) {
        ParsePosition position = new ParsePosition(0);
        TemporalAccessor raw = formatter.parseUnresolved(text, position);
        System.out.println(label + "=" + (raw == null ? "FAILED" : "READ")
                + ",index=" + position.getIndex());
    }

    private static void showDate(
            String label, String text, DateTimeFormatter formatter) {
        try {
            System.out.println(label + "=" + LocalDate.parse(text, formatter));
        } catch (DateTimeException ex) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        DateTimeFormatter strict =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        inspectRaw("rawInvalidCalendar", "2023-02-29", strict);
        inspectRaw("rawWrongWidth", "2024-2-29", strict);
        inspectRaw("rawTrailing", "2024-02-29extra", strict);

        ParsePosition position = new ParsePosition(0);
        TemporalAccessor raw = strict.parseUnresolved("2023-02-29", position);
        System.out.println("rawDay=" + raw.getLong(ChronoField.DAY_OF_MONTH));

        showDate("strictValid", "2024-02-29", strict);
        showDate("strictInvalid", "2023-02-29", strict);
        showDate("smartInvalid", "2023-02-29",
                strict.withResolverStyle(ResolverStyle.SMART));
        showDate("lenientInvalid", "2023-02-29",
                strict.withResolverStyle(ResolverStyle.LENIENT));
        showDate("fullTrailing", "2024-02-29extra", strict);

        DateTimeFormatter textStrict =
                new DateTimeFormatterBuilder()
                        .parseStrict()
                        .appendPattern("uuuu-MM-dd")
                        .toFormatter(Locale.ROOT);

        showDate("textStrictButSmart", "2023-02-29", textStrict);

        DateTimeFormatter flexibleWidth =
                new DateTimeFormatterBuilder()
                        .parseLenient()
                        .appendPattern("uuuu-MM-dd")
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        showDate("flexibleWidthValid", "2024-2-9", flexibleWidth);
        showDate("flexibleWidthInvalid", "2023-2-29", flexibleWidth);

        DateTimeFormatter redundant =
                DateTimeFormatter.ofPattern("uuuu-MM-dd-DDD", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        inspectRaw("rawConflictingFields", "2024-02-29-061", redundant);
        showDate("resolvedConflictingFields", "2024-02-29-061", redundant);

        DateTimeFormatter monthOnly =
                DateTimeFormatter.ofPattern("uuuu-MM", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        TemporalAccessor monthFields = monthOnly.parse("2024-02");
        System.out.println("yearMonth=" + YearMonth.from(monthFields));

        try {
            LocalDate.from(monthFields);
            System.out.println("localDateFromMonth=CREATED");
        } catch (DateTimeException ex) {
            System.out.println("localDateFromMonth=REJECTED");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 ParsingPhasesDemo.java
java ParsingPhasesDemo
```

Stdout:

```text
rawInvalidCalendar=READ,index=10
rawWrongWidth=FAILED,index=0
rawTrailing=READ,index=10
rawDay=29
strictValid=2024-02-29
strictInvalid=REJECTED
smartInvalid=2023-02-28
lenientInvalid=2023-03-01
fullTrailing=REJECTED
textStrictButSmart=2023-02-28
flexibleWidthValid=2024-02-09
flexibleWidthInvalid=REJECTED
rawConflictingFields=READ,index=14
resolvedConflictingFields=REJECTED
yearMonth=2024-02
localDateFromMonth=REJECTED
```

The labels `READ`, `FAILED`, and `REJECTED` are how the program describes the results, not verbatim messages from the JDK.

## 6. Reading the Output: Distinct Pieces of Evidence

### Reading All Fields Does Not Mean a Valid Date

`rawInvalidCalendar=READ,index=10` and `rawDay=29` show that `parseUnresolved` read the number 29 from an input that has no corresponding real date.

For the same string, `LocalDate.parse` with `STRICT` rejects it; with `SMART` and `LENIENT`, it produces two different adjusted results. The difference belongs to the resolution phase, not because three parsers read three different day numbers.

### Syntax Can Fail Before Calendar Validation

`rawWrongWidth=FAILED,index=0` occurs because the single-digit month structure does not match the parsing rules in use. The current index of `ParsePosition` on failure is not always the index where the cause occurred; when diagnosing, also check `getErrorIndex()`.

The `flexibleWidth` formatter proves that you can read short month/day values and still reject nonexistent dates. It does not turn `STRICT` at the resolution step into a requirement for two-digit months.

### Reading a Prefix Is Not Checking the Entire String

`rawTrailing=READ,index=10` only says that the date part at the beginning of `2024-02-29extra` was read. Positional `parseUnresolved` does not automatically require consuming the entire input.

`fullTrailing=REJECTED` shows that the full parse call rejects the trailing characters. You need to distinguish “fields were read” from “the entire input field was validated.”

## 7. Resolution Also Detects Inconsistent Fields

The pattern:

```text
uuuu-MM-dd-DDD
```

contains both month/day and day-of-year. In the leap year 2024, February 29 is day `060`, not `061`.

The string:

```text
2024-02-29-061
```

has all numbers parsed cleanly according to the structure, but the two ways of identifying the date are inconsistent. The resolver rejects it instead of arbitrarily picking one side.

That is why resolution should not be viewed merely as checking each field independently against its valid range. `DAY_OF_MONTH=29` and `DAY_OF_YEAR=61` are both numbers that can be valid individually; it is the relationship between them that causes the error.

If the data intentionally provides redundant information for cross-checking, keep that cross-check. Do not drop a field from resolution just so conflicting inputs can “parse.”

## 8. Successful Resolution May Still Be Insufficient for the Target Type

`monthOnly.parse("2024-02")` in the program reads the entire string and retains year–month information. `YearMonth.from` obtains the result `2024-02`.

However, `LocalDate.from` cannot construct a date because the day-of-month is missing. This is a problem of **missing information for the target type**, not that February 2024 is invalid.

Similarly:

- Having only a date is not enough to construct a `LocalDateTime` without a rule for supplying the time.
- Having only a local date-time is not enough to uniquely determine an `Instant` without an appropriate offset/zone.
- A year-of-era may also require era information before constructing a date in a strict configuration.

When encountering an error, determine what type the data should actually hold. Only supply default fields when the contract allows it and the meaning of those default values can be explained.

## 9. Which API Should You Use for Each Purpose?

| Purpose | Usually appropriate API |
| --- | --- |
| Parse a complete date for immediate use | `LocalDate.parse(text, formatter)` |
| Parse a year–month | `YearMonth.parse(text, formatter)` |
| Parse completely and use a specific type query | `formatter.parse(text, LocalDate::from)` |
| Diagnose fields before resolution | `formatter.parseUnresolved(text, position)` |
| Parse a segment within a larger structure | API with `ParsePosition`, plus checking the remainder |

`parseUnresolved` is a low-level API. It does not resolve dates, may parse only part of the string, and may return `null` when parsing fails. Do not use a “non-null result” check as a valid-date validator. [`parseUnresolved` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parseUnresolved(java.lang.CharSequence,java.text.ParsePosition))

Nor should you assume `LocalDate.from` will re-run the entire formatter pipeline on an unresolved result. When you need a date result in production code, letting the full parse API construct the date according to the chosen configuration is usually simpler.

For diagnostic code, check specific fields using `isSupported`/`getLong` rather than relying on the order or `toString()` format of the intermediate object.

## 10. A Troubleshooting Workflow You Can Apply

When a string fails to produce the desired type:

1. Verify the pattern and actual data: field order, separators, widths, letter case, and locale.
2. If the failure location is unclear, use an unresolved parse in diagnostic code to see whether fields can be read and up to what index.
3. Check whether the entire input was consumed; succeeding on a prefix is not enough.
4. Verify whether the fields required for the target type are present.
5. Check the resolution rules, chronology, and relationships between fields.
6. After obtaining a typed value, apply business constraints such as year ranges or allowed dates.

The diagnostic step is not a requirement to add an unresolved-parse layer to every production function. Once you find the root cause, keep the main processing path simple and verify it against the contract.

A useful test suite should cover separately: invalid syntax, nonexistent dates, missing fields, conflicting fields, trailing characters, and valid values. If everything is lumped together as “invalid string,” it becomes very hard to tell whether a future fix accidentally relaxes another kind of input.

## 11. Self-Check

1. Why can `parseUnresolved` successfully read `2023-02-29`?
2. Does calling `parseStrict()` guarantee that `2023-02-29` will be rejected?
3. Why can `2024-02-29-061` pass the parsing step but fail during resolution?
4. Can a valid year–month string necessarily produce a `LocalDate`?
5. If the parsing step only reaches index 10 in a 15-character string, what should you conclude?

Answer hints:

1. Because it can read the three fields without checking whether they form an existing date.
2. Not yet; you need to choose an appropriate resolution rule, such as `ResolverStyle.STRICT`.
3. The fields are structurally valid, but they point to two different dates.
4. No; `LocalDate` also requires a day-of-month, whereas `YearMonth` matches the available information.
5. Only a prefix was read; the remainder must be handled according to the contract, rather than treating it as a success for the entire field.

Separate the question “which fields were read?” from “can those fields form the value we need?”. That distinction helps you choose the right configuration and accurately explain the cause of date-time parsing errors.
