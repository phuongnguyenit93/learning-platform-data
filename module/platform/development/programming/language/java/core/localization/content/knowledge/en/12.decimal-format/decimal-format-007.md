# DecimalFormat: RoundingMode and Digit Count Control in Java

## 1. Goal: numbers that satisfy both rounding rules and display format

When localizing numbers in Java, selecting the decimal and grouping separators by `Locale` alone is not enough. An application may need to display `1234.5` as `1,234.50`, round `2.345` to two decimal places, or keep at most three digits after the decimal separator without adding unnecessary zeros.

Two key configuration groups on `java.text.DecimalFormat` are:

- **Rounding policy**, controlled via `setRoundingMode(java.math.RoundingMode)`. It decides the outcome when the full remainder cannot be represented within the requested display precision.
- **Minimum/maximum digit counts**, controlled via `setMinimumFractionDigits`, `setMaximumFractionDigits`, `setMinimumIntegerDigits`, `setMaximumIntegerDigits`, or the pattern. They determine the length/precision of the resulting string.

These are **two distinct responsibilities**. Configuring "two decimal digits" determines *where to round*; `RoundingMode` determines *which direction to round* at that position.

Examples with `Locale.US` and two digits after the decimal separator:

| Original value | Mode | Displayed string |
|---:|---|---|
| `2.345` | `HALF_UP` | `2.35` |
| `2.345` | `HALF_EVEN` | `2.34` |
| `2.345` | `DOWN` | `2.34` |
| `-2.345` | `CEILING` | `-2.34` |
| `-2.345` | `FLOOR` | `-2.35` |

This lesson uses **Java 17+**, distinguishes the rounding modes, integer/fractional digit bounds, patterns, precision pitfalls, and monetary handling principles. For consistent experimental results, examples pass `BigDecimal` values constructed from **decimal strings** and format using `DecimalFormatSymbols` for `Locale.US`.

## 2. Initializing DecimalFormat with the right Locale

An explicit approach:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

DecimalFormat formatter = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
```

This is a **code snippet** meant to go inside a Java class/method; complete runnable programs appear in later sections.

`#,##0.00` is a **non-localized pattern**, in which:

- `0` is a required digit: if a digit is missing at that position, a zero can be padded when displaying.
- `#` is an optional digit: padding zeros at these positions is not forced.
- `,` in the pattern represents the **grouping separator** in pattern syntax, not necessarily a literal comma on screen.
- `.` in the pattern represents the **decimal separator** in pattern syntax, not necessarily a literal period on screen.

`DecimalFormatSymbols.getInstance(Locale.US)` specifies the corresponding display symbols. Under `Locale.GERMANY`, the decimal/grouping symbols differ; never hardcode `.` and `,` into application output and call it localization.

You can obtain a formatter via:

```java
DecimalFormat formatter =
        (DecimalFormat) java.text.NumberFormat.getNumberInstance(Locale.US);
```

However, formatters from `NumberFormat.get...Instance` can depend on the locale data provider and configuration; a cast like the above is not guaranteed across all implementations. When you need `DecimalFormat`-specific APIs and application-owned patterns, instantiating `new DecimalFormat(pattern, symbols)` directly keeps the examples transparent.

## 3. Four main digit limits

`DecimalFormat` inherits four getter/setter pairs from `NumberFormat`:

| Method | Effect |
|---|---|
| `setMinimumFractionDigits(n)` | At least `n` digits after the decimal separator; may pad zeros |
| `setMaximumFractionDigits(n)` | At most `n` digits after the decimal separator; may require rounding |
| `setMinimumIntegerDigits(n)` | At least `n` integer digits; may pad leading zeros |
| `setMaximumIntegerDigits(n)` | Caps integer digits the formatter is allowed to display; **can drop leftmost digits** |

The corresponding getters are `getMinimumFractionDigits()`, `getMaximumFractionDigits()`, `getMinimumIntegerDigits()`, and `getMaximumIntegerDigits()`.

### How to interpret minimum and maximum fraction digits

Example:

```java
DecimalFormat optional = new DecimalFormat(
        "0.##", DecimalFormatSymbols.getInstance(Locale.US));
```

When formatting `BigDecimal("12")`, `BigDecimal("12.3")`, and `BigDecimal("12.345")`:

```text
12
12.3
12.34
```

- `0.##` has **minimum 0** and **maximum 2** fractional digits.
- When there are no fractional digits to show, the decimal separator need not appear either.
- For `12.345` with the default `HALF_EVEN` rounding mode, the two-digit result is `12.34`; this outcome depends on both value and mode.

Conversely, the pattern `0.00` specifies **minimum 2** and **maximum 2**, so `12` becomes `12.00`. Trailing zeros are a **display** requirement, not proof that the underlying measurement is accurate to two decimal places.

### Setters automatically keep minimum from exceeding maximum

When setting a new limit creates a min/max conflict, Java can adjust the other bound. For instance, starting from `#,##0.00`:

- `setMinimumFractionDigits(0)` → min 0, max 2.
- `setMaximumFractionDigits(0)` → min 0, max 0.
- `setMaximumFractionDigits(3)` → min 0, max 3.
- `setMinimumFractionDigits(4)` → min 4, max also becomes 4.

Therefore, **the order of setter calls affects the final configuration**. Never simply assume the formatter kept its old maximum after increasing the minimum. After dynamic configuration changes, inspect getters or write tests to verify.

## 4. The eight java.math.RoundingMode modes

`DecimalFormat.setRoundingMode(...)` accepts the `java.math.RoundingMode` enum, with the same mode names used in `BigDecimal`.

| Mode | Rule when discarding remainder | For `2.345`, keep 2 digits | For `-2.345`, keep 2 digits |
|---|---|---|---|
| `UP` | Away from 0 | `2.35` | `-2.35` |
| `DOWN` | Toward 0 | `2.34` | `-2.34` |
| `CEILING` | Toward positive infinity | `2.35` | `-2.34` |
| `FLOOR` | Toward negative infinity | `2.34` | `-2.35` |
| `HALF_UP` | Nearest; exact half goes away from 0 | `2.35` | `-2.35` |
| `HALF_DOWN` | Nearest; exact half goes toward 0 | `2.34` | `-2.34` |
| `HALF_EVEN` | Nearest; exact half picks even last digit | `2.34` | `-2.34` |
| `UNNECESSARY` | Forbids rounding if significant digits must be dropped | Throws `ArithmeticException` | Throws `ArithmeticException` |

**Most common confusion:** `CEILING`/`FLOOR` depend on the **number line**, whereas `UP`/`DOWN` depend on **distance from 0**. They coincide only in some cases. For negative numbers, `CEILING` moves toward 0, while `FLOOR` moves toward larger negative magnitude.

The three `HALF_*` modes differ only when the value being rounded sits at the exact **midpoint** between two representable results. Whenever it is closer to one result, all three pick the closer one.

### HALF_EVEN: rounding toward the even digit at the retained position

Keeping two digits after the decimal point:

- `2.345` sits halfway between `2.34` and `2.35`: `HALF_EVEN` chooses `2.34`, because the last retained digit is **4** (even).
- `2.355` sits halfway between `2.35` and `2.36`: `HALF_EVEN` chooses `2.36`, because the last retained digit is **6** (even).
- `HALF_UP` chooses `2.35` and `2.36`, respectively.

`HALF_EVEN` is often called *banker's rounding* and can reduce statistical bias over many rounding operations. Yet specific monetary rules must be defined by product/regulation; never assume banks or every country use a single mode.

## 5. Java 17+ program: verifying every RoundingMode

Save to `RoundingModesDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingModesDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        BigDecimal positive = new BigDecimal("2.345");
        BigDecimal negative = new BigDecimal("-2.345");

        for (RoundingMode mode : RoundingMode.values()) {
            formatter.setRoundingMode(mode);
            try {
                System.out.printf(
                        "%s: %s | %s%n",
                        mode,
                        formatter.format(positive),
                        formatter.format(negative));
            } catch (ArithmeticException exception) {
                System.out.println(mode + ": ArithmeticException");
            }
        }
    }
}
```

Compile/run:

```bash
javac RoundingModesDemo.java
java RoundingModesDemo
```

Verified output on the JDK:

```text
UP: 2.35 | -2.35
DOWN: 2.34 | -2.34
CEILING: 2.35 | -2.34
FLOOR: 2.34 | -2.35
HALF_UP: 2.35 | -2.35
HALF_DOWN: 2.34 | -2.34
HALF_EVEN: 2.34 | -2.34
UNNECESSARY: ArithmeticException
```

Here `new BigDecimal("2.345")` represents the exact decimal value under test, so exact midpoint cases reproduce cleanly. Passing a `double` produced by arithmetic or a literal directly may yield different results due to **binary representation**; see section 9.

`UNNECESSARY` does not mean "do not print digits after the decimal point." It means **no rounding that loses information may occur**. For instance, formatting `2.340` to two decimal places drops a trailing zero without altering numeric value and can succeed; for `2.345`, dropping the digit 5 cannot preserve the value, so an error is thrown.

## 6. Java 17+ program: min/max fraction and zero padding

Save to `DigitLimitsDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DigitLimitsDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        BigDecimal value = new BigDecimal("1234.5");

        System.out.printf(
                "initial min=%d max=%d text=%s%n",
                formatter.getMinimumFractionDigits(),
                formatter.getMaximumFractionDigits(),
                formatter.format(value));

        formatter.setMinimumFractionDigits(0);
        System.out.printf(
                "min0 min=%d max=%d text=%s%n",
                formatter.getMinimumFractionDigits(),
                formatter.getMaximumFractionDigits(),
                formatter.format(value));

        formatter.setMaximumFractionDigits(0);
        System.out.printf(
                "max0 min=%d max=%d text=%s%n",
                formatter.getMinimumFractionDigits(),
                formatter.getMaximumFractionDigits(),
                formatter.format(value));

        formatter.setMaximumFractionDigits(3);
        System.out.printf(
                "max3 min=%d max=%d text=%s%n",
                formatter.getMinimumFractionDigits(),
                formatter.getMaximumFractionDigits(),
                formatter.format(value));

        formatter.setMinimumFractionDigits(4);
        System.out.printf(
                "min4 min=%d max=%d text=%s%n",
                formatter.getMinimumFractionDigits(),
                formatter.getMaximumFractionDigits(),
                formatter.format(value));
    }
}
```

Run:

```bash
javac DigitLimitsDemo.java
java DigitLimitsDemo
```

Output:

```text
initial min=2 max=2 text=1,234.50
min0 min=0 max=2 text=1,234.5
max0 min=0 max=0 text=1,234
max3 min=0 max=3 text=1,234.5
min4 min=4 max=4 text=1,234.5000
```

Meaningful transitions:

1. **Initial:** pattern `#,##0.00` forces two fractional digits: `1,234.50`.
2. **Min = 0:** no trailing `0` padding needed; `1234.5` becomes `1,234.5`, even though max still permits 2 digits.
3. **Max = 0:** drops fractional part; the default mode in the example is `HALF_EVEN`. `1234.5` lies halfway between 1234 and 1235, so **1234** (even) is chosen.
4. **Max = 3:** the formatter is allowed to show up to 3 fractional digits without forcing zero padding.
5. **Min = 4:** Java raises max to 4 to avoid conflict; the string is padded to `1,234.5000`.

Do not treat the number of printed fractional digits as the precision of the **in-memory value**; it is a presentation choice. Keep this especially in mind when rounding monetary amounts or measurements.

## 7. Controlling the integer part: minimum and maximum mean different things

For the integer part, `setMinimumIntegerDigits(n)` is commonly used to **add zero padding**:

```java
DecimalFormat code = new DecimalFormat(
        "0000", DecimalFormatSymbols.getInstance(Locale.US));
System.out.println(code.format(42));
```

The output is `0042`. This is a valid display style for a numeric code or sequence number, but **you should not use DecimalFormat as a general identifier formatter** if the code contains letters, hyphens, or must preserve the exact input string.

`setMaximumIntegerDigits(n)` is different and more dangerous: with `DecimalFormat`, it can **truncate leftmost digits** when the integer part is too long.

Snippet example:

```java
DecimalFormat limited = new DecimalFormat(
        "0000", DecimalFormatSymbols.getInstance(Locale.US));
limited.setMaximumIntegerDigits(3);

System.out.println(limited.format(12345));
```

With this configuration, the verified output is:

```text
345
```

Because `setMaximumIntegerDigits(3)` sets maximum to 3 and can adjust minimum down to 3, `12345` loses its two most significant digits on the left. Never use maximum integer digits to **validate numeric magnitude** or mask part of a number while expecting the output to retain the value. If the data domain permits at most three digits, validate the value before formatting and report an error if out of range.

When you want to control the **total number of significant digits** rather than integer/fractional digit counts, design a different rule (such as working with `BigDecimal` using `MathContext`) instead of assuming `setMaximumIntegerDigits` is a "significant digits limit."

## 8. Pattern vs. setters: which takes precedence?

`DecimalFormat` takes its initial min/max digit limits from the pattern. For example:

| Pattern | Minimum fraction | Maximum fraction | Example value `12` |
|---|---:|---:|---|
| `0` | 0 | 0 | `12` |
| `0.0` | 1 | 1 | `12.0` |
| `0.00` | 2 | 2 | `12.00` |
| `0.##` | 0 | 2 | `12` |
| `#,##0.000` | 3 | 3 | `12.000` |

After applying a pattern, you can change the limits with setters. However, calling `applyPattern(...)` **afterward** can reset the limits to match the new pattern.

Example:

```java
DecimalFormat df = new DecimalFormat(
        "0.00", DecimalFormatSymbols.getInstance(Locale.US));
df.setMaximumFractionDigits(0);
df.applyPattern("0.000");

System.out.println(df.getMinimumFractionDigits());
System.out.println(df.getMaximumFractionDigits());
```

Output:

```text
3
3
```

Because `applyPattern("0.000")` updated min/max to match the new pattern. If you need both a pattern and setter overrides, **apply the pattern first and configure min/max and rounding mode afterward**. Check getters in tests to catch wrong ordering during refactoring.

Patterns containing percent (`%`), currency (`¤`), scientific (`E`), or special numeric patterns can change how digit counts are interpreted. This lesson focuses on ordinary decimal patterns like `#,##0.00`; do not extrapolate all scientific-formatting rules solely from basic decimal examples.

## 9. double, BigDecimal, and "unexpected rounding"

`double` uses binary representation and cannot store every decimal fraction accurately. In some cases, a value near `2.675` is slightly **less than** the true midpoint; to two decimal places, the result can be `2.67` instead of `2.68`.

Standalone Java 17+ example, saved as `DecimalPrecisionDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalPrecisionDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setRoundingMode(RoundingMode.HALF_EVEN);

        double primitive = 2.675;
        BigDecimal exact = new BigDecimal("2.675");
        BigDecimal fromDouble = new BigDecimal(primitive);

        System.out.println("double=" + formatter.format(primitive));
        System.out.println("stringBD=" + formatter.format(exact));
        System.out.println("newBDdouble=" + formatter.format(fromDouble));
    }
}
```

Run:

```bash
javac DecimalPrecisionDemo.java
java DecimalPrecisionDemo
```

Verified output:

```text
double=2.67
stringBD=2.68
newBDdouble=2.67
```

Explanation:

- `double` does not represent decimal `2.675` accurately; rounding depends on the actual binary value received.
- `new BigDecimal("2.675")` represents the exact decimal as written.
- `new BigDecimal(primitive)` reflects the exact approximated `double` value and does not automatically fix it to the intended decimal.
- `BigDecimal.valueOf(primitive)` uses the decimal string from `Double.toString`, making it better suited than `new BigDecimal(double)` when converting an existing `double` to a human-expected decimal. However, if precision was already lost in earlier calculations, `valueOf` cannot recover data that no longer exists.

If business data originates from a decimal string such as an input amount or database field, parse/store it as `BigDecimal` from the start instead of detouring through `double`. Never write tie-case rounding tests using `double` literals and conclude that the format method broke `HALF_EVEN`.

## 10. Rounding during formatting vs. changing the value

`DecimalFormat.format(number)` creates a **display string**. It does not modify the `BigDecimal` or `double` passed in.

```java
BigDecimal value = new BigDecimal("12.345");
DecimalFormat formatter = new DecimalFormat(
        "0.00", DecimalFormatSymbols.getInstance(Locale.US));
formatter.setRoundingMode(RoundingMode.HALF_UP);

String text = formatter.format(value);
// text = "12.35"
// value still equals 12.345
```

This is an illustrative code snippet inside a method with appropriate imports. If you need a **quantized numeric value** to two decimal places for storage or further math, make the rule explicit via:

```java
BigDecimal rounded = value.setScale(2, RoundingMode.HALF_UP);
```

The result `rounded` is a new `BigDecimal` with scale 2. `BigDecimal` is immutable; `setScale` does not mutate the original `value`.

**Never** take a locale-formatted string and pass it directly to `new BigDecimal(text)`. For instance, `"1,234.50"` is US display output with a grouping comma, not the standard decimal syntax that the constructor accepts; in another locale, a comma may be the decimal separator. Keep separate:

1. **Storage/computation:** choose exact numeric types and rounding rules, usually `BigDecimal` for money.
2. **User presentation:** use `DecimalFormat` with `Locale`, digit bounds, and the appropriate mode.
3. **Parsing localized input:** use a properly configured parser and verify full string consumption; do not conflate display parsing with machine-format parsing.

Do not take a value rounded for display and feed it back as the basis for financial calculations, as this can introduce cumulative drift.

## 11. Choosing digit counts for currency, ratios, and measurements

### Currency

A practical approach is using `NumberFormat.getCurrencyInstance(locale)` and setting the appropriate `Currency`. Default fractional digits can follow the currency; for example, different currencies commonly have 0, 2, or 3 decimal places.

However, **do not assume every currency workflow has exactly two digits** or that cash-rounding rules are solved solely by `setRoundingMode`. Some monetary amounts must be rounded to a multiple (such as the smallest payable cash denomination), not merely a number of decimal places. Those cases require business quantization by step/multiple before display.

If you must use `DecimalFormat` for currency, ensure the currency symbol, digit counts, and rounding mode comply with policy; test with every supported currency.

### Percentages

`NumberFormat.getPercentInstance(locale)` / `DecimalFormat` can multiply the input value by 100 on display. For example, a ratio `0.125` can be rendered as `12.5%` when one fractional digit is allowed. Because multiplication and display digit counts are separate concepts, do not equate `setMaximumFractionDigits(1)` with rounding the raw ratio to 1 decimal place.

### Continuous measurements

For temperature, length, velocity, or sensor readings, maximum fractional digits can depend on measurement source accuracy. `setMinimumFractionDigits` keeps UI columns consistent; `setMaximumFractionDigits` and `RoundingMode` govern presentation rounding. Do not use printed digits to imply reliability or measurement precision beyond what the data source actually supports.

## 12. UNNECESSARY: detecting disallowed rounding

`RoundingMode.UNNECESSARY` is especially useful when an application **requires values to already fit the specified precision** and refuses to discard significant digits.

Example:

```java
DecimalFormat strict = new DecimalFormat(
        "0.00", DecimalFormatSymbols.getInstance(Locale.US));
strict.setRoundingMode(RoundingMode.UNNECESSARY);

System.out.println(strict.format(new BigDecimal("12.30")));
// 12.30
System.out.println(strict.format(new BigDecimal("12.345")));
// Throws ArithmeticException because rounding is required
```

Here `12.30` already fits two decimal digits, whereas `12.345` cannot preserve its value when printing only two decimal digits.

Catch the exception appropriately when data is untrusted or flows through multiple pipelines. `UNNECESSARY` does not mean "truncate remainder without rounding" — that is closer to `DOWN`, and `DOWN` can still lose value.

In monetary processors or payload validators, a cleaner design is checking scale via `BigDecimal.setScale(expectedScale, RoundingMode.UNNECESSARY)` to fail fast before building display strings when business rules strictly require a fixed scale.

## 13. Testing critical rounding boundaries

Do not test only a single positive number. With two decimal places and common modes, test at minimum:

| Value | HALF_UP | HALF_DOWN | HALF_EVEN |
|---|---|---|---|
| `2.344` | `2.34` | `2.34` | `2.34` |
| `2.345` | `2.35` | `2.34` | `2.34` |
| `2.355` | `2.36` | `2.35` | `2.36` |
| `-2.345` | `-2.35` | `-2.34` | `-2.34` |
| `-2.355` | `-2.36` | `-2.35` | `-2.36` |

At `2.344`, all nearest modes agree because it is not a midpoint. `UP`/`DOWN` and `CEILING`/`FLOOR` must be tested specifically on negative numbers to catch directional mistakes.

Additionally test:

- `minFraction=0/maxFraction=2` with integers: does it append `.00`? (No.)
- `minFraction=2/maxFraction=2` with integers: does it append `.00`? (Yes.)
- `maxFraction=0` with tie-cases `1234.5`, `1235.5` under `HALF_EVEN`.
- `minFraction > maxFraction` across setter ordering: are getters auto-adjusted?
- `applyPattern` after calling setters: are limits reset?
- `maxIntegerDigits` smaller than integer length: are leftmost digits lost?
- Formatting the same value across multiple locales: grouping, decimal separators, and digits may differ.
- `double` values near a decimal tie, e.g., `2.675`, vs. `BigDecimal` created from a string.
- `UNNECESSARY` with values matching scale vs. values requiring rounding.
- Very large numbers, values near 0, negative numbers, high-precision values, and scientific-notation cases if the app permits them.

## 14. Common mistakes

1. **Confusing minimum and maximum digit counts.** Min pads zeros for display; max can round/drop digits.
2. **Relying on default HALF_EVEN when business rules require HALF_UP.** `DecimalFormat`'s default mode is `HALF_EVEN`; set the mode explicitly when required.
3. **Assuming UP always moves toward positive infinity.** `UP` moves away from 0; `CEILING` moves toward positive infinity.
4. **Assuming DOWN always moves toward negative infinity.** `DOWN` moves toward 0; `FLOOR` moves toward negative infinity.
5. **Testing tie-cases with double literals and expecting exact decimals.** Use `BigDecimal` from strings to control decimal values.
6. **Assuming changing min never affects max.** Setters preserve `min <= max` and can auto-adjust the opposite bound.
7. **Calling applyPattern after setters and forgetting limits were reset.** Apply patterns first, configure setters afterward.
8. **Using maxIntegerDigits to block oversized numbers.** The formatter may strip significant left digits; perform validation separately.
9. **Assuming format mutates the numeric value.** It only builds a string; use `BigDecimal.setScale` when a rounded value is needed.
10. **Passing locale-formatted strings to the BigDecimal constructor.** Locale grouping and decimal separators are not constructor syntax.
11. **Formatting money with strictly 2 decimals for all currencies.** Digit counts and cash-rounding rules depend on currency/business policy.
12. **Sharing mutable DecimalFormat instances across threads.** `DecimalFormat` is not thread-safe; instantiate per thread/context.
13. **Skipping validation of counts, quantities, or scales.** Pretty formatting does not guarantee valid input domains.
14. **Ignoring UNNECESSARY outcomes.** This mode enforces exactness and throws `ArithmeticException` when rounding is needed.
15. **Guessing decimal/grouping symbols from Locale.** Use `DecimalFormatSymbols` and verify real outputs.

## 15. Self-check questions

**Question 1.** To display `12` as `12.00`, what needs to be configured?

**Answer:** Minimum 2 fractional digits, such as pattern `0.00` or `setMinimumFractionDigits(2)` with a sufficiently large maximum.

**Question 2.** Keeping 2 decimal digits, how does `2.345` differ under HALF_UP vs. HALF_EVEN?

**Answer:** HALF_UP → `2.35`, HALF_EVEN → `2.34` because digit 4 in `2.34` is even.

**Question 3.** For `-2.345`, what do CEILING and FLOOR return when keeping 2 digits?

**Answer:** CEILING → `-2.34`, FLOOR → `-2.35`.

**Question 4.** Starting from pattern `0.00`, if you call `setMaximumFractionDigits(0)`, what is minimum fraction?

**Answer:** Minimum is adjusted down to 0 so it does not exceed maximum.

**Question 5.** Is `setMaximumIntegerDigits(3)` a validation preventing 5-digit integers?

**Answer:** No. `DecimalFormat` may simply display the last three digits; validate the value before formatting.

**Question 6.** Why can `format(2.675)` and `format(new BigDecimal("2.675"))` differ under HALF_EVEN?

**Answer:** `double` uses an approximate binary representation, whereas `BigDecimal` from a string represents exact decimal 2.675.

**Question 7.** Does `RoundingMode.UNNECESSARY` allow silent truncation?

**Answer:** No. If significant digits would be dropped to meet digit limits, it throws `ArithmeticException`.

**Question 8.** Does formatting into `1,234.50` modify `BigDecimal("1234.5")` into `1234.50`?

**Answer:** No. Formatting is presentation; to change scale under an agreed policy, create a new `BigDecimal` via `setScale`.

## 16. Summary

`DecimalFormat` combines **pattern/Locale** to control digit layout with **`RoundingMode`** to control rounding. `minimumFractionDigits` controls zero padding; `maximumFractionDigits` controls the rounding point. `minimumIntegerDigits` can pad leading zeros, while `maximumIntegerDigits` must be used carefully because it can truncate leftmost digits.

For financial logic or high-precision data, store/compute using `BigDecimal`, establish rounding and scale policies explicitly in the business layer, and format by locale at the display step. Testing positive numbers, negatives, tie-cases, min/max bounds, and setter ordering prevents both arithmetic and localization bugs.

**Official documentation:** [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) · [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) · [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html) · [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).
