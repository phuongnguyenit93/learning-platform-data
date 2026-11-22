# `String` `hashCode` Caching Is an Implementation Detail

## 1. Main idea: the hash value is an API contract; caching is internal

`String` in Java is **immutable**: once a `String` object is created, its sequence of characters never changes. Therefore, the `hashCode()` value computed from the contents of a given `String` is always stable.

Two things must be distinguished:

1. **The public Java contract:** `String.hashCode()` must compute the hash according to the formula documented in the API specification. Two strings with equal content under `equals` must have the same hash; the empty string has hash `0`. Programs are allowed to rely on these properties.
2. **How the JDK optimizes the calculation:** Some implementations, such as OpenJDK 17, store the computed hash in private fields of the object to avoid rescanning characters. Field structure, caching conditions, storage timing, and synchronization are **implementation details**. Application code must not depend on them.

In other words, the result of `s.hashCode()` is determined by the *content* of `s` and the API contract, not by whether the JVM uses a cache. Having a cache also does not turn `hashCode()` into an object identity function or a cryptographic hash.

## 2. The official formula of `String.hashCode()`

The Java documentation defines the hash of a string of `n` `char` units as:

```text
h = s[0] × 31^(n-1) + s[1] × 31^(n-2) + ... + s[n-1]
```

The computation uses Java's 32-bit `int` type. Written as an equivalent loop:

```java
static int calculateHash(String text) {
    int h = 0;
    for (int i = 0; i < text.length(); i++) {
        h = 31 * h + text.charAt(i);
    }
    return h;
}
```

This is an **illustrative method** that can be placed inside a Java class; it demonstrates the formula, not `String`'s caching mechanism.

- `s.charAt(i)` accesses one **UTF-16 code unit**; characters outside the BMP (such as many emojis) are represented by two `char` values, and both participate in the hash.
- `int` can overflow; Java uses 32-bit integer arithmetic where the low 32 bits are retained. Do not switch to `long` or add custom overflow handling if you want the exact standard `String` hash.
- For an empty string, there are zero iterations, so the result is `0`.
- The formula depends on the order and values of the `char` units, not on file encoding, terminal encoding, object address, or how the JVM stores the string in memory.
- The value can be negative because the result is interpreted as a signed `int`. A hash is not a sequence number or a unique ID.

For example, `"Aa"` and `"BB"` have the same hash:

```text
"Aa": 65 × 31 + 97 = 2112
"BB": 66 × 31 + 66 = 2112
```

These two strings have **different content** even though they share the same `hashCode()`. This is a *hash collision*, not a bug in Java.

## 3. How does caching work in a concrete implementation?

A common optimization strategy for `String.hashCode()` is:

1. If a hash has already been stored for the current `String` object, return the stored value.
2. If no cached value exists yet, compute the hash using the standard formula.
3. Optionally write the result into a private field so subsequent calls do not have to scan the string again.

Because `String` is immutable, the cached result never needs to be invalidated when content "changes": producing different content creates another `String` result (aside from optimizations that return the same object when no change occurs). Operations like `concat`, `replace`, or `substring` cannot mutate characters inside the original object.

**Concrete example from OpenJDK 17:** the `java.lang.String` source code contains private fields `hash` (type `int`) and `hashIsZero` (type `boolean`). When needed, `hashCode()` can compute the hash based on the internal encoding and store the result. If the true hash is `0`, the `hashIsZero` flag distinguishes "already computed and equal to 0" from "no hash value stored yet" without rescanning the string.

This detail explains *how optimization is possible*, not a promise that every JDK, every release, or every JVM execution path has two fields with those exact names. In older OpenJDK releases, handling a hash of `0` worked differently; future implementations may also change.

**Note on hash equal to 0:** `0` is a completely valid result and does not automatically mean "not cached yet." Both `""` and a string containing a single NUL character (`"\0"`) have a hash of `0`. Therefore, never assume that strings with hash `0` are always recomputed or always cached.

Do not write reflection code to read or modify private fields such as `hash`, `hashIsZero`, or `value`. They are not part of the public API, may be blocked by the module system, and tampering with them risks breaking data structures keyed by strings.

## 4. Standalone Java 17+ example

Save as **`StringHashCodeDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public class StringHashCodeDemo {
    private static int calculateHash(String text) {
        int h = 0;
        for (int i = 0; i < text.length(); i++) {
            h = 31 * h + text.charAt(i);
        }
        return h;
    }

    public static void main(String[] args) {
        String first = "Aa";
        String second = "BB";
        String equalCopy = new String(new char[] {'A', 'a'});

        System.out.println("Aa hash: " + first.hashCode());
        System.out.println("BB hash: " + second.hashCode());
        System.out.println("Aa equals BB: " + first.equals(second));
        System.out.println("Equal text, same hash: "
                + (first.hashCode() == equalCopy.hashCode()));
        System.out.println("Different objects: " + (first != equalCopy));

        System.out.println("Empty hash: " + "".hashCode());
        System.out.println("NUL hash: " + "\0".hashCode());
        System.out.println("Formula matches: "
                + (calculateHash(first) == first.hashCode()));

        Map<String, Integer> map = new HashMap<>();
        map.put(first, 1);
        map.put(second, 2);

        System.out.println("Map size: " + map.size());
        System.out.println("Map Aa: " + map.get("Aa"));
        System.out.println("Map BB: " + map.get("BB"));

        String changed = first.concat("!");
        System.out.println("Original: " + first);
        System.out.println("Concatenated: " + changed);
    }
}
```

Compile and run:

```bash
javac StringHashCodeDemo.java
java StringHashCodeDemo
```

**Exact stdout** per the Java 17+ contract:

```text
Aa hash: 2112
BB hash: 2112
Aa equals BB: false
Equal text, same hash: true
Different objects: true
Empty hash: 0
NUL hash: 0
Formula matches: true
Map size: 2
Map Aa: 1
Map BB: 2
Original: Aa
Concatenated: Aa!
```

Interpretation:

- `first.hashCode()` and `second.hashCode()` are both `2112`, yet `first.equals(second)` is `false`: identical hashes do not mean identical strings.
- `equalCopy` was created from a new `char` array, so it is a different object from `first` but shares the same content; thus both objects produce the same hash.
- Both the empty string and the NUL-character string have hash `0`. This output **does not tell you** whether the current implementation caches the `0` result.
- `calculateHash(first)` returns the same value as `first.hashCode()` without using any cache field. This illustrates the specification result, not an inspection of internal JDK data structures.
- `HashMap` still stores both keys `"Aa"` and `"BB"` because, in addition to the hash, key lookup checks equality when needed.
- `concat("!")` produces a string with new content; `first` still refers to the original `"Aa"`. Therefore, the original object's hash is not "updated to track new content."

**You cannot prove caching with code that merely prints `hashCode()`.** An implementation that always recomputes the hash and one that caches it must still produce the exact same output above.

## 5. Computation cost and limits of cache optimization

Recomputing the formula across `n` code units takes steps proportional to string length: **O(n)**. With a caching strategy, the first computation can be O(n), while reading a stored value afterward is typically **O(1)** in terms of operations over string data.

This model explains a possible optimization, **not a complexity guarantee on every call** across every `String.hashCode()` implementation. Actual runtime behavior is also affected by JIT, escape analysis, constant folding, string length, whether the object is reused, and the JVM implementation.

| Scenario | What an application can expect |
| --- | --- |
| Calling `hashCode()` repeatedly on the same `String` object | Always returns the same value; the JDK may reuse the computed value. |
| Creating many distinct `String` objects with equal content | Each object still has its own internal state; do not assume all objects share a cache. |
| Hash equal to `0` | Result is `0`; whether recomputation is avoided depends on the implementation. |
| Changing string storage across JDK versions | The public formula and results must stay identical; byte storage and caching techniques may differ. |
| Calling `hashCode()` from multiple threads | Every call must return the correct result; do not rely on the hash being computed only once. |

When evaluating performance, measure **real applications** using a proper benchmarking methodology such as JMH. Do not draw conclusions from wrapping `System.nanoTime()` around one or a few `hashCode()` calls, as the code may be JIT-optimized, eliminated, or behave differently before warm-up.

## 6. Thread safety: why the cache field does not have to be `final`

`String` has immutable content, yet an implementation can **store internal computed state** in a cache field after object construction. `String` "immutability" at the API level refers to observable character content; it does not require every bit in the object's memory to remain immutable after the constructor finishes.

In OpenJDK 17, the hash optimization is designed so concurrent calls can read or write the cache without explicit locking. If two threads call `hashCode()` for the first time simultaneously, some computation may be repeated. Because the hash calculation is based on immutable content, the public result remains identical. The OpenJDK source describes this case as a form of *benign data race* subject to specific constraints to preserve correctness.

That observation applies only to the carefully controlled design inside `String`, **not as general advice** that developers can freely leave data races on cache fields in their own classes. For mutable classes or computations with side effects, unsynchronized caches can cause bugs or inconsistent data.

Multi-threaded applications can call `hashCode()` on the same `String` normally; there is no need to synchronize on the string to protect its internal cache. However, **never use hash calculation count, cache field writes, or cache state as a synchronization or communication mechanism between threads**.

## 7. Relationship with `equals`, `HashMap`, and memory

Relevant contracts:

- If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`.
- If two hashes are equal, that **does not imply** `equals` is `true`.
- `String.equals` compares content; the `==` operator compares references. Hash caching does not change either rule.
- `HashMap` and `HashSet` use hashes to locate lookup buckets/slots and use equality to distinguish keys when needed. `HashMap` may also perturb hash bits in its own implementation; bucket layout is not part of the `String.hashCode()` contract.
- `String.hashCode()` is **not for secure encryption**, tamper-resistant integrity checks, or password storage. A 32-bit hash is easy to collide and predict; for security, use appropriate cryptographic APIs and algorithms.

Some private OpenJDK details also relate to *Compact Strings*: since JDK 9, many strings are stored efficiently using a byte array and Latin-1/UTF-16 representation metadata rather than always using a `char` array as before. That storage layout can affect memory cost and computation paths, yet **it does not alter the hash formula over logical UTF-16 code units**. Therefore, do not deduce object size or cached bytes from the hash formula; those depend on the JDK version, JVM, and flags.

Having a cache field also does not mean every `String` immediately incurs the cost of scanning characters to compute its hash. An implementation can compute it **lazily** when requested; whether a value is already stored is internal state. Application code should rely only on public facts: the string's text, `equals`, and `hashCode()`.

## 8. Common mistakes and how to avoid them

**Mistake 1: "`String.hashCode()` is O(1) on every call because Java always caches it."**

What is true is that an implementation may cache it and reading a cached value is usually cheap. The specification does not mandate a specific cache structure; you cannot guarantee the first call, concurrent calls, or every JVM performs only a fixed amount of work.

**Mistake 2: "If the hash is `0`, it hasn't been computed yet."**

`0` is a valid hash value, such as for `""` and `"\0"`. Some OpenJDK builds use a separate flag marking a computed hash of `0`. Do not guess cache state from the return value alone.

**Mistake 3: "Two strings with the same hash have the same content."**

`"Aa"` and `"BB"` both have hash `2112` yet are unequal. When checking content, use `equals`; never replace it with `hashCode()` comparison.

**Mistake 4: "To optimize, modify the `hash` field via reflection."**

Private fields are internal implementation details; tampering breaks consistency and may be blocked by module system access controls. Do not depend on object layout.

**Mistake 5: "Hash caching means String content can be mutated."**

The cache only records a computed value; it does not alter the characters of the `String`. Operations producing different content do not edit the original string in place.

**Mistake 6: "You can time a single call to prove caching exists."**

JIT, inlining, constant folding, warm-up, and flawed microbenchmarks can make timings meaningless. Do not use raw elapsed time as proof of internal structure.

## 9. Rules for writing Java code

1. Use `String.hashCode()` normally when collection APIs or data structures require a hash; do not reimplement or manually cache it unless a clear business/measurement reason exists.
2. Use `equals` to check content equality; use `==` only when you genuinely need reference identity comparison.
3. When using `String` as keys in `HashMap`/`HashSet`, rely on immutability and the `equals`/`hashCode` contract, not on a specific JDK's caching mechanism.
4. Accept hash collisions as normal. Never use `hashCode()` as a unique ID, cryptographic fingerprint, or replacement for the original data.
5. When reading JDK source code to study optimizations, clearly separate **"how OpenJDK version X implements it"** from **"what the Java SE API guarantees."**

## References

- [Java SE 17 — `String.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#hashCode()) — authoritative source for the hash formula and values.
- [Java SE 17 — `Object.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()) — general contract between hash and equality.
- [OpenJDK 17 — `java.lang.String` source code](https://github.com/openjdk/jdk17/blob/master/src/java.base/share/classes/java/lang/String.java) — concrete example of `hash`/`hashIsZero` fields and optimization; this is implementation, not public API.
