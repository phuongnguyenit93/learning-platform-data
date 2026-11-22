# Understanding the Split, Process, and Combine Model

## 1. Lesson objectives

In the **`JAVA_STREAM_API`** module, the Stream API lets you describe declarative pipelines: creating a source, chaining lazy intermediate steps such as `filter`, `map`, and `flatMap`, and finishing with `reduce`, `collect`, or an aggregation operation. With sufficiently large data and suitable operations, you can ask Java to process the pipeline in **parallel** mode.

However, `parallel()` **does not mean one element is assigned to a dedicated thread**, and `parallelStream()` **does not guarantee faster execution** than a sequential stream. To understand both semantics and performance, you need to grasp three conceptual stages:

1. **Split:** partition the source into work chunks that can be processed independently.
2. **Process:** pass each element through the operations in the pipeline.
3. **Combine:** merge local results to complete the terminal operation.

After this lesson, you will be able to:

- Explain the role of `Spliterator.trySplit()` in partitioning data.
- Distinguish work chunks, execution threads, and *encounter order*.
- Read how data is reduced with `reduce`, accumulated with `collect`, and combined.
- Understand why `identity`, *associativity*, and `combiner` determine correctness in parallel execution.
- Identify bugs caused by side effects, shared state, or false ordering assumptions.
- Verify result correctness first, and only then consider performance measurement.

This lesson belongs to the **Parallel Processing Semantics** chapter, serving as a foundation for `Spliterator`, custom collectors, grouping, statefulness, and resource limits.

## 2. Visualizing the three stages on a pipeline

Consider computing the sum of squares of eight numbers:

```java
import java.util.stream.LongStream;

public class ViDuTongBinhPhuong {
    public static void main(String[] args) {
        long tong = LongStream.rangeClosed(1, 8)
            .parallel()
            .map(n -> n * n)
            .sum();

        System.out.println(tong); // 204
    }
}
```

Mathematically:

```text
1² + 2² + 3² + 4² + 5² + 6² + 7² + 8² = 204
```

One **possible way to visualize** the split:

```text
                Source: 1 2 3 4 5 6 7 8
                           |
                         SPLIT
                ___________|___________
               /                       \
           1 2 3 4                   5 6 7 8
          /       \                 /       \
         1 2      3 4             5 6      7 8
          |        |               |        |
       map, sum  map, sum        map, sum  map, sum
          |        |               |        |
          5       25              61      113
           \      /                \       /
              30                      174
                \                    /
                 COMBINE (addition)
                         |
                        204
```

**This diagram does not promise** that the JVM always splits into exactly four branches, along those boundaries, or using only four threads. The source and runtime decide splittability, task size, execution schedule, and combining strategy. The semantics of the computation must still hold whenever the pipeline functions obey the Stream contract.

Not every element gets its own task. Creating too many tiny tasks can cost more than the actual computation, so parallel streams typically process **batches of elements** within each work chunk.

## 3. Enabling parallel mode and when the pipeline actually runs

There are two common approaches:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

List<Integer> so = Arrays.asList(1, 2, 3, 4, 5);

Stream<Integer> a = so.parallelStream();
Stream<Integer> b = so.stream().parallel();

System.out.println(a.isParallel()); // true
System.out.println(b.isParallel()); // true
```

`parallel()` is an **intermediate** operation that configures the execution mode. It does not consume data by itself: processing only starts when a terminal operation such as `sum`, `reduce`, `count`, `collect`, or `forEach` requires a result.

```java
long tong = so.stream()
    .mapToLong(Integer::longValue)
    .parallel()
    .sum();

System.out.println(tong); // 15
```

`sequential()` returns the pipeline to sequential mode:

```java
long tongTuanTu = so.stream()
    .parallel()
    .mapToLong(Integer::longValue)
    .sequential()
    .sum();

System.out.println(tongTuanTu); // 15
```

Do not read the snippet above as "everything before `sequential()` runs in parallel, and everything after runs sequentially." For ordinary Stream pipelines, sequential/parallel mode is set for the **entire pipeline when the terminal operation executes**, not per individual stage.

A stream **can only be consumed once**. To compare sequential and parallel results, create two new streams from the same source; do not call a second terminal operation on an already consumed stream.

## 4. The split stage: `Spliterator`

### 4.1. Role of `Spliterator`

`Spliterator<T>` provides the mechanism to consume and **attempt to split** a source. Key methods:

| Method | Meaning |
| --- | --- |
| `tryAdvance(Consumer<? super T>)` | Supplies the next element to the consumer if available. |
| `forEachRemaining(Consumer<? super T>)` | Consumes all remaining elements. |
| `trySplit()` | Attempts to partition a portion of data into another spliterator; may return `null`. |
| `estimateSize()` | Reports the estimated number of remaining elements. |
| `characteristics()` | Describes attributes such as `ORDERED`, `SIZED`, `SUBSIZED`. |

Model example:

```text
Initial Spliterator: [A, B, C, D, E, F]
                      trySplit()
                      /        \
   New Spliterator [A,B,C]    Remaining [D,E,F]
```

For an ordered source, the split-off part from `trySplit` must correspond to a **prefix** of the unvisited elements, although the split strategy and chunk sizes depend on the source. Not every source splits evenly; some return `null` because they cannot split or splitting is not worthwhile.

Common characteristics:

- **`ORDERED`:** the source has a defined encounter order.
- **`SIZED`:** the exact remaining element count is known per contract.
- **`SUBSIZED`:** child spliterators produced by splitting also have exact sizes.
- **`SORTED` / `DISTINCT`:** the source already satisfies these properties, which can help optimize certain steps.

These characteristics are **contracts**, not casual hints. When writing a custom spliterator, misdeclaring `SIZED`, `SUBSIZED`, or `ORDERED` can cause serious bugs when the pipeline applies optimizations.

### 4.2. Observing a single `trySplit` call

Self-contained Java 8+ example:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;

public class ThuTrySplit {
    public static void main(String[] args) {
        List<Integer> nguon = Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8);

        Spliterator<Integer> conLai = nguon.spliterator();
        Spliterator<Integer> tachRa = conLai.trySplit();

        List<Integer> a = new ArrayList<>();
        List<Integer> b = new ArrayList<>();

        if (tachRa != null) {
            tachRa.forEachRemaining(a::add);
        }
        conLai.forEachRemaining(b::add);

        List<Integer> ghep = new ArrayList<>(a);
        ghep.addAll(b);

        System.out.println("Tách ra: " + a);
        System.out.println("Còn lại: " + b);
        System.out.println(ghep.equals(nguon)); // true
    }
}
```

With an ordered `List` source like above, the split-off part is a prefix and the remaining part is a suffix. The program does not have to assume `a` and `b` have equal sizes. **Calling `trySplit` directly does not spawn threads**: it only divides the object representing the data.

### 4.3. Not every source splits efficiently

| Source | Splitting characteristic | Consequence |
| --- | --- | --- |
| Array, `ArrayList`, `IntStream.range` | Usually splits into fast, balanced segments | Generally favorable if CPU-bound work is large enough. |
| `LinkedList` | Lacks fast index access like arrays | Splitting may require batching; needs measurement. |
| `Stream.iterate` | Next element may depend on the previous element | Hard to exploit independent splitting in some cases. |
| `BufferedReader.lines()` | Sequential I/O reading source | Parallelism does not automatically make file reading efficient. |
| `Files.walk` / `Files.find` | Tree traversal and I/O access, stateful | Resource limits and splitting differ from in-memory sources. |
| Custom Spliterator | Depends directly on `trySplit` | Must ensure no elements are dropped or duplicated. |

A source may split into two regions with nearly equal element counts yet **different per-element costs**. Hence "splitting element counts evenly" is not enough to guarantee load balance.

## 5. The process stage: tasks, threads, and fork/join

Parallel streams in common JDK implementations typically use the **fork/join** mechanism, with many tasks able to run in `ForkJoinPool.commonPool()`. This is a description of a common implementation, **not an API promise** that every pipeline always uses a specific pool, thread count, or thread name.

In fork/join, a task can further split work into subtasks; other workers can pick up remaining work (*work stealing*). There is no guarantee that each element or each diagram branch is processed by a separate thread.

### 5.1. `map` and `filter` preserve data semantics

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> nguon = Arrays.asList(1, 2, 3, 4, 5, 6);

List<Integer> ketQua = nguon.parallelStream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * n)
    .collect(Collectors.toList());

System.out.println(ketQua); // [4, 16, 36]
```

On an ordered `List`, `filter` preserves the relative order of surviving elements, `map` transforms each value, and the `toList` collector gathers elements in encounter order. **Callbacks may run in a different wall-clock order**, yet the resulting list retains the logical order shown above.

A well-behaved processing function:

```java
List<Integer> binhPhuong = nguon.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
```

It does not modify the source, does not update external variables, and does not depend on prior invocations. Such **stateless** and **non-interfering** functions are easy to reason about when distributing elements across tasks.

### 5.2. Cost per element can vary

Suppose the first 100 elements are very cheap while the next 100 require heavy computation. If the source splits into two halves by count, **the execution time of the two branches remains unbalanced**. The runtime may split parts further, but there is no guarantee it automatically eliminates all imbalance.

Therefore, when evaluating a source, ask:

- Does `trySplit` produce reasonably balanced chunks without excessive overhead?
- Do elements have roughly similar processing costs?
- Are there locks or shared resources forcing tasks to wait on each other?
- Is the work primarily CPU-bound, memory-bound, or I/O-bound?

## 6. The combine stage: `reduce`

True parallelization means results from multiple branches can be **combined regardless of how the source was split**. For example, addition on numbers within a safe range:

```java
import java.util.stream.LongStream;

long tong = LongStream.rangeClosed(1, 1000)
    .parallel()
    .reduce(0L, Long::sum);

System.out.println(tong); // 500500
```

`0L` is the **identity** of addition, and `Long::sum` is the combining operation. An operation `op` with identity `e` must satisfy:

```text
op(e, x) == x
op(x, e) == x
op(op(a, b), c) == op(a, op(b, c))
```

The third property is called **associativity**. It permits regrouping parentheses when merging local sums.

### 6.1. Why is subtraction unsuitable?

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Subtraction is not associative, so the following example is not guaranteed to produce the same logical result between sequential and parallel runs:

```java
List<Integer> so = Arrays.asList(1, 2, 3, 4);

int tuanTu = so.stream()
    .reduce(0, (a, b) -> a - b);

int songSong = so.parallelStream()
    .reduce(0, (a, b) -> a - b);

System.out.println(tuanTu);  // -10
System.out.println(songSong); // Not guaranteed to equal -10
```

Getting the expected value by chance in one run does not prove the operation is valid. The flaw lies in the **algebraic law**, not in the number of CPU cores.

### 6.2. A wrong identity can be applied multiple times

```java
// WRONG: 10 is not an identity for addition.
int sai = so.parallelStream().reduce(10, Integer::sum);

// RIGHT:
int dung = so.parallelStream().reduce(0, Integer::sum);

System.out.println(dung); // 10
```

In sequential mode, adding identity `10` makes the sum wrong once. In parallel mode, the initial value can be introduced into **multiple local partitions**, so the error is not a fixed offset that the program can rely on.

### 6.3. Three-argument overload with accumulator and combiner

Signature:

```java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

Example summing string lengths:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

int tong = ten.parallelStream()
    .reduce(0,
        (soKyTu, s) -> soKyTu + s.length(),
        Integer::sum);

System.out.println(tong); // 12
```

In addition to a valid identity and an associative combiner, there is a **compatibility** requirement between accumulator and combiner:

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

In the example: `u + (0 + s.length()) == u + s.length()`. If the combiner were replaced with subtraction, parallel execution could produce the wrong result even though the sequential version appears to work.

Just to sum string lengths, specialized APIs are usually more concise:

```java
int tong = ten.parallelStream()
    .mapToInt(String::length)
    .sum();
```

### 6.4. Floating-point numbers and integer overflow

`double` has floating-point error: `(a + b) + c` can differ bitwise from `a + (b + c)`. Therefore, `DoubleStream.reduce` results may differ in the least significant digits when grouping changes; when testing floating-point data, specify an appropriate tolerance. `DoubleStream.sum()` may apply compensated summation to reduce error, so it does not necessarily evaluate identically to `reduce(0.0, Double::sum)`.

Sums of `int` or `long` also have bounds. Use an appropriate type and overflow checks when business logic requires high precision; do not treat "parallel matches sequential" as proof that the calculation did not overflow.

## 7. `collect`: local accumulation containers and combiner

`reduce` typically combines into a **new value**; `collect` supports **mutable reduction** such as lists, sets, maps, and grouped statistics.

Example:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

List<String> ketQua = ten.parallelStream()
    .map(String::toUpperCase)
    .collect(Collectors.toList());

System.out.println(ketQua); // [JAVA, GO, KOTLIN]
```

A collector has conceptual components:

1. **Supplier:** creates an initial accumulation container.
2. **Accumulator:** records one element into an accumulation container.
3. **Combiner:** merges accumulation containers from multiple work chunks.
4. **Finisher:** transforms the accumulation container into the final result, when needed.

```text
             [Java, Go]        [Kotlin]
                 |                 |
              supplier          supplier
                 |                 |
              listA=[]          listB=[]
                 |                 |
             accumulate        accumulate
                 |                 |
            [Java, Go]          [Kotlin]
                 \                 /
                    combiner
                       |
               [Java, Go, Kotlin]
```

This diagram is illustrative and does not claim that a collector always creates two lists. The runtime may partition and combine in various ways consistent with the contract.

### 7.1. Do not manually mutate a shared `ArrayList`

```java
List<Integer> nguon = Arrays.asList(1, 2, 3, 4);
List<Integer> ketQua = new ArrayList<>();

// UNSAFE: multiple threads may concurrently add to the ArrayList.
nguon.parallelStream().forEach(ketQua::add);
```

Replace with:

```java
List<Integer> ketQua = nguon.parallelStream()
    .collect(Collectors.toList());
```

A collector can organize independent accumulation regions and merge them. `Collectors.toList()` does not guarantee a specific list type or mutability. If an `ArrayList` is explicitly needed:

```java
ArrayList<Integer> ketQua = nguon.parallelStream()
    .collect(Collectors.toCollection(ArrayList::new));
```

### 7.2. Seeing how it works via the three-argument `collect` overload

```java
long[] tongTrongMang = Arrays.asList(1, 2, 3, 4)
    .parallelStream()
    .collect(
        () -> new long[1],
        (box, n) -> box[0] += n,
        (left, right) -> left[0] += right[0]
    );

System.out.println(tongTrongMang[0]); // 10
```

The supplier creates a separate `long[1]` array each time it is called; the accumulator updates the chunk's array; the combiner merges the sum from another array. **You must not** return a single global array from the supplier for all chunks. This example illustrates the mechanism; when you only need a sum, `mapToLong(Integer::longValue).sum()` is simpler.

## 8. Grouping and combining with `groupingBy`

`groupingBy` can build local group maps and then merge them by key. When there are many groups, the cost of merging maps and lists can be substantial.

```java
List<String> tu = Arrays.asList(
    "Java", "Go", "Kotlin", "Ruby", "C", "Python"
);

Map<Integer, List<String>> theoDoDai = tu.parallelStream()
    .collect(Collectors.groupingBy(String::length));

System.out.println(theoDoDai.get(4)); // [Java, Ruby]
```

If you only need counts:

```java
Map<Integer, Long> dem = tu.parallelStream()
    .collect(Collectors.groupingBy(
        String::length, Collectors.counting()));

System.out.println(dem.get(4)); // 2
```

`groupingByConcurrent` can allow tasks to accumulate into a `ConcurrentMap` under suitable conditions. This collector has **concurrent** and **unordered** characteristics, so you must not expect it to preserve the encounter order of elements within each group:

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<Integer, Long> demConcurrent = tu.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        String::length, Collectors.counting()));
```

Do not choose `groupingByConcurrent` solely because its name contains "Concurrent." Consider ordering requirements, group distribution skew, contention overhead, memory, and real performance measurements.

## 9. Encounter order is not execution order

| Order type | Meaning | What is guaranteed |
| --- | --- | --- |
| **Encounter order** | Logical order defined by source and pipeline | Preserved on ordered streams like `List.stream()`, `IntStream.range` unless relaxed. |
| **Execution order** | When and on which thread callbacks are invoked | Not guaranteed on a parallel stream. |
| **Result order** | Order returned by a terminal operation/collector | Depends on the source and the terminal operation's semantics. |

Example:

```java
List<Integer> so = Arrays.asList(1, 2, 3, 4, 5);

List<Integer> ketQua = so.parallelStream()
    .map(n -> n * 10)
    .collect(Collectors.toList());

System.out.println(ketQua); // [10, 20, 30, 40, 50]
```

The resulting List follows encounter order, even though the `map` calls do not necessarily execute in the chronological order 1, 2, 3, 4, 5.

### `forEach` vs. `forEachOrdered`

```java
so.parallelStream().forEach(System.out::println);
```

This does not guarantee printing 1 through 5 in order. When you genuinely need the final action to run in encounter order:

```java
so.parallelStream().forEachOrdered(System.out::println);
```

On a `List` source, `forEachOrdered` prints 1, 2, 3, 4, 5; this requirement can limit parallel gains. When the goal is collecting a list, `collect` is clearer than writing manually to an external list.

### `findFirst` vs. `findAny`

```java
int first = so.parallelStream()
    .filter(n -> n > 2)
    .findFirst()
    .orElse(-1); // 3

int any = so.parallelStream()
    .filter(n -> n > 2)
    .findAny()
    .orElse(-1); // Could be 3, 4, or 5
```

`findFirst` respects the first position in encounter order. `findAny` accepts any matching element, so do not hardcode tests assuming it always returns 3.

`unordered()` does not force shuffling; it only **relaxes the order-preservation requirement** for steps that can take advantage of it. When you need the exact first N elements or the very first element, do not casually add `unordered()`.


## 10. Stateful operations and short-circuiting in parallel

Not every intermediate step is element-by-element independent:

| Operation | Characteristic | Potential impact when run in parallel |
| --- | --- | --- |
| `map` | Usually stateless if mapper is pure | Easy to process independently per chunk. |
| `filter` | Usually stateless if predicate is pure | Easy to process independently, though output count may be unknown upfront. |
| `sorted` | Stateful, needs information across many elements | May need to buffer data and coordinate to sort. |
| `distinct` | Stateful because deduplication is required | Keeping the first occurrence on an ordered stream can incur coordination cost. |
| `limit(n)` / `skip(n)` | Depends on element position if source is ordered | May need coordination to identify the leading/skipped segment. |
| `takeWhile` / `dropWhile` (Java 9+) | Depends on a contiguous prefix matching a condition | Ordering constraints can reduce parallel efficiency. |
| `findFirst` | Short-circuiting and respects first element if ordered | May need to synchronize information across branches. |
| `findAny` / `anyMatch` | Short-circuiting | Can stop early without examining the entire source. |

### 10.1. `limit` on an ordered source

```java
import java.util.stream.IntStream;

List<Integer> dauTien = IntStream.range(0, 1000)
    .parallel()
    .limit(5)
    .boxed()
    .collect(Collectors.toList());

System.out.println(dauTien); // [0, 1, 2, 3, 4]
```

With an ordered `IntStream.range` source, `limit(5)` must select the **first five elements in logical order**, not whichever five elements some thread finishes first. Maintaining this requirement can incur coordination overhead.

`sorted().limit(5)` and `limit(5).sorted()` also have different semantics: the first finds the five smallest values in the entire source; the second only sorts the first five encountered elements.

### 10.2. Short-circuiting does not promise how many times a lambda runs

```java
boolean coSoChan = IntStream.range(1, 1000)
    .parallel()
    .anyMatch(n -> n % 2 == 0);

System.out.println(coSoChan); // true
```

`anyMatch` can determine its result before traversing the entire source. However, other work chunks may already have started, be running, or be stopping; **you cannot deduce that the predicate was called exactly twice** just because the first even element in encounter order is 2.

Therefore, do not use a test predicate to trigger business actions that must execute once per element.

## 11. Side effects and shared state

Behavioral functions in a pipeline should be **non-interfering** (not modifying the source being processed) and in most cases **stateless** (their result does not depend on a variable changing across calls).

**Unsafe** example:

```java
List<Integer> nguon = Arrays.asList(1, 2, 3, 4, 5);
List<Integer> dich = new ArrayList<>();

// DO NOT DO THIS: multiple threads may concurrently modify dich.
nguon.parallelStream()
    .map(n -> {
        dich.add(n);
        return n * n;
    })
    .count();
```

There are two issues:

1. A shared `ArrayList` is unsafe under concurrent writes.
2. `count()` can return the source size directly **without evaluating `map`**, because `map` does not change element count. Thus `dich.add(n)` might not even **run**.

The right way if you want a list of squares:

```java
List<Integer> binhPhuong = nguon.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());

System.out.println(binhPhuong); // [1, 4, 9, 16, 25]
```

### 11.1. `AtomicInteger` does not automatically guarantee semantic correctness

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger();

List<Integer> ketQua = nguon.parallelStream()
    .map(n -> n + counter.incrementAndGet())
    .collect(Collectors.toList());
```

`AtomicInteger` makes incrementing the counter atomic. Yet the sequence number assigned to each element still depends on **thread execution scheduling**, so it is no longer a pure function of `n`. When the requirement is processing by **position in a List**, use an explicit index:

```java
List<Integer> theoViTri = IntStream.range(0, nguon.size())
    .parallel()
    .mapToObj(i -> nguon.get(i) + i)
    .collect(Collectors.toList());
```

This pattern assumes the source `List` is not modified and supports fast indexed access, such as `ArrayList`. For a `LinkedList`, repeated indexed access can be expensive.

### 11.2. Do not use a mutable identity in `reduce`

```java
// DO NOT DO THIS: identity is an ArrayList object mutated in place.
List<Integer> sai = nguon.parallelStream()
    .reduce(
        new ArrayList<Integer>(),
        (list, n) -> {
            list.add(n);
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

`reduce` requires the identity and combining operation to obey algebraic laws; mutating an identity object in place can cause multiple chunks to share references, duplicate results, or create race conditions. If the goal is building a collection, use `collect` with an appropriate supplier.

### 11.3. Do not mutate the source while traversing

```java
List<Integer> so = new ArrayList<>(
    Arrays.asList(1, 2, 3, 4));

// DO NOT DO THIS:
// so.parallelStream().forEach(so::remove);
```

Traversing and mutating the source simultaneously violates the *non-interference* assumption and can cause errors or wrong results. Instead, create a new collection:

```java
List<Integer> soLe = so.parallelStream()
    .filter(n -> n % 2 != 0)
    .collect(Collectors.toList());

System.out.println(soLe); // [1, 3]
```

## 12. Costs and limitations of parallel streams

Parallel streams pay overhead for:

1. Splitting the source and organizing work chunks.
2. Scheduling, stealing work, and coordinating workers.
3. Collecting or merging results from parts.
4. Maintaining encounter order when operations require it.
5. Allocating intermediate containers and consuming memory cache/bandwidth.

Parallelism is worth considering when:

- **The source is large enough** and splits well, such as arrays, `ArrayList`, or `IntStream.range`.
- **Each element requires a relatively substantial amount of CPU computation**.
- Processing functions are independent, stateless, and do not contend on shared state.
- The terminal operation has a valid `combiner` with reasonable merge cost.
- CPU resources are available and not busy handling other tasks.

Parallelism can be **slower** when:

- Data has only a few dozen or a few hundred simple elements.
- The source splits poorly or work chunks are heavily skewed.
- There are multiple stateful steps such as `sorted` or `distinct`.
- Tasks contend on a lock, map, or memory region.
- Work blocks on I/O such as disk reads, HTTP calls, or database waits.
- The primary bottleneck is memory bandwidth rather than CPU compute power.

### 12.1. Comparing results is not a benchmark

```java
long tuanTu = java.util.stream.LongStream.rangeClosed(1, 100000)
    .map(n -> n * n)
    .sum();

long songSong = java.util.stream.LongStream.rangeClosed(1, 100000)
    .parallel()
    .map(n -> n * n)
    .sum();

System.out.println(tuanTu == songSong); // true
```

In this example, the sum of squares stays within `long` range. However, comparing outputs only shows **the results match**, not that parallel is faster. A single timing measurement can be skewed by JIT, GC, OS scheduling, and CPU thermal throttling.

For real performance measurement, set up a representative workload, warm up properly, prevent dead-code elimination, and use a benchmark tool like JMH. Do not wrap `System.nanoTime()` around a single run to decide on switching an entire system to parallel streams.

### 12.2. Blocking I/O tasks and the common pool

For independent CPU-bound computations, distributing across cores can help. But lambdas waiting on network, disk, or database can tie up pool workers for long periods and affect other tasks. Do not assume `Files.walk(...).parallel()` automatically makes I/O reads faster.

In service applications, consider connection limits, timeouts, backpressure, source splittability, and dedicated thread management when blocking tasks dominate. A shared orchestration pool is no substitute for explicit resource design.

## 13. Writing custom `Spliterator` and `Collector`: two distinct contracts

When writing a custom **Spliterator**, ask:

- Does `trySplit` produce two **non-overlapping, exhaustive** regions?
- With `ORDERED`, does the split-off part serve as a prefix?
- Do `estimateSize`, `SIZED`, and `SUBSIZED` accurately reflect sizes?
- Is there any state or I/O that cannot be safely shared across work chunks?

When writing a **Collector**, verify:

- Does `supplier` create a fresh accumulation container each time it is called?
- Does `accumulator` accept each element and update the target container properly?
- Does `combiner` merge two containers without losing or duplicating data?
- Does `finisher` return the correct final result?
- Do `characteristics` such as `CONCURRENT`, `UNORDERED`, and `IDENTITY_FINISH` accurately reflect the collector's capabilities?

`CONCURRENT` does not mean "a flag you can add to go faster." It requires the accumulator to be safe when called concurrently on the same accumulation container under suitable conditions. `UNORDERED` should also be declared only when encounter order does not affect the result.

For common needs, prefer Java's built-in collectors (`toList`, `toSet`, `summingLong`, `groupingBy`) over writing custom ones, unless business contracts truly require it.

## 14. Complete semantic verification program (Java 8+)

This standalone program verifies sequential and parallel results on empty, single-element, and multi-element data, while also validating ordering and grouping. It **does not rely on thread names** or specific split shapes, making it suitable for verifying correctness rather than benchmarking.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class KiemChungParallelStream {
    static void yeuCau(boolean hopLe, String thongBao) {
        if (!hopLe) {
            throw new AssertionError(thongBao);
        }
    }

    static long tinhTong(List<Integer> nguon, boolean parallel) {
        LongStream stream = nguon.stream()
            .mapToLong(Integer::longValue);

        if (parallel) {
            stream = stream.parallel();
        }

        return stream.reduce(0L, Long::sum);
    }

    public static void main(String[] args) {
        List<List<Integer>> cacCa = Arrays.asList(
            Collections.<Integer>emptyList(),
            Collections.singletonList(7),
            Arrays.asList(1, 2, 3, 4),
            Arrays.asList(-3, 0, 7, -2)
        );

        for (List<Integer> ca : cacCa) {
            long mongDoi = 0L;
            for (int n : ca) {
                mongDoi += n;
            }

            yeuCau(tinhTong(ca, false) == mongDoi,
                "Sai kết quả tuần tự " + ca);
            yeuCau(tinhTong(ca, true) == mongDoi,
                "Sai kết quả song song " + ca);
        }

        List<Integer> nguon = Arrays.asList(1, 2, 3, 4, 5, 6);

        List<Integer> daLoc = nguon.parallelStream()
            .filter(n -> n % 2 == 0)
            .map(n -> n * n)
            .collect(Collectors.toList());

        yeuCau(daLoc.equals(Arrays.asList(4, 16, 36)),
            "Sai kết quả collect có thứ tự");

        List<Integer> dauTien = IntStream.range(0, 100)
            .parallel()
            .limit(5)
            .boxed()
            .collect(Collectors.toList());

        yeuCau(dauTien.equals(Arrays.asList(0, 1, 2, 3, 4)),
            "Sai encounter order");

        Map<Integer, Long> theoSoDu = IntStream.rangeClosed(1, 1000)
            .parallel()
            .boxed()
            .collect(Collectors.groupingBy(
                n -> n % 3,
                Collectors.counting()
            ));

        yeuCau(theoSoDu.get(0) == 333L, "Sai nhóm dư 0");
        yeuCau(theoSoDu.get(1) == 334L, "Sai nhóm dư 1");
        yeuCau(theoSoDu.get(2) == 333L, "Sai nhóm dư 2");

        List<Integer> banSao = new ArrayList<>(nguon);
        List<Integer> ketQua = banSao.parallelStream()
            .map(n -> n * n)
            .collect(Collectors.toList());

        yeuCau(ketQua.size() == banSao.size(),
            "Sai số phần tử sau map");

        System.out.println("PASS: chia, xử lý, ghép kết quả");
    }
}
```

When all checks pass, the program prints:

```text
PASS: chia, xử lý, ghép kết quả
```

Tests help catch common bugs, but **they do not prove every custom accumulator/combiner is always correct**. Algebraically verify identity, associativity, and compatibility across the actual data domain.

## 15. Common errors and misconceptions

| Error / misconception | Cause | How to address |
| --- | --- | --- |
| Thinking `parallel()` spawns one thread per element | The runtime usually splits into chunks and uses a scheduler | Separate the concepts of work chunk, thread, and data. |
| Thinking only stages after `parallel()` run in parallel | Execution mode applies to the pipeline at the terminal operation | Use `isParallel()` to inspect mode; do not split by stage position. |
| `forEach` prints in a different order than the list | Execution order is not encounter order | Use `forEachOrdered` if output must follow order. |
| `findAny` does not return the first element | Allowed to select any matching element | Use `findFirst` if the first element is required. |
| `reduce(10, Integer::sum)` produces wrong results | Identity is not neutral for addition | Use `0`. |
| Subtraction gives different results between sequential and parallel | Subtraction is not associative | Choose an associative combining operation. |
| Manually calling `ArrayList.add` inside `parallel().forEach` loses elements | Multiple threads mutate the list unsafely | Use `collect(toList())`. |
| Using `AtomicInteger` for encounter order | Counter reflects thread scheduling | Use indices from an ordered source. |
| `map` containing logging does not run when ending with `count` | Runtime may elide steps that do not affect count | Do not rely on side effects. |
| `groupingByConcurrent` scrambles group order | Unordered collector | Choose an order-preserving collector or sort output. |
| Unsplittable source with `parallel()` called | `trySplit` may be ineffective or return null | Choose a suitable source and measure performance. |
| `sorted` and `limit` on an ordered stream are slow | Coordination and state increase overhead | Review operation order and ordering needs. |
| `parallel()` on I/O tasks is slower | Blocked workers and resource contention | Choose an appropriate I/O concurrency model. |
| Testing once and concluding correctness | Failed to check empty, boundary cases, or combiner | Cross-check independently and verify algebraic properties. |

## 16. Practice exercises

### Exercise 1 — Split–process–combine model

Given `IntStream.rangeClosed(1, 8).parallel().map(n -> n * 2).sum()`. What is the result? Explain the three stages and why you cannot claim the stream will create exactly four branches with two elements each.

### Exercise 2 — Identity and associativity

```java
List<Integer> so = Arrays.asList(2, 4, 6, 8);

int a = so.stream().reduce(0, Integer::sum);
int b = so.parallelStream().reduce(0, Integer::sum);
int c = so.parallelStream().reduce(10, Integer::sum);
```

Are `a` and `b` identical? Can `c` be considered the valid sum of the source? Explain.

### Exercise 3 — Result order

```java
List<Integer> so = Arrays.asList(5, 2, 4, 1, 3);

List<Integer> kq = so.parallelStream()
    .map(n -> n * 10)
    .collect(Collectors.toList());

so.parallelStream().forEach(System.out::println);
```

Predict `kq`. Can you predict the order of lines printed by `forEach`? If you need to print in exact encounter order, what should you use?

### Exercise 4 — Shared state

```java
List<Integer> output = new ArrayList<>();
so.parallelStream().forEach(n -> output.add(n * n));
```

Is the snippet above safe? Rewrite it using a collector. Why is merely wrapping the list with `Collections.synchronizedList` still insufficient to guarantee result order matches encounter order?

### Exercise 5 — When is performance worth measuring?

Two pipelines each process 100,000 records: (A) performs an independent CPU-bound calculation per element, and (B) reads file metadata/files or makes a network call per element. Should you call `parallel()` by default for both? Which factors should you measure?

### Reference solutions

**Exercise 1:** The result is `72`, because `2 × (1 + 2 + ... + 8) = 72`. The source can be split in multiple ways; partitions compute local sums and combine them via addition. There is no contract guaranteeing four branches.

**Exercise 2:** `a == 20`, `b == 20`. `c` is not a valid aggregation because `10` is not an identity; the number of times `10` appears across branches can vary by split. The identity for addition is 0.

**Exercise 3:** `kq = [50, 20, 40, 10, 30]`. The line order of `forEach` is not guaranteed. `forEachOrdered` executes the action according to the encounter order of an ordered stream.

**Exercise 4:** No, `ArrayList` is unsafe when modified by multiple threads. Use:

```java
List<Integer> output = so.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
```

`synchronizedList` can prevent certain races when adding elements, yet it does not make `forEach` run in encounter order; thus the order of `add` calls can still differ from the source.

**Exercise 5:** Not by default. An independent CPU-bound pipeline with a splittable source may be worth testing in parallel; blocking I/O can be constrained by connection limits, disk, timeouts, and shared worker resources. Measure execution time, throughput, latency, CPU, memory, contention, and I/O pressure on a representative workload.

## 17. Summary

The parallel stream model can be remembered as:

```text
Source with Spliterator
          |
      trySplit()
          |
   Local work chunks
          |
  map / filter / process
          |
   Intermediate results
          |
  reduce / collect / sum
          |
      Final result
```

- **Split:** `Spliterator.trySplit` governs splittability; `SIZED` / `SUBSIZED` / `ORDERED` help the runtime understand source characteristics.
- **Process:** behavioral functions must be non-interfering and usually stateless; do not depend on threads or external counters.
- **Combine:** `reduce` requires a proper identity, associativity, and combiner; `collect` requires supplier, accumulator, and combiner to obey the contract.
- **Order:** encounter order differs from execution order; `Collectors.toList()` preserves output order on an ordered stream even when parallel `forEach` does not preserve print order.
- **Performance:** stateful operations, ordering requirements, poorly splittable sources, and merge overhead can make parallel slower.
- **Verification:** compare results on empty, single-element, multi-element, and boundary cases; verify combining contracts before measuring performance.

Understanding **split – process – combine** lets you use parallel Stream APIs on solid ground, avoiding subtle state, ordering, and correctness bugs while knowing when `parallel()` is genuinely worth considering.