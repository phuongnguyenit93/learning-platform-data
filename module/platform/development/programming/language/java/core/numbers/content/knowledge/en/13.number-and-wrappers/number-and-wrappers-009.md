# Different Wrapper Types Do Not Automatically Equal Each Other via equals in Java

In Java, numeric wrappers such as `Byte`, `Short`, `Integer`, `Long`, `Float`, and `Double` all extend `Number`, yet **each wrapper's `equals(Object)` requires the other object to belong to that exact wrapper class**. Therefore:

~~~java
Integer a = Integer.valueOf(42);
Long b = Long.valueOf(42L);

System.out.println(a.equals(b)); // false
~~~

The two objects represent the same mathematical value 42, yet **are not equal under the `Integer.equals` contract**. This is intentional behavior, not Java forgetting to auto-widen. This lesson focuses on the boundary between **object-type equality**, **numeric equality**, **primitive comparison**, and consequences in collections.

## 1. Why Is `Integer.equals(Long)` False?

`Integer` stores an `int` value; `Long` stores a `long` value. The `Integer.equals(Object obj)` method returns `true` only when `obj` is an `Integer` with the same `int` value. Likewise, `Long.equals` only accepts a `Long` with the same `long` value.

~~~java
Integer i = Integer.valueOf(42);
Long l = Long.valueOf(42L);
Double d = Double.valueOf(42.0);

boolean sameInteger = i.equals(Integer.valueOf(42)); // true
boolean integerVsLong = i.equals(l);                  // false
boolean longVsDouble = l.equals(d);                   // false
~~~

| Call | Result | Why? |
| --- | --- | --- |
| `Integer.valueOf(42).equals(Integer.valueOf(42))` | `true` | Same `Integer` type and same `int` |
| `Integer.valueOf(42).equals(Long.valueOf(42L))` | `false` | `Long` is not an `Integer` |
| `Long.valueOf(42L).equals(Double.valueOf(42.0))` | `false` | `Double` is not a `Long` |
| `Double.valueOf(42.0).equals(Double.valueOf(42.0))` | `true` | Same `Double` type and same value |
| `Float.valueOf(42.0f).equals(Double.valueOf(42.0))` | `false` | Different wrapper types |

**The contract of `equals(Object)` differs from primitive comparisons with automatic widening.** The parameter of `equals` is `Object`, and Java does not auto-unbox/widen two objects to compare numeric values. In wrapper implementations, the logic checks type before checking value.

Do not reason "both are `Number`" to predict `equals`: the `Number` superclass **does not define a universal numeric equality mechanism** for all subclasses. The actual runtime object determines which `equals` method executes via dynamic dispatch.

## 2. `==` Between Primitives vs. `equals` Between Different Wrappers

### Two primitives undergo numeric promotion

~~~java
int x = 42;
long y = 42L;

System.out.println(x == y); // true
~~~

With `int` and `long`, the `==` comparison applies binary numeric promotion: `int` is widened to `long`, and then the two primitives are compared. Hence the result is `true`.

### A wrapper compared to a primitive can be unboxed

~~~java
Integer wrapper = Integer.valueOf(42);
long primitive = 42L;

System.out.println(wrapper == primitive); // true
~~~

Because one side is a numeric primitive, Java unboxes `wrapper` to `int`, then widens `int → long` to compare. If `wrapper` is `null`, unboxing can throw `NullPointerException`.

### Two wrappers of different types do not auto-unbox to use `==`

The following snippet **intentionally does not compile**:

~~~java
Integer i = Integer.valueOf(42);
Long l = Long.valueOf(42L);

// boolean eq = i == l; // ERROR: incomparable types: Integer and Long
~~~

Both `i` and `l` have reference types; in this case, `==` does not trigger the same unboxing + widening chain as when one operand is primitive. Two independent wrapper classes `Integer` and `Long` are not reference types that can be compared to each other with `==`.

If both are declared as `Number` or `Object`, `==` between two reference variables compiles, yet the result is **reference identity**, not numeric value comparison.

~~~java
Number a = Integer.valueOf(42);
Number b = Long.valueOf(42L);
boolean sameReference = a == b; // false
boolean sameByEquals = a.equals(b); // false
~~~

Even with **two `Integer`s**, `==` between two references only checks whether they are the same object. Do not rely on wrapper caching (`Integer.valueOf` caches a value range) to infer that `==` compares numbers. Use `equals` when you want wrapper-type equality, or unbox when you genuinely want primitive comparison and have handled `null`.

## 3. `Number` and Polymorphism Do Not Provide Cross-Type Equality

A variable declared as `Number` still references a concrete object such as `Integer` or `Long`:

~~~java
Number left = Integer.valueOf(42);
Number right = Long.valueOf(42L);

System.out.println(left.equals(right)); // false
~~~

Calling `left.equals(right)` runs `Integer.equals`'s implementation because the left-hand object is an `Integer`. It checks whether the right-hand object is an `Integer`; the result is `false`. Java does not see that both objects extend `Number` and call `longValue()` by default to compare them.

Key point: **the static type `Number` grants access to value-conversion methods** such as `intValue()`, `longValue()`, and `doubleValue()`, yet does not establish a unified notion of "the same number" across all wrappers or all `Number` subclasses.

Beyond wrappers, classes like `BigInteger` and `BigDecimal` also extend `Number` and have their own `equals` contracts. When accepting a general `Number` parameter, a method must explicitly decide what it wants to compare: same object, same type and value, or same numeric value after a controlled conversion.

## 4. `Objects.equals` Is Null-Safe, Not a Numeric Type Converter

`Objects.equals(a, b)` is a convenient tool for comparing potentially null objects. It returns `true` if both references match (including both null); if `a` is non-null, it calls `a.equals(b)`. **It does not normalize wrappers**, and does not convert `Integer` to `Long`.

~~~java
Integer i = Integer.valueOf(42);
Long l = Long.valueOf(42L);

System.out.println(java.util.Objects.equals(i, l)); // false
System.out.println(java.util.Objects.equals(null, null)); // true
~~~

Use `Objects.equals` when the goal is **object equality** and avoiding calling `null.equals(...)`. If the goal is **numeric equivalence across multiple different types**, you need a dedicated conversion and comparison policy. Changing `i.equals(l)` to `Objects.equals(i, l)` does not resolve type differences.

## 5. Consequences in `HashSet`, `HashMap`, and `Number` Keys

Hash-based collections use `equals` and `hashCode`. Because `Integer(42)`, `Long(42)`, and `Double(42.0)` are unequal under `equals`, they are **three distinct elements** in a `Set<Number>`:

~~~java
java.util.Set<Number> values = new java.util.HashSet<>();
values.add(Integer.valueOf(42));
values.add(Long.valueOf(42L));
values.add(Double.valueOf(42.0));

System.out.println(values.size()); // 3
~~~

A `Map<Number, String>` can likewise hold `Integer.valueOf(42)` and `Long.valueOf(42L)` as separate keys. This affects caches, statistics, deduplication, ID mappings, and value retrieval: `map.get(42L)` is not equivalent to `map.get(42)` when the key was stored as a different wrapper type.

**Design condition:** If "ID 42" has only one valid numeric type, normalize **the key type at ingestion**, e.g., use `Long` for all ID keys within `long` range, or `BigInteger` if very large integers are needed. Avoid creating `Map<Number, ...>` and hoping differently typed wrappers merge into the same key.

Do not write a custom business-object `equals` that "sometimes compares `Integer` and `Long` via `doubleValue`" while keeping an incompatible `hashCode`: two objects considered equal must have matching hash codes. The `equals`/`hashCode` consistency rule must be upheld.

## 6. How Do You Compare *Numeric Value* Between Two Wrappers?

First, clearly define **the data domain**. There is no single universal cast that is right for every `Number` value.

### Case A — guaranteed both are primitive integers fitting in `long`

~~~java
Integer i = Integer.valueOf(42);
Long l = Long.valueOf(42L);

boolean sameNumericValue = i.longValue() == l.longValue(); // true
~~~

This approach is valid because `Integer` and `Long` both represent exact integers within `long` range. It also works for `Byte`/`Short` once input types are controlled. However, **do not apply it indiscriminately to a `BigInteger` exceeding `long` range or a `Double` with a fractional part**, as those `longValue()` calls can lose information.

If you need to normalize multiple integer wrappers, you can convert to `BigInteger`:

~~~java
java.math.BigInteger fromInt =
        java.math.BigInteger.valueOf(Integer.valueOf(42).longValue());
java.math.BigInteger fromLong =
        java.math.BigInteger.valueOf(Long.valueOf(42L).longValue());

boolean equalIntegers = fromInt.equals(fromLong); // true
~~~

For data already in `BigInteger`, keep that object as-is; do not convert it down to `long` only to rebuild a `BigInteger`.

### Case B — decimal requirements with explicit precision and policy

If a system receives decimal values such as `"42.0"` and `"42.00"`, `BigDecimal` provides both object equality and numeric comparison:

~~~java
java.math.BigDecimal x = new java.math.BigDecimal("42.0");
java.math.BigDecimal y = new java.math.BigDecimal("42.00");

boolean objectEqual = x.equals(y);   // false: different scale
boolean numericEqual = x.compareTo(y) == 0; // true
~~~

`BigDecimal.equals` requires **the same value and same scale**, whereas `compareTo` compares the decimal numeric value and ignores scale differences. If you need a decimal key treating `42.0` and `42.00` as identical, define a scale normalization strategy or key type upfront, and understand the impact on `HashMap`/`TreeMap`. `BigDecimal` is a `Number` subclass, not a primitive wrapper.

### Case C — floating-point and approximate values

`doubleValue()` converts many `Number`s to `double`, yet **does not preserve every numeric value**. For example, two adjacent `long` integers above `2^53` can convert to the same `double`:

~~~java
long a = 9_007_199_254_740_993L; // 2^53 + 1
long b = 9_007_199_254_740_992L; // 2^53

boolean equalAsLong = a == b; // false
boolean equalAsDouble = (double) a == (double) b; // true
~~~

Converting both to `double` and using `==` can falsely report equality. Likewise, huge numbers can become infinity, tiny numbers can be rounded; NaN and ±0 follow special rules. If a mixed integer/floating problem needs **exact** comparison, define how to handle range, sign, NaN, infinity, overflow, and conversion methods before building a comparator.

If business logic only needs "approximately equal" within a tolerance, write a separate check for finite data with a tolerance suited to the scale. **Do not use epsilon-based approximate comparison as `equals`/a comparator for collections** when it fails to guarantee transitivity and consistency.

## 7. Floating-Point Wrappers Also Have Special Rules for NaN and Signed Zero

`Float.equals` and `Double.equals` also require **the same wrapper type**. Additionally, they use canonicalized NaN bit comparison rules:

- Two `Double` objects holding NaN are treated as equal by `Double.equals`, even though primitive `Double.NaN == Double.NaN` is `false`.
- `Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` is `false`, even though primitive `+0.0 == -0.0` is `true`.
- `Float.valueOf(Float.NaN).equals(Double.valueOf(Double.NaN))` is `false` due to **different wrapper types**, even though both represent NaN.

~~~java
Double d1 = Double.valueOf(Double.NaN);
Double d2 = Double.valueOf(Double.NaN);
Float f = Float.valueOf(Float.NaN);

boolean sameDoubleNaNs = d1.equals(d2); // true
boolean floatVsDoubleNaN = f.equals(d1); // false
boolean signedZeroDifferent =
        Double.valueOf(0.0).equals(Double.valueOf(-0.0)); // false
~~~

In algorithms sorting `Float`/`Double`, `Float.compare` and `Double.compare` define an ordering consistent with the wrappers: NaN compares equal to NaN in `compare`, and `-0.0` precedes `+0.0`. That still does not create shared equality between `Float` and `Double`.

## 8. Complete Java 17+ Example

Save the file named `WrapperEquality.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class WrapperEquality {
    public static void main(String[] args) {
        Integer integer = Integer.valueOf(42);
        Long longValue = Long.valueOf(42L);
        Double doubleValue = Double.valueOf(42.0);
        Number left = integer;
        Number right = longValue;

        System.out.println("Integer.equals(Long) = "
                + integer.equals(longValue));
        System.out.println("Long.equals(Double) = "
                + longValue.equals(doubleValue));
        System.out.println("Integer.equals(Integer) = "
                + integer.equals(Integer.valueOf(42)));
        System.out.println("Objects.equals(Integer, Long) = "
                + Objects.equals(integer, longValue));
        System.out.println("Number.equals(Long) = "
                + left.equals(longValue));
        System.out.println("int == long = " + (42 == 42L));
        System.out.println("Integer == long = " + (integer == 42L));
        System.out.println("Number reference == = " + (left == right));

        Set<Number> numbers = new HashSet<>();
        numbers.add(integer);
        numbers.add(longValue);
        numbers.add(doubleValue);
        System.out.println("HashSet size = " + numbers.size());
        System.out.println("contains Long(42) = "
                + numbers.contains(Long.valueOf(42L)));

        long large = 9_007_199_254_740_993L;
        System.out.println("large as double = " + (double) large);
        System.out.println("large double == previous double = "
                + ((double) large == (double) (large - 1)));
        System.out.println("BigInteger exact compare = "
                + BigInteger.valueOf(large)
                .compareTo(BigInteger.valueOf(large - 1)));

        BigDecimal decimalA = new BigDecimal("42.0");
        BigDecimal decimalB = new BigDecimal("42.00");
        System.out.println("BigDecimal equals = "
                + decimalA.equals(decimalB));
        System.out.println("BigDecimal compareTo = "
                + decimalA.compareTo(decimalB));
        System.out.println("Double NaN equals NaN = "
                + Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN)));
        System.out.println("Float NaN equals Double NaN = "
                + Float.valueOf(Float.NaN)
                .equals(Double.valueOf(Double.NaN)));
        System.out.println("Double +0 equals -0 = "
                + Double.valueOf(+0.0).equals(Double.valueOf(-0.0)));
        System.out.println("Objects.equals(null, null) = "
                + Objects.equals(null, null));
    }
}
~~~

Compile/run using Java 17 or newer:

~~~bash
javac WrapperEquality.java
java WrapperEquality
~~~

Stdout:

~~~text
Integer.equals(Long) = false
Long.equals(Double) = false
Integer.equals(Integer) = true
Objects.equals(Integer, Long) = false
Number.equals(Long) = false
int == long = true
Integer == long = true
Number reference == = false
HashSet size = 3
contains Long(42) = true
large as double = 9.007199254740992E15
large double == previous double = true
BigInteger exact compare = 1
BigDecimal equals = false
BigDecimal compareTo = 0
Double NaN equals NaN = true
Float NaN equals Double NaN = false
Double +0 equals -0 = false
Objects.equals(null, null) = true
~~~

The nineteen lines of output illustrate the difference between wrapper `equals` and primitive equality, collection consequences, `doubleValue` precision loss, and special rules for NaN/signed zero.

## 9. Common Mistakes When Handling Different Wrapper Types

1. **Assuming two wrappers with the same mathematical value are always `equals`.** `Integer.valueOf(42).equals(Long.valueOf(42L))` is `false` because the types differ.
2. **Using `Objects.equals` as numeric normalization.** It only wraps object equality and handles `null` safely.
3. **Seeing `Number` and using `Number.equals` as a universal arithmetic contract.** `Number` does not implement cross-subclass equality.
4. **Using `==` between two wrappers to measure value.** If both references have the same type, it checks object identity; if they are different wrapper types like `Integer` and `Long`, the expression may not even compile. With one primitive operand, unboxing can occur and throw `NullPointerException` when the wrapper is null.
5. **Coercing every `Number` via `doubleValue` to compare.** For integers larger than `2^53`, two distinct numbers can collapse into the same `double`, producing wrong conclusions.
6. **Using mixed numeric data as keys in `Map<Number, ...>` and expecting lookups with another wrapper type to hit the same entry.** Normalize key types per the data specification.
7. **Confusing `BigDecimal.equals` with `BigDecimal.compareTo`.** `42.0` and `42.00` have equal decimal numeric value yet different scales; `equals` returns `false` and `compareTo` returns 0.
8. **Assuming `Float`'s NaN and `Double`'s NaN are equal via `equals`.** They are different wrapper classes so it is `false`; even within each wrapper type, NaN/±0 rules differ from primitives.
9. **Overriding `equals` without updating `hashCode`.** This breaks hash-key consistency and can cause hard-to-reproduce bugs.

## 10. Process for Choosing the Comparison Operation

| Goal | Suitable approach | Note |
| --- | --- | --- |
| Same wrapper type and same wrapper value | `Objects.equals(a, b)` or `a.equals(b)` when `a` is non-null | Different wrapper types remain `false` |
| Two primitives needing numeric equality | `==` after numeric promotion | NaN and signed zero have special rules |
| Two small integer wrappers known within `long` range | Compare `longValue()` after verifying types and range | Do not use for huge `BigInteger` or decimals |
| Exact large integers | `BigInteger.equals`/`compareTo` | Preserves original data accurately |
| Exact decimal numbers | `BigDecimal.compareTo == 0` if ignoring scale | Define scale and key contracts |
| Sorting floating-point numbers of the same type | `Double.compare` / `Float.compare` | NaN and ±0 are ordered per Java convention |
| Map/set needing consistent IDs | Normalize key type at the data boundary | Ensure `equals` and `hashCode` share the same policy |

**Self-practice questions:**

- What does `Integer.valueOf(8).equals(Long.valueOf(8L))` return? What about `8 == 8L`?
- If `Number n = Integer.valueOf(8)`, is `n.equals(Long.valueOf(8L))` any different?
- Why can a `HashSet<Number>` contain both `Integer(8)` and `Long(8)`?
- What is wrong with comparing two `long`s around `2^53` by casting both to `double`?
- Do `new BigDecimal("8.0").equals(new BigDecimal("8.00"))` and `compareTo` give the same result?

**Answers:** (1) `false` and `true`. (2) Still `false` because `Integer.equals`'s implementation runs. (3) They are two unequal elements under wrapper `equals`. (4) Casting can drop precision bits and merge two distinct numbers. (5) `equals` is `false`, while `compareTo` equals 0.

## References

- [Java SE 21 — Integer.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#equals(java.lang.Object)).
- [Java SE 21 — Long.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html#equals(java.lang.Object)).
- [Java SE 21 — Number](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Number.html).
- [Java SE 21 — Objects.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).
- [Java Language Specification `15.21 — Equality Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.21).