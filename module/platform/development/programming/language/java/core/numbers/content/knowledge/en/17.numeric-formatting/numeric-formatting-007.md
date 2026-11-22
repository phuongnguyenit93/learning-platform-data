# `DecimalFormat`, Patterns, and `DecimalFormatSymbols` in Java

## 1. Goal: formatting a numeric value does not mean changing that value

In Java Core — Numbers, a numeric value may have to appear differently depending on country, system, or UI requirements:

```text
Same numeric value: 1234567.5

US convention:       1,234,567.50
German convention:   1.234.567,50
Custom format:       1^234^567|50
```

`java.text.DecimalFormat` performs most of this style of formatting. It lets you choose digit counts, thousands grouping, negative signs, percentage suffixes, scientific notation, or currency. The **pattern** string describes the layout, while `java.text.DecimalFormatSymbols` determines the actual symbols used for display, such as the decimal separator and grouping separator.

**Most importantly:** formatting a `double`/`long`/`BigDecimal` into a `String` **does not modify the stored numeric value**. Formatting may round the **display** output, while parsing a string back into a number is a separate operation with its own contract and risks.

After this lesson, you can:

1. Use `DecimalFormat` to format numbers with patterns such as `#,##0.00` and `0.###`.
2. Explain the symbols `0`, `#`, `.`, `,`, `;`, `%`, `‰`, `E`, `¤`, and the quoting mechanism `'...'`.
3. Understand the difference between **non-localized patterns** and **localized symbols**, and know how to use `applyPattern` and `applyLocalizedPattern` in the right context.
4. Create `DecimalFormatSymbols` from a specific `Locale` and customize grouping separators, decimal separators, minus signs, and currency units when needed.
5. Control rounding with `RoundingMode`, and understand the benefit of `BigDecimal` when exact decimal rounding is needed.
6. Parse strings with `parse`, `ParsePosition`, `setParseBigDecimal(true)`, and understand the risk of **parsing only a prefix**.
7. Distinguish presentation formats, data-exchange formats, monetary data, and locale-specific input.
8. Avoid sharing a single mutable `DecimalFormat` across threads without synchronization.

The complete programs use **Java 17+**; compile/run commands and stdout are provided for self-verification.

## 2. Roles of `NumberFormat`, `DecimalFormat`, `DecimalFormatSymbols`, and `Locale`

Four related yet distinct concepts:

| Component | Function |
| --- | --- |
| `NumberFormat` | General `Locale`-aware number formatting/parsing API; provides factories for general numbers, integers, currencies, and percentages |
| `DecimalFormat` | Implementation with **patterns** and detailed properties: digit counts, grouping, rounding, multiplier, negative subpattern, scientific notation |
| `DecimalFormatSymbols` | Symbol set: decimal separator, grouping separator, zero digit, minus sign, `%`, `‰`, currency symbol, NaN, Infinity, etc. |
| `Locale` | Selects language/region conventions; affects symbols, default formatting styles, and related localization data |

### 2.1. Getting started with `NumberFormat`

If you only want numbers formatted according to a `Locale`, it is usually best to use a factory:

```java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat formatter = NumberFormat.getNumberInstance(Locale.US);
String result = formatter.format(1234567.5);
```

This is an **illustrative code snippet**; place it inside a method or class to run. Using a factory lets Java pick the format matching the locale, instead of you guessing separators manually.

**Do not unconditionally cast** the result of `NumberFormat.getNumberInstance(locale)` to `DecimalFormat`: many providers return `DecimalFormat`, but the factory API does not guarantee always returning that exact subclass. If you need features specific to `DecimalFormat`:

```java
NumberFormat nf = NumberFormat.getNumberInstance(Locale.US);
if (nf instanceof java.text.DecimalFormat df) {
    df.applyPattern("#,##0.00");
}
```

This snippet uses **pattern matching for `instanceof`**, valid in Java 17. If business code requires a `DecimalFormat` directly, you can also instantiate `new DecimalFormat(pattern, symbols)` with an explicitly chosen symbol set, as shown in the following examples.

### 2.2. Do not implicitly rely on the default locale

`new DecimalFormat("#,##0.00")` pulls the symbol set of the default formatting locale. The same program may print `1,234.50` on one machine and `1.234,50` on another. For stable documentation, tests, and protocols, choose `Locale` or `DecimalFormatSymbols` explicitly.

Example:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

DecimalFormatSymbols us =
        DecimalFormatSymbols.getInstance(Locale.US);
DecimalFormat moneyLike = new DecimalFormat("#,##0.00", us);
```

The variable name `moneyLike` only indicates **how two fractional digits are displayed**. The pattern `#,##0.00` does not automatically attach a currency unit, ISO code, tax rules, or monetary rounding policy.

## 3. What is a pattern? Distinguishing structural characters from printed characters

`DecimalFormat` has **non-localized patterns** using standard structural characters. The pattern `#,##0.00` does not mean the output string will always contain literal commas and dots; those positions are replaced with the corresponding symbols from `DecimalFormatSymbols`.

Table of important symbols:

| Symbol | Role in a non-localized pattern | Example meaning |
| --- | --- | --- |
| `0` | **Required** digit, pads with `0` when missing | `0000` formats 12 as `0012` |
| `#` | **Optional** digit, omits unnecessary zeros | `0.##` has at most 2 fractional digits |
| `.` | Decimal separator position | Displays `.`, `,`, or another symbol per `DecimalFormatSymbols` |
| `,` | Integer grouping separator position | Thousands or group size per pattern/configuration |
| `;` | Separates positive and negative patterns | `0.00;(0.00)` |
| `%` | Percent; multiplies by 100 when formatting, divides by 100 when parsing per multiplier | `0.0%` |
| `‰` | Per mille; multiplier 1000 | `0.0‰` |
| `E` | Scientific/exponential notation | `0.00E0` |
| `¤` | Currency symbol per symbols/locale | `¤#,##0.00` |
| `¤¤` | International currency code (e.g., USD) | `¤¤ #,##0.00` |
| `'` | Quotes literal text/special symbols | `'Total:' #,##0.00` |

In Java string literals, most patterns in the table are written directly like `"#,##0.00"` or `"0.0%"`. The `‰` symbol is Unicode U+2030 and can be written in Java source as `"\u2030"` to avoid depending on source-file encoding/keyboard input. The currency sign `¤` is U+00A4.

### 3.1. `0` and `#`: required or optional

Given the number `12.5`:

```text
Pattern        Result with Locale.US symbols
0.00           12.50
0.##           12.5
0000.000       0012.500
```

With `0.00`, the format displays **exact two digits** after the decimal point. With `0.##`, it shows **at most two digits**, without forcing trailing zeros. With `0000.000`, the integer part is zero-padded to four digits and the fractional part to three digits.

**Note:** `DecimalFormat` is not a way to store numbers as strings with infinite precision. If formatting only allows two digits after the decimal point, remaining digits are omitted from the result and may have been **rounded at the string-representation stage**.

### 3.2. Grouping and the pattern `#,##0.00`

`#,##0.00` means:

- Display thousands grouping in the integer part.
- Have at least one integer digit.
- Have exact two fractional digits.
- Use separators defined by `DecimalFormatSymbols`.

Example:

```java
DecimalFormat usFormatter =
        new DecimalFormat("#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(usFormatter.format(1234567.5));
// 1,234,567.50
```

The comma **in the pattern** is a placeholder for grouping. The comma **in the US output** is the glyph supplied by `DecimalFormatSymbols`. These happen to be the same character in `Locale.US`, but need not match in other locales.

### 3.3. Group size and digit limits

You can also adjust properties via methods:

```java
DecimalFormat df = new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

df.setGroupingUsed(true);
df.setGroupingSize(4);
df.setMinimumFractionDigits(2);
df.setMaximumFractionDigits(2);
```

With `setGroupingSize(4)`, groups appear from right to left every four digits in the integer part. Understand this as a **display group width**, which does not change the numeric value. If you write a pattern with multiple grouping commas, `DecimalFormat` rules are not an arbitrary general system for all regional grouping hierarchies; the documentation describes how the pattern is interpreted and that the primary effective grouping mark is the last section near the integer digits.

Do not treat `setMaximumFractionDigits` as an input validator: limiting display digits does not automatically guarantee users only enter up to that many digits.

## 4. Two pattern parts: positive and negative numbers

A pattern can contain two subpatterns separated by `;`:

```text
#,##0.00;(#,##0.00)
```

Example output for `Locale.US`:

```text
 1234.5 ->  1,234.50
-1234.5 -> (1,234.50)
```

This suits accounting reports that prefer writing **negative numbers in parentheses**. If no negative subpattern is declared, Java typically uses the positive subpattern with a leading minus sign.

Note: per the `DecimalFormat` contract, the negative subpattern mainly determines the **negative prefix/suffix**; the minimum/maximum digit structure and grouping of the positive pattern are shared. Therefore, do not expect declaring two completely different digit sequences for positive/negative in one pattern to produce two independent precisions.

When parsing parenthesized negative numbers back, use a matching formatter and pattern. Do not apply an ad-hoc rule that strips and reattaches `-` if data has localized prefixes/suffixes.

## 5. Prefix, suffix, and quoting text

Patterns can attach words or symbols:

```java
DecimalFormat df = new DecimalFormat(
        "'Total:' #,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(df.format(1234.5));
// Total: 1,234.50
```

Single quotes `'...'` instruct Java to treat `Total:` as a literal character string in the prefix rather than pattern symbols. If you need a literal apostrophe character in a prefix/suffix, write two consecutive single quotes `''` per pattern rules.

**Do not assemble currency units, values, and separators by arbitrary string concatenation** in a multi-locale system: some locales place symbols before, others after; spacing and symbol conventions also vary. For monetary content, use currency factories or patterns with `¤` and proper currency metadata.

## 6. Percent and per mille: changing the multiplier

A common mistake is thinking `0.0%` just "appends a `%` sign". In fact, `%` also **multiplies the value by 100 when formatting**.

```java
DecimalFormat percent = new DecimalFormat("0.0%",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(percent.format(0.256)); // 25.6%
```

Input `0.256` is displayed as `25.6%`, rightly because `0.256×100=25.6`. If input already holds `25.6` meaning "25.6%", formatting with `0.0%` will multiply by 100 again; input data must follow a consistent convention.

The symbol `‰` (U+2030) denotes **per mille**, multiplying the value by **1000** when formatting:

```java
DecimalFormat perMille = new DecimalFormat(
        "0.0\u2030",
        DecimalFormatSymbols.getInstance(Locale.US));
```

This snippet displays `0.256` as `256.0‰` when the US per-mille symbol is `‰`. Java source uses the Unicode escape so the file stores the pattern independently of keyboard input.

When parsing a string with a percent suffix using a percent formatter, **the multiplier is applied in reverse**. For example, `percent.parse("25.6%")` returns a numeric value near `0.256` (exact type may be `Double` depending on parse config). Do not divide by 100 a second time after the parser has already handled the multiplier.

## 7. Scientific notation: `E` in patterns

`E` separates the significand and the decimal exponent of the **displayed string**:

```java
DecimalFormat scientific = new DecimalFormat("0.00E0",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(scientific.format(12345));
// 1.23E4
```

`0.00E0` specifies:

- One required digit before the decimal point in the significand.
- Two fractional digits.
- The letter `E` and at least one exponent digit.

`DecimalFormat` has dedicated rules for scientific/engineering notation when patterns have varying numbers of integer digits, such as `##0.###E0`. Do not manually divide input by 10ⁿ and concatenate `"E"` when Java already supports exponent formatting and the exponent separator can be customized via `DecimalFormatSymbols`.

**Note the two kinds of E:** `e/E` in `Double.parseDouble("1.23e4")` is syntax for **reading a numeric string**, whereas `E` in the pattern `"0.00E0"` is a **directive for how to output a string**. Do not interchange them as though `DecimalFormat` reads Java source literals.

## 8. Currency symbols: `¤`, `¤¤`, and `Currency`

`DecimalFormat` understands:

- `¤` (U+00A4) as the placeholder for `DecimalFormatSymbols`'s currency symbol, e.g., `$` for USD in a US context.
- `¤¤` as the placeholder for the international currency code, e.g., `USD`.
- Currency patterns may use a **monetary decimal separator** distinct from the regular decimal separator if the locale/symbols specify one.

Example:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Currency;
import java.util.Locale;

DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);
symbols.setCurrency(Currency.getInstance("USD"));

DecimalFormat formatter =
        new DecimalFormat("\u00A4#,##0.00", symbols);

String formatted = formatter.format(1234.5);
```

This is a snippet inside a Java method. With `Locale.US` and USD on a standard JDK, the result has the form **`$1,234.50`**. With `¤¤`, the output shows the code like `USD` instead of the short currency symbol.

**Do not use `¤` as currency conversion.** If the input is 1234.5 units of currency X, changing the symbol to USD **does not** compute an exchange rate and **does not** alter the monetary amount. The application must know the actual currency of the value and convert exchange rates separately if needed.

For default locale currency formatting, `NumberFormat.getCurrencyInstance(locale)` is usually preferable to hand-writing every pattern. Yet when fixed ISO codes, symbols, and fractional digits are required, control `Currency`, locale, and rounding according to business standards.

## 9. `DecimalFormatSymbols`: separating the number pattern from display glyphs

Take the same pattern `#,##0.00` but use symbols for two locales:

```java
DecimalFormat us = new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

DecimalFormat de = new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));
```

With the value `1234567.5`:

```text
US: 1,234,567.50
DE: 1.234.567,50
```

The pattern **does not change**. The symbol sets differ, so the resulting strings differ.

Commonly used `DecimalFormatSymbols` methods:

| Method | Meaning |
| --- | --- |
| `getDecimalSeparator()` / `setDecimalSeparator(char)` | General decimal separator |
| `getGroupingSeparator()` / `setGroupingSeparator(char)` | Grouping separator |
| `getMinusSign()` / `setMinusSign(char)` | Negative sign |
| `getZeroDigit()` / `setZeroDigit(char)` | Base zero digit for localized digit systems |
| `getPercent()` / `setPercent(char)` | Percent sign |
| `getPerMill()` / `setPerMill(char)` | Per-mille sign |
| `getCurrencySymbol()` / `setCurrencySymbol(String)` | Displayed currency symbol |
| `getInternationalCurrencySymbol()` | International currency code |
| `getExponentSeparator()` / `setExponentSeparator(String)` | Exponent separator |
| `getNaN()` / `setNaN(String)` | NaN representation |
| `getInfinity()` / `setInfinity(String)` | Infinity representation |

Some APIs also provide monetary grouping separator / monetary decimal separator. If you change currency symbols, carefully review the contract and consistency of related properties instead of changing only one decimal separator.

### 9.1. Defining custom separators

```java
DecimalFormatSymbols custom =
        DecimalFormatSymbols.getInstance(Locale.US);
custom.setGroupingSeparator('^');
custom.setDecimalSeparator('|');

DecimalFormat df = new DecimalFormat("#,##0.00", custom);
System.out.println(df.format(1234567.5));
// 1^234^567|50
```

**Takeaway:** `#,##0.00` still uses `,` and `.` as **placeholders in the pattern**. When displayed, the grouping character becomes `^`, and the decimal separator becomes `|`. This is a visual way to verify the difference between patterns and symbols.

If you customize them so **the same character** acts as both decimal and grouping separator, or the minus sign collides with a digit, parsing becomes ambiguous. `DecimalFormat`/`DecimalFormatSymbols` do not infer intent across nonsensical configurations. Design symbol sets so components remain distinguishable.

## 10. `applyPattern` and `applyLocalizedPattern` do not share the same semantics

`DecimalFormat.applyPattern(String)` accepts a **standard non-localized pattern**: `.` is the decimal placeholder, `,` is the grouping placeholder. It still uses the current `DecimalFormatSymbols` to render locale glyphs.

`DecimalFormat.applyLocalizedPattern(String)` accepts a **localized pattern**, where the decimal/grouping symbols inside the **input pattern string** match the formatter's symbol set.

Example with `Locale.GERMANY`:

```java
DecimalFormat df = new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));

df.applyPattern("#,##0.00");          // non-localized
df.applyLocalizedPattern("#.##0,00"); // localized to German symbols
```

Both patterns describe the same format layout and both can produce `1.234.567,50` when formatting `1234567.5`. If you pass `"#.##0,00"` to `applyPattern`, Java **does not** treat that `.` as grouping in the German reading sense; it uses **non-localized** structural rules, so it may fail or give a different meaning.

The companion methods are `toPattern()` and `toLocalizedPattern()` to retrieve the pattern in the two corresponding forms. This matters when **persisting configurations**: explicitly document whether the file stores a standard or localized pattern, and do not switch locales on reload without translating the syntax.

### 10.1. UIs allowing users to enter patterns

If a UI lets a German user type `#.##0,00`, you may need `applyLocalizedPattern`, since the user is writing in German symbols. If an internal system-generated config file uses `#,##0.00`, use `applyPattern` to avoid depending on local notation. Clearly identify the pattern source right at the API boundary, and do not mix the two conventions.

Do not accept arbitrary external patterns and run them unbounded in a performance-sensitive system without length/complexity limits, symbol policies, and boundary tests. A syntactically valid pattern may still fail business requirements for currency or digit counts; validation must go beyond "does not throw an exception".

## 11. Combining `RoundingMode` with patterns

The pattern `0.00` specifies two digits after the decimal point; `setRoundingMode` determines which direction to pick when fractional digits must be dropped. For `BigDecimal("2.345")`, `HALF_EVEN` gives `2.34`, while `HALF_UP` gives `2.35`. The formatter only outputs a string and does not modify the original `BigDecimal`. The full breakdown of all eight `RoundingMode` values, negative numbers, `UNNECESSARY`, and the difference between display and calculation rounding belongs in the lesson `RoundingMode of formatters`.

## 12. Complete program A: common patterns

Save as **`DecimalFormatPatterns.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalFormatPatterns {
    public static void main(String[] args) {
        DecimalFormatSymbols us =
                DecimalFormatSymbols.getInstance(Locale.US);

        System.out.println(new DecimalFormat("#,##0.00", us)
                .format(1234567.5));
        System.out.println(new DecimalFormat("#,##0.##", us)
                .format(1234567.5));
        System.out.println(new DecimalFormat("0000.000", us)
                .format(12.5));
        System.out.println(new DecimalFormat("#,##0.00;(#,##0.00)", us)
                .format(-1234.5));
        System.out.println(new DecimalFormat("0.0%", us)
                .format(0.256));
        System.out.println(new DecimalFormat("0.00E0", us)
                .format(12345));
        System.out.println(new DecimalFormat("'Total:' #,##0.00", us)
                .format(1234.5));
    }
}
```

Compile/run:

```bash
javac --release 17 DecimalFormatPatterns.java
java DecimalFormatPatterns
```

**Exact stdout** with the specified US symbols:

```text
1,234,567.50
1,234,567.5
0012.500
(1,234.50)
25.6%
1.23E4
Total: 1,234.50
```

Each line illustrates a feature: digit grouping, optional fractional digits, required zeros, parenthesized negative pattern, percent multiplier, scientific notation, and quoted prefix.

## 13. Complete program B: locales, symbols, and localized patterns

Save as **`DecimalFormatLocales.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalFormatLocales {
    public static void main(String[] args) {
        DecimalFormatSymbols us =
                DecimalFormatSymbols.getInstance(Locale.US);
        DecimalFormatSymbols de =
                DecimalFormatSymbols.getInstance(Locale.GERMANY);

        DecimalFormat usFormat = new DecimalFormat("#,##0.00", us);
        DecimalFormat deFormat = new DecimalFormat("#,##0.00", de);

        System.out.println(usFormat.format(1234567.5));
        System.out.println(deFormat.format(1234567.5));

        DecimalFormatSymbols custom =
                (DecimalFormatSymbols) us.clone();
        custom.setGroupingSeparator('^');
        custom.setDecimalSeparator('|');

        DecimalFormat customFormat =
                new DecimalFormat("#,##0.00", custom);
        System.out.println(customFormat.format(1234567.5));

        deFormat.applyLocalizedPattern("#.##0,00");
        System.out.println(deFormat.toPattern());
        System.out.println(deFormat.format(1234567.5));
    }
}
```

Run:

```bash
javac --release 17 DecimalFormatLocales.java
java DecimalFormatLocales
```

**Exact stdout:**

```text
1,234,567.50
1.234.567,50
1^234^567|50
#,##0.00
1.234.567,50
```

With `Locale.GERMANY`, the grouping and decimal separators swap in the **output string**. The canonical pattern `#,##0.00` does not change; the localized pattern `#.##0,00` is translated by `applyLocalizedPattern` into the corresponding canonical structure.

Using `clone()` to obtain an isolated symbol set before mutating symbols prevents accidentally modifying an object shared by other code. The mutability of formatters/symbols is why scope and thread ownership should be designed explicitly.

## 14. Complete program C: rounding with `BigDecimal`

Save as **`DecimalFormatRounding.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalFormatRounding {
    public static void main(String[] args) {
        DecimalFormat df = new DecimalFormat("0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        System.out.println(df.getRoundingMode());
        System.out.println(df.format(new BigDecimal("2.345")));
        System.out.println(df.format(new BigDecimal("2.355")));

        df.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println(df.format(new BigDecimal("2.345")));
        System.out.println(df.format(new BigDecimal("-2.345")));

        BigDecimal original = new BigDecimal("2.345");
        String display = df.format(original);
        System.out.println(display);
        System.out.println(original.toPlainString());
    }
}
```

Run:

```bash
javac --release 17 DecimalFormatRounding.java
java DecimalFormatRounding
```

**Stdout:**

```text
HALF_EVEN
2.34
2.36
2.35
-2.35
2.35
2.345
```

The last two lines are especially instructive: `display` has been rounded into the string `"2.35"` under `HALF_UP`, yet `original` remains `BigDecimal("2.345")`. Perform actual data operations if the rounded result needs to be persisted.

### 14.1. Effects of `setRoundingMode` and `setMaximumFractionDigits`

`DecimalFormat` has mutable properties. If you create a formatter once and later call `setMaximumFractionDigits(4)`, subsequent `format` calls may print up to four fractional digits. When users change formatting preferences, avoid reusing the same formatter instance to serve multiple different configurations concurrently.

If `RoundingMode.UNNECESSARY` is used, a formatting operation that requires dropping digits can throw `ArithmeticException`. Choose this mode when **policy forbids rounding**, and handle the exception instead of silently rounding.

## 15. Parsing with `DecimalFormat` has its own limitations

`DecimalFormat` reads strings according to its current pattern, symbols, and locale. `parse(String)` may accept only a valid prefix; when the whole string is required, use `ParsePosition` and compare `getIndex()` with `text.length()`. If exact finite decimals are desired, enable `setParseBigDecimal(true)` while still checking the result type, as some special values may be `Double`. `setParseIntegerOnly(true)` affects parsing and does not mean output formatting becomes integer-only.

The lessons `ParsePosition and whole-string validation when parsing by locale` and `setParseBigDecimal and thread-safety limits when using formatters concurrently` cover strict parsing examples, edge cases, and thread safety thoroughly.

## 16. Quick reference when parsing a localized string

```java
java.text.DecimalFormat f = new java.text.DecimalFormat(
        "#,##0.00",
        java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US));
f.setParseBigDecimal(true);
java.text.ParsePosition p = new java.text.ParsePosition(0);
String text = "1,234.50";
Number result = f.parse(text, p);
System.out.println(result instanceof java.math.BigDecimal
        && p.getIndex() == text.length()); // true
```

This snippet illustrates the pattern and symbols being used in the **parsing direction**. To enforce stricter grouping placement, value ranges, or allowed digits, add schema-level validation; full-string consumption is only a necessary condition.

## 17. Formatting and parsing are not perfect inverses

Suppose `DecimalFormat("0.00")` is used to print a value:

```text
Source value:    2.345
Displayed string: "2.34" or "2.35" depending on rounding
Parsed value:    2.34 or 2.35
```

Parsing back does not recreate every digit of the original source number, because **formatting truncated/rounded the displayed digits**. Thus:

```text
parse(format(x)) == x
```

**Is not a general identity.** Reasons include:

1. Rounding and digit limits in the pattern.
2. Locale-based grouping/decimal separators.
3. Percent/per-mille multipliers.
4. Currency or negative prefixes/suffixes.
5. Special strings `NaN`/`Infinity` and signed zero.
6. Parse policies returning `Long`, `Double`, or `BigDecimal`, which can change type and scale preservation.

For machine-to-machine data exchange requiring exact `double` round-trip, `Double.toString` and `Double.parseDouble` (with controlled schema constraints and special-value rules) are typically used rather than presentation format `#,##0.00`.

For exact decimals and money, transmit a canonical form per a well-defined schema (such as a canonical decimal string alongside currency code/scale), rather than using locale-dependent UI strings as an internal storage format.

## 18. Formatters hold mutable state

`DecimalFormat` allows changing pattern, symbols, multiplier, fraction digits, and mode while in use; therefore it is not safe by default when the same instance is accessed concurrently by multiple threads. The dedicated lesson on `setParseBigDecimal` and concurrent formatter usage guides local instances, `ThreadLocal`, and external synchronization.

## 19. `Locale` and business formatting

`DecimalFormatSymbols` changes decimal, grouping, minus, and currency symbols; do not assume every locale uses the same grouping or glyphs. Patterns and symbols serve presentation, not defining units, currencies, or tax rules. The lesson `Locale, decimal separator, digit grouping, and negative signs` and the final wire-format lesson of the chapter explain input/output policies in detail.

## 20. Common mistakes and fixes

| Misconception/Error | Why it is wrong | Right approach |
| --- | --- | --- |
| "`#,##0.00` always prints comma for grouping, dot for decimal" | Symbols depend on locale | Choose `DecimalFormatSymbols` explicitly |
| "`#` and `0` are identical" | `0` forces digit output, `#` is optional | Set min/max digits as required |
| "Two-digit formatting edits the source value" | `format` creates a new string | Round the data separately if business rules require it |
| "`0.0%` only appends the percent sign" | Multiplier is 100 | Clarify whether input is a fraction or percentage |
| "`¤` automatically converts currency" | Symbol does not compute exchange rates | Manage currency and conversion separately |
| "`applyPattern("#.##0,00")` reads as German symbols" | `applyPattern` takes a standard pattern | Use `applyLocalizedPattern` for localized patterns |
| "`new DecimalFormat(pattern)` does not depend on locale" | Constructor pulls symbols from default locale | Specify symbols/locale |
| "Successful `parse` means the whole string is valid" | Parser may consume only a prefix | Check `ParsePosition` and input grammar |
| "`setMaximumFractionDigits` limits input fractional digits" | Mainly a formatting rule | Separate input validation |
| "`parse(String)` always returns `Double`" | `Number` has multiple subtypes | Check/configure `setParseBigDecimal` |
| "`parseBigDecimal` turns NaN into a decimal" | NaN/Infinity have special handling | Reject non-finite values per schema |
| "`DecimalFormat` always defaults to `HALF_UP`" | Defaults to `HALF_EVEN` | Set `RoundingMode` explicitly |
| "Formatting `double` 2.345 is an exact decimal tie" | binary64 has rounding | Use `BigDecimal("2.345")` when demonstrating decimal ties |
| "A `static final` formatter shared across threads is always safe" | Formatter is mutable, not synchronized by default | Use separate instances or synchronization |
| "UI strings can serve as a universal storage format across all countries" | Locale, rounding, and separators vary | Pick a separate canonical interchange format |

## 21. Self-practice exercises with answers

### Exercise 1 — Pattern meaning

How does the pattern `#,##0.00` in `Locale.US` print `1234.5`?

**Answer:** `1,234.50`. The `0` digits in the fractional part require two digits; thousands grouping commas are displayed per US symbols.

### Exercise 2 — `0` and `#`

With `12.5` and US symbols, how do patterns `0000.000` and `0.##` differ?

**Answer:** `0012.500` and `12.5`. The first pads with zeros; the second prints only the necessary fractional digits (at most 2).

### Exercise 3 — Positive/negative subpatterns

With `#,##0.00;(#,##0.00)`, how is `-1234.5` represented?

**Answer:** `(1,234.50)` in `Locale.US`. The negative subpattern changes the negative prefix/suffix to parentheses.

### Exercise 4 — Percentage

What string does `new DecimalFormat("0.0%", us).format(0.256)` produce? Why?

**Answer:** `25.6%`. The `%` pattern multiplies the input by 100 and attaches the percent symbol.

### Exercise 5 — Scientific notation

What string does `"0.00E0"` print for `12345` in US?

**Answer:** `1.23E4`. One digit before the decimal point, two digits after, decimal exponent.

### Exercise 6 — `Locale`

With the same value `1234567.5` and the same standard pattern `#,##0.00`, how do US and German results differ?

**Answer:** US `1,234,567.50`; Germany `1.234.567,50`. Symbols change the glyphs without changing the value.

### Exercise 7 — Custom symbols

If the grouping separator is `^` and the decimal separator is `|`, how does the standard pattern `#,##0.00` print `1234567.5`?

**Answer:** `1^234^567|50`. You do not rewrite the pattern as `#^##0|00`; the two custom symbols only appear in the output symbols.

### Exercise 8 — `applyPattern` vs `applyLocalizedPattern`

With a German symbol set, which method should receive the pattern string `"#.##0,00"`?

**Answer:** `applyLocalizedPattern`. `applyPattern` expects standard `"#,##0.00"`, independent of local symbols.

### Exercise 9 — Half-even and half-up

With `BigDecimal("2.345")` and pattern `0.00`, what do `HALF_EVEN` and `HALF_UP` produce?

**Answer:** `2.34` and `2.35`. Under `HALF_EVEN`, ties pick the even final digit.

### Exercise 10 — Does formatting lose source data?

A `BigDecimal("2.345")` is formatted to `"2.35"`. What is `toPlainString()` of the original `BigDecimal` after formatting?

**Answer:** Still `2.345`. The formatter produces a string and does not mutate the `BigDecimal` value.

### Exercise 11 — Prefix parsing

`df.parse("123abc", new ParsePosition(0))` returns `123` and position 3. Should the whole input be accepted?

**Answer:** No, if the schema requires the entire string to be a number. Compare `ParsePosition.getIndex()` with `input.length()` and add grammar checks if needed.

### Exercise 12 — `Number` subtype

Does `DecimalFormat.parse("1,234.50")` always return `Double`?

**Answer:** No. `parse` is declared to return `Number`; it can return different subtypes depending on settings/input, including `setParseBigDecimal(true)` causing finite decimals to be returned as `BigDecimal`.

### Exercise 13 — `setParseBigDecimal`

With `setParseBigDecimal(true)` and parsing `"1,234.50"` under US symbols, what is the displayed value of `Number`?

**Answer:** `1234.50`, of type `BigDecimal` in this case. This is useful when you need to preserve decimal numbers instead of parsing via binary `double`.

### Exercise 14 — Thread safety

Why should you not share a `static final DecimalFormat` object across dozens of threads without synchronization?

**Answer:** `final` does not make a mutable object immutable; `DecimalFormat` is not thread-safe/synchronized by default. Use separate scope or external synchronization.

### Exercise 15 — Currency

The pattern `¤#,##0.00` with USD is used to display a monetary amount. Does it automatically convert an EUR amount into USD?

**Answer:** No. The pattern only chooses the symbol/string and display layout; it has no exchange rate or unit conversion.

### Exercise 16 — Round-trip

Why might `parse(format(x))` not equal `x` after formatting `x` with pattern `0.00`?

**Answer:** Formatting rounded and limited the fractional part, potentially discarding information from `x`. Parsing the display string cannot automatically restore the original digits.

## 22. Checklist when using `DecimalFormat` in projects

- [ ] I distinguish **numeric values** from **formatted strings** and know formatting does not mutate inputs.
- [ ] I use `NumberFormat` factories when only locale formatting is needed, without unconditional subclass casts.
- [ ] I know `DecimalFormat` is a class with patterns and mutable properties.
- [ ] I correctly explain `0`, `#`, `.`, `,`, `;`, `%`, `‰`, `E`, `¤`, and `'...'` quoting.
- [ ] I know the pattern `#,##0.00` is **non-localized**, while the output string takes separators from `DecimalFormatSymbols`.
- [ ] I use `DecimalFormatSymbols.getInstance(locale)` instead of relying on an arbitrary environment.
- [ ] I distinguish `applyPattern` and `applyLocalizedPattern` when reading pattern configurations.
- [ ] I control positive/negative subpatterns and negative number display policies.
- [ ] I understand percent/per-mille multipliers and do not multiply or divide twice.
- [ ] I know the `¤` symbol binds to currency metadata, not an exchange-rate formula.
- [ ] I set `RoundingMode` as required, using `BigDecimal` when exact decimal rounding is needed.
- [ ] I do not treat two-decimal `format` as the step for rounding and saving business data.
- [ ] I know `parse` returns `Number` and may accept only part of a string.
- [ ] I check `ParsePosition`/length, choosing `setParseBigDecimal` when decimals must be preserved.
- [ ] I do not share one mutable instance across multiple threads without synchronization.
- [ ] I use machine-to-machine formats with fixed schemas rather than locale-based UI strings.
- [ ] I ran the four programs and tested negative numbers, zero, rounding ties, garbage inputs, and multiple locales.

## 23. Official Java SE 17 documentation

- [DecimalFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) — patterns, positive/negative subpatterns, multipliers, rounding, parsing, symbols, thread safety.
- [DecimalFormatSymbols API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html) — decimal, grouping, minus, currency, percent, exponent, NaN/Infinity symbols.
- [NumberFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) — factory methods and format/parse attributes.
- [ParsePosition API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html) — checking the index consumed by the parser.
- [Locale API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) — choosing locales and cultural conventions.
- [RoundingMode API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html) — rounding rules.
- [BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) — exact decimal representation from string sources and scale.
- [Currency API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html) — currency metadata.
- [Oracle Java Tutorial — Customizing Formats](https://docs.oracle.com/javase/tutorial/i18n/format/decimalFormat.html) — pattern/symbol examples (legacy tutorial; cross-check Java SE 17 API for version details).

**Summary:** `DecimalFormat` determines the **presentation layout**, `DecimalFormatSymbols` determines **which glyphs are displayed**, and `Locale` provides **regional conventions**. Always separate **computing/storing values**, **display formatting**, **input parsing**, and **business validation**; that way, changing separators, formatting money, percentages, or rounding will never accidentally alter numeric meaning in the program.