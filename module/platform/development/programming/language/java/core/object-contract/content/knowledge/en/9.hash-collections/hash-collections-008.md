# Distinguishing the API Contract From Internal Hash Table Organization in Java

## 1. Two Layers to Distinguish

When working with `HashMap`, `HashSet`, and hash structures in Java, there are two different questions:

- **API contract:** What behavior can a caller rely on when calling `put`, `get`, `containsKey`, `add`, `contains`, `equals`, or `hashCode`? What is guaranteed by the Java type's documentation?
- **Internal organization (implementation):** How does the library organize elements into buckets, how does it pick bucket indices, handle collisions, expand the table, and optimize lookups?

**The outer layer is the guarantee; the inner layer is the mechanism for fulfilling that guarantee.** Correct application code should rely on behaviors specified in the contract of the type it uses. Concrete details of an implementation can change across JDK versions or across libraries, even while public behavior remains the same.

Distinguish further **three contract levels** that frequently appear together:

1. `Object.equals(Object)` and `Object.hashCode()` define how objects express their equality relation and hash code. This is the responsibility of the *key/element type*.
2. `Map<K,V>` and `Set<E>` specify collection semantics, such as unique keys by equality and non-repeating set elements.
3. `HashMap` and `HashSet` are concrete implementation classes, with some additional public behaviors (such as `HashMap` accepting `null`) and many implementation details that application code should not depend on.

A characteristic not guaranteed by `Map` in general can still be **promised in the API of a specific implementation class**. Conversely, an incidental observation on one JVM does not by itself turn that behavior into a contract.

## 2. Behaviors You Must Rely On Under the Contract

### 2.1. Key equality and hash codes

For non-`null` keys, the foundational rules are:

- If `a.equals(b)` is `true`, **it is mandatory** that `a.hashCode() == b.hashCode()`.
- If `a.equals(b)` is `false`, the hash codes **may be equal or different**; two different objects having the same hash code (*collision*) is valid.
- Within a single run, if the information used in the `equals` comparison has not changed, calls to `hashCode()` on an object must be consistent.
- `equals` must also obey the clauses of reflexivity, symmetry, transitivity, consistency, and non-equality to `null`.

No clause requires a **unique hash code per key** or mandates that hash codes be positive values. The hash code is only a hint to organize searching; logical equality is what decides whether two keys represent the same entry.

### 2.2. Semantics of `Map` and `HashMap`

A `Map` represents a mapping from **each key to at most one value**. With a properly implemented `HashMap` and contract-compliant keys:

- `put(k, v)` associates value `v` with logical key `k`. If an equivalent key already exists, the old mapping is replaced; two equal keys do not create two independent entries. `HashMap.put` returns the previously associated value, or `null` if there was no prior mapping or it previously mapped to `null`.
- `get(k)` returns the value associated with the equivalent key, or `null` when there is no mapping. With `HashMap`, `null` can also be **a stored value**, so use `containsKey(k)` to distinguish the two cases.
- `size()` returns the number of current mappings; `remove(k)` removes the mapping for the equivalent key.
- `HashMap` accepts **one `null` key** and multiple `null` values. This is a property published in `HashMap`'s documentation; it must not be generalized to every `Map`. For instance, `ConcurrentHashMap` and `Map.of(...)` do not accept `null` keys or values.

Some modification operations are *optional operations* at the `Map` interface level: not every `Map` permits `put` or `remove`. `HashMap` is a class that supports those modification operations.

### 2.3. Semantics of `Set` and `HashSet`

A `Set` does not contain two equal elements. With `HashSet`:

- `add(e)` returns `true` if the new element was added, and returns `false` if an equivalent element was already present.
- `contains(e)` checks whether an equivalent element exists, regardless of whether that element has the **same address/reference** as `e`.
- Elements with the same hash code yet `equals` returning `false` **can still coexist in the set**.
- `HashSet` allows one `null` element; some other `Set` implementations may impose their own rules.

These are the things to verify through the API, without needing to know whether the set uses a bucket array, list, tree, or another organization.

## 3. Buckets, Collisions, and Resizing Belong to the Implementation Layer

You can picture the typical operation of a hash table as follows:

```text
put(key, value)
    |
    v
get key's hashCode
    |
    v
mix/transform bits (if the implementation needs to)
    |
    v
determine container/bucket from current capacity
    |
    v
process keys in the same region via equality comparison
    |
    v
add new entry or update equivalent entry
```

This is a **conceptual diagram**, not a promise about method-call order, index formula, node structure, or exact step count of a specific `HashMap` version.

Commonly encountered terms:

- **Bucket:** a slot or group holding entries distributed by the hash function. Bucket count and how hash codes map to buckets are implementation details.
- **Collision:** two keys may be examined in the same bucket, or share the same hash code, depending on phrasing. Matching `hashCode` is natural; distinct keys must still be distinguished when comparing equality.
- **Capacity:** the internal size/holding capacity of the table in a specific structure.
- **Load factor:** a parameter related to how full the table gets and the expansion policy in implementations like `HashMap`.
- **Resize/rehash:** the internal process of adjusting the structure and redistributing entries when the table needs more space.

`HashMap` has public constructors allowing callers to supply **initial capacity** and **load factor**, so those *concepts* and parameters are part of the class API. However, details like the actual bucket count after rounding, node distribution thresholds, bit-mixing scheme, or exact point of bucket treeification are not `Map` semantic rules that an application can rely on.

In some OpenJDK releases, buckets may use list nodes and occasionally switch to a tree structure to handle high-collision cases. That is useful when reading JDK source code or diagnosing performance, yet **it is not a prerequisite** for understanding and correctly using `put/get/equals/hashCode`; do not write business logic requiring a specific node count, treeification threshold, or OpenJDK internal traversal order.

## 4. Java 17 Example: Same Contract, Different Table Configurations

A common mistake when reading JDK source code is using table capacity or bucket organization to predict business outcomes. The experiment below creates two `HashMap`s with different initial capacities, inserts the same **intentionally colliding** keys, and checks only the values guaranteed by the API.

Save to `HashApiContractDemo.java`:

~~~java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

public class HashApiContractDemo {
    record Key(String id) {
        @Override
        public int hashCode() {
            return 1; // Intentionally causes collisions, still compatible with record's equals.
        }
    }

    private static String observe(Map<Key, String> map) {
        map.put(new Key("A"), "a1");
        map.put(new Key("B"), "b1");
        String old = map.put(new Key("A"), "a2");
        return "size=" + map.size()
                + ", old=" + old
                + ", A=" + map.get(new Key("A"))
                + ", B=" + map.get(new Key("B"));
    }

    public static void main(String[] args) {
        System.out.println("small: " + observe(new HashMap<>(2)));
        System.out.println("large: " + observe(new HashMap<>(128)));

        Map<String, Integer> ordered = new LinkedHashMap<>();
        ordered.put("B", 2);
        ordered.put("A", 1);
        ordered.put("B", 20);
        System.out.println("linked keys: "
                + String.join(" -> ", ordered.keySet()));
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac --release 17 HashApiContractDemo.java
java HashApiContractDemo
~~~

Output:

~~~text
small: size=2, old=a1, A=a2, B=b1
large: size=2, old=a1, A=a2, B=b1
linked keys: B -> A
~~~

The two `HashMap`s have different initial capacity parameters yet yield the exact same results through `put`, `get`, and `size`: a newly created key A still equals the stored key A, key B differs from A despite sharing a hash code, and updating A returns the old value. That is the **observable contract**. The lesson does not inspect or assert the actual number of allocated buckets, treeification threshold, or `equals()` call sequence; those factors depend on the implementation.

`LinkedHashMap` is included to contrast another guarantee: its insertion order is documented. Replacing B's value does not move B to the end in default mode, so the sequence `B -> A` can be verified. We do not check the iteration order of the two `HashMap`s because they do not promise insertion order.

The example uses a constant hash function solely to isolate the equality contract. A poorly distributed hash function can degrade performance with large datasets; operation correctness still depends on compatible `equals`/`hashCode` and stable keys.

## 5. Comparison Table: Public Guarantees vs. Internal Details

| Topic | Contract you can rely on | Details not to treat as guarantees |
| --- | --- | --- |
| Equal keys | `HashMap` does not keep two separate mappings for two equivalent keys | How many nodes are in the same bucket, in what exact order nodes are compared |
| Hash code | `equals == true` ⇒ same `hashCode`; collisions are permitted | Bit-mixing function, index extraction from hash, bucket count |
| `put/get` | Results match the key's mapping, if the key obeys the contract | Exact number of comparisons or memory accesses |
| `null` | `HashMap` supports `null` keys and values; `HashSet` supports a `null` element | How `null` is marked or stored internally |
| Ordering | `LinkedHashMap` preserves insertion order by default; `HashMap` does not guarantee order | Incidental iteration order appearing at a given capacity/JVM version |
| Collision | Distinct keys with the same hash can still coexist | Whether a bucket is a list, tree, or another optimization |
| Expansion | After expansion, mapping semantics do not change solely due to expansion | Timing, threshold, resize formula, and bucket redistribution method |
| Performance | `HashMap` has good average performance for basic operations when hashes distribute suitably | Guarantee that every `get/put` always takes strictly O(1), regardless of data |
| Concurrency | `HashMap` is not a self-synchronizing collection for concurrent modifications | Unsynchronized reads/writes "happening to work" on the current machine |

The "performance" row needs to be understood properly: `HashMap` documentation speaks of **expected performance** for `get` and `put` assuming hash values distribute reasonably. That is not a strict guarantee that every operation takes identical time regardless of collisions, resizing, size, or JVM effects. When optimizing performance, measure real workloads rather than reasoning about a hypothetical bucket.

## 6. Ordering Contract: Choosing the Right Collection

A familiar mistake is running the following code several times, seeing the same order, and assuming `HashMap` always returns items in that order. `HashMap` **does not guarantee iteration order**, nor is order guaranteed to remain fixed over time. Changes in table size, hash distribution, insert/delete history, or JDK version can alter what you observe.

If the application **truly needs ordering**, pick a type with the corresponding contract:

- **`LinkedHashMap`:** maintains insertion order by default; offers an access-order configuration for specialized problems. In default mode, updating an existing key's value does not change insertion order.
- **`TreeMap`:** key ordering is based on natural ordering or a supplied `Comparator`. For sorted maps, the comparator's comparison criterion determines key equivalence according to the map; if you want full compliance with the `Map` contract by `equals`, that ordering should be consistent with `equals`.
- **`HashMap`:** choose when you need mappings with typical hash performance and **do not need** ordering guarantees.

Do not rely on `HashMap` printing integer keys in ascending order today: for that specific set of keys/capacity, ascending order is merely an implementation artifact.

## 7. Contract With Mutable Keys: The Bug Is Not in the Bucket

You can write a class whose `equals()` and `hashCode()` both rely on a mutable `id` field. Before any mutation, both methods may satisfy the contract. However, once that object is already a key in `HashMap`, mutating `id` later means the map **has no obligation to automatically reorganize** the entry under the new hash code value.

The following is an **illustrative code snippet**, assuming `key` is an object with a setter modifying the `id` field participating in `equals/hashCode`:

```java
map.put(key, "saved");
key.setId("another-id"); // Avoid mutating identity properties of a stored key.
String value = map.get(key); // May fail to find the stored entry.
```

How to handle it: use **immutable keys** (such as `String` IDs, numbers, or records made of immutable components) or remove the old key *before* mutating and insert a new key with the new value. Mutating a stored object in place and hoping `get` still works relies on implementation luck.

A Java 17 record like:

```java
record CustomerKey(String tenantId, long customerId) {}
```

has `equals/hashCode` auto-generated from its components. It is a suitable example when all components are stable, like `String` and `long`. **A record does not automatically guarantee deep immutability** if it has a component that is an array or mutable object.

Distinguish bugs caused by **the key itself breaking the equality/hash contract** from issues caused by **bucket algorithms**. Many inconsistent lookup symptoms stem from flawed `equals/hashCode` implementations or mutating keys, not from hash table structure details.

## 8. How to Read JDK Source Without Turning It Into API?

Reading the source of `java.util.HashMap` in a specific JDK is very helpful for understanding:

- How the implementation processes hash values and maps into the current table.
- Scenarios for allocating new entries, updating entries, handling collisions, and resizing.
- How that version optimizes crowded buckets or supports iterators.
- Why a particular data pattern or workload creates CPU/memory pressure.

However, a **source observation** should be explicitly scoped, such as "in this OpenJDK release ..."; do not generalize it into a mandatory rule for all of Java. Having multiple JDKs and versions in Java makes this distinction very practical.

To know which behaviors you can **depend on**, consult the Javadoc of the exact API type and version you are using (`Map`, `Set`, `HashMap`, `HashSet`, `LinkedHashMap`, `Object`). To know **why** the current implementation is fast or slow in a scenario, read the source, run benchmarks, and use profiling tools.

The concepts "capacity" and "load factor" remain important when tuning `HashMap` configuration: they are described in the Javadoc and several public constructors. Still, exact details of bucket counts, distribution schemes, or treeification thresholds are not elevated into a contract merely because the current source uses them.

## 9. Method Call Order, Iterators, and Concurrency

### Do not assume how many times `equals()` is called

Application code should not count how many times `equals` is called during a single `get`, `containsKey`, or `put` and treat that as business behavior. Implementations may check by identity, hash, compare candidates, or apply internal optimizations. Therefore, `equals` should be a comparison **without side effects** and independent of call counts or wall-clock time.

### Do not rely on fail-fast as a synchronization mechanism

The `HashMap` documentation describes iterators as having a **fail-fast** mechanism for certain invalid structural modifications during iteration, typically throwing `ConcurrentModificationException`. However, detection behavior is **best effort**, not a guaranteed mechanism to catch every data race, nor does it make `HashMap` thread-safe.

If multiple threads modify concurrently without external synchronization, design accordingly, such as using `ConcurrentHashMap` when requirements are met. Note that `ConcurrentHashMap` has **its own contract** (for example, disallowing `null`), so it cannot be treated as an interchangeable internal implementation without checking the API.

### Distinguish interfaces from implementation classes

If you declare `Map<String, Integer> m = new HashMap<>();`, the variable `m` has type `Map`, yet the runtime object is a `HashMap`. Call behavior must adhere to the `Map` contract, plus the characteristics published by the `HashMap` class. If later switching to `Map.of(...)` or `TreeMap`, re-verify the differing characteristics (mutability, `null` acceptance, ordering) instead of assuming every `Map` is equivalent.

## 10. Real-World Scenarios for Self-Checking

**Scenario A — two different keys with the same hash.** `k1.hashCode() == k2.hashCode()` yet `k1.equals(k2) == false`. `HashSet` is allowed to hold both, and `HashMap` must be able to store both mappings if operations are valid. Do not report an error merely because of a collision.

**Scenario B — two equal keys.** `k1.equals(k2) == true` and `hashCode` has the same value. `HashMap.put(k2, newValue)` must update the equivalent mapping already added by `k1`. There is no need to know which bucket the two keys sit in.

**Scenario C — printed order always seems the same.** When iterating `HashMap`, you cannot turn observation into a contract; if insertion order is needed, use `LinkedHashMap`; if sorted order by key is needed, look at `TreeMap`.

**Scenario D — value read back is `null`.** With `HashMap`, you must check `containsKey` if you need to distinguish "key absent" from "key has value `null`". How `null` is represented inside the table is irrelevant to this decision.

**Scenario E — lost key after changing ID.** First check whether the key has a mutable field participating in `equals/hashCode`. Fix it in the key's design and lifecycle; do not patch the application by assuming a bucket-selection formula.

**Scenario F — optimizing the hash table.** Poorly distributed hash data can increase collisions and degrade performance. Adjust key selection, hash function, and capacity based on real measurements; do not use treeify/resize details of a specific JDK release as a logical condition for business correctness.

## 11. Key Takeaways

- The contract tells you **public results and semantics**; the implementation explains **how it is carried out**, which can change.
- `equals` defines logical equality, `hashCode` assists lookup organization. **Equal ⇒ same hash code**; **same hash code ⇏ equal**.
- `HashMap` does not guarantee iteration order; `LinkedHashMap` and `TreeMap` provide different ordering guarantees.
- Collisions do not mean two keys are treated as one; `HashMap` and `HashSet` must still behave properly for distinct keys.
- Initial capacity/load factor are concepts and configuration options published by `HashMap`, whereas node/tree thresholds, bucket formulas, and internal check order are not part of the `Map` contract.
- Do not mutate fields participating in `equals/hashCode` while the object is serving as a key in a hash table.
- Read the Javadoc to determine what an application **is allowed to rely on**, and read source/benchmarks to understand and optimize a **specific implementation**.