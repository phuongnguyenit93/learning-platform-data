# Integer wrapper classes of different types are not equal by default

## 1. Two objects with the same number are not necessarily equal under `equals()`

Java has **wrapper classes** for primitive integer types:

| Primitive type | Wrapper class | Example value creation |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.valueOf((byte) 42)` |
| `short` | `Short` | `Short.valueOf((short) 42)` |
| `int` | `Integer` | `Integer.valueOf(42)` |
| `long` | `Long` | `Long.valueOf(42L)` |

Those four objects all represent the mathematical value **42**, yet they belong to **four different Java classes**. For standard integer wrapper classes, the `equals(Object)` method requires the other object to belong to the **exact same wrapper type** and hold the same stored value. Therefore:

```java
Integer integer = 42;
Long longNumber = 42L;

System.out.println(integer.equals(longNumber)); // false
System.out.println(longNumber.equals(integer));  // false
```

This is an **illustrative fragment**; the full runnable program appears later. The key point to grasp: a wrapper's `equals()` defines equality **by type and value**; it does not automatically convert both sides to a common numeric type.

This is a deliberate choice about **Java object** identity, not a statement that the arithmetic comparison `42 == 42L` is false. When you want to compare **numeric values**, you must explicitly specify the conversion or comparison rule.

## 2. How `equals()` works in integer wrappers

In terms of semantics, the implementations follow rules like these:

```java
// Semantic illustration; NOT the actual implementation source code:
boolean integerEquals(Object other, int value) {
    return other instanceof Integer that && value == that.intValue();
}

boolean longEquals(Object other, long value) {
    return other instanceof Long that && value == that.longValue();
}
```

These are **two behavior-modeling functions**. When `Integer.equals` receives a `Long`, the `instanceof Integer` check fails; the result is immediately `false`. When `Long.equals` receives an `Integer`, the `instanceof Long` check also fails.

The same applies to `Byte` and `Short`. The following pairs produce these results:

| Left | Right | `left.equals(right)` |
| --- | --- | --- |
| `Integer.valueOf(42)` | `Integer.valueOf(42)` | `true` |
| `Integer.valueOf(42)` | `Long.valueOf(42L)` | `false` |
| `Short.valueOf((short) 42)` | `Byte.valueOf((byte) 42)` | `false` |
| `Long.valueOf(42L)` | `Long.valueOf(42L)` | `true` |
| `Integer.valueOf(42)` | `null` | `false` |

The table shows symmetry for these examples: two wrappers of different types are unequal in both directions. Returning `false` between two different classes **does not violate** the `equals()` contract. The contract only requires reflexivity, symmetry, transitivity, consistency, and `x.equals(null) == false`; it does not require Java to treat every representation of the same number as one logical object.

`Objects.equals(a, b)` is a null-handling comparison utility: if both are null it returns `true`, if one is null it returns `false`, and otherwise it delegates to `a.equals(b)`. **`Objects.equals` does not automatically convert wrapper types.**

## 3. Runnable Java 17 example

Create the file `IntegerWrapperEqualityDemo.java`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class IntegerWrapperEqualityDemo {

    // Accept only the four integer wrapper types.
    static boolean isIntegerWrapper(Number number) {
        return number instanceof Byte
                || number instanceof Short
                || number instanceof Integer
                || number instanceof Long;
    }

    // CUSTOM rule for business logic that needs to compare integer values.
    // longValue() is an exact conversion for the four wrappers above.
    static boolean sameIntegerValue(Number a, Number b) {
        return isIntegerWrapper(a)
                && isIntegerWrapper(b)
                && a.longValue() == b.longValue();
    }

    public static void main(String[] args) {
        Integer i = Integer.valueOf(42);
        Long l = Long.valueOf(42L);
        Short s = Short.valueOf((short) 42);
        Byte b = Byte.valueOf((byte) 42);

        System.out.println("Integer.equals(Long): " + i.equals(l));
        System.out.println("Long.equals(Integer): " + l.equals(i));
        System.out.println("Integer.equals(Integer): "
                + i.equals(Integer.valueOf(42)));
        System.out.println("Short.equals(Byte): " + s.equals(b));
        System.out.println("Objects.equals(i, l): "
                + Objects.equals(i, l));

        Number left = i;
        Number right = l;
        System.out.println("Number references ==: " + (left == right));
        System.out.println("int vs long primitives ==: "
                + (i.intValue() == l.longValue()));
        System.out.println("boxed Integer vs primitive long ==: "
                + (i == 42L));

        System.out.println("sameIntegerValue(i, l): "
                + sameIntegerValue(i, l));
        System.out.println("sameIntegerValue(s, b): "
                + sameIntegerValue(s, b));
        System.out.println("sameIntegerValue(i, 43L): "
                + sameIntegerValue(i, Long.valueOf(43L)));
        System.out.println("sameIntegerValue(i, 42.0): "
                + sameIntegerValue(i, Double.valueOf(42.0)));

        System.out.println("Integer hash: " + i.hashCode());
        System.out.println("Long hash: " + l.hashCode());

        Set<Number> numbers = new HashSet<>();
        numbers.add(i);
        numbers.add(l);
        numbers.add(s);
        numbers.add(b);
        System.out.println("set size: " + numbers.size());
        System.out.println("contains Integer(42): "
                + numbers.contains(Integer.valueOf(42)));
        System.out.println("contains Long(42): "
                + numbers.contains(Long.valueOf(42L)));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac IntegerWrapperEqualityDemo.java
java IntegerWrapperEqualityDemo
```

Exact output:

```text
Integer.equals(Long): false
Long.equals(Integer): false
Integer.equals(Integer): true
Short.equals(Byte): false
Objects.equals(i, l): false
Number references ==: false
int vs long primitives ==: true
boxed Integer vs primitive long ==: true
sameIntegerValue(i, l): true
sameIntegerValue(s, b): true
sameIntegerValue(i, 43L): false
sameIntegerValue(i, 42.0): false
Integer hash: 42
Long hash: 42
set size: 4
contains Integer(42): true
contains Long(42): true
```

### Reading the output by semantic layer

- `i.equals(l)` and `l.equals(i)` are both `false` because one side is `Integer` and the other is `Long`.
- `Objects.equals(i, l)` is also `false`: this method only handles null-safety and relies on `i.equals(l)`.
- `left` and `right` are declared with type `Number`, so `left == right` compares **references** to two different objects: `false`. There is no unboxing because both operands here are `Number` references.
- `i.intValue() == l.longValue()` compares two primitive values; `int` is widened to `long` according to Java's numeric promotion rules, so `42 == 42L` is `true`.
- `i == 42L` is also `true` because one operand is the primitive `long`; Java unboxes `i` to `int` and then widens it for primitive numeric comparison. The `==` syntax can yield different results depending on the **static types of the operands**.
- `sameIntegerValue(i, l)` returns `true` because we explicitly defined the comparison by `longValue()` for the four integer wrappers.
- `Double.valueOf(42.0)` is rejected by `isIntegerWrapper`, even though its mathematical value is 42. This is the **policy scope of the helper**, not an inability to compare floating-point numbers with integers using another API.
- The two objects `Integer(42)` and `Long(42)` have the same hash code `42` yet are still not equal. **Equal hashes do not imply `equals()` is true**.
- `HashSet<Number>` holds all four wrappers of different types that all represent 42: `size() == 4`. The set uses each object's `equals()`/`hashCode()`, **not arbitrary arithmetic conversions**.

## 4. Why `==` cannot replace `equals()`

`==` in Java has two semantics relevant to this example:

1. **Two references of compatible types for reference comparison**: checks whether they point to the same object in memory.
2. **Two operands in a primitive numeric comparison context**, possibly via unboxing: checks numeric value after the language's numeric conversion rules.

Separate examples for each case:

```java
Integer boxedInt = Integer.valueOf(42);
long primitiveLong = 42L;
boolean numeric = boxedInt == primitiveLong; // true: unbox + widen

Number a = boxedInt;
Number b = Long.valueOf(42L);
boolean sameReference = (a == b); // false: reference comparison
```

The first two lines use `==` with primitives, and the next two use it with references. This code is a **fragment**, not a standalone program.

**Warning when looking at two variables of types `Integer` and `Long`:** the expression `integerObject == longObject` may be rejected by the compiler because those two reference types are incompatible for reference comparison; Java has no rule that says "if you see two different wrapper types, always unbox both." Do not generalize from `boxedInt == primitiveLong` to all wrapper combinations.

### Caching is not an equality contract

`Integer.valueOf` guarantees object reuse for at least the range `-128..127`. This can cause `==` between two `Integer` variables to sometimes return `true` because they point to the same object. Outside the guaranteed range, the runtime may have a broader caching policy; never use `==` results to infer that two boxed integers have the same value.

```java
Integer first = Integer.valueOf(42);
Integer second = Integer.valueOf(42);

first == second;      // true within the guaranteed cache range
first.equals(second); // true by value and type
```

This fragment is for illustration; if the goal is to compare two `Integer` values, use `equals()` or `Objects.equals()` when null-safety is needed.

## 5. When you need to compare different integer wrappers by value

### Explicit conversion within a safe value range

All four wrappers `Byte`, `Short`, `Integer`, and `Long` represent values within the range of `long`. Therefore, converting via `longValue()` from **strictly these four types** is exact and lossless:

```java
static boolean sameIntegerValue(Number a, Number b) {
    boolean supportedA = a instanceof Byte || a instanceof Short
            || a instanceof Integer || a instanceof Long;
    boolean supportedB = b instanceof Byte || b instanceof Short
            || b instanceof Integer || b instanceof Long;
    return supportedA && supportedB && a.longValue() == b.longValue();
}
```

This snippet is an **illustrative helper**, not a standalone runnable Java file. The type filter condition before conversion plays a crucial role: `Number` also includes other classes such as `Float`, `Double`, `BigInteger`, and `BigDecimal`. For those, `longValue()` can **truncate the fractional part**, lose precision, or keep only the lower bits of a value outside the `long` range.

If the data includes `BigInteger` values larger than the `long` limits, you should not use `longValue()` to decide whether two values are equal. You need a common representation with sufficient precision for the business domain, such as converting the integer wrappers and `BigInteger` to `BigInteger`, or designing a dedicated value type.

### Do not implicitly change the policy of `equals()`

An application may define a `sameIntegerValue` helper that returns `true` for `Integer(42)` and `Long(42)`. This **does not change** the result of `Integer.equals(Long)` or `Long.equals(Integer)`, which remain `false`.

You cannot "fix" `Integer.equals()` or `Long.equals()` in the standard library simply by using a helper. If business logic wants source types with the same number to count as one key, **normalize to a single common key type** before storing and comparing.

For example, if the domain only allows numbers within `long`, we can use `Long` as the key:

```java
Long fromInteger = Long.valueOf(Integer.valueOf(42).longValue());
Long fromLong = Long.valueOf(Long.valueOf(42L).longValue());

boolean equalKeys = fromInteger.equals(fromLong); // true
```

This is an illustrative fragment. Normalizing both sides to `Long` keeps the meaning of "same integer value in the long range" consistent. In a real system, the normalization policy should be applied at data boundaries (reading input, building keys, writing to collections), avoiding situations where code sometimes compares using the original wrapper and sometimes uses a value helper.

## 6. Impact on `HashSet`, `HashMap`, and collections

`HashSet` relies on its elements' `equals()` relation and corresponding hash codes; `HashMap` uses this relation for keys. When adding `Integer.valueOf(42)` and `Long.valueOf(42L)` to a `HashSet<Number>`, they are treated as **two distinct elements**.

```java
Set<Number> set = new java.util.HashSet<>();
set.add(Integer.valueOf(42));
set.add(Long.valueOf(42L));
System.out.println(set.size()); // 2
```

This is a fragment: `import java.util.Set;` or a fully qualified type name is needed. Both `Integer(42)` and `Long(42)` return `42` for `hashCode()` in this example, yet a collision does not cause two elements to be considered equal. The collection also has to use `equals()` to distinguish objects.

Practical consequence: code using `Map<Number, String>` can store two separate entries for `Integer(42)` and `Long(42)`, even when they share the same hash code and look like a single customer ID. If the intent is "all integer IDs belong to the same reference space," choose **a single fixed key type**, such as `Map<Long, String>`, and validate/convert every ID before putting it into the map.

Do not modify `hashCode()` alone to try to merge wrappers of different types. For hash-based Java collections, having the same hash code is a necessary condition for an equal pair, but **not sufficient to make two objects equal**.

## 7. Common pitfalls and type notes

### a. `Number` is a common superclass, not an "arithmetic equals" definition

The wrappers `Byte`, `Short`, `Integer`, and `Long` are subclasses of `Number`, but assigning them to `Number` references **does not give them a shared numeric `equals()` algorithm**.

```java
Number n1 = Integer.valueOf(42);
Number n2 = Long.valueOf(42L);

System.out.println(n1.equals(n2)); // false
```

Dynamic method dispatch still runs the implementation of the actual runtime object, which is `Integer` or `Long`.

### b. Distinguishing `Character` and `Boolean`

`Character` wraps the primitive `char`, whose character code is an unsigned integer in the sense of a UTF-16 code unit value, yet it **does not extend `Number`** and does not share `equals()` with `Integer` or `Long`. `Boolean` is also not an integer wrapper. Do not pass them into the `sameIntegerValue(Number, Number)` helper without clear business rules.

### c. Handling null

`Integer.equals(null)` returns `false`; however, calling `nullableInteger.equals(anything)` when `nullableInteger == null` will cause a `NullPointerException`. Use `Objects.equals(a, b)` if you need null-safety while still **preserving wrapper type policy**:

```java
java.util.Objects.equals(Integer.valueOf(42), Long.valueOf(42L)); // false
java.util.Objects.equals(null, null);                       // true
java.util.Objects.equals(Integer.valueOf(42), null);        // false
```

This is a fragment illustrating the expressions. If you want an **arithmetic** comparison helper to accept null under a custom policy, you must state explicitly whether null equals null and whether null is allowed as a key; do not assume `Objects.equals` changes wrapper semantics.

### d. Overflow and supported ranges

Comparing by casting both to `int` can truncate information from a `Long` larger than `Integer.MAX_VALUE`. The `longValue()` method is safe for the four integer wrappers listed above, but not generally safe for every `Number`, especially `BigInteger`/`BigDecimal`/`Double`.

If choosing `Long` as the normalized type, ensure inputs are within the `long` range. If choosing `BigInteger`, use **exact** conversions from standard integer types; floating-point or decimal numbers with fractional parts require separate rules. Rounding or truncating the fractional part must be an explicitly documented business decision.

### e. Comparing in `TreeSet`/`TreeMap` using a `Comparator`

Unlike hash collections, sorted collections determine key duplicates by the comparator's `compare(a, b) == 0` result (or natural ordering). A custom comparator comparing `Number` instances by `longValue()` may treat `Integer(42)` and `Long(42)` as equivalent even though `equals()` returns `false`. This makes the ordering **inconsistent with equals**, which can produce behavior different from `HashSet` and violate expectations of `Set` APIs.

Choose and document a consistent key policy for the collection; if you must define a cross-type comparator, verify reflexivity of `compare(x,x)==0`, antisymmetry, transitivity, and compatibility with your intended use.

## 8. Practical checklist

1. **Ask what "equal" means:** same wrapper and value, or same integer value regardless of wrapper? These are two different relations, both valid in their own contexts.
2. **Check static types before using `==`:** two references compare identity; a wrapper and a primitive can trigger unboxing + promotion; two wrappers of different types do not automatically compare arithmetically.
3. **If comparing wrappers under Java's contract:** use `equals()`, or `Objects.equals()` when nulls are possible. `Integer(42)` with `Long(42)` yields `false`.
4. **If comparing integers across types:** restrict the supported set of types and convert to a common lossless representation, such as `long` for `Byte/Short/Integer/Long`.
5. **If using as collection keys:** normalize inputs to a single key type before inserting/looking up; do not rely on matching hashes or implicit casting.
6. **Test edge cases:** `null`, negative numbers, `Long.MIN_VALUE`/`Long.MAX_VALUE`, values outside the `int` range, and `Number` subtypes that are not integer wrappers.

### Self-check

**Question 1:** What is `Integer.valueOf(7).equals(Long.valueOf(7L))`? — `false` because the two objects are of different classes.

**Question 2:** If two wrappers of different types have the same `hashCode()`, will `HashSet` merge them into one element? — No; `HashSet` also checks equality.

**Question 3:** What does `Integer.valueOf(7) == 7L` evaluate to? — `true`: one operand is primitive, so the wrapper is unboxed and compared numerically. However, you must not infer that every `==` between two wrappers has those semantics.

**Question 4:** Why not use `Number.longValue()` directly for every `Number`? — Because `Double` has a fractional part and `BigInteger` can exceed the `long` range; conversion can lose information, causing two different values to be treated as equal.

## Conclusion

**Having the same numeric value does not mean being the same logical object in Java.** `Byte`, `Short`, `Integer`, and `Long` apply `equals()` based on **the exact wrapper type plus the stored value**, so `Integer(42).equals(Long(42L))` is `false`. When a problem requires comparing integer values across types, state the domain explicitly and convert losslessly to a common representation. Keep that policy consistent at comparison sites, data normalization boundaries, and when choosing collection keys.
