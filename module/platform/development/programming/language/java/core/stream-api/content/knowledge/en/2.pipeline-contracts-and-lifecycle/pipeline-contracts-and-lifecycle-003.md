# Distinguishing Stateless and Stateful Operations

> **Chapter:** Pipeline Contracts and Lifecycle  
> **Module:** `JAVA_STREAM_API` — learn how to process data declaratively through lazy pipelines, `filter`, `map`, `reduce`, `collect`, and advanced techniques.

When reading a Stream pipeline, we often pay attention to **what the data is transformed into**. However, to predict how many elements a pipeline will process, how much memory it needs, and whether it can short-circuit, you must know whether an *intermediate operation* is **stateless** or **stateful**.

This distinction is foundational for writing understandable pipelines, avoiding redundant processing, using parallel Streams appropriately, and continuing to learn `reduce`, `collect`, `groupingBy`, custom collectors, `Spliterator`, or Stream Gatherers.

## 1. Context: pipelines and intermediate operations

A Stream pipeline typically consists of three parts:

```text
Data source    →  intermediate operations  →  terminal operation
List / Set        filter / map / sorted       toList / collect / count
                  distinct / limit / ...      reduce / findFirst / ...
```

Example:

```java
List<Integer> result = List.of(5, 1, 5, 2, 3).stream()
        .filter(n -> n > 1)   // intermediate
        .map(n -> n * 2)      // intermediate
        .distinct()           // intermediate
        .toList();            // terminal; Java 16+

// result = [10, 4, 6]
```

An intermediate operation produces a new Stream describing the next processing step. **These steps are usually lazy**: declaring `filter`, `map`, or `sorted` does not automatically run through the entire source. Traversing the source begins when there is a terminal operation, unless the Stream implementation can optimize and skip certain steps that do not affect the result.

Two concepts must be kept separate:

- **Stateless/stateful** describes the extent to which a processing step needs to know or store information from other elements.
- **Lazy/eager** describes when the work is performed. Both `map()` and `sorted()` are lazy intermediate operations; yet when the pipeline runs, they process data very differently.

## 2. Definitions and identifying signs

### Stateless intermediate operations

A **stateless** operation can decide how to process each element without having to remember previously encountered elements or wait to see all the data. The result for the current element depends only on that element and the operation's immutable parameters.

Example:

```java
numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n);
```

`filter` checks whether each number is even; `map` squares each number. Given the input `8`, neither step needs to ask which numbers were seen previously. Streams can typically fuse steps so that each element passes through `filter` and then `map` sequentially, rather than creating an intermediate list for each step.

### Stateful intermediate operations

A **stateful** operation needs to track information about already-processed elements, position in the stream, or even the collection of elements before deciding the output.

Example:

```java
numbers.stream()
        .distinct()
        .sorted()
        .limit(3);
```

- `distinct()` needs to recognize values that have already appeared in order to remove duplicates.
- `sorted()` needs to consider the ordering of values; with an unsorted source, outputting the smallest element generally requires inspecting the remaining elements.
- `limit(3)` needs to track how many elements have been forwarded so it can stop once three elements are reached.

**Stateful does not mean storing all data.** `limit(3)` only needs to track progress in the normal sequential case, whereas `sorted()` usually has to retain many elements in order to sort.

## 3. Classification table of common operations

| Intermediate operation | Type | What does it need to remember? | Notes |
| --- | --- | --- | --- |
| `filter(predicate)` | Stateless | Does not need to remember other elements | Keeps or discards the current element. |
| `map(mapper)`, `mapToInt(...)` | Stateless | Does not need to remember other elements | Transforms each element individually. |
| `flatMap(mapper)`, `mapMulti(...)` | Stateless | Does not need to remember other *source* elements | One input can produce zero, one, or many outputs. |
| `peek(action)` | Stateless | Needs no state to decide data flow | Mainly used for observation/debugging; do not rely on `peek` side effects. |
| `distinct()` | Stateful | Values already encountered or equivalent structure | Can consume memory proportional to the number of distinct values. |
| `sorted()`, `sorted(comparator)` | Stateful | Information to determine overall order | Usually a step that requires buffering data. |
| `limit(n)` | Stateful | How many elements have been forwarded | Capable of *short-circuiting*: stops early once enough outputs are produced. |
| `skip(n)` | Stateful | How many elements have been skipped | Requires special care on ordered parallel streams. |
| `takeWhile(predicate)` | Stateful | Whether currently within the initial contiguous matching prefix | Java 9+; on ordered streams, stops at the first non-matching element. |
| `dropWhile(predicate)` | Stateful | Whether the initial contiguous matching prefix has been passed | Java 9+; after the state transition point, keeps all remaining elements. |

Here, "stateless" describes **the contract of the Stream operation with properly written functions**. It does not mean every lambda passed to `map`/`filter` is safe if it arbitrarily reads and mutates shared variables; that issue is analyzed in section 8.

## 4. Execution example: changing order changes the result

Run the following Java 17+ program to observe both groups of operations on the same source:

```java
import java.util.List;

public class StreamStateDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(5, 1, 5, 2, 3);

        // map and filter: independent decisions per element.
        System.out.println(numbers.stream()
                .map(n -> n * 2)
                .filter(n -> n > 2)
                .toList());

        // distinct needs to remember seen numbers; limit needs to count taken numbers.
        System.out.println(numbers.stream()
                .distinct()
                .limit(3)
                .toList());

        // Take three elements first, then deduplicate.
        System.out.println(numbers.stream()
                .limit(3)
                .distinct()
                .toList());

        // Sort the entire source, then take the three smallest numbers.
        System.out.println(numbers.stream()
                .sorted()
                .limit(3)
                .toList());

        // Sort only the first three elements of the source.
        System.out.println(numbers.stream()
                .limit(3)
                .sorted()
                .toList());
    }
}
```

Output:

```text
[10, 10, 4, 6]
[5, 1, 2]
[5, 1]
[1, 2, 3]
[1, 5, 5]
```

From the example, important conditions can be drawn:

1. `distinct().limit(3)` finds the **first three distinct values** according to the encounter order of an ordered source. If there are duplicates, it may have to read more than three elements to collect three values.
2. `limit(3).distinct()` looks only at the **first three elements**, so it may return fewer than three values.
3. `sorted().limit(3)` takes the **three smallest values** on an unsorted finite source; knowing what they are usually requires inspecting the entire source.
4. `limit(3).sorted()` sorts only the **first three elements taken**, so it does not guarantee those are the three smallest values of the source.

Therefore, never arbitrarily swap stateful operations just to make a pipeline look cleaner.

## 5. How does `filter` differ from `takeWhile` and `dropWhile`?

All three operations accept a `Predicate<T>`, yet their semantics are very different:

```java
List<Integer> values = List.of(2, 4, 1, 6, 8);

List<Integer> a = values.stream()
        .filter(n -> n % 2 == 0)
        .toList();
// [2, 4, 6, 8]

List<Integer> b = values.stream()
        .takeWhile(n -> n % 2 == 0)
        .toList();
// [2, 4]

List<Integer> c = values.stream()
        .dropWhile(n -> n % 2 == 0)
        .toList();
// [1, 6, 8]
```

- `filter`: for **each element**, evaluates the condition independently and keeps matching elements regardless of their position.
- `takeWhile`: on an ordered Stream, keeps only the **initial contiguous segment** satisfying the condition; when encountering `1`, this segment ends.
- `dropWhile`: on an ordered Stream, discards the **initial contiguous segment** satisfying the condition; from `1` onward it keeps `1`, `6`, and `8`, even though some subsequent numbers are still even.

To understand the two `*While` operations, you must know whether elements **have already crossed the boundary point**. This is state of the traversal process, unlike the independent check of `filter`.

## 6. Laziness, element-by-element processing, and short-circuiting

Consider a sequential pipeline with an ordered source:

```java
List<Integer> firstTwo = List.of(5, 1, 4, 2, 3).stream()
        .filter(n -> n > 1)
        .map(n -> n * 10)
        .limit(2)
        .toList();

// [50, 40]
```

Logically, the `filter` and `map` steps can process elements one by one: `5` passes through and produces `50`; `1` is discarded; `4` produces `40`; `limit(2)` now has enough (two) results so the pipeline can stop without needing to process `2` and `3`. This kind of coordination is often called **fusion**: multiple intermediate operations are executed within the same traversal pass.

If `sorted()` is inserted before `limit(2)`:

```java
List<Integer> smallest = List.of(5, 1, 4, 2, 3).stream()
        .sorted()
        .limit(2)
        .toList();

// [1, 2]
```

In the general case, `sorted()` must examine every element before knowing the first two elements in ascending order. **`limit(2)` is still a short-circuiting operation, but it cannot force the preceding `sorted()` to skip the rest of the source.**

This is especially important with infinite sources:

```java
// Can terminate: only needs three elements.
List<Integer> ok = java.util.stream.Stream.generate(() -> 7)
        .limit(3)
        .toList();

// Cannot terminate on an infinite source like this:
// java.util.stream.Stream.generate(() -> 7)
//         .sorted()
//         .limit(3)
//         .toList();
```

A terminal call such as `count()` or `findFirst()` can also trigger different optimizations, depending on source characteristics (`SIZED`, `SORTED`, `DISTINCT`, ...) and the implementation. Therefore, **do not use the number of times `peek()` is called as fixed proof of the amount of work** across all pipelines: `peek` may not run for elements skipped by optimization.

## 7. State, memory, and parallel processing

There is no single cost level for all stateful operations:

| Group | Typical state in sequential processing | Practical impact |
| --- | --- | --- |
| `filter`, `map` | No need to remember other elements | Usually processed element by element, small auxiliary memory overhead. |
| `distinct` | Set of seen values; usually proportional to the number of distinct values | Can increase memory usage when the source is large or has many distinct values. |
| `sorted` | Buffer to sort the elements | Usually costs memory proportional to element count plus sorting cost; be cautious with very large sources. |
| `limit`, `skip` | Counter or positional information | Can be very compact sequentially; with ordered parallel streams, coordinating branches can be costly. |
| `takeWhile`, `dropWhile` | State before/after the initial segment boundary | Must respect boundaries in order, making ordered parallel execution harder to scale. |

The levels above are a **mental model**, not a guarantee of exact data structures or absolute complexity: Java can apply optimizations based on `Spliterator`, source characteristics, and Stream type. For example, a source that already reports `SORTED` can allow the implementation to avoid unnecessary sorting work.

With parallel Streams, pay attention to the **encounter order** of the source:

- On an ordered source like `List`, `limit(10)`, `skip(10)`, `takeWhile(...)`, and `dropWhile(...)` must preserve order-related semantics; coordination across parallel branches can be expensive.
- If order **does not matter for business logic**, consider `.unordered()` before certain stateful operations to give the implementation more flexibility. `.unordered()` does not mean randomly shuffling data; it only removes the requirement to preserve encounter order.
- Once the ordering requirement is removed, `limit(n)` no longer guarantees taking the **first n elements of the original list**; `takeWhile`/`dropWhile` also no longer have prefix-segment semantics as on an ordered source. Use only when the application accepts that outcome.
- `parallel()` does not guarantee being faster: the overhead of splitting, merging results, and managing state can exceed the parallelized work.

Example using `unordered()` only when the goal is **taking any 100 elements**:

```java
List<Integer> sample = hugeList.parallelStream()
        .unordered()
        .limit(100)
        .toList();

// Not guaranteed to be the first 100 elements of hugeList.
```

If the application needs stable data pages, exact top-N, or order-reproducible results, preserve encounter order and prioritize clear algorithm design before considering parallelism.

## 8. Do not confuse operation state with self-created lambda state

`filter()` is a **stateless operation**, yet one can still write a **stateful lambda that violates the Stream contract**:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger();

List<String> unreliable = names.parallelStream()
        .filter(name -> counter.incrementAndGet() % 2 == 0)
        .toList();
```

This example attempts to pick "every second element" using a shared counter. Even though `AtomicInteger` prevents lost updates, the order in which lambdas execute in `parallelStream()` does not necessarily match the order of `names`, so **the selected names can change between runs**. Using a mutable `int` variable from multiple threads also causes data races.

If the requirement is truly to select elements at even indices of a `List` that supports efficient indexed access, express the rule using indices:

```java
import java.util.stream.IntStream;

List<String> evenIndexNames = IntStream.range(0, names.size())
        .filter(i -> i % 2 == 0)
        .mapToObj(names::get)
        .toList();
```

The condition `i % 2 == 0` is independent for each index, making it well-defined and deterministic. For linked lists without efficient random access, consider another traversal approach to avoid high `get(i)` cost.

Functions passed to `map`, `filter`, `sorted(comparator)`, and other operations generally need to be **non-interfering** with the source, while avoiding dependence on external mutable state. Do not modify the source collection while the pipeline is running; do not use `peek` or lambda side effects as a data accumulation mechanism. When aggregation is needed, use an appropriate terminal operation such as `reduce()` or `collect()`.

**Note:** `reduce()` and `collect()` can accumulate state, but they are **terminal operations**, not part of the *intermediate operations* classification table above. For example, `collect(groupingBy(...))` builds stateful groups during collection; that is a different aspect from `distinct()` or `sorted()`.

## 9. How to decide when building a pipeline

When choosing and ordering operations, ask yourself the following questions:

1. **Does each output depend on other elements?** If not, prefer expressing it with `filter`, `map`, `flatMap`, or `mapMulti`. If so, clearly identify whether it needs to remember seen values, position, boundaries, or global order.
2. **Is exact encounter order required?** `distinct().limit(n)` and `limit(n).distinct()` are different; `takeWhile` and `filter` are also different. Do not reorder steps without proving the results are equivalent.
3. **Can it short-circuit?** Place appropriate element-filtering conditions before resource-heavy steps if semantics allow. `sorted().limit(n)` usually still has to process the entire source, whereas a sequential `filter().limit(n)` can stop once enough results are found.
4. **Is the source large, infinite, or running in parallel?** Be careful with `sorted`, `distinct`, and order-boundary operations. Prefer measuring with representative data if performance is a key requirement.
5. **Does the lambda read/write shared state?** If so, look for a pure functional expression or use a compliant collector/reduction instead of mixing side effects into the pipeline.

## 10. Self-check

**Question 1.** Why is `limit(5)` stateful even though it does not need to store five elements?  
**Answer:** Because it must remember how many elements have been forwarded to know when to stop. *Stateful* describes dependence on processing progress, not necessarily storing all elements.

**Question 2.** For `[2, 4, 1, 6]`, how do `filter(n -> n % 2 == 0)` and `takeWhile(n -> n % 2 == 0)` differ?  
**Answer:** `filter` returns `[2, 4, 6]`; `takeWhile` returns `[2, 4]` because it stops at the first non-matching element `1`.

**Question 3.** Why does `numbers.stream().sorted().limit(3)` not guarantee reading only three source elements?  
**Answer:** To know the three smallest elements in an unsorted source, `sorted` usually needs to inspect all elements; the trailing `limit` only restricts the output.

**Question 4.** Does `filter()` itself become a stateful intermediate operation if its lambda increments a shared counter?  
**Answer:** No. `filter` is still defined as a stateless intermediate operation; that lambda introduces external state dependence on its own, which can make results nondeterministic or wrong in parallel.

## Key takeaway

- **Stateless:** processes the current element independently of other elements (`filter`, `map`, `flatMap`).
- **Stateful:** needs to remember seen values, position, boundaries, or global order (`distinct`, `sorted`, `limit`, `skip`, `takeWhile`, `dropWhile`).
- **Both can be lazy:** the main difference appears when running the pipeline, in how the source is traversed, short-circuiting capability, memory cost, and parallel execution.
- **Correctness before optimization:** changing the order of operations can change the result; do not use lambda side effects to replace contract-compliant aggregation operations.
