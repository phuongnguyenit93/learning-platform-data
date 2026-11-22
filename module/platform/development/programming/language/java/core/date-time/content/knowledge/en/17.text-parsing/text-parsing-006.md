# Distinguishing Case-Insensitive Parsing from Strict Date Resolution

## 1. Flexible Month Name Input Does Not Mean Accepting Non-Existent Dates

Suppose a form accepts dates in the pattern `dd-MMM-uuuu`, where `MMM` is the abbreviated English month name. Users might enter `28-Feb-2023`, `28-FEB-2023`, or `28-feb-2023`. You want to accept all three variations while still rejecting `29-FEB-2023`, because the year 2023 does not have a February 29.

These are **two independent conditions**:

- When recognizing the month name, does case sensitivity matter?
- After reading the year, month, and day, do they form a valid date?

In Java, you can relax the first condition while keeping the second condition strict. The appropriate configuration is `DateTimeFormatterBuilder.parseCaseInsensitive()` combined with `DateTimeFormatter.withResolverStyle(ResolverStyle.STRICT)`.

Do not lower the date validation level just to accept uppercase month names. Also, do not assume that choosing `STRICT` forces every letter in the input text to match exact casing.

## 2. Two Parsing Steps and Three Control Groups

A formatter reads a string in two main steps:

```text
"28-fEb-2023"
       |
       v
Step 1: Match text against the pattern
        read day 28, month name fEb, year 2023
        recognize fEb as month 2 via Locale and case policy
       |
       v
Step 2: Resolve the fields
        is year 2023 + month 2 + day 28 valid?
       |
       v
LocalDate: 2023-02-28
```

In the first step, there are two separate option groups: case policy and text-form parsing strictness. These are also distinct from the date-resolution policy in the second step.

| Configuration | What does it control? | What does it NOT replace? |
|---|---|---|
| `parseCaseInsensitive()` / `parseCaseSensitive()` | Case matching in subsequent parts of the parser | Does not check leap years or the number of days in a month |
| `parseStrict()` / `parseLenient()` on the builder | Flexibility when reading numbers, signs, and widths per parser component | Does not replace `ResolverStyle` |
| `withResolverStyle(STRICT/SMART/LENIENT)` | Combining and validating parsed fields into a date/time | Does not select the language or case policy |

APIs with `Strict` or `Lenient` in their names can be confusing, but they operate at different stages. The goal of "case-insensitive month names with valid date checking" does not require `parseLenient()` or `ResolverStyle.LENIENT`.

## 3. Creating the Appropriate Formatter

The following declaration can be placed inside a Java method:

```java
DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .parseCaseInsensitive()
        .appendPattern("dd-MMM-uuuu")
        .toFormatter(Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);
```

Step-by-step breakdown:

1. `parseCaseInsensitive()` switches the policy for subsequently appended components to case-insensitive.
2. `appendPattern` adds the day, abbreviated month name, and year structure.
3. `toFormatter(Locale.ENGLISH)` specifies the English month name set to recognize.
4. `withResolverStyle(STRICT)` requires the fields to combine into an actually existing date.

`Locale.ENGLISH` is an important part: case-insensitivity does not mean accepting every language. `FEB` can match an English month name; a French month name will not automatically be translated to English just because this option is enabled.

For ISO calendar dates, `uuuu` is used in the example. `yyyy` is `YEAR_OF_ERA`; without era data, strict parsing may lack enough fields to construct a `LocalDate`. Using the right year field helps avoid mistaking a date-model error for a casing error.

The resulting formatter is immutable and can be shared. `withResolverStyle` returns a new formatter, so you must use its return value. The builder is a mutable object, so use it to assemble the configuration and keep the finished `DateTimeFormatter` for reuse.

## 4. Comparing Along Two Axes Instead of a Single "Strictness" Level

With the English pattern `dd-MMM-uuuu`, consider three configurations:

| Input | Case-sensitive + STRICT | Case-insensitive + STRICT | Case-insensitive + SMART |
|---|---|---|---|
| `28-Feb-2023` | `2023-02-28` | `2023-02-28` | `2023-02-28` |
| `28-FEB-2023` | Month name match error | `2023-02-28` | `2023-02-28` |
| `29-FEB-2023` | Month name match error | Non-existent date error | `2023-02-28` |
| `29-feb-2024` | Month name match error | `2024-02-29` | `2024-02-29` |

In the `29-FEB-2023` row, the case-insensitive configuration correctly recognized February. However, under `STRICT`, it still rejected the day combination for a non-leap year. When switching only the field resolution policy to `SMART`, day 29 of February in that year was adjusted to the last day of the month.

This adjustment has nothing to do with writing `FEB`, `Feb`, or `feb`: it is a decision made in the field-resolution step. If the form requires users to enter an existing date, choosing `SMART` to "make input easier" can cause dates to be silently altered.

### parseStrict() does not automatically make dates strict

By default, the builder parses text in strict and case-sensitive mode. However, the formatter returned by `toFormatter(...)` defaults to `SMART` field resolution.

Therefore, the following snippet can still adjust `29-Feb-2023` to `2023-02-28`:

```java
DateTimeFormatter textStrictOnly = new DateTimeFormatterBuilder()
        .parseStrict()
        .appendPattern("dd-MMM-uuuu")
        .toFormatter(Locale.ENGLISH);
```

`parseStrict()` here applies to how text is parsed; it does not implicitly call `withResolverStyle(STRICT)`. The two defaults may seem contradictory, but they belong to two different steps.

## 5. Call Placement and Scope of the Case Policy

Calls to `parseCaseInsensitive()` and `parseCaseSensitive()` affect components appended **after** that call. They can be toggled mid-way on the builder.

For example, if you want flexible month names but an exact ` END` suffix:

```java
DateTimeFormatter mixed = new DateTimeFormatterBuilder()
        .parseCaseInsensitive()
        .appendPattern("dd-MMM-uuuu")
        .parseCaseSensitive()
        .appendLiteral(" END")
        .toFormatter(Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);
```

`28-feb-2023 END` is accepted, while `28-feb-2023 end` is rejected. The space before `END` is part of the literal string and must still be present. Switching modes does not make whitespace or delimiters optional.

If you only call `parseCaseInsensitive()` after appending the entire date pattern, it does not retroactively change the policy for already-added components. Place the setting before the text parts it should govern; for simple patterns, placing it right before `appendPattern` makes the scope easy to verify.

This option only affects **parsing strings**. It does not cause `format()` to print month names in lowercase or uppercase. If you want to change how output is displayed, configure formatting separately rather than inferring it from the input case policy.

## 6. Complete Runnable Program

Save the file `CaseAndDateStrictnessDemo.java` below. The program uses Java 17 or later and requires no external libraries.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class CaseAndDateStrictnessDemo {
    public static void main(String[] args) {
        DateTimeFormatter sensitiveStrict = new DateTimeFormatterBuilder()
                .appendPattern("dd-MMM-uuuu")
                .toFormatter(Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter insensitiveStrict = new DateTimeFormatterBuilder()
                .parseCaseInsensitive()
                .appendPattern("dd-MMM-uuuu")
                .toFormatter(Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter insensitiveSmart =
                insensitiveStrict.withResolverStyle(ResolverStyle.SMART);

        show("sensitive-strict", "28-Feb-2023", sensitiveStrict);
        show("sensitive-strict", "28-FEB-2023", sensitiveStrict);
        show("insensitive-strict", "28-FEB-2023", insensitiveStrict);
        show("insensitive-strict", "28-fEb-2023", insensitiveStrict);
        show("insensitive-strict", "29-FEB-2023", insensitiveStrict);
        show("insensitive-smart", "29-FEB-2023", insensitiveSmart);
        show("insensitive-strict", "29-feb-2024", insensitiveStrict);
        show("insensitive-strict", "28/Feb/2023", insensitiveStrict);
        show("insensitive-strict", "28-Feb-2023x", insensitiveStrict);

        DateTimeFormatter textStrictOnly = new DateTimeFormatterBuilder()
                .parseStrict()
                .appendPattern("dd-MMM-uuuu")
                .toFormatter(Locale.ENGLISH);
        System.out.println("builder-default="
                + textStrictOnly.getResolverStyle());
        show("parseStrict-only", "29-Feb-2023", textStrictOnly);

        DateTimeFormatter mixed = new DateTimeFormatterBuilder()
                .parseCaseInsensitive()
                .appendPattern("dd-MMM-uuuu")
                .parseCaseSensitive()
                .appendLiteral(" END")
                .toFormatter(Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);
        show("mixed", "28-feb-2023 END", mixed);
        show("mixed", "28-feb-2023 end", mixed);
    }

    static void show(String label, String text, DateTimeFormatter formatter) {
        try {
            LocalDate date = LocalDate.parse(text, formatter);
            System.out.println(label + " | " + text + " -> " + date);
        } catch (DateTimeParseException e) {
            System.out.println(label + " | " + text + " -> ERROR");
        }
    }
}
```

Compile and run in the directory containing the file:

```shell
javac CaseAndDateStrictnessDemo.java
java CaseAndDateStrictnessDemo
```

Expected output:

```text
sensitive-strict | 28-Feb-2023 -> 2023-02-28
sensitive-strict | 28-FEB-2023 -> ERROR
insensitive-strict | 28-FEB-2023 -> 2023-02-28
insensitive-strict | 28-fEb-2023 -> 2023-02-28
insensitive-strict | 29-FEB-2023 -> ERROR
insensitive-smart | 29-FEB-2023 -> 2023-02-28
insensitive-strict | 29-feb-2024 -> 2024-02-29
insensitive-strict | 28/Feb/2023 -> ERROR
insensitive-strict | 28-Feb-2023x -> ERROR
builder-default=SMART
parseStrict-only | 29-Feb-2023 -> 2023-02-28
mixed | 28-feb-2023 END -> 2023-02-28
mixed | 28-feb-2023 end -> ERROR
```

`ERROR` is a label printed by the program when catching `DateTimeParseException`, not Java's literal error message. The program tests both text-recognition errors and non-existent date errors; you should not classify these two errors as the same just because they share the same label.

The `28/Feb/2023` line still fails because the delimiter does not match the pattern. The line with a trailing `x` fails because `LocalDate.parse(text, formatter)` requires consuming the entire string; trailing characters are not ignored just because the parser is case-insensitive.

## 7. What Not to Infer from parseCaseInsensitive

- **Does not strip diacritics.** Case-insensitivity is not accent-insensitive or fuzzy matching.
- **Does not fix typos.** A misspelled month name will not become a valid month name.
- **Does not translate languages.** Recognized names still depend on the chosen `Locale` and pattern.
- **Does not strip whitespace or change delimiters.** The string must still match the formatter's structure.
- **Does not choose a leap-year policy.** Accepting or adjusting dates depends on field resolution.
- **Does not replace business validation.** An existing calendar date may still violate business rules such as "issue date cannot be in the future."

You do not need to convert the entire string to uppercase or lowercase to achieve this goal. Manual case conversion can affect parts that must remain unchanged, depend on the default locale's rules, and alter the original input string needed for error reporting. Configuring the parser expresses exactly which parts are allowed to be flexible while preserving the user's original input.

If whitespace normalization is needed, that is a separate decision at the input-handling layer. Explicitly decide whether to allow it rather than assuming it is an effect of `parseCaseInsensitive`.

## 8. Self-Check and Application

When building a date parser that includes month names, determine three separate answers:

1. Which language do the month names belong to, and should they be full or abbreviated?
2. Is letter case mandatory in each specific part?
3. Should non-existent dates be rejected, or is there an agreed-upon adjustment policy?

To practice, add the following inputs to the program before checking the predictions:

| Input | With insensitiveStrict | Reason |
|---|---|---|
| `31-APR-2023` | Error | April does not have 31 days |
| `30-aPr-2023` | `2023-04-30` | Recognized month name and valid date |
| `29-FEB-2024` | `2024-02-29` | Leap year |

Then try removing only `.withResolverStyle(ResolverStyle.STRICT)` when creating the case-insensitive formatter. Check `getResolverStyle()` and observe what happens with `31-APR-2023`: the month name is still parsed flexibly, but the date policy has reverted to the `SMART` default.

References: [DateTimeFormatterBuilder — parseCaseInsensitive, parseCaseSensitive, and parseStrict](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html), [ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html), and [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) in Java SE 21.
