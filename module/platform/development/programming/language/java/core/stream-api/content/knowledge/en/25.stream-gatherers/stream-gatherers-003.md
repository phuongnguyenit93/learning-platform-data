# Splitting Fixed Windows with `Gatherers.windowFixed`

In the **Java Stream API**, operations such as `filter`, `map`, `reduce`, and `collect` typically process each element individually or aggregate the entire source. However, many real-world tasks require processing **batches of consecutive elements**: sending data in batches, summing every three transactions, packaging log lines for reporting, or dividing a measurement sequence into non-overlapping groups.

Starting in **Java 24**, the **Stream Gatherers** API provides `Gatherers.windowFixed(windowSize)` to express this partitioning directly. A Gatherer is an intermediate operation capable of holding state; it is inserted into a pipeline via `Stream.gather(...)`, allowing the output to be **windows** containing multiple source elements.

This lesson belongs to the **Stream Gatherer** chapter of the `JAVA_STREAM_API` module. We will learn how to split fixed windows, handle an incomplete final window, combine with `map`, `filter`, and `collect`, distinguish fixed windows from sliding windows, and recognize constraints around ordering, memory, resources, and performance.

## 1. What is a fixed window?

Given a sequence with encounter order:

```text
Source:   [1, 2, 3, 4, 5, 6, 7, 8]
                         windowSize = 3

Window 1: [1, 2, 3]
Window 2:          [4, 5, 6]
Window 3:                   [7, 8]
```

Each window receives **at most `windowSize` consecutive elements in encounter order**. The windows:

- **Do not overlap**: a source element belongs to a single window.
- **Preserve the relative order** of elements within the window.
- Are emitted one by one from left to right for a source with encounter order.
- **Do not have to be full at the end**: if 1–2 elements remain when `windowSize = 3`, they form a shorter final window.

This is a **count-based tumbling window**, not a time window. `windowFixed(3)` means three elements, **not three seconds or three minutes**.

Notation: if a finite source has `n` elements and window size `k > 0`, the number of windows is:

\[
\operatorname{windows}(n,k) =
\begin{cases}
0, & n=0 \\
\lceil n/k \rceil, & n>0
\end{cases}
\]

Each full window has `k` elements. The last window has the remainder `n % k` if the remainder is nonzero; when `n` is divisible by `k`, **no extra empty window is created**.

## 2. JDK version and API signature

`Gatherer`, `Gatherers`, and `Stream.gather` are official APIs starting in **Java 24**. Java 22 and 23 included Stream Gatherers as a **preview** feature, requiring preview flags and attention to differences between releases. This lesson uses the stable API syntax of Java 24+.

Method signature:

```java
public static <TR> Gatherer<TR, ?, List<TR>>
windowFixed(int windowSize);
```

Parts:

| Part | Meaning |
| --- | --- |
| `TR` | Source element type, and also the element type inside each window. |
| `windowSize` | Maximum number of elements in each window; must be **at least 1**. |
| `Gatherer<TR, ?, List<TR>>` | A Gatherer that receives `TR` elements and emits `List<TR>`. |
| `Stream.gather(...)` | Inserts the Gatherer into a pipeline as an intermediate operation. |

Minimal example:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [4, 5, 6], [7, 8]]
```

After `gather`, each element flowing downstream in the pipeline **is no longer an `Integer`**, but a **`List<Integer>`**. Therefore, a subsequent `map` processes **one window**, such as `map(List::size)` or `map(batch -> batch.stream().mapToInt(...).sum())`.

### When `windowSize` is invalid

```java
import java.util.stream.Gatherers;

Gatherers.windowFixed(1);   // Valid
Gatherers.windowFixed(20);  // Valid, even if the source only has 3 elements

// Throws IllegalArgumentException:
// Gatherers.windowFixed(0);
// Gatherers.windowFixed(-3);
```

The precondition is checked on **the size parameter**, independent of whether the source is empty. Do not use `windowSize = 0` to represent an empty batch; if "no processing" is needed, handle that condition before creating the Gatherer.

## 3. Edge cases to remember

This is the behavior specified by the API:

| Source | `windowSize` | Result |
| --- | ---: | --- |
| `[]` | 3 | `[]` |
| `[1]` | 3 | `[[1]]` |
| `[1,2]` | 3 | `[[1,2]]` |
| `[1,2,3]` | 3 | `[[1,2,3]]` |
| `[1,2,3,4]` | 3 | `[[1,2,3],[4]]` |
| `[1,2,3,4,5,6]` | 3 | `[[1,2,3],[4,5,6]]` |
| `[1,2,3]` | 1 | `[[1],[2],[3]]` |
| `[1,2,3]` | 10 | `[[1,2,3]]` |

Specifically:

1. **An empty source creates no empty window.** The result is an empty stream, so `toList()` returns an empty outer list.
2. **A source shorter than the window size still creates one window**, provided the source has at least one element.
3. **No remainder is dropped.** A shorter final window is valid behavior, not an error.
4. `windowSize = 1` wraps each element in a single-element list; it is not an optimal tool if the goal is only to `map` each element.

Quick check with Java 24+:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<String>> empty = Stream.<String>empty()
    .gather(Gatherers.windowFixed(4))
    .toList();

List<List<String>> shortInput = Stream.of("A", "B")
    .gather(Gatherers.windowFixed(4))
    .toList();

System.out.println(empty);      // []
System.out.println(shortInput); // [[A, B]]
```

If the business rule **only accepts full batches of `k` elements**, that is an extra application requirement, not the default contract of `windowFixed`.

## 4. Complete example: creating batches from a list of transaction IDs

Suppose a system needs to split transaction IDs into batches of at most three IDs for display, reconciliation, or forwarding to another processing step.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Gatherers;

public class FixedWindowDemo {
    public static void main(String[] args) {
        List<String> transactionIds = Arrays.asList(
            "TX-001", "TX-002", "TX-003",
            "TX-004", "TX-005", "TX-006",
            "TX-007"
        );

        List<List<String>> batches = transactionIds.stream()
            .gather(Gatherers.windowFixed(3))
            .toList();

        for (List<String> batch : batches) {
            System.out.println(batch);
        }
    }
}
```

Output:

```text
[TX-001, TX-002, TX-003]
[TX-004, TX-005, TX-006]
[TX-007]
```

This pipeline is:

```text
List<String>
   |
   +--> stream()                 Stream<String>
   |
   +--> gather(windowFixed(3))   Stream<List<String>>
   |
   +--> toList()                 List<List<String>>
```

Because the source is a `List` with encounter order, the order of IDs within each batch matches their order of appearance. If the original transaction IDs are not yet in business order (for example, not sorted by timestamp), `windowFixed` **does not sort them automatically**.

## 5. Returned windows are unmodifiable

According to the Java 24 contract, **each window** emitted by `windowFixed` is an **unmodifiable** `List`. Calling methods that alter the window structure such as `add`, `remove`, or `set` will be rejected with `UnsupportedOperationException`.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> batches = Stream.of(10, 20, 30, 40)
    .gather(Gatherers.windowFixed(3))
    .toList();

List<Integer> first = batches.get(0);
System.out.println(first); // [10, 20, 30]

// first.add(99);     // UnsupportedOperationException
// first.set(0, 99);  // UnsupportedOperationException
// first.remove(0);   // UnsupportedOperationException
```

Distinguish clearly:

- **The inner window list** is guaranteed by `windowFixed` to be unmodifiable.
- **The outer list** in the example is also unmodifiable because `Stream.toList()` (Java 16+) is used.
- **The element objects inside** may still be mutable. An unmodifiable window **does not automatically deep-copy** each element.

For example, if windows hold `StringBuilder` objects, a caller can still call `append` on a `StringBuilder` that was already emitted:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

StringBuilder value = new StringBuilder("A");

List<List<StringBuilder>> batches = Stream.of(value)
    .gather(Gatherers.windowFixed(2))
    .toList();

value.append("B");
System.out.println(batches.get(0).get(0)); // AB
```

If a truly immutable snapshot is required, convert elements to immutable value types or copy the necessary properties **before or during batch creation**. Holding an unmodifiable window does not guarantee that element data has permanently fixed state.

## 6. Processing each window with `map`, `filter`, and `collect`

The strength of `windowFixed` is that it returns a **Stream of windows**, so the pipeline can continue.

### Computing the sum of every three elements

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<Integer> totals = IntStream.rangeClosed(1, 8)
    .boxed()
    .gather(Gatherers.windowFixed(3))
    .map(batch -> batch.stream()
        .mapToInt(Integer::intValue)
        .sum())
    .toList();

System.out.println(totals); // [6, 15, 15]
```

Result explanation: `[1,2,3]` sums to 6; `[4,5,6]` sums to 15; `[7,8]` also sums to 15. **No 0s are automatically padded** into the last batch unless a business rule explicitly requires it.

`IntStream` does not have a direct `gather` matching Java 24's `Stream<T>.gather` signature. Therefore, `.boxed()` in the example converts `IntStream` to `Stream<Integer>` before calling `gather`. This creates `Integer` objects; with massive volumes of numbers and high performance requirements, measure the boxing cost or choose another approach.

### Keeping only windows whose sum exceeds a threshold

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> largeWindows = Stream.of(1, 2, 3, 8, 9, 10, 4)
    .gather(Gatherers.windowFixed(3))
    .filter(batch -> batch.stream()
        .mapToInt(Integer::intValue).sum() >= 20)
    .toList();

System.out.println(largeWindows); // [[8, 9, 10]]
```

Here `filter` is applied **after windowing**, meaning it **drops entire windows** that do not meet the requirement, rather than dropping individual elements before windowing.

### Counting windows, not source elements

```java
import java.util.stream.Gatherers;
import java.util.stream.Stream;

long windowCount = Stream.of("A", "B", "C", "D", "E")
    .gather(Gatherers.windowFixed(2))
    .count();

System.out.println(windowCount); // 3
```

After `gather`, `count()` counts **the number of lists emitted**, not the number of elements inside those lists.

## 7. `filter` placement changes window boundaries

Two pipelines look similar but have different meanings:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> filterFirst = Stream.of(1, 2, 3, 4, 5, 6)
    .filter(n -> n % 2 == 0)
    .gather(Gatherers.windowFixed(2))
    .toList();

List<List<Integer>> filterWindows = Stream.of(1, 2, 3, 4, 5, 6)
    .gather(Gatherers.windowFixed(2))
    .filter(batch -> batch.contains(2))
    .toList();

System.out.println(filterFirst);   // [[2, 4], [6]]
System.out.println(filterWindows); // [[1, 2]]
```

- **`filter` before `gather`**: excluded elements take no slot in any window; the remaining elements are grouped from the start in their new sequence.
- **`filter` after `gather`**: boundaries are already fixed; the predicate decides whether to keep or drop **the entire batch**.

Similarly, if `sorted()` is called before `gather`, windows are formed in **the sorted order**; if `distinct()` is called before `gather`, element counts and boundaries can change. Thus **the placement of intermediate operations is part of the business requirement**, not just a coding detail.

## 8. How do `limit` before and after windowing differ?

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<List<Integer>> firstFiveItems = IntStream.rangeClosed(1, 8)
    .boxed()
    .limit(5)
    .gather(Gatherers.windowFixed(3))
    .toList();

List<List<Integer>> firstTwoWindows = IntStream.rangeClosed(1, 8)
    .boxed()
    .gather(Gatherers.windowFixed(3))
    .limit(2)
    .toList();

System.out.println(firstFiveItems);  // [[1, 2, 3], [4, 5]]
System.out.println(firstTwoWindows); // [[1, 2, 3], [4, 5, 6]]
```

In the first pipeline, `limit(5)` limits **five source elements** before windowing. In the second pipeline, `limit(2)` limits **two elements of the window stream** — meaning two lists, totaling six values in the example.

This is a form of **short-circuiting**: the terminal operation can finish without exhausting the source once downstream has received enough windows. However, you should not rely on the number of mapper/`peek` invocations to assert that the system always reads exactly `2 * windowSize` elements: optimizations, buffering, and consumption strategy can affect observed operation counts.

With infinite sources, a stopping condition is generally required:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> firstThreeBatches =
    Stream.iterate(1, n -> n + 1)
        .gather(Gatherers.windowFixed(4))
        .limit(3)
        .toList();

System.out.println(firstThreeBatches);
// [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
```

Never call `toList()` on all windows of **an unbounded infinite source**, because the terminal operation cannot complete and retaining the data will consume unbounded resources.

## 9. Handling an incomplete final window

`windowFixed` **keeps the remainder**. Applications need to choose one of the following policies:

| Policy | When applied | With `[1,2,3,4,5]`, `k=3` |
| --- | --- | --- |
| **Accept a short final batch** | Batch API allows counts from 1 to `k`. | `[[1,2,3],[4,5]]` |
| **Process full batches only** | Algorithm strictly requires `k` values. | `[[1,2,3]]`; remainder must be handled separately if needed. |
| **Pad to full element count** | Protocol has a well-defined padding value. | `[[1,2,3],[4,5,PAD]]` |
| **Reject incomplete input** | Entire dataset size must be divisible by `k`. | Report error before or after size validation. |

### Keeping full batches only

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

int batchSize = 3;

List<List<Integer>> complete = IntStream.rangeClosed(1, 8)
    .boxed()
    .gather(Gatherers.windowFixed(batchSize))
    .filter(batch -> batch.size() == batchSize)
    .toList();

System.out.println(complete); // [[1, 2, 3], [4, 5, 6]]
```

This choice **drops the last two elements** from the result. In transaction systems, payment processing, or critical logs, **never discard the remainder silently**. You must decide explicitly whether remaining data is held for the next batch, processed separately, or flagged as an error.

### Padding the remainder with a placeholder value

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

int batchSize = 3;

List<List<String>> padded = Stream.of("A", "B", "C", "D", "E")
    .gather(Gatherers.windowFixed(batchSize))
    .map(batch -> {
        List<String> copy = new ArrayList<>(batch);
        while (copy.size() < batchSize) {
            copy.add("MISSING");
        }
        return List.copyOf(copy);
    })
    .toList();

System.out.println(padded);
// [[A, B, C], [D, E, MISSING]]
```

You must **create a copy** before adding elements, because the list emitted by `windowFixed` is unmodifiable. In the example, `"MISSING"` is only a placeholder value; with real data, ensure the padding value can never be mistaken for a real transaction or measurement.

## 10. How does `windowFixed` differ from `windowSliding`?

Both create count-based windows, but **the window-shifting rule** differs:

```text
Source:      [1, 2, 3, 4, 5, 6, 7]

Fixed(3):    [1, 2, 3]
                      [4, 5, 6]
                               [7]

Sliding(3):  [1, 2, 3]
                [2, 3, 4]
                   [3, 4, 5]
                      [4, 5, 6]
                         [5, 6, 7]
```

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<Integer> source = IntStream.rangeClosed(1, 7)
    .boxed()
    .toList();

List<List<Integer>> fixed = source.stream()
    .gather(Gatherers.windowFixed(3))
    .toList();

List<List<Integer>> sliding = source.stream()
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(fixed);
// [[1, 2, 3], [4, 5, 6], [7]]

System.out.println(sliding);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6], [5, 6, 7]]
```

| Property | `windowFixed(k)` | `windowSliding(k)` |
| --- | --- | --- |
| Boundaries | Splits into **non-overlapping** consecutive groups. | Each next group slides forward by **one element**. |
| How many groups does an element appear in? | At most one. | May appear in multiple groups. |
| Last group size | May be shorter than `k`. | For sources with at least `k` elements, sliding groups have full `k`; if shorter than `k`, there is one short group. |
| Number of groups when `n > 0` | `ceil(n / k)`. | `1` if `n < k`; if `n >= k`, there are `n - k + 1` groups. |
| Best suited for | Batch packaging, per-batch aggregation. | Moving averages, comparing adjacent value sequences. |

For example, summing over **non-overlapping daily batches** should use a fixed window. If you need **the average of three consecutive measurements at each position**, a sliding window is more appropriate. Do not call `windowFixed` and expect overlapping results like a rolling average.

## 11. Windows by element order, not grouping by key

`Collectors.groupingBy` classifies elements sharing the **same key**. `Gatherers.windowFixed` partitions by **relative position in an ordered sequence**.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<String> events = List.of("A", "B", "A", "B", "A");

List<List<String>> batches = events.stream()
    .gather(Gatherers.windowFixed(2))
    .toList();

Map<String, List<String>> byValue = events.stream()
    .collect(Collectors.groupingBy(value -> value));

System.out.println(batches); // [[A, B], [A, B], [A]]
System.out.println(byValue.get("A")); // [A, A, A]
```

You cannot replace `windowFixed(k)` with `groupingBy(value -> value)` if the goal is batches of `k` consecutive elements. Similarly, `partitioningBy` splits into two boolean groups rather than packaging by element count.

If the source is a `HashSet` or a stream without encounter order, element positions are not guaranteed to be stable according to business order. **Fixed windows are most meaningful on sources with a clear encounter order**, such as `List` or `Stream.of(...)`.

## 12. Real-world project: generating a transaction batch report

Suppose each transaction has an ID and an amount in **minor integer units**. Every three consecutive transactions form a batch; for each batch, we want the transaction count and total amount.

Here is a complete Java 24+ program:

```java
import java.util.List;
import java.util.stream.Gatherers;

public class TransactionBatchReport {
    record Transaction(String id, long amountInMinorUnits) {}

    record BatchSummary(
        String firstTransaction,
        String lastTransaction,
        int transactionCount,
        long totalAmount
    ) {}

    static BatchSummary summarize(List<Transaction> batch) {
        long total = batch.stream()
            .mapToLong(Transaction::amountInMinorUnits)
            .sum();

        return new BatchSummary(
            batch.get(0).id(),
            batch.get(batch.size() - 1).id(),
            batch.size(),
            total
        );
    }

    public static void main(String[] args) {
        List<Transaction> data = List.of(
            new Transaction("T-01", 1200L),
            new Transaction("T-02", 1800L),
            new Transaction("T-03", 3000L),
            new Transaction("T-04",  500L),
            new Transaction("T-05",  700L),
            new Transaction("T-06", 1100L),
            new Transaction("T-07",  250L)
        );

        List<BatchSummary> report = data.stream()
            .gather(Gatherers.windowFixed(3))
            .map(TransactionBatchReport::summarize)
            .toList();

        report.forEach(System.out::println);
    }
}
```

Output has three report lines corresponding to the batches:

```text
BatchSummary[firstTransaction=T-01, lastTransaction=T-03,
             transactionCount=3, totalAmount=6000]
BatchSummary[firstTransaction=T-04, lastTransaction=T-06,
             transactionCount=3, totalAmount=2300]
BatchSummary[firstTransaction=T-07, lastTransaction=T-07,
             transactionCount=1, totalAmount=250]
```

Points to note:

1. `data.stream()` has an encounter order matching the transaction list.
2. `gather(windowFixed(3))` partitions into three batches, preserving the final transaction.
3. `summarize(batch)` can safely call `get(0)` because **there are no empty windows**.
4. Each `BatchSummary` result is a record containing only `String` and primitives, suitable for publishing immutable data.
5. If the number of transactions is very large, using `sum()` on `long` can still overflow. Financial systems need bounds checks, `Math.addExact`, or an appropriate numeric type.

The program uses batches for **aggregation**, not for actual network calls or DB writes. If you replace `summarize` with a side-effecting API, you also need concurrency limits, retries, idempotency, timeouts, and partial-batch failure handling; `windowFixed` does not provide atomic transactions or exactly-once delivery on its own.

## 13. Producing a report without holding every window until the end

`toList()` on a stream of windows **retains all windows** in a result list. When the source is very large, this can consume a lot of memory.

If only final metrics are needed, you can compute them inside `map` and collect a smaller result, or aggregate further:

```java
import java.util.LongSummaryStatistics;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

LongSummaryStatistics sumsOfBatches = IntStream.rangeClosed(1, 1_000)
    .boxed()
    .gather(Gatherers.windowFixed(100))
    .mapToLong(batch -> batch.stream()
        .mapToLong(Integer::longValue)
        .sum())
    .summaryStatistics();

System.out.println(sumsOfBatches.getCount()); // 10 batches
System.out.println(sumsOfBatches.getSum());   // 500500
```

Here, the terminal operation returns **a summary statistics object of batch sums**, rather than a nested list holding all 1,000 values. If you only need the total sum of the entire source, `IntStream.rangeClosed(1, 1_000).asLongStream().sum()` is simpler and needs no windowing.

### With I/O sources such as `Files.lines`

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FileBatchSizes {
    public static List<Integer> countLinesPerBatch(Path path)
            throws IOException {
        try (Stream<String> lines =
                Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .gather(Gatherers.windowFixed(500))
                .map(List::size)
                .toList();
        }
    }
}
```

`Files.lines` holds an I/O resource, so `try-with-resources` is required to close the stream. `collect`, `toList`, or `gather` **do not replace the responsibility of closing the source**. In this example, the output is a list of **line counts per batch**, not retaining the entire file content.

However, if the file has extremely long lines or a huge number of batches, you still need to account for total memory. If the source requires consistency (e.g., the file changes while being read), `windowFixed` does not automatically lock or snapshot the data source.

## 14. Memory considerations and window size

According to the `Gatherers.windowFixed` API documentation, windows may be **allocated greedily and eagerly** for efficiency. This has a notable consequence: choosing an enormous `windowSize` for a very short source can consume memory **disproportionate to the actual data volume**.

Example:

```java
import java.util.stream.Gatherers;
import java.util.stream.Stream;

// Avoid doing this out of habit: a huge window size
// does not automatically become cheap just because the source has 2 elements.
var windows = Stream.of("A", "B")
    .gather(Gatherers.windowFixed(1_000_000));
```

The snippet above only illustrates a **configuration risking large allocation**, without asserting exact byte counts or allocation timing on every JDK. Choose the window size according to resource limits, data characteristics, and actual processing requirements.

Distinguish two memory layers:

- **Gatherer buffer**: holds the elements needed to form one window; cost relates to `windowSize` and the implementation.
- **Terminal operation result**: `toList()` holds all emitted windows; if you want streaming per-batch processing without retaining everything, use an appropriate terminal operation/downstream.

Note that `windowFixed` can help **process in batches**, but does not automatically solve memory limits of all downstream operations. A `map(batch -> hugeObject)` followed by `toList()` can still consume a huge amount of memory.

## 15. Ordering, parallelism, and processing semantics

Fixed windows are **order-dependent**. Given `[1,2,3,4,5,6]`, we expect `[[1,2,3],[4,5,6]]`, not random groups simply because two workers were used.

Points to remember:

1. On a source with encounter order, windows preserve element order per the API contract.
2. If the source is inherently **unordered** or `unordered()` was called, do not expect specific elements to land in specific batches in business order.
3. Adding `parallel()` **does not guarantee speedup**. Windowing is a stateful, boundary-dependent intermediate operation; execution also depends on source splittability and Gatherer implementation.
4. Do not mutate a source `ArrayList` inside `map`/`forEach` while the Stream is traversing it. Lambda behavior should be *non-interfering* and, if possible, *stateless*.
5. Do not assume `windowFixed` dispatches batches to a worker pool with a specific task count or execution order.

If you need to **process each batch concurrently** after windowing, that is a separate requirement from **windowing**. Java 24 also provides `Gatherers.mapConcurrent(maxConcurrency, mapper)` to handle mapping with bounded concurrency while still preserving output order per contract. Only use it when the mapper fits, each batch is processed independently, and you have defined error and side-effect handling.

Example of a **pure computation**, performing no I/O:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<Integer> totals = IntStream.rangeClosed(1, 12)
    .boxed()
    .gather(Gatherers.windowFixed(3))
    .gather(Gatherers.mapConcurrent(
        2,
        batch -> batch.stream().mapToInt(Integer::intValue).sum()
    ))
    .toList();

System.out.println(totals); // [6, 15, 24, 33]
```

This example illustrates **chaining two Gatherers**. It does not prove `mapConcurrent` is faster than regular `map`; for summing three numbers, concurrency overhead is hardly worth choosing before benchmarking.

## 16. Comparison with index-based List splitting before Java 24

Before Stream Gatherers, if the source was already an indexed `List` and you wanted to split by position, you could use `IntStream.range` or `subList`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> source = List.of(1, 2, 3, 4, 5, 6, 7, 8);
int batchSize = 3;

List<List<Integer>> batches = IntStream
    .range(0, (source.size() + batchSize - 1) / batchSize)
    .mapToObj(batchIndex -> {
        int from = batchIndex * batchSize;
        int to = Math.min(from + batchSize, source.size());
        return List.copyOf(source.subList(from, to));
    })
    .toList();

System.out.println(batches); // [[1, 2, 3], [4, 5, 6], [7, 8]]
```

This is a reasonable choice when you already have an **indexed-access** list. This pattern uses `List.copyOf` (Java 10+) to create unmodifiable window lists, without deep-copying elements. If elements can be `null`, `List.copyOf` will reject `null`, so a data policy is needed before applying it.

Another point: `source.subList(from, to)` **is usually a view** backed by the original list, not an independent snapshot. Returning `subList`s directly can cause source modifications to affect results or invalidate the view. Creating a copy avoids structural dependency on the original list, though it still only copies references to elements.

`windowFixed` does not require the source to be an indexed `List`; it works on any `Stream<T>` and preserves the declarative style of the pipeline. When data originates from an iterator, file, or a stream that has passed through several transformations, it can be the cleaner API to express intent.

## 17. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `windowFixed` with `k = 0` or a negative number | `IllegalArgumentException`. | Enforce `k >= 1`. |
| Expecting the last batch to always have `k` elements | Trailing records may be mishandled. | Accept, pad, reject, or keep remainder per policy. |
| Thinking `windowFixed(3)` means three seconds | Confusing count-based with time-based windows. | Use proper time-windowing tools if needed. |
| Passing `IntStream` directly to `gather` | `gather` API is for reference `Stream<T>`. | Use `boxed()` or other primitive processing options. |
| Calling `window.add(...)` on a result window | `UnsupportedOperationException`. | Copy to a mutable collection if modification is needed. |
| Placing `filter` in the wrong position | Window boundaries change or whole batches are dropped. | Decide whether to filter elements or filter windows. |
| Using `limit(2)` after `gather` expecting only 2 elements | Actually takes at most **2 windows**. | Place `limit` at the level of data you want to cap. |
| Using a huge window on a short source | Risks excessive memory allocation. | Choose a finite, resource-appropriate `windowSize`. |
| Using `toList()` to hold all batches of a huge source | Output consumes a lot of memory. | Aggregate or consume batch by batch when appropriate. |
| Using an unordered source while expecting stable groups | Loses positional meaning in business order. | Provide explicit encounter order before splitting. |
| Sending batches to an API in `forEach` assuming atomic transaction | Partial send can occur before an error. | Design retries, idempotency, concurrency limits, and monitoring separately. |
| Comparing `windowFixed` and `windowSliding` while ignoring overlap | Wrong batch count and totals. | Choose the windowing rule matching the requirement. |

## 18. Testing window boundaries

When you need to ensure **no missing or duplicated elements**, test across multiple input sizes. Java 24+ example:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class WindowFixedCheck {
    static void check(int n, int size) {
        List<Integer> source = IntStream.range(0, n)
            .boxed()
            .toList();

        List<List<Integer>> windows = source.stream()
            .gather(Gatherers.windowFixed(size))
            .toList();

        List<Integer> flattened = windows.stream()
            .flatMap(List::stream)
            .toList();

        if (!flattened.equals(source)) {
            throw new AssertionError("Missing, duplicated, or reordered elements");
        }

        int expectedWindows = n == 0
            ? 0
            : 1 + (n - 1) / size;
        if (windows.size() != expectedWindows) {
            throw new AssertionError("Incorrect window count");
        }

        for (int i = 0; i < windows.size(); i++) {
            int expectedSize = Math.min(size, n - i * size);
            if (windows.get(i).size() != expectedSize) {
                throw new AssertionError("Incorrect size for window " + i);
            }
        }
    }

    public static void main(String[] args) {
        for (int k : new int[] {1, 2, 3, 8}) {
            for (int n = 0; n <= 30; n++) {
                check(n, k);
            }
        }
        System.out.println("Window checks passed");
    }
}
```

Some invariants worth testing:

- **Element integrity**: flattening the windows of an ordered source must yield the original sequence (when there is no `filter` or transformation changing element count).
- **Window count**: `0` if source is empty; otherwise `ceil(n/k)`.
- **Sizes**: every window except the last has exactly `k` elements; the last window has between 1 and `k`.
- **Unmodifiability**: calling a mutator method on a result window must be rejected.
- **No data loss at boundaries**: specifically test `n = k - 1`, `n = k`, `n = k + 1`, `n = 2k`, `n = 2k + 1`.

These checks verify behavior for the tested inputs; they are not performance benchmarks or proof of all concurrent/unordered source cases.

## 19. Practice exercises

**Exercise 1 — Basic windows.** From `Stream.of(10,20,30,40,50,60,70)`, use `windowFixed(3)` and predict the three resulting lists. Explain why the final window has only one element.

**Exercise 2 — Filtering in the right place.** With source `[1,2,3,4,5,6]` and `k=2`, compare `filter(n -> n % 2 == 0)` before `gather` with `filter(batch -> batch.contains(2))` after `gather`. Write clearly the difference in window count and contents.

**Exercise 3 — Keeping or dropping the remainder.** Given eight transaction IDs and `k=3`. Collect all batches first; then keep only batches with exactly three elements. How many transactions are dropped? If these are financial transactions, propose a zero-data-loss policy.

**Exercise 4 — Sum per batch.** Using `IntStream.rangeClosed(1, 10).boxed()`, split with `windowFixed(4)` and sum each batch. Expected output is `[10,26,19]`.

**Exercise 5 — Comparing sliding.** With `[1,2,3,4,5]`, write the outputs of `windowFixed(3)` and `windowSliding(3)`. Why would summing the sliding windows count several elements more than once?

**Exercise 6 — Memory and API.** Why can `windowFixed(1_000_000)` on a stream with only two elements still cause memory pressure? Why is `toList()` holding every window of a huge source not a memory-efficient pipeline?

**Exercise 7 — Invariant testing.** Write a `check(n,k)` function to verify: no missing/duplicated elements; valid size for each window; exact window count; returned windows are unmodifiable. Run on an empty source and sizes right before/after multiples of `k`.

**Exercise 8 — Batch report.** From `Stream<Transaction>`, produce a report containing count, total amount, and first/last ID of each batch using `windowFixed(100)`. If real API calls are added, describe how to avoid duplicate sends, limit concurrent tasks, and handle an error occurring in only one batch.

## 20. Adoption checklist

- [ ] Project uses Java 24+ for the official Stream Gatherers API.
- [ ] Source has encounter order if preserving batch order is required.
- [ ] `windowSize` is validated to be greater than 0 and reasonably bounded.
- [ ] Policy for handling the trailing remainder is written as a business requirement.
- [ ] Distinguished `filter` on elements from `filter` on windows.
- [ ] Distinguished `limit` on source elements from `limit` on window count.
- [ ] Never call `add`, `remove`, or `set` on windows returned by Gatherer.
- [ ] Checked mutability of element objects if data snapshots are needed.
- [ ] Not using `windowFixed` in place of time windows or sliding windows.
- [ ] Not retaining all windows in memory when input is large and full retention is unnecessary.
- [ ] Considered resources and stream closing for I/O sources.
- [ ] Not assuming parallelization or performance gains without measuring.
- [ ] If batch processing has side effects, separate policies exist for retry, idempotency, and error reporting.
- [ ] Tested empty source, `k=1`, `n<k`, `n=k`, and `n=k+1`.

**Remember:** `Gatherers.windowFixed(k)` splits an ordered `Stream<T>` into a `Stream<List<T>>` of **consecutive, non-overlapping** groups, each with at most `k` elements. Empty sources have no windows; the final window may be shorter; each window is guaranteed to be **unmodifiable**. Place `map`, `filter`, and `limit` in the right positions, choose a resource-appropriate batch size, and only use windowing when the problem truly requires batch processing.

**Official documentation:** [Gatherers.windowFixed — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html#windowFixed(int)); [Stream Gatherers — Oracle Java 24 Guide](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html); [Stream.gather — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html#gather(java.util.stream.Gatherer)).
