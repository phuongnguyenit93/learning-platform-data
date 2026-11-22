# parallelStream(), parallel(), and sequential() in Java

The Java Stream API supports two **execution modes** for a pipeline: **sequential** and **parallel**. Sequential mode is usually easier to reason about and has lower coordination overhead. Parallel mode allows the Stream framework to split work for processing across multiple threads when appropriate, but **does not guarantee** that every pipeline will use multiple threads or run faster.

The three most common APIs are:

- **`collection.parallelStream()`**: creates a Stream **initially in parallel mode** from a `Collection`.
- **`stream.parallel()`**: requests the Stream pipeline to **switch to parallel mode**.
- **`stream.sequential()`**: requests the Stream pipeline to **switch to sequential mode**.

For comparison, regular `collection.stream()` creates a sequential Stream. Both modes can use intermediate and terminal operations such as `map`, `filter`, `collect`, `reduce`, and `toList`, but how work is executed internally and what guarantees exist for callback ordering need to be understood accurately.

**Most important point:** `parallel()` and `sequential()` are operations that configure the mode of **the entire pipeline when the terminal operation executes**, not a promise that the `map` segment before `parallel()` runs sequentially while the `map` segment after it runs in parallel. If a pipeline calls mode-switching methods multiple times, **the last mode choice** is the one that takes effect at execution time.

This lesson focuses on syntax, the target of each API, lazy evaluation, encounter order, `forEach`/`forEachOrdered`, proper `reduce`/`collect`, shared mutable state, and how to decide whether to use parallel processing.

## 1. What are sequential and parallel Streams?

A Stream is a **pipeline of operations over a data source**, not a collection that already stores transformed results. A pipeline typically consists of:
1. **Source**: `List`, array, `IntStream` range, or another source.
2. **Intermediate operations**: `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`, etc., which are usually **lazy**.
3. **Terminal operation**: `toList`, `collect`, `sum`, `reduce`, `count`, `forEach`, `findFirst`, etc., which triggers execution.

In **sequential** mode, the pipeline uses sequential evaluation. In **parallel** mode, the library **may** split work into parts, process them on multiple threads, and then combine the results, though scheduling details are an implementation detail.

Illustrative code inside a method:

```java
List<Integer> source = List.of(1, 2, 3, 4, 5);

List<Integer> sequential = source.stream()
        .map(n -> n * n)
        .toList();

List<Integer> parallel = source.parallelStream()
        .map(n -> n * n)
        .toList();
```

This requires importing `java.util.List`. With an ordered List source, both results are `[1, 4, 9, 16, 25]`. However, **having the same ordered result does not prove that the two pipelines ran with the same schedule**.

**Important distinction**: parallel mode does not mean asynchronous execution in the sense of returning a `Future`. A terminal operation such as `toList()` normally **waits for the result to complete** before returning the list. Parallel Streams also do not automatically provide retry, timeout, transaction, or arbitrary task cancellation mechanisms according to application needs.

## 2. collection.parallelStream(): creating a source in parallel mode

`parallelStream()` is a method on the **`Collection<E>`** interface, so collections such as `List` or `Set` provide this API.

```java
List<String> items = List.of("A", "B", "C");
Stream<String> work = items.parallelStream();
boolean parallel = work.isParallel(); // true
```

This is a code snippet requiring imports for `java.util.List` and `java.util.stream.Stream`. `isParallel()` checks the **Stream's mode flag**, not the number of active worker threads.

Common sources:

```java
Stream<Integer> a = numbers.stream();         // sequential
Stream<Integer> b = numbers.parallelStream(); // parallel
```

Here `numbers` is an existing `Collection<Integer>`. **There is no `parallelStream()` on a `Stream` object** in the `Stream` API. If you already have a Stream, use `parallel()`.

Correct and incorrect examples to distinguish:

```java
Stream<Integer> s = numbers.stream().parallel(); // correct
// numbers.stream().parallelStream(); // WRONG: Stream does not have parallelStream()
```

`parallelStream()` does not turn the collection itself into a "parallel collection". Each call creates a new Stream; when a terminal operation is invoked, the Stream traverses the source in accordance with its contract. You must not modify the source being traversed if doing so violates the non-interference requirement.

### Should you use parallelStream() on every Collection?

No. For example, a very small List with only a few elements and simple calculations usually does not have enough work to offset the overhead of splitting and merging. A source that is difficult to split may not utilize parallelism as well as an array, `ArrayList`, or `IntStream.range`.

If the source has no defined **encounter order**, such as a `HashSet`, parallelism does not automatically create a stable order. Do not write unit tests assuming that `HashSet.parallelStream().toList()` will always preserve the exact order observed in one run.

## 3. stream.parallel(): switching the pipeline's mode

`parallel()` is a method of `BaseStream` and is available on object streams as well as primitive streams:

```java
Stream<Integer> s = numbers.stream().parallel();
IntStream ints = IntStream.rangeClosed(1, 10).parallel();
LongStream longs = LongStream.of(10L, 20L).parallel();
DoubleStream doubles = DoubleStream.of(1.0, 2.0).parallel();
```

This snippet requires the corresponding imports from `java.util.stream`; `numbers` is an existing Collection. Each element is not turned into a separate thread. The framework decides how to execute, split data, and combine results.

A pipeline can be configured as follows:

```java
List<Integer> result = numbers.stream()
        .filter(n -> n > 0)
        .parallel()
        .map(n -> n * 2)
        .toList();
```

It is **one** pipeline configured as parallel, not a `filter` part guaranteed to have finished running sequentially before `parallel` was called. Intermediate operations normally do not run until the terminal operation starts.

**Calling `parallel()` does not execute data by itself.** To get a result, you still need a terminal operation such as `toList`, `collect`, or `sum`.

## 4. stream.sequential(): returning to sequential mode

`sequential()` is also a method of `BaseStream`; it requests the pipeline to execute sequentially:

```java
Stream<Integer> s = numbers.parallelStream().sequential();
boolean parallel = s.isParallel(); // false
```

You can use `sequential()` when a pipeline initially comes from a parallel source but needs to avoid overhead, needs simpler sequential behavioral logic, or needs to make the choice explicit in a specific context.

**Do not use `sequential()` to "fix" a callback with contract-violating side effects.** A sequential pipeline can still be wrong if it modifies the source being traversed, uses an incorrect operation, or depends on invalid state. Sequential mode only changes the execution mechanism; it does not guarantee that every callback is safe and correct.

### The last choice determines the mode

```java
Stream<Integer> a = numbers.stream().parallel().sequential();
Stream<Integer> b = numbers.parallelStream().sequential().parallel();

// a.isParallel() -> false
// b.isParallel() -> true
```

The two lines above create two new pipelines. Even though the code reads from left to right, mode-switching calls **do not split the pipeline into independent execution phases**.

If you genuinely need "compute phase 1 sequentially, save the result, then run phase 2 in parallel", **materialize the result of phase 1** (for example using `toList()`) and then create **a new Stream** from that result:

```java
List<Integer> phaseOne = numbers.stream()
        .map(n -> n * 2)
        .toList();

List<Integer> phaseTwo = phaseOne.parallelStream()
        .map(n -> n + 1)
        .toList();
```

This is a snippet where `numbers` is a numeric Collection. Only then is there a real boundary between two terminals/pipelines, and the application will incur the cost of storing intermediate results. Do not force phase splitting when there is no reason to.

## 5. Java 17 program: comparing the three APIs and the final mode

Save as **`ParallelModeSwitchDemo.java`**:

```java
import java.util.List;
import java.util.stream.Stream;

public class ParallelModeSwitchDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

        Stream<Integer> fromStream = numbers.stream();
        Stream<Integer> fromParallel = numbers.parallelStream();
        Stream<Integer> switchedToSequential =
                numbers.stream().parallel().sequential();
        Stream<Integer> switchedBackToParallel =
                numbers.parallelStream().sequential().parallel();

        System.out.println("streamParallel=" + fromStream.isParallel());
        System.out.println("parallelStreamParallel=" + fromParallel.isParallel());
        System.out.println("switchedSequential="
                + switchedToSequential.isParallel());
        System.out.println("switchedParallel="
                + switchedBackToParallel.isParallel());

        System.out.println("streamResult=" + fromStream
                .map(n -> n * n).toList());
        System.out.println("parallelResult=" + fromParallel
                .map(n -> n * n).toList());
        System.out.println("sequentialAgain=" + switchedToSequential
                .map(n -> n + 1).toList());
        System.out.println("parallelAgain=" + switchedBackToParallel
                .map(n -> n + 1).toList());
    }
}
```

Compile and run with JDK 17:

```bash
javac -encoding UTF-8 ParallelModeSwitchDemo.java
java ParallelModeSwitchDemo
```

**Exact stdout:**

```text
streamParallel=false
parallelStreamParallel=true
switchedSequential=false
switchedParallel=true
streamResult=[1, 4, 9, 16, 25, 36]
parallelResult=[1, 4, 9, 16, 25, 36]
sequentialAgain=[2, 3, 4, 5, 6, 7]
parallelAgain=[2, 3, 4, 5, 6, 7]
```

Because the input is a List with an encounter order, `toList()` preserves result order in both modes. The `isParallel()` flag reflects the chosen mode, not a throughput measurement or proof of thread count.

Each Stream in the example is used for **exactly one terminal operation** and no more. Do not call `toList()`, `count()`, or `sum()` again on an already-consumed Stream. To run again, create a new Stream from the source.

## 6. Encounter order differs from execution order

**Encounter order** is the element order defined by the source and pipeline. For `List.of("A","B","C","D")`, the encounter order is A, B, C, D. **Execution order** is the order in which operations actually happen when the framework evaluates the pipeline.

In a parallel stream:
- `map`, `filter`, or lambdas may be executed on elements in a different order.
- Workers may finish their work at different times.
- Some terminal operations still **must preserve encounter order** in the result, if the Stream has an order and the terminal requires it.
- `forEach` **does not guarantee** action order; `forEachOrdered` guarantees encounter order, but does not force all upstream steps to run sequentially.

| API | On an ordered parallel Stream | Practical meaning |
| --- | --- | --- |
| `toList()` | Preserves encounter order | Result has stable order; internally may be parallel |
| `collect(Collectors.toList())` | Suitable collector preserves encounter order | Do not infer a specific List implementation type |
| `forEach(action)` | Does not guarantee action order | Do not use for logging that requires strict order |
| `forEachOrdered(action)` | Actions run in encounter order | May incur coordination overhead |
| `findFirst()` | Picks first element in encounter order when present | Ordering constraint may increase cost |
| `findAny()` | May pick any matching element | Do not rely on always returning the first element |
| `unordered()` | Removes encounter order constraint | Does not mean random shuffling |

**Order in the resulting List and side-effect order are not the same.** For example, `parallelStream().map(...).toList()` can produce a properly ordered list even if `map` calls finish out of order. Do not use the output list to infer callback execution order.

## 7. Java 17 program: ordered output despite parallel processing

Create the file **`ParallelOrderDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class ParallelOrderDemo {
    public static void main(String[] args) {
        List<String> words = List.of("A", "B", "C", "D");

        List<String> result = words.parallelStream()
                .map(word -> word.toLowerCase(Locale.ROOT))
                .toList();

        System.out.println("result=" + result);

        System.out.print("orderedAction=");
        words.parallelStream().forEachOrdered(System.out::print);
        System.out.println();

        System.out.println("first=" + words.parallelStream()
                .findFirst()
                .orElse("-"));

        boolean anyBelongs = words.parallelStream()
                .findAny()
                .filter(words::contains)
                .isPresent();
        System.out.println("anyBelongs=" + anyBelongs);
    }
}
```

Run commands:

```bash
javac -encoding UTF-8 ParallelOrderDemo.java
java ParallelOrderDemo
```

**Exact stdout:**

```text
result=[a, b, c, d]
orderedAction=ABCD
first=A
anyBelongs=true
```

`findAny()` may return A, B, C, or D. The program **does not print the chosen value**, but only checks whether it belongs to the list; because of that, stdout is deterministic. `forEachOrdered` prints ABCD because the List source is ordered.

If `forEachOrdered` is replaced with `forEach` on a parallel Stream, the example cannot promise to print ABCD. It might happen to be in order on a few runs, but that is not the API contract.

With `findFirst` on an **unordered** Stream, you should not infer a fixed first element, because the source/pipeline carries no encounter-order requirement.

## 8. Laziness: changing mode does not execute intermediate operations

Intermediate operations like `map` and `filter` are usually **lazy**. For example:

```java
Stream<Integer> pipeline = numbers.stream()
        .filter(n -> n % 2 == 0)
        .parallel()
        .map(n -> n * 10);

// No terminal operation yet at this point.
List<Integer> result = pipeline.toList();
```

This is a snippet requiring `List`, `Stream`, and an existing `numbers` collection. Calling `parallel()` does not immediately run `filter` or `map`; `toList()` is what demands the result.

Laziness implies:
- A `Stream` is usually consumed **only once**. Do not reuse a pipeline that has already had a terminal operation.
- Short-circuit operations may not traverse all elements if the termination condition is already satisfied.
- In parallel, there may still be work running in other parts when a terminal decides to stop.
- Do not place **mandatory side effects** inside `peek` or `map` and expect each source element to definitely produce one log entry. The JDK may optimize away some steps if they do not affect the terminal result according to the Stream contract.

With `count()` on a source of known size and steps that do not change the element count, an implementation may know the result without calling every mapper; therefore `peek(System.out::println)` should not be used as a tool to guarantee "every element passed through".

## 9. Correct reduce when processing in parallel

`reduce` combines elements according to an operation. In parallel, the framework may compute results for parts and then combine them, so the operator must be **associative** and have a valid identity if using an overload with an identity.

- **Associativity:** `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)`.
- **Identity:** `e ⊕ a = a` and `a ⊕ e = a`.

Correct example with small data:

```java
int total = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .reduce(0, Integer::sum); // 55
```

Addition has identity 0, suitable for parallel combination in the example. Conversely:

```java
int unreliable = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .reduce(0, (a, b) -> a - b);
```

The second snippet **compiles but does not have the intended reduction semantics**: subtraction is not associative, so the result may differ from sequential left-to-right reduction. Do not assume a fixed stdout for that snippet.

### Another trap: mutable accumulator in reduce

The following pattern should not be used:

```java
// INTENTIONALLY WRONG BY DESIGN, especially dangerous with parallel:
List<Integer> values = java.util.stream.IntStream.rangeClosed(1, 10)
        .boxed()
        .parallel()
        .reduce(
            new java.util.ArrayList<Integer>(),
            (list, number) -> {
                list.add(number);
                return list;
            },
            (left, right) -> {
                left.addAll(right);
                return left;
            }
        );
```

This is an **unsafe** illustration: a mutable identity can be used and modified by multiple reduction branches; that violates the reduction contract and can corrupt the result. Use `collect` to create independent containers for work partitions.

Also note that `int`/`long` sums can overflow with large data, and `double` has rounding errors depending on how additions are grouped. Parallel mode does not solve those arithmetic limits.

## 10. Correct collect: let the framework manage state

If the goal is to gather elements into a List, Set, or Map, use an appropriate collector instead of modifying a shared collection from `forEach`.

```java
List<Integer> values = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .boxed()
        .toList();
```

On Java 17, `Stream.toList()` returns an **unmodifiable List** via the API and preserves encounter order for ordered sources. If you need a mutable List, use:

```java
List<Integer> mutable = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .boxed()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));
```

These are two independent snippets, importing `List`. `Collectors.toCollection(ArrayList::new)` chooses the result container type. With a parallel Stream, the framework can create multiple containers and merge them; it **does not require** you to manually use `synchronizedList` to update a single shared List outside the pipeline.

Example of grouping by a property:

```java
Map<Integer, Long> counts = words.parallelStream()
        .collect(java.util.stream.Collectors.groupingBy(
                String::length,
                java.util.TreeMap::new,
                java.util.stream.Collectors.counting()
        ));
```

This is a snippet where `words` has type `Collection<String>` and `java.util.Map;` is imported. `TreeMap` ensures that printing the Map displays keys in ascending order, rather than depending on HashMap iteration order.

**A Collector does not have to have the `CONCURRENT` characteristic to be used in a parallel Stream.** A normal collector can be applied by the framework to independent states and then combined. Only collectors that genuinely support concurrent updates on the same state and meet the relevant conditions should declare `CONCURRENT`.

## 11. Java 17 program: safe reduce and collect in parallel

Save as **`ParallelAggregationDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelAggregationDemo {
    public static void main(String[] args) {
        int sequentialSum = IntStream.rangeClosed(1, 10).sum();
        int parallelSum = IntStream.rangeClosed(1, 10)
                .parallel()
                .reduce(0, Integer::sum);

        List<Integer> evens = IntStream.rangeClosed(1, 10)
                .parallel()
                .filter(n -> n % 2 == 0)
                .boxed()
                .toList();

        List<String> words = List.of("a", "bb", "ccc", "dd");
        Map<Integer, Long> lengthCounts = words.parallelStream()
                .collect(Collectors.groupingBy(
                        String::length,
                        TreeMap::new,
                        Collectors.counting()
                ));

        String joined = words.parallelStream()
                .collect(Collectors.joining("-"));

        System.out.println("sequentialSum=" + sequentialSum);
        System.out.println("parallelSum=" + parallelSum);
        System.out.println("evens=" + evens);
        System.out.println("lengthCounts=" + lengthCounts);
        System.out.println("joined=" + joined);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ParallelAggregationDemo.java
java ParallelAggregationDemo
```

**Exact stdout:**

```text
sequentialSum=55
parallelSum=55
evens=[2, 4, 6, 8, 10]
lengthCounts={1=1, 2=2, 3=1}
joined=a-bb-ccc-dd
```

In the example:
- `Integer::sum` with identity 0 produces a consistent result for the sum of 1..10.
- `evens` preserves the encounter order of the `IntStream.rangeClosed` source because `filter` and `toList` have order-preserving semantics on ordered sources.
- `groupingBy` with `TreeMap::new` returns a Map sorted by string length keys.
- `joining("-")` preserves encounter order on an ordered Stream, so it does not depend on the order in which workers finish.

There is no updating of a shared List or Map from outside the pipeline.

## 12. Side effects and shared mutable state

One of the most dangerous mistakes when switching from `stream()` to `parallelStream()` is keeping a callback that mutates a shared variable.

**Wrong example to avoid:**

```java
List<Integer> output = new java.util.ArrayList<>();
java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(output::add); // unsafe
```

The above is an **anti-pattern** illustration, not a recommended program. `ArrayList` does not support concurrent updates from multiple threads without proper synchronization. Elements can be lost, data races can occur, order can be arbitrary, or structural corruption can happen.

Correct way when you only need the data:

```java
List<Integer> output = java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .boxed()
        .toList();
```

The two snippets are **alternatives**, not two `output` declarations in the same scope.

If you need **side effects** such as sending emails, writing files, or updating a database, switching to parallel can cause wrong ordering, resource contention, or difficult error handling. You need explicit decisions on concurrency architecture, transactions, and retries — do not assume `parallelStream().forEach` provides those guarantees out of the box.

### Stateless and non-interfering

Functions passed to `map`, `filter`, and `reduce` should preferably be:
- **Stateless:** the result does not depend on mutable state modified by other invocations.
- **Non-interfering:** does not modify the source being traversed by the Stream in violation of the contract.
- **Deterministic when business logic requires it:** the same input produces the same result; does not depend on the assigned thread or execution timing.

Private resources that callbacks only read can be suitable if thread-safe when used in parallel. However, do not assume an arbitrary HTTP client, repository, or mutable formatter is safe for multiple threads without checking the library's contract.

## 13. Java 17 program: parallel partitioning without a shared List

Create the file **`ParallelPartitionModeDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelPartitionModeDemo {
    public static void main(String[] args) {
        List<Integer> numbers = IntStream.rangeClosed(1, 8)
                .boxed()
                .toList();

        Map<Boolean, List<Integer>> partition = numbers.parallelStream()
                .collect(Collectors.partitioningBy(n -> n > 4));

        long evenCount = numbers.stream()
                .parallel()
                .filter(n -> n % 2 == 0)
                .count();

        List<Integer> changed = numbers.parallelStream()
                .sequential()
                .map(n -> n * 2)
                .toList();

        System.out.println("higher=" + partition.get(true));
        System.out.println("lower=" + partition.get(false));
        System.out.println("evenCount=" + evenCount);
        System.out.println("sequentialResult=" + changed);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ParallelPartitionModeDemo.java
java ParallelPartitionModeDemo
```

**Exact stdout:**

```text
higher=[5, 6, 7, 8]
lower=[1, 2, 3, 4]
evenCount=4
sequentialResult=[2, 4, 6, 8, 10, 12, 14, 16]
```

`partitioningBy` partitions by the condition `n > 4`, and both Boolean branches always exist; the program accesses each branch using `get(true)` and `get(false)` instead of printing the Map directly with unguaranteed key order. `sequential()` resets the sequential mode for the final pipeline, even though the initial source was created with `parallelStream()`.

The example does not use tiny data to draw **performance conclusions**: it only illustrates semantics and how to write code without sharing a mutable `ArrayList`.

## 14. Choosing sequential or parallel based on real conditions

There is no rule that "parallel is always faster by the number of cores". Parallelism has overhead for splitting work, scheduling, synchronization, coordination, combining results, and potentially higher intermediate memory usage.

| Situation | Leans toward sequential | Can consider parallel |
| --- | --- | --- |
| Small data, each operation very light | Yes | Little benefit |
| Large data, easily splittable source | Depends on testing | Good opportunity |
| Independent CPU-bound tasks | Depends on size | Reasonable if heavy enough |
| Blocking I/O read/write | Usually needs dedicated concurrency design | Does not solve blocking by itself |
| Strict order requirements and stateful operations | Simpler to keep sequential | May incur overhead |
| Shared mutable state or side effects | Requires redesign first | Should not switch directly |
| Associative reduce, proper collector | Correct | Can be correct and leverage split/combine |
| CPU/common pool is busy | Easy to avoid contention | May suffer contention |

### Pool and threads

The parallel Stream implementation in the JDK is typically based on the **Fork/Join** mechanism, often using the common pool in common contexts. This is not a promise that "every element is a task" or "each pipeline has its own pool". The number of worker threads and how they are chosen are not details that business logic is allowed to depend on.

Do not print `Thread.currentThread().getName()` and conclude that it is part of the Stream contract. If an application needs control over worker pools, cancellation, timeouts, or per-task backpressure, consider a dedicated concurrency abstraction such as `ExecutorService` or `CompletableFuture` (and an appropriate resource management policy).

### Proper performance measurement

Use **JMH** or a rigorous benchmarking methodology:
1. Ensure sequential and parallel code produce **equivalent results** on the same data.
2. Test realistic source sizes and processing weights.
3. Warm up the JIT and measure multiple times in a stable environment.
4. Observe CPU, garbage collection, allocation, and contention.
5. Only keep parallelism when benchmarks show a benefit and logic remains maintainable.

Do not take a single `System.nanoTime()` call as general proof. This lesson intentionally prints computed values to stdout rather than "milliseconds" because timings vary by machine, JDK, and system load.

## 15. Common misconceptions

1. **"`parallelStream()` is a method on `Stream`."** False; it is normally called on a Collection. If you already have a Stream, use `parallel()`.
2. **"`parallel()` immediately executes `map`/`filter` operations."** False; intermediate operations remain lazy.
3. **"`parallel()` creates one thread per element."** False; splitting and scheduling are decided by the framework.
4. **"`parallel().sequential()` creates two phases running in different modes."** False; the final mode governs the pipeline when the terminal executes.
5. **"`isParallel()` proves multiple threads were used."** False; it only reads the mode flag.
6. **"Parallel is always faster."** False; overhead and contention can outweigh the gains.
7. **"`parallelStream().toList()` always scrambles order."** False for ordered sources and order-preserving terminals.
8. **"Parallel `forEach` always follows encounter order."** False; use `forEachOrdered` if ordered actions are needed.
9. **"`forEachOrdered` makes all upstream steps sequential."** False; it only guarantees action order according to encounter order.
10. **"`findAny` always returns the first element."** False; it is allowed to return any element.
11. **"A Stream can have multiple terminal operations called on it."** False; create a new Stream when you need to run again.
12. **"Using a mutable identity with parallel `reduce` is fine."** False; it can break the contract and cause races.
13. **"Using an external `ArrayList` in parallel `forEach` to collect data."** Dangerous due to concurrent updates.
14. **"Any `reduce` operator can be parallelized."** False; it requires an identity and associativity.
15. **"A Collector must be `CONCURRENT` to work with parallel."** False; normal collectors can use separate accumulators and combine them.
16. **"`sequential` definitely fixes side-effect bugs."** False; mode does not replace proper logic design.
17. **"`unordered()` means shuffling elements randomly."** False; it only removes the encounter-order constraint.
18. **"Switching to parallel is non-blocking async for the caller."** False for ordinary terminal operations that return a result after completion.

## 16. Exercises and answers

**Question 1.** Given `List<Integer> numbers`. What are two ways to create a parallel pipeline?

**Answer:** `numbers.parallelStream()` or `numbers.stream().parallel()`.

**Question 2.** What is `numbers.parallelStream().sequential().isParallel()`?

**Answer:** `false`. `sequential()` is the final mode choice.

**Question 3.** What is `numbers.stream().parallel().sequential().parallel().isParallel()`?

**Answer:** `true`. The last configured mode is parallel; it does not create three separate execution phases.

**Question 4.** Why can `parallelStream().map(f).toList()` still preserve the source List's order?

Because the encounter order of an ordered source can be preserved under the contract of `toList()`, even though mapper calls execute in parallel.

**Question 5.** Should `forEach` or `forEachOrdered` be used to print A, B, C in order from an ordered Stream?

**Answer:** `forEachOrdered`. `forEach` on parallel does not guarantee action order.

**Question 6.** Does `reduce(0, (a,b) -> a-b)` guarantee an equivalent result to sequential when run in parallel?

**No.** Subtraction is not associative, so how work is split and grouped can change the result.

**Question 7.** Why should you not write `parallelStream().forEach(sharedList::add)` where `sharedList` is an `ArrayList`?

Because `ArrayList` is not safe for multiple concurrent updates; elements can be lost or state corrupted. Use `toList()` or a suitable collector.

**Question 8.** When should `sequential()` be used on a Stream received from elsewhere?

When you need to request the final pipeline to execute sequentially to reduce overhead or keep computation simpler, while still ensuring the pipeline logic is correct.

**Question 9.** If you need phase 1 sequential and phase 2 genuinely parallel, is calling `stream.map(f).parallel().map(g)` enough?

**No.** Materialize phase 1's result with a terminal operation (such as `toList()`), then create a new parallel Stream for phase 2. Those are two real pipelines.

**Question 10.** How do you know if parallel is worth using in production?

Verify correctness in both modes and benchmark on realistic workloads; do not infer from method names or core counts.

**Takeaway:** `parallelStream()` **initializes** a parallel Stream from a Collection; `parallel()` **requests switching** a Stream to parallel; `sequential()` **requests switching** a Stream back to sequential. The final mode applies to **the entire pipeline when the terminal runs**. Speed and execution order are not guaranteed simply by choosing parallel; favor stateless functions, valid combining operations, and order-preserving terminals when business logic requires it.