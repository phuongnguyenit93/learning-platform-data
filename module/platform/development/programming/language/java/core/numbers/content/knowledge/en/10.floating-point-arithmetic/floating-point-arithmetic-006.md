# Impact of Signed Zero on Division and Math Functions in Java

## 1. Objectives and Opening Question

Java has two floating-point values representing **zero**: `+0.0` (positive zero) and `-0.0` (negative zero). These two values **compare equal with the `==` operator**, yet they **cannot be substituted for each other in every operation**. The sign of zero can determine the sign of infinity during division, the sign of the result of certain math functions, sorting order via `Double.compare`, and raw data when serializing.

Look at these two statements:

```java
System.out.println(+0.0 == -0.0); // true
System.out.println(1.0 / -0.0);    // -Infinity
```

There is no contradiction: `==` on primitives compares according to floating-point arithmetic rules; division inspects the signs of both operands. This is an important topic in **Java Core — Numbers / Floating-Point Arithmetic**.

After this lesson, you will be able to:

1. Understand the bit patterns of `+0.0` and `-0.0` in `float`/`double`.
2. Predict the result of `/` when the denominator or numerator is signed zero; distinguish `Infinity`, `-Infinity`, and `NaN`.
3. Analyze the impact of zero's sign on `Math.abs`, `Math.signum`, `Math.copySign`, `Math.min`, `Math.max`, `Math.sqrt`, `Math.ceil`, `Math.floor`, `Math.rint`, `Math.atan2`, and `Math.pow`.
4. Distinguish primitive `==` comparison from `Double.compare`/`Double.equals` and their effects on collections.
5. Correctly read raw bits, check the sign of zero, and preserve the sign when truly needed—without confusing it with epsilon or integer type casting.

The examples **run with Java 17+** and require no libraries outside the JDK.

## 2. Two Zeros in IEEE 754 binary32/binary64

Java's `float` type uses the **binary32** format consisting of 1 sign bit, 8 exponent bits, and 23 fraction bits. The `double` type uses **binary64** consisting of 1 sign bit, 11 exponent bits, and 52 fraction bits.

Zero in both formats has an **all-0 exponent field and an all-0 fraction field**; the sign bit determines whether it is `+0.0` or `-0.0`.

| Value | Type | Hexadecimal Bit Pattern |
| --- | --- | --- |
| `+0.0f` | `float` | `0x00000000` |
| `-0.0f` | `float` | `0x80000000` |
| `+0.0` | `double` | `0x0000000000000000` |
| `-0.0` | `double` | `0x8000000000000000` |

The mathematical value "magnitude equal to 0" is split into two bit patterns to help floating-point arithmetic retain useful sign information, especially when a very small result **underflows** to zero or when dividing by zero.

In Java, `-0.0` is an expression applying the unary minus operator to the literal `0.0`; the result is negative zero. `Double.toString(-0.0)` prints `-0.0`, while `Double.toString(+0.0)` prints `0.0`. This shows that default printing preserves the sign, even though `==` treats both values as equal.

### 2.1. Inspecting the Bits Yourself

```java
double plus = +0.0;
double minus = -0.0;

System.out.printf("%016X%n", Double.doubleToRawLongBits(plus));
System.out.printf("%016X%n", Double.doubleToRawLongBits(minus));
```

Stdout:

```text
0000000000000000
8000000000000000
```

This is a **code snippet** that must be placed inside a Java method before running. `Double.doubleToRawLongBits` returns the 64-bit pattern, completely different from casting `(long) minus`—casting a floating-point number to an integer yields `0L`, not the "raw signed-zero bits".

There is a corresponding API for `float`: `Float.floatToRawIntBits`. When checking NaN, note that raw methods have a different contract from `doubleToLongBits`/`floatToIntBits`, which canonicalize multiple NaN patterns. For **zero**, both raw and non-raw return the exact sign pattern.

## 3. `==` Treats +0.0 and -0.0 as Equal, Yet the Bits Differ

```java
double positive = +0.0;
double negative = -0.0;

System.out.println(positive == negative); // true
System.out.println(positive != negative); // false
System.out.println(positive < negative);  // false
System.out.println(positive > negative);  // false
```

Primitive comparison operators do not order `-0.0` as less than `+0.0`. However, there are at least three **different** ways to ask about zero:

| Question | Expression | For `-0.0` vs `+0.0` |
| --- | --- | --- |
| Are the two values equal under arithmetic `==`? | `a == b` | `true` |
| Are the two IEEE 754 bit patterns identical? | `Double.doubleToRawLongBits(a) == Double.doubleToRawLongBits(b)` | `false` |
| In the total ordering for wrappers, which is smaller? | `Double.compare(a, b)` | `-0.0` comes before `+0.0` |

**Consequence:** if an application only asks "is the value numerically equal to zero?", using `value == 0.0` is appropriate and matches both signs. If the application wants to **distinguish the sign of zero**, `==` is not enough. Conversely, if all zeros must be treated as equivalent at the business level, using a comparator that distinguishes both signs may be inappropriate.

## 4. Division With Zero: The Sign of the Result Cannot Be Ignored

Sign rule for floating-point division: **same signs give a positive result, opposite signs give a negative result**, except in cases yielding NaN. This rule applies to zero and infinity under Java's IEEE 754 specification.

### 4.1. A Finite Non-Zero Number Divided by ±0.0

| Expression | Result |
| --- | --- |
| `1.0 / +0.0` | `Infinity` |
| `1.0 / -0.0` | `-Infinity` |
| `-1.0 / +0.0` | `-Infinity` |
| `-1.0 / -0.0` | `Infinity` |

Even though `+0.0 == -0.0` is `true`, you **must not** deduce `1.0 / +0.0 == 1.0 / -0.0`. The two sides are positive infinity and negative infinity respectively.

```java
System.out.println(1.0 / +0.0);
System.out.println(1.0 / -0.0);
System.out.println(-1.0 / +0.0);
System.out.println(-1.0 / -0.0);
```

Stdout:

```text
Infinity
-Infinity
-Infinity
Infinity
```

That is the **rule for `double`**, not "integer division". If both operands are `int`/`long`, dividing by `0` throws `ArithmeticException` at runtime when the division is executed.

### 4.2. Zero as Numerator, Finite Non-Zero Denominator

| Expression | Result |
| --- | --- |
| `+0.0 / 2.0` | `0.0` |
| `-0.0 / 2.0` | `-0.0` |
| `+0.0 / -2.0` | `-0.0` |
| `-0.0 / -2.0` | `0.0` |

The result is still numerically zero, yet the **sign of zero** follows the division sign rule. If that result is passed into a subsequent division, its sign can flip infinity:

```java
double tinyResult = +0.0 / -2.0; // -0.0
double reciprocal = 1.0 / tinyResult; // -Infinity
```

This example shows how silently replacing every zero value with `+0.0` can alter downstream behavior.

### 4.3. Zero Divided by Zero and Infinity

Other boundary rules to remember:

- `+0.0 / +0.0`, `+0.0 / -0.0`, `-0.0 / +0.0`, and `-0.0 / -0.0` all yield **`NaN`**.
- A finite number divided by `+Infinity` or `-Infinity` produces **signed zero**, signed according to the two operands if neither is NaN.
- `Infinity / Infinity` and `-Infinity / Infinity` yield `NaN`.
- If either operand is `NaN`, the division result is `NaN`.

Example:

```java
System.out.println(0.0 / -0.0);                 // NaN
System.out.println(3.0 / Double.NEGATIVE_INFINITY); // -0.0
System.out.println(Double.isNaN(0.0 / 0.0));     // true
```

Use `Double.isNaN(result)` or `Double.isInfinite(result)` when you need to **check status**; do not check NaN with `result == Double.NaN` because NaN is not equal to itself under primitive `==`.

### 4.4. Distinguishing `1 / 0` from `1.0 / 0.0`

`1 / 0` is integer division by zero (such a constant expression can be a compile error in constant-expression contexts; integer division by zero executed at runtime throws `ArithmeticException`). `1.0 / 0.0` is floating-point division returning `Infinity`.

Under the JLS, floating-point divisions do not throw a runtime exception solely because of division by zero, overflow, underflow, or loss of information. Nevertheless, the program **still has to decide** whether to accept `Infinity` or `NaN` as a business result.

## 5. Zeros Produced Through Addition, Subtraction, and Multiplication

Signed zero does not only come from the literal `-0.0`. Multiplying a zero by a negative number can flip the sign:

```java
System.out.println(-0.0 * 2.0);  // -0.0
System.out.println(-0.0 * -2.0); // 0.0
System.out.println(0.0 * -2.0);  // -0.0
```

Addition and subtraction have their own zero-sign rules. For example, under Java's default rounding mode:

```java
System.out.println(-0.0 + +0.0); // 0.0
System.out.println(-0.0 + -0.0); // -0.0
```

This leads to an important warning: an expression transformation often considered obvious in **real-number algebra** may not preserve **every floating-point result bit**. For example, adding `+0.0` to an expression can turn `-0.0` into `+0.0`.

**Do not conclude floating-point addition is always associative**: rounding, overflow, underflow, and signed zero can all create differences between differently parenthesized expressions. When bitwise reproducible results are required, examine any optimized or transformed expressions and adhere to Java/JLS semantics.

## 6. `Math.abs`, `Math.signum`, and `Math.copySign`

Three methods easily confused because all their names relate to sign:

| `double` Expression | Result | Meaning |
| --- | --- | --- |
| `Math.abs(-0.0)` | `0.0` | Returns non-negative magnitude, drops negative sign |
| `Math.signum(-0.0)` | `-0.0` | Preserves signed zero |
| `Math.signum(+0.0)` | `0.0` | Preserves signed zero |
| `Math.copySign(2.5, -0.0)` | `-2.5` | Uses magnitude of first operand, sign of second operand |
| `Math.copySign(0.0, -1.0)` | `-0.0` | Can create negative zero |
| `Math.copySign(-0.0, 1.0)` | `0.0` | Can create positive zero |

### 6.1. `Math.abs`: Removes the Sign of Negative Zero

`Math.abs(-0.0)` is `+0.0`. If you want to **normalize** every zero to positive for display or business rules, this is one way; however, it also turns finite negative numbers positive, so it is unsuitable when you must **change only zero**.

If you only want to normalize the two zeros:

```java
static double normalizeZero(double value) {
    return value == 0.0 ? 0.0 : value;
}
```

This is a **method snippet**, not a standalone Java file. It leaves non-zero values—including `NaN` and infinity—unchanged, while turning `-0.0` into `+0.0`. Apply it only when **explicitly required**: normalizing zero can flip the sign of a subsequent division result.

### 6.2. `Math.signum`: Does Not Lose the Sign of Zero

`Math.signum(-0.0)` returns `-0.0`, not `0.0` or the integer `-1`. `Math.signum(+0.0)` returns `+0.0`. For finite non-zero numbers, `signum` returns ±1.0; for NaN, it returns NaN.

If you are looking for an arithmetic "sign value of -1, 0, +1" while needing to distinguish negative zero, `signum` still returns **floating-point signed zero**. To obtain a distinct `int` code for negative zero, design an explicit convention and inspect raw bits.

### 6.3. `Math.copySign`: Intentionally Copying the Sign Bit

`Math.copySign(magnitude, sign)` uses the **magnitude of the first argument** and the **sign of the second argument**. With zero inputs, it can preserve or create negative zero. Example:

```java
double negativeMagnitude = Math.copySign(5.0, -0.0); // -5.0
double negativeZero = Math.copySign(0.0, -3.0);       // -0.0
```

`Math.copySign` is not the same as `Math.signum`. For NaN, sign-bit details can depend on the API/contract of each method, so read the `Math`/`StrictMath` documentation for your target JDK version if specific NaN payload/sign handling is required.

## 7. `Math.min` and `Math.max` Distinguish Signed Zero

This case often surprises developers: even though `-0.0 == +0.0` is `true`, `Math.min` and `Math.max` on `double`/`float` **treat negative zero as strictly less than positive zero**.

```java
System.out.println(Math.min(-0.0, +0.0)); // -0.0
System.out.println(Math.max(-0.0, +0.0)); // 0.0
```

Even if you swap the two arguments, the same ±0 pair will still yield `-0.0` for `min` and `+0.0` for `max`. The `int`/`long` overloads have no separate concept of signed zero.

| Method | With -0.0 and +0.0 | With one NaN argument |
| --- | --- | --- |
| `Math.min` (`double`/`float`) | Returns `-0.0` | Returns NaN |
| `Math.max` (`double`/`float`) | Returns `+0.0` | Returns NaN |

Therefore, if an algorithm aggregates minimum/maximum values over multiple steps, keep **the sign of zero in data** in mind, especially if reciprocals or raw bits are produced afterward.

**Do not mechanically replace `Math.min(a,b)` with `a < b ? a : b`** when full IEEE 754 contract compliance is needed, because primitive comparison does not distinguish signed zero and has different rules for NaN. Nor should you assume every custom min/max expression is equivalent to the standard API.

## 8. `Math.sqrt`, `Math.ceil`, `Math.floor`, `Math.rint`, and Signed Zero

Real-number methods can accept and return negative zero:

| Expression | Result |
| --- | --- |
| `Math.sqrt(-0.0)` | `-0.0` |
| `Math.cbrt(-0.0)` | `-0.0` |
| `Math.ceil(-0.5)` | `-0.0` |
| `Math.floor(-0.0)` | `-0.0` |
| `Math.rint(-0.4)` | `-0.0` |
| `Math.abs(-0.0)` | `+0.0` |

### 8.1. Square Root of Negative Zero

`Math.sqrt(-0.0)` returns **`-0.0`**, even though learners sometimes think a square root can never be negative. The negative zero result is preserved per the method's floating-point contract, and is not "the square root of a finite negative number".

Distinguish clearly:

- `Math.sqrt(-0.0)` → `-0.0`.
- `Math.sqrt(-1.0)` → `NaN`.

Both `+0.0` and `-0.0` are zero under `==`, yet `sqrt` can distinguish them at the output bit level.

### 8.2. Rounding Near Zero From the Negative Side

`Math.ceil(-0.5)` returns `-0.0`: the mathematical ceiling of `-0.5` is zero, but the result sign is negative under `ceil`'s contract. `Math.rint(-0.4)` can also return `-0.0` when rounding to the nearest integer representable in type `double`.

`Math.floor(-0.0)` preserves `-0.0`. When applying `Math.floor(-0.5)`, however, the result is `-1.0`; do not equate `floor` and `ceil`.

**Type-conversion trap:** if you cast `(int) Math.ceil(-0.5)`, the final value becomes `0` of type `int` and loses the zero sign bit. When you need to keep the original floating-point representation intact, do not convert through integer types.

### 8.3. Some Always-Non-Negative Functions Can Still Drop the Sign

`Math.abs` intentionally returns magnitude. Methods like `Math.hypot` representing non-negative length are likewise not designed to preserve the sign of zero from an input axis. Read the contract of **each function**, rather than inferring from the generic phrase "math function".

## 9. `Math.atan2`: The Sign of Zero Determines the Angle at the Branch Cut

`Math.atan2(y, x)` returns an angle in radians when processing a coordinate pair, and has special rules for signed zero. Among them:

- `Math.atan2(+0.0, -1.0)` = `+π`.
- `Math.atan2(-0.0, -1.0)` = `-π`.

Example:

```java
System.out.println(Math.atan2(+0.0, -1.0));
System.out.println(Math.atan2(-0.0, -1.0));
```

Stdout:

```text
3.141592653589793
-3.141592653589793
```

This is useful in geometry, graphics, orientation representation, and angle ranges from `-π` to `+π`. Both coordinates have `y` **equal to zero under `==`**, yet the sign of zero lets `atan2` choose the **side of the branch cut**.

Do not replace `atan2(y,x)` with `atan(y/x)` when full angle handling is needed: that loses quadrant information, can produce infinity/NaN at `x = 0`, and is not equivalent in many special cases.

### 9.1. Common Coordinate Scenarios

For `x > 0`:

- `Math.atan2(+0.0, x)` returns `+0.0`.
- `Math.atan2(-0.0, x)` returns `-0.0`.

For `x < 0`:

- `Math.atan2(+0.0, x)` returns `+π`.
- `Math.atan2(-0.0, x)` returns `-π`.

Other trigonometric functions have their own contracts (for example, `Math.sin(-0.0)` returns `-0.0`), but do not assume **every** function preserves the sign of zero: consult the Java SE `Math` or `StrictMath` documentation for your target JDK version.

## 10. `Math.pow` and the Sign of Zero by Exponent

Some cases of `Math.pow` depend on the sign of zero and the exponent, particularly **odd vs. even integer exponents**:

| Expression | Result |
| --- | --- |
| `Math.pow(-0.0, 3.0)` | `-0.0` |
| `Math.pow(-0.0, 2.0)` | `+0.0` |
| `Math.pow(-0.0, -3.0)` | `-Infinity` |
| `Math.pow(-0.0, -2.0)` | `Infinity` |

Interpretation: the negative sign of a zero base is preserved for odd integer powers (when the result is zero or infinity); for even integer powers the result has a positive sign. This matches intuition from multiplication/division sign rules, though `Math.pow` has many special branches for NaN, infinity, and non-integer exponents.

When boundary behavior must be guaranteed, verify **specific values and the contract**. Do not substitute manual multiplication for `Math.pow` or vice versa while blindly claiming all boundary cases preserve bit patterns.

## 11. `Math.nextUp` and `Math.nextDown` Crossing Zero

`Math.nextUp(x)` returns the **next representable floating-point value in the direction of +∞**; `Math.nextDown(x)` returns the next value in the direction of −∞.

At zero:

```java
System.out.println(Math.nextUp(-0.0) == Double.MIN_VALUE);
System.out.println(Math.nextDown(+0.0) == -Double.MIN_VALUE);
```

Stdout:

```text
true
true
```

`Double.MIN_VALUE` is the **smallest positive non-zero number** in binary64 (subnormal), not the smallest finite negative number. `nextUp`/`nextDown` reflect the ordering of representable numbers **by value**: `+0.0` and `-0.0` compare numerically equal, yet have two distinct bit patterns.

Do not confuse the result of applying `nextUp`/`nextDown` with the `Double.compare` relation on zeros; these APIs serve different purposes. To compare the raw bits of two zeros, use bit APIs rather than going indirectly through `nextUp`.

## 12. `Double.compare` and `Double.equals` Differ from `==`

Primitive `==` comparison:

```java
System.out.println(-0.0 == +0.0); // true
```

Comparison under the **total ordering** of wrappers:

```java
System.out.println(Double.compare(-0.0, +0.0)); // -1
System.out.println(Double.valueOf(-0.0)
        .equals(Double.valueOf(+0.0))); // false
```

`Double.compare` orders `-0.0` strictly below `+0.0`. `Double.equals` is based on bit representation after canonicalizing NaN, so it treats ±0 as **unequal**. This makes `Double`'s equality/comparison relations compatible with usage in `HashSet`, `HashMap`, and `TreeSet`.

Similarly, `Float.compare(-0.0f, +0.0f)` returns a negative number and `Float.valueOf(-0.0f).equals(Float.valueOf(+0.0f))` is false.

### 12.1. Impact on Collections

```java
java.util.Set<Double> zeros = new java.util.HashSet<>();
zeros.add(+0.0);
zeros.add(-0.0);
System.out.println(zeros.size()); // 2
```

This is a **code snippet**; place it inside a method to run. When added to `HashSet<Double>`, auto-boxing creates two `Double` objects that are distinct under `equals`. Therefore, the set has **2 elements**, even though primitive `+0.0 == -0.0` is true.

If business requirements dictate merging the two zeros into a single key, you must **intentionally normalize** before inserting into a map/set. For example:

```java
double value = -0.0;
double normalized = value == 0.0 ? 0.0 : value;
```

However, if the value is used for reciprocals, geometric analysis, or retaining raw IEEE bits, normalization can discard necessary information. **The decision to keep or merge signed zero must follow requirements**, not be applied mechanically across all systems.

### 12.2. Why Is NaN Comparison Also Different?

`Double.compare` also defines an ordering for NaN, whereas `==` with NaN is always false. `Double.equals` treats canonicalized NaNs as equivalent. That is why you need to know whether you are using **primitive mathematical comparison**, **collection ordering**, or **bit-pattern inspection**.

## 13. Complete Java Program A: Dividing by Signed Zero

Save as **`SignedZeroDivision.java`**:

```java
public class SignedZeroDivision {
    public static void main(String[] args) {
        double positive = +0.0;
        double negative = -0.0;

        System.out.println(positive == negative);

        System.out.println(1.0 / positive);
        System.out.println(1.0 / negative);
        System.out.println(-1.0 / positive);
        System.out.println(-1.0 / negative);

        System.out.println(negative / 2.0);
        System.out.println(positive / -2.0);
        System.out.println(negative / -2.0);

        System.out.println(positive / negative);
        System.out.println(3.0 / Double.NEGATIVE_INFINITY);
    }
}
```

Compile/run with JDK 17+:

```bash
javac --release 17 SignedZeroDivision.java
java SignedZeroDivision
```

**Exact stdout:**

```text
true
Infinity
-Infinity
-Infinity
Infinity
-0.0
-0.0
0.0
NaN
-0.0
```

Group-by-group explanation:

1. The `true` line only states that the two zeros are equal under primitive comparison.
2. The four infinity lines demonstrate the **same-sign / opposite-sign** rule.
3. The three zero-result lines demonstrate the sign of the quotient.
4. `0.0 / -0.0` yields NaN, with no finite numerical sign.
5. `3.0 / -Infinity` yields negative zero according to the sign rule.

Do not feed `-Infinity` into a business calculation unchecked, because it can cause infinity/NaN propagation in subsequent steps.

## 14. Complete Java Program B: Signed Zero in `Math`

Save as **`SignedZeroMath.java`**:

```java
public class SignedZeroMath {
    public static void main(String[] args) {
        System.out.println(Math.min(-0.0, +0.0));
        System.out.println(Math.max(-0.0, +0.0));
        System.out.println(Math.abs(-0.0));
        System.out.println(Math.signum(-0.0));

        System.out.println(Math.copySign(2.5, -0.0));
        System.out.println(Math.copySign(0.0, -1.0));

        System.out.println(Math.sqrt(-0.0));
        System.out.println(Math.ceil(-0.5));
        System.out.println(Math.floor(-0.0));
        System.out.println(Math.rint(-0.4));

        System.out.println(Math.atan2(+0.0, -1.0));
        System.out.println(Math.atan2(-0.0, -1.0));

        System.out.println(Math.pow(-0.0, 3.0));
        System.out.println(Math.pow(-0.0, -3.0));
    }
}
```

Run:

```bash
javac --release 17 SignedZeroMath.java
java SignedZeroMath
```

**Exact stdout:**

```text
-0.0
0.0
0.0
-0.0
-2.5
-0.0
-0.0
-0.0
-0.0
-0.0
3.141592653589793
-3.141592653589793
-0.0
-Infinity
```

These cases were chosen because the sign of zero is **specified by the API contract**. Other `Math` methods may have their own rules for signed zero, NaN, and infinity; always check the documentation for the exact JDK version your project supports.

## 15. Complete Java Program C: Bits, Equality, and Ordering

Save as **`SignedZeroIdentity.java`**:

```java
import java.util.HashSet;
import java.util.Set;

public class SignedZeroIdentity {
    public static void main(String[] args) {
        double positive = +0.0;
        double negative = -0.0;

        System.out.printf("%016X%n", Double.doubleToRawLongBits(positive));
        System.out.printf("%016X%n", Double.doubleToRawLongBits(negative));

        System.out.println(positive == negative);
        System.out.println(Double.compare(negative, positive));
        System.out.println(Double.valueOf(negative)
                .equals(Double.valueOf(positive)));

        Set<Double> values = new HashSet<>();
        values.add(positive);
        values.add(negative);
        System.out.println(values.size());

        System.out.println(Math.nextUp(negative) == Double.MIN_VALUE);
        System.out.println(Math.nextDown(positive) == -Double.MIN_VALUE);
    }
}
```

Run:

```bash
javac --release 17 SignedZeroIdentity.java
java SignedZeroIdentity
```

**Exact stdout:**

```text
0000000000000000
8000000000000000
true
-1
false
2
true
true
```

Here there are three distinct questions: `==` determines arithmetic equivalence, raw bits determine **bit identity**, and wrappers/collections determine **equivalence/ordering** per `Double`'s contract.

## 16. Checking and Preserving Signed Zero in Real Programs

### 16.1. Only Needing to Know Whether a Value Is Zero

Use:

```java
boolean isZero = value == 0.0;
```

This matches both positive zero and negative zero; `NaN` does not match. This is the right choice when the sign of zero **has no business meaning**.

### 16.2. Needing to Identify Negative Zero Specifically

Use raw bits or check the sign component of zero:

```java
static boolean isNegativeZero(double x) {
    return Double.doubleToRawLongBits(x) == 0x8000000000000000L;
}
```

This method is true **only for negative zero**, without treating every negative number or a NaN with sign bit 1 as negative zero. It is a **method snippet** that must be placed inside a class.

Another check relies on division: `x == 0.0 && 1.0 / x == Double.NEGATIVE_INFINITY`. However, raw bits usually express intent more clearly and avoid making readers think you are attempting division by an invalid denominator.

### 16.3. Needing to Preserve the Sign When Transferring Data

- Use `Double.doubleToRawLongBits`/`Double.longBitsToDouble` when the contract requires preserving IEEE 754 bits.
- If stored as a decimal string via `Double.toString`, `-0.0` will appear explicitly as `"-0.0"`. However, external systems may normalize it when parsing or mapping.
- When passing through integer types, fixed-point decimal formats, financial data, databases, or interchange protocols, verify end-to-end whether the sign of zero is preserved. **Do not assume** every numeric format supports signed zero like IEEE 754.
- If normalizing to `+0.0` is required, perform it once at the system boundary and document the convention clearly.

### 16.4. Boundary Tests You Should Have

| Target | Test Cases |
| --- | --- |
| Division | `1.0/+0.0`, `1.0/-0.0`, `-1.0/-0.0` |
| Zero/zero | `0.0/0.0`, `-0.0/+0.0` → NaN |
| Zero from other ops | `-0.0*2.0`, `-0.0+-0.0`, `-0.0++0.0` |
| Math functions | `Math.min/max` of ±0, `abs`, `signum`, `copySign` |
| Rounding | `Math.ceil(-0.5)`, `Math.rint(-0.4)` |
| Angles | `Math.atan2(±0.0,-1.0)` |
| Bit identity | `doubleToRawLongBits(±0.0)` |
| Collections | Both `Double` ±0 as keys |
| Special values | `NaN`, `Infinity`, `Double.MIN_VALUE` |

**Tip:** do not rely solely on `==` in unit tests that must distinguish negative and positive zero; compare raw bits or sign-sensitive operations. For comparators/collections, verify the `equals` and `compareTo` contracts properly.

## 17. Common Misconceptions

1. **"`+0.0 == -0.0` so they are interchangeable."** False. Reciprocal division and several math functions distinguish their signs.
2. **"Dividing by floating-point zero always throws an exception."** False; it usually returns ±Infinity or NaN. Only `int`/`long` division by 0 throws `ArithmeticException` at runtime.
3. **"`Math.abs(-0.0)` preserves the sign."** False; it returns +0.0.
4. **"`Math.signum(-0.0)` returns -1.0."** False; it returns -0.0.
5. **"`Math.min(+0.0,-0.0)` arbitrarily returns either zero."** False; the floating-point overloads specify the result is -0.0.
6. **"`Math.atan2(0.0,-1.0)` doesn't care about the sign of 0."** False; +0 gives +π, while -0 gives -π.
7. **"`Double.equals` uses the exact same rule as primitive `==`."** False; the wrapper distinguishes the two zeros and handles NaN under its own contract.
8. **"`HashSet<Double>` definitely merges ±0."** False; by default it can store both because `equals` differs.
9. **"Casting `(long) -0.0` keeps the sign bit."** False; numeric casting yields integer 0, losing the signed-zero bit.
10. **"`Double.MIN_VALUE` is the smallest negative number."** False; it is the smallest positive non-zero subnormal.
11. **"Output `-0.0` is a number-printing bug."** No; `Double.toString` preserves the sign to reflect the IEEE 754 distinction.
12. **"Every -0.0 can be normalized to +0.0 without affecting the program."** False if the sign of zero affects downstream computations.
13. **"Every math function handles signed zero the same way."** False; you must check the contract of each function.
14. **"NaN can be checked with `== Double.NaN`."** False; use `Double.isNaN`.

## 18. Exercises With Solutions

### Exercise 1 — Two Equal Values, Two Opposite-Sign Results

Given `double a=+0.0, b=-0.0;`, evaluate `a == b`, `1.0 / a`, and `1.0 / b`.

**Answer:** `true`, `Infinity`, `-Infinity`. `==` does not compare the sign bits of zero in arithmetic comparison, whereas division follows the sign rules.

### Exercise 2 — Same Sign and Opposite Sign

Evaluate `-2.0 / +0.0` and `-2.0 / -0.0`.

**Answer:** `-Infinity` and `Infinity`. Division of two operands with the same sign is positive; with opposite signs, negative.

### Exercise 3 — Zero Divided by Zero

Does `-0.0 / -0.0` give negative zero, positive zero, or NaN?

**Answer:** `NaN`. Zero divided by zero has no defined finite or infinite quotient.

### Exercise 4 — Three Sign-Handling Functions

Predict `Math.abs(-0.0)`, `Math.signum(-0.0)`, and `Math.copySign(2.5,-0.0)`.

**Answer:** `0.0`, `-0.0`, and `-2.5`. `abs` drops the sign, `signum` preserves negative zero, and `copySign` takes the sign of the second argument.

### Exercise 5 — Min/Max of Signed Zero

What do `Math.min(-0.0,+0.0)` and `Math.max(-0.0,+0.0)` return?

**Answer:** `-0.0` and `0.0` per the `Math` contract.

### Exercise 6 — Boundary Angles

Compare `Math.atan2(+0.0,-1.0)` and `Math.atan2(-0.0,-1.0)`.

**Answer:** `+π` and `-π`. The sign of the y coordinate indicates the side of the branch cut.

### Exercise 7 — Wrapper vs. Primitive

Why is `-0.0 == +0.0` true while `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` is false?

**Answer:** Primitive `==` follows floating-point numerical equality; `Double.equals` is based on bit conversion that distinguishes negative/positive zero.

### Exercise 8 — Exact Sign Detection

Write a condition that is true only for `double x = -0.0`, and false for `+0.0` or `-Double.MIN_VALUE`.

**Answer:** `Double.doubleToRawLongBits(x) == 0x8000000000000000L`.

### Exercise 9 — Square Root

Evaluate `Math.sqrt(-0.0)` and `Math.sqrt(-1.0)`.

**Answer:** `-0.0` and `NaN`. Negative zero is preserved; finite non-zero negative numbers have no real square root in `double`.

### Exercise 10 — Rounding Toward Zero

What do `Math.ceil(-0.5)`, `Math.floor(-0.5)`, and `Math.rint(-0.4)` return?

**Answer:** `-0.0`, `-1.0`, `-0.0`. The sign of zero is preserved in the results of `ceil`/`rint`.

### Exercise 11 — Testing Collections

Add `+0.0` and `-0.0` to a `HashSet<Double>` and call `size()`. What is the result?

**Answer:** `2`. `Double.equals` distinguishes negative/positive zero, even though primitive `==` treats them as equal.

### Exercise 12 — Deciding on Normalization

Should an API that only checks "is mass equal to zero?" distinguish ±0? Can an API computing `1.0/x` discard the sign of zero?

**Answer:** The first usually only needs `x == 0.0`, without distinguishing sign; the second **cannot** drop the sign if it needs to preserve the exact sign of infinity and IEEE 754 semantics. The decision must be based on the data's purpose.

## 19. Completion Checklist

- [ ] I know the exact bit patterns of `+0.0` and `-0.0` for `float`/`double`.
- [ ] I can explain why primitive `==` returns true even though sign-aware division produces two opposite infinities.
- [ ] I can distinguish `±0.0`, `±Infinity`, and `NaN` results in `/` division.
- [ ] I know `Math.abs` drops the negative zero sign, while `Math.signum` preserves it.
- [ ] I know `Math.copySign` can create negative zero and `Math.min/max` choose the zero sign by contract.
- [ ] I understand that `Math.sqrt`, `Math.ceil`, `Math.floor`, and `Math.rint` can return signed zero.
- [ ] I can explain why `Math.atan2(+0.0,-1.0)` differs from `Math.atan2(-0.0,-1.0)`.
- [ ] I distinguish `Double.compare`/`equals` from `==` when using collections.
- [ ] I use raw bits to detect negative zero accurately without confusing it with small negative numbers or NaN.
- [ ] I have a clear rationale before **keeping** or **normalizing** signed zero in data.
- [ ] I ran the three Java 17+ examples and checked the boundary values.

**Official Reference Documentation:**

- [Java SE 17 — Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): signed zero, `compare`, `equals`, `doubleToRawLongBits`, `toString`.
- [Java SE 17 — Float API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): binary32 layout and raw bits APIs.
- [Java SE 17 — Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `abs`, `signum`, `copySign`, `min`, `max`, `sqrt`, `ceil`, `floor`, `rint`, `atan2`, `pow`.
- [JLS 17 `15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17): floating-point multiplication/division semantics, signed zero, and infinity.
- [JLS 17 `15.18 — Additive Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18): floating-point addition/subtraction.
- [JLS 17 `15.21.1 — Numerical Equality](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21.1): `==` and NaN/zero.

**Conclusion:** signed zero is **sign information stored in the floating-point representation**, not just a printing quirk. When building Java algorithms with `double`/`float`, do not infer from `+0.0 == -0.0` that they are interchangeable in division or every math function. To get the right result, identify whether you need **value equality**, **raw bit identity**, or the **sign-handling rules** of each operation and API.