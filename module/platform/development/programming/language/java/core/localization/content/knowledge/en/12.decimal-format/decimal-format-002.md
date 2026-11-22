# Symbols 0, #, Decimal Point, and Grouping Separator in DecimalFormat

`java.text.DecimalFormat` is Java's number formatting class that lets you write **patterns** to control minimum/maximum digit counts, fractional parts, digit grouping, and symbols appearing in the output string. The four most important symbols in this lesson are:

- `0` — **required digit**: when a digit is missing at a display position, the formatter pads with 0.
- `#` — **optional digit**: unnecessary zeros at that position can be omitted.
- `.` — **decimal point position in the pattern**; the output uses the decimal separator from `DecimalFormatSymbols`.
- `,` — **grouping separator position in the pattern**; the output uses the grouping separator from `DecimalFormatSymbols` when grouping is enabled.

For example, with `Locale.US`, the pattern `#,##0.00` formats the number `12345.6` into `12,345.60`. With `Locale.GERMANY`, the **same non-localized pattern** yields `12.345,60`. The pattern defines the **number structure**; the locale's symbol set determines the **displayed characters**.

This lesson analyzes the meaning of each symbol individually, how to combine them, rounding and parsing mechanisms, the role of locale, along with runnable Java 17+ examples.

## 1. Distinguishing the pattern from the output value

A number like `1234.5` can be displayed as:

| Pattern | Locale | Output string |
| --- | --- | --- |
| `0` | `en-US` | `1234` or `1235` depending on rounding rule and fractional part; keeps no fraction |
| `0.00` | `en-US` | `1234.50` |
| `#,##0.00` | `en-US` | `1,234.50` |
| `#,##0.00` | `de-DE` | `1.234,50` |
| `000000.000` | `en-US` | `001234.500` |

When **formatting**, the formatter takes a number and returns a string. It does not mutate the original numeric value. When **parsing a string** with `parse`, the formatter performs the reverse according to its own configuration, though default parsing is not a strict financial text validator.

**Rounding note:** With the pattern `0`, `1234.5` uses `RoundingMode.HALF_EVEN` by default in `DecimalFormat`, resulting in `1234` (the ones digit 4 is even). If the application configures `HALF_UP`, the result becomes `1235`. Do not rely on saying "truncates the fractional part" because formatting can **round**, not truncate.

## 2. The `0` symbol — a required digit

In the **numeric section** of a pattern, each `0` represents a digit position that must be printed. When the integer part is shorter than the minimum `0` positions, Java pads with zeros on the left. When the fractional part is shorter than the minimum `0` positions, Java pads with zeros on the right.

Examples with `Locale.US`:

| Pattern | Value | Result | Reason |
| --- | ---: | --- | --- |
| `0` | 7 | `7` | At least one integer digit |
| `0000` | 7 | `0007` | Four minimum integer digits |
| `0000` | 12345 | `12345` | More than four digits are still displayed normally |
| `0.00` | 12.5 | `12.50` | Two required fractional digits |
| `000.000` | 12.5 | `012.500` | Three integer digits and three fractional digits |
| `0.00` | 0 | `0.00` | Fractional part still prints two zeros |

`0` **does not mean only one digit is allowed**: the pattern `0` can still display a large integer. The count of `0` symbols controls the **minimum**, not necessarily an absolute width for the integer part.

To generate fixed-width codes like `0007`, make a clear distinction: this formatting approach only fits when the code is truly generated from a number; if an identifier contains leading zeros as raw data (postal codes, account numbers, serial numbers), store it as a **string** to avoid losing leading zeros during numeric conversion.

## 3. The `#` symbol — an optional digit

`#` indicates a position where a digit **may** appear, without forcing a 0 if that position is unnecessary. It is typically placed on the left of the integer part or on the right of the fractional part:

| Pattern | Value | `en-US` Result |
| --- | ---: | --- |
| `0.##` | 12.5 | `12.5` |
| `0.##` | 12.00 | `12` |
| `0.##` | 12.567 | `12.57` |
| `#,##0.##` | 12345.6 | `12,345.6` |
| `#,##0.##` | 12345 | `12,345` |
| `#.##` | 12.5 | `12.5` |

Accurate interpretation:

- `0.00` — **exactly two fractional digits displayed**, rounding if needed.
- `0.##` — **at most two fractional digits**, without forcing trailing zeros.
- `0.0#` — **at least one, at most two** fractional digits.
- `#,##0.00` — groups integer digits, displays two digits after the decimal point.
- `#,##0.##` — groups digits with a variable fractional part.

**The zero value case:** Even though `#` means optional, `new DecimalFormat("#", symbols).format(0)` on Java 17+ still yields `"0"`: `DecimalFormat` ensures an appropriate representation is displayed for zero instead of leaving the entire number blank by default. Therefore, do not mechanically interpret "every `#` drops zeros, so zero becomes an empty string".

## 4. Runnable example: comparing `0` and `#`

Create the file **`DigitPlaceholdersDemo.java`**:

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DigitPlaceholdersDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        String[] patterns = {
                "0", "0000", "#", "0.00",
                "0.##", "#.##", "#,##0.00", "#,##0.##"
        };

        for (String pattern : patterns) {
            DecimalFormat formatter = new DecimalFormat(pattern, symbols);
            System.out.println(pattern + " | " +
                    formatter.format(0) + " | " +
                    formatter.format(12.5) + " | " +
                    formatter.format(12345.678));
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac DigitPlaceholdersDemo.java
java DigitPlaceholdersDemo
~~~

Output on Java with `Locale.US` symbols:

~~~text
0 | 0 | 12 | 12346
0000 | 0000 | 0012 | 12346
# | 0 | 12 | 12346
0.00 | 0.00 | 12.50 | 12345.68
0.## | 0 | 12.5 | 12345.68
#.## | 0 | 12.5 | 12345.68
#,##0.00 | 0.00 | 12.50 | 12,345.68
#,##0.## | 0 | 12.5 | 12,345.68
~~~

From the table, observe:

1. `0000` only adds zeros at the **beginning of the integer part** when missing.
2. `0.00` always has two decimal digits; `0.##` can omit the fractional part entirely.
3. `#,##0.00` applies digit grouping when the integer part is large enough.
4. `12345.678` becomes `12345.68` in patterns with two decimal digits due to **rounding**.

`DecimalFormatSymbols` is obtained for `Locale.US` so the example produces predictable results without depending on the host machine's default locale.

## 5. The period `.` in a pattern: logical decimal point

In a **non-localized pattern** (used by the `DecimalFormat(pattern, symbols)` constructor and `applyPattern(String)`), the period `.` is the **positional symbol separating the integer and fractional parts**.

That **does not mean the output always contains a period character**. The formatter will use the current decimal separator in its `DecimalFormatSymbols`. For example:

~~~text
Pattern:       #,##0.00
Locale.US:     1,234.50
Locale.GERMANY:1.234,50
~~~

In the German example, the `.` *in the pattern* is rendered as `,` *in the output*. This is the most important property to avoid hardcoding decimal separators in international applications.

A pattern like `0.00` has a decimal point by design and **requires** two fractional digits. The pattern `0.##` only outputs fractional digits when needed: `1234` formats as `1234`, not necessarily `1234.`.

Additionally, `DecimalFormat.setDecimalSeparatorAlwaysShown(true)` can force the decimal separator to appear even when there are no fractional digits. For example, `new DecimalFormat("#,##0.##", symbols)` with that flag can format `1234` as `1,234.` (this is a separate option, not inferred solely from `#`).

### Decimal separator vs. "converting data"

The value `1234.5` in a Java program still represents the same number. `DecimalFormat` only creates a display string. Do not replace characters in a formatted string and treat it as a complete "locale conversion": beyond the decimal separator, there are grouping separators, digits, currency, minus signs, and many other rules.

## 6. The comma `,` in a pattern: digit grouping position

In a **non-localized pattern**, the comma `,` instructs the formatter to use **grouping** for the integer part. Typically, the pattern `#,##0` groups every three digits from right to left:

| Number | `#,##0` in `en-US` | `#,##0` in `de-DE` |
| ---: | --- | --- |
| 123 | `123` | `123` |
| 1234 | `1,234` | `1.234` |
| 12345 | `12,345` | `12.345` |
| 1234567 | `1,234,567` | `1.234.567` |

The same comma `,` in the pattern renders according to `DecimalFormatSymbols.getGroupingSeparator()`, for instance as a period in `Locale.GERMANY`. Grouping separators aid human readability but **perform no arithmetic** and do not affect the underlying number.

**Grouping is not a requirement for every application.** For identifiers, software versions, machine-to-machine data exchange, or certain normalized expressions, inserting grouping is usually inappropriate. For user-facing values, digit grouping generally improves readability but should follow local conventions.

### Grouping vs. fractional part

The grouping separator in a pattern belongs to the **integer part**, while the decimal separator marks the **boundary between integer and fraction**. For example:

~~~text
#,##0.00
 ^   ^
 |   └── decimal point position
 └────── digit grouping position
~~~

The position of the grouping separator in the pattern determines the **grouping size**. With this pattern, the grouping size is 3. The result of `1234567.8` in `Locale.US` is `1,234,567.80`.

Do not place grouping separators arbitrarily in the fractional part; `DecimalFormat` numeric patterns have their own syntax, and grouping is defined in the integer part.

## 7. Locale and `DecimalFormatSymbols` determine the actual characters

`DecimalFormatSymbols` is the set of symbols that `DecimalFormat` uses to format and parse numbers: including decimal separator, grouping separator, zero digit, minus sign, and many other symbols.

Create **`LocaleSeparatorsDemo.java`**:

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LocaleSeparatorsDemo {
    public static void main(String[] args) {
        String pattern = "#,##0.00";

        DecimalFormat us = new DecimalFormat(
                pattern, DecimalFormatSymbols.getInstance(Locale.US));
        DecimalFormat germany = new DecimalFormat(
                pattern, DecimalFormatSymbols.getInstance(Locale.GERMANY));

        System.out.println("US: " + us.format(12345.6));
        System.out.println("DE: " + germany.format(12345.6));
    }
}
~~~

~~~bash
javac LocaleSeparatorsDemo.java
java LocaleSeparatorsDemo
~~~

Output:

~~~text
US: 12,345.60
DE: 12.345,60
~~~

**Mechanism:** `DecimalFormat` reads the same pattern structure `#,##0.00` and uses the locale symbols at the time the formatter is created. It is not that the pattern string was translated into German; it remains a **non-localized standard pattern**.

Locale data can update across JDKs/providers, and some regions use special whitespace or different numbering systems. When exact Unicode output comparison is needed in tests, identify the JDK and provider in use; do not assume two visually similar spaces are the same character.

## 8. Customizing symbols instead of editing the pattern

You can proactively configure symbols through `DecimalFormatSymbols`. This is a useful tool when output requirements do not strictly follow default locale rules.

Example **`CustomSeparatorsDemo.java`**:

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class CustomSeparatorsDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        symbols.setGroupingSeparator('_');
        symbols.setDecimalSeparator(':');

        DecimalFormat formatter =
                new DecimalFormat("#,##0.00", symbols);

        System.out.println(formatter.format(12345.6));
    }
}
~~~

~~~bash
javac CustomSeparatorsDemo.java
java CustomSeparatorsDemo
~~~

Output:

~~~text
12_345:60
~~~

The `,` and `.` **in the pattern remain unchanged**. Only the output characters change according to symbols. This is also why you should not use `new DecimalFormat(pattern)` and rely on the JVM default in multi-user programs; pass locale/symbols explicitly.

`DecimalFormatSymbols` is mutable, and `DecimalFormat` is also mutable. If you want multiple formatters with different symbol sets, create explicit configurations for each formatter. Avoid mutating a formatter shared across multiple threads.

## 9. `applyPattern` and `applyLocalizedPattern` do not accept the same pattern dialect

This is a common error when seeing a German-formatted number and thinking the pattern must also swap its separators.

- `applyPattern(String)` accepts a **non-localized pattern**: using `.` as the decimal placeholder and `,` as the grouping placeholder.
- `applyLocalizedPattern(String)` accepts a **pattern using the current symbol set**: with German symbols, the decimal and grouping separators in a localized pattern are `,` and `.`, respectively.

Example:

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.GERMANY);

DecimalFormat formatter = new DecimalFormat("#,##0.00", symbols);

System.out.println(formatter.toPattern());
System.out.println(formatter.toLocalizedPattern());
~~~

This is a **snippet inside a Java method** with imports `java.text.DecimalFormat`, `java.text.DecimalFormatSymbols`, and `java.util.Locale`. Result on Java using common German symbols:

~~~text
#,##0.00
#.##0,00
~~~

Key takeaway: **do not pass `#.##0,00` to `applyPattern` expecting it to be a German pattern**, because that method interprets characters using standard pattern syntax, leading to a different meaning or an error. If accepting patterns written with user-visible symbols, know the pattern's origin and use the matching API.

### Why prefer non-localized patterns in source code?

An application serving multiple locales typically stores a standard pattern structure like `#,##0.00`. The formatter combines the pattern with the active locale's symbols. This avoids managing different pattern strings solely because decimal and grouping separators differ.

`applyLocalizedPattern` remains useful when a tool allows users to **enter patterns using their own separators**, though the product needs to explain the syntax and validate input to prevent misunderstandings.

## 10. Group size and multiple commas

With the pattern `#,##0`, the distance between the last grouping separator and the last integer digit is three digits, so the size is typically 3. You can change it with `setGroupingSize(int)`:

~~~java
DecimalFormat fmt = new DecimalFormat(
        "#,##0", DecimalFormatSymbols.getInstance(Locale.US));
fmt.setGroupingSize(4);
System.out.println(fmt.format(12345678));
~~~

This is a **snippet inside a method**, requiring importing `DecimalFormat`, `DecimalFormatSymbols`, and `Locale`. Result:

~~~text
1234,5678
~~~

A grouping size of 4 may suit special display needs, but does not mean it matches every region's grouping rules.

### Multiple grouping separators do not create multiple distinct group sizes in `DecimalFormat`

A pattern like:

~~~text
##,##,##0.00
~~~

might lead learners to expect a string in the style of "3 digits in the last group, then 2 digits in earlier groups", such as `1,23,45,678.90`. In **standard `java.text.DecimalFormat`**, additional grouping separators do not create multiple independent hierarchical group sizes like that: **the distance from the rightmost grouping separator** determines the size.

With the pattern above in `Locale.US` and the number `12345678.9`, Java produces:

~~~text
12,345,678.90
~~~

If an application truly requires multi-level custom grouping (e.g., regional standards like 3 then 2), check APIs/libraries that support the requirement rather than inferring it by adding extra commas to `DecimalFormat`.

**Note:** `NumberFormat.getNumberInstance(locale)` may select the provider's grouping rules for that locale. A custom pattern forcing a size is another option; verify behavior on your deployment runtime.

## 11. Rounding: `0` and `#` do not decide every rule

The pattern defines the **allowed or required number of fractional digits**, while the rounded result also depends on `RoundingMode`.

- `0.00`: minimum and maximum two fractional digits.
- `0.##`: 0 to 2 fractional digits.
- `0.0#`: 1 to 2 fractional digits.
- When a number has more digits than the limit, the formatter **rounds** according to the rounding mode.

`DecimalFormat` defaults to `RoundingMode.HALF_EVEN` (rounds toward the even digit at exact midpoints). Some business rules require `HALF_UP` or another mode: specify it explicitly.

Example **`RoundingDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingDemo {
    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234.565");

        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        System.out.println(formatter.format(value));

        formatter.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println(formatter.format(value));
    }
}
~~~

~~~bash
javac RoundingDemo.java
java RoundingDemo
~~~

Output:

~~~text
1,234.56
1,234.57
~~~

With `HALF_EVEN`, the exact midpoint `...565` rounds to `...56` because the last retained digit 6 is even. With `HALF_UP`, it rounds to `...57`.

**Why use `BigDecimal("1234.565")`?** A decimal value created from a string stays exact, avoiding binary representation error from `double` that makes midpoint examples unpredictable. In monetary applications, `BigDecimal` is generally more appropriate for business calculations and rounding; `DecimalFormat` only handles the **presentation** layer.

Do not round by slicing strings after `format`, as that can break grouping separators, minus signs, and decimal rules.

## 12. Toggling grouping and forced decimal separator

Beyond patterns, `DecimalFormat` has key setters:

| API | Effect |
| --- | --- |
| `setGroupingUsed(boolean)` | Enables or disables digit grouping |
| `setGroupingSize(int)` | Configures number of digits per group |
| `setMinimumIntegerDigits(int)` | Minimum integer digits |
| `setMinimumFractionDigits(int)` | Minimum fractional digits |
| `setMaximumFractionDigits(int)` | Maximum fractional digits |
| `setDecimalSeparatorAlwaysShown(boolean)` | Whether to print the decimal separator when there are no fractional digits |
| `setRoundingMode(RoundingMode)` | Rounding rule |
| `setDecimalFormatSymbols(DecimalFormatSymbols)` | Changes display/parsing symbol set |

Example:

~~~java
DecimalFormat f = new DecimalFormat(
        "#,##0.##", DecimalFormatSymbols.getInstance(Locale.US));
f.setGroupingUsed(false);
System.out.println(f.format(12345.6));

f.setDecimalSeparatorAlwaysShown(true);
System.out.println(f.format(1234));
~~~

This is a **snippet inside a method**, requiring importing `DecimalFormat`, `DecimalFormatSymbols`, and `Locale`. Result:

~~~text
12345.6
1234.
~~~

The number `12345.6` no longer has a grouping separator when grouping is disabled; on the next line, the decimal separator is still printed even though the fraction has no digits. In most UIs, there is no need to enable `setDecimalSeparatorAlwaysShown(true)` unless the data design specifically requires that trailing separator.

**Configuration order matters:** calling setters after the constructor can override constraints established by the initial pattern. If caching a formatter, ensure it is fully configured before use, and do not modify the same instance from multiple threads.

## 13. Formatting and parsing are not the same strict check

`format(number)` converts **numeric value → text**. `parse(text)` converts **text → a `Number`** using the formatter's configuration. Default parsing in `DecimalFormat` can **stop at an invalid character** instead of requiring the entire input to be consumed.

Example with `Locale.US` and pattern `#,##0.00`:

~~~java
DecimalFormat f = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(f.parse("1,234.50"));
System.out.println(f.parse("1.234,50"));
~~~

This is an illustrative snippet inside a method handling `ParseException` or declaring `throws Exception`, with corresponding imports. On Java 17+:

~~~text
1234.5
1.234
~~~

The second line does **not** mean `"1.234,50"` was correctly understood as one thousand two hundred thirty-four point five. The US-style formatter treats the period as a decimal point and stops before the remaining comma; if the application ignores the unread remainder, it can silently receive the wrong number.

### Using `ParsePosition` to see how far the parser read

Example **`ParsePositionDemo.java`**:

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParsePositionDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        String input = "1,234.50XYZ";
        ParsePosition pos = new ParsePosition(0);
        Number result = formatter.parse(input, pos);

        System.out.println(result);
        System.out.println(pos.getIndex());
        System.out.println(pos.getIndex() == input.length());
    }
}
~~~

~~~bash
javac ParsePositionDemo.java
java ParsePositionDemo
~~~

Output:

~~~text
1234.5
8
false
~~~

The parser read the first 8 characters and left `XYZ` behind. When validating input, check `result != null`, `pos.getErrorIndex()`, and whether `pos.getIndex()` equals the input length.

Even when the entire string is consumed, locale parsing can still allow some unexpected grouping forms; if **strict input rules** are required, add extra validation according to product specifications. For JSON and inter-system data, standard locale-independent number representations are usually used for exchange.

### Getting a `BigDecimal` result

You can call `formatter.setParseBigDecimal(true)` before `parse` when you need to preserve decimal representation accuracy. You must still validate the input and locale; returning `BigDecimal` does not guarantee the original string meets business standards.

## 14. Patterns are formatting conventions, not arbitrary numeric text

Commonly confused examples:

- `"1,234.56"` is a **US-style numeric string**, **not** a pattern describing a number with grouping and two decimal digits; the proper pattern is usually `#,##0.00`.
- `"1.234,56"` is a **German-style numeric string**, **not** a non-localized pattern. Passing that string to `new DecimalFormat(pattern)` makes Java interpret the separators differently.
- `"#,###"` and `"#,##0"` are not completely equivalent in required digits; in particular, choose the form with an explicit `0` to avoid ambiguity at zero.
- `"0.000"` does not mean "take three decimal digits by truncation"; the formatter rounds according to the rounding mode.
- `"#,##0.##"` does not promise there will always be a decimal separator or two fractional digits.
- `"0000"` does not guarantee the output has exactly four characters for numbers with more than four digits.

When formatting currency or percentages, `DecimalFormat` patterns also have `¤` or `%` symbols, though those requirements also involve units, scale, and locale conventions; do not treat the plain numeric patterns in this lesson as a full substitute for `NumberFormat.getCurrencyInstance(locale)` or the corresponding business logic.

## 15. Proper use in multi-user applications

`DecimalFormat` is **mutable** and not guaranteed to be thread-safe. Code handling multiple concurrent requests should not share a `static final DecimalFormat` and mutate its locale, symbols, or rounding mode per request.

A helper can create a formatter for specific needs:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalFormattingService {
    public static String display(BigDecimal amount, Locale locale) {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(locale));

        formatter.setRoundingMode(RoundingMode.HALF_UP);
        return formatter.format(amount);
    }

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");

        System.out.println(display(amount, Locale.US));
        System.out.println(display(amount, Locale.GERMANY));
    }
}
~~~

~~~bash
javac DecimalFormattingService.java
java DecimalFormattingService
~~~

Output:

~~~text
1,234.50
1.234,50
~~~

Each call creates its own formatter with an explicit locale and explicit rounding mode. For high-performance requirements, you can optimize formatter lifecycle after measuring, while maintaining thread safety and locale correctness. `DecimalFormatSymbols` should also be treated as configuration to specify explicitly rather than relying on the global JVM default.

**Do not store formatted strings as calculation data.** Store numbers in an appropriate type, then format at the presentation boundary. If the value itself is an exchange rate or money, keep the number, currency code, scale, and business rounding rules separate—do not infer everything from grouping/decimal separators.

## 16. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `#.##` when always wanting two decimals | `12.5` instead of `12.50` | Use `0.00` for required fractional digits |
| Using `0000` to strictly cap at four digits | Five-digit numbers are still longer than four | Validate length separately if it is an identifier |
| Swapping `.`/`,` via `String.replace` | Easily corrupts grouping/decimal separators | Use the locale's symbols |
| Writing a German-style pattern into `applyPattern` | Parser misinterprets separator meanings | Use non-localized patterns or `applyLocalizedPattern` properly |
| Treating `parse` as full-string validation | Invalid input may be partially accepted | Use `ParsePosition` and additional validation |
| Rounding by slicing the result string | Wrong results and broken separators | Use `RoundingMode` and exact numeric data |
| Using `new DecimalFormat(pattern)` for all users | Tied to JVM default locale | Pass `DecimalFormatSymbols.getInstance(locale)` |
| Sharing a mutable formatter across threads | Can cause races/mixed configurations | Create per request or synchronize under control |
| Assuming `#` turns zero into empty string | Wrong output expectation | Test with zero; understand `DecimalFormat` zero digits behavior |
| Adding extra commas expecting 3-2 grouping | Standard Java still uses the last size | Check API rules or an appropriate library |

## 17. Self-check exercises

**1.** Under `Locale.US`, what does `new DecimalFormat("000.00", symbols).format(7.5)` produce?

**Answer:** `007.50`. Three integer positions and two fractional positions are all required.

**2.** Why does the pattern `0.##` format `12` as `12` instead of `12.00`?

**Answer:** The two `#` symbols after the decimal point are **optional**, so unnecessary fractional digits can be omitted.

**3.** Why does the pattern `#,##0.00` contain a comma yet German output has a period for grouping?

**Answer:** The comma in a non-localized pattern is a **logical grouping symbol**; the locale's `DecimalFormatSymbols` determines the actual output character.

**4.** Does the pattern `0000` force the number `123456` into a four-digit string?

**Answer:** No. `0` specifies a minimum, not a maximum length for the integer part.

**5.** Is `DecimalFormat.parse("1.234,50")` with US symbols guaranteed to return `1234.5`?

**Answer:** No. The parser may interpret the period as a decimal point and stop at the comma; check the parse position and use the right locale.

**6.** Why choose `BigDecimal("1234.565")` instead of `double 1234.565` for monetary values when illustrating exact midpoint rounding?

**Answer:** `BigDecimal` created from a string preserves the exact decimal representation, preventing binary floating-point errors from affecting rounding results.

**7.** To produce `12,345.60` from `12345.6` under `Locale.US`, which pattern is appropriate?

**Answer:** `#,##0.00`.

**8.** What is the difference between `applyPattern` and `applyLocalizedPattern`?

**Answer:** The former interprets standard `.`/`,` symbols in a non-localized pattern; the latter interprets pattern symbols according to the formatter's `DecimalFormatSymbols`.

**9.** How can you use `_` for grouping while keeping the pattern structure `#,##0.00`?

**Answer:** Create/set a `DecimalFormatSymbols` with `setGroupingSeparator('_')` and use a formatter with those symbols.

**10.** Why shouldn't a mutable `DecimalFormat` instance be shared across requests with different locales?

**Answer:** It is not guaranteed thread-safe, and setters can alter configuration across formatting operations.

## 18. Core knowledge summary

- **`0` = required digit**; pads with zeros to reach the minimum.
- **`#` = optional digit**; does not force trailing zeros in the fractional part.
- **`.` in a pattern = decimal separator position**, while the output character comes from symbols.
- **`,` in a pattern = grouping position**, while the output character and group size come from configuration.
- **Non-localized patterns** keep structure uniform across locales; symbols make display vary.
- `format` can **round**, so use `BigDecimal` and an explicit `RoundingMode` when precision matters.
- `parse` can read **part** of a string; check parse position and validation policies.
- `DecimalFormat` is mutable; create formatters per context locale rather than relying on JVM defaults or unsynchronized sharing.

**Authoritative references:** [DecimalFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html), [DecimalFormatSymbols — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html), [NumberFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html).
