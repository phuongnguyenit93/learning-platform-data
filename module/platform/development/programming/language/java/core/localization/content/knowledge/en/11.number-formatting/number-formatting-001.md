# NumberFormat for General Numbers and Integers in Java

## 1. Goal: One Value, Many Representations

In Java applications supporting multiple languages/regions, the same numeric value can be **displayed differently**: US English typically uses a comma for thousands grouping and a period for the decimal point; German (Germany) typically swaps those two separators. The numeric data inside the program retains the same meaning, while the representation for the reader depends on the `Locale`.

The abstract class `java.text.NumberFormat` provides factory methods to create objects for **formatting numbers** and **parsing strings into numbers** appropriate for a locale:

- `NumberFormat.getNumberInstance(locale)`: general numbers, which may have a fractional part.
- `NumberFormat.getIntegerInstance(locale)`: **integer** presentation style, displaying no fractional digits and by default **parsing only the integer part**.
- `NumberFormat.getNumberInstance()` and `getIntegerInstance()`: use the default locale for the `Locale.Category.FORMAT` category.
- `NumberFormat.getInstance(locale)`: equivalent to the general number factory `getNumberInstance(locale)`.

The two number styles in this topic are **formatting styles**. `NumberFormat` does not change the `int`/`long`/`BigDecimal` data type in the domain and does not establish business rounding rules on its own.

Conceptual example:

| Numeric data | `getNumberInstance(Locale.US)` with 2 fractional digits | `getIntegerInstance(Locale.US)` with HALF_UP |
| --- | --- | --- |
| 12345.678 | `12,345.68` | `12,346` |
| 1234 | `1,234.00` if at least 2 fractional digits are required | `1,234` |
| 12.5 | `12.50` if at least 2 fractional digits are required | `13` |

In the table, the two output columns already have **specific illustrative configurations**; do not assume a default factory always displays exactly two fractional digits or uses HALF_UP. When implementing on your own, set explicit formatting rules.

## 2. Factory for General Numbers

### 2.1. Creating a Formatter with an Explicit Locale

~~~java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);
~~~

The snippet above **illustrates statements** that need to be inside a method or initializer block of a Java class; a complete standalone runnable program is in section 7.

`NumberFormat` abstracts formatting conventions. The same number `12345.678` can produce `12,345.678` in `en-US` and `12.345,678` in `de-DE` with a configuration allowing three fractional digits. Specific symbol names, grouping behavior, and Unicode characters may vary by locale, provider, or CLDR data version; test in your target environment.

`Locale` affects multiple aspects:

- Decimal separator character and thousands grouping character.
- Grouping rules and digit counts.
- Numbering system (which may use non-ASCII digits, depending on the locale and Unicode extensions).
- Negative sign display and certain special symbols.

Do not use `String.format("%,.2f", value)` with an uncontrolled default locale if the output must be consistent per user. If you use `String.format(locale, ...)`, you must also pass an explicit locale; `NumberFormat` is more suitable when you need to switch formatting styles and perform locale-aware two-way parsing.

### 2.2. Configuring Fractional Digits

Commonly used methods:

~~~java
formatter.setMinimumFractionDigits(2);
formatter.setMaximumFractionDigits(2);
~~~

`formatter` is an already created `NumberFormat`. **Minimum** ensures trailing zeros are padded if needed, and **maximum** limits the number of fractional digits displayed, so **rounding** may be required. When applying min/max, the formatter object may adjust the other value to satisfy min ≤ max. You should explicitly set both according to clear rules if you need to display exactly 2 fractional digits.

Example with `en-US`:

| Value | min = 2, max = 2 | Reason |
| --- | --- | --- |
| `12` | `12.00` | Pads two zeros |
| `12.3` | `12.30` | Pads one zero |
| `12.345` | `12.35` with HALF_UP | Rounds to 2 digits |
| `-12.345` | `-12.35` with HALF_UP | Rounds away from zero (by magnitude) under HALF_UP |

You must distinguish between **rounding for display** and **rounding business results**. `NumberFormat` only produces a string; if the system calculates money or stores quantities, use `BigDecimal` with an appropriate scale and `RoundingMode` in the business layer.

### 2.3. Configuring Grouping

~~~java
formatter.setGroupingUsed(true);   // Enable thousands grouping according to locale rules.
formatter.setGroupingUsed(false);  // Disable thousands grouping.
~~~

Example of the number `12345.68` in `Locale.US`, configured with two fractional digits:

- Grouping enabled: `12,345.68`.
- Grouping disabled: `12345.68`.

Some locales use a **non-breaking space** or another Unicode whitespace character for grouping. Do not blindly use `replace(",", "")` to "remove grouping": a comma may be the decimal separator in another locale.

## 3. NumberFormat for Integers

`NumberFormat.getIntegerInstance(locale)` is designed for **integer output** style. On standard JDK formatters, this factory configures the fractional digit limit to 0 and `isParseIntegerOnly()` to `true`:

~~~java
NumberFormat integers = NumberFormat.getIntegerInstance(Locale.US);
System.out.println(integers.getMaximumFractionDigits()); // 0
System.out.println(integers.isParseIntegerOnly());        // true
~~~

This is an **illustrative snippet** inside a method, with `NumberFormat` and `Locale` imported.

### 3.1. When Formatting: Rounding for Integer Display

With `getIntegerInstance(Locale.US)`, formatting a value with a fractional part **does not mean Java truncates the fractional part**. The value may be rounded according to the formatter's rules. To make results predictable in this lesson, configure it explicitly:

~~~java
integers.setRoundingMode(java.math.RoundingMode.HALF_UP);
System.out.println(integers.format(
        new java.math.BigDecimal("12345.5"))); // 12,346
~~~

Keep in mind:

- `format(12345.5)` produces the `String` `"12,346"` under the configuration above. It **does not return** an `int` or mutate the original number into `12346`.
- With the common default HALF_EVEN rule of `DecimalFormat`, exact midpoint values can yield different results than HALF_UP. If the application requires a specific rule, set `RoundingMode` and write tests.
- `getIntegerInstance` is suitable for displaying integer quantities, record counts, integer scores, or counters; do **not** use it to cast data types, validate strict integer input, or generate technical IDs.

### 3.2. When Parsing: Only Takes the Integer Prefix

More importantly, `getIntegerInstance` typically sets `parseIntegerOnly = true`. When encountering `"12,345.67"` in `en-US`, the parser may stop **before the decimal point** and return `12345` even though `.67` remains unconsumed.

This is **not** a mechanism to validate that the entire input string is a valid integer. `parse` can succeed on a **portion** of the input.

If an API accepts an item quantity or product count, the string `"12,345.67"` must be rejected or handled according to published input rules; do not silently accept `12345`.

### 3.3. `setParseIntegerOnly(true)` Does Not Change Formatting Precision

These are two independent settings:

| Setting | Primary effect |
| --- | --- |
| `setMaximumFractionDigits(0)` | Limits fractional digits when **formatting** |
| `setParseIntegerOnly(true)` | Stops when encountering a decimal part during **parsing** |
| `getIntegerInstance(locale)` | Factory configured appropriately for both integer formatting and integer-part parsing |

Example:

~~~java
NumberFormat parserMode =
        NumberFormat.getNumberInstance(Locale.US);
parserMode.setParseIntegerOnly(true);
System.out.println(parserMode.format(12.75)); // 12.75
~~~

Changing `parseIntegerOnly` **does not remove** the fractional part in the formatted string. The two methods control two different behaviors; this code snippet is verified in the complete program in section 7.

## 4. Locale-Aware String Parsing: Input Is Data, Not Display Formatting

`NumberFormat.parse(String)` attempts to convert a prefix of the string into a `Number` according to the selected locale. It may throw `ParseException` if **nothing can be parsed** from the starting position, but it does not inherently require the entire string to be consumed.

With `Locale.US`:

~~~java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
Number value = us.parse("12,345.67");
~~~

This is an illustrative snippet inside a method that declares or handles `ParseException`. The parsed value corresponds to the number `12345.67`, but the result type may be `Long`, `Double`, or another type depending on the parser and configuration. Do not cast directly to `Double` or `Long` without verifying the API contract.

### 4.1. Checking the Entire Input with ParsePosition

`java.text.ParsePosition` indicates how far the parser has consumed into the string:

~~~java
ParsePosition position = new ParsePosition(0);
Number parsed = formatter.parse(input, position);
boolean fullyConsumed =
        parsed != null && position.getIndex() == input.length();
~~~

This snippet assumes `formatter` is a `NumberFormat` and `input` is a `String`, inside a method. With the 9-character string `"12,345.67"`:

- Number formatter `en-US`: parses `12345.67`, consumes 9/9.
- Integer formatter `en-US`: parses `12345`, consumes 6/9 (stops before the period).

The `6/9` result indicates the input cannot be accepted as a **complete integer**. If it is not fully consumed or `parsed == null`, report an error to the user.

**Important limitation:** checking `position.getIndex() == input.length()` only ensures the entire string was consumed; it is **not sufficient** to guarantee strict grouping syntax or business rule compliance. Some parsers may accept non-standard grouping; applications should add their own validation policy (for example, disallowing grouping, checking signs, value ranges, length, or the full representation). Do not use parsing as a "strictly valid for every local format" validator.

### 4.2. Need to Preserve Decimal Precision?

In many JDK implementations, `NumberFormat.getNumberInstance(locale)` returns a `DecimalFormat`. `DecimalFormat` supports `setParseBigDecimal(true)` to produce a `BigDecimal` instead of relying on binary `double` representation for decimal values. If needed:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.US);
if (format instanceof java.text.DecimalFormat decimalFormat) {
    decimalFormat.setParseBigDecimal(true);
    Number number = decimalFormat.parse("12345.67");
    // In the normal finite-number case above, number is a BigDecimal.
}
~~~

This is an **illustrative snippet**, with appropriate `ParseException` handling. Do not assume every `NumberFormat` from every provider is a `DecimalFormat`; if the code directly needs `DecimalFormat`, check the type and the provider's contract.

For monetary amounts, formatting and parsing must rely on currency rules, scale, and the source of truth; `NumberFormat` should not be used as a value store. `getCurrencyInstance` is the dedicated factory for currency display, whereas this lesson focuses on general numbers and integers.

## 5. Default Locale vs. Explicit Locale

Two ways to create an object:

~~~java
NumberFormat implicit = NumberFormat.getNumberInstance();
NumberFormat explicit =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"));
~~~

Where:

- `implicit` uses the JVM's default locale for the `Locale.Category.FORMAT` category.
- `explicit` has a specific locale, so it does not depend on the host machine's default choice for selecting separators and formatter patterns.

For a single-language CLI program, the default locale can be useful. For websites, servers, and applications with multiple concurrent users, **do not call `Locale.setDefault(...)` per request** to switch number separators: `Locale.setDefault` mutates JVM-wide state, and other threads/requests can be affected. Instead, determine the locale at the input/UI boundary and pass it into the presentation layer.

`Locale` does **not** uniquely determine a currency or time zone. Use a separate `ZoneId` for instants/times and a `Currency` alongside the value when handling money.

## 6. NumberFormat Configuration Mutates the Object

Setters such as `setGroupingUsed`, `setMinimumFractionDigits`, `setMaximumFractionDigits`, `setParseIntegerOnly`, and `setRoundingMode` **mutate the state of the formatter**. `NumberFormat` in general is not guaranteed to be thread-safe: do not share a mutable instance across multiple requests/threads without proper synchronization.

A safe pattern for the presentation layer:

~~~java
static String formatQuantity(Number quantity, Locale locale) {
    NumberFormat format = NumberFormat.getIntegerInstance(locale);
    format.setRoundingMode(java.math.RoundingMode.HALF_UP);
    return format.format(quantity);
}
~~~

This snippet is an **illustrative method**, requiring `import java.text.NumberFormat;` and `import java.util.Locale;` in its enclosing class. For real-world use, the quantity rounding rule must be defined by the domain beforehand; if a quantity must strictly be an integer, validate the quantity before passing it to the formatter.

Do not keep a `NumberFormat` as a singleton and mutate its locale/settings "for the current request." Create a formatter per context or use a copy/management strategy that ensures mutable state is never shared.

## 7. Standalone Runnable Java 17 Program

Place the following code in a file named **`NumberFormatDemo.java`**. The example explicitly selects the locale, fractional digit counts, and `RoundingMode.HALF_UP`; it does not depend on the host machine's default locale.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class NumberFormatDemo {
    static String parseResult(NumberFormat format, String input) {
        ParsePosition position = new ParsePosition(0);
        Number number = format.parse(input, position);
        return String.valueOf(number) + ", consumed=" + position.getIndex()
                + "/" + input.length();
    }

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("12345.678");
        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);
        for (NumberFormat formatter : new NumberFormat[]{us, de}) {
            formatter.setMinimumFractionDigits(2);
            formatter.setMaximumFractionDigits(2);
            formatter.setRoundingMode(RoundingMode.HALF_UP);
        }

        System.out.println("US number: " + us.format(amount));
        System.out.println("DE number: " + de.format(amount));

        NumberFormat integer = NumberFormat.getIntegerInstance(Locale.US);
        integer.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("US integer: "
                + integer.format(new BigDecimal("12345.5")));
        System.out.println("integer parser only: "
                + integer.isParseIntegerOnly());
        System.out.println("decimal parse: "
                + parseResult(NumberFormat.getNumberInstance(Locale.US),
                        "12,345.67"));
        System.out.println("integer parse: "
                + parseResult(integer, "12,345.67"));

        NumberFormat parsingOnly = NumberFormat.getNumberInstance(Locale.US);
        parsingOnly.setParseIntegerOnly(true);
        System.out.println("parseIntegerOnly format: "
                + parsingOnly.format(12.75));

        us.setGroupingUsed(false);
        System.out.println("without grouping: " + us.format(amount));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 NumberFormatDemo.java
java NumberFormatDemo
~~~

**Exact stdout of the example** on a standard JDK with common `Locale.US`/`Locale.GERMANY` formatting data:

~~~text
US number: 12,345.68
DE number: 12.345,68
US integer: 12,346
integer parser only: true
decimal parse: 12345.67, consumed=9/9
integer parse: 12345, consumed=6/9
parseIntegerOnly format: 12.75
without grouping: 12345.68
~~~

Meaning of the output:

1. The same `BigDecimal("12345.678")` is presented according to two separator conventions.
2. `getIntegerInstance` displays `12345.5` as `12,346` when HALF_UP is requested; the original number is unchanged.
3. For the same input string `12,345.67`, the general number parser consumes 9/9 characters, while the integer parser consumes only 6/9.
4. Calling only `setParseIntegerOnly(true)` does not change the result of `format(12.75)`.
5. `setGroupingUsed(false)` disables grouping on the created US formatter.

Formatting results for some locales may differ across CLDR data sources, providers, or JDK versions; if writing snapshot tests, only assert exact output in a controlled environment.

## 8. Choosing a NumberFormat Type for Your Needs

| Need | Recommendation | Additional things to check |
| --- | --- | --- |
| Display measurements with fractional parts | `getNumberInstance(locale)` | Min/max fraction digits, unit of measurement, rounding |
| Display integer quantities already domain-validated | `getIntegerInstance(locale)` | Grouping and rounding for input values |
| Parse user-entered decimal numbers | `getNumberInstance(locale)` + `ParsePosition` | Full string consumption, grouping, value range |
| Parse **strictly integer** input | Locale-aware parser + custom validation | Reject fractional parts, overflow, invalid signs |
| Display percentages | `getPercentInstance(locale)` | Multiply-by-100 rule and fraction digits |
| Display money | `getCurrencyInstance(locale)` | `Currency`, scale, rounding, exchange rate |
| Store/exchange machine-readable numbers (JSON/API) | Canonical numeric representation per contract | Do not use locale-grouped strings |

For **IDs, customer codes, phone numbers, and postal codes**, do not use an integer formatter to "prettify" them: those values may have leading zeros, plus signs, hyphens, or more digits than fit in an integer range. They are **identifiers**, so they should be kept as strings and validated with their own rules.

## 9. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `getIntegerInstance` to truncate fractional parts | The formatter **rounds** on display | Validate/convert types in the domain first; set rounding when formatting |
| Calling `setParseIntegerOnly(true)` expecting `format` to output integers | The two behaviors are independent | Use `getIntegerInstance` or set maxFractionDigits=0 |
| Only checking that `parse` does not throw `ParseException` | The string may have been only partially parsed | Use `ParsePosition` and verify the entire input was consumed |
| Using `ParsePosition` and assuming the input obeys all grouping rules | The parser can be lenient with grouping | Add a validator per contract |
| Blindly casting the returned `Number` to `(Long)` or `(Double)` | `ClassCastException` or data loss | Check the type and data rules |
| Using `double` for monetary values requiring decimal precision | Binary floating-point error during calculations | Use `BigDecimal` in the domain; control scale |
| Hardcoding `,` as decimal or grouping separator | Wrong for other locales | Use locale-aware `NumberFormat` |
| Calling `Locale.setDefault` per request | Shared JVM state interferes with other requests | Pass locale explicitly |
| Sharing a mutable `NumberFormat` across threads | Race conditions / unstable formatting | Create per context or manage thread-safely |
| Using a formatter to normalize IDs/phone numbers | Loses leading zeros or alters characters | Keep identifiers as strings |

## 10. Tests You Should Write

For a component that displays or parses numbers by locale, you should test:

- **Different locales:** the number `12345.678` in `en-US` and `de-DE`, verifying separators/grouping in an environment with defined locale data.
- **Minimum/maximum fraction:** `12`, `12.3`, `12.345`, negative values, `0`, very large numbers, and `BigDecimal` with high scale.
- **Rounding:** exact midpoint values (e.g., `2.5`, `3.5`, `-2.5`) with HALF_UP/HALF_EVEN or the chosen business rule.
- **Integer display:** integer formatter has no fractional digits left but performs rounding.
- **Integer parsing:** entering `12,345.67` must be rejected by the integer-input validator because only 6/9 characters are consumed.
- **Malformed strings:** empty string, separator only, multiple minus signs, unusual grouping, unexpected Unicode digits, trailing garbage, and out-of-range numbers.
- **Concurrency:** do not share mutable formatters or mutate default locale per request.
- **Identifiers:** codes like `00123` and phone numbers preserve exact characters regardless of locale changes.

A well-designed test compares the **parsed value and consumed character count**, rather than relying on `NumberFormat` as a strict input validator that the library does not promise to provide.

## 11. Practice Exercises

1. Replace `Locale.GERMANY` with `Locale.forLanguageTag("vi-VN")` and observe the separators and digits on your current JDK.
2. Change `setMinimumFractionDigits(2)` to `0` while keeping `setMaximumFractionDigits(2)`; explain the difference between `12` and `12.345`.
3. Try HALF_EVEN when formatting `2.5` and `3.5` with the integer formatter, compared to HALF_UP. Check the effect of negative signs.
4. Create `NumberFormat.getNumberInstance(Locale.US)`, set `setParseIntegerOnly(true)`, and test parsing `12,345.67`; then try formatting `12.75`.
5. Use `ParsePosition` to check `"12,345.67abc"`, `"12,345.67"`, and `"12,345.67 "`; determine which portion the parser consumes.
6. Try `DecimalFormat.setParseBigDecimal(true)` with a value having many decimal digits; compare the returned type against when it is disabled.
7. Disable grouping and compare `us.format(new BigDecimal("1234567.89"))` before and after.
8. Write a method `formatCount(long count, Locale locale)` that creates a new formatter on every call, then test with multiple locales across different threads.

Through these exercises, remember that **formatting turns a number into a string for human readers**, while **parsing turns a string into a number**, and the two operations can be configured differently even on the same `NumberFormat` instance.

## 12. Summary

`NumberFormat.getNumberInstance(locale)` is suitable for formatting and parsing **general numbers** that may have a fractional part. `NumberFormat.getIntegerInstance(locale)` serves **integer presentation** and by default parses only the **integer part**; this does not turn it into a validator for integer-only input.

Create formatters with an explicit `Locale`, decide grouping/min/max/rounding according to requirements, check how much input was consumed when parsing, and keep business data in an appropriate numeric type. For high-precision requirements, combine `BigDecimal` with explicit parsing/rounding policies, and never use localized strings as the source of truth.

**References:**

- Java SE 17, `java.text.NumberFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html
- Java SE 17, `java.text.DecimalFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html
- Java SE 17, `java.text.ParsePosition`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html
- Java SE 17, `java.util.Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html