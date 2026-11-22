# Combining a Hash Table with Deterministic Iteration Order

## 1. Why Do We Need LinkedHashMap?

A configuration screen has fields added in a specific order: display name, email, language. The program needs two capabilities:

- Quickly look up a value by field name.
- When outputting the list, preserve the exact order in which the fields were added.

HashMap handles mapping keys to values well, but it does not guarantee iteration order. A List preserves order, but if you only use a list of pairs, finding a key usually requires checking many pairs.

LinkedHashMap combines both ideas: **using a hash table to locate mappings by key and using a linked chain to determine the iteration order of the mappings**.

Therefore, the name LinkedHashMap does not mean every `get` call has to traverse an entire LinkedList. The two structures serve two different jobs.

This lesson focuses on that combined mechanism, the default insertion order, and the consequences when reading, updating, copying, or testing a map. Access-order mode is also introduced to avoid the misconception that every LinkedHashMap always keeps positions unchanged after a `get`.

## 2. Two Independent Questions: Where to Find It and Which Path to Traverse?

### 2.1. The Hash Table Answers the Lookup Question

When calling `get(key)`, the hashing mechanism uses the key's hash to navigate to the bucket that may contain the mapping, then checks for a matching key using the map's equality rules.

The condition that must still be upheld is the `equals`/`hashCode` contract. Two equal keys must have the same hash; multiple distinct keys may collide and still remain separate mappings.

Adding ordering does not cause LinkedHashMap to abandon Map's unique-key model.

### 2.2. The Linked Chain Answers the Traversal Question

In addition to information for the hash table, entries are linked together in a map-wide order.

Conceptual diagram with three entries:

```text
Hash table: hash(key) → matching bucket → target entry

Iteration order:
head → [zeta=3] ⇄ [alpha=1] ⇄ [beta=2] → tail
```

An entry participates in both the hash-based lookup mechanism and the ordering mechanism. There is no need to manually maintain a HashMap and a List containing duplicate data in application code.

In the OpenJDK 17u source code, a regular entry has `before`/`after` links; the map has the head and tail of the chain. The iterator follows the order links instead of using bucket order as the result order. You can reference [LinkedHashMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/LinkedHashMap.java).

Field names and internal class organization are implementation details. What users can rely on is LinkedHashMap's iteration order contract.

### 2.3. Do Not Confuse the Two Kinds of Links

A bucket with multiple colliding keys may also need links or an internal structure to hold candidates within that bucket.

LinkedHashMap's `before`/`after` chain has a different role: it connects **all entries of the map in iteration order**, even entries located in different buckets.

Therefore, do not infer that "keys near each other during iteration are in the same bucket" or that "keys with the same hash will appear adjacent to each other in the output."

## 3. The Default Is Insertion Order, Not Key Order

Standard constructors such as `new LinkedHashMap<>()` create a map in **insertion order**.

If you add `zeta`, `alpha`, `beta` in sequence, the iteration order is:

```text
zeta → alpha → beta
```

It does not automatically reorder to `alpha`, `beta`, `zeta` just because the key names have that alphabetical order.

### 3.1. New Keys Are Added at the End

A key not yet in the map creates a new mapping. In default insertion mode, that mapping is placed after all previously existing mappings.

The order here is produced by the history of operations on the map, not by an inherent sorting property of the data.

### 3.2. Re-putting an Existing Key Preserves Its Position

With the order `zeta`, `alpha`, `beta`, calling `put("alpha", 10)` replaces the value of `alpha` without pushing `alpha` to the end in insertion mode.

This is useful when you want to preserve the first occurrence of a key while updating it with the latest content.

It does not have to be the exact same key object by `==`. A different key object that is equal to an existing key still updates the mapping for that logical key, provided the keys obey the contract.

### 3.3. Removing and Re-adding Is a New Insertion

If you call `remove("zeta")` and then `put("zeta", 30)`, between those two operations the map no longer contains `zeta`. The subsequent `put` adds a new mapping at the end.

The order changes from:

```text
zeta → alpha → beta
       remove zeta
alpha → beta
       add zeta
alpha → beta → zeta
```

This is the difference between "updating the value of an existing key" and "removing a mapping and recreating it."

### 3.4. Reading in Insertion Mode Does Not Change Order

`get`, `containsKey`, and iterating over views are not treated as re-insertions. With the default configuration, reading `alpha` does not move `alpha` from its original position.

You must know the ordering mode before concluding the effect of a read operation; a later section contrasts this with access-order mode.

## 4. Java 17 Example: Observing Order Across Operations

Save as **LinkedOrderDemo.java**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.StringJoiner;

public class LinkedOrderDemo {
    static String entries(Map<String, Integer> map) {
        StringJoiner result = new StringJoiner("; ");
        for (Map.Entry<String, Integer> entry : map.entrySet()) {
            result.add(entry.getKey() + "=" + entry.getValue());
        }
        return result.toString();
    }

    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("zeta", 3);
        scores.put("alpha", 1);
        scores.put("beta", 2);
        System.out.println("initial keys: " + new ArrayList<>(scores.keySet()));
        System.out.println("get alpha: " + scores.get("alpha"));
        System.out.println("after get: " + new ArrayList<>(scores.keySet()));

        System.out.println("old alpha value: " + scores.put("alpha", 10));
        System.out.println("after update: " + new ArrayList<>(scores.keySet()));
        System.out.println("size after update: " + scores.size());

        scores.remove("zeta");
        scores.put("zeta", 30);
        scores.put("beta", 10);
        System.out.println("after remove and insert: " + new ArrayList<>(scores.keySet()));
        System.out.println("values: " + new ArrayList<>(scores.values()));
        System.out.println("entries: " + entries(scores));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LinkedOrderDemo.java
java LinkedOrderDemo
```

Stdout:

```text
initial keys: [zeta, alpha, beta]
get alpha: 1
after get: [zeta, alpha, beta]
old alpha value: 1
after update: [zeta, alpha, beta]
size after update: 3
after remove and insert: [alpha, beta, zeta]
values: [10, 10, 30]
entries: alpha=10; beta=10; zeta=30
```

The programs in this lesson were compiled with `--release 17` and run on OpenJDK 24.0.2. That flag selects the target language/API level and bytecode; the JVM running the program is still version 24.0.2.

### 4.1. Explaining the Output

The three initial keys are `zeta`, `alpha`, `beta`, so `keySet` follows that order.

`get("alpha")` returns `1` without changing the order. `put("alpha", 10)` returns the old value `1`; the number of keys remains three and `alpha` stays in the second position.

After removing `zeta` and adding it back, `zeta` moves to the end. Next, updating `beta` to `10` does not change `beta`'s position.

The `values` line is `[10, 10, 30]`. It has two `10` values because `Map` only requires unique keys; values can be duplicated. The `entries` line shows the exact key–value pair at each traversal position.

### 4.2. Why Still Declare the Variable as Map?

The `scores` variable has type `Map<String, Integer>`, while the actual object created is a `LinkedHashMap`. Using the `Map` interface does not strip away the actual object's behavior.

However, a method accepting an arbitrary `Map` must not assume every argument has insertion order. If order is a requirement of the interface, state that requirement clearly and use an appropriate structure or copy at the boundary.

The `new ArrayList<>(...)` calls in the example create lists to print and compare the order at that moment. They do not alter the internal order of the map.

## 5. One Order Shared Across keySet, values, and entrySet

LinkedHashMap has three familiar views:

| View | Data on traversal | Relation to the same entry order |
| --- | --- | --- |
| `keySet()` | Keys | Key of the first entry, second entry, ... |
| `values()` | Values | Value of the first entry, second entry, ... |
| `entrySet()` | Key–value pairs | The entries themselves in that order |

If the map is not modified between traversals, all three views correspond to the same sequence of entries. There is no case where `keySet` keeps insertion order while `values` sorts itself by value.

### 5.1. Views Are Not Copies

Keeping a variable pointing to `keySet` and then adding a key to the map causes the view to reflect the updated map. Conversely, supported removal operations performed through a view affect the underlying map.

If you need to keep a list of keys at a point in time, you can create `new ArrayList<>(map.keySet())`. This is a snapshot of the sequence of key references at copy time, not a deep copy of the key objects.

### 5.2. When You Need Both Keys and Values, Iterate Over entrySet

In the example, `entries` iterates over `Map.Entry` to obtain both parts of the same mapping. This approach directly expresses what the code is doing.

In particular, there is no need to fetch each key and call `get` again just to look up a value that is already in the entry. In access-order mode, a `get` call can also affect the order, so loop choice should be deliberate.

### 5.3. Removing While Iterating

If you need to remove an entry directly during an iterator pass, use the iterator's own `remove` method after `next` when that operation is supported. LinkedHashMap's iterator maintains consistency between traversal and mapping removal.

Do not iterate with an enhanced `for` loop while calling `map.remove` arbitrarily and rely on a single run not throwing an error. Structural modification outside the allowed path can invalidate the iterator.

The fail-fast mechanism detects errors on a best-effort basis; it is neither a synchronization protocol nor a guarantee that every invalid access will be caught.

## 6. Insertion Order, Access Order, and Sorted Order

"Ordered" is an incomplete description. You need to know **which rule produces the order**.

| Structure or configuration | Primary ordering rule |
| --- | --- |
| `HashMap` | No iteration order guarantee |
| Default `LinkedHashMap` | Insertion order of existing keys |
| `LinkedHashMap` with `accessOrder = true` | Access order, from least-recently accessed to most-recently accessed |
| `TreeMap` | Key order according to natural ordering or a suitable `Comparator` |

### 6.1. LinkedHashMap Does Not Compare Keys to Keep Insertion Order

Keys do not have to implement `Comparable` just to use `LinkedHashMap`. Nor do you pass a `Comparator` to this class's constructor to request sorting.

If you need a sorted sequence of keys or range queries, you must choose a contract that satisfies that requirement. Insertion order does not provide operations such as `floorKey`.

Refer to [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) when key-comparison ordering is required.

### 6.2. Access Mode Changes the Meaning of History

The three-argument constructor can enable `accessOrder`:

```java
Map<String, Integer> byAccess = new LinkedHashMap<>(16, 0.75f, true);
```

This is an illustrative declaration assuming `Map` and `LinkedHashMap` are imported. `16` is the capacity parameter, `0.75f` is the load factor, and `true` selects access-order mode.

If the map currently holds `a`, `b`, `c`, successfully accessing `a` with `get` moves `a` to the end, producing `b`, `c`, `a`. The end of the chain is then the most-recently accessed entry, no longer simply the most-recently inserted key.

The class documentation defines which operations count as accesses. For example, `get` and `put` have this effect on the relevant entry under their respective conditions; `containsKey` does not count as an access that changes order.

Do not assume every method call on the map makes an entry the newest. Iterating over views also does not count as accessing entries under this rule.

### 6.3. Access Mode Does Not Create a Complete Cache by Itself

Configuring `accessOrder` only selects how order is maintained. It does not automatically set an entry count limit, expiration time, or eviction policy.

It is a useful foundation for organizing data by recent usage. Achieving full cache behavior still requires separate policies.

In this lesson, you need to recognize the mode to understand the iteration contract correctly, not to implement a caching system.

## 7. Having the Same Mappings Does Not Guarantee the Same Order

Two `LinkedHashMap` instances can contain the same key–value pairs while having been inserted in different sequences.

`Map.equals` checks for **the same mappings**, not the insertion order sequence. That is the general contract stated in [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#equals(java.lang.Object)).

Example:

```text
Left map:   b=2, a=1, c=3
Right map:  c=3, a=1, b=2

Same mappings.
Different key sequence on traversal.
```

### 7.1. Testing Order with an Ordered Sequence

If the goal is to verify key order, compare two `List`s of keys built from traversal, or check the sequence of keys obtained via the iterator.

Calling only `map.equals` or `keySet().equals` is not enough. `Set` also evaluates its elements using set equality, without verifying their iteration order.

If you need to check both content and order, you can verify the mappings and then verify the key sequence. If you need to keep pairs for comparison later while the map might still change, take an appropriate snapshot of the pairs instead of holding onto live entries as immutable data.

### 7.2. Do Not Use a Map's hashCode to Verify Order

`Map`'s `hashCode` contract goes hand in hand with mapping-based `equals`. Two equal maps must have the same `hashCode` even if their insertion orders differ.

A matching `hashCode` certainly does not prove identical order. Do not use it as a substitute for an explicit order check.

## 8. Copying Preserves the Observed Order, Not a Lost History

`new LinkedHashMap<>(source)` creates an insertion-order map with the mappings from `source`. The order is populated into the copy according to the source's traversal order.

### 8.1. If the Source Has an Ordering Contract

Copying from an insertion-order `LinkedHashMap` preserves the source's iteration order at the time of copying.

If the source is a `TreeMap`, the copy starts with the keys in their sorted traversal order. However, the new copy is still an insertion-order `LinkedHashMap`: adding a new key afterward places it at the end rather than inserting it into sorted position.

Copying from an access-order map also captures the order observed at that moment; the copy constructor does not automatically carry the `accessOrder` mode over to the new instance.

### 8.2. If the Source Does Not Guarantee Order

Copying a `HashMap` into a `LinkedHashMap` captures whatever order the `HashMap` yields during the copy traversal. It does not know the order in which keys were originally added to the `HashMap`.

The new result can remain stable under subsequent operations, but it does not become a canonical order such as alphabetical order, record creation time, or original input order.

If the output requires a consistent order independent of the source's order, define that rule and actively sort or insert the data according to it.

### 8.3. A Structural Copy Is Not a Deep Copy

Adding or removing mappings in the original does not automatically add or remove mappings in the copy. However, keys and values are references to the same objects.

If a value is a mutable object, both maps can point to that same value object. `LinkedHashMap` does not deep-copy every object just because a constructor accepts a `Map`.

## 9. Java 17 Example: equals, Copying, and Access Mode

Save as **OrderSemanticsDemo.java**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class OrderSemanticsDemo {
    static List<String> keys(Map<String, Integer> map) {
        return new ArrayList<>(map.keySet());
    }

    public static void main(String[] args) {
        Map<String, Integer> left = new LinkedHashMap<>();
        left.put("b", 2);
        left.put("a", 1);
        left.put("c", 3);

        Map<String, Integer> right = new LinkedHashMap<>();
        right.put("c", 3);
        right.put("a", 1);
        right.put("b", 2);
        System.out.println("left order: " + keys(left));
        System.out.println("right order: " + keys(right));
        System.out.println("maps equal: " + left.equals(right));
        System.out.println("key sequences equal: " + keys(left).equals(keys(right)));

        Map<String, Integer> copy = new LinkedHashMap<>(left);
        left.remove("a");
        left.put("d", 4);
        System.out.println("left later: " + keys(left));
        System.out.println("copy order: " + keys(copy));

        Map<String, Integer> byAccess = new LinkedHashMap<>(16, 0.75f, true);
        byAccess.put("a", 1);
        byAccess.put("b", 2);
        byAccess.put("c", 3);
        System.out.println("access initial: " + keys(byAccess));
        System.out.println("access get a: " + byAccess.get("a"));
        System.out.println("access after get: " + keys(byAccess));
        System.out.println("access contains b: " + byAccess.containsKey("b"));
        System.out.println("access after contains: " + keys(byAccess));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 OrderSemanticsDemo.java
java OrderSemanticsDemo
```

Stdout on the stated environment:

```text
left order: [b, a, c]
right order: [c, a, b]
maps equal: true
key sequences equal: false
left later: [b, c, d]
copy order: [b, a, c]
access initial: [a, b, c]
access get a: 1
access after get: [b, c, a]
access contains b: true
access after contains: [b, c, a]
```

### 9.1. Two Different Equality Results

`left` and `right` have the same mappings, so `maps equal` is `true`. The two key `List`s have different orders, so `key sequences equal` is `false`.

This is why a test for order must check an ordered sequence, not merely call `equals` on `Map`.

### 9.2. The Copy Keeps the Sequence Before the Source Changes

`copy` is created when `left` has `b`, `a`, `c`. Afterward `left` removes `a` and adds `d`, becoming `b`, `c`, `d`. `copy` still has `b`, `a`, `c`.

The `Integer` values in the example avoid the need to handle mutating shared objects, letting us focus on observing the independence of the mappings.

### 9.3. get and containsKey Behave Differently in Access Mode

`byAccess` starts with `a`, `b`, `c`. `get("a")` returns `1` and moves `a` to the end, yielding `b`, `c`, `a`.

`containsKey("b")` returns `true` without moving `b` from the head of the chain. The `keys` helper only iterates over `keySet` to build a `List`, so printing the order does not itself trigger accesses that change the order.

Do not apply `byAccess`'s behavior back onto the default map in the first program; the two objects have different ordering configurations.

## 10. The Cost of This Combination

### 10.1. Lookup Still Relies on Hashing

With a well-distributed hash function, basic key-based operations have expected constant-time performance. The order links do not turn `get` into a full scan from the head of the chain.

Hash distribution still matters. Having iteration order does not fix a broken `equals`/`hashCode`, keys whose identity fields mutate, or data piling up excessively in a single bucket.

### 10.2. Full-Map Iteration Scales with Entry Count

The iterator follows the linked chain, so iterating over an entire collection view has cost proportional to the `size` of the map, rather than scanning every bucket the way `HashMap` does.

For example, if a table is allocated with many buckets but holds only 100 mappings, the order chain has 100 entries to visit. The traversal structure does not need to step through every empty bucket.

However, the work inside the loop body still has its own cost. "Proportional to size" does not mean every traversal is faster than every other structure in all environments.

### 10.3. Memory and Updates Carry Extra Cost

The `before`/`after` links must be stored and updated. When adding, removing, or reordering in access-order mode, the structure must keep the chain consistent.

Therefore, do not treat `LinkedHashMap` as a `HashMap` with free ordering. Exact byte size depends on object layout and the JVM, so you should not assume a fixed number across all machines.

Capacity and load factor still affect the hash table, memory, and resizing. The fact that the iterator skips empty buckets does not make over-allocating huge capacities harmless.

### 10.4. Bucket Changes Must Not Break the Committed Order

The implementation may resize the table or change how a collision group is organized. Those actions serve the hashing mechanism; they do not permit arbitrarily altering the insertion order promised to the user.

This is the benefit of separating the two roles: how entries are located internally can change, while the ordering contract remains intact.

Tests against the public API can load many keys, including valid colliding keys, and verify that both the key sequence and lookup results are correct. There is no need to inspect internal node class names to prove that contract.

## 11. "Deterministic" Requires Corresponding Input and History

`LinkedHashMap` specifies that order is maintained according to the chosen rule. It does not invent a canonical order independent of all history.

### 11.1. Identical Operations Yield the Same Order Model

If we create a default map and insert `a`, `b`, `c` in sequence and then update `b`, we have a basis to predict the sequence `a`, `b`, `c`.

If you read data from a source without an ordering contract and insert it according to that source's traversal order, the inputs to the insertion history can vary. `LinkedHashMap` still follows its rule faithfully, but the order across different builds is not guaranteed to match.

### 11.2. In-Memory Stability Does Not Guarantee Order at the Destination

Converting to an unordered structure can lose this requirement. Serialization or export libraries also have their own contracts regarding output order and how the receiver interprets it.

If order is business data, it must be modeled and verified across the entire pipeline. For instance, an ordered list may be more appropriate if the receiver must read items by position.

Do not look at a single correct `println` in Java and conclude that all downstream processing preserves the same ordering semantics.

### 11.3. Ordering Does Not Create Thread Safety

`LinkedHashMap` does not synchronize access automatically. When multiple threads operate on it concurrently, appropriate coordination matching the program's requirements is required.

In access-order mode, `get` can modify the internal order. Therefore, do not divide operations into "reads are always harmless" and "only writes mutate structure" based solely on method names.

An order guaranteed under proper usage does not mean uncoordinated concurrent operations will naturally produce a valid history.

## 12. Nulls, Mutable Keys, and the Limits of "Preserving Order"

`LinkedHashMap` allows a `null` key and `null` values. As a key, `null` still has at most one mapping; `null` values can appear under multiple keys.

In insertion mode, updating the value of an existing `null` key preserves that key's position just like any other key.

`get` returning `null` does not by itself prove the key is absent; the key may exist mapped to `null`. If you need to distinguish the two, check using the appropriate method.

For mutable keys, properties participating in `equals`/`hashCode` must remain stable while the key is in use in the map. The fact that the linked chain may still hold a reference to the entry does not mean `get` lookups with that key will still work if the hashing rules have been broken.

Do not use "I can still see the entry when iterating" as proof that the key is designed properly. Lookup and iteration are two separate paths; a key bug can manifest differently on those two paths.

## 13. Common Mistakes and How to Fix Them

| Misconception | Correction |
| --- | --- |
| `LinkedHashMap` always sorts keys | Clarify insertion vs. access order; if key comparison is needed, choose the appropriate rule |
| Having a linked list means `get` must be O(n) | Distinguish the hash lookup path from the iterator path |
| Putting an existing key moves it to the end by default | Updating an existing mapping preserves its position in insertion mode |
| Removing and re-adding is the same as updating in place | After removal, re-adding creates a new insertion position |
| `values` is a set without duplicates | Only keys are unique; values can repeat |
| `Map.equals` verifies order | Also compare the key sequence or an appropriately captured entry sequence |
| Copying from `HashMap` recovers insertion order | The copy only receives the order currently yielded by the source's iteration |
| Copying preserves the source's access-order mode | The copy constructor creates an insertion-order map |
| Every method counts as an access | Read the access-order contract; `containsKey` and view iteration do not have that effect |
| Typing a variable as `Map` makes the object lose its order | `LinkedHashMap`'s behavior remains; an arbitrary `Map` interface does not itself promise that order |
| Having order makes it thread-safe | Synchronization is a separate requirement |
| The linked chain fixes keys with broken hashing | The key contract must still be obeyed |

## 14. Self-Check Exercises with Solutions

### Exercise 1: Predicting Default Order

Create a default map, `put` `c`, `a`, `b` in order, then `put` `a` again with a different value. What is the final key sequence?

**Solution:** `c`, `a`, `b`. Key `a` already exists, so updating its value preserves its position.

### Exercise 2: Removing Then Adding

Starting from `c`, `a`, `b`, remove `a` and then add `a` back. What is the new sequence?

**Solution:** `c`, `b`, `a`. The old mapping for `a` was removed; the new addition goes to the end.

### Exercise 3: Two Identical Values

A map in order `x`, `y`, `z` has values `7`, `7`, `9`. What are `values` on traversal? What is `size`?

**Solution:** `7`, `7`, `9` and `size` is `3`. Duplicate values do not merge distinct keys.

### Exercise 4: Hash Table with Collisions

Two distinct keys have the same valid hash. Must they appear adjacent to each other when iterating over a `LinkedHashMap`?

**Solution:** No. Map-wide order follows insertion or access rules. Other keys inserted in between can sit between them in the order chain even though they are not in the same bucket.

### Exercise 5: Checking equals

Two maps both contain `a=1`, `b=2`, but their key sequences are `a, b` and `b, a`. Can `Map.equals` be `true`?

**Solution:** Yes. It checks mappings. If a test requires the order `a, b`, it must check a corresponding ordered sequence.

### Exercise 6: Copying from a Sorted Source

Copy a `TreeMap` with keys `a, c` into a `LinkedHashMap`, then add `b`. Is the copy guaranteed to iterate as `a, b, c`?

**Solution:** No. The copy starts with `a, c` and inserts `b` at the end, yielding `a, c, b` in standard insertion mode.

### Exercise 7: Two Kinds of Reads

An access-order map currently has `a, b, c`. `get("a")` succeeds, followed by `containsKey("b")`. What is the final sequence?

**Solution:** `b, c, a`. `get("a")` makes `a` most-recently accessed; `containsKey("b")` does not move `b` to the end.

### Exercise 8: Choosing a Structure

You need to look up configuration settings by name and export them in the order of each name's first appearance; later values may overwrite earlier ones. Which default structure fits both requirements?

**Solution:** An insertion-order `LinkedHashMap` fits. Putting an existing key updates its value while keeping the existing insertion position, provided the key is not removed and recreated.

## 15. References

- [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): ordering contract, both modes, views, performance, and synchronization.
- [LinkedHashMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/LinkedHashMap.java): before/after links, head/tail, link updates, and iterator path.
- [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): mapping contract, `equals`, `hashCode`, and views.
- [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): comparison for lack of iteration order guarantee.
- [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): comparison for key-comparator ordering.

The key takeaway is that both roles coexist: the hash table locates mappings, and the linked chain traverses them according to the chosen rule. When using `LinkedHashMap`, clearly identify the ordering rule and test it as a requirement independent of mapping contents.
