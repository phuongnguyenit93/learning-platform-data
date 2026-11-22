# Formatting Numbers, Strings, Newlines, and the % Sign in `printf()` (Java 17+)

## 1. What is `printf()` used for?

In Java, `System.out.printf(...)` writes formatted text to the standard `stdout` stream. Instead of manually concatenating multiple strings, you write a **format string** containing specifiers starting with `%`, and then pass the corresponding values.

```java
System.out.printf("Name: %s, age: %d%n", "An", 20);
```

The printed line is `Name: An, age: 20` followed by a newline. `%s` formats a string or object, `%d` formats a decimal integer, and `%n` is the platform-dependent line separator.

Comparison of methods:

| Method | Role | Automatically adds a newline? |
| --- | --- | --- |
| `System.out.print(value)` | Prints a value directly | No |
| `System.out.println(value)` | Prints a value then moves to a new line | Yes |
| `System.out.printf(format, args...)` | Prints according to a template with conversions/flags/width/precision | **No**, unless the template includes `%n` or a newline character |
| `String.format(format, args...)` | Creates and **returns** a formatted string for further use | Does not print to the console |

`printf()` returns the `PrintStream` itself so calls can be chained; in basic I/O lessons, you normally only need to care about the content it prints.

## 2. Structure of a format specifier

Common general form:

```text
%[argument_index$][flags][width][.precision]conversion
```

Parts in square brackets are optional; this is a syntax description, not a Java expression to paste and run.

- `argument_index$`: selects the argument at a specific 1-based position. For example, `%2$s` selects the second argument and formats it with `%s`.
- `flags`: specify alignment, sign, zero-padding, digit grouping, etc. Certain flags are only valid with specific conversions.
- `width`: the **minimum width** of the output field, measured in characters according to Formatter rules. If the value is longer, it is not automatically truncated.
- `.precision`: meaning depends on the type: `%.2f` means two digits after the decimal point; `%.4s` keeps at most four characters from the string according to how Formatter handles it.
- `conversion`: a character indicating the type of value to print: `d`, `f`, `s`, `x`, `c`, etc.

For example, `%8.2f`: prints a floating-point number with two decimal places, a minimum field width of eight characters, right-aligned by default. `%-8.2f`: same width, but left-aligned. `%08.2f`: pads with `0` on the left (when the `0` flag is valid for that format type).

## 3. Essential specifiers to remember

| Specifier | Used with | Example value | Result |
| --- | --- | --- | --- |
| `%d` | Decimal integer (compatible `byte`, `short`, `int`, `long`, `BigInteger`) | `42` | `42` |
| `%x` / `%X` | Hexadecimal integer, lowercase/uppercase | `26` | `1a` / `1A` |
| `%o` | Octal integer | `26` | `32` |
| `%f` | Decimal floating-point (`float`, `double`, `BigDecimal`) | `12.5` | `12.500000` when using `Locale.ROOT` |
| `%.2f` | Floating-point number, two digits after the decimal point | `12.5` | `12.50` |
| `%e` | Floating-point number in scientific notation | `12.5` | `1.250000e+01` |
| `%s` | String/object; uses an appropriate string representation | `"Java"` | `Java` |
| `%S` | Uppercase string according to the appropriate locale | `"java"` | `JAVA` |
| `%c` | Character or valid Unicode code point in an appropriate integer type | `'A'` | `A` |
| `%b` | Boolean value or other objects | `true` | `true` |
| `%%` | **Literal** percent sign | No argument needed | `%` |
| `%n` | Platform-specific line separator | No argument needed | Newline |

**Type note:** `%d` does not automatically convert the string `"42"` into a number, and `%f` does not automatically accept every integer type. Provide the matching data type. If you want to print an `int` as a floating-point number with two decimal places, convert it intentionally, for example `System.out.printf("%.2f%n", (double) 42);`.

With `%b`, the `Boolean` type uses its `true/false` value, a `null` argument yields `false`, and any non-`null` object that is not a `Boolean` prints as `true`. Therefore, `%b` does **not** mean Java automatically turns arbitrary data into a business-logic truthiness check.

## 4. Runnable example: numbers, strings, and the % sign

Create **`PrintfDemo.java`**:

```java
import java.util.Locale;

public class PrintfDemo {
    public static void main(String[] args) {
        System.out.printf(Locale.ROOT,
                "so=%d, hex=%x, oct=%o%n", 26, 26, 26);
        System.out.printf(Locale.ROOT,
                "thap-phan=%.2f, khoa-hoc=%.2e%n", 12.5, 12.5);
        System.out.printf(Locale.ROOT,
                "can-phai=[%6d], can-trai=[%-6d]%n", 42, 42);
        System.out.printf(Locale.ROOT,
                "them-zero=[%05d], them-dau=[%+d]%n", 42, 42);
        System.out.printf(Locale.ROOT,
                "nhom=[%,d]%n", 1234567);
        System.out.printf(Locale.ROOT,
                "chuoi=[%s], rut-gon=[%.4s], viet-hoa=[%S]%n",
                "Java", "language", "java");
        System.out.printf(Locale.ROOT,
                "ti-le=%.1f%%%n", 12.5);
        System.out.printf(Locale.ROOT,
                "doi-cho: %2$s (%1$d)%n", 7, "items");
    }
}
```

In the directory containing the file, using **JDK 17+** (PowerShell, CMD, or bash). Create the `out` directory if it does not already exist:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out PrintfDemo.java
java -cp out PrintfDemo
```

**Exact stdout** (spaces inside square brackets are an intentional part of the output):

```text
so=26, hex=1a, oct=32
thap-phan=12.50, khoa-hoc=1.25e+01
can-phai=[    42], can-trai=[42    ]
them-zero=[00042], them-dau=[+42]
nhom=[1,234,567]
chuoi=[Java], rut-gon=[lang], viet-hoa=[JAVA]
ti-le=12.5%
doi-cho: items (7)
```

Explanation:

1. `%d`, `%x`, and `%o` all receive the value `26` but display it in decimal, hexadecimal, and octal respectively.
2. `%.2f` keeps two digits after the decimal point; `%.2e` uses scientific notation with two decimal digits in the significand.
3. `%6d` creates a field at least six characters wide for `42`: four spaces **before** it. `%-6d` adds four spaces **after** it.
4. `%05d` pads with zeros to reach width five; `%+d` displays `+` for positive numbers. `%,d` enables thousands grouping according to `Locale.ROOT`.
5. `%.4s` truncates `language` to `lang`; `%S` prints `java` as `JAVA`.
6. `%.1f%%%n` consists of **three specifiers in sequence**: `%.1f` consumes `12.5`, `%%` prints a single `%`, and `%n` prints a newline. They are not a single `%%%` specifier.
7. `%2$s` takes the second argument (`"items"`), and `%1$d` takes the first argument (`7`). These are **1-based argument indices**, unlike Java's 0-based array indices.

Specifying `Locale.ROOT` ensures the examples above use `.` as the decimal separator and consistent grouping rules. If no locale is passed, `printf()` uses the default locale of the Java environment, which may display `,` as the decimal separator in some regions.

## 5. `%n`, `\n`, `print()`, and `println()`

An important point: **`printf()` does not automatically move to a new line** after printing. Add `%n` to the format string when you want to end the line.

- `%n` is a **Formatter conversion** representing the platform-specific line separator (conceptually `System.lineSeparator()`).
- `\n` is an **escape character in a Java string literal**, representing the LF character. On Windows, the platform line separator is typically CRLF, so `%n` and `\n` do not necessarily produce the exact same bytes.
- `println()` automatically adds the `PrintStream`'s line separator; `print()` does not.
- Inside a format string, neither `%%` nor `%n` **consumes an argument**.

Create **`NewlineDemo.java`**:

```java
public class NewlineDemo {
    public static void main(String[] args) {
        System.out.print("A");
        System.out.println("B");
        System.out.printf("C%n");
        System.out.print("D\nE\n");
        System.out.printf("progress=100%%%n");
    }
}
```

Compile and run:

```sh
javac -encoding UTF-8 --release 17 -d out NewlineDemo.java
java -cp out NewlineDemo
```

**Exact line-by-line stdout content** (the line separator may be LF or CRLF depending on the platform):

```text
AB
C
D
E
progress=100%
```

`print("A")` has not moved to a new line, so `println("B")` appends `B` immediately after `A`. With `System.out.printf("C%n")`, `%n` is required so that `D` starts on a new line. `"D\nE\n"` contains two LF characters from the `\n` escape. `"progress=100%%%n"` consists of the text `100`, the `%%` specifier printing one `%` sign, and then `%n` ending the line.

**Common mistake:** writing `System.out.printf("100% done%n");` leaves a bare `%` sign starting an invalid format specifier. Fix it to `System.out.printf("100%% done%n");`, or use `println("100% done")` if Formatter is not needed.

## 6. Width, alignment, and precision

### Minimum width

With the string `"Cat"`:

```java
System.out.printf("[%8s]%n", "Cat");
System.out.printf("[%-8s]%n", "Cat");
```

Output:

```text
[     Cat]
[Cat     ]
```

In `%8s`, `Cat` is three characters long so five spaces appear before it; `%-8s` has five spaces after it. `width` does not cap the maximum length: if a string is longer than eight characters, Formatter still prints the entire string (unless precision is used to limit it).

### Precision for floating-point numbers and strings

```java
System.out.printf(java.util.Locale.ROOT, "[%8.2f]%n", 12.5);
System.out.printf(java.util.Locale.ROOT, "[%.3s]%n", "abcdef");
```

Output:

```text
[   12.50]
[abc]
```

`%8.2f` produces `12.50` (five characters long), so three spaces are padded on the left. `%.3s` keeps at most three characters from `abcdef`.

For `%f`, precision controls the number of fractional digits and may involve rounding. If you need to represent **exact monetary values**, use `BigDecimal` with explicit business rounding rules, rather than assuming `double` can represent every decimal number accurately.

### Common format flags

| Flag | Example | Result with `Locale.ROOT` | Notes |
| --- | --- | --- | --- |
| `-` | `%-6d`, number `42` | `42    ` | Left-align within a 6-character field |
| `+` | `%+d`, number `42` | `+42` | Always show the number sign |
| `0` | `%05d`, number `42` | `00042` | Pad with zero digits instead of spaces |
| `,` | `%,d`, number `1234567` | `1,234,567` | Group digits according to locale |
| `(` | `%(d`, number `-42` | `(42)` | Enclose negative values in parentheses |
| `#` | `%#x`, number `26` | `0x1a` | Alternate form; meaning depends on conversion |

Not every flag can be used with every conversion. For example, the `0` flag works with many numeric formats, but is invalid for regular `%s`.

## 7. `Locale` determines how numbers are displayed

When calling `System.out.printf("%.2f%n", 1234.5)`, the output depends on the default locale. To specify the display format explicitly:

```java
import java.util.Locale;

public class LocaleDemo {
    public static void main(String[] args) {
        System.out.printf(Locale.US, "US=[%,.2f]%n", 1234.5);
        System.out.printf(Locale.GERMANY, "DE=[%,.2f]%n", 1234.5);
    }
}
```

Compile and run:

```sh
javac -encoding UTF-8 --release 17 -d out LocaleDemo.java
java -cp out LocaleDemo
```

Stdout:

```text
US=[1,234.50]
DE=[1.234,50]
```

In `Locale.US`, commas are used for digit grouping and a dot separates the decimal part. In `Locale.GERMANY`, these two characters swap roles. When formatting for **human readers**, choose the user's locale; when you need stable output for learning or machine processing, specify an appropriate locale explicitly.

`Locale.ROOT` is used in the main examples to avoid depending on system settings; it does not mean every country uses the same conventions.

## 8. Use `String.format()` when you need to keep the result

`System.out.printf(...)` prints directly to stdout. If you need to build the string first, use `String.format(Locale, format, args...)`:

```java
import java.util.Locale;

public class FormatStringDemo {
    public static void main(String[] args) {
        String label = String.format(Locale.ROOT, "ID=%03d; value=%.1f%%", 7, 12.5);
        System.out.println(label);
    }
}
```

Compile and run:

```sh
javac -encoding UTF-8 --release 17 -d out FormatStringDemo.java
java -cp out FormatStringDemo
```

Output:

```text
ID=007; value=12.5%
```

`%03d` prints `7` with width three and two leading zeros. `%.1f%%` prints `12.5%` under `Locale.ROOT`. A literal `%` in the format string still must be escaped as `%%` even when using `String.format` instead of `printf`.

## 9. Common mistakes and how to fix them

Formatting mistakes are primarily **runtime exceptions** in the `java.util.IllegalFormatException` family and are not necessarily caught by `javac`:

| Mistake | Possible consequence | How to fix |
| --- | --- | --- |
| `printf("%d", "42")` | `IllegalFormatConversionException` because `String` does not match `%d` | Parse into an integer or use `%s` |
| `printf("%f", 42)` | Type `Integer` does not match `%f` | Use `42.0`, `(double) 42`, or `%d` |
| `printf("%s %d", "An")` | `MissingFormatArgumentException` due to missing argument for `%d` | Supply all required arguments |
| `printf("%.2d", 7)` | `IllegalFormatPrecisionException` | For integers, use width or the `0` flag, such as `%03d` |
| `printf("rate=10%")` | A single `%` creates an invalid format | `printf("rate=10%%")` |
| `printf("%05s", "A")` | The `0` flag is invalid for `%s` | Use `%5s` or `%-5s` |
| Missing `%n` at the end of a format string | Consecutive print calls merge onto the same line | Add `%n` or use `println` |
| Output has an unexpected decimal separator | Different default locale | Pass `Locale.ROOT`, `Locale.US`, or the target locale |

Not every sequence starting with `%` requires an argument. `%%` (prints `%`) and `%n` (newline) **do not consume an argument slot**. If you want to display a literal format-like sequence such as `%d`, write `%%d` in the format string.

In addition:

- Argument order matters: `printf("%s: %d", name, age)` differs from `printf("%s: %d", age, name)`, and the latter can fail with a type mismatch.
- `%d` formats the integer value according to formatting rules without adding units. For currency or percentages, write the unit explicitly.
- `%f` defaults to six digits after the decimal point. Do not confuse **precision** with **width**.
- `%s` is a simple option when displaying many kinds of objects, though its representation depends on `toString()` or the corresponding formatter behavior; do not assume it produces a round-trip parseable format for arbitrary objects.
- Width and precision are not Unicode table-alignment tools when dealing with emojis, combining marks, or characters whose display width differs from one terminal column. For column-aligned tables, test on the target terminal.

## 10. Practice exercises with answers

**Exercise 1.** Print the number `5` as `005` followed by a newline.

```java
System.out.printf("%03d%n", 5);
```

Result: `005` on a single line.

**Exercise 2.** Print the number `7.5` with two decimal places and a percent sign.

```java
System.out.printf(java.util.Locale.ROOT, "%.2f%%%n", 7.5);
```

Result: `7.50%` followed by a newline.

**Exercise 3.** Left-align the string `"Hi"` in a 6-character field, surrounded by square brackets so the spaces are visible.

```java
System.out.printf("[%-6s]%n", "Hi");
```

Result: `[Hi    ]`.

**Exercise 4.** Print `"second"` then `"first"` when the arguments are passed in the order `"first", "second"`.

```java
System.out.printf("%2$s, %1$s%n", "first", "second");
```

Result: `second, first`.

These practice snippets can be placed inside a Java class's `main` method or executed in JShell; they are individual statements, not standalone Java files.

**Key takeaway:** With `printf()`, choose the right conversion for the data type, use `width`/`precision` when you need column alignment or digit control, use `%%` to print a literal percent sign, and use `%n` for a platform-appropriate newline. Specify a `Locale` when consistent output is required.