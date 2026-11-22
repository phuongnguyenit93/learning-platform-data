# Composing Numeric Fields, Text Fields, and Fixed Literals

## 1. Viewing a Format as a Sequence of Meaningful Components

Suppose you need to present the date 25/10/2026 as `Sun | 25 October 2026`. The string contains both data taken from the date and fixed characters:

```text
Sun       |       25       October       2026
 |        |        |          |           |
day name  separator day number month name  year number
```

If you concatenate manually using `getDayOfMonth()` and month-name strings, you have to handle leading zeros, locale, ordering, and parsing back yourself. `DateTimeFormatterBuilder` lets you describe the structure once, then create a `DateTimeFormatter` to format and parse under the same contract.

The three foundational operations are:

| Operation | What gets appended | Example |
|---|---|---|
| `appendValue(...)` | Numeric value of a temporal field | Day `25`, month `10`, year `2026` |
| `appendText(...)` | Textual representation of a field | `Sun`, `October` |
| `appendLiteral(...)` | Fixed character or string | `" \| "`, `' '`, `'-'` |

The call order is the exact order of components in the output and input. The builder does not automatically rearrange them according to a default locale pattern.

## 2. Numeric Fields: Choosing the Right Field and Width

Commonly used fields come from `ChronoField`, such as `YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH`, `HOUR_OF_DAY`, and `MINUTE_OF_HOUR`.

Example of declaring components in a builder:

```java
new DateTimeFormatterBuilder()
        .appendValue(ChronoField.DAY_OF_MONTH, 2)
        .appendLiteral('/')
        .appendValue(ChronoField.MONTH_OF_YEAR, 2)
        .appendLiteral('/')
        .appendValue(ChronoField.YEAR, 4);
```

These are only structure-building calls; you need to call `toFormatter(...)` to obtain a usable formatter.

### Fixed Width and Leading Zeros

`appendValue(field, width)` uses a fixed width. When formatting, shorter values are left-padded with zeros: day 5 with width 2 becomes `05`. When parsing under the default strict text-reading mode, it requires the exact number of digits chosen.

The width is not a truncation command. If a value does not fit, formatting throws an error instead of keeping the last few digits. This overload also does not print a sign for negative values; therefore, `appendValue(YEAR, 4)` fits the 0000–9999 year range of the example, not every year that `LocalDate` can represent.

For wider or signed year fields, choose an appropriate overload such as `appendValue(field, minWidth, maxWidth, signStyle)`. Do not use width 4 and implicitly assume negative years or five-digit years will still be handled under the same contract.

`appendValue(field)` without a width produces an unpadded, variable-width number. Choose fixed or variable width based on the data you want to accept and emit, not just because a current example happens to have two digits.

### Concatenating Numbers Without Separators

To produce `20261025`, you can concatenate a 4-digit year, a 2-digit month, and a 2-digit day. Boundaries are determined by the width of each part. If adjacent fields all have variable widths, input easily becomes ambiguous; you need to design clear boundaries or width rules.

In the full example, all three fields are fixed-width so the reader can easily verify how `2026`, `10`, and `25` are split. The builder has a mechanism for handling adjacent numeric values in certain combinations, but you should not rely on guesswork when designing a new contract.

## 3. Text Fields: The Data Is Still a Date-Time Field

`appendText` does not insert a fixed label. It reads the field value and looks up the corresponding textual representation according to `Locale` and `TextStyle`.

```java
.appendText(ChronoField.DAY_OF_WEEK, TextStyle.SHORT)
.appendText(ChronoField.MONTH_OF_YEAR, TextStyle.FULL)
```

With English and the date in the example, the day-of-week field can display `Sun`, while the month field displays `October`.

| TextStyle | Intent | Example English month name |
|---|---|---|
| `FULL` | Full form | `January` |
| `SHORT` | Abbreviated form | `Jan` |
| `NARROW` | Very short form | `J` |

The narrow form does not necessarily distinguish all values: multiple months can share the initial letter `J`. Do not use it as a unique month code if unambiguous parsing is required.

The `*_STANDALONE` styles serve standalone name usage in languages that have grammatical differences compared to names appearing inside a full date. Do not equate "standalone" with "automatically capitalized".

Specify `Locale` explicitly via `toFormatter(Locale.ENGLISH)` or the locale you need. If left to the default, day/month names may vary depending on the host machine. Changing the locale changes text names; literals you wrote remain unchanged and are not automatically translated.

When parsing a string, the text must match the set of names and style that the formatter accepts. To make it case-insensitive, place `parseCaseInsensitive()` before the relevant parts. That does not replace the date-validation policy and does not automatically accept names from all languages.

## 4. Literals: What You Write Is Exactly What the Structure Has

`appendLiteral('-')` appends a single character; `appendLiteral(" | ")` appends the entire string consisting of a space, a `|` character, and a space.

A literal has two roles:

- When formatting, it is emitted verbatim.
- When parsing, the parser expects the corresponding text to appear at that position, according to the active text-matching policy.

The builder does not automatically insert spaces between two calls. If you want `25 October`, you must add `' '` between the day field and the month field; omitting it may produce `25October`.

You also need to distinguish a literal from a pattern:

```java
.appendLiteral("at")
```

This call inserts the literal text `at`. By contrast, `appendPattern("at")` treats the letters as pattern symbols and may be invalid; if you use a pattern to insert text, you must use pattern quoting syntax such as `appendPattern("'at'")`.

A literal containing a word such as `"tháng"` is always the exact word you supplied. It does not change to `month` when switching to `Locale.ENGLISH`. Therefore, choose between fixed text defined by the design and localized names managed by `appendText`.

## 5. Building the Formatter and Ensuring Sufficient Data

The call chain ends with `toFormatter(...)`, after which you can configure the field-resolution policy:

```java
DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .appendValue(ChronoField.DAY_OF_MONTH, 2)
        .appendLiteral('-')
        .appendText(ChronoField.MONTH_OF_YEAR, TextStyle.SHORT)
        .appendLiteral('-')
        .appendValue(ChronoField.YEAR, 4)
        .toFormatter(Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);
```

A builder is a mutable object used to construct the structure. A completed `DateTimeFormatter` is immutable and can be reused concurrently. Do not keep sharing a mutable builder across multiple threads instead of keeping the created formatter.

When formatting, the source object must have the required fields. `LocalDate` has day, month, year, and day-of-week; `LocalTime` does not have those fields. When parsing back into `LocalDate`, the input must also provide enough information to determine a date; a month name and a literal alone cannot produce a complete date.

Adding a day-of-week field adds verifiable data, not just decoration. If the string says `Mon` while the actual day-month-year is a Sunday, field resolution and cross-checking will report a conflict. Do not ignore the day-of-week name when using the same formatter to accept input.

## 6. Complete Runnable Program

Save the following code to `ComposedFormatterDemo.java`. The program uses Java 17 or later and requires no external libraries.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class ComposedFormatterDemo {
    private static final DateTimeFormatter LABEL =
            new DateTimeFormatterBuilder()
                    .appendText(ChronoField.DAY_OF_WEEK, TextStyle.SHORT)
                    .appendLiteral(" | ")
                    .appendValue(ChronoField.DAY_OF_MONTH, 2)
                    .appendLiteral(' ')
                    .appendText(ChronoField.MONTH_OF_YEAR, TextStyle.FULL)
                    .appendLiteral(' ')
                    .appendValue(ChronoField.YEAR, 4)
                    .toFormatter(Locale.ENGLISH)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static final DateTimeFormatter COMPACT =
            new DateTimeFormatterBuilder()
                    .appendValue(ChronoField.YEAR, 4)
                    .appendValue(ChronoField.MONTH_OF_YEAR, 2)
                    .appendValue(ChronoField.DAY_OF_MONTH, 2)
                    .toFormatter(Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 25);
        String text = LABEL.format(date);
        System.out.println("label=" + text);
        System.out.println("parsed=" + LocalDate.parse(text, LABEL));
        System.out.println("compact=" + COMPACT.format(date));
        System.out.println("compactParsed="
                + LocalDate.parse("20261025", COMPACT));

        inspect("Sun | 25 October 2026");
        inspect("Sun / 25 October 2026");
        inspect("Sun | 5 October 2026");
        inspect("Mon | 25 October 2026");
        inspect("Sun | 31 February 2026");
    }

    private static void inspect(String text) {
        try {
            System.out.println("input=" + text + " -> "
                    + LocalDate.parse(text, LABEL));
        } catch (DateTimeParseException e) {
            System.out.println("input=" + text + " -> ERROR");
        }
    }
}
```

Compile and run:

```shell
javac ComposedFormatterDemo.java
java ComposedFormatterDemo
```

Verified output:

```text
label=Sun | 25 October 2026
parsed=2026-10-25
compact=20261025
compactParsed=2026-10-25
input=Sun | 25 October 2026 -> 2026-10-25
input=Sun / 25 October 2026 -> ERROR
input=Sun | 5 October 2026 -> ERROR
input=Mon | 25 October 2026 -> ERROR
input=Sun | 31 February 2026 -> ERROR
```

The day/month names here use English; this output was verified on Zulu OpenJDK 24.0.2. Locale data may be updated between JDK releases. For output following a protocol that requires long-term character-for-character stability, specify the text contract explicitly rather than relying solely on the host's locale data.

`ERROR` is the program's label when catching `DateTimeParseException`. The causes deliberately isolated in the example:

1. `Sun / ...` has the wrong literal `" | "`.
2. `Sun | 5 ...` does not meet the 2-digit width of the day field.
3. `Mon | 25 October 2026` has a day-of-week that conflicts with the specific date.
4. `Sun | 31 February 2026` is not a real calendar date.

The example uses `ResolverStyle.STRICT` so nonexistent dates are not adjusted. Field structure, text-matching policy, and calendar validity work together; they do not replace one another.

## 7. Common Design Mistakes

| Mistake | How to handle it |
|---|---|
| Using `appendLiteral("October")` for every date | Use `appendText(MONTH_OF_YEAR, ...)` when it is a month name derived from the value |
| Concatenating two fields and expecting an automatic space | Add an explicit space literal |
| Using `MONTH_OF_YEAR` when you want minutes | Choose `MINUTE_OF_HOUR`; the builder follows the field you pass |
| Using `YEAR_OF_ERA` and missing the era under strict parsing | For standard ISO dates, choose `YEAR` or design sufficient era data |
| Using a 4-digit width and assuming all years are supported | Define the range or use an overload with appropriate width/sign rules |
| Changing the locale and expecting literals to be translated | Re-select literals per language at the design layer, or use a text field when it is temporal data |
| Formatting succeeds into a string, but parsing back fails | Check width, locale, order, literals, and whether the input provides enough fields to construct the target type |

For a simple structure, `ofPattern` can be shorter. A builder is useful when you need to see each component type clearly, apply specific numeric rules, or compose separately built parts. You do not need to replace every pattern with a builder; use the approach that makes the formatting contract easy to read and verify.

## 8. Practice on Your Own

Change the date in the program to `LocalDate.of(2026, 1, 5)`. For the `LABEL` formatter, predict:

```text
Mon | 05 January 2026
```

Explain why the day number has a leading `0`, the month uses the full word, and ` | ` does not change. Next, change the month's `TextStyle.FULL` to `TextStyle.SHORT` and rerun to observe the exact part that changes.

Finally, build a `dd/MM/uuuu` formatter using three `appendValue` calls and two `/` literals, then test both directions with `05/01/2026`. Try the string `5/1/2026` to confirm that fixed width is part of the input contract.

References: [DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html), [TextStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/TextStyle.html), and [ChronoField](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoField.html) in Java SE 21.
