# ConcurrentSkipListMap and ConcurrentSkipListSet in Java

In Java concurrency, not every collection accessed by multiple threads only needs to store and look up elements. Some use cases also need to **maintain sorted keys**, query the nearest element, traverse in order, or work with a **key range** while other threads are updating it. Two structures in `java.util.concurrent` address this group of requirements:

- **`ConcurrentSkipListMap<K,V>`:** a concurrent map **ordered by key**, implementing the `ConcurrentNavigableMap`, `NavigableMap`, and `SortedMap` contracts; supports finding predecessor/successor keys and range views.
- **`ConcurrentSkipListSet<E>`:** a concurrent set **with ordered elements**, implementing `NavigableSet` and `SortedSet`; supports adding/removing/finding neighbors and range views.

Both are based on the **skip list** idea, a multi-level linked structure that supports search, insertion, and deletion with **expected O(log n) complexity**. Operations on the collection are designed for concurrent access without requiring user-side locking of the entire structure in typical cases.

However, the word "concurrent" does **not** mean that any sequence of multiple operations is a transaction, that iterators are immutable snapshots, that the element count can always be read in O(1), or that mutable value objects automatically become thread-safe. This article analyzes those boundaries using Java 17+, focusing on explaining the API, runnable examples, and common design mistakes.

**Scope:** **Concurrent Collections** in **general Java concurrency**. No Spring-specific collections, annotations, or schedulers are used; Spring-related topics are reserved for a separate chapter.

## 1. Why do we need an ordered concurrent collection?

Suppose a system stores tasks by timestamp:

```text
1700000100 -> task A
1700000120 -> task B
1700000190 -> task C
```

While worker A adds new tasks, worker B needs to find the task with the **largest timestamp not exceeding the deadline**; worker C needs to traverse a timestamp range. `ConcurrentHashMap` provides concurrent access by key, but **does not maintain key ordering** to perform `floorKey`, `ceilingKey`, or `subMap`.

`TreeMap` has ordering and the `NavigableMap` API, but it is **not safe when multiple threads modify/read it concurrently without proper synchronization**. Simply adding `volatile` to the variable referencing `TreeMap` does not make its internal operations thread-safe either.

`ConcurrentSkipListMap` satisfies two requirements **simultaneously**:

1. Individual operations have a concurrent contract.
2. Keys are organized by **natural ordering** or a provided `Comparator`.

`ConcurrentSkipListSet` is the corresponding structure when you only care about a **set of keys/elements**, without values.

## 2. Skip list: visualizing the multi-level structure

A skip list maintains order at the lowest level and uses "shortcuts" at higher levels:

```text
Level 3: HEAD ----------------------> 50
Level 2: HEAD ----------> 30 ------> 50
Level 1: HEAD -> 10 ---> 30 -> 40 -> 50
Level 0: HEAD -> 10 -> 20 -> 30 -> 40 -> 50 -> 60
                        ^
                   ascending keys
```

The diagram only illustrates the idea; the actual number of levels and how links are maintained are implementation details. When searching for `40`, the algorithm can take shortcuts at higher levels and then descend instead of sequentially scanning every node from the beginning.

Implications:

- Keys/elements are accessed in ascending order.
- Search, insert, and remove have **expected average O(log n)**, not a hard worst-case guarantee for every execution schedule and every input.
- A concurrent implementation must coordinate link changes across multiple threads; you should not assume the entire collection uses a single shared monitor that blocks all activity.
- Skip lists use extra pointers/indexes in exchange for ordered navigation capabilities.
- Ordering is strictly **comparator ordering**, not thread arrival order or `put` call order.

Do not write business logic that depends on level heights or internal random decisions of a node; the API guarantees ordered relationships and operations, not the shape of the graph.

## 3. Creating a `ConcurrentSkipListMap`

You only need to import:

```java
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.ConcurrentNavigableMap;
```

A few initialization forms:

```java
ConcurrentSkipListMap<Integer, String> byId =
        new ConcurrentSkipListMap<>();

ConcurrentSkipListMap<String, Integer> reverse =
        new ConcurrentSkipListMap<>(
                java.util.Comparator.reverseOrder());
```

These are illustrative declarations within a valid scope. With the no-comparator constructor, keys must have a compatible **natural ordering**, typically via `Comparable`; for example `Integer`, `Long`, `String`.

When passing a comparator, the map uses that comparator to sort and determine **whether two keys occupy the same logical position**. Therefore, the comparator does not just affect how things are printed—it also affects lookup/duplicate-key semantics.

If multiple threads use the same map, you can share the reference after initialization through an appropriate publication mechanism: passing via a constructor, a `final` field, or through an executor/concurrent mechanism. A concurrent class itself does not automatically give good visibility to an improperly published reference.

## 4. Basic map operations

Commonly used operations:

| Operation | Meaning |
| --- | --- |
| `put(key,value)` | Associates the value, returning the previous value if any |
| `get(key)` | Reads the current mapping |
| `remove(key)` | Removes the mapping if present |
| `putIfAbsent(key,value)` | Inserts only if no mapping exists per contract |
| `remove(key,value)` | Removes only if the current mapping matches the expected value |
| `replace(key,old,new)` | Conditionally replaces based on the value |
| `computeIfAbsent(key,f)` | Creates a value when absent using the remapping mechanism |
| `computeIfPresent(key,f)` | Updates when the key is currently present |
| `compute(key,f)` | Computes a new mapping from the current mapping |
| `merge(key,value,f)` | Combines the new value with the old value if already present |

These operations are atomic updates with respect to **a single mapping/key** per their respective contracts. That **does not create a transaction across two keys**.

Incorrect example when a multi-key invariant is required:

```java
if (map.get("a") > 0) {
    map.put("a", map.get("a") - 1);
    map.put("b", map.get("b") + 1);
}
```

This is an **illustrative anti-pattern**; `map` assumes both keys/values already exist. Three consecutive reads/writes do not form an atomic transfer. Another thread can interleave, causing lost updates or violating the `a+b` sum invariant. When a multi-key transaction is needed, design higher-level synchronization or an atomic state object.

## 5. Java 17+ example: ordering, lookup, and neighboring keys

Save as `SkipListMapBasicsDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;

public class SkipListMapBasicsDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        map.put(30, "thirty");
        map.put(10, "ten");
        map.put(50, "fifty");
        map.put(20, "twenty");

        System.out.println("Keys: " + map.navigableKeySet());
        System.out.println("First: " + map.firstKey());
        System.out.println("Last: " + map.lastKey());
        System.out.println("Floor 25: " + map.floorKey(25));
        System.out.println("Ceiling 25: " + map.ceilingKey(25));
        System.out.println("Lower 20: " + map.lowerKey(20));
        System.out.println("Higher 20: " + map.higherKey(20));
        System.out.println("Value at 30: " + map.get(30));
    }
}
```

Run:

```bash
javac SkipListMapBasicsDemo.java
java SkipListMapBasicsDemo
```

Exact stdout when no other thread is modifying the map:

```text
Keys: [10, 20, 30, 50]
First: 10
Last: 50
Floor 25: 20
Ceiling 25: 30
Lower 20: 10
Higher 20: 30
Value at 30: thirty
```

Key order is **ascending by `Integer.compareTo`**, even though the initial `put` order was 30, 10, 50, 20. The four operations `floorKey`, `ceilingKey`, `lowerKey`, and `higherKey` have distinct semantics and should not be replaced by guessing a "nearest element".

## 6. Distinguishing `lower/floor/ceiling/higher`

For a target key `k`:

| Operation | Relationship to `k` | If no candidate exists |
| --- | --- | --- |
| `lowerKey(k)` | Greatest key **strictly less than k** | `null` |
| `floorKey(k)` | Greatest key **less than or equal to k** | `null` |
| `ceilingKey(k)` | Least key **greater than or equal to k** | `null` |
| `higherKey(k)` | Least key **strictly greater than k** | `null` |

Example with keys `[10,20,30]`:

```text
lowerKey(20)   -> 10
floorKey(20)   -> 20
ceilingKey(20) -> 20
higherKey(20)  -> 30

floorKey(5)    -> null
ceilingKey(35) -> null
```

Do not confuse `floor` with **floating-point rounding**; this name only refers to an ordering relationship. With a custom comparator, "less than" and "greater than" are both **according to the comparator**, not necessarily numeric value or default alphabetical order.

If you need both the key and its corresponding value in **one entry**, use `lowerEntry`, `floorEntry`, `ceilingEntry`, or `higherEntry`. Fetching the key and then calling `get(key)` separately are **two different operations**; under concurrent removal, the value may have disappeared between the two reads.

## 7. First/last and polling entries: reading vs. removing

The map provides:

- `firstKey()`, `lastKey()`: retrieves the first/last key, throwing `NoSuchElementException` if the map is currently empty.
- `firstEntry()`, `lastEntry()`: returns the corresponding entry, or `null` when none exists.
- `pollFirstEntry()`, `pollLastEntry()`: **removes and returns** the first/last entry in order.
- `descendingMap()`: navigable view in reverse order.
- `navigableKeySet()`, `descendingKeySet()`: views of the keys.

`pollFirstEntry` is especially useful when multiple workers want to **claim the element with the smallest priority key**: each removal of an entry is a single operation, so there is no need to write a separate `firstEntry` followed by `remove`. However:

- Another worker may insert a smaller key **right after** the poll.
- You cannot infer that you have polled the "smallest element of all future time".
- If tasks need deadline checks and waiting when the map is empty, CSLM is **not a blocking queue**: you must combine it with signaling/conditions or use an appropriate scheduler structure.
- With a custom comparator, "first" means **smallest according to the comparator**.

## 8. Java 17+ example: poll and descending view

Save as `SkipListPollDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;

public class SkipListPollDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        map.put(5, "five");
        map.put(1, "one");
        map.put(3, "three");

        System.out.println("Ascending: " + map.navigableKeySet());
        System.out.println("Descending: " + map.descendingKeySet());

        var first = map.pollFirstEntry();
        var last = map.pollLastEntry();

        System.out.println("Polled first key: " + first.getKey());
        System.out.println("Polled last key: " + last.getKey());
        System.out.println("Remaining keys: " + map.navigableKeySet());
    }
}
```

```bash
javac SkipListPollDemo.java
java SkipListPollDemo
```

Exact stdout:

```text
Ascending: [1, 3, 5]
Descending: [5, 3, 1]
Polled first key: 1
Polled last key: 5
Remaining keys: [3]
```

`pollFirstEntry()` and `pollLastEntry()` **mutate** the map. In a program without competing writers, the results are 1 and 5 respectively. If `firstEntry` were used instead of `pollFirstEntry`, the first entry would remain in the map.

Entries returned from navigation operations are records **representing the mapping at the time of observation**; do not treat `Map.Entry.setValue` on them as a way to update the mapping in the collection—to change a value, use map APIs such as `replace` or `compute`.

## 9. `ConcurrentSkipListSet`: when only sorted elements are needed

When values are not needed, use `ConcurrentSkipListSet<E>`. It supports:

- `add(e)` and `remove(e)` for membership.
- `contains(e)` to check for an element.
- `first()` and `last()`.
- `lower(e)`, `floor(e)`, `ceiling(e)`, `higher(e)`.
- `pollFirst()` and `pollLast()` to retrieve and remove the first/last element.
- `subSet`, `headSet`, `tailSet`, and `descendingSet`.

Like the map, the set sorts by natural ordering or a comparator. Two elements that **compare equal to 0 according to the comparator** are treated as equivalent for membership, even if `equals` says otherwise.

`ConcurrentSkipListSet` is suitable for ordered unique IDs, watermark candidates, timestamp markers, or token sets that need range queries. It is **not a multiset**: if you need to count occurrences of the same key, you must use a key → count map with appropriate updates.

## 10. Java 17+ example: set operations

Save as `SkipListSetDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListSet;

public class SkipListSetDemo {
    public static void main(String[] args) {
        ConcurrentSkipListSet<Integer> set =
                new ConcurrentSkipListSet<>();

        System.out.println("Added 20: " + set.add(20));
        set.add(10);
        set.add(30);
        System.out.println("Duplicate 20: " + set.add(20));
        System.out.println("Sorted: " + set);
        System.out.println("Floor 25: " + set.floor(25));
        System.out.println("Ceiling 25: " + set.ceiling(25));
        System.out.println("Polled first: " + set.pollFirst());
        System.out.println("Remaining: " + set);
    }
}
```

```bash
javac SkipListSetDemo.java
java SkipListSetDemo
```

Exact stdout:

```text
Added 20: true
Duplicate 20: false
Sorted: [10, 20, 30]
Floor 25: 20
Ceiling 25: 30
Polled first: 10
Remaining: [20, 30]
```

The second `add(20)` returns `false` because 20 already exists according to the comparator. The set does not store duplicates. `pollFirst` both returns 10 and removes 10. Printing the collection directly produces guaranteed output in this example only because no other thread is modifying it.

## 11. Both map and set disallow `null`

These two classes **do not allow `null` keys/elements**; `ConcurrentSkipListMap` also **does not allow `null` values**.

The important API-level reason: `map.get(key) == null` is used to indicate **no mapping**, not "a mapping exists with a null value". In a concurrent environment, allowing `null` to represent both absent and a valid value would make conditional operations ambiguous.

Incorrect example:

```java
ConcurrentSkipListMap<String, String> map =
        new ConcurrentSkipListMap<>();

map.put("ok", null); // NullPointerException
map.put(null, "x");  // NullPointerException
```

This is an illustrative error example, not a complete exception-handling program.

Instead of storing `null`:

- Use `Optional<T>` inside a **value object** if you need to represent an intentionally missing data state.
- Use a record/value type such as `Status(MISSING)` or a sentinel enum.
- Or remove the mapping when there is no longer a valid value, per the business contract.

**Do not confuse** "a method returning `null` because there is no neighbor/key" with "the collection allows storing `null`". `floorKey` returns `null` if there is no candidate, but a `null` key is not a valid key.

## 12. Comparator determines both ordering and uniqueness

With natural order, `String` uses lexicographic order and `Integer` uses numeric order. When passing a custom `Comparator`, the collection uses the **comparison result** to navigate and decide whether two keys/elements are equivalent.

A flawed comparator can cause logic bugs:

```java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);
```

If comparing only by length, two strings with different contents such as `"ab"` and `"cd"` compare as 0, so in an ordered map they are treated as a single logical key.

If you want to distinguish strings of the same length, add a tie-breaker:

```java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
```

These are illustrative snippets (requiring `import java.util.Comparator` in source). A comparator must also have the required consistency properties: reflexivity for equivalence, sign consistency, and transitivity. If a comparator relies on mutable state that changes over time, the ordered structure may fail to locate keys as expected.

## 13. Java 17+ example: comparator treating two keys as one

Save as `SkipListComparatorDemo.java`:

```java
import java.util.Comparator;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.ConcurrentSkipListSet;

public class SkipListComparatorDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<String, Integer> map =
                new ConcurrentSkipListMap<>(
                        String.CASE_INSENSITIVE_ORDER);

        map.put("Alpha", 1);
        map.put("ALPHA", 2);

        System.out.println("Case-insensitive size: " + map.size());
        System.out.println("Lookup alpha: " + map.get("alpha"));

        Comparator<String> byLengthThenText =
                Comparator.comparingInt(String::length)
                          .thenComparing(Comparator.naturalOrder());

        ConcurrentSkipListSet<String> set =
                new ConcurrentSkipListSet<>(byLengthThenText);

        set.add("bb");
        set.add("c");
        set.add("a");

        System.out.println("Length order: " + set);
    }
}
```

```bash
javac SkipListComparatorDemo.java
java SkipListComparatorDemo
```

Exact stdout:

```text
Case-insensitive size: 1
Lookup alpha: 2
Length order: [a, c, bb]
```

In the case-insensitive map, `"Alpha"` and `"ALPHA"` compare to 0; the second `put` updates the value of **one logical key** instead of creating two entries. For the set, the tie-breaker prevents `"a"` and `"c"` from being treated as a single element just because both have length 1.

**Note on the `SortedMap`/`SortedSet` contract:** ordering should be **consistent with equals** if you want to adhere to general `Map`/`Set` semantics based on `equals`. An inconsistent comparator may still run, but behavior when comparing with other collections can be surprising. Do not assume `equals` and `compare` always define "duplicate" in the same way.

## 14. Range views: `subMap`, `headMap`, and `tailMap`

One advantage over `ConcurrentHashMap` is key-range querying:

```java
map.subMap(fromKey, true, toKey, false);
map.headMap(toKey, false);
map.tailMap(fromKey, true);
```

These are illustrative snippets. The overloads accepting `boolean inclusive` let you explicitly specify whether the boundary includes the bound key.

Important: **the result is a view backed by the original map**, not a copied snapshot. That means:

- Valid modifications through the view can affect the original map.
- Changes to the original map within the range will appear when observing the view afterward.
- If other threads modify the original map while you iterate over the view, the iterator still has weakly consistent semantics.
- A key outside the range bounds cannot be added through the view as if it were within the valid range; the operation can throw `IllegalArgumentException`.
- A view does not freeze the set of keys at a single point in time.

An API that receives a range view and uses it as an **exact point-in-time snapshot report** will fail requirements if writers remain active.

## 15. Java 17+ example: range views are live/backed

Save as `SkipListRangeViewDemo.java`:

```java
import java.util.concurrent.ConcurrentNavigableMap;
import java.util.concurrent.ConcurrentSkipListMap;

public class SkipListRangeViewDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        for (int i = 1; i <= 6; i++) {
            map.put(i, "v" + i);
        }

        ConcurrentNavigableMap<Integer, String> middle =
                map.subMap(2, true, 5, false);

        System.out.println("Middle before: "
                + middle.navigableKeySet());

        middle.remove(3);
        map.put(4, "changed");

        System.out.println("Main after remove: "
                + map.navigableKeySet());
        System.out.println("Middle sees update: "
                + middle.get(4));

        boolean rejected = false;
        try {
            middle.put(6, "outside");
        } catch (IllegalArgumentException e) {
            rejected = true;
        }
        System.out.println("Outside key rejected: " + rejected);
    }
}
```

```bash
javac SkipListRangeViewDemo.java
java SkipListRangeViewDemo
```

Exact stdout:

```text
Middle before: [2, 3, 4]
Main after remove: [1, 2, 4, 5, 6]
Middle sees update: changed
Outside key rejected: true
```

`subMap(2, true, 5, false)` includes 2, 3, 4 and excludes 5. `middle.remove(3)` removes from the original map. `map.put(4, "changed")` modifies through the original map and the view reads the new value. `middle.put(6,...)` exceeds the view's bounds and is therefore rejected.

**Conclusion:** a range view is a way to constrain the key namespace, not a snapshot-isolation mechanism.

## 16. Range views on `ConcurrentSkipListSet`

For the set, the corresponding APIs are:

```java
ConcurrentSkipListSet<Integer> set =
        new ConcurrentSkipListSet<>();

set.add(10);
set.add(20);
set.add(30);
set.add(40);

NavigableSet<Integer> range =
        set.subSet(20, true, 40, false);
```

This is an illustrative snippet (requiring `import java.util.NavigableSet`). `range` contains 20 and 30 at that moment; changes on either the range or the set can be reflected in both.

`headSet(to, inclusive)` keeps elements below the bound; `tailSet(from, inclusive)` keeps elements above the bound. Overloads without boolean parameters follow the default boundary semantics of the `SortedSet` contract: `headSet` excludes the upper bound, `tailSet` includes the lower bound, and `subSet(from,to)` includes `from` and excludes `to`.

With a reverse-order comparator, boundary conditions are also interpreted **according to the comparator**. Do not use natural numeric ordering to infer the meaning of "from" and "to" in a descending view.

## 17. What is a weakly consistent iterator?

Iterators of concurrent skip list collections are **weakly consistent**:

- They can traverse while other threads are adding/removing without **using the fail-fast `ConcurrentModificationException` mechanism like iterators of many standard collections**.
- They may reflect **some** concurrent changes; they are not fixed snapshots.
- There is no guarantee that all elements added after the iterator was created will appear.
- There is no guarantee that the observed result is an atomic snapshot at a single point in time.
- Concurrent operations can cause iteration contents to differ across runs.
- Iteration still follows the collection's sorted ordering rules within the scope of iterator behavior, but do not infer that the result has the same set of elements as `keySet()` at any single instant.

**Two things to avoid:**

1. Using an iterator and assuming you have a "copy of the map at the exact start time".
2. Catching `ConcurrentModificationException` to build a retry loop, thinking that is the proper way to use this kind of collection.

If you need a stable snapshot for financial calculations or transaction decisions, design a dedicated snapshot/versioning mechanism or **quiesce writers**; simply using a concurrent collection is not enough.

## 18. Java 17+ example: iterator running while a writer updates

Save as `WeakIteratorDemo.java`:

```java
import java.util.Iterator;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class WeakIteratorDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        map.put(1, "one");
        map.put(2, "two");
        map.put(3, "three");

        Iterator<Integer> iterator =
                map.navigableKeySet().iterator();

        CountDownLatch begin = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            try {
                begin.await();
                while (iterator.hasNext()) {
                    iterator.next();
                }
            } catch (Throwable e) {
                failure.set(e);
            }
        }, "reader");

        Thread writer = new Thread(() -> {
            try {
                begin.await();
                map.put(4, "four");
                map.remove(2);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "writer");

        reader.start();
        writer.start();
        begin.countDown();
        reader.join();
        writer.join();

        System.out.println("Reader finished without error: "
                + (failure.get() == null));
        System.out.println("Final keys: "
                + map.navigableKeySet());
    }
}
```

```bash
javac WeakIteratorDemo.java
java WeakIteratorDemo
```

Stdout when there is no external interruption to the program:

```text
Reader finished without error: true
Final keys: [1, 3, 4]
```

**It does not print and does not promise which keys the reader saw.** It may have seen 2 before deletion, or seen 4 after insertion, depending on the scheduler. That is weak consistency. After both threads `join`, the map has no active writers, so `Final keys` is a stable and predictable state.

In this example, `failure` is written from the reader via `AtomicReference`; `main` reads it after `join`. Catching `Throwable` is a scoped choice **for reporting QA in the demo**, not a recommendation to swallow all exceptions/`Error`s in production applications.

## 19. `size()` is not necessarily O(1) or instantaneously exact

For `ConcurrentSkipListMap` and `ConcurrentSkipListSet`, `size()` does not have the same characteristics as `ArrayList.size()` or a stored atomic counter.

The Javadoc emphasizes:

- Determining the size may require **traversing the elements**.
- When multiple threads perform concurrent updates, the returned size may **not reflect the element count at a single point in time as expected by the caller**.
- The result should only be treated as an **observed estimate** while the collection is changing.
- Calling `size()` repeatedly on a hot path can be expensive on large maps/sets.
- Do not rely on `if (map.size() < limit) map.put(...)` to enforce a hard capacity.

If you need a capacity limit, use a bounded queue, semaphore, admission control, or a dedicated atomic protocol. A concurrent sorted map **does not have built-in max-capacity enforcement**.

**Important:** even if reading `size` returns 100, another thread can add/remove before you act on that number. That is a time-of-check-to-time-of-use issue, not just a performance issue.

## 20. Key-level atomic updates: `putIfAbsent`, `replace`, `remove(key,value)`

An incorrect pattern:

```java
if (!map.containsKey(key)) {
    map.put(key, value);
}
```

This is an illustrative snippet. With multiple threads, two threads can both observe absence and then both `put`; one value overwrites the other.

Use the conditional API:

```java
V previous = map.putIfAbsent(key, newValue);
```

`previous == null` indicates that a new mapping could be inserted when absent per the map's contract (since `null` values are not stored). Similarly:

```java
boolean changed = map.replace(key, expectedOldValue, newValue);
boolean removed = map.remove(key, expectedValue);
```

These snippets use generic notation; you must substitute types `V`/`key` and declarations in real code.

These operations are useful for **per-key compare-and-update**. However, `putIfAbsent` is not enough for the goal "the key must remain absent for the entire duration of task execution"; another thread could remove the mapping immediately after insertion.

## 21. Java 17+ example: conditional updates without lost updates

Save as `ConditionalSkipListDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;

public class ConditionalSkipListDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<String, Integer> map =
                new ConcurrentSkipListMap<>();

        Integer first = map.putIfAbsent("job", 10);
        Integer second = map.putIfAbsent("job", 20);

        boolean replacedWrong = map.replace("job", 7, 30);
        boolean replacedRight = map.replace("job", 10, 30);

        boolean removedWrong = map.remove("job", 20);
        boolean removedRight = map.remove("job", 30);

        System.out.println("First insertion was absent: "
                + (first == null));
        System.out.println("Second saw old value: " + second);
        System.out.println("Wrong replace: " + replacedWrong);
        System.out.println("Right replace: " + replacedRight);
        System.out.println("Wrong remove: " + removedWrong);
        System.out.println("Right remove: " + removedRight);
        System.out.println("Map empty: " + map.isEmpty());
    }
}
```

```bash
javac ConditionalSkipListDemo.java
java ConditionalSkipListDemo
```

Exact stdout:

```text
First insertion was absent: true
Second saw old value: 10
Wrong replace: false
Right replace: true
Wrong remove: false
Right remove: true
Map empty: true
```

The example has no actual contention, but it demonstrates the **conditional update contract** instead of a "read then write" pair. In a concurrent application, you must handle the `false` branch or the current value modified by another thread, rather than assuming the operation is guaranteed to succeed.

## 22. `compute`, `merge`, and functions that may be invoked multiple times

APIs such as:

```java
map.compute(key, (k, oldValue) -> nextValue(oldValue));

map.merge(key, 1, Integer::sum);

map.computeIfAbsent(key, k -> buildValue(k));
```

help express per-key updates instead of separate `get`/`put` calls. However, you must distinguish them from a transaction whose callback **runs strictly once**.

For `ConcurrentSkipListMap`, concurrent update logic may **retry** because another thread modified the mapping. The Javadoc for remapping operations warns that the function **is not necessarily applied once atomically as users might expect**; therefore the function should:

- **Have no non-idempotent side effects** (sending emails, charging money, calling remote APIs).
- Not depend on each callback invocation corresponding to one successful commit.
- Only compute output from input, be fast enough, and not block for long.
- Not modify the same map/key itself in a way that causes hard-to-control dependencies or recursion.
- Watch out for `null`: for remapping methods that allow returning `null`, `null` can mean **remove/no mapping**, not a valid value.

For example, if you want to increment a mapping's counter:

```java
map.merge("counter", 1, Integer::sum);
```

Integer addition **has no side effects**, so it is suitable when the implementation must retry. However, `Integer` can overflow if the counter is large; consider `Long` or a bounding policy.

## 23. Java 17+ example: multiple threads using `merge`

Save as `ConcurrentSkipListMergeDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;

public class ConcurrentSkipListMergeDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentSkipListMap<String, Integer> map =
                new ConcurrentSkipListMap<>();

        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[4];

        for (int t = 0; t < workers.length; t++) {
            workers[t] = new Thread(() -> {
                try {
                    start.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }

                for (int i = 0; i < 500; i++) {
                    map.merge("counter", 1, Integer::sum);
                }
            });
            workers[t].start();
        }

        start.countDown();

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Counter: " + map.get("counter"));
        System.out.println("Keys: " + map.navigableKeySet());
    }
}
```

```bash
javac ConcurrentSkipListMergeDemo.java
java ConcurrentSkipListMergeDemo
```

Stdout on a normal run with no external program interruption:

```text
Counter: 2000
Keys: [counter]
```

Four threads start together from the latch, each performing 500 `merge` calls: a logical total of 2,000. An expression like `map.put("counter", map.get("counter")+1)` lacks equivalent atomicity and can lose increments under concurrency.

Do not draw conclusions about the order of the 2,000 callback invocations or which worker won CAS first. Only the **final result of the mapping** is guaranteed. `Thread.join()` lets `main` wait for all workers before reading the result.

## 24. Mutable values do not automatically become thread-safe

The map is designed to be safe for concurrent operations on **mappings**, but value objects can be ordinary mutable types:

```java
ConcurrentSkipListMap<String, ArrayList<String>> map =
        new ConcurrentSkipListMap<>();
```

This is an illustrative snippet, requiring `import java.util.ArrayList`. If multiple threads retrieve the same `ArrayList` and call `add`, that value collection is **not automatically synchronized** just because it is placed inside a concurrent map.

Options:

1. Use **immutable** values, updating via `compute`/`replace` per key.
2. Use a value with its own thread-safe design if multiple threads need to mutate it in place.
3. Use a per-key lock or transaction-level protocol when multiple fields must be updated consistently.
4. Do not leak mutable values to callers that can modify them freely.
5. Even if the value is an immutable record, still pay attention to fields that reference mutable objects inside the record.

**Safe publication of a reference** and **thread safety of post-publication mutation** are two different issues. Concurrent `put`/`get` has proper memory consistency, but it does not turn a value's internal state into an atomic object.

## 25. "Snapshot" vs. "weakly consistent view"

A statement like:

```java
var snapshot = new java.util.TreeMap<>(map);
```

creates a new `TreeMap` object, but **if the source map is being modified during the copy**, the set of mappings read may come from different points in time. This is not automatically an atomic snapshot of the concurrent map.

To get an **accurate snapshot at a single logical point**, you need an additional protocol:

- Pause/coordinate writers using an external lock that **all writers** obey.
- Or use versioning/MVCC, immutable snapshot swapping, or a storage architecture with snapshot semantics.
- Or accept an **eventual/approximate snapshot** if the problem only needs statistics or rough display.

Copying after **all writers have finished and joined** produces a stable result set; in that case you can use `new TreeMap<>(map)` to make a copy that is no longer affected by later changes to the source map (except that mutable values are still referenced).

Do not call copying a "linearizable snapshot" while writers are active without an additional protocol.

## 26. `descendingMap` and reverse-order views

`descendingMap()` creates a reverse-order view of the map. `descendingSet()` does the same for the set. These are **backed views**, not copies.

Example:

```java
var reverse = map.descendingMap();
```

If the original has keys `[1,3,5]`, `reverse` traverses `[5,3,1]`. However, if another thread inserts `4` into the original map, the reverse view also reflects the live state at the time of observation.

For workloads that only need descending order occasionally, consider iterator cost. Java documentation notes that ascending-ordered views/iterators can be more efficient than descending variants on these implementations; do not assume both directions have identical performance characteristics.

Any update through the reverse view still affects the same backing map. Do not use a reverse view to create an independent index with its own lifecycle.

## 27. Comparison with other collections

| Collection | Concurrent access | Sorted/navigable ordering? | Key characteristics |
| --- | --- | --- | --- |
| `HashMap` | Not safe for unsynchronized concurrent mutation | No | Standard hash table |
| `TreeMap` | Not thread-safe on its own | Yes | Balanced tree, single-thread or external lock |
| `ConcurrentHashMap` | Yes | No | Key-based lookup/update, high throughput for unordered keys |
| `ConcurrentSkipListMap` | Yes | **Yes** | Sorted concurrent map, neighbor/range navigation |
| `HashSet` | Not safe for concurrent mutation | No | Standard set |
| `TreeSet` | Not thread-safe on its own | Yes | Sorted set, external synchronization when shared mutable |
| `ConcurrentSkipListSet` | Yes | **Yes** | Sorted concurrent set, `NavigableSet` |
| `CopyOnWriteArraySet` | Yes | Does not maintain sorted ordering | Suitable for many reads, very few writes; copies on modification |

Choose based on **query needs** and **workload characteristics**. If you only need random get/put by key without ordering, `ConcurrentHashMap` is usually simpler and has better throughput/overhead. If you need `floorEntry` or concurrent range-based queries, `ConcurrentSkipListMap` has a clear API advantage.

Do not pick a skip list just for the word "concurrent" while ignoring the fact that metadata/order maintenance costs more memory and CPU than a regular hash table.

## 28. Do not use CSLM as a blocking deadline queue

A timestamp-keyed map often tempts developers to write:

```java
while (true) {
    var first = map.firstEntry();
    if (first != null && first.getKey() <= now()) {
        map.remove(first.getKey());
        runTask(first.getValue());
    }
}
```

This is an illustrative anti-pattern; `now`/`runTask` are undefined.

Issues:

- Busy-spin loop when there is no work.
- `firstEntry` followed by `remove(key)` is not an atomic claim. Another thread may have already taken/removed/replaced the mapping; there is still risk of duplicate processing or picking up a stale value.
- If the deadline is in the future, there is no operation to wait until the exact deadline.
- If a task fails, there is no clear retry/requeue lifecycle.
- `now()` should use a time source matching scheduling semantics; clock adjustments can affect deadlines.
- If exact execution order is needed across multiple workers, sorted order alone is not enough to guarantee global execution ordering.

`DelayQueue` or `ScheduledExecutorService` is usually more appropriate for scheduled delayed work; `PriorityBlockingQueue` uses priority and blocking `take`, but **does not automatically wait until a deadline timestamp**. If you must use a map as an index, you must design signaling and atomic claiming with `pollFirstEntry`/conditional methods according to a protocol.

## 29. Complexity and performance choices

General overview:

| Operation | Typical characteristic |
| --- | --- |
| `get/put/remove` by key | Expected O(log n) |
| `floor/ceiling/lower/higher` | Expected O(log n) |
| Traversing all n elements | O(n) for an unchanging traversal |
| `size()` | May require traversal and cost O(n), unstable under concurrent updates |
| Range query with k results | Locate cost + traversal of k elements, but concurrent changes make observed results non-snapshot |
| Map's `containsValue` | May require scanning, should not be used as a secondary lookup index |

In real workloads, cost also depends on:

- Whether many writers contend on the same key or spread across the key space.
- Whether the comparator is CPU-expensive.
- Keys that are long, mutable, or have unstable hash/compare behavior.
- Ratio of range navigation to random get/put.
- Whether there are many descending traversals.
- Map size, memory footprint of skip-list indexes, and cache locality.
- Thread count, contention, allocation, and garbage collector.
- Number of composite operations requiring external synchronization.

**Expected complexity** is not a guarantee that every operation has a fixed time upper bound. Benchmarks should be run with data and contention matching the production environment; do not use a 10-key microbenchmark to draw conclusions for millions of elements.

## 30. Common mistakes

**1. "ConcurrentSkipListMap is like ConcurrentHashMap except it prints sorted."** No. It has `NavigableMap`/range semantics and a different structure; choose based on queries and cost.

**2. "A comparator only affects display."** False. `compare(a,b)==0` can cause two keys that differ by `equals` to be treated as the same logical key.

**3. "You can store null like in HashMap."** False. CSLM forbids `null` keys/values; CSLS forbids `null` elements.

**4. "A weakly consistent iterator is a snapshot at the moment iterator() is called."** False. It can reflect concurrent changes.

**5. "An iterator will always see every update that occurs after it starts."** No. There is no such guarantee.

**6. "size() is an O(1) count and completely exact with multiple writers."** False. It may require traversal and is not an atomic snapshot.

**7. "if (get==null) put is atomic."** False. Use `putIfAbsent` or a remapping operation per contract.

**8. "A compute function always runs strictly once."** Do not assume that; remapping can retry, so avoid side effects.

**9. "A concurrent map makes any ArrayList value thread-safe."** False. Mutable values must have their own synchronization.

**10. "subMap creates an independent copy."** False. It is a view backed by the original map.

**11. "You can put a key outside the range through subMap."** No. Out-of-range insertion is rejected.

**12. "firstEntry followed by remove is the same as pollFirstEntry."** False. That pair of operations can be interleaved by another thread.

**13. "An ordered set can store multiple comparator-equal elements."** False. Comparator returning 0 defines membership as a single element.

**14. "Concurrent collections automatically guarantee multi-key transactions."** False. A sequence of multiple operations can still interleave.

**15. "ConcurrentSkipListMap is a blocking queue that wakes up when an item is added."** No. It does not have `take`/`await` like `BlockingQueue`.

**16. "Reading lastKey from an empty map returns null."** False. `lastKey()` throws `NoSuchElementException`; `lastEntry()` returns `null` when empty.

**17. "descendingMap is a copy, unaffected by external updates."** False. It is a live view.

**18. "A concurrent sorted map automatically guarantees business processing order across threads."** No. It guarantees key navigation order, not task execution scheduling.

**19. "A volatile reference to a TreeMap is enough for safe updates."** False. Reference visibility does not protect internal `put`/`remove` operations.

**20. "Copying a map with new TreeMap is an atomic snapshot even while writers are modifying it."** False. A separate snapshot protocol is required if point-in-time consistency is demanded.

## 31. Checklist for real-world applications

1. **Do you actually need sorted/navigable queries?** If not, try `ConcurrentHashMap`.
2. **Is the comparator correct and immutable?** Consistent with `equals` when standard `Map`/`Set` contracts are needed.
3. **Are keys immutable?** Do not mutate fields participating in the comparator after insertion.
4. **Can `null` be passed in?** This map/set rejects `null`; represent missing state with an explicit value type.
5. **Do multi-key operations have invariants?** Requires separate coordination/transactions.
6. **Are you iterating entries while writers are active?** Weakly consistent, not a snapshot.
7. **Do you need exact `size` reporting?** Do not use `size` to prove capacity/transaction invariants.
8. **Are you using `subMap`/`subSet`?** Remember backed views and inclusive flags.
9. **Are you fetching `firstEntry` and removing separately?** If you need to claim the smallest head, consider `pollFirstEntry`.
10. **Do remapping callbacks have side effects?** If so, move side effects out of the retryable function.
11. **Are values mutable?** Choose immutable replacement or internal synchronization.
12. **Do you need blocking/deadline semantics?** Skip list map/set do not replace `BlockingQueue`.
13. **Does the workload have many descending iterations?** Benchmark in practice; ascending is often advantageous.
14. **Do you protect data after copying?** Shallow copy does not deep-copy mutable values.
15. **Did you check the empty case?** `firstKey`/`lastKey` can throw, `firstEntry`/`lastEntry` can return `null`.
16. **Do external monitors/locks need coordination?** Every writer must obey the same lock if an atomic external snapshot is desired.
17. **Do you need cleanup/shutdown?** The collection does not own worker threads; manage executors in their own lifecycle.
18. **Have you tested under realistic contention and ordering?** Use latches/joins and verify invariants instead of guessing execution schedules.

## 32. Self-check questions

**Question 1.** How does `ConcurrentSkipListMap` differ from `ConcurrentHashMap`?

CSLM maintains **sorted key order** and provides `NavigableMap`/range operations. CHM serves as a hash-based concurrent map and does not maintain sorted key order.

**Question 2.** Does `ConcurrentSkipListSet` allow adding two `String`s with different contents if `Comparator.compare` returns 0?

No. For ordered set membership, they are treated as one logical element according to the comparator.

**Question 3.** Given keys `[10,20,30]`, what are `floorKey(25)` and `higherKey(20)`?

20 and 30, respectively.

**Question 4.** Which keys does `subMap(2,true,5,false)` contain in the map `[1,2,3,4,5,6]`?

Keys 2, 3, 4. It is a **live view**, not a snapshot.

**Question 5.** Why does an iterator not throwing a fail-fast exception during writer updates not prove that it is a snapshot?

Because it is **weakly consistent**: traversal may reflect some updates but does not guarantee an atomic snapshot.

**Question 6.** Why is `size()` unsuitable for enforcing max-capacity under contention?

It may traverse, return unstable values while writers are active, and check-then-put still has a race.

**Question 7.** Does the map allow `null` as a value?

No. `null` values are forbidden, allowing `get()==null` to indicate absence.

**Question 8.** How is `map.putIfAbsent` better than `if(!map.containsKey(k)) map.put(k,v)`?

A single per-key conditional operation avoids the race between separate check and put.

**Question 9.** If the value is an `ArrayList`, does the concurrent map protect concurrent `add` calls?

No. Thread safety of mutable values is a separate responsibility.

**Question 10.** Are `map.firstEntry()` followed by `map.remove(key)` equivalent to `pollFirstEntry` under concurrency?

No. Another thread can interleave between the two calls. `pollFirstEntry` combines retrieving and removing the entry in one operation.

**Question 11.** Can `merge(key, 1, Integer::sum)` be used to increment a key's counter from multiple threads?

Yes, it fits a pure remapping function and update semantics, though overflow and contention must be considered.

**Question 12.** Can CSLM be used as a `DelayQueue` simply by choosing timestamps as keys?

No. CSLM does not provide blocking waits until a deadline or task lifecycle management. You need an appropriate scheduler/queue and protocol.

## 33. Summary

- **`ConcurrentSkipListMap`** is a key-sorted concurrent map; **`ConcurrentSkipListSet`** is an element-sorted concurrent set. Both provide navigation/range APIs, reject `null`, and use a comparator or natural ordering.
- **Skip lists** support search/insert/remove at expected logarithmic cost; they are not hash maps with arbitrary ordering.
- **`lower/floor/ceiling/higher`**, `pollFirst/pollLast`, `descendingMap/descendingSet`, and `subMap/subSet` are the core APIs when ordered queries are needed.
- **Range views are live/backed**, not snapshots. Iterators are **weakly consistent**—they can traverse alongside concurrent updates but do not provide an atomic snapshot.
- **`size()` can cost O(n) and be unstable while writers are active**; do not use it to enforce hard capacity.
- **Conditional updates/remapping** allow single-key operations without check-then-act races; callbacks should be pure because they may retry.
- **The comparator determines equivalence**; mutable keys, comparators missing tie-breakers, or comparators inconsistent with `equals` easily cause lookup/membership bugs.
- **Concurrent collections do not automatically protect mutable values or multi-key transactions**. Proper data ownership/locking/immutable state is required.
- If you only need unordered concurrent key/value access, `ConcurrentHashMap` may be a better fit; if you need blocking/delayed execution, use a queue/scheduler with the appropriate semantics.

The tool-selection question should be: **"Do I need to query by key order while data is being updated concurrently, or do I only need key-based lookup? Do I need a weakly consistent view, or a consistent snapshot/transaction?"**. Answering those two questions clearly will determine whether to use `ConcurrentSkipListMap`/`ConcurrentSkipListSet` or another Java concurrency construct.
