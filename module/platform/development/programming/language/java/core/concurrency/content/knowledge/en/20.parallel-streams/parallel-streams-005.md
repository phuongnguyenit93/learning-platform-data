# Stateless Lambdas and Avoiding Shared Mutable State in Parallel Streams

## 1. The Problem: The Same Transformation Executed Across Multiple Threads

A `Stream` in Java describes a data-processing pipeline consisting of **source → intermediate operations → terminal operation**. Switching to `parallelStream()` or calling `parallel()` allows the Java Stream framework to split the work into multiple parts and potentially execute them on different threads. The lambda syntax usually stays the same, but **the conditions required for the operation to remain correct under concurrency** become critical.

For example, doubling each number is an independent transformation:

```java
List<Integer> doubled = numbers.parallelStream()
        .map(n -> n * 2)
        .toList();
```

This code is an *illustrative snippet*: the variable `numbers` must be defined in your program. Each result depends only on the element `n`, does not read or write mutable external variables, and does not modify the source. Therefore, the lambda `n -> n * 2` is **stateless** (it does not depend on any state that changes across invocations).

In contrast:

```java
List<Integer> output = new ArrayList<>();
numbers.parallelStream().forEach(n -> output.add(n * 2));
```

This is a **dangerous anti-pattern**, not a pattern to use in applications. `ArrayList` is modified concurrently by multiple threads; `add()` is not synchronized, which can drop elements, produce the wrong size, corrupt the internal structure, or lead to exceptions. A test run that "seems to produce the right result" must never be treated as proof of thread safety.

This lesson focuses on the **Java Stream API and plain Java concurrency**. It does not require Spring, framework schedulers, or asynchronous annotations.

### Learning Outcomes

After this lesson, you should be able to explain:

1. How stateless lambdas differ from stateful lambdas and side effects.
2. Why multiple callbacks accessing shared mutable state cause races and non-deterministic results.
3. How to replace `forEach + add` with `map`, `filter`, `sum`, `reduce`, `collect`, or a concurrent collector.
4. Why `ArrayList` can still appear safely inside `collect`, even though it is not a thread-safe collection.
5. The constraints regarding encounter order, stateful stream operations, thread safety, and performance when switching to a parallel stream.

## 2. Stateless Lambdas: A Property of Behavior, Not Syntax

A behavioral parameter such as `Predicate<T>`, `Function<T,R>`, `Consumer<T>`, or `BinaryOperator<T>` is considered **stateless** when the result or behavior of a single invocation does not depend on any state that may be modified by other invocations in the pipeline (or by external threads).

Good example:

```java
final int threshold = 10;

var values = List.of(4, 11, 16, 3);
var selected = values.parallelStream()
        .filter(n -> n > threshold)
        .map(n -> n * n)
        .toList();
```

`threshold` remains fixed while the pipeline runs; the predicate and mapper accumulate no state and do not modify the input data. This is a self-contained **illustrative code snippet** in terms of variables, which needs to be placed inside a method with `List` imported. For an ordered `List` source, `toList()` preserves encounter order, so `selected` corresponds to `[121, 256]`; whether the callbacks execute in the order 11 then 16 is a separate matter.

Stateful example:

```java
AtomicInteger sequence = new AtomicInteger();

List<String> labelled = items.parallelStream()
        .map(item -> sequence.getAndIncrement() + ":" + item)
        .toList();
```

This is an **anti-pattern of a stateful lambda**, even though `AtomicInteger` increments the counter atomically. The order in which numbers are assigned depends on thread scheduling and can vary across executions; `labelled` is still returned in the encounter order of `items`, but the sequence number attached to each element can be scrambled. If you need stable indices, express the index using the input data—for example, using `IntStream.range(0, items.size())` to map `i` with `items.get(i)` when the source is an unmodified list and indexed access is appropriate.

**Stateless does not mean the lambda captures no variables.** Capturing an immutable value like `threshold` is completely normal. Capturing a reference to a mutable object and repeatedly reading/writing its state can be stateful even if the reference variable itself is `final`.

```java
final List<Integer> sink = new ArrayList<>();
// 'sink' is never reassigned to another object, but sink.add(...) still mutates the object.
```

Java's rule requiring local variables captured by a lambda to be **final or effectively final** only prevents reassigning the local variable; it **does not automatically make the referenced object immutable or thread-safe**.

## 3. Shared Mutable State and Data Races

**Shared mutable state** is mutable state shared across multiple callback invocations or multiple threads—for example, an `ArrayList`, `HashMap`, `int[]`, a counter, an object with mutable fields, or a source element being updated.

Consider the following code, where `numbers` is a list of integers:

```java
List<Integer> results = new ArrayList<>();

numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .forEach(results::add); // WRONG if multiple threads write to the ArrayList concurrently
```

An `ArrayList` stores elements in an internal array and maintains `size`; concurrent `add` calls can read and write that state simultaneously. Without a proper synchronization relationship, this is a **data race** under the Java Memory Model. Symptoms can vary from run to run; there is no fixed number of lost elements to expect as sample output.

Imagine two calls operating on the `size` index at the same time:

```text
Thread A: read size = 5   → write element at index 5 → update size
Thread B: read size = 5   → write element at index 5 → update size
                                      ↑
                              May overwrite the result
```

This diagram models one possible interleaving, not a mandatory internal sequence for every `ArrayList` implementation. Using a non-thread-safe collection for shared writes across callbacks leaves the program with no correctness guarantees.

A `HashMap` does not become thread-safe just because you call `parallelStream()` either; concurrent additions or modifications must use proper synchronization or an appropriate concurrent collection.

### Data Races vs. Incorrect Results Due to Non-Deterministic Order

Even if you use `AtomicInteger` or `Collections.synchronizedList(...)` to eliminate the race on a **single operation**, the program can still have problems:

- Sequence numbers or computations depend on which thread runs first; atomicity is preserved, but the result is no longer stable in logical order.
- Multiple individual operations may require atomicity **across the entire sequence of operations** (check-then-act); a thread-safe single call does not make the whole workflow atomic.
- All workers contending on a single lock or atomic counter degrades performance.
- The source can still be modified concurrently outside the pipeline, violating the non-interference rule.

Therefore, "just use `synchronized`" is not the default approach to writing stream pipelines.

## 4. Two Core Requirements of the Stream API: Non-Interference and Statelessness

### Non-Interference: Do Not Modify the Source While the Stream Is Processing

In most cases, behavioral parameters must not modify a **non-concurrent data source** while the stream is traversing it. Incorrect example:

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));
source.parallelStream().forEach(source::remove);
```

This anti-pattern violates non-interference: the code modifies the very collection the stream uses as its source. It may throw errors, skip elements, or exhibit unstable behavior depending on the situation. If you need to remove elements, do so in a separate step after the pipeline finishes, or produce a new collection using `filter` and replace the reference in your data-management layer.

The rule has exceptions when the source is designed for concurrent modification, such as certain concurrent collections with a `CONCURRENT` spliterator; however, such sources have their own traversal semantics, which does not mean every modification produces a consistent or deterministic snapshot.

### Statelessness: The Same Input Should Not Depend on the Processing Schedule of Other Elements

Operations like `map`, `filter`, and `flatMap`, along with the predicates and mappers passed to them, should generally be pure per element. A stateless function is easy to test on individual inputs and safe to execute in parallel.

Example:

```java
int threshold = 100;
long count = orders.parallelStream()
        .filter(order -> order.total() >= threshold)
        .count();
```

This is an **illustrative code snippet** where `orders` contains elements with a `total()` method. The condition is that the order data is not modified while the pipeline runs. `count()` may apply optimizations based on the characteristics of the source and pipeline; do not add a side effect just to "count how many times the lambda is called" and expect it to equal the number of elements every time.

## 5. Distinguishing Stateful Lambdas from Stateful Intermediate Operations

A **stateful lambda** depends on mutable state outside itself or across invocations. It makes processing steps dependent on execution scheduling and hard to reason about for correctness.

A **stateful intermediate operation** is a standard Stream API operation with internal state managed by the library, such as `distinct()`, `sorted()`, `limit()`, or `skip()`. They are **not forbidden in parallel streams**: the implementation handles synchronization and merging according to its contract, though it may require buffering, coordination, or reduced throughput.

Valid example:

```java
List<Integer> unique = List.of(3, 1, 3, 2, 2)
        .parallelStream()
        .distinct()
        .sorted()
        .toList();
```

The result is `[1, 2, 3]`. This is a stateful operation managed by the Stream API, unlike creating a shared `HashSet` and calling `forEach(set::add)` inside a parallel pipeline.

**Do not assume** that "parallel streams cannot use `sorted` or `distinct`." What you need to measure is the cost of ordering, buffering, and output requirements—not to re-implement stateful algorithms yourself using side effects.

## 6. The Right Way: Express Processing Using `map`, `filter`, and Reduction

Instead of manually accumulating data into a shared collection, let the framework manage splitting and merging:

| Goal | Side-Effect Anti-Pattern | Preferred Approach |
| --- | --- | --- |
| Build a list of transformed elements | `forEach(result::add)` | `map(...).toList()` |
| Filter elements | `forEach(n -> { if (...) result.add(n); })` | `filter(...).toList()` |
| Count matching elements | `AtomicInteger.incrementAndGet()` | `filter(...).count()` |
| Sum numbers | `AtomicLong.addAndGet()` | `mapToLong(...).sum()` |
| Aggregate elements | Write to a shared variable in `forEach` | `reduce` with an associative combiner |
| Group elements | Shared `HashMap.computeIfAbsent(...).add(...)` | `collect(groupingBy(...))` or `groupingByConcurrent(...)` when appropriate |
| Build a map with duplicate keys | Unsynchronized `HashMap.put` | `toMap(..., mergeFunction)` or `toConcurrentMap(...)` |

**Terminal reductions** include `count()`, `sum()`, `min()`, `max()`, and `reduce()`. Each worker can compute its own portion and the framework combines the results without requiring application code to maintain a shared accumulator.

### `reduce` Requires an Identity and a Valid Associative Combiner

```java
int total = numbers.parallelStream()
        .reduce(0, Integer::sum);
```

This is an illustrative code snippet when `numbers` contains `Integer` values. For integer addition under Java semantics, `0` is the identity and addition is associative under modulo `(2^{32})` arithmetic, though a sum exceeding the limit can overflow. When business logic cannot tolerate overflow, use `long`, `Math.addExact`, or `BigInteger` as required.

In a parallel reduction, the combining function must be **associative**; if regrouping the execution changes the result, the program can be wrong.

Anti-pattern:

```java
int wrong = numbers.parallelStream().reduce(0, (a, b) -> a - b);
```

Subtraction is not associative: `(a - b) - c` differs from `a - (b - c)`. The parallel result can differ from the sequential one. For floating-point numbers, even addition is not strictly associative due to IEEE 754 rounding; accept minor numerical differences or choose a stable summation algorithm when high precision is required.

### `reduce` Is Not for Mutating a Shared Container

Do not try to use `reduce(new ArrayList<>(), ...)` and mutate the identity/accumulator list to mimic `collect`. For `reduce`, the accumulator must obey non-interference, associativity, and identity rules; mutating the same identity object can cause the same container to be used across multiple branches. **Mutable reduction** already has its own dedicated API: `collect`.

## 7. Complete Example 1: Stateless Lambdas Producing Stable Results

Run with **Java 17+**. Save the file as `ParallelStreamStatelessDemo.java`:

```java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelStreamStatelessDemo {
    public static void main(String[] args) {
        List<Integer> input = IntStream.rangeClosed(1, 12).boxed().toList();
        List<Integer> squares = input.parallelStream()
                .map(n -> n * n)
                .toList();
        int sumSquares = input.parallelStream()
                .mapToInt(n -> n * n)
                .sum();
        long evenCount = input.parallelStream()
                .filter(n -> n % 2 == 0)
                .count();

        System.out.println("size=" + squares.size());
        System.out.println("first=" + squares.get(0)
                + ", last=" + squares.get(squares.size() - 1));
        System.out.println("sumSquares=" + sumSquares);
        System.out.println("evenCount=" + evenCount);
    }
}
```

```bash
javac -encoding UTF-8 ParallelStreamStatelessDemo.java
java ParallelStreamStatelessDemo
```

```text
size=12
first=1, last=144
sumSquares=650
evenCount=6
```

Explanation:

1. `IntStream.rangeClosed(1, 12)` produces fixed data; `toList()` creates a list used as an unmutated source.
2. `map(n -> n * n)` uses only `n`. The framework may invoke the mapper for elements on multiple threads; the mapper does not need to maintain a shared sum or list.
3. `Stream.toList()` preserves the **encounter order** of an ordered stream. Because the input is an ordered list, `squares` has `1` as its first element and `144` as its last, even though the internal execution schedule is unordered.
4. `mapToInt(...).sum()` combines the partial sums, yielding `1² + 2² + ... + 12² = 650`; `filter(...).count()` yields `6` even numbers.
5. `Stream.toList()` returns an **unmodifiable** list on Java 17+. If you want a separate `ArrayList` that can be mutated after the pipeline finishes, you can create `new ArrayList<>(result)` in a subsequent step.

In this example, the main benefit is **correctness and clarity**. With 12 elements and a very lightweight operation, parallel execution is usually not faster than sequential execution; the overhead of splitting work can exceed the actual computation.

## 8. Proper Mutable Reduction: `collect` with Independent Temporary Containers

A common misconception is: "`ArrayList` is not thread-safe, so `parallelStream().collect(...)` cannot use `ArrayList`." That is false when using a collector or mutable reduction according to its contract.

For a standard collector without the `CONCURRENT` characteristic, the Stream framework creates **independent accumulators** for different branches, invokes the accumulator on each container in the appropriate branch, and then merges them using the combiner. It does **not** mean all workers call `add` on a **single shared `ArrayList`**.

```java
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 2)
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

This is an **illustrative code snippet** requiring `List` and `ArrayList` to be imported and `numbers` to be defined.

The three functions have clear roles:

- **Supplier `ArrayList::new`**: creates a new empty container.
- **Accumulator `ArrayList::add`**: adds an element to the current branch's container.
- **Combiner `ArrayList::addAll`**: merges the result containers from two branches.

The framework is responsible for coordinating the containers. Never pass the **exact same shared instance** into the supplier:

```java
List<Integer> shared = new ArrayList<>();
// WRONG: the supplier returns the exact same object for every branch.
var bad = numbers.parallelStream()
        .collect(() -> shared, List::add, List::addAll);
```

This anti-pattern can cause races, merge data into itself, and violate the `collect` contract. The supplier must provide a fresh, independent container according to the contract.

`Collectors.toList()` is also a normal choice:

```java
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 2)
        .collect(Collectors.toList());
```

`Collectors.toList()` **makes no guarantees** about the implementation type, mutability, or thread safety of the returned collection; therefore, you should not cast it to `ArrayList` or assume it can be mutated afterward. It is still designed to be used safely during parallel `collect` under the contract. If a specific collection type is required, use `Collectors.toCollection(ArrayList::new)`.

## 9. Complete Example 2: Concurrent Grouping and Local Accumulator Collection

To count word occurrences, you should not use a shared `HashMap<String, Integer>` and `put`/increment counters inside `forEach`. Java provides concurrent collectors for appropriate cases.

Save the file as `ParallelCollectorDemo.java` (Java 17+):

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelCollectorDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "java", "stream", "java", "parallel", "stream", "java");
        ConcurrentMap<String, Long> counts = words.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        Function.identity(), Collectors.counting()));

        System.out.println("java=" + counts.get("java"));
        System.out.println("stream=" + counts.get("stream"));
        System.out.println("parallel=" + counts.get("parallel"));

        List<Integer> doubled = IntStream.rangeClosed(1, 6)
                .boxed()
                .parallel()
                .map(n -> 2 * n)
                .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
        System.out.println("doubled=" + doubled);
    }
}
```

```bash
javac -encoding UTF-8 ParallelCollectorDemo.java
java ParallelCollectorDemo
```

```text
java=3
stream=2
parallel=1
doubled=[2, 4, 6, 8, 10, 12]
```

Explanation:

- `groupingByConcurrent` returns a concurrent and unordered collector, allowing coordinated grouping in a parallel pipeline. The result is a `ConcurrentMap`, which supports concurrent access and updates according to its implementation contract.
- `Collectors.counting()` is used as the downstream collector; the library coordinates updating the value for each key according to collector semantics, without requiring you to share a `long[]` or a plain `HashMap`.
- Do not print `counts` directly expecting a predictable key order: a concurrent map does not provide a stable iteration order. Printing values for specific keys gives deterministic output.
- In the `collect(ArrayList::new, ...)` section, the `ArrayList` instances are temporary containers for reduction, and the final result still preserves encounter order for an ordered stream source.
- `groupingByConcurrent` can perform well when the dataset is large enough and grouping does not depend on encounter order; it is not automatically faster than `groupingBy` in all cases, especially when a small number of keys causes contention on the same groups.

If you need to preserve encounter order within each group, use an appropriate collector such as `groupingBy` with an ordered source and the desired downstream collector, then evaluate the parallel overhead. `groupingByConcurrent` itself does not guarantee the order of elements within a group.

## 10. `forEach`, `forEachOrdered`, `peek`, and Side Effects

### `forEach` Does Not Preserve Encounter Order

```java
List.of(1, 2, 3, 4).parallelStream()
        .forEach(System.out::println);
```

This snippet is runnable when placed inside a method with `List` imported. The lines may appear in **any order**; you should not write an expected stdout of `1,2,3,4` for this program. The fact that `PrintStream.println` has internal synchronization does not restore the logical order of elements.

### `forEachOrdered` Preserves the Encounter Order of an Ordered Source

```java
List.of(1, 2, 3, 4).parallelStream()
        .forEachOrdered(System.out::println);
```

With an ordered `List` source, the output is `1`, `2`, `3`, `4` in order. The Stream API applies the necessary ordering and synchronization between `forEachOrdered` actions, which can reduce the benefits of parallelism. This does not mean all intermediate callbacks run in order, nor does it mean you can freely mutate an external object in other stages without synchronization.

If the goal is simply to create a transformed list, `map(...).toList()` remains more direct and clearer.

### `peek` Is Not a Tool for Business Side Effects

```java
AtomicInteger counter = new AtomicInteger();
long size = numbers.parallelStream()
        .peek(n -> counter.incrementAndGet())
        .count();
```

This is an **anti-pattern**: for some sources or pipelines, `count()` can deduce the result without traversing the elements, so `peek` is not guaranteed to be called for every element. `AtomicInteger` avoids a race on the counter, but it does not turn `peek` into a guaranteed side-effect contract. `peek` is useful for cautious diagnostics, not as a standard way to produce results or update business state.

In general, Java Streams may optimize away and skip evaluating certain stages if doing so does not affect the terminal result under the contract. Therefore, never build critical logic on the side effects of `map`, `filter`, or `peek`.

## 11. Associativity, Identity, and Result Ordering

For parallel reduction, the framework is allowed to split data into partitions and combine them in a tree, so the combining operation must be **associative** and have an appropriate identity.

Consider string concatenation: if you only need the final combined string, a `joining` collector can coordinate multiple internal buffers. However, if an algorithm expects the "earlier element" in the result to depend on which worker finishes first, that is a scheduling dependency, not stream logic.

Three types of "order" to distinguish:

1. **Encounter order**: the logical order of elements from the source, such as `List.of("a","b","c")`.
2. **Execution order**: the actual order in which callbacks run; in a parallel stream, this may differ from encounter order.
3. **Result order**: the output order guaranteed by the terminal operation. `toList()` preserves encounter order if present, `forEach` does not guarantee it, `forEachOrdered` does, and `groupingByConcurrent` does not guarantee encounter order.

For an ordered stream, `findFirst()` respects the first element in encounter order. `findAny()` allows selecting any element to improve the chance of fast completion in parallel; do not use `findAny()` if business logic requires the "first" result.

`unordered()` can unlock certain optimizations when the algorithm does not depend on order, but it should only be called when the output genuinely permits dropping encounter order.

## 12. Why a Thread-Safe Collection Is Not Necessarily the Best Design

When there is an **intentional** requirement to write to a shared resource outside the stream (for example, telemetry or a sink whose API cannot be changed), proper synchronization and side-effect control are needed. However:

- `Collections.synchronizedList(new ArrayList<>())` synchronizes each individual operation on the list; it still does not guarantee source processing order when used with `parallel().forEach`.
- `ConcurrentLinkedQueue` allows concurrent appending, but does not guarantee that the queue order matches the source's encounter order.
- `ConcurrentHashMap` supports atomic updates such as `merge` and `compute` under its contract; you must still choose the right remapping function and avoid placing unprotected mutable state inside it.
- `AtomicInteger`/`LongAdder` are suitable for certain concurrent counters, but incur sharing overhead, and you should still use `count()` if you only need the total number of elements in a pipeline.

If a task must call an external API, update a database, or write to a file, that is a side effect **outside the collection model**: thread safety of Java objects alone is not enough to guarantee idempotency, ordering, transactions, or retryability. You can run those sequentially or separate the side effects into a distinct step after pure data computation.

Repeated `map` or terminal operations on the same source may execute on different threads; do not use `ThreadLocal` as a map from "data element" to "fixed bucket" and expect consistent ordering. A stream does not assign a single fixed thread to each element.

## 13. Mutable Input Elements Can Also Cause Races

Keeping the source `List` unmodified is **not enough** if the elements inside it have mutable fields.

Error-prone example:

```java
customers.parallelStream()
        .forEach(customer -> customer.setPoints(customer.getPoints() + 1));
```

This is an illustrative code snippet; `Customer` must be defined. If each element is genuinely a **distinct object** and is not accessed concurrently from outside, mutating each object might not race across stream elements, but it still creates hard-to-control side effects. If the list contains **multiple references pointing to the same `Customer`**, or another thread is modifying those objects, multiple callbacks can read/write the same state and lose updates.

An approach that is easier to reason about is creating new immutable values:

```java
record Customer(String id, int points) {}

List<Customer> updated = customers.parallelStream()
        .map(c -> new Customer(c.id(), c.points() + 1))
        .toList();
```

This is an **illustrative snippet** requiring `customers` and `List` in context. Here, `record` holds immutable `String` and `int` fields; for a record containing a `List` or mutable object, using `record` alone **does not automatically provide deep immutability**.

If the source or object graph is modified concurrently while the stream runs, you need a safe snapshot, immutable data, or a clear concurrency contract; reading data via `List.copyOf(source)` only copies the list structure, not the objects inside.

## 14. When Should You Use a Parallel Stream?

Parallel streams are most useful when there are enough elements, each element involves significant CPU work, the operations are independent, the reduction can combine efficiently, and the cost of splitting and merging is smaller than the time saved. It is not a "flip a flag and the app automatically gets faster" feature.

Influencing factors:

- **Volume and complexity**: a few dozen small additions incur high overhead compared to a sequential stream.
- **Spliterator/source**: `ArrayList` and arrays generally split easily, whereas some sources are hard to split or costly to convert.
- **Ordering**: `sorted`, `limit`, and `findFirst` on ordered streams may require coordination.
- **Collector**: the cost of creating and merging many containers can be high; concurrent collectors can suffer contention when there are few keys.
- **Shared resources**: the common `ForkJoinPool` is used by the Stream framework in typical situations and can be affected by other parallel work in the same JVM; you should not assume the pool is always idle or has a fixed number of threads matching the machine.
- **Blocking I/O**: `parallelStream()` is not a good default coordinator for batches of blocking requests; you need dedicated concurrency and deadline management, and should consider an executor suited to the workload's characteristics.

If you need to compare performance, measure a representative workload in both sequential and parallel modes, warm up the JVM sufficiently, choose a large enough input, inspect GC/CPU, and use an appropriate benchmarking tool such as JMH. **Always prove correctness before measuring speed.**

## 15. Checklist for Reviewing a Parallel Pipeline

When reading a pipeline, you can ask these questions in turn:

1. **Is the source modified concurrently?** If so, is it a concurrent source designed for that, and do its semantics satisfy business requirements?
2. **Does the lambda read or write external state that changes over time?** If so, can that state be turned into an input or a result structure?
3. **Is `forEach` used just to add to a shared collection?** Usually replace it with `map`/`filter`/`collect`.
4. **Does the reduction have an identity and an associative combining function?** If not, the result may change depending on how work is partitioned.
5. **Is there an assumption that callbacks run in source order or on a specific thread?** Parallel streams make no such promise.
6. **Are atomics or `synchronized` being used to mask a computation that could be expressed as a reduction?** Prefer direct reduction and compare performance.
7. **Does logic depend on side effects in `peek` or intermediate operations?** Streams are allowed to optimize them away, so such logic is unreliable.
8. **What ordering, mutability, and thread-safety guarantees does the output need?** Choose `toList`, `toCollection`, `groupingBy`, or `groupingByConcurrent` according to their contracts.
9. **Has the result been tested with duplicate keys, empty inputs, large inputs, and repeated runs?** Race bugs sometimes appear only under real load.
10. **Does parallelism actually benefit this workload?** If not, a sequential stream with stateless lambdas remains a very good choice.

## 16. Mini Exercises and Answers

**Exercise 1.** Is the following code safe with a parallel stream?

```java
List<String> out = new ArrayList<>();
input.parallelStream().map(String::trim).forEach(out::add);
```

**Answer:** Not safe, because multiple threads concurrently modify the `ArrayList`. Use `List<String> out = input.parallelStream().map(String::trim).toList();`; only create a mutable copy afterward if genuinely needed.

**Exercise 2.** If we replace `ArrayList` with `Collections.synchronizedList`, will the result preserve input order?

**Answer:** No. It protects each `add()` call, but `forEach` on a parallel stream does not guarantee encounter order. If input order is needed, use an ordered source and `toList()` or an appropriate collector.

**Exercise 3.** Is `map(n -> atomicCounter.getAndIncrement())` stateless just because it uses an atomic?

**Answer:** No. It has no data race on the counter, but the mapped values depend on the execution order of invocations, meaning it depends on shared state.

**Exercise 4.** Does `collect(ArrayList::new, ArrayList::add, ArrayList::addAll)` concurrently call `add` on a single `ArrayList`?

**Answer:** No. Branches have their own accumulator containers under the contract, and the framework calls the combiner to merge them; the supplier must return a new container.

**Exercise 5.** `distinct()` is a stateful operation; must it be banned in parallel streams?

**Answer:** No. It is a library operation designed for use with streams, though it may incur coordination overhead. It is different from a lambda manually reading/writing a shared `HashSet`.

**Exercise 6.** Does `parallelStream().forEachOrdered(...)` force all preceding `map` stages to run sequentially?

**Answer:** No. This terminal operation preserves the order in which the action is invoked according to encounter order when the source is ordered, but preceding stages can still execute in parallel.

## 17. Concept Summary

**Stateless lambdas** depend only on the current invocation's input and immutable context; **non-interference** avoids modifying the source while the stream is processing; **reductions/collectors** delegate result coordination to the Stream framework. These three principles keep a pipeline correct when switching from `stream()` to `parallelStream()`.

Whenever you see a `forEach` writing into a shared `ArrayList`, `HashMap`, or counter, identify what the real goal is—building a list, filtering, counting, summing, or grouping data. Expressing that goal directly with `map`, `filter`, `count`, `sum`, `reduce`, `collect`, or an appropriate concurrent collector makes the code easier to test and gives the framework room to optimize.

### References

- [Java SE 17 – java.util.stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): non-interference, stateless behavioral parameters, side effects, reduction.
- [Java SE 17 – Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `parallel`, `map`, `forEach`, `forEachOrdered`, `collect`, `toList`.
- [Java SE 17 – Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): `toList`, `groupingBy`, `groupingByConcurrent`, `toConcurrentMap`.
- [Java SE 17 – ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): synchronization notes when multiple threads modify a list.
