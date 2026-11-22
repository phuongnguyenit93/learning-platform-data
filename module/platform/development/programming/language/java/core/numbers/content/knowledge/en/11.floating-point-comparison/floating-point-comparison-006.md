# `equals()` on `Float` and `Double` with `NaN` and Signed Zero in Java

## 1. Why Does Comparing Floating-Point Numbers Give Different Results?

In Java, `float` and `double` are **primitive types**, whereas `Float` and `Double` are the corresponding **wrapper classes**. The `==` operator on primitive values follows IEEE 754 floating-point comparison rules; the `Float.equals(Object)` and `Double.equals(Object)` methods have a separate contract suited to `Object.equals` and Java's collections.

The two most confusing cases are **NaN** (*Not a Number*) and **signed zero** (`+0.0`, `-0.0`):

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(Double.valueOf(positiveZero)
        .equals(Double.valueOf(negativeZero)));    // false

System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.valueOf(Double.NaN)
        .equals(Double.valueOf(Double.NaN))); // true
```

**This is neither a contradiction nor a Java bug**. The two mechanisms define "equality" for different purposes:

- **Arithmetic comparison with `==`:** `NaN` is not equal to any value, including itself; `+0.0` and `-0.0` are equal arithmetically.
- **Wrapper `equals` comparison:** all `NaN` values of the same wrapper type are treated as equal; `+0.0` and `-0.0` are **not** equal.

These rules apply symmetrically to `Float`/`float` and `Double`/`double` at each type's respective precision width.

## 2. Understanding `NaN` and the Two Bit Patterns of Zero

### What Is `NaN`?

`NaN` represents a result that is not a valid real number in floating-point arithmetic, for example:

```java
double invalid = 0.0 / 0.0;
float invalidFloat = 0.0f / 0.0f;

System.out.println(Double.isNaN(invalid)); // true
System.out.println(Float.isNaN(invalidFloat)); // true
```

Under primitive floating-point comparison rules, if one operand is `NaN`:

- `x == y` evaluates to `false`, including `NaN == NaN`.
- `x != y` evaluates to `true`.
- `x < y`, `x <= y`, `x > y`, and `x >= y` all evaluate to `false`.

Do not check for `NaN` using `value == Double.NaN` or `value == Float.NaN`; that comparison is **always false**. Use `Double.isNaN(value)` or `Float.isNaN(value)`.

`NaN` has many possible IEEE 754 bit patterns (*NaN payloads*). They do not correspond to normal real numeric values. Java provides bit-conversion functions that distinguish between a **canonical view** and a **raw view**; that is the basis on which wrapper `equals` considers all `NaN`s of the same type equal.

### What Is Signed Zero?

IEEE 754 has **two representations of zero**:

- `+0.0`: sign bit is `0`.
- `-0.0`: sign bit is `1`.

Both have significand and exponent equal to `0`, differing only in the sign bit. Java treats them as equal under arithmetic `==`. However, the sign of zero can affect other operations:

```java
System.out.println(+0.0 == -0.0); // true
System.out.println(1.0 / +0.0);    // Infinity
System.out.println(1.0 / -0.0);    // -Infinity
```

Thus, the two zero patterns have the same value under `==`, yet **not every operation treats them identically**. Wrapper `equals` intentionally distinguishes these two zero bit patterns.

## 3. Comparison Table: Primitive `==` vs. Wrapper `equals`

| Scenario (same `double`/`Double` type) | Primitive `==` comparison | `Double.equals` |
| --- | --- | --- |
| `1.0` vs. `1.0` | `true` | `true` |
| `1.0` vs. `2.0` | `false` | `false` |
| `+0.0` vs. `-0.0` | `true` | `false` |
| `Double.NaN` vs. `Double.NaN` | `false` | `true` |
| Two `NaN`s with different payloads | `false` | `true` |
| `Double.POSITIVE_INFINITY` vs. itself | `true` | `true` |
| `Double.NEGATIVE_INFINITY` vs. positive infinity | `false` | `false` |

For `Float`, replace `Double` with `Float` in the corresponding cases. Note that `Float.valueOf(1.0f).equals(Double.valueOf(1.0))` is still **`false`**, even though they represent the same mathematical value, because wrapper `equals` requires **the exact same wrapper class**.

The special behaviors of `NaN` and signed zero are also why you should not write a general floating-point comparison function by replacing `a == b` with `Double.valueOf(a).equals(Double.valueOf(b))` without considering the business contract.

## 4. What Do `Double.equals` and `Float.equals` Actually Compare?

According to JDK documentation, `Double.equals(Object obj)` returns `true` when the other object is also a `Double` and the results of **`Double.doubleToLongBits`** on both values are equal. Similarly, `Float.equals` uses **`Float.floatToIntBits`**.

Conceptually, you can think of it like this (**illustrative mechanism** code, not a copy of the full JDK implementation):

```java
static boolean sameDoubleWrapperValue(double a, double b) {
    return Double.doubleToLongBits(a) == Double.doubleToLongBits(b);
}

static boolean sameFloatWrapperValue(float a, float b) {
    return Float.floatToIntBits(a) == Float.floatToIntBits(b);
}
```

Two properties of these bit-conversion functions explain the edge cases:

1. **`NaN` is *canonicalized*:** `Double.doubleToLongBits` returns the same **canonical NaN bit pattern** for every `double` value that is `NaN`. `Float.floatToIntBits` does the same in 32 bits. Therefore, `NaN`s of the same wrapper class have `equals == true`.
2. **Zero's sign bit is preserved:** `+0.0` and `-0.0` convert to two different bit sequences; hence wrapper `equals` returns `false`.

Examples:

```java
System.out.println(Double.doubleToLongBits(+0.0)
        == Double.doubleToLongBits(-0.0)); // false

System.out.println(Float.floatToIntBits(+0.0f)
        == Float.floatToIntBits(-0.0f)); // false

System.out.println(Double.doubleToLongBits(Double.NaN)
        == Double.doubleToLongBits(0.0 / 0.0)); // true
```

**Do not confuse** `doubleToLongBits` with `doubleToRawLongBits`, or `floatToIntBits` with `floatToRawIntBits`:

- `doubleToLongBits` / `floatToIntBits` **canonicalize NaN**, matching `equals`.
- `doubleToRawLongBits` / `floatToRawIntBits` **do not intentionally canonicalize NaN** when returning bits, so different NaN payloads can be observed depending on which bits were preserved by prior operations.

If the goal is to inspect or record exact binary payloads according to a protocol, deliberately choose raw-bit tools. If the goal is using `Float`/`Double` keys in collections, respect the canonical semantics defined by the wrappers.

## 5. How Do `Double.compare`, `Float.compare`, and `compareTo` Relate to `equals`?

Java needs a **total order** to sort and store floating-point numbers in ordered structures. For wrapper types, `Double.compare(double x, double y)` and `Float.compare(float x, float y)` define two extra special rules:

- `-0.0` is ordered **less than** `+0.0`.
- `NaN` is considered **greater than all floating-point numbers**, including `+Infinity`; `NaN` values are considered equal when compared via `compare`.

`Double.compareTo(Double)` and `Float.compareTo(Float)` follow the rules of the same wrapper class. When comparing two values of the same typed wrapper, `compare(x,y) == 0` is consistent with the corresponding wrapper `equals`.

```java
System.out.println(Double.compare(-0.0, +0.0) < 0); // true
System.out.println(Double.compare(Double.NaN,
        Double.POSITIVE_INFINITY) > 0); // true
System.out.println(Double.compare(Double.NaN, 0.0 / 0.0) == 0); // true
```

Meanwhile, primitive ordering operators:

```java
System.out.println(-0.0 < +0.0); // false
System.out.println(Double.NaN > Double.POSITIVE_INFINITY); // false
```

Do not use `<`/`>` on primitives to simulate a total-order comparator. For sorting `List<Double>`, use `Double::compare` or `Double::compareTo` when the desired policy is **NaN last, -0.0 before +0.0**.

Distinguish **total order for collections** from **IEEE 754 arithmetic ordering when encountering NaN**. The differing rules are intentional and documented in the JDK.

## 6. Why Do Collections Need This `equals` Contract?

`HashSet`, `HashMap`, and key-based collections use an object's `equals` and `hashCode` contract—not the arithmetic `==` operator—to determine duplicate keys.

For `Double`:

- Two objects holding `NaN` are considered **equal by `equals`**, so they represent the **same key**.
- `Double.valueOf(+0.0)` and `Double.valueOf(-0.0)` are **two distinct keys**.
- The `hashCode` rule is designed to be consistent with `equals`: two equal values must have the same hash code. NaNs of the same wrapper class are normalized accordingly; two zeros with opposite signs retain their distinction.

Example:

```java
import java.util.HashSet;
import java.util.Set;

Set<Double> values = new HashSet<>();
values.add(+0.0);
values.add(-0.0);
values.add(Double.NaN);
values.add(0.0 / 0.0);

System.out.println(values.size()); // 3
```

The set holds three values under `Double.equals`: positive zero, negative zero, and one NaN key. Do not rely on `HashSet` iteration order in illustrations because `HashSet` **does not guarantee order**.

And for `HashMap`:

```java
import java.util.HashMap;
import java.util.Map;

Map<Double, String> descriptions = new HashMap<>();
descriptions.put(+0.0, "positive zero");
descriptions.put(-0.0, "negative zero");
descriptions.put(Double.NaN, "first");
descriptions.put(0.0 / 0.0, "second");

System.out.println(descriptions.size()); // 3
System.out.println(descriptions.get(+0.0)); // positive zero
System.out.println(descriptions.get(-0.0)); // negative zero
System.out.println(descriptions.get(Double.NaN)); // second
```

The later `NaN` write **replaces the value** for the same NaN key; the two zeros remain two independent keys.

### What About `TreeSet` and `TreeMap`?

Ordered structures like `TreeSet<Double>` typically rely on `Double.compareTo`. That comparator is consistent with `Double.equals`, so there are still three distinct values in the positive zero, negative zero, and NaN example; when sorted in natural order, `-0.0` comes before `+0.0`, and `NaN` comes after positive infinity.

**Important:** If you supply your own custom comparator to `TreeSet` or `TreeMap`, that comparator decides whether two keys are considered order-equivalent. A comparator inconsistent with `equals` can make "duplicate element" behavior differ from `HashSet`. Design comparison criteria consistently with your business purpose.

## 7. Do Not Confuse `equals`, Object `==`, and Autounboxing

### `equals` Compares Values Under the Wrapper Contract

```java
Double a = Double.valueOf(1.0);
Double b = Double.valueOf(1.0);

System.out.println(a.equals(b)); // true
```

### `==` Between Two Wrapper References Can Be Object Identity Comparison

When **both operands have reference types**, `==` checks whether they point to **the same object**, without calling `Double.equals`.

```java
Double a = Double.valueOf(1.0);
Double b = Double.valueOf(1.0);

boolean sameReference = a == b; // Do not use to compare values.
boolean sameValue = a.equals(b); // true.
```

Do not assume `sameReference` is always `true` or `false`: object creation/reuse can vary, and it is not the floating-point comparison contract.

### When One Operand Is Primitive, Comparison Can Unbox the Wrapper

```java
Double boxed = Double.valueOf(Double.NaN);
double primitive = Double.NaN;

System.out.println(boxed == primitive); // false
```

Here `boxed` is unboxed to `double` for arithmetic comparison, returning to the primitive `NaN != NaN` rule.

If the wrapper is `null`, unboxing can throw `NullPointerException`. For example, `Double d = null; boolean eq = d == 0.0;` does **not** safely return `false`—it fails when evaluating `d`.

When comparing nullable wrappers with object semantics, `java.util.Objects.equals(a, b)` avoids `NullPointerException`, while still using the wrapper's `equals` for two non-null objects, thereby preserving the NaN/signed-zero semantics above.

## 8. Different Wrapper Classes: `Float` and `Double` Are Not Equal via `equals`

```java
Float f = Float.valueOf(1.0f);
Double d = Double.valueOf(1.0);

System.out.println(f.equals(d)); // false
System.out.println(d.equals(f)); // false
System.out.println(f.floatValue() == d.doubleValue()); // true
```

Both wrappers hold the same numeric value `1`, but `equals` requires objects of the same class. In the last primitive expression, binary numeric promotion widens `float` to `double` and compares values, returning `true`.

Do not conclude from the `1.0` example that every `float` vs. `double` can be compared accurately: `float` only has 24 bits of precision and many decimals are already rounded when stored. When business logic requires comparing across both types, clearly define the **intended value** and acceptable conversions.

## 9. When to Use Which Comparison Method?

| Goal | Appropriate approach | Notes |
| --- | --- | --- |
| Handling primitive values per IEEE 754 arithmetic | `a == b`, `a < b` | `NaN` always makes equality false; both signed zeros are equal |
| Detecting NaN | `Double.isNaN(a)`, `Float.isNaN(a)` | Do not use `a == NaN` |
| Comparing `Double`/`Float` objects | `a.equals(b)` | NaN equals NaN; both signed zeros differ |
| Comparing nullable wrappers | `Objects.equals(a, b)` | Avoids NPE from calling `equals` on null; preserves wrapper semantics |
| Sorting floating-point numbers with NaN and signed zero | `Double.compare(a, b)` or `Float.compare(a, b)` | NaN last, `-0.0 < +0.0` under comparator |
| Using floating-point numbers as `HashMap`/`HashSet` keys | Define data per `equals`/`hashCode` | NaN merges keys; signed zero separates keys |
| Comparing two nearby computation results | An error policy suited to the business domain | Do not default to `equals` or an arbitrary fixed epsilon |
| Exact decimal monetary comparisons | `BigDecimal` or smallest-unit integers | `BigDecimal.equals` checks scale too; `compareTo` compares value only |

An example of *approximate comparison* of calculation results:

```java
double computed = 0.1 + 0.2;
double expected = 0.3;
double tolerance = 1e-12;

boolean close = Double.isFinite(computed)
        && Double.isFinite(expected)
        && Math.abs(computed - expected) <= tolerance;
System.out.println(close); // true
```

This is a custom application rule, **not a replacement** for the `Double.equals` contract. The threshold `1e-12` is only meaningful for a suitable problem and scale, not a universal constant for all floating-point numbers. When handling infinity, NaN, very large or very small numbers, or bit-exact requirements, define detailed handling rules separately.

## 10. Standalone Runnable Java 17+ Example

Create the file **`FloatingEqualityDemo.java`**:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class FloatingEqualityDemo {
    public static void main(String[] args) {
        double posZero = +0.0;
        double negZero = -0.0;

        System.out.println("primitive NaN == NaN = "
                + (Double.NaN == Double.NaN));
        System.out.println("primitive +0 == -0 = "
                + (posZero == negZero));

        System.out.println("Double.equals NaN = "
                + Double.valueOf(Double.NaN).equals(Double.valueOf(0.0 / 0.0)));
        System.out.println("Double.equals signed zero = "
                + Double.valueOf(posZero).equals(Double.valueOf(negZero)));

        System.out.println("Float.equals NaN = "
                + Float.valueOf(Float.NaN).equals(Float.valueOf(0.0f / 0.0f)));
        System.out.println("Float.equals signed zero = "
                + Float.valueOf(+0.0f).equals(Float.valueOf(-0.0f)));

        System.out.println("Double.compare -0 < +0 = "
                + (Double.compare(negZero, posZero) < 0));
        System.out.println("Double.compare NaN > infinity = "
                + (Double.compare(Double.NaN,
                        Double.POSITIVE_INFINITY) > 0));

        System.out.println("zero bits equal = "
                + (Double.doubleToLongBits(posZero)
                == Double.doubleToLongBits(negZero)));
        System.out.println("NaN canonical bits equal = "
                + (Double.doubleToLongBits(Double.NaN)
                == Double.doubleToLongBits(0.0 / 0.0)));

        Set<Double> set = new HashSet<>();
        set.add(posZero);
        set.add(negZero);
        set.add(Double.NaN);
        set.add(0.0 / 0.0);
        System.out.println("HashSet size = " + set.size());

        Map<Double, String> names = new HashMap<>();
        names.put(posZero, "positive");
        names.put(negZero, "negative");
        names.put(Double.NaN, "first NaN");
        names.put(0.0 / 0.0, "second NaN");
        System.out.println("HashMap size = " + names.size());
        System.out.println("positive zero key = " + names.get(posZero));
        System.out.println("negative zero key = " + names.get(negZero));
        System.out.println("NaN key = " + names.get(Double.NaN));

        System.out.println("Float.equals Double = "
                + Float.valueOf(1.0f).equals(Double.valueOf(1.0)));

        Double boxedNaN = Double.valueOf(Double.NaN);
        double primitiveNaN = Double.NaN;
        System.out.println("unboxed NaN comparison = "
                + (boxedNaN == primitiveNaN));

        System.out.println("NaN detected = " + Double.isNaN(0.0 / 0.0));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac FloatingEqualityDemo.java
java FloatingEqualityDemo
```

Output:

```text
primitive NaN == NaN = false
primitive +0 == -0 = true
Double.equals NaN = true
Double.equals signed zero = false
Float.equals NaN = true
Float.equals signed zero = false
Double.compare -0 < +0 = true
Double.compare NaN > infinity = true
zero bits equal = false
NaN canonical bits equal = true
HashSet size = 3
HashMap size = 3
positive zero key = positive
negative zero key = negative
NaN key = second NaN
Float.equals Double = false
unboxed NaN comparison = false
NaN detected = true
```

The example focuses on behaviors **guaranteed by the Java contract**, without relying on `HashMap`/`HashSet` iteration order, wrapper caching, or specific raw NaN payloads. You can verify the `HashSet`/`HashMap` lines to immediately see why two "zeros" produce two keys while multiple NaN sources collapse into a single key.

## 11. Common Pitfalls When Handling `Float`/`Double`

1. **Assuming `Double.equals` is equivalent to `==` on `double`.** Wrong in two core cases: `NaN` and signed zero.
2. **Using `x == Double.NaN` to check for calculation errors.** The result is always `false`; use `Double.isNaN(x)`.
3. **Assuming `NaN` is never "equal to itself" in any API.** Primitive `==` returns `false`, but wrapper `equals` returns `true` and `Double.compare(NaN,NaN)` returns 0.
4. **Assuming `+0.0` and `-0.0` are a single key in `HashMap<Double,...>`.** Wrappers distinguish them, so they normally form two keys.
5. **Using `Double.compare(a,b)==0` and inferring `a==b` for all values.** Untrue for NaN and signed zero. `compare == 0` is consistent with wrapper `equals`, not all primitive comparisons.
6. **Using `==` between two wrappers to compare contents.** When both are references, the operation checks object identity; for wrapper semantics, use `equals`.
7. **Calling `equals` across different `Float` and `Double` classes and expecting `true` because both represent 1.** Wrappers require the same object type.
8. **Assuming all NaNs have the same raw-bit payload.** `equals` relies on bit conversions with canonicalization; when working with binary protocols, understand the difference from `doubleToRawLongBits`/`floatToRawIntBits`.
9. **Using `equals` to check approximate results** of calculations like `0.1+0.2`. `equals` is not tolerance-based comparison; choose a different policy if the problem permits small deviations.
10. **Failing to account for `null` when comparing wrappers.** `a.equals(b)` can throw NPE when `a` is null; `==` with unboxing can also throw NPE. Use an appropriate nullable policy.

## 12. Floating-Point Comparison Design Checklist

Before choosing an operator or API, determine clearly:

- **Is the data primitive or wrapper?** The same `==` symbol can mean arithmetic comparison or reference identity comparison depending on operand types.
- **Is NaN allowed to appear?** If it signals invalid data, check early with `isNaN`; if it is a valid value in collection keys, understand wrapper canonicalization rules.
- **Must the two zeros be distinguished?** If not, consider normalizing zero before storing keys; if so, `Double.equals`/`Float.equals` preserve the difference.
- **Is a total sort order needed?** Choose `Double.compare`/`Float.compare` for a well-defined ordering with NaN and signed zero.
- **What accuracy is actually required?** If comparing measured/estimated quantities, determine thresholds from the problem; if decimal exactness is needed, consider `BigDecimal` and its own `equals`/`compareTo` rules.
- **Is it used as a data or collection key?** Once an equality definition is chosen, ensure the comparator, hash code, and data normalization are consistent with that goal.

**Conclusion:** `==` on `float`/`double` follows IEEE 754 arithmetic comparison (**NaN does not equal NaN, both zeros are equal**). `Float.equals` and `Double.equals` rely on NaN-canonicalized bit patterns (**NaN equals NaN, both zeros differ**), establishing consistent key and ordering semantics in collections. Do not substitute one rule for the other unconsciously; choose based on the program's actual requirements.

**References:** [Java SE 21 — Double.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html#equals(java.lang.Object)), [Double.compare](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html#compare(double,double)), [Double.doubleToLongBits](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html#doubleToLongBits(double)), [Float.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Float.html#equals(java.lang.Object)), [JLS §15.21.1 — Numerical Equality Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.21.1).
