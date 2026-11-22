# Immutable Wrappers and Value-Based Semantics in Java

## 1. Objectives

In Java, each primitive type has a corresponding *wrapper* class. Wrapper classes allow primitive values to be passed into APIs that require objects, such as `List<Integer>`, `Map<Long, String>`, `Optional<Double>`, or methods accepting `Object`/`Number`.

The most important point: **wrappers are immutable and are described by Java as value-based classes**. Programmers should care about their **values**, not rely on object identity. Immutability makes sharing values safe, though it does not mean wrappers are primitives or that Java guarantees two objects with the same value always have the same address/reference.

After this lesson, you should be able to explain:

- Why you cannot "directly modify" the contents inside `Integer`, `Long`, `Double`, or `Boolean`.
- Why `x++` or `x = x + 1` on a wrapper variable does not mutate the old wrapper object.
- Why `equals()` is normally the right intent for comparing **values**, whereas `==` between two wrapper references can cause subtle bugs.
- The roles of `valueOf()`, autoboxing, unboxing, and `Integer`'s cache range.
- Why wrappers should not be used as monitors in `synchronized`, keys in `IdentityHashMap`, or identity-dependent operations.
- Important exceptions in `Double.equals()`/`Float.equals()` regarding NaN and differently signed zeros `+0.0`/`-0.0`.

This lesson uses Java 17+; the value-based concepts here reflect current API contracts and Java design guidance, without requiring preview features.

## 2. How Do Primitives and Wrappers Differ?

| Primitive | Wrapper | Example |
| --- | --- | --- |
| `boolean` | `Boolean` | `Boolean.TRUE` |
| `byte` | `Byte` | `Byte.valueOf((byte) 12)` |
| `short` | `Short` | `Short.valueOf((short) 12)` |
| `char` | `Character` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer.valueOf(12)` |
| `long` | `Long` | `Long.valueOf(12L)` |
| `float` | `Float` | `Float.valueOf(1.25f)` |
| `double` | `Double` | `Double.valueOf(1.25)` |

Numeric wrappers (except `Character` and `Boolean`) are subclasses of `java.lang.Number`. All eight classes above are `final` classes: you cannot subclass them. In modern Java, their API documentation also describes them as **value-based classes**.

Practical differences:

- A primitive variable directly holds a value of that type: `int n = 10;`.
- A wrapper variable is a **reference to an object** containing the primitive value: `Integer n = Integer.valueOf(10);`.
- A wrapper reference can be `null`; a primitive has no `null` value.
- Wrappers have methods such as `intValue()`, `compareTo()`, `equals()`, `hashCode()`, `toString()`, and static methods like `valueOf()`/parse per class.
- Standard generics do not accept primitives: `List<int>` is invalid, whereas `List<Integer>` is valid.

**Do not confuse immutability with a `final` variable:** `final` restricts **reassigning the variable**, while immutability restricts **mutating the state of an existing object**. They are independent concepts.

## 3. Immutable Wrappers: The Old Object Is Never Modified

An `Integer` object representing 10 will continue representing 10 throughout that object's lifetime. The class provides no `setValue()` or valid mechanism to alter the internal primitive value.

~~~java
Integer first = Integer.valueOf(10);
Integer saved = first;

first = Integer.valueOf(20);

System.out.println(saved); // 10
System.out.println(first); // 20
~~~

This is an **illustrative snippet inside a method**, not a standalone runnable program. The assignment `first = ...` points `first` to another wrapper value; `saved` still holds 10.

The same principle applies to `Long`, `Short`, `Double`, `Boolean`, and the rest of the wrappers. Calls like `Integer.sum(a, b)` or `Math.abs(n)` compute a **result value**; they do not mutate the source object.

### Immutability differs from final

~~~java
Integer changeableReference = 7;
changeableReference = 9; // valid: variable is not final

final Integer fixedReference = 7;
// fixedReference = 9;  // compile-time error: cannot reassign final
~~~

In both cases, the wrapper objects holding 7 remain immutable. `final` is not what makes a wrapper immutable.

### What does incrementing a wrapper variable with ++ actually do?

~~~java
Integer counter = 5;
Integer before = counter;
counter++;

System.out.println(before);  // 5
System.out.println(counter); // 6
~~~

In terms of values, Java performs **unboxing → adding one on the primitive → boxing** and then **reassigns** the `counter` reference. The original object is not modified. Primitive overflow rules still apply: incrementing `Integer.MAX_VALUE` wraps around to `Integer.MIN_VALUE`; wrappers do not automatically expand their numeric range.

### Other immutable data classes

`BigInteger` and `BigDecimal` are also immutable: `value.add(...)` returns a new result instead of mutating the receiver. However, they are not primitive wrappers and have their own ranges/precisions and API contracts. The concept of "immutable" is broader than "wrapper" and broader than the list of classes marked *value-based* in the API.

## 4. What Does Value-Based Mean?

According to the Java API documentation, objects of a **value-based** class should be treated by applications as **values**: instances considered equal by `equals()` should be interchangeable in value-based uses.

Design consequences:

1. **Do not use identity as business data:** avoid concluding two wrappers represent different entities just because two references are not `==`.
2. **Do not use wrappers as monitors in `synchronized`:** some instances may be shared by caches or other object-creation mechanisms. Java also warns that synchronizing on value-based instances may have unpredictable behavior and may lose support in the future.
3. **Do not rely on `System.identityHashCode(wrapper)`, `IdentityHashMap`, or identity-based lookups** to store value semantics.
4. **Do not rely on the number of objects allocated** by `valueOf()` or boxing. JVM implementations may reuse or optimize objects whenever compatible with the class's contract.

This **does not** mean wrappers are not objects in Java 17. `Integer` still has a reference type, can be `null`, has `equals()` and `hashCode()`, and can be used as keys in `HashMap`. Value-based describes **proper usage under the API contract**, not a claim that Java 17 turned `Integer` into a primitive type or a new JVM *value class*.

Immutability and value-based semantics are related but **not identical**: an object can be immutable while an application still needs its identity (e.g., an identity token with its own contract). For wrappers, the API clearly specifies **value-oriented** semantics.

## 5. Comparisons: equals() vs. ==

### Two wrappers of the same type: compare values

~~~java
Integer left = Integer.valueOf(1000);
Integer right = Integer.valueOf(1000);

System.out.println(left.equals(right)); // true
~~~

Do not write `left == right` to compare values when **both operands are `Integer` references**. In that case `==` compares **whether they refer to the same object**, not numeric equality.

A confusing detail: if one operand is a primitive, Java can unbox the wrapper and turn `==` into a **numeric comparison**:

~~~java
Integer boxed = Integer.valueOf(1000);
System.out.println(boxed == 1000); // true: unboxes boxed to int
~~~

Thus nearly identical-looking statements can have **two different semantics** for `==` depending on the compile-time operand types.

### equals checks the exact wrapper class

~~~java
Integer oneInt = Integer.valueOf(1);
Long oneLong = Long.valueOf(1L);

System.out.println(oneInt.equals(oneLong)); // false
~~~

Both objects hold the same mathematical value 1, yet `Integer.equals(Object)` is only equal to an `Integer` object with the same value; `Long` is not an `Integer`. Do not call `equals()` between wrappers of different types expecting Java to convert or widen numbers as in primitive addition.

If you truly want to compare numeric values of two integer types, **convert explicitly** to a type with an appropriate range (e.g., `long` for `int` and `long`), or `BigInteger` for large values; for `float`/`double`, consider rounding error and special values.

### Null-safe equality

~~~java
Integer nullable = null;
Integer expected = 10;

System.out.println(java.util.Objects.equals(nullable, expected)); // false
System.out.println(java.util.Objects.equals(null, null));          // true
~~~

`Objects.equals(a, b)` safely handles cases where one or both references are `null`. It does not convert `Integer` to `Long` or alter the class's `equals()` contract.

## 6. Caching and Integer.valueOf(): A Benefit, Not an Application Contract on Identity

`Integer.valueOf(int)` **always caches** values from **−128 to 127** per the Java 17 documentation and **may cache additional** values depending on the environment. Therefore:

~~~java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);

System.out.println(a == b);      // true: example of guaranteed cache for this range
System.out.println(a.equals(b));  // true
~~~

However, if you use 1000:

~~~java
Integer x = Integer.valueOf(1000);
Integer y = Integer.valueOf(1000);

System.out.println(x.equals(y)); // true
// Do not rely on (x == y): caching beyond -128..127 is not guaranteed.
~~~

**Lesson:** even though `a == b` happens to be true due to caching in many cases, do not use identity to conclude two values are equal. Code that works for 42 and fails for 1000 is a classic bug from relying on object identity.

`Integer.valueOf` is generally preferred over constructing objects via constructors. Constructors like `new Integer(int)` are **deprecated for removal** in Java 17; they force unnecessary identity and are not the intended way to obtain wrappers. Likewise, autoboxing typically goes through the appropriate wrapper-creation mechanism rather than mutating an existing object.

Do not assume every wrapper has the exact same caching policy as `Integer`: guaranteed ranges vary by class and type; what stays reliable for business logic is using **`equals()` and `hashCode()` by value**.

## 7. Autoboxing and Unboxing: Convenient, Yet Carrying Cost and Risk

**Autoboxing** converts a primitive to its wrapper in suitable contexts:

~~~java
int primitive = 7;
Integer boxed = primitive; // equivalent to using Integer.valueOf(...)
~~~

**Unboxing** extracts the primitive value from a wrapper:

~~~java
Integer boxed = 7;
int primitive = boxed; // equivalent to boxed.intValue()
~~~

This allows Java to write:

~~~java
Integer a = 2;
Integer b = 3;
Integer sum = a + b; // unboxes both numbers, adds ints, boxes result
System.out.println(sum); // 5
~~~

This process **does not** modify `a` or `b`. The `+` operation executes on primitive values per language rules; for example, `int` addition can still overflow.

### Unboxing null throws NullPointerException

~~~java
Integer quantity = null;
// int count = quantity; // throws NullPointerException at runtime
~~~

Even without an explicit assignment to `int`, an operation requiring unboxing such as `quantity + 1`, `quantity > 0`, or `quantity == 0` can also throw `NullPointerException`. By contrast, `quantity == null` is a valid reference check and does not require unboxing.

Do not assume wrapper values coming from a database, JSON, `Map.get()`, or an API that can return `null` are always non-null. Handle missing data per contract (validation, meaningful fallback, or error reporting).

### Performance

Creating/reading wrappers can incur boxing/unboxing, object allocations, and memory accesses. The JIT compiler can optimize some cases, yet applications should not rely on a specific allocation count.

For very large computational loops, prefer `int`, `long`, `double`, and primitive arrays where suitable. For generic/collection APIs requiring objects, wrappers remain the standard choice. Optimize only based on profiling and actual program requirements.

## 8. Wrappers in Collections: HashMap, HashSet, and Immutability

Value-based collections such as `HashMap` and `HashSet` use `equals()`/`hashCode()` to identify equivalent keys/elements. Wrappers make great keys because the object's value state does not spontaneously change after insertion.

~~~java
java.util.Map<Integer, String> labels = new java.util.HashMap<>();
labels.put(Integer.valueOf(1000), "thousand");

String found = labels.get(Integer.valueOf(1000));
System.out.println(found); // thousand
~~~

There is no need to guarantee two calls to `valueOf(1000)` return **the exact same object**: `Integer.equals()` and `hashCode()` enable lookup by value.

Contrast this with:

~~~java
java.util.Map<Integer, String> identityMap = new java.util.IdentityHashMap<>();
// Do not use IdentityHashMap if business logic needs numeric key lookup by value.
~~~

`IdentityHashMap` compares keys using `==`, so its behavior can diverge from `HashMap` and wrapper reuse policies. It is designed for situations that **genuinely require object identity**, not ordinary integer key lookup tables.

Note that immutable wrappers **do not make a collection immutable**. `labels.put(1000, "...")` still mutates the map's contents; it simply does not alter the primitive value inside the key wrapper.

## 9. Do Not Use Wrappers as Synchronization Monitors

Code like the following is an **anti-pattern to avoid**:

~~~java
// Bad design example, do not use in applications:
// Integer lock = Integer.valueOf(1);
// synchronized (lock) {
//     // critical section
// }
~~~

Problems:

- `Integer.valueOf(1)` can return a cached object shared with completely unrelated code. Two unrelated threads/code blocks can unintentionally share the same monitor.
- If the wrapper variable is reassigned, `synchronized` blocks across different executions may lock on **different objects**.
- Official documentation warns that wrappers are *value-based* and must not be used for synchronization; Java may change how identity is supported for these values in the future.
- The Java 17 compiler can emit warnings on `synchronized` statements over an instance of a value-based class (per JEP 390).

Use a lock object whose identity is dedicated to synchronization:

~~~java
public class SafeCounter {
    private final Object lock = new Object();
    private int value;

    public void increment() {
        synchronized (lock) {
            value++;
        }
    }

    public int get() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

This is a **standalone compilable class** (save as `SafeCounter.java`), though it has no `main`. For a simple counter needing atomic operations across multiple threads, `AtomicInteger` may fit; that is a **mutable stateful class**, not the immutable `Integer` wrapper.

## 10. Float and Double: equals Differs from == on NaN and Signed Zero

Floating-point wrappers must support a consistent `equals()` relation for collections like `HashMap`/`HashSet`. Consequently, `Double.equals()` and `Float.equals()` have **rules that differ from primitive `==`** in two special cases.

| Situation | Primitive `double == double` | `Double.equals()` |
| --- | --- | --- |
| `1.0` and `1.0` | `true` | `true` |
| `Double.NaN` and `Double.NaN` | `false` | `true` |
| `+0.0` and `-0.0` | `true` | `false` |

Example:

~~~java
Double nanA = Double.valueOf(Double.NaN);
Double nanB = Double.valueOf(Double.NaN);
System.out.println(nanA.equals(nanB)); // true
System.out.println(nanA.doubleValue() == nanB.doubleValue()); // false

Double positiveZero = Double.valueOf(+0.0);
Double negativeZero = Double.valueOf(-0.0);
System.out.println(positiveZero.equals(negativeZero)); // false
System.out.println(positiveZero.doubleValue() == negativeZero.doubleValue()); // true
~~~

`Double.equals()` is based on the `Double.doubleToLongBits()` representation, canonicalizing NaN bit patterns so all NaNs are considered equal while preserving the distinction between signed zeros. `Float.equals()` has an analogous mechanism using `Float.floatToIntBits()`.

This **does not contradict value-based semantics**: the notion of "two equal instances" is defined by **the class's `equals()`**, not necessarily by the primitive `==` arithmetic operator.

### compareTo and total ordering of floating-point wrappers

`Double.compare()`/`Double.compareTo()` establish an ordering consistent with `Double.equals()`:

- `-0.0` is ordered **less than** `+0.0`.
- `NaN` is ordered greater than all other `double` values, including `+Infinity`; NaNs compare equal under this ordering.

This design lets `Double` serve as elements in ordered collections like `TreeSet`. Do not assume `Double.compare(a, b)` always matches `a < b` semantics when NaN or differently signed zeros are present.

## 11. Complete Java 17+ Program

Save the following code into `WrapperValueDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class WrapperValueDemo {
    public static void main(String[] args) {
        Integer original = Integer.valueOf(10);
        Integer saved = original;
        original++;

        System.out.println("saved=" + saved);
        System.out.println("after increment=" + original);

        Integer left = Integer.valueOf(1000);
        Integer right = Integer.valueOf(1000);
        System.out.println("same value=" + left.equals(right));
        System.out.println("boxed vs primitive=" + (left == 1000));
        System.out.println("cached 42=" +
                (Integer.valueOf(42) == Integer.valueOf(42)));

        System.out.println("cross type equals=" +
                Integer.valueOf(1).equals(Long.valueOf(1L)));
        System.out.println("null safe=" + Objects.equals(null, null));

        Map<Integer, String> labels = new HashMap<>();
        labels.put(Integer.valueOf(1000), "thousand");
        System.out.println("map lookup=" + labels.get(Integer.valueOf(1000)));

        Double nanA = Double.valueOf(Double.NaN);
        Double nanB = Double.valueOf(Double.NaN);
        System.out.println("NaN wrapper equals=" + nanA.equals(nanB));
        System.out.println("NaN primitive equals=" +
                (nanA.doubleValue() == nanB.doubleValue()));

        Double plusZero = Double.valueOf(+0.0);
        Double minusZero = Double.valueOf(-0.0);
        System.out.println("signed zero wrapper equals=" +
                plusZero.equals(minusZero));
        System.out.println("signed zero primitive equals=" +
                (plusZero.doubleValue() == minusZero.doubleValue()));

        Integer missing = null;
        try {
            int primitive = missing;
            System.out.println(primitive);
        } catch (NullPointerException ex) {
            System.out.println("unboxing null: NPE");
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 WrapperValueDemo.java
java WrapperValueDemo
~~~

Stdout:

~~~text
saved=10
after increment=11
same value=true
boxed vs primitive=true
cached 42=true
cross type equals=false
null safe=true
map lookup=thousand
NaN wrapper equals=true
NaN primitive equals=false
signed zero wrapper equals=false
signed zero primitive equals=true
unboxing null: NPE
~~~

**Explanation of key points:**

1. `original++` computes via unboxing/boxing and reassigns the variable; `saved` remains 10.
2. `left.equals(right)` compares **values**, regardless of whether the two `1000` wrappers share an object.
3. `left == 1000` is true because the second operand is `int`, causing `left` to unbox. `valueOf(42) == valueOf(42)` is true due to guaranteed caching; **do not generalize this identity assumption to all values**.
4. `Integer(1)` and `Long(1L)` are not equal under `equals()` because they are different classes.
5. `HashMap` looks up keys using `equals()`/`hashCode()`, so two wrappers with the same value retrieve the same entry.
6. Comparing `NaN` and signed zeros shows the differing semantics between wrapper `equals()` and primitive `==`.
7. Unboxing `null` throws `NullPointerException`; the program catches the exception and prints a message.

This is a single-threaded example focusing on immutability, identity, and equality. There is no need to include a `synchronized` block on a wrapper just to demonstrate it, since that is an anti-pattern to avoid.

## 12. Applying Properly in API and Data Design

### Choosing int vs. Integer

Choose `int` when data always has a value, needs arithmetic, and has no "unknown" meaning. Choose `Integer` when generic/collection APIs require an object or the application **genuinely needs to distinguish** `null` from `0`.

For example, a `retryCount` field can use `int` defaulting to 0; a nullable database column may need `Integer`. Do not silently turn `null` into `0` when they carry different meanings.

### Do not turn a wrapper into an identity-bearing entity

A value `Integer.valueOf(42)` should be treated as **the number 42**, not as "user object number 42" with its own lifecycle. If an application needs to represent an entity with identity, create a domain class/record with an explicit identifier, such as `CustomerId` or `Order`, instead of using wrapper instance identity.

### Do not pick a monitor from a numeric value

If you need a private object lock, use a `private final Object lock = new Object()` field, `ReentrantLock`, or an appropriate concurrent structure. If you need to update a counter concurrently, consider `AtomicInteger`/`AtomicLong`. Numeric values should only be **data**, never monitors.

### Immutability does not cure floating-point error

An immutable `Double` still holds a `double` value subject to IEEE 754 limits: NaN, Infinity, ±0, and rounding error still exist. If business logic needs exact decimals, `BigDecimal` may be more appropriate. That is a decision about **numeric model**, not about object identity.

## 13. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| `Integer a = 1000, b = 1000; if (a == b)...` | Reference comparison, prone to cache dependence | `a.equals(b)` or `Objects.equals(a,b)` |
| Using `==` on wrappers just because it worked for `42` | Behavior changes when value/cache range changes | Compare values consistently |
| `Integer count = null; count++;` | `NullPointerException` when unboxing | Check/apply null policy |
| Assuming `count++` mutates the old `Integer` object | Misunderstands aliasing and immutability | It unboxes, adds, boxes, and reassigns |
| Using `synchronized(Integer.valueOf(id))` | Caching causes unintended monitor sharing; violates value-based guidance | Use a lock with dedicated identity |
| Using `IdentityHashMap<Integer, ...>` for numeric keys | Looks up by `==` instead of value | `HashMap<Integer, ...>` |
| Expecting `Integer.valueOf(1).equals(Long.valueOf(1))` to be true | `equals` requires matching wrapper type | Convert explicitly when comparing numbers across types |
| Assuming `Double.NaN == Double.NaN` is true | IEEE 754 comparison is non-reflexive for NaN | Use `Double.isNaN` or `Double.equals` as appropriate |
| Assuming `Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` is true | `Double.equals` distinguishes signed zeros | Choose comparison semantics per business rules |
| Creating wrappers via deprecated constructors | Compiler warnings; bypasses `valueOf`/boxing | `valueOf` or boxing |
| Using `Integer` for loop counters in hot loops without evaluating cost | Unnecessary boxing/unboxing and object access | Use primitives where appropriate, benchmark performance |

## 14. Self-Check Questions

**1.** What does the following snippet print?

~~~java
Integer a = 5;
Integer b = a;
a = a + 1;
System.out.println(a + ", " + b);
~~~

**Answer:** `6, 5`. `a` points to a new wrapper value; `b` is unchanged.

**2.** Why is `Integer.valueOf(42) == Integer.valueOf(42)` true, yet `==` should still not be used to compare wrappers?

**Answer:** `Integer.valueOf` guarantees caching from −128 to 127. Outside that range, caching is not guaranteed; more importantly, `==` between two references checks object identity, whereas numeric value comparison should use `equals()`.

**3.** Does `Integer.valueOf(1000).equals(Long.valueOf(1000L))` return `true`?

**Answer:** No; `equals()` checks the exact wrapper class. To compare the numeric values of `int` and `long`, convert explicitly to `long` and compare primitives.

**4.** Can you synchronize using `synchronized(Integer.valueOf(1))` if only one place in the code uses it?

**Answer:** No. Wrappers are value-based classes with caching mechanisms and are not designed to serve as lock identities. Use a dedicated `Object`/lock.

**5.** Are `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` and `Double.NaN == Double.NaN` the same?

**Answer:** No; the first expression is `true`, the second is `false`. This is an intentional difference between `Double.equals()` and primitive comparison.

**6.** Can a `HashMap<Integer, String>` look up an entry using a wrapper of the same value even if the instances are not shared?

**Answer:** Yes. `HashMap` uses `hashCode()` and `equals()` to identify equivalent keys, without requiring wrapper identity.

## 15. Takeaways and References

- Wrappers are **immutable objects**, whereas variables holding references can be reassigned unless declared `final`.
- **Value-based** directs applications toward value semantics via `equals()`; do not use wrappers as monitors or rely on object identity.
- `Integer.valueOf()` guarantees caching for `-128..127`, but this is **not** a reason to use `==` for value comparison.
- Autoboxing/unboxing is convenient, yet can add overhead, lose information across numeric conversions, and throw `NullPointerException` when unboxing `null`.
- `Double.equals()`/`Float.equals()` handle NaN and signed zero differently from primitive `==`; choose the right comparison per API contract.
- For numeric keys in collections, use `HashMap`/`HashSet`; for repeated arithmetic, consider primitives; for synchronization, use a dedicated lock or appropriate concurrent class.

Official sources:

- [Java SE 17 — Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): value-based, `valueOf`, cache, `equals`, deprecated constructors.
- [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): equality for NaN and signed zero; value-based description.
- [Java SE 17 — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `Objects.equals`.
- [JEP 390 — Warnings for Value-Based Classes](https://openjdk.org/jeps/390): risks related to identity and synchronizing on value-based objects.
- [JLS SE 17 — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7) and [Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8): automatic conversion rules.