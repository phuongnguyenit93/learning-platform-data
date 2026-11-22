# Zero, Positive, or Negative Scale in the `BigDecimal` Model

`java.math.BigDecimal` stores decimal numbers **as an integer value without a decimal point and an integer `scale`**. Scale can be **positive, zero, or negative**. It is part of the data representation, not simply "how many digits are displayed after the dot".

In Java, the mathematical value of a `BigDecimal` is determined by:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

`unscaledValue()` returns `BigInteger`, and `scale()` returns `int`. Simply remembering the **negative exponent rule for scale** makes all three cases easy to understand:

| `unscaledValue` | `scale` | Calculation | Value |
|---:|---:|---|---:|
| 12345 | 2 | `12345 × 10^-2` | `123.45` |
| 12345 | 0 | `12345 × 10^0` | `12345` |
| 12345 | -2 | `12345 × 10^2` | `1234500` |
| -123 | 3 | `-123 × 10^-3` | `-0.123` |
| 1 | -3 | `1 × 10^3` | `1000` |

This modeling approach lets `BigDecimal` represent finite decimals **exactly**, avoiding the binary rounding errors common with `double`. This lesson focuses on the meaning of scale's sign, how to observe the representation, and the consequences of changing scale.

## 1. Positive Scale: Number of Digits to the Right of the Decimal Point

Example:

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount.unscaledValue()); // 1234500
System.out.println(amount.scale());         // 4
System.out.println(amount.precision());     // 7
```

This is an illustrative snippet meant to be placed in a method or JShell. The string `"123.4500"` has four digits after the decimal point, so `scale()` equals **4**. By the formula, `1234500 × 10^-4 = 123.4500`.

The two numbers `new BigDecimal("1.2")` and `new BigDecimal("1.20")` have **equal mathematical values**, yet have `scale` 1 and 2 respectively. Trailing zeros are preserved in the representation and can matter when data must record the exact representation or scale constraints.

A positive scale **does not guarantee** the value lies between -1 and 1. For example, `123.45` has scale 2, and `12345.67` also has scale 2. Scale is information about the decimal point's position relative to `unscaledValue`.

## 2. Zero Scale: Integers in the Decimal System

When `scale = 0`, the formula becomes:

\[
\text{value} = \text{unscaledValue} \times 10^0 = \text{unscaledValue}.
\]

Example:

```java
BigDecimal count = new BigDecimal("12345");
// count.unscaledValue() = 12345
// count.scale() = 0
// count.toPlainString() = "12345"
```

A `BigDecimal` with scale 0 represents an integer value; however, **not every `BigDecimal` with an integer value must have scale 0**:

- `new BigDecimal("100")` has scale 0.
- `new BigDecimal("100.0")` has scale 1.
- `new BigDecimal("1E+2")` has scale -2.
- All three represent the numeric value **100**.

Therefore, one must distinguish **the numeric value being an integer** from **a representation having scale equal to 0**.

## 3. Negative Scale: Representing Multiples of 10

When `scale < 0`, the exponent `-scale` is positive; `unscaledValue` is **multiplied** by a power of 10. Hence:

```java
BigDecimal x = new BigDecimal("1.23E+4");
// x.unscaledValue() = 123
// x.scale() = -2
// x.toPlainString() = "12300"
```

`1.23E+4` means `1.23 × 10^4 = 12300`. In fact, the internal representation has `unscaledValue = 123`, `scale = -2`, so `123 × 10^2 = 12300`.

This representation can be created directly:

```java
import java.math.BigInteger;

BigDecimal x = new BigDecimal(new BigInteger("123"), -2);
// x.scale() = -2
// x.toString() = "1.23E+4"
// x.toPlainString() = "12300"
```

This is an illustrative example and needs to be placed inside a method with proper imports. Do not interpret "negative scale" as "negative value": the sign of the number sits in `unscaledValue`, whereas the sign of scale controls the **power of 10**. A `BigDecimal` with scale -2 can still hold a positive, negative, or 0 number.

With scale -2, the values represented exactly from integer `unscaledValue`s are multiples of 100; with scale -3, multiples of 1000. For instance, 12345 cannot be kept with its exact value at scale -2 because 12345 is not divisible by 100.

## 4. `scale` Differs from `precision`

`scale()` and `precision()` do not describe the same property:

- `scale`: the negated exponent in the formula `unscaled × 10^-scale`, which can be negative, 0, or positive.
- `precision`: the number of **decimal digits in `unscaledValue`** (ignoring minus sign), calculated per `BigDecimal`'s definition; for 0, precision is 1.

| Value created from string | `unscaledValue` | `scale` | `precision` |
|---|---:|---:|---:|
| `"123.4500"` | 1234500 | 4 | 7 |
| `"12345"` | 12345 | 0 | 5 |
| `"1.23E+4"` | 123 | -2 | 3 |
| `"0.000"` | 0 | 3 | 1 |
| `"100.00"` | 10000 | 2 | 5 |

A number with a large positive scale does not mean precision must be large; for example, `0.0001` has scale 4 but precision 1. Conversely, a number with a negative scale can have small precision yet a very large value. When wanting to constrain the **number of significant digits** in an operation, Java provides `MathContext`; when wanting to specify **fractional digit positions**, the relevant API is typically `setScale`.

## 5. `setScale`: Changing Representation and Potential Rounding

`setScale(int newScale)` requests a result with a specific scale. If changing scale preserves the numeric value, Java returns a mathematically equivalent `BigDecimal`. If **reducing scale** forces dropping a non-zero portion of the value, the one-parameter version throws `ArithmeticException` (because no rounding mode was specified).

### Increasing Scale: Typically Adds 0 Digits

```java
BigDecimal price = new BigDecimal("1.23");
BigDecimal displayed = price.setScale(4);
// displayed.toPlainString() = "1.2300"
// displayed.unscaledValue() = 12300
// displayed.scale() = 4
// price.scale() remains 2
```

Moving from scale 2 to scale 4 multiplies `unscaledValue` by 100, while **preserving the numeric value 1.23**. Zero digits are added to the representation.

### Exact Scale Reduction

```java
BigDecimal whole = new BigDecimal("12300");
BigDecimal hundreds = whole.setScale(-2);
// hundreds.toString() = "1.23E+4"
// hundreds.toPlainString() = "12300"
// hundreds.unscaledValue() = 123
// hundreds.scale() = -2
```

Here 12300 is divisible by 100, so reducing scale from 0 to -2 loses no information. Similarly, `new BigDecimal("1.2300").setScale(2)` preserves the exact value 1.23 because it only drops trailing zeros.

### Inexact Scale Reduction: Must Choose a Rounding Rule

```java
BigDecimal number = new BigDecimal("12345");

// number.setScale(-2); // ArithmeticException
BigDecimal rounded = number.setScale(-2, java.math.RoundingMode.HALF_UP);
// rounded.toPlainString() = "12300"
```

Choosing scale -2 means rounding to the **hundreds place**, not "keeping negative two decimal digits". The value 12345 is closer to 12300 than 12400, so with `HALF_UP` the result is 12300. With `12350`, an exact midpoint between 12300 and 12400, `HALF_UP` yields **12400**.

`setScale(int, RoundingMode)` clearly expresses cases requiring rounding. Set the mode based on business rules: `HALF_UP`, `HALF_EVEN`, `DOWN`, `CEILING`, `FLOOR`, etc. A rounding call cannot determine the right billing, tax, or reporting policy on its own if the application has not defined **when** and **how** to round.

### Useful Scale Conversion Table

| Original value | Original scale | New scale | Result | Needs rounding? |
|---|---:|---:|---|---|
| `1.23` | 2 | 4 | `1.2300` | No |
| `1.2300` | 4 | 2 | `1.23` | No |
| `12300` | 0 | -2 | `1.23E+4` | No |
| `12345` | 0 | -2 | `1.23E+4` with `HALF_UP` | Yes |
| `12350` | 0 | -2 | `1.24E+4` with `HALF_UP` | Yes |
| `100` | 0 | 0 | `100` | No |

The table uses the standard `toString()` representation. With `toPlainString()`, the negative-scale results above are written as `"12300"` and `"12400"`.

## 6. `stripTrailingZeros`: Why Can Scale Become Negative?

The `stripTrailingZeros()` method removes trailing 0 digits in the representation while keeping the **numeric value**. It can cause `scale` to drop below 0.

```java
BigDecimal initial = new BigDecimal("100.00");
BigDecimal stripped = initial.stripTrailingZeros();

// initial: unscaled=10000, scale=2, toString="100.00"
// stripped: unscaled=1, scale=-2, toString="1E+2"
```

Explanation: `100.00 = 10000 × 10^-2 = 100`. After stripping all trailing zeros from `unscaledValue`, `1` remains; to still represent 100, the scale must be -2, because `1 × 10^2 = 100`.

A special case is 0:

```java
BigDecimal zero = new BigDecimal("0.000");
BigDecimal normalized = zero.stripTrailingZeros();
// normalized has scale=0, precision=1 and representation is "0"
```

This does not mean every initial 0 has scale 0: only **after** calling `stripTrailingZeros()` do we get the normalized representation in this example case.

## 7. `equals` and `compareTo`: Scale Affects Comparison Results

`BigDecimal.equals` requires both **numeric value** and **scale** to match. Meanwhile `compareTo` compares by **numeric value order**, ignoring scale representation differences.

```java
BigDecimal a = new BigDecimal("1.0");  // scale=1
BigDecimal b = new BigDecimal("1.00"); // scale=2

a.equals(b);          // false
a.compareTo(b) == 0;  // true
```

Therefore:

- Use `compareTo(...) == 0` when checking **mathematical value equality**.
- Use `equals(...)` when scale is a meaningful part of data equality.
- `hashCode()` follows the `equals` contract, so numerically equal `BigDecimal`s with different scales **can have different hashes**. If using them as keys in a `HashMap`/`HashSet`, decide on a normalization policy beforehand.
- `stripTrailingZeros()` can help normalize values for comparison or key creation, but alters representation scale; apply it only when consistent with the data contract.

Notably, `new BigDecimal("100")` and `new BigDecimal("1E+2")` have the same numeric value, yet scales 0 and -2 respectively, so `equals` is `false`, while `compareTo` returns 0.

## 8. `toString`, `toPlainString`, and Scientific Notation

When scale is negative, `BigDecimal.toString()` often represents the value using scientific notation:

```java
BigDecimal number = new BigDecimal("1.23E+4");

number.toString();      // "1.23E+4"
number.toPlainString(); // "12300"
number.scale();         // -2
```

`toString()` produces a canonical representation per `BigDecimal`'s rules and retains the information needed for round-tripping the representation. `toPlainString()` omits exponent notation and is often easier to display to users, but **does not automatically preserve negative scale metadata when parsed back from the string**:

```java
BigDecimal x = new BigDecimal("1E+3"); // scale=-3
BigDecimal y = new BigDecimal(x.toPlainString()); // scale=0
// x.compareTo(y) == 0, yet x.equals(y) == false
```

For stored data that must preserve scale, keep a suitable representation, or explicitly store `unscaledValue` and `scale`. Do not rely on plain decimal strings to recover a negative scale.

## 9. `movePointRight`, `movePointLeft`, and `scaleByPowerOfTen`

Decimal-point shifting methods are used when multiplying/dividing by a power of 10:

- `movePointRight(n)`: increases value by `10^n`, while ensuring the resulting scale is **non-negative**.
- `movePointLeft(n)`: divides value by `10^n`, also ensuring the resulting scale is **non-negative**.
- `scaleByPowerOfTen(n)`: multiplies value by `10^n`, primarily by adjusting `scale` to `scale - n`; the resulting scale **can be negative**.

Example with the same starting value:

```java
BigDecimal original = new BigDecimal("1.00"); // unscaled=100, scale=2

BigDecimal moved = original.movePointRight(3);
// moved.toPlainString() = "1000", scale=0

BigDecimal scaled = original.scaleByPowerOfTen(3);
// scaled.toString() = "1.00E+3", scale=-1
// scaled.toPlainString() = "1000"
```

The two results have the same **numeric value 1000**, yet different scales (0 and -1); `compareTo` deems them equal while `equals` does not. This is a difference that can affect storage, formatting, and data-equality logic.

Operations multiplying/dividing by large powers can require heavy resources or cause `ArithmeticException` if the computed scale exceeds the `int` range. Do not treat scale as a number that can grow/shrink infinitely without bounds.

## 10. Compilable and Runnable Java 17+ Example

Create file **`BigDecimalScaleDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class BigDecimalScaleDemo {
    static void show(String name, BigDecimal x) {
        System.out.println(name + ": " + x.toString()
                + " | plain=" + x.toPlainString()
                + " | unscaled=" + x.unscaledValue()
                + " | scale=" + x.scale()
                + " | precision=" + x.precision());
    }

    public static void main(String[] args) {
        show("positive", new BigDecimal("123.4500"));
        show("zero", new BigDecimal("12345"));
        show("negative", new BigDecimal("1.23E+4"));
        show("constructor", new BigDecimal(new BigInteger("123"), -2));

        show("raise scale", new BigDecimal("1.23").setScale(4));
        show("exact lower", new BigDecimal("12300").setScale(-2));
        show("strip", new BigDecimal("100.00").stripTrailingZeros());
        show("zero after strip", new BigDecimal("0.000").stripTrailingZeros());

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("equal objects: " + a.equals(b));
        System.out.println("same numeric value: " + (a.compareTo(b) == 0));

        try {
            new BigDecimal("12345").setScale(-2);
        } catch (ArithmeticException ex) {
            System.out.println("inexact setScale: ArithmeticException");
        }
        show("rounded", new BigDecimal("12350").setScale(-2, RoundingMode.HALF_UP));
        show("movePointRight", new BigDecimal("1.00").movePointRight(3));
        show("scaleByPowerOfTen", new BigDecimal("1.00").scaleByPowerOfTen(3));
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 BigDecimalScaleDemo.java
java BigDecimalScaleDemo
```

Stdout verified by compiling and running Java:

```text
positive: 123.4500 | plain=123.4500 | unscaled=1234500 | scale=4 | precision=7
zero: 12345 | plain=12345 | unscaled=12345 | scale=0 | precision=5
negative: 1.23E+4 | plain=12300 | unscaled=123 | scale=-2 | precision=3
constructor: 1.23E+4 | plain=12300 | unscaled=123 | scale=-2 | precision=3
raise scale: 1.2300 | plain=1.2300 | unscaled=12300 | scale=4 | precision=5
exact lower: 1.23E+4 | plain=12300 | unscaled=123 | scale=-2 | precision=3
strip: 1E+2 | plain=100 | unscaled=1 | scale=-2 | precision=1
zero after strip: 0 | plain=0 | unscaled=0 | scale=0 | precision=1
equal objects: false
same numeric value: true
inexact setScale: ArithmeticException
rounded: 1.24E+4 | plain=12400 | unscaled=124 | scale=-2 | precision=3
movePointRight: 1000 | plain=1000 | unscaled=1000 | scale=0 | precision=4
scaleByPowerOfTen: 1.00E+3 | plain=1000 | unscaled=100 | scale=-1 | precision=3
```

The program demonstrates the consistent relationship among the three pieces of information `unscaled`, `scale`, and `precision`. The `negative`/`constructor` lines illustrate two ways to construct the same negative-scale representation. The `strip` line shows that normalization can produce a negative scale; `zero after strip` shows the case where 0 is normalized to scale 0. The `equal objects`/`same numeric value` lines distinguish `equals` from `compareTo`. Finally, `movePointRight` and `scaleByPowerOfTen` produce the **same value** yet **different scales**.

## 11. Common Mistakes

1. **Assuming scale is always non-negative.** Strings in scientific notation like `"1E+3"` or `stripTrailingZeros()` can validly lead to a negative scale.
2. **Assuming a negative scale means a negative number.** A negative scale indicates multiplying by a positive power of `10`; the sign of the value is independent of the sign of scale.
3. **Confusing scale with precision.** `123.4500` has scale 4 yet precision 7; `1.23E+4` has scale -2 yet precision 3.
4. **Assuming an integer value must have scale 0.** `100`, `100.0`, and `1E+2` have the same numeric value yet scales 0, 1, and -2 respectively.
5. **Reducing scale while ignoring rounding.** `setScale(-2)` on `12345` throws `ArithmeticException`; if intentionally rounding to hundreds, specify `RoundingMode`.
6. **Misusing `equals` to compare mathematical values.** `1.0.equals(1.00)` is false; use `compareTo == 0` when checking value only.
7. **Using `toPlainString` for storage and expecting to recover negative scale.** Parsing `"1000"` back produces scale 0, unlike `"1E+3"` which has scale -3.
8. **Assuming `stripTrailingZeros` only reduces scale down to 0.** `100.00` normalizes to `1E+2` with scale -2.
9. **Mixing `BigDecimal` with `double` while ignoring representation.** `new BigDecimal(0.1)` creates the exact decimal corresponding to the rounded binary `double` value; to express exact decimal 0.1, use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)`.
10. **Inferring that every arithmetic operation's result scale matches an operand.** For example, with multiplication, the preferred scale of the result is the sum of the two operands' scales (aside from boundary/representation adjustment cases); other operations have their own rules. After calculating, read the actual `scale()` if it is part of the data contract.

## 12. Self-Check Exercises

Based on the formula `value = unscaled × 10^-scale`, determine the numeric value and `scale`:

| Question | Answer |
|---|---|
| What is the scale of `new BigDecimal("3.1400")`? | 4; unscaled is 31400 |
| What are the scale and value of `new BigDecimal("4E+3")`? | Scale -3; value 4000 |
| Does `new BigDecimal("150").setScale(-1)` succeed? | Yes; value 150; scale -1; `toString()` is `"1.5E+2"` |
| Does `new BigDecimal("155").setScale(-1)` succeed? | No; throws `ArithmeticException` without a rounding mode |
| What scale does `new BigDecimal("100.0").stripTrailingZeros()` have? | -2; value 100; representation `"1E+2"` |
| Do `"100.0"` and `"1E+2"` have `compareTo == 0`? | Yes, because both have numeric value 100 |
| Are the two values above `equals`? | No, because scale 1 differs from -2 |
| What does `new BigDecimal("0.000").precision()` return? | 1 |

To verify further on your own, try taking any `BigDecimal` and printing `toString`, `toPlainString`, `unscaledValue`, `scale`, and `precision`. Predict beforehand which values allow `setScale` to reduce exactly and which require rounding.

## Takeaways

- The foundational formula is **`value = unscaledValue × 10^-scale`**.
- **Positive** scale divides the integer representation by a power of 10; **0** scale leaves it unchanged; **negative** scale multiplies by a power of 10.
- Scale is part of the **representation**, not the number's sign or precision.
- `setScale` can preserve value or require rounding; `stripTrailingZeros` can produce a negative scale.
- `equals` checks scale as well; `compareTo` checks mathematical value.
- When negative scale must be preserved across storage, choose a representation that retains that information instead of relying solely on `toPlainString`.