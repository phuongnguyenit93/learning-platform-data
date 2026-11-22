# Slicing Data with `skip` and `limit`

When a Stream contains many elements but a program only needs a slice, the Java Stream API provides two intermediate operations: `skip(long n)` and `limit(long maxSize)`. They often appear together to skip a number of leading elements and take a fixed number of elements. This is **data slicing**, very useful for displaying paginated results, taking a finite sample from a long source, or controlling how many elements proceed downstream.

This lesson belongs to the **Ordering, Deduplication, and Slicing** chapter of the **JAVA_STREAM_API** module. In the declarative lazy-pipeline model, `skip` and `limit` interact directly with `filter`, `map`, `sorted`, `distinct`, and terminal operations like `collect` and `reduce`. Understanding them well also helps avoid pagination bugs, high parallel-processing overhead, and non-terminating pipelines on infinite sources.

## 1. Exact Meaning of `skip` and `limit`

| Operation | Meaning | Argument | Properties |
| --- | --- | --- | --- |
| `skip(n)` | Discards at most the first `n` elements **at that stage** of the pipeline; forwards the remaining elements | Non-negative `long` | Intermediate, lazy, stateful because it must track the discarded prefix |
| `limit(n)` | Allows at most the first `n` elements **at that stage** to pass downstream | Non-negative `long` | Intermediate, lazy, stateful, and **short-circuiting** |

For example, given a source with an encounter order:

```text
Source:                 [10, 20, 30, 40, 50, 60, 70, 80]
After skip(3):                   [40, 50, 60, 70, 80]
After limit(2):                  [40, 50]
```

On an ordered Stream, `skip(3).limit(2)` selects the elements at the **fourth and fifth positions** (if present). Neither method **modifies the original Collection**, creates a sublist immediately when called, or triggers element traversal on its own.

Edge cases:

- `skip(0)` discards no elements; `limit(0)` lets no elements pass downstream.
- If a finite source has fewer than `n` elements, `skip(n)` yields an empty Stream.
- If a finite source has fewer than `n` elements, `limit(n)` yields all remaining elements.
- `skip(-1)` and `limit(-1)` throw `IllegalArgumentException` for negative arguments.
- When a source has no encounter order, you cannot rely on the notion of "first elements" in a user-expected order; see section 6.

## 2. Trying It on a `List`: Seeing the Slice

The following complete program runs on Java 8 or later:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class SliceDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList(
            "An", "Binh", "Chi", "Dung", "Ha", "Khoa", "Linh"
        );

        List<String> middle = names.stream()
            .skip(2)
            .limit(3)
            .collect(Collectors.toList());

        List<String> fromFourth = names.stream()
            .skip(3)
            .collect(Collectors.toList());

        List<String> firstTwo = names.stream()
            .limit(2)
            .collect(Collectors.toList());

        System.out.println(middle);
        System.out.println(fromFourth);
        System.out.println(firstTwo);
        System.out.println(names);
    }
}
```

Output:

```text
[Chi, Dung, Ha]
[Dung, Ha, Khoa, Linh]
[An, Binh]
[An, Binh, Chi, Dung, Ha, Khoa, Linh]
```

Notice that the source `names` is unchanged. `collect(Collectors.toList())` is the step that builds the resulting lists. In this example, the source list is ordered by position, so the extracted slice is well-defined.

## 3. Why Both Operations Are Lazy, Yet Only `limit` Short-Circuits

Consider the pipeline:

```java
List<Integer> output = Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8)
    .stream()
    .filter(n -> n % 2 == 0)
    .skip(1)
    .limit(2)
    .map(n -> n * 10)
    .collect(Collectors.toList());

// output = [40, 60]
```

Meaning of each step:

1. `filter` keeps even numbers, producing the logical sequence `[2, 4, 6, 8]`.
2. `skip(1)` discards the first even number `2`, leaving `[4, 6, 8]`.
3. `limit(2)` requests at most the next two elements, which are `4` and `6`.
4. `map` multiplies those two numbers by `10`; `collect` gathers `[40, 60]`.

**Laziness:** `filter`, `skip`, `limit`, and `map` describe processing stages; actual consumption begins when `collect` is invoked. A sequential pipeline can fuse these stages per element without necessarily allocating intermediate lists like the logical sequence shown above.

**Early stopping:** `limit(2)` allows the pipeline to stop requesting elements as soon as it receives two elements from `skip`. Conversely, `skip(2)` by itself does not bound how many elements remain: a terminal operation that wants everything after `skip` still has to continue until the source ends.

Do not use logging inside `peek` or side effects in `map` to verify that every element was processed exactly once. Java is permitted to apply optimizations that preserve the result; for instance, `count()` on a sized source can compute the element count after `skip`/`limit` without invoking every lambda.

## 4. Reordering `skip`, `limit`, and `filter` Changes the Problem

### `skip` before `limit` differs from `limit` before `skip`

```java
List<Integer> input = Arrays.asList(10, 20, 30, 40, 50, 60);

List<Integer> a = input.stream()
    .skip(2)
    .limit(3)
    .collect(Collectors.toList()); // [30, 40, 50]

List<Integer> b = input.stream()
    .limit(3)
    .skip(2)
    .collect(Collectors.toList()); // [30]
```

Pipeline `a` skips the first two elements **and then takes the next three**. Pipeline `b` considers only the first three elements of the source **and then skips two** of those three. Both are valid, but they answer different questions.

### `filter` before `skip` differs from `skip` before `filter`

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8, 9, 10);

List<Integer> afterFiltering = numbers.stream()
    .filter(n -> n % 2 == 0)
    .skip(2)
    .limit(3)
    .collect(Collectors.toList()); // [6, 8, 10]

List<Integer> beforeFiltering = numbers.stream()
    .skip(2)
    .filter(n -> n % 2 == 0)
    .limit(3)
    .collect(Collectors.toList()); // [4, 6, 8]
```

If the requirement is "skip the first two **even numbers**", put `filter` before `skip`. If the requirement is "skip the first two **source records** and then filter for even numbers", put `skip` before `filter`.

A good self-check when writing a pipeline is to read the stages as a complete sentence: **filter what, in what order, skip how many, take how many?**

## 5. Combining `sorted` and `distinct` to Slice the Right Items

Paginating a list or selecting a slice usually requires a **deterministic order**. When the source does not already have the right order, sort before slicing:

```java
List<Integer> scores = Arrays.asList(9, 1, 7, 3, 6, 2);

List<Integer> sortedWindow = scores.stream()
    .sorted()
    .skip(2)
    .limit(2)
    .collect(Collectors.toList()); // [3, 6]

List<Integer> sortOnlyWindow = scores.stream()
    .skip(2)
    .limit(2)
    .sorted()
    .collect(Collectors.toList()); // [3, 7]
```

`sorted().skip(2).limit(2)` retrieves the third and fourth elements **in the sorted sequence**. `skip(2).limit(2).sorted()` instead selects two elements in original source order and then sorts only those two.

Similarly, if you need the second page of a **deduplicated code list**, place `distinct()` before `skip()`:

```java
List<String> codes = Arrays.asList("A", "A", "B", "C", "C", "D");

List<String> uniquePage = codes.stream()
    .distinct()
    .skip(1)
    .limit(2)
    .collect(Collectors.toList()); // [B, C]

List<String> slicedThenUnique = codes.stream()
    .skip(1)
    .limit(2)
    .distinct()
    .collect(Collectors.toList()); // [A, B]
```

On an ordered Stream, `distinct` keeps the first occurrence of each value. Placing it after slicing deduplicates **only within the retrieved slice**, so element counts and page boundaries may differ from expectations.

Cost note: `sorted` normally must consume the entire finite input before emitting sorted elements. Hence `sorted().skip(...).limit(...)` can still read and sort the whole source; `limit` does not make the preceding `sorted` step cheap.

## 6. Encounter Order: "First" and "Next" Are Only Clear When Ordered

`skip` and `limit` are easiest to reason about on sources with an **encounter order**: the element order a Stream receives from its source.

| Source | Encounter order | Meaning of slicing |
| --- | --- | --- |
| `List.stream()` | Yes, by List position | `skip` and `limit` slice by List index |
| `LinkedHashSet.stream()` | Yes, by insertion order | Slice by insertion order of unique values |
| `TreeSet.stream()` | Yes, by sorted order | Slice by the Set's sort order |
| `HashSet.stream()` | Not guaranteed | Do not treat results as a stable "first n elements" |
| `stream.unordered()` | Drops encounter-order constraint | Allows implementations to select elements without preserving source order |

Example:

```java
Set<Integer> values = new HashSet<>(
    Arrays.asList(40, 10, 30, 20)
);

List<Integer> unpredictable = values.stream()
    .limit(2)
    .collect(Collectors.toList());
// Do not rely on the result being [10, 20] or any specific pair.

List<Integer> predictable = values.stream()
    .sorted()
    .skip(1)
    .limit(2)
    .collect(Collectors.toList());
// [20, 30]
```

For a source without an encounter order, `limit(n)` may choose **any** `n` eligible elements under the Stream contract; `skip(n)` may discard an unspecified set of `n` elements. The count is right, but stability across runs is not guaranteed.

**If an application needs stable pagination, establish a well-defined order with a tie-breaker**, such as sorting by timestamp and then by unique ID. Sorting only by a field where many records share the same value may not be enough to stabilize page positions when data or source order changes.

## 7. Pagination with `skip` and `limit`

Suppose pages are **1-based**, with page size `pageSize`. Formula for the number of elements to skip:

\[
\text{offset} = (\text{pageNumber} - 1) \times \text{pageSize}
\]

Then:

```java
stream
    .skip(offset)
    .limit(pageSize)
    .collect(Collectors.toList());
```

Complete example with a list of order IDs:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class OrderPagingDemo {
    public static List<String> page(
            List<String> orderIds, int pageNumber, int pageSize) {
        if (pageNumber < 1 || pageSize < 1) {
            throw new IllegalArgumentException(
                "pageNumber and pageSize must be greater than 0"
            );
        }

        long offset = Math.multiplyExact(
            (long) pageNumber - 1,
            (long) pageSize
        );

        return orderIds.stream()
            .sorted() // For this example, ID is both unique key and desired order.
            .skip(offset)
            .limit(pageSize)
            .collect(Collectors.toList());
    }

    public static void main(String[] args) {
        List<String> ids = Arrays.asList(
            "ORD-104", "ORD-102", "ORD-105", "ORD-101", "ORD-103"
        );

        System.out.println(page(ids, 1, 2)); // [ORD-101, ORD-102]
        System.out.println(page(ids, 2, 2)); // [ORD-103, ORD-104]
        System.out.println(page(ids, 3, 2)); // [ORD-105]
        System.out.println(page(ids, 4, 2)); // []
    }
}
```

In this code:

1. Validate that `pageNumber` and `pageSize` are positive to reject invalid parameters.
2. Cast to `long` before multiplying and use `Math.multiplyExact` to detect overflow; `skip` accepts a `long` argument.
3. Sort IDs before slicing so the same input list produces deterministic pages.
4. Using `skip(offset).limit(pageSize)`, a page past the end of the list returns an empty `List`.

Some practical limitations:

- `skip` **is not equivalent to O(1) random access**. With large offsets, the pipeline may still have to traverse or discard many elements; Streams do not magically turn into efficient pagination for huge tables.
- `sorted()` in the example may read and buffer the entire input to sort it. If the data already has an appropriate, stable order, do not sort repeatedly.
- Data mutations between two page requests can cause duplicate or missed records when using offsets. With databases, it is usually better to paginate in the query with a deterministic `ORDER BY`, and consider *keyset/cursor pagination* for large or rapidly changing datasets.
- `skip`/`limit` operate on the **Stream at consumption time**; they neither create a snapshot nor lock the Collection against concurrent modification.

## 8. Slicing Very Long or Infinite Sources

Laziness lets you extract a finite slice from a source capable of generating infinitely many elements:

```java
List<Integer> window = IntStream.iterate(0, n -> n + 1)
    .skip(100)
    .limit(5)
    .boxed()
    .collect(Collectors.toList());

// [100, 101, 102, 103, 104]
```

In this sequential example, the pipeline skips the first 100 numbers and collects the next five; `limit(5)` allows the terminal `collect` to complete without consuming infinitely many elements.

However, `skip` and `limit` **do not automatically guarantee every pipeline terminates**. If an upstream `filter` never passes enough elements, the downstream limit is never reached:

```java
// Example for analysis, DO NOT run: source produces only positive numbers.
// Stream.iterate(BigInteger.ONE, n -> n.add(BigInteger.ONE))
//     .filter(n -> n.signum() < 0)
//     .skip(2)
//     .limit(3)
//     .collect(Collectors.toList());
```

Or if `sorted()` is placed **before** the limit on an infinite source, general sorting must consume the entire source before emitting its first element:

```java
// DO NOT run: sorted() waits for the entire infinite source.
// IntStream.iterate(1, n -> n + 1).sorted().limit(5).sum();

// Terminates: sorts only the five elements already taken.
int sum = IntStream.iterate(1, n -> n + 1)
    .limit(5)
    .sorted()
    .sum(); // 15
```

For sources that may block while producing elements (such as reading external I/O), `limit` is also **not a timeout**. It sets a count limit, not a time limit.

## 9. Running in Parallel: The Cost of Preserving Exact Slice Positions

The same pipeline can be created via `collection.parallelStream()` or switched using `parallel()`:

```java
List<Integer> values = IntStream.rangeClosed(1, 20)
    .boxed()
    .collect(Collectors.toList());

List<Integer> page = values.parallelStream()
    .skip(5)
    .limit(4)
    .collect(Collectors.toList());

System.out.println(page); // [6, 7, 8, 9]
```

Because `List` has an encounter order, slicing results must still respect that order even when some elements are processed concurrently. That exact requirement—"skip **the first five** and take **the next four**"—can make `skip`/`limit` on a parallel Stream expensive to coordinate, especially when the source splits poorly or its size is unknown.

If you **genuinely do not care which elements are chosen**, you can drop the ordering constraint to give implementations more freedom to optimize:

```java
List<Integer> sample = values.parallelStream()
    .unordered()
    .skip(5)
    .limit(4)
    .collect(Collectors.toList());

// Contains at most four elements, but do not rely on them being [6, 7, 8, 9].
```

`unordered()` **does not randomly shuffle** data and does not promise a fair random sample; it merely removes the encounter-order constraint. In real pagination, you should normally **not** use it because applications require predictable page positions and ordering.

`Spliterator` characteristics like `SIZED`/`SUBSIZED` help Streams optimize slicing on certain sized, cleanly splittable sources. Actual outcomes still depend on the source, size, preceding operations, terminal operation, and runtime environment. Switching to `parallelStream()` is not guaranteed to be faster; decide only after benchmarking on representative data.

## 10. Common Pitfalls

| Scenario | Consequence | Fix |
| --- | --- | --- |
| Putting `limit` before `skip` when expecting fixed-size pages | Pages may be unexpectedly short or empty | Typically use `skip(offset).limit(pageSize)` |
| Putting `skip` before `filter` when intending to skip **filtered** elements | Skips raw source elements instead of filtered ones | Place `filter` before `skip` |
| Putting `distinct` after slicing when paginating unique values | Pages may have fewer values or duplicates across pages | Deduplicate before slicing |
| Paginating a `HashSet` without sorting | No guarantee which page contains which elements | Establish a clear order, e.g., `sorted` |
| Computing `pageNumber * pageSize` with `int` | Risk of integer overflow before passing to `skip` | Validate inputs, cast to `long`, and consider `Math.multiplyExact` |
| Calling `skip(1_000_000)` on a large source expecting instant access | May incur heavy traversal and processing cost | Consider querying at the source, indexes, or cursors |
| Calling two terminal operations on the same Stream | Stream is already consumed, typically throwing `IllegalStateException` | Create a new Stream per consumption |
| Assuming `limit` bounds time or always terminates infinite sources | May hang if source blocks or never passes enough elements upstream | Design explicit stop conditions and cancellation mechanisms |

## 11. Self-Check Exercises

**Exercise 1 — Predict the output.** Given `List<Integer> data = Arrays.asList(2, 4, 6, 8, 10, 12);`, what do these two expressions produce?

```java
data.stream().skip(2).limit(2).collect(Collectors.toList());
data.stream().limit(2).skip(2).collect(Collectors.toList());
```

**Answer:** The first returns `[6, 8]`; the second returns `[]` because it passes only the first two elements and then discards both.

**Exercise 2 — Filter then paginate.** From the integers 1 through 15, select the second page (1-based) with three **odd numbers** per page, in ascending order.

```java
List<Integer> pageTwo = IntStream.rangeClosed(1, 15)
    .filter(n -> n % 2 != 0)
    .skip(3)
    .limit(3)
    .boxed()
    .collect(Collectors.toList()); // [7, 9, 11]
```

**Explanation:** The odd numbers are `[1, 3, 5, 7, 9, 11, 13, 15]`. Skip the first three odd numbers and take the next three.

**Exercise 3 — Choosing where to put `distinct`.** Given `["A", "B", "A", "C", "D", "C"]`, get two **distinct values** after the first distinct value. Write the correct pipeline.

```java
List<String> unique = Arrays.asList("A", "B", "A", "C", "D", "C")
    .stream()
    .distinct()
    .skip(1)
    .limit(2)
    .collect(Collectors.toList()); // [B, C]
```

**Explanation:** `distinct()` must process the necessary prefix before positions are counted on the deduplicated sequence.

**Exercise 4 — Last page.** A List has seven elements. Paginating with page size three, 1-based page numbers: how many elements are on pages 1, 2, 3, and 4?

**Answer:** `3, 3, 1, 0`, respectively. `skip(9)` on a seven-element List yields an empty Stream; `limit(3)` cannot fabricate extra elements.

**Exercise 5 — Performance.** Why might `parallelStream().sorted().skip(1000).limit(10)` not be faster than a sequential pipeline?

**Answer:** `sorted` usually must collect and sort the entire source before slicing, while `skip`/`limit` must preserve exact positions by encounter order. The overhead of splitting, sorting, and merging results can outweigh parallel gains, especially on small or poorly splittable sources.

## Key Takeaways

`skip(n)` discards up to the first `n` elements **at its position in the pipeline**, whereas `limit(n)` allows at most `n` subsequent elements through and enables short-circuiting. The `skip(offset).limit(pageSize)` pair is the standard way to slice and paginate in the Java Stream API, but results only have a **deterministic positional** meaning when the pipeline has an appropriate encounter order. Reason carefully about the ordering of `filter`, `distinct`, and `sorted` relative to slicing before optimizing, guard against offset overflow and the cost of skipping large volumes, and watch out for infinite sources and ordering constraints in parallel execution.
