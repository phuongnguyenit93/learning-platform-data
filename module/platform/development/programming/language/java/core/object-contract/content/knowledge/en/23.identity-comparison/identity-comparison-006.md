# IdentityHashMap: Why It Intentionally Differs from the Standard Map Contract on Comparison Semantics

In Java, `IdentityHashMap<K, V>` implements the `Map<K, V>` interface yet **intentionally uses object identity (reference identity, the `==` operator)** to distinguish keys and compare values, instead of logical equality (`equals()`). This is a publicly documented exception in the API, suitable for certain specialized problems; it is not a bug in `IdentityHashMap`.

Key point to remember: **two objects with `equals() == true` can still be two distinct keys in `IdentityHashMap`**. When comparing this map against a standard map such as `HashMap`, even `Map.equals()` may cease to be symmetric.

## 1. Distinguishing value equality and identity equality

Suppose:

```java
String a = new String("java");
String b = new String("java");

System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false
```

- `a.equals(b)` returns `true` because both strings carry the same content.
- `a == b` returns `false` because `new` creates two separate objects.
- Having `equals()` return `true` does not mean two variables point to the same object. Having the same reference always makes `==` `true`, regardless of how the class overrides `equals()`.

For keys in `HashMap`, Java uses `hashCode()` and `equals()` to find logically equivalent keys. `IdentityHashMap` uses `==` combined with the identity hash code (`System.identityHashCode()`). The identity hash code is only a lookup aid: **two different objects can still share the same identity hash code**, and the map must distinguish them using `==`. This hash code is neither a memory address nor an absolute unique ID.

| Scenario | Ordinary `HashMap` | `IdentityHashMap` |
| --- | --- | --- |
| Two keys with the same reference | Same key | Same key |
| Two keys with different references where `equals()` is `true` | Same key if obeying the `hashCode/equals` contract | Two separate keys |
| `get(key)` / `containsKey(key)` | Based on logical equivalence of the key | Based on the exact stored reference |
| `containsValue(value)` | Compares via `equals()` | Compares via `==` |
| Two entries with content-equal key/value but different references | Can be the same mapping | Not the same mapping by identity |

**Note:** `IdentityHashMap` does not hash by value; value identity checking appears in `containsValue()` and entry/map comparison operations. `get()` still selects a mapping based on **key identity**.

## 2. What exactly is "violating the Map contract"?

The standard `Map` contract describes key equivalence based on `equals()` and map equality based on equivalent mappings. `IdentityHashMap` implements `Map` operations yet intentionally replaces key/value equivalence criteria with **same object reference**.

Important consequences:

1. **Key uniqueness changes.** `put(k1, v1)` followed by `put(k2, v2)` does not replace the old mapping just because `k1.equals(k2)` is `true`; both keys must be the exact same object.
2. **`IdentityHashMap.equals(other)` evaluates mappings by identity.** The specification expresses it as `this.entrySet().equals(other.entrySet())`, where `IdentityHashMap` entries use reference semantics.
3. **Comparing with a standard map can be asymmetric:** cases exist where `normalMap.equals(identityMap) == true` while `identityMap.equals(normalMap) == false`. The Javadoc also warns that `Object.equals` transitivity (`transitivity`) may be violated when mixing map types.
4. **A map's `hashCode()` is based on entries with identity semantics.** The rule "equal maps have equal hash codes" is guaranteed when comparing between `IdentityHashMap` instances; when cross-comparing with standard maps, you cannot assume that rule still holds.

Key takeaway: **across `IdentityHashMap` instances, the `equals/hashCode` contract is still upheld**; risks arise when code applies assumptions of `HashMap`/ordinary `Map` or cross-compares different map types.

## 3. Java 17+ example: demonstrating the difference and asymmetry

Save as `IdentityMapContractDemo.java`:

```java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityMapContractDemo {
    public static void main(String[] args) {
        String k1 = new String("code");
        String k2 = new String("code");
        String v1 = new String("same");
        String v2 = new String("same");

        Map<String, String> normal = new HashMap<>();
        Map<String, String> byIdentity = new IdentityHashMap<>();

        normal.put(k1, v1);
        normal.put(k2, v2);
        byIdentity.put(k1, v1);
        byIdentity.put(k2, v2);

        System.out.println("k1.equals(k2) = " + k1.equals(k2));
        System.out.println("k1 == k2 = " + (k1 == k2));
        System.out.println("HashMap.size = " + normal.size());
        System.out.println("IdentityHashMap.size = " + byIdentity.size());
        System.out.println("IdentityHashMap.containsKey(new key) = "
                + byIdentity.containsKey(new String("code")));
        System.out.println("IdentityHashMap.containsValue(new value) = "
                + byIdentity.containsValue(new String("same")));
        System.out.println("IdentityHashMap.containsValue(v1) = "
                + byIdentity.containsValue(v1));

        // Same key object, two different value objects with equals() == true.
        Object sharedKey = new Object();
        Map<Object, String> regularOne = new HashMap<>();
        Map<Object, String> identityOne = new IdentityHashMap<>();
        regularOne.put(sharedKey, new String("same"));
        identityOne.put(sharedKey, new String("same"));

        System.out.println("HashMap.equals(IdentityHashMap) = "
                + regularOne.equals(identityOne));
        System.out.println("IdentityHashMap.equals(HashMap) = "
                + identityOne.equals(regularOne));
    }
}
```

Compile and run:

```bash
javac IdentityMapContractDemo.java
java IdentityMapContractDemo
```

Standard output:

```text
k1.equals(k2) = true
k1 == k2 = false
HashMap.size = 1
IdentityHashMap.size = 2
IdentityHashMap.containsKey(new key) = false
IdentityHashMap.containsValue(new value) = false
IdentityHashMap.containsValue(v1) = true
HashMap.equals(IdentityHashMap) = true
IdentityHashMap.equals(HashMap) = false
```

Explanation:

- The two key strings have identical content but are different objects. `HashMap` retains one mapping because the second key is equivalent to the first; `IdentityHashMap` retains both because `k1 != k2`.
- Creating a new string `new String("code")` for lookup fails to find the key in `IdentityHashMap` despite identical content. Similarly, `containsValue(new String("same"))` is `false`; passing the exact `v1` object gives `true`.
- At the end, both maps contain **the exact same `sharedKey` object**, while the values are two `String` objects with different references and identical content. `HashMap.equals` accepts `equals()`-equivalent values, returning `true`. `IdentityHashMap.equals` requires the exact value reference, returning `false`. This is a concrete counterexample to symmetry, **not** a random artifact of iteration order or hash collisions.

**Do not use `System.identityHashCode(...)` to predict output:** hash numbers can differ across runs, do not indicate map ordering, and do not prove two references are the same object.

## 4. Impact on APIs, collection views, and map conversion

### Lookup operations

- `put(k, v)` replaces the value only when a mapping already exists for **the exact object `k`**; a new key object with identical content is added as a new mapping.
- `get(k)`, `containsKey(k)`, `remove(k)` look up by key identity. `get(k) == null` may mean the key is absent **or** the key maps to `null`; use `containsKey(k)` to distinguish.
- `containsValue(v)` uses value identity, not `v.equals(...)`.
- `IdentityHashMap` allows one `null` key and `null` values.

### `keySet()`, `entrySet()`, `values()`

- `keySet()` is an **identity-based set**: two keys that are different objects yet have `equals() == true` both appear. Do not assume this view compares with any `HashSet` under standard `Set.equals` conventions.
- `entrySet()` represents mappings by identity of **both key and value**. This forms the basis of `IdentityHashMap.equals/hashCode`.
- `values()` is a collection view backed by the original map, not a copy. Presence checks on values obey identity semantics.
- `IdentityHashMap` does not guarantee iteration order; do not write tests depending on the order of `keySet()`/`entrySet()`/`values()`.

### Converting to `HashMap` can lose mappings

If `identityMap` contains two keys `k1` and `k2` that are different objects with `k1.equals(k2) == true`:

```java
Map<String, String> copied = new HashMap<>(identityMap);
```

`copied` may collapse the two mappings into one; which value survives depends on source iteration order and must not be relied upon. Conversely, constructing an `IdentityHashMap` from a `HashMap` cannot recover distinct-object keys that were already merged. Both classes implement `Map<K,V>`, yet changing implementations can alter **the meaning of data**.

### Pitfalls when using `Map.equals/hashCode` for integration

An API accepting any `Map` normally assumes `equals` is symmetric, transitive, and compatible with `hashCode`. With `IdentityHashMap`, those assumptions can fail when mixed with ordinary maps. Inspect code that compares maps, uses maps as keys in another map, checks `assertEquals(expectedHashMap, actualIdentityMap)`, or passes data through APIs that do not specify equality criteria. **The order of the two comparison arguments can change the result.**

## 5. When should IdentityHashMap be used?

Use it only when the problem requires identifying **each exact instance**, including instances that happen to carry identical data:

- **Cloning/transforming object graphs with sharing or cycles:** mapping each *original node object* to its exact *new node object*. If two different nodes share the same `equals()`, merging them into one would corrupt the graph structure.
- **Tracking visited objects during graph traversal:** nodes representing two separate entities must be processed separately, even with identical attributes.
- **Mapping original objects to proxies or diagnostic metadata:** keeping a separate proxy for each specific runtime object.

When you only need a set of visited objects, use `Collections.newSetFromMap(new IdentityHashMap<>())` with an initially empty map. The lesson **Using Identity When Traversing and Tracking Object Graphs** provides DFS examples and distinguishes revisiting a node from a cycle.

## 6. Misconceptions## 6. Misconceptions and limitations to avoid

1. **Do not think `IdentityHashMap` is a faster `HashMap`.** The two structures have different semantics. Hash table details and optimization are not reasons to substitute it if business logic uses `equals()`.
2. **Do not use it for "value-equal" business keys.** Emails, product codes, IDs, or strings recreated across requests can become multiple hard-to-look-up entries despite identical content.
3. **Do not misunderstand `==` as `equals()`.** For objects, `==` compares references; overriding `equals/hashCode` does not change this.
4. **Do not use identity hash code as a global ID.** `System.identityHashCode(x)` can collide across different objects and is not a durable identifier across processes.
5. **Do not assume ordering, thread safety, or automatic key release.** `IdentityHashMap` guarantees no ordering, is not synchronized by default, and holds strong references to keys/values. When multiple threads perform structural modifications, synchronize appropriately; if weak keys are needed, choose a structure matching that requirement.
6. **Do not rely on fail-fast iterators as a synchronization mechanism.** `ConcurrentModificationException` is only detected on a best-effort basis and does not replace synchronization.
7. **Do not compare via `Map.equals` when both sides use different criteria.** Clarify whether the same instance or the same data is needed; if switching to a value-equality structure, evaluate key-merging risks beforehand.

## 7. Practical checklist

Before choosing `IdentityHashMap`, answer:

- Must two keys with different references yet `equals() == true` **strictly** be kept separate?
- Do value comparisons (`containsValue`, `entrySet`, `Map.equals`) truly require `==` instead of `equals()`?
- Does calling code rely on the `Map.equals/hashCode` contract when comparing against `HashMap`/`TreeMap`?
- Is there any map copying, serialization, caching, or exposing of `Map` to another API that would lose identity semantics?
- Do tests cover **same reference**, **different references with equal values**, **`null`**, and **cross-type map comparison**?

If the criterion is logical equality, `HashMap` is usually appropriate. If the criterion is **which object in memory**, `IdentityHashMap` serves that purpose; protect semantic boundaries when combining it with other collections.

## References

- [Java SE 17 API — IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): describes identity semantics, exceptions to the `Map` contract, `equals/hashCode`, collection views, and object-graph applications.
- [Java SE 17 API — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): general contract for keys, values, `equals`, and `hashCode`.
- [Java SE 17 API — System.identityHashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)): identity-based hash code, independent of `hashCode()` overrides.