# Distinguishing MessageFormat from String.format and Formatter

## 1. Three APIs That All Build Strings, Solving Different Problems

When building a multilingual Java application, we often need to insert user names, monetary amounts, dates, or counts into text. Java provides three tools that are easily confused:

- **`java.text.MessageFormat`**: builds **user-facing messages** from a *sentence pattern* with numbered arguments `{0}`, `{1}`. Patterns can be translated into other languages, reorder arguments, and choose number/date formatting per `Locale`.
- **`String.format(...)`**: builds a string using **`printf`** syntax, such as `%s`, `%d`, `%,.2f`, `%1$s`. Suited for number presentation, alignment, logging, test output, or structured strings.
- **`java.util.Formatter`**: the **engine behind `printf`-style formatting**, able to write multiple times into an `Appendable` such as `StringBuilder`, `Writer`, or `System.out`, with its own state and lifecycle.

All three can accept a `Locale`, yet **their pattern syntax, argument handling, localization suitability, date/time behavior, and object lifecycle characteristics differ**.

| Question | `MessageFormat` | `String.format` | `Formatter` |
| --- | --- | --- | --- |
| Pattern input | `"Hello {0}"` | `"Hello %s"` | `formatter.format("Hello %s", name)` |
| Arguments | **0-based** indices `{0}`, `{1}` | Positional by default; explicit **1-based** indices `%1$s`, `%2$d` | Same syntax as `String.format` |
| Primary focus | Translated sentences, reordering message components | Presentation strings, width, precision, flags | Appending multiple formatted outputs to one destination |
| Locale-sensitive numbers/dates | Via `{0,number}`, `{0,date}`, and subformats | Via corresponding conversions like `%,.2f`, `%tF` | Same `printf`-style semantics |
| Reordering parameters in translations | Natural with `{1}`, `{0}` | Possible with `%2$s`, `%1$s`, but patterns are harder for translators to read | Same as `String.format` |
| Patterns typically stored in ResourceBundle | Very well suited | Usable, but requires understanding `printf` syntax | Usable, same `printf` constraints |
| Return type | `String` or writes into `StringBuffer` | Returns `String` | Writes to `Appendable`, returns `Formatter` for chaining |
| Multithreading | `MessageFormat` is not synchronized | Each call performs independent formatting work | A shared `Formatter` is not guaranteed thread-safe |

**Selection rule:** for **translatable sentences**, prefer `ResourceBundle` + `MessageFormat`; for **technical strings, tables, column widths, precision, and metrics**, use `String.format`; when you need to **write multiple formatted segments into the same destination**, use `Formatter`.

## 2. Syntax: `{0}` vs. `%s`

### 2.1. MessageFormat: 0-Based Argument Indexing

Structure of `MessageFormat` replacement elements:

~~~text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
~~~

Example:

~~~text
"Hello {0}, you have {1,number,integer} notifications."
~~~

Where:

- `{0}` is the **first argument**.
- `{1,number,integer}` is the **second argument**, formatted using integer rules appropriate for the `Locale`.
- Standard Java 17 `formatType` values are `number`, `date`, `time`, and `choice`.
- Valid `formatStyle` values include `integer`, `currency`, `percent`, `short`, `medium`, `long`, `full`, or a subformatter-specific pattern.

Direct example:

~~~java
MessageFormat message = new MessageFormat(
        "Chào {0}, bạn có {1,number,integer} thông báo.",
        Locale.forLanguageTag("vi-VN")
);
String output = message.format(new Object[]{"Lan", 3});
~~~

This is an **in-method code fragment**, requiring imports for `java.text.MessageFormat` and `java.util.Locale`. The result follows the locale's numeric conventions (the argument `3` needs no grouping separator). Crucially, argument order can change in the **pattern** without changing the data-supplying code.

### 2.2. String.format and Formatter: `printf` Syntax

For a typical conversion:

~~~text
%[argument_index$][flags][width][.precision]conversion
~~~

Common components:

| Syntax | Purpose |
| --- | --- |
| `%s` | String representation of an object |
| `%d` | Integer |
| `%f` / `%.2f` | Floating-point / two digits after the decimal point |
| `%,.2f` | Adds locale grouping, displays two decimal places |
| `%10s` / `%-10s` | Minimum width 10, right-aligned / left-aligned |
| `%04d` | Zero-padded to width 4 |
| `%1$s` / `%2$s` | References the **first / second** argument |
| `%%` | Prints a literal percent sign `%` |
| `%n` | Prints a platform-specific line separator, consuming no argument |

**Indexing note:** `MessageFormat` starts at **`0`**, whereas explicit indices in `Formatter` start at **`1$`**. `%0$s` is not a valid argument index in `printf` syntax.

Example:

~~~java
String output = String.format(
        Locale.US,
        "Hello %1$s, count=%2$04d, cost=%3$,.2f",
        "Lan", 7, 1234.5
);
~~~

This is an in-method snippet importing `java.util.Locale`. Output:

~~~text
Hello Lan, count=0007, cost=1,234.50
~~~

`String.format` specifies precision/width/flags explicitly, which helps produce fixed-layout report lines. `MessageFormat` is stronger at representing **translatable sentence patterns** and using localized subformats.

## 3. Runnable Example: Same Data, Three Approaches

Create the file `FormatComparisonDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Formatter;
import java.util.Locale;

public class FormatComparisonDemo {
    public static void main(String[] args) {
        String name = "Lan";
        double amount = 1234.5;

        // 1. Sentence pattern with 0-based numbered parameters.
        MessageFormat message = new MessageFormat(
                "Hello {0}, balance: {1,number,#,##0.00}",
                Locale.US
        );
        System.out.println("MessageFormat: "
                + message.format(new Object[]{name, amount}));

        // 2. printf-style pattern, arguments starting at 1.
        String oneShot = String.format(
                Locale.US,
                "Hello %1$s, balance: %2$,.2f",
                name, amount
        );
        System.out.println("String.format: " + oneShot);

        // 3. Writing multiple times into the same StringBuilder.
        StringBuilder destination = new StringBuilder();
        try (Formatter formatter =
                     new Formatter(destination, Locale.US)) {
            formatter.format("Hello %s", name);
            formatter.format(", balance: %,.2f", amount);
        }
        System.out.println("Formatter: " + destination);
    }
}
~~~

Compile and run on Java 17+:

~~~bash
javac -encoding UTF-8 FormatComparisonDemo.java
java FormatComparisonDemo
~~~

Output:

~~~text
MessageFormat: Hello Lan, balance: 1,234.50
String.format: Hello Lan, balance: 1,234.50
Formatter: Hello Lan, balance: 1,234.50
~~~

Identical output, different mechanisms:

1. `MessageFormat` accepts `Object[]`, substituting `{0}` and `{1}`. Subpattern `#,##0.00` is interpreted by `DecimalFormat` using `Locale.US` symbols.
2. `String.format` accepts varargs, processing `%1$s` and `%2$,.2f` using `Formatter` syntax. It does not parse `MessageFormat` patterns.
3. `Formatter` takes a `StringBuilder` as its destination and appends two format calls. Closing `Formatter` finishes using the formatter object; `StringBuilder` still retains the text and can be read via `toString()`.

**You cannot mechanically pass** `"Hello {0}"` as input to `String.format`, nor pass `"Hello %s"` directly into `MessageFormat` expecting its syntax to be interpreted. Each tool has its own pattern parser.

## 4. Localizing Messages: Why MessageFormat Fits Better

A good translation may need to change **the order of components**, not just translate word for word. For example, language A wants "{name} ordered {quantity}", while language B wants "Ordered {quantity} for {name}". If you concatenate strings with `+` or rely purely on the programmer's code order, translators struggle to adjust sentence structure.

`MessageFormat` uses argument indices so translators keep the right data while changing order:

~~~java
MessageFormat first = new MessageFormat(
        "{0} ordered {1,number,integer} items.", Locale.US
);
MessageFormat second = new MessageFormat(
        "Đã đặt {1,number,integer} món cho {0}.",
        Locale.forLanguageTag("vi-VN")
);

Object[] args = {"Lan", 3};
System.out.println(first.format(args));
System.out.println(second.format(args));
~~~

The snippet above imports `java.text.MessageFormat;` and `java.util.Locale;`. With count `3`, the two outputs are:

~~~text
Lan ordered 3 items.
Đã đặt 3 món cho Lan.
~~~

**Distinction from `String.format`:** `%2$d` and `%1$s` syntax also allows reordering arguments, but translators have to understand data-type-specific conversions, flags, precision, and `%` escaping. For a **translated sentence** needing number/date formatting and structural reordering, `MessageFormat` expresses intent more directly.

### Combining Properly with `ResourceBundle`

In an application, patterns should not be hardcoded for every language. A simple structure:

~~~text
demo/
├── LocalizedMessageDemo.java
├── Messages_en.properties
└── Messages_de.properties
~~~

`Messages_en.properties`:

~~~properties
receipt=Hello {0}, total: {1,number,#,##0.00}.
~~~

`Messages_de.properties`:

~~~properties
receipt=Hallo {0}, Gesamtbetrag: {1,number,#,##0.00}.
~~~

Create `LocalizedMessageDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedMessageDemo {
    public static void main(String[] args) {
        Locale locale = Locale.GERMANY;
        ResourceBundle bundle = ResourceBundle.getBundle(
                "Messages", locale
        );

        MessageFormat formatter = new MessageFormat(
                bundle.getString("receipt"), locale
        );

        System.out.println(
                formatter.format(new Object[]{"Lan", 1234.5})
        );
    }
}
~~~

Save the files in the same directory, using JDK 17+:

~~~bash
javac -encoding UTF-8 LocalizedMessageDemo.java
java -cp . LocalizedMessageDemo
~~~

Output with standard German locale data in the JDK:

~~~text
Hallo Lan, Gesamtbetrag: 1.234,50.
~~~

In this example, `ResourceBundle` selects the **sentence pattern**, while `MessageFormat` uses **`Locale.GERMANY`** to format the numeric argument. The two tasks are related but distinct: when a bundle falls back to another locale, the application needs a clear policy on which locale formats numbers and dates. Whether to use `bundle.getLocale()` or the requested locale is a product decision, not a universal rule for every system.

`.properties` files in Java 17 can contain UTF-8 Unicode; manage encoding consistently in build and runtime to prevent corrupted Vietnamese diacritics or international characters.

## 5. Locale and Data Types: Different Limits Across APIs

### 5.1. How Locales Are Passed

Common signatures:

~~~java
// MessageFormat: constructor accepts locale.
MessageFormat message =
        new MessageFormat("{0,number,#,##0.00}", Locale.GERMANY);

// String.format: locale is the first argument.
String s = String.format(Locale.GERMANY, "%,.2f", 1234.5);

// Formatter: locale is specified when constructing the instance.
StringBuilder out = new StringBuilder();
try (Formatter formatter = new Formatter(out, Locale.GERMANY)) {
    formatter.format("%,.2f", 1234.5);
}
~~~

These are illustrative in-method snippets with corresponding imports. If `Locale` is omitted:

- `new MessageFormat(pattern)` uses the default locale for the `Locale.Category.FORMAT` category.
- `MessageFormat.format(pattern, args...)` is a **static convenience method** that constructs an instance using the default locale; it **does not have a `Locale`-first overload** like `String.format(Locale, ...)`.
- `String.format(pattern, args...)` uses the default `FORMAT` category locale; `String.format(locale, pattern, args...)` lets you pass it explicitly.
- `new Formatter()` and constructors without a locale parameter use the appropriate default locale; constructors accepting `Locale` establish conventions upon creation.
- `Formatter.format(Locale, pattern, args...)` lets you specify a locale for a single formatting call on an instance when needed.

In multi-user applications, passing the recipient's locale for each operation is explicit and avoids relying on JVM defaults. **Do not mutate `Locale.setDefault(...)` per request**, as it is shared state that can affect other threads.

### 5.2. Numbers and Currency

For numbers:

~~~text
MessageFormat : {0,number,#,##0.00}
printf        : %,.2f
~~~

Both patterns can display the same number, yet **there is no one-to-one syntax conversion rule**. `MessageFormat` patterns also hold message structure; `Formatter` patterns have flags, width, precision, and conversions.

For currency:

~~~java
MessageFormat moneyMessage = new MessageFormat(
        "Amount: {0,number,currency}", Locale.US
);

String withPrintf = String.format(
        Locale.US, "Amount: $%,.2f", 1234.5
);
~~~

These are illustrative snippets. The first formats the amount via `NumberFormat.getCurrencyInstance(Locale.US)` at the subformat level; the second hardcodes the `$` sign **as a literal in the pattern**. The second breaks if the user expects EUR or VND, or if the currency symbol must appear in another position. When handling real money, you must know **the transaction's `Currency`** and configure `NumberFormat` or `MessageFormat.setFormatByArgumentIndex(...)` per business requirements; never infer currency solely from user location.

### 5.3. Dates, Times, and `java.time`

`MessageFormat` in Java 17 uses legacy subformats like `DateFormat` for `{0,date}`/`{0,time}`, which typically expect `java.util.Date` or a subformat-compatible type. Do not assume passing `LocalDate` or `LocalDateTime` directly into `{0,date}` will work.

`Formatter` supports `%t...`/`%T...` date/time conversions for temporal argument types listed in its Javadoc—such as `Date`, `Calendar`, `long`, and appropriate `TemporalAccessor` types. However, that **does not** mean `MessageFormat` and `Formatter` share the same date-formatting API.

With modern `java.time`, when you simply need to build a standalone date/time string, prefer explicit `DateTimeFormatter`:

~~~java
LocalDate date = LocalDate.of(2025, 7, 14);
String dateText = date.format(
        DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US)
);
MessageFormat message = new MessageFormat(
        "Scheduled for {0}", Locale.US
);
String output = message.format(new Object[]{dateText});
~~~

This is an illustrative in-method snippet requiring imports for `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.text.MessageFormat`, and `java.util.Locale`.

This approach builds `dateText` for the locale first and inserts it as a string. However, if you want translated sentence patterns to **choose the date style themselves**, design the formatting service's responsibilities clearly. `Locale` does not determine time zones: when formatting an absolute instant, select `ZoneId` separately.

## 6. Escaping Syntax: A Very Common Source of Bugs

### 6.1. MessageFormat Has Special Single-Quote Rules

In `MessageFormat`, the **single quote** `'` is the syntactic quoting symbol. To display a literal single quote in a pattern, use **two single quotes `''`**. To print a curly brace `{` or `}` without the parser treating it as a placeholder, quote the literal segment appropriately.

Standalone example:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class QuoteDemo {
    public static void main(String[] args) {
        MessageFormat message = new MessageFormat(
                "It''s '{'ok'}': {0}",
                Locale.US
        );
        System.out.println(message.format(new Object[]{"yes"}));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 QuoteDemo.java
java QuoteDemo
~~~

Output:

~~~text
It's {ok}: yes
~~~

Explanation: `''` denotes a literal single quote; `'{'` and `'}'` denote literal curly braces, while `{0}` is an actual placeholder.

**Pitfall:** a single unescaped quote in a pattern like `"It's {0}"` can accidentally activate quoting mode, preventing `{0}` from being substituted as intended. When loading patterns from `ResourceBundle`, translators must be clearly instructed on this rule.

### 6.2. Formatter Has Percent-Sign Rules

In `String.format` and `Formatter`, `%` introduces a conversion. To print a literal `%`, write `%%`:

~~~java
String output = String.format(
        Locale.US, "Progress: %d%%", 75
);
System.out.println(output);
~~~

Output:

~~~text
Progress: 75%
~~~

In `printf` patterns, the single quote `'` is **not** a structural escape like in `MessageFormat`. Conversely, `%` in a `MessageFormat` pattern is normally a plain character unless it appears inside a subpattern with its own rules.

**Never convert patterns with simple find-and-replace** between the two APIs: it can produce broken sentences, missing arguments, or parser errors. Whenever editors are allowed to edit patterns, include syntax checks and per-locale formatting tests.

## 7. Formatting Quantities, Singular/Plural

`MessageFormat` includes `choice`, which can pick a text segment based on numeric thresholds:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceDemo {
    public static void main(String[] args) {
        String pattern =
                "{0,choice,0#No files|1#One file|1<Many files}";

        MessageFormat message =
                new MessageFormat(pattern, Locale.US);

        System.out.println(message.format(new Object[]{0}));
        System.out.println(message.format(new Object[]{1}));
        System.out.println(message.format(new Object[]{2}));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ChoiceDemo.java
java ChoiceDemo
~~~

Output:

~~~text
No files
One file
Many files
~~~

This is only a threshold example for **non-negative** counts; `choice` **does not automatically provide** the full set of complex plural rules across all languages (such as grammatical forms for 0, 1, 2, few, or many in certain languages). `String.format`/`Formatter` has no `%plural` conversion: using them to print a number does not select grammatically accurate prose.

When a product requires CLDR-compliant pluralization, consider an i18n engine that supports plural rules (such as ICU MessageFormat or a library chosen for the product). External libraries' syntax and feature sets can differ from `java.text.MessageFormat` in Java 17; verify APIs and pattern formats before migrating.

## 8. Stateful Formatter, Convenient String.format, and Configurable MessageFormat

### 8.1. When to Use `Formatter` Directly?

`String.format` is usually sufficient for creating **a single string**:

~~~java
String line = String.format(
        Locale.US, "%-12s | %08d | %,.2f", "Order", 42, 1234.5
);
~~~

`Formatter` makes sense when building multiple parts of the same output:

~~~java
StringBuilder buffer = new StringBuilder();

try (Formatter formatter = new Formatter(buffer, Locale.US)) {
    formatter.format("Report%n");
    formatter.format("%-10s %8d%n", "Orders", 42);
    formatter.format("%-10s %8.2f%n", "Rate", 3.5);
}

String report = buffer.toString();
~~~

These snippets require importing `java.util.Locale` and `java.util.Formatter`; they are code fragments suitable for placing inside a method.

With `Formatter`, the destination can be any `Appendable`. When wrapping a `Writer`/stream backed by external resources, calling `close()` may **close the destination** if it implements `Closeable`; define resource ownership clearly. Calling `formatter.format(...)` after closing `Formatter` throws a state error. If you only need a `String` from a single format call, `String.format` is shorter and easier to manage.

### 8.2. `MessageFormat` Can Mutate Its Pattern and Subformats

`MessageFormat` exposes `applyPattern`, `setLocale`, `setFormatByArgumentIndex`, and other methods to alter formatting behavior. It is **not immutable** and **not synchronized**. Having threads mutate the pattern or subformats on the same instance while formatting can produce unexpected results.

`Formatter` is likewise not guaranteed safe for concurrent multi-threaded use. A clean approach is to create instances per call or apply appropriate synchronization. By contrast, the resulting `String` is immutable; calling static `String.format(locale, ...)` does not require sharing a stateful `Formatter` across requests.

If optimizing performance by caching `MessageFormat`, you can store validated patterns and clone or instantiate copies before use, or manage synchronization; never share an unprotected mutable instance directly.

### 8.3. Exceptions When Passing Invalid Patterns or Types

| Input error | Likely outcome |
| --- | --- |
| `MessageFormat` with unbalanced curly braces | `IllegalArgumentException` when parsing pattern |
| `MessageFormat` expects `{0,number}` but receives an incompatible type | `IllegalArgumentException` during formatting |
| `String.format` uses `%d` for a `String` | `IllegalFormatConversionException` or another `IllegalFormatException` |
| `String.format` has a valid conversion but missing argument | `MissingFormatArgumentException` |
| Formatting after `Formatter` is closed | `FormatterClosedException` |
| Translated pattern has malformed `%` or `'` rules | Lost placeholders, wrong string, or parser error |

Because patterns may be supplied by editors via translation files, **testing with sample data for every locale** is highly valuable. Do not treat runtime formatting errors as merely cosmetic issues: the UI may fail to render messages or lose critical information.

## 9. Distinguishing Display Strings from Data-Interchange Formats

All three APIs focus on **presentation**. Locale-dependent number/date formats are generally suited for human readers, not for machine-to-machine data exchange.

For example, the same number `1234.5` can render as `1,234.50` or `1.234,50`. Using that string as a number in JSON, CSV, or query strings without an explicit contract can cause the receiver to misinterpret it.

- Interchange data: use JSON numbers, `BigDecimal`/consistent numeric protocols, and ISO-8601 dates where appropriate.
- Display data: use an explicit `Locale` and the corresponding API.
- Translatable text: fetch sentence patterns from `ResourceBundle`/i18n systems, then format with the appropriate mechanism.
- Aligned reports: `Formatter`/`String.format` suits columns and widths; for Unicode text and complex tables, display width on a terminal also depends on fonts and multi-codepoint characters.

Translated content does not become grammatically sound merely because every variable was inserted and numbers have the right grouping separators. When text forms complete sentences, you must evaluate the grammar and structure of the target language.

## 10. API Selection Guide by Scenario

| Scenario | Typically best choice | Why |
| --- | --- | --- |
| "Hello {name}, you have {count} notifications" in multiple languages | `ResourceBundle` + `MessageFormat` | Translators control argument position and formatting |
| A diagnostic line `"x=12.30; y=4.50"` | `String.format(Locale.ROOT, ...)` or fixed locale | Concise, explicit precision; uniform locale for technical data |
| Multi-line column alignment in a text report | `Formatter` bound to `StringBuilder`/`Writer` | Appends multiple times to the same destination |
| Formatting a standalone number label `1.234,50` | `NumberFormat.getNumberInstance(locale)` | Locale number formatting without needing a message pattern |
| Formatting a standalone date `14 July 2025` from `LocalDate` | `DateTimeFormatter` with locale | Modern date/time API |
| Translating 0/1/many messages or complex plural rules | `MessageFormat` with simple `choice`; i18n/CLDR library when complex | Chooses accurate per-language grammar |
| Printing logs/diagnostics with stable formatting | `String.format(Locale.ROOT, ...)` or consistent technical format | Avoids depending on the host's default locale |
| Formatting dates inside `MessageFormat` | Supported `Date`/subformat, or pre-format with `DateTimeFormatter` | Avoids passing `LocalDate` directly to unsupported legacy subformats |

### A Quick Code-Review Checklist

1. Is the pattern a translated sentence loaded from translation resources, or just a technical display string?
2. Do pattern parameters correctly use **0-based** (`MessageFormat`) or explicit **1-based** (`Formatter`) indexing?
3. Is `Locale` passed explicitly? Is anything accidentally relying on the JVM default locale?
4. Are the conversions and argument types matched? Are dates/times handled with the right data types and time zones?
5. Do translated patterns have single quotes/curly braces or `%` signs requiring escaping?
6. Is any mutable `MessageFormat`/`Formatter` shared across threads?
7. Do quantity messages require more sophisticated pluralization than `choice`?
8. Is the output human-readable prose or machine-exchange data? Should a locale-dependent format be used here at all?

## 11. Hands-On Exercises

1. Write two `MessageFormat` patterns—English and Vietnamese—using the same `Object[] {"Lan", 3}` while reversing argument order. Pass explicit `Locale` instances at construction.
2. Produce the same output `"Lan: 1,234.50"` using `MessageFormat`, `String.format`, and `Formatter`, then switch `Locale.US` to `Locale.GERMANY` and compare.
3. Modify `QuoteDemo` to display a sentence containing both single quotes and curly braces. Explain why `MessageFormat` quoting differs from `printf` syntax.
4. Call `String.format(Locale.US, "Value=%08d", 42)`. Try passing `"42"` instead of `42` and observe the exception.
5. Build a `ResourceBundle`-backed message pattern with a person's name and a total amount; identify which locale selects the pattern and which locale formats the number when fallback occurs.
6. Write a `Formatter` appending three lines to a `StringBuilder`; explain when the destination must be closed versus when only the wrapper is closed.
7. Take a fixed date `LocalDate.of(2025, 7, 14)`, format it via `DateTimeFormatter` into date text, and insert it into `MessageFormat`. Why does this design avoid confusion between `java.time` and legacy `DateFormat` subformats?

**Takeaway:** `MessageFormat` is designed for **localizable messages**, using 0-based `{0}` placeholders and locale-aware subformats. `String.format` and `Formatter` use **`printf`** syntax, with explicit 1-based `%1$s` references, excelling at precision, width, flags, and layout. `String.format` is convenient for creating one string; `Formatter` fits repeated writes to a destination. Choose the API based on the nature of the content and always control locale, data types, escaping, and thread safety.

### References

- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) — `{index}` syntax, subformats, single quotes, `choice`, and synchronization.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html) — `printf` syntax, conversions, flags, width, locale, Appendable, and thread safety.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html) — `String.format(...)`.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) — `java.time` date and time formatting.
