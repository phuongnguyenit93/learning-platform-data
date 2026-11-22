# Combining Hashes of Multiple Fields in Java

## Objectives

When an object's equality is based on **multiple attributes**, `hashCode()` needs to produce a hash code consistent with that equality definition. This lesson explains how to combine the hashes of multiple fields, when to use `Objects.hash(...)`, when to combine manually using the multiplier `31`, and how to handle `null`, primitive types, arrays, nested objects, and pitfalls that cause `HashMap`/`HashSet` to behave unexpectedly.

After this lesson, you will be able to:

- Choose which fields to combine based on `equals(Object)`.
- Write a multi-field `hashCode()` in Java 17+ and verify consistency.
- Distinguish hashing ordinary fields from hashing **array contents**.
- Understand how field order, stability, and hash collisions affect design, while knowing a hash code is not a unique identifier.

## 1. Why Must Multiple Fields Be Combined?

Suppose a business key `PersonKey` has three fields:

```java
String region;
int number;
boolean active;
```

If `equals` determines that two keys are equal when **all three fields** match, we want `hashCode` to compute a hash code from that tuple of values. One way to describe it is:

```text
hash(PersonKey) = combine(
    hash(region),
    hash(number),
    hash(active)
)
```

The mandatory requirement under the `Object` contract is:

> If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must also be `true`.

The converse is **not required**: two unequal objects may still share the same hash code (**collision**). `hashCode()` returns a 32-bit `int`; the finite number of values makes it impossible to expect a unique hash code for every distinct object.

You could write `hashCode()` to return a constant for every object and still satisfy "equal objects have equal hashes", but that causes heavy collisions and generally degrades the performance of hash-based data structures. Therefore, good practice is to combine **the components that determine `equals`** to achieve a useful hash distribution.

Two questions must be answered before writing the method:

1. Which fields does `equals` compare?
2. Are those fields stable for as long as the object is used as a **`HashMap` key** or **`HashSet` element**?

Do not hash an extra field that can differ between two objects that `equals` still considers equal: doing so easily produces **two different hashes for two equal objects**, violating the contract. Conversely, omitting a field from the hash does not necessarily violate the contract, though it can increase collisions.

## 2. The Quick and Clear Way: `Objects.hash(...)`

The standard library provides `java.util.Objects.hash(Object... values)`. This method accepts multiple values, computes a combined hash in argument order, and handles `null` values. Primitive arguments are **boxed** into their wrapper types when passed through the `Object...` varargs parameter.

Example:

```java
@Override
public int hashCode() {
    return Objects.hash(region, number, active);
}
```

This approach is usually good enough for typical value objects with few fields when the execution path is not overly sensitive to allocation overhead.

**Note:** `Objects.hash(region, number, active)` differs from `Objects.hashCode(region)`:

- `Objects.hash(a, b, c)` **combines multiple values** in a way compatible with `Arrays.hashCode(Object[])` on the varargs argument array.
- `Objects.hashCode(x)` computes the hash of **a single object**; it returns `0` if `x == null`, and `x.hashCode()` otherwise.
- `Objects.hash(x)` with a single value is **not necessarily equal to** `Objects.hashCode(x)`: varargs combination starts at `1` and applies the combining formula, so it typically adds a `31` step. This is not wrong as long as the class's `equals` and `hashCode` use it consistently.

## 3. The Manual Way: Accumulating with Multiplier 31

A common pattern is to initialize an integer and fold in each field one by one:

```java
int result = 1;
result = 31 * result + hashOf(field1);
result = 31 * result + hashOf(field2);
result = 31 * result + hashOf(field3);
return result;
```

Where `hashOf(...)` can be:

| Field type | How to hash a single value |
| --- | --- |
| `int` | `Integer.hashCode(value)` (or `value` itself) |
| `long` | `Long.hashCode(value)` |
| `boolean` | `Boolean.hashCode(value)` |
| `byte`, `short`, `char` | `Byte.hashCode`, `Short.hashCode`, `Character.hashCode` |
| `float`, `double` | `Float.hashCode(value)`, `Double.hashCode(value)` |
| Nullable object | `Objects.hashCode(value)` |
| Primitive or object array compared by element | `Arrays.hashCode(array)`; see Section 6 |
| Nested object array compared deeply | `Arrays.deepHashCode(array)`; see Section 6 |

The multiplier `31` is a pragmatic convention widely used across Java. It makes **the order of values** affect the result, reducing certain trivial collisions compared to plain addition. Nothing guarantees that every distinct set of values will produce a distinct hash.

When `int` multiplication/addition overflows its range, Java uses 32-bit `int` wrap-around arithmetic; integer overflow in this combining pattern is **normal** and remains deterministic. There is no need to try to eliminate overflow; in particular, never switch to a random calculation that makes the hash code change across calls for the same object state.

**Field order:** If you use `region → number → active`, keep that same order in every calculation. Changing field order still satisfies the contract if implemented consistently, whereas an unstable order across calls is a bug. When comparing two versions of a formula, exact hash numbers can only be compared when both the rule and the order match.

## 4. Complete Example: `equals`, `Objects.hash`, and Manual Combination

Create the file **`MultiFieldHashDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MultiFieldHashDemo {
    static final class PersonKey {
        private final String region;
        private final int number;
        private final boolean active;

        PersonKey(String region, int number, boolean active) {
            this.region = region;
            this.number = number;
            this.active = active;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof PersonKey other)) {
                return false;
            }
            return number == other.number
                    && active == other.active
                    && Objects.equals(region, other.region);
        }

        @Override
        public int hashCode() {
            return Objects.hash(region, number, active);
        }

        int manualHashCode() {
            int result = 1;
            result = 31 * result + Objects.hashCode(region);
            result = 31 * result + Integer.hashCode(number);
            result = 31 * result + Boolean.hashCode(active);
            return result;
        }
    }

    public static void main(String[] args) {
        PersonKey first = new PersonKey("VN", 7, true);
        PersonKey equal = new PersonKey("VN", 7, true);
        PersonKey different = new PersonKey("VN", 7, false);

        System.out.println("first.equals(equal): "
                + first.equals(equal));
        System.out.println("same hash for equal keys: "
                + (first.hashCode() == equal.hashCode()));
        System.out.println("Objects.hash matches manual: "
                + (first.hashCode() == first.manualHashCode()));
        System.out.println("first.equals(different): "
                + first.equals(different));

        Set<PersonKey> keys = new HashSet<>();
        keys.add(first);
        System.out.println("set contains equal key: "
                + keys.contains(equal));

        PersonKey nullRegionA = new PersonKey(null, 7, true);
        PersonKey nullRegionB = new PersonKey(null, 7, true);
        System.out.println("null region keys equal: "
                + nullRegionA.equals(nullRegionB));
        System.out.println("null region hashes equal: "
                + (nullRegionA.hashCode() == nullRegionB.hashCode()));
    }
}
```

Run with JDK 17+:

```bash
javac MultiFieldHashDemo.java
java MultiFieldHashDemo
```

**Output:**

```text
first.equals(equal): true
same hash for equal keys: true
Objects.hash matches manual: true
first.equals(different): false
set contains equal key: true
null region keys equal: true
null region hashes equal: true
```

Explanation:

- `equals` checks the **exact same three fields** that `hashCode` combines. `Objects.equals(region, other.region)` handles cases where one or both strings are `null`.
- `Objects.hash` applies the same accumulation formula as the manual example: `result` starts at `1`, and for each varargs element `result = 31 * result + elementHash`. Here the field order and component hashes match, so the outputs are equal.
- `Integer.hashCode` returns the `int` value itself, while `Boolean.hashCode` returns deterministic constants for `true` and `false`. `Objects.hashCode(null)` returns `0`.
- Two equal `PersonKey` instances produce the same hash. Consequently, `HashSet.contains(equal)` finds the element added from a different instance with the same values.
- The example uses `final` fields and immutable component types (`String`, `int`, `boolean`), keeping key state stable.

**Do not misunderstand:** the line `first.equals(different): false` does not by itself guarantee the corresponding two hashes must differ. Distinct values may still share a hash; that is not a contract violation.

## 5. Why Plain Addition or Using Only One Field Is Usually Poor

An ad-hoc implementation such as:

```java
return x + y; // Poor example: fails to distinguish (1, 2) from (2, 1).
```

has obvious collisions: `(1, 2)` and `(2, 1)` produce the same sum. Another implementation like `return region.hashCode();` ignores `number` and `active`, causing many distinct objects to share the same hash code. Omitting fields is not necessarily a **contract bug**, but it can hurt distribution if the omitted fields carry high distinguishing power.

Multiplying by 31 distinguishes order better in many cases:

```java
int result = 1;
result = 31 * result + x;
result = 31 * result + y;
return result;
```

However, **no `int` hash function guarantees zero collisions for all possible value tuples**. The goal is a fast, stable function with reasonable distribution that satisfies the `equals/hashCode` contract.

For keys with few fields, `Objects.hash(...)` is usually easy to read and reduces the risk of forgetting a field. For very frequently called hash paths, manual combination can avoid varargs array allocation and boxing overhead; rely on **actual measurements** before optimizing. Avoid inventing a complex algorithm just to make hash numbers look "pretty".

## 6. Array Fields: Hashing **Contents** vs. Hashing **References**

This is an important trap when combining multiple fields.

Arrays in Java are objects. If a class defines equality by **element contents** (`Arrays.equals`), then `hashCode` must also use the matching content hash function (`Arrays.hashCode`). Hashing an array with the method inherited from `Object` is essentially based on reference identity and does not reflect its elements.

Conceptually wrong example:

```java
// If equals uses Arrays.equals(bytes, other.bytes), then:
return Objects.hash(name, bytes); // Wrong semantics: bytes is an array.
```

With `byte[]`, the `bytes` argument is treated as **a single array object** by `Objects.hash`. A byte array inherits identity-based `hashCode` from `Object`; two arrays with equal contents are not guaranteed to yield equal hashes.

Better:

```java
int result = Objects.hashCode(name);
result = 31 * result + Arrays.hashCode(bytes);
return result;
```

For an `Object[]` whose elements are nested arrays requiring deep comparison, use the corresponding pair:

- `Arrays.deepEquals(a, b)` with `Arrays.deepHashCode(a)`.
- `Arrays.equals(a, b)` with `Arrays.hashCode(a)` if you want single-level element comparison (nested arrays inside `Object[]` are still compared by their own relation unless the `deep` variant is used).

**A note on varargs:** When passing an `Object[]` directly to `Objects.hash(Object...)`, its elements themselves can be treated as the varargs arguments. Calling `Objects.hash(array)` is therefore error-prone in array contexts. When content-based array hashing is required, explicitly call `Arrays.hashCode(array)` or `Arrays.deepHashCode(array)` depending on semantics.

### 6.1. Complete Example with an Array Field

Create the file **`ArrayFieldHashDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ArrayFieldHashDemo {
    static final class PacketKey {
        private final String protocol;
        private final byte[] payload;

        PacketKey(String protocol, byte[] payload) {
            this.protocol = Objects.requireNonNull(protocol);
            this.payload = Objects.requireNonNull(payload).clone();
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof PacketKey other)) {
                return false;
            }
            return protocol.equals(other.protocol)
                    && Arrays.equals(payload, other.payload);
        }

        @Override
        public int hashCode() {
            int result = Objects.hashCode(protocol);
            result = 31 * result + Arrays.hashCode(payload);
            return result;
        }

        int firstByte() {
            return payload[0];
        }
    }

    public static void main(String[] args) {
        byte[] source = {1, 2, 3};
        PacketKey first = new PacketKey("tcp", source);
        PacketKey same = new PacketKey("tcp", new byte[] {1, 2, 3});
        PacketKey changed = new PacketKey("tcp", new byte[] {1, 2, 4});

        System.out.println("equal payloads: " + first.equals(same));
        System.out.println("equal hashes: "
                + (first.hashCode() == same.hashCode()));
        System.out.println("different payloads: "
                + first.equals(changed));

        Set<PacketKey> packets = new HashSet<>();
        packets.add(first);
        System.out.println("set finds equal payload: "
                + packets.contains(same));

        source[0] = 99; // Mutate the external array.
        System.out.println("internal first byte: " + first.firstByte());
        System.out.println("set still finds original: "
                + packets.contains(same));
    }
}
```

Run:

```bash
javac ArrayFieldHashDemo.java
java ArrayFieldHashDemo
```

**Output:**

```text
equal payloads: true
equal hashes: true
different payloads: false
set finds equal payload: true
internal first byte: 1
set still finds original: true
```

Here `PacketKey` makes a **defensive copy** (`clone`) of the array in the constructor. Because external code only retains the `source` array, mutating `source` does not alter the key's internal state. This is especially important once the key has been inserted into a `HashSet` or `HashMap`.

**Example limitation:** `firstByte()` assumes a non-empty payload and only serves to inspect content in an example using a three-element array. In a real API, accessors must handle empty cases, and exposing the array externally must also be controlled (for example, returning a copy).

## 7. Object Fields and Nested Structures

For a regular object field, use `Objects.hashCode(field)` or `field.hashCode()` (if guaranteed non-`null`). For the overall hash code to align with `equals`, that field's own type must also obey the `equals/hashCode` contract.

Example:

```java
final class Address {
    private final String city;
    private final String street;

    // Constructor, equals, and hashCode will need to be fully implemented.
}
```

If a `CustomerKey` compares `customerId` and `address` using `Objects.equals`, the hash code can be:

```java
return Objects.hash(customerId, address);
```

These two snippets **only illustrate the design** and are not standalone programs to compile and run; the rest of the class must be declared and `Address` must have value-appropriate `equals/hashCode`.

Do not call `address.toString().hashCode()` just to "get a hash" of an object. `toString()` is meant for presentation/diagnostics and is rarely designed as an equality definition. Nor should you use `System.identityHashCode(address)` if the class's `equals` treats two distinct address instances with identical content as equal.

For standard collections:

- `List.hashCode()` combines element hashes **taking order into account**, matching `List.equals`.
- `Set.hashCode()` is based on elements and **is independent of iteration order**, matching `Set.equals`.
- `Map.hashCode()` is based on entries, matching `Map.equals`.
- An object holding a mutable collection as an equality component risks having its hash change if the collection is modified. Avoid allowing external mutation of an internal collection when it forms part of a key.

## 8. Special Types and `null` Values

### 8.1. Primitive Types

Use the standard hash method for each corresponding type, especially `long`, `float`, and `double`. For example:

```java
int result = 1;
result = 31 * result + Long.hashCode(orderId);
result = 31 * result + Double.hashCode(amount);
result = 31 * result + Boolean.hashCode(confirmed);
```

This is an **illustrative snippet** assuming the field variables are already declared in the class.

Avoid writing `(int) orderId` for a `long` field: casting truncates the upper bits and easily causes unnecessary collisions. Avoid casting floating-point numbers to `int` if the equality relation distinguishes fractional values.

For `float`/`double`, `Float.hashCode` and `Double.hashCode` have bit-level semantics consistent with value comparisons under `Float.equals`/`Double.equals`. If the class's `equals` uses the `==` operator directly on floating-point values, be very careful: for instance, `+0.0 == -0.0` is `true` under `==`, yet those two values have different hashes under `Double.hashCode`. A `hashCode` using `Double.hashCode` when `equals` uses `==` can violate the contract in this case. Standardize on a consistent comparison policy (for example, `Double.compare` in `equals` with `Double.hashCode` in hash) rather than mixing incompatible formulas.

### 8.2. `null`

`Objects.hash(region, category)` handles `null` values automatically. With a manual formula:

```java
int result = 1;
result = 31 * result + Objects.hashCode(region);
result = 31 * result + Objects.hashCode(category);
return result;
```

`Objects.hashCode(null)` returns `0`; no `NullPointerException` occurs. Avoid `region.hashCode()` when `region == null` is possible.

### 8.3. `record`

A Java `record` automatically provides `equals` and `hashCode` over **all record components**, unless you explicitly override them:

```java
record ProductKey(String code, int revision, boolean active) {}
```

This is a concise way to model simple value objects. However:

- If a `record` has an **array** component, the default `equals`/`hashCode` of the record uses the array component's own semantics (reference comparison), **not automatic array-content comparison**. If you want element-based equality, you must design an appropriate `equals/hashCode` pair or use a different structure.
- A `record` makes its component fields `final`, but **does not automatically make a component referencing a mutable collection/array deeply immutable**.
- If business logic requires a subset different from all components to participate in equality, design an explicit value object/structure and maintain consistency between `equals` and `hashCode`.

## 9. Mutating Fields After Inserting the Object into `HashMap`/`HashSet`

Consider a mutable class where both `equals` and `hashCode` depend on `id`:

```java
final class MutableKey {
    int id;

    MutableKey(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof MutableKey other && id == other.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}
```

This snippet is a **class illustration**; it can be placed in an appropriate Java file as a top-level class or inside a program's `main`.

When `id` changes after the key has been added to a `HashMap`, lookups may fail to find the key because the hash code at lookup time differs from the hash code when the key was placed in the data structure. Even if `equals/hashCode` remain consistent with each other, mutating hash-participating state still causes application bugs.

**Practical rule:** For value-based keys, prefer immutable designs; fields participating in `equals/hashCode` should stay fixed throughout the time the object is used as a key. If mutation is unavoidable, remove the key under its old state and re-insert it under its new state at the appropriate point with consistent management.

## 10. How to Verify Implementation Quality

Beyond running examples, check the following categories of scenarios:

| Scenario | What to verify |
| --- | --- |
| Two instances with identical `equals` fields | `equals == true` and `hashCode` values are equal |
| Differ in exactly one `equals` field | `equals == false`; hashes **may** be equal or different, do not assert inequality |
| Nullable reference field | No `NullPointerException`; identical `null` states yield consistent hashes |
| Content-compared array field | `Arrays.equals/hashCode` or `deepEquals/deepHashCode` pair used accordingly |
| Mutable fields present | Not mutated while used as a key, or governed by a clear management strategy |
| Component class used | That component also has compatible `equals/hashCode` |
| Used in `HashSet`/`HashMap` | Entry/key can be found using another instance considered equal by `equals` |

Common mistakes spotted in code reviews:

1. `equals` checks `name` and `age`, while `hashCode` hashes `name` with `createdAt`. Two equal objects can have different hashes if `createdAt` differs.
2. Using `Objects.hash(bytes)` when `equals` uses `Arrays.equals(bytes, ...)`, hashing array identity instead of array content.
3. Calling `field.hashCode()` on a field that can be `null`.
4. Computing the hash once and caching it while the relevant fields remain mutable and can change, leaving the cached hash out of sync with comparison state.
5. Believing different hashes are required for unequal objects; in reality, collisions are valid.
6. Using hash data as a persistent identifier, security signature, or uniqueness check: `hashCode()` is not designed for those purposes.

## 11. Self-Check Exercises

**Exercise 1.** A `BookKey` class compares by `isbn` and `edition`. Which hash code implementation is readable and appropriate?

```java
@Override
public int hashCode() {
    return Objects.hash(isbn, edition);
}
```

**Answer:** Appropriate if `equals` also checks those exact two fields with matching rules, and the values remain stable while the object serves as a key.

**Exercise 2.** `equals` compares only `username` and `tenantId`. May `lastLoginTime` be added to `hashCode`?

**Answer:** No. Two objects with the same `username`/`tenantId` but different `lastLoginTime` could have `equals == true` while having different hashes, violating the contract.

**Exercise 3.** A class contains `int[] scores` and uses `Arrays.equals(scores, other.scores)`. How should the hash of `scores` be computed?

**Answer:** `Arrays.hashCode(scores)`, then combined with the hashes of the remaining fields. `scores.hashCode()` hashes by array identity and is inappropriate when equality is defined by content.

**Exercise 4.** Can two unequal objects return the same hash?

**Answer:** Yes. Collisions do not violate the contract; the mandatory relation only goes in the direction `equals == true ⇒ same hash`.

**Exercise 5.** Why is `Objects.hash(...)` convenient yet the `31 * result + ...` formula still popular?

**Answer:** `Objects.hash` is concise, handles `null` and automatic boxing, and helps avoid accidentally omitting a field. The manual formula provides exact control over data types and avoids some varargs/boxing overhead on hot paths, at the cost of requiring care to pick the right fields, order, and component hash functions.

## Key Takeaways

**Start from `equals`, then pick the exact attributes that determine equality to combine into `hashCode`.** For regular fields, `Objects.hash(field1, field2, ...)` is an easy default; when performance control or special types matter, combine manually with `31` and type-specific hash functions. For arrays, you must use `Arrays.hashCode`/`Arrays.deepHashCode` if equality is content-based. Keep the hash stable while the object acts as a key, and accept collisions as a normal part of hashing.