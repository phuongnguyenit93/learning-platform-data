# Distinguishing Display Precision from Underlying Numeric Values in Java

## Objectives

When a Java application displays monetary amounts, ratios, scores, or measurement results, we often want to **display fewer digits** for readability. For instance, a calculation yields `12.3456`, while the UI only shows `12.35`. We must clearly distinguish:

- **Underlying numeric value**: data stored in a `double`, `float`, or `BigDecimal` variable, or produced by a calculation.
- **Display precision**: the number of digits chosen when creating a display string, via `String.format`, `System.out.printf`, or a similar formatter.
- **Rounding the value for further use**: an actual numeric operation producing a new numeric value under a rounding rule, e.g., `BigDecimal.setScale(..., RoundingMode.HALF_UP)`.

**Formatting to two digits after the decimal point does not alter the underlying numeric variable.** The formatted result is a `String`; rounding operations are a separate matter and require selecting rules suited to the business logic.

This lesson focuses on Java Core, string formatting, especially the `%.2f` format specifier and its meaning compared to the value held in memory.

## 1. First Example: Number Stays Intact, String Is Shortened

```java
import java.util.Locale;

double original = 12.3456;

String displayed = String.format(Locale.US, "%.2f", original);

System.out.println("Original: " + original);
System.out.println("Displayed: " + displayed);
System.out.println("Still original: " + original);
```

Output:

```text
Original: 12.3456
Displayed: 12.35
Still original: 12.3456
```

Analysis:

1. `original` has type `double`; `String.format` reads this value to build text.
2. The specifier `%.2f` requests a fixed-point decimal floating-point representation with **two digits after the decimal separator**.
3. `displayed` is the string `"12.35"`, not a new `double`.
4. The variable `original` was not reassigned, so it continues to be used in subsequent calculations at the precision stored by `double`.

**Note on `double`:** the decimal number `12.3456` is not necessarily represented with exact precision in IEEE 754 binary. The fact that `Double.toString` prints `12.3456` means it outputs a short decimal form that converts back to the same `double` value, not proof that the bits in memory encode that exact decimal fraction. Still, the formatting operation does not modify the bits of `original`.

## 2. Meaning of `%.2f`, `%8.2f`, and `%.3g`

Methods in the `java.util.Formatter` family use `%` syntax to describe how a value is represented.

Examples:

```java
String a = String.format(Locale.US, "%.2f", 12.3456);
String b = String.format(Locale.US, "%8.2f", 12.3456);
String c = String.format(Locale.US, "%.3g", 12345.678);
```

Comparison table:

| Format | Meaning | Example Output |
| --- | --- | --- |
| `%.2f` | Fixed-point decimal format, two digits after separator | `12.35` |
| `%.0f` | Fixed-point decimal format, no digits after separator | `12` for `12.3456` |
| `%8.2f` | Like `%.2f`, but minimum field width is eight characters | `"   12.35"` |
| `%.3e` | Scientific notation, three digits after separator in mantissa | `1.235e+01` for `12.3456` |
| `%.3g` | General format with three **significant digits** | `1.23e+04` for `12345.678` |

For the `f` conversion, *precision* is the number of digits after the decimal separator. For `g`, *precision* denotes the number of significant digits. For `e`, it is the number of digits after the separator in the mantissa of scientific notation. You cannot interpret every specifier type with the same rule.

For example, `%8.2f` has two different formatting parameters: `8` is the **minimum display width**, while `2` is the precision after the decimal point. A width smaller than the displayed output will not cause Java to silently truncate arithmetic digits.

`%.2f` rounds to build the string rather than truncating characters. The value `12.3456` becomes `12.35`, not `12.34`. Rounding behavior at exact half-way cases should be examined carefully when the input comes from binary floating-point numbers.

### The `%d` Specifier Has No `%.2f`-Style Precision

`%d` is for integers. In Java Formatter, do not write `%.2d` to ask for "a two-digit integer"; precision is not supported for the integer `d` conversion. If you want leading zeros, one way to write it is `%02d`:

```java
String padded = String.format(Locale.US, "%02d", 7);
System.out.println(padded); // 07
```

The number `7` is still integer 7; `07` here is a **formatted string**, suitable for displaying fixed-width codes as needed.

## 3. Three Distinct Operations to Differentiate

| Operation | Output Data Type | Modifies Original Variable? | Creates Rounded Numeric Value for Further Math? |
| --- | --- | --- | --- |
| `String.format(Locale.US, "%.2f", x)` | `String` | No | No |
| `System.out.printf("%.2f", x)` | Writes formatted string to output | No | No |
| `BigDecimal.setScale(2, mode)` | New `BigDecimal` | No, because `BigDecimal` is immutable | Yes |
| `Math.round(x)` with `double x` | `long` | No | Yes, but rounds to an integer |
| `new BigDecimal("12.3456")` | `BigDecimal` | No | Decimal representation constructed from string, scale not yet reduced |

The key is to look at **what you need to do with the result**. If you only need to display a report with two decimal places, producing a `String` is usually sufficient. If business rules require locking amounts to cents, persisting converted amounts, or performing further math on rounded values, create an appropriate numeric value and choose a `RoundingMode` intentionally.

Do not parse a formatted string back into a number with `Double.parseDouble` just to round: this mixes presentation responsibilities with computation and can fail depending on locale (e.g., string `12,35`).

## 4. `BigDecimal`: Controlling Decimal Values and Rounding Rules

Financial problems or exact decimal rules typically require `BigDecimal` rather than relying on monetary calculations with `double`.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal original = new BigDecimal("12.3456");
BigDecimal rounded = original.setScale(2, RoundingMode.HALF_UP);

System.out.println(original); // 12.3456
System.out.println(rounded);  // 12.35
System.out.println(original); // 12.3456
```

In the example, the constructor from a **decimal string** preserves the exact value `12.3456`. Calling `setScale(2, RoundingMode.HALF_UP)` creates **a new numeric object** with two digits after the decimal point, rounded under the selected mode. `BigDecimal` is immutable: the `original` variable is not modified.

### Distinguishing `HALF_UP` and `HALF_EVEN`

Rounding modes are business rules, especially when a value lies **exactly halfway between two possible outcomes**:

```java
BigDecimal sample = new BigDecimal("2.345");

System.out.println(sample.setScale(2, RoundingMode.HALF_UP));
System.out.println(sample.setScale(2, RoundingMode.HALF_EVEN));
```

Output:

```text
2.35
2.34
```

When rounding to two digits, `2.345` is halfway between `2.34` and `2.35`. `HALF_UP` rounds away from zero on exact halves; `HALF_EVEN` picks the result whose last retained digit is even, which in this case is `2.34`.

Do not infer business rounding modes solely from what `%.2f` displays. If accounting policy mandates `HALF_EVEN`, `HALF_UP`, or another mode, enforce that policy on numeric values using `BigDecimal`.

### Why Avoid `new BigDecimal(double)` for Fixed Decimals

`double` stores a binary value close to the decimal digits written by the user. The constructor `new BigDecimal(1.005)` converts the **exact binary value of the double** into decimal form, which can produce a long and unexpected result.

If the source is a decimal string, use `new BigDecimal("1.005")`. If the source is already a `double` and you need the decimal representation per `Double.toString`, `BigDecimal.valueOf(double)` is usually more appropriate than the constructor taking `double` directly. Even so, `valueOf` cannot recover exact precision already lost in earlier binary operations.

When monetary calculations are required, keep data in an appropriate `BigDecimal` from input onward and define clear rounding points. Do not create rounded numbers by repeatedly transforming display strings.

## 5. `Locale` Only Changes Presentation Conventions

A numeric value can be written differently by country:

```java
double amount = 12345.678;

String us = String.format(Locale.US, "%,.2f", amount);
String de = String.format(Locale.GERMANY, "%,.2f", amount);

System.out.println(us);
System.out.println(de);
```

Output:

```text
12,345.68
12.345,68
```

Explanation:

- With `Locale.US`, commas group thousands and a dot separates the decimal part.
- With `Locale.GERMANY`, dots group thousands and a comma separates the decimal part.
- `%,.2f` enables digit grouping (`,`) and chooses two decimal digits (`.2`).

Both formats read the same `double amount`. Changing separators does not alter the value stored in the variable.

**Recommendation on API contracts:** Human-facing output should use an appropriate `Locale`. Data exchanged between systems should use representations defined by the transfer standard (such as JSON numbers per JSON syntax) or a schema specifying exact type, precision, and locale. Do not store `"12.345,68"` directly in a numeric API field and expect `Double.parseDouble` to interpret it properly.

`String.format("%.2f", value)` without `Locale` uses the default locale. If results are used in tests, structured logs, or interchange data needing stability, specify `Locale.US` or a locale matching the output standard instead of depending on the host machine.

## 6. Choosing When to Round: Before or After Calculation?

Suppose you need to sum three values of `0.333`. There are two non-equivalent strategies:

1. **Preserve input precision**, add the three values, then round the result: `0.333 + 0.333 + 0.333 = 0.999`, which rounds to two digits as `1.00`.
2. **Round each value before summing**: each `0.333` becomes `0.33`, then the sum becomes `0.99`.

Example using `BigDecimal` to avoid binary drift:

```java
BigDecimal each = new BigDecimal("0.333");

BigDecimal roundAtEnd = each.add(each).add(each)
        .setScale(2, RoundingMode.HALF_UP);

BigDecimal roundBeforeSum = each.setScale(2, RoundingMode.HALF_UP)
        .multiply(new BigDecimal("3"));

System.out.println(roundAtEnd);       // 1.00
System.out.println(roundBeforeSum);   // 0.99
```

You cannot decide which rule is right solely from display formatting. For invoices, taxes, statistics, or measurements, rounding per line vs. on the total is a **business requirement**. APIs must specify rounding points, decimal places, and `RoundingMode`, because they can change actual outcomes.

If you only want to display two digits at each step while keeping the original number for further math, you can format each value for the UI while still computing the total from the unrounded values. Clearly separate "displayed numbers" from "numbers used in calculations."

## 7. Complete Runnable Java 17+ Example

Create a file **`PrecisionPresentationDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public class PrecisionPresentationDemo {
    public static void main(String[] args) {
        double original = 12.3456;
        String displayed = String.format(Locale.US, "%.2f", original);

        System.out.println("Original: " + original);
        System.out.println("Displayed: " + displayed);
        System.out.println("Still original: " + original);
        System.out.println(
                "Width: [" + String.format(Locale.US, "%8.2f", original) + "]"
        );

        double quantity = 12345.678;
        System.out.println(
                "US: " + String.format(Locale.US, "%,.2f", quantity)
        );
        System.out.println(
                "Germany: " + String.format(Locale.GERMANY, "%,.2f", quantity)
        );

        BigDecimal amount = new BigDecimal("12.3456");
        BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);

        System.out.println("Decimal original: " + amount);
        System.out.println("Decimal rounded: " + rounded);
        System.out.println("Decimal original again: " + amount);

        BigDecimal halfway = new BigDecimal("2.345");
        System.out.println(
                "Half up: " + halfway.setScale(2, RoundingMode.HALF_UP)
        );
        System.out.println(
                "Half even: " + halfway.setScale(2, RoundingMode.HALF_EVEN)
        );
        System.out.println(
                "Significant: " + String.format(Locale.US, "%.3g", quantity)
        );
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 PrecisionPresentationDemo.java
java PrecisionPresentationDemo
```

Displayed output:

```text
Original: 12.3456
Displayed: 12.35
Still original: 12.3456
Width: [   12.35]
US: 12,345.68
Germany: 12.345,68
Decimal original: 12.3456
Decimal rounded: 12.35
Decimal original again: 12.3456
Half up: 2.35
Half even: 2.34
Significant: 1.23e+04
```

Each line proves a point:

- `Original` and `Still original` match; only `Displayed` uses lower display precision.
- `Width` adds three leading spaces to reach a minimum width of eight characters; this does not change the numeric value.
- `US` and `Germany` use the same number with locale-specific separators.
- `BigDecimal.setScale` produces a separate rounded decimal value, while keeping the original numeric object intact.
- `HALF_UP` and `HALF_EVEN` yield different results at the exact midpoint.
- `%.3g` takes three significant digits and may use scientific notation; it differs from requesting three digits after the decimal point.

## 8. Real-World Scenarios and How to Handle Them

| Need | Approach | Reason |
| --- | --- | --- |
| Display an average score to two digits | `String.format(locale, "%.2f", average)` | Only changes the output string |
| Print a table with neatly aligned number columns | `%8.2f` or `%-8.2f` | Width/alignment is a presentation requirement |
| Store a price locked to two decimal places | `BigDecimal.setScale(2, roundingMode)` per business rules | A new numeric value chosen intentionally |
| Compute a ratio and display as a percentage | Compute the ratio, convert to percentage units if needed, then format | `%.2f` by itself does not multiply by 100 |
| Display across multiple locales | Format the same numeric value with the appropriate locale | Decimal and grouping separators are language conventions |
| Write numbers into machine-readable data | Use a schema/serializer with a defined number representation | UI-formatted strings may not parse uniformly |
| Compare calculation results | Use numeric values and define epsilon/precision as required | Identical display strings do not prove numeric equality |

### Two Different Numbers Can Display Identically

```java
double a = 1.231;
double b = 1.234;

System.out.println(String.format(Locale.US, "%.2f", a)); // 1.23
System.out.println(String.format(Locale.US, "%.2f", b)); // 1.23
System.out.println(a == b);                              // false
```

Both displayed strings are `"1.23"`, yet the underlying numeric values are unequal. Therefore, never infer `a == b` from two UI cells showing identical two-decimal text.

Conversely, differing displays due to locale do not mean the numbers differ. When designing tests, separate **formatting tests** (comparing strings under a fixed locale) from **calculation tests** (comparing values, tolerances, or `BigDecimal` values as required).

### Two Different-Looking Strings Can Represent the Same Value

For example, `"12.30"` and `"12.3"` are two distinct `String`s. When interpreted under the same decimal convention, both represent the numeric value 12.3. For `BigDecimal`, `equals` also considers scale; `new BigDecimal("12.30").equals(new BigDecimal("12.3"))` is `false`, whereas `compareTo` returns 0. Choosing value-based vs. representation-based equality must match the API contract.

## 9. Common Mistakes

1. **Assuming `String.format("%.2f", value)` rounds the variable `value`.** It returns a new string. If you continue calculating, `value` remains unchanged.
2. **Calling every specifier precision "decimal places".** For `f`, it is digits after the decimal point; for `g`, it is significant digits.
3. **Confusing width with precision.** `%8.2f` has width 8 and precision 2; width does not limit the significant digits of the value.
4. **Using `%.2f` for business monetary rounding.** If the rounded value must be stored or used in further calculations, define an explicit numeric type and rounding policy.
5. **Using `new BigDecimal(double)` when the source is user-entered decimal text.** It preserves the binary value of `double`, which may differ from decimal expectations. Prefer constructing from a validated string or a `BigDecimal` source.
6. **Using `Math.round` expecting two decimal places.** For `double`, `Math.round` returns an integer `long`; multiplying and dividing by powers of 10 easily introduces binary floating-point error.
7. **Ignoring `Locale`.** Different environments can render different separators, making string comparisons or reverse parsing unstable.
8. **Rounding individual components when business rules require rounding the total.** Final results can differ, as in the `0.333` example.
9. **Comparing numbers via formatted strings.** Two different numbers can both display as `1.23`, and the same number can appear differently in two locales.

## 10. Self-Check

**Question 1.** Given `double price = 19.999;`. After `String label = String.format(Locale.US, "%.2f", price);`, what is the type of `label`? Does `price` become 20.00?

**Answer:** `label` has type `String`, with content `"20.00"`. `price` remains the exact same `double` value as before the call.

**Question 2.** How does `%.3f` differ from `%.3g`?

**Answer:** `%.3f` requests three digits after the decimal separator in fixed-point form; `%.3g` requests three significant digits in general form.

**Question 3.** Why is `BigDecimal.setScale(2, RoundingMode.HALF_EVEN)` not the same as just printing with `%.2f`?

**Answer:** `setScale` returns a new `BigDecimal` numeric object rounded with an explicit mode. `%.2f` only creates a presentation string per formatter rules and does not modify the passed numeric value.

**Question 4.** Why should you not take the string `"12.345,68"` (German locale) and pass it straight into `Double.parseDouble`?

**Answer:** `Double.parseDouble` accepts decimal syntax without German-style grouping separators; this string does not match and will throw `NumberFormatException`. If you must read locale-formatted numbers, use a locale-appropriate parser and clarify the data contract.

**Question 5.** `0.333` is recorded three times. Is rounding each number to `0.33` and adding them the same as adding them to `0.999` and then rounding?

**Answer:** No. The first case yields `0.99`, while the second yields `1.00` when rounding to two digits with `HALF_UP`. Follow the business specification.

## Key Takeaways

**Display precision is a rule for converting a numeric value into a `String`; it is not synonymous with underlying numeric precision or calculation rounding policy.** Use `String.format`/`printf` for display, use `BigDecimal` and `RoundingMode` when a rounded decimal value is genuinely required, and pass an explicit `Locale` whenever separator conventions matter.
