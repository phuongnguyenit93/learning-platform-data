# Optional Components and Multiple Input Formats

## 1. Optional Parts vs. Choosing Between Multiple Syntaxes

A system may accept both a standalone date `2026-10-25` and a date with time `2026-10-25T09:05`. These two forms share the date part; the time part is an extension that may be absent. This is a suitable case for **optional components** in `DateTimeFormatterBuilder`.

Another system accepts `2026-10-25` or `25/10/2026`. The field order and separators differ: these are **two alternative syntaxes**, not simply adding or removing a suffix.

Distinguishing between these two needs from the start helps avoid creating a formatter that accepts unexpected combinations or silently loses information.

| Requirement | Appropriate Representation |
|---|---|
| Optionally append time after a required date | Optional group |
| Optionally append seconds after hours and minutes | Nested optional groups |
| Same syntax but can produce multiple result types | `parseBest` with an appropriate query order |
| Two date notations with different structures | Separate formatters and explicit selection rules |
| Missing time is defined by convention as 00:00 | Explicitly configured default values |

## 2. optionalStart and optionalEnd Create a Group

An optional group starts with `optionalStart()` and ends with `optionalEnd()`. The elements inside are treated as a block that may be present or absent when parsing a string.

Example structure with a required date followed by an optional `T` and hour/minute:

```java
DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .append(DateTimeFormatter.ISO_LOCAL_DATE)
        .optionalStart()
            .appendLiteral('T')
            .appendValue(ChronoField.HOUR_OF_DAY, 2)
            .appendLiteral(':')
            .appendValue(ChronoField.MINUTE_OF_HOUR, 2)
        .optionalEnd()
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

The snippet above is the formatter declaration; full imports and usage are in Section 7.

The group contains the `T` character, hour, `:`, and minute. Therefore, the form without a time is a standalone date, not a date with a trailing `T`.

Placing a separator in the wrong position is a common mistake:

```java
.appendLiteral('T')
.optionalStart()
    // Hour/minute fields...
.optionalEnd()
```

This is only an illustration of an incorrect structure for the requirement at hand: `T` is outside the group, so it becomes required. Do not use this snippet if you want to accept a standalone date without `T`.

To attach a child formatter as an optional component, you can use `appendOptional(childFormatter)` instead of wrapping it manually in a group pair. You still need to determine correctly which separators belong to the group.

## 3. Nesting Groups to Express Dependencies

If seconds are allowed, the desired structure is:

```text
date [ T hour:minute [ :second ] ]
```

Square brackets in the diagram indicate optional parts, not characters entered by the user. The seconds group is nested inside the time group, so it can only appear after hours and minutes.

Valid inputs:

```text
2026-10-25
2026-10-25T09:05
2026-10-25T09:05:30
```

Inputs such as `2026-10-25T`, `2026-10-25T09`, or `2026-10-25T09:05:` are not valid ways of "omitting the optional part". When parsing the entire string, an incomplete group leaves unparsed trailing characters or causes an error; a trailing separator must not be treated as ignorable data.

Call `optionalEnd()` in order, closing the inner group first and then the outer group. Closing a group when no group is open causes an error when building the formatter. Although `toFormatter()` can automatically close any remaining open groups, you should write explicit open/close pairs so readers can verify the boundaries.

With a pattern, the corresponding structure for four-digit year examples can be written as:

```java
DateTimeFormatter.ofPattern("uuuu-MM-dd['T'HH:mm[:ss]]", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

The builder is suitable when you want to express each group and field through the API. There is no need to use both a pattern and a builder for the same structure just to increase the number of ways it is written.

## 4. Optional Syntax Does Not Automatically Populate Fields for Every Result Type

A formatter may be able to parse a standalone date, yet `LocalDateTime.parse` still cannot produce a result if hours and minutes are missing. An optional component allows data to be absent; it does not automatically decide that a missing time means midnight.

When you want to preserve the distinction between "date only" and "date with time", use:

```java
TemporalAccessor result = formatter.parseBest(
        text, LocalDateTime::from, LocalDate::from);
```

`parseBest` parses the entire string using **one formatter**, then tries the queries to convert to a result type in the given order. At least two queries are required, and the more information-rich type should be placed first.

For a date-time, `LocalDateTime::from` succeeds, so the time is preserved. For a standalone date, the first query lacks sufficient data; `LocalDate::from` can succeed.

If you reverse the order to `LocalDate::from, LocalDateTime::from`, a date-time can also be converted immediately to `LocalDate`, losing the time part in the return value. That is a result of the query order, not Java misinterpreting the string.

`parseBest` is not a feature for choosing among multiple unrelated patterns. It selects **the result type from the data already parsed by the formatter**; it does not automatically try `dd/MM/uuuu` when the formatter only describes `uuuu-MM-dd`.

## 5. Default Values Must Be an Intentional Decision

If the application's rule is that a date without a time is treated as `00:00`, you can add default values after assembling the structure:

```java
DateTimeFormatter withMidnight = new DateTimeFormatterBuilder()
        .append(formatter)
        .parseDefaulting(ChronoField.HOUR_OF_DAY, 0)
        .parseDefaulting(ChronoField.MINUTE_OF_HOUR, 0)
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

`parseDefaulting` supplies a field when that field is not already present; it does not overwrite an hour that was actually parsed. Place defaults after the input-parsing parts to prevent them from taking effect too early and conflicting with values present in the input.

Understand the impact: after defaulting, "no time provided" and "user explicitly provided 00:00" can produce the same `LocalDateTime`. If the two cases have different business meanings, keep a standalone date type or store the source information separately.

Default values also do not supply a time zone. A `LocalDateTime` at 00:00 is not yet a unique instant on the timeline; do not implicitly assume UTC or the host machine's time zone from a missing time.

## 6. Multiple Alternative Syntaxes: Clear Limits and Order

For two notations such as `uuuu-MM-dd` and `dd/MM/uuuu`, you can maintain two strict formatters and try them in a fixed order. Catch only `DateTimeParseException` for each attempt to move to the next syntax; if all fail, report that no supported input format matched.

Do not use a huge list of patterns to "guess as many as possible". A string like `03/04/2026` is ambiguous between day/month and month/day; if both are accepted, the trial order can determine a different date with no error indication. The input contract must define the meaning or ask the user for clarification.

Also, do not mistake the pattern `[uuuu-MM-dd][dd/MM/uuuu]` for an "either-or" operator. These are **two consecutive optional groups**: it does not enforce that exactly one group must be chosen. When formatting a `LocalDate` that has all fields, both parts may be printed, producing a concatenated string of both formats. When parsing, whether unintended combinations are accepted depends on overlapping fields and conflict checks.

Using separate formatters makes it easy to identify each accepted syntax, test each branch, and choose a single consistent output format.

## 7. Complete Runnable Program

Save the following code to `OptionalDateInputDemo.java`. The program uses Java 17 or later and requires no external libraries.

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;

public class OptionalDateInputDemo {
    private static final DateTimeFormatter FLEX =
            new DateTimeFormatterBuilder()
                    .append(DateTimeFormatter.ISO_LOCAL_DATE)
                    .optionalStart()
                        .appendLiteral('T')
                        .appendValue(ChronoField.HOUR_OF_DAY, 2)
                        .appendLiteral(':')
                        .appendValue(ChronoField.MINUTE_OF_HOUR, 2)
                        .optionalStart()
                            .appendLiteral(':')
                            .appendValue(ChronoField.SECOND_OF_MINUTE, 2)
                        .optionalEnd()
                    .optionalEnd()
                    .toFormatter(Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static final DateTimeFormatter WITH_MIDNIGHT =
            new DateTimeFormatterBuilder()
                    .append(FLEX)
                    .parseDefaulting(ChronoField.HOUR_OF_DAY, 0)
                    .parseDefaulting(ChronoField.MINUTE_OF_HOUR, 0)
                    .toFormatter(Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static final DateTimeFormatter[] DATE_FORMATS = {
            DateTimeFormatter.ISO_LOCAL_DATE,
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT)
    };

    public static void main(String[] args) {
        for (String text : new String[]{
                "2026-10-25", "2026-10-25T09:05",
                "2026-10-25T09:05:30", "2026-10-25T",
                "2026-10-25T09", "2026-10-25T09:05:",
                "2026-02-30", "2026-10-25T25:00"
        }) {
            inspect(text);
        }

        System.out.println("formatDate="
                + FLEX.format(LocalDate.of(2026, 10, 25)));
        System.out.println("formatDateTime="
                + FLEX.format(LocalDateTime.of(2026, 10, 25, 9, 5)));
        System.out.println("defaulted="
                + LocalDateTime.parse("2026-10-25", WITH_MIDNIGHT));

        System.out.println("iso=" + parseKnownDate("2026-10-25"));
        System.out.println("slash=" + parseKnownDate("25/10/2026"));
        try {
            parseKnownDate("10-25-2026");
        } catch (IllegalArgumentException e) {
            System.out.println("other=ERROR");
        }
    }

    private static void inspect(String text) {
        try {
            TemporalAccessor result = FLEX.parseBest(
                    text, LocalDateTime::from, LocalDate::from);
            String type = result instanceof LocalDateTime
                    ? "LocalDateTime" : "LocalDate";
            System.out.println(text + " -> " + type + " " + result);
        } catch (DateTimeParseException e) {
            System.out.println(text + " -> ERROR");
        }
    }

    private static LocalDate parseKnownDate(String text) {
        for (DateTimeFormatter format : DATE_FORMATS) {
            try {
                return LocalDate.parse(text, format);
            } catch (DateTimeParseException ignored) {
                // Try the next format in the explicit input contract.
            }
        }
        throw new IllegalArgumentException("unsupported date format");
    }
}
```

Compile and run:

```shell
javac OptionalDateInputDemo.java
java OptionalDateInputDemo
```

Expected output:

```text
2026-10-25 -> LocalDate 2026-10-25
2026-10-25T09:05 -> LocalDateTime 2026-10-25T09:05
2026-10-25T09:05:30 -> LocalDateTime 2026-10-25T09:05:30
2026-10-25T -> ERROR
2026-10-25T09 -> ERROR
2026-10-25T09:05: -> ERROR
2026-02-30 -> ERROR
2026-10-25T25:00 -> ERROR
formatDate=2026-10-25
formatDateTime=2026-10-25T09:05:00
defaulted=2026-10-25T00:00
iso=2026-10-25
slash=2026-10-25
other=ERROR
```

`ERROR` is a label printed by the program when rejecting input, not a literal Java exception message. `inspect` tests the date structure with optional time; `parseKnownDate` separately demonstrates trying two specified date syntaxes. They are two independent functions; not every string in the program is passed through both handlers.

February 30 and hour 25:00 are rejected because the formatter uses `ResolverStyle.STRICT`. Allowing a part to be absent does not mean the part that is present may contain invalid values.

## 8. Reformatting Does Not Preserve History of Omitted Parts

When parsing `2026-10-25T09:05`, the resulting `LocalDateTime` has seconds equal to 0. When formatted back with `FLEX`, the object has a seconds field, so the `:ss` group is printed as `:00`.

This explains the line:

```text
formatDateTime=2026-10-25T09:05:00
```

When **formatting**, an optional group is decided based on whether the object provides the required fields for the group. It does not check "whether the user previously typed the seconds field", nor does it automatically omit the group just because the seconds value is 0.

Conversely, `LocalDate` has no time fields, so the entire time group is omitted when formatting. If you want the output to never include seconds, choose an output formatter with only hours and minutes. If you want to preserve the original source notation, you must store the original string or metadata about which parts were present; date-time objects generally do not retain that history.

The ISO form shown in the `parseBest` output lines comes from the object's `toString()`, which has its own display rules. Do not infer from the brevity of `LocalDateTime.toString()` that `FLEX.format(...)` will print the exact same thing.

## 9. Common Mistakes and How to Self-Check

- Placing `T` or `:` outside the group so a separator remains required even though the fields are optional.
- Making hours and minutes independently optional, unintentionally allowing combinations the feature does not want to accept.
- Calling `LocalDateTime.parse` on a standalone date and assuming optional groups are broken, when the issue is missing fields for the target result type.
- Putting `LocalDate::from` first in `parseBest`, discarding the time from inputs that include time.
- Using a midnight default without agreeing on the meaning of "no time provided".
- Combining patterns in multiple `[]` pairs and thinking they act as mutually exclusive branches.
- Testing only valid inputs; failing to check truncated inputs such as a trailing `T` or `:`.

For practice, add `2026-10-25T09:05:00` and compare it with the input without seconds: both forms produce the same `LocalDateTime` value. Then reverse the query order in `parseBest` and observe the time part disappearing from the result. Finally, test `2026-10-25T09:05x` to confirm that trailing characters are still rejected when parsing the entire string.

References: [DateTimeFormatterBuilder — optionalStart, optionalEnd, appendOptional, and parseDefaulting](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) and [DateTimeFormatter — parseBest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parseBest(java.lang.CharSequence,java.time.temporal.TemporalQuery...)) in Java SE 21.
