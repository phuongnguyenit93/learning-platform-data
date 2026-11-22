# Argument Index, Flags, Width, Precision, and Conversion Syntax in Java

When using `String.format(...)`, `System.out.printf(...)`, or `Formatter`, we describe the appearance of data using a **format string**. A symbol beginning with `%` is called a *format specifier*: it selects an argument, determines alignment/character padding, limits precision, and chooses the display type. Understanding the exact order of components helps produce tables, messages, monetary amounts, dates, and reports with consistent results.

This lesson focuses on the **syntax of a format specifier in Java 17+**, specifically `argument index`, `flags`, `width`, `precision`, and `conversion`. These rules belong to `java.util.Formatter`; `String.format` and `printf` use the same syntax system.

## 1. Starting with a Format String

```java
String message = String.format("Hello %s, you have %d messages", "An", 3);
// "Hello An, you have 3 messages"
```

- `Hello `, the comma, and ` you have ` are literal text kept as-is.
- `%s` takes the corresponding argument and displays it as a string.
- `%d` takes an integer argument and displays it in decimal form.
- `String.format(...)` **returns** a `String`; `System.out.printf(...)` **writes** text to the output stream (and returns `PrintStream`).

For example, `String.format(Locale.US, "%,.2f", 12345.5)` returns `"12,345.50"`. `Locale.US` is specified intentionally to fix the decimal point and grouping separator in the result.

## 2. The Complete Syntax Formula

For regular conversions (strings, characters, integers, and floating-point numbers), the syntax is:

```text
%[argument_index$][flags][width][.precision]conversion
```

Square brackets in the **grammar description** line only mean "optional component"; **do not type square brackets** into an actual format string. The components are written in this exact order:

| Component | Meaning | Example |
| --- | --- | --- |
| `%` | Starts a format specifier. | `%s` |
| `argument_index$` | Selects the argument position, **1-based**; includes the `$` sign. | `%2$s` |
| `flags` | Flags controlling alignment, +/- signs, `0`-padding, digit grouping, etc. | `%-10s`, `%+d` |
| `width` | **Minimum width** of the output field. | `%10s` |
| `.precision` | Precision or length limit, depending on the conversion; includes a dot. | `%.2f`, `%.4s` |
| `conversion` | Indicates the conversion type and representation rules. | `s`, `d`, `f`, `x` |

**Reading the expression `%2$-12.4s` from left to right:**

1. `%`: starts the specifier.
2. `2$`: takes the **second argument**.
3. `-`: left-aligns.
4. `12`: field is **at least 12** characters wide.
5. `.4`: for `s`, takes **at most 4** characters of the string content.
6. `s`: converts the argument to a string.

For example, `String.format("%2$-12.4s", 99, "Notebook")` produces the text `"Note        "`: the four characters `Note` followed by eight spaces. If `-` is omitted, the spaces are placed **on the left**.

Note that there are **two special syntax branches**:

- Date/time: `%[argument_index$][flags][width]tX` or `...TX`, where `t`/`T` is followed by a **character specifying the time component**, such as `%1$tF`, `%1$tY`; there is no `.precision`.
- Symbols that take no arguments: `%%` (a literal percent sign) and `%n` (platform-specific newline character). These directives do not consume data arguments.

Not every flag, width, or precision is valid with every conversion; Java will throw an exception on an invalid combination rather than silently ignoring it.

## 3. Argument Index: Selecting and Reusing Arguments

### 3.1. No Index Specified: Taking Arguments in Order

```java
String value = String.format("%s has %d points", "Mai", 42);
// "Mai has 42 points"
```

In this example, `%s` uses the first argument, and `%d` uses the second argument.

### 3.2. Explicit Index: `1$`, `2$`...

```java
String value = String.format("%2$d points belong to %1$s", "Mai", 42);
// "42 points belong to Mai"
```

`%2$d` takes the second element of the argument list and displays it as an integer; `%1$s` takes the first element and displays it as a string. Indices **start from 1**, not 0. An argument can be referenced multiple times:

```java
String value = String.format("%1$s / %1$S", "java");
// "java / JAVA"
```

`%S` applies uppercase conversion (according to the locale). This is a way to use the same argument twice while formatting it differently.

### 3.3. The `<` Flag: Reusing the Previous Specifier's Argument

```java
String value = String.format("%s -> %<S", "java");
// "java -> JAVA"
```

In `%<S`, `<` **is not a comparison operator**: it is the flag for "reuse the argument of the immediately preceding specifier that had an argument", and `S` is the conversion. Using `%<s` when there is no preceding argument to reference will cause a `MissingFormatArgumentException`.

**Commonly confused rule:** explicit indices (`%2$s`) and default sequential indices (`%s`) are tracked separately; mixing both in one template makes it hard to read. Prefer using all explicit indices when reordering is needed, or all sequential specifiers when reordering is not needed. The `<` flag is useful for presenting **the same argument** in multiple ways, especially dates.

## 4. Flags: Changing How Values Are Displayed

Flags may appear consecutively **after the argument index and before width**. They have different meanings depending on the conversion.

| Flag | Typical Effect | Example and Meaning |
| --- | --- | --- |
| `-` | Left-aligns within a field with width; default is usually right-aligned. | `%-8s` |
| `+` | Always displays the numeric sign: `+` or `-`. | `%+d`, `%+.2f` |
| ` ` (space) | Reserves a blank space before positive numbers; negative numbers still have a minus sign. | `% d` |
| `0` | Pads with `0` digits on the left of the numeric part to fill width. | `%08d` |
| `,` | Groups digits according to locale, for appropriate numeric conversions. | `%,d`, `%,.2f` |
| `(` | Encloses negative numbers in parentheses instead of a minus sign for compatible numeric types. | `%(d`, `%(,.2f` |
| `#` | Alternate representation when supported by the conversion. | `%#x` produces prefix `0x` |
| `<` | Reuses the previous argument. | `%s %<S` |

With `Locale.US`:

```java
String a = String.format(Locale.US, "%08d", -42);      // "-0000042"
String b = String.format(Locale.US, "%+d", 42);        // "+42"
String c = String.format(Locale.US, "%,d", 1234567);  // "1,234,567"
String d = String.format(Locale.US, "%(,.2f", -1234.5);
// "(1,234.50)"
String e = String.format(Locale.US, "%#x", 255);      // "0xff"
```

**Be careful with flag combinations:** `-` (left-align) and `0` (zero-pad) cannot be used together in numeric conversions where both apply; `+` and the space flag also conflict. With regular `%s`, numeric flags like `0` or `,` are incompatible. Some flags only apply to certain conversions: for example, `,` can be used with `d` and several floating-point formats, but not as a grouping flag for `x`.

## 5. Width: **Minimum** Width

With `%8s` and the content `"AB"`, the result has six spaces followed by `AB`. With `%-8s`, the result is `AB` followed by six spaces:

```java
String right = String.format("|%8s|", "AB");  // "|      AB|"
String left  = String.format("|%-8s|", "AB"); // "|AB      |"
```

Width does not shorten a value that is already longer than the field:

```java
String value = String.format("|%3s|", "Hello");
// "|Hello|" (not truncated to 3 characters)
```

**Width is the character count of the resulting field, including plus/minus signs, numeric prefixes, and formatted separators when applicable.** When padding `0` for negative numbers, the zeros are inserted **after the minus sign**: `%08d` with `-42` produces `-0000042`.

Do not mistake `-` before width for a negative number. In `%-10s`, the `-` sign is the **left-alignment flag**, and `10` is still a positive width. Some flags require a width; for example, `%-s` has no width and is therefore invalid.

## 6. Precision: Different Between Strings and Numbers

Precision is written `.N`, where `N` is a non-negative integer. It is applied depending on the conversion:

| Conversion | Meaning of Precision | Example |
| --- | --- | --- |
| `s` / `S` (regular text) | **Maximum** number of characters displayed before applying width. | `%.3s` with `"abcdef"` → `"abc"` |
| `f` | Number of digits after the decimal point. | `%.2f` with `12.5` → `"12.50"` |
| `e` / `E` | Number of digits after the decimal point in scientific notation. | `%.2e` |
| `g` / `G` | Number of **significant digits** of the value after rounding. | `%.3g` |
| `d`, `x`, `c`, `tF` | **Precision is not supported**. | `%.2d` is invalid |

Examples combining width and precision:

```java
String a = String.format(Locale.US, "|%8.3s|", "abcdef");
// "|     abc|" — truncated to 3 characters then right-aligned in 8 positions

String b = String.format(Locale.US, "|%-8.3s|", "abcdef");
// "|abc     |" — truncated to 3 characters then left-aligned

String c = String.format(Locale.US, "|%8.2f|", 12.5);
// "|   12.50|" — rounded/displayed with 2 digits after decimal point,
// then padded with spaces to width 8
```

For binary floating-point numbers (`double`/`float`), rounding results at boundary values can be affected by floating-point storage. If dealing with monetary values requiring strict decimal precision, consider `BigDecimal` and business rounding rules; `%.2f` is only a **display** format and does not alter the original data.

## 7. Conversion: Choosing the Output Data Type

| Conversion | Common Value Types | Example / Meaning |
| --- | --- | --- |
| `s` / `S` | Any object, takes string representation; `S` converts to uppercase. | `%s`, `%S` |
| `b` / `B` | Boolean; `null` becomes `false`, any other non-null non-`Boolean` object becomes `true`. | `%b` |
| `h` / `H` | Hexadecimal form of hash code (not memory address). | `%h` |
| `c` / `C` | Valid Unicode character (e.g., `char`; or code point in `int`). | `%c` |
| `d` | Decimal integer. | `%d` |
| `o` | Octal integer. | `%o` |
| `x` / `X` | Hexadecimal integer, using lowercase/uppercase letters. | `%x` |
| `f` | Fixed-point decimal floating-point number. | `%.2f` |
| `e` / `E` | Floating-point number in scientific notation. | `%e` |
| `g` / `G` | General floating-point format by significant digits. | `%g` |
| `a` / `A` | Hexadecimal floating-point representation (suitable for `float`/`double`). | `%a` |
| `tX` / `TX` | Date/time, **where X is a date/time component character**, such as `F`, `Y`, `m`, `d`, `H`. | `%tF`, `%1$tY` |
| `%` in `%%` | Literal percent sign; takes no argument. | `100%%` → `100%` |
| `n` in `%n` | OS-specific newline; takes no argument. | `Line 1%nLine 2` |

**Type compatibility:** `%d` does not accept a `String` containing `"42"` instead of an integer; `%f` is for floating-point numbers such as `double`, `float`, and `BigDecimal`; `%c` does not accept a multi-character `String` instead of a single character. Incompatible conversions typically cause `IllegalFormatConversionException`.

Commonly used date formats (with `LocalDate` or a compatible `TemporalAccessor` value):

- `%tF`: ISO date in `yyyy-MM-dd` form.
- `%tY`: four-digit year; `%tm`: two-digit month; `%td`: two-digit day of month.
- `%tH`: hour (00–23); `%tM`: minute, **only used with values having hour/minute fields**, such as `LocalDateTime`.

Because `tF` consists of **two conversion characters** `t` and `F`, do not read `F` as a flag or width. To reuse the same date:

```java
LocalDate date = LocalDate.of(2026, 10, 23);
String value = String.format(Locale.US,
        "%1$td/%1$tm/%1$tY", date);
// "23/10/2026"
```

This is an illustrative snippet; it requires importing `java.time.LocalDate` and `java.util.Locale`.

## 8. Standalone Runnable Java 17+ Example

Save a file named `FormatSyntaxDemo.java` with the code:

```java
import java.time.LocalDate;
import java.util.Locale;

public class FormatSyntaxDemo {
    public static void main(String[] args) {
        String product = "Notebook";
        int quantity = 7;
        double price = 12.5;

        // 1-based argument index and reordering.
        System.out.println(String.format(Locale.US,
                "Name: %1$s; qty: %2$d", product, quantity));
        System.out.println(String.format(Locale.US,
                "Reordered: %2$d / %1$s", product, quantity));

        // Left alignment, string truncation, right alignment, floating-point formatting.
        System.out.println(String.format(Locale.US,
                "|%1$-12.4s|", product));
        System.out.println(String.format(Locale.US,
                "|%1$10.2f|", price));

        // Combining + and 0 flags with width, precision, and f conversion.
        System.out.println(String.format(Locale.US,
                "%1$+010.2f", price));

        System.out.println(String.format(Locale.US,
                "%,d", 1234567));
        System.out.println(String.format(Locale.US,
                "%#x", 255));

        // < repeats the previous specifier's argument; S converts to uppercase.
        System.out.println(String.format(Locale.US,
                "%1$s -> %<S", "java"));

        System.out.println(String.format(Locale.US,
                "%b", (Object) null));

        // Date/time conversion tF; no precision.
        System.out.println(String.format(Locale.US,
                "%tF", LocalDate.of(2026, 10, 23)));

        // %% is a literal percent; %n is a system newline.
        System.out.print(String.format(Locale.US,
                "100%% done%n"));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 FormatSyntaxDemo.java
java FormatSyntaxDemo
```

Exact output of the program:

```text
Name: Notebook; qty: 7
Reordered: 7 / Notebook
|Note        |
|     12.50|
+000012.50
1,234,567
0xff
java -> JAVA
false
2026-10-23
100% done
```

Points to observe: `%1$-12.4s` selects argument one, truncates `Notebook` to `Note`, then fills eight spaces on the right to reach width 12; `%1$10.2f` displays `12.50` and adds five spaces on the left; `%1$+010.2f` displays the `+` sign, pads zeros after the sign, and reaches total width 10. The spaces inside `|...|` in stdout are part of the result, not a formatting glitch.

## 9. Locale, Related APIs, and Escaping Characters

### 9.1. Locale Controls Part of Formatting

```java
double value = 12345.5;
String us = String.format(Locale.US, "%,.2f", value);
// "12,345.50"
String de = String.format(Locale.GERMANY, "%,.2f", value);
// "12.345,50"
```

When `Locale` is not passed, formatting uses the runtime environment's default formatting locale. Results can differ between a developer's machine and a deployment server. If output is data communicated between systems or tests requiring deterministic stdout, pass an explicit locale such as `Locale.US`. For user interfaces, choose a locale matching the appropriate language/region.

### 9.2. `String.format`, `formatted`, `printf`, and `Formatter`

- `String.format(Locale.US, "%d", 7)` produces the string `"7"`.
- `"%d".formatted(7)` also produces the string `"7"` (API available since Java 15, usable in Java 17+).
- `System.out.printf("%d%n", 7)` writes directly to the screen.
- `Formatter` allows formatting into an `Appendable`, such as `StringBuilder`, when you need control over where the result goes.

Specifier syntax is essentially shared across these APIs; the main difference is whether the method returns a string value or writes to a destination.

### 9.3. Distinguishing Percent Signs in Format Strings vs. Data

Inside a **format string** itself, to print a literal percent sign you must write `%%`. However, when data `"50%"` is passed as an argument for `%s`, **do not double** the percent sign inside the data:

```java
String result = String.format("Progress: %s", "50%");
// "Progress: 50%"

String another = String.format("Progress: 50%%");
// "Progress: 50%"
```

Do not use user-provided text directly as a **format string** when the goal is merely verbatim display, because `%` symbols in it can be parsed as format specifiers. Use a fixed template such as `"%s"` and pass that text as an argument.

## 10. Common Errors and How to Diagnose Them

| Invalid Template or Situation | Common Consequence | How to Fix |
| --- | --- | --- |
| `String.format("%d", "42")` | `IllegalFormatConversionException`: string is not an integer. | Parse to a number if appropriate, or use `%s` to display a string. |
| `String.format("%.2d", 42)` | `IllegalFormatPrecisionException`: integer `d` does not support precision. | Use numeric width/flag like `%04d` if zero-padding is needed. |
| `String.format("%-s", "A")` | `MissingFormatWidthException`: `-` requires a width. | Use e.g. `%-8s`. |
| `String.format("%2$s", "A")` | `MissingFormatArgumentException`: there is no second argument. | Check positions using 1-based indexing. |
| `String.format("%<s", "A")` | `MissingFormatArgumentException`: no previous argument to reuse. | Place a specifier with an argument before `%<s`. |
| `String.format("%q", "A")` | `UnknownFormatConversionException`: `q` is not a valid conversion. | Choose a conversion from the supported table. |
| Mixing `%s` and `%2$s` arbitrarily | Output may differ from expected order. | Pick one clear indexing style and verify argument order. |
| Assuming `%8.3s` means "take 8 characters, pad 3" | Misreading width/precision. | For `s`: take at most 3 characters, then pad to minimum width 8. |
| Assuming `%n` is the letter `n` or always equals `\n` | Confusion about platform-dependent newline characters. | Use `%n` for system-formatted output; `\n` when LF is strictly required. |

In practice, these exceptions belong to the `IllegalFormatException` family and usually appear only when the format string is parsed at runtime. Avoid building format strings dynamically if possible; if you must, validate inputs and test representative execution paths.

## 11. Procedure for Reading Any Specifier

When encountering an expression like `%3$-14.5S`, answer in sequence:

1. **Which argument?** `3$` takes the third argument.
2. **What flags?** `-` requests left alignment.
3. **How wide is width?** `14` is the minimum width.
4. **What is precision for this conversion?** `.5` for `S` means at most five characters.
5. **What conversion?** `S` converts the string to uppercase according to the locale.

When encountering `%1$+010.2f`, the answers are: first argument, always show sign, zero-pad, minimum width 10 characters, two digits after the decimal point, floating-point type `f`. When encountering `%1$tF`, read it as: first argument, date/time type `t` with suffix `F`, **no precision**.

## 12. Self-Practice

Given the argument `"abcdef"`, value `7`, and floating-point number `12.5`, predict:

```java
String a = String.format("|%1$8.3s|", "abcdef");
String b = String.format(Locale.US, "%1$04d", 7);
String c = String.format(Locale.US, "%1$+.1f", 12.5);
String d = String.format("%2$s-%1$s", "first", "second");
```

Answers: `a` is `"|     abc|"` (five spaces before `abc`), `b` is `"0007"`, `c` is `"+12.5"`, and `d` is `"second-first"`.

**Key takeaway:** read specifiers in the order **index → flags → width → precision → conversion**, while checking whether the conversion supports the requested components. For date/time, also handle the character following `t`/`T`; for `%%` and `%n`, no argument is consumed.

Official reference: [`java.util.Formatter` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html).
