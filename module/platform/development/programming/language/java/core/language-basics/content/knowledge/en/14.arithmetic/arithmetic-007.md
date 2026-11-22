# NaN, Infinity, and Signed Zero in Floating-Point Arithmetic — Java 17+

`float` and `double` in Java represent binary floating-point numbers according to IEEE 754. Beyond ordinary finite numbers, they have three groups of special values:

- **`NaN` (*Not a Number*)**: a value indicating an undefined arithmetic result, such as `0.0 / 0.0`.
- **Infinity (`Infinity` and `-Infinity`)**: can appear when a non-zero floating-point number is divided by zero or when a result is too large.
- **Signed zero (*signed zero*)**: there are `+0.0` and `-0.0`. The two values are equal under the `==` operator, yet **their sign bits differ** and can produce different results in certain operations.

~~~java
double positive = 1.0 / 0.0;  // Infinity.
double negative = 1.0 / -0.0; // -Infinity.
double undefined = 0.0 / 0.0; // NaN.
~~~

**Do not apply integer division-by-0 rules to floating-point numbers.** `int` divided by 0 throws `ArithmeticException` at runtime; `double`/`float` divided by zero follows IEEE 754 rules.

## 1. Table of Typical Results

| Java Expression | Result | Cause |
| --- | --- | --- |
| `1.0 / 0.0` | `Infinity` | Positive number divided by positive zero |
| `1.0 / -0.0` | `-Infinity` | Positive number divided by negative zero |
| `0.0 / 0.0` | `NaN` | Indeterminate form |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` | Infinity minus infinity |
| `Double.POSITIVE_INFINITY * 0.0` | `NaN` | Infinity times zero |
| `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY` | `NaN` | Infinity divided by infinity |
| `Double.MAX_VALUE * 2.0` | `Infinity` | Floating-point overflow |
| `Double.MIN_VALUE / 2.0` | `0.0` | Underflow toward positive zero |
| `-Double.MIN_VALUE / 2.0` | `-0.0` | Underflow toward negative zero |

**Be careful with the name `Double.MIN_VALUE`:** this is the **smallest positive `double` number greater than 0**, not the most negative number. To get a finite negative value with very large magnitude, you can use `-Double.MAX_VALUE`.

## 2. Standalone Runnable Java 17+ Example

Create a UTF-8 file **`FloatingSpecialValuesDemo.java`**:

~~~java
public class FloatingSpecialValuesDemo {
    public static void main(String[] args) {
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = 1.0 / -0.0;
        double nan = 0.0 / 0.0;

        System.out.println("positiveInfinity=" + positiveInfinity);
        System.out.println("negativeInfinity=" + negativeInfinity);
        System.out.println("zeroOverZeroIsNaN="
                + Double.isNaN(nan));

        System.out.println("infinityMinusInfinityIsNaN="
                + Double.isNaN(Double.POSITIVE_INFINITY
                        - Double.POSITIVE_INFINITY));
        System.out.println("infinityTimesZeroIsNaN="
                + Double.isNaN(Double.POSITIVE_INFINITY * 0.0));
        System.out.println("infinityOverInfinityIsNaN="
                + Double.isNaN(Double.POSITIVE_INFINITY
                        / Double.POSITIVE_INFINITY));

        System.out.println("nanEqualsSelf=" + (nan == nan));
        System.out.println("nanNotEqualsSelf=" + (nan != nan));
        System.out.println("nanLessThanZero=" + (nan < 0.0));
        System.out.println("nanCompareSelf="
                + Double.compare(nan, nan));
        System.out.println("nanWrapperEquals="
                + Double.valueOf(nan).equals(Double.valueOf(nan)));

        System.out.println("finite42=" + Double.isFinite(42.0));
        System.out.println("finiteInfinity="
                + Double.isFinite(positiveInfinity));
        System.out.println("maxOverflow="
                + (Double.MAX_VALUE * 2.0));
        System.out.println("minUnderflow="
                + (Double.MIN_VALUE / 2.0));
        System.out.println("negativeMinUnderflow="
                + (-Double.MIN_VALUE / 2.0));

        double positiveZero = 0.0;
        double negativeZero = -0.0;
        System.out.println("zerosEqual="
                + (positiveZero == negativeZero));
        System.out.println("zeroWrapperEquals="
                + Double.valueOf(positiveZero)
                        .equals(Double.valueOf(negativeZero)));
        System.out.println("zeroCompare="
                + Double.compare(positiveZero, negativeZero));
        System.out.println("positiveZeroBits="
                + Long.toHexString(
                        Double.doubleToRawLongBits(positiveZero)));
        System.out.println("negativeZeroBits="
                + Long.toHexString(
                        Double.doubleToRawLongBits(negativeZero)));

        System.out.println("reciprocalPositiveZero="
                + (1.0 / positiveZero));
        System.out.println("reciprocalNegativeZero="
                + (1.0 / negativeZero));
        System.out.println("minZero="
                + Math.min(negativeZero, positiveZero));
        System.out.println("maxZero="
                + Math.max(negativeZero, positiveZero));
        System.out.println("copiedNegativeSign="
                + Math.copySign(5.0, negativeZero));
        System.out.println("nanMinIsNaN="
                + Double.isNaN(Math.min(nan, 3.0)));
        System.out.println("negativeZeroRemainder="
                + (negativeZero % 3.0));

        float floatNegativeInfinity = 1.0f / -0.0f;
        System.out.println("floatNegativeInfinity="
                + floatNegativeInfinity);
        System.out.println("parsedNaN="
                + Double.isNaN(Double.parseDouble("NaN")));

        double sum = 0.1 + 0.2;
        System.out.println("sum=" + sum);
        System.out.println("exactDecimalEquality="
                + (sum == 0.3));
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file. Requires **JDK 17 or later**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 FloatingSpecialValuesDemo.java
java FloatingSpecialValuesDemo
~~~

**Exact expected output** of `java FloatingSpecialValuesDemo` alone:

~~~text
positiveInfinity=Infinity
negativeInfinity=-Infinity
zeroOverZeroIsNaN=true
infinityMinusInfinityIsNaN=true
infinityTimesZeroIsNaN=true
infinityOverInfinityIsNaN=true
nanEqualsSelf=false
nanNotEqualsSelf=true
nanLessThanZero=false
nanCompareSelf=0
nanWrapperEquals=true
finite42=true
finiteInfinity=false
maxOverflow=Infinity
minUnderflow=0.0
negativeMinUnderflow=-0.0
zerosEqual=true
zeroWrapperEquals=false
zeroCompare=1
positiveZeroBits=0
negativeZeroBits=8000000000000000
reciprocalPositiveZero=Infinity
reciprocalNegativeZero=-Infinity
minZero=-0.0
maxZero=0.0
copiedNegativeSign=-5.0
nanMinIsNaN=true
negativeZeroRemainder=-0.0
floatNegativeInfinity=-Infinity
parsedNaN=true
sum=0.30000000000000004
exactDecimalEquality=false
~~~

`java -version` and `javac -version` print machine-specific JDK information and are not part of the program's expected output.

## 3. `NaN`: Checking and Comparing

`NaN` is not `null`, the number 0, or an error string. It is a **special floating-point value** that can propagate through many calculations.

~~~java
double value = 0.0 / 0.0;
System.out.println(value == Double.NaN); // false.
System.out.println(value != value);      // true.
System.out.println(Double.isNaN(value)); // true.
~~~

For primitive `double` or `float`, the operators `==`, `<`, `<=`, `>`, `>=` with a NaN operand return `false`; `!=` returns `true`. Therefore **do not check for NaN using `value == Double.NaN`**. Use `Double.isNaN(value)` or `Float.isNaN(value)`.

### Distinguishing Primitive `==`, `Double.equals`, and `Double.compare`

~~~java
double nan = Double.NaN;
System.out.println(nan == nan); // false.
System.out.println(Double.compare(nan, nan)); // 0.
System.out.println(Double.valueOf(nan)
        .equals(Double.valueOf(nan))); // true.
~~~

| Comparison | Two NaN Values | `+0.0` and `-0.0` |
| --- | --- | --- |
| Primitive `==` | `false` | `true` |
| Wrapper `Double.equals` | `true` | `false` |
| `Double.compare(a,b)` | Returns 0 when both are NaN | Distinguishes sign, `compare(+0.0,-0.0) > 0` |

`Double.equals` and `Double.compare` are designed to provide equality/ordering rules suitable for wrappers and collections. They are **not completely identical** to primitive floating-point comparison semantics using `==`.

### NaN Propagation and Parsing

~~~java
double nan = Double.NaN;
System.out.println(Double.isNaN(nan + 2.0)); // true.
System.out.println(Double.isNaN(nan * 0.0)); // true.
System.out.println(Double.isNaN(Double.parseDouble("NaN"))); // true.
~~~

A string `"NaN"` can be accepted by `Double.parseDouble`. **Successful parsing does not mean the value is valid for business logic**, especially when the application only wants finite numbers.

## 4. Infinity and Detecting Finite Values

Besides `Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY`, calculations that are too large can produce infinity:

~~~java
double overflow = Double.MAX_VALUE * 2.0; // Infinity.
double reciprocal = 1.0 / -0.0;          // -Infinity.
~~~

Some operations with infinity still yield infinity, such as `Infinity + 3.0`. However, `Infinity + (-Infinity)`, `Infinity * 0.0`, or `Infinity / Infinity` produce NaN.

If you need to confirm a finite floating-point number:

~~~java
double input = Double.parseDouble("12.5");
if (!Double.isFinite(input)) {
    throw new IllegalArgumentException("Expected a finite number");
}
~~~

- `Double.isNaN(x)`: is the value NaN?
- `Double.isInfinite(x)`: is the value positive or negative infinity?
- `Double.isFinite(x)`: is the value neither NaN nor infinity?
- `Float` also has corresponding methods for `float`.

`Double.isFinite(-0.0)` returns **`true`**. A zero with a sign bit is still a **finite** number.

## 5. How Do `+0.0` and `-0.0` Differ?

Both `+0.0` and `-0.0` are zero under `==`:

~~~java
double plus = 0.0;
double minus = -0.0;

System.out.println(plus == minus); // true.
System.out.println(1.0 / plus);    // Infinity.
System.out.println(1.0 / minus);   // -Infinity.
~~~

However, under IEEE 754 they have **different sign bits**. `Double.doubleToRawLongBits` lets you inspect the bit pattern:

| Expression | 64-bit Pattern (hexadecimal) |
| --- | --- |
| `Double.doubleToRawLongBits(+0.0)` | `0x0000000000000000` |
| `Double.doubleToRawLongBits(-0.0)` | `0x8000000000000000` |

The demo prints `positiveZeroBits=0` and `negativeZeroBits=8000000000000000` because `Long.toHexString` omits leading zero digits.

Beyond reciprocals, the sign of zero can matter in `Math.min`, `Math.max`, `Math.copySign`, division, and floating-point remainder:

~~~java
System.out.println(Math.min(-0.0, 0.0));    // -0.0.
System.out.println(Math.max(-0.0, 0.0));    //  0.0.
System.out.println(Math.copySign(5.0, -0.0)); // -5.0.
System.out.println(-0.0 % 3.0);            // -0.0.
~~~

**Do not use `x == 0.0` to distinguish the sign of zero.** Depending on your needs, use `Math.copySign` or inspect the bits. `float` also has `+0.0f` and `-0.0f`, using a 32-bit representation.

## 6. Overflow/Underflow Are Different from Ordinary Rounding Errors

**Floating-point overflow** can produce `Infinity` when magnitude exceeds the finite range. **Underflow** occurs with values too close to 0, which can become subnormal or round to **signed zero**:

~~~java
System.out.println(Double.MAX_VALUE * 2.0); // Infinity.
System.out.println(Double.MIN_VALUE / 2.0); // 0.0.
System.out.println(-Double.MIN_VALUE / 2.0); // -0.0.
~~~

`Double.MIN_VALUE` is the **smallest positive non-zero** number, not the negative value with the largest magnitude. These operations do not automatically throw `ArithmeticException` like integer division by 0.

Even a **finite** number may still be only an approximation: `0.1 + 0.2` in `double` gives `0.30000000000000004`. `Double.isFinite` checks for NaN/infinity; it does **not** prove an exact decimal value. The next lesson focuses on binary32/binary64, ULP, accumulated error, tolerances, and exact decimal models.


## 7. Common Mistakes

| Misconception | Reality in Java 17+ |
| --- | --- |
| "`0.0 / 0.0` throws `ArithmeticException`." | The result is `NaN` |
| "`1.0 / 0.0` is like `1 / 0`." | `double` gives `Infinity`; `int` divided by 0 throws an exception |
| "`NaN == NaN` is always true." | For primitive `double`: `false` |
| "`x == Double.NaN` checks for NaN." | Wrong; use `Double.isNaN(x)` |
| "`Double.equals` and primitive `==` are completely identical." | They differ for NaN and ±0.0 |
| "`+0.0` and `-0.0` have no differences at all." | They differ in sign bit and can yield different operation results |
| "`Double.MIN_VALUE` is the smallest negative value." | It is the smallest positive number greater than 0 |
| "If `parseDouble` succeeds, you always get a finite number." | Strings `"NaN"` and `"Infinity"` are also valid inputs |
| "Finite number means exact decimal number." | No; `0.1 + 0.2` is a counterexample |

## 8. Self-Check Exercises

1. What are `1.0 / 0.0`, `1.0 / -0.0`, and `0.0 / 0.0`, respectively?  
   *Answer:* `Infinity`, `-Infinity`, `NaN`.
2. Why does `Double.NaN == Double.NaN` evaluate to false?  
   *Answer:* Primitive `==` follows NaN comparison rules; check for NaN with `Double.isNaN`.
3. What do `0.0 == -0.0` and `1.0 / -0.0` evaluate to?  
   *Answer:* `true` and `-Infinity`.
4. Are the two wrappers `Double.valueOf(0.0)` and `Double.valueOf(-0.0)` equal under `equals`?  
   *Answer:* No; `Double.equals` distinguishes the sign bit of zero.
5. What can `Double.MIN_VALUE / 2.0` produce?  
   *Answer:* `0.0` due to underflow.
6. If you need to reject both NaN and Infinity in floating-point input, what should you use?  
   *Answer:* `Double.isFinite(value)`.
7. `Double.isFinite(0.1 + 0.2)` returns true, so is `0.1 + 0.2 == 0.3` guaranteed to be true?  
   *Answer:* No; in `double`, the result is `0.30000000000000004`.

## Checklist

- [ ] Know that `NaN`, `Infinity`, and `-Infinity` are **special floating-point values**, not `null`.
- [ ] Use `Double.isNaN`, `Double.isInfinite`, `Double.isFinite` instead of guessing from `==`.
- [ ] Distinguish primitive `==` from `Double.equals` and `Double.compare`.
- [ ] Understand that `+0.0` and `-0.0` are equal under `==` but differ in sign bit.
- [ ] Know that overflow can produce infinity, and underflow can produce signed zero.
- [ ] Distinguish division by 0 between integers and floating-point numbers.
- [ ] Do not equate **finite** with **decimally exact**.

**Conclusion:** `float`/`double` have important rules dedicated to **NaN, infinity, and the two signed zero values**. Read these values properly with dedicated checking APIs, understand the differences between comparison operations, and verify precision independently of finiteness.