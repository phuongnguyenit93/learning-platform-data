# Spliterator: tryAdvance(), forEachRemaining(), and trySplit() in Java

**Spliterator<T>** is the interface that helps Java traverse a source of elements and, when possible, **split unprocessed elements into independent parts** to support the Stream API. When creating a custom source for a Stream, the three most important methods to understand are **tryAdvance()**, **forEachRemaining()**, and **trySplit()**.

- **tryAdvance(action)**: attempts to pass **one** next element to action and returns true; returns false if exhausted.
- **forEachRemaining(action)**: passes **all unconsumed elements** sequentially to action.
- **trySplit()**: attempts to split off a portion of **unconsumed** data into a new Spliterator, leaving the original Spliterator with the remainder.

The three methods must be consistent regarding traversal state. If they duplicate an element, skip an element, or split overlapping regions, a Stream based on that source can produce wrong results, especially when running in parallel. This lesson covers the contract of each method, sizing, characteristics, splitting, StreamSupport, common pitfalls, and a standalone compilable/runnable Java 17+ program.

## 1. What is a Spliterator?

**Spliterator** resides in the **java.util** package. The name suggests a splittable iterator: besides stepping through each element, it can hand off part of the work to another Spliterator.

Quick comparison:

| Property | Iterator<T> | Spliterator<T> |
| --- | --- | --- |
| Step-by-step traversal | hasNext() and next() | tryAdvance(action) |
| Traverse remaining elements | forEachRemaining(action) | forEachRemaining(action) |
| Split source into parts | No standard method | trySplit() |
| Know remaining element count | No general contract | estimateSize() |
| Declare source characteristics | No standard bit flags | characteristics() |
| Use in Stream | Can be converted via adapter | Can be passed to StreamSupport |

Spliterator **is not a Collection**. It does not promise to store all data, does not necessarily have a reset, and is not required to know the exact size. An implementation may simply read elements one by one in order, with **trySplit() returning null**. This is still valid and useful for sequential streams.

### 1.1. Important Signatures

For a general Spliterator<T>:

~~~java
boolean tryAdvance(Consumer<? super T> action);
void forEachRemaining(Consumer<? super T> action);
Spliterator<T> trySplit();
long estimateSize();
int characteristics();
~~~

Java provides specializations for primitive values:

~~~java
Spliterator.OfInt
Spliterator.OfLong
Spliterator.OfDouble
~~~

With OfInt, replace Consumer<Integer> with **IntConsumer**, avoiding boxing to Integer when emitting numbers:

~~~java
boolean tryAdvance(IntConsumer action);
void forEachRemaining(IntConsumer action);
Spliterator.OfInt trySplit();
~~~

The hands-on exercise will use Spliterator.OfInt to generate the range **[fromInclusive, toExclusive)**, for example [1,9) which is 1,2,3,4,5,6,7,8.

## 2. tryAdvance(): delivering exactly one element

tryAdvance accepts an action and looks for the next element:

~~~java
List<String> names = List.of("An", "Binh");

Spliterator<String> sp = names.spliterator();
boolean a = sp.tryAdvance(System.out::println);
boolean b = sp.tryAdvance(System.out::println);
boolean c = sp.tryAdvance(System.out::println);
~~~

This is an **illustrative snippet** requiring List and Spliterator imports inside a method. It prints two names, then a and b equal true, and c equals false.

Contract:

1. **true** means an element was passed to action.
2. **false** means there is no next element; action must not be called with dummy data.
3. Each successful call emits **one element**, not a whole batch.
4. When action is null, the method must handle it per contract, typically throwing NullPointerException.
5. If action throws an exception, the exception may propagate up; do not assume the same element can be safely retried.

### 2.1. Implementation with cursor and fence

~~~java
@Override
public boolean tryAdvance(IntConsumer action) {
    Objects.requireNonNull(action);
    if (cursor >= fence) {
        return false;
    }
    action.accept(cursor++);
    return true;
}
~~~

This is a method in a class implementing Spliterator.OfInt, where cursor points to the next unread value and fence is the exclusive upper bound. When not exhausted, action receives one number, cursor increments by one, and the method returns true.

If cursor equals fence, no numbers remain. **Do not return true without calling action**, or call action twice and return only a single true value.

### 2.2. Consumed elements do not reappear

Visualize the sequence:

~~~text
1 2 3 4 5 6 7 8
└───────────────┘
      source
~~~

After two tryAdvance calls:

~~~text
[1 2] | 3 4 5 6 7 8
 read    remaining
~~~

The Spliterator is now only responsible for **3..8**. A subsequent call will fetch 3, not go back to 1. If you need to traverse the entire sequence again, create a new Spliterator from a recreatable source.

## 3. forEachRemaining(): consuming the rest

forEachRemaining(action) processes unread elements until the end, unless action throws an exception.

~~~java
Spliterator<String> sp =
    List.of("An", "Binh", "Mai").spliterator();

sp.tryAdvance(System.out::println);       // An
sp.forEachRemaining(System.out::println); // Binh then Mai
~~~

It continues from the current position without resetting to the beginning.

The default implementation can be pictured as:

~~~java
while (tryAdvance(action)) {
    // Continue until no elements remain.
}
~~~

With a custom Spliterator, you can override it to reduce overhead:

~~~java
@Override
public void forEachRemaining(IntConsumer action) {
    Objects.requireNonNull(action);
    while (cursor < fence) {
        action.accept(cursor++);
    }
}
~~~

Overriding is not mandatory if the default method already meets your needs. However, if you override it yourself, it must emit **exactly the unread portion** following the same order/contract as tryAdvance.

### 3.1. Distinguishing Spliterator and Stream terminal operations

**Spliterator.forEachRemaining** consumes the remainder of that Spliterator itself. **Stream.forEach** is a terminal operation of a pipeline that may include filter/map. In a parallel Stream, forEach does not promise to preserve the encounter order of the action.

**Stream.forEachOrdered** is for cases where preserving the encounter order of an ordered pipeline is needed; it may come with different overhead.

Do not let a caller invoke Spliterator.forEachRemaining while another Stream is consuming the same Spliterator instance. Both could advance the state of the same source simultaneously.

## 4. trySplit(): delegating a portion of unconsumed work

trySplit attempts to split off **a portion of unprocessed work** and returns a new Spliterator. The original Spliterator keeps the remainder. If it cannot split or is not worth splitting, return **null**.

Example with unread sequence 1..8:

~~~text
Before split:
original [1 2 3 4 5 6 7 8]

After split:
returned object    [1 2 3 4]
original remaining [5 6 7 8]
~~~

For an **ORDERED** source, the returned Spliterator must represent a **prefix** of the untraversed portion. With 1,2 already read, the remaining portion is 3..8:

~~~text
already read       [1 2]
returned object    [3 4 5]
original remaining [6 7 8]
~~~

The two resulting objects must have **non-overlapping** responsibilities. Splitting is not duplicating the source, does not spawn threads itself, and does not invoke the consumer itself.

### 4.1. Range-splitting algorithm

Suppose RangeSpliterator holds cursor and fence:

~~~java
@Override
public Spliterator.OfInt trySplit() {
    long remaining = (long) fence - cursor;
    if (remaining <= 1) {
        return null;
    }

    int low = cursor;
    int middle = (int) (low + remaining / 2);
    cursor = middle;
    return new RangeSpliterator(low, middle);
}
~~~

If the initial range is **[low, fence)**, then after splitting:

- The new Spliterator handles **[low, middle)**.
- The original Spliterator has a new cursor middle, handling **[middle, fence)**.
- No range is skipped or overlapped.
- When at most one element remains, return null.

**Computing the difference as a long** before taking the midpoint avoids overflow when the two int endpoints are far apart. Directly adding two int bounds can overflow, causing an incorrect split.

### 4.2. Stopping condition for splitting

If a Spliterator returns a new part without reducing the original's work, the system can split forever or emit duplicate elements. For finite numeric ranges, halving generally ensures segments shrink until only 0 or 1 element remains.

There is no rule that every Spliterator must split in half. A tree, array, linked list, or file source may require a different strategy. However, **every successful split must preserve the set of unconsumed elements**.

## 5. estimateSize and remaining size

Spliterator.estimateSize() returns a **long** estimating the number of unread elements, or a suitable upper bound. It is not necessarily the initial element count.

For RangeSpliterator:

~~~java
@Override
public long estimateSize() {
    return (long) fence - cursor;
}
~~~

If range [1,9) has 8 numbers, after two tryAdvance calls only 6 remain. A split in half leaves both the prefix and original with 3 each.

### 5.1. SIZED

The **SIZED** characteristic is a promise that estimateSize provides an exact size per the contract. Do not declare SIZED for a source whose element count depends on unread data or changes unpredictably.

Java has the **getExactSizeIfKnown()** method. For a Spliterator with SIZED, it returns the declared exact size; without SIZED, it returns -1.

### 5.2. SUBSIZED

**SUBSIZED** promises that Spliterators produced by trySplit also have SIZED and SUBSIZED appropriately. RangeSpliterator knows the exact value count of every segment [start,end), so it satisfies both.

If splitting on an I/O cursor where the data count per part is unknown, you should not declare SUBSIZED just to make the Stream look "more optimal."

### 5.3. Avoiding overflow when computing size

Wrong intent for extremely wide int ranges:

~~~java
// May overflow before converting to long.
return (long) (fence - cursor);
~~~

Correct:

~~~java
return (long) fence - cursor;
~~~

The cast must happen **before the subtraction** so the difference fits within the long range.

## 6. characteristics(): source metadata

Spliterator uses **bit flags** to declare characteristics. This information can be used by the Stream runtime to optimize, so it must be truthful.

| Flag | Meaning | Note |
| --- | --- | --- |
| ORDERED | Has a defined encounter order | trySplit of an ORDERED source returns a prefix |
| DISTINCT | No duplicate elements per contract | Only use when genuinely guaranteed |
| SORTED | Elements are in a sorted order | Requires a matching getComparator contract |
| SIZED | Exact size known per contract | estimateSize must be reliable |
| SUBSIZED | Split parts are also SIZED and SUBSIZED | Not automatically implied by SIZED |
| NONNULL | Elements are non-null | Natural for primitive elements |
| IMMUTABLE | Source is not structurally modified during traversal | Does not mean cursor is final |
| CONCURRENT | Source allows concurrent modification per contract | Not a command to enable parallel |

Example in RangeSpliterator:

~~~java
@Override
public int characteristics() {
    return ORDERED | SIZED | SUBSIZED |
        IMMUTABLE | NONNULL | DISTINCT;
}
~~~

**ORDERED** because numbers are emitted in ascending order; **DISTINCT** because numbers do not repeat; **SIZED/SUBSIZED** because bounds exist; **NONNULL** because int is primitive; **IMMUTABLE** because the source is a rule generating numbers from two fixed bounds.

### 6.1. IMMUTABLE differs from cursor immutability

A Spliterator still has a mutable cursor to advance through elements. The IMMUTABLE flag refers to **the source structure** not changing during the traversal lifecycle, not that every field of the traversal object itself is final.

Do not declare IMMUTABLE for a Spliterator pointing to a mutable ArrayList modified concurrently without a mechanism ensuring the source contract.

### 6.2. SORTED and getComparator

If SORTED is declared, getComparator must obey the ordering contract: it can return **null** for natural ordering or an appropriate Comparator for another order. If SORTED is absent, the default getComparator can throw IllegalStateException.

In the main program, we **do not declare SORTED**, even though the sequence is in fact ascending, to focus on the three traversal/splitting methods and avoid adding a contract that is not demonstrated.

### 6.3. hasCharacteristics

~~~java
boolean correctFlags = source.hasCharacteristics(
    Spliterator.SIZED | Spliterator.SUBSIZED);
~~~

The result is true when **all requested flags are present**, not just any single flag.

### 6.4. CONCURRENT does not mean parallel

A Spliterator can split and run in a parallel stream **without having CONCURRENT**. CONCURRENT is for sources that support concurrent modification per the contract. Parallelism is decided at the Stream API level; do not declare this flag for a source without the appropriate capability.

## 7. StreamSupport connects a custom source to the Stream API

For Spliterator<T>:

~~~java
Stream<String> stream =
    StreamSupport.stream(customSpliterator, false);
~~~

This is an illustrative snippet; customSpliterator needs to be defined beforehand and support String elements. The **false** parameter requests sequential mode.

For Spliterator.OfInt, use the primitive specialization:

~~~java
IntStream stream = StreamSupport.intStream(
    new RangeSpliterator(1, 9), false);
~~~

**true** in the second parameter requests parallel mode:

~~~java
int sum = StreamSupport.intStream(
    new RangeSpliterator(1, 9), false
).sum();

int squares = StreamSupport.intStream(
    new RangeSpliterator(1, 9), true
).map(n -> n * n).sum();
~~~

The results are 36 and 204, respectively. The two calculations use **two fresh Spliterator instances**, because a consumed Spliterator must not be treated as a source that can be arbitrarily reset.

### 7.1. Parallel stream does not guarantee faster execution

**parallel=true** allows the Stream runtime to schedule parallel processing when appropriate; it does not guarantee a specific thread count or better speed. With only eight numbers, the overhead of splitting and combining results can outweigh the benefit.

A non-splittable Spliterator (trySplit always returns null) can still be used as a sequential source, though it may limit the ability to exploit parallelism.

### 7.2. Do not spawn threads inside trySplit

trySplit only creates a new data region. **The Stream runtime coordinates tasks**. If you spawn threads in every trySplit without a clear design, you can create too many threads, alter the data contract, and cause resource lifecycle bugs.

## 8. Ordered source, ordered results, and callback order

ORDERED describes the encounter order of elements. For RangeSpliterator, that is the ascending order from cursor to fence.

However, parallel Stream **forEach** is not required to invoke the action in source order. If the action needs to observe the exact encounter order, use **forEachOrdered** on an ordered pipeline and keep performance in mind.

Conversely, associative aggregations such as summing small integers produce the same result regardless of task scheduling. That is why the example program uses **sum()**, rather than having multiple threads print directly to stdout.

### 8.1. Do not re-split already read parts

If source has called tryAdvance twice and then splits, the returned prefix must start from the third element. Handing old elements back to the prefix will cause duplicate data. Similarly, after splitting, the original source must only keep the suffix, and must not also emit the prefix.

### 8.2. Do not call the same Spliterator concurrently without care

A Spliterator with a mutable cursor is not thread-safe by default when two threads call tryAdvance on **the exact same instance**. The right parallel model is to **split into objects with separate regions** and let the runtime handle them.

Do not share the same RangeSpliterator between a manual forEachRemaining loop and a running Stream, because both will contend over the traversal state.

## 9. Spliterators for mutable and I/O sources

A custom Spliterator can pull data from an array, List, tree, buffer, file, or generator. These sources have very different contracts.

For a mutable List, structural modification during traversal can violate non-interference or lead to ConcurrentModificationException depending on the implementation. Do not declare **IMMUTABLE** or **CONCURRENT** if the source does not genuinely satisfy them.

For a file or socket, a Spliterator may need to read on demand; splitting a file into independent regions can be hard due to newlines, encoding, permissions, and I/O state. In cases where safe splitting is not possible, **returning null from trySplit** is the right choice.

### 9.1. Resource management

The Spliterator interface itself **has no general close contract**. If it holds a file descriptor/socket, the Stream-creating API must clarify who closes the source and when. You can provide a Stream with **onClose** wired to cleanup and require callers to use **try-with-resources**, or design a wrapper that clearly manages the lifecycle.

Terminal operations should not be assumed to automatically close every resource of a custom source. Do not let an I/O-backed Stream outlive the lifecycle of the file it depends on.

### 9.2. Late binding and source characteristics

Some Spliterators bind to the source later than creation time; others bind early. This affects how the source reflects mutations, sizedness, and fail-fast behavior.

Do not assume that because Streams process intermediate operations lazily, opening I/O resources or binding the source is necessarily lazy as well. Those are two different mechanisms.

## 10. Complete Java 17+ Program

The program **CustomSpliteratorDemo.java** implements OfInt to generate an integer sequence without a backing array. It uses cursor/fence to guarantee non-overlapping splits. All printed values are deterministic and have been verified on Java 17; the long-based midpoint variant has also been tested with very wide int bounds.

Create file **CustomSpliteratorDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class CustomSpliteratorDemo {
    static final class RangeSpliterator implements Spliterator.OfInt {
        private int cursor;
        private final int fence;

        RangeSpliterator(int fromInclusive, int toExclusive) {
            if (fromInclusive > toExclusive) {
                throw new IllegalArgumentException("Invalid range");
            }
            this.cursor = fromInclusive;
            this.fence = toExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (cursor >= fence) return false;
            action.accept(cursor++);
            return true;
        }

        @Override
        public void forEachRemaining(IntConsumer action) {
            Objects.requireNonNull(action);
            while (cursor < fence) {
                action.accept(cursor++);
            }
        }

        @Override
        public Spliterator.OfInt trySplit() {
            long remaining = (long) fence - cursor;
            if (remaining <= 1) return null;
            int low = cursor;
            int middle = (int) (low + remaining / 2);
            cursor = middle;
            return new RangeSpliterator(low, middle);
        }

        @Override
        public long estimateSize() {
            return (long) fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED |
                IMMUTABLE | NONNULL | DISTINCT;
        }
    }

    public static void main(String[] args) {
        RangeSpliterator source = new RangeSpliterator(1, 9);
        List<Integer> visited = new ArrayList<>();
        boolean first = source.tryAdvance((int n) -> visited.add(n));
        boolean second = source.tryAdvance((int n) -> visited.add(n));
        System.out.println("advanced=" + visited);
        System.out.println("advancedFlags=" + first + "," + second);
        System.out.println("remainingSize=" + source.estimateSize());

        Spliterator.OfInt prefix = source.trySplit();
        System.out.println("splitSizes=" + prefix.estimateSize()
            + "," + source.estimateSize());
        List<Integer> left = new ArrayList<>();
        List<Integer> right = new ArrayList<>();
        prefix.forEachRemaining((int n) -> left.add(n));
        source.forEachRemaining((int n) -> right.add(n));
        System.out.println("prefix=" + left);
        System.out.println("remainder=" + right);
        System.out.println("exhausted=" +
            source.tryAdvance((int n) -> right.add(n)));

        System.out.println("sizeFlags=" +
            source.hasCharacteristics(Spliterator.SIZED | Spliterator.SUBSIZED));
        System.out.println("emptySplit=" +
            (new RangeSpliterator(5, 5).trySplit() == null));

        int sequentialSum = StreamSupport.intStream(
            new RangeSpliterator(1, 9), false).sum();
        int parallelSquares = StreamSupport.intStream(
            new RangeSpliterator(1, 9), true)
                .map(n -> n * n).sum();
        System.out.println("sequentialSum=" + sequentialSum);
        System.out.println("parallelSquares=" + parallelSquares);
    }
}
~~~

Compile and run on JDK 17 or later:

~~~bash
javac CustomSpliteratorDemo.java
java CustomSpliteratorDemo
~~~

**Exact stdout:**

~~~text
advanced=[1, 2]
advancedFlags=true,true
remainingSize=6
splitSizes=3,3
prefix=[3, 4, 5]
remainder=[6, 7, 8]
exhausted=false
sizeFlags=true
emptySplit=true
sequentialSum=36
parallelSquares=204
~~~

### 10.1. Explanation of Results

**advanced=[1, 2]**: two tryAdvance calls emit exactly two numbers, not the entire sequence.

**advancedFlags=true,true**: elements remain, so both calls succeed.

**remainingSize=6**: the initial range [1,9) has eight numbers; two were taken, so six remain.

**splitSizes=3,3**: splits the six unread values into prefix [3,6) and remainder [6,9). Each part has three numbers left.

**prefix=[3,4,5] and remainder=[6,7,8]**: forEachRemaining consumes the two independent parts with no duplicates and no omissions.

**exhausted=false**: after traversing the original remainder completely, no next number remains.

**sizeFlags=true**: the Spliterator declares both SIZED and SUBSIZED per contract.

**emptySplit=true**: the range [5,5) is empty, so trySplit does not return a new region.

**sequentialSum=36**: sum of 1+2+3+4+5+6+7+8.

**parallelSquares=204**: sum of squares 1²+2²+3²+4²+5²+6²+7²+8². The program does not need to assume thread scheduling order to determine the result.

### 10.2. Testing midpoint with wide numeric ranges

The implementation uses **long remaining** to compute midpoint and estimateSize. When the range spans from Integer.MIN_VALUE to Integer.MAX_VALUE with an exclusive upper bound, the total element count is **4.294.967.295** (which fits in long).

With halving in the tested extended example, the sizes of the two halves are **2.147.483.647** and **2.147.483.648**, and the sum remains exact. You should not actually collect this entire range into a List just to test: the element count is too large. You can test the size calculation and range splitting without traversing everything.

## 11. Common Pitfalls

**Pitfall 1 — tryAdvance returns true without calling action.** The caller thinks an element was processed even though there was no data; breaks the progress contract.

**Pitfall 2 — tryAdvance calls action multiple times for a single true.** Use forEachRemaining when you want to traverse a whole segment; tryAdvance is for one element only.

**Pitfall 3 — forEachRemaining restarts from the origin.** After some elements have already been taken, it must continue from the current cursor, otherwise data is duplicated.

**Pitfall 4 — trySplit returns a copy of the entire unread region without updating the original.** Both Spliterators will emit duplicate elements. Splitting is delegating ownership, not duplicating.

**Pitfall 5 — Off-by-one bounds when splitting.** With ranges [low,middle) and [middle,fence), neither omit middle nor include middle in both.

**Pitfall 6 — trySplit has no stopping condition.** When 0 or 1 element remains, it should generally return null; avoid infinite splitting or creating countless empty regions.

**Pitfall 7 — estimateSize does not change after consuming data.** When SIZED is declared, the number must match the unread count at that point per contract.

**Pitfall 8 — Declaring SUBSIZED inaccurately.** Every child split must maintain exact sizes, not just the root source.

**Pitfall 9 — Computing midpoint with int addition that can overflow.** Use long for differences and bounds if the range is very wide.

**Pitfall 10 — Marking SORTED without guaranteeing the comparator and getComparator.** A wrong characteristic can cause the runtime to optimize on false assumptions.

**Pitfall 11 — Marking CONCURRENT to enable parallelism.** CONCURRENT describes a source property, not thread count.

**Pitfall 12 — Letting two threads call tryAdvance on the same instance without a thread-safe contract.** A mutable cursor can race; split and assign separate regions instead.

**Pitfall 13 — Taking a Spliterator just manually traversed and expecting Stream to read from the beginning.** It continues from the unprocessed position and does not reset automatically.

**Pitfall 14 — Using trySplit on an I/O source that cannot be safely split.** Returning null can be more accurate than splitting across wrong data boundaries.

**Pitfall 15 — Forgetting to close the file/socket of a custom source.** Spliterator has no general close itself; a resource lifecycle needs to be designed for the Stream/owner.

**Pitfall 16 — Assuming parallel is always faster.** With a few values and cheap operations, coordination overhead can outweigh the benefit.

## 12. Checklist for Testing a Spliterator Source

- **Empty source**: tryAdvance false, estimateSize equals 0 if SIZED, trySplit null, forEachRemaining does not call action.
- **Single element**: tryAdvance true exactly once then false; trySplit does not create useless empty regions.
- **After partial traversal**: forEachRemaining continues from the remaining part.
- **After split**: the two parts have no duplicates, no omissions; with ORDERED, the returned part is the prefix.
- **Recursive split**: part sizes shrink to the stopping point, combined results remain complete.
- **SIZED/SUBSIZED**: declared sizes are accurate before/after splitting and traversal.
- **Large bounds**: no overflow when computing midpoint/estimateSize.
- **Sequential vs parallel**: two fresh sources with the same data yield semantically identical results for appropriate aggregations.
- **Failing or null action**: handled per contract; do not assume every action can be retried.
- **Mutable/I/O sources**: declare characteristics honestly and manage resources properly.

### 12.1. Testing splitting without parallel

You can create a Spliterator yourself, call trySplit, collect prefix and suffix into two Lists, concatenate them, and compare against an expected list.

If two elements of [1,9) have already been read, the concatenated result of the two parts after splitting must be [3,4,5,6,7,8], **not** the entire [1,2,3,4,5,6,7,8]. This approach reproduces missing/duplicate bugs more reliably than waiting on a parallel stream with non-deterministic scheduling.

## 13. When to Choose a Custom Source?

You do not always need to write a Spliterator yourself. For a Collection or array, **collection.stream()** and built-in Stream/Arrays APIs are usually simpler. Write a custom Spliterator when the source **has its own natural data generation or splitting mechanism**:

- A numeric sequence, index segment, or region in an array/buffer.
- A tree structure whose branches can be traversed independently.
- A paginated source with a clear range-splitting contract.
- A specialized API providing a cursor without a built-in Stream.
- An expensive data source needing control over size, ordering, or resource lifecycle.

Choose the simplest structure that preserves exact semantics. **The complexity of a custom Spliterator is only worthwhile when it solves a real data-source requirement, not just to rewrite existing JDK functionality.**

## 14. Self-Check Questions

1. How do tryAdvance and forEachRemaining differ in the number of elements passed to action?
2. After two tryAdvance calls from [1,9), what is estimateSize and what is the next element?
3. When a Spliterator is ORDERED, which part must trySplit return relative to the untraversed region?
4. Why must trySplit not let both the prefix and the original emit the same number?
5. Why is trySplit allowed to return null even if the source is not completely empty?
6. Do SIZED and SUBSIZED have the same meaning?
7. If estimateSize returns a wrong number, what consequences can Stream face?
8. Why does IMMUTABLE of a source not require cursor to be final?
9. How does CONCURRENT differ from parallel?
10. Why should you not spawn threads yourself inside trySplit?
11. If printing in source order is required, does parallelStream.forEach guarantee it?
12. When should you choose Spliterator.OfInt instead of Spliterator<Integer>?
13. How do you use StreamSupport.intStream to process a sequence of numbers from a Spliterator?
14. Why do you need to create a new Spliterator if you want to compute both sum and max?
15. For an I/O source, who is responsible for closing the resource?
16. Why can computing the midpoint by adding two ints fail?
17. How does testing splitting with Lists help detect missing/duplicate data?
18. For a cursor-advancing source that cannot be split, is that a broken Spliterator?

**Conclusion:** **tryAdvance()** traverses one element at a time, **forEachRemaining()** traverses all unread elements, and **trySplit()** splits off a portion of unread work into an independent region. These methods must be consistent in state and neither lose nor duplicate data. **estimateSize() and characteristics()** describe the source honestly so the Stream runtime processes it properly; **StreamSupport** turns a custom source into a sequential or parallel pipeline. When designing a Spliterator, correctness of traversal and splitting always matters more than trying to force parallel execution.