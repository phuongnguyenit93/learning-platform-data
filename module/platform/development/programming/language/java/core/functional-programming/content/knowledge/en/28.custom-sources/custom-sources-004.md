# ORDERED, SIZED, SUBSIZED, SORTED, and DISTINCT in Java Spliterator

## 1. Context: Custom Sources and the Spliterator Contract

In the Java Stream API, a **Spliterator<T>** is an interface for traversing and potentially splitting a data source for sequential or parallel processing. It provides methods such as **tryAdvance**, **forEachRemaining**, **trySplit**, **estimateSize**, and **characteristics**. When building a custom Stream source with **StreamSupport.stream(spliterator, parallel)**, the developer must honestly describe the source's properties via **bit flags** called *Spliterator characteristics*.

Five key flags in this lesson:

- **ORDERED**: has a defined encounter order.
- **SIZED**: the source size is known accurately per contract at specified times.
- **SUBSIZED**: spliterators created when splitting the source also maintain the SIZED and SUBSIZED contracts.
- **SORTED**: elements are traversed in a defined sort order.
- **DISTINCT**: no two traversed elements are equal according to this characteristic's duplicate-detection rule.

These flags **are not data-processing operations**. They are promises about source behavior so the Stream API can produce correct results and perform safe optimizations.

For example, an array **[5, 1, 5]** may have a very clear encounter order (by index) and an exact size of 3, yet it is **neither SORTED nor DISTINCT**. You must not attach SORTED or DISTINCT just to make the Stream run faster.

### 1.1. Why do custom sources especially need accuracy?

When Java provides Spliterators for standard collections, most of the contract is already established by the library. However, when creating your own Spliterator reading from an array, a numeric range, a result set, or a custom structure, you must decide:

1. Is the traversal order predetermined?
2. Is the size known accurately?
3. If split in half, do both child sources still have exact sizes?
4. Are elements genuinely emitted in a stable comparison order?
5. Can the data contain duplicate values?

If the answers change after the source is filtered, has data added/removed, or splits into branches, the flags must reflect the contract accurately at the appropriate time. **Over-declaring capabilities can cause wrong results**, not just wasted resources.

## 2. The Five Characteristics Side by Side

| Characteristic | Promise to Caller | Suitable Example | Misconception to Avoid |
| --- | --- | --- | --- |
| **ORDERED** | Has a defined encounter order | Spliterator traversing a List by index | ORDERED does not mean ascending |
| **SIZED** | estimateSize provides exact element count when SIZED contract applies | Fixed array snapshot | Not merely a rough estimate |
| **SUBSIZED** | Every split produced is also SIZED and SUBSIZED | Splitting an index range of known length | Having SIZED does not imply SUBSIZED |
| **SORTED** | Traverses in natural order or a Comparator declared by the Spliterator | Ascending int range | SORTED does not imply DISTINCT |
| **DISTINCT** | Elements are unique per equals | Non-repeating integer range | DISTINCT does not mean sorted |

Two important relationships:

- **SORTED implies ORDERED**: if elements are emitted in a sorted order, there is a corresponding encounter order.
- **SUBSIZED implies SIZED**: you cannot promise every split has an exact size when the current spliterator itself does not maintain SIZED.

Conversely:

- ORDERED does **not** imply SORTED.
- SIZED does **not** imply SUBSIZED.
- SORTED and DISTINCT are **two independent concepts**: data can be sorted yet contain duplicates, or unique yet unordered.

Java uses **bits of an int** to represent these characteristics. Bitwise representation allows combining multiple promises in a single value without needing a separate metadata object.

## 3. Checking Characteristics with hasCharacteristics and characteristics

A Spliterator provides:

~~~java
int flags = spliterator.characteristics();

boolean ordered =
        spliterator.hasCharacteristics(Spliterator.ORDERED);
~~~

This is an illustrative snippet, assuming a **spliterator** variable exists and **java.util.Spliterator** is imported.

Multiple flags can be checked at once:

~~~java
boolean exactOrderedSize = spliterator.hasCharacteristics(
        Spliterator.ORDERED | Spliterator.SIZED);
~~~

The expression returns true when **both flags** are present. Distinguish the **bitwise OR operator (|)** used to combine flags from the **logical OR operator (||)** used to combine boolean conditions.

Equivalent check:

~~~java
int mask = Spliterator.ORDERED | Spliterator.SIZED;

boolean hasBoth =
        (spliterator.characteristics() & mask) == mask;
~~~

This illustrative snippet requires importing Spliterator; the bitwise **&** operator retains common bits.

**Do not check using characteristics() == ORDERED** when you need to know whether ORDERED is present. A valid spliterator typically has **multiple flags** at once, so the combined value does not necessarily equal a single flag alone.

### 3.1. getExactSizeIfKnown and estimateSize

Two easily confused methods:

- **estimateSize()** returns a long describing the estimated remaining element count; if the source is SIZED, the size is known accurately per the SIZED contract.
- **getExactSizeIfKnown()** returns the exact size based on estimateSize if the spliterator has **SIZED**; without SIZED, it returns **-1**.

~~~java
long estimate = spliterator.estimateSize();
long exact = spliterator.getExactSizeIfKnown();
~~~

This is an illustrative snippet.

**Note:** estimateSize can return **Long.MAX_VALUE** when unbounded or size is unknown; that does **not** mean the source actually has exactly Long.MAX_VALUE elements. Do not interpret the estimate as proof to allocate an array of that size.

## 4. ORDERED: encounter order is not sorted order

**Encounter order** is the element order defined by the source and order-preserving operations. A List has an encounter order by index; a TreeSet is traversed in sorted order; whereas a HashSet does not promise a stable encounter order across runs.

Example:

~~~text
Data: [9, 2, 9, 4]

Has ORDERED: may have to emit as [9, 2, 9, 4].
Not SORTED: 9 before 2 is not ascending.
Not DISTINCT: value 9 appears twice.
~~~

When a Stream is ORDERED:

- **findFirst()** means the first element in encounter order, if any.
- **limit(n)** on an ordered stream selects the prefix of n elements.
- **skip(n)** skips the first n elements.
- **forEachOrdered()** respects the Stream's encounter order.
- **sorted()** can impose a new order, different from the source's encounter order.
- **distinct()** on an ordered stream is stable by first occurrence for values equivalent under equals.

**Do not treat ORDERED as a requirement to run sequentially.** A parallel Stream can still output results in encounter order for terminal operations that preserve it, even though work chunks are processed across multiple threads.

### 4.1. ORDERED and split sources

For a custom ORDERED Spliterator, **trySplit()** must respect a split compatible with encounter order. Typically, the spliterator returned from trySplit represents a **prefix** of the remaining elements and the original spliterator keeps the **suffix**.

Example of range 1..8 split at 5:

~~~text
Before:  [1, 2, 3, 4, 5, 6, 7, 8]
Returned split: [1, 2, 3, 4]
Original remainder: [5, 6, 7, 8]
~~~

If you randomly take alternating head-tail elements and still report ORDERED without satisfying the split contract, an order-preserving parallel terminal operation may produce unexpected results.

### 4.2. When should ORDERED not be attached?

If the source structure has no meaningful encounter order, attaching ORDERED makes a false promise. For example, when pulling data from an unordered set, the incidental order observed in one run **is not a contract** for other runs.

Conversely, if source order has business meaning, do not arbitrarily call **unordered()** for speed and still expect **findFirst()/limit()** to pick the exact first elements required earlier.

## 5. SIZED: exact size vs. rough estimate

**SIZED** states that the spliterator's estimateSize provides the exact element count per contract before traversal or splitting. This is very useful when the source is:

- A fixed array with a known number of slots.
- A finite index range [start,end).
- A snapshot collection with a fixed size throughout traversal.
- A custom structure that can accurately compute remaining elements and update on tryAdvance.

Example of a 6-element source with no internal filter:

~~~text
estimateSize() = 6
getExactSizeIfKnown() = 6
SIZED = true
~~~

If the source can unexpectedly drop elements during tryAdvance, or depends on an unknown number of valid records, **you cannot attach SIZED just because the raw record count is known**.

### 5.1. Cases where SIZED should not be declared

Suppose a source reads records one by one and discards invalid records. Initially there are 100 physical lines, but after processing only 83 valid records exist. If the Spliterator only **emits 83 elements**, it must not advertise SIZED=100.

An infinite or open-ended source may not know the exact count. In that case, report an **honest estimate** and do not attach SIZED. For an unknown-size source, estimateSize can often use Long.MAX_VALUE, though callers should not treat that as a real length.

**Do not infer SIZED from a Collection return type in source code** if the collection can change during traversal without a clear snapshot/binding contract. For some standard collections, Spliterator has late-binding or fail-fast mechanisms; those are contract details of each specific source, not to be applied arbitrarily to a custom Spliterator.

### 5.2. SIZED and Stream.count()

If the source and pipeline preserve exact size information, Stream can return the **count()** result without traversing every element. Thus:

~~~java
long count = List.of("a", "b", "c").stream()
        .peek(System.out::println)
        .count();
~~~

This is an illustrative snippet. **count** is still 3, but **there is no guarantee** that peek's action runs three times. For a SIZED source, Java can optimize counting when other operations do not change the element count.

**Do not use side effects in map/peek/filter as mandatory work** just because you plan to end with count().

## 6. SUBSIZED: a stronger promise than SIZED when branching

**SUBSIZED** means **every Spliterator obtained by splitting from this Spliterator is also SIZED and SUBSIZED**. This is a very fitting promise for sources that can split into exact index ranges.

Example of an eight-element array split in half:

~~~text
Original size = 8
trySplit() -> prefix size = 4
Original remainder size = 4
Both continue to report exact size.
Each half may split again into sizes 2 + 2.
~~~

In that case, **SIZED|SUBSIZED** indicates the entire branch hierarchy has known sizes upfront. It helps the Stream framework position, partition work, and plan allocations in appropriate scenarios.

**Having SIZED without SUBSIZED** is valid. For example, a Spliterator knows the total element count initially, but the splitting mechanism makes child branch sizes hard to determine accurately. Do not attach SUBSIZED if each branch cannot keep the promise.

### 6.1. Recomputing size after trySplit

A custom Spliterator must update internal state when splitting the source. If 10 elements remain before splitting and trySplit creates a 4-element prefix, the original spliterator must accurately estimate **6** remaining elements if it continues reporting SIZED.

You must not use the same initial size value for **both branches**, as doing so could double the virtual element count. This kind of bug sometimes does not surface in sequential runs but causes wrong behavior when switching to parallel.

### 6.2. SUBSIZED does not mean branches are always equal

A range with 7 elements can split into 3 and 4. **SUBSIZED only promises each branch's size is exact**, not that the two branches are equal or that trySplit must produce a split in every situation.

**trySplit()** can return **null** when no useful split remains, even for a SUBSIZED Spliterator. This is not a contract violation.

## 7. SORTED: comparison order and getComparator()

**SORTED** is a promise that elements are traversed in a defined order. A SORTED Spliterator must also carry **ORDERED**.

Two cases:

1. **Natural order**: elements can be compared via natural ordering. When a Spliterator reports SORTED and uses natural order, **getComparator() returns null**.
2. **Custom Comparator**: when a Spliterator reports SORTED according to a chosen Comparator, **getComparator() returns that Comparator**.

If a Spliterator **does not report SORTED**, calling **getComparator()** must throw **IllegalStateException** per the method's contract. For a custom Spliterator, getComparator() must be implemented appropriately if SORTED is declared.

Usage example on an existing Spliterator:

~~~java
if (spliterator.hasCharacteristics(Spliterator.SORTED)) {
    Comparator<? super String> cmp =
            spliterator.getComparator();
    if (cmp == null) {
        System.out.println("Natural ordering");
    } else {
        System.out.println("Custom comparator");
    }
}
~~~

This is an illustrative snippet assuming spliterator is Spliterator<String> and Comparator, Spliterator are imported.

**Do not infer that getComparator()==null means unsorted.** For a SORTED Spliterator using natural order, null is the valid result.

### 7.1. Sorted does not mean elements are unique

The sequence **[1, 1, 2, 3]** can have:

- **SORTED = true** because the order is non-decreasing.
- **DISTINCT = false** because there are two 1s.

At the same time, the sequence **[3, 1, 2]** can have:

- **SORTED = false**.
- **DISTINCT = true** because all three values are different.

Therefore, do not substitute SORTED for DISTINCT, nor attach DISTINCT just because sort was called.

### 7.2. Comparator must be stable

If a comparator relies on time, randomness, or mutable fields that change during traversal, the order may no longer be stable. When a Spliterator declares SORTED, callers are entitled to rely on the ordering promise, so the comparator and data must genuinely align.

**Note:** If a source is sorted by a comparator that is inconsistent with equals, set behavior and DISTINCT can be hard to reason about; do not assume two elements considered equal by the comparator are necessarily equal under equals. Deduplication semantics must be defined precisely per application requirements.

## 8. DISTINCT: based on equals, not position or sort

Under the **Spliterator.DISTINCT** contract, for any two emitted elements x and y, **there must not exist a pair where x.equals(y) returns true** (per the element semantics declared by the source). For data objects, you must properly understand `equals` and value stability.

Example:

~~~text
["A", "B", "C"]  -> DISTINCT true, SORTED may be true/false
["A", "B", "A"]  -> DISTINCT false
[1, 2, 3]       -> DISTINCT true
[1, 1, 2]       -> DISTINCT false
~~~

A **Set** is intended to eliminate duplicates, yet you should not design a custom Spliterator based on a Set or an ambiguous comparator and declare DISTINCT without confirming **the equals relationship of emitted elements**.

### 8.1. Why does the DISTINCT promise affect efficiency?

If the source already commits to DISTINCT, the Stream **distinct()** step may avoid extra duplicate-detection work in some cases. This enables optimization, but also creates a risk: **falsely declaring DISTINCT** can cause a downstream distinct operation to fail to remove all duplicates.

You should not declare DISTINCT "to speed things up." Only declare it when the source genuinely cannot emit two equal elements.

### 8.2. Equality of mutable elements

If an element is emitted and then has fields participating in equals/hashCode mutated, the distinctness rule may no longer hold. A custom source should avoid mutable data changing during traversal, or require an appropriate snapshot/identity contract.

**DISTINCT differs from UNIQUE KEY in a database:** a query may have distinct primary keys yet return objects equal under equals if the equals method does not inspect the primary key. Business identity must be distinguished from Java equality.

## 9. Runnable Java 17 Example: array with ORDERED/SIZED/SUBSIZED but not SORTED/DISTINCT

Create file **ArraySpliteratorFlagsDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

public class ArraySpliteratorFlagsDemo {
    public static void main(String[] args) {
        int[] input = {4, 2, 4};

        Spliterator.OfInt spliterator =
                Spliterators.spliterator(
                        input, Spliterator.ORDERED);

        System.out.println("ORDERED="
                + spliterator.hasCharacteristics(Spliterator.ORDERED));
        System.out.println("SIZED="
                + spliterator.hasCharacteristics(Spliterator.SIZED));
        System.out.println("SUBSIZED="
                + spliterator.hasCharacteristics(Spliterator.SUBSIZED));
        System.out.println("SORTED="
                + spliterator.hasCharacteristics(Spliterator.SORTED));
        System.out.println("DISTINCT="
                + spliterator.hasCharacteristics(Spliterator.DISTINCT));
        System.out.println("exact="
                + spliterator.getExactSizeIfKnown());

        int[] values = StreamSupport.intStream(spliterator, false)
                .toArray();
        System.out.println("values=" + Arrays.toString(values));
    }
}
~~~

Compile and run (JDK 17):

~~~bash
javac ArraySpliteratorFlagsDemo.java
java ArraySpliteratorFlagsDemo
~~~

Stdout:

~~~text
ORDERED=true
SIZED=true
SUBSIZED=true
SORTED=false
DISTINCT=false
exact=3
values=[4, 2, 4]
~~~

**Explanation:**

- **Spliterators.spliterator(int[], characteristics)** provides a Spliterator following index order, exact size, and array-region splitting capability; SIZED and SUBSIZED are reported along with the array source characteristics.
- The input array **is not sorted**, and has two duplicate 4 elements. Therefore SORTED and DISTINCT are not attached.
- **getExactSizeIfKnown()** returns 3 before consuming the stream.
- StreamSupport accepts the Spliterator and creates an **IntStream**; `toArray()` preserves all three values in encounter order.
- After the stream consumes the Spliterator, you should not reuse that Spliterator as if it still held the original data.

**Specifically:** the Spliterators.spliterator API accepts an additionalCharacteristics bitmask. You must not pass SORTED or DISTINCT if the array does not satisfy them; Java does not scan the array itself to prove those two promises.

## 10. Java 17 Example: custom Spliterator for an ascending int range

An integer range **[start,end)**, i.e., start inclusive and end exclusive, is a suitable example for implementing all five flags yourself. When start <= end and each number is emitted only once, the range has:

- ORDERED: from smallest to largest.
- SIZED: remaining count equals end - cursor.
- SUBSIZED: splitting index segments still yields exact sizes.
- SORTED: natural ascending ordering of Integer.
- DISTINCT: each number is emitted exactly once.

Add **NONNULL** because elements are primitive ints (when boxed they also have non-null values), and **IMMUTABLE** because the bounds are held in an independent instance, not read from an external mutable collection.

Create file **CustomRangeSpliteratorDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class CustomRangeSpliteratorDemo {
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
            Objects.requireNonNull(action, "action");
            if (cursor >= fence) {
                return false;
            }
            int current = cursor++;
            action.accept(current);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            long remaining = estimateSize();
            if (remaining < 2L) {
                return null;
            }

            int oldStart = cursor;
            int midpoint = (int) (cursor + remaining / 2L);
            cursor = midpoint;
            return new RangeSpliterator(oldStart, midpoint);
        }

        @Override
        public long estimateSize() {
            return (long) fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED
                    | SORTED | DISTINCT | NONNULL | IMMUTABLE;
        }

        @Override
        public Comparator<? super Integer> getComparator() {
            return null; // SORTED by natural ordering.
        }
    }

    public static void main(String[] args) {
        RangeSpliterator remainder = new RangeSpliterator(1, 9);
        Spliterator.OfInt prefix = remainder.trySplit();

        System.out.println("prefix size="
                + prefix.getExactSizeIfKnown());
        System.out.println("remainder size="
                + remainder.getExactSizeIfKnown());

        int[] left = StreamSupport.intStream(prefix, false).toArray();
        int[] right = StreamSupport.intStream(remainder, false).toArray();

        System.out.println("prefix=" + Arrays.toString(left));
        System.out.println("remainder=" + Arrays.toString(right));

        RangeSpliterator all = new RangeSpliterator(1, 9);
        System.out.println("sorted="
                + all.hasCharacteristics(Spliterator.SORTED));
        System.out.println("natural="
                + (all.getComparator() == null));

        int sum = StreamSupport.intStream(
                new RangeSpliterator(1, 9), true).sum();
        System.out.println("parallel sum=" + sum);
    }
}
~~~

Compile and run:

~~~bash
javac CustomRangeSpliteratorDemo.java
java CustomRangeSpliteratorDemo
~~~

Stdout:

~~~text
prefix size=4
remainder size=4
prefix=[1, 2, 3, 4]
remainder=[5, 6, 7, 8]
sorted=true
natural=true
parallel sum=36
~~~

### 10.1. Exact trySplit Analysis

For [1,9), there are eight numbers from 1 to 8. **estimateSize()** initially returns 8. **trySplit()** computes midpoint = 1 + 8/2 = 5 and returns a new Spliterator [1,5). The original Spliterator moves cursor to 5, so it keeps [5,9).

Both Spliterators have an exact size of 4 and both retain ORDERED, SIZED, SUBSIZED, SORTED, DISTINCT. When traversing prefix before remainder, the overall encounter order is 1..8.

After splitting, each branch can split again into smaller segments while staying exact. This is a natural reason to declare SUBSIZED.

### 10.2. Why use long for estimateSize?

Because the difference between two int numbers at opposite ends of the domain can exceed **Integer.MAX_VALUE**. Casting both operands to long before subtracting:

~~~java
return (long) fence - cursor;
~~~

computes the length of a range in the int domain without overflowing during subtraction. Midpoint is computed using long math before casting to int, and lies between the two valid bounds.

**There is no automatic check** that a caller using an overly large range will fit in memory. For example, **toArray()** on a huge range may fail to allocate; flags only describe properties, not guarantee sufficient resources.

### 10.3. Why must getComparator be overridden?

Spliterator.OfInt may inherit the default behavior that throws IllegalStateException when asked for a Comparator. A custom Spliterator that has declared **SORTED** must provide the meaning of getComparator. In this natural-ordering example, it returns null.

**Do not replace return null with an arbitrary Comparator** just to avoid an exception. If declaring natural ordering, make sure the source actually emits values in natural order.

### 10.4. Why does this custom Spliterator not use an external mutable source?

The **cursor/fence** pair belongs to the Spliterator instance; this is valid traversal state. **IMMUTABLE** in this context refers to the data source the Spliterator relies on, not a claim that the traversal pointer never changes. The Spliterator needs to update cursor when emitting or splitting elements.

The Spliterator contract does not automatically make a single instance safe for multiple threads to concurrently call tryAdvance or trySplit without coordination; the Stream framework is responsible for using/partitioning per contract. You should not directly share the same instance across multiple threads and invoke methods concurrently.

## 11. TreeSet: SORTED with a custom comparator

A SORTED source does not have to use natural order. **TreeSet** is a classic example of a sorted collection that can accept a Comparator.

Create file **SortedComparatorDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Spliterator;
import java.util.TreeSet;

public class SortedComparatorDemo {
    public static void main(String[] args) {
        Comparator<String> byLengthThenText =
                Comparator.comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder());

        TreeSet<String> words = new TreeSet<>(byLengthThenText);
        words.addAll(List.of("pear", "fig", "kiwi", "apple", "fig"));

        Spliterator<String> spliterator = words.spliterator();

        System.out.println("ORDERED="
                + spliterator.hasCharacteristics(Spliterator.ORDERED));
        System.out.println("SORTED="
                + spliterator.hasCharacteristics(Spliterator.SORTED));
        System.out.println("DISTINCT="
                + spliterator.hasCharacteristics(Spliterator.DISTINCT));

        Comparator<? super String> comparator =
                spliterator.getComparator();
        System.out.println("custom=" + (comparator != null));
        System.out.println("words=" + words);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SortedComparatorDemo.java
java SortedComparatorDemo
~~~

Stdout:

~~~text
ORDERED=true
SORTED=true
DISTINCT=true
custom=true
words=[fig, kiwi, pear, apple]
~~~

**Explanation:**

1. The Comparator compares length first, then natural order when lengths are equal.
2. "fig" (3 chars) comes before "kiwi" and "pear" (4 chars); "kiwi" precedes "pear" alphabetically; "apple" (5 chars) is last.
3. TreeSet retains only one copy of "fig", so this source has distinct elements per the Set contract.
4. TreeSet's Spliterator reports SORTED and ORDERED; **getComparator()** returns the Comparator used rather than null.
5. If using TreeSet without passing a comparator and elements have natural ordering, getComparator() returns null.

**Design note:** TreeSet decides which elements are considered duplicates using the comparison relation. The Comparator in the example uses length **plus natural order** to prevent two different Strings of the same length from being treated as duplicates. If the comparator only compared length, distinct Strings could be unintentionally dropped from the TreeSet. Do not infer a correct dataset solely from having SORTED/DISTINCT flags.

## 12. Flags Can Change Through a Stream Pipeline

A source having characteristics does not mean every **intermediate Stream** preserves the same flags on the final Spliterator. Each operation can transform what the Stream knows.

Examples of impact:

| Operation | Information Affected |
| --- | --- |
| **filter(predicate)** | Cannot assume output size equals source size when retained count is unknown |
| **map(mapper)** | Mapper can turn distinct elements into the same value or break sort order |
| **distinct()** | Output removes duplicates per Stream semantics |
| **sorted()** | Output has sort order per the corresponding call |
| **limit/skip** | Remaining element count changes by position and can affect splitting info |
| **unordered()** | Removes the pipeline's encounter order requirement |

You should not assert that a fixed set of flags will persist after every operation and across every JDK. The safe approach is to **read the API contract where used** and **check characteristics** when writing custom algorithms based on them.

### 12.1. map does not automatically preserve DISTINCT and SORTED

Suppose an int source **[1,2,3]** is both SORTED and DISTINCT. The mapper **n -> n % 2** turns it into **[1,0,1]**: neither ascendingly sorted, nor free of duplicate value 1. Thus blindly keeping SORTED and DISTINCT flags for a mapped source as if no transformation occurred is **wrong**.

Even if a specific mapper preserves order, such as **n -> n + 1** in a non-overflowing range, we still should not assume the framework will declare SORTED because it does not prove the monotonicity of an arbitrary lambda. A custom Spliterator wrapper should only declare flags that the wrapper itself guarantees.

### 12.2. filter changes the element count

For a SIZED source of 100 values, **filter(n -> n > 50)** might keep 50 values or another count depending on the data. When building a custom Spliterator with internal filtering logic, you cannot keep the exact size 100 promise if only 50 elements are emitted.

Java Streams can optimize across pipelines based on provable information; do not use the original element count as a substitute for the exact size of filtered output.

### 12.3. SORTED is not automatically inferred when a Collection holds sorted values

An ArrayList that happens to be in ascending order does not mean ArrayList's Spliterator necessarily reports SORTED. Characteristics are **a contract of the source and implementation**, not the result of scanning data at runtime.

If you need a custom-defined source that is always sorted, model the characteristic properly and provide an appropriate comparator; if you only need to sort once, using Stream.sorted can be simpler than building a custom Spliterator reporting SORTED.

## 13. How Wrong Flags Affect Results

### 13.1. Attaching DISTINCT inaccurately

A custom Spliterator emits **[A, B, A]** yet reports DISTINCT. Downstream **distinct()** may assume the source already has no duplicates and skip deduplication work. The result may still contain A twice even though the user expected duplicates removed.

### 13.2. Attaching SORTED inaccurately

A source emits **[4,1,3]** yet reports SORTED in natural order. Downstream algorithms are allowed to rely on that promise and may optimize incorrectly. Results of operations requiring order/comparator may be wrong. When SORTED, getComparator must also be consistent with data ordering.

### 13.3. Attaching SIZED inaccurately

A source of 10 elements only emits 7, yet reports exact size 10. Optimizations such as count and some allocation strategies may use inaccurate information; result data may not match reality. **Do not declare SIZED if the number is only an upper bound**.

### 13.4. Attaching SUBSIZED inaccurately

The initial source knows the exact size, yet splits do not know sizes or report wrong ones; parallel partitioners may trust mismatched positions/lengths. Consequences may only appear under parallel workloads, making bugs hard to reproduce.

### 13.5. Attaching ORDERED inaccurately

If the source does not maintain a defined encounter order, yet reports ORDERED, operations like limit/findFirst may take on wrong meanings relative to user requirements. Do not use ORDERED to turn an accidental order into a meaningful one.

**Testing rule:** every declared bit must be backed by proof from the source's invariants and the behavior of tryAdvance/trySplit, not just because the author wants optimization.

## 14. Other Characteristics to Recognize

Beyond the five main flags, Spliterator has a few other important characteristics:

- **NONNULL**: elements are never null.
- **IMMUTABLE**: the underlying data source structure cannot be modified during traversal per the Spliterator contract.
- **CONCURRENT**: the source supports concurrent modification per a defined contract (e.g., an appropriate concurrent collection).

These characteristics are largely independent of the five main flags. For example:

- A source can be NONNULL yet not SORTED.
- An IMMUTABLE source can contain duplicate values, so it is not automatically DISTINCT.
- A concurrent collection may not guarantee an exact size snapshot, so it is not automatically SIZED.

**Do not overuse IMMUTABLE:** a Java array can be modified through another reference. Just because an array's length is fixed does not mean the source's structure/values are completely immutable in the sense required during traversal. Base it on the source API's contract rather than guessing IMMUTABLE.

## 15. Performance and Parallelization

Characteristic flags help the framework plan, but **no flag makes an algorithm fast on its own**.

### 15.1. ORDERED can make parallel execution incur coordination cost

When having to preserve the first element or encounter order, some operations like **limit**, **skip**, and **distinct** may require more coordination between parallel branches. If business requirements have no ordering need, order constraints can be avoided; if they do, do not trade correctness for nice benchmarks.

### 15.2. SUBSIZED helps partition accurately

When splits know their sizes, the framework can distribute work and positional results more easily. However, a custom Spliterator with an **ineffective trySplit** or creating heavily skewed branches can still run slowly despite carrying SUBSIZED.

### 15.3. SORTED and DISTINCT help avoid unnecessary work

If a source is genuinely sorted/distinct, corresponding operations may reduce work. However, this depends on the pipeline, Stream type, and implementation; **no specific speed is guaranteed**.

### 15.4. StreamSupport with the parallel flag

~~~java
IntStream stream = StreamSupport.intStream(
        new RangeSpliterator(0, 1000), true);
~~~

This is an illustrative snippet assuming RangeSpliterator is available as in the example, requiring StreamSupport and IntStream imports.

The **true** parameter enables a parallel pipeline, but does not guarantee multiple threads will always be used. A source that is too small or has an unhelpful trySplit may not achieve expected speedups. Consider branching overhead, combiners, data size, and the purity of behavioral parameters.

## 16. Building Custom Sources with StreamSupport: Which Option?

Java supports two common ways:

~~~java
Stream<T> fromSpliterator =
        StreamSupport.stream(spliterator, false);
~~~

or:

~~~java
Stream<T> fromSupplier =
        StreamSupport.stream(supplier, characteristics, false);
~~~

These are **illustrative usage signatures**, assuming appropriate variables/types and importing StreamSupport and Stream.

- Passing a **Spliterator directly**: you already have a Spliterator instance, using that instance for the Stream.
- Passing a **Supplier<Spliterator<T>>** with a characteristics bitmask: allows deferring Spliterator acquisition until the terminal operation, per the API contract. This is useful when the source must be late-binding or is sensitive to changes before traversal starts.
- With the Supplier version, **declared characteristics must match the Spliterator provided by the supplier**. Supplying flags different from reality can cause incorrect behavior.

### 16.1. Do not reuse a consumed Stream

Streams are designed for **single use**. After a terminal operation such as toList, count, or sum, do not continue consuming the same Stream.

Similarly, a custom Spliterator containing a mutable cursor should not be passed into multiple Streams expecting each Stream to get the initial data again. If two traversals are needed, create **two fresh Spliterators**, or design the source with a contract-compliant re-initialization mechanism.

## 17. Reading the Table: Choosing Flags by Scenario

| Data Source | ORDERED | SIZED | SUBSIZED | SORTED | DISTINCT |
| --- | --- | --- | --- | --- | --- |
| Ascending non-repeating int range [start,end) with exact range split | Yes | Yes | Yes | Yes | Yes |
| Array [5,1,5] traversed by index | Yes | Yes | Yes | No | No |
| List [1,1,2] traversed by position | Yes | Yes if snapshot/size per contract | Depends on implementation | Not required | No |
| Sorted String list with duplicates | Yes | If known accurately | Depends on split | Yes if Spliterator declares sort contract | No |
| Set with unique values but no encounter order | Not needed | Depends on source | Depends on split | Not required | Yes if uniqueness by equals |
| Data emitted from filter with unknown valid count | Depends on source | No | No | Depends on invariants | Depends on invariants |

The table is a **guide to determining contracts for custom sources**, not a substitute for reading the documentation of each Spliterator in Java Collections. Specific characteristics of an implementation can depend on how it traverses and splits the source.

In particular: **"the list is currently sorted"** does not automatically make a List's Spliterator report SORTED. If a SORTED contract is needed, you must implement or choose an appropriate source.

## 18. Testing a Custom Spliterator Properly

When implementing a Spliterator yourself, do not just run **stream(...,false).toList()** once and call it done. The test suite should cover:

### 18.1. Sequential traversal

- Create a source with known content and order.
- Traverse to completion using tryAdvance/forEachRemaining.
- Verify actual received element count, order, duplicate count, and behavior after exhaustion.
- If ORDERED, verify expected encounter order.
- If SORTED, verify adjacent pairs are non-decreasing per getComparator or natural ordering.

### 18.2. Size

- Before traversal, check estimateSize and getExactSizeIfKnown.
- After one tryAdvance, if SIZED and remaining count is managed per contract, re-check the remaining value.
- For non-SIZED sources, verify getExactSizeIfKnown returns -1.
- Avoid negative counts or long overflow.

### 18.3. Splitting and reassembling

- Call trySplit until no further splits are possible.
- Traverse **the returned split first** then the remainder if ORDERED and restoring encounter order.
- Total element count across branches must equal the original source, with no lost and no duplicated elements.
- If SUBSIZED, every branch must report SIZED/SUBSIZED and exact size.
- Test empty sources, 1-element sources, odd counts, and large counts.

### 18.4. Consuming algorithms

- Compare sequential and parallel StreamSupport results.
- Try **toArray**, **count**, **findFirst**, **distinct**, **sorted**, **limit**, **skip**.
- For genuinely DISTINCT sources, verify no duplicate elements per equals.
- For SORTED sources, verify getComparator and actual ordering.
- Do not rely on log order from a mapper in a parallel stream.

### 18.5. Data domain boundaries

- For int ranges, test negative values and near Integer.MIN_VALUE/Integer.MAX_VALUE bounds to catch midpoint/estimateSize overflow.
- For resource-backed sources, test lifecycle and exceptions when traversal stops early.
- For mutable data, clearly define snapshot or concurrent-modification mechanisms.

**Important:** a custom Spliterator declared SUBSIZED whose trySplit returns null on small sources is completely valid; there is no need to force splitting a single element into two branches.

## 19. Common Mistakes

| Mistake | Problem | Fix |
| --- | --- | --- |
| Attaching SORTED to an unsorted List | Downstream may trust wrong order | Only report SORTED when emitting in proper order |
| Attaching DISTINCT to a source with duplicates | Downstream distinct may be wrongly optimized | Verify equals uniqueness |
| Treating ORDERED as natural ascending | Confusing encounter order with sorted order | ORDERED only promises encounter order |
| Treating SIZED as a rough estimate | Wrong exact size and count | Without exact size, omit SIZED |
| Attaching SUBSIZED even though splits lack real sizes | Wrong parallel partitioning | Only report SUBSIZED if all splits qualify |
| Failing to update cursor/estimateSize after trySplit | Can duplicate/lose elements or report wrong size | Split non-overlappingly and update remainder |
| Attaching SORTED without implementing getComparator | SORTED contract not met | Return null for natural, comparator for custom |
| Calling getComparator on a non-SORTED source | IllegalStateException | Check SORTED first |
| Attaching IMMUTABLE to a mutable source without contract | May encounter modifications during traversal | Define snapshot/ownership clearly |
| Guessing flags from one printed output | Depends on incidental data | Base on source invariants |
| Using SUBSIZED as a promise of even splits | Not the flag's meaning | Only promises exact size per split |
| Keeping SORTED/DISTINCT flags after arbitrary map | Mapper can break those properties | Re-evaluate flags after transformation |
| Sharing the same Spliterator across multiple Streams | Single-use cursor | Create a fresh Spliterator each time |
| Relying on count to force side effects to run | May optimize without traversal | Do not use side effects for business logic |
| Testing only sequential, skipping parallel | Split bugs stay hidden | Test both execution paths |

## 20. Practice Exercises

### Exercise 1: Classify an array

An array source [7, 1, 7, 3] is traversed by index, knows it has exactly 4 elements, and splits by index segments. Determine the five main flags.

**Hint:** ORDERED, SIZED, SUBSIZED are present; SORTED and DISTINCT are not.

### Exercise 2: SORTED but not DISTINCT

Design a Spliterator emitting [1,1,2,3] in natural ordering. Why can SORTED be true while DISTINCT is false? What must be returned from getComparator?

### Exercise 3: DISTINCT but not SORTED

A source emits [9,2,7] with no duplicates. Why can it be DISTINCT yet not SORTED? If the source always traverses in that fixed order, is ORDERED allowed?

### Exercise 4: Checking after splitting

Create RangeSpliterator(0,7), call trySplit, and check both sizes. Repeat on the prefix branch. Prove all branches do not overlap and total size equals 7.

### Exercise 5: Broken size contract

A source reports SIZED=100 yet only emits records passing a filter, totaling 68 records. Explain why **getExactSizeIfKnown()** and **count()** can mislead, and propose a flag change.

### Exercise 6: Custom comparator

Create a TreeSet<String> with a comparator by length then alphabetically. Observe getComparator is non-null and test ordering of two same-length strings. If the comparator only checks length, what happens to two different values of the same length?

### Exercise 7: Ordered parallel

Run RangeSpliterator(1,101) through StreamSupport.intStream with parallel false and true; collect toArray and compute sum. Compare result contents, not log order from map or peek.

### Exercise 8: Designing a random number generator source

A source continuously generates random values with unknown exact count and possible repeats. Among the five flags, which should be avoided without additional contracts? Distinguish having a generation sequence from the encounter order defined by the API.

## 21. Remember

**ORDERED** promises encounter order; **SORTED** promises a sort order and implies ORDERED, while requiring a proper getComparator. **SIZED** promises exact size per contract; **SUBSIZED** is stronger, ensuring splits remain SIZED and SUBSIZED. **DISTINCT** promises no duplicate elements per equals.

The five flags **are not speed switches**. They are truthful descriptions of the Spliterator. When building custom Stream sources, those promises affect element selection, counting, parallel work splitting, and deduplication. **False declarations can cause downstream optimizations based on wrong assumptions and return wrong results.**

Before setting a flag, ask: **"Can any valid caller rely on this characteristic in every traversal and after every trySplit and still receive correct results?"** If it cannot be proven, do not declare that flag.