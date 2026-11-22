# The `==`, `!=`, `<`, `<=`, `>`, and `>=` Operators When Comparing Floating-Point Numbers in Java

Java allows comparing `float` and `double` values using six operators: **`==`, `!=`, `<`, `<=`, `>`, and `>=`**. They return a `boolean` and use Java's **floating-point comparison semantics**, not approximate comparison based on mathematical intuition.

Key points:

- `==` checks whether **two numeric values are equal according to floating-point comparison**, not whether "two numbers are close to each other."
- `!=` returns the negation of `==`, even for `NaN`.
- `<`, `<=`, `>`, and `>=` check ordering relationships. **If either operand is `NaN`, all four ordering comparisons evaluate to `false`.**
- **`NaN == NaN` is `false`**, whereas **`NaN != NaN` is `true`**.
- **`+0.0 == -0.0` is `true`**, even though their bit patterns differ.
- `float`/`double` values have finite binary precision. Therefore, `0.1 + 0.2 == 0.3` can be `false`, which is not a compiler bug.

To compare computed values that have rounding error, you need a **tolerance rule determined by the problem domain**. To sort all values, including `NaN` and `-0.0`, you can use `Double.compare`/`Float.compare` with ordering rules that **differ** from the primitive operators.

## 1. How Do the Six Operators Work?

| Operator | Meaning | Example | Result |
| --- | --- | --- | --- |
| `==` | Equal in value according to primitive comparison | `1.5 == 1.5` | `true` |
| `!=` | Not equal | `1.5 != 2.5` | `true` |
| `<` | Less than | `1.5 < 2.5` | `true` |
| `<=` | Less than or equal to | `2.5 <= 2.5` | `true` |
| `>` | Greater than | `2.5 > 1.5` | `true` |
| `>=` | Greater than or equal to | `2.5 >= 2.5` | `true` |

When both operands are finite non-`NaN` numbers, they follow the familiar arithmetic ordering. The operators return `boolean`, not -1/0/1.

```java
double x = 1.5;
double y = 2.5;

boolean a = x == y; // false
boolean b = x != y; // true
boolean c = x < y;  // true
boolean d = x <= y; // true
boolean e = x > y;  // false
boolean f = x >= y; // false
```

For `<`, `<=`, `>`, and `>=`, both operands must be numeric types that can be compared with relational operators. Java does not support ordering comparison of two `String` values with `<`; `String` uses its own comparison method such as `compareTo` if the problem requires it.

## 2. Operand Promotion Rules Before Comparison

When comparing two values of different primitive numeric types, Java applies **binary numeric promotion**. If one operand is `double`, the other is converted to `double`; if there is a `float` and no `double`, the comparison uses `float`; for integer types, the integer promotion rules apply.

```java
float f = 0.1f;
double d = 0.1;

boolean equal = f == d; // false
```

Why is `equal` false? The literal `0.1f` is already rounded to `float` precision (24 bits of effective significand). When `f` is widened to `double` for comparison, it carries the rounded `float` value and does **not restore** the exact same value pattern as the `double` literal `0.1`. Thus, even though both look like "0.1" in source code, the two values can differ.

Another example:

```java
int i = 16_777_217;
float f = 16_777_216f;

boolean same = i == f; // true: int is converted to float and rounded
```

`16_777_217` cannot be represented exactly in `float`, so when converted for comparison with `f`, it can be rounded to `16_777_216f`. Therefore, **`==` is not guaranteed to detect differences between all integers** when mixing `float` with large `int`/`long` values. Avoid mixing types when exact integer comparison is required; convert to an appropriate type before losing precision.

For the `Double`/`Float` wrappers, you also need to consider unboxing rules and `equals` (Section 8). Do not assume that all objects holding numbers use the same semantics as primitive operators.

## 3. Why Is `0.1 + 0.2 == 0.3` `false`?

`float` and `double` use a binary representation with finite precision. Many decimal fractions such as `0.1`, `0.2`, and `0.3` cannot be represented exactly in finite binary form. An addition rounds the result according to floating-point rules.

```java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(actual);             // 0.30000000000000004
System.out.println(actual == expected); // false
System.out.println(actual != expected); // true
```

In this case, `==` is **working correctly**: the two resulting `double` values are genuinely not identical. The mistake lies in expecting `double` arithmetic to produce exact decimal representations.

**This does not mean you should never use `==` with `double`.** There are cases where `==` is the right choice: checking a clearly designed finite sentinel value, comparing two values produced through the same representation process when exact equality is needed, or comparing with `0.0` when equality to zero is semantically appropriate and `NaN` is handled separately. The key question is the **goal of the comparison**: exact equality of `double` values or proximity within an allowed tolerance.

### Finite Precision Also Affects Ordering Comparisons

```java
float big = 16_777_216f;
boolean stillSame = (big + 1 == big); // true
```

In this range, the spacing between two consecutive representable `float` values is 2. When adding 1, the result falls halfway between two representable values and rounds back to `big` under the round-to-nearest, ties-to-even rule. Therefore, the comparison yields `true`, even though in real arithmetic $x + 1 > x$.

Choosing the right domain and numeric type is essential before concluding whether floating-point comparisons reflect the ordering of the **original mathematical values**.

## 4. How `NaN` Changes Intuition About `==`, `!=`, and Ordering

`NaN` (*Not a Number*) is a special value that can result from operations with no well-defined real numeric result, such as `0.0 / 0.0`. Both `Float.NaN` and `Double.NaN` are NaN.

In primitive floating-point comparisons, NaN is considered **unordered** with respect to every value, **including NaN itself**:

| Expression | Result |
| --- | --- |
| `Double.NaN == Double.NaN` | `false` |
| `Double.NaN != Double.NaN` | `true` |
| `Double.NaN < 1.0` | `false` |
| `Double.NaN <= 1.0` | `false` |
| `Double.NaN > 1.0` | `false` |
| `Double.NaN >= 1.0` | `false` |
| `1.0 < Double.NaN` | `false` |
| `1.0 >= Double.NaN` | `false` |

This also holds for `float` comparisons involving `Float.NaN`.

**An easily overlooked logical consequence:** With NaN, `!(a < b)` is `true`, whereas `a >= b` is `false`. Therefore, rewriting `!(x < y)` as `x >= y` is **not equivalent** if `x` or `y` can be NaN. Similarly, `!(x <= y)` is not synonymous with `x > y` when NaN is present. The rule "not less than implies greater than or equal to" holds only when data is guaranteed to be **non-NaN**.

`!=` is the direct negation of `==`, so when NaN is involved, `!=` is `true` even if both variables hold the same NaN value in floating-point storage.

### Checking for NaN Properly

```java
double value = Double.NaN;

boolean wrong = value == Double.NaN; // false
boolean isNan = Double.isNaN(value);  // true
```

Do not use `value == Double.NaN` to detect NaN. You could rely on `value != value` based on NaN's property, but `Double.isNaN(value)`/`Float.isNaN(value)` expresses intent more clearly and is easier to read.

If you need to exclude both NaN and infinity, use `Double.isFinite(value)` or `Float.isFinite(value)` before performing computations or ordering comparisons.

## 5. `+0.0` and `-0.0`: Equal Under Operators, Different Bit Patterns

IEEE 754 has two representations of zero: **positive zero** and **negative zero**. Java treats them as equal under primitive operators:

```java
double positive = +0.0;
double negative = -0.0;

boolean eq = (positive == negative); // true
boolean ne = (positive != negative); // false
boolean lt = (negative < positive);  // false
boolean le = (negative <= positive); // true
boolean gt = (negative > positive);  // false
boolean ge = (negative >= positive); // true
```

However, the sign bit of zero can affect other operations:

```java
double p = 1.0 / +0.0; // +Infinity
double n = 1.0 / -0.0; // -Infinity
```

`Double.doubleToLongBits(0.0)` and `Double.doubleToLongBits(-0.0)` return two different bit patterns. The same applies to `Float.floatToIntBits`. **If you only use `==`, you are choosing the arithmetic semantics that both zeros are equal**; it is not a tool for inspecting the sign bit.

When you need to distinguish bits for binary formats or calculations sensitive to the sign of zero, use the bit APIs or `Double.compare`/`Float.compare` with its additional ordering rules instead of relying on `==`.

## 6. `+Infinity` and `-Infinity`: Ordered When There Is No NaN

Unlike NaN, infinities participate in floating-point ordering according to the familiar rule:

\[
-\infty < \text{every finite number} < +\infty
\]

Examples:

```java
boolean a = Double.POSITIVE_INFINITY > Double.MAX_VALUE; // true
boolean b = Double.NEGATIVE_INFINITY < -Double.MAX_VALUE; // true
boolean c = Double.POSITIVE_INFINITY == (1.0 / 0.0);     // true
boolean d = Double.POSITIVE_INFINITY == Double.NEGATIVE_INFINITY; // false
```

Even though they have an ordering relationship, infinities are usually **not valid input data** for real-world ratios, prices, measurements, or counters. Many operations can turn finite data into infinity via overflow or floating-point division by zero; you must decide explicitly whether this state is allowed.

**Do not confuse** floating-point division by zero with integer division by zero: `1.0 / 0.0` returns `Infinity`, whereas integer division `1 / 0` (when executed) throws `ArithmeticException`; Java may report an error earlier if it is an invalid constant expression in a context requiring a constant.

## 7. When to Use Approximate Comparison Instead of `==`?

For the results of many `double` calculations, you sometimes need to treat two values as "nearly equal" within an **application-defined error threshold**, instead of requiring `==`.

A common approach combines **absolute tolerance** and **relative tolerance**:

\[
|a-b| \leq \max(\text{absTol},\ \text{relTol}\cdot\max(|a|,|b|)).
\]

- `absTol` suits a fixed error bound, especially **near 0**.
- `relTol` suits cases where number magnitudes vary over many orders of magnitude, helping bound error proportionally.
- Thresholds must **be determined from the unit of measurement, business requirements, and algorithm characteristics**; there is no single fixed epsilon that works for every problem.

Illustrative method example:

```java
static boolean nearlyEqual(double a, double b, double absTol, double relTol) {
    if (Double.isNaN(a) || Double.isNaN(b)) return false;
    if (a == b) return true; // Includes two infinities of the same sign and ±0.0
    if (!Double.isFinite(a) || !Double.isFinite(b)) return false;

    double delta = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return delta <= Math.max(absTol, relTol * scale);
}
```

This is a **method snippet** that needs to be placed inside a class. It assumes the caller passes **finite, non-negative, appropriately chosen** thresholds. If this is an API for untrusted data, you should validate `absTol` and `relTol` (not NaN/Infinity, non-negative), and also consider the risk of overflow in subtraction or in multiplying to form the threshold when absolute values are very large.

**Important:** `nearlyEqual` is not a universal replacement for `==`:

- A "nearly equal" relation with positive tolerance is **generally not transitive**. It is possible for `a` to be close to `b` and `b` close to `c`, while `a` is not close to `c`.
- Therefore, do not use approximate equality directly to define `equals`/`hashCode` or sorting comparators, which require a consistent contract.
- Do not use `Double.MIN_VALUE` as a default absolute epsilon: it is the **smallest positive subnormal number**, not a representative error when adding and subtracting multiple `double` values.
- Proximity near **0** requires an appropriate absolute bound; using relative tolerance alone can be counterintuitive when both numbers are very small.
- For currency and exact decimal-digit requirements, `BigDecimal` with `RoundingMode` is more appropriate in many cases, though an explicit precision policy must be declared.

If the goal is to detect **bit changes**, use the bit APIs. If the goal is to compare **exact `double` values**, use `==`. If you need to compare **closeness according to a measurement**, use a specifically defined tolerance. These are three different requirements.

## 8. Comparing Primitives vs. `Double.compare`, `Float.compare`, and Wrapper `equals`

When you need to **sort** a list containing NaN or signed zero, primitive operators cannot establish a valid total order over all values: NaN makes all `<`/`>` comparisons `false`.

Java provides:

```java
int orderDouble = Double.compare(a, b);
int orderFloat = Float.compare(x, y);
```

The return value is **negative, zero, or positive** (not necessarily strictly -1, 0, or 1 in every comparison API) according to a defined ordering. For `Double.compare`/`Float.compare`:

- `-Infinity` is less than every finite number, and `+Infinity` is greater than every finite number.
- **`-0.0` is less than `+0.0`**, even though primitive `-0.0 == +0.0` is `true`.
- **NaN is considered greater than all other values**, including `+Infinity`.
- NaNs are considered **equal in comparison** because NaN bit patterns are treated under canonical semantics.

Examples:

```java
int z = Double.compare(-0.0, +0.0); // Negative value (-1 in current JDK)
int n = Double.compare(Double.NaN, Double.POSITIVE_INFINITY); // Positive value
int bothNaN = Double.compare(Double.NaN, Double.NaN); // 0
```

`Double.valueOf(0.0).equals(Double.valueOf(-0.0))` is `false`; `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` is `true`. Wrapper `equals` uses semantics consistent with `Double.compare` for the corresponding values, which **differs** from primitive `==` for signed zero and NaN.

If both operands are `Double` wrapper objects, the `==` operator between them can perform **reference comparison**, not numeric comparison. When one side is primitive and Java applies unboxing, it becomes a numeric comparison; unboxing `null` throws `NullPointerException`. When working with collections, choose `equals` or an appropriate comparator instead of using `==` on two wrapper objects.

**Sorting properly:**

```java
double[] values = { Double.NaN, +0.0, -0.0, Double.POSITIVE_INFINITY };
java.util.Arrays.sort(values);
// [-0.0, 0.0, Infinity, NaN] according to Double.compare ordering
```

Do not write a comparator using `(int) (a - b)`, because the difference may be a very small number that casts to 0, may overflow to infinity, and for NaN produces 0 under integer casting rules. Such a comparator can violate sorting requirements.

## 9. Java 17+ Program Verifying the Six Operators and Edge Cases

Save to `FloatingComparisonDemo.java`:

```java
public class FloatingComparisonDemo {
    static boolean nearlyEqual(double a, double b, double absTol, double relTol) {
        if (Double.isNaN(a) || Double.isNaN(b)) return false;
        if (a == b) return true;
        if (!Double.isFinite(a) || !Double.isFinite(b)) return false;

        double delta = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return delta <= Math.max(absTol, relTol * scale);
    }

    public static void main(String[] args) {
        double a = 0.1 + 0.2, b = 0.3;
        System.out.println("sum: " + a);
        System.out.println("sum == 0.3: " + (a == b));
        System.out.println("sum != 0.3: " + (a != b));
        System.out.println("near sum: " + nearlyEqual(a, b, 1e-12, 1e-9));

        System.out.println("1 < 2: " + (1.0 < 2.0));
        System.out.println("2 <= 2: " + (2.0 <= 2.0));
        System.out.println("2 > 1: " + (2.0 > 1.0));
        System.out.println("2 >= 2: " + (2.0 >= 2.0));

        double nan = Double.NaN;
        System.out.println("NaN == NaN: " + (nan == nan));
        System.out.println("NaN != NaN: " + (nan != nan));
        System.out.println("NaN < 1: " + (nan < 1));
        System.out.println("NaN <= 1: " + (nan <= 1));
        System.out.println("NaN > 1: " + (nan > 1));
        System.out.println("NaN >= 1: " + (nan >= 1));

        System.out.println("+0 == -0: " + (0.0 == -0.0));
        System.out.println("1/+0: " + (1.0 / 0.0));
        System.out.println("1/-0: " + (1.0 / -0.0));
        System.out.println("Infinity > MAX: "
            + (Double.POSITIVE_INFINITY > Double.MAX_VALUE));
        System.out.println("-Infinity < MIN: "
            + (Double.NEGATIVE_INFINITY < -Double.MAX_VALUE));

        float f = 0.1f;
        System.out.println("0.1f == 0.1: " + (f == 0.1));
        float big = 16_777_216f;
        System.out.println("float next equals: " + (big + 1 == big));

        System.out.println("compare -0,+0: " + Double.compare(-0.0, +0.0));
        System.out.println("compare NaN,+Infinity: "
            + Double.compare(Double.NaN, Double.POSITIVE_INFINITY));
        System.out.println("compare NaN,NaN: " + Double.compare(Double.NaN, Double.NaN));
        System.out.println("boxed zeros equals: "
            + Double.valueOf(0.0).equals(Double.valueOf(-0.0)));
        System.out.println("boxed NaNs equals: "
            + Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN)));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac FloatingComparisonDemo.java
java FloatingComparisonDemo
```

Stdout:

```text
sum: 0.30000000000000004
sum == 0.3: false
sum != 0.3: true
near sum: true
1 < 2: true
2 <= 2: true
2 > 1: true
2 >= 2: true
NaN == NaN: false
NaN != NaN: true
NaN < 1: false
NaN <= 1: false
NaN > 1: false
NaN >= 1: false
+0 == -0: true
1/+0: Infinity
1/-0: -Infinity
Infinity > MAX: true
-Infinity < MIN: true
0.1f == 0.1: false
float next equals: true
compare -0,+0: -1
compare NaN,+Infinity: 1
compare NaN,NaN: 0
boxed zeros equals: false
boxed NaNs equals: true
```

**Reading the output:** The first lines show how exact comparison between two rounded `double` values differs from tolerance-based comparison. The `NaN` lines demonstrate that all ordering relational operators are false, `==` is false, and `!=` is true. The `±0` and infinity lines illustrate the difference between numeric value equality and the sign of zero. Finally, `Double.compare` and wrapper `equals` demonstrate rules for sorting and collections, which are not identical to primitive `==`.

## 10. Designing Safe Comparison Conditions

### Input Domain Validation

If the system only accepts finite numeric results, **validate upfront**:

```java
static boolean inRange(double value, double min, double max) {
    return Double.isFinite(value)
        && value >= min
        && value <= max;
}
```

This is an **illustrative code snippet**: use it only when `min` and `max` are verified finite bounds with `min <= max`. Checking `isFinite` clearly expresses the requirement to reject NaN/Infinity; while `>=` and `<=` already return false for NaN, they do not exclude infinities across all domains if the bounds are not finite.

### Avoid Carelessly Inverting Conditions When NaN Is Possible

If you want to reject every value **not less than a threshold** or NaN, do not blindly rewrite `!(x < threshold)` as `x >= threshold` because they behave differently with NaN.

```java
double x = Double.NaN;
boolean notLess = !(x < 10.0); // true
boolean greaterOrEqual = x >= 10.0; // false
```

When you want a condition that behaves predictably with NaN, write it explicitly:

```java
boolean accepted = Double.isFinite(x) && x >= 0.0 && x <= 10.0;
```

### When Approximate Equality Checks Are Needed

Use purposeful names such as `nearlyEqual` or `withinTolerance` and pass `absTol`/`relTol` parameters according to the unit of measurement. Do not apply an arbitrary tolerance to compare map keys, identifiers, transaction IDs, or every value in a problem.

### When a Stable Ordering for Sorting Is Needed

Use `Double.compare`/`Float.compare`, or `Comparator.comparingDouble` when working with objects and `double` fields. If the data may contain `NaN`, decide whether this comparator's "NaN sorts last" rule is appropriate, or whether you should filter the data first.

## 11. Common Misconceptions

1. **"Two expressions that are mathematically equal in decimal must compare equal with `==`."** False: `double` has representation and rounding errors.
2. **"`!=` is also false with NaN because it cannot be compared."** False: `NaN != NaN` is true.
3. **"Not less than definitely means greater than or equal to."** False with NaN: `!(x < y)` can be true while `x >= y` is false.
4. **"`NaN == NaN` is true because both sides are NaN."** False: primitive `==` returns false; use `Double.isNaN` to check.
5. **"`+0.0` and `-0.0` differ under `==` because their sign bits differ."** False: `+0.0 == -0.0` is true.
6. **"`Double.compare` works identically to `<`, `>`, and `==` for all values."** False: it distinguishes signed zero and defines a position for NaN.
7. **"Just use `Double.MIN_VALUE` as the epsilon for approximate comparison."** False: it is the smallest positive number and is usually inappropriate for algorithmic error bounds.
8. **"Approximate tolerance can replace `equals` and `hashCode`."** False: approximate equality is generally not transitive, so it is not a valid equivalence relation for many collections.
9. **"`0.1f` and `0.1` are definitely equal after promotion."** False: `float` was already rounded at lower precision before being widened to `double`.
10. **"Comparing floating-point numbers by casting their difference to `int` makes a good comparator."** False: it loses small differences, handles NaN incorrectly, and can break the comparator contract.
11. **"Infinities are always unordered."** False: only NaN is unordered; `-Infinity` and `+Infinity` are ordered.
12. **"Using `==` on two `Double` wrappers always compares numeric values."** False: two objects may undergo reference comparison; `equals` and unboxing have separate rules.

## 12. Self-Check Questions

- What is the result of `Double.NaN == Double.NaN`? **false**.
- What is the result of `Double.NaN != Double.NaN`? **true**.
- With `x = Double.NaN`, are `!(x < 3.0)` and `x >= 3.0` equal? **No**: the results are true and false, respectively.
- Is `-0.0 == 0.0` true? **True**; however, `Double.compare(-0.0, 0.0)` returns a negative value.
- What is `Double.POSITIVE_INFINITY > Double.MAX_VALUE`? **true**.
- Given `float a = 0.1f; double b = 0.1;`, is `a == b` guaranteed to be true? **No**: in this example it is false due to `float` rounding.
- If you want "nearly equal" within a specific measurement error, what should you use? **A comparison function with tolerance chosen for the domain/units**, checking NaN and infinity according to policy.
- If you need to sort a list containing NaN and signed zero, what should you use? **`Double.compare`/`Float.compare`** or a comparator following business ordering rules, not `(int)(a-b)`.

**Remember:** The six operators on `float`/`double` compare the **represented floating-point values**, without automatically applying an error tolerance. `NaN` makes `==` and the four ordering relational operators evaluate to false, while `!=` evaluates to true. `+0.0` and `-0.0` are equal under primitive `==`, whereas standard comparators distinguish them. When approximate comparison or sorting is needed, choose **a dedicated rule suited to your goal**, rather than extrapolating directly from infinite-precision real-number mathematics.
