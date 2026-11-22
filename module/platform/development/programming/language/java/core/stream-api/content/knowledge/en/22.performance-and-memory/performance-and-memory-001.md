# Understanding Pipeline Fusion, Laziness, and Object Creation Cost

## 1. Why does the same processing operation have different costs?

The Java Stream API lets you describe data processing using a **pipeline**: a data source (*source*), intermediate operations (*intermediate operations*), and a terminal operation (*terminal operation*). Declarative syntax such as `filter`, `map`, `reduce`, and `collect` helps you focus on the result to compute. However, to evaluate performance and memory usage, you need to understand **when the pipeline actually runs, how it traverses elements, and what objects it creates**.

For example, given a list of orders, the requirement “compute the total value of paid orders” can be written with `filter(...).mapToLong(...).sum()`. This pipeline typically needs only a single pass over the elements, without creating a result list after each operation. Conversely, `sorted()` may have to hold many elements in memory before passing results to the next step. For the same problem, using `Stream<Long>` versus `LongStream` also affects the likelihood of boxing.

After this lesson, you will be able to distinguish:

- **Pipeline fusion**: stateless intermediate steps are typically combined in a single traversal pass.
- **Lazy evaluation**: element processing is deferred until a terminal operation is invoked, and it can stop early.
- **Object cost**: pipeline setup cost, boxing/unboxing, application object creation, and result storage are distinct sources of cost.

> Scope: examples use Java 17 or later for `record`, `List.of()`, and `Stream.toList()`. The core pipeline principles of the Stream API also apply to many earlier JDK versions; check specific APIs against the version you are using.

## 2. Pipeline fusion: one pass, multiple processing steps

Consider a sequential pipeline:

```java
List<Integer> result = List.of(1, 2, 3, 4, 5, 6).stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10)
    .toList();

System.out.println(result); // [20, 40, 60]
```

A common misconception is that `filter()` creates a list `[2, 4, 6]`, and then `map()` traverses that list again to produce `[20, 40, 60]`. With a sequential pipeline made of **stateless** intermediate operations, Stream typically passes each element through successive steps in the same pass over the source:

```text
Source: 1 ─→ filter (reject)
        2 ─→ filter (keep) ─→ map (20) ─→ result
        3 ─→ filter (reject)
        4 ─→ filter (keep) ─→ map (40) ─→ result
        5 ─→ filter (reject)
        6 ─→ filter (keep) ─→ map (60) ─→ result
```

This is the practical mental model of **pipeline fusion**: Stream coordinates the steps so it does not have to create an intermediate collection for every `filter()` or `map()`. In a simple sequential pipeline, an element can pass through `filter`, `map`, and be consumed by the terminal operation before the next element is processed.

**Fusion does not mean “zero cost”.** The Stream object itself, stages, lambdas, method invocation mechanisms, and the final result still have potential costs. In particular, `map(x -> new Dto(...))` can still create a DTO for every element passing through `map`, even though no intermediate list is created. The JVM/JIT may optimize away some allocations under suitable conditions, but you should not assume they will disappear.

### Demonstrating processing order with logging

The following code uses logging **only to observe** the execution order of a sequential pipeline:

```java
OptionalInt first = IntStream.rangeClosed(1, 6)
    .filter(n -> {
        System.out.println("filter " + n);
        return n % 2 == 0;
    })
    .map(n -> {
        System.out.println("map " + n);
        return n * 10;
    })
    .findFirst();

System.out.println(first); // OptionalInt[20]
```

The log order in the sequential example is:

```text
filter 1
filter 2
map 2
OptionalInt[20]
```

There is no `map 4` or `map 6`: `findFirst()` has found the first result and can terminate the pipeline early. If the Stream runs in parallel, work splitting and observed order may differ; do not use this sequential log example to infer the execution order of `parallelStream()`.

## 3. Laziness: describe first, execute later

`filter`, `map`, `flatMap`, `distinct`, `sorted`, and many intermediate operations return a new Stream to chain the pipeline. They **do not traverse or process elements when declared**. Traversal typically begins when calling a terminal operation such as `sum`, `count`, `findFirst`, `forEach`, `reduce`, `collect`, or `toList`.

```java
Stream<Integer> pipeline = Stream.of(1, 2, 3, 4)
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10);

System.out.println("Pipeline created");

List<Integer> numbers = pipeline.toList(); // Starts processing elements
System.out.println(numbers);                // [20, 40]
```

When creating `pipeline`, the program still needs to build the structures representing the pipeline and acquire the data source. “Lazy” here refers to **when elements are processed**, not that every operation is free until the terminal operation.

A Stream may only be used for **one consumption**. After `toList()`, do not call `sum()`, `count()`, or another terminal operation on the same `pipeline`; create a new pipeline from the source if you need to compute another result.

### Stopping early with short-circuiting

Some terminal operations only need to process part of the data:

| Operation | Condition under which it can stop |
| --- | --- |
| `findFirst()` | Found the first element according to encounter order, if ordered. |
| `findAny()` | Found any element; especially useful when order does not need to be preserved. |
| `anyMatch(...)` | Encountered an element matching the condition. |
| `allMatch(...)` | Encountered an element not matching the condition. |
| `noneMatch(...)` | Encountered an element matching the condition. |
| `limit(n)` | An intermediate operation that can stop pulling more elements once `n` elements reach downstream, depending on the pipeline. |

Example:

```java
boolean hasNegative = IntStream.of(5, 8, -3, 12, 20)
    .anyMatch(n -> n < 0);

System.out.println(hasNegative); // true
```

With a sequential pipeline and the source above, `anyMatch()` can terminate upon encountering `-3`, without needing to examine `12` and `20`. In a parallel pipeline, tasks already started may process additional elements before cancellation propagates to them.

### Do not rely on side effects of intermediate operations

Stream allows implementations to optimize without **necessarily invoking every behavior attached to an intermediate operation**, as long as the terminal operation result is preserved. For example, with a sized source:

```java
long count = List.of("a", "b", "c").stream()
    .map(s -> {
        System.out.println("map: " + s);
        return s.toUpperCase();
    })
    .count();

System.out.println(count); // 3
```

The JDK can compute `count()` directly from the source size, skipping execution of `map()` because this transformation does not change the element count. Therefore, **do not use `map`, `filter`, or `peek` to perform required business logic with side effects** (writing to a database, updating shared variables, sending notifications…). `peek` is suitable for observation while debugging, but it is also not guaranteed to be called for every element.

## 4. When is fusion limited?

Not every intermediate operation can immediately pass each element to the next step. In particular, **stateful** operations may need to inspect multiple elements or store state before emitting results.

| Operation | Execution characteristic | Potential implication |
| --- | --- | --- |
| `filter`, `map`, `mapToInt`, `mapToLong` | Stateless; typically processes one element at a time. | Usually needs no intermediate collection; lambdas or objects created in `map` still have cost. |
| `flatMap` | Emits elements from multiple sub-streams. | Has cost of creating/closing sub-streams or related structures. |
| `sorted()` | Must know the sort order of the elements to sort. | Usually needs to buffer the entire finite input before emitting ordered results. |
| `distinct()` | Must recognize previously seen elements. | May need a set-like structure to remember values, depending on source characteristics and execution mode. |
| `limit(n)`, `skip(n)` | Stateful with respect to element count; `limit` can stop early. | Cost depends on encounter order, position in the pipeline, and parallel execution. |
| `collect(toList())`, `toList()` | Accumulating terminal operation. | Needs memory for the resulting collection; does not create a collection after *every* intermediate step. |
| `sum()`, `count()`, `reduce(...)` | Aggregating terminal operation. | May not need to store all elements; cost depends on the accumulator and execution mode. |

### The position of `sorted()` and `limit()` changes meaning

```java
List<Integer> smallestTwo = Stream.of(9, 2, 7, 1, 5)
    .sorted()
    .limit(2)
    .toList();
// [1, 2]: gets the 2 smallest numbers in the entire source

List<Integer> firstTwoSorted = Stream.of(9, 2, 7, 1, 5)
    .limit(2)
    .sorted()
    .toList();
// [2, 9]: only sorts the first 2 elements of the source
```

Moving `limit()` before `sorted()` can reduce the number of elements that must be buffered, **but it changes the result**. Only change the order when business semantics allow it. Similarly, filtering data before `sorted()` usually reduces the amount to sort if `filter()` does not alter the selection condition.

With an infinite source, `Stream.generate(...).sorted().findFirst()` may never terminate because `sorted()` needs to consume all data before picking the first element. A finite bound placed **before** `sorted()` can let the pipeline finish, provided it fits the problem.

## 5. Sources of memory and object creation cost

To avoid wrong conclusions like “Stream always creates many objects” or “fusion creates zero objects”, separate the cost categories:

1. **Pipeline setup:** the Stream source, stages, execution machinery, and lambdas/captures may require allocation. For small datasets and very simple operations, this cost can be significant compared to the actual work.
2. **Per-element object creation:** `map(order -> new Summary(...))`, string concatenation, creating `Optional`/sub-collections, or data conversions can allocate objects proportional to the number of processed elements.
3. **Boxing/unboxing:** reference streams such as `Stream<Integer>` or `Stream<Long>` can create wrappers and increase memory access overhead compared to `IntStream`, `LongStream`, `DoubleStream`.
4. **State and result storage:** `sorted`, `distinct`, `groupingBy`, `toList`, and certain collectors may require memory proportional to the number of elements or groups.
5. **GC pressure and temporary memory:** short-lived objects can still cause garbage collection pressure; the impact depends on workload and JVM optimizations.

### Avoiding boxing when working primarily with numbers

Suppose we have an order type:

```java
record Order(String code, boolean paid, long amount) {}

List<Order> orders = List.of(
    new Order("A01", true, 1_200_000L),
    new Order("A02", false, 400_000L),
    new Order("A03", true, 500_000L)
);

long revenue = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amount)
    .sum();

System.out.println(revenue); // 1700000
```

`mapToLong()` switches to `LongStream`, so monetary values in the summation phase are represented as primitive `long`. Compare this with a version that can cause boxing:

```java
Long revenueBoxed = orders.stream()
    .filter(Order::paid)
    .map(Order::amount)        // Stream<Long>
    .reduce(0L, Long::sum);   // Involves boxing/unboxing steps
```

Both produce the same value in the example, but the reference Stream type creates additional opportunities for wrapper allocations. In practice, the JIT may eliminate some allocations; **do not deduce the exact number of objects merely by counting `map` calls**. If the input data is already a `List<Long>`, the wrappers already in the list still exist even when using `mapToLong(Long::longValue)`.

### Distinguishing scalar results from DTO lists

```java
record Summary(String code, long amount) {}

List<Summary> summaries = orders.stream()
    .filter(Order::paid)
    .map(order -> new Summary(order.code(), order.amount()))
    .toList();
```

Here fusion avoids an intermediate list containing only paid orders, while `new Summary(...)` creates result objects and `toList()` stores them for later use. That is a **reasonable cost if the application genuinely needs the Summary list**. If only the total is needed, `mapToLong(...).sum()` is usually more appropriate because there is no need to retain a DTO per order.

`Stream.toList()` (available since Java 16) returns a list that does not allow modification via operations like `add`/`remove`. Do not confuse it with `Collectors.toList()`, which makes no specific guarantees about implementation type, mutability, or other characteristics of the returned list.

### Estimating complexity, not confusing it with benchmarking

With `n` input elements, `k` elements passing the filter, and `u` distinct values, you can use these estimates for design:

| Typical pipeline | Typical time | Notable additional memory |
| --- | --- | --- |
| `filter(...).mapToLong(...).sum()` | `O(n)` | Typically `O(1)` for aggregation in sequential execution, aside from pipeline infrastructure. |
| `filter(...).map(...).toList()` | `O(n)` | `O(k)` for the result, plus objects created by `map`. |
| `sorted().toList()` | `O(n log n)` when general sorting is needed | Typically `O(n)` to hold sorted data and result. |
| `distinct().toList()` | Typically near `O(n)` with efficient hashing | Typically depends on `u`, plus space for the result. |

These figures describe tendencies, **not guarantees of pass count, peak memory, or absolute performance**. Source characteristics (`SIZED`, `DISTINCT`, `SORTED`...), operations, encounter order, JDK version, and parallel execution can all change the execution strategy.

## 6. Comparing Stream and loops in real-world problems

The revenue calculation pipeline above has an equivalent loop version:

```java
long revenue = 0L;
for (Order order : orders) {
    if (order.paid()) {
        revenue += order.amount();
    }
}
```

Both represent a single `O(n)` pass and require no intermediate list. A loop can avoid some pipeline setup overhead, especially in very short code executed very frequently. Stream has the advantage of clearly expressing transformations and composing easily with collectors and aggregation operations.

There is no universal rule that loops are always faster than Streams or that Streams are always optimized by the JVM into the same machine code as loops. Decisions should be based on **readability, semantics, and measurements in the real environment**.

### Notes when switching to parallel streams

`parallelStream()` can split the source into parts for parallel processing, then merge the results. It does not automatically improve performance: splitting work, synchronization, merging, preserving order, and stateful operations like `sorted` or `distinct` all have their own overhead. `findFirst()` on an ordered source can require more coordination than `findAny()` when the first element is not needed. Shared side effects across tasks also risk contention and data corruption.

For small sources, lightweight per-element work, or strict ordering requirements, a sequential pipeline is usually a reasonable starting point. Only evaluate parallel execution when the work is large enough, separable, and measurements prove a benefit.

## 7. Measure actual cost instead of guessing

A one-off `System.nanoTime()` benchmark is easily skewed by JVM startup, JIT compilation, GC, and machine noise. To compare soundly:

1. **Define the workload:** input size, filter pass rate, DTO size, lambda complexity, duplication rate, and order preservation requirements.
2. **Compare equivalent algorithms:** same data, same output, and same semantics; do not compare `sorted().limit(10)` with `limit(10).sorted()` if the requirement is “the 10 smallest values overall”.
3. **Benchmark with warmup:** use JMH to reduce JIT skew, run multiple iterations, and ensure results are not optimized away because they are unused.
4. **Measure allocations and GC:** combine JFR/JDK Mission Control, a profiler, or allocation statistics to see whether cost comes from pipeline setup, boxing, DTOs, or collectors.
5. **Test under realistic conditions:** large and small datasets, realistic heap sizing, the target JDK, and concurrent load if the application serves many requests.

A meaningful experiment is to benchmark these three ways of computing the sum on the same set of `Order`s: a `for` loop, `stream().filter(...).mapToLong(...).sum()`, and `stream().filter(...).map(...).reduce(...)`. Measure **both throughput/latency and allocated bytes/op**; conclusions hold only within the tested configuration and data.

## 8. Common thinking traps

| Hasty claim | Accurate understanding |
| --- | --- |
| “With three `map`/`filter` calls, data is traversed three times.” | For stateless stages in a sequential pipeline, Stream typically combines them into a single traversal pass. |
| “Streams are lazy so they create no objects.” | Pipeline initialization, lambdas, boxing, DTOs, and results can still allocate. |
| “`count()` always calls every `map`/`peek`.” | The JDK can infer the size and skip stages that do not affect the result. |
| “Moving `limit` earlier is always better.” | It can reduce work but changes semantics, especially alongside `sorted`, `skip`, or ordered processing. |
| “`parallelStream()` is always faster.” | You must account for splitting, merging, state, and ordering overhead; you must measure. |
| “`mapToLong` eliminates all wrappers.” | It avoids boxing in the primitive pipeline segment, but does not remove objects already existing in the source. |

## 9. Practice exercises

**Exercise 1 — Predict lambda invocation count.** For the following sequential pipeline, predict the log order and explain why:

```java
List<Integer> result = IntStream.rangeClosed(1, 10)
    .filter(n -> {
        System.out.println("F " + n);
        return n % 3 == 0;
    })
    .map(n -> {
        System.out.println("M " + n);
        return n * n;
    })
    .limit(2)
    .boxed()
    .toList();

System.out.println(result);
```

*Verification hint:* `limit(2)` receives two elements passing the filter, `3` and `6`; the result is `[9, 36]`. Compare this with placing `limit(2)` before `filter`.

**Exercise 2 — Memory-efficient design.** A system has millions of `Order`s and only needs the total amount of paid orders. Compare (a) `filter` then `map` into `List<Summary>` then summing, and (b) `filter` then `mapToLong().sum()`. Identify which part in option (a) uses memory proportional to the number of valid orders and when a Summary list is still a required output.

**Exercise 3 — Check operation ordering.** Try writing `sorted().limit(5)` and `limit(5).sorted()` on a set of numbers whose input order is not ascending. Describe the business requirement each pipeline implements, then use JMH to evaluate performance as source size grows.

When optimizing a Stream API pipeline, answer these in order: **Do we need to process the entire source? Which step must keep state? Does the output need to be a collection or just a single value? Are wrappers or DTOs being created? Have we measured on a real workload?** These five questions are usually more useful than just counting `map` and `filter` calls in the source code.
