# Observing Pipelines with `peek` and the Limits of Side Effects

A Java Stream API pipeline is typically expressed with declarative steps such as `filter`, `map`, `sorted`, `distinct`, and a terminal operation. When results do not match expectations, learners often want to inspect elements passing through each step. `peek` is a convenient tool for **observing** values during stream consumption, but that observation comes with important limits: pipelines execute lazily, may stop early, may skip unnecessary steps, and may process elements across multiple threads.

This lesson belongs to the **Traversal, Search, and Matching** chapter of the **JAVA_STREAM_API** module. The goal is to accurately understand what `peek` does, when actions inside `peek` can execute, how to use it to diagnose pipelines, and why you should not rely on `peek`'s side effects to update business state. Examples use Java 17 or later, connecting to `filter`, `map`, `collect`, parallel processing, stream lifecycles, and performance.

## 1. What Is `peek`?

`Stream.peek` is an **intermediate operation** accepting a `Consumer`:

```java
Stream<T> peek(Consumer<? super T> action);
```

`Consumer<T>` has the method `void accept(T value)`: it receives an element and performs an action without returning a new element. When an element actually flows through `peek` during pipeline processing, the action can observe that element. `peek` forwards **the exact same input element**, changing neither the count nor the value reference via mapping as `map` does.

```java
import java.util.List;

List<Integer> result = List.of(5, 2, 8, 3).stream()
        .filter(n -> n % 2 == 0)
        .peek(n -> System.out.println("After filter: " + n))
        .map(n -> n * 10)
        .toList();

System.out.println(result); // [20, 80]
```

Along a normal sequential execution path, `peek` prints `2` and `8`, and then `map` turns them into `20` and `80`. **The guaranteed result** is the list `[20, 80]`; whether the log executes and how many times it runs is not a contract to rely on in business logic.

### Comparing with Commonly Confused Operations

| Operation | Role | Output Elements |
|---|---|---|
| `filter(predicate)` | Decides whether to keep or drop an element | Keeps elements matching the condition unchanged |
| `map(function)` | Transforms value/type | Value returned by `function` |
| `peek(consumer)` | Observes or runs an auxiliary action when an element is consumed | Forwards the same element |
| `forEach(consumer)` | Terminal operation performing an action on traversed elements | Produces no output stream |
| `forEachOrdered(consumer)` | Terminal operation performing an action in encounter order if present | Produces no output stream |
| `collect(collector)` / `toList()` | Terminal operation accumulating results | An aggregated result, such as a list |

**Rule:** use `map` to produce new values, `filter` to drop unsuitable values, `peek` to assist observation, and a terminal operation to complete the pipeline.

## 2. Laziness: Declaring `peek` Does Not Run the Action Immediately

Because `peek` is an intermediate operation, calling it only constructs the pipeline:

```java
import java.util.stream.Stream;

Stream<String> pipeline = Stream.of("Lan", "An", "Minh")
        .peek(name -> System.out.println("Seen: " + name))
        .map(String::toUpperCase);

System.out.println("Pipeline declared");
// No need yet to read elements or invoke the action inside peek.

List<String> names = pipeline.toList();
System.out.println(names); // [LAN, AN, MINH]
```

`toList()` is the terminal operation requesting the final values. With this pipeline, `peek` helps observe the elements that consumption actually passes through.

Laziness avoids unnecessary work, especially with short-circuiting operations, but it also means **`peek` must never be used as a counter of elements that is assumed to run unconditionally**.

### 2.1. Data Flowing Through Multiple Observation Points

```java
List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> result = values.stream()
        .peek(n -> System.out.println("Source: " + n))
        .filter(n -> n % 2 == 0)
        .peek(n -> System.out.println("Passed filter: " + n))
        .map(n -> n * n)
        .peek(n -> System.out.println("Passed map: " + n))
        .toList();

System.out.println(result); // [4, 16]
```

When debugging a sequential pipeline whose terminal operation requires all results, `peek` checkpoints distinguish three value sets: inputs `1, 2, 3, 4, 5`, even elements `2, 4`, and squared results `4, 16`.

Do not infer from this snippet that the JVM must execute three **separate loops**. Operations can be fused during traversal, and neither invocation order nor call count should be asserted in tests.

## 3. Why Might `peek` Not Execute as Expected?

Under the Stream API contract, the runtime can **elide certain operations or lambda invocations** whenever it can still compute the correct final result. That is the main reason `peek` is documented as a debugging aid.

### 3.1. Without a Terminal Operation, Nothing Is Consumed

```java
Stream.of("A", "B", "C")
        .peek(System.out::println);
// No terminal operation; no request to print elements.
```

The code above merely constructs a stream and discards its reference; no element consumption is requested.

### 3.2. `count()` Can Compute the Result from Source Size

```java
long size = Stream.of("A", "B", "C")
        .peek(s -> System.out.println("Processing: " + s))
        .count();

System.out.println(size); // 3
```

For a sized source like `Stream.of("A", "B", "C")`, the implementation **can deduce `count() = 3` without traversing each element**. Consequently, the `Processing` lines may not appear at all. This is valid optimization behavior, explicitly highlighted in the API documentation since Java 9.

You cannot use `peek` to write audit logs or increment a `processedCount` variable and assume that value always matches `count()`.

### 3.3. Short-Circuiting Operations Need Only Part of the Data

```java
import java.util.Optional;

Optional<Integer> firstEven = List.of(3, 7, 8, 10, 12).stream()
        .peek(n -> System.out.println("Checking: " + n))
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(firstEven); // Optional[8]
```

`findFirst()` can stop once it has found the first matching element in encounter order. In a typical sequential pipeline, the `peek` action may be called for `3`, `7`, and `8`; `10` and `12` do not need to be examined. Do not write tests asserting the action must be called **exactly** three times.

Operations such as `findAny`, `anyMatch`, `allMatch`, `noneMatch`, `limit`, and `takeWhile` can affect how many elements are actually requested. With parallel streams, several tasks may process extra elements around the moment a result is found; thus log counts are unstable as well.

### 3.4. Empty Sources and Filters That Drop Everything

```java
List<String> none = Stream.<String>empty()
        .peek(System.out::println)
        .toList();
System.out.println(none); // []
```

There are no elements to observe. Similarly, `filter` can discard all elements before they ever reach a downstream `peek`.

### 3.5. Exceptions Can Also Cut Execution Short

If `filter`, `map`, `peek`, or the terminal operation throws an exception, the pipeline can terminate as the error propagates. Actions executed prior to the error may already have caused side effects; the Stream API provides no automatic rollback mechanism.

```java
// Not a safe way to manage transactions.
// values.stream()
//       .peek(value -> updateDatabase(value))
//       .map(this::mayThrow)
//       .toList();
```

Never attach mandatory operations like database writes, payments, or notifications inside `peek` just to have them run “as data flows through”.

## 4. Ordering, Threads, and `parallelStream()`

A stream having an **encounter order** (such as a `List` source) does not mean `peek` actions execute in that order on one thread. With a parallel pipeline, actions on elements can run on any thread managed by the implementation.

```java
List<Integer> input = List.of(1, 2, 3, 4, 5);

List<Integer> output = input.parallelStream()
        .peek(n -> System.out.printf(
                "value=%d, thread=%s%n",
                n, Thread.currentThread().getName()
        ))
        .map(n -> n * 10)
        .toList();

System.out.println(output); // [10, 20, 30, 40, 50]
```

**Log order is not guaranteed**, yet `toList()` preserves result order according to the input's encounter order. Because `peek` is an observation action, never rely on print order to infer result order or how elements were assigned to worker threads.

### 4.1. `forEach` and `forEachOrdered` Solve a Different Problem

```java
List.of(1, 2, 3, 4, 5).parallelStream()
        .forEach(n -> System.out.print(n + " "));
// Print order is not guaranteed.

System.out.println();

List.of(1, 2, 3, 4, 5).parallelStream()
        .forEachOrdered(n -> System.out.print(n + " "));
// 1 2 3 4 5
```

`forEachOrdered` guarantees the terminal operation's action runs in encounter order when the source is ordered; the action for an earlier element *happens-before* the action for the next element. This **does not force all actions onto one thread** and does not make upstream `peek` calls run in order.

When the goal is building a list or result table, `toList()` or `collect(...)` is usually far better than using `forEach` to append elements into an external list.

### 4.2. `findAny` and `findFirst`

```java
int first = List.of(4, 1, 3).parallelStream()
        .peek(n -> System.out.println("Observing: " + n))
        .findFirst()
        .orElseThrow();

System.out.println(first); // 4
```

`findFirst` must respect the first element in encounter order of an ordered stream; with `findAny`, the selected element may be any element. Both can stop early, and `peek` is not a complete trace of the entire source.

## 5. Side Effects and Three Requirements for Lambdas in Pipelines

A **side effect** is when a function alters or affects state beyond its return value: writing external variables, mutating a `List`, updating a database, logging, emitting events, incrementing a counter, modifying shared objects, and so on.

To keep a pipeline understandable, parallelizable, and bug-free, lambda behavior in most stream operations should adhere to:

1. **Non-interfering:** do not modify a non-concurrent data source while the stream is traversing it. For example, do not add or remove elements of a source `ArrayList` while the pipeline is running.
2. **Stateless:** the result for an element does not depend on state mutated by processing other elements. `n -> n * 2` is stateless; `n -> runningTotal += n` depends on external state.
3. **Avoid business side effects:** output values should be expressed via `map`, `filter`, `reduce`, and `collect`, not by how many times `peek` is called.

### 5.1. Avoid Updating an External List via `peek`

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> seen = new ArrayList<>();

// Do not do this:
// List<Integer> values = List.of(1, 2, 3, 4).parallelStream()
//         .peek(seen::add)
//         .toList();
```

`ArrayList` is not safe for multiple threads calling `add` concurrently without synchronization, so that snippet can suffer race conditions or unreliable results. Even if replaced with a thread-safe list, `peek` still does not guarantee being called for every element in every pipeline.

If the goal is obtaining a list, use a collector:

```java
List<Integer> values = List.of(1, 2, 3, 4).parallelStream()
        .map(n -> n * 2)
        .toList();

System.out.println(values); // [2, 4, 6, 8]
```

With `collect(Collectors.toList())`, the framework manages accumulating and combining results in parallel according to the collector contract. There is no need to share an `ArrayList` via `peek`.

### 5.2. `AtomicInteger` Does Not Turn `peek` into a Reliable Counter

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger observed = new AtomicInteger();

long count = List.of("a", "b", "c").stream()
        .peek(s -> observed.incrementAndGet())
        .count();

System.out.println(count);          // 3
System.out.println(observed.get()); // May be 0 when count is optimized.
```

`AtomicInteger` makes the increment atomic when the action **is invoked**, but it does not force the runtime to invoke the action. Therefore, this counter is not an accurate measure of the element count returned by `count()`. Use `count` as the count result; if you need to record how many elements were actually processed in a business workflow, design tracking in a place with an explicit execution contract.

### 5.3. Do Not Mutate Business Objects via `peek`

```java
record Order(String id, int amount) {}

List<Order> orders = List.of(
        new Order("A", 100),
        new Order("B", 150)
);

// Compute the new state using map and return new data objects.
List<Order> discounted = orders.stream()
        .map(order -> new Order(order.id(), order.amount() - 10))
        .toList();

System.out.println(discounted);
// [Order[id=A, amount=90], Order[id=B, amount=140]]
```

With mutable objects, `peek(order -> order.setAmount(...))` can mutate objects still referenced by the source and other callers. Such side effects are hard to reason about when reusing data, optimizing pipelines, or running in parallel. Use `map` to produce new output data and handle state updates at the appropriate business layer.

## 6. How to Observe a Pipeline Purposefully

`peek` is useful when answering a specific question: which elements pass a filter, where a value gets transformed, or why an output disappeared. You can place observation checkpoints before and after a transformation:

```java
List<String> names = List.of(" Lan ", "", " Minh ", "An");

List<String> normalized = names.stream()
        .peek(s -> System.out.println("Input: [" + s + "]"))
        .map(String::trim)
        .peek(s -> System.out.println("After trim: [" + s + "]"))
        .filter(s -> !s.isEmpty())
        .peek(s -> System.out.println("Kept: [" + s + "]"))
        .map(String::toUpperCase)
        .toList();

System.out.println(normalized); // [LAN, MINH, AN]
```

During debugging, `peek` reveals pipeline stages without altering transformation expressions. Once observation is no longer needed, `peek` can be removed while leaving the pipeline's result semantics intact.

### 6.1. Logging a Result That Must Be Guaranteed

If logging the complete result is a program requirement, logging after the terminal operation is clearer than placing it inside `peek`:

```java
List<Integer> output = List.of(4, 2, 5, 1).stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .toList();

System.out.println("Final result: " + output); // [2, 4]
```

This makes the separation clear: **the pipeline computes data**, and the code following it decides what to do with the produced data. In real systems, use a logging framework and log at appropriate processing boundaries, avoiding writing sensitive data to logs.

### 6.2. When an Action Is Needed per Element

If business logic genuinely requires acting on **each element** of a finite set, a terminal operation like `forEach` or `forEachOrdered` states that intent more clearly than `peek`. Still, that action must handle failures, duplicates, thread safety, and transactions at the proper layer:

```java
List<String> names = List.of("An", "Bình", "Chi");
names.stream().forEachOrdered(System.out::println);
// An
// Bình
// Chi
```

Do not assume `forEachOrdered` automatically makes database updates atomic or rollbackable. If retry policies, exactly-once semantics, or transactions are required, design them explicitly.

## 7. Effects of `sorted`, `distinct`, `limit`, and Infinite Streams

Where `peek` is placed determines **which logical stage it observes**, not a guarantee that every element produces a log line.

### 7.1. After `sorted`, Sorted Values Are Observed

```java
List<Integer> result = List.of(5, 1, 4, 2).stream()
        .sorted()
        .peek(n -> System.out.println("After sort: " + n))
        .toList();

System.out.println(result); // [1, 2, 4, 5]
```

`sorted` is a stateful operation that usually needs to read the entire finite source before emitting results; logs before `sorted` and after `sorted` can reflect different stages. Do not rely on log line ordering when switching a pipeline to `parallel()`.

### 7.2. After `distinct`, Only Non-Duplicate Elements Remain

```java
List<Integer> unique = List.of(4, 2, 4, 1, 2).stream()
        .distinct()
        .peek(n -> System.out.println("Unique: " + n))
        .toList();

System.out.println(unique); // [4, 2, 1]
```

`distinct` removes duplicates using `equals`. For a `List` source with encounter order, the first occurrence is kept; placing `peek` after `distinct` serves to observe the remaining elements.

### 7.3. `limit` and Unbounded Sources

```java
List<Integer> sample = java.util.stream.Stream.generate(() -> 7)
        .limit(3)
        .peek(n -> System.out.println("Sample: " + n))
        .toList();

System.out.println(sample); // [7, 7, 7]
```

`Stream.generate` can produce elements forever; `limit(3)` makes the result finite. Avoid using `peek` to count how many times an infinite source's supplier is invoked, because optimizations and short-circuiting can make observed behavior differ from expectations. Never run an unbounded `Stream.generate(...).peek(...).toList()`: the terminal requires the entire source, so it will never finish and risks exhausting memory.

## 8. Resources and Exceptions in Pipelines

`peek` does not replace resource management. For file-opening sources like `Files.lines(path)`, use `try-with-resources` to close the stream whether traversal finishes or throws an exception:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<String> readNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .peek(s -> System.out.println("Reading: " + s))
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .toList();
    }
}
```

In production environments, avoid logging raw file contents directly when private information may be present; observing counts or safe identifiers can be more helpful. Remember that `Files.lines` holds an underlying resource released by `close()`; `peek` and `toList()` do not close the stream themselves.

If an action inside `peek` throws an unchecked exception, the exception propagates when the pipeline is consumed. Side effects already performed before the error are not automatically rolled back. In parallel streams, do not assume all other actions stopped instantaneously the moment one action threw.

## 9. A Complete Runnable Program (Java 17+)

The example below contrasts observation via `peek`, results computed via `toList`, `count` optimization, and using `forEachOrdered` when ordered printing is desired:

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class PeekAndSideEffectsDemo {
    public static void main(String[] args) {
        // (1) Observing stages of a sequential pipeline.
        List<Integer> result = List.of(5, 2, 4, 1).stream()
                .peek(n -> System.out.println("Input: " + n))
                .filter(n -> n % 2 == 0)
                .peek(n -> System.out.println("Even: " + n))
                .map(n -> n * 10)
                .toList();
        System.out.println("Result: " + result); // [20, 40]

        // (2) count() may be computed from source size.
        AtomicInteger observed = new AtomicInteger();
        long count = Stream.of("A", "B", "C")
                .peek(s -> observed.incrementAndGet())
                .count();
        System.out.println("Count: " + count); // 3
        System.out.println("Peek calls: " + observed.get());
        // Do not require Peek calls == 3; it may be 0.

        // (3) Short-circuiting terminal operation may stop early.
        int firstEven = List.of(3, 5, 8, 10).stream()
                .peek(n -> System.out.println("Find: " + n))
                .filter(n -> n % 2 == 0)
                .findFirst()
                .orElseThrow();
        System.out.println("First even: " + firstEven); // 8

        // (4) Parallel result preserves List encounter order.
        List<Integer> parallelResult = List.of(3, 1, 2)
                .parallelStream()
                .peek(n -> System.out.println(
                        Thread.currentThread().getName() + ": " + n))
                .sorted()
                .toList();
        System.out.println(parallelResult); // [1, 2, 3]

        // (5) Terminal action requested in encounter order.
        List.of("An", "Bình", "Chi").parallelStream()
                .forEachOrdered(System.out::println);
    }
}
```

In part (2), the business result is `Count: 3`; `Peek calls` merely demonstrates the unreliability of side effects. In part (4), the order of lines containing thread names may vary, while the final result list is sorted in ascending order.

## 10. Common Mistakes

| Claim/practice | Problem | Recommended fix |
|---|---|---|
| Waiting for `peek` to print without calling a terminal operation | Pipeline is lazy so no consumption occurs | Add a terminal operation matching your goal |
| Expecting `peek(...).count()` to invoke the action N times | `count` may infer size without traversing | Use the `count()` return value for counting |
| Expecting `peek` to be called for every source element | `filter`, short-circuiting, and optimizations may skip it | Treat `peek` as an observation tool, not a business outcome |
| Expecting `parallelStream().peek(...)` to run in `List` order | Actions may run on multiple threads; log order is unstable | Rely on result encounter order or `forEachOrdered` |
| Using `peek(list::add)` to collect results | Shared state risks data races and actions may be elided | Use `toList()`, `collect(...)` |
| Using `peek(entity::setStatus)` for business updates | Introduces side effects, may mutate source, hard to roll back | Use `map` to produce new data; update state at the business layer |
| Using `AtomicInteger` inside `peek` to get an “exact count” | Atomic only protects increments if the action runs | Count using a terminal operation or dedicated tracking |
| Assuming `forEachOrdered` forces every `peek` to run in order | Guarantee applies to the terminal action | Do not infer order/frequency of intermediate actions |
| Calling `peek` then `toList` on an infinite stream | No stopping point, risks exhausting resources | Apply a finite limit or a source with a terminating condition |
| Overusing `peek` logging in hot pipelines | I/O, string formatting, and lock contention can slow execution | Enable observation only when needed, measure overhead, log appropriately |

## 11. Self-Check

1. **Is `Stream.of(1, 2).peek(System.out::println)` guaranteed to print two numbers?** No. There is no terminal operation, so no data consumption is requested.
2. **Is `Stream.of("A", "B").peek(...).count()` guaranteed to run the action twice?** No. `count()` can obtain the size directly from the source.
3. **Can `peek` replace `map`?** No. `peek` accepts a `Consumer` and forwards the same element, whereas `map` accepts a `Function` to produce a new value.
4. **Does `findFirst` guarantee all elements before and after the result are observed by `peek`?** No. Short-circuiting and execution strategies may leave some elements unprocessed.
5. **Does using `AtomicInteger` in `peek` guarantee the action count equals `count()`?** No. Atomic only makes incrementing safe if the action actually runs.
6. **After `parallelStream().peek(...).sorted().toList()`, must the log order be ascending?** No. The result list from `toList()` is ordered, while log actions inside `peek` have no such guarantee.
7. **What should you use if you want to gather all results into a list?** `toList()` or `collect(Collectors.toList())`, rather than mutating an external list via `peek`.
8. **Should database writes be placed inside `peek`?** No. Processing contracts, transactions, and error handling should be expressed explicitly at the business layer or in an appropriate terminal operation.

**Core Takeaway:** `peek` is very helpful for inspecting a pipeline while learning and debugging, but **actions inside it are not guaranteed to always run, to run in order, or to run once per source element**. Compute data with declarative operations, use terminal operations to obtain results, and manage business side effects where the execution contract is explicit.
