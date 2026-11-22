# print, println, printf, and Formatter in Java

When outputting data to the console or generating structured text, Java provides three familiar methods on `PrintStream`: `print(...)`, `println(...)`, and `printf(...)`. All three are commonly called via `System.out`, yet **they do not share the same line-ending or value-formatting behavior**. Behind `printf` lies `java.util.Formatter`, which can align columns, format numbers according to patterns, select a `Locale`, and build formatted strings for files or other destinations.

This lesson explains how to choose the right method, read `%...` syntax, control formatting across machines, and avoid common pitfalls in Java 17+.

## 1. Standard Output and PrintStream

`System.out` is the standard output stream (stdout), of type `PrintStream`; `System.err` is the standard error stream (stderr), also a `PrintStream`. For programs running in a terminal, both usually appear on screen. However, when redirected or run in an IDE, they can be sent to different places.

~~~java
System.out.print("Hello");
System.out.println(" World");
System.err.println("Something went wrong");
~~~

This is an **illustrative code snippet**. The first two calls combine into the line `Hello World` on stdout. The last call sends a message to stderr; relative display order between the two streams is not necessarily guaranteed by the terminal or log collector. Do not call `close()` on `System.out`/`System.err` in normal programs, as other parts of the application may still need them.

`PrintStream` provides `print`/`println` overloads for primitive types, `String`, `char[]`, and `Object`. For objects, representation usually relies on `String.valueOf(...)` and `toString()`; thus how nicely an object formats depends on how `toString()` is implemented. Primitive arrays such as `int[]` do not automatically print their element list with `print(array)`; to display their contents, use `Arrays.toString(array)`.

## 2. How Do print, println, and printf Differ?

| Method | Primary Behavior | Automatically Ends Line? | Supports `%...` Format String? |
|---|---|---|---|
| `print(value)` | Prints representation of a value | **No** | No |
| `println(value)` | Prints value then prints a line terminator | **Yes** | No |
| `println()` | Prints only a line terminator | **Yes** | No |
| `printf(format, args...)` | Replaces format specifiers with formatted values | **No**, unless the pattern contains a newline or `%n` | **Yes** |
| `format(format, args...)` on `PrintStream` | Same formatting engine as `printf` | Per pattern | Yes |

`print` is useful for joining multiple pieces on one line. `println` suits line-by-line messages. `printf` fits records needing column widths, digit counts, precision, or type-specific formatting.

Example:

~~~java
System.out.print("A");
System.out.print("B");
System.out.println("C");
System.out.println("D");
~~~

Output on stdout:

~~~text
ABC
D
~~~

The two `print` calls do not add a newline. `println("C")` ends the `ABC` line; `println("D")` produces the next line.

**Very easy mistake:** `System.out.printf("Done")` does not add a newline automatically. If you want a newline, use `System.out.printf("Done%n")` or call `println()` afterward.

## 3. Complete Example: All Three Methods in One Program

Create file **`ConsoleOutputDemo.java`**:

~~~java
import java.util.Locale;

public class ConsoleOutputDemo {
    public static void main(String[] args) {
        System.out.print("Java");
        System.out.print(" ");
        System.out.println("IO");
        System.out.println();

        System.out.printf(Locale.US, "ID=%04d; price=%.2f%n", 7, 12.5);
        System.out.printf(Locale.US, "[%-6s][%05d]%n", "OK", 42);
        System.out.printf(Locale.US,
                "%2$s/%1$s/%%%n", "right", "left");
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 ConsoleOutputDemo.java
java ConsoleOutputDemo
~~~

Stdout (with **one blank line** after `Java IO`):

~~~text
Java IO

ID=0007; price=12.50
[OK    ][00042]
left/right/%
~~~

Explanation:

1. Two `print` calls and one `println` together produce `Java IO`; then `println()` creates a blank line.
2. `%04d` prints integer `7` in a minimum width of 4 padded with leading `0`s, yielding `0007`.
3. `%.2f` prints a floating-point number with two digits after the decimal point, yielding `12.50` under `Locale.US`.
4. `%-6s` left-aligns string `OK` in a field at least six characters wide: `OK` plus four spaces. `%05d` yields `00042`.
5. `%2$s` selects the second argument (`left`); `%1$s` selects the first (`right`). `%%` prints a literal `%`, and `%n` ends the line.
6. `Locale.US` is specified explicitly so numbers and formatting symbols do not depend on the host machine's default locale.

The text lines are identical across platforms, though the trailing line-ending byte sequences may differ by OS because `println` and `%n` use the platform's line separator.

## 4. Structure of a Formatter Specifier

General template for an argument-taking conversion:

~~~text
%[argument_index$][flags][width][.precision]conversion
~~~

| Part | Role | Example |
|---|---|---|
| `%` | Starts a specifier | `%d` |
| `argument_index$` | Selects argument at position 1, 2, 3, ... (1-based) | `%2$s` |
| `flags` | Adjusts alignment, sign, zero-padding, digit grouping... | `%-10s`, `%+d` |
| `width` | **Minimum width**, does not truncate if exceeded | `%8d` |
| `.precision` | Precision or maximum length, depending on conversion type | `%.2f`, `%.3s` |
| `conversion` | Desired representation type | `s`, `d`, `f` |

Parts in `[...]` are optional. Not every combination of flags, width, and precision is valid for every conversion; invalid combinations can throw a formatting exception.

Some special specifiers consume no arguments:

- `%%` outputs a literal percent character `%`.
- `%n` outputs the **platform-appropriate line terminator**.
- Writing `\n` in a Java string outputs an exact LF character; it does not carry the *platform line separator* meaning of `%n`.

### Common Conversions

| Specifier | Matching Argument Type | Example Value / Output |
|---|---|---|
| `%s` | Most objects, string form | `"Java"` → `Java` |
| `%S` | Uppercase form of `%s` using active locale | `"java"` → `JAVA` |
| `%d` | Integer types: `byte`, `short`, `int`, `long`, `BigInteger` | `42` → `42` |
| `%x`, `%X` | Hexadecimal integer, lowercase/uppercase | `255` → `ff` / `FF` |
| `%o` | Octal integer | `8` → `10` |
| `%f` | `float`, `double`, `BigDecimal` | `1.5` → `1.500000` when precision is omitted |
| `%e`, `%E` | Floating-point in scientific notation | `12.0` → exponent representation |
| `%b` | Boolean value per Formatter rules | `true` → `true` |
| `%c` | Character, or a valid code point from a suitable integer value | `'A'` → `A` |
| `%tF` | Date/time argument supporting conversion: `yyyy-MM-dd` date | `LocalDate.of(2024, 2, 29)` → `2024-02-29` |
| `%n` | Takes no argument | Line terminator |
| `%%` | Takes no argument | `%` |

Key details to remember:

- `%d` is **not** for floating-point `double`; to format decimal numbers, use `%f` or convert types intentionally.
- `%f` defaults to six digits after the decimal point (e.g., `1.500000`), not raw `Double.toString` output.
- Formatter's `%b` **differs from parsing a string as boolean**: if the argument is `null`, the result is `false`; if it is a `Boolean`, it uses that value; any other non-`null`, non-`Boolean` object produces `true`. Do not use `%b` to interpret text data `"false"`.
- `%s` with `null` outputs the text `null`; it is not equivalent to an empty string. For custom objects, the result depends on `toString()` or `Formattable` if implemented.
- `%tF` uses date-time syntax: `t` followed by `F`; other variants include `%tY` (year), `%tm` (month), `%td` (day), and `%tT` (hours/minutes/seconds). The argument type must support the requested temporal field.
- Java `char`/`Character` values cannot be used directly with `%d`; if you want the character code, convert explicitly to `int`.

## 5. Width, Alignment, Zero-Padding, and Precision

### 5.1. Width Is a Minimum

~~~java
System.out.printf(Locale.US, "[%5s]%n", "A");
System.out.printf(Locale.US, "[%-5s]%n", "A");
~~~

This is an illustrative snippet requiring `import java.util.Locale` inside a method. Output:

~~~text
[    A]
[A    ]
~~~

- `%5s`: total width of at least 5, by default padding 4 spaces on the **left**.
- `%-5s`: the `-` flag aligns **left**, padding 4 spaces on the right.
- If the value is longer than width, Formatter does not truncate it automatically. Width is not a maximum size.

### 5.2. Precision Depends on Conversion Type

~~~java
System.out.printf(Locale.US, "[%.3s]%n", "Formatter");
System.out.printf(Locale.US, "[%.2f]%n", 3.14159);
~~~

Output:

~~~text
[For]
[3.14]
~~~

- `%.3s` limits the formatted string representation to at most three characters, producing `For`.
- `%.2f` specifies two digits after the decimal separator, rounding when necessary.
- **Do not use `%.2d`** out of habit from other languages: precision does not apply to `%d` integer conversions in `java.util.Formatter`; it throws `IllegalFormatPrecisionException`. To pad with leading zeros, use e.g. `%04d`.

### 5.3. Common Numeric Formatting Flags

| Specifier | Value | Output with `Locale.US` | Meaning |
|---|---:|---|---|
| `%+d` | `42` | `+42` | Always show sign |
| `%06d` | `42` | `000042` | Zero-pad to width 6 |
| `%,d` | `1234567` | `1,234,567` | Digit grouping |
| `%(d` | `-42` | `(42)` | Enclose negative numbers in parentheses |
| `%8.2f` | `3.5` | `    3.50` | Width 8, two decimal digits |
| `%-8.2f` | `3.5` | `3.50    ` | Left-aligned in 8 positions |

Spaces in the last two rows are part of the output. Do not apply the `0` flag to `%s` strings, and do not combine opposing flags `-` and `0`: incompatible combinations throw `FormatFlagsConversionMismatchException` or `IllegalFormatFlagsException`.

## 6. Argument Ordering and Argument Reuse

By default, specifiers that take arguments consume them in order:

~~~java
String text = String.format("%s:%d", "port", 8080);
~~~

`text` holds `port:8080`. This is an illustrative snippet.

To change order without changing the argument list, use **1-based** indices followed by `$`:

~~~java
String text = String.format("%2$s / %1$s / %2$s", "B", "A");
~~~

`text` holds `A / B / A`. Arguments are referenced multiple times without passing duplicates.

The `<` flag also lets you reuse the argument of the preceding specifier:

~~~java
String result = String.format(Locale.US, "%1$.2f / %<.1f", 2.5);
~~~

`result` is `2.50 / 2.5`. Using `<` before any previous argument exists causes Formatter to report a missing argument error. In code with many formatted fields, explicit indices are usually easier to verify because mixing explicit and implicit indexing follows subtle rules.

## 7. How Locale Affects Formatting Output

`Locale` governs localization rules in Formatter, such as decimal separators, thousands grouping, and month names. By default, `printf(...)` calls without a `Locale` use the **default locale for the FORMAT category**, so output can differ between machines.

Program **`LocaleFormattingDemo.java`**:

~~~java
import java.time.LocalDate;
import java.util.Locale;

public class LocaleFormattingDemo {
    public static void main(String[] args) {
        double amount = 12345.6;

        System.out.println("US: "
                + String.format(Locale.US, "%,.2f", amount));
        System.out.println("DE: "
                + String.format(Locale.GERMANY, "%,.2f", amount));

        LocalDate date = LocalDate.of(2024, 2, 29);
        System.out.printf(Locale.US, "Date: %1$tF%n", date);

        String message = "Item=%s; quantity=%d".formatted("Pen", 3);
        System.out.println(message);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleFormattingDemo.java
java LocaleFormattingDemo
~~~

Output:

~~~text
US: 12,345.60
DE: 12.345,60
Date: 2024-02-29
Item=Pen; quantity=3
~~~

Rounding via `%.2f` is a display formatting behavior; **it does not change the underlying `double` variable's value**. When business logic requires exact monetary rules, choose the appropriate numeric type (e.g., `BigDecimal`), precision, and rounding mode separately; Formatter primarily handles presentation.

- Use `Locale.US` or a fixed locale for predictable results when formatting reports or tests.
- Use the user's locale for region-friendly display text.
- Do not treat Formatter's decimal separator as a default machine-to-machine interchange format. CSV, JSON, SQL, or data protocols have their own specifications; follow each format's standard.
- `String.formatted(args...)` (Java 15+) is a concise way to apply Formatter syntax to a template string; it uses the default locale when localization applies. To specify a locale explicitly, use `String.format(Locale, ...)`.

## 8. java.util.Formatter: Formatting Without Printing to the Console

`java.util.Formatter` is the formatting engine itself. `PrintStream.printf` and `PrintStream.format` are convenient ways to write formatted results to a PrintStream; `String.format` creates a **new String**; while a `Formatter` instance can write directly to an `Appendable` target, such as `StringBuilder` or `Writer`.

Standalone example **`FormatterBuilderDemo.java`**:

~~~java
import java.util.Formatter;
import java.util.Locale;

public class FormatterBuilderDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder();

        try (Formatter formatter = new Formatter(builder, Locale.US)) {
            formatter.format("%2$s | %1$04d%n", 3, "ID");
            formatter.format("ratio=%.2f%n", 2.5);
        }

        System.out.print(builder.toString());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FormatterBuilderDemo.java
java FormatterBuilderDemo
~~~

Stdout:

~~~text
ID | 0003
ratio=2.50
~~~

Example lifecycle:

1. `StringBuilder` serves as the character destination, with no byte I/O or console yet.
2. `new Formatter(builder, Locale.US)` creates a formatter writing to builder with the specified locale.
3. Both `format` calls append to the same builder, **without erasing previous content**.
4. `Formatter` implements `AutoCloseable`, so it works in `try-with-resources`. Here `StringBuilder` is not an I/O resource needing closure, and its contents remain accessible after closing the Formatter.
5. The final `System.out.print(...)` merely outputs the constructed string; it could be replaced by writing to a file or used inside an application without console printing.

For a Formatter writing to a `Closeable` destination, `Formatter.close()` also closes that destination. Avoid creating a `Formatter` wrapping `System.out` and accidentally closing it mid-program. A closed Formatter cannot format further; reusing it throws `FormatterClosedException`.

### Formatter Can Write to a Writer

~~~java
// Illustrative code snippet: writer is a Writer owned by the application.
try (Formatter formatter = new Formatter(writer, Locale.US)) {
    formatter.format("%s,%.2f%n", "Book", 12.5);
}
~~~

Use this when you want to assemble formatted content in one place, optionally combined with `BufferedWriter` or `Files.newBufferedWriter(...)` using an explicit charset. When the formatter closes, the underlying writer is closed as well if it implements `Closeable`.

## 9. printf, Formatter, and String-Building Methods

| API | Output Destination | Return Value | Characteristics |
|---|---|---|---|
| `System.out.printf(...)` | Stdout via PrintStream | The `PrintStream` itself | Writes directly, does not add newline automatically |
| `System.out.format(...)` | Stdout via PrintStream | The `PrintStream` itself | Equivalent mechanism to printf |
| `String.format(...)` | Memory | New `String` | Suitable for building messages to send elsewhere |
| `"pattern".formatted(...)` | Memory | New `String` | Concise syntax since Java 15 |
| `formatter.format(...)` | Formatter's `Appendable` target | The `Formatter` itself | Allows appending multiple segments with the same formatter |

`printf` has the overload `printf(Locale locale, String format, Object... args)`. If no locale is passed, numbers and dates are formatted with the default FORMAT locale. `String.format` has a matching overload.

`print` and `println` **do not parse input strings for format specifiers**: `System.out.println("100%")` prints literally `100%`. Conversely, with `printf("100%")`, a standalone percent sign causes a formatting syntax error; write `printf("100%%")` or use `print/println` for strings that do not need formatting.

## 10. Formatting Errors and How to Detect Them

Unlike plain `print`, Formatter checks compatibility between pattern and arguments **at runtime**. Wrong conversion codes, missing arguments, or invalid flags throw an exception from the `IllegalFormatException` hierarchy at runtime.

| Error | Example | Typical Result |
|---|---|---|
| Incompatible argument type | `String.format("%d", "12")` | `IllegalFormatConversionException` |
| Missing argument | `String.format("%s %d", "A")` | `MissingFormatArgumentException` |
| Unsupported precision | `String.format("%.2d", 4)` | `IllegalFormatPrecisionException` |
| Flag incompatible with conversion | `String.format("%05s", "A")` | `FormatFlagsConversionMismatchException` |
| Pattern has unsupported conversion | `String.format("%q", 1)` | `UnknownFormatConversionException` |

Standalone example **`FormattingErrorsDemo.java`**:

~~~java
import java.util.IllegalFormatConversionException;
import java.util.MissingFormatArgumentException;

public class FormattingErrorsDemo {
    public static void main(String[] args) {
        try {
            String.format("%d", "42");
        } catch (IllegalFormatConversionException ex) {
            System.out.println("Wrong type");
        }

        try {
            String.format("%s %d", "A");
        } catch (MissingFormatArgumentException ex) {
            System.out.println("Missing argument");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FormattingErrorsDemo.java
java FormattingErrorsDemo
~~~

Stdout:

~~~text
Wrong type
Missing argument
~~~

Treat formatting errors as bugs in the program or input validation issues to be controlled. Do not use `catch (Exception)` and ignore them to hide bad patterns. If user-entered text must be printed, pass it **as an argument to `%s`** (e.g., `printf("%s%n", userText)`) instead of using the user text itself as the format string; a `%` inside user input will not then be misinterpreted as a format directive.

### I/O Errors Differ from Format Syntax Errors

`PrintStream` by contract does not throw `IOException` from ordinary print operations; underlying I/O failures are recorded via an error flag, checkable with `checkError()`. However, **formatting exceptions** like `IllegalFormatException` are still thrown when the pattern/arguments are invalid. Do not confuse these two error categories.

Similarly, a `Formatter` writing to an `Appendable` can record an `IOException` from the destination and expose it via `ioException()`. When writing important data to files, beyond formatting accurately you must decide how to react if writing actually fails. Notably, seeing no exception from `PrintStream.print(...)` is not proof that data was durably saved to storage.

## 11. Charset, Newlines, and Output Streams

A `String` in the JVM differs from the bytes `System.out` sends to a terminal/file. The charset used by `PrintStream` and the terminal environment can affect whether Vietnamese diacritics display properly; starting in JDK 18, a UTF-8 default charset does not mean every `System.out`/`System.err` and terminal setup necessarily uses the exact same encoding.

If you need to produce a consistently formatted text file, you can write a Formatter-built string with an explicit charset:

~~~java
// Illustrative code snippet: path is a valid Path and overwrite behavior is already chosen.
String line = String.format(Locale.US, "%s,%.2f%n", "Tea", 3.5);
Files.writeString(path, line, StandardCharsets.UTF_8);
~~~

This snippet requires importing `Locale`, `Files`, and `StandardCharsets`; `Files.writeString` uses the specified UTF-8 charset. It only demonstrates encoding and is **not** a standalone runnable program. For real CSV files, you also need to handle commas inside values, double quotes, embedded newlines, and CSV rules; joining `%s,%.2f` alone is not a complete CSV writer.

Regarding newlines:

- `println(...)` writes the platform's line terminator.
- `printf("...%n")` appends the platform's line separator.
- `printf("...\n")` writes the LF character `U+000A` inside the format string.
- `print(...)` and `printf(...)` do not add a newline automatically unless requested.

`PrintStream` can be configured to `flush` automatically under defined conditions, though flushing depends on how the PrintStream was constructed and does not guarantee durable disk persistence. For applications needing high-reliability logs or transactional data storage, use proper tools and write strategies rather than relying solely on `System.out.printf`.

## 12. Choosing Tools in Practice

**Simple line-by-line messages:** use `println(...)`. It is readable, adds a newline automatically, and is less error-prone than calling `printf` without specifiers.

**Joining content on the same line:** use `print(...)`. For complex terminal UIs, however, consider dedicated terminal libraries rather than relying on how character streams are buffered and rendered.

**Tables, numbers with separators/precision:** use `printf(locale, pattern, args...)`; control width, precision, flags, and locale.

**Building text for reuse in multiple places:** use `String.format(...)` or `String.formatted(...)`; avoid writing directly to the console inside business logic layers.

**Writing multiple segments to the same buffer or Writer:** use `Formatter` with an `Appendable` target. Define resource-closing responsibility clearly and check I/O errors when writing to external targets.

**Monetary amounts or precision-sensitive calculations:** Formatter is a presentation layer; choosing data types, rounding rules, and storage/exchange formats are separate decisions.

## 13. Common Mistakes

1. **Assuming `printf` automatically adds a newline:** incorrect. Add `%n` when a line ending is needed.
2. **Confusing `%n` with `\n`:** `%n` is the platform line separator, whereas `\n` is LF. Byte-level output tests and file formats must account for this difference.
3. **Using `%d` for `double`, `%.2d` for integers, or `%05s` for strings:** each conversion accepts different types and flags; invalid combinations throw runtime exceptions.
4. **Assuming width is a maximum length:** it is only a minimum; to cap string length, check `%s` precision if suitable, or validate data before printing.
5. **Forgetting Locale:** `%,.2f` may print different grouping and decimal separators across machines. Select locale per requirements.
6. **Using `%b` to parse a boolean value from a string:** the argument `"false"` is still a non-null object and will be formatted as `true` by `%b`.
7. **Passing user data as the format string:** `%` characters can trigger specifiers; pass data as arguments to a fixed pattern instead.
8. **Printing an array with `print(intArray)` expecting a list of values:** array types lack a friendly `toString()`. Use `Arrays.toString(...)` or format elements individually.
9. **Using `printf` to compute/round numbers and reusing the string as a numeric result:** Formatter only builds representations, not arithmetic rules.
10. **Closing `System.out` or wrapping `System.out` in a Formatter and closing it accidentally:** this can prevent the rest of the program from printing.
11. **Assuming every print error throws `IOException`:** `PrintStream` typically records them via `checkError()`; runtime format errors still throw normally.
12. **Thinking stdout and stderr always appear in call order:** when mixed or redirected separately, observed order can differ, so never rely on it for event ordering guarantees.

## 14. Takeaways

- `print(value)` **does not add a newline**; `println(value)` **adds a newline**; `printf(format, args...)` **formats by pattern** and adds a newline only when requested.
- `Formatter` supports `%s`, `%d`, `%f`, `%tF`, `%%`, `%n` plus flags/width/precision/argument indices. Matching argument types is mandatory.
- Specify `Locale` explicitly for stable numbers and date/time output; use `%n` when you want the platform's line separator.
- `String.format`, `String.formatted`, and `Formatter` let you produce formatted output without printing to the console.
- Distinguish formatting syntax/type errors from actual I/O errors; when writing to files or external systems, choose the right charset and resource management strategy.

### Official References

- [Java SE — PrintStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintStream.html)
- [Java SE — Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html)
- [Java SE — String.format and formatted](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
