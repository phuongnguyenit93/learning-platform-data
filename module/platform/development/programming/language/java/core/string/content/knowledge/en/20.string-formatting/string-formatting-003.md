# Java String Formatting with %s, %c, %b, %d, %f, and %e

## 1. Purpose and APIs Used

In Java, `java.util.Formatter` provides syntax for inserting values into a string based on a template (*format string*). Six common **conversion specifiers** are `%s`, `%c`, `%b`, `%d`, `%f`, and `%e`. Each specifier determines how an argument is converted to text; width, precision, alignment flags, and display rules can be added.

Three common ways to use it:

~~~java
import java.util.Locale;

String message = String.format(Locale.US, "Name: %s, age: %d", "Mai", 20);
System.out.printf(Locale.US, "Price: %.2f%n", 12.5);

String message2 = "Name: %s, age: %d".formatted("Mai", 20);
~~~

- `String.format(...)` **returns a `String`**; it does not print automatically.
- `System.out.printf(...)` **writes to the output stream**, similar to `System.out.format(...)`; `%n` is usually added when a newline is wanted. `printf` returns the `PrintStream` itself.
- `"template".formatted(...)` (since Java 15) returns a formatted string and uses the default locale; specifier syntax still follows `Formatter`.

In the first two calls, `Locale.US` is passed explicitly so that example numbers have a consistent decimal dot and grouping comma. If the locale is omitted, numeric formatting results may depend on the JVM's region/language configuration.

A format string can contain plain text interspersed with multiple specifiers:

~~~java
String line = String.format(
        Locale.US,
        "%s | %c | %b | %d | %.2f | %.2e",
        "Java", 'J', true, 42, 12.5, 1250.0
);
// Java | J | true | 42 | 12.50 | 1.25e+03
~~~

Each `%...` placeholder receives a corresponding argument in order, unless an argument index or argument-reuse syntax is used.

## 2. Structure of a Format Specifier

General form in `Formatter`:

~~~text
%[argument_index$][flags][width][.precision]conversion
~~~

Meaning of the components:

| Component | Meaning | Example |
|---|---|---|
| `%` | Starts the specifier | `%d` |
| `argument_index$` | Selects which argument, **1-based** | `%2$s` |
| `flags` | Left-align, add sign, zero-pad, digit grouping, etc. depending on conversion | `%-8s`, `%+d`, `%,d` |
| `width` | **Minimum width** of the output field | `%8d` |
| `.precision` | Limits string length or digits after the decimal point, depending on conversion | `%.3s`, `%.2f` |
| `conversion` | Conversion type | `s`, `c`, `b`, `d`, `f`, `e` |

`width` does not truncate values longer than the requested width; by default it adds spaces on the left, unless a left-align flag is present. `precision` has different meanings per conversion and **cannot be used with every type**.

Examples:

~~~java
System.out.println("|" + String.format(Locale.US, "%8s", "Hi") + "|");
// |      Hi|

System.out.println("|" + String.format(Locale.US, "%-8s", "Hi") + "|");
// |Hi      |

System.out.println(String.format(Locale.US, "%.3s", "Spring"));
// Spr

System.out.println("|" + String.format(Locale.US, "%8.2f", 12.5) + "|");
// |   12.50|
~~~

The examples use Latin letters and ASCII characters so the number of spaces is easy to verify. `Formatter` width should not be interpreted as guaranteed display column count in a terminal for all emojis, combining characters, or East Asian scripts.

## 3. `%s`: Representing an Object as a String

`%s` is the **general/string** conversion. It accepts many argument types, including `String`, numbers, booleans, and general objects:

~~~java
System.out.println(String.format("Language: %s", "Java"));    // Language: Java
System.out.println(String.format("Count: %s", 42));           // Count: 42
System.out.println(String.format("Enabled: %s", true));       // Enabled: true
System.out.println(String.format("Value: %s", (Object) null)); // Value: null
~~~

Normally, Java uses the object's string representation (related to `toString()`). For objects implementing `java.util.Formattable`, `Formatter` can use that interface's specialized formatting mechanism. `%s` does not mean Java automatically generates JSON, CSV, or a standard data-interchange format.

Important options:

~~~java
String.format("%10s", "Java");  // "      Java": at least 10 wide
String.format("%-10s", "Java"); // "Java      ": left-aligned
String.format("%.2s", "Java"); // "Ja": at most 2 characters
String.format("%-6.3s", "Spring"); // "Spr   "
~~~

When you need to format columns for person names, product codes, or text labels, `%s` combined with width/precision gives clean presentation. If string truncation could lose information or split a Unicode character cluster, handle the truncation rules in the business layer before formatting.

Uppercase `%S` applies uppercase transformation to the result according to the locale (for example, `String.format(Locale.US, "%S", "java")` gives `JAVA`). This differs from `%s`, which does not automatically uppercase.

## 4. `%c`: Character or Unicode Code Point

`%c` is the **character** conversion, commonly used with `char`/`Character`. It also accepts `Byte`, `Short`, or `Integer` representing a valid Unicode code point:

~~~java
System.out.println(String.format("%c", 'A')); // A
System.out.println(String.format("%c", 66));  // B (code point U+0042)
System.out.println(String.format("|%3c|", 'Z')); // |  Z|
~~~

`%c` requires an argument of the proper type; **a one-character `String` is still not a `char`**:

~~~java
char letter = "Java".charAt(0);
String ok = String.format("%c", letter); // J

// String.format("%c", "J"); // Runtime error: IllegalFormatConversionException
~~~

`%c` with an integer value receives a **Unicode code point**, not a digit to print literally. A code point outside the valid Unicode range will lead to a formatting error; for example, `String.format("%c", -1)` is invalid. For a valid supplementary code point (outside the BMP), the result may contain two UTF-16 code units while still representing one code point.

Do not use precision with `%c`; `%.2c` is an invalid format. Width can be used for column alignment. `%C` is the uppercase variant depending on locale rules.

## 5. `%b`: Boolean Representation per Formatter Rules

`%b` is the **boolean** conversion, but its rules **differ** from coercing any argument to `boolean` by business logic.

- If the argument is `null`, the result is `false`.
- If it is a `Boolean`, the result is `true` or `false` according to its actual value.
- If it is **any other non-null object**, the result is `true`, including the number `0` or an empty string.

~~~java
System.out.println(String.format("%b", true));           // true
System.out.println(String.format("%b", false));          // false
System.out.println(String.format("%b", (Object) null));  // false
System.out.println(String.format("%b", 0));              // true
System.out.println(String.format("%b", ""));             // true
~~~

Therefore, `%b` **does not check "non-zero number" or "non-empty string"** and does not automatically treat the string `"false"` as boolean `false`. To represent a business condition, evaluate the boolean expression first:

~~~java
int quantity = 0;
System.out.println(String.format("Has stock: %b", quantity > 0));
// Has stock: false
~~~

`%B` uppercases the result to `TRUE` or `FALSE`. Width/alignment can be used for presentation; `%b` should not be used in place of input validation.

## 6. `%d`: Signed Decimal Integer

`%d` accepts integer types such as `byte`, `short`, `int`, `long`, and `BigInteger` (or their corresponding wrapper objects), and formats them in **base 10 (decimal)**.

~~~java
System.out.println(String.format(Locale.US, "%d", 42));       // 42
System.out.println(String.format(Locale.US, "%d", -42));      // -42
System.out.println(String.format(Locale.US, "%05d", 42));     // 00042
System.out.println(String.format(Locale.US, "%+d", 42));      // +42
System.out.println(String.format(Locale.US, "%,d", 1234567)); // 1,234,567
~~~

Common flags:

- `0`: pads zeros into the left space after the +/- sign to reach width, e.g. `%05d`.
- `+`: always shows the positive or negative sign, e.g. `%+d`.
- `,`: groups digits according to locale, e.g. `%,d`.
- `-`: left-aligns within a field of sufficient width, e.g. `%-6d`.
- `(`: represents negative numbers in parentheses, e.g. `%(d` turns `-42` into `(42)`.

`%d` **does not** round floating-point numbers: passing `double` or `float` to `%d` causes `IllegalFormatConversionException`. If you want to display a floating-point number with no fractional part, decide on rounding/type conversion rules first, or use `%.0f` with a floating-point type if that matches the display requirement.

In particular, `%.3d` **is invalid in Java Formatter**: precision is not supported for `%d`. To display `007` from integer `7`, use `%03d` (width + zero-padding).

## 7. `%f`: Floating-Point Number in Fixed Decimal Form

`%f` accepts `float`, `double`, or `BigDecimal` (and wrapper objects of the two primitives). It displays floating-point numbers in regular decimal form, **without exponent notation**.

~~~java
System.out.println(String.format(Locale.US, "%f", 12.5));    // 12.500000
System.out.println(String.format(Locale.US, "%.2f", 12.5));  // 12.50
System.out.println(String.format(Locale.US, "%.0f", 12.5));  // 13
System.out.println(String.format(Locale.US, "%8.2f", 12.5)); // "   12.50"
System.out.println(String.format(Locale.US, "%,.2f", 1234.5)); // 1,234.50
~~~

For `%f`:

- No precision specified: defaults to **6 digits after the decimal point**.
- `%.2f`: displays **2 digits after the decimal point**; rounds to represent at that precision and appends trailing zeros if needed.
- `%.0f`: prints no digits after the decimal point; does not mean altering the value in the original variable.
- `%8.2f`: `8` is the minimum width of the entire field, including a minus sign or dot; `2` is the number of digits after the decimal point.
- `%,.2f`: adds grouping characters, with the exact character depending on the locale.

Do not use `%f` directly for an integer `int`: `String.format("%f", 12)` fails with an argument type error. If the goal is to represent `12.00`, pass `12.0`, cast to `double`, or use `BigDecimal`.

**Regarding accuracy:** `double` stores numbers in binary, so many decimal numbers (like `1.005`) are not represented with exact decimal precision. `%.2f` controls how it is **displayed**; it does not turn a binary floating-point number into an exact decimal and does not replace monetary rounding rules. For problems requiring exact decimal values, consider `BigDecimal` constructed from a string and explicitly define rounding in calculations; and for displaying regional currency, `NumberFormat` may be more appropriate.

## 8. `%e`: Floating-Point Number in Scientific Notation

`%e` accepts the same group of floating-point arguments as `%f`, but uses **scientific notation**:

~~~text
mantissa e exponent
~~~

For example, `1250.0 = 1.25 × 10³`, so:

~~~java
System.out.println(String.format(Locale.US, "%e", 1250.0));
// 1.250000e+03

System.out.println(String.format(Locale.US, "%.2e", 1250.0));
// 1.25e+03

System.out.println(String.format(Locale.US, "%.2e", 0.00125));
// 1.25e-03

System.out.println(String.format(Locale.US, "%.2E", 1250.0));
// 1.25E+03
~~~

Similar to `%f`, the default precision of `%e` is **6 digits after the decimal point in the mantissa**; `%.2e` gives two digits after the decimal point. `e`/`E` is the exponent marker, `+`/`-` is the sign of the exponent, and `03` means an exponent of three, presented with at least two digits.

`%e` is especially useful when data is very large or very small (statistics, measurements, scientific computing); `%f` is easier to read when values lie in a familiar range and viewers want a fixed number of decimal places.

Example of choosing how to display the same number:

~~~java
double value = 0.0000125;
System.out.println(String.format(Locale.US, "%.8f", value));
// 0.00001250

System.out.println(String.format(Locale.US, "%.2e", value));
// 1.25e-05
~~~

Both only change the text representation of the same `double`; neither modifies the `value` variable.

## 9. Comparison Table of the Six Conversions

| Conversion | Meaning | Common Arguments | Example and Result with Locale.US |
|---|---|---|---|
| `%s` | String/object representation | `String`, any object (including null) | `"%s", "Java"` → `Java` |
| `%c` | Character / valid Unicode code point | `char`, `Character`, corresponding `byte`/`short`/`int` | `"%c", 'A'` → `A` |
| `%b` | Boolean per Formatter rules | `boolean`, `Boolean`, any object | `"%b", 0` → `true` |
| `%d` | Decimal integer | `byte`, `short`, `int`, `long`, `BigInteger` | `"%05d", 42` → `00042` |
| `%f` | Fixed-point floating-point number | `float`, `double`, `BigDecimal` | `"%.2f", 12.5` → `12.50` |
| `%e` | Scientific-notation floating-point number | `float`, `double`, `BigDecimal` | `"%.2e", 1250.0` → `1.25e+03` |

The corresponding uppercase conversions `%S`, `%C`, `%B`, and `%E` change uppercase presentation; `%d` and `%f` do not have equivalent `%D` or `%F` forms in `Formatter`.

Choose based on the nature of the data: use `%c` for a character; `%b` for boolean; `%d` for integers; `%.2f` for floating-point numbers needing two decimal places; `%.2e` for very small/large numbers; and `%s` for data needing general text display.

## 10. Argument Ordering, Reuse, and Special Characters

### 10.1. Reordering with `n$`

By default, conversions receive arguments in order of appearance. With `%1$s`, `%2$d`, etc., we can directly specify the argument position (1-based):

~~~java
String text = String.format(Locale.US,
        "%2$s has %1$d points", 95, "Lan");
System.out.println(text);
// Lan has 95 points
~~~

This is a useful option when translations across languages require reversing the order of sentence components. Ensure indices and conversion types match the actual arguments.

### 10.2. Reusing with `<`

The `<` flag reuses the argument of the **preceding** format specifier:

~~~java
System.out.println(String.format(Locale.US, "%d / %<d", 7));
// 7 / 7
~~~

Do not use `%<d` in the first position when there is no preceding argument to reuse.

### 10.3. Printing a Percent Sign and Newline

`%%` represents a **literal `%` sign**; `%n` produces a platform-specific newline. Both **do not consume a value argument**:

~~~java
System.out.printf(Locale.US, "Completed: %d%%%n", 75);
// Completed: 75%
// (followed by an OS-specific newline)
~~~

`%n` is suitable when printing to console or building text that follows platform newline conventions. For protocol-standard strings explicitly requiring `\n`, use the standard newline character required by the protocol rather than defaulting to `%n`.

## 11. Locale and Number Formatting

The same format `%,.2f` can produce two different representations across two locales:

~~~java
double amount = 1234.5;

System.out.println(String.format(Locale.US, "%,.2f", amount));
// 1,234.50

System.out.println(String.format(Locale.GERMANY, "%,.2f", amount));
// 1.234,50
~~~

Locale affects decimal separators, grouping, and certain language rules. For logs, machine-exchange files, or tests with exact expectations, choose an appropriate explicit locale (such as `Locale.US` or `Locale.ROOT` per the desired formatting convention). When displaying to users, use a locale suitable for them.

Do not blindly embed `String.format("%.2f", amount)` into machine-readable formats without controlling the locale: in some locales, a comma can be the decimal separator, causing receivers to misinterpret the data. Additionally, `%s` and the conversions above do not automatically quote/escape for CSV, JSON, SQL, or HTML.

## 12. Complete Java 17+ Example

Create a file **`FormatterConversionsDemo.java`**:

~~~java
import java.util.Locale;

public class FormatterConversionsDemo {
    public static void main(String[] args) {
        String name = "Linh";
        char grade = 'A';
        boolean active = true;
        long count = 1_234_567L;
        double price = 1234.5;
        double tiny = 0.00125;

        System.out.printf(Locale.US, "text: %s%n", name);
        System.out.printf(Locale.US, "char: %c%n", grade);
        System.out.printf(Locale.US, "bool: %b%n", active);
        System.out.printf(Locale.US, "decimal: %,d%n", count);
        System.out.printf(Locale.US, "fixed: %,.2f%n", price);
        System.out.printf(Locale.US, "scientific: %.2e%n", tiny);

        System.out.printf(Locale.US,
                "alignment: |%-8.3s|%05d|%n", "Spring", 42);
        System.out.printf(Locale.US,
                "reordered: %2$s=%1$d%n", 9, "id");

        String summary = String.format(
                Locale.US, "%s: %.2f", "Total", 12.5);
        System.out.println(summary);
    }
}
~~~

Compile and run:

~~~bash
javac FormatterConversionsDemo.java
java FormatterConversionsDemo
~~~

Output when using `Locale.US`:

~~~text
text: Linh
char: A
bool: true
decimal: 1,234,567
fixed: 1,234.50
scientific: 1.25e-03
alignment: |Spr     |00042|
reordered: id=9
Total: 12.50
~~~

Checking the output:

1. `%s` inserts `Linh`, `%c` inserts `A`, `%b` inserts `true`.
2. `%,d` groups the integer: `1,234,567`.
3. `%,.2f` displays the floating-point number with two decimal digits and grouping: `1,234.50`.
4. `%.2e` normalizes the small number into mantissa and exponent: `1.25e-03`.
5. `%-8.3s` truncates `Spring` to `Spr` and adds 5 spaces on the right for width 8; `%05d` pads zeros so `42` has width 5.
6. `%2$s=%1$d` takes the second argument `id` first and then the first argument `9`; `String.format` creates `Total: 12.50` without printing until `println` is called.

The `System.out.printf` and `System.out.println` statements produce newlines as shown in the output. No libraries outside the JDK are needed.

## 13. Common Errors and How to Handle Them

### 13.1. Conversion Incompatible with Argument Type

These calls **compile but throw an exception at runtime**:

~~~java
// String.format("%d", "42");  // IllegalFormatConversionException
// String.format("%f", 42);    // IllegalFormatConversionException
// String.format("%c", "A");   // IllegalFormatConversionException
~~~

The fix is to pass the right data type or explicitly convert after validating input; for example `Integer.parseInt("42")` if you want to display it as an actual integer. Do not replace every conversion with `%s` just to hide errors if the task requires numeric formatting.

### 13.2. Insufficient Number of Arguments

~~~java
// String.format("%s %d", "Java");
// MissingFormatArgumentException: no argument for %d
~~~

Check that there are enough arguments, in the right order, and verify `n$` indices. Note that `%%` and `%n` do not occupy an argument slot.

### 13.3. Confusing Width with Precision

- `%8s`: width **at least 8**, does not truncate the string.
- `%.3s`: takes at most 3 characters from the `%s` result.
- `%8.2f`: width at least 8, with 2 decimal digits.
- `%03d`: integer with field width 3 padded with zeros.
- `%.3d`: **invalid** in Java Formatter; `%d` does not support precision.

### 13.4. Placing Invalid Flags or Precision

Not every flag is valid for every conversion. For example, `%05s` is invalid because the `0` flag is for numeric padding, not string padding with `%s`. `%.2c` and `%.2d` are invalid because these two conversions do not accept precision. Java will raise exceptions in the `IllegalFormatException` family (such as `FormatFlagsConversionMismatchException` or `IllegalFormatPrecisionException`), rather than ignoring invalid options.

### 13.5. Assuming `%b` Is Business-Logic Boolean Conversion

`String.format("%b", 0)` yields `true` because `Integer` is a non-null object. To display the meaning "is quantity greater than 0", format the expression `quantity > 0`.

### 13.6. Assuming Formatting Modifies Original Data or Solves Monetary Problems

~~~java
double x = 12.5;
String display = String.format(Locale.US, "%.2f", x);
// display = "12.50", while x remains 12.5
~~~

`Formatter` creates a text representation. It does not change `x`, does not check currency units, and does not handle complex business rounding rules. Do not use formatted strings as the source of truth for further calculations.

### 13.7. Not Controlling the Locale

`String.format("%,.2f", value)` can produce different grouping and decimal separators across machines. For output that must be compared verbatim in tests or transmitted between systems, choose an explicit locale and specific encoding/format conventions.

## 14. How to Choose a Conversion When Writing Programs

When formatting a value, determine the actual data type and display purpose first:

- Text/object data: `%s`; use width, alignment, and precision when columns or truncation are needed.
- A character or Unicode code point: `%c`; do not pass a `String` instead of a `char`.
- A pre-evaluated boolean condition: `%b`.
- An integer: `%d`; use `%05d` for zero-padding to width, `%,d` for locale grouping.
- A floating-point number in regular form: `%f` or `%.2f`; precision controls digits after the decimal point.
- A floating-point number in scientific form: `%e` or `%.2e`; suitable for very large/small values.

Finally, verify argument order, data types, locale, width/precision semantics, and `%%`, `%n` tokens. These checks keep displayed strings consistent and avoid `Formatter` errors that only surface at runtime.
