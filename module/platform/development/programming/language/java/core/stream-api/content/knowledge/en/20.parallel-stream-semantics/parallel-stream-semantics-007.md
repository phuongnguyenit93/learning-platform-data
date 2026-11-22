# Shared State, Thread Confinement, and Thread Safety

When switching a Java Stream API pipeline from `stream()` to `parallelStream()`, Java may process elements across multiple concurrent tasks. If lambdas only read immutable data and return new values, the program usually remains straightforward. However, if lambdas **write to a shared `ArrayList`, `HashMap`, counter, or object**, results can suffer from missing elements, duplicates, wrong ordering, or dependence on thread scheduling.

This lesson belongs to the **Parallel Processing Semantics** chapter of the **JAVA_STREAM_API** module. The goal is to understand three related yet distinct ideas: **shared mutable state**, **thread confinement** (restricting state access within an execution scope), and **thread safety** (correctness under concurrent access). We will apply these rules to `filter`, `map`, `reduce`, `collect`, `groupingBy`, custom collectors, `Spliterator`, I/O sources, parallel execution, and performance evaluation.

## 1. Why does a sequential pipeline seem right yet fail in parallel?

Consider a list of integers where we want to extract even numbers into a new list.

Dangerous approach:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> result = new ArrayList<>();

IntStream.range(0, 10_000)
    .parallel()
    .filter(n -> n % 2 == 0)
    .forEach(result::add); // Unsafe!

System.out.println(result.size());
```

Mathematically, there are **5,000** even numbers in `[0, 10_000)`. Yet `ArrayList.add` is not designed for concurrent updates by multiple threads on the same list. Writing to the internal array and updating the element count can race, making the result unreliable; bugs may also not surface on every run.

Fix using Stream's collection mechanism:

```java
List<Integer> evenNumbers = IntStream.range(0, 10_000)
    .parallel()
    .filter(n -> n % 2 == 0)
    .boxed()
    .toList();

System.out.println(evenNumbers.size()); // 5000
```

This pipeline delegates result management to `toList()`. With an ordered source like `IntStream.range`, `toList()` preserves encounter order; the returned list cannot be mutated via `add`/`remove`. We do not need to coordinate concurrent `add` calls into a global `ArrayList`.

**First principle:** Describe the **desired result** using `reduce` or `collect`, instead of turning lambdas into a loop mutating external state.

## 2. Three concepts to distinguish

| Concept | Meaning | Example |
| --- | --- | --- |
| **Shared mutable state** | Two or more tasks can access the same object/field and at least one task can write to it | Multiple lambdas calling `sharedList.add(...)` |
| **Thread confinement** | State is owned by only one thread or task scope at a time, never mutated concurrently by multiple tasks | A private accumulation container for one `collect` branch |
| **Thread safety** | Operations on state uphold their contract when multiple threads access it concurrently | `ConcurrentHashMap` with appropriate update methods |

**Thread-safe does not mean the whole algorithm is correct.** For example, `AtomicInteger.incrementAndGet()` guarantees a single increment is atomic, yet it does not guarantee the lambda is called exactly once per input element; Stream operations may short-circuit or skip unnecessary work.

**Thread confinement also does not mean an object is permanently pinned to the same Java thread.** In a non-concurrent collector, accumulation state is managed so it never experiences concurrent accumulator calls on the same container. During combining, a container may be handed across tasks in a framework-managed way. What must hold is **no unprotected concurrent write ownership**, not memorizing thread IDs.

### Visual diagram

```text
Wrong: unsynchronized shared state

 task A ---- add ----\
 task B ---- add -----+----> shared ArrayList (race)
 task C ---- add ----/

Right: accumulation state owned by processing chunks

 task A --> container A --\
                           +--> combiner --> result
 task B --> container B --/
```

In the second approach, `supplier`, `accumulator`, and `combiner` express the state-management boundaries. This is why a collector can use a mutable internal container without requiring that container itself to be concurrent.

## 3. Why do shared `ArrayList` and `HashMap` easily cause data races?

A **data race** occurs when tasks access ordinary state without proper synchronization, including at least one write. The consequences go beyond "losing one increment":

- One update can overwrite another update.
- Internal structure can be left inconsistent while another task reads or writes.
- Observed order and value visibility across threads can diverge from expectations.
- Results can vary between runs even on identical inputs.

Example counting by region using an external `HashMap`:

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Long> totals = new HashMap<>();

orders.parallelStream().forEach(order ->
    totals.merge(order.region(), order.amountVnd(), Long::sum)
); // Wrong: HashMap is not safe for concurrent updates.
```

Even if every element belonged to a distinct region, two tasks can still collide or corrupt Map structure. The fact that `Map.merge` is a convenient method **does not turn `HashMap` into a concurrent Map**.

Writing according to aggregation intent:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> totalsByRegion = orders.parallelStream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

`groupingBy` combined with `summingLong` lets the framework manage accumulators and merge partial results.

## 4. Requirements for lambdas: non-interfering and stateless

Functions passed to many Stream operations such as `filter`, `map`, and `mapToLong` must satisfy key requirements:

- **Non-interfering:** must not interfere with the source being traversed by the Stream, unless the source is contractually designed to support concurrent modification.
- **Stateless:** the result must not depend on state that can change during pipeline execution.

Well-behaved lambdas:

```java
List<String> names = List.of("An", "Bình", "Chi");

List<Integer> lengths = names.parallelStream()
    .filter(name -> !name.isBlank())
    .map(String::length)
    .toList();

System.out.println(lengths); // [2, 4, 3]
```

`String::length` only reads the input object and returns a number; `filter` does not mutate the source. Thus operations can be evaluated without updating shared variables.

Improper lambdas:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

source.parallelStream()
    .map(n -> {
        source.add(n * 10); // Interfering with the collection being traversed!
        return n * n;
    })
    .toList();
```

This snippet can throw `ConcurrentModificationException` or exhibit undefined behavior, even before considering result correctness. Do not modify the traversed source structure inside ordinary behavioral functions.

### 4.1. Input elements themselves can also be shared

Even when the source `List` is unmodifiable, individual elements in the list may be **mutable objects**, and multiple entries in the source may reference the same object. When a lambda mutates an element, tasks can write to that same object concurrently.

```java
final class Counter {
    int value;
}

Counter shared = new Counter();
List<Counter> input = List.of(shared, shared);

input.parallelStream().forEach(counter -> counter.value++);
```

Both entries here point to **the same Counter**. `value++` is not atomic; having `List.of(...)` as the source does not make `Counter` immutable. To process safely in parallel, prefer constructing **new result values** or applying synchronization/ownership rules suited to the data model.

## 5. Shared mutable accumulators and what breaks `reduce`

`reduce(identity, accumulator)` is designed for a combining operation with a **valid identity**, **associativity**, and no reliance on external side effects.

Safe example:

```java
import java.util.stream.LongStream;

long sum = LongStream.rangeClosed(1, 1_000)
    .parallel()
    .reduce(0L, Long::sum);

System.out.println(sum); // 500500
```

`Long::sum` combines two values and returns a `long`; it does not mutate shared variables. Within the example's range, the sum does not overflow. However, `parallel()` does not make `long` immune to overflow, and `double` addition can still differ in the last digits due to rounding.

Wrong example with side effects:

```java
import java.util.concurrent.atomic.AtomicLong;

AtomicLong runningTotal = new AtomicLong();

long reduced = LongStream.rangeClosed(1, 1_000)
    .parallel()
    .reduce(0L, (left, right) -> {
        runningTotal.addAndGet(right); // External side effect inside reduce!
        return left + right;
    });
```

`runningTotal` is thread-safe at the single-update level, yet the program maintains **two results** with different semantics. In parallel reduction, the accumulator can receive partial results rather than only raw source elements, so `runningTotal` has no contract equivalent to the sum. The right approach is **using the returned `reduced` value directly** and removing the side effect.

### 5.1. Associativity matters more than task order

Subtraction is not associative:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Therefore, do not treat `reduce(0, (a, b) -> a - b)` as a valid parallel aggregation. Changing how elements are split and merged can change the result. Algorithms that depend on previous state or step-by-step order may fit a sequential loop or a dedicated stateful construct better.

## 6. Thread confinement via `collect`: mutable inside, right result

A non-concurrent collector can use a mutable `ArrayList` as its accumulation state because the framework manages container creation and merging. This is a concrete example of **confinement within an accumulation scope**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

record Product(String sku, long priceVnd) {}

Collector<Product, ArrayList<String>, List<String>> skuCollector =
    Collector.of(
        ArrayList::new,                      // supplier: dedicated container
        (list, product) -> list.add(product.sku()),
        (left, right) -> {                   // combiner: merges two containers
            left.addAll(right);
            return left;
        },
        List::copyOf                         // finisher: unmodifiable result
    );

List<Product> products = List.of(
    new Product("P-01", 100_000L),
    new Product("P-02",  60_000L),
    new Product("P-03",  80_000L)
);

List<String> skus = products.parallelStream()
    .collect(skuCollector);

System.out.println(skus); // [P-01, P-02, P-03]
```

Although `ArrayList` is not thread-safe for concurrent `add` calls from multiple threads, the collector above **does not declare `CONCURRENT`** and relies on the collector contract so temporary containers are never concurrently accumulated into unsafely. The combiner merges containers and the finisher produces an immutable copy.

For the simple case of extracting SKUs, a built-in collector is shorter and clearer:

```java
List<String> skus = products.parallelStream()
    .map(Product::sku)
    .toList();
```

**Lesson to learn:** Not all mutable state is wrong. Mutable state **owned by the framework, clearly scoped, and combined properly** is a valid pattern. Mutable state **outside the pipeline mutated directly by multiple tasks** is the common source of bugs.

### 6.1. Roles of the four Collector components

| Component | Role in parallel execution | Risk if written incorrectly |
| --- | --- | --- |
| `supplier` | Creates an initial container; multiple containers may be created | Returning a shared mutable singleton |
| `accumulator` | Adds an element to the assigned container | Concurrently writing to another container or external variable |
| `combiner` | Merges partial results | Dropping elements, double-merging, or wrong order |
| `finisher` | Converts container into the final result type | Exposing a mutable reference when an immutable result is expected |

Do not arbitrarily put a fixed surcharge, non-zero initial counter, or external data inside the supplier: in a parallel pipeline, containers can be created multiple times, causing the initial value to be counted repeatedly.

## 7. `groupingBy` and `groupingByConcurrent`: same goal, different contracts

Counting and summing by region is a common example of grouped accumulation state.

```java
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

Map<String, Long> grouped = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));

ConcurrentMap<String, Long> concurrentGrouped = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

| Collector | View of state | Ordering |
| --- | --- | --- |
| `groupingBy` | May create multiple partial Maps/containers and merge them | Does not guarantee Map key iteration order by default; downstream may still preserve value order |
| `groupingByConcurrent` | A `CONCURRENT` and `UNORDERED` collector; supports concurrent accumulation into a `ConcurrentMap` when applicable | Does not maintain encounter order as a result requirement |

A common misconception: `Collectors.summingLong(...)` or `Collectors.toList()` **are not standalone concurrent collectors**. Yet when used as a downstream of `groupingByConcurrent`, the implementation must coordinate accumulation calls as needed to uphold the combined collector's contract; do not assume downstream will be invoked concurrently without protection on the same `ArrayList`.

Still, do not replace all `groupingBy` calls with `groupingByConcurrent`. If data concentrates on very few keys, contention can be high; if element order inside each group matters, an unordered collector may be unsuitable.

### 7.1. `Spliterator.CONCURRENT` differs from `Collector.Characteristics.CONCURRENT`

- `Spliterator.CONCURRENT` states that the **source** supports concurrent modification during traversal under a specific contract.
- `Collector.Characteristics.CONCURRENT` states that the **accumulator** may be called concurrently on **the same result container** under the collector's contract.

The two flags belong to two different layers of responsibility. A concurrent source does not make a shared `ArrayList` in `forEach` safe; a concurrent collector does not automatically make any custom source safe to mutate during traversal.

## 8. Should you use `AtomicInteger`, `LongAdder`, or locks?

Synchronization primitives are useful when a problem **genuinely needs shared state**. In Stream pipelines, however, they are rarely the first choice for counting or summing.

### 8.1. `AtomicInteger` and `AtomicLong`

`AtomicInteger.incrementAndGet()` is an atomic increment. The following example has no data race on the increment itself:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger counter = new AtomicInteger();

IntStream.range(0, 1_000)
    .parallel()
    .forEach(n -> counter.incrementAndGet());

System.out.println(counter.get()); // 1000
```

In this simple example, terminal `forEach` processes each element and updates atomically. Yet if the goal is **only counting**, the code is cleaner as:

```java
long count = IntStream.range(0, 1_000)
    .parallel()
    .count();

System.out.println(count); // 1000
```

`AtomicInteger` solves **atomicity of a single operation**, not correctness of an entire business flow. Specifically, when concurrently updating multiple fields (e.g., `count` and `total`), two separate `AtomicLong` instances do not form a **consistent snapshot** of both fields if a reader observes them mid-update.

### 8.2. `LongAdder`: reducing contention does not mean replacing a Collector

`LongAdder` is useful for counters under heavy concurrent updates. Example:

```java
import java.util.concurrent.atomic.LongAdder;

LongAdder processed = new LongAdder();

orders.parallelStream().forEach(order -> {
    // Suppose real work needs a telemetry counter:
    processed.increment();
});

System.out.println(processed.sum());
```

`LongAdder.sum()` is not an atomic snapshot while threads are still updating. Once a synchronous terminal operation finishes, you can read it for observability; for direct business statistics from a Stream, `count()` or an appropriate collector is easier to verify.

A telemetry counter differs in purpose from **the pipeline's output product**. Do not rely on a shared counter for approval logic when the result can be expressed purely with Streams.

### 8.3. `Collections.synchronizedList`

A synchronized list can make individual `add` calls safer:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<Integer> synchronizedResult =
    Collections.synchronizedList(new ArrayList<>());

IntStream.range(0, 1_000)
    .parallel()
    .forEach(synchronizedResult::add);

System.out.println(synchronizedResult.size()); // 1000
```

However, **element order in the list is no longer encounter order**: tasks processing smaller indices may call `add` after other tasks. Furthermore, compound operations like check-then-add need extra synchronization, and all threads contending on the same lock add overhead.

If you need a `List<Integer>` in encounter order, use `boxed().toList()` or a built-in collector; only use a synchronized list outside the pipeline when a specific requirement cannot be expressed cleanly as a collection step.

## 9. `ThreadLocal`: not a data aggregation mechanism

`ThreadLocal<T>` provides a separate value per **execution thread**. It is helpful in certain per-thread state contexts, yet easily misused in parallel Streams.

Wrong mental model example:

```java
import java.util.concurrent.atomic.AtomicInteger;

ThreadLocal<Integer> localCount = ThreadLocal.withInitial(() -> 0);

orders.parallelStream().forEach(order ->
    localCount.set(localCount.get() + 1)
);

// localCount.get() on the outer calling thread is NOT the sum across all threads.
System.out.println(localCount.get());
```

Each worker thread has its own value. `ThreadLocal` **has no mechanism to automatically merge values** into a final total; furthermore, different tasks may be scheduled onto the same thread in ways the application does not control.

There is also a lifecycle risk: pool threads can be **reused for other work**. If `ThreadLocal` state is retained improperly, it can leak data or affect subsequent tasks. When you genuinely must use `ThreadLocal`, establish clear setup and cleanup with `remove()` in `finally`, and avoid misusing it to pass data across Stream stages.

A better approach for aggregating data is a **collector with state isolated per accumulation scope**, not counting by thread ID. Collectors know how to create containers, combine, and finish results; `ThreadLocal` does not replace those contracts.

## 10. `forEach`, `forEachOrdered`, and ordering guarantees

A source having encounter order does not mean all side effects run in that order when parallel.

```java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 5)
    .parallel()
    .forEach(System.out::print);

// May print digits in an order other than 12345.
```

`forEach` intentionally does not guarantee element processing order. If you need actions to execute in encounter order:

```java
IntStream.rangeClosed(1, 5)
    .parallel()
    .forEachOrdered(System.out::print);

// Prints 12345 for an ordered source.
```

`forEachOrdered` guarantees actions execute in encounter order on an ordered Stream, and the action for one element happens-before the action for the next element per method semantics. However, **it does not guarantee every action runs on the same thread**; nor does it make a mutable source or prior side effects thread-safe.

More importantly: if the goal is **creating an ordered list**, do not use `forEachOrdered` to add elements to an external container when `toList()` solves the problem directly. `forEachOrdered` can require extra coordination and reduce parallel benefits when executing mandatory sequential side effects.

### 10.1. `findAny` vs. `findFirst`

`findAny()` may return any matching element; this is especially helpful when order is unnecessary and you want to permit parallel optimization. `findFirst()` must obey encounter order if the source is ordered, which can incur coordination overhead.

Do not use the result of `findAny()` to assert "the first record" of an ordered dataset.

## 11. Short-circuiting and Stream optimizations make side effects unpredictable

Some operations do not need to traverse the entire source:

- `anyMatch` stops once a matching element is found.
- `allMatch` stops once a non-matching element is found.
- `findFirst` or `findAny` stops once a qualifying element is available.
- `limit(n)` may forward at most `n` elements downstream.

Additionally, implementations may optimize away intermediate stages when the terminal operation's result remains valid. For example, `count()` on a sized source may **skip calling `peek` altogether**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger visits = new AtomicInteger();

long size = IntStream.range(0, 1_000)
    .parallel()
    .peek(n -> visits.incrementAndGet())
    .count();

System.out.println(size); // 1000

// visits == 1000 is not guaranteed; peek may never be called.
```

`AtomicInteger` makes the counter safe if `peek` is called, yet **does not force Stream to call peek**. `peek` is suited for debugging observation within appropriate limits, not for executing mandatory business steps.

Similarly, a `Predicate` with side effects may be called a different number of times and in a different order on a parallel Stream. If you need to count how many records truly match a condition, use `filter(predicate).count()` with a pure predicate.

## 12. Complete Java 17 example: parallel-safe order report

The example below uses `record` and Java 17+ APIs. It demonstrates three independent results produced **without mutating state outside the pipeline**:

1. Total paid revenue via `mapToLong(...).sum()`.
2. Total revenue by region via `groupingBy(..., summingLong(...))`.
3. List of paid order IDs in encounter order via `map(...).toList()`.

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ParallelStreamStateDemo {

    record Order(String id, String region, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "Bắc", 120_000L, true),
            new Order("O-02", "Nam",  60_000L, false),
            new Order("O-03", "Bắc",  80_000L, true),
            new Order("O-04", "Nam", 200_000L, true),
            new Order("O-05", "Trung", 50_000L, true)
        );

        long revenue = orders.parallelStream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .sum();

        Map<String, Long> byRegion = orders.parallelStream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.summingLong(Order::amountVnd)
            ));

        ConcurrentMap<String, Long> concurrentByRegion =
            orders.parallelStream()
                .filter(Order::paid)
                .collect(Collectors.groupingByConcurrent(
                    Order::region,
                    Collectors.summingLong(Order::amountVnd)
                ));

        List<String> paidIds = orders.parallelStream()
            .filter(Order::paid)
            .map(Order::id)
            .toList();

        long paidCount = orders.parallelStream()
            .filter(Order::paid)
            .count();

        System.out.println(revenue);              // 450000
        System.out.println(byRegion.get("Bắc"));   // 200000
        System.out.println(byRegion.get("Nam"));   // 200000
        System.out.println(byRegion.get("Trung")); // 50000
        System.out.println(concurrentByRegion.get("Bắc")); // 200000
        System.out.println(paidIds);              // [O-01, O-03, O-04, O-05]
        System.out.println(paidCount);            // 4
    }
}
```

Each call to `orders.parallelStream()` creates **a new Stream**. A Stream cannot be reused after a terminal operation. In this example, `Order` has immutable fields via its record structure; lambdas only read data and aggregate. No `ArrayList` or `HashMap` outside the pipeline is concurrently mutated by multiple tasks.

Both Map results contain the same totals per group, yet **there is no guarantee they share the same Map implementation type or key iteration order**. Do not rely on `Map.toString()` or default `keySet()` ordering in tests. `paidIds` preserves the `List` source's encounter order, because `Stream.toList()` returns elements in encounter order when the Stream is ordered.

**Arithmetic limits:** `summingLong` and `sum()` can still overflow `long` if the sum exceeds 64-bit range. When exact integer sums unbounded by `long` are needed, switch to `BigInteger` and reduce with `BigInteger::add`; parallel processing does not automatically widen numeric ranges.

## 13. Performance: avoid turning synchronization into a bottleneck

A pipeline can be thread-safe yet slower than sequential execution because:

- Creating tasks and splitting via `Spliterator` incurs overhead.
- Multiple tasks updating the same `AtomicLong`, `synchronizedList`, or hot key in `ConcurrentHashMap` cause contention.
- `forEachOrdered` must maintain encounter order.
- `groupingBy` needs a combiner to merge Maps; `groupingByConcurrent` can suffer contention on hot keys.
- Boxing from `int` to `Integer` can add unnecessary cost.
- I/O sources or small datasets lack enough compute work to offset parallel overhead.

You can use `IntStream`, `LongStream`, and `DoubleStream` to avoid boxing on pure numeric tasks. For custom sources, `trySplit()` quality and characteristics `SIZED`, `SUBSIZED`, and `ORDERED` heavily shape splittability. Still, do not write a complex custom Spliterator when standard sources suffice.

### How to evaluate performance sensibly

1. First verify sequential and parallel outputs **using the same data and business rules**.
2. Use representative data, multiple runs, and an appropriate benchmark tool such as JMH.
3. Inspect group key distribution, element count, mapper/accumulator cost, and synchronization wait ratios.
4. Measure time, throughput, CPU, memory, and allocation rate as needed.
5. Choose parallel only if the improvement is substantial and does not complicate correctness or operations.

**Thread safety is a necessary condition, not a guarantee of speed.**

## 14. Special cases: concurrent sources, I/O, and resources

Some sources support concurrent reads or updates during traversal under specific contracts, such as concurrent collections. Yet that property does not grant permission to arbitrarily mutate the source inside `map` or `filter`.

For sources from `Files.lines(path)`, `Files.walk(path)`, or APIs holding external resources, closing responsibility remains with the Stream/resource owner, **whether running sequentially or in parallel**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countErrors(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.parallel()
            .filter(line -> line.contains("ERROR"))
            .count();
    }
}
```

`count()` does not replace `close()`; `try-with-resources` guarantees resource closure upon leaving the block, even if the pipeline throws an exception. Do not enable parallel execution just because a file has many lines: I/O, splitting, decoding, and contention can make it slower.

If the source is a custom `Spliterator`, clearly determine whether it is safe to split, whether sub-parts after `trySplit()` share any mutable references, and whether `CONCURRENT`/`IMMUTABLE` characteristics are declared accurately.

## 15. Common pitfalls

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| `parallelStream().forEach(sharedArrayList::add)` | Data race, missing/corrupted elements | `map(...).toList()` or `collect(...)` |
| `parallelStream().forEach(n -> hashMap.merge(...))` | `HashMap` is unsafe under concurrent updates | `groupingBy` or `groupingByConcurrent` |
| Thinking `AtomicInteger` makes any side-effecting lambda valid | Only safe per atomic op, does not guarantee lambda invocation count | Use `count()`/`sum()`/collectors for their intended purpose |
| Using `peek` to increment a mandatory counter | Stage may be skipped when terminal operation optimizes | Do not put business logic in `peek` |
| Using `ThreadLocal` to sum across workers | Values are never merged automatically; threads can be reused | Use a collector with supplier/combiner |
| Returning a shared singleton `ArrayList` in collector supplier | Multiple branches share state unsafely | Supplier must return a fresh container each call |
| Using `reduce` mutating a shared mutable identity container | Violates reduction contract and may share across tasks | Use immutable combining or `collect` |
| Using subtraction as accumulator for parallel reduce | Not associative, depends on grouping | Use an associative operation or a different algorithm |
| Assuming `forEach` preserves encounter order | Side effects occur in non-deterministic order | Use `forEachOrdered` when ordered actions are required; prefer `toList` |
| Assuming `forEachOrdered` forces all actions onto one thread | Confuses ordering guarantee with thread affinity | Do not tie state to thread ID |
| Thinking `groupingByConcurrent` preserves per-group element order | Unordered collector | Choose an order-preserving approach if business requires order |
| Thinking `Spliterator.CONCURRENT` makes any collector safe | Confuses source contract and accumulator contract | Evaluate each contract separately |
| Thinking `parallel()` speeds up and prevents overflow | Overhead can be high; numeric range does not widen | Measure performance, choose valid numeric types |
| Forgetting to close I/O sources after terminal operation | Resource leak | `try-with-resources` at the resource owner |
| Mutating a mutable object referenced by multiple elements | Data race even with an immutable source collection | Transform into new values or protect ownership |

## 16. Practice exercises

### Exercise 1: Fixing a shared mutable list

Given an `ArrayList<Integer>` outside the pipeline, the code uses `IntStream.range(0, 100_000).parallel().forEach(list::add)`. Rewrite it into a `List<Integer>` using `boxed().toList()` and explain why `synchronizedList` is unnecessary.

### Exercise 2: Counting and summing by region

Given a list of `Order(region, amountVnd, paid)`. Write two pipelines producing `Map<String, Long>` of total paid revenue using `groupingBy` and `groupingByConcurrent`. Compare key results, not Map print order.

### Exercise 3: When to use `AtomicInteger`?

Create two programs counting from 0 to 1 million: one using `AtomicInteger` inside `parallel().forEach`, and one using `count()`. State the differences in atomic safety, business intent, and contention cost.

### Exercise 4: Catching a `peek` bug

Use `IntStream.range(0, 100).peek(...)` with an Atomic counter and terminal `count()`. May you assume `peek` always runs 100 times? Explain why optimizations are permitted to alter intermediate stage invocation counts.

### Exercise 5: Stateful yet safe Collector

Write a `Collector<Product, ArrayList<String>, List<String>>` with supplier `ArrayList::new`, accumulator adding SKU, combiner concatenating lists, and finisher `List.copyOf`. Run sequentially and in parallel on an ordered source; explain why `ArrayList` itself does not need to be thread-safe in this design.

### Exercise 6: `ThreadLocal` does not auto-merge

Describe a `parallelStream` pipeline using `ThreadLocal<Integer>` as a counter. Why does reading `threadLocal.get()` on the outer calling thread not give the total? What risks arise when worker threads are reused by a pool?

### Exercise 7: Ordering and performance

Compare `forEach`, `forEachOrdered`, and `toList` on `IntStream.range(0, 100).parallel()`. For building an ascending list, which approach is most direct and safe? When is `forEachOrdered` the necessary choice?

### Exercise 8: Shared data inside the source

Given a `List<Counter>` containing two positions referencing the same mutable `Counter` object. If each task executes `counter.value++`, is the result reliable? Rewrite into a read-only pipeline summed with `mapToInt(...).sum()`, noting the requirement that input data remain stable during reading.

### Exercise 9: Correctness before optimization

Create a dataset with many orders but only two group keys. Predict the difference between `groupingBy` and `groupingByConcurrent` regarding Map merge cost and contention; design a JMH benchmark instead of measuring once and concluding.

## 17. Knowledge self-check

- Why are `ArrayList.add` or `HashMap.merge` on a container outside the pipeline unsafe with `parallelStream`?
- What are the differences between data race, thread confinement, and thread safety?
- Why can mutable state inside a non-concurrent collector still be used safely in parallel execution?
- Why must a Collector's Supplier never return a shared mutable singleton?
- Does `AtomicInteger` make `peek` a guaranteed business step that must execute?
- Does `ThreadLocal` automatically aggregate data across multiple tasks into one result?
- What does `forEachOrdered` guarantee, and what does it **not** guarantee about threads?
- Why is `groupingByConcurrent` not necessarily faster than `groupingBy` when there are few group keys?
- How does `Spliterator.CONCURRENT` differ from `Collector.Characteristics.CONCURRENT`?
- When can a `reduce` with a side effect fail even when the side effect uses an atomic class?
- Why must you verify correctness, ordering, I/O resources, and numeric precision before enabling `parallel()`?

**Takeaway:** With parallel Streams, **keep element-processing lambdas stateless and non-interfering**, avoid writing to shared mutable state, and let **`reduce`/`collect` manage aggregation**. Thread confinement of temporary collector containers and thread safety of concurrent structures are two distinct mechanisms; both must be used according to their contracts. Tools like `AtomicInteger`, `LongAdder`, `ThreadLocal`, and `forEachOrdered` do not replace Stream's pure result-expressing power, nor do they automatically guarantee better performance.