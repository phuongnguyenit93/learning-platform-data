# Steps Can Be Combined in a Single Pass in Java Stream

## 1. What Happens Behind a Stream Pipeline

With the Java Stream API, we can chain multiple *intermediate operations* such as `filter()`, `map()`, `peek()` and a *terminal operation* such as `toList()`, `findFirst()`, or `sum()`:

~~~java
List<Integer> result = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .toList();
~~~

The snippet above is an illustration inside a method where `numbers` is a `List<Integer>` and `java.util.List` is imported. Reading it in business terms: keep even numbers, multiply by 10, collect the result.

A common misconception is thinking Java **always** executes sequentially like this:

1. Traverse all of `numbers` and create a list containing all even numbers.
2. Traverse that entire list and create a list containing all numbers multiplied by 10.
3. Traverse the second list to put them into the result.

With **stateless** intermediate operations like `filter` and `map`, the sequential processing model is usually **element-by-element across multiple steps** (*vertical processing*, also known as pipeline fusion):

~~~text
Source         filter(even)           map(*10)           terminal toList
  1 ─────────► reject
  2 ─────────► keep ───────────────► 20 ────────────────► write 20
  3 ─────────► reject
  4 ─────────► keep ───────────────► 40 ────────────────► write 40
  5 ─────────► reject
~~~

In this mental model, each element passes through the processing chain before the next element is requested, rather than necessarily creating an intermediate collection after **every** method in the pipeline.

**Key takeaway of this article:** Intermediate operations can be **combined in a single source traversal**. However, this should not be understood as a mechanical guarantee that *every* pipeline is always a simple loop, uses no buffers, never re-processes data anywhere, or must invoke every callback exactly once.

## 2. Three Components: Source, Intermediate Operations, and Terminal Operation

A Stream pipeline typically consists of:

| Part | Example | Role |
|---|---|---|
| **Source** | `list.stream()`, `Arrays.stream(...)`, `IntStream.range(...)` | Provides the sequence of elements to traverse |
| **Intermediate operation** | `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit` | Sets up a new processing step, usually without traversing the source immediately |
| **Terminal operation** | `toList`, `collect`, `sum`, `anyMatch`, `findFirst`, `forEach` | Triggers pipeline consumption and produces a result/side effect |

Example:

~~~java
Stream<String> pipeline = names.stream()    // Source.
        .filter(s -> !s.isBlank())           // Intermediate.
        .map(String::strip);                // Intermediate.

List<String> cleaned = pipeline.toList();    // Terminal.
~~~

This is an illustration with `names` and `List`/`Stream` imports. Calling `filter` and `map` builds the processing steps; the pipeline only begins executing when `toList()` consumes it.

**Laziness** here means the evaluation of intermediate operations is deferred until needed. It helps:

- Avoid creating unused intermediate results.
- Stop early when the terminal operation has enough data.
- Combine processing steps without manually writing multiple separate loops.
- Allow the library to perform certain optimizations when the correctness of the result is preserved.

However, a Stream does not automatically cache results after a terminal operation, and a consumed stream object **cannot be reused**.

## 3. Java 17 Program: Observing Each Element Passing Through the Pipeline

Save as **`PipelineFusionDemo.java`**:

~~~java
import java.util.List;

public class PipelineFusionDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5);

        System.out.println("pipeline constructed");

        List<Integer> result = numbers.stream()
                .filter(n -> {
                    System.out.println("filter:" + n);
                    return n % 2 == 0;
                })
                .map(n -> {
                    System.out.println("map:" + n);
                    return n * 10;
                })
                .limit(2)
                .toList();

        System.out.println("result=" + result);
    }
}
~~~

Compile and run with **JDK 17 or higher**:

~~~bash
javac PipelineFusionDemo.java
java PipelineFusionDemo
~~~

Stdout output in a sequential pipeline using the source `List.of(1,2,3,4,5)`:

~~~text
pipeline constructed
filter:1
filter:2
map:2
filter:3
filter:4
map:4
result=[20, 40]
~~~

**Exact order explanation:**

1. The line `pipeline constructed` runs before the Stream pipeline below starts. Intermediate calls like `filter`, `map`, `limit` do not force traversing the entire source immediately.
2. Element `1` enters `filter`; it is rejected, so it **does not reach `map`**.
3. Element `2` passes `filter` and is immediately transformed into `20` by `map`.
4. Element `3` is rejected.
5. Element `4` passes `filter` and `map`, producing `40`.
6. Once `limit(2)` has received two results, the terminal operation does not need to request element `5`. The pipeline finishes with `[20,40]`.

Notably, the print order is `filter:2` then `map:2`, **not** `filter:1`, `filter:2`, ..., `filter:5` followed by all `map` lines. This is a clear illustration of **per-element combined processing** in a typical sequential pipeline.

In this example, `println` is placed inside callbacks to demonstrate the mechanism. **Do not turn log lines/counters inside intermediate operations into business requirements**, because the Stream API has optimizations and different execution modes that are permitted to skip certain callback invocations.

## 4. What Does “Single Pass” Mean Exactly?

There are three levels to distinguish:

**(a) Traversing the source once per consuming pipeline.** In a basic sequential pipeline, the terminal operation requests elements from the source and pushes them through the intermediate steps. There is no need to create a list after `filter` and then traverse that list again after `map`.

**(b) A single element can pass through multiple transformations.** For example, `filter` can reject an element, preventing `map` from running on it. If it is kept, `map` can immediately produce a value to pass downstream.

**(c) Not every step requires only O(1) memory or allows emitting results immediately.** Stateful operations like `sorted()` may need to hold data to produce the correct order. `distinct()` may need to store information about previously seen values. `flatMap()` may open each sub-stream and traverse the elements inside it.

Therefore, **combining steps in one pipeline** does not mean:

- Every source element must be inspected.
- Every user callback is invoked.
- Every callback runs exactly once in all situations.
- There are no buffers or auxiliary data structures.
- There is no processing of multiple chunks when running in parallel.
- It is always faster than every manual loop.

The Stream specification focuses on **results and behavioral contracts**, not committing to a fixed loop shape or object graph across all JDKs.

## 5. Stateless Operations: Ideal for “Vertical” Processing

Some common intermediate operations:

| Operation | Nature | Can pass each element to the next step? |
|---|---|---|
| `map(Function)` | One element to one value | Usually yes |
| `mapToInt(ToIntFunction)` | One object to one `int` | Usually yes |
| `filter(Predicate)` | Keep or reject an element | Usually yes; may emit no value |
| `peek(Consumer)` | Perform an action on an element as it is consumed | Yes; mainly for debugging, no guarantee every action runs |
| `flatMap(Function<T,Stream<R>>)` | One element produces a sub-stream | May emit multiple sub-elements; needs to traverse the sub-stream |
| `limit(n)` | Caps the number of elements passing downstream | Can stop early, depending on data and order |
| `skip(n)` | Skips the first elements | May pass through/discard elements before emitting further |

`map` and `filter` are classic examples of **stateless operations**: their callbacks do not need to remember every previously seen element to apply the operation to the current element. `flatMap` can emit a variable number of elements per source element, so the output count differs from the input count; that does not mean it has to materialize the entire output by default.

### 5.1. Distinguishing Stateless Operations from Stateful Lambdas

`map` is classified as a stateless intermediate operation, **but the lambda passed by the programmer can still be stateful**:

~~~java
// NOT RECOMMENDED if using external mutable state:
AtomicInteger counter = new AtomicInteger();

List<Integer> values = numbers.stream()
        .map(n -> n + counter.incrementAndGet())
        .toList();
~~~

This is an illustration with `numbers` and `AtomicInteger` imported. Even though `map` is a stateless operation, the callback accesses external state that mutates with each invocation. This makes the result hard to reason about when switching to a parallel stream, changing the terminal operation, or applying optimizations.

You should write mappers that are **pure, non-interfering with the source (*non-interfering*), and independent of mutable state** whenever possible, especially in parallel pipelines.

### 5.2. `flatMap` Is Not a Single-Level Loop

~~~java
List<String> words = groups.stream()
        .flatMap(List::stream)
        .map(String::toUpperCase)
        .toList();
~~~

`groups` in the illustration is `List<List<String>>`. `flatMap` opens each sub-list and emits `String` elements down to `map`. Java can combine these steps, but the nature of the operation is traversing both the outer source and the elements of the sub-sources, **not** a “one get call per outer element” operation with a fixed one-to-one output.

## 6. Stateful Operations: When Memory or Processing Boundaries Are Required

A **stateful** intermediate operation needs information from other elements to determine the result.

### 6.1. `sorted()`

To emit output in the right order, `sorted()` typically needs to **receive the elements and sort them** before downstream can process them in final order.

~~~java
List<String> ordered = Stream.of("pear", "fig", "apple")
        .sorted()
        .map(String::toUpperCase)
        .toList();
// [APPLE, FIG, PEAR]
~~~

The snippet above is an illustration inside a method, requiring `Stream`/`List` imports. You should not expect `sorted` to always emit the first element as soon as it receives it, because a smaller element could still appear later in the source.

### 6.2. `distinct()`

`distinct()` needs to know which values have already appeared in order to remove duplicates. On an ordered stream, preserving the selection of the first element—especially during parallel processing—can require extra memory or synchronization.

~~~java
List<String> unique = Stream.of("a", "b", "a", "c")
        .distinct()
        .toList();
// [a, b, c]
~~~

For `Stream<T>`, `distinct` relies on `Object.equals()`; objects with mutable state that changes the result of `equals/hashCode` during processing are a source of unpredictable bugs.

### 6.3. `sorted`, `distinct`, and `limit`

These operations have different processing characteristics:

- `sorted()` is a stateful operation; with a finite source, sorting may need to buffer many elements. With an infinite source, `sorted()` usually cannot produce the first element or complete.
- `distinct()` may need a set of seen values; with an infinite source containing many unique values, state memory can grow.
- `limit(n)` is a **short-circuiting stateful intermediate operation**; it tracks how many elements are allowed to be emitted and can cut off the source early in appropriate situations.

`limit` is classified as stateful because it needs to remember how many elements have been emitted. However, this level of state is completely different from `sorted`, which needs to process/hold many elements to sort them.

**Distinguish between “the pipeline is still lazy” and “every step can emit output immediately”**. A pipeline with `sorted` can still be lazy in the sense that **it does not run until a terminal operation is present**, yet when it runs it may create a buffering boundary.

## 7. Java 17 Program: Buffering Boundary at sorted()

Save the file **`SortedPipelineDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class SortedPipelineDemo {
    public static void main(String[] args) {
        List<String> names = List.of("kiwi", "pear", "fig");

        List<String> sorted = names.stream()
                .filter(s -> {
                    System.out.println("source:" + s);
                    return true;
                })
                .sorted(Comparator.comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder()))
                .map(s -> {
                    System.out.println("map:" + s);
                    return s.toUpperCase(Locale.ROOT);
                })
                .toList();

        System.out.println("result=" + sorted);
    }
}
~~~

Compile and run:

~~~bash
javac SortedPipelineDemo.java
java SortedPipelineDemo
~~~

Stdout of the sequential pipeline on this list:

~~~text
source:kiwi
source:pear
source:fig
map:fig
map:kiwi
map:pear
result=[FIG, KIWI, PEAR]
~~~

**Analysis:**

1. `filter(s -> true)` includes a print statement to observe when elements **enter** `sorted`. In this demo program, it accepts all three elements.
2. `sorted(Comparator.comparingInt(String::length).thenComparing(...))` sorts by **ascending length**, then by **natural order** for equal lengths. `fig` has 3 characters, `kiwi` and `pear` have 4 characters, and `kiwi` comes before `pear`.
3. In the demonstrated sequential execution, all three `source` lines are printed before any `map` lines appear. `sorted` must know the data to be sorted before emitting results in the right order.
4. `map` receives each element **after sorting**, converting it to uppercase using `Locale.ROOT`.
5. The pipeline still uses a single chain of Stream operations; the programmer **does not need** to manually create intermediate lists and write multiple loops. However, one cannot conclude that auxiliary memory is O(1): `sorted` may need to buffer.

Note that the `println` statements in intermediate operations are used **intentionally for demonstration**, not as an API guarantee of side effects across other optimizations, terminal operations, or source types.

## 8. Short-Circuiting: Combining Steps and Stopping When Enough

`findFirst()`, `findAny()`, `anyMatch()`, `allMatch()`, and `noneMatch()` are terminal operations that can **stop early** once enough information is obtained. `limit(n)` also provides the ability to cut off the rest of the source.

Example:

~~~java
Optional<String> first = names.stream()
        .filter(s -> s.startsWith("A"))
        .map(String::toUpperCase)
        .findFirst();
~~~

The illustration has `names` of type `List<String>`, `Optional` imported, and a stream with encounter order from `List`. If the first matching element appears early, the pipeline does not need to process all remaining elements.

### 8.1. Java 17 Program: findFirst Stops After One Result

Save **`ShortCircuitPipelineDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Optional;

public class ShortCircuitPipelineDemo {
    public static void main(String[] args) {
        List<String> words = List.of("alpha", "beta", "gamma");

        Optional<String> first = words.stream()
                .filter(s -> {
                    System.out.println("check:" + s);
                    return s.length() > 4;
                })
                .map(s -> {
                    System.out.println("map:" + s);
                    return s.toUpperCase(Locale.ROOT);
                })
                .findFirst();

        System.out.println("first=" + first.orElse("none"));
    }
}
~~~

Run commands:

~~~bash
javac ShortCircuitPipelineDemo.java
java ShortCircuitPipelineDemo
~~~

Stdout:

~~~text
check:alpha
map:alpha
first=ALPHA
~~~

`alpha` is the first element and has length 5, so it satisfies `s.length() > 4`. `findFirst()` already has the right result according to encounter order and can stop the pipeline, so there is no need to check `beta` or `gamma`.

**If switched to `parallel()`**, Java may check multiple elements across multiple workers before finding the result, so you must not rely on **callback counts** or log order like in the sequential program above. The `findFirst()` result value on an ordered stream still respects encounter order, but the execution path may differ.

### 8.2. Placement of limit and filter

~~~java
// Limits the number of source elements passed through before filtering.
stream.limit(5).filter(predicate)

// Selects at most five elements that satisfy the condition after filtering.
stream.filter(predicate).limit(5)
~~~

The two pipelines can return different results. With an infinite source and a predicate that is never true, `filter(predicate).limit(5).toList()` may **never terminate**, even with `limit(5)` after it, because it never receives five elements passing the filter. If you need to limit the number of attempts, place `limit` before `filter`.

## 9. Optimization: Skipping an Intermediate Step When It Does Not Affect the Result

A subtle fact: **The Stream API does not promise to invoke every behavioral parameter** if the implementation can prove it can compute the terminal result without running that part.

Example:

~~~java
long count = List.of("a", "bb", "ccc").stream()
        .map(s -> {
            System.out.println("mapping:" + s);
            return s.toUpperCase();
        })
        .count();
~~~

This is an illustration; **do not treat the number of `mapping` lines as a guaranteed output**. An implementation that knows the exact element count of the source, and also knows `map` does not change the element count, can compute `count() == 3` **without running the mapper**. This optimization is explicitly mentioned in the `Stream.count()` documentation.

Therefore, the statement “a stream combines steps in a single pass” **does not mean** “every intermediate operation is guaranteed to execute.” Sometimes a terminal operation is optimized so it **does not need to traverse** part of the source while still producing the correct result under the Stream contract.

### 9.1. Side Effects Are Not a Guaranteed Mechanism

~~~java
// Do not use this pattern to enforce auditing for every element.
long count = records.stream()
        .peek(this::audit)
        .count();
~~~

If the implementation can compute `count` from the source size, `peek` may **not run**. Even when the terminal operation requires traversal, short-circuiting may stop early. Therefore `peek` is better suited for debugging/observation under controlled conditions, and **should not be used to perform mandatory business logic**.

If the goal is to audit every record, organize a separate operation with a clear contract for processing all elements, error handling, transactions, and execution order; do not rely on intermediate pipeline side effects.

### 9.2. Do Not Measure Performance by Callback Counts in a Single Example

The benefits of pipeline fusion typically come from reducing intermediate collections and processing element-by-element, but performance also depends on:

- The actual cost of the mapper/predicate.
- Source organization, CPU memory/cache, and primitive vs. boxed types.
- The degree of buffering in stateful operations.
- JIT optimizations and JDK version.
- Splitting/coordination overhead when using `parallel()`.
- Final allocation/copying cost at `collect()`/`toList()`.

When performance matters, use an appropriate benchmark (e.g., JMH) with representative data, rather than concluding “streams are always faster than loops” based only on a small example.

## 10. Comparison with Loops and Multiple Intermediate Collections

Suppose we need to get even numbers and multiply by 10. A manual approach:

~~~java
List<Integer> evens = new ArrayList<>();
for (Integer n : numbers) {
    if (n % 2 == 0) {
        evens.add(n);
    }
}

List<Integer> result = new ArrayList<>();
for (Integer n : evens) {
    result.add(n * 10);
}
~~~

This is an illustration with `numbers` of type `List<Integer>` and `ArrayList`/`List` imports. This approach creates an **intermediate `evens`** and traverses it again.

Stream pipeline:

~~~java
List<Integer> result = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .toList();
~~~

Expresses the same transformation with fewer declarative steps. With stateless `filter` and `map`, Stream can chain the steps without creating an intermediate `List` for `evens`. `toList` still has to create/hold the **final result** as required by the API.

A **single loop** can also do the same thing without an intermediate list:

~~~java
List<Integer> result = new ArrayList<>();
for (Integer n : numbers) {
    if (n % 2 == 0) {
        result.add(n * 10);
    }
}
~~~

Thus, the advantage of Stream **is not that Java invented a “single loop” capability that loops lack**, but rather a **clear declarative way to chain transformations so the library coordinates execution**. If business logic requires multiple `break`/`continue` statements, ordered state updates, or complex exception handling, an explicit loop can be easier to read and control.

## 11. One Pipeline Does Not Mean One Scan for Every Problem

Some situations algorithmically require **multiple data processing steps**:

### 11.1. Sorting Requires Collecting Then Sorting

`sorted()` may have to accumulate many or all elements to sort them. Only then are elements pushed downstream in order. Even if the code is a single pipeline, it is not simply equivalent to an O(n) single scan with O(1) memory.

### 11.2. `distinct()` Needs to Remember Seen Elements

To remove duplicates, the implementation may maintain a set or equivalent structure. When data is large, the amount of state can also be large. With ordered streams and parallelism, preserving the exact encounter order adds extra overhead.

### 11.3. A Terminal Operation Can Collect All Data

`toList()` and `collect(toList())` need to store the final result. `groupingBy()` also creates a map structure and groups. Combining operations does not eliminate the need to store data to serve the **requested result**.

### 11.4. The Difference with Multiple Terminal Operations

~~~java
long size = numbers.stream().count();
int max = numbers.stream().mapToInt(Integer::intValue).max().orElse(0);
~~~

Here there are **two different pipelines** and potentially **two different traversals** (or optimized ones). Laziness does not turn a single-use `Stream` into an object that can run multiple terminal operations.

If multiple aggregate metrics are needed from an expensive source, consider using a combined collector or a properly contracted record accumulator instead of re-running the source multiple times. However, a compatible combiner must be designed if running in parallel.

## 12. Sequential and Parallel: Still Combining Steps, Different Execution

### 12.1. Sequential Stream

In `list.stream().filter(...).map(...).toList()`, the mental model “each element goes through the steps” is usually helpful. The source is a `List` with encounter order; when using order-preserving operations and an appropriate terminal operation, the result order is preserved.

### 12.2. Parallel Stream

With `list.parallelStream()`, the source can be **split into multiple parts** for parallel processing. Each worker applies the pipeline steps to its chunk of data, and then the results can be merged.

~~~java
List<Integer> squares = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(n -> n * n)
        .boxed()
        .toList();
~~~

With a stream that has encounter order and an order-preserving transformation, the logical result is still `[1, 4, 9, 16, 25]`. However, workers **do not necessarily process values in 1 → 5 order**, and callbacks with side effects must not rely on execution order.

**Distinction:**
- *Encounter order* is the order of elements according to the source/pipeline semantics.
- *Execution order* is the actual order in which callbacks and tasks run.
- *Output order* depends on the terminal operation's contract. For instance, `forEach` on a parallel stream does not promise to preserve encounter order, whereas `forEachOrdered` applies appropriate ordering constraints.

Using `parallel()` does not automatically guarantee faster execution: `sorted`, `distinct`, and `limit` on an ordered source may require coordination/buffering and incur significant overhead.

## 13. Primitive Sources and Avoiding Unnecessary Boxing

A pipeline like:

~~~java
int total = IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .map(n -> n * 2)
        .sum();
~~~

uses `IntStream` throughout; the steps operate on primitive `int`, without needing to create an `Integer` for each element. The result is `2 * (2+4+6+8+10) = 60`.

Meanwhile:

~~~java
int total = boxedNumbers.stream()
        .filter(n -> n % 2 == 0)
        .mapToInt(Integer::intValue)
        .sum();
~~~

`boxedNumbers` is `List<Integer>`; `mapToInt` converts to a primitive stream. If the original data is primitive or very large, choosing the right `IntStream`/`LongStream`/`DoubleStream` can reduce boxing/unboxing and express the aggregation more accurately.

Even when operations can be combined, **element types** and **per-step cost** still affect performance.

## 14. Common Misconceptions About “Single Pass”

| Misconception | Why it is wrong | Correct understanding |
|---|---|---|
| “Every `filter()`/`map()` creates a new list” | Intermediate operations usually only build the pipeline | Intermediate results are not necessarily materialized |
| “`filter` always finishes traversing everything before `map` runs” | Stateless operations can process element-by-element | `filter` and `map` usually interleave in sequential traversal |
| “One pipeline = O(1) memory” | `sorted`, `distinct`, collectors can hold state | Distinguish fusion from auxiliary memory |
| “Every lambda always runs once per element” | `filter` blocks downstream, short-circuiting and optimizations skip steps | Do not use intermediate callbacks as side-effect guarantees |
| “`Stream.count()` always runs `map`” | The API can infer size and skip the mapper | Rely only on the `count` result, not mapper side effects |
| “Having `limit(5)` guarantees an infinite pipeline stops” | `filter` before `limit` may let no elements through | Consider limit placement and reachability conditions |
| “Having `sorted()` means it is no longer lazy” | The pipeline can still defer until the terminal operation | When running, sorted may create a buffering boundary |
| “`parallel()` preserves callback print order” | Workers execute in a non-deterministic order | Distinguish result order from callback order |
| “Multiple terminal operations can be called on the same stream” | A stream is a single-use flow | Create a new pipeline or aggregate multiple results in one pass |
| “Only Stream can do a single loop” | Manual loops can also fuse operations | Choose based on clarity, requirements, and measurement |
| “`peek()` is suitable for mandatory auditing” | It can be skipped or stopped early | Separate mandatory side effects from intermediate operations |
| “`flatMap` is always one-to-one” | One element can emit 0..n results | Count based on actual sub-source elements |

## 15. Checklist for Reading and Optimizing a Stream Pipeline

1. **What is the source?** Collection, array, file, infinite source, or primitive range?
2. **Where is the terminal operation?** Without a terminal operation, most intermediate pipelines are not consumed yet.
3. **Which steps are stateless?** `map` and `filter` are usually favorable for per-element processing.
4. **Which steps are stateful?** `sorted`, `distinct`, `limit` have different state requirements.
5. **Which steps can stop early?** `findFirst`, `anyMatch`, `limit` can reduce the number of elements to process.
6. **Does operation order change the result?** `limit` before/after `filter`, `sorted` before/after `limit` are generally not freely interchangeable.
7. **Do callbacks have side effects, read mutable state, or modify the source?** Try to use stateless, non-interfering functions.
8. **Is encounter order needed?** Check the source and terminal operation when using parallelism.
9. **Are there large intermediate structures/memory?** `sorted`/`distinct`/`groupingBy`/`toList` can hold a lot of data.
10. **Is a consumed stream being reused?** A terminal operation ends the usable lifecycle of that stream.
11. **Can primitive streams be used to avoid boxing?** Consider `mapToInt`, `IntStream` when appropriate.
12. **Are there resources to close?** Streams from `Files.lines` need try-with-resources; laziness does not automatically close the file for you.

When evaluating performance, measure a pipeline **with the same result**, avoiding comparisons against a loop that has different behavior, null policy, or stopping boundaries.

## 16. Self-Check Questions

**Question 1.** With `filter` followed by `map` on a sequential Stream, is Java forced to create an intermediate List between the two steps?

**Question 2.** In `PipelineFusionDemo`, why is `filter:5` not seen?

**Question 3.** Why can `sorted` cause all upstream log lines to appear before downstream log lines?

**Question 4.** Does `Stream.toList()` mean no collection is allocated at all?

**Question 5.** Is `Stream.of("a","b").map(x -> sideEffect(x)).count()` guaranteed to call `sideEffect` twice?

**Question 6.** Does running in parallel change the logical meaning of pure `map`/`filter` on an ordered source? Is the callback order fixed?

**Question 7.** Why does `Stream.generate(() -> 1).filter(n -> n > 1).limit(3).toList()` never complete?

**Question 8.** Is it safe to use `peek` for mandatory audit logging?

**Question 9.** If you want both sum and count from the same expensive source, should you run two independent pipelines or consider a combined collector?

**Question 10.** Does `flatMap` always produce one new element for each source element?

**Short answers:**

1. No. Stateless steps can be combined, processing element-by-element sequentially.
2. `limit(2)` had enough with two results after processing `2` and `4`, so the pipeline stopped before `5`.
3. `sorted` needs to know the elements to sort before emitting results in the right order, so it usually buffers.
4. No, `toList` still has to create/hold an appropriate final result.
5. No; `count` can rely on the source's size and skip the mapper.
6. With pure callbacks, result semantics still follow the contract; callback execution order is not fixed.
7. `filter` never lets any element pass, so `limit` after it never reaches three elements.
8. No; intermediate callbacks can be skipped or stopped early.
9. You can consider a properly contracted combined collector/accumulator to avoid re-consuming the source.
10. No. `flatMap` can produce 0, 1, or many result elements from each source element.

## 17. Official References

- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): intermediate/terminal operations, laziness, short-circuiting, stateless/stateful behaviors, and optimizations.
- [Java SE 17 API — Stream.count](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()): explains the ability to deduce the element count without executing certain intermediate operations.
- [Java SE 17 — java.util.stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): pipeline execution, behavioral parameters, non-interference, statelessness, and parallelism.
- [Java SE 17 API — Stream.sorted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#sorted()): stateful intermediate operation with ordering constraints.
- [Java SE 17 API — Stream.limit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#limit(long)): short-circuiting stateful intermediate operation and notes on ordered parallel streams.

**Remember:** In Java Stream, steps like `filter` and `map` **can be combined** so elements pass through multiple steps **within the same traversal**, without creating an intermediate list after each step. However, `sorted`/`distinct` can hold state, short-circuiting can stop early, and optimizations like `count` can skip some callbacks altogether. Trust the **result contract** of the Stream API, not the order or invocation count of side effects in intermediate operations.