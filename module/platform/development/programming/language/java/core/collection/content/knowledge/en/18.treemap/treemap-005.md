# lowerEntry, floorEntry, ceilingEntry, and higherEntry

## 1. Finding a Neighboring Mapping Instead of Only an Exact Key

Suppose a program stores configuration versions by their effective start milestone. When querying at milestone 25, the map may only contain milestones 10, 20, and 30.

`get(25)` only answers whether the exact key 25 exists. It does not answer which closest version started before or at 25.

`TreeMap` implements `NavigableMap`, providing four operations to find a neighboring entry by key order:

- `lowerEntry`: before, excluding the query key itself.
- `floorEntry`: before, including the query key if present.
- `ceilingEntry`: after, including the query key if present.
- `higherEntry`: after, excluding the query key itself.

"Before/after" here must be understood according to the **map's ordering**. With natural numeric order, they correspond to smaller/larger sides. When reversing the `Comparator`, you must not continue applying the usual ascending-number intuition.

This lesson explains boundary inequalities, cases with no result, the meaning of the returned `Map.Entry`, and how to choose a method based on practical requirements.

## 2. Definition Table to Master

Let `q` be the query key and `k` be the key of an existing mapping.

| Method | Condition on the result key | Which key is chosen among candidates? |
| --- | --- | --- |
| `lowerEntry(q)` | k < q | Greatest key satisfying the condition |
| `floorEntry(q)` | k ≤ q | Greatest key satisfying the condition |
| `ceilingEntry(q)` | k ≥ q | Least key satisfying the condition |
| `higherEntry(q)` | k > q | Least key satisfying the condition |

All relationships in the table use the map's ordering, via `compareTo` or `Comparator`.

If there is no candidate, the result is `null`. If there is one, the result is a `Map.Entry<K,V>` containing both the key and value of the selected mapping.

Compare with the public specification at [NavigableMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html).

### 2.1. The Two Pairs Differ by Equality

`lower` and `floor` both search toward the smaller side in the ordering, but `floor` allows equality with `q`.

`ceiling` and `higher` both search toward the larger side in the ordering, but `ceiling` allows equality with `q`.

When `q` does not exist in the map, `lower` and `floor` usually yield the same candidate; the same applies to `ceiling` and `higher`. When `q` matches an equivalent key position according to the `Comparator`, the equality sign makes a clear difference.

### 2.2. "Greatest" or "Least" Selects Closest to the Boundary

They do not just pick any arbitrary key smaller than `q`. `lower`/`floor` pick the key closest to `q` from the allowed side.

Similarly, `ceiling`/`higher` do not pick an arbitrary larger key; they select the first matching candidate along the ordering direction.

That is why these operations are useful for effective milestones, next positions, or range boundaries.

### 2.3. The Query Key Does Not Need to Exist

`q` is a reference point used for comparison. It does not need to be `put` into the map beforehand.

Do not temporarily insert `q` into the map and then remove it just to find neighbors. These APIs are designed to locate entries using an independent query key.

## 3. Reading the Four Operations with a Small Dataset

A map in natural numeric order has:

```text
10=ten       20=twenty       30=thirty
   ────────────────┬────────────────
             existing keys
```

The table below lists only the **key** of the result entry; "None" means the entire entry is `null`:

| q | lowerEntry | floorEntry | ceilingEntry | higherEntry |
| --- | --- | --- | --- | --- |
| 5 | None | None | 10 | 10 |
| 10 | None | 10 | 10 | 20 |
| 15 | 10 | 10 | 20 | 20 |
| 20 | 10 | 20 | 20 | 30 |
| 25 | 20 | 20 | 30 | 30 |
| 30 | 20 | 30 | 30 | None |
| 35 | 30 | 30 | None | None |

### 3.1. Querying with an Existing Key

With `q = 20`:

- `lower` skips 20 because it requires strictly less, so it chooses 10.
- `floor` accepts 20, so it chooses 20.
- `ceiling` also accepts 20, so it chooses 20.
- `higher` skips 20, so it chooses 30.

`floor` and `ceiling` can return the same mapping. There is no requirement that these two results must differ.

### 3.2. Querying Between Two Keys

With `q = 25`, there is no key equal to 25:

- `lower` and `floor` both choose 20.
- `ceiling` and `higher` both choose 30.

This is the case where many learners see the pairs behaving "identically" and overlook the equality condition. You must also test the case where `q` equals an existing key to understand them fully.

### 3.3. Out-of-Bounds Queries and Empty Maps

If `q` is smaller than all keys, there is no candidate for `lower`/`floor`. If `q` is larger than all keys, there is no candidate for `ceiling`/`higher`.

An empty map has no candidate for any of the four operations, for any query key valid under the contract.

Do not automatically substitute a missing result with the smallest/largest key on the opposite side. If the application needs such a fallback rule, it must be explicitly defined outside the query operation.

## 4. Java 17 Example: Seven Query Positions and All Results

Save as **NeighborEntriesDemo.java**:

```java
import java.util.ArrayList;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class NeighborEntriesDemo {
    static String format(Map.Entry<Integer, String> entry) {
        return entry == null ? "none" : entry.getKey() + "=" + entry.getValue();
    }

    static void show(NavigableMap<Integer, String> map, int query) {
        System.out.println(query + " | " + format(map.lowerEntry(query))
                + " | " + format(map.floorEntry(query))
                + " | " + format(map.ceilingEntry(query))
                + " | " + format(map.higherEntry(query)));
    }

    public static void main(String[] args) {
        NavigableMap<Integer, String> map = new TreeMap<>();
        map.put(30, "thirty");
        map.put(10, "ten");
        map.put(20, "twenty");

        System.out.println("q | lower | floor | ceiling | higher");
        for (int query : new int[] {5, 10, 15, 20, 25, 30, 35}) {
            show(map, query);
        }
        System.out.println("keys after queries: " + new ArrayList<>(map.keySet()));
        System.out.println("size after queries: " + map.size());

        NavigableMap<Integer, String> empty = new TreeMap<>();
        System.out.println("empty floor: " + format(empty.floorEntry(20)));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NeighborEntriesDemo.java
java NeighborEntriesDemo
```

Stdout:

```text
q | lower | floor | ceiling | higher
5 | none | none | 10=ten | 10=ten
10 | none | 10=ten | 10=ten | 20=twenty
15 | 10=ten | 10=ten | 20=twenty | 20=twenty
20 | 10=ten | 20=twenty | 20=twenty | 30=thirty
25 | 20=twenty | 20=twenty | 30=thirty | 30=thirty
30 | 20=twenty | 30=thirty | 30=thirty | none
35 | 30=thirty | 30=thirty | none | none
keys after queries: [10, 20, 30]
size after queries: 3
empty floor: none
```

The programs in this lesson are compiled with `--release 17` and run on OpenJDK 24.0.2. The `--release` flag selects the target language/API level and bytecode version; the JVM running the program is still version 24.0.2.

### 4.1. Insertion Order Does Not Determine Neighbor Results

The map is populated in the order 30, 10, 20, yet its key order is 10, 20, 30. The navigation operations rely on that ordering.

They do not pick "the most recently `put` entry" or "the entry closest in source code to the line where `q` was added."

### 4.2. Searching Does Not Remove Entries

After the queries, the map still has the three keys 10, 20, 30 and a size of 3.

These four operations locate a mapping; they do not retrieve and remove it. Do not confuse them with `poll` operations that remove elements.

### 4.3. Only Access the Entry After Checking Existence

The `format` method checks `entry == null` before calling `getKey`/`getValue`.

Those are two separate layers: **whether a result mapping exists**, and then **what the key/value of that mapping is**.

Do not call `map.floorEntry(q).getValue()` unless you have a guarantee that a candidate definitely exists.

## 5. What Does the Returned Entry Contain and Can It Be Modified?

### 5.1. An Entry with a `null` Value Is Still a Result

`TreeMap` allows `null` values. If a matching key is mapped to `null`, `floorEntry` or another navigation method can still return a non-null entry.

For example, the map contains `20=null`. `floorEntry(20)` returns a result with key 20 and value `null`.

Do not check only `getValue() == null` to conclude that no key was found. The "no candidate" conclusion is based on **the returned entry itself being `null`**.

### 5.2. TreeMap Navigation Entries Are Mapping Snapshots

For the four `TreeMap` methods under discussion, the returned entry captures the key–value pair at the time it was created and does not support `setValue`.

Changing the value in the map later via `put` does not automatically update the value field recorded in the previously obtained entry snapshot.

In the [TreeMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java) source, these operations go through `exportEntry` to create a `SimpleImmutableEntry` from the search result.

Do not generalize this property as a universal rule for every `Map.Entry` obtained from any source. An entry can come from an iterator, a view, or another implementation class with a different contract. You need to know the API that produced it.

### 5.3. Modifying the Map via the Map API

If you want to replace the selected mapping, first obtain the entry, check for existence, and then use its key for the appropriate update operation on the map.

Illustrative snippet in a context where `map` and `q` already exist:

```java
Map.Entry<Integer, String> selected = map.floorEntry(q);
if (selected != null) {
    map.put(selected.getKey(), "updated");
}
```

This is a snippet inside a program with appropriate variables and imports already in place, not a standalone runnable file.

Finding and updating are two separate steps. When a map is shared across threads, such a sequence requires coordination according to application requirements; an entry snapshot does not turn two steps into a single atomic transaction.

### 5.4. A Snapshot Is Not a Deep Copy

If the value is a mutable object, the entry snapshot and the map can still reference the same object.

Being unable to replace the value via `setValue` does not mean the fields inside the value object have become immutable.

The examples use `String` to focus on mapping semantics and avoid mixing in side effects from mutating shared objects.

## 6. Comparator Order Governs Every Relational Inequality

### 6.1. Natural Numeric Order

With keys 10, 20, 30 in natural order, `lowerEntry(25)` selects 20 and `higherEntry(25)` selects 30.

In this configuration, "less than" aligns with familiar arithmetic.

### 6.2. Reversed Order

If the map is ordered 30, 20, 10, then 30 comes before 25 in the reversed order, while 20 comes after 25.

With the same data and `q = 25`:

| Operation | Natural order | Reversed order |
| --- | --- | --- |
| `lowerEntry` | 20 | 30 |
| `floorEntry` | 20 | 30 |
| `ceilingEntry` | 30 | 20 |
| `higherEntry` | 30 | 20 |

The definitions do not change. What changes is the comparison relation used by the definitions.

Do not memorize "`lower` is always the smaller number" and apply it to an arbitrary `Comparator`.

### 6.3. `descendingMap` Reverses Navigation Semantics

`descendingMap` is a view that reverses the order of the original map. Navigation relationships are interpreted according to that view's order.

In terms of key relationships:

- `lower` of the reversed view corresponds to `higher` of the original map.
- `floor` of the reversed view corresponds to `ceiling` of the original map.
- `ceiling` of the reversed view corresponds to `floor` of the original map.
- `higher` of the reversed view corresponds to `lower` of the original map.

The view remains backed by the same underlying data. Viewing through `descendingMap` does not create a separate copy of the entire map.

### 6.4. "Equal" Means Equal According to the Ordering

`floor`/`ceiling` check whether comparison returns `0` under the map's ordering; they do not require `q` and the key stored in the tree to be the exact same object by `==`.

A `Comparator` must define a proper ordering relation and should be consistent with `equals` so that `TreeMap` fully obeys the `Map` contract. Do not swap the `Comparator` or mutate properties used to sort keys while they are in use as if the tree would automatically reorganize itself.

## 7. Java 17 Example: `null`, Snapshots, and Reversed Views

Save as **NeighborEntrySemantics.java**:

```java
import java.util.ArrayList;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class NeighborEntrySemantics {
    static String format(Map.Entry<Integer, String> entry) {
        return entry == null ? "none" : entry.getKey() + "=" + entry.getValue();
    }

    public static void main(String[] args) {
        NavigableMap<Integer, String> map = new TreeMap<>();
        map.put(10, "ten");
        map.put(20, null);
        map.put(30, "thirty");

        Map.Entry<Integer, String> saved = map.floorEntry(20);
        System.out.println("entry exists: " + (saved != null));
        System.out.println("snapshot before put: " + format(saved));
        map.put(20, "updated");
        System.out.println("current value: " + map.get(20));
        System.out.println("snapshot after put: " + format(saved));
        try {
            saved.setValue("changed through entry");
        } catch (UnsupportedOperationException expected) {
            System.out.println("setValue: UnsupportedOperationException");
        }

        NavigableMap<Integer, String> descending = map.descendingMap();
        System.out.println("descending keys: " + new ArrayList<>(descending.keySet()));
        System.out.println("descending lower 25: " + format(descending.lowerEntry(25)));
        System.out.println("descending floor 25: " + format(descending.floorEntry(25)));
        System.out.println("descending ceiling 25: " + format(descending.ceilingEntry(25)));
        System.out.println("descending higher 25: " + format(descending.higherEntry(25)));
        System.out.println("original keys: " + new ArrayList<>(map.keySet()));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NeighborEntrySemantics.java
java NeighborEntrySemantics
```

Stdout on the stated environment:

```text
entry exists: true
snapshot before put: 20=null
current value: updated
snapshot after put: 20=null
setValue: UnsupportedOperationException
descending keys: [30, 20, 10]
descending lower 25: 30=thirty
descending floor 25: 30=thirty
descending ceiling 25: 20=updated
descending higher 25: 20=updated
original keys: [10, 20, 30]
```

### 7.1. An Entry Exists Even When Its Value Is `null`

`saved` is non-null because key 20 is a valid candidate for `floorEntry(20)`. Its value is `null`, which is not the same as "no result."

After `put(20, "updated")`, `get` on the map returns the new value. `saved` still holds `20=null` because it is a snapshot of the mapping pair received earlier.

### 7.2. `setValue` Is Rejected Under This Entry Contract

Calling `saved.setValue` throws `UnsupportedOperationException`. The example catches the exception to demonstrate the behavior of the returned object.

In normal usage, update through the map as shown in the previous section rather than using exceptions for control flow.

### 7.3. Original Data and Different Viewing Order

The `descending` view traverses 30, 20, 10. At `q = 25`, `lower`/`floor` on the view select 30, and `ceiling`/`higher` select 20.

The original map still has the key sequence 10, 20, 30. No reordering of the original map occurs; there is simply a different ordering perspective over the same data.

## 8. Choosing a Method from Business Requirements

Write out the condition clearly before recalling the API name.

| Condition to find, in map order | Appropriate method |
| --- | --- |
| Last milestone before `q`, excluding `q` | `lowerEntry(q)` |
| Last milestone not exceeding `q` | `floorEntry(q)` |
| First milestone not less than `q` | `ceilingEntry(q)` |
| First milestone after `q`, excluding `q` | `higherEntry(q)` |

### 8.1. Configuration Effective from a Milestone

Suppose versions start at 10, 20, 30. Each version is considered effective from its start milestone up until just before the next version.

At 25, the version with the greatest start milestone not exceeding 25 is 20: use `floorEntry`.

At exactly 20, version 20 must be selected. Using `lowerEntry` would fall back to 10 and cause a bug right at the version transition point.

If querying before milestone 10, `floorEntry` returns no result. The application must decide whether that means a missing configuration, a default configuration, or another case; the API does not guess that policy.

### 8.2. Finding a Task at the Current Time or Later

If a task can start immediately at `q`, use `ceilingEntry(q)`.

If the rule requires the milestone to be strictly after `q`, use `higherEntry(q)`.

The two requirements differ only by equality, yet they determine whether an item is processed immediately or skipped.

### 8.3. Finding the Version Immediately Before or After a Key

When `q` is already in the map and you need a neighbor different from it, `lower`/`higher` are the appropriate operations.

If you use `floor`/`ceiling`, the result may be `q` itself rather than a different neighbor.

Do not adjust `q` to `q - 1` or `q + 1` to simulate strict inequality. That approach depends on the data type, can overflow, and does not generalize to all `Comparator` implementations or key types.

## 9. "Closest on One Side" vs. "Closest by Distance"

The four navigation operations select by ordering relation and boundary direction. They do not compute arithmetic distance.

With keys 10 and 20:

- At `q = 12`, `floor` chooses 10 and `ceiling` chooses 20; 10 is closer in numeric distance.
- At `q = 18`, `floor` still chooses 10 and `ceiling` still chooses 20; this time 20 is closer.

To pick the closest key by absolute distance on natural numbers, you can fetch both the `floor` and `ceiling` candidates, compare their distances, handle the case where only one side exists, and define a tie-breaking rule.

A general `Comparator` only defines an ordering; it does not automatically provide a meaningful business distance function.

If computing differences between `int` keys near large bounds, perform the arithmetic in a sufficiently wide type before subtracting. Do not let an `abs` call on an overflowed `int` difference pick the wrong candidate.

These distance rules are an additional selection step in the application, not a hidden meaning of `floorEntry` or `ceilingEntry`.

## 10. `Entry`, `Key`, `get`, and `poll` Serve Different Needs

### 10.1. If You Only Need the Key, Use the Corresponding `Key` Method

`lowerKey`, `floorKey`, `ceilingKey`, and `higherKey` apply the same relations but return only the key.

If you need both the key and the value, use the `Entry` method to get the matching mapping pair directly, rather than finding the key and calling `get` a second time.

In a program with concurrent modifications, two separate calls do not automatically form a consistent snapshot. `TreeMap` is also not thread-safe on its own.

### 10.2. `get` Only Finds an Equivalent Key, Not a Neighbor

`get(q)` does not automatically fall back to `floor` when `q` is absent.

For example, if the map has 10, 20, 30, `get(25)` has no equivalent mapping. `floorEntry(25)` can return `20=twenty`.

Do not mix the "exact key lookup" policy and the "nearest applicable milestone" policy through ad-hoc `null` handling.

### 10.3. Navigation Does Not Remove; `poll` Does

The four operations discussed here only locate and return a result. They do not reduce `size`.

`pollFirstEntry`/`pollLastEntry` retrieve and remove boundary entries. Those are different APIs with explicit data-mutating semantics.

If you want to remove a neighbor you just found, you need a separate removal operation and must consider atomicity if the state is shared; do not call `lowerEntry` and assume the item has left the map.

## 11. `null` Keys and Query Validity

### 11.1. The Query Key Must Be Comparable

With natural ordering, do not use `null` as a valid milestone. With a custom `Comparator`, whether `null` is accepted depends on the `Comparator` and the map's contract.

Navigation APIs may throw an exception when a key cannot be properly compared. Using generics and clear key rules helps avoid nonsensical calls.

An empty map only means there are no candidates; you should not treat the empty state as a reason to ignore all validity constraints on the key/query type.

### 11.2. A Valid `null` Key Differs from No Entry

If you intentionally use `Comparator.nullsFirst` to allow `null` keys, a result entry may have `getKey()` equal to `null`.

For example, a map using `nullsFirst` contains `null="null-key"` and `10="ten"`. `lowerEntry(10)` can be the entry for the `null` key. That entry itself is still non-null.

In this case, `lowerKey(10)` returning `null` is not enough to distinguish a valid `null` key from having no candidate. Use the `Entry` result when you need to distinguish the two cases.

This is why three concepts must be kept separate:

- No result entry exists.
- An entry with a `null` key exists, if permitted.
- An entry with a `null` value exists.

If the application does not need `null` keys, you can choose a policy that forbids them to keep the model simpler. Do not use `null` as an "infinitely small key" without a supporting `Comparator`.

## 12. Tree Search Mechanism and Usage Cost

`TreeMap` is based on a balanced search tree. A neighbor lookup does not need to scan every entry sequentially.

Visualizing `floorEntry(q)`:

1. If the current key is greater than `q`, the target candidate must lie on the smaller side.
2. If the current key does not exceed `q`, it is a candidate; a potentially better one lies on the larger side while still not exceeding `q`.
3. If an exact match with `q` is encountered, you already have the best candidate for `≤`.
4. When you can go no further, return the matching candidate or no result.

`lower` follows the same search toward the smaller side without accepting equality with `q`. `ceiling`/`higher` have a symmetric pattern toward the larger side.

The OpenJDK source may implement candidate lookup via specific child and parent pointers. The explanation above is a way to reason about the result condition, not a requirement that the source code must maintain a single candidate variable in one exact pattern.

### 12.1. A Query Costs Proportional to Tree Height

For `TreeMap` and a constant-time key comparison model, these navigation paths take `O(log n)` time on the balanced tree.

If key comparison is expensive, that cost must also be accounted for. Do not treat a short method name as a constant-time guarantee.

### 12.2. Use for Positioning, Not as a Replacement for Iterators on Full Scans

A sequence of repeated `higherEntry` calls can be useful when a program needs independent neighbor queries.

However, if the goal is to traverse `k` consecutive entries, each new lookup can add `O(log n)`, yielding `O(k log n)` total. An iterator or range view has sequential traversal paths better suited for scanning.

In particular, calling `floorEntry` or `ceilingEntry` with the previously returned key as the next reference without changing anything can keep returning the same entry forever. When you need a different next key, the strict inequality of `higher`/`lower` reflects forward progress.

Choosing between an iterator and neighbor queries also depends on the goal and data-modification contract, not solely on avoiding a non-advancing loop.

## 13. How to Thoroughly Test All Boundaries

A dataset of three sufficiently spaced keys helps verify the following groups:

| Query group | What to verify |
| --- | --- |
| Less than all keys | `lower`/`floor` are missing; `ceiling`/`higher` select the first key in order |
| Equal to the first key | Strict and inclusive inequalities behave differently |
| Between two keys | The `lower`/`floor` pair and the `ceiling`/`higher` pair can yield the same result |
| Equal to a middle key | `floor`/`ceiling` can return that exact key |
| Equal to the last key | One strict side may have no result left |
| Greater than all keys | `lower`/`floor` select the last key; `ceiling`/`higher` are missing |
| Empty map | No entry for any valid query |
| Single-key map | Clearly verify equality on both sides |

Also test with a reversed `Comparator` to ensure the tests rely on the map's ordering relation rather than a fixed arithmetic condition.

For `Entry`, check existence, key, and value. A result with the right key that misinterprets a `null` value is still a bug in the caller.

To verify data immutability under queries, keep the expected mappings and verify the size/keys/values after the query sequence.

For entry snapshots, verify that updating the map with `put` does not change the already-received pair and do not use `setValue` as an update mechanism on `TreeMap` navigation entries.

## 14. Common Mistakes and How to Fix Them

| Misconception | Fix |
| --- | --- |
| `lower` and `floor` are the same because one test returned 20 for both | Also test with `q` equal to an existing key |
| `ceiling` is always the element after `q` | `ceiling` allows equality with `q`; `higher` excludes equality |
| The query must be added to the map first | Pass the query key directly to locate neighbors |
| When there is no result, the API automatically picks the opposite side | Handle `null` with an explicit policy |
| An entry with a `null` value means not found | Check `entry == null` first, separate from the mapping's value |
| Calling `setValue` on a navigation entry updates the map | These `TreeMap` entries do not support `setValue`; use the map API |
| `lower` is always the smaller number | Read according to the `Comparator`, including reversed views |
| `floor`/`ceiling` automatically pick the smallest distance | They pick by side; distance comparison is a separate step |
| Getting a neighbor result means the entry was removed | The four methods only search; they do not `poll` |
| Getting `Key` then calling `get` is always identical to an `Entry` snapshot | Two calls can diverge in state |
| `q - 1` can replace `lower` for all key types | Do not rely on arithmetic; use the right relational operation |
| Repeating `ceiling` with the found key will always advance | It can return the same key; choose `higher` or an iterator when appropriate |

## 15. Self-Check Exercises with Solutions

### Exercise 1: Equality

A natural-order map has 4, 8, 12. With `q = 8`, what are the keys of the four results `lower`, `floor`, `ceiling`, `higher`?

**Solution:** 4, 8, 8, 12.

### Exercise 2: Between Two Keys

Same map, `q = 10`. What are the four result keys?

**Solution:** 8, 8, 12, 12. There is no key equal to 10, so equality makes no difference within each pair.

### Exercise 3: Out of Bounds

With `q = 2`, is there a `lowerEntry` or `floorEntry`? What do `ceiling`/`higher` select?

**Solution:** `lower`/`floor` have no result; `ceiling`/`higher` select key 4.

### Exercise 4: Selecting the Effective Configuration

Versions start at milestones 100, 200, 300. At exactly 200, if the new version takes effect immediately at that milestone, use `lower` or `floor`?

**Solution:** `floorEntry(200)`, to select the version starting at 200. `lower` would fall back to 100.

### Exercise 5: `null` in the Value

A map has `8=null`. `floorEntry(8)` returns a non-null entry with a `null` value. Should it be treated as no candidate?

**Solution:** No. The mapping for key 8 exists; only its value is `null`.

### Exercise 6: Reversed Order

A map has the numbers 4, 8, 12, but with a reversed `Comparator`. Which number does `lowerEntry(10)` select?

**Solution:** 12, because 12 comes before 10 in the reversed order. Do not apply the "number smaller than 10" condition to a reversed map's relation.

### Exercise 7: Closest by Distance

A map has 10 and 20, `q = 18`. `floor` returns 10 and `ceiling` returns 20. Which method automatically decides that 20 is closest by absolute distance?

**Solution:** None of the four operations performs that selection automatically. The application compares the two distances and handles boundaries/ties if needed.

### Exercise 8: Entry Snapshot

`saved = floorEntry(8)` records `8="old"`. After `put(8, "new")`, must `saved` automatically change to `"new"`?

**Solution:** No. A `TreeMap` navigation entry is a mapping snapshot, not a live update handle to the map.

### Exercise 9: Advancing to the Next Key

You found key 8 and want a greater key different from 8. Does `ceilingEntry(8)` guarantee advancing to a different key?

**Solution:** No. It can return 8 again; `higherEntry(8)` is what requires strictly greater in the map's order.

## 16. References

- [NavigableMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html): the four neighbor relations, `Key` methods, and reversed view semantics.
- [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): class-specific contract, key rules, and returned entries.
- [TreeMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java): candidate search paths and `exportEntry`.
- [Map.Entry Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html): key–value pairs and the optional nature of `setValue`.

Choosing the right one of the four operations starts from the condition you need to find: which side, whether equality is included, and in what order. Then handle the existence of the entry separately from the key–value content that the entry carries.
