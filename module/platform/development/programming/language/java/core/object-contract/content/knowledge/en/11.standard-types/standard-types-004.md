# Distinguishing `==` on floating-point numbers from `equals()` on `Double` and `Float` wrappers

## 1. Are you comparing primitive values or objects?

In Java, `double` and `float` are **primitive types**; `Double` and `Float` are **wrapper classes**. The following two expressions look similar but rely on different rules:

```java
double a = 1.5;
double b = 1.5;
boolean primitiveEqual = (a == b);           // true
boolean wrapperEqual = Double.valueOf(a)
        .equals(Double.valueOf(b));          // true
```

This is an **illustrative code snippet**, not a standalone Java program. The results above happen to both be `true`; how the expressions are evaluated is what needs to be distinguished:

- **`a == b` with two primitive numeric operands:** Java performs numeric comparison according to IEEE 754 floating-point rules; when `float` and `double` are mixed, numeric promotion (`binary numeric promotion`) is applied before comparing.
- **`x.equals(y)` where `x` is `Double` or `Float`:** invokes the method on object `x` and checks the value under the wrapper class's rules, including special handling for `NaN` and `+0.0`/`-0.0`. The argument must be of the **exact same wrapper class** (`Double` for `Double.equals`, `Float` for `Float.equals`).
- **`x == y` with two `Double` (or two `Float`) reference variables:** compares **whether they are the same object reference**, without calling `equals()` and without auto-unboxing when both operands are references.

This leads to three distinct questions: whether two **primitive values** are equal under `==`; whether two **wrapper objects** are equal under `equals()`; and whether two **references** point to the exact same object.

## 2. `NaN`: `==` is `false`, yet `Double.equals()` can be `true`

`NaN` (Not a Number) represents the undefined result of certain floating-point operations such as `0.0 / 0.0`. With the `==` operator on primitive floating-point numbers:

```java
double x = Double.NaN;
System.out.println(x == x);                         // false
System.out.println(Double.valueOf(x).equals(
        Double.valueOf(Double.NaN)));               // true
```

Under floating-point comparison rules, **any `==` equality comparison with a `NaN` operand returns `false`**, even when comparing a variable with itself. To detect NaN, use `Double.isNaN(value)` or `Float.isNaN(value)`.

Meanwhile, `Double.equals(Object)` specifies that **two `Double` values holding NaN are considered equal**, even across different NaN bit patterns. `Float.equals(Object)` likewise treats `Float` NaNs as equal.

This is a deliberate design choice so that wrapper classes work with the `equals()` contract (especially reflexivity) and with sets/hash tables. `Double.doubleToLongBits` and `Float.floatToIntBits` normalize NaN bit patterns for this comparison purpose.

## 3. Signed zeros: `+0.0 == -0.0` yet wrapper `equals()` is `false`

IEEE 754 represents **two signs for zero**. When comparing primitive numbers:

```java
double positive = +0.0;
double negative = -0.0;
System.out.println(positive == negative);           // true
System.out.println(Double.valueOf(positive)
        .equals(Double.valueOf(negative)));         // false
```

Under `==`, `+0.0` and `-0.0` are considered equal. Under `Double.equals()`, the two representations have **different sign bits**, so they are not equal. `Float.equals()` applies the same distinction to `+0.0f` and `-0.0f`.

Do not confuse this rule with `NaN`: `Double.equals()` **merges all NaNs into the same equal value**, but **distinguishes the sign of zero**. The rules for `Float` are analogous.

## 4. Behavior comparison table

Assume each `equals()` call uses two objects of the same wrapper class (`Double` or `Float`) containing the corresponding values:

| Case | `==` between primitive values | `equals()` between wrappers of the same type |
| --- | --- | --- |
| `1.5` and `1.5` | `true` | `true` |
| `1.5` and `2.0` | `false` | `false` |
| `Double.NaN` and `Double.NaN` | `false` | `true` |
| `+0.0` and `-0.0` | `true` | `false` |
| `Double.POSITIVE_INFINITY` and itself | `true` | `true` |
| `Float.NaN` and `Float.NaN` | `false` | `true` |
| `+0.0f` and `-0.0f` | `true` | `false` |

None of the comparisons in this table uses `==` between **two wrapper references**: if you change the operands to `Double`/`Double`, the meaning of `==` shifts to object identity.

## 5. Standalone runnable Java 17+ program

Save the entire snippet to the file **`FloatingEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class FloatingEqualityDemo {
    public static void main(String[] args) {
        double plusZero = +0.0;
        double minusZero = -0.0;
        double nan1 = Double.NaN;
        double nan2 = 0.0 / 0.0;

        Double boxedPlusZero = Double.valueOf(plusZero);
        Double boxedMinusZero = Double.valueOf(minusZero);
        Double boxedNaN1 = Double.valueOf(nan1);
        Double boxedNaN2 = Double.valueOf(nan2);

        System.out.println("double zeros ==: " + (plusZero == minusZero));
        System.out.println("Double.equals zeros: "
                + boxedPlusZero.equals(boxedMinusZero));
        System.out.println("double NaN ==: " + (nan1 == nan2));
        System.out.println("Double.equals NaN: "
                + boxedNaN1.equals(boxedNaN2));

        float floatPlusZero = +0.0f;
        float floatMinusZero = -0.0f;
        System.out.println("float zeros ==: "
                + (floatPlusZero == floatMinusZero));
        System.out.println("Float.equals zeros: "
                + Float.valueOf(floatPlusZero).equals(Float.valueOf(floatMinusZero)));
        System.out.println("float NaN ==: " + (Float.NaN == Float.NaN));
        System.out.println("Float.equals NaN: "
                + Float.valueOf(Float.NaN).equals(Float.valueOf(Float.NaN)));

        System.out.println("primitive double/float ==: " + (1.0d == 1.0f));
        System.out.println("cross-type wrapper equals: "
                + Double.valueOf(1.0).equals(Float.valueOf(1.0f)));
        System.out.println("Objects.equals same Double: "
                + Objects.equals(Double.valueOf(1.5), Double.valueOf(1.5)));

        Set<Double> values = new HashSet<>();
        values.add(boxedNaN1);
        values.add(boxedNaN2);
        values.add(boxedPlusZero);
        values.add(boxedMinusZero);
        System.out.println("HashSet<Double> size: " + values.size());

        System.out.println("decimal ==: " + (0.1 + 0.2 == 0.3));
        System.out.println("decimal close: "
                + (Math.abs((0.1 + 0.2) - 0.3) < 1e-9));

        Double missing = null;
        System.out.println("Objects.equals(null, null): "
                + Objects.equals(missing, null));
        try {
            System.out.println(missing == 0.0);
        } catch (NullPointerException ex) {
            System.out.println("null Double == double: NullPointerException");
        }
    }
}
```

Compile and run:

```bash
javac FloatingEqualityDemo.java
java FloatingEqualityDemo
```

Output:

```text
double zeros ==: true
Double.equals zeros: false
double NaN ==: false
Double.equals NaN: true
float zeros ==: true
Float.equals zeros: false
float NaN ==: false
Float.equals NaN: true
primitive double/float ==: true
cross-type wrapper equals: false
Objects.equals same Double: true
HashSet<Double> size: 3
decimal ==: false
decimal close: true
Objects.equals(null, null): true
null Double == double: NullPointerException
```

`HashSet<Double>` stores three elements because **two NaNs are considered duplicates under `equals()`**, whereas `+0.0` and `-0.0` are two distinct values under the `Double` class contract. The wrapper class ensures `hashCode()` corresponds to `equals()`, so lookups in hash-based collections remain consistent.

The `decimal close: true` example illustrates approximate comparison with a small tolerance in a **scenario with finite numbers of small magnitude**; `1e-9` is only a sample threshold, not the right value for every problem.

## 6. Three traps when using `==` with wrapper classes

### a. Two wrappers: reference comparison

```java
Double first = Double.valueOf(1.25);
Double second = Double.valueOf(1.25);
boolean sameObject = (first == second);  // do not assume true/false
boolean sameValue = first.equals(second); // true
```

Because both `first` and `second` are `Double`, `==` here checks for the **same object**. Do not rely on whether a factory or autoboxing reuses an object. The same applies to `Float`.

### b. One wrapper and one primitive: Java auto-unboxes

```java
Double boxed = Double.valueOf(1.25);
double primitive = 1.25;
boolean equal = (boxed == primitive);     // true, boxed is unboxed
```

When one side is `Double` and the other is `double`, the numeric comparison expression requires a primitive value; Java performs **unboxing** on the wrapper side. If `boxed == null`, unboxing throws `NullPointerException`; `null` is not automatically treated as `0.0`.

### c. `Double.equals(Float)` is always `false`

```java
System.out.println(1.0d == 1.0f); // true: two primitives, numeric promotion
System.out.println(Double.valueOf(1.0).equals(Float.valueOf(1.0f)));
// false: Double.equals only accepts Double objects
```

`Double.equals(Object)` does not convert a `Float` into a `Double` before comparing, and `Float.equals(Object)` does not automatically convert from `Double` either. Meanwhile, `==` on two primitives of different types uses numeric promotion rules. For numbers that cannot be represented exactly such as `0.1f`, promotion can still lead to unexpected results due to representation error.

## 7. Approximate comparison and comparison for keys

The `==` comparison on primitives asks **whether two represented values are equal under Java's floating-point rules**. It does not understand rounding error from earlier computations. For example, `0.1 + 0.2` and `0.3` differ by a tiny amount due to binary representation, so `==` returns `false`.

If the business requirement is **near-equality** in numerical calculations, you can consider an appropriate error threshold:

```java
boolean close = Math.abs(a - b) <= tolerance;
```

The snippet above assumes `a` and `b` are finite numbers; if `NaN`, infinities, multiple orders of magnitude, or values close to zero are possible, you must design a dedicated check (such as handling special cases separately and combining absolute/relative thresholds). Do not use an arbitrary tolerance to replace `equals()`/`hashCode()` for hash table keys: ordinary near-equality can be **non-transitive** (A is close to B, B is close to C, yet A is not close to C), violating the requirements of an equality relation.

Conversely, when using `Double`/`Float` in a `HashMap`, `HashSet`, or value-object comparisons, `equals()` has stable rules compatible with hashing: `NaN` equals NaN, `+0.0` differs from `-0.0`. For applications needing a sort order, `Double.compare(a, b)` and `Float.compare(a, b)` provide a more complete order than `==`/`<` on primitives, including ordering for NaN and the two zeros; do not interpret `Double.compare` simply as `a == b`.

`Objects.equals(x, y)` helps compare **two potentially `null` references** without throwing NPE on its own: two `null`s return `true`, one `null` returns `false`, and when non-`null`, it relies on `x.equals(y)`. If both are of class `Double`, the NaN/zero rules described above still apply.

## 8. Common mistakes and quick checks

| Misconception / wrong code | How to handle it |
| --- | --- |
| Using `==` between two `Double`s and thinking it compares values | Choose `equals()` or `Objects.equals()` when wrapper values are needed |
| Thinking `Double.NaN == Double.NaN` is `true` | `NaN` does not equal itself under primitive `==`; use `Double.isNaN` to check for NaN |
| Thinking `+0.0` and `-0.0` are always treated as one | Distinguish them: primitive `==` is `true`, wrapper `equals()` is `false` |
| Overlooking unboxing of a potentially `null` `Double` | Check for `null` before numeric comparison or use `Objects.equals()` with the exact semantics needed |
| Mixing `Double` and `Float` in `equals()` expecting auto-conversion | Convert to the same type and define the comparison rules explicitly |
| Comparing floating-point calculation results with `==` when business logic expects near-equality | Choose an error criterion based on value domain, units, and boundary conditions; handle NaN/infinity separately |

## 9. Knowledge self-check

1. What does `double d = Double.NaN; d == d` return? **`false`**, because `NaN` does not equal itself under floating-point `==`.
2. What does `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` return? **`true`**, because `Double.equals()` treats two NaNs as equal.
3. What are `+0.0d == -0.0d` and `Double.valueOf(+0.0d).equals(Double.valueOf(-0.0d))` respectively? **`true` and `false`**.
4. Does `Double x = null; x == 0.0` return `false`? **No**; Java unboxes `x` and throws `NullPointerException`.
5. Given two `Double` variables holding `1.0`, is `x == y` always `true`? **No**; `==` between two references asks whether they are the same object.

**Remember:** `==` on `double`/`float` compares primitive floating-point values; `Double.equals`/`Float.equals` is the wrapper object's equality relation, which **treats NaN as equal to NaN yet distinguishes `+0.0` from `-0.0`**. And when both operands are wrappers, `==` compares **references** instead, not replacing `equals()`.
