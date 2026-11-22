# Comparing `==` Between Two Wrappers and Between a Wrapper and a Primitive in Java

Java has two common type groups for representing numbers: **primitives** (`int`, `long`, `double`, …) and **wrappers** (`Integer`, `Long`, `Double`, …). A wrapper is a **reference object** containing a corresponding primitive value. This causes the same `==` symbol to carry two very different meanings:

- When **both operands are wrappers of the same reference type**, `==` normally compares **whether they are the same object** (*reference identity*), rather than comparing numeric values.
- When **one operand is a numeric wrapper and the other is a numeric primitive**, Java normally **unboxes** the wrapper, applies appropriate numeric type conversions, and then compares **numeric values**.
- If the wrapper that needs unboxing is `null`, the operation can throw **`NullPointerException`**.
- `equals` and `Objects.equals` use object equality rules, distinct from reference `==`. For numeric wrappers, `equals` normally requires **the same wrapper type and the same value according to that type's rules**.

Clearly understanding **the static types of both operands** and **whether unboxing occurs** is the key to explaining a comparison.

## 1. Distinguishing primitives, wrappers, and boxing/unboxing

| Primitive | Corresponding wrapper | Example |
| --- | --- | --- |
| `byte` | `Byte` | `byte n = 7; Byte w = n;` |
| `short` | `Short` | `Short w = (short) 7;` |
| `char` | `Character` | `Character w = 'A';` |
| `int` | `Integer` | `Integer w = 7;` |
| `long` | `Long` | `Long w = 7L;` |
| `float` | `Float` | `Float w = 7.0f;` |
| `double` | `Double` | `Double w = 7.0;` |
| `boolean` | `Boolean` | `Boolean w = true;` |

**Autoboxing** converts a primitive into a wrapper when the context permits:

```java
int value = 42;
Integer boxed = value; // int -> Integer
```

**Unboxing** converts a wrapper back to a primitive:

```java
Integer boxed = 42;
int plain = boxed; // Integer -> int
```

Wrappers can be `null`; numeric primitives cannot be `null`. Short examples in the explanation sections are written to be placed inside a method/class, unless explicitly noted as a standalone runnable program.

## 2. Two `Integer` wrappers: `==` compares references

`Integer` is a class. With two `Integer` variables, Java can use the `==` operator for **reference equality**:

```java
Integer a = Integer.valueOf(42);
Integer b = a;
boolean sameObject = (a == b); // true because b points to the exact same object as a
```

If two wrappers are two distinct objects holding the same `int` value, `==` on the two references will be `false`; `equals` can still be `true`. However, with `Integer.valueOf` and autoboxing, the JVM can **reuse objects**, causing two separate boxing operations to point to the same object.

**Do not conclude** that `Integer x = 1000; Integer y = 1000; x == y` always evaluates to `false`. For some values, an implementation may cache beyond the minimum; correct code must **not depend on** the identity of separately boxed wrappers.

### Why does caching from -128 to 127 easily mislead learners?

Java guarantees that boxing `int` values in the range **-128 to 127** uses reused objects per the language specification. Therefore:

```java
Integer a = 100;
Integer b = 100;
System.out.println(a == b);      // true: guaranteed cache range
System.out.println(a.equals(b)); // true: same int value
```

However, outside the guaranteed range:

```java
Integer x = 1_000;
Integer y = 1_000;

// Do not write business logic depending on (x == y).
// Use:
boolean equalValues = x.equals(y); // true
```

Why do many resources say `128 == 128` with two `Integer`s gives `false`? That is a common outcome of typical JVM configurations, **not a general contract that a program is entitled to rely on**. Several other integer wrappers also have rules for reusing small boxed values; hence caching must never become a way to check numeric values.

### Identical references are always `==`

```java
Integer n = Integer.valueOf(500);
Integer alias = n;
System.out.println(n == alias); // true, regardless of whether n is in the cache
```

This is object identity, unrelated to the `int` value range.

## 3. Wrapper and primitive: unboxing to compare values

When one side is a numeric primitive and the other is a numeric wrapper, Java performs an **unboxing conversion** on the wrapper operand, then compares numerically according to the appropriate type conversion rules:

```java
Integer boxed = 1_000;
int primitive = 1_000;
System.out.println(boxed == primitive); // true
System.out.println(primitive == boxed); // true
```

This is **completely different** from `Integer == Integer`. The comparison here does not ask whether two references share an object; `primitive` is not a reference.

Another example with widening:

```java
Integer a = 10;
long b = 10L;
System.out.println(a == b); // true: Integer -> int, int -> long
```

Or:

```java
Long wrapped = 10L;
int primitive = 10;
System.out.println(wrapped == primitive); // true: Long -> long; int -> long
```

**Values may be converted before comparison.** If floating-point numbers are involved, numeric promotion can cause precision loss on large values, such as a `long` widened to `double`. Do not interpret an `==` operation with unboxing as an “absolutely exact comparison for any pair of numbers” after arbitrary conversions.

### Converse case: explicitly converting wrappers to primitives

When the intent is to compare the values of two wrappers, you can make it explicit by unboxing:

```java
Integer left = 1_000;
Integer right = 1_000;
boolean equalInts = (left.intValue() == right.intValue()); // true
```

This approach is easy to understand, though both `intValue()` calls will throw `NullPointerException` if the corresponding reference is `null`. If you do not need to unbox, `left.equals(right)` or `Objects.equals(left, right)` is usually cleaner.

## 4. When `null` is involved, `==` can be safe or throw an exception

`Integer` is a reference so it can hold `null`:

```java
Integer missing = null;
Integer alsoMissing = null;
System.out.println(missing == alsoMissing); // true: both are null references
System.out.println(missing == null);        // true: no unboxing
```

Conversely:

```java
Integer missing = null;
int zero = 0;
// System.out.println(missing == zero); // Runtime NPE because missing must be unboxed
```

The commented line **compiles validly** but throws `NullPointerException` if executed. Comparing `missing == null` does not trigger unboxing because the other side is the reference `null` literal, not the `int` value 0.

### How to check for null before unboxing

```java
Integer count = null;
boolean isTen = count != null && count == 10; // false, safe
```

`&&` evaluates from left to right and **short-circuits**: if `count != null` is `false`, the `count == 10` side is not executed.

Reversing the order loses safety:

```java
Integer count = null;
// boolean wrong = count == 10 && count != null;
// if executed, NPE immediately at count == 10
```

For objects:

```java
Integer a = null;
Integer b = null;
boolean bothMissing = java.util.Objects.equals(a, b); // true
```

Check whether **two equally missing values** should truly be considered equal by business logic. `Objects.equals(null, null)` returns `true` per its contract, whereas an input validation rule might require both to be non-`null`.

## 5. What do `equals` and `Objects.equals` compare?

With two `Integer`s, `a.equals(b)` compares **integer values** when `b` is also an `Integer`:

```java
Integer a = 1_000;
Integer b = 1_000;
System.out.println(a.equals(b)); // true
```

`equals` is a method on the left-hand reference. If `a == null`, calling `a.equals(b)` causes an NPE. `Objects.equals(a, b)` is a null-handling comparison utility:

```java
Integer a = null;
Integer b = 7;
System.out.println(java.util.Objects.equals(a, b)); // false
System.out.println(java.util.Objects.equals(null, null)); // true
```

Decision table:

| Syntax | When both arguments are `Integer` | When `null` is present |
| --- | --- | --- |
| `a == b` | Compares whether same object reference | Two nulls are equal, one null is not |
| `a.equals(b)` | Compares same wrapper type and value | NPE if `a` itself is null |
| `Objects.equals(a, b)` | Compares with `equals` when non-null | No NPE; two nulls are considered equal |
| `a.intValue() == b.intValue()` | Compares two primitive `int` values | NPE if either wrapper is null |

**Do not replace every `==` in a program with `equals`**: primitives cannot invoke methods, and in many places you intentionally want reference comparison. Determine the desired semantics first.

## 6. Two wrappers of different numeric types: an easily confused case

`Integer` and `Long` are **two classes with no direct inheritance relationship** and do not automatically become the same type just because both hold integers.

```java
Integer i = 7;
Long l = 7L;

System.out.println(i.equals(l)); // false: Integer and Long are different types
System.out.println(i.longValue() == l.longValue()); // true
```

If you write `i == l` with both operands being `Integer` and `Long` references, Java **reports a compile-time error** because the two reference types cannot be compared with `==` under reference equality rules in this case. It **does not automatically unbox two different numeric wrapper types** to pick numeric comparison.

To compare by value, explicitly convert the operands to primitives, or choose a comparison API according to the defined numeric range:

```java
Integer i = 7;
Long l = 7L;

boolean equal = i.longValue() == l.longValue(); // true
// boolean invalid = i == l; // compile-time error
```

When using `equals`, `Integer.valueOf(7).equals(Long.valueOf(7L))` is `false` even though the mathematical value is 7 in both. `Objects.equals` does not auto-convert wrapper types: it still follows the object's `equals` definition.

### Be careful when comparing `long` and `double`

```java
long exactLong = 9_007_199_254_740_993L; // 2^53 + 1
double roundedDouble = 9_007_199_254_740_992.0;
System.out.println(exactLong == roundedDouble); // true
```

When a `long` is compared with a `double`, Java promotes `long` to `double`; overly large integers can be rounded. `==` can therefore return `true` for two values with different original mathematical sources. This is a limitation of numeric type conversion, unrelated to wrapper caching.

If business logic needs to compare exact integer IDs, do not convert them through `double`.

## 7. `Double`, `Float`: numeric equality and object equality do not match

Two primitive `double` values are compared numerically according to IEEE 754:

```java
double posZero = +0.0;
double negZero = -0.0;
System.out.println(posZero == negZero); // true
```

However, `Double.equals` distinguishes the sign bit of zero:

```java
Double pos = Double.valueOf(+0.0);
Double neg = Double.valueOf(-0.0);
System.out.println(pos.equals(neg)); // false
System.out.println(pos == +0.0);     // true: unboxes pos and compares primitives
System.out.println(neg == +0.0);     // true: unboxes neg, primitive -0.0 == +0.0
```

Note here that `pos.equals(neg)` differs from `pos == +0.0` because **the comparison mechanisms differ**; the first uses the wrapper's `equals` definition, while the second unboxes to use primitive comparison.

Similarly, `NaN`:

```java
double nan = Double.NaN;
System.out.println(nan == nan); // false per IEEE 754

Double boxedNaN1 = Double.valueOf(Double.NaN);
Double boxedNaN2 = Double.valueOf(Double.NaN);
System.out.println(boxedNaN1.equals(boxedNaN2)); // true
```

**Do not use `==` between two `Double` references to check whether two values are NaN**: that compares object identity and depends on object creation/reuse, not directly expressing NaN semantics.

`Float` has corresponding behavior for signed zero and NaN. These exceptions are why you should pick the comparison operator based on specific requirements rather than mechanically applying a slogan like “for wrappers, just use equals”.

## 8. Wrappers in collections: `HashSet`, `HashMap`, and lookup

Collections like `HashSet<Integer>` and keys of `HashMap<Integer, …>` operate via `equals` and `hashCode`, **not** reference `==` to decide duplicate elements.

```java
java.util.Set<Integer> values = new java.util.HashSet<>();
values.add(1_000);
values.add(1_000);
System.out.println(values.size()); // 1
```

In the snippet above, whether Java caches wrapper 1000 or not has zero effect on the set's result. Adding the same `Integer` value twice is treated as a duplicate under `equals`.

Conversely, a `HashSet<Double>` **distinguishes `+0.0` and `-0.0`**, because `Double.equals` distinguishes them:

```java
java.util.Set<Double> zeros = new java.util.HashSet<>();
zeros.add(+0.0);
zeros.add(-0.0);
System.out.println(zeros.size()); // 2
```

This serves as a reminder that a comparison used for keys must match the **semantic contract**. If an application wants signed zeros to act as one key, proactively normalize values according to policy rather than assuming every API treats them as equal.

## 9. What happens in overloads, expressions, and conditional operators?

When passing a wrapper into a method accepting a primitive, Java can unbox according to method invocation rules:

```java
static boolean positive(int value) {
    return value > 0;
}

Integer boxed = 10;
// positive(boxed) -> true: Java unboxes Integer to int
```

This is an illustrative method and call placed in an appropriate class/method. If `boxed` is `null`, unboxing will throw an NPE.

### `==` does not always unbox

```java
Integer a = 10;
Integer b = 10;
int c = 10;

boolean wrapperWrapper = a == b; // reference equality
boolean wrapperPrimitive = a == c; // numeric equality after unboxing
```

Do not look at all values being 10 and ignore static types. The expression's outcome changes because different semantic meanings of the `==` operator are selected.

### The `+` operator triggers unboxing before comparison

```java
Integer a = 10;
Integer b = 10;

boolean numeric = (a + 0) == b; // true: a + 0 is int; b is unboxed
```

In this example `a + 0` produces an `int`, so the final `==` is numeric comparison; whereas `a == b` is reference comparison. However, this is not a trick to use to “force equals”. Use `a.equals(b)` or `Objects.equals(a,b)` when you want object value comparison, and check for null explicitly.

## 10. Standalone runnable Java 17+ program

Create file **`WrapperEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class WrapperEqualityDemo {
    public static void main(String[] args) {
        Integer smallA = 100;
        Integer smallB = 100;
        System.out.println("smallIdentity=" + (smallA == smallB));

        Integer largeA = 1_000;
        Integer largeB = 1_000;
        System.out.println("largeValuesEqual=" + largeA.equals(largeB));
        System.out.println("largePrimitiveEqual=" +
                (largeA.intValue() == largeB.intValue()));

        Integer alias = largeA;
        System.out.println("sameAlias=" + (largeA == alias));

        int primitive = 1_000;
        System.out.println("wrapperVsPrimitive=" + (largeA == primitive));
        long longPrimitive = 1_000L;
        System.out.println("wrapperVsLong=" + (largeA == longPrimitive));
        System.out.println("wrapperPlusZero=" + ((largeA + 0) == largeB));

        Integer missing = null;
        Integer alsoMissing = null;
        System.out.println("nullReferences=" + (missing == alsoMissing));
        System.out.println("nullLiteral=" + (missing == null));
        System.out.println("nullSafeEquals=" + Objects.equals(missing, alsoMissing));
        System.out.println("nullGuard=" + (missing != null && missing == 0));
        try {
            boolean outcome = (missing == 0);
            System.out.println("nullUnbox=" + outcome);
        } catch (NullPointerException ex) {
            System.out.println("nullUnbox=NullPointerException");
        }

        Integer numberInt = 7;
        Long numberLong = 7L;
        System.out.println("crossTypeEquals=" + numberInt.equals(numberLong));
        System.out.println("crossTypeNumeric=" +
                (numberInt.longValue() == numberLong.longValue()));

        Set<Integer> values = new HashSet<>();
        values.add(1_000);
        values.add(1_000);
        System.out.println("integerSetSize=" + values.size());

        Double plusZero = Double.valueOf(+0.0);
        Double minusZero = Double.valueOf(-0.0);
        System.out.println("doubleWrapperEquals=" + plusZero.equals(minusZero));
        System.out.println("doublePrimitiveCompare=" + (minusZero == +0.0));

        Set<Double> zeros = new HashSet<>();
        zeros.add(+0.0);
        zeros.add(-0.0);
        System.out.println("doubleSetSize=" + zeros.size());

        double nan = Double.NaN;
        System.out.println("nanPrimitiveSelf=" + (nan == nan));
        System.out.println("nanWrapperEquals=" +
                Double.valueOf(nan).equals(Double.valueOf(nan)));

        long big = 9_007_199_254_740_993L;
        double rounded = 9_007_199_254_740_992.0;
        System.out.println("longDoubleNumericEqual=" + (big == rounded));
    }
}
```

Compile and run:

```bash
javac WrapperEqualityDemo.java
java WrapperEqualityDemo
```

Exact output:

```text
smallIdentity=true
largeValuesEqual=true
largePrimitiveEqual=true
sameAlias=true
wrapperVsPrimitive=true
wrapperVsLong=true
wrapperPlusZero=true
nullReferences=true
nullLiteral=true
nullSafeEquals=true
nullGuard=false
nullUnbox=NullPointerException
crossTypeEquals=false
crossTypeNumeric=true
integerSetSize=1
doubleWrapperEquals=false
doublePrimitiveCompare=true
doubleSetSize=2
nanPrimitiveSelf=false
nanWrapperEquals=true
longDoubleNumericEqual=true
```

The program **does not print `largeA == largeB`**, because for values outside the guaranteed cache range, the identity of two separately created wrappers is not a stable contract to test. The lines `largeValuesEqual` and `wrapperVsPrimitive` represent the semantics worth relying on when comparing **values**.

## 11. Common mistakes and how to fix them

| Statement or practice | Issue | Solution |
| --- | --- | --- |
| “Two `Integer`s using `==` is numeric comparison.” | False: two reference wrappers of the same type use reference identity. | Use `equals` or `Objects.equals`. |
| “`Integer 100 == Integer 100` is true, so any `Integer` compared with `==` is safe.” | False: boxing/caching causes small values to frequently share objects. | Do not rely on caching to check values. |
| “`Integer 1000 == Integer 1000` is definitely false.” | There is no identity guarantee for this range. | Do not depend on the result of `==`. |
| “`Integer a == int b` still compares references.” | The primitive causes the wrapper to be unboxed for numeric comparison. | If null is possible, check first. |
| “`null Integer == 0` is false.” | False: unboxing null throws NPE. | `a != null && a == 0`. |
| “`a.equals(b)` is safe with `a == null`.” | False: calling a method on null throws NPE. | `Objects.equals(a,b)`, or validate null first. |
| “`Integer.equals(Long)` returns true if both are 7.” | False: wrappers of different classes are not equal. | Convert to an appropriate numeric type before comparing. |
| “You can write `Integer a == Long b` to auto-unbox both.” | Invalid when both sides are numeric wrappers of different types that cannot be reference-compared. | Unbox explicitly then compare. |
| “`Double.equals` is like primitive `==` for ±0.0.” | False: the wrapper distinguishes signed zeros. | Choose the required rule; normalize zero if appropriate. |
| “`==` on two `Double` objects checks NaN equality like `equals`.” | False: `==` compares identity, whereas `equals` has its own rule for NaN. | Use `Double.isNaN`/`Double.equals` appropriately. |
| “`HashSet<Integer>` relies on caching to deduplicate numbers.” | False: sets use `equals`/`hashCode`. | Understand collection contracts. |

### Procedure for reading an `==` expression

1. **Check the static type of each side.** Two wrappers of the same type are two references; a wrapper and a numeric primitive trigger unboxing and numeric comparison.
2. **Check if null is possible.** Comparing two references with each other or with `null` does not necessarily unbox; comparing a wrapper with a primitive can NPE.
3. **Do not treat caching as business logic.** Object reuse is not numeric equality.
4. **Pick the equality API according to need.** `equals` for wrappers of the same type; `Objects.equals` to handle null; primitive numeric comparison when intentionally comparing numeric values after conversion.
5. **Check cross-type and floating-point cases.** `Integer`/`Long` are not automatically equivalent in `equals`; `Double` has NaN/signed-zero and converting `long` to `double` can lose precision.
6. **For collections, look at `equals` and `hashCode`**, do not guess from the `==` result of two wrappers.

**Key takeaway:** `Integer == Integer` compares **identity**; `Integer == int` compares **values after unboxing**; `Integer.equals(Integer)` compares **values within the same wrapper type**. `null` and floating-point rules can change behavior, so always verify the types of both operands before using `==`.