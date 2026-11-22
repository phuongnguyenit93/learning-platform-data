# `nextUp`, `nextDown`, `nextAfter`, and `ulp` in Java

When working with `float` and `double`, between two close real numbers there is not always a representable floating-point value. Java provides four methods in `Math` and `StrictMath` to find **adjacent representable values** and **spacing at machine precision**:

- `nextUp(x)`: the next representable value in the direction of positive infinity.
- `nextDown(x)`: the next representable value in the direction of negative infinity.
- `nextAfter(start, direction)`: the next representable value starting from `start` toward `direction`.
- `ulp(x)`: the size of one *unit in the last place* (ULP) at `x`.

They serve boundary testing, error analysis, and numerical algorithms; they are **not** functions for "adding an arbitrary tiny amount" or rounding decimals for display.

## 1. Why Are Adjacent Representable Numbers Needed?

Java uses the IEEE 754 binary format for its two standard floating-point types:

| Type | Length | Effective Significand Bits | Example ULP at `1.0` |
|---|---:|---:|---|
| `float` | 32 bits | 24 bits | `2^-23` ≈ `1.1920929e-7` |
| `double` | 64 bits | 53 bits | `2^-52` ≈ `2.220446049250313e-16` |

A finite set of bit patterns cannot represent every real number. For example, `1.0` is an exact `double` value, and the immediately greater `double` number is:

```text
1.0
↓ next double value
0x1.0000000000001p0  =  1.0000000000000002 (decimal form shortened when printed)
```

Here `0x...p...` is Java's hexadecimal binary floating-point literal notation: the part after `p` is a power of **2**, not 10. `Double.toHexString(...)` lets you observe exact representation steps more clearly than ordinary decimal printing.

The spacing between two adjacent numbers is **not constant** across the entire domain: around numbers of larger magnitude, steps are generally larger; around small numbers, steps are smaller, down to **subnormals**. Therefore, assuming you can always use `x + 1e-15` to reach the next number is wrong: addition may leave `x` unchanged, skip many values, or produce a result unsuitable for the data type.

> In this lesson, "adjacent" means **there is no representable `float`/`double` strictly between them** in numeric order. It does not mean two consecutive integers or decimals.

## 2. API and Direction Rules

Main overloads of `java.lang.Math`:

```java
public static double nextUp(double d);
public static float  nextUp(float f);

public static double nextDown(double d);
public static float  nextDown(float f);

public static double nextAfter(double start, double direction);
public static float  nextAfter(float start, double direction);

public static double ulp(double d);
public static float  ulp(float f);
```

`StrictMath` also provides corresponding methods with the same meaning. An easily overlooked detail is the `nextAfter(float, double)` overload taking **`direction` of type `double`** while **returning `float`**: the *start* value determines the representable grid being stepped across.

For a finite starting value not at a boundary case:

| Call | Interpretation |
|---|---|
| `Math.nextUp(x)` | One step to the right on the number line |
| `Math.nextDown(x)` | One step to the left on the number line |
| `Math.nextAfter(x, y)`, with `y > x` | One step from `x` toward `y`, like `nextUp(x)` |
| `Math.nextAfter(x, y)`, with `y < x` | One step from `x` toward `y`, like `nextDown(x)` |
| `Math.nextAfter(x, y)`, with `x == y` | Returns `direction` itself (important detail when two zeros have opposite signs) |
| `Math.ulp(x)` | Magnitude of ULP at `x`, always non-negative for finite inputs |

`nextAfter(start, direction)` **does not jump straight to `direction`**; it moves exactly one step on the value grid of `start`'s type, unless both values are already equal under numerical comparison (or hit `NaN`/special boundaries).

### Distinguishing `nextAfter` and `nextUp`/`nextDown`

```java
double x = 1.0;

Math.nextAfter(x, 2.0); // Same result as Math.nextUp(x)
Math.nextAfter(x, 0.0); // Same result as Math.nextDown(x)
Math.nextAfter(x, x);   // 1.0: already at the target direction
```

This is an **illustrative snippet**, not a standalone Java class. When only a fixed direction is needed, `nextUp`/`nextDown` express intent more directly; when direction depends on a target, `nextAfter` allows expressing general algorithms.

## 3. Runnable and Verified Java 17+ Program

Create file `FloatingNeighborsDemo.java` with contents:

```java
public class FloatingNeighborsDemo {
    public static void main(String[] args) {
        double x = 1.0;
        System.out.println("nextUp(1.0): " + Double.toHexString(Math.nextUp(x)));
        System.out.println("nextDown(1.0): " + Double.toHexString(Math.nextDown(x)));
        System.out.println("nextAfter(1.0, 2.0): " + Double.toHexString(Math.nextAfter(x, 2.0)));
        System.out.println("nextAfter(1.0, 0.0): " + Double.toHexString(Math.nextAfter(x, 0.0)));
        System.out.println("ulp(1.0): " + Double.toHexString(Math.ulp(x)));
        System.out.println("gap above: " + Double.toHexString(Math.nextUp(x) - x));
        System.out.println("gap below: " + Double.toHexString(x - Math.nextDown(x)));
        System.out.println("nextUp(-0.0): " + Double.toHexString(Math.nextUp(-0.0)));
        System.out.println("nextDown(+0.0): " + Double.toHexString(Math.nextDown(+0.0)));
        System.out.println("nextAfter(+0.0, -0.0): " + Double.toHexString(Math.nextAfter(+0.0, -0.0)));
        System.out.println("ulp(0.0): " + Double.toHexString(Math.ulp(0.0)));
        System.out.println("nextUp(MAX_VALUE): " + Math.nextUp(Double.MAX_VALUE));
        System.out.println("nextDown(+INFINITY) == MAX_VALUE: "
                + (Math.nextDown(Double.POSITIVE_INFINITY) == Double.MAX_VALUE));
        float f = 1.0f;
        System.out.println("nextAfter(1.0f, 2.0): " + Float.toHexString(Math.nextAfter(f, 2.0)));
        System.out.println("ulp(1.0f): " + Float.toHexString(Math.ulp(f)));
        System.out.println("NaN: " + Double.isNaN(Math.nextUp(Double.NaN)));
        System.out.println("StrictMath agrees: " + (StrictMath.nextUp(x) == Math.nextUp(x)));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 FloatingNeighborsDemo.java
java FloatingNeighborsDemo
```

Stdout verified by compiling and running the program:

```text
nextUp(1.0): 0x1.0000000000001p0
nextDown(1.0): 0x1.fffffffffffffp-1
nextAfter(1.0, 2.0): 0x1.0000000000001p0
nextAfter(1.0, 0.0): 0x1.fffffffffffffp-1
ulp(1.0): 0x1.0p-52
gap above: 0x1.0p-52
gap below: 0x1.0p-53
nextUp(-0.0): 0x0.0000000000001p-1022
nextDown(+0.0): -0x0.0000000000001p-1022
nextAfter(+0.0, -0.0): -0x0.0p0
ulp(0.0): 0x0.0000000000001p-1022
nextUp(MAX_VALUE): Infinity
nextDown(+INFINITY) == MAX_VALUE: true
nextAfter(1.0f, 2.0): 0x1.000002p0
ulp(1.0f): 0x1.0p-23
NaN: true
StrictMath agrees: true
```

**Key points from the output:**

1. `nextUp(1.0)` is the `double` immediately above `1.0`; `nextDown(1.0)` is the one immediately below. `nextAfter` yields those same two numbers when the target direction is above or below, respectively.
2. `ulp(1.0)` equals the step **above** `1.0`, whereas the step **below** is only half as large (because `1.0` is an exact power of 2, sitting on the boundary between two step regions).
3. `nextUp(-0.0)` and `nextDown(+0.0)` move to the smallest non-zero subnormal values, positive and negative respectively.
4. `nextAfter(+0.0, -0.0)` returns `-0.0` even though `+0.0 == -0.0` is `true`; hex notation reveals the sign.
5. At the upper finite boundary, the next step from `Double.MAX_VALUE` upward is `+Infinity`.
6. The `float` overload steps on the 32-bit grid, so the step around `1.0f` is larger than `double`'s step.

## 4. Understanding `ulp(x)` Accurately

ULP is the weighted unit of the last digit in floating-point representation at the magnitude under consideration. In the **normal** range, the step generally takes the form:

- `double`, with 53-bit precision: roughly `2^(e - 52)`;
- `float`, with 24-bit precision: roughly `2^(e - 23)`,

where `e` is the binary exponent of the value range under consideration. In the **subnormal** region, the spacing is fixed at the format's minimum resolution.

Example:

```java
Math.ulp(1.0);     // double: 2^-52
Math.ulp(2.0);     // double: 2^-51
Math.ulp(1.0f);    // float: 2^-23
Math.ulp(2.0f);    // float: 2^-22
Math.ulp(0.0);     // Double.MIN_VALUE (smallest positive non-zero double)
Math.ulp(0.0f);    // Float.MIN_VALUE  (smallest positive non-zero float)
```

These are illustrative expressions; to inspect output, you can print with `Double.toHexString` or `Float.toHexString`.

### `ulp(x)` Does Not Always Equal `nextUp(x) - x`

A misconception that easily causes test bugs is applying the identity `Math.ulp(x) == Math.nextUp(x) - x` for **all** `x`. At power-of-2 boundaries or when flipping sign, adjacent gaps on the two sides can differ.

For example, with `x = 1.0`:

| Quantity | Exact Result |
|---|---|
| `Math.ulp(1.0)` | `2^-52` |
| `Math.nextUp(1.0) - 1.0` | `2^-52` |
| `1.0 - Math.nextDown(1.0)` | `2^-53` |

With `x = -1.0`, the situation reverses: moving toward `+∞` approaches 0 and has step `2^-53`, while moving toward `-∞` has step `2^-52`; meanwhile `Math.ulp(-1.0)` remains `2^-52`. Therefore, if an algorithm needs the **gap in a specific direction**, use the two neighbor functions to measure the gap in that direction, combined with handling special values.

Do not take `ulp(x)` as a "guaranteed absolute error bound" for every computation. Error depends on the operation, algorithm, operand magnitudes, loss of significance, and number of steps. A ULP can be useful for measuring representational differences, but error tolerance rules must come from the problem's requirements.

### Why Is There No Single Fixed Epsilon?

`Math.ulp(0.0)` equals `Double.MIN_VALUE`, which is tiny; `Math.ulp(1.0)` is much larger, and `Math.ulp(1e20)` is larger still. Even `Math.ulp(1.0)` does not mean every computation has a maximum error of exactly that size.

In numerical testing, comparing by absolute error, relative error, or ULP count must account for the data domain and cases of 0, infinity, `NaN`, and overflow/underflow. Do not apply a fixed `epsilon` just because it has a familiar name.

## 5. Special Boundaries That Must Be Tested

`float` and `double` have two zeros (`+0.0`, `-0.0`), two infinities, `NaN`, and subnormal values. Thus you cannot infer every case solely from ordinary real-number intuition.

| Input | Result or Behavior |
|---|---|
| `Math.nextUp(+0.0)` or `Math.nextUp(-0.0)` | `Double.MIN_VALUE` |
| `Math.nextDown(+0.0)` or `Math.nextDown(-0.0)` | `-Double.MIN_VALUE` |
| `Math.nextAfter(+0.0, -0.0)` | `-0.0` (returns `direction` itself) |
| `Math.nextAfter(-0.0, +0.0)` | `+0.0` (returns `direction` itself) |
| `Math.nextUp(Double.MAX_VALUE)` | `Double.POSITIVE_INFINITY` |
| `Math.nextDown(-Double.MAX_VALUE)` | `Double.NEGATIVE_INFINITY` |
| `Math.nextDown(Double.POSITIVE_INFINITY)` | `Double.MAX_VALUE` |
| `Math.nextUp(Double.NEGATIVE_INFINITY)` | `-Double.MAX_VALUE` |
| `Math.nextUp(Double.POSITIVE_INFINITY)` | `Double.POSITIVE_INFINITY` |
| `Math.nextDown(Double.NEGATIVE_INFINITY)` | `Double.NEGATIVE_INFINITY` |
| `Math.nextAfter(Double.NaN, 1.0)` | `NaN` |
| `Math.nextAfter(1.0, Double.NaN)` | `NaN` |
| `Math.ulp(Double.NaN)` | `NaN` |
| `Math.ulp(Double.POSITIVE_INFINITY)` | `Double.POSITIVE_INFINITY` |

For the `float` overload, replace the corresponding constants with `Float.MIN_VALUE`/`Float.MAX_VALUE` and use `float` results. Do not confuse the name `Double.MIN_VALUE`: it is the **smallest positive non-zero number** representable by `double`, **not the most negative number**. The finite negative `double` with the largest magnitude is `-Double.MAX_VALUE`.

### Signed Zero and `nextAfter`

`+0.0 == -0.0` is `true` in Java arithmetic comparisons, but their bit patterns and some numerical behaviors differ. When `start` and `direction` are equal, the `nextAfter` spec returns the `direction` parameter itself, so:

```java
double result = Math.nextAfter(+0.0, -0.0);
boolean negativeZero =
        Double.doubleToRawLongBits(result) == Double.doubleToRawLongBits(-0.0);
// negativeZero == true
```

This snippet is illustrative code placed inside a method. If you use `== 0.0` to check the result, you **cannot distinguish** the two zero signs. To inspect bits, use `Double.doubleToRawLongBits`, `Float.floatToRawIntBits`, or appropriate hex formatting.

### Subnormals and the Smallest Limit

For `double`:

- `Double.MIN_NORMAL` is the **smallest positive normal** number (approx `2.225e-308`).
- `Double.MIN_VALUE` is the **smallest positive non-zero subnormal** number (approx `4.9e-324`).
- `Math.nextUp(0.0) == Double.MIN_VALUE`.
- `Math.nextDown(Double.MIN_VALUE)` returns `+0.0` because the closest representable value in the downward direction is zero.
- `Math.ulp(0.0)` and `Math.ulp(Double.MIN_VALUE)` both equal `Double.MIN_VALUE`.

This is why very small values do not have as many significant digits as normal values. When crossing the normal/subnormal boundary, test carefully because relative precision changes.

## 6. How Do `Math` and `StrictMath` Differ in This Lesson?

`nextUp`, `nextDown`, `nextAfter`, and `ulp` all exist on both `Math` and `StrictMath` with identical neighbor-handling rules. You can write:

```java
double a = Math.nextAfter(1.0, 2.0);
double b = StrictMath.nextAfter(1.0, 2.0);
// a and b are both the double value immediately above 1.0
```

This is illustrative code used inside a class/method. `StrictMath` is commonly mentioned when caring about result reproducibility of math operations; however, for these **four stepping operations on the representable grid**, boundary rules and return types are the focus. Do not generalize from this group of functions to every trigonometric or transcendental function without reading the specific API contract.

## 7. Practical Applications

### 7.1. Testing Tightly Around a Condition Boundary

Suppose a rule requires a `double` value to be **less than or equal to** `limit`:

```java
static boolean withinLimit(double value, double limit) {
    return value <= limit;
}
```

This is an illustrative method. With `limit = 1.0`, a boundary test suite can use three values:

```java
double limit = 1.0;
boolean below = withinLimit(Math.nextDown(limit), limit); // true
boolean exact = withinLimit(limit, limit);                // true
boolean above = withinLimit(Math.nextUp(limit), limit);  // false
```

Each test value is a representable point; no need to guess "a very small number" to add/subtract. When `limit` is infinite, `NaN`, or could involve overflow, define additional expectations and tests separately.

### 7.2. Stepping Toward a Target Milestone

If you need the **first step** from a `double` toward a target:

```java
double current = 1.0;
double target = 2.0;
double step = Math.nextAfter(current, target);
// step == Math.nextUp(current)
```

One step of `nextAfter` is typically tiny; do not use it to iterate arbitrarily from `1.0` to `2.0`. Between those two values lies a huge number of `double`s, and stepping one by one would be far too slow. If iteration is truly needed, include a step cap, termination condition, and handling for `NaN`, infinity, and lack of progress.

### 7.3. Measuring Differences on the Number Grid

`ulp(...)` helps interpret discrepancies near a reference, such as observing the difference between `1.0` and the `double` immediately above it:

```java
double baseline = 1.0;
double observed = Math.nextUp(baseline);

double delta = observed - baseline;
double oneUlpAtBaseline = Math.ulp(baseline);
// delta == oneUlpAtBaseline, true for baseline = 1.0
```

In this specific example, the difference is exactly one ULP at `baseline`; for values at power-of-two boundaries or negative numbers, do not assume the gap between two neighbors in **every direction** equals `ulp(baseline)`. To measure exact ULP distance for numbers over a wide range, you typically need to compare ordered normalized bit representations and handle `NaN`, signed zero, and infinity.

## 8. Common Mistakes

**Mistake 1 — `Math.nextUp(x)` equals `x + Math.ulp(x)` in all cases.** The addition formula works at some points, but fails at boundaries like infinity, `NaN`, and does not consistently describe left/right directional gaps. Use `nextUp` directly when the goal is finding the upper neighbor.

**Mistake 2 — `nextAfter(start, direction)` always returns `direction`.** When the two numbers differ, it advances by only **one representable value**; the `direction` parameter determines the direction of movement.

**Mistake 3 — `Math.nextAfter(1.0f, 2.0)` steps in `double` increments.** The overload with `start` of type `float` returns `float`, so the result is right next to `1.0f` by a `float` step. Always check the first operand's type and the `f` suffix on literals.

**Mistake 4 — `Float.MIN_VALUE` is the smallest negative number.** It is the smallest positive non-zero number; on the negative side immediately below 0 is `-Float.MIN_VALUE`. The finite negative number with the largest magnitude is `-Float.MAX_VALUE`.

**Mistake 5 — Ignoring `+0.0` and `-0.0`.** `==` treats them as equal, yet `nextAfter(+0.0, -0.0)` returns the target `-0.0`. Test using raw bits if the sign of 0 is an important condition.

**Mistake 6 — Treating `ulp(x)` as an accuracy threshold for all operations.** `ulp` is a property of the representable number grid, not a quality guarantee of an algorithm. For approximate comparisons, define tolerance rules per problem.

**Mistake 7 — Computing the direction via an expression that already rounds back to `start`.** For instance, `1.0 + 1e-20` evaluates in `double` to `1.0`, so `Math.nextAfter(1.0, 1.0 + 1e-20)` returns `1.0` instead of stepping up. If the goal is simply the next representable number above `1.0`, call `Math.nextUp(1.0)`.

**Mistake 8 — Using representation steps to replace financial rounding rules.** `ulp` relates to binary precision, not decimal places after the decimal point. When decimal rules are needed, consider `BigDecimal`/`RoundingMode` per business specification.

## 9. Self-Check Questions

Predict the answers before running in JShell or a Java class:

1. What is `Math.nextUp(-0.0)`?
2. What is `Math.nextDown(Double.POSITIVE_INFINITY)`?
3. Does `Math.nextAfter(1.0, 1.0)` move?
4. Why is `Math.nextUp(1.0) - 1.0` different from `1.0 - Math.nextDown(1.0)`?
5. Why does `Math.nextAfter(1.0f, 2.0)` take a larger step than `Math.nextAfter(1.0, 2.0)`?
6. Is `Math.ulp(Double.NaN)` a finite real number usable as a tolerance?

**Answers:** (1) `Double.MIN_VALUE`; (2) `Double.MAX_VALUE`; (3) no, returns `1.0`; (4) `1.0` sits right on a binary boundary, so gaps on the two sides are `2^-52` and `2^-53`; (5) `float` has 24 bits of effective precision while `double` has 53 bits; (6) no, the result is `NaN`.

## Key Takeaways

- `nextUp`/`nextDown`: neighbor in a fixed direction on the number line; `nextAfter`: neighbor toward a target.
- The grid of **type `float` or `double`** determines the step size, and the `float` overload of `nextAfter` takes a `double` direction.
- `ulp(x)` indicates the step unit at magnitude `x`; do not automatically equate it with the distance in **every direction**.
- Always test signed zero, subnormals, maximum finite values, infinity, and `NaN`.
- To inspect individual values clearly, use `Double.toHexString(...)`, `Float.toHexString(...)`, and raw-bit methods when zero sign matters.
