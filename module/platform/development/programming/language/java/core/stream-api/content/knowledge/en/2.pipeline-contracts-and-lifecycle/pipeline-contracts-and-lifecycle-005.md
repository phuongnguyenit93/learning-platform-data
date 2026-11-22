# Encounter Order and Ordering Guarantees

In the Java Stream API, a pipeline can process elements sequentially or in parallel, yet **the execution order across threads** and **the element order that the result must obey** are two different issues. Understanding *encounter order* helps you use `filter`, `map`, `sorted`, `distinct`, `limit`, `collect`, and terminal operations in compliance with their contracts, especially when enabling `parallel()`.

This lesson belongs to the **Pipeline Contracts and Lifecycle** chapter of the **JAVA_STREAM_API** module. The focus is on processing data declaratively while still being able to determine when order is guaranteed, when order can change, and the performance cost of maintaining order.

## 1. What is encounter order?

**Encounter order** is the logical order in which elements are *encountered* in a stream, if that stream has a defined order. This order usually comes from the data source, though an intermediate operation like `sorted()` can also establish it.

Example:

```java
List<String> names = List.of("Lan", "Minh", "An");

List<String> result = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [LAN, MINH]
```

The `List` source has an encounter order of `Lan → Minh → An`. Both transformations `filter` and `map` preserve the relative order of the remaining elements; `toList()` creates a list in that encounter order.

It is important to distinguish three concepts:

| Concept | Meaning | Example |
|---|---|---|
| **Encounter order** | The logical order of elements in the stream | `List.of(3, 1, 2).stream()` has order `3, 1, 2` |
| **Execution order** | The order in which tasks run or finish across threads | `parallelStream()` may process `2` before `3` |
| **Result order** | The order that the terminal operation commits to exhibiting | `parallelStream().toList()` still returns `[3, 1, 2]` with the source above |

**Having an encounter order does not mean the stream is sorted.** The list `[3, 1, 2]` has a completely deterministic encounter order, even though it is not ascending.

## 2. Which sources are ordered?

Order is part of the source and pipeline contract; it cannot be inferred just because data "looks stable" during a test run.

| Stream source | Encounter order | Notes |
|---|---|---|
| `List`, array, `Arrays.stream(...)` | Yes | By element position |
| `LinkedHashSet` | Yes | By insertion order (unless removed/reinserted) |
| `TreeSet` | Yes | By `Comparator` order or natural order |
| `HashSet`, `HashMap.entrySet().stream()` | Not guaranteed | Do not rely on the order observed in a single traversal |
| `IntStream.range(0, n)` | Yes | In ascending order |
| `Stream.iterate(...)` | Yes | By element generation sequence |
| `Stream.generate(...)` | No | Generated elements have no defined encounter order |

At a lower level, `Spliterator.ORDERED` indicates a source has a defined encounter order; `Spliterator.SORTED` provides additional information about sorted order. A pipeline can also alter ordering constraints via `sorted()` or `unordered()`.

```java
System.out.println(
        List.of(8, 3, 5).stream().toList()
); // [8, 3, 5] — ordered, unsorted

System.out.println(
        List.of(8, 3, 5).stream().sorted().toList()
); // [3, 5, 8] — sorted
```

With `HashSet`, if one run happens to yield the same order multiple times, that **does not constitute a guarantee**. When insertion order is needed, use `LinkedHashSet`; when comparison order is needed, use `TreeSet` or sort explicitly in the pipeline.

## 3. How do intermediate operations affect order?

Most intermediate operations are *lazy*: they describe the pipeline and are only executed when a terminal operation requests data. However, each operation has its own contract regarding encounter order.

| Operation | Key guarantee for ordered streams |
|---|---|
| `filter(predicate)` | Preserves the relative order of retained elements |
| `map(mapper)` | Preserves relative position when transforming each element |
| `sorted()`, `sorted(comparator)` | Establishes encounter order in sorted order; *stable* when the input is ordered |
| `distinct()` | For ordered input, retains the first occurrence of each distinct value by `equals` |
| `limit(n)` | Selects at most the first `n` elements |
| `skip(n)` | Skips the first `n` elements |
| `takeWhile(predicate)` | Takes the longest contiguous prefix still satisfying the condition |
| `dropWhile(predicate)` | Drops the longest contiguous prefix still satisfying the condition |
| `unordered()` | Removes the encounter order constraint for the subsequent part of the pipeline |
| `parallel()`, `sequential()` | Chooses execution mode; by themselves they do not remove or create encounter order |

### 3.1. `sorted()` creates an order, even when the original source is unordered

```java
List<Integer> lowest = List.of(7, 3, 5, 1, 9, 2)
        .parallelStream()
        .sorted()
        .limit(3)
        .toList();

System.out.println(lowest); // [1, 2, 3]
```

Here `sorted()` establishes ascending order before `limit(3)` selects the first three elements. Order is guaranteed even though the pipeline runs in parallel.

With a comparator that allows two elements to compare equal in sort order, `sorted` is **stable if the input is ordered**: elements considered equal by the comparator preserve their original relative order.

```java
record Task(int priority, String id) {}

List<String> ids = List.of(
        new Task(2, "A"),
        new Task(1, "B"),
        new Task(2, "C")
).stream()
 .sorted(Comparator.comparingInt(Task::priority))
 .map(Task::id)
 .toList();

System.out.println(ids); // [B, A, C]
```

Both tasks with priority `2` remain in the order `A` then `C`. With **unordered input**, this stability is not guaranteed. If reproducible results are needed even when primary keys tie, add a secondary key, for example `thenComparing(Task::id)`.

### 3.2. `distinct()` and the notion of "first element"

```java
List<String> unique = List.of("A", "B", "A", "C", "B")
        .parallelStream()
        .distinct()
        .toList();

System.out.println(unique); // [A, B, C]
```

When the stream is ordered, `distinct()` removes duplicates and retains the element appearing first in encounter order. This also matters for distinct objects considered equal by `equals`. With an unordered stream, `distinct()` makes no commitment as to which representative among duplicate elements is kept.

### 3.3. `limit`, `skip`, `takeWhile`, `dropWhile` are not like `filter`

```java
List<Integer> values = List.of(2, 4, 5, 6, 8);

System.out.println(values.stream().filter(n -> n % 2 == 0).toList());
// [2, 4, 6, 8]

System.out.println(values.stream().takeWhile(n -> n % 2 == 0).toList());
// [2, 4]

System.out.println(values.stream().dropWhile(n -> n % 2 == 0).toList());
// [5, 6, 8]

System.out.println(values.stream().skip(2).limit(2).toList());
// [5, 6]
```

`takeWhile` takes only the **contiguous prefix** matching the condition; upon encountering `5` it stops taking, even though `6` and `8` are still even. `dropWhile` drops only that prefix. This is a contractual difference, not merely an optimization.

With an **unordered** stream:

- `limit(n)` is permitted to select any `n` elements if enough elements exist;
- `skip(n)` is permitted to skip any `n` elements;
- `takeWhile(predicate)` may take an arbitrary subset of elements matching the condition (the case where all elements match has its own rule);
- `dropWhile(predicate)` may drop an arbitrary subset of elements matching the condition.

Therefore, `unordered().takeWhile(...)` does not have the same meaning as "take until the first element failing the condition is encountered". The `takeWhile` and `dropWhile` operations were introduced in Java 9.

## 4. Terminal operations: not every operation preserves output order

A pipeline having an encounter order does not mean **every** terminal operation must execute in or expose that order.

| Terminal operation | Ordering contract |
|---|---|
| `toList()`, `toArray()` | Produces results in encounter order if the stream is ordered |
| `collect(Collectors.toList())` | Accumulates in encounter order when the source is ordered |
| `findFirst()` | Selects the first element in encounter order, if present; with an unordered stream may pick any |
| `findAny()` | Permitted to pick any element, especially useful for parallel processing |
| `forEach(action)` | Does not guarantee action execution order, even with an ordered source |
| `forEachOrdered(action)` | Executes actions in encounter order if the stream is ordered |
| `count()`, `sum()`, `anyMatch()` | Result value does not carry element order |
| `collect(Collectors.toSet())` | Collector is `UNORDERED`; makes no guarantee about traversal order of the resulting `Set` |

Example with `findFirst` and `findAny`:

```java
List<Integer> values = List.of(10, 20, 30, 40);

System.out.println(values.parallelStream().findFirst().orElseThrow());
// 10

System.out.println(values.parallelStream().findAny().orElseThrow());
// Any element in [10, 20, 30, 40]
```

Even if `findAny()` often returns a familiar value on your machine, do not write logic that depends on that value.

### 4.1. `forEach` differs from `forEachOrdered`

```java
List<Integer> values = List.of(1, 2, 3, 4, 5);

values.parallelStream().forEach(n -> System.out.print(n + " "));
// Print order is not guaranteed

System.out.println();

values.parallelStream().forEachOrdered(n -> System.out.print(n + " "));
// 1 2 3 4 5
```

`forEachOrdered` guarantees actions occur in encounter order; in a parallel stream, the action for an earlier element has a *happens-before* relationship with the action for a later element. Even so, actions do not necessarily run on the same thread.

If the goal is to **collect results**, prefer `toList()` or `collect(...)` instead of adding elements to an external `ArrayList` via `forEach`. A shared `ArrayList` risks race conditions in a parallel pipeline; even thread-safe structures do not automatically guarantee element insertion order.

## 5. Parallel streams: parallel does not mean losing encounter order

Consider the pipeline:

```java
List<Integer> input = List.of(5, 2, 4, 1, 3);

List<Integer> result = input.parallelStream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * 10)
        .toList();

System.out.println(result); // [50, 10, 30]
```

Tasks may process `1` before `5` on different threads. Even so, `toList()` must return `[50, 10, 30]` following the encounter order of the retained elements. Replacing `toList()` with `forEach(System.out::println)` loses the guarantee on print order.

Maintaining order can reduce the benefit of parallelism for certain operations:

- `distinct()` on an ordered stream must determine which duplicate element appeared first.
- `limit()` and `skip()` on an ordered stream must select or skip the exact leading elements.
- `takeWhile()` and `dropWhile()` on an ordered stream must determine the prefix, which can limit work-splitting efficiency.
- `forEachOrdered()` must coordinate the order of actions instead of letting them run completely freely.

This does **not** mean dropping order is always faster: actual cost also depends on data size, operations, and hardware. Measure performance with representative data before changing the contract.

### 5.1. Use `unordered()` when order genuinely does not matter

```java
List<Integer> anyThree = List.of(10, 20, 30, 40, 50, 60)
        .parallelStream()
        .unordered()
        .limit(3)
        .toList();

System.out.println(anyThree); // Any 3 values; no guarantee of [10, 20, 30]
```

`unordered()` **does not shuffle data**. It only removes the ordering constraint, giving subsequent operations more execution choices. The output *may* still happen to be `[10, 20, 30]`; that is simply no longer a guarantee of the pipeline.

If the business requirement asks for "the first three orders", do not add `unordered()`. If the requirement is only "any three samples for testing", removing the ordering constraint may be reasonable.

### 5.2. Collector ordering and output data structures

When using `collect`, you must consider **all of** the stream's encounter order, `Collector.Characteristics`, and the target structure:

```java
List<String> words = List.of("a", "bb", "c", "ddd");

// List preserves encounter order.
List<String> list = words.parallelStream()
        .collect(Collectors.toList());
// [a, bb, c, ddd]

// The default Map of groupingBy does not guarantee key traversal order.
Map<Integer, List<String>> groups = words.stream()
        .collect(Collectors.groupingBy(String::length));

// Requirement to maintain key insertion order: use LinkedHashMap with a sequential stream.
Map<Integer, List<String>> orderedGroups = words.stream()
        .collect(Collectors.groupingBy(
                String::length,
                LinkedHashMap::new,
                Collectors.toList()
        ));
// Key order: 1 -> [a, c], 2 -> [bb], 3 -> [ddd]
```

Ordinary `groupingBy` does not guarantee the `Map` type or key traversal order if no `mapFactory` is specified. With an ordered source, the list inside each group collected via `toList()` preserves encounter order within the group. When predictable key insertion order is needed, the example above uses `LinkedHashMap` **and** a sequential stream.

`groupingByConcurrent(...)` is a collector carrying `CONCURRENT` and `UNORDERED` characteristics; suitable when preserving encounter order within groups is not needed. `toSet()` also carries the `UNORDERED` characteristic. Do not infer ordering just from the printed output of a single run of `HashMap`, `HashSet`, or default `toMap(...)`.

Version note: `Stream.toList()` has existed since Java 16 and returns an unmodifiable list; `Collectors.toList()` makes no guarantee about list type or mutability. If a mutable `ArrayList` result is needed, use `collect(Collectors.toCollection(ArrayList::new))`.

## 6. Ordering contracts tied to the pipeline lifecycle

A Stream is described by the chain **source → intermediate operations → terminal operation**:

```text
List (ORDERED)
    |
    v
filter(...)    -- preserves relative order
    |
    v
parallel()     -- changes execution mode, does not remove ORDERED
    |
    v
sorted(...)    -- establishes encounter order according to comparator
    |
    v
limit(3)       -- takes first three elements in current order
    |
    v
toList()       -- returns list in encounter order
```

Intermediate operations are usually lazy; only when a terminal operation runs does the pipeline consume the source. Each Stream is intended for **one consumption only**; to run a pipeline with another terminal operation, create a new stream from the source:

```java
List<Integer> source = List.of(3, 1, 2);

List<Integer> ascending = source.stream().sorted().toList();
Optional<Integer> first = source.stream().findFirst();

System.out.println(ascending);             // [1, 2, 3]
System.out.println(first.orElseThrow());    // 3
```

Do not reuse the same `Stream` instance after a terminal operation. For resource-backed sources like `Files.lines(path)`, use `try-with-resources` to close the stream; ordering guarantees do not replace the obligation to release resources.

Besides order, lambdas in a pipeline should be **non-interfering with the source** and **not rely on shared mutable state**. Guaranteed result order does not prove that side effects in `map`, `peek`, or `forEach` run in a particular order or the expected number of times; optimizations and terminal operations can cause parts of the pipeline not to execute.

## 7. Common mistakes and how to handle them

| Coding pattern or assumption | Problem | Appropriate approach |
|---|---|---|
| "`parallel()` causes `toList()` to lose order" | Confusing processing time with encounter order | Read the terminal operation's contract; `toList()` preserves encounter order of an ordered source |
| "`forEach` will print in `List` order" | `forEach` does not guarantee action order | Use `forEachOrdered`, or collect into a `List` if data is needed |
| "`unordered()` will shuffle elements" | `unordered` only removes the constraint | Use an explicit shuffle mechanism if shuffling is genuinely required |
| "`HashSet.stream().findFirst()` always picks element X" | The source has no encounter order | Choose an ordered source or `sorted()` before `findFirst()` |
| "`takeWhile` is equivalent to `filter`" | `takeWhile` only considers the contiguous prefix on an ordered source | Use `filter` to evaluate each element independently |
| "`groupingBy` automatically preserves key order" | Default `Map` type and traversal order are not guaranteed | Specify `LinkedHashMap::new` and execute sequentially when key insertion order matters |
| "Ordered result means lambdas are thread-safe" | Result guarantees do not protect shared mutable state | Use pure transformations and appropriate collectors |

## 8. Complete runnable example

The following example requires Java 17 or later, so the commented results can be verified:

```java
import java.util.List;

public class EncounterOrderDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(5, 2, 4, 1, 3);

        // Parallel, yet the result still follows encounter order.
        System.out.println(source.parallelStream()
                .filter(n -> n % 2 != 0)
                .map(n -> n * 10)
                .toList());                         // [50, 10, 30]

        // sorted() establishes ascending order before limit().
        System.out.println(source.parallelStream()
                .sorted()
                .limit(3)
                .toList());                         // [1, 2, 3]

        // findFirst() selects the first element of an ordered source.
        System.out.println(source.parallelStream()
                .findFirst()
                .orElseThrow());                    // 5

        // Actions are executed in encounter order.
        source.parallelStream()
                .forEachOrdered(n -> System.out.print(n + " ")); // 5 2 4 1 3
        System.out.println();
    }
}
```

## 9. Self-check

1. For `List.of(9, 2, 7, 2).parallelStream().distinct().toList()`, what is the result order? **Answer:** `[9, 2, 7]` because the source is ordered and `distinct` keeps the first occurrence.
2. For `List.of(9, 2, 7, 2).parallelStream().unordered().limit(2).toList()`, can you assert the result is `[9, 2]`? **No.** That result may occur, but it is not guaranteed.
3. To select the smallest element in `List.of(8, 3, 5)`, can you use `findFirst()` directly? **No**, because the initial encounter order is `8, 3, 5`. Use `min(Integer::compareTo)` or `sorted().findFirst()` if sorted order needs to be considered.
4. To preserve order in the result of a parallel pipeline, is it mandatory to switch back to `sequential()`? **No.** With an ordered source, terminal operations such as `toList()`, `toArray()`, and `forEachOrdered()` provide appropriate guarantees.

**Rule of thumb:** determine whether the source has an encounter order, examine whether intermediate operations preserve or alter it, and then check the terminal operation's contract. Remove the constraint with `unordered()` only when the business logic truly does not require order.
