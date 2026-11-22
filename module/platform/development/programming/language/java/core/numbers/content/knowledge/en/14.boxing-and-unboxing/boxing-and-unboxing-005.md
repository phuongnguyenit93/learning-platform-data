# Wrapper Caching and Why It Must Not Be Used as an Identity Contract in Java

## 1. The problem: two objects with the same value are not necessarily the same object

When working with `Integer`, `Long`, `Short`, `Byte`, and other wrapper classes, there are two **different** questions:

1. **Do two objects represent the same value?** Normally use `equals` per the wrapper class contract, or use arithmetic operators after unboxing if `null` has been checked.
2. **Do two reference variables point to the exact same object?** With two references, `==` checks *reference identity*.

Java has a **wrapper caching** mechanism: some boxing operations or `valueOf` calls can return a previously used object instead of allocating a new one. Consequently, `==` between certain pairs of wrappers with small values can return `true`, whereas other values may return `false`.

The most important takeaway of this lesson:

> **Wrapper caching is not a numeric identity contract.** Do not use `==` between two wrapper references to decide if they have the same numeric value, and do not use wrappers as synchronization locks relying on identity.

Basic example:

```java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);
System.out.println(a == b);      // true: within the guaranteed cache range

Integer x = Integer.valueOf(200);
Integer y = Integer.valueOf(200);
System.out.println(x.equals(y)); // true: same Integer type and same value
```

Do not conclude that `x == y` is **always** `false`. Caching additional values outside the guaranteed range depends on the JVM implementation and configuration. The reliable way to check value equality is `x.equals(y)`.

## 2. Wrappers are objects; boxing and unboxing are conversions

Java has six familiar numeric wrappers:

| Primitive | Wrapper | Example created from primitive |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.valueOf((byte) 12)` |
| `short` | `Short` | `Short.valueOf((short) 12)` |
| `int` | `Integer` | `Integer.valueOf(12)` |
| `long` | `Long` | `Long.valueOf(12L)` |
| `float` | `Float` | `Float.valueOf(12.0f)` |
| `double` | `Double` | `Double.valueOf(12.0)` |

Each wrapper is a `final`, immutable class extending `Number`. A wrapper object has **identity** like any reference object; however, the numeric value it holds is what usually matters for business logic.

**Boxing** turns a primitive into a wrapper:

```java
int primitive = 42;
Integer boxed = primitive; // autoboxing; semantically equivalent to Integer.valueOf
```

**Unboxing** retrieves a primitive from a wrapper:

```java
Integer boxed = Integer.valueOf(42);
int primitive = boxed; // invokes the corresponding value conversion
```

Java automatically inserts boxing/unboxing in many places, including assignments, arithmetic operations, certain comparisons, and collection operations. Those conversions can make code look as if it is only manipulating numbers, even though object references and `null` risks exist in reality.

The `valueOf` methods are the standard choice for creating wrappers. Constructors like `new Integer(...)` and `new Long(...)` have been deprecated and marked for removal in modern Java; you should not construct new objects merely to force identity checks. If business logic genuinely requires an entity with its own identity, define an entity class with an appropriate ID.

## 3. What does wrapper caching actually guarantee?

### 3.1. Guaranteed cache ranges

The `valueOf` factory methods of the integer wrapper group commit to reusing objects in the following ranges:

| Wrapper | Range with guaranteed cached objects via `valueOf` | Notes |
| --- | --- | --- |
| `Byte` | Entire `byte` range: `-128..127` | Every `byte` value falls in this range |
| `Short` | `-128..127` | Additional values may be cached |
| `Integer` | `-128..127` | Additional values may be cached |
| `Long` | `-128..127` | Additional values may be cached |
| `Float` | **No cache range guarantee like above** | Do not infer identity from equal values |
| `Double` | **No cache range guarantee like above** | Do not infer identity from equal values |

With `Byte.valueOf`, all valid values fall in `-128..127`. With `Short.valueOf`, `Integer.valueOf`, and `Long.valueOf`, values in that range are returned from the cache as promised by the API. Outside that range, whether two calls return the same object **is not a guaranteed contract**.

```java
Byte a = Byte.valueOf((byte) -128);
Byte b = Byte.valueOf((byte) -128);
// a == b is guaranteed true

Short c = Short.valueOf((short) 127);
Short d = Short.valueOf((short) 127);
// c == d is guaranteed true

Long e = Long.valueOf(127L);
Long f = Long.valueOf(127L);
// e == f is guaranteed true
```

There are other wrappers such as `Boolean` and `Character`, though they do not belong to the six numeric classes above. `Boolean.valueOf` returns the `TRUE` or `FALSE` instances; `Character.valueOf` guarantees caching characters from `'\u0000'` to `'\u007f'`. These examples emphasize that **each API has its own contract**; there is no blanket rule that “all wrappers cache `-128..127`”.

### 3.2. Boxing rules in the Java specification

Beyond the `valueOf` API commitment, the Java specification defines cases where boxing results share identity, notably constant expressions of types `byte`, `short`, `int`, and `long` in `-128..127`, `char` in `0..127`, and `boolean` values.

However, **do not reverse-interpret** this to mean that every boxing of any expression, at any value or for any wrapper, has stable identity. The specification permits implementations to share additional objects in some cases, and implementation optimizations can change.

A common example:

```java
Integer a = 100;
Integer b = 100;
System.out.println(a == b); // true within the guaranteed range

Integer x = 200;
Integer y = 200;
// Do not rely on x == y to determine equal values
```

The second case may create two objects or use an extended cache. **An application must make the exact same business decision across every valid JVM**, even if identity outcomes differ.

### 3.3. The cache is not a “pool of objects with numeric IDs”

Caching reduces allocations of commonly occurring wrappers, especially small values. Yet primitive values such as `42` have no identity; identity is only a property of a specific wrapper object reference.

Do not treat the cache as a general *interning* mechanism that can replace:

- record identifiers, user IDs, or business keys;
- application-designed singleton mechanisms;
- dedicated synchronization lock sets;
- `equals` and `hashCode` relationships in `HashMap`/`HashSet`.

Using wrappers to represent IDs is completely valid (e.g., `Map<Integer, Customer>`), **as long as values are compared with `equals`**, not because two `Integer` references must point to the same instance.

## 4. `==` between two wrappers vs. `==` when a primitive is involved

The same `==` symbol can lead to two different mechanisms, depending on **the static types of the operands**.

### Both operands are wrapper references

```java
Integer a = Integer.valueOf(200);
Integer b = Integer.valueOf(200);

boolean sameObject = (a == b);  // reference comparison
boolean sameValue = a.equals(b); // true
```

`sameObject` should not be used to decide `sameValue`. If `null` is possible, calling `a.equals(b)` when `a == null` causes a `NullPointerException`.

### One side wrapper, one side primitive

```java
Integer boxed = Integer.valueOf(200);
int raw = 200;

System.out.println(boxed == raw); // true: boxed is unboxed, then int comparison
```

When the context applies *binary numeric promotion*, Java unboxes the wrapper to perform a numeric value comparison. Thus `boxed == raw` can evaluate to true even when `boxed == anotherBoxed` has no guarantee of being true.

Be careful with `null`:

```java
Integer missing = null;
// System.out.println(missing == 0); // Throws NullPointerException due to unboxing
```

Do not “fix” a wrapper comparison by changing one operand to a primitive if the input can be `null` without specifying how missing data is handled.

### Two `null` references

```java
Integer first = null;
Integer second = null;

System.out.println(first == second); // true: both are null
```

`true` here only means both are the `null` reference. It does **not** mean two numeric values exist and are equal. If `null` must be interpreted as “missing data”, state a separate rule.

## 5. How to check values accurately and safely

### 5.1. Two wrappers of the same type, guaranteed non-`null`

```java
Integer left = Integer.valueOf(200);
Integer right = Integer.valueOf(200);

boolean sameValue = left.equals(right); // true
```

`Integer.equals` compares the `int` value and corresponding wrapper type; it does not depend on how many objects are cached.

### 5.2. Wrappers that may be `null`

Use `java.util.Objects.equals`:

```java
import java.util.Objects;

Integer left = null;
Integer right = Integer.valueOf(200);

System.out.println(Objects.equals(left, right)); // false
System.out.println(Objects.equals(null, null));  // true
```

`Objects.equals(a, b)` returns `true` when both references are `null`, or when `a != null` and `a.equals(b)`. This is a **null-aware object comparison policy**, not a check for “two valid numbers are equal”. If the business domain forbids `null`, reject it first.

### 5.3. When primitive numeric comparison is desired

```java
Integer left = Integer.valueOf(200);
Integer right = Integer.valueOf(200);

if (left != null && right != null
        && left.intValue() == right.intValue()) {
    System.out.println("Same numeric int");
}
```

Explicit unboxing makes the value comparison clear. This is a good approach when subsequent calculations genuinely need `int` and `null` checks are already complete.

### 5.4. Two wrappers of *different classes*

`Integer.valueOf(10).equals(Long.valueOf(10L))` is `false`: the `equals` contract of integer wrappers requires the same wrapper type and the same value.

```java
Integer a = Integer.valueOf(10);
Long b = Long.valueOf(10L);
System.out.println(a.equals(b)); // false
```

If business logic wants two numbers of different types to be considered equivalent in mathematical value, define a **lossless** normalization before comparing. For example, with finite `Integer` and `Long`, `a.longValue() == b.longValue()` preserves every `int` value. Do not blindly convert every `Number` to `double`, because multiple distinct `long` values can round to the same `double`.

### 5.5. `Float` and `Double` have special contracts

`Double.equals` and `Float.equals` do not match the primitive `==` operator for special values:

```java
System.out.println(Double.NaN == Double.NaN); // false
System.out.println(
        Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN))); // true

System.out.println(+0.0 == -0.0); // true
System.out.println(
        Double.valueOf(+0.0).equals(Double.valueOf(-0.0))); // false
```

Similarly for `Float`: wrapper `equals` treats NaN values as equal and distinguishes `+0.0f`/`-0.0f`. This is the class contract, **not** a consequence of caching.

When approximate comparison is needed for floating-point results with rounding error, define a dedicated tolerance and NaN/infinity policy. An “approximately equal” relation cannot implicitly replace `equals` for collection keys because it may not be transitive.

## 6. Runnable example on Java 17

Save the following code to `WrapperCacheDemo.java`:

```java
import java.util.Objects;

public class WrapperCacheDemo {
    public static void main(String[] args) {
        Integer smallA = Integer.valueOf(127);
        Integer smallB = Integer.valueOf(127);
        System.out.println("Integer 127 same object: " + (smallA == smallB));

        Byte byteA = Byte.valueOf((byte) -128);
        Byte byteB = Byte.valueOf((byte) -128);
        System.out.println("Byte -128 same object: " + (byteA == byteB));

        Short shortA = Short.valueOf((short) 127);
        Short shortB = Short.valueOf((short) 127);
        System.out.println("Short 127 same object: " + (shortA == shortB));

        Long longA = Long.valueOf(127L);
        Long longB = Long.valueOf(127L);
        System.out.println("Long 127 same object: " + (longA == longB));

        Integer largeA = Integer.valueOf(200);
        Integer largeB = Integer.valueOf(200);

        // Do not print largeA == largeB: identity outside the guaranteed cache
        // is not a stable result to rely on for business rules.
        System.out.println("Integer 200 equals: "
                + largeA.equals(largeB));
        System.out.println("Integer 200 primitive values: "
                + (largeA.intValue() == largeB.intValue()));

        int primitive = 200;
        System.out.println("Wrapper vs primitive: "
                + (largeA == primitive));

        System.out.println("Integer vs Long equals: "
                + Integer.valueOf(10).equals(Long.valueOf(10L)));

        Integer missing = null;
        System.out.println("Objects.equals(null, 200): "
                + Objects.equals(missing, largeA));

        System.out.println("Double NaN wrapper equals: "
                + Double.valueOf(Double.NaN)
                        .equals(Double.valueOf(Double.NaN)));
        System.out.println("Double signed zero wrapper equals: "
                + Double.valueOf(0.0)
                        .equals(Double.valueOf(-0.0)));
    }
}
```

Compile/run:

```bash
javac WrapperCacheDemo.java
java WrapperCacheDemo
```

Output:

```text
Integer 127 same object: true
Byte -128 same object: true
Short 127 same object: true
Long 127 same object: true
Integer 200 equals: true
Integer 200 primitive values: true
Wrapper vs primitive: true
Integer vs Long equals: false
Objects.equals(null, 200): false
Double NaN wrapper equals: true
Double signed zero wrapper equals: false
```

The reference checks in the program **only use guaranteed cache ranges**. The program deliberately avoids depending on the outcome of `largeA == largeB`, so the output carries the same meaning across JVMs compliant with the API contract. The remainder checks values via `equals` or primitives after explicit unboxing.

## 7. Why not use wrappers as synchronization locks?

Example of harmful code:

```java
Integer lock = Integer.valueOf(42);
synchronized (lock) {
    // Do not synchronize on a wrapper object!
}
```

Some wrappers are cached or shared; unrelated code can receive the exact **same reference**. Consequences can include unexpected lock contention, delays, or very hard-to-find synchronization bugs. Wrappers are also regarded by Java as **value-based classes**: developers are advised not to rely on identity for synchronization. In modern JDKs, the compiler may warn when attempting `synchronized` on a wrapper object.

To lock and protect an instance's state, create a dedicated lock object owned by the class itself:

```java
public final class SafeCounter {
    private final Object lock = new Object();
    private int count;

    public void increment() {
        synchronized (lock) {
            count++;
        }
    }

    public int get() {
        synchronized (lock) {
            return count;
        }
    }
}
```

Here `lock` has its own dedicated identity for synchronization; it is not shared due to small-number caching. If a concurrent counter is required, `AtomicInteger` is also a meaningful option depending on the problem.

**Do not use `System.identityHashCode(integer)` as a business ID.** That value depends on object identity, not the numeric value or a persistent identifier; it can vary across runs and is not guaranteed unique.

## 8. How does caching affect performance?

Wrapper caching is primarily an optimization to **reuse objects** for frequently occurring values. However, do not infer:

- That every autoboxing allocates a new object: many cases use caching or JVM optimizations that eliminate allocations.
- That `valueOf` returns the same object for every value: outside the guaranteed range, there is no such general commitment.
- That using `Integer` is as efficient as primitive `int` in every situation: a wrapper is an object reference, can be `null`, requires boxing/unboxing, and can increase memory or operational overhead.
- That expanding the cache improves performance for every application: effectiveness depends on data, JVM, GC, JIT optimizations, and access patterns; you must benchmark under real workloads.

Example:

```java
Integer count = 0;
count++; // unbox -> add an int -> box -> assign new reference
```

`Integer` objects are immutable: incrementing **does not mutate the old instance**. If the new value falls in the cache region, the JVM may use a reused instance; if outside, the implementation may differ.

For pure arithmetic counting in a hot loop, prefer primitives:

```java
int sum = 0;
for (int i = 0; i < 1000; i++) {
    sum += i;
}
```

When you need `List<Integer>`, `Map<String, Long>`, or generics accepting reference types, wrappers are the right tool, but distinguish performance evaluation from correctness.

## 9. Extended caches and portability

A JDK/VM may have its own configuration or optimizations to extend the cached `Integer` range. This explains why the same test snippet:

```java
Integer x = Integer.valueOf(200);
Integer y = Integer.valueOf(200);
boolean sameReference = x == y;
```

can return `true` in one environment and `false` in another. That result **does not prove two values are different**, nor is it a signal to branch logic on.

Some implementations can optimize boxing through escape analysis or VM optimizations. Do not turn identity measurements, `identityHashCode`, or allocation counts in a single run into an API contract for equality.

Sustainable design rules:

1. Need *numeric equality* → `equals`, `Objects.equals`, or primitive comparison when safe to unbox.
2. Need entity identity → keep a separate immutable ID and define `equals`/`hashCode` according to business logic.
3. Need true object identity → use an object with clear ownership and lifecycle, not a numeric wrapper.
4. Need synchronization → use a private lock (`new Object()`), atomic primitives, or an appropriate synchronization mechanism.
5. Need optimization → measure performance and adopt suitable data structures without trading correctness to depend on caching.

## 10. Issues with collections and checks

### `HashMap`/`HashSet` use `equals` and `hashCode`

Example:

```java
import java.util.HashSet;
import java.util.Set;

Set<Integer> ids = new HashSet<>();
ids.add(Integer.valueOf(200));

System.out.println(ids.contains(Integer.valueOf(200))); // true
```

The two `valueOf(200)` calls **do not need** to return the same reference. `HashSet` uses `Integer`'s `hashCode`/`equals` contract to find the right element.

Conversely, `IdentityHashMap` intentionally compares keys by reference, so wrappers are unsuitable if the intent is identification by numeric value. Even if tests show small values working due to caching, logic will easily fail once values exceed the cache range or implementations change.

### Approximate comparisons are not `equals`

For `Float`/`Double`, if a tolerance is needed due to calculation errors, use a dedicated criterion for numeric checks. A criterion like `Math.abs(a-b) < epsilon` is not a general equivalence relation: it may fail transitivity and does not replace the `hashCode` contract.

### Auto-unboxing in collections

When retrieving data from `List<Integer>`:

```java
Integer nullableId = null;
// int id = nullableId; // Throws NullPointerException
```

Regardless of caching, `null` is a valid reference for a wrapper and requires a handling policy. `Objects.equals` only helps compare safely with `null`; it does not guarantee every passed value is valid according to the business domain.

## 11. Common errors and fixes

| Error | Why it is wrong | Correct approach |
| --- | --- | --- |
| `Integer a=200, b=200; if (a==b)` | Reference comparison; identity outside cache is unstable | `a.equals(b)` if non-null |
| Thinking all wrappers cache `-128..127` | `Float`/`Double` have no cache guarantee like integer wrappers | Read each type's API contract |
| Assuming outside `127`, `==` is always false | JVM may cache additional values | Do not rely on identity |
| Using `synchronized(Integer.valueOf(1))` | Can accidentally lock on a shared object; wrappers are value-based | Application-managed private lock |
| `Integer x=null; x==0` | Auto-unboxes `null` causing `NullPointerException` | Check `null` first |
| Comparing `Integer(10)` with `Long(10)` via `equals` expecting `true` | `equals` requires matching wrapper type | Choose a value-preserving conversion and unified policy |
| Treating `Double.equals` like `double ==` for NaN/±0 | The two APIs have different contracts | Use the right kind of comparison |
| Creating wrappers with constructors to get separate identity | Deprecated API; value-based wrappers are unfit as identity entities | Design a dedicated entity class |
| Using `IdentityHashMap<Integer, ...>` to look up keys by value | Identity differs from equality; caching only hides bugs for some numbers | Use `HashMap<Integer, ...>` |
| Using `System.identityHashCode(wrapper)` as a persistent code | Not a numeric ID, not guaranteed unique | Use an explicit domain ID |
| Assuming immutable `Integer` can `++` in place | `++` unboxes, computes, and boxes a new value object | Use primitives/atomics as required |
| Seeing `a==b` true and concluding numeric comparison is always right | Might accidentally hit the cache | Write tests for values inside and outside cache; verify `equals` |

## 12. Exercises with explanations

**Exercise 1.** Predict:

```java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);
boolean same = a == b;
```

**Answer:** `true`. This is within the cache range committed by `Integer.valueOf`. However, using `equals` remains the right choice to express “equal by value”.

**Exercise 2.** If `127` is replaced with `200`, is `same` guaranteed to be `false`?

**Answer:** No. `Integer.valueOf` may cache additional values outside `-128..127`; the identity outcome is not guaranteed. `a.equals(b)` is always `true` for two `Integer`s with the same value 200.

**Exercise 3.** Why is `Integer.valueOf(200) == 200` `true` even though comparing two `Integer` references can differ?

**Answer:** One operand is primitive `int`, so the wrapper is unboxed and **numeric values** are compared; this is no longer comparing two references.

**Exercise 4.** What happens when running `Integer a = null; System.out.println(a == 0);`?

**Answer:** `NullPointerException` when Java tries to unbox `a` to compare with primitive `0`.

**Exercise 5.** What does `Objects.equals(null, null)` return? Does it mean two valid numeric values are equal?

**Answer:** `true` under the nullable reference comparison contract; no, both indicate the absence of a numeric object. Business logic must distinguish missing data from 0.

**Exercise 6.** Are two `Long.valueOf(127L)` instances guaranteed to be the same reference? Should this be used as identification logic?

**Answer:** The `Long.valueOf` cache contract guarantees sharing in `-128..127`. However, wrapper identity should not be used as an identifier; instead compare by value or model a separate business ID.

**Exercise 7.** Why is using `Integer.valueOf(42)` as a monitor for `synchronized` dangerous?

**Answer:** Cached values can cause unrelated parts of code to receive the same object. Locks become unintentionally shared, and wrappers are value-based so they are unsuitable for identity-based synchronization. Use a private lock object.

**Exercise 8.** When a `HashSet<Integer>` contains `200`, why is `contains(Integer.valueOf(200))` true without relying on caching?

**Answer:** Collections match based on `hashCode`/`equals`, not reference `==`. Two `Integer`s with the same value have compatible hash/equality contracts.

**Conclusion:** Wrapper caching is an optimization detail with **certain specific range guarantees**, not a value identification mechanism. Read operand types accurately to understand `==`; use `equals` or `Objects.equals` for wrappers (with a `null` policy), use primitives when computing, and always use dedicated objects when identity or synchronization locks are needed.