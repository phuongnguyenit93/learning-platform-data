# Ordering in Parallel Streams: forEachOrdered(), findFirst(), unordered()

## 1. The Core Question: Does Parallel Processing Still Have Order?

A Java Stream can run **sequentially** (`sequential()`) or **in parallel** (`parallel()` / `Collection.parallelStream()`). A parallel stream splits work into multiple parts and allows those parts to be computed concurrently. Therefore, **the moment an element is processed** does not necessarily match **the element's position in the source data**.

However, calling `parallel()` does not automatically discard all ordering. The Stream API makes clear distinctions:

- **Encounter order:** the logical order in which elements are "encountered" in the source and through the pipeline, if the pipeline defines such an order. For example, `List.of("A", "B", "C")` has an encounter order of `A → B → C`.
- **Execution order:** the timing and thread executing the operation on each element. With a parallel stream, the operation on `C` may run before `A`.
- **Result order:** the order in the final result, which depends on the source, intermediate operations, and terminal operation; it cannot be inferred solely from the use of multiple threads.
- **Ordering constraint:** a constraint that the Stream API must respect. This constraint may require some parallel operations to coordinate, wait, reorder results, or buffer data.

This article focuses on three APIs:

1. `forEachOrdered()`: executes the final action in encounter order **if the stream has a defined order**.
2. `findFirst()`: selects the first element according to encounter order **if present**.
3. `unordered()`: drops the requirement to preserve encounter order, which can allow parallel optimizations in suitable pipelines.

These APIs are part of the **pure Java Stream API**; the discussion does not depend on any framework.

## 2. Where Does Encounter Order Come From?

### 2.1. Ordered Sources vs. Unordered Sources

Common sources **with an encounter order**:

- `List`: positional order of elements in the list.
- Arrays via `Arrays.stream(...)`: index order.
- `IntStream.range(start, end)`: ascending from `start` up to (but excluding) `end`.
- `Stream.of(...)`: in the order of the arguments.
- `LinkedHashSet`: in the iteration order of that set.

Sources **without a guaranteed encounter order**:

- `HashSet`: has no contract to maintain insertion order or any specific order.
- `Stream.generate(...)`: an infinite, unordered stream source.
- Certain custom sources/spliterators implemented by libraries or applications that do not declare the `ORDERED` characteristic.

A `HashSet` might **print the exact same order** across multiple test runs; that observation does not turn the order into an API contract. You should not write tests that rely on an observed accidental order.

### 2.2. Intermediate Operations Can Preserve, Introduce, or Drop Order

With an ordered source, ordinary `map` and `filter` operations preserve the **relative logical order** of the remaining elements. For example, filtering even numbers from `[5, 2, 4, 1]` yields `[2, 4]`, even if evaluating the predicate on elements runs concurrently.

Several operations directly affect ordering:

| Operation | Effect on encounter order |
|---|---|
| `map()` / `filter()` | Typically preserves the defined relative order |
| `sorted()` | Establishes order by value or comparator; for equal elements, stability must be considered |
| `unordered()` | Drops the encounter order constraint; **does not sort or shuffle** |
| `distinct()` | If ordered, retains the first occurrence of each value; if unordered, there is no guarantee which occurrence is chosen when values are equal |
| `limit(n)` / `skip(n)` | For an ordered stream, "the first n elements" has a clear meaning; for an unordered stream, selection/skipping does not need to follow a fixed prefix |
| `takeWhile()` / `dropWhile()` | For an ordered stream, processes a contiguous prefix; for an unordered stream, the subset semantics differ and may be non-deterministic |

**Two dimensions to keep separate:** `parallel()` controls the **execution mode**; `unordered()` controls the **ordering guarantee**. A stream can be both `parallel` and `ordered`, or `sequential` yet `unordered`.

## 3. forEach() and forEachOrdered(): Why Can the Two Results Differ?

Both are **terminal operations**, meaning they end the pipeline and consume the stream. The difference lies in the ordering guarantee of the **final action**:

- `forEach(action)`: for a parallel stream, makes no commitment to respect encounter order. The library may execute the action on different threads and at different times; run A and run B may print in different orders.
- `forEachOrdered(action)`: if the stream has an encounter order, the action is performed **in that exact order**, one element at a time. The API guarantees that the action for an earlier element **happens-before** the action for a subsequent element.
- `forEachOrdered` does not state that every action must run on **the same thread**; the JVM is allowed to choose a different thread for each element.
- **Upstream processing** (`map`, `filter`, etc.) can still run in parallel. `forEachOrdered` constrains the **observable order of the final action**, without turning the entire pipeline into a sequential stream.

### Example 1: Deterministic Result with forEachOrdered

**File `OrderedTerminal.java` (Java 17+):**

```java
import java.util.List;

public class OrderedTerminal {
    public static void main(String[] args) {
        List<String> letters = List.of("D", "B", "A", "C");

        System.out.print("ordered actions: ");
        letters.parallelStream()
                .map(String::toLowerCase)
                .forEachOrdered(letter -> System.out.print(letter + " "));
        System.out.println();

        System.out.println("ordered result: " +
                letters.parallelStream()
                        .map(String::toLowerCase)
                        .toList());
    }
}
```

Commands:

```bash
javac OrderedTerminal.java
java OrderedTerminal
```

Exact stdout:

```text
ordered actions: d b a c 
ordered result: [d, b, a, c]
```

The trailing space on the first line is intentionally printed by `System.out.print(letter + " ")`. `List` has encounter order `D, B, A, C`; `map` converts to lowercase without changing the logical order. For an ordered stream, `Stream.toList()` (Java 16+) preserves encounter order in the result.

**If you replace `forEachOrdered` with `forEach`**, the letters are still processed, but **the order in which they appear on screen is not guaranteed**. You cannot write a fixed expected stdout string for parallel `forEach`, even on a multi-CPU machine.

### Example 2: Do Not Try to Assert Non-Deterministic Order

**File `UnorderedPrint.java` (Java 17+):**

```java
import java.util.stream.IntStream;

public class UnorderedPrint {
    public static void main(String[] args) {
        IntStream.rangeClosed(1, 8)
                .parallel()
                .forEach(value -> System.out.print(value + " "));
        System.out.println();
    }
}
```

Run:

```bash
javac UnorderedPrint.java
java UnorderedPrint
```

One run **might** print `6 5 8 7 3 2 1 4`, or another permutation, or even `1 2 3 4 5 6 7 8`. **No fixed stdout is guaranteed**. `forEach` on a parallel stream only commits to invoking the action for the elements consumed by the pipeline; order is not part of the contract.

### 3.1. Happens-Before Does Not Mean the Entire Pipeline Runs Sequentially

The Javadoc guarantees that with `forEachOrdered`, executing the action for one element **happens-before** the action for the next element. This provides a memory ordering relationship between **the final actions**. However, it does not extend to assuming that each `map` runs on the same thread or in order.

In this example, the final action is executed in order, even though `map` may compute in parallel:

```java
IntStream.range(0, 5)
        .parallel()
        .map(n -> n * 2)
        .forEachOrdered(System.out::println);
```

Placed inside a method with `import java.util.stream.IntStream;`, the stdout of the terminal action is:

```text
0
2
4
6
8
```

You should not rely on that guarantee to introduce side effects in `map`. Intermediate operations should be **stateless** and **non-interfering**, never concurrently mutating an `ArrayList` or a shared variable without synchronization.

### 3.2. When Should You Use forEachOrdered?

It is appropriate when the order of the final action matters: emitting data lines in source order, printing logs in record order, writing a linear format, or performing an effect that requires sequential order.

It is unnecessary if you are only summing numbers, computing statistics, counting, checking conditions, or grouping without order requirements. For aggregations, prefer `reduce` or an appropriate collector rather than `forEach` mutating external variables.

**Drawback:** enforcing order at the terminal action can reduce parallelism utilization and introduce coordination/buffering overhead, especially when the action itself is slow. If every action must run sequentially and most of the work is inside the action, benchmark against `sequential()`.

## 4. findFirst(): "First" Means According to Encounter Order

`findFirst()` is a **short-circuiting terminal operation**. It returns an `Optional<T>` (or `OptionalInt`, `OptionalLong`, `OptionalDouble` for primitive streams):

- If the stream **has an encounter order**, it selects the **first element** in the pipeline (after any relevant filter/map operations).
- If the stream **has no encounter order**, it may select **any element**.
- An empty stream returns `Optional.empty()`; do not call `get()` without checking. `orElse(...)` or `orElseThrow()` is usually clearer.
- For reference streams, if the selected element is `null`, `findFirst()` throws a `NullPointerException`; do not design pipelines with unhandled null elements.

"First" does not mean **the task that finishes fastest**. In an ordered parallel stream, the engine may have already computed later elements earlier, yet it must still choose the leading element according to encounter order.

### Example 3: findFirst() Is Deterministic When Ordered

**File `FirstElement.java` (Java 17+):**

```java
import java.util.List;

public class FirstElement {
    public static void main(String[] args) {
        List<Integer> source = List.of(9, 4, 8, 2, 6);

        int firstEven = source.parallelStream()
                .filter(n -> n % 2 == 0)
                .findFirst()
                .orElse(-1);

        int smallestEven = source.parallelStream()
                .filter(n -> n % 2 == 0)
                .sorted()
                .findFirst()
                .orElse(-1);

        int missing = source.parallelStream()
                .filter(n -> n < 0)
                .findFirst()
                .orElse(-1);

        System.out.println("first even: " + firstEven);
        System.out.println("smallest even: " + smallestEven);
        System.out.println("none: " + missing);
    }
}
```

Run:

```bash
javac FirstElement.java
java FirstElement
```

Exact stdout:

```text
first even: 4
smallest even: 2
none: -1
```

`firstEven == 4` because the first even element **in source order** is 4, even though 2 is smaller. After `sorted()`, the new order has 2 as the first even element. If the problem is actually to find the **minimum value**, you can express it directly with `min(Integer::compareTo)` and avoid sorting the entire dataset:

```java
int minimumEven = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .min(Integer::compareTo)
        .orElse(-1);
```

This is an illustrative snippet within the same `main` scope where `source` is defined; the result is `2`.

### 4.1. How findAny() Differs from findFirst()

`findAny()` selects a matching element **without committing to any position**, even when the source has an encounter order. With parallel streams, it gives the engine more freedom to choose based on efficient execution. `findAny()` may still happen to return the first element; that is not a guarantee.

| Requirement | Appropriate choice |
|---|---|
| First record in the list matching a condition | `findFirst()` on an ordered stream |
| Any record matching a condition | `findAny()` |
| Minimum/maximum value | `min()` / `max()` |
| All results in order | Ordered stream + `toList()` or an order-preserving collector |
| One result when input has no order | Neither `findAny()` nor `findFirst()` has a defined "first" |

**Performance:** `findFirst()` in an ordered parallel stream may require coordination across partitions to prove that no earlier element matches the condition. `findAny()` can avoid that constraint. However, actual performance depends on the data, predicate, partitioning, CPU count, and other operations; **it cannot be claimed to always be faster**.

### 4.2. Short-Circuiting Does Not Mean "Only Processes Exactly One Element"

A parallel stream may have already started testing multiple elements before `findFirst()` selects a result. `filter`/`map` functions should be pure and must not rely on being invoked once or an exact number of times. Do not count executed tasks using a counter inside `peek` and treat that count as guaranteed behavior.

## 5. unordered(): Dropping the Constraint, Not Shuffling Data

`BaseStream.unordered()` is an **intermediate operation** that returns an equivalent stream without the encounter order requirement. It may do no actual work if the stream is already unordered.

**It does not:**

- Automatically make the stream parallel; to run in parallel you must call `parallel()` or create a parallel stream.
- Guarantee a random permutation or reverse the data; to shuffle, use a dedicated algorithm.
- Sort ascending/descending; to sort, call `sorted()`.
- Modify the order or contents of the original `List`.
- Guarantee faster execution in every pipeline.
- Guarantee that `findFirst()` will return an element other than the first; it only **removes the obligation** to return the first element.

### Example 4: Testing the unordered Contract Without Guessing the Result

**File `UnorderedContract.java` (Java 17+):**

```java
import java.util.List;

public class UnorderedContract {
    public static void main(String[] args) {
        List<Integer> values = List.of(10, 20, 30, 40);

        int chosen = values.parallelStream()
                .unordered()
                .findFirst()
                .orElseThrow();

        System.out.println("chosen belongs to source: " +
                values.contains(chosen));
        System.out.println("source: " + values);
        System.out.println("sorted again: " +
                values.parallelStream()
                        .unordered()
                        .sorted()
                        .toList());
    }
}
```

Run:

```bash
javac UnorderedContract.java
java UnorderedContract
```

Guaranteed stdout for the three lines:

```text
chosen belongs to source: true
source: [10, 20, 30, 40]
sorted again: [10, 20, 30, 40]
```

We intentionally do not print the specific value of `chosen`: it can be **any element** in the list. `sorted()` in the third pipeline **re-imposes order** by value (requiring comparable data), so the resulting stream has a defined encounter order.

Even if a test snippet always observes `chosen == 10` on a particular JDK, code must **not rely** on that outcome. A different version, dataset, configuration, or execution schedule may produce a different result.

### 5.1. Operation Call Order Can Change Semantics

Compare:

```java
// First even element in List order:
source.parallelStream().filter(n -> n % 2 == 0).findFirst();

// No longer required to select the first even element:
source.parallelStream().unordered()
        .filter(n -> n % 2 == 0).findFirst();

// Sorting re-establishes order, then takes the smallest even element:
source.parallelStream().unordered()
        .filter(n -> n % 2 == 0).sorted().findFirst();

// Dropping order after sorting: no longer guarantees the smallest:
source.parallelStream().sorted()
        .unordered().findFirst();
```

The above are **illustrative expressions**, assuming `source` is a declared `List<Integer>`; each statement is a separate pipeline. Do not confuse "how fast or slow each step computes" with the logical order guaranteed by the API.

### 5.2. How Does unordered() Affect forEachOrdered()?

The name `forEachOrdered()` can be misleading. It only guarantees visiting **in encounter order if one exists**. After calling `unordered()`, the stream no longer has an encounter order for the terminal action to follow, so:

```java
values.parallelStream()
        .unordered()
        .forEachOrdered(System.out::println);
```

When `values` is a `List<Integer>`, you **cannot require** stdout to match the list order. In a specific run or implementation it might still print in the original order; that does not mean the program is allowed to depend on that behavior.

**Do not use `unordered().forEachOrdered(...)` as a trick to both guarantee order and optimize speed**; those two goals directly contradict each other in the ordering contract.

## 6. When Can Dropping Ordering Help a Parallel Stream?

According to the JDK documentation, ordering constraints particularly affect certain **stateful intermediate operations** and prefix-selection operations:

| Operation | Ordered parallel stream must preserve | After `unordered()` it can |
|---|---|---|
| `distinct()` | Keep the first occurrence in encounter order; often requires coordination/buffering | Avoid keeping the first occurrence; may reduce coordination |
| `limit(n)` | Select the **first n elements** | Select **any n matching elements** (if enough exist) |
| `skip(n)` | Skip exactly the **first n elements** | Avoid identifying a fixed prefix |
| `takeWhile(p)` | Take the longest contiguous prefix matching `p` | Take an arbitrary subset of elements matching `p` per the unordered contract |
| `dropWhile(p)` | Drop the longest contiguous prefix matching `p` | Drop a subset of elements matching `p`, not necessarily a prefix |
| `findFirst()` | Find the first matching element | Return any element; consider `findAny()` if that is the intent |

**Changing ordering means potentially changing the result.** If the business requirement calls for "the first 10 records in chronological order," `unordered().limit(10)` is **semantically wrong**, even if a benchmark runs faster.

Conversely, if the goal is simply "get up to any 10 objects matching a condition" with no fairness, ordering, or stability requirement, dropping ordering can make sense.

### Example 5: Aggregate Results Can Remain Identical Even When Dropping Ordering

**File `DistinctCount.java` (Java 17+):**

```java
import java.util.stream.IntStream;

public class DistinctCount {
    public static void main(String[] args) {
        long distinct = IntStream.range(0, 100_000)
                .parallel()
                .unordered()
                .map(n -> n % 100)
                .distinct()
                .count();

        System.out.println("distinct count=" + distinct);
    }
}
```

Run:

```bash
javac DistinctCount.java
java DistinctCount
```

Stdout:

```text
distinct count=100
```

Because only the **number of distinct values** is needed, order has no bearing on this result. `unordered()` can allow `distinct()` to be implemented more efficiently in some scenarios, though you cannot conclude it is faster from this small example alone.

### Example 6: limit() Has Different Semantics When Unordered

Given:

```java
List<Integer> data = List.of(10, 20, 30, 40, 50, 60);
List<Integer> firstThree =
        data.parallelStream().limit(3).toList();
List<Integer> anyThree =
        data.parallelStream().unordered().limit(3).toList();
```

These are illustrative statements inside a method with `import java.util.List;`.

- `firstThree` **is guaranteed** to be `[10, 20, 30]`.
- `anyThree` is guaranteed to contain **three elements from the source** (in this six-element example), but is **not guaranteed to be the first three elements**. The order within `anyThree` also has no encounter order contract.
- You should not hardcode a specific result for `anyThree`. A given run might still produce `[10, 20, 30]`.

If you need to select three truly random elements, `unordered().limit(3)` is **not a random sampling algorithm**.

## 7. Reasoning Correctly When Combining the Three APIs

Read the pipeline from **source to terminal** and answer in order:

1. Does the source have an encounter order?
2. Do intermediate operations add `sorted()` or drop order with `unordered()`?
3. Is the stream parallel or sequential?
4. Does the terminal operation respect order or ignore order?
5. Does the result need to guarantee **position** or only **values/element set**?

Example with `List.of(7, 3, 8, 2)`:

| Pipeline | Guaranteed result/meaning |
|---|---|
| `parallelStream().findFirst()` | `7` |
| `parallelStream().filter(x -> x % 2 == 0).findFirst()` | `8` |
| `parallelStream().unordered().findFirst()` | One of `7, 3, 8, 2` |
| `parallelStream().unordered().filter(x -> x % 2 == 0).findFirst()` | `8` or `2` |
| `parallelStream().sorted().findFirst()` | `2` |
| `parallelStream().unordered().sorted().findFirst()` | `2` |
| `parallelStream().sorted().unordered().findFirst()` | Does not guarantee `2` |
| `parallelStream().forEachOrdered(...)` | Actions in order `7, 3, 8, 2` |
| `parallelStream().forEach(...)` | No guarantee on action order |

A one-line change such as inserting `unordered()` before `findFirst()` can change the business contract from **"the first record"** to **"any record"**. Code reviews must therefore understand *why* ordering is required.

## 8. Common Misconceptions About Ordering and Side Effects

### Misconception 1: "`parallelStream()` always destroys order"

False. An ordered stream still has an encounter order. `toList()` and `forEachOrdered()` can observe results in that order. Only the **internal execution order** is uncommitted.

### Misconception 2: "`forEachOrdered()` forces everything to run on a single thread"

False. It only guarantees that actions run in order if the stream has an encounter order; one action may run on a different thread from the previous action. Upstream computation can still run in parallel.

### Misconception 3: "`forEach()` is guaranteed to be `unordered()`"

False in terms of the API: `forEach()` is a terminal operation that is **not required** to respect order when running in parallel; `unordered()` is an intermediate operation that **drops the encounter order constraint** for the remainder of the pipeline. Their purposes and positions are different.

### Misconception 4: "`unordered()` shuffles data"

False. It only drops the requirement to preserve order. It neither randomizes nor modifies the source collection.

### Misconception 5: "`findFirst()` in a parallel stream returns the element that finishes first"

False. If ordered, it returns the **first matching element in encounter order**, even if a later partition finishes computing earlier.

### Misconception 6: "Using a `synchronizedList` ensures appending preserves encounter order"

`Collections.synchronizedList(...)` can protect the append operation from data races, but it **does not guarantee that the order in which threads arrive to append** matches encounter order. Instead of:

```java
List<Integer> result = java.util.Collections.synchronizedList(
        new java.util.ArrayList<>());
source.parallelStream().forEach(result::add);
```

prefer creating the result directly:

```java
List<Integer> result = source.parallelStream().toList();
```

Both snippets are **illustrative code**, assuming `source` is a `List<Integer>`. The `toList()` approach is clearer, avoids side effects on an external collection, and preserves order when the source is ordered. `Stream.toList()` returns an unmodifiable `List`; if you need a mutable result, consider `collect(Collectors.toCollection(ArrayList::new))` with the appropriate imports.

### Misconception 7: "`unordered()` is guaranteed to make it faster"

No. The cost of changing order, data size, splitting/combining overhead, contention, and CPU count determine performance. For simple operations on small datasets, parallelism can be **slower than sequential**; adding `unordered()` does not eliminate that overhead.

### Misconception 8: "Dropping ordering is always safe because the result still has enough elements"

`unordered()` can change **which elements are selected** in `limit`, `skip`, `findFirst`, `takeWhile`, and `dropWhile`. In scenarios such as pagination, prioritization, SLAs, or business rules selecting the first record, this change is a functional bug, not merely a presentation issue.

## 9. Testing Ordering by Contract Instead of Luck

A good test must verify **what is guaranteed**, without depending on a coincidental execution schedule.

**Tests you should write:**

- For an ordered `List` and `findFirst()`: assert the exact first element after filtering.
- For an ordered `List` and `forEachOrdered()`: assert that the action produces a sequence matching source order.
- For unordered `findFirst()`: assert that the element belongs to the candidate set, not that it equals the first element.
- For `unordered().limit(n)`: assert size, validity, and uniqueness when the source has no duplicates; do not assert a fixed prefix.
- For `unordered().distinct().count()`: assert the count of distinct elements.
- For `sorted()`: assert comparator order and do not assume stability for elements with equal keys on an unordered source.

Example verifying a deterministic contract:

**File `OrderingAssertions.java` (Java 17+):**

```java
import java.util.List;
import java.util.stream.Collectors;

public class OrderingAssertions {
    public static void main(String[] args) {
        List<String> values = List.of("A", "C", "B");

        StringBuilder ordered = new StringBuilder();
        values.parallelStream().forEachOrdered(ordered::append);

        if (!"ACB".contentEquals(ordered)) {
            throw new AssertionError("forEachOrdered lost encounter order");
        }

        String first = values.parallelStream().findFirst().orElseThrow();
        if (!"A".equals(first)) {
            throw new AssertionError("findFirst did not respect order");
        }

        String any = values.parallelStream()
                .unordered().findFirst().orElseThrow();
        if (!values.contains(any)) {
            throw new AssertionError("unordered result outside source");
        }

        List<String> collected = values.parallelStream()
                .collect(Collectors.toList());
        if (!collected.equals(values)) {
            throw new AssertionError("ordered collection mismatch");
        }

        System.out.println("Ordering contracts passed");
    }
}
```

Run:

```bash
javac OrderingAssertions.java
java OrderingAssertions
```

Deterministic stdout:

```text
Ordering contracts passed
```

`StringBuilder` is safe here under **`forEachOrdered`'s sequential action contract** (actions execute one after another with happens-before), and the object is only used after the terminal operation completes. Do not apply that pattern with `parallelStream().forEach(ordered::append)` because `StringBuilder` is not thread-safe.

## 10. Making the Right Decision for Real-World Problems

**Scenario A — Sending records in business order:** Each record has a position in a list and the receiver requires that exact order. Keep the pipeline ordered; if the final action has an ordered side effect, consider `forEachOrdered()`. For large outputs, measure memory and latency.

**Scenario B — Finding the first person meeting priority criteria:** Input data is already sorted by priority, and the first matching item is needed. Use `filter(...).findFirst()` and preserve encounter order. Do not add `unordered()` just because it seems faster.

**Scenario C — Checking existence or picking any element:** If order does not matter, `anyMatch(...)` or `findAny()` expresses intent better than `findFirst()`. Do not use `findFirst()` to implicitly promise "the first" and then drop ordering in the pipeline.

**Scenario D — Counting unique elements on large datasets:** If only the distinct count is needed, `parallel().unordered().distinct().count()` may be suitable; benchmark with real data before optimizing.

**Scenario E — Taking the first n elements for pagination:** Keep the source ordered and use `limit(n)`, while clearly specifying which business field the source is ordered by. If the source is unordered to begin with, "the first page" has no stable meaning.

**Scenario F — Needing a sorted result:** If the goal is a list ordered by a comparator, `sorted(comparator)` provides the required order. Only add `unordered()` before `sorted()` when there is a reason and you understand that stability for elements with equal keys on an unordered source is not guaranteed.

## 11. Review and Benchmarking Checklist

- [ ] Accurately identify the source ordering (`List`, array, `HashSet`, custom spliterator, etc.).
- [ ] Check whether the pipeline contains `sorted()`, `unordered()`, `distinct()`, `limit()`, `skip()`, `takeWhile()`, or `dropWhile()`.
- [ ] Separate **result ordering** requirements from **parallelizing computation** needs.
- [ ] If you want the first element, use `findFirst()` on an ordered source; if any element suffices, consider `findAny()`.
- [ ] If you want ordered side effects, consider `forEachOrdered()`, while weighing the cost.
- [ ] Do not use `unordered()` as a shuffle or as a guaranteed speedup.
- [ ] Avoid mutating shared mutable state in `map`/`filter`/`forEach` during parallel execution; prefer collectors/reductions.
- [ ] Test ordering by contract; do not hardcode output of non-deterministic behavior.
- [ ] Benchmark with the same input and the same result semantics after JVM warm-up; monitor time, CPU, allocations, and cache behavior.
- [ ] If ordered parallel execution is too slow and order is mandatory, try `sequential()` before complicating the code.

## 12. Self-Check Questions

1. Given `List.of(5, 1, 4)`, what list is `parallelStream().map(x -> x * 2).toList()` guaranteed to return?
2. Does `forEachOrdered()` always run the action on the same worker thread?
3. Why might `parallelStream().filter(x -> x > 10).findFirst()` have to wait for results from an earlier partition, even if a later partition finds an element first?
4. Does calling `unordered()` before `findFirst()` force it to pick an element different from the source's first element?
5. When is `unordered().limit(10)` business-valid? When is it a bug?
6. Why does `Collections.synchronizedList` not guarantee that append order matches encounter order when using `parallelStream().forEach(...)`?
7. If a `HashSet` always iterates in the same order during testing, can you rely on that for `findFirst()`?
8. Do `unordered().sorted().findFirst()` and `sorted().unordered().findFirst()` share the same guarantee of finding the minimum value?

**Answer hints:** (1) `[10, 2, 8]`; (2) no, it only guarantees order and happens-before between actions; (3) it must verify the true "first"; (4) no; (5) valid when any 10 elements are acceptable, a bug when the first 10 elements are required; (6) `synchronized` protects the operation, not arrival order; (7) no, `HashSet` has no encounter order; (8) no, only the pipeline that **sorts last before `findFirst`** retains the minimum guarantee.

## Official References

- [Java SE 21 — Stream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): `forEach`, `forEachOrdered`, `findFirst`, `findAny`, `distinct`, `limit`, `skip`, and `sorted`.
- [Java SE 21 — BaseStream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/BaseStream.html): `parallel()`, `sequential()`, `unordered()`, `isParallel()`.
- [Java SE 21 — java.util.stream package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html): encounter order, parallelism, non-interference, and reduction rules.
- [dev.java — Stream terminal operations](https://dev.java/learn/api/streams/terminal-operations/): how to use `findFirst()`, `findAny()`, and terminal operations.

> **Takeaway:** `parallel()` changes **how execution runs**, `unordered()` changes **ordering constraints**, `findFirst()` requires encounter order to have a meaningful "first," and `forEachOrdered()` preserves **the order of the final action when order is defined**. Choose APIs according to the **data contract you need to guarantee**, and only then optimize for performance.
