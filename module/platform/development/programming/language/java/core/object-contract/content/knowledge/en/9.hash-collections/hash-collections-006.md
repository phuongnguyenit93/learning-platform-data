# Hash Collisions Do Not by Themselves Break Correctness

## Objectives

A hash data structure such as `HashMap` or `HashSet` uses hash codes to find where to store and look up elements efficiently. Multiple objects can produce the same hash code (**hash collision**). However, **a collision by itself does not cause `HashMap` to confuse two different keys as one key or cause `HashSet` to lose elements**.

After this lesson, you will understand:

- What a collision is and why you cannot require every distinct object to have a distinct hash.
- The conceptual mechanism hash data structures use to handle multiple keys with the same hash code.
- The distinct roles of `hashCode()` and `equals()` in deciding whether a key is found, a value is replaced, or an element is allowed to be added.
- How to verify with Java 17+ that multiple keys with the same hash are still stored and retrieved accurately.
- The difference between **result correctness** and **performance**; contract bugs or key mutations that can actually cause problems.

## 1. What Is a Collision?

Java's `hashCode()` method returns an `int`, a 32-bit signed integer value. The number of objects and data states that can be created is far larger than that finite set of hash codes. Therefore, it is impossible to guarantee a unique hash code for every object.

A **hash collision** occurs when two objects or keys **differ under the equality comparison** yet produce the same hash code:

```text
a.equals(b) == false
a.hashCode() == b.hashCode()
```

This is a **valid** situation. As an imaginary example, if the hash code of a numeric key were its units digit, key 21 and key 31 would both have hash 1 yet still be two different keys. That hashing scheme may distribute poorly, yet the collision does not erase the original key information.

Even well-designed hash functions can still collide. What matters is that the storage structure knows how to **distinguish colliding keys** instead of using the hash code alone as proof that two keys are equal.

### Reviewing the relevant contract

For objects obeying the `equals()/hashCode()` contract:

| Relationship | Mandatory? |
| --- | --- |
| `a.equals(b) == true` ⇒ `a.hashCode() == b.hashCode()` | **Mandatory** |
| `a.hashCode() == b.hashCode()` ⇒ `a.equals(b) == true` | **No** |
| `a.equals(b) == false` ⇒ the two hashes must differ | **No** |

The first condition ensures that logically equal keys have compatible hash codes so the hash structure can locate and match them. The remaining two conditions permit collisions.

## 2. The Hash Code Finds Candidates, `equals()` Decides Equality

In `HashMap<K,V>`, the hash function helps narrow down the candidate search region. When multiple keys collide, the implementation still must find which key **actually equals the lookup key**. Determining equality can take advantage of a same-reference check and then call `equals()` when needed. Having the same hash code alone is not enough.

Mental model:

```text
                 map.get(key)
                     │
                     ▼
           Compute key's hash
                     │
                     ▼
       Determine candidate region
                     │
                     ▼
    Check each suitable candidate
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
      Equal key            Different key
      by equals()          even if hash matches
          │                     │
          ▼                     ▼
   Return matching       Continue searching or
       value             conclude absent
```

This is a **conceptual diagram**, not a copy of the internal source code of a specific `HashMap` version. Depending on the implementation, the table may process additional hash bits, use groups holding multiple entries, and organize groups using lists or trees when appropriate. The exact mechanism primarily affects search method and performance. `Map` semantics still require distinguishing unequal keys.

For `HashSet`, the principle is the same: an element is only considered already present if there is an element **equal to it** by the set's rule. Two different elements with the same hash are allowed to coexist.

### Illustrating a collision region

Suppose three keys have hash 5, yet only `A` and `A2` are equal:

```text
Group with hash 5:

  [Key A, value 100]    [Key B, value 200]

Key A.equals(Key B)  = false  → two entries
Key A.equals(Key A2) = true   → A2 is a key equivalent to A
```

If `put(A2, 300)` is called, the operation updates the entry for key `A`, rather than creating a third key just because `A2` is a new instance. If `put(B, 400)` is called, `A`'s data stays independent even though `B` shares the same hash. Matching hashes can make finding candidates take longer, but do not turn `B` into `A`.

## 3. Runnable Java 17+ Example: Every Key Has the Same Hash

We intentionally create a key class whose `hashCode()` always returns `1` to simulate an extreme collision scenario. This class uses a Java 17 `record`: `equals()` is generated to compare the `id` component value, while `hashCode()` is explicitly overridden to return a constant value.

This is a **pattern for observing behavior**, not a recommended hash function design for real applications.

Create the file `HashCollisionCorrectnessDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class HashCollisionCorrectnessDemo {
    record Key(int id) {
        @Override
        public int hashCode() {
            return 1; // Intentionally create collisions for all keys
        }
    }

    public static void main(String[] args) {
        Key a = new Key(10);
        Key b = new Key(20);
        Key equivalentA = new Key(10);

        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("different keys: " + !a.equals(b));
        System.out.println("equal keys: " + a.equals(equivalentA));

        Map<Key, String> map = new HashMap<>();
        map.put(a, "ten");
        map.put(b, "twenty");

        System.out.println("map size: " + map.size());
        System.out.println("get 10: " + map.get(new Key(10)));
        System.out.println("get 20: " + map.get(new Key(20)));
        System.out.println("get 99: " + map.get(new Key(99)));

        String previous = map.put(equivalentA, "TEN");
        System.out.println("previous: " + previous);
        System.out.println("map size after update: " + map.size());
        System.out.println("get 10 after update: "
                + map.get(new Key(10)));
        System.out.println("get 20 after update: "
                + map.get(new Key(20)));

        Set<Key> set = new HashSet<>();
        set.add(a);
        set.add(b);
        boolean addedEquivalent = set.add(equivalentA);

        System.out.println("set size: " + set.size());
        System.out.println("added equal key: " + addedEquivalent);
        System.out.println("set contains 20: "
                + set.contains(new Key(20)));
        System.out.println("set contains 99: "
                + set.contains(new Key(99)));
    }
}
```

Compile and run on JDK 17+:

```bash
javac HashCollisionCorrectnessDemo.java
java HashCollisionCorrectnessDemo
```

**Exact output:**

```text
same hash: true
different keys: true
equal keys: true
map size: 2
get 10: ten
get 20: twenty
get 99: null
previous: ten
map size after update: 2
get 10 after update: TEN
get 20 after update: twenty
set size: 2
added equal key: false
set contains 20: true
set contains 99: false
```

Explanation of each group of results:

1. `a` and `b` share hash `1`, yet `record Key(int id)` has `equals()` based on `id`, so `a.equals(b)` is `false`.
2. Both `map.put(a, ...)` and `map.put(b, ...)` store **two separate keys**; `map.size()` is `2`, not `1`.
3. `map.get(new Key(10))` retrieves the value `"ten"` even though the query object was just created, because the query key equals `a` by `equals()`. Same for `Key(20)`.
4. `map.get(new Key(99))` is `null` because there is no equivalent key; the fact that `Key(99)`'s hash is also `1` **does not cause the program to retrieve the wrong value** of another key.
5. `map.put(equivalentA, "TEN")` replaces the value of key `Key(10)`, returning the previous value `"ten"`. The key count stays `2`, and the value of `Key(20)` remains `"twenty"`.
6. `HashSet` stores two elements `Key(10)` and `Key(20)`. Adding `equivalentA` fails because an equal element already exists, not because of a collision. Afterward, `contains(Key(20))` is true, while `contains(Key(99))` is false.

The program only prints deterministic query calls, without relying on `HashMap`/`HashSet` iteration order. As a result, the output is clear and independent of the hash structure's ordering.

## 4. Why Is a Constant Hash Function Still Logically Correct?

A `hashCode()` that always returns `1` satisfies the core conditions of the contract:

- On the same object whose equality-determining data does not change, hash calls return consistent results.
- If two objects are equal by `equals()`, both also have hash `1`.
- If two objects are **not** equal, Java **does not require** different hash codes.

Therefore, every entry can use a constant hash while the hash structure still preserves business results, provided the keys obey the contract, the state used for comparison remains stable while stored, and the structure is used properly.

Even so, this implementation is a **poor performance choice**. A large collection holding thousands of distinct keys sharing the same hash may have to check many more candidates than when hashes are well distributed. A `HashMap` implementation may use a different data structure to reduce cost in some situations, yet there is no reason to intentionally create all-key collisions in a real application.

It can be said:

> **A good hash function helps efficiency; a proper `equals()` with a compliant `hashCode()` contract ensures correctness.**

This statement does not mean performance is always completely separated from real-world experience: excessive collisions can make operations slow enough to cause timeouts or degrade service availability. However, that is a performance/availability consequence, distinct from `HashMap` silently merging two unequal keys into one.

## 5. Comparing the Impact on Three Key Operations

### 5.1. `put(key, value)`

When adding an entry with a key not equal to any existing key, `HashMap` must store it as a separate entry even if hashes collide. When adding a key **equal** to an existing key, `put` updates the value currently associated with that key.

For example, `new Key(10)` and `new Key(20)` both have hash 1 yet exist side by side. Meanwhile, the second `new Key(10)` equals the old `Key(10)`, so it updates the entry of the same logical key.

### 5.2. `get(key)` and `containsKey(key)`

The hash helps determine the candidate region. When keys have colliding hashes, the operation must still use equality semantics to select the right result.

If `Key(10)` and `Key(20)` are present, querying `Key(99)` yields `null` from `get` and `false` from `containsKey` even though all have hash 1.

**Note:** `map.get(key) == null` does not always prove a key is absent, because `HashMap` permits an entry with a `null` value. When you need to distinguish "key absent" from "key present with `null` value", use `containsKey(key)`.

### 5.3. `HashSet.add(element)` and `contains(element)`

In `HashSet`, if an element **differs** by `equals`, it is added even if hashes collide. If the element equals an existing element, the `add` call returns `false`.

The duplication condition is **equality under the element's contract**, not merely equal `hashCode()`. This is why in the example adding `equivalentA` does not increase the set size, while adding `b` does.

## 6. The Boundary Between Performance and Correctness

| Aspect | What many collisions can cause | What collisions by themselves do not cause |
| --- | --- | --- |
| Key storage | Multiple entries must share one region or candidate group | Do not automatically delete keys differing by `equals` |
| Lookup | May spend extra work distinguishing candidates | Do not automatically make `get` return the value of a key unequal to the query key |
| `HashSet` | May increase insertion and membership-check cost | Do not automatically reject distinct elements merely because hashes collide |
| Data growth | Performance can degrade when hash distribution is poor | Does not change the logical contract of `Map`/`Set` |

Regarding complexity, operations on a hash table are typically expected to be efficient on average when hash distribution is good. Under very poor distribution, processing many candidates can take significant time. Do not state a single fixed complexity for **all** implementations and circumstances, because Java can optimize bucket handling depending on table size, entry count, and key type.

When evaluating a real application, a good hash function should have distribution suitable enough for the data in use, return stable results per the contract, and be compatible with `equals`. You cannot evaluate key correctness solely by counting collisions; you must also verify the `equals` rules.

## 7. What Problems Can Actually Cause Hash Structures to Return Wrong Results?

Valid collisions differ from the following bugs.

### 7.1. Violating the mandatory direction of the `equals()/hashCode()` contract

Suppose two objects are considered equal by `equals` yet `hashCode()` differs:

```text
a.equals(b) == true
a.hashCode() != b.hashCode()  // Contract violation
```

This is a design bug in the key class. When a collection relies on hashes to narrow down lookups, logically equal keys with incompatible hash codes may fail to find each other or produce unwanted duplicates.

Example of an **anti-pattern** inside a class with fields `int id` and `String name`:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return id == other.id;
}

@Override
public int hashCode() {
    return java.util.Objects.hashCode(name); // Violates contract
}
```

This is a **bug-illustration snippet, not a standalone program**. Two objects with the same `id` but different `name`s are considered equal, while their hashes can differ. The fix is to compute the hash consistently from `id` if `id` is truly the sole field determining equality.

Do not try to "fix collisions" by giving every object a different hash at all costs; doing so does not resolve the contract between `equals` and `hashCode`.

### 7.2. Mutating a key field after insertion

Suppose a key is added to `HashMap` with a hash computed from `id = 10`. Later, the program modifies `id` to `20`, causing the new hash to differ from the hash used at insertion. Lookup may go to a different candidate group and fail to find the entry.

This is a **bug caused by key state mutation**, not a collision. Especially for fields participating in `equals/hashCode`, use immutable keys or a strategy of removing and re-adding when changes are needed.

The `record Key(int id)` keys in the example have no setters, and the primitive component `id` is immutable, thus avoiding this case.

### 7.3. `equals()` lacking symmetry, transitivity, or consistency

If `a.equals(b)` and `b.equals(a)` give different results, or the equality relation changes erratically when relevant data has not changed, hash structures can hardly operate as expected. The issue stems from the key class's contract, not merely from two matching hash values.

### 7.4. Improper concurrent usage

Standard `HashMap` and `HashSet` do not provide thread safety for concurrent read/write operations. If multiple threads mutate the structure without proper synchronization, the program can exhibit unexpected behavior. This is a **concurrent access** issue, not incorrectness of the collision-handling algorithm.

If a concurrent structure is needed, choose a compatible one such as `ConcurrentHashMap` and synchronization mechanisms suited to the application's requirements; do not blame collisions when the cause is a race condition.

## 8. Common Thinking Mistakes

1. **"When two keys have the same hash, the second entry overwrites the first."** False. `HashMap` updates when keys are equal by key semantics; a collision is not enough.
2. **"`HashSet` holds at most one element per hash."** False. Multiple elements differing by `equals` can share the same hash and coexist.
3. **"Having no collisions proves the code is correct."** False. Having no collisions in test data does not guarantee `equals/hashCode` obey the contract.
4. **"A collision occurring means data loss."** False. A proper hash structure must have a mechanism to distinguish colliding keys.
5. **"A unique hash is an object identifier."** False. An `int` value is not guaranteed unique; nor does `hashCode()` mean memory address.
6. **"As long as `hashCode()` matches, you can skip calling `equals()`."** False. If you build your own hash structure, this can be a severe bug merging two distinct keys.
7. **"Always returning hash 1 is good practice because it still runs correctly."** False. It may obey the contract yet causes poor distribution, significantly hurting performance.
8. **"Seeing wrong `get` results must be due to collisions."** First check the `equals/hashCode` contract, key stability, `null` policy, operation logic, and concurrent access.

## 9. Reasoning Exercise Without Running the Program

Given the `Key` class from the example with `hashCode() == 1` for every instance and `equals` comparing `id`, trace step by step:

```java
Map<Key, String> map = new HashMap<>();

map.put(new Key(1), "A");
map.put(new Key(2), "B");
map.put(new Key(1), "A2");

int size = map.size();
String one = map.get(new Key(1));
String two = map.get(new Key(2));
String unknown = map.get(new Key(3));
boolean presentThree = map.containsKey(new Key(3));
```

This snippet must be placed inside a method with the required imports and access to `record Key` defined in the program in section 3.

**Answers:**

- `size == 2` because `Key(1)` and `Key(2)` are two distinct keys, while the second `Key(1)` only updates the value.
- `one` is `"A2"` because the new value replaced the old value of the equivalent key `Key(1)`.
- `two` is `"B"` because a collision does not overwrite key `Key(2)`.
- `unknown == null` and `presentThree == false` because `Key(3)` equals none of the stored keys, even though its hash is still `1`.

Try replacing `Key` with a type having better hash distribution while keeping the same equality definition by `id`. If the implementation still obeys the contract and key state does not change, the business results above **must remain identical**; only distribution and performance may differ.

## 10. When Should You Take Action in a Real Project?

If you observe many collisions or slow `HashMap` operations, evaluate hash code distribution against **real data** and the `hashCode()` implementation. Cases where large numbers of keys share a hash can degrade performance; testing with representative data is more useful than assuming hashes are always random.

If instead you observe keys "disappearing", multiple equal keys appearing together, or `HashSet.contains` returning abnormal results, check in order:

1. Does `equals()` obey reflexivity, symmetry, transitivity, consistency, and proper `null` handling?
2. Do two equal objects always produce the same hash?
3. Do fields participating in equality and hash change after insertion?
4. Is code concurrently accessing a non-thread-safe structure or misusing a related API?
5. Is `Map.get` returning `null` being confused with the absence of a key that has a `null` value?

These steps focus on causes that can produce wrong behavior. Valid collisions are simply a characteristic to be handled properly by the hash structure and may need performance optimization when frequency is excessive.

## Key Takeaways

**A hash collision is when multiple distinct keys produce the same hash code; it does not mean the keys are equal or data is lost.** `HashMap` and `HashSet` distinguish keys/elements by equality semantics, so they can hold multiple keys with the same hash while still looking up and updating accurately. Too many collisions can slow down operations; `equals/hashCode` contract bugs, mutated keys, or improper structure usage are the real sources of risk to correctness.