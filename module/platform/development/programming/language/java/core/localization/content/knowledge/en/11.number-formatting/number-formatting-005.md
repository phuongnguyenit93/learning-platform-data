# Integer Digits, Fraction Digits, and Rounding Impact in Java

When formatting a number for a `Locale`, we do not merely choose a comma or a period. We also decide **how many digits at minimum/maximum the integer part must have**, **how many fractional digits are allowed**, and **which rounding rule applies**. In Java, `java.text.NumberFormat` provides four pairs of digit-count properties; `java.text.DecimalFormat` adds patterns, symbols, and fine-grained control.

The most common points of confusion:

- **Minimum digit counts** usually **pad with zeros to reach the required display width**; they do not multiply or divide the value.
- **Maximum fraction digits** can **round the fractional part**.
- **Maximum integer digits**, especially with `DecimalFormat`, can **drop high-order digits** when displaying, rather **than** rounding to a number with fewer digits.
- **A formatted string is not the raw number**: changing the number of displayed digits does not mutate an input `BigDecimal` or `double`; however, if you take the formatted string as input for calculations, you can lose information.

This lesson uses **Java 17+**, `NumberFormat`, `DecimalFormat`, `BigDecimal`, and `RoundingMode`, with standalone runnable examples, verifiable output, and warnings for financial data.

## 1. Integer Part and Fractional Part of a Number

For a decimal number written in English convention:

```text
               12345.6789
               ----- ----
               whole frac
               part  part

Formatted in en-US: 12,345.68
Formatted in de-DE: 12.345,68
```

In both results, the **source value** can still be `12345.6789`; the thousands separator and decimal mark are **presentation rules** of the locale, while the two fractional digits result from the digit-limit configuration. Do not confuse a period character in a UI string with the decimal point of a `BigDecimal` or Java numeric literal.

Key APIs:

| Property | Getter | Setter | Effect when formatting |
| --- | --- | --- | --- |
| **Minimum** integer digits | `getMinimumIntegerDigits()` | `setMinimumIntegerDigits(int)` | Pads zeros on the left when fewer digits exist |
| **Maximum** integer digits | `getMaximumIntegerDigits()` | `setMaximumIntegerDigits(int)` | `DecimalFormat` may drop leftmost integer digits if the limit is exceeded |
| **Minimum** fraction digits | `getMinimumFractionDigits()` | `setMinimumFractionDigits(int)` | Pads zeros to the right of the decimal separator if needed |
| **Maximum** fraction digits | `getMaximumFractionDigits()` | `setMaximumFractionDigits(int)` | Rounds the fractional part to this limit |

The two **minimum/maximum** pairs are constraints on **how the output is written**, not on the data type or precision stored in the variable. These methods belong to `NumberFormat`; `DecimalFormat` is a common subclass that implements them.

## 2. Configuring a NumberFormat: Complete Example

Create the file **`DigitBoundsDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class DigitBoundsDemo {
    public static void main(String[] args) {
        NumberFormat number =
                NumberFormat.getNumberInstance(Locale.US);

        number.setGroupingUsed(false);
        number.setMinimumIntegerDigits(5);
        number.setMinimumFractionDigits(2);
        number.setMaximumFractionDigits(3);
        number.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println(number.format(new BigDecimal("12")));
        System.out.println(number.format(new BigDecimal("12.5")));
        System.out.println(number.format(new BigDecimal("12.3456")));
        System.out.println(number.format(new BigDecimal("0")));
        System.out.println("minInteger="
                + number.getMinimumIntegerDigits());
        System.out.println("minFraction="
                + number.getMinimumFractionDigits());
        System.out.println("maxFraction="
                + number.getMaximumFractionDigits());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 DigitBoundsDemo.java
java DigitBoundsDemo
```

**Stdout on a JDK providing standard number formatting for `Locale.US`:**

```text
00012.00
00012.50
00012.346
00000.00
minInteger=5
minFraction=2
maxFraction=3
```

Analysis:

1. `12` has two integer digits, so it is padded to `00012`; it has no fractional part, but **minimum fraction = 2** forces `.00`.
2. `12.5` becomes `00012.50`: pads one zero at the end of the fractional part, and does **not** turn the number into `1250`.
3. `12.3456` has four fractional digits and **maximum fraction = 3**, so it rounds to `12.346` under `HALF_UP`; the integer part is still padded to five digits.
4. `0` has a one-digit integer part, so it is padded to `00000`; minimum fraction displays `.00`.
5. `setGroupingUsed(false)` turns off thousands grouping so the leading zeros are easy to inspect; it is **unrelated** to the rounding mechanism.

The example uses `new BigDecimal("12.3456")` to represent the input decimal value accurately, avoiding noise from binary floating-point `double` while learning rounding rules.

## 3. Minimum Integer Digits: Zero-Padding, Not Rounding

When calling `setMinimumIntegerDigits(4)`, an integer like `7` can display as `0007`. This is useful for **fixed-width display codes**, such as sequence number `0007`, though important identifiers should generally be stored as a **String** if leading zeros must be preserved.

With `DecimalFormat`, a similar effect can be achieved using a pattern:

```java
DecimalFormat format = new DecimalFormat(
        "0000", DecimalFormatSymbols.getInstance(Locale.US));
System.out.println(format.format(7));    // 0007
System.out.println(format.format(1234)); // 1234
```

This is a **fragment** requiring `import java.text.DecimalFormat;`, `DecimalFormatSymbols;`, and `java.util.Locale;`. Each `0` character in the integer portion of the pattern denotes a **required** digit to display. `setMinimumIntegerDigits(4)` has a similar effect on minimum digit count, while a pattern also controls symbol structure, grouping, and fractional digits.

**Do not confuse with value normalization:** `format.format(7)` returns the string `"0007"`; the argument `7` is still the number seven. Converting `"0007"` back to a number can strip leading zeros. Therefore, do not use number formatting to store **postal codes, customer IDs, or product codes** that have leading zeros.

## 4. Maximum Integer Digits: Risk of Dropping High-Order Digits

This is the **easiest place to lose data at the presentation layer**. With `DecimalFormat`, if the maximum integer digit limit is lower than the actual digit count, the formatter **drops leftmost digits** to satisfy the limit; it neither switches to scientific notation nor rounds the number to one with fewer digits.

**File `MaximumIntegerDigitsDemo.java`:**

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class MaximumIntegerDigitsDemo {
    public static void main(String[] args) {
        DecimalFormat number = new DecimalFormat(
                "0", DecimalFormatSymbols.getInstance(Locale.US));

        number.setGroupingUsed(false);
        System.out.println("Default: " + number.format(12345));

        number.setMaximumIntegerDigits(3);
        System.out.println("Max 3: " + number.format(12345));
        System.out.println("Short: " + number.format(99));
        System.out.println("Max digits: "
                + number.getMaximumIntegerDigits());
    }
}
```

```bash
javac -encoding UTF-8 MaximumIntegerDigitsDemo.java
java MaximumIntegerDigitsDemo
```

Stdout:

```text
Default: 12345
Max 3: 345
Short: 99
Max digits: 3
```

**Critically important:** `345` on the second line is **not** a rounded result of `12345`. The high-order digits `12` were **stripped from the display string**. The source number is still `12345`, but someone seeing only the label `345` will completely misread it.

Therefore:

- Never set a small maximum integer digit limit on **monetary amounts, quantities, or measurements** that could exceed the limit.
- If you want a **compact display** for large quantities, choose a transparent product convention such as `"12.3K"`, controlled scientific notation, or an out-of-range error message—never silently chop off high-order digits.
- If you want to restrict **input** to at most N digits, **validate the input value** rather than using `setMaximumIntegerDigits(N)` as a validator. The formatter only governs the output string.
- The integer-digit truncation behavior shown here is specific to `DecimalFormat`; do not generalize that every future subclass of `NumberFormat` follows the exact same rule without checking its documentation.

## 5. Minimum and Maximum Fraction Digits: Zero-Padding or Rounding

These two methods are commonly used together:

```java
number.setMinimumFractionDigits(2);
number.setMaximumFractionDigits(2);
```

This is a **fragment** in a context where `NumberFormat number` already exists. Effect when printing:

| Exact input value | Min fraction = 2, max = 2, HALF_UP, en-US | Reason |
| --- | --- | --- |
| `12` | `12.00` | Pads two zeros |
| `12.5` | `12.50` | Pads one zero |
| `12.34` | `12.34` | Unchanged |
| `12.345` | `12.35` | Third fractional digit rounds up |
| `12.344` | `12.34` | Remainder is not enough to round up |
| `12.999` | `13.00` | Rounding can **carry** into the integer part |

The last row is worth noting: limiting fractional digits can change **even the integer part of the formatted result** when rounding carries to the next unit. That is completely different from dropping high-order digits via `setMaximumIntegerDigits`.

### Why Set Both Min and Max?

- Setting only `maxFractionDigits = 2`: output can be `12`, `12.5`, or `12.35` depending on the value. The goal is **no more than two** fractional digits.
- Setting only `minFractionDigits = 2`: output has at least two fractional digits, yet may have more depending on the formatter's default max.
- Setting **both min = max = 2**: output has **exactly two fractional digits** for normal finite numbers, convenient for price tables or metrics requiring uniform alignment.

`setMinimumFractionDigits(0)` together with `setMaximumFractionDigits(0)` means no digits are displayed after the decimal separator; **the input number is still rounded** according to the active `RoundingMode` before printing. Do not assume `0 fractional digits` means truncating all fractional digits without rounding.

## 6. Rounding Rules: RoundingMode Is an Independent Decision

`NumberFormat.setRoundingMode(RoundingMode)` specifies how to round when digit limits force a shorter representation. Common modes:

| Mode | Meaning when digits must be dropped | Example positive `2.5` to 0 fractional digits |
| --- | --- | --- |
| `UP` | Away from 0 when non-zero discarded fraction exists | `3` |
| `DOWN` | Toward 0 (drops remainder) | `2` |
| `CEILING` | Toward positive infinity | `3` |
| `FLOOR` | Toward negative infinity | `2` |
| `HALF_UP` | Ties round away from 0 | `3` |
| `HALF_DOWN` | Ties round toward 0 | `2` |
| `HALF_EVEN` | Ties round to the even last digit | `2` |
| `UNNECESSARY` | Rounding must not be needed | Throws `ArithmeticException` if exact representation under constraints is impossible |

**Negative numbers reveal the differences:** `-2.5` rounded to 0 digits gives `-2` with `CEILING` but `-3` with `FLOOR`. `HALF_UP` gives `-3`, whereas `HALF_EVEN` picks `-2` because the retained digit is even. Do not interpret `UP` as "increase the number" in all cases: for negative numbers, `UP` moves **away from 0**.

Standard `DecimalFormat` defaults to `RoundingMode.HALF_EVEN`. However, in business code, **setting the mode explicitly** is always better than implicitly relying on a specific formatter's or factory's default.

### Midpoint Comparison Example — Java 17+

Create the file **`FractionRoundingDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class FractionRoundingDemo {
    public static void main(String[] args) {
        DecimalFormat f = new DecimalFormat(
                "0.00", DecimalFormatSymbols.getInstance(Locale.US));

        BigDecimal a = new BigDecimal("2.345");
        BigDecimal b = new BigDecimal("2.355");

        f.setRoundingMode(RoundingMode.HALF_EVEN);
        System.out.println("Even A: " + f.format(a));
        System.out.println("Even B: " + f.format(b));

        f.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("Up A: " + f.format(a));
        System.out.println("Up B: " + f.format(b));
        System.out.println("Up negative: "
                + f.format(new BigDecimal("-2.345")));

        f.setMaximumFractionDigits(0);
        f.setMinimumFractionDigits(0);
        System.out.println("Whole: "
                + f.format(new BigDecimal("2.5")));
    }
}
```

```bash
javac -encoding UTF-8 FractionRoundingDemo.java
java FractionRoundingDemo
```

Stdout:

```text
Even A: 2.34
Even B: 2.36
Up A: 2.35
Up B: 2.36
Up negative: -2.35
Whole: 3
```

**Explanation:**

- With `HALF_EVEN`, `2.345` sits halfway between `2.34` and `2.35`; `2.34` has an even final digit 4, so it is chosen. `2.355` lies between `2.35` and `2.36`, so `2.36` (even 6) is chosen.
- With `HALF_UP`, midpoints round **away from 0**, so `2.345 → 2.35` and `-2.345 → -2.35`.
- When `maxFraction = minFraction = 0`, `2.5` under `HALF_UP` becomes `3`. It is **not** truncated to `2`.
- The `"0.00"` pattern ensures two digits after the decimal point for the earlier lines; the last lines override those limits via setters.

All decimal values needing exactness in the example are constructed from **`String`**, avoiding uncertainty caused by a `double` literal like `2.345` not always having an exact binary representation.

## 7. BigDecimal, double, and Differences Between Numeric Representation and Rounding

### String-Constructed BigDecimal

`new BigDecimal("2.345")` preserves the exact decimal value `2.345`. `BigDecimal.valueOf(2.345)` uses the decimal representation from `Double.toString(...)` when converting from `double`, which is generally more convenient than `new BigDecimal(2.345)` in business code; however, a `double` already computed via binary arithmetic may have accumulated error beforehand.

Calling `new BigDecimal(2.345)` directly from a binary floating-point literal is **not** a reliable way to say "exact 2.345." Binary approximation can lead to surprising rounding outcomes. For money or fixed-decimal quantities, accept input as a **validated decimal string** or use `BigDecimal` throughout the calculation pipeline.

### Round for Calculation or Only for Display?

Compare these two operations:

```java
BigDecimal raw = new BigDecimal("12.345");
BigDecimal calculated =
        raw.setScale(2, RoundingMode.HALF_UP);

String presented = format.format(raw);
```

This is a **fragment** with `import java.math.BigDecimal` and `RoundingMode`, where `format` is a previously declared formatter. `calculated` is **a new `BigDecimal` value** equal to `12.35`, while `raw` remains `12.345`; `presented` is only a display string, which may be `"12.35"` if the formatter uses two fractional digits and `HALF_UP`.

**Design boundary:** if business rules require a number to be finalized at two decimal places (e.g., a rounded invoice total), perform the business rounding via `BigDecimal.setScale(...)` or calculations with an explicit `MathContext`/policy, **then** format for display. Never format to a string and parse back to perform a business rounding step: separators, locale, and rounding can cause information loss.

### What Is `double` Still Suitable For?

`double` suits many scientific/engineering computations that tolerate controlled floating-point error. When using `NumberFormat`, remember the formatter only rounds the **already computed binary value** according to its rules—it does not synthesize decimal precision that did not exist in the input.

## 8. Interaction Between min/max Setters

All four bounds are non-negative. `NumberFormat` maintains valid bound pairs: **minimum must not exceed maximum** in the resulting state. If a setter asks for a minimum larger than the current maximum, the implementation adjusts the other bound to satisfy the invariant; if setting maximum lower than minimum, minimum may be lowered accordingly.

Therefore, **setter call order matters** when the final values of a pair conflict. Configure them intentionally, and verify with getters if the invariant is critical.

**Standalone runnable example — `DigitLimitsOrderDemo.java`:**

```java
import java.text.NumberFormat;
import java.util.Locale;

public class DigitLimitsOrderDemo {
    public static void main(String[] args) {
        NumberFormat f = NumberFormat.getNumberInstance(Locale.US);

        f.setMinimumFractionDigits(4);
        f.setMaximumFractionDigits(2);
        System.out.println("Case A min="
                + f.getMinimumFractionDigits()
                + ", max=" + f.getMaximumFractionDigits());

        f.setMaximumFractionDigits(2);
        f.setMinimumFractionDigits(4);
        System.out.println("Case B min="
                + f.getMinimumFractionDigits()
                + ", max=" + f.getMaximumFractionDigits());
    }
}
```

```bash
javac -encoding UTF-8 DigitLimitsOrderDemo.java
java DigitLimitsOrderDemo
```

Stdout with standard `DecimalFormat` implementation for `Locale.US`:

```text
Case A min=2, max=2
Case B min=4, max=4
```

If the exact goal is two fractional digits, call `setMinimumFractionDigits(2)` and `setMaximumFractionDigits(2)`; if you set conflicting values in sequence expecting the implementation to ignore the conflicting call, you can end up with an unintended digit width.

### Can You Set maximumIntegerDigits(0)?

Digit bounds accept non-negative values, yet some formatters/patterns have special rules for minimum digits (such as before the decimal mark). Do not design a UI assuming every boundary value of `0` for the integer part behaves uniformly across all formatters/providers. For practical numbers, keeping at least one integer digit is the clearest choice; if a special representation like `.75` is required, test the pattern and output explicitly.

## 9. DecimalFormat Patterns: `0`, `#`, and the Decimal Separator

`DecimalFormat` lets you express bounds via a pattern:

| Pattern (`en-US` style) | Value `12.5` | Meaning |
| --- | --- | --- |
| `"0"` | `12` (with `HALF_EVEN`; `HALF_UP` gives `13`) | Rounds midpoint according to chosen mode |
| `"0.00"` | `12.50` | Exactly two fractional digits |
| `"0000.00"` | `0012.50` | Minimum four integer digits, two fractional digits |
| `"#,##0.##"` | `12.5` | Grouping for large enough numbers; up to two fractional digits |
| `"0.000"` | `12.500` | Exactly three fractional digits |

**Exact note on the first row:** when `RoundingMode.HALF_EVEN` is used, `12.5` formatted with `"0"` yields `12` (12 is an even integer). If `HALF_UP` is used, the result is `13`. To avoid misinterpretation, **do not rely on the pattern to determine the rounding mode**; the pattern only controls digit positions/widths, while the mode must be set per policy. The other examples in the table do not hit a rounding midpoint.

- `0` in the integer/fraction part is a **required** digit.
- `#` is an **optional** digit position; unneeded zeros may be omitted.
- `.` and `,` in a pattern are not necessarily printed literally: `DecimalFormatSymbols`/locale determines the decimal and grouping separators.
- Patterns can include currency symbols, percent signs, scientific exponents, and prefixes/suffixes. Do not treat arbitrary `0` or `#` tokens inside random business strings as valid `DecimalFormat` patterns.

For examples requiring deterministic stdout, pass `DecimalFormatSymbols.getInstance(Locale.US)` or set an explicit formatting locale to prevent other machines from producing different separator strings.

## 10. Changing Locale: Different Separators, Same Digit Bounds

`setMinimumFractionDigits(2)` / `setMaximumFractionDigits(2)` define the width of the fractional part; **locale** determines the decimal separator, grouping separator, and sometimes the digits used for display.

**File `LocaleDigitsDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleDigitsDemo {
    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234.5");

        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

        for (NumberFormat formatter : new NumberFormat[] {us, de}) {
            formatter.setMinimumFractionDigits(2);
            formatter.setMaximumFractionDigits(2);
            formatter.setRoundingMode(RoundingMode.HALF_UP);
        }

        System.out.println("US: " + us.format(value));
        System.out.println("DE: " + de.format(value));
    }
}
```

```bash
javac -encoding UTF-8 LocaleDigitsDemo.java
java LocaleDigitsDemo
```

Typical output on a JDK with corresponding locale data:

```text
US: 1,234.50
DE: 1.234,50
```

Both formatters keep the same number of fractional digits while using different local symbols. Output for a specific locale can be influenced by the JDK's locale data source and provider configuration; if writing exact string comparison tests, control the runtime and use sufficiently specific locales.

In a multi-user server, use `NumberFormat.getNumberInstance(userFormatLocale)` per request or render operation. Never call `Locale.setDefault(...)` per request, as that is a JVM-wide change that can cause threads to interfere with one another.

## 11. Currency, Percentages, Scientific Notation, and Digit Bounds

Not every `NumberFormat` variant has "general number" semantics:

### Currency

`NumberFormat.getCurrencyInstance(locale)` returns a formatter configured for regional currency presentation. Default fractional digits may reflect currency conventions; **do not assume every currency has two fractional digits** (for example, currencies with 0 or 3 decimal places). `Locale` is display context, **not proof of transaction currency**.

When formatting a payment, the application must know the actual currency code such as `VND`, `USD`, or `JPY`, selecting it from business data along with its dedicated rounding rules and fractional policy. `setCurrency(Currency.getInstance(...))` updates the currency unit on a compatible formatter, but does not replace controlling **scale, rounding, and monetary semantics** of the transaction.

### Percentages

`NumberFormat.getPercentInstance(locale)` typically **multiplies the value by 100 when presenting** and appends a percent sign. For example, a ratio of `0.125` can display as `12.5%` if fractional digits allow. Fraction digit bounds on the formatter apply to the **scaled percentage representation**, not directly to the raw initial decimal. Thus, limiting fractional digits on percentages vs. general numbers yields different results.

### Scientific Notation and Other Formats

`DecimalFormat` supports patterns for exponential notation. Integer digit limits in a scientific pattern affect both mantissa and exponent layout; you cannot simply infer that it always truncates digits like the general decimal example. If scientific notation is needed, define a pattern and test specifically against large and small inputs rather than using `setMaximumIntegerDigits(3)` hoping to automatically achieve `1.23E4`.

## 12. Formatting Differs from Parsing and Validation

`NumberFormat` can both **format** and **parse**, yet digit limits primarily describe the **output string**. Do not assume format limits enforce length checks or automatic rounding on input strings.

**Java 17+ Example — `FormattingVsParsingDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.util.Locale;

public class FormattingVsParsingDemo {
    public static void main(String[] args) throws ParseException {
        DecimalFormat f = new DecimalFormat(
                "0.00", DecimalFormatSymbols.getInstance(Locale.US));
        f.setRoundingMode(RoundingMode.HALF_UP);
        f.setParseBigDecimal(true);

        BigDecimal value =
                (BigDecimal) f.parse("123.456");
        String shown = f.format(value);

        System.out.println("Parsed: " + value.toPlainString());
        System.out.println("Formatted: " + shown);
        System.out.println("Still: " + value.toPlainString());
    }
}
```

```bash
javac -encoding UTF-8 FormattingVsParsingDemo.java
java FormattingVsParsingDemo
```

Stdout:

```text
Parsed: 123.456
Formatted: 123.46
Still: 123.456
```

`setParseBigDecimal(true)` is a `DecimalFormat`-specific method; it parses into a `BigDecimal` when appropriate instead of returning a `Long`/`Double`. `setMaximumFractionDigits(2)` does not reject `"123.456"` or pre-round it when parsing into a value. After formatting, `value` still has three fractional digits.

If you need to **enforce at most two fractional digits on input**, use syntax checks and `BigDecimal.scale()` (accounting for trailing zeros/normalization if policy requires), or context-specific validation. To ensure the entire input is parsed, use `ParsePosition` or check for leftover characters; `DecimalFormat.parse` can accept a valid prefix without requiring full consumption. If you need to round values for business logic, do it in the calculation layer with `BigDecimal.setScale(...)`.

## 13. RoundingMode.UNNECESSARY and Detecting Precision Loss

Sometimes rounding is **forbidden**—for example, a processing step must prove that the original value can be represented exactly within the requested digit count. `RoundingMode.UNNECESSARY` throws `ArithmeticException` whenever a non-zero digit would have to be dropped.

**File `UnnecessaryRoundingDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class UnnecessaryRoundingDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "0.00", DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setRoundingMode(RoundingMode.UNNECESSARY);

        System.out.println(formatter.format(
                new BigDecimal("7.500")));

        try {
            System.out.println(formatter.format(
                    new BigDecimal("7.501")));
        } catch (ArithmeticException exception) {
            System.out.println("Rounding would be required");
        }
    }
}
```

```bash
javac -encoding UTF-8 UnnecessaryRoundingDemo.java
java UnnecessaryRoundingDemo
```

Stdout:

```text
7.50
Rounding would be required
```

`7.500` can be represented as `7.50` without losing significant digits; `7.501` cannot be reduced to two fractional digits exactly. This rule helps detect data that requires business handling before presentation.

Do not use `UNNECESSARY` as a substitute for comprehensive validation: integer length limits, data type, range, currency, and input syntax must still be checked independently. `UNNECESSARY` specifically concerns **whether arithmetic rounding would occur** during formatting.

## 14. Common Mistakes and How to Avoid Them

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Setting only minimum fraction = 2 expecting always two fractional digits | Maximum may allow more | Set min = max = 2 if exactly two digits are needed |
| Setting maximum fraction = 2 expecting always two fractional digits | The number `12` may display as `12` | Also set minimum fraction = 2 |
| Thinking maximum fraction truncates without rounding | The formatter applies `RoundingMode` | Choose an explicit mode and test midpoint cases |
| Thinking max integer = 3 turns `12345` into `12300` | `DecimalFormat` can drop leading digits and print `345` | Never cap max integer on numbers needing full display |
| Treating `RoundingMode.UP` as "round toward +∞" | For negative numbers, `UP` goes **away from 0** | Use `CEILING` if you want toward +∞ |
| Assuming the default rounding always fits business rules | `HALF_EVEN` differs from `HALF_UP` at exact midpoints | Choose according to business rules |
| Using `double` literals expecting exact decimal values | Binary floating-point can approximate | Use `BigDecimal(String)` when exact decimals are required |
| Using formatted strings in calculations | Strings contain separators and may lose precision | Compute on numeric values; format at the presentation layer |
| Believing `setMaximumFractionDigits(2)` validates input | Format limits do not reject long input/parses | Validate scale, syntax, and range separately |
| Setting conflicting minimum/maximum without checking | Setters may adjust the paired property | Apply final configuration deliberately and inspect getters |
| Sharing a single formatter across all threads | `NumberFormat`/`DecimalFormat` are mutable and not thread-safe | Create per context/request or synchronize properly |
| Taking locale from the server default for every user | Separators/grouping may be wrong for the viewer | Pass `Locale` explicitly |
| Confusing currency with locale | Display locale does not dictate transaction currency | Manage currency code and business rounding separately |
| Testing exact string matching across all JDKs/providers without pinning config | Locale data may differ | Use explicit locale, control runtime, and assert appropriate expectations |

## 15. Practice Exercises

### Exercise 1 — Choosing the Right Bounds

Create a `Locale.US` formatter, disable grouping, set **minimum integer = 4**, **minimum fraction = 2**, **maximum fraction = 2**, **HALF_UP**. Predict and run with `7`, `7.5`, `7.555`, `0.004`, `9.999` using `BigDecimal(String)`.

Goal: observe both kinds of zero-padding and the **carry** into the integer part upon rounding. Try changing maxFraction to 3 and compare.

### Exercise 2 — Avoiding Dangerous Maximum Integer Limits

Format `987654` with `DecimalFormat("0")`, then call `setMaximumIntegerDigits(3)`. Inspect what remains displayed; explain why a payment API **must never** rely on such formatting to represent monetary amounts. Find a solution that displays the full value or reports an out-of-range error.

### Exercise 3 — HALF_EVEN and HALF_UP

With `new BigDecimal("2.345")` and `new BigDecimal("2.355")`, format to two fractional digits. Compare both modes and explain `HALF_EVEN`'s "ties to even digit" rule. Repeat with negative numbers to distinguish `HALF_UP` from `CEILING`.

### Exercise 4 — Asymmetric Parsing and Formatting

Use `DecimalFormat("0.00")` and `setParseBigDecimal(true)` to parse `"123.456"`. Format the resulting value and then print `toPlainString()` of the original value. Explain why the display string has two fractional digits while the `BigDecimal` itself still has three.

### Exercise 5 — Locale and Width

With the same `BigDecimal("1234.5")`, test `en-US`, `de-DE`, and `vi-VN` while keeping min/max fraction = 2. Note the differences in decimal/grouping separators, without concluding that changing separators changes the **numeric value**.

## 16. Official Documentation

- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): `setMinimumIntegerDigits`, `setMaximumIntegerDigits`, `setMinimumFractionDigits`, `setMaximumFractionDigits`, `setRoundingMode`.
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): patterns, required/optional digits, grouping, integer limits, and rounding behavior.
- [Java SE 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): exact definitions of rounding rules.
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): `setScale`, decimal arithmetic, and precision management.
- [Java SE 21 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormatSymbols.html): locale-dependent symbols.

## 17. Key Takeaways

**Minimum integer/fraction digits** set the **minimum** display width, typically padding with zeros. **Maximum fraction digits** cap digits after the decimal separator and can trigger **rounding** under `RoundingMode`. **Maximum integer digits** in `DecimalFormat` is not a safe compaction mechanism for large numbers: it can **drop leading digits**, rendering the label misleading.

Choose an explicit `Locale`, configure min/max and `RoundingMode` intentionally, use `BigDecimal` for decimals needing exactness, separate **business rounding** from **display rounding**, and test boundary cases such as `2.345`, `12.999`, negative numbers, and multi-digit integers.