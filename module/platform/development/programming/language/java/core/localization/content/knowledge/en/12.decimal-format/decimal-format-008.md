# setParseBigDecimal and Preserving Precision When Parsing Numbers

## 1. Objectives and use cases

When a user enters a number in a UI localized to their language, a Java program must perform two **distinct** tasks:

1. **Understand locale-specific numeric syntax**: decimal separator, grouping separator, and numbering system.
2. **Preserve the decimal value needed for business logic**: avoid turning financial or high-precision data into an unwanted binary approximation.

For example, these two strings can represent the same mathematical value:

```text
en-US: 1,234.50
de-DE: 1.234,50
```

When parsed with the right locale, the desired result may be a `BigDecimal` object representing exact `1234.50`, including **scale equal to 2**. However, `NumberFormat.parse(String)` normally returns a `Number` such as `Long` or `Double` depending on input, implementation, and settings. For long decimal numbers, `Double` does not preserve all digits entered by the user.

`DecimalFormat.setParseBigDecimal(true)` solves that crucial part: it instructs `DecimalFormat` to return a `BigDecimal` for parsed **finite numeric values**, instead of rounding data through `double` or converting into an ordinary integer type. This is a setting for **parsing numbers**, distinct from rounding settings when **formatting numbers to strings**.

After this lesson, you will be able to:

- Use `DecimalFormat` with `Locale` and enable `setParseBigDecimal(true)` properly.
- Understand the difference between **value**, **precision**, **scale**, and `double` binary representation.
- Detect when the parser consumed only **part** of the input using `ParsePosition`.
- Recognize `NaN`, infinity, negative zero exceptions, and malformed input errors.
- Distinguish displayed numbers from exact numbers used in calculations and storage.
- Design a numeric input pipeline that validates locale, allowed digits, value bounds, and precision.

## 2. Why not just use `Double.parseDouble` right away?

`Double.parseDouble("1234.50")` requires Java-style numeric syntax and **does not** automatically apply localized separator symbols. For instance, the `de-DE` string `1.234,50` is not automatically understood as `1234.50` by `Double.parseDouble`.

Even when input has no grouping and the decimal point is `.`, `double` uses **binary IEEE 754** representation and therefore cannot store many decimal numbers such as `0.1` or `0.2` accurately. This differs from a comma-parsing bug: this is a **numeric representation** issue after parsing.

```java
System.out.println(0.1 + 0.2); // 0.30000000000000004
```

The snippet above is an illustration inside a Java method. To compute monetary amounts or data requiring decimal precision, we typically use `BigDecimal` instead of relying on `double`.

**Note:** `BigDecimal` does not decide whether input is en-US or de-DE. It handles decimal representation/arithmetic; `DecimalFormat` is the component that parses strings by locale.

## 3. `NumberFormat` and `DecimalFormat`: parser configuration

### 3.1. Relevant APIs

| API | Role |
| --- | --- |
| `NumberFormat.getNumberInstance(locale)` | Obtains the standard number formatter/parser for a locale |
| `NumberFormat.parse(String)` | Returns `Number`; result can be `Long` or `Double` |
| `DecimalFormat.setParseBigDecimal(true)` | Enables parsing finite numbers into `BigDecimal` |
| `DecimalFormat.isParseBigDecimal()` | Checks whether the flag is enabled |
| `DecimalFormat.parse(String, ParsePosition)` | Parses from a given index, returning position after last read character |
| `DecimalFormatSymbols.getInstance(locale)` | Gets locale-specific separators and symbols |
| `DecimalFormat.setParseIntegerOnly(true)` | Parses integer part only; **unsuitable** when preserving fractional parts |
| `DecimalFormat.setGroupingUsed(boolean)` | Controls grouping separators in formatting; not a strict validator of every group position |

Example of explicit `DecimalFormat` configuration:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("en-US");
DecimalFormat parser = new DecimalFormat(
        "#,##0.################",
        DecimalFormatSymbols.getInstance(locale));
parser.setParseBigDecimal(true);
```

This is a **code snippet inside a method**, not a standalone Java file. The pattern above describes a number with grouping and up to 16 fractional positions for **formatting**; it does not automatically cap the number of digits allowed when **parsing**. If you want form-input precision/scale rules, add **separate validation** after parsing.

In many common JDK environments, `NumberFormat.getNumberInstance(locale)` returns a `DecimalFormat` and can be cast:

```java
NumberFormat nf = NumberFormat.getNumberInstance(locale);
if (nf instanceof DecimalFormat decimal) {
    decimal.setParseBigDecimal(true);
} else {
    throw new IllegalStateException("DecimalFormat not available");
}
```

However, **do not assume every locale provider returns `DecimalFormat`**. `NumberFormat` is the superclass; if business logic strictly depends on `setParseBigDecimal`, use a parser initialization path with a known type and provider, or check the type before casting. Never write `(DecimalFormat) nf` without understanding deployment constraints.

### 3.2. The `parseBigDecimal` flag changes the *result type*

By default, `DecimalFormat` can return:

- `Long` for integers fitting within range.
- `Double` for numbers with fractional parts or values outside integer range.
- `Double` representing `NaN` or infinity when the parser encounters matching symbols.

When `setParseBigDecimal(true)` is enabled, for **finite** numbers the parser returns a `BigDecimal` holding the exact decimal value matching the digits read. It does **not** mean `parse(...)`'s declared return type changes: the method still declares `Number`, so inspect the result before calling `BigDecimal`-specific methods.

## 4. How value, precision, and scale differ

`BigDecimal` stores a decimal value using an arbitrary-length integer (`unscaledValue`) and a decimal exponent (`scale`). In principle:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Examples:

| Decimal string | Mathematical value | `scale()` | `precision()` |
| --- | --- | --- | --- |
| `0.1` | one tenth | 1 | 1 |
| `0.10` | one tenth | 2 | 2 |
| `1234.50` | one thousand two hundred thirty-four point five | 2 | 6 |
| `1234.500` | same mathematical value | 3 | 7 |

**Scale** is the number of digits after the decimal point in ordinary representation, though it can be negative for powers of ten; **precision** is the number of significant digits in the unscaled value. Scale is not simply "calculation accuracy", and precision is not the raw input string length (excluding signs, grouping separators, and insignificant leading zeros).

Two numbers:

```java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("1.2");
```

have equal numerical values but different scales. `a.equals(b)` returns `false` because `BigDecimal.equals` compares scale too, whereas `a.compareTo(b) == 0` is `true` because it compares mathematical value.

**Why preserve scale?** In business logic, `1.20` may signify the user entered two decimal places, unlike `1.2` which entered one. That does not mean the parsed string's scale is always a mandatory business property: some monetary systems enforce a fixed scale of 2 and must explicitly validate `setScale(...)` under accepted rules.

## 5. Runnable example: toggling `setParseBigDecimal`

Create the file `ParseBigDecimalDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class ParseBigDecimalDemo {
    public static void main(String[] args) throws Exception {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.################",
                DecimalFormatSymbols.getInstance(Locale.US));

        Number ordinary = parser.parse("1,234.50");
        System.out.println("ordinary type: "
                + ordinary.getClass().getSimpleName());
        System.out.println("ordinary value: " + ordinary);

        parser.setParseBigDecimal(true);
        BigDecimal exact = (BigDecimal) parser.parse("1,234.50");
        System.out.println("exact type: "
                + exact.getClass().getSimpleName());
        System.out.println("exact value: " + exact.toPlainString());
        System.out.println("scale: " + exact.scale());
        System.out.println("precision: " + exact.precision());

        BigDecimal zeroTen = (BigDecimal) parser.parse("0.10");
        System.out.println("0.10 value: " + zeroTen.toPlainString());
        System.out.println("0.10 scale: " + zeroTen.scale());

        String large = "12345678901234567890.123456789";
        BigDecimal veryLarge = (BigDecimal) parser.parse(large);
        System.out.println("large: " + veryLarge.toPlainString());
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 ParseBigDecimalDemo.java
java ParseBigDecimalDemo
```

Output:

```text
ordinary type: Double
ordinary value: 1234.5
exact type: BigDecimal
exact value: 1234.50
scale: 2
precision: 6
0.10 value: 0.10
0.10 scale: 2
large: 12345678901234567890.123456789
```

**Key explanation:**

- The default parser returns `Double` and prints `1234.5`; the `1,234.50` representation lost its grouping separator and trailing fractional zero in the printed value.
- `BigDecimal` mode retains `1234.50` with `scale=2` and `precision=6`.
- Very long decimal numbers retain all valid parsed digits accurately, without being truncated to `double`'s ~15–17 significant digits.
- Casting to `BigDecimal` in the example works because all inputs are **valid finite numbers**. For arbitrary user input, **never cast unconditionally**; handle `NaN`/infinity cases and validate the result.

## 6. Do not confuse `new BigDecimal(double)` with exact parsing

A bug can still occur even with `setParseBigDecimal(true)` enabled if you subsequently convert the value to `double`:

```java
BigDecimal exact = (BigDecimal) parser.parse("0.1");
double approximate = exact.doubleValue();
```

`doubleValue()` converts to binary representation and can lose exact digits; if you later construct a `BigDecimal` from that `double`, the data can change unintentionally.

Three ways to construct `BigDecimal` to distinguish:

| Construction | Characteristics |
| --- | --- |
| `new BigDecimal("0.1")` | Exact decimal representation equal to `0.1` |
| `BigDecimal.valueOf(0.1)` | Uses standard string from `Double.toString(0.1)`, usually yielding expected decimal `0.1` |
| `new BigDecimal(0.1)` | Represents the **exact binary double value** near `0.1`, not necessarily decimal `0.1` |

For inputs with locale separators, parse directly to `BigDecimal` via `DecimalFormat` instead of `Double.parseDouble` followed by `new BigDecimal(double)`. For strings stored in **locale-independent** decimal form (e.g., `"1234.50"` in an application schema), `new BigDecimal(string)` is a clean choice since no grouping-separator parser is needed.

## 7. Parsing by locale: separators change meaning

A parser for `en-US` reads `1,234.50` as `1234.50`; a parser for `de-DE` reads `1.234,50` as the same value. However, applying a US parser to a German string can **misread it or parse only a prefix**:

```text
en-US: 1,234.50
de-DE: 1.234,50
```

Periods and commas have opposite meanings. Never switch locales by replacing all commas with periods: a comma is the **grouping separator** in en-US, but the **decimal separator** in de-DE.

### Java 17+ example: comparing two locales

Create `LocaleDecimalParseDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LocaleDecimalParseDemo {
    static DecimalFormat parserFor(Locale locale) {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.################",
                DecimalFormatSymbols.getInstance(locale));
        parser.setParseBigDecimal(true);
        return parser;
    }

    public static void main(String[] args) throws Exception {
        DecimalFormat us = parserFor(Locale.US);
        DecimalFormat de = parserFor(Locale.GERMANY);

        BigDecimal fromUs =
                (BigDecimal) us.parse("1,234.50");
        BigDecimal fromDe =
                (BigDecimal) de.parse("1.234,50");

        System.out.println("US: " + fromUs.toPlainString());
        System.out.println("DE: " + fromDe.toPlainString());

        // Wrong locale: parse(String) may accept a prefix.
        Number wrong = us.parse("1.234,50");
        System.out.println("wrong locale: " + wrong);
    }
}
```

```bash
javac LocaleDecimalParseDemo.java
java LocaleDecimalParseDemo
```

Output:

```text
US: 1234.50
DE: 1234.50
wrong locale: 1.234
```

The last line is **not a success**: `us.parse("1.234,50")` accepted `1.234` and stopped before `,50`. Do not treat a non-null numeric return value as proof that the entire input was valid.

Note: the `Locale` you select must be the **locale of the format the user actually entered**, not the server's default locale or someone else's locale. If an application allows changing form language, bind the submitted input to the actual formatting language used.

## 8. `ParsePosition`: did it parse the entire string or only part?

`NumberFormat.parse(String)` / `DecimalFormat.parse(String)` can return a `Number` after reading only **part** of the input. For a numeric input form, this risk is particularly serious:

```text
Input:  1,234.50oops
Parsed: 1234.50
Suffix: oops
```

If you fail to catch the trailing `oops`, the system can silently accept corrupted data.

Use `ParsePosition` to verify the parser walked through **the entire string**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class FullInputParseDemo {
    static BigDecimal parseAll(String raw, Locale locale) {
        if (raw == null || raw.isEmpty()) {
            throw new IllegalArgumentException("Empty input");
        }

        DecimalFormat format = new DecimalFormat(
                "#,##0.################",
                DecimalFormatSymbols.getInstance(locale));
        format.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number number = format.parse(raw, position);

        if (!(number instanceof BigDecimal decimal)
                || position.getIndex() != raw.length()) {
            throw new IllegalArgumentException(
                    "Invalid decimal input");
        }
        return decimal;
    }

    public static void main(String[] args) {
        System.out.println(parseAll("1,234.50", Locale.US));
        try {
            parseAll("1,234.50oops", Locale.US);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
        try {
            parseAll("oops", Locale.US);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac FullInputParseDemo.java
java FullInputParseDemo
```

```text
1234.50
Invalid decimal input
Invalid decimal input
```

`ParsePosition.getIndex()` is the position right after the parsed portion; `getErrorIndex()` helps diagnose errors when reading could not start. For form inputs, the criteria for "success" should include **(1) a result of the right type; (2) all input characters consumed; (3) the value satisfies domain constraints**.

**Very important point:** even consuming the entire string **is still not a truly strict grouping-syntax validator**. Many `DecimalFormat` implementations accept misplaced grouping separators, such as `12,34.5` with a US parser, returning `1234.5`. If a system mandates exact grouping syntax, add separate format validation or a stricter parser mechanism supported by the target library/version; do not assume `DecimalFormat` checks every display rule.

**Whitespace policy:** the `parseAll` example does not `trim()` automatically, so leading/trailing spaces may be rejected. In production, you may intentionally allow surrounding whitespace, but specify handling for both U+0020 and Unicode whitespace; never silently alter grouping spaces inside a number.

## 9. Special cases: `NaN`, infinity, and negative zero

`setParseBigDecimal(true)` **does not guarantee every result from `parse(...)` is a `BigDecimal`**.

- `NaN`: if the input matches the locale/provider's `NaN` representation, the parser returns a `Double` with value `Double.NaN`, **not** a `BigDecimal`.
- **Infinity:** if the input matches `DecimalFormatSymbols`'s infinity symbol, the parser can still return `Double.POSITIVE_INFINITY` or `Double.NEGATIVE_INFINITY`.
- **Negative zero:** when `parseBigDecimal` is **off**, strings like `"-0"` can parse to `Double(-0.0)`. When the flag is **on**, the `BigDecimal.ZERO` result has no distinct negative-zero state; zero's negative sign cannot be preserved by `BigDecimal`.
- `parseIntegerOnly`: when enabled, the parser discards everything after the decimal point; do not use it if preserving exact decimals is the goal.

### Java 17+ example: handling `Number` safely for special values

File `SpecialNumberDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class SpecialNumberDemo {
    public static void main(String[] args) throws Exception {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);
        DecimalFormat parser = new DecimalFormat(
                "#,##0.################", symbols);
        parser.setParseBigDecimal(true);

        Number finite = parser.parse("0.10");
        Number notANumber = parser.parse(symbols.getNaN());
        Number infinity = parser.parse(symbols.getInfinity());
        Number negativeZero = parser.parse("-0");

        System.out.println("finiteBigDecimal="
                + (finite instanceof BigDecimal));
        System.out.println("nanIsDouble="
                + (notANumber instanceof Double));
        System.out.println("nan="
                + Double.isNaN(notANumber.doubleValue()));
        System.out.println("infinity="
                + Double.isInfinite(infinity.doubleValue()));
        System.out.println("negativeZero=" + negativeZero);
    }
}
```

```bash
javac SpecialNumberDemo.java
java SpecialNumberDemo
```

Output on standard JDKs:

```text
finiteBigDecimal=true
nanIsDouble=true
nan=true
infinity=true
negativeZero=0
```

The program fetches `symbols.getNaN()` and `symbols.getInfinity()` rather than guessing display strings: symbols can vary by locale. When an application accepts only finite decimal values, **check `instanceof BigDecimal`** as in `FullInputParseDemo` before using the value.

## 10. `setMaximumFractionDigits` does not limit parser precision

A common misconception:

```java
DecimalFormat format = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
format.setParseBigDecimal(true);

BigDecimal parsed =
        (BigDecimal) format.parse("1,234.56789");
System.out.println(parsed);        // 1234.56789
System.out.println(format.format(parsed)); // 1,234.57
```

This is an illustrative snippet inside a method with the required imports. `"#,##0.00"` or `setMaximumFractionDigits(2)` affects the **output string when formatting**, **not** causing `parse` to truncate or reject a number with five decimal digits.

This distinction matters for monetary systems: you might accidentally accept `1.23456` on input, then display `1.23` and assume the value was capped at two digits. To enforce a maximum number of decimal places, check `parsed.scale()` / raw data, or apply `setScale(allowedScale, RoundingMode.UNNECESSARY)` if you want to **reject** any value requiring rounding.

```java
// Illustrates a currency policy requiring at most two decimal digits.
BigDecimal amount = parsed.setScale(
        2, java.math.RoundingMode.UNNECESSARY);
```

`RoundingMode.UNNECESSARY` throws `ArithmeticException` if rounding is needed to reduce scale; however, it allows stripping trailing zeros that do not alter value, such as `1.230` to `1.23`. Thus, if the business rule is **"must not enter more than two fractional digits even if zero"**, check `scale()` or the input representation before normalizing; these two conditions are different.

## 11. Processing exact decimals after parsing

`BigDecimal` supports decimal arithmetic, though it does not enforce financial rules by itself. Example:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalMathDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.2");

        System.out.println(a.add(b).toPlainString());
        System.out.println(
                new BigDecimal("1.20").equals(new BigDecimal("1.2")));
        System.out.println(
                new BigDecimal("1.20")
                        .compareTo(new BigDecimal("1.2")) == 0);

        BigDecimal divided = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        System.out.println(divided.toPlainString());
    }
}
```

```bash
javac DecimalMathDemo.java
java DecimalMathDemo
```

```text
0.3
false
true
0.33
```

- Adding `BigDecimal("0.1")` and `BigDecimal("0.2")` yields the exact value `0.3`.
- `equals` considers scale, whereas `compareTo` compares mathematical value.
- Division can produce non-terminating decimals like `1/3`, requiring scale/rounding rules; `BigDecimal` does not make every operation produce a finite decimal result.

In financial applications, you must also decide **Currency**, minor currency units, per-step rounding rules, value bounds, and audit requirements. `setParseBigDecimal(true)` is only one stage in an exact processing pipeline.

## 12. Production input-handling pipeline

A safe pipeline for numeric input forms:

1. **Identify input source and locale.** If the user chose `de-DE`, use that exact locale when reading decimal/grouping separators. Never use the server's `Locale.getDefault()` to guess.
2. **Check characters and input size.** Bound length appropriately to prevent millions of digits from consuming memory/CPU. Decide whether negatives, `+` signs, exponents, currency symbols, and Unicode digits are allowed.
3. **Parse into `BigDecimal`** using `DecimalFormat` with `setParseBigDecimal(true)`; pass `Locale` explicitly and never mutate the JVM default per request.
4. **Verify the entire input** with `ParsePosition`; handle leftover characters, `NaN`/infinity cases, and missing input.
5. **Apply strict format validation if needed.** If grouping separators must sit at exact positions, apply a locale-aware syntax validator or suitable strict parser; do not treat full consumption as sufficient.
6. **Validate value constraints:** whether negatives are allowed, min/max, scale/precision, currency unit, maximum quantity.
7. **Compute with `BigDecimal` and an explicit rounding policy**, never converting to `double` mid-pipeline.
8. **Store under a locale-independent contract:** a decimal/numeric column with controlled scale or a canonical string `value.toPlainString()` if required by the schema. Never store locale-specific grouping separators for another machine to re-parse.
9. **Format for the UI** using `NumberFormat.getNumberInstance(viewLocale)`/`DecimalFormat` and appropriate display settings; never let formatting alter the domain value.

### Two string forms with the same meaning but different contracts

```text
User input source (de-DE):          "1.234,50"
                  | DecimalFormat parseBigDecimal
                  v
Domain BigDecimal:                  1234.50
                  |
           +------+------+
           |             |
           v             v
Canonical storage     Display en-US
"1234.50"             "1,234.50"
```

**Core point:** locale-specific separators are purely **input/output syntax**. Once parsed accurately, keep a business-meaningful decimal type and never carry separators into calculations.

## 13. Common mistakes

| Mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| Parsing localized numbers with `Double.parseDouble` | Does not understand locale grouping/decimal separators | Use `DecimalFormat` configured for the locale |
| Parsing via `NumberFormat` then calling `doubleValue()` | Can lose long decimal digits | Enable `setParseBigDecimal(true)` and keep `BigDecimal` |
| `new BigDecimal(double)` to keep entered decimal | Stores binary approximation, not the entered decimal string | Parse directly into `BigDecimal` or use `new BigDecimal(String)` for canonical strings |
| Casting every `parse` result to `BigDecimal` | `NaN`/infinity can return `Double` | Check `instanceof BigDecimal` |
| Assuming `0.10` and `0.1` share the same scale | Numeric value may match while scale differs | Distinguish `compareTo` from `equals` |
| Checking only that `parse` returned non-null | Parser may have read only a prefix | Verify `ParsePosition.getIndex() == input.length()` |
| Checking only full-string parse | Misplaced grouping separators may still be accepted | Add lexical/strict validation per contract |
| Selecting the wrong locale | `1,234` means different things in en-US vs. de-DE | Use the input's actual locale |
| Calling `setMaximumFractionDigits(2)` thinking input is capped | Output formatting setting, not parser validation | Validate `scale`/precision at the domain layer |
| Calling `replace(",", ".")` to normalize | Can turn grouping separators into decimal points or vice versa | Use locale-aware parsing and validation |
| Assuming `BigDecimal` handles all rounding automatically | Division may require rounding rules | Pick an explicit `RoundingMode` |
| Sharing a static `DecimalFormat` across threads | `DecimalFormat` is mutable, not guaranteed thread-safe | Create per-thread/request instances |
| Saving grouped UI strings to DB/API | Data becomes locale-dependent and fragile to round-trip | Store decimal values in a locale-independent schema |

## 14. Self-check

1. **What does `setParseBigDecimal(true)` change?** It instructs `DecimalFormat` to return `BigDecimal` for finite numeric results, instead of ordinary `Long`/`Double`.
2. **Why does calling `NumberFormat.parse("0.10")` and taking `double` lose `scale=2`?** `double` has no concept of decimal scale; it only carries an approximate binary value.
3. **Is `BigDecimal("1.20").equals(BigDecimal("1.2"))` true?** No: the two representations have different scales. `compareTo(...) == 0` is true for numerical value.
4. **Is it safe to use an en-US parser to read `1.234,50`?** No: it may partially parse `1.234`; you must use the input source's actual locale.
5. **Why does `parse(String)` return `Number` even with `parseBigDecimal` enabled?** That is the API signature of `NumberFormat`/`DecimalFormat`, and special values can still return other types.
6. **Is `NaN` returned as a `BigDecimal`?** No. Values like NaN or infinity are not representable by `BigDecimal` and can return `Double`.
7. **Does `parseBigDecimal` enabled preserve `"-0"` as negative zero?** No: `BigDecimal` has no separate negative-zero state.
8. **Does `setMaximumFractionDigits(2)` reject the string `1.23456` when parsing?** Not by default; you need scale/precision checks and a validator.
9. **Why is verifying `ParsePosition` consumed the whole string still not enough?** Because some parsers accept unconventional grouping; syntax validation may need to be stricter.
10. **Should you store a `de-DE` formatted result like `"1.234,50"` in a canonical decimal API?** Not if the schema requires locale-independent numbers. Store canonical numeric/decimal values and format only for display.
11. **Does `BigDecimal` automatically pick rounding for `1/3` division?** Not according to business policy; you must specify scale and `RoundingMode` when needed.
12. **For a monetary amount `1234.50`, what must be checked beyond accurate parsing?** Currency, scale/fractional rules, value range, rounding, strict parser checks, and storage policy.

## 15. References

- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): `setParseBigDecimal`, `isParseBigDecimal`, return types, and special cases.
- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): `parse`, locale-aware number formatting/parsing.
- [Java SE 21 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormatSymbols.html): decimal, grouping, and `NaN`/infinity symbols.
- [Java SE 21 — ParsePosition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ParsePosition.html): tracking parsed position and error index.
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): scale, precision, rounding, and value comparison.
- [Java SE 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): controlling rounding rules.
