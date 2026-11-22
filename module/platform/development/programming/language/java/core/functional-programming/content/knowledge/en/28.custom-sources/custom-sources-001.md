# Spliterator and the Role of Traversing or Splitting Sources in Java Streams

When using `list.stream()`, `Arrays.stream(array)`, or `IntStream.range(...)`, Java already provides a way to traverse data for a Stream. However, if the data source is a custom-designed structure—such as a numeric range, a segmented record set, a tree structure, a data block, or a sequential reading API—we need to understand **`Spliterator`**: the interface that helps a Stream **traverse elements** and, when possible, **split the source into independent parts for parallel processing**.

`Spliterator` is an abbreviation suggestive of *splittable iterator*. A spliterator describes **the set of elements remaining to be traversed**, providing operations to get the next element, estimate the number of remaining elements, and split off part of the work into another spliterator. It is a key input component in the Stream mechanism, but it **does not automatically turn every source into an efficient parallel source**.

~~~text
Custom source: [1, 2, 3, 4, 5, 6, 7, 8]
                  |
                  v
           Spliterator.OfInt
                  |
        trySplit()| 
          +-------+-------+
          |               |
      [1,2,3,4]       [5,6,7,8]
          |               |
       task A           task B
          +-------+-------+
                  |
             combine
                  |
       Stream terminal result
~~~

Key skills in this lesson: understanding `tryAdvance()`, `forEachRemaining()`, `trySplit()`, `estimateSize()`, **characteristics**, how to create a Stream using `StreamSupport`, and how to test a custom Spliterator.

## 1. How do `Iterator` and `Spliterator` differ?

`Iterator<T>` primarily provides `hasNext()` and `next()` to read elements one by one. `Spliterator<T>` combines traversal capability with **the ability to split the source into chunks of work**, giving the Stream framework the option of parallel execution.

| Aspect | `Iterator<T>` | `Spliterator<T>` |
| --- | --- | --- |
| Element-by-element traversal | `hasNext()` + `next()` | `tryAdvance(action)` |
| Traversing all remaining elements | Loop, `forEachRemaining` | `forEachRemaining(action)` |
| Splitting work into parts | No standard API | `trySplit()` |
| Estimating remaining elements | No general method | `estimateSize()` |
| Declaring source characteristics | No standard flag set | `characteristics()` |
| Serving parallel Streams | Requires adapter/buffering mechanism | API used directly by Stream |

Do not infer that `Spliterator` is always faster than `Iterator`. Its core advantage is **describing enough information so that Stream can decide the traversal and work-splitting strategy**.

A standard collection typically provides `collection.spliterator()`. When calling `collection.stream()` or `collection.parallelStream()`, Java can use the source's Spliterator as input. For a custom source that is not a Collection, we can create a Spliterator object directly and pass it to `StreamSupport`.

## 2. Core Methods

### `boolean tryAdvance(Consumer<? super T> action)`

`tryAdvance` attempts to pass **exactly one** remaining element to `action`:

- Returns `true` if an element was processed.
- Returns `false` if there are no elements left to traverse.
- After returning `false` due to exhausting the source, subsequent calls must not re-emit already traversed elements.
- `action` must not be `null`; proper implementations typically check `Objects.requireNonNull(action)`.

Example:

~~~java
Spliterator<String> sp = List.of("A", "B").spliterator();

boolean first = sp.tryAdvance(System.out::println); // prints A, returns true
boolean second = sp.tryAdvance(System.out::println); // prints B, returns true
boolean third = sp.tryAdvance(System.out::println); // returns false
~~~

This is an **illustrative snippet** inside a method, requiring imports for `List` and `Spliterator`. `tryAdvance` is an operation that **consumes traversal state**; do not call it to "peek" if you still expect the Stream to start from the first element.

### `void forEachRemaining(Consumer<? super T> action)`

Traverses all remaining elements, passing each element to `action`. The default implementation can be understood conceptually as:

~~~java
// Logic illustration, not JDK source code:
while (tryAdvance(action)) {
    // Processed one more element.
}
~~~

If `tryAdvance` has already been called once, `forEachRemaining` only traverses the elements that **have not yet been consumed**.

### `Spliterator<T> trySplit()`

Attempts to split off an element or a subset of **untraversed** elements into another Spliterator. Returns `null` when it cannot or does not want to split further. After a successful split, the two Spliterators must cover **disjoint** subsets of data, and combined they must represent exactly all the elements remaining before the split.

For an ordered source, a correct `trySplit` usually returns a **prefix** of the remaining elements; the original Spliterator continues managing the **suffix**. An exact 50–50 split is not required in every case, but reasonably balanced parts make parallel processing more effective.

### `long estimateSize()`

Returns an **estimate** of the number of remaining elements. If unknown or if the number of elements may be unbounded, it can return `Long.MAX_VALUE`. If the `SIZED` characteristic is declared, this value must satisfy the exact size guarantee under the corresponding contract, not merely a rough guess.

### `int characteristics()` and `hasCharacteristics(int flags)`

`characteristics()` returns a bitmask of flags representing actual properties of the source and traversal. `hasCharacteristics(mask)` checks whether all requested bits are set:

~~~java
boolean ordered = sp.hasCharacteristics(Spliterator.ORDERED);
boolean sized = sp.hasCharacteristics(Spliterator.SIZED);
~~~

Over-declaring flags is a **contract violation**: the Stream framework may use that information to optimize and produce incorrect results when flags are declared inaccurately.

## 3. `trySplit()` is a source-splitting mechanism, not thread execution

An important point: **`trySplit` does not create threads itself, does not launch `parallelStream` itself, and does not invoke terminal operations itself**. It only divides **the right to traverse the remaining elements** between two Spliterators. The Stream framework decides whether to request a split, how many times to split, and which tasks receive which parts.

For the integer range `[1, 9)` (inclusive of 1, exclusive of 9):

~~~text
Initially:
  spliterator: [1,2,3,4,5,6,7,8]

Call trySplit():
  returned prefix: [1,2,3,4]
  original suffix: [5,6,7,8]

Call trySplit() on original again, if possible:
  returned prefix: [5,6]
  original suffix: [7,8]
~~~

**Correctness first:** every element belongs to exactly one branch, with no element lost or emitted twice. **Optimization second:** branches have reasonable sizes so processing costs are balanced, avoiding creating countless tiny branches if splitting is expensive.

If `trySplit` always returns `null`, the source **can still be used with Stream**, even when `parallel=true` is requested; however, work-splitting capability is limited and actual parallelism may be low. Conversely, `trySplit` returning non-null does not guarantee that the JVM has enough cores or that performance will benefit.

### Do not split already traversed parts

Suppose the source has `[3,4,5,6]` remaining after the first two elements have passed through `tryAdvance`. At that point `trySplit` may only split the **remaining part**, without reclaiming `1,2`. Splitting incorrectly will produce duplicate records or lose data during parallel collection.

## 4. Characteristics to Know

The flags are defined in `java.util.Spliterator`:

| Flag | Primary Guarantee | Typical Scenario |
| --- | --- | --- |
| `ORDERED` | Elements have a defined encounter order | List, ascending numeric range |
| `DISTINCT` | No two elements are equivalent according to `equals` | Source guaranteeing unique values |
| `SORTED` | Encounter order is a defined sort order | Ascending numeric source |
| `SIZED` | Exact number of remaining elements is known under contract conditions | Array, finite numeric range |
| `SUBSIZED` | All Spliterators produced after splitting also have `SIZED` and `SUBSIZED` | Splitting array/range indices accurately |
| `NONNULL` | Does not emit `null` elements | `int`, source guaranteeing non-null |
| `IMMUTABLE` | Source cannot be structurally modified during traversal | Numeric sequence computed from fixed bounds |
| `CONCURRENT` | Source allows concurrent modification during traversal per the corresponding contract | Certain concurrent structures |

These are **guarantees of the source**, not an arbitrary request to "turn on optimizations." When designing a custom Spliterator, only declare flags that can be proven.

### `ORDERED` vs. `SORTED`

`ORDERED` only states that there is a meaningful element encounter order. For example, `["C", "A", "B"]` has a clear order but is **not** sorted alphabetically.

`SORTED` is stronger: elements are traversed in a declared sort order. By specification, `SORTED` implies `ORDERED`; if a custom source declares `SORTED`, `getComparator()` must be implemented properly:

- Return `null` if using natural ordering.
- Return the comparator if using a custom ordering.
- If `SORTED` is not present, `getComparator()` must throw `IllegalStateException` per the contract.

Do not attach `SORTED` to a source that only "occasionally" produces ascending data. If elements might appear out of order, you must drop the flag or fix the data generation algorithm.

### `DISTINCT` relates to `equals`, not comparator

A Spliterator has `DISTINCT` when no two elements are equal according to `equals`. For an integer source from 1 to 8, this condition holds. For records with the same ID but different versions, they may **not be equal according to `equals`**, even if business logic treats the same ID as one item; the equality contract must be clearly determined.

### `IMMUTABLE` does not mean traversal state cannot change

A Spliterator needs to increment a `cursor` pointer while traversing. That **does not contradict `IMMUTABLE`**: this flag states that **the underlying data source structure is not modified**, not that internal traversal positions cannot be updated. For example, a numeric range defined by two immutable bounds has no backing collection to which elements can be added or removed.

### `Spliterator.CONCURRENT` is not `Collector.Characteristics.CONCURRENT`

`Spliterator.CONCURRENT` describes a **source** property regarding concurrent structural modifications; `Collector.Characteristics.CONCURRENT` describes the **accumulator**'s ability to accept concurrent updates to the same container. The two flags belong to different interfaces and **cannot be used interchangeably**.

Do not declare `CONCURRENT` on a regular `ArrayList` source to "fix" the list being modified from another thread. Likewise, do not arbitrarily attach `IMMUTABLE` when elements can still be added to or removed from the source unexpectedly.

## 5. `SIZED`, `SUBSIZED`, and Splitting Cost

`SIZED` indicates that a Spliterator can report the **exact size** of the remaining elements under the contract's assumptions. `SUBSIZED` indicates that after splits, the child Spliterators **also** retain the `SIZED`/`SUBSIZED` characteristics.

Example with numeric source 1–8:

~~~text
Before traversal: estimateSize() = 8
After tryAdvance one element: estimateSize() = 7

Splitting a fresh source 1..8:
  prefix [1..4]: estimateSize() = 4
  suffix [5..8]: estimateSize() = 4
  Total size = 8
~~~

An exact size can help the framework **distribute tasks, allocate buffers, and optimize appropriate terminal operations**. However, `estimateSize` is not a requirement forcing the framework to call `trySplit` until each branch has exactly one element.

A source reading a network file, continuously growing data, or an iterator without information about the remaining element count should not declare `SIZED`. For a source of unknown size, it can return `Long.MAX_VALUE` and omit `SIZED/SUBSIZED`. Fabricating an exact size to make a Stream "run faster" can lead to logic bugs or errors when the framework trusts the metadata.

`getExactSizeIfKnown()` is a convenience method: if the Spliterator has `SIZED`, it can return the exact size; otherwise, it returns `-1`. Do not confuse this method with `estimateSize()`—the latter can still return an estimate when the exact size is unknown.

## 6. Java 17+ Example: Writing a Custom `Spliterator.OfInt` for a Numeric Range

To avoid boxing when traversing integers, Java provides primitive specializations:

- `Spliterator.OfInt`: uses `IntConsumer` and `IntStream`.
- `Spliterator.OfLong`: uses `LongConsumer` and `LongStream`.
- `Spliterator.OfDouble`: uses `DoubleConsumer` and `DoubleStream`.

A complete example is `RangeSpliterator`, which traverses numbers from `startInclusive` to `endExclusive - 1`, knows the exact size, and splits at the midpoint.

Save file **`SpliteratorSourceDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class SpliteratorSourceDemo {
    static final class RangeSpliterator implements Spliterator.OfInt {
        private int cursor;
        private final int fence;

        RangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("start > end");
            }
            this.cursor = startInclusive;
            this.fence = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (cursor >= fence) {
                return false;
            }
            action.accept(cursor++);
            return true;
        }

        @Override
        public OfInt trySplit() {
            int remaining = fence - cursor;
            if (remaining <= 1) {
                return null;
            }
            int midpoint = cursor + remaining / 2;
            OfInt prefix = new RangeSpliterator(cursor, midpoint);
            cursor = midpoint;
            return prefix;
        }

        @Override
        public long estimateSize() {
            return (long) fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | DISTINCT | SORTED | SIZED | SUBSIZED
                    | NONNULL | IMMUTABLE;
        }

        @Override
        public Comparator<? super Integer> getComparator() {
            return null; // Natural ascending order
        }
    }

    public static void main(String[] args) {
        Spliterator.OfInt probe = new RangeSpliterator(1, 9);
        System.out.println("estimatedBefore=" + probe.estimateSize());
        probe.tryAdvance((int n) -> System.out.println("first=" + n));
        System.out.println("estimatedAfter=" + probe.estimateSize());

        Spliterator.OfInt remainder = new RangeSpliterator(1, 9);
        Spliterator.OfInt prefix = remainder.trySplit();
        System.out.println("prefixSize=" + prefix.estimateSize());
        System.out.println("remainderSize=" + remainder.estimateSize());
        System.out.println("prefix="
                + StreamSupport.intStream(prefix, false).boxed().toList());
        System.out.println("remainder="
                + StreamSupport.intStream(remainder, false).boxed().toList());

        System.out.println("parallelSquares="
                + StreamSupport.intStream(new RangeSpliterator(1, 9), true)
                    .map(n -> n * n).sum());
        System.out.println("parallelOrdered="
                + StreamSupport.intStream(new RangeSpliterator(1, 9), true)
                    .boxed().toList());
        Spliterator.OfInt flags = new RangeSpliterator(1, 9);
        System.out.println("ordered=" + flags.hasCharacteristics(Spliterator.ORDERED));
        System.out.println("sized=" + flags.hasCharacteristics(Spliterator.SIZED));
        System.out.println("subsized=" + flags.hasCharacteristics(Spliterator.SUBSIZED));
        System.out.println("naturalComparator=" + (flags.getComparator() == null));
    }
}
~~~

Test commands with JDK 17+:

~~~bash
javac SpliteratorSourceDemo.java
java SpliteratorSourceDemo
~~~

**Exact stdout:**

~~~text
estimatedBefore=8
first=1
estimatedAfter=7
prefixSize=4
remainderSize=4
prefix=[1, 2, 3, 4]
remainder=[5, 6, 7, 8]
parallelSquares=204
parallelOrdered=[1, 2, 3, 4, 5, 6, 7, 8]
ordered=true
sized=true
subsized=true
naturalComparator=true
~~~

Explanation:

1. `RangeSpliterator(1, 9)` represents the sequence 1 through 8, having eight values, so `estimateSize()` is initially 8.
2. `tryAdvance` delivers element `1` to the action and updates the cursor; seven values remain.
3. `trySplit` on a fresh source splits it into a returned part `[1,2,3,4]` and a remaining original part `[5,6,7,8]`. Each side reports a size of 4.
4. `StreamSupport.intStream(prefix, false)` creates a sequential Stream from the prefix branch; similarly for the suffix branch. After consuming a branch, do not reuse that object to build another Stream.
5. `StreamSupport.intStream(new RangeSpliterator(1,9), true)` requests a parallel pipeline. The sum of squares of 1..8 is `204`.
6. `parallelOrdered` shows that after parallel processing, `toList()` still preserves encounter order because the Spliterator declares and properly implements `ORDERED`.
7. `getComparator() == null` is correct for a `SORTED` Spliterator using **natural ordering**; it does not mean "unsorted."
8. The example does not declare `CONCURRENT`: the `cursor` pointer is not designed for multiple threads to simultaneously call `tryAdvance` on **a single Spliterator**. The framework can assign the split Spliterators to separate tasks.

In this demonstration version, the range size is small for easy observation; for extremely large `int` ranges, the `fence - cursor` operation computed in `int` can overflow **before** being assigned to `remaining`. Therefore, **do not apply this `int remaining` splitting algorithm verbatim to arbitrary `int` bound pairs separated by more than `Integer.MAX_VALUE`**. If building a production source that needs to support the full value domain, compute the distance using `long` and redesign the splitting/estimation logic accordingly. The `SIZED/SUBSIZED` characteristics may only be declared when the implementation genuinely satisfies the bounds of the supported domain.

## 7. Understanding `tryAdvance()` and `trySplit()` Code in Detail

### Cursor and fence are two kinds of state

`cursor` changes after each traversed element, while `fence` fixes the right boundary. The termination condition is `cursor >= fence`. Zero elements can be traversed if `startInclusive == endExclusive`.

Checking that `action` is non-null avoids passing a `null` consumer into the pipeline. If the action throws an exception, the exception can propagate to the caller; the Spliterator should not swallow exceptions because that would hide processing errors. Do not assume action calls occur on the same thread in a parallel Stream.

### Return prefix, keep suffix

In `trySplit`:

~~~java
int midpoint = cursor + remaining / 2;
OfInt prefix = new RangeSpliterator(cursor, midpoint);
cursor = midpoint;
return prefix;
~~~

This is an **excerpt from the full program**, with the `remaining` variable already computed. Upon returning, `prefix` owns `[old_cursor, midpoint)`; the current object owns `[midpoint, fence)`. The two branches do not overlap.

If 0 or 1 element remains, the algorithm returns `null` because splitting further is pointless. For special sources with high splitting overhead, a higher threshold can be chosen, as long as elements are neither lost nor duplicated.

### Do not let two Spliterators share a cursor

A common mistake when implementing your own:

~~~java
// ANTI-PATTERN: both branches reference the same mutable Iterator.
// trySplit() returns a wrapper reading the shared iterator,
// while the original Spliterator still reads that same iterator.
~~~

If the two branches do not have independent ownership ranges, they can contend for elements, emit out of order, or cause races. Returning another Spliterator does not automatically mean **data has actually been split**. Access to the source data must be designed to be non-overlapping.

## 8. `StreamSupport`: Bringing a Spliterator into the Stream API

Common Stream creation methods:

~~~java
Stream<T> stream = StreamSupport.stream(spliterator, false);
Stream<T> parallel = StreamSupport.stream(spliterator, true);
IntStream primitive = StreamSupport.intStream(intSpliterator, true);
~~~

This is **illustrative syntax**, requiring imports for `StreamSupport`, `Stream`, `IntStream`, and appropriate Spliterator variables. The boolean parameter:

- `false` requests a sequential Stream.
- `true` requests a parallel Stream.
- Requesting parallel **does not** guarantee the JVM will use multiple tasks or run faster.

There are two main forms of `StreamSupport.stream`: one takes an existing Spliterator; the other takes a **Supplier<? extends Spliterator<T>>** along with characteristics and the parallel flag.

Example of creating a fresh Spliterator when the terminal operation starts:

~~~java
Stream<Integer> numbers = StreamSupport.stream(
        () -> new RangeSpliterator(1, 9),
        Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED
            | Spliterator.DISTINCT | Spliterator.SORTED
            | Spliterator.NONNULL | Spliterator.IMMUTABLE,
        false
).boxed(); // Wrong type if using StreamSupport.stream for OfInt.
~~~

**The snippet above intentionally illustrates an overload selection error**: `StreamSupport.stream` creates a `Stream<T>`, which does not have `boxed()`. For a `Spliterator.OfInt` source, you must call **`StreamSupport.intStream`**. The correct way to write it:

~~~java
IntStream numbers = StreamSupport.intStream(
        () -> new RangeSpliterator(1, 9),
        Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED
            | Spliterator.DISTINCT | Spliterator.SORTED
            | Spliterator.NONNULL | Spliterator.IMMUTABLE,
        false
);
~~~

This is an **illustrative snippet** using the `RangeSpliterator` class from the full program and importing `IntStream`, `Spliterator`, and `StreamSupport`. Here, the source is only obtained when the terminal operation begins executing (*late binding* via the Supplier overload). The characteristic bits declared to the Supplier must **match the actual characteristics** of the Spliterator returned by the Supplier; you must not claim the source has `SIZED` if it does not.

The benefit of the Supplier overload is reducing the risk of source modification between **Stream construction** and **terminal execution start**, especially when the corresponding Spliterator does not have `IMMUTABLE` or `CONCURRENT` and is not late-binding. However, it does not make a mutable source thread-safe.

### Do not reuse a Spliterator already consumed by a Stream

~~~java
Spliterator.OfInt sp = new RangeSpliterator(1, 5);
long count = StreamSupport.intStream(sp, false).count();
// Do not reuse sp as a fresh source expecting to read all of 1..4.
~~~

A Stream can only be used for one terminal operation. Furthermore, **do not manually traverse a Spliterator after passing it to a Stream** and expect the Stream to still see all the data. To run multiple independent computations, create a new Spliterator from a replayable source, or use an appropriate summarizing terminal operation.

## 9. Iterator Adapter and Unknown-Size Sources

Not every source is easy to split by index. If you only have an `Iterator<T>`, Java provides a utility:

~~~java
Iterator<String> iterator = List.of("A", "B", "C").iterator();

Spliterator<String> sp = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED
);

List<String> result = StreamSupport.stream(sp, false).toList();
// [A, B, C]
~~~

This is a snippet **that can be placed inside a method** with imports `Iterator`, `List`, `Spliterator`, `Spliterators`, and `StreamSupport`. The adapter does not know the total size upfront; therefore, `SIZED/SUBSIZED` must not be arbitrarily attached. For a sequential iterator source, parallel splitting capability may require **pre-reading and buffering** in batches or may be less efficient than a source with independently splittable index ranges.

If a source is streaming network/file data or has side effects, you must also manage **resource closing**, emission rate, and I/O errors. Spliterator does not automatically replace `try-with-resources` or underlying resource closing mechanisms.

### Infinite stream scenarios

`Spliterator` can represent an unbounded source, but without a stopping condition, terminal operations like `toList()` will not terminate finitely. Moreover, a source without a finite size must not declare `SIZED`. A pipeline such as `limit(n)` can bound the data, though the impact of other stateful operations preceding it still needs to be considered.

## 10. Ordering, Parallelism, and Terminal Operations

`ORDERED` means the source defines an encounter order, but it **does not guarantee that every terminal operation executes side effects in that exact order**.

~~~java
// May print out of order:
StreamSupport.intStream(new RangeSpliterator(1, 9), true)
        .forEach(System.out::println);
~~~

Parallel `forEach` does not promise the order in which the action is invoked. Conversely:

~~~java
// Preserves the source's encounter order:
StreamSupport.intStream(new RangeSpliterator(1, 9), true)
        .forEachOrdered(System.out::println);
~~~

`forEachOrdered` requires the action to be executed in encounter order, but it can increase coordination overhead and should not be used as the default solution to build a list via side effects. If you need a result List, `boxed().toList()` or an appropriate collector is usually clearer in intent.

**Similarly:** a `SORTED` Spliterator does not guarantee that a parallel `forEach` operation will automatically print in order; `SORTED` describes a sorted encounter order, whereas `forEach` is not an order-preserving terminal operation. Distinguish between **the logical order of elements** and **the temporal order in which callbacks run on threads**.

### Declaring `SIZED` can affect pipeline execution

Some terminal operations like `count()` can use size information when the pipeline does not change the element count, instead of executing `tryAdvance` for each element. Therefore, **do not place mandatory side effects** inside `peek()` or during element emission expecting every terminal operation to definitely read through all values. Accurate metadata is part of the contract that enables valid optimizations.

## 11. Common Mistakes When Implementing Your Own

**Not advancing the cursor in `tryAdvance`.** If returning true without updating state, the terminal operation may receive the same element forever or run infinitely.

**Returning false too early.** If elements remain and false is returned, the Stream will assume the source has ended and silently lose data.

**`trySplit` creating overlapping data segments.** Two branches emitting some of the same records cause incorrect counts and reductions; the bug may only surface when running in parallel.

**`trySplit` failing to update the remaining part of the original Spliterator.** If a prefix is returned while the original still retains the entire source, values in the prefix are emitted twice.

**Declaring `SIZED` with an inaccurate count.** Optimizations based on wrong metadata can produce wrong results. For sources that can generate new data, the flag policy must be reviewed.

**Declaring `SUBSIZED` when children do not maintain exact sizes.** This flag is a contract applying to *all branches after splitting*, not just the root Spliterator.

**Declaring `SORTED` when data is not properly ordered.** The framework may skip a valid sort step based on false information, leaving the output unsorted as requested.

**Declaring `CONCURRENT` to fix races.** `CONCURRENT` describes a source guarantee; it does not automatically synchronize a collection or cursor. If a mutable source lacks synchronization, fix the design before choosing flags.

**Not handling `getComparator()` properly when `SORTED` is present.** For a natural-order sorted Spliterator return `null`; if a custom comparator is used, return the right comparator. If `SORTED` is absent, per contract the method must not report a comparator as if the source were sorted.

**Calling `spliterator()` and manually invoking `tryAdvance` before passing it to a Stream.** The Stream will only see the remainder from the advanced cursor; if unintended by the caller, leading elements are missing from the result.

**Using `StreamSupport.stream` instead of `intStream` for a primitive Spliterator.** Easily leads to boxing, wrong type inference, or attempting to call APIs that do not exist on `Stream<T>`.

**Splitting into too many tiny tasks.** Splitting millions of Spliterators just to perform a simple addition can incur more overhead than running sequentially; choose an appropriate partitioning strategy.

**Failing to close source resources.** For files or network connections, building a Stream does not automatically guarantee resources are closed when the terminal completes; an API with a close mechanism and `try-with-resources` management is needed when appropriate.

## 12. Proper Testing: Sequential, Parallel, and Post-Split State

A reliable custom Spliterator should have the following tests:

1. **Sequential traversal from start to finish:** no missing/duplicate elements; calling `tryAdvance` after exhaustion returns false.
2. **Partial traversal then remaining traversal:** call `tryAdvance` a few times, then `forEachRemaining`; combined results remain complete and in order if `ORDERED` is present.
3. **Single and multiple splits:** merging elements from all branches has no duplicates/omissions; for an ordered source, prefix/suffix combine in exact encounter order.
4. **Size:** before/after traversal and after splits, `estimateSize` is accurate with `SIZED`; if `SUBSIZED` is present, all children are accurate too.
5. **Characteristics:** `ORDERED`, `SORTED`, `DISTINCT`, `NONNULL`, `IMMUTABLE`, etc. are only declared if actually satisfied; `getComparator` follows the contract.
6. **Boundary inputs:** empty range, single element, odd/even element counts, near numeric type limits, invalid parameters.
7. **Sequential/parallel StreamSupport:** compare value sets, sums, element counts, and ordered results across both modes.
8. **Sources with side effects/IO:** test error handling, resource lifecycle, and no unexpected eager evaluation of the source.

A small data check after `trySplit`:

~~~java
Spliterator.OfInt whole = new RangeSpliterator(1, 9);
Spliterator.OfInt firstHalf = whole.trySplit();

List<Integer> a = StreamSupport.intStream(firstHalf, false).boxed().toList();
List<Integer> b = StreamSupport.intStream(whole, false).boxed().toList();

// a = [1,2,3,4], b = [5,6,7,8] with this implementation.
~~~

This is an illustrative snippet using the class from the full program and importing `List`, `Spliterator`, and `StreamSupport`. Do not attempt to reuse `whole` or `firstHalf` after terminal operations have consumed them.

**In summary:** Spliterator is the **source access contract** for Stream: `tryAdvance` traverses elements, `trySplit` partitions untraversed elements, and `estimateSize`/`characteristics` help the framework plan and optimize. A custom source only runs correctly and efficiently when **splits are non-overlapping, the cursor advances accurately, metadata is honest, and concurrency boundaries are clearly designed**. Passing `parallel=true` only requests parallel mode; it cannot fix a broken Spliterator or automatically guarantee performance.