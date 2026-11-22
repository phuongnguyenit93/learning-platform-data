# `null` Arguments and Common `IllegalFormatException`s in Java

## Objectives

After this lesson, you will be able to predict how `String.format()` handles `null` arguments, distinguish errors caused by argument values from errors caused by format strings, recognize common formatting exceptions, and choose appropriate handling when creating messages, logs, or display strings.

## 1. Why Can String Formatting Fail?

`String.format()`, `System.out.printf()`, `Formatter.format()`, and `String.formatted()` use the rules of `java.util.Formatter`. A typical specifier has the form:

```text
%[argument_index$][flags][width][.precision]conversion
```

For example: `%2$-10.3s` takes the second argument, left-aligns it in a minimum width of 10, and takes at most 3 string characters. `%d` is for integers, `%f` is for floating-point numbers, `%s` renders an object's string representation, `%b` renders a boolean representation, and `%tY` formats the year of a date/time value. The two specifiers `%%` (percent character) and `%n` (platform-specific newline) do not consume arguments.

`Formatter` validates syntax, flags, width, precision, argument indices, and data type compatibility. If invalid, it throws a subclass of `IllegalFormatException` (an unchecked exception in the `IllegalArgumentException` family). A distinct case is a `null` format string: for example, `String.format((String) null, "x")` throws `NullPointerException`, not `IllegalFormatException`.

## 2. `null` Arguments: Concrete Results

A common misconception is that every `null` argument causes `NullPointerException` or `IllegalFormatConversionException`. According to the `Formatter` specification, for general, character, numeric, and date/time conversions, `null` is normally represented by the text `null`; `%b`/`%B` is a notable exception because `null` is represented as `false`/`FALSE`.

| Specifier | Actual Argument Is `null` | Output |
| --- | --- | --- |
| `%s` / `%S` | `(Object) null` | `null` / `NULL` |
| `%b` / `%B` | `(Object) null` | `false` / `FALSE` |
| `%h` / `%H` | `(Object) null` | `null` / `NULL` |
| `%d`, `%f`, `%c`, `%tY` | `(Object) null` | `null` |

Complete example, runnable on Java 17+:

```java
import java.util.Locale;

public class FormatterNullDemo {
    public static void main(String[] args) {
        Object absent = null;

        System.out.println("string=[" + String.format(Locale.ROOT, "%s", absent) + "]");
        System.out.println("boolean=[" + String.format(Locale.ROOT, "%b", absent) + "]");
        System.out.println("hash=[" + String.format(Locale.ROOT, "%h", absent) + "]");
        System.out.println("integer=[" + String.format(Locale.ROOT, "%d", absent) + "]");
        System.out.println("decimal=[" + String.format(Locale.ROOT, "%f", absent) + "]");
        System.out.println("char=[" + String.format(Locale.ROOT, "%c", absent) + "]");
        System.out.println("year=[" + String.format(Locale.ROOT, "%tY", absent) + "]");
        System.out.println("uppercase=[" + String.format(Locale.ROOT, "%S", absent) + "]");
    }
}
```

Save as `FormatterNullDemo.java`, then run:

```bash
javac FormatterNullDemo.java
java FormatterNullDemo
```

Output:

```text
string=[null]
boolean=[false]
hash=[null]
integer=[null]
decimal=[null]
char=[null]
year=[null]
uppercase=[NULL]
```

Three distinctions must be made:

- `null` **is not** a valid integer, float, or date; `Formatter` uses a special display rule for absent values. A **non-null value of the wrong type** still causes an error: `String.format("%d", "42")` throws `IllegalFormatConversionException` because `"42"` is a `String`, not an integer type accepted by `%d`.
- `%b` does not coerce strings to booleans. With `Boolean.TRUE`, the output is `true`; with `Boolean.FALSE` or `null`, the output is `false`; **any non-null object that is not a `Boolean`** is also formatted as `true`. Thus `String.format("%b", "false")` yields `true`.
- `null` can mask missing data. For instance, an amount column showing `null` or an optional flag showing `false` does not prove the source data is valid.

### Varargs Note: Single `null` vs. `null` Argument Array

The signature `String.format(String format, Object... args)` uses varargs. When you need **one argument** whose value is `null`, write `(Object) null` explicitly or pass an `Object` variable set to `null`:

```java
String oneNull = String.format("%s", (Object) null);
String twoNulls = String.format("%s|%s", (Object[]) null);
```

`oneNull` is `"null"`. In `Formatter`, the `null` varargs array in the second example is treated as all arguments being `null`, so `twoNulls` is `"null|null"`. Even though the outputs look similar, **`(Object) null` and `(Object[]) null` do not express the same intent at the call site**. Writing `String.format("%s", null)` directly can produce a compiler warning about an ambiguous varargs call; casting or using an explicit variable removes the ambiguity.

## 3. Recognizing Common `IllegalFormatException`s

The classes below belong to `java.util`; the subclass name usually indicates which part of the specifier is wrong. The table uses intentionally failing examples that are independent of one another.

| Exception | Example | Cause and Fix |
| --- | --- | --- |
| `IllegalFormatConversionException` | `String.format("%d", "42")` | Conversion does not accept the argument type; change to number `42` or use `%s`. |
| `MissingFormatArgumentException` | `String.format("%s %s", "A")` | Specifier requires another argument; pass enough arguments or fix placeholder count. |
| `UnknownFormatConversionException` | `String.format("%q", 1)` | `q` is not a valid conversion character; use `%s` or another valid type. |
| `FormatFlagsConversionMismatchException` | `String.format("%#s", "A")` | Flag `#` is not supported for `%s` with an ordinary `String`; remove the flag. |
| `DuplicateFormatFlagsException` | `String.format("%--5s", "A")` | Flag `-` is repeated; change to `%-5s`. |
| `IllegalFormatFlagsException` | `String.format("%-05d", 42)` | Flags `-` and `0` conflict; use only one alignment style. |
| `MissingFormatWidthException` | `String.format("%0d", 42)` | Flag `0` requires a width; e.g., use `%05d`. |
| `IllegalFormatPrecisionException` | `String.format("%.2d", 42)` | `%d` does not support precision; use `%d` or format the value beforehand. |
| `IllegalFormatWidthException` | `String.format("%5n")` | `%n` does not accept width; use `%n`. |
| `IllegalFormatCodePointException` | `String.format("%c", 0x110000)` | Unicode code is outside valid code point range; validate with `Character.isValidCodePoint()`. |

Do not assume an exception class name always reveals every detail of the cause: a single format string may contain multiple errors, and `Formatter` reports the first one encountered during validation. `IllegalFormatException` also has rarer subclasses such as `UnknownFormatFlagsException`; there is no need to instantiate these exception classes yourself when merely formatting strings.

### Running a Test and Reading Exact Exception Names

```java
import java.util.IllegalFormatException;
import java.util.List;
import java.util.Locale;

public class FormatErrorsDemo {
    private record Sample(String label, String format, Object[] args) {}

    public static void main(String[] args) {
        List<Sample> examples = List.of(
                new Sample("wrong-type", "%d", new Object[]{"42"}),
                new Sample("missing-arg", "%s %s", new Object[]{"A"}),
                new Sample("unknown-conversion", "%q", new Object[]{1}),
                new Sample("flag-mismatch", "%#s", new Object[]{"A"}),
                new Sample("duplicate-flag", "%--5s", new Object[]{"A"}),
                new Sample("conflicting-flags", "%-05d", new Object[]{42}),
                new Sample("missing-width", "%0d", new Object[]{42}),
                new Sample("invalid-precision", "%.2d", new Object[]{42}),
                new Sample("invalid-width", "%5n", new Object[]{}),
                new Sample("invalid-codepoint", "%c", new Object[]{0x110000})
        );

        for (Sample example : examples) {
            try {
                String.format(Locale.ROOT, example.format(), example.args());
                System.out.println(example.label() + " => OK");
            } catch (IllegalFormatException error) {
                System.out.println(example.label() + " => "
                        + error.getClass().getSimpleName());
            }
        }
    }
}
```

Save as `FormatErrorsDemo.java`, compile, and run:

```bash
javac FormatErrorsDemo.java
java FormatErrorsDemo
```

Deterministic output:

```text
wrong-type => IllegalFormatConversionException
missing-arg => MissingFormatArgumentException
unknown-conversion => UnknownFormatConversionException
flag-mismatch => FormatFlagsConversionMismatchException
duplicate-flag => DuplicateFormatFlagsException
conflicting-flags => IllegalFormatFlagsException
missing-width => MissingFormatWidthException
invalid-precision => IllegalFormatPrecisionException
invalid-width => IllegalFormatWidthException
invalid-codepoint => IllegalFormatCodePointException
```

The program above catches `IllegalFormatException` strictly for learning purposes. In real applications, it is usually best to fix the format string right where the code is written; do not catch broadly and silently swallow exceptions, allowing invalid data to keep flowing through the system.

## 4. Errors from Counting and Selecting Arguments

Note that `%s`, `%d`, and `%f` consume arguments; `%%` and `%n` do not. `Formatter` has three ways to select arguments:

- **Sequential**: `"%s %d"` uses arguments 1 and 2 in order.
- **Positional**: `"%2$s %1$s"` takes the second argument first, then the first; indices are 1-based.
- **Reusing the previous argument**: `"%s %<s"` uses one argument twice; `%<s` at the start, with no preceding argument, causes `MissingFormatArgumentException`.

`String.format("%s", "A", "B")` simply yields `"A"`: extra arguments are ignored and do **not** throw an exception. Conversely, `String.format("%2$s", "A")` throws `MissingFormatArgumentException` because index 2 does not exist. Passing `null` and **failing to pass enough arguments** are two distinct situations; only the latter produces a missing-argument error.

When checking messages with multiple placeholders, write down the count, data type, and index of each argument and compare them against the specifiers. If you need a literal `%` in the text, use `%%`; if you need a platform-dependent line ending, use `%n`; if output requires a fixed LF, use `\n` in the Java string.

## 5. Safe Handling in Real Code

### Define a Policy When Data May Be `null`

If `null` is invalid under business rules, check it before formatting instead of letting `Formatter` print the word `null`:

```java
import java.util.Locale;
import java.util.Objects;

public class RequiredAmount {
    public static String label(Integer amount) {
        int present = Objects.requireNonNull(amount, "amount is required");
        return String.format(Locale.ROOT, "Amount: %d", present);
    }
}
```

This is an illustrative method (no `main`). `Objects.requireNonNull` fails early with a `NullPointerException` carrying a clear message; it expresses a requirement that **data must be present**, distinct from a format syntax error. If `null` is a valid state, represent it intentionally:

```java
import java.util.Locale;

public class OptionalAmount {
    public static String label(Integer amount) {
        return amount == null
                ? "Amount: no data yet"
                : String.format(Locale.ROOT, "Amount: %d", amount);
    }
}
```

If you need a string from an arbitrary object, `String.valueOf(value)` also returns `"null"` when `value == null`; use it only when that representation is genuinely appropriate. For a three-state boolean flag (`true`, `false`, `null`), do not use `%b` in order to preserve the distinction between "unknown" and `false`.

### Keep Format Strings Fixed and Correctly Typed

Instead of treating external input as the format string itself:

```java
// Input data is content, not formatting syntax.
String userText = "20% off";
String message = String.format(Locale.ROOT, "Note: %s", userText);
```

`message` is `"Note: 20% off"`. `%s` will not interpret the `%` character inside `userText` as a new placeholder. This is much safer to control than passing `userText` as the `format` argument, which can lead to unintended placeholders or exceptions if input contains `%`.

Prefer constants or format strings verifiable by tests. Use `Locale.ROOT`/`Locale.US` when stable output is desired; use the user's actual `Locale` for display text containing region-formatted numbers or dates. Remember that `%f` applies to compatible floating-point types, whereas `%d` applies to compatible integer types; `Formatter` does not automatically parse `"42"` into a number.

### Handle Exceptions at Appropriate Boundaries

In dynamic content-generation libraries that genuinely must read format templates from configuration, you can catch `IllegalFormatException` at the configuration boundary to return a contextual error (template pattern, list of argument types, configuration location). Avoid logging sensitive argument contents. When an error comes from a hardcoded format string, fixing it at the source and adding tests is better than using `catch` to silently fall back to `"null"`.

## 6. Misconceptions to Avoid

1. **"`%d` encountering `null` will always throw `IllegalFormatConversionException`."** False: `null` is rendered as `"null"`; a **non-null incompatible** argument like `"42"` is what triggers this exception.
2. **"`%b` parses the string `"false"`."** False: any non-`Boolean` object, if non-`null`, yields `true`.
3. **"Passing extra arguments causes an error."** False: unreferenced arguments are ignored, which can make logic bugs harder to spot.
4. **"`%n` and `%%` each take an argument."** False: they do not consume arguments.
5. **"`%.2d` means print an integer with two digits."** False: precision does not apply to `%d`; `%02d` is what requests minimum width 2 with zero-padding.
6. **"Catching `IllegalFormatException` catches all formatting errors."** False: for instance, a `null` format string throws `NullPointerException`; other code errors do not necessarily belong to this exception family either.

## 7. Self-Check

Predict the output or exception of each call below, then verify with `jshell`:

```java
String.format("%s", (Object) null)
String.format("%b", "false")
String.format("%d", (Object) null)
String.format("%d", "12")
String.format("%s %s", "A")
String.format("%2$s-%1$s", "A", "B")
String.format("100%% %s", "OK")
String.format("%05d", 42)
```

Answers in order: `"null"`; `"true"`; `"null"`; `IllegalFormatConversionException`; `MissingFormatArgumentException`; `"B-A"`; `"100% OK"`; `"00042"`.

Official references for further lookup: [`java.util.Formatter` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html) and [`java.util.IllegalFormatException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IllegalFormatException.html).
