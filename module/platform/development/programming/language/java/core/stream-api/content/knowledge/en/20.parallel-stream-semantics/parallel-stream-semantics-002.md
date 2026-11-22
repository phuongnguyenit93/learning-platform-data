# Switching Modes with sequential and Checking with isParallel

## 1. Two execution modes of a Stream pipeline

In **JAVA_STREAM_API**, developers describe data processing using pipelines such as `filter`, `map`, `reduce`, and `collect`. A pipeline can execute in **sequential** mode or **parallel** mode. Java provides two operations to choose the mode and one method to inspect the configured state:

- `parallel()`: requests the Stream to switch to parallel mode.
- `sequential()`: requests the Stream to switch to sequential mode.
- `isParallel()`: reports the current parallel mode of the Stream, returning a `boolean`.

Both `parallel()` and `sequential()` return a Stream for continuing the pipeline; they are **not** terminal operations and do not traverse data on their own. `isParallel()` only inspects the configured state and **does not** run the pipeline.

~~~text
Data source
     │
     ├─ stream() ─────────────► sequential by default
     │
     └─ parallelStream() ─────► parallel by default
                                     │
                     parallel() / sequential()
                                     │
                                     ▼
                              Pipeline mode
                                     │
                      filter → map → sorted → ...
                                     │
                                     ▼
                         terminal operation
                           reduce / collect / toList
                                     │
                                     ▼
                             Final result
~~~

This lesson belongs to the **Parallel Processing Semantics** chapter. The goal is not merely memorizing API names, but understanding **when the mode takes effect**, why `isParallel() == true` does not prove multiple threads are active, and why parallelization must not alter business results when callbacks obey the Stream contract.

The examples below apply to **Java 17+**. `parallel()`, `sequential()`, and `isParallel()` have all been available since Java 8.

## 2. Related APIs and return types

These three methods are declared in `BaseStream<T, S extends BaseStream<T, S>>`, so not only `Stream<T>` but also `IntStream`, `LongStream`, and `DoubleStream` support them.

~~~java
// Conceptual API signatures in BaseStream:
S sequential();
S parallel();
boolean isParallel();
~~~

| Method | Operation kind | Return value | Meaning |
| --- | --- | --- | --- |
| `parallel()` | Switches Stream mode | Same Stream type | Sets the pipeline to parallel mode |
| `sequential()` | Switches Stream mode | Same Stream type | Sets the pipeline to sequential mode |
| `isParallel()` | Queries state | `boolean` | Checks whether the Stream is currently configured as parallel |

Note: `parallel()` **does not** launch threads immediately when called, and `sequential()` **does not** mean "bring parallel-computed results back onto one thread." Ordinary Stream transformations remain lazy until a terminal operation runs.

Example checking Stream types and modes:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class CheckStreamMode {
    public static void main(String[] args) {
        Stream<Integer> serial = List.of(1, 2, 3).stream();
        System.out.println(serial.isParallel()); // false

        Stream<Integer> parallel = serial.parallel();
        System.out.println(parallel.isParallel()); // true

        Stream<Integer> backToSerial = parallel.sequential();
        System.out.println(backToSerial.isParallel()); // false

        System.out.println(backToSerial.toList()); // [1, 2, 3]
    }
}
~~~

Here each chained step builds **a single pipeline**, ending with **one terminal operation**, `toList()`. Do not treat the `serial` and `parallel` variables as two independent Streams to run separate terminal operations on.

## 3. stream() and parallelStream(): choosing the mode from the source

With a Collection, there are two common ways to start:

~~~java
import java.util.List;

List<Integer> values = List.of(5, 3, 8, 2);

var serial = values.stream();
var parallel = values.parallelStream();

System.out.println(serial.isParallel());   // false
System.out.println(parallel.isParallel()); // true
~~~

`Collection.stream()` creates a sequential Stream, whereas `Collection.parallelStream()` creates a parallel Stream. However, the initial mode **can be switched**:

~~~java
List<Integer> values = List.of(5, 3, 8, 2);

var changedToParallel = values.stream().parallel();
var changedToSerial = values.parallelStream().sequential();

System.out.println(changedToParallel.isParallel()); // true
System.out.println(changedToSerial.isParallel());   // false
~~~

The following two approaches can express the same requirement:

~~~java
long a = values.parallelStream()
    .filter(n -> n > 2)
    .count();

long b = values.stream()
    .parallel()
    .filter(n -> n > 2)
    .count();

// a == b == 3
~~~

Even so, **producing the same result type does not mean identical performance** in every case. Source-splitting cost, stage optimizations, and the weight of each computation still need to be evaluated separately.

### When to use which?

- Use `stream()` when you want a sequential pipeline by default.
- Use `parallelStream()` when you already know from the start that parallel processing is a suitable option.
- Use `parallel()` or `sequential()` when you want to select the mode based on configuration or a condition in code.
- If the input is already a `Stream` passed in from outside, you can call `sequential()` to request sequential execution or `parallel()` to request parallel execution, while respecting **ownership and the single-use lifecycle of the Stream**.

## 4. Switching modes: the last call determines pipeline execution

An important point: within a single Stream pipeline, `parallel()` and `sequential()` **do not create separate parallel/sequential execution boundaries for individual segments**. The pipeline's mode at the terminal operation determines the execution strategy.

~~~java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

// Ends mode configuration with sequential().
List<Integer> first = numbers.stream()
    .parallel()
    .map(n -> n * 2)
    .sequential()
    .filter(n -> n > 4)
    .toList();

System.out.println(first); // [6, 8, 10]
~~~

Do not interpret this example as "`map` runs in parallel and then `filter` runs sequentially." The final mode is **sequential** for the entire pipeline when the terminal operation begins.

In the opposite direction:

~~~java
List<Integer> second = numbers.stream()
    .sequential()
    .map(n -> n * 2)
    .parallel()
    .filter(n -> n > 4)
    .toList();

System.out.println(second); // [6, 8, 10]
~~~

In the second pipeline, the final request is **parallel**; `toList()` still preserves encounter order from the `List` source. Both results match because `map` and `filter` are pure and do not depend on callback execution order.

### 4.1. Checking the final state

~~~java
import java.util.stream.IntStream;

IntStream a = IntStream.range(0, 10)
    .parallel()
    .sequential();

IntStream b = IntStream.range(0, 10)
    .sequential()
    .parallel();

System.out.println(a.isParallel()); // false
System.out.println(b.isParallel()); // true
~~~

You can picture the rule as:

~~~text
stream()
  ├─ parallel()           → parallel
  ├─ sequential()         → sequential
  ├─ parallel()           → parallel
  └─ terminal operation   → executes in parallel mode

parallelStream()
  ├─ sequential()         → sequential
  └─ terminal operation   → executes in sequential mode
~~~

**Do not overuse toggling back and forth** in the same pipeline. Choosing one clear mode in a readable place makes testing and maintenance easier.

### 4.2. Want truly two stages with different modes?

If a problem strictly requires one stage to execute sequentially and another to execute in parallel, you need a **materialization boundary** and two separate pipelines; calling `sequential()` in the middle of a single pipeline does not achieve this.

~~~java
import java.util.List;

// Pipeline 1: complete sequential computation.
List<Integer> normalized = List.of(1, 2, 3, 4).stream()
    .map(n -> n * 10)
    .toList();

// Pipeline 2: a new Stream over the materialized result.
long total = normalized.parallelStream()
    .mapToLong(n -> (long) n * n)
    .sum();

System.out.println(total); // 3000
~~~

Splitting into stages creates an intermediate Collection, incurring memory and allocation overhead. Only do this when there is a real processing-boundary requirement, not as a default optimization.

## 5. What does isParallel() check, and what does it not check?

`isParallel()` reports the mode of the Stream object at the moment it is queried. It returns `true` if the Stream is configured for parallel execution and `false` if configured for sequential execution.

~~~java
import java.util.stream.IntStream;

IntStream pipeline = IntStream.range(1, 6)
    .filter(n -> n % 2 == 1)
    .parallel();

System.out.println(pipeline.isParallel()); // true

int sum = pipeline.sum(); // 1 + 3 + 5 = 9
System.out.println(sum);  // 9
~~~

`isParallel()` **does not mean**:

- How many threads are processing.
- Whether new threads have been created.
- Whether every intermediate operation must be invoked on a different thread.
- Whether parallel is definitely faster than sequential.
- Whether the pipeline has already started executing.
- Whether results may vary with thread scheduling while still being business-valid.

A Stream configured as parallel can perform part or all of its work on the very thread calling the terminal operation; splitting and scheduling depend on the JDK, environment, and source characteristics.

### 5.1. Do not use thread names to prove API mode

~~~java
import java.util.stream.IntStream;

IntStream.range(0, 8)
    .parallel()
    .forEach(n ->
        System.out.println(Thread.currentThread().getName() + ": " + n)
    );
~~~

This code may print several thread names and numbers out of order. However, **that is merely an observation from one run**, not a contract guaranteeing a specific worker count or print order. Conversely, seeing a single thread in a small test **does not prove `parallel()` was ignored**.

If you need to check the **configured state**, use `isParallel()`. If you need to verify **performance gains**, measure with representative workloads and data. If you need guarantees about threads, coordination, concurrency limits, or timeouts, parallel Streams are usually not the API to control those requirements directly.

## 6. Execution mode is not the same as encounter order

**Parallel/sequential** and **ordered/unordered** are two orthogonal dimensions of a pipeline.

- *Sequential/parallel* refers to the execution strategy.
- *Ordered/unordered* refers to whether the pipeline must preserve **encounter order**.

| Configuration | Execution mode | Encounter order |
| --- | --- | --- |
| `list.stream()` | Sequential | Present from `List` source |
| `list.parallelStream()` | Parallel | Still present from `List` source |
| `list.stream().unordered()` | Sequential | Constraint relaxed |
| `list.parallelStream().unordered()` | Parallel | Constraint relaxed |
| `list.parallelStream().sequential()` | Sequential | Still present from `List` source |

`parallel()` **does not automatically call `unordered()`**. `sequential()` **does not automatically sort data**. If the business logic requires output in source order, you must examine the encounter order of both the source and the pipeline.

### 6.1. toList() preserves encounter order when the source is ordered

~~~java
import java.util.List;

List<String> names = List.of("Chi", "An", "Bình");

List<String> result = names.parallelStream()
    .map(String::toUpperCase)
    .toList();

System.out.println(result); // [CHI, AN, BÌNH]
~~~

Even though callbacks may execute in parallel, `toList()` must preserve encounter order when the Stream is ordered. Do not use `parallel()` as a way to shuffle a list.

### 6.2. forEach() and forEachOrdered() differ

~~~java
import java.util.stream.IntStream;

// Action execution order is not guaranteed when parallel:
IntStream.rangeClosed(1, 5)
    .parallel()
    .forEach(System.out::println);
~~~

If actions must execute in encounter order, use:

~~~java
IntStream.rangeClosed(1, 5)
    .parallel()
    .forEachOrdered(System.out::println);

// Prints 1, 2, 3, 4, 5 in order.
~~~

`forEachOrdered` preserves action sequence in encounter order, though it can limit parallel speedup. If the goal is simply building a list, `toList()` or an appropriate collector is usually better than writing into an external mutable List.

### 6.3. findFirst(), findAny(), and short-circuiting

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> values = List.of(10, 20, 30, 40);

Optional<Integer> first = values.parallelStream()
    .filter(n -> n >= 20)
    .findFirst(); // Optional[20] because the source is ordered.

Optional<Integer> any = values.parallelStream()
    .filter(n -> n >= 20)
    .findAny(); // Could be 20, 30, or 40.
~~~

`findAny()` allows selecting any matching element, which can be convenient for parallelism. `findFirst()` must obey encounter order when present. Calling `sequential()` or `parallel()` does not change that requirement.

`limit` and `skip` on an ordered parallel stream may require extra coordination to determine the leading elements. If order is unnecessary, `unordered()` can relax constraints, but it simultaneously **changes semantics**: `limit(3)` may then return any three matching elements.

## 7. Spliterator and the source determine splittability

Streams do not parallelize by "creating a thread per element." How well data can be partitioned depends heavily on the **source's `Spliterator`** and pipeline structure.

~~~text
Collection / array / custom source
                 │
                 ▼
             Spliterator
                 │
            trySplit()
           /          \
      Part A          Part B
         │               │
  process separately  process separately
         │               │
         └───────┬───────┘
                 ▼
              combine
                 │
                 ▼
          terminal result
~~~

`Spliterator.trySplit()` can return a sub-Spliterator or `null` if it cannot or chooses not to split. Characteristics such as `SIZED`, `SUBSIZED`, and `ORDERED` can affect the execution strategy and coordination overhead.

Example of a numeric source that splits into ranges:

~~~java
import java.util.stream.IntStream;

long total = IntStream.range(0, 100_000)
    .parallel()
    .asLongStream()
    .sum();

System.out.println(total); // 4_999_950_000
~~~

An `IntStream.range` is typically easier to partition than a custom data source that must perform sequential I/O. Still, **there is no promise that `parallel()` is always faster**, even for numeric ranges: the time spent splitting, combining results, and starting execution can exceed the gain when the computation is trivial.

### Source characteristics do not guarantee multiple threads

A source with an **unsplittable** Spliterator can still be configured as parallel:

~~~java
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.Iterator;
import java.util.List;
import java.util.stream.StreamSupport;

Iterator<Integer> iterator = List.of(1, 2, 3).iterator();

Spliterator<Integer> source =
    Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED
    );

var pipeline = StreamSupport.stream(source, true);
System.out.println(pipeline.isParallel()); // true

System.out.println(pipeline.toList()); // [1, 2, 3]
~~~

In this example, `true` sets parallel mode. It does not guarantee that the three values will be processed by three threads or faster than an equivalent sequential run. Some Spliterators can also split internally by batching even when the size is unknown upfront.

## 8. Intermediate operations must still be stateless and non-interfering

A valid parallel pipeline requires **behavioral parameters** (`Predicate`, `Function`, `BinaryOperator`, ...) to obey the Stream API contract: **non-interfering** with the source being traversed and, where applicable, **stateless** (not depending on shared mutable state).

### 8.1. Do not use a shared ArrayList to collect results

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

// ANTI-PATTERN: risk of race condition.
List<Integer> shared = new ArrayList<>();

IntStream.range(0, 1000)
    .parallel()
    .forEach(shared::add);

// shared is not thread-safe; size/contents are not guaranteed.
~~~

Even if replaced with a synchronized collection, the algorithm can still suffer from lock contention and lose parallel benefits. When you want a result list, let Stream/collector manage it:

~~~java
List<Integer> result = IntStream.range(0, 1000)
    .parallel()
    .boxed()
    .toList();

System.out.println(result.size()); // 1000
~~~

### 8.2. AtomicInteger does not automatically make an algorithm stateless

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

// Unsuitable example if the goal is assigning sequence numbers in encounter order.
AtomicInteger counter = new AtomicInteger();

int[] labels = IntStream.range(0, 5)
    .parallel()
    .map(n -> counter.getAndIncrement())
    .toArray();
~~~

`AtomicInteger` makes incrementing atomic, yet **the value assigned to each element depends on execution scheduling**. Thus you cannot expect `labels` to always be `[0, 1, 2, 3, 4]`. This is a **business determinism** issue, not just a data race.

If you need each element's sequence number, use the source's index:

~~~java
int[] labels = IntStream.range(0, 5).parallel()
    .map(n -> n)
    .toArray();

// [0, 1, 2, 3, 4]
~~~

Or construct index-value pairs explicitly from an ordered `List`, rather than relying on a counter updated inside callbacks.

### 8.3. Do not mutate the source inside the pipeline

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

// Do not do this:
// source.parallelStream().forEach(source::add);
~~~

Modifying a Collection's structure while a Stream is traversing it can lead to errors, missing/duplicate data, or undefined behavior. Calling `sequential()` does not make source interference valid either; the non-interference rule still applies.

## 9. reduce and collect: associativity matters more than mode

For a pipeline to split and combine results across different groups, reduction functions must satisfy the API contract.

### 9.1. Integer addition within the proper value range

~~~java
import java.util.List;

List<Integer> numbers = List.of(10, 20, 30, 40);

long sequentialTotal = numbers.stream()
    .mapToLong(Integer::longValue)
    .sum();

long parallelTotal = numbers.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(sequentialTotal); // 100
System.out.println(parallelTotal);   // 100
~~~

`sum()` expresses the goal directly. With sufficiently large data, both `int` and `long` can overflow; choose an appropriate numeric domain or checked arithmetic as required.

### 9.2. Subtraction is not an associative reduction

~~~java
import java.util.List;

// This formula is unsuitable if you expect equivalence when parallel.
int wrong = List.of(10, 3, 2).parallelStream()
    .reduce(0, (left, right) -> left - right);
~~~

Subtraction is not associative and `0` is not a two-sided identity for subtraction. Different groupings can yield different results. Calling `sequential()` so an example "looks fine" **does not fix incorrect math** if it is meant as a general reduction.

If you want to subtract a total of discounts from an initial base amount, **sum the discounts first**, then subtract once:

~~~java
int base = 100;
int discounts = List.of(10, 3, 2).parallelStream()
    .mapToInt(Integer::intValue)
    .sum();

int payable = base - discounts;
System.out.println(payable); // 85
~~~

### 9.3. collect is not automatically thread-safe with external mutable state

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> result = List.of(1, 2, 3, 4).parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
~~~

A Collector uses supplier/accumulator/combiner to coordinate intermediate containers according to contract. Do not replace it with an external mutable `ArrayList` variable. `Collectors.toList()` **does not guarantee** that the returned List is mutable; if you genuinely need an `ArrayList`, use `Collectors.toCollection(ArrayList::new)`.

## 10. Stateful operations can make parallel execution inefficient

`sorted`, `distinct`, `limit`, `skip`, and certain other operations may require coordination across data partitions. Parallel mode does not eliminate that algorithmic cost.

| Operation | When parallel, may additionally require | Notes |
| --- | --- | --- |
| `sorted()` | Collecting/sorting, coordinating results | Incurs memory and comparison cost |
| `distinct()` | Deduplicating, preserving stability if ordered | `unordered()` sometimes relaxes constraints |
| `limit(n)` | Determining the first n elements in encounter order | Ordered sources can restrict speedup |
| `skip(n)` | Skipping the exact first n elements | May require coordination |
| `takeWhile()/dropWhile()` | Finding the prefix on an ordered stream | Unordered changes semantics |
| `forEachOrdered()` | Preserving action order | Can reduce parallel efficiency |

Example:

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> topFive = IntStream.range(0, 100_000)
    .parallel()
    .map(n -> 100_000 - n)
    .sorted()
    .limit(5)
    .boxed()
    .toList();

System.out.println(topFive); // [1, 2, 3, 4, 5]
~~~

`sorted` establishes the ordering, then `limit(5)` takes the first five values in that order. If the requirement is "the five smallest values," **do not** replace `sorted().limit(5)` with `unordered().limit(5)`.

### parallel is not always the faster choice

There is no hard rule like "use parallel from 10,000 elements upward." Benefits depend on per-element cost, source splittability, core count and machine load, ordering, data distribution, merging overhead, allocations, and GC. You must measure the actual workload.

## 11. Floating-point: the same algorithm may not yield identical bits

With `double`, addition has rounding error. Differences in how additions are grouped between sequential and parallel execution can make results differ in the least significant digits:

~~~java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

This is an IEEE 754 arithmetic property, not a sign that the Stream API is "wrong." When decimal exactness is required, consider `BigDecimal` with explicit scale and rounding policies. When testing floating-point sums, define an application-appropriate tolerance instead of always comparing bit-for-bit if the algorithm does not guarantee bitwise identity.

### Other stateful aggregations also require care

For statistical averages, you cannot simply average group averages if group sizes differ. You must keep **sum and count**, or use standard collectors/terminals such as `averagingDouble` or `summaryStatistics`, while understanding floating-point error bounds.

## 12. Writing a function that selects mode by configuration

An application may want to run the same transformation in both modes, for example allowing parallel mode to be enabled via configuration after benchmarking with appropriate data.

~~~java
import java.util.List;
import java.util.stream.Stream;

public class ConfigurablePipeline {
    static List<Integer> normalize(List<Integer> source, boolean parallel) {
        Stream<Integer> pipeline = source.stream();

        pipeline = parallel
            ? pipeline.parallel()
            : pipeline.sequential();

        return pipeline
            .filter(n -> n >= 0)
            .map(n -> n * 2)
            .toList();
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(3, -1, 5, 2);

        System.out.println(normalize(source, false)); // [6, 10, 4]
        System.out.println(normalize(source, true));  // [6, 10, 4]
    }
}
~~~

What this structure gets right:

1. Creates a **new Stream** from the Collection on each call.
2. Selects the mode only once, before the terminal operation.
3. Lambdas use no shared state and do not mutate the source.
4. `toList()` preserves the `List`'s encounter order even when running in parallel.
5. Does not attempt to reuse the same Stream for both modes.

### Checking mode inside a method

~~~java
static long sum(List<Integer> values, boolean runParallel) {
    Stream<Integer> stream = values.stream();
    stream = runParallel ? stream.parallel() : stream.sequential();

    // Queries mode without triggering traversal.
    boolean configuredParallel = stream.isParallel();
    if (configuredParallel != runParallel) {
        throw new IllegalStateException("Cấu hình mode không khớp");
    }

    return stream.mapToLong(Integer::longValue).sum();
}
~~~

`isParallel` is useful for testing **configuration selection**. It does not test whether the software actually speeds up, achieves desired concurrency, or executes across multiple threads.

## 13. Testing sequential and parallel semantics

A basic test should compare functional results in both modes, especially for pipelines with `filter`, `map`, `sorted`, or complex collectors.

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelSemanticsCheck {
    static List<Integer> process(boolean parallel) {
        IntStream stream = IntStream.rangeClosed(1, 100);

        stream = parallel
            ? stream.parallel()
            : stream.sequential();

        return stream
            .filter(n -> n % 3 == 0)
            .map(n -> n * n)
            .boxed()
            .toList();
    }

    public static void main(String[] args) {
        List<Integer> a = process(false);
        List<Integer> b = process(true);

        if (!a.equals(b)) {
            throw new AssertionError("Hai mode khác kết quả");
        }

        if (a.size() != 33) {
            throw new AssertionError("Số phần tử không đúng");
        }

        System.out.println("PASS");
    }
}
~~~

This test pattern works because `IntStream.rangeClosed` is an ordered source and the transformations under test are stateless and non-interfering. `toList()` preserves encounter order.

For pipelines that **do not require order** and return a `Set`, compare Set contents rather than `toString()` or iteration order. For `double` computations, choose a comparison strategy suited to your precision policy. When testing concurrency, do not use log order or thread names as pass/fail criteria for algorithm correctness.

### Avoid testing via side effects in peek

~~~java
import java.util.stream.IntStream;

// Do not use a counter inside peek as proof that
// every element was processed by the mapper.
long count = IntStream.range(0, 100)
    .parallel()
    .peek(n -> System.out.println("Seen: " + n))
    .count();
~~~

Some terminal operations like `count()` can leverage exact size information and optimize away intermediate steps that do not affect the result. Side-effect behavior in `peek` is not reliable proof of how many elements were traversed.

## 14. Resource constraints, I/O, and lifecycle management

Parallel streams are generally best suited to **CPU-bound** computations with splittable sources, sufficient per-element work, and pure callbacks. For long-blocking I/O such as HTTP calls or database queries, using `parallelStream()` can increase the number of waiting tasks and affect other work; if you need to manage concurrent request counts, timeouts, retries, or backpressure, use a dedicated orchestration mechanism.

**There is no guarantee** that a parallel stream uses a fixed number of threads that the application can configure independently via `parallel()`. Although implementations often use Fork/Join, correctness must not depend on pool names, thread counts, or tasks always running on a specific pool.

### Streams backed by resources still must be closed

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileLineCounter {
    static long countNonBlankLines(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path)) {
            return lines
                .parallel()
                .filter(line -> !line.isBlank())
                .count();
        }
    }
}
~~~

`try-with-resources` ensures the Stream is closed after the terminal operation completes or throws an exception. `parallel()` and `sequential()` do not replace resource-management obligations; nor do they guarantee that the file will be read or decoded efficiently in parallel. For ordered sources or sequential readers, source reading cost may be the main bottleneck.

## 15. Common pitfalls

### Pitfall 1: parallel() at the start and sequential() in the middle create two stages

~~~java
var values = List.of(1, 2, 3).stream()
    .parallel()
    .map(n -> n * 2)
    .sequential()
    .toList();
~~~

This is **one pipeline executing sequentially**; it is not that `map` ran in parallel and then the results switched to sequential. For two true stages, split into two terminal operations/pipelines using appropriate intermediate data.

### Pitfall 2: isParallel() true means multiple threads are active

`isParallel()` only confirms the requested mode. Source splittability, data size, and scheduling decide the actual execution. Do not use it as a measure of throughput or concurrency.

### Pitfall 3: parallel always breaks toList ordering

On sources with encounter order like `List`, `parallelStream().toList()` still preserves order. Only when the source or pipeline lacks encounter order does the resulting list have no guaranteed original order.

### Pitfall 4: sequential() fixes every race condition

Switching back to sequential may hide a bug temporarily, yet a lambda that mutates the source or depends on external state can still violate the Stream contract and make code fragile. Fix the root cause, do not just turn off parallelism.

### Pitfall 5: Double addition always gives the exact same bits as sequential

Floating-point addition is not strictly associative due to rounding. Switching modes can change how additions are grouped; choose arithmetic and testing models suited to your goals.

### Pitfall 6: adding parallel must be faster

With small sources, simple operations, or pipelines containing `sorted`, `limit`, or `distinct`, splitting/merging overhead can outweigh any gain. Decide only after measuring real load.

### Pitfall 7: a Stream can be run multiple times by changing its mode

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> once = List.of(1, 2, 3).stream();
long count = once.count();

// Cannot reuse: the stream has already been consumed.
// long other = once.parallel().count();
~~~

Streams have no built-in rewind mechanism. If you want to compare both modes, create two **new** Streams from the source or a valid Stream-producing Supplier:

~~~java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

List<Integer> source = List.of(1, 2, 3);
Supplier<Stream<Integer>> factory = source::stream;

long sequentialCount = factory.get().count();
long parallelCount = factory.get().parallel().count();
~~~

### Pitfall 8: unordered() is the same as sequential()

`unordered()` drops the **encounter order constraint**. `sequential()` selects **sequential execution mode**. The two operations solve completely different problems and can be combined when the business logic calls for it.

## 16. Mode selection table by requirement

| Problem | Initial choice | Reason |
| --- | --- | --- |
| Small list, cheap `map`/`filter` | `stream()` | Avoid parallel overhead |
| Large source, CPU-bound, easily splittable, stateless | Consider `parallelStream()` or `parallel()` | Potentially beneficial, but requires benchmarking |
| Must preserve exact result order | Can use either, keeping encounter order | `toList` and contract-compliant reductions still preserve order |
| Must execute side effects in sequence | Prefer sequential design or a separate coordination step | Avoid depending on thread scheduling |
| Need any matching element | `findAny()`, consider parallel | No need to keep the first element in order |
| Need the first element | `findFirst()` on an ordered source | Correct semantics; may incur coordination cost when parallel |
| Complex `sorted` / `distinct` / `limit` | Start sequential, then measure | Stateful operations can incur merge/sync overhead |
| Given a Stream that must be forced sequential | `sequential()` before terminal | Selects the mode for the pipeline |
| Need to know which mode was selected | `isParallel()` | Checks configuration, does not measure threads |
| Need strict thread pool, timeout, or backpressure control | Appropriate dedicated concurrency mechanism | Stream mode does not provide detailed orchestration contracts |

## 17. Self-check questions

1. **What does `stream().isParallel()` return by default?** `false` for `Collection.stream()`.
2. **What does `parallelStream().isParallel()` return by default?** `true`.
3. **What does `stream().parallel().sequential().isParallel()` return?** `false`, because the last mode selection is `sequential()`.
4. **What does `stream().sequential().parallel().isParallel()` return?** `true`.
5. **Does calling `parallel()` immediately start processing elements?** No; the pipeline remains lazy until the terminal operation.
6. **Does `isParallel() == true` guarantee multiple threads are processing?** No; it is a configuration state, not a thread metric.
7. **Can you run `map` in parallel and then `filter` sequentially in one pipeline by inserting `sequential()` in the middle?** No; the mode applies to the entire pipeline at execution time.
8. **Does `parallelStream().toList()` preserve the order of a `List`?** Yes, if the pipeline still has encounter order.
9. **Does `forEach()` on a parallel stream guarantee action order?** No; if actions must follow encounter order, use `forEachOrdered()`.
10. **Does `parallel()` mean `unordered()`?** No; they control two different aspects.
11. **Why can `AtomicInteger` inside a callback still be business-incorrect?** Even without an increment race, assigning sequence numbers depends on thread scheduling.
12. **Why is subtraction via `reduce(0, (a,b) -> a-b)` unsuitable for parallel reduction?** Subtraction is not associative and `0` is not a two-sided identity.
13. **How do you run the same algorithm in both modes to compare?** Create two new Streams from the same stable source, one sequential and one parallel.
14. **Why does Spliterator affect parallel performance?** It governs traversal, work splitting, and provides source metadata.
15. **For `double` addition, can parallel and sequential results differ slightly?** Yes, due to rounding error and different addition groupings.
16. **Does `sequential()` automatically close a File Stream?** No; resources must be closed via `try-with-resources` or equivalent management.
17. **When should parallelism be enabled?** When callbacks satisfy the contract, the source is splittable, per-element work is large enough, and benchmarks prove a benefit.

**Takeaway:** `parallel()` and `sequential()` set the **execution mode for the entire Stream pipeline**, while `isParallel()` only **reports the configured mode**. They do not create stage boundaries, do not independently determine result ordering, and do not guarantee thread count or speed. Keep processing functions stateless and non-interfering, use contract-compliant reductions, and measure actual performance before parallelizing.