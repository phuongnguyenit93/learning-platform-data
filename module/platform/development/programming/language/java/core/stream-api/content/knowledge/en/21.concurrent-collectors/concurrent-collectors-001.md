# Distinguishing Collect on a Parallel Stream and a Concurrent Collector

In the Java Stream API, a **parallel stream** and a **concurrent collector** are two different concepts. Calling `parallelStream()` or `parallel()` allows the framework to split data for processing by multiple workers. Meanwhile, a Collector with the `CONCURRENT` characteristic indicates that **multiple workers are allowed to call the accumulator on the same result container**, when the framework chooses an appropriate concurrent accumulation strategy.

Therefore, both of the following statements are false:

- “Once you use `parallelStream()`, the collector must be thread-safe so that multiple threads modify a single `ArrayList` together.”
- “To process a Stream in parallel, you must use `groupingByConcurrent` or `toConcurrentMap`.”

A collector **without `CONCURRENT`** can still work properly on a parallel stream: the framework creates separate containers for branches, accumulates locally, and then merges them using the `combiner`. Conversely, a collector that declares `CONCURRENT` must actually tolerate multiple workers accessing **the same container**.

This lesson belongs to the **Concurrent Collection** chapter of the **JAVA_STREAM_API** module. It builds upon lazy pipelines, `filter`, `map`, `reduce`, and `collect`, while connecting with grouping, custom collectors, `Spliterator`, and parallel processing semantics. After this lesson, learners need to distinguish *parallel processing*, *concurrent reduction*, ordering requirements, the Collector contract, and trade-offs regarding performance, state, and resources.

## 1. Two Independent Questions When Designing a Collection Operation

Before each `collect` call, ask:

1. **What mode is the source/pipeline in?** `stream()` normally creates a sequential Stream; `parallelStream()` or `parallel()` requests parallel mode.
2. **What accumulation capabilities does the Collector declare?** Does it have the `CONCURRENT` characteristic? Does it have `UNORDERED`? Do the accumulator, combiner, and finisher adhere to the Collector contract?

Example:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList(4, 1, 3, 2);

// Parallel pipeline; Collector.toList() is NOT a concurrent collector.
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 10)
        .collect(Collectors.toList());

System.out.println(result); // [40, 10, 30, 20]
```

The result is still correct and preserves the encounter order of the `List`, even though `Collectors.toList()` does not declare `CONCURRENT`. The library is responsible for accumulating and merging the partial results according to the contract.

### 1.1. Comparison Table

| Aspect | Parallel Stream | Concurrent Collector |
|---|---|---|
| How to determine | `parallelStream()`, `parallel()`; checked via `isParallel()` | `collector.characteristics()` contains `CONCURRENT` |
| Primary effect | Allows processing the pipeline using multiple workers | Allows multiple workers to **accumulate concurrently into the same container** |
| Must they be used together? | No | No |
| Guarantees a speedup? | No | No |
| Automatically protects side effects outside the pipeline? | No | No |
| Preserves encounter order? | Still possible, depending on source/operations | Depends on `UNORDERED` and collector semantics |
| Needs a valid combiner? | Yes, when the collection needs to merge parts | Yes, the Collector must still have a contract-compliant combiner |

**Do not confuse processing mode with Collector characteristics:** `isParallel() == true` only describes the Stream configuration. It does not indicate whether workers are sharing a single container during `collect`.

## 2. Reviewing the Five Components of a Collector

The `Collector<T, A, R>` interface describes how to reduce an input sequence of type `T` into an accumulation state `A`, and then produce a result `R`.

| Component | Role |
|---|---|
| `supplier` | Creates a new accumulation container |
| `accumulator` | Incorporates an element `T` into container `A` |
| `combiner` | Combines two accumulation containers |
| `finisher` | Transforms `A` into `R` |
| `characteristics` | Describes guarantees such as `CONCURRENT`, `UNORDERED`, and `IDENTITY_FINISH` |

For `Collectors.toList()`, the intermediate state typically represents a list being accumulated. For `Collectors.summingLong(...)`, the state may represent a sum. For `groupingBy(...)`, the state holds the grouped results. A Collector is allowed to use **internal** mutable state; that does not mean it automatically allows multiple workers to modify **the same** state.

A valid Collector must satisfy at least three groups of requirements:

- **Identity:** merging an accumulated result with an empty container from the supplier does not change the meaning of the result.
- **Associativity:** accumulating in one pass and splitting into branches then merging must yield equivalent results.
- **Equivalence:** valid splits/executions produce results with the same meaning; for a collector without `UNORDERED`, output order may be part of that meaning.

Without a proper associativity contract, a collector might “work fine” in sequential mode yet lose elements or produce wrong sums when run in parallel, regardless of whether `CONCURRENT` is declared.

## 3. Two Ways to Execute Parallel Collection

### 3.1. Accumulating into Separate Containers, Then Merging via Combiner

This is the model suited for `Collectors.toList()` and many standard collectors:

```text
Ordered source: [A, B, C, D, E, F]
                        |
                split into branches
                 /              \
              [A,B,C]          [D,E,F]
                 |                |
              supplier         supplier
                 |                |
          container 1         container 2
          [A, B, C]           [D, E, F]
                 \                /
                    combiner
                        |
                 [A, B, C, D, E, F]
                        |
                     finisher
```

Each branch can use its **own** non-thread-safe `ArrayList`, because no two workers concurrently modify the same container in normal accumulation. The framework manages how branches are split and combined. The `combiner` merges intermediate states into the final result, preserving encounter order constraints when the collector and source require it.

Example:

```java
List<String> ordered = Arrays.asList("A", "B", "C", "D")
        .parallelStream()
        .collect(Collectors.toList());

System.out.println(ordered); // [A, B, C, D]
```

**There is no need** to switch to `Collections.synchronizedList` or manually create a `ConcurrentLinkedQueue` just because the Stream is run in parallel. Standard collectors are already designed for valid collection on parallel streams.

### 3.2. Accumulating Concurrently into a Shared Container

A collector with `CONCURRENT` can allow a different execution style:

```text
Parallel source: [A, B, C, D, E, F]
            /        |         \
         worker 1  worker 2   worker 3
            \        |         /
           concurrent accumulator
                      |
              shared container
                      |
                   finisher
```

Here, **the same container** may receive accumulator calls from multiple workers, so the container and update operations must tolerate concurrent access. A `ConcurrentHashMap` with appropriate update operations is a common foundation for concurrent Map collectors.

The framework **may** choose concurrent accumulation when conditions are met; `CONCURRENT` does not force the runtime to use an exact container or specific strategy in every situation.

## 4. Conditions for the Framework to Perform Concurrent Reduction

In the `Stream.collect(Collector)` model, direct concurrent reduction into a shared container is permitted when:

1. The Stream is in **parallel mode**;
2. The Collector has the **`CONCURRENT`** characteristic;
3. **The Stream has no encounter order**, **or** the Collector also declares **`UNORDERED`**.

This can be summarized briefly:

```text
parallel
   AND collector.CONCURRENT
   AND (stream unordered OR collector.UNORDERED)
            |
            v
Framework is permitted to perform concurrent reduction
```

This is a **permitting condition**, not a mandatory command forcing the framework to use that approach. If the last condition is not met, the runtime can still process the Stream in parallel using separate containers and a combiner to preserve encounter order requirements.

| Stream | Collector | Collection Behavior |
|---|---|---|
| Sequential | Not `CONCURRENT` | Typically sequential accumulation |
| Parallel, ordered | `toList()` not `CONCURRENT` | Branched accumulation and merge; preserves encounter order |
| Parallel, ordered | `CONCURRENT` but not `UNORDERED` | Cannot arbitrarily discard order; may use separate containers then merge |
| Parallel, ordered | `CONCURRENT` and `UNORDERED` | May accumulate concurrently into a shared container |
| Parallel, unordered | `CONCURRENT` collector | May accumulate concurrently |

### 4.1. CONCURRENT Differs from UNORDERED

**`CONCURRENT`** is a guarantee about the ability to call the accumulator concurrently on the same container. **`UNORDERED`** is a guarantee that **element order does not contribute to determining the equivalence of the result**.

A Collector can be `CONCURRENT` without being `UNORDERED` by contract, in which case the framework must consider the source's ordering before accumulating concurrently. Conversely, a collector like `Collectors.toSet()` can be `UNORDERED` yet **not `CONCURRENT`**: the result does not need order, but the accumulator is not permitted to receive concurrent writes on the same `HashSet`.

**`IDENTITY_FINISH`** is yet a third property: the finisher is an identity mapping between the accumulation state and the result. It does **not** by itself indicate thread safety or unorderedness.

### 4.2. Checking Characteristics in Code

```java
import java.util.stream.Collector;
import java.util.stream.Collectors;

boolean listConcurrent = Collectors.toList()
        .characteristics()
        .contains(Collector.Characteristics.CONCURRENT);

boolean setUnordered = Collectors.toSet()
        .characteristics()
        .contains(Collector.Characteristics.UNORDERED);

boolean concurrentMap = Collectors.toConcurrentMap(
                String::length, value -> value, (a, b) -> a)
        .characteristics()
        .contains(Collector.Characteristics.CONCURRENT);

System.out.println(listConcurrent); // false
System.out.println(setUnordered);    // true
System.out.println(concurrentMap);   // true
```

`characteristics()` describes the **collector's contract**. The output above is not proof of how many threads or containers a particular run actually used.

## 5. Comparing Commonly Used Map Collectors

Two pairs of APIs directly related to this problem are `groupingBy`/`groupingByConcurrent` and `toMap`/`toConcurrentMap`.

| Collector | Typical Result | `CONCURRENT` | Ordering |
|---|---|---|---|
| `Collectors.toMap(...)` | `Map<K, V>` | No | Does not guarantee Map key iteration order; can preserve encounter order semantics when merge depends on order |
| `Collectors.toConcurrentMap(...)` | `ConcurrentMap<K, V>` | Yes | `UNORDERED` collector, does not rely on “first/last seen value” |
| `Collectors.groupingBy(...)` | `Map<K, D>` | No | Downstream can preserve appropriate encounter order |
| `Collectors.groupingByConcurrent(...)` | `ConcurrentMap<K, D>` | Yes | `UNORDERED` collector, does not guarantee value order within each group |
| `Collectors.toList()` | `List<T>` | No | Preserves encounter order if the source is ordered |
| `Collectors.toSet()` | `Set<T>` | No | Does not guarantee encounter order |

Choosing a concurrent collector **is not simply picking a “faster version”**. It can change the ordering constraints that the business logic requires, and not every workload benefits when multiple workers update a single Map concurrently.

### 5.1. groupingBy on a Parallel Stream Is Still Valid

```java
Map<String, Long> counts = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.counting()));
```

This snippet assumes `Order` has `getRegion()` returning `String` and the `orders` list has valid elements. The framework can create per-branch Maps and then combine them. `Collectors.groupingBy` **does not need `CONCURRENT`** to work correctly in this case.

### 5.2. groupingByConcurrent When Encounter Order Is Not Needed

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> counts = orders.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Order::getRegion,
                Collectors.counting()));
```

`groupingByConcurrent` returns a collector with concurrent and unordered characteristics. It can support concurrent accumulation by key. Do not assume that any downstream collector such as `Collectors.toList()` immediately becomes a thread-safe List for the application to freely mutate after collection.

### 5.3. toMap and toConcurrentMap When Duplicate Keys Exist

```java
Map<String, Long> totalBySku = orders.parallelStream()
        .collect(Collectors.toMap(
                Order::getSku,
                Order::getAmountCents,
                Long::sum));

ConcurrentMap<String, Long> concurrentTotals = orders.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Order::getSku,
                Order::getAmountCents,
                Long::sum));
```

Both collectors above solve the same problem of **summing amounts by SKU**, provided input values are valid and the sum does not overflow `long`. The difference lies in the **accumulation strategy** and result characteristics, not in the summation formula.

If you omit `mergeFunction` from `toMap` or `toConcurrentMap` when duplicate keys exist, the collector may throw `IllegalStateException`. Do not use `(oldValue, newValue) -> newValue` in `toConcurrentMap` to infer the “latest record”: an unordered collector does not guarantee update order according to the input data. If you need the latest by timestamp/version, choose the maximum according to a deterministic comparison rule.

## 6. Complete Java 8 Example: Same Data, Two Strategies

The following program runs from **Java 8** onward, illustrating:

- Collecting into a List from a parallel stream **without needing a concurrent collector**.
- Comparing `toMap` with `toConcurrentMap` when summing numbers by key.
- Comparing `groupingBy` with `groupingByConcurrent` when counting records.
- Clearly seeing the issue of list ordering within each group.
- Checking the `CONCURRENT` characteristic of both collector types.

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class ConcurrentCollectorDemo {
    static final class Order {
        private final String id;
        private final String region;
        private final String sku;
        private final long amountCents;
        private final boolean paid;

        Order(String id, String region, String sku,
                long amountCents, boolean paid) {
            this.id = id;
            this.region = region;
            this.sku = sku;
            this.amountCents = amountCents;
            this.paid = paid;
        }

        String getId() {
            return id;
        }

        String getRegion() {
            return region;
        }

        String getSku() {
            return sku;
        }

        long getAmountCents() {
            return amountCents;
        }

        boolean isPaid() {
            return paid;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("A1", "BAC", "P01", 100L, true),
                new Order("A2", "NAM", "P02", 250L, true),
                new Order("A3", "BAC", "P01", 150L, true),
                new Order("A4", "BAC", "P03", 500L, false),
                new Order("A5", "NAM", "P02", 350L, true),
                new Order("A6", "BAC", "P01", 200L, true)
        );

        // 1) Parallel pipeline with a NON-CONCURRENT collector.
        List<String> paidIds = orders.parallelStream()
                .filter(Order::isPaid)
                .map(Order::getId)
                .collect(Collectors.toList());

        System.out.println(paidIds);
        // [A1, A2, A3, A5, A6] - encounter order of the source List

        // 2) Merge branch Maps using toMap.
        Map<String, Long> totalsBySku = orders.parallelStream()
                .filter(Order::isPaid)
                .collect(Collectors.toMap(
                        Order::getSku,
                        Order::getAmountCents,
                        Long::sum));

        // 3) Concurrent and unordered collector.
        ConcurrentMap<String, Long> concurrentTotals =
                orders.parallelStream()
                        .filter(Order::isPaid)
                        .collect(Collectors.toConcurrentMap(
                                Order::getSku,
                                Order::getAmountCents,
                                Long::sum));

        System.out.println(totalsBySku.get("P01")); // 450
        System.out.println(concurrentTotals.get("P01")); // 450
        System.out.println(concurrentTotals.get("P02")); // 600

        // 4) Both groupingBy and groupingByConcurrent count accurately.
        Map<String, Long> normalCounts = orders.parallelStream()
                .filter(Order::isPaid)
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.counting()));

        ConcurrentMap<String, Long> concurrentCounts =
                orders.parallelStream()
                        .filter(Order::isPaid)
                        .collect(Collectors.groupingByConcurrent(
                                Order::getRegion,
                                Collectors.counting()));

        System.out.println(normalCounts.get("BAC")); // 3
        System.out.println(concurrentCounts.get("BAC")); // 3
        System.out.println(concurrentCounts.get("NAM")); // 2

        // 5) groupBy preserves encounter order in the List of each group.
        Map<String, List<String>> idsByRegion = orders.parallelStream()
                .filter(Order::isPaid)
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.mapping(Order::getId, Collectors.toList())));

        ConcurrentMap<String, List<String>> concurrentIdsByRegion =
                orders.parallelStream()
                        .filter(Order::isPaid)
                        .collect(Collectors.groupingByConcurrent(
                                Order::getRegion,
                                Collectors.mapping(
                                        Order::getId,
                                        Collectors.toList())));

        System.out.println(idsByRegion.get("BAC")); // [A1, A3, A6]

        // Do not rely on the List order in a concurrent collector.
        System.out.println(
                new HashSet<>(idsByRegion.get("BAC")).equals(
                        new HashSet<>(concurrentIdsByRegion.get("BAC"))));
        // true - same contents, though the order may differ

        // 6) Check the collector's contract, do not infer from thread count.
        boolean listIsConcurrent = Collectors.toList()
                .characteristics()
                .contains(Collector.Characteristics.CONCURRENT);

        boolean groupingIsConcurrent =
                Collectors.groupingByConcurrent(
                                Order::getRegion,
                                Collectors.counting())
                        .characteristics()
                        .contains(Collector.Characteristics.CONCURRENT);

        System.out.println(listIsConcurrent);     // false
        System.out.println(groupingIsConcurrent); // true
    }
}
```

**Explanation:** With five paid orders, the totals by SKU are `P01 = 450` and `P02 = 600`; the order counts by region are `BAC = 3`, `NAM = 2`. Both Map strategies yield the same numerical results. The key difference appears in the **collection characteristics**: the List from `groupingBy` preserves the encounter order of orders in each group, whereas `groupingByConcurrent` does not guarantee that order.

The program intentionally uses only a few records to make **API semantics** easy to observe, not to demonstrate performance gains. At small sizes, the overhead of parallel streams and concurrent maps can exceed the actual work.

## 7. Why Can Non-Thread-Safe toList() Still Be Used with parallelStream()?

This is a very common interview question. `ArrayList` does not allow multiple threads to concurrently call `add` on **one instance** without synchronization. However, `Collectors.toList()` **does not guarantee** that all workers add into a single `ArrayList` instance.

In regular mutable reduction, the framework can:

1. Create a separate `List` for each branch.
2. Put that branch's elements into its own `List`.
3. Merge the intermediate `List`s using the combiner.
4. Return the final list when `collect` finishes.

That is completely different from:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> unsafeSharedList = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(unsafeSharedList::add); // WRONG.
```

In the wrong example, **the program itself** creates an `ArrayList` outside the pipeline and shares it across all actions. The framework does not control merging that state, and `ArrayList` is not thread-safe. The result can lose elements, corrupt data, or throw errors.

### 7.1. The collect(supplier, accumulator, combiner) Overload

`Stream.collect` also has a three-parameter overload, allowing you to describe mutable reduction directly:

```java
List<Integer> safeList = java.util.stream.IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(
                ArrayList::new,
                List::add,
                (left, right) -> left.addAll(right));

System.out.println(safeList.size()); // 10000
```

Here, `supplier` creates a separate container and `combiner` merges them according to the contract. Do not put a static, shared `ArrayList` in the supplier; if the supplier always returns **the same container**, the algorithm can suffer from data races when run in parallel.

**Note:** This overload does not accept a `Collector` object with `characteristics()`; it still relies on branched accumulation and a combiner. You cannot arbitrarily declare it “concurrent” just by switching from `stream()` to `parallelStream()`.

## 8. Writing a Custom Concurrent Collector: Only Declare It When the Accumulator Is Truly Safe

Sometimes standard collectors cannot express the problem. In that case, a custom collector that wants to declare `CONCURRENT` must ensure:

- `supplier` creates a valid new container, not returning a globally shared container across collections.
- `accumulator` tolerates multiple concurrent calls on **the same container**.
- `combiner` still combines two containers properly when the framework chooses branched merging.
- `finisher` only declares `IDENTITY_FINISH` if no transformation from `A` to `R` is actually needed.
- `UNORDERED` is only declared when the encounter order of elements does not change the meaning of the result.

### 8.1. Example of a Concurrent Collector Using LongAdder

`LongAdder` in `java.util.concurrent.atomic` supports efficient count accumulation under contention. The collector below counts the elements in a Stream. Each element increments the counter; the final result is of type `Long`, so `IDENTITY_FINISH` is **not** declared.

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;

public class ConcurrentCountCollectorDemo {
    public static void main(String[] args) {
        Collector<String, LongAdder, Long> concurrentCount =
                Collector.of(
                        LongAdder::new,
                        (counter, value) -> counter.increment(),
                        (left, right) -> {
                            left.add(right.sum());
                            return left;
                        },
                        LongAdder::sum,
                        Collector.Characteristics.CONCURRENT,
                        Collector.Characteristics.UNORDERED);

        List<String> names = Arrays.asList("An", "Bình", "Chi", "Dũng");

        long count = names.parallelStream()
                .collect(concurrentCount);

        System.out.println(count); // 4
        System.out.println(concurrentCount.characteristics().contains(
                Collector.Characteristics.CONCURRENT)); // true
    }
}
```

This collector has the semantics of **counting**, independent of order, so `UNORDERED` is appropriate. `LongAdder.increment()` supports concurrent updates. The combiner adds the sum of the right branch into the left branch if the framework uses multiple containers. `LongAdder::sum` is only used to produce the result once the collection process has finished; reading the sum while multiple threads are still updating may only be an unstable observed value.

In practice, `Collectors.counting()` or `Stream.count()` is much simpler if you only need to count. The `LongAdder` example is meant to clarify **why declaring `CONCURRENT` must go hand in hand with a safe accumulator design**, not to recommend always writing custom collectors instead of standard APIs.

### 8.2. Incorrect Example: Declaring CONCURRENT for ArrayList

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

// WRONG: declaring CONCURRENT even though ArrayList.add is not thread-safe.
Collector<String, List<String>, List<String>> broken =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED);
```

In the collector above, when concurrent accumulation is allowed, multiple workers can modify a single `ArrayList` at the same time. This causes a data race. Adding `CONCURRENT` **does not automatically make a container thread-safe**; it is a **promise from the collector author** to the framework.

There is another mistake: marking `UNORDERED` when the caller needs a list in encounter order. Even if you fix the race with a thread-safe collection, the insertion order of workers is still not equivalent to the source order.

## 9. groupingByConcurrent: A Safe Map Does Not Mean the Inner Lists Are Safe for Arbitrary Use

Example:

```java
ConcurrentMap<String, List<String>> ids = orders.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Order::getRegion,
                Collectors.mapping(
                        Order::getId,
                        Collectors.toList())));
```

`groupingByConcurrent` is a concurrent collector. However, the downstream `toList` **does not have the `CONCURRENT` characteristic**. The JDK can protect accumulation operations on a downstream container with an appropriate synchronization mechanism during collection. Therefore, you must not assume that subsequent application calls to `List.add` on the resulting lists become thread-safe later.

Distinguish three situations:

1. **During collection:** the framework is responsible for properly implementing the collector's contract, even when the downstream is not concurrent.
2. **After collect returns the result:** `ConcurrentMap` supports concurrent Map operations according to its contract, but a `List` stored inside a value may still not be thread-safe when modified by multiple threads simultaneously.
3. **When the application needs order within each group:** `groupingByConcurrent` is an unordered collector, so you must not rely on element positions in the `List` to represent transaction timing or order.

If you need both grouping and lists that preserve order, `groupingBy(..., toList())` usually expresses the intent more clearly. If multiple threads need to modify the lists after collection, you must choose an appropriate data/synchronization design at **the layer that consumes the result**, rather than relying on the outer Map being concurrent.

## 10. Ordering Semantics and Order-Dependent Merge Functions

Two common merge functions are:

```java
// Keep the value that appears earlier in an ordered sequence.
(oldValue, newValue) -> oldValue

// Keep the value that appears later in an ordered sequence.
(oldValue, newValue) -> newValue
```

They are **associative** but **not commutative**: changing input order can change the result. Because `toConcurrentMap` is an unordered collector, they should not be used to determine “first” or “last” by encounter order.

For example, if you want to select each customer's latest order, you should use a business attribute such as `timestamp`, `version`, or a unique identifier as a tie-breaker:

```java
import java.util.Comparator;
import java.util.function.BinaryOperator;

Comparator<Event> byTimeThenId =
        Comparator.comparingLong(Event::getTimestamp)
                .thenComparing(Event::getId);

BinaryOperator<Event> latest = BinaryOperator.maxBy(byTimeThenId);
```

This snippet assumes an `Event` type exists, `getTimestamp()` returns `long`, `getId()` returns a non-null key, and id values serve as tie-breakers. If the comparator defines **a unique maximum**, the selection result does not depend on worker execution order. When you want to select by transaction order rather than timestamp, you must preserve encounter order in the pipeline and use an appropriate collector.

### 10.1. Sorting Map Keys Is Also an Independent Concern

A `ConcurrentMap` or `Map` from the default collectors does not guarantee a business-defined key iteration order. If you want to output a report in ascending key order, sort the result at presentation time or use an appropriately ordered structure. Do not assume that `parallel()`, `CONCURRENT`, or `UNORDERED` automatically produces a stable order.

## 11. Performance: Concurrent Reduction Does Not Mean Faster

Benefits depend on data size, mapping cost, number of groups/keys, key distribution, contention level, source splittability, and ordering requirements.

| Scenario | Consideration |
|---|---|
| Many independent keys, no ordering needed, large data | `toConcurrentMap` or `groupingByConcurrent` is worth trying |
| Most records share a single key | Multiple workers contend on one entry; a concurrent collector may perform poorly |
| Need to keep lists of events in exact encounter order | `groupingBy(..., toList())` is usually more appropriate |
| Only a few dozen records, cheap transformations | Parallel overhead is usually not worthwhile |
| Downstream collector has a complex finisher or combiner | Measure merging cost; do not infer from the name “Concurrent” |
| `Files.lines` or I/O source with resources to close | Parallel does not replace `try-with-resources`, and may increase I/O load |
| Many duplicate keys and CPU-expensive merges | Check contention, lock duration, and memory |

### 11.1. Source Splittability and Spliterator Characteristics

`Spliterator` determines how well source elements can be split across workers. Sources like `ArrayList` or numeric ranges like `IntStream.range` are usually easy to split; sources that depend on previous elements or I/O sources may split poorly. Therefore, `parallelStream()` does not guarantee that all elements actually run concurrently or that concurrent collection will always stay busy.

### 11.2. Measuring Performance Properly

If you want to compare `groupingBy` and `groupingByConcurrent`:

1. Use data with record counts, key collision rates, and group distributions close to production.
2. Verify that both results are **equivalent in value**, not just having the same number of keys; if a result is unordered, do not use Map print order for comparison.
3. Warm up the JVM and run multiple iterations; benchmark with a tool like JMH when conclusions are needed.
4. Also measure memory allocation, contention, number of active workers, and other task loads.
5. Do not run `System.out.println` for every element when the goal is to measure CPU algorithms.

If business requirements strictly require ordering, do not trade correctness for speed by switching to an unordered collector.

## 12. Common Mistakes

| Claim or Practice | Issue | How to Handle |
|---|---|---|
| “Parallel stream requires every collector to be thread-safe.” | The framework can use separate containers then a combiner | Use standard collectors like `toList`, `groupingBy` normally |
| “A collector with `CONCURRENT` always uses a single shared container.” | The framework may choose another execution strategy; ordering condition applies | Check both Stream mode and `UNORDERED` |
| “`UNORDERED` also implies `CONCURRENT`.” | Two independent characteristics | Check each characteristic individually |
| Manually declaring `CONCURRENT` for `ArrayList` | `ArrayList.add` is not thread-safe | Remove the characteristic or design a genuinely concurrent container/accumulator |
| Attaching `UNORDERED` and expecting the list to keep encounter order | Gives up ordering requirements | Use an ordered collector |
| `groupingByConcurrent(..., toList())` then modifying the List from multiple threads | The downstream List may not be thread-safe | Protect or copy the result before concurrent modification |
| Using keep-last merge with `toConcurrentMap` to find the “latest” | Worker update order does not represent timestamp | Select by timestamp/version and a tie-breaker |
| Using `toConcurrentMap(key,value)` with duplicate keys | May throw `IllegalStateException` | Choose an appropriate merge function |
| Key mapper or value mapper returning null | Prone to throwing `NullPointerException` | Filter/normalize inputs |
| Assuming concurrent collectors are always faster | Can suffer key contention and high overhead | Benchmark with realistic data distributions |
| Overusing side effects outside the pipeline | Data races or business logic bugs | Use reduction/collectors and pure functions |

## 13. Self-Check Exercises with Answers

### Exercise 1. Parallel List and the CONCURRENT Characteristic

```java
List<Integer> result = Arrays.asList(1, 2, 3)
        .parallelStream()
        .collect(Collectors.toList());
```

**Question:** Why is this code valid even though `Collectors.toList()` is not concurrent?

**Answer:** The framework can create separate containers for branches and merge them with a combiner. Multiple workers are not required to call `add` on a single List concurrently. With an ordered List source, the result is `[1, 2, 3]`.

### Exercise 2. Concurrent Reduction Condition

**Question:** An ordered Stream is running in parallel. The Collector has `CONCURRENT` but **does not have `UNORDERED`**. Can it be assumed that all workers will update a single container while ignoring order?

**Answer:** No. To perform concurrent reduction without preserving order, the encounter order condition must also be met: the Stream is unordered **or** the collector has `UNORDERED`. The framework can split containers and merge them to preserve ordering semantics.

### Exercise 3. Choosing a Grouping Collector

The source is a large list of orders. The business only needs to **count orders by region**, with no ordering requirement. Can `groupingByConcurrent(..., counting())` be used?

**Answer:** Yes, if the key fields are valid. However, you should compare performance against `groupingBy(..., counting())` because speed depends on key dispersion and contention.

### Exercise 4. Identifying a Dangerous Collector

A collector has supplier `ArrayList::new`, accumulator `List::add`, and is marked `CONCURRENT, UNORDERED`. What is wrong?

**Answer:** When the runtime accumulates from multiple workers into the same `ArrayList`, the `add` calls have a data race. You must not declare `CONCURRENT` for a container/accumulator that is not actually safe.

### Exercise 5. Selecting the Last Record

Three records with the same key have timestamps `100, 130, 120`. The author uses `toConcurrentMap` with merge `(oldValue, newValue) -> newValue`. Is it guaranteed to get timestamp `120` as the last element of the source List?

**Answer:** No. The collector is unordered; concurrent merge order does not represent encounter order. If you need the largest timestamp, use selection by timestamp with a tie-breaker for equals, yielding `130`.

### Exercise 6. Thread Safety of the Map and List Values

The application obtains a `ConcurrentMap<String, List<String>>` from `groupingByConcurrent(..., toList())`. After collection finishes, two threads concurrently call `get("BAC").add(...)`. Is this safe?

**Answer:** Not guaranteed. The outer Map is concurrent, but the downstream `List` values are not inherently thread-safe for arbitrary mutations after collection. You need a synchronization design or a different collection type when the application requires this.

### Exercise 7. Writing a Custom Concurrent Counting Collector

Why does the collector using `LongAdder` in section 8 declare `CONCURRENT, UNORDERED` but not `IDENTITY_FINISH`?

**Answer:** The `LongAdder` accumulator can be safely incremented by multiple workers, and counting does not depend on order. However, the intermediate accumulator is `LongAdder` while the result is `Long`; the finisher `LongAdder::sum` must be executed, so it is not an identity finish.

## 14. Checklist Before Choosing a Concurrent Collector

Before replacing `groupingBy` with `groupingByConcurrent` or `toMap` with `toConcurrentMap`, check yourself:

1. **Is the pipeline actually parallel?** `parallelStream()` and `parallel()` change the mode, without guaranteeing speedup.
2. **Does the output need encounter order?** If list order or “first/last” matters, an unordered collector may not be suitable.
3. **Is the collector truly `CONCURRENT`?** Check `characteristics()` and the contract, do not infer from variable names.
4. **Can the accumulator tolerate multiple calls on the same container?** Do not declare `CONCURRENT` for an unprotected `ArrayList` or `HashMap`.
5. **Is the combiner correct?** The framework may still split the result into multiple branches and merge them.
6. **Does the downstream hold mutable state?** A `ConcurrentMap` does not make every object inside it thread-safe.
7. **Are the merge function and computation valid?** Duplicate keys, overflow, associativity, ordering, and null values must be handled explicitly.
8. **Is there a real performance benefit?** Measure with large/small data, group counts, key distribution, and contention before deciding.

**Remember:** `parallelStream().collect(...)` does not mean “every thread modifies one accumulator together”. Normal collectors can run correctly on a parallel stream by **accumulating independently and then combining**. A `CONCURRENT` collector allows **concurrent accumulation into the same container** when conditions are met, often paired with `UNORDERED` to avoid maintaining encounter order. Prioritize the correctness of the Collector contract, choose ordering based on business needs, and only use a concurrent strategy when it fits the data and has been measured.
