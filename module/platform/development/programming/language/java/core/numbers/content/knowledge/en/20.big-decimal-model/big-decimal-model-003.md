# `BigDecimal`: Precision Differs from Scale in Java

## 1. Understanding the Two Most Important Properties

In Java, `java.math.BigDecimal` represents **exact base-10** decimal numbers using an arbitrary-length integer (*unscaled value*) and an integer `scale`. `BigDecimal` does not automatically mean "infinite precision in every division": rounding and result precision must be controlled when a calculation has no finite decimal representation or when the application specifies a digit count.

Two concepts are very easily confused:

- **Precision (`precision()`):** the number of decimal digits in the unscaled integer value, counted from the first non-zero digit; for an unscaled integer value of 0, precision is defined as **1**.
- **Scale (`scale()`):** the decimal exponent used to place the decimal point according to `unscaledValue × 10^(-scale)`. `scale` can be **positive, zero, or negative**. In ordinary decimal notation without an exponent, a positive scale typically corresponds to the number of digits after the decimal point retained in the representation.

Example:

```java
BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount.precision());     // 7
System.out.println(amount.scale());         // 4
System.out.println(amount.unscaledValue()); // 1234500
```

The number `123.4500` has seven significant digits in the unscaled integer part: `1`, `2`, `3`, `4`, `5`, `0`, `0`; the decimal point stands before the last four digits, so `scale = 4`.

**Key takeaway:** `precision` is not "the number of digits after the decimal point"; `scale` is not "overall accuracy". They describe **two different properties** of a `BigDecimal` value.

## 2. Mathematical Model: `unscaledValue × 10^(-scale)`

Conceptually, a `BigDecimal` carries:

\[
\text{value}=\text{unscaledValue}\times 10^{-\text{scale}}.
\]

Here `unscaledValue()` returns `BigInteger`; `scale()` returns `int`. The decimal model separates the **signed integer coefficient** and the **decimal point position**.

Examples:

| Creation | Unscaled value | Scale | Decimal value |
| --- | ---: | ---: | --- |
| `new BigDecimal("123.4500")` | `1234500` | `4` | `123.4500` |
| `new BigDecimal("0.0012300")` | `12300` | `7` | `0.0012300` |
| `new BigDecimal("1000")` | `1000` | `0` | `1000` |
| `new BigDecimal("1E+3")` | `1` | `-3` | `1000` |
| `new BigDecimal("1.20E+3")` | `120` | `-1` | `1200` |
| `new BigDecimal("0.000")` | `0` | `3` | `0.000` |

Example `new BigDecimal("1E+3")`:

\[
1\times10^{-(-3)}=1\times10^3=1000.
\]

Therefore, a negative scale is **not an error** and does not mean a negative number: it indicates that the integer coefficient should be multiplied by a positive power of 10.

### How Does `precision()` Count?

Precision is generally the number of decimal digits of the **absolute unscaled value**, ignoring insignificant leading zeros. For `1234500`, precision is 7; for `12300`, precision is 5. Trailing zeros **are still counted** if they exist in the unscaled representation.

For `0`, Java defines precision as 1, not 0:

```java
System.out.println(new BigDecimal("0").precision());     // 1
System.out.println(new BigDecimal("0.000").precision()); // 1
```

Even though the representation `"0.000"` has three decimal digits after the dot, the unscaled value is 0 and precision remains 1. Do not mechanically infer `precision()` from the number of digits in the original string.

## 3. Examples Contrasting Precision and Scale

Read `precision()`, `scale()`, and `unscaledValue()` together rather than relying on how the number is printed on screen.

| Input string | `precision()` | `scale()` | `unscaledValue()` | Explanation |
| --- | ---: | ---: | ---: | --- |
| `"123.4500"` | 7 | 4 | 1234500 | The two trailing zeros are retained in unscaled |
| `"0.0012300"` | 5 | 7 | 12300 | Zeros before digit 1 do not increase precision |
| `"1000"` | 4 | 0 | 1000 | Four significant digits per representation |
| `"1E+3"` | 1 | -3 | 1 | Same value 1000, negative scale |
| `"1.20E+3"` | 3 | -1 | 120 | Same value 1200, three unscaled digits |
| `"0"` | 1 | 0 | 0 | Precision of zero is 1 |
| `"0.00"` | 1 | 2 | 0 | Scale keeps two decimal digits of representation |
| `"-0.000"` | 1 | 3 | 0 | `BigDecimal` has no separate negative zero |

Java code to inspect for yourself (place inside a method or in JShell):

```java
for (String text : new String[] {
        "123.4500", "0.0012300", "1000",
        "1E+3", "1.20E+3", "0", "0.00"
}) {
    BigDecimal x = new BigDecimal(text);
    System.out.printf(
            "%s -> unscaled=%s, precision=%d, scale=%d%n",
            text, x.unscaledValue(), x.precision(), x.scale());
}
```

`BigDecimal` remembers the value and scale, **not every exact character of the input string**. For instance, `"1.2300E+4"` creates the value `12300` with `scale = 0` and `precision = 5`; the original string formatting is not necessarily preserved to replay the exact same syntax.

### Why Can Precision Be Smaller Than Displayed Digits?

The string `"0.0012300"` has many characters and multiple zeros before the first non-zero digit. `precision()` does not count leading zeros of the decimal magnitude. It counts the digits of `unscaledValue=12300`, so it returns 5, while `scale=7`.

With exponent notation, `"1E+3"` has `precision=1` yet prints in full decimal form as `"1000"` with four digit characters. Precision is not the length of `toPlainString()`.

## 4. Two Equal Values with Different Precision and Scale

`BigDecimal` distinguishes between **equality by numerical value** and **equality by scaled representation**.

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.compareTo(b)); // 0
System.out.println(a.equals(b));    // false
```

Both represent the mathematical number 2, but:

| Variable | Unscaled | Precision | Scale |
| --- | ---: | ---: | ---: |
| `a = "2.0"` | 20 | 2 | 1 |
| `b = "2.00"` | 200 | 3 | 2 |

`compareTo` yields `0` because the two **numerical values** are equal. `equals` returns `false` because `BigDecimal.equals` requires both the same value and the same scale (hence requiring the corresponding unscaled value as well).

This differs from `BigInteger`, where `compareTo()==0` and `equals` are consistent with each other in value.

### Consequences for `HashSet` and `TreeSet`

```java
Set<BigDecimal> hash = new HashSet<>();
hash.add(new BigDecimal("2.0"));
hash.add(new BigDecimal("2.00"));

System.out.println(hash.size()); // 2
```

`HashSet` uses `equals`/`hashCode`, so it treats two objects with different scales as distinct elements.

```java
Set<BigDecimal> tree = new TreeSet<>();
tree.add(new BigDecimal("2.0"));
tree.add(new BigDecimal("2.00"));

System.out.println(tree.size()); // 1
```

`TreeSet` uses natural ordering via `compareTo`; two numbers with equal mathematical value are treated as the same key under that ordering. Do not use `BigDecimal` as a collection key without deciding whether the business logic needs to distinguish scales or only values.

### Do Not Use `==` to Compare Two BigDecimal Objects

`==` between two `BigDecimal` references only compares identity, not numeric value. Use `compareTo(...) == 0` to check for the same value **regardless of scale**, or `equals` if scale must also match. `BigDecimal.ZERO`, `BigDecimal.ONE`, and `BigDecimal.TEN` are convenience constants and do not turn `BigDecimal` into a primitive.

## 5. `setScale` Changes Decimal Position; `MathContext` Limits Precision

These two APIs serve two different purposes.

### 5.1. `setScale(int, RoundingMode)`

`setScale` requests a **target scale**:

```java
BigDecimal x = new BigDecimal("123.4500");

BigDecimal y = x.setScale(2, RoundingMode.UNNECESSARY);
BigDecimal z = x.setScale(6);

System.out.println(y); // 123.45
System.out.println(z); // 123.450000
```

Results:

| Value | Precision | Scale |
| --- | ---: | ---: |
| `x = 123.4500` | 7 | 4 |
| `y = 123.45` | 5 | 2 |
| `z = 123.450000` | 9 | 6 |

`setScale(6)` appends trailing zeros to fit the representation; **the mathematical value is unchanged**. Reducing scale may require dropping significant digits; in that case you must choose a `RoundingMode` or accept `ArithmeticException` if using `UNNECESSARY`.

Example:

```java
BigDecimal price = new BigDecimal("12.345");

System.out.println(price.setScale(2, RoundingMode.HALF_UP)); // 12.35
// price.setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: rounding would be necessary
```

As of Java 17, there is also the `setScale(int)` overload which by default requires no information loss from rounding. For scale-reduction operations that can lose digits, you should **explicitly pass a `RoundingMode`** per business policy.

`setScale` does not "set the total number of significant digits"; it specifies the **decimal exponent of the representation**. At negative scales, the rounding step corresponds to tens, hundreds, etc., rather than keeping digits after the decimal point.

### 5.2. `MathContext` Limits the Number of Significant Digits

`MathContext` configures the **maximum precision of the result** and the rounding mode used in calculations that accept a context:

```java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);
BigDecimal result = new BigDecimal("123.4500").round(mc);

System.out.println(result);             // 123
System.out.println(result.precision()); // 3
System.out.println(result.scale());     // 0
```

Here `MathContext(3, HALF_UP)` means using **at most three significant digits**, **not** three digits after the decimal point. Therefore `123.4500` rounds to `123` with `scale=0`, rather than `123.450`.

Comparison:

```java
BigDecimal x = new BigDecimal("123.4500");
System.out.println(x.setScale(3, RoundingMode.HALF_UP)); // 123.450
System.out.println(x.round(new MathContext(3, RoundingMode.HALF_UP))); // 123
```

The two results differ because the questions differ:

- `setScale(3, ...)` → wants a representation with **three decimal places**.
- `round(MathContext(3, ...))` → wants a result with **at most three significant digits**.

Do not substitute one for the other in billing, pricing, measurement, or scientific figures when the contract states a specific requirement.

### 5.3. Precision 0 of `MathContext` Is Not BigDecimal Precision 0

`MathContext.UNLIMITED.getPrecision()` returns `0`: in a **computation context**, precision 0 means **unlimited precision for the context**.

```java
System.out.println(MathContext.UNLIMITED.getPrecision()); // 0
System.out.println(BigDecimal.ZERO.precision());           // 1
```

That does **not** mean there is a valid `BigDecimal` with `precision() == 0` because it equals 0. The two APIs use the number 0 with **different meanings**.

A division like `1 / 3` has no finite decimal representation: even with unlimited precision, exact division cannot terminate in a finite number of digits. It will need a rounding rule or throw an exception; "unlimited" does not turn an infinite decimal into finite stored data.

## 6. Rounding Can Change Both Precision and Scale

Rounding by significant digits can produce a **carry**, shifting the exponent and scale in ways that are hard to predict by merely counting characters from a string.

```java
BigDecimal x = new BigDecimal("999.9");
BigDecimal rounded = x.round(new MathContext(3, RoundingMode.HALF_UP));

System.out.println(rounded);             // 1.00E+3
System.out.println(rounded.precision()); // 3
System.out.println(rounded.scale());     // -1
```

The mathematical result value is 1000, yet the representation is `unscaled=100`, `scale=-1`, precision 3. Converting it to `"1000"` for printing produces four digit characters, **without automatically making precision 4**.

Second example:

```java
BigDecimal x = new BigDecimal("0.0012345");
BigDecimal y = x.round(new MathContext(3, RoundingMode.HALF_UP));

System.out.println(y); // 0.00123
```

Here the three significant digits are `1`, `2`, `3` even though the display string contains several leading zeros; the `scale` of the result is 5.

### What Does RoundingMode Determine?

`RoundingMode.HALF_UP` rounds halves in the direction of increasing magnitude (away from 0); `HALF_EVEN` chooses the even digit at an exact midpoint, commonly used to reduce cumulative rounding bias; `DOWN` drops the discarded part towards 0; `UNNECESSARY` requires that no rounding is needed.

Example with positive numbers:

```java
BigDecimal x = new BigDecimal("1.235");
System.out.println(x.setScale(2, RoundingMode.HALF_UP));   // 1.24
System.out.println(x.setScale(2, RoundingMode.HALF_EVEN)); // 1.24
```

The two modes match in the example because the last kept digit is `3` before the midpoint? Let's look at the exact rule: when rounding `1.235` to two fractional digits, the first discarded digit is `5`, and the last kept digit is `3` (odd), so `HALF_EVEN` also rounds up to `1.24`. For `1.245`, `HALF_UP` gives `1.25` while `HALF_EVEN` gives `1.24` because the last kept digit `4` is even.

Do not assume `HALF_UP` or `HALF_EVEN` is universally right for every business case; the system's accounting or scientific rules must decide.

## 7. `stripTrailingZeros()`: Same Value, New Representation

The `stripTrailingZeros()` method removes trailing zeros in the unscaled representation by adjusting scale accordingly, keeping the **numerical value** unchanged.

```java
BigDecimal x = new BigDecimal("123.4500");
BigDecimal y = x.stripTrailingZeros();

System.out.println(y);             // 123.45
System.out.println(y.precision()); // 5
System.out.println(y.scale());     // 2
```

For a number with multiple trailing zeros in the integer part:

```java
BigDecimal x = new BigDecimal("1000.00");
BigDecimal y = x.stripTrailingZeros();

System.out.println(y);             // 1E+3
System.out.println(y.precision()); // 1
System.out.println(y.scale());     // -3
```

This is a very instructive transformation: **scale can become negative even when the input string has no exponent notation at all**.

### The Case of Zero

```java
BigDecimal x = new BigDecimal("0.000");
BigDecimal y = x.stripTrailingZeros();

System.out.println(y);             // 0
System.out.println(y.precision()); // 1
System.out.println(y.scale());     // 0
```

A zero with a positive scale can be normalized to `BigDecimal.ZERO` with scale 0. Therefore, if the application must preserve `0.000` to indicate the resolution of a measuring device, do **not** automatically call `stripTrailingZeros()` before storing the representative data.

### Can It Be Used for Comparison?

You can intentionally normalize to a specific representation rule when wanting to use `BigDecimal` as a value-based key:

```java
BigDecimal canonical = value.stripTrailingZeros();
```

However, **do not apply it unconditionally** to prices, currencies, measurements, or data that needs to retain scale. If normalization is used, system components must agree on the rules, zero handling, output strings, and negative scales. Simply checking whether two numbers have the same mathematical value is usually clearer with `compareTo`.

## 8. Addition, Multiplication, Division: How Do Precision and Scale Change?

`BigDecimal` operations produce immutable `BigDecimal` results. The scale in a calculation does **not necessarily** equal an operand's scale or the precision the user expects.

### 8.1. Addition and Subtraction Without `MathContext`

For exact addition/subtraction without a context, the preferred scale is the **larger scale** of the two operands:

```java
BigDecimal a = new BigDecimal("1.20");  // scale 2
BigDecimal b = new BigDecimal("3.004"); // scale 3

BigDecimal sum = a.add(b);
System.out.println(sum);         // 4.204
System.out.println(sum.scale()); // 3
```

The precision of the result is derived from the actual unscaled value, **not simply the sum of the two operands' precisions**.

### 8.2. Multiplication Without `MathContext`

The preferred scale of exact multiplication is the **sum of the scales** of the two operands:

```java
BigDecimal a = new BigDecimal("1.20"); // scale 2
BigDecimal b = new BigDecimal("3.0");  // scale 1

BigDecimal product = a.multiply(b);
System.out.println(product);         // 3.600
System.out.println(product.scale()); // 3
```

Although the mathematical value is 3.6, the representation retains the scale from exact multiplication and has precision corresponding to its unscaled digits.

### 8.3. Division May Require Rounding Rules

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");
```

Exact division `one.divide(three)` throws `ArithmeticException` because the decimal result 1/3 is non-terminating repeating. Two different ways to bound it:

```java
BigDecimal byScale =
        one.divide(three, 2, RoundingMode.HALF_UP);
BigDecimal byPrecision =
        one.divide(three, new MathContext(3, RoundingMode.HALF_UP));

System.out.println(byScale);     // 0.33
System.out.println(byPrecision); // 0.333
```

The first result has **scale = 2**, precision = 2; the latter has **precision = 3**, scale = 3.

For operations with `MathContext`, Java applies the preferred scale and API rounding rules, so the result scale can differ from the exact operation's scale formula, especially when rounding or truncating digits is needed. If the final pipeline must keep a fixed 2 decimal places, call `setScale(2, ...)` per contract at the appropriate step, instead of treating `MathContext(2)` as synonymous with `scale=2`.

## 9. Reading/Writing `BigDecimal`: Do Not Lose Scale Unintentionally

### 9.1. Create from a Decimal String Instead of Arbitrary `double`

If the goal is to preserve exact decimal `"0.1"` and scale 1:

```java
BigDecimal exact = new BigDecimal("0.1");
System.out.println(exact.precision()); // 1
System.out.println(exact.scale());     // 1
```

Alternative:

```java
BigDecimal displayValue = BigDecimal.valueOf(0.1);
```

`BigDecimal.valueOf(double)` uses the decimal form from `Double.toString` of the existing binary value; for `0.1`, it usually produces `0.1`, scale 1.

Whereas:

```java
BigDecimal binaryExact = new BigDecimal(0.1);
System.out.println(binaryExact);
// 0.1000000000000000055511151231257827021181583404541015625
```

`new BigDecimal(double)` reflects **the exact binary value of `double`**, which does not equal the mathematical decimal number 0.1. Do not carelessly use the `double` constructor when ingesting money or decimal numbers from users. If the input has already undergone lossy `double` operations earlier, `valueOf(double)` cannot recover the original either.

### 9.2. `toString()` Can Output Scientific Notation

```java
BigDecimal x = new BigDecimal("1E+3");

System.out.println(x.toString());      // 1E+3
System.out.println(x.toPlainString()); // 1000
```

Both describe the same **mathematical value**, but when parsing `"1000"` with `new BigDecimal`, the scale will be 0, **not preserving scale -3** like the original `1E+3`. `BigDecimal.toString()` provides a canonical decimal representation that can recover the exact unscaled value and scale when parsed back; `toPlainString()` is meant for decimal display without exponents and does not promise to preserve negative scale after a round-trip.

If storing data where **scale is an important part of the schema**, choose a serialization format and database type that preserve scale by contract, instead of only outputting `toPlainString()` and expecting all metadata to be restored.

### 9.3. Working with Currency

Example:

```java
BigDecimal amount = new BigDecimal("12.3");
BigDecimal currencyValue = amount.setScale(2, RoundingMode.UNNECESSARY);

System.out.println(currencyValue); // 12.30
```

Here `precision` goes from 3 to 4 after adding a trailing zero, yet **the mathematical value does not change**. Keeping `scale=2` is a requirement to represent money with two decimal digits, **not** a requirement to keep only two significant digits.

If the initial value needs rounding, you must use `setScale(2, roundingMode)` per business rules. Do not apply `stripTrailingZeros()` to currency data that needs to output `"12.30"`; it will drop the trailing zero and change the scale.

## 10. Complete Java 17 Example

Create file `PrecisionVsScaleDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionVsScaleDemo {
    private static void describe(String label, BigDecimal value) {
        System.out.println(label + " = " + value
                + " | unscaled=" + value.unscaledValue()
                + " | precision=" + value.precision()
                + " | scale=" + value.scale());
    }

    public static void main(String[] args) {
        describe("amount", new BigDecimal("123.4500"));
        describe("small", new BigDecimal("0.0012300"));
        describe("integer", new BigDecimal("1000"));
        describe("scientific", new BigDecimal("1E+3"));
        describe("zero", new BigDecimal("0.000"));

        BigDecimal x = new BigDecimal("123.4500");
        describe("scale2", x.setScale(2, RoundingMode.UNNECESSARY));
        describe("scale6", x.setScale(6));
        describe("precision3",
                x.round(new MathContext(3, RoundingMode.HALF_UP)));

        BigDecimal carried = new BigDecimal("999.9")
                .round(new MathContext(3, RoundingMode.HALF_UP));
        describe("carry", carried);

        BigDecimal stripped = new BigDecimal("1000.00")
                .stripTrailingZeros();
        describe("stripped", stripped);

        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        System.out.println("equals 2.0 / 2.00: " + a.equals(b));
        System.out.println("compare 2.0 / 2.00: " + a.compareTo(b));

        BigDecimal byScale = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        BigDecimal byPrecision = BigDecimal.ONE.divide(
                new BigDecimal("3"),
                new MathContext(3, RoundingMode.HALF_UP));
        describe("divideScale2", byScale);
        describe("dividePrecision3", byPrecision);

        System.out.println("UNLIMITED context precision: "
                + MathContext.UNLIMITED.getPrecision());
        System.out.println("ZERO value precision: "
                + BigDecimal.ZERO.precision());

        BigDecimal inScientific = new BigDecimal("1E+3");
        System.out.println("scientific toString: "
                + inScientific.toString());
        System.out.println("scientific toPlainString: "
                + inScientific.toPlainString());
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac PrecisionVsScaleDemo.java
java PrecisionVsScaleDemo
```

Output:

```text
amount = 123.4500 | unscaled=1234500 | precision=7 | scale=4
small = 0.0012300 | unscaled=12300 | precision=5 | scale=7
integer = 1000 | unscaled=1000 | precision=4 | scale=0
scientific = 1E+3 | unscaled=1 | precision=1 | scale=-3
zero = 0.000 | unscaled=0 | precision=1 | scale=3
scale2 = 123.45 | unscaled=12345 | precision=5 | scale=2
scale6 = 123.450000 | unscaled=123450000 | precision=9 | scale=6
precision3 = 123 | unscaled=123 | precision=3 | scale=0
carry = 1.00E+3 | unscaled=100 | precision=3 | scale=-1
stripped = 1E+3 | unscaled=1 | precision=1 | scale=-3
equals 2.0 / 2.00: false
compare 2.0 / 2.00: 0
divideScale2 = 0.33 | unscaled=33 | precision=2 | scale=2
dividePrecision3 = 0.333 | unscaled=333 | precision=3 | scale=3
UNLIMITED context precision: 0
ZERO value precision: 1
scientific toString: 1E+3
scientific toPlainString: 1000
```

**Reading the three columns:** `unscaled`, `precision`, and `scale` are representation details; printed decimal numbers may use exponents. Some operations can change scale and precision **without changing the mathematical value**, whereas rounding operations can change the mathematical value as well.

## 11. Common Mistakes

1. **Thinking `precision()` is the number of digits after the decimal point.** `new BigDecimal("123.4500")` has precision 7, scale 4.
2. **Thinking scale is always non-negative.** `"1E+3"` has scale -3; `stripTrailingZeros()` can also produce a negative scale from an ordinarily written number.
3. **Counting leading zeros to infer precision.** For `"0.0012300"`, precision is 5, not the length of the digit string.
4. **Thinking 0 has precision 0.** Every `BigDecimal` value equal to 0 has precision defined as 1.
5. **Confusing `MathContext(2)` with `setScale(2)`.** One limits the number of significant digits; the other specifies the decimal point position.
6. **Believing `MathContext.UNLIMITED.getPrecision() == 0` means the BigDecimal result has precision 0.** The 0 in `MathContext` is a code for "unlimited precision".
7. **Reducing scale without choosing a `RoundingMode`.** If non-zero digits would be dropped, `setScale` without rounding can throw `ArithmeticException`.
8. **Using `equals` to check numerical equality while ignoring scale.** `"2.0"` and `"2.00"` have `compareTo == 0` but `equals == false`.
9. **Using `BigDecimal` as a `HashSet` and `TreeSet` key without understanding the difference.** `HashSet` relies on `equals`; `TreeSet` relies on `compareTo`.
10. **Calling `stripTrailingZeros` while still expecting to keep `"12.30"` or `"0.000"`.** The result can change scale and formatting.
11. **Thinking `BigDecimal` never needs rounding.** Dividing 1/3 must have a context or rounding rule; if exactness is requested where no finite decimal result exists, exact `divide` throws an error.
12. **Using `new BigDecimal(0.1)` to enter exact decimal 0.1.** This constructor reflects the binary value of double, not the mathematical decimal source.
13. **Using `toPlainString()` then parsing back and expecting to keep a negative scale.** `1E+3` becomes `"1000"` and will be parsed with scale 0.
14. **Assuming all trailing zeros have no business meaning.** In measurements and reporting, trailing zeros can express resolution rules; do not normalize them away when they need to be kept.
15. **Trying to measure precision via `value.toString().replace(...)`.** Exponent notation, minus signs, leading zeros, and negative scales make character counting wrong. Use the `precision()` API.
16. **Using `BigDecimal` as if it were a mutable primitive.** It is immutable; every `setScale`, `round`, `stripTrailingZeros`, `add`, etc. returns a result that must be retained when needed.
17. **Using scale to definitively infer the accuracy of a measurement.** Scale is a representation property, not proof that the source has low error or was calibrated to that many digits.
18. **Assuming precision always equals the exact limit of MathContext.** A result may have fewer digits than the threshold if the calculation does not require that many digits or trailing digits are reduced per API rules.

## 12. Exercises and Solutions

**Question 1.** What are the precision and scale of `new BigDecimal("123.4500")`?

**Answer:** Precision 7 and scale 4; unscaled value is 1234500.

**Question 2.** How many digits of precision does `new BigDecimal("0.0012300")` have? Why is the scale 7?

**Answer:** Precision 5 because the unscaled value is 12300; scale 7 because there are seven digits after the dot in the input representation.

**Question 3.** Are `new BigDecimal("1E+3")` and `new BigDecimal("1000")` equal according to `equals` and `compareTo`?

**Answer:** `compareTo` gives 0 because both have numeric value 1000; `equals` gives `false` because scale -3 and scale 0 differ.

**Question 4.** An application needs to display `12.3` as `12.30`. Should `MathContext(2)` be used?

**Answer:** No. Use `setScale(2, RoundingMode.UNNECESSARY)` to get scale 2 when no rounding is needed. `MathContext(2)` limits to two significant digits, not two decimal places.

**Question 5.** Why can `new BigDecimal("1000.00").stripTrailingZeros()` print `"1E+3"`?

**Answer:** Normalization removes trailing zeros in the unscaled representation, keeping the value 1000 while changing unscaled to 1 and scale to -3, so the canonical representation takes exponent form.

**Question 6.** For `new BigDecimal("999.9").round(new MathContext(3, HALF_UP))`, what are the resulting precision/scale?

**Answer:** The result is `1.00E+3`, precision 3, scale -1. The carry during rounding changes both decimal point placement and unscaled value.

**Question 7.** Why is `BigDecimal.ZERO.precision()` 1 while `MathContext.UNLIMITED.getPrecision()` is 0?

**Answer:** `precision()` of 0 uses the BigDecimal rule: 1. `MathContext` uses the configuration value 0 to indicate unlimited precision; the two APIs have different meanings.

**Question 8.** Two ways to compute `1 / 3`:

```java
BigDecimal a = BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.HALF_UP);
BigDecimal b = BigDecimal.ONE.divide(
        new BigDecimal("3"), new MathContext(3, RoundingMode.HALF_UP));
```

What are the results?

**Answer:** `a = 0.33` (scale 2, precision 2); `b = 0.333` (scale 3, precision 3).

**Question 9.** If you want to preserve the exact scale of a `BigDecimal` with a negative scale during serialization and re-parsing, should `toPlainString` be used?

**Answer:** Not if the round-trip is required to preserve both unscaled value and scale. `toPlainString` of `1E+3` prints `"1000"` and parses back with scale 0; use a serialization approach with a contract that preserves scale, such as the canonical string from `toString()` when appropriate.

**Question 10.** Does `BigDecimal("0.000")` have `precision = 3`? What happens after `stripTrailingZeros`?

**Answer:** No: precision = 1, scale = 3. After stripping, the zero value is normalized to scale = 0 and precision remains = 1.

**Summary:** `BigDecimal` stores `unscaledValue × 10^(-scale)`. `precision` tells the number of significant digits in the unscaled representation (zero has precision 1); `scale` determines the position of the decimal point and can be negative. Use `setScale` for a contractual number of decimal places, use `MathContext` for significant-digit limits, and remember that `equals` distinguishes scale while `compareTo` compares numeric value.