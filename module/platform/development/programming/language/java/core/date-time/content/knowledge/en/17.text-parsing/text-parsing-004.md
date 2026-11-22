# Validating Invalid Dates and Differences Between Resolver Styles

## 1. Should an Invalid Input Date Be Rejected or Adjusted?

Suppose a user enters `2025-02-31` for a delivery date. The string has four digits for the year, two digits for the month, and two digits for the day; however, February 2025 does not have a 31st day. If the program accepts this string and saves it as February 28 or March 3, the data has changed from what the user entered.

In `java.time`, how such date–month fields are handled depends on the **resolver style**, `ResolverStyle`. There are three options: `STRICT`, `SMART`, and `LENIENT`. Choosing a style means choosing the data-handling rule, not just choosing how friendly the error message is.

Two questions need to be separated:

1. Does the string match the syntax that the formatter accepts?
2. Do the parsed numbers combine into a valid date, or into which date are they adjusted?

According to [Java SE 21 — ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html), parsing the text and resolving the fields are two separate phases; `ResolverStyle` controls the resolution phase. Therefore, switching to `LENIENT` does not mean every malformed string will be accepted.

## 2. Distinguishing Syntax Errors from Nonexistent Dates

With the pattern `uuuu-MM-dd`, consider the following inputs:

| Input | Issue to Consider |
| --- | --- |
| `2025/02/28` | Separator does not match the pattern |
| `2025-2-28` | Month part does not have the width required by the pattern |
| `2025-02-29` | Format is valid, but 2025 is not a leap year |
| `2025-04-31` | Format is valid, but April only has 30 days |
| `2025-13-10` | Month is outside the normal range |
| `2024-02-29` | Valid date in the ISO calendar |

A regular expression that only checks the shape—such as four digits, a `-` sign, and two digits—is not enough to determine whether a date exists. The day limit depends on both the month and the year. Even checking `1 <= day <= 31` fails to catch April 31.

In this article, the result is parsed into a `LocalDate` using the ISO calendar. Do not generalize these end-of-month details to all calendar systems or to every combination of date fields.

## 3. Three Modes for Handling Year–Month–Day

### `STRICT`: Requires the Date to Actually Exist

`STRICT` is appropriate when the purpose of the operation is to validate the entered date as-is. For example, `2025-02-29` must fail rather than be corrected; `2024-02-29` must succeed. In addition to the month being in the range 1–12 and the day being in the normal range, the year–month–day combination must be valid.

If an incorrect birth date, invoice date, or appointment date is entered and the business requirement is to report an error so the user can re-enter it, explicitly configure this mode. `STRICT` itself does not enforce rules such as "no appointments in the past": a date may exist on the calendar yet still be disallowed by business logic.

### `SMART`: May Clamp the Day to the End of the Month

For the year, month, and day fields of the ISO calendar, `SMART` can accept a day in the range 1–31 that exceeds the last day of the month and select the last day of that month instead. These resolution rules are described in [Java SE 21 — IsoChronology.resolveDate()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/IsoChronology.html#resolveDate(java.util.Map,java.time.format.ResolverStyle)).

The examples in this article show:

```text
2025-02-29 → 2025-02-28
2025-02-31 → 2025-02-28
2025-04-31 → 2025-04-30
```

Do not think of `SMART` as "accept any number and fix it": month 13, day 0, or day 32 are still rejected under this resolution behavior. The key takeaway when evaluating data is that **a successful parse may involve changing the date**.

### `LENIENT`: Allows Out-of-Range Values to Roll Over

With the same year–month–day form, `LENIENT` treats the month and day values as offsets. You can think of it as starting from January 1 of the parsed year, adding `month - 1` months, and then adding `day - 1` days.

For example, `2025-02-31` corresponds to February 1, 2025 plus 30 days, resulting in `2025-03-03`. Month 13 of 2025 rolls over into January 2026. Day 0 of January 2025 steps back to the last day of December 2024.

Only use this behavior when the data source intentionally represents overflow offsets or the application genuinely permits such adjustments. It does not prove that the input string described a valid date in the ordinary sense. Nor does `LENIENT` guarantee success every time: syntax errors, missing fields, or values outside the representable range can still cause failures.

## 4. Runnable Experiment: Same Input, Three Results

Save the following code to `InvalidDateModesDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class InvalidDateModesDemo {
    private static String parse(String text, DateTimeFormatter formatter) {
        try {
            return LocalDate.parse(text, formatter).toString();
        } catch (DateTimeParseException ex) {
            return "ERROR";
        }
    }

    public static void main(String[] args) {
        DateTimeFormatter base = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT);
        System.out.println("pattern default = " + base.getResolverStyle());
        System.out.println("ISO default = "
                + DateTimeFormatter.ISO_LOCAL_DATE.getResolverStyle());

        String[] inputs = {
            "2024-02-29", "2025-02-29", "2025-02-31",
            "2025-04-31", "2025-02-32", "2025-13-10",
            "2025-00-10", "2025-01-00", "2025-2-03"
        };
        System.out.println("input | STRICT | SMART | LENIENT");
        for (String input : inputs) {
            System.out.println(input + " | "
                    + parse(input, base.withResolverStyle(ResolverStyle.STRICT))
                    + " | "
                    + parse(input, base.withResolverStyle(ResolverStyle.SMART))
                    + " | "
                    + parse(input, base.withResolverStyle(ResolverStyle.LENIENT)));
        }

        DateTimeFormatter yearOfEra = DateTimeFormatter
                .ofPattern("yyyy-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        System.out.println("yyyy strict = " + parse("2025-02-28", yearOfEra));
        System.out.println("uuuu strict = " + parse("2025-02-28",
                base.withResolverStyle(ResolverStyle.STRICT)));
        System.out.println("ISO invalid = "
                + parse("2025-02-29", DateTimeFormatter.ISO_LOCAL_DATE));
    }
}
```

Compile and run in the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 InvalidDateModesDemo.java
java InvalidDateModesDemo
```

Output:

```text
pattern default = SMART
ISO default = STRICT
input | STRICT | SMART | LENIENT
2024-02-29 | 2024-02-29 | 2024-02-29 | 2024-02-29
2025-02-29 | ERROR | 2025-02-28 | 2025-03-01
2025-02-31 | ERROR | 2025-02-28 | 2025-03-03
2025-04-31 | ERROR | 2025-04-30 | 2025-05-01
2025-02-32 | ERROR | ERROR | 2025-03-04
2025-13-10 | ERROR | ERROR | 2026-01-10
2025-00-10 | ERROR | ERROR | 2024-12-10
2025-01-00 | ERROR | ERROR | 2024-12-31
2025-2-03 | ERROR | ERROR | ERROR
yyyy strict = ERROR
uuuu strict = 2025-02-28
ISO invalid = ERROR
```

`ERROR` is a string returned by the helper method in the example when it catches `DateTimeParseException`, not a result from the library. This helper makes it easy to compare the matrix; in application code, you should preserve or convert the error into a meaningful input validation result rather than continuing to treat `ERROR` as a valid date.

Observe three key rows:

- `2025-02-31`: `SMART` stops at the end of February, whereas `LENIENT` moves into March. The two styles do not adjust dates the same way.
- `2025-02-32`: even `SMART` rejects this, showing that the 1–31 range check is distinct from each month's actual day limit.
- `2025-2-03`: all three fail because the syntax parser for the pattern in use requires a two-digit month. Changing `ResolverStyle` alone does not relax this rule.

## 5. Two Pitfalls That Cause Unexpected Validation Results

### Not Every Formatter Defaults to `STRICT`

The first two lines of the program show that a formatter created with `ofPattern("uuuu-MM-dd", Locale.ROOT)` defaults to `SMART`, whereas `ISO_LOCAL_DATE` is `STRICT`. Consequently, the following two expressions handle invalid dates differently even though both appear to parse the same year–month–day format:

```java
// Illustrated inside a method; java.time and java.time.format classes are imported.
LocalDate.parse("2025-02-29"); // DateTimeParseException
LocalDate.parse("2025-02-29",
        DateTimeFormatter.ofPattern("uuuu-MM-dd")); // 2025-02-28
```

When using a custom pattern to validate user-entered dates, explicitly specify `.withResolverStyle(ResolverStyle.STRICT)` instead of assuming the default.

`DateTimeFormatter` is immutable. `withResolverStyle()` returns the resulting formatter; calling it does not modify the existing instance. You must assign or use the returned value:

```java
DateTimeFormatter input = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", java.util.Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

### `yyyy` and `uuuu` Have Different Meanings

In patterns, `u` represents the year directly, whereas `y` represents the year-of-era. With `yyyy-MM-dd` and `STRICT`, the string `2025-02-28` does not provide an era; therefore, the example fails to construct a `LocalDate` even though February 28, 2025 is a real date. Switching to `uuuu-MM-dd` properly addresses parsing ISO years in this context.

So if you enable `STRICT` and see every date rejected, check the pattern and any missing fields before concluding that the mode is too strict. If the input genuinely includes an era, describe the era in the formatter instead of changing the meaning of the data. Also do not use `YYYY` in place of `uuuu`: `Y` is the week-based year.

## 6. Do Not Mix Validation Layers

A clear date input pipeline can follow this sequence:

```text
Determine whether the input is required
              ↓
Parse according to the pattern and consume the entire string
              ↓
Resolve into a LocalDate using the chosen style
              ↓
Check business constraints on the resulting date
```

For example, a booking application needs to reject both `2025-02-31` and dates outside the booking window. `STRICT` handles the first requirement; `isBefore()`/`isAfter()` comparisons on the parsed date handle the second. There is no need to reimplement leap-year logic or a table of days per month.

Calling `LocalDate.of(year, month, day)` directly also requires the date to exist and does not accept a `ResolverStyle` parameter. The styles discussed in this article belong to resolving data parsed by a formatter; they are not a global switch that makes every date-creation method lenient.

Settings such as `DateTimeFormatterBuilder.parseLenient()` or `parseStrict()` control syntax parsing for the corresponding part of the builder. They differ from `withResolverStyle()`, which controls field resolution. If you need to accept either one- or two-digit months, design the appropriate parsing rule; do not expect `ResolverStyle.LENIENT` to alter the `MM` pattern.

## 7. Applying and Re-verifying the Decision

When the requirement is to validate an entered date as-is, configure `STRICT` and catch `DateTimeParseException` at the input boundary to prompt for correction. If using `SMART` or `LENIENT`, understand that the resulting value may differ from the input; any decision to adjust dates should come from the data source or business requirements.

Do not use the approach "parse with `LENIENT`, no error means the date is valid" for a form that needs to detect invalid dates. Nor should you parse and compare `toString()` with the original string as a catch-all check: the output format may differ from the input format. Choose the style and format contract upfront.

For parse errors, the exception's literal message is useful for diagnostics but should not drive program control flow. Nonexistent dates, missing fields caused by a `yyyy` pattern, and wrong separators can all manifest as `DateTimeParseException`; inspect the input context and configuration to fix the actual root cause.

Exercise: predict the three styles for `2024-02-30`. `STRICT` rejects it; `SMART` produces `2024-02-29`; `LENIENT` produces `2024-03-01`. Then try `2025-04-00`: the first two styles reject it, while `LENIENT` produces `2025-03-31`. Being able to explain these two cases means you have distinguished preserving the entered date, clamping to the end of the month, and rolling over the excess.
