# String.format, String.formatted, and Formatter in Java

## 1. Why Do We Need String Formatting?

When creating messages, reports, logs, or data lines presented to readers, we often want to combine **fixed text** with values of different types: strings, integers, floating-point numbers, dates and times. Concatenating many segments with the `+` operator can make code long and hard to align. Java provides three APIs all based on **format string syntax**:

- `String.format(...)`: creates a new `String` from a format template and arguments.
- `String.formatted(...)`: invokes the format template as a method on the `String` itself, since Java 15.
- `java.util.Formatter`: a stateful formatting object that can write multiple times to a destination such as `StringBuilder` or `Appendable`.

Lesson objectives: read `%...` specifiers accurately, control width and decimal places, choose the right `Locale`, distinguish the three APIs, know how to handle formatting errors, and choose the appropriate tool.

## 2. String.format: One-Time Formatting into a String

Two important overloads:

```java
public static String format(String format, Object... args);

public static String format(Locale l, String format, Object... args);
```

The first argument is a **template** containing fixed text and *format specifiers* (symbols starting with `%`). Subsequent arguments supply values to substitute into those positions.

```java
import java.util.Locale;

String text = String.format(
        Locale.US,
        "Name: %s | Age: %d | Score: %.2f",
        "An", 20, 8.75
);
// "Name: An | Age: 20 | Score: 8.75"
```

In this example: `%s` represents a string, `%d` represents a decimal integer, and `%.2f` displays a floating-point number with **2 digits after the decimal point**. `Locale.US` keeps the decimal point consistent, even when the machine running the code uses a different locale.

If `Locale` is not passed, `String.format(String, Object...)` uses the JVM's **default FORMAT locale** (`Locale.getDefault(Locale.Category.FORMAT)`). Therefore, the same numeric format template can produce different separators on two machines. When results must be consistent in documentation, tests, or inter-system communication, pass a locale explicitly.

`String.format` returns a new string without modifying the template variable, arguments, or source `String`.

## 3. String.formatted: Concise Formatting from a String Template

Since Java 15, `String` has a method that directly expresses the relationship "this template is formatted with the following values":

```java
public String formatted(Object... args);
```

Example:

```java
String title = "Hello %s, you have %d notifications."
        .formatted("Linh", 3);

// "Hello Linh, you have 3 notifications."
```

Compare two approaches with the same purpose:

```java
String a = String.format("Code: %s, quantity: %d", "P01", 7);
String b = "Code: %s, quantity: %d".formatted("P01", 7);
```

In the same locale environment, `a` and `b` have the same content. `formatted(...)` is convenient when the string template is already available as a `String` expression, such as a multi-line text block. It uses `Formatter` formatting rules, similar to `String.format`.

**Key difference to remember:** `String.formatted(...)` **has no overload accepting `Locale`**. When you need to format numbers or dates according to a specific locale, choose `String.format(locale, template, args...)` or a `Formatter` configured with a locale. Both `format` and `formatted` create a new `String` result.

## 4. Format Specifier Structure: Enough to Get Started

All three APIs use `Formatter` syntax: `%[argument_index$][flags][width][.precision]conversion`. Square brackets are notation describing optional components, not characters typed into the template. Argument indices start at **1**; `conversion` determines the value type, such as `%s` (string), `%d` (integer), `%f` (floating-point), `%tF` (date). `%%` prints a percent sign and `%n` inserts a platform-specific line separator; these two symbols do not consume arguments.

```java
String line = String.format(Locale.US, "%s: %d items, total %.2f", "Cart", 3, 12.5);
// "Cart: 3 items, total 12.50"
```

This is the shared syntax layer that helps you understand all three APIs. Thoroughly analyzing all combinations of indices, flags, and conversions is the focus of the subsequent in-depth lessons in this chapter.

## 5. Width, Precision, and Flags: Essential Differences

`width` is the **minimum width** of the output field; it does not automatically truncate text. The `-` sign left-aligns; the `0` flag zero-pads compatible numeric types. `precision` depends on the conversion: `%.2f` prints two decimal digits, whereas `%.3s` limits a string to at most three characters.

```java
String s = String.format(Locale.US, "|%-6s|%04d|%.2f|", "AB", 7, 2.5);
// "|AB    |0007|2.50|"
```

Not every flag or precision is compatible with every conversion: for example, `%.2d` and `%05s` are invalid. Formatting only changes the output text; it does not round or modify the original data variable.

## 6. Reselecting or Reordering Arguments

Normally `%s` and `%d` receive arguments sequentially from left to right. `%2$s` selects the second argument, while `%1$d` selects the first argument; the `<` flag reuses the argument of the preceding specifier that took an argument.

```java
String reordered = String.format("%2$s bought %1$d items", 3, "Lan");
// "Lan bought 3 items"
String reused = String.format("%s -> %<S", "java");
// "java -> JAVA"
```

Specifying argument indices is useful when a message changes word order. For full language localization of complete sentences, this chapter also introduces `MessageFormat` and `ResourceBundle`.

## 7. Locale Belongs to the Output, Not the Template

`String.format(format, args)` and `String.formatted(args)` use the default locale for formatting (`Locale.Category.FORMAT`). `String.format(locale, format, args)` lets you explicitly choose conventions for decimal points, digit grouping, or uppercase letters; the fixed template text itself is not automatically translated.

```java
String us = String.format(Locale.US, "%,.2f", 12345.5);       // 12,345.50
String de = String.format(Locale.GERMANY, "%,.2f", 12345.5);  // 12.345,50
```

Choose the locale for the reader; when data is meant for machines, follow the protocol's serialization standard. Do not change `Locale.setDefault` per request in a multithreaded application.

## 8. Formatter: Formatting Multiple Times to the Same Destination

`Formatter` belongs to `java.util` and implements `Closeable` and `Flushable`. It has similar `format(...)` calls, but writes to an **output destination** attached to the object. The destination can be a `StringBuilder`, `Writer`, `OutputStream`, or objects supporting compatible writing mechanisms, depending on the constructor.

Example writing sequentially to a `StringBuilder`:

```java
import java.util.Formatter;
import java.util.Locale;

StringBuilder builder = new StringBuilder();

try (Formatter formatter = new Formatter(builder, Locale.US)) {
    formatter.format("Code: %04d; ", 7);
    formatter.format("Price: %,.2f", 1234.5);
}

System.out.println(builder);
// Code: 0007; Price: 1,234.50
```

`format(...)` on `Formatter` returns the `Formatter` itself, so calls can be chained. In the example, both calls write to the same `builder`; `StringBuilder` remains readable after closing the `Formatter`. Use `try-with-resources` to close `Formatter` when no longer needed, especially when the destination is a managed I/O resource.

Note that **closing `Formatter` may also close the output destination** if the destination is also `Closeable`. Do not create a `Formatter` and close it on `System.out` when you still need to continue writing to the console. You can use `System.out.printf(...)` or `System.out.format(...)` to write directly to standard output in simple cases.

`Formatter` also has `locale()` to inspect the associated locale and `ioException()` to check for any `IOException` recorded by the formatter while operating on the output destination. When writing to a file or stream, do not just inspect the resulting string and ignore I/O status. A shared `Formatter` object should also not be assumed thread-safe when called concurrently by multiple threads; manage concurrent access yourself if needed.

## 9. Standalone Runnable Java 17+ Program

Create a file named `FormattingDemo.java` with the following complete content:

```java
import java.time.LocalDate;
import java.util.Formatter;
import java.util.Locale;

public class FormattingDemo {
    public static void main(String[] args) {
        Locale us = Locale.US;

        String product = String.format(
                us, "Product: %s | Qty: %d | Price: %,.2f",
                "Pen", 3, 1234.5);
        System.out.println(product);

        String greeting = "Hello %s (%d years old)"
                .formatted("Mai", 21);
        System.out.println(greeting);

        System.out.println(
                String.format(us, "|%8s|%-8s|", "cat", "dog"));

        System.out.println(
                String.format(us,
                        "%2$s bought %1$d items; %2$s has paid.",
                        3, "Lan"));

        System.out.println(
                String.format(us,
                        "Date: %tF", LocalDate.of(2026, 10, 23)));

        System.out.println(
                String.format(us, "US: %,.2f", 12345.5));
        System.out.println(
                String.format(Locale.GERMANY,
                        "DE: %,.2f", 12345.5));

        StringBuilder builder = new StringBuilder();
        try (Formatter formatter = new Formatter(builder, us)) {
            formatter.format("A=%04d; ", 7);
            formatter.format("B=%.1f", 2.5);
        }
        System.out.println(builder);
    }
}
```

Compile and run (ensure the source file is saved as UTF-8):

```bash
javac -encoding UTF-8 FormattingDemo.java
java FormattingDemo
```

Exact stdout output:

```text
Product: Pen | Qty: 3 | Price: 1,234.50
Hello Mai (21 years old)
|     cat|dog     |
Lan bought 3 items; Lan has paid.
Date: 2026-10-23
US: 12,345.50
DE: 12.345,50
A=0007; B=2.5
```

The lines illustrate `String.format`, `String.formatted`, alignment, argument indices, date formatting, locale, and reusing `Formatter`, respectively. The example chooses a deterministic date and explicit `Locale` for locale-sensitive conversions so the output is easy to verify.

## 10. Date and Time in Formatter

`%tF` formats a date as `yyyy-MM-dd`; `%tT` formats time as `HH:mm:ss`, if the argument actually provides the required time fields. For example, `String.format(Locale.US, "%tF", LocalDate.of(2026, 10, 23))` yields `2026-10-23` (requires importing `LocalDate`). `LocalDate` does not have an hour to use with `%tT`. Requirements involving parsing, time zones, or rich date-time patterns should use `DateTimeFormatter`.

## 11. Input Errors and Formatting Exceptions

The compiler usually does not check compatibility between conversions and arguments. For example, `%d` with the string `"42"` causes `IllegalFormatConversionException`, missing arguments cause `MissingFormatArgumentException`, and invalid flags/precision can cause other subclasses of `IllegalFormatException`. Passing `(Object) null` to `%s` displays `"null"`, while `%b` with the string `"false"` gives `"true"` because it is a non-null object.

For user-supplied text containing `%`, pass that text as an `%s` argument rather than treating it as a format string. Choose `%%` when you want to print a percent sign directly in the template; use `%n` for platform-dependent line endings, or `\n` when a protocol requires a fixed LF. When closing a `Formatter` attached to an I/O destination, remember to check and manage the destination's lifecycle as described in Section 8.

## 12. Choosing the Right API

| Need | Recommendation | Reason |
| --- | --- | --- |
| A single message, explicitly specifying locale | `String.format(Locale, ...)` | Template, arguments, and locale are clear in one call |
| A short `String` template, using default locale | `template.formatted(args)` | Reads naturally when the template is the receiver |
| Incrementally building multiple formatted segments | `Formatter` + `StringBuilder` | Can call `format` multiple times onto the same destination |
| Printing directly to stdout | `System.out.printf(...)` or `format(...)` | No need to create an intermediate string if only printing is needed |
| Complex dates and times | `DateTimeFormatter` | Controls patterns, locales, and temporal types |
| Numbers following specialized currency/display rules | Appropriate `NumberFormat` or `DecimalFormat` | Has dedicated rules for representing numbers and currencies |

These tools are not mutually exclusive. For example, a program can use `DateTimeFormatter` to build the date portion according to custom rules, then pass that string into `String.format` alongside other fields.

## 13. Self-Practice Exercises: Choosing the Right API

**Exercise 1.** You need to build a report string with stable US number separators. Choose `String.format(Locale.US, "Total: %,.2f", 1234.5)` to get `"Total: 1,234.50"`.

**Exercise 2.** The template is already in the variable `String template = "Hello %s"`, and only the default locale is needed. Use `template.formatted("Mai")`, resulting in `"Hello Mai"`. If a specific locale is needed, switch to `String.format(locale, template, "Mai")`.

**Exercise 3.** You need to write multiple times to a `StringBuilder` without creating many intermediate strings: create `Formatter(builder, locale)` and call `format(...)` successively. Then close the formatter; if the destination is `Closeable`, closing the formatter may also close the destination, so manage resources intentionally.

## 14. Key Takeaways

1. `String.format` is a **static** method, suited for one-off formatting and offers an overload accepting `Locale`.
2. `String.formatted` is an **instance** method since Java 15, concise when the format template is already a `String`; it has no `Locale` overload.
3. `Formatter` is an object that can **write multiple times to the same destination** and requires attention to resource lifecycles, especially when the destination is an I/O stream.
4. A format specifier has the order `%[index$][flags][width][.precision]conversion`; **width** and **precision** have different meanings.
5. Choose the right conversion for the **actual data type**; wrong types, missing arguments, or invalid flags can cause runtime exceptions.
6. For consistent results, specify `Locale` explicitly. Formatting for display does not replace parsing, exact arithmetic, or serialization.

Official references: [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html), [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html).
