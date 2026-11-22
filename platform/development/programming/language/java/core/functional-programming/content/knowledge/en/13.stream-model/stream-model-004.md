# Lazy Evaluation of Intermediate Operations in Java Stream

## 1. Lesson Objectives

A Java **Stream** describes a multi-stage data processing pipeline. A key aspect of this model is that **intermediate operations use lazy evaluation**: when you call `map`, `filter`, `flatMap`, `sorted`, or `distinct`, the program mainly **builds a pipeline** rather than immediately running every function on each element.

Execution is typically triggered by a **terminal operation** such as `toList`, `collect`, `forEach`, `count`, `reduce`, `findFirst`, or `anyMatch`. At that point, the Stream processes just enough of the data source to produce the requested result.

After this lesson, you will be able to:

- Distinguish between a source, an intermediate operation, and a terminal operation.
- Predict **when** lambdas in `map/filter` are invoked.
- Understand that **lazy intermediate operations** do not mean every pipeline always reads elements one by one in the same way, because `sorted` and `distinct` behave differently from `map/filter`.
- Analyze **short-circuiting** operations such as `limit`, `findFirst`, and `anyMatch`, as well as how behavior changes when `sorted` is present.
- Identify bugs that rely on side effects in `peek/map/filter`, since a Stream may optimize and skip some callback invocations.
- Avoid reusing a consumed Stream, relying on non-deterministic order in parallel execution, or mutating the data source while running.
- Verify behavior with a Java 17 program that produces clear output.

## 2. The Model: Source → Intermediate Operations → Terminal Operation

A typical pipeline:

~~~java
List<String> result = names.stream()
        .filter(s -> !s.isBlank())
        .map(String::strip)
        .map(String::toUpperCase)
        .toList();
~~~

There are three parts:

| Component | Example | Role |
| --- | --- | --- |
| **Source** | `names.stream()` | Provides the data to traverse |
| **Intermediate** | `filter`, `map` | Describes how to filter/transform, returning a Stream to chain steps |
| **Terminal** | `toList()` | Requests the final result, triggering pipeline evaluation |

Mental model diagram:

~~~text
List<String>
    |
    v
stream()  --> filter(...) --> map(...) --> map(...)
                                             |
                                      (not yet traversed)
                                             |
                                             v
                                          toList()
                                             |
                                    triggers evaluation
                                             |
                                             v
                                       List<String>
~~~

**Note:** `stream()` creates a Stream object; it does not mean a copy of the list has been created. A Stream typically only holds information about the source and the planned stages; it is not a list of intermediate results.

An important characteristic of the Stream API is **internal iteration**: the library coordinates fetching elements from the source and passing them through the stages, rather than the developer explicitly writing loops and intermediate lists. Different sources have different spliterator characteristics, sizes, and ordering; therefore, you should reason accurately using the Stream contract rather than assuming all sources are traversed identically.

## 3. What Does Lazy Mean?

Consider:

~~~java
Stream<String> pipeline = List.of("  An ", "Binh").stream()
        .map(String::strip)
        .filter(s -> s.length() > 2);
~~~

After this statement, the `pipeline` variable represents a processing workflow, but there is **no terminal operation yet**. Building the pipeline does not require `String::strip` or the `length() > 2` predicate to run on every string.

When you call:

~~~java
List<String> output = pipeline.toList();
~~~

Only then does the Stream begin evaluating the source and the steps needed to produce `List<String>`.

An observable example:

~~~java
AtomicInteger calls = new AtomicInteger();

Stream<String> stream = List.of(" A ", " B ").stream()
        .map(s -> {
            calls.incrementAndGet();
            return s.strip();
        });

System.out.println(calls.get());   // 0: pipeline just built.
System.out.println(stream.toList()); // [A, B]
System.out.println(calls.get());   // 2: terminal has run.
~~~

This snippet requires importing `AtomicInteger`, `List`, and `Stream` and placing it inside a method. The counter is only an **observation tool for learning purposes**; production business code should not rely on side effects inside `map` to count completed tasks.

### 3.1. "Lazy Evaluation" Is Different from "Running on Another Thread"

Lazy is **not** asynchronous. On a regular sequential stream, the terminal operation is called and executed on the calling thread (unless another execution mechanism is used by the program). A Stream does not automatically create a `Future`, make network API calls, or run the pipeline in the background.

~~~java
var filtered = numbers.stream().filter(n -> n > 0);
// This is a described Stream, not a task completed on a background thread.
long count = filtered.count();
// Terminal is called synchronously.
~~~

If you want to run work asynchronously, you need a mechanism such as an executor/`CompletableFuture`, which is separate from the concept of laziness. If you use a **parallel stream**, processing may use multiple threads, and callback execution order needs to be considered separately.

### 3.2. Lazy Is Not Caching

A Stream does not automatically store the results of `map/filter` for repeated use. It is **not equivalent to a cache**, nor is it a collection you can traverse over and over. Each Stream object is meant for a single pipeline consumed **once**.

If you want to reuse results, **materialize** the result in a terminal operation, such as `toList()`, and then create a new stream from that list when needed.

## 4. Intermediate Operations and Terminal Operations

### 4.1. Common Intermediate Operations

| Operation | Effect | Lazy? | Characteristics |
| --- | --- | --- | --- |
| `filter(Predicate)` | Keeps elements matching the condition | Yes | Usually stateless |
| `map(Function)` | Transforms each element | Yes | Usually stateless |
| `mapToInt(...)` | Converts to an IntStream | Yes | Usually stateless |
| `flatMap(...)` | Flattens sub-streams into a stream of elements | Yes | May create/close sub-streams during traversal |
| `peek(Consumer)` | Observes elements passing through | Yes | Unreliable for executing required side effects |
| `distinct()` | Removes duplicates using `equals/hashCode` | Yes | Stateful, may need to remember seen elements |
| `sorted()` | Sorts elements | Yes | Stateful, typically needs to buffer all input reaching the sort stage |
| `limit(n)` | Takes at most n elements | Yes | Short-circuiting intermediate |
| `skip(n)` | Skips the first n elements | Yes | Needs to track position/count state |

Even though `sorted` and `distinct` are **lazy**, when a terminal operation requests data through them, they may internally need to hold buffers/state to guarantee the result. "Lazy" only means that **constructing the pipeline does not immediately compute the result**, not that every step is stateless or uses only O(1) memory.

### 4.2. Common Terminal Operations

| Operation | Result | Notes |
| --- | --- | --- |
| `toList()` | `List<T>` | Java 16+; the returned list does not support mutation |
| `collect(...)` | Result per Collector | Can produce a List, Map, or summary |
| `forEach(...)` | `void` | Has side effects; parallel does not guarantee encounter order |
| `count()` | `long` | Can be optimized from source size without invoking callbacks |
| `reduce(...)` | Aggregated value | Must understand identity and associativity |
| `findFirst()` | `Optional<T>` | Short-circuiting terminal, prefers the first element in encounter order |
| `findAny()` | `Optional<T>` | May return any matching element; do not rely on order |
| `anyMatch(...)` | `boolean` | Can stop once a matching element is found |
| `allMatch(...)` | `boolean` | Can stop once a non-matching element is encountered |
| `noneMatch(...)` | `boolean` | Can stop once a matching element is encountered |

A pipeline can have **zero or more** intermediate operations, but usually has only **one** terminal operation for that Stream instance.

## 5. Terminal Operations Trigger On-Demand Evaluation of the Entire Pipeline

Look at this code snippet:

~~~java
List<Integer> answer = List.of(1, 2, 3, 4, 5).stream()
        .filter(n -> n % 2 == 1)
        .map(n -> n * 10)
        .toList();
~~~

The result is `[10, 30, 50]`. For a basic stateless pipeline on an ordered source with a terminal like `toList`, actual execution is often **fused** element by element:

~~~text
1 -> filter(true)  -> map(10) -> collector
2 -> filter(false)            -> skipped
3 -> filter(true)  -> map(30) -> collector
4 -> filter(false)            -> skipped
5 -> filter(true)  -> map(50) -> collector
~~~

There does not necessarily have to be a temporary list holding all odd numbers before mapping. Fusing steps into a single pass can reduce intermediate storage overhead and the number of traversals over the source.

However, this is an **intuitive model** of common sequential execution, not a guarantee on the exact number of callback invocations if the terminal can optimize, if the pipeline contains stateful operations, or if it runs in parallel. The exact contract is the **observable result according to Stream semantics**, not a fixed callback trace.

## 6. Short-Circuiting: Not All Data Needs to Be Processed

Laziness combined with early-stopping operations helps a Stream avoid unnecessary work.

### 6.1. anyMatch

~~~java
boolean hasEven = List.of(1, 3, 4, 6).stream()
        .anyMatch(n -> n % 2 == 0);
~~~

The result is `true`. On a regular sequential stream, `anyMatch` can stop after seeing 4 without needing to inspect 6. `anyMatch` returns `false` for an empty stream; `allMatch` and `noneMatch` on an empty stream return `true` by vacuous truth.

If you need to execute a callback for **every** element, `anyMatch` is not the right tool: its very purpose is to determine a boolean answer and stop as soon as enough data has been seen.

### 6.2. findFirst and findAny

~~~java
Optional<Integer> first = List.of(2, 4, 6).stream()
        .filter(n -> n >= 4)
        .findFirst();
~~~

`first` contains 4. For an ordered stream, `findFirst` returns the first element in encounter order. If there is **no result**, it returns `Optional.empty()`.

`findAny` can be more flexible, especially in parallel, and **should not be used when the rule requires strictly the first element**. Both are short-circuiting terminal operations.

### 6.3. limit

~~~java
List<Integer> firstTwo = List.of(10, 20, 30, 40).stream()
        .limit(2)
        .toList();
~~~

The result is `[10, 20]`. `limit(2)` is a lazy, short-circuiting intermediate operation. With an ordered source and a simple pipeline, the runtime can avoid processing subsequent elements once two elements have been taken. With an ordered parallel stream, preserving exact order can incur significant overhead.

It **does not mean** every callback is always called exactly twice: preceding operations, stateful stages, optimizations, and execution mode can all affect it. Rely on the **result value**, not on counting side effects.

## 7. Stateful Intermediate Operations: sorted and distinct

A pipeline consisting only of `filter` and `map` can usually process elements one by one. However, `sorted()` needs to know the comparison order of the elements entering the sort stage.

~~~java
int minimum = Stream.of(9, 2, 5)
        .sorted()
        .findFirst()
        .orElseThrow();
~~~

The result is `2`. To be certain which element is smallest in sorted order, a general-purpose sort step typically has to **consume all elements reaching that stage** before emitting the first element. Therefore, `findFirst()` does not mean "always read only one source element".

With `distinct()`, the Stream may need to store information about seen elements to avoid duplicates. `distinct` relies on `equals` and `hashCode` of the elements. On an ordered stream, `distinct` produces results stable with respect to encounter order; in parallel, guaranteeing stability can increase overhead.

### 7.1. sorted Before limit vs. limit Before sorted

~~~java
List<Integer> bestTwo = List.of(7, 1, 9, 3).stream()
        .sorted()
        .limit(2)
        .toList();

List<Integer> sortedPrefix = List.of(7, 1, 9, 3).stream()
        .limit(2)
        .sorted()
        .toList();
~~~

Results:

- `bestTwo = [1, 3]`: sorts **the entire source** and then takes the two smallest values.
- `sortedPrefix = [1, 7]`: takes only **the first two elements of the source**, and then sorts those two elements.

Changing operation placement does not just change performance—it can **completely change the business meaning**. Do not arbitrarily move `limit` before `sorted`.

### 7.2. filter Before sorted Is Usually Beneficial When Semantically Equivalent

~~~java
List<Integer> positive = numbers.stream()
        .filter(n -> n > 0)
        .sorted()
        .toList();
~~~

When the task is "sort only positive numbers", filtering first usually reduces the number of elements that must be sorted. However, if the condition depends on **position after sorting**, you must not move the filter earlier arbitrarily. Determine the business requirement and prove the two forms are equivalent before optimizing.

## 8. Do Not Put Required Side Effects in map, filter, or peek

An example that easily causes misunderstanding:

~~~java
long size = List.of("A", "B", "C").stream()
        .peek(System.out::println)
        .count();
~~~

Some people expect the three lines A/B/C to always be printed before `count` returns 3. **That expectation is not guaranteed by the API**. For a sized source and operations that do not change the element count, `count()` can compute the result without traversing the pipeline. In that case, the `peek` callback **may not run at all**.

This optimization does not make the terminal result wrong; `size` is still 3. The Java Stream API is allowed to elide certain steps when the final result is unaffected, so **never use `peek` to record transactions, invoke payments, perform required state updates, or enforce correctness**.

### 8.1. peek Is Not a Terminal Operation

`peek` is an intermediate operation and by itself **does not trigger the pipeline**:

~~~java
Stream<Integer> s = Stream.of(1, 2, 3)
        .peek(n -> System.out.println("seen: " + n));
// No terminal => does not yet require traversing the source.
~~~

`peek` is typically used for observation/debugging, with the awareness that how many times and when the callback runs may vary due to optimizations or execution mode.

### 8.2. When Business Logic Truly Requires an Action

Computation part:

~~~java
List<String> cleaned = names.stream()
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .toList();
~~~

Action execution part:

~~~java
cleaned.forEach(thisService::publish);
~~~

These two snippets assume `names` and `thisService` are in context. Even `forEach` still requires error handling and ordering per requirements; individual I/O calls do not automatically form a shared transaction. However, separating **producing the result** from **outputting/applying effects** makes the code's intent clearer and easier to test.

### 8.3. Side Effects in Predicates/Filters

~~~java
AtomicInteger checked = new AtomicInteger();
boolean found = IntStream.rangeClosed(1, 10)
        .filter(n -> {
            checked.incrementAndGet();
            return n % 3 == 0;
        })
        .anyMatch(n -> n > 4);
~~~

This is an illustrative measurement in a sequential pipeline: the condition finds element 6 after checking 1 through 6 in order. In production code, do not use `checked` as a required audit counter, because Streams allow short-circuiting and optimizations. If you need to count every input accurately for business purposes, do so in an orchestration flow with an explicit contract rather than relying on incidental callback counts.

## 9. A Stream Object Can Only Be Consumed Once

~~~java
Stream<Integer> stream = Stream.of(1, 2, 3);
long size = stream.count();

// IllegalStateException if you try to reuse it:
// long sum = stream.mapToInt(Integer::intValue).sum();
~~~

After a terminal operation, a Stream is considered **consumed**. Do not reuse a Stream object to invoke another terminal operation or attach more intermediate operations.

If you need two results from the same source, create two separate Streams:

~~~java
List<Integer> numbers = List.of(1, 2, 3);

long size = numbers.stream().count();
int sum = numbers.stream().mapToInt(Integer::intValue).sum();
~~~

Or, if appropriate, use a single collector that aggregates multiple metrics in **one pass**. Choose based on performance and readability requirements.

**Additional note:** the fact that a pipeline produces a result does not mean it automatically snapshots the entire source. When traversing mutable data, source and non-interference rules must still be followed.

## 10. Do Not Interfere with the Source While Running

The Stream documentation requires behavioral parameters to generally be **non-interfering** (not modifying the source being traversed) and in many cases **stateless** to avoid state dependencies across invocations.

Do not write:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
numbers.stream().forEach(n -> numbers.add(n));
// Interfering with the source during traversal: may throw ConcurrentModificationException
// or cause unexpected behavior.
~~~

This is a **counterexample**, not meant to be run in the exercise. Depending on the source and modification-detection mechanism, the outcome may vary; you should not assert that every stream throws the exact same exception type.

If you want to create new data:

~~~java
List<Integer> doubled = numbers.stream()
        .map(n -> n * 2)
        .toList();
~~~

This creates a separate result list without adding elements to the source list.

### 10.1. Source Changes Between Stream Creation and Terminal Operation

Because pipelines are lazy, some sources are **late-binding** and may reflect changes that occur before the terminal operation starts. However, exact behavior depends on the source/spliterator; **you should not mutate the source and expect a specific snapshot or trace**.

Need a consistent result at a specific point in time? Create a data snapshot under clear ownership, such as a new list containing the elements to process, and do not modify it during traversal. `List.copyOf` creates a copy that does not support structural mutation of the list, but **does not deep-copy** mutable elements.

## 11. Sequential vs. Parallel: Laziness Still Holds, Callback Order May Differ

Both sequential and parallel streams describe pipelines with lazy intermediate operations. The difference lies in how the terminal operation coordinates execution:

- **Sequential:** processes sequentially; with an ordered source, many operations preserve encounter order.
- **Parallel:** may split data across multiple threads, invoking callbacks at different times and in different orders.
- `forEach` on a parallel stream does not guarantee encounter order; if encounter order must be preserved, `forEachOrdered` provides an ordering contract but may reduce parallelism benefits.
- `findAny` may return any matching element, especially in parallel; `findFirst` must respect encounter order if present.
- Stateful operations like `sorted` and `distinct`, or `limit` on an ordered parallel stream, can introduce barriers and consume extra resources.

A lambda that mutates a shared variable does not automatically become thread-safe just because it runs through the Stream API:

~~~java
// Avoid using in parallel when shared is not protected:
// source.parallelStream().forEach(x -> shared.add(x));
~~~

Even when the source is concurrent, code inside the callback must still obey the thread-safety contract of any object being mutated. Do not turn on `parallel()` just because you heard it is "faster"; consider workload size, splitting/merging overhead, ordering, and real benchmarks.

## 12. Optimizations and Limits of Reasoning

### 12.1. count() and Known Source Size

~~~java
long total = List.of(10, 20, 30).stream()
        .map(n -> n * 2)
        .count();
~~~

The result is 3. When there are no operations that change the number of elements and the source size is known, Java can deduce the count without calling the mapper. This **does not make count wrong**, but serves as a reminder that `map` is not the place for required side effects.

### 12.2. filter Makes the Element Count Unknown Upfront

~~~java
long positiveCount = List.of(-1, 0, 2, 3).stream()
        .filter(n -> n > 0)
        .count();
~~~

The result is 2. To determine how many elements match the condition, the runtime normally has to evaluate the corresponding predicate. Even so, callback invocations are still not a contract for business reporting: if you need audit information, model it in the result or in an explicit process.

### 12.3. Why Optimizations Are Not Algorithmic Guarantees

Do not conclude "Java 17 is guaranteed to run exactly n callbacks in example X" across every JDK and every source. The specification focuses on **results and correctness**, whereas implementations may optimize, fuse, swap strategies, or skip unnecessary parts within permitted bounds.

The number of behavioral parameter invocations and the threads running them can vary, especially with short-circuiting and parallel pipelines. Use side effects in examples to **understand how common implementations work**, but do not treat that trace as a business logic invariant.

## 13. Complete Java 17 Program

The example below illustrates these phenomena:

1. Building a pipeline does not immediately run the mapper.
2. Terminal `toList()` triggers element transformation.
3. `anyMatch` can stop early on a sequential pipeline.
4. `sorted` may need to read all input elements before `findFirst`.

Create the file **LazyStreamDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class LazyStreamDemo {
    public static void main(String[] args) {
        AtomicInteger mapped = new AtomicInteger();

        Stream<String> pipeline = List.of(
                " An ", " ", "Binh", " Chi "
        ).stream()
                .map(s -> {
                    mapped.incrementAndGet();
                    return s.strip();
                })
                .filter(s -> !s.isEmpty())
                .map(s -> s.toUpperCase(Locale.ROOT));

        System.out.println("after building: " + mapped.get());

        List<String> values = pipeline.toList();
        System.out.println("after toList: " + mapped.get());
        System.out.println("values: " + values);

        AtomicInteger inspected = new AtomicInteger();
        boolean matched = IntStream.rangeClosed(1, 10)
                .filter(n -> {
                    inspected.incrementAndGet();
                    return n % 3 == 0;
                })
                .anyMatch(n -> n > 4);

        System.out.println("anyMatch: " + matched);
        System.out.println("inspected: " + inspected.get());

        AtomicInteger sortedInput = new AtomicInteger();
        int first = Stream.of(9, 2, 5)
                .map(n -> {
                    sortedInput.incrementAndGet();
                    return n;
                })
                .sorted()
                .findFirst()
                .orElseThrow();

        System.out.println("sorted first: " + first);
        System.out.println("sorted input: " + sortedInput.get());

        List<Integer> smallestTwo = List.of(7, 1, 9, 3)
                .stream()
                .sorted()
                .limit(2)
                .toList();

        System.out.println("smallest two: " + smallestTwo);
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac LazyStreamDemo.java
java LazyStreamDemo
~~~

**Output when running this sequential program:**

~~~text
after building: 0
after toList: 4
values: [AN, BINH, CHI]
anyMatch: true
inspected: 6
sorted first: 2
sorted input: 3
smallest two: [1, 3]
~~~

### 13.1. Line-by-Line Explanation

- **after building: 0** — the mapper has not run yet merely because the pipeline was declared.
- **after toList: 4** — the source has four strings; the first mapper executed for all of them in this specific sequential Java pipeline. A whitespace-only string was removed by the filter, but it was still processed by the mapper before the filter.
- **values: [AN, BINH, CHI]** — the data has been stripped, empty strings filtered out, and uppercased. `toList()` creates a result list that does not support mutation.
- **anyMatch: true** — there is a number divisible by 3 and greater than 4: the number 6.
- **inspected: 6** — in this sequential pipeline, the `filter` predicate inspected 1 through 6 in order until the terminal had enough to conclude, so it stopped before 7 through 10.
- **sorted first: 2** — the first element after sorting 9, 2, 5 is 2.
- **sorted input: 3** — the sort stage processed all three numbers in the source to determine the order.
- **smallest two: [1, 3]** — sorted in ascending order first, then took the two smallest numbers.

The counters here are for observing **a specific pipeline with deterministic sequential operations**. In production code, you should not rely on a callback always running a fixed number of times when changing the terminal, source, mode, or JDK.

## 14. How to Test Lazy Evaluation

For lessons or examples in unit tests, you can use a counter to observe that building the pipeline **has not yet executed the transformation**:

~~~java
AtomicInteger invoked = new AtomicInteger();

Stream<String> pending = Stream.of("A", "B")
        .map(s -> {
            invoked.incrementAndGet();
            return s.toLowerCase(Locale.ROOT);
        });

if (invoked.get() != 0) {
    throw new AssertionError("Unexpected eager evaluation");
}

List<String> result = pending.toList();

if (!result.equals(List.of("a", "b"))) {
    throw new AssertionError("Unexpected result: " + result);
}
~~~

This is a snippet inside a method with imports for `AtomicInteger`, `Stream`, `List`, and `Locale`; it is not a standalone runnable file.

Tests should prioritize **output values**, not consuming the source before the terminal operation, and the business contract. Do not write tests expecting `peek` to always print exactly n lines before `count`, because the specification allows other optimizations.

If you need to test that an important action **must happen** for each element, make that action the responsibility of an orchestrator/terminal layer with an explicit contract, and verify the observable outcome rather than indirectly relying on side effects in `map`.

## 15. Common Pitfalls

| Pitfall | Consequence | How to Fix |
| --- | --- | --- |
| Believing `map` runs immediately when called | Easy to log/compute work at the wrong time | Remember intermediate is lazy; terminal triggers execution |
| Thinking lazy means running on a background thread | Confuses performance/concurrency | Lazy and async/parallel are different concepts |
| Putting business side effects in `peek` | Callback may be skipped during optimization | Use an intentional execution step |
| Expecting `count()` to always traverse every element | Sized sources may compute count directly | Rely on the count value, not side effects |
| Thinking `findFirst` only reads one source element | `sorted` may need all elements | Consider the entire pipeline, not just the terminal |
| Changing `sorted().limit(2)` to `limit(2).sorted()` | Result/meaning changes | Keep operation order per the contract |
| Reusing a Stream after `toList`/`count` | `IllegalStateException` | Create a new stream from the source or store the result |
| Modifying the source collection in a callback | May cause wrong behavior or an exception | Do not interfere with the source during traversal |
| Using shared mutable state in parallel callbacks | Race conditions/lost updates | Isolate state, use a collector, or synchronize |
| Relying on `findAny` ordering | Result may not be the first element | Use `findFirst` if encounter order is needed |
| Thinking all intermediate operations are stateless | `sorted/distinct` have state and buffers | Check each operation's characteristics |
| Measuring performance by `peek` line count | Logs do not reflect actual work done | Benchmark the real scenario and measure results/cost |

## 16. Practice Exercises

### Exercise 1: Predict Execution Timing

~~~java
AtomicInteger counter = new AtomicInteger();
Stream<Integer> pipeline = Stream.of(2, 4, 6)
        .map(n -> {
            counter.incrementAndGet();
            return n * 10;
        });
System.out.println(counter.get());
System.out.println(pipeline.toList());
~~~

Predict the two printed lines in this sequential program.

**Answer:** `0`, then `[20, 40, 60]`. The `map` lambda does not need to run before the `toList` terminal.

### Exercise 2: Conditional Short-Circuiting

~~~java
boolean result = IntStream.rangeClosed(1, 100)
        .filter(n -> n % 7 == 0)
        .anyMatch(n -> n > 20);
~~~

**Answer:** `true`, because 21 is the first multiple of 7 greater than 20. A sequential implementation can stop upon seeing 21; it does not need to traverse up to 100 to decide the boolean result.

### Exercise 3: Operation Order

Given `[10, 2, 8, 1]`, evaluate:

~~~java
numbers.stream().sorted().limit(2).toList();
numbers.stream().limit(2).sorted().toList();
~~~

**Answer:** `[1, 2]` and `[2, 10]`, respectively. The first finds the two smallest values; the second only sorts the first two values appearing in the source.

### Exercise 4: Should You Use peek for Auditing?

An application wants to ensure every valid order is audited. The author writes:

~~~java
long total = orders.stream()
        .peek(thisService::audit)
        .count();
~~~

This is a snippet with hypothetical `orders` and `thisService`. **Answer:** Not appropriate. `count` can optimize without traversing, so auditing is not guaranteed to run. Separate audit logging into an operation with an explicit execution contract, handling transactions/errors if needed.

### Exercise 5: Design a Pipeline

You have a list of transactions. Requirement: select valid transactions, take the three with the highest amounts, and convert them to display DTOs.

**Suggested solution:** `filter(valid)` → `sorted(byAmountDescending)` → `limit(3)` → `map(toDto)` → `toList()`. Consider the order if validity rules depend on converted currency amounts, and choose an appropriate numeric type to avoid overflow or rounding errors. Note that `sorted` typically incurs storage/buffering cost, especially if the source is very large.

## 17. Key Takeaways

**Stream intermediate operations are lazily evaluated**: declaring `map/filter/sorted` mainly constructs a pipeline and does not immediately process all data. A terminal operation triggers evaluation **just enough to produce the result**, and short-circuiting/optimizations may cause some elements or callbacks to be skipped.

- **Lazy is not async or a cache.**
- **Stateless** operations like `map/filter` can be fused element by element; **stateful** operations like `sorted/distinct` may require extra memory or consume more input.
- **Short-circuiting** operations like `limit/findFirst/anyMatch` allow stopping early when semantics permit.
- **Side effects in callbacks are not guaranteed to run a specific number of times**; in particular, avoid using `peek` for required actions.
- **Each Stream can only be consumed once**; avoid modifying the source during traversal.
- **Results and business contracts** matter more than the execution trace of individual callbacks.

When reading Stream code, always look for the **terminal operation**, check the order of steps, note stateful/short-circuiting properties, and check whether any logic would break when the JVM optimizes or when switching to parallel.
