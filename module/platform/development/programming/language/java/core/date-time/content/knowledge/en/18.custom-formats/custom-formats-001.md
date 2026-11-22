# `DateTimeFormatterBuilder` and When to Use It

## 1. From a Pattern to a Structured Rule

A format like `dd/MM/uuuu` usually only needs `DateTimeFormatter.ofPattern()`. However, suppose an input source has English month names in text, accepts both `jun` and `JUN`, still requires an uppercase `T`, may omit seconds, allows fractional seconds, and always requires a UTC offset. At this point, the decisions lie in individual parts of the format rather than just a single pattern string.

`DateTimeFormatterBuilder` lets you build rules from small components: numeric fields, fixed literals, localized text, optional sections, fractions, offsets, and parsing settings. The final result is still a `DateTimeFormatter` used with `parse()` or `format()`.

According to [Java SE 21 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html), the builder is a mutable object intended for the construction process within a single thread. Meanwhile, [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) is immutable and safe to share across threads.

You can visualize the lifecycle as follows:

```text
DateTimeFormatterBuilder
    append parsing/formatting rules sequentially
                ↓ toFormatter(locale)
DateTimeFormatter
    parse string → temporal object
    format object → string
```

The builder does not create date-time values immediately when `appendValue()` is called. Those calls only add rules to the formatter that will be produced.

## 2. When Should You Choose the Builder?

| Need | Suitable Way to Start |
| --- | --- |
| Parse/format standard built-in ISO formats | Use constants like `ISO_LOCAL_DATE`, `ISO_OFFSET_DATE_TIME` |
| A fixed, readable pattern like `dd/MM/uuuu HH:mm` | Use `ofPattern()` with an explicit `Locale` |
| Display dates according to local language/style | Consider `ofLocalizedDate()` or `ofLocalizedDateTime()` |
| Need to change case-sensitivity rules for one segment | Builder with `parseCaseInsensitive()`, then reset the mode |
| Need variable fractional digits or explicit field widths | Builder with `appendFraction()` / `appendValue()` |
| Need to provide default fields when genuinely missing | Builder with `parseDefaulting()` |
| Need to compose sub-formatters or custom lookup text | Builder with `append()` or `appendText()` |

Some optional sections can already be expressed using `[]` in a pattern. Therefore, having an optional section does not automatically mean you must use the builder. Choose the builder when the structure and specific conditions need to be clearly visible through named calls, or when a pattern cannot describe the requirement.

There is no guarantee that rewriting a simple pattern with multiple builder calls will make the program faster. The main benefit here is control and expressiveness of the rules.

## 3. Operation Groups to Recognize

| Operation | Role |
| --- | --- |
| `appendValue(field, width)` | Appends a numeric field with a fixed width under standard parsing |
| `appendLiteral(...)` | Appends a fixed character or text literal such as `-`, `:`, `T` |
| `appendText(field, textStyle)` | Appends the text representation of a field, such as a short month name |
| `appendPattern(pattern)` | Appends a familiar pattern segment to the builder |
| `append(formatter)` | Appends rules from an existing formatter |
| `optionalStart()` / `optionalEnd()` | Marks an entire group that may be absent |
| `appendFraction(field, min, max, decimalPoint)` | Controls fractional digits, digit count, and the decimal point |
| `appendOffsetId()` | Appends a UTC offset such as `+07:00` or `Z` |
| `appendZoneRegionId()` | Appends a region-based time-zone ID when the contract requires it |
| `parseDefaulting(field, value)` | Supplies a value for a field not yet present at that point |

These are the groups to help orient you when reading code, without needing to memorize the entire API. The order of calls is the exact order of components in the string. Parsing settings also affect subsequent sections, so placing them in the right position is part of the design.

## 4. Building a Formatter for a Specific Input Source

In this experiment, the input is specified as follows:

- Four-digit year, abbreviated English month name, two-digit day.
- Month names are case-insensitive.
- Between the date and time, there must be an uppercase `T`.
- Hours and minutes are required; the seconds group may be absent.
- When seconds are present, the fractional part can have up to 9 digits.
- A UTC offset is required because the target type is `OffsetDateTime`.

Two valid examples:

```text
2025-jun-10T09:15+07:00
2025-JUN-10T09:15:30.12+07:00
```

Save the program as `FormatterBuilderDemo.java`. The code uses Java 17 or later and requires no external libraries:

```java
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class FormatterBuilderDemo {
    private static final DateTimeFormatter INPUT = new DateTimeFormatterBuilder()
            .appendValue(ChronoField.YEAR, 4)
            .appendLiteral('-')
            .parseCaseInsensitive()
            .appendText(ChronoField.MONTH_OF_YEAR, TextStyle.SHORT)
            .parseCaseSensitive()
            .appendLiteral('-')
            .appendValue(ChronoField.DAY_OF_MONTH, 2)
            .appendLiteral('T')
            .appendPattern("HH:mm")
            .optionalStart()
                .appendLiteral(':')
                .appendValue(ChronoField.SECOND_OF_MINUTE, 2)
                .appendFraction(ChronoField.NANO_OF_SECOND, 0, 9, true)
            .optionalEnd()
            .appendOffsetId()
            .toFormatter(Locale.ENGLISH)
            .withResolverStyle(ResolverStyle.STRICT);

    private static void check(String text) {
        try {
            OffsetDateTime value = OffsetDateTime.parse(text, INPUT);
            System.out.println(text + " -> " + value);
            System.out.println("formatted -> " + INPUT.format(value));
        } catch (DateTimeParseException ex) {
            System.out.println(text + " -> DateTimeParseException");
        }
    }

    public static void main(String[] args) {
        check("2025-jun-10T09:15+07:00");
        check("2025-JUN-10T09:15:30.12+07:00");
        check("2025-Jun-10t09:15+07:00");
        check("2025-Jun-31T09:15+07:00");
        check("2025-Jun-10T09:15");

        DateTimeFormatter normalizedOutput = DateTimeFormatter
                .ofPattern("uuuu-MM-dd'T'HH:mm:ssXXX", Locale.ROOT);
        OffsetDateTime parsed = OffsetDateTime.parse(
                "2025-jun-10T09:15+07:00", INPUT);
        System.out.println("separate output -> "
                + parsed.format(normalizedOutput));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 FormatterBuilderDemo.java
java FormatterBuilderDemo
```

Output:

```text
2025-jun-10T09:15+07:00 -> 2025-06-10T09:15+07:00
formatted -> 2025-Jun-10T09:15:00+07:00
2025-JUN-10T09:15:30.12+07:00 -> 2025-06-10T09:15:30.120+07:00
formatted -> 2025-Jun-10T09:15:30.12+07:00
2025-Jun-10t09:15+07:00 -> DateTimeParseException
2025-Jun-31T09:15+07:00 -> DateTimeParseException
2025-Jun-10T09:15 -> DateTimeParseException
separate output -> 2025-06-10T09:15:00+07:00
```

## 5. Reading the Builder from Left to Right

### Numeric Fields and Fixed Literals

`appendValue(YEAR, 4)` sets the contract for a four-digit year; `appendValue(DAY_OF_MONTH, 2)` sets a two-digit day. This choice intentionally restricts how the source data is written, rather than allowing the full year range supported by `java.time`. If a system needs signed years or more digits, the width and sign rules must be redesigned accordingly.

`appendLiteral('-')` and `appendLiteral('T')` represent characters that must be present. `appendPattern("HH:mm")` shows that the builder and patterns can work together: there is no need to manually write out every field when a pattern segment is already clear. `HH` is the 24-hour clock hour, and `mm` is the minute; writing `MM` in the minute position would have a different meaning.

### Case Sensitivity and Locale

`parseCaseInsensitive()` is placed before the month name, and then `parseCaseSensitive()` is called to reset the rule for the subsequent parts. As a result, both `jun` and `JUN` are accepted, while a lowercase `t` cannot replace `T`. These settings are not scoped blocks that expire automatically after one call: you must explicitly reset them when needed.

`toFormatter(Locale.ENGLISH)` determines the language of the month names. Accepting multiple casing styles does not mean accepting month names in every language. When formatting back to a string, the month name follows the canonical form for the `Locale` and `TextStyle`, so inputs with different casing can all be formatted back as `Jun`.

### Optional Seconds Group and Fractions

`optionalStart()` opens a group containing the `:` separator, two-digit seconds, and fractional seconds. `optionalEnd()` closes the group before appending the offset. Because of this, omitting seconds does not make the offset optional as well.

`appendFraction(NANO_OF_SECOND, 0, 9, true)` represents the fractional part of a second. The argument `0` allows zero fractional digits, `9` is the maximum number of digits, and `true` tells this element to manage the decimal point. With this configuration, that separator is `.`. Do not append another fixed `.` literal before it if you want this element to manage the decimal point itself.

The string `.12` means 0.12 seconds, corresponding to 120,000,000 nanoseconds—not 12 nanoseconds. Therefore, the printed object line may show `.120`, while the demo's formatter outputs `.12`. Both representations have the same sub-second value.

The fraction sits after the seconds field inside the optional group, so it does not allow attaching a fraction directly to minutes in this format. The group structure determines which variants are accepted.

### Offsets and Valid Dates

`appendOffsetId()` is outside the optional group, so the offset is always required. The example missing `+07:00` fails. If you make the offset optional while still wanting to create an `OffsetDateTime`, you must also define where the offset comes from when it is absent; the optional marker alone does not produce that information.

`.withResolverStyle(ResolverStyle.STRICT)` is called on the resulting formatter to reject `2025-Jun-31`. This input matches the field syntax, but June does not have 31 days. Builder methods like `parseStrict()` / `parseLenient()` control syntax parsing; they do not replace the resolver style for validating dates. Similarly, case-insensitivity does not mean relaxing date validation.

## 6. Optional Sections on Parse Are Not Preserved Verbatim on Format

The input line without seconds is still formatted back with `:00`. The reason is that `OffsetDateTime` after parsing has its second field set to 0; when formatting that object, the optional group has enough information to be output. It does not remember that the group was omitted in the original string.

Therefore, the same formatter can be used for both parsing and formatting, but it does not guarantee verbatim reproduction of the input. Differences such as month-name casing, zero seconds, and the number of fractional digits may be normalized. If you need to keep the original text verbatim, you must store the raw string separately.

The program also uses a separate `normalizedOutput` for formatting. This is a clean approach when inputs have multiple variants but the output must have a stable form. The variable name simply refers to consistent output formatting; there is no special temporal-object normalization call here.

## 7. Application Usage and Common Pitfalls

**Build once, reuse the resulting formatter.** The example declares `INPUT` as `static final DateTimeFormatter`. Keep the builder within the initialization scope; do not share a builder that is still having rules appended across multiple threads. There is no need to rebuild the entire builder for every record.

**Close groups in the right place.** If you put `optionalEnd()` after `appendOffsetId()`, the offset also becomes part of the optional group. Calling `optionalEnd()` when no group is open is a configuration error. Write balanced open/close pairs so readers can inspect the structure easily.

**Do not confuse syntactic optionality with sufficient data for the target type.** A section may be absent according to the formatter, yet still be required to construct a `LocalDateTime`, `OffsetDateTime`, or `ZonedDateTime`. Choose the appropriate target type or provide supplementary rules. `parseDefaulting()` only supplies a value if the field is not yet present at that call site; it is typically placed after the parsing section that might provide the field, and should not be used to mask invalid data that is already present.

**Keep the input contract narrow enough.** If two unrelated formats use different field meanings or orders, do not treat chaining multiple optional sections as a universal format-selection mechanism. You can maintain separate formatters and classify inputs according to clear contracts, verifying them with both allowed and disallowed examples.

**Test for the right kinds of failure.** A mismatched string during parsing typically throws `DateTimeParseException`; an invalid builder configuration fails during construction. When formatting an object that lacks a required field, the format operation can also fail. Test both the parsing and formatting paths that the application actually uses.

Exercise: modify the formatter to require seconds by removing the `optionalStart()` / `optionalEnd()` pair around the seconds group. The input `2025-jun-10T09:15+07:00` should then be rejected, while the input with `:30.12` remains valid. Next, move `parseCaseSensitive()` down to after the `T` literal and predict that a lowercase `t` will also be accepted at that position. These two changes help verify that you understand group scope and setting scope in the builder.
