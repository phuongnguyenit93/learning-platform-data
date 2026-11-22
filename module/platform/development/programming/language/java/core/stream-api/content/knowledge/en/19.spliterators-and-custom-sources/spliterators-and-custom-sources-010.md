# Verifying Data, Ordering, and Correctness of Source Splits

## 1. Why Can a Broken `Spliterator` Break the Entire Pipeline?

In the **JAVA_STREAM_API** module, we often see pipelines like:

```java
long count = source.stream()
    .filter(item -> item.active())
    .map(Item::price)
    .reduce(0L, Long::sum);
```

Operations like `filter`, `map`, and `reduce` are only correct when **the source supplies the exact elements to process**. For standard collections, Java provides appropriate traversal mechanisms. Yet when building custom sources via `Spliterator<T>` and `StreamSupport.stream(...)`, the developer takes responsibility for **data correctness, traversal order, and source splitting**.

Imagine a source containing IDs:

```text
Original source:     [0, 1, 2, 3, 4, 5, 6, 7]
Desired split:       [0, 1, 2, 3] | [4, 5, 6, 7]

Overlap bug:         [0, 1, 2, 3, 4] | [4, 5, 6, 7]
                                             ^
                                     ID 4 processed twice

Gap bug:             [0, 1, 2] | [4, 5, 6, 7]
                                     ^
                               ID 3 lost
```

In a sequential pipeline, a bug in `trySplit()` may stay hidden because Java does not necessarily call the split method. Once `parallel()` is added, the framework splits work into multiple tasks and **totals, record counts, or output data can become wrong**.

Objectives of this lesson in the **Spliterators and Custom Sources** chapter:

1. Understand the contracts of `tryAdvance`, `forEachRemaining`, `trySplit`, `estimateSize`, and `characteristics`.
2. Prove each original element appears **exactly once** across splits, with none lost or processed twice.
3. Distinguish **encounter order** from parallel worker execution order.
4. Accurately declare `ORDERED`, `SIZED`, `SUBSIZED`, `NONNULL`, `IMMUTABLE`, and other characteristics.
5. Write a custom `Spliterator` that splits by index range and verify it both sequentially and in parallel.
6. Assess risks around mutable sources, I/O, unknown sizes, performance, and resources.

The core principle is **correct first, fast second**: splittability and parallel execution are worthless if data is lost.

## 2. What Is `Spliterator<T>`?

`java.util.Spliterator<T>` is an interface for **traversing and optionally partitioning** a collection of elements. Its name combines *split* and *iterator*, yet it is not merely an `Iterator` with an extra method: it carries metadata on size, ordering, and traversability so the Java Stream API can plan execution.

Key methods:

| Method | Contract to Understand |
| --- | --- |
| `boolean tryAdvance(Consumer<? super T> action)` | Passes **one next element** to action and returns `true`; returns `false` if exhausted |
| `void forEachRemaining(Consumer<? super T> action)` | Traverses remaining elements; default implementation loops `tryAdvance` |
| `Spliterator<T> trySplit()` | Returns a new spliterator managing **part** of the remaining elements, or `null` if not split |
| `long estimateSize()` | Estimates remaining element count; with `SIZED`, exact count per contract |
| `int characteristics()` | Describes source properties that the implementation **guarantees** |
| `long getExactSizeIfKnown()` | Returns exact size if `SIZED` is present, otherwise typically `-1` |
| `Comparator<? super T> getComparator()` | Meaningful only when `SORTED` is declared |

This is the mechanism backing many Stream sources. Example:

```java
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

List<String> names = List.of("An", "Bình", "Chi");
Spliterator<String> spliterator = names.spliterator();

List<String> copied = StreamSupport
    .stream(spliterator, false)
    .toList();

System.out.println(copied); // [An, Bình, Chi]
```

`StreamSupport.stream(spliterator, false)` creates a sequential stream; passing `true` creates a stream in parallel mode. **A Spliterator is a single-use source**, not a reusable collection: to traverse again, obtain a new spliterator from an appropriate source.

Javadoc references:

- [`Spliterator`, Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Spliterator.html)
- [`StreamSupport`, Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/StreamSupport.html)
- [Package `java.util.stream`: parallelism and non-interference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html)

## 3. `tryAdvance` Contract: Never Drop or Duplicate Elements

`tryAdvance(action)` is responsible for delivering **at most one** remaining element and advancing traversal state:

```text
cursor = 0, fence = 3
source = [A, B, C]

tryAdvance(action) -> action(A), true;  cursor = 1
tryAdvance(action) -> action(B), true;  cursor = 2
tryAdvance(action) -> action(C), true;  cursor = 3
tryAdvance(action) ->           false; cursor = 3
```

Basic verifications:

- For an `n`-element source, traversing to completion must invoke action `n` times when no errors occur.
- When returning `false` upon exhaustion, no extra element may be emitted.
- Every `true` return must correspond to **one element** passed to action.
- After reaching the end, subsequent calls on unchanged state continue reporting exhaustion.
- `action` must be non-`null`; implementations may check with `Objects.requireNonNull(action)`.

Do not skip an element simply because it is `null` or business-invalid, unless **the source is explicitly defined as a filtered source**. If invalid records must be excluded, typically place a `filter` or explicit validation layer above the Spliterator.

**Exception note:** when action throws an exception, do not assume a failed traversal step can be retried safely. Design error policies at the pipeline and source layers.

## 4. `trySplit` Contract: Splitting Two Disjoint Regions

`trySplit()` does not simply "return a copy." Given a spliterator with remaining elements `S`, after splitting:

```text
Before:
    current -> S

After:
    prefix = current.trySplit()
    prefix  -> S_left
    current -> S_right

Requirements:
    S_left ∩ S_right = ∅     (by source element POSITION)
    S_left ∪ S_right = S
```

For an **`ORDERED`** source, `trySplit` must return a spliterator traversing a **prefix** of the remaining elements and keep a **suffix** in the original spliterator. Thus:

```text
Source:            [A, B, C, D, E, F, G]
trySplit returns:  [A, B, C]
current remaining:           [D, E, F, G]
Joined in order:   [A, B, C, D, E, F, G]
```

An element with the same **value** as another still occupies a **distinct source position**. Therefore, you cannot simply inspect a `Set` of the output to detect duplicate or missing bugs:

```text
Valid source: [7, 2, 7]
Wrong:        [7, 2]       // lost one position containing value 7
Set of both:  {2, 7}       // identical Set, does not prove correctness
```

**Two mandatory checks:**

1. **Exact once-per-position coverage:** element count and occurrence multiplicity of every value must match the source.
2. **Correct ordering:** if `ORDERED` is declared, concatenating splits in prefix → suffix order must match encounter order.

`trySplit()` is allowed to return `null` when unable or unwilling to split further; there is no requirement that every source split perfectly in half. However, if a non-`null` spliterator is returned, the split must make **progress** and never retain the same element set in both objects.

## 5. Size: `estimateSize`, `SIZED`, and `SUBSIZED`

When a source has an exact size, parallel execution can distribute work better. However, misdeclaring size breaks assumptions of operations like `toArray` or `count`.

### 5.1. `SIZED` is a contract, not "a pretty good estimate"

If a spliterator carries the `SIZED` characteristic, `estimateSize()` must reflect **the exact remaining element count** before processing, barring concurrent source modifications allowed under JDK contracts.

Example of an `8`-element source:

```text
Before traversal:  estimateSize() = 8
After 1 tryAdvance: estimateSize() = 7
After 3 tryAdvance: estimateSize() = 5
After exhaustion:   estimateSize() = 0
```

`getExactSizeIfKnown()` returns the size when `SIZED` is present; otherwise, it returns `-1` by default.

### 5.2. `SUBSIZED` extends the promise to every child part

`SUBSIZED` indicates that the current spliterator and **every spliterator generated by subsequent splits** are also `SIZED` and `SUBSIZED`. This is a stronger commitment than `SIZED`.

Valid example:

```text
parent [0..10): 10 elements
   │ trySplit()
   ├─ prefix [0..5):   5 elements
   └─ current [5..10): 5 elements

prefix.trySplit():
   ├─ prefix [0..2): 2 elements
   └─ current [2..5): 3 elements
```

Each child knows its own exact length. Splits preserve:

\[
\operatorname{size}(\text{before split})
=\operatorname{size}(\text{prefix})
+\operatorname{size}(\text{remaining current})
\]

Never attach `SUBSIZED` to a source whose child spliterators would need to scan to EOF to know their size.

### 5.3. Sources with undetermined size

A line-oriented text file, socket stream, or dynamically generated iterator usually **does not know the exact element count in advance**. Unless proven, omit `SIZED` and `SUBSIZED`; `estimateSize` can return a valid approximation or `Long.MAX_VALUE` if unknown.

With `Spliterators.spliteratorUnknownSize(iterator, characteristics)`, do not pass `SIZED`/`SUBSIZED` pretending the source has a known size. A child chunk that has already materialized data might know its own size, yet that does not mean the overall initial source had an exact size.

## 6. Declaring `characteristics` Must Be Evidence-Based

`Spliterator` defines important characteristic bits:

| Characteristic | Meaning to Guarantee | Common Mistake |
| --- | --- | --- |
| `ORDERED` | Defined encounter order, and `trySplit` returns a prefix | Returning suffix while still claiming ORDERED |
| `SIZED` | Exact remaining element count known per contract | Returning initial size after partial traversal |
| `SUBSIZED` | All split child parts are also SIZED and SUBSIZED | Relying on variable-length sources |
| `NONNULL` | Emits no `null` elements | Declaring even though source permits null |
| `DISTINCT` | No two elements are equal per `equals` | Confusing distinct positions with duplicate values |
| `SORTED` | Data follows comparator or natural ordering | Having ORDERED without actually being sorted |
| `IMMUTABLE` | Source structure cannot be modified during traversal | Using unprotected mutable collections |
| `CONCURRENT` | Source permits concurrent changes per contract | Assuming thread-safety simply from using parallel stream |

Example checking bits:

```java
int properties = spliterator.characteristics();

boolean ordered = (properties & Spliterator.ORDERED) != 0;
boolean sized = spliterator.hasCharacteristics(Spliterator.SIZED);
boolean subSized = spliterator.hasCharacteristics(Spliterator.SUBSIZED);
```

**Characteristics are commitments about the source**, not "speedup" toggles. Declaring more bits than reality can cause the Stream framework to apply invalid optimizations.

### 6.1. `SORTED` is not `ORDERED`

`ORDERED` only states there is an element encounter order, not that values are sorted ascending. If declaring `SORTED`, the spliterator must also obey the ordering contract and `getComparator()`:

- `SORTED` with natural ordering: `getComparator()` returns `null`.
- `SORTED` with custom comparator: returns the corresponding comparator.
- Without `SORTED`: `getComparator()` normally throws `IllegalStateException`.

Never mark `SORTED` simply because a list happened to be sorted in one test run.

### 6.2. `IMMUTABLE` differs from deep object immutability

A snapshot list disallowing additions/removals can support `IMMUTABLE` for **source structure**. Yet if each element is a mutable object, internal fields can still mutate and affect `filter` or `map`. For snapshot sources, distinguish:

- **Unchanging element set and order:** protects traversal integrity.
- **Unchanging object contents:** an additional data-model guarantee, not automatically granted just because the source is an unmodifiable list.

### 6.3. `CONCURRENT` does not mean "this spliterator is thread-safe"

`CONCURRENT` is a property of a source supporting concurrent modifications while being traversed; it does not authorize concurrent `tryAdvance` calls on **the same unsynchronized custom spliterator object**. The standard partitioning model assigns one spliterator per branch traversing an independent region.

## 7. Complete Example: Index-Range Splitting Spliterator

For clear verification, let's design a **snapshot source from a `List`**:

1. Input data is copied into an unmodifiable list via `List.copyOf`.
2. Each spliterator holds a **half-open** range `[cursor, fence)`.
3. `tryAdvance` reads index `cursor` and increments it.
4. `trySplit` returns **the first half of the remaining slice** and updates the current spliterator to keep the second half.
5. `estimateSize` always equals `fence - cursor`.
6. The source contains no `null` because `List.copyOf` rejects null; `NONNULL` can be declared.

The full program below uses **JDK 17+**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.IntStream;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public final class IndexedSpliteratorDemo {

    private IndexedSpliteratorDemo() {}

    static final class IndexRangeSpliterator<T> implements Spliterator<T> {
        private final List<T> values;
        private int cursor;
        private final int fence;

        IndexRangeSpliterator(List<T> values, int start, int end) {
            this.values = Objects.requireNonNull(values, "values");
            if (start < 0 || end < start || end > values.size()) {
                throw new IllegalArgumentException("Invalid index range");
            }
            this.cursor = start;
            this.fence = end;
        }

        @Override
        public boolean tryAdvance(Consumer<? super T> action) {
            Objects.requireNonNull(action, "action");
            if (cursor >= fence) {
                return false;
            }

            T value = values.get(cursor);
            cursor++;
            action.accept(value);
            return true;
        }

        @Override
        public Spliterator<T> trySplit() {
            int lo = cursor;
            int remaining = fence - lo;
            if (remaining < 2) {
                return null;
            }

            int mid = lo + remaining / 2;
            cursor = mid; // Current spliterator keeps [mid, fence).
            return new IndexRangeSpliterator<>(values, lo, mid);
            // Returned spliterator holds prefix [lo, mid).
        }

        @Override
        public long estimateSize() {
            return (long) fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED | IMMUTABLE | NONNULL;
        }
    }

    static <T> Spliterator<T> from(List<T> source) {
        // Structural snapshot while rejecting null elements.
        List<T> snapshot = List.copyOf(
            Objects.requireNonNull(source, "source")
        );
        return new IndexRangeSpliterator<>(
            snapshot, 0, snapshot.size()
        );
    }

    static <T> Stream<T> stream(List<T> source, boolean parallel) {
        return StreamSupport.stream(from(source), parallel);
    }

    public static void main(String[] args) {
        List<Integer> input = IntStream.range(0, 9)
            .boxed().toList();

        List<Integer> sequential = stream(input, false).toList();
        List<Integer> parallel = stream(input, true).toList();

        System.out.println(sequential); // [0, 1, 2, 3, 4, 5, 6, 7, 8]
        System.out.println(parallel);   // [0, 1, 2, 3, 4, 5, 6, 7, 8]

        Spliterator<Integer> suffix = from(input);
        Spliterator<Integer> prefix = suffix.trySplit();

        List<Integer> firstPart = new ArrayList<>();
        List<Integer> secondPart = new ArrayList<>();
        Objects.requireNonNull(prefix).forEachRemaining(firstPart::add);
        suffix.forEachRemaining(secondPart::add);

        System.out.println(firstPart);  // [0, 1, 2, 3]
        System.out.println(secondPart); // [4, 5, 6, 7, 8]
    }
}
```

### 7.1. Why are the intervals disjoint?

Suppose pre-split state is `[lo, fence)` with length `n = fence - lo`. When `n >= 2`:

```text
mid = lo + n / 2

Returned child: [lo, mid)
Remaining parent: [mid, fence)
```

The two intervals are **disjoint** because one excludes `mid` while the other starts at `mid`; their union equals `[lo, fence)`. Each interval is strictly smaller than before, so subsequent splits make progress. When 0 or 1 elements remain, `trySplit` returns `null`.

### 7.2. Why are the characteristics in the example valid?

| Characteristic | Evidence |
| --- | --- |
| `ORDERED` | Each slice traverses in ascending index order; `trySplit` returns a prefix |
| `SIZED` | `estimateSize() == fence - cursor` is always exact |
| `SUBSIZED` | Every child part has a fixed index slice and reports exact length |
| `IMMUTABLE` | Every branch uses the structural snapshot created by `List.copyOf` |
| `NONNULL` | `List.copyOf` rejects `null` elements |
| Not `DISTINCT` | The list may contain equal values |
| Not `SORTED` | Source order is index order, not comparator sort order |
| Not `CONCURRENT` | No contract for concurrent structural source modification |

`List.copyOf` does not deep-copy individual objects. If `T` is an object with mutable fields, mutating fields externally can still affect mapper behavior. Use records or immutable models when you need content snapshots, not just structural snapshots.

### 7.3. Spliterator ownership after splitting

A spliterator is not meant to have `tryAdvance` called concurrently by multiple workers. After `trySplit` returns a prefix, each branch has **its own spliterator object** governing a disjoint range. Both objects share the read-only snapshot list without sharing `cursor`; this is a crucial condition for sound parallel execution.

## 8. Manually Testing Every Split Branch Before Running in Parallel

A test calling only `StreamSupport.stream(spliterator, false)` is insufficient because it may **never invoke `trySplit`**. Write a helper that recursively splits until no further split is possible, traversing **the prefix branch first** and **the suffix branch second**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

static <T> List<T> collectEverySplit(Spliterator<T> current) {
    Spliterator<T> prefix = current.trySplit();
    if (prefix == null) {
        List<T> result = new ArrayList<>();
        current.forEachRemaining(result::add);
        return result;
    }

    List<T> result = collectEverySplit(prefix);
    result.addAll(collectEverySplit(current));
    return result;
}
```

This helper method can live in any Java class. It is especially suited to **`ORDERED` spliterators that split into shrinking intervals**. If a custom spliterator returns a non-shrinking split (e.g., returning itself), the recursion will loop forever—a bug in `trySplit` to catch and fix, not a valid outcome.

Expected example:

```java
List<Integer> source = List.of(7, 2, 7, 9, 2);
List<Integer> result = collectEverySplit(
    IndexedSpliteratorDemo.from(source)
);

System.out.println(result); // [7, 2, 7, 9, 2]
```

Comparing **full lists** catches both legitimate value duplicates and **data-position losses/duplications** caused by broken splits. For sources marked unordered, compare **element frequency maps** and total counts instead of enforcing order.

### 8.1. Verification via independent methods

A reliable test suite should have at least three ways to observe output:

1. **Ground-truth source:** data from a known `List`.
2. **Unsplit traversal:** `forEachRemaining` on a fresh spliterator.
3. **Multi-level split traversal:** `collectEverySplit`.

Then add **sequential** and **parallel pipelines** using fresh spliterators and compare against the ground-truth source.

Never reuse a consumed spliterator across multiple tests; it has already mutated `cursor` and has no standard "rewind" operation.

## 9. JUnit 5: Testing Coverage, Ordering, Size, and Boundary Data

These tests use `IndexedSpliteratorDemo` from section 7 and `collectEverySplit` from section 8 (helper placed in the test class). JUnit Jupiter example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class IndexedSpliteratorDemoTest {

    private static <T> List<T> collectEverySplit(
        Spliterator<T> current
    ) {
        Spliterator<T> prefix = current.trySplit();
        if (prefix == null) {
            List<T> values = new ArrayList<>();
            current.forEachRemaining(values::add);
            return values;
        }
        List<T> values = collectEverySplit(prefix);
        values.addAll(collectEverySplit(current));
        return values;
    }

    @Test
    void emptyAndSingletonSourcesCannotBeSplit() {
        Spliterator<Integer> empty =
            IndexedSpliteratorDemo.from(List.of());
        assertEquals(0L, empty.estimateSize());
        assertNull(empty.trySplit());

        Spliterator<Integer> one =
            IndexedSpliteratorDemo.from(List.of(99));
        assertEquals(1L, one.estimateSize());
        assertNull(one.trySplit());
        assertEquals(List.of(99), collectEverySplit(one));
    }

    @Test
    void splitReturnsPrefixAndPreservesAllElements() {
        List<Integer> source = IntStream.range(0, 9)
            .boxed().toList();
        Spliterator<Integer> suffix =
            IndexedSpliteratorDemo.from(source);

        long before = suffix.estimateSize();
        Spliterator<Integer> prefix = suffix.trySplit();

        assertTrue(prefix != null);
        assertEquals(before,
            prefix.estimateSize() + suffix.estimateSize());
        assertEquals(4L, prefix.getExactSizeIfKnown());
        assertEquals(5L, suffix.getExactSizeIfKnown());

        List<Integer> merged = new ArrayList<>();
        prefix.forEachRemaining(merged::add);
        suffix.forEachRemaining(merged::add);
        assertEquals(source, merged);
        assertEquals(0L, prefix.estimateSize());
        assertEquals(0L, suffix.estimateSize());
    }

    @Test
    void recursiveSplitsNeverLoseOrRepeatPositions() {
        List<Integer> source = IntStream.range(0, 4_097)
            .boxed().toList();

        assertEquals(source, collectEverySplit(
            IndexedSpliteratorDemo.from(source)
        ));
    }

    @Test
    void duplicateValuesArePreservedWithMultiplicity() {
        List<Integer> source = List.of(7, 2, 7, 9, 2);

        assertEquals(source, collectEverySplit(
            IndexedSpliteratorDemo.from(source)
        ));
        assertEquals(source,
            IndexedSpliteratorDemo.stream(source, true).toList());
    }

    @Test
    void sequentialAndParallelToListPreserveEncounterOrder() {
        List<Integer> source = IntStream.range(0, 20_000)
            .boxed().toList();

        assertEquals(source,
            IndexedSpliteratorDemo.stream(source, false).toList());
        assertEquals(source,
            IndexedSpliteratorDemo.stream(source, true).toList());
    }

    @Test
    void characteristicsMatchActualContract() {
        Spliterator<Integer> s =
            IndexedSpliteratorDemo.from(List.of(2, 2, 1));

        assertTrue(s.hasCharacteristics(Spliterator.ORDERED));
        assertTrue(s.hasCharacteristics(Spliterator.SIZED));
        assertTrue(s.hasCharacteristics(Spliterator.SUBSIZED));
        assertTrue(s.hasCharacteristics(Spliterator.IMMUTABLE));
        assertTrue(s.hasCharacteristics(Spliterator.NONNULL));
        assertFalse(s.hasCharacteristics(Spliterator.DISTINCT));
        assertFalse(s.hasCharacteristics(Spliterator.SORTED));
        assertEquals(3L, s.getExactSizeIfKnown());
        assertThrows(IllegalStateException.class, s::getComparator);
    }

    @Test
    void sourceSnapshotIsIndependentOfListStructure() {
        ArrayList<Integer> mutable =
            new ArrayList<>(List.of(1, 2, 3));
        Spliterator<Integer> snapshot =
            IndexedSpliteratorDemo.from(mutable);

        mutable.add(4);
        mutable.remove(0);

        List<Integer> actual = new ArrayList<>();
        snapshot.forEachRemaining(actual::add);
        assertEquals(List.of(1, 2, 3), actual);
    }

    @Test
    void rejectsNullSourceElements() {
        List<Integer> nullable = new ArrayList<>();
        nullable.add(1);
        nullable.add(null);

        assertThrows(NullPointerException.class, () ->
            IndexedSpliteratorDemo.from(nullable)
        );
    }
}
```

**Why use `4_097` elements in the test?** An odd length prevents splits from always dividing into equal halves, helping expose off-by-one bugs in `mid`. Continue testing lengths `0`, `1`, `2`, `3`, `7`, `8`, `9`, and large sizes.

Beyond comparing outputs, test **state after each operation**: `tryAdvance` decrements size by exactly one; `trySplit` conserves total size; every new branch properly reports `SUBSIZED` if the source declares that characteristic.

## 10. Exact Verification via Keys When Values Can Repeat

`List.equals` catches discrepancies on ordered sources, yet for unordered sources with many equal values, build a **frequency** check.

Example:

```java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

static <T> Map<T, Long> frequency(List<T> values) {
    return values.stream()
        .collect(Collectors.groupingBy(
            Function.identity(),
            Collectors.counting()
        ));
}

List<Integer> input = List.of(1, 2, 1, 2, 2);
List<Integer> output = List.of(2, 1, 2, 1, 2);

System.out.println(frequency(input).equals(frequency(output))); // true
```

On unordered sources, tests should assert **frequencies** and **total count**, rather than using a `Set`, since `Set` discards occurrence counts. For objects lacking business-identity `equals`/`hashCode`, attach a **unique ID** to each element in test data or map to IDs before comparing.

If a custom spliterator constructs new objects inside `tryAdvance`, verify correctness based on **logical records** (ID, position, content) rather than insisting on object reference equality.

### 10.1. Why is total `count` alone insufficient?

Source `[1,2,3,4]` and buggy output `[1,2,2,4]` both have `count == 4`. Total element count matches, yet ID `3` was lost and ID `2` was duplicated. Combine:

- Element count.
- Frequency count per ID.
- Ordering check when `ORDERED`.
- Consistency checks across multi-level splits.

## 11. Data Order Differs from Parallel Execution Order

The `ORDERED` characteristic asserts element **encounter order**, not the execution order of lambdas across threads.

```java
List<Integer> input = java.util.stream.IntStream.range(0, 100)
    .boxed().toList();

List<Integer> orderedResult =
    IndexedSpliteratorDemo.stream(input, true)
        .map(n -> n * 2)
        .toList();

System.out.println(orderedResult.get(0)); // 0
System.out.println(orderedResult.get(1)); // 2
```

For an ordered stream, `toList()` preserves encounter order in the result even when chunks execute concurrently. However:

```java
IndexedSpliteratorDemo.stream(input, true)
    .forEach(System.out::println);
// Output printing order is not guaranteed to be 0, 1, 2, ..., 99.
```

`forEach` on a parallel stream does not guarantee encounter order; `forEachOrdered` enforces observing elements in encounter order at the potential cost of coordination overhead.

**Never** use `map` or `peek` timestamp logs as proof that a custom spliterator preserves order. Verify **contracted output results**, such as `toList()` or a manual prefix → suffix traversal.

### 11.1. `findFirst` and `findAny`

For an ordered stream:

- `findFirst` returns the first element according to encounter order.
- `findAny` may return any element, especially when running in parallel.

If `trySplit` returns the **suffix** while the spliterator still declares `ORDERED`, order-sensitive operations such as `findFirst`, `limit`, or `takeWhile` can return wrong results.

### 11.2. `sorted` cannot fix every source bug

`sorted` sorts **the elements it receives**. If the source spliterator dropped a record or duplicated an ID, `sorted` merely sorts the **already-corrupted** dataset; it cannot resurrect lost elements.

## 12. Common Mistakes When Implementing `trySplit`

### 12.1. Forgetting to advance the current spliterator's boundary

Wrong:

```java
// Buggy idea: creates prefix while current still keeps [cursor, fence).
// return new IndexRangeSpliterator<>(values, cursor, mid);
```

After returning prefix `[cursor, mid)`, the original spliterator still traverses from `cursor`, causing **duplicate elements**. You must update `cursor = mid` when splitting, as in the complete example.

### 12.2. Skipping an element at the boundary

Wrong:

```java
// Buggy idea:
// current.cursor = mid + 1;
// return new IndexRangeSpliterator<>(values, lo, mid);
```

Neither the prefix `[lo, mid)` nor the suffix `[mid+1, fence)` contains the element at index `mid`. Output length shrinks by one compared to the source.

### 12.3. Returning the suffix when `ORDERED` is declared

For an ordered spliterator, the branch returned from `trySplit` must be a **prefix** of the remaining elements. Returning the suffix and keeping the prefix in the current instance might preserve total element count, yet operations requiring encounter order will see contract-violating results.

### 12.4. Returning `this` as a split part

Returning the same object or two spliterators sharing one cursor destroys **independent ownership**, causing duplicates, losses, or races when two branches run in parallel. `trySplit` must return a child spliterator representing a **disjoint** data slice.

### 12.5. Declaring `SIZED` without updating `estimateSize`

If `tryAdvance` has already traversed three elements while `estimateSize` still returns the initial size, `SIZED` is falsely declared. Size-based optimizations can break.

### 12.6. Declaring `DISTINCT` despite duplicate records in source data

If the input has two elements equal per `equals`, declaring `DISTINCT` is wrong even if they come from two different positions or sources. Operations like `distinct()` may trust the source characteristic to optimize; outputs become wrong when falsely declared.

### 12.7. Misusing `IMMUTABLE` or `CONCURRENT`

When elements are added or removed during traversal without implementation support, the source may miss items, duplicate items, or throw errors. Never declare `IMMUTABLE` for an unsnapshotted mutable `ArrayList`; never declare `CONCURRENT` just because an application wants to call `parallelStream()`.

## 13. Mutation, Late Binding, and Source Ownership

Collection sources can change over time. When customizing a spliterator, explicitly choose one of these models:

1. **Immutable snapshot:** copy the structure before traversal; makes `SIZED` and `SUBSIZED` easy to prove.
2. **Late-binding:** bind to the element set only when traversal or splitting starts, while clearly documenting visibility of prior edits and policy for edits after binding.
3. **Concurrently modifiable source:** requires a data structure and algorithm that genuinely support traversal under concurrent modifications.

The `IndexedSpliteratorDemo.from` example intentionally picks **snapshot**, ensuring additions or removals in the original `List` **do not alter traversal output**. This trades extra memory to simplify the contract and eliminate structural races.

### 13.1. `StreamSupport`'s Supplier overload

`StreamSupport` also has an overload taking a spliterator supplier:

```java
static <T> Stream<T> stream(
    Supplier<? extends Spliterator<T>> supplier,
    int characteristics,
    boolean parallel
)
```

The supplier is invoked to create the spliterator when the terminal operation starts, narrowing the gap between wiring the source and starting traversal. **The characteristics passed to `stream` must match the spliterator returned by the supplier**; you must not supply a different bitmask hoping to optimize.

Illustrative example:

```java
import java.util.List;
import java.util.Spliterator;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<Integer> original = List.of(4, 5, 6);
Supplier<Spliterator<Integer>> supplier =
    () -> IndexedSpliteratorDemo.from(original);

int flags = Spliterator.ORDERED | Spliterator.SIZED
    | Spliterator.SUBSIZED | Spliterator.IMMUTABLE
    | Spliterator.NONNULL;

Stream<Integer> stream = StreamSupport.stream(
    supplier, flags, false
);

System.out.println(stream.toList()); // [4, 5, 6]
```

**Caution:** the supplier overload does not automatically make a mutable source thread-safe. If `original` is modified concurrently right while the supplier copies it, you still need synchronization or an appropriate snapshot policy. For large datasets, snapshot memory cost must also be weighed.

## 14. I/O Sources and Unknown Sizes

How many lines a text file contains is typically **unknown upfront** when opened. Do not assume you can split by byte ranges like index-splitting a `List`, because:

- Text encodings may use variable numbers of bytes per character.
- Line boundaries can fall across chunk boundaries.
- Naive byte splitting can cut a single line in half or drop lines.
- The source can change or hit read errors mid-traversal.

For sequential sources using an `Iterator`, standard utilities can be used:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

static long countLines(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(
            path, StandardCharsets.UTF_8)) {
        Iterator<String> iterator = reader.lines().iterator();
        Spliterator<String> spliterator =
            Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED | Spliterator.NONNULL
            );

        Stream<String> lines = StreamSupport.stream(
            spliterator, false
        );
        return lines.count();
    }
}
```

This example keeps `BufferedReader` open until after the terminal operation and closes it via `try-with-resources`. `Spliterators.spliteratorUnknownSize` must not advertise the overall source as `SIZED`; if reading multiple files, ownership of each sub-reader/stream must also be defined.

**What never to do:** pass `Files.size(path)` (**byte** count) as the element count of a **line**-emitting spliterator and declare `SIZED`. Byte count is not line count. Some sources may supply reliable metadata giving exact record counts, yet you must verify that metadata truly matches traversal output.

### 14.1. `StreamSupport.stream` does not auto-manage I/O source closing

`StreamSupport.stream(spliterator, ...)` creates a stream backed by a spliterator without knowing which `BufferedReader` or file descriptor the application owns. Terminal operations like `count` are not resource-closing commands. Use `try-with-resources` with the right owner; if creating a stream with its own lifecycle, use `onClose`, though callers must still close the stream.

## 15. Parallel Correctness: Three Distinct Verification Categories

A custom spliterator can produce right sequential results yet fail in parallel. When evaluating, split verification into three categories:

### 15.1. Functional verification

Compare lists/frequencies/IDs against a reliable **oracle** such as the source `List`, including:

- Empty and singleton sources.
- Even and odd element counts.
- Duplicate values.
- Deep multi-level splits.
- Boundary cases at `start`, `mid`, and `fence`.
- Source modifications before/after spliterator creation (per chosen model).

### 15.2. Ordering contract verification

If `ORDERED` is declared:

- `trySplit` must return a prefix.
- Traversing split parts in prefix → suffix order must match the original sequence.
- `StreamSupport.stream(spliterator, true).toList()` must match the original sequence.
- Never use `forEach` log printing order as evidence.

For unordered sources, verify only **frequencies and contents**, without enforcing unpromised ordering.

### 15.3. Performance and resource verification

Only after proving correctness should you measure:

| Metric | Why Inspect It? |
| --- | --- |
| Sequential/parallel pipeline duration | Determine whether parallelism actually pays off |
| Split chunk sizes | Detect heavily skewed splits causing load imbalance |
| Number of splits | Avoid spawning too many tiny tasks |
| CPU and memory | Identify allocation and snapshot management overhead |
| I/O source latency | Slow sources can make extra splitting counterproductive |
| Open file/resource count | Ensure zero leaks from custom sources |

Never assume `trySplit` balances perfectly or call counts match CPU thread counts. The framework decides how to schedule work. Reliable benchmarks require warm-up, representative inputs, and proper tooling (e.g., JMH in dedicated optimization workflows).

## 16. Mental Checklist When Designing Custom Sources

| Question | Decision and Verification |
| --- | --- |
| How many times will each source position be emitted? | Exactly **once**, no losses or duplicates |
| When splitting, which parts do child branches manage? | Union covers everything; intersection by position is empty |
| Does the source have an encounter order? | If yes, return a **prefix** from `trySplit` |
| Is the size exact? | Declare `SIZED` only when genuinely known |
| Do all child parts also have exact sizes? | Declare `SUBSIZED` only when proven |
| Can the source contain `null` elements? | Declare `NONNULL` only if guaranteed never to emit null |
| Is data sorted? | Declare `SORTED` only with a compliant comparator |
| Can duplicate values appear? | Omit `DISTINCT` if so |
| Can source structure change during traversal? | Choose clear snapshot, late-binding, or concurrent semantics |
| Are there external resources to close? | Define owner, `try-with-resources`, and close handlers |
| Can one spliterator be shared across threads? | Not by default; split into objects owning disjoint regions |
| Is sequential testing enough? | No; force multi-level manual splits and compare parallel runs |
| Does matching `count` prove correctness? | No; verify frequencies, ordering, sizes, and boundaries |
| Should `parallel()` be enabled? | Only after proving correctness and benchmarking |

## 17. Practice Exercises

**Exercise 1 — Finding an overlap bug.** A spliterator handles `[start,end)`, returns `[start,mid)` on split, yet forgets to update `start` on the current object. Using IDs `0..7`, show which elements repeat, fix `trySplit`, and write a test counting each ID's frequency.

**Exercise 2 — Boundary omission bug.** After splitting at `mid`, a developer sets `start = mid + 1` on the original object. Write tests for lengths `1,2,3,7,8,9` to detect the dropped element. Explain why **half-open** intervals are a useful model.

**Exercise 3 — Declaring characteristics.** For a snapshot list `[3,1,3]` traversed by index, pick the valid bits among `ORDERED`, `SIZED`, `SUBSIZED`, `DISTINCT`, `SORTED`, `NONNULL`, and `IMMUTABLE`. Explain why `ORDERED` does not imply `SORTED`.

**Exercise 4 — Parallel verification.** Run `IndexedSpliteratorDemo.stream(source,true)` on `20_000` unique IDs and compare with `source` via `toList`. Then test a source with duplicate IDs; does comparing `Set` alone catch every bug? Write a frequency-based check.

**Exercise 5 — `estimateSize`.** Create a spliterator with `9` elements, split once, and sum `estimateSize` of both branches. Traverse two elements from the prefix branch and check the remaining size. Explain when `SIZED` and `SUBSIZED` may be declared.

**Exercise 6 — Comparator and `SORTED`.** Create a spliterator traversing `[1,2,3,4]` in order and declaring `SORTED`. State the requirement on `getComparator`. Then change data to `[1,3,2,4]` and explain why `SORTED` can no longer be declared.

**Exercise 7 — Unknown-length I/O source.** Use `BufferedReader.lines()` and `Spliterators.spliteratorUnknownSize` to count lines. Identify which resource must be closed, why file byte size is not element count, and the difference between an empty source and a file-read error.

**Exercise 8 — Testing source immutability.** Create an `ArrayList<Integer>`, obtain a snapshot spliterator, then add and remove elements from the original `ArrayList`. Verify the snapshot preserves the copied data. Explain why mutable object contents can still change even when structure is snapshotted.

**Exercise 9 — Splitting overhead.** With a `1_000_000`-element source where each mapper only performs simple addition, compare sequential and parallel execution. Observe timing, allocations, and split counts; explain why spawning too many tasks can slow processing down.

## 18. Conclusion and Guiding Principles

`Spliterator` is where the Java Stream API receives **elements and guarantees about the source**. When implementing one yourself, what matters is not merely writing a `trySplit` that returns a new object, but proving that **every split produces an exact partition, without overlap or omissions, while preserving encounter order if `ORDERED` is declared**.

Start from a small source with known data, test `tryAdvance` and `estimateSize`, then deliberately invoke multi-level `trySplit` and verify output against the ground-truth source. Only publish `SIZED`, `SUBSIZED`, `NONNULL`, `IMMUTABLE`, or `SORTED` once proven true. Only then evaluate parallel execution, resource management, and performance. That workflow ensures declarative pipelines with `filter`, `map`, `reduce`, `collect`, and multi-level collectors receive sound data right from the source stage.
