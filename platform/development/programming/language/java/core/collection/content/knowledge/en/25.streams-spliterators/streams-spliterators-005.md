# ORDERED, SORTED, DISTINCT, SIZED, IMMUTABLE and CONCURRENT

## 1. Characteristics Are Guarantees for Spliterator Consumers

A Spliterator can emit elements one by one, traverse the remaining elements, and split the source into parts. So that algorithms know what they can rely on, it also reports **characteristics** via `characteristics()`.

The six characteristics in this lesson answer different groups of questions:

| Characteristic | Question Answered |
| --- | --- |
| `ORDERED` | Do the elements have a defined encounter order? |
| `SORTED` | Does the encounter order follow a sorting rule? |
| `DISTINCT` | Are the encountered elements distinct according to the `equals` relation? |
| `SIZED` | Is there a guarantee that the exact element count is known under the specified conditions? |
| `IMMUTABLE` | Does the source covered by the Spliterator prevent adding, removing, or replacing elements during traversal? |
| `CONCURRENT` | Does the source have a policy that allows safe concurrent modification during traversal? |

These bits are information about the source, structure, and elements that algorithms can take advantage of. They are not commands telling the Spliterator to sort itself, deduplicate itself, or lock its data. [Java SE 17 — Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).

For example, a list `[3, 1, 3]` has a clear index order, but it is not sorted in ascending order and contains duplicate elements. A `TreeSet` can be ordered, sorted, and distinct all at once. A key view of a `ConcurrentHashMap` may not have a guaranteed encounter order, yet it supports concurrent modification of the source.

To use them properly, you must read each characteristic according to the scope of its guarantee, rather than treating every convenient property as the same kind of "safety".

## 2. Reading Bits Properly with hasCharacteristics

`characteristics()` returns an `int` containing multiple bits combined with bitwise OR. When you only need to check, use the convenience method:

~~~java
boolean ordered = source.hasCharacteristics(Spliterator.ORDERED);
~~~

This is an illustrative snippet where `source` is a `Spliterator<?>`. `ordered` is `true` when the Spliterator reports that characteristic.

To require multiple characteristics at the same time:

~~~java
boolean both = source.hasCharacteristics(
        Spliterator.ORDERED | Spliterator.SORTED);
~~~

`both` means **having both ORDERED and SORTED**, not having at least one of the two.

If you use bitwise operations yourself, the full check is:

~~~java
int required = Spliterator.ORDERED | Spliterator.SORTED;
boolean all = (source.characteristics() & required) == required;
~~~

Comparing `(flags & required) != 0` only confirms that at least one bit is set. Confusing the two checks can send an algorithm down a branch that requires sorted data even though the source only has index order.

Do not compare `source.characteristics() == Spliterator.ORDERED` to ask whether ORDERED is present. A Spliterator can simultaneously report `ORDERED`, `SIZED`, and `SUBSIZED`, so the full mask value differs from the `ORDERED` constant alone.

### The Absence of a Bit Does Not Prove the Opposite Property

An `ArrayList` currently containing `[1, 2, 3]` may not report `SORTED`. The fact that specific data happens to look ascending does not mean the Spliterator implementation declares that sorting rule.

Similarly, a list currently holding three different numbers does not necessarily report `DISTINCT`. An algorithm must distinguish between:

- Observing a property on a specific dataset.
- Having a characteristic reported by the Spliterator to rely on as a contract.

Characteristic information can be conservative. Do not infer a bit just by looking at printed output once, and do not attach a bit yourself hoping the Stream will run faster.

## 3. ORDERED: Encounter Order, Not Ascending Order

`ORDERED` means the source defines an **encounter order** for its elements. For a `List`, that is increasing index order.

Example:

~~~text
List:            [3, 1, 3]
encounter order: 3 then 1 then 3
~~~

This order is well-defined, but it is not ascending numerical order. This is a classic example of `ORDERED` without needing `SORTED`.

For a Spliterator with ORDERED:

- `tryAdvance` takes the next element in encounter order.
- `forEachRemaining` invokes the action in the encounter order of the source portion currently covered.
- `trySplit`, when splitting succeeds, must return a prefix of the untraversed portion.

Thanks to the prefix rule, an algorithm can process the front and back parts separately and then combine them in the right order. However, splitting by itself does not make completion times across multiple threads automatically follow source order.

### Different Sources Have Different Guarantees

`LinkedHashSet` both keeps elements distinct and preserves insertion order. If you insert `3`, `1`, and then `3` again, traversal yields `[3, 1]`: it has an order, but it does not automatically sort in ascending order. [Java SE 17 — LinkedHashSet.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html#spliterator()).

`HashSet` does not guarantee traversal order. One run may print numbers that look ascending, but that is not a contract to rely on for display, testing, or pagination. [Java SE 17 — HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html).

Not having ORDERED also does not mean every traversal is forced to differ from the previous one or that the data is randomly shuffled. It only means there is no encounter order guaranteed by this characteristic.

## 4. SORTED: Order Following a Comparison Rule

`SORTED` is stronger than ORDERED: not only is there an encounter order, but that order also follows a sorting rule.

Mandatory relationship:

~~~text
SORTED  =>  ORDERED
~~~

A Spliterator that reports SORTED must also report ORDERED. The reverse is not true.

### 4.1. getComparator Distinguishes Natural Order from a Custom Comparator

If the source is sorted according to the natural order of `Comparable` elements:

~~~java
Comparator<? super Integer> cmp = source.getComparator();
~~~

`cmp` can be `null` to represent natural order. In this case, `null` is not an error indicating a missing sorting rule.

If the source uses a custom comparator, `getComparator` returns that comparator. If the Spliterator does not report SORTED, calling `getComparator` throws `IllegalStateException` per the contract.

To use it safely:

~~~java
if (source.hasCharacteristics(Spliterator.SORTED)) {
    Comparator<? super Integer> cmp = source.getComparator();
    // cmp == null means natural order.
}
~~~

This is an illustrative snippet that requires appropriate imports and source types, not a standalone program.

### 4.2. Sorted Does Not Always Mean Natural Ascending Order

A `TreeSet` created with `Comparator.reverseOrder()` can traverse `[3, 1]` and still report SORTED. It is sorted according to the reverse comparator.

`TreeSet` reports order based on natural order or the comparator provided at creation time. The comparator should be consistent with `equals` to fully obey the `Set` contract. [Java SE 17 — TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

If the goal is natural ascending order, do not see SORTED and skip the comparison requirement. In the demonstration program, a Stream from the reverse `TreeSet` still calls `sorted()` to produce `[1, 3]` in natural order.

### 4.3. SORTED and DISTINCT Are Two Separate Guarantees

A sorted sequence can still contain equal values, such as `[1, 1, 3]`. SORTED does not deduplicate elements.

Conversely, a `HashSet` can have distinct elements without a sorted order. Therefore, do not infer DISTINCT from SORTED, and do not infer SORTED from DISTINCT.

## 5. DISTINCT: Distinct According to equals

`DISTINCT` declares that the encountered elements are distinct according to the `equals` relation. It does not merely say that they are objects with different memory addresses.

Two `String` objects created separately with the same content can still be equal according to `equals`. A source that is distinct by reference identity is not enough to report DISTINCT in this general sense.

A `Set` that obeys its contract is a familiar example. With input data `[3, 1, 3]`, `HashSet` or `LinkedHashSet` retains the two values `3` and `1`. The DISTINCT characteristic tells algorithms they do not need to treat the two occurrences of `3` as two separate source elements anymore.

### DISTINCT Does Not Mean NONNULL

A `HashSet` can contain one `null` element and still have no duplicate elements. Allowing one `null` and guaranteeing distinctness are not contradictory.

`NONNULL` is a separate characteristic stating that encountered elements are never null. When an algorithm needs to skip null checks, it must have the appropriate guarantee; DISTINCT does not provide that guarantee.

### Mapping Operations Can Break Distinctness

The source `[1, 3]` has distinct values. However, the transformation `n -> 0` produces `[0, 0]`. If DISTINCT were preserved after an arbitrary mapping operation, an algorithm might skip a deduplication step even though the result now contains duplicates.

This is why you must examine the characteristics of **the source or pipeline currently in use**, not just look at the initial collection class. A transformation may preserve the element count while losing another guarantee.

For objects whose `equals` depends on mutable state, mutating objects during traversal can also break the source's assumptions. A characteristic is not a license to mutate data in a way that changes equality relations unpredictably.

## 6. SIZED: Exact Count Known Within Contract Conditions

`SIZED` states that before traversal or splitting, `estimateSize()` returns the exact finite number of elements that will be encountered in a complete traversal, provided no source modification invalidates that condition.

Do not simplify this to "estimateSize is always the exact remaining element count." Partial traversal state, splitting state, and sub-split characteristics must all be considered.

For example, with a three-element `ArrayList`, before traversal:

~~~java
Spliterator<Integer> source = numbers.spliterator();
long size = source.getExactSizeIfKnown();
~~~

In the demonstration program, `size` is `3`. Without SIZED, `getExactSizeIfKnown` returns `-1` instead of turning an estimate into a guaranteed count.

### 6.1. SIZED Does Not Mean the Source Is Immutable

A mutable `ArrayList` still has a Spliterator that reports SIZED. That does not make it immutable or safe when multiple threads modify it concurrently.

You must separate:

- Whether the exact size can be known under stable conditions.
- Whether the source is guaranteed to remain unchanged throughout the entire process.

These two questions belong to different characteristics or policies.

### 6.2. SUBSIZED Is the Guarantee for Split Parts

`SUBSIZED` is directly tied to SIZED: Spliterators created by splits will have the required size guarantees, including continuing to report SIZED and SUBSIZED per the contract.

A source that knows its total element count does not necessarily know the exact size of each split branch. Therefore:

~~~text
SUBSIZED => SIZED
SIZED does not imply SUBSIZED
~~~

The Spliterator of `ArrayList` reports all three: ORDERED, SIZED, and SUBSIZED. [Java SE 17 — ArrayList.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#spliterator()).

In the example where no elements have been traversed yet, splitting once and adding the two `estimateSize` values still gives a total of `3`. This is an appropriate case to illustrate splitting a known size. Do not use a test on one source type to assume every tree, hash table, or I/O source has the same guarantee.

### 6.3. Lacking SIZED Does Not Mean Infinite

A source may be finite yet hard to size upfront, or it may undergo concurrent modifications that make a fixed count inappropriate. `estimateSize` can still provide a useful estimate.

`Long.MAX_VALUE` can indicate unknown, too expensive to compute, or an unbounded source. Looking at that number alone is not enough to conclude that the source is definitely infinite.

Characteristics help consumers know whether a number may be treated as a guarantee or only as an estimate.

## 7. IMMUTABLE: Source Stable for the Spliterator, Not a Deep Copy

In the sense of this characteristic, the source covered by the Spliterator cannot have elements added, removed, or replaced in a way that causes changes during traversal. This is a guarantee about the **element source**, not a claim that every element object has immutable internal state.

### 7.1. CopyOnWriteArrayList Shows Why Source Scope Matters

`CopyOnWriteArrayList` is a mutable collection. However, its Spliterator holds a snapshot of the list's state at creation time and reports IMMUTABLE, ORDERED, SIZED, and SUBSIZED. [Java SE 17 — CopyOnWriteArrayList.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#spliterator()).

Example:

~~~java
CopyOnWriteArrayList<String> values =
        new CopyOnWriteArrayList<>(List.of("A", "B"));

Spliterator<String> snapshot = values.spliterator();
values.set(0, "X");
values.add("C");
~~~

When traversing `snapshot`, you still get `[A, B]`. The current list is `[X, B, C]`. The collection is not permanently locked or turned into an unmodifiable object; the Spliterator holds a snapshot source that is not replaced by those updates.

This is an easy point to misunderstand if you only read the class name or look at the word IMMUTABLE and say "this collection cannot call add."

### 7.2. Element Objects Can Still Be Mutable

If the snapshot contains a `StringBuilder`, the reference inside the snapshot is not automatically cloned:

~~~java
StringBuilder item = new StringBuilder("seed");
CopyOnWriteArrayList<StringBuilder> values = new CopyOnWriteArrayList<>();
values.add(item);

Spliterator<StringBuilder> snapshot = values.spliterator();
item.append("!");
~~~

The snapshot source still holds the same reference, so traversal sees the object representing `seed!`. No new element was added and no element reference was replaced in the snapshot; the object's internal state changed.

If you want data that is immutable at the business-content level, you need immutable element types or your own object-copying rules. IMMUTABLE does not automatically provide a deep copy.

### 7.3. A Read-Only View Does Not Automatically Become an IMMUTABLE Source

`Collections.unmodifiableList(backing)` forbids modification through that view, but anyone holding `backing` can still modify the underlying source. With the view over an `ArrayList` in the program, the Spliterator does not report IMMUTABLE, and adding `B` through `backing` is visible when reading the view.

Do not conflate these three concepts:

| Concept | What It Refers To |
| --- | --- |
| Disallowing modification through a view reference | Permissions through that access path |
| Spliterator's IMMUTABLE | The source covered by the Spliterator cannot have elements changed during the relevant operation |
| Immutable element objects | The internal state of the objects does not change |

A fixed-size list that still allows `set` is also not enough to infer IMMUTABLE. Merely not growing or shrinking the number of slots does not prevent replacing references at those slots.

## 8. CONCURRENT: Source Accepts Concurrent Updates Under Its Policy

`CONCURRENT` states that the source allows supported concurrent modifications to occur safely without requiring external callers to lock the entire source for traversal. The Spliterator must be accompanied by a policy describing the effects of such modifications.

An important example is the views of `ConcurrentHashMap`:

| View | Documented Characteristics |
| --- | --- |
| Keys | CONCURRENT, DISTINCT, NONNULL |
| Values | CONCURRENT, NONNULL |
| Entries | CONCURRENT, DISTINCT, NONNULL |

Keys are distinct, but multiple keys can share the same value, so the values view does not automatically have DISTINCT. The Spliterators of these views are weakly consistent. [Java SE 17 — ConcurrentHashMap views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#keySet()).

### 8.1. Not a Snapshot at a Single Point in Time

A traversal over a concurrent source may observe state over the duration of the traversal according to the structure's policy. It does not necessarily freeze all keys and values at the same instant.

Therefore, do not use CONCURRENT to promise that an aggregate report across multiple keys is an atomic snapshot. If business requirements demand global consistency, you must design a separate mechanism.

### 8.2. Does Not Mean Multiple Threads Can Share One Spliterator Object

This characteristic belongs to the **data source**, and does not make the Spliterator object itself safe for multiple threads to call `tryAdvance` or `trySplit` on concurrently.

Parallel processing models typically hand each split to one worker at a time. The result destination and actions must also be designed appropriately; writing to a shared output `ArrayList` from multiple threads is still not made safe just because the source reports CONCURRENT.

### 8.3. Does Not Add Mutation Operations Unsupported by Other APIs

A key view with a concurrent source does not thereby support every `add` operation. Mutation permissions through a specific API and the source's ability to tolerate concurrent modification are two different contracts.

Characteristics help manage interference on the source during traversal; they do not replace the full documentation of the `Collection` or `Map` providing the view.

## 9. Relationships and Combinations to Read Correctly

Key relationships:

~~~text
SORTED  => ORDERED
SUBSIZED => SIZED

ORDERED does not imply SORTED
SORTED does not imply DISTINCT
DISTINCT does not imply NONNULL
SIZED does not imply IMMUTABLE
CONCURRENT does not imply a thread-safe Spliterator object
IMMUTABLE does not imply deeply immutable elements
~~~

At the top-level Spliterator, CONCURRENT should not be combined with SIZED because the size can change as the source is updated. It should also not be combined with IMMUTABLE as two contradictory promises about the same source. Sub-splits may have their own guarantees if their scope has been fixed; do not generalize top-level combinations into a simple rule for all sub-splits.

If a Spliterator reports neither IMMUTABLE nor CONCURRENT, read the source's policy on binding time and modification detection. "Fail-fast" is usually only best-effort detection, not a synchronization mechanism and not proof that no access bug exists just because an exception has not been thrown yet.

### There Is No Single "Best Bit" for Everything

An IMMUTABLE source keeps the traversal's element set stable, though it may pay the cost of creating a snapshot. A CONCURRENT source allows ongoing updates, though it does not automatically provide a global snapshot. An ORDERED source is useful when results need exact ordering, though it can force some parallel operations to maintain extra constraints.

Choose characteristics to understand the source's contract accurately, not as a general quality score for collections.

## 10. Pipeline Characteristics Can Differ from the Initial Source

When a Stream wraps a Spliterator, intermediate operations can preserve or lose guarantees.

### filter Can Lose Known Size

A three-element `ArrayList` knows its input size. After `filter(n -> n > 0)`, for the specific data `[3, 1, 3]`, all three pass. However, a general filter must inspect elements before knowing how many will pass through.

In the program, the filtered pipeline's Spliterator only reports ORDERED, no longer reporting the source `ArrayList`'s SIZED and SUBSIZED. That is not an undercounting bug; the pipeline does not promise to know the output count before evaluating the predicate.

### map Can Lose SORTED and DISTINCT

The source `TreeSet` holds distinct numbers in sorted order. After `map(n -> 0)`, multiple elements become the same value. An arbitrary mapping can also scramble comparison order.

In the test case, the mapped pipeline's Spliterator still reports ORDERED and SIZED, but does not report SORTED or DISTINCT. Encounter order is preserved and each input produces one output, while the value-level guarantees are lost.

These observations help distinguish input contracts from output contracts. When writing downstream algorithms, inspect the data or Spliterator actually passed to them, not just the collection characteristics at the start of the program.

## 11. Why Wrong Declarations Can Cause Wrong Results

Library algorithms can trust declared characteristics. If a source falsely claims there are no duplicates, a deduplication step may be treated as unnecessary. If a source reports the wrong size, allocation or result-combining algorithms may rely on an invalid assumption.

The bits are therefore **an obligation of the Spliterator implementer**, not hints that the library is forced to re-verify from scratch.

If you create a custom source:

- Only report ORDERED when there is a real encounter order and splitting preserves the prefix constraint.
- Only report SORTED when both the order and `getComparator` obey the contract.
- Only report DISTINCT when `equals`-based distinctness is guaranteed for encountered elements.
- Only report SIZED and SUBSIZED when size estimates and all relevant splits meet the conditions.
- Only report IMMUTABLE or CONCURRENT according to the actual source model, not based on "no error seen yet."

`StreamSupport` is the bridge for low-level sources; the overload accepting a supplier requires the declared characteristic set to match the Spliterators created by the supplier. The library cannot automatically fix every false guarantee from a source. [Java SE 17 — StreamSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/StreamSupport.html).

When using standard collections, you rarely need to build a Spliterator yourself. Still, understanding what the bits mean is essential for explaining why a pipeline preserves order, loses a known count, or follows a different traversal policy when the source changes.

## 12. Full Demonstration Program

Save the following code as **SpliteratorCharacteristicsDemo.java**. The program is Java 17 compatible and uses the standard library.

The `flags` method only prints the names of reported bits in a fixed order for readability; the order of names in the string is not the order of source elements. The `drain` method consumes the Spliterator, so each example needs an appropriate Spliterator for its traversal.

The program does not print element order for `HashSet` or `ConcurrentHashMap` to avoid turning an unguaranteed order into an assumed stdout. The concurrency-related examples only check documented characteristics, rather than using a single sequential run to prove thread safety.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Spliterator;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

public class SpliteratorCharacteristicsDemo {
    private static String flags(Spliterator<?> source) {
        int[] bits = {
            Spliterator.ORDERED, Spliterator.SORTED, Spliterator.DISTINCT,
            Spliterator.SIZED, Spliterator.IMMUTABLE, Spliterator.CONCURRENT,
            Spliterator.SUBSIZED, Spliterator.NONNULL
        };
        String[] names = {
            "ORDERED", "SORTED", "DISTINCT", "SIZED",
            "IMMUTABLE", "CONCURRENT", "SUBSIZED", "NONNULL"
        };
        List<String> result = new ArrayList<>();
        for (int i = 0; i < bits.length; i++) {
            if (source.hasCharacteristics(bits[i])) {
                result.add(names[i]);
            }
        }
        return result.toString();
    }

    private static <T> List<T> drain(Spliterator<T> source) {
        List<T> result = new ArrayList<>();
        source.forEachRemaining(result::add);
        return result;
    }

    public static void main(String[] args) {
        List<Integer> numbers = new ArrayList<>(List.of(3, 1, 3));
        Spliterator<Integer> listSource = numbers.spliterator();
        System.out.println("array-list=" + flags(listSource));
        System.out.println("array-values=" + drain(listSource));

        System.out.println("hash-set="
                + flags(new HashSet<>(numbers).spliterator()));
        LinkedHashSet<Integer> linked = new LinkedHashSet<>(numbers);
        System.out.println("linked-set=" + flags(linked.spliterator()));
        System.out.println("linked-values=" + drain(linked.spliterator()));

        TreeSet<Integer> natural = new TreeSet<>(numbers);
        Spliterator<Integer> naturalSource = natural.spliterator();
        System.out.println("tree-set=" + flags(naturalSource));
        System.out.println("natural-comparator-null=" + (naturalSource.getComparator() == null));
        System.out.println("tree-values=" + drain(naturalSource));

        TreeSet<Integer> reverse = new TreeSet<>(Comparator.reverseOrder());
        reverse.addAll(numbers);
        Spliterator<Integer> reverseSource = reverse.spliterator();
        System.out.println("reverse-comparator-1-3=" + reverseSource.getComparator().compare(1, 3));
        System.out.println("reverse-values=" + drain(reverseSource));
        System.out.println("natural-sort-from-reverse=" + reverse.stream().sorted().toList());

        Spliterator<Integer> sortedLooking =
                new ArrayList<>(List.of(1, 2, 3)).spliterator();
        System.out.println("sorted-looking-sorted="
                + sortedLooking.hasCharacteristics(Spliterator.SORTED));
        System.out.println("sorted-looking-distinct="
                + sortedLooking.hasCharacteristics(Spliterator.DISTINCT));
        System.out.println("ordered-and-sorted="
                + sortedLooking.hasCharacteristics(Spliterator.ORDERED | Spliterator.SORTED));
        try {
            sortedLooking.getComparator();
            throw new AssertionError("Expected missing SORTED");
        } catch (IllegalStateException expected) {
            System.out.println("unsorted-getComparator -> IllegalStateException");
        }

        Spliterator<Integer> sized = numbers.spliterator();
        System.out.println("list-exact-before=" + sized.getExactSizeIfKnown());
        Spliterator<Integer> split = sized.trySplit();
        if (split == null) {
            throw new AssertionError("Expected ArrayList split");
        }
        System.out.println("split-sized="
                + split.hasCharacteristics(Spliterator.SIZED | Spliterator.SUBSIZED));
        System.out.println("split-total=" + (split.estimateSize() + sized.estimateSize()));

        CopyOnWriteArrayList<String> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Spliterator<String> snapshot = copyOnWrite.spliterator();
        System.out.println("copy-on-write=" + flags(snapshot));
        copyOnWrite.set(0, "X");
        copyOnWrite.add("C");
        System.out.println("snapshot-values=" + drain(snapshot));
        System.out.println("current-list=" + copyOnWrite);

        StringBuilder item = new StringBuilder("seed");
        CopyOnWriteArrayList<StringBuilder> objects = new CopyOnWriteArrayList<>();
        objects.add(item);
        Spliterator<StringBuilder> objectSnapshot = objects.spliterator();
        item.append("!");
        System.out.println("immutable-flag="
                + objectSnapshot.hasCharacteristics(Spliterator.IMMUTABLE));
        System.out.println("mutable-element=" + drain(objectSnapshot));

        List<String> backing = new ArrayList<>(List.of("A"));
        List<String> readOnly = Collections.unmodifiableList(backing);
        System.out.println("read-only-immutable="
                + readOnly.spliterator().hasCharacteristics(Spliterator.IMMUTABLE));
        backing.add("B");
        System.out.println("read-only-values=" + readOnly);

        ConcurrentHashMap<String, Integer> concurrent = new ConcurrentHashMap<>();
        concurrent.put("A", 1);
        concurrent.put("B", 1);
        Spliterator<String> concurrentKeys = concurrent.keySet().spliterator();
        System.out.println("concurrent-keys=" + flags(concurrentKeys));
        System.out.println("concurrent-values=" + flags(concurrent.values().spliterator()));
        System.out.println("concurrent-exact=" + concurrentKeys.getExactSizeIfKnown());

        System.out.println("filtered-list="
                + flags(numbers.stream().filter(n -> n > 0).spliterator()));
        System.out.println("mapped-tree="
                + flags(natural.stream().map(n -> 0).spliterator()));
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 SpliteratorCharacteristicsDemo.java
java SpliteratorCharacteristicsDemo
~~~

Exact stdout:

~~~text
array-list=[ORDERED, SIZED, SUBSIZED]
array-values=[3, 1, 3]
hash-set=[DISTINCT, SIZED]
linked-set=[ORDERED, DISTINCT, SIZED, SUBSIZED]
linked-values=[3, 1]
tree-set=[ORDERED, SORTED, DISTINCT, SIZED]
natural-comparator-null=true
tree-values=[1, 3]
reverse-comparator-1-3=1
reverse-values=[3, 1]
natural-sort-from-reverse=[1, 3]
sorted-looking-sorted=false
sorted-looking-distinct=false
ordered-and-sorted=false
unsorted-getComparator -> IllegalStateException
list-exact-before=3
split-sized=true
split-total=3
copy-on-write=[ORDERED, SIZED, IMMUTABLE, SUBSIZED]
snapshot-values=[A, B]
current-list=[X, B, C]
immutable-flag=true
mutable-element=[seed!]
read-only-immutable=false
read-only-values=[A, B]
concurrent-keys=[DISTINCT, CONCURRENT, NONNULL]
concurrent-values=[CONCURRENT, NONNULL]
concurrent-exact=-1
filtered-list=[ORDERED]
mapped-tree=[ORDERED, SIZED]
~~~

The code was compiled with `--release 17` and run on JDK 24.0.2. That is the API/language level at compile time and the JVM version executed; it is not a claim of running on JVM 17.

Comparing the groups:

- `array-list` and `array-values` show ORDERED alongside unsorted data that still contains duplicates.
- `hash-set` and `linked-set` separate distinctness from encounter order.
- `tree-set`, `natural-comparator-null`, and `reverse-values` distinguish two sorting rules.
- `sorted-looking` shows that data currently having a property is not enough to assert that the bit is reported.
- `ordered-and-sorted` checks both characteristics together.
- `list-exact`, `split-sized`, and `split-total` illustrate sizing with an untraversed `ArrayList` source.
- `copy-on-write` preserves the old snapshot even when the current collection changes.
- `mutable-element` shows that a structural snapshot does not make element objects deeply immutable.
- `read-only` distinguishes a view that forbids mutation from a stable source.
- The two `concurrent` lines on views distinguish distinct keys from potentially duplicate values.
- The last two lines illustrate how guarantees change after `filter` and `map`.

## 13. Practice Exercises with Answers

### Exercise 1 — Does ORDERED Require Ascending Order?

An `ArrayList` containing `[9, 2, 9]` has a Spliterator that reports ORDERED. Is that wrong because the sequence is not ascending?

**Answer:** No. ORDERED refers to the `List`'s index-based encounter order. It does not promise ascending order or distinctness. To know whether a declared comparison order exists, you must check SORTED and its corresponding rule.

### Exercise 2 — getComparator Returning null

A `TreeSet` of integers uses natural order. Its Spliterator reports SORTED, yet `getComparator()` returns `null`. Is that a missing-comparator error?

**Answer:** No. For a SORTED source, `null` represents natural order. If SORTED is not reported, calling `getComparator` throws `IllegalStateException`; you must distinguish the two cases instead of treating every `null` as an error.

### Exercise 3 — One Bit or Both Bits?

Does `s.hasCharacteristics(ORDERED | SORTED)` return `true` when `s` only reports ORDERED? What does `(flags & mask) != 0` check?

**Answer:** `hasCharacteristics` requires every bit in the mask, so it returns `false`. The other expression only asks whether at least one bit overlaps, which is not enough to confirm the source is sorted.

### Exercise 4 — DISTINCT and null

Can a `HashSet` containing `null` and `"A"` report DISTINCT? Can you rely on that to skip null checks in the processing action?

**Answer:** It can report DISTINCT because no two elements are equal. However, DISTINCT does not guarantee NONNULL; the action must still handle `null` unless another contract excludes it.

### Exercise 5 — Does SIZED Mean Every Split Is Exact?

A Spliterator reports SIZED. Can you automatically infer that it reports SUBSIZED and that every sub-split after `trySplit` keeps an exact size like `ArrayList`?

**Answer:** No. SIZED is conditional on timing and a stable source; knowing the total size does not automatically mean knowing the exact size of every split. Only SUBSIZED adds the contract guarantees for sub-splits.

### Exercise 6 — Mutable Collection with an IMMUTABLE Spliterator

Why can `CopyOnWriteArrayList` still call `add`, while a Spliterator created from it reports IMMUTABLE?

**Answer:** The Spliterator holds a stable snapshot of the source at creation time. Updates create a new state for the collection without changing the slots in the snapshot held by the Spliterator. This does not turn every element object into a deeply immutable object.

### Exercise 7 — Does CONCURRENT Allow Sharing One Spliterator?

A source reports CONCURRENT. Can two threads concurrently call `tryAdvance` on the same Spliterator object and append to a shared output `ArrayList` without any additional design?

**Answer:** No. CONCURRENT is a guarantee about the source's ability to tolerate concurrent updates, not a safety guarantee for the Spliterator object or the result collector. You still need proper work partitioning and result coordination.

### Exercise 8 — Keeping Bits Unchanged After map

A `TreeSet` source reports SORTED and DISTINCT. After `map(n -> 0)`, what goes wrong if a custom Spliterator keeps those two bits unchanged?

**Answer:** The result can contain multiple `0`s, so DISTINCT is no longer true; an arbitrary `map` also does not preserve the sorting rule. False declarations can cause library algorithms to apply invalid optimizations. You must report the characteristics of the actual output.

## 14. Using Characteristics When Reading and Writing Code

First identify which source the Spliterator covers, and at what point in time. Then use `hasCharacteristics` to ask for the exact guarantee the algorithm needs: order, sorting rule, distinctness, count, or source modification policy.

Do not infer a bit from a collection's name or from data that happens to look a certain way. When passing through a filter, mapping, or split, re-evaluate the scope of the guarantee. When multiple threads are involved, separate source safety from Spliterator ownership and shared state in actions.

Understanding the six characteristics along their separate axes explains Stream and Spliterator behavior accurately: ordered does not mean sorted; sized does not mean immutable; a structural snapshot does not mean deep copy; and a concurrent source does not mean an atomic snapshot.
