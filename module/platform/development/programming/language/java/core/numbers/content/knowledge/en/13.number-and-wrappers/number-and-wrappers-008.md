# compare, compareTo, equals, and hashCode — Java Core: Number and Wrappers

## 1. Why Does Java Have Multiple Ways to "Compare Numbers"?

Java has several numeric primitive types (`byte`, `short`, `int`, `long`, `float`, `double`) and corresponding wrapper classes (`Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`). Beyond comparing with the `==` operator, developers also encounter:

- `Integer.compare(a, b)`, `Long.compare(a, b)`, `Double.compare(a, b)`…: **static methods** comparing two values of the same primitive type.
- `wrapperA.compareTo(wrapperB)`: **instance method** comparing ordering between wrappers of the same class.
- `wrapperA.equals(other)`: **instance method** deciding whether two objects are considered to have the same value under the class's contract.
- `wrapperA.hashCode()`: hash code consistent with `equals` when used as keys in `HashMap` or elements in `HashSet`.
- Operators `==`, `<`, `>`, `<=`, `>=`: compare **primitives**, or may trigger unboxing when operands are wrappers.

They are related, yet **are not arbitrarily interchangeable**. For example:

```java
Integer a = 9;
Long b = 9L;

System.out.println(a.equals(b)); // false
System.out.println(a.longValue() == b.longValue()); // true
```

`Integer.equals` does not treat a `Long` with the same mathematical quantity as the same object type. Conversely, after extracting primitive values and comparing with a matching type, `9L == 9L` is true.

**Lesson objectives:**

1. Distinguish comparing **value**, **object type**, **identity**, and **ordering**.
2. Use `compare` and `compareTo` properly for signed integers, unsigned interpretation, and floating-point numbers.
3. Understand `equals`/`hashCode`, required contracts, and impact on collections.
4. Handle `Float`/`Double` properly with `NaN`, `+0.0`, and `-0.0`.
5. Know why `==` on wrappers should not be used to compare object values, especially with caching/boxing.
6. Avoid subtraction-based comparators and avoid using "within epsilon" comparisons for equality or sorting.
7. Read and test Java 17+ examples with reproducible outputs.

**Scope:** `Number` and standard Java wrappers, and how they participate in comparison/collections. `BigDecimal` and `BigInteger` are included only to clarify differing comparison behaviors in the `Number` family, without turning this lesson into a detailed decimal arithmetic guide.

## 2. Primitive Types, Wrappers, and the `Number` Class

| Primitive | Wrapper | Type family in Java | Comparable |
| --- | --- | --- | --- |
| `byte` | `Byte` | Extends `Number` | `Comparable<Byte>` |
| `short` | `Short` | Extends `Number` | `Comparable<Short>` |
| `int` | `Integer` | Extends `Number` | `Comparable<Integer>` |
| `long` | `Long` | Extends `Number` | `Comparable<Long>` |
| `float` | `Float` | Extends `Number` | `Comparable<Float>` |
| `double` | `Double` | Extends `Number` | `Comparable<Double>` |

`Number` is an abstract class providing ways to **obtain values in specific numeric types** via `intValue()`, `longValue()`, `floatValue()`, `doubleValue()`, and other conversion methods. It **does not define a common `compareTo` for comparing any `Number`** and does not mandate a shared `equals` definition across all subclasses.

This means:

```java
Number a = Integer.valueOf(5);
Number b = Double.valueOf(5.0);
```

You cannot simply call `a.compareTo(b)` on the declared type `Number`; `Number` has no `compareTo(Number)`. Calling `a.equals(b)` dispatches to `Integer.equals` and returns `false`. You must specify an explicit comparison policy when accepting multiple `Number` subclasses; converting everything to `double` is not automatically safe either, because it can lose precision for large integers or `BigDecimal`.

### 2.1. Auto-boxing and unboxing

`Integer n = 9;` can be compiled into a boxing operation. `int x = n;` can be compiled into unboxing, equivalent to extracting the primitive value. When `null` is involved:

```java
Integer missing = null;
// int x = missing; // runtime NullPointerException due to unboxing
```

`compareTo` and `equals` also have null rules: `a.equals(null)` returns `false` when `a` is non-null, whereas `a.compareTo(null)` on a non-null `Integer a` normally throws `NullPointerException`. If the receiver `a` itself is null, calling any method throws `NullPointerException`.

## 3. Quick Decision Table Among Comparison Approaches

| Purpose | Approach | Notes |
| --- | --- | --- |
| Do two `int`s have the same value? | `a == b` | Primitive equality |
| Order two `int`s without overflow risk? | `Integer.compare(a,b)` | Returns negative/0/positive |
| Order two `long`s | `Long.compare(a,b)` | Do not use `(int)(a-b)` |
| Order two wrappers of the same type | `a.compareTo(b)` | Receiver/argument must have matching type |
| Are two wrappers equal per class contract? | `a.equals(b)` | Null-safe if `a` is guaranteed non-null |
| Wrappers may be null on either side? | `Objects.equals(a,b)` | Returns true if both references are null |
| Wrapper used as a hash key? | `equals` paired with `hashCode` | Java wrappers already satisfy the contract |
| Sort `double` numeric data | `Double.compare(a,b)` | Has rules for NaN and signed zero |
| Interpret `int` bits as unsigned | `Integer.compareUnsigned(a,b)` | Does not change bits, only ordering |
| Check floating-point results within tolerance? | Dedicated `near(a,b,tolerance)` function | Do not use as default `equals`/`compareTo` |

Distinguish `compare(a,b) < 0` from `compare(a,b) == -1`. The general comparison contract only guarantees the **sign of the result**, not that it will always be `-1`, `0`, or `1`. For instance, `Byte.compare((byte)-1, (byte)1)` can return `-2` by subtracting byte values in that method's implementation. Write `< 0`, `== 0`, `> 0`.

## 4. `compare`: Static Methods Accepting Primitives

Numeric wrapper classes have static comparison methods:

```java
int c1 = Integer.compare(9, 12);       // negative
int c2 = Long.compare(9L, 12L);        // negative
int c3 = Float.compare(9.0f, 12.0f);   // negative
int c4 = Double.compare(9.0, 12.0);    // negative
```

Although named on wrapper classes, the inputs to these methods are **primitives** (e.g., `int,int` or `double,double`) and the return value is an `int` indicating ordering.

`Byte`/`Short` also have `Byte.compare(byte,byte)` and `Short.compare(short,short)`. These methods are handy when writing a `Comparator` via lambdas or method references.

### 4.1. Do not compare integers by subtraction

The following snippet can be wrong:

```java
// DO NOT USE:
Comparator<Integer> bad = (a, b) -> a - b;
```

If `a=Integer.MAX_VALUE` and `b=-1`, the mathematical difference exceeds the `int` range; `int` subtraction overflows, flipping the ordering sign. Instead use:

```java
Comparator<Integer> order = Integer::compare;
```

Or:

```java
Comparator<Integer> order = Comparator.naturalOrder();
```

The `Comparator` snippets require `import java.util.Comparator` or a fully qualified name. For `long`, avoid `return (int)(a-b);` because it risks both `long` overflow and 32-bit truncation; use `Long.compare(a,b)`.

### 4.2. Static compare returns ordering, not boolean

`Integer.compare(10,10)` returns the integer `0`. It **does not** return `true`; to test equality via compare, write `Integer.compare(a,b)==0`, though for ordinary primitive `int`s `a==b` is clearer.

## 5. `compareTo`: The Wrapper `Comparable` Contract

Wrappers implement `Comparable` for **the same object type**. For example:

```java
Integer a = 9;
Integer b = 12;
System.out.println(a.compareTo(b)); // -1
```

Negative result: `a` comes before `b`; 0 result: same position under natural ordering; positive result: `a` comes after `b`.

`Integer.compareTo` takes `Integer`; `Long.compareTo` takes `Long`. They **do not** allow:

```java
Integer left = 9;
Long right = 9L;
// left.compareTo(right); // DOES NOT COMPILE: Long is not Integer
```

Likewise, `Number` has no common natural ordering across all subclasses. `BigDecimal` and `BigInteger` each have their own `compareTo`.

### 5.1. Natural ordering and `Collections.sort`

For a `List<Integer>`, you can call `Collections.sort(list)` or `list.sort(null)` to use `Integer`'s natural ordering. For a `List<Double>`, `Double`'s natural ordering has special rules for `NaN` and signed zero.

Do not assume a `List<Number>` mixing `Integer` and `Double` automatically has a valid comparator. Choose a **homogeneous data model** or define an ordering with an explicit contract.

### 5.2. `compareTo` and `equals` are not always consistent across all Number types

The wrappers `Byte`, `Short`, `Integer`, `Long`, `Float`, and `Double` design natural ordering to align with each class's equality (in particular `Float`/`Double` handle NaN/zero per the wrapper contract).

However, another `Number` subclass, such as `BigDecimal`, differs:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.compareTo(y)); // 0
System.out.println(x.equals(y));    // false
```

The two `BigDecimal`s are equal in **numeric value** yet differ in **scale**, so `equals` returns `false`. The snippet above requires `import java.math.BigDecimal;`. This case shows you cannot claim every `Number` object with `compareTo()==0` also satisfies `equals()==true`.

## 6. `equals`: Equality by Class Contract, Not Just Same Number

For `Integer`:

```java
System.out.println(Integer.valueOf(9)
        .equals(Integer.valueOf(9))); // true

System.out.println(Integer.valueOf(9)
        .equals(Long.valueOf(9L)));   // false
```

`Integer.equals` requires the compared object **to be an `Integer`** and have the same primitive `int` value. `Long.equals` works similarly within `Long`. Therefore `Integer.valueOf(9)` and `Long.valueOf(9)` are not equal under `equals` despite having the same mathematical quantity.

Distinguishing examples:

| Comparison | Result | Why |
| --- | --- | --- |
| `Integer.valueOf(9).equals(Integer.valueOf(9))` | true | Same class, same value |
| `Integer.valueOf(9).equals(Long.valueOf(9))` | false | Different class |
| `Double.valueOf(9.0).equals(Float.valueOf(9.0f))` | false | Different class |
| `Long.valueOf(9).equals(null)` | false | `equals(null)` |
| `Integer.valueOf(9).intValue() == 9` | true | Primitive int equality |
| `Integer.valueOf(9).longValue() == Long.valueOf(9L).longValue()` | true | After appropriate conversion, primitive long equality |

**Do not convert every `Number` to `double` just to compare.** `double` has 53 bits of significand precision; many `long` values above `2⁵³` are no longer distinguishable accurately. `BigDecimal.doubleValue()` can also round or overflow to infinity, losing information. If a domain truly needs cross-`Number` comparison, define range/precision requirements and pick an appropriate intermediate representation.

### 6.1. `Objects.equals` only handles null, it does not coerce types

`java.util.Objects.equals(a,b)` returns `true` if both are null; `false` if only one is null; and delegates to `a.equals(b)` if both are non-null.

`Objects.equals(Integer.valueOf(9), Long.valueOf(9))` is still `false`. This is not a "general numeric value comparison," but a null-safe way to invoke `equals`.

## 7. `hashCode`: Contract with `equals`

`hashCode` is a method from `Object`. For two objects `x` and `y`:

> If `x.equals(y)` is true, then **it is required** that `x.hashCode() == y.hashCode()`.

The converse **is not required**: two unequal objects can share the same hash, known as a **hash collision**. A hash is not a unique identifier and does not guarantee security properties.

Wrappers implement `hashCode` based on value contents consistent with `equals`:

- `Integer.hashCode(int value)` returns the input `int` itself.
- `Long.hashCode(long value)` folds the high/low bits of `long` into an `int`.
- `Float.hashCode(float value)` and `Double.hashCode(double value)` use bit representations consistent with `equals`, including distinguishing signed zero and canonicalizing NaN.
- `Byte` and `Short` use their corresponding numeric values for hashing, per each API's rules.

`Integer.hashCode(9)` is a **static method**, while `Integer.valueOf(9).hashCode()` is an **instance method**. Both produce the hash corresponding to the same value.

### 7.1. HashMap and HashSet

`HashMap`/`HashSet` use hashes to find candidate buckets and then use key equality to determine duplicates. Hence:

```java
Set<Number> values = new HashSet<>();
values.add(Integer.valueOf(9));
values.add(Long.valueOf(9L));
System.out.println(values.size()); // 2
```

Requires importing `java.util.Set` and `java.util.HashSet`; this snippet belongs inside a method. `Integer(9)` and `Long(9)` are not equal under `equals`, so they remain two distinct elements.

**Do not use `hashCode` to conclude two objects are equal.** Matching hashes are only a quick pre-check, not a replacement for `equals`.

**Do not pick a random hash** for a wrapper or immutable object. If a custom key has multiple fields, `equals` and `hashCode` must share the same notion of identity, and you must avoid mutating fields used in hashing after placing the key in a map/set.

## 8. `==` on Wrappers: Reference Comparison or Unboxing?

When both operands of `==` are **wrapper references of the same type** (e.g., two `Integer`s), `==` checks **object identity**, not contents. Because Java boxing/`valueOf` caches certain value ranges, results can be misleading:

```java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);
boolean sameReference = (a == b); // true for Integer.valueOf in -128..127

Integer c = Integer.valueOf(1000);
Integer d = Integer.valueOf(1000);
// c == d should not be used to check value: caching outside standard range depends on implementation.
boolean sameValue = c.equals(d); // true
```

To **compare wrapper values**, use `a.equals(b)` when the receiver is known non-null, or `Objects.equals(a,b)` when null is possible. To compare as primitives, unbox deliberately and handle null:

```java
Integer maybe = Integer.valueOf(42);
boolean equalsPrimitive = maybe != null && maybe.intValue() == 42;
```

### 8.1. Two wrappers of different types cannot use `==` directly

Two references belonging to two independent wrapper classes such as `Integer` and `Long` **cannot be compared directly with `==`**. Java does not automatically unbox both sides in this expression:

```java
Integer a = Integer.valueOf(9);
Long b = Long.valueOf(9L);
// boolean invalid = (a == b); // COMPILE ERROR: incomparable types.
boolean sameNumericValue = a.longValue() == b.longValue(); // true.
boolean sameObjectValue = a.equals(b); // false: different wrapper class.
```

When **one operand is a primitive**, such as `a == 9L`, Java can unbox `Integer` to `int` and widen to `long` for comparison. If both references are declared as `Number`, `==` between them checks **same object**, not numeric value. When comparing numbers across different wrapper types, convert explicitly in a range-preserving way and check `null` before calling methods; `longValue()` fits the `Integer`/`Long` pair.

## 9. `Float`/`Double`: NaN and Signed Zero Make the Sharpest Difference

IEEE 754 floating-point numbers have special values that integers lack:

- `+0.0` and `-0.0`: two distinct bit patterns, yet primitive `+0.0 == -0.0` is `true`.
- `NaN`: primitive `Double.NaN == Double.NaN` is `false`.
- `+Infinity`, `-Infinity`: infinities with corresponding arithmetic ordering.

With the `Double` wrapper:

- `Double.compare(-0.0, +0.0)` returns a negative number: **−0.0 precedes +0.0**.
- `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` returns `false`.
- `Double.compare(Double.NaN, Double.POSITIVE_INFINITY)` returns a positive number: NaN comes after +Infinity.
- `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` returns `true`, even though primitive `NaN == NaN` is `false`.

Corresponding behaviors apply to `Float` at 32-bit width.

### 9.1. Common reference table

| Expression | Result |
| --- | --- |
| `+0.0 == -0.0` | true |
| `Double.compare(-0.0,+0.0)` | negative value (JDK returns -1) |
| `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` | false |
| `Double.NaN == Double.NaN` | false |
| `Double.compare(Double.NaN,Double.NaN)` | 0 |
| `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` | true |
| `Double.compare(Double.NaN,Double.POSITIVE_INFINITY)` | positive value |
| `Double.hashCode(-0.0) == Double.hashCode(+0.0)` | false |

Why do wrappers make these choices? `Double.equals` is based on `doubleToLongBits` to distinguish ±0, and that bit method **canonicalizes NaN patterns**. Natural ordering/`compare` is defined consistently with wrapper equality, making it suitable for keys/sorting under `Double` semantics.

**Do not treat the sign of zero as "they are always identical anyway."** Signed zero can affect division, `Math.atan2`, and `Math.min/max`. If a specific business rule wants positive and negative zero merged, apply an explicit normalization policy.

### 9.2. NaN does not equal itself under primitive `==`

`Double.NaN == Double.NaN` being false is the rule for primitive floating-point comparison. Yet `Double.NaN` wrapped in a wrapper follows a different `equals` contract, which treats NaNs as an equal equivalence group.

Do not use `value == Double.NaN` to detect NaN; use `Double.isNaN(value)` or `Float.isNaN(value)`. Do not arbitrarily apply epsilon comparisons to treat NaN as "nearly equal."

### 9.3. Floating-point hashing uses canonicalized bits

`Double.hashCode(value)` uses bits compatible with `Double.equals`, including canonicalizing NaN. If you write a custom `equals` over raw bits with `doubleToRawLongBits` while using `Double.hashCode` which ignores NaN payload differences, the "equal ⇒ same hash" invariant still holds, yet equality and hashing no longer describe the exact same information; consider carefully when designing bit-level keys.

A simple option when wanting to mirror wrapper semantics is using `Double.doubleToLongBits` for `equals` and `Double.hashCode` for hashing, instead of trying to piece together signed-zero/NaN logic from individual `==` checks.

## 10. Runnable Program A — `compare`, `compareTo`, `equals`, and Unsigned

Save as **`WrapperComparison.java`**:

```java
public class WrapperComparison {
    public static void main(String[] args) {
        Integer a = Integer.valueOf(9);
        Integer b = Integer.valueOf(12);
        Long sameNumber = Long.valueOf(9L);

        System.out.println(Integer.compare(9, 12));
        System.out.println(a.compareTo(b));
        System.out.println(a.equals(Integer.valueOf(9)));
        System.out.println(a.equals(sameNumber));

        System.out.println(Integer.hashCode(9));
        System.out.println(Byte.compare((byte) -1, (byte) 1));

        System.out.println(Integer.compare(-1, 1));
        System.out.println(Integer.compareUnsigned(-1, 1));
        System.out.println(Long.compareUnsigned(-1L, 1L));
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 WrapperComparison.java
java WrapperComparison
```

**Exact stdout:**

```text
-1
-1
true
false
9
-2
-1
1
1
```

Notes:

1. `Integer.compare(9,12)` and `Integer(9).compareTo(Integer(12))` both return negative (in this case `-1`).
2. `Integer.equals` returns `true` for the same `Integer(9)` but `false` for `Long(9L)`.
3. `Integer.hashCode(9)` equals `9`.
4. `Byte.compare(-1,1)` returns `-2`; demonstrating why you should check the **sign** of a comparator result, not require strictly `-1/0/1`.
5. Under signed order, `-1` precedes `1`; under unsigned interpretation of 32/64 bits, the all-ones bit pattern is greater than `1`. `compareUnsigned` does not turn `int` into a new unsigned primitive type.

## 11. Runnable Program B — `Double`, NaN, Signed Zero, and Collections

Save as **`FloatingWrapperComparison.java`**:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class FloatingWrapperComparison {
    public static void main(String[] args) {
        double positiveZero = +0.0;
        double negativeZero = -0.0;

        System.out.println(positiveZero == negativeZero);
        System.out.println(Double.compare(negativeZero, positiveZero));
        System.out.println(Double.valueOf(negativeZero)
                .equals(Double.valueOf(positiveZero)));

        System.out.println(Double.NaN == Double.NaN);
        System.out.println(Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN)));
        System.out.println(Double.compare(Double.NaN,
                Double.POSITIVE_INFINITY));

        Set<Double> hashed = new HashSet<>();
        hashed.add(positiveZero);
        hashed.add(negativeZero);
        hashed.add(Double.NaN);
        hashed.add(Double.NaN);
        System.out.println(hashed.size());

        TreeSet<Double> ordered = new TreeSet<>();
        ordered.add(positiveZero);
        ordered.add(negativeZero);
        ordered.add(Double.NaN);
        ordered.add(Double.NaN);
        System.out.println(ordered.size());
        System.out.println(ordered.first());
        System.out.println(ordered.last());
    }
}
```

Run:

```bash
javac --release 17 FloatingWrapperComparison.java
java FloatingWrapperComparison
```

**Exact stdout:**

```text
true
-1
false
false
true
1
3
3
-0.0
NaN
```

Explanation:

- `primitive ==` treats the two signed zeros as equal; `Double.compare` and `Double.equals` distinguish them.
- `NaN == NaN` is false, whereas `Double.equals` treats `NaN` wrappers as equivalent.
- `HashSet<Double>` uses `equals`/`hashCode`, and `TreeSet<Double>` uses natural ordering; for these `Double` values, both retain `+0.0`, `-0.0`, and one `NaN` value, totaling `3` elements.
- `TreeSet.first()` is `-0.0`, `TreeSet.last()` is `NaN` per `Double`'s ordering; `HashSet` iteration order must not be used to infer natural ordering.

## 12. Runnable Program C — Boxing, Null, and `Objects.equals`

Save as **`BoxingEquality.java`**:

```java
import java.util.Objects;

public class BoxingEquality {
    public static void main(String[] args) {
        Integer smallA = Integer.valueOf(42);
        Integer smallB = Integer.valueOf(42);
        Integer bigA = Integer.valueOf(1000);
        Integer bigB = Integer.valueOf(1000);

        System.out.println(smallA == smallB);
        System.out.println(bigA.equals(bigB));

        Integer missing = null;
        System.out.println(Objects.equals(missing, null));
        System.out.println(Objects.equals(missing, smallA));

        Integer n = Integer.valueOf(9);
        Long m = Long.valueOf(9L);
        System.out.println(n.equals(m));
        System.out.println(n.intValue() == m.longValue());
    }
}
```

Run:

```bash
javac --release 17 BoxingEquality.java
java BoxingEquality
```

**Exact stdout:**

```text
true
true
true
false
false
true
```

This code **intentionally does not print** `bigA == bigB`: caching outside the minimum range of `Integer.valueOf` can vary by implementation/configuration, so that output is not made a portable contract. `equals` still returns `true` for the same integer content.

## 13. The `Number` Class and Mixed Comparisons: Avoid Arbitrary Conversions

Suppose an API receives `Number x, Number y`. Multiple comparison policies can be valid, yet you must pick **one** based on the contract:

**Policy A — types must match:** only accept the same wrapper class and use `equals`. Useful when the numeric type carries business meaning, e.g., `int` is a count while `double` is a measurement.

**Policy B — exact integer values:** accept only integer types within a defined range, convert to `long` or `BigInteger` with checks to compare, avoiding rounding.

**Policy C — floating-point values within acceptable precision:** compare `doubleValue()` with suitable criteria while handling NaN/infinity. However, this is unsuitable if inputs include huge `BigDecimal`s or integers requiring precision beyond 53 bits.

**Policy D — sorting mixed numeric types:** must define a total order over type, value, NaN, ±Infinity, signed zero, and values that cannot convert exactly. Ordering by type first and value second may fit some domains, yet does not represent a mathematical order across all `Number`s.

**Warning:** forcing every `Number` to `double` and calling `Double.compare` can conflate distinct large `long` values. For example, `9_007_199_254_740_992L` and `9_007_199_254_740_993L` convert to the **same** `double` value because binary64 precision has only 53 significand bits.

Without a specific requirement to compare across multiple `Number` classes, keeping a consistent generic/concrete type directly in the API is usually safer.

## 14. `Comparable` and `Comparator` Contracts When Putting Wrappers in Sort/Map

For `Comparable<T>`/`Comparator<T>`, the sign of the result must describe an ordering satisfying basic rules: sign antisymmetry, transitivity, and consistency when comparing as 0.

A valid comparator for `double` measurement data typically starts with:

```java
Comparator<Double> natural = Double::compare;
```

A valid comparator for an object with a `double` field can be written:

```java
Comparator<Sample> ordered =
        Comparator.comparingDouble(Sample::measurement)
                .thenComparingLong(Sample::id);
```

Where `Sample` is a class/record with matching `measurement()` and `id()` methods; this is a **code snippet**, not a standalone program without defining `Sample`.

Why `thenComparingLong`? When two `Sample`s have the same measurement under `Double.compare`, the application may still want a tie-breaking order by ID. Note that **`Comparator.compare(a,b)==0` is not required to match `a.equals(b)` in every situation**; however, if used as keys in `TreeMap` or `TreeSet`, inconsistency with `equals` can cause behavior that differs from `Map`/`Set` expectations.

### 14.1. Never turn epsilon into an arbitrary comparator

Do not write:

```java
// WRONG idea:
int compare(double a, double b) {
    return Math.abs(a - b) <= 0.1 ? 0 : Double.compare(a, b);
}
```

This is an illustrative method snippet **not to use**. The three numbers `0.00`, `0.09`, and `0.18` satisfy "0.00 is close to 0.09" and "0.09 is close to 0.18," yet "0.00 is not close to 0.18." Returning `0` is non-transitive and violates the `Comparator`/`Comparable` contract.

Separate **approximate numerical queries** from **equality and ordering**:

```java
static boolean near(double a, double b, double tolerance) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(tolerance) || tolerance < 0) {
        return false; // a specific domain data policy
    }
    return Math.abs(a - b) <= tolerance;
}
```

This is a **dedicated query** method for finite numbers; do not use it as `equals`/`compareTo`. Across very wide value scales, consider relative tolerance, subtraction overflow, and business requirements. Tolerance must be determined per unit of measurement, not by picking one epsilon for every field.

## 15. `BigDecimal`'s `equals` and `compareTo` Differ

`BigDecimal` is a subclass of `Number` represented by an **unscaled value** and a **scale**. Examples:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));      // false
System.out.println(a.compareTo(b));   // 0
```

Requires `import java.math.BigDecimal;`.

- `BigDecimal.equals` checks **value along with scale**: `2.0` has scale 1, `2.00` has scale 2.
- `BigDecimal.compareTo` checks **numeric value**: both equal 2, so it returns 0.
- The `hashCode` of the two `BigDecimal`s can differ, consistent with that class's `equals`.
- `HashSet<BigDecimal>` can hold both `2.0` and `2.00`; `TreeSet<BigDecimal>` uses natural ordering via `compareTo` and treats them as the same position in the tree.

This is the classic example of a natural ordering **inconsistent with equals**; do not generalize this conclusion to all wrappers. When business logic wants "same decimal number ignoring scale," define a transparent canonicalization policy, considering how `stripTrailingZeros` alters scale and the zero case. Do not use default `equals` and assume it behaves like `compareTo`.

### 15.1. Short program demonstrating collection differences

Save as **`DecimalCollectionIdentity.java`**:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.TreeSet;

public class DecimalCollectionIdentity {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println(a.equals(b));
        System.out.println(a.compareTo(b));

        HashSet<BigDecimal> hashed = new HashSet<>();
        hashed.add(a);
        hashed.add(b);
        System.out.println(hashed.size());

        TreeSet<BigDecimal> ordered = new TreeSet<>();
        ordered.add(a);
        ordered.add(b);
        System.out.println(ordered.size());
    }
}
```

Run:

```bash
javac --release 17 DecimalCollectionIdentity.java
java DecimalCollectionIdentity
```

**Stdout:**

```text
false
0
2
1
```

`HashSet` uses `equals`/`hashCode`, and `TreeSet` uses `compareTo`. If scale matters to business logic, `BigDecimal`'s natural ordering may **not** be suitable as a deduplication policy; the choice must reflect the actual data.

## 16. Edge Cases to Check When Wrappers Are Used as Keys

### 16.1. Null

`Integer.compare(a,b)` takes primitives, so if `a` or `b` is a null wrapper and gets unboxed, it throws `NullPointerException`. `Integer.compareTo(null)` also does not define null as a valid `Integer`.

If a collection allows nulls in data and needs sorting, wrap an appropriate comparator with `Comparator.nullsFirst` or `Comparator.nullsLast`, e.g.:

```java
Comparator<Integer> byValueWithNull =
        Comparator.nullsLast(Integer::compare);
```

This snippet requires `import java.util.Comparator;`.

### 16.2. Signed zero and NaN

If `+0.0` and `-0.0` must share the same business identity, default `Double.equals`/`Double.compare` **do not** merge them. You can normalize at the boundary:

```java
static double normalizeZero(double value) {
    return value == 0.0 ? 0.0 : value;
}
```

However, the sign of zero can affect division and `Math.atan2`; normalize only when appropriate.

For NaN, `Double.compare` places NaN above other numeric values and `Double.equals` canonicalizes NaN bit patterns. If NaN represents invalid data, a better choice may be **rejecting it from keys** rather than letting it sort after infinity by default.

### 16.3. Unsigned comparison

`Integer.compare(-1,1)` and `Integer.compareUnsigned(-1,1)` yield opposite orders. A data field holding 32 bits interpreted as unsigned by a protocol must use `compareUnsigned` when unsigned order is required; when using `equals`/`hashCode` on `Integer` bit patterns, equality can remain valid because the bits do not change.

### 16.4. Immutable keys

Standard wrappers are immutable. However, if a custom key object wrapping a wrapper contains mutable fields determining `equals`/`hashCode`, mutating those fields after inserting into `HashMap`/`HashSet` can cause lookups to target the wrong bucket. Keep keys immutable or manage updates by removing and reinserting under an explicit policy.

## 17. Checklist for Choosing the Right API by Scenario

- When data are two primitive `int`s: use `==` for equality, `Integer.compare` for ordering.
- When data are two non-null `Integer`s: use `equals` for equality, `compareTo`/`Integer.compare` for ordering.
- When wrappers may be null: use `Objects.equals` or a null-aware comparator.
- When mixing `Integer` and `Long`: do not assume `equals` provides cross-type numeric equality; choose an appropriate range/conversion method.
- When handling `Double`: remember the differences among `==`, `equals`, and `Double.compare` for `NaN`/signed zero.
- When comparing unsigned binary data: use `compareUnsigned` as needed.
- When sorting: do not return integer differences or floating-point differences cast to `int`.
- When using as `HashMap` keys: respect `equals`/`hashCode`; never use `hashCode` alone to conclude equality.
- When using as `TreeMap` keys: provide a valid, transitive, consistent comparator; know that `compare==0` determines key duplication.
- When using `BigDecimal`: decide whether scale is part of identity.
- When checking approximate equality: use a dedicated function with explicit tolerance/scope; never put it in `equals` or a comparator.

## 18. Exercises with Solutions

### Exercise 1 — `Integer` and `Long` with the same number

`Integer a = 9; Long b = 9L;`. What is `a.equals(b)`, and why?

**Answer:** `false`. `Integer.equals` requires the right-hand object to be an `Integer`; `Long` is a different class. `a.longValue() == b.longValue()` is `true` for this data.

### Exercise 2 — Static and instance compare

Write two ways to compare the order of 9 and 12 using `Integer`. What do they return?

**Answer:** `Integer.compare(9,12)` and `Integer.valueOf(9).compareTo(Integer.valueOf(12))` both return a negative number (here `-1`).

### Exercise 3 — Hash collision

If `x.hashCode() == y.hashCode()`, is that enough to conclude `x.equals(y)` is true?

**Answer:** No. Two unequal objects can have colliding hashes; only the implication `equals true ⇒ hash equal` is required.

### Exercise 4 — Byte.compare

Why can `Byte.compare((byte)-1,(byte)1)` return `-2` and still be correct?

**Answer:** The comparison API only requires a negative/0/positive sign to indicate ordering; it does not have to return strictly `-1,0,1`. `-2 < 0` reflects that -1 is less than 1.

### Exercise 5 — Signed vs. unsigned

Determine the signs of `Integer.compare(-1,1)` and `Integer.compareUnsigned(-1,1)`.

**Answer:** Signed comparison returns negative; unsigned comparison returns positive. The same all-ones bit pattern of -1 is read as the largest 32-bit unsigned integer.

### Exercise 6 — Cache/identity

Why can `Integer.valueOf(42) == Integer.valueOf(42)` be true, yet `==` should not be used to compare the values of two arbitrary `Integer`s?

**Answer:** `Integer.valueOf` caches small values within a guaranteed range; `==` between two `Integer`s compares reference identity. For values outside the standard cache range there is no identity guarantee, while `equals` still compares values.

### Exercise 7 — Signed zero

What do `Double.compare(-0.0,+0.0)` and `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` return?

**Answer:** `compare` returns negative; `equals` returns `false`. Meanwhile, primitive `-0.0 == +0.0` is `true`.

### Exercise 8 — NaN

What do `Double.NaN == Double.NaN` and `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` return?

**Answer:** `false` and `true`. The wrapper canonicalizes NaN for equality.

### Exercise 9 — HashSet/TreeSet with Double

Add `+0.0`, `-0.0`, and `Double.NaN` twice into both a `HashSet<Double>` and a `TreeSet<Double>`; how many elements does each set contain?

**Answer:** `3`. Both distinguish the two zeros, while both `NaN`s are treated as equivalent under `Double.equals` and natural ordering.

### Exercise 10 — BigDecimal and scale

What do `new BigDecimal("2.0").compareTo(new BigDecimal("2.00"))` and `equals` return?

**Answer:** `0` and `false`. `compareTo` considers numeric value; `equals` also considers scale.

### Exercise 11 — Comparator via subtraction

Why is `(a,b) -> a-b` not a safe choice for `Comparator<Integer>`?

**Answer:** `int` subtraction can overflow, causing the sign of the result to no longer reflect ordering. Use `Integer.compare(a,b)`.

### Exercise 12 — Mixed Numbers

Why is using `a.doubleValue() == b.doubleValue()` on arbitrary `Number`s dangerous?

**Answer:** Precision is lost for `long`s exceeding `double`'s exact integer range and for high-precision `BigDecimal`s, and it conflates NaN/signed zero if treated as a general equality. Data ranges/contracts must be defined before converting.

### Exercise 13 — Null

`Integer a = null;`. What does `Objects.equals(a,null)` return? What about `a.compareTo(1)`?

**Answer:** `true` for `Objects.equals` since both are null; calling a method on a null receiver causes `NullPointerException`.

### Exercise 14 — Hash and tree with BigDecimal

Add `2.0` and `2.00` as `BigDecimal`s into a `HashSet` and a `TreeSet`. What are the resulting sizes?

**Answer:** `HashSet` has 2, `TreeSet` has 1 according to `BigDecimal`'s default equality/natural ordering.

## 19. Java SE 17 Reference Documentation

- [Java SE 17 Number API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html): abstract class for numeric wrappers.
- [Integer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `compare`, `compareUnsigned`, `compareTo`, `equals`, `hashCode`, `valueOf`.
- [Long API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): signed/unsigned comparisons and hashing.
- [Byte API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html) and [Short API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Short.html): comparison and promotion.
- [Float API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html) and [Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): signed zero/NaN and bit-based equality.
- [Object.equals/hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): equality and hashing contracts.
- [Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html) and [Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): natural ordering and comparator contract.
- [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html): duplicate-element criteria.
- [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `compareTo` vs. `equals` when scale differs.

**Conclusion:** use **`compare`/`compareTo`** to express *ordering*, **`equals`** to express *equality under the class contract*, and **`hashCode`** to support *equality-based lookup*. With numeric wrappers, always consider **type**, **null**, **boxing identity**, **signed/unsigned**, **NaN**, **±0.0**, and **scale** instead of assuming "same mathematical quantity" means the same Java key.