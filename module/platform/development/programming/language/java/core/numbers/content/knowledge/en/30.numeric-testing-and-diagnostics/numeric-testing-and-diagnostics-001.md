# Testing `MIN_VALUE`, `MAX_VALUE`, Zero, and Boundary Neighbors in Java

## 1. Why Must Numeric Testing Focus on Boundaries?

A piece of numeric processing code can run correctly on ordinary data yet fail at **value range limits**: `int` addition overflows, division by zero occurs, a floating-point number underflows to 0, or a range check uses `MAX_VALUE + 1`. These bugs often do not appear when testing only values like 10, 20, and 50.

The prompt “test `MIN_VALUE`, `MAX_VALUE`, zero, and boundary neighbors” requires designing a test suite using **equivalence partitioning** and **boundary-value analysis**. If a function accepts the interval `[min, max]`, at a minimum you should consider `min`, `max`, values immediately **inside**, immediately **outside**, and central/zero cases when meaningful.

In particular, you must distinguish two kinds of numbers in Java:

- **Primitive integral types**: `byte`, `short`, `int`, and `long` have finite bounds, and ordinary arithmetic operations can overflow without throwing an exception.
- **Floating-point numbers**: `float` and `double` have an extremely large finite maximum, a smallest positive nonzero value, *subnormal* numbers, `+0.0`/`-0.0`, `NaN`, and `±Infinity`. “Neighbors” must be understood in terms of **representable** values rather than simply adding or subtracting 1.

With `BigInteger` and `BigDecimal`, the value range expands arbitrarily within resource limits, yet conversions to `int` or `long` and scale/precision checks still have boundary cases.

Lesson objective: build a systematic test-case matrix, predict and verify Java 17+ results, diagnose overflow/precision bugs, and write tests that do not rely on luck.

## 2. Boundary Test Case Design Process

Suppose a function `accept(int value)` only accepts `0 <= value <= 100`. Start from the specification, then pick the points:

| Partition | Value | Expected result |
|---|---:|---|
| Just outside lower bound | `-1` | Reject |
| At lower bound | `0` | Accept |
| Just above lower bound | `1` | Accept |
| A mid-range value | `50` | Accept |
| Just below upper bound | `99` | Accept |
| At upper bound | `100` | Accept |
| Just outside upper bound | `101` | Reject |

From this example, expand into a checklist when working with numbers:

1. **Value type**: integer, `double`, `BigDecimal`, etc.; identical notation can have different overflow rules.
2. **Valid domain**: are the lower/upper bounds **inclusive** (`>=`, `<=`) or **exclusive** (`>`, `<`)? Are negative numbers, 0, or decimals accepted?
3. **Adjacent values**: for integers you can use `±1` **if still within range**; for `double` you should use `Math.nextUp`/`Math.nextDown`.
4. **Special cases**: division by 0, `MIN_VALUE / -1`, `Math.abs(MIN_VALUE)`, `-0.0`, `NaN`, infinities, subnormals.
5. **Expected behavior**: return the right result, throw an exception, saturate, reject data, or round according to specification. Do not merely check “does not crash”.
6. **Do not introduce bugs in the test suite itself**: the expression `Integer.MAX_VALUE + 1` has already overflowed before being passed into the function; it is a negative input, not an `int` exceeding max.
7. **Multi-variable testing**: prioritize combinations that push operations to boundaries, such as `a + b`, `a * b`, division by 0, or `MIN_VALUE / -1`.

More tests are not automatically better; choose cases with a **direct rationale from the contract and data type**.

## 3. Bounds of Primitive Integral Types

| Type | `MIN_VALUE` | `MAX_VALUE` | Range |
|---|---:|---:|---|
| `byte` | `-128` | `127` | 8-bit signed |
| `short` | `-32768` | `32767` | 16-bit signed |
| `int` | `-2147483648` | `2147483647` | 32-bit signed |
| `long` | `-9223372036854775808` | `9223372036854775807` | 64-bit signed |

For `int`, the key values can be laid out as:

```text
Integer.MIN_VALUE       = -2147483648
Integer.MIN_VALUE + 1   = -2147483647
-1
0
1
Integer.MAX_VALUE - 1   =  2147483646
Integer.MAX_VALUE       =  2147483647
```

These are the **seven primary check points** at the physical bounds of the type. If the function has other business limits, add those business bounds as well (for example `0` and `100`). Read carefully: `Integer.MIN_VALUE - 1` is **not a valid `int`**; `int` arithmetic will overflow.

### 3.1. `int` Overflow Silently Wraps Around

Java computes `int` in a 32-bit range. If the mathematical result exceeds the limits, ordinary primitive addition, subtraction, and multiplication **do not automatically throw an exception**:

```java
int wrappedUp = Integer.MAX_VALUE + 1;
int wrappedDown = Integer.MIN_VALUE - 1;

System.out.println(wrappedUp);   // -2147483648
System.out.println(wrappedDown); // 2147483647
```

Do not treat a negative result after an increment as proof that negative input was supplied; the **operation itself** can produce an unintended value.

When the requirement is “compute accurately or report an error”, use the `Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact`, or `negateExact` family depending on the operation. They throw `ArithmeticException` if the result does not fit in the target type.

### 3.2. The `Math.abs(Integer.MIN_VALUE)` Trap

The `int` range is asymmetric: the mathematical absolute value of `Integer.MIN_VALUE` is `2147483648`, which is one greater than `Integer.MAX_VALUE`. Therefore:

```java
System.out.println(Math.abs(Integer.MIN_VALUE)); // -2147483648
```

`Math.abs(long)` has the same issue at `Long.MIN_VALUE`. If you want an exact absolute value for `int` with enough range, you can widen the type **before** computing:

```java
long magnitude = Math.abs((long) Integer.MIN_VALUE);
System.out.println(magnitude); // 2147483648
```

For `Long.MIN_VALUE`, widening to `long` does not help because it is already at the `long` limit; you can use `BigInteger.valueOf(Long.MIN_VALUE).abs()` when you truly need the exact magnitude.

### 3.3. The `MIN_VALUE / -1` Case

In mathematical arithmetic, `-2147483648 / -1 = 2147483648`, outside the `int` range. Java specifies that integer division `Integer.MIN_VALUE / -1` returns `Integer.MIN_VALUE` due to overflow, without reporting an error. With `long`, `Long.MIN_VALUE / -1L` behaves the same way.

In contrast, integer division with denominator **0** throws `ArithmeticException`. Therefore, the following two cases must be tested **separately**, not merged:

```text
MIN_VALUE / -1  -> special overflow, does not throw
anyInteger / 0  -> ArithmeticException
```

If using Java 18+ and needing exact division with overflow detection, see `Math.divideExact`. For Java 17 illustration/testing, you can explicitly check the pair `MIN_VALUE, -1` before dividing.

## 4. Runnable Example: Diagnosing `int` Boundaries

**File `IntegralBoundaryDemo.java`:**

```java
public class IntegralBoundaryDemo {
    public static void main(String[] args) {
        System.out.println("int.min=" + Integer.MIN_VALUE);
        System.out.println("int.max=" + Integer.MAX_VALUE);

        System.out.println("wrapMax=" + (Integer.MAX_VALUE + 1));
        System.out.println("wrapMin=" + (Integer.MIN_VALUE - 1));
        System.out.println("absMin=" + Math.abs(Integer.MIN_VALUE));
        System.out.println("minDivNegOne=" + (Integer.MIN_VALUE / -1));

        try {
            System.out.println(Math.addExact(Integer.MAX_VALUE, 1));
        } catch (ArithmeticException ex) {
            System.out.println("addExact=ArithmeticException");
        }

        try {
            int impossible = Integer.MAX_VALUE / 0;
            System.out.println(impossible);
        } catch (ArithmeticException ex) {
            System.out.println("divideZero=ArithmeticException");
        }

        long magnitude = Math.abs((long) Integer.MIN_VALUE);
        System.out.println("safeAbs=" + magnitude);
    }
}
```

```bash
javac IntegralBoundaryDemo.java
java IntegralBoundaryDemo
```

Output:

```text
int.min=-2147483648
int.max=2147483647
wrapMax=-2147483648
wrapMin=2147483647
absMin=-2147483648
minDivNegOne=-2147483648
addExact=ArithmeticException
divideZero=ArithmeticException
safeAbs=2147483648
```

The example puts division by 0 into an `int` variable with a literal `0` denominator; Java allows such integer division to compile and only throws the exception at runtime. Note that the expression `Integer.MAX_VALUE + 1` overflows as an `int`, and assigning to `long` **after** the addition does not fix the already-overflowed value:

```java
long wrong = Integer.MAX_VALUE + 1;     // Already overflowed int before assignment
long right = (long) Integer.MAX_VALUE + 1; // Added in the long domain

System.out.println(wrong); // -2147483648
System.out.println(right); // 2147483648
```

## 5. Boundary Neighbors for Floating-Point Numbers: Fundamentally Different from Integers

`float`/`double` under IEEE 754 represent a set of numbers with uneven density. The spacing between two consecutive representable values changes with magnitude. Therefore **you cannot arbitrarily use `x + 1` to find an adjacent value**.

Special cases of `double`:

| Constant / value | Meaning |
|---|---|
| `Double.MAX_VALUE` | Largest positive finite number, about `1.7976931348623157E308` |
| `-Double.MAX_VALUE` | Smallest negative finite number in ordering |
| `Double.MIN_NORMAL` | Smallest positive **normal** number, about `2.2250738585072014E-308` |
| `Double.MIN_VALUE` | Smallest **positive nonzero** number, about `4.9E-324` |
| `+0.0`, `-0.0` | Two representations of zero with different sign bits |
| `Double.POSITIVE_INFINITY` / `NEGATIVE_INFINITY` | Infinity values |
| `Double.NaN` | Not-a-Number, with special comparison rules |

**Especially easy to get wrong:** `Double.MIN_VALUE` is **not** the smallest negative finite number. `Double.MIN_VALUE` is the smallest **positive** nonzero number. The same applies to `Float.MIN_VALUE`. If you need to test the negative finite bound, use `-Double.MAX_VALUE` or `-Float.MAX_VALUE`.

**Subnormal** numbers lie between 0 and `MIN_NORMAL` (in absolute magnitude). They allow representing tiny numbers near 0 with gradually decreasing relative precision. When an operation produces a number smaller than representable, the result can underflow to 0.

### 5.1. `Math.nextUp`, `Math.nextDown`, and `Math.ulp`

To generate **adjacent** representable values:

- `Math.nextUp(x)`: the immediately following representable floating-point value in numerical order.
- `Math.nextDown(x)`: the immediately preceding value.
- `Math.nextAfter(x, direction)`: steps to the adjacent value toward `direction`.
- `Math.ulp(x)`: the size of one unit in the last place at the magnitude of `x`.

Example:

```java
System.out.println(Math.nextUp(1.0));   // 1.0000000000000002
System.out.println(Math.nextDown(1.0)); // 0.9999999999999999
System.out.println(Math.nextUp(0.0));   // 4.9E-324
System.out.println(Math.nextDown(0.0)); // -4.9E-324
```

Unlike `+1`, these functions can generate values **right at representation boundaries** to test comparison conditions, numerical algorithms, and rounding.

### 5.2. Be Careful with Signed Zero

Under `==`, `+0.0 == -0.0` is `true`, yet the sign bit differs and can affect division:

```java
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

`Double.compare(0.0, -0.0)` **does not return 0** because `Double.compare` distinguishes signed zero in the API's total order. If you only check `x == 0.0`, both are treated as zero. In some algorithms, you need to determine whether the sign of zero is part of the contract.

### 5.3. `NaN` and Infinities

`Double.NaN` cannot be checked with `x == Double.NaN` because every `==` comparison with `NaN` evaluates to `false`. Use `Double.isNaN(x)`. To reject all non-finite values, use `Double.isFinite(x)`.

If `x` is `NaN`, both `x < limit` and `x > limit` are `false`. Consequently, a validator written with only two bound comparisons can accidentally **accept NaN**; checking `Double.isFinite` first is the clear choice when the domain only accepts finite numbers.

## 6. Runnable Example: Floating-Point Numbers and Boundary Neighbors

**File `FloatingBoundaryDemo.java`:**

```java
public class FloatingBoundaryDemo {
    public static void main(String[] args) {
        System.out.println("smallestPositive=" + Double.MIN_VALUE);
        System.out.println("smallestNormal=" + Double.MIN_NORMAL);

        System.out.println("nextUpZero=" + Math.nextUp(0.0));
        System.out.println("nextDownZero=" + Math.nextDown(0.0));
        System.out.println("nextUpOne=" + Math.nextUp(1.0));
        System.out.println("nextDownOne=" + Math.nextDown(1.0));

        System.out.println("underflow=" + (Double.MIN_VALUE / 2));
        System.out.println("overflow="
                + Double.isInfinite(Double.MAX_VALUE * 2));
        System.out.println("negativeZeroSign=" + (1.0 / -0.0));

        System.out.println("zeroEqual=" + (0.0 == -0.0));
        System.out.println("nanEqual=" + (Double.NaN == Double.NaN));
        System.out.println("finiteOne=" + Double.isFinite(1.0));
        System.out.println("finiteInfinity="
                + Double.isFinite(Double.POSITIVE_INFINITY));
    }
}
```

```bash
javac FloatingBoundaryDemo.java
java FloatingBoundaryDemo
```

Output:

```text
smallestPositive=4.9E-324
smallestNormal=2.2250738585072014E-308
nextUpZero=4.9E-324
nextDownZero=-4.9E-324
nextUpOne=1.0000000000000002
nextDownOne=0.9999999999999999
underflow=0.0
overflow=true
negativeZeroSign=-Infinity
zeroEqual=true
nanEqual=false
finiteOne=true
finiteInfinity=false
```

The values printed here follow Java's standard `Double.toString` representation. `Double.MIN_VALUE / 2` underflows and rounds to `+0.0`; `Double.MAX_VALUE * 2` overflows to `+Infinity`. Unlike integer division by 0, dividing a `double` by `+0.0` or `-0.0` with a nonzero finite numerator yields signed infinity per IEEE 754; `0.0 / 0.0` yields `NaN`.

## 7. Essential Test Cases at Type-Conversion Boundaries

A good test suite tests not only input data but also **intermediate results** during type conversions.

### 7.1. `long` to `int`: Overflow or Error Detection

```java
long aboveInt = (long) Integer.MAX_VALUE + 1;
int truncated = (int) aboveInt; // -2147483648

// Math.toIntExact(aboveInt) throws ArithmeticException.
```

Casting `long` to `int` keeps the lower bits, so it can turn a large positive number into a negative one. If the conversion must be exact, use `Math.toIntExact(long)` (Java 8+).

### 7.2. `BigInteger` Has No Fixed `MAX_VALUE` Like `long`

`BigInteger` represents integers of arbitrary magnitude within memory limits. You can create a number exceeding `Long.MAX_VALUE` exactly:

```java
BigInteger beyondLong =
        BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);

System.out.println(beyondLong); // 9223372036854775808
```

The snippet above requires importing `java.math.BigInteger` and placing it inside a method when run. `beyondLong.longValue()` does not check for bit loss; `beyondLong.longValueExact()` throws `ArithmeticException`. Test cases should include the **last value that still fits in range**, and the **first value outside the range**.

### 7.3. `BigDecimal` Can Differ in Representation Even for the Same Zero

`new BigDecimal("0.00")` has scale 2, while `BigDecimal.ZERO` has scale 0:

```java
BigDecimal zero = new BigDecimal("0.00");

System.out.println(zero.signum());                 // 0
System.out.println(zero.compareTo(BigDecimal.ZERO)); // 0
System.out.println(zero.equals(BigDecimal.ZERO)); // false
```

This is an illustrative snippet requiring `import java.math.BigDecimal`. `signum()` and `compareTo()` check numerical value; `equals()` also checks scale. Therefore **tests for zero in `BigDecimal` should also check inputs with trailing zeros**, depending on business requirements.

When converting `BigDecimal` to `int`/`long`, use `intValueExact()`/`longValueExact()` if out-of-range or fractional values must be rejected. `intValue()`/`longValue()` can drop fractional digits and high-order bits without reporting an error.

### 7.4. Do Not Confuse `Double.MIN_VALUE` and `Integer.MIN_VALUE`

The constant names are the same, but their meanings differ:

- `Integer.MIN_VALUE` is the lower bound in numerical order, and is negative.
- `Double.MIN_VALUE` is the **smallest positive nonzero number**, not a negative lower bound.
- `BigDecimal` and `BigInteger` do not have a fixed-range `MIN_VALUE`/`MAX_VALUE` constant pair like primitives.

Therefore, do not write generic tests for every type assuming “`MIN_VALUE` is the most negative number”; check each type's contract.

## 8. Writing Framework-Independent Boundary Checks

A good test needs:

1. **Known inputs** and expected results derived from requirements.
2. Proper evaluation of sign, overflow, and exception semantics.
3. Not relying on Java's `assert` without `-ea` enabled, because assertions are disabled by default and may not execute; you can explicitly throw `AssertionError` or use JUnit.
4. Checks for cases just inside/just outside bounds, including 0.
5. Checks for conversions and calculations **after validation**, not validation alone.
6. When testing `double` for approximation algorithms, use a meaningful tolerance relative to magnitude or ULP; when testing exact behavior at adjacent values, use `Math.nextUp`/`Math.nextDown` and a specific expected value.

**File `BoundaryChecks.java` — standalone Java 17+ execution:**

```java
import java.math.BigDecimal;

public class BoundaryChecks {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static boolean inRange(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("Invalid bounds");
        }
        return value >= min && value <= max;
    }

    private static boolean isValidFiniteRatio(double value) {
        return Double.isFinite(value) && value >= 0.0 && value <= 1.0;
    }

    private static void expectArithmeticException(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected ArithmeticException");
        } catch (ArithmeticException expected) {
            // Test case passed: the operation must reject the data.
        }
    }

    public static void main(String[] args) {
        // Inclusive business range [0, 100].
        check(!inRange(-1, 0, 100), "below min");
        check(inRange(0, 0, 100), "at min");
        check(inRange(1, 0, 100), "above min");
        check(inRange(99, 0, 100), "below max");
        check(inRange(100, 0, 100), "at max");
        check(!inRange(101, 0, 100), "above max");

        // Physical bounds of the int type.
        check(Integer.MAX_VALUE + 1 == Integer.MIN_VALUE,
                "int overflow");
        expectArithmeticException(
                () -> Math.addExact(Integer.MAX_VALUE, 1));
        expectArithmeticException(
                () -> Math.toIntExact((long) Integer.MAX_VALUE + 1));

        // Double zeroes and adjacent values.
        check(0.0 == -0.0, "numeric zero comparison");
        check(Double.doubleToRawLongBits(0.0)
                != Double.doubleToRawLongBits(-0.0),
                "signed zero bits");
        check(Math.nextUp(0.0) == Double.MIN_VALUE,
                "successor of zero");
        check(Math.nextDown(0.0) == -Double.MIN_VALUE,
                "predecessor of zero");
        check(!isValidFiniteRatio(Double.NaN), "NaN rejected");
        check(!isValidFiniteRatio(Double.POSITIVE_INFINITY),
                "Infinity rejected");
        check(isValidFiniteRatio(0.0), "ratio min");
        check(isValidFiniteRatio(1.0), "ratio max");
        check(!isValidFiniteRatio(Math.nextUp(1.0)),
                "ratio just above max");

        // Decimal zero with different scales.
        BigDecimal scaledZero = new BigDecimal("0.00");
        check(scaledZero.compareTo(BigDecimal.ZERO) == 0,
                "numeric decimal zero");
        check(!scaledZero.equals(BigDecimal.ZERO),
                "BigDecimal scale preserved");

        System.out.println("All boundary checks passed");
    }
}
```

```bash
javac BoundaryChecks.java
java BoundaryChecks
```

Output:

```text
All boundary checks passed
```

`inRange` checks `min > max` to reject nonsensical configurations. Direct comparisons `value >= min && value <= max` **do not compute `max + 1`**, so they do not cause unintended overflow. In the `double` validator, checking `Double.isFinite` first actively rejects `NaN`/`Infinity`; just outside the upper bound is generated with `Math.nextUp(1.0)`, not by adding an arbitrary epsilon.

For projects using JUnit 5, the `check` conditions can be translated to `assertTrue`, `assertFalse`, `assertEquals`, and `assertThrows`; the test content remains the boundary cases designed from the specification.

## 9. Pitfalls in Testing Boundary-Adjacent Values

### 9.1. Do Not Compute `MIN_VALUE - 1` or `MAX_VALUE + 1` in an Integral Type

If you need to test “out of bounds” for `int`, **you cannot store that number in an `int` variable**. You must test at a parsing API boundary or in a wider type:

```java
// Parsing "2147483648" to int -> NumberFormatException.
Integer.parseInt("2147483648");

// Can be stored in long to test conversion:
long justAboveInt = (long) Integer.MAX_VALUE + 1;
```

The `Integer.parseInt` line illustrates a call that **will throw an exception** if executed, so in tests wrap it with `assertThrows`/try-catch as shown above.

### 9.2. Do Not Assume One Fixed Epsilon Works for All `double` Values

`Double.MIN_VALUE` is not a useful relative epsilon for general calculations. The gap between two adjacent `double` values near `1.0` is approximately `2.220446049250313E-16`, whereas near `1E20` the gap is much larger. Error checking needs **absolute/relative tolerances** suited to the problem; when testing bit/representable-number structure, use `Math.ulp` and `Math.nextUp/Down`.

### 9.3. Do Not Mechanically Use `==` as an Approximation Criterion

```java
System.out.println((0.1 + 0.2) == 0.3); // false
```

This is a consequence of binary representation, not proof that Java performs arithmetic incorrectly. Approximate numeric testing should have an explicit tolerance; conversely, for cases where the API specifies exact behavior such as signed-zero bits or `nextUp(0.0) == Double.MIN_VALUE`, exact checks are entirely appropriate.

### 9.4. Diagnosing Using Bits and Data Types

When investigating the difference between `+0.0` and `-0.0`, `==` is insufficient. Use `Double.doubleToRawLongBits` to inspect the sign representation; for `NaN`, use `Double.isNaN` and consider NaN payload normalization rules in each API. For `BigDecimal`, print `toPlainString()`, `scale()`, `precision()`, and `unscaledValue()` to understand why two values compare equal with `compareTo` yet differ under `equals`.

Diagnostic output should include the data type, value source, and transformation that produced the result, especially when overflow or underflow is suspected. Do not conclude from the way Java prints a decimal number that all of those digits exist exactly in `double`.

## 10. Quick Testing Matrix by Data Type

| Value type | Bounds and neighbors to test | Typical risks |
|---|---|---|
| `byte`, `short` | MIN, MIN+1, -1, 0, 1, MAX-1, MAX | Promotion to `int`, narrowing cast losing bits |
| `int`, `long` | MIN, MIN+1, -1, 0, 1, MAX-1, MAX | Addition/multiplication overflow, `abs(MIN)`, `MIN / -1` division |
| Integer division | denominator -1, 0, 1; numerator 0, MIN, MAX | Division by 0 throws, `MIN/-1` overflow |
| `float`, `double` | ±MAX_VALUE, ±MIN_NORMAL, ±MIN_VALUE, ±0.0, ±Infinity, NaN | Overflow, underflow, signed zero, NaN comparisons |
| `double` values right at a bound | `Math.nextDown(bound)`, `bound`, `Math.nextUp(bound)` | Adding an “epsilon” of the wrong magnitude |
| `BigDecimal` | 0, 0.00, numbers near specified thresholds, differing scales | Confusing `equals` with `compareTo`, rounding |
| `BigInteger` | `int`/`long` bounds ±1, very large negative values | `intValue`/`longValue` bit loss |

Not every class or method needs the entire matrix. Select cases based on the **input type, operations used, and specific business rules**. However, if a method contains addition, multiplication, division, casting, or bound comparisons, the corresponding boundary regions are almost always worth testing.

## 11. Exercises with Solutions

1. **What does `Integer.MAX_VALUE + 1` return?**  
   `-2147483648`, due to `int` overflow. `Math.addExact(Integer.MAX_VALUE, 1)` throws `ArithmeticException`.

2. **Is `Math.abs(Integer.MIN_VALUE)` positive?**  
   No, the result is still `-2147483648`. You must widen to `long` before calling `Math.abs` if you need the exact magnitude.

3. **Is `Double.MIN_VALUE` the smallest negative floating-point number?**  
   No. It is the smallest **positive nonzero** `double` value. The negative finite bound is `-Double.MAX_VALUE`.

4. **What is the representable `double` value immediately above `1.0`?**  
   `Math.nextUp(1.0)`, typically printed as `1.0000000000000002`.

5. **What does `+0.0 == -0.0` return? Are the two values completely identical in all operations?**  
   It returns `true`, yet their sign bits differ and `1.0 / +0.0` returns `Infinity` whereas `1.0 / -0.0` returns `-Infinity`.

6. **Why is using only `x < 0 || x > 1` insufficient to reject an invalid ratio?**  
   Because for `NaN`, both comparisons are `false`. `Double.isFinite(x)` is needed if only finite numbers are accepted.

7. **Why is `BigDecimal("0.00").equals(BigDecimal.ZERO)` `false`, while `compareTo` returns `0`?**  
   The two numbers have the same numerical value 0 but different scales; `equals` also considers scale, whereas `compareTo` considers only value.

8. **Is `Long.MAX_VALUE + 1` a `long` input larger than `Long.MAX_VALUE` for testing a function?**  
   No. The expression has already overflowed to `Long.MIN_VALUE`. To represent a mathematical number outside the `long` range, use `BigInteger` or a string input and test parsing/conversion methods.

## 12. Key Takeaways and References

Numeric testing must check **all three boundary layers**: **data-type bounds**, **operation bounds**, and **business bounds**. For integers, test MIN/MAX/0 and adjacent points using operations that do not overflow on their own; for `double`, test signed zero, positive MIN_VALUE, MIN_NORMAL, ±MAX_VALUE, NaN/infinities, and use `Math.nextUp`/`Math.nextDown` to produce boundary-adjacent values. Expectations for each case must follow the method contract, not intuition about ordinary arithmetic.

Official Java 21 documentation (the core APIs also work on Java 17 unless noted otherwise in Javadoc):

- [`Integer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html)
- [`Long`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html)
- [`Double`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
- [`Math`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [`BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [`BigInteger`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html)
