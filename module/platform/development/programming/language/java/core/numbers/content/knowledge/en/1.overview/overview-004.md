# How Does Value Range Differ from Precision in Java?

The two concepts answer **two different questions**:

- **Value range:** What are the smallest and largest values a data type can represent? Does a calculation exceed the representable range?
- **Precision:** Within that range, how finely can the data type distinguish closely spaced values? How many significant digits are preserved during storage and computation?

A type with a very wide range can still have finite precision. In particular, `double` can represent numbers vastly larger than `int`, yet **it does not accurately represent every integer or every decimal number** within that range.

## 1. For Integers: Limited Range, Exact Representation Within Range

Java's primitive integer types use a fixed number of bits:

| Type | Bits | Value Range |
| --- | ---: | --- |
| `byte` | 8 | -128 to 127 |
| `short` | 16 | -32,768 to 32,767 |
| `int` | 32 | -2,147,483,648 to 2,147,483,647 |
| `long` | 64 | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 |

- Every **integer** value inside the type's range is stored exactly: `int` represents `1_000_000` and `1_000_001` as two distinct values.
- The limitation here is **range**, not a phenomenon of rounding a value that is still in range. Type `int` cannot hold an integer greater than `Integer.MAX_VALUE`.
- Primitive integer addition, subtraction, and multiplication can **overflow**: the result is computed modulo the type's bit width and can flip signs. Java does not automatically widen from `int` to `long` to keep the result; to compute in `long`, convert operands before the operation takes place.
- Use `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, or `Math.toIntExact` to detect overflow cases appropriately. For integers beyond 64 bits, consider `BigInteger`.

**Example:** `Integer.MAX_VALUE + 1` gives `-2_147_483_648` due to `int` overflow. This is not a rounding error from lacking decimal digits: the mathematical result exceeded the range of `int`.

> `char` also holds 16 unsigned bits (from `'\u0000'` to `'\uffff'`), but it is a **UTF-16 code unit** and should not be treated as an integer type for general arithmetic.

## 2. For Floating-Point Numbers: Wide Range Yet Finite Precision

`float` (32 bits) and `double` (64 bits) use IEEE 754 binary floating-point representation. Bits are allocated for **sign**, **exponent**, and **significand**:

- **Exponent** enables representing values spanning vastly different orders of magnitude; this is one reason floating-point range is wide.
- **Significand** contains finitely many bits and therefore can only represent a discrete set of values. Numbers lying between two representable values usually must be **rounded** to one of them.
- The spacing between two adjacent representable floating-point numbers (often called **ULP**, *unit in the last place*) **varies with magnitude**. Near large values, the spacing is larger; near 0, the spacing is generally smaller. In the *subnormal* region, relative precision decreases.

| Property | `float` | `double` |
| --- | --- | --- |
| Total bits | 32 | 64 |
| Effective significand bits of normal numbers | 24 | 53 |
| Commonly used decimal precision estimate | about 7 significant digits | about 15–16 significant digits |
| Largest finite magnitude | about `3.4028235E38` | about `1.7976931348623157E308` |
| Smallest nonzero positive (*subnormal*) | about `1.4E-45` | about `4.9E-324` |
| Every consecutive integer exact up to | `2^24 = 16_777_216` | `2^53 = 9_007_199_254_740_992` |

The milestones `2^24` and `2^53` state that **every integer in the respective interval is represented exactly**; they do not mean every larger integer is wrong. For example, even numbers near enough to `2^24` can still be stored exactly by `float`, whereas adjacent odd integers in between may not.

**Distinguishing "significant digits" from "digits after the decimal point":** For `double`, precision is approximately 15–16 **significant digits for the whole number**, not always 15–16 digits *after the decimal point*. The number `1_000_000_000_000_000` uses more significant digits than `1.0`; the distance to the next `double` depends on the order of magnitude.

Notes on Java constants:

- `Float.MAX_VALUE` / `Double.MAX_VALUE`: the **largest finite positive** number; the smallest finite negative number in numeric order is `-Float.MAX_VALUE` / `-Double.MAX_VALUE`.
- `Float.MIN_VALUE` / `Double.MIN_VALUE`: the **smallest nonzero positive** number, **not** the most negative number. `MIN_NORMAL` is the smallest *normal* positive number.
- `Float.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY`, and `NaN` are special values. They are not finite numbers lying between `-MAX_VALUE` and `MAX_VALUE`.

### Why Can a Very Large `double` "Ignore" `+1`?

`double` holds 53 bits of significand precision, yet must represent numbers up to roughly `10^308` in magnitude. Near `1.0E16`, two adjacent `double` numbers are spaced **2** apart; hence `1.0E16 + 1` rounds back to `1.0E16`. Meanwhile, near `1.0`, `Math.ulp(1.0)` is only about `2.22E-16`.

This is **loss of resolution**, not range overflow. Both `1.0E16` and `1.0E16 + 1` are tiny compared to `Double.MAX_VALUE`, yet `double` cannot retain those two values as two distinct numbers.

### Why Does `0.1 + 0.2` Not Equal Exact `0.3`?

Most decimal fractions, including `0.1`, have no finite binary representation. As soon as literals `0.1` or `0.2` are stored in `double`, the actual value is already an approximate binary number. After addition, the result is rounded again, so exact equality comparison:

`0.1 + 0.2 == 0.3`

returns `false`. **Floating-point range is not the issue here**: all three numbers are tiny and well inside the representable range. The issue is **representation precision and rounding**.

## 3. Hands-On Experiment: Observing Range, Overflow, Precision, and Decimal

Create the file `RangePrecisionDemo.java` (Java 17 or newer):

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class RangePrecisionDemo {
    public static void main(String[] args) {
        System.out.println("byte: " + Byte.MIN_VALUE + " .. " + Byte.MAX_VALUE);
        System.out.println("int: " + Integer.MIN_VALUE + " .. " + Integer.MAX_VALUE);
        System.out.println("int overflow: " + (Integer.MAX_VALUE + 1));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException e) {
            System.out.println("addExact: overflow detected");
        }

        float f = 16_777_216f;
        System.out.println("float keeps +1? " + (f + 1 == f));
        double d = 1e16;
        System.out.println("double keeps +1? " + (d + 1 == d));
        System.out.println("0.1 + 0.2 == 0.3? " + (0.1 + 0.2 == 0.3));
        System.out.println("ulp(1.0): " + Math.ulp(1.0));
        System.out.println("double infinity: " + Double.isInfinite(1e308 * 10));

        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.2");
        System.out.println("BigDecimal sum: " + a.add(b));
        BigDecimal x = new BigDecimal("123.4500");
        System.out.println("precision=" + x.precision() + ", scale=" + x.scale());
        BigDecimal thirds = BigDecimal.ONE.divide(
            new BigDecimal("3"), new MathContext(5, RoundingMode.HALF_UP));
        System.out.println("1 / 3 (5 digits): " + thirds);
    }
}
```

Compile and run:

```bash
javac RangePrecisionDemo.java
java RangePrecisionDemo
```

Output verified with JDK 21 (the program uses only APIs available since Java 17):

```text
byte: -128 .. 127
int: -2147483648 .. 2147483647
int overflow: -2147483648
addExact: overflow detected
float keeps +1? true
double keeps +1? true
0.1 + 0.2 == 0.3? false
ulp(1.0): 2.220446049250313E-16
double infinity: true
BigDecimal sum: 0.3
precision=7, scale=4
1 / 3 (5 digits): 0.33333
```

How to read the results:

1. `int overflow`: exceeded **range**; `Math.addExact` detects it with an exception rather than wrapping around.
2. `float keeps +1? true`: `16_777_216f + 1` rounds back to `16_777_216f`; `float` has not exceeded range, yet cannot preserve a step increment of 1.
3. `double keeps +1? true`: the same phenomenon happens with `double` at magnitude `10^16`.
4. `0.1 + 0.2 == 0.3? false`: the decimal calculation looks simple, yet the operands are in approximate binary form.
5. `Math.ulp(1.0)` measures the distance to the adjacent `double` near `1.0`.
6. `double infinity: true`: multiplication exceeding the largest finite number leads to `+Infinity`; this is **floating-point overflow**, distinct from rounding away `+1`.
7. `BigDecimal` sums the input decimals exactly. However, the division `1 / 3` has no finite decimal expansion, so precision and rounding rules must be chosen deliberately.

## 4. Are BigDecimal's Precision, Scale, and Rounding Like float/double?

`BigDecimal` stores an **unscaled integer** together with a `scale` (number of decimal digits in base-10 representation). It is not bound to fixed 24/53-bit binary precision like `float` and `double`:

- `new BigDecimal("123.4500").precision()` = `7`: there are seven digits in the unscaled integer `1234500`.
- `new BigDecimal("123.4500").scale()` = `4`: there are four positions after the decimal point in the stored representation.
- `precision` is **different from** `scale`. A value can have a large scale without having many significant digits, or vice versa.
- Without passing a `MathContext`, `BigDecimal` addition/subtraction/multiplication generally yields exact decimal results, subject to practical memory and scale limits. Dividing one number by another with an infinite decimal part, like `1 / 3`, requires specifying a `MathContext` or scale and `RoundingMode`; using `divide` requesting an exact result when it cannot terminate causes Java to throw `ArithmeticException`.
- When needing to round for displaying money with two decimal places, `amount.setScale(2, RoundingMode.HALF_UP)` can be used (just one rounding policy; business rules may require a different one).
- `new BigDecimal("0.1")` keeps the exact decimal `0.1`. `new BigDecimal(0.1)` instead receives the **approximate binary double value**; thus you should construct from `String` or a trusted decimal input form. `BigDecimal.valueOf(0.1)` uses the string representation of `double`, but cannot recover information already lost if data was rounded beforehand.

`BigDecimal.equals` also inspects scale: `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false`, whereas `compareTo` returns `0` because the two values are numerically equal. This is a matter of **representation and comparison semantics**, not a difference in range.

`BigInteger` solves the **integer range** problem when `long` is not enough; `BigDecimal` solves the **decimal representation and rounding control** problem. Both remain subject to practical resource limits.

## 5. Choosing the Right Data Type Based on Requirements

| Need | Suggestion | Reason |
| --- | --- | --- |
| Counts, indices, quantities within `int` range | `int` | Every valid integer is exact, compact cost |
| Integers larger than `int` range yet fitting `long` | `long` | Widens range; remember to compute with `long` operands before overflow |
| Integers larger than even `long` | `BigInteger` | No fixed 64-bit limit |
| Measurements, simulations, scientific calculations tolerating error | Usually `double` | Wider range and higher binary precision than `float` |
| Memory optimization for large real datasets when error is acceptable | `float` after evaluating error | 32-bit, though lower precision than `double` |
| Currency, taxes, prices, and decimal rounding rules | `BigDecimal`, with specified scale/rounding | Avoids inaccuracies from binary representation of `0.1`, `0.2` |
| Storing money in smallest unit, e.g., cents, when range permits | `long` or `int` | Exact integer; must specify unit and handle conversions |

When working with `double`/`float`, avoid `==` comparisons if the intent is "mathematically close" after calculation. Absolute and/or relative error can be used according to value range; the error threshold must derive from problem requirements. `Math.ulp(value)` is useful when wanting to understand the representation's resolution at a given value. Exception: exact comparison remains valid when that is the exact intended semantics (e.g., checking a directly assigned value or checking a special status flag).

## 6. Common Misconceptions

1. **"`double` has a wider range than `long` so it stores every `long` exactly."** False: from `2^53 + 1` onward, not every adjacent integer can be distinguished by `double`. Casting a large `long` to `double` can lose digits even without overflow.
2. **"`double` is exact to 16 decimal places after the decimal point."** False: it typically refers to about 15–16 **significant digits**, and resolution depends on magnitude.
3. **"`Double.MIN_VALUE` is the most negative number."** False: it is the smallest nonzero positive number; the lowest finite negative number is `-Double.MAX_VALUE`.
4. **"Computing `0.1 + 0.2` is wrong because it exceeded range."** False: that is representation/rounding error within range; floating-point overflow is what can produce `Infinity`.
5. **"Casting after the calculation avoids overflow."** False: `long result = (long) (Integer.MAX_VALUE + 1);` still overflows in the `int` addition before the cast. `(long) Integer.MAX_VALUE + 1` or `1L` is needed.
6. **"Adding more digits to a `double` literal makes it arbitrarily precise."** False: a `double` holds only a fixed number of significand bits; literal syntax does not expand precision.
7. **"`BigDecimal` always divides exactly and needs no rounding."** False for non-terminating decimal quotients, such as `1 / 3`.
8. **"`1 / 3` gives `0` because `int` lacks precision."** Distinguish carefully: Java uses **integer division** when both operands are integers, so the remainder is discarded by the operation's rules. Write `1.0 / 3` to perform floating-point division, though the result is still a binary approximation.

## 7. Self-Check

- If we want to store every integer from `0` to `1_000_000_000` exactly, does `int` have enough **range**? **Yes**, and all valid values are represented exactly.
- Can `double` store a value around `10^100`? **Yes**, because it lies in the finite range; however, that does not mean preserving every digit of that value exactly.
- Why is `16_777_216f + 1 == 16_777_216f`? **Because `float`'s resolution in that region can no longer distinguish a step of 1**, even though it has not exceeded range.
- When needing to compute `0.1 + 0.2` in exact decimal for monetary business logic, what should be used? **`BigDecimal` initialized from a decimal string**, along with clear rounding policies when needed.

**Takeaway:** *Range* tells **how far values can reach**; *precision* tells **how closely spaced values can be distinguished**. For Java integers, every value within range is exact; for floating-point numbers, the range can be vast yet resolution is finite and varies with magnitude.