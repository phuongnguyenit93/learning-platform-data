# Creating Streams with StreamSupport Using a Spliterator Supplier

The Java Stream API lets you build pipelines from `Collection`, arrays, and familiar sources. When data comes from an application-defined source, `Spliterator` describes how elements are traversed and split for parallel execution, while `StreamSupport` turns that source into a `Stream`. A special overload accepts **`Supplier<? extends Spliterator<T>>`** instead of an already-created `Spliterator`. This option **defers obtaining the Spliterator until the terminal operation begins**, thereby shrinking the window during which the source could be interfered with before traversal.

This article belongs to the **Spliterators and Custom Sources** chapter in the **JAVA_STREAM_API** module. It focuses on the Supplier-based overload, the `characteristics` parameter, instantiation timing, custom source correctness, and splittability. We also connect it to lazy pipelines (`filter`, `map`, `reduce`, `collect`), parallel execution, I/O resources, and avoiding state and performance bugs.

## 1. Scenario: Why Not Always Pass a Spliterator Directly?

Suppose we want to create a Stream from data whose traversal start time is only known later: a list might have items appended **before** the terminal operation runs, or a custom source should only be initialized when processing is genuinely needed.

`StreamSupport` has two overloads for `Stream<T>`:

```java
public static <T> Stream<T> stream(
    Spliterator<T> spliterator,
    boolean parallel
);

public static <T> Stream<T> stream(
    Supplier<? extends Spliterator<T>> supplier,
    int characteristics,
    boolean parallel
);
```

Key differences:

| Criterion | Passing `Spliterator` | Passing `Supplier` |
| --- | --- | --- |
| Spliterator object | Supplied when creating the Stream | Obtained via `supplier.get()` when the terminal operation starts |
| Source creation timing | Caller creates/selects Spliterator upfront | Caller describes how to create/obtain the Spliterator later |
| `characteristics` flags | Read from the supplied Spliterator | Caller **must declare upfront** and ensure exact match with actual Spliterator |
| Suitable when | Source is ready, Spliterator creation is cheap and safe | Wanting to defer Spliterator creation or narrow the interference window |
| Automatically makes Stream reusable? | No | **No** |
| Automatically closes I/O sources? | No | **No** |

For the Supplier overload, the Java specification states that `Supplier.get()` is called **at most once** and **only after the pipeline's terminal operation commences**. "At most once" differs from "always exactly once" in every usage: for instance, if a Stream is created and discarded without a terminal operation, the Supplier never needs to be invoked.

### A timeline diagram

```text
Create Stream
    |
    | StreamSupport.stream(supplier, characteristics, false)
    v
Build lazy pipeline
    |
    | filter(...).map(...)
    | supplier.get() not yet requested
    v
Invoke terminal operation
    |
    | supplier.get()  →  Spliterator
    |                         |
    |                         v
    |                     tryAdvance(...)
    |                     trySplit(...) if appropriate
    v
Receive result from count()/toList()/reduce()/collect()
```

The diagram only illustrates possible steps: a terminal operation may optimize using size metadata, so never assume a specific number of `tryAdvance` calls; for unsplittable sources, `trySplit` may not be called or may return `null`.

## 2. Signature of the Supplier Overload and Its Three Parameters

```java
StreamSupport.stream(supplier, characteristics, parallel)
```

| Parameter | Type | Role |
| --- | --- | --- |
| `supplier` | `Supplier<? extends Spliterator<T>>` | Returns a Spliterator serving as the Stream's source |
| `characteristics` | `int` | Characteristic flags that **must match the Spliterator returned by the Supplier** |
| `parallel` | `boolean` | Requests whether the initial Stream is sequential (`false`) or parallel (`true`) |

Flags come from `java.util.Spliterator` and are combined with bitwise OR `|`:

```java
import java.util.Spliterator;

int flags = Spliterator.ORDERED
          | Spliterator.SIZED
          | Spliterator.SUBSIZED;
```

**Core contract:** The `characteristics` value passed to `StreamSupport.stream` **must equal** `supplier.get().characteristics()`. If they do not match, behavior when the terminal operation starts is undefined under the API specification. Never treat this parameter as "a few hint flags" or "add more flags for more speed."

The Supplier must provide a valid, non-`null` Spliterator. Creating the Spliterator must also stay consistent with the data boundaries the application intends to traverse.

### Naming carefully to avoid confusion

In this snippet:

```java
Supplier<Spliterator<String>> source = names::spliterator;
Stream<String> stream = StreamSupport.stream(source, flags, false);
```

`source` is not a Stream to consume. It is a **traversal source factory/supplier**. `stream` remains single-use even though `source.get()` could create new Spliterators in independent calls outside that pipeline.

## 3. Foundational Example: Supplier Lazily Creating a Spliterator from ArrayList

For a standard `ArrayList`, the Spliterator has characteristics `ORDERED`, `SIZED`, and `SUBSIZED`. Java 17+ example:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class SupplierBindingDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Bình"));

        AtomicInteger suppliersCalled = new AtomicInteger();

        Supplier<Spliterator<String>> source = () -> {
            suppliersCalled.incrementAndGet();
            return names.spliterator();
        };

        int flags = Spliterator.ORDERED
                  | Spliterator.SIZED
                  | Spliterator.SUBSIZED;

        Stream<String> stream = StreamSupport.stream(source, flags, false)
            .filter(name -> !name.isBlank())
            .map(String::toUpperCase);

        System.out.println(suppliersCalled.get()); // 0

        // Modify the list BEFORE the terminal operation starts.
        names.add("Chi");

        List<String> result = stream.toList();

        System.out.println(suppliersCalled.get()); // 1
        System.out.println(result);                 // [AN, BÌNH, CHI]
    }
}
```

What this example demonstrates:

1. While building the pipeline, `supplier.get()` has not been called yet.
2. After adding `"Chi"` **before the terminal operation**, the Supplier returns `names.spliterator()` reflecting the current list.
3. `toList()` consumes the pipeline once, producing results in `ArrayList`'s encounter order.
4. `supplier.get()` is called once during this consumption.

Do not conclude that an application may modify the list **while the terminal operation is running**. `ArrayList` is not a concurrent source; structurally modifying the list mid-traversal can cause `ConcurrentModificationException` or undefined results.

**Note on late binding:** Several standard library Spliterators, such as `ArrayList`'s, already have their own *late-binding* mechanism. The Supplier overload provides deferral at the `StreamSupport` level and is especially useful when **custom source Spliterator instantiation** needs to be deferred; not every list needs a Supplier to behave properly.

## 4. Spliterator Characteristics: Source Commitments, Not Decorative Options

Every Spliterator declares flags via `characteristics()`. `StreamSupport` needs to know these flags before invoking the Supplier.

| Flag | Meaning | What to Verify |
| --- | --- | --- |
| `ORDERED` | Source has a meaningful encounter order | Source and `trySplit` must preserve order when splitting |
| `DISTINCT` | Source elements are unique per equality rules | Do not set if data may contain duplicates |
| `SORTED` | Elements are sorted in a defined order | `getComparator()` must reflect comparator; return `null` for natural ordering |
| `SIZED` | `estimateSize()` reports exact remaining element count per contract | Do not set for unknown-size sources |
| `NONNULL` | Source emits no `null` elements | Do not set when `null` may be emitted |
| `IMMUTABLE` | Source cannot be structurally modified during traversal | Do not set just because a reference variable is `final` |
| `CONCURRENT` | Source supports concurrent modification per contract | Do not set for ordinary `ArrayList` |
| `SUBSIZED` | Spliterator and all split parts also satisfy `SIZED` and `SUBSIZED` | Set only when exact sizes can be guaranteed across all branches |

Several key rules:

- `ORDERED` concerns **the source's encounter order**, not that every Map resulting from `collect` is ordered.
- `SORTED` is a stronger commitment than `ORDERED`; if `SORTED` is declared, the source's comparison rule must be expressed properly via `getComparator()`.
- `SIZED` enables size-based computation optimizations; misdeclaring it can cause terminal operations like `count()` to return unexpected results.
- `IMMUTABLE` refers to structural mutability of **the source**, not deep immutability of element objects inside.
- `CONCURRENT` describes **traversal source** characteristics, not permission for `map`/`filter` lambdas to mutate shared variables.
- Flags must hold on **the supplied source Spliterator**, not be inferred from `map` or `filter` steps written afterward.

### Self-checking a source during development

```java
import java.util.ArrayList;
import java.util.Spliterator;

Spliterator<String> spliterator =
    new ArrayList<>(java.util.List.of("A", "B")).spliterator();

int actual = spliterator.characteristics();

System.out.println(spliterator.hasCharacteristics(
    Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED
)); // true for ArrayList's Spliterator
```

`hasCharacteristics(...)` only verifies that **the requested flags are present**, not that two bitmasks are identical. When checking the `StreamSupport` Supplier contract, check **full equality** `actual == declaredFlags`, not merely `hasCharacteristics`.

## 5. When Is a Supplier More Useful Than a Pre-Created Spliterator?

Three common situations arise.

### 5.1. The source must be determined when consumption begins

For example, a list receives more items before running a report:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2));

Supplier<Spliterator<Integer>> source = numbers::spliterator;

Stream<Integer> pending = StreamSupport.stream(
    source,
    Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
    false
);

numbers.add(3); // Before terminal operation.

int sum = pending.mapToInt(Integer::intValue).sum();

System.out.println(sum); // 6
```

Do not modify the source while `sum()` is executing.

### 5.2. Avoiding expensive Spliterator setup when no terminal operation runs

For a custom source, creating a Spliterator might involve setting up cursors, mapping metadata, or preparing traversal tools. Deferring with a Supplier means this setup **does not run merely because code constructed a pipeline and left it unused**.

```java
Supplier<Spliterator<String>> source = () -> {
    System.out.println("Preparing traversal source");
    return List.of("x", "y").spliterator();
};

Stream<String> unused = StreamSupport.stream(
    source,
    Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
    false
);

// No terminal operation called: supplier may never be invoked.
unused.close();
```

This example uses a small list purely to illustrate source creation timing. Never rely on `close()` to force a Supplier to run; closing a pipeline does not require calling `supplier.get()`.

### 5.3. Narrowing the window for source interference

If a custom Spliterator *eagerly binds* to source state upon creation, passing it too early creates a wide gap between Stream creation and consumption during which underlying data might change. Passing a Supplier instantiates the Spliterator later, closer to execution time.

Yet a Supplier **is not a synchronization lock** and not an automatic snapshot. If multiple threads concurrently mutate a mutable source, you must use concurrent structures, snapshots, locks, or an explicit consistency policy as required.

## 6. Unknown-Size Sources: Using Spliterators.spliteratorUnknownSize

A source does not always know its element count. An `Iterator` can be adapted into a Spliterator:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<String> events = List.of("START", "READ", "END");

Supplier<Spliterator<String>> source = () -> {
    Iterator<String> iterator = events.iterator();

    return Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED | Spliterator.NONNULL
    );
};

Stream<String> stream = StreamSupport.stream(
    source,
    Spliterator.ORDERED | Spliterator.NONNULL,
    false
);

System.out.println(stream.toList()); // [START, READ, END]
```

Here:

- `events.iterator()` is created **inside the Supplier** when the terminal operation requests the source.
- `spliteratorUnknownSize` works with iterators whose element count is unknown in advance.
- Do not declare `SIZED` or `SUBSIZED` because the source uses an unknown-size mechanism.
- `NONNULL` is valid only because `List.of(...)` in this example contains no `null`.

`Spliterators.spliteratorUnknownSize` has its own `trySplit` mechanism, but splitting an Iterator typically incurs different costs than random-access sources and does not guarantee parallel speedups.

**Never share a pre-created Iterator across multiple independent Suppliers/Streams** if each run is meant to traverse from the beginning. An Iterator holds positional state; a single-use source must be treated properly as single-use.

## 7. Writing a Splittable Custom Spliterator: Integer Range Example

When a custom source is genuinely needed, you can implement the core methods yourself:

- `tryAdvance(action)`: pulls at most one next element.
- `trySplit()`: splits off part of the source (or returns `null` if unsplittable).
- `estimateSize()`: estimates or supplies exact size.
- `characteristics()`: declares source guarantees.
- `getComparator()`: must obey the contract if `SORTED` is present.

The example below builds a `Spliterator.OfInt` representing `[startInclusive, endExclusive)`, restricting inputs to non-negative integers. It avoids pre-allocating an array of numbers and supports splitting the range into a **prefix** and **suffix** for parallel processing.

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;
import java.util.Spliterator;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntConsumer;
import java.util.function.Supplier;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

public class SupplierIntStreamDemo {
    static final int FLAGS =
          Spliterator.ORDERED
        | Spliterator.DISTINCT
        | Spliterator.SORTED
        | Spliterator.SIZED
        | Spliterator.NONNULL
        | Spliterator.IMMUTABLE
        | Spliterator.SUBSIZED;

    static final class IntRangeSpliterator implements Spliterator.OfInt {
        private int cursor;
        private final int endExclusive;

        IntRangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive < 0 || endExclusive < startInclusive) {
                throw new IllegalArgumentException("Invalid non-negative range");
            }
            this.cursor = startInclusive;
            this.endExclusive = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);

            if (cursor >= endExclusive) {
                return false;
            }

            int value = cursor++;
            action.accept(value);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            int lo = cursor;
            int mid = lo + ((endExclusive - lo) >>> 1);

            if (mid <= lo) {
                return null;
            }

            // Return prefix [lo, mid); this retains suffix [mid, end).
            cursor = mid;
            return new IntRangeSpliterator(lo, mid);
        }

        @Override
        public long estimateSize() {
            return (long) endExclusive - cursor;
        }

        @Override
        public int characteristics() {
            return FLAGS;
        }

        @Override
        public Comparator<? super Integer> getComparator() {
            // SORTED by natural order.
            return null;
        }
    }

    public static void main(String[] args) {
        AtomicInteger end = new AtomicInteger(8);
        AtomicInteger supplierCalls = new AtomicInteger();

        Supplier<Spliterator.OfInt> source = () -> {
            supplierCalls.incrementAndGet();
            return new IntRangeSpliterator(0, end.get());
        };

        IntStream numbers = StreamSupport.intStream(
            source,
            FLAGS,
            true
        );

        System.out.println(supplierCalls.get()); // 0

        // Update bound before terminal operation begins.
        end.set(10);

        int[] squares = numbers.map(n -> n * n).toArray();

        System.out.println(Arrays.toString(squares));
        // [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]

        System.out.println(supplierCalls.get()); // 1
    }
}
```

### 7.1. Why does the example satisfy the declared characteristics?

- `ORDERED`: source emits in ascending numeric order; `trySplit` returns a **prefix**, keeping the suffix on the current instance.
- `DISTINCT`: no number repeats in the range.
- `SORTED`: ascending in natural ordering; `getComparator()` returns `null` to indicate natural order.
- `SIZED`: `estimateSize()` equals the exact remaining element count.
- `SUBSIZED`: both halves after splitting retain exact sizes and identical flags.
- `NONNULL`: primitive `int` Stream has no `null` elements.
- `IMMUTABLE`: the numeric range inside each Spliterator is fixed; `end` is read only when the Supplier creates the Spliterator, not used to alter the range during traversal.

`FLAGS` passed to `StreamSupport.intStream` is **identical to** `IntRangeSpliterator.characteristics()`. When splitting, each child Spliterator also returns the same flag set.

### 7.2. Common range-splitting bugs

A buggy `trySplit` can cause:

- **Lost elements** if `[lo, mid)` or `[mid, hi)` leaves a gap.
- **Duplicate elements** if two branches traverse overlapping regions.
- **Broken encounter order** if returning a suffix when promising a prefix.
- **Broken `SIZED`** if declared size mismatches remaining elements.
- **Infinite loop or recursion** if splitting fails to shrink the range.

Returning `null` when 0 or 1 elements remain is an appropriate stopping rule. Size must decrement accurately after `tryAdvance` and partition accurately after `trySplit`.

### 7.3. Why not always write a custom Spliterator?

If the input is a list or array and you just need a simple numeric range, `IntStream.range(start, end)` is shorter and easier to maintain than a custom implementation. The purpose here is **learning the source Spliterator contract** and how to supply it via a Supplier, not replacing standard sources.

## 8. Primitive Stream Supplier Overloads

`StreamSupport` also supports `IntStream`, `LongStream`, and `DoubleStream` with specialized Spliterators:

```java
StreamSupport.intStream(
    Supplier<? extends Spliterator.OfInt> supplier,
    int characteristics,
    boolean parallel
);

StreamSupport.longStream(
    Supplier<? extends Spliterator.OfLong> supplier,
    int characteristics,
    boolean parallel
);

StreamSupport.doubleStream(
    Supplier<? extends Spliterator.OfDouble> supplier,
    int characteristics,
    boolean parallel
);
```

This avoids unnecessary boxing when the source is already primitive. Example of a Supplier emitting an `int` range via a standard-library Spliterator:

```java
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.Supplier;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

int flags = Spliterator.ORDERED | Spliterator.SIZED
          | Spliterator.SUBSIZED | Spliterator.IMMUTABLE
          | Spliterator.NONNULL;

Supplier<Spliterator.OfInt> numbers = () ->
    Spliterators.spliterator(
        new int[] {10, 20, 30},
        Spliterator.ORDERED | Spliterator.IMMUTABLE | Spliterator.NONNULL
    );

// Spliterators.spliterator(int[], flags) also adds SIZED and SUBSIZED.
int total = StreamSupport.intStream(numbers, flags, false).sum();

System.out.println(total); // 60
```

In this example, `Spliterators.spliterator(int[], characteristics)` automatically adds `SIZED` and `SUBSIZED` for the array source. Hence the outer `flags` must include both flags, even though the flags passed when constructing the array Spliterator only specify additional characteristics.

**Note:** If the source type does not guarantee `IMMUTABLE` (e.g., the array could be mutated by another thread during traversal), do not set that flag merely because this sample does not edit the array. For standard-library factories, verify the exact characteristics of the returned Spliterator.

## 9. Common Misconceptions About Suppliers and Laziness

### 9.1. A Supplier does not make a Stream reusable

```java
Supplier<Spliterator<String>> factory =
    () -> List.of("A", "B").spliterator();

int flags = Spliterator.ORDERED | Spliterator.SIZED
          | Spliterator.SUBSIZED;

Stream<String> stream = StreamSupport.stream(factory, flags, false);

System.out.println(stream.count()); // 2
// stream.toList(); // Invalid: Stream has already been consumed.
```

A Supplier can instead be used to **create a fresh Stream** each time you need to re-run:

```java
java.util.function.Supplier<Stream<String>> freshStream = () ->
    StreamSupport.stream(factory, flags, false);

System.out.println(freshStream.get().count()); // 2
System.out.println(freshStream.get().toList()); // [A, B]
```

This is only safe when the Spliterator Supplier can create a fresh source or the underlying source allows re-traversal. For network connections, one-shot Iterators, or I/O transactions, you cannot assume data can be re-read.

### 9.2. "Late-binding Supplier" does not mean snapshot

If a Supplier reads a mutable list, changes **before** the terminal operation can be reflected in the lazily obtained source. Yet if another thread mutates the list **during traversal**, interference risks remain. To obtain a stable snapshot, you can create a copy **inside the Supplier**, if memory cost and business rules allow:

```java
List<String> mutable = new ArrayList<>(List.of("A", "B"));

Supplier<Spliterator<String>> snapshotSource = () ->
    List.copyOf(mutable).spliterator();
```

With this snapshot source, mutations after the copy is created do not alter the element set of the obtained Spliterator. However, if data is updated concurrently **during the copy itself** without synchronization, copying a mutable source is still unsafe; a proper snapshot needs synchronization or an appropriate storage structure.

**Watch characteristics:** When replacing `ArrayList.spliterator()` with `List.copyOf(...).spliterator()`, do not assume the exact same flag set from the old Spliterator. Ensure the `characteristics` passed to `StreamSupport` match the new instance.

### 9.3. A Supplier only defers *obtaining the Spliterator*, not necessarily every resource

If a file or connection was already opened externally and the Supplier merely wraps an open `reader`, that resource was still opened early. To defer opening the resource too, the open logic must sit at the appropriate point **and** include proper closing and failure-cleanup handling if initialization fails.

Never call a pipeline "resource-free" just because it uses a Supplier.

## 10. Resource Management When a Custom Spliterator Reads I/O

`StreamSupport.stream(supplier, flags, parallel)` **does not automatically turn an I/O source into a self-closing resource after the terminal operation**. If a Spliterator traverses a file, socket, connection, or closeable cursor, your API must define ownership and closing time.

For regular text files, prefer the standard source:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines = Files.lines(Path.of("input.txt"))) {
    long count = lines
        .filter(s -> !s.isBlank())
        .count();

    System.out.println(count);
}
```

If you must use a custom Spliterator, attach `onClose` on the returned Stream to release resources; **the caller still must close the Stream**, ideally via `try-with-resources`. A sound design must handle all cases:

1. Terminal operation processes all elements.
2. Terminal operation short-circuits (`findFirst`, `anyMatch`, `limit`).
3. Supplier or `tryAdvance` throws an exception.
4. Stream is closed when the Supplier **has not yet been called**.
5. Failures occur while opening the source or running close handlers.

Basic `onClose` example with a non-I/O source:

```java
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

AtomicInteger closeCount = new AtomicInteger();

try (Stream<String> items = StreamSupport.stream(
        () -> List.of("x", "y").spliterator(),
        Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
        false
    ).onClose(closeCount::incrementAndGet)) {
    System.out.println(items.findFirst().orElse("none")); // x
}

System.out.println(closeCount.get()); // 1
```

The handler here merely counts close calls for illustration; it **does not represent** file-closing mechanics. With real resources, attach appropriate close handlers and prevent leaks if the Supplier fails during initialization. `onClose` does not run automatically after `sum()`, `count()`, or `toList()` without `close()`.

## 11. Parallel Processing: A Supplier Does Not Replace `trySplit`

The `parallel = true` parameter requests creating a parallel Stream; it does not guarantee the source splits well or runs faster.

For effective partitioning, `trySplit` needs to:

- Return a Spliterator holding **a portion of untraversed elements**, disjoint from the remainder.
- Shrink toward smaller subproblems on each split; avoid overly tiny or skewed splits.
- Preserve declared characteristics, especially `ORDERED`, `SIZED`, and `SUBSIZED` if present.
- Never share a mutable cursor across branches without proper safety mechanisms.

An unsplittable Spliterator can implement:

```java
@Override
public Spliterator<T> trySplit() {
    return null;
}
```

Such a source can still create a Stream with `parallel = true`, but its ability to exploit multiple parallel tasks will be limited.

### When does `CONCURRENT` make sense?

Only declare `Spliterator.CONCURRENT` when **the source** supports concurrent modifications with valid data semantics. This flag does not make `ArrayList` thread-safe, nor does it allow `reduce`/`collect` accumulators to mutate shared variables without synchronization.

When using `collect` on a custom source, collectors must still uphold identity, associativity, supplier/accumulator/combiner, and shared-state contracts. Using a Spliterator Supplier does not alter those contracts.

### Working alongside Stream Gatherers

Stream Gatherers suit stateful intermediate transformations on supporting JDKs, whereas a Spliterator is responsible for **the element-emitting source** and source partitioning. There is no need to implement a Gatherer just to build a Stream from a Spliterator. Choose the simplest construct satisfying source and pipeline requirements.

## 12. Verifying Correctness of a Custom Source

When developing a custom Spliterator, verify properties of **element set**, **order**, **size**, and **source splitting** before evaluating performance.

### 12.1. Comparing sequential and parallel

With `SupplierIntStreamDemo`, the same numeric range must yield the exact same sequence of elements if `ORDERED` is preserved:

```java
int[] sequential = StreamSupport.intStream(
    () -> new SupplierIntStreamDemo.IntRangeSpliterator(0, 100),
    SupplierIntStreamDemo.FLAGS,
    false
).toArray();

int[] parallel = StreamSupport.intStream(
    () -> new SupplierIntStreamDemo.IntRangeSpliterator(0, 100),
    SupplierIntStreamDemo.FLAGS,
    true
).toArray();

System.out.println(java.util.Arrays.equals(sequential, parallel)); // true
System.out.println(sequential.length); // 100
```

Test similarly with lengths 0, 1, 2, 3, 10, 1000 and odd split points to catch `trySplit` bugs.

### 12.2. Verifying exact flags

```java
Spliterator.OfInt actual =
    new SupplierIntStreamDemo.IntRangeSpliterator(0, 10);

if (actual.characteristics() != SupplierIntStreamDemo.FLAGS) {
    throw new IllegalStateException("Declared characteristics differ");
}
```

Do not test by calling `supplier.get()` an extra time assuming that call belongs to "the Stream"; extra external calls can instantiate redundant sources or trigger side effects. With a custom factory, construct an independent verification instance in tests.

### 12.3. Verifying Supplier invocation

```java
AtomicInteger calls = new AtomicInteger();

Supplier<Spliterator<String>> factory = () -> {
    calls.incrementAndGet();
    return List.of("A", "B").spliterator();
};

Stream<String> stream = StreamSupport.stream(
    factory,
    Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
    false
);

System.out.println(calls.get()); // 0
System.out.println(stream.toList()); // [A, B]
System.out.println(calls.get()); // 1
```

Observe only the Supplier invocation count; **do not use side effects inside `tryAdvance` to prove every terminal operation visited every element**, as some terminal operations can rely on known size or pipeline optimizations.

## 13. Performance and Design Trade-Offs

| Option | Benefit | Trade-Off |
| --- | --- | --- |
| Passing Spliterator directly | Concise, no need to know flags upfront at call site | Spliterator already instantiated before Stream starts |
| Passing Supplier | Late source acquisition/creation, narrows interference window before terminal | Must supply exact flags and design source factory carefully |
| Compliant `SIZED`/`SUBSIZED` Spliterator | Aids split planning and terminal optimizations | Wrong flags lead to unreliable results |
| Balanced range-splitting Spliterator | Easy work distribution across branches | More complex source code needing thorough edge-case tests |
| Unknown-size Iterator Spliterator | Easy Stream wrapping from custom iterators | Hard to predict size; splitting can add overhead |
| Materialize into `List` then call `stream()` | Simple, leverages standard source | Needs memory for full dataset and eager loading |
| Lazy I/O reading with Stream | Reduces memory for sequential processing | Must manage close, traversal errors, and cursor lifecycle |

Using a Supplier provides no automatic performance gain. When you already have a `List`, calling `list.stream()` is usually simpler and better suited. Only reach for `StreamSupport` when you need a custom source or explicit control over `Spliterator` behavior.

For large workloads, measure latency, actual elements traversed, split depth, memory, and contention using representative benchmarks like JMH. Never assume parallel execution is always faster: splitting/merging overhead and source properties can outweigh any gains.

## 14. Common Mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Setting `characteristics = 0` out of uncertainty while Supplier returns non-zero flags | Violates flag-equality contract | Supply bitmask matching `spliterator.characteristics()` |
| Declaring `SIZED` for an unknown-size Iterator | Invalid optimizations, unreliable results | Omit `SIZED` when exact count is not guaranteed |
| Declaring `IMMUTABLE` on a mutable source modified concurrently | Misrepresents source stability | Remove flag or design a true snapshot/immutable source |
| Declaring `SORTED` while `getComparator` violates contract | Violates `Spliterator` contract | Return valid comparator or `null` for natural ordering |
| Assuming `Supplier.get()` runs immediately at `StreamSupport.stream(...)` | Initialization logic runs at wrong time | Wait for terminal operation; verify with Supplier counter |
| Assuming Supplier makes a Stream reusable | `IllegalStateException` on second consumption | Create a fresh Stream for each pass |
| Sharing one Iterator/cursor across two independent Streams | Source exhausted on first pass | Create a new cursor when supported or document one-shot source |
| Splitting range in `trySplit` with overlap or gaps | Wrong output, especially in parallel | Verify splits are disjoint and lossless |
| Using `parallel = true` when `trySplit()` always returns `null` expecting speedup | Parallelism is crippled | Design effective splitting or run sequentially |
| Mutating `ArrayList` while Stream is running | Concurrent modification or undefined behavior | Finish updates before terminal operation or pick a suitable source |
| Assuming I/O sources auto-close after `count()`/`findFirst()` | Resource leak | Use `try-with-resources` and `onClose` with clear ownership |
| Creating a Supplier that opens a file without error cleanup | Leak during setup or traversal | Design complete lifecycle and exception handling |
| Thinking `Spliterator.CONCURRENT` allows any lambda to mutate shared variables | Race conditions across pipeline stages | Separate source contract from collector state contract |
| Using `tryAdvance` to count how many times terminal operation runs | Fails under `SIZED` optimizations | Assert outputs directly, never rely on traversal side effects |

## 15. Practice Exercises

### Exercise 1: Determining when the Supplier runs

Create a `Supplier<Spliterator<String>>` that increments an `AtomicInteger`, pass it to `StreamSupport.stream(supplier, flags, false)`, then chain `filter` and `map`. Predict the counter value before and after `toList()`. Why does the Supplier not need to run while merely constructing the pipeline?

### Exercise 2: Comparing the two overloads

Write two Streams from the same `ArrayList`: one receiving `list.spliterator()` and one receiving `list::spliterator`. Mutate the list **before** the terminal operation; explain the limits of each design. Avoid claiming every direct Spliterator always freezes data at creation time.

### Exercise 3: Declaring accurate flags

Build a Supplier using `Spliterators.spliteratorUnknownSize(iterator, ORDERED | NONNULL)`. Determine the exact `characteristics` to pass to `StreamSupport.stream`. Why must `SIZED` not be set?

### Exercise 4: Building a splittable numeric range

Using `IntRangeSpliterator`, test ranges `[0, 0)`, `[0, 1)`, `[0, 2)`, `[0, 7)`, and `[5, 20)`. Compare sequential and parallel results; verify no elements are lost or duplicated and final size matches expected count.

### Exercise 5: Catching invalid `SORTED` declaration

Create a Spliterator emitting values in order `3, 1, 2` yet declaring `SORTED`. Explain why this violates the contract even if the Stream appends `.sorted()` downstream. State how to fix either the flags or the source logic.

### Exercise 6: Source changing before and during terminal operation

Create an `ArrayList`-backed Supplier. Add an element before `toList()` and observe the result. Then analyze **on paper** the risks if another thread mutates the list while the pipeline is running; do not write an unstable race-condition test.

### Exercise 7: Designing an I/O source

Describe an API returning `Stream<String>` from a file-reading Spliterator: who opens, who closes, where `onClose` is attached, what happens if `supplier.get()` throws, and why `findFirst()` does not replace `close()`. Compare with `Files.lines(path)`.

### Exercise 8: Choosing source and processing approach

Given 1 million integers already in an `int[]`, choose among `Arrays.stream(array)`, `StreamSupport.intStream(arraySpliterator, false)`, and a custom Spliterator + Supplier. When does the more complex choice add value? State what must be benchmarked before enabling parallel mode.

## 16. Self-Check Knowledge Questions

- At what moment does `StreamSupport.stream(Supplier, characteristics, parallel)` differ from the direct Spliterator overload?
- At most how many times may `Supplier.get()` be called for a single Stream?
- Why must the outer `characteristics` exactly equal `supplier.get().characteristics()`?
- How do `ORDERED` and `SORTED` differ? When may `getComparator()` return `null`?
- What requirements do `SIZED` and `SUBSIZED` impose on `estimateSize()` and `trySplit()`?
- Why does a Supplier not automatically turn a mutable source into a safe snapshot?
- How must `trySplit()` partition elements to avoid duplicates, losses, or broken encounter order?
- When should you choose `Spliterator.OfInt` and `StreamSupport.intStream`?
- Why must you never reuse the same Stream after calling `sum()` or `collect()`?
- Does using a Supplier change the responsibility for closing I/O sources?
- Why is `parallel = true` insufficient on its own to guarantee speedups?
- How can you verify when the Supplier is called without relying on `tryAdvance` side effects?

**Remember:** The `StreamSupport.stream(supplier, characteristics, parallel)` overload defers **obtaining the Spliterator** until the terminal operation begins, yet it does **not** make a Stream reusable, does not create a snapshot automatically, and does not auto-close I/O. Most importantly, declare `characteristics` **identical to** the actual Spliterator's characteristics and ensure `tryAdvance`, `trySplit`, size, ordering, ownership, and source state uphold the contract. When standard sources already suffice, prefer simpler Stream creation APIs over writing a custom Spliterator.
