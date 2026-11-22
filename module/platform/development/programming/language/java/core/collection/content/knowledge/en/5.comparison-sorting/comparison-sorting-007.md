# List Sort Stability and Handling Tied Elements

When sorting a list by score, priority, or creation date, multiple elements may share the same key. That raises two separate questions:

1. In what order should the different key groups appear?
2. Within a tied group, which element comes first?

**Stable sort** answers the second question by preserving the relative order that tied elements already had before the sort.

Stability is useful when the input order carries meaning, such as application arrival order. However, it does not automatically turn an unordered source into a fully deterministic result, nor does it invent missing secondary business criteria.

## 1. Ties Under a Comparison Rule

Suppose a list contains the following records:

| Initial Position | ID | Rank Used for Sorting |
| --- | --- | --- |
| 0 | C | 2 |
| 1 | D | 1 |
| 2 | A | 2 |
| 3 | B | 1 |
| 4 | E | 2 |

The rule is that a smaller rank comes first:

~~~java
// Entry is a type with a rank() method returning int.
Comparator<Entry> byRank = Comparator.comparingInt(Entry::rank);
~~~

D and B are tied because:

~~~java
byRank.compare(d, b) == 0
~~~

C, A, and E are also tied with one another under this comparator.

The records may have different IDs, be distinct objects, and not be `equals` to each other. "Tied" here simply means the comparator returns `0` under the criterion in use.

After an ascending stable sort by rank:

~~~text
Before: C:2, D:1, A:2, B:1, E:2
After:  D:1, B:1, C:2, A:2, E:2
~~~

The two groups are reordered by rank. Within group `1`, D still precedes B. Within group `2`, C still precedes A, and A still precedes E.

There is no requirement that IDs increase alphabetically. If alphabetical ID ordering is required on ties, that is an additional criterion that must be expressed separately.

## 2. Exact Definition of Stability

Let the elements before sorting be `x0, x1, ..., xn-1`. With comparator `c`, if:

~~~text
i < j
and c.compare(xi, xj) == 0
~~~

then a stable sort keeps the occurrence `xi` before the occurrence `xj` in the result.

This definition is about **relative order**:

- The two elements may move to new indices.
- The distance between them may change.
- However, the element that came first in a tied pair still comes first after sorting.

In the data above, D moves from index `1` to `0`; B moves from `3` to `1`. The relative order of D before B is preserved even though both indices change.

Stability also applies to occurrences in a list containing duplicate elements. In practice, you need data with distinct labels or identifiers to clearly observe two elements with the same key; if you only print `[1, 1, 2]`, it is hard to tell whether the two `1`s swapped internally.

### Do Not Confuse "Stable" with Other Properties

| Property | Question It Answers |
| --- | --- |
| Correct sorting by comparator | Does the result follow the ordering relation? |
| Stable sorting | Do elements that compare equal keep their pre-sort relative order? |
| Non-mutating source | Does the operation modify the input list? |
| Data-deterministic result | Does the dataset have enough rules to select one specific order? |
| Thread-safe under concurrent access | Are proper synchronization rules and structures in place to avoid conflicts? |

A sort can be both stable and in-place mutating. Stability also does not replace synchronization across threads.

## 3. Guarantees of the List Sorting API

`List.sort(comparator)` guarantees stability. A contract-compliant implementation must not reorder elements that the comparator considers equal. This is an API requirement, not merely an accidental side effect of a current algorithm. See [List.sort in Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

~~~java
// values must be a list that supports reordering elements.
values.sort(byRank);
~~~

`Collections.sort(list, comparator)` also guarantees stability; the natural-ordering overload carries the corresponding guarantee. See [Collections.sort in Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#sort(java.util.List,java.util.Comparator)).

~~~java
Collections.sort(values, byRank);
~~~

Neither call leaves the source untouched. If you need to preserve the source, create a new list:

~~~java
List<Entry> sorted = new ArrayList<>(source);
sorted.sort(byRank);
~~~

This creates a list holding element references from the source; it does not automatically deep-copy each object.

### Does the List Support Sorting?

An unmodifiable list such as the result of `List.of(...)` does not become modifiable just because the sort operation is guaranteed to be stable.

~~~java
List<Integer> fixed = List.of(3, 1, 2);

// fixed.sort(Comparator.naturalOrder());
// If executed, this mutating call throws UnsupportedOperationException.
~~~

Do not equate "fixed size" with "cannot replace elements". For example, `Arrays.asList(...)` creates a fixed-size list that still supports element replacement and sorting; changes are reflected in the backing array. Stability and mutability are independent concerns that must be read from their respective contracts.

## 4. compare Returning 0 Is Not equals

Consider the type:

~~~java
// Type declaration used in this article.
record Entry(String id, int rank) {}
~~~

And two objects:

~~~java
Entry first = new Entry("C", 2);
Entry second = new Entry("A", 2);
~~~

Record `equals` checks both ID and rank, so the two objects are not equal. A comparator that checks only rank still returns `0`.

When stably sorting by rank, C and A are treated as tied even though they are not `equals`. C stays before A if C was before A prior to the sort.

### Example with BigDecimal

`BigDecimal` demonstrates this distinction with a built-in type:

~~~java
BigDecimal first = new BigDecimal("1.0");
BigDecimal second = new BigDecimal("1.00");

System.out.println(first.equals(second));    // false
System.out.println(first.compareTo(second)); // 0
~~~

The two values have the same numerical magnitude but different scales. When sorting a list in natural order, stability considers `compareTo == 0`, not `equals`.

In the complete program below, the input order of `1.0` and `1.00` is preserved; the same holds for `2.00` and `2.0`.

You do not need to align a comparator with `equals` to use it for sorting a list. However, if you use the same comparator for a `TreeSet` or `TreeMap`, a `0` result also determines duplicate elements or key equivalence; that responsibility must be evaluated separately.

## 5. Which Order Does a Stable Sort Preserve?

It preserves the order **immediately before that sort call**, not some original history that the program never recorded.

For example:

1. Data arrives in the order C, D, A, B, E.
2. Another operation sorts or reverses the list.
3. Only afterward is the list sorted by rank.

Stability at step 3 preserves the tied order of the list as it stood after step 2.

If the business rule is "on ties, first come first served", you must ensure reliable arrival-order information is available:

- Maintain arrival order in the input source passed to the sort.
- Or store an arrival sequence number field and use that field as a secondary criterion.
- If timestamps are used, define how to handle multiple records with identical timestamps.

Do not assume an identifier or current index represents arrival time unless the data model guarantees it.

### Sources Without an Ordering Guarantee

If a list is built from a `HashSet` or a query without an explicit ordering rule, the input order may vary across runs.

A stable sort by rank will preserve whatever tied order it receives on each run. It cannot recover lost insertion history or guess the desired ordering rule.

Do not call that variation "List.sort is unstable" when the input itself differs each time. To verify stability, you must compare against the exact sequence immediately preceding the sort under test.

## 6. Choosing a Tie-Handling Policy

There are at least three reasonable policies, depending on requirements:

| Policy | When Appropriate | How to Express It |
| --- | --- | --- |
| Keep current order within tied groups | The source already has a meaningful sequence that should be preserved | Use the primary-criterion comparator with a stable sort. |
| Use a meaningful secondary criterion | A clear rule independent of input order is needed within tied groups | Chain `thenComparing` in the proper hierarchy. |
| Keep shared business rank but separate display order | Elements must be treated as tied for business ranking while still needing a consistent display sequence | Use a secondary key for display, while still computing ties from the primary business criterion. |

### Keeping Current Order

~~~java
List<Entry> result = new ArrayList<>(source);
result.sort(Comparator.comparingInt(Entry::rank));
~~~

Do not add an ID criterion if the pre-sort order is what must be preserved within tied groups. Adding ID changes the policy.

### Sorting IDs Ascending Within the Same Rank

~~~java
Comparator<Entry> displayOrder =
        Comparator.comparingInt(Entry::rank)
                .thenComparing(Entry::id);
~~~

With the source C:2, D:1, A:2, B:1, E:2, the result becomes:

~~~text
B:1, D:1, A:2, C:2, E:2
~~~

C and A are no longer tied **under the full comparator**, because the ID distinguishes them. Therefore, A appearing before C does not violate sort stability.

Stability applies after evaluating the entire comparator, not just the first key the programmer happens to focus on.

### Shared Business Rank Does Not Require Identical Display Position

Two candidates with the same score may both need to receive rank `1`, even if the screen sorts names ascending for readability. If you determine ties using a comparator that already includes name or ID, you can accidentally turn two people with the same score into two different ranks.

Separate:

- The rule that determines business-level ties.
- The rule that selects display order.
- The rule that assigns rank numbers, if needed.

Sorting does not automatically compute ranking tables such as `1, 1, 3` or `1, 1, 2`. Those rules belong to a separate processing step.

## 7. Descending Order and the Post-Sort Reverse Trap

Suppose you want larger ranks first while preserving relative order within tied groups:

~~~java
List<Entry> descending = new ArrayList<>(source);
descending.sort(byRank.reversed());
~~~

From the sample data, the result is:

~~~text
C:2, A:2, E:2, D:1, B:1
~~~

Within rank `2`, C still precedes A, which precedes E. Within rank `1`, D still precedes B.

An approach that looks equivalent at first glance is sorting ascending and then reversing the whole list:

~~~java
List<Entry> reversed = new ArrayList<>(source);
reversed.sort(byRank);
Collections.reverse(reversed);
~~~

The result is:

~~~text
E:2, A:2, C:2, B:1, D:1
~~~

`Collections.reverse` also reverses the internal sequence of every tied group. The initial sort was still stable; a subsequent operation changed the relative order.

Therefore:

~~~text
sorting with a reversed comparator
~~~

is not equivalent in tie-handling policy to:

~~~text
sorting with the original comparator and then reversing the entire result
~~~

You must decide whether you want to reverse the order of the groups or reverse every element.

When multiple criteria are involved, the placement of `reversed()` also matters. Placing it after the entire comparator chain flips both primary and secondary criteria; placing it immediately after the primary comparator flips only the primary part built up to that point.

## 8. Multi-Pass Sorting Based on Stability

Suppose you want ascending rank, and ascending ID within the same rank.

A single comparator expresses this directly:

~~~java
Comparator<Entry> order =
        Comparator.comparingInt(Entry::rank)
                .thenComparing(Entry::id);

values.sort(order);
~~~

You can also use multiple stable sort passes, from the least significant criterion to the most significant criterion:

~~~java
values.sort(Comparator.comparing(Entry::id));  // Secondary criterion first.
values.sort(Comparator.comparingInt(Entry::rank)); // Primary criterion second.
~~~

The final pass groups elements by rank. Because it is stable, within each same-rank group it preserves the ID order established in the previous pass.

Do not swap those two lines arbitrarily:

~~~java
values.sort(Comparator.comparingInt(Entry::rank));
values.sort(Comparator.comparing(Entry::id));
~~~

Here the final pass prioritizes ID across the entire list. It does not magically mean "only sort by ID within tied rank groups".

The multi-pass technique relies on:

- The stability of the sort operations used to preserve secondary order.
- Applying keys from least significant to most significant.
- The data and comparators not changing meaning between passes.

A `thenComparing` chain usually makes the hierarchy clearer to readers. Understanding the multi-pass technique is still useful for seeing what information a stable sort actually preserves.

## 9. If You Need the Original Order, Save It Before Losing It

In some processing pipelines, a list undergoes multiple transformations yet still needs to fall back to the policy "on equal rank, order by initial arrival position".

You can attach the position to each occurrence before changing the order:

~~~java
// Illustrates declarations inside a class; Entry is already defined.
record IndexedEntry(Entry value, int originalPosition) {}

List<IndexedEntry> tagged = new ArrayList<>();
for (int i = 0; i < source.size(); i++) {
    tagged.add(new IndexedEntry(source.get(i), i));
}

Comparator<IndexedEntry> order =
        Comparator.comparingInt(
                (IndexedEntry entry) -> entry.value().rank()
        ).thenComparingInt(IndexedEntry::originalPosition);

tagged.sort(order);
~~~

`originalPosition` only has meaning relative to the chosen `source` sequence at the moment of tagging. It does not automatically become an entity ID or a system-wide sequence number.

This approach also distinguishes occurrences when the exact same object appears in the source multiple times. If you instead recorded positions using a `Map<Entry, Integer>`, elements that are `equals` to each other or are the same object instance would overwrite one another's position information.

If the business domain already has a stable intake sequence number, prefer that domain field over reconstructing positions from an already shuffled source.

## 10. Ties at a Top-N Cutoff Boundary

A rule like "take the first N elements after sorting" does not yet specify what to do when the cutoff slices through a tied group.

Consider the list sorted by rank:

~~~text
D:1, B:1, C:2, A:2, E:2
~~~

If you take `1` element:

- A strict count-limit policy returns D.
- A policy that includes the entire tied group sharing the rank of the last selected element returns D and B.

Both can be valid, but the choice must be stated explicitly.

If you use ID as a secondary criterion for display while still wanting to include all business-tied elements at the cutoff, you must determine the boundary tie group using the primary rank comparator, not the full display comparator. If the full comparator distinguishes every ID, no tied group remains under it.

For a policy that includes the entire boundary tie group:

1. Sort according to the chosen display rule.
2. Locate the boundary for the initial count, if data is present.
3. Continue taking elements that share the same business rank as the boundary element.
4. Explicitly handle the cases where N is `0`, N exceeds the list size, or the input is empty.

Stability helps keep a consistent order within a group; it does not choose pagination, count-limiting, or prize-awarding policies for you.

## 11. Complete Program

Save as **StableListSortDemo.java**. The example uses records with distinct IDs so the internal ordering of each group can be observed directly.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class StableListSortDemo {
    record Entry(String id, int rank) {}

    public static void main(String[] args) {
        List<Entry> source = List.of(
                new Entry("C", 2),
                new Entry("D", 1),
                new Entry("A", 2),
                new Entry("B", 1),
                new Entry("E", 2)
        );

        Comparator<Entry> byRank = Comparator.comparingInt(Entry::rank);

        List<Entry> ascending = new ArrayList<>(source);
        ascending.sort(byRank);
        System.out.println("Stable ascending = " + ids(ascending));

        List<Entry> usingCollections = new ArrayList<>(source);
        Collections.sort(usingCollections, byRank);
        System.out.println("Collections.sort = " + ids(usingCollections));

        List<Entry> descending = new ArrayList<>(source);
        descending.sort(byRank.reversed());
        System.out.println("Stable descending = " + ids(descending));

        List<Entry> reversedAfterSort = new ArrayList<>(ascending);
        Collections.reverse(reversedAfterSort);
        System.out.println("Ascending then reverse = "
                + ids(reversedAfterSort));

        List<Entry> explicitTieBreak = new ArrayList<>(source);
        explicitTieBreak.sort(byRank.thenComparing(Entry::id));
        System.out.println("Rank then id = " + ids(explicitTieBreak));

        List<Entry> multiPass = new ArrayList<>(source);
        multiPass.sort(Comparator.comparing(Entry::id));
        multiPass.sort(byRank);
        System.out.println("Id first, then stable rank = " + ids(multiPass));

        List<Entry> anotherInput = List.of(
                new Entry("B", 1),
                new Entry("D", 1),
                new Entry("E", 2),
                new Entry("A", 2),
                new Entry("C", 2)
        );
        List<Entry> anotherSorted = new ArrayList<>(anotherInput);
        anotherSorted.sort(byRank);
        System.out.println("Different input, rank only = "
                + ids(anotherSorted));
        anotherSorted.sort(byRank.thenComparing(Entry::id));
        System.out.println("Different input, rank then id = "
                + ids(anotherSorted));

        List<BigDecimal> amounts = new ArrayList<>(List.of(
                new BigDecimal("2.00"),
                new BigDecimal("1.0"),
                new BigDecimal("2.0"),
                new BigDecimal("1.00")
        ));
        amounts.sort(Comparator.naturalOrder());
        System.out.println("BigDecimal stable natural order = " + amounts);
        System.out.println("1.0 equals 1.00 = "
                + new BigDecimal("1.0").equals(new BigDecimal("1.00")));
        System.out.println("1.0 compareTo 1.00 = "
                + new BigDecimal("1.0").compareTo(new BigDecimal("1.00")));

        System.out.println("Original = " + ids(source));
    }

    private static List<String> ids(List<Entry> values) {
        List<String> result = new ArrayList<>();
        for (Entry value : values) {
            result.add(value.id());
        }
        return result;
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 StableListSortDemo.java
java StableListSortDemo
~~~

Stdout:

~~~text
Stable ascending = [D, B, C, A, E]
Collections.sort = [D, B, C, A, E]
Stable descending = [C, A, E, D, B]
Ascending then reverse = [E, A, C, B, D]
Rank then id = [B, D, A, C, E]
Id first, then stable rank = [B, D, A, C, E]
Different input, rank only = [B, D, E, A, C]
Different input, rank then id = [B, D, A, C, E]
BigDecimal stable natural order = [1.0, 1.00, 2.00, 2.0]
1.0 equals 1.00 = false
1.0 compareTo 1.00 = 0
Original = [C, D, A, B, E]
~~~

### Result Explanation

**Stable ascending** and **Collections.sort**

Both produce D, B, C, A, E. These are the two rank groups in ascending order, with the original relative order preserved inside each group.

**Stable descending**

C, A, E come before D, B. The reversed comparator flips the order of the groups, but elements with the same rank still tie under the reversed comparator, so the order within each group is preserved.

**Ascending then reverse**

The result flips to E, A, C, B, D. The reversal happens after sorting and reverses the internal order of the groups as well.

**Rank then id**

ID is used to break ties, so rank group `1` becomes B, D and rank group `2` becomes A, C, E. This expresses a different requirement from simply preserving input sequence.

**Id first, then stable rank**

Sorting by ID first and then stably sorting by rank produces the same result as the compound comparator. The ID ordering information is preserved within the groups of the final sort.

**Different input, rank only**

The alternative source placed B before D, and E before A before C. A proper stable sort must preserve those sequences within each group, producing a different result from sorting the same set of records in the original input order.

**Different input, rank then id**

When ID is added as a secondary criterion, two differently ordered sources containing the same records produce the same result B, D, A, C, E in this example.

**BigDecimal**

`1.0` stays before `1.00`, and `2.00` stays before `2.0`, matching the pre-sort order of the `compareTo == 0` groups. The `equals` line shows that two numbers with the same magnitude are not necessarily `equals` when their scales differ.

**Original**

The sorts operate on modifiable copies. The source data remains C, D, A, B, E. This comes from copying the list, not from sort stability.

## 12. Testing Sort Stability Properly

Tests in which every element has a distinct key cannot detect whether tied elements swap places. You should deliberately construct test data with:

- Multiple tied groups.
- Elements of the same group interleaved with other groups.
- Distinct labels to track each individual occurrence.
- Label sequences that do not accidentally coincide with ascending ID order.

The C:2, D:1, A:2, B:1, E:2 dataset in this article was chosen to make this visible. If you used A:1, B:1, C:2, D:2, accidentally adding an ascending ID criterion would still yield the same output, causing the test to miss a policy bug.

A thorough check should separate at least three properties:

1. **Content preservation:** no elements are lost, added, or duplicated with wrong multiplicities.
2. **Primary ordering correctness:** every adjacent pair satisfies the comparator.
3. **Stability correctness:** for elements that compare equal, their pre-sort relative order is preserved.

When elements carry their own original positions, after sorting you can group adjacent elements that compare equal under the comparator and verify that original positions strictly increase within each group.

Do not write a stability test that always asserts ascending IDs if the comparator does not inspect IDs. That tests a different business rule.

Include edge cases as well: empty input, single element, all elements tied, no elements tied, and `null` elements if both the comparator and the list permit them. A `nullsFirst` or `nullsLast` comparator decides where `null` goes; a stable sort does not automatically add `null`-handling capability to a comparator that rejects `null`.

## 13. Limitations and Unwarranted Inferences

### A Stable Sort Cannot Fix a Broken Comparator

If a comparator overflows by subtracting two numbers, changes its outcome over time, or violates transitivity, the result has no sound basis for meeting the intended meaning.

An algorithm may detect certain violations and throw an exception, but the absence of an exception does not prove the comparator is valid. Comparison keys should remain stable during sorting, and the rule must be consistent.

### Stability Does Not Mean Preserving Indices

Only the relative order of tied pairs is preserved. Changing indices is normal sorting behavior; never store an element's list index as a long-lived entity identifier.

### Stability Is Not a Universal Property of Every Ordered Structure

Do not infer from `List.sort`'s guarantee that every other algorithm or data structure handles ties the same way. For example, do not rely on `PriorityQueue` to automatically preserve FIFO order among elements with equal priority; if FIFO within a priority group is required, provide an explicit policy and tie-breaking criterion.

### Stability Does Not Permanently Maintain the Sorted State

After sorting, appending new elements or mutating comparison keys inside existing objects can leave the list out of order. A `List` does not automatically re-sort itself whenever data changes.

### Stability Does Not Compensate for Changing Source Data

If records or datasets change between reads, results may change even when the full comparator and the sort operation are both right. When a reproducible report is required, you must pin both the data snapshot and the rule version, not just add a sort call.

## 14. Common Mistakes

| Misconception | Proper Understanding |
| --- | --- |
| Stable sort does not change element positions | It preserves relative order within tied groups; indices can still change. |
| Tied means `equals` to each other | For sorting, ties are determined by the comparator or natural ordering. |
| Stable sort always produces the exact same result from the same dataset | If the source arrives in a different sequence and tied groups remain, the order within groups can differ. |
| Adding ID must still preserve the old order of all elements with the same score | Once ID is added, elements with different IDs are no longer tied under the full comparator. |
| Sorting ascending and then reversing is equivalent to a stable descending sort | Reversing flips the internal order of tied groups as well. |
| Sorting by primary key and then secondary key performs a multi-criteria sort | The final sort affects the entire sequence; multi-pass stable sorting must run from secondary to primary. |
| Using a TreeSet instead of a sorted List keeps every element | A comparator returning `0` in a TreeSet causes those elements to be treated as occupying the same slot. |
| `limit(N)` or taking N elements automatically includes everyone tied at the cutoff | Boundary tie policies must be designed explicitly. |

## 15. Exercises

1. Write out the stable ascending and stable descending results by hand for the sequence `X:3, A:1, B:3, C:1, D:3`.
2. Add an ascending ID criterion. Identify the pairs that were previously tied but are no longer tied under the full comparator.
3. Compare direct descending sort against ascending sort followed by reverse; circle the same-rank pairs whose order gets flipped.
4. Create two sources containing the same set of records but in different sequences within rank groups. Verify that stable sorting by rank yields different yet equally valid results.
5. Choose the policy "equal ranks are ordered by arrival sequence". Design a data source or sequence-number field that preserves that meaning across multiple processing steps.
6. Given a requirement to take the top three elements, construct data where a tied group straddles the third position. Write out both results under the strict count-limit policy and the whole-boundary-group policy.
7. Write a stability check using each occurrence's distinct original position, then test it on data containing objects that are `equals` to each other or the same object instance appearing multiple times.

Before implementing any sorting requirement involving ties, clarify what counts as a tie, which sequence must be preserved within a group, and whether a secondary display rule is needed. The stability of `List.sort` is a tool for executing your chosen policy, not a substitute for choosing one.
