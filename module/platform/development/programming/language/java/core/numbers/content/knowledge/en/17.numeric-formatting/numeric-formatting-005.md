# `String.format`, `printf`, and `Formatter` in Java

In Java, storing numbers in memory and **presenting numbers as text** are two separate concerns. The same value `12345.678` can be displayed as `12,345.68`, `12.345,68`, or `1.235e+04` depending on the **format pattern, Locale, and intended use**.

Three closely related yet distinct APIs:

- **`String.format(...)`**: formats arguments into **a new `String`**, without printing to the console.
- **`System.out.printf(...)`** (or `PrintStream.printf`): **formats and writes immediately** to the output stream; returns the `PrintStream` so calls can be chained.
- **`java.util.Formatter`**: a stateful formatting object that writes to an `Appendable` such as a `StringBuilder`, a stream, or another supported destination. Suitable when you want to reuse a formatter or control where text goes.

All three rely on **`Formatter` format string syntax**, such as `%d`, `%.2f`, `%,.2f`, and `%e`. Formatting **does not modify the source numeric value**, though the resulting string may be rounded or use a different decimal symbol based on `Locale`.

## 1. How do the three APIs differ in action?

### `String.format` creates a string

```java
import java.util.Locale;

double amount = 1234.567;
String text = String.format(Locale.US, "%,.2f", amount);
System.out.println(text); // 1,234.57
```

`text` holds `"1,234.57"`. The `amount` variable still retains its original numeric value. `String.format` **does not print by itself**; printing is a separate `System.out.println` statement.

There are two familiar overloads:

```java
String a = String.format("%.2f", 1.5); // uses the environment's default Locale
String b = String.format(Locale.US, "%.2f", 1.5); // uses Locale.US
```

If the output must have a consistent format in machine logs, data exports, or tests, **pass an explicit Locale** instead of relying on a default Locale that varies across machines.

### `printf` formats and prints to a stream

```java
System.out.printf(Locale.US, "Total: %.2f%n", 1234.5);
```

Displayed output:

```text
Total: 1234.50
```

`printf` does not "create a String for you to use" like `String.format`; it writes to `System.out`. On `PrintStream`, `printf` returns that stream itself. When calling it multiple times, explicitly handle line breaks with `%n`, `println`, or an appropriate message structure; `printf` does not append a newline by default.

### `Formatter` writes to a destination and can be used across multiple calls

```java
import java.util.Formatter;
import java.util.Locale;

StringBuilder buffer = new StringBuilder();
try (Formatter formatter = new Formatter(buffer, Locale.US)) {
    formatter.format("Price: %.2f", 12.5);
    formatter.format(" | Qty: %d", 3);
}
System.out.println(buffer); // Price: 12.50 | Qty: 3
```

`Formatter` executes multiple `format` calls against the same `StringBuilder` destination. After closing the formatter, `StringBuilder` still holds the written content and can be read. You should close objects you create if they own resources; for a formatter writing to a stream/file, pay attention to how closing can affect the destination. **Do not intentionally close `System.out`** just to stop formatting.

## 2. Structure of a format specifier

General template for an argument-consuming conversion:

```text
%[argument_index$][flags][width][.precision]conversion
```

Parts are optional, except `%` at the start and the **conversion** determining the representation. Example:

```text
%1$+08d
││ │ │ └─ d: decimal integer
││ │ └── 8: minimum width
││ └──── + and 0: always print sign; zero-pad
│└─────── 1$: use the first argument
└──────── %: start of specifier
```

In `"%1$+08d"`, the first argument is an integer; for `42`, the result is `+0000042` (8 characters).

Components:

| Component | Purpose | Example |
| --- | --- | --- |
| `argument_index$` | Selects an argument starting from 1 instead of default order | `%2$s` |
| `flags` | Specifies sign, padding, alignment, grouping, alternate form, etc. | `+`, `0`, `-`, `,`, `(`, `#` |
| `width` | **Minimum** width; does not truncate longer strings | `%8d` |
| `.precision` | Meaning depends on conversion: fractional digits or significant digits, string limit, etc. | `%.2f`, `%.4g` |
| `conversion` | Desired display type | `d`, `f`, `e`, `g`, `x`, `s` |

**Not every flag and precision is valid for every conversion.** For instance, `%.2d` is not a valid way to request "two fractional digits of an integer" and can throw `IllegalFormatPrecisionException`.

## 3. Common integer conversions

| Conversion | Meaning | Example in `Locale.US` |
| --- | --- | --- |
| `%d` | Base-10 integer | `String.format("%d", 42)` → `"42"` |
| `%x` | Base-16 integer, lowercase | `String.format("%x", 255)` → `"ff"` |
| `%X` | Base-16 integer, uppercase | `String.format("%X", 255)` → `"FF"` |
| `%o` | Base-8 integer | `String.format("%o", 8)` → `"10"` |
| `%#x` | Base-16 form with prefix | `String.format("%#x", 255)` → `"0xff"` |
| `%,d` | Base-10 with Locale grouping | `String.format(Locale.US, "%,d", 1234567)` → `"1,234,567"` |
| `%+d` | Always print `+` or `-` sign | `42` → `"+42"` |
| `%(d` | Negative numbers in parentheses | `-42` → `"(42)"` |
| `%05d` | Minimum width 5, zero-padded | `-42` → `"-0042"` |

`%d` works for integral types, including their corresponding wrappers and `BigInteger`. You cannot pass a `double` to `%d` and hope the formatter automatically truncates the fractional part:

```java
// String.format("%d", 3.5); // IllegalFormatConversionException
String correct = String.format(Locale.US, "%.0f", 3.5); // "4"
```

This is **rounding when displaying as a floating-point number**, not casting `double` to `int`. For negative arguments or very large numbers, formatting rules and type-casting rules can differ markedly.

### Alignment, width, and zero-padding

```java
String right = String.format(Locale.US, "|%6d|", 42);
// "|    42|": right-aligned in at least 6 characters

String left = String.format(Locale.US, "|%-6d|", 42);
// "|42    |": left-aligned in at least 6 characters

String zeroFilled = String.format(Locale.US, "%+08d", 42);
// "+0000042": signed and zero-padded
```

`width` is only a **minimum width**, so output strings longer than `width` are still printed in full; the formatter does not automatically truncate digits. If formatting hurts readability or is used to transmit fixed-length data, check the post-format length separately according to your contract.

## 4. Conversions for `float`/`double` and `BigDecimal`

| Conversion | Meaning | Typical pattern |
| --- | --- | --- |
| `%f` | Standard decimal floating-point form | `%.2f` |
| `%e` or `%E` | Scientific notation with exponent | `%.3e` |
| `%g` or `%G` | General form: uses standard or scientific format depending on value/precision | `%.4g` |
| `%a` or `%A` | **Hexadecimal floating-point** format | `%a` with `double` |
| `%,.2f` | Locale-based grouping and two decimal places | `%,.2f` |
| `%(,.2f` | Grouping; negative numbers in parentheses | `%(,.2f` |

Concrete examples:

```java
String fixed = String.format(Locale.US, "%.2f", 12.345);
// "12.35"

String science = String.format(Locale.US, "%.3e", 12345.6);
// "1.235e+04"

String general = String.format(Locale.US, "%.4g", 12345.6);
// "1.235e+04"

String hexadecimal = String.format(Locale.US, "%a", 3.5);
// "0x1.cp1"
```

**Precision does not mean the same thing for `%f` and `%g`**:

- `%.2f` requests **2 digits after the decimal point** of the representation.
- `%.4g` requests **4 significant digits** in the general representation; the formatter chooses standard or scientific form accordingly.
- `%.3e` requests **3 digits after the decimal point of the mantissa** in scientific form.

Special floating-point values such as `Double.NaN` and `Double.POSITIVE_INFINITY` can be printed as `NaN` and `Infinity`, with case depending on the conversion. `-0.0` can also preserve its sign when printed:

```java
System.out.println(String.format(Locale.US, "%.2f", -0.0));
// -0.00
```

`BigDecimal` works with many decimal conversions (`%f`, `%e`, `%g`), whereas `%a` is for the hex representation of binary floating-point types and **does not support `BigDecimal` as an equivalent conversion**.

## 5. Rounding during formatting does not alter the source value

`String.format` and `printf` can **round the displayed text** when precision requests fewer digits, without modifying the value stored in the variable.

```java
double value = 12.3456;
String display = String.format(Locale.US, "%.2f", value);

System.out.println(display); // 12.35
System.out.println(value);   // 12.3456
```

For decimals requiring exactness (such as finalized monetary amounts), you can construct a `BigDecimal` from a string:

```java
java.math.BigDecimal exact = new java.math.BigDecimal("2.345");
String display = String.format(Locale.US, "%.2f", exact);
// "2.35"
```

Do not infer that using `%.2f` for all monetary calculations is enough: a formatter **only produces text**; deciding when amounts are finalized, scale, rounding mode, and recorded figures is the responsibility of **business logic**.

`Math.round`, `BigDecimal.setScale`, and `String.format` are not three arbitrary substitutes for one requirement. A formatting step may round solely **for printing** without altering subsequent computation values. If the contract requires the numeric variable itself to be formally rounded, operate on the appropriate numeric type and store the finalized result.

### Beware binary error

`double` cannot accurately represent every decimal number. `%.2f` may display a value that looks "clean", but that is not proof that the source decimal was represented and computed accurately to two decimal places.

Do not format and then `Double.parseDouble(...)` the printed string to "fix errors" in every scenario: doing so can introduce an unintended extra rounding step, and if the formatted string depends on `Locale`, parsing with `Double.parseDouble` can even fail.

## 6. `Locale` directly affects number formatting

`Locale` governs many text-presentation traits, including the decimal separator and digit grouping separator. Compare:

```java
String us = String.format(Locale.US, "%,.2f", 12345.67);
String germany = String.format(Locale.GERMANY, "%,.2f", 12345.67);

// us:      "12,345.67"
// germany: "12.345,67"
```

The strings differ despite **the exact same `double` value**. `Locale` changes the **text**, not the arithmetic of the expression before it is passed to the formatter.

Therefore:

- **User interface:** choose a Locale matching the user or product rules.
- **Protocols, schema-bound CSV, machine logs, and golden tests:** choose a fixed Locale, such as `Locale.US` or `Locale.ROOT` depending on the contract.
- **Reading strings back:** do not assume `Double.parseDouble` understands locale decimal commas and grouping separators. `Double.parseDouble("12.345,67")` is not a suitable way to parse.

Do not mechanically replace commas with dots: a string like `"1,234"` can mean **one thousand two hundred thirty-four** or **one point two three four**, depending on the Locale and contract. When parsing user-entered strings, use a Locale-configured parser and validate **the entire input**.

### The default Locale can change

`String.format("%.2f", value)` and `System.out.printf("%.2f", value)` use a Locale matching the current environment or configuration; output can differ depending on where it runs. Avoid relying on default output in snapshot tests or inter-system data formats.

## 7. Argument index, reuse, and argument order

Normally conversions consume arguments in order:

```java
String text = String.format(Locale.US, "%s=%d", "count", 7);
// "count=7"
```

`%n$` allows selecting the `n`-th argument (index starting at **1**):

```java
String reversed = String.format(Locale.US, "%2$s=%1$04d", 7, "n");
// "n=0007"
```

The `<` flag **reuses the argument consumed by the preceding format specifier**:

```java
String bothBases = String.format(Locale.US, "%1$d / %<x", 31);
// "31 / 1f"
```

It is very easy to confuse **the second argument** with **0-based indexing**. `%2$s` is the second argument, not the argument at Java array index 2.

Avoid positional index syntax and the `<` flag when they make patterns hard to audit. In critical code, clear variable names and simple formats are usually easier to maintain than a string pieced together with many manual indices.

## 8. `%s`, `%%`, `%n`, and special characters

Non-numeric conversions are also essential:

| Conversion | Purpose | Example |
| --- | --- | --- |
| `%s` | Formats an object as a string | `String.format("%s", "cat")` → `"cat"` |
| `%.3s` | Limits string to at most 3 characters | `"abcdef"` → `"abc"` |
| `%b` | Boolean-like representation | `true` → `"true"`; `null` reference → `"false"` |
| `%c` | Character | `'A'` → `"A"` |
| `%%` | Prints a literal percent sign | `"Discount: 10%%"` → `"Discount: 10%"` |
| `%n` | Platform-specific line separator | Differs from hardcoding `\n` in a string |

Examples:

```java
String percent = String.format(Locale.US, "Discount: %d%%", 10);
// "Discount: 10%"

String row = String.format(Locale.US, "A%nB");
// has a platform-dependent newline between A and B
```

**`%n` does not consume an argument.** For multiline text requiring fixed byte-for-byte output across all operating systems, choose an explicit newline convention instead of defaulting to `%n`.

When logging data that may contain newlines or untrusted formatting, also consider escaping and logging policies to prevent log injection; formatters do not sanitize all data automatically.

## 9. Format string errors only appear at runtime

Java type-checks the syntax of `String.format` calls, but does not prove at compile time that the format string and arguments are **always compatible**.

Some exceptions under `java.util.IllegalFormatException`:

| Mistake | Example | Typical exception |
| --- | --- | --- |
| Wrong conversion for argument type | `String.format("%d", 1.25)` | `IllegalFormatConversionException` |
| Missing argument | `String.format("%d %d", 1)` | `MissingFormatArgumentException` |
| Invalid precision | `String.format("%.2d", 7)` | `IllegalFormatPrecisionException` |
| Unsupported conversion | `String.format("%q", 7)` | `UnknownFormatConversionException` |
| Invalid flag for conversion | `String.format("%#s", "a")` when argument is not `Formattable` | `FormatFlagsConversionMismatchException` |

The examples above are **deliberately erroneous** cases for explanation. Do not run them outside testing/error-handling mechanisms.

```java
try {
    String.format(Locale.US, "%d", 1.25);
} catch (java.util.IllegalFormatException ex) {
    System.out.println("invalid conversion");
}
```

When building APIs, avoid constructing format strings from untrusted data. Cleanly separate the format template defined by the program from the **content** provided by the user:

```java
String userText = "%n%n";
String safeAsArgument = String.format(Locale.US, "Input: %s", userText);
// "Input: %n%n" — userText is data for %s, not a format string
```

This does not replace context-specific output escaping (HTML/SQL/logs). It only reduces the risk of input data being interpreted as a format string.

### Beware `null` and arguments of other types

`String.format("%s", (Object) null)` can display `"null"`, and `String.format("%d", (Object) null)` displays `"null"` per Java's Formatter rules for null, not evidence of an integer 0. If business rules forbid missing data, validate inputs before formatting.

**Do not** use `%f` to automatically convert any `Integer` into a floating-point number. With `String.format("%.2f", 7)`, the argument is an `Integer`, and the formatter can throw `IllegalFormatConversionException`. To format a floating-point number, pass `7.0`, `Double.valueOf(7)`, or an appropriate `BigDecimal`.

## 10. Designing stable and clear output

We can categorize by goal:

| Goal | Recommendation |
| --- | --- |
| Short string for display | `String.format(locale, pattern, args)` |
| Print directly to console | `System.out.printf(locale, pattern, args)` |
| Multiple appends to a buffer | `Formatter` with `StringBuilder` |
| Percentages and column alignment | `%%`, `width`, `-` flag |
| Number reports with group separators | `%,d`, `%,.2f` per Locale |
| Machine-to-machine data exchange | Fix Locale/syntax; better to use a schema-compliant serializer instead of ad-hoc formatting |
| Exact decimal monetary values | Compute with appropriate type/method (often `BigDecimal`), format only at display time |

A formatter can round the **printed string**, but it does not turn imprecise measurements into exact data. If an application must store contractually finalized values, finalize them using numeric algorithms and the proper rounding mode, and only then use a formatter for presentation.

Do not repeatedly allocate new formatters in a hot loop merely for syntactic convenience if performance matters; benchmark and consider `StringBuilder` or suitable string assembly. Even so, the first priority remains **correct format, correct Locale, and a clear contract**.

## 11. Standalone runnable Java 17+ program

Create the file **`NumberFormattingDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Formatter;
import java.util.IllegalFormatException;
import java.util.Locale;

public class NumberFormattingDemo {
    public static void main(String[] args) {
        double amount = 12345.678;
        String text = String.format(Locale.US, "%,.2f", amount);
        System.out.println("formatted=" + text);
        System.out.println("original=" + amount);

        System.out.println("integer=" +
                String.format(Locale.US, "%d", 42));
        System.out.println("hex=" +
                String.format(Locale.US, "%#x", 255));
        System.out.println("octal=" +
                String.format(Locale.US, "%o", 8));
        System.out.println("signed=" +
                String.format(Locale.US, "%+08d", 42));
        System.out.println("negativePadded=" +
                String.format(Locale.US, "%05d", -42));
        System.out.println("leftAligned=" +
                String.format(Locale.US, "|%-6d|", 42));
        System.out.println("groupInteger=" +
                String.format(Locale.US, "%,d", 1234567));

        System.out.println("scientific=" +
                String.format(Locale.US, "%.3e", 12345.6));
        System.out.println("general=" +
                String.format(Locale.US, "%.4g", 12345.6));
        System.out.println("hexFloat=" +
                String.format(Locale.US, "%a", 3.5));
        System.out.println("negativeParen=" +
                String.format(Locale.US, "%(,.2f", -1234.5));
        System.out.println("negativeZero=" +
                String.format(Locale.US, "%.2f", -0.0));
        System.out.println("specialNaN=" +
                String.format(Locale.US, "%f", Double.NaN));
        System.out.println("specialInfinity=" +
                String.format(Locale.US, "%f", Double.POSITIVE_INFINITY));

        System.out.println("bigDecimal=" +
                String.format(Locale.US, "%.2f",
                        new BigDecimal("2.345")));
        System.out.println("germany=" +
                String.format(Locale.GERMANY, "%,.2f", 12345.67));
        System.out.println("positional=" +
                String.format(Locale.US, "%2$s=%1$04d", 7, "n"));
        System.out.println("reused=" +
                String.format(Locale.US, "%1$d / %<x", 31));
        System.out.println("percent=" +
                String.format(Locale.US, "Discount: %d%%", 10));

        StringBuilder buffer = new StringBuilder();
        try (Formatter formatter = new Formatter(buffer, Locale.US)) {
            formatter.format("item=%s", "pen");
            formatter.format(" qty=%d price=%.2f",
                    3, new BigDecimal("1.25"));
        }
        System.out.println("formatter=" + buffer);

        try {
            String.format(Locale.US, "%d", 1.25);
            System.out.println("invalidFormat=missed");
        } catch (IllegalFormatException ex) {
            System.out.println("invalidFormat=detected");
        }

        System.out.printf(Locale.US, "printfValue=%.2f%n", 2.5);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac NumberFormattingDemo.java
java NumberFormattingDemo
```

Output with the specified `Locale` and exact arguments above:

```text
formatted=12,345.68
original=12345.678
integer=42
hex=0xff
octal=10
signed=+0000042
negativePadded=-0042
leftAligned=|42    |
groupInteger=1,234,567
scientific=1.235e+04
general=1.235e+04
hexFloat=0x1.cp1
negativeParen=(1,234.50)
negativeZero=-0.00
specialNaN=NaN
specialInfinity=Infinity
bigDecimal=2.35
germany=12.345,67
positional=n=0007
reused=31 / 1f
percent=Discount: 10%
formatter=item=pen qty=3 price=1.25
invalidFormat=detected
printfValue=2.50
```

For the program to print an extra line via `printf`, it uses `%n` (the OS line separator). The visible text looks identical across common platforms; **the newline byte sequence** may differ by environment.

## 12. Common mistakes and checklist

| Claim | Reality |
| --- | --- |
| "`String.format` prints the result automatically." | False: it returns a `String`; `printf` writes to a stream. |
| "`printf` always adds a newline." | False: the pattern must include `%n` or a newline must be printed separately. |
| "`%.2f` makes `double` hold exact two decimal digits." | False: formatting only produces text; the source value is unchanged. |
| "`%,.2f` always uses commas for grouping and a dot for the decimal point." | False: `Locale` affects how it is displayed. |
| "`%.4g` has four digits after the decimal point." | False: `g` uses significant-digit precision. |
| "`%8d` truncates any number longer than 8 characters." | False: `width` is a **minimum**. |
| "`%d` automatically converts a `double` to `int`." | False: it can throw `IllegalFormatConversionException`. |
| "`%n` is everywhere identical to `\n`." | False: `%n` uses the platform newline. |
| "`%2$s` references argument index 2 in Java zero-based indexing." | False: indexing starts at 1. |
| "`Formatter` is just another name for `String.format`." | No: it is a formatting object with its own destination and lifecycle. |
| "An invalid format string is always caught by the compiler." | No: many errors only throw `IllegalFormatException` at runtime. |
| "Printing `NaN` or `Infinity` means the input parser broke." | No: these are valid `float`/`double` representation values; handle them according to policy. |

Before formatting numbers, check yourself:

1. **Is the goal to return a string, print to a stream, or write to a buffer?** Choose `String.format`, `printf`, or `Formatter`.
2. **What is the actual type of the argument?** Choose `%d` for integers, `%f`/`%e`/`%g` for appropriate floating-point numbers; do not assume the formatter coerces all types.
3. **What does precision mean here?** `%.2f` is two digits after the decimal point; `%.4g` is four significant digits.
4. **Is the output Locale-dependent?** Fix the Locale in tests, machine logs, or data exchange.
5. **Can the format fail at runtime?** Check specifiers, flags, argument counts, and conversions; test critical patterns.
6. **Is formatting being mixed up with business rounding?** Do not use formatted strings in place of computed values unless the contract calls for it.
7. **How are special values and negative zero handled?** Consider `NaN`, `Infinity`, `-0.0`, and external protocols before outputting.

**Takeaway:** `String.format` **returns a string**, `printf` **prints to a stream**, and `Formatter` **formats into a specific destination**. They share `%...` syntax, yet you must still pick the right **conversion, precision, width, flags, and Locale**, while keeping **number presentation** separate from **business calculation and rounding**.