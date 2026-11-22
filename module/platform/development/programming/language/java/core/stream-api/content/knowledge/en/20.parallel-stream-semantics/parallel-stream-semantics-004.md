# Impact of Source Size, Per-Element Cost, and Splitting Strategy

**Parallel Stream** lets Java process multiple elements of a pipeline across multiple tasks concurrently. However, `parallel()` is not a "speed-up" button for every problem. A pipeline can run **slower** in parallel if the data is too small, per-element work is too cheap, the source is hard to split, or the result requires extensive coordination to preserve order.

In the **JAVA_STREAM_API** module, we learn declarative data processing via lazy pipelines with `filter`, `map`, `reduce`, and `collect`, while also recognizing limits around state, resources, and performance. This lesson belongs to the **Parallel Processing Semantics** chapter, focusing on the three most important variables when considering a parallel Stream:

1. **Source size:** how many elements or how much work is there?
2. **Processing cost per element:** how much work does each element do, and is the cost uniform?
3. **Source splittability:** can `Spliterator` produce independent, balanced work chunks with low overhead?

Beyond these three variables, we will examine the impact of `ORDERED`, stateful intermediate operations, combiners, contention, and how to measure performance properly. These principles also apply when using custom collectors, `Spliterator`, and advanced transformations like Stream Gatherers.

## 1. What does a Parallel Stream do?

A sequential source:

~~~java
long total = java.util.stream.IntStream.range(0, 10_000)
    .mapToLong(n -> n * 2L)
    .sum();
~~~

Can be requested to process in parallel:

~~~java
long total = java.util.stream.IntStream.range(0, 10_000)
    .parallel()
    .mapToLong(n -> n * 2L)
    .sum();
~~~

Both must return the right result: the sum of `2 * n` for `n` from 0 to 9,999. Replacing `parallel()` with `sequential()` indicates that the pipeline should execute sequentially.

**`parallel()` only specifies the pipeline's execution mode.** It does not mean:

- Each element gets its own dedicated thread.
- All elements always run simultaneously.
- Thread count always equals CPU core count.
- Callbacks run in a specific order.
- The problem is guaranteed to finish sooner.

Typically, JDK Stream implementations use fork/join to split and process work. Task count, split boundaries, and execution schedules are implementation details, so you should not write business logic that depends on those details.

### General diagram

~~~mermaid
flowchart TD
    A["Source N elements"] --> B["Spliterator / split work"]
    B --> C1["Part 1"]
    B --> C2["Part 2"]
    B --> C3["Part ..."]
    B --> C4["Part k"]
    C1 --> D["Process filter/map"]
    C2 --> D
    C3 --> D
    C4 --> D
    D --> E["Combine reduce/collect"]
    E --> F["Final result"]
~~~

This diagram illustrates the **possibility** of partitioning, not a promise that there are always four tasks. Some sources are very difficult to split; some terminal operations force branches to synchronize or preserve order.

## 2. Cost model: total work and non-parallelizable work

Parallel execution time can be approximated conceptually as:

~~~text
T_parallel ≈ T_sequential_part
           + T_parallelizable / effective_workers
           + T_split
           + T_schedule
           + T_merge
           + T_contention
           + T_allocation
~~~

Where:

- `T_sequential_part` is the portion that must run sequentially or wait for another step.
- `T_parallelizable` is the time of work that can be split independently.
- `effective_workers` is the actual usable parallelism, **not automatically equal to core count**.
- `T_split` is the cost of partitioning the source into chunks.
- `T_schedule` is the cost of coordinating and stealing tasks.
- `T_merge` is the cost of combining partial results.
- `T_contention` is the cost of contention on CPU, memory, locks, and other resources.
- `T_allocation` is the cost of creating intermediate containers or objects.

This is a **reasoning model**, not an exact measurement formula for a JVM. It shows that for parallel execution to pay off, **the time saved by splitting work must exceed the added overhead**.

### Amdahl's Law

If a program has a fraction `s` of work that cannot be parallelized, the theoretical speedup using `p` workers is:

\[
S(p) \leq \frac{1}{s + \frac{1-s}{p}}
\]

For example: if `s = 0.2` (20% of the work must run sequentially), even with infinitely many workers the maximum theoretical speedup under this model approaches only **5x**. With 8 workers, the theoretical limit is:

\[
S(8) \leq \frac{1}{0.2 + 0.8/8} \approx 3.33
\]

Actual speedup is even lower due to splitting, scheduling, merging, memory, and contention overhead. Therefore, you cannot multiply core count by sequential speed and treat it as a guaranteed outcome.

## 3. Source size: few elements rarely offset overhead

Consider two pipelines computing the same kind of sum:

~~~java
long small = java.util.stream.IntStream.range(0, 20)
    .parallel()
    .asLongStream()
    .sum();

long large = java.util.stream.IntStream.range(0, 2_000_000)
    .parallel()
    .asLongStream()
    .sum();
~~~

A 20-element source has very little work when the operation is integer addition. Splitting and combining overhead can exceed sequential summation time. A two-million-element source has more work, yet **many elements alone do not guarantee parallel is faster**, because integer addition is still very light and data can be limited by memory bandwidth.

| Source size | Cost per element | Expectation to verify |
|---|---|---|
| Very small | Very light | Parallel rarely pays off |
| Very small | Heavy | May pay off if enough independent work units exist |
| Very large | Very light | May be dominated by overhead or memory limits |
| Very large | Heavy, independent | Reasonable candidate to test parallel |
| Large, hard-to-split source | Any | Difficult to utilize multiple workers |
| Large, must preserve order and complex merge | Any | Coordination overhead can be high |

The thresholds for "small" and "large" have no universal number across projects. They vary with CPU, JDK version, data structure, algorithm, and server load.

### 3.1. Many elements do not equate to many computations

`IntStream.range(0, 1_000_000).count()` can be optimized using the source's size metadata. It does not necessarily perform one million callback invocations.

~~~java
long count = java.util.stream.IntStream.range(0, 1_000_000)
    .parallel()
    .count();

System.out.println(count); // 1000000
~~~

When merely counting a `SIZED` source, `count()` can skip traversal. In such cases, increasing the element count does not increase pipeline work. **Do not use `peek` or side effects inside `map` to assume callback count equals element count.**

## 4. Per-element cost: sufficiently heavy computation creates speedup potential

The following two operations differ dramatically in workload:

~~~java
// Light: adding a number.
.map(n -> n + 1)

// Heavier: multiple independent transformation rounds on one value.
.mapToLong(n -> expensiveCalculation(n))
~~~

If each element only performs one or two arithmetic operations, the JVM can execute sequentially very fast. In that case, orchestration overhead can take a large share of the time. If each element consumes many CPU operations without needing shared state, dividing work across workers has a chance to outweigh overhead.

However, **high cost alone is not enough**: elements must still be relatively independent, the source must be splittable, and result aggregation must not become a bottleneck.

### 4.1. Example illustrating two workload types

~~~java
import java.util.stream.IntStream;

public class CostPerElement {
    static long simple(int n) {
        return n + 1L;
    }

    static long cpuWork(int value) {
        long x = value + 0x9E3779B97F4A7C15L;
        for (int i = 0; i < 100; i++) {
            x ^= x >>> 13;
            x *= 0xBF58476D1CE4E5B9L;
            x ^= x >>> 17;
        }
        // Bound each element's result so the sum does not overflow in the example.
        return x & 1023L;
    }

    public static void main(String[] args) {
        int size = 100_000;

        long cheap = IntStream.range(0, size)
            .mapToLong(CostPerElement::simple)
            .sum();

        long expensive = IntStream.range(0, size)
            .parallel()
            .mapToLong(CostPerElement::cpuWork)
            .sum();

        System.out.println(cheap > 0);      // true
        System.out.println(expensive >= 0);  // true
    }
}
~~~

This program illustrates **the difference in work per element**, not a speed comparison benchmark between the two pipelines: one side uses a completely different calculation than the other. To evaluate parallelism, you must compare **the same algorithm and the same input** in both modes; section 12 provides a better measurement template.

## 5. Non-uniform cost: load balance matters more than element count

Two slices of data with equal element counts **do not necessarily have equal total cost**.

Suppose a job processes `Order` records:

- Normal orders take about 1 unit of work.
- Orders with many line items take about 100 units of work.
- The first half of the dataset contains all heavy orders, and the second half contains all light orders.

If the source is split in half by position, one worker may end up doing most of the work while the other finishes early. This is **load imbalance**.

~~~text
Split by element count:
  Branch A: 100 heavy elements -> very slow
  Branch B: 100 light elements -> finishes early

Completion time is dominated by the slowest branch.
~~~

Fork/join can keep splitting and rebalancing work under favorable conditions, but **it does not guarantee perfect automatic load balancing**. Task *granularity* and source splitting heavily influence runtime.

### 5.1. Principles for handling non-uniform cost

1. If you can split into **many sufficiently sized chunks**, the system has a chance to redistribute work.
2. If each chunk is too large and unsplittable, workers easily sit idle while another branch stays busy.
3. If each chunk is too small, task creation and management overhead rises.
4. If elements are heavy due to I/O or locks, adding threads may not help and can saturate resources.

Measure **time skew across branches**, not just element count. For highly variable workloads, partitioning by estimated cost or using an appropriate scheduler can outperform splitting evenly by index.

## 6. Spliterator determines how easily a source splits

Parallel Stream relies heavily on the source's `Spliterator`. Key methods:

~~~java
boolean tryAdvance(Consumer<? super T> action);
Spliterator<T> trySplit();
long estimateSize();
int characteristics();
~~~

- **`tryAdvance`** traverses one element if remaining.
- **`trySplit`** attempts to split off part of the unvisited data into a new Spliterator.
- **`estimateSize`** estimates the remaining element count.
- **`characteristics`** describes source traits so the runtime can optimize accordingly.

### 6.1. A valid split

~~~text
Ordered source [0, 8):

Before:
  original = [0, 1, 2, 3, 4, 5, 6, 7]

After original.trySplit():
  returned = [0, 1, 2, 3]    (prefix)
  original = [4, 5, 6, 7]    (suffix)

estimateSize(returned) = 4
estimateSize(original) = 4
~~~

For a Spliterator with `ORDERED`, the Spliterator returned by `trySplit` must contain **a prefix** of the unvisited elements. Neither branch may emit the same element twice or drop an element. This correctness holds independently of whether parallel execution is faster.

**Splitting exactly in half is not required.** `trySplit()` can split in batches, return different ratios, or return `null` when it cannot split.

### 6.2. Observing a standard Java source

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class SplitObservation {
    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>();
        for (int i = 0; i < 16; i++) {
            values.add(i);
        }

        Spliterator<Integer> rest = values.spliterator();
        System.out.println(rest.estimateSize()); // 16

        Spliterator<Integer> prefix = rest.trySplit();

        if (prefix != null) {
            long leftSize = prefix.estimateSize();
            long rightSize = rest.estimateSize();

            System.out.println(leftSize + rightSize); // 16

            // Check characteristic only, without relying on half sizes.
            System.out.println(
                rest.hasCharacteristics(Spliterator.ORDERED)
            ); // true for ArrayList
        }
    }
}
~~~

Some implementations may split 8–8 in this example, yet **the `Spliterator` contract does not require every source or every call to split that way**. What matters is continued splittability, balance, and disjointness of branches.

## 7. SIZED, SUBSIZED, and size metadata assist work splitting

Two characteristics relate directly to size:

- **`SIZED`:** the remaining element count is known accurately by source contract.
- **`SUBSIZED`:** this Spliterator and all Spliterators returned by `trySplit` continue to guarantee `SIZED` and `SUBSIZED`.

`SUBSIZED` is a stronger promise than `SIZED`. Not every source that knows its initial size can know the exact size of every sub-branch.

| Characteristic | Impact on performance reasoning |
|---|---|
| `SIZED` | Helps estimate input size and optimize certain terminal operations |
| `SUBSIZED` | Facilitates partitioning with known sizes |
| `ORDERED` | Defines encounter order, though `limit`/`distinct` may need extra coordination |
| `SORTED` | Informs the framework data is ordered, if declaration and comparator are valid |
| `CONCURRENT` | Source supports certain forms of concurrent modification under its own contract |
| `IMMUTABLE` | Source guarantees its structure will not mutate in ways that interfere with traversal |
| `DISTINCT` | Elements are distinct by `equals`; can help optimize deduplication |

Do not declare false characteristics just for speed. For example, declaring `SIZED` when `estimateSize()` is inaccurate can make `count()` return wrong results or cause errors when Stream allocates memory. Performance cannot be bought by breaking the source contract.

### 7.1. Cost of size estimation

`estimateSize()` returns a `long`, and may return `Long.MAX_VALUE` when the element count is unknown or unbounded. **That is not a request to allocate memory for that many elements.**

For a range source `[start, end)`, computing `end - start` is usually cheap and exact if overflow is handled properly. For data coming from I/O or a stateful generator, counting accurately before traversal can be very expensive or impossible.

## 8. Comparing easy-to-split and hard-to-split sources

A good parallel source does not only have many elements; it must also split at reasonable cost.

| Source | Splitting characteristic | Notes |
|---|---|---|
| Primitive arrays `int[]`, `long[]`, `double[]` | Direct positional access; typically splits efficiently by index ranges | Do not mutate the array while the pipeline traverses it |
| `ArrayList` | Indexed access; Spliterator supports balanced partitioning well | Operations can still be limited by memory bandwidth |
| `IntStream.range(...)` | Known bounds and size; easy to split into ranges | Splitting well alone does not guarantee fast terminal ops |
| `HashSet` | Has a Spliterator and splits, but order is not guaranteed | Different traits from List; output depends on ordering needs |
| `LinkedList` | Linked traversal; splitting is more complex and may batch | Do not conclude it is unsplittable; measure |
| One-way `Iterator` | Hard to jump directly to the middle; may batch before splitting | Splitting/buffering overhead affects gains |
| I/O / network sources | May block waiting for data or external resource limits | Parallel Stream does not turn blocking I/O into nonblocking |
| `Stream.iterate(seed, next)` | Next element depends on the previous one; hard to split efficiently in some cases | Consider termination bounds and recurrence cost |
| `Stream.generate(supplier)` | Values from supplier, possibly stateful / lacking encounter order | Supplier must satisfy contract when used in parallel |

This table reflects design tendencies; actual behavior also depends on the Spliterator implementation and JDK version.

### 8.1. Same algorithm, different sources can perform differently

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

List<Integer> arrayList = new ArrayList<>();
List<Integer> linkedList = new LinkedList<>();

for (int i = 0; i < 100_000; i++) {
    arrayList.add(i);
    linkedList.add(i);
}

long fromArrayList = arrayList.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();

long fromLinkedList = linkedList.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(fromArrayList == fromLinkedList); // true
~~~

The correct results must match. However, the two sources differ in structure, traversal cost, and partitioning strategy, so execution time can differ. The goal of this example is to **see that the data source matters**, not to claim one source is always faster in every case.

## 9. Work chunk size: granularity and split threshold

Suppose there are `N` elements and each task receives roughly `B` elements. A simple mental model puts the task count near `N / B`.

- `B` **too large**: few tasks, prone to imbalance when per-element cost varies.
- `B` **too small**: many tasks, increasing creation, scheduling, merging, and sync overhead.
- `B` **well-sized**: enough tasks to keep workers busy without letting overhead dominate.

~~~text
Tasks too coarse:
  [████████████████] [████]
  Worker 1 busy for long, Worker 2 waits.

Tasks too fine:
  [█][█][█][█][█][█][█][█][█]...
  Can incur high management overhead.

Tasks well-sized:
  [████][████][████][████]
  Can be distributed more flexibly.
~~~

There is no single fixed split threshold that fits every dataset. Consider per-element processing speed, cost uniformity, effective worker count, combiner cost, and host resources.

### 9.1. A custom Spliterator should not split infinitely into tiny tasks

Example `trySplit` logic for a Spliterator managing the interval `[current, fence)`:

~~~java
@Override
public Spliterator.OfInt trySplit() {
    long remaining = (long) fence - current;

    // Example: do not split further when fewer than 2,048 elements remain.
    if (remaining < 2_048L) {
        return null;
    }

    int middle = (int) ((long) current + remaining / 2);

    Spliterator.OfInt prefix =
        new RangeSpliterator(current, middle);

    current = middle;
    return prefix;
}
~~~

This is an **illustrative snippet to implement `trySplit`** on a `RangeSpliterator` class managing a numeric range, not a standalone program. That class must implement `tryAdvance`, `estimateSize`, `characteristics`, and maintain `current`/`fence` per contract. The threshold 2,048 is only an example showing the idea of "do not split overly tiny ranges"; it has no universal optimality meaning.

When `ORDERED`, the returned part is a prefix; after splitting, the original object keeps only the suffix. Arithmetic in `long` prevents `int` overflow on wide ranges. Other splitting strategies may use batching, uneven splits, or refuse splitting if the source disallows it.

## 10. ORDERED and stateful operations can make parallel execution costly

An `ORDERED` source has an **encounter order**, such as the element order of a `List` or an `IntStream.range` sequence. For many problems, order is critical; yet preserving order during parallel execution can require coordinating across multiple branches.

### 10.1. forEach and forEachOrdered

~~~java
import java.util.stream.IntStream;

IntStream.range(1, 6)
    .parallel()
    .forEach(System.out::print);
// May print digits in an unspecified order.

System.out.println();

IntStream.range(1, 6)
    .parallel()
    .forEachOrdered(System.out::print);
// Prints 12345.
~~~

`forEach` on a parallel Stream **does not guarantee** action execution order. `forEachOrdered` preserves the source's encounter order, but maintaining that order can reduce parallel gains, especially when the action itself performs I/O or synchronization.

**Do not use console output as a benchmark**, because writing to the console can be very slow and shared I/O itself skews performance observations.

### 10.2. distinct, sorted, limit

~~~java
List<Integer> firstThreeDistinct = List.of(3, 3, 2, 2, 1, 1)
    .parallelStream()
    .distinct()
    .limit(3)
    .toList();

System.out.println(firstThreeDistinct); // [3, 2, 1]
~~~

On a Stream with encounter order, `distinct` must retain the first-appearing representative; `limit(3)` must choose the first three values **after deduplication**. These requirements can increase coordination overhead across parallel branches.

`sorted()` is also a stateful intermediate operation: on a large source, it must organize data before establishing global order. If you only need a single minimum value, `min(...)` usually expresses the intent more directly than `sorted().findFirst()`.

### 10.3. unordered() only when business logic truly does not need order

~~~java
long count = List.of(3, 3, 2, 2, 1, 1)
    .parallelStream()
    .unordered()
    .distinct()
    .count();

System.out.println(count); // 3
~~~

`unordered()` drops the requirement to preserve encounter order, which can allow some parallel pipelines to run more flexibly. It **does not shuffle data** and must not be used if reports must keep the "first element" or appearance order.

## 11. Aggregations and branch-merging overhead

Parallel Streams often require a **combiner** to merge local results.

### 11.1. Reduce with associative addition

~~~java
long sum = java.util.stream.LongStream.rangeClosed(1, 100_000)
    .parallel()
    .reduce(0L, Long::sum);

System.out.println(sum); // 5000050000
~~~

Integer addition with identity 0 is associative under Java's integer model, so branch sums can be merged validly. Note that the sum can still **overflow `long`** on huge inputs; Java does not automatically promote integers to arbitrary precision.

### 11.2. Expensive combiners reduce benefits

Example collecting into a list:

~~~java
List<String> labels = java.util.stream.IntStream.range(0, 20_000)
    .parallel()
    .mapToObj(i -> "ID-" + i)
    .collect(java.util.stream.Collectors.toList());
~~~

Each branch may build local containers and then merge them. Creating 20,000 strings, allocating containers, and merging results all carry cost. If the main work is just turning an int into a short string, overhead can be large relative to computation.

`collect` is still the right API for mutable reduction; the point here is that **semantically right API does not mean fastest in parallel mode**.

### 11.3. groupingBy may require merging Maps

~~~java
Map<Integer, Long> counts = java.util.stream.IntStream.range(0, 100_000)
    .parallel()
    .boxed()
    .collect(java.util.stream.Collectors.groupingBy(
        n -> n % 10,
        java.util.stream.Collectors.counting()
    ));
~~~

The result has ten groups of 10,000 numbers each. However, Map containers across branches may need to be merged. With `groupingByConcurrent`, the contract differs regarding concurrency and ordering; do not substitute it casually if the application needs encounter order or specific collector behavior.

Merge cost and group cardinality must be evaluated alongside source size.

## 12. Illustrative measurement program: same algorithm, two modes

To compare performance meaningfully, **you must use the same data, the same computation, and the same result**. The following program compares sequential vs. parallel for pure CPU work without shared mutable state.

The example runs on **Java 17+**; the APIs used have existed since Java 8.

~~~java
import java.util.stream.IntStream;

public class ParallelCostExperiment {

    // Pure CPU computation: no I/O, no external state mutation.
    static long cpuWork(int value) {
        long x = value + 0x9E3779B97F4A7C15L;

        for (int i = 0; i < 100; i++) {
            x ^= x >>> 13;
            x *= 0xBF58476D1CE4E5B9L;
            x ^= x >>> 17;
        }

        return x & 1023L; // Per-element result from 0 to 1023.
    }

    static long calculate(int size, boolean parallel) {
        IntStream source = IntStream.range(0, size);
        if (parallel) {
            source = source.parallel();
        }

        return source
            .mapToLong(ParallelCostExperiment::cpuWork)
            .sum();
    }

    static long measureNanos(int size, boolean parallel) {
        long started = System.nanoTime();

        // Result used to prevent measuring a dead call.
        long result = calculate(size, parallel);

        long elapsed = System.nanoTime() - started;
        System.out.println(
            (parallel ? "parallel" : "sequential")
                + ", size=" + size
                + ", result=" + result
                + ", elapsedNs=" + elapsed
        );
        return result;
    }

    public static void main(String[] args) {
        // Simple warmup; not yet a professional benchmark.
        for (int i = 0; i < 3; i++) {
            calculate(30_000, false);
            calculate(30_000, true);
        }

        for (int size : new int[] {1_000, 30_000, 300_000}) {
            long sequential = measureNanos(size, false);
            long parallel = measureNanos(size, true);

            if (sequential != parallel) {
                throw new AssertionError(
                    "Sai kết quả tại size=" + size
                );
            }
        }
    }
}
~~~

The program prints **matching total results** for each `size`. Measured timings **have no fixed value**, as they depend on CPU, JDK, JIT warmup, runtime conditions, GC, and other tasks on the machine.

### 12.1. How to read the results

Suppose a run shows:

~~~text
size=1000:   sequential is faster
size=30000:  roughly comparable
size=300000: parallel is faster
~~~

This is only **a hypothetical scenario for practicing analysis**, not an experimentally measured result. Different datasets, iteration counts in `cpuWork`, JDK versions, and hardware can reverse the ranking.

The takeaway is not "300,000 elements is a standard threshold," but rather: **as total compute volume rises, the chance to amortize parallel overhead also rises**, provided the source and aggregation behave well.

### 12.2. Why is this not yet a proper benchmark?

Calling `System.nanoTime()` once per case is heavily affected by:

- **JIT warmup** and execution-profile optimizations.
- **GC** and memory allocation.
- **CPU turbo, thermals, power saving**, and actually allocated cores.
- **Other processes** running concurrently.
- **Sample run order** and dataset size.
- **Repetition frequency and timing outliers**.

For decision-grade evaluation, use **JMH** or a benchmarking harness with warmup, multiple forks/iterations, controlled inputs, and statistical reporting. This lesson only presents an illustrative experiment; do not treat single timings as performance proof.

## 13. Semantics and correctness must come before speedup

A pipeline that is correct sequentially **can become wrong** when switched to parallel if its logic depends on side effects, callback order, or external state.

### 13.1. Do not collect into a shared ArrayList using forEach

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> broken = new ArrayList<>();

// Wrong: multiple threads may call add on the same ArrayList.
// IntStream.range(0, 10_000).parallel().forEach(broken::add);

// Right: use a collector.
List<Integer> safe = IntStream.range(0, 10_000)
    .parallel()
    .boxed()
    .collect(java.util.stream.Collectors.toList());
~~~

`ArrayList` is not thread-safe under concurrent updates from multiple threads. Switching to `Collections.synchronizedList` may make adds thread-safe, yet it does not guarantee the required order and can introduce contention. `collect` expresses the intent of gathering results directly.

### 13.2. Reduce requires an identity and associativity

~~~java
int sum = List.of(1, 2, 3, 4)
    .parallelStream()
    .reduce(0, Integer::sum); // 10
~~~

Addition with identity 0 is suitable for splitting and merging. Subtraction is not associative; do not use `reduce(0, (a, b) -> a - b)` expecting every grouping to return the sequential result.

With `double`, addition can produce slight differences when merge order changes due to floating-point rounding. When data requires strict reproducibility and exactness (such as currency), choose appropriate arithmetic rules and data types.

### 13.3. Side effects have unpredictable invocation counts and order

~~~java
long count = java.util.stream.IntStream.range(0, 100)
    .parallel()
    .peek(n -> {
        // Do not place mandatory data-writing logic here.
    })
    .count();
~~~

Some optimizations may skip invoking intermediate callbacks for every element when the terminal operation can compute the result without traversing. Even when callbacks are invoked, order and executing threads in a parallel Stream are not guaranteed as in sequential execution.

Therefore, **do not use `peek`, `map`, or `filter` to perform I/O or mandatory business state updates**. Pipeline functions should be non-interfering with the source and not rely on mutable external state.

## 14. CPU-bound, memory-bound, and I/O-bound are not the same

Not every expensive task fits a Parallel Stream.

### CPU-bound

Work that is mostly computation with minimal shared state:

~~~text
Independent data decoding, numeric transforms, heavy formulas, rule checks.
~~~

Parallelism can be helpful if there are enough elements and the source splits well.

### Memory-bound

Work that reads/writes large amounts of data with very little computation:

~~~text
Scanning a large array to sum or copy data.
~~~

Speed can be bottlenecked by memory bandwidth or cache. Adding workers may not yield proportional gains.

### I/O-bound

Work waiting on disk, network, or external systems:

~~~text
HTTP calls per element, database queries, slow file reads.
~~~

Parallel Stream does not automatically turn blocking calls into nonblocking ones. Unbounded parallelism mismatched to external service limits can exhaust connections, saturate pools, or trigger timeouts.

In I/O systems, you typically need an explicit concurrency/backpressure and task-limiting mechanism rather than switching immediately to `parallelStream()`.

## 15. Environmental factors causing measurement differences

Testing parallel execution on a laptop may not reflect production environments:

- **Available processors** may differ from physical core count.
- **Container CPU quotas** can throttle CPU even on a multi-core host.
- **The common fork/join pool** is often used by default Stream implementations and can compete with other work in the same JVM.
- **A concurrently loaded machine** means adding parallel tasks can increase overall application latency even if single-task throughput appears higher.
- **Memory and GC** change when `collect` creates many intermediate containers.
- **Different JDK versions** may choose different splitting and scheduling strategies.

Do not use `Runtime.getRuntime().availableProcessors()` to conclude with certainty that the pipeline will use exactly that many threads, or scale by that factor.

When optimizing an API server, measure **throughput and latency under multiple concurrent requests**, not just the runtime of one isolated Stream on an idle machine.

## 16. Decision process for when to try parallel()

Here is a practical checklist:

| Question | If the answer is "no" |
|---|---|
| Is the sequential result already correct and tested? | Ensure correctness first |
| Can per-element processing functions run independently? | Remove shared state / side effects first |
| Does `reduce`/`collect` have a contract-compliant combiner? | Fix aggregation logic |
| Does the source have enough work to split? | Keep using sequential |
| Can the Spliterator split the source efficiently? | Consider changing the source or algorithm |
| Is per-element cost high enough to outweigh overhead? | Benchmark; do not assume benefit |
| Must strict encounter order be preserved? | Evaluate the cost of `sorted`, `limit`, `forEachOrdered` |
| Are CPU/memory resources available? | Avoid contention harming other tasks |
| Have you measured with representative data and load? | Not enough basis to decide |

The deciding criteria are **total time, throughput, latency, and correctness**. Parallel mode is just an execution option; it is not a mandatory requirement of the Java Stream API.

## 17. Common misconceptions and errors

| Misconception / error | Consequence | How to handle |
|---|---|---|
| "Above 10,000 elements, always turn on parallel" | Threshold varies by CPU, algorithm, and source | Measure on real data |
| "More threads always means faster" | Overhead, contention, worse cache locality | Observe effective parallelism |
| "All elements cost the same to process" | Load imbalance if some elements are very heavy | Inspect cost distribution |
| "`trySplit` must split evenly in half" | Design relies on a false contract assumption | Expect uneven splits or null |
| "`SIZED` only speeds things up, so declare it anyway" | Can produce wrong results | Only declare accurate characteristics |
| "`ArrayList` is safe enough with parallel `forEach`" | Race condition | Use `collect` or proper concurrent design |
| "`findAny()` always returns the first element" | Non-deterministic result | Use `findFirst()` when ordered and first is needed |
| "`forEachOrdered` runs as fast as `forEach`" | Order-coordination cost | Use only when order is needed |
| "`sorted().limit(k)` always processes few elements" | `sorted` may need the entire source | Choose an appropriate top-k algorithm |
| "A large `count()` means n elements were traversed" | `SIZED` sources can be optimized | Do not measure work using side effects |
| "Parallel will speed up blocking I/O" | Service congestion, connection exhaustion, timeouts | Limit concurrency and use a suitable I/O model |
| "One faster run is enough to conclude" | Noisy results | Use repeated benchmarks and varied environments |
| "Same printed order means parallel is deterministic" | Depends on execution schedule | Define encounter order and terminal contract |
| "Smaller splits are always better" | Higher scheduling/merging overhead | Choose appropriate granularity |

## 18. Practice exercise: analyzing the three factors on one pipeline

**Context:** a system needs to sum processing results for many job codes, each applying a pure CPU function. There are three experiments:

1. **Size:** keep the processing function constant, vary `size` between 1,000 and 200,000.
2. **Per-element cost:** keep `size` constant, vary loop rounds inside the function from 5 to 200.
3. **Splitting:** inspect the source's Spliterator, then describe the impact if a custom Spliterator's `trySplit` always returns `null`.

Task: explain which cases have a chance to speed up with parallel execution, **without relying on a fixed element-count threshold**.

### Reference solution (Java 8+)

~~~java
import java.util.Spliterator;
import java.util.stream.IntStream;

public class ParallelThreeFactorsPractice {

    static long work(int value, int rounds) {
        long x = value + 1L;

        for (int i = 0; i < rounds; i++) {
            x = x * 1_664_525L + 1_013_904_223L;
            x ^= x >>> 11;
        }

        return x & 1023L;
    }

    static long sum(int size, int rounds, boolean parallel) {
        IntStream source = IntStream.range(0, size);

        if (parallel) {
            source = source.parallel();
        }

        return source
            .mapToLong(value -> work(value, rounds))
            .sum();
    }

    public static void main(String[] args) {
        for (int size : new int[] {1_000, 200_000}) {
            for (int rounds : new int[] {5, 200}) {
                long seq = sum(size, rounds, false);
                long par = sum(size, rounds, true);

                System.out.println(
                    "size=" + size
                    + ", rounds=" + rounds
                    + ", equal=" + (seq == par)
                ); // equal=true if both compute accurately
            }
        }

        Spliterator.OfInt source = IntStream.range(0, 20)
            .spliterator();

        System.out.println(
            source.hasCharacteristics(Spliterator.SIZED)
        ); // true

        System.out.println(source.estimateSize()); // 20

        Spliterator.OfInt prefix = source.trySplit();

        if (prefix != null) {
            System.out.println(
                prefix.estimateSize() + source.estimateSize()
            ); // 20
        }
    }
}
~~~

This program **does not print execution time**; it checks the first priority: the same algorithm on the same input must produce equivalent results in both modes. When running timing experiments yourself, use a benchmark tool and control the variables discussed in section 12.

### Expected interpretation

- For `size = 1_000, rounds = 5`: little work, so parallel overhead easily dominates.
- For `size = 200_000, rounds = 200`: high CPU work with independent elements, making it a better candidate to test parallel execution.
- For `size = 1_000, rounds = 200`: each element is heavy, so total work might still be large enough to benefit; **measure**, do not conclude in advance.
- For `size = 200_000, rounds = 5`: many elements but light per-element work, so merging/scheduling overhead or memory bandwidth may limit gains.
- If `trySplit()` always returns `null`: source splitting for parallel execution is severely restricted, even though `parallel` is enabled.

### Self-check questions

1. What are the three main factors in this lesson? — **Source size, per-element cost, and source splittability**.
2. Does `parallel()` guarantee faster execution than `sequential()`? — **No**.
3. What does `trySplit()` return when it cannot split? — **`null`**.
4. Is `estimateSize()` always exact? — **No**, only when the source has a matching contract such as `SIZED`.
5. What does `SUBSIZED` add beyond `SIZED`? — **Split-off branches continue to have exact sizes**.
6. How does one half having much heavier work affect parallel execution? — **The slowest branch can determine completion time**.
7. Does `forEachOrdered` preserve encounter order? — **Yes**, though it may increase coordination overhead.
8. Can you use `ArrayList::add` on an external list with `parallelStream().forEach`? — **Unsafe when multiple threads update concurrently**.
9. When a source is `SIZED`, can `count()` skip traversal? — **Yes** in pipelines that can optimize accordingly.
10. Why can `Collectors.groupingBy` be costly in parallel? — **It must create and merge intermediate Maps**.
11. If data comes from blocking HTTP, does enabling parallel automatically solve I/O? — **No**.
12. What is needed to conclude something is faster? — **Benchmarks with warmup, sufficient iterations, identical data, and monitoring real system performance**.

## 19. Summary: all three variables must be evaluated together

To evaluate a **parallel Stream**, do not look only at element count or CPU core count. Evaluate all three variables as a system:

- **Source size** determines total work volume and the opportunity to create multiple tasks.
- **Cost per element** determines potential time savings from concurrent execution; **non-uniform** cost leads to load imbalance.
- **Source splitting** via `Spliterator.trySplit()`, `estimateSize()`, and characteristics like `SIZED`/`SUBSIZED` directly shapes task count, size, and balance.

Once the source is split, other factors remain critical: `ORDERED`, `distinct`, `sorted`, `limit`, combiner cost, contention, mutable state, and CPU/memory/I/O workload type. Therefore, **correctness must be verified first, and performance measured afterward**.

Using `parallel()` is a **workload-driven** decision, not a blanket rule for every pipeline. Understanding how size, per-element work, and splittability interact helps you design Streams, custom `Spliterator` implementations, and aggregations more effectively without sacrificing correctness or exhausting system resources.