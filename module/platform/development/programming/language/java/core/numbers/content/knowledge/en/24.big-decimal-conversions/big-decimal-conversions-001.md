# BigDecimal.toString() and Scientific Notation When Appropriate

## Objectives

When converting a `BigDecimal` to a string in Java, the `toString()` method does not always produce a number written out in full standard decimal form. It may choose **scientific notation** such as `1E-7` or `1E+6`. This behavior follows clear rules depending on the **unscaled value**, **scale**, and **precision** of the `BigDecimal`.

After this lesson, you will be able to explain when `toString()` produces scientific notation, choose correctly between `toString()`, `toPlainString()`, and `toEngineeringString()`, and understand the impact of parsing the string back into a `BigDecimal`.

## 1. How Does BigDecimal Store Values?

`BigDecimal` represents a number using two main components:

- **Unscaled value**: an integer containing the significant digits, retrieved via `unscaledValue()`.
- **Scale**: the number of decimal digits in the representation, retrieved via `scale()`. The scale can be positive, zero, or negative.

The numeric value is calculated by the formula:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Examples:

| String Creating BigDecimal | Unscaled value | Scale | Value |
|---|---:|---:|---|
| `"123.4500"` | `1234500` | `4` | `123.4500` |
| `"0.000001"` | `1` | `6` | `0.000001` |
| `"0.0000001"` | `1` | `7` | `0.0000001` |
| `"1E+3"` | `1` | `-3` | `1000` |
| `"1000"` | `1000` | `0` | `1000` |

The two objects `new BigDecimal("1E+3")` and `new BigDecimal("1000")` are **equal in numeric value**, but differ in scale and unscaled value. Therefore, `compareTo()` can return `0` while `equals()` returns `false`.

**Precision** is the number of digits in the unscaled value, excluding the sign and leading zeros (specifically, the value 0 has a precision of 1). For example, `123.4500` has precision `7`, scale `4`; `1E+3` has precision `1`, scale `-3`. Do not confuse precision with the number of digits after the decimal point.

## 2. Does toString() Produce Decimal Form or Scientific Notation?

`BigDecimal.toString()` produces the **canonical string representation** of the unscaled value and scale pair. The method preserves the value, scale, and trailing zeros that are significant to the representation; it **does not round** and does not convert through `double`.

To understand the display rules, consider the **adjusted exponent** of `BigDecimal`:

\[
\text{adjustedExponent} = \text{precision} - \text{scale} - 1
\]

For a non-zero `BigDecimal`, the adjusted exponent indicates the power of 10 corresponding to the first significant digit. The canonical mechanism of `toString()` chooses:

1. **Standard decimal form** if the **scale is non-negative** (`scale >= 0`) **and the adjusted exponent is -6 or greater** (`adjustedExponent >= -6`).
2. **Scientific notation** in all remaining cases, with one significant digit before the decimal point, the remaining digits (if any) after it, followed by the `E` symbol and the exponent.

For positive exponents, Java adds a `+` sign after `E`, such as `1E+3`. For negative exponents, Java uses a `-` sign like `1E-7`. In standard form, the decimal separator is `.`, independent of the machine's locale settings.

Two threshold examples are well worth remembering:

- `new BigDecimal("0.000001").toString()` produces `"0.000001"`: precision `1`, scale `6`, adjusted exponent `-6`, so it keeps standard form.
- `new BigDecimal("0.0000001").toString()` produces `"1E-7"`: precision `1`, scale `7`, adjusted exponent `-7`, so it switches to scientific notation.

The rule also depends on **scale**, not just the magnitude of the number. `new BigDecimal("1000000").toString()` is `"1000000"` because scale is `0`; `new BigDecimal("1E+6").toString()` is `"1E+6"` because scale is `-6`. Their numeric values are identical.

### What Does a Scientific String Mean?

In Java `BigDecimal` syntax:

- `1E-7` means \(1 \times 10^{-7}\), i.e. `0.0000001`.
- `1.23E+4` means \(1.23 \times 10^4\), i.e. `12300`.
- `1E+6` means \(1 \times 10^6\), i.e. `1000000`.

`E` denotes a base-10 exponent, not a calculation involving Euler's mathematical constant. In Java, the value can be reconstructed using `new BigDecimal("1E-7")`.

## 3. Distinguishing toString(), toPlainString(), and toEngineeringString()

All three methods **only produce a string**; they do not modify or round the `BigDecimal` object.

| Method | Purpose | Example with `new BigDecimal("0.0000001")` |
|---|---|---|
| `toString()` | Canonical string, may use scientific notation depending on scale and adjusted exponent | `"1E-7"` |
| `toPlainString()` | Full decimal string, **without E notation** | `"0.0000001"` |
| `toEngineeringString()` | When written in exponential form, chooses an **exponent that is a multiple of 3**; the significand can have 1–3 digits before the decimal point | `"100E-9"` |

Common examples:

| Created Value | `toString()` | `toPlainString()` | `toEngineeringString()` |
|---|---|---|---|
| `"123.4500"` | `123.4500` | `123.4500` | `123.4500` |
| `"0.000001"` | `0.000001` | `0.000001` | `0.000001` |
| `"0.0000001"` | `1E-7` | `0.0000001` | `100E-9` |
| `"1E+3"` | `1E+3` | `1000` | `1E+3` |
| `"1.23E+4"` | `1.23E+4` | `12300` | `12.3E+3` |
| `"1000000"` | `1000000` | `1000000` | `1000000` |
| `"1000000.00"` | `1000000.00` | `1000000.00` | `1000000.00` |

`100E-9` and `1E-7` have the same value because \(100 \times 10^{-9} = 10^{-7}\). Engineering notation is useful when presenting orders of magnitude in groups of thousands, millions, and billions; whereas the standard scientific notation of `toString()` prioritizes a single digit before the decimal point.

### Which Method Should You Choose?

- **Recording a BigDecimal representation so it can be read back with the exact value and scale**: use `toString()`. The canonical string contains enough information so that `new BigDecimal(original.toString()).equals(original)` is `true`.
- **UI, logs, or text fields requiring no E**: use `toPlainString()`, but check the length because a number with a very large absolute scale can produce a very long string.
- **Displaying exponents as multiples of 3**: use `toEngineeringString()` if this is the desired presentation rule.

For monetary amounts with a fixed display format, you must determine the **scale/rounding** separately before converting to a string. `toPlainString()` only changes the representation; it does not automatically enforce two fractional digits. For example, `new BigDecimal("12.345").toPlainString()` is still `"12.345"`.

## 4. Runnable Java 17+ Program

Save as **`BigDecimalStringDemo.java`**:

```java
import java.math.BigDecimal;

public class BigDecimalStringDemo {
    private static void show(String source) {
        BigDecimal number = new BigDecimal(source);

        System.out.println(source
                + " | " + number.toString()
                + " | " + number.toPlainString()
                + " | " + number.toEngineeringString()
                + " | " + number.precision()
                + " | " + number.scale());
    }

    public static void main(String[] args) {
        System.out.println("input | toString | plain | engineering | precision | scale");

        for (String source : new String[] {
                "123.4500",
                "0.000001",
                "0.0000001",
                "1E+3",
                "1.23E+4",
                "1000000",
                "1000000.00"
        }) {
            show(source);
        }

        BigDecimal withZeros = new BigDecimal("1000000.00");
        BigDecimal stripped = withZeros.stripTrailingZeros();
        System.out.println("stripTrailingZeros: " + stripped.toString());

        BigDecimal scientific = new BigDecimal("1E+3");
        BigDecimal fromCanonical = new BigDecimal(scientific.toString());
        BigDecimal fromPlain = new BigDecimal(scientific.toPlainString());

        System.out.println("canonical equals: " + scientific.equals(fromCanonical));
        System.out.println("plain equals: " + scientific.equals(fromPlain));
        System.out.println("plain compareTo: " + scientific.compareTo(fromPlain));
    }
}
```

Compile and run:

```bash
javac BigDecimalStringDemo.java
java BigDecimalStringDemo
```

Exact output:

```text
input | toString | plain | engineering | precision | scale
123.4500 | 123.4500 | 123.4500 | 123.4500 | 7 | 4
0.000001 | 0.000001 | 0.000001 | 0.000001 | 1 | 6
0.0000001 | 1E-7 | 0.0000001 | 100E-9 | 1 | 7
1E+3 | 1E+3 | 1000 | 1E+3 | 1 | -3
1.23E+4 | 1.23E+4 | 12300 | 12.3E+3 | 3 | -2
1000000 | 1000000 | 1000000 | 1000000 | 7 | 0
1000000.00 | 1000000.00 | 1000000.00 | 1000000.00 | 9 | 2
stripTrailingZeros: 1E+6
canonical equals: true
plain equals: false
plain compareTo: 0
```

**How to read the output:** The `0.0000001` line shows that `toString()` can automatically choose exponential notation when the adjusted exponent is less than `-6`. The `1E+3` line shows that `toPlainString()` turns the value into `1000` but **does not preserve the negative scale** after parsing the string back. The `stripTrailingZeros` line illustrates that the same value `1000000` can be represented in exponential notation when the scale changes.

## 5. Why Isn't toPlainString() Always Suitable for BigDecimal Round-Trips?

For `BigDecimal`, there are two different ways to compare:

- `compareTo()` compares **numeric value**; `new BigDecimal("1E+3").compareTo(new BigDecimal("1000")) == 0`.
- `equals()` requires the same **numeric value and scale**; the two objects above are not `equals` because their scales are `-3` and `0`, respectively.

Consider:

```java
BigDecimal original = new BigDecimal("1E+3");
BigDecimal parsedCanonical = new BigDecimal(original.toString());
BigDecimal parsedPlain = new BigDecimal(original.toPlainString());

System.out.println(original.scale());             // -3
System.out.println(parsedCanonical.scale());      // -3
System.out.println(parsedPlain.scale());          // 0
System.out.println(original.equals(parsedPlain)); // false
System.out.println(original.compareTo(parsedPlain) == 0); // true
```

`toString()` is the standard choice when you need a **round-trip that reproduces the exact same BigDecimal representation**, including scale. `toPlainString()` is more suitable when you need a human-readable string without scientific notation. If the application only cares about numeric value, `compareTo()` reflects the numerical relationship more appropriately than `equals()`; if scale is part of the data contract, preserve the scale information or use `toString()`.

Note that `System.out.println(number)`, string concatenation `"x=" + number`, and `String.valueOf(number)` all invoke `toString()` on a non-null `BigDecimal`. Therefore, those printing approaches **can still display scientific notation**. Call `toPlainString()` directly if the display target requires the full plain form.

## 6. stripTrailingZeros() Can Cause E to Appear

`stripTrailingZeros()` returns a `BigDecimal` that is equivalent in **numeric value** but removes trailing zeros from the unscaled value representation where possible. The result can have a **negative scale**, causing `toString()` to switch to scientific notation.

Example:

```java
BigDecimal before = new BigDecimal("1000000.00");
BigDecimal after = before.stripTrailingZeros();

System.out.println(before.toString());  // 1000000.00
System.out.println(before.scale());     // 2
System.out.println(after.toString());   // 1E+6
System.out.println(after.scale());      // -6
System.out.println(after.toPlainString()); // 1000000
```

This is **not an error and not a rounding operation**. The value is still one million; it is the unscaled value/scale representation itself that has changed. `stripTrailingZeros()` also does not modify the `before` object because `BigDecimal` is immutable.

This often causes confusion when a data normalization function calls `stripTrailingZeros()` and somewhere else inadvertently uses `toString()` to output the result. If the output requirement is a string without E, choose `toPlainString()` after obtaining the result object. If the requirement is to keep the original number of decimal places (e.g., `1000000.00`), **do not strip trailing zeros before storing the representation**.

## 7. Edge Cases and Common Pitfalls

### Treating Scientific Notation as Loss of Value or Precision

`1E-7` and `0.0000001` are both the exact decimal value \(10^{-7}\). `toString()` does not truncate significant digits to a new precision. It simply chooses the notation corresponding to the existing unscaled value/scale. Do not use `doubleValue()` and convert to a string to "avoid E": `double` has a different representation range and binary precision than `BigDecimal`.

### Assuming Large BigDecimals Must Automatically Print in Scientific Notation

`new BigDecimal("1000000")` prints `1000000`; `new BigDecimal("1E+6")` prints `1E+6` even though their values are equal. The condition in `toString()` is based on **scale and adjusted exponent**, not a single absolute value threshold.

### Removing Trailing Zeros and Expecting the Same Scale

`new BigDecimal("12.3400").toString()` is `"12.3400"` because scale `4` is still preserved. `stripTrailingZeros()` can change the scale; `toPlainString()` does not restore the original representation's trailing zeros. If the data requires an exact number of digits, use `setScale(scale, roundingMode)` according to business rules before outputting the string. The `setScale` method may require rounding and takes a `RoundingMode`; it differs functionally from the three string-conversion-only methods.

### Using Strings to Decide Which Number Is Larger

Comparing the strings `"1E+3"` and `"900"` lexicographically is not equivalent to numeric comparison. Compare the `BigDecimal` objects themselves using `compareTo()` first, then convert to strings when needed for display or data transmission.

### Forgetting Locale-Specific Formatting Requirements

`toString()`, `toPlainString()`, and `toEngineeringString()` all use Java-style decimal notation (a period and E notation when applicable), and **do not automatically switch** to a comma based on locale or add thousands separators. If the UI requires locale-specific presentation rules, use formatting mechanisms like `NumberFormat`/`DecimalFormat`, configured with the appropriate locale and rounding. Formatting for display should be kept distinct from the canonical representation used for storing/reading back BigDecimal values.

### Ignoring Output Size

`toPlainString()` always attempts to build the full plain form; with a scale of very large magnitude, the string may contain an enormous number of digits or zeros. Choose the full plain form only when genuinely needed and when input data has appropriate bounds. The exponential form of `toString()` is shorter in many cases, though it is not an output size-limiting mechanism.

## 8. Process for Choosing a String Conversion Method

1. **Need to store and restore the exact BigDecimal object, including its scale?** Use `toString()`, then parse with `new BigDecimal(text)`. This is the canonical representation suitable for round-trips.
2. **Need full display, with no E allowed?** Use `toPlainString()`; specify scale/rounding and output length yourself if business rules demand it.
3. **Need exponential notation with exponents as multiples of 3?** Use `toEngineeringString()`.
4. **Unexpectedly seeing E after a normalization step?** Check `stripTrailingZeros()` and `scale()` before/after.
5. **Two different strings describing the same number?** Check both `compareTo()` and `scale()`; do not assume `equals()` reflects only the numeric value.

**Self-check:** Why is `new BigDecimal("0.000001").toString()` equal to `"0.000001"`, while `new BigDecimal("0.0000001").toString()` is `"1E-7"`? Because their adjusted exponents are `-6` and `-7` respectively, while both scales are non-negative. And why does `new BigDecimal("1E+3").toPlainString()` produce `"1000"` yet reading it back can yield `equals() == false`? Because the plain string loses the negative scale `-3`; the parsed object has scale `0` even though the numeric value is unchanged.

**Takeaway:** `BigDecimal.toString()` chooses scientific notation based on scale and adjusted exponent, preserving the representation for round-trips; `toPlainString()` guarantees no E; `toEngineeringString()` uses exponents in multiples of 3. None of the three **perform rounding**.
