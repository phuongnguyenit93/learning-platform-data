# Distinguishing `==`, `equals`, and Comparison Ordering of Floating-Point Numbers in Java 17

## 1. Why Must Floating-Point Comparisons Be Understood Separately?

In Java, `float` and `double` represent real numbers using IEEE 754 binary floating-point format. This representation is efficient for scientific and engineering computation, but **not every decimal number has a finite, exact binary representation**. Consequently, two calculations that appear to produce the same mathematical result can yield slightly different `double` values.

Additionally, Java has both primitive types `double`/`float` and wrapper types `Double`/`Float`. The same `==` symbol can mean numeric value comparison or object identity comparison. `equals()` and `compareTo()` each have their own rules, especially for `NaN` and `+0.0`/`-0.0`.

The goal of this lesson is choosing the right comparison for the question being asked:

- Are two primitive values equal under Java's arithmetic operator?
- Do two wrappers refer to the same object, or do they have equal contents under the `equals` contract?
- Which value comes before another in a sort order?
- Are two computed results close enough within the problem's allowed error?
- Does the data require exact decimal numbers such as currency?

This Java knowledge remains applicable today. The examples use stable Java 17 syntax and APIs.

## 2. Background: Binary Floating-Point Does Not Store Every Decimal Exactly

### 2.1. `float` and `double`

| Type | Size | Format | Approximate Decimal Precision |
|---|---:|---|---:|
| `float` | 32 bits | IEEE 754 binary32 | About 6–7 significant digits |
| `double` | 64 bits | IEEE 754 binary64 | About 15–16 significant digits |

`double` has higher precision and a larger representable range than `float`, so it is usually the default choice for floating-point computation. However, both are **approximate** representations for many decimal fractions.

Example:

```java
double a = 0.1;
double b = 0.2;
double c = 0.3;

System.out.println(a + b);       // Typically displays 0.30000000000000004
System.out.println(a + b == c);  // false
```

Mathematically, \(0.1 + 0.2 = 0.3\). However, `0.1`, `0.2`, and `0.3` are rounded to the nearest representable binary64 numbers. The addition result is also rounded, so it may not equal the exact value stored for the literal `0.3`.

This is not a bug in the `==` operator. The calculation took place on approximate binary values; exact comparison accurately reflects the actual values in memory.

### 2.2. Not Every Number Is Approximate

Integers within an appropriate range and fractions whose denominators are powers of 2 can be represented exactly. For instance, `0.5`, `0.25`, and `1.75` have finite binary representations. Conversely, `0.1` has a repeating binary expansion and cannot be stored exactly in binary32/binary64.

Do not conclude that every `double` comparison is wrong. If a program needs to check a sentinel value, an integer represented exactly within range, or a result produced and checked by the same deterministic flow, `==` can still be an intentional comparison. Understand the data and requirements before choosing.

## 3. `==` with Primitive `float` and `double`

When both operands are floating-point primitives, `==` compares **floating-point values** according to Java's rules:

```java
double x = 1.5;
double y = 1.5;

System.out.println(x == y); // true
```

With approximate calculation results:

```java
double x = 0.1 + 0.2;
double y = 0.3;

System.out.println(x == y); // false
```

There is no automatic epsilon applied when using `==`. It is an exact comparison of the two stored binary floating-point values.

### 3.1. Other Relational Operators

Operators `<`, `>`, `<=`, and `>=` also compare numeric values, though special values require attention:

```java
double a = 2.0;
double b = 3.0;

System.out.println(a < b);  // true
System.out.println(a > b);  // false
System.out.println(a <= b); // true
System.out.println(a >= b); // false
```

When an operand is `NaN`, **every relational comparison evaluates to false**, including equality:

```java
double n = Double.NaN;

System.out.println(n == n);  // false
System.out.println(n != n);  // true
System.out.println(n < 1.0); // false
System.out.println(n > 1.0); // false
System.out.println(n <= 1.0); // false
System.out.println(n >= 1.0); // false
```

Therefore, do not use `x == Double.NaN` to check for NaN. Use:

```java
if (Double.isNaN(x)) {
    System.out.println("Value is not a number");
}
```

### 3.2. `+0.0` and `-0.0`

IEEE 754 has two signed zero representations:

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(positiveZero < negativeZero);  // false
System.out.println(positiveZero > negativeZero);  // false
```

Under arithmetic operators, the two values compare equal. However, zero's sign can still affect certain operations:

```java
System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
```

If an application cares about the sign of zero (e.g., specialized numerical calculations, signal processing, or numerical algorithms), `==` cannot distinguish the two cases. `Double.compare`, `Double.equals`, and `Double.compareTo` have rules to distinguish them, covered later.

### 3.3. Infinity and Special Values

`double` can represent positive and negative infinity:

```java
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeInfinity = Double.NEGATIVE_INFINITY;

System.out.println(positiveInfinity > 1.0); // true
System.out.println(negativeInfinity < -1.0); // true
System.out.println(positiveInfinity == Double.POSITIVE_INFINITY); // true
System.out.println(Double.isInfinite(positiveInfinity)); // true
```

Before performing approximate comparison, sorting, or exporting data, determine whether the problem allows `NaN`/infinity. `Double.isFinite(x)` returns false for NaN and both infinities.

## 4. `==` with Wrapper `Double` and `Float`

`Double` and `Float` are **objects**, each wrapping a primitive value. Therefore, when both operands are wrapper references, `==` checks **whether both references point to the same object**, not whether the underlying numbers are equal.

```java
Double first = Double.valueOf(2.5);
Double sameReference = first;
Double another = Double.valueOf(2.5);

System.out.println(first == sameReference); // true: same object
System.out.println(first == another);      // Identity comparison, not numeric value
System.out.println(first.equals(another)); // true: Double contents are equal
```

Do not rely on `==` between two separately created wrappers to test value equality. The contract of `Double.valueOf` does not turn `==` into numeric comparison.

### 4.1. When One Side Is Primitive: Unboxing

If one operand is primitive `double` and the other is `Double`, Java automatically **unboxes** the wrapper to a primitive and performs numeric comparison:

```java
Double boxed = Double.valueOf(0.5);
double primitive = 0.5;

System.out.println(boxed == primitive); // true: boxed is unboxed
```

This differs completely from the two-wrapper case:

```java
Double a = Double.valueOf(0.5);
Double b = Double.valueOf(0.5);

System.out.println(a == b); // Reference comparison
```

Unboxing a `null` wrapper throws `NullPointerException`:

```java
Double missing = null;
// boolean same = (missing == 0.0); // Throws NullPointerException on unboxing
boolean sameObject = (missing == null); // true, no unboxing
```

When a wrapper can be null, check for null before using it in numeric expressions.

### 4.2. Do Not Rely on Autoboxing When Comparing Objects

Autoboxing/unboxing shortens code, but can obscure whether Java is comparing identity or value. When reading an expression involving `Double`, identify **the static types of both operands**:

| Left Operand Type | Right Operand Type | Typical Meaning of `==` |
|---|---|---|
| `double` | `double` | Primitive value comparison |
| `Double` | `Double` | Object identity comparison |
| `Double` | `double` | Unbox `Double`, then compare values |
| `Double` | `null` | Reference comparison with null, no unboxing |

If the goal is comparing wrapper contents, use `equals` or `Double.compare` according to the required semantics.

## 5. `equals()` of `Double` and `Float`

`Double.equals(Object)` compares values according to rules defined for the `Double` wrapper, which do not completely match the `==` operator on primitives. Specifically, the rules distinguish:

- Two NaN values are considered equal under `Double.equals`.
- `+0.0` and `-0.0` are considered **different** under `Double.equals`.
- All other numeric values must correspond to the same floating-point value.

Example:

```java
Double nan1 = Double.valueOf(Double.NaN);
Double nan2 = Double.valueOf(Double.NaN);
Double plusZero = Double.valueOf(+0.0);
Double minusZero = Double.valueOf(-0.0);

System.out.println(nan1.equals(nan2));       // true
System.out.println(plusZero.equals(minusZero)); // false
System.out.println(Double.NaN == Double.NaN);   // false
System.out.println(+0.0 == -0.0);               // true
```

`Float.equals` follows corresponding rules for `float`.

### 5.1. Why Is NaN Different?

Under IEEE 754, NaN has multiple bit patterns and any primitive comparison with NaN is unequal, including with itself. For wrappers, Java needs a stable equivalence contract for `equals` to work in collections. `Double.equals` uses a canonicalized bit form so that all NaNs are treated as equal.

This allows collections based on `equals`/`hashCode` to behave consistently:

```java
var values = new java.util.HashSet<Double>();
values.add(Double.NaN);
values.add(Double.longBitsToDouble(0x7ff8000000000001L));

System.out.println(values.size()); // 1
```

Both values are recognized as NaN; bit canonicalization in `Double.equals` makes them equivalent in `HashSet`.

### 5.2. Why Is Signed Zero Different?

`Double.equals` distinguishes the two signed zeros because their bit representations differ. This is an intentional choice for the wrapper contract and total floating-point ordering:

```java
Double a = 0.0;
Double b = -0.0;

System.out.println(a.equals(b)); // false
System.out.println(a.doubleValue() == b.doubleValue()); // true
```

Consequently, you cannot use `Double.equals` if business semantics require both signed zeros to be treated as the same numeric value. In that case, compare primitives after handling null appropriately.

### 5.3. Wrappers of Different Types Are Not Equal

```java
Integer one = 1;
Double onePointZero = 1.0;

System.out.println(one.equals(onePointZero)); // false
```

`equals` must respect symmetry and each class's contract. `Integer` does not consider a `Double` to be of the same value type, even though the two numbers can be equivalent when converted to a common computation type.

## 6. Comparison Ordering: `Double.compare` and `compareTo`

Equality comparison is not enough for sorting. When you need to determine which value comes before, after, or at the same position, Java provides:

- `Double.compare(double a, double b)`: static method returning a negative number, 0, or a positive number.
- `Double.compareTo(Double other)`: instance method performing natural-order comparison.
- `Float.compare` and `Float.compareTo`: analogous for `float`.

Result convention:

| Result | Meaning |
|---:|---|
| Less than 0 | First value precedes second value |
| Equal to 0 | Both values are equal under wrapper comparison order |
| Greater than 0 | First value follows second value |

Do not test for exact values `-1` or `1`; the contract only specifies negative, zero, or positive.

```java
System.out.println(Double.compare(1.0, 2.0) < 0); // true
System.out.println(Double.compare(2.0, 1.0) > 0); // true
System.out.println(Double.compare(2.0, 2.0) == 0); // true
```

### 6.1. Total Ordering for NaN and Signed Zero

`Double.compare` and `Double.compareTo` provide an ordering usable for sorting, even in cases primitive relational operators cannot classify:

1. Negative values are less than positive values in standard numeric order.
2. `-0.0` precedes `+0.0`.
3. NaN is considered greater than all other numeric values, including `Double.POSITIVE_INFINITY`.
4. NaN values are considered equal to each other in comparison order.

Example:

```java
System.out.println(Double.compare(-0.0, +0.0)); // negative number
System.out.println(Double.compare(+0.0, -0.0)); // positive number
System.out.println(Double.compare(Double.NaN,
        Double.POSITIVE_INFINITY) > 0);          // true
System.out.println(Double.compare(Double.NaN,
        Double.NaN) == 0);                       // true
```

This ordering is consistent with `Double.equals`: if `a.equals(b)`, then `a.compareTo(b) == 0`. Thus `Double` can be used in collections sorted by natural ordering.

### 6.2. Sorting a List of `Double`

```java
var values = new java.util.ArrayList<Double>();
values.add(Double.NaN);
values.add(+0.0);
values.add(2.0);
values.add(Double.NEGATIVE_INFINITY);
values.add(-0.0);
values.add(Double.POSITIVE_INFINITY);

values.sort(null); // Natural ordering of Double
System.out.println(values);
```

Order according to `Double.compareTo`:

```text
[-Infinity, -0.0, 0.0, 2.0, Infinity, NaN]
```

This differs from writing a custom comparator using `a < b ? -1 : a > b ? 1 : 0`: that approach handles NaN incorrectly because both `a < NaN` and `a > NaN` are false, causing NaN to appear equal to unrelated values.

### 6.3. Using `TreeSet` and `HashSet`

`HashSet<Double>` relies on `equals`/`hashCode`; `TreeSet<Double>` relies on natural ordering (`compareTo`) or a comparator:

```java
var hash = new java.util.HashSet<Double>();
hash.add(+0.0);
hash.add(-0.0);

var tree = new java.util.TreeSet<Double>();
tree.add(+0.0);
tree.add(-0.0);

System.out.println(hash.size()); // 2
System.out.println(tree.size()); // 2
System.out.println(tree.first()); // -0.0
```

For `Double`, natural ordering and `equals` agree on distinguishing signed zero and grouping NaN. If you write a custom comparator with different rules, `TreeSet` may treat two objects as the same element when the comparator returns 0 even if `equals` returns false. Consider this carefully when writing custom comparators.

## 7. Approximate Comparison Using Allowed Tolerance

For floating-point calculation results, the requirement is often "two values are close enough" rather than "two bit patterns represent the same value". In that case, define a **tolerance** (allowed error).

### 7.1. Absolute Tolerance

Compare using absolute error:

\[
|a-b| \leq \varepsilon
\]

In Java:

```java
static boolean nearlyEqualAbsolute(
        double a, double b, double epsilon) {
    return Math.abs(a - b) <= epsilon;
}
```

This works when maximum error has a fixed meaning in the problem domain. However, the same epsilon can be too tight for very large numbers and too loose for numbers very close to 0.

### 7.2. Relative Tolerance

Relative error compares the difference against the magnitude of the values:

\[
\frac{|a-b|}{\max(|a|,|b|)} \leq r
\]

In practice, cases where both values are near 0 must be handled separately, since the denominator is zero or very close to zero. A formula combining absolute and relative tolerance is usually easier to apply.

### 7.3. Combining Absolute and Relative Tolerance

A common policy:

\[
|a-b| \leq \max(\varepsilon_{abs},
 r \cdot \max(|a|, |b|))
\]

Example:

```java
static boolean nearlyEqual(
        double a,
        double b,
        double absoluteTolerance,
        double relativeTolerance) {

    if (absoluteTolerance < 0 || relativeTolerance < 0
            || !Double.isFinite(absoluteTolerance)
            || !Double.isFinite(relativeTolerance)) {
        throw new IllegalArgumentException("Invalid tolerance");
    }

    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }

    // Exact equality, including identical infinities and two signed zeros.
    if (a == b) {
        return true;
    }

    // Unequal values involving infinity are not close.
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    double allowed = Math.max(
            absoluteTolerance,
            relativeTolerance * scale);

    return difference <= allowed;
}
```

Usage example:

```java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(nearlyEqual(actual, expected, 1e-12, 1e-12)); // true
```

The tolerances in the example are illustrative only. **There is no single epsilon right for every program.** Determine:

- Units of measurement and typical magnitude of the data.
- Maximum error accepted by business rules or the algorithm.
- Whether `+0.0` and `-0.0` must be distinguished.
- Whether NaN/infinity are valid data or must be rejected.
- Whether very small, very large, or subnormal values can occur.

The function above intentionally treats both signed zeros as close because `a == b` returns true. If the problem must distinguish zero signs, add a dedicated rule before that check. Subtracting two extremely large finite numbers of opposite signs can also overflow to infinity; in that case the actual difference exceeds any reasonable tolerance in the example.

### 7.4. Why Should You Avoid an Arbitrary Epsilon?

Example:

```java
double epsilon = 0.000001;
```

Such a constant might make sense in one specific problem, but it is not a rule of Java. For data around \(10^{-12}\), it might treat vastly different values as equal. For data around \(10^{12}\), it might be too small compared to the precision of the calculation.

Tolerance must reflect **the required accuracy of the result**, not a number copied from an online example.

### 7.5. Comparing by ULP

ULP (*unit in the last place*) is the spacing between adjacent representable floating-point values at a given magnitude. Java provides:

- `Math.ulp(double)` and `Math.ulp(float)`: ULP spacing at the given value.
- `Math.nextUp(x)`: next larger representable value toward positive infinity.
- `Math.nextDown(x)`: next smaller representable value toward negative infinity.

```java
double x = 1.0;
double next = Math.nextUp(x);

System.out.println(next > x);            // true
System.out.println(next - x == Math.ulp(x)); // true in this case
```

Checking by ULP count is useful in numerical algorithms needing to bound discrepancy to adjacent representable values. However, it is harder to explain than absolute/relative tolerance and requires separate handling for NaN, infinity, signed zero, subnormals, and value ranges. Do not replace business error policies with ULP merely because it looks "more precise".

## 8. When to Use `BigDecimal`?

If a problem requires **exact decimal arithmetic by decimal digits**, such as money, taxes, or quantities with rounding rules, `BigDecimal` is generally more appropriate than `double`.

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal sum = a.add(b);

System.out.println(sum); // 0.3
```

Creating `BigDecimal` from a decimal string represents the exact number from that string. Avoid:

```java
BigDecimal wrongForDecimalIntent = new BigDecimal(0.1);
```

The `double` constructor reflects the exact approximate binary floating-point value currently in `double`, not the original decimal intent `0.1`. If the source is already a `double`, `BigDecimal.valueOf(double)` is usually more convenient because it uses the canonical decimal representation of the double value; however, if original input accuracy is required, parse from `String` or a reliable decimal representation.

### 8.1. `BigDecimal.equals` and `compareTo` Also Differ

`BigDecimal` has a rule to remember: `equals` considers both **value and scale**, whereas `compareTo` compares numeric value, ignoring scale differences:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.equals(y));      // false
System.out.println(x.compareTo(y));   // 0
System.out.println(x.compareTo(y) == 0); // true
```

`2.0` has scale 1, `2.00` has scale 2. They have the same numeric value, yet are not equal under the `equals` contract.

Consequences when using collections:

```java
var hashSet = new java.util.HashSet<BigDecimal>();
hashSet.add(new BigDecimal("2.0"));
hashSet.add(new BigDecimal("2.00"));

var treeSet = new java.util.TreeSet<BigDecimal>();
treeSet.add(new BigDecimal("2.0"));
treeSet.add(new BigDecimal("2.00"));

System.out.println(hashSet.size()); // 2: equals distinguishes scale
System.out.println(treeSet.size()); // 1: compareTo returns 0
```

The natural ordering of `BigDecimal` is **inconsistent with equals** when scales differ for numerically equal values. This is an important distinction when using `TreeSet`/`TreeMap`.

### 8.2. Choosing Comparison Methods for `BigDecimal`

| Question | How to Check |
|---|---|
| Do two values have the same value and scale? | `a.equals(b)` |
| Are two values numerically equal, regardless of scale? | `a.compareTo(b) == 0` |
| Is `a` numerically less than `b`? | `a.compareTo(b) < 0` |
| Want to normalize representation before storing? | Specify scale/rounding or an explicit `stripTrailingZeros()` policy |

Do not use `==` to compare the contents of two `BigDecimal` objects because they are objects.

## 9. Comparison Method Selection Table

| Need | Common Approach | Notes |
|---|---|---|
| Compare two `double` primitives by exact stored value | `a == b` | NaN is never equal to itself; signed zeros are treated as equal |
| Check if a primitive is NaN | `Double.isNaN(a)` | Do not use `a == Double.NaN` |
| Check for a finite number | `Double.isFinite(a)` | Excludes both NaN and both infinities |
| Compare two wrappers per `Double` contract | `a.equals(b)` | NaN equals NaN; signed zeros differ; watch out for null |
| Compare floating-point numbers by order | `Double.compare(a, b)` or `a.compareTo(b)` | Defines ordering for NaN and signed zero |
| Sort `List<Double>` | `list.sort(null)` or appropriate comparator | Natural ordering uses `Double.compareTo` |
| Check if two computed results are close enough | Domain-specific tolerance function | Choose suitable absolute/relative tolerance |
| Exact decimal computation | `BigDecimal` | Parse from string; specify scale and rounding |

## 10. Comprehensive Example Running on Java 17

The following program demonstrates key cases in one place:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public class Main {
    static boolean nearlyEqual(double a, double b, double epsilon) {
        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        return Math.abs(a - b) <= epsilon;
    }

    public static void main(String[] args) {
        double sum = 0.1 + 0.2;
        System.out.println(sum == 0.3);                  // false
        System.out.println(nearlyEqual(sum, 0.3, 1e-12)); // true

        double nan = Double.NaN;
        System.out.println(nan == nan);                  // false
        System.out.println(Double.valueOf(nan)
                .equals(Double.valueOf(nan)));           // true

        System.out.println(+0.0 == -0.0);                 // true
        System.out.println(Double.valueOf(+0.0)
                .equals(Double.valueOf(-0.0)));          // false
        System.out.println(Double.compare(-0.0, +0.0) < 0); // true

        List<Double> values = new ArrayList<>(
                List.of(Double.NaN, +0.0, 2.0,
                        Double.NEGATIVE_INFINITY, -0.0));
        values.sort(null);
        System.out.println(values);

        BigDecimal decimalA = new BigDecimal("2.0");
        BigDecimal decimalB = new BigDecimal("2.00");
        System.out.println(decimalA.equals(decimalB)); // false
        System.out.println(decimalA.compareTo(decimalB)); // 0
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Key output:

```text
false
true
false
true
true
false
true
[-Infinity, -0.0, 0.0, 2.0, NaN]
false
0
```

Each pair of results demonstrates a different contract: primitive equality, tolerance, wrapper equality, total ordering, and decimal equality.

## 11. Common Mistakes

### 11.1. Using `==` Between Two Wrappers

```java
Double a = Double.valueOf(0.1);
Double b = Double.valueOf(0.1);

// Do not use to check whether two numbers have the same value:
boolean same = (a == b);
```

This is an identity comparison because both operands are wrappers. If you want value equality under the wrapper contract, use `a.equals(b)`; if you want primitive arithmetic comparison, check for null then unbox or call `Double.compare(a, b)`.

### 11.2. Using `==` to Check for NaN

```java
if (value == Double.NaN) { // Never true
    // ...
}
```

Fix with `Double.isNaN(value)`.

### 11.3. Assuming `equals` and `==` Always Have the Same Semantics

For the `Double` wrapper, NaN and signed zero prove they differ:

| Expression | Result |
|---|---|
| `Double.NaN == Double.NaN` | false |
| `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` | true |
| `+0.0 == -0.0` | true |
| `Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` | false |

### 11.4. Writing a Custom Comparator Using `<` and `>`

```java
// Insufficient to determine correct ordering when NaN is present.
static int badCompare(double a, double b) {
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
}
```

If one operand is NaN, both checks evaluate to false so the function returns 0, even though the other value may be finite. Use `Double.compare(a, b)` when standard wrapper ordering is needed.

### 11.5. Assuming a Fixed Epsilon Works for All Quantities

Acceptable errors for temperatures, coordinates, ratios, simulations, and algorithm outputs can differ greatly. Choose tolerances from units and business requirements; if the data is exact decimal, consider `BigDecimal`.

### 11.6. Converting to BigDecimal Too Late

If monetary data is read into `double`, added and subtracted multiple times, and only then converted into `BigDecimal`, binary errors already introduced cannot vanish on their own. Choose the right data type **right at the input boundary**:

```java
BigDecimal price = new BigDecimal("19.95");
BigDecimal quantity = new BigDecimal("3");
BigDecimal total = price.multiply(quantity);
```

### 11.7. Forgetting Null When a Wrapper Is Unboxed

```java
Double score = null;
// if (score > 0.0) { ... } // NullPointerException due to unboxing
```

Check for null before using arithmetic operators, or design APIs not to allow null wrappers.

## 12. Practice Exercises

### Exercise 1 — Predict `==` and `equals`

```java
double a = Double.NaN;
double b = Double.NaN;
Double x = Double.valueOf(+0.0);
Double y = Double.valueOf(-0.0);
```

Predict:

- `a == b`
- `Double.valueOf(a).equals(Double.valueOf(b))`
- `x.equals(y)`
- `x.doubleValue() == y.doubleValue()`

**Answer:** `false`, `true`, `false`, `true`, respectively. Explain based on NaN and signed zero rules.

### Exercise 2 — Sorting Floating-Point Numbers

Create a list containing `NaN`, both signed zeros, negative numbers, positive numbers, and infinity; call `sort(null)`. Explain why the order starts with `-Infinity`, `-0.0` and ends with `NaN`.

Hint: the list uses the natural ordering of `Double`, i.e., `compareTo`.

### Exercise 3 — Approximate Comparison

Write a function checking whether two temperature measurements differ by at most 0.05 degrees. Specify how to handle `NaN`, infinity, and null if inputs are boxed as `Double`.

Hint: tolerance is a domain requirement, not a universal constant. With wrappers, check for null and then convert to primitive.

### Exercise 4 — BigDecimal

Create:

```java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");
```

Explain why `equals` returns false while `compareTo` returns 0. Try adding both to a `HashSet` and a `TreeSet`, and explain the element counts.

**Answer:** `HashSet` has two elements because equality considers scale; `TreeSet` has one element because `BigDecimal`'s natural ordering considers them at the same comparison position.

### Exercise 5 — Fixing a Broken Comparator

Fix the function:

```java
static int compare(double a, double b) {
    return a < b ? -1 : a > b ? 1 : 0;
}
```

**Answer:** use `return Double.compare(a, b);`. If the problem wants to ignore signed zero or handle NaN under a custom policy, write a comparator following that contract and verify consistency.

## 13. Completion Criteria

Learners complete this lesson when they can:

1. Explain why `0.1 + 0.2 == 0.3` can be false with `double`.
2. Distinguish primitive `==`, `==` between two wrappers, and cases where a wrapper is unboxed.
3. Explain accurately the behavior of NaN and signed zero with arithmetic operators.
4. Describe the rules of `Double.equals`/`Float.equals`, including NaN and both signed zeros.
5. Use `Double.compare` or `compareTo` for sorting and explain the positions of NaN, infinity, `-0.0`, and `+0.0`.
6. Write an approximate check with an appropriate tolerance, explicitly handle NaN/infinity, and avoid treating epsilon as a fixed constant for all problems.
7. Distinguish `BigDecimal.equals` from `compareTo`, create decimal values from strings, and specify scale/rounding when needed.
8. Choose the right comparison for the requirement: exact equality, object equality, sort order, or tolerance-based approximation.

## 14. Official Documentation

- [Java Language Specification, Java SE 17 — Floating-Point Types, Formats, and Values (§4.2.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): floating-point model and values.
- [Java Language Specification, Java SE 17 — Equality Operators (§15.21)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21): rules for `==` and `!=` operators.
- [Java SE 17 API — `Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `equals`, `compare`, `compareTo`, NaN, infinity, and signed zero.
- [Java SE 17 API — `Float`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): corresponding rules for binary32.
- [Java SE 17 API — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal values, scale, `equals`, `compareTo`, and rounding.
- [Java SE 17 API — `Math.ulp`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#ulp(double)): unit spacing at a floating-point value.

**Key takeaway:** Primitive `==` answers equality under numeric comparison; wrapper `equals` follows the object contract with special handling for NaN and signed zero; `compareTo`/`Double.compare` provides sort ordering; and "close enough" requires a domain-defined tolerance. Choosing the right contract avoids both comparison bugs and data design mistakes.
