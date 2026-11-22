# ResolverStyle.STRICT, SMART, and LENIENT

## 1. Parsing numbers does not guarantee a valid date

The string `2023-02-29` has a very clear year-month-day structure: the year is 2023, the month is 2, and the day of month is 29. However, 2023 is not a leap year, so that date does not exist in the ISO calendar. The application must decide whether to **reject** it, **adjust it to the end of the month**, or **let the overflow roll into the next month**.

`ResolverStyle` is the policy choice Java uses when combining parsed fields into a date/time. Understanding this option helps avoid situations where the parser returns a valid value that differs from the date the user actually entered.

The three options are:

| Mode | Intent | For `2023-02-29` in the ISO calendar |
|---|---|---|
| `STRICT` | Only create a date when the fields are genuinely valid together | Throws an error |
| `SMART` | Apply sensible per-field adjustments | Becomes `2023-02-28` |
| `LENIENT` | Allow calculations with out-of-range values according to field rules | Becomes `2023-03-01` |

You should not interpret `SMART` as "always matches what the user meant" or `LENIENT` as "accepts any string". They are different contracts that must be chosen based on the feature being built.

## 2. Two phases of parsing a string

To see where `ResolverStyle` intervenes, split the process into two phases:

```text
Input string
    |
    v
1. Parse text according to pattern
   "2023-02-29" -> YEAR=2023, MONTH_OF_YEAR=2, DAY_OF_MONTH=29
    |
    v
2. Resolve and validate fields according to ResolverStyle
    |
    +--> Valid LocalDate
    |
    +--> DateTimeParseException
```

**Phase 1** deals with characters, separators, field widths, month names, and the components present in the pattern. **Phase 2** resolves relationships between fields: how many days that month has, whether the year is a leap year, and whether an hour past 24 rolls over to the next day.

`DateTimeFormatter.withResolverStyle(...)` configures phase 2. It does not automatically turn `/` into `-`, remove whitespace, translate month names to another language, or relax all digit-count rules in phase 1.

This explains why a formatter with pattern `uuuu-MM-dd` using `LENIENT` can still reject `2023/02/09` or `2023-2-9`.

## 3. Configuring explicitly

Example declaration inside a Java method:

```java
DateTimeFormatter base = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT);
DateTimeFormatter strict = base.withResolverStyle(ResolverStyle.STRICT);
DateTimeFormatter smart = base.withResolverStyle(ResolverStyle.SMART);
DateTimeFormatter lenient = base.withResolverStyle(ResolverStyle.LENIENT);
```

`DateTimeFormatter` is immutable; each call to `withResolverStyle` returns a new formatter. Calling it and discarding the return value does not modify `base`. Created formatters can be reused without synchronization locks.

A formatter created with `ofPattern` uses `SMART` by default. Meanwhile, common ISO constants such as `DateTimeFormatter.ISO_LOCAL_DATE` use `STRICT`; do not assume every formatter has the same default. You can inspect the current setting using `getResolverStyle()`.

Use it as follows:

```java
LocalDate valid = LocalDate.parse("2024-02-29", strict);
```

The snippets above require imports from `java.time`, `java.time.format`, and `java.util`. The full program is in section 7.

## 4. STRICT: preserve the meaning of the entered date or fail

In the ISO calendar, `STRICT` checks each field's value and its validity when combined. `2024-02-29` is valid; `2023-02-29` is invalid. It also rejects month 15 or day 0.

For user-supplied inputs such as birth dates, contract signing dates, or invoice dates, silently shifting a nonexistent date to another date often corrupts the meaning of the data. If the feature requires the exact date entered, `STRICT` is the right choice.

### Why does STRICT with yyyy fail even for a real date?

In the pattern `yyyy-MM-dd`, the letter `y` represents **year-of-era** (`YEAR_OF_ERA`). To strictly resolve a date, the era (`ERA`) is also required; those three fields alone may not be enough to construct a `LocalDate`.

For ordinary ISO calendar dates, use `uuuu-MM-dd`: `u` represents the proleptic year directly (`YEAR`), so no era inference is needed. For example:

```java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

If the requirement genuinely needs a pattern with year-of-era, ensure sufficient data is provided such as the era or an appropriate default value. Do not work around the error by dropping `STRICT` when strict validation is actually required. Also do not use `YYYY`: that is week-based year, not the calendar year in question.

## 5. SMART: bounded, per-field adjustment

For the year-month-day triplet in the ISO calendar, `SMART` requires the day of month to be within the range 1–31. If the number is within that range but the specific month does not have that day, it adjusts to the last day of the month.

For example:

- `2023-02-29` becomes `2023-02-28`.
- `2023-04-31` becomes `2023-04-30`.
- `2023-02-32` still fails because 32 is outside the 1–31 range.
- `2023-15-10` still fails because month 15 is invalid.

Thus, `SMART` is not a mode that rolls every out-of-range value into the next larger unit. You must check the rules of the field being used rather than assuming "smart" means automatically fixing all input errors.

Another example is the hour `24:00`: when parsing both date and time, `SMART` accepts this exact end-of-day mark and converts it to `00:00` of the next day. However, `24:30` still fails in `SMART`. The full runnable example below demonstrates this difference directly.

Only use such adjustments when the feature permits them. If you need to notify the user that the entered date does not exist, `SMART` can mask the error signal you need.

## 6. LENIENT: calculate out-of-range values instead of just checking bounds

For ISO year-month-day, you can think of `LENIENT` as starting at the beginning of the year, adding `(month - 1)` months, and then adding `(day - 1)` days. Any overflow is added or subtracted according to the calendar.

Example `2023-02-32`:

```text
2023-01-01
    + 1 month
= 2023-02-01
    + 31 days
= 2023-03-04
```

Other examples:

| String | LENIENT result | Interpretation |
|---|---|---|
| `2023-02-29` | `2023-03-01` | 1 day after February 28 |
| `2023-15-10` | `2024-03-10` | Month 15 rolls into the next year |
| `2023-02-00` | `2023-01-31` | Day 0 is one day before the start of the month |

These results can be useful when the source format is designed to use out-of-range values as an offset calculation, or when importing legacy data with agreed-upon adjustment rules. They should not be used as a way to "ignore errors" for ordinary user input.

`LENIENT` does not guarantee success either. The text must still match the pattern; the data may also be missing fields, contradictory, or exceed the representable range of the date/time type.

## 7. Runnable comparison program

Save the following code into `ResolverStyleDemo.java`. The code requires Java 17 or later and needs no external libraries.

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ResolverStyleDemo {
    public static void main(String[] args) {
        DateTimeFormatter base =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);
        System.out.println("default=" + base.getResolverStyle());
        String[] dates = {
                "2023-02-29", "2024-02-29", "2023-02-32",
                "2023-15-10", "2023-02-00"
        };

        for (String text : dates) {
            for (ResolverStyle style : ResolverStyle.values()) {
                System.out.println(style + " " + text + " -> "
                        + parseDate(text, base.withResolverStyle(style)));
            }
        }

        DateTimeFormatter strict = base.withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter yearOfEra = DateTimeFormatter
                .ofPattern("yyyy-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        System.out.println("yyyy=" + parseDate("2024-02-29", yearOfEra));
        System.out.println("uuuu=" + parseDate("2024-02-29", strict));
        System.out.println("width=" + parseDate("2023-2-9",
                base.withResolverStyle(ResolverStyle.LENIENT)));
        System.out.println("separator=" + parseDate("2023/02/09",
                base.withResolverStyle(ResolverStyle.LENIENT)));

        DateTimeFormatter dateTime = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm", Locale.ROOT);
        for (ResolverStyle style : ResolverStyle.values()) {
            for (String time : new String[]{"24:00", "24:30"}) {
                String text = "2023-02-28 " + time;
                try {
                    LocalDateTime value = LocalDateTime.parse(
                            text, dateTime.withResolverStyle(style));
                    System.out.println(style + " " + time + " -> " + value);
                } catch (DateTimeParseException e) {
                    System.out.println(style + " " + time + " -> ERROR");
                }
            }
        }
    }

    static String parseDate(String text, DateTimeFormatter formatter) {
        try {
            return LocalDate.parse(text, formatter).toString();
        } catch (DateTimeParseException e) {
            return "ERROR";
        }
    }
}
```

Compile and run:

```shell
javac ResolverStyleDemo.java
java ResolverStyleDemo
```

Expected output:

```text
default=SMART
STRICT 2023-02-29 -> ERROR
SMART 2023-02-29 -> 2023-02-28
LENIENT 2023-02-29 -> 2023-03-01
STRICT 2024-02-29 -> 2024-02-29
SMART 2024-02-29 -> 2024-02-29
LENIENT 2024-02-29 -> 2024-02-29
STRICT 2023-02-32 -> ERROR
SMART 2023-02-32 -> ERROR
LENIENT 2023-02-32 -> 2023-03-04
STRICT 2023-15-10 -> ERROR
SMART 2023-15-10 -> ERROR
LENIENT 2023-15-10 -> 2024-03-10
STRICT 2023-02-00 -> ERROR
SMART 2023-02-00 -> ERROR
LENIENT 2023-02-00 -> 2023-01-31
yyyy=ERROR
uuuu=2024-02-29
width=ERROR
separator=ERROR
STRICT 24:00 -> ERROR
STRICT 24:30 -> ERROR
SMART 24:00 -> 2023-03-01T00:00
SMART 24:30 -> ERROR
LENIENT 24:00 -> 2023-03-01T00:00
LENIENT 24:30 -> 2023-03-01T00:30
```

In the program, `ERROR` is a label printed by the example code when catching `DateTimeParseException`, not Java's literal exception message. Do not compare the full exception message in the example, because the goal is to compare parsing outcomes.

The `width` and `separator` lines show that `LENIENT` alone does not relax the text pattern. The final lines use `LocalDateTime` so you can observe the date rolling over to the next day; if you only extract `LocalTime`, you will not see the full impact on the date.

## 8. Distinguishing parseStrict/parseLenient from ResolverStyle

The names look similar, but these APIs control different things:

| API | Phase affected | Key question |
|---|---|---|
| `DateTimeFormatterBuilder.parseStrict()` / `parseLenient()` | Parsing text into fields | How flexible is the parser when matching digits, signs, and widths? |
| `DateTimeFormatter.withResolverStyle(...)` | Resolving fields into a date/time | How should a field set like month 2, day 29 be handled? |
| `parseCaseInsensitive()` / `parseCaseSensitive()` | Matching text with letters | Is matching case-sensitive or case-insensitive? |

The builder's default is strict text parsing; the default for a formatter created with `ofPattern` is `SMART` field resolution. These two do not conflict because they belong to different phases.

If the input design allows one- or two-digit months/days, use an appropriate pattern or builder setting for the text-parsing phase. Do not enable `ResolverStyle.LENIENT` to solve a purely formatting-related requirement.

Conversely, calling `parseStrict()` on the builder without choosing an appropriate resolver policy is not enough to ensure that February 29 of a non-leap year is rejected when creating a `LocalDate`.

## 9. Parsing policy does not replace business rules

A calendar-valid date can still be invalid for the feature being implemented. For example, an expiration date must be after the issue date, or a birth date cannot be in the future. `STRICT` has no knowledge of those rules.

The data intake pipeline should be clear:

1. Define the accepted text pattern and locale.
2. Choose `ResolverStyle` according to the feature's adjustment/rejection policy.
3. Parse into the appropriate date/time type.
4. Validate business rules on the resulting value.
5. If `SMART` or `LENIENT` adjustments occur, decide whether the user needs to be shown the adjusted result.

When an error occurs, preserve the source string to report context. You can use `DateTimeParseException.getParsedString()` and `getErrorIndex()` to aid diagnostics, but you should not interpret every error index as a complete business error message. For instance, a missing-era error in a `yyyy` pattern is different from the user entering an invalid date.

Do not automatically try `STRICT`, then `SMART`, then `LENIENT` until something succeeds unless that is an intentionally designed rule. Such fallback attempts can turn a nonexistent date into a different date without the caller realizing it.

## 10. Practice on your own

With the same `uuuu-MM-dd` pattern, predict the three results for `2023-04-31`, then run it to verify:

```text
STRICT  -> ERROR
SMART   -> 2023-04-30
LENIENT -> 2023-05-01
```

Next, change to the valid date `2023-04-30`: all three modes produce `2023-04-30`. Explain why differences between modes do not necessarily appear for every input.

Finally, try discarding the return value of `withResolverStyle(STRICT)`, then print `base.getResolverStyle()`. The result is still `SMART`, which verifies the immutability of the formatter.

References: [ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html), [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html), and [DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) in Java SE 21.
