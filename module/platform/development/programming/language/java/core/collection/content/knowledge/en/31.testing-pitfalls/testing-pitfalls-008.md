# Mutable Keys, Inconsistent Comparators, and "Lost" Elements

A collection may still contain an object even when the program cannot find it through normal lookups. This behavior usually stems from **changed identity rules** or **incompatible comparison rules**, rather than the element actually being removed from memory.

This lesson distinguishes three mechanisms: (1) hash-based structures using `hashCode` and `equals`, (2) sorted structures using `Comparator`/`Comparable`, and (3) objects or keys mutated after being inserted into a structure. These are *data contract* errors; changing an individual lookup operation does not fix the root cause.

## 1. "Present in the Structure" vs. "Findable Under Current Rules"

Suppose a `Map` stores a record keyed by an object. After insertion, the program mutates a field of that key. Subsequent lookup code computes against the new state, while the structure organized or stored the key under its old state. As a result, `get` may return `null`, `containsKey` may return `false`, or `remove` may fail to find the element even though iterating over the structure still reveals that reference.

Ask three questions before concluding that data has "disappeared":

1. Was the object truly removed from the collection, or can it simply no longer be found?
2. Did the `equals`, `hashCode`, or `compare` outcome change between insertion and lookup?
3. Does the structure rely on **hashing**, **comparison ordering**, or **position/index** for lookup?

`HashMap` and `HashSet` use hashing to organize and locate elements. `TreeMap` and `TreeSet` rely on an ordering relation. `ArrayList` searches using `equals` by scanning through its elements. Because of this, the exact same flaw can manifest differently depending on the data structure.

## 2. Mutable Keys in HashMap/HashSet

The essential requirement for a hash key is: **for the entire duration that a key resides in the structure, any data affecting `equals` and `hashCode` must remain stable**. Two objects that are equal according to `equals` must have the same `hashCode`; two objects with the same hash code are *not necessarily* equal.

Example of a dangerous key type:

```java
import java.util.Objects;

final class MutableKey {
    String code;

    MutableKey(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey key
                && Objects.equals(code, key.code);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}
```

A typical failure scenario:

```java
MutableKey key = new MutableKey("alpha");
Map<MutableKey, String> map = new HashMap<>();
map.put(key, "Đã lưu");

key.code = "beta"; // mutates input to equals/hashCode
String result = map.get(key); // lookup guarantee no longer holds
```

During `put`, `HashMap` selects a storage bucket using the hash value at that moment. After `code` changes, the hash code may differ, causing a lookup request to probe a different bucket. **Do not assume every mutation produces `null`:** the new hash might coincidentally land in the same bucket, or a mutated field might not participate in the hash code. The problem is that the usage contract is broken; as stated in the `Map` Javadoc, behavior is undefined when a key is mutated in a manner that affects `equals` comparisons while it is a key in the map.

In `HashSet`, the element itself acts as the key in the underlying hash structure. An element whose identifying field is modified after `add` may likewise become impossible to find or remove under current rules. Calling `remove` before mutating the object and `add` again afterward is a valid approach **if** you ensure single-threaded execution or proper synchronization and never alter the element's identity while it resides in the Set.

### Choosing Stable Keys

Prefer immutable identifying values, such as a normalized code, `String`, `UUID`, or a `record` that holds no mutable components participating in identity:

```java
record CustomerKey(String tenant, String customerId) {}

Map<CustomerKey, String> customers = new HashMap<>();
customers.put(new CustomerKey("vn", "C-42"), "Lan");
System.out.println(customers.get(new CustomerKey("vn", "C-42")));
```

Output:

```text
Lan
```

Two distinct record instances whose components carry equal values match properly. However, **a `record` does not automatically provide deep immutability**: if a component is a mutable `List` and its contents participate in `equals`/`hashCode`, mutating that list can still break the key contract. Use immutable components or make defensive immutable copies where appropriate.

## 3. A Comparator That Conflates Distinct Values

A `TreeSet` determines whether a new element duplicates an existing one by checking whether `compare(a, b) == 0`. It does not invoke `equals` as an additional duplicate check. If a comparator inspects only part of the data, two genuinely distinct elements can be treated as identical.

Program `ComparatorPitfallDemo.java`:

```java
import java.util.Comparator;
import java.util.Set;
import java.util.TreeSet;

public class ComparatorPitfallDemo {
    public static void main(String[] args) {
        Set<String> names = new TreeSet<>(
                Comparator.comparingInt(String::length)
        );
        System.out.println(names.add("Lan"));
        System.out.println(names.add("Min"));
        System.out.println(names.contains("Min"));
        System.out.println(names);
    }
}
```

Run:

```text
javac -encoding UTF-8 --release 17 ComparatorPitfallDemo.java
java -Dfile.encoding=UTF-8 ComparatorPitfallDemo
```

Output:

```text
true
false
true
[Lan]
```

`"Lan"` and `"Min"` have the same length, so the comparator returns `0`. `add("Min")` does not insert a new value, yet `contains("Min")` returns `true` because an equivalent element **according to the comparator** was found. Thus, `contains` returning `true` does not mean the string `"Min"` was ever stored. This is not a random JVM bug.

If you want to sort names by length while still distinguishing different strings, add a tie-breaking criterion:

```java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
Set<String> names = new TreeSet<>(byLengthThenText);
names.add("Lan");
names.add("Min");
System.out.println(names);
```

Output:

```text
[Lan, Min]
```

The secondary criterion prevents two names with *different content* of equal length from being collapsed together. If your domain model treats two strings differing only by letter case as the same person, define a dedicated **domain identity** rather than assuming `Comparator.naturalOrder()` matches person identity.

In `TreeMap`, the comparator similarly determines which keys are considered equivalent. If two keys compare as `0`, calling `put` with the second key **updates the value associated with the existing key** instead of creating a new entry. This is dangerous if the author only intended the comparator to control display order.

## 4. A Comparator Must Satisfy the Ordering Contract

A valid comparator does not need to return literally `-1` or `1`; only negative, zero, or positive signs matter. It must guarantee:

- **Sign antisymmetry:** the sign of `compare(a,b)` must be the opposite of the sign of `compare(b,a)`.
- **Transitivity:** if `a > b` and `b > c` according to the comparator, then `a > c`.
- **Consistency of equivalence:** if `compare(a,b)==0`, then for every `z`, the sign of comparing `a` with `z` and `b` with `z` must be identical.
- For `SortedSet`/`SortedMap`, it should be **consistent with `equals`** if full compliance with the general `Set`/`Map` contract is required.

A common flawed example:

```java
Comparator<Integer> wrong = (a, b) -> a - b;
```

Subtraction can **overflow**, producing the wrong sign. Use `Integer.compare(a, b)` instead. A comparator written along the lines of "if a person has priority, put them first; otherwise put them after" without properly handling ties often violates antisymmetry. Comparators that depend on the current time, changing configuration, or external mutable state are also unsuitable as stable ordering rules for `TreeSet`/`TreeMap`.

A contract-violating comparator can produce incorrect results and, in some sorting algorithms, throw an `IllegalArgumentException` reporting a contract violation. **Never rely on the absence or presence of an exception to prove that a comparator is valid.**

## 5. Fields Participating in Ordering Must Not Change Inside TreeSet/TreeMap

`TreeSet` places an element into its tree structure based on the ordering at insertion time. If an object mutates a field read by the comparator, the structure does not automatically rebalance or rebuild the tree.

For example, suppose a `Task` has its `priority` modified after being added to a `TreeSet<Task>`. Iterating over the tree may yield an invalid order, and `contains`/`remove` may traverse the wrong branch and fail to locate the object. Just as with hash keys, not every mutation triggers an immediate visible failure, but mutating ordering fields corrupts the structure's invariants.

Remedies by use case:

| Requirement | Recommended Model |
| --- | --- |
| Stable domain key, mutable record payload | Immutable `record`/ID key → mutable value in a `Map` |
| Need to update an element in an ordered set | `remove` while still in old state → create/update element or key → `add` |
| Continuously changing task priority | Re-manage the queue/structure under an explicit update policy; do not expect `PriorityQueue` to reorder itself on in-place object mutation |
| Only need a freshly sorted display list | Keep source data stable and create a new list to `sort` on demand |
| Multi-criteria comparison | Use a comparator with enough tie-breaking criteria to match the identity model |

**Note:** `PriorityQueue` does not automatically adjust an element's heap position when you mutate the priority of an element already inside the heap. Modifying priority in place can cause `peek`/`poll` to no longer reflect the expected priority order.

## 6. How to Investigate "Lost" Elements

1. **Snapshot data before insertion:** record the fields participating in `equals`/`hashCode`/`compare`, the identity, and comparison results against other keys.
2. **Separate lookup from iteration:** for a Map or Set, test `get`/`contains` while also inspecting entries via iteration (in a single-threaded test environment). Do not mutate data during inspection.
3. **Compare current state against the snapshot:** an updated identifying field often explains why the hash or ordering changed.
4. **Test two distinct references with the same identity:** they must produce compatible `equals` and `hashCode` results; for sorted structures, verify `compare` as well.
5. **Create a minimal reproduction test:** add two equal-length strings to a `TreeSet` to verify comparator behavior; use a mutable key class in a test to demonstrate the risk.
6. **Redesign the data model:** favor immutable keys, stable comparators, and separating sorting fields from frequently mutated fields.

Do not rely on print order from `HashMap` or `HashSet` to judge correctness; those structures do not guarantee insertion order. Verify data state using explicit assertions on `containsKey`, retrieved values, and element count.

## 7. Self-Check Questions

- Are two objects with the same `hashCode` for which `equals` returns `false` treated as the same key in a `HashMap`? **No.** Hash collisions are resolved by matching keys with `equals`.
- A `TreeSet<String>` orders strings by length and already contains `"Lan"`. What happens when `"Min"` is added? **It is not added** because the comparator returns `0`; `contains("Min")` can still return `true`.
- Does changing a `Customer`'s `phone` field always break its key in a `HashMap`? **No**, not if `phone` does not participate in `equals`/`hashCode`; always check the key type's contract.
- Can you fix these issues by calling `rehash` on `HashMap`? **No**—there is no public `rehash` API for users to paper over a broken contract. Fix the key design and update lifecycle instead.
- Why is adding `thenComparing` useful? Because secondary criteria distinguish cases where the primary criterion returns `0`, provided they align with domain identity and ordering rules.

## References

- `Map` Javadoc (Java SE 21), mutable key warning: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html
- `SortedSet` Javadoc (Java SE 21), ordering consistent with equals: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html
- `Comparator` Javadoc (Java SE 21), sign rules and transitivity: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html
