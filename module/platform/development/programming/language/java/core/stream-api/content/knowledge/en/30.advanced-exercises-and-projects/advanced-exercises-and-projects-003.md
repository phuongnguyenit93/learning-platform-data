# Designing a Spliterator for Batch-Split Data Sources

## 1. Problem Statement and Project Goals

In the **`JAVA_STREAM_API`** module, we have used declarative pipelines with data sources, lazy operations such as `filter` and `map`, and terminal operations such as `reduce` and `collect`. At an advanced level, to process a large source with `parallelStream`, we must understand how to **split data into independently processable units of work**.

Suppose a program receives 40,000 records from a preloaded list. Business logic needs to transform each record, filter valid data, and compute a sum. We want each split attempt on the source to produce a **batch of at most B elements** to control work unit size.

We will design a custom `Spliterator<T>` named `BatchSpliterator<T>`, wire it into `StreamSupport.stream(...)`, and verify:

- Are **all elements present**?
- Is **any element duplicated** across batches?
- If the source is ordered, do batches preserve **encounter order**?
- Is `estimateSize` accurate after each split and consumption?
- Do `reduce` / `collect` results on a parallel stream match the true result from the source?
- How do large batches, small batches, and source-copying policies affect performance and memory?

**Learning outcome:** not only will you know how to implement `trySplit`, you will also understand the `ORDERED`, `SIZED`, and `SUBSIZED` contracts, how the Stream runtime splits work, and how to design tests capable of catching dropped or duplicated data.

This lesson belongs to the **Advanced Exercises and Projects** chapter. It is an integrative project covering Spliterator, parallel streams, `filter`, `map`, `reduce`, `collect`, and constraints around state, resources, and performance. This guide does not assume parallel execution is always faster than sequential execution.

## 2. What Does "Splitting by Batch" Mean?

A **batch** in this lesson is a **contiguous slice of elements** from an ordered source. Each successful `trySplit()` splits off a **prefix** of at most `batchSize` elements into a new spliterator.

Example source:

```text
Ordered source: [1, 2, 3, 4, 5, 6, 7, 8]
batchSize = 3

Initial Spliterator: [1, 2, 3, 4, 5, 6, 7, 8]
  ├─ split 1 -> [1, 2, 3]     | remaining [4, 5, 6, 7, 8]
  └─ split 2 -> [4, 5]        | remaining [6, 7, 8]

Final chunks: [1, 2, 3] | [4, 5] | [6, 7, 8]
```

With the algorithm used in this lesson, **`batchSize` is the maximum size of a work chunk once splitting finishes**; it does not mean every batch must contain exactly `batchSize` elements. The split in the example only illustrates this specific algorithm; the Stream runtime does not guarantee performing exactly two splits.

Distinguish between:

1. **Batching for work splitting (`trySplit`):** determines which elements each child spliterator owns.
2. **Element-by-element consumption (`tryAdvance`):** still delivers **one element at a time** to the `filter`, `map` pipeline.
3. **I/O or network batching:** a mechanism for fetching groups of records from a database or service, with its own resource lifecycle. The `List`-backed `BatchSpliterator` in this lesson **does not itself perform batched queries**.

### Setting Requirements Before Writing Code

| Requirement | Invariant to Maintain |
| --- | --- |
| No lost elements | The union of all split parts and the remainder equals the original index set. |
| No duplicate elements | Index ranges of any two child spliterators are disjoint. |
| Order preserved | With `ORDERED`, `trySplit` returns a prefix of the untraversed range. |
| Known size | `estimateSize()` equals the number of remaining positions in the range. |
| Finite splitting | When a range has at most B elements left, `trySplit()` returns `null`. |
| No shared cursor | Each spliterator has its own `index`; only stable read-only data is shared. |
| No hidden errors | Invalid `batchSize` must be rejected explicitly. |

If any invariant is missing, bugs might not show up in sequential `stream()` and only surface when parallelized via `StreamSupport.stream(spliterator, true)`.

## 3. Methods and Characteristics You Must Understand

`Spliterator<T>` has five core methods:

| API | Contract |
| --- | --- |
| `boolean tryAdvance(Consumer<? super T> action)` | Emits at most one element; returns `true` if emitted, `false` if exhausted. |
| `void forEachRemaining(Consumer<? super T> action)` | Emits all remaining elements. |
| `Spliterator<T> trySplit()` | Attempts to split off a partition for independent processing; returns `null` if not split. |
| `long estimateSize()` | Estimates unconsumed element count; exact when `SIZED` is declared. |
| `int characteristics()` | Declares properties of the source and its splits. |

Important flags:

- **`ORDERED`:** the source has an encounter order; split spliterators must maintain proper prefix/suffix relationships.
- **`SIZED`:** the exact number of remaining elements is known.
- **`SUBSIZED`:** spliterators returned by `trySplit` are also `SIZED` and `SUBSIZED`.
- **`NONNULL`:** use only when guaranteed **there are no `null` values**.
- **`DISTINCT`:** use only when elements are known to be unique under `equals`.
- **`SORTED`:** use only when data truly follows an appropriate comparator and the spliterator honors the `getComparator()` contract.
- **`IMMUTABLE`:** declare only when the source cannot be structurally modified during traversal under an appropriate contract; do not equate "callers promise not to modify" with a guaranteed invariant.

Do not enable `CONCURRENT` merely because `parallel()` is used. `CONCURRENT` means the source **supports concurrent structural modification under contract**, not "multiple disjoint data partitions can be processed concurrently".

With a design using **a private `ArrayList` copy not mutated by this class**, we choose at minimum:

```java
Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED
```

Do not declare `NONNULL` because input data might contain `null`; do not declare `SORTED` or `DISTINCT` because those properties are not verified. Declaring only the accurate flags is enough for the Stream runtime to recognize splittability without "optimizing" via false claims.

## 4. Choosing the [index, fence) Range Representation

Instead of creating sublists on every split, the first version uses **half-open index intervals**:

```text
data:  [A, B, C, D, E, F, G, H]
index:  0
fence:  8
owned range: [0, 8) = A..H

After trySplit:
  returned part:   [0, 3) = A, B, C
  remaining part:  [3, 8) = D, E, F, G, H
```

Fields:

- `data`: list snapshotted from input for stable reads.
- `index`: position of the next element for the **current spliterator**.
- `fence`: **exclusive** end position.
- `batchSize`: upper bound on work chunk size after splitting.

Size invariant:

```text
0 <= index <= fence <= data.size()
estimateSize() == fence - index
```

If splitting at `cut`, we must maintain:

```text
[index_old, fence)
     = [index_old, cut)  +  [cut, fence)

two non-overlapping partitions, total size unchanged
```

**Choosing the `List` source:** we create an `ArrayList` copy via `new ArrayList<>(source)`. That makes `get(index)` fast and prevents interference if the caller adds/removes elements from the original list after creating the spliterator. This is only a **shallow copy**: if elements are mutable objects, their internal contents can still change unexpectedly.

Copying costs **O(n) memory and initialization time**. If the source is already an `ArrayList` used immutably, the built-in spliterator may be more efficient. The goal of this custom version is learning the **batch-splitting contract**, not claiming it is optimal for every source.

## 5. Complete `BatchSpliterator<T>` Implementation (Java 8+)

Place the following program in `BatchDemo.java`. It compiles and runs on Java 8 or later.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

public class BatchDemo {
    public static final class BatchSpliterator<T>
            implements Spliterator<T> {

        private final List<T> data;
        private int index;
        private final int fence;
        private final int batchSize;

        private BatchSpliterator(
                List<T> data,
                int index,
                int fence,
                int batchSize) {
            this.data = data;
            this.index = index;
            this.fence = fence;
            this.batchSize = batchSize;
        }

        public static <T> BatchSpliterator<T> snapshotOf(
                List<? extends T> source,
                int batchSize) {
            Objects.requireNonNull(source, "source");

            if (batchSize <= 0) {
                throw new IllegalArgumentException(
                    "batchSize must be > 0"
                );
            }

            // Snapshot list structure before splitting.
            List<T> snapshot = new ArrayList<>(source);
            return new BatchSpliterator<>(
                snapshot, 0, snapshot.size(), batchSize
            );
        }

        @Override
        public boolean tryAdvance(Consumer<? super T> action) {
            Objects.requireNonNull(action, "action");

            if (index >= fence) {
                return false;
            }

            T value = data.get(index);
            index++;
            action.accept(value);
            return true;
        }

        @Override
        public void forEachRemaining(Consumer<? super T> action) {
            Objects.requireNonNull(action, "action");

            while (index < fence) {
                T value = data.get(index);
                index++;
                action.accept(value);
            }
        }

        @Override
        public Spliterator<T> trySplit() {
            int remaining = fence - index;

            // Range <= batchSize is one final work chunk.
            if (remaining <= batchSize) {
                return null;
            }

            // Return prefix of at most batchSize elements.
            // Do not move everything into prefix so the remainder
            // still has data allowing further splits.
            int prefixSize = Math.min(
                batchSize, remaining / 2
            );
            int cut = index + prefixSize;

            BatchSpliterator<T> prefix =
                new BatchSpliterator<>(
                    data, index, cut, batchSize
                );

            // Current spliterator keeps only [cut, fence).
            index = cut;
            return prefix;
        }

        @Override
        public long estimateSize() {
            return fence - index;
        }

        @Override
        public int characteristics() {
            return Spliterator.ORDERED
                | Spliterator.SIZED
                | Spliterator.SUBSIZED;
        }
    }

    public static void main(String[] args) {
        List<Integer> so = IntStream.rangeClosed(1, 40)
            .boxed()
            .collect(Collectors.toList());

        List<Integer> binhPhuongChan = StreamSupport.stream(
                BatchSpliterator.snapshotOf(so, 7), true)
            .filter(n -> n % 2 == 0)
            .map(n -> n * n)
            .collect(Collectors.toList());

        long tong = StreamSupport.stream(
                BatchSpliterator.snapshotOf(so, 7), true)
            .mapToLong(Integer::longValue)
            .sum();

        System.out.println(binhPhuongChan.size()); // 20
        System.out.println(binhPhuongChan.get(0)); // 4
        System.out.println(binhPhuongChan.get(19)); // 1600
        System.out.println(tong);                  // 820
    }
}
```

Key points in the code:

1. `snapshotOf` rejects zero or negative batch sizes and copies the original list.
2. `tryAdvance` delivers one value and increments `index` exactly once.
3. `trySplit` splits only when the range has more than `batchSize` elements; the new part is the **prefix**, and the current instance becomes the suffix.
4. `estimateSize` is computed from the remaining span, so it shrinks after `tryAdvance` or `trySplit`.
5. Each child spliterator owns its own `index` / `fence`; they only **read** the shared snapshot list.
6. `StreamSupport.stream(..., true)` requests parallel mode; it **does not guarantee** multiple threads will actually run or one task will be created per batch.

Both `collect` and `sum` pipelines in `main` create a **new spliterator**. Never reuse a consumed spliterator to run a second terminal operation.

### Why `prefixSize = min(batchSize, remaining / 2)`?

If you always take a fixed `batchSize` elements when the remainder is only slightly larger than B, you can end up with one very large chunk and a leftover of just one element. The formula above takes at most B and at most half the remaining elements, avoiding heavily skewed final batches near the threshold.

For `remaining > batchSize >= 1`, `remaining / 2` is at least 1, so `trySplit` always produces two **non-empty** ranges. Once every range has at most B elements left, no further splitting occurs.

For example, with eight elements and B = 3, final batches can have sizes `3, 2, 3`. There is no guarantee of **exactly B elements per batch**, only that every final chunk is `<= B`.

## 6. Testing Batch Splitting Without Threads

Before running in parallel, test `trySplit` directly. That is the best way to catch **lost elements, duplicate elements, wrong order, and inaccurate `estimateSize`** without scheduling noise.

Place the following test class alongside `BatchDemo.java` (Java 8+):

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Spliterator;

public class BatchSplitCheck {
    static <T> void tachHet(
            Spliterator<T> current,
            List<Spliterator<T>> leaves) {

        Spliterator<T> prefix = current.trySplit();
        if (prefix == null) {
            leaves.add(current);
            return;
        }

        // Prefix must precede the remaining partition.
        tachHet(prefix, leaves);
        tachHet(current, leaves);
    }

    static void kiemTra(
            List<Integer> source,
            int batchSize) {

        BatchDemo.BatchSpliterator<Integer> root =
            BatchDemo.BatchSpliterator.snapshotOf(
                source, batchSize);

        long initial = root.estimateSize();
        if (initial != source.size()) {
            throw new AssertionError("Incorrect initial estimateSize");
        }

        List<Spliterator<Integer>> leaves = new ArrayList<>();
        tachHet(root, leaves);

        List<Integer> merged = new ArrayList<>();
        long totalSizes = 0L;

        for (Spliterator<Integer> leaf : leaves) {
            long size = leaf.estimateSize();
            if (size < 0 || size > batchSize) {
                throw new AssertionError("Incorrect batch size: " + size);
            }
            totalSizes += size;
            leaf.forEachRemaining(merged::add);
            if (leaf.estimateSize() != 0L) {
                throw new AssertionError("Batch not fully consumed");
            }
        }

        if (totalSizes != source.size()) {
            throw new AssertionError("Lost/duplicated positions on split");
        }
        if (!merged.equals(source)) {
            throw new AssertionError("Lost/duplicated/misordered elements");
        }
    }

    public static void main(String[] args) {
        kiemTra(Collections.<Integer>emptyList(), 3);
        kiemTra(Collections.singletonList(7), 3);
        kiemTra(Arrays.asList(1, 2, 3), 3);
        kiemTra(Arrays.asList(1, 2, 3, 4), 3);
        kiemTra(Arrays.asList(1, 1, 2, 2, 3, 3, 4), 2);
        kiemTra(Arrays.asList(
            1, 2, 3, 4, 5, 6, 7, 8, 9, 10), 4);

        System.out.println("PASS: split without loss/duplication/misordering");
    }
}
```

Expected output:

```text
PASS: split without loss/duplication/misordering
```

Testing a list with duplicate values is deliberate. If you only compare `Set`s of results, a buggy algorithm that drops one element while duplicating an equal value elsewhere **could still pass**. Comparing the full `List` in order detects both counts and positions.

`tachHet` uses recursion for readability; use it only with small test inputs. For millions of batches, write an iterative test using a worklist structure instead of deep recursion.

## 7. Parallel Testing: Correctness Before Performance Measurement

Keeping `BatchDemo.BatchSpliterator` unchanged, you can add sequential and parallel test cases:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

public class BatchParallelCheck {
    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static List<Integer> transformed(
            List<Integer> source,
            int batchSize,
            boolean parallel) {

        return StreamSupport.stream(
                BatchDemo.BatchSpliterator.snapshotOf(
                    source, batchSize), parallel)
            .filter(n -> n % 2 == 0)
            .map(n -> n * n)
            .collect(Collectors.toList());
    }

    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 40)
            .boxed()
            .collect(Collectors.toList());

        List<Integer> expected = source.stream()
            .filter(n -> n % 2 == 0)
            .map(n -> n * n)
            .collect(Collectors.toList());

        check(transformed(source, 1, false).equals(expected),
            "Incorrect sequential, batch 1");
        check(transformed(source, 1, true).equals(expected),
            "Incorrect parallel, batch 1");
        check(transformed(source, 7, true).equals(expected),
            "Incorrect parallel, batch 7");
        check(transformed(source, 100, true).equals(expected),
            "Incorrect parallel, batch 100");

        List<Integer> empty = Arrays.<Integer>asList();
        check(transformed(empty, 4, true).isEmpty(),
            "Incorrect on empty source");

        List<Integer> one = Arrays.asList(8);
        check(transformed(one, 4, true)
            .equals(Arrays.asList(64)), "Incorrect on single element");

        long sum = StreamSupport.stream(
                BatchDemo.BatchSpliterator.snapshotOf(source, 7), true)
            .mapToLong(Integer::longValue)
            .reduce(0L, Long::sum);

        check(sum == 820L, "Incorrect sum");
        System.out.println("PASS: sequential/parallel correct");
    }
}
```

The program cross-checks against an **independent expected result** from a sequential `List` pipeline, then tries multiple batch sizes to catch boundary bugs. Expected output:

```text
PASS: sequential/parallel correct
```

Observing a single successful run **does not prove** every declared spliterator characteristic is valid. For custom spliterators, always inspect method contracts and test edge cases, not just output equality.

## 8. Position-Preserving Invariants on Every Split

Let `L = [index, fence)` be the remaining range. If `trySplit()` returns `P = [index, cut)`, then after the operation:

```text
L before = P after  ∪  L remaining after
P ∩ L remaining = ∅
|L before| = |P| + |L remaining|
```

With the example `[0, 8)`, splitting at `cut = 3`:

```text
Before: [0,1,2,3,4,5,6,7]
Prefix: [0,1,2]
Remain: [3,4,5,6,7]
3 + 5 = 8
```

Bugs that commonly break parallel execution:

- **Forgetting to update `index` of the remainder:** prefix and original read the same positions -> duplicate elements.
- **Setting `cut` past `fence`:** out-of-bounds reads.
- **Incrementing `index` twice in `tryAdvance`:** skipped elements.
- **Returning a suffix instead of a prefix while declaring `ORDERED`:** can reverse result order when a collector preserves encounter order.
- **Not decreasing `estimateSize` after `trySplit`:** violates `SIZED`/`SUBSIZED` and can break optimizations.
- **Splitting in a way that always leaves tiny ranges:** creates more tasks than necessary.

Because `trySplit` may be called after part of the current range has already been consumed, the algorithm must use the **current `index`**, not an immutable initial `origin` saved at construction time, to calculate the new prefix boundary.


## 9. When the Source Is an `Iterator`: Fetching Batches on Demand

The `BatchSpliterator` above copies the entire `List` into memory. Real-world projects, however, may read data from:

- An `Iterator<T>` generating records sequentially.
- A database cursor.
- A stream of text lines.
- A paginated API where each request returns a group of records.

For sources **without random access** or **with unknown total size**, we need a different strategy. One option is: when `trySplit()` is requested, prefetch **at most B elements** from the iterator and return an independent spliterator for that batch.

### 9.1. `IteratorBatchSpliterator<T>` Pattern

The following is a Java 8+ class you can place in `IteratorBatchSpliterator.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;

public final class IteratorBatchSpliterator<T>
        implements Spliterator<T> {

    private final Iterator<? extends T> source;
    private final int batchSize;

    public IteratorBatchSpliterator(
            Iterator<? extends T> source,
            int batchSize) {
        this.source = Objects.requireNonNull(source, "source");

        if (batchSize <= 0) {
            throw new IllegalArgumentException(
                "batchSize must be > 0"
            );
        }

        this.batchSize = batchSize;
    }

    @Override
    public boolean tryAdvance(Consumer<? super T> action) {
        Objects.requireNonNull(action, "action");

        if (!source.hasNext()) {
            return false;
        }

        T value = source.next();
        action.accept(value);
        return true;
    }

    @Override
    public Spliterator<T> trySplit() {
        // Prefetch up to batchSize elements.
        List<T> batch = new ArrayList<>(batchSize);

        while (batch.size() < batchSize && source.hasNext()) {
            batch.add(source.next());
        }

        // No more data to split.
        if (batch.isEmpty()) {
            return null;
        }

        // This ArrayList's spliterator is independent of the original cursor.
        return batch.spliterator();
    }

    @Override
    public long estimateSize() {
        // A general Iterator does not know the exact element count.
        return Long.MAX_VALUE;
    }

    @Override
    public int characteristics() {
        // Use only if the Iterator source has a meaningful encounter order.
        return Spliterator.ORDERED;
    }
}
```

Test it first with a `List`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

public class IteratorBatchExample {
    public static void main(String[] args) {
        List<Integer> source =
            Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8);

        List<Integer> result = StreamSupport.stream(
                new IteratorBatchSpliterator<>(
                    source.iterator(), 3),
                true)
            .map(n -> n * n)
            .collect(Collectors.toList());

        System.out.println(result);
        // [1, 4, 9, 16, 25, 36, 49, 64]
    }
}
```

With an ordered iterator, the extracted batch is also a **prefix** of the unread portion. `trySplit` returns a spliterator over the sub-`ArrayList`, so that batch can be processed independently while the root spliterator keeps the source iterator.

**Important limitations of this version:**

1. A general `Iterator` does not expose total element count. Therefore, the root spliterator returns `Long.MAX_VALUE` from `estimateSize` as an **unknown size estimate**, and **must not declare `SIZED` or `SUBSIZED`**.
2. Each split batch can use O(B) memory. If the runtime creates many batches before processing completes, total memory can still grow with the number of queued batches.
3. `trySplit` **prefetches elements**. A short-circuiting terminal operation like `findAny` or `limit` may cause the source to read more elements than strictly needed for the output.
4. A shared `Iterator` is not thread-safe for concurrent `next()` calls. Never let multiple callers invoke `tryAdvance` / `trySplit` concurrently on **the same spliterator instance**. Controlled splitting by the Stream runtime is a different usage model from calling methods concurrently on one instance.
5. The class assumes the iterator has a **stable encounter order**. If the source is an iterator from `HashSet` without guaranteed encounter order, do not advertise `ORDERED` as a business contract.
6. This demonstration version **does not automatically close I/O resources**: if the iterator wraps a file or connection, the resource-owning layer must close it externally.

### 9.2. Comparing the Two Batch-Splitting Approaches

| Aspect | `BatchSpliterator` on `List` Snapshot | `IteratorBatchSpliterator` |
| --- | --- | --- |
| Source | `List` copied into an `ArrayList` | Sequential `Iterator` |
| On split | Creates a new index range without copying elements per split | Prefetches up to B elements into a list |
| Total element count | Known exactly | May be unknown |
| `SIZED` / `SUBSIZED` | Allowed for fixed index ranges | Must not be declared on general root spliterator |
| Memory cost | O(N) to snapshot initial list | O(B) per retained batch |
| Access complexity | `ArrayList.get(index)` | `hasNext()` / `next()` calls |
| Ability to short-circuit source reads | No new I/O needed; data is already in the list | May have already prefetched extra elements |
| Applicability | In-memory data, demonstrating disjoint index ranges | Sequential, unsized sources supplied in batches |

These are **two different strategies**, not resource-equivalent ways to write the same thing. If the source is already a stable `ArrayList`, the JDK's built-in spliterator is usually simpler and often faster than a custom solution.

## 10. Connecting to `StreamSupport.stream` and Laziness

Signature to know:

```java
static <T> Stream<T> stream(
    Spliterator<T> spliterator,
    boolean parallel
)
```

- `parallel = false`: requests sequential execution.
- `parallel = true`: requests parallel execution, but **does not guarantee** a fixed thread count or number of `trySplit` calls.
- The Stream draws from the spliterator; `filter` and `map` typically **execute only when a terminal operation consumes elements**.

Example with `BatchDemo.BatchSpliterator`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<Integer> source = Arrays.asList(1, 2, 3, 4);

Stream<Integer> pipeline = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .filter(n -> n > 2)
    .map(n -> n * 10);

// Pipeline has not been consumed yet.
System.out.println(pipeline.isParallel()); // true

long count = pipeline.count();
System.out.println(count); // 2
```

Do not embed business side effects inside `map` or `peek` and expect them to always run. For some pipelines where the source size is known, terminal operations like `count()` can exploit `SIZED` to optimize away steps that do not affect the count.

### Note on `SIZED` After `filter`

The root `BatchSpliterator` has `SIZED` because it knows the exact number of **remaining source elements**. After `filter`, however, the **output** element count is generally unknown in advance. The Stream runtime handles this characteristic change; **do not** assume `filter(...).count()` will simply return the source size immediately.

In the example above, `filter(n -> n > 2)` genuinely changes the count, so the right answer is 2, not 4.

### Two Different Lifecycles: In-Memory Sources vs. I/O Sources

A spliterator over an `ArrayList` copy holds no file or connection, so by itself it does not require `try-with-resources`. For files, databases, or cursors, **an explicit resource-ownership contract is mandatory**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

static long demDongCoChu(
        Path file,
        int batchSize) throws IOException {

    try (Stream<String> lines =
            Files.lines(file, StandardCharsets.UTF_8)) {

        Iterator<String> iterator = lines.iterator();

        return StreamSupport.stream(
                new IteratorBatchSpliterator<>(iterator, batchSize),
                false)
            .filter(s -> !s.trim().isEmpty())
            .count();
    }
}
```

Here `Files.lines` creates an I/O-backed source; **the `try` block owns and closes `lines`**. The iterator is used only while the source remains open. The example deliberately sets `parallel = false` so disk reading through an iterator is not promoted as a default parallelization strategy.

If an application needs parallel CPU processing on read batches, it must evaluate read throughput, buffering, task count, backpressure, and file-closing policy—never just flip `false` to `true` assuming it is safe and faster.

## 11. Encounter Order, `forEach`, and Terminal Operations

`ORDERED` does not mean multiple threads invoke callbacks **in exact encounter order**. It means **the source has a logical order** that certain terminal operations must respect.

Example:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

List<Integer> source =
    Arrays.asList(7, 3, 5, 1, 9);

List<Integer> output = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .map(n -> n * 10)
    .collect(Collectors.toList());

System.out.println(output); // [70, 30, 50, 10, 90]
```

`Collectors.toList()` preserves the encounter order of an ordered stream. However:

```java
StreamSupport.stream(
    BatchDemo.BatchSpliterator.snapshotOf(source, 2),
    true
).forEach(System.out::println);
```

`forEach` makes no ordering promise when printing; use `forEachOrdered` if the final action must execute in encounter order:

```java
StreamSupport.stream(
    BatchDemo.BatchSpliterator.snapshotOf(source, 2),
    true
).forEachOrdered(System.out::println);
```

When a list is needed as the result, **`collect` is usually better** than appending to a shared `ArrayList` inside `forEach`. `forEachOrdered` may reduce concurrency in order to honor ordering.

### `findFirst` Differs from `findAny`

```java
int first = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .filter(n -> n > 2)
    .findFirst()
    .orElse(-1); // 7

int any = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .filter(n -> n > 2)
    .findAny()
    .orElse(-1); // 7, 3, 5, or 9
```

`findFirst` must honor the first matching element in encounter order; `findAny` is allowed to return any matching element. Consequently, `ORDERED` can add coordination overhead for operations requiring the first element.

## 12. Even with a Correct Spliterator, `reduce` Must Still Be Right

An accurate `trySplit` design cannot fix an algebraically broken reduction. When batches run in parallel, `reduce` may combine partial results in various ways.

Valid example:

```java
long sum = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .mapToLong(Integer::longValue)
    .reduce(0L, Long::sum);
```

`0L` is the additive identity; `Long::sum` is associative under Java integer semantics (including Java's two's-complement overflow rules). If business rules cannot tolerate overflow, you still must choose an appropriate numeric domain or `BigInteger`.

Invalid example:

```java
int wrong = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .reduce(0, (a, b) -> a - b);
```

Subtraction is not associative:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Thus, you cannot expect consistent results across arbitrary splits. **A correct Spliterator** and **a valid accumulator/combiner** are two independent requirements.

### Collecting Lists Properly

Do not use:

```java
List<Integer> output = new ArrayList<>();

// AVOID: adding into a shared ArrayList from multiple threads.
StreamSupport.stream(
    BatchDemo.BatchSpliterator.snapshotOf(source, 2), true)
    .forEach(output::add);
```

Use:

```java
List<Integer> output = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2), true)
    .collect(Collectors.toList());
```

A Collector provides proper supplier, accumulator, and combiner mechanics. If you specifically want an `ArrayList`, choose `Collectors.toCollection(ArrayList::new)`.

### Batch Splitting Does Not Automatically Batch Results

`trySplit` hands out ranges for processing, yet the Stream remains `Stream<T>`, **not `Stream<List<T>>`**. If the problem requires output grouped into B-element lists (for API requests or database batch writes), you need a separate algorithm or collector to **group elements into lists**. Do not abuse `trySplit` as a business batching operation; split boundaries may vary at runtime.

## 13. Performance: How to Choose `batchSize`?

There is no single optimal batch size for all workloads. Relevant factors:

| When B Is Very Small | When B Is Very Large |
| --- | --- |
| May create more regions/tasks than needed | May create too few work units to utilize multiple cores |
| `trySplit` and scheduling overhead increases | Some workers may sit idle; uneven load |
| With Iterator sources, allocates many small lists | With Iterator sources, each batch retains many elements in memory |
| Can balance load more finely when per-element cost varies | Reduces overhead when per-element work is very cheap |

**Do not equate batch count with thread count.** The runtime may stop splitting before threshold B due to source size, scheduling strategy, and cost estimation. Conversely, the Iterator version may prefetch batches, increasing memory if reading outpaces processing.

### Recommended Experimental Framework

1. Verify correctness on small data with B = 1, 2, 7, and B larger than source size.
2. Build a sufficiently large source and define **pure CPU-bound** work per element.
3. Test a range of batch sizes, e.g. B = 64, 256, 1024, 4096, instead of guessing one number.
4. Compare `source.stream()`, `source.parallelStream()` using the built-in spliterator, and the custom version.
5. Measure throughput/latency, CPU utilization, memory allocation, and GC frequency on realistic hardware.
6. Use a benchmark with warm-up and multiple iterations, such as JMH; never draw conclusions from one `System.nanoTime()` call.

If per-element computation is very light, the **O(N) snapshot cost** in `BatchSpliterator.snapshotOf` can outweigh any batch-splitting benefit. When the source is already an `ArrayList`, `ArrayList.spliterator()` is always an essential baseline.

**Changing B does not make an invalid computation valid.** `reduce` must still satisfy identity and associativity, and lambdas must remain stateless/non-interfering regardless of batch size.

## 14. Design Mistakes Easy to Overlook

| Symptom | Cause | Fix |
| --- | --- | --- |
| Some elements processed twice | `trySplit` creates prefix without updating `index` of remainder | Cut disjoint intervals; always advance cursor. |
| Last element lost | Confusing half-open `[index, fence)` with closed interval | Use `index < fence` and test 0, 1, B, B+1 elements. |
| Parallel list output out of order | Splitting off suffix first while declaring `ORDERED` | Return prefix of untraversed region. |
| `count()` returns wrong value | Misdeclaring `SIZED` or failing to update `estimateSize` | Declare only when exact size is known; verify after split/advance. |
| `SUBSIZED` misreported on dynamic source | Split sizes are unstable | Drop the flag or use a fixed snapshot/range. |
| `NONNULL` declared yet input has `null` | Incorrect characteristic | Never declare `NONNULL` unless verified. |
| `batchSize = 0` causes non-progressing loop | Unvalidated parameter | Throw `IllegalArgumentException`. |
| Iterator source read concurrently | Same instance called directly by multiple threads | Manage ownership; split first, then process independent splits. |
| Calling `List.get(i)` on a huge `LinkedList` | Indexed access can be O(n) | Copy to `ArrayList` or use an appropriate Iterator source. |
| Source too large exhausts RAM | Copying entire source or queuing too many batches | Bounded batching and resource/backpressure control. |
| `findFirst` on Iterator data reads too much | `trySplit` prefetches a batch | Weigh batch size and short-circuit strategy. |
| `forEach` outputs in wrong order | Execution order is not encounter order | Use `collect`, or `forEachOrdered` when appropriate. |
| `reduce` with subtraction gives varying results | Non-associative operation | Fix reduction logic; changing batch size will not fix it. |
| I/O source not closed | Spliterator does not manage lifecycle itself | Use `try-with-resources` in the stream/connection-owning layer. |
| Parallel runs slower | Split/merge overhead or overly cheap work | Benchmark, revisit B and source; consider JDK spliterator. |

## 15. Tiered Practice Exercises

### Exercise 1 — Trace the Batches

Given source `[1, 2, ..., 10]`, `batchSize = 4`, and the algorithm:

```java
if (remaining <= batchSize) return null;
int prefixSize = Math.min(batchSize, remaining / 2);
```

Trace consecutive splits on the **remainder** and record the size of every final chunk. Do any chunks overlap in position?

### Exercise 2 — Fix the Missing Cursor Update

Faulty snippet:

```java
public Spliterator<T> trySplit() {
    int remaining = fence - index;
    if (remaining <= batchSize) return null;

    int cut = index + Math.min(batchSize, remaining / 2);
    return new BatchSpliterator<>(
        data, index, cut, batchSize
    );
}
```

Why can this code duplicate elements? Which line is missing?

### Exercise 3 — When to Use `SIZED`?

A Spliterator reads records from an `Iterator<T>` with unknown total count. `estimateSize()` returns `Long.MAX_VALUE`. May it declare `SIZED | SUBSIZED` like the `ArrayList` snapshot version? Explain.

### Exercise 4 — Ensuring Parallel Correctness

Propose at least five test cases that catch batch-cutting bugs: empty source, single element, exact B elements, B+1 elements, and duplicate values. Explain why `List.equals` is used instead of `Set.equals` to detect positional duplication.

### Exercise 5 — Pipeline Transformation

Use `BatchDemo.BatchSpliterator.snapshotOf(data, 8)` with an ordered list of integers. Write a parallel pipeline to filter positive numbers, multiply by 10, and collect into `List<Integer>` preserving encounter order. Explain why not to use `parallel().forEach(result::add)`.

### Exercise 6 — Reading Batches from an I/O Source

The source is `Files.lines(path)`. Who is responsible for closing the resource? If `IteratorBatchSpliterator` prefetches B lines on each split, is `limit(10)` guaranteed to read only 10 lines from the file? Why or why not?

### Exercise 7 — Performance Measurement

Explain why the snapshot version over an `ArrayList` can be slower than the JDK's built-in spliterator even when both return correct results. Design an experiment with at least three values of B and two levels of per-element computational cost.

## 16. Hints and Reference Solutions

**Exercise 1.** Initially 10 elements remain; `prefixSize = min(4,5) = 4`, splitting `[1,2,3,4]`. Six elements remain `[5,6,7,8,9,10]`; another split of `min(4,3) = 3` gives `[5,6,7]`. The final slice `[8,9,10]` has three elements and does not split further because `remaining = 3 <= 4`. Batch sizes are `[4,3,3]`; there is no positional overlap.

**Exercise 2.** Missing code:

```java
BatchSpliterator<T> prefix =
    new BatchSpliterator<>(data, index, cut, batchSize);

index = cut; // Crucial: remove the prefix from the remaining range.
return prefix;
```

Without advancing `index` on the current instance, the original retains the split-off range and can emit elements already processed by the prefix.

**Exercise 3.** No. For an unsized iterator, `Long.MAX_VALUE` is only an unknown estimate, not an exact size. The root spliterator must not declare `SIZED` / `SUBSIZED`. A sub-`ArrayList` built from a specific batch of B elements can have its own size characteristics because that sublist itself knows its element count.

**Exercise 4.** Cases should include `[]`, `[7]`, `[1..B]`, `[1..B+1]`, and a list such as `[1,1,2,2,3]`. After exhausting all splits, consume prefixes in order before the remainder; compare the resulting list with the source list. `Set.equals` compares only unique values and fails to verify multiplicities and positions.

**Exercise 5.**

```java
List<Integer> output = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(data, 8),
        true)
    .filter(n -> n > 0)
    .map(n -> n * 10)
    .collect(Collectors.toList());
```

`Collectors.toList()` collects in the ordered source's encounter order. `forEach` in a parallel stream does not preserve execution order, and concurrently adding to an external `ArrayList` is thread-unsafe.

**Exercise 6.** The layer creating `Files.lines` must close the stream, typically via `try-with-resources`. `IteratorBatchSpliterator.trySplit` can prefetch a batch of B lines, and the runtime may even split multiple batches before `limit(10)` terminates. Therefore, it cannot be guaranteed that only 10 lines are read from the file, even though at most 10 lines are output.

**Exercise 7.** Snapshotting copies the entire `List`, costing O(N) memory/time; `trySplit` allocates additional objects and overly small batches incur overhead. You can test B = 64, 512, 4096 with two workloads: (a) a trivial multiply-add and (b) a relatively heavy independent CPU-bound algorithm. Compare against `source.stream()` and `source.parallelStream()` on identical data and outputs; use a benchmark with warm-up, multiple iterations, and allocation/GC monitoring.

## 17. Production Deployment Checklist

Before shipping a custom spliterator into production, verify:

- [ ] Is the source genuinely **ordered**? If not, do not declare `ORDERED`.
- [ ] Does `trySplit` return a partition **disjoint** from the current one without dropping elements?
- [ ] If `ORDERED` is set, is the split-off part a prefix of the remainder?
- [ ] Does `tryAdvance` emit exactly one element and `forEachRemaining` emit all unconsumed elements?
- [ ] Does `estimateSize` decrease properly after consumption and splitting, with `SIZED` / `SUBSIZED` declared only when accurate?
- [ ] Are `NONNULL` / `DISTINCT` / `SORTED` / `CONCURRENT` omitted unless their contracts are fulfilled?
- [ ] Is `batchSize > 0` validated and do final chunk sizes match batch policy?
- [ ] Is the source free from structural modification during traversal; if snapshotting, are **shallow-copy** limits understood?
- [ ] Is the same spliterator never accessed concurrently by multiple threads, with each split owning its traversal state?
- [ ] Are pipeline lambdas **stateless** and **non-interfering**?
- [ ] Do `reduce` and collectors use valid identity, accumulator, and combiner functions?
- [ ] Have empty source, single element, B, B+1, duplicates, and sequential/parallel equivalence been tested?
- [ ] If I/O-backed, is **resource closing** ownership clear and short-circuit behavior understood?
- [ ] Have speed and memory been measured against Java's built-in spliterator rather than guessing optimizations?

## 18. Summary

The design mindset for a batch-splitting Spliterator can be summarized as:

```text
Ordered data source
          |
    BatchSpliterator
          |
        trySplit
      /     |     \
  batch A batch B batch C   (disjoint index ranges)
      \     |     /
  map / filter / process
          |
  reduce / collect
          |
        Result
```

The crux is not "splitting into many batches", but honoring **source contracts and result-combining rules**:

- `trySplit` must split properly, return prefixes for ordered sources, and keep partitions non-overlapping.
- `estimateSize` along with `SIZED` / `SUBSIZED` must be accurate whenever declared.
- `StreamSupport.stream(spliterator, true)` enables parallel execution by the runtime without promising task count or speedup.
- `reduce` and `collect` must use valid combining operations; a right Spliterator cannot rescue lambdas with shared mutable state.
- Iterator/I/O sources demand accounting for **prefetching**, unknown sizes, and resource ownership.
- Measure performance only after verifying **element coverage, order, boundary cases, and correctness**.

By completing this project, you can approach large data sources with the Java Stream API more systematically: knowing when to rely on built-in spliterators, when to write a custom batch splitter, and how to evaluate safety, resources, and performance before running in parallel.
