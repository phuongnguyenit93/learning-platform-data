# Implementing tryAdvance and forEachRemaining

## 1. Where Does Spliterator Sit in the Java Stream API?

In the **Java Stream API**, learners typically start with `Collection.stream()`, using lazy pipelines with `filter`, `map`, `reduce`, and `collect`. For custom data sources, the harder question is: **where does the Stream obtain elements one by one, and how does it know when the data is exhausted?**

A central interface that solves source traversal is **`Spliterator<T>`** (*splittable iterator*). It describes both how to **advance through elements** and how to **split off the remaining data** so that a Stream can consider parallel processing.

```text
Custom source (array, data range, file, generator...)
                       |
                       v
                 Spliterator<T>
                 /       |       \
         tryAdvance  forEachRemaining  trySplit
             |             |             |
        one element   remaining items  split work
                 \       |       /
                       v
               StreamSupport.stream(...)
                       |
                 filter / map / ...
                       |
                 collect / count / ...
```

The **Spliterators and Custom Sources** chapter focuses on two traversal methods:

- `tryAdvance`: attempts to take **one** next element and pass it to a `Consumer`.
- `forEachRemaining`: passes **all remaining elements** to the same `Consumer`.

Both methods must share the same **traversal progress state**. If `tryAdvance` has already taken the first element, `forEachRemaining` must continue from the second element, without repeating the first element or skipping any element.

**Lesson objectives:** understand the contract and return value of `tryAdvance`, know why `forEachRemaining` has a default implementation, write a custom Spliterator with a proper cursor, combine it with `trySplit`/`estimateSize`/`characteristics`, create a Stream via `StreamSupport`, and recognize common pitfalls with parallel processing, mutable data, or I/O sources.

The `Spliterator` and `StreamSupport` APIs have existed since **Java 8**. The standalone examples below run on **Java 17+**, mainly for consistency with modern examples in the `JAVA_STREAM_API` module.

## 2. Reading the Contract of tryAdvance

Signature on `Spliterator<T>`:

```java
boolean tryAdvance(Consumer<? super T> action);
```

It attempts to take the next element **if one remains**, invokes `action.accept(element)`, and then reports the result:

| Return Value | Meaning | Is `action` called? |
| --- | --- | --- |
| `true` | Processed one element | Yes, exactly once per successful call |
| `false` | No elements remaining | No |

Once the source is exhausted, subsequent calls to `tryAdvance` must also return `false`; it must not automatically wrap back to the first element or emit imaginary elements.

Example using the built-in Spliterator of a `List`:

```java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> cursor =
        List.of("A", "B", "C").spliterator();

boolean first = cursor.tryAdvance(System.out::println);  // Prints A
boolean second = cursor.tryAdvance(System.out::println); // Prints B
boolean third = cursor.tryAdvance(System.out::println);  // Prints C
boolean fourth = cursor.tryAdvance(System.out::println); // Prints nothing

System.out.println(first);  // true
System.out.println(second); // true
System.out.println(third);  // true
System.out.println(fourth); // false
```

**`tryAdvance` does not return the element**, it returns a `boolean`. The element is passed to the `Consumer` supplied by the caller. If you need to collect elements into a List, you can pass `list::add` as the action; in a regular Stream pipeline, the framework supplies the corresponding consumer.

### Action must not be null

The API contract requires `action` to be non-`null`. A custom implementation should check immediately:

```java
Objects.requireNonNull(action, "action");
```

If action is `null`, throw `NullPointerException` even when the source is already exhausted. Avoid code that only checks action after determining whether data remains, as that can violate the contract.

### Do not rely on side effects to control the source

A `Consumer` can print, write data, or mutate caller variables. However, in a Stream pipeline, side-effecting actions can make the application unpredictable; do not use logging inside `tryAdvance`/mappers as part of business output. Any exception thrown by `action.accept(...)` propagates to the caller, and the Spliterator contract **does not guarantee a specific state after an action throws an exception**.

## 3. forEachRemaining: Traversing Unconsumed Elements

Signature:

```java
void forEachRemaining(Consumer<? super T> action);
```

`forEachRemaining` does not return a count or a list. It invokes the action for **every unprocessed element** in the appropriate traversal order and finishes when the source is exhausted.

```java
Spliterator<Integer> numbers =
        List.of(10, 20, 30, 40).spliterator();

numbers.tryAdvance(n -> System.out.println("First: " + n));
// First: 10

numbers.forEachRemaining(n -> System.out.println("Remaining: " + n));
// Remaining: 20
// Remaining: 30
// Remaining: 40

System.out.println(numbers.tryAdvance(System.out::println));
// false
```

If `forEachRemaining` is called from the beginning, it traverses the entire source. If called after three successful `tryAdvance` calls, it processes only the remaining elements starting from the fourth. If the source is already exhausted, `forEachRemaining` never calls the action.

The non-`null` requirement for `action` also applies to `forEachRemaining`. Similarly to `tryAdvance`, if the action throws an exception, you should not assume the Spliterator remains in a recoverable state to continue accurately.

### forEachRemaining comes with a default implementation

In `Spliterator`, `forEachRemaining` is a **default method** with equivalent logic:

The default implementation's logic can be expressed simply as:

```java
default void forEachRemaining(Consumer<? super T> action) {
    Objects.requireNonNull(action, "action");
    while (tryAdvance(action)) {
        // tryAdvance has already passed one element to action.
    }
}
```

The snippet above illustrates the logic **inside the interface**, not a method you need to copy into your implementation class. Because `forEachRemaining` already has a default implementation, a class implementing `Spliterator` can simply implement `tryAdvance` along with the other required methods.

**Why override it anyway?** When a source has a more efficient sequential traversal (such as an array or buffer with a cursor), you can override `forEachRemaining` to reduce the loop overhead across many `tryAdvance` calls. When doing so, ensure both traversal methods **update the same cursor** rather than re-reading from the start.

## 4. Starting with a Minimal Sequential Spliterator

Suppose we manage an internal string array. An initial Spliterator may **not support splitting**; `trySplit()` returns `null`. This is a valid choice if the source is small, sequential, or hard to split:

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;

final class SimpleArraySpliterator implements Spliterator<String> {
    private final String[] data;
    private int cursor;

    SimpleArraySpliterator(String[] source) {
        this.data = Objects.requireNonNull(source, "source").clone();
    }

    @Override
    public boolean tryAdvance(Consumer<? super String> action) {
        Objects.requireNonNull(action, "action");

        if (cursor >= data.length) {
            return false;
        }

        action.accept(data[cursor++]);
        return true;
    }

    @Override
    public Spliterator<String> trySplit() {
        return null; // Splitting the remaining part is not supported.
    }

    @Override
    public long estimateSize() {
        return data.length - cursor;
    }

    @Override
    public int characteristics() {
        return ORDERED | SIZED | SUBSIZED | IMMUTABLE;
    }
}
```

This is a standalone illustrative class that can be placed in the same file as the runner class (two `public` classes cannot be declared in the same Java file). Key points to notice:

1. `data` holds a copy of the source array to prevent caller code from mutating the array structure externally during traversal.
2. `cursor` marks **the index of the next element**; the already-visited portion is `[0, cursor)`.
3. If `cursor >= data.length`, `tryAdvance` returns `false` and does not call the action.
4. After a successful step, the cursor increments by exactly one.
5. `estimateSize()` counts **the remaining elements**, not the initial count.
6. `trySplit() == null` means no further splitting is possible. Including `SUBSIZED` remains consistent here because the current Spliterator always knows its exact size and produces no child Spliterators.

`ORDERED` declares that the source has an encounter order by array index; `SIZED` declares that `estimateSize` is exact; `SUBSIZED` requires split parts to have exact sizes; `IMMUTABLE` is used because the source array is privately cloned and cannot change during traversal. `NONNULL` is not declared because elements of `String[]` **may contain null** if the caller passes them in.

### Trying both traversal methods together

```java
SimpleArraySpliterator spliterator =
        new SimpleArraySpliterator(new String[] {"A", "B", "C"});

spliterator.tryAdvance(System.out::println); // A
System.out.println(spliterator.estimateSize()); // 2

spliterator.forEachRemaining(System.out::println); // B, then C
System.out.println(spliterator.estimateSize()); // 0
System.out.println(spliterator.tryAdvance(System.out::println)); // false
```

This example uses the interface's **default `forEachRemaining`**. Even without overriding it, it continues from the right position because repeated `tryAdvance` calls updated the cursor.

## 5. Overriding forEachRemaining Without Breaking State

If you want to traverse all remaining elements with a direct loop, add the following method to the class:

```java
@Override
public void forEachRemaining(Consumer<? super String> action) {
    Objects.requireNonNull(action, "action");

    while (cursor < data.length) {
        action.accept(data[cursor++]);
    }
}
```

This snippet is a **member method** of `SimpleArraySpliterator` from the previous section. Because `cursor` is the same field used by `tryAdvance`, both methods can be interleaved:

```text
data = [A, B, C, D], cursor = 0

tryAdvance()          -> A          cursor = 1
tryAdvance()          -> B          cursor = 2
forEachRemaining()    -> C, D       cursor = 4
tryAdvance()          -> false      cursor = 4
forEachRemaining()    -> emits nothing
```

Dangerous bugs to avoid:

```java
// WRONG: restarts from 0 instead of cursor, causing A/B to repeat.
for (int i = 0; i < data.length; i++) {
    action.accept(data[i]);
}

// WRONG: updates cursor after the entire loop instead of per element,
// which can emit wrong items or fail to terminate properly.
```

In the main example, `action.accept(data[cursor++])` increments the cursor before the action call finishes. If the action throws an exception, the state may have already changed; this falls within the Spliterator contract, which does not guarantee continuation after an action error.

Overriding `forEachRemaining` is not required for every Spliterator. First make `tryAdvance` **correct**, then optimize when measurements show a need. Optimized traversal logic must be tested against edge cases: empty source, empty remainder, single remaining element, prior `tryAdvance` calls, and an action throwing an exception.

## 6. How Does Spliterator Differ from Iterator?

`Iterator<T>` centers on `hasNext()` and `next()`. `Spliterator<T>` combines checking and processing an element in a single `tryAdvance(action)` call, provides size and characteristic metadata, and enables splitting the remaining work:

| Aspect | `Iterator<T>` | `Spliterator<T>` |
| --- | --- | --- |
| Retrieving elements | `hasNext()` and `next()` | `tryAdvance(action)` |
| Traversing remaining elements | `forEachRemaining(action)` | `forEachRemaining(action)` |
| Splitting source into tasks | No `trySplit` protocol | `trySplit()` |
| Estimating remaining count | No common API | `estimateSize()` |
| Describing order/size/properties | No standard characteristic bits like Spliterator | `characteristics()`, `hasCharacteristics(...)` |
| Feeding StreamSupport | Can be wrapped via helper | Direct source for creating a Stream |

Do not build a custom Spliterator if a suitable API already exists. For a `Collection`, use `collection.spliterator()`. For a source that only exposes an `Iterator`, `Spliterators.spliteratorUnknownSize(iterator, characteristics)` is a built-in option.

```java
import java.util.Iterator;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

Iterator<String> iterator = List.of("A", "B", "C").iterator();
Spliterator<String> source = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED
);

long count = StreamSupport.stream(source, false).count();
System.out.println(count); // 3
```

The helper above creates a Spliterator when the exact size is unknown beforehand; do not attach `SIZED` or `SUBSIZED` merely because the sample data is short. Writing a custom Spliterator is worth considering when you need to control how the source is partitioned, traversal state, or specialized characteristics.

## 7. Connecting Spliterator with StreamSupport

Two common approaches:

```java
Stream<T> StreamSupport.stream(
        Spliterator<T> spliterator,
        boolean parallel
);

IntStream StreamSupport.intStream(
        Spliterator.OfInt spliterator,
        boolean parallel
);
```

These are illustrative signatures; `StreamSupport` also has overloads accepting a `Supplier` to defer obtaining the Spliterator until the terminal operation begins.

Creating an object Stream from a custom Spliterator:

```java
import java.util.Arrays;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

Spliterator<String> source =
        new SimpleArraySpliterator(new String[] {" An ", "Bình", " Chi "});

List<String> names = StreamSupport.stream(source, false)
        .map(String::strip)
        .filter(name -> !name.isBlank())
        .toList();

System.out.println(names); // [An, Bình, Chi]
```

The `false` argument creates a **sequential Stream**; `true` creates a Stream configured for **parallel** processing. Passing `true` does not guarantee faster execution or force the source to be split.

**Do not reuse a Spliterator after it has consumed the source.** Like a Stream, a Spliterator object has a cursor and moves forward only. Once exhausted, creating a new Stream from **that same Spliterator** will not yield the original elements. To process again, create a new Spliterator from the source.

## 8. Implementing trySplit: Each Part Handles a Disjoint Range

`tryAdvance` and `forEachRemaining` handle advancing through current data; `trySplit` **divides the untraversed range** into two Spliterators when the source is suitable.

For an index range `[origin, fence)`, a good implementation typically:

1. Determines a midpoint `mid` solely from the **untraversed** portion.
2. Returns a new Spliterator managing the first half `[origin, mid)`.
3. Updates the current Spliterator to manage the second half `[mid, fence)`.
4. Never duplicates, drops, or unnecessarily reorders elements when reassembled in encounter order.

```text
Before split (cursor = 0, fence = 8):
[0 1 2 3 4 5 6 7]

trySplit()
   |
   +-- returned split: [0 1 2 3]   (prefix)
   |
   +-- current:        [4 5 6 7]   (suffix)

Each Spliterator maintains its own cursor/fence.
```

Example `trySplit` for a Spliterator that already has `data`, `cursor`, and `fence` fields:

```java
@Override
public Spliterator<String> trySplit() {
    int low = cursor;
    int mid = low + (fence - low) / 2;

    if (mid == low) {
        return null; // 0 or 1 elements left, do not split further.
    }

    cursor = mid; // Current Spliterator keeps [mid, fence).
    return new RangeStringSpliterator(data, low, mid);
}
```

This snippet belongs to the full **`RangeStringSpliterator`** model in section 12; it cannot be pasted verbatim into `SimpleArraySpliterator` (since the simpler class lacks the `fence` field and range constructor).

**Note:** Not every Spliterator must be splittable. For a sequential I/O source or step-by-step generated data without a sound way to split, returning `null` is usually simpler and safer than faking a broken `trySplit`.

## 9. estimateSize and characteristics Must Tell the Truth

Two other important methods:

```java
long estimateSize();
int characteristics();
```

`estimateSize` returns **an estimate of the remaining elements**. If size cannot be known, the source may report `Long.MAX_VALUE`; if the `SIZED` characteristic is set, this value must be the **exact** remaining element count per the contract.

`characteristics` returns characteristic bits by ORing constants:

| Characteristic | Common Meaning | Important Note |
| --- | --- | --- |
| `ORDERED` | Has a defined encounter order | `trySplit` must preserve a valid prefix when splitting an ordered source. |
| `SIZED` | Exact remaining element count is known | `estimateSize()` must be exact, not an arbitrary number. |
| `SUBSIZED` | Every split part is also `SIZED` and `SUBSIZED` | Only use when maintaining the contract across child splits. |
| `IMMUTABLE` | Source cannot be structurally modified during traversal | Do not attach if the source may be mutated unexpectedly. |
| `CONCURRENT` | Source supports concurrent modification under its contract | Does not mean the Spliterator cursor itself is thread-safe. |
| `NONNULL` | Emits no `null` elements | Do not attach to a source that may contain null. |
| `DISTINCT` | No two elements are equal per `equals` | Do not assume this merely because the source is an array. |
| `SORTED` | Elements follow a declared sort order | Must follow comparator/`getComparator()` rules. |

Example for a privately cloned `String[]` array, indexed access, immutable source:

```java
@Override
public int characteristics() {
    return ORDERED | SIZED | SUBSIZED | IMMUTABLE;
}

@Override
public long estimateSize() {
    return fence - cursor;
}
```

These two methods belong in `RangeStringSpliterator` in section 12. Do not attach `NONNULL` unless every element is guaranteed non-null, and do not attach `SORTED` unless the array is sorted according to an appropriate comparator.

**Misdeclaring characteristics can cause a Stream to make invalid optimizations.** For example, when a source actually has uncounted elements yet declares `SIZED` with a wrong estimate, terminal operations like `count` may rely on size metadata without traversing elements as expected. Therefore, characteristics are part of the **source contract**, not decorative flags for speedups.

## 10. Relationship Between tryAdvance, forEachRemaining, and trySplit

A compliant Spliterator must ensure no elements are duplicated or lost when callers mix traversal methods:

```text
Initial range: [A, B, C, D, E, F]

tryAdvance()  -> A
remaining     -> [B, C, D, E, F]

trySplit()    -> returned prefix [B, C]
                 current suffix  [D, E, F]

returned.forEachRemaining() -> B, C
current.tryAdvance()        -> D
current.forEachRemaining()  -> E, F

Every input element appears exactly once:
A, B, C, D, E, F
```

Splitting may affect only the **untraversed portion** of the Spliterator being called. The already-consumed part `[A]` must never unexpectedly reappear in a child split.

In an example with encounter order, when `trySplit()` returns a child split, it must represent a **prefix** of the untraversed portion; the current Spliterator retains the remaining suffix. This allows the framework to preserve the logical order of an ordered source when needed.

### State safety rules

- Each Spliterator instance has its own cursor; do not share a single `cursor` variable that two splits could mutate concurrently.
- A **read-only** backing buffer can be shared if all splits only read data and traverse disjoint ranges.
- One split's `forEachRemaining` must never stray into another split's range.
- Do not allow a mutable source to be structurally modified while a Spliterator is traversing it, unless the source and characteristics have an explicit concurrent contract.
- Do not rely on calling `tryAdvance` or `trySplit` from multiple threads **concurrently on the exact same Spliterator instance**. A Spliterator is not thread-safe by default.

## 11. Why Can a Stream Use forEachRemaining?

The Stream framework may pull elements from a Spliterator using `tryAdvance`, or use `forEachRemaining` when sequentially processing the rest of a work unit. It **does not promise** a specific call count for either method on any given terminal operation.

The following example illustrates how a **direct caller** uses both methods:

```java
Spliterator<String> s =
        List.of("alpha", "beta", "gamma").spliterator();

List<String> processed = new ArrayList<>();

boolean gotOne = s.tryAdvance(processed::add);
s.forEachRemaining(processed::add);

System.out.println(gotOne);    // true
System.out.println(processed); // [alpha, beta, gamma]
```

In an actual Stream pipeline, the framework is free to choose traversal strategies and optimizations based on source characteristics. Therefore, **do not use a counter inside `tryAdvance`** to infer how many elements passed through `map` or how many the terminal operation definitely processed.

A pipeline with `limit` or `findFirst` can stop early without requesting traversal of the entire source. Conversely, operations like `sorted` may need to collect intermediate data. When designing a custom source, focus on a correct traversal contract before optimizing.

## 12. Full Example: RangeStringSpliterator with All Four Operations

The Java 17+ program below is a standalone implementation for a **cloned** string array, featuring `tryAdvance`, `forEachRemaining`, `trySplit`, `estimateSize`, and `characteristics`. It preserves index-based encounter order and can split the array into disjoint ranges.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.StreamSupport;

public class CustomSpliteratorDemo {
    static final class RangeStringSpliterator implements Spliterator<String> {
        private final String[] data;
        private int cursor;
        private final int fence;

        RangeStringSpliterator(String[] source) {
            this(Objects.requireNonNull(source, "source").clone(),
                    0, source.length);
        }

        private RangeStringSpliterator(
                String[] data, int origin, int fence) {
            this.data = data;
            this.cursor = origin;
            this.fence = fence;
        }

        @Override
        public boolean tryAdvance(Consumer<? super String> action) {
            Objects.requireNonNull(action, "action");

            if (cursor >= fence) {
                return false;
            }
            action.accept(data[cursor++]);
            return true;
        }

        @Override
        public void forEachRemaining(Consumer<? super String> action) {
            Objects.requireNonNull(action, "action");

            while (cursor < fence) {
                action.accept(data[cursor++]);
            }
        }

        @Override
        public Spliterator<String> trySplit() {
            int low = cursor;
            int mid = low + (fence - low) / 2;
            if (mid == low) {
                return null;
            }

            cursor = mid;
            return new RangeStringSpliterator(data, low, mid);
        }

        @Override
        public long estimateSize() {
            return fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED | IMMUTABLE;
        }
    }

    public static void main(String[] args) {
        String[] source = {"  An ", " Bình ", " Chi ", "Dũng"};

        // 1. Directly test traversing one element then the remainder.
        Spliterator<String> cursor =
                new RangeStringSpliterator(source);
        cursor.tryAdvance(name -> System.out.println("First: " + name));
        cursor.forEachRemaining(name -> System.out.println("After: " + name));
        System.out.println(cursor.estimateSize()); // 0

        // 2. Use a fresh Spliterator to create a sequential Stream.
        List<String> normalized = StreamSupport.stream(
                        new RangeStringSpliterator(source), false)
                .map(String::strip)
                .filter(name -> !name.isEmpty())
                .toList();
        System.out.println(normalized); // [An, Bình, Chi, Dũng]

        // 3. Run in parallel mode on a splittable source.
        List<String> parallel = StreamSupport.stream(
                        new RangeStringSpliterator(source), true)
                .map(String::strip)
                .toList();
        System.out.println(parallel); // [An, Bình, Chi, Dũng]

        // 4. Original source may change, but the array snapshot stays isolated.
        Spliterator<String> snapshot =
                new RangeStringSpliterator(source);
        source[0] = "Changed";
        System.out.println(StreamSupport.stream(snapshot, false)
                .map(String::strip).findFirst().orElseThrow()); // An
    }
}
```

**Key explanations:**

1. The package-private constructor (without `public`) **clones the array once**. Child splits share the same cloned array, differing only in cursor/fence, avoiding array copies on every split.
2. `tryAdvance` processes at most one element and returns `true` only when it has passed an element to the action.
3. `forEachRemaining` uses the **same cursor**, so it never repeats already-traversed elements.
4. `trySplit` returns a prefix of the untraversed portion and updates the current instance to hold the suffix.
5. `estimateSize` is always `fence - cursor` for each split; every split knows its exact size.
6. `characteristics` declares the true properties of the source. `NONNULL` is omitted because `null` values could exist inside the `String[]` array.
7. When using `StreamSupport.stream(..., true)`, the framework can split and run chunks in parallel, yet `toList` still preserves encounter order for an `ORDERED` source.

**Limitations:** This source holds the entire array in memory; the initial clone has `O(n)` cost. For very large arrays or data generated over time, you need a different source and resource lifecycle design rather than simply copying everything. The example also does not replace string validation if elements can be `null` and the pipeline calls `String::strip`.

## 13. Primitive Spliterators: Avoiding Boxing When Traversing Numbers

If a custom source contains only numbers, the `Spliterator.OfInt`, `Spliterator.OfLong`, and `Spliterator.OfDouble` interfaces provide primitive traversal operations and integrate with `IntStream`, `LongStream`, and `DoubleStream`.

```java
boolean tryAdvance(IntConsumer action);
void forEachRemaining(IntConsumer action);
```

Example `Spliterator.OfInt` for a sequence from `start` (inclusive) to `endExclusive` (exclusive):

```java
import java.util.Objects;
import java.util.Comparator;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

final class IntRangeSpliterator implements Spliterator.OfInt {
    private int cursor;
    private final int fence;

    IntRangeSpliterator(int start, int endExclusive) {
        if (start > endExclusive) {
            throw new IllegalArgumentException("start > endExclusive");
        }
        this.cursor = start;
        this.fence = endExclusive;
    }

    @Override
    public boolean tryAdvance(IntConsumer action) {
        Objects.requireNonNull(action, "action");
        if (cursor >= fence) return false;
        action.accept(cursor++);
        return true;
    }

    @Override
    public void forEachRemaining(IntConsumer action) {
        Objects.requireNonNull(action, "action");
        while (cursor < fence) action.accept(cursor++);
    }

    @Override
    public Spliterator.OfInt trySplit() {
        int low = cursor;
        int mid = low + (int) (((long) fence - low) / 2);
        if (mid == low) return null;
        cursor = mid;
        return new IntRangeSpliterator(low, mid);
    }

    @Override
    public long estimateSize() {
        return (long) fence - cursor;
    }

    @Override
    public int characteristics() {
        return ORDERED | SIZED | SUBSIZED | IMMUTABLE
                | NONNULL | DISTINCT | SORTED;
    }

    @Override
    public Comparator<? super Integer> getComparator() {
        return null; // SORTED in natural order.
    }
}

long total = StreamSupport.intStream(
        new IntRangeSpliterator(1, 5), false).asLongStream().sum();
System.out.println(total); // 10 (1+2+3+4)
```

This source has strictly increasing, non-repeating numbers in natural order, so the `DISTINCT` and `SORTED` bits are legitimately declared. When declaring `SORTED`, the class must implement `getComparator()` properly: returning `null` when using natural ordering. Without overriding it, `Spliterator.getComparator()`'s default implementation throws `IllegalStateException`, contradicting the declared characteristic. Operating on primitive `int` avoids boxing each element into `Integer`.

**Important:** This example should not be used instead of `IntStream.range(start, endExclusive)` when you just need a simple numeric range; the standard library already provides that source. Its purpose is to demonstrate implementing the methods with `IntConsumer` and valid characteristics for a primitive Spliterator.

## 14. Common Mistakes When Writing a Custom Spliterator

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `tryAdvance` returns `true` forever | Not advancing cursor or missing end condition | Advance cursor once per element and return `false` when exhausted |
| `tryAdvance` returns `false` yet still calls action | Broken exhaustion contract | Check exhaustion before calling `action.accept` |
| `forEachRemaining` repeats past elements | Restarting from index 0 instead of current cursor | Share the same progress state with `tryAdvance` |
| Missing elements when interleaving both methods | `forEachRemaining` uses a separate unsynchronized cursor | Use the same cursor/fence, not an independent loop state |
| Calling `trySplit` duplicates or skips elements | Two splits manage overlapping or gapped ranges | Split the **untraversed** part into disjoint ranges |
| Parallel Stream does not split | `trySplit()` always returns `null` | Implement splitting only when the source supports it soundly and it pays off |
| `count()` returns wrong number | Declared `SIZED` with inaccurate `estimateSize()` | Report exact remaining elements or omit `SIZED` |
| Inconsistent `NullPointerException` on null action | Validating action only when data remains | Call `Objects.requireNonNull(action)` at the top of the method |
| `String::strip` throws `NullPointerException` | Array contains null elements unhandled by pipeline | Filter `null` or validate source before transformation |
| Wrong data when source is mutated | Spliterator traverses mutable source without sync/snapshot | Clone, lock, or use a concurrent source with proper contract |
| Wrong data when multiple threads call same cursor | Allowing two threads to operate on one Spliterator instance | Keep separate state per split, never share a mutable cursor |
| `CONCURRENT`/`IMMUTABLE` declared arbitrarily | Mistaking characteristics for speedup flags | Only set characteristics backed by source guarantees |
| Calling `StreamSupport.stream` twice with same cursor | Spliterator is already consumed | Create a new Spliterator when re-traversing |

## 15. Practice Exercise

Given the data:

```java
String[] logs = {
        "OPEN",
        "FETCH",
        "PROCESS",
        "CLOSE",
        "ARCHIVE"
};
```

**Task 1 — tryAdvance:** Write `LogSpliterator` holding the array and a cursor. Each successful `tryAdvance` call emits only one log line and returns `true`; when exhausted, return `false`.

**Task 2 — forEachRemaining:** Override `forEachRemaining` to emit the exact remaining logs. Call `tryAdvance` twice, then `forEachRemaining`; expected output in order is `OPEN, FETCH` first, then `PROCESS, CLOSE, ARCHIVE`.

**Task 3 — size:** Implement `estimateSize` so that after two successful `tryAdvance` calls it reports `3`, and after `forEachRemaining` it reports `0`.

**Task 4 — characteristics:** Declare the proper characteristics for a privately cloned array traversed by index. Explain why `DISTINCT` or `SORTED` should not be attached by default.

**Task 5 — extension:** To support parallel processing, add `trySplit` producing two disjoint ranges; verify that merging results in encounter order yields all five elements with no duplicates or omissions.

### Reference solution for the three traversal methods

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;

final class LogSpliterator implements Spliterator<String> {
    private final String[] logs;
    private int cursor;

    LogSpliterator(String[] source) {
        logs = Objects.requireNonNull(source, "source").clone();
    }

    @Override
    public boolean tryAdvance(Consumer<? super String> action) {
        Objects.requireNonNull(action, "action");
        if (cursor == logs.length) return false;
        action.accept(logs[cursor++]);
        return true;
    }

    @Override
    public void forEachRemaining(Consumer<? super String> action) {
        Objects.requireNonNull(action, "action");
        while (cursor < logs.length) {
            action.accept(logs[cursor++]);
        }
    }

    @Override
    public Spliterator<String> trySplit() {
        return null; // Try adding this yourself in task 5.
    }

    @Override
    public long estimateSize() {
        return logs.length - cursor;
    }

    @Override
    public int characteristics() {
        return ORDERED | SIZED | SUBSIZED | IMMUTABLE;
    }
}

LogSpliterator cursor = new LogSpliterator(logs);
cursor.tryAdvance(System.out::println); // OPEN
cursor.tryAdvance(System.out::println); // FETCH
System.out.println(cursor.estimateSize()); // 3
cursor.forEachRemaining(System.out::println);
// PROCESS, CLOSE, ARCHIVE
System.out.println(cursor.estimateSize()); // 0
```

For the extension, refer to the `[origin, fence)` range-splitting approach in section 12. Do not mutate the `logs` array directly while a Stream is traversing it. When data may contain duplicate or unsorted elements, `DISTINCT` and `SORTED` would be false guarantees.

## 16. Self-Check Checklist Before Using a Custom Source

1. **Termination:** Does `tryAdvance` reliably return `false` once the source is exhausted?
2. **Single element:** Does every `true` return invoke the action for exactly one element?
3. **Cursor:** Does `forEachRemaining` start from the current position and stop at the end?
4. **Null:** Is `action == null` rejected immediately with `NullPointerException`?
5. **Splitting:** Does `trySplit` split only the untraversed portion into disjoint ranges?
6. **Size:** Does `estimateSize` reflect the remaining count? If `SIZED`/`SUBSIZED` are set, is it exact after every operation?
7. **Characteristics:** Are `ORDERED`/`IMMUTABLE`/`NONNULL`/`SORTED` truly accurate for the source and each split?
8. **Resources:** If the source is backed by a file/stream/connection, is there an appropriate resource-closing policy via `onClose` or `try-with-resources`?
9. **Parallelism:** Does each split maintain its own state, and is the underlying data stable enough for traversal?
10. **Testing:** Have you tested empty sources, single-element sources, interleaving both methods, calling after exhaustion, splitting after advancing, and actions throwing exceptions?

For sources with a resource lifecycle, merely returning `false` when no elements remain does not always release the file or connection. If you build a Stream from an I/O-backed Spliterator, design an explicit closing mechanism and use `try-with-resources` at the call site.

## Remember

`tryAdvance(action)` is the traversal operation for **at most one element**: it returns `true` after passing one element to the action, and returns `false` when the source is exhausted without calling the action again. `forEachRemaining(action)` processes **all untraversed elements**, and can usually rely on the default implementation that repeatedly calls `tryAdvance`; override it only when there is a clear benefit, and ensure it shares the same cursor state.

To use a Spliterator as a Stream source, besides the two traversal methods you also need to properly define `trySplit`, `estimateSize`, and `characteristics`. All split ranges must be non-overlapping; characteristics such as `SIZED`, `ORDERED`, or `IMMUTABLE` must reflect the source's true contract. Prioritize **correct traversal with no lost or duplicated elements** before optimizing `forEachRemaining` or parallelizing via `StreamSupport`.
