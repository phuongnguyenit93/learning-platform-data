# Creating Streams with StreamSupport Using a Direct Spliterator

The Java Stream API usually starts from built-in sources like `list.stream()`, `Arrays.stream(...)`, or `IntStream.range(...)`. However, sometimes data resides in a custom structure, an `Iterator`, a value generator, or a source that requires controlling how work is partitioned. In those situations, `Spliterator` combined with `StreamSupport` lets you **feed a custom data source into a Stream pipeline** without first converting all data into a `List`.

This lesson belongs to the **Spliterators and Custom Sources** chapter of the `JAVA_STREAM_API` module. We will learn how to create a `Stream<T>` with `StreamSupport.stream(spliterator, parallel)`, build an `IntStream` with `StreamSupport.intStream(...)`, understand the responsibilities of `tryAdvance`, `trySplit`, `estimateSize`, and `characteristics`, distinguish *early binding* from *late binding*, and examine state, resource, and performance limits under parallel execution. The examples connect to lazy pipelines using `filter`, `map`, `reduce`, and `collect`.

The core APIs in this article have existed since **Java 8**. Each section's snippet can run standalone with its listed `import` statements, or reuse classes defined in preceding sections.

## 1. What Role Does Spliterator Play?

`Spliterator<T>` is an object that traverses and optionally splits a source of elements of type `T`. Its name comes from *splittable iterator*. Unlike `Iterator`, which only offers standard sequential traversal, `Spliterator` provides:

- `tryAdvance(action)`: attempts to pass **one** next element to `action`.
- `forEachRemaining(action)`: passes remaining elements to `action`.
- `trySplit()`: attempts to split remaining elements into two **non-overlapping** parts.
- `estimateSize()`: estimates the remaining element count.
- `characteristics()`: declares source properties such as `ORDERED`, `SIZED`, `SORTED`, or `IMMUTABLE`.

`StreamSupport` takes a `Spliterator` as a source, while downstream Stream operations handle element processing:

```text
Custom source
      │
      ▼
Spliterator<T>
      │
      ├── tryAdvance()     : emit elements
      ├── trySplit()       : split range
      ├── estimateSize()
      └── characteristics()
      │
      ▼
StreamSupport.stream(spliterator, false)
      │
      ├── filter(...)
      ├── map(...)
      ├── distinct(...)
      └── collect(...)     ← terminal operation
      │
      ▼
Result
```

**Key point:** `Spliterator` defines **the source and traversal**, rather than performing `map` or `collect` for the Stream. `StreamSupport` does not copy all elements into memory just to construct a Stream.

You do not always need to write a custom `Spliterator`. Before doing so, check whether the source already has `stream()`, `spliterator()`, or a standard factory that meets your needs.

## 2. Direct Usage of StreamSupport.stream

Basic signature:

```java
public static <T> Stream<T> stream(
        Spliterator<T> spliterator,
        boolean parallel
)
```

- `spliterator`: source object, must be non-null.
- `parallel = false`: creates a sequential pipeline.
- `parallel = true`: creates a pipeline in parallel mode; **does not promise faster execution**.
- Returns a `Stream<T>` to which intermediate operations and a terminal operation can be attached.

Example using a list's `Spliterator`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<String> words = Arrays.asList(" Java ", "Stream", "", " API ");

Spliterator<String> source = words.spliterator();
Stream<String> pipeline = StreamSupport.stream(source, false);

List<String> cleaned = pipeline
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());

System.out.println(cleaned); // [Java, Stream, API]
```

We did not need to convert `words` into another structure. `StreamSupport` simply wires the source's `Spliterator` into the pipeline.

Still, for an ordinary `List`, `words.stream()` is shorter and should be preferred. Writing `StreamSupport.stream(words.spliterator(), false)` in this example illustrates the connection mechanism. `StreamSupport`'s practical value shines when a source **does not provide a Stream on its own**.

### A Stream is consumed only once

`pipeline.collect(...)` consumed the Stream in the example. Do not call `pipeline.count()` on the same instance after a terminal operation has run. To re-traverse the list source, create a new Stream from a fresh `Spliterator`:

```java
long count = StreamSupport.stream(words.spliterator(), false)
        .filter(s -> !s.trim().isEmpty())
        .count();

System.out.println(count); // 3
```

An already-consumed `Spliterator` must also never be reused as a fresh source. Creating a new Stream **does not** reset traversal state on a one-shot source such as an Iterator or Reader.

## 3. Bridging an Iterator via Spliterators.spliteratorUnknownSize

A legacy source exposing only an `Iterator<T>` can also be turned into a Stream:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

Iterator<String> iterator = Arrays.asList(
        "backend", "frontend", "qa"
).iterator();

Spliterator<String> source = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED
);

List<String> upper = StreamSupport.stream(source, false)
        .map(String::toUpperCase)
        .collect(Collectors.toList());

System.out.println(upper); // [BACKEND, FRONTEND, QA]
```

Meaning:

1. `Spliterators.spliteratorUnknownSize(iterator, characteristics)` wraps an Iterator into a Spliterator without requiring known size upfront.
2. `Spliterator.ORDERED` is only accurate if the Iterator truly has an encounter order to preserve.
3. `StreamSupport.stream(source, false)` creates a sequential Stream from that source.
4. `map` and `collect` consume only the elements actually supplied by the Iterator.

Do not declare `SIZED` or `SUBSIZED` when exact size is unknown. The `spliteratorUnknownSize` factory clears those two flags even if the caller passes them by mistake.

**Note:** this is not a magic trick to "upgrade an Iterator into an ideal parallel source." The created Spliterator may support batch splitting, but effectiveness depends on the Iterator's nature. If the Iterator reads sequentially from a socket or holds external resources, ownership and lifecycle must be managed separately.

## 4. Building a Simple Source with AbstractSpliterator

When no Collection or Iterator is available, you can supply element-generation logic directly. `Spliterators.AbstractSpliterator<T>` reduces boilerplate when you mainly need to define `tryAdvance`.

Example emitting five consecutive event codes:

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.Consumer;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

Spliterator<String> generated =
        new Spliterators.AbstractSpliterator<String>(
                5L,
                Spliterator.ORDERED
        ) {
            private int next = 0;

            @Override
            public boolean tryAdvance(Consumer<? super String> action) {
                Objects.requireNonNull(action, "action");
                if (next >= 5) {
                    return false;
                }

                action.accept("event-" + next++);
                return true;
            }
        };

System.out.println(
        StreamSupport.stream(generated, false)
                .collect(Collectors.toList())
);
// [event-0, event-1, event-2, event-3, event-4]
```

In this example:

- `tryAdvance` emits **at most one** element per `true` return.
- When no elements remain, it returns `false`.
- `ORDERED` holds because codes are generated in order from 0 to 4.
- The initial `estimateSize` of 5 is a bound/estimate; the example does not declare `SIZED`, so the Stream need not treat it as an exact count at all times.

`AbstractSpliterator` includes a default `trySplit` algorithm based on batching elements. That splitting strategy is not necessarily optimal for every source. For expensive, ordered, or I/O-stateful sources, evaluate whether splitting is truly safe and worthwhile.

**Never declare `IMMUTABLE`, `CONCURRENT`, or `SIZED` just to run faster.** Every characteristic is a contract about source and behavior, not a decorative option.

## 5. Defining a Custom Range-Splitting Spliterator

To see partitioning clearly, let's build a `Spliterator.OfInt` emitting integers from `startInclusive` to `endExclusive - 1`. This mirrors `IntStream.range(...)`, with the intent here being to learn how to implement a custom source.

### 5.1. A complete Spliterator.OfInt class

```java
import java.util.Comparator;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;

final class IntRangeSpliterator implements Spliterator.OfInt {
    private int cursor;
    private final int fence;

    IntRangeSpliterator(int startInclusive, int endExclusive) {
        if (startInclusive < 0 || endExclusive < startInclusive) {
            throw new IllegalArgumentException("Invalid range");
        }
        this.cursor = startInclusive;
        this.fence = endExclusive;
    }

    @Override
    public boolean tryAdvance(IntConsumer action) {
        Objects.requireNonNull(action, "action");

        if (cursor >= fence) {
            return false;
        }

        action.accept(cursor++);
        return true;
    }

    @Override
    public Spliterator.OfInt trySplit() {
        int remaining = fence - cursor;
        if (remaining < 2) {
            return null;
        }

        int midpoint = cursor + remaining / 2;

        Spliterator.OfInt prefix =
                new IntRangeSpliterator(cursor, midpoint);

        cursor = midpoint;
        return prefix;
    }

    @Override
    public long estimateSize() {
        return (long) fence - cursor;
    }

    @Override
    public int characteristics() {
        return Spliterator.ORDERED
                | Spliterator.SIZED
                | Spliterator.SUBSIZED
                | Spliterator.SORTED
                | Spliterator.DISTINCT
                | Spliterator.NONNULL
                | Spliterator.IMMUTABLE;
    }

    @Override
    public Comparator<? super Integer> getComparator() {
        return null; // SORTED in ascending natural order
    }
}
```

To keep the example clear, the constructor accepts a **non-negative** range with `endExclusive >= startInclusive`. When using integer sources across arbitrary domains, be careful with midpoint calculation and overflow; you cannot safely subtract arbitrary `int` values to find the distance between any two `int`s.

### 5.2. Using StreamSupport.intStream

```java
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

IntStream numbers = StreamSupport.intStream(
        new IntRangeSpliterator(10, 15),
        false
);

int[] values = numbers.toArray();
System.out.println(Arrays.toString(values));
// [10, 11, 12, 13, 14]
```

This is the result of an `IntStream`, avoiding boxing into `Stream<Integer>`. After calling `toArray()`, the Stream is consumed.

When changing `parallel` to `true`:

```java
int evenSum = StreamSupport.intStream(
        new IntRangeSpliterator(0, 20),
        true
).filter(n -> n % 2 == 0)
 .sum();

System.out.println(evenSum); // 90
```

`IntRangeSpliterator` splits `[0, 20)` into disjoint sub-ranges. The integer sum here stays within bounds, yielding the same result sequentially or in parallel.

### 5.3. Why must trySplit return the right portion of the source?

Suppose the initial state is `[0, 8)`:

```text
Before splitting:
  this = [0, 8)

After trySplit():
  returned result = [0, 4)   ← preceding part
  this            = [4, 8)   ← remaining part

Splitting this again:
  returned result = [4, 6)
  this            = [6, 8)
```

After splitting, **the total element count must not lose or duplicate items**. `trySplit()` must never return a Spliterator containing elements still retained by the original Spliterator. For an `ORDERED` source, the returned part should be a **prefix** of the remaining elements.

When no useful split is possible (0 or 1 element left in the example), return `null`. Never assume the framework will call `trySplit` once or split into a fixed number of branches; partitioning depth varies with the execution algorithm.

## 6. Explaining Each Method of IntRangeSpliterator

| Method | Guarantee in Example | Common Mistake |
| --- | --- | --- |
| `tryAdvance` | Emits one `int` if data remains; returns `false` when exhausted | Returning `true` without emitting an element, or emitting two |
| `trySplit` | Returns a disjoint prefix range; narrows `this`'s range | Both branches emitting the same element or skipping a segment |
| `estimateSize` | Exact remaining element count | Failing to decrease after `tryAdvance` or `trySplit` |
| `characteristics` | Accurately describes ordering and value domain | Falsely declaring `SIZED`, `SORTED` |
| `getComparator` | Returns `null` for `SORTED` in natural order | Declaring `SORTED` without providing a valid comparator |

For reference-type Spliterators, `tryAdvance` accepts `Consumer<? super T>`. For `OfInt`, the primitive argument is passed to `IntConsumer` to avoid boxing. `OfLong` and `OfDouble` use `LongConsumer` and `DoubleConsumer` respectively.

**Never directly share a single Spliterator whose cursor mutates across two threads.** Parallelism works because the framework creates *separate ranges* via `trySplit`; it does not mean methods on a single Spliterator instance are thread-safe if callers invoke them concurrently.

## 7. Characteristics: Declaring the Truth About the Data Source

`Spliterator.characteristics()` returns a combined bitmask of characteristics. Common flags:

| Characteristic | Meaning | When Allowed to Declare |
| --- | --- | --- |
| `ORDERED` | Source has a defined encounter order | Ordered lists, ordered numeric sequences |
| `DISTINCT` | No two elements are equal per `equals` | Duplicate-free sequences, compliant Sets |
| `SORTED` | Elements are sorted by natural order or comparator | Only when source order is genuinely guaranteed |
| `SIZED` | `estimateSize()` is exact remaining count absent unauthorized interference | Arrays, fixed ranges of known size |
| `SUBSIZED` | All Spliterators from `trySplit` also guarantee `SIZED` and `SUBSIZED` | Exact-size range splitting |
| `NONNULL` | Source emits no null elements | Primitive Spliterators, verified non-null sources |
| `IMMUTABLE` | Data source structure is not modified during traversal | Formula-generated ranges, immutable data |
| `CONCURRENT` | Source permits concurrent modification per contract | Suitably designed concurrent data structures |

**Two boundaries to remember:**

1. `SIZED` does not mean every downstream Stream still knows its exact size like the source. `filter` changes the count flowing through the pipeline, so you cannot assume the filtered result equals the source's `estimateSize`.
2. Spliterator's `CONCURRENT` **differs from** `Collector.Characteristics.CONCURRENT`. The first describes **a source tolerant of concurrent modifications**; the second describes **how multiple threads accumulate into a single result container**.

A custom Spliterator for a mutable List must not arbitrarily declare `IMMUTABLE` if that List can be modified during traversal. Conversely, updating a Spliterator's `cursor` during traversal is **traversal state**, which does not violate the **data source immutability** described by `IMMUTABLE`.

### SORTED requires a valid getComparator

With `Spliterator.SORTED`, `getComparator()` must supply the right comparator when a custom comparator is used, or return `null` for natural ordering. In `IntRangeSpliterator`, the numbers ascend naturally, so `getComparator()` returns `null`.

If a Spliterator does not truly know the order, **never declare `SORTED`**. Misdeclaring it can cause a pipeline to omit necessary sort steps or apply invalid optimizations, leading to wrong results.

## 8. Creating Primitive Streams Without Boxing

`StreamSupport` has dedicated factories:

```java
StreamSupport.intStream(Spliterator.OfInt spliterator, boolean parallel);
StreamSupport.longStream(Spliterator.OfLong spliterator, boolean parallel);
StreamSupport.doubleStream(Spliterator.OfDouble spliterator, boolean parallel);
```

These three lines illustrate **conceptual signatures**, not standalone Java calls. Example using a built-in factory to create a `LongStream` from an array:

```java
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.LongStream;
import java.util.stream.StreamSupport;

long[] amounts = {10L, 20L, 30L};

Spliterator.OfLong source = Spliterators.spliterator(
        amounts,
        Spliterator.ORDERED
);

long total = StreamSupport.longStream(source, false).sum();

System.out.println(total); // 60
```

Because the source is a primitive array, there is no need to allocate a `Long` per element. With an ordinary `Stream<Integer>`, `mapToInt(Integer::intValue)` involves unboxing; `OfInt` is more natural when the source natively produces `int`.

If you simply have a primitive array, `Arrays.stream(amounts)` remains cleaner and more direct. `StreamSupport` exists to integrate specialized sources, not to replace every standard Stream factory.

## 9. Direct Spliterator vs. Supplier: Early Binding and Late Binding

`StreamSupport` also provides an overload accepting a Supplier:

```java
public static <T> Stream<T> stream(
        Supplier<? extends Spliterator<T>> supplier,
        int characteristics,
        boolean parallel
)
```

Key difference:

- `stream(spliterator, parallel)` takes **an already-created Spliterator** when constructing the Stream.
- `stream(supplier, characteristics, parallel)` defers **obtaining the Spliterator from the Supplier** until the terminal operation begins; the factory is invoked at most once per the API contract.

That enables *late binding*, useful when capturing a snapshot at consumption time.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<String> source = new ArrayList<>(
        Arrays.asList("A", "B")
);

Supplier<Spliterator<String>> supplier =
        () -> new ArrayList<>(source).spliterator();

Stream<String> deferred = StreamSupport.stream(
        supplier,
        Spliterator.ORDERED
                | Spliterator.SIZED
                | Spliterator.SUBSIZED,
        false
);

// Mutate source before terminal operation begins.
source.add("C");

List<String> snapshot = deferred.collect(Collectors.toList());
System.out.println(snapshot); // [A, B, C]
```

In this example, the Supplier creates **a copy of the list when the terminal operation starts**. This clarifies the source boundary: edits to `source` before the terminal operation are visible in the copy, while changes after the copy is taken are excluded from that snapshot.

**Never declare a characteristics set different from the Spliterator the Supplier actually returns.** The flags passed to the Supplier overload must match the flags of the returned Spliterator at creation time; mismatching them violates the contract.

### When to choose which overload?

| Situation | Choice |
| --- | --- |
| Already have a Spliterator and want single-pass consumption | `stream(spliterator, false)` |
| Want to create the Spliterator right when terminal operation begins | `stream(supplier, flags, false)` |
| Need a primitive Stream from a custom source | `intStream` / `longStream` / `doubleStream` |
| Source already provides `stream()` | Use built-in `stream()` if sufficient |
| Have a legacy Iterator | `spliteratorUnknownSize` then `StreamSupport.stream` |

**Caution with concurrent mutations:** deferring Spliterator creation does not make an `ArrayList` modified concurrently by another thread thread-safe. If multiple threads share a source, you need synchronization, immutable snapshots, or an appropriate concurrent structure.

## 10. State and Correctness Traps

### 10.1. tryAdvance returns true without emitting an element

```java
// WRONG: reports an element exists without calling action.accept(...).
@Override
public boolean tryAdvance(Consumer<? super String> action) {
    if (hasNext()) {
        moveCursor();
        return true;
    }
    return false;
}
```

`tryAdvance` must invoke the action with **exactly one** element whenever returning `true`. When returning `false`, it must not silently emit an element. Violating this contract can cause missing data or invalid pipeline behavior.

### 10.2. Two trySplit branches overlapping data

```text
WRONG:
  prefix = [0, 5)
  this   = [3, 8)

  Numbers 3 and 4 will be processed twice.

RIGHT:
  prefix = [0, 4)
  this   = [4, 8)
```

Element count after splitting must be conserved. With `SIZED` and `SUBSIZED`, declared sizes must remain exact after splits and traversals.

### 10.3. Declaring SIZED for a source with unknown termination

If the source is a continuous log stream, socket, or iterator with an undetermined element count, do not declare `SIZED` based on a guess. `estimateSize()` can return `Long.MAX_VALUE` when no useful estimate exists, though that does not make the source finite.

A terminal operation on an infinite source like `collect(toList())` or `sorted()` may never finish and exhaust memory. For suitable sources, `limit(n)` can stop the pipeline early, though it does not automatically close resources.

### 10.4. Using the same Spliterator for two Streams

```java
Spliterator<String> oneShot = words.spliterator();

long firstCount = StreamSupport.stream(oneShot, false)
        .filter(s -> !s.isEmpty())
        .count(); // filter requires traversing elements of this source

// WRONG expectation: Spliterator is already consumed;
// do not create a new source by re-wrapping this exact instance.
long secondCount = StreamSupport.stream(oneShot, false)
        .filter(s -> !s.isEmpty())
        .count(); // source is exhausted; not a fresh read
```

The second call may return 0 or source-dependent behavior, not "re-traverse the list." Request a fresh Spliterator from the source when multiple passes are needed.

### 10.5. Using peek or an external variable as a counter

```java
// AVOID: external variable is unsafe for parallel execution,
// and side effects in peek are not how results should be designed.
int[] seen = {0};

StreamSupport.stream(words.spliterator(), true)
        .peek(s -> seen[0]++)
        .count();
```

`peek` must not be used for side effects that business logic depends on; terminal operations can leverage size metadata to skip per-element traversal in eligible cases. In a parallel stream, updating `seen[0]++` also causes a data race. When you need a count, use `count()`; when you need custom aggregated state, use `collect` with a compliant Collector.

## 11. Resource Management with Custom Spliterators

`StreamSupport.stream(...)` **does not automatically know** whether a source holds a file, network connection, Reader, or socket. It merely takes a Spliterator to traverse; creating a Stream does not mean a close handler is registered to close underlying resources.

Example showing how to wrap an open Reader with StreamSupport:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Spliterator;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

static long countErrorLines(Path path) throws IOException {
    try (BufferedReader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

        Spliterator<String> source = reader.lines().spliterator();

        Stream<String> lines = StreamSupport.stream(source, false);
        return lines.filter(s -> s.startsWith("ERROR")).count();
    }
}
```

The **critical** part is `try-with-resources` closing the `BufferedReader` whether the terminal operation succeeds or throws an exception. The snippet intentionally uses `StreamSupport` to explain the mechanism. In real code, calling `reader.lines().filter(...).count()` directly is simpler; wrapping a Reader's Stream into a Spliterator and back into a Stream offers no inherent benefit.

If you want to **return a resource-owning Stream** for the caller to close, define ownership clearly and register a close handler via `onClose(...)`. When a close handler must convert `IOException` into an unchecked exception, `UncheckedIOException` can be used. Even then, the caller must still use `try-with-resources`: terminal operations like `limit` or `count` **do not automatically close the Stream**.

**Never close the Reader before the lazy Stream is consumed.** Nor should you read concurrently from one Reader inside `tryAdvance` across multiple branches unless the source is explicitly designed to support it safely.

## 12. Designing a Source That Tolerates Parallel Streams

To use `StreamSupport.stream(spliterator, true)` effectively requires more than setting `parallel = true`.

### Input must be splittable

`trySplit` should produce chunks large and balanced enough to be worthwhile. If it always returns `null`, many pipelines cannot distribute source reading across meaningful branches. If splits are too tiny, scheduling and merging overhead can outweigh actual work.

### Each branch must have independent traversal state

In `IntRangeSpliterator`, branches maintain separate cursor/fence fields. There is no shared index variable incremented by multiple threads without synchronization. A source reading from a single `BufferedReader` cannot simply split by line number without independent access and boundary detection.

### Characteristics must be accurate

If the source is a fixed-count ascending sequence, you can declare `SIZED`, `SUBSIZED`, `ORDERED`, and `SORTED`. If the source undergoes structural mutations during traversal without a consistency policy, never arbitrarily declare `IMMUTABLE` or `CONCURRENT`.

### Downstream operations must also be suitable

`filter`, `map`, and `reduce` require pure, stateless functions that do not interfere with the source. Operations like `sorted`, `distinct`, `skip`, and `limit` can increase coordination cost when preserving encounter order. A splittable source alone does not guarantee the entire pipeline benefits from parallelism.

**Measure on real data.** A 100-element source with cheap per-element work rarely sees clear parallel gains; a large source with CPU-heavy per-element processing may differ. Boxing overhead, buffering, I/O load, and branch size distribution all play a role.

## 13. When Is StreamSupport Unnecessary?

Before writing a custom Spliterator, check built-in alternatives:

| Source or Requirement | Recommended API |
| --- | --- |
| `List<T>`, `Set<T>` | `collection.stream()` or `parallelStream()` |
| Object or primitive array | `Arrays.stream(...)` |
| Integer range | `IntStream.range(...)` / `rangeClosed(...)` |
| Fixed small set of elements | `Stream.of(...)` |
| Rule-based element generation | `Stream.generate(...)` / `Stream.iterate(...)` |
| Reading file lines | `Files.lines(path)` with `try-with-resources` |
| Existing Reader | `BufferedReader.lines()` with proper Reader close lifecycle |
| Custom Iterator | `Spliterators.spliteratorUnknownSize(...)` + `StreamSupport.stream(...)` |
| Custom structure needing special splitting | Custom `Spliterator` + `StreamSupport` |
| Grouping mutable accumulated results | `collect(...)`, never mutating source inside `tryAdvance` |

In a Stream API learning module, understanding `StreamSupport` reveals how Streams are built atop `Spliterator`. In production applications, **the simplest approach should still come first** whenever it satisfies business and resource contracts.

## 14. Synthesis Example: Processing a Numeric Range in Both Modes

Suppose we need the sum of squares of multiples of 3 in `[0, 100)`. Instead of building a list upfront, we use `IntRangeSpliterator` from section 5:

```java
import java.util.stream.StreamSupport;

int sequential = StreamSupport.intStream(
        new IntRangeSpliterator(0, 100),
        false
).filter(n -> n % 3 == 0)
 .map(n -> n * n)
 .sum();

int parallel = StreamSupport.intStream(
        new IntRangeSpliterator(0, 100),
        true
).filter(n -> n % 3 == 0)
 .map(n -> n * n)
 .sum();

System.out.println(sequential); // 112761
System.out.println(parallel);   // 112761
```

The range 0 to 99 contains multiples of 3: `0, 3, ..., 99`. Their sum of squares is `9 * (0² + 1² + ... + 33²) = 112761`, fitting within `int`; for wider ranges, `n * n` and the sum could overflow. In that case, switch to `LongStream` and multiply in `long` or use larger numeric types as required.

What this example demonstrates:

1. `tryAdvance` emits each element once in sequential execution.
2. When parallel, `trySplit` can partition into non-overlapping sub-ranges.
3. `filter` and `map` are lazy intermediate operations.
4. `sum()` is the terminal operation, consuming all produced results.
5. Flipping the `parallel` flag does not alter the computation when arithmetic bounds and state rules hold.

**Performance caveat:** with only 100 elements, parallel execution can take longer than sequential execution. This example targets correctness, not benchmarking.

## 15. Checklist Before Writing a Custom Stream Source

1. **Does a suitable source API already exist?** If `stream()` or `Arrays.stream` is available, `StreamSupport` is usually unnecessary.
2. **Does `tryAdvance` emit exactly one element per `true` return?** It must return `false` when exhausted.
3. **Does `trySplit` conserve all elements without overlap?** For ordered sources, the returned part must be a prefix.
4. **Does `estimateSize` match `SIZED` and `SUBSIZED`?** If unsure, omit those flags.
5. **Is `SORTED` accurate and `getComparator` valid?** Distinguish natural order from a custom comparator.
6. **Can the source change during traversal?** Evaluate `IMMUTABLE`, `CONCURRENT`, and external data interactions.
7. **Is a primitive Spliterator needed?** `OfInt`, `OfLong`, and `OfDouble` avoid boxing when the source is natively primitive.
8. **Is late binding needed?** A Supplier can defer obtaining the Spliterator, but declared characteristics must match accurately.
9. **What resources does the source hold?** `StreamSupport` does not auto-close files/Readers/sockets; define ownership and close handlers.
10. **Is the Stream consumed exactly once?** Never reuse an exhausted Stream or Spliterator.
11. **Does parallelism help?** Enable it only after verifying branch splitting, state isolation, and cost.
12. **Do infinite sources have a stopping condition?** `limit` and short-circuiting help, but do not replace closing responsibilities.

## 16. Self-Check Questions

1. What does `StreamSupport.stream(spliterator, false)` return? **`Stream<T>`**, using the given Spliterator as a sequential source.
2. If `tryAdvance` returns `true`, what must happen? **Call action exactly once with one element**.
3. Is `trySplit` returning `null` an error? **No**, it signals it cannot or chooses not to split right now.
4. For `ORDERED`, which portion should the branch returned by `trySplit` contain? **A prefix** of the remaining elements.
5. Why must you not reuse an exhausted Spliterator for a second pass? **It retains consumed state** and does not reset its cursor automatically.
6. May `SIZED` be declared if you only guess the source length? **No**, declaring `SIZED` requires exact size per contract.
7. Is `Spliterator`'s `CONCURRENT` the same as `Collector.Characteristics.CONCURRENT`? **No**, one describes the source and the other describes result accumulation.
8. Why does `IntRangeSpliterator.getComparator()` return `null`? **Because** the source is marked `SORTED` in natural ordering.
9. How do you create a primitive stream from `Spliterator.OfInt`? **`StreamSupport.intStream(spliterator, parallel)`**.
10. Should you pass `parallel = true` for every source? **No**, the source must be splittable and the computation heavy enough to justify overhead.
11. What does the Supplier overload provide? **Defers obtaining the Spliterator until the terminal operation begins**.
12. Does `StreamSupport` automatically close a Reader read by a Spliterator? **No**, you must manage the source and resource ownership.
13. When using `spliteratorUnknownSize`, should you declare `SUBSIZED`? **No**, the source size is unknown upfront.
14. Is `StreamSupport.stream(list.spliterator(), false)` always better than `list.stream()`? **No**, for Lists prefer calling `stream()` directly.
15. If `trySplit` produces two overlapping parts, what happens to `count()` and `sum()`? **They may count or sum duplicates**, violating the Spliterator contract.

**Guiding principle:** `StreamSupport` is the bridge that brings **a custom source's Spliterator** into the Java Stream API, not a replacement for standard Stream factories. Ensure `tryAdvance` emits accurate elements, `trySplit` partitions without overlap while preserving order when promised, declare `characteristics` truthfully, and manage external resources explicitly. Switch to parallel only when the source splits safely and processing cost outweighs parallel overhead.
