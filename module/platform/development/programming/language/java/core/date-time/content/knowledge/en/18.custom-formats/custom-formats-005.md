# Width, Sign, and Fractional Seconds

## 1. Three Distinct Decisions in a Numeric Field

When exchanging dates and times as text, having “the same value” is not enough to guarantee that the string conforms to the contract. Day 7 may need to be written as `07`; a negative year needs to keep the `-` sign; a fractional second of `.1` must be interpreted as 100 milliseconds rather than 1 nanosecond. Choosing the wrong rule can cause the string to be rejected or lose information on a format-and-parse round trip.

With `DateTimeFormatterBuilder`, you need to distinguish:

- **Width:** how many digits are there, and are leading zeros added?
- **Sign:** should `+` or `-` be accepted/printed, or are only non-negative numbers allowed?
- **Fraction:** what proportion of a second do the digits represent, and at what precision?

`appendValue()`, `SignStyle`, `padNext()`, and `appendFraction()` address different aspects. You should not use a chain of manual character-insertion operations in place of properly specifying each rule.

## 2. Field Width and Padding

### Fixed or Variable Number of Digits

Common builder call forms:

| Builder call | Meaning to recognize |
| --- | --- |
| `appendValue(DAY_OF_MONTH)` | Prints the numeric value in its natural width, such as `7` |
| `appendValue(DAY_OF_MONTH, 2)` | Uses two digits and pads with a leading zero, such as `07` |
| `appendValue(YEAR, 4, 10, signStyle)` | Independently controls the minimum width, maximum width, and sign rule |

In the default strict parsing mode, a fixed width requires the exact number of digits; the `minWidth`/`maxWidth` form accepts a digit count within the chosen range. The sign is not counted toward the number of digits: `-0007` has four digits and one sign character.

When formatting, the minimum width may add leading zeros, while exceeding the maximum width may throw an error; do not assume `appendValue(field, 2)` truncates a three-digit value down to two. Width also does not replace range validation: parsing two digits for a month does not prove that month 13 exists.

### Space Padding vs. Zero Padding

`padNext(3, ' ')` applies to the next element added, making its formatted output occupy three characters. In the program below, day 7 is formatted as `[  7]`, whereas the two-digit numeric field is formatted as `[07]`. The brackets only help make the spaces visible; they are not part of the formatter.

Padding is calculated over the element's formatted representation, which may include a sign if the element prints one. By contrast, the width of `appendValue()` refers to the digits. `padNext()` does not automatically make all remaining fields share the same width; it must be placed at the exact position that needs padding.

For concatenated numeric formats without separators—such as year–month–day written together—you must control field boundaries. The builder has rules for reserving digits for adjacent fixed-width numeric fields in suitable configurations; do not assume that every combination of variable-width fields can be split unambiguously. When the contract uses a fixed four-digit year, two-digit month, and two-digit day, specify those widths directly.

## 3. `SignStyle`: Sign as Part of the Contract

[Java SE 21 — SignStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/SignStyle.html) describes the ways to control the sign. The following table focuses on formatting; the program will verify this with years `7`, `-7`, and `10000` using a minimum width of 4:

| Sign style | Formatting behavior |
| --- | --- |
| `NORMAL` | Only prints a sign when the number is negative |
| `ALWAYS` | Always prints a sign; non-negative numbers use `+` |
| `NEVER` | Never prints a sign, even for negative inputs; only prints the absolute value |
| `NOT_NEGATIVE` | Disallows negative values when formatting |
| `EXCEEDS_PAD` | Negative numbers have `-`; positive numbers have `+` when the digit count exceeds the minimum width |

Two options that are easy to confuse are `NEVER` and `NOT_NEGATIVE`. `NEVER` can turn year `-7` into the string `0007`, losing the sign. `NOT_NEGATIVE` rejects negative years instead of silently dropping the sign.

In strict parsing mode, `ALWAYS` requires a sign; `NORMAL` allows a minus sign but does not accept a plus sign; `NEVER` and `NOT_NEGATIVE` do not accept a sign. With `EXCEEDS_PAD`, the plus sign is tied to the width-exceeding rule; you cannot simply prepend `+` to any number and expect every formatter to accept it. Lenient parsing modes may change the sign-acceptance rules, so you must verify the exact configuration in use.

`SignStyle` here applies to the sign of a numeric field, not to configuring how time-zone offsets like `+07:00` are parsed. Offsets require dedicated elements such as `appendOffset()` or `appendOffsetId()`.

## 4. Fractional Seconds Are a Proportion, Not a Raw Nanosecond Count

With `NANO_OF_SECOND`, the fractional range is from 0 to 999,999,999 nanoseconds. The decimal position determines the meaning of the string:

| Fraction in string | Fractional second value | Nanoseconds |
| --- | --- | ---: |
| `.1` | One tenth of a second | 100,000,000 |
| `.01` | One hundredth of a second | 10,000,000 |
| `.001` | One millisecond | 1,000,000 |
| `.000000001` | One nanosecond | 1 |

That is why you cannot replace `appendFraction(NANO_OF_SECOND, ...)` with `appendValue(NANO_OF_SECOND)` when the contract calls for a decimal fraction of a second. The integer value `1` nanosecond requires `.000000001`, not `.1`.

Calling `appendFraction(NANO_OF_SECOND, minWidth, maxWidth, decimalPoint)` selects the fraction width and decimal-point handling. `decimalPoint=true` uses the symbol from `DecimalStyle`; the program uses `DecimalStyle.STANDARD` to explicitly specify `.`. If `false` is chosen, the element does not add or parse a decimal point itself, so the contract must handle that separator elsewhere.

For example, using `0, 9, true` allows no fraction at all, up to 9 digits, and omits trailing zeros when formatting unless required to be kept by the minimum width. If exactly three digits are needed, you can choose `3, 3, true` or the `SSS` pattern with a dot placed appropriately.

### Dropping Digits Does Not Mean Rounding

The pattern `HH:mm:ss.SSS` outputs a nanosecond value of `123456789` as `.123`. Lower-order digits are dropped from the string; there is no rounding step up to `.124`. Parsing that string back yields only `123000000` nanoseconds. The original object is unchanged, but the intermediate string has lost precision.

This non-rounding rule for fractions is stated in [Java SE 21 — appendFraction()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html#appendFraction(java.time.temporal.TemporalField,int,int,boolean)). If business logic requires rounding time values, you must define and perform a separate rounding step before formatting, including how to handle cases where the fractional part rolls over into the next second.

## 5. Complete Runnable Program

Save the following code to `WidthSignFractionDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class WidthSignFractionDemo {
    private static void checkTime(String text, DateTimeFormatter formatter) {
        try {
            LocalTime time = LocalTime.parse(text, formatter);
            System.out.println(text + " -> nano=" + time.getNano());
        } catch (DateTimeParseException ex) {
            System.out.println(text + " -> DateTimeParseException");
        }
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 6, 7);
        DateTimeFormatter zeroFilled = new DateTimeFormatterBuilder()
                .appendValue(ChronoField.DAY_OF_MONTH, 2)
                .toFormatter(Locale.ROOT);
        DateTimeFormatter spacePadded = new DateTimeFormatterBuilder()
                .padNext(3, ' ')
                .appendValue(ChronoField.DAY_OF_MONTH)
                .toFormatter(Locale.ROOT);
        System.out.println("zero=[" + date.format(zeroFilled) + "]");
        System.out.println("pad =[" + date.format(spacePadded) + "]");

        for (SignStyle style : SignStyle.values()) {
            DateTimeFormatter year = new DateTimeFormatterBuilder()
                    .appendValue(ChronoField.YEAR, 4, 10, style)
                    .toFormatter(Locale.ROOT);
            String negative;
            try {
                negative = year.format(Year.of(-7));
            } catch (DateTimeException ex) {
                negative = "DateTimeException";
            }
            System.out.println(style + " -> " + year.format(Year.of(7))
                    + " | " + negative + " | " + year.format(Year.of(10000)));
        }

        LocalTime sample = LocalTime.of(8, 9, 10, 123_456_789);
        DateTimeFormatter millis = DateTimeFormatter
                .ofPattern("HH:mm:ss.SSS", Locale.ROOT);
        System.out.println("three digits = " + sample.format(millis));
        System.out.println("nano after reparse = "
                + LocalTime.parse(sample.format(millis), millis).getNano());

        DateTimeFormatter fraction = new DateTimeFormatterBuilder()
                .appendPattern("HH:mm:ss")
                .appendFraction(ChronoField.NANO_OF_SECOND, 0, 9, true)
                .toFormatter(Locale.ROOT)
                .withDecimalStyle(DecimalStyle.STANDARD)
                .withResolverStyle(ResolverStyle.STRICT);
        checkTime("08:09:10", fraction);
        checkTime("08:09:10.1", fraction);
        checkTime("08:09:10.", fraction);
        checkTime("08:09:10.123456789", fraction);
        checkTime("08:09:10.1234567890", fraction);
        System.out.println("zero fraction = "
                + LocalTime.of(8, 9, 10).format(fraction));
        System.out.println("trimmed fraction = "
                + LocalTime.of(8, 9, 10, 120_000_000).format(fraction));

        DateTimeFormatter optionalNonEmptyFraction = new DateTimeFormatterBuilder()
                .appendPattern("HH:mm:ss")
                .optionalStart()
                    .appendFraction(ChronoField.NANO_OF_SECOND, 1, 9, true)
                .optionalEnd()
                .toFormatter(Locale.ROOT)
                .withDecimalStyle(DecimalStyle.STANDARD)
                .withResolverStyle(ResolverStyle.STRICT);
        System.out.println("optional non-empty fraction:");
        checkTime("08:09:10", optionalNonEmptyFraction);
        checkTime("08:09:10.1", optionalNonEmptyFraction);
        checkTime("08:09:10.", optionalNonEmptyFraction);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 WidthSignFractionDemo.java
java WidthSignFractionDemo
```

Output:

```text
zero=[07]
pad =[  7]
NORMAL -> 0007 | -0007 | 10000
ALWAYS -> +0007 | -0007 | +10000
NEVER -> 0007 | 0007 | 10000
NOT_NEGATIVE -> 0007 | DateTimeException | 10000
EXCEEDS_PAD -> 0007 | -0007 | +10000
three digits = 08:09:10.123
nano after reparse = 123000000
08:09:10 -> nano=0
08:09:10.1 -> nano=100000000
08:09:10. -> nano=0
08:09:10.123456789 -> nano=123456789
08:09:10.1234567890 -> DateTimeParseException
zero fraction = 08:09:10
trimmed fraction = 08:09:10.12
optional non-empty fraction:
08:09:10 -> nano=0
08:09:10.1 -> nano=100000000
08:09:10. -> DateTimeParseException
```

Each sign-style line shows the results for year 7, year -7, and year 10000, respectively. `DateTimeException` is recorded by the test helper when `NOT_NEGATIVE` refuses to format a negative year. The parse-error lines likewise print only the exception name for easy comparison of results, not a value returned by the library in place of a time.

## 6. Optional Fraction That Must Not Be Empty After the Dot

The result `08:09:10. -> nano=0` shows that a minimum width of 0 can accept a decimal point with no trailing digits. If the contract requires **either no fraction at all, or between 1 and 9 digits**, wrap `appendFraction(..., 1, 9, true)` in an optional section, as shown in `optionalNonEmptyFraction` in the program.

This structure has three verified properties:

- A string without a dot is still parsed, with nanoseconds set to 0.
- With a dot and at least one digit, the fractional part is parsed.
- A trailing dot alone is rejected because the fractional section fails to complete, leaving extra characters that cause parsing of the entire string to fail.

Do not simply change `minWidth` from 0 to 1 without adding an optional section if you still want to accept inputs that have no fraction at all. Doing so makes the fraction mandatory at that position.

## 7. Applying This Correctly to Parsing and Formatting

**Choose precision from the data contract.** If the output only retains milliseconds, understand that sub-millisecond nanoseconds will not survive a format–parse round trip. If nanoseconds must be preserved, use a formatter that allows up to 9 digits and test the entire data pipeline.

**Do not treat trailing zeros as higher source precision.** The strings `.1`, `.10`, and `.100` represent the same time value. After parsing, `LocalTime` does not remember whether the source had one or three digits. If the original digit count carries meaning about measurement precision, store that information separately.

**Parsing and resolving are two separate layers.** The builder examples use the default strict parsing mode; `withResolverStyle(STRICT)` controls how parsed fields are resolved into a time. It is not the sole setting that governs width, sign, or fractional digit count. If `parseLenient()` was enabled earlier, you must review the parsing rules rather than looking only at `ResolverStyle`.

**Do not use string slicing to handle over-wide fields.** Truncating a year or a sign can alter the value; truncating a fraction can lose precision. The formatter should explicitly specify what is permitted, and the application should make an explicit decision if it wants to reduce precision.

Exercise: given a time with `999999999` nanoseconds, predict that the pattern `HH:mm:ss.SSS` will output `.999` without rolling over the second. Then change the fraction formatter to `3, 3, true` and verify that an input with `.1` does not satisfy the exact three-digit requirement in strict parsing mode, whereas `.100` does and produces `100000000` nanoseconds.
