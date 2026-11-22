# Role of Spliterator in Traversing and Splitting Sources

## 1. Where Does Spliterator Sit in the Java Stream API?

In **JAVA_STREAM_API**, developers typically build pipelines using `filter`, `map`, `reduce`, and `collect`, rarely needing to write loops to read individual elements manually. Retrieving data from a `List`, an array, or a custom source is organized by the Stream API through a foundational interface: **`java.util.Spliterator<T>`**.

The name `Spliterator` combines *split* and *iterator*. It has two primary responsibilities:

1. **Traversing elements:** sequentially delivering elements to a `Consumer` when requested.
2. **Splitting the source:** partitioning the remaining work into parts that can be traversed independently, giving the system an opportunity for parallel execution.

Additionally, a Spliterator **describes characteristics of the source**, such as whether the source is ordered, whether its exact size is known, or whether it may contain duplicates or `null` values. This information helps the Stream API choose an appropriate execution strategy.

~~~text
                List / Set / array / custom source
                               │
                               ▼
                          Spliterator
                 ┌─────────────┼──────────────┐
                 ▼             ▼              ▼
            tryAdvance     trySplit()    characteristics()
         traverse elements split parts   declare properties
                 │             │              │
                 └─────────────┴──────────────┘
                               │
                               ▼
                  StreamSupport / Stream API
                               │
                       filter → map → ...
                               │
                    collect / reduce / sum
~~~

**Important distinction:** A Spliterator is neither a terminal operation nor a transformation like `map`. It is the **underlying source access and partitioning mechanism** beneath the pipeline. If a source splits well, a parallel stream can process parts independently; if it cannot be split, simply calling `parallel()` will not automatically turn the problem into useful parallel tasks.

This article belongs to the **Spliterators and Custom Sources** chapter; examples use Java 17+ and focus on traversal/splitting semantics, characteristic contracts, performance, and data lifecycle.

## 2. Spliterator Compared to Iterator and Stream

`Iterator<T>` generally only provides operations to retrieve the next element. `Spliterator<T>` adds the ability to split work and report source characteristics.

| Aspect | `Iterator<T>` | `Spliterator<T>` | `Stream<T>` |
| --- | --- | --- | --- |
| Element-by-element traversal | `hasNext()`, `next()` | `tryAdvance(action)` | Internal pipeline processing |
| Remaining traversal | Loop or `forEachRemaining` | `forEachRemaining(action)` | `forEach` / other terminals |
| Source splitting | No standard equivalent API | `trySplit()` | System can leverage when parallel |
| Remaining size estimate | No common contract | `estimateSize()` | May be inferred via source/Spliterator |
| Ordering/size characteristics | No standard flag set | `characteristics()` | Can rely on or alter via operations |
| Purpose | Direct traversal | Traversing and partitioning sources | Declarative transformation and aggregation |

You should not use `Spliterator` directly just to write a loop instead of `Iterator`. For typical data processing needs, `stream()` and higher-level operations remain clearer. Working directly with `Spliterator` makes sense when you need to **understand or define a source**, especially a source with custom splitting rules.

## 3. Core Methods of Spliterator

Abbreviated signature:

~~~java
public interface Spliterator<T> {
    boolean tryAdvance(Consumer<? super T> action);
    void forEachRemaining(Consumer<? super T> action);
    Spliterator<T> trySplit();
    long estimateSize();
    int characteristics();

    // Related APIs:
    long getExactSizeIfKnown();
    boolean hasCharacteristics(int characteristics);
    Comparator<? super T> getComparator();
}
~~~

| Method | Meaning | Return Value or Effect |
| --- | --- | --- |
| `tryAdvance(action)` | If elements remain, pass **exactly one** element to action | `true` if an element was passed; `false` if exhausted |
| `forEachRemaining(action)` | Traverse remaining elements and invoke action for each | Returns nothing |
| `trySplit()` | Attempt to split off part of the untraversed work | Returns a child Spliterator or `null` |
| `estimateSize()` | Estimate the number of remaining elements | Non-negative `long`, may be `Long.MAX_VALUE` if unknown |
| `characteristics()` | Bitmask of **guaranteed** characteristics | Combination of flags `ORDERED`, `SIZED`, ... |
| `getExactSizeIfKnown()` | Exact size if `SIZED` is present | Remaining count, or `-1` |
| `hasCharacteristics(flags)` | Check whether all queried flags are present | `boolean` |
| `getComparator()` | Comparator for a `SORTED` Spliterator | Comparator, or `null` for natural ordering |

`tryAdvance` and `trySplit` are the two central methods in this article. A Spliterator can **traverse correctly** without being splittable; in that case `trySplit()` may return `null`. The interface does not require every source to be splittable or to split into two equal halves.

## 4. Traversing a Source with tryAdvance and forEachRemaining

### 4.1. tryAdvance: one call, at most one element

~~~java
import java.util.List;
import java.util.Spliterator;

public class TraverseWithSpliterator {
    public static void main(String[] args) {
        Spliterator<String> cursor =
            List.of("An", "Bình", "Chi").spliterator();

        boolean first = cursor.tryAdvance(
            value -> System.out.println("First: " + value)
        );
        System.out.println(first); // true

        boolean second = cursor.tryAdvance(System.out::println);
        System.out.println(second); // true; passed element "Bình"

        boolean third = cursor.tryAdvance(System.out::println);
        System.out.println(third); // true; passed element "Chi"

        boolean done = cursor.tryAdvance(System.out::println);
        System.out.println(done); // false; no elements remaining
    }
}
~~~

`tryAdvance` differs from `Iterator.next()`: you supply an **action** for the Spliterator to pass the element into, rather than asking it to return the element to the caller. Each time it returns `true`, the action is invoked for exactly one element; when it returns `false`, no element is emitted.

If `action` is `null`, the Spliterator may throw `NullPointerException` when used to process an element. To make custom code predictable, check `Objects.requireNonNull(action)` before invoking the action.

### 4.2. forEachRemaining: traversing all remaining elements

~~~java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> cursor =
    List.of("A", "B", "C", "D").spliterator();

cursor.tryAdvance(System.out::println); // A

cursor.forEachRemaining(System.out::println);
// B
// C
// D
~~~

`forEachRemaining` is defined by default via repeated calls to `tryAdvance`, though an implementation may optimize bulk traversal.

**Important:** A Spliterator is a traversal cursor with **forward-moving state**. Once `tryAdvance` or `forEachRemaining` consumes part of it, subsequent traversals only see the **unconsumed** portion. To traverse again from the beginning, you typically need to obtain a new Spliterator from the source.

### 4.3. Do not confuse side effects with pipeline results

The goal of the examples above is to observe traversal behavior. In a real pipeline, do not rely on `peek` or `map` callbacks definitely being called for every element to write audit logs or perform business side effects. A Stream may short-circuit or optimize intermediate steps; side-effect management should be designed separately.

## 5. Splitting a Source with trySplit

`trySplit()` can create **a new Spliterator** covering a portion of the untraversed elements. The original Spliterator continues to represent the remaining part.

~~~text
Before splitting:
     original = [A, B, C, D, E, F, G, H]

Call original.trySplit()
                 │
                 ├── prefix = [A, B, C, D]
                 └── original keeps [E, F, G, H]

Can split further:
     prefix.trySplit()   → [A, B] + [C, D]
     original.trySplit() → [E, F] + [G, H]
~~~

This is **an illustrative split pattern**. The API does not guarantee splitting exactly in the middle, does not guarantee always being able to split, and does not guarantee a specific number of splits. For an `ORDERED` Spliterator, the returned Spliterator must cover a **prefix** of the untraversed elements in encounter order, while the original object retains the subsequent part.

### 5.1. Practical example with List

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class SplitListDemo {
    public static void main(String[] args) {
        List<String> source =
            List.of("A", "B", "C", "D", "E", "F");

        Spliterator<String> remaining = source.spliterator();
        Spliterator<String> prefix = remaining.trySplit();

        List<String> result = new ArrayList<>();

        if (prefix != null) {
            prefix.forEachRemaining(result::add);
        }
        remaining.forEachRemaining(result::add);

        System.out.println(result); // [A, B, C, D, E, F]
    }
}
~~~

When combining **the prefix first, followed by the remaining part**, you recover the exact encounter order of the `List` source. Note: some Spliterators cannot split, so checking `prefix != null` is mandatory.

### 5.2. One split does not necessarily create two threads

`trySplit()` merely exposes the ability to divide work. It **does not create threads on its own**. Scheduling and running multiple branches is the responsibility of the calling framework or program. Parallel streams may use recursive splitting, but there is no guarantee that "each child Spliterator corresponds to one thread."

### 5.3. Rule against losing or duplicating elements

For a valid split, the initial set of untraversed elements must be partitioned into **non-overlapping parts with no lost elements**. If the source has an encounter order, concatenating the prefix and the remaining part must represent the exact remaining sequence of the source. This is the most important invariant when designing `trySplit` for a custom source.

## 6. Size Estimation and Characteristics

A Spliterator describes source properties through bit flags. These are **guarantees about the source**, not arbitrary hints to "enable optimizations."

| Flag | Guaranteed Meaning | Typical Scenario |
| --- | --- | --- |
| `ORDERED` | Elements have a defined encounter order | `List`, ascending sequence |
| `DISTINCT` | Elements are unique according to `equals` | `Set`, non-repeating integer sequence |
| `SORTED` | Elements are ordered by a comparator or natural order; also implies `ORDERED` | Sorted number sequence |
| `SIZED` | `estimateSize()` is exact before traversal/splitting, per the size contract | Fixed array, stable `List` |
| `SUBSIZED` | All child Spliterators produced by `trySplit` also have `SIZED` and `SUBSIZED` | Arrays, interval-split numeric ranges |
| `NONNULL` | Elements emitted by the source are never `null` | `IntStream` and certain reference sources |
| `IMMUTABLE` | The source structure cannot be modified during traversal | Fixed data source |
| `CONCURRENT` | The source supports concurrent structural modification during traversal | Certain concurrent collections |

A source can declare multiple flags:

~~~java
import java.util.List;
import java.util.Spliterator;

Spliterator<Integer> spliterator =
    List.of(10, 20, 30).spliterator();

boolean ordered = spliterator.hasCharacteristics(
    Spliterator.ORDERED
);

boolean sized = spliterator.hasCharacteristics(
    Spliterator.SIZED
);

System.out.println(ordered); // true
System.out.println(sized);   // true
~~~

**Do not over-infer:**

- `ORDERED` does not mean callbacks must execute in chronological order when running in parallel; it refers to encounter order and the result semantics of order-sensitive operations.
- `SORTED` must be paired with `ORDERED` and an appropriate comparator rule. For a source sorted in natural order, `getComparator()` returns `null`. If a Spliterator does not have `SORTED`, `getComparator()` throws `IllegalStateException`.
- `DISTINCT` must hold for the actual values emitted by the source, not just for keys you hope are unique.
- `IMMUTABLE` refers to **the source structure**, not a guarantee that every object inside is deeply immutable.
- `CONCURRENT` does not make a lambda updating an `ArrayList` or shared variable thread-safe.
- `SIZED` and `SUBSIZED` do not mean the pipeline after `filter` still knows the exact output element count.

### 6.1. estimateSize and getExactSizeIfKnown

~~~java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> s = List.of("A", "B", "C").spliterator();

System.out.println(s.estimateSize());        // 3
System.out.println(s.getExactSizeIfKnown()); // 3

s.tryAdvance(value -> {});
System.out.println(s.estimateSize());        // 2
~~~

If the source **does not have `SIZED`**, `getExactSizeIfKnown()` returns `-1`. `estimateSize()` must still provide an estimate per the contract; `Long.MAX_VALUE` can be used for unbounded sources or unknown sizes.

Falsely marking `SIZED` is dangerous: a terminal operation like `count()` can rely on the declared size to optimize, leading to an incorrect count without traversing individual elements. Never use `SIZED` to "help the Stream run faster" if the actual count cannot be guaranteed.

## 7. Primitive Stream Spliterators

To avoid boxing, Java provides specialized interfaces:

| Data Type | Spliterator | `tryAdvance` Action | Corresponding Stream |
| --- | --- | --- | --- |
| `int` | `Spliterator.OfInt` | `IntConsumer` | `IntStream` |
| `long` | `Spliterator.OfLong` | `LongConsumer` | `LongStream` |
| `double` | `Spliterator.OfDouble` | `DoubleConsumer` | `DoubleStream` |

Example of getting a Spliterator from an `IntStream`:

~~~java
import java.util.Spliterator;
import java.util.stream.IntStream;

Spliterator.OfInt cursor = IntStream.rangeClosed(1, 4)
    .spliterator();

cursor.forEachRemaining((int n) -> System.out.println(n));
// 1
// 2
// 3
// 4
~~~

Primitive Spliterators have specialized methods to avoid creating `Integer`, `Long`, or `Double` objects for each element. When defining large numeric sources, choosing the right primitive Spliterator can reduce allocation overhead and allow chaining terminal operations such as `sum`, `average`, and `summaryStatistics`.

## 8. Complete Example: Spliterator.OfInt for a Custom Integer Range

We will build a Spliterator for an integer range **from `startInclusive` up to (excluding) `endExclusive`**, similar to `IntStream.range`. Notice the two parts of the contract:

- `tryAdvance` traverses each number exactly once.
- `trySplit` splits the remaining range into a **prefix** and the remaining part, without duplicating or losing numbers.

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class CustomIntRangeDemo {
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

            action.accept(current++);
            return true;
        }

        @Override
        public OfInt trySplit() {
            long remaining = estimateSize();
            if (remaining <= 1) {
                return null;
            }

            // Compute using long to prevent overflow when current is negative and fence is positive.
            int middle = (int) ((long) current + remaining / 2);

            RangeSpliterator prefix =
                new RangeSpliterator(current, middle);
            current = middle; // The original instance keeps the second half.

            return prefix;
        }

        @Override
        public long estimateSize() {
            return (long) fence - current;
        }

        @Override
        public int characteristics() {
            return ORDERED | DISTINCT | SORTED | SIZED
                | SUBSIZED | NONNULL | IMMUTABLE;
        }

        @Override
        public Comparator<? super Integer> getComparator() {
            // Has SORTED and uses natural ordering.
            return null;
        }
    }

    public static void main(String[] args) {
        int[] numbers = StreamSupport.intStream(
                new RangeSpliterator(2, 11),
                true // Allow the Stream to run in parallel.
            )
            .filter(n -> n % 2 == 0)
            .toArray();

        System.out.println(Arrays.toString(numbers));
        // [2, 4, 6, 8, 10]
    }
}
~~~

### 8.1. Why is tryAdvance correct?

`current` represents the next unemitted number; `fence` is the exclusive upper bound. If `current < fence`, we emit one number and increment the cursor. When `current >= fence`, the method returns `false`. Each value in the range is emitted exactly once if the Spliterator is used according to its contract.

For example, `RangeSpliterator(2, 5)` emits `2, 3, 4` and then terminates.

### 8.2. Why is trySplit correct?

Suppose the remaining elements are `[2, 3, 4, 5, 6, 7, 8, 9, 10]`. `middle` is computed near the midpoint. The new Spliterator receives `[2, middle)`, while the original Spliterator updates `current = middle` to hold `[middle, 11)`. The two ranges are **non-overlapping**, and concatenating the returned prefix followed by the remaining part restores the entire original range.

If 0 or 1 numbers remain, `trySplit` returns `null` because splitting further yields no benefit. Using `long` to compute the difference and midpoint prevents `int` overflow if the two endpoints of the range are far apart. Splitting does not pre-materialize a stream of data; it only shifts the boundaries of untraversed work segments.

### 8.3. Why are the characteristics flags valid?

- `ORDERED`: the numbers in the range are ascending.
- `DISTINCT`: there are no duplicate numbers.
- `SORTED`: follows natural ordering; `getComparator()` returns `null`.
- `SIZED`: `estimateSize()` always equals the number of remaining elements.
- `SUBSIZED`: all sub-ranges satisfy `SIZED` and `SUBSIZED`.
- `NONNULL`: primitive `int` cannot be `null`.
- `IMMUTABLE`: the source consists of fixed numeric bounds, with no underlying mutable data structure.

Because the declared characteristics match the actual data generation rules, the Stream can use them to execute or optimize the pipeline. If a later custom version skips numbers or changes the ordering, the announced flags must be re-evaluated.

## 9. Testing Splitting: No Duplicates, No Losses, and Correct Encounter Order

A simple way to test is to split manually first, traverse the **returned Spliterator first**, and then traverse the original Spliterator.

The following snippet belongs in the same `CustomIntRangeDemo` class where `RangeSpliterator` is defined:

~~~java
import java.util.Arrays;
import java.util.Spliterator;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

Spliterator.OfInt remaining = new RangeSpliterator(0, 10);
Spliterator.OfInt prefix = remaining.trySplit();

int[] first = prefix == null
    ? new int[0]
    : StreamSupport.intStream(prefix, false).toArray();

int[] second = StreamSupport.intStream(remaining, false)
    .toArray();

int[] combined = IntStream.concat(
    IntStream.of(first),
    IntStream.of(second)
).toArray();

int[] expected = IntStream.range(0, 10).toArray();

if (!Arrays.equals(combined, expected)) {
    throw new AssertionError("trySplit lost, duplicated, or reordered elements");
}

System.out.println("PASS"); // Reconstructed sequence 0..9 accurately.
~~~

With this Spliterator, a single split produces a prefix around `[0,5)` and a remaining part around `[5,10)`. However, do not write generic tests for **all kinds** of Spliterators that require splitting strictly in the middle: the split size and position are at the implementation's discretion.

### Checking sequential and parallel results

~~~java
long serialSum = StreamSupport.intStream(
        new RangeSpliterator(0, 100_000),
        false
    )
    .asLongStream()
    .sum();

long parallelSum = StreamSupport.intStream(
        new RangeSpliterator(0, 100_000),
        true
    )
    .asLongStream()
    .sum();

if (serialSum != parallelSum || serialSum != 4_999_950_000L) {
    throw new AssertionError("Sum mismatch");
}
~~~

Each terminal operation uses **a new Spliterator**, since the old Spliterator is already consumed. `asLongStream()` converts to `long` before summing to avoid `int` overflow.

Other important checks for custom sources: empty ranges, single-element ranges, ranges with negative numbers, boundaries near `Integer.MIN_VALUE` and `Integer.MAX_VALUE`, multiple consecutive splits, and the same computation across different source sizes. These checks belong in a dedicated QA/testing step; here we illustrate the design contract.

## 10. Connecting Spliterator with StreamSupport

`StreamSupport` provides methods to create a Stream from an existing Spliterator:

~~~java
Stream<T> StreamSupport.stream(
    Spliterator<T> spliterator,
    boolean parallel
);

IntStream StreamSupport.intStream(
    Spliterator.OfInt spliterator,
    boolean parallel
);
~~~

Example with a List:

~~~java
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

Spliterator<String> source =
    List.of("Java", "Stream", "API").spliterator();

List<String> result = StreamSupport.stream(source, false)
    .map(String::toLowerCase)
    .toList();

System.out.println(result); // [java, stream, api]
~~~

`parallel = true` enables a parallel pipeline; it **does not guarantee** it will be faster or force multiple threads to actually process the data. Parallel effectiveness depends on splittability, per-element cost, CPU core count, system load, and ordering constraints.

### 10.1. Overload accepting a Spliterator Supplier

`StreamSupport.stream(...)` and `StreamSupport.intStream(...)` also have overloads that accept a **Supplier** along with characteristics flags:

~~~java
import java.util.Spliterator;
import java.util.function.Supplier;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

// RangeSpliterator is defined in section 8.
int flags = Spliterator.ORDERED | Spliterator.DISTINCT
    | Spliterator.SORTED | Spliterator.SIZED
    | Spliterator.SUBSIZED | Spliterator.NONNULL
    | Spliterator.IMMUTABLE;

Supplier<Spliterator.OfInt> factory =
    () -> new RangeSpliterator(0, 100);

IntStream values = StreamSupport.intStream(
    factory,
    flags,
    true
);

long count = values.count(); // 100
~~~

The Supplier is invoked when the terminal operation starts, making it suitable for sources that need to bind Spliterator creation to consumption time. The characteristics passed to the Supplier overload **must match** the `characteristics()` of the Spliterator produced by the Supplier; misdeclaring them can cause undefined Stream behavior under the API contract.

Do not use a Supplier as a way to implicitly open multiple connections or replay an old Stream: a Stream remains a **single-use object**.

### 10.2. Built-in factories from Spliterators

If your data is already in an array, collection, or iterator, consider existing APIs before writing your own:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;

Iterator<String> iterator =
    List.of("A", "B", "C").iterator();

Spliterator<String> source = Spliterators.spliteratorUnknownSize(
    iterator,
    Spliterator.ORDERED
);
~~~

`spliteratorUnknownSize` wraps an Iterator whose size is not known in advance. Do not declare `SIZED` or `SUBSIZED` without an exact size contract; the implementation may split in internal batches, but it does not turn the source into random-access data.

For standard arrays or collections, `Arrays.spliterator(...)`, `Collection.spliterator()`, and built-in `stream()` methods are usually sufficient for applications. Write a custom Spliterator only when you need a source or splitting strategy that standard options do not properly express.

## 11. Encounter Order, Splitting, and Downstream Operations

A source's `ORDERED` characteristic matters when operations depend on order:

- `findFirst()` selects the first element according to encounter order, if present.
- `limit(n)` on an ordered source takes the first `n` elements.
- `forEachOrdered` executes the action in encounter order if the Stream is ordered.
- `sorted()` can establish a new order on the output.
- `unordered()` **removes the constraint** on encounter order; it does not perform a random shuffle.

~~~java
import java.util.List;
import java.util.stream.StreamSupport;

// RangeSpliterator from section 8.
List<Integer> firstFive = StreamSupport.intStream(
        new RangeSpliterator(0, 100),
        true
    )
    .limit(5)
    .boxed()
    .toList();

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

Because the source declares `ORDERED` and `trySplit` returns a prefix, the pipeline can preserve the "first 5 elements" semantics. If you omit `ORDERED` or implement `trySplit` incorrectly (for instance, the child receives a segment that is not a proper prefix while still reporting `ORDERED`), order-sensitive operations may produce wrong results.

### 11.1. Ordering constraints can limit parallel speed

With a parallel stream, `limit` and `skip` on an ordered source may require coordination to determine the exact prefix. If business logic allows "taking any 5 elements," `unordered()` can relax the constraint, though it will **change the semantics**:

~~~java
List<Integer> anyFive = StreamSupport.intStream(
        new RangeSpliterator(0, 100),
        true
    )
    .unordered()
    .limit(5)
    .boxed()
    .toList();

// Contains 5 numbers from the range, not guaranteed to be 0..4.
~~~

Do not use `unordered().limit(...)` for pagination, fetching the earliest records, or top-N by criteria. For top-N, sort by the criteria first and then limit.

## 12. Late-Binding, Fail-Fast, and Source Mutation

Some Spliterators are **late-binding**: they bind to the source's state only upon the first traversal, split, or size calculation. Other implementations bind earlier. For regular collections, if an unauthorized structural modification occurs **after traversal has begun**, the result may be undefined or detected via an exception.

For example, `ArrayList` has a late-binding Spliterator along with a *best-effort* fail-fast structural modification detection mechanism:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

ArrayList<String> source = new ArrayList<>(List.of("A"));

Spliterator<String> s = source.spliterator();
source.add("B"); // Before starting to use s.

s.forEachRemaining(System.out::println);
// With ArrayList, late binding sees both A and B.
~~~

This is a property of `ArrayList`, **not a universal guarantee for all Spliterators**. Once traversal has started, do not structurally modify the source unless the source contract allows it. In particular, fail-fast is not a synchronization mechanism or a reliable correctness check; it only helps detect certain misuse bugs.

**`IMMUTABLE`** and **`CONCURRENT`** have different meanings:

- `IMMUTABLE`: the source is not structurally modified during traversal; this does not mean child elements are deeply immutable.
- `CONCURRENT`: the source supports structural modifications concurrent with traversal under the source's own contract; it does not imply encounter order or a fixed snapshot.
- Sources without these two flags should generally avoid external structural interference while the pipeline is running.

When creating a Stream from a custom mutable source, the `StreamSupport.stream(supplier, characteristics, parallel)` overload can defer obtaining the Spliterator. However, **it does not make an inherently non-thread-safe source safe**; you must still adhere to the data type's mutation and synchronization rules.

## 13. Split Quality Determines Parallel Stream Effectiveness

A Spliterator with a valid `trySplit` does not necessarily produce a fast parallel stream.

### Influencing factors

| Factor | Possible Consequence |
| --- | --- |
| `trySplit()` always returns `null` | Cannot generate multiple work units from this source |
| Highly skewed split, one branch very large | Difficult to load-balance across workers |
| Splitting into too many tiny chunks | Task creation/management overhead increases |
| Unreasonable `estimateSize()` | Framework struggles to pick a good splitting threshold |
| `ORDERED` when the task does not need order | May cause operations like `limit`/`distinct` to require more coordination |
| Mapper performs slow I/O or writes shared state | Contention/bottlenecks can outweigh splitting benefits |
| Small source, cheap transformation | Parallel overhead may exceed processing cost |

For example, `RangeSpliterator` splits the remaining elements roughly in half each time, a strategy that usually works well for data with relatively uniform processing cost. For data whose per-element cost is heavily skewed, splitting **element count** evenly may not balance **processing time**.

### Do not try to optimize by misdeclaring characteristics

Adding `SIZED`, `DISTINCT`, or `SORTED` when the source does not satisfy the contract can cause a Stream to **compute wrong results** rather than merely "displaying wrong metadata." For example, `count()` may skip traversal if the count is known; `distinct()` may leverage `DISTINCT` to skip work; `sorted()` may leverage `SORTED`. Only declare what the implementation actually guarantees.

## 14. Resource-Backed Sources: Spliterator Does Not Auto-Close Files

A Spliterator describes **traversal and splitting**, not a resource management protocol. If a Stream source opens a file, socket, or database cursor, merely completing a terminal operation may not automatically close the resource.

For files, use standard APIs and closing mechanisms:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileStreamExample {
    static long countNonBlankLines(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path)) {
            return lines
                .filter(line -> !line.isBlank())
                .count();
        }
    }
}
~~~

`Files.lines(path)` returns a Stream backed by a file resource that must be closed with `try-with-resources`. Do not build a custom file-reading Spliterator just to try parallelism while ignoring reader closing rules, I/O exceptions, and source access safety.

When a custom source must open and close resources, clearly design **who owns the resource**, **who closes it**, **when it closes**, and whether multiple branches after `trySplit` can safely share the same source. `StreamSupport.stream(...)` does not invent closing rules for a source; closing can be integrated via `Stream.onClose(...)` and `try-with-resources` if the design permits.

## 15. Common Mistakes When Writing or Using a Spliterator

### Mistake 1: tryAdvance returns true without emitting an element

~~~java
// VIOLATES contract:
// public boolean tryAdvance(Consumer<? super T> action) {
//     return true; // Does not call action.accept(...)
// }
~~~

If it returns `true`, it must pass exactly one element to the action. If exhausted, return `false`. Do not use `true` to indicate "more elements may still be generated in the future" when nothing has been emitted.

### Mistake 2: trySplit loses or duplicates data

~~~text
Untraversed source: [0, 1, 2, 3, 4, 5]

Wrong: child = [0, 1, 2, 3]   original = [3, 4, 5]
                                         ↑ duplicated 3

Wrong: child = [0, 1]         original = [3, 4, 5]
                                ↑ lost 2

Right: child = [0, 1, 2]      original = [3, 4, 5]
~~~

For an ordered source, the returned child Spliterator must also be an **in-order prefix** of the untraversed portion. Across multiple splits, this guarantee must continue to hold recursively.

### Mistake 3: sharing the same Spliterator across multiple threads

A Spliterator is generally **not guaranteed to be thread-safe** for concurrent traversal/splitting on **the same instance**. The right pattern is to partition first, then manage each branch separately; do not call `tryAdvance` or `trySplit` concurrently on a shared cursor unless the implementation has a contract supporting it.

### Mistake 4: declaring SIZED for a source with unknown size

~~~java
// Do not declare SIZED if estimateSize() is only a guess.
// Do not declare SUBSIZED if child Spliterators do not have exact sizes.
~~~

`SIZED` is an exact count commitment, not "a roughly accurate size." Fix this by only declaring characteristics that truly hold and returning an appropriate estimate.

### Mistake 5: declaring SORTED without handling getComparator

A `SORTED` Spliterator must have a valid ordering rule and support `getComparator()`: returning `null` for natural ordering or returning the corresponding comparator. Do not mark `SORTED` on a source that merely "usually looks sorted."

### Mistake 6: using parallel to mutate a mutable source

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

// Wrong: modifying source structure while the Stream traverses it.
// source.parallelStream().forEach(source::add);
~~~

Interfering with the source inside a pipeline can cause errors, dropped data, duplicated data, or undefined behavior. `CONCURRENT` only applies when **the source itself** supports concurrent modification under its own contract, and does not legitimize arbitrary side-effecting callbacks.

### Mistake 7: thinking Spliterator runs in parallel automatically

`trySplit` only enables splitting. To create a parallel stream from a Spliterator, use `StreamSupport.stream(s, true)` or `StreamSupport.intStream(s, true)`; the framework decides how to run it. And if the source cannot be split, simply enabling the parallel flag brings no independent work units.

### Mistake 8: consuming a Spliterator first and then expecting a full Stream from it

~~~java
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

Spliterator<Integer> source = List.of(1, 2, 3).spliterator();
source.tryAdvance(value -> {}); // Already consumed 1.

List<Integer> remaining = StreamSupport.stream(source, false)
    .toList();

// remaining only has [2, 3], not [1, 2, 3].
~~~

A Spliterator does not rewind automatically. When you need to traverse again from the start, obtain a new Spliterator from the source or design a factory for independent runs.

## 16. Choosing an Approach for a Data Source

| Need | Recommended Solution |
| --- | --- |
| Processing a regular `List`, `Set`, or array | Use `collection.stream()` or `Arrays.stream(...)` |
| Direct single-pass traversal, no pipeline needed | `Iterator` or loop |
| Creating a Stream from a custom Spliterator | `StreamSupport.stream(s, parallel)` |
| Source emitting `int`, `long`, `double` values | `Spliterator.OfInt/OfLong/OfDouble` or built-in primitive Stream |
| Wrapping an Iterator of unknown size | `Spliterators.spliteratorUnknownSize(...)` |
| Supporting parallelism from a custom source | Design `trySplit`, size, and characteristics properly; benchmark |
| Guaranteeing element retrieval order | Source has `ORDERED`, `trySplit` returns prefix, preserve order constraints in pipeline |
| Source backed by files/I/O resources | Resource-managed APIs and `try-with-resources`; avoid custom splitting if unsafe |
| Standard filtering/mapping/aggregation | Prefer high-level operations over writing a custom Spliterator |

## 17. Self-Check Questions

1. **What two responsibilities does Spliterator address?** Traversing elements and splitting untraversed elements into independent parts.
2. **If `tryAdvance(action)` returns `true`, what must happen?** The action is called to receive exactly one element.
3. **Does `trySplit()` returning `null` mean the source is exhausted?** Not necessarily; elements may remain, but the source cannot or chooses not to split further.
4. **With `ORDERED`, which portion must the Spliterator returned by `trySplit` represent?** A prefix of the untraversed elements.
5. **Does `estimateSize()` returning `Long.MAX_VALUE` mean the source definitely has that many elements?** No. It may represent an unknown estimate or an infinite source.
6. **What does `getExactSizeIfKnown()` return if `SIZED` is absent?** `-1`.
7. **How does `SIZED` differ from `SUBSIZED`?** `SIZED` guarantees exact size on the current Spliterator; `SUBSIZED` extends this guarantee to child Spliterators created by splitting.
8. **Can `SORTED` be used with an unordered source?** No. `SORTED` implies `ORDERED`.
9. **For a `SORTED` Spliterator in natural order, what does `getComparator()` return?** `null`.
10. **What advantage does `Spliterator.OfInt` have?** Traverses `int` values via `IntConsumer`, avoiding per-element boxing.
11. **Does calling `parallel()` guarantee multiple threads do useful work if the Spliterator cannot split?** No.
12. **Why can misdeclaring `DISTINCT` or `SIZED` cause a program to compute wrong results?** The Stream may trust those characteristics and skip certain processing/traversal steps.
13. **Can a partially consumed Spliterator automatically restart?** No; a new source or Spliterator is needed.
14. **Does `CONCURRENT` make a callback writing into a shared `ArrayList` safe?** No; that characteristic describes the source's contract.
15. **Does `StreamSupport.stream(s, true)` automatically close a file opened by a custom source?** No; resource management must be designed and closed explicitly.

**Remember:** `Spliterator` is the bridge between **a data source** and the **traversal and partitioning** capabilities of the Java Stream API. `tryAdvance` emits individual elements, `trySplit` creates independent work units, and `estimateSize` and `characteristics` describe guarantees that the framework can leverage. Only define a custom Spliterator when truly needed, ensure no elements are lost or duplicated, declare characteristics honestly, and always verify ordering, source state, resources, and performance before parallelizing.
