# Concurrent Grouping with `groupingByConcurrent`

## 1. Why Is Concurrent Grouping Needed?

In the **JAVA_STREAM_API** module, we use declarative pipelines with `filter`, `map`, `reduce`, and `collect` to process data. When the input is large, `parallelStream()` or `parallel()` can be considered so multiple elements are processed across multiple threads. However, **collecting results into a single `Map`** raises questions: who manages group update access, can data be lost or duplicated, and to what extent is ordering still guaranteed?

Consider the following order data:

```text
O-1: HN  = 120_000
O-2: HCM =  80_000
O-3: HN  =  30_000
O-4: DN  =  50_000
O-5: HCM =  20_000

Expected:
HN  -> 2 orders, 150_000
HCM -> 2 orders, 100_000
DN  -> 1 order,   50_000
```

`Collectors.groupingBy` can already group data, even on a parallel stream. But for collections requiring a **concurrent map structure**, `Collectors.groupingByConcurrent` provides a **concurrent**, **unordered** collector that returns a `ConcurrentMap`.

That does **not** mean:

- The Stream is guaranteed to run in parallel.
- Every list of values inside the map is thread-safe.
- Key order or element order within each group is guaranteed.
- Every dataset will always run faster than `groupingBy`.

This lesson belongs to the **Concurrent Collection** chapter and focuses on designing the right contract before optimizing. After this lesson, you will be able to:

1. Read the three overloads of `groupingByConcurrent` and the return type `ConcurrentMap<K,D>`.
2. Understand the two characteristics `CONCURRENT` and `UNORDERED` along with the effect of downstream collectors.
3. Distinguish the concurrency of the **outer map** from the safety of **values within each group**.
4. Combine `counting`, `summingLong`, `mapping`, `filtering`, and `summarizingLong` to aggregate per group.
5. Choose `ConcurrentHashMap` or `ConcurrentSkipListMap` when a key ordering policy is needed.
6. Control `null` keys, missing values, overflow, skewed data, and memory risks.
7. Write tests comparing sequential and parallel execution **without relying on ordering not guaranteed by the API**.

The complete examples use **JDK 17 or newer**, because they use `record`, `Stream.toList()`, and `Collectors.filtering` (JDK 9+). `groupingByConcurrent` has been available since Java 8.

## 2. Reading the Three Overloads of `Collectors.groupingByConcurrent`

Abbreviated signatures from `java.util.stream.Collectors`:

```java
// 1. Each key receives a List<T>.
<T, K> Collector<T, ?, ConcurrentMap<K, List<T>>>
groupingByConcurrent(
    Function<? super T, ? extends K> classifier
)

// 2. Each key receives the result D of the downstream collector.
<T, K, A, D> Collector<T, ?, ConcurrentMap<K, D>>
groupingByConcurrent(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
)

// 3. Choose the ConcurrentMap type via mapFactory.
<T, K, A, D, M extends ConcurrentMap<K, D>> Collector<T, ?, M>
groupingByConcurrent(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
```

Required imports: `java.util.concurrent.ConcurrentMap`, `java.util.function.Function`, `java.util.function.Supplier`, `java.util.stream.Collector`.

| Symbol | Meaning |
| --- | --- |
| `T` | Input element type of the stream, e.g., `Order` |
| `K` | Key type produced by `classifier`, e.g., `String` |
| `A` | Intermediate accumulation state of the downstream collector, hidden by the outer collector |
| `D` | Downstream result type for **one group**, e.g., `Long` or `LongSummaryStatistics` |
| `M` | Target map type, must be a subtype of `ConcurrentMap<K,D>` |
| `?` | Internal accumulation type of the overall collector, not exposed publicly |

Example:

```java
ConcurrentMap<String, Long> counts = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.counting()
    ));
```

The compiler infers `T = Order`, `K = String`, `D = Long`, so `collect` returns `ConcurrentMap<String,Long>`. For the single-parameter overload, `D = List<Order>`.

**Return type note:** `groupingByConcurrent` returns results via the `ConcurrentMap` interface. Default overloads typically use `ConcurrentHashMap` in current JDK implementations, but application design should not depend on the concrete class unless using the `mapFactory` overload and specifying it explicitly.

## 3. How Does `groupingBy` Differ from `groupingByConcurrent`?

The same requirement to count orders by region:

```java
Map<String, Long> sequentialStyle = orders.parallelStream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

ConcurrentMap<String, Long> concurrentStyle = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.counting()
    ));
```

They can return **the same value mappings**, yet their execution contracts and results differ.

| Criterion | `groupingBy` | `groupingByConcurrent` |
| --- | --- | --- |
| Default return type | `Map<K,D>` | `ConcurrentMap<K,D>` |
| Concurrent collector? | Not a concurrent collector by default | Has `CONCURRENT` characteristic |
| Unordered collector? | Does not declare `UNORDERED` by default | Has `UNORDERED` characteristic |
| Usable with parallel streams? | Yes | Yes |
| Must use a single shared map in parallel? | No | Framework may use concurrent accumulation per contract |
| Preserves element order in group lists? | Depends on encounter order and downstream | **Does not guarantee** ordering |
| Always faster? | No | No |

In many cases, `groupingBy` running in parallel accumulates into local maps and then **merges maps together**, and key-merging cost can be significant. `groupingByConcurrent` enables concurrent accumulation into a suitable `ConcurrentMap` structure, though threads may contend on the same group.

**Distinction:** `parallelStream()` is the pipeline's execution mode; `CONCURRENT` is **a guarantee of the collector**. A non-concurrent collector can still be used safely on a parallel stream because the framework isolates state. Do not assume that putting `parallel()` forces you to use `groupingByConcurrent`.

## 4. `CONCURRENT`, `UNORDERED`, and Encounter Order

A Collector has characteristics in `Collector.Characteristics`. Two characteristics govern this lesson's design:

### 4.1. `CONCURRENT` Is About Accumulation

`CONCURRENT` informs the framework that accumulator calls can execute concurrently on **the same accumulation container**. It does not state that every object stored in the container is suitable for arbitrary modification by the application from multiple threads.

`groupingByConcurrent` organizes classification and accumulation according to the collector contract. When the downstream is not concurrent (such as `Collectors.toList()`), the collector implementation must coordinate safely during collection; **you must not infer backward that the resulting `ArrayList` is now thread-safe**.

### 4.2. `UNORDERED` Is About Result Ordering

`UNORDERED` indicates that the collector does not require preserving encounter order during accumulation. Consequently, the lists inside groups produced by `groupingByConcurrent(classifier)` **have no ordering guarantee**; the Javadoc states there are no guarantees on the type, mutability, serializability, or thread-safety of the returned lists.

Example:

```java
List<Integer> ids = java.util.stream.IntStream.range(0, 10)
    .boxed().toList();

ConcurrentMap<String, List<Integer>> grouped = ids.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        n -> n % 2 == 0 ? "even" : "odd"
    ));

// Contract: contains all five even numbers and all five odd numbers.
// Do not write a test requiring grouped.get("even") to always be [0, 2, 4, 6, 8].
```

When exact per-group ordering is required, prefer an ordered stream combined with `groupingBy(classifier, downstream)` or sort **after** collection by a deterministic criterion.

### 4.3. The Framework May Choose Different Strategies

For a concurrent collector, the encounter order condition affects accumulation into a shared container. `groupingByConcurrent` declares `UNORDERED` itself, allowing the framework to perform concurrent reduction per the contract. Still, **do not depend on how many times supplier or combiner is called, or group creation order**, as these are not business APIs.

A sequential pipeline using `groupingByConcurrent` still creates a `ConcurrentMap`, which does not mean it ran on multiple threads. Nor does a parallel pipeline guarantee faster speed or that all cores stay busy.

## 5. How Does Data Flow into Concurrent Groups?

To understand, look at a **conceptual** model, not a guarantee of implementation details:

```text
          Parallel Stream<Order>
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
       Order    Order    Order
        │        │        │
      classifier: region
        │        │        │
        └────────┼────────┘
                 ▼
       ConcurrentMap<String, A>
          HN   -> A_HN
          HCM  -> A_HCM
          DN   -> A_DN
                 │
       downstream finisher (if needed)
                 ▼
       ConcurrentMap<String, D>
```

The outer collector ensures the correctness of grouping and interaction with the downstream collector. If the downstream is `counting()`, `D = Long`; if `toList()`, `D = List<Order>`; if `summarizingLong(...)`, `D = LongSummaryStatistics`.

**Three layers to keep separate:**

1. **Input:** is the source safe for parallel traversal? Are the mapper and classifier stateless and non-interfering?
2. **Accumulation:** does the collector coordinate updates properly?
3. **Final result:** the `ConcurrentMap` object permits a set of concurrent operations, while value contents may remain mutable and non-thread-safe.

Do not write `parallelStream().forEach(order -> sharedHashMap.put(...))` and hope Java synchronizes it automatically. Collectors provide a much clearer contract mechanism.

## 6. Complete Java 17 Example: Grouping and Aggregating Orders

The following example defines immutable data and demonstrates three result forms: order lists, order counts, and total amounts by region.

```java
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public final class ConcurrentOrderReport {

    private ConcurrentOrderReport() {}

    public record Order(
        String id,
        String region,
        long amountVnd,
        boolean paid
    ) {
        public Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            if (id.isBlank() || region.isBlank() || amountVnd < 0) {
                throw new IllegalArgumentException("Invalid Order");
            }
        }
    }

    public static List<Order> sample() {
        return List.of(
            new Order("O1", "HN", 120_000L, true),
            new Order("O2", "HCM", 80_000L, true),
            new Order("O3", "HN", 30_000L, true),
            new Order("O4", "DN", 50_000L, false),
            new Order("O5", "HCM", 20_000L, true),
            new Order("O6", "DN", 10_000L, true)
        );
    }

    public static ConcurrentMap<String, List<Order>> allByRegion(
        List<Order> source
    ) {
        return source.parallelStream()
            .collect(Collectors.groupingByConcurrent(Order::region));
    }

    public static ConcurrentMap<String, Long> countByRegion(
        List<Order> source
    ) {
        return source.parallelStream()
            .collect(Collectors.groupingByConcurrent(
                Order::region,
                Collectors.counting()
            ));
    }

    public static ConcurrentMap<String, Long> paidAmountByRegion(
        List<Order> source
    ) {
        return source.parallelStream()
            .filter(Order::paid)
            .collect(Collectors.groupingByConcurrent(
                Order::region,
                Collectors.summingLong(Order::amountVnd)
            ));
    }

    public static void main(String[] args) {
        var orders = sample();

        var groups = allByRegion(orders);
        System.out.println(groups.get("HN").size()); // 2
        System.out.println(groups.get("DN").size()); // 2

        var counts = countByRegion(orders);
        System.out.println(counts.get("HN"));  // 2
        System.out.println(counts.get("HCM")); // 2
        System.out.println(counts.get("DN"));  // 2

        var totals = paidAmountByRegion(orders);
        System.out.println(totals.get("HN"));  // 150000
        System.out.println(totals.get("HCM")); // 100000
        System.out.println(totals.get("DN"));  // 10000
    }
}
```

**Explanation:**

- `allByRegion` returns `ConcurrentMap<String,List<Order>>`. Every order appears exactly once in the appropriate group, but **the position of orders inside the list is not guaranteed**.
- `countByRegion` uses `Collectors.counting` as downstream, storing only the count per group.
- `paidAmountByRegion` filters by payment status **before** grouping, so a region only gets a key if it has at least one paid order. With the sample data, all three regions retain keys.
- Integer `long` VND is used for the aggregation lesson; `summingLong` does not automatically detect overflow.
- `record Order` protects immutable fields, yet if the source is a collection undergoing structural modification during traversal, non-interference must still be ensured.

Results are printed by looking up keys, **not by relying on map iteration order**. A `ConcurrentMap` has no requirement to preserve insertion order like `LinkedHashMap`.

## 7. Safety of the `List`s Inside Groups

The single-parameter overload signature is:

```java
Collector<Order, ?, ConcurrentMap<String, List<Order>>>
```

This does **not** mean `List<Order>` is a `CopyOnWriteArrayList`, `synchronizedList`, or a list safe for the caller to write to concurrently at will.

During `collect`, the framework and collector are responsible for proper accumulation. **After the terminal operation returns**, `ConcurrentMap` manages map operations, yet if multiple threads concurrently call `get("HN").add(order)` on the same regular list, they can cause races or corrupt data.

Counterexample:

```java
ConcurrentMap<String, List<ConcurrentOrderReport.Order>> result =
    ConcurrentOrderReport.allByRegion(
        ConcurrentOrderReport.sample()
    );

// Do not treat the following as thread-safe just because result is a ConcurrentMap:
// result.get("HN").add(newOrder); // multiple threads modifying one List concurrently.
```

To handle this properly:

- If you only need to **read** the groups after `collect` finishes and nobody mutates the lists, read-only processing is fine.
- If you need an **immutable snapshot**, copy the lists and map after collection has completed.
- If **multiple threads must modify the same value** after collection, design a dedicated structure/synchronization for the value rather than relying on `groupingByConcurrent` by default.
- If you only need counts or totals, use `counting`/`summingLong` instead of retaining every `Order` in a list, reducing mutation risk and memory pressure.

The Javadoc of `groupingByConcurrent(classifier)` explicitly states there is no guarantee regarding the **thread-safety of the returned `List`s**; that sentence matters more than the word “Concurrent” in the method name.

## 8. Downstream Collectors: `counting`, `summingLong`, and `summarizingLong`

### 8.1. Counting Elements in Each Group

```java
ConcurrentMap<String, Long> counts =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.counting()
        ));

System.out.println(counts.get("HN")); // 2
```

`counting()` returns `Long` for each group. When only counts are needed, avoid building `List<Order>` just to call `size()` afterward, especially on large datasets.

### 8.2. Summing `long` Values by Group

```java
ConcurrentMap<String, Long> totals =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.summingLong(
                ConcurrentOrderReport.Order::amountVnd
            )
        ));

System.out.println(totals.get("DN")); // 60000 (includes unpaid orders)
```

If you only want paid orders, add `filter(Order::paid)` before grouping or use a downstream `filtering`, noting that **the two approaches produce different key sets** when a group has no matching elements.

### 8.3. Full Summary Statistics with `summarizingLong`

```java
import java.util.LongSummaryStatistics;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, LongSummaryStatistics> stats =
    ConcurrentOrderReport.sample().parallelStream()
        .filter(ConcurrentOrderReport.Order::paid)
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.summarizingLong(
                ConcurrentOrderReport.Order::amountVnd
            )
        ));

LongSummaryStatistics hn = stats.get("HN");
System.out.println(hn.getCount());   // 2
System.out.println(hn.getSum());     // 150000
System.out.println(hn.getMin());     // 30000
System.out.println(hn.getMax());     // 120000
System.out.println(hn.getAverage()); // 75000.0
```

`LongSummaryStatistics` has `accept` and `combine`, so it is **mutable**. Just like `List`, the fact that it was created by concurrent grouping **does not mean the caller can safely mutate the same instance from multiple threads**.

With an empty source, the result map is empty: no groups exist to produce statistics. For a group formed before downstream `filtering` that has no counted elements, its statistics have `count == 0`; `getMin/getMax` in that case are sentinel values rather than real figures.

## 9. `mapping`, `filtering`, and Multi-Level Collectors

`groupingByConcurrent` accepts a downstream collector, allowing transformations and aggregations to be written **directly inside each group**.

### 9.1. Collecting Only Order IDs by Region

```java
ConcurrentMap<String, List<String>> idsByRegion =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.mapping(
                ConcurrentOrderReport.Order::id,
                Collectors.toList()
            )
        ));

// Groups contain all IDs; do not assert that the List has a fixed order.
System.out.println(idsByRegion.get("HN").size()); // 2
```

Here, the outer collector receives `Order` and determines `String region`; the downstream `mapping` converts each `Order` into `String id` before `toList` accumulates it.

### 9.2. Filtering Before Grouping: Groups Can Disappear

```java
var onlyPaid = ConcurrentOrderReport.sample().parallelStream()
    .filter(ConcurrentOrderReport.Order::paid)
    .collect(Collectors.groupingByConcurrent(
        ConcurrentOrderReport.Order::region,
        Collectors.counting()
    ));
```

If you add a region that only has unpaid orders, that region **will have no key** in `onlyPaid`.

### 9.3. `Collectors.filtering` Inside Groups: Empty Groups Still Appear

`Collectors.filtering` (Java 9+) takes a predicate and a downstream collector:

```java
var countsIncludingZero = ConcurrentOrderReport.sample()
    .parallelStream()
    .collect(Collectors.groupingByConcurrent(
        ConcurrentOrderReport.Order::region,
        Collectors.filtering(
            ConcurrentOrderReport.Order::paid,
            Collectors.counting()
        )
    ));

System.out.println(countsIncludingZero.get("DN")); // 1
```

If DN only had unpaid orders, `countsIncludingZero` would still contain `"DN" -> 0L` because the outer collector observed the DN key, while downstream filtering excluded non-matching orders. Thus, downstream filtering is useful for reports that must retain groups **present in the source** even when their valid count is 0.

**Limitation:** if a region does not exist in the source at all, `groupingByConcurrent` does not automatically create that key; to display the full set of configured regions, fill in missing entries after collection.

### 9.4. Using `collectingAndThen` to Return Immutable Results

`collectingAndThen` wraps a downstream collector and runs a finisher on each group's result. Example returning a sorted and unmodifiable list of IDs:

```java
ConcurrentMap<String, List<String>> sortedIdsByRegion =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.collectingAndThen(
                Collectors.mapping(
                    ConcurrentOrderReport.Order::id,
                    Collectors.toList()
                ),
                ids -> ids.stream().sorted().toList()
            )
        ));

System.out.println(sortedIdsByRegion.get("HN")); // [O1, O3]
// sortedIdsByRegion.get("HN").add("O7"); // UnsupportedOperationException
```

Thanks to `sorted()`, the order of **IDs within a group** is explicitly defined regardless of parallel execution schedule. `Stream.toList()` creates an unmodifiable list in JDK 16+. The outer map remains a mutable `ConcurrentMap`; protect it separately if the entire result must be fixed.

## 10. Choosing a Map Type: `ConcurrentHashMap` and `ConcurrentSkipListMap`

The overload with `mapFactory` lets you pick a subtype of `ConcurrentMap<K,D>`:

```java
<T, K, A, D, M extends ConcurrentMap<K, D>> Collector<T, ?, M>
groupingByConcurrent(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
```

### 10.1. `ConcurrentHashMap`: Concurrent Lookup, No Ordering Guarantee

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

ConcurrentHashMap<String, Long> counts =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            ConcurrentHashMap::new,
            Collectors.counting()
        ));
```

`ConcurrentHashMap` supports concurrent map operations, but `keySet` iteration order is neither encounter order nor lexicographical order. Iteration over concurrent collections may reflect modifications during traversal; do not build a “stably ordered” report while data is still being modified.

### 10.2. `ConcurrentSkipListMap`: Concurrent Map with Sorted Keys

If **keys** need to be iterated in the natural order of `String`:

```java
import java.util.List;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

ConcurrentSkipListMap<String, Long> countsBySortedKey =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            ConcurrentSkipListMap::new,
            Collectors.counting()
        ));

System.out.println(List.copyOf(countsBySortedKey.keySet()));
// [DN, HCM, HN]
```

`ConcurrentSkipListMap` uses key order via `Comparable` or `Comparator`, not **the order groups appeared in the source**. Once the map is no longer updated, key iteration order per comparator is a useful contract for display.

If descending order is needed, pass a comparator to the factory:

```java
import java.util.Comparator;
import java.util.concurrent.ConcurrentSkipListMap;

ConcurrentSkipListMap<String, Long> descending =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            () -> new ConcurrentSkipListMap<String, Long>(
                Comparator.reverseOrder()
            ),
            Collectors.counting()
        ));

System.out.println(List.copyOf(descending.keySet()));
// [HN, HCM, DN]
```

### 10.3. Do Not Use `LinkedHashMap::new` in This Overload

`LinkedHashMap` does not implement `ConcurrentMap`, so this expression:

```java
// Does not compile: LinkedHashMap is not a subtype of ConcurrentMap.
// Collectors.groupingByConcurrent(
//     Order::region, LinkedHashMap::new, Collectors.counting()
// )
```

If the true requirement is **first-insertion order in an ordered stream**, use `Collectors.groupingBy(..., LinkedHashMap::new, downstream)` with an appropriate ordering policy, instead of trying to force a concurrent unordered collector to satisfy insertion order.

## 11. `groupingByConcurrent` vs. `toConcurrentMap`

Both factories can produce a `ConcurrentMap`, but they express different business semantics.

### 11.1. `groupingByConcurrent`: One Key, One Group

```java
ConcurrentMap<String, Long> countByRegion =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.counting()
        ));
```

This is a **grouping problem**: use a classifier to determine the key, then a downstream collector aggregates elements in the same group.

### 11.2. `toConcurrentMap`: Mapping Key and Value, Resolving Collisions

```java
ConcurrentMap<String, Long> totalByRegion =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.toConcurrentMap(
            ConcurrentOrderReport.Order::region,
            ConcurrentOrderReport.Order::amountVnd,
            Long::sum
        ));
```

This is a **keyMapper → valueMapper → mergeFunction** problem. If a key has multiple elements, `mergeFunction` decides how to combine the values.

| Requirement | Usually Choose |
| --- | --- |
| Store all records with the same key in a list | `groupingByConcurrent(classifier)` |
| Count/sum/gather statistics by group | `groupingByConcurrent(classifier, downstream)` |
| Turn each record into a key–value pair, merging on duplicate keys | `toConcurrentMap(key, value, merge)` |
| Need a concurrent map with sorted keys | `groupingByConcurrent(classifier, ConcurrentSkipListMap::new, downstream)` |
| Need to preserve encounter order in lists | Consider ordered `groupingBy`, or sort after collection |

Do not use a merge function that depends on shared mutable state or lacks associativity just because a single sample run produced the expected output. For floating-point `double`, addition results may differ in the last digits depending on grouping and merge order.

## 12. Empty Sources, `null` Keys, and Invalid Data

### 12.1. Empty Source Produces an Empty Map

```java
ConcurrentMap<String, Long> empty =
    List.<ConcurrentOrderReport.Order>of().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.counting()
        ));

System.out.println(empty.isEmpty()); // true
```

An empty map differs from a map containing a key with count `0`. In the first case, **no groups were formed**; in the second, a group existed, though downstream filtering may have filtered out all of its elements.

### 12.2. A Classifier Returning `null` Key Is Invalid

`groupingByConcurrent` does not support a classifier producing a `null` key. At the same time, implementations like `ConcurrentHashMap` and `ConcurrentSkipListMap` disallow `null` keys. On standard JDKs, the collector will throw `NullPointerException` if the classifier returns null.

```java
record RawOrder(String region, long amount) {}

List<RawOrder> raw = List.of(
    new RawOrder("HN", 10L),
    new RawOrder(null, 20L)
);

// Do not do this if region can be null:
// raw.parallelStream().collect(
//     Collectors.groupingByConcurrent(RawOrder::region)
// );
```

Choose a policy **before grouping**:

- If null represents invalid data, validate and throw a clear error.
- If the business allows an “unspecified” region, you can use a sentinel key like `"UNKNOWN"` (ensuring no collision with valid region codes).
- If dropping records without a region is allowed, filter them before the collector.

Explicit normalization example:

```java
ConcurrentMap<String, Long> totals = raw.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        row -> row.region() == null ? "UNKNOWN" : row.region(),
        Collectors.summingLong(RawOrder::amount)
    ));

System.out.println(totals.get("UNKNOWN")); // 20
```

For a large system, instead of a sentinel string that risks collision, you can use a dedicated key type representing valid regions and “missing region”.

### 12.3. A `null` Source Element Differs from a Classifier Returning `null`

If the source collection contains a **`null` element**, calling a method reference `Order::region` can throw `NullPointerException` **even before** the classifier creates a key. If the policy allows dropping null elements:

```java
List<ConcurrentOrderReport.Order> nullable =
    new java.util.ArrayList<>();
nullable.add(null);
nullable.addAll(ConcurrentOrderReport.sample());

ConcurrentMap<String, Long> counts = nullable.parallelStream()
    .filter(java.util.Objects::nonNull)
    .collect(Collectors.groupingByConcurrent(
        ConcurrentOrderReport.Order::region,
        Collectors.counting()
    ));
```

`List.of(...)` does not accept `null` elements; the example uses `ArrayList`. If `null` is a data error that must be reported, do **not** silently use `filter(Objects::nonNull)`.

### 12.4. Do Not Assume Values Can Be `null`

`ConcurrentHashMap` and `ConcurrentSkipListMap` reject null values in the map. Standard downstream collectors like `counting()` return a non-null value. If you use a downstream whose finisher returns null, or a mapper not designed for null, execution may fail. Specify missing-data rules explicitly and test that path.

## 13. Ordering, Determinism, and Testing Parallel Results

### 13.1. Key Order Is Not Processing Order

`ConcurrentHashMap` does not guarantee key iteration order. `ConcurrentSkipListMap` can provide key order via a comparator. Neither changes the fact that **the classifier may run across threads in different orders**.

If a report needs a list of order IDs sorted by `id`, sort the resulting list after collection:

```java
List<String> orderedIds = ConcurrentOrderReport.sample()
    .parallelStream()
    .collect(Collectors.groupingByConcurrent(
        ConcurrentOrderReport.Order::region,
        Collectors.mapping(
            ConcurrentOrderReport.Order::id,
            Collectors.toList()
        )
    ))
    .get("HN")
    .stream()
    .sorted()
    .toList();

System.out.println(orderedIds); // [O1, O3]
```

This is ordering by **ID**, not by input order. If the real goal is input order, preserve encounter order using a suitable collector or carry a **sequence number** from the source and sort by sequence after grouping.

### 13.2. Using `Set` for Comparison Can Lose Duplicate Counts

If a group is allowed to contain multiple records with the same ID, comparing `Set<String>` drops occurrence counts. For full verification, compare **frequencies**, or use unique IDs per record in tests.

```java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

static <T> Map<T, Long> frequency(List<T> values) {
    return values.stream().collect(
        Collectors.groupingBy(
            Function.identity(),
            Collectors.counting()
        )
    );
}
```

### 13.3. `double` Results May Differ in Fractional Digits

With `averagingDouble` or `summingDouble` downstreams, addition and merging order can change rounding error. Do not write tests requiring parallel `double` results to match sequential results bit-for-bit, unless a special numeric contract exists. Use a domain-defined tolerance or a more accurate algorithm.

With `summingLong`, `long` addition can **overflow** without throwing an error automatically. In the revenue example, it is only correct when totals fit within `long`; businesses needing overflow detection can use a checked accumulator or `BigInteger`.

## 14. Performance: Hot Keys and Group Distribution

“Concurrent” describes accumulation capability, not a timing guarantee. Important factors include:

### 14.1. Many Evenly Distributed Keys

If there are many keys and data is distributed relatively evenly, threads can work across different groups. `groupingByConcurrent` can reduce part of the cost of **merging multiple local maps** incurred by non-concurrent collectors.

### 14.2. Hot Keys

If 99% of records share `region = "HN"`, many threads will update the same group. With a non-concurrent downstream like `toList()`, the collector must coordinate updates on the same container. Hot-key contention can reduce or eliminate parallel gains.

```text
Uniform distribution:        One very hot key:
HN  ████                    HN  ███████████████████████
HCM ████                    HCM █
DN  ████                    DN  █
HP  ████                    HP  █
```

You cannot infer the speed of `groupingByConcurrent` from CPU thread count alone. Measure based on **key count, frequency distribution, classifier cost, downstream collector, and source size**.

### 14.3. Small Sources and Cheap Operations

With a few dozen records and a simple mapper, the overhead of splitting work, scheduling, and concurrent coordination can exceed sequential processing time. `stream().collect(groupingBy(...))` is often easier to read and fast enough.

### 14.4. Data-Retaining vs. Aggregating Downstreams

| Downstream | Memory Retained |
| --- | --- |
| `toList()` | Retains every element in each group, total can approach `O(n)` |
| `counting()` | Compact count state per group |
| `summingLong()` | Sum state per group |
| `summarizingLong()` | One count/sum/min/max/average statistics object per group |
| `mapping(..., toSet())` | Retains distinct values, depending on value cardinality |

If you only need counts or revenue, **do not** collect full lists only to call `size`/`sum` later. When the number of keys is very large, even compact states consume memory proportional to the number of groups.

## 15. I/O Sources, Resources, and Mutable Data

`groupingByConcurrent` does not automatically manage stream resource lifecycles. With `Files.lines` or `Files.walk`, close the source using `try-with-resources`, even after the terminal operation finishes:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static ConcurrentMap<String, Long> wordInitials(Path file)
    throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines
            .flatMap(line -> java.util.Arrays.stream(
                line.strip().split("\\s+")
            ))
            .filter(word -> !word.isEmpty())
            .parallel()
            .collect(Collectors.groupingByConcurrent(
                word -> word.substring(0, 1),
                Collectors.counting()
            ));
    }
}
```

`Files.lines` can throw `IOException` on open and `UncheckedIOException` during traversal; do not turn a read error into an empty map and report success. For very large files, a parallel I/O pipeline is not automatically faster: it may be bottlenecked by disk read speed.

**Mutable sources:** avoid modifying a source `ArrayList` while a parallel stream is traversing it. A thread-safe collector does not make the source thread-safe. If you want a snapshot of the data, create `List.copyOf(source)` at a well-defined point (assuming the snapshot is created safely), then collect from the snapshot.

## 16. JUnit 5: Verifying Contents, Groups, and Concurrency

The following tests use the `ConcurrentOrderReport` class from section 6. They do **not** assume map ordering or list ordering within groups:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class ConcurrentOrderReportTest {

    @Test
    void preservesAllElementsAcrossGroups() {
        var source = ConcurrentOrderReport.sample();
        ConcurrentMap<String, List<ConcurrentOrderReport.Order>> grouped =
            ConcurrentOrderReport.allByRegion(source);

        assertEquals(3, grouped.size());
        assertEquals(source.size(),
            grouped.values().stream().mapToInt(List::size).sum());

        var expectedIds = source.stream()
            .map(ConcurrentOrderReport.Order::id)
            .sorted()
            .toList();
        var actualIds = grouped.values().stream()
            .flatMap(List::stream)
            .map(ConcurrentOrderReport.Order::id)
            .sorted()
            .toList();

        assertEquals(expectedIds, actualIds);
    }

    @Test
    void countsAndSumsByKey() {
        var source = ConcurrentOrderReport.sample();
        var counts = ConcurrentOrderReport.countByRegion(source);
        var totals = ConcurrentOrderReport.paidAmountByRegion(source);

        assertEquals(2L, counts.get("HN"));
        assertEquals(2L, counts.get("HCM"));
        assertEquals(2L, counts.get("DN"));

        assertEquals(150_000L, totals.get("HN"));
        assertEquals(100_000L, totals.get("HCM"));
        assertEquals(10_000L, totals.get("DN"));
    }

    @Test
    void emptySourceReturnsEmptyConcurrentMap() {
        var empty = List.<ConcurrentOrderReport.Order>of();
        assertTrue(ConcurrentOrderReport.countByRegion(empty).isEmpty());
        assertTrue(ConcurrentOrderReport.allByRegion(empty).isEmpty());
    }

    @Test
    void sequentialAndParallelGroupingAgreeOnCounts() {
        var input = IntStream.range(0, 50_000)
            .mapToObj(i -> new ConcurrentOrderReport.Order(
                "ID-" + i,
                "R-" + (i % 17),
                i,
                true
            ))
            .toList();

        Map<String, Long> expected = input.stream()
            .collect(Collectors.groupingBy(
                ConcurrentOrderReport.Order::region,
                Collectors.counting()
            ));

        ConcurrentMap<String, Long> actual = input.parallelStream()
            .collect(Collectors.groupingByConcurrent(
                ConcurrentOrderReport.Order::region,
                Collectors.counting()
            ));

        assertEquals(expected, actual);
        assertEquals(50_000L,
            actual.values().stream().mapToLong(Long::longValue).sum());
    }

    @Test
    void sortedConcurrentMapOrdersKeys() {
        ConcurrentSkipListMap<String, Long> actual =
            ConcurrentOrderReport.sample().parallelStream()
                .collect(Collectors.groupingByConcurrent(
                    ConcurrentOrderReport.Order::region,
                    ConcurrentSkipListMap::new,
                    Collectors.counting()
                ));

        assertEquals(List.of("DN", "HCM", "HN"),
            List.copyOf(actual.keySet()));
    }

    @Test
    void classifierReturningNullIsRejected() {
        record RawOrder(String region) {}
        var input = List.of(new RawOrder(null));

        assertThrows(NullPointerException.class, () ->
            input.parallelStream().collect(
                Collectors.groupingByConcurrent(RawOrder::region)
            )
        );
    }

    @Test
    void downstreamFilteringRetainsGroupWithZeroCount() {
        var source = List.of(
            new ConcurrentOrderReport.Order(
                "X", "ONLY-UNPAID", 10L, false
            )
        );

        var grouped = source.parallelStream()
            .collect(Collectors.groupingByConcurrent(
                ConcurrentOrderReport.Order::region,
                Collectors.filtering(
                    ConcurrentOrderReport.Order::paid,
                    Collectors.counting()
                )
            ));

        assertTrue(grouped.containsKey("ONLY-UNPAID"));
        assertEquals(0L, grouped.get("ONLY-UNPAID"));
    }
}
```

The `sequentialAndParallelGroupingAgreeOnCounts` test uses many keys and large data to catch grouping bugs. When comparing records in a `List`, sort IDs or compare frequencies; do **not** assert that child lists follow source order.

Cases worth extending in a real project: sources with duplicate values, skewed data (one very hot key), CPU-intensive mappers, large key sets, `null` inputs, numeric overflow, and `double` precision errors. A performance benchmark should be kept separate from unit tests and measured with warm-up and representative data.

## 17. Common Anti-Patterns

| Anti-Pattern | Risk | Fix |
| --- | --- | --- |
| `parallelStream().forEach(sharedHashMap::put)` | Races, lost updates, or corrupted map structure | Use a contract-compliant collector |
| Assuming `groupingByConcurrent` preserves input order | Child lists are unordered | Use ordered `groupingBy` or sort after collection |
| Calling `result.get(key).add(...)` from multiple threads | Inner lists are not inherently thread-safe | Design dedicated value synchronization or immutable snapshots |
| Using `LinkedHashMap::new` with concurrent overload | Does not implement `ConcurrentMap` | Choose a concurrent map or regular collector |
| Classifier returning `null` | No valid group key | Validate, normalize, or filter per business rules |
| Using `summingLong` for amounts that can overflow | Wrong results due to overflow | Choose exact arithmetic or overflow checks |
| Collecting `List<Order>` just to count | High memory usage, increased group contention | `counting()` |
| Expecting parallel to always be fast | Thread/synchronization overhead can dominate | Measure and check key distribution skew |
| Measuring with a single un-warmed `System.nanoTime()` | Unreliable results | Use a properly designed benchmark |
| Mutating source `ArrayList` during collection | Non-interference is violated | Stabilize/snapshot source beforehand |
| Treating concurrent map as an immutable snapshot | Result remains mutable and can change | Copy after collection, publish contract |
| Assuming `CONCURRENT` means every value is concurrent | Confuses map-level and value-level safety | Clearly distinguish ownership |

## 18. Practice Exercises

### Exercise 1 — Group by Region

From `ConcurrentOrderReport.sample()`, use `groupingByConcurrent(Order::region)` to obtain `ConcurrentMap<String,List<Order>>`. Test that each order appears exactly once and in the right region, without relying on list order.

### Exercise 2 — Count and Sum

Write two pipelines with downstreams `counting()` and `summingLong(Order::amountVnd)`. Compare on sequential and parallel sources. Explain the difference between “grouping” and “merging key–value pairs” in `toConcurrentMap`.

### Exercise 3 — Groups with Zero Values

Add a region `"ONLY-UNPAID"` with only unpaid orders. Compare `stream.filter(Order::paid).collect(groupingByConcurrent(...))` and `collect(groupingByConcurrent(..., filtering(Order::paid, counting())))` regarding the key set and group values.

### Exercise 4 — Sorting Keys

Switch `mapFactory` to `ConcurrentSkipListMap::new` to get ascending keys. Then use a reversed comparator for descending keys. Explain why sorting keys does not make lists within groups follow encounter order.

### Exercise 5 — Immutable Lists per Group

Write downstream `collectingAndThen(mapping(Order::id, toList()), ids -> ids.stream().sorted().toList())`. Verify each list is sorted and elements cannot be added. Is the outer map immutable? State how to create a map-level report snapshot.

### Exercise 6 — Hot Key

Create 100,000 records, 99% with key `"HN"` and 1% split across other groups. Compare `groupingBy` and `groupingByConcurrent` sequentially and in parallel. Measure time using a benchmark with warm-up; explain why a hot group can cause contention.

### Exercise 7 — Invalid Data

Create a record with region equal to `null`. Write a policy to either:

- Fail clearly with an appropriate message, **or**
- Normalize the key to a type/value meaning “unspecified”.

Do not silently drop elements if the report must be complete.

### Exercise 8 — Arithmetic and Memory

Collect `LongSummaryStatistics` by group, comparing `getCount`, `getSum`, and `getAverage`. Explain why a mutable statistics object does not mean thread-safe for arbitrary updates by callers. If totals could exceed `Long.MAX_VALUE`, propose a more accurate solution.

## 19. End-of-Lesson Decision Table

| Question | Choice |
| --- | --- |
| Need a grouped map without requiring child list order? | `groupingByConcurrent(classifier)` |
| Need compact metrics per group? | `groupingByConcurrent(classifier, counting/summing/summarizing)` |
| Need to transform each group's contents? | `groupingByConcurrent(classifier, mapping(...))` |
| Need group keys to exist even when downstream filters all items out? | `groupingByConcurrent(classifier, filtering(...))` |
| Need lists in deterministic order? | Sort by an explicit key after collection, or use appropriate ordered grouping |
| Need a concurrent map with sorted keys? | `ConcurrentSkipListMap` via `mapFactory` |
| Need to preserve source key insertion order? | Consider `groupingBy` with `LinkedHashMap` on an ordered stream |
| Need key/value mappers and a merge function? | `toConcurrentMap` |
| Source has `null` keys? | Do not pass directly to concurrent grouping; validate/normalize |
| Need multiple threads to mutate values after collect? | Design separate value handling and synchronization; do not trust `toList()` to be thread-safe |
| Few groups, one very hot key? | Benchmark because contention may be high |
| Small source or cheap mapper? | Sequential stream/`groupingBy` may be more sensible |
| Resource-backed I/O source? | `try-with-resources` and explicit error policy |
| Totals exceeding `long` range or requiring exact arithmetic? | BigInteger/BigDecimal or checked arithmetic collector |
| Testing concurrency? | Compare maps by values/frequencies, do not enforce ordering outside the contract |

`Collectors.groupingByConcurrent` is a tool for **grouping data by key into a `ConcurrentMap`**, especially when the input can be processed in parallel and preserving encounter order within group lists is not needed. The collector's concurrency lets the framework organize accumulation according to the contract; it does **not** turn every value into a thread-safe structure, fix source data errors, or guarantee better performance. Choose downstreams based on real needs, define ordering policies clearly, test data completeness, and benchmark with realistic key distributions before adopting it in production.
