# Wrapper Object Caching and Why Not to Rely on `==` — Java 17+

## 1. Core Question: Same Number Means Same Object?

Java has the primitive type `int` and its corresponding wrapper class `Integer`. Two `Integer` variables can hold **the same numeric value** yet **not necessarily reference the same object**.

~~~java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);

System.out.println(a == b);      // true: guaranteed cache range
System.out.println(a.equals(b)); // true: same Integer value
~~~

The result `a == b` in this example is `true` because `Integer.valueOf` guarantees object reuse for the range **-128 to 127**. Now change the value to `1000`:

~~~java
Integer x = Integer.valueOf(1000);
Integer y = Integer.valueOf(1000);

System.out.println(x.equals(y)); // true: always equal by value
// Do not rely on (x == y): identity at this value is not guaranteed.
~~~

**There is no fixed expected output for `x == y` in the 1000 example.** Some JVMs/configurations cache larger numbers; others do not. Code appearing to work "correctly" on the current machine does not turn identity comparison into a guaranteed value comparison across all Java environments.

**Conclusion before diving deeper:** to check **whether two wrappers have equal values**, use `equals` or `Objects.equals` depending on nullability. Only use `==` on two references when **the real intent is to check whether they are the same object**.

## 2. Why Can Wrappers Be Cached?

Wrappers are **immutable** reference objects containing a primitive value; for example, `Integer` wraps `int`, and `Character` wraps `char`. Because the object cannot change its value after creation, Java can share wrappers for frequently used values without altering the meaning of the value.

~~~java
int primitive = 10;
Integer wrapper = primitive; // Autoboxing.
System.out.println(wrapper.equals(10)); // true: value comparison.
~~~

`int` carries no reference identity, whereas `Integer` can be `null` and used in `List<Integer>`. Primitive/wrapper pairs and boxing rules were covered in the overview lesson; this lesson focuses on **cache ranges, identity guarantees, and why not to use caching in business logic**.


## 3. What Is Wrapper Object Caching?

When representing values that occur very frequently, a wrapper class can **reuse existing immutable objects**. This is called a *wrapper cache*.

Conceptual model:

~~~mermaid
flowchart LR
    A["Integer a = 127"] -->|"autoboxing"| C["Integer instance: 127"]
    B["Integer b = 127"] -->|"autoboxing"| C
    X["Integer x = 1000"] -->|"identity outside guaranteed range"| D["Implementation-dependent object"]
    Y["Integer y = 1000"] -->|"identity outside guaranteed range"| E["Implementation-dependent object"]
~~~

The arrows to two separate objects for the value 1000 only emphasize that **identity cannot be inferred from value**: depending on configuration, those two variables *may* reference the same object or different objects. The diagram must not be used to claim there are always two objects for 1000.

**Why is caching useful?** Wrapper objects are immutable; reusing one object for a given value cannot alter that object's contents. Sharing objects can reduce the need to allocate new objects in certain situations, but **caching is an implementation mechanism detail with a specific guaranteed scope**, not a value-comparison operator for applications.

## 4. Guaranteed Identity Ranges and What Is Not Guaranteed

In Java 17, commonly used boxed values have a **guaranteed identity range**. The corresponding factory methods specify this in the API specification:

| Wrapper | Guaranteed Reused Values on Boxing/`valueOf` | Notes |
|---|---|---|
| `Byte` | Entire `byte` range: -128..127 | Full Byte domain |
| `Short` | -128..127 | Numbers outside this range may additionally be cached |
| `Integer` | -128..127 | Familiar cache range |
| `Long` | -128..127 | Do not extrapolate to all `long` values |
| `Character` | U+0000..U+007F | First 128 UTF-16 code units |
| `Boolean` | `true` and `false` | The two canonical instances `Boolean.TRUE`/`FALSE` |
| `Float`, `Double` | No similar guaranteed numeric value cache range for all boxing | Do not rely on floating-point wrapper identity |

Examples with predictable results:

~~~java
Integer x = Integer.valueOf(-128);
Integer y = Integer.valueOf(-128);
System.out.println(x == y); // true

Character c1 = Character.valueOf('A');
Character c2 = Character.valueOf('A');
System.out.println(c1 == c2); // true

Long l1 = Long.valueOf(127L);
Long l2 = Long.valueOf(127L);
System.out.println(l1 == l2); // true
~~~

**Understand this carefully:** for `Integer.valueOf(128)` or `Long.valueOf(1000L)`, Java may use an extended cache; you are **not guaranteed true or false** when comparing two independent boxing results with `==`. Some JVM configurations have an option to expand the `Integer` cache, but a configuration setting must never become a correctness condition for business logic.

**Do not create wrappers via constructors to try to "force two objects".** Numeric wrapper constructors such as `new Integer(...)` have been deprecated for removal in modern Java. `valueOf`, autoboxing, and appropriate content-comparison APIs are the standard approach.

## 5. `==` Checks Identity, `equals` Checks Content

For **two expressions both having reference type `Integer`**, the `==` operator checks whether they point to the same object:

~~~java
Integer first = Integer.valueOf(1000);
Integer alias = first;
Integer second = Integer.valueOf(1000);

System.out.println(first == alias); // true: alias assignment does not create another object
System.out.println(first.equals(second)); // true: same value 1000
~~~

Do not print `first == second` with a fixed expected output because Java does not guarantee identity for the value 1000.

Distinguish the comparisons:

| Expression | Meaning |
|---|---|
| `a == b` with two `int`s | Compares primitive values |
| `a == b` with two `Integer`s | Compares reference identity |
| `a.equals(b)` with non-null `Integer` | Compares values of two `Integer`s |
| `Objects.equals(a, b)` | Compares equality and handles null cases |
| `a.compareTo(b) == 0` with non-null `Integer` | Compares numeric order; result is 0 when equal in value |

`Integer.equals` only checks whether the other `Integer` wrapper has the same value; it does not automatically convert different numeric types into `Integer`:

~~~java
Integer n = Integer.valueOf(5);
Long m = Long.valueOf(5L);
System.out.println(n.equals(m)); // false
~~~

This is due to **different wrapper types**, not caching.

## 6. `==` Between Wrapper and Primitive: Can Be Numeric Comparison

Consider:

~~~java
Integer boxed = Integer.valueOf(1000);
int primitive = 1000;

System.out.println(boxed == primitive); // true
~~~

**Why is it true even though 1000 is outside the guaranteed cache range?** One operand has type `int`, so Java **unboxes** `boxed` and compares two primitive values. This is not reference identity.

This differs markedly from:

~~~java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);
// a == b is reference comparison: do not use to check numeric equality.
~~~

Therefore, saying "`==` with Integer is always wrong" is also inaccurate. You must examine **the types of both operands**:

- `Integer == Integer`: compares references.
- `Integer == int`: unboxes then compares numeric values, provided the wrapper is non-null.
- `int == int`: compares numeric values.
- `Integer.equals(Integer)`: compares values as defined by the `Integer` class.

**Null trap:** if `boxed == null`, the expression `boxed == primitive` throws `NullPointerException` during unboxing. Conversely, `boxed == null` is a safe null-reference check.

## 7. Null Is Not a Cached Value

An `Integer` variable can hold `null`, which is distinct from an `Integer.valueOf(0)` object. Comparing `maybe == null` does not unbox; whereas `maybe == 0` can unbox and throw `NullPointerException`:

~~~java
Integer maybe = null;
System.out.println(maybe == null); // true.
System.out.println(java.util.Objects.equals(maybe, (Integer) null)); // true.
~~~

`Objects.equals(a,b)` handles both being null according to equality semantics; however, it does not replace validation if business rules require a value to be present. Caching a wrapper does not turn a null reference into a "cached zero", and does not change NPE rules on unboxing.


## 8. Caching Does Not Mean Wrappers Are Mutable

Standard wrappers such as `Integer`, `Long`, and `Character` are **immutable**. When sharing a cached object, changing one variable cannot modify the "value inside the cached object" to affect others.

~~~java
Integer before = Integer.valueOf(5);
Integer count = before;
count++;

System.out.println(before); // 5
System.out.println(count);  // 6
~~~

Semantically, `count++` performs **unbox → add 1 → box → reassign variable `count`**, without modifying the old object. The variable `before` still holds 5.

~~~java
final Integer limit = Integer.valueOf(5);
// limit++; // Compile error: ++ requires reassigning a final variable
~~~

If you genuinely need a mutable counter shared across components, an `Integer` wrapper does not fill that role. Design an object with mutable state, or use `AtomicInteger` when appropriate for concurrency requirements.

## 9. Collections Use `equals`, Not Caching

Standard collections use the `equals` and `hashCode` contract to look up elements/keys.

~~~java
import java.util.List;
import java.util.Map;

Integer key1 = Integer.valueOf(1000);
Integer key2 = Integer.valueOf(1000);

List<Integer> list = List.of(key1);
Map<Integer, String> map = Map.of(key1, "found");

System.out.println(list.contains(key2)); // true
System.out.println(map.get(key2));       // found
~~~

Here the value `1000` is outside the guaranteed cache range, **yet** `List.contains` and `Map.get` still work properly according to `Integer` equality. They do not compare two references using `==`.

**Intentional exception:** `IdentityHashMap` uses identity (`==`) for keys, so it is not equivalent to `HashMap` in business logic that requires value-based equality. Do not switch to `IdentityHashMap` just to optimize or because its name contains "map".

Treat choosing a collection as choosing a **comparison contract**, not choosing a way to exploit caching.

## 10. Do Not Predict Allocations or Performance from Caching

Not every autoboxing operation necessarily creates a new object; nor does every wrapper outside the cache range necessarily allocate a new object. The JVM may use caching or perform internal optimizations, while program semantics must remain true to Java.

~~~java
Integer a = 1000;
Integer b = 1000;
// Cannot use (a == b) as a reliable measure of allocation,
// and cannot rely on its result to decide whether a and b have the same value.
~~~

**Mistakes to avoid:**

- Relying on `System.identityHashCode(a)` to claim two objects have the same address; an identity hash is not a memory address and can collide across different objects.
- Printing `a.toString()` and comparing display strings to decide whether two references are identical.
- Switching to `int` solely to avoid caching without considering `null`.
- Writing business logic that depends on the result of `Integer.valueOf(128) == Integer.valueOf(128)`.
- Drawing conclusions about speed or memory usage from a few manual measurements without warm-up.

In loops performing repeated numeric calculations, **primitive `int`/`long` is usually the clearer default choice** when nullability or generics are not needed. When measuring Java performance is necessary, use a proper benchmarking tool (such as JMH) and measure on realistic data.

## 11. Complete, Standalone Runnable Java 17 Program

Create the file with the exact name **`WrapperCacheDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class WrapperCacheDemo {
    private WrapperCacheDemo() {}

    public static void main(String[] args) {
        Integer small1 = Integer.valueOf(127);
        Integer small2 = Integer.valueOf(127);
        System.out.println("Integer cached 127=" + (small1 == small2));

        Byte byte1 = Byte.valueOf((byte) 127);
        Byte byte2 = Byte.valueOf((byte) 127);
        System.out.println("Byte cached 127=" + (byte1 == byte2));

        Short short1 = Short.valueOf((short) -128);
        Short short2 = Short.valueOf((short) -128);
        System.out.println("Short cached -128=" + (short1 == short2));

        Long long1 = Long.valueOf(127L);
        Long long2 = Long.valueOf(127L);
        System.out.println("Long cached 127=" + (long1 == long2));

        Character char1 = Character.valueOf('A');
        Character char2 = Character.valueOf('A');
        System.out.println("Character cached A=" + (char1 == char2));

        Boolean bool1 = Boolean.valueOf(true);
        Boolean bool2 = Boolean.valueOf(true);
        System.out.println("Boolean shared true=" + (bool1 == bool2));

        Integer large1 = Integer.valueOf(1000);
        Integer large2 = Integer.valueOf(1000);
        Integer alias = large1;
        // Do not use large1 == large2: identity outside guaranteed cache range.
        System.out.println("large equality=" + large1.equals(large2));
        System.out.println("large compareTo=" + (large1.compareTo(large2) == 0));
        System.out.println("large alias identity=" + (large1 == alias));
        System.out.println("wrapper vs int=" + (large1 == 1000));

        Integer missing = null;
        System.out.println("null check=" + (missing == null));
        System.out.println("two nulls equal="
                + Objects.equals(missing, (Integer) null));
        System.out.println("null vs value=" + Objects.equals(missing, large1));
        try {
            System.out.println("null vs primitive=" + (missing == 0));
        } catch (NullPointerException ex) {
            System.out.println("null unboxing=NullPointerException");
        }

        Integer previous = Integer.valueOf(5);
        Integer incremented = previous;
        incremented++;
        System.out.println("previous wrapper=" + previous);
        System.out.println("incremented wrapper=" + incremented);

        List<Integer> list = List.of(large1);
        Map<Integer, String> map = Map.of(large1, "found");
        System.out.println("list contains equal wrapper=" + list.contains(large2));
        System.out.println("map lookup equal wrapper=" + map.get(large2));

        Integer numericFive = Integer.valueOf(5);
        Long longFive = Long.valueOf(5L);
        System.out.println("cross-class equals=" + numericFive.equals(longFive));
    }
}
~~~

**Requirements:** JDK 17+ and terminal in the directory containing the file. The example requires no Maven/Gradle or libraries outside the JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 WrapperCacheDemo.java
java -cp . WrapperCacheDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\WrapperCacheDemo.java
java -cp . WrapperCacheDemo
~~~

**Exact expected output, independent of extended caching:**

~~~text
Integer cached 127=true
Byte cached 127=true
Short cached -128=true
Long cached 127=true
Character cached A=true
Boolean shared true=true
large equality=true
large compareTo=true
large alias identity=true
wrapper vs int=true
null check=true
two nulls equal=true
null vs value=false
null unboxing=NullPointerException
previous wrapper=5
incremented wrapper=6
list contains equal wrapper=true
map lookup equal wrapper=found
cross-class equals=false
~~~

**Why is the output stable?** The program only prints identity within the **guaranteed shared range** or for an **actual alias**. For 1000, the program uses `equals`/`compareTo` and equality-based collections, and **does not print the result of `large1 == large2`**. Therefore, whether caching beyond -128..127 is expanded or not, the expected output does not change.

Additional points to observe:

1. Small integer wrappers and ASCII characters use identity guaranteed by the cache.
2. Two `Integer`s representing 1000 still compare values accurately via `equals`, even without relying on identity.
3. `Integer == int` unboxes before comparing; it differs from `Integer == Integer`.
4. Checking `missing == null` is safe; `missing == 0` tries to unbox null and causes an exception.
5. `incremented++` does not change the value observed by `previous`.
6. `List.contains`/`Map.get` still operate based on wrapper equality.
7. Wrappers of different classes (`Integer` and `Long`) are not automatically `equals` just because both represent the number 5.

## 12. Summary Table: Which Comparison Should You Use?

| Purpose | How to Do It | Why |
|---|---|---|
| Do two `int`s have the same value? | `a == b` | Both are primitives |
| Do two non-null `Integer`s have the same value? | `a.equals(b)` | Compares values, does not rely on caching |
| Are two possibly null `Integer`s equal? | `Objects.equals(a,b)` | Null-safe |
| Do two reference variables point to the same object? | `a == b` | Intentionally compares identity |
| Is a wrapper null? | `a == null` | Does not unbox |
| Compare wrapper with primitive, knowing wrapper is non-null | `boxed == primitive` | Unboxes then compares numbers |
| Wrappers have the same numeric value but different classes? | Choose a controlled conversion policy | `Integer.equals(Long)` does not compare across types |
| Generic collections using `Integer` as keys | `HashMap`/`Map.of` via `equals` | Does not depend on cache identity |

**Do not use `==` just because small-number examples all print `true`.** That is how caching hides bugs: when data scales up or moves to another JVM, identity results can differ.

## 13. Common Mistakes

| Mistake / Assumption | What Actually Happens | How to Handle It |
|---|---|---|
| `Integer a = 127; Integer b = 127; a == b` is true so always use `==` | Value 127 lies in the guaranteed cache range | Use `equals` to compare values |
| `Integer.valueOf(128) == Integer.valueOf(128)` is definitely false | The cache can be extended | Do not assert true/false outside the guaranteed range |
| Two `Integer`s with the same number are always the same object | Wrappers can have separate identities for the same value | Compare using `equals` |
| Two `Integer`s that are different objects have different values | `==` does not reflect equality | Use `equals` |
| `Integer a == int b` compares identity | Java unboxes the wrapper when comparing numbers | Be careful with null |
| `null Integer == 0` returns false | Unboxing null causes NPE | Check for null first |
| `a.equals(b)` is safe when `a` is null | Calling a method on null throws NPE | `Objects.equals(a, b)` |
| `Integer.valueOf(5).equals(Long.valueOf(5L))` is true | `Integer`'s `equals` requires matching type | Define a cross-type numeric comparison policy |
| Using `new Integer(...)` to bypass cache | Constructor is deprecated for removal | Use `valueOf`; no need to force identity control |
| `System.identityHashCode` is the object's address | Hash value is neither an address nor unique | Do not infer addresses from hashes |
| Caching makes wrappers mutable | Wrappers remain immutable | `++` computes and reassigns |
| `HashMap` uses `==` for keys | Normally uses `equals` and `hashCode` | Use the right collection for the required semantics |
| Wrappers have zero overhead because of caching | Caching does not guarantee eliminating all allocations | Choose primitives when appropriate; benchmark properly |

## 14. Exercises with Answers

### Exercise A — Same Reference

~~~java
Integer a = Integer.valueOf(1000);
Integer b = a;
System.out.println(a == b);
~~~

**Answer:** `true`. `b = a` copies the same reference value, regardless of whether 1000 is cached.

### Exercise B — Same Value, Identity Not Guaranteed

~~~java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);
System.out.println(a.equals(b));
~~~

**Answer:** `true`. You should not write a fixed expected output for `a == b` in this example; the required semantics are **value equality**.

### Exercise C — Small-Number Cache

~~~java
Long x = Long.valueOf(127L);
Long y = Long.valueOf(127L);
System.out.println(x == y);
~~~

**Answer:** `true`. The -128..127 range is guaranteed to be shared for `Long.valueOf`.

### Exercise D — Wrapper Compared to Primitive

~~~java
Integer wrapped = Integer.valueOf(1000);
int raw = 1000;
System.out.println(wrapped == raw);
~~~

**Answer:** `true`. Java unboxes `wrapped` to `int` and compares primitive values.

### Exercise E — Null and Unboxing

~~~java
Integer value = null;
System.out.println(value == null);
// System.out.println(value == 1);
~~~

**Answer:** the first line prints `true`. If the last line is run, auto-unboxing of the null value throws `NullPointerException`.

### Exercise F — HashMap Relies on Value

~~~java
java.util.Map<Integer, String> map = new java.util.HashMap<>();
map.put(Integer.valueOf(1000), "ok");
System.out.println(map.get(Integer.valueOf(1000)));
~~~

**Answer:** `ok`. `Integer.hashCode`/`equals` are value-based, so an equivalent key is found without needing the same object.

## 15. Completion Checklist

- [ ] Distinguish primitive `int` from wrapper `Integer`.
- [ ] Explain boxing cache and the benefit of reusing immutable wrappers.
- [ ] Remember the guaranteed identity range of `Integer.valueOf`: -128..127.
- [ ] Know that `Byte` caches the full range, `Character` caches 0..127, and `Boolean` has canonical instances.
- [ ] Know that outside the guaranteed range, caching may expand so `==` is unreliable for comparing values.
- [ ] Know that `Integer == Integer` compares references, while `Integer == int` unboxes then compares numbers.
- [ ] Use `equals` for non-null wrappers and `Objects.equals` when null is possible.
- [ ] Never unbox `null` in operators, assignments, or primitive parameters.
- [ ] Understand that wrappers are immutable: `count++` does not modify the old object.
- [ ] Know that `Integer.equals(Long)` does not convert wrapper types to compare numbers.
- [ ] Know that standard collections use equality, not wrapper caching.
- [ ] Do not use caching/`identityHashCode` as a basis for predicting performance or memory addresses.
- [ ] Compile and run `WrapperCacheDemo.java` with Java 17+, matching the exact expected output.

**Conclusion:** Wrapper caching causes some `==` comparisons on small values to return `true`, but **`==` is not a value comparison between two wrappers**. Caching outside Java's guaranteed ranges can vary across JVMs. To write accurate and maintainable code, use `equals` or `Objects.equals` for value comparisons, handle `null` before unboxing, and use `==` only when you genuinely want to check for the exact same object.