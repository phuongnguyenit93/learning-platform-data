# Float.compare, Double.compare, and Total Ordering in Java

In Java, two `float` or `double` numbers can be compared using the operators `<`, `>`, `<=`, `>=`, `==`, `!=` or using `Float.compare(a, b)` and `Double.compare(a, b)`. For ordinary finite numbers, both approaches usually lead to the same greater/less conclusion; however, when encountering **NaN** and **signed zero** (`-0.0`, `+0.0`), their behaviors intentionally differ.

`Float.compare` and `Double.compare` establish a **total ordering over values according to Java's convention**: even NaN is placed at a defined position so that values can be sorted, searched, and used as collection keys. Understanding this difference helps avoid subtle bugs when moving from arithmetic calculations to `sort`, `TreeSet`, `TreeMap`, or the `Float`/`Double` wrappers.

## 1. Distinguishing Two Comparison Purposes

**Primitive comparison operators** reflect the arithmetic relationship of floating-point operands:

- `1.0 < 2.0` is `true`; `2.0 == 2.0` is `true`.
- `-0.0 == +0.0` is `true`: primitive equality considers the two signed zeros equal.
- `Double.NaN == Double.NaN` is `false`, even when comparing the same NaN variable with itself.
- When NaN is present, `<`, `<=`, `>`, `>=`, and `==` all return `false`; only `!=` returns `true`.

**`Double.compare(a, b)` / `Float.compare(a, b)`** produce an `int` result:

| Result | Meaning |
| --- | --- |
| Less than 0 | `a` comes before `b` in Java's ordering |
| Equal to 0 | `a` and `b` are equivalent in Java's ordering |
| Greater than 0 | `a` comes after `b` in Java's ordering |

The API contract guarantees only the **sign** (negative / 0 / positive). Do not write logic assuming every call always returns strictly `-1` or `1`; the concrete examples below may return those numbers, but the contract is the sign of the result.

## 2. The Total Ordering Used by Java

According to `Double.compare`, values are ordered as follows (from smallest to largest):

~~~text
-Infinity < negative finite numbers < -0.0 < +0.0
          < positive finite numbers < +Infinity < NaN
~~~

Key points:

1. Finite numbers and infinities are ordered according to normal arithmetic order.
2. **`-0.0` is less than `+0.0`**, even though the primitive `==` operator considers them equal.
3. **NaN comes after all other values**, including `Double.POSITIVE_INFINITY`.
4. **All NaNs are treated as equivalent by `Double.compare`** and return 0 when compared with one another. This holds even if two NaNs have different bit patterns (*payloads*).

`Float.compare` uses the same ordering convention for `float`. Signatures to remember:

~~~java
int orderD = Double.compare(1.0, 2.0);      // < 0
int orderF = Float.compare(1.0f, 2.0f);     // < 0
~~~

`Float.compare` takes `float` parameters; `Double.compare` takes `double`. Do not cast `double` data to `float` just to call `Float.compare`: casting can round values or make two different numbers become equal.

**"Total" here means an ordering over values as defined by Java**, not the ability to distinguish every IEEE 754 bit pattern. All NaN payloads are collapsed into a single equivalence class during comparison. This differs from requiring a separate ordering for *all bit encodings* of NaN.

## 3. Signed Zero: `==` and `compare` Differ Intentionally

IEEE 754 allows `+0.0` and `-0.0` to be two distinct bit patterns. Java preserves the sign of 0 in many operations; for example:

~~~java
double positiveZero = +0.0;
double negativeZero = -0.0;

boolean primitiveEqual = positiveZero == negativeZero; // true
int first = Double.compare(negativeZero, positiveZero); // < 0
int second = Double.compare(positiveZero, negativeZero); // > 0

double inversePositive = 1.0 / positiveZero; // Infinity
double inverseNegative = 1.0 / negativeZero; // -Infinity
~~~

In the runnable example below, `Double.compare(-0.0, +0.0)` returns `-1`, while the reverse returns `1`. The two zeros can therefore **occupy two distinct positions** in a `TreeSet<Double>`.

Be careful when writing logic like `if (x == 0.0)`: this expression is true for **both** signs of 0. If you must distinguish the sign bit for numerical business logic, use `Double.compare`, `Double.doubleToRawLongBits`, or an appropriate API rather than `==` alone.

## 4. NaN: Unordered Under Primitives, Yet Ordered by `compare`

NaN can arise from `0.0 / 0.0`, `Infinity - Infinity`, `Math.sqrt(-1.0)`, or a data source containing NaN values. Primitive operators impose no ordering relationship between NaN and other numbers:

~~~java
double nan = Double.NaN;

boolean equalsSelf = nan == nan;                 // false
boolean smaller = nan < Double.POSITIVE_INFINITY; // false
boolean greater = nan > Double.POSITIVE_INFINITY; // false
boolean differs = nan != nan;                   // true
~~~

Meanwhile:

~~~java
int afterInfinity =
        Double.compare(Double.NaN, Double.POSITIVE_INFINITY); // > 0
int equalNaNs =
        Double.compare(Double.NaN, Double.NaN);               // 0
~~~

There is no contradiction: primitive operators describe **arithmetic comparison**, whereas `compare` uses **Java API's total ordering rule** to work with sorting and collections.

Check "is this NaN?" with `Double.isNaN(value)` or `Float.isNaN(value)`—**do not use** `value == Double.NaN` (always false) and do not use `Double.compare(value, Double.NaN) == 0` to obscure the intent of classifying the value. The latter can detect NaN, but it expresses the wrong intent and is harder to maintain than `isNaN`.

## 5. Two NaNs with Different Payloads Still Yield `compare == 0`

A `double` NaN can have multiple distinct IEEE 754 bit patterns. Java has two APIs to distinguish:

- `Double.doubleToRawLongBits(x)` preserves the raw bit pattern of the `double` value at the time of the call.
- `Double.doubleToLongBits(x)` **canonicalizes all NaNs into a single canonical NaN bit pattern**; therefore, it aligns with the `Double.equals`/`hashCode` convention.

~~~java
double nanA = Double.longBitsToDouble(0x7ff8_0000_0000_0001L);
double nanB = Double.longBitsToDouble(0x7ff8_0000_0000_0002L);

boolean rawDifferent = Double.doubleToRawLongBits(nanA)
                    != Double.doubleToRawLongBits(nanB); // true
int order = Double.compare(nanA, nanB);        // 0
boolean wrapperEqual =
        Double.valueOf(nanA).equals(Double.valueOf(nanB)); // true
~~~

Do not rely on `compare` to distinguish payloads, NaN sign bits, or trace the intact encoding of individual NaNs. If distinguishing payloads is a protocol or bit-level requirement, define a policy based on raw bits and note that certain floating-point operations may not preserve payloads. For `float`, the corresponding pair of APIs is `Float.floatToRawIntBits` and `Float.floatToIntBits`.

## 6. Relationship with `Double.equals`, `Float.equals`, and `compareTo`

The `Double` wrapper has `equals`/`hashCode` based on canonicalized NaN representation. Consequently:

| Two values | Primitive `a == b` | `Double.compare(a,b) == 0` | `Double.valueOf(a).equals(Double.valueOf(b))` |
| --- | --- | --- | --- |
| `2.0` and `2.0` | `true` | `true` | `true` |
| `+0.0` and `-0.0` | `true` | `false` | `false` |
| `NaN` and `NaN` | `false` | `true` | `true` |
| `-Infinity` and `-Infinity` | `true` | `true` | `true` |

`Double.compareTo` uses the same rules as `Double.compare`; `Float.compareTo` corresponds to `Float.compare`. One reason this ordering exists is so that **`compareTo` is consistent with the wrapper's `equals`**, which is very important for ordered collections.

When you write `Double a = ...; Double b = ...; a.equals(b)`, you are using **wrapper object equality**; whereas `a == b` if both are `Double` objects checks **reference identity**, not numeric comparison. Only when an operand is unboxed to a primitive does `==` perform floating-point comparison. Therefore, to be clear about semantics, determine the static types of the operands before predicting the result.

## 7. Sorting and Data Structures

APIs like `Arrays.sort(double[])`, `Arrays.sort(float[])`, and comparators based on `Double.compare` or `Float.compare` use a consistent ordering that handles NaN and signed zero. For a list of `Double`s, you can write:

~~~java
List<Double> values = new ArrayList<>(Arrays.asList(
        Double.NaN, 3.0, -0.0, Double.NEGATIVE_INFINITY,
        +0.0, Double.POSITIVE_INFINITY, -5.0, Double.NaN));
values.sort(Double::compare);
// [-Infinity, -5.0, -0.0, 0.0, 3.0, Infinity, NaN, NaN]
~~~

The snippet above **belongs inside a method of a class with `java.util.*` imports**; the complete example in Section 9 can be run directly.

With `TreeSet<Double>` (natural ordering via `Double.compareTo`):

- `-0.0` and `+0.0` are kept as **two distinct elements**.
- Two NaN values are considered **duplicates**, and only one NaN element is kept.
- NaN comes last when iterating in ascending order.

If you use `TreeMap<Double, ...>`, `-0.0` and `+0.0` are also two distinct keys, while NaNs are treated as the same key under comparator ordering. `HashSet<Double>` likewise treats NaNs as equal and the two signed zeros as distinct due to `Double.equals`/`hashCode`, although `HashSet` does not guarantee iteration order.

**Rule for custom comparators:** returning `0` means two keys are equivalent in `TreeSet`/`TreeMap`. A comparator like `(a, b) -> a < b ? -1 : a > b ? 1 : 0` is **wrong** if NaN or signed zero can appear: it returns 0 for many non-equivalent pairs, which can drop elements or overwrite keys. Use `Double.compare(a,b)` or `Comparator.naturalOrder()`.

## 8. Compilable and Runnable Java 17+ Program

Create the file `CompareDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class CompareDemo {
    public static void main(String[] args) {
        double negZero = -0.0;
        double posZero = 0.0;
        double nanA = Double.NaN;
        double nanB = Double.longBitsToDouble(0x7ff8_0000_0000_0001L);
        double nanC = Double.longBitsToDouble(0x7ff8_0000_0000_0002L);

        System.out.println("primitive +0 == -0: " + (posZero == negZero));
        System.out.println("primitive NaN == NaN: " + (nanA == nanA));
        System.out.println("primitive NaN < Infinity: "
                + (nanA < Double.POSITIVE_INFINITY));
        System.out.println("Double.compare(-0,+0): "
                + Double.compare(negZero, posZero));
        System.out.println("Double.compare(+0,-0): "
                + Double.compare(posZero, negZero));
        System.out.println("Double.compare(NaN,+Infinity): "
                + Double.compare(nanA, Double.POSITIVE_INFINITY));
        System.out.println("Double.compare(NaN,NaN): "
                + Double.compare(nanB, nanC));
        System.out.println("raw NaN payloads differ: "
                + (Double.doubleToRawLongBits(nanB)
                != Double.doubleToRawLongBits(nanC)));
        System.out.println("Double.equals(+0,-0): "
                + Double.valueOf(posZero).equals(Double.valueOf(negZero)));
        System.out.println("Double.equals(NaN,NaN): "
                + Double.valueOf(nanB).equals(Double.valueOf(nanC)));
        System.out.println("Float.compare(-0f,+0f): "
                + Float.compare(-0.0f, 0.0f));
        System.out.println("Float.compare(NaN,Infinity): "
                + Float.compare(Float.NaN, Float.POSITIVE_INFINITY));

        List<Double> values = new ArrayList<>(Arrays.asList(
                Double.NaN, 3.0, -0.0, Double.NEGATIVE_INFINITY,
                +0.0, Double.POSITIVE_INFINITY, -5.0, Double.NaN));
        values.sort(Double::compare);
        System.out.println("sorted: " + values);

        Set<Double> tree = new TreeSet<>(values);
        System.out.println("tree: " + tree);
        System.out.println("tree size: " + tree.size());
        System.out.println("nanB == nanC: " + (nanB == nanC));
    }
}
~~~

Run command:

~~~bash
javac CompareDemo.java
java CompareDemo
~~~

Stdout output:

~~~text
primitive +0 == -0: true
primitive NaN == NaN: false
primitive NaN < Infinity: false
Double.compare(-0,+0): -1
Double.compare(+0,-0): 1
Double.compare(NaN,+Infinity): 1
Double.compare(NaN,NaN): 0
raw NaN payloads differ: true
Double.equals(+0,-0): false
Double.equals(NaN,NaN): true
Float.compare(-0f,+0f): -1
Float.compare(NaN,Infinity): 1
sorted: [-Infinity, -5.0, -0.0, 0.0, 3.0, Infinity, NaN, NaN]
tree: [-Infinity, -5.0, -0.0, 0.0, 3.0, Infinity, NaN]
tree size: 7
nanB == nanC: false
~~~

The output illustrates what looks like a paradox: `nanB == nanC` is `false` yet `Double.compare(nanB,nanC)` is 0, and the two signed zeros have the opposite relationship. Because `TreeSet` uses the natural ordering of `Double`, it retains both signed zeros and merges duplicate NaNs.

## 9. `compare` Is Not an Approximate Equality Comparison

Suppose two computation results are close due to floating-point error. `Double.compare(a,b) == 0` only detects **equality under wrapper ordering**, without applying an allowed error margin (*tolerance*). Do not use it in place of business logic for approximate comparison.

Example:

~~~java
double x = 0.1 + 0.2;
double y = 0.3;

boolean exactlyEqual = Double.compare(x, y) == 0; // false
~~~

If the problem has a tolerance, you must specify the unit/magnitude of the error bound. A simple example for finite numbers in a range that does not overflow upon subtraction:

~~~java
static boolean approximatelyEqual(
        double a, double b, double absoluteTolerance) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    if (!Double.isFinite(absoluteTolerance)
            || absoluteTolerance < 0.0) {
        throw new IllegalArgumentException("Invalid tolerance");
    }
    return Math.abs(a - b) <= absoluteTolerance;
}
~~~

This is an **illustrative method**, which must be placed inside a class. For extremely large magnitudes, the difference `a-b` can overflow to infinity; many problems require combining absolute and relative tolerance in an algorithm suited to the value domain. You must decide separately how to handle NaN and infinities, as they are never "nearly equal" to finite numbers simply because of an epsilon.

For **sorting, data keys, and binary search**, avoid using an arbitrary epsilon-based comparator because approximate equality may **not be transitive** (e.g., A is near B and B is near C, yet A is not near C), violating the comparator contract. Use `Double.compare` for ordering and keep approximate-equality logic separate.

## 10. How to Choose a Comparison Method

| Need | Suitable tool | Notes |
| --- | --- | --- |
| Ordinary arithmetic relation between primitives | `<`, `>`, `==` ... | NaN makes ordering relations always false; ±0 are equal |
| Detecting NaN | `Double.isNaN` / `Float.isNaN` | Do not use `x == NaN` |
| Defining a stable ordering for sorting | `Double.compare` / `Float.compare` | `-0 < +0 < Infinity < NaN` |
| Comparing wrappers per equals contract | `Double.equals` / `Float.equals` | NaN equals NaN; ±0 differ |
| Validating finite input | `Double.isFinite` / `Float.isFinite` | Excludes NaN and infinity |
| Comparing nearly equal results | A tolerance function with business specification | Do not use epsilon comparators for ordered collections |
| Checking exact bit patterns including NaN payload | `doubleToRawLongBits` / `floatToRawIntBits` | Requires an explicit bit-level policy |

A common mistake to avoid is implementing a comparator like this:

~~~java
// INTENTIONALLY WRONG if data contains NaN or signed zero:
static int brokenCompare(double a, double b) {
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
}
~~~

With `a = Double.NaN` and `b = 5.0`, the function above returns 0, even though the two values are not equivalent. With `-0.0` and `+0.0`, it also returns 0, differing from `Double`'s ordering contract. The correct version for `double` data is:

~~~java
static int correctCompare(double a, double b) {
    return Double.compare(a, b);
}
~~~

Both snippets are **standalone illustrative methods**, not runnable programs with `main`.

## 11. Practice Questions

1. Is `Double.compare(-0.0, +0.0)` negative, 0, or positive? What about `-0.0 == +0.0`?
2. Does `Double.NaN > Double.POSITIVE_INFINITY` return `true`? What sign does `Double.compare(Double.NaN, Double.POSITIVE_INFINITY)` return?
3. Can two NaNs with different bit payloads coexist as two separate elements in a `TreeSet<Double>` using natural ordering?
4. Why does `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` return `true`, whereas `Double.NaN == Double.NaN` returns `false`?
5. What is dangerous about a comparator using `a < b ? -1 : a > b ? 1 : 0` when comparing NaN? Should you use an epsilon comparator for `TreeMap`?

**Answers:** (1) Negative; the primitive operator returns `true`. (2) The `>` operator returns `false`, while `Double.compare` is positive. (3) No, `Double.compare` treats all NaNs as equivalent so the set contains only one NaN value. (4) The wrapper applies equality based on canonical bits, whereas primitive NaN is unordered. (5) It returns 0 for NaN and many non-equivalent numbers; an epsilon comparator can violate transitivity, so do not use it for ordered collections.

## References

- [Java SE 21: Double.compare, equals, compareTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html).
- [Java SE 21: Float.compare, equals, compareTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Float.html).
- [JLS `15.20 and `15.21: Relational and Equality Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20).
- [Java SE 21: Comparator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html), [TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).
