# Spliterator.estimateSize() and Exact Size When Known in Java

## 1. Why Does the Size of a Stream Source Matter?

When writing a **custom data source for a Java Stream**, simply providing elements one by one is not enough. The Stream framework also needs to know **how many elements might remain** to decide how to split work, allocate space for results, and, in some pipelines, compute results without traversing every element.

The `java.util.Spliterator<T>` interface—short for *splitable iterator*—has two directly related methods:

~~~java
long estimateSize();
long getExactSizeIfKnown();
~~~

These are **API signatures for reference**, not two methods to declare at the file level. `estimateSize()` is a method that a Spliterator must provide; `getExactSizeIfKnown()` has a default implementation in the interface.

They answer two **different** questions:

- **`estimateSize()`:** "How many elements do I estimate might be encountered if I continue traversing this Spliterator?"
- **`getExactSizeIfKnown()`:** "According to the Spliterator's characteristic contract, am I allowed to assert the exact number of remaining elements?"

Example with an immutable `List` containing four elements:

~~~java
Spliterator<Integer> sp = List.of(10, 20, 30, 40).spliterator();

System.out.println(sp.estimateSize());          // 4
System.out.println(sp.getExactSizeIfKnown());   // 4
~~~

This snippet requires importing `java.util.List` and `java.util.Spliterator`, placed inside a method. For this List's Spliterator, the `SIZED` characteristic is declared and the size 4 is known exactly.

Conversely, a source reading incrementally from an iterator, file, socket, or generator may not know how many elements remain, even if it will eventually terminate. In that case `estimateSize()` **is not an exact guarantee**, and `getExactSizeIfKnown()` usually returns `-1`.

**Lesson goal:** accurately understand the contract of `estimateSize()`, the `SIZED`/`SUBSIZED` characteristics, changes after `tryAdvance()` and `trySplit()`, how to create a Stream from a custom Spliterator, and the consequences of declaring an inaccurate size.

## 2. Role of Spliterator in Custom Sources

A `Spliterator<T>` combines two capabilities:

1. **Traversal**: sequentially providing elements to an action via `tryAdvance(Consumer)` or `forEachRemaining(Consumer)`.
2. **Partitioning**: when possible, splitting part of the source into another Spliterator via `trySplit()` for potential parallel processing.

In addition, a Spliterator exposes:
- `estimateSize()`: estimates the number of remaining elements.
- `characteristics()`: bits describing the source and element properties, such as `ORDERED`, `SIZED`, `SUBSIZED`.
- `getExactSizeIfKnown()`: exact value if `SIZED` is declared; otherwise `-1` by default.
- `hasCharacteristics(flags)`: checks the requested characteristic bits.

This can be visualized as:

~~~text
Custom source: number sequence 0,1,2,3,4,5,6,7
                     |
            IntRangeSpliterator
       current=0, fence=8, size=8
                /         \
       trySplit()         remainder
          |                    |
      [0,1,2,3]           [4,5,6,7]
      size=4                size=4
          \                    /
           Stream can split work
                      |
                 terminal op
~~~

This is a model of splitting a source into two halves, **not a guaranteed thread schedule**. The important part is that the element counts of the two Spliterators after splitting must **match the element count before splitting** when `SUBSIZED` is declared.

### 2.1. How does Spliterator differ from Iterator?

`Iterator<T>` primarily provides `hasNext()` and `next()` for sequential traversal. It has no general contract requiring knowledge of the remaining size and provides no source-splitting method equivalent to `trySplit()`.

`Spliterator<T>` can:
- Traverse sequentially via `tryAdvance`.
- Split the source into independent Spliterators suitable for parallel processing.
- Declare metadata about ordering, uniqueness, size, immutability, etc.
- Help the framework optimize operations that only need counts or source partitioning.

Not every Spliterator is splittable: `trySplit()` is allowed to return `null` when no reasonable part remains to split or due to source characteristics.

## 3. What does estimateSize() actually promise?

Signature:

~~~java
long estimateSize();
~~~

Per the Java SE 17 API, the method returns an **estimate of the number of elements** that would be encountered by traversing all remaining elements, or returns `Long.MAX_VALUE` if the source is infinite, unknown, or too expensive to compute.

Three scenarios:

| Source/Spliterator | `estimateSize()` may be | Necessarily exact? |
| --- | --- | --- |
| Stable List declared SIZED | 4 if 4 elements remain | Yes, under SIZED contract conditions |
| Custom finite int range with clear current/fence | `fence - current` | Yes, if implementation and characteristics are accurate |
| Iterator with no declared size | `Long.MAX_VALUE` | No; this is a sentinel for "unknown" |
| Source that may change without size guarantee | An estimated number | Should not be treated as an exact count |
| Truly infinite source | `Long.MAX_VALUE` | Not an exact finite count |

Note: **an estimate is useful even when not exact**. A parallel framework can use the estimate to weigh splitting work. However, an estimate is not proof that exactly that many elements exist and does not automatically turn into a promise of speed.

### 3.1. "Remaining," not initial total

If a Spliterator has eight elements and we have successfully retrieved one element via `tryAdvance()`, logically only seven elements remain. For a custom Spliterator declared `SIZED/SUBSIZED` that updates its cursor accurately, `estimateSize()` must reflect the remaining element count, not stay at eight forever.

Design example:

~~~java
// Logic example inside a custom Spliterator:
public long estimateSize() {
    return (long) fence - current;
}
~~~

This is a **method fragment placed inside a class**, not a standalone program. `fence` is the **exclusive** ending index, and `current` is the index of the next element to be supplied.

If `current=5` and `fence=8`, the remaining size is 3, even though the original source may once have had 8 elements.

### 3.2. Long.MAX_VALUE is not a real count

When the size is unknown, the API allows:

~~~java
return Long.MAX_VALUE;
~~~

This is an **example return expression inside the estimateSize() method**. The value `9_223_372_036_854_775_807` is used as an **unknown/infinite/too expensive** signal, not meaning the Stream will actually create over nine quintillion elements.

Strictly avoid:

~~~java
// ANTI-PATTERN: do not treat estimateSize as a proven array size.
// int capacity = (int) spliterator.estimateSize();
// Object[] output = new Object[capacity];
~~~

It can overflow when casting `long` to `int`, allocate absurdly, or use an inaccurate estimate. If an exact size is needed, check `getExactSizeIfKnown()` and handle the `-1` case; even when the element count is known, memory/allocation limits still need to be checked.

## 4. SIZED — when is a size considered exact?

`Spliterator.SIZED` is a **characteristic flag**. It states that the element count reported by the Spliterator is **exact under the applicable contract conditions**, typically prior to traversal/splitting and when the source is not improperly interfered with.

Characteristic constants are combined using bitwise OR:

~~~java
int flags = Spliterator.ORDERED
        | Spliterator.SIZED
        | Spliterator.SUBSIZED
        | Spliterator.IMMUTABLE
        | Spliterator.NONNULL;
~~~

This illustrative snippet requires importing `java.util.Spliterator`.

You should not mark `SIZED` merely because of a **rough guess** or because you know the size of an array different from what the source actually provides. To declare `SIZED`, the implementation must ensure the value matches the elements that will be traversed per the contract.

### 4.1. getExactSizeIfKnown() relies on SIZED, not luck

The default implementation in the interface is semantically equivalent to:

~~~java
default long getExactSizeIfKnown() {
    return (characteristics() & SIZED) == 0 ? -1L : estimateSize();
}
~~~

This is an **illustration of the default method in Spliterator**; `SIZED` is a constant on the interface itself.

Consequences:

- If `SIZED` **is present**, `getExactSizeIfKnown()` calls `estimateSize()` and returns that value.
- If `SIZED` **is absent**, it returns `-1` by default **even if** `estimateSize()` happens to equal the true element count.
- `getExactSizeIfKnown()` returning a positive number is **trust in the Spliterator's characteristic**, not an independent check by traversing all elements.

This is why writing `estimateSize()` and `characteristics()` must be **consistent**. A false `SIZED` declaration can cause the Stream framework to produce wrong results because it is permitted to trust that metadata.

### 4.2. Lacking SIZED does not mean estimateSize is useless

A Spliterator **without SIZED** can still return a finite estimate to inform source-splitting decisions. However, downstream clients cannot infer that the number is exact just because it looks plausible.

If the source is an iterator without a cheap way to compute count or is reading data until exhaustion, returning `Long.MAX_VALUE` is a valid choice rather than trying to traverse everything just to calculate the size. Traversing the source yourself to count can **consume data**, losing elements for subsequent steps or adding unnecessary I/O.

## 5. SUBSIZED — exact size even after splitting

`SUBSIZED` is a **stronger characteristic than SIZED**. It means this Spliterator and **all Spliterators created from it via `trySplit()`** satisfy `SIZED` and `SUBSIZED`.

For an eight-element sequence:

~~~text
Before split: [0,1,2,3,4,5,6,7]  estimateSize=8

After trySplit():
  prefix:     [0,1,2,3]       estimateSize=4
  remainder:  [4,5,6,7]       estimateSize=4

Total size after split: 4 + 4 = 8
~~~

For a custom Spliterator declaring `SUBSIZED` with clear range control, we must preserve this relationship. Traversing one more element from the prefix will reduce the prefix size from 4 down to 3.

### 5.1. SIZED does not automatically imply SUBSIZED

**SIZED** refers to the size accuracy under the Spliterator's contract; it does not automatically mean all child splits also have exact size info. **SUBSIZED** adds that guarantee for child Spliterators and further splits.

Therefore, do not enable `SUBSIZED` out of habit. Only use it if:
- Each split data segment is disjoint, with no skipped/duplicated elements.
- Each new split can accurately report its remaining element count.
- Further splits do not break that commitment.
- Characteristic bits and counts remain consistent after permitted operations.

Some sources that are hard to split evenly or only know the count before the first split can declare `SIZED` without being able to honestly promise `SUBSIZED`.

### 5.2. A Spliterator may be unsplittable

`trySplit()` is allowed to return `null`. That can happen because the Spliterator is empty, only one element remains, the algorithm has no reasonable split point, or splitting overhead is too high.

Do not interpret `trySplit()==null` as "the source has size 0" or "the source is broken"; it only indicates that no portion of the source was split off in that call.

### 5.3. With ORDERED, the split-off part must be a proper prefix

When a source has an encounter order and declares `ORDERED`, `trySplit()` on a conforming Spliterator usually returns a **prefix** of the remaining elements, while the original instance keeps the **suffix**.

In the 0-to-7 sequence example:
- The Spliterator returned after `trySplit()` holds 0 to 3.
- The original instance after splitting holds 4 to 7.

If proper segment ordering is not maintained, an ordered stream can produce wrong results for operations like `findFirst()`, `limit()`, or `toList()`.

## 6. Designing a Custom Sized Spliterator.OfInt

We implement an integer range source **[start, end)** with end exclusive. To avoid boxing and leverage specialized APIs, use `Spliterator.OfInt` and `IntConsumer`:

~~~java
static final class IntRangeSpliterator implements Spliterator.OfInt {
    private int current;
    private final int fence;
    private final AtomicInteger advances;

    IntRangeSpliterator(int start, int end, AtomicInteger advances) {
        if (start < 0 || end < start) {
            throw new IllegalArgumentException("Invalid range");
        }
        this.current = start;
        this.fence = end;
        this.advances = Objects.requireNonNull(advances);
    }

    @Override
    public boolean tryAdvance(IntConsumer action) {
        Objects.requireNonNull(action);
        if (current >= fence) return false;
        int value = current++;
        advances.incrementAndGet();
        action.accept(value);
        return true;
    }

    @Override
    public OfInt trySplit() {
        int lo = current;
        int mid = lo + ((fence - lo) >>> 1);
        if (mid == lo) return null;
        current = mid;
        return new IntRangeSpliterator(lo, mid, advances);
    }

    @Override
    public long estimateSize() {
        return (long) fence - current;
    }

    @Override
    public int characteristics() {
        return ORDERED | DISTINCT | SORTED | SIZED | SUBSIZED
                | NONNULL | IMMUTABLE;
    }

    @Override
    public java.util.Comparator<? super Integer> getComparator() {
        return null;
    }
}
~~~

This is a **complete nested class declaration to be placed inside an enclosing class**. Required imports: `java.util.Spliterator`, `java.util.Objects`, `java.util.concurrent.atomic.AtomicInteger`, and `java.util.function.IntConsumer`. A standalone Java 17 program with a wrapper class and `main` is in Section 10.

### 6.1. Role of each component

**`current`** is the next element that can be supplied; **`fence`** is the exclusive ending bound. On each success, `tryAdvance` increments `current`, so the remaining size decreases by exactly one.

**`trySplit()`** computes the midpoint of the remaining range. If it is down to an unsplittable size, it returns `null`. If splittable, it updates the current instance to the second half and returns a new instance representing the first half.

**`estimateSize()`** returns `fence-current` accurately because this source is a finite numeric range not modified by anything else. In the example, the constructor restricts `start >= 0` and `end >= start`, so the halving calculation based on the difference of two indices does not overflow since the range is ordered and within the non-negative int domain.

**`advances`** is purely an instrumentation counter for testing; it does not determine element values and must not be used in place of the source's true size. It is an AtomicInteger because parallel tests may call different Spliterators from multiple threads.

### 6.2. Why declare those characteristics?

| Bit | Makes sense for the example sequence? | Explanation |
| --- | --- | --- |
| `ORDERED` | Yes | Sequence increases from start to end-1; returned segment is a prefix |
| `DISTINCT` | Yes | Each value in the range appears exactly once |
| `SORTED` | Yes | Numbers ascend according to natural ordering |
| `SIZED` | Yes | Remaining element count equals fence-current |
| `SUBSIZED` | Yes | Both halves and all further splits have exact sizes |
| `NONNULL` | Yes | Primitive source does not emit null references |
| `IMMUTABLE` | Yes | Numeric domain contents are generated from a fixed range, with no external mutable backing structure |
| `CONCURRENT` | Not declared | Not designed for multiple threads to traverse/split a single instance concurrently |

`SORTED` has an additional requirement: `getComparator()` must match the ordering; for natural order, return `null`. If you declare `SORTED` while inheriting an unsuitable default `getComparator()` that throws an exception, clients may fail. In the example, the method is explicitly overridden.

**Only declare properties that can be proven.** Do not add `DISTINCT` if the source has duplicates, `SORTED` if data is unsorted, or `IMMUTABLE` if the source contents can be modified in violation of the contract.

### 6.3. A note on units of measurement

`estimateSize()` measures **the number of elements to be traversed**, not byte count, not allocated Java object count, not string character length, and not CPU steps.

For example, a single String element with one million characters still **counts as one element**. If a `flatMap` produces multiple elements from one String, the post-`flatMap` size can be completely different from the source String count.

## 7. Unknown-size sources: spliteratorUnknownSize()

Java provides a helper:

~~~java
Spliterator<Integer> unknown =
        Spliterators.spliteratorUnknownSize(iterator, Spliterator.ORDERED);
~~~

This is illustrative code inside a method with an `iterator` variable and imports `java.util.Spliterator`/`Spliterators`. The helper takes an `Iterator<? extends T>` and characteristic bits. It **does not** assume knowledge of the iterator's size.

Example with an Iterator over a four-element List:

~~~java
Iterator<Integer> it = List.of(10, 20, 30, 40).iterator();
Spliterator<Integer> sp =
        Spliterators.spliteratorUnknownSize(it, Spliterator.ORDERED);

System.out.println(sp.estimateSize());         // Long.MAX_VALUE
System.out.println(sp.getExactSizeIfKnown());  // -1
~~~

This is an illustrative snippet requiring imports `java.util.Iterator`, `List`, `Spliterator`, and `Spliterators`. Even though the programmer **knows the original List** has four elements, the adapter was only given an Iterator and a characteristic set without SIZED. Per Java 17 test results:
- `estimateSize()` returns `Long.MAX_VALUE`.
- `getExactSizeIfKnown()` returns `-1`.
- `SIZED` is not declared.
- Traversing a Stream from this Spliterator for `count()` must determine the actual count; in the example, `next()` was called four times.

### 7.1. Why do two sources with the same data have different metadata?

`List.spliterator()` can report size because List has a `size()` API. Conversely, the `Iterator` interface alone has no `size()`; the unknown-size helper is not permitted to guess the size by silently consuming the Iterator.

This shows that metadata belongs to **the source/Spliterator contract**, not merely to "how many elements exist in the real world."

### 7.2. When size is needed, should you count by pre-traversing?

Not always. For a single-pass iterator reading from a file or network, traversing to count can **consume the source**. Re-processing would require rewinding/reopening the connection or buffering data in memory, costing extra resources.

In many systems, declaring unknown size and letting Stream traverse when needed is the right approach. Only declare `SIZED` if you can genuinely compute it accurately without breaking traversal semantics.

## 8. How does getExactSizeIfKnown() differ from count()?

These two calls are at **two different abstraction levels**:

~~~java
long known = spliterator.getExactSizeIfKnown();

long result = StreamSupport.stream(spliterator, false)
        .count();
~~~

The illustrative snippet above requires importing `java.util.stream.StreamSupport` and a `spliterator` variable. **Do not run these exact two lines on an instance already consumed elsewhere**; in the first case, the size-query call does not consume elements, whereas the `count` terminal operation completes the Stream's lifecycle.

| Property | `getExactSizeIfKnown()` | `Stream.count()` |
| --- | --- | --- |
| Target | Spliterator | Stream pipeline |
| Return value | Remaining size when SIZED, or `-1` | Number of **pipeline result** elements, type long |
| Must traverse elements? | No in default method; relies on characteristics/estimate | Not necessarily; may traverse or deduce |
| Accounts for `filter`/`flatMap`? | No, only Spliterator source metadata | Yes, per pipeline semantics |
| Usable with unknown-size sources? | Returns `-1` if not SIZED | Yes, typically traverses to count |
| For infinite Stream sources | May be unknown | If unbounded, may never terminate |

**Example:** a custom source has five numbers [0,1,2,3,4]. `getExactSizeIfKnown()` returns 5. However, the pipeline `filter(v -> v % 2 == 0).count()` returns 3 because after filtering only [0,2,4] remain.

Do not use the **source** size as a substitute for the count **after transformations that can change cardinality**.

### 8.1. count() can leverage SIZED to optimize

If the Stream framework trusts SIZED metadata and intermediate operations preserve element count, it can return the count **without calling tryAdvance on each element**.

Example:

~~~java
AtomicInteger visits = new AtomicInteger();

long count = StreamSupport.intStream(
        new IntRangeSpliterator(0, 5, visits), false)
        .map(v -> v * 2)
        .count();
~~~

This is **illustrative code inside a method**, requiring the `IntRangeSpliterator` class from Section 6 and imports `AtomicInteger` and `StreamSupport`.

In the JDK 17 experiment:
- `count = 5`.
- `visits.get() = 0`.

That is a valid optimization: `map` is a one-element-in/one-element-out operation, so the final count remains 5. **Do not place mandatory side effects inside `tryAdvance` or `map` and rely on count to trigger them.**

This is not a contract that every JDK will always optimize in one specific way; only the final pipeline result, under the condition that characteristics are declared **accurately**, is what must be correct per the API.

### 8.2. Filter can force the framework to traverse

~~~java
AtomicInteger visits = new AtomicInteger();

long evenCount = StreamSupport.intStream(
        new IntRangeSpliterator(0, 5, visits), false)
        .filter(v -> v % 2 == 0)
        .count();
~~~

In the same experiment:
- `evenCount = 3` because of [0,2,4].
- `visits.get() = 5` because all values in the example source had to be examined to decide the three valid values.

Even though the source Spliterator is SIZED, the `filter` operation **can change the output element count**; therefore, the number 5 from the source cannot be used as the final result of the filtered pipeline.

**Key takeaway:** `SIZED` means exact **at the layer of the source being described**, not "every transformation in the Stream knows its output count upfront."

## 9. Serious Mistakes When Implementing estimateSize() Yourself

### 9.1. Reporting SIZED but returning a size larger than reality

Suppose a source only emits 3 elements, yet `estimateSize()` always returns 100 and `characteristics()` declares `SIZED`. This is a **contract violation**. The framework may trust the metadata to allocate space, arrange work, or optimize count, leading to wrong reported counts or other errors.

The danger is that a test "traversing forEach gets three elements" might still pass, while a `count()` test could yield a different result. Do not treat the right result of one terminal operation as proof that all declared characteristics are accurate.

### 9.2. Failing to decrement estimate after tryAdvance

If an element has already been supplied yet `estimateSize()` stays the same, the "remaining" figure is wrong. For a custom Spliterator declaring SIZED/SUBSIZED, that is a major violation, especially if the framework queries size after partial traversal.

Correct pattern for a numeric range:

~~~java
// Inside custom Spliterator:
if (current < fence) {
    int element = current++;
    action.accept(element);
    return true;
}
return false;
~~~

And the size method must be based on the advanced cursor:

~~~java
public long estimateSize() {
    return (long) fence - current;
}
~~~

Both snippets are **method-fragment illustrations**, not standalone files.

### 9.3. Splitting with overlap or gaps while still declaring SUBSIZED

If `trySplit()` returns prefix 0–4 while remainder still starts at 4 (and both contain 4), data can be duplicated. If remainder starts at 6 after prefix 0–4, data 5 will be lost.

Even when the sum of both `estimateSize()` values looks equal to the initial size, the parts might **not actually be disjoint and cover the entire source**. Therefore tests must verify **the emitted values** as well, not just the counts.

### 9.4. Declaring SORTED without an appropriate comparator

`SORTED` is a declaration about natural ordering or a comparator. If this characteristic is declared, you must ensure `getComparator()` is appropriate. For an ascending int sequence, returning `null` indicates natural ordering. For a custom order, the comparator must be consistent with traversal.

Declaring `SORTED` for a random sequence just to make the Stream run faster is invalid.

### 9.5. Modifying the source after size has been declared

For mutable or concurrently written sources, "accurate size at Spliterator creation time" is not enough if the source changes unlawfully before/during traversal. If source stability cannot be guaranteed, you must implement an appropriate **late-binding**, fail-fast, snapshot, or concurrent characteristics policy.

`StreamSupport.stream(spliterator, false)` is designed so that Stream only traverses/splits/queries size after the terminal operation starts; however, this **does not automatically replace** the synchronization and binding contract of a custom source.

### 9.6. Triggering a traversal yourself to measure estimateSize

It is a design flaw if `estimateSize()` repeatedly calls `tryAdvance()` to count: it consumes elements, mutates source state, and breaks the expectation of a metadata-only query. For a source without an exact size, return an estimate or `Long.MAX_VALUE` instead of ruining traversal.

### 9.7. Confusing "has SUBSIZED" with "automatically runs on multiple threads"

`SUBSIZED` helps the framework split and know sizes; it does not force `parallelStream` to create one thread per part, does not guarantee speedup, and does not make the Spliterator thread-safe.

Each Spliterator instance generally needs **thread-confined ownership**; during parallel splitting, a child instance may be handed off to another thread, but multiple threads should not call `tryAdvance`/`trySplit` on the same instance when the implementation does not support it.

## 10. Complete, Compiled and Run Java 17 Program

Create file **SpliteratorSizeDemo.java**. The program has two kinds of sources:

- A custom `IntRangeSpliterator`, declaring SIZED + SUBSIZED and able to split in half.
- `spliteratorUnknownSize`, creating a Spliterator from an Iterator without declaring an exact size.

The `AtomicInteger` counters only measure traversal behavior in **that test run**, making no promise about the required number of `tryAdvance` calls in every pipeline.

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class SpliteratorSizeDemo {
    static final class IntRangeSpliterator implements Spliterator.OfInt {
        private int current;
        private final int fence;
        private final AtomicInteger advances;

        IntRangeSpliterator(int start, int end, AtomicInteger advances) {
            if (start < 0 || end < start) {
                throw new IllegalArgumentException("Invalid range");
            }
            this.current = start;
            this.fence = end;
            this.advances = Objects.requireNonNull(advances);
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (current >= fence) return false;
            int value = current++;
            advances.incrementAndGet();
            action.accept(value);
            return true;
        }

        @Override
        public OfInt trySplit() {
            int lo = current;
            int mid = lo + ((fence - lo) >>> 1);
            if (mid == lo) return null;
            current = mid;
            return new IntRangeSpliterator(lo, mid, advances);
        }

        @Override
        public long estimateSize() {
            return (long) fence - current;
        }

        @Override
        public int characteristics() {
            return ORDERED | DISTINCT | SORTED | SIZED | SUBSIZED
                    | NONNULL | IMMUTABLE;
        }

        @Override
        public java.util.Comparator<? super Integer> getComparator() {
            return null;
        }
    }

    static final class CountingIterator implements Iterator<Integer> {
        private final Iterator<Integer> delegate;
        int nextCalls;

        CountingIterator(List<Integer> source) {
            this.delegate = source.iterator();
        }
        @Override
        public boolean hasNext() {
            return delegate.hasNext();
        }
        @Override
        public Integer next() {
            nextCalls++;
            return delegate.next();
        }
    }

    public static void main(String[] args) {
        Spliterator<Integer> list = List.of(10, 20, 30, 40).spliterator();
        System.out.println("list estimate=" + list.estimateSize()
                + ", exact=" + list.getExactSizeIfKnown()
                + ", sized=" + list.hasCharacteristics(Spliterator.SIZED));

        AtomicInteger splitAdvances = new AtomicInteger();
        IntRangeSpliterator range = new IntRangeSpliterator(0, 8, splitAdvances);
        System.out.println("range initial=" + range.estimateSize());
        Spliterator.OfInt prefix = range.trySplit();
        System.out.println("split prefix=" + prefix.estimateSize()
                + ", remainder=" + range.estimateSize());
        prefix.tryAdvance((int v) ->
                System.out.println("first from prefix=" + v));
        System.out.println("prefix after advance=" + prefix.estimateSize()
                + ", exact=" + prefix.getExactSizeIfKnown());

        CountingIterator iterator = new CountingIterator(
                List.of(10, 20, 30, 40));
        Spliterator<Integer> unknown = Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED);
        System.out.println("unknown estimate=" + unknown.estimateSize()
                + ", exact=" + unknown.getExactSizeIfKnown()
                + ", sized=" + unknown.hasCharacteristics(Spliterator.SIZED));
        long unknownCount = StreamSupport.stream(unknown, false).count();
        System.out.println("unknown count=" + unknownCount
                + ", next calls=" + iterator.nextCalls);

        AtomicInteger sizedAdvances = new AtomicInteger();
        long size = StreamSupport.intStream(
                new IntRangeSpliterator(0, 5, sizedAdvances), false)
                .map(v -> v * 2)
                .count();
        System.out.println("sized count=" + size
                + ", advances=" + sizedAdvances.get());

        AtomicInteger filteredAdvances = new AtomicInteger();
        long even = StreamSupport.intStream(
                new IntRangeSpliterator(0, 5, filteredAdvances), false)
                .filter(v -> v % 2 == 0)
                .count();
        System.out.println("filtered count=" + even
                + ", advances=" + filteredAdvances.get());
    }
}
~~~

Compile with JDK 17:

~~~bash
javac --release 17 SpliteratorSizeDemo.java
java SpliteratorSizeDemo
~~~

**Verified exact stdout:**

~~~text
list estimate=4, exact=4, sized=true
range initial=8
split prefix=4, remainder=4
first from prefix=0
prefix after advance=3, exact=3
unknown estimate=9223372036854775807, exact=-1, sized=false
unknown count=4, next calls=4
sized count=5, advances=0
filtered count=3, advances=5
~~~

### 10.1. Explanation of Each Result

1. **`list estimate=4, exact=4, sized=true`:** List provides a Spliterator with a declared exact size.
2. **`range initial=8`:** the sequence 0..7 has eight elements.
3. **`split prefix=4, remainder=4`:** `trySplit()` returns the first half, the original instance keeps the second half. Total size after splitting equals 8.
4. **`first from prefix=0`:** the first half starts at value 0, preserving encounter order.
5. **`prefix after advance=3, exact=3`:** after supplying value 0, the prefix has only three elements left. Since the custom Spliterator has SIZED/SUBSIZED and updates the cursor properly, both methods return 3.
6. **`unknown estimate=Long.MAX_VALUE, exact=-1, sized=false`:** the iterator wrapper does not provide exact-size metadata even though the concrete iterator will end after four elements.
7. **`unknown count=4, next calls=4`:** in this sequential test, `count()` traverses all four elements of the unknown-size source.
8. **`sized count=5, advances=0`:** JDK 17 leverages size metadata and the cardinality-preserving `map` operation, avoiding element traversal to count.
9. **`filtered count=3, advances=5`:** after `filter(v -> v%2==0)`, the result is [0,2,4]; JDK 17 traversed all five elements in this run.

Do not infer exact callback counts as a contract from instrumentation data; only **the count value and accurately declared characteristics** are the foundation to rely on.

## 11. Independent Verification with Parallel Processing

A custom Spliterator with `SUBSIZED` does not just need to report accurate sizes; it must **split the source without losing or duplicating elements**. An additional test can sum 0 to 99 using a parallel Stream:

~~~java
AtomicInteger visits = new AtomicInteger();

long total = StreamSupport.intStream(
        new IntRangeSpliterator(0, 100, visits), true)
        .asLongStream()
        .sum();

System.out.println("parallel sum=" + total
        + ", advances=" + visits.get());
~~~

This illustrative snippet belongs inside a method with the `IntRangeSpliterator` class and `AtomicInteger`/`StreamSupport` imports.

Verified with `javac --release 17`, stdout:

~~~text
parallel sum=4950, advances=100
~~~

Since the sum from 0 to 99 is `99*100/2 = 4950`, the example helps verify the source-splitting design in a real aggregation. The counter shows 100 element deliveries in this test run. In real testing, you should also verify that **the resulting element set is exact** rather than only checking sum/count, because a source with both missing and duplicate elements could coincidentally yield the same sum in some datasets.

### 11.1. Systematic trySplit testing

A good test suite for a custom Spliterator should include:

- **Empty source**: `start=end`, `estimateSize()==0`, `tryAdvance()==false`, `trySplit()==null`.
- **Single element**: `trySplit()==null` is fine; one advance succeeds, remaining size is 0.
- **Two elements**: try splitting one and one; verify no overlap.
- **Odd count**: from 0 to 4 has 5 elements, split can be 2 and 3; halves do not need equal sizes.
- **Advance then split**: new parts must contain only **remaining** elements, without re-emitting already-taken elements.
- **Multi-level splits**: if SUBSIZED is declared, branches continue knowing exact sizes.
- **Sequential/parallel traversal**: both produce the same result set (and same encounter order if required by the terminal operation).
- **Count vs filter count**: post-filter count can differ from source size.
- **Arithmetic bounds**: verify no overflow when computing `mid` and `estimateSize()`; the sample snippet restricts to non-negative ranges for simplicity.

### 11.2. Performance measurement is not the goal of this test

A parallel Stream with 100 elements may not be faster than sequential; measuring here serves **correctness** of the custom Spliterator and partitioning. For performance benchmarking, representative data, JMH, or an appropriate methodology is needed, accounting for warm-up, thread contention, and test overhead.

## 12. Relation to Mutable Sources, Late-Binding, and Non-Interference

The `StreamSupport` documentation recommends that a custom source's Spliterator should be `IMMUTABLE` or `CONCURRENT`, or be **late-binding**. Otherwise, the overload taking `Supplier<? extends Spliterator<T>>` can help reduce the window during which the source might be modified before the terminal operation begins.

Design directions:

| Source Type | Potentially Suitable Design |
| --- | --- |
| Fixed mathematical sequence | Immutable, SIZED/SUBSIZED if split accurately |
| Immutable array or List | Report SIZED per source and preserve traversal |
| Mutable collection traversed via snapshot | Snapshot + SIZED if snapshot size is exact |
| Late-binding mutable collection | Determine source at bind time per contract |
| Concurrent queue | Use concurrent source with appropriate characteristics/ordering/count, do not attach SIZED if not guaranteed |
| Incremental read-only iterator | Can use unknown-size adapter; do not fabricate SIZED |
| Unbounded generator | Do not attach exact finite size; requires bounding terminal if completion is desired |

If using the `StreamSupport.stream(supplier, characteristics, parallel)` overload, **the separately supplied characteristics must match** the Spliterator produced by the supplier; otherwise, behavior may be undefined per contract. Do not pass `SIZED` for a supplier creating an unknown-size source to "push" the framework to optimize.

**Non-interference:** `map`/`filter` callbacks should not modify the source being traversed by the Spliterator, unless the source has an appropriate concurrent contract. And a custom Spliterator is generally **not thread-safe** just because it is used in a parallel Stream; the work-splitting system typically assigns each Spliterator to one worker at a time.

## 13. Checklist Before Declaring Size in a Custom Spliterator

When implementing `estimateSize()` yourself, ask yourself:

1. **Am I measuring remaining elements or the initial total?** It must be remaining per the current traversal.
2. **Is the exact size known?** If not, do not declare `SIZED`.
3. **If unknown, is the estimate reasonable?** `Long.MAX_VALUE` can be used instead of trying to traverse to count.
4. **Does `getExactSizeIfKnown()` return the right value on empty data and after one advance?** For custom SIZED, check carefully.
5. **Does `trySplit()` split without duplicates or omissions?** Check the data, not just the size sum.
6. **Is SUBSIZED promised?** If so, every branch after splitting must retain exact characteristics and size.
7. **Is ORDERED promised?** If so, the part returned from trySplit should be the prefix in encounter order.
8. **Are SORTED/DISTINCT/NONNULL promised?** Only when the contents genuinely satisfy them; SORTED needs an appropriate getComparator.
9. **Can the source be modified concurrently?** Define binding, snapshot, fail-fast, or concurrent policy.
10. **Is there any int/long overflow or dangerous cast?** Choose a safe size calculation, never converting `Long.MAX_VALUE` to an array element count.
11. **Does the pipeline change cardinality?** Do not use source size as the result of filter/flatMap.
12. **Does anything rely on side effects in tryAdvance/map when calling count?** Size metadata can cause count to skip traversal.
13. **Has it been tested with parallel and multi-level splits?** Increases confidence if SUBSIZED is declared.
14. **Have you distinguished guaranteed results from empirical callback counts?** Do not over-extrapolate from the current JVM.
15. **If the source is single-pass, is it being consumed inside estimateSize?** Must be avoided.

## 14. Self-Check Questions

**Question 1.** Does `estimateSize()` always return the exact size?

**Answer:** No. It returns an estimate; when unknown/infinite/too expensive it can be `Long.MAX_VALUE`. Only when characteristics and contract conditions match, such as accurate SIZED, can it be considered exact.

**Question 2.** What does `getExactSizeIfKnown()` return if `estimateSize()==4` but the Spliterator does not declare `SIZED`?

**Answer:** The default implementation returns `-1`. An estimate of 4 does not prove exactness on its own.

**Question 3.** What is the difference between `SIZED` and `SUBSIZED`?

**Answer:** SIZED declares the ability to report exact size per the Spliterator's contract. SUBSIZED further guarantees that all Spliterators created by `trySplit` calls also have SIZED/SUBSIZED.

**Question 4.** For a custom range [0,8), `trySplit()` creates prefix [0,4) and suffix [4,8). What is the count of each part?

**Answer:** Each part has four elements remaining. The sum after splitting 4+4 equals the initial eight elements.

**Question 5.** After taking element 0 from prefix [0,4), what must the prefix size be?

**Answer:** 3, because only 1,2,3 remain.

**Question 6.** Why does `spliteratorUnknownSize(iterator, ORDERED)` not return an exact size even though the iterator is reading from a four-element List?

**Answer:** The adapter only knows the Iterator contract and receives no List.size() metadata. It must not infer size by corrupting data; by default it does not declare SIZED.

**Question 7.** Why might `StreamSupport.intStream(range, false).map(f).count()` not call `tryAdvance`?

**Answer:** range accurately declares SIZED and map preserves cardinality, so count can take the count directly from metadata instead of traversing values.

**Question 8.** If `filter(x -> x%2==0)` is added, can the range's size still be used as the count result?

**Answer:** No. Filter can drop elements; for range 0..4, the result has only 3 even numbers.

**Question 9.** A Spliterator declares SIZED but estimate=100 even though it only has three elements—is that acceptable?

**Answer:** No. That is a broken contract and the framework is entitled to trust metadata, so terminal operations can produce wrong results or errors.

**Question 10.** Can `Long.MAX_VALUE` from `estimateSize()` be used to allocate an array holding the actual number of elements?

**Answer:** No. It may be an unknown/infinite sentinel; a suitable storage/streaming strategy and memory limit checks are needed.

**Question 11.** If a custom Spliterator always creates the right prefix, yet the remainder accidentally re-includes the last element of the prefix, will comparing only the size sum detect it?

**Answer:** Not necessarily. You must check the emitted values, uniqueness, and source coverage along with declared characteristics.

**Question 12.** Should `SORTED` be set for an ascending source? And what does getComparator return?

**Answer:** It can be set if genuinely guaranteed sorted. For natural ordering, getComparator returns `null` per the SORTED contract; when using another order, an appropriate comparator is needed.

**Question 13.** When a source is mutable, are additional guarantees needed?

**Answer:** Yes. You must design bind timing, snapshot, fail-fast/concurrent semantics, and consistency across traversal, characteristics, and estimate. Do not just read size at creation time and assume the source will not change.

## 15. Official Java 17 Documentation

- [Spliterator<T> — overview, estimateSize(), getExactSizeIfKnown(), characteristics](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).
- [Spliterator.SIZED and SUBSIZED](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html#SIZED).
- [Spliterator.OfInt — traversal for primitive ints](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.OfInt.html).
- [Spliterators.spliteratorUnknownSize()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterators.html).
- [StreamSupport.intStream() and stream()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/StreamSupport.html).
- [Stream.count() and API Note on skipping traversal when size is known](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()).

**Remember:** `estimateSize()` is an **estimate of remaining elements**, and can return `Long.MAX_VALUE` when unknown; `getExactSizeIfKnown()` only reports an exact number when the Spliterator has `SIZED` per contract. `SUBSIZED` extends that guarantee to all parts created by `trySplit()`. For custom sources, size reporting must be **honest, updated accurately after traversal and splits, with no skipped or duplicated elements**. Accurate metadata helps Stream optimize; inaccurate metadata can corrupt results, especially when `count()` trusts SIZED and skips calling `tryAdvance()`.