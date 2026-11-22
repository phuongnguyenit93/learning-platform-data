# Creating Streams with `StreamSupport` in Java

## 1. When Is `StreamSupport` Needed?

Most Java programs obtain Streams from built-in sources:

```java
List<String> names = List.of("Lan", "Minh", "An");
Stream<String> namesStream = names.stream();

IntStream numbers = IntStream.rangeClosed(1, 5);
Stream<String> codes = Stream.of("A01", "A02");
```

However, there are cases where the data **is not a `Collection`** with a built-in `stream()` method: a custom `Iterable`, an `Iterator` from a legacy library, a self-managed data structure, a sequence computed by a custom rule, or a source where you want to control work-splitting capability during parallel processing.

`java.util.stream.StreamSupport` is the utility class for building a Stream from a **`Spliterator`**—an object describing how to step through elements and, when possible, split the source into smaller parts.

Common example:

```java
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

Stream<String> result =
        StreamSupport.stream(iterable.spliterator(), false);
```

Here `iterable` is assumed to be declared and provide a `Spliterator<String>`. The `false` parameter specifies creating a **sequential stream**. To build good sources and avoid hard-to-detect bugs, you need to grasp three components:

- **Data source:** where elements come from, whether they reside in memory or are generated on demand?
- **`Spliterator<T>`:** how to step to the next element, estimate size, and (if appropriate) split the source?
- **`StreamSupport`:** connects the `Spliterator` into the Stream pipeline; `filter`, `map`, `flatMap`, and `collect` still work as usual.

**Important:** `StreamSupport` is not a magic library to automatically turn every `Iterator` into an efficient parallel structure. Quality, correctness, and source characteristics depend on the `Spliterator` you provide.

## 2. Important Overloads

`StreamSupport` has overloads for object streams and three primitive stream types:

```java
// Object stream:
static <T> Stream<T> stream(
        Spliterator<T> spliterator, boolean parallel);

static <T> Stream<T> stream(
        Supplier<? extends Spliterator<T>> supplier,
        int characteristics,
        boolean parallel);

// IntStream:
static IntStream intStream(
        Spliterator.OfInt spliterator, boolean parallel);

static IntStream intStream(
        Supplier<? extends Spliterator.OfInt> supplier,
        int characteristics,
        boolean parallel);

// LongStream:
static LongStream longStream(
        Spliterator.OfLong spliterator, boolean parallel);

static LongStream longStream(
        Supplier<? extends Spliterator.OfLong> supplier,
        int characteristics,
        boolean parallel);

// DoubleStream:
static DoubleStream doubleStream(
        Spliterator.OfDouble spliterator, boolean parallel);

static DoubleStream doubleStream(
        Supplier<? extends Spliterator.OfDouble> supplier,
        int characteristics,
        boolean parallel);
```

This is a presentation of Java 17 API signatures, not code to paste outside a class for standalone compilation.

**The `parallel` parameter**:

- `false`: creates a sequential Stream by default.
- `true`: creates a Stream in parallel mode. Whether parallelism is effective depends on how `Spliterator.trySplit()` partitions data, pipeline characteristics, source size, and workload.

**Two ways to provide the source**:

1. Pass an **existing `Spliterator`**.
2. Pass a **`Supplier<Spliterator>` and a set of `characteristics`** to defer obtaining the Spliterator until the terminal operation begins.

The supplier overload is especially useful when you want to **limit the time between source binding and traversal**, reducing the window of interference for a mutable source. However, it does not automatically guarantee thread safety or protect against all concurrent modifications.

## 3. What Is a `Spliterator`?

The name `Spliterator` combines *splittable iterator*: an object that can advance through elements and, if supported, split off part of the source for parallel processing.

Important methods:

| Method | Meaning |
| --- | --- |
| `tryAdvance(Consumer<? super T> action)` | If elements remain, applies action to **one** element and returns `true`; if exhausted, returns `false` |
| `forEachRemaining(Consumer<? super T> action)` | Traverses remaining elements |
| `trySplit()` | Attempts to split off part of the source into another Spliterator, or returns `null` if unsplittable |
| `estimateSize()` | Estimates remaining element count; may be `Long.MAX_VALUE` if unknown |
| `characteristics()` | Bit flags describing guaranteed properties of the source |
| `hasCharacteristics(flags)` | Checks one or more properties |
| `getExactSizeIfKnown()` | Returns exact size if `SIZED` is present, otherwise `-1` |
| `getComparator()` | Meaningful for sources with `SORTED`; if sorted by natural order, returns `null` |

A `Spliterator` does not have to know all elements upfront. For example, a `Spliterator.OfInt` can generate numbers 1,2,3... on demand rather than storing them in an `ArrayList`.

### Stepping through one element with `tryAdvance`

```java
Spliterator<String> spliterator =
        List.of("A", "B").spliterator();

boolean first = spliterator.tryAdvance(System.out::println);
boolean second = spliterator.tryAdvance(System.out::println);
boolean third = spliterator.tryAdvance(System.out::println);

System.out.println(first + "/" + second + "/" + third);
```

Output:

```text
A
B
true/true/false
```

This snippet is placed inside a method with `import java.util.*;`. Each `tryAdvance` call consumes at most one element. After two elements have been traversed, the third call returns `false` and does not invoke action.

**Warning:** do not call `tryAdvance` yourself on a Spliterator and then pass **that same Spliterator** into a Stream while expecting the entire original source. Its traversal position has already changed; the Stream will only see unconsumed elements.

## 4. The Simple Way: From `Iterable` to Stream

`Iterable<T>` has a `spliterator()` method. Thus, for a variable declared as `Iterable` (not necessarily a `Collection`), you can write:

```java
Iterable<String> names = List.of("Lan", "Minh", "An");

List<String> result = StreamSupport
        .stream(names.spliterator(), false)
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [LAN, MINH, AN]
```

In the example, the actual object is `List.of(...)`, so `spliterator()` has a traversal order matching the list.

Why not write `names.stream()`? Because **the `Iterable<T>` interface does not declare `stream()`**; `stream()` is a method provided by `Collection` and corresponding APIs. Even if the runtime object is a List, when the variable is declared as `Iterable`, the compiler only permits calling methods that exist on `Iterable`.

### Using with a custom `Iterable`

```java
Iterable<Integer> odds = () ->
        List.of(1, 3, 5, 7).iterator();

List<Integer> values = StreamSupport
        .stream(odds.spliterator(), false)
        .filter(n -> n > 3)
        .toList();

System.out.println(values); // [5, 7]
```

This is a concise approach when a class only provides `iterator()`.

**Note on ordering:** the default `Iterable.spliterator()` is based on `iterator()` and may not advertise the `ORDERED` characteristic even if the iterator usually returns elements in an observable order. If encounter order is an important contract, design/document the returned `Spliterator` to declare `ORDERED` properly, or convert to an ordered `List` structure when appropriate.

## 5. From `Iterator`: `Spliterators.spliteratorUnknownSize`

`Iterator<T>` **does not directly provide `spliterator()`**. The JDK has the utility class `java.util.Spliterators` to create a Spliterator from an iterator:

```java
Iterator<String> iterator = List.of("A", "B", "C").iterator();

Spliterator<String> spliterator =
        Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED);

List<String> values = StreamSupport.stream(spliterator, false)
        .map(String::toLowerCase)
        .toList();

System.out.println(values); // [a, b, c]
```

`spliteratorUnknownSize` means "size not known upfront." It **does not** have `SIZED` or `SUBSIZED` characteristics, even when you know the example Iterator will eventually traverse three elements. If the underlying data genuinely has a known size, use another appropriate factory API instead of trying to declare SIZED inaccurately.

### Iterators are typically single-use sources

After consuming `iterator` with a Stream, you cannot rewind to the beginning like a regular List. If multiple independent results are needed, supply a **fresh Iterator** each time or create a snapshot collection within allowed memory limits.

### Flags must be declared truthfully

`Spliterators.spliteratorUnknownSize(iterator, Spliterator.ORDERED)` states that elements are encountered in iterator order. If the source comes from an unordered structure, do not advertise `ORDERED` just to make output look deterministic.

Do not declare `DISTINCT` if the source can repeat values, `NONNULL` if elements can be null, or `IMMUTABLE` if the source can be modified during traversal. Flags are a **contract**, not harmless hints.

## 6. Lazy Mechanism: Creating a Stream Without Traversing the Whole Source Yet

`StreamSupport.stream(...)` returns a stream whose intermediate operations typically **do not execute** until a terminal operation is invoked.

```java
Iterable<Integer> source = List.of(2, 4, 6);

Stream<Integer> mapped = StreamSupport
        .stream(source.spliterator(), false)
        .map(n -> n * 10);

// At this point, it is not a computed List yet.
List<Integer> values = mapped.toList();

System.out.println(values); // [20, 40, 60]
```

`toList` is the terminal operation, causing the pipeline to be consumed. After calling it, do not reuse `mapped`.

**Important:** creating a Stream via the overload passing a Spliterator directly may access some source metadata early. Do not build code on an absolute assumption that no Spliterator method is queried before the terminal operation. What you should rely on is that elements are **traversed lazily** by the Stream pipeline, and the supplier overload has its own guarantee on when the supplier is called.

### `StreamSupport` does not manage resources automatically

If the Spliterator reads a file, socket, or database cursor, Stream is only the data traversal pipeline. You must define who owns the resource and **close the resource properly**. Do not assume `stream.toList()` or `stream.count()` automatically calls `close()` on the stream; in the JDK, Streams are usually not resources needing closing, whereas streams backed by I/O resources may require `try-with-resources` or `onClose` designed by the source.

For example, `Files.lines(path)` is a Stream with a file resource and must be closed with `try-with-resources`. If building a custom Spliterator over a resource-backed source, you must provide an appropriate resource-closing strategy; `StreamSupport` does not guess how to close a custom cursor.

## 7. Common `Spliterator` Characteristics

`characteristics()` returns a bitmask of flags. Each flag carries meaning for the Stream framework to plan processing:

| Characteristic | Primary Meaning | Practical Note |
| --- | --- | --- |
| `ORDERED` | Source has a defined encounter order | `forEachOrdered`/`toList` can preserve order |
| `DISTINCT` | Under `equals`, elements have no duplicates | Do not declare if source can have duplicates |
| `SORTED` | Elements have a defined sort order | Must obey `getComparator()` |
| `SIZED` | Remaining size is known accurately before traversal per contract | Do not declare for unstable/unknown-size sources |
| `SUBSIZED` | Every Spliterator produced by `trySplit` is also `SIZED` and `SUBSIZED` | Useful for parallel partitioning |
| `NONNULL` | No `null` reference elements | Only declare when genuinely guaranteed |
| `IMMUTABLE` | Element source cannot be structurally modified in a way affecting traversal | Does not mean every element object is deeply immutable |
| `CONCURRENT` | Source has a mechanism allowing concurrent updates per contract | Do not attach arbitrarily to ArrayList |
| `SORTED` + `ORDERED` | A SORTED Spliterator must be ORDERED | If naturally sorted, `getComparator()` returns null |

Characteristics are bit flags, combined with the OR operator `|`:

```java
int characteristics =
        Spliterator.ORDERED
        | Spliterator.SIZED
        | Spliterator.SUBSIZED;
```

**Do not declare `SIZED` just to make `count()` faster.** If you declare an inaccurate size, some optimizations can produce wrong results or expose hard-to-find bugs. Only declare properties you are certain hold across `tryAdvance`, `trySplit`, and traversal.

### `SORTED` requires an additional contract

If a Spliterator declares `SORTED`, it must obey the `getComparator()` rule. Return `null` only when natural ordering is the contract, or return the corresponding comparator. If the source **is not sorted**, do not declare `SORTED` just because you want Stream to sort it automatically; use `stream.sorted(...)` when needed.

## 8. The Overload Using `Supplier<Spliterator<T>>`

Here is the overload:

```java
Stream<T> stream(
        Supplier<? extends Spliterator<T>> supplier,
        int characteristics,
        boolean parallel);
```

Unlike passing an existing Spliterator, this overload **defers calling `supplier.get()` until the terminal operation begins**. Therefore it fits when the source is tied to mutable state and you want to minimize the interval between obtaining the Spliterator and using it.

Example:

```java
AtomicInteger created = new AtomicInteger();

int flags = Spliterator.ORDERED | Spliterator.SIZED
        | Spliterator.SUBSIZED | Spliterator.NONNULL;

Supplier<Spliterator<String>> supplier = () -> {
    created.incrementAndGet();
    return Spliterators.spliterator(
            new String[] {"A", "B", "C"},
            Spliterator.ORDERED | Spliterator.NONNULL);
};

Stream<String> stream =
        StreamSupport.stream(supplier, flags, false);

System.out.println(created.get());  // 0
System.out.println(stream.toList()); // [A, B, C]
System.out.println(created.get());  // 1
```

This is an illustrative snippet inside a method requiring imports `java.util.Spliterator`, `java.util.Spliterators`, `java.util.function.Supplier`, `java.util.concurrent.atomic.AtomicInteger`, `java.util.stream.Stream`, and `StreamSupport`. `Spliterators.spliterator(array, flags)` automatically provides `SIZED` and `SUBSIZED` for the array, along with the additional `ORDERED`/`NONNULL` flags, so `flags` is chosen consistently with the created source.

**Important rule:** the `characteristics` parameter when creating a Stream with a supplier **must match** `supplier.get().characteristics()` of the actual Spliterator. If you declare two conflicting flag sets, pipeline behavior may be unpredictable.

Do not use the supplier to sneak in a different kind of source or occasionally return a Spliterator with properties different from the declaration. In the example, the supplier creates a fresh independent array for a single traversal. The Stream is still **consumed only once**; to traverse again, create a new Stream from the supplier, do not invoke another terminal operation on the same Stream.

## 9. Why Can `Supplier` Reduce Source Interference Risk?

Suppose you have a mutable dataset:

```java
List<String> source = new ArrayList<>(List.of("A", "B"));
```

If you obtain the Spliterator early and then modify `source`, behavior depends on the specific *late-binding* and *fail-fast* mechanisms of the source Spliterator. For some collections, modifying during traversal can throw `ConcurrentModificationException`; for other sources, there may be a specific concurrent contract.

Using a supplier clarifies when the Spliterator is obtained:

```java
Stream<String> stream = StreamSupport.stream(
        source::spliterator,
        Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
        false);

// Only modify the source BEFORE the terminal operation starts.
source.add("C");
List<String> values = stream.toList();
```

This example assumes `source` is an `ArrayList`; verify the full actual Spliterator characteristics when using the supplier overload. Before the terminal operation starts, the supplier has not been called yet. However, **that does not make modifying source while the terminal operation is traversing safe**. Once the terminal operation starts, non-interference rules and the source's concurrent update capabilities must be obeyed.

If an immutable snapshot is needed, create a snapshot like `List.copyOf(source)` at a clear boundary before computation; the supplier does not automatically create a deep snapshot and does not solve all races.

## 10. Writing a Custom `Spliterator` for a Numeric Range

We can build a source without storing a list of all elements. For example, an integer range in **[startInclusive, endExclusive)**:

```text
[1, 6)  =>  1, 2, 3, 4, 5
[3, 3)  =>  empty source
```

A custom `Spliterator.OfInt` can traverse one number per `tryAdvance` call. For parallel processing, `trySplit` splits the remaining range into two non-overlapping ranges.

Mechanism:

```text
Initial source: [1, 9)
                   |
               trySplit()
               /        \
        [1, 5)           [5, 9)
  (new spliterator)  (current spliterator)
```

- The two branches **do not overlap**, and skip no values.
- `estimateSize()` is the number of untraversed elements.
- `tryAdvance` advances position after emitting exactly one value.
- `trySplit` can return `null` if the remaining range is too small to split.
- `SIZED`/`SUBSIZED` flags are only valid when estimates and splits always keep exact counts.

The complete Java 17 example in the next section implements all of these elements.

## 11. Complete, Compilable and Runnable Java 17 Example

Create file **`StreamSupportDemo.java`**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntConsumer;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class StreamSupportDemo {
    static final class IntRangeSpliterator implements Spliterator.OfInt {
        private int current;
        private final int fence;

        IntRangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("Invalid range");
            }
            this.current = startInclusive;
            this.fence = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (current >= fence) {
                return false;
            }
            action.accept(current++);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            int start = current;
            int half = (fence - start) / 2;
            if (half == 0) {
                return null;
            }
            int middle = start + half;
            current = middle; // Current Spliterator keeps the second half.
            return new IntRangeSpliterator(start, middle);
        }

        @Override
        public long estimateSize() {
            return (long) fence - current;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED
                    | IMMUTABLE | NONNULL | DISTINCT;
        }
    }

    public static void main(String[] args) {
        // 1. Iterable can be passed into StreamSupport.
        Iterable<String> colors = List.of("red", "green", "blue");
        List<String> upper = StreamSupport
                .stream(colors.spliterator(), false)
                .map(value -> value.toUpperCase(Locale.ROOT))
                .toList();
        System.out.println("Iterable: " + upper);

        // 2. Create Spliterator from an unknown-size Iterator.
        Iterator<String> iterator =
                List.of("Lan", "Minh", "An").iterator();
        Spliterator<String> unknown =
                Spliterators.spliteratorUnknownSize(
                        iterator, Spliterator.ORDERED);
        System.out.println("Unknown SIZED: "
                + unknown.hasCharacteristics(Spliterator.SIZED));

        List<String> names = StreamSupport.stream(unknown, false)
                .filter(name -> name.length() >= 3)
                .toList();
        System.out.println("Iterator: " + names);

        // 3. Supplier is not called when creating the Stream.
        AtomicInteger created = new AtomicInteger();
        int flags = Spliterator.ORDERED | Spliterator.SIZED
                | Spliterator.SUBSIZED | Spliterator.NONNULL;

        Supplier<Spliterator<String>> supplier = () -> {
            created.incrementAndGet();
            return Spliterators.spliterator(
                    new String[] {"A", "B", "C"},
                    Spliterator.ORDERED | Spliterator.NONNULL);
        };

        Stream<String> deferred =
                StreamSupport.stream(supplier, flags, false);
        System.out.println("Supplier before: " + created.get());
        System.out.println("Supplier values: " + deferred.toList());
        System.out.println("Supplier after: " + created.get());

        // 4. Custom Spliterator.OfInt, no need to create a backing List.
        List<Integer> firstFive = StreamSupport.intStream(
                new IntRangeSpliterator(1, 6), false)
                .boxed()
                .toList();
        System.out.println("Range: " + firstFive);

        // 5. Use Spliterator.OfInt when parallel processing is needed.
        int sum = StreamSupport.intStream(
                new IntRangeSpliterator(1, 1001), true)
                .sum();
        System.out.println("Parallel sum: " + sum);

        // 6. Observe range splitting accurately.
        Spliterator.OfInt right =
                new IntRangeSpliterator(1, 6);
        System.out.println("Size before split: "
                + right.estimateSize());
        Spliterator.OfInt left = right.trySplit();

        System.out.println("Split left: "
                + StreamSupport.intStream(left, false)
                        .boxed().toList());
        System.out.println("Split right: "
                + StreamSupport.intStream(right, false)
                        .boxed().toList());

        // 7. Empty source works as well.
        long count = StreamSupport.intStream(
                new IntRangeSpliterator(3, 3), false)
                .count();
        System.out.println("Empty count: " + count);

        // 8. LongStream version from Spliterator.OfLong.
        long longSum = StreamSupport.longStream(
                Spliterators.spliterator(
                        new long[] {5L, 10L},
                        Spliterator.ORDERED),
                false)
                .sum();
        System.out.println("Long sum: " + longSum);

        // 9. DoubleStream version from Spliterator.OfDouble.
        double avg = StreamSupport.doubleStream(
                Spliterators.spliterator(
                        new double[] {1.0, 2.0},
                        Spliterator.ORDERED),
                false)
                .average()
                .orElseThrow();
        System.out.println("Double average: " + avg);
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 StreamSupportDemo.java
java StreamSupportDemo
```

**Expected exact stdout:**

```text
Iterable: [RED, GREEN, BLUE]
Unknown SIZED: false
Iterator: [Lan, Minh]
Supplier before: 0
Supplier values: [A, B, C]
Supplier after: 1
Range: [1, 2, 3, 4, 5]
Parallel sum: 500500
Size before split: 5
Split left: [1, 2]
Split right: [3, 4, 5]
Empty count: 0
Long sum: 15
Double average: 1.5
```

### Analysis of Each Result

**`Iterable`:** the actual object is `List.of` which has an encounter order. `StreamSupport.stream(..., false)` traverses sequentially, `map` uppercases using `Locale.ROOT`, so the result keeps red, green, blue in order.

**`Iterator`:** the `spliteratorUnknownSize` factory does not advertise `SIZED`. `filter` keeps Lan (3 chars) and Minh (4 chars), dropping An (2 chars).

**`Supplier`:** `created` is 0 after just creating the Stream; when `deferred.toList()` starts, the supplier is called once to return the actual Spliterator, so the counter becomes 1. The three-element array is traversed in exact order A, B, C.

**`IntRangeSpliterator`:** range [1,6) contains 5 numbers. `StreamSupport.intStream(..., false)` pulls elements from `tryAdvance`. When computing parallel sum for [1,1001), all numbers 1 to 1000 are summed; the sum is `1000 × 1001 / 2 = 500500`. Addition does not change the result despite splitting across multiple branches.

**`trySplit`:** for [1,6), length 5, the first half has length 2 as [1,3), while the current Spliterator keeps [3,6). Thus left contains 1,2 and right contains 3,4,5, with no duplicates and no lost elements.

**Empty source:** [3,3) contains no elements so `count()` returns 0. With an accurate `SIZED` flag, Stream can optimize `count()` using the known size without necessarily calling `tryAdvance` for each element.

**Primitive:** `StreamSupport.longStream` and `doubleStream` work with `OfLong`/`OfDouble` respectively. Data [5,10] sums to 15; average of [1.0,2.0] is 1.5.

### Note on range length and overflow

In the demo's `trySplit`, `fence - start` uses `int`. Since the tested ranges have small sizes, no overflow occurs. If designing a Spliterator for the full `int` domain (e.g., from `Integer.MIN_VALUE` to `Integer.MAX_VALUE`), `int` subtraction can overflow. A production Spliterator needs to compute distance using `long`:

```java
long remaining = (long) fence - current;
long half = remaining / 2;
long middle = (long) current + half;
```

This is an **illustrative snippet for safe calculation**, requiring checking conversion back to `int` per domain conditions and specific contracts. Do not copy the demo's small `trySplit` verbatim to advertise support for all extreme integer ranges.

## 12. `tryAdvance`: Rules to Keep When Implementing Yourself

A custom Spliterator must ensure that when `tryAdvance(action)` returns `true`:

1. It applies `action` to one current element.
2. It updates state so as **not to re-emit the same element unexpectedly**.
3. It does not skip other elements if the source is defined to traverse all elements.
4. When data is exhausted, it returns `false` and does not invoke action.

A wrong example:

```java
@Override
public boolean tryAdvance(IntConsumer action) {
    action.accept(current); // Forgot to increment current.
    return true;             // No stopping condition.
}
```

This is an **anti-pattern**, not a valid standalone program. If passed into `StreamSupport.intStream` and `toList()` is called without limit, the Stream can repeat a single value forever and exhaust resources. Before using a custom `Spliterator` with a terminal operation that collects everything, check the termination boundary.

### Should side effects happen in the action or in the source?

`tryAdvance` is responsible for **supplying data**. You should not silently write files/send emails inside `tryAdvance` when the source's purpose is only to read elements. Because Stream may traverse partially or skip unnecessary steps depending on the pipeline and terminal operation, you should not rely on `tryAdvance` to execute mandatory once-per-element side effects for all source data.

If the Spliterator actually reads from a device or file, reading is I/O with technical side effects. Clarify the contract for opening/closing resources, I/O errors, ownership, and replayability; do not assume the source is pure just because it is called through the Stream API.

## 13. `trySplit` and Proper Parallel Processing

`trySplit()` returns a new Spliterator covering **a portion of untraversed elements**, while the current Spliterator keeps the remainder. For an ordered source, the returned part is usually a **prefix** of the remaining elements.

Example from [1,9):

```text
Initially: 1 2 3 4 5 6 7 8
                  |
              trySplit()
               /      \
Returned:   1 2 3 4  | Kept: 5 6 7 8
```

Important invariants:

- **No duplicate elements.**
- **No skipped elements.**
- For `SIZED`/`SUBSIZED` sources, branch sizes match the pre-split size.
- For `ORDERED` sources, traversal order of combined branches must be compatible with source order.
- Each child Spliterator manages its own traversal range/address; avoid sharing an unsynchronized mutable variable across branches.
- When too few elements remain or splitting is not possible, `trySplit` can return `null`.

### Parallel does not mean the order in which lambdas execute

```java
List<String> labels = StreamSupport.intStream(
        new IntRangeSpliterator(1, 6), true)
        .mapToObj(n -> "N" + n)
        .toList();

System.out.println(labels); // [N1, N2, N3, N4, N5]
```

The source advertises `ORDERED` and `toList()` preserves encounter order, so the **result** order is N1..N5. However, the transformation `n -> "N" + n` may run on multiple threads not in linear 1..5 order. Do not update a shared `ArrayList` or write business logs based on mapper execution order.

### When does parallel not pay off?

A source with only a few elements, `trySplit()` always returning null, sequential I/O reading, or a trivial mapper can make splitting/synchronization overhead larger than the benefit. Do not set `parallel=true` just because `trySplit()` exists; measure actual time with a representative workload.

## 14. `SIZED`, `SUBSIZED`, and Exact Size

When a Spliterator advertises `SIZED`, `estimateSize()` has a contract corresponding to the size of the untraversed portion. With `SUBSIZED`, child Spliterators produced by `trySplit` must also carry appropriate size characteristics.

A test:

```java
Spliterator.OfInt s = new IntRangeSpliterator(1, 6);

System.out.println(s.hasCharacteristics(Spliterator.SIZED)); // true
System.out.println(s.getExactSizeIfKnown());                // 5
```

Using `SIZED` accurately can help Stream optimize operations like `count` or result allocation. However, do not assume every terminal operation will be forced to call `tryAdvance`: optimizing based on metadata is valid when conditions are met.

**If you provide an inaccurate size**, such as reporting 100 elements while only emitting 3, some optimizations can be severely affected and results become wrong or erroneous. Spliterator characteristics are a promise by the implementer and must be unit-tested.

### Unknown size

If the source is an input iterator or cursor, `estimateSize()` can return `Long.MAX_VALUE` when the element count is unknown, and not advertise `SIZED`. That is completely valid; creating a Stream from an unknown-size source does not require building an entire List first.

## 15. Using `Spliterators` to Reduce Boilerplate

You do not always need to implement `Spliterator` yourself. `java.util.Spliterators` already provides factories:

```java
// From an unknown-size iterator:
Spliterator<String> unknown =
        Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED);

// From an object array:
Spliterator<String> array =
        Spliterators.spliterator(
                new String[] {"A", "B"},
                Spliterator.ORDERED);

// From an int array:
Spliterator.OfInt ints =
        Spliterators.spliterator(
                new int[] {1, 2, 3},
                Spliterator.ORDERED);
```

These snippets assume `iterator` exists and require importing `Spliterator`/`Spliterators`. Arrays have a known size upfront, so the factory can provide `SIZED`/`SUBSIZED`; unknown-size iterators do not.

When the input is already a `Collection`, in most cases **`collection.stream()` or `collection.parallelStream()` is the clearer way**. Manually using StreamSupport is only worthwhile when the source lacks a convenient Stream API or you need to control Spliterator behavior.

## 16. Ordering Contracts and Unordered Data

`forEachOrdered` and `Stream.toList()` can preserve order if the source **has an encounter order**. If the Spliterator does not advertise `ORDERED`, you should not assume element order will always match a test run.

Example:

```java
Spliterator<String> source =
        Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED);

StreamSupport.stream(source, false)
        .forEachOrdered(System.out::println);
```

This is an illustrative snippet with `iterator` providing an order committed to by the source. If the iterator comes from an unordered structure, attaching `ORDERED` may not reflect the source contract. When business ordering is needed, you can build a `List`/call `sorted` or choose an ordered source.

Do not confuse **the order of elements in the result** with **the execution order of mappers** in a parallel pipeline.

## 17. Immutability and Source Interference

The Stream API recommends that non-concurrent sources not be modified while a pipeline is active. If using an `ArrayList` being modified by another thread, the Spliterator may detect the change and throw `ConcurrentModificationException` or exhibit effects you should not rely on.

**Do not fix the problem by declaring a fake `CONCURRENT`.** The `CONCURRENT` flag is for sources that genuinely support concurrent updates per contract, such as certain concurrent collections, not a way to enable a non-existent feature.

For a collection-independent generator like `IntRangeSpliterator`, `IMMUTABLE` can fit because the sequence is already fixed by the bounds. However, for a mutable list, do not declare `IMMUTABLE` just because you hope callers will not modify it; base it on the source's contract.

If a fixed snapshot is needed for multi-step processing, you can use `List.copyOf(source)` or an appropriate immutable model at the boundary. This is a decision at the data layer, not performed automatically by `StreamSupport`.

## 18. Checked Exceptions from I/O Sources

`Spliterator.tryAdvance` accepts a `Consumer` and **does not declare checked `IOException`** in its signature. Therefore, a Spliterator directly reading a file/network usually must catch checked exceptions itself or design an adapter to translate errors per contract.

Example handling approach:

```java
// Inside a tryAdvance method of a custom Spliterator:
try {
    String line = reader.readLine();
    if (line == null) {
        return false;
    }
    action.accept(line);
    return true;
} catch (IOException ex) {
    throw new UncheckedIOException(ex);
}
```

This is an **illustrative snippet**, requiring `reader`/`action` and imports `IOException`/`UncheckedIOException`, not a standalone program. Wrapping preserves the original cause in `getCause()` yet **does not automatically close `reader`**. The source owner must still close it via an appropriate mechanism.

When a terminal operation throws `UncheckedIOException`, the caller needs an error-handling policy and may have to roll back/compensate for side effects executed earlier. Creating a Stream with StreamSupport does not guarantee atomicity or retry.

## 19. Primitive Spliterators and Avoiding Boxing

`StreamSupport.intStream(...)`, `longStream(...)`, and `doubleStream(...)` accept specialized Spliterators:

| Source Type | Resulting Stream | Action Type |
| --- | --- | --- |
| `Spliterator.OfInt` | `IntStream` | `IntConsumer` |
| `Spliterator.OfLong` | `LongStream` | `LongConsumer` |
| `Spliterator.OfDouble` | `DoubleStream` | `DoubleConsumer` |
| `Spliterator<T>` | `Stream<T>` | `Consumer<T>` |

This avoids having to box an `int` into `Integer` when the source inherently only generates numbers. Example:

```java
long sum = StreamSupport.intStream(
        new IntRangeSpliterator(1, 1001), false)
        .asLongStream()
        .sum();

System.out.println(sum); // 500500
```

With small data like the example, performance is not the main reason; when processing millions of numbers, primitive streams can reduce overhead. However, evaluate overflow, precision, and correctness before optimizing.

### Why is there no `StreamSupport.floatStream`?

The specialized Java Stream API has `IntStream`, `LongStream`, and `DoubleStream`, **with no separate `FloatStream`** in JDK 17. When processing `float`, you can use `DoubleStream` with necessary conversions or `Stream<Float>` depending on the contract.

## 20. Combining with `map`, `filter`, `flatMap`, and Collectors

Once you have a Stream, it works like any other Stream:

```java
List<String> result = StreamSupport
        .stream(iterable.spliterator(), false)
        .filter(s -> !s.isBlank())
        .map(s -> s.trim().toUpperCase(Locale.ROOT))
        .distinct()
        .sorted()
        .toList();
```

`iterable` is assumed to be an `Iterable<String>` with valid strings; if `null` is present, calling `isBlank()` will throw `NullPointerException`, so you must validate or filter nulls per business rules.

Example from a nested structure source:

```java
Iterable<List<Integer>> groups = List.of(
        List.of(1, 2), List.of(), List.of(3));

List<Integer> flat = StreamSupport
        .stream(groups.spliterator(), false)
        .flatMap(List::stream)
        .toList();

System.out.println(flat); // [1, 2, 3]
```

**StreamSupport only changes how the source is created**, not the contract of `map`, `flatMap`, `sorted`, `collect`, or `toList`.

## 21. Common Mistakes When Creating Streams with `StreamSupport`

| Mistake | Why It Is Dangerous/Wrong | How to Fix |
| --- | --- | --- |
| Calling `iterable.stream()` when the variable is typed as `Iterable` | `Iterable` does not declare `stream()` | Use `StreamSupport.stream(iterable.spliterator(), false)` |
| Passing `Iterator` directly to `stream` | Overload requires `Spliterator`/`Supplier` | Use `Spliterators.spliteratorUnknownSize` |
| Thinking `parallel=true` will auto-split the source optimally | Depends on `trySplit` and workload | Implement splitting properly then benchmark |
| `tryAdvance` always returns true | Can create a non-terminating source | Update position and stopping condition |
| `trySplit` returns overlapping regions | Elements may be processed twice | Verify non-overlapping/no-omission invariants |
| Advertising `SIZED` when size is unknown | Wrong metadata, optimizations may fail | Do not attach `SIZED` |
| Advertising `SORTED` when unsorted | Violates contract | Only declare if source is truly sorted |
| Attaching `CONCURRENT` to `ArrayList` | Does not make ArrayList thread-safe | Follow true source or create a snapshot |
| Not defining `ORDERED` yet expecting exact encounter order | Ordering contract unclear | Use appropriate source/flags |
| Reusing a terminated Stream | Streams are consumed only once | Create a new Stream from the source |
| Reusing an exhausted Iterator | Does not rewind to start of data | Create a new Iterator |
| Creating an I/O stream and forgetting to close the source | Leaks file/socket/cursor | `try-with-resources` or clear close hook |
| Giving a mapper mandatory side effects | Lazy/short-circuit/parallel hard to control | Separate computation from I/O |
| Declaring supplier characteristics different from actual Spliterator | Violates supplier overload contract | Sync flags with source |
| Overusing StreamSupport for a `List` that already has `stream()` | Adds unnecessary code | Use collection's stream API |
| Using `int` to compute very large range sizes | Overflows when subtracting or dividing | Use `long` and check bounds |
| Thinking `count()` always calls `tryAdvance` | With SIZED sources it may optimize | Test values, do not rely on side effects |
| Overusing `parallel()` on I/O | Races, rate limits, unstable order | Coordinate I/O separately, limit concurrency |

## 22. Practice Exercises

1. Given `Iterable<String> data = List.of("a","b","c")`. Use `StreamSupport.stream(data.spliterator(), false)` to get an uppercase `List<String>`; identify why `data.stream()` cannot be called directly.
2. Create an `Iterator<Integer>` from `List.of(1,2,3)` and wrap it with `Spliterators.spliteratorUnknownSize(iterator, Spliterator.ORDERED)`. Compute the sum with `mapToInt(Integer::intValue).sum()`.
3. Check `hasCharacteristics(Spliterator.SIZED)` on a Spliterator from `spliteratorUnknownSize`. Explain why the result is false even when you know the element count is three.
4. Modify `IntRangeSpliterator` in the example to generate range [5,10). Predict the `List` is [5,6,7,8,9].
5. With `new IntRangeSpliterator(1,6)`, call `trySplit` and traverse both Spliterators separately. Why are the results [1,2] and [3,4,5]?
6. Write a test comparing total elements before split with the sum of both branches after split. Ensure no duplicates and no omissions.
7. Build a Spliterator that only returns `null` in `trySplit`. Does it still create a sequential Stream? Can a parallel stream optimize work splitting?
8. Create a source without `SIZED`, try `count()`, and observe the difference between `estimateSize` and actual size.
9. Use the supplier overload and `AtomicInteger` to count supplier invocations. Verify 0 before terminal and 1 when `toList()` runs.
10. Try attaching `SORTED` to an unsorted sequence. Explain **why this code must not be run as a valid solution** and why Stream may optimize based on the wrong flag.
11. Create `Spliterator.OfLong` from a `long[]` array using `Spliterators.spliterator`, then `StreamSupport.longStream(..., false).sum()`.
12. Create `Spliterator.OfDouble` from a `double[]` array and compute `average().orElseThrow()`, checking the empty-array case requiring `OptionalDouble` handling.
13. Write a StreamSupport example from `Iterable<List<Integer>>` followed by `flatMap(List::stream)`, demonstrating that how the source is created does not alter `flatMap` semantics.
14. Describe a scenario requiring manual I/O management when reading a file via a custom Spliterator and how to attach resource-closing responsibility to the consuming API.
15. For an Ordered source, compare `forEach` and `forEachOrdered` when `parallel=true`. Why should action order not be inferred from a single run's output?
16. Propose unit tests for a custom Spliterator covering: empty input, single element, multiple elements, repeated splits, size, characteristic flags, and no omissions.
17. Write a `trySplit` version computing remaining range with `long` to avoid overflow when start/fence are near `int` limits.

## 23. Checklist Before Using in a Project

- Is a custom source really needed, or are `collection.stream()`/`Stream.of()` sufficient?
- Is the source an `Iterable`, `Iterator`, collection, array, generator, or I/O cursor?
- Are you choosing the right `StreamSupport.stream` or `intStream`/`longStream`/`doubleStream` overload?
- For unknown-size sources, have you used `spliteratorUnknownSize` and avoided declaring `SIZED` inaccurately?
- Does `tryAdvance` emit exactly one element and have a proper stopping point?
- Does `trySplit` partition accurately, with no duplicates/omissions, and preserve order if `ORDERED` is declared?
- Do `estimateSize` and `SIZED`/`SUBSIZED` match reality?
- Are `ORDERED`/`DISTINCT`/`SORTED`/`NONNULL`/`IMMUTABLE`/`CONCURRENT` flags honest?
- If using Supplier, do the passed `characteristics` match the actual Spliterator?
- Are you distinguishing **creating a stream** from **consuming via a terminal operation**?
- Are you reusing an already consumed Iterator/Stream?
- For mutable or concurrent sources, have non-interference and thread-safety policies been defined?
- For I/O sources, who opens/closes the file/socket/cursor and handles exceptions?
- If setting `parallel=true`, have you benchmarked and tested parallel traversal instead of assuming it is faster?
- Are there unit tests for output, count, order, splits, size, and empty cases?

**Conclusion:** `StreamSupport` is the bridge from `Spliterator` to `Stream` (or `IntStream`, `LongStream`, `DoubleStream`). Use `Iterable.spliterator()`, `Spliterators.spliteratorUnknownSize`, or a custom Spliterator to accurately define how to traverse and split a source. Put the correctness of `tryAdvance`, `trySplit`, `estimateSize`, and characteristics ahead of enabling `parallel`; the downstream Stream pipeline still follows the lazy mechanism, terminal operations, and side-effect/resource-management rules of the Java Stream API.