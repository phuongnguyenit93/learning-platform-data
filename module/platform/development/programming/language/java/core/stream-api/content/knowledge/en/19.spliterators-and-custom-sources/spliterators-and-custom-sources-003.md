# Splitting Sources with trySplit and Estimating with estimateSize

When you call `parallel()` on a **Java Stream API** pipeline, the program does not automatically become faster. For effective parallel processing, the data source must be **partitioned into work units** that are sufficiently independent, without losing elements or processing duplicates. In Java, the **`Spliterator`** interface is a key mechanism supporting source traversal and partitioning.

Two core methods are **`trySplit()`** and **`estimateSize()`**:

- `trySplit()` attempts to split off a portion of untraversed data into a **new Spliterator**, allowing that portion to be processed independently.
- `estimateSize()` reports **an estimate of the remaining elements** in the current Spliterator; if exact and paired with the right characteristics, this number can also help the Stream optimize execution.

This article belongs to the **Spliterators and Custom Sources** chapter of the **JAVA_STREAM_API** module. We will learn the source partitioning contract, its relationship with `tryAdvance()`, the meaning of `SIZED`/`SUBSIZED`/`ORDERED`, how to write a `Spliterator.OfInt` for an integer range, converting a source to a Stream with `StreamSupport`, and caveats around state, memory, ordering, integer overflow, and parallel performance. This forms the foundation for building custom sources, understanding lazy pipelines, and integrating with `filter`, `map`, `reduce`, `collect`, or advanced mechanisms like Stream Gatherers.

## 1. What Problem Does Spliterator Solve?

Suppose a list contains eight numbers:

~~~text
[0, 1, 2, 3, 4, 5, 6, 7]
~~~

When processing sequentially, we can traverse from left to right. But to divide work between two processing workers, we need a way to turn **one untraversed region** into two **disjoint** regions:

~~~text
Initial source:
[0, 1, 2, 3, 4, 5, 6, 7]

trySplit() may produce:
  Returned Spliterator: [0, 1, 2, 3]
  Original Spliterator: [4, 5, 6, 7]

Either part can be split further:
  [0, 1] and [2, 3]
~~~

A Spliterator supports **traversal** and, when feasible, **partitioning**. That is why the name `Spliterator` suggests *split* + *iterator*.

A regular `Iterator` has `hasNext()` and `next()`. A `Spliterator` uses `tryAdvance(...)`, `forEachRemaining(...)`, and `trySplit()` along with size and source characteristic metadata. Thus, it can supply valuable signals to a Stream pipeline.

### Distinguishing three concepts

| Component | Role |
|---|---|
| `Stream` | Declaratively describes a processing pipeline with lazy steps and a terminal operation |
| `Spliterator` | Mechanism for traversing, partitioning, and describing characteristics of the **source** |
| `ForkJoinPool`/execution engine | Coordinates parallel work across chunks provided by the source and pipeline |

Having `trySplit()` return a chunk of data **does not mean** it spawns a thread itself. `Spliterator` does not decide thread counts; scheduling belongs to the Stream execution layer.

## 2. Primary Methods of Spliterator

The `java.util.Spliterator<T>` interface has these fundamental operations:

~~~java
boolean tryAdvance(Consumer<? super T> action);

void forEachRemaining(Consumer<? super T> action);

Spliterator<T> trySplit();

long estimateSize();

int characteristics();
~~~

There are also:

~~~java
long getExactSizeIfKnown();

boolean hasCharacteristics(int characteristics);

Comparator<? super T> getComparator();
~~~

`getComparator()` is only valid when the source declares `SORTED`; otherwise, the default method typically throws `IllegalStateException`. For natural ordering, a `SORTED` Spliterator may return `null` from `getComparator()` to indicate natural ordering.

Interpretation table:

| Method | Question It Answers |
|---|---|
| `tryAdvance(action)` | Is there a next element? If so, pass **one element** to action and return `true` |
| `forEachRemaining(action)` | Traverse all remaining elements |
| `trySplit()` | Can the untraversed region be split to yield an independent Spliterator? |
| `estimateSize()` | Approximately how many elements remain? |
| `characteristics()` | Does the source have properties such as `ORDERED`, `SIZED`, `SUBSIZED`? |
| `getExactSizeIfKnown()` | Return remaining size **if known exactly**, otherwise `-1` |

**Note:** `tryAdvance` does not merely "check existence" like `hasNext`; it also **consumes** an element if available. `forEachRemaining` also consumes data. This changes the *untraversed* data range inside the Spliterator.

## 3. The Contract of trySplit(): Lossless and Duplicate-Free Partitioning

Signature:

~~~java
Spliterator<T> trySplit();
~~~

`trySplit()` returns:

- **A new Spliterator** containing **some untraversed elements** split off from the current Spliterator, if splitting succeeded.
- **`null`** if it cannot or chooses not to split further.

After a successful split, elements belonging to the returned Spliterator **are no longer in the untraversed range of the original Spliterator**. If both parts are traversed exactly once, we must obtain **the exact set of untraversed elements from before the split**, with no elements lost or re-emitted.

### 3.1. When the source is ORDERED

When a Spliterator reports `ORDERED`, the Spliterator returned by `trySplit()` must cover **a prefix** of the remaining elements, while the original Spliterator retains the **suffix**.

Valid example:

~~~text
Before split:
    [A, B, C, D, E, F]

After split:
    trySplit() result:    [A, B, C]
    Original Spliterator: [D, E, F]
~~~

Splitting into `[A, C, E]` and `[B, D, F]` does **not** satisfy the prefix/suffix constraint of an `ORDERED` Spliterator.

For a source **without `ORDERED`**, the returned part does not have to be a prefix; however, it must still maintain a valid partition without dropping or duplicating elements.

### 3.2. Is splitting strictly in half required?

**No.** `trySplit()` may split off any chunk size suited to the source; it may return `null` even when many elements remain if it cannot split effectively. Splitting roughly in half is usually sensible for **arrays or index ranges** because:

- Both tasks tend to be similar in size.
- Branches can continue to be subdivided.
- Computing boundaries is relatively simple.

However, for a one-way `Iterator`, I/O stream, or stateful generator, not every source supports random-access splitting. In those cases, batch splitting (*batching*) or not supporting splitting may be more appropriate.

### 3.3. Splitting after partial traversal

If `tryAdvance` has already consumed an element earlier, `trySplit` may only split **the remaining portion**:

~~~text
Initially: [0, 1, 2, 3, 4, 5]
tryAdvance took 0.

Remaining: [1, 2, 3, 4, 5]
Valid split:
    returned part: [1, 2]
    original part: [3, 4, 5]
~~~

The already-processed element `0` **must not reappear** in either Spliterator.

## 4. estimateSize(): Remaining Size, Not Initial Size

Signature:

~~~java
long estimateSize();
~~~

The return type is `long` to represent counts larger than `int` bounds. However, **an estimate is not always exact**: its meaning depends on source characteristics.

- For a source with an exact known size, such as an index range of a stable array, `estimateSize()` can equal the exact remaining element count.
- For a source whose size is hard to determine, the value may only be an approximation.
- When no reliable finite estimate exists, or for infinite sources, the API may return `Long.MAX_VALUE` to represent "unknown/unbounded" — it does **not** mean the source actually contains that exact number of elements.

For example, if a Spliterator manages `[10, 20)`, containing ten integers, the exact size is:

~~~text
20 - 10 = 10
~~~

After consuming 10, the remaining range is `[11, 20)`, reducing the size to **9**. If split at 15, the returned part manages `[11, 15)` (4 elements) and the original part manages `[15, 20)` (5 elements). Total remaining is 9 elements.

### 4.1. How getExactSizeIfKnown differs from estimateSize

~~~java
long estimate = spliterator.estimateSize();
long exact = spliterator.getExactSizeIfKnown();
~~~

Per the default contract:

- When the Spliterator reports **`SIZED`**, `getExactSizeIfKnown()` returns the known remaining size, matching `estimateSize()`.
- When **`SIZED` is absent**, `getExactSizeIfKnown()` returns **`-1`**.

`getExactSizeIfKnown() == -1` does not mean the Spliterator is empty; it only means **no exact size is declared**. Do not use `estimateSize()` to allocate a large output array if that number is merely an estimate or `Long.MAX_VALUE`.

### 4.2. Size values change during traversal

For a properly designed fixed-size source, after a successful `tryAdvance`, the remaining count decreases. After a successful `trySplit`, the original object's `estimateSize()` reflects **only the portion it still manages**, not the pre-split size.

Do not write a Spliterator that always returns the initial total size after consumption or splitting while still declaring `SIZED`. Doing so introduces contradictory size data and can disrupt Stream optimizations.

## 5. SIZED and SUBSIZED: Promises You Must Keep

`characteristics()` returns a bitmask combination of constants from `Spliterator`, of which the key ones for this topic are:

| Characteristic | Meaning |
|---|---|
| `SIZED` | Remaining size before traversal/splitting is known exactly per contract |
| `SUBSIZED` | The current Spliterator and **all Spliterators produced by `trySplit`** also guarantee `SIZED` and `SUBSIZED` |
| `ORDERED` | Has an encounter order; split results on ordered sources must be prefixes |
| `IMMUTABLE` | Source structure cannot be altered in a way that violates properties during traversal |
| `CONCURRENT` | Source is designed to handle concurrent modifications under its own contract |
| `DISTINCT` | No two distinct elements are equal per `equals` |
| `SORTED` | Elements follow a defined sort order, paired with `getComparator()` |
| `NONNULL` | Elements are never `null` |

**Distinction:** `SIZED` does not automatically imply `SUBSIZED`. A Spliterator may know its initial size accurately without guaranteeing that every child branch continues to know its size accurately. If you declare `SUBSIZED`, you must uphold the stronger promise across **the entire Spliterator tree**.

For structurally immutable arrays or index ranges `[start, end)`, computing the exact size of every split half is usually feasible, so `SIZED | SUBSIZED` is a sound choice.

### 5.1. Do not declare characteristics just hoping for faster runs

Falsely declaring `SIZED` can cause terminal operations like `count()` to rely on the reported size without necessarily traversing each element. If the reported count is wrong, results can be incorrect or trigger internal issues.

Similarly, if an unsorted source declares `SORTED`, a pipeline may optimize based on a false promise. Only declare characteristics that **the source truly guarantees**.

## 6. Observing trySplit on Standard Java Sources

Before writing a custom Spliterator, we can observe the behavior on a `List`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

public class StandardSplitDemo {
    public static void main(String[] args) {
        List<Integer> values =
            Arrays.asList(0, 1, 2, 3, 4, 5, 6, 7);

        Spliterator<Integer> remaining = values.spliterator();

        System.out.println(remaining.estimateSize()); // 8
        System.out.println(remaining.getExactSizeIfKnown()); // 8

        Spliterator<Integer> prefix = remaining.trySplit();

        if (prefix != null) {
            System.out.println(
                "Returned part: " + prefix.estimateSize()
            );
            System.out.println(
                "Original part: " + remaining.estimateSize()
            );

            // For an ORDERED List, the returned part is a prefix.
            System.out.println(StreamSupport.stream(prefix, false).toList());
        }

        System.out.println(StreamSupport.stream(remaining, false).toList());
    }
}
~~~

**Note on output:** Java does not promise that every `List` Spliterator will split **strictly in half**. For instance, an implementation might split 4–4, or branch sizes could differ, or `trySplit()` could return `null`. What matters is **no duplicated/lost content**, a valid prefix if `ORDERED`, and sizes conforming to declared characteristics.

The code above uses `Stream.toList()` (Java 16+). On Java 8–15, you can replace it with `collect(Collectors.toList())`.

## 7. Writing a Custom Spliterator.OfInt for an Integer Range

Now we create a custom source for the integer range **`[startInclusive, endExclusive)`**, similar to the semantics of `IntStream.range`. This source has:

- Two bounds: `current` (next element) and `fence` (**exclusive** endpoint).
- `tryAdvance` emits `current` and increments the cursor.
- `trySplit` splits the untraversed part into a **returned first half** and a **retained second half**.
- `estimateSize` returns the exact `fence - current`.
- `characteristics` announces only the properties truly guaranteed.

We choose `Spliterator.OfInt` to work with `int` directly, avoiding boxing when summing and filtering numbers.

### 7.1. Complete Java program

Create a file `RangeSpliteratorDemo.java` with the contents below; the program runs on **Java 8+**.

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class RangeSpliteratorDemo {

    static final class RangeSpliterator implements Spliterator.OfInt {
        private int current;
        private final int fence;

        RangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("start > end");
            }
            this.current = startInclusive;
            this.fence = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action, "action");

            if (current >= fence) {
                return false;
            }

            int value = current;
            current++;
            action.accept(value);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            long remaining = estimateSize();
            if (remaining <= 1) {
                return null;
            }

            // Compute in long to avoid overflow when int bounds are far apart.
            long middleAsLong = (long) current + remaining / 2;
            int middle = (int) middleAsLong;

            // Return prefix [current, middle).
            Spliterator.OfInt prefix =
                new RangeSpliterator(current, middle);

            // Keep suffix [middle, fence) in the current instance.
            current = middle;
            return prefix;
        }

        @Override
        public long estimateSize() {
            return (long) fence - current;
        }

        @Override
        public int characteristics() {
            return Spliterator.ORDERED
                 | Spliterator.SIZED
                 | Spliterator.SUBSIZED
                 | Spliterator.IMMUTABLE
                 | Spliterator.NONNULL
                 | Spliterator.DISTINCT;
        }
    }

    public static void main(String[] args) {
        RangeSpliterator original = new RangeSpliterator(0, 10);

        Spliterator.OfInt prefix = original.trySplit();

        if (prefix == null) {
            throw new AssertionError("This range must be splittable");
        }

        System.out.println(prefix.estimateSize());    // 5
        System.out.println(original.estimateSize());  // 5

        int[] left = StreamSupport.intStream(prefix, false).toArray();
        int[] right = StreamSupport.intStream(original, false).toArray();

        System.out.println(Arrays.toString(left));
        // [0, 1, 2, 3, 4]

        System.out.println(Arrays.toString(right));
        // [5, 6, 7, 8, 9]

        // Create new sources: two separate pipelines, never reuse an old Stream.
        long sequential = StreamSupport.intStream(
            new RangeSpliterator(0, 1_000), false
        ).asLongStream().sum();

        long parallel = StreamSupport.intStream(
            new RangeSpliterator(0, 1_000), true
        ).asLongStream().sum();

        System.out.println(sequential); // 499500
        System.out.println(parallel);   // 499500
    }
}
~~~

This is **a source with an exact known size**. The code does not implement a custom `forEachRemaining` because `Spliterator.OfInt` already provides remaining traversal based on `tryAdvance`; in high-performance sources you may optimize that method further, provided it preserves the contract and never re-emits elements.

### 7.2. Why use long when computing the midpoint?

The naive calculation:

~~~java
int middle = (current + fence) / 2; // Unsafe near int bounds.
~~~

can overflow `int` when `current` and `fence` are both large, even when each bound individually is valid.

In the example, we use:

~~~java
long remaining = (long) fence - current;
long middleAsLong = (long) current + remaining / 2;
int middle = (int) middleAsLong;
~~~

When `current < fence` and `remaining >= 2`, `middleAsLong` lies **between the two bounds** and is representable in `int`. Using `long` also enables `estimateSize` to accurately report ranges exceeding `Integer.MAX_VALUE` elements.

For instance, the element count of `[Integer.MIN_VALUE, Integer.MAX_VALUE)` is **4,294,967,295**, exceeding `int` yet fitting within `long`. You should never allocate an array holding that entire range; the example solely illustrates size and midpoint accuracy.

### 7.3. Why not declare SORTED?

This source emits strictly increasing numbers, which are data-wise completely sorted. Still, the example intentionally **does not declare `SORTED`**, because properly publishing that characteristic also requires adhering to the `getComparator()` contract (returning `null` for natural ordering).

The **`ORDERED`** characteristic merely states there is an encounter order and `trySplit` must return a prefix; it is **not equivalent** to `SORTED`. When implementing custom sources, prefer declaring only the characteristics you have thoroughly understood and verified.

## 8. Proving the Invariant of the Custom Source

For `RangeSpliterator`, at any moment before completion:

~~~text
Remaining elements: current, current+1, ..., fence-1
Managed interval:   [current, fence)
Remaining size:     fence - current
~~~

Suppose initially `current = a` and `fence = b`, with `a < b`. After splitting at `m`:

~~~text
Returned prefix:         [a, m)
Suffix kept in original: [m, b)

[a, m) ∩ [m, b) = ∅
[a, m) ∪ [m, b) = [a, b)
~~~

From these two relations, we deduce:

1. No element belongs to both branches.
2. No element is skipped.
3. The returned branch is a prefix, conforming to `ORDERED`.
4. The sum of both branch sizes equals the remaining source size before splitting.
5. The new branches remain half-open intervals, continuing to satisfy `SIZED` and `SUBSIZED`.

These invariants **matter more** than forcing each branch to hold exactly half the elements on odd-length intervals. For 9 elements, splitting 4–5 is completely valid.

## 9. Observing How tryAdvance Affects Size

A `Spliterator` is not only split—it is also **consumed incrementally**:

~~~java
RangeSpliterator remaining = new RangeSpliterator(10, 16);

System.out.println(remaining.estimateSize()); // 6

boolean hasNext = remaining.tryAdvance(
    (int value) -> System.out.println(value)
); // Prints 10

System.out.println(hasNext);                  // true
System.out.println(remaining.estimateSize()); // 5

Spliterator.OfInt prefix = remaining.trySplit();

System.out.println(prefix.estimateSize());    // 2
System.out.println(remaining.estimateSize()); // 3

prefix.forEachRemaining((int value) ->
    System.out.println("Prefix: " + value)
); // 11, 12

remaining.forEachRemaining((int value) ->
    System.out.println("Suffix: " + value)
); // 13, 14, 15

System.out.println(remaining.estimateSize()); // 0
~~~

This example uses the `RangeSpliterator` class declared inside `RangeSpliteratorDemo` in section 7; when practicing, you can place this snippet inside that class's `main`.

Key observations:

- After taking element 10, the Spliterator only has `[11, 16)` left, size = 5.
- `trySplit` divides `[11, 16)` into `[11, 13)` (2 elements) and `[13, 16)` (3 elements).
- Exhausting both branches emits 11–15 **exactly once**.
- Once exhausted, the next `tryAdvance` returns `false` and `estimateSize()` is 0.

In real code, never use a `Spliterator` or `Stream` after handing it off to another pipeline for processing. Illustrative direct calls should only be made while you hold exclusive ownership of the source.

## 10. StreamSupport: Turning a Spliterator into a Stream Source

Two familiar methods in `java.util.stream.StreamSupport`:

~~~java
StreamSupport.stream(Spliterator<T> spliterator, boolean parallel)

StreamSupport.intStream(Spliterator.OfInt spliterator, boolean parallel)
~~~

There are also `longStream` and `doubleStream` for `OfLong`/`OfDouble`.

The `parallel` parameter specifies whether the Stream is created in **sequential** (`false`) or **parallel** (`true`) mode. This does not alter the required correctness of `trySplit` or `estimateSize`.

~~~java
long sum = StreamSupport.intStream(
        new RangeSpliterator(0, 100),
        true
    )
    .filter(n -> n % 2 == 0)
    .asLongStream()
    .sum();

System.out.println(sum); // 2450
~~~

The example above uses the custom source from section 7, so place it in the same class scope or use its qualified name. Even numbers from 0 to 98 sum to `2450`.

A processing pipeline:

~~~mermaid
flowchart LR
    A["Spliterator.OfInt"] --> B["StreamSupport.intStream"]
    B --> C["filter(n % 2 == 0)"]
    C --> D["asLongStream()"]
    D --> E["sum()"]
    F["trySplit / estimateSize"] --> A
~~~

`filter`, `map`, `reduce`, `collect`, and other operations remain at the **pipeline layer**. Source design should only determine emitted data, splitting logic, and the characteristics the source can guarantee.

### 10.1. Enabling parallel does not automatically split into many parts

If `trySplit()` always returns `null`, the framework can still create a Stream with `parallel = true`, but **the source does not support splitting work at the Spliterator level**. Consequently, the ability to utilize multiple threads for source traversal will be limited.

Conversely, even if `trySplit()` splits well, parallel execution is not automatically faster: there are still splitting costs, memory overhead, stateful intermediate operations, result merging, and hardware resource limits.

## 11. Splitting Too Small or Too Large Both Have Costs

Our custom example splits every range containing at least two elements. This is **logically correct**, but if the framework keeps splitting into many tiny branches, object creation and coordination overhead can rise.

Several strategies:

| Strategy | Strength | Trade-off to Control |
|---|---|---|
| Split index range roughly in half | Balanced, easy size math, further splittable | Unaware of per-element processing cost |
| Split in fixed-size batches | Suits sequential sources or batch readers | Must handle final batch and preserve ORDERED |
| Stop splitting below a minimum count | Avoids overhead for tiny tasks | May reduce parallelization opportunities |
| Do not support splitting | Simple for unsplittable sources | Parallel throughput may be limited |

If you want to stop splitting very small ranges, a variant can be written as:

~~~java
@Override
public Spliterator.OfInt trySplit() {
    long remaining = estimateSize();
    if (remaining < 1_024) {
        return null;
    }

    int middle = (int) ((long) current + remaining / 2);
    Spliterator.OfInt prefix =
        new RangeSpliterator(current, middle);
    current = middle;
    return prefix;
}
~~~

This is an **alternative implementation** for `trySplit` in `RangeSpliterator`, not an extra method added alongside the old one. The 1,024 threshold is just an example; choosing a threshold depends on per-element workload and benchmark results on the target system.

## 12. Unknown-Size Sources: estimateSize Is Not Always Exact

Not every source is an integer range or an array. An `Iterator` might fetch data incrementally without knowing upfront how many elements exist.

Java provides `Spliterators.spliteratorUnknownSize`:

~~~java
import java.util.Arrays;
import java.util.Iterator;
import java.util.Spliterator;
import java.util.Spliterators;

public class UnknownSizeDemo {
    public static void main(String[] args) {
        Iterator<String> iterator =
            Arrays.asList("A", "B", "C").iterator();

        Spliterator<String> source =
            Spliterators.spliteratorUnknownSize(
                iterator,
                Spliterator.ORDERED | Spliterator.NONNULL
            );

        System.out.println(
            source.hasCharacteristics(Spliterator.SIZED)
        ); // false

        System.out.println(source.getExactSizeIfKnown()); // -1

        System.out.println(
            source.estimateSize() == Long.MAX_VALUE
        ); // true on a newly created unknown-size source
    }
}
~~~

Although the **sample data** actually has three elements, a Spliterator created from an Iterator receives no size guarantee under the contract. Here, `Long.MAX_VALUE` represents **unknown element count**, not an estimate safe to allocate against.

Note: an implementation may split an Iterator into **pre-fetched batches**, making a child branch's estimate differ from the original source. Do not write logic that depends on internal batching details or exact `trySplit` positions of a library class.

### 12.1. Do not report SIZED and SUBSIZED for a source that cannot guarantee them

If a source can add or remove elements during traversal, or its size is unknown upfront, declaring `SIZED | SUBSIZED` is a false promise. `Spliterators.spliteratorUnknownSize` does not guarantee `SIZED` and `SUBSIZED` on the root Spliterator.

Do not guess "around 1,000 elements left" and attach `SIZED`. Return a reasonable estimate if possible, but **omit `SIZED`** unless it is guaranteed exact per the contract.

### 12.2. Infinite sources need a stopping point

A `Spliterator` backed by an unbounded generator can return `Long.MAX_VALUE` from `estimateSize`. An operation like `collect(toList())` on an infinite source cannot complete without a truncation step or proper termination condition.

~~~java
// Caution: infinite source, cannot collect everything.
// Stream.generate(() -> 1).collect(Collectors.toList());

// Finite bound:
int[] firstFive = java.util.stream.IntStream
    .generate(() -> 1)
    .limit(5)
    .toArray();

System.out.println(java.util.Arrays.toString(firstFive));
// [1, 1, 1, 1, 1]
~~~

`limit` can short-circuit a source, but cost and termination also depend on **preceding intermediate operations**. A `sorted()` step on an infinite source may never terminate even with `limit(5)` downstream.

## 13. ORDERED, DISTINCT, SORTED Characteristics and Pipeline Impact

A `Spliterator` does more than supply data: it describes **properties that a Stream can trust**.

- `ORDERED` refers to encounter order, not necessarily ascending sorted values.
- `SORTED` is stronger: data must obey an ordering relation and corresponding `getComparator`; it implies `ORDERED`.
- `DISTINCT` means no two elements are equal per `equals`; ascending numbers in a range make this characteristic valid.
- `NONNULL` means elements are non-null; for primitive Streams, this holds naturally.
- `SIZED` and `SUBSIZED` refer to element count, **not byte size or memory allocation**.

If `DISTINCT` or `SORTED` is falsely announced, operations like `distinct()` or `sorted()` may optimize based on false assumptions. Wrong characteristics do not merely hurt performance—they can produce **wrong output data**.

### 13.1. Do not equate ORDERED with sequential traversal

An `ORDERED` source can still be processed in parallel. Encounter order merely imposes semantic requirements that operations such as `forEachOrdered`, `findFirst`, or `limit` must respect when applicable.

Conversely, a source without `ORDERED` is not required to shuffle its output. One run appearing "in order" is not a guarantee for business logic to depend on.

## 14. Thread-Safety and Data Slice Ownership

A custom `Spliterator` **does not need to be thread-safe by default** to support a parallel Stream. The typical model is:

1. The framework owns one Spliterator.
2. The framework may call `trySplit` to create a new Spliterator.
3. **Each branch** is traversed independently and owns its own cursor state.
4. Once branches are handed to separate tasks, never use the same Spliterator from multiple threads unless the source explicitly supports it.

For example, `RangeSpliterator` has separate `current` fields across branches and an immutable `fence`. This prevents two threads from updating the same counter concurrently.

**Do not** write a `trySplit` that simply returns `this`:

~~~java
@Override
public Spliterator.OfInt trySplit() {
    // Wrong: both branches share the exact same current state!
    return this;
}
~~~

If the framework treats the returned value and the original object as two separate branches, the same object gets traversed overlappingly, risking duplicates, dropped elements, race conditions, or infinite split loops.

Similarly, never create two child Spliterators pointing to **the exact same full range** without adjusting bounds. A valid split must partition the **untraversed** portion into disjoint segments.

### 14.1. NONNULL, IMMUTABLE, and CONCURRENT are not interchangeable

`IMMUTABLE` means **the source structure is not modified** during traversal under that source's model. `CONCURRENT` means **the source supports concurrent modifications** under documented conditions. `NONNULL` means elements are not null. These are independent concepts; do not attach `CONCURRENT` merely because you want to run `parallelStream`.

For a custom source backed by an array that another thread might mutate, arbitrarily declaring `IMMUTABLE` can be wrong. Consider a snapshot or synchronization mechanism matching your data requirements.

## 15. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| `trySplit` returns `this` | Both branches share state; may duplicate/drop elements | Create a child Spliterator managing a **distinct** range |
| After split, original keeps full range | Overlapping elements between returned and original branches | Advance original's `current` to the midpoint |
| Returning suffix on an `ORDERED` source | Violates prefix rule | Return `[current, middle)` and keep `[middle, fence)` |
| `estimateSize` always returns initial size | Size fails to reflect remaining elements | Compute from current cursor to boundary |
| Computing `(start + end) / 2` in `int` | Can overflow and split incorrectly | Use safe `long` arithmetic |
| Declaring `SIZED` on unknown-size source | Framework may trust wrong element count | Omit `SIZED` unless guaranteed |
| Declaring `SUBSIZED` when children lack exact size | Violates Spliterator tree contract | Ensure every child satisfies it or omit `SUBSIZED` |
| Assuming `trySplit` always splits | Source may return `null` | Handle unsplittable case and fall back to sequential traversal |
| Enabling `parallel` expecting many threads | Source may not split or overhead dominates | Measure and design a splitting strategy suited to the source |
| Splitting every element into tiny tasks | Object and scheduling overhead | Split in batches or above a threshold |
| Concurrently traversing a non-thread-safe Spliterator | Race conditions and unpredictable output | Give each branch an independent owner |
| Collecting an entire infinite source | Never completes, may exhaust resources | Apply a limit or proper stopping rule |
| Declaring `SORTED` on an unsorted source | Pipeline may skip necessary sorting steps | Declare only accurate characteristics |
| Relying on `peek` + `count` to count traversal calls | `SIZED` optimization may skip intermediate steps | Check terminal outputs and test invariants |

## 16. Practice Exercise: Verifying Partitioning and Parallel Sum

**Problem:** Complete a Spliterator for `[0, 20)`, then compare sequential and parallel results. Use the `RangeSpliterator` class written in section 7.

**Requirements:**

1. Create a Spliterator managing `[0, 20)` and verify `estimateSize() == 20`.
2. Call `trySplit()` once to obtain the prefix and suffix parts.
3. Traverse each branch using `StreamSupport.intStream(..., false).toArray()`.
4. Verify the total element count is 20, there are no duplicate elements, and concatenating the two parts yields `0..19`.
5. Use a **fresh Spliterator** to create a parallel `IntStream` to compute the sum, comparing against the sequential result.
6. Change `trySplit` to use a threshold and observe that **the correct result remains unchanged**, even though the degree of splitting differs.

### Reference solution (place inside main of RangeSpliteratorDemo)

~~~java
RangeSpliterator original = new RangeSpliterator(0, 20);
System.out.println(original.estimateSize()); // 20

Spliterator.OfInt firstHalf = original.trySplit();
if (firstHalf == null) {
    throw new IllegalStateException("Cannot split");
}

int[] left = StreamSupport.intStream(firstHalf, false).toArray();
int[] right = StreamSupport.intStream(original, false).toArray();

int[] joined = new int[left.length + right.length];
System.arraycopy(left, 0, joined, 0, left.length);
System.arraycopy(right, 0, joined, left.length, right.length);

int[] expected = java.util.stream.IntStream.range(0, 20).toArray();

System.out.println(Arrays.equals(joined, expected)); // true

long serialSum = StreamSupport.intStream(
    new RangeSpliterator(0, 20), false
).asLongStream().sum();

long parallelSum = StreamSupport.intStream(
    new RangeSpliterator(0, 20), true
).asLongStream().sum();

System.out.println(serialSum);   // 190
System.out.println(parallelSum); // 190
~~~

Because our source is `ORDERED`, combining the prefix first and the suffix second reproduces `0..19` accurately. If you accidentally swap parts, duplicate elements, or forget to update the original's `current` after splitting, `Arrays.equals(joined, expected)` will evaluate to `false`.

**Note on testing `count()`:** For a source reporting `SIZED`, the `count()` terminal operation can use the declared size directly without forcing element traversal. Therefore, to test **`tryAdvance` and `trySplit` behavior**, actually collect or compute over the elements—such as `toArray()` or `sum()`—and compare against expected output. Do not rely solely on `count() == 20` to conclude a custom source emits all 20 elements properly.

### Self-check questions

1. What does `trySplit()` return when it cannot split further? — **`null`**.
2. For an `ORDERED` Spliterator, is the part returned by split a prefix or suffix? — **Prefix**.
3. What type does `estimateSize()` return? — **`long`**.
4. Does `Long.MAX_VALUE` from `estimateSize` always mean the source has exactly `Long.MAX_VALUE` elements? — **No**, it may indicate an unknown size or infinite source.
5. Does `SIZED` automatically guarantee `SUBSIZED`? — **No**.
6. What does `SUBSIZED` require? — **The current Spliterator and all child branches from splitting have exact sizes, continuing to satisfy SIZED/SUBSIZED**.
7. After a Spliterator for `[0, 10)` has emitted 0, what is `estimateSize`? — **9**.
8. Why compute the midpoint using `long` in the example? — **To avoid `int` overflow when computing boundaries**.
9. Does creating `StreamSupport.intStream(spliterator, true)` immediately spawn threads? — **No**, it creates a Stream in parallel mode; execution happens when the pipeline runs.
10. If `trySplit()` always returns null, does `parallel = true` guarantee processing the source across multiple independent tasks? — **No**.
11. When should you omit `SIZED`? — **When you cannot guarantee the exact remaining element count**.
12. Should you use the same mutable Spliterator across two threads? — **No**, unless the source design and contract explicitly permit it.

## 17. Key Takeaways Before Designing Advanced Custom Sources

**`trySplit()`** partitions **untraversed** elements into two independent regions; for `ORDERED` sources, the returned part is a **prefix**. **`estimateSize()`** describes the remaining element count: either an exact count when `SIZED` is declared, or an estimate/`Long.MAX_VALUE` when unknown. **`SUBSIZED`** is a stronger promise: child Spliterators also preserve exact sizes.

When writing your own source, uphold the invariants: **no lost or duplicated elements**, **no shared cursors across branches**, **sizes updated accurately after traversal and splitting**, **no false characteristics**, and **proper termination support for terminal operations**. Do not treat `parallel` as a default speed button: splitting algorithms, per-element cost, result combining, and ordering all need measurement.

Understanding `trySplit` and `estimateSize` explains why some Stream sources parallelize cleanly while Iterator-, I/O-, or stateful-generator-based sources are harder to parallelize. This lays the groundwork for building custom `Spliterator`s, collectors, lazy pipelines, parallel execution, and Stream Gatherers accurately and efficiently.
