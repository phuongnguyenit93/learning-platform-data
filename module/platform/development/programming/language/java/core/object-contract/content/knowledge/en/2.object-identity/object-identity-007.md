# Identity Hash Codes Can Collide and Are Not Memory Addresses

In Java, an object has its own **identity**, even when the data inside it is identical to another object's. `System.identityHashCode(Object)` provides a hash value tied to that identity, which is useful when observing or tracking instances. However, **the hash value is not a unique identifier and is not the object's address in RAM**.

## 1. Identity, Equality, and Hash Codes Are Three Different Concepts

- **`a == b` with two references:** checks whether two variables reference **the same object**; two different instances always give `false`, even when their contents are equal.
- **`a.equals(b)`:** checks equality according to the class's convention. If `Object.equals` is not overridden, the default convention is reference identity; classes such as `String` usually override it to compare values.
- **`a.hashCode()`:** calls a method that may have been overridden by the class. The `equals`/`hashCode` contract requires two objects equal by `equals` to have the same hash code; the converse is not true. Two unequal objects can still have the same hash code.
- **`System.identityHashCode(a)`:** retrieves the hash code the way the default `Object.hashCode()` would, **regardless of whether `a`'s class overrides `hashCode()` or not**. This value is not derived from a class-defined value-based `equals`.

For example, two `new String("java")` objects are two different instances so `==` returns `false`, yet `equals` returns `true` and their `String.hashCode()` values are equal. **You cannot infer from that** that their two `System.identityHashCode` values are necessarily different or necessarily equal.

## 2. What Identity Hash Codes Guarantee

For a given object within the same program run, calling `System.identityHashCode` multiple times returns the same value. Two references pointing to the same object naturally receive the same identity hash code. `System.identityHashCode(null)` returns `0`.

However, the API **does not guarantee** that two different objects have two different identity hash codes:

- The return value has type `int`, meaning at most `2^32` bit patterns can be represented, whereas the number of object identities that can appear is not bounded by a unique set of hash values across all executions.
- The JVM's hash generation mechanism only attempts to distinguish objects under practical conditions; it does not assign unique sequence numbers. A **collision** means `a != b` yet `System.identityHashCode(a) == System.identityHashCode(b)`.
- Two different objects can collide; comparing two hash numbers for equality **does not prove** that two references point to the same object. Conversely, if two identity hash codes differ, those references cannot point to the same object at the time of comparison within the same run.
- Hash values are not guaranteed to remain the same across JVM restarts, across machines, JVM versions, or runtime configurations. Do not store them as persistent identity keys.

The pigeonhole principle shows that an `int` cannot be used as a unique code for an arbitrary number of identities. **You do not need to create billions of objects to prove this limit**, and a small example without a collision does not prove that collisions are impossible.

## 3. Why Is an Identity Hash Code Not a Memory Address?

Java provides *references* to access objects, but the Java API does not expose an object's physical address or virtual machine memory address through `System.identityHashCode`. The JVM is free to organize the heap and implement identity hashing in various ways.

- The garbage collector can **move objects** in memory while object identity and identity hash codes within a single run retain their meaning. Therefore, a hash value cannot be equated with a memory location at a single point in time.
- Details of how the hash is stored (such as in object metadata or an external structure) are JVM implementation details, **not part of the Java contract**.
- A common representation such as `java.lang.Object@4e25154f` comes from how default `Object.toString()` concatenates the class name with `Integer.toHexString(hashCode())`. The hex string after `@` is the **hash code in base 16**, not a pointer. If a class overrides `toString()` or `hashCode()`, the displayed output can also differ.
- Even if a specific JVM uses address-related information in its hashing algorithm, **an exact or stable address cannot be reverse-engineered from it** under the Java specification.

Therefore, you should not read numbers like `0x4e25154f` as heap addresses, use them to calculate distances between objects, or assume an object will remain in one place forever.

## 4. Directly Runnable Java 17+ Example

Save the following snippet in the file `IdentityHashCodeDemo.java`:

```java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityHashCodeDemo {
    public static void main(String[] args) {
        Object original = new Object();
        Object alias = original;
        Object another = new Object();

        System.out.println("alias == original: " + (alias == original));
        System.out.println("another == original: " + (another == original));
        System.out.println("alias identity hash matches: "
                + (System.identityHashCode(alias) == System.identityHashCode(original)));
        System.out.println("Object.hashCode matches identityHashCode: "
                + (original.hashCode() == System.identityHashCode(original)));
        System.out.println("identityHashCode(null): " + System.identityHashCode(null));

        String one = new String("java");
        String two = new String("java");
        System.out.println("one == two: " + (one == two));
        System.out.println("one.equals(two): " + one.equals(two));
        System.out.println("one.hashCode() == two.hashCode(): "
                + (one.hashCode() == two.hashCode()));

        Map<String, Integer> valueKeys = new HashMap<>();
        Map<String, Integer> identityKeys = new IdentityHashMap<>();
        valueKeys.put(one, 1);
        valueKeys.put(two, 2);
        identityKeys.put(one, 1);
        identityKeys.put(two, 2);
        System.out.println("HashMap size: " + valueKeys.size());
        System.out.println("IdentityHashMap size: " + identityKeys.size());
    }
}
```

Compile and run from the directory containing the file:

```bash
javac IdentityHashCodeDemo.java
java IdentityHashCodeDemo
```

Standard output, independent of specific hash numbers:

```text
alias == original: true
another == original: false
alias identity hash matches: true
Object.hashCode matches identityHashCode: true
identityHashCode(null): 0
one == two: false
one.equals(two): true
one.hashCode() == two.hashCode(): true
HashMap size: 1
IdentityHashMap size: 2
```

**Reading the output correctly:**

1. `original` and `alias` point to the same instance, so both `==` and the identity hash code comparison yield `true`. `another` is a new instance so `==` with `original` yields `false`; the example **does not assert** that the identity hash codes of these two instances must differ.
2. `original` is of exact class `Object`, which does not override `hashCode()`, so `original.hashCode()` and `System.identityHashCode(original)` are equal. That **does not apply by default to every class that overrides `hashCode()`**.
3. `one` and `two` have identical content, so `String.equals` and `String.hashCode` treat them as equal values. `HashMap` replaces the value for the equivalent key, leaving 1 entry.
4. `IdentityHashMap` uses **`==` for keys**, so `one` and `two` are two different keys and the map has 2 entries. It uses identity hash codes for lookup but **still compares actual identity to handle collisions**; it does not treat matching hash numbers as the same key.

The example deliberately **does not print a fixed identity hash code number**, because those numbers depend on the runtime. Nor does it use `identityHashCode(one) != identityHashCode(two)` as proof that two instances are different: that may hold in one run, but it is not an API guarantee.

## 5. How to Apply and Mistakes to Avoid

| Purpose | Appropriate Approach | Error-Prone Approach |
| --- | --- | --- |
| Checking if two references share the same object | `a == b` | `System.identityHashCode(a) == System.identityHashCode(b)` |
| Comparing two logical values | `equals` and `hashCode` following the class's contract | Using identity hash codes instead of value comparison |
| Creating a map that distinguishes instances even when `equals` is true | `IdentityHashMap` when identity semantics are genuinely needed | Using identity hash code as an `Integer` key and ignoring collisions |
| Logging to correlate occurrences of an instance in a single run | Display class name with identity hash code **as a hint label**, and confirm by reference when needed | Treating that label as a unique ID across all objects and all runs |
| Needing a unique ID, persisted long-term or exchanged across processes | Issue a domain-specific ID, such as a UUID or lifecycle-managed ID generator | Storing `System.identityHashCode` or the suffix of `Object.toString()` |
| Investigating an object's location in memory | Use appropriate JVM diagnostic tools while accepting environment dependence | Inferring addresses from hash numbers or the hex string after `@` |

**Debugging note:** two log lines with the same identity hash code can still come from two different instances. When distinguishing identity affects program correctness, rely on references or a dedicated ID mechanism designed to be unambiguous within your requirements.

## 6. Knowledge Self-Check

- If `a == b` is `true`, will two calls to `System.identityHashCode(a)` and `System.identityHashCode(b)` in the same run be equal? **Yes**, because it is the same object.
- If two identity hash codes are equal, can you conclude `a == b`? **No**, because collisions can occur.
- If `a.equals(b)` is `true`, must their identity hash codes be equal? **No**, because `equals` can compare the values of two different instances; the mandatory contract applies to `a.hashCode()` and `b.hashCode()`, not identity hash codes.
- Can you obtain the memory address using `Integer.toHexString(System.identityHashCode(a))`? **No**: that operation merely converts the representation of the same hash number to base 16.

**Remember:** identity is determined by **the same reference** (`==`); an identity hash code is a **supporting hash value** that can collide and does not represent a memory address.