# Enabling Parallelism with parallelStream and parallel

The Java Stream API allows processing a sequence of elements using a declarative pipeline: creating a source, chaining intermediate operations such as `filter` and `map`, and executing a terminal operation such as `sum`, `reduce`, or `collect`. By default, many sources create a **sequential stream**. When the work is large enough and can be partitioned independently, you can request **parallel mode** (*parallel stream*) using `Collection.parallelStream()` or `BaseStream.parallel()`. However, enabling parallel mode **does not guarantee a faster program, does not make an algorithm with side effects thread-safe, and does not guarantee that each element runs on a separate thread**.

This lesson belongs to the **Parallel Processing Semantics** chapter of the **JAVA_STREAM_API** module. The focus is on how to enable parallel mode, how to check and switch modes, and the effects on encounter order, reduction, collectors, shared state, and performance. This knowledge supports advanced topics on `Spliterator`, grouping, custom collectors, and Stream Gatherers, but it must start with the semantic contract of Streams rather than just calling `parallel()`.

## 1. Two common ways to create a parallel Stream

### 1.1. Calling parallelStream() directly on a Collection

Since Java 8, the `java.util.Collection<E>` interface provides the method:

```java
default Stream<E> parallelStream();
```

Example:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5);

int sum = numbers.parallelStream()
        .filter(n -> n % 2 != 0)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 9 = 1 + 3 + 5
```

`parallelStream()` creates a Stream configured in parallel mode from a collection. It can be called on `List`, `Set`, and other collections; if the source is a `Map`, you typically choose `map.entrySet().parallelStream()` or `map.values().parallelStream()` depending on the data to traverse.

### 1.2. Calling parallel() on an existing Stream

`parallel()` is a method on `BaseStream` and is available on `Stream` as well as the primitive streams `IntStream`, `LongStream`, and `DoubleStream`:

```java
import java.util.stream.IntStream;

long sum = IntStream.rangeClosed(1, 100_000)
        .parallel()
        .mapToLong(n -> n)
        .sum();

System.out.println(sum); // 5000050000
```

In this example, `rangeClosed(1, 100_000)` creates an ordered sequence of integers; `parallel()` requests parallel processing, `mapToLong` converts to `long` so the sum does not overflow `int`, and `sum()` performs the aggregation.

You can also start from `stream()` and then call `parallel()`:

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5);

int sum = numbers.stream()
        .parallel()
        .mapToInt(Integer::intValue)
        .sum(); // 15
```

For most problems with ordinary `Collection` types, `collection.parallelStream()` and `collection.stream().parallel()` are **two ways of expressing the same intent**: obtaining a pipeline in parallel mode. However, do not treat them as a guarantee of the exact same splitting strategy or speed, because the source `Spliterator` and collection implementation can affect splittability.

### 1.3. Quick selection table

| Existing source | How to enable | Notes |
|---|---|---|
| `List<Product> products` | `products.parallelStream()` | Concise when you already have a collection |
| `Set<String> tags` | `tags.parallelStream()` | Does not automatically add encounter order to an unordered set |
| `Stream<Order> orders` | `orders.parallel()` | Switches the pipeline mode |
| `IntStream.range(0, n)` | `IntStream.range(0, n).parallel()` | Primitive numeric source easy to split into ranges |
| `Arrays.stream(array)` | `Arrays.stream(array).parallel()` | Processes elements from an array |
| `Map<K,V> map` | `map.entrySet().parallelStream()` | Processes each entry of the Map |
| `Spliterator<T> spliterator` | `StreamSupport.stream(spliterator, true)` | Advanced approach when controlling the source directly |

**Note:** `parallelStream` does not exist on the `Stream` type itself; for an object that is already a Stream, call `parallel()`.

## 2. parallel() sets the mode, it does not immediately perform work

`parallel()` **is not a terminal operation**. It does not traverse data on its own and does not produce a result. The pipeline remains *lazy*: operations like `filter` or `map` are executed only when a terminal operation actually requests data.

```java
import java.util.stream.Stream;

Stream<Integer> pipeline = Stream.of(1, 2, 3, 4)
        .parallel()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10);

System.out.println(pipeline.isParallel()); // true

List<Integer> result = pipeline.collect(
        java.util.stream.Collectors.toList());
System.out.println(result); // [20, 40]
```

Only the terminal operation `collect` triggers execution. `isParallel()` is a query of the Stream's **configured mode**, not an execution command. There is no guarantee that all four elements in the example are processed on different threads: a tiny size may make splitting offer no benefit.

### 2.1. sequential() switches back to sequential mode

`BaseStream.sequential()` returns the Stream to sequential mode:

```java
Stream<Integer> selected = Stream.of(1, 2, 3)
        .parallel()
        .sequential();

System.out.println(selected.isParallel()); // false
System.out.println(selected.count());      // 3
```

If a pipeline calls both `parallel()` and `sequential()`, **the final mode of the pipeline when the terminal operation runs** is what matters; it does not mean each segment of the pipeline keeps its own mode:

```java
Stream<Integer> source = Stream.of(1, 2, 3)
        .parallel()
        .map(n -> n * 2)
        .sequential();

System.out.println(source.isParallel()); // false
System.out.println(source.reduce(0, Integer::sum)); // 12
```

Conversely, `Stream.of(1, 2, 3).sequential().parallel()` is in parallel mode. You should not toggle back and forth repeatedly as a mechanism to "run this part in parallel and that part sequentially" inside **one** pipeline; if you need stages with distinct lifecycles, complete one stage and create a new pipeline from the appropriate result.

### 2.2. A Stream can still only be used once

`parallel()` **does not duplicate** data or create a reusable pipeline:

```java
Stream<Integer> numbers = Stream.of(1, 2, 3).parallel();
long count = numbers.count(); // 3

// numbers.reduce(0, Integer::sum);
// WRONG: The Stream has already been consumed.
```

If you need both the sum and the count, you can create two new Streams from a re-traversable source or use a single collector that aggregates multiple metrics in one pass.

## 3. How does a parallel stream work?

At a conceptual level, Java can **split the source into parts**, process each part, and **combine the results**:

```text
              Source [1, 2, 3, 4, 5, 6, 7, 8]
                              |
                      Spliterator split
                        /            \
                 [1,2,3,4]        [5,6,7,8]
                  /      \         /      \
               [1,2]   [3,4]   [5,6]   [7,8]
                  \      /         \      /
                local result     local result
                        \           /
                           combine
                              |
                        final result
```

**This diagram is illustrative only**; the library may split the source using a different strategy. The key point is that work can be performed independently, yet the combine step must still produce the right result regardless of how many parts the source is split into.

### 3.1. Role of Spliterator

`Spliterator` is the mechanism Stream uses to traverse and potentially partition a source. Capabilities such as `trySplit()`, size estimation (`estimateSize()`), and characteristics like `ORDERED`, `SIZED`, and `SUBSIZED` can influence how the framework splits work.

Typically, an array or `ArrayList` is easier to split into segments than a source that depends on previous state to generate the next element. For example:

```java
// Source with a clear integer range.
long sumRange = java.util.stream.LongStream
        .rangeClosed(1, 100_000)
        .parallel()
        .sum();

// Source generated step-by-step from the previous element.
long sumIterate = java.util.stream.Stream
        .iterate(1L, n -> n + 1)
        .limit(100_000)
        .parallel()
        .mapToLong(Long::longValue)
        .sum();
```

Both pipelines can produce the sum `5000050000`, but the `iterate` source has sequential generation semantics and therefore does not inherently split work as well as `rangeClosed`. Do not assume that adding `parallel()` is enough to eliminate the inherently sequential nature of a source.

### 3.2. Threads and ForkJoinPool

Common Java parallel stream implementations are typically built on **fork/join** and use `ForkJoinPool.commonPool()` in normal contexts. However, the Stream API **does not promise that each element runs on a specific thread, does not promise an exact thread count**, and does not turn `parallel()` into an asynchronous task-scheduling call for the caller.

```java
java.util.stream.IntStream.rangeClosed(1, 8)
        .parallel()
        .forEach(n -> System.out.println(
                n + " handled by " + Thread.currentThread().getName()));
```

When you run this, you may see different thread names and numbers printed out of order. **Thread names and specific execution order are for observation only**, not data to use in correctness tests.

Because the common pool is a shared resource in many runtime configurations, long-running blocking I/O, waiting on locks, or network waits can reduce throughput for other tasks. Parallel streams are best suited when the workload is large enough, primarily CPU-bound, independent, and can combine results efficiently. If you need fine-grained control over execution scheduling and concurrency limits, consider a dedicated execution design instead of relying implicitly on calling `parallel()`.

## 4. Complete Java 8 example: invoice aggregation

The following example illustrates **two ways to enable parallelism**, compares the result with sequential mode, and then collects by region. There are no shared side effects in the pipeline; invoice data is treated as immutable during traversal.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ParallelStreamActivationDemo {
    static final class Invoice {
        private final String id;
        private final String region;
        private final long amountCents;
        private final boolean paid;

        Invoice(String id, String region, long amountCents, boolean paid) {
            this.id = id;
            this.region = region;
            this.amountCents = amountCents;
            this.paid = paid;
        }

        String getId() {
            return id;
        }

        String getRegion() {
            return region;
        }

        long getAmountCents() {
            return amountCents;
        }

        boolean isPaid() {
            return paid;
        }
    }

    public static void main(String[] args) {
        List<Invoice> invoices = Arrays.asList(
                new Invoice("HD-01", "BAC", 1_000L, true),
                new Invoice("HD-02", "NAM", 2_000L, true),
                new Invoice("HD-03", "BAC", 3_000L, false),
                new Invoice("HD-04", "BAC", 4_000L, true),
                new Invoice("HD-05", "NAM", 5_000L, true)
        );

        // 1) Default sequential Stream.
        long sequentialTotal = invoices.stream()
                .filter(Invoice::isPaid)
                .mapToLong(Invoice::getAmountCents)
                .sum();

        // 2) Collection.parallelStream().
        long parallelTotal = invoices.parallelStream()
                .filter(Invoice::isPaid)
                .mapToLong(Invoice::getAmountCents)
                .sum();

        // 3) Stream.parallel() on a sequential source.
        long parallelViaFlag = invoices.stream()
                .parallel()
                .filter(Invoice::isPaid)
                .mapToLong(Invoice::getAmountCents)
                .sum();

        System.out.println(sequentialTotal); // 12000
        System.out.println(parallelTotal);   // 12000
        System.out.println(parallelViaFlag); // 12000

        // 4) Parallel collection using built-in collectors.
        Map<String, Long> paidByRegion = invoices.parallelStream()
                .filter(Invoice::isPaid)
                .collect(Collectors.groupingBy(
                        Invoice::getRegion,
                        Collectors.summingLong(Invoice::getAmountCents)));

        System.out.println(paidByRegion.get("BAC")); // 5000
        System.out.println(paidByRegion.get("NAM")); // 7000

        // 5) collect(toList()) preserves encounter order from the List source.
        List<String> paidIds = invoices.parallelStream()
                .filter(Invoice::isPaid)
                .map(Invoice::getId)
                .collect(Collectors.toList());
        System.out.println(paidIds);
        // [HD-01, HD-02, HD-04, HD-05]

        // 6) Checking and switching mode.
        System.out.println(invoices.parallelStream().isParallel()); // true
        Stream<Invoice> switched = invoices.stream()
                .parallel()
                .sequential();
        System.out.println(switched.isParallel()); // false
        System.out.println(switched.count());      // 5

        // 7) Ordered printing even though the pipeline is configured in parallel.
        invoices.parallelStream()
                .filter(Invoice::isPaid)
                .map(Invoice::getId)
                .forEachOrdered(System.out::println);
        // HD-01
        // HD-02
        // HD-04
        // HD-05
    }
}
```

**Explanation:** the first three ways of summing all produce `12000` because only four invoices are paid. The `groupingBy` collector with `summingLong` lets the framework manage accumulation and merging for each group; there is no need for a shared `HashMap` modified from multiple threads. `collect(toList())` preserves encounter order from the ordered `List` source, whereas the Map returned by `groupingBy` does not guarantee key iteration order. With five elements, enabling parallelism is **not** a performance optimization recommendation; the program only demonstrates API semantics.

## 5. Encounter order remains a separate concept

**Encounter order** is the order of elements established by the source and pipeline. For example, a `List` has positional order; `IntStream.range` has increasing numeric order; a `HashSet` does not guarantee an encounter order. Enabling `parallel()` **does not automatically strip** encounter order, although the **action execution** order may differ from it.

```java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 8)
        .parallel()
        .forEach(n -> System.out.print(n + " "));
// May not print in the order 1, 2, 3, ..., 8.

System.out.println();

IntStream.rangeClosed(1, 8)
        .parallel()
        .forEachOrdered(n -> System.out.print(n + " "));
// 1 2 3 4 5 6 7 8
```

`forEach` **does not guarantee** the order in which actions execute, even on a source with encounter order. `forEachOrdered` **guarantees** that actions execute in encounter order if the Stream is ordered; however, it may require coordination and waiting, reducing the benefit of parallelism. It **does not** promise that every upstream `map` or `filter` also runs in order or on the same thread.

### 5.1. findFirst and findAny

`findFirst()` respects the first element according to the encounter order of an ordered Stream. `findAny()` is allowed to choose any matching element and often gives parallel processing more freedom:

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt first = IntStream.rangeClosed(1, 100)
        .parallel()
        .filter(n -> n % 7 == 0)
        .findFirst();

OptionalInt any = IntStream.rangeClosed(1, 100)
        .parallel()
        .filter(n -> n % 7 == 0)
        .findAny();

System.out.println(first.orElse(-1)); // 7
System.out.println(any.isPresent());  // true
// Do not assume any.getAsInt() is always 7.
```

If the application only needs to know whether a matching element exists, use `anyMatch` instead of traversing everything with `forEach`. If the application needs the first position, you must preserve the encounter order requirement; do not pick `findAny` just for speed and alter business behavior.

### 5.2. limit, distinct, and sorted can incur order-preservation overhead

`limit(n)` on an ordered Stream must select **the first n elements in encounter order**. `distinct()` on an ordered Stream must determine which element is the first occurrence to retain. `sorted()` needs enough relevant data to perform sorting. These constraints can make a parallel pipeline cost extra memory, synchronization, or time.

```java
List<Integer> firstFourEven = java.util.stream.IntStream
        .rangeClosed(1, 100)
        .parallel()
        .filter(n -> n % 2 == 0)
        .limit(4)
        .boxed()
        .collect(java.util.stream.Collectors.toList());

System.out.println(firstFourEven); // [2, 4, 6, 8]
```

Do not call `unordered()` just to speed things up if the business requirement needs the "first four elements" from the source; that operation can change the set of selected elements.

## 6. Side effects and shared state: the primary source of bugs

Switching `stream()` to `parallelStream()` allows multiple lambda invocations **to run concurrently**. Any mutable variable or object modified by multiple invocations must be evaluated for thread safety. However, the best remedy is usually **to avoid introducing shared mutable state into lambdas**, not to add ad-hoc locks.

### 6.1. Wrong: multiple threads modifying an ArrayList concurrently

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> unsafe = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(unsafe::add); // WRONG: ArrayList is not thread-safe.

// unsafe.size() or its contents cannot be relied upon.
```

This is a *data race*: multiple workers can concurrently modify the internal structure of the `ArrayList`, leading to lost elements, wrong order, or errors. Observing `size == 10000` in a few runs does not prove the code is safe.

### 6.2. Right: let a Collector manage the accumulator

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> safe = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(Collectors.toList());

System.out.println(safe.size()); // 10000
System.out.println(safe.get(0));  // 0
```

With an ordered source and an appropriate collector, the runtime can create **multiple local containers**, accumulate elements, and merge them according to the collector's contract. There is no need to manually manage a mutable `ArrayList` outside the pipeline.

### 6.3. AtomicLong avoids races but may not be the optimal design

`AtomicLong.addAndGet` can protect an addition on shared state, but having many workers contend on a single variable can introduce overhead:

```java
java.util.concurrent.atomic.AtomicLong total =
        new java.util.concurrent.atomic.AtomicLong();

java.util.stream.LongStream.rangeClosed(1, 100_000)
        .parallel()
        .forEach(total::addAndGet);

System.out.println(total.get()); // 5000050000
```

To compute a sum, a cleaner and usually more sensible approach is:

```java
long sum = java.util.stream.LongStream.rangeClosed(1, 100_000)
        .parallel()
        .sum(); // 5000050000
```

`sum` expresses a reduction instead of forcing all workers to update a single shared accumulator. Do not interpret "thread-safe" as "automatically efficient."

### 6.4. Do not modify the source while traversing

Lambdas should be **non-interfering** (not modifying the source) and typically **stateless** (not relying on shared mutable state). For example, adding or removing elements from the source `ArrayList` itself inside `filter` or `map` while the Stream is traversing can cause errors or unpredictable results. Prepare a valid source first, then build a read-only pipeline.

For tasks calling external APIs, writing to a database, writing files, or sending emails inside `forEach`, you must also consider retries, partial failures, concurrency limits, and transactions. `parallel()` does not automatically provide those mechanisms.

## 7. Reduction and Collector must satisfy the right contracts

To merge results from branches, a reduction operation must satisfy **associativity**:

\[
(a \mathbin{\mathrm{op}} b) \mathbin{\mathrm{op}} c
= a \mathbin{\mathrm{op}} (b \mathbin{\mathrm{op}} c)
\]

`Integer::sum` and `Long::sum` satisfy associativity under Java integer addition semantics (though they **can overflow** relative to the intended mathematical sum). Subtraction and division generally do not satisfy associativity.

```java
int left = (20 - 5) - 3; // 12
int right = 20 - (5 - 3); // 18
```

Therefore, this is **not** a contract-compliant reduction when the framework is allowed to split work:

```java
// DO NOT DO THIS: subtraction is not associative.
int wrong = java.util.stream.Stream.of(20, 5, 3)
        .parallel()
        .reduce((a, b) -> a - b)
        .orElse(0);
// The result may depend on how parts are combined.
```

### 7.1. Identity must be a true identity element

When using `reduce(identity, accumulator)`, the identity must leave elements unchanged:

```java
int correct = java.util.stream.IntStream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum);
System.out.println(correct); // 6

// WRONG: 100 is not an identity element for addition.
int wrong = java.util.stream.IntStream.of(1, 2, 3)
        .parallel()
        .reduce(100, Integer::sum);
// Do not expect the result to follow "add 100 only once" logic.
```

Across branches, the identity may participate in multiple intermediate results; an invalid identity causes wrong results or partition-dependent behavior. For addition, choose `0`; for multiplication, choose `1`. Do not use a business default number as the identity unless it is truly an identity element for the operation.

### 7.2. Collector must be able to combine accumulated parts

`collect(Collectors.toList())`, `groupingBy`, and `summingLong` are built-in collectors that accumulate and combine according to contract. When writing a custom `Collector`, ensure that:

- `supplier` creates a new, independent, valid accumulation state.
- `accumulator` adds an element to the state without modifying the source or external state.
- `combiner` merges two states completely without losing elements.
- The final result is equivalent between sequential accumulation and splitting followed by combining.
- Do not declare `CONCURRENT` for a container that cannot tolerate concurrent updates from multiple workers; do not declare `UNORDERED` when business order matters.

```java
Map<String, Long> totals = invoices.parallelStream()
        .filter(Invoice::isPaid)
        .collect(java.util.stream.Collectors.groupingBy(
                Invoice::getRegion,
                java.util.stream.Collectors.summingLong(
                        Invoice::getAmountCents)));
```

This snippet uses `Invoice` and `invoices` from the program in section 4. `groupingBy` does not have to be a `CONCURRENT` collector to be used in a parallel stream: the framework can use intermediate Maps and then merge them.

If order does not matter and the data has suitable characteristics, you may consider `groupingByConcurrent` or `toConcurrentMap`, but do not assume they are faster or preserve "first/last seen element" rules in a Stream whose encounter order has been dropped.

### 7.3. Floating-point rounding error

`double` is not bitwise associative due to rounding:

```java
double a = (1.0e16 + -1.0e16) + 1.0; // 1.0
double b = 1.0e16 + (-1.0e16 + 1.0); // 0.0
```

Consequently, parallel floating-point aggregations can yield small differences (or significant ones on special inputs) compared to sequential execution. `DoubleStream.sum()` may use compensated summation to improve accuracy, but it does not guarantee bitwise-identical results across all splits. For currency, consider `BigDecimal` or integers in the smallest currency unit with overflow checks.

## 8. When is parallelStream beneficial, and when should it be avoided?

Actual speed depends on **cost per element**, **splitting cost**, **merging cost**, **element count**, ordering constraints, and machine resources. There is no fixed element-count threshold that guarantees parallel mode is faster.

| Scenario | Assessment |
|---|---|
| Large array or numeric range, substantial CPU work per element, independent elements | May benefit from parallelism if confirmed by real measurements |
| List of a few dozen elements, very lightweight `map` | Splitting/merging overhead usually makes parallelism unattractive |
| `Stream.iterate` source depending on the previous element | Limited splittability can restrict benefits |
| Pipeline using `sorted`, `distinct`, or `limit` with encounter order | May require extra coordination/buffering to preserve order |
| Many blocking I/O tasks or network calls | Risk of occupying workers and resource contention; needs an appropriate concurrency limiter |
| Shared mutable state inside `forEach` | Data race risk; redesign rather than just adding `parallel()` |
| Transactional requirements or strictly ordered notifications | Parallelism does not automatically provide action ordering or transactions |
| High-precision `BigDecimal` calculations | Can use parallelism if merge and rounding policies are right; measure overhead |

### 8.1. Source-splitting and result-merging overhead

Each chunk of work must be large enough to outweigh the **overhead** of splitting, scheduling, and merging. For instance, on `IntStream.range(0, 10)`, squaring and summing has far too little work to infer any benefit from parallelism. Conversely, an expensive pure-CPU computation over a large dataset can benefit more clearly.

### 8.2. Benchmarks must measure properly

If you want to compare sequential and parallel execution:

1. Use the **same data and the same business logic**, verifying correctness before measuring.
2. *Warm up* both execution paths to reduce the impact of JIT compilation and initialization.
3. Measure multiple iterations on representative data sizes; do not rely on a single `System.nanoTime()` call on a small set.
4. Avoid `System.out.println`, logging, or file/network reads inside the measured region if the goal is measuring CPU work.
5. Use a benchmark tool like **JMH** when reliable performance conclusions are needed; also pay attention to memory allocation and load from other threads.

You should not alter production execution flows based solely on a short snippet or a single run on a development machine.

## 9. Parallel stream is not an async mechanism

Calling `parallel()` asks the runtime **to potentially process elements using multiple workers during the terminal operation**. It **does not** mean that calling `sum()` or `collect()` immediately returns a `Future` so the caller can continue doing other work. Normally, the terminal operation finishes before returning a value to the caller.

```java
long total = java.util.stream.LongStream
        .rangeClosed(1, 100_000)
        .parallel()
        .sum();

// By this point total has already been computed, not a CompletableFuture<Long>.
System.out.println(total); // 5000050000
```

For coordinating asynchronous tasks, cancellation, timeouts, concurrency limits, and handling completion, choose an appropriate model such as `ExecutorService` or `CompletableFuture`. They solve a different problem from parallelizing a data pipeline.

### 9.1. Nested parallel streams and blocking

Do not automatically put `parallel()` on both an outer pipeline and an inner pipeline expecting exponential speedup. Tasks can contend for the same worker resources, incur management overhead, and degrade performance. With I/O sources like `Files.lines`, `try-with-resources` is still required even when reading in parallel; `parallel()` does not replace closing resources. Network calls, lock waits, or thread sleeps inside a mapper must be evaluated against real load and allowed concurrency.

## 10. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| "`parallelStream()` is always faster than `stream()`." | No; overhead and workload type determine performance. |
| "`parallel()` immediately executes `filter`/`map` steps." | No; the pipeline remains lazy until the terminal operation. |
| "`isParallel() == true` proves multiple threads were used." | No; it is a configuration flag, not a guarantee of actual worker count. |
| "`parallel()` creates a Future." | No; ordinary terminal operations still return the result upon completion. |
| "`forEach` on a parallel stream always preserves List order." | No; if action order is required, use `forEachOrdered` and accept the cost. |
| "`collect(toList())` on a parallel stream scrambles the list." | On a source with encounter order, an appropriate collector preserves element order. |
| "Just using `AtomicLong` is optimal for summing." | Synchronization safety does not mean optimal; `sum` or `reduce` is usually better. |
| "`reduce` can use any binary operation." | The accumulator must be associative and the identity must be valid. |
| "Enabling `parallel()` on `Files.lines` removes the need to close the file." | No; I/O resources still require explicit management. |
| "`parallel()` before and `sequential()` after create two distinct stages." | No; they control the mode of the whole pipeline, not stage boundaries. |

## 11. Practice exercises with solutions

### Exercise 1. Two ways to enable parallel mode

Given `List<Integer> numbers = Arrays.asList(1, 2, 3, 4)`. Write two pipelines to compute the sum using `parallelStream()` and `stream().parallel()`.

```java
int a = numbers.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();

int b = numbers.stream()
        .parallel()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(a); // 10
System.out.println(b); // 10
```

**Answer:** Both pipelines configure parallel processing and return `10`. With four numbers, you cannot claim parallel is faster.

### Exercise 2. Final mode

```java
Stream<Integer> s = Stream.of(1, 2, 3)
        .parallel()
        .sequential()
        .parallel();
```

**Answer:** `s.isParallel()` is `true`. If `s.sequential()` is called before the terminal operation, the mode will be sequential. Switching state does not create multiple independent execution phases.

### Exercise 3. Identifying a data race

```java
List<Integer> result = new java.util.ArrayList<>();
java.util.stream.IntStream.range(0, 1000)
        .parallel()
        .forEach(result::add);
```

**Answer:** Wrong because `ArrayList` is updated concurrently without thread safety. Fix it with `boxed().collect(Collectors.toList())` so the framework manages the result.

### Exercise 4. Is order preserved?

```java
java.util.stream.IntStream.rangeClosed(1, 5)
        .parallel()
        .forEachOrdered(System.out::print);
```

**Answer:** Prints `12345`. With `forEach(System.out::print)`, print order is not guaranteed even though the source has encounter order.

### Exercise 5. Which reduce operation is wrong?

```java
int result = java.util.stream.IntStream.of(10, 5, 2)
        .parallel()
        .reduce((a, b) -> a - b)
        .orElse(0);
```

**Answer:** Subtraction is not associative: `(10 - 5) - 2 = 3` differs from `10 - (5 - 2) = 7`. Do not use it as a reduction when partitioning can vary.

### Exercise 6. Choosing a splittable source

To sum integers from 1 to 1,000,000, should you start with `LongStream.rangeClosed(1, 1_000_000)` or `Stream.iterate(1L, n -> n + 1).limit(1_000_000)` when evaluating parallel processing?

**Answer:** `LongStream.rangeClosed` expresses the numeric range directly, avoids boxing, and typically splits easily across workers. Even then, you still need to measure to decide whether to call `parallel()`.

### Exercise 7. Choosing the right terminal operation

An ordered list contains requests. You only need to know **whether any request is overdue**, without traversing every request to print details. Should you use `forEach` with an external boolean variable or `anyMatch`?

**Answer:** Use `requests.parallelStream().anyMatch(Request::isOverdue)` if the predicate is pure and checks are independent. `anyMatch` can short-circuit and needs no external mutable variable. Measure performance and consider concurrency cost before keeping `parallelStream()`.

## 12. Checklist before enabling parallel()

Before replacing `stream()` with `parallelStream()` or adding `parallel()`, check:

1. **Right problem?** Can each element be processed independently, or does it need state from the previous element?
2. **Well-splittable source?** An array, list, or range, or a sequential hard-to-split or I/O source?
3. **Pure lambdas?** Do they modify the source collection, shared variables, business logs, or call APIs that require sequential execution?
4. **Valid combination operation?** Is the accumulator associative, the identity valid, and the collector's combiner and characteristics accurate?
5. **Is encounter order required?** Are `findFirst`, `limit`, `sorted`, `distinct`, or `forEachOrdered` adding overhead?
6. **Any resource limits?** Worker count, I/O, memory, file handles, blocking, and other tasks in the application?
7. **Checked accuracy?** `int`/`long` overflow, `double` rounding error, or currency requirements?
8. **Properly benchmarked?** Are sequential and parallel results equivalent, and does performance improve significantly on real data?

**Takeaway:** `Collection.parallelStream()` and `BaseStream.parallel()` are two ways to put a pipeline into **parallel mode**, not an automatic speedup command or an asynchronous processing mechanism. Your program must still obey Stream contracts on encounter order, lambda independence, reduction associativity, and resource lifecycles. Choose a splittable source, use appropriate aggregations, avoid shared state, and keep parallel mode only when real measurements prove its benefit.