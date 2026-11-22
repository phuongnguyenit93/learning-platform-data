# Mistake of Using `==` to Compare Two Wrappers in Java

## 1. The Problem: Two Equal Numbers May Still Not Be `==`

Java has primitive types (*primitive*) such as `int`, `long`, `double`, `boolean`, and corresponding **wrapper classes (*wrapper*)**: `Integer`, `Long`, `Double`, `Boolean`, etc. How they are compared depends on **the static types of both operands** in the expression, not just the displayed numeric value.

```java
int primitiveA = 1000;
int primitiveB = 1000;
System.out.println(primitiveA == primitiveB); // true: compares int values

Integer boxA = Integer.valueOf(1000);
Integer boxB = Integer.valueOf(1000);
System.out.println(boxA.equals(boxB)); // true: both Integer values are equal

// Avoid using boxA == boxB to decide numeric equality:
// that operator checks whether they are the same object.
```

The lines above are an illustrative snippet placed inside `main` of a class and require no import for `Integer`. The expression `boxA == boxB` can return `true` or `false` depending on identity/caching; **it must never be used as a criterion for numeric comparison**.

In this article, we will:

- Understand `==` on primitives, references, and wrappers.
- Spot the **Integer cache** trap, autoboxing, unboxing, and `null` cases.
- Choose `equals()`, `Objects.equals()`, and `compareTo()` for the right purpose.
- Distinguish wrappers of different types such as `Integer` vs `Long`.
- Explain the `Double.NaN` and signed zero exceptions.
- Verify with Java 17+ programs having deterministic output.

## 2. Fundamental Rules of `==`

In Java, `==` is the **equality** operator and performs comparison based on operand categories:

| Two Operands | What Does `==` Mean? | Example |
|---|---|---|
| Two numeric primitives | Compares numeric values after numeric promotion rules | `10 == 10L` → `true` |
| Two `boolean` primitives | Compares logical values | `true == true` → `true` |
| Two references of comparable reference types | Compares **identity**: whether they refer to the same object or are both null | `Integer a, b; a == b` |
| One numeric wrapper and one numeric primitive | The wrapper is typically **unboxed**; then numeric comparison runs | `Integer a = 5; a == 5` → `true` |
| Wrappers of different types incomparable under reference `==` rules | Can be a **compile-time error**, e.g. `Integer == Long` | See Section 6 |

Therefore, saying "`==` always compares addresses" is **not true for every expression**. It is true when Java performs **reference equality** between two objects. If at least one operand is a numeric primitive, Java can unbox the wrapper and apply **numeric equality**. Always look at the exact expression written.

### Primitives and Wrappers: Different Data Types

```java
int a = 200;
int b = 200;
System.out.println(a == b); // true

Integer x = Integer.valueOf(200);
Integer y = Integer.valueOf(200);
System.out.println(x.equals(y)); // true
```

`int` has no object identity; `Integer` is a reference type. Both can represent the number 200, yet they follow different default comparison rules.

## 3. Autoboxing, Unboxing, and the Integer Cache

### 3.1. What Is Autoboxing?

Java automatically converts primitives to wrappers in contexts requiring a reference:

```java
Integer count = 10; // boxing from int
int raw = count;    // unboxing back to int
```

Semantically, boxing an `int` behaves like `Integer.valueOf(10)`, without necessarily creating a new object every time. The JVM can reuse wrapper objects via a **cache** mechanism.

### 3.2. Why Is `127 == 127` as `Integer` Usually True?

For `Integer.valueOf(int)`, Java **guarantees caching** for values from `-128` to `127`, inclusive. Hence:

```java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);

System.out.println(a == b);      // true: same cached object
System.out.println(a.equals(b)); // true: equal in value
```

`a == b` evaluates to `true` because the implementation returns the same cached reference; this does not turn `==` into a value comparison.

Other wrappers also have reuse contracts:

- `Byte.valueOf`: caches the entire `byte` range.
- `Short.valueOf`, `Long.valueOf`: guarantee caching at least `-128` to `127`.
- `Character.valueOf`: caches at least characters `\u0000` to `\u007F`.
- `Boolean.valueOf`: returns `Boolean.TRUE` or `Boolean.FALSE`.
- `Float` and `Double`: **have no similar caching guarantee** for numeric values; avoid inferring identity.

For `Integer` outside `-128..127`, Java **may extend the cache** depending on JVM version, implementation, and configuration. Therefore, do not write tests assuming "`Integer.valueOf(128) == Integer.valueOf(128)` is definitely false".

### 3.3. Complete Example with Deterministic Output

**File `WrapperCacheDemo.java`:**

```java
public class WrapperCacheDemo {
    public static void main(String[] args) {
        Integer smallA = Integer.valueOf(127);
        Integer smallB = Integer.valueOf(127);

        Integer largeA = Integer.valueOf(1_000);
        Integer largeB = Integer.valueOf(1_000);

        System.out.println("smallSameReference=" + (smallA == smallB));
        System.out.println("smallSameValue=" + smallA.equals(smallB));
        System.out.println("largeSameValue=" + largeA.equals(largeB));
        System.out.println("largeViaCompareTo="
                + (largeA.compareTo(largeB) == 0));
    }
}
```

```bash
javac WrapperCacheDemo.java
java WrapperCacheDemo
```

```text
smallSameReference=true
smallSameValue=true
largeSameValue=true
largeViaCompareTo=true
```

The example **deliberately does not print `largeA == largeB` as a fixed outcome**, because outside the guaranteed cache range, identity is implementation-dependent. Never build business rules on cache side effects even if they seem to pass consistently on your machine.

## 4. `equals()` Is Value Comparison for Wrappers of the Same Type

Standard wrappers implement `equals(Object)` to check value according to each class's contract, along with an appropriate object type requirement.

```java
Integer x = Integer.valueOf(1_000);
Integer y = Integer.valueOf(1_000);
System.out.println(x.equals(y)); // true

Long a = Long.valueOf(1_000L);
Long b = Long.valueOf(1_000L);
System.out.println(a.equals(b)); // true

Boolean yes = Boolean.valueOf(true);
System.out.println(yes.equals(Boolean.TRUE)); // true
```

This is an illustrative snippet inside `main`. For `Integer`, `Long`, `Short`, `Byte`, and `Character`, `equals` checks **the same wrapper class and the same underlying value**. Objects of different classes are not considered equal merely because they represent the same number.

`equals` is an instance method, so:

```java
Integer maybe = null;
// maybe.equals(0); // Throws NullPointerException if executed.
```

When data can be `null`, `Objects.equals(a,b)` can be a suitable choice; see Section 7.

### Ordering Comparison with `compareTo()`

When less-than/greater-than ordering is needed, numeric wrappers can use `compareTo` or primitive comparison methods:

```java
Integer x = 2;
Integer y = 10;

System.out.println(x.compareTo(y) < 0); // true
System.out.println(Integer.compare(x, y) < 0); // true
```

`Integer.compare(x,y)` takes `int`, so it unboxes both wrappers. It **does not handle `null`**. For `compareTo`, also avoid assuming the return value is strictly `-1`, `0`, or `1`; the comparison contract relies on **negative sign, zero, or positive sign**.

## 5. When One Side Is Primitive: `==` Can Check Value Correctly but Risks NPE

Comparing **an `Integer` with an `int`** makes Java unbox `Integer` and then compare primitive values:

```java
Integer wrapper = Integer.valueOf(1_000);
int primitive = 1_000;
long wider = 1_000L;

System.out.println(wrapper == primitive); // true
System.out.println(wrapper == wider);     // true
```

In the second expression, `wrapper` is unboxed from `Integer` to `int`, and then binary numeric promotion applies to compare with `long`. This is a numeric value comparison, not object identity comparison.

**Danger:** if the wrapper is `null`, unboxing throws `NullPointerException`:

```java
Integer count = null;

System.out.println(count == null); // true: reference comparison with null
// System.out.println(count == 0); // NullPointerException due to unboxing
```

The difference is determined by the type of the second operand:

- `count == null`: reference comparison, no unboxing.
- `count == Integer.valueOf(0)`: two `Integer` references, compares identity, no unboxing; if `count` is null, result is `false`.
- `count == 0`: one side is primitive `int`, forcing unboxing of `count`; throws if null.
- `count > 0`, `count + 1`: both require unboxing, so null also throws.

### Complete Example: Predicting Null Cases

**File `WrapperUnboxingDemo.java`:**

```java
public class WrapperUnboxingDemo {
    public static void main(String[] args) {
        Integer boxed = Integer.valueOf(1_000);
        int primitive = 1_000;
        long wide = 1_000L;

        System.out.println("boxVsInt=" + (boxed == primitive));
        System.out.println("boxVsLongPrimitive=" + (boxed == wide));

        Integer missing = null;
        Integer otherMissing = null;
        Integer one = Integer.valueOf(1);

        System.out.println("twoNullReferences=" + (missing == otherMissing));
        System.out.println("nullVsWrapper=" + (missing == one));
        System.out.println("nullLiteral=" + (missing == null));

        try {
            System.out.println(missing == 1);
        } catch (NullPointerException ex) {
            System.out.println("nullUnboxing=NullPointerException");
        }
    }
}
```

```bash
javac WrapperUnboxingDemo.java
java WrapperUnboxingDemo
```

```text
boxVsInt=true
boxVsLongPrimitive=true
twoNullReferences=true
nullVsWrapper=false
nullLiteral=true
nullUnboxing=NullPointerException
```

Note: `==` between two null references returns `true` because of **identical null reference values**, not because two objects are "equal"; there are no objects here at all.

## 6. Two Wrappers of Different Types: `Integer` and `Long`

This is another major trap: two wrappers can represent the same numeric value yet **`equals` does not return true**:

```java
Integer i = Integer.valueOf(1);
Long l = Long.valueOf(1L);

System.out.println(i.equals(l)); // false: different classes
System.out.println(i.longValue() == l.longValue()); // true
```

**Do not write `i == l`** when both are `Integer` and `Long` objects: that expression is a **compile-time error** in Java because these two final reference types lack the cast compatibility required for reference equality. The fact that both extend `Number` **does not turn `==` between them into numeric comparison**.

The following code is **only to illustrate the error, not a runnable program**:

```java
Integer i = 1;
Long l = 1L;
// boolean equal = (i == l); // COMPILE ERROR: incomparable types
```

If business logic needs to compare **numeric values across different types**, you must intentionally normalize them, for example:

- Between `Integer` and `Long`, `i.longValue() == l.longValue()` preserves both ranges exactly, since `int` always converts losslessly to `long`.
- When `double`, `float`, or very large integers are involved, converting to floating-point can **lose digits**, so an appropriate criterion and data type (such as `BigDecimal` constructed from the right source) is needed.
- If the requirement is **object and type equality**, `Objects.equals(i,l)` returning `false` is the sensible behavior.

### Complete Example

**File `MixedWrapperDemo.java`:**

```java
public class MixedWrapperDemo {
    public static void main(String[] args) {
        Integer i = Integer.valueOf(1_000);
        Long l = Long.valueOf(1_000L);

        System.out.println("equals=" + i.equals(l));
        System.out.println("numeric=" + (i.longValue() == l.longValue()));
        System.out.println("againstPrimitiveLong=" + (i == 1_000L));
    }
}
```

```bash
javac MixedWrapperDemo.java
java MixedWrapperDemo
```

```text
equals=false
numeric=true
againstPrimitiveLong=true
```

Having the same digits `1000` does not mean the wrappers share the same type or the same reference. When designing APIs, standardize on one suitable numeric type to avoid ad-hoc comparisons between different wrapper types.

## 7. `Objects.equals(a,b)`: Null-Safe Handling and Proper `equals`

`java.util.Objects.equals(a,b)` checks whether both references are null or delegates to `a.equals(b)`. It prevents `NullPointerException` when the left-hand variable is null:

```java
import java.util.Objects;

Integer a = null;
Integer b = null;
Integer one = 1;

System.out.println(Objects.equals(a, b)); // true
System.out.println(Objects.equals(a, one)); // false
System.out.println(Objects.equals(Integer.valueOf(500),
                                  Integer.valueOf(500))); // true
```

The snippet above is illustrated inside `main`, with the import at the top of the file. `Objects.equals` **does not automatically convert numeric types**; `Objects.equals(Integer.valueOf(1), Long.valueOf(1L))` is still `false`.

### Complete Example: Null-Safe Comparison Table

**File `WrapperObjectsEqualsDemo.java`:**

```java
import java.util.Objects;

public class WrapperObjectsEqualsDemo {
    public static void main(String[] args) {
        Integer a = null;
        Integer b = null;
        Integer x = Integer.valueOf(500);
        Integer y = Integer.valueOf(500);

        System.out.println("nullNull=" + Objects.equals(a, b));
        System.out.println("nullValue=" + Objects.equals(a, x));
        System.out.println("valueValue=" + Objects.equals(x, y));
        System.out.println("crossType=" + Objects.equals(
                Integer.valueOf(1), Long.valueOf(1L)));
    }
}
```

```bash
javac WrapperObjectsEqualsDemo.java
java WrapperObjectsEqualsDemo
```

```text
nullNull=true
nullValue=false
valueValue=true
crossType=false
```

**Important:** if `null` is invalid data, `Objects.equals` does not replace validation. It treats two nulls as equal; for business rules requiring both fields to hold a number, proactively reject null before comparing.

## 8. `Double` and `Float`: `NaN` and Signed Zero Still Cause Differences

For floating-point wrappers, `equals` does not behave identically to `==` on primitives. This is especially important when testing `NaN` and signed zeros.

### 8.1. `NaN`: Primitive Is Not Equal to Itself, Wrapper `equals` Treats Two NaNs as Equal

```java
System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.valueOf(Double.NaN)
        .equals(Double.valueOf(Double.NaN)));  // true
```

On the first line, the operands are primitive `double`s, so IEEE 754 comparison applies: `NaN == NaN` is always false. The second line calls `Double.equals` on two wrappers; the method relies on bit-representation comparison rules (canonicalizing NaN encodings), so two `NaN` values are considered equal.

Therefore, if you want to check whether a value is `NaN`, use `Double.isNaN(value)` or `Float.isNaN(value)`; never use `== Double.NaN`.

### 8.2. `+0.0` and `-0.0`: Primitives Are Equal, Wrapper `equals` Distinguishes Them

```java
System.out.println(0.0 == -0.0); // true
System.out.println(Double.valueOf(0.0)
        .equals(Double.valueOf(-0.0))); // false
```

The two zeros are equal under primitive numeric comparison, yet they have different sign bits. `Double.equals` distinguishes them, aligning with `Double.hashCode` and the behavior of hash/equality-based collections.

`Double.compare(0.0, -0.0) > 0` is also `true`: the API applies an ordering that distinguishes signed zeros. Do not assume `Double.compare` always matches primitive `==`.

### 8.3. Complete Program

**File `FloatingWrapperEqualityDemo.java`:**

```java
public class FloatingWrapperEqualityDemo {
    public static void main(String[] args) {
        Double nanA = Double.valueOf(Double.NaN);
        Double nanB = Double.valueOf(Double.NaN);
        Double plusZero = Double.valueOf(0.0);
        Double minusZero = Double.valueOf(-0.0);

        System.out.println("primitiveNaN=" + (Double.NaN == Double.NaN));
        System.out.println("wrapperNaN=" + nanA.equals(nanB));
        System.out.println("primitiveZero=" + (0.0 == -0.0));
        System.out.println("wrapperZero=" + plusZero.equals(minusZero));
        System.out.println("compareZero=" + Double.compare(0.0, -0.0));
    }
}
```

```bash
javac FloatingWrapperEqualityDemo.java
java FloatingWrapperEqualityDemo
```

```text
primitiveNaN=false
wrapperNaN=true
primitiveZero=true
wrapperZero=false
compareZero=1
```

Similarly, `Float` has matching rules for `Float.NaN` and signed zeros. Never use `==` as the universal equality criterion for all floating-point cases without considering your goal: numeric comparison, representation identity, or tolerance policy.

## 9. Why Does This Mistake Affect `HashSet` and `HashMap`?

`HashSet` and `HashMap` keys use `equals` along with `hashCode` to detect duplicates; they **do not rely on `==` to compare wrapper values**.

Example:

**File `WrapperCollectionDemo.java`:**

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class WrapperCollectionDemo {
    public static void main(String[] args) {
        Set<Integer> ids = new HashSet<>();
        ids.add(Integer.valueOf(1_000));
        ids.add(Integer.valueOf(1_000));

        Map<Integer, String> byId = new HashMap<>();
        byId.put(Integer.valueOf(1_000), "first");
        byId.put(Integer.valueOf(1_000), "updated");

        System.out.println("setSize=" + ids.size());
        System.out.println("mapSize=" + byId.size());
        System.out.println("value=" + byId.get(Integer.valueOf(1_000)));
    }
}
```

```bash
javac WrapperCollectionDemo.java
java WrapperCollectionDemo
```

```text
setSize=1
mapSize=1
value=updated
```

Even though the wrapper 1000 may be created as distinct objects, they are equal under `Integer.equals`. `HashSet` keeps one element and `HashMap` replaces the value for the key of the same value.

If you write a custom deduplication algorithm using `==` on wrappers, the program may appear to work "correctly" for small values due to caching and then fail on larger inputs. Never rely on caching behavior as a uniqueness check.

## 10. Common Buggy Patterns and Fixes

| Goal | Bug-Prone Pattern | Recommended Approach |
|---|---|---|
| Are two `Integer`s equal in value? | `a == b` | `a.equals(b)` if guaranteed non-null |
| Two wrappers of same type, possibly null? | `a.equals(b)` | `Objects.equals(a,b)` |
| Compare `Integer` ordering | `a == b` | `a.compareTo(b) < 0`, `> 0`, `== 0` |
| Do `Integer` and `Long` have the same value? | `a == b` (compile error) | `a.longValue() == b.longValue()` after null check |
| Wrapper vs primitive | Assuming non-null by default | Validate null before unboxing |
| Check for `Double.NaN` | `x == Double.NaN` | `Double.isNaN(x)` |
| Distinguish `+0.0` and `-0.0` as `Double` | `x.doubleValue() == y.doubleValue()` | `x.equals(y)` or appropriate bit comparison |
| Check if same object instance? | `a.equals(b)` | `a == b` if identity is genuinely the goal |
| Test equality based on `Integer` cache | Asserting `Integer.valueOf(128) == ...` with hardcoded expectation | Test `equals` for value, do not rely on cache |

**Review tip:** whenever you see `==` between two variables typed `Integer`, `Long`, `Double`, or `Boolean`, ask: "Do I need to know if these two variables point to the same reference, or do I need to compare values?" In most numeric business logic, the answer is **value**.

### Do Not Use `new Integer(int)` to Bypass the Cache

Wrapper constructors like `new Integer(10)` have been deprecated and marked for removal in modern Java. Do not use them to force "two wrappers guaranteed to be distinct objects" in production code or ordinary tests. That is also why the examples in this article prefer `Integer.valueOf` and check values with `equals`.

## 11. A Complete Runnable Summary Example

The following program tests a series of differences with outputs **independent of caching outside the guaranteed range**.

**File `WrapperComparisonSummary.java`:**

```java
import java.util.Objects;

public class WrapperComparisonSummary {
    public static void main(String[] args) {
        Integer smallA = Integer.valueOf(127);
        Integer smallB = Integer.valueOf(127);
        Integer largeA = Integer.valueOf(1_000);
        Integer largeB = Integer.valueOf(1_000);

        System.out.println("cache127=" + (smallA == smallB));
        System.out.println("equals1000=" + largeA.equals(largeB));
        System.out.println("numeric1000=" + (largeA == 1_000));

        Integer absent = null;
        System.out.println("nullEquals=" + Objects.equals(absent, null));

        Integer oneInt = Integer.valueOf(1);
        Long oneLong = Long.valueOf(1L);
        System.out.println("crossEquals=" + oneInt.equals(oneLong));
        System.out.println("crossNumeric="
                + (oneInt.longValue() == oneLong.longValue()));

        System.out.println("NaNprimitive=" + (Double.NaN == Double.NaN));
        System.out.println("NaNwrapper=" + Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN)));
        System.out.println("zeroPrimitive=" + (0.0 == -0.0));
        System.out.println("zeroWrapper=" + Double.valueOf(0.0)
                .equals(Double.valueOf(-0.0)));
    }
}
```

```bash
javac WrapperComparisonSummary.java
java WrapperComparisonSummary
```

```text
cache127=true
equals1000=true
numeric1000=true
nullEquals=true
crossEquals=false
crossNumeric=true
NaNprimitive=false
NaNwrapper=true
zeroPrimitive=true
zeroWrapper=false
```

The output `cache127=true` relies on the cache guaranteed by `Integer.valueOf`. The program does not treat the identity of wrapper 1000 as a pass/fail condition, because it is outside the mandatory cache range. `numeric1000` compares an `Integer` with a **primitive** `int` literal, so it unboxes.

## 12. Testing to Catch Wrapper `==` Bugs

Practical tests for projects handling wrappers:

1. **Beyond cache**: verify equality of `Integer.valueOf(1000)` and another `Integer` of the same value via `equals`, without hardcoding expectations for `==`.
2. **Cache boundary values**: `127`, `128`, `-128`, `-129` help reveal the difference between identity and value; cases outside the cache range must be tested against the contract, not machine-specific behavior.
3. **Null**: `null == null`, `Objects.equals(null, value)`, and null unboxing when compared against a primitive to confirm proper error handling.
4. **Different types**: `Integer.valueOf(1).equals(Long.valueOf(1))` is `false`, while numeric comparison via a common type can be `true`.
5. **Special floating-point values**: `NaN`, `+0.0`, `-0.0` with primitive `==` and wrapper `equals`.
6. **Collections**: two out-of-cache wrappers of equal value are properly deduplicated in `HashSet`/`HashMap` keys via `equals/hashCode`.
7. **Independence from extended JVM caches**: tests should run reliably across different JDKs without falsely expecting `Integer.valueOf(128) == Integer.valueOf(128)` to be `false`.

When testing null variants in code that performs unboxing, use tests confirming that null is **properly rejected or handled before unboxing**. Never write unit tests comparing only a few values inside the cache range and conclude correctness for all `Integer`s.

## 13. Self-Check Exercises with Solutions

1. **What can `Integer a = 127, b = 127; a == b` evaluate to?**  
   `true` by the boxing/cache guarantee for values in `-128..127`. However, this is still a reference comparison.

2. **Is `Integer a = 1_000, b = 1_000; a == b` always `false`?**  
   Cannot be guaranteed. The cache can be expanded; never use `==` to compare values. `a.equals(b)` returns `true`.

3. **Why does `Integer a = null; a == 0` throw an exception while `a == null` does not?**  
   `a == 0` requires unboxing `a` to `int`; null cannot be unboxed. `a == null` compares references.

4. **What does `Integer.valueOf(3).equals(Long.valueOf(3L))` return?**  
   `false`; the two objects belong to different wrapper classes.

5. **Can you write `Integer i; Long l; i == l` directly?**  
   No; two final wrappers of different types cannot be compared with reference `==` here. If needed, use numeric comparison with safe type conversion.

6. **What do `Double.NaN == Double.NaN` and `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` return?**  
   `false` and `true` respectively, because primitive `double` and `Double.equals` follow different contracts.

7. **What do `0.0 == -0.0` and `Double.valueOf(0.0).equals(Double.valueOf(-0.0))` return?**  
   `true` and `false` respectively; wrapper `equals` distinguishes the sign bit of zero.

8. **Is `Objects.equals(null,null)` `true`?**  
   Yes. However, if a numeric field is required to have a value, separate validation is needed.

## 14. Conclusion and References

When both variables are **wrappers**, `==` can check **reference identity**, not numeric equality. Correct results for small values can be due to **caching**, and comparing a wrapper with a primitive **unboxes**. To test whether **two wrappers of the same type are equal in value**, use `equals` or `Objects.equals` if null support is needed; use `compareTo` or appropriate comparison APIs when ordering is needed. With `Double`/`Float`, clarify your goal when encountering `NaN` or signed zero.

Official documentation:

- [Java 21 — `Integer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html)
- [Java 21 — `Double`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
- [Java 21 — `Objects`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html)
- [Java Language Specification — Equality Operators, §15.21](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.21)
- [Java Language Specification — Boxing Conversion, §5.1.7](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7)
