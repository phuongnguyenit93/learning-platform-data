# ConcurrentSkipListMap, ConcurrentSkipListSet, and Ordered Queries

## 1. When Concurrent Data Also Needs an Order for Searching

Suppose multiple threads record events over time. The program does not only ask "is there an event with this key?" but also asks:

- What is the latest event no later than a given timestamp?
- What is the first key after a given timestamp?
- Which events fall within a range?
- Can the leading entry be retrieved and removed without multiple threads taking the same entry?

These questions rely on an **ordering relationship** between keys. A hash table is suitable for exact-key lookups, but it does not inherently provide the concepts of "preceding key", "following key", or "range from A to B".

`ConcurrentSkipListMap<K, V>` combines a concurrent map with key ordering. `ConcurrentSkipListSet<E>` maintains unique elements in order and supports similar queries without a separate value part. Both classes are suitable when ordering is part of how queries are expressed while multiple threads access the data.

Three ideas should be separated from the start:

1. **Ordering:** which key or element is considered to come first?
2. **Navigation:** do you need the immediately preceding entry, the immediately following entry, or a range?
3. **Concurrency:** while the data is changing, how meaningful are the application's reads and sequences of operations?

Having an order does not mean having a fixed snapshot. Being safe for individual operations does not automatically turn multiple queries into a transaction. These are the two most important boundaries in this lesson.

The programs in this lesson are standalone, use Java 17 or later, and require no external libraries. Save each file with its exact name in the corresponding section, then compile and run it in the directory containing the file. Examples explaining range boundaries run sequentially so the results are clear. Multithreaded examples print results only after all `Future` instances have completed, avoiding dependence on arbitrary thread print order.

## 2. Structural Model and Interface Types

### 2.1. Maps Are Ordered by Key, Sets Are Ordered by Element

For a map, ordering is evaluated on `K`, not on `V`. Inserting `(30, "A")`, `(10, "Z")`, and `(20, "M")` into a map using natural numeric order yields key order 10, 20, 30. The values are traversed according to their corresponding keys, not automatically sorted as A, M, Z.

For a set, the element itself is the data used for comparison. If you need to keep multiple jobs with the same priority, you must define a total order sufficient to distinguish them rather than comparing only priority.

If no comparator is passed, both classes use natural ordering. If a `Comparator` is passed at construction, every notion of first, last, lower, higher, and range bounds follows that comparator.

### 2.2. Composed Capabilities

```text
Map
  → SortedMap: ordered keys
      → NavigableMap: neighbor lookup, range views, reverse order
          → ConcurrentNavigableMap: concurrent operations
              → ConcurrentSkipListMap

Set
  → SortedSet: ordered elements
      → NavigableSet: neighbor lookup, range views, reverse order
          → ConcurrentSkipListSet
```

The diagram illustrates capability relationships across interfaces; not every line represents a direct superclass. `ConcurrentSkipListSet` is built on top of `ConcurrentSkipListMap`, though callers still interact with it through set operations.

`ConcurrentSkipListMap` provides expected average O(log n) time cost for basic operations such as `get`, `containsKey`, `put`, and `remove`. `ConcurrentSkipListSet` has corresponding characteristics for `contains`, `add`, and `remove`. Do not interpret this characteristic as meaning every query, every traversal, or every real-world workload takes the same amount of time. See [ConcurrentSkipListMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html) and [ConcurrentSkipListSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html).

The name "skip list" suggests a search structure with levels that skip over segments of sorted data. When writing application code, what you should rely on is the query and concurrency contract of the class, not the height or internal shape of a particular list.

### 2.3. Input Requirements

Map keys must be mutually comparable under the chosen rule; the same applies to set elements. Mixing types without a common order or supplying an incompatible comparator can cause a `ClassCastException`.

The map does not allow `null` keys or values; the set does not allow `null` elements. Therefore, when a neighbor query returns `null`, that indicates no matching result was found for the query, not that a `null` element is stored.

Fields involved in comparison should remain stable for as long as the key or element resides in the structure. If you mutate the timestamp, priority, or ID used for comparison on an object already stored inside, the structure does not automatically move it to its new position. An immutable key object helps prevent this bug.

A comparator should also not read a changing ordering configuration or rely on unsynchronized shared state. A comparison whose outcome changes over time renders questions like "between two bounds" inconsistent and meaningless.

## 3. Finding Neighboring Keys or Elements

### 3.1. Four Relationships to Remember

Given a target `x`, navigation operations find the closest result satisfying a relationship without requiring `x` to exist:

| Intent | Map (key only) | Map (key-value entry) | Set (element) |
|---|---|---|---|
| Greatest strictly less than x | `lowerKey(x)` | `lowerEntry(x)` | `lower(x)` |
| Greatest less than or equal to x | `floorKey(x)` | `floorEntry(x)` | `floor(x)` |
| Least greater than or equal to x | `ceilingKey(x)` | `ceilingEntry(x)` | `ceiling(x)` |
| Least strictly greater than x | `higherKey(x)` | `higherEntry(x)` | `higher(x)` |

"Less than" and "greater than" are always interpreted according to the structure's ordering. `lower` and `higher` exclude the target; `floor` and `ceiling` allow equality with the target. If no candidate exists, the result is `null`. See [NavigableMap navigation methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html) and [NavigableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html).

With keys 10, 20, 30, the target 25 does not exist, yet `floorKey(25)` is 20 and `ceilingKey(25)` is 30. With target 20, `lowerKey(20)` is 10 whereas `floorKey(20)` is 20. That is the difference between exclusive and inclusive boundary queries.

### 3.2. Program with a Map and Entry Objects

File `OrderedMapQueriesDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;

public class OrderedMapQueriesDemo {
    public static void main(String[] args) {
        var values = new ConcurrentSkipListMap<Integer, String>();
        values.put(30, "thirty");
        values.put(10, "ten");
        values.put(20, "twenty");

        System.out.println("keys=" + values.keySet());
        System.out.println("lower20=" + values.lowerKey(20));
        System.out.println("floor20=" + values.floorKey(20));
        System.out.println("ceiling25=" + values.ceilingKey(25));
        System.out.println("higher30=" + values.higherKey(30));
        System.out.println("floorEntry25=" + values.floorEntry(25));
        System.out.println("first=" + values.firstEntry());
        System.out.println("last=" + values.lastEntry());

        var observed = values.floorEntry(25);
        values.put(20, "TWENTY");
        System.out.println("observedValue=" + observed.getValue());
        System.out.println("currentValue=" + values.get(20));
        try {
            observed.setValue("changed");
        } catch (UnsupportedOperationException ex) {
            System.out.println("entryWrite=" + ex.getClass().getSimpleName());
        }

        var empty = new ConcurrentSkipListMap<Integer, String>();
        System.out.println("emptyFirstEntry=" + empty.firstEntry());
        try {
            empty.firstKey();
        } catch (java.util.NoSuchElementException ex) {
            System.out.println("emptyFirstKey=" + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 OrderedMapQueriesDemo.java
java OrderedMapQueriesDemo
```

Stdout:

```text
keys=[10, 20, 30]
lower20=10
floor20=20
ceiling25=30
higher30=null
floorEntry25=20=twenty
first=10=ten
last=30=thirty
observedValue=twenty
currentValue=TWENTY
entryWrite=UnsupportedOperationException
emptyFirstEntry=null
emptyFirstKey=NoSuchElementException
```

The program inserts keys in the order 30, 10, 20, yet iterates in 10, 20, 30. This shows that insertion order is not the order used for queries.

`floorEntry(25)` retrieves both key 20 and its value in a single result. If you need both the key and the value, using the entry-returning variant avoids manually combining two reads like `floorKey` followed by `get`, between which another update could occur.

The `observed` object was obtained when the value was `"twenty"`. After the map was updated to `"TWENTY"`, the previously obtained entry still holds the earlier value. It is not a live handle that updates automatically with the map.

`setValue` on this entry is not supported. To update the map, use a map update method with the appropriate condition. Also distinguish between a live mapping and a deep copy: if the value is a mutable object, the entry holds that reference and does not deep-copy its internal data.

### 3.3. Empty Cases and the Two Forms of Reading First/Last

When the map is empty, `firstEntry()` and `lastEntry()` return `null`, whereas `firstKey()` and `lastKey()` throw `NoSuchElementException`. For a set, `first()` and `last()` also require handling the empty case; `pollFirst()` and `pollLast()` return `null` when no element exists.

Do not write "check non-empty then get first key" as if two consecutive calls form a single atomic boundary. Another thread could remove all data between the two calls. Choose an API that directly represents the absence of a result, or handle the exception in line with the design.

In the program above, the `empty` map is not accessed by any other thread, so the empty result is completely stable. In multithreaded code, the result of each read should only be relied upon within the guarantee scope of that single read.

## 4. Range Queries: Are Bounds Inclusive or Exclusive?

### 4.1. Expressing Ranges Explicitly

In ascending numeric order, the notation `[a, b)` means keys greater than or equal to `a` and strictly less than `b`. The two brackets express an important distinction: the left bound is inclusive and the right bound is exclusive.

Calls with boolean flags state this explicitly:

```java
// Illustrative snippet inside a method, not a standalone program.
var window = map.subMap(20, true, 40, false); // [20, 40)
var before = map.headMap(40, false);         // less than 40
var from = map.tailMap(20, true);            // 20 and above
```

`subSet`, `headSet`, and `tailSet` on a set work in the same way.

The shorter forms inherit the semantics of the ordered interfaces:

| Call | Meaning under the current order |
|---|---|
| `subMap(a, b)` or `subSet(a, b)` | Inclusive of a, exclusive of b |
| `headMap(b)` or `headSet(b)` | Exclusive of b |
| `tailMap(a)` or `tailSet(a)` | Inclusive of a |

Do not assume every short form is inclusive or exclusive. When reading business logic involving timestamps, writing the boolean flags explicitly often makes code review easier.

If both bounds are equal, `[a, a)` is empty. A range inclusive of both bounds can contain a key that compares equal to `a` if such a key exists. If the lower bound comes after the upper bound under the active ordering, the range call is invalid.

### 4.2. Returned Ranges Are Views Backed by the Original Data

A view is a bounded window over the same underlying data, not a copy. Updates within the range via the original map can appear in the view; changes through the view affect the original map. Inserting a key outside the view's bounds throws `IllegalArgumentException`. A view of a `ConcurrentNavigableMap` continues to support concurrent navigation operations. See [ConcurrentNavigableMap range view contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentNavigableMap.html#subMap(K,boolean,K,boolean)).

File `RangeViewsDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;

public class RangeViewsDemo {
    public static void main(String[] args) {
        var root = new ConcurrentSkipListMap<Integer, String>();
        for (int key : new int[] {10, 20, 30, 40, 50}) {
            root.put(key, "v" + key);
        }

        var window = root.subMap(20, true, 40, false);
        System.out.println("initialWindow=" + window.keySet());
        window.put(25, "v25");
        window.remove(30);
        root.put(35, "v35");
        System.out.println("rootAfterChanges=" + root.keySet());
        System.out.println("liveWindow=" + window.keySet());

        try {
            window.put(40, "outside");
        } catch (IllegalArgumentException ex) {
            System.out.println("outsideWrite=" + ex.getClass().getSimpleName());
        }
        System.out.println("root40=" + root.get(40));
        System.out.println("head40Default=" + root.headMap(40).keySet());
        System.out.println("tail40Default=" + root.tailMap(40).keySet());

        var descending = window.descendingMap();
        System.out.println("descending=" + descending.keySet());
        System.out.println("descendingLower25=" + descending.lowerKey(25));
        System.out.println("descendingHigher25=" + descending.higherKey(25));
        System.out.println("descendingRange=" +
                descending.subMap(35, true, 20, false).keySet());

        window.clear();
        System.out.println("rootAfterWindowClear=" + root.keySet());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 RangeViewsDemo.java
java RangeViewsDemo
```

Stdout:

```text
initialWindow=[20, 30]
rootAfterChanges=[10, 20, 25, 35, 40, 50]
liveWindow=[20, 25, 35]
outsideWrite=IllegalArgumentException
root40=v40
head40Default=[10, 20, 25, 35]
tail40Default=[40, 50]
descending=[35, 25, 20]
descendingLower25=35
descendingHigher25=20
descendingRange=[35, 25]
rootAfterWindowClear=[10, 40, 50]
```

Tracing the steps before reversing:

1. `window` initially contains 20 and 30; 40 is excluded because the right bound is exclusive.
2. Adding 25 via the view adds 25 to the root map.
3. Removing 30 via the view removes 30 from the root map.
4. Adding 35 via the root map makes 35 visible in the view.
5. Inserting 40 via the view is rejected; the value for 40 in the root map remains `v40`.
6. `window.clear()` at the end of the program removes the entries in the range from the root map.

This experiment runs sequentially. It demonstrates the relationship between a view and the backing data without mixing in concurrent mutations from other threads.

### 4.3. Access Through a View Is Scoped, Yet Still Has Real Effects

Passing a submap to another method does not merely pass a list of results. The receiving method can modify any entries permitted by the view. For example, calling `clear` on the view deletes real data within that range.

If the receiver should only read, use an appropriate contract or wrapper that restricts mutations. An unmodifiable wrapper around a view can still reflect changes from the underlying source; it does not automatically become a snapshot.

A view nested inside another view must also respect the outer view's bounds. You cannot use `subMap` on a smaller range to expand back outside those bounds.

Keeping a view in memory also retains a reference to the backing structure. If you only want to keep a short-lived set of results, consider copying the needed data and deciding what consistency level the copy requires.

## 5. Reversing Order Also Reverses Navigation Semantics

`descendingMap()` and `descendingSet()` provide views in reverse order. This is not merely printing the same list from back to front; the comparison relationships of the view are inverted as well.

In `RangeViewsDemo`, the ascending keys of `window` are 20, 25, 35. The descending view iterates 35, 25, 20:

```text
Ascending order:   20 → 25 → 35
Descending order:  35 → 25 → 20

In the descending view:
lowerKey(25)  = 35
higherKey(25) = 20
```

The number 35 is numerically greater than 25, yet it precedes 25 in the descending order. Therefore, it is the result of `lowerKey(25)` on that view.

Similarly, a range on a descending view must be written in descending order:

```java
// Illustrative snippet inside a method, not a standalone program.
var part = descending.subMap(35, true, 20, false);
```

This example produces 35, 25. Writing the two bounds in reverse out of habit from ascending numeric order can cause an invalid-range error.

To read a navigation call accurately:

1. Identify whether it is called on the root map or on a view.
2. Identify the comparator or traversal direction of that view.
3. Interpret "before", "after", and "inclusive bound" according to that exact order.

Reversing twice returns the view to the original order. Mutations through a reversed view still affect the backing data within its bounds.

For these classes, the API documentation notes that ascending traversal is more efficient than descending traversal. If an application uses both directions, choose the primary key order to match the frequent query pattern and measure under realistic load; do not infer a fixed performance ratio from a small example.

## 6. Ordered Sets: Uniqueness Is Determined by the Comparison Rule

### 6.1. When Comparison Returns 0 but equals Returns false

A comparator does more than decide presentation order. In ordered structures, a comparison result of 0 also determines whether two keys or elements occupy the same identity slot in the structure.

Suppose each job has a `priority` and an `id`. Two jobs with the same priority but different IDs are still two distinct jobs. If the comparator looks only at `priority`, the set treats them as equivalent in order and will not keep both.

To obey the general contract of `Set` and `Map`, the ordering must be consistent with `equals` over the domain in use. A comparator that causes two objects that are distinct under `equals` to compare as 0 can produce very confusing behavior. See [Comparator consistency with equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

### 6.2. Program with Set, Views, and Tie-Breaker Keys

File `OrderedSetDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentSkipListSet;

public class OrderedSetDemo {
    record Job(int priority, String id) {}

    public static void main(String[] args) {
        var numbers = new ConcurrentSkipListSet<Integer>(List.of(40, 10, 30, 20));
        System.out.println("numbers=" + numbers);
        System.out.println("lower20=" + numbers.lower(20));
        System.out.println("floor25=" + numbers.floor(25));
        System.out.println("ceiling25=" + numbers.ceiling(25));
        System.out.println("higher20=" + numbers.higher(20));

        var window = numbers.subSet(20, true, 40, false);
        System.out.println("window=" + window);
        window.remove(30);
        System.out.println("afterViewRemove=" + numbers);
        System.out.println("polled=" + numbers.pollFirst());
        System.out.println("remaining=" + numbers);

        Job first = new Job(5, "A");
        Job second = new Job(5, "B");
        var priorityOnly = new ConcurrentSkipListSet<Job>(
                Comparator.comparingInt(Job::priority));
        System.out.println("jobsEqual=" + first.equals(second));
        System.out.println("firstAdded=" + priorityOnly.add(first));
        System.out.println("secondAdded=" + priorityOnly.add(second));
        System.out.println("priorityOnlyContainsB=" + priorityOnly.contains(second));
        System.out.println("priorityOnlySize=" + priorityOnly.size());

        Comparator<Job> fullOrder = Comparator.comparingInt(Job::priority)
                .thenComparing(Job::id);
        var complete = new ConcurrentSkipListSet<Job>(fullOrder);
        complete.add(first);
        complete.add(second);
        System.out.println("fullOrderIds=" +
                complete.stream().map(Job::id).toList());

        var empty = new ConcurrentSkipListSet<Integer>();
        System.out.println("emptyPoll=" + empty.pollFirst());
        try {
            empty.first();
        } catch (java.util.NoSuchElementException ex) {
            System.out.println("emptyFirst=" + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 OrderedSetDemo.java
java OrderedSetDemo
```

Stdout:

```text
numbers=[10, 20, 30, 40]
lower20=10
floor25=20
ceiling25=30
higher20=30
window=[20, 30]
afterViewRemove=[10, 20, 40]
polled=10
remaining=[20, 40]
jobsEqual=false
firstAdded=true
secondAdded=false
priorityOnlyContainsB=true
priorityOnlySize=1
fullOrderIds=[A, B]
emptyPoll=null
emptyFirst=NoSuchElementException
```

The first half shows that the set API parallels the map's key API: neighbor lookup, range view, removal through a view, and polling the first element.

The second half intentionally uses an under-specified comparator:

- `first.equals(second)` is `false`, because the two records have different IDs, A and B.
- The second `add` returns `false`, because the comparator sees only priority 5 on both.
- `contains(second)` returns `true`, even though the element actually stored is job A.
- The set size is only 1.

This is not a race between threads. It stems from the identity model imposed by the comparator.

The `fullOrder` comparator compares priority first and then ID. For this two-field record and the sample data, that rule properly distinguishes both jobs and is consistent with `equals`.

### 6.3. Applying the Same Reasoning to Map

If the map key is `Job` and the comparator compares only `priority`, two keys with the same priority also contend for the same key position in the ordering. Calling `put` with the second key can replace the value of the existing mapping instead of creating an independent mapping.

If the domain wants case-insensitive keys or wants to group multiple representations under a single identity, define the data identity explicitly—for instance, normalize the code before using it as a key. Do not let a comparator meant for display accidentally cause data loss.

Adding a tie-breaker key must also fit the domain model. Blindly appending an arbitrary field just to "avoid losing elements" can make the ordering inconsistent with `equals` in the opposite direction. Identify which fields truly define identity and use a consistent rule.

### 6.4. Avoiding Unstable Comparators

Do not write numeric comparisons by subtracting and casting if the numeric range can overflow. Using `Integer.compare`, `Long.compare`, `Comparator.comparingInt`, or `comparingLong` expresses intent more clearly.

Likewise, do not use "current time", load state, or a mutable priority table to change the order of elements already inside the set. If priority needs to change, establish a workflow to remove and re-insert with the updated data, and define how multiple threads coordinate that workflow.

Structural thread safety does not turn a broken comparator into a valid ordering.

## 7. What Concurrency Guarantees and What the Application Must Still Solve

### 7.1. Safe Iteration During Updates Does Not Mean a Snapshot

The iterators of these structures are weakly consistent. They can continue iterating during concurrent operations and do not use `ConcurrentModificationException` to signal those changes. Updates made during iteration may be reflected, but you must not expect all updates to appear as a single shared snapshot. See [java.util.concurrent traversal rules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#ConcurrentCollections).

There are two separate questions:

- Are the iterated results in key order?
- Do the results all belong to a single point-in-time state of the data?

An iteration can preserve key order while traversing data that is actively changing. The fact that a result list appears sorted does not prove it is a consistent snapshot.

Therefore, do not present a fixed stdout list for an experiment that iterates while freely inserting/removing and claim every run must look identical. If you need deterministic output to verify range logic, stabilize the data or use explicit coordination points as in the sequential examples in this lesson.

### 7.2. Ordered Views Do Not Create Range Transactions

Suppose an application obtains a `subMap`, sums the values, and then clears the range. Meanwhile, another thread can insert, update, or remove entries. There is no basis for treating "sum then clear" as an atomic action.

Multi-entry operations such as `putAll`, `clear`, or `forEach` traversal should not be treated as a single atomic state transition across all entries. Likewise, `size()` and an iteration result taken at another moment do not form a synchronized pair of metrics.

The `ConcurrentSkipListSet` documentation also notes that `size()` is not a constant-time operation and the count may not reflect a stable state under concurrent modification. Do not use a freshly read count as a reservation of capacity for a subsequent operation.

If business requirements demand a report accurate at a single point in time, an additional mechanism is needed: all parties honoring an external lock, publishing data as immutable versions, or using a store with appropriate snapshot/transaction support. Having only the reader lock an object while writers do not participate does not establish that boundary.

### 7.3. Two Individually Correct Calls Still Leave a Gap Between Them

The following illustrative snippet has a flaw when multiple workers claim jobs:

```java
// INCORRECT illustrative snippet, not a standalone program.
Integer key = pending.firstKey();
String value = pending.remove(key);
process(value);
```

After one worker reads the key, another worker may already have taken that entry. The first worker is no longer guaranteed to receive a value, and the empty-map case must also be handled.

If the requirement is truly to retrieve and remove the first entry, use the operation that directly expresses that action: `pollFirstEntry()`. If you only want to read, use `firstEntry()` and accept that the read does not reserve exclusive ownership.

Similarly, to insert only when a key is absent, use `putIfAbsent` rather than combining `containsKey` and `put`. To remove or replace only the exact value observed, consider expected-value variants such as `remove(key, oldValue)` or `replace(key, oldValue, newValue)`.

A conditional update also handles only the condition it is given. It does not automatically verify that the entry just read is still the best candidate across the entire range if other keys are changing concurrently.

### 7.4. Do Not Generalize Callback Invocation Counts Across Classes

For `ConcurrentSkipListMap`, the documentation for `computeIfAbsent`, `computeIfPresent`, and `compute` does not guarantee that the mapping function is executed atomically only once, as is often assumed for all concurrent maps. Under contention, avoid placing side effects that must happen only once inside the computation function. See [ConcurrentSkipListMap.computeIfAbsent contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html#computeIfAbsent(K,java.util.function.Function)).

For example, the fact that the map ends up holding a single result does not prove an external service was called only once to produce it. If loading work needs coordination, design an explicit task lifecycle rather than relying on matching method names across classes.

## 8. Multiple Threads Draining the Leading Entry

### 8.1. Program Using pollFirstEntry

This example preloads 40 entries, then has four threads concurrently retrieve and remove the first entry. During the draining phase, no thread re-inserts or modifies data.

File `ConcurrentDrainDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Map;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentDrainDemo {
    public static void main(String[] args) throws Exception {
        var pending = new ConcurrentSkipListMap<Integer, String>();
        for (int id = 1; id <= 40; id++) {
            pending.put(id, "job-" + id);
        }

        var removedIds = new ConcurrentLinkedQueue<Integer>();
        var start = new CyclicBarrier(4);
        var pool = Executors.newFixedThreadPool(4);
        var futures = new ArrayList<Future<Void>>();

        try {
            for (int i = 0; i < 4; i++) {
                futures.add(pool.submit(() -> {
                    start.await(10, TimeUnit.SECONDS);
                    Map.Entry<Integer, String> entry;
                    while ((entry = pending.pollFirstEntry()) != null) {
                        removedIds.add(entry.getKey());
                    }
                    return null;
                }));
            }
            for (Future<Void> future : futures) {
                future.get(10, TimeUnit.SECONDS);
            }
            var unique = new HashSet<>(removedIds);
            System.out.println("removedCount=" + removedIds.size());
            System.out.println("uniqueCount=" + unique.size());
            System.out.println("remainingCount=" + pending.size());
            System.out.println("coversAllIds=" +
                    (unique.size() == 40 && unique.contains(1) && unique.contains(40)));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ConcurrentDrainDemo.java
java ConcurrentDrainDemo
```

Stdout:

```text
removedCount=40
uniqueCount=40
remainingCount=0
coversAllIds=true
```

`pollFirstEntry()` both returns the result and removes the corresponding mapping. Each thread records the claimed IDs in a concurrent queue so the main thread can verify them after all tasks finish.

The output metrics are chosen to be deterministic for the experiment's invariants:

- 40 entries were received in total.
- All 40 IDs are distinct.
- No entries remain in the map.
- Every possible ID comes from the initially loaded range 1 through 40.

The program does not print "which IDs thread 1 took" because that distribution depends on execution scheduling. Nor does it force each thread to receive an equal share of the work.

### 8.2. Claiming First and Completing First Are Two Different Events

Even when every poll selects the first entry, the order in which processing starts or completes can still differ:

```text
Thread A polls entry 1 → long processing
Thread B polls entry 2 → fast processing → completes first
Thread A completes later
```

If business logic requires strict in-order completion, you need another coordination mechanism or an ordered result-recording step. The data structure governs only the entry-claiming step it manages.

Nor can you infer "exactly-once" external processing from the fact that an entry is removed once. If a thread polls an entry and the process crashes before processing finishes, the map has already lost that entry. If you need recovery, completion acknowledgment, or durability across process restarts, you must design appropriate state tracking and persistence.

### 8.3. Empty at Poll Time Does Not Mean the Work Source Is Finished

In this experiment, no producer adds more entries, so seeing `null` is a valid termination condition for each thread.

If another party can insert work later, `null` only means the current poll received no entry. The loop must have a notification, waiting, or separate termination mechanism. Do not busy-spin in a tight loop just to keep asking the map whether a new element has arrived.

If the primary goal is a priority queue that blocks while waiting for work, consider a queue structure suited to that such as `PriorityBlockingQueue`. It supports blocking takes, though its iterator does not guarantee priority-order traversal and it does not provide the map's range queries. See [PriorityBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html).

## 9. Designing a Time Index with Composite Keys

### 9.1. Why a Timestamp Alone Is Not Enough

If two events share the same timestamp and the map uses only the time as its key, the later write can overwrite the earlier value. A map does not automatically become a multi-value structure for the same key.

You can choose a composite key:

```text
EventKey = (time, sequence)

Compare time first
If time is equal → compare sequence
```

In this example, `time` is milliseconds on a shared simulated timeline; `sequence` is positive and distinguishes events that must be kept at the same timestamp. The positivity rule also allows using 0 as a bound before every event at a given timestamp.

File `EventWindowDemo.java`:

```java
import java.util.Comparator;
import java.util.concurrent.ConcurrentSkipListMap;

public class EventWindowDemo {
    record EventKey(long time, long sequence) {}

    public static void main(String[] args) {
        Comparator<EventKey> order = Comparator.comparingLong(EventKey::time)
                .thenComparingLong(EventKey::sequence);
        var events = new ConcurrentSkipListMap<EventKey, String>(order);

        events.put(new EventKey(900, 1), "before");
        events.put(new EventKey(1000, 2), "A");
        events.put(new EventKey(1000, 3), "B");
        events.put(new EventKey(1500, 4), "C");
        events.put(new EventKey(2000, 5), "at-end");

        // Domain rule: stored sequence numbers are strictly positive.
        EventKey from = new EventKey(1000, 0);
        EventKey to = new EventKey(2000, 0);
        var window = events.subMap(from, true, to, false);

        System.out.println("windowValues=" + window.values());
        var afterLastInGroup = new EventKey(1000, Long.MAX_VALUE);
        System.out.println("lastAtOrBefore1000=" +
                events.floorEntry(afterLastInGroup).getValue());

        events.put(new EventKey(1200, 6), "D");
        System.out.println("liveWindowValues=" + window.values());

        var copy = new ConcurrentSkipListMap<EventKey, String>(window);
        events.put(new EventKey(1300, 7), "E");
        System.out.println("copyValues=" + copy.values());
        System.out.println("rootWindowValues=" + window.values());

        events.headMap(from, false).clear();
        System.out.println("firstRemaining=" + events.firstEntry().getValue());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EventWindowDemo.java
java EventWindowDemo
```

Stdout:

```text
windowValues=[A, B, C]
lastAtOrBefore1000=B
liveWindowValues=[A, B, D, C]
copyValues=[A, B, D, C]
rootWindowValues=[A, B, D, E, C]
firstRemaining=A
```

### 9.2. Interpreting Ranges Across the Full Key

The two bounds are `(1000, 0)` and `(2000, 0)`. Because every stored sequence is positive:

- Every event at time 1000 comes after the left bound, so A and B are included.
- Event C at time 1500 falls inside.
- The event at time 2000 with sequence 5 comes after the right bound and is excluded.
- The range implements the time interval `[1000, 2000)`.

This follows from the established data model. If an application allows negative sequence numbers or uses a different key rule, a bound of 0 is no longer valid. Do not copy a "sentinel bound value" into another domain while dropping the assumption behind it.

To find the last entry no later than 1000, the program uses `(1000, Long.MAX_VALUE)` as the target for `floorEntry`. The result is B, the last element in the time-1000 group by key order. Real applications must handle the case where no matching entry exists before calling `getValue()`; this program knows the preloaded data contains a match.

### 9.3. A Live View and an Independent Copy

`window` is created before D is added at 1200. After the insertion, the view iterates A, B, D, C. It remains connected to the original data.

The `copy` variable is created from `window`, and only afterward does the root map add E. The copy does not contain E, while the root view contains E. In this sequential program, the copy point lies clearly between two statements, making the output easy to compare.

If writers are active while creating a copy, constructing an independent structure does not by itself guarantee an atomic point-in-time snapshot of the source. There are two distinct properties:

- Once created, structural changes to the original map do not automatically propagate into the copy.
- What consistency guarantee does the collection pass have while the source is changing?

Additionally, copying a map still copies the key and value references. Using immutable key records and string values in the example keeps this part simple.

### 9.4. Purging Old Data Requires Rules About Arrival Time

Calling `events.headMap(from, false).clear()` removes keys preceding `(1000, 0)`. In the example data, `before` is removed and the first remaining entry is A.

If a late-arriving event with a timestamp below 1000 is inserted after cleanup, old data can reappear. Clearing a range does not establish a rule forbidding writes into that range.

The application must decide whether late events are accepted, whether the purge cutoff is based on event time or ingestion time, and what checks writers must enforce. Those decisions belong to the storage and event-processing model; the map does not infer them.

### 9.5. Composite Keys Also Affect Pagination

If you use the last result on a page as the cursor for the next page, using the full composite key with an exclusive bound avoids missing or repeating events that share the same timestamp.

That is only an ordered continuation rule. It does not create a snapshot across all pages: new events inserted before a cursor that has already been passed may not appear on later pages, and deleted entries will alter the results.

If pagination over a fixed dataset is required, tie it to a version or a snapshot source. Do not use ascending order to promise a consistency level the system does not provide.

## 10. Choosing a Structure and Reviewing Usage

### 10.1. Choosing by the Question You Need to Answer

| Primary need | Direction to consider |
|---|---|
| Exact-key lookup, no neighbor or range queries needed | A hash-based concurrent map may fit |
| Key, neighbor, and range lookups with concurrent updates | `ConcurrentSkipListMap` |
| Maintaining unique ordered elements with neighbor or range queries | `ConcurrentSkipListSet` |
| Single-threaded or all access already coordinated externally | A concurrent class may not be needed |
| Taking work by priority and waiting when empty | Consider a queue structure with blocking operations |
| Mutating multiple entries as a single transaction | Add application-level or storage-level coordination |

This table does not claim one class is always faster than another. Entry count, comparator cost, read/write ratio, traversal direction, and range size all affect the choice.

### 10.2. Often-Overlooked Costs

A long comparator that reads many fields or allocates temporary objects can make queries expensive despite the structure's good search characteristics. Normalize keys once where appropriate instead of repeating heavy work in every comparison.

Obtaining a view does not mean the entire range has been processed. Reading, aggregating, exporting, or deleting many entries still incurs work proportional to the entries involved. Do not take the O(log n) characteristic of a single basic operation and attribute it to printing all data.

`containsValue` is also not an indexed lookup by value. If the application frequently queries by a field in `V`, evaluate whether to include that field in the key or maintain another index; maintaining multiple indexes introduces its own consistency requirements.

Do not treat a skip list as an indexed positional list. It does not provide an operation like "get the 10,000th element" with array-like cost guarantees. If positional ranking is a core requirement, use a design suited for ranking.

## 11. Practice and Self-Check

### Exercise 1: Choosing Navigation Methods

Given keys 10, 20, 30, 40, find:

1. The closest key before 20, excluding 20 itself.
2. The closest key not less than 25.
3. The closest key not greater than 20.
4. The key after 40.

Explanation guide: use `lowerKey(20)`, `ceilingKey(25)`, `floorKey(20)`, and `higherKey(40)` respectively. The results are 10, 30, 20, and `null`. Then repeat on `descendingMap` by interpreting them under the view's order.

### Exercise 2: Range Bounds and View Effects

Create a map with keys 10, 20, 30, 40, 50 and obtain `subMap(20, true, 40, false)`.

- Why is key 40 not in the result?
- If 25 is added through the view, does the root map change?
- If the root map adds 35 after the view is created, must the view be recreated?
- If `clear` is called through the view, which keys remain?

Assuming no other updates, the remaining keys after adding 25, adding 35, and clearing the view are 10, 40, 50. Explain this using range boundaries and shared backing data, not insertion order.

### Exercise 3: Comparator and Collapsed Entries

A set holds orders; the comparator compares only the order date. Two orders with different IDs share the same date.

Explain why adding the second order can return `false` even though `equals` between the two orders is `false`. Then design an identity and comparator rich enough to keep both while remaining consistent with `equals`.

Do not just append a randomly incrementing field to the comparator. Determine whether that field belongs to object identity and whether it stays stable while the data resides in the structure.

### Exercise 4: Summing Amounts in a Range

One thread iterates a submap to sum amounts; another thread continues updating values and adding entries.

Why might the result still not represent the sum at a single point in time even without a `ConcurrentModificationException`? If the report must be a point-in-time snapshot, what mechanism must all parties participate in?

Explanation guide: iteration safety and multi-entry report consistency are two separate requirements. Coordinated locking, immutable versions, or a transactional source matching the required accuracy is needed.

### Exercise 5: Claiming and Completing Work

Multiple threads use `pollFirstEntry` to claim jobs. A small job claimed later finishes before a large job claimed earlier.

Does this contradict the map's ordering? If the process stops after removing an entry but before finishing processing, does the data automatically return to the map?

Explanation guide: claim order, completion order, and recoverability are three distinct concerns. An atomic poll-and-remove operation does not by itself provide completion ordering or workflow durability.

### Questions to Answer in Real Code

1. Which key or element does the ordering apply to?
2. Is the comparator consistent, stable, and compatible with `equals`?
3. Are the left and right bounds inclusive or exclusive?
4. Is the navigation call invoked on the ascending map or on a reversed view?
5. Is the result a live view, an observed entry, or an independent copy?
6. Is a single shared snapshot needed across multiple entries or multiple pages?
7. Is there any "read-then-write" sequence that should be replaced by a conditional operation or a coordination mechanism?
8. Are the contained elements and values themselves thread-safe to share, or is only the outer structure concurrent?

Being able to answer these questions lets you use ordering to express queries accurately while keeping the limits of results clear in a changing system.
