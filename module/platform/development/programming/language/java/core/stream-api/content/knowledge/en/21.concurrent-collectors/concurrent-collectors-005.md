# Impact of Downstream Collectors on Concurrent Grouping

In the Java Stream API, `Collectors.groupingByConcurrent()` is used to group data into a `ConcurrentMap`. However, **the result map supporting concurrent access** does not mean every accumulation operation inside each group runs in parallel without coordination. Pipeline effectiveness also depends on the **downstream Collector**: the collector that decides how each group's values are stored, accumulated, transformed, and finalized.

This lesson belongs to the **Concurrent Collection** chapter, focusing on how to choose and combine downstream collectors when processing data with parallel streams; thereby identifying synchronization bottlenecks, thread-safety requirements, and trade-offs between correctness and performance.

## 1. What Does `groupingByConcurrent` Do?

Consider the expression:

```java
ConcurrentMap<K, D> result = stream.parallel().collect(
    Collectors.groupingByConcurrent(classifier, downstream)
);
```

- `classifier` computes the key `K` of each element `T`.
- `groupingByConcurrent` manages a map capable of being updated by multiple threads, typically a `ConcurrentHashMap`.
- `downstream` collects elements having **the same key** into a result `D`; for example `List<T>`, `Long`, `Set<T>`, or a nested map.

The word *concurrent* on the outer collector indicates the capability to support concurrent accumulation into a shared result. It does not guarantee that the JVM will use multiple threads on every run, nor does it guarantee that the resulting values `D` are thread-safe objects after collection finishes. To have an opportunity for concurrent execution, the source and pipeline must run in parallel, such as via `parallelStream()`.

Unlike `groupingBy()`, the `groupingByConcurrent()` collector has the `UNORDERED` characteristic: **element order within each group is not guaranteed**, even when the original source has an encounter order.

## 2. How Does the Downstream Affect Accumulation?

Each downstream collector has an *accumulation container* and an `accumulator` function to incorporate elements into that container. `Collector.Characteristics` flags indicate how the accumulation container may be used:

| Downstream Characteristic | Meaning for Concurrent Grouping |
| --- | --- |
| `CONCURRENT` | Allows multiple threads to safely call `accumulator` on **the same accumulation container**. `groupingByConcurrent` can accumulate concurrently into the same group without an outer lock caused by a non-concurrent downstream. |
| Not `CONCURRENT` | The downstream does not guarantee safety when multiple threads update the same container. `groupingByConcurrent` must protect accumulation into each group; in common JDK implementations, this operation is synchronized on the group's container. |
| `UNORDERED` | The downstream does not depend on input order. Regardless of whether the downstream has this characteristic, **the result of `groupingByConcurrent` still does not guarantee encounter order**. |
| `IDENTITY_FINISH` | The accumulation container itself can be used as the result value without conversion in the final step. If the downstream needs a `finisher`, the outer collector must also finalize the values before returning. |

A subtle point: **`groupingByConcurrent()` is still a concurrent collector even when the downstream does not have `CONCURRENT`**. The outer collector is responsible for coordinating safe updates. However, if many elements fall into the same key, updates to that group may be serialized, reducing the benefit of a parallel stream.

The processing flow can be visualized as follows:

```text
Multiple threads reading elements T
          │
          ▼
    classifier(T) → key K
          │
          ▼
ConcurrentMap finds/creates container for K
          │
          ├─ CONCURRENT downstream
          │    └─ Threads may accumulate into the same container
          │
          └─ non-CONCURRENT downstream
               └─ Accumulations into the same container must be coordinated
          │
          ▼
    downstream finisher (if needed)
          │
          ▼
        Map<K, D>
```

Groups with different keys can still be processed concurrently in both cases. Therefore, **the number of distinct keys and the distribution of data across keys** strongly affect performance.

## 3. Comparing Common Downstream Collectors

| Downstream | Value per Group | Downstream `CONCURRENT`? | Practical Consequence |
| --- | --- | --- | --- |
| `toList()` | `List<T>` | No | Can collect in parallel across groups; additions to the same list must be protected. The resulting list is not inherently thread-safe. |
| `toSet()` | `Set<T>` | No | Deduplicates per group; the resulting set is not inherently thread-safe. |
| `counting()` | `Long` | No | Counts elements per group accurately; an overly common key can become a bottleneck. |
| `summingInt(mapper)` | `Integer` | No | Sums values per group; may need coordinated updates per group. |
| `mapping(mapper, toList())` | `List<U>` | No | Transforms elements then collects into a list; `mapping` does not itself add concurrent accumulation capability. |
| `toConcurrentMap(keyMapper, valueMapper, merge)` | `ConcurrentMap<K2, V>` | Yes | Inside each group is a concurrent map; threads can update the shared container, though contention can still occur on subkeys. |
| `collectingAndThen(toList(), finisher)` | Depends on `finisher` | No in this example | Adds a finalization step per group; does not turn `toList()` into a concurrent collector. |

The `CONCURRENT` characteristic must come from **the collector's contract**, and cannot be inferred from the result type name or from using `parallelStream()`. For example, `toSet()` can be `UNORDERED` yet still not `CONCURRENT`.

## 4. Complete Example: One Set of Orders, Three Grouping Approaches

The following example runs on Java 16 or newer (because it uses `record`):

```java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ConcurrentGroupingDemo {
    record Order(String region, String product, int quantity) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("Bac", "A", 2),
            new Order("Nam", "A", 3),
            new Order("Bac", "A", 4),
            new Order("Bac", "B", 1)
        );

        // 1. Group orders by region.
        ConcurrentMap<String, List<Order>> ordersByRegion =
            orders.parallelStream().collect(
                Collectors.groupingByConcurrent(
                    Order::region,
                    Collectors.toList()
                )
            );

        // 2. Count orders in each region.
        ConcurrentMap<String, Long> countByRegion =
            orders.parallelStream().collect(
                Collectors.groupingByConcurrent(
                    Order::region,
                    Collectors.counting()
                )
            );

        // 3. Sum quantities by product within each region.
        ConcurrentMap<String, ConcurrentMap<String, Integer>> quantityByRegion =
            orders.parallelStream().collect(
                Collectors.groupingByConcurrent(
                    Order::region,
                    Collectors.toConcurrentMap(
                        Order::product,
                        Order::quantity,
                        Integer::sum
                    )
                )
            );

        System.out.println(ordersByRegion.get("Bac").size()); // 3
        System.out.println(countByRegion.get("Bac"));         // 3
        System.out.println(countByRegion.get("Nam"));         // 1
        System.out.println(quantityByRegion.get("Bac").get("A")); // 6
        System.out.println(quantityByRegion.get("Bac").get("B")); // 1
    }
}
```

In this example:

1. `toList()` accumulates multiple orders into each region's list. Although `ordersByRegion` is a `ConcurrentMap`, you should not assume `ordersByRegion.get("Bac")` is a `CopyOnWriteArrayList` or a list allowing concurrent updates.
2. `counting()` uses a non-concurrent downstream. The count is still accurate because `groupingByConcurrent` performs accumulation in compliance with the downstream's contract.
3. `toConcurrentMap()` creates a sub-map using `product` as the key. The two `("Bac", "A")` orders are merged via `Integer::sum`, yielding total `6`. This downstream has `CONCURRENT`, so it is capable of concurrently updating the sub-map container.

The order of orders when iterating `ordersByRegion.get("Bac")`, and the order of keys when iterating the resulting maps, must not be treated as a stable order. Therefore, the example only checks sizes and totals by key.

## 5. Advanced Example: Writing a Custom Concurrency-Capable Downstream

`counting()` does not have the `CONCURRENT` characteristic. If the goal is counting a large volume of data with many threads updating the same group, you can consider a downstream based on `LongAdder`:

```java
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<Order, LongAdder, Long> concurrentCounting = Collector.of(
    LongAdder::new,
    (counter, order) -> counter.increment(),
    (left, right) -> {
        left.add(right.sum());
        return left;
    },
    LongAdder::sum,
    Collector.Characteristics.CONCURRENT,
    Collector.Characteristics.UNORDERED
);

var counts = orders.parallelStream().collect(
    Collectors.groupingByConcurrent(Order::region, concurrentCounting)
);
```

This snippet assumes `Order` and `orders` are declared as in the previous example. `LongAdder` supports multiple threads incrementing the counter together; the `finisher` converts the intermediate result into `Long` after collection completes. Therefore, the collector does **not** declare `IDENTITY_FINISH`. This is an option that should be measured before adoption: `LongAdder`, container creation, and the `finisher` also have costs; it is not automatically faster than `counting()` on every dataset.

When writing a custom downstream with `CONCURRENT`, the `accumulator` function **must actually be safe if called concurrently on the same container**. Simply adding the `CONCURRENT` flag to a collector based on `ArrayList`, `HashMap`, or a plain `long` counter can cause lost data or race conditions.

## 6. When Does the Downstream Undermine Parallel Stream Benefits?

Performance depends on key distribution, accumulation cost, and contention level:

- **Very few keys, skewed distribution:** Millions of records sharing one `region` with `counting()` or `toList()` cause many threads to wait to update a single group. More threads may not yield faster execution.
- **Many evenly distributed keys:** Threads mostly update different containers. A non-concurrent downstream can still deliver good speed because inter-group contention is low.
- **Concurrent downstream with hot subkeys:** With `toConcurrentMap(product, quantity, Integer::sum)`, if every order has the same `product`, merging that one key in the sub-map can still become a bottleneck.
- **Expensive `finisher`:** `collectingAndThen(...)` or a collector with a costly finishing step increases total cost, even if the accumulation phase runs in parallel.
- **Small dataset or cheap operations:** The cost of splitting work, coordinating threads, and updating a concurrent map can exceed the benefit of running in parallel.

For example, with `Collectors.mapping(Order::product, Collectors.toSet())`, the mapping operation can run on different threads, yet adding elements into **the same group's set** must still be coordinated because `toSet()` lacks `CONCURRENT`. `mapping()` does not change that fact.

When optimizing, measure on real data and compare at least three options that produce the same required result:

```java
// A. Sequential grouped collection.
orders.stream().collect(
    Collectors.groupingBy(Order::region, Collectors.counting())
);

// B. Parallel stream, groupingBy: combine local maps.
orders.parallelStream().collect(
    Collectors.groupingBy(Order::region, Collectors.counting())
);

// C. Parallel stream, groupingByConcurrent: accumulate into a concurrent map.
orders.parallelStream().collect(
    Collectors.groupingByConcurrent(Order::region, Collectors.counting())
);
```

Option B pays the cost of merging intermediate maps; option C pays the cost of coordinating shared map updates and may contend on groups. No option is inherently fastest by default. In serious benchmarks, use JMH, warm up the JVM, run multiple iterations, keep input data constant, and verify results before comparing times.

## 7. Easy-to-Make Mistakes

**Confusing `ConcurrentMap` with thread-safe values.**

```java
ConcurrentMap<String, List<Order>> byRegion = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(Order::region));

// Unsafe if multiple threads arbitrarily call add() on this same list after collect.
byRegion.get("Bac").add(new Order("Bac", "C", 5));
```

A single `add()` call is not an issue if the program runs sequentially; the problem arises when **multiple threads concurrently mutate the same list**. Safety during `collect()` is the collector's responsibility; it does not turn the returned list into a data structure safe for arbitrary subsequent operations. If read-only state is needed, consider finalizing into unmodifiable lists and preventing other threads from mutating the outer map.

**Relying on order after `sorted()`.**

```java
var grouped = orders.parallelStream()
    .sorted(java.util.Comparator.comparingInt(Order::quantity))
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.toList()
    ));
```

`sorted()` establishes order at the output of the sorting stage, but `groupingByConcurrent` is an `UNORDERED` collector, so it does not guarantee the resulting lists remain sorted by `quantity`. If order within each group is a business requirement, use an approach that preserves encounter order appropriately or explicitly sort the groups **after** collection.

**Failing to define how duplicate subkeys are handled.**

```java
// Error if two Orders in the same region have the same product.
Collectors.groupingByConcurrent(
    Order::region,
    Collectors.toConcurrentMap(Order::product, Order::quantity)
);
```

The `toConcurrentMap(keyMapper, valueMapper)` overload without a merge function throws `IllegalStateException` upon encountering duplicate subkeys. If you want to sum quantities, use the overload with a `mergeFunction`, such as `Integer::sum`.

**Allowing the classifier to return `null`.** `groupingByConcurrent()` does not accept grouping results with `null` keys; normalize missing keys before collection or decide to filter out elements according to business rules.

**Attaching `CONCURRENT` to an unsafe downstream.** This characteristic is a promise about concurrent `accumulator` invocations, not an optimization trick. If accumulation logic has shared state without proper synchronization, results can fail in hard-to-reproduce ways.

## 8. Choosing a Collector in Practice

First ask: what must each group's output be? If you only need to group to read lists, `groupingByConcurrent(classifier, toList())` is a valid choice, provided you do not rely on order and do not update the lists from multiple threads after `collect()` returns. If you need counts, `counting()` is simple and clear; only consider a custom concurrent downstream when measurements show group updates are the bottleneck. If you need sums by a subkey, `toConcurrentMap()` is usually the natural choice, with an associative merge function suitable for unordered processing.

Two further questions determine performance and correctness: **how many keys are actually created?** and **can the downstream safely update the same container?** With few keys, pressure on individual groups usually dominates; with many keys, allocation and data-merging costs may dominate. When results require ordering, use an explicit order-preserving or order-reconstructing strategy instead of inferring it from `parallelStream()`.

### Self-Check

1. Does `groupingByConcurrent(classifier, toList())` allow multiple threads to collect safely? Yes: the outer collector coordinates safely; that **does not** make the returned list thread-safe.
2. Why can `groupingByConcurrent(classifier, counting())` be slow when there is only one key? Multiple threads contend on updating the same non-concurrent counting container.
3. Does replacing `toList()` with `mapping(mapper, toList())` make the downstream concurrent? No; `mapping()` inherits appropriate characteristics from its downstream, and `toList()` does not have `CONCURRENT`.
4. When is `toConcurrentMap()` more useful as a downstream? When each group needs a concurrently updated sub-map, with a business-valid duplicate subkey handler and low enough contention for parallelism to pay off.

Core takeaway: **thread-safety of the outer collector, concurrent accumulation capability of the downstream, and safety of the result values are three separate concerns**. Understanding each layer accurately helps you choose a collection structure that is both correct and suited to real data characteristics.
# Impact of Downstream Collectors on Concurrent Grouping

In the **Java Stream API**, `Collectors.groupingByConcurrent` supports grouping into a `ConcurrentMap` and is designed to participate in parallel collection. However, a `groupingByConcurrent` call often also contains a **downstream collector**, such as `toList`, `counting`, `summingLong`, `mapping`, or a custom-defined collector.

This is an easy point to misunderstand: **an outer map capable of concurrent access does not mean every value object inside it is thread-safe**, and **a downstream collector without the `CONCURRENT` characteristic does not mean `groupingByConcurrent` is wrong or unusable on a parallel stream**. The framework must obey the accumulation contract of the composed collector; how contention at each key is handled can strongly affect performance.

This lesson belongs to the **Concurrent Collection** chapter of the `JAVA_STREAM_API` module. The goal is to read a collector's contract, select an appropriate downstream, distinguish correctness from scalability, and avoid sharing mutable state carelessly during parallel processing.

## 1. Three Layers to Distinguish When Saying “Concurrent”

Suppose we want to categorize events by `type` and store the list of `id`s for each type:

```text
Stream<Event> --parallel--> groupingByConcurrent(Event::type,
                                      mapping(Event::id, toList()))
                                      |
                                      v
                         ConcurrentMap<String, List<String>>
                              /                    \
                        "ERROR"                  "INFO"
                           |                        |
                       List<String>             List<String>
```

There are three **different** questions:

| Layer | Question | What to Understand |
| --- | --- | --- |
| **Stream Source** | Is it processed in parallel? | `parallel()` allows the framework to split the source; does not guarantee elements are processed in order or faster. |
| **Outer Collector** | Does it allow multiple workers to contribute to the same accumulation result? | `groupingByConcurrent` returns a collector with `CONCURRENT` and `UNORDERED` characteristics per the API contract. |
| **Downstream and Result Values** | Is each group's container safe under concurrent updates? | `toList()` is not a concurrent collector; the returned lists are **not guaranteed to be thread-safe** either. |

A `ConcurrentMap<K, List<V>>` only states that **compatible operations on the map structure** are concurrently supported per the `ConcurrentMap` contract. It does not turn the inner `List<V>` into a safe list for multiple threads to arbitrarily call `add`.

Crucially, **while `collect` is running**, the framework must coordinate value updates according to the downstream's characteristics. After `collect` finishes, user code receives the map and values; from then on, mutability and thread safety of each value must be evaluated **separately**.

## 2. Syntax of `groupingByConcurrent`

Three main overloads, with generic types simplified for readability:

```java
groupingByConcurrent(classifier);

groupingByConcurrent(classifier, downstream);

groupingByConcurrent(classifier, mapFactory, downstream);
```

Where:

- `classifier` is a `Function<T, K>` returning the group key for each element.
- `downstream` is another `Collector`, determining **the result type and accumulation method** for each group.
- `mapFactory` is a `Supplier` creating an appropriate `ConcurrentMap`, e.g., `ConcurrentSkipListMap::new`.

The terminal operation result has type `ConcurrentMap<K, D>`, with `D` determined by the downstream. The overload taking only `classifier` is conceptually equivalent to collecting each key's elements into a `List<T>`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

List<String> labels = Arrays.asList("API", "AUTH", "UI", "UPLOAD");

ConcurrentMap<Character, List<String>> groups = labels.parallelStream()
    .collect(Collectors.groupingByConcurrent(s -> s.charAt(0)));

System.out.println(groups.get('A').size()); // 2
System.out.println(groups.get('U').size()); // 2
```

In this example, two groups exist, but **you must not write tests demanding the lists always follow source order**. The collector has the `UNORDERED` characteristic; element order within each group is not guaranteed, especially under parallel execution.

In addition, a classifier returning `null` will be rejected; use immutable keys or keys with stable `equals`/`hashCode`. For mutable source types, you must still follow *non-interference*: do not modify the source from inside a mapper or classifier.

## 3. Comparing `groupingBy` and `groupingByConcurrent`

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

// events is a List<Event>, and Event has a type() method.
Map<String, List<Event>> regular = events.parallelStream()
    .collect(Collectors.groupingBy(Event::type));

ConcurrentMap<String, List<Event>> concurrent = events.parallelStream()
    .collect(Collectors.groupingByConcurrent(Event::type));
```

This snippet is illustrative assuming an `Event` type and `events` variable exist. Both collectors produce the same **logical grouping structure by key**, but they do not share the same ordering contract or combination strategy.

| Criterion | `groupingBy` | `groupingByConcurrent` |
| --- | --- | --- |
| Result | `Map<K, D>` | `ConcurrentMap<K, D>` |
| Outer collector `CONCURRENT` characteristic | No | Yes |
| Outer collector `UNORDERED` characteristic | Not by default | Yes |
| Typical parallel processing | Creates partial accumulation maps then merges | Multiple workers can accumulate into one concurrent map |
| Group encounter order | Can preserve order per downstream contract and ordered source | Must not be expected to preserve encounter order |
| Are `List<T>` values thread-safe? | Not guaranteed | **Also not guaranteed** |
| Always faster? | No | No; depends on key distribution and downstream |

On an ordered source, `groupingBy` combined with downstream `toList` is appropriate when **the relative order of elements within each list is required**. `groupingByConcurrent` prioritizes concurrent accumulation capability, accepting the loss of encounter order guarantees.

With few keys and very many elements sharing a key, contention when updating a group can be high. When keys are diverse, work spreads out more and the concurrent collector has a better chance to be effective. **Benchmark on realistic key distributions**, rather than concluding from source size alone.

## 4. Downstream `toList()`: Non-Concurrent Yet Still Usable

A complete example (Java 8+):

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ConcurrentGroupingExample {
    static final class Event {
        final String type;
        final String id;

        Event(String type, String id) {
            this.type = type;
            this.id = id;
        }
    }

    public static void main(String[] args) {
        List<Event> events = Arrays.asList(
            new Event("ERROR", "E1"),
            new Event("INFO",  "I1"),
            new Event("ERROR", "E2"),
            new Event("WARN",  "W1"),
            new Event("ERROR", "E3")
        );

        ConcurrentMap<String, List<String>> idsByType =
            events.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                    event -> event.type,
                    Collectors.mapping(
                        event -> event.id,
                        Collectors.toList()
                    )
                ));

        System.out.println(idsByType.get("ERROR").size()); // 3
        System.out.println(idsByType.get("INFO").size());  // 1
        System.out.println(idsByType.get("WARN").size());  // 1
    }
}
```

`mapping` is a downstream **adapter**: it converts `Event` to `String` and passes the result to `toList`. `toList` does not have the `CONCURRENT` characteristic, yet **the overall collector produced by `groupingByConcurrent` is still a valid collector for parallel streams**.

Why doesn't a race occur from workers writing to the same `ArrayList`? Because the composed collector implementation **is responsible for coordinating accumulation according to the downstream's characteristics**. When the downstream does not support concurrency on the same container, the implementation can protect updates for the same group, such as via synchronization. The exact internal mechanism is an implementation detail, not something the application should rely on.

However, after `collect` returns:

```java
// DO NOT use a returned List as a shared container
// for multiple threads to arbitrarily add/remove concurrently.
List<String> errorIds = idsByType.get("ERROR");
```

`ConcurrentMap` protects map access operations per its contract; it **does not guarantee** that calling `errorIds.add(...)` concurrently from multiple threads will be safe. If you need to share and update the resulting lists, choose an appropriate container/synchronization mechanism or convert to immutable results.

## 5. The Downstream Determines the Shape and Cost of Each Group

Not every report needs to retain **every element**. Choosing the right downstream can improve scalability more than merely switching from `groupingBy` to `groupingByConcurrent`.

| Downstream | `D` in `ConcurrentMap<K,D>` | Retained Data | Notes |
| --- | --- | --- | --- |
| `toList()` | `List<T>` | All elements | Consumes memory proportional to element count; list is not guaranteed thread-safe. |
| `toSet()` | `Set<T>` | Unique elements | Makes no promise about Set implementation, order, or thread-safety. |
| `counting()` | `Long` | Count | Does not store elements; may face contention on “hot” keys. |
| `summingLong(mapper)` | `Long` | A sum | Sum can overflow `long`; no list needed. |
| `summarizingLong(mapper)` | `LongSummaryStatistics` | Count, sum, min, max, average | Result object is mutable, unsafe for arbitrary concurrent updates. |
| `mapping(mapper, downstream)` | Per inner downstream | Depends on downstream | Transforms each element before accumulation. |
| `filtering(predicate, downstream)` (Java 9+) | Per inner downstream | Only elements accepted into downstream | Keys already seen by the classifier can still exist with empty/0 results. |
| `collectingAndThen(downstream, finisher)` | Per `finisher` | Finalizes object after accumulation | Does not turn a non-concurrent accumulator into a concurrent one. |

To avoid allocating large lists when you only need to count errors:

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = Arrays.asList(
        "ERROR", "INFO", "ERROR", "WARN", "ERROR"
    ).parallelStream()
    .collect(Collectors.groupingByConcurrent(
        type -> type,
        Collectors.counting()
    ));

System.out.println(counts.get("ERROR")); // 3
System.out.println(counts.get("INFO"));  // 1
```

`counting` is a downstream that can be used safely **through `groupingByConcurrent`**, even though it is not a concurrent collector itself. This causes no contract violation; parallel execution may still need coordination when multiple workers accumulate into the same key.

## 6. `summarizingLong`: Multiple Metrics, Yet Mutable Results

If you need both counts and statistics per group, avoid `toList` followed by scanning each group's list multiple times:

```java
import java.util.Arrays;
import java.util.LongSummaryStatistics;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

final class Sale {
    final String category;
    final long amount;

    Sale(String category, long amount) {
        this.category = category;
        this.amount = amount;
    }
}

ConcurrentMap<String, LongSummaryStatistics> stats =
    Arrays.asList(
        new Sale("BOOK", 100L),
        new Sale("TOOL", 300L),
        new Sale("BOOK", 200L)
    ).parallelStream()
    .collect(Collectors.groupingByConcurrent(
        sale -> sale.category,
        Collectors.summarizingLong(sale -> sale.amount)
    ));

LongSummaryStatistics books = stats.get("BOOK");
System.out.println(books.getCount());   // 2
System.out.println(books.getSum());     // 300
System.out.println(books.getMin());     // 100
System.out.println(books.getMax());     // 200
System.out.println(books.getAverage()); // 150.0
```

`LongSummaryStatistics` uses mutable state during accumulation. **The framework handles accumulation in accordance with the downstream's contract**; that does not grant permission for other code to mutate `books` while it is being read. Do not call `books.accept(...)` from multiple threads without independent protection.

Using `long` amounts in the smallest integer unit avoids decimal representation errors, though `getSum()` can still overflow `long`; `getAverage()` returns `double` and may require its own rounding rules. If the business requires immutable results, **do not return mutable statistics objects directly**.

### Finalizing Statistics into an Immutable Value

Java 16+ example using `record` to avoid exposing a mutable accumulator:

```java
import java.util.Arrays;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

record Metrics(long count, long sum, long min, long max) {
    static Metrics from(LongSummaryStatistics s) {
        return new Metrics(s.getCount(), s.getSum(), s.getMin(), s.getMax());
    }
}

Map<String, Metrics> immutableReport =
    Arrays.asList(
        new Sale("BOOK", 100L),
        new Sale("BOOK", 200L),
        new Sale("TOOL", 300L)
    ).parallelStream()
    .collect(Collectors.collectingAndThen(
        Collectors.groupingByConcurrent(
            sale -> sale.category,
            Collectors.collectingAndThen(
                Collectors.summarizingLong(sale -> sale.amount),
                Metrics::from
            )
        ),
        Map::copyOf
    ));

System.out.println(immutableReport.get("BOOK").sum()); // 300
```

This snippet uses the `Sale` type from the previous example. The final result is an **unmodifiable** `Map`, and the `Metrics` records hold only primitives. Initial accumulation may still be mutable; `collectingAndThen` only applies the finisher **after per-part accumulation finishes**, without making the accumulator concurrent.

For empty groups, `LongSummaryStatistics.getMin()`/`getMax()` contain special initial sentinel values. In the `groupingByConcurrent` example, each key only appears because an element was assigned to it; if you add a downstream `filtering`, a group can have count 0, so handle that case before publishing min/max.

## 7. `mapping` and `filtering` Do Not Remove Downstream Constraints

Another misconception is thinking that merely wrapping `toList()` with `mapping()` or `filtering()` automatically makes accumulation concurrent. In reality, these two adapters **forward accumulation** to the downstream, and the resulting collector's characteristics depend on the composed collectors.

Example counting severe events by service (Java 9+):

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

final class Alert {
    final String service;
    final boolean severe;

    Alert(String service, boolean severe) {
        this.service = service;
        this.severe = severe;
    }
}

ConcurrentMap<String, Long> severeCounts =
    Arrays.asList(
        new Alert("API", false),
        new Alert("API", true),
        new Alert("UI", false)
    ).parallelStream()
    .collect(Collectors.groupingByConcurrent(
        alert -> alert.service,
        Collectors.filtering(
            alert -> alert.severe,
            Collectors.counting()
        )
    ));

System.out.println(severeCounts.get("API")); // 1
System.out.println(severeCounts.get("UI"));  // 0
```

`filtering` is placed **after** the classifier: the `UI` group exists because an event for `UI` appeared, even though it had no severe alerts. If you placed `stream.filter(alert -> alert.severe)` **before** `groupingByConcurrent`, the `UI` group would not appear.

Distinguish **result shape** (a Map containing `Long`, `List`, `Statistics`, etc.) from **accumulation characteristics** (`CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH`). `mapping` or `filtering` is often semantically useful, but does not by itself resolve contention on a hot key.

## 8. What Does `Collector.Characteristics` Tell Us?

A Collector has a set of characteristics returned by `characteristics()`:

| Characteristic | Meaning | What Must **Not** Be Inferred |
| --- | --- | --- |
| `CONCURRENT` | Allows the accumulator to be called concurrently from multiple threads on **the same accumulation container**. | Does not guarantee the **final result value** is immutable or has all operations thread-safe. |
| `UNORDERED` | The collection does not guarantee preserving encounter order. | Does not mean inputs are processed randomly or that a specific map's iteration order has no rule. |
| `IDENTITY_FINISH` | The finisher is essentially the identity function; the accumulation container is the result type. | Does not mean the object is immutable. |

Inspecting a few collectors via the API:

```java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, List<String>> listCollector =
    Collectors.toList();

Collector<String, ?, ConcurrentMap<Integer, List<String>>> grouped =
    Collectors.groupingByConcurrent(String::length);

System.out.println(listCollector.characteristics()
    .contains(Collector.Characteristics.CONCURRENT)); // false
System.out.println(grouped.characteristics()
    .contains(Collector.Characteristics.CONCURRENT)); // true
System.out.println(grouped.characteristics()
    .contains(Collector.Characteristics.UNORDERED));  // true
```

**Important:** A Collector with `CONCURRENT` but **without** `UNORDERED` is only permitted to perform *concurrent reduction* on an ordered stream if the stream is already treated as **unordered**. `groupingByConcurrent` is `UNORDERED`, so concurrent accumulation does not have to preserve element encounter order.

Do not attach `CONCURRENT` to a collector whose accumulator uses `ArrayList.add`, `HashMap.put`, or increments a shared `long` variable without concurrency safety. That characteristic is a **contract with the Stream framework**, not a speedup directive.

## 9. Genuinely Concurrent Downstreams: When Are They Needed?

If a huge group has many workers competing to update the same container, a **genuinely concurrent** downstream can allow direct accumulation into the group's container without serializing all updates. However, concurrent data structures also carry their own synchronization/allocation overhead and are **not faster by default**.

Example custom collector into `ConcurrentLinkedQueue` (Java 8+):

```java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.concurrent.ConcurrentMap;

Collector<String, ConcurrentLinkedQueue<String>, ConcurrentLinkedQueue<String>>
    queueCollector = Collector.of(
        ConcurrentLinkedQueue::new,
        ConcurrentLinkedQueue::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        Collector.Characteristics.CONCURRENT,
        Collector.Characteristics.UNORDERED
    );

ConcurrentMap<Integer, ConcurrentLinkedQueue<String>> byLength =
    Stream.of("AB", "CD", "A", "XYZ", "EF")
        .parallel()
        .collect(Collectors.groupingByConcurrent(
            String::length,
            queueCollector
        ));

System.out.println(byLength.get(2).size()); // 3
```

Meaning of this design:

- `supplier` creates **a new queue** for each accumulation container; do not return a single shared queue for all keys.
- `ConcurrentLinkedQueue.add` is designed so multiple threads can safely append elements.
- Combiner merges two queues when the framework needs to combine partial results.
- `CONCURRENT` is declared because **the accumulator on the same queue** supports concurrent updates.
- `UNORDERED` is declared because element order in the queue is not guaranteed to match encounter order in parallel mode.

Note: `Collectors.toCollection(ConcurrentLinkedQueue::new)` **does not automatically become a concurrent collector** just because the created collection class is concurrent. Collector characteristics must be designed and declared per the contract, not inferred merely from the container class.

A custom collector with `CONCURRENT` must be verified for correctness when accumulator and combiner may be called in various valid patterns. Without a measured performance requirement, standard downstreams such as `counting`, `toList`, or `summarizingLong` are usually easier to maintain.

## 10. Using `toConcurrentMap` as a Downstream When Sub-Map Results Are Wanted

Not every group needs a list. Sometimes inside each group, we want to **build a lookup table by a secondary key**; `toConcurrentMap` can fit well:

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

final class Item {
    final String category;
    final String sku;
    final int quantity;

    Item(String category, String sku, int quantity) {
        this.category = category;
        this.sku = sku;
        this.quantity = quantity;
    }
}

ConcurrentMap<String, ConcurrentMap<String, Integer>> inventory =
    Arrays.asList(
        new Item("BOOK", "B1", 2),
        new Item("BOOK", "B1", 3),
        new Item("BOOK", "B2", 1),
        new Item("TOOL", "T1", 4)
    ).parallelStream()
    .collect(Collectors.groupingByConcurrent(
        item -> item.category,
        Collectors.toConcurrentMap(
            item -> item.sku,
            item -> item.quantity,
            Integer::sum
        )
    ));

System.out.println(inventory.get("BOOK").get("B1")); // 5
System.out.println(inventory.get("TOOL").get("T1")); // 4
```

`toConcurrentMap` creates a concurrent, unordered downstream for collecting into a sub-map. When **SKU keys collide**, a merger `Integer::sum` or a business-appropriate rule is required; the two-mapper overload rejects duplicate keys.

The concurrent sub-map supports its corresponding operations safely under concurrency per its contract, yet **does not make the data immutable**. For large financial or inventory datasets, `int` sums can still overflow; use `long` or overflow checks when appropriate.

Do not build nested map structures just because you see the word “concurrent”. If you only need the count per category, `groupingByConcurrent(..., counting())` is simpler and retains less data.

## 11. Key Concentration Determines Scalability

The downstream's effect becomes clear when key distribution changes. Compare two scenarios:

```text
Fairly even distribution:    Heavily skewed distribution:
  A: 25%                      HOT: 99%
  B: 25%                      A: 0.5%
  C: 25%                      B: 0.5%
  D: 25%
```

With a non-concurrent downstream like `toList` or `counting`, updates to the same key must be coordinated to preserve correctness. **The HOT key** becomes a point where contention can arise, forcing workers to wait or reducing useful parallelism. Adding `parallel()` does not eliminate that logical bottleneck.

When the downstream is genuinely concurrent, some updates can proceed concurrently on the same container; however, concurrent structures typically use atomics, striping, or internal coordination. That still carries cost, especially when there are only a few elements.

| Factor | Impact to Measure |
| --- | --- |
| Number of keys | Many independent keys can distribute updates better. |
| Distribution skew | One very hot key can cause contention on that group. |
| `toList` downstream | Retains all elements, consumes memory, and requires per-group accumulation coordination. |
| `counting` downstream | Retains little data, yet can still contend on a hot group. |
| Concurrent downstream | Can help reduce bottlenecks, though concurrent structures also have overhead. |
| Mapper/classifier cost | If computation is heavy, synchronization overhead is a smaller fraction; if very cheap, overhead stands out easily. |
| Source Spliterator | Poorly splittable sources limit parallel gains even with an optimal collector. |
| Ordered vs unordered | `groupingByConcurrent` drops the obligation to preserve encounter order, which can help if business rules allow it. |

You should not conclude that `groupingByConcurrent` is always better than `groupingBy`. With small datasets or very few groups, splitting the source and coordinating can make it slower. With ordered data where results must keep per-group ordering, `groupingByConcurrent` can also **violate business requirements**, even if benchmark timings look good.

## 12. Choosing a Factory for the Outer Map: Concurrent Does Not Mean Unsorted Keys

The three-parameter overload lets you choose the `ConcurrentMap` type:

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = Arrays.asList(
        "API", "UI", "API", "DB"
    ).parallelStream()
    .collect(Collectors.groupingByConcurrent(
        service -> service,
        ConcurrentSkipListMap::new,
        Collectors.counting()
    ));

System.out.println(counts.keySet()); // [API, DB, UI]
```

`ConcurrentSkipListMap` iterates keys in sorted order, unlike `ConcurrentHashMap` which guarantees no iteration order. However, **sorted key order** does not mean preserving the encounter order of individual elements within each group. The collector is still `UNORDERED`.

When choosing a comparator for a sorted map, understand key equivalence rules: a comparator returning `0` means the keys are equivalent to the sorted map. Do not use a stateful or inconsistent comparator.

If you only need to display data in key order, you can also **sort after collection** to decouple accumulation logic from display logic.

## 13. Correctness: What to Check and What Not to Check

With source data immutable throughout the pipeline, side-effect-free classifier/mapper, and a valid downstream, a parallel pipeline must produce correct results per the collection contract.

Example checking counts rather than list order:

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

ConcurrentMap<Integer, List<Integer>> grouped =
    IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(Collectors.groupingByConcurrent(
            n -> n % 4
        ));

for (int key = 0; key < 4; key++) {
    List<Integer> group = grouped.get(key);
    if (group == null || group.size() != 2500) {
        throw new AssertionError("Wrong element count for group " + key);
    }
    for (int n : group) {
        if (n % 4 != key) {
            throw new AssertionError("Wrong classifier");
        }
    }
}
```

If you also need to prove **no elements were lost or duplicated**, build a verification set or count value frequencies in each group when the source has unique identifiers. Never check only total size if data could be duplicated while keeping the total unchanged.

**Do not assert:**

- `grouped.get(key)` must have the same order as the original elements of `IntStream.range`.
- Every worker must process an equal number of elements.
- Downstream `toList` must be `ArrayList` or a thread-safe list type.
- `groupingByConcurrent` must necessarily be faster than the sequential version.

For sources containing `null`, classifiers returning `null`, non-associative mergers, keys with mutating `hashCode`, or lambdas depending on shared state, fix those issues **before** evaluating performance.

## 14. Measuring Performance with Clear Key Distributions and Downstreams

To study downstream impact, create a benchmark with independent variables:

1. **Source size:** e.g., 1,000, 100,000, 1,000,000 elements.
2. **Key distribution:** uniform across many keys and heavily skewed toward a single key.
3. **Downstream:** `counting`, `toList`, `summarizingLong`; if genuinely needed, add a custom concurrent collector.
4. **Collection strategy:** `groupingBy` and `groupingByConcurrent`, run sequentially and in parallel per comparison design.
5. **Environment:** core count, JDK, heap size, system load, and how JMH runs the benchmark.

All options must start from **the same data** and compute **the same business metric** when comparing timings. Do not compare `counting` against `toList` and claim collector A is faster than B “on the same problem” when one retains lists and the other only counts; those are two different workloads and two different output contracts.

With JMH, use warm-up, multiple measurement/fork iterations, and proper result consumption. Track `time/op`, throughput, allocation, and GC if needed. **Do not fabricate numbers**: timings vary with key distribution, downstream algorithm, Spliterator, and hardware.

A reasonable reporting table:

| Source | Key Distribution | Downstream | Outer Collector | Time (Measured) | Notes |
| --- | --- | --- | --- | --- | --- |
| 100,000 events | Uniform | `counting` | `groupingBy` | Fill after measuring | Baseline |
| 100,000 events | Uniform | `counting` | `groupingByConcurrent` | Fill after measuring | Compare map merge cost |
| 100,000 events | Heavily skewed | `counting` | `groupingByConcurrent` | Fill after measuring | Watch hot key |
| 100,000 events | Heavily skewed | `toList` | `groupingByConcurrent` | Fill after measuring | Adds element storage cost |

### Why Can a Concurrent Downstream Still Be Slow?

A concurrent queue lets multiple threads append elements to the same group without an exclusive lock from the outer collector. Yet it still has node-management and concurrent-access overhead. When you only need to **count**, creating a queue holding every element is usually a **much more memory-intensive** design than a counter. Optimize for **the exact output data requirement** before optimizing concurrency mechanisms.

## 15. Common Mistakes

| Incorrect Claim or Practice | Issue | Fix |
| --- | --- | --- |
| “`groupingByConcurrent` using `toList` is not thread-safe so it is wrong.” | Confuses **collector safety during collection** with thread-safety of the **resulting list**. | Use standard collectors per contract; do not concurrently mutate result lists outside the pipeline. |
| “If the map is concurrent, every value is concurrent too.” | `ConcurrentMap<K,List<V>>` does not make `List` automatically thread-safe. | Choose immutable, concurrent, or separately synchronized values as needed. |
| “Passing `ConcurrentLinkedQueue` to `toCollection` gives a `CONCURRENT` collector.” | Collector characteristics are not inferred from the container class. | Use a collector properly designed, tested, and declared with `CONCURRENT`. |
| “`groupingByConcurrent` preserves data order within groups.” | An `UNORDERED` collector does not promise encounter order. | Choose `groupingBy` appropriately if order is mandatory, or sort results. |
| “Using `toList` when only a count is needed.” | Allocates many objects and retains unnecessary data. | Use `counting`. |
| “A non-concurrent downstream prevents parallel streams from running.” | The framework can coordinate the accumulator per downstream characteristics. | Still works; measure contention if performance matters. |
| “With many cores, `groupingByConcurrent` is always faster.” | Hot keys, overhead, and poorly splittable sources can negate benefits. | Measure on realistic key distributions; compare with sequential and `groupingBy`. |
| “Returned `LongSummaryStatistics` can be updated from multiple threads.” | Mutable object not designed for unsynchronized concurrent updates. | Finalize into an immutable DTO or coordinate separately. |
| “`collectingAndThen` makes the downstream concurrent.” | The finisher only transforms the result; it does not make the accumulator thread-safe. | Inspect downstream and composed collector characteristics. |
| “The classifier can return `null`.” | Concurrent grouping collectors reject null keys. | Validate or use a meaningful sentinel key before grouping. |

## 16. Practice Exercises

**Exercise 1 — Distinguish Three Layers.** Given `groupingByConcurrent(Event::type, mapping(Event::id, toList()))`, identify: (a) which characteristics the outer collector has, (b) whether the downstream is concurrent, (c) whether the resulting lists can be mutated concurrently from multiple threads. Explain why these three questions must not be conflated.

**Exercise 2 — Count Instead of Storing Everything.** From one million service codes, use `parallelStream().collect(groupingByConcurrent(identity(), counting()))` to count by code. Verify the sum of all counts equals the input size. Compare expected memory cost against a `toList` downstream.

**Exercise 3 — Hot Key.** Generate data such that 99% of elements belong to one key and 1% belong to remaining keys. Compare `groupingBy` and `groupingByConcurrent` with downstream `counting` using JMH. Why might the results differ from evenly distributed data?

**Exercise 4 — Immutable Statistics.** Use `groupingByConcurrent(category, summarizingLong(amount))`, then convert each `LongSummaryStatistics` into a record with only primitive fields and seal the map with `Map.copyOf`. Why is using `Map.copyOf` alone while keeping `LongSummaryStatistics` insufficient?

**Exercise 5 — Grouping and Filtering.** From a list of alerts by service, use `groupingByConcurrent(service, filtering(severe, counting()))`. Compare with `stream.filter(severe)` before grouping. For a service that only has non-severe alerts, do the two results differ?

**Exercise 6 — Custom Collector.** Create a `CONCURRENT` collector backed by `ConcurrentLinkedQueue`. Explain the responsibilities of supplier, accumulator, and combiner; why `UNORDERED` is appropriate; and what goes wrong if the supplier always returns **the same shared queue** for all groups.

**Exercise 7 — Concurrent Sub-Map.** Group items by category, then by SKU using downstream `toConcurrentMap` with `Integer::sum`. Test data with duplicate SKUs; what happens if you use the overload without a merge function?

**Remember:** `groupingByConcurrent` provides **concurrent, non-encounter-order-preserving collection** at the grouping layer. The downstream determines **the value shape, how much state is retained, and the potential for per-key contention**. Downstreams like `toList` or `counting` are not concurrent collectors, yet they are still valid inside `groupingByConcurrent` because the framework coordinates accumulation per the contract. Do not confuse that with thread safety of the resulting collections; choose downstreams based on data requirements and benchmark realistic key distributions before drawing performance conclusions.
