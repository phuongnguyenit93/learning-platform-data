# The Last Mode Applies to the Entire Pipeline in Java Stream

## 1. Objective

In Java Stream, you can request **sequential processing** or **parallel processing** using the methods:

~~~java
stream.sequential()
stream.parallel()
~~~

A common point of confusion is that if you write `parallel()` at the start of a pipeline and `sequential()` in the middle, the stages before do **not** run in parallel while the stages after run sequentially.

**Core rule:** for a Stream pipeline, **the last sequential/parallel mode setting takes effect for the entire pipeline when the terminal operation executes**. The `parallel()` and `sequential()` methods do not split a pipeline into "segments" operating independently in different modes.

After this lesson, you will be able to:

- Read `stream()`, `parallelStream()`, `parallel()`, `sequential()`, and `isParallel()` accurately.
- Predict the **final mode** when a pipeline has multiple mode switches.
- Distinguish **execution mode** from **encounter order** and from operations like `unordered()`, `sorted()`, and `forEachOrdered()`.
- Understand why the mode is decided for the entire pipeline at evaluation time, rather than "locked in" when each intermediate operation is added.
- Identify the requirements for **stateless**, **non-interfering** operations and the correctness of reductions/collectors when running in parallel.
- Avoid mistakes such as relying on thread count, log order, mutable shared state, or assuming parallel is always faster.
- Test using complete Java 17 examples and deterministic output.

## 2. A pipeline has only one effective execution mode

Example:

~~~java
List<Integer> result = numbers.stream()
        .parallel()
        .map(n -> n * 2)
        .sequential()
        .filter(n -> n > 5)
        .toList();
~~~

Assume `numbers` is a valid `List<Integer>`. Here:

1. `numbers.stream()` creates an initially **sequential** Stream.
2. `parallel()` sets a **parallel** mode request for the Stream pipeline.
3. `map(...)` adds a lazy intermediate operation.
4. `sequential()` switches the effective mode back to **sequential**.
5. `filter(...)` adds another lazy intermediate operation.
6. `toList()` is the terminal operation that requests pipeline evaluation.

**Conclusion:** this entire pipeline is evaluated in **sequential mode**. There is no requirement that the `map` before `sequential()` must run in parallel.

Conversely:

~~~java
List<Integer> result = numbers.stream()
        .sequential()
        .map(n -> n * 2)
        .parallel()
        .filter(n -> n > 5)
        .toList();
~~~

Here the last mode setting is `parallel()`, so **the entire pipeline** is requested to be evaluated in **parallel mode**. It is not the case that `map` "already finished running sequentially" before encountering `parallel()`: intermediate operations remain lazy.

### 2.1. "Last" means the last among mode-setting calls

A pipeline can have many method calls, but not just any last method determines parallel or sequential.

~~~java
var pipeline = numbers.stream()
        .parallel()
        .filter(n -> n > 0)
        .map(n -> n * 2);
~~~

The last two steps are filter and map, which **do not change execution mode**, so the pipeline still has **parallel mode**.

In the case:

~~~java
var pipeline = numbers.stream()
        .parallel()
        .filter(n -> n > 0)
        .sequential()
        .map(n -> n * 2);
~~~

The last mode setting is sequential, so **sequential mode** is in effect.

Read `parallel()`/`sequential()` as **configuring an execution property for the pipeline**, not "a data operation applied only to the steps immediately following it".

## 3. Why is this rule tied to lazy evaluation?

A Stream consists of:

~~~text
Source -> intermediate A -> intermediate B -> ... -> terminal
                  \                      /
                   \-- pipeline spec ---/
                             |
                             v
                   when terminal runs
                             |
                             v
             evaluate pipeline in effective mode
~~~

Intermediate operations such as:

~~~java
filter(...)
map(...)
flatMap(...)
sorted(...)
distinct(...)
limit(...)
peek(...)
~~~

typically **do not immediately traverse data** when added to the pipeline. They contribute rules for later execution. Only when a terminal operation such as `toList()`, `collect(...)`, `reduce(...)`, `sum()`, `count()`, or `forEach(...)` is called is the pipeline asked to produce a result.

Because earlier steps **are not forced to complete at construction time**, a `sequential()` call near the end can establish the mode for executing the entire chain, including `map/filter` steps declared earlier.

### 3.1. Parallel mode is not a stage named "parallel"

Example of an **incorrect** mental model:

~~~text
source ---- parallel() ---- map() ---- sequential() ---- filter()
               |            |            |                 |
         start threads   already ran  close threads     continue
~~~

This is **not** the Stream model. `parallel()` and `sequential()` do not mean opening/closing threads at the point they appear, do not create barriers, and do not materialize results after each stage.

**Correct** mental model:

~~~text
source -> map -> filter -> terminal
            \___pipeline___/
            final mode: sequential
~~~

The Stream implementation plans and evaluates the pipeline according to the configured mode. Parallel execution may use multiple threads and split work, but thread details are implementation/runtime behavior, not a contract that "each step runs on a separate thread".

## 4. Stream sources and default modes

Common ways to create a Stream:

| Creation method | Initial mode | Example |
| --- | --- | --- |
| `collection.stream()` | Sequential | `orders.stream()` |
| `collection.parallelStream()` | Parallel | `orders.parallelStream()` |
| `Stream.of(...)` | Sequential | `Stream.of(1,2,3)` |
| `IntStream.range(...)` | Sequential | `IntStream.range(0,10)` |
| `stream.parallel()` | Parallel | `orders.stream().parallel()` |
| `stream.sequential()` | Sequential | `orders.parallelStream().sequential()` |

These are the **defaults/settings of standard creation methods**, before the caller may continue calling mode-switching methods. Some custom APIs/sources may create Streams with specific characteristics, so when working with a Stream passed from elsewhere, check the source contract or `isParallel()` when you truly need to know its current property.

Example:

~~~java
List<String> items = List.of("A", "B");

Stream<String> s1 = items.stream();
Stream<String> s2 = items.parallelStream();

System.out.println(s1.isParallel()); // false
System.out.println(s2.isParallel()); // true
~~~

`isParallel()` is a method of **BaseStream** and indicates whether the Stream is currently marked parallel. It does not execute a terminal operation to traverse elements.

### 4.1. Switching back from parallelStream()

~~~java
List<String> result = items.parallelStream()
        .map(String::toLowerCase)
        .sequential()
        .toList();
~~~

Even though the source was created by `parallelStream()`, the subsequent `sequential()` call causes the pipeline to be evaluated in sequential mode.

And vice versa:

~~~java
List<String> result = items.stream()
        .map(String::toLowerCase)
        .parallel()
        .toList();
~~~

Starting from a sequential `stream()` does not prevent you from switching to parallel before the terminal.

**Key distinction:** a Stream's mode is not an immutable property of the collection. The same List can create **two separate Streams** with two different modes without modifying the List itself.

## 5. Multiple mode switches: the last operation wins

Example with three mode settings:

~~~java
var pipeline = Stream.of(1, 2, 3, 4)
        .parallel()
        .map(n -> n + 1)
        .sequential()
        .filter(n -> n > 2)
        .parallel()
        .map(n -> n * 10);
~~~

**The last** is `parallel()`, so `pipeline.isParallel()` is **true** and the terminal will process the pipeline in parallel mode.

If you add `sequential()` right before the terminal:

~~~java
var sequentialPipeline = Stream.of(1, 2, 3, 4)
        .parallel()
        .map(n -> n + 1)
        .sequential()
        .filter(n -> n > 2)
        .parallel()
        .map(n -> n * 10)
        .sequential();
~~~

then `sequentialPipeline.isParallel()` is **false** and the entire pipeline is requested to process sequentially.

**Pay attention to timing:** you may only change mode **before the Stream has been consumed**. After a terminal operation, a Stream cannot be reused as a new pipeline.

~~~java
Stream<Integer> stream = Stream.of(1, 2, 3);
long count = stream.count();

// Do not continue using a consumed stream:
// stream.parallel().toList(); // IllegalStateException (or reuse error).
~~~

Create **a new Stream from the source** if another processing pass is needed.

## 6. isParallel() verifies the mode flag, not performance or thread count

~~~java
Stream<Integer> stream = Stream.of(1, 2, 3).parallel();

boolean parallelMode = stream.isParallel();
System.out.println(parallelMode); // true
~~~

What is guaranteed here is **the Stream's flag**. It **does not prove**:

- That the JVM will definitely use more than one thread for a small pipeline.
- That each `map` or `filter` will run on a different thread.
- That speed will be faster than sequential.
- That callbacks run on a fixed schedule.
- That output will be scrambled in order.

The library may decide how to split data, the degree of parallelism, and scheduling order depending on the source, terminal, workload, and environment. A Stream with `isParallel() == true` may not achieve any noticeable speedup.

### 6.1. Do not use Thread.currentThread() as a primary test

Example:

~~~java
numbers.parallelStream().forEach(n ->
        System.out.println(Thread.currentThread().getName() + ":" + n));
~~~

Thread names and print order can vary across runs. This snippet is only suitable for **observation/debugging**, not for asserting exact output or writing tests that must always see a specific number of worker threads.

To test mode-switching rules, test **isParallel()** on an unconsumed pipeline. To test correctness, test **output values** and reduction rules, rather than relying on thread logs.

## 7. Parallel/sequential differs from encounter order

These are two independent concepts:

1. **Execution mode**: is the pipeline evaluated sequentially or in parallel?
2. **Encounter order**: does the data have an encounter order defined by the source/pipeline?

For example, **List** has an encounter order; a stream created from a List still carries encounter order when you call `parallel()`, unless an operation or source changes that characteristic.

~~~java
List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> doubled = values.parallelStream()
        .map(n -> n * 2)
        .toList();

System.out.println(doubled); // [2, 4, 6, 8, 10]
~~~

Even though the pipeline is parallel, **toList() preserves encounter order if the Stream has encounter order**. This is one reason not to conclude that "parallel means the result is automatically randomized".

### 7.1. unordered() does not make a Stream parallel

~~~java
Stream<Integer> p = Stream.of(1, 2, 3)
        .parallel()
        .unordered()
        .sequential();

System.out.println(p.isParallel()); // false
~~~

`unordered()` removes the **encounter-order constraint** on the pipeline where appropriate; it is not a way to enable parallel or sequential mode.

In the example above, the final mode is **sequential**, even though `parallel()` and `unordered()` were called earlier.

Similarly:

~~~java
Stream<Integer> p = Stream.of(1, 2, 3)
        .sequential()
        .unordered()
        .parallel();
~~~

The final mode is parallel. Dropping the encounter-order constraint is a **separate property** that may help some parallel operations optimize when business logic does not require order.

### 7.2. sorted() determines order by Comparator

~~~java
List<Integer> sorted = List.of(4, 1, 3, 2)
        .parallelStream()
        .sorted()
        .toList();

System.out.println(sorted); // [1, 2, 3, 4]
~~~

`sorted()` is a **stateful** intermediate operation that produces elements in comparison order. It does not switch parallel mode to sequential mode. A step requiring ordering or buffering may reduce parallel benefits, but that does not mean the pipeline was split into "a sequential sorted part and a parallel remainder" under mode semantics.

### 7.3. limit() and takeWhile() on an ordered parallel stream

With an ordered List source:

~~~java
List<Integer> firstThree = List.of(1, 2, 3, 4, 5)
        .parallelStream()
        .limit(3)
        .toList();

System.out.println(firstThree); // [1, 2, 3]
~~~

To obtain **the exact three-element prefix**, the pipeline must respect encounter order. A `limit` on an ordered parallel stream can be more expensive than on an unordered stream. `takeWhile` and `dropWhile` also have corresponding prefix requirements on ordered streams.

Do not call `unordered()` just for speed if business logic requires "the first three elements" or processing a prefix in chronological order.

## 8. forEach and forEachOrdered: callback order differs from execution mode

### 8.1. forEach in parallel

~~~java
List.of(1, 2, 3, 4).parallelStream()
        .forEach(System.out::print);
~~~

**Does not promise to print "1234"**. Callbacks may run concurrently or in different orders.

### 8.2. forEachOrdered in parallel

~~~java
List.of(1, 2, 3, 4).parallelStream()
        .forEachOrdered(System.out::print);
~~~

With a source that has encounter order, **forEachOrdered** guarantees that actions execute in encounter order, so the printed string is ordered "1234" in this example. However, that **does not mean** the Stream switched its execution mode to sequential. It is a **constraint of the terminal operation**, which may limit performance and does not guarantee all callbacks run on the main thread.

If you need a result list instead of printing/updating state, prefer:

~~~java
List<Integer> result = List.of(1, 2, 3, 4)
        .parallelStream()
        .map(n -> n * 2)
        .toList();
~~~

Output data should be produced using reduction/collector operations with clear contracts, not by manually adding to an external `ArrayList` from parallel `forEach`.

## 9. Stateful and short-circuiting operations share the same mode

A pipeline can contain:

~~~java
List<Integer> result = values.stream()
        .parallel()
        .filter(n -> n > 0)
        .distinct()
        .sorted()
        .limit(5)
        .sequential()
        .toList();
~~~

**The final mode is sequential** for the entire pipeline, even though `distinct`, `sorted`, and `limit` have their own characteristics.

- **filter** is usually stateless and can be combined per element.
- **distinct** is stateful and needs to detect duplicates.
- **sorted** is stateful and usually needs buffering to sort properly.
- **limit** is short-circuiting and can limit elements passing through.
- **sequential** sets the effective mode; it does not sort, does not filter, and is not a terminal.

Replacing the final `sequential()` with `parallel()` requests the entire pipeline to be parallel, but does not guarantee faster execution because stateful stages and ordering can increase split/merge costs.

### 9.1. Short-circuiting may not inspect all elements

~~~java
boolean found = values.parallelStream()
        .anyMatch(n -> n > 100);
~~~

`anyMatch` can stop once enough information is found. In parallel, other tasks may still be processing after one task has found a result. Do not measure business success by the number of `Predicate` invocations.

Parallel/sequential mode determines the evaluation strategy, but **does not turn short-circuiting into a loop with a fixed callback count**.

### 9.2. count may not invoke every map/peek

~~~java
long count = List.of(1, 2, 3).stream()
        .parallel()
        .peek(System.out::println)
        .sequential()
        .count();
~~~

The `count` result is 3, but `peek` may **print nothing** if the implementation exploits the source's known size without traversing the pipeline. Do not conclude that "sequential mode guarantees every lambda definitely runs".

**The final mode is a rule about how the pipeline is evaluated**, not a contract on the number of lambda invocations.

## 10. Lambdas must be non-interfering and stateless

Behaviors passed to a Stream, especially when using parallel, must generally be:

- **Non-interfering:** do not modify the source being traversed.
- **Stateless:** do not depend on mutable state that changes across element evaluations.
- **Business-correct:** the same input data and stable configuration produce corresponding results.
- **Concurrently safe for how they are used:** do not cause races when multiple elements are processed simultaneously.

**Good** example:

~~~java
List<Integer> result = List.of(1, 2, 3, 4).parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .toList();
~~~

Filter and map only read `n` and produce results without updating shared state.

**Problematic** example:

~~~java
List<Integer> shared = new ArrayList<>();

numbers.parallelStream()
        .forEach(n -> shared.add(n));
~~~

This is a counterexample requiring `ArrayList` import and a `numbers` source. `ArrayList` is not thread-safe; `add` calls can race, leading to missing/duplicate results or corrupted internal data.

**Switching to `sequential()` at the end of the pipeline may make this counterexample accidentally less prone to concurrency errors, but it does not turn poorly managed side effects into good design**. When you need to build a result list, use `toList()` or an appropriate collector.

### 10.1. synchronized does not replace semantics

Wrapping a shared collection in `synchronizedList` may protect some operations, but:

- Does not automatically guarantee encounter order in parallel `forEach`.
- Does not turn a counter-dependent `Predicate` into a stateless one.
- Does not fix the identity/associativity contract of `reduce`.
- Can cause lock contention, negating parallel benefits.

Choose **the right aggregation model**, rather than just adding locks to "make it run".

## 11. Reduction and collector in parallel mode

### 11.1. Sum with valid identity and associative operation

~~~java
int sum = IntStream.rangeClosed(1, 100)
        .parallel()
        .sum();

System.out.println(sum); // 5050
~~~

For `int` addition in the example's value range, aggregation has identity 0 and yields a consistent result when split and combined. Do not use an external mutable sum variable inside `forEach`.

You can write:

~~~java
int sum = IntStream.rangeClosed(1, 100)
        .parallel()
        .reduce(0, Integer::sum);
~~~

The result is also 5050.

### 11.2. reduce must have a valid contract

With the three-argument overload:

~~~java
<U> U reduce(U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

**Identity** must be an identity element, **combiner** must be associative, and accumulator must be compatible with combiner and not rely on a shared mutable accumulator.

Do not do:

~~~java
// Counterexample: mutable identity is invalid with reduce.
// stream.parallel().reduce(
//     new ArrayList<T>(),
//     (list, item) -> { list.add(item); return list; },
//     (left, right) -> { left.addAll(right); return left; }
// );
~~~

During parallel reduction, the combiner may receive two shared references and data can be duplicated or race. Use **collect** for mutable accumulation, with a supplier creating separate containers.

### 11.3. Appropriate Collector when creating containers

~~~java
List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.toList());
~~~

The result contains A, B, C and preserves encounter order for an ordered stream according to the collector's semantics. **Collectors.toList()** does not promise a specific List class or mutability; if you want an unmodifiable list per `Stream.toList`, you can use `toList()` directly (Java 16+).

If you want to guarantee creating an **ArrayList**, use:

~~~java
List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

The snippets above require importing `List`, `Stream`, `Collectors`, and `ArrayList`. The supplier creates a new container suitable for work partitions, unlike an external shared `ArrayList` being arbitrarily appended to by every callback.

## 12. Does parallel always speed things up?

**No.** Parallel Stream has overhead:

- Splitting the source into work partitions.
- Scheduling, coordinating, and merging results.
- Buffering/synchronization for operations like `sorted`, `distinct`, and ordered `limit`.
- Resource sharing, cache/memory contention, and boxing costs.
- Side effects, I/O, or a source that cannot be split efficiently.

Parallel is likely to be useful when:

1. The source is large enough and **splits efficiently** (e.g., array or List with a suitable `Spliterator`).
2. Each element requires relatively heavy, independent computation.
3. Operations are stateless/non-interfering and data is stable.
4. The reduction/collector can combine results properly.
5. CPU resources are available and real benchmarks show a benefit.

Sequential is usually reasonable when the dataset is small, the work is light, or steps require strict ordering and complex state.

### 12.1. Parallel Stream is not an async API

`parallel()` does not return a `Future`. A terminal operation on a parallel stream normally **blocks until aggregation completes** (or fails) before returning the result to the caller.

If you want tasks to run asynchronously and return a result later, consider **CompletableFuture** or an executor with an appropriate contract. Do not equate `parallel()` with "background" or "fire-and-forget".

### 12.2. I/O and blocking tasks

Parallel Stream is not by default suitable for making database/HTTP calls on every element. Blocking I/O can cause resource contention and make it hard to control concurrency, retries, timeouts, and backpressure.

When you need to limit concurrent requests, manage queues, or handle per-task errors, an explicitly configured executor or a dedicated concurrency model is usually easier to control. Do not enable parallel just to "fetch a lot of data at once" without considering the target service's load capacity.

### 12.3. Do not assume fixed parallelism

Pool/execution details depend on the JDK and environment. Do not write business logic requiring exact `n` workers or relying on names like `ForkJoinPool.commonPool-worker-N`.

A valid benchmark needs warm-up, representative data, avoidance of dead-code elimination, and evaluation of throughput, latency, and memory. For serious measurements, use a dedicated tool like **JMH** rather than `System.currentTimeMillis()` for a single run.

## 13. Standalone Java 17 program

This example illustrates **the last mode wins for the entire pipeline**, verifies the flag with `isParallel()`, and only prints **deterministic results** rather than depending on thread names or callback execution order.

Create the file **PipelineModeDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class PipelineModeDemo {
    static Stream<Integer> numbers() {
        return IntStream.rangeClosed(1, 6).boxed();
    }

    public static void main(String[] args) {
        Stream<Integer> lastSequential = numbers()
                .parallel()
                .map(n -> n * 2)
                .sequential()
                .filter(n -> n % 3 == 0);

        System.out.println("A parallel: "
                + lastSequential.isParallel());
        System.out.println("A result: " + lastSequential.toList());

        Stream<Integer> lastParallel = numbers()
                .sequential()
                .filter(n -> n % 2 == 0)
                .parallel()
                .map(n -> n * 10);

        System.out.println("B parallel: "
                + lastParallel.isParallel());
        System.out.println("B result: " + lastParallel.toList());

        Stream<Integer> manySwitches = numbers()
                .parallel()
                .map(n -> n + 1)
                .sequential()
                .filter(n -> n >= 4)
                .parallel()
                .map(n -> n * 2);

        System.out.println("C parallel: "
                + manySwitches.isParallel());
        System.out.println("C result: " + manySwitches.toList());

        Stream<Integer> unorderedThenSequential = numbers()
                .parallel()
                .unordered()
                .sequential();

        System.out.println("D parallel: "
                + unorderedThenSequential.isParallel());
        System.out.println("D sorted: "
                + unorderedThenSequential.sorted().toList());

        List<Integer> orderedResult = numbers()
                .parallel()
                .map(n -> n * n)
                .toList();

        System.out.println("parallel ordered result: "
                + orderedResult);

        int sum = IntStream.rangeClosed(1, 6)
                .parallel()
                .sum();

        System.out.println("parallel sum: " + sum);

        Stream<Integer> finalSequential = numbers()
                .parallel()
                .sequential()
                .parallel()
                .sequential();

        System.out.println("E parallel: "
                + finalSequential.isParallel());
        System.out.println("E result: " + finalSequential.toList());
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac PipelineModeDemo.java
java PipelineModeDemo
~~~

**Expected output:**

~~~text
A parallel: false
A result: [6, 12]
B parallel: true
B result: [20, 40, 60]
C parallel: true
C result: [8, 10, 12, 14]
D parallel: false
D sorted: [1, 2, 3, 4, 5, 6]
parallel ordered result: [1, 4, 9, 16, 25, 36]
parallel sum: 21
E parallel: false
E result: [1, 2, 3, 4, 5, 6]
~~~

### 13.1. Explaining A

~~~java
numbers().parallel()
        .map(n -> n * 2)
        .sequential()
        .filter(n -> n % 3 == 0)
~~~

- Initial source is 1, 2, 3, 4, 5, 6.
- `map(n -> n*2)` produces 2, 4, 6, 8, 10, 12.
- `filter(n % 3 == 0)` keeps 6 and 12.
- **sequential() is the last mode setting**, so `isParallel()` is false.

Even though `map` appears **before** `sequential()`, it is not required to run in a separate "parallel phase".

### 13.2. Explaining B

~~~java
numbers().sequential()
        .filter(n -> n % 2 == 0)
        .parallel()
        .map(n -> n * 10)
~~~

- Filter even numbers: 2, 4, 6.
- Multiply by 10: 20, 40, 60.
- **parallel() is the last mode setting**, so `isParallel()` is true.
- `toList()` still returns the order [20, 40, 60] because the Stream has encounter order from the source.

Do not infer that `filter` already finished running sequentially before enabling parallel.

### 13.3. Explaining C

With sequence 1..6:

1. `map(n -> n+1)` produces 2..7.
2. `filter(n >= 4)` keeps 4, 5, 6, 7.
3. `map(n*2)` produces 8, 10, 12, 14.
4. The last mode switch is `parallel()`, so **C parallel: true**.

The presence of `sequential()` earlier does not give the stages before it their own mode.

### 13.4. Explaining D

Pipeline D has `parallel().unordered().sequential()`:

- `unordered()` is **not** an execution mode change.
- `sequential()` is the last mode setting → false.
- `sorted()` determines ascending result → [1, 2, 3, 4, 5, 6].

If `sorted()` were removed from the unordered example, you should not set exact order expectations for every source/terminal combination.

### 13.5. Explaining ordered result and sum

- `numbers().parallel().map(n*n).toList()` returns [1,4,9,16,25,36] in encounter order. This is an invariant result even though callback execution order may vary.
- `IntStream.rangeClosed(1,6).parallel().sum()` gives 21. Integer addition in the example has a deterministic result, without needing a shared mutable counter.

### 13.6. Explaining E

Pipeline E has four mode switches: parallel → sequential → parallel → sequential. **The last one** is sequential. Data does not pass through filter/map, so the list remains [1..6]. **isParallel() is false**, regardless of the number of previous mode switches.

## 14. Test semantics, not execution traces

You can write unit tests to verify:

1. A Stream created by `stream()` defaults to `isParallel()==false`.
2. A Stream created by `parallelStream()` defaults to `isParallel()==true`.
3. `parallel().sequential()` returns mode false.
4. `sequential().parallel()` returns mode true.
5. `parallel().map(...).sequential()` returns mode false, because the last mode applies to the pipeline.
6. The same pipeline processing pure values produces consistent results in both sequential/parallel.
7. `unordered()` does not change mode by itself.
8. `forEachOrdered` imposes ordering on an ordered stream without necessarily changing the parallel flag.
9. Pipelines with `sorted/limit` still produce business-correct results per encounter order.
10. Parallel reducers/collectors must be compatible with splitting and combining work, without using shared mutable state.

A concise test:

~~~java
boolean expectedSequential = Stream.of(1, 2, 3)
        .parallel()
        .map(n -> n * 2)
        .sequential()
        .isParallel();

if (expectedSequential) {
    throw new AssertionError("Expected final sequential mode");
}
~~~

This snippet requires importing `Stream` and being inside a method. `isParallel()` only reads the mode; it is not a terminal that traverses data.

**Do not test** "must see 4 threads" or "element 1 must be printed before element 2 from parallel forEach". Those are not part of the execution mode contract.

### 14.1. Comparing sequential and parallel results

If the operation has pure logic and a suitable reduction:

~~~java
int sequential = IntStream.rangeClosed(1, 1000)
        .sequential()
        .sum();

int parallel = IntStream.rangeClosed(1, 1000)
        .parallel()
        .sum();

if (sequential != parallel || parallel != 500_500) {
    throw new AssertionError("Unexpected sum");
}
~~~

In the example, the sum stays within the `int` range. With `double`, rounding errors may depend on the order of combination; do not assume all floating-point results always match bit-for-bit.

## 15. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking stages before `sequential()` stay parallel | The last mode applies to the whole pipeline | Read the entire chain before the terminal |
| Thinking `parallel()` immediately runs work | Intermediates remain lazy | The terminal triggers evaluation |
| Thinking `parallelStream()` cannot switch to sequential | You can call `sequential()` afterward | Use the mode suited to the goal |
| Thinking `unordered()` equals `parallel()` | Order and execution mode are independent | Distinguish the two properties |
| Thinking `parallel()` makes `toList()` lose order | Ordered streams have encounter order | Rely on the terminal contract |
| Thinking `forEachOrdered()` sets sequential mode | It constrains action order | Do not infer mode from ordering |
| Calling `isParallel()==true` and demanding multiple threads | It is a flag, not a thread count | Do not test thread names/counts |
| Using `parallel().peek(...).count()` for auditing | Callbacks may be skipped/evaluated differently | Separate mandatory processing steps |
| Using a shared `ArrayList` in parallel `forEach` | Can race and corrupt data | Use `collect`/`toList` |
| Using a shared mutable object in `reduce` | Violates identity/associativity/aliasing | Pure reduce or proper collect |
| Thinking parallel is always fast | Has overhead and limits from ordering/stateful ops | Benchmark realistically |
| Enabling parallel for uncontrolled I/O | Can exhaust resources / hard to retry | Use an executor / clear concurrency design |
| Reusing a Stream after a terminal | A Stream is consumed only once | Create a new Stream |
| Changing `sorted().limit(3)` to `limit(3).sorted()` | Changes top-k meaning | Keep business order |

## 16. Exercises

### Exercise 1 — What is the final mode?

~~~java
var s = Stream.of(1, 2, 3)
        .parallel()
        .map(n -> n + 1)
        .sequential()
        .filter(n -> n > 0);
~~~

**Question:** What is `s.isParallel()`? **Answer:** false. The last mode setting is sequential; the preceding `map` does not create an independent parallel phase.

### Exercise 2 — Reversing the mode switch position

~~~java
var s = Stream.of(1, 2, 3)
        .sequential()
        .filter(n -> n > 1)
        .parallel()
        .map(n -> n * 10);
~~~

**Answer:** `s.isParallel()` is true; the result of `s.toList()` is [20,30] because `Stream.of` has encounter order.

### Exercise 3 — Distinguishing order and mode

~~~java
var s = Stream.of(3, 1, 2)
        .parallel()
        .unordered()
        .sequential()
        .sorted();
~~~

**Question:** final mode, and `toList()` result? **Answer:** sequential mode, result [1,2,3]. `unordered()` does not change mode; `sorted()` produces ascending order.

### Exercise 4 — Should a shared List be used?

A developer uses `numbers.parallelStream().forEach(sharedList::add)` with an `ArrayList`. **Answer:** no, because `ArrayList` is not thread-safe and `forEach` does not guarantee encounter order. Use `map(...).toList()` or an appropriate collector.

### Exercise 5 — Designing performance criteria

You have 1,000 elements, and each element only adds 1. Should you use parallel? **Hint:** insufficient basis; overhead may outweigh the work. Compare both sequential and parallel using a benchmark with warm-up and representative data, rather than assuming parallel is faster.

### Exercise 6 — Choosing a terminal to preserve order

An ordered list needs to print each element in encounter order. On a parallel stream, is `forEach` or `forEachOrdered` more appropriate? **Answer:** `forEachOrdered` if action order is truly required, though it does not mean the mode switches to sequential and you still need proper side-effect/error handling per contract.

## 17. Takeaways

**The last `parallel()` or `sequential()` mode set takes effect for the entire Java Stream pipeline when the terminal operation executes.** It does not split the pipeline into segments running in different modes simply because of where the method is called.

- **parallel()** sets parallel mode; **sequential()** sets sequential mode; **isParallel()** reads the effective flag.
- **Intermediate operations are lazy**, so the final mode can apply to steps declared earlier.
- **Execution mode is independent of encounter order**: parallel does not by default scramble result order; unordered does not by default enable parallel.
- **forEachOrdered** constrains action order, and is not a switch to sequential.
- **Stateless, non-interfering operations and contract-compliant reductions** are key conditions for reliable parallel processing.
- **Parallel is not by default faster and not automatically asynchronous**; measure performance and control resources.
- **Do not rely on thread count, log order, callback invocation count, or shared mutable state** to determine business correctness.

When reviewing a long pipeline, find **the last `parallel()` or `sequential()` call before the terminal**, determine the overall mode; then check encounter order, stateful/short-circuit operations, and callback correctness under that mode.