# groupingByConcurrent(), toConcurrentMap(), and Concurrent Collector Requirements in Java

When processing data with `parallelStream()`, multiple transformations can execute on different threads. To aggregate data by key or build a `ConcurrentMap`, Java provides two important collector families in `java.util.stream.Collectors`:

- **`groupingByConcurrent()`**: groups elements according to a classifier function (*classifier*), returning a `ConcurrentMap<K,...>`. Can be combined with downstream collectors to count, sum, or build group results.
- **`toConcurrentMap()`**: transforms each element into a **key–value** pair placed into a `ConcurrentMap<K,U>`; allows specifying how to merge when multiple elements produce the same key.

A defining trait of these two families is that they are collectors designed for **concurrent reduction** and declare appropriate `Collector.Characteristics`. However, you must clearly distinguish:

1. **Concurrent collector** refers to *the accumulator being callable concurrently by the framework on the same result container* when conditions permit.
2. **ConcurrentMap** refers to the map's access/update mechanism under its implementation contract; it **does not automatically make objects stored inside the map thread-safe**.
3. **Parallel Stream** describes the pipeline's execution mode; it **does not guarantee** always running faster, does not guarantee thread order, and does not require every collector to have `CONCURRENT`.
4. **`UNORDERED`** allows dropping encounter-order requirements in the result; if business logic needs "the first record" or stable list order, design for it separately.

This lesson uses **Java 17+**, runnable examples with deterministic output, rules for choosing the right collector, and concurrency mistakes to avoid.

## 1. Reviewing Collector<T,A,R> and concurrent reduction

A `Collector<T,A,R>` has three type roles:

- `T`: input Stream element type.
- `A`: intermediate accumulation container/state type.
- `R`: final result type of `collect`.

Core functions:

```java
Supplier<A> supplier()
BiConsumer<A, T> accumulator()
BinaryOperator<A> combiner()
Function<A, R> finisher()
```

These are **illustrative signatures**, not standalone Java code. In practice, `Collector` methods use more detailed wildcard generics. `supplier` creates state, `accumulator` folds an element into state, `combiner` merges states, and `finisher` produces the final result.

With a collector **without `CONCURRENT`**, the Stream framework can still collect in parallel by creating multiple independent accumulators and calling the combiner to merge them. For example, `Collectors.toList()` does not need to be declared concurrent to work properly with `parallelStream()`.

With a collector that has **`CONCURRENT`**, the framework is permitted to let multiple threads **concurrently update the same accumulator** when ordering and collector conditions are met. Therefore, the accumulator must genuinely support concurrency. Do not attach `CONCURRENT` to a collector whose state is an `ArrayList` if the accumulator calls unsynchronized `add` on the same list.

### Three common Characteristics

| Characteristic | Core meaning | Do not misunderstand |
| --- | --- | --- |
| `CONCURRENT` | Accumulator can be called concurrently on the same result container | Does not guarantee multiple threads are always used, nor that nested values are thread-safe |
| `UNORDERED` | Collector does not commit to preserving element encounter order | Does not mean randomly shuffling results each run |
| `IDENTITY_FINISH` | Accumulated state can be used directly as the final result | Does not apply if a finisher must convert to another type |

**Rule on encounter order:** With a concurrent collector on an ordered Stream, a *concurrent reduction using a single shared state* is only applied under permitted conditions, such as the collector being `UNORDERED` or the Stream being marked unordered. Both collector families in this lesson typically have both `CONCURRENT` and `UNORDERED`, so they provide no guarantee of preserving the first element in source List order.

## 2. groupingByConcurrent(): grouping by classifier

Most common form:

```java
ConcurrentMap<K, List<T>> result = source.parallelStream()
        .collect(Collectors.groupingByConcurrent(classifier));
```

This is a **syntax pattern**: `source` must be a collection of type `T`, `classifier` is `Function<? super T, ? extends K>`, and imports for `ConcurrentMap`, `List`, `Collectors` are required.

Example using string length as the key:

```java
ConcurrentMap<Integer, List<String>> byLength =
        List.of("cat", "ox", "dog", "ant")
                .parallelStream()
                .collect(Collectors.groupingByConcurrent(String::length));
```

The result has group **2** containing `"ox"`, and group **3** containing `"cat"`, `"dog"`, `"ant"`. However, **do not rely on the order** of elements inside each group's list when using `groupingByConcurrent()`. If deterministic printing is needed, sort a copy of each list or switch to a collection method with an appropriate encounter-order requirement.

Differences from `Collectors.groupingBy(String::length)`:
- `groupingBy` statically returns `Map<K,List<T>>` and does not declare `CONCURRENT`.
- `groupingByConcurrent` statically returns `ConcurrentMap<K,List<T>>` and declares `CONCURRENT` and `UNORDERED`.
- With parallel processing, `groupingByConcurrent` can avoid merging multiple intermediate maps in some workloads, but **is not guaranteed to be faster**.

### Three main overloads of groupingByConcurrent

```java
Collectors.groupingByConcurrent(classifier)
Collectors.groupingByConcurrent(classifier, downstream)
Collectors.groupingByConcurrent(classifier, mapFactory, downstream)
```

These are **illustrative API calls**. Use `downstream` when a group result other than `List<T>` is needed; use `mapFactory` when you want a specific `ConcurrentMap` implementation, such as `ConcurrentSkipListMap` for key ordering.

The overloads return `ConcurrentMap<K,D>` where `D` depends on the downstream collector. For example, `Collectors.counting()` returns `Long`; `Collectors.summingInt(...)` returns `Integer`; `Collectors.mapping(..., toList())` returns `List<R>`.

## 3. Java 17 program: groupingByConcurrent with stable output

Create file **`ConcurrentGroupingDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ConcurrentGroupingDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "cat", "dog", "ox", "ant", "bee", "cow"
        );

        ConcurrentMap<Integer, List<String>> byLength =
                words.parallelStream()
                        .collect(Collectors.groupingByConcurrent(
                                String::length));

        ConcurrentMap<Integer, Long> counts =
                words.parallelStream()
                        .collect(Collectors.groupingByConcurrent(
                                String::length,
                                Collectors.counting()));

        new TreeMap<>(byLength).forEach((length, group) -> {
            List<String> sorted = new ArrayList<>(group);
            Collections.sort(sorted);
            System.out.println("length" + length + "=" + sorted);
        });
        System.out.println("counts=" + new TreeMap<>(counts));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ConcurrentGroupingDemo.java
java ConcurrentGroupingDemo
```

**Exact stdout:**

```text
length2=[ox]
length3=[ant, bee, cat, cow, dog]
counts={2=1, 3=5}
```

Explanation:
1. Length 2 has only `"ox"`; length 3 has the remaining five words.
2. `groupingByConcurrent` returns a `ConcurrentMap`, but **does not promise map iteration order or element order within each group's list**.
3. The program uses `new TreeMap<>(byLength)` to iterate keys in ascending order, and creates a new `ArrayList` to sort each group before printing. Thus stdout does not depend on worker scheduling.
4. `counting()` is the downstream, so each group has a `Long` instead of a list; `counts` is copied into a `TreeMap` before printing.

**Do not interpret `ConcurrentMap<Integer,List<String>>` as a map whose lists are automatically synchronized.** Some downstreams like `toList()` are not concurrent collectors. The framework may coordinate updates to each group during collection; after returning the result, **the caller is still responsible for thread safety if multiple threads manually modify the same list**.

## 4. Downstream collectors do not need CONCURRENT themselves

A confusing point: `groupingByConcurrent(classifier, Collectors.toList())` returns a collector with the concurrent characteristic, even though `Collectors.toList()` is **not** a concurrent collector in the sense of allowing multiple threads to concurrently call its accumulator on the same `ArrayList`.

Why is it still valid? Because **the outer collector is responsible for organizing and synchronizing updates to downstream state** when the downstream does not declare `CONCURRENT`. In the JDK implementation, updates to group containers can be coordinated separately to prevent multiple workers from modifying a group's list simultaneously.

Therefore, distinguish:

- **Overall concurrent collector:** can allow multiple elements to be classified and collected concurrently per contract.
- **Non-concurrent downstream:** callers must not arbitrarily share a downstream accumulator across threads and mutate it concurrently.
- **Resulting `List<T>` after collect:** not necessarily a thread-safe list; the `ConcurrentMap` contract does not cover synchronization for every nested object inside it.

Example:

```java
ConcurrentMap<String, List<String>> buckets = words.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                word -> word.substring(0, 1),
                Collectors.toList()));
```

This is an illustrative snippet with `words` as a `Collection<String>` containing no empty strings, with `ConcurrentMap`, `List`, `Collectors` imported. Group values can be regular lists. If multiple threads need to add elements **after collection finishes**, choose a suitable data structure and synchronization technique; do not rely on the map being concurrent to assume `buckets.get("a").add(...)` is always safe.

Also do not mutate groups while another task is inspecting them without a synchronization design. Concurrent collections do not automatically provide *transactions* across multi-step operations on nested structures.

## 5. Per-group statistics with downstream collectors

Downstream can be `counting`, `summingInt`, `summarizingInt`, `mapping`, `filtering`, and many other standard collectors:

```java
ConcurrentMap<String, Long> counts = events.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Event::region,
                Collectors.counting()));
```

`events` and `Event` in the snippet are application-provided data/types; `Event::region` is an accessor returning `String`, as shown in the program right below.

In particular, with `IntSummaryStatistics`, you can aggregate count, sum, min, max, and average for each group. If ordered printing is needed, put keys into a `TreeMap` or sort keys before outputting results.

### Java 17 program: downstream summarizingInt

Save as **`ConcurrentGroupStatsDemo.java`**:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ConcurrentGroupStatsDemo {
    record Event(String region, int duration) {}

    public static void main(String[] args) {
        List<Event> events = List.of(
                new Event("N", 2),
                new Event("S", 3),
                new Event("N", 4),
                new Event("S", 5),
                new Event("N", 6)
        );

        ConcurrentMap<String, IntSummaryStatistics> stats =
                events.parallelStream()
                        .collect(Collectors.groupingByConcurrent(
                                Event::region,
                                Collectors.summarizingInt(Event::duration)));

        new TreeMap<>(stats).forEach((region, s) -> {
            System.out.println(region
                    + ": count=" + s.getCount()
                    + ", sum=" + s.getSum()
                    + ", min=" + s.getMin()
                    + ", max=" + s.getMax()
                    + ", avg=" + s.getAverage());
        });
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ConcurrentGroupStatsDemo.java
java ConcurrentGroupStatsDemo
```

**Exact stdout:**

```text
N: count=3, sum=12, min=2, max=6, avg=4.0
S: count=2, sum=8, min=3, max=5, avg=4.0
```

For group N, durations are 2, 4, 6 so count is 3, sum is 12, average is 4.0. Group S has 3 and 5 so count is 2, sum is 8, average is 4.0. `summarizingInt` can be used as a downstream of an overall concurrent collector; the framework is responsible for updating the appropriate group during the collection phase.

**Arithmetic condition:** `IntSummaryStatistics.getSum()` returns `long`, which is convenient for many `int` sums, though `long` still has limits. Do not treat Java statistics as arbitrary-precision arithmetic.

## 6. toConcurrentMap(): mapping elements to key–value pairs

While `groupingByConcurrent` by default collects **multiple elements into a group**, `toConcurrentMap` maps each element to **one value per key**, or merges values when duplicate keys occur.

Key overloads:

```java
Collectors.toConcurrentMap(keyMapper, valueMapper)
Collectors.toConcurrentMap(keyMapper, valueMapper, mergeFunction)
Collectors.toConcurrentMap(
        keyMapper, valueMapper, mergeFunction, mapFactory)
```

These are **illustrative API patterns**; appropriate functions and types are required.

- **`keyMapper`**: computes key `K` for each element `T`.
- **`valueMapper`**: computes value `U` for each element `T`.
- **`mergeFunction`**: handles the case where multiple elements produce the same key `K`.
- **`mapFactory`**: optionally supplies a specific `ConcurrentMap<K,U>`.

Two arguments suffice when keys are guaranteed unique. If duplicate keys exist, the two-argument overload will **throw `IllegalStateException`**; it does not automatically pick the "first" or "last" value.

When duplicate keys are valid, provide a merge function with business meaning. For example, to sum quantities by product SKU:

```java
ConcurrentMap<String, Integer> quantities = sales.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Sale::sku, Sale::quantity, Integer::sum));
```

This is a snippet in an application with corresponding `Sale` and `sales`. `Integer::sum` is associative and commutative for the small `int` values in the example; merge order does not change the result.

### When sorted keys are needed

The four-argument overload allows supplying `ConcurrentSkipListMap::new` as the map factory:

```java
Collectors.toConcurrentMap(
        Sale::sku, Sale::quantity,
        Integer::sum,
        java.util.concurrent.ConcurrentSkipListMap::new)
```

`ConcurrentSkipListMap` orders keys by comparator or natural ordering, suitable when keys must be printed in a deterministic order. **Map key ordering does not solve the merge order of multiple values for the same key**: if the merge function depends on order, parallel results can still be nondeterministic.

## 7. Java 17 program: toConcurrentMap, duplicate keys, and merging

Create file **`ConcurrentMapMergeDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

public class ConcurrentMapMergeDemo {
    record Sale(String sku, int quantity) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 3),
                new Sale("B", 4),
                new Sale("A", 7),
                new Sale("C", 2),
                new Sale("B", 1)
        );

        ConcurrentMap<String, Integer> totals = sales.parallelStream()
                .collect(Collectors.toConcurrentMap(
                        Sale::sku,
                        Sale::quantity,
                        Integer::sum,
                        ConcurrentSkipListMap::new));

        System.out.println("totals=" + totals);

        try {
            sales.parallelStream()
                    .collect(Collectors.toConcurrentMap(
                            Sale::sku, Sale::quantity));
            System.out.println("unexpected");
        } catch (IllegalStateException ex) {
            System.out.println("duplicateKey=IllegalStateException");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ConcurrentMapMergeDemo.java
java ConcurrentMapMergeDemo
```

**Exact stdout:**

```text
totals={A=10, B=5, C=2}
duplicateKey=IllegalStateException
```

Explanation:
1. `Sale("A",3)` and `Sale("A",7)` share key A, and `Integer::sum` merges them to 10. B becomes 5, C becomes 2.
2. `ConcurrentSkipListMap` displays keys A, B, C in natural order, making stdout deterministic.
3. The two-argument overload **has no merge function**. Because data has duplicate keys, `collect` throws `IllegalStateException`. The program catches the exact error type to demonstrate; do not rely on the specific exception message because messages can vary across JDKs.
4. Each `collect` creates a new Stream from `sales`; a Stream already consumed by a terminal operation is not reused.

**Do not swallow duplicate-key errors with an arbitrary merge function** such as `(oldValue, newValue) -> newValue` if business logic needs to log duplicates, check versions, or pick the latest record by timestamp. In a parallel Stream and `UNORDERED` collector, `newValue` in a merge call is not guaranteed to be the element **arriving later in encounter order**.

## 8. Merge functions must be suitable for concurrent aggregation

For parallel combining operations, an essential requirement is **associativity**: changing how merges are grouped must not alter the semantic result.

Example of addition:

```text
(a + b) + c = a + (b + c)
```

Conversely, subtraction is not associative:

```text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
```

The two blocks above are mathematical notation, not Java code. If you use subtraction as a merge function for values sharing a key, the result can change depending on merge order.

With `UNORDERED` collectors, **commutativity** is also a very useful property to ensure results do not depend on update order: `merge(a,b)` and `merge(b,a)` should be equivalent when order has no business meaning.

| Merge function | Usually suitable? | Reason |
| --- | --- | --- |
| `Integer::sum` | Yes, when `int` sum stays within business bounds | Associative and commutative for integer addition |
| `Integer::max` | Yes | Picks max independently of order |
| `Long::sum` | Yes, when not overflowing business bounds | `long` addition |
| `(a,b) -> a-b` | No | Subtraction is not associative |
| `(a,b) -> a` | Careful | "Keep existing value" does not promise the first element in the source List |
| `(a,b) -> b` | Careful | "Keep new value" does not promise the last element in encounter order |
| `(a,b) -> a + "," + b` | Careful | String concatenation depends on order, can produce varying results |

If the requirement is truly **the record with the largest timestamp**, merge by a timestamp comparator, e.g., picking the record with the greater `timestamp`. If two records can tie on timestamp, add a clear tie-breaker rule so the result remains deterministic.

Some merges like `double` addition are affected by rounding errors and grouping; do not demand bit-for-bit identical results across all parallel schedules if the problem is not designed for it.

## 9. Null keys, null values, and classifiers

Concurrent maps generally disallow null keys or null values; for example, `ConcurrentHashMap` and `ConcurrentSkipListMap` **do not support null keys or null values**. Therefore, control the outputs of `keyMapper`, `valueMapper`, and classifiers.

```java
// DANGEROUS PATTERN if sku can be null:
Collectors.toConcurrentMap(Sale::sku, Sale::quantity, Integer::sum)
```

If a `Sale.sku()` is null, you cannot assume the collector will create a null-key entry. With `groupingByConcurrent`, a classifier returning null is also not accepted under standard collector implementation contracts.

Depending on business logic, you can:

- **Filter out invalid records:** `filter(sale -> sale.sku() != null)`, if skipping records is an allowed policy.
- **Substitute a sentinel code:** `sku == null ? "UNKNOWN" : sku`, if you genuinely want to group all nulls into a specific bucket.
- **Fail validation:** handle before aggregating when null is a contract violation.
- **Represent multiple states:** use an enum or explicit record if "unknown SKU" differs from a valid group.

Do not use a merge function to try to handle null keys; the merge function runs **after the mapper has produced the key**, and cannot turn an unsupported key into a valid one.

### Merge function returning null

In `Map.merge`, if the remapping function returns null, the associated entry can be removed. Therefore, do not write a merge function that returns null when the goal is ensuring a key always has a value, unless removal is intentional and contract-verified. If the problem requires strict duplicate-key checking, the two-argument `toConcurrentMap` overload throws an error instead of dropping data.

## 10. When to use groupingByConcurrent vs. toConcurrentMap?

| Goal | Suitable collector | Reason |
| --- | --- | --- |
| Each region has a **list** of orders | `groupingByConcurrent(Order::region)` | One key can correspond to multiple elements |
| Count orders per region | `groupingByConcurrent(Order::region, counting())` | Downstream produces a single count |
| Total quantity per SKU | `toConcurrentMap(Sale::sku, Sale::quantity, Integer::sum)` | Each key merges into one value |
| Map unique IDs to objects | `toConcurrentMap(Entity::id, e -> e)` | Duplicate keys are errors |
| Pick maximum value per key | `toConcurrentMap(keyMapper, valueMapper, maxMerge)` | Merge determines result |
| Multi-level grouping | `groupingByConcurrent(..., downstream)` | Can compose downstreams as needed |
| Need to preserve first-encounter order | Consider `groupingBy` or an explicitly ordered algorithm | Concurrent collectors are usually `UNORDERED` |
| Only need a Boolean check | `anyMatch`, `allMatch`, `noneMatch` | No need to build a Map |

Both return a concurrent map, but their **aggregation goals** differ. With `groupingByConcurrent`, the downstream can produce `List<T>`, `Set<T>`, statistics, or sub-maps. With `toConcurrentMap`, you explicitly define **one value (`U`)** per key and how to merge on collision.

**Do not write `parallelStream().forEach(map::put)` to replace a collector.** `ConcurrentMap.put` may be safe for a single update, but a bare `put` overwrites values on duplicate keys, easily losing information. For accumulation problems, use merge/collectors to express atomic aggregation properly.

## 11. Inspecting Characteristics and finishers

Collectors can declare `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH`. Inspect **the actual characteristics of the collector** rather than guessing from part of an API name.

For example, a `groupingByConcurrent` collector using downstream `toList` can have `IDENTITY_FINISH` if the container result can be used directly as the final result. When adding `collectingAndThen(..., List::copyOf)`, the downstream requires a real finisher, so `IDENTITY_FINISH` must not be declared for the complete collector.

### Java 17 program: Characteristics and read-only results

Create file **`ConcurrentCollectorCharacteristicsDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class ConcurrentCollectorCharacteristicsDemo {
    public static void main(String[] args) {
        Collector<String, ?, ConcurrentMap<Integer, List<String>>> basic =
                Collectors.groupingByConcurrent(String::length);

        Collector<String, ?, ConcurrentMap<Integer, List<String>>> finished =
                Collectors.groupingByConcurrent(
                        String::length,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                List::copyOf));

        System.out.println("concurrent=" + basic.characteristics()
                .contains(Collector.Characteristics.CONCURRENT));
        System.out.println("unordered=" + basic.characteristics()
                .contains(Collector.Characteristics.UNORDERED));
        System.out.println("identityFinish=" + basic.characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("finishedIdentity=" + finished.characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));

        List<String> group = List.of("cat", "ant", "bee")
                .parallelStream()
                .collect(finished)
                .get(3);
        try {
            group.add("new");
            System.out.println("modifiable=true");
        } catch (UnsupportedOperationException ex) {
            System.out.println("modifiable=false");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ConcurrentCollectorCharacteristicsDemo.java
java ConcurrentCollectorCharacteristicsDemo
```

**Exact stdout:**

```text
concurrent=true
unordered=true
identityFinish=true
finishedIdentity=false
modifiable=false
```

`basic` has the Characteristics of a concurrent collector returning regular list results. `finished` uses downstream `collectingAndThen` to turn group lists into unmodifiable `List.copyOf` results, so it lacks `IDENTITY_FINISH`. The program **does not print the order** of elements inside the group directly, because concurrent collectors do not promise encounter order.

**Note:** a structurally unmodifiable `List` result does not make mutable objects inside it immutable. With complex keys and values, you must still design safe concurrent access/writes per the contract of each data type.

## 12. Creating key-ordered maps with ConcurrentSkipListMap

A `ConcurrentMap` does not mean a `SortedMap`. `ConcurrentHashMap` does not promise key order, whereas `ConcurrentSkipListMap` supports a chosen key ordering.

With `groupingByConcurrent`, the `mapFactory` overload can use:

```java
ConcurrentMap<String, List<Order>> grouped =
        orders.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        Order::region,
                        java.util.concurrent.ConcurrentSkipListMap::new,
                        Collectors.toList()));
```

This is an illustrative snippet; `Order::region` and `orders` are defined in the application. When using a key-ordered map factory, **key** iteration is sorted, but elements inside each `List<Order>` of concurrent grouping **still have no encounter-order guarantee**.

With `toConcurrentMap`, the four-argument overload also accepts `ConcurrentSkipListMap::new`. This option is especially useful when generating reports or displaying maps in natural key/code order without sorting a copy at the end.

**Trade-off:** an ordered map can have different overhead than `ConcurrentHashMap`. Do not pick a map factory just because it looks nice in `println` when the application does not actually need key ordering.

## 13. Parallel Stream and result ownership after collect

While terminal `collect` runs, the Stream framework manages accumulators and coordinates work per the collector's contract. After the terminal returns the result:

1. **The returned Map** may be a `ConcurrentMap`, suitable for certain concurrent reads/writes per its implementation contract.
2. **Map values** may be lists, sets, statistics, or domain objects. **Do not assume** they are thread-safe just because the map itself is concurrent.
3. **Multi-step operations** (check-then-update, reading two groups then modifying concurrently) do not automatically become transactional. Use appropriate atomic methods, locks, or immutable designs as required.
4. **Reading while updating** generally follows the collection's specific visibility/consistency contract. Do not infer that iterating over a changing map gives an instantaneous immutable snapshot.
5. **If only an immutable final report is needed**, convert results to immutable structures or appropriate copies and publish them after collection completes.

The example below is an **unsafe pattern** if multiple threads can call it simultaneously:

```java
// Unsafe just because buckets is a ConcurrentMap:
buckets.get("A").add(item);
```

If `buckets.get("A")` is an `ArrayList`, adding from multiple threads can cause races. The solution should be based on data design: use a concurrent queue, use `compute` with an appropriate mechanism, or only allow updates during the framework-managed collection phase.

Do not habitually use `Collections.synchronizedList` to mask an unclear update lifecycle: you need to define ownership, concurrent iteration behavior, multi-step consistency, and performance.

## 14. Performance: concurrent collectors are not the best default choice

Concurrent collectors can be beneficial when:
- The data source is large enough and easily splittable.
- Per-element processing is independent.
- CPU-bound work is heavy enough to offset split/merge overhead.
- Keys/groups are sufficiently distributed to avoid heavy contention on a single bucket.
- Encounter order does not need to be preserved.

They can be less beneficial when:
- The dataset is small or the mapper/classifier is very cheap.
- Most data concentrates on **one key**, causing update contention.
- The downstream collector must synchronize updates into the same group.
- Sorting, finding "the first record", or post-processing large lists is required.
- Accessing blocking I/O, databases, or connection-limited networks.
- Many other threads are also using shared Fork/Join resources.

In many JDKs, parallel Stream runs on a Fork/Join mechanism and may use the common pool. **Do not rely on thread counts or scheduling order as a fixed contract.** To test throughput and contention, use realistic workloads, warm up the JIT, repeat runs, and use benchmarking tools like **JMH**. Measure correctness, memory/GC, and key collision rates; only enable parallelism when there is a measurable benefit.

### Comparing groupingBy vs. groupingByConcurrent

- `groupingBy` may have to merge partial maps in a parallel Stream.
- `groupingByConcurrent` can accumulate concurrently and reduce map-merging work in suitable cases.
- However, `groupingByConcurrent` has an `UNORDERED` contract. If order within each group is required, `groupingBy` with an ordered pipeline or an explicitly ordered algorithm may fit better.
- With very hot keys, downstream synchronization and contention can prevent concurrent grouping from being faster.

**Correctness first, speed second.** Optimizations must not change business semantics without permission, especially picking first/last records by encounter order and order-dependent value merging.

## 15. Common mistakes

1. **Claiming `parallelStream` requires all collectors to be `CONCURRENT`.** False; non-concurrent collectors can still be used via independent accumulators and combiners.
2. **Claiming `ConcurrentMap` makes `List` values thread-safe.** False; the map and its values have separate concurrency contracts.
3. **Claiming `groupingByConcurrent` preserves source List order.** No encounter-order guarantee; the collector is `UNORDERED`.
4. **Printing a `ConcurrentHashMap` directly and testing key order.** Not guaranteed; sort keys or choose an ordered map factory.
5. **Using two-argument `toConcurrentMap` when keys can collide.** Throws `IllegalStateException`; a merge function is needed if duplicates are valid.
6. **Using merge `(old,new) -> new` to pick the last element in the List.** On parallel unordered collectors, update order does not mean encounter order.
7. **Using subtraction or non-associative merge operations.** Can change results depending on parallel scheduling.
8. **Equating associative with commutative.** String concatenation is associative but not commutative; unsuitable if results must be order-independent under concurrent aggregation.
9. **Returning null from a mapper to represent "absent".** Concurrent maps generally forbid nulls; filter, normalize, or fail per contract.
10. **Returning null from a merge function without intending to delete the entry.** Can cause data loss.
11. **Modifying the Stream source inside a classifier or mapper.** Violates non-interference and risks races.
12. **Using global mutable state inside a predicate/classifier.** Can classify inconsistently across threads.
13. **Assuming `groupingByConcurrent` is always faster than `groupingBy`.** Contention, group count, and downstream determine the gain.
14. **Assuming `CONCURRENT` means a new thread per element.** The framework chooses the work-splitting mechanism.
15. **Manually declaring `CONCURRENT` on a custom Collector using an unsynchronized `ArrayList`.** Violates contract and can lose data.
16. **Keeping `IDENTITY_FINISH` when using `collectingAndThen`.** A real finisher cannot be skipped.
17. **Confusing an ordered `mapFactory` with value merge order.** Sorted keys do not guarantee encounter order of elements within a group or record-retention rules.
18. **Holding a `ConcurrentMap` result and assuming all multi-step operations are atomic.** Proper synchronization/transaction mechanisms are needed.
19. **Optimizing without benchmarking.** Concurrent collectors have overhead and do not guarantee speedups.

## 16. One-minute API decision table

| Question | Suggestion |
| --- | --- |
| Need a **list of all elements** per key, no order needed? | `groupingByConcurrent(classifier)` |
| Need **counts** per key? | `groupingByConcurrent(classifier, counting())` |
| Need statistics per key? | `groupingByConcurrent(classifier, summarizingInt(...))` |
| Need a Map from unique keys to values? | `toConcurrentMap(keyMapper, valueMapper)` |
| Duplicate keys valid, need sum/max? | `toConcurrentMap(keyMapper, valueMapper, merge)` |
| Need sorted keys? | `mapFactory` overload with `ConcurrentSkipListMap` |
| Need to preserve **first element in encounter order**? | Consider `groupingBy` or a specific ordered algorithm |
| Only need a result List? | `toList()` or `collect(toCollection(...))` |
| Only need to check if a matching element exists? | `anyMatch(predicate)`, no Map needed |

Before using a concurrent collector, answer three questions: **(1) Is encounter order needed? (2) Can data with the same key be merged by an order-independent operation? (3) Do the downstream and resulting data have appropriate concurrency contracts?** If unsure, do not replace `groupingBy` with `groupingByConcurrent` just because the name contains "Concurrent".

## 17. Self-check questions

**Question 1.** What Map type does `groupingByConcurrent(String::length)` return, and what is each value by default?

**Answer:** The return type is `ConcurrentMap<Integer,List<String>>`; each value is a list of strings with the same length. Element order within each group's list is not guaranteed.

**Question 2.** Why can `groupingByConcurrent(key, counting())` still be a concurrent collector even though `counting()` is not a concurrent collector itself?

Because the outer collector organizes concurrent accumulation and protects the downstream accumulator as needed. You should not infer that downstream state can be mutated freely from arbitrary threads.

**Question 3.** What does `toConcurrentMap(keyMapper,valueMapper)` do if two elements share the same key?

**Answer:** Throws `IllegalStateException` because this overload has no merge function.

**Question 4.** How do you sum `quantity` per `sku` on a parallel Stream?

```java
ConcurrentMap<String, Integer> totals = sales.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Sale::sku, Sale::quantity, Integer::sum));
```

This is a snippet with `Sale` and `sales` from your program. When keys collide, `Integer::sum` merges values into a sum.

**Question 5.** Does `ConcurrentMap` guarantee `map.get("A").add(item)` is safe if the value is an `ArrayList`?

**No.** `ConcurrentMap` protects operations on the map per its contract; it does not automatically make an `ArrayList` value thread-safe.

**Question 6.** With an `UNORDERED` collector, can you use merge `(first,later) -> first` to always pick the first record in the List?

**No.** The merge parameters describe the relationship between an already-stored value and a newly merged value, not encounter order. Select by an explicit data attribute if a deterministic result is needed.

**Question 7.** Why is using `ConcurrentSkipListMap` as `mapFactory` not enough to guarantee the list in each group matches source order?

Because `mapFactory` determines the structure and order of **keys**, while concurrent grouping does not promise encounter order for **elements inside value lists**.

**Question 8.** When can using a concurrent collector be beneficial?

When the workload is large enough, classification is independent, encounter order is not needed, merging is valid, and benchmarks show a real gain. There is no absolute speedup guarantee.

**Question 9.** Are `CONCURRENT` and `IDENTITY_FINISH` the same?

**No.** `CONCURRENT` relates to the ability to update the accumulator concurrently; `IDENTITY_FINISH` relates to using the accumulated state directly as the final result.

**Question 10.** If you want the maximum value per key, but two records tie for the highest score, what must you do?

Define a tie-breaker rule (e.g., ID or secondary timestamp). A merge function without a tie rule can pick different records depending on parallel update order.

**Takeaway:** `groupingByConcurrent()` groups data into **buckets** in a `ConcurrentMap`; `toConcurrentMap()` produces **one value per key** and needs a merge function if keys can collide. Both support concurrent reduction, but **a concurrent collector differs from thread safety of individual values**, and `UNORDERED` does not promise keeping the first element. Design associative merges, handle nulls and duplicates explicitly, and measure performance instead of guessing.