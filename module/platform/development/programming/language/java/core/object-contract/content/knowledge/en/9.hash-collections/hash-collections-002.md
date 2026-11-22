# Distinguishing Hashing for Search Routing from Confirming Equality

## 1. Two Different Questions in Hash Data Structures

When using `HashMap` or `HashSet`, it is easy to misunderstand that "two objects with the same `hashCode()` are equal". That is **incorrect**. Hash structures use two related mechanisms that perform two different jobs:

1. **Hashing for search routing:** `hashCode()` provides an integer that helps the data structure determine where to look first (the bucket, candidate group, or corresponding internal structure).
2. **Confirming equality:** when encountering a suitable candidate key, a reference-identity check or `equals(Object)` decides whether it is actually the key being searched for.

**A hash is a pointer to where to look, not proof of unique identity.** Two keys can collide on the same hash value (hash collision) even though they are not equal. The hash structure must handle this collision by distinguishing keys according to the `equals` contract.

For example:

- The two strings `"Aa"` and `"BB"` have the same `String.hashCode()` value of `2112`, but `"Aa".equals("BB")` is `false`.
- A `HashMap<String, Integer>` can hold **both keys** and return the right corresponding values.
- Two objects that have the same value meaning according to `equals` **must** have the same `hashCode`; the converse is not guaranteed.

This lesson focuses on how to connect **hashing to find candidates** with **comparing to confirm** when using Java hash structures, and how to design `equals`/`hashCode` properly so that lookup is reliable.

## 2. Lookup Flow in `HashMap`: Narrow Down, Then Confirm

Imagine the call `map.get(queryKey)`. At a conceptual level, the process proceeds as follows:

1. Obtain the hash code of the query key (for `null`, `HashMap` has special handling).
2. Use the hash information and the current table capacity/structure to route to the group containing potentially matching keys.
3. Within the candidate group, compare hash information and inspect the key. If the two references are identical, they represent the same key; if the references differ, use `equals` according to `HashMap`'s rules to confirm.
4. If an equal key is found, return the value associated with that key; if not found, return `null`. Note that `get` returning `null` can also happen because the key exists but is mapped to the **value `null`**; use `containsKey` to distinguish when needed.

The pseudocode **only illustrates the idea**, not `HashMap` source code or the specific bucket algorithm of any JDK version:

```text
find(queryKey):
    hash = hashOf(queryKey)
    candidates = locateCandidateGroup(hash)

    for each storedEntry in candidates:
        if hashesMayMatch(storedEntry, hash):
            if sameReference(storedEntry.key, queryKey)
               or keysAreEqual(storedEntry.key, queryKey):
                return storedEntry.value

    return NOT_FOUND
```

The actual implementation optimizes hash distribution, checks hashes stored in nodes, and may use a tree-like structure for large collision groups. The exact order of check branches depends on the JDK source code. **The semantic invariant** is that narrowing down using only the hash is not enough; distinct keys with the same hash must still be distinguished.

For `HashSet<E>`, the analogous question is "is this element already in the set?". `HashSet` relies on an internal `HashMap` to manage element presence: `hashCode` assists with locating, while `equals` decides semantically duplicate elements.

### Example flow diagram

```text
Query: get(k)
       |
       v
Get hash code / handle null case
       |
       v
Route to candidate group
       |
       v
Inspect a candidate key
       |
       +-- Hash does not match --------> Skip candidate
       |
       +-- Hash matches
                 |
                 v
          Same reference or
          equal by equals?
            |             |
           Yes           No
            |             |
            v             v
         Key hit     Check next
            |
            v
      Return value
```

This diagram describes **why** two layers of checking are needed; it does not promise that the hash table is always implemented as a linked list, performs only one `equals` call, or always traverses elements in a fixed order.

## 3. Hash Collision: Same Hash Can Still Be Different

A Java `hashCode()` only returns a 32-bit `int`. Meanwhile, the number of objects and value states can be far larger than the number of `int` values. Therefore, **a hash cannot be required to be a unique identifier** for all objects.

For two objects `a` and `b`:

| Relationship | Correct conclusion | Consequence when using hash structures |
| --- | --- | --- |
| `a.equals(b) == true` | Must have `a.hashCode() == b.hashCode()` if implemented according to the contract. | Both keys represent the same logical key; adding an equal key to `HashMap` updates the value associated with that key. |
| `a.hashCode() == b.hashCode()` | **Does not imply** `a.equals(b)`. | Distinct keys can still coexist; the structure needs to check equality. |
| `a.hashCode() != b.hashCode()` | Under a valid contract, `a.equals(b)` must be `false`. | A hash structure may exclude this pair during search; if `equals` instead returns `true`, the class has violated the contract. |
| `a.equals(b) == false` | Hashes may be equal or different. | There is no requirement for distinct hashes for distinct keys. |

Pairs of keys with matching hashes form a group that needs further distinction; collisions are normal, not a bug in `HashMap`.

Do not confuse **hash collision** (two distinct keys having the same hash value) with **bucket collision** (two different hashes being mapped into the same region/bucket due to the table's finite capacity). Both can cause multiple candidates to be examined in the same group. That is why even well-distributed hashes still need the confirmation step.

### Do we need a distinct hash for every object?

No. A good hash code tries to **spread out** distinct keys to reduce the number of candidates that must be compared; it must never break the correctness of `equals`. Two equal objects must use the same hash; two unequal objects can collide while the program remains functionally correct, only potentially slower.

An implementation `hashCode() { return 7; }` can be **valid under the contract** if `equals` is valid, because every equal pair has the same hash. However, it is terrible for performance when the number of keys is large: the hash structure can no longer route searches well.

## 4. Standalone Java 17+ Example: Collisions Still Find the Right Key

The program illustrates two phenomena:

- Two different strings `"Aa"` and `"BB"` intentionally share the same `String.hashCode`. `HashMap` still stores and retrieves both values.
- The `ConstantHashKey` class has a hash code that is **always 7** while `equals` compares by `id`. This is a way of actively creating collisions to see that `HashSet` still distinguishes elements.

Save all the code in the file `HashAndEqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashAndEqualityDemo {
    static final class ConstantHashKey {
        private final String id;

        ConstantHashKey(String id) {
            this.id = Objects.requireNonNull(id, "id");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof ConstantHashKey that)) {
                return false;
            }
            return id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return 7; // Valid contract, poor distribution: for illustration only.
        }
    }

    public static void main(String[] args) {
        String first = "Aa";
        String second = "BB";

        System.out.println("first hash: " + first.hashCode());
        System.out.println("second hash: " + second.hashCode());
        System.out.println("same hash: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("strings equal: " + first.equals(second));

        Map<String, Integer> map = new HashMap<>();
        map.put(first, 10);
        map.put(second, 20);
        System.out.println("map size: " + map.size());
        System.out.println("get Aa: " + map.get("Aa"));
        System.out.println("get BB: " + map.get("BB"));

        Set<ConstantHashKey> set = new HashSet<>();
        set.add(new ConstantHashKey("alpha"));
        set.add(new ConstantHashKey("beta"));
        set.add(new ConstantHashKey("alpha"));
        System.out.println("set size: " + set.size());
        System.out.println("contains new alpha: "
                + set.contains(new ConstantHashKey("alpha")));
        System.out.println("contains new gamma: "
                + set.contains(new ConstantHashKey("gamma")));

        Map<String, String> nullableValues = new HashMap<>();
        nullableValues.put("exists", null);
        System.out.println("get missing is null: "
                + (nullableValues.get("missing") == null));
        System.out.println("get exists is null: "
                + (nullableValues.get("exists") == null));
        System.out.println("contains missing: "
                + nullableValues.containsKey("missing"));
        System.out.println("contains exists: "
                + nullableValues.containsKey("exists"));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac -encoding UTF-8 HashAndEqualityDemo.java
java HashAndEqualityDemo
```

Standard output:

```text
first hash: 2112
second hash: 2112
same hash: true
strings equal: false
map size: 2
get Aa: 10
get BB: 20
set size: 2
contains new alpha: true
contains new gamma: false
get missing is null: true
get exists is null: true
contains missing: false
contains exists: true
```

**Mechanism explanation:**

1. Both `"Aa"` and `"BB"` yield hash `2112`. If `HashMap` used only the hash code to confirm keys, these two elements would be wrongly merged; however, `String.equals` distinguishes them, so `map.size()` is `2`.
2. `map.get("Aa")` retrieves `10` and `map.get("BB")` retrieves `20` because the query matches the right key through both hash and equality comparison, not because every key must have a different hash.
3. `ConstantHashKey("alpha")` and `ConstantHashKey("beta")` both have hash `7` yet are not equal, so `HashSet` holds two elements. The two newly created `ConstantHashKey("alpha")` objects on the first and third additions are **equal**, so the third addition does not increase the set size.
4. When calling `contains(new ConstantHashKey("alpha"))`, a new query object can be used and still find the equivalent element. Conversely, `"gamma"` has no equal element in the set despite having the same hash.
5. Both `get(...) == null` expressions result in `true` yet carry different meanings: the key `"missing"` does not exist, whereas the key `"exists"` exists with a `null` value. `containsKey` resolves this ambiguity.

The example deliberately uses a constant hash code to prove correctness under collisions; **this approach should not be chosen for real-world keys with many values**.

## 5. Why Must `equals` and `hashCode` Be Designed as a Pair?

Java's fundamental contract is:

> If `a.equals(b)` is `true` then `a.hashCode() == b.hashCode()` must be `true`, as long as the state used for comparison has not changed.

This one-way contract allows the hash table to use the hash to narrow down the search **without missing an equal key**. If two keys are considered equal by `equals` yet have different hashes, the query process can go to a different group and fail to match the stored key. When that happens, operations like `get`, `containsKey`, `contains`, duplicate-key detection, or element removal may return inappropriate results.

Example of **flawed design** (abbreviated snippet, not a standalone program):

```java
@Override
public boolean equals(Object other) {
    return other instanceof BadKey that
            && id.equalsIgnoreCase(that.id);
}

@Override
public int hashCode() {
    return id.hashCode(); // WRONG: hash is case-sensitive.
}
```

Suppose `BadKey("java").equals(BadKey("JAVA"))` is `true`, yet the hashes of the original strings differ. The two calculations are incompatible. The fix depends on the business rule: either use a **single normalized key** for both methods (and ensure the domain/normalization algorithm matches the policy), or make both methods compare/distinguish case alike.

For a value class such as `ProductCode`, a valid contract example is:

```java
// Illustration in class ProductCode with field final String code.
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof ProductCode that
                && code.equals(that.code));
}

@Override
public int hashCode() {
    return code.hashCode();
}
```

This snippet only illustrates the method pair inside a class where `code` is non-`null`; it does not run standalone. Key point: **the same equality criterion leads to the same hashing criterion**.

### Can a good hash replace `equals`?

No. Even a hash combined from multiple fields with good dispersion is still just an `int` value; two different values can collide on the hash. The following code is **wrong if used to conclude object equality**:

```java
// WRONG: matching hashes do not prove two objects are equal.
boolean same = left.hashCode() == right.hashCode();
```

If you need to compare values, use the real equality rule (`equals` or a published business comparison API). If you need a key for hash structures, implement both `equals` and `hashCode`.

## 6. When Does a Hash Stop Routing to the Right Key?

### Key mutates after storage

Suppose a key object has a mutable `id` field and `hashCode` depends on `id`. Steps:

1. `map.put(key, value)` places the node into the region chosen according to the **hash at insertion time**.
2. The program modifies `key.id`, causing `hashCode()` to change.
3. `map.get(key)` uses the **new hash** to route the search; the old node remains at the position for the old hash, so `get` may fail to find it even when passing the exact same `key` reference.

The problem here is not "having modified the hash inside the table" but that **the table does not automatically know that the key object outside the table was modified and does not automatically move the node**. Even if the hash does not change, mutating the fields in `equals` while acting as a key can also produce unexpected results such as duplicate logical keys.

The safest approach is to choose **immutable keys**: the fields participating in `equals` and `hashCode` do not change during the lifecycle of being used as a key. If changing a logical key is unavoidable, you usually need to remove the entry under the old key before mutating and re-insert with the new key; for sets, consider creating a new key object rather than modifying an object currently in the set.

### `hashCode` depends on the environment or random outcomes

`hashCode` must remain stable across invocations on the same object when the fields used for `equals` have not changed. A hash generated randomly on each call, depending on the current time, or relying on external state that changes unpredictably will make search routing inconsistent.

Java hash codes **are not guaranteed to be stable across processes or application versions**, unless a specific API/implementation documents otherwise. Do not arbitrarily store `Object.hashCode()` as a persistent identifier of a record or protocol.

## 7. Performance Cost: Hash Reduces Candidates, Equals Does the Exact Work

For a hash table with good distribution and reasonable load, insert/lookup/delete operations typically have an expected cost near **O(1)**. However, this is an average/expected complexity under suitable conditions, not a promise that every operation always performs only one hash and one comparison.

When too many keys collide:

- More candidates must be distinguished; the number of equality checks can increase.
- Expensive `equals` (comparing long strings, deep data graphs, external queries) can noticeably increase time. Do not perform I/O, database calls, or operations with side effects inside `equals`.
- `HashMap` in modern Java versions optimizes buckets with tree structures in certain situations; you should not infer exact complexity for every scenario solely from a "bucket is a list" model. With different hashes and key types, performance depends on data, element count, and JDK details.
- Designing a simple, consistent `hashCode` with good distribution over meaningful fields helps reduce candidates; **do not try to compute a hash more expensive than a full comparison just to avoid all collisions**.

We can picture two separate quality criteria:

| Property | Related mechanism | Consequence when poor |
| --- | --- | --- |
| **Correctness** | `equals` matches the equality relation; `hashCode` is compatible with `equals` | Can mis-find/lose keys, duplicate logical elements, or cause abnormal collection behavior. |
| **Performance** | Well-distributed hash, immutable keys, sufficiently cheap `equals` | Many collisions force comparing many candidates; increases operation time. |

A constant hash with a valid `equals`: **functionally correct but usually slow**. A very well-distributed hash with a contract-violating `equals`: **may be fast but returns wrong results**. Correct semantics must be prioritized before optimization.

## 8. Common Boundaries and Confusions

### 8.1. Where to use `==` and where to use `equals`?

- For object references, `a == b` only determines whether two variables point to the same object (or are both `null`); it does not inherently understand two separately created objects that have the same value.
- A hash structure implementation may optimize the case where two keys are the **same reference**, because an object cannot differ from itself under the `equals` contract. That does not mean hash tables only use `==`.
- `equals` defines the value/domain equality relation of the key type. If a class does not override `Object.equals`, the default remains reference identity.

### 8.2. How does `HashMap` handle the `null` key?

`HashMap` allows one `null` key, and `HashSet` allows a `null` element. In this case it is impossible to call `null.hashCode()` or `null.equals(...)`; the collection implementation handles it specially. Do not interpret the two-step diagram as "always calling `key.hashCode()` directly" for all keys, including `null`.

`null` key policies differ across collections: for example, `ConcurrentHashMap` does not allow `null` keys or values. Choose the appropriate collection rather than assuming every Map handles `null` like `HashMap`.

### 8.3. Why are `TreeMap` / `TreeSet` different?

`TreeMap` and `TreeSet` use **comparison order** via `Comparable` or `Comparator` to locate and determine duplicate keys, rather than using `hashCode` for routing like hash tables. For sorted trees, the result `compare(a, b) == 0` plays a key role for duplicate keys. Consequently, two objects can be treated differently between `HashSet` and `TreeSet` if the comparator is inconsistent with `equals`.

This is why you must know the mechanism of the collection you are using: "key lookup" does not always mean "hash code hashing".

### 8.4. Is `hashCode` encryption or a secure identifier?

No. `Object.hashCode()` / `String.hashCode()` and hash functions meant for collections are not cryptographic hash functions. They are not designed to prevent tampering, store passwords, act as signatures, or verify downloaded files. Those requirements must use appropriate cryptographic algorithms/APIs; in this lesson, "hash" means **query routing** inside data structures.

### 8.5. When overriding `equals` without overriding `hashCode`

Two objects with different references can be considered equal by `equals` yet still receive different default hash codes. Then `HashSet.contains`, `HashMap.get`, or duplicate-key detection may return wrong results. Java does not automatically fix `hashCode` when you override `equals` on an ordinary class.

With `record`, Java automatically generates value implementations for `equals` and `hashCode` based on the record components; however, if a component is a reference to mutable data, the mutable-key issue still needs to be considered.

## 9. Design and Testing Process

When you need to create a new key type for `HashMap`/`HashSet`:

1. **Define the equality relation:** which fields form the logical identity? Is comparison case-sensitive? How are `null` and subclasses handled?
2. **Implement `equals(Object)`:** guarantee reflexivity, symmetry, transitivity, consistency, and non-equality to `null`; ensure two objects with different references but equivalent values are still confirmed.
3. **Implement `hashCode()` on the same data:** every equal pair has the same hash code. Do not use extraneous data or non-deterministic sources.
4. **Choose immutable keys:** especially when used in heavily operated collections or shared across application layers.
5. **Test intentional collisions:** create at least two distinct keys with the same hash. Both must coexist if `equals` differs; look up each key accurately.
6. **Test multiple equal objects:** create multiple independent instances representing one value; verify `contains`/`get` returns properly, re-adding does not create duplicate logical keys, and values update properly.
7. **Test non-existent keys:** hashes may collide yet search must still report absence; separate the absent-key case from a `null` value via `containsKey`.
8. **Evaluate hash distribution and `equals` cost:** optimize only once semantic tests are already correct; measure with representative data.

A reference test table:

| Operation | Test data | Expected outcome |
| --- | --- | --- |
| `map.put(a, value1)` then `map.get(b)` | `a.equals(b) == true`, `a` and `b` are separate instances | Finds `value1`, hashes of both keys are equal. |
| `map.put(a, value1)` and `map.put(c, value2)` | `a.equals(c) == false` yet hashes collide | Map has two keys; each `get` returns the right value. |
| `set.add(a)` then `set.add(b)` | `a.equals(b) == true` | Second addition returns `false`, size does not increase. |
| `set.contains(c)` | `c` equals no element even if hash collides | Returns `false`. |
| `map.get(k)` / `map.containsKey(k)` | `get` result is `null` | Distinguishes absent key from present-null value. |
| Lookup after key's `hashCode` field is modified | Mutable key (controlled experiment) | Exposes inconsistent lookup risk, prompting redesign to immutable key. |

No single test proves every pair of values satisfies the contract; test both the mathematical properties of `equals` and collection behaviors with equal, distinct, and colliding pairs.

## 10. Conclusion

In Java hash structures, `hashCode` assists with **routing toward potentially matching keys**, while `equals` **confirms whether two keys are truly equal**. Same hash does not prove same key; same key by `equals` strictly requires same hash. Collisions are not bugs, and Java collections are designed to handle them properly when keys obey the contract. Design `equals`/`hashCode` consistently, prefer immutable keys, test intentional collision cases, and separate semantic correctness requirements from performance optimization goals.