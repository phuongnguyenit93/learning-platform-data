# Distinguishing `filter` from `takeWhile` and `dropWhile`

In the Java Stream API, `filter`, `takeWhile`, and `dropWhile` all accept a `Predicate` condition, yet **they do not answer the same question**. `filter` selects matching elements across the **entire source**; `takeWhile` takes the **contiguous leading segment** while the condition holds; `dropWhile` **discards the contiguous leading segment** while the condition holds and keeps the rest. The difference is especially important when data is ordered, when an out-of-range value appears mid-stream, and when processing parallel Streams.

This lesson belongs to the **Ordering, Deduplication, and Slicing** chapter of the **JAVA_STREAM_API** module. Through Java 17+ examples, you will learn *encounter order*, preconditions for boundary-based slicing, laziness and short-circuiting, pitfalls with unordered Streams, how to combine `sorted`, `limit`, and `skip`, as well as limits regarding state, resources, and performance in `filter → map → collect` pipelines.

## 1. One Example, Three Different Results

Consider an ordered sequence:

```text
[1, 3, 7, 2, 9]
```

The condition is `n < 5`. The number `2` satisfies the condition, yet it **comes after** the non-matching element `7`.

```java
import java.util.List;

public class WhileVsFilterBasics {
    public static void main(String[] args) {
        List<Integer> values = List.of(1, 3, 7, 2, 9);

        System.out.println(values.stream()
            .filter(n -> n < 5)
            .toList()); // [1, 3, 2]

        System.out.println(values.stream()
            .takeWhile(n -> n < 5)
            .toList()); // [1, 3]

        System.out.println(values.stream()
            .dropWhile(n -> n < 5)
            .toList()); // [7, 2, 9]
    }
}
```

With the exact same predicate, the three operations produce three distinct result sets:

| Operation | Rule on an ordered Stream | Example result |
| --- | --- | --- |
| `filter(n -> n < 5)` | Keeps **every** element matching the condition | `[1, 3, 2]` |
| `takeWhile(n -> n < 5)` | Keeps the **longest contiguous prefix** matching the condition; stops at the first non-matching element | `[1, 3]` |
| `dropWhile(n -> n < 5)` | Discards the **longest contiguous prefix** matching the condition; keeps the first non-matching element **and everything after it** | `[7, 2, 9]` |

Visualizing the cuts:

```text
Data:          [ 1, 3 | 7, 2, 9 ]
                        ^
                    7 does not satisfy n < 5
filter:        [ 1, 3,    2    ]   (selects every matching element)
takeWhile:     [ 1, 3 ]            (takes the leading segment)
dropWhile:             [ 7, 2, 9 ] (drops the leading segment)
```

**Remember right away:** `dropWhile` **is not** `filter(predicate.negate())`. In the `dropWhile` result above, `2` still appears even though it satisfies the predicate, because it occurs after the cut point.

## 2. Exact Meaning of "Prefix" and Encounter Order

A *prefix* is a contiguous segment of elements starting at the **beginning of the encounter order** of the source. An ordered Stream makes it possible to identify which element is first, second, third, and so on.

Example with a `List`:

```java
List<String> states = List.of(
    "PENDING", "PENDING", "DONE", "PENDING"
);
```

- `takeWhile("PENDING"::equals)` returns `[PENDING, PENDING]`.
- `dropWhile("PENDING"::equals)` returns `[DONE, PENDING]`.
- `filter("PENDING"::equals)` returns `[PENDING, PENDING, PENDING]`.

Sources that normally have an encounter order include `List.stream()`, `Arrays.stream(...)`, and `IntStream.range(...)`. Conversely, a typical `HashSet` source **has no guaranteed encounter order**. That difference directly affects the meaning of `takeWhile` and `dropWhile`.

### 2.1. Three Index-Based Descriptions

Suppose an ordered source has elements `x0, x1, ..., x(n-1)` and condition `p(x)`.

- `filter(p)` returns all `xi` for which `p(xi)` is true, preserving the relative order of the retained elements.
- `takeWhile(p)` finds the first index `k` where `p(xk)` is false, then returns `x0, ..., x(k-1)`. If no element fails, it returns the entire source.
- `dropWhile(p)` finds the same index `k` and returns `xk, ..., x(n-1)`. If no element fails, it returns an empty Stream.

The cut index `k` may be 0 (the first element fails) or `n` (every element passes). For a finite, ordered Stream, the two segments produced by `takeWhile(p)` and `dropWhile(p)` are **non-overlapping** and concatenating them in order reconstructs the original source.

**Note:** Those two expressions must run on **two separate fresh Streams**, because a Stream consumed by a terminal operation cannot be reused. To split a source into two branches in a single pass, use a different algorithm, such as buffering or an appropriate stream-splitting mechanism.

## 3. `filter`: Filtering at Every Position in the Source

`filter` is a **stateless intermediate operation**. It retains an element whenever `Predicate.test(element)` returns `true`, regardless of whether earlier elements matched.

```java
import java.util.List;

List<Integer> scores = List.of(40, 90, 20, 80, 50);

List<Integer> passed = scores.stream()
    .filter(score -> score >= 50)
    .toList();

System.out.println(passed); // [90, 80, 50]
```

The score data does not need to be sorted. Passing scores can appear at any position.

### When Is `filter` the Right Choice?

- Finding **all** paid orders in a list.
- Keeping every log line at `ERROR` level, even when interleaved with other lines.
- Selecting products belonging to a category, regardless of where they appear.
- Processing unordered data where the condition applies independently to each element.

With a terminal operation requiring the full result like `toList()`, `filter` generally inspects elements across the source to pick all matching ones; however, do not treat this as a guarantee that a side-effecting predicate runs **exactly once in every pipeline**. Streams may optimize stages when result semantics remain unchanged.

### `filter` Does Not Cut at the First Threshold Violation

```java
List<Integer> readings = List.of(1, 2, 10, 3, 4);

System.out.println(readings.stream()
    .filter(n -> n < 5)
    .toList()); // [1, 2, 3, 4]
```

If business logic requires **stopping data at the first threshold violation**, `[1, 2, 3, 4]` is wrong because it keeps `3` and `4` after the violation. On an ordered source, `takeWhile` is the right operation.

## 4. `takeWhile`: Taking a Contiguous Matching Prefix

`takeWhile` was introduced in **Java 9** for `Stream` and primitive Streams. On an ordered Stream, it returns the **longest prefix** in which every element satisfies the predicate.

```java
List<Integer> temperatures = List.of(28, 29, 30, 36, 29, 28);

List<Integer> beforeFirstHotReading = temperatures.stream()
    .takeWhile(temp -> temp < 35)
    .toList();

System.out.println(beforeFirstHotReading); // [28, 29, 30]
```

After encountering `36`, the trailing values `29` and `28` **do not appear** in the result, even though they are also below 35.

### 4.1. Why Can `takeWhile` Short-Circuit?

On an ordered source, as soon as the first non-matching element is found, no later element can belong to the valid prefix. Thus `takeWhile` is a **stateful** and **short-circuiting** intermediate operation.

```text
Source:     A(true) → B(true) → C(false) → D(true) → E(true)
takeWhile:  A       → B       → STOP
Result:     [A, B]
```

Semantically, `D` and `E` do not need to be forwarded downstream. Nonetheless, in parallel execution or other optimizations, **do not rely on the call count or evaluation order of the predicate** to perform side effects.

### 4.2. Edge Cases

```java
import java.util.List;

List<Integer> numbers = List.of(2, 4, 6);

System.out.println(numbers.stream()
    .takeWhile(n -> n % 2 == 0)
    .toList()); // [2, 4, 6] — all elements match

System.out.println(numbers.stream()
    .takeWhile(n -> n < 0)
    .toList()); // [] — first element already fails

System.out.println(List.<Integer>of().stream()
    .takeWhile(n -> n > 0)
    .toList()); // [] — empty source
```

If no element fails the condition, `takeWhile` takes the entire Stream. If the first element fails, the result is empty.

## 5. `dropWhile`: Dropping a Prefix, Not Removing Every Match

`dropWhile` also arrived in Java 9. On an ordered Stream, it skips the **longest prefix** matching the condition and passes **everything remaining** downstream.

```java
List<String> lines = List.of(
    "# header", "# source", "name,amount", "# data", "A,100"
);

List<String> afterHeader = lines.stream()
    .dropWhile(line -> line.startsWith("#"))
    .toList();

System.out.println(afterHeader);
// [name,amount, # data, A,100]
```

This example drops **leading comment lines at the start of a file**. The line `"# data"` after `"name,amount"` is kept. Replacing it with `filter(line -> !line.startsWith("#"))` would remove `"# header"`, `"# source"`, and `"# data"` alike—a completely different meaning.

### 5.1. The First Non-Matching Element **Is Retained**

```java
List<Integer> values = List.of(1, 2, 5, 3, 4);

System.out.println(values.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [5, 3, 4]
```

The value `5` is the **boundary-defining element**. It fails `n < 5`, so `dropWhile` retains it. If business logic requires **dropping the boundary element too**, express the additional rule explicitly and test edge cases instead of assuming `dropWhile` does it automatically.

### 5.2. Past the Cut Point, Remaining Elements Are Not Filtered by the Predicate

```java
List<Integer> values = List.of(1, 2, 7, 3, 9);

System.out.println(values.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [7, 3, 9]
```

The number `3` is still kept. `dropWhile` is not a negated `filter`; it merely selects the **starting point of the suffix**.

### 5.3. Edge Cases

```java
List<Integer> values = List.of(2, 4, 6);

System.out.println(values.stream()
    .dropWhile(n -> n % 2 == 0)
    .toList()); // [] — all elements dropped

System.out.println(values.stream()
    .dropWhile(n -> n < 0)
    .toList()); // [2, 4, 6] — first element already fails

System.out.println(List.<Integer>of().stream()
    .dropWhile(n -> n > 0)
    .toList()); // [] — empty source
```

Unlike `takeWhile`, `dropWhile` must continue forwarding suffix elements downstream if the terminal operation asks for them. Hence **`dropWhile` is not classified as a short-circuiting operation** like `takeWhile`, even though it stops testing the predicate once the cut point is found.

## 6. Comparison Table for Common Scenarios

Given an ordered source and predicate `p`:

| Input data | `filter(p)` | `takeWhile(p)` | `dropWhile(p)` |
| --- | --- | --- | --- |
| `[]` | `[]` | `[]` | `[]` |
| Every element satisfies `p` | All elements | All elements | `[]` |
| No element satisfies `p` | `[]` | `[]` | All elements |
| Matching prefix then a non-matching element | Keeps every match, including later ones | Keeps only the prefix | Keeps from the non-matching element onward |
| First element fails, later elements match | Keeps later matches | `[]` | All elements |

Concrete examples with predicate `n < 5`:

| Source | `filter` | `takeWhile` | `dropWhile` |
| --- | --- | --- | --- |
| `[1, 2, 3]` | `[1, 2, 3]` | `[1, 2, 3]` | `[]` |
| `[5, 1, 2]` | `[1, 2]` | `[]` | `[5, 1, 2]` |
| `[1, 2, 5]` | `[1, 2]` | `[1, 2]` | `[5]` |
| `[1, 5, 2]` | `[1, 2]` | `[1]` | `[5, 2]` |
| `[8, 9]` | `[]` | `[]` | `[8, 9]` |

These two tables make it quick to spot common misuses: `takeWhile` **takes no further** matching elements after the first failure, while `dropWhile` **removes no further** matching elements after that point.

## 7. When Does `takeWhile` Match `filter`? Monotonic Conditions Under Order

In some sources, elements are arranged so that every element matching the predicate precedes every non-matching element. Then, on an ordered Stream, `filter(p)` and `takeWhile(p)` return the exact same list of elements.

Example of an ascending score sequence:

```java
List<Integer> sortedScores = List.of(10, 20, 30, 60, 90);

System.out.println(sortedScores.stream()
    .filter(score -> score < 50)
    .toList()); // [10, 20, 30]

System.out.println(sortedScores.stream()
    .takeWhile(score -> score < 50)
    .toList()); // [10, 20, 30]
```

Here, the predicate `score < 50` has the **prefix property** over ascending order: once a value not less than 50 appears, no later value can be less than 50.

Yet simply changing source order breaks that equivalence:

```java
List<Integer> unsorted = List.of(10, 60, 20, 90);

System.out.println(unsorted.stream()
    .filter(score -> score < 50)
    .toList()); // [10, 20]

System.out.println(unsorted.stream()
    .takeWhile(score -> score < 50)
    .toList()); // [10]
```

### 7.1. `sorted` Can Establish an Appropriate Order — But Not for Free

```java
List<Integer> source = List.of(30, 70, 10, 20, 90);

List<Integer> lowScores = source.stream()
    .sorted()
    .takeWhile(score -> score < 50)
    .toList();

System.out.println(lowScores); // [10, 20, 30]
```

`sorted()` changes the encounter order to match the sort criterion. It is a **stateful** intermediate operation: on a finite source without known order, it generally must organize data for sorting before emitting the first output element. Therefore, do not assume adding `sorted` followed by `takeWhile` will be faster than a plain `filter`.

Ask: does business logic require **preserving original order** or **taking by threshold after sorting**? Changing order can change the meaning of a report.

### 7.2. `dropWhile` and Threshold Conditions

If a source is sorted ascending and `p(n) = n < 50`, `dropWhile(p)` returns the first element `>= 50` and everything after it:

```java
List<Integer> highScores = sortedScores.stream()
    .dropWhile(score -> score < 50)
    .toList();

System.out.println(highScores); // [60, 90]
```

When ascending order is **guaranteed** and the predicate is a threshold check, the result matches `filter(score -> score >= 50)`. Do not rely on this equivalence for unsorted data or predicates that are not monotonic with respect to encounter order.

## 8. Unordered Streams: `takeWhile` and `dropWhile` Lose a Deterministic Boundary

This is the biggest trap when switching from a `List` to a `HashSet` or calling `unordered()` in a pipeline.

On an **unordered Stream**:

- `filter(p)` still means "select elements satisfying `p`", just with **no guaranteed return order**.
- `takeWhile(p)` may return **any subset of elements satisfying `p`** if any match, not necessarily all of them; it may return an empty set.
- `dropWhile(p)` may **drop any subset** of elements satisfying `p`; non-matching elements must be kept, yet some matching elements may also be retained.

There is no longer a "longest prefix" in any business sense, because the source promises no such ordering.

```java
import java.util.List;

List<Integer> input = List.of(1, 2, 3, 8, 9);

// Intentionally drop the pipeline's encounter-order guarantee.
List<Integer> taken = input.parallelStream()
    .unordered()
    .takeWhile(n -> n < 5)
    .toList();

List<Integer> dropped = input.parallelStream()
    .unordered()
    .dropWhile(n -> n < 5)
    .toList();

System.out.println(taken);
System.out.println(dropped);
// Do not write a fixed expected output for these two results.
```

In the snippet above, `taken` contains only values from `{1, 2, 3}`, with no guarantee that all three are present. `dropped` must contain `8` and `9`, yet may also retain some values from `{1, 2, 3}`.

### 8.1. `unordered()` Is Not `shuffle()`

`unordered()` **removes the ordering constraint** to allow optimizations; it **does not request shuffling** data. On some runs the output may look identical to sequential execution, but that does not turn the observed output into a stable contract.

### 8.2. Choosing Operations Based on Requirements

If the goal is the **set of all elements matching a condition**, use `filter`. If the goal is **cutting at the first point in order**, ensure a proper encounter order and use `takeWhile` or `dropWhile`. Never use `unordered()` to chase speed without accepting the semantic change.

For a `HashSet` source, `takeWhile`/`dropWhile` rarely express a reliable business cut point. If a cut point is truly needed, first **define an order** via an appropriate source or deliberate sorting.

## 9. Parallelism: Semantic Correctness Matters More Than Speed

`takeWhile` and `dropWhile` are **stateful**. Especially on an **ordered parallel Stream**, identifying the prefix boundary in encounter order can require substantial coordination between tasks.

Example:

```java
import java.util.stream.IntStream;

long count = IntStream.range(0, 1_000_000)
    .parallel()
    .takeWhile(n -> n < 100_000)
    .count();

System.out.println(count); // 100000
```

For an ordered `IntStream.range` with a threshold predicate, the logical result remains exact. Even so, never infer from `parallel()` alone that the pipeline will execute faster than its sequential counterpart.

Factors governing performance include:

- Source size and the splitting quality of `Spliterator.trySplit()`.
- Position of the cut point and fraction of leading elements traversed.
- Cost of evaluating the predicate, `map`, and downstream collector.
- Coordination overhead to preserve encounter order during parallel execution.
- Other stateful operations such as `sorted`, `distinct`, and intermediate buffering.
- Resource contention, memory usage, and GC pressure.

For requirements that do not need a prefix boundary, `filter` is usually more direct and splits work independently per element.

### 9.1. Dropping Order Does Not Keep the Same Result While Optimizing

```java
IntStream.range(0, 1_000_000)
    .parallel()
    .unordered()
    .takeWhile(n -> n < 100_000)
    .count();
```

You cannot predict with certainty that the result will be 100,000, because `takeWhile` on an unordered Stream only promises an arbitrary permitted subset of matching elements.

If the result **must** be 100,000, keep encounter order or choose another operation matching the question. Drop the ordering constraint only when business logic truly does not need it and non-deterministic slicing is acceptable.

### 9.2. How to Evaluate Performance

If your goal is improving speed, measure with representative data and a benchmarking tool such as JMH. Compare sequential and parallel versions using **the same input, the same required ordering, and the same correctness criteria**—never trade away business requirements for faster numbers.

## 10. Combining with `limit`, `skip`, and Pipeline Ordering

`limit(n)` and `skip(n)` slice by **element count**, not by predicate:

- `limit(n)`: keeps at most the first `n` elements.
- `skip(n)`: discards the first `n` elements.

`takeWhile` and `dropWhile` slice by **content up to the first boundary** on an ordered Stream.

```java
import java.util.List;

List<Integer> data = List.of(1, 2, 6, 3, 4);

System.out.println(data.stream()
    .limit(3)
    .toList()); // [1, 2, 6]

System.out.println(data.stream()
    .skip(2)
    .toList()); // [6, 3, 4]

System.out.println(data.stream()
    .takeWhile(n -> n < 5)
    .toList()); // [1, 2]

System.out.println(data.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [6, 3, 4]
```

### 10.1. Reordering Operations Can Change Results

The order of `filter` and `takeWhile` cannot be swapped arbitrarily. Look at an example that produces genuinely different results:

```java
List<Integer> input = List.of(1, 7, 2, 3, 8);

List<Integer> filterThenTake = input.stream()
    .filter(n -> n % 2 == 0) // [2, 8]
    .takeWhile(n -> n < 5)  // takes [2], stops at 8
    .toList();

List<Integer> takeThenFilter = input.stream()
    .takeWhile(n -> n < 5)  // takes [1], stops at 7
    .filter(n -> n % 2 == 0)
    .toList();             // []

System.out.println(filterThenTake); // [2]
System.out.println(takeThenFilter); // []
```

**Core reason:** `filter` can remove elements that would otherwise act as `takeWhile`'s cut point. Thus step ordering determines which boundary is observed.

### 10.2. `dropWhile` Followed by `limit`

A common pattern is dropping older records at the head of a chronologically sorted sequence and then taking a few newer records:

```java
List<Integer> sorted = List.of(10, 20, 30, 40, 50, 60);

System.out.println(sorted.stream()
    .dropWhile(n -> n < 35)
    .limit(2)
    .toList()); // [40, 50]
```

This combines **two kinds of constraints**: a threshold value selects the start position, and a count limits the output length.

### 10.3. `sorted` and `distinct` Also Change the Input Observed by Slicing

`sorted` changes encounter order. `distinct` removes duplicate elements, changing both count and relative positions of remaining elements. Therefore the pipeline:

```java
stream.distinct().takeWhile(predicate)
```

can yield a different result from:

```java
stream.takeWhile(predicate).distinct()
```

Do not apply algebraic rewrites mechanically between operations; specify clearly the **order and scope** the predicate should observe.

## 11. Infinite Streams: Can They Terminate?

With an infinite source, early stopping is a very practical distinction.

### 11.1. `takeWhile` Can Turn an Infinite Source into a Finite Result

```java
import java.util.stream.IntStream;

List<Integer> firstFive = IntStream.iterate(1, n -> n + 1)
    .takeWhile(n -> n <= 5)
    .boxed()
    .toList();

System.out.println(firstFive); // [1, 2, 3, 4, 5]
```

`IntStream.iterate(1, n -> n + 1)` generates an unbounded sequence by definition. Yet on this ordered source, `takeWhile(n -> n <= 5)` stops upon hitting `6`, allowing `toList()` to terminate.

If the predicate is **never false**, `takeWhile` cannot create a stop point either; a terminal operation needing the whole result may never terminate.

### 11.2. `dropWhile` Only Drops a Prefix; It Does Not Make the Suffix Finite

```java
List<Integer> afterFive = IntStream.iterate(1, n -> n + 1)
    .dropWhile(n -> n <= 5)
    .limit(3)
    .boxed()
    .toList();

System.out.println(afterFive); // [6, 7, 8]
```

`dropWhile` reaches `6`, then **retains an infinite suffix**. `limit(3)` is what forces the final output to be finite. Calling `toList()` right after `dropWhile` on an infinite suffix can run forever or exhaust resources.

### 11.3. `filter` Does Not Mean "Stop on First Failure"

```java
List<Integer> firstOdds = IntStream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 != 0)
    .limit(3)
    .boxed()
    .toList();

System.out.println(firstOdds); // [1, 3, 5]
```

`filter` searches for matching elements at any position. If the predicate is never true, `filter(p).findFirst()` on an infinite source can wait forever because no valid element is ever found.

**Note:** On infinite Streams, only use terminal operations with a clear termination path; applying `sorted()` to an entire infinite source is generally unsuitable because it must order the entire source before emitting results.

## 12. Primitive Streams: Same Semantics on `IntStream`, `LongStream`, and `DoubleStream`

All three operations—`filter`, `takeWhile`, and `dropWhile`—exist on:

- `Stream<T>`: takes `Predicate<? super T>`.
- `IntStream`: takes `IntPredicate`.
- `LongStream`: takes `LongPredicate`.
- `DoubleStream`: takes `DoublePredicate`.

Example with `IntStream`:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] values = {2, 4, 7, 8, 10};

int[] even = IntStream.of(values)
    .filter(n -> n % 2 == 0)
    .toArray();

int[] initialEven = IntStream.of(values)
    .takeWhile(n -> n % 2 == 0)
    .toArray();

int[] afterInitialEven = IntStream.of(values)
    .dropWhile(n -> n % 2 == 0)
    .toArray();

System.out.println(Arrays.toString(even));             // [2, 4, 8, 10]
System.out.println(Arrays.toString(initialEven));      // [2, 4]
System.out.println(Arrays.toString(afterInitialEven)); // [7, 8, 10]
```

Examples with `LongStream` and `DoubleStream`:

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;
import java.util.stream.LongStream;

long[] recentIds = LongStream.of(10L, 20L, 30L, 5L)
    .takeWhile(id -> id < 25L)
    .toArray();

double[] remaining = DoubleStream.of(0.1, 0.3, 0.9, 0.2)
    .dropWhile(value -> value < 0.5)
    .toArray();

System.out.println(Arrays.toString(recentIds)); // [10, 20]
System.out.println(Arrays.toString(remaining)); // [0.9, 0.2]
```

Primitive Streams avoid boxing during numeric processing. However, primitive types **do not change** prefix semantics, encounter order, or parallel processing constraints.

## 13. Complete Example: Analyzing Events by Timestamp Cutoff

A system receives events with timestamps. A user wants events **before** a timestamp cutoff and **from that cutoff onward**.

There are two distinct questions:

1. "Find all older events before the cutoff, **regardless of position**." → `filter`.
2. "Given events already sorted in ascending chronological order, **split the list at the cutoff**." → `takeWhile` and `dropWhile`.

The self-contained Java 17+ example below clearly demonstrates the risk when input is unsorted.

```java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;

public class TimeBoundaryDemo {

    record Event(String id, Instant occurredAt, long amountVnd) {}

    public static void main(String[] args) {
        Instant cutoff = Instant.parse("2026-11-18T10:02:00Z");

        // Arrival order: E-03 arrives late in source position,
        // while E-02 occurred earlier yet appears after E-03.
        List<Event> events = List.of(
            new Event("E-01", Instant.parse("2026-11-18T10:00:00Z"), 100L),
            new Event("E-03", Instant.parse("2026-11-18T10:03:00Z"), 300L),
            new Event("E-02", Instant.parse("2026-11-18T10:01:00Z"), 200L),
            new Event("E-04", Instant.parse("2026-11-18T10:05:00Z"), 400L)
        );

        List<String> allEarlier = events.stream()
            .filter(e -> e.occurredAt().isBefore(cutoff))
            .map(Event::id)
            .toList();

        List<String> wronglyCutUnsorted = events.stream()
            .takeWhile(e -> e.occurredAt().isBefore(cutoff))
            .map(Event::id)
            .toList();

        List<Event> sorted = events.stream()
            .sorted(Comparator.comparing(Event::occurredAt))
            .toList();

        List<String> beforeBoundary = sorted.stream()
            .takeWhile(e -> e.occurredAt().isBefore(cutoff))
            .map(Event::id)
            .toList();

        List<String> fromBoundary = sorted.stream()
            .dropWhile(e -> e.occurredAt().isBefore(cutoff))
            .map(Event::id)
            .toList();

        System.out.println(allEarlier);       // [E-01, E-02]
        System.out.println(wronglyCutUnsorted);// [E-01]
        System.out.println(beforeBoundary);   // [E-01, E-02]
        System.out.println(fromBoundary);     // [E-03, E-04]
    }
}
```

### Result Analysis

- In the original data, `E-02` appears after `E-03`, even though `E-02`'s timestamp is earlier.
- `filter` finds **all events earlier than cutoff**, returning `E-01` and `E-02`.
- `takeWhile` on the unsorted source hits `E-03` (which fails) and cuts there; `E-02` is missed.
- `sorted(Comparator.comparing(Event::occurredAt))` establishes an order suitable for timestamp slicing.
- On the sorted source, `takeWhile` takes events before cutoff, while `dropWhile` retains events **from cutoff onward**.

Sorting has time and memory costs. If the source is already guaranteed by the system to be ascending by timestamp, calling `sorted` is unnecessary. Conversely, if timestamps can arrive out of order and the requirement is simply "all events before the cutoff", `filter` is more direct and avoids reordering the source.

### 13.1. Which Group Does an Event Exactly at the Cutoff Belong To?

`Instant.isBefore(cutoff)` returns `false` when a timestamp **equals** `cutoff`, so an event right on the boundary will:

- **Not** be in `takeWhile(isBefore)` on a sorted source.
- **Be** in `dropWhile(isBefore)`, as it is the first element that no longer satisfies `isBefore`.

If business rules define the boundary as "before or equal", change the predicate explicitly, e.g., `!event.occurredAt().isAfter(cutoff)`. Your choice of condition decides **boundary inclusion or exclusion**, not the names `takeWhile`/`dropWhile` themselves.

## 14. Lazy Pipelines, Side Effects, and Resource-Backed Streams

All three methods are **intermediate operations** and do not start traversal when constructing the pipeline:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = List.of(1, 2, 5, 3);

Stream<Integer> pending = values.stream()
    .takeWhile(n -> n < 5)
    .map(n -> n * 10); // Pipeline has not executed yet.

System.out.println(pending.toList()); // [10, 20]
```

`toList()` is the terminal operation that triggers execution. Afterward, you cannot call `pending.count()`.

### 14.1. Avoid State-Dependent Predicates

A common temptation is simulating `takeWhile` via `filter` with a flag variable:

```java
// Discouraged: stateful predicate and side effect.
boolean[] keep = {true};

List<Integer> result = values.parallelStream()
    .filter(n -> {
        if (n >= 5) {
            keep[0] = false;
        }
        return keep[0];
    })
    .toList();
```

This is not thread-safe in parallel execution, and even sequentially it obscures intent and restricts optimizations. Use `takeWhile(n -> n < 5)` on an ordered Stream when business logic requires stopping at the first invalid element.

Behavioral functions should be **stateless** and **non-interfering**: do not mutate the traversed source and do not rely on external state whose result depends on execution scheduling.

### 14.2. `peek` Is Not an Exact Traversal Counter

`peek` and side effects in predicates must not be used as business evidence to conclude how many elements were read. Short-circuiting operations, size-based optimizations, and parallel execution can alter stage invocation counts. If you need a count, apply a terminal operation like `count()` over the selected slice.

### 14.3. I/O-Backed Streams Must Still Be Closed

For example, `Files.lines(path)` returns a file-backed Stream that must be closed. `takeWhile` may stop traversing early, yet **it does not close the file resource automatically** when the terminal operation finishes:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public static List<String> firstCommentBlock(Path file)
        throws IOException {
    try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
        return lines
            .takeWhile(line -> line.startsWith("#"))
            .toList();
    }
}
```

This method reads the **contiguous comment block at the top of a file**, not every comment line. `try-with-resources` ensures the resource is closed even when the pipeline stops early or throws an error. If a caller receives a Stream from another API, closing responsibility must follow that API's ownership contract.

## 15. Choosing the Right Operation for Business Requirements

| Requirement | Preferred operation | Reason |
| --- | --- | --- |
| Keep all paid transactions, possibly interleaved | `filter(Order::paid)` | Condition applies independently to every element |
| Read a contiguous header block at the top of a file | `takeWhile(isHeader)` | Stops at the first non-header line |
| Drop the header block and process the remaining content | `dropWhile(isHeader)` | Removes only the leading header |
| On an ascending timestamp sequence, get elements before cutoff | `takeWhile(beforeCutoff)` | Cuts at the first timestamp boundary |
| On an ascending timestamp sequence, get elements from cutoff onward | `dropWhile(beforeCutoff)` | Keeps the suffix starting at the boundary |
| On unsorted timestamps, find every record before cutoff | `filter(beforeCutoff)` | Does not miss older records arriving late |
| Drop exactly the first 10 elements, regardless of value | `skip(10)` | Slices by count |
| Take at most the first 10 elements | `limit(10)` | Slices by count |
| Select every matching element on an unordered source | `filter(predicate)` | Needs no encounter-order boundary |

A quick self-check: **"Do I want to test every element independently, or stop/start at the first ordered boundary?"** The answer usually decides between `filter` and the `while` operations.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `takeWhile(p)` like `filter(p)` on interleaved data | Misses matching elements after the first failure | Use `filter` if all matches are needed |
| Using `dropWhile(p)` like `filter(p.negate())` | Retains matching elements in the suffix | Use `filter(p.negate())` if **all** matches should be removed |
| Thinking `dropWhile` also drops the first non-matching element | Misunderstands the boundary | Remember the first non-matching element **is retained** |
| Using `takeWhile` to slice by timestamp on unsorted data | Misses older events appearing late | Use `filter` or establish proper order |
| Calling `unordered()` before `takeWhile` while still expecting the full prefix | Loses deterministic boundary; results may be incomplete | Keep encounter order when slicing by position |
| Assuming `HashSet.stream()` has reliable ordering | `while` results are undefined relative to business order | Switch to an ordered source or sort |
| Assuming `parallel().takeWhile` is always fast | Ordered parallel execution can incur costly coordination | Benchmark on realistic workloads |
| Using `takeWhile` on an infinite source with an always-true predicate and `toList()` | Never terminates | Provide a stopping condition or cap |
| Using `dropWhile` on an infinite source and `toList()` | Suffix remains infinite | Combine with `limit` or use another finite approach |
| Confusing `limit(10)` with `takeWhile(n -> n < 10)` | One is count-based, the other is value-based | Choose by boundary definition |
| Writing a `boolean[]`-flagged predicate inside `filter` | Stateful, races under parallel execution | Use `takeWhile`/`dropWhile` on an ordered Stream |
| Relying on `Predicate`/`peek` invocation counts for business logic | Unreliable under optimizations or parallelism | Use official terminal operation results |
| Forgetting to close a `Files.lines` Stream when using `takeWhile` | Resource leak | `try-with-resources` |
| Reusing a Stream after `toList` or `count` | Stream is already consumed | Open a fresh Stream from the source if another calculation is needed |

## 17. Practice Exercises

### Exercise 1: Predict Three Results

Given `List<Integer> values = List.of(2, 4, 7, 6, 8)`, predict the results of `filter(n -> n % 2 == 0)`, `takeWhile(n -> n % 2 == 0)`, and `dropWhile(n -> n % 2 == 0)`. Explain why `6` and `8` appear only in certain results.

### Exercise 2: File Header Block

Given lines `["# generated", "# owner", "id,value", "# note", "1,100"]`. Use `takeWhile` to extract the header, `dropWhile` to skip the header, and `filter` to strip **all** comment lines. Compare the three results.

### Exercise 3: Threshold Slicing

Given `[10, 30, 50, 20, 70]` and predicate `n < 40`. Compute the results of both `while` operations and `filter`; then insert `sorted()` before each and explain what changes. When is sorting valid for business requirements?

### Exercise 4: Pipeline Order

Look at `List.of(1, 7, 2, 3, 8)`. Compare `filter(even).takeWhile(n < 5)` and `takeWhile(n < 5).filter(even)`. Why does swapping the two operations produce different results?

### Exercise 5: Unordered Streams

Write `IntStream.range(0, 1000).parallel().unordered().takeWhile(n -> n < 100)`. Can you assert the result always contains all 100 numbers from 0 to 99? If the requirement is **all numbers less than 100**, which operation should you use?

### Exercise 6: Infinite Sources

Use `IntStream.iterate(1, n -> n + 1)` to produce `[1, 2, 3, 4, 5]` with `takeWhile`; then produce `[6, 7, 8]` with `dropWhile` and `limit`. Explain why `dropWhile` does not make the suffix finite on its own.

### Exercise 7: Out-of-Order Events

A system receives logs chronologically over a network; an event created at 10:01 may arrive after a 10:03 event. Design a pipeline to find **all events before 10:02**. Why would running `takeWhile` directly on arrival order be wrong?

### Exercise 8: Parallel Evaluation

Compare sequential and parallel pipelines on `IntStream.range(0, 1_000_000)` with `takeWhile(n -> n < 100_000)`. Describe the benchmarking factors to consider before choosing `parallel()`. Do not use side effects inside the predicate to infer how many elements were actually processed.

## 18. Self-Check Questions

- Does `filter` evaluate the condition across the entire source or stop at the first non-matching element?
- What does "longest prefix" mean for `takeWhile` on an ordered Stream?
- Does `dropWhile` keep the first element that fails the predicate?
- Why is `dropWhile(p)` not equivalent to `filter(p.negate())`?
- Under what condition does `takeWhile(p)` return the exact same result as `filter(p)`?
- What changes when using `unordered()` or a source without an encounter order?
- Why can `takeWhile` help an infinite Stream terminate whereas `dropWhile` usually cannot?
- Why can `sorted` make threshold slicing accurate yet increase cost?
- How do `limit` and `skip` differ from content-based `while` operations?
- Can you rely on predicate invocation count in a parallel Stream to update a business counter?
- Why must an I/O-backed Stream still be closed even when `takeWhile` stops early?

**Key takeaway:** On an **ordered** Stream, `filter(p)` selects **every element** satisfying `p`, `takeWhile(p)` takes only the **longest contiguous prefix** satisfying `p`, and `dropWhile(p)` **drops that prefix and keeps the entire suffix**. To slice at a boundary, guarantee an encounter order matching business semantics. When you just need to filter elements at arbitrary positions—especially on unordered sources—use `filter`.
