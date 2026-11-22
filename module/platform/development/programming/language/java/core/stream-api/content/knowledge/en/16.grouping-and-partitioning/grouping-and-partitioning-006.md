# Combining `partitioningBy` with a Downstream Collector

In the Java Stream API, `Collectors.partitioningBy(predicate)` partitions data into two groups based on a true/false condition. When you want to do **more than storing a list of elements**—such as counting orders, summing revenue, finding the largest order, or grouping further by region—you use the overload that takes a **downstream collector** (*downstream collector*).

This lesson belongs to the **Grouping and Partitioning** chapter of the **JAVA_STREAM_API** module. The goal is to understand the contract of `partitioningBy(predicate, downstream)` and how to combine it with `counting`, `mapping`, `summingLong`, `summarizingLong`, `filtering`, `groupingBy`, `maxBy`, `collectingAndThen`, and `teeing`. It also explains empty-group results, ordering, parallel execution, and limitations around state, resources, and performance when building `filter`, `map`, `reduce`, and `collect` pipelines.

Examples use Java 17 for `record`. `partitioningBy` and most basic collectors have existed since Java 8; `Collectors.filtering` was added in Java 9, and `Collectors.teeing` in Java 12.

## 1. Scenario: Partitioning Orders by Payment Status

Suppose a system has the following set of orders; amounts are stored in **cents (`long`)** to avoid binary floating-point error when summing small monetary amounts:

```java
import java.util.List;

record Order(String id, String region, long amountCents, boolean paid) {}

List<Order> orders = List.of(
        new Order("O-101", "Bắc", 12_500, true),
        new Order("O-102", "Nam",  5_000, false),
        new Order("O-103", "Bắc",  7_500, true),
        new Order("O-104", "Bắc", 10_000, false),
        new Order("O-105", "Nam",  3_000, true)
);
```

We need to create two groups:

- **`true`**: paid orders (`paid == true`).
- **`false`**: unpaid orders (`paid == false`).

If you only need to keep the lists of orders, use the single-argument overload:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Order>> byPaid = orders.stream()
        .collect(Collectors.partitioningBy(Order::paid));

System.out.println(byPaid.get(true).size());  // 3
System.out.println(byPaid.get(false).size()); // 2
```

However, when you only want counts, storing all `Order` objects in two lists is unnecessary. That is why we use a **downstream collector**.

## 2. Syntax and How to Read `downstream`

The two-argument overload has the conceptual signature:

```java
static <T, D, A> Collector<T, ?, Map<Boolean, D>> partitioningBy(
        Predicate<? super T> predicate,
        Collector<? super T, A, D> downstream
);
```

Where:

| Component | Role |
|---|---|
| `T` | Source element type, e.g., `Order` |
| `predicate` | Classifies each element into key `true` or `false` |
| `downstream` | Defines how elements are aggregated **within each group** |
| `D` | Result type produced by the downstream collector for each group |
| `Map<Boolean, D>` | Final result containing two aggregated values corresponding to the two Boolean keys |

You can read the pipeline as follows:

```text
Stream<Order>
     |
     v
  Order::paid
     |
     +------------> true  ----> downstream ----> D for the true group
     |
     +------------> false ----> downstream ----> D for the false group
                                               |
                                               v
                                          Map<Boolean, D>
```

Counting example:

```java
Map<Boolean, Long> counts = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));

System.out.println(counts.get(true));  // 3
System.out.println(counts.get(false)); // 2
```

`Collectors.counting()` is the downstream collector. It receives the `Order` elements of **each partition** and returns `Long`. Therefore, the overall result is `Map<Boolean, Long>`, not `Map<Boolean, List<Order>>`.

## 3. Important Contract: Both Boolean Keys Are Always Present

A defining characteristic of `partitioningBy` is that the result always contains **both `Boolean.TRUE` and `Boolean.FALSE` keys**, even if one or both partitions receive no elements.

```java
Map<Boolean, Long> allPaid = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));

System.out.println(allPaid.get(true));            // 3
System.out.println(allPaid.get(false));           // 0
System.out.println(allPaid.containsKey(false));   // true
```

A completely empty source still produces **two downstream results for the two empty partitions**:

```java
import java.util.stream.Stream;

Map<Boolean, List<Order>> emptyLists = Stream.<Order>empty()
        .collect(Collectors.partitioningBy(Order::paid));

System.out.println(emptyLists.get(true));  // []
System.out.println(emptyLists.get(false)); // []
```

However, "the downstream result for an empty group" is **not always `null` or an empty list**. It depends on the chosen collector:

| Downstream | Value for an empty partition |
|---|---|
| `toList()` | Empty list |
| `toSet()` | Empty set |
| `counting()` | `0L` |
| `summingLong(...)` | `0L` |
| `averagingLong(...)` | `0.0` |
| `maxBy(...)` | `Optional.empty()` |
| `groupingBy(...)` | Empty map |
| `summarizingLong(...)` | Statistics object with `count == 0` |

For example:

```java
Map<Boolean, Long> none = Stream.<Order>empty()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));

System.out.println(none.get(true));  // 0
System.out.println(none.get(false)); // 0
```

**Note:** Having both keys present does not mean the `Map` has a fixed iteration order. Do not rely on `entrySet()` printing `false` first or `true` first. Also do not assume the concrete implementation class, mutability, or thread-safety of the resulting `Map`.

## 4. Counting and Summing Within Each Partition

### 4.1. Counting with `counting()`

```java
Map<Boolean, Long> countByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));

System.out.println(countByPayment.get(true));  // 3
System.out.println(countByPayment.get(false)); // 2
```

The value type is `Long`, not `Integer`. If the goal is only the sizes of the two groups, this states the intent clearly without storing all objects.

### 4.2. Summing revenue with `summingLong()`

```java
Map<Boolean, Long> moneyByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.summingLong(Order::amountCents)
        ));

System.out.println(moneyByPayment.get(true));  // 23000
System.out.println(moneyByPayment.get(false)); // 15000
```

The paid group total is `12500 + 7500 + 3000 = 23000` cents, and the unpaid group total is `5000 + 10000 = 15000` cents.

If you only need the total amount, use `summingLong` instead of storing two `List<Order>` collections and iterating again to sum. Keep in mind that `long` **can still overflow** if the sum exceeds its range; storing money in integer units eliminates binary floating-point error, but does not eliminate overflow risk.

### 4.3. Computing averages with `averagingLong()`

```java
Map<Boolean, Double> averageByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.averagingLong(Order::amountCents)
        ));

System.out.println(averageByPayment.get(true));  // 7666.666666666667 (approx.)
System.out.println(averageByPayment.get(false)); // 7500.0
```

The paid group has a total of `23000` cents divided by `3` orders. The average result is a `double` and is approximate. For an empty group, `averagingLong` returns `0.0`; this value **does not tell you** whether the group genuinely has an average of 0 or has zero elements. If you need to distinguish those cases, also collect the count or use statistics that track `count`.

### 4.4. Multiple statistics with `summarizingLong()`

```java
import java.util.LongSummaryStatistics;

Map<Boolean, LongSummaryStatistics> statistics = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.summarizingLong(Order::amountCents)
        ));

LongSummaryStatistics paid = statistics.get(true);
System.out.println(paid.getCount());   // 3
System.out.println(paid.getSum());     // 23000
System.out.println(paid.getMin());     // 3000
System.out.println(paid.getMax());     // 12500
```

`summarizingLong` provides `count`, `sum`, `min`, `max`, and `average` without re-traversing the input. For an empty group, `getCount() == 0`, while `getMin()` and `getMax()` hold initial sentinel values `Long.MAX_VALUE` and `Long.MIN_VALUE`, respectively. Do not treat them as real business extremes when the group has no data.

## 5. `mapping()`: Transforming Data Types Before Collecting

`Collectors.mapping(mapper, downstream)` converts each `Order` into another value **within the scope of its respective partition**. It lets you choose which field to keep in the final result.

```java
Map<Boolean, List<String>> idsByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.mapping(
                        Order::id,
                        Collectors.toList()
                )
        ));

System.out.println(idsByPayment.get(true)); 
// [O-101, O-103, O-105]
System.out.println(idsByPayment.get(false));
// [O-102, O-104]
```

The source `T` is `Order`, but `mapping` turns it into `String`, and then `toList` produces `List<String>`. The overall result type is `Map<Boolean, List<String>>`.

### 5.1. Collecting unique values in each group

```java
import java.util.Set;

Map<Boolean, Set<String>> regionsByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.mapping(
                        Order::region,
                        Collectors.toSet()
                )
        ));

System.out.println(regionsByPayment.get(true).equals(Set.of("Bắc", "Nam")));
// true
System.out.println(regionsByPayment.get(false).equals(Set.of("Bắc", "Nam")));
// true
```

`toSet()` deduplicates according to the `Set` contract. It **does not guarantee element order** or a specific `Set` implementation class. If you need unique region codes in first-appearance order from a source with encounter order, use `toCollection(LinkedHashSet::new)`:

```java
import java.util.LinkedHashSet;

Map<Boolean, LinkedHashSet<String>> orderedRegions = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.mapping(
                        Order::region,
                        Collectors.toCollection(LinkedHashSet::new)
                )
        ));

System.out.println(orderedRegions.get(true)); // [Bắc, Nam]
```

Preserving encounter order can increase coordination overhead in parallel processing. If ordering does not matter, do not add unnecessary constraints just for "pretty" print output.

### 5.2. `mapping` downstream or `map` on the stream?

In the example where we need to partition and then extract `id`, we can write:

```java
// Correct: partition Order first, then extract id within each group.
Map<Boolean, List<String>> result = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.mapping(Order::id, Collectors.toList())
        ));
```

If you write `orders.stream().map(Order::id)` **before** `partitioningBy`, the stream elements have already become `String`, and `paid` is no longer available to classify by `Order::paid`. Therefore, placing `mapping` in the downstream collector is the natural way to express classification on the full object while keeping only a subset of fields in the output.

## 6. `filtering()` Inside a Partition

`Collectors.filtering(predicate, downstream)` (Java 9+) lets each partition **contribute only elements that pass an additional condition** to the downstream collector.

For example, counting only orders with a value of `10000` cents or more within each payment status:

```java
Map<Boolean, Long> highValueCounts = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.filtering(
                        order -> order.amountCents() >= 10_000,
                        Collectors.counting()
                )
        ));

System.out.println(highValueCounts.get(true));  // 1: O-101
System.out.println(highValueCounts.get(false)); // 1: O-104
```

You can read the pipeline in order:

1. Based on `paid`, determine whether an element belongs to the `true` or `false` partition.
2. Within that partition, keep only orders with `amountCents >= 10000` for counting.
3. Place the count results of both partitions into `Map<Boolean, Long>`.

Filtering **before** calling `partitioningBy` can also yield the same counts in this example:

```java
Map<Boolean, Long> alternative = orders.stream()
        .filter(order -> order.amountCents() >= 10_000)
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));
```

The difference lies in **how processing steps are expressed**: filtering before the collector removes elements from the entire stream; downstream `filtering` expresses an extra condition inside each partition's aggregation. With `partitioningBy`, both Boolean keys still appear even when a partition has zero elements left after filtering. When nesting `groupingBy` inside, where `filtering` is placed can affect which sub-groups are created; verify the intent before moving the filter step.

## 7. Combining `partitioningBy` with `groupingBy`

When two analysis dimensions are equally important, you can **partition first, then group**.

Requirement: for each payment status, calculate the total amount by region:

```java
Map<Boolean, Map<String, Long>> totalsByPaymentAndRegion =
        orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.groupingBy(
                                Order::region,
                                Collectors.summingLong(Order::amountCents)
                        )
                ));

System.out.println(totalsByPaymentAndRegion.get(true).get("Bắc"));  // 20000
System.out.println(totalsByPaymentAndRegion.get(true).get("Nam"));  // 3000
System.out.println(totalsByPaymentAndRegion.get(false).get("Bắc")); // 10000
System.out.println(totalsByPaymentAndRegion.get(false).get("Nam")); // 5000
```

Result structure:

```text
Map<Boolean, Map<String, Long>>
  true
    Bắc -> 20000
    Nam -> 3000
  false
    Bắc -> 10000
    Nam -> 5000
```

Reversing the nesting order to `groupingBy(Order::region, partitioningBy(Order::paid, summingLong(...)))` produces `Map<String, Map<Boolean, Long>>`. Both approaches hold the same numbers, yet serve **two different lookup patterns**:

- `Map<Boolean, Map<String, Long>>`: inspect payment status first.
- `Map<String, Map<Boolean, Long>>`: inspect region first.

Important: `partitioningBy` always contains both Boolean keys **at the level where it is used**. However, `groupingBy` creates keys only for classification groups that actually appear. If a partition has no orders, its inner region map is an empty map rather than automatically containing every hypothetical region.

### 7.1. Summing by region without using `groupingBy`

Since `toMap` is also a collector, you can use it as a downstream collector and supply a merge function:

```java
Map<Boolean, Map<String, Long>> amountsByRegion =
        orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.toMap(
                                Order::region,
                                Order::amountCents,
                                Long::sum
                        )
                ));

System.out.println(amountsByRegion.get(true).get("Bắc")); // 20000
```

If `Long::sum` is omitted, two paid orders in the `Bắc` region create a **duplicate key** in `toMap`, which can throw `IllegalStateException`. `groupingBy(..., summingLong(...))` expresses the grouping-and-summing intent more clearly. Additionally, `groupingBy` does not accept a classifier returning a `null` key; define a policy for missing region data before using it.

## 8. Finding the Best Element with `maxBy` or `minBy`

A partition may need to pick **a single object satisfying an extremum criterion**. `Collectors.maxBy` returns `Optional<T>` for each group because a group may be empty:

```java
import java.util.Comparator;
import java.util.Optional;

Map<Boolean, Optional<Order>> biggestByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.maxBy(
                        Comparator.comparingLong(Order::amountCents)
                                .thenComparing(Order::id)
                )
        ));

System.out.println(biggestByPayment.get(true).orElseThrow().id());
// O-101
System.out.println(biggestByPayment.get(false).orElseThrow().id());
// O-104
```

`thenComparing(Order::id)` defines a tie-breaker when amounts are equal. Without a secondary criterion, if two orders share the maximum amount, you should not rely on an arbitrary representative not defined by business rules.

For a source with no elements in one group:

```java
Map<Boolean, Optional<Order>> noUnpaid = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.maxBy(Comparator.comparingLong(Order::amountCents))
        ));

System.out.println(noUnpaid.get(false).isEmpty()); // true
```

Do not call `orElseThrow()` when a partition can be empty unless emptiness is genuinely a business error. If you want to convert `Optional<Order>` into an identifier or default value, handle `Optional` explicitly.

## 9. `collectingAndThen`: Finalizing Each Partition's Result

`Collectors.collectingAndThen(downstream, finisher)` lets you transform **the completed collection result of each group**.

For example, producing an unmodifiable list of order IDs:

```java
Map<Boolean, List<String>> immutableListsByPayment =
        orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.collectingAndThen(
                                Collectors.mapping(
                                        Order::id,
                                        Collectors.toList()
                                ),
                                List::copyOf
                        )
                ));

System.out.println(immutableListsByPayment.get(true));
// [O-101, O-103, O-105]

// immutableListsByPayment.get(true).add("O-999");
// Throws UnsupportedOperationException.
```

Note that **each list** is wrapped/replaced with an unmodifiable result, but you should not infer that **the `Map` itself** is unmodifiable. If you need both levels to be unmodifiable, wrap an outer `collectingAndThen` around it:

```java
Map<Boolean, List<String>> fullyReadOnly = orders.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.partitioningBy(
                        Order::paid,
                        Collectors.collectingAndThen(
                                Collectors.mapping(Order::id, Collectors.toList()),
                                List::copyOf
                        )
                ),
                Map::copyOf
        ));
```

`List.copyOf` and `Map.copyOf` reject `null` elements/values. They make the collections unmodifiable at the collection level; they **do not provide deep immutability** if inner elements are mutable objects.

## 10. `teeing`: Computing Multiple Metrics Simultaneously (Java 12+)

`Collectors.teeing(left, right, merger)` feeds each element into **two child collectors**, then combines both results into one. When used as a downstream collector, we can compute both the count and total amount of each partition:

```java
record Summary(long count, long totalCents) {}

Map<Boolean, Summary> summaryByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Order::amountCents),
                        Summary::new
                )
        ));

System.out.println(summaryByPayment.get(true));
// Summary[count=3, totalCents=23000]
System.out.println(summaryByPayment.get(false));
// Summary[count=2, totalCents=15000]
```

Meaning:

- `counting()` produces a `Long` count of orders in a partition.
- `summingLong(...)` produces a `Long` total amount for that same partition.
- `Summary::new` combines the two results into an immutable record.

For an empty partition, the result is `Summary(0, 0)`. That is a much cleaner contract than creating a mutable sum variable outside the pipeline and updating it via `peek`/`forEach`.

In applications running Java 8–11 without `teeing`, you can use `summarizingLong` if a built-in statistics object suffices, or design an appropriate collector. There is no need to create two separate streams just to count and sum when a single collector handles both requirements.

## 11. Distinguishing `partitioningBy` and `groupingBy`

Both collectors split data into groups, but they have different contracts:

| Criterion | `partitioningBy(predicate, downstream)` | `groupingBy(classifier, downstream)` |
|---|---|---|
| Keys | Only `true` and `false` | Keys of type `K` from classifier |
| Number of groups created | Always exactly two Boolean keys | Depends on keys that actually appear |
| Empty groups | Still receive a downstream result | Absent keys are usually not in the map |
| Input function | A `Predicate<T>` | A `Function<T, K>` |
| Use when | Two yes/no, pass/fail branches | Multiple groups by region, type, status |

Example when all orders are paid:

```java
List<Order> paidOnly = orders.stream()
        .filter(Order::paid)
        .toList();

Map<Boolean, Long> partitioned = paidOnly.stream()
        .collect(Collectors.partitioningBy(
                Order::paid, Collectors.counting()
        ));

Map<Boolean, Long> grouped = paidOnly.stream()
        .collect(Collectors.groupingBy(
                Order::paid, Collectors.counting()
        ));

System.out.println(partitioned.containsKey(false)); // true
System.out.println(partitioned.get(false));         // 0
System.out.println(grouped.containsKey(false));     // false
```

If you need **exactly two result buckets**, even when one is empty, `partitioningBy` models the domain better than `groupingBy`. If you need multiple states, such as `NEW`, `PAID`, `CANCELLED`, do not squeeze them into `true`/`false` and lose information; use `groupingBy` with an appropriate domain key.

## 12. Nulls, Exceptions, and Shared State

### 12.1. The partitioning condition must be well-defined

With valid `Order` source elements and primitive `boolean paid`, the `Order::paid` predicate always returns `true` or `false`. If the source contains **`null` elements**, this method reference can throw `NullPointerException` when processed:

```java
import java.util.Objects;

Map<Boolean, Long> safeCounts = java.util.stream.Stream
        .of(new Order("O-X", "Bắc", 100, true), null)
        .filter(Objects::nonNull)
        .collect(Collectors.partitioningBy(
                Order::paid, Collectors.counting()
        ));

System.out.println(safeCounts.get(true)); // 1
```

In problems with a boxed `Boolean` payment status (which can be `null`), do not automatically treat `null` as `false` if business rules need to distinguish "unknown" from "unpaid". `Boolean.TRUE.equals(value)` puts both `false` and `null` into the `false` branch; that is an **intentional business choice**, not an inherent default of `partitioningBy`.

To represent three distinct states (`TRUE`, `FALSE`, `UNKNOWN`), use `groupingBy` with an enum or a non-null key that captures all three states.

### 12.2. The downstream collector can also fail

If a mapper or classifier inside the downstream throws an exception, the error occurs when `collect` actually consumes the pipeline. For instance, `Collectors.groupingBy(Order::region)` does not allow the classifier to return a `null` key in standard cases; `Collectors.toMap` can throw on duplicate keys or `null` values.

Therefore, the predicate partitioning successfully **does not guarantee** the entire downstream collector will succeed. Define policies for missing/duplicate data before collecting.

### 12.3. Avoid side effects in predicates and collectors

```java
// Do not use an external variable to manually record results in a parallel pipeline.
// List<Order> paid = new ArrayList<>();
// orders.parallelStream().filter(order -> {
//     if (order.paid()) paid.add(order); // unsafe
//     return order.paid();
// }).count();
```

Predicates should be **stateless** and **non-interfering**, never mutating the source or appending to a shared `ArrayList`. Standard collectors coordinate accumulation and combination according to contract; there is no need to manually manage a shared container through side effects.

## 13. Parallelism, Ordering, and Performance

```java
Map<Boolean, Long> parallelCounts = orders.parallelStream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));

System.out.println(parallelCounts.get(true));  // 3
System.out.println(parallelCounts.get(false)); // 2
```

A parallel pipeline can split the source into chunks and then combine **two intermediate partitions**. `Collectors.partitioningBy` does not guarantee that the returned map is a concurrent map safe for external threads to mutate together. Avoid assuming the returned `Map<Boolean, D>` is thread-safe merely because the source is a `parallelStream()`.

Factors affecting performance:

1. **Downstream type:** `counting` and `summingLong` hold only small aggregates; `toList` may retain all elements, while nested `groupingBy` allocates additional maps and containers.
2. **Predicate/mapper cost:** use pure, simple functions; do not perform I/O or mutate external state inside a predicate.
3. **Encounter order:** on an ordered source, collectors like `toList` generally preserve encounter order of elements; collectors like `toSet` do not guarantee order. Do not rely on the iteration order of the two-key map.
4. **Element count:** having only **two groups** does not mean parallelism is guaranteed to be faster. Splitting, container allocation, and result-merging overhead can outweigh benefits on small sources.
5. **Numeric types:** `double` addition can suffer precision error and vary with parallel combination order; `long` avoids floating-point error for integer units, but can still overflow.

`collect` is a terminal operation, so once called, the same stream object cannot be consumed again. For unbounded sources, `partitioningBy(..., counting())` or `toList()` normally **will not terminate** without a suitable bound. For resource-backed sources such as `Files.lines(path)`, manage `close()` with `try-with-resources`; `partitioningBy` does not automatically close source resources.

## 14. Complete Runnable Program (Java 17+)

The following program is a standalone example. It uses the same order dataset to build lists, count, sum amounts, group by region, find the largest order, and combine two metrics:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

public class PartitioningDownstreamDemo {
    record Order(String id, String region, long amountCents, boolean paid) {}
    record Summary(long count, long totalCents) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O-101", "Bắc", 12_500, true),
                new Order("O-102", "Nam",  5_000, false),
                new Order("O-103", "Bắc",  7_500, true),
                new Order("O-104", "Bắc", 10_000, false),
                new Order("O-105", "Nam",  3_000, true)
        );

        Map<Boolean, Long> counts = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.counting()
                ));
        System.out.println(counts.get(true));  // 3
        System.out.println(counts.get(false)); // 2

        Map<Boolean, Long> totals = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.summingLong(Order::amountCents)
                ));
        System.out.println(totals.get(true));  // 23000
        System.out.println(totals.get(false)); // 15000

        Map<Boolean, Set<String>> regions = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.mapping(Order::region, Collectors.toSet())
                ));
        System.out.println(regions.get(true).equals(Set.of("Bắc", "Nam")));
        // true

        Map<Boolean, Map<String, Long>> byRegion = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.groupingBy(
                                Order::region,
                                Collectors.summingLong(Order::amountCents)
                        )
                ));
        System.out.println(byRegion.get(true).get("Bắc")); // 20000

        Map<Boolean, Optional<Order>> largest = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.maxBy(
                                Comparator.comparingLong(Order::amountCents)
                                        .thenComparing(Order::id)
                        )
                ));
        System.out.println(largest.get(false).orElseThrow().id());
        // O-104

        Map<Boolean, Summary> summaries = orders.parallelStream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.teeing(
                                Collectors.counting(),
                                Collectors.summingLong(Order::amountCents),
                                Summary::new
                        )
                ));
        System.out.println(summaries.get(true));
        // Summary[count=3, totalCents=23000]

        Map<Boolean, Long> noUnpaid = orders.stream()
                .filter(Order::paid)
                .collect(Collectors.partitioningBy(
                        Order::paid, Collectors.counting()
                ));
        System.out.println(noUnpaid.containsKey(false)); // true
        System.out.println(noUnpaid.get(false));         // 0
    }
}
```

In the parallel example, `teeing` composes standard collectors to gather both count and sum. Do not use external `count` or `sum` variables updated manually across threads.

## 15. Common Mistakes and Fixes

| Misconception or practice | Problem | Better approach |
|---|---|---|
| Thinking `partitioningBy` only has keys that appeared | Contract always creates both Boolean keys | Access `get(true)`/`get(false)` directly and handle empty-group downstream values |
| Thinking the downstream is always `List` | Result depends on the collector | Use the proper `Map<Boolean, D>` type |
| Using `toList` then recounting/summing when only metrics are needed | Unnecessarily stores data and traverses twice | Use `counting`, `summingLong`, `summarizingLong` |
| Assuming `averagingLong` returning `0.0` means the group has data | Empty groups also return `0.0` | Check `count` or `Optional` appropriately |
| Calling `orders.map(Order::id)` before partitioning by `paid` | After `map`, `paid` is no longer available | Use `mapping(Order::id, ...)` as the downstream collector |
| Using `toSet` and expecting insertion order | `toSet` does not guarantee order | Use `toCollection(LinkedHashSet::new)` when needed |
| Thinking nested `groupingBy` inside `partitioningBy` creates all region keys | Only Boolean keys are fixed; region map can be empty | Handle empty region maps when needed |
| Using `toMap` downstream with duplicate region keys and no merge | Can throw `IllegalStateException` | Use an appropriate merge function or `groupingBy` |
| Calling `Optional.get()` on `maxBy` of an empty group | Can throw `NoSuchElementException` | Use `isPresent`, `orElse`, or `orElseThrow` intentionally |
| Assuming the resulting `Map` is sorted or thread-safe | Not guaranteed by the collector | Choose APIs/result structures according to requirements |
| Predicate updates a shared `ArrayList` in parallel execution | Data race and uncontrollable side effects | Pure predicate, proper collector |
| Collecting from an unbounded infinite stream | Terminal operation never finishes | Use a finite source or `limit` before `collect` |

## 16. Self-Check

1. **What is the difference between `partitioningBy(predicate)` and `partitioningBy(predicate, counting())`?** The former returns `Map<Boolean, List<T>>`, whereas the latter returns `Map<Boolean, Long>`.
2. **If every element satisfies the predicate, does the result have a `false` key?** Yes; the downstream for the `false` group receives an empty partition.
3. **What does `Stream.<Order>empty().collect(partitioningBy(Order::paid, counting()))` return?** A Map with both `true -> 0L` and `false -> 0L`.
4. **If you want total amount by payment status, which downstream should you use?** `Collectors.summingLong(Order::amountCents)`.
5. **If you want a list of `id`s by status, what do you choose?** `Collectors.mapping(Order::id, Collectors.toList())` inside `partitioningBy`.
6. **If you want a deduplicated set of regions per status?** `mapping(Order::region, toSet())`; if first-appearance order is needed, use `toCollection(LinkedHashSet::new)`.
7. **How does downstream `filtering` differ from filtering before the collector?** It expresses the filtering condition inside each partition's aggregation; you must consider filter placement when nesting other collectors.
8. **Why does `partitioningBy(..., groupingBy(...))` not automatically contain every region?** Because `groupingBy` only generates keys for regions that have data; only the two Boolean keys are always present.
9. **Why does `maxBy` return `Optional<Order>`?** To represent the case where a partition has no matching elements.
10. **What does `teeing(counting(), summingLong(...), Summary::new)` produce?** A `Summary` containing the order count and total amount of each partition.
11. **Does `partitioningBy` executed on `parallelStream` return a thread-safe map?** There is no such guarantee; the framework manages collection, without turning the result into a concurrent map.
12. **When should you not use `partitioningBy`?** When there are more than two distinct states to distinguish; use `groupingBy` with a multi-valued key to avoid losing information.

**Key takeaway:** `partitioningBy(predicate, downstream)` has a structure of **two fixed Boolean keys**, while the downstream collector determines **each key's value**. Choose `counting` to count, `summingLong` to sum, `mapping` to transform types, `groupingBy` to group further, `maxBy` for extrema, `collectingAndThen` for a finishing step, and `teeing` to compute multiple metrics. Always check empty-group results, ordering requirements, numeric types, and parallel execution contracts before putting a pipeline into production.
