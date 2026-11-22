# Spliterator and Data Source Splitting in Parallel Streams

`Spliterator<T>` (in `java.util`) is an interface that supports **traversing** and **splitting** a source of elements. `Iterator` primarily traverses sequentially; `Spliterator` adds `trySplit()` to hand off untraversed portions to other tasks. This is a key mechanism that enables the Java Stream API to execute pipelines in parallel.

**Key takeaway:** Calling `parallelStream()` or `stream().parallel()` only requests parallel processing; the source must be splittable into independent parts at a reasonable cost for parallelism to have a chance of paying off. A Spliterator describes the data source and how work is split; it does not create or manage threads itself.

This article is part of **Parallel Streams** in Java concurrency, using only general Java APIs without introducing framework-specific mechanisms.

## 1. Where Does Spliterator Fit in a Parallel Stream?

```text
Source: array / ArrayList / Set / range / custom source
                         |
                    Spliterator
                         |
                    trySplit()
                   /          \
               part A          part B
                /                 \
           trySplit()          trySplit()
            /    \              /    \
          A1     A2            B1     B2
            \    /              \    /
             processing results / reduction
                         |
                    final result
```

Only when a terminal operation is invoked does the stream implementation actually traverse the source. In a parallel pipeline, the JDK can decompose the work into Fork/Join tasks and process the split portions on appropriate workers. Using `ForkJoinPool.commonPool()` is the typical behavior of the JDK implementation, not a guarantee that every chunk gets its own dedicated thread. The split tree in the diagram is illustrative only; the number of splits, chunk sizes, and execution timing depend on the source, pipeline, and system.

A stream can still run correctly even if its Spliterator cannot split, though in that case the benefit of processing multiple elements in parallel may be minimal or nonexistent.

## 2. Core Methods

| Method | Purpose and Contract |
|---|---|
| `boolean tryAdvance(Consumer<? super T> action)` | If a remaining element exists, passes one element to `action` and returns `true`; otherwise returns `false` |
| `void forEachRemaining(Consumer<? super T> action)` | Consumes all remaining elements; can be better optimized than iterating element by element |
| `Spliterator<T> trySplit()` | Returns a new Spliterator owning a portion of the **untraversed** elements, keeping the rest in the original object; may return `null` |
| `long estimateSize()` | Estimates the number of remaining elements; may return `Long.MAX_VALUE` if the size is unknown |
| `int characteristics()` | Bitmask describing the characteristics of the source and traversal order |
| `long getExactSizeIfKnown()` | Exact size when the `SIZED` characteristic is present; otherwise returns `-1` |
| `boolean hasCharacteristics(int flags)` | Checks whether the given characteristics are present in the bitmask |
| `Comparator<? super T> getComparator()` | For a `SORTED` source, returns the comparator (`null` if in natural order); if not sorted, typically throws `IllegalStateException` |

The operations `tryAdvance()`, `forEachRemaining()`, and `trySplit()` all mutate the set of elements **still managed by the Spliterator**. Do not reuse the same Spliterator for multiple independent runs and expect identical results. When you need to traverse from the beginning again, obtain a new Spliterator from the source.

Java also provides `Spliterator.OfInt`, `OfLong`, and `OfDouble` with primitive consumers to avoid unnecessary boxing in numeric computations.

## 3. How Does trySplit() Partition Elements?

Suppose a source has an encounter order:

```text
before split: [1, 2, 3, 4, 5, 6, 7, 8]
                       |
                    trySplit()
                /                \
returned prefix: [1, 2, 3, 4]   original keeps: [5, 6, 7, 8]
```

For a Spliterator with `ORDERED`, the object returned by `trySplit()` must contain a **prefix** of the untraversed elements; the original object retains the remaining suffix. The resulting subsets must be non-overlapping, omit nothing, and together equal the original untraversed elements.

**There is no API rule requiring an exact midpoint split.** A source may split off a block, a node, a growing batch size, or return `null` if it cannot or should not split. For a source without `ORDERED`, there is no prefix along an encounter order to preserve.

### Runnable Example: Splitting an ArrayList

Save as `ListSplitDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class ListSplitDemo {
    public static void main(String[] args) {
        List<Integer> values =
                new ArrayList<>(List.of(1, 2, 3, 4, 5, 6, 7, 8));

        Spliterator<Integer> remainder = values.spliterator();
        Spliterator<Integer> prefix = remainder.trySplit();

        if (prefix == null) {
            throw new IllegalStateException("Unexpected unsplittable list");
        }

        System.out.println("Prefix size: " + prefix.getExactSizeIfKnown());
        System.out.println("Remainder size: "
                + remainder.getExactSizeIfKnown());

        List<Integer> left = new ArrayList<>();
        List<Integer> right = new ArrayList<>();
        prefix.forEachRemaining(left::add);
        remainder.forEachRemaining(right::add);

        System.out.println("Prefix: " + left);
        System.out.println("Remainder: " + right);
        System.out.println("Total: " + (left.size() + right.size()));
    }
}
```

Compile and run on JDK 17+:

```bash
javac ListSplitDemo.java
java ListSplitDemo
```

Output:

```text
Prefix size: 4
Remainder size: 4
Prefix: [1, 2, 3, 4]
Remainder: [5, 6, 7, 8]
Total: 8
```

`ArrayList`'s Spliterator can split by index, so it splits nearly evenly while preserving encounter order. `getExactSizeIfKnown()` gives the exact size of both halves thanks to the `SIZED` characteristic. In this example, traversal after splitting is performed **sequentially** for illustration; `trySplit()` does not mean creating threads or executing code on another thread.

## 4. estimateSize(), SIZED, and SUBSIZED

To partition work effectively, algorithms need to estimate how many elements remain. The size flags must be understood precisely:

- `SIZED`: the size reported by `estimateSize()` is exact according to the source's contract (assuming no unauthorized interference). `getExactSizeIfKnown()` can return this number.
- `SUBSIZED`: the current Spliterator **and all Spliterators resulting from splitting** satisfy both `SIZED` and `SUBSIZED`.
- Without `SIZED`: `estimateSize()` is only an estimate; `getExactSizeIfKnown()` returns `-1`.
- With `SIZED` but without `SUBSIZED`: you cannot automatically assume every split branch has an exact size.

A 16-element source can be split into a balanced tree:

```text
16
├── 8
│   ├── 4
│   └── 4
└── 8
    ├── 4
    └── 4
```

However, splitting into **balanced element counts** does not guarantee balanced **processing time**: one chunk may contain an operation taking 100 ms while another takes only 1 ms. That creates a slow branch acting as a bottleneck (*straggler*), even with equal element counts.

Nor is there a universal "optimal chunk threshold" for all sources. If each element is very cheap to process, decomposition, scheduling, and combining overhead can outweigh computation time. If operations are heavy and branches are balanced, parallelism can deliver substantial gains.

## 5. The Eight Characteristics and Their Impact on Streams

`characteristics()` combines flags using bitwise OR (`|`). They are **behavioral guarantees** so that Stream operations can safely choose optimizations:

| Flag | Meaning | Common Misconception |
|---|---|---|
| `ORDERED` | The source has an encounter order; splits must preserve the prefix | Does not mean parallel tasks execute in increasing time order |
| `DISTINCT` | Elements are distinct according to `equals()` | Useful for optimizing `distinct()`; do not declare if duplicates exist |
| `SORTED` | Traversal follows a defined sort order | Must properly fulfill the `getComparator()` contract |
| `SIZED` | Exact size | Must not declare if the size is only an estimate |
| `NONNULL` | Contains no `null` elements | Not appropriate for sources that may contain null |
| `IMMUTABLE` | The source cannot be structurally modified during traversal | Does not guarantee all element objects themselves are immutable |
| `CONCURRENT` | The source supports concurrent structural modification per its contract | Does **not** mean multiple threads may call methods on the same Spliterator instance |
| `SUBSIZED` | The size of every split branch remains exact | Stronger than `SIZED` at the root alone |

Typical examples:

- `ArrayList` has an encounter order and known size, with a Spliterator suited to index-range splitting; it typically carries `ORDERED`, `SIZED`, and `SUBSIZED`.
- `HashSet` guarantees uniqueness but not a `List`-like encounter order. Splitting depends on the set's internal structure and may be uneven.
- Concurrent collections such as `ConcurrentHashMap.keySet()` have different traversal and structural interference policies than `ArrayList`; `CONCURRENT` describes the source, not unlimited license to share a single Spliterator object.

When writing a custom Spliterator, declaring inaccurate flags can cause Stream to optimize based on false assumptions, leading to missing elements, wrong ordering, or incorrect results. If you cannot guarantee a characteristic, do not advertise that flag.

## 6. Implementing a Custom Spliterator.OfInt for Integer Ranges

Contiguous ranges are well suited for parallel processing: no large list needs to be stored, each branch holds two bounds, the size is exact, and it can split quickly at the midpoint.

Invariant while untraversed:

```text
Original manages: [index, fence)
trySplit():
    returns [index, mid)   // prefix
    original keeps [mid, fence) // suffix
```

Save the following program as `RangeSplitDemo.java`:

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class RangeSplitDemo {
    static final class IntRange implements Spliterator.OfInt {
        private int index;
        private final int fence;

        IntRange(int fromInclusive, int toExclusive) {
            if (fromInclusive > toExclusive) {
                throw new IllegalArgumentException("Invalid range");
            }
            index = fromInclusive;
            fence = toExclusive;
        }

        @Override
        public OfInt trySplit() {
            int size = fence - index;
            if (size <= 1) {
                return null;
            }

            int middle = index + size / 2;
            IntRange prefix = new IntRange(index, middle);
            index = middle;
            return prefix;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (index >= fence) {
                return false;
            }
            action.accept(index++);
            return true;
        }

        @Override
        public long estimateSize() {
            return (long) fence - index;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED | IMMUTABLE;
        }
    }

    public static void main(String[] args) {
        Spliterator.OfInt remaining = new IntRange(1, 9);
        Spliterator.OfInt first = remaining.trySplit();

        System.out.println("First: "
                + StreamSupport.intStream(first, false).boxed().toList());
        System.out.println("Remaining: "
                + StreamSupport.intStream(remaining, false).boxed().toList());

        long sumSquares = StreamSupport
                .intStream(new IntRange(1, 1001), true)
                .mapToLong(x -> (long) x * x)
                .sum();

        System.out.println("Sum of squares: " + sumSquares);
    }
}
```

Run on Java 17+:

```bash
javac RangeSplitDemo.java
java RangeSplitDemo
```

Deterministic output:

```text
First: [1, 2, 3, 4]
Remaining: [5, 6, 7, 8]
Sum of squares: 333833500
```

**Design explanation:**

1. Each Spliterator manages a distinct, non-overlapping half-open interval. `trySplit()` creates a new instance holding the first half and updates the original's `index`; no elements are lost.
2. `tryAdvance()` consumes exactly one value if available; when exhausted, it returns `false`. `Objects.requireNonNull` rejects a null consumer.
3. `estimateSize()` is always computed from the bounds, so `SIZED` and `SUBSIZED` are accurate for valid ranges. `ORDERED` applies because splits return prefixes; `IMMUTABLE` fits a structurally immutable synthetic integer source.
4. `StreamSupport.intStream(..., true)` creates a parallel `IntStream` from the Spliterator. The sum of squares uses `long` to avoid `int` overflow and provides a reduction suitable for parallel computation.
5. Task scheduling order may vary between runs, but the total sum never changes because branches neither overlap nor omit elements.

**Example limitations:** the `size` variable in `trySplit()` is an `int`, so it can overflow if the bounds are more than `Integer.MAX_VALUE` apart. This example only uses small ranges; a general-purpose library should compute the difference as `long` and calculate the midpoint safely. This Spliterator object is not thread-safe for concurrent method calls from multiple threads; the proper pattern is to **split and hand each branch object to a single task**.

For arrays, `ArrayList`, or `IntStream.range`/`rangeClosed`, the JDK already provides suitable Spliterators. Writing a custom one is only worth considering when you own a specialized source structure, such as blocks or partitioned trees, and measurements confirm the need for custom splitting logic.

## 7. Sources from an Iterator: Splittable, but Not Always Ideal

When you only have a sequentially advancing `Iterator`, you can wrap it as a Spliterator:

```java
Spliterator<String> spliterator =
        java.util.Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED);

java.util.stream.Stream<String> stream =
        java.util.stream.StreamSupport.stream(spliterator, true);
```

This snippet is illustrative code **placed inside a method that already has** a variable `iterator` of type `Iterator<String>` and imports `java.util.Spliterator`. The `spliteratorUnknownSize` adapter does not know the exact size upfront, but the JDK implementation **can gather batches** to split. Therefore, you should not conclude that a Spliterator from an Iterator "can never split"; the limitation is that pulling data sequentially to form batches can become a bottleneck.

In addition to `StreamSupport.stream(spliterator, parallel)`, Java provides an overload accepting `Supplier<? extends Spliterator<T>>`, `characteristics`, and the `parallel` flag to defer acquiring the source until the terminal operation runs. This helps avoid binding to a mutable source too early, provided the **characteristics passed to StreamSupport match the Spliterator returned by the supplier**.

## 8. Implications for Ordering, Performance, and Concurrency

### Encounter Order vs. Execution Order

An `ORDERED` source can still process elements across multiple workers in a non-deterministic execution order. For example:

```java
java.util.List.of(1, 2, 3, 4)
        .parallelStream()
        .forEach(System.out::print);
```

This may print in an order other than `1234`. Replacing `forEach` with `forEachOrdered` preserves encounter order when printing (`1234` for this list source), but may increase synchronization overhead and reduce parallelism at the terminal step. Avoid relying on the order of side effects in `forEach`.

### Why Can a Good Split Still Be Slow?

Being splittable is an important prerequisite, but performance also depends on:

- **Granularity:** tasks that are too small incur scheduling, splitting, and combining overhead. Cheap addition over a short list is rarely worth running in parallel.
- **Cost distribution:** two branches with the same element count where one is many times harder to process will produce a straggler.
- **Operation type:** pipelines with only stateless, independent transformations parallelize more easily than `sorted`, `distinct`, or order-dependent operations.
- **Source size and structure:** index-based splitting of arrays/ranges is cheap, whereas linked structures, sequential Iterators, or unknown-size sources may pay a high cost just to find split points.
- **Reduction/combining cost:** reductions using shared mutable state or a shared lock can negate parallel speedup.
- **Physical resources:** core count, caches, allocation, GC, a busy common pool, blocking I/O operations, or external system limits all have an impact.

Think of total processing time as splitting cost + the slowest branch's work + combining cost + scheduling/synchronization. This is a qualitative mental model, not an exact timing formula.

### Avoid Arbitrary Shared Side Effects

A common mistake:

```java
List<Integer> output = new ArrayList<>();
input.parallelStream().forEach(output::add);
```

This is an **anti-pattern snippet inside a method**, where `input` is a `Collection<Integer>`. `ArrayList` is not thread-safe, so concurrent `add` calls can corrupt data. Use an appropriate collector or a stateless reduction instead:

```java
List<Integer> output = input.parallelStream().toList();
```

This produces the result after the terminal operation, letting the Stream machinery handle collection; if you need a mutable list, choose a collector with the right semantics. Never treat a Spliterator's `SIZED` or `CONCURRENT` flag as an excuse to ignore accumulator thread-safety.

### Interfering with the Source While a Stream Is Running

`ArrayList` and many mutable collections have late-binding Spliterators with **best-effort** fail-fast checks. Structurally modifying the source after traversal has bound to it can trigger `ConcurrentModificationException` or unpredictable behavior; fail-fast is not a thread-synchronization mechanism.

Sources like `ConcurrentHashMap` document traversal policies suited for concurrent modification; being readable here does not mean having a fixed point-in-time snapshot of all keys. For sources that do not support concurrent modification, keep the data stable during traversal or create an appropriate snapshot before building the stream.

**Important:** Spliterators are generally not guaranteed to be thread-safe; parallel algorithms should hand each Spliterator instance to one thread at a time after splitting. `CONCURRENT` describes the **data source**, not the ability for two workers to call `tryAdvance()` concurrently on the exact same Spliterator object.

## 9. How to Inspect a Specific Source's Splittability

Before optimizing, inspect the following facts on **a fresh Spliterator**:

1. `characteristics()` and `hasCharacteristics(...)`: does it have `ORDERED`, `SIZED`, `SUBSIZED`?
2. `estimateSize()`, `getExactSizeIfKnown()`: does the source know its exact size or only an estimate?
3. `trySplit()`: does it return a child branch; what are the sizes and structures of the child and original?
4. Can it split repeatedly and effectively, or only produce a single heavily skewed split?
5. Does the pipeline actually have enough independent CPU-bound work to offset splitting and combining overhead?

Metadata-only inspection example (illustrative snippet inside a method where `numbers` is a `Collection<Integer>`):

```java
Spliterator<Integer> s = numbers.spliterator();

System.out.println("Estimate: " + s.estimateSize());
System.out.println("SIZED: " + s.hasCharacteristics(Spliterator.SIZED));
System.out.println("SUBSIZED: "
        + s.hasCharacteristics(Spliterator.SUBSIZED));
System.out.println("ORDERED: "
        + s.hasCharacteristics(Spliterator.ORDERED));
```

If you want to actually test splitting, use a separate Spliterator for the test. `trySplit()` changes element ownership; do not split an instance you intend to pass into a real pipeline and assume it still represents the full source.

To evaluate speed, compare sequential vs. parallel on **the same data types, the same workload, multiple sizes, and after warm-up**. Prefer JMH when reliable benchmarks are needed; a single `System.nanoTime()` measurement is easily skewed by JIT, GC, and system load.

## 10. Common Mistakes

1. **Assuming `parallel()` is always faster.** Hard-to-split sources or overly cheap per-element work can make parallel execution slower.
2. **Assuming `trySplit()` always splits 50/50.** The API allows returning `null`, splitting in batches, or using other strategies.
3. **Assuming `trySplit()` creates OS threads.** It only partitions the source; the runtime schedules tasks.
4. **Letting two threads concurrently use the same Spliterator instance.** You must split into child instances and transfer ownership.
5. **Setting `SIZED` or `SUBSIZED` inaccurately.** Optimizations relying on metadata can produce wrong results.
6. **Equating `ORDERED` with `forEach` execution order.** Encounter order does not force the scheduler to execute sequentially.
7. **Misusing `CONCURRENT` to justify an unsafe shared accumulator.** That flag only describes the source structure.
8. **Structurally modifying a mutable source during traversal.** This can cause interference and undefined results.
9. **Measuring size by traversing all elements and then reusing the same Spliterator.** Traversal consumes the data; use metadata when appropriate.
10. **Treating an I/O bottleneck as a reason to enable parallel streams.** Blocking Fork/Join tasks can starve other work and will not increase external connection throughput.

## 11. Choosing the Right Spliterator

A well-splittable Spliterator typically has four qualities: **complete non-overlapping partitioning**, **low split cost**, **accurate size and characteristics**, and **reasonably balanced work distribution**. Even when all four are met, measure the real workload before committing to a parallel stream.

Start with the standard Spliterators for `ArrayList`, arrays, or `IntStream.range`; implement a custom one only when a new source structure or block-based data layout requires dedicated splitting logic. The essence of `trySplit()` is handing off an untraversed portion of the source to another task; parallel efficiency emerges when independent chunks are large enough to process and combine at low overhead.

Official API references:

- [Oracle Java SE 21 — Spliterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Spliterator.html)
- [Oracle Java SE 21 — StreamSupport](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/StreamSupport.html)
- [Oracle Java SE 21 — java.util.stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html)
