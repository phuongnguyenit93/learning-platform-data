# estimateSize, getExactSizeIfKnown, and Source Characteristics

## 1. A Spliterator Needs to Know More Than "What Is the Next Element?"

A `Spliterator` supports both traversing elements and splitting a portion of data into smaller units of work. To decide how to split, how to size a target container, or whether a processing step can be skipped, the library needs information about the source.

There are two main categories of information:

- **Size:** approximately how many elements remain; whether that count is guaranteed to be exact.
- **Characteristics:** whether there is an encounter order, whether elements are distinct, whether they are sorted, whether `null` may be present, and what modification policy the source follows.

This descriptive information is commonly referred to as metadata. It is a contract reported by the spliterator. It is not the result of automatically scanning the entire source to verify every property.

For example, an `ArrayList` with four elements can provide its count before traversal. An iterator backed by a data-generation process may not know in advance how many elements it will yield. Both can be represented by a `Spliterator`, but the library must not apply the same size assumptions to both.

Three questions must be distinguished:

| Question | Commonly Related API |
| --- | --- |
| Can the number of elements to be encountered be estimated? | `estimateSize()` |
| Does the spliterator report an exact size by contract? | `getExactSizeIfKnown()`, `SIZED` |
| What guarantees accompany traversing or splitting the source? | `characteristics()`, `hasCharacteristics(...)` |

"Four elements in the original collection," "four elements remaining in this spliterator's portion of work," and "four elements remaining after a filter" are also different things. This article moves from the size of a spliterator to source characteristics and how they change during processing.

The standalone programs use Java 17. Save each file using the exact name of its `public class`; compile commands and stdout are recorded right after each program.

## 2. estimateSize Is an Estimate, Not a Counting Command

`estimateSize()` returns a `long` estimating the number of elements that traversing the remaining portion would encounter. When the source is infinite, its size is unknown, or computing the count is too expensive, the method may return `Long.MAX_VALUE`.

Therefore:

- A finite return value does not by itself prove that the number is exact.
- `Long.MAX_VALUE` does not prove that the source is definitely infinite.
- The returned value is not the capacity of an array allocated for the collection.
- It describes the portion of work belonging to the spliterator being queried, not always the total size of the original source.

`estimateSize()` is not a terminal stream operation that counts by traversing every element. It is designed to provide information usable for organizing execution, even when that information is only approximate. [Javadoc Spliterator.estimateSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html#estimateSize())

An estimate still has practical value. For instance, knowing that one portion of work is likely larger than another helps decide whether to split further. However, never treat an unguaranteed estimate as an exact count to conclude that all data has been processed.

### SIZED Places Exactness Conditions on the Estimate

The `SIZED` characteristic indicates that the reported size is guaranteed to be exact under the conditions of the contract. Timing matters greatly:

1. If a spliterator is `SIZED` and has not been partially traversed or split, the estimate must be the exact number of elements for a valid full traversal.
2. If a spliterator is `SUBSIZED` and has not been partially traversed, the exactness guarantee also applies after splitting.
3. Outside those conditions, do not look at the flag alone and assume every implementation always updates the exact remaining element count after each `tryAdvance`.

These guarantees also assume the source is not interfered with contrary to its policy. Do not use a previously obtained count to prove that the source cannot change.

Some classes update the remaining size very accurately after each step. The `ArrayList` program below demonstrates that behavior. This is a welcome property of a specific implementation, not a reason to ignore the state conditions of the interface contract.

## 3. getExactSizeIfKnown Does Not Traverse to Find the Answer

The default implementation of `getExactSizeIfKnown()` has logic equivalent to the following illustrative snippet:

```java
// Illustrative code for default logic, not a standalone program.
return hasCharacteristics(Spliterator.SIZED) ? estimateSize() : -1L;
```

It asks whether the spliterator reports `SIZED`. If so, it returns `estimateSize()`; otherwise, it returns `-1`. The method does not turn an unknown-size source into a counted source. [Javadoc getExactSizeIfKnown](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html#getExactSizeIfKnown())

The method name must be read together with the spliterator's state contract:

- Prior to traversal or splitting, `SIZED` is the basis for using an exact count.
- When a source has a stronger guarantee such as `SUBSIZED`, exactness can be preserved across splits under the corresponding conditions.
- Once partially traversed, the default implementation still only checks `SIZED` and delegates to `estimateSize()`; it does not add an independent counting mechanism.

Consequently, when writing a general-purpose algorithm for any `Spliterator`, do not use the word "exact" in the method name to generalize that the number returned in every state is always an updated remaining counter.

### -1 and 0 Have Different Meanings

`-1` is a signal that an exact size is not reported. It is not a negative quantity of data and does not mean the source is empty.

`0` is a count. For a fresh spliterator with a guaranteed exact size and a valid source, `0` indicates there are no elements to traverse.

If you genuinely need the element count of an unknown-size source, you must choose a counting operation that traverses it. That consumes the corresponding spliterator or stream, can be expensive, and cannot complete on an infinite source. Reading metadata and traversing to count are two different tasks.

## 4. Experiment: ArrayList Size During Traversal and Splitting

Save as `SpliteratorSizesDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class SpliteratorSizesDemo {
    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4, 5, 6));
        Spliterator<Integer> remaining = source.spliterator();

        System.out.println("initialEstimate=" + remaining.estimateSize());
        System.out.println("initialExact=" + remaining.getExactSizeIfKnown());
        System.out.println("sized=" + remaining.hasCharacteristics(Spliterator.SIZED));
        System.out.println("subsized="
                + remaining.hasCharacteristics(Spliterator.SUBSIZED));

        List<Integer> first = new ArrayList<>();
        remaining.tryAdvance(first::add);
        System.out.println("first=" + first);
        long beforeSplit = remaining.estimateSize();
        System.out.println("estimateAfterOne=" + beforeSplit);
        System.out.println("exactAfterOne=" + remaining.getExactSizeIfKnown());

        Spliterator<Integer> prefix = remaining.trySplit();
        if (prefix == null) {
            throw new IllegalStateException("Expected a split for this ArrayList");
        }
        System.out.println("prefixExact=" + prefix.getExactSizeIfKnown());
        System.out.println("remainingExact=" + remaining.getExactSizeIfKnown());
        System.out.println("splitEstimatesAddUp="
                + (beforeSplit == prefix.estimateSize() + remaining.estimateSize()));

        List<Integer> left = new ArrayList<>();
        List<Integer> right = new ArrayList<>();
        prefix.forEachRemaining(left::add);
        remaining.forEachRemaining(right::add);
        System.out.println("prefixValues=" + left);
        System.out.println("remainingValues=" + right);
        System.out.println("remainingEstimateAfterDrain=" + remaining.estimateSize());
        System.out.println("source=" + source);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SpliteratorSizesDemo.java
java SpliteratorSizesDemo
```

Stdout:

```text
initialEstimate=6
initialExact=6
sized=true
subsized=true
first=[1]
estimateAfterOne=5
exactAfterOne=5
prefixExact=2
remainingExact=3
splitEstimatesAddUp=true
prefixValues=[2, 3]
remainingValues=[4, 5, 6]
remainingEstimateAfterDrain=0
source=[1, 2, 3, 4, 5, 6]
```

Initially, the spliterator covers six elements, so both the estimate and the exact size are 6. It reports `SIZED` and `SUBSIZED`.

After `tryAdvance`, element `1` has been processed. For the `ArrayList` spliterator in this program, the remaining count is updated to 5.

The next `trySplit` returns a spliterator for the prefix `[2, 3]`; `remaining` keeps `[4, 5, 6]`. You can visualize it as:

```text
Initial:                [1, 2, 3, 4, 5, 6]  size 6
Traversed:              [1]
Remaining before split: [2, 3, 4, 5, 6]     size 5
After split:
  prefix                [2, 3]              size 2
  remaining             [4, 5, 6]           size 3
```

The sum of the two post-split estimates equals the pre-split estimate: `2 + 3 = 5`. This is the relationship `SUBSIZED` requires when a split succeeds.

The spliterators process disjoint portions of work; `trySplit` does not duplicate every element so that both objects traverse the entire source. After `remaining`'s portion is drained, its estimate in this example is 0. The source list still retains all six numbers.

### SIZED and SUBSIZED Are Not Interchangeable

`SIZED` describes the size information of the current spliterator under the stated conditions. `SUBSIZED` adds the guarantee that child spliterators created directly or indirectly via `trySplit` also have `SIZED` and `SUBSIZED`.

A structure may know its total number of elements without storing the exact element count of each smaller branch. In that case, reporting `SIZED` on the root spliterator is not enough to report `SUBSIZED`.

The relationships to remember are:

```text
SUBSIZED ⇒ SIZED
SIZED ⇏ SUBSIZED
```

The `2/3` split ratio in the program is an observed result for `ArrayList` in that specific state. Do not require every source to always split strictly in half. A source may be unable to split or may decide not to split due to cost; `trySplit()` returning `null` does not by itself prove that the source is empty.

## 5. Experiment: A Finite Source of Unknown Size

Save as `UnknownSizeSpliteratorDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;

public class UnknownSizeSpliteratorDemo {
    public static void main(String[] args) {
        Spliterator<String> unknown = Spliterators.spliteratorUnknownSize(
                List.of("red", "blue", "green").iterator(),
                Spliterator.ORDERED);

        System.out.println("estimateIsMax="
                + (unknown.estimateSize() == Long.MAX_VALUE));
        System.out.println("exact=" + unknown.getExactSizeIfKnown());
        System.out.println("sized=" + unknown.hasCharacteristics(Spliterator.SIZED));

        List<String> visited = new ArrayList<>();
        unknown.tryAdvance(visited::add);
        System.out.println("first=" + visited);
        System.out.println("estimateAfterOneIsMax="
                + (unknown.estimateSize() == Long.MAX_VALUE));
        System.out.println("exactAfterOne=" + unknown.getExactSizeIfKnown());

        unknown.forEachRemaining(visited::add);
        System.out.println("allVisited=" + visited);
        System.out.println("actualVisitedCount=" + visited.size());
        System.out.println("exactAfterDrain=" + unknown.getExactSizeIfKnown());
        System.out.println("hasAnother=" + unknown.tryAdvance(visited::add));

        Spliterator<String> empty = Spliterators.emptySpliterator();
        System.out.println("knownEmptyEstimate=" + empty.estimateSize());
        System.out.println("knownEmptyExact=" + empty.getExactSizeIfKnown());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 UnknownSizeSpliteratorDemo.java
java UnknownSizeSpliteratorDemo
```

Stdout:

```text
estimateIsMax=true
exact=-1
sized=false
first=[red]
estimateAfterOneIsMax=true
exactAfterOne=-1
allVisited=[red, blue, green]
actualVisitedCount=3
exactAfterDrain=-1
hasAnother=false
knownEmptyEstimate=0
knownEmptyExact=0
```

The source has only three strings. However, the program intentionally wraps the iterator with `Spliterators.spliteratorUnknownSize`, so the spliterator does not report `SIZED`. This helper method also does not report `SIZED` or `SUBSIZED` even if the caller passes those flags in the characteristics argument. [Javadoc spliteratorUnknownSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterators.html#spliteratorUnknownSize(java.util.Iterator,int))

Reading the output lines:

- `estimateIsMax=true`: `Long.MAX_VALUE` is used to indicate there is no useful finite estimate at this time.
- `exact=-1`: no exact size is reported.
- `first=[red]`: the spliterator still traverses normally even though its size is unknown.
- After one element, the estimate in this implementation remains `Long.MAX_VALUE`.
- `actualVisitedCount=3`: actual traversal processed three elements.
- `exactAfterDrain=-1`: the `SIZED` flag does not magically appear just because the end was reached.
- `hasAnother=false`: `tryAdvance` directly confirms there are no more elements for that call.
- The empty spliterator created by `emptySpliterator` reports both an estimate and an exact size of 0.

This shows that **size unknown** and **no elements** are two different states.

### Do Not Use Metadata Instead of Traversal Conditions

Do not write a general loop like "traverse while `getExactSizeIfKnown() > 0`." For an unknown-size source, the value `-1` will cause you to skip a source that actually has data.

Likewise, do not use "`estimateSize() == Long.MAX_VALUE`, so stop because the source is infinite." The program just verified a finite source that has that exact estimate value.

When the goal is to traverse elements one by one, use the result of `tryAdvance` or an appropriate traversal operation. When the goal is to decide a strategy, read the metadata together with its guarantees.

### Counting a Source Consumes It

The `actualVisitedCount` variable in the example is derived from the list of values collected after traversal. This is a verification that incurs the cost of traversing and storing the results.

If you only need a count, you can use a counting reduction instead of storing everything. Even so, you cannot reuse an already-consumed spliterator to walk the source again. If you want both the results and the count, design the processing to retain the needed information or create a new spliterator from a re-traversable source.

## 6. Which Characteristics Directly Relate to Size?

`characteristics()` is a bitmask advertising the spliterator's guarantees. You can call `hasCharacteristics(mask)` to ask whether the spliterator has **all** bits in the mask. When making decisions about size, the two bits to check first are:

| Bit | What Is Guaranteed |
| --- | --- |
| `SIZED` | The estimated size is exact when traversal-state conditions are met and the source is not interfered with contrary to contract. |
| `SUBSIZED` | Spliterators created directly or indirectly via `trySplit` continue to carry the `SIZED` and `SUBSIZED` guarantees. |

The relationship is `SUBSIZED ⇒ SIZED`, whereas `SIZED` does not imply `SUBSIZED`. Thus, a spliterator that knows the count of the whole source may still not know the exact size of each split portion. By default, `getExactSizeIfKnown()` relies on `SIZED` and `estimateSize()`; it does not recount the remaining elements itself.

Other bits answer different questions: `ORDERED` concerns encounter order, `SORTED` concerns sorting rules, `DISTINCT` concerns elements being distinct according to `equals`, `NONNULL` concerns the absence of null elements, `IMMUTABLE` concerns source stability during traversal, and `CONCURRENT` concerns the source's update policy. The absence of a bit does not mean the opposite property is necessarily true. The conditions and relationships of each bit are analyzed separately in the article *ORDERED, SORTED, DISTINCT, SIZED, IMMUTABLE, and CONCURRENT*.

## 7. Comparing Sources Instead of Inferring Size from Class Names

On JDK 17, a standard `ArrayList` spliterator has `SIZED` and `SUBSIZED`, so the example in Section 4 verifies the sizes of both halves after splitting. A `TreeSet` spliterator reports `SIZED` but not `SUBSIZED`: knowing the total element count is not enough to require every sub-branch to have an exact count. A source wrapping an iterator with `spliteratorUnknownSize`, as in Section 5, does not report `SIZED` even when the actual data is finite.

`CopyOnWriteArrayList` uses snapshot-based traversal and reports `IMMUTABLE`, whereas a `ConcurrentHashMap` key view reports `CONCURRENT` and does not commit to an exact size like an atomic snapshot when the source can be updated. This is a difference in **source policy**, not proof that a spliterator or processing function is automatically safe when multiple threads mutate state outside the pipeline.

When writing an algorithm, check the bits of the **Spliterator object actually in use**, rather than taking a flag table from another class and extrapolating. The next section examines why Stream operations themselves can alter that metadata.

## 8. Source Size Is Not the Size of Every Pipeline

A list with four elements does not mean every stream starting from it knows the output element count in advance.

- A regular `map` transforms each input element into one output element, so it can preserve size information.
- `filter` may drop any number of elements depending on values and predicates; before evaluation, the output count is generally unknown.
- `limit` can update the size information according to a known bound.
- Other steps can also alter characteristics such as `DISTINCT` or `SORTED`.

You must query the metadata of the exact spliterator being processed, not take the initial source metadata and apply it verbatim to the output.

Save as `StreamSizeMetadataDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class StreamSizeMetadataDemo {
    private static void describe(String name, Spliterator<?> spliterator) {
        System.out.println(name + ":estimate=" + spliterator.estimateSize()
                + ",exact=" + spliterator.getExactSizeIfKnown()
                + ",sized=" + spliterator.hasCharacteristics(Spliterator.SIZED));
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                List.of("A", "BB", "CCC", "DDDD"));

        describe("source", source.spliterator());
        describe("mapped", source.stream().map(String::length).spliterator());

        Spliterator<String> filtered = source.stream()
                .filter(value -> value.length() >= 3)
                .spliterator();
        describe("filtered", filtered);
        List<String> selected = new ArrayList<>();
        filtered.forEachRemaining(selected::add);
        System.out.println("filteredActual=" + selected);
        System.out.println("filteredActualCount=" + selected.size());

        describe("limited", source.stream().limit(2).spliterator());
        System.out.println("source=" + source);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 StreamSizeMetadataDemo.java
java StreamSizeMetadataDemo
```

Stdout:

```text
source:estimate=4,exact=4,sized=true
mapped:estimate=4,exact=4,sized=true
filtered:estimate=4,exact=-1,sized=false
filteredActual=[CCC, DDDD]
filteredActualCount=2
limited:estimate=2,exact=2,sized=true
source=[A, BB, CCC, DDDD]
```

Here are the verified results on JDK 17:

| Case | Estimate | Reported Exact Size | Observation |
| --- | --- | --- | --- |
| `ArrayList` source | 4 | 4 | Count known before traversal |
| After `map(String::length)` | 4 | 4 | Element count unchanged |
| After `filter` keeping strings of length >= 3 | 4 | -1 | Exact number of passing strings unknown |
| After `limit(2)` on a sized source | 2 | 2 | Implementation can compute the size bound |

For `filtered`, the estimate of 4 is not the actual result count. Upon traversal, only `CCC` and `DDDD` match, so the actual count is 2.

Do not generalize that every estimate without `SIZED` is always a tight upper bound or always equals the source element count. The general contract permits inaccurate estimates; the table only describes the specific spliterators in this program.

Also do not use this example to assert that every source or every stream implementation must report the exact same set of flags after each operation. Consumers read the actual guarantees reported, while the processing result must still obey the stream operation's contract.

### Taking a Spliterator from a Stream Transfers Traversal Control

`Stream.spliterator()` is a special terminal operation that lets the caller control traversal directly. After obtaining the spliterator, do not continue using that same stream object for another terminal operation. [Javadoc BaseStream.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html#spliterator())

The program creates a new stream for each case: `mapped`, `filtered`, and `limited`. Specifically, `filtered` is traversed via the obtained spliterator rather than going back to call `toList()` on an already-consumed stream.

Calling `estimateSize` or `getExactSizeIfKnown` on the spliterator does not mean elements have been processed. However, obtaining the spliterator from the stream already establishes how that stream is used; do not confuse these two lifecycles.

## 9. Querying Size Can Bind the Source Early

A late-binding spliterator does not necessarily lock in the source's extent at creation time. Under the contract for this kind of spliterator, the first traversal, first split, or first query for estimated size can be the point at which it binds to the source.

Therefore, "just peeking at the size" is not necessarily a complete no-op for the spliterator's lifecycle.

The snippet below illustrates the milestone to watch out for, not an example program with guaranteed post-modification traversal results:

```java
List<String> source = new ArrayList<>(List.of("A", "B"));
Spliterator<String> spliterator = source.spliterator();

long initialEstimate = spliterator.estimateSize();
// The size query has bound the ArrayList spliterator to its source.

source.add("C");
// Do not continue treating this as the same situation as adding before binding.
// Further traversal on the bound spliterator may detect interference.
```

By default, `getExactSizeIfKnown` calls `estimateSize` when `SIZED` is present, so it can trigger that binding as well.

Do not log descriptive metadata once and assume the spliterator is still in a state that has never touched the source. If you need to process data after modifying an ordinary collection, create a new spliterator at a valid point or design a dedicated snapshot.

### Having an Exact Size Does Not Mean the Source Is Immutable

`SIZED` describes the count under valid conditions; it does not provide a lock or prevent another party from modifying the source. `ArrayList` still requires adherence to the non-interference policy during traversal.

A fail-fast spliterator may throw `ConcurrentModificationException` when it detects a change, but detection is not guaranteed to catch every case. The absence of an exception does not prove the data was not interfered with.

Similarly, `CONCURRENT` does not solve every consistency requirement. If the source is changing, read the source's policy to understand how traversal may observe updates, rather than demanding a fixed size throughout the process.

## 10. Use Metadata to Choose Strategies, Not to Invent Guarantees

### Preparing Containers

If an exact size is available in a guaranteed state, that information can help size a target container appropriately. If only an estimate or an unknown value is available, the container needs to grow dynamically.

Before using a `long` value to create an `int`-sized container, check the range. Never cast `Long.MAX_VALUE` or `-1` into an array size and treat it as an actual element count.

In ordinary application code, stream collectors typically handle these decisions already. There is no need to build a custom allocation algorithm just to replace a clear collect call.

### Splitting Work

`estimateSize` helps gauge the scale of a portion of work; `SUBSIZED` adds guarantees about the sizes of split parts. However, knowing the size does not mean every element has the same processing cost.

Two portions with the same element count can still take very different amounts of time. Conversely, a source with an imprecise estimate can still split and process efficiently. Flags are inputs to a strategy, not performance measurements.

### Optimizing Stream Operations

Knowing the count and characteristics can help the library choose a better execution path. For example, when the count is known and intermediate steps do not change the element count, a `count` operation may not need to traverse every element. This is also why you should not place mandatory side effects inside an observation step and assume it will always be invoked. [Javadoc Stream.count](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count())

Never attach `SIZED`, `SORTED`, or `DISTINCT` to a spliterator just hoping the library will run faster. If the reported information is false, consumers may skip work that is actually required.

### Pitfalls to Recognize

| Misconception | Correction |
| --- | --- |
| `estimateSize` is always the true element count | Check `SIZED`, `SUBSIZED`, traversal state, and source policy |
| `Long.MAX_VALUE` proves the source is infinite | It can also indicate unknown size or that computing size is too expensive |
| `getExactSizeIfKnown` counts the entire source itself | The default implementation only checks the flag and returns metadata or `-1` |
| `-1` means out of data | Use traversal operations to check for remaining elements; `-1` means size unknown |
| Having `SIZED` means all split children have it too | Distinguish it from the `SUBSIZED` guarantee |
| A partially traversed spliterator always reports the exact remaining count | Read guarantees by state and implementation; do not generalize from one example |
| `ORDERED` means `SORTED` | Index order or insertion order is not sorted order |
| Lacking `NONNULL` means nulls are definitely present | Missing a flag only means that commitment is not provided |
| `IMMUTABLE` makes every element object immutable | It describes the element source for the traversal, not deep immutability |
| `CONCURRENT` lets multiple parties use the same spliterator arbitrarily | Separate source update policy from concurrent access to the spliterator object itself |
| `hasCharacteristics` with mask A and B only requires one flag | The method requires all flags in the mask to be present |
| Querying size does not affect source binding state | On late-binding sources, querying size can trigger binding |

## 11. Practice Reading Guarantees Correctly

### Exercise 1: A Finite Number Without SIZED

A spliterator reports `estimateSize() == 100` but does not have `SIZED`. Can 100 be used as the guaranteed total number of elements that will be traversed? What does the default `getExactSizeIfKnown()` return?

**Check:**

You cannot assert the true count is 100 from the estimate alone. The default implementation returns `-1` because `SIZED` is absent. A finite number and a guaranteed exact size are two different conditions.

### Exercise 2: A Three-Element Source with a Huge Estimate

`spliteratorUnknownSize` wraps the iterator of a three-element list. It reports `Long.MAX_VALUE` and `-1` from the two size methods. Is data lost, or is the source necessarily infinite?

**Check:**

No to both questions. The wrapper does not provide an exact size, yet it still traverses all three elements. You can verify this with `tryAdvance` or `forEachRemaining`; doing so actually consumes the elements.

### Exercise 3: Total Known, Parts Unknown

A root spliterator has `SIZED` but not `SUBSIZED`. After `trySplit`, can we assume every child spliterator has an exact size?

**Check:**

No. You must inspect the characteristics and contract of each child spliterator. The root's `SIZED` guarantee does not automatically create a recursive guarantee about the sizes of split parts.

### Exercise 4: Data Currently Has No Nulls

An `ArrayList<String>` currently contains `[A, B]`, yet its spliterator does not report `NONNULL`. Is this a contradiction?

**Check:**

No. Both current values are non-`null`, but the class does not provide a `NONNULL` guarantee through that spliterator. The absence of a flag does not mean the opposite assertion holds.

### Exercise 5: Sorting and Natural Order

A spliterator has `SORTED`, and `getComparator()` returns `null`. Must it still report `ORDERED`? Does `null` mean the source is unsorted?

**Check:**

It must still have `ORDERED`. When `SORTED` is present, a `null` return value indicates natural ordering. If `SORTED` is absent, calling `getComparator` does not return `null` to mean "unknown"—it throws `IllegalStateException`.

### Exercise 6: Flags Before and After Filtering

A source has four strings, but only two satisfy the predicate. The pipeline spliterator after `filter` reports an estimate of 4 and an exact size of `-1`. Which number should be used as the actual result count?

**Check:**

There is no actual result count from that metadata yet. You must execute the processing to know that two strings pass the filter. Do not assign 4 as the result size just because it is the source size or the reported estimate.

### Exercise 7: Reading a Multi-Flag Mask

A spliterator has `ORDERED` and `SIZED`, but not `SORTED`. Predict:

```java
// Question snippet; s is a spliterator with the characteristics stated above.
boolean first = s.hasCharacteristics(Spliterator.ORDERED | Spliterator.SIZED);
boolean second = s.hasCharacteristics(Spliterator.ORDERED | Spliterator.SORTED);
```

**Check:**

The first expression returns `true`; the second returns `false`. All requested flags must be present.

### Exercise 8: Checking After Partial Traversal

In `SpliteratorSizesDemo`, after traversing the first element, both methods return 5. Can this result be turned into a mandatory rule for every `SIZED` spliterator after each `tryAdvance`?

**Check:**

No. The program verifies `ArrayList`'s implementation in a specific state. The general estimate contract distinguishes untraversed, split, and partially traversed states. The default `getExactSizeIfKnown` implementation does not add remaining-count tracking on its own.

When designing a new processing operation, explicitly state which spliterator is being queried, what has already been consumed or split, what policy governs source modifications, and which flags are actually reported. Only with that information can metadata be used according to its true meaning.
