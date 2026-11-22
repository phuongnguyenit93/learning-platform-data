# swap, rotate, and replaceAll

## 1. Three Ways to Modify an Existing List

A task list might need to swap two items, move the trailing group to the front, or replace all old labels with a new label. All three needs preserve the number of positions in the list, but act on the data according to different rules.

The `java.util.Collections` utility class provides static methods for these operations:

| Method | Question it answers | Target modified | Return value |
| --- | --- | --- | --- |
| `swap(list, i, j)` | Which two positions need their elements exchanged? | The passed-in List itself | `void` |
| `rotate(list, distance)` | By how many positions should the sequence shift cyclically? | The passed-in List itself | `void` |
| `replaceAll(list, oldVal, newVal)` | All occurrences of which value need to be replaced? | The passed-in List itself | `boolean` indicating whether any element matched |

These are **in-place** operations: call the method, then read the same List again to see the result. They do not return a new transformed List. If two variables hold the same List, modifications made through one variable are also observed through the other.

You can picture a List as a sequence of slots indexed from 0. `swap` exchanges what two slots hold; `rotate` rearranges the references cyclically; `replaceAll` finds slots with matching elements and assigns the replacement value. These operations do not automatically deep-copy element objects.

An important difference is how the target is specified: `swap` uses indices, `rotate` uses a shift distance, and `replaceAll` uses value equality. Therefore, an input that is valid for one operation is not necessarily valid or meaningful for another.

Readers should know that a List is ordered, indices start at 0, `get` reads an element, and `set` replaces the element at a position. All programs below are standalone and use Java 17. Save each program with its exact filename; compile commands and stdout are shown right after the code.

## 2. Keeping the Same Size Still Requires Write Permission

A List may allow replacing elements while disallowing increasing or decreasing the number of elements. This is a sufficient condition for many operations in this lesson, because they mainly require the ability to replace elements via `set` or the corresponding mechanism of the List iterator.

For example, `Arrays.asList(array)` creates a fixed-size List backed directly by the array. It cannot be used to add a new position, but it can replace elements at existing positions. Utilities that replace element references can operate on that List, and the changes are observed in the array.

Conversely, a List from `List.of`, `List.copyOf`, or a read-only wrapper does not allow replacing elements. The fact that `swap` and `rotate` preserve `size()` does not make them read-only operations. A call that needs to mutate can still be rejected with `UnsupportedOperationException`.

If you need a separate result from a read-only source, prepare a mutable List, such as `new ArrayList<>(source)`, and apply the utility to your own copy. That choice also changes the relationship with the source: holders of the original source do not see operations performed on the copy's container.

Do not use the `List<?>` type in the signature of `swap` or `rotate` to infer that the parameter is read-only. Both methods can move references already inside the List itself to other positions without needing to accept a new element from the outside. Actual mutability depends on the List object.

## 3. swap: Exchanging Exactly Two Positions

For `Collections.swap(list, i, j)`, both `i` and `j` must be in the range from 0 to `list.size() - 1`. An index equal to `size()` is not valid for an existing element position.

If the two indices are different, the old element at `i` moves to `j` and the old element at `j` moves to `i`. Other positions remain unchanged. If the two indices are the same and the call completes normally, the contents do not change. Do not use that no-op case to guess the mutability of every kind of List.

Save as `SwapPositionsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SwapPositionsDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> alias = values;
        Collections.swap(values, 0, 3);
        System.out.println("afterSwap=" + values);
        System.out.println("alias=" + alias);

        Collections.swap(values, 1, 1);
        System.out.println("sameIndex=" + values);
        System.out.println("size=" + values.size());

        try {
            Collections.swap(values, 0, values.size());
        } catch (IndexOutOfBoundsException e) {
            System.out.println("badIndex=IndexOutOfBoundsException");
        }

        try {
            Collections.swap(values, -1, 0);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("negativeIndex=IndexOutOfBoundsException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SwapPositionsDemo.java
java SwapPositionsDemo
```

Stdout:

```text
afterSwap=[D, B, C, A]
alias=[D, B, C, A]
sameIndex=[D, B, C, A]
size=4
badIndex=IndexOutOfBoundsException
negativeIndex=IndexOutOfBoundsException
```

The first line shows that the two ends of the sequence have swapped places. The `alias` line has the same contents because it is another variable holding the exact List being modified; no new copy is created by `swap`.

The call using the same index 1 does not change the data. The two error cases that follow test the upper bound and a negative index separately. Having four elements in the List does not mean index 4 is valid: its positions are 0, 1, 2, and 3.

`swap` does not search by value. If a List contains two equal elements at two different positions, the method is still specified by index. It also does not sort the entire List and does not need a Comparator to determine which element is "greater."

One way to model it manually is to temporarily hold the element at the first position, assign the second element into the first position, and then assign the temporary element into the second position. What matters is preserving both elements, not a specific assignment sequence that every implementation must use.

The index and result contract is described at [Collections.swap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#swap(java.util.List,int,int)).

## 4. rotate: Cyclic Shifting and Shift Direction

Consider the sequence `[A, B, C, D, E]`. Cyclic rotation means an element that passes one end wraps around to the other end. No new positions are added and no elements are removed.

- A positive distance moves elements to the right.
- A negative distance moves elements to the left.
- A distance of 0 leaves the sequence unchanged when the operation completes.
- The distance can be larger than the size; full cycles do not change the final result.

For example, shifting right by one position brings E to the front, producing `[E, A, B, C, D]`. Shifting left by two positions moves A and B to the end in their original order, producing `[C, D, E, A, B]`.

For a non-empty List of n elements, you can use modular arithmetic to predict the outcome. Normalize the distance to r in the range 0 to n - 1 using `Math.floorMod(distance, n)`. Then, in the mathematical sense:

`new position of the old element at i = (i + r) mod n`

This is a position formula, not a requirement to rewrite the library algorithm yourself. If you implement the addition in Java with very large indices, you must account for int overflow; do not assume the mathematical expression is always safe to copy verbatim into every int calculation.

With n equal to 5 and r equal to 2:

| Initial element | Old index | New index |
| --- | --- | --- |
| A | 0 | 2 |
| B | 1 | 3 |
| C | 2 | 4 |
| D | 3 | 0 |
| E | 4 | 1 |

Reading by the new index gives `[D, E, A, B, C]`. You can also split the sequence into two blocks: the first three elements and the last two elements; move the last block to the front, preserving the order within each block.

For negative distances, do not use the absolute value to determine the result. `floorMod` maps negative numbers to a non-negative remainder that matches the cycle. The empty List case must be handled separately when computing modulo yourself, because you must not take a remainder modulo 0.

## 5. Experimenting with rotate on Negative Numbers, Large Numbers, and Empty Lists

Save as `RotateDistanceDemo.java`. Each distance is applied to a fresh ArrayList from the same original data, so the lines are not cumulative shifts.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class RotateDistanceDemo {
    public static void main(String[] args) {
        List<String> base = List.of("A", "B", "C", "D", "E");
        int[] distances = {1, -2, 7, Integer.MIN_VALUE, 0};
        for (int distance : distances) {
            List<String> values = new ArrayList<>(base);
            Collections.rotate(values, distance);
            System.out.println("distance=" + distance + " -> " + values);
        }

        int normalized = Math.floorMod(Integer.MIN_VALUE, base.size());
        System.out.println("minValueNormalized=" + normalized);

        List<String> roundTrip = new ArrayList<>(base);
        Collections.rotate(roundTrip, 2);
        Collections.rotate(roundTrip, -2);
        System.out.println("roundTrip=" + roundTrip);

        List<String> empty = new ArrayList<>();
        Collections.rotate(empty, 8);
        System.out.println("empty=" + empty);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 RotateDistanceDemo.java
java RotateDistanceDemo
```

Stdout:

```text
distance=1 -> [E, A, B, C, D]
distance=-2 -> [C, D, E, A, B]
distance=7 -> [D, E, A, B, C]
distance=-2147483648 -> [D, E, A, B, C]
distance=0 -> [A, B, C, D, E]
minValueNormalized=2
roundTrip=[A, B, C, D, E]
empty=[]
```

A distance of 7 is equivalent to shifting right by 2 for five elements. A distance of `Integer.MIN_VALUE` also normalizes to 2 in this case; the program produces the corresponding identical result. There is no need to clamp the distance to a small range before passing it to `Collections.rotate`.

The `roundTrip` case shifts right by two and then left by two on the same List, returning to the initial sequence. Cyclic rotation does not reverse the entire order like a reverse operation; elements that cross the boundary continue wrapping around in sequence order.

The empty List case is called directly with `Collections.rotate` and remains empty. In prediction code you write yourself, do not call `Math.floorMod(distance, empty.size())`; that is a separate invalid calculation due to a zero divisor, not something the program above did.

If you compute the inverse distance as `-distance`, watch out for `Integer.MIN_VALUE`: negating that value in int does not produce a representable symmetric positive number. When you need an inverse operation for a non-empty List, you can base it on an appropriately normalized distance instead of arbitrarily negating an input int. The example verifies the pair 2 and -2; it does not claim that every int negation is safe.

See the position rules and distance domain in [Collections.rotate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#rotate(java.util.List,int)).

## 6. Collections.replaceAll: Replacing Every Value-Matching Occurrence

The utility's signature is `Collections.replaceAll(List<T> list, T oldVal, T newVal)`. The method examines the elements in the List and replaces those matching `oldVal` with `newVal`.

The matching condition is defined as follows:

- If `oldVal` is null, null elements are matching elements.
- If `oldVal` is non-null, `oldVal.equals(element)` is used.

Therefore, two objects with different references that are equal according to `equals` can still match. Do not use `==` to predict ordinary value replacement. Matching here also does not rely on a Comparator or sort order.

The method replaces **all** matching positions, without stopping at the first one. Positional order is preserved and size is preserved, though the occurrence counts of values may change because the old value is replaced by the new value.

The boolean return value indicates whether the List contained at least one element matching the condition. It is not the count of replaced elements, nor is it proof that the contents observed via `equals` differ from before. If you replace `"green"` with `"green"` in a List containing green, the boolean result is still true.

`newVal` must fit the List's type and element constraints. With a List that allows null, you can use null as the target value or the replacement value. Do not infer from that capability that every List accepts null or allows `set`.

Replacement happens on the List's element references. It does not call a domain setter on the old object and does not automatically create a new copy of `newVal` for each position. If `newVal` is a mutable object, the replaced positions may all hold that same object; you need to understand that level of sharing when using such element types.

## 7. Experimenting with replaceAll and Distinguishing the Same-Named Method on List

Save as `ReplaceMatchingValuesDemo.java`. One red string is created with `new String` to emphasize that matching is based on content equality and does not require the same String reference. Null is prepared using a List that allows null.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class ReplaceMatchingValuesDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(
                Arrays.asList("red", null, new String("red"), "blue"));

        boolean found = Collections.replaceAll(values, "red", "green");
        System.out.println("foundRed=" + found);
        System.out.println("afterRed=" + values);

        boolean foundNull = Collections.replaceAll(values, null, "unknown");
        System.out.println("foundNull=" + foundNull);
        System.out.println("afterNull=" + values);

        boolean absent = Collections.replaceAll(values, "black", "white");
        System.out.println("absent=" + absent);

        boolean sameValue = Collections.replaceAll(values, "green", "green");
        System.out.println("sameValue=" + sameValue);
        System.out.println("afterSameValue=" + values);

        values.replaceAll(value -> value.toUpperCase(Locale.ROOT));
        System.out.println("afterOperator=" + values);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ReplaceMatchingValuesDemo.java
java ReplaceMatchingValuesDemo
```

Stdout:

```text
foundRed=true
afterRed=[green, null, green, blue]
foundNull=true
afterNull=[green, unknown, green, blue]
absent=false
sameValue=true
afterSameValue=[green, unknown, green, blue]
afterOperator=[GREEN, UNKNOWN, GREEN, BLUE]
```

After the first replacement, both red positions become green, while null and blue remain. The second replacement targets only null elements, placing the unknown label at that exact position.

There is no black in the List, so `absent` is false. When replacing green with green, `sameValue` is true, while the displayed contents remain as they were before the call. These two lines help you interpret the boolean result accurately.

The last line calls `values.replaceAll(...)`, which is a method on the List itself. It takes a single-argument function and uses the function's result to replace each element. At this point null has already been replaced with unknown, so uppercasing can be applied to every String element.

| Criterion | `Collections.replaceAll(list, oldVal, newVal)` | `list.replaceAll(operator)` |
| --- | --- | --- |
| Where declared | Collections utility class | List interface |
| Primary input | A target value and a replacement value | A function transforming each element |
| Elements processed | Elements matching the old value | Every element using the function's result |
| Return value | `boolean` indicating whether any matched | `void` |
| Example use case | Change every old label to a new label | Normalize or compute a new value per element |

`Locale.ROOT` in the program makes the uppercasing independent of the machine's default locale. This section illustrates how to tell the two same-named APIs apart; the main focus of the lesson remains the Collections utility that replaces by value.

If you only need to replace a single known position, `list.set(index, value)` expresses a different intent from replacing all equal values. If you need an arbitrary condition and each element produces its own result, the List method taking a function may be more appropriate. Choose according to the transformation rule you need.

Corresponding contracts: [Collections.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#replaceAll(java.util.List,T,T)) and [List.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator)).

## 8. Experimenting with Mutability: Fixed-Size vs. Read-Only

Save as `ListMutationSupportDemo.java`. The program tests all three utilities on an array-backed List, then on a read-only wrapper. The blocked cases genuinely request data changes rather than relying on no-op scenarios.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ListMutationSupportDemo {
    public static void main(String[] args) {
        String[] array = {"A", "B", "C", "A"};
        List<String> fixed = Arrays.asList(array);
        Collections.swap(fixed, 0, 1);
        Collections.rotate(fixed, 1);
        boolean found = Collections.replaceAll(fixed, "A", "X");
        System.out.println("fixed=" + fixed);
        System.out.println("array=" + Arrays.toString(array));
        System.out.println("found=" + found);
        try {
            fixed.add("new");
        } catch (UnsupportedOperationException e) {
            System.out.println("fixedAdd=UnsupportedOperationException");
        }

        List<String> readOnly = Collections.unmodifiableList(
                new ArrayList<>(List.of("A", "B", "C")));
        try {
            Collections.swap(readOnly, 0, 1);
        } catch (UnsupportedOperationException e) {
            System.out.println("readOnlySwap=UnsupportedOperationException");
        }
        try {
            Collections.rotate(readOnly, 1);
        } catch (UnsupportedOperationException e) {
            System.out.println("readOnlyRotate=UnsupportedOperationException");
        }
        try {
            Collections.replaceAll(readOnly, "A", "Z");
        } catch (UnsupportedOperationException e) {
            System.out.println("readOnlyReplace=UnsupportedOperationException");
        }
        System.out.println("readOnly=" + readOnly);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ListMutationSupportDemo.java
java ListMutationSupportDemo
```

Stdout:

```text
fixed=[X, B, X, C]
array=[X, B, X, C]
found=true
fixedAdd=UnsupportedOperationException
readOnlySwap=UnsupportedOperationException
readOnlyRotate=UnsupportedOperationException
readOnlyReplace=UnsupportedOperationException
readOnly=[A, B, C]
```

Tracing the array-backed List step by step:

| Step | Contents |
| --- | --- |
| Initial | `[A, B, C, A]` |
| Swap positions 0 and 1 | `[B, A, C, A]` |
| Rotate right by one position | `[A, B, A, C]` |
| Replace every A with X | `[X, B, X, C]` |

The line printing the array has the same final contents because the fixed-size List is backed by that array. `set` operations are permitted, whereas `add` requires growing the size and is rejected.

For `readOnly`, all three mutation requests are blocked. Keeping the number of elements unchanged is not enough to permit the operation: the ability to replace a reference at a position is still data mutation.

An accurate comparison table needs to separate two capabilities:

| List kind in the example | Replace element at existing position | Increase/decrease element count |
| --- | --- | --- |
| Ordinary ArrayList | Yes | Yes |
| List from Arrays.asList | Yes | No |
| Collections.unmodifiableList wrapper | No (via wrapper) | No (via wrapper) |

Do not program by calling a utility speculatively and catching exceptions to guess the List kind. If your method is responsible for producing a transformed result, prepare a suitable List from the start. If your method requires mutating the caller's List itself, state the requirement that element replacement must be supported.

Collections mutation algorithms have differing allowances regarding whether they throw an exception on certain no-op calls. Therefore, cases like no matching value found, a distance that does not change the sequence, or two identical indices should not be used as a universal test of mutability.

The relationship between an array and its List along with fixed-size behavior is described at [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

## 9. Applying to subList: Narrow Scope, Impact on the Parent List

If you only want to transform a slice, you can obtain a view with `subList(fromIndex, toIndex)` and pass that view to the utility. The start bound is inclusive and the end bound is exclusive. Indices when calling `swap` on the view are local indices within the slice, not direct indices of the parent List.

Suppose the parent List is `[head, A, B, C, D, tail]`. The view `subList(1, 5)` consists of four elements `[A, B, C, D]`. Position 0 of the view corresponds to position 1 of the parent; position 3 corresponds to position 4.

The view does not create a copy. When you modify elements through the view, the parent List receives the changes in the corresponding slice. Elements outside the slice are not targeted by the utility.

Save as `SubListUtilitiesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SubListUtilitiesDemo {
    public static void main(String[] args) {
        List<String> parent = new ArrayList<>(
                List.of("head", "A", "B", "C", "D", "tail"));
        List<String> window = parent.subList(1, 5);

        Collections.swap(window, 0, 3);
        System.out.println("parentAfterSwap=" + parent);

        Collections.rotate(window, -1);
        System.out.println("parentAfterRotate=" + parent);

        boolean found = Collections.replaceAll(window, "A", "X");
        System.out.println("found=" + found);
        System.out.println("window=" + window);
        System.out.println("parentAfterReplace=" + parent);

        List<String> move = new ArrayList<>(List.of("P", "Q", "R", "S", "T"));
        Collections.rotate(move.subList(1, 4), -1);
        System.out.println("moveOne=" + move);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SubListUtilitiesDemo.java
java SubListUtilitiesDemo
```

Stdout:

```text
parentAfterSwap=[head, D, B, C, A, tail]
parentAfterRotate=[head, B, C, A, D, tail]
found=true
window=[B, C, X, D]
parentAfterReplace=[head, B, C, X, D, tail]
moveOne=[P, R, S, Q, T]
```

The two elements head and tail remain unchanged across all three operations on window. The lines printing the parent List show that the middle slice was swapped, rotated, and value-replaced. The `window` line shows the local result of that slice itself.

The `moveOne` case uses cyclic rotation to move one element while preserving the order of the remaining elements in the slice. The slice from index 1 up to (excluding) 4 is `[Q, R, S]`. Shifting left by one position produces `[R, S, Q]`; in the parent List, Q moves from index 1 to index 3.

In general, to move an element at j to k where j is less than or equal to k, you can shift left by one position on the slice from j up to (excluding) k + 1. That handles repositioning within a range without removing an element and inserting a new position.

This is especially useful when the List supports replacing elements but does not support resizing. However, you must compute the end bound correctly: using k instead of k + 1 leaves the destination position itself out of the slice.

While using a view, do not arbitrarily make structural additions/removals to the parent List through another path and continue treating the view as valid. The `subList` contract has conditions regarding structural modifications outside the view. The example only replaces elements, without mixing in operations that change the source's size.

If you want to transform a slice independently without modifying the parent, create a separate List from the slice before calling the utility. Mutability, scope, and relationship to the source are three decisions to consider together.

## 10. Mechanisms and Cost Depend on the List Type

Understanding how a List accesses elements helps you choose the right operation. A method accepting the List interface does not mean every List has the same cost for `get(index)` and `set(index, value)`.

For [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), get/set operations take constant time. Swapping two positions only requires a few element accesses and replacements, so swap has constant cost with respect to size in this common case.

For [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), indexed access must walk from the start or end to the appropriate position. Swapping two positions in the middle of a large List can take time proportional to the traversal length. Do not apply conclusions about ArrayList to every List just because the utility signature is the same.

For rotate, distinguish between the result and one way of implementing that result:

- The result is defined by the cyclic shift distance and element positions.
- The JDK implementation may move elements along positional cycles, or process slices with reversals, depending on the List's size and access capabilities.

Algorithm descriptions in the Collections Javadoc are implementation notes and do not force every version to keep the exact same internal instruction sequence. What matters when using it is a correct result and that the List permits element replacement. Do not manually shift one step at a time millions of times just because distance is huge; full cycles do not change the desired result anyway.

Value-based replaceAll needs to inspect elements to find every match. With common Lists and a constant-cost equals method, traversal cost is typically linear in the number of elements. If equals performs a large content comparison, you must factor in that comparison cost as well.

A subList view can narrow the range to inspect down to the relevant slice, but the cost still depends on how the underlying List performs access. Do not assume creating a view copies data into a structure with a different cost profile.

The operations in this lesson also do not provide an atomic update transaction across threads. When a List is shared and accessed concurrently, proper coordination is needed for the entire business operation. Preserving size does not mean element replacements can be performed concurrently at will.

## 11. Reading Exceptions and Keeping Impact Within Scope

| Situation | How to interpret and handle |
| --- | --- |
| swap receives a negative index or size | The index is outside the range of existing elements; check both bounds |
| rotate receives a negative number or a number greater than size | That distance is valid; recheck direction and normalization if your prediction was wrong |
| Computing modulo yourself when size is 0 | Separate the empty case before the calculation; do not blame rotate for that arithmetic error |
| Utility mutates a read-only List | Need a List that supports element replacement, or create a mutable copy |
| Fixed-size List still allows swap/rotate | This is consistent when the List supports set; do not conflate it with add/remove permission |
| replaceAll returns true but printed contents look unchanged | An element matched; the boolean does not measure how much the contents changed |
| replaceAll does not match an object as expected | Check oldVal's equals and the element types; neither identity nor Comparator replaces the matching rule |
| Using parent indices when calling swap on a subList | Convert to the view's local indices |
| Transforming a slice also changes the parent | The slice is a view; create a separate List if an independent result is needed |

If the passed-in List object itself is null, the utilities throw `NullPointerException` per the Collections contract. Distinguish that case from a valid List that contains a null element: for example, replaceAll handled a null element because that List allowed it.

Library mutation methods do not automatically check every business rule of your application. A List may allow element replacement, yet data-validation types or an element's equals code can raise an error during execution. Do not assume there is always a rollback mechanism for everything done before the error.

If you need to preserve source data when a transformation fails, choose to operate on separate data and then validate/publish the result through an appropriate workflow. Merely wrapping an in-place operation in try/catch does not turn it into an "all-or-nothing" update.

When verifying, print or compare both contents and size before and after. For swap and rotate, also check that element occurrences are preserved. For replaceAll, identify the matching positions clearly; the occurrence count of the new value may increase even though the total number of positions stays the same.

## 12. Practice from Prediction to Verification

### Exercise 1: Swapping Two Selected Items

The source is `[draft, review, publish, archive]`. Swap positions 1 and 3, predict the result before running, and then verify the size.

The expected result is `[draft, archive, publish, review]`, and the size remains four. Also try an index equal to size to distinguish between "an insertion position in some APIs" and "an existing element position for swap."

### Exercise 2: Choosing the Starting Element of a Cycle

The source is `[Mon, Tue, Wed, Thu, Fri]`. You need Wed to be first while keeping the cyclic order as before.

Choose the distance before calling rotate. Shifting left by two positions, i.e., distance -2, produces `[Wed, Thu, Fri, Mon, Tue]`. Then choose an equivalent positive distance and verify that the two results match. With five elements, a distance of 3 is one such choice.

### Exercise 3: Replacing Statuses and Reading the Boolean Correctly

The source is `[open, closed, open]`. Replace every open with pending, then replace pending with pending.

The first call should produce `[pending, closed, pending]` and return true. The second call still returns true because there is a matching element, even though the displayed sequence is unchanged. Add a case searching for a nonexistent status to test the false branch.

### Exercise 4: Rotating Only the Middle Slice

The source is `[L, A, B, C, R]`. Shift right by one position within the A, B, C slice, keeping L and R in place.

Identify the view with start bound 1 and end bound 4. The result should be `[L, C, A, B, R]`. Verify that local indices and the exclusive end bound are used properly.

### Exercise 5: Transforming an Array-Backed List

Create a String array and obtain a List via Arrays.asList. Apply each utility, printing both the List and the array after each step. Finally, try adding a new element.

Passing criteria: element replacements appear in both views of the data; the size-increasing operation is rejected. Explain this using two distinct permissions: set permission and add/remove permission.

### Exercise 6: Preserving a Read-Only Source and Producing a Separate Result

The input is a List created with List.of. You need to return a rotated list while leaving the input unchanged.

Create a separate ArrayList before rotating. Passing criteria: the source retains its original contents, the separate result has the right rotation direction, and the code does not rely on catching an exception before fixing the design.

## 13. Check Your Understanding

1. **Do swap and rotate return a new List?** No. They return void and act on the passed-in List.
2. **Why can a fixed-size List still be used?** Because the utilities do not need to add or remove positions, but do need the ability to replace elements at existing positions.
3. **Which direction does a positive distance in rotate move?** To the right, with elements passing the end wrapping around to the front.
4. **Is a distance greater than size an error?** No. It can be predicted using the equivalent modulo distance when the List is non-empty.
5. **What does Collections.replaceAll use for matching?** It matches null to null or uses oldVal.equals(element), not ordinary reference comparison.
6. **Does a boolean true prove the data is different from before?** No. It indicates that an element matched the condition.
7. **What does List.replaceAll take differently?** It takes a function that transforms each element and returns void.
8. **Does modifying a subList modify the parent List?** It can affect the corresponding slice because subList is a view, not a copy.
9. **Does preserving size mean an operation is read-only?** No. Swapping or replacing element references still mutates the List.
10. **What should a good prediction consider?** Index range, direction or matching condition, the List's set support, and whether the data is the original source, a view, or a separate copy.
