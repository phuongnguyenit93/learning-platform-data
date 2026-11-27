# Floating-Point Overflow, Underflow, and Subnormal Values in Java 17

Java's floating-point types `float` and `double` have finite representable ranges. When a computation result exceeds that range, the operation can produce infinity (`Infinity`); when a result is too small, it can be rounded to a **subnormal number** or to zero. These phenomena are inherent to Java's floating-point model and must be accounted for when writing scientific algorithms, processing measurements, performing financial calculations, rendering graphics, and validating data.

Java 17 uses strict IEEE 754 floating-point semantics for all expressions (`JEP 306`). This lesson explains **overflow**, **underflow**, **subnormal values**, signed zero, `Infinity`, and `NaN`, while showing how to observe, control, and choose the right data types. The examples use official Java 17 features, with no preview flags required.

## 1. How Java Represents Floating-Point Numbers

Java's two primitive floating-point types are:

- `float`: single precision, occupying 32 bits.
- `double`: double precision, occupying 64 bits and serving as the default type for floating-point literals without a suffix.

Both follow the IEEE 754 binary format. Bits are divided into sign, exponent, and fraction/significand.

| Component | `float` (binary32) | `double` (binary64) |
| --- | ---: | ---: |
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Exponent bits | 8 | 11 |
| Fraction bits | 23 | 52 |
| Exponent bias | 127 | 1023 |
| Approximate precision | 7 decimal digits | 15–17 decimal digits |

For a normal number, the value has the form:

\[
(-1)^{sign} \times 1.fraction \times 2^{exponent-bias}
\]

The 1 before the binary point is an implicit leading bit, giving 24 bits of significand precision for `float` and 53 bits for `double`.

Not every mathematical value can be represented exactly with a finite binary number. For instance, 0.1 in decimal has a repeating binary expansion; when stored in `double`, Java must choose the nearest representable floating-point value.

## 2. Normal and Subnormal Ranges

IEEE 754 reserves a special encoding region where all exponent bits are 0. If the fraction is non-zero, that value is **subnormal**. If the fraction is 0, it is a signed zero.

Normal numbers have an implicit leading significand bit of 1. Subnormal numbers lack this implicit 1 bit; the significand starts with 0, allowing the format to represent very small positive values continuously right below the normal threshold.

Key constants in Java:

| Constant | `float` | `double` | Meaning |
| --- | ---: | ---: | --- |
| `MAX_VALUE` | approx. `3.4028235E38` | approx. `1.7976931348623157E308` | Largest positive finite value |
| `MIN_NORMAL` | approx. `1.17549435E-38` | approx. `2.2250738585072014E-308` | Smallest positive normal value |
| `MIN_VALUE` | approx. `1.4E-45` | approx. `4.9E-324` | Smallest positive non-zero value, in the subnormal range |

**Important note:**

`Float.MIN_VALUE` and `Double.MIN_VALUE` are **neither** the smallest negative numbers **nor** the smallest normal values. They are the **smallest positive non-zero values** representable by their respective types. To get the smallest normal threshold, use `MIN_NORMAL`.

### 2.1. Formula for Subnormal Numbers

For `float`, subnormal numbers have the form:

\[
(-1)^{sign} \times fraction \times 2^{-149}
\]

For `double`:

\[
(-1)^{sign} \times fraction \times 2^{-1074}
\]

Here `fraction` is understood as a binary fraction with 23 bits for `float` or 52 bits for `double`. Because there is no longer an implicit leading 1 bit, subnormal values have fewer significant bits of precision than normal values.

### 2.2. Spacing Between Representable Values

Consecutive floating-point numbers are not spaced at a fixed interval across the entire range.

- In the normal range, spacing depends on the exponent: larger numbers have larger absolute gaps between adjacent representable values.
- In the subnormal range, the step size is fixed and equals `MIN_VALUE`.
- Near 0, subnormals allow gradual approach toward 0 instead of jumping abruptly from `MIN_NORMAL` to 0.

You can use `Math.ulp(value)` to inspect the representable spacing (unit in the last place) around a value:

~~~java
System.out.println(Math.ulp(1.0));
System.out.println(Math.ulp(1.0f));
System.out.println(Double.MIN_VALUE);
~~~

The first output is approximately `2.220446049250313E-16`; the second is approximately `1.1920929E-7`. `Math.ulp` is useful when analyzing rounding errors and the resolution of a floating-point type.

## 3. Floating-Point Overflow

**Overflow** occurs when the mathematical result exceeds the finite representable magnitude of a floating-point type. In Java floating-point arithmetic, the result does not automatically throw `ArithmeticException` like integer division by 0; the result can become `POSITIVE_INFINITY` or `NEGATIVE_INFINITY`.

Example:

~~~java
double tooLarge = Double.MAX_VALUE * 2.0;
System.out.println(tooLarge);                 // Infinity
System.out.println(Double.isInfinite(tooLarge)); // true
System.out.println(Double.isFinite(tooLarge));   // false
~~~

With `float`:

~~~java
float tooLarge = Float.MAX_VALUE * 2.0f;
System.out.println(tooLarge); // Infinity
~~~

Use the `f` suffix for `float` literals. Floating-point literals without a suffix default to `double`.

### 3.1. Which Operations Can Cause Overflow?

Overflow can occur in many operations:

~~~java
double a = Double.MAX_VALUE;

double multiply = a * 2.0;     // Infinity
double add = a + a;            // Infinity
double divideByTiny = a / 1e-300; // Infinity
~~~

A calculation can overflow in an **intermediate value**, even when the final mathematical result would lie within the representable range if computed in a different order. For example, computing vector length by directly squaring large components can overflow before taking the square root.

~~~java
double x = 3e200;
double y = 4e200;

double naive = Math.sqrt(x * x + y * y);
double stable = Math.hypot(x, y);

System.out.println(naive);  // Infinity
System.out.println(stable); // approximately 5.0E200
~~~

`Math.hypot` is designed to compute length while avoiding intermediate overflow and underflow. For numerical algorithms, prefer library functions designed for wide value ranges rather than multiplying or dividing naively.

### 3.2. Overflow Is Not Like Integer Division by Zero

Java handles the two groups of types differently:

~~~java
double floating = 1.0 / 0.0;
System.out.println(floating); // Infinity

// int integer = 1 / 0;
// Throws ArithmeticException if uncommented.
~~~

Floating-point division by 0 produces a special value under IEEE 754; integer division by 0 throws `ArithmeticException`. Do not rely on integer behavior to infer how `float`/`double` behave.

### 3.3. Converting `double` to `float` Can Also Overflow

~~~java
double source = 1e100;
float narrowed = (float) source;

System.out.println(narrowed); // Infinity
~~~

Narrowing conversion from `double` to `float` can lose precision, push values into the subnormal range, turn them into 0, or turn them into infinity if the value exceeds `float`'s range. Check after conversion if a finite range is strictly required.

## 4. Floating-Point Underflow

**Underflow** occurs when a result's magnitude is too small for the resolution of the floating-point type. In IEEE 754 formats supporting subnormals, a result does not immediately become 0 as soon as it drops below `MIN_NORMAL`.

The progression can happen as follows:

1. Result remains in the normal range: represented normally.
2. Result is smaller than `MIN_NORMAL` but large enough to represent: represented as a subnormal.
3. Result is smaller than what can be distinguished in the subnormal range: after rounding, it can become a smaller subnormal or a signed zero.

This is called **gradual underflow**: values decrease smoothly through the subnormal range down to 0.

### 4.1. Smaller Than `MIN_NORMAL` Does Not Yet Mean Zero

~~~java
double smallestNormal = Double.MIN_NORMAL;
double subnormal = smallestNormal / 2.0;

System.out.println(smallestNormal);
System.out.println(subnormal);
System.out.println(subnormal > 0.0); // true
System.out.println(subnormal < Double.MIN_NORMAL); // true
~~~

`subnormal` is still positive and non-zero, yet lies below the normal threshold. Java still preserves this value.

### 4.2. Very Small Results Can Round to Zero

~~~java
double smallestPositive = Double.MIN_VALUE;
double half = smallestPositive / 2.0;

System.out.println(smallestPositive); // approximately 4.9E-324
System.out.println(half);             // 0.0
System.out.println(half == 0.0);      // true
~~~

`Double.MIN_VALUE` is the smallest subnormal step. Halving it produces a value halfway between 0 and `Double.MIN_VALUE`; under round-to-nearest, ties-to-even, the result is 0.

### 4.3. Multiplying Very Small Numbers

~~~java
double product = 1e-200 * 1e-200;
System.out.println(product); // 0.0
~~~

The mathematical value is around `1e-400`, smaller than the smallest non-zero value `double` can represent, so the result rounds to 0.

For `float`, the range is even narrower:

~~~java
float tiny = 1e-30f * 1e-20f;
System.out.println(tiny); // 0.0f
~~~

If a problem needs to preserve very small quantities, evaluate the data's value range and choose an appropriate type; switching from `float` to `double` can widen the representable range, though it does not solve all arithmetic limits.

## 5. Example Observing Overflow, Subnormals, and Underflow

Create the file **`FloatingRangeDemo.java`**:

~~~java
public final class FloatingRangeDemo {

    private FloatingRangeDemo() {
    }

    public static void main(String[] args) {
        double overflow = Double.MAX_VALUE * 2.0;
        double subnormal = Double.MIN_NORMAL / 2.0;
        double roundedToZero = Double.MIN_VALUE / 2.0;
        double negativeZero = -Double.MIN_VALUE / 2.0;

        System.out.println("MAX_VALUE = " + Double.MAX_VALUE);
        System.out.println("MIN_NORMAL = " + Double.MIN_NORMAL);
        System.out.println("MIN_VALUE = " + Double.MIN_VALUE);

        System.out.println("overflow = " + overflow);
        System.out.println("isInfinite = " + Double.isInfinite(overflow));
        System.out.println("isFinite = " + Double.isFinite(overflow));

        System.out.println("subnormal = " + subnormal);
        System.out.println("subnormal > 0 = " + (subnormal > 0.0));
        System.out.println("roundedToZero = " + roundedToZero);
        System.out.println("negativeZero = " + negativeZero);
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 FloatingRangeDemo.java
java FloatingRangeDemo
~~~

The output looks like:

~~~text
MAX_VALUE = 1.7976931348623157E308
MIN_NORMAL = 2.2250738585072014E-308
MIN_VALUE = 4.9E-324
overflow = Infinity
isInfinite = true
isFinite = false
subnormal = 1.1125369292536007E-308
subnormal > 0 = true
roundedToZero = 0.0
negativeZero = -0.0
~~~

Values are printed according to Java's floating-point-to-string conversion. Key observations:

- `overflow` becomes positive infinity.
- `subnormal` is smaller than `MIN_NORMAL` yet remains greater than 0.
- `roundedToZero` has been rounded to 0.
- `negativeZero` retains the negative sign after underflowing to 0.

## 6. Signed Zero (Positive Zero and Negative Zero)

IEEE 754 has both `+0.0` and `-0.0`. They compare equal with the `==` operator, but have different bit representations and certain differing arithmetic behaviors.

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);            // Infinity
System.out.println(1.0 / negativeZero);            // -Infinity
~~~

Underflow can preserve the sign of the result:

~~~java
double positive = Double.MIN_VALUE / 2.0;
double negative = -Double.MIN_VALUE / 2.0;

System.out.println(positive); // 0.0
System.out.println(negative); // -0.0
~~~

If business logic only cares whether a value is zero, `== 0.0` is usually sufficient. If sign carries meaning (e.g., direction of motion, one-sided limits, or numerical algorithms), preserve and check the sign separately.

You can use `Double.doubleToRawLongBits` to inspect the representation:

~~~java
long positiveBits = Double.doubleToRawLongBits(+0.0);
long negativeBits = Double.doubleToRawLongBits(-0.0);

System.out.printf("%016X%n", positiveBits);
System.out.printf("%016X%n", negativeBits);
~~~

The bit patterns are `0000000000000000` and `8000000000000000`, respectively. Do not use `==` to distinguish the two signed zeros.

## 7. Infinity and NaN as Special Values

When overflow occurs, the result can be infinity. Additionally, IEEE 754 defines `NaN` (*Not a Number*) for operations that do not yield a meaningful real number under floating-point rules.

Example:

~~~java
double positiveInfinity = 1.0 / 0.0;
double negativeInfinity = -1.0 / 0.0;
double notANumber = 0.0 / 0.0;
double alsoNaN = Math.sqrt(-1.0);

System.out.println(positiveInfinity); // Infinity
System.out.println(negativeInfinity); // -Infinity
System.out.println(notANumber);       // NaN
System.out.println(alsoNaN);          // NaN
~~~

Notable rules:

| Expression | Result |
| --- | --- |
| Positive finite value divided by 0.0 | `POSITIVE_INFINITY` |
| Negative finite value divided by 0.0 | `NEGATIVE_INFINITY` |
| 0.0 divided by 0.0 | `NaN` |
| `Infinity - Infinity` | `NaN` |
| `0.0 * Infinity` | `NaN` |
| `sqrt(-1.0)` | `NaN` |
| Finite value divided by `Infinity` | Signed zero |

`NaN` has a very important property:

~~~java
double value = Double.NaN;

System.out.println(value == Double.NaN); // false
System.out.println(Double.isNaN(value));  // true
~~~

Do not check for NaN using `== Double.NaN`. Use `Double.isNaN(value)` or `Float.isNaN(value)`.

Similarly, to check for infinity and finiteness, use dedicated APIs:

~~~java
Double.isInfinite(value);
Double.isFinite(value);
Float.isInfinite(value);
Float.isFinite(value);
~~~

`isFinite` returns `false` for both NaN and both infinities.

## 8. Distinguishing Overflow, Underflow, and Precision Loss

These three phenomena are related, but not synonymous:

| Phenomenon | Meaning | Example |
| --- | --- | --- |
| Overflow | Result exceeds finite range | `Double.MAX_VALUE * 2` becomes `Infinity` |
| Underflow | Result is very small, represented as subnormal or rounded to zero | `Double.MIN_VALUE / 2` becomes `0.0` |
| Precision loss (rounding/representation error) | Mathematical value cannot be represented exactly with finite bits | `0.1 + 0.2 != 0.3` |
| Cancellation | Subtracting two nearly equal values loses significant digits | `(1.000000000000001 - 1.0)` retains few reliable digits |

### 8.1. Precision Loss Is Not Necessarily Underflow

~~~java
double result = 0.1 + 0.2;
System.out.println(result);          // 0.30000000000000004
System.out.println(result == 0.3);   // false
~~~

The result is still far away from both 0 and `Double.MAX_VALUE`. This is a representation/rounding error, not overflow or underflow.

### 8.2. Cancellation Is Not Overflow

~~~java
double a = 1.000000000000001;
double b = 1.0;
double difference = a - b;
~~~

Subtracting two nearly equal numbers can lose significant digits in the result. This is a *numerical stability* issue, not the result dropping into the subnormal range.

When designing algorithms, identify which kind of issue you face before choosing a fix. Widening from `float` to `double` can reduce some rounding errors, but it will not fix an inherently unstable algorithm.

## 9. How to Detect and Control Out-of-Range Values

### 9.1. Validating Input Data

If business rules only accept finite numbers:

~~~java
static double requireFinite(double value, String name) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException(
                name + " must be a finite number");
    }
    return value;
}
~~~

Validate before passing values into calculations to prevent NaN/Infinity from propagating across layers.

### 9.2. Validating Operation Results

~~~java
double result = input * factor;

if (!Double.isFinite(result)) {
    throw new ArithmeticException("Result is outside the finite range");
}
~~~

Java does not automatically throw an exception on `double` overflow; if the business contract requires an error, the application must check explicitly.

### 9.3. Validating Business Domain Bounds Instead of Only Finiteness

A finite value can still be invalid:

~~~java
double temperature = -500.0;

if (!Double.isFinite(temperature)
        || temperature < -273.15
        || temperature > 1000.0) {
    throw new IllegalArgumentException("Temperature is outside the allowed range");
}
~~~

The data contract must specify finiteness, units of measurement, and domain bounds.

### 9.4. Avoiding Intermediate Overflow

When computing expressions that can generate very large or very small intermediate numbers:

- Use library functions designed for numerical stability, such as `Math.hypot`.
- Normalize/scale values before multiplying or squaring if the algorithm permits.
- Choose an appropriate operation order to avoid unnecessary intermediate overflow.
- For scientific algorithms, analyze error and data ranges with tests covering large, small, and boundary-adjacent values.

There is no single trick for all expressions. Base the approach on the mathematical meaning and input limits of the problem.

## 10. Choosing `float`, `double`, `BigDecimal`, or Integer Types?

`double` has a wider range and higher precision than `float`, so it is usually the default choice for floating-point computation in Java. However, some problems require exact decimal arithmetic under business rules or integers with very large ranges.

| Type | Suitable When | Limitations to Understand |
| --- | --- | --- |
| `float` | Graphics, large datasets needing memory savings, APIs requiring binary32 | Narrower range and lower precision than `double` |
| `double` | General scientific/engineering computation, measurement, general real numbers | Has rounding, overflow, and underflow |
| `BigDecimal` | Decimals requiring explicit precision/rounding rules, such as money | Higher resource cost; requires specifying scale and rounding |
| `BigInteger` | Integers larger than `long` range | Does not represent fractional parts |

### 10.1. Using BigDecimal When Controlled Decimal Arithmetic Is Needed

Do not initialize `BigDecimal` from a `double` literal if you want to preserve user-entered decimal values:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.08");

BigDecimal tax = price.multiply(taxRate)
        .setScale(2, RoundingMode.HALF_UP);

BigDecimal total = price.add(tax);

System.out.println(total); // 21.59
~~~

`new BigDecimal("19.99")` preserves the exact decimal value specified by the string. In contrast, `new BigDecimal(0.1)` takes a `double` already approximated in binary, then represents that exact binary approximation in decimal.

`BigDecimal.valueOf(0.1)` is generally preferable to the direct `double` constructor because it relies on the canonical string representation of the double value. For user-supplied monetary data, parse input strings and explicitly define scale and rounding per business rules.

`BigDecimal` has no `NaN` or `Infinity` values. However, division without a finite decimal expansion throws `ArithmeticException` unless precision/rounding is specified:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3);

// one.divide(three) // ArithmeticException: non-terminating repeating decimal result

BigDecimal result = one.divide(
        three,
        10,
        RoundingMode.HALF_UP
);
~~~

Nor is `BigDecimal` a universal replacement for all scientific math: consider performance, rounding rules, and appropriate data models.

### 10.2. Using BigInteger for Integers That Must Not Overflow

For integer arithmetic needing overflow detection, use `Math.addExact`, `Math.multiplyExact`, or `BigInteger` as required:

~~~java
long result = Math.multiplyExact(1_000_000_000L, 1_000_000_000L);
~~~

The snippet above throws `ArithmeticException` if the multiplication exceeds the `long` range. This mechanism is for integers; `Math.multiplyExact` does not apply to `float`/`double`.

## 11. Java 17 Always Uses Strict Floating-Point Semantics

Before Java 17, Java had the concept of floating-point expression *value sets* and the `strictfp` keyword to enforce strict evaluation on platforms that could use extended intermediate values. Starting in **Java 17 (JEP 306)**, all floating-point expressions are always evaluated strictly under standard semantics; `strictfp` is no longer needed to achieve that behavior.

Example:

~~~java
public strictfp class Calculation {
    static double calculate(double x, double y) {
        return x * y + 1.0;
    }
}
~~~

In Java 17, the `strictfp` modifier in the example above is redundant. There is no need to add `strictfp` to new classes or methods just to "enable IEEE 754". You may still encounter legacy code retaining this keyword; it does not change the meaning of overflow/underflow topics in Java 17.

Strict semantics do not mean all decimal calculations become absolutely exact. They guarantee floating-point evaluation follows Java's deterministic rules, while bit limits, rounding, overflow, and underflow still exist.

## 12. Practice Exercise: Checking Representation Boundaries

Create a program checking several key values:

~~~java
public final class FloatingBoundaryExercise {

    private FloatingBoundaryExercise() {
    }

    public static void main(String[] args) {
        double normal = Double.MIN_NORMAL;
        double subnormal = normal / 2.0;
        double smallest = Double.MIN_VALUE;
        double zero = smallest / 2.0;
        double overflow = Double.MAX_VALUE * 2.0;

        print("normal", normal);
        print("subnormal", subnormal);
        print("smallest", smallest);
        print("underflow-to-zero", zero);
        print("overflow", overflow);
    }

    private static void print(String label, double value) {
        System.out.printf(
                "%-20s value=%-24s finite=%-5s zero=%s%n",
                label,
                value,
                Double.isFinite(value),
                value == 0.0
        );
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 FloatingBoundaryExercise.java
java FloatingBoundaryExercise
~~~

After running, answer:

1. Why does `subnormal` still have `finite=true`?
2. Why does `underflow-to-zero` not throw an exception?
3. Why does `overflow` have `finite=false`?
4. If you change `double` to `float`, how do the representation boundaries change?
5. Does `-0.0` compare equal to `0.0`? How can they be distinguished?

## 13. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Multiplication result becomes `Infinity` | Value exceeds finite range | Validate inputs/results, apply scaling, or use a different numeric type |
| Small values become `0.0` | Underflow after rounding | Evaluate data range, use `double` instead of `float`, or change numeric model |
| `Double.MIN_VALUE` mistaken for smallest normal number | Constant name confusion | Use `Double.MIN_NORMAL` for the normal threshold |
| `NaN` enters the system | Only checking for null or numeric comparisons | Use `Double.isFinite`/`isNaN` |
| `value == Double.NaN` is always false | NaN equals no value, including itself | Use `Double.isNaN(value)` |
| Dividing by 0.0 throws no error | IEEE 754 floating-point rules | Explicitly check if business rules forbid a 0 denominator |
| Vector length becomes Infinity despite finite answer | Squaring components causes intermediate overflow | Use `Math.hypot` or scaling algorithms |
| Converting `double` to `float` produces Infinity | Value is outside `float`'s range | Check after narrowing conversion |
| Using `BigDecimal` fails on division | Non-terminating decimal division without precision/rounding specified | Use overload with scale or `MathContext` |
| Adding `strictfp` still shows decimal error | Strict does not mean absolutely exact | Distinguish rounding from overflow/underflow |

## 14. Extended Exercises

1. **Overflow:** compute `Float.MAX_VALUE * 2.0f` and `Double.MAX_VALUE * 2.0`. Check with `isInfinite` and `isFinite`.
2. **Subnormal:** start from `Double.MIN_NORMAL`, divide repeatedly by 2.0, and observe when values drop below normal while remaining non-zero.
3. **Underflow:** compute `Double.MIN_VALUE / 2.0` and `-Double.MIN_VALUE / 2.0`; compare the results and the bit representations of both zeros.
4. **NaN:** try `0.0 / 0.0`, `Math.sqrt(-1)`, and `Double.isNaN`; observe why equality comparison cannot detect NaN.
5. **Intermediate overflow:** compare `Math.sqrt(x*x + y*y)` with `Math.hypot(x, y)` for values `x=3e200`, `y=4e200`.
6. **Decimal numbers:** compare `new BigDecimal("0.1")`, `BigDecimal.valueOf(0.1)`, and `new BigDecimal(0.1)`; explain differences in value origin.

When working with floating-point numbers, you need to know how large or small data can be, what error is acceptable, and how the application should react when results go out of bounds. In Java 17, `float` and `double` follow strict IEEE 754 semantics, yet remain finite: overflow produces infinity, and underflow passes through the subnormal range before potentially reaching signed zero.
