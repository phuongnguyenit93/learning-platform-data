# sort, reverse, and shuffle: Three Ways to Change the Order of a List

A list stores elements by position, but "changing the order" can serve very different purposes. Sorting scores from lowest to highest requires a comparison criterion. Reviewing history from end to start only needs reversing the existing order. Shuffling question order requires a random permutation.

`Collections.sort`, `Collections.reverse`, and `Collections.shuffle` correspond to those three purposes. They all operate on **the passed-in list**, return `void`, and do not create a separate result copy on their own. Therefore, this lesson covers two parallel questions: what order is produced, and who will observe the change.

The runnable examples use Java 17. Readers should already know `List`, `ArrayList`, references, and the basic meaning of `Comparator`. This lesson also explains sort stability and the role of the seed when shuffling.

## 1. Distinguish the Goal Before Calling the Method

| Operation | Ordering rule | Compares values? | A typical purpose |
| --- | --- | --- | --- |
| `Collections.sort(list)` | Ascending by natural order | Yes | Ordering numbers from smallest to largest |
| `Collections.sort(list, comparator)` | According to comparator | Yes | Ordering by points descending, then id ascending |
| `Collections.reverse(list)` | Position `i` moves to `n - 1 - i` | No | Reversing an existing sequence of events |
| `Collections.shuffle(list)` | Permutes positions using default random source | No | Shuffling a sequence for a practice round |
| `Collections.shuffle(list, random)` | Permutes positions using specified random source | No | Reproducing an experiment with a known seed |

All three groups of operations preserve the number of elements and the multiplicity of each element. They change positions, do not deduplicate, do not make a deep copy, and do not modify business fields inside the elements.

For example, given the sequence `[4, 1, 3, 1, 2]`:

- Ascending sort produces `[1, 1, 2, 3, 4]`.
- Reversing the original sequence produces `[2, 1, 3, 1, 4]`.
- Shuffling produces a permutation that still has two `1`s and one each of `2`, `3`, and `4`.

Reverse does not mean "descending." Shuffle also does not mean "the order is guaranteed to differ from the previous run." Choose the operation based on the postcondition you actually need.

## 2. Mutating the Input List In Place and Keeping Ownership Clear

### All three methods return `void`

Here is an illustrative snippet inside a method:

~~~java
List<Integer> values = new ArrayList<>(List.of(3, 1, 2));
Collections.sort(values);
~~~

After the call, `values` represents `[1, 2, 3]`. No new list is returned from `sort` to assign to another variable. `reverse` and `shuffle` are used the same way.

If two variables point to this same list, both observe the new order:

~~~java
List<Integer> alias = values;
Collections.reverse(values);
// alias also sees [3, 2, 1].
~~~

This is the effect of sharing the same list object, not the algorithm finding and updating every variable in the program.

### Create a working copy when the original order must be preserved

~~~java
List<Integer> original = List.of(3, 1, 2);
List<Integer> working = new ArrayList<>(original);
Collections.sort(working);
~~~

`original` keeps its old order, while `working` has the sorted order. The list constructor copies element references; it does not clone each object.

When elements are mutable objects, a separate working copy protects **the source list's order**, not all element state. If a comparator or other code mutates those objects, lists sharing those elements can all observe the change.

Make the method contract explicit: "sorts the passed-in list" versus "returns a sorted list while leaving the input unchanged." Do not make callers guess from a local variable name.

### The list must support replacing positions, not necessarily resizing

These operations do not need to add or remove elements to do their job, but they require permission to replace values at list positions or via an iterator.

A list created by `Arrays.asList(array)` has a fixed size yet supports replacing elements, so it can be sorted, reversed, and shuffled. Because it is backed by the array, the order in the array itself also changes. [Arrays.asList contract, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

Lists created by `List.of` or `List.copyOf` do not allow modification; `Collections.unmodifiableList` also does not grant modification rights through the view. If you need to reorder them, create an appropriate modifiable working copy. [Unmodifiable lists in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable).

Do not use a no-op operation on an empty or single-element list to infer mutability. An algorithm may not need to perform any position-replacement step in those cases; "not throwing an exception" does not prove the list supports general reordering.

## 3. `sort`: Ordering by a Comparison Rule

### Natural order

`Collections.sort(list)` uses the natural order of the elements. Elements must be mutually comparable under an appropriate `Comparable` contract.

~~~java
List<Integer> scores = new ArrayList<>(List.of(8, 3, 8, 5));
Collections.sort(scores);
~~~

The result is `[3, 5, 8, 8]`. Both `8`s remain; sorting is not deduplication.

Using proper generic types helps prevent putting mutually incomparable types into the same list. If you bypass type checking with raw types and mix incompatible types, do not expect `sort` to invent a sensible rule; comparison can throw `ClassCastException`.

### Comparator describes the rule for a single sort

With a test-result object, you may want to sort by points rather than the class's own natural order:

~~~java
Comparator<Attempt> byPoints =
        Comparator.comparingInt(Attempt::points);

Collections.sort(attempts, byPoints);
~~~

This snippet illustrates with an existing `Attempt` type and `attempts` variable; the complete program below declares both.

`compare(a, b)` returns a negative number when `a` comes before `b`, `0` when the two elements are equal under the sorting criterion, and a positive number when `a` comes after `b`. The returned number is neither a target index nor a boolean value.

Do not use integer subtraction such as `a.points() - b.points()` as a general comparison technique; subtraction can overflow. `Integer.compare` or `Comparator.comparingInt` expresses the comparison without that risky subtraction.

### Chain and reverse criteria at the right level

~~~java
Comparator<Attempt> order =
        Comparator.comparingInt(Attempt::points)
                .reversed()
                .thenComparing(Attempt::id);
~~~

This rule orders by points descending; when points are tied, by `id` ascending.

If you place `reversed()` after the entire `thenComparing`, both criteria are reversed. That may be right or wrong depending on the requirement, but the two forms are not equivalent.

A comparator must be consistent: for example, if `a` comes after `b` and `b` comes after `c`, the relation must be transitive so that `a` also comes after `c`. Do not return random results, do not change criteria mid-sort, and do not mutate comparison keys during sorting.

A comparator that violates its contract can lead to incorrect results or `IllegalArgumentException` if the violation is detected. Do not rely on "running once without throwing" to treat a comparator as valid. [Comparator contract, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

### `List.sort` and `Collections.sort`

With a comparator, you can write `list.sort(comparator)`. In Java 17, `Collections.sort` delegates execution to `List.sort` according to the implementation documentation.

Both calls are meant to sort the existing list. Choosing one syntax over the other does not create a copy of the input and does not change the mutability requirement.

Do not treat a specific sorting algorithm as an immutable contract for every custom list. The important guarantees when using it are ordering according to the comparison rule and stability; classes may have their own implementations that satisfy the contract. [List.sort API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

## 4. Sort Stability and the Sort-Then-Reverse Trap

### "Equal" in sorting means the comparator returns 0

Suppose the input data arrives in this exact order:

~~~text
B:2, D:1, A:2, C:1
~~~

The notation is `id:points`. When comparing only by points, `B` and `A` are considered equal under the criterion; `D` and `C` are as well, even though the objects are not equal across all fields.

A **stable** sort preserves the original relative order of elements that the comparator treats as equal.

Sorting ascending by points gives:

~~~text
D:1, C:1, B:2, A:2
~~~

`D` still comes before `C`; `B` still comes before `A`. `Collections.sort` guarantees stability. [Collections.sort API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#sort(java.util.List,java.util.Comparator)).

### Reversing the whole sequence also reverses the order within tied groups

Reversing the ascending result above gives:

~~~text
A:2, B:2, C:1, D:1
~~~

Points are now descending, but `B`/`A` and `D`/`C` swapped places. If the requirement is "points descending, and people with the same points keep their arrival order," sorting ascending and then reversing does not satisfy it.

The right approach for that requirement is to sort directly with a descending comparator. Sort stability preserves the original order within tied groups:

~~~text
B:2, A:2, D:1, C:1
~~~

If the actual requirement is "points descending, and when points are tied, id ascending," include the `id` criterion in the comparator. Then preserving arrival order is no longer the tie-breaking rule for elements with different ids.

### Stability does not create a deterministic input order on its own

If the list is built from a source that does not guarantee iteration order, preserving the initial order within tied groups only preserves the order observed during that particular build. It does not create a stable secondary rule across runs.

When a report needs deterministic output, add a meaningful tie-breaker such as a unique id. When arrival order matters, capture and preserve that order from the start.

## 5. `reverse`: Position Mapping Without Comparing Content

With `n` elements, `reverse` moves the old element at index `i` to index `n - 1 - i`. You can think of it as swapping pairs from the two ends inward toward the middle.

~~~text
before: [a, b, c, d, e]
after:  [e, d, c, b, a]
~~~

The middle element of an odd-length sequence stays in place. An empty sequence or a single-element sequence keeps the same order after reversing. With nothing else modifying the list in between, reversing twice restores the original order.

Reverse does not require elements to implement `Comparable` and does not need a comparator. If the list allows `null` elements, the operation simply swaps `null`'s position like any other element without comparing it.

### Reverse does not replace a descending sort

Given `[4, 1, 3, 1, 2]`, `reverse` produces `[2, 1, 3, 1, 4]`. The result is neither ascending nor descending.

Only when the input sequence is already sorted ascending by a criterion does reversing it produce descending order by that criterion. Even then, you still have to consider the relative order requirement within tied groups as discussed in the previous section.

### Distinguishing similar names

- `Collections.reverse(list)` modifies the order of positions in place inside the list.
- `Collections.reverseOrder()` creates a comparator that reverses natural order.
- `Collections.reverseOrder(comparator)` or `comparator.reversed()` creates a reversed comparison rule.

Creating a comparator does not reorder any list by itself. You must pass that rule to a sort operation or a data structure that uses a comparator.

If you are reading code for a newer Java version that has a reversed-view API, do not equate it with `Collections.reverse`. The focus here is the `void` method that mutates the passed-in list; the program uses Java 17 APIs.

## 6. `shuffle`: Permuting Positions Using a Random Source

### Selecting progressively from the end

One way to understand the algorithm is to walk from the last position toward the front. On each step, randomly pick a position from the unfixed prefix, including the current position itself, and swap.

The following code only illustrates the mechanism for a modifiable list; it is not a standalone program and is not meant to replace the library call:

~~~java
for (int remaining = values.size(); remaining > 1; remaining--) {
    int selected = random.nextInt(remaining);
    Collections.swap(values, remaining - 1, selected);
}
~~~

On the first step of a length-4 sequence, it picks from 4 positions to fix the end of the sequence; on the next step, from the remaining 3 positions; then 2. This is the Fisher–Yates shuffle idea.

Picking from the exact `[0, remaining)` range is crucial. A loop where "each position swaps with any random position in the entire sequence" does not produce the same permutation distribution.

With a suitable fair source of choices, the algorithm generates position permutations with equal probability. The overload without a random source is documented as producing approximately equal likelihood. Do not use a few test prints to prove a probability distribution.

### It may preserve part or all of the order

A position can be chosen to swap with itself. The identity permutation—meaning the final sequence matches the initial sequence—is still a valid outcome.

Therefore, all of the following claims are false:

- "After shuffling, every element must change position."
- "The second run must differ from the first run."
- "With the same seed, changing the input must still produce the same value sequence."
- "If there are two identical elements, the algorithm will remove one."

With duplicate elements, multiple position permutations can produce the same observable sequence of values. If all elements are equal, you cannot demand to observe a different value order even though positions participated in the shuffle.

### Do not sort with a random comparator

A random comparator does not describe a consistent ordering relation. The same pair can be compared differently across calls; transitivity can be broken.

If you want to shuffle, use `shuffle`. If you want to order by a fixed random priority value, generate those priority values explicitly and handle ties as required; do not let the comparison outcome change every time the comparator is called.

## 7. What Does a Seed Help Reproduce?

~~~java
List<String> first = new ArrayList<>(original);
List<String> second = new ArrayList<>(original);

Collections.shuffle(first, new Random(17));
Collections.shuffle(second, new Random(17));
~~~

The two `Random` sources are initialized with the same seed; the inputs to both lists have the same order. Under the same implementation, both shuffles consume the same sequence of choices and produce the same result.

`Random` has the contract that the same seed and the same sequence of method calls produce the same sequence of numbers. [Random API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html).

All of these conditions must hold together:

1. Identical input data and initial order.
2. Same type of random source and same initial state.
3. Same sequence of random-number consumption.
4. Same shuffle implementation using that sequence.

If you reuse one `Random` instance and call `shuffle` twice in a row, the second call starts from the already-advanced state. It is not equivalent to creating `new Random(seed)` again before each call. Sharing one source across multiple tasks also makes consumption history affect the outcome.

A seed is useful for recording a test scenario and reproducing a bug. It does not mean the shuffled result is a long-term data format fixed across all library algorithm changes. When you need to restore an exact published order, storing the order itself or its corresponding identifiers is a different requirement from storing only the seed.

`java.util.Random` generates pseudorandom numbers and is not suitable for cryptographic requirements. This lesson uses it for reproducible experiments and testing, not as a guarantee for every drawing mechanism with specialized requirements.

## 8. `null` and Descending Reversal Rules

### Put the `null` policy into the comparator

A list may allow `null`, but natural order does not provide a valid position for `null` when it needs to be compared with numbers. If the data contains `null`, use a comparator with an explicit policy:

~~~java
Comparator<Integer> ascendingNullLast =
        Comparator.nullsLast(Comparator.naturalOrder());

Collections.sort(values, ascendingNullLast);
~~~

For the input `[3, null, 1]`, the result is `[1, 3, null]`.

Do not build the test input with `List.of(3, null, 1)` because that factory rejects `null` before reaching the sort step. The program uses `Arrays.asList` and copies into an `ArrayList` to test the sorting step itself.

Passing a `null` comparator to `Collections.sort(list, null)` means using natural order; it does not mean automatically knowing how to order `null` elements.

### Reversing the whole rule differs from reversing only the non-`null` values

If you reverse the whole list `[1, 3, null]`, the result is `[null, 3, 1]`. To have numbers descending while keeping `null` last, use:

~~~java
Comparator<Integer> descendingNullLast =
        Comparator.nullsLast(Comparator.reverseOrder());
~~~

Then the result is `[3, 1, null]`.

Similarly, calling `reversed()` on an entire comparator that already has `nullsLast` also reverses the `null`-placement rule. You must choose the right level of reversal for the requirement.

## 9. Processing Only a Slice with `subList`

A list may have a prefix or suffix that must stay intact while the middle segment needs sorting:

~~~java
List<String> items =
        new ArrayList<>(List.of("left", "c", "a", "b", "right"));

Collections.sort(items.subList(1, 4));
~~~

`subList(1, 4)` covers indices `1`, `2`, `3`; the upper bound `4` is exclusive. It is a view over that slice of the source list, so sorting the view updates the corresponding positions in the source.

The source becomes `[left, a, b, c, right]`. You can also reverse or shuffle that view directly if modification is supported.

Do not mistake `subList` for an isolated copy to experiment on. If you need to detach from the source, create `new ArrayList<>(source.subList(from, to))` before processing.

While using the view, do not structurally add or remove elements in the source through another path and then keep relying on the old view. Ownership and view lifetime still need to be managed; reordering algorithms do not remove that contract. [List.subList API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)).

## 10. Complete Program and Exact Stdout

Save the following code to **`ListOrderingDemo.java`**. The `Attempt` type is a two-field record; the program uses only stable numbers and strings as comparison data.

Stdout does not contain a default random shuffle sequence that would need to be predicted. Instead, the shuffle section checks the occurrence count of each value, equality when using two sources with the same seed, and that the original source remains intact.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.TreeMap;

public class ListOrderingDemo {
    record Attempt(String id, int points) {
        @Override
        public String toString() {
            return id + ":" + points;
        }
    }

    private static Map<String, Integer> counts(List<String> values) {
        Map<String, Integer> result = new TreeMap<>();
        for (String value : values) {
            result.merge(value, 1, Integer::sum);
        }
        return result;
    }

    private static void rejects(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(4, 1, 3, 1, 2);
        List<Integer> reversed = new ArrayList<>(source);
        Collections.reverse(reversed);
        List<Integer> ascending = new ArrayList<>(source);
        Collections.sort(ascending);
        List<Integer> descending = new ArrayList<>(source);
        Collections.sort(descending, Comparator.reverseOrder());
        System.out.println("numbers.source=" + source);
        System.out.println("numbers.reversed=" + reversed);
        System.out.println("numbers.asc=" + ascending);
        System.out.println("numbers.desc=" + descending);

        List<Attempt> attempts = List.of(
                new Attempt("B", 2),
                new Attempt("D", 1),
                new Attempt("A", 2),
                new Attempt("C", 1));
        Comparator<Attempt> byPoints =
                Comparator.comparingInt(Attempt::points);
        List<Attempt> stableAscending = new ArrayList<>(attempts);
        Collections.sort(stableAscending, byPoints);
        List<Attempt> reverseAfterSort = new ArrayList<>(stableAscending);
        Collections.reverse(reverseAfterSort);
        List<Attempt> stableDescending = new ArrayList<>(attempts);
        Collections.sort(stableDescending, byPoints.reversed());
        List<Attempt> descendingThenId = new ArrayList<>(attempts);
        Collections.sort(descendingThenId,
                byPoints.reversed().thenComparing(Attempt::id));
        System.out.println("attempts.original=" + attempts);
        System.out.println("attempts.asc=" + stableAscending);
        System.out.println("attempts.ascThenReverse=" + reverseAfterSort);
        System.out.println("attempts.descStable=" + stableDescending);
        System.out.println("attempts.descThenId=" + descendingThenId);

        List<Integer> nullable =
                new ArrayList<>(Arrays.asList(3, null, 1));
        Collections.sort(nullable,
                Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("nulls.ascLast=" + nullable);
        Collections.reverse(nullable);
        System.out.println("nulls.reverseWhole=" + nullable);
        List<Integer> descendingNullLast =
                new ArrayList<>(Arrays.asList(3, null, 1));
        Collections.sort(descendingNullLast,
                Comparator.nullsLast(Comparator.reverseOrder()));
        System.out.println("nulls.descLast=" + descendingNullLast);

        Integer[] backing = {3, 1, 2};
        List<Integer> fixed = Arrays.asList(backing);
        Collections.sort(fixed);
        System.out.println("fixed.afterSort=" + Arrays.toString(backing));
        Collections.reverse(fixed);
        System.out.println("fixed.afterReverse=" + Arrays.toString(backing));
        Collections.shuffle(fixed, new Random(17));
        List<Integer> fixedCheck = new ArrayList<>(fixed);
        Collections.sort(fixedCheck);
        System.out.println("fixed.shufflePreserves="
                + fixedCheck.equals(List.of(1, 2, 3)));

        List<String> window =
                new ArrayList<>(List.of("left", "c", "a", "b", "right"));
        Collections.sort(window.subList(1, 4));
        System.out.println("window.afterSort=" + window);
        Collections.reverse(window.subList(1, 4));
        System.out.println("window.afterReverse=" + window);

        List<String> original = List.of("A", "B", "A", "C", "D");
        List<String> first = new ArrayList<>(original);
        List<String> second = new ArrayList<>(original);
        Collections.shuffle(first, new Random(17));
        Collections.shuffle(second, new Random(17));
        System.out.println("shuffle.sameSeed=" + first.equals(second));
        if (!counts(first).equals(counts(original))) {
            throw new AssertionError("shuffle changed multiplicities");
        }
        System.out.println("shuffle.counts=" + counts(first));
        System.out.println("shuffle.source=" + original);
        List<String> defaultRandom = new ArrayList<>(original);
        Collections.shuffle(defaultRandom);
        System.out.println("shuffle.defaultPreserves="
                + counts(defaultRandom).equals(counts(original)));

        List<Integer> linked =
                new LinkedList<>(List.of(1, 2, 3, 4, 5, 6, 7, 8));
        Collections.shuffle(linked, new Random(17));
        Collections.sort(linked);
        System.out.println("linked.afterShuffleThenSort=" + linked);

        List<Integer> twice = new ArrayList<>(source);
        Collections.reverse(twice);
        Collections.reverse(twice);
        System.out.println("reverse.twice=" + twice.equals(source));

        List<Integer> readonly = List.of(3, 1, 2);
        rejects("sort.readonly", () -> Collections.sort(readonly));
        rejects("reverse.readonly", () -> Collections.reverse(readonly));
        rejects("shuffle.readonly",
                () -> Collections.shuffle(readonly, new Random(17)));

        List<String> empty = new ArrayList<>();
        Collections.sort(empty);
        Collections.reverse(empty);
        Collections.shuffle(empty, new Random(17));
        System.out.println("empty.size=" + empty.size());
        List<String> single = new ArrayList<>(List.of("only"));
        Collections.sort(single);
        Collections.reverse(single);
        Collections.shuffle(single, new Random(17));
        System.out.println("single.value=" + single);
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 ListOrderingDemo.java
java ListOrderingDemo
~~~

JDK 17 or higher is required for this compilation command. The code was compiled with `--release 17` and run on OpenJDK 24.0.2, exiting successfully with the following exact stdout:

~~~text
numbers.source=[4, 1, 3, 1, 2]
numbers.reversed=[2, 1, 3, 1, 4]
numbers.asc=[1, 1, 2, 3, 4]
numbers.desc=[4, 3, 2, 1, 1]
attempts.original=[B:2, D:1, A:2, C:1]
attempts.asc=[D:1, C:1, B:2, A:2]
attempts.ascThenReverse=[A:2, B:2, C:1, D:1]
attempts.descStable=[B:2, A:2, D:1, C:1]
attempts.descThenId=[A:2, B:2, C:1, D:1]
nulls.ascLast=[1, 3, null]
nulls.reverseWhole=[null, 3, 1]
nulls.descLast=[3, 1, null]
fixed.afterSort=[1, 2, 3]
fixed.afterReverse=[3, 2, 1]
fixed.shufflePreserves=true
window.afterSort=[left, a, b, c, right]
window.afterReverse=[left, c, b, a, right]
shuffle.sameSeed=true
shuffle.counts={A=2, B=1, C=1, D=1}
shuffle.source=[A, B, A, C, D]
shuffle.defaultPreserves=true
linked.afterShuffleThenSort=[1, 2, 3, 4, 5, 6, 7, 8]
reverse.twice=true
sort.readonly=UnsupportedOperationException
reverse.readonly=UnsupportedOperationException
shuffle.readonly=UnsupportedOperationException
empty.size=0
single.value=[only]
~~~

### Explaining the result groups

**`numbers`:** `reverse` is applied to a copy of the unsorted sequence, so the result is not descending. The ascending and descending sorts use the appropriate criteria. The source has two `1`s and every copy preserves the occurrence counts.

**`attempts`:** ascending sort keeps `D` before `C` and `B` before `A`. Reversing that result flips the tied groups. Direct descending sort from the input keeps `B` before `A` and `D` before `C`. When the ascending `id` criterion is added, tie order is determined by `id` instead of original order.

**`nulls`:** reversing the whole sequence moves `null` from the end to the front; the descending comparator specifically for non-`null` values keeps `null` last as required.

**`fixed`:** a fixed-size list still allows replacing positions. The first two lines print the backing array again to demonstrate the effect through the view. The shuffle check verifies the multiset of elements with occurrence counts rather than asserting a specific permutation.

**`window`:** sorting and reversing the middle slice mutates the same source list, while the two boundary elements stay unchanged.

**`shuffle`:** two shuffles under the same conditions produce equal results. The count map has two `A`s and one each of `B`, `C`, and `D`. The default shuffle also preserves occurrence counts even though the random sequence is not printed. `original` stays unchanged because the shuffles use copies.

**`linked`:** `shuffle` also works with a modifiable `LinkedList`. The subsequent `sort` restores ascending order of the values; this line checks content, not performance.

**`reverse.twice`:** two consecutive reversals restore the original sequence.

**Exception lines:** lists created by `List.of` do not support replacing positions. The program tests each algorithm individually on multi-element data, rather than using a no-op case to infer mutability.

**`empty` and `single`:** modifiable working lists at the 0- and 1-element boundaries remain valid. There is no need to write special-case branches just to avoid a reordering call on them.

## 11. Mechanisms, Costs, and Limits to Know

### Sort depends on both the list and the comparator

For commonly used standard lists, comparison sorting typically costs around `O(n log n)`; adaptive implementations can take advantage of existing order in the data. Do not treat that formula as a promise for every custom list class or expensive comparator.

If every comparison reads a file, calls a service, or computes an expensive value, comparator cost can dominate total time. Determine stable comparison keys before sorting when the model allows.

The `List.sort` documentation describes using an intermediate array in the default implementation to avoid sorting based on slow indexed access of linked lists. It also describes an adaptive, stable algorithm. This is information about the implementation, not a requirement that every list must stick to one specific algorithm class.

### Reverse and shuffle do linear work in standard implementations

Reverse needs to swap symmetric pairs of positions. Shuffle needs to progressively fix positions. `Collections` documents both operations as running in linear time.

For large lists without `RandomAccess`, the shuffle implementation can dump data into an array, shuffle it, and write it back, avoiding repeated indexed access that would lead to quadratic cost. Therefore, "mutating the passed-in list" does not mean "never allocating temporary memory." [Shuffle mechanism in Collections, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#shuffle(java.util.List,java.util.Random)).

For `ArrayList`, positional access has constant cost by the class's contract. For `LinkedList`, indexed access must traverse nodes. Do not write your own `get(i)`/`set(i)` loop and assume it has the same cost on both. [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

### No rollback guarantee if an operation fails

A comparator can throw an exception mid-comparison; a custom list can also reject a modification step. Do not rely on the assumption that if an exception is thrown, the input is guaranteed to remain as it was before.

If you need to protect the original list from a sort that might fail, process a working copy and publish the result only upon success. The comparator must still avoid side effects on shared elements.

### Coordination is needed if the list is used concurrently

Reordering is a multi-step process. Do not let other threads arbitrarily read or write the same list mid-operation and treat the result as a consistent snapshot.

A per-method synchronized wrapper does not automatically turn every multi-step sequence of operations into a transaction according to business requirements. When needed, apply an ownership/locking protocol for the entire process, or create a privately owned working copy and publish the result appropriately.

Do not use `ConcurrentModificationException` as a data-protection mechanism. Detecting unexpected modification does not replace proper coordination.

## 12. Testing What Actually Needs to Be Guaranteed

### For sort

Verify the result against the comparator and verify that no elements are missing or extra. If stability matters, include at least two distinguishable elements for which the comparator returns `0` so you can observe their relative order.

If there are multiple criteria, choose data with ties on the first criterion and differences on the later criterion. If all scores are distinct, tests will not catch an accidentally reversed secondary criterion.

### For reverse

Check position mapping or a specific expected sequence. Test both even and odd element counts when writing an algorithm yourself. The property that reversing twice returns to the original is useful, yet not enough to prove an arbitrary algorithm is `reverse`: a no-op function also satisfies that property.

The program in this lesson includes both concrete reverse results and the double-reverse property to avoid relying on too weak a piece of evidence.

### For shuffle

Check the size and occurrence count of each element. Converting the list to a set and comparing is not enough: `[A, A, B]` and `[A, B, B]` have the same member set but different multiplicities.

Use a controlled seed when you need to reproduce a scenario. Do not assert that "the order must differ from before," because the identity permutation is valid. Do not prove a fair distribution from one or a few runs.

A property test such as "preserves elements" is also not enough by itself to prove the algorithm shuffles with the right distribution: a no-op function still preserves elements. Correctness of the selection mechanism must rely on the algorithm and the random source contract, while experiments help catch specific implementation bugs.

## 13. Practice with Answers

### Exercise 1 — Does reverse make a list descending?

The input `[2, 5, 1, 4]` is passed directly to `Collections.reverse`.

**Question:** What is the result? What should you use to sort numbers descending?

**Answer:** The result is `[4, 1, 5, 2]`, not descending order. Use `Collections.sort(list, Comparator.reverseOrder())` on a modifiable list to get `[5, 4, 2, 1]`. Reverse depends only on the current positional order.

### Exercise 2 — Preserving arrival order on tied points

The data arrives in order `P:2, Q:1, R:2, S:1`. The requirement is points descending, and tied points preserve arrival order.

**Question:** What does sorting ascending then reversing produce? What does sorting descending directly produce?

**Answer:** A stable ascending sort gives `Q:1, S:1, P:2, R:2`; reversing next gives `R:2, P:2, S:1, Q:1`, which does not preserve the initial tie order. Sorting directly with a descending-points comparator gives `P:2, R:2, Q:1, S:1` and meets the requirement.

### Exercise 3 — Where to place `reversed`?

The requirement is points descending, but name ascending when points are tied.

**Question:** Do the following two comparators have the same meaning?

~~~java
Comparator<Attempt> a =
        Comparator.comparingInt(Attempt::points)
                .reversed()
                .thenComparing(Attempt::id);

Comparator<Attempt> b =
        Comparator.comparingInt(Attempt::points)
                .thenComparing(Attempt::id)
                .reversed();
~~~

**Answer:** No. `a` reverses the points criterion and then adds `id` ascending. `b` reverses the entire composed rule, so when points are tied, `id` is descending. This changes the sorting requirement, not just the phrasing.

### Exercise 4 — Fixed size, yet reorderable

~~~java
Integer[] array = {2, 3, 1};
List<Integer> values = Arrays.asList(array);
Collections.sort(values);
Collections.reverse(values);
~~~

**Question:** What is the final array? Why is `add` not needed?

**Answer:** The final array is `[3, 2, 1]`. The operations only replace values at existing slots; the list supports replacing elements and writes through to the array. The size remains 3. That does not apply to an unmodifiable list just because it also has size 3.

### Exercise 5 — Same seed is not enough

Two lists have the same set of strings but different initial orders. Each list is shuffled with its own `new Random(42)`.

**Question:** Can we assert that the two results must have the same value sequence? If reproduction is needed, what should be saved?

**Answer:** No. Applying the same sequence of position choices to two different initial orders does not necessarily yield the same value sequence. To reproduce an experiment, keep the input data and initial order, the seed, the source type, and how the source is consumed. If a published order must be preserved long-term, save the order itself or its identifiers.

### Exercise 6 — Must shuffle change the sequence?

The input is `[A, A, A]`. A test requires that the result must differ from the input and every element must move to a different position.

**Question:** Does that requirement match the contract?

**Answer:** No. Every position permutation yields the same value sequence `[A, A, A]`. Even when elements are distinguishable, some positions can still stay in place and the identity permutation can occur. Test that occurrence counts are preserved and use an algorithm/random source with an appropriate contract, rather than demanding a forced different result.

### Exercise 7 — `null` last, yet values descending

There is a modifiable list containing `[null, 2, 1]`. The required result is `[2, 1, null]`.

**Question:** Is sorting ascending with `nullsLast` and then reversing correct? Write the appropriate comparator.

**Answer:** No; sorting ascending produces `[1, 2, null]`, and then reversing puts `null` at the front. Use `Comparator.nullsLast(Comparator.reverseOrder())` to reverse the order of the numbers while keeping the `null`-last policy.

### Exercise 8 — View or separate copy?

~~~java
List<String> source =
        new ArrayList<>(List.of("L", "b", "a", "R"));
List<String> middle = source.subList(1, 3);
Collections.sort(middle);
~~~

**Question:** What does `source` become? If the source needs to stay unchanged, how should `middle` be created?

**Answer:** The source becomes `[L, a, b, R]` because `middle` is a view of positions `1` and `2`. You need to create `new ArrayList<>(source.subList(1, 3))` before sorting to have a separate list for ordering. The copy still shares the elements if they are mutable objects; in this example, the elements are strings.

When handling order, identify the required criterion or permutation, the list's mutability rights, and the data sources that must remain intact. Sort uses a comparison relation, reverse uses current positions, and shuffle uses random choices; those differences determine both how you write the code and how you verify it.
