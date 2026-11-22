# `RoundingMode` of Formatters in Java

When displaying a number as a string, an application often needs to cap the number of decimal places: prices have two digits after the decimal point, ratios have three digits, or values in a report must share the same precision. If a value has more digits than the display limit, **the formatter must decide which direction to round**. In Java, `java.math.RoundingMode` describes that rule; `java.text.DecimalFormat` lets you configure it with `setRoundingMode(...)`.

This lesson explains how `RoundingMode` governs the **formatting output** of `DecimalFormat`, especially when encountering numbers exactly halfway between two rounding levels (*ties*) and negative numbers. Rounding in arithmetic using `BigDecimal` is contrasted to avoid confusing their purposes.

## 1. At which step does rounding occur?

There are three distinct concepts:

1. **Original value:** e.g., `BigDecimal("12.345")` still represents the value `12.345`.
2. **Display precision:** pattern `0.00` or `setMaximumFractionDigits(2)` specifies displaying no more than two decimal digits.
3. **Rule for choosing an approximation:** `RoundingMode.HALF_UP`, `HALF_EVEN`, `FLOOR`, etc., specify how to handle the discarded portion.

For example, the same value `12.345` with two digits after the decimal point:

| Formatter | Rule | Resulting string |
|---|---|---|
| `0.00` | `HALF_UP` | `12.35` |
| `0.00` | `HALF_EVEN` | `12.34` |
| `0.00` | `DOWN` | `12.34` |

`DecimalFormat.format(...)` returns a **`String`**; it does not modify the `BigDecimal` object and does not update the input numeric variable. If you need a rounded value for further calculations, use an appropriate arithmetic API such as `BigDecimal.setScale(...)` with the chosen rule.

### How to configure it

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

DecimalFormat formatter = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
formatter.setRoundingMode(RoundingMode.HALF_UP);

String text = formatter.format(new BigDecimal("1234.565"));
// text = "1,234.57"
```

This is an **illustrative code snippet** to be placed inside a method or JShell (not a standalone Java file). The `#,##0.00` pattern enables thousands grouping and always prints exact two fractional digits; the `Locale.US` symbol set uses `.` for the decimal part and `,` for thousands. `HALF_UP` picks the side away from 0 when the value lies exactly halfway between two rounding levels.

`DecimalFormat` defaults to `RoundingMode.HALF_EVEN`, though you should set it explicitly so code readers recognize the business rule and to avoid relying on defaults.

## 2. The eight modes of `RoundingMode`

Suppose formatting enforces **two decimal places**, and the input value is `2.345` or `-2.345`. Both lie exactly halfway between the two nearest levels because the third digit is `5` with no remaining digits.

| Mode | Meaning | `2.345` | `-2.345` |
|---|---|---:|---:|
| `UP` | Away from 0 if any non-zero part is discarded | `2.35` | `-2.35` |
| `DOWN` | Toward 0; discards digits beyond precision | `2.34` | `-2.34` |
| `CEILING` | Toward positive infinity (`+∞`) | `2.35` | `-2.34` |
| `FLOOR` | Toward negative infinity (`-∞`) | `2.34` | `-2.35` |
| `HALF_UP` | Nearest neighbor; if tied, away from 0 | `2.35` | `-2.35` |
| `HALF_DOWN` | Nearest neighbor; if tied, toward 0 | `2.34` | `-2.34` |
| `HALF_EVEN` | Nearest neighbor; if tied, the last retained digit must be even | `2.34` | `-2.34` |
| `UNNECESSARY` | Disallows rounding that changes the value | Throws `ArithmeticException` | Throws `ArithmeticException` |

**Two groups of rules to distinguish:**

- `UP`, `DOWN`, `CEILING`, and `FLOOR` determine **direction** whenever a non-zero portion is discarded, regardless of whether that portion is greater or less than `0.5` units of the last retained digit.
- `HALF_UP`, `HALF_DOWN`, and `HALF_EVEN` pick the **nearest value** first; only when distances to both adjacent values are equal do their *tie*-breaking rules differ.

For example, `2.346` printed with two decimal places becomes `2.35` under all three of `HALF_UP`, `HALF_DOWN`, and `HALF_EVEN`: this is not a tie, because `2.35` is closer than `2.34`.

### Why doesn't `HALF_EVEN` mean "always round down"?

On a tie, `HALF_EVEN` picks the result whose **last retained digit is even**:

- `2.345` → `2.34`, because the hundredths digit is `4` (even).
- `2.355` → `2.36`, because the hundredths digit is `6` (even).
- `-2.345` → `-2.34`, following the same even-digit rule.

This mechanism is also called *round half to even* or *banker's rounding*. Across many rounding operations on suitably distributed data, it helps reduce cumulative bias from always breaking ties in one direction. That does not make it mandatory for every monetary system: each system must apply the rounding policy specified for its business domain.

### Especially with negative numbers

`CEILING` and `FLOOR` do not equate to "increasing" and "decreasing" absolute magnitude:

- `CEILING(-2.345)` at two decimal places → `-2.34`, because `-2.34` is **greater than** `-2.35`.
- `FLOOR(-2.345)` → `-2.35`, because `-2.35` is **less than** `-2.34`.
- `UP` always points **away from 0**; `DOWN` always points **toward 0**, for both positive and negative signs.

This is a common reason why testing only positive numbers misses bugs.

## 3. Standalone runnable Java 17+ program

Save the file as `RoundingModeFormatterDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingModeFormatterDemo {
    private static String display(String value, RoundingMode mode) {
        DecimalFormat formatter = new DecimalFormat("0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setRoundingMode(mode);
        return formatter.format(new BigDecimal(value));
    }

    public static void main(String[] args) {
        for (RoundingMode mode : new RoundingMode[] {
                RoundingMode.UP, RoundingMode.DOWN, RoundingMode.CEILING,
                RoundingMode.FLOOR, RoundingMode.HALF_UP, RoundingMode.HALF_DOWN,
                RoundingMode.HALF_EVEN
        }) {
            System.out.println(mode + ": " + display("2.345", mode)
                    + " | " + display("-2.345", mode));
        }
        System.out.println("HALF_EVEN 2.355: "
                + display("2.355", RoundingMode.HALF_EVEN));
        try {
            System.out.println(display("2.345", RoundingMode.UNNECESSARY));
        } catch (ArithmeticException ex) {
            System.out.println("UNNECESSARY: ArithmeticException");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 RoundingModeFormatterDemo.java
java RoundingModeFormatterDemo
```

Standard output in a Java environment supporting these APIs (e.g., Java 17):

```text
UP: 2.35 | -2.35
DOWN: 2.34 | -2.34
CEILING: 2.35 | -2.34
FLOOR: 2.34 | -2.35
HALF_UP: 2.35 | -2.35
HALF_DOWN: 2.34 | -2.34
HALF_EVEN: 2.34 | -2.34
HALF_EVEN 2.355: 2.36
UNNECESSARY: ArithmeticException
```

**Program explanation:**

1. `new BigDecimal(value)` takes a decimal string to create an input matching the written number, allowing exact testing of tie values.
2. `new DecimalFormat("0.00", ...)` caps the output at two decimal places and fixes display symbols.
3. `setRoundingMode(mode)` changes how results are chosen when digits must be dropped.
4. The loop tests the modes across the same positive and negative data. `UNNECESSARY` is tested separately because it asserts **no rounding is needed**, and it can throw an exception.

## 4. Relationship between format pattern, digit count, and `RoundingMode`

`RoundingMode` **does not by itself dictate** rounding to whole units, one decimal place, or two decimal places. The rounding position is determined by the formatter's digit configuration.

```java
DecimalFormat f = new DecimalFormat("0.##",
        DecimalFormatSymbols.getInstance(Locale.US));
f.setRoundingMode(RoundingMode.HALF_UP);

f.format(new BigDecimal("2.345")); // "2.35"
f.format(new BigDecimal("2.3"));   // "2.3"
f.format(new BigDecimal("2"));     // "2"
```

The `0.##` pattern allows **at most** two digits after the decimal point; `#` does not force trailing zeros to print. If you want two digits always printed, use `0.00`. This is a **presentation** difference, not two different rounding modes.

You can configure via methods instead of a pattern:

```java
DecimalFormat f = new DecimalFormat("#,##0.###",
        DecimalFormatSymbols.getInstance(Locale.US));
f.setMinimumFractionDigits(2);
f.setMaximumFractionDigits(2);
f.setRoundingMode(RoundingMode.HALF_UP);

f.format(new BigDecimal("1234.565")); // "1,234.57"
f.format(new BigDecimal("1234.5"));   // "1,234.50"
```

- `setMaximumFractionDigits(2)`: limits displayed fractional digits to at most two; this is the setting that can trigger rounding.
- `setMinimumFractionDigits(2)`: requires printing at least two digits, even if zeros must be appended.
- `getRoundingMode()`: reads the formatter's current rule.
- `setRoundingMode(...)`: sets the rule when digits must be discarded.

For a value already represented at the required display precision (e.g., `2.34` printed to two decimal places), all modes yield the same resulting value; appending zeros (`2.3` → `2.30`) is not value-changing rounding.

## 5. `UNNECESSARY`: detecting instead of automatically rounding

`RoundingMode.UNNECESSARY` fits when a data contract requires inputs to **already have the right precision**, and discarding any non-zero fraction must be reported as an error.

```java
DecimalFormat strict = new DecimalFormat("0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
strict.setRoundingMode(RoundingMode.UNNECESSARY);

strict.format(new BigDecimal("2.34"));  // "2.34"
strict.format(new BigDecimal("2.340")); // "2.34": dropping trailing 0 does not change value
strict.format(new BigDecimal("2.345")); // ArithmeticException
```

This snippet illustrates individual calls; if run sequentially without catching the exception, the last statement halts execution. Importantly, `UNNECESSARY` **does not forbid every character-string change**: it forbids rounding that changes the **numeric value**. Thus dropping redundant trailing decimal zeros remains valid.

If values come from user input or an API, validate scale/precision requirements right at the input boundary and return a clear business error; do not use `UNNECESSARY` as a substitute for a complete input-validation pipeline.

## 6. Formatting differs from rounding for arithmetic

There are two valid processing flows, depending on the goal.

**Display only:**

```java
BigDecimal original = new BigDecimal("19.995");
DecimalFormat view = new DecimalFormat("0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
view.setRoundingMode(RoundingMode.HALF_UP);

String label = view.format(original); // "20.00"
// original is still 19.995
```

**Continue calculating with the rounded value:**

```java
BigDecimal original = new BigDecimal("19.995");
BigDecimal rounded = original.setScale(2, RoundingMode.HALF_UP);
// rounded = 20.00 (BigDecimal, scale = 2)
```

Both `format(...)` and `setScale(...)` can take a `RoundingMode`, but their outputs differ in kind: one is a `String` for presentation, while the other is a `BigDecimal` for arithmetic. `BigDecimal` is immutable: `setScale(...)` returns a new object instead of mutating `original`.

When calculating money, taxes, discounts, or reconciliations, you must determine **when rounding occurs** per business rules (per line item, per transaction, or at the final total). Summing formatted strings or formatting before each step and parsing back into numbers can lose information and introduce discrepancies. `RoundingMode` only determines **how** to round when a rounding step is reached; it does not decide **when** to round.

## 7. `double` input, `BigDecimal`, and binary representation pitfalls

Most decimal fractions are not represented exactly by `double`. When testing sensitive cases such as exact midpoints, using `double` values can make results hard to deduce just by looking at decimal literals in source code.

```java
BigDecimal exact = new BigDecimal("2.345"); // Exact 2.345
BigDecimal fromDouble = new BigDecimal(2.345); // Captures the exact binary value of the double
```

These two ways of creating a `BigDecimal` do not guarantee the same numeric value. To express a business decimal value, prefer constructing `BigDecimal` from a decimal string, from controlled decimal data, or using `BigDecimal.valueOf(double)` when converting from `double` is unavoidable (understanding that prior `double` arithmetic may already have lost precision).

When calling `DecimalFormat.format(double)`, remember you are formatting the **actual `double` value**, not an "ideal decimal number" imagined from the literal. For testing tie rules and monetary figures, `BigDecimal` constructed from strings expresses intent far more accurately.

## 8. Choosing a mode based on usage requirements

There is no single best mode for every problem. Choose according to the rules of the data and its consumers.

| Scenario | Option to consider | Why |
|---|---|---|
| Statistical reports with many roundings | `HALF_EVEN` | Can reduce cumulative bias when many values land on ties |
| Business rule requires ties away from 0 | `HALF_UP` | Rule is easy to explain for both positive and negative numbers |
| Truncating digits, always toward 0 | `DOWN` | Expresses intent to discard digits beyond precision |
| Finding rounding bounds up/down the number line | `CEILING` / `FLOOR` | Directions defined toward `+∞` / `-∞` |
| Data strictly required to already match precision | `UNNECESSARY` | Explicit error if rounding would alter the value |

Monetary scenarios require special care: rounding rules, currency units, digit counts, and where rounding is applied must follow product specs, legal regulations, or contracts. Do not assume that calling `NumberFormat.getCurrencyInstance(...)` automatically satisfies all monetary rounding laws.

A locale-based currency formatter can still have its `RoundingMode` configured:

```java
import java.text.NumberFormat;

NumberFormat usd = NumberFormat.getCurrencyInstance(Locale.US);
usd.setRoundingMode(RoundingMode.HALF_UP);

String amount = usd.format(new BigDecimal("1234.565"));
// With Locale.US currency symbol and rules: "$1,234.57"
```

`NumberFormat` is a base class. Common decimal formatters support `setRoundingMode(...)`, though the base class API allows certain implementations to throw `UnsupportedOperationException`. If you need to rely on `DecimalFormat`-specific behavior or configuration, work directly with a `DecimalFormat` instance.

## 9. Common mistakes and how to avoid them

**Mistake 1 — Setting `RoundingMode` without limiting digits.** If the formatter still displays the full input precision, the rounding rule may never take effect. Check the format pattern, `getMinimumFractionDigits()`, and `getMaximumFractionDigits()`.

**Mistake 2 — Confusing `DOWN` with `FLOOR`, or `UP` with `CEILING`.** For negative numbers, these mode pairs produce different results. Include tests for both `2.345` and `-2.345`.

**Mistake 3 — Thinking `HALF_UP` always rounds up.** `HALF_UP` picks the nearest result and only goes away from 0 on an exact tie. For `2.341` at two decimal places, `HALF_UP` gives `2.34`, not `2.35`.

**Mistake 4 — Thinking `HALF_EVEN` always rounds down.** `2.345` → `2.34`, whereas `2.355` → `2.36`.

**Mistake 5 — Omitting locale when comparing strings.** Decimal and thousands separators depend on `DecimalFormatSymbols`/`Locale`. For tests comparing fixed stdout, pass `Locale.US`; for real UIs, use the required locale.

**Mistake 6 — Assuming the formatted string alters the source number.** `format()` only builds a display string. If business logic actually needs a rounded value, explicitly save the arithmetic result (`BigDecimal.setScale(...)`) at the appropriate step.

**Mistake 7 — Sharing a single `DecimalFormat` across multiple threads.** `DecimalFormat` has mutable state and is not guaranteed safe when accessed concurrently without synchronization. Usually create a formatter per call/task scope, or design an appropriate usage and synchronization strategy.

**Mistake 8 — Believing two-digit display guarantees every calculation is accurate to two decimal places.** The final formatting step does not replace precision policies across the entire calculation pipeline. Check scale, rounding points, and summation order per business requirements.

## 10. Self-check exercises

Suppose you use `new DecimalFormat("0.00", DecimalFormatSymbols.getInstance(Locale.US))` to format `BigDecimal` values created from **strings**. Predict the results before running:

1. `1.225` with `HALF_EVEN`.
2. `1.235` with `HALF_EVEN`.
3. `-1.225` with `CEILING`.
4. `-1.225` with `FLOOR`.
5. `2.300` with `UNNECESSARY`.
6. `2.301` with `UNNECESSARY`.

**Answers and reasons:**

1. `1.22`: between `1.22` and `1.23`, picks the even final digit (`2`).
2. `1.24`: between `1.23` and `1.24`, picks the even final digit (`4`).
3. `-1.22`: toward positive infinity.
4. `-1.23`: toward negative infinity.
5. `2.30`: only drops redundant trailing zero without changing value.
6. Throws `ArithmeticException`: reducing to two digits requires rounding away a non-zero portion.

When testing number formatting, at minimum include positive numbers, negative numbers, exact ties, near-ties, values already at exact precision, and values where rounding is disallowed.

## Takeaway

- **Display precision** is determined by the `DecimalFormat` pattern or digit-setting methods; **rounding direction** is determined by `RoundingMode`.
- `HALF_UP`, `HALF_DOWN`, and `HALF_EVEN` differ **only on ties**; for all other values, they pick the same nearest value.
- `UP`/`DOWN` consider direction relative to **0**; `CEILING`/`FLOOR` consider direction along the **number line**.
- `DecimalFormat.format(...)` produces a `String` and leaves the input value unchanged; `BigDecimal.setScale(...)` returns a new numeric value.
- For results requiring exact sign and rounding rules, use controlled decimal values and test both negative cases and ties.