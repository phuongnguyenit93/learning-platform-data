# Reference Table: NaN, Signed Zero, equals, and compare in Java

## 1. Goal: Distinguishing Four Concepts of "Equality"

In Java, the floating-point types `float` and `double` follow Java's specified IEEE 754 semantics. Several special values compare differently from ordinary arithmetic intuition:

- **NaN (Not a Number)**: a special value representing an undefined result of a floating-point operation, such as `0.0 / 0.0`.
- **Signed zero**: both `+0.0` and `-0.0` exist. The two values compare equal under the arithmetic operator `==`, yet behave differently in certain operations, such as `1.0 / +0.0` and `1.0 / -0.0`.
- **`==`, `!=`, `<`, `>`, `<=`, `>=` on primitives**: apply **numerical comparison** rules, in which NaN is not considered equal to any number, including itself.
- **`Double.equals` / `Float.equals` and `Double.compare` / `Float.compare`**: use **wrapper equality and ordering rules**, designed consistently for use as collection keys and for sorting.

Therefore, looking at the exact same two `double` values, choosing different APIs can yield different results. This is not a Java bug; these are **different comparison contracts**.

This lesson is a reference table for Java 17+, including a standalone runnable example, NaN cases with different payloads, signed zero, hash/sorted collections, and how to choose the comparison method by problem.

## 2. Quick Table: Primitive Operators and Wrappers

Suppose:

~~~java
double nan = Double.NaN;
double positiveZero = 0.0;
double negativeZero = -0.0;
~~~

These are declarations **inside a method body**; the complete program is in Section 8.

| Check | Java Result | Reason |
|---|---|---|
| `Double.NaN == Double.NaN` | `false` | NaN is not equal to any value via primitive `==` |
| `Double.NaN != Double.NaN` | `true` | `!=` evaluates to true if either side is NaN |
| `Double.NaN < 1.0` | `false` | Primitive ordering with NaN is unordered |
| `Double.NaN > 1.0` | `false` | Same |
| `Double.NaN <= 1.0` | `false` | Same |
| `Double.NaN >= 1.0` | `false` | Same |
| `Double.NaN == Double.POSITIVE_INFINITY` | `false` | Infinity is a distinct value, not NaN |
| `0.0 == -0.0` | `true` | Both zeros are equal under numerical comparison |
| `0.0 < -0.0` | `false` | No numerical value difference |
| `0.0 > -0.0` | `false` | Same |
| `Double.valueOf(nan).equals(Double.valueOf(nan))` | `true` | Wrapper treats all NaNs as equal |
| `Double.valueOf(-0.0).equals(Double.valueOf(0.0))` | `false` | Wrapper distinguishes the sign bit of zero |
| `Double.compare(nan, nan)` | `0` | Two NaNs share the same position in wrapper order |
| `Double.compare(nan, Double.POSITIVE_INFINITY)` | Positive number (`1` in JDK 17) | NaN sorts **after** all numeric values, including +Infinity |
| `Double.compare(-0.0, +0.0)` | Negative number (`-1` in JDK 17) | `-0.0` sorts before `+0.0` |
| `Double.compare(+0.0, -0.0)` | Positive number (`1` in JDK 17) | `+0.0` sorts after `-0.0` |

**Memory tip:** if you need to compare floating-point values using arithmetic operators, `==` and `<` have specific rules for NaN/zero. If you need a **total order for sorting**, `Double.compare` and `Float.compare` are the appropriate APIs.

The examples in the table use `Double.NaN` of primitive type `double`, not `Double` objects. The difference between primitives and wrappers becomes clear in the following sections.

## 3. NaN and Primitive Operators

NaN can arise from undefined floating-point operations:

~~~java
double undefined = 0.0 / 0.0;
double infinity = 1.0 / 0.0;

System.out.println(undefined); // NaN
System.out.println(infinity);  // Infinity
~~~

Do not think of NaN as a very large or very small number. When at least one operand is NaN:

- `==` returns `false`, even when comparing NaN with NaN itself.
- `!=` returns `true`.
- `<`, `<=`, `>`, and `>=` all return `false`.
- Consequently, the two conditions `!(a < b)` and `a >= b` are **not equivalent** when NaN is present: for `a = NaN`, `!(a < b)` is true while `a >= b` is false.

Example:

~~~java
double a = Double.NaN;
double b = 10.0;

System.out.println(a == a);  // false
System.out.println(a != a);  // true
System.out.println(a < b);   // false
System.out.println(a >= b);  // false
System.out.println(!(a < b)); // true
~~~

**Do not detect NaN with `x == Double.NaN`.** That condition is always false for every value of `x`, including NaN. Use:

~~~java
boolean invalid = Double.isNaN(a);
~~~

For `float`, use `Float.isNaN(value)`. If you need to reject all non-finite values (both NaN and ±Infinity), use `Double.isFinite(value)` or `Float.isFinite(value)` (available in Java 17).

### Infinity Is Not NaN

`Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY` are numerically ordered values:

~~~java
System.out.println(Double.NEGATIVE_INFINITY < -1e300); // true
System.out.println(Double.POSITIVE_INFINITY > 1e300);  // true
System.out.println(Double.isNaN(Double.POSITIVE_INFINITY)); // false
System.out.println(Double.isInfinite(Double.POSITIVE_INFINITY)); // true
~~~

With `double`, `1.0 / 0.0` returns +Infinity and `-1.0 / 0.0` returns -Infinity under floating-point rules. However, **integer** division `1 / 0` or `int x / intZero` throws `ArithmeticException`; do not lump both cases together.

If input data must be a finite number, checking `!Double.isNaN(x)` is **not enough**: Infinity is not NaN. Useful rule:

~~~java
if (!Double.isFinite(x)) {
    throw new IllegalArgumentException("Value must be finite");
}
~~~

This is a snippet inside a method with a `double` variable `x`.

## 4. Signed Zero: Why 0.0 Equals -0.0 Yet Is Not Completely Identical

IEEE 754 has two zero representations:

- `+0.0`: sign bit is 0.
- `-0.0`: sign bit is 1.

The primitive `==` operator treats them as **equal**, because they have the same zero value under numerical comparison:

~~~java
System.out.println(0.0 == -0.0); // true
System.out.println(-0.0 < +0.0);  // false
~~~

However, in certain operations, the sign of zero affects the result:

~~~java
System.out.println(1.0 / +0.0); // Infinity
System.out.println(1.0 / -0.0); // -Infinity

System.out.println(Math.min(-0.0, +0.0)); // -0.0
System.out.println(Math.max(-0.0, +0.0)); // 0.0
~~~

`Math.min` and `Math.max` for `double` have a signed-zero rule: `-0.0` is considered smaller than `+0.0` when both arguments are zeros of opposite signs. If either operand is NaN, both methods return NaN per the Java API. Therefore, do not use min/max as a way to **filter out NaN** from data.

String representation can also preserve the sign:

~~~java
System.out.println(Double.toString(-0.0)); // -0.0
System.out.println(Double.toString(+0.0)); // 0.0
~~~

If the problem only needs to know whether two values are numerically equal, `+0.0 == -0.0` is true. If distinguishing the sign of zero matters (e.g., results of computing 1/x, bit-level serialization, exact output checks), do not assume the two representations are completely interchangeable.

### Bit Patterns of the Two Zeros

~~~java
long positiveBits = Double.doubleToRawLongBits(+0.0);
long negativeBits = Double.doubleToRawLongBits(-0.0);
System.out.println(positiveBits == negativeBits); // false
~~~

In Java's IEEE 754 binary64 format, the sign bit differs. `Double.doubleToLongBits` also preserves this distinction for ±0.0.

**Note:** the term "signed zero" does not mean that `-0.0 < 0.0` in every API. The primitive `<` operator returns false, whereas `Double.compare(-0.0, +0.0) < 0` is true under the wrapper's separately defined ordering.

## 5. Double.equals and Double.compare: How Do They Differ from ==?

### 5.1. Double.equals

`Double.equals(Object)` compares two **Double objects** by their bit representation, with NaN canonicalized. The result differs from primitive comparison in two key places:

| Value Pair | Primitive `a == b` | `Double.valueOf(a).equals(Double.valueOf(b))` |
|---|---|---|
| `1.0` and `1.0` | true | true |
| `1.0` and `2.0` | false | false |
| `+0.0` and `-0.0` | **true** | **false** |
| `NaN` and `NaN` | **false** | **true** |
| `NaN` and `+Infinity` | false | false |
| `+Infinity` and `+Infinity` | true | true |
| `-Infinity` and `-Infinity` | true | true |

This definition allows `Double` to work properly with `equals`/`hashCode` in `HashMap`, `HashSet`, and standard collections. Any two `Double` values considered equal by `equals` have equal `hashCode`s.

**Do not use `==` to compare two `Double` objects if you need value equality.** When both operands are `Double` references, `==` compares **references**. When one side is unboxed to primitive, behavior switches to numerical comparison and can raise `NullPointerException`.

~~~java
Double left = Double.valueOf(1.5);
Double right = Double.valueOf(1.5);

System.out.println(left.equals(right)); // true
// left == right: do not use to infer value-equality.
~~~

If two `Double` references can be null, use `Objects.equals(left, right)` when you want null-safe wrapper equality rules; if null is invalid, validate the input first and then use `left.equals(right)`. `Objects.equals` **does not fall back to primitive `==`**, so it still distinguishes signed zeros and treats NaN as equal to NaN.

### 5.2. Double.compare and compareTo

`Double.compare(double a, double b)` and `Double.compareTo(Double other)` establish a **total order** for sorting, placing NaN at a well-defined position:

~~~text
-Infinity < finite negative numbers < -0.0 < +0.0
          < finite positive numbers < +Infinity < NaN
~~~

That is the most important ordering to remember. All NaNs are treated as equal **under compare**, even if they have different payload bits. Although results may be negative/0/positive, do not write conditions relying on `compare(...) == -1` or `== 1`; the general contract of compare APIs only specifies the sign, so use `< 0`, `== 0`, `> 0`.

Example:

~~~java
System.out.println(Double.compare(-0.0, +0.0)); // -1
System.out.println(Double.compare(+0.0, -0.0)); // 1
System.out.println(Double.compare(Double.NaN, Double.NaN)); // 0
System.out.println(Double.compare(
        Double.NaN, Double.POSITIVE_INFINITY)); // 1
~~~

**Overarching rule:** for any two primitive double values `a`, `b` (including NaN, ±0.0), the expression `Double.compare(a,b) == 0` is consistent with `Double.valueOf(a).equals(Double.valueOf(b))`. However, they are **not consistent with primitive `a == b`** at NaN and signed zero.

### 5.3. Float Has Corresponding Rules

`Float.equals`, `Float.compare`, and `Float.compareTo` follow the same NaN and signed-zero handling, but at **binary32** bit width, differing from `double` (binary64) in precision and value range.

~~~java
System.out.println(Float.NaN == Float.NaN); // false
System.out.println(Float.compare(Float.NaN, Float.NaN)); // 0
System.out.println(Float.compare(-0.0f, +0.0f)); // -1
System.out.println(Float.valueOf(-0.0f).equals(+0.0f)); // false
~~~

If the wrapper objects belong to different classes, `Double.valueOf(1.0).equals(Float.valueOf(1.0f))` is **false**: `Double.equals` only accepts objects of type `Double` and does not convert `Float` to `Double` for comparison.

## 6. API Selection Table by Purpose

| Purpose | Recommended Approach | Key Semantics to Know |
|---|---|---|
| Check if two primitives are equal under floating-point arithmetic | `a == b` | NaN differs from every value, ±0.0 are equal |
| Check if two primitives differ | `a != b` | True when either side is NaN, including both NaN |
| Filter out NaN | `Double.isNaN(a)` | Do not use `a == Double.NaN` |
| Reject both NaN and Infinity | `Double.isFinite(a)` | Only finite numbers accepted |
| Check wrapper value-equality | `Double.valueOf(a).equals(Double.valueOf(b))` | NaN equals NaN, ±0.0 differ |
| Check wrappers when null is possible | `Objects.equals(left, right)` | Applies wrapper equals, null-safe |
| Sort a double column | `Double.compare(a,b)` | Total order, NaN after +Infinity |
| Compare per SortedSet/SortedMap contract using Double | `Double.compare` or natural order | Duplicate keys when compare == 0 |
| Distinguish raw bits/payload of NaN | `Double.doubleToRawLongBits(x)` | Do not use equals/compare to preserve payload |
| Check approximate equality within tolerance | A separate predicate with explicit tolerance | Do not turn into equals/hashCode/order |
| Sort with "NaN first" or "NaN as missing" | Custom Comparator/policy | Must preserve transitivity and consistency |
| Money/decimal precision arithmetic | BigDecimal or integer units | Do not expect primitive double to always be exact |

For external input data, defining the **NaN/Infinity policy** before comparing is more important than choosing a single operator. For instance, when NaN means "not measured", the business logic might reject it, place it at the end of a list, or handle missing data; these policies are distinct.

## 7. NaN Payload, Canonical Bits, and hashCode

NaN does not have just a single raw bit pattern. In IEEE 754 representation, there are many different NaN encodings; Java lets you inspect the raw bits of a `double` value via:

~~~java
long raw = Double.doubleToRawLongBits(value);
~~~

Another method:

~~~java
long normalized = Double.doubleToLongBits(value);
~~~

`Double.doubleToLongBits` **canonicalizes NaNs**: all NaNs yield the same canonical NaN bit pattern when this method is called. `Double.equals` uses semantics compatible with the result of `doubleToLongBits`, so **two NaNs with different raw payloads still compare equal**. `Double.hashCode` is also consistent with this equality.

Example of two different payloads:

~~~java
double a = Double.longBitsToDouble(0x7ff8000000000001L);
double b = Double.longBitsToDouble(0x7ff8000000000002L);

System.out.println(Double.isNaN(a) && Double.isNaN(b)); // true
System.out.println(Double.doubleToRawLongBits(a)
        != Double.doubleToRawLongBits(b)); // true
System.out.println(Double.valueOf(a).equals(b)); // true
System.out.println(Double.compare(a, b));        // 0
~~~

The raw bit patterns above are constructed and read within the same Java 17 program per the API. Even so, **do not use NaN payloads as a long-term metadata storage channel** without an explicit serialization and platform contract: operations, transport layers, or formatting can canonicalize or fail to preserve raw payloads. If you need to store **exact bits**, work directly with raw integer bits in a specific format rather than relying on `double` operations.

Both `Double.doubleToRawLongBits` and `Double.doubleToLongBits` preserve the raw signed-zero difference:

~~~java
System.out.println(
    Double.doubleToLongBits(-0.0)
        == Double.doubleToLongBits(+0.0)); // false
~~~

For `Float`, there is a corresponding pair of APIs: `Float.floatToRawIntBits` and `Float.floatToIntBits`. When the value is NaN, `Float.floatToIntBits` canonicalizes similarly.

## 8. Complete Java 17+ Program and Exact Output

Save the file **`FloatingCompareTableDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.TreeSet;
import java.util.Set;

public class FloatingCompareTableDemo {
    public static void main(String[] args) {
        double nan = Double.NaN;
        double posZero = 0.0d;
        double negZero = -0.0d;

        System.out.println("primitive NaN == NaN: " + (nan == nan));
        System.out.println("primitive NaN != NaN: " + (nan != nan));
        System.out.println("primitive NaN < 1.0: " + (nan < 1.0));
        System.out.println("primitive NaN >= 1.0: " + (nan >= 1.0));
        System.out.println("primitive -0.0 == +0.0: "
                + (negZero == posZero));

        System.out.println("Double.equals(NaN, NaN): " +
                Double.valueOf(nan).equals(Double.valueOf(nan)));
        System.out.println("Double.compare(NaN, NaN): " +
                Double.compare(nan, nan));
        System.out.println("Double.compare(NaN, +Infinity): " +
                Double.compare(nan, Double.POSITIVE_INFINITY));
        System.out.println("Double.equals(-0.0, +0.0): " +
                Double.valueOf(negZero).equals(Double.valueOf(posZero)));
        System.out.println("Double.compare(-0.0, +0.0): " +
                Double.compare(negZero, posZero));
        System.out.println("Double.compare(+0.0, -0.0): " +
                Double.compare(posZero, negZero));

        System.out.println("1.0 / +0.0: " + (1.0 / posZero));
        System.out.println("1.0 / -0.0: " + (1.0 / negZero));
        System.out.println("Math.min(-0.0, +0.0): " +
                Math.min(negZero, posZero));
        System.out.println("Math.max(-0.0, +0.0): " +
                Math.max(negZero, posZero));

        System.out.println("isNaN(NaN): " + Double.isNaN(nan));
        System.out.println("isFinite(+Infinity): " +
                Double.isFinite(Double.POSITIVE_INFINITY));

        double nanPayloadA =
                Double.longBitsToDouble(0x7ff8000000000001L);
        double nanPayloadB =
                Double.longBitsToDouble(0x7ff8000000000002L);

        System.out.println("NaN raw bit patterns differ: " +
                (Double.doubleToRawLongBits(nanPayloadA)
                 != Double.doubleToRawLongBits(nanPayloadB)));
        System.out.println("NaN wrapper equality: " +
                Double.valueOf(nanPayloadA).equals(nanPayloadB));
        System.out.println("NaN wrapper hash codes equal: " +
                (Double.hashCode(nanPayloadA)
                 == Double.hashCode(nanPayloadB)));

        Set<Double> hashSet = new HashSet<>(Arrays.asList(
                -0.0, +0.0, Double.NaN, nanPayloadA, nanPayloadB));
        Set<Double> treeSet = new TreeSet<>(Arrays.asList(
                -0.0, +0.0, Double.NaN, nanPayloadA, nanPayloadB));

        System.out.println("HashSet size: " + hashSet.size());
        System.out.println("TreeSet size: " + treeSet.size());
        System.out.println("Sorted values: " + treeSet);

        System.out.println("Float NaN == NaN: "
                + (Float.NaN == Float.NaN));
        System.out.println("Float.compare(NaN, NaN): "
                + Float.compare(Float.NaN, Float.NaN));
        System.out.println("Float.compare(-0.0f, +0.0f): "
                + Float.compare(-0.0f, +0.0f));
    }
}
~~~

Compile and run:

~~~bash
javac FloatingCompareTableDemo.java
java FloatingCompareTableDemo
~~~

**Verified stdout output on Java 17:**

~~~text
primitive NaN == NaN: false
primitive NaN != NaN: true
primitive NaN < 1.0: false
primitive NaN >= 1.0: false
primitive -0.0 == +0.0: true
Double.equals(NaN, NaN): true
Double.compare(NaN, NaN): 0
Double.compare(NaN, +Infinity): 1
Double.equals(-0.0, +0.0): false
Double.compare(-0.0, +0.0): -1
Double.compare(+0.0, -0.0): 1
1.0 / +0.0: Infinity
1.0 / -0.0: -Infinity
Math.min(-0.0, +0.0): -0.0
Math.max(-0.0, +0.0): 0.0
isNaN(NaN): true
isFinite(+Infinity): false
NaN raw bit patterns differ: true
NaN wrapper equality: true
NaN wrapper hash codes equal: true
HashSet size: 3
TreeSet size: 3
Sorted values: [-0.0, 0.0, NaN]
Float NaN == NaN: false
Float.compare(NaN, NaN): 0
Float.compare(-0.0f, +0.0f): -1
~~~

The program uses no random numbers, so the results do not depend on execution schedule. The NaN payload bit patterns are constructed explicitly, and `TreeSet` prints according to `Double`'s natural order; `HashSet` prints only its **size**, without relying on an unguaranteed iteration order.

## 9. Collections: HashSet, TreeSet, HashMap, TreeMap

The two collection families use two different contracts:

- `HashSet<Double>` / `HashMap<Double,...>` use `Double.equals` and `Double.hashCode` to detect duplicate keys.
- `TreeSet<Double>` / `TreeMap<Double,...>` use `Double.compareTo` or a supplied `Comparator`; under natural ordering, keys where the comparator returns 0 are considered at the same key position.

Fortunately, `Double.compareTo` is **consistent with `Double.equals`**, including NaN and signed zero, so for pure `Double` values both structures distinguish the two zeros and collapse all NaNs into a single key under their respective equality concepts.

| Inserted Data | HashSet Size | Natural-Order TreeSet Size | Explanation |
|---|---:|---:|---|
| `+0.0`, `-0.0` | 2 | 2 | The two zeros are not wrapper-equal and compare nonzero |
| `NaN`, `NaN` | 1 | 1 | NaNs are wrapper-equal and compare = 0 |
| Two NaNs with different raw payloads | 1 | 1 | Payloads are canonicalized in equality |
| `-0.0`, `+0.0`, three NaNs | 3 | 3 | Three distinct key groups under wrapper rules |
| `1.0`, `1.0` | 1 | 1 | Completely identical |

**Do not apply primitive `==` rules to predict `HashSet<Double>` behavior.** If `NaN == NaN` is false yet the collection still deduplicates NaN, that is because the collection uses wrapper `equals` rather than primitive `==`.

Map lookup example:

~~~java
Map<Double, String> map = new HashMap<>();
map.put(Double.NaN, "missing");
map.put(-0.0, "negative");
map.put(+0.0, "positive");

System.out.println(map.size());             // 3
System.out.println(map.get(Double.NaN));    // missing
System.out.println(map.get(-0.0));          // negative
System.out.println(map.get(+0.0));          // positive
~~~

This is code **inside a method**, requiring imports for `java.util.Map` and `java.util.HashMap`. If using `TreeMap` with `Double`'s natural ordering, the structure still distinguishes the two zeros and treats NaNs as the same key.

**Beware of custom comparators**: if you replace the comparator with a rule where `compare(a,b) == 0` while `!a.equals(b)`, key uniqueness in TreeSet/TreeMap will differ from HashSet/HashMap. That may be an intentional choice, but it must be documented and tested.

## 10. Sorting Data Containing NaN: Three Common Policies

### Policy A — Keep Java Natural Order

Use `Double.compare`, `Comparator.comparingDouble`, `Arrays.sort(double[])`, or `DoubleStream.sorted()` depending on the data structure. NaN comes last, and signed zeros are ordered separately:

~~~java
double[] values = {
    Double.NaN, 0.0, -0.0,
    Double.POSITIVE_INFINITY, -3.0, Double.NEGATIVE_INFINITY
};
java.util.Arrays.sort(values);
System.out.println(java.util.Arrays.toString(values));
// [-Infinity, -3.0, -0.0, 0.0, Infinity, NaN]
~~~

The snippet above sits inside a method. This policy is convenient for sorting, but **does not mean NaN is mathematically "the largest number"**; it merely has a conventional position in the wrapper ordering.

### Policy B — Reject NaN and Infinity

If a business data column must contain finite numbers, validate upfront:

~~~java
static double requireFinite(double x) {
    if (!Double.isFinite(x)) {
        throw new IllegalArgumentException("Expected finite double");
    }
    return x;
}
~~~

This is a method inside a class. Once NaN/Infinity are rejected, processing logic avoids many unexpected edge cases. However, signed zero can still exist if the API permits it; decide whether to normalize ±0.0 according to data requirements.

### Policy C — Treat NaN as Missing Data

If NaN represents "no measurement", you can separate it into an explicit **missing-data state** using a clear domain model type, rather than relying on a `double` value with special comparison properties. When sorting, the application must define whether "missing" comes first/last and whether it participates in statistics.

If you choose a custom comparator, it must obey the `Comparator` contract (antisymmetry of sign, transitivity, consistency). Do not turn an "approximately equal within epsilon" check into a comparator and pass it to `TreeSet`: approximate equality may fail transitivity, causing sorted collections to behave unreliably.

## 11. "Approximate Equality": Different from Equality and NaN Handling

With floating-point numbers, two mathematically equivalent formulas can yield slightly different results due to rounding error. Many problems require a tolerance check:

~~~java
static boolean approximatelyEqual(double a, double b, double epsilon) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(epsilon) || epsilon < 0.0) {
        return false;
    }
    return Math.abs(a - b) <= epsilon;
}
~~~

This is an **illustrative predicate** with a policy that rejects NaN/Infinity. It also has limitations: the subtraction `a - b` can overflow to Infinity when `a`/`b` are near extreme bounds, even when `a` and `b` are individually finite; this must be designed for and tested if used across extreme floating-point ranges. Absolute tolerance is only appropriate when units and data scale are reasonable; sometimes relative tolerance or a combination of both is needed.

Key points:

- `Double.compare(a,b) == 0` **is not an approximate equality check**.
- `a == b` on primitives **is not an approximate equality check**.
- For NaN, the predicate above proactively returns false rather than relying on an implicit rule.
- For ±0.0, `Math.abs(a-b) <= epsilon` returns true when `epsilon >= 0`; that is a **domain decision of the predicate**, distinct from wrapper equality.
- Do not override `equals`/`hashCode` simply because a calculation needs a tolerance margin.

Non-transitivity example: A = 0.00, B = 0.09, C = 0.18, and epsilon = 0.10. A is close to B, B is close to C, yet A is not close to C. Hence this relation **cannot** directly replace equality for HashMap keys or comparator ordering.

## 12. Pitfalls with Casting, Boxing, Null, and BigDecimal

### 12.1. Primitives and Wrappers Do Not Always Compare the Same Way

~~~java
Double obj = Double.valueOf(Double.NaN);
double raw = Double.NaN;

System.out.println(obj.equals(Double.valueOf(raw))); // true
System.out.println(obj.doubleValue() == raw);         // false
~~~

`obj.equals` uses wrapper equality; `obj.doubleValue() == raw` uses primitive `==`. If `obj` is null, `obj.doubleValue()` throws `NullPointerException`.

In generic collections such as `List<Double>`, elements are typically boxed into `Double`; operations like `contains` and `remove(Object)` apply `equals`, not primitive `==`. Thus `list.contains(Double.NaN)` can be true even though `Double.NaN == Double.NaN` is false.

### 12.2. Float and Double Are Not Equal Just Because Numbers Look Alike

~~~java
Object a = Double.valueOf(1.0);
Object b = Float.valueOf(1.0f);
System.out.println(a.equals(b)); // false
~~~

They are two different wrapper classes. If type conversion is needed for numerical comparison, you must account for the conversion operation and precision issues. For large numbers, converting `long` to `double` can lose precision; do not blindly cast every type to `double` and conclude two values are identical.

### 12.3. BigDecimal Has a Completely Different Contract

`BigDecimal` has neither NaN nor ±Infinity like floating-point primitives. Additionally, `BigDecimal.equals` checks both **value and scale**, whereas `BigDecimal.compareTo` compares by numerical value:

~~~java
java.math.BigDecimal x = new java.math.BigDecimal("2.0");
java.math.BigDecimal y = new java.math.BigDecimal("2.00");
System.out.println(x.equals(y));      // false
System.out.println(x.compareTo(y));   // 0
~~~

This is merely a **contrast so contracts are not confused**, not a NaN/signed-zero rule of `Double`. `BigDecimal.valueOf(Double.NaN)` does not create a valid NaN BigDecimal value: it throws `NumberFormatException`. When converting floating-point data to BigDecimal, handle NaN/Infinity first and consider signed zero because decimal representation does not retain the same signed-zero semantics as `double`.

## 13. Checklist When Reviewing Floating-Point Comparison Bugs

1. **Is the variable actually a primitive or a wrapper?** `==` between two wrapper references checks identity; `==` on primitives or with unboxing checks floating-point value.
2. **Can the data contain NaN?** If so, primitive inequality comparisons can all evaluate to false, while `!=` evaluates to true. Use `isNaN` when detection is needed.
3. **Can it contain Infinity?** `isNaN` does not block Infinity; if finite values are required, use `isFinite`.
4. **Does signed zero matter?** If sign distinction must be preserved, use wrapper equality, `Double.compare`, or bit APIs; if only numerical zero matters, primitive `==` treats them as equal.
5. **Are you sorting or using a SortedSet?** Choose `Double.compare` or a comparator with a clear contract; do not pass `(a,b) -> a < b ? -1 : (a > b ? 1 : 0)` to `TreeSet` when NaN may appear, because it treats NaN as equal to all values and can violate consistency.
6. **Are you using HashMap/HashSet?** Reason from `Double.equals/hashCode`, not primitive `==`.
7. **Do you need to identify NaN payloads?** Use `doubleToRawLongBits` and an explicit bit-storage protocol.
8. **Do you need approximate comparison?** Write a local predicate with tolerance requirements; do not alter global `equals` and do not arbitrarily use it as a sorted comparator.
9. **Are you converting types?** Precision can be lost or non-finite states altered; do not treat casting as a neutral step.
10. **Have you defined business behavior for missing data?** "NaN = missing" is a policy, not something to infer solely from `Double.compare` ordering.

### Minimum Test Questions

- Is `Double.NaN == Double.NaN` false?
- Is `Double.isNaN(Double.NaN)` true?
- Is `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` true?
- Is `Double.compare(Double.NaN, Double.POSITIVE_INFINITY) > 0` true?
- Is `+0.0 == -0.0` true?
- Is `Double.compare(-0.0,+0.0) < 0` true?
- Is `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` false?
- Is `1.0/-0.0` equal to -Infinity?
- Does a `HashSet<Double>` receiving 2 oppositely signed zeros and 3 NaNs have size = 3?
- Does a `TreeSet<Double>` with that data produce `[-0.0, 0.0, NaN]` in natural order?

## 14. Exercises and Answers

**Exercise 1.** Predict the output of the following expressions, stating clearly whether primitive or wrapper semantics apply:

~~~java
double a = Double.NaN;
System.out.println(a == a);
System.out.println(Double.compare(a, a) == 0);
System.out.println(Double.valueOf(a).equals(a));
~~~

**Exercise 2.** Why is `0.0 == -0.0` true while `Double.valueOf(0.0).equals(-0.0)` is false? Name an operation that exposes the difference.

**Exercise 3.** Predict the sorted set in `TreeSet<Double>` for `-0.0`, `+0.0`, `Double.NaN`, and `Double.POSITIVE_INFINITY`. Why is NaN at the end?

**Exercise 4.** You receive sensor readings that may return NaN and Infinity. Propose validation rules before computing an average and before saving to a database.

**Exercise 5.** Two NaNs have different raw payloads. What do `Double.equals` and `Double.compare` return? Which API is needed to preserve the raw bit difference?

**Exercise 6.** A comparator is written as:

~~~java
Comparator<Double> bad = (x, y) -> x < y ? -1 : x > y ? 1 : 0;
~~~

Why should `bad` not be used with values containing NaN in a `TreeSet`? Propose a replacement.

**Answers:**

1. `false`, `true`, `true`. In the third expression, `Double.equals(Object)` receives argument `a` boxed into `Double`, so NaN equals NaN.
2. Primitive equality treats both zeros as numerically equal; the wrapper distinguishes the sign bit. `1.0 / -0.0` yields -Infinity, unlike +Infinity from `1.0 / +0.0`.
3. `[-0.0, 0.0, Infinity, NaN]` according to `Double.compare` ordering; NaN is placed after all numeric values.
4. If the domain only accepts finite numbers, use `Double.isFinite(x)` to reject both NaN and ±Infinity; define missing-data rules separately and ensure data is validated before storing/computing.
5. `Double.equals` returns true and `Double.compare` returns 0; use `Double.doubleToRawLongBits` to distinguish raw payloads when needed.
6. That comparator returns 0 between NaN and many different values, failing to establish a proper ordering. Use `Double::compare` or a custom comparator that handles NaN explicitly while preserving ordering properties.

## 15. Java 17 References

- Java SE 17 — `Double` (`equals`, `compare`, `compareTo`, `isNaN`, `doubleToLongBits`, `doubleToRawLongBits`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html
- Java SE 17 — `Float`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html
- Java SE 17 — `Math.min`/`max`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html
- Java SE 17 — `Comparator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html
- Java Language Specification 17 — `15.20.1 Numerical Comparison Operators` and `15.21.1 Numerical Equality Operators`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html
- Java SE 17 — `TreeSet` and `HashSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html

**Takeaway:** for primitives, **NaN does not equal NaN** and **+0.0 equals -0.0**. For `Double.equals` and `Double.compare`, those two rules **flip at both special points**: all NaNs are treated as equal and signed zeros are distinguished. Choose the API that matches your exact need: arithmetic, hash key, sorting, or preserving raw bits.
