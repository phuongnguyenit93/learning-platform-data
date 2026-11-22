# Formatting Fewer Digits Does Not Fix Error in a Stored Java Value

In Java, a `double` value can **display** as `0.30` while the actual stored value is a floating-point number near `0.30000000000000004`. Asking `printf`, `String.format`, or `DecimalFormat` to print two digits after the decimal point only changes the **presentation string**. It does not update the variable, does not change the bits of the `double`, and does not cure errors that already occurred during computation.

This lesson belongs to the **Error and stability** topic. The goal is to clearly distinguish (1) the stored binary representation, (2) the visible text string, (3) intentional rounding, and (4) exact decimal computation with `BigDecimal` when the business domain requires it. This distinction governs how you test floating-point numbers, accumulate sums, export data, and calculate money.

## 1. Three Layers Often Conflated

| Layer | Example | What actually happens? |
| --- | --- | --- |
| Value stored in `double` | `double sum = 0.1 + 0.2;` | Machine stores the bit pattern of a `double` value close to the mathematical sum |
| String used for display | `String.format(Locale.ROOT, "%.2f", sum)` | Creates string `"0.30"`; **does not modify `sum`** |
| Re-rounded / quantized value | `Math.round(sum * 100.0) / 100.0` | Computes and assigns a **new `double` value** (still binary floating point) |
| Policy-based decimal number | `new BigDecimal("0.30")` | Stores a decimal number in `BigDecimal`, roundable via `RoundingMode` |

Two key concepts:

- **Formatting**: transforms *how a value is presented* into characters. The number of printed digits does not equal the number of stored digits.
- **Rounding**: produces a new arithmetic or decimal result according to a rounding rule. It can change the retained result if you actually reassign it, yet it does not guarantee a `double` becomes an exact decimal.

Even when a screen, log, table, or JSON payload is asked to "display concisely," the prior calculations were still executed on the stored value itself.

## 2. Why Does `0.1 + 0.2` Not Equal `0.3` Exactly?

`float` and `double` use IEEE 754 binary floating-point representation. Most decimal fractions such as 0.1, 0.2, and 0.3 have **infinite repeating** binary representations, so they must be rounded to the nearest bit pattern when stored in a finite width. When adding two already-rounded operands, the result is rounded again according to floating-point rules.

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum);             // 0.30000000000000004
System.out.println(sum == 0.3);      // false
System.out.println(sum - 0.3);       // 5.551115123125783E-17
~~~

`0.3` as a `double` literal is also an approximate binary number, yet its representation **differs by a tiny amount** from the result of `0.1 + 0.2`. The `==` operator compares two stored floating-point values under Java rules and does not automatically apply a decimal tolerance.

The default output of `Double.toString` and `System.out.println(double)` is usually a short decimal form sufficient to read back the exact same bit pattern (`shortest round-trip representation`), **not the full exact decimal expansion of the stored bits**. To see the exact decimal value corresponding to a `double`, you can use `new BigDecimal(sum)` for inspection purposes. That technique differs from the recommended way to construct `BigDecimal` for exact decimal data.

## 3. `String.format` and `printf` Only Change What Is Visible

~~~java
double sum = 0.1 + 0.2;
String display = String.format(java.util.Locale.ROOT, "%.2f", sum);
System.out.println(display); // 0.30
System.out.println(sum);     // 0.30000000000000004
~~~

`%.2f` requests fixed formatting with two digits after the decimal point. The formatter produces a string and **does not assign back into `sum`**. Similarly:

~~~java
System.out.printf(java.util.Locale.ROOT, "Result: %.2f%n", sum);
// Prints: Result: 0.30
// Does not modify the value of sum
~~~

With `DecimalFormat`, a pattern like `"0.00"` also specifies **presentation**. `DecimalFormat` has its own rules for locale, pattern, and rounding mode; do not assume every formatter shares the same rounding policy at exact midpoints.

The decimal separator can depend on locale: a machine's default in one country may use a comma. When machine-readable text output or deterministic output in an example is needed, specify `Locale.ROOT` or an appropriate fixed locale. When displaying to users, choose the locale per UI requirements.

**Common thinking trap:** seeing `0.30` in logs and concluding the calculation is accurate to two digits. Logs only show a shortened view, which can hide discrepancies large enough to affect comparisons, decision thresholds, or subsequent calculations.

## 4. Standalone Java 17+ Example

Save the file named `DisplayVsValue.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public class DisplayVsValue {
    public static void main(String[] args) {
        double result = 0.1 + 0.2;
        String displayed =
                String.format(Locale.ROOT, "%.2f", result);
        double parsed = Double.parseDouble(displayed);

        System.out.println("raw sum = " + result);
        System.out.println("formatted = " + displayed);
        System.out.println("raw sum after formatting = " + result);
        System.out.println("sum == 0.3 = " + (result == 0.3));
        System.out.println("parsed = " + parsed);
        System.out.println("parsed == sum = " + (parsed == result));
        System.out.println("sum - 0.3 = " + (result - 0.3));

        System.out.println("decimal from computed sum = "
                + BigDecimal.valueOf(result));
        System.out.println("exact decimal from stored double = "
                + new BigDecimal(result));
        System.out.println("scaled decimal = "
                + BigDecimal.valueOf(result)
                .setScale(2, RoundingMode.HALF_UP));

        BigDecimal exactMoney =
                new BigDecimal("0.10").add(new BigDecimal("0.20"));
        System.out.println("string decimal sum = " + exactMoney);

        double roundedDouble = Math.round(result * 100.0) / 100.0;
        System.out.println("rounded as double = " + roundedDouble);
        System.out.println("rounded double == 0.3 = "
                + (roundedDouble == 0.3));
        System.out.println("rounded double exact = "
                + new BigDecimal(roundedDouble));
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac DisplayVsValue.java
java DisplayVsValue
~~~

Exact stdout:

~~~text
raw sum = 0.30000000000000004
formatted = 0.30
raw sum after formatting = 0.30000000000000004
sum == 0.3 = false
parsed = 0.3
parsed == sum = false
sum - 0.3 = 5.551115123125783E-17
decimal from computed sum = 0.30000000000000004
exact decimal from stored double = 0.3000000000000000444089209850062616169452667236328125
scaled decimal = 0.30
string decimal sum = 0.30
rounded as double = 0.3
rounded double == 0.3 = true
rounded double exact = 0.299999999999999988897769753748434595763683319091796875
~~~

Comparison:

- The first three lines show that the string `0.30` **does not alter the original variable**.
- After parsing `"0.30"`, we obtain a `double` whose short representation is `0.3`; this value **differs** from the original `0.1 + 0.2` result. That is a new data conversion, not a side effect of `String.format`.
- `BigDecimal.valueOf(result)` yields the decimal `0.30000000000000004` based on `double`'s short string form, whereas `new BigDecimal(result)` represents **the exact stored binary value in decimal form**. The two conversions serve different purposes.
- `setScale(2, HALF_UP)` returns a new `BigDecimal` object with two decimal places and an explicit rounding policy.
- `Math.round(...)/100.0` created a new `double` matching the `0.3` literal at the bit level, **yet that `double` itself still cannot store exact decimal 0.3**; the last line shows its full decimal representation.

## 5. Formatting, Parsing, and Reassigning Are Three Different Actions

Suppose:

~~~java
double x = 0.1 + 0.2;
String text = String.format(java.util.Locale.ROOT, "%.2f", x);
~~~

After these two lines, `x` **still equals** `0.30000000000000004`. If you later call `Double.parseDouble(text)`, a **new** `double` value is computed from the formatted string. Only when you explicitly use that new value, e.g., `x = Double.parseDouble(text)`, does the variable `x` change.

Formatting and then parsing is not a general-purpose way to fix precision:

1. You **discard information** according to the display length. Two genuinely different values can turn into the same `"0.30"` string.
2. Strings may use locale-specific decimal separators, grouping separators, or digits; `Double.parseDouble` is not a locale-aware parser.
3. The parsed-back value is still a binary `double`. Many decimal fractions still **cannot be represented accurately**.
4. Formatting/parsing at every calculation step alters the algorithm in hard-to-control ways and can introduce drift from repeated rounding.

If the actual requirement is to store a value quantized to a specific number of digits, define an explicit **arithmetic quantization rule** and store the result in an appropriate type. If only display is needed, format solely at the output step.

## 6. `Math.round` Produces Another Number, Not an Exact Decimal

~~~java
double x = 0.1 + 0.2;
double rounded = Math.round(x * 100.0) / 100.0;
System.out.println(rounded); // 0.3
~~~

In this example, `rounded` no longer shares the same bit pattern as `x`. That differs fundamentally from `String.format`, because the calculation actually produced a new number. However, the result is still of **type `double`**, so it cannot accurately represent most decimal fractions like 0.3.

The expression `Math.round(x * 100.0) / 100.0` is also **not a safe decimal rounding formula for all values**. It can run into issues with very large numbers, overflow during the initial multiplication, NaN/infinity, and midpoint handling for negative numbers. `Math.round` rounds by its own rule; do not assume that rule matches invoicing or financial policies.

Example showing the difference between a rounding policy and display:

~~~java
BigDecimal amount = new BigDecimal("1.005");
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
// rounded = 1.01 (decimal number with scale 2)
~~~

`setScale` returns **a new `BigDecimal`** (the original object is unchanged), and `RoundingMode.HALF_UP` explicitly describes how dropped digits are handled. The same data can use a different policy, such as `HALF_EVEN`, if the business requires it. Do not pick a policy just because the UI prints two digits.

## 7. When Should `BigDecimal` Be Used?

If the data domain demands **exact rule-based decimal** addition, subtraction, multiplication, and quantization—such as monetary amounts, list prices, or unit conversions with fixed decimal steps—`BigDecimal` is generally more appropriate than `double`.

~~~java
BigDecimal first = new BigDecimal("0.10");
BigDecimal second = new BigDecimal("0.20");
BigDecimal sum = first.add(second);
System.out.println(sum); // 0.30
~~~

Here, the strings `"0.10"` and `"0.20"` specify exact decimal numbers. It is crucial to **construct data properly right at the source**:

- `new BigDecimal("0.1")`: represents the exact decimal value 0.1.
- `BigDecimal.valueOf(0.1)`: uses the canonical string form `Double.toString(0.1)`, creating a `BigDecimal` equal to 0.1. Useful when receiving an existing `double` value while **not knowing the original decimal intent**.
- `new BigDecimal(0.1)`: takes the exact stored binary value of the `double` literal, not the exact decimal number 0.1 written in code.
- `BigDecimal.valueOf(0.1 + 0.2)`: becomes `0.30000000000000004`, **failing to recover the decimal addition 0.10 + 0.20**.

Therefore, converting to `BigDecimal` **after** errors have already arisen in `double` calculations does not guarantee recovering the value the user intended to enter. Whenever possible, parse original decimal strings directly or receive `BigDecimal` from a data layer with an exact contract, and perform calculations in `BigDecimal` from the start.

`BigDecimal` also needs division rules: `BigDecimal.ONE.divide(new BigDecimal("3"))` cannot represent a finite decimal quotient and will throw `ArithmeticException` unless an appropriate scale or `MathContext` is specified. A decimal type does not eliminate the need to design a rounding policy.

## 8. Errors Can Affect Both Comparisons and Algorithms

### Comparing Floating-Point Numbers

~~~java
double x = 0.1 + 0.2;
if (x == 0.3) {
    // This branch does not run in the example
}
~~~

Printing both values with `%.2f` can show `0.30` on both sides, even though `x == 0.3` is `false`. For **approximate comparison**, define a tolerance based on units and value domain. A simple example for finite numbers whose magnitudes are not overly large:

~~~java
static boolean nearlyEqual(double a, double b, double eps) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(eps) || eps < 0.0) {
        return false;
    }
    return Math.abs(a - b) <= eps;
}
~~~

This is an **illustrative method** to be placed inside a class. For numbers of very large or very small magnitude, subtraction can lose information or overflow; relative tolerance or ULP-based checks may be more suitable depending on the problem. Do not use an epsilon-based comparator in `TreeSet`/`TreeMap`, because "near equality" may not be transitive, violating the ordering contract.

### Loss of Precision Due to Cancellation

Formatting also cannot rescue information lost when adding/subtracting numbers of widely differing magnitudes:

~~~java
double large = 1e16;
double difference = (large + 1.0) - large;
System.out.println(difference); // 0.0, not 1.0
~~~

At magnitude `1e16`, a change of `1.0` is too small to be represented as a distinct `double` at the addition step. The subsequent subtraction has no way to recover the rounded-away information. Printing `0.000000` instead of `0.0` only alters the text written for the result.

This is why you must separate **pretty number display** from **numerically stable algorithms**: error and operation order must be evaluated right in the computation design.

## 9. Choosing the Approach Based on Purpose

| Purpose | Suitable choice | What must be checked |
| --- | --- | --- |
| Printing readable numbers for users only | `String.format`, `printf`, `DecimalFormat` | Locale, digit count, formatting rules |
| Sending values for round-trip without arbitrary truncation loss | `Double.toString` or a round-trip-guaranteed format | Corresponding parsing, NaN/Infinity if present |
| Comparing close floating-point results | Tolerance with a clear contract | Value range, finiteness, numerical error, absolute/relative |
| Storing values quantized to decimal steps | `BigDecimal` and `setScale(..., RoundingMode)` | Scale, rounding policy, data source |
| Decimal monetary calculations | `BigDecimal` from original strings or standard decimal data | Do not pass through `double` computations that introduce prior error |
| Measurements/science tolerating error | `double`/`float` + error control | Stability, range, overflow/underflow |

**Exporting data also requires care:** If one system exports a `double` as a two-digit string and another system parses it back, that is **changing the precision of the exchanged data**. It may be an intentional product decision, yet it is no longer transmitting the exact original value intact. In particular, resolution finer than `0.01` can be lost.

## 10. Common Pitfalls

1. **Assuming the string `"0.30"` proves `sum == 0.3`.** Two values can print identically while differing in their low-order bits.
2. **Overwriting logs with a rounded string and losing diagnostic capability.** When debugging numerical errors, also log a sufficiently precise form (`Double.toString`, bits if needed) or the raw input.
3. **Formatting then parsing to "fix" error.** This actively discards information and still yields an approximate `double`.
4. **Equating `Math.round` with formatting.** `Math.round` actually computes a new value, yet keeps a binary type if the final result is `double` and does not fit all decimal rules.
5. **Passing `new BigDecimal(double)` and assuming you get the decimal the user entered.** This constructor preserves **the exact binary representation** of the argument; an original decimal string source is needed if exact decimals are desired.
6. **Adjusting only displayed digits to address accumulated error.** Errors may have already affected `if` branches, thresholds, sums, and averages prior to formatting.
7. **Using printed digit count as proof of business accuracy.** Two decimal places on an invoice require consistently defined billing, rounding, summation, and tax policies.
8. **Failing to specify locale and machine-readable output.** Separators, digit grouping, and special values can cause misparsing if two systems use different conventions.

## 11. Self-Check Questions

1. If `double x = 0.1 + 0.2;` and `String.format(Locale.ROOT, "%.2f", x)` produces `"0.30"`, does `x == 0.3` become `true`?
2. Does `Double.parseDouble("0.30")` necessarily store the exact same binary value currently in `0.1 + 0.2`?
3. After `double y = Math.round(x * 100) / 100.0;`, has `y` become an exact decimal number?
4. Do `new BigDecimal(0.1)` and `new BigDecimal("0.1")` represent the exact same decimal number?
5. When must `BigDecimal` be used from the data source, and when is `double` with error control still reasonable?

**Answers:** (1) No; formatting does not modify `x`, so the comparison remains `false`. (2) No; parsing the short string produces the bit pattern for the `0.3` literal, which differs from the bits of `0.1 + 0.2`. (3) Not yet: the result is a new `double`, which may be close to a round decimal number yet remains an approximate binary representation. (4) No; the `double` constructor reflects the exact binary value near 0.1, while the string constructor represents the decimal number 0.1. (5) Use `BigDecimal` when decimal arithmetic and explicit scale/rounding policies are required; `double` fits many measurements, scientific computations, and algorithms where error is controlled.

## References

- [Java Language Specification `4.2.3 — Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3).
- [Java SE 21 API — Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html): `toString`, `parseDouble`, and floating-point values.
- [Java SE 21 API — Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html): floating-point format specifiers, precision, and locale.
- [Java SE 21 API — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): `String`/`double` constructors, `valueOf`, `setScale`.
- [Java SE 21 API — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): rounding rules.
