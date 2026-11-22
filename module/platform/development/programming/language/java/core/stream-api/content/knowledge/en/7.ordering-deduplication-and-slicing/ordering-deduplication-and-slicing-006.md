# Dropping a Conditional Prefix with `dropWhile`

## 1. The Problem: Discarding the Head of a Sequence Until a State Transition

In the Java Stream API, we do not always want to **filter out every** element matching a condition. Sometimes we only want to discard a **contiguous leading section** of a sequence and keep all remaining elements intact:

- Skipping leading comment lines in a file and processing from the first data line onward.
- Discarding events with timestamps before a cutoff, provided events are already sorted chronologically.
- Skipping completed tasks at the front of a list and continuing from the first incomplete task.
- Skipping already-processed IDs in an ascending list to fetch the next page.

`dropWhile` expresses this exact operation: **discarding the longest prefix of contiguous elements satisfying a predicate** on a stream with an **encounter order**.

Visualizing the sequence:

```text
Source:      [1, 2, 4, 8, 3, 10]
Condition:   n < 5
                     ▲
               8 is the FIRST element that does NOT match

Dropped:     [1, 2, 4]
Retained:             [8, 3, 10]
```

Key point: **the number `3` is still kept** even though `3 < 5`, because it appears after `8`, which ended the dropped prefix.

Java example:

```java
import java.util.List;

List<Integer> values = List.of(1, 2, 4, 8, 3, 10);

List<Integer> result = values.stream()
    .dropWhile(n -> n < 5)
    .toList();

System.out.println(result); // [8, 3, 10]
```

This lesson belongs to the **Ordering, Deduplication, and Slicing** section of the `JAVA_STREAM_API` module. After this lesson, you should be able to:

1. Read and apply the `dropWhile` signature and the **contiguous prefix** rule accurately.
2. Distinguish `dropWhile` from `takeWhile`, `filter`, `skip`, `limit`, and `sorted`.
3. Recognize the effect of encounter order and unordered streams.
4. Use `dropWhile` in declarative pipelines combined with `map`, `reduce`, `collect`, or grouping.
5. Test critical boundary cases: empty source, all elements matching, no elements matching, condition becoming true again later.
6. Evaluate laziness, side effects, infinite sources, and parallel processing costs.

## 2. Reading the Official API Signature and Contract

On `java.util.stream.Stream<T>`, the method signature is:

```java
Stream<T> dropWhile(Predicate<? super T> predicate)
```

`dropWhile` was introduced in **Java 9**. The parts of the signature mean:

| Component | Meaning |
| --- | --- |
| Leading `Stream<T>` | Result is a stream of the same element type `T` |
| `Predicate<? super T>` | Element-testing function accepting `T` or a compatible supertype and returning `boolean` |
| `true` from predicate | Element **may be dropped** if still within the prefix being examined |
| First `false` | Ends the dropped prefix on an **ordered stream**; this element is kept |
| Return value | Stream containing the suffix after dropping the prefix, or an empty stream |

According to the Javadoc, this is a **stateful intermediate operation** as well as a **short-circuiting intermediate operation**. It must record when the first non-matching element has been seen; from that point onward, subsequent elements are kept even if the predicate would return `true` for them.

As an **intermediate operation**, `dropWhile` does not consume the stream on its own. A terminal operation such as `toList`, `findFirst`, or `count` triggers data flow through the pipeline:

```java
var pipeline = values.stream()
    .dropWhile(n -> n < 5); // Only builds the pipeline.

List<Integer> suffix = pipeline.toList(); // Triggers processing.
```

A stream should be consumed only once. If you need one result from `dropWhile` and another from `filter`, create two new streams from the source collection.

Official documentation:

- [`Stream.dropWhile` in Java 21 Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#dropWhile(java.util.function.Predicate))
- [Package `java.util.stream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html)
- [`IntStream.dropWhile`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/IntStream.html#dropWhile(java.util.function.IntPredicate))

Consult the documentation matching your JDK version. The examples in this lesson use `toList()` (Java 16+) and `record` (Java 16+), so full demo programs target **JDK 17 or later**; `dropWhile` itself has been available since JDK 9.

## 3. Exact Rule on an Ordered Stream

Let the ordered source sequence be `x₀, x₁, ..., xₙ₋₁` and the condition be `p(x)`. Find the first index `k` such that `p(xₖ) == false`. Then:

- Drop all elements `x₀ ... xₖ₋₁`.
- Keep `xₖ ... xₙ₋₁`.
- If every element matches, the result is empty.
- If the very first element fails, the entire source is retained.

There is no search for a boundary at the end of the sequence, nor does the condition have to remain false **forever**. Only the first transition from true to false while moving from the start of the sequence determines the cut point.

| Ordered source | Predicate | `dropWhile` result |
| --- | --- | --- |
| `[1, 2, 3, 7, 2, 8]` | `n < 5` | `[7, 2, 8]` |
| `[1, 2, 3]` | `n < 5` | `[]` |
| `[7, 1, 2]` | `n < 5` | `[7, 1, 2]` |
| `[]` | `n < 5` | `[]` |
| `[5, 6, 7]` | `n < 5` | `[5, 6, 7]` |
| `[1, 2, 5, 3]` | `n <= 5` | `[3]` |

The final example shows that **strict `<` and inclusive `<=` boundaries differ**: if the predicate is `n <= 5`, `5` stays inside the dropped prefix. When implementing timestamp or ID cutoffs, state explicitly whether **boundary equality is kept or dropped**.

## 4. Comparing `dropWhile`, `takeWhile`, `filter`, and `skip`

These methods look similar because they all shorten the resulting sequence, yet their contracts differ.

### 4.1. `dropWhile` vs `filter`

`filter` applies the condition to **every evaluated element**. `dropWhile` only decides the **prefix cutoff point**.

```java
List<Integer> source = List.of(1, 2, 8, 3, 10);

List<Integer> droppedPrefix = source.stream()
    .dropWhile(n -> n < 5)
    .toList();
// [8, 3, 10]

List<Integer> filtered = source.stream()
    .filter(n -> n >= 5)
    .toList();
// [8, 10]
```

If the condition can become true again after a failing element, **the two results differ**. Replace `dropWhile` with `filter` only when business logic genuinely wants element-by-element selection.

### 4.2. `dropWhile` vs `takeWhile`

On an **ordered** stream, both use the longest prefix satisfying the predicate, but with opposite actions:

```java
List<Integer> source = List.of(1, 2, 8, 3, 10);

List<Integer> prefix = source.stream()
    .takeWhile(n -> n < 5)
    .toList(); // [1, 2]

List<Integer> suffix = source.stream()
    .dropWhile(n -> n < 5)
    .toList(); // [8, 3, 10]
```

On an ordered source, `takeWhile` keeps the prefix and `dropWhile` discards the same prefix. If you need both parts independently, create **two pipelines** from the same re-iterable source; never try to reuse a stream already consumed by a terminal operation.

### 4.3. `dropWhile` vs `skip`

`skip(long n)` discards a **fixed count** of `n` leading elements, regardless of values:

```java
List<Integer> source = List.of(1, 2, 8, 3, 10);

System.out.println(source.stream()
    .skip(2)
    .toList()); // [8, 3, 10]

System.out.println(source.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [8, 3, 10]
```

The two results match only by coincidence because there happen to be two leading numbers below `5`. If the source changes to `[1, 2, 4, 8, 3, 10]`, `skip(2)` keeps `4`, while `dropWhile(n -> n < 5)` drops `4` as well. `skip` suits positional pagination, whereas `dropWhile` suits condition-defined cutoffs.

### 4.4. Operation Selection Table

| Business requirement | Choose | Reason |
| --- | --- | --- |
| Drop contiguous leading elements matching a condition | `dropWhile(predicate)` | Slices by prefix condition |
| Take contiguous leading elements matching a condition | `takeWhile(predicate)` | Keeps the prefix |
| Keep every element matching a condition, regardless of position | `filter(predicate)` | Evaluates each element individually |
| Drop exactly the first `n` elements | `skip(n)` | Slices by count |
| Cap output to at most `n` elements | `limit(n)` | Caps by output count |
| Sort data by a comparator | `sorted(comparator)` | Reorders to redefine the prefix |

## 5. Encounter Order Is the Decisive Condition

The "prefix" rule is well-defined only when the stream has an **encounter order**. Commonly ordered sources include `List`, arrays, `IntStream.range`, and `Stream.of`. Structures such as `HashSet` typically **do not guarantee encounter order**.

### 5.1. Ordered Sources

```java
List<String> lines = List.of(
    "# auto-generated file",
    "# version 2",
    "id,name",
    "# this # sign is part of the subsequent data",
    "1,An"
);

List<String> content = lines.stream()
    .dropWhile(line -> line.startsWith("#"))
    .toList();

System.out.println(content);
// [id,name, # this # sign is part of the subsequent data, 1,An]
```

`dropWhile` drops only the two **leading** comment lines. The line starting with `#` after the `id,name` header is retained. If you instead want to strip **all** comment lines, use `filter(line -> !line.startsWith("#"))` per your data-format policy.

### 5.2. Unordered Sources: A Completely Different Contract

For an **unordered stream**, the Javadoc defines no "first prefix". If some elements satisfy the predicate, `dropWhile` may drop **any subset** of those matching elements, including the empty set. Non-matching elements must still be retained. Consequently, you cannot predict exactly which matching elements will remain.

Example:

```java
import java.util.Set;

Set<Integer> numbers = Set.of(1, 2, 3, 8, 9);

List<Integer> result = numbers.stream()
    .unordered()
    .dropWhile(n -> n < 5)
    .toList();

// Do not assert result == [8, 9]
// or any fixed output order.
// 8 and 9 do not satisfy n < 5, so dropWhile cannot drop them.
```

Do not add `unordered()` merely assuming it speeds up the pipeline: for `dropWhile`, it permits a **different result set**. If the requirement is to drop a deterministic prefix by time or task order, you must **have and preserve encounter order**.

If every element matches, `dropWhile` may drop all of them; on an unordered stream it is not required to drop all of them. If no element matches, `dropWhile` cannot drop any element.

### 5.3. `sorted` Redefines the Meaning of the Prefix

`sorted` establishes an encounter order based on comparison. This is often helpful when the cutoff condition is an **ascending threshold**, though it also alters element order relative to the original source.

```java
List<Integer> values = List.of(6, 1, 8, 2, 4);

System.out.println(values.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [6, 1, 8, 2, 4] because 6 fails immediately at the start.

System.out.println(values.stream()
    .sorted()
    .dropWhile(n -> n < 5)
    .toList()); // [6, 8]
```

Adding `sorted()` shifts the semantics from "drop the prefix in input order" to "drop values below the threshold after sorting ascending". `sorted` is a stateful intermediate operation that may need to inspect, sort, and buffer many elements before returning results; weigh the cost on large datasets.

## 6. Practical Example: Taking Events from a Timestamp Cutoff Onward

Suppose a system receives events **out of chronological order**, yet a report must retain events occurring from a cutoff timestamp onward. Sort first, then apply `dropWhile` on the timestamp:

```java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;

public class EventsAfterCutoff {

    record Event(String id, Instant occurredAt, String message) {}

    public static void main(String[] args) {
        List<Event> events = List.of(
            new Event("E3", Instant.parse("2026-11-17T08:15:00Z"), "Done"),
            new Event("E1", Instant.parse("2026-11-17T08:05:00Z"), "Created"),
            new Event("E4", Instant.parse("2026-11-17T08:07:00Z"), "Received"),
            new Event("E2", Instant.parse("2026-11-17T08:10:00Z"), "Started")
        );

        Instant cutoff = Instant.parse("2026-11-17T08:10:00Z");

        List<String> eventIds = events.stream()
            .sorted(Comparator.comparing(Event::occurredAt))
            .dropWhile(event -> event.occurredAt().isBefore(cutoff))
            .map(Event::id)
            .toList();

        System.out.println(eventIds); // [E2, E3]
    }
}
```

Here:

1. `sorted(Comparator.comparing(Event::occurredAt))` defines encounter order in ascending timestamp order.
2. `dropWhile(event -> event.occurredAt().isBefore(cutoff))` drops events **before** the cutoff.
3. An event occurring **exactly at the cutoff** is kept because `isBefore(cutoff)` returns `false` when equal.
4. `map(Event::id)` maps each event to its ID; `toList()` collects results in sorted order.

If the requirement is to keep events **strictly after** the cutoff, change the predicate to:

```java
.dropWhile(event -> !event.occurredAt().isAfter(cutoff))
```

This expression drops events at the cutoff as well, since "not after cutoff" covers **before or equal**.

**Important:** `dropWhile` does not act as a valid time filter on unsorted timestamps if you omit sorting. If the source is already **guaranteed** to be ascending by time, you can omit `sorted` to avoid sorting overhead. If ordering does not need to be preserved and you simply want all events not before the cutoff, `filter(event -> !event.occurredAt().isBefore(cutoff))` may be more direct and appropriate.

## 7. Practical Example: Resuming from the First Incomplete Task

Consider a prioritized list of tasks. We want to skip completed tasks **at the head of the sequence**, then keep everything from the point where work resumes:

```java
import java.util.List;

record Task(String id, boolean done) {}

List<Task> tasks = List.of(
    new Task("A", true),
    new Task("B", true),
    new Task("C", false),
    new Task("D", true),
    new Task("E", false)
);

List<String> remainingFromFirstIncomplete = tasks.stream()
    .dropWhile(Task::done)
    .map(Task::id)
    .toList();

System.out.println(remainingFromFirstIncomplete); // [C, D, E]
```

**Why is `D` kept even though it is done?** This models "resuming from the first incomplete position", keeping the suffix so task states can be inspected in sequence. If business logic simply wants a **list of incomplete tasks** regardless of position, use:

```java
List<String> incompleteIds = tasks.stream()
    .filter(task -> !task.done())
    .map(Task::id)
    .toList();

System.out.println(incompleteIds); // [C, E]
```

The design crux is clarifying whether you mean **drop a leading prefix in order** or **filter elements by status**, because the two problems are not identical.

## 8. Combining `dropWhile` with `limit`, `map`, `reduce`, and `collect`

### 8.1. Keyset-Style Paging by Threshold

Suppose IDs are already ascending and we need up to two IDs **greater than** cursor `20`:

```java
List<Integer> ids = List.of(10, 20, 30, 40, 50);
int cursor = 20;

List<Integer> page = ids.stream()
    .dropWhile(id -> id <= cursor)
    .limit(2)
    .toList();

System.out.println(page); // [30, 40]
```

For this to be correct, the source must be sorted ascending by the same criterion as the cursor. Given `[30, 10, 40]`, the first element `30` ends the dropped prefix immediately, so `10` still appears in the output. If data lives in a large database, push the cursor condition and limit into the query instead of loading everything into the JVM before calling `dropWhile`.

Operation order matters greatly:

```java
List<Integer> byCursorThenLimit = ids.stream()
    .dropWhile(id -> id <= 20)
    .limit(2)
    .toList(); // [30, 40]

List<Integer> limitedBeforeCursor = ids.stream()
    .limit(2)
    .dropWhile(id -> id <= 20)
    .toList(); // []
```

Putting `limit` before `dropWhile` inspects only the first two IDs and drops both, leaving no data.

### 8.2. Summing the Suffix

```java
List<Integer> points = List.of(1, 3, 5, 10, 2);

int totalAfterThreshold = points.stream()
    .dropWhile(n -> n < 5)
    .mapToInt(Integer::intValue)
    .sum();

System.out.println(totalAfterThreshold); // 17 = 5 + 10 + 2
```

When summing primitive integers, `mapToInt` and `sum` avoid creating many intermediate `Integer` wrappers for `reduce`.

### 8.3. Grouping the Suffix of an Event Sequence

Reusing the `events` list sorted by `occurredAt` from section 6, we can group events from the cutoff onward by message type:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> countByMessage = events.stream()
    .sorted(Comparator.comparing(Event::occurredAt))
    .dropWhile(event -> event.occurredAt().isBefore(cutoff))
    .collect(Collectors.groupingBy(
        Event::message,
        Collectors.counting()
    ));
```

`dropWhile` determines **which events belong to the suffix to aggregate**; `collect(groupingBy(...))` is the aggregating terminal operation. The resulting `Map` does not guarantee key iteration order; if display ordering is required, specify a sort policy or use the appropriate collector overload.

## 9. Empty Inputs, Boundary Conditions, and `null`

### 9.1. Cases to Master

```java
import java.util.List;
import java.util.stream.Stream;

System.out.println(
    Stream.<Integer>empty()
        .dropWhile(n -> n < 5)
        .toList()
); // []

System.out.println(
    List.of(1, 2, 3).stream()
        .dropWhile(n -> n < 5)
        .toList()
); // []

System.out.println(
    List.of(8, 1, 2).stream()
        .dropWhile(n -> n < 5)
        .toList()
); // [8, 1, 2]
```

An empty source has no elements to retain. If all elements satisfy the condition, `dropWhile` drops the entire sequence. If the very first element fails, it keeps the entire ordered sequence.

### 9.2. `null` Predicate and `null` Elements

Passing a `null` `Predicate` to `dropWhile` is invalid and can throw `NullPointerException`. Elements **inside the stream** may be `null` if the source permits them, so the predicate needs an explicit policy:

```java
import java.util.ArrayList;
import java.util.List;

List<String> data = new ArrayList<>();
data.add("");
data.add(null);
data.add("start");
data.add("");

// Convention: both leading empty strings and nulls are dropped.
List<String> result = data.stream()
    .dropWhile(value -> value == null || value.isEmpty())
    .toList();

System.out.println(result); // [start, ""]
```

If `null` represents corrupt data, reject it early rather than silently treating it as something to skip. `List.of(...)` rejects `null`, so the example uses `ArrayList`. When results contain `null`, also note that some terminal operations or collectors have specific rules regarding `null` values.

### 9.3. Do Not Use Predicates with External State

Avoid writing:

```java
// Anti-pattern: predicate mutates external state and relies on invocation count.
java.util.concurrent.atomic.AtomicInteger calls =
    new java.util.concurrent.atomic.AtomicInteger();

var result = values.stream()
    .dropWhile(n -> calls.incrementAndGet() <= 2)
    .toList();
```

`AtomicInteger` makes concurrent updates safe, yet the predicate still has side effects, depends on mutable state, and cannot be tested as a pure condition. The Javadoc requires stream behavioral parameters to be **non-interfering** and generally **stateless**. Output may depend on implementation or execution mode; use `skip(2)` if the task is dropping two elements, and use a value-only predicate if slicing by condition.

Do not mutate the source collection inside the predicate:

```java
// Do not do this:
// list.stream().dropWhile(item -> {
//     list.remove(item); // Interferes with the source being traversed.
//     return item.isOld();
// }).toList();
```

## 10. Infinite Streams and Termination Conditions

`dropWhile` can work on infinite streams if it **eventually encounters** an element failing the predicate and a downstream terminal operation can terminate:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> afterOneHundred = Stream.iterate(0, n -> n + 1)
    .dropWhile(n -> n < 100)
    .limit(4)
    .toList();

System.out.println(afterOneHundred); // [100, 101, 102, 103]
```

However, if an infinite stream **always** satisfies the predicate, `dropWhile` can never find the first element to keep:

```java
// Example that risks non-termination; DO NOT run as a normal test.
// Stream.generate(() -> 0)
//     .dropWhile(n -> n == 0)
//     .findFirst();
```

`findFirst()` can only return once an output element exists, while `dropWhile` keeps discarding every element received. Placing `limit(n)` **before** `dropWhile` bounds the inspected source, though it also changes semantics because at most `n` initial elements are examined.

Do not place `sorted()` on an infinite source expecting it to supply order to `dropWhile`: sorting an entire infinite source generally cannot complete.

## 11. Cost, Parallelism, and Performance Risks

### 11.1. Sequential Execution Characteristics

When the stream is ordered and sequential, `dropWhile` must determine the prefix: it checks leading elements until the first failing one, then forwards remaining elements as requested by downstream operations. For example, `dropWhile(...).limit(5)` can stop early once five suffix elements are received, provided the source and upstream steps allow it.

With an ordered source and a simple predicate, this is usually straightforward and requires no auxiliary list just to locate the cut point. Actual cost still depends on surrounding operations, the data source, short-circuiting behavior, and how many elements are dropped.

### 11.2. `parallel()` Can Be Expensive When Ordering Must Be Preserved

The Javadoc notes that `dropWhile` on an **ordered parallel stream** can be quite costly when preserving the "longest prefix": threads process different chunks of the source while still having to locate the boundary in global order.

```java
List<Integer> numbers = java.util.stream.IntStream.range(0, 100_000)
    .boxed()
    .toList();

List<Integer> remaining = numbers.parallelStream()
    .dropWhile(n -> n < 90_000)
    .toList();

System.out.println(remaining.size()); // 10000
```

Do not assume `parallelStream` is faster just because you have multiple CPU cores. Measure on real datasets. When source order must be kept and the check is cheap, sequential execution is often the better choice.

Cases that **do not depend on output order and accept unordered semantics** may consider `unordered()` to reduce overhead; however, that change allows `dropWhile` to drop an arbitrary subset of matching elements, so it is **not equivalent** to a threshold cut. Do this only if the output specification permits it.

### 11.3. Primitive Streams

`IntStream`, `LongStream`, and `DoubleStream` also offer `dropWhile` with their corresponding primitive predicates:

```java
import java.util.stream.IntStream;

int sum = IntStream.range(0, 8)
    .dropWhile(n -> n < 5)
    .sum(); // 5 + 6 + 7 = 18

System.out.println(sum); // 18
```

`IntStream.dropWhile(IntPredicate)` avoids boxing to `Integer`. For `DoubleStream`, define an explicit policy for `NaN`, infinities, and signed zeros, since floating-point comparisons have edge cases. For example, `Double.NaN < 5` evaluates to `false`, so a `NaN` element can end the dropped prefix early.

### 11.4. Stream Gatherers and Advanced Slicing

Stream Gatherers became an official API in **JDK 24** for expressing stateful intermediate transformations such as windows or prefix scans. However, when the requirement is simply "drop a prefix matching a predicate", `dropWhile` is simpler and communicates intent more clearly. Do not use Gatherers to replace an existing built-in operation unless business logic needs richer state or slicing rules.

## 12. Testing Semantics and Common Pitfalls

### 12.1. JUnit 5 Unit Tests

These tests use JDK 17+ and JUnit Jupiter; rather than asserting how many times the predicate runs, they verify **guaranteed outputs**:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class DropWhileTest {

    @Test
    void dropsOnlyLeadingMatchingElements() {
        List<Integer> input = List.of(1, 2, 8, 3, 10);

        assertEquals(
            List.of(8, 3, 10),
            input.stream().dropWhile(n -> n < 5).toList()
        );
    }

    @Test
    void returnsEmptyWhenAllElementsMatch() {
        assertEquals(
            List.of(),
            List.of(1, 2, 3).stream()
                .dropWhile(n -> n < 5)
                .toList()
        );
    }

    @Test
    void retainsWholeStreamWhenFirstDoesNotMatch() {
        assertEquals(
            List.of(8, 1, 2),
            List.of(8, 1, 2).stream()
                .dropWhile(n -> n < 5)
                .toList()
        );
    }

    @Test
    void handlesEmptySource() {
        assertEquals(
            List.of(),
            Stream.<Integer>empty()
                .dropWhile(n -> n < 5)
                .toList()
        );
    }

    @Test
    void differsFromFiltering() {
        List<Integer> input = List.of(1, 2, 8, 3, 10);

        assertEquals(
            List.of(8, 3, 10),
            input.stream().dropWhile(n -> n < 5).toList()
        );
        assertEquals(
            List.of(8, 10),
            input.stream().filter(n -> n >= 5).toList()
        );
    }

    @Test
    void boundaryValueIsRetainedWhenPredicateIsStrict() {
        List<Integer> input = List.of(1, 2, 5, 7);

        assertEquals(
            List.of(5, 7),
            input.stream().dropWhile(n -> n < 5).toList()
        );
    }
}
```

Avoid tests like "predicate must be called exactly N times" or asserting a specific element set on an unordered stream, as those are not guaranteed by the API contract.

### 12.2. Six Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `dropWhile` to remove all invalid elements | Invalid elements after the boundary remain | Use `filter` if full filtering is needed |
| Forgetting to ensure encounter order | Cut point is not guaranteed | Use an ordered source, or `sorted` when business logic requires sorting |
| Using `unordered()` when an exact boundary is needed | Dropped element set may vary | Keep ordered semantics |
| Confusing `<` with `<=` | Boundary value is mistakenly dropped or kept | Specify boundaries explicitly in requirements and tests |
| Unintentionally placing `limit` before `dropWhile` | Searches for cut point only within an initial slice | Put `dropWhile` before `limit` when capping the suffix |
| Predicate has side effects or mutates source | Unpredictable results, parallel race bugs | Use pure, non-interfering predicates |

## 13. Practice Exercises

**Exercise 1 — Dropping a file header.** Given:

```java
List<String> lines = List.of(
    "# generated",
    "# schema 1",
    "name,age",
    "# note inside data",
    "An,20"
);
```

Produce a list retaining lines from `name,age` to the end. Explain why the later line starting with `#` still appears in the output. Then change the problem to "drop every line starting with `#`" and pick the appropriate operation.

**Exercise 2 — Should the boundary include equality?** Given `[2, 4, 6, 8, 3]` and threshold `6`. Write two pipelines:

- Drop leading elements **strictly less than** `6`. Expected output `[6, 8, 3]`.
- Drop leading elements **less than or equal to** `6`. Expected output `[8, 3]`.

**Exercise 3 — Pagination.** Given an ascending ID list `[10, 20, 30, 40, 50, 60]`, cursor `30`, and page size `2`. Retrieve `[40, 50]` using `dropWhile` and `limit`. Try swapping the two operations and explain why the output differs.

**Exercise 4 — Unsorted data.** Given `[9, 1, 5, 2, 12]`, requirement "keep numbers `5` and above". Explain why `dropWhile(n -> n < 5)` on the raw sequence is wrong. Write a solution using `filter`. If "ascending output" is also required, add `sorted` in the right place.

**Exercise 5 — Parallel evaluation.** A developer replaces `stream()` with `parallelStream()` upon seeing 100,000 elements, and calls `unordered()` to boost performance. Analyze the impact on both **correctness** (does it still drop the exact threshold prefix?) and **performance** (is it guaranteed faster?). Rewrite the solution correctly if ascending ID order must be preserved.

## 14. Checklist Before Applying

| Question to ask beforehand | Decision to make |
| --- | --- |
| Need to drop a prefix or filter all elements? | `dropWhile` differs from `filter` |
| Does the stream have an encounter order? | Prefix rules require deterministic order |
| Is the first non-matching element kept? | **Yes** on an ordered stream |
| What if the predicate becomes true again after the first failure? | Later elements are still kept |
| Should values equal to the threshold be dropped? | Depends on `<` vs `<=` in the predicate |
| Could all elements match? | Output can be empty; handle it |
| Could the source be infinite? | Ensure the cutoff is reached and the terminal operation can finish |
| Need `limit` after dropping the prefix? | Order them according to pagination/slicing semantics |
| Thinking of running parallel or dropping order? | Re-check the contract and benchmark |
| Using `IntStream`/`LongStream`/`DoubleStream`? | Use the primitive-typed `dropWhile` |

`dropWhile` directly expresses **dropping a contiguous matching head** in a Java Stream API pipeline. To use it properly, determine the source's order, the predicate boundary, and the meaning of the retained suffix before combining it with `map`, `reduce`, `collect`, grouping, or other slicing operations. Laziness and parallelism affect execution timing, resources, and cost, but they do not alter the prefix contract of an **ordered stream**.
