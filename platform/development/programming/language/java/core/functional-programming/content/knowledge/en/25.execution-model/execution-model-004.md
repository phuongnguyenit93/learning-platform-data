# Stateless and Stateful Operations in Java Streams

## 1. Problem Statement: Why Do Two Similar-Looking Pipelines Have Different Costs?

The Java Stream API allows chaining data transformations into a pipeline:

~~~java
List<Integer> values = List.of(7, 4, 7, 2, 4, 9);

List<Integer> result = values.stream()
        .filter(n -> n >= 4)
        .distinct()
        .sorted()
        .toList();
~~~

Elements pass through `filter`, `distinct`, and `sorted`, and are then collected into a List. However, these three intermediate operations do not share the same mechanism:

- `filter` decides whether to keep or discard **an element based on that element alone**, without needing to remember all previous elements.
- `distinct` must determine whether an element has already appeared in order to remove duplicates; it **may need to remember previously encountered elements**.
- `sorted` needs to establish a comparison order among elements; for general data, it **may need to buffer most or all elements** before emitting sorted output.

In the Java Stream documentation, these are two groups: **stateless intermediate operations** (intermediate operations that do not retain state across elements) and **stateful intermediate operations** (intermediate operations that require state or depend on other elements or position in the stream).

This difference affects laziness, early termination capability, memory usage, parallel Stream performance, and logical correctness when the order of operations changes.

### After this lesson, you will:

1. Accurately define `stateless` and `stateful` in the **context of Stream intermediate operations**.
2. Classify `map`, `filter`, `flatMap`, `peek`, `distinct`, `sorted`, `limit`, `skip`, `takeWhile`, and `dropWhile`.
3. Distinguish **an operation's internal state** from **lambdas with side effects and shared mutable state**.
4. Explain why `sorted().limit(n)` differs from `limit(n).sorted()`.
5. Understand the encounter order requirements of `distinct`, `limit`, and `takeWhile` when running in parallel.
6. Understand lazy pipelines, terminal operations, short-circuiting, and optimization cases that may skip invoking certain lambdas.
7. Run a complete Java 17 program, predict stdout, and avoid common mistakes.

## 2. Background: Source, Intermediate Operations, and Terminal Operation

A Stream pipeline typically consists of:

~~~text
Source
  |
  v
Intermediate operations (0 or more)
  |
  v
Terminal operation
  |
  v
Result or side effect
~~~

Example:

~~~java
List<String> result = Stream.of(" a ", "bb", " c ", "dd")
        .map(String::trim)
        .filter(s -> s.length() == 1)
        .toList();

System.out.println(result); // [a, c]
~~~

Here:

- `Stream.of(...)` creates the source.
- `map(...)` and `filter(...)` are **intermediate operations**: they return a new Stream to continue the pipeline.
- `toList()` is a **terminal operation**: it triggers pipeline evaluation and collects the result.

Intermediate operations are typically **lazy**: the expression `stream.map(...).filter(...)` may only construct the pipeline without traversing the data yet. A terminal operation such as `toList`, `findFirst`, `count`, or `forEach` is typically when the pipeline is evaluated. Optimization details depend on the operation and source characteristics; **there is no guarantee that every intermediate lambda will always be invoked a fixed number of times**.

### 2.1. Note: A Stream Is Not a Reusable Collection

~~~java
Stream<String> stream = Stream.of("a", "b");
long count = stream.count();
// stream.toList(); // Cannot reuse an already consumed Stream.
~~~

A Stream can normally only be consumed once; if a second processing pass is needed, create a new Stream from a re-traversable source or store the appropriate data in a collection.

### 2.2. This Lesson Focuses on Intermediate Operations

`stateless`/`stateful` in this lesson is used to describe **characteristics of intermediate transformations**. Terminal operations have their own computation strategies, combining requirements, and short-circuiting behavior; you should not use the intermediate operation classification to claim that all terminal operations collect or retain all data.

## 3. What Is a Stateless Intermediate Operation?

A **stateless** intermediate operation does not need to remember the processing results of previous elements to decide how to process **a new element**. Conceptually, each element can be processed independently using the provided function.

### 3.1. `filter`: Deciding Based on Each Element

~~~java
List<Integer> filtered = List.of(7, 4, 7, 2, 4, 9)
        .stream()
        .filter(n -> n >= 4)
        .toList();

System.out.println(filtered); // [7, 4, 7, 4, 9]
~~~

The predicate `n -> n >= 4` only reads `n`. To know whether `7` should be kept, it **does not need to know** whether the previous element was `4` or `9`.

### 3.2. `map`: Transforming Each Element

~~~java
List<String> labels = List.of(1, 2, 3).stream()
        .map(n -> "item-" + n)
        .toList();

System.out.println(labels); // [item-1, item-2, item-3]
~~~

`map` takes one element and produces a corresponding value. With a pure function, `map` can be applied independently across elements.

### 3.3. `flatMap`: One Element Produces a Sub-Stream

~~~java
List<String> words = Stream.of("red blue", "green")
        .flatMap(line -> Arrays.stream(line.split(" ")))
        .toList();

System.out.println(words); // [red, blue, green]
~~~

`flatMap` is classified as a stateless intermediate operation. The mapper creates a sub-Stream from the **current element**; there is no need to maintain the set of previous elements to decide how to process a new element.

This **does not mean** every sub-Stream is cheap or holds no resources: a mapper may create a large Stream, open I/O, or throw errors. Resources and costs must be managed separately. Under `Stream.flatMap` semantics, mapped Streams are closed after their contents are placed into the pipeline according to the API contract.

### 3.4. `peek` Is Also a Stateless Intermediate Operation, but Should Not Carry Business Logic

~~~java
List<Integer> values = Stream.of(1, 2, 3)
        .peek(n -> System.out.println("saw " + n))
        .toList();
~~~

`peek` is classified in the API as a stateless intermediate operation. However, the `println` action has a **side effect**. Do not assume that `peek` will execute exactly once per element in every pipeline: some terminal operations and optimizations may skip unnecessary steps. `peek` is better suited for controlled debugging support rather than writing data, business counting, or emitting mandatory events.

### 3.5. Common Characteristics of Stateless Operations

| Operation | Processing a single element | Needs to remember other elements to determine this element's result? |
| --- | --- | --- |
| `map(f)` | Converts value to `f(value)` | No |
| `filter(p)` | Keeps if `p(value)` is true | No |
| `mapToInt(f)` | Converts to primitive int | No |
| `flatMap(f)` | Expands element into a sub-Stream | No by operation classification |
| `peek(action)` | Performs an observation action | No by operation classification, though the action may have side effects |

Statelessness makes per-element processing and pipeline fusion easier, but it does not mean **every user lambda is guaranteed to be pure, thread-safe, or stateless**. These are two separate concerns.

## 4. What Is a Stateful Intermediate Operation?

A **stateful** intermediate operation may need information from previously seen elements, position in encounter order, or overall data to determine which elements are emitted and in what order.

### 4.1. `distinct`: Remembering Data to Remove Duplicates

~~~java
List<Integer> unique = List.of(7, 4, 7, 2, 4, 9)
        .stream()
        .distinct()
        .toList();

System.out.println(unique); // [7, 4, 2, 9]
~~~

To decide whether to keep the second `7`, `distinct` must know that an equivalent `7` was already encountered earlier. On a reference Stream, the duplicate criterion is based on `Object.equals(Object)` and proper hash/equality rules; **not the comparator of `sorted`**.

For a Stream with encounter order, `distinct` is guaranteed to be **stable**: when there are duplicate elements according to `equals`, the element appearing first in encounter order is retained. For an unordered Stream, there is no guarantee which copy among equal elements is selected.

### 4.2. `sorted`: Establishing a Total Order

~~~java
List<Integer> sorted = List.of(7, 4, 7, 2, 4, 9)
        .stream()
        .sorted()
        .toList();

System.out.println(sorted); // [2, 4, 4, 7, 7, 9]
~~~

To emit the smallest value first with an arbitrary comparator, `sorted` in principle needs to know the values that arrive later. It is a **stateful intermediate operation** that may have to buffer data in order to sort. On an ordered Stream, `sorted` is guaranteed to be stable: elements considered equal by the comparator preserve their relative encounter order. On an unordered Stream, there is no stability guarantee among elements that compare equal to 0.

`sorted(Comparator)` relies on the comparator contract. A comparator that violates transitivity or depends on randomness/shared mutation can produce wrong results or errors, regardless of whether the Stream is used sequentially or in parallel.

### 4.3. `limit` and `skip`: Position-Dependent

~~~java
List<Integer> first = List.of(7, 4, 7, 2, 4, 9)
        .stream()
        .limit(3)
        .toList();

List<Integer> tail = List.of(7, 4, 7, 2, 4, 9)
        .stream()
        .skip(3)
        .toList();

System.out.println(first); // [7, 4, 7]
System.out.println(tail);  // [2, 4, 9]
~~~

`limit(n)` needs to know how many elements have been emitted; `skip(n)` needs to know how many elements must be skipped before emitting results. These are **stateful intermediate operations**; on ordered Streams they depend on encounter order. `limit` is also a **short-circuiting intermediate operation**: it can bound the amount of data that needs to be processed.

With unordered Streams, these operations do not necessarily select the "first n elements" in a fixed original order, because the source has no encounter order to preserve. Do not rely on a single run to infer a guaranteed order.

### 4.4. `takeWhile` and `dropWhile`: Dependent on the Prefix of an Ordered Stream

Since Java 9:

~~~java
List<Integer> input = List.of(7, 4, 7, 2, 4, 9);

List<Integer> prefix = input.stream()
        .takeWhile(n -> n >= 4)
        .toList();

List<Integer> remainder = input.stream()
        .dropWhile(n -> n >= 4)
        .toList();

System.out.println(prefix);    // [7, 4, 7]
System.out.println(remainder); // [2, 4, 9]
~~~

**Do not confuse `takeWhile` with `filter`.**

- `filter(n -> n >= 4)` selects **all** elements matching the predicate at any position: `[7, 4, 7, 4, 9]`.
- `takeWhile(n -> n >= 4)` on an ordered Stream takes the **longest prefix** of consecutive elements matching the predicate, and stops upon encountering `2`.
- `dropWhile(n -> n >= 4)` on an ordered Stream discards **that prefix**, then returns the remainder, including `2` and subsequent values even if they match the predicate.

These two operations are stateful and often interact strongly with encounter order. On an unordered Stream, the Javadoc allows selecting a subset of elements matching the predicate under different constraints, so do not assume the same prefix semantics as an ordered Stream.

### 4.5. Classification Table of Key Operations

| Intermediate operation | Category | What must it remember conceptually? | Key notes |
| --- | --- | --- | --- |
| `map`, `mapToInt` | Stateless | No element history needed | Mapper should be non-interfering and stateless |
| `filter` | Stateless | No element history needed | Not `takeWhile` |
| `flatMap` | Stateless | No element history needed | Sub-Streams can be resource-intensive |
| `peek` | Stateless | No history per operation | Side effects are not guaranteed in count |
| `distinct` | Stateful | Values already seen | Ordered: keeps first occurrence of duplicates |
| `sorted` | Stateful | Set of elements to compare/order | May need to buffer data |
| `limit(n)` | Stateful, short-circuiting | Count of elements emitted | `n` must be non-negative |
| `skip(n)` | Stateful | Count of elements skipped | `n` must be non-negative |
| `takeWhile` | Stateful, short-circuiting | Prefix state matching predicate | Different from `filter` |
| `dropWhile` | Stateful | Prefix state to drop | Different from `filter` |

There is no rule that **every stateful operation must buffer the entire source**. `limit` often only needs to count the selected elements, whereas `sorted` may need to retain many elements. "Stateful" indicates **dependencies during processing**, not a fixed memory footprint.

## 5. Complete Java 17 Program: Observing the Differences

Create the file **`StatefulStreamDemo.java`**:

~~~java
import java.util.List;

public class StatefulStreamDemo {

    record Reading(String id, int score) {}

    public static void main(String[] args) {
        List<Reading> readings = List.of(
                new Reading("A", 7),
                new Reading("B", 4),
                new Reading("C", 7),
                new Reading("D", 2),
                new Reading("E", 4),
                new Reading("F", 9)
        );

        // Stateless: each Reading is filtered and mapped independently.
        System.out.println("stateless=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .toList());

        // Stateful: needs to know previously seen values for distinct.
        System.out.println("distinct=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .distinct()
                .toList());

        // Stateful: sorted must determine the order among elements.
        System.out.println("sorted=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .sorted()
                .toList());

        // Two operation orders produce different results.
        System.out.println("sort-then-limit=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .sorted()
                .limit(3)
                .toList());

        System.out.println("limit-then-sort=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .limit(3)
                .sorted()
                .toList());

        System.out.println("skip=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .skip(2)
                .toList());

        // takeWhile/dropWhile look at the prefix of an ordered Stream.
        System.out.println("takeWhile=" + readings.stream()
                .takeWhile(r -> r.score() >= 4)
                .map(Reading::id)
                .toList());

        System.out.println("dropWhile=" + readings.stream()
                .dropWhile(r -> r.score() >= 4)
                .map(Reading::id)
                .toList());

        // List.parallelStream() still has an encounter order.
        System.out.println("parallel-distinct="
                + readings.parallelStream()
                        .filter(r -> r.score() >= 4)
                        .map(Reading::score)
                        .distinct()
                        .toList());
    }
}
~~~

Compile and run on JDK 17 or later:

~~~bash
javac -encoding UTF-8 StatefulStreamDemo.java
java StatefulStreamDemo
~~~

**Exact stdout:**

~~~text
stateless=[7, 4, 7, 4, 9]
distinct=[7, 4, 9]
sorted=[4, 4, 7, 7, 9]
sort-then-limit=[4, 4, 7]
limit-then-sort=[4, 7, 7]
skip=[7, 4, 9]
takeWhile=[A, B, C]
dropWhile=[D, E, F]
parallel-distinct=[7, 4, 9]
~~~

### 5.1. Explaining Each Result

**`stateless`:** `Reading D` has score 2 so it is filtered out; the remaining scores still follow the encounter order from `List`, which is `[7,4,7,4,9]`. `map(Reading::score)` extracts only the current score.

**`distinct`:** The second `7` and second `4` are removed. The ordered Stream keeps the first occurrence by `Integer.equals`, yielding `[7,4,9]`.

**`sorted`:** The same 5 scores after filtering are sorted in ascending order to `[4,4,7,7,9]`; duplicates remain because `sorted` is not `distinct`.

**`sort-then-limit`:** Sorts the entire filtered sequence in ascending numeric order, then takes the first 3 values, yielding `[4,4,7]`.

**`limit-then-sort`:** Takes the first three values of the filtered sequence `[7,4,7]` and only then sorts them, resulting in `[4,7,7]`. These two operations cannot be arbitrarily swapped.

**`skip`:** Skips the first two elements `7,4` of the filtered sequence, leaving `[7,4,9]`.

**`takeWhile`:** Given the original source `A(7), B(4), C(7), D(2), E(4), F(9)`, the predicate is true up to C and becomes false at D; takes the IDs `[A,B,C]`.

**`dropWhile`:** Drops the exact prefix A,B,C and keeps from D to F, yielding `[D,E,F]`.

**`parallel-distinct`:** An ordered List still preserves encounter order even during parallel execution; `distinct` keeps the first occurrence per the contract, resulting in `[7,4,9]`. `toList` collects in the pipeline's encounter order; do not rely on task execution order to explain the output.

## 6. Does Operation Order Change the Result?

Yes. Some pairs of intermediate operations can be reordered under specific conditions, but you must not assume they always commute.

### 6.1. `sorted().limit(n)` vs. `limit(n).sorted()`

~~~java
List<Integer> input = List.of(9, 1, 7, 2, 5);

List<Integer> smallestTwo = input.stream()
        .sorted()
        .limit(2)
        .toList();

List<Integer> firstTwoSorted = input.stream()
        .limit(2)
        .sorted()
        .toList();

System.out.println(smallestTwo);    // [1, 2]
System.out.println(firstTwoSorted); // [1, 9]
~~~

- `sorted().limit(2)` means finding the two smallest values in the entire input according to the comparator.
- `limit(2).sorted()` means **taking the first two elements in encounter order**, then sorting only those two elements.

In the first case, `sorted` may have to observe many or all elements **before** `limit` allows two results to be emitted. In the second case, placing `limit` first reduces the amount of data to sort, but it also changes the problem to **a different meaning**.

### 6.2. `filter().limit(n)` vs. `limit(n).filter()`

~~~java
List<Integer> input = List.of(1, 2, 3, 4, 5);

List<Integer> firstTwoEven = input.stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();

List<Integer> filteredFirstTwo = input.stream()
        .limit(2)
        .filter(n -> n % 2 == 0)
        .toList();

System.out.println(firstTwoEven);    // [2, 4]
System.out.println(filteredFirstTwo); // [2]
~~~

Taking **the first two even numbers** is different from **examining only the first two elements and then filtering even numbers**. Start from the business requirement before optimizing the pipeline.

### 6.3. `distinct().limit(n)` vs. `limit(n).distinct()`

~~~java
List<Integer> input = List.of(1, 1, 2, 3);

System.out.println(input.stream()
        .distinct().limit(2).toList()); // [1, 2]

System.out.println(input.stream()
        .limit(2).distinct().toList()); // [1]
~~~

The first takes the first two **distinct** values. The second processes only the first two elements, then deduplicates within those two elements.

### 6.4. Can `filter` and `map` Be Reordered?

Only when the predicate and mapper have compatible type/logic relationships, the transformation preserves the information needed for filtering, and reordering does not change observable exceptions or side effects. Do not arbitrarily move `filter` before or after `map` by guesswork.

For example, to filter based on `Reading.score`, place `filter(r -> r.score() >= 4)` before `map(Reading::id)`; if you map to ID first, the predicate no longer has the score data to evaluate.

## 7. A Stateless Operation Does Not Mean a Stateful Lambda Is Correct

This is the most important misconception in this lesson.

`map` is still a **stateless intermediate operation by Stream classification**, yet you can easily pass a lambda that **holds or mutates shared mutable state**. Doing so can lead to unpredictable behavior and violates the *stateless, non-interfering* requirements for behavioral parameters in the Stream API.

### 7.1. Anti-pattern: Using an External Counter Variable

~~~java
AtomicInteger counter = new AtomicInteger();

List<String> labels = names.parallelStream()
        .map(name -> counter.incrementAndGet() + ":" + name)
        .toList();
~~~

This is **anti-pattern illustrative code**, with `names` of type `List<String>` and `AtomicInteger` imported. Although `AtomicInteger` supports atomic updates, the sequence number attached to each name depends on scheduling order when the pipeline runs in parallel. It **does not guarantee** that the first name in encounter order receives `1`.

If numbering by input position is required, use explicit indices from the list when appropriate:

~~~java
List<String> labels = IntStream.range(0, names.size())
        .mapToObj(i -> (i + 1) + ":" + names.get(i))
        .toList();
~~~

This snippet requires importing `IntStream`. For a List supporting efficient random access, this clearly expresses position; for a `LinkedList` with repeated `get(i)` calls, consider the access cost.

### 7.2. Anti-pattern: Interfering with the Source While the Stream Runs

~~~java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

List<Integer> result = source.stream()
        .map(n -> {
            source.add(n * 10); // Do not do this.
            return n;
        })
        .toList();
~~~

This is **code intentionally violating the non-interference contract**. Mutating the data source while the pipeline is traversing it can cause `ConcurrentModificationException` or unreliable behavior; do not use `map` to modify the source collection.

### 7.3. Pure Functions Make Pipelines Easier to Reason About

~~~java
List<String> labels = names.stream()
        .filter(name -> name.length() >= 2)
        .map(String::toUpperCase)
        .toList();
~~~

Neither lambda modifies external state; the output depends on the input data. This is the preferred style of composition, especially when switching from sequential to parallel while preserving correctness.

Not every lambda needs to be strictly "side-effect-free" across all APIs, but behavioral parameters passed to Stream operations should satisfy the requirements of non-interference, statelessness, and appropriate synchronization. Do not conflate an operation's classification with a lambda's implementation characteristics.

## 8. Stateful Operations and Encounter Order

### 8.1. What Is Encounter Order?

**Encounter order** is the element order defined by the Stream source and respected by relevant operations while the pipeline retains the ordered characteristic.

- `List.stream()` has an encounter order matching the order in the List.
- `Stream.of("A","B","C")` has an order matching the input elements.
- `HashSet.stream()` **does not guarantee an encounter order**.
- `unordered()` can remove the ordering constraint from a pipeline.

For stateful operations, encounter order often significantly affects semantics or processing cost.

### 8.2. Ordered `distinct` Keeps the First Occurrence; Unordered Does Not

~~~java
record Item(String key, String label) {}

List<Item> source = List.of(
        new Item("x", "first"),
        new Item("x", "second")
);
~~~

By default `equals`, the records above are **not duplicates**, because `label` differs. To deduplicate solely by `key`, you cannot assume `distinct` will automatically use `Item.key()`: you must define appropriate object equality, or use a collector/map that handles keys and a retention policy. Do not use an `Item::key` comparator and expect `distinct()` to distinguish elements by that comparator.

A simple valid example:

~~~java
List<String> source = List.of("A", "B", "A", "C");
System.out.println(source.stream().distinct().toList());
// [A, B, C]
~~~

`String.equals` determines that the two `"A"` values are duplicates; on an ordered Stream, the first `"A"` is kept.

### 8.3. Ordered `sorted` Is Stable by Comparator

~~~java
record Task(String id, int priority) {}

List<Task> tasks = List.of(
        new Task("C", 2),
        new Task("B", 1),
        new Task("A", 2)
);

List<String> ids = tasks.stream()
        .sorted(Comparator.comparingInt(Task::priority))
        .map(Task::id)
        .toList();

System.out.println(ids); // [B, C, A]
~~~

With `priority=2`, Task C appears before A in the source, so a stable sort keeps C before A. If the source is `unordered()`, there is no guarantee about the relative order of two Tasks with the same priority, even though the comparator still sorts by priority.

### 8.4. Ordered `limit` and `skip` Have Clear Positions

`limit(3)` on an ordered Stream takes the first three elements in encounter order. `skip(3)` discards the first three elements. On an unordered Stream, when the requirement is merely to take any at most `n` elements, relaxing the order constraint can enable parallel optimizations, but it **changes the meaning** if the business logic requires "the first records".

`unordered()` **is not a shuffle operation**; it only removes the encounter order guarantee. The result may coincidentally look like the original order, but that must not be relied upon as a contract.

## 9. Lazy Execution, Fusion, and Short-Circuiting

### 9.1. Why Are Stateless Operations Easy to Process Consecutively?

Consider the pipeline:

~~~java
List<String> output = source.stream()
        .filter(n -> n > 0)
        .map(n -> "N=" + n)
        .toList();
~~~

An implementation can traverse element `n`, filter it, and map it before moving to the next element; it does not need to create a temporary List holding **all** elements after `filter` and another temporary List after `map`. This is the mental model of **pipeline fusion** that helps understand the processing mechanism. Do not use this model to predict every internal JDK detail or the exact lambda invocation count for every terminal operation.

### 9.2. Stateful Operations Can Block Output Emission

`sorted` typically must examine elements in the source before knowing the smallest element to emit. `distinct` must also retain information about previously seen values. A pipeline with a stateful stage may require **buffering or synchronization** that changes processing cost.

Even so, **stateful does not mean always buffering the entire source**: `limit(n)` can stop early, `skip(n)` needs to count, and `takeWhile` on an ordered Stream can stop upon encountering an element that fails the predicate. Exact memory requirements depend on the operation, source, size, and execution strategy.

### 9.3. Short-Circuiting Does Not Guarantee Every Pipeline Finishes Quickly

~~~java
List<Integer> firstThree = IntStream.iterate(1, n -> n + 1)
        .limit(3)
        .boxed()
        .toList();

System.out.println(firstThree); // [1, 2, 3]
~~~

`limit(3)` allows stopping the pipeline on an infinite source created by `iterate`. However:

~~~java
// May never produce a result:
IntStream.iterate(1, n -> n + 1)
        .sorted()
        .limit(3)
        .toArray();
~~~

This is an **anti-pattern**—do not run it waiting for stdout. `sorted` must process an unbounded source before knowing the global order; placing `limit` after `sorted` does not make an infinite sort finite.

If the problem allows it, place a finite limit **before** sorting:

~~~java
int[] values = IntStream.iterate(1, n -> n + 1)
        .limit(3)
        .sorted()
        .toArray();
~~~

This snippet processes three elements. When changing order, always verify the meaning of the result, not just speed.

### 9.4. Optimizations May Skip Calling Certain Actions

~~~java
long n = List.of("a", "b", "c").stream()
        .peek(System.out::println)
        .count();
~~~

**Do not treat printing three lines as a contract.** Because the List source has a known size, `count()` can compute the count without traversing each element and without running `peek`. Similarly, some stages that do not alter the element count may be skipped if the terminal operation does not need their results.

If the business requirement is to send logs, update metrics, or emit events **for every element**, do not rely on `peek` in a pipeline that the terminal operation might optimize away; use an explicit processing mechanism with proper side-effect and error specifications.

## 10. Sequential and Parallel: Cost of Stateful Operations

### 10.1. Stateless Operations Have Potential for Independent Processing

`map` and `filter` with non-interfering, stateless behavioral parameters can process multiple elements independently, making them generally favorable for parallel execution. However, **there is no automatic guarantee of being faster**: task splitting, result combining, boxing, cache locality, and data size can make parallel slower than sequential.

If the transformation is very lightweight on a small dataset, parallel Stream overhead can dominate the runtime. Measure on realistic workloads when performance is a goal.

### 10.2. `distinct` with Ordered Parallel Streams Can Incur Buffer/Coordination Costs

On an ordered Stream, `distinct` must respect keeping the first occurrence of each value. With a parallel Stream, preserving stability in encounter order may require **more buffering or coordination between tasks**, creating significant overhead.

The Javadoc allows considering `unordered()` if **the semantics do not require keeping the first occurrence**; this may improve performance for some workloads. However, using `unordered()` must not violate business requirements that depend on preserving order.

### 10.3. `sorted` on Ordered Parallel Streams Remains Stable

`parallelStream().sorted(comparator)` on an ordered source still preserves the stability guarantee of `sorted`. However, sorting is stateful and may need to coordinate/sort chunks of data and merge them. Do not assume it is always faster than sequential sorting.

If data is sorted only to find a single max/min element, you can use `max(comparator)` or `min(comparator)` instead of creating a sorted List. Choose based on the requirement: "get one largest value" is different from "output the entire ordering".

### 10.4. Ordered `limit`/`skip` in Parallel Can Be Expensive

With:

~~~java
List<Integer> first = IntStream.range(0, 1_000)
        .parallel()
        .limit(10)
        .boxed()
        .toList();
~~~

The source range has an encounter order, so the result must be the values 0 through 9. Requiring "the first ten elements" in parallel can require tight coordination to determine exact positions. If the problem genuinely only needs **any ten elements**, `unordered()` can relax ordering and help optimization; however, the output is no longer guaranteed to contain the first ten numbers from the source.

### 10.5. `forEach` and `forEachOrdered` Differ

~~~java
IntStream.range(0, 10)
        .parallel()
        .forEach(System.out::println);
~~~

There is no fixed stdout order: `forEach` does not guarantee action execution order on a parallel Stream. That **does not mean** `map`, `sorted`, or `distinct` before it produced wrong data.

If actions must be executed in encounter order:

~~~java
IntStream.range(0, 10)
        .parallel()
        .forEachOrdered(System.out::println);
~~~

`forEachOrdered` guarantees action order according to encounter order, which may reduce parallel benefits. If you only need ordered data for testing, use `toList()` and compare Lists instead of relying on log order across threads.

### 10.6. Stateful Operations and Shared Mutable State Are Two Different Issues

`sorted` may need internal state **managed by the library**. That does not permit you to mutate a shared `ArrayList` inside `parallel().forEach(shared::add)`. Collectors and the Stream API have coordination mechanisms by contract, whereas external mutations outside the pipeline must be designed for safety separately.

## 11. Primitive Streams and Statistics

The same stateless/stateful concepts apply to `IntStream` and `LongStream`:

~~~java
int[] values = IntStream.rangeClosed(1, 8)
        .filter(n -> n % 2 == 0)
        .map(n -> n * 2)
        .toArray();

System.out.println(Arrays.toString(values)); // [4, 8, 12, 16]
~~~

`filter` and `map` here are stateless. If you add `distinct()` or `sorted()`, those stages are stateful.

Instead of sorting a sequence of numbers to compute their sum:

~~~java
long sum = IntStream.rangeClosed(1, 100)
        .mapToLong(n -> n)
        .sum();
~~~

This is a **terminal reduction**, requiring no sorting. `IntStream.sum()` returns `int` and can overflow on large ranges; `mapToLong` widens the accumulation range in this example, though `long` still has limits.

**Note:** do not assume `IntStream` is always faster than reference pipelines in every problem; consider data types, boxing, source characteristics, lambda cost, and benchmark when performance truly matters.

## 12. Designing Pipelines Around Business Requirements

Suppose a system processes transactions with fields `id`, `score`, and arrival order:

- If you need to **filter all transactions with score >= 4**, use `filter`.
- If you need to **keep transactions with unique ids and pick the first received**, design clear equality/key semantics and a strategy to keep the first in encounter order; `distinct()` alone suffices only when the object's `equals` represents that exact key.
- If you need to **sort all by score**, use `sorted(comparator)`.
- If you need the **three highest-scoring transactions**, you can use `sorted(comparator.reversed()).limit(3)` for a finite dataset, while considering cost and tie-breaker policy.
- If you need the **first three transactions by arrival time**, use `limit(3)` with an ordered source; do not place `unordered()` beforehand if order is part of the contract.
- If you need to **read until an end marker is encountered**, `takeWhile` may fit an ordered Stream; do not replace it with `filter` because `filter` may continue keeping elements after the marker.

### 12.1. Define the Criteria Before Optimizing Operation Order

Stage order is part of the problem's meaning. For example:

~~~java
List<Integer> firstTwoPassing = values.stream()
        .filter(n -> n >= 4)
        .limit(2)
        .toList();
~~~

This means "the first two numbers matching the condition". Changing it to `limit(2).filter(...)` means "check only the first two numbers"; the result can differ. Pipeline optimization must not silently alter meaning.

### 12.2. When Should You Use a Loop Instead of a Stream?

A `for` loop can be clearer if the logic needs complex break/continue control, multiple mandatory ordered side effects, per-element transactions, or step-by-step error recovery. Streams are well suited for clear transformation and aggregation pipelines; they are not a mandatory replacement for every loop construct.

## 13. Common Mistakes and Fixes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Assuming stateless `map` means the lambda can safely mutate external state | Wrong order, race conditions, interference | Use pure lambdas or explicit state control |
| Using `filter` instead of `takeWhile` | Does not stop at the first failing element | Choose based on prefix vs. full-set requirement |
| Using `distinct` to deduplicate by a comparator | `distinct` relies on `equals` | Design equality or group by key |
| Using `sorted` to remove duplicates | Sorting does not remove equal elements | Add `distinct` when appropriate for the contract |
| Changing `sorted().limit(n)` to `limit(n).sorted()` | Changes the selected dataset | Only reorder if the problem allows it |
| Using `parallel().forEach` to verify order | Action does not guarantee encounter order | Use `toList` or `forEachOrdered` |
| Assuming an unordered source has a fixed "first element" | No guaranteed encounter order | Choose an ordered source or sort/tie-breaker |
| Adding `unordered()` for speed without checking requirements | Loses first-occurrence / first-n guarantees | Relax ordering only when not needed |
| Calling `sorted` on an infinite Stream then `limit` | May never return a result | Bound the source finitely before sorting |
| Calling `peek` to increment a business counter | Optimizations may skip the action | Handle mandatory business logic explicitly |
| Reusing an already consumed Stream | `IllegalStateException` or lifecycle violation | Create a new Stream |
| Writing comparator `a-b` on extreme int values | Can overflow and produce wrong order | Use `Integer.compare`/`comparingInt` |
| Running `sorted` unconditionally on huge datasets | May buffer heavily, run out of memory | Choose reduction/top-k/appropriate bounds |
| Mutating the source collection inside `map` | May throw errors and yield unreliable results | Do not interfere with the source in the pipeline |
| Believing parallel is always faster than sequential | High overhead, contention | Benchmark realistic workloads |

### 13.1. Comparators Must Satisfy Their Contract

`sorted(Comparator)` requires a comparator with a consistent comparison relation. If a comparator uses mutable values that change between comparisons, or is non-transitive, results become unreliable. Prefer:

~~~java
Comparator<Reading> byScore =
        Comparator.comparingInt(Reading::score);
~~~

This snippet assumes `Reading` is in scope and `Comparator` is imported. Avoid writing `(a,b) -> a.score() - b.score()` when subtraction can overflow.

### 13.2. `limit` and `skip` Require Non-Negative Numbers

~~~java
Stream.of("A", "B").limit(-1); // When the call executes, throws IllegalArgumentException.
Stream.of("A", "B").skip(-1);  // Same.
~~~

These are intentionally invalid examples. Per the Javadoc, the `maxSize`/`n` argument of `limit` and `skip` must be **non-negative**. When the value comes from input, validate it beforehand and report an appropriate error.

## 14. Practice Exercises

### Exercise 1 — Classify Operations

Group `map`, `filter`, `peek`, `flatMap`, `distinct`, `sorted`, `limit`, `skip`, `takeWhile`, and `dropWhile` into stateless and stateful. For each stateful operation, state one minimal piece of information it needs to know (previously seen elements, position, prefix, or total order).

### Exercise 2 — Predict `distinct` Output

Given `List.of(4, 2, 4, 3, 2, 5)`, compute the result of `stream().distinct().toList()`. **Answer:** `[4, 2, 3, 5]` because the source has an encounter order and `distinct` is stable on an ordered Stream.

### Exercise 3 — Reordering `sorted` and `limit`

Given `[9,1,7,2,5]`, compute `sorted().limit(2)` and `limit(2).sorted()`. **Answer:** `[1,2]` and `[1,9]` respectively. Explain why these represent two different requirements.

### Exercise 4 — `filter` vs. `takeWhile`

Given `[7,4,7,2,4,9]` and condition `n >= 4`, predict `filter`, `takeWhile`, and `dropWhile`. **Answer:** `filter` = `[7,4,7,4,9]`; `takeWhile` = `[7,4,7]`; `dropWhile` = `[2,4,9]`.

### Exercise 5 — Parallel Semantics

Use an ordered `List<Integer>` with duplicate elements. Compare `stream().distinct().toList()` and `parallelStream().distinct().toList()`. Explain why the result in encounter order must still be stable; then try `parallelStream().forEach(System.out::println)` and explain why stdout order is not guaranteed.

### Exercise 6 — Distinguish Stateless Operation from Stateful Lambda

Write a `map` using an external counter and run it in parallel; show why the counter values attached to elements can differ from source order. Fix it using `IntStream.range(0, list.size()).mapToObj(i -> ...)` if the data and numbering requirement allow.

### Exercise 7 — Unordered Source

Create a `HashSet<String>` and use `stream().distinct().limit(2)`. Explain why there is no contract for "the first two elements of a HashSet". Do not write a test expecting a specific pair of elements unless an appropriate ordering rule has been added.

### Exercise 8 — Infinite and Bounded

Compare `IntStream.iterate(1, n -> n+1).limit(10).sorted().toArray()` with `IntStream.iterate(1, n -> n+1).sorted().limit(10).toArray()`. Execute only the first version. Explain why the second version is inappropriate.

### Exercise 9 — Business Optimization

A system needs to compute the sum of scores of filtered records. Choose `filter` then `mapToInt(...).sum()` instead of `sorted(...).collect(...).stream().sum()` when ordering is not needed. Explain why omitting the stateful sort saves cost and does not change the sum result under appropriate conditions.

### Exercise 10 — Correctness of `peek`

Given `Stream.of("a","b","c").peek(log).count()`, explain why `log` cannot be guaranteed to run three times. Propose how to design mandatory logging as an explicit part of processing rather than an unguaranteed side effect in an intermediate operation.

## 15. Self-Check Questions

1. **What does stateless intermediate operation mean?** It does not need to retain information from other elements to process the current element.
2. **What does stateful intermediate operation mean?** It may need to remember previous elements, position, prefix, or overall data.
3. **What category are `filter` and `map`?** Stateless.
4. **What category are `distinct` and `sorted`?** Stateful.
5. **Are `limit`/`skip` stateful?** Yes, they depend on element position/count.
6. **Is `takeWhile` the same as `filter`?** No; on an ordered Stream it only takes the consecutive prefix matching the predicate.
7. **Does stateful mean keeping the entire Stream in RAM?** No; it depends on the operation.
8. **Does `sorted().limit(3)` always equal `limit(3).sorted()`?** No; the elements can differ.
9. **Does `distinct` use `equals` or a comparator?** It uses `equals` to determine duplicates on a reference Stream.
10. **Is `parallelStream` on a List still ordered?** Yes; parallel execution does not automatically remove encounter order.
11. **Why doesn't `parallel().forEach` help verify a sort result?** Side effects may execute out of encounter order.
12. **Is a `map` with a lambda modifying an external counter called a stateful operation?** The `map` operation itself remains stateless by API classification, but the lambda has state/side effects and violates the stateless behavior requirement.
13. **Can `peek` replace mandatory business logic that must run for every element?** It is unreliable, because it may be optimized away.
14. **Does `unordered()` randomly shuffle data?** No; it removes the ordering constraint.
15. **When should you prefer a terminal reduction over `sorted`?** When the goal is only a sum, count, or max/min and full sorting is unnecessary.

## 16. Project Application Checklist

- [ ] Have you clearly identified whether the Stream source is ordered or unordered?
- [ ] Does every `map`/`filter` lambda avoid mutating the source and shared state?
- [ ] Are you using `distinct` with the right `equals` criterion, or is the actual requirement "unique by key"?
- [ ] Is `sorted` truly necessary, or would `max/min` or a reduction suffice?
- [ ] Do `limit/skip/takeWhile/dropWhile` match the intended element-order semantics?
- [ ] Have you reordered any stages without comparing outputs on edge cases?
- [ ] Are you relying on side effects in `peek` or `map` to guarantee execution counts?
- [ ] Are you calling `sorted` before bounding an infinite or overly large source?
- [ ] If using parallel, have you measured the cost of stateful operations and eliminated shared mutable state?
- [ ] If calling `unordered()`, does the business requirement truly not need encounter order?
- [ ] Do tests compare collected data rather than relying on `println` order in parallel `forEach`?
- [ ] Have you tested empty inputs, heavy duplicates, inputs with no matching elements, and short-circuit cases?

## 17. Summary and References

**Stateless intermediate operations** such as `map`, `filter`, and `flatMap` can process each element without remembering the history of other elements. **Stateful intermediate operations** such as `distinct`, `sorted`, `limit`, `skip`, `takeWhile`, and `dropWhile` depend on previous elements, position, prefix, or the overall dataset. This classification explains why some pipelines process element-by-element easily, while others may require buffering or complex coordination.

Three principles to remember:

1. **Operation classification is distinct from lambda correctness.** `map` remains a stateless operation even if the author passes a lambda with side effects; that does not make stateful behavior safe.
2. **Operation order defines program semantics.** `sorted().limit(n)` is not equivalent to `limit(n).sorted()`, and `filter` does not mean `takeWhile`.
3. **Ordered/parallel/short-circuiting affect behavior and cost.** Do not rely on log order from parallel `forEach`, do not drop encounter order if keeping the first occurrence is required, and do not expect `limit` after `sorted` to rescue an infinite source.

For verification, read the **Java SE 17 Javadoc** for `java.util.stream.Stream` (`map`, `filter`, `flatMap`, `peek`, `distinct`, `sorted`, `limit`, `skip`, `takeWhile`, `dropWhile`, `forEach`, `forEachOrdered`), the `java.util.stream` package documentation on *stateless/stateful operations, non-interference, stateless behaviors, laziness, short-circuiting*, and `java.util.Spliterator` on `ORDERED`.
