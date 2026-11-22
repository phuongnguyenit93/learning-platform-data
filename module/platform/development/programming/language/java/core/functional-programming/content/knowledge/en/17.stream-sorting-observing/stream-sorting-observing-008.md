# Impact of the Order of `sorted()`, `limit()`, and `distinct()` in Java Stream

In Java Stream, `sorted()`, `limit()`, and `distinct()` are all **intermediate operations**: they describe how to produce the next stream but generally do not compute the result until a terminal operation such as `toList()`, `count()`, or `forEach()` is invoked. However, **the order in which these three operations are placed in the pipeline changes the meaning of the transformation**. You cannot arbitrarily reorder the steps just because they all "filter down or sort data."

This lesson focuses on three questions: when reordering changes the result, when you can get the same result, and why the choice of order also affects performance, especially with parallel streams.

## 1. Understand each operation before combining them

| Operation | Behavior | Can change the number of elements? | Relationship to order |
| --- | --- | --- | --- |
| `sorted()` | Sorts according to the natural order of the elements, or `sorted(comparator)` according to a comparator | No | Establishes a sorted encounter order; `sorted` is *stable* on an ordered stream |
| `limit(n)` | Keeps at most the first `n` elements at **this position** in the pipeline | Yes | On an ordered stream, selects a prefix according to encounter order |
| `distinct()` | Keeps one copy of each value according to `equals()` | Yes | On an ordered stream, keeps the **first occurrence** of each value; on an unordered stream, there is no guarantee of picking the first appearance |

Key points to remember:

- `sorted()` **does not remove duplicates**: `[3, 1, 1]` becomes `[1, 1, 3]`, keeping both `1`s.
- `distinct()` **does not sort**: on an ordered stream, `[3, 1, 3, 2]` becomes `[3, 1, 2]`.
- `limit(3)` **has no concept of "smallest" or "distinct."** It simply takes at most the first three elements after the preceding steps.
- `limit(n)` requires `n >= 0`; a negative number throws `IllegalArgumentException`. `limit(0)` produces an empty result.
- `distinct()` compares elements using **`Object.equals`** (and implementations typically use `hashCode` for performance). It does not use the comparator from `sorted()` to decide duplicates.
- All three are **stateful intermediate operations**: they may need to store or track information from multiple elements. In particular, `limit` is a *short-circuiting* operation that can allow stopping consumption from the source early.

## 2. One list, eight pipelines, eight interpretations

Use a source that has both an "unsorted" order and duplicate values:

```text
Source: [4, 1, 1, 3, 2, 2, 5, 1]
            ^  ^              ^
            The 1s appear three times; 2 appears twice.
```

Consider the following pipelines (`n = 3`):

| Pipeline | Result | Interpretation |
| --- | --- | --- |
| `sorted().limit(3)` | `[1, 1, 1]` | Sorts everything by value and then takes the first three elements; duplicates may remain |
| `limit(3).sorted()` | `[1, 1, 4]` | Takes only the first three original elements `[4, 1, 1]` and then sorts them |
| `distinct().limit(3)` | `[4, 1, 3]` | Takes the first three **distinct values** in encounter order |
| `limit(3).distinct()` | `[4, 1]` | Takes three elements first, then removes duplicates; may yield fewer than three results |
| `sorted().distinct().limit(3)` | `[1, 2, 3]` | Takes the three **smallest distinct** values |
| `sorted().limit(3).distinct()` | `[1]` | Looks only at the three smallest elements (all `1`s), then removes duplicates |
| `distinct().sorted().limit(3)` | `[1, 2, 3]` | Deduplicates the entire source, sorts, then takes the first three values |
| `distinct().limit(3).sorted()` | `[1, 3, 4]` | Takes only the first three distinct values from the source, then sorts those three values |

**Key takeaway from the table:** placing `limit` **before or after** `sorted` or `distinct` can change the result set, the number of returned elements, and the business meaning.

## 3. Complete runnable Java 17+ example and exact stdout

Save to `StreamOperationOrderDemo.java`:

```java
import java.util.List;

public class StreamOperationOrderDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(4, 1, 1, 3, 2, 2, 5, 1);

        System.out.println("source = " + values);

        System.out.println("sortedLimit = " + values.stream()
                .sorted().limit(3).toList());

        System.out.println("limitSorted = " + values.stream()
                .limit(3).sorted().toList());

        System.out.println("distinctLimit = " + values.stream()
                .distinct().limit(3).toList());

        System.out.println("limitDistinct = " + values.stream()
                .limit(3).distinct().toList());

        System.out.println("sortDistinctLimit = " + values.stream()
                .sorted().distinct().limit(3).toList());

        System.out.println("sortLimitDistinct = " + values.stream()
                .sorted().limit(3).distinct().toList());

        System.out.println("distinctSortLimit = " + values.stream()
                .distinct().sorted().limit(3).toList());

        System.out.println("distinctLimitSort = " + values.stream()
                .distinct().limit(3).sorted().toList());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac StreamOperationOrderDemo.java
java StreamOperationOrderDemo
```

Exact stdout output:

```text
source = [4, 1, 1, 3, 2, 2, 5, 1]
sortedLimit = [1, 1, 1]
limitSorted = [1, 1, 4]
distinctLimit = [4, 1, 3]
limitDistinct = [4, 1]
sortDistinctLimit = [1, 2, 3]
sortLimitDistinct = [1]
distinctSortLimit = [1, 2, 3]
distinctLimitSort = [1, 3, 4]
```

Each line in `main` creates a **new** `values.stream()`. A stream can only be consumed once; it cannot be reused after the terminal operation `toList()`. Since the input data is a `List`, the encounter order is well-defined and the results in the example do not depend on thread scheduling.

## 4. `sorted()` and `limit()`: "smallest across the source" vs. "sort a slice"

### `sorted().limit(n)`: take the first n elements of the entire sorted data

```java
List<Integer> smallest = List.of(9, 2, 8, 1, 7)
        .stream()
        .sorted()
        .limit(2)
        .toList();
// [1, 2]
```

`sorted()` establishes an encounter order in ascending order. Then `limit(2)` selects the first two elements of that new order: `1` and `2`.

This is **not necessarily** "the two smallest distinct values": if the source contains two `1`s, the result can be `[1, 1]`. If you want **distinct** values, you must also include `distinct()`.

### `limit(n).sorted()`: sort only the first n elements of the source

```java
List<Integer> prefixSorted = List.of(9, 2, 8, 1, 7)
        .stream()
        .limit(2)
        .sorted()
        .toList();
// [2, 9]
```

Data beyond the first two elements `[9, 2]` is not considered in the sort step because it has already been discarded by `limit(2)`. The result `[2, 9]` **cannot be used** to determine the two smallest numbers in the entire source.

The two snippets above are illustrations placed inside a method and require `import java.util.List;`.

### When to use each

- The "**Top N smallest values**" problem usually requires `sorted(comparator).limit(n)` if the sorting cost is acceptable.
- The "**Take the first N records in input order and then display by name**" problem uses `limit(n).sorted(comparator)`.
- The "**Top N smallest distinct values**" problem requires combining both `distinct()` and `sorted()` **before** `limit(n)`.

**Performance:** with a finite source, `limit(n).sorted()` can significantly reduce the number of elements to sort, but it returns a different result. `sorted().limit(n)` semantically has to determine the N smallest elements **across the entire source**, so it typically requires examining more than N elements and may require substantial buffering/sorting. Do not optimize by changing the order if it produces the wrong result.

## 5. `distinct()` and `limit()`: "N distinct values" vs. "N elements then deduplicate"

Given the source:

```java
List<String> names = List.of("An", "An", "Bình", "Chi", "Chi");
```

With the goal of **the first two distinct names**:

```java
List<String> firstTwoUnique = names.stream()
        .distinct()
        .limit(2)
        .toList();
// [An, Bình]
```

With the goal of **examining the exact first two records and then deduplicating**:

```java
List<String> uniqueInFirstTwo = names.stream()
        .limit(2)
        .distinct()
        .toList();
// [An]
```

Both illustrative snippets are inside a method and require `import java.util.List;`.

Note that `distinct().limit(n)` may have to inspect **more than n elements from the source** before finding n distinct values. With a source containing many duplicates, the n-th occurrence of a unique value can be very far into the stream. If the source only repeats a single value forever, a pipeline looking for two unique values may **never terminate**:

```java
// Example illustrating the hang risk: DO NOT run toList() on this pipeline.
java.util.stream.Stream.generate(() -> "A")
        .distinct()
        .limit(2)
        .toList();
```

This snippet intentionally has no output because the source is infinite and only generates `"A"`; `distinct()` has only one value to emit, and `limit(2)` never receives two elements to stop.

Meanwhile, `limit(2).distinct()` on that same source will return `["A"]` because it only takes the initial two generated items before deduplicating. That illustrates both the difference in **result** and in **termination**.

## 6. `sorted()` and `distinct()`: when does swapping them still give the same result?

With integers, natural comparator, and an ordered stream:

```java
List<Integer> values = List.of(4, 1, 1, 3, 2, 2);

List<Integer> a = values.stream()
        .sorted()
        .distinct()
        .toList();             // [1, 2, 3, 4]

List<Integer> b = values.stream()
        .distinct()
        .sorted()
        .toList();             // [1, 2, 3, 4]
```

With the data and semantics above, both pipelines return the same distinct values sorted in ascending order. However, **you should not generalize unconditionally** to every comparator, every source, or code with side effects:

- `distinct()` uses `equals()`; `sorted(comparator)` uses the comparator. The two criteria can **differ**, for example when a comparator compares only string length while `equals` compares the entire content.
- On an **ordered stream**, `distinct()` picks the first element encountered according to `equals`, and `sorted` preserves the relative order of elements considered equal by the comparator (*stable sort*). When the comparator is inconsistent with `equals`, the result across the comparator's "equivalence groups" can make the order of records matter more than just the set of values.
- On an **unordered stream**, `distinct` does not guarantee picking the first representative when elements are equal according to `equals`. A comparator that treats multiple elements as equal also does not guarantee the order among those elements if the original stream is unordered.
- `distinct().sorted()` often reduces the number of elements to sort when the data has many duplicates; `sorted().distinct()` may have to sort duplicate elements as well. **Even so, there is no absolute performance guarantee**; source structure, data, JVM, and parallelism all play a role.

### "Equal" according to a comparator is not the same as `equals()`

```java
List<String> values = List.of("aa", "BB", "c");
List<String> result = values.stream()
        .sorted(String.CASE_INSENSITIVE_ORDER)
        .distinct()
        .toList();
// [aa, BB, c]
```

The snippet above illustrates that `distinct()` does not remove an element just because a comparator considers two values equal. However, with the specific example `"aa"`, `"BB"`, `"c"`, the comparator does not consider them equal either; to see the difference clearly, use:

```java
List<String> values = List.of("a", "A", "b");
List<String> result = values.stream()
        .sorted(String.CASE_INSENSITIVE_ORDER)
        .distinct()
        .toList();
// [a, A, b]
```

Here the comparator is case-insensitive, so it treats `"a"` and `"A"` as equivalent for sorting; `String.equals`, on the other hand, treats them as different. Therefore `distinct` keeps both. These snippets belong inside a method and require `java.util.List`.

**If you want to deduplicate by a key** such as a case-insensitive name, you must express that rule explicitly (for example by normalizing the key, grouping, or using a map by key). Simply calling `sorted(comparator).distinct()` will not replace that policy.

## 7. Why is `limit()` a critical boundary in a pipeline?

Three statements on the same source can express three very different questions:

```java
List<Integer> data = List.of(4, 1, 1, 3, 2, 2, 5, 1);

List<Integer> a = data.stream().sorted().distinct().limit(3).toList();
// a = [1, 2, 3]: the three smallest DISTINCT VALUES across the entire source.

List<Integer> b = data.stream().distinct().limit(3).sorted().toList();
// b = [1, 3, 4]: the first three DISTINCT VALUES in source order, then sorted.

List<Integer> c = data.stream().sorted().limit(3).distinct().toList();
// c = [1]: among the three smallest ELEMENTS, only one DISTINCT VALUE remains.
```

These snippets belong inside a method and require `java.util.List`.

The question "Take the first 3" only makes sense once you specify **what has been computed before limiting**:

1. If you need the **top N distinct across the entire source**, `limit` must come after both deduplication and sorting.
2. If you only need the **first N elements/groups in the source**, `limit` comes before subsequent transformation steps according to the desired policy.
3. If the business requirement accepts **fewer than N results** due to deduplication, `limit(n).distinct()` may be appropriate; if you need a full N distinct values when the source has enough, choose `distinct().limit(n)`.

## 8. Encounter order, unordered sources, and parallel streams

`List.stream()` has an encounter order defined by the list. `HashSet.stream()` does not guarantee an encounter order; therefore `limit(n)` on a `HashSet` does not have a stable meaning of "first N elements" across runs.

```java
java.util.Set<Integer> values = new java.util.HashSet<>(
        List.of(4, 1, 3, 2, 5)
);
List<Integer> picked = values.stream().limit(2).toList();
// No specific pair or order is guaranteed.
```

If a deterministic result based on values is required, you can sort before `limit`:

```java
List<Integer> picked = values.stream()
        .sorted()
        .limit(2)
        .toList();
// [1, 2]
```

These snippets belong inside a method and require `java.util.List`.

With a `parallelStream()` backed by a `List`, encounter order still exists. For example:

```java
List<Integer> result = List.of(4, 1, 1, 3, 2)
        .parallelStream()
        .distinct()
        .sorted()
        .limit(3)
        .toList();
// [1, 2, 3]
```

Java may execute callbacks and combine data across multiple threads in different schedules, but the result of an ordered stream with `toList()` respects the encounter order at the end of the pipeline. **The execution order of callbacks is not necessarily the same as the result order**.

### `unordered()` relaxes the ordering requirement, it does not shuffle data

```java
List<Integer> picked = List.of(4, 1, 1, 3, 2, 2)
        .parallelStream()
        .unordered()
        .distinct()
        .limit(2)
        .toList();
```

`picked` may contain two distinct values, but it is not guaranteed to always be the first two distinct values `4` and `1`. `unordered()` does not turn the stream into a random shuffle; it simply removes the obligation to maintain encounter order.

Keeping or dropping order is a **business decision**, not just an optimization option. If you need stable pagination or a "top N" result, do not drop ordering without establishing a meaningful order before selecting a prefix.

## 9. Performance: same target result, different costs

The following table describes common impacts; these are **guidelines**, not complexity guarantees for every implementation or JVM.

| Pipeline | Work that may occur | When to consider |
| --- | --- | --- |
| `sorted().limit(n)` | Must determine the smallest values from many source elements; sorting/buffering can be substantial | When the goal is truly top N by comparator |
| `limit(n).sorted()` | Sorts at most the n pre-selected elements | When only the initial elements of the source need sorting |
| `distinct().limit(n)` | Must track seen elements; may read more than n inputs to find n unique values | When the first n distinct values are needed |
| `limit(n).distinct()` | Limits input to at most n elements before deduplicating | When business logic only considers a prefix of the source |
| `distinct().sorted().limit(n)` | Has an opportunity to reduce the number of elements to sort if the source has many duplicates | When the top N distinct values are needed |
| `sorted().distinct().limit(n)` | May sort duplicate elements as well before deduplicating | When this phrasing is clearer or for specific data characteristics |

**With ordered parallel streams**, `distinct` must preserve the first occurrence, `limit` must select the exact prefix, and `sorted` must establish a global order. These constraints may require additional memory, buffering, or coordination across parallel branches. In particular, stateful operations can reduce the benefits of parallel streams.

Worthwhile optimizations:

- Prioritize **semantic correctness**: do not push `limit` before `sorted` or `distinct` if doing so changes the result.
- If there is an independent `filter` step, filtering before `sorted` can reduce the number of elements to sort, but verify that filtering at that position is correct.
- If the source is a large database, consider `ORDER BY` and pagination at the query layer instead of loading all data into Java and calling `stream().sorted().limit(n)`.
- Do not assume `parallelStream()` is faster; measure with realistic data sizes, comparators, duplicate ratios, and runtime conditions.

## 10. Does `sorted()` affect side effects and callback invocations?

Like any Stream pipeline, `sorted`, `limit`, and `distinct` operate **lazily** and are allowed to apply optimizations that preserve the final result. `limit` may stop early, while `distinct` or `sorted` may need to inspect more elements before emitting output.

Do not rely on `peek`, `map`, or a comparator with side effects to perform required writes:

```java
List<Integer> result = List.of(4, 1, 3, 2)
        .stream()
        .peek(n -> System.out.println("seen " + n))
        .sorted()
        .limit(2)
        .toList();
// result = [1, 2]; do not rely on the "seen" lines as a business contract.
```

This example may print the `seen` values as the pipeline traverses the source, but the order or completeness of side effects in intermediate operations is not an API for determining business results, especially after adding another terminal operation or switching to a parallel stream. `peek` is primarily intended for observation/debugging.

A comparator function should **adhere to the Comparator contract**: consistent results for the same pair of inputs and consistent with the desired ordering. A comparator whose behavior changes over time, or that mutates the data being sorted, can lead to unexpected results or exceptions.

When you need to output data, collect the result first and then perform I/O actions at a well-controlled boundary:

```java
List<Integer> result = values.stream()
        .distinct()
        .sorted()
        .limit(3)
        .toList();

result.forEach(System.out::println);
```

This is an illustrative snippet inside a method with `values` of type `List<Integer>`; the print operation is an intentional action after the result has already been selected.

## 11. Common mistakes

1. **Thinking `sorted().limit(3)` always returns three distinct values:** no; duplicate data remains. `distinct` is needed if that is the requirement.
2. **Moving `limit` before `sorted` for speed without checking the result:** then only the initial prefix is sorted, and it is no longer the top N across the entire source.
3. **Using `limit(n).distinct()` when requiring exactly n distinct values:** it can yield fewer than n. Use `distinct().limit(n)` if you want the first n unique values and the source has enough.
4. **Assuming `distinct()` relies on the comparator:** it relies on `equals`; the comparator is only used in `sorted(comparator)`.
5. **Confusing "unique by ID" with default `equals`:** objects with two different instances but the same ID are not automatically merged by `distinct` if `equals` does not reflect that relationship. You need an explicit comparison/key rule.
6. **Using `HashSet.stream().limit(3)` to reliably get the first three elements:** `HashSet` does not guarantee encounter order.
7. **Misusing `unordered()` thinking it preserves the prefix:** `unordered` relaxes the constraint of selecting the initial prefix.
8. **Forgetting that a stream can only be used once:** each pipeline in the examples must start from a new stream.
9. **Mutating the source collection inside `peek`/comparator:** violates the non-interfering requirement of streams and can corrupt the result.
10. **Treating parallel test output as an ordering guarantee:** callback execution order is not the logical order of the result.

## 12. Self-assessment questions

**1.** Given `List.of(4, 1, 1, 3, 2)`, are `sorted().limit(3)` and `sorted().distinct().limit(3)` the same?

No. The first returns `[1, 1, 2]`; the second returns `[1, 2, 3]`.

**2.** To get the first three distinct codes in input order, should you choose `distinct().limit(3)` or `limit(3).distinct()`?

Choose `distinct().limit(3)`; `limit(3).distinct()` only examines the first three records and may leave fewer than three codes.

**3.** When you already know a `List<Integer>` needs the three smallest distinct values, can you swap between `distinct().sorted().limit(3)` and `sorted().distinct().limit(3)`?

For integers and natural ordering as in this lesson, both produce the same smallest distinct values. However, execution cost may differ; when a comparator is not consistent with `equals`, you must carefully check the ordering and uniqueness requirements.

**4.** Does `parallelStream().sorted().limit(3).toList()` guarantee that callbacks run in ascending order?

No. The pipeline may run in parallel; `sorted` determines the logical order of the result, not that every intermediate callback executes in that order.

**5.** Why shouldn't you use `Stream.generate(() -> "A").distinct().limit(2).toList()`?

The infinite source has only one distinct value, so `distinct()` can never provide a second result; the call may never terminate.

## Key Takeaways

- `sorted()`: **sorts**, does not remove duplicates.
- `distinct()`: **removes duplicates according to `equals()`**, does not necessarily sort.
- `limit(n)`: **takes at most the first n elements at the exact position it appears in the pipeline**.
- `sorted().limit(n)` and `limit(n).sorted()` usually serve two different requirements.
- `distinct().limit(n)` and `limit(n).distinct()` can even differ in the number of elements returned.
- To find the **N smallest distinct values** of an ordered stream of integers, use `distinct().sorted().limit(n)` or `sorted().distinct().limit(n)` according to the appropriate semantics.
- Choose the operation order based on data semantics first; only then consider performance optimization through measurement.
