# binarySearch and the Sorted-List Precondition

## 1. Why Does Binary Search Require Order?

Suppose a list of milestones is already ordered as 3, 7, 11, 15, 19, 23, 27. To find 19, we can compare against the middle element, 15. Because 19 comes after 15 under the order in use, the entire preceding portion and 15 itself cannot be the answer. We only need to continue in the remaining half.

That is the idea behind **binary search**: each comparison eliminates a large portion of the range that could still contain the search key.

That elimination is only justified when the list is already sorted according to the exact same comparison. If 19 could appear arbitrarily before 15, discarding the first half could discard the answer as well.

One illustrative trace on the list above:

| Step | Remaining index range | Middle element | Compared with 19 | Decision |
|---|---|---|---|---|
| 1 | 0 to 6 | 15 at 3 | 15 precedes 19 | Narrow to range 4 to 6 |
| 2 | 4 to 6 | 23 at 5 | 23 follows 19 | Narrow to range 4 to 4 |
| 3 | 4 to 4 | 19 at 4 | Equal under the comparison | Found at 4 |

The table illustrates one valid way to split the range; it does not require every library implementation to pick those exact midpoint steps.

`Collections.binarySearch` is a search utility for `List`. It **does not sort the list automatically**, does not fall back to linear search to rescue invalid input, and does not insert elements for the caller.

This lesson progresses from the ordering precondition, interpreting return values, comparators, and duplicate elements to maintaining the list in real-world use. All three complete programs run on Java 17 or later using only the standard library.

## 2. "Sorted" According to Which Comparison?

### 2.1. Two Main Call Forms

| Call form | Required list order |
|---|---|
| `Collections.binarySearch(list,key)` | Natural ordering of the elements, ascending according to `Comparable` |
| `Collections.binarySearch(list,key,order)` | Ascending according to the relation defined by `order` |
| `Collections.binarySearch(list,key,null)` | Uses natural ordering, same as omitting the comparator |

"Natural ordering" is the order defined by the element type itself—for example, `Integer` by numeric value, `String` by `String` lexicographical comparison. A sequence that looks ascending to a human reader is not necessarily ascending according to the data type's `compareTo`.

For example, the `String` values `"1"`, `"10"`, `"2"` are in valid natural order even though that differs from numeric order 1, 2, 10. If business logic requires numeric comparison, you must convert to a numeric type or provide an appropriate comparator and sort by it.

A `List` does not carry a `Comparator` of its own for `binarySearch` to retrieve, unlike `TreeSet`/`TreeMap`. Every call to the comparator overload must pass the rule that matches the data being searched.

### 2.2. Non-Decreasing, Not Strictly Increasing

With a valid and consistent comparator `c`, a list is sorted when every adjacent pair satisfies:

`c.compare(list.get(i), list.get(i + 1)) <= 0`.

Duplicate elements or elements that compare equal under the comparator are allowed. The sequence 1, 2, 2, 2, 4 is still sorted. There is no need to remove duplicates before calling `binarySearch`.

Empty lists and single-element lists have no adjacent pairs that can violate order. The comparison condition with the search key must still be used properly; do not treat an empty case as proof that arbitrary key types are compatible in other cases.

### 2.3. Numerically Descending Is Still Ascending Under a Reverse Comparator

`Comparator.reverseOrder()` for integers places 50 before 40, and 40 before 30. The list 50, 40, 30, 20, 10 is therefore sorted in ascending order under that comparator's relation.

Searching this list with the default natural-ordering overload violates the precondition. You must pass the corresponding descending `Comparator`.

An easy-to-control pattern is to keep the comparator in a variable and use it for both `sort` and `binarySearch`. It is not required to be the exact same `Comparator` instance by `==`; what must hold is that the list remains ordered according to the relation used for searching.

A finer-grained order can sometimes remain compatible with searching by a coarser criterion. For example, sorting by score then name still preserves order by score. However, sorting only by score does not guarantee that elements with equal scores are ordered by name for a search using a score-then-name comparator. Always check the actual relation rather than relying on two comparator names looking similar.

The specification of [Collections.binarySearch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#binarySearch(java.util.List,T,java.util.Comparator)) requires the list to be sorted beforehand according to the comparison used for the call.

### 2.4. Violating the Precondition Does Not Guarantee an Exception

If the list is not properly sorted, the contract makes no guarantee about the search result. Sometimes it finds the element, sometimes it returns a negative number even though the element is present, or it returns an insertion point that is meaningless for the list as a whole.

Do not write code that catches an "unsorted list" exception and tries to recover. `binarySearch` is not responsible for scanning the entire list to detect that condition before every search.

## 3. Two Return-Value Branches, Not Just Index or -1

Let `r = Collections.binarySearch(list, key)`.

### 3.1. `r >= 0`: Found an Element Comparing Equal to the Key

`r` is the 0-based index in the exact `list` passed in. You can call `list.get(r)` as long as the list has not been modified in a way that invalidates the index.

Index 0 means found at the first element, not failure. Therefore, the correct condition to check for a match is `r >= 0`, not `r > 0`.

"Found" means `compareTo`/`Comparator` returns 0. It does not by default mean finding the same reference or an object that `equals` the key; the example with a single-field comparator on a record will illustrate this distinction.

### 3.2. `r < 0`: Encoded Insertion Point

When not found, `r` is not merely a generic failure code. It has the form:

`r = -insertionPoint - 1`.

`insertionPoint` is the index at which the key could be inserted to preserve order: the index of the first element greater than the key under the comparison, or `list.size()` if the key comes after all elements.

Because we are in the branch where **no element compares equal to the key**, the first position not less than the key and the first position greater than the key are the same.

Decode it with:

`insertionPoint = -(r + 1)`.

The insertion point lies in `[0, size]`, whereas valid element indices lie in `[0, size)`. The value `size` is valid for `add(size, key)` on a list that supports addition, but invalid for `get(size)`.

### 3.3. Decoding Examples

Ordered source `[-10, 0, 10, 20, 30]`:

| Key | Result `r` | Meaning |
|---|---|---|
| -10 | 0 | Found at the first element |
| 10 | 2 | Found at index 2 |
| 15 | -4 | Not found; insert at 3, before 20 |
| -20 | -1 | Not found; insert at 0 |
| 40 | -6 | Not found; insert at 5, i.e., end of list |

For an empty list, the insertion point is 0, so the return value is -1. `-1` does not solely mean "not found anywhere"; it specifically encodes position 0.

Do not use `Math.abs(r)` to obtain the insertion point. For `r = -4`, `Math.abs` gives 4 whereas the correct position is 3. Using `-(r + 1)` also avoids negating the most negative integer before subtracting 1.

## 4. Program: Reading Results, Inserting When Absent, and Handling Duplicates

File **BinarySearchResultDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class BinarySearchResultDemo {
    private static void report(List<Integer> values, int key) {
        int result = Collections.binarySearch(values, key);
        if (result >= 0) {
            System.out.println("key=" + key + ", found=" + result +
                    ", value=" + values.get(result));
        } else {
            int insertionPoint = -(result + 1);
            System.out.println("key=" + key + ", result=" + result +
                    ", insertion=" + insertionPoint);
        }
    }

    public static void main(String[] args) {
        List<Integer> values =
                new ArrayList<>(List.of(-10, 0, 10, 20, 30));
        report(values, -10);
        report(values, 10);
        report(values, 15);
        report(values, -20);
        report(values, 40);
        report(List.of(), 42);

        int result = Collections.binarySearch(values, 15);
        if (result < 0) {
            values.add(-(result + 1), 15);
        }
        System.out.println("afterInsert=" + values);
        System.out.println("readOnlySearch=" +
                Collections.binarySearch(List.of(2, 4, 6, 8), 6));

        List<Integer> duplicates = List.of(-2, 0, 0, 0, 4);
        int duplicateResult = Collections.binarySearch(duplicates, 0);
        System.out.println("duplicateFound=" + (duplicateResult >= 0));
        System.out.println("duplicateMatched=" + duplicates.get(duplicateResult));
        System.out.println("duplicateIndexInRange=" +
                (duplicateResult >= 1 && duplicateResult <= 3));
        report(duplicates, 1);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 BinarySearchResultDemo.java
java BinarySearchResultDemo
```

Exact stdout:

```text
key=-10, found=0, value=-10
key=10, found=2, value=10
key=15, result=-4, insertion=3
key=-20, result=-1, insertion=0
key=40, result=-6, insertion=5
key=42, result=-1, insertion=0
afterInsert=[-10, 0, 10, 15, 20, 30]
readOnlySearch=2
duplicateFound=true
duplicateMatched=0
duplicateIndexInRange=true
key=1, result=-5, insertion=4
```

### 4.1. Searching Does Not Require a Modifiable List

`readOnlySearch` searches `List.of(2, 4, 6, 8)` and returns 2. `binarySearch` is read-only; it does not need `add`/`set` and never calls `sort`.

Conversely, inserting 15 requires a list that supports `add(index, value)`. Having a valid insertion index does not magically make an unmodifiable list support insertion.

If you need to sort an unmodifiable list while preserving the original input, create a separate `ArrayList` and sort that copy. Do not call `sort` on a read-only view or assume `binarySearch` will handle sorting for you.

### 4.2. Negative Values Must Be Handled Before Indexing

`report()` only calls `get(result)` in the `result >= 0` branch. In the negative branch, it decodes the insertion point and prints the information.

Passing a negative return value directly as an index is a caller bug that typically causes `IndexOutOfBoundsException`. `binarySearch` has already returned valid information indicating the key is absent.

### 4.3. With Duplicates, Neither First Nor Last Is Guaranteed

`duplicates` has elements equal to 0 at indices 1, 2, and 3. The program checks that the returned index falls within that range and that the element at that index is 0, rather than printing a specific index and treating it as part of the contract.

`Collections.binarySearch` makes no guarantee to return the first or last occurrence when multiple elements compare equal to the key. Even a stable sort does not change this contract: preserving the relative order of equal elements during sorting does not mean the search algorithm must pick the first element in the group.

If you only need to know whether at least one element matches the key, any index in the group is sufficient. If you need to count occurrences, retrieve the entire group, or insert before/after the group, you must find the bounds separately.

## 5. The Comparator Defines What "Found" and "Insertion Point" Mean

The next program uses `Score` records containing a name and points. The first comparator looks only at `points`, so two `Score` instances with different names can compare equal (0) even though `record.equals()` returns `false`.

It also uses a descending list of numbers and a null-friendly comparator to examine the ordering precondition across different cases.

File **BinarySearchComparatorDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class BinarySearchComparatorDemo {
    record Score(String name, int points) {}

    public static void main(String[] args) {
        Comparator<Score> byPoints = Comparator.comparingInt(Score::points);
        List<Score> scores = new ArrayList<>(List.of(
                new Score("A", 30), new Score("B", 10),
                new Score("C", 20), new Score("D", 20)));
        scores.sort(byPoints);
        System.out.println("sortedPoints=" +
                scores.stream().map(Score::points).toList());

        Score probe = new Score("probe", 20);
        int result = Collections.binarySearch(scores, probe, byPoints);
        Score matched = scores.get(result);
        System.out.println("matchedPoints=" + matched.points());
        System.out.println("compareZero=" + (byPoints.compare(matched, probe) == 0));
        System.out.println("equalsProbe=" + matched.equals(probe));
        System.out.println("indexOfProbe=" + scores.indexOf(probe));

        int missing = Collections.binarySearch(
                scores, new Score("probe", 25), byPoints);
        System.out.println("missing25=" + missing);
        System.out.println("insert25At=" + (-(missing + 1)));

        Comparator<Score> byPointsThenName =
                byPoints.thenComparing(Score::name);
        scores.sort(byPointsThenName);
        int exact = Collections.binarySearch(
                scores, new Score("D", 20), byPointsThenName);
        System.out.println("exactName=" + scores.get(exact).name());

        Comparator<Integer> descending = Comparator.reverseOrder();
        List<Integer> descendingValues =
                new ArrayList<>(List.of(50, 40, 30, 20, 10));
        int reverseMissing =
                Collections.binarySearch(descendingValues, 35, descending);
        int reverseInsertion = -(reverseMissing + 1);
        System.out.println("descendingMissing35=" + reverseMissing);
        System.out.println("descendingInsertion=" + reverseInsertion);
        descendingValues.add(reverseInsertion, 35);
        System.out.println("descendingAfterInsert=" + descendingValues);

        Comparator<Integer> nullsFirst =
                Comparator.nullsFirst(Comparator.naturalOrder());
        List<Integer> nullable = Arrays.asList(null, 10, 20);
        System.out.println("nullKeyIndex=" +
                Collections.binarySearch(nullable, null, nullsFirst));
        System.out.println("nullableMissing15=" +
                Collections.binarySearch(nullable, 15, nullsFirst));
        System.out.println("nullComparatorUsesNatural=" +
                Collections.binarySearch(List.of(1, 2, 3), 2, null));
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 BinarySearchComparatorDemo.java
java BinarySearchComparatorDemo
```

Exact stdout:

```text
sortedPoints=[10, 20, 20, 30]
matchedPoints=20
compareZero=true
equalsProbe=false
indexOfProbe=-1
missing25=-4
insert25At=3
exactName=D
descendingMissing35=-3
descendingInsertion=2
descendingAfterInsert=[50, 40, 35, 30, 20, 10]
nullKeyIndex=0
nullableMissing15=-3
nullComparatorUsesNatural=1
```

### 5.1. Searching by Points Differs from Matching the Entire Record

`probe` has name `"probe"` and 20 points. After sorting by `points`, `binarySearch` returns a `Score` with 20 points. Its name could be `"C"` or `"D"`; the program does not rely on which one is chosen.

`byPoints.compare(matched, probe)` is 0, whereas `matched.equals(probe)` is `false` because `record.equals` compares all record components. `scores.indexOf(probe)` returns -1 because it uses `equals`.

These are two different questions:

- `binarySearch` with `byPoints`: is there any element in the 20-point group?
- `indexOf` with `probe`: is there an element that `equals` `probe` according to the class contract?

A comparator on `points` alone is still completely valid when you want to search by score group. A comparator used to search a `List` does not have to distinguish every field of a record.

To search by points and then name, the program re-sorts with `byPoints.thenComparing(Score::name)` and searches with that same relation. `exactName` is `D`.

### 5.2. The Insertion Point Also Follows the Comparator's Direction

In `50, 40, 30, 20, 10` ordered by `reverseOrder`, 35 is inserted at index 2, between 40 and 30. The return code is -3.

Do not decode the index and then apply an ascending-order intuition. The insertion point is already the position within the descending sequence passed in.

### 5.3. A `null` Comparator and a `null` Key Are Different Things

Passing `null` as the comparator parameter means "use natural ordering"; it is not a comparator that allows `null` elements or `null` keys.

`Comparator.nullsFirst(naturalOrder())` explicitly expresses the policy of placing `null` before numbers. The `nullable` list in the example is already ordered according to that comparator, so searching for `null` validly returns 0 and searching for 15 returns insertion point 2.

Do not assume natural ordering knows how to compare `null`. A special case that happens not to perform comparisons—such as an empty list—does not prove that `null` is generally supported across all inputs.

### 5.4. The Comparison Must Be Correct and Consistent

Do not write an integer comparator as `a - b` if the value range can cause subtraction overflow. Using `Integer.compare` or factories like `comparingInt`, as in the example, expresses the comparison safely.

A `Comparator` must satisfy the ordering contract, including consistency and transitivity. Nor should its meaning change between `sort` and `search` because of a configuration flag or mutable external state.

The [Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html) documentation explains the ordering relation and why `compare == 0` can differ from `equals`. [Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html) specifies the foundation for natural ordering.

## 6. To Get the First, Last, or Entire Duplicate Group, Search for Bounds

### 6.1. Two Bounds to Distinguish

On a list sorted according to comparator `c`:

- `lowerBound(key)`: the first index whose element does not precede `key`, i.e. `c.compare(element, key) >= 0`; returns `size` if none exists.
- `upperBound(key)`: the first index whose element follows `key`, i.e. `c.compare(element, key) > 0`; returns `size` if none exists.

Elements comparing equal to `key` occupy the half-open index range `[lowerBound, upperBound)`. The number of elements in the group is `upperBound - lowerBound`.

If the two bounds are equal, no element compares equal to the key. That shared index is also the insertion point when not found.

If the group is non-empty:

- The first index of the group is `lowerBound`.
- The last index of the group is `upperBound - 1`.
- Inserting at `lowerBound` places the new element before the group.
- Inserting at `upperBound` places the new element after the group.

These are custom helper methods in the example, not built-in methods on `Collections`. They still require a sorted list and a matching comparator.

### 6.2. Program: Bounds, Order Verification, and `subList` Indexing

File **BinarySearchBoundsDemo.java**:

```java
import java.util.Collections;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

public class BinarySearchBoundsDemo {
    public static <T> int lowerBound(
            List<? extends T> values, T key, Comparator<? super T> order) {
        Objects.requireNonNull(values);
        Objects.requireNonNull(order);
        int low = 0;
        int high = values.size();
        while (low < high) {
            int mid = low + (high - low) / 2;
            if (order.compare(values.get(mid), key) < 0) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }
        return low;
    }

    public static <T> int upperBound(
            List<? extends T> values, T key, Comparator<? super T> order) {
        Objects.requireNonNull(values);
        Objects.requireNonNull(order);
        int low = 0;
        int high = values.size();
        while (low < high) {
            int mid = low + (high - low) / 2;
            if (order.compare(values.get(mid), key) <= 0) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }
        return low;
    }

    public static <T> boolean isSorted(
            List<? extends T> values, Comparator<? super T> order) {
        Objects.requireNonNull(values);
        Objects.requireNonNull(order);
        Iterator<? extends T> iterator = values.iterator();
        if (!iterator.hasNext()) {
            return true;
        }
        T previous = iterator.next();
        while (iterator.hasNext()) {
            T current = iterator.next();
            if (order.compare(previous, current) > 0) {
                return false;
            }
            previous = current;
        }
        return true;
    }

    public static void main(String[] args) {
        Comparator<Integer> ascending = Comparator.naturalOrder();
        List<Integer> values = List.of(1, 2, 2, 2, 4);
        int lower = lowerBound(values, 2, ascending);
        int upper = upperBound(values, 2, ascending);
        System.out.println("bounds2=" + lower + "," + upper);
        System.out.println("count2=" + (upper - lower));
        System.out.println("equalRange=" + values.subList(lower, upper));
        System.out.println("bounds3=" +
                lowerBound(values, 3, ascending) + "," +
                upperBound(values, 3, ascending));
        System.out.println("beforeAll=" + lowerBound(values, 0, ascending));
        System.out.println("afterAll=" + upperBound(values, 9, ascending));
        System.out.println("emptyBounds=" +
                lowerBound(List.<Integer>of(), 2, ascending) + "," +
                upperBound(List.<Integer>of(), 2, ascending));
        System.out.println("sorted=" + isSorted(values, ascending));
        System.out.println("unsorted=" +
                isSorted(List.of(1, 3, 2), ascending));

        List<Integer> descending = List.of(5, 4, 4, 2);
        Comparator<Integer> reverse = Comparator.reverseOrder();
        System.out.println("descendingBounds4=" +
                lowerBound(descending, 4, reverse) + "," +
                upperBound(descending, 4, reverse));

        List<Integer> whole = List.of(0, 10, 20, 30, 40);
        int from = 1;
        List<Integer> part = whole.subList(from, 4);
        int localFound = Collections.binarySearch(part, 20);
        int localMissing = Collections.binarySearch(part, 25);
        System.out.println("localFound=" + localFound);
        System.out.println("wholeFound=" + (from + localFound));
        System.out.println("localMissing=" + localMissing);
        System.out.println("wholeInsertion=" + (from - (localMissing + 1)));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 BinarySearchBoundsDemo.java
java BinarySearchBoundsDemo
```

Exact stdout:

```text
bounds2=1,4
count2=3
equalRange=[2, 2, 2]
bounds3=4,4
beforeAll=0
afterAll=5
emptyBounds=0,0
sorted=true
unsorted=false
descendingBounds4=1,3
localFound=1
wholeFound=2
localMissing=-3
wholeInsertion=3
```

### 6.3. Why Changing One Comparison Operator Shifts the Bound

In `lowerBound`, when the middle element precedes `key`, the target bound must lie to the right, so `low = mid + 1`. When the middle element is equal to or follows `key`, `mid` itself cannot be ruled out yet, so `high = mid`.

In `upperBound`, the equal-to-`key` case must also move right. Therefore, the condition in the `low`-updating branch uses `<= 0` instead of `< 0`.

The search space is represented as `[low, high)`, allowing the result to be `size` without ever calling `get(size)`. When `low == high`, the loop terminates at the exact bound.

Computing `mid = low + (high - low) / 2` avoids adding two large indices directly before dividing. Every iteration strictly shrinks the remaining range.

On `[1, 2, 2, 2, 4]`, the bounds for 2 are 1 and 4, so the group has three elements. Both bounds for 3 are 4, confirming 3 is absent and can be inserted at index 4.

### 6.4. Demonstration Helpers Do Not Replicate Every Library Policy

Both bound helpers in the program explicitly require a non-null `Comparator`. For natural ordering, pass `Comparator.naturalOrder()`. That is the contract of these custom helpers, unlike `Collections.binarySearch(..., null)`, which falls back to natural ordering.

Both use `get(mid)`, so they are best suited to fast random-access lists. They produce correct results on valid sequential-access lists as well, but they do not include the iterator-based optimization that `Collections.binarySearch` uses for large sequential lists.

`isSorted` uses an iterator to check adjacent pairs. When the comparator is a valid and consistent ordering relation, non-decreasing adjacent pairs confirm that the list is sorted under that relation. The method does not verify transitivity or the overall correctness of an arbitrary `Comparator`.

## 7. Searching a `subList`: Results Use the Passed-In View's Index Space

In the program, `whole` is `[0, 10, 20, 30, 40]`. `part = whole.subList(1, 4)` contains `[10, 20, 30]`.

Searching for 20 in `part` returns index 1. The corresponding index in `whole` is `1 + 1 = 2`. `binarySearch` does not automatically return the parent list's index.

When 25 is absent from `part`:

- `localMissing` is `-3`.
- The insertion point in `part` is `-(-3 + 1) = 2`.
- The corresponding insertion point in `whole` is `from + 2 = 3`.

You must **decode the negative result first**, and only then translate the coordinate. Never add the offset directly to an encoded negative result and treat it as an index or an encoded result for the parent list.

If `r >= 0`, translate the index with `from + r`. If `r < 0`, translate the insertion point with `from - (r + 1)`.

This rule applies while the relationship between the `subList` and the parent list remains valid and no structural modification has invalidated the view or indices. `List.subList` has its own rules regarding structural modification of the backing list; read-only wrappers or `binarySearch` do not remove those rules.

Elements in a contiguous slice of a sorted list remain sorted under the same comparator. However, that does not allow using a different comparator or ignoring mutations to the parent list.

## 8. Maintaining the Sorted Precondition Across the Data Lifecycle

### 8.1. One Sort in the Past Is Not Enough

After sorting, any of the following operations can break the required order:

- Inserting an element at an arbitrary position that violates order.
- Calling `set` to replace an element with a value that breaks order relative to its neighbors.
- Reversing or shuffling the list and still searching with the old comparator.
- Mutating a field on an element object that the comparator reads.
- Changing the comparator's rules or external state that it depends on.

Not every modification breaks order. Removing an element from a sorted list preserves the order of the remaining elements. Inserting at the computed insertion point or replacing with a value that still fits between its two neighbors can preserve the precondition.

What you must track is the current ordering invariant, not merely a flag saying "sort was called once."

### 8.2. Inserting When Absent vs. Adding to an Existing Group

In the `r < 0` branch, the decoded insertion point preserves order when inserting the exact key just searched for into an unchanged list.

In the `r >= 0` branch, if your goal is uniqueness under the comparator, you can skip insertion. If you want to keep multiple equal elements, decide whether position within the group matters.

Inserting at the matched index still preserves order under the comparator, but it does not guarantee placement after all existing equal elements. To place before or after the group, use the corresponding bound.

If objects have a secondary criterion, agree on a single comparator that defines the full ordering invariant. Do not find a position by points alone and assume the list remains sorted by points-and-name after inserting an arbitrary name.

### 8.3. Mutable Element Fields Are Another Way to Break Order

Preventing `add`/`set` on the list does not make the elements inside it immutable. If a mutable `Score` has its points incremented directly, its physical position may no longer match its new score.

When that happens, `binarySearch` still inspects the current physical order and does not re-sort when an object's field changes. You may need to route updates through a manager class, remove and re-insert the element at its new position, re-sort at the end of a batch update, or use immutable elements as appropriate.

Even a structural copy made with `new ArrayList<>(source)` can still share the same mutable element references, so copying the list alone does not solve this problem.

### 8.4. A Returned Index Is Not a Stable Object Identity

After inserting or removing elements before a previously found index, the same object can shift to a different index. Saving `r` and reusing it across multiple updates can retrieve the wrong element.

If you need to retain an entity, store an identifier or reference suited to the data lifecycle; if you need an index for an immediate operation, ensure the list does not change between searching and using the index.

In multithreaded environments, a sequence such as search -> decode -> insert or search -> get may need to run under the same synchronization or ownership boundary. `binarySearch` does not lock that entire workflow for you.

## 9. Cost: Fewer Comparisons Does Not Always Mean Fewer Access Steps

### 9.1. On Random-Access Lists

When `get(index)` is effectively constant-time and the comparison cost is bounded, binary search performs `O(log n)` range-halving steps.

`ArrayList` is the common example of fast positional access. When a comparator compares large objects or performs expensive computation, the cost of each comparison still adds up. `O(log n)` comparisons does not mean comparisons are free.

### 9.2. On `LinkedList` or Large Sequential-Access Lists

`LinkedList` must traverse node links to reach an index. If you write your own algorithm that repeatedly calls `get(mid)` without checking the list type, total cost can be far worse than what the number of comparisons suggests.

The `Collections.binarySearch` specification describes using an iterator-based search for large lists that do not implement `RandomAccess`: it performs `O(log n)` element comparisons but `O(n)` link traversals. You must not claim total runtime on `LinkedList` is `O(log n)` just because the algorithm is called binary search.

[RandomAccess](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html) is a marker interface used by generic algorithms to distinguish positional-access capability. [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) documents index traversal; the operational guarantees of [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) follow a different model.

Do not hard-code a particular JDK version's algorithm-switching size threshold into application logic. Internal thresholds and implementation details are not business invariants.

### 9.3. Fast Position Lookup Does Not Make `ArrayList` Insertion Fast

Even though finding the insertion point on an `ArrayList` takes logarithmic steps, inserting into the middle of the list can still shift many elements, taking linear time in the number of shifted elements.

If you continuously insert data and must maintain order after every insertion, evaluate search, insertion, deletion, and duplicate-handling requirements together. Another ordered data structure may fit better, but do not replace a `List` with a `Set`/`Map` without accounting for differences in positional semantics and equality.

### 9.4. Should You Sort Before Every Search?

If the data is unsorted and you only need a single `equals`-based lookup, a linear search can be simpler and more appropriate than sorting the entire list. Sorting also alters the input order if done in place.

For many queries over rarely changing data, sorting once and searching many times can pay off. In standard comparison-sort analysis, an `O(n log n)` preparation cost can be amortized across many `O(log n)` lookups on a random-access structure.

If you must preserve the original source order, sort a separate copy or store the original index in your model. The result of `binarySearch` on the sorted copy is an index in that copy, not the original index in the unsorted input.

## 10. Detecting Precondition Violations and Handling Inputs

### 10.1. When Should You Check Order?

The `isSorted` method in `BinarySearchBoundsDemo` checks adjacent pairs in `O(n)` time. It is useful at data boundaries, during debugging, or in tests.

If you scan the entire list before every `binarySearch`, each lookup is no longer `O(log n)`. In a data-managing class, it is usually better to enforce order by design in the update paths, or validate when data enters or changes in batches.

Do not treat `isSorted` as proof that a contract-violating `Comparator` is suddenly valid. The method checks the data's order under the supplied comparator, assuming that comparator defines a proper ordering relation.

### 10.2. Type Errors and Comparability

The natural-ordering form requires elements and the key to be mutually comparable via `Comparable`. Generics catch many mismatches at compile time; if bypassed with raw types or invalid casts, `ClassCastException` can still occur at runtime.

The `Comparator` form does not require the element class itself to implement `Comparable`, as seen with the `Score` record in the example. Still, the comparator must be able to handle the actual elements and the search key.

Passing a `null` list provides no data to search and is invalid. `null` keys or `null` elements require a comparison policy that supports them; the mere fact that a `List` implementation permits `null` elements is not enough to make natural-ordering search valid.

### 10.3. Unsorted Input Should Not Have a "Standard Stdout" for Search Results

An example that intentionally passes an unsorted list and prints an index from `binarySearch` only shows the observed behavior of that single run. It does not establish a contract for outputs on precondition-violating inputs.

In this lesson, `isSorted([1, 3, 2])` returns `false` to detect the problem. Do not turn the search result on that sequence into an exercise that expects memorizing a fixed number.

## 11. Applying This in a Real Feature

For a list of data that needs repeated searching, you can structure the workflow as follows:

1. Define the exact search key and comparison relation, including tie-breakers if needed.
2. Validate data for types, `null`s, and business invariants.
3. Create or choose an appropriate `List`, then sort it according to that relation.
4. Perform `binarySearch` calls using the same compatible relation.
5. Branch on the result: matched index or decoded insertion point.
6. If you need the full group of equal elements, use a bound search with a clear contract.
7. Allow updates only through paths that preserve order, or re-sort when necessary.
8. Ensure the data does not change between searching and any index-dependent operation.

If you only need a presence/absence check without positional access or ordering, a key-based lookup structure may express the intent better. Even then, consider the equality relation: `Comparator` returning 0 may not match `equals`/`hashCode` lookup.

If the query is "find by score," a comparison result of 0 only confirms the score matches, not that all other fields match. If the query is "find the exact entity with a specific ID," include that requirement in the indexing model or an explicit verification step.

Do not use `binarySearch` as a general-purpose way to search any arbitrary `List`. It is valuable when the application genuinely maintains the required ordering relation.

## 12. Common Mistakes and How to Read Results Correctly

| Misuse | Problem | Fix |
|---|---|---|
| Searching an unsorted list | Eliminating half the range has no basis | Sort first or choose another search method |
| Sorting by one relation, searching by an incompatible one | The search's sorted precondition is violated | Use a comparator matching the current order |
| Checking `r > 0` | Misses a match at index 0 | Check `r >= 0` |
| Checking `r == -1` alone for "not found" | Other negative numbers also mean not found | Branch on `r < 0` |
| Using `Math.abs(r)` as the insertion point | Wrong formula and integer-boundary issues | Use `-(r + 1)` when `r < 0` |
| Passing insertion point `size` to `get` | `size` is the boundary past the last element | Use it only for operations whose contract accepts that boundary |
| Assuming the result is the first element in a duplicate group | The API makes no such guarantee | Compute `lowerBound`/`upperBound` when needed |
| Assuming `compare == 0` means `equals` | It may match only on one attribute | Understand the comparator and business rules |
| Adding an offset to a negative `subList` result | Adds to an encoded value | Decode first, then translate the index |
| Calling `sort` or `add` on a read-only list | Searching only reads, whereas modifying requires support | Prepare a separate mutable list when needed |
| Reusing an index across multiple updates | The index may point to a different element | Use the index only while data is stable |
| Calling every `binarySearch` `O(log n)` time | Ignores `LinkedList` traversal and comparison cost | Analyze both comparisons and element accesses |

## 13. Exercises and Solutions

### Exercise 1 — Index 0

Sorted list `[2, 5, 9]`. Searching for 2 returns 0. Is `if (r > 0)` correct to check whether it was found?

**Solution:** No. 0 is the valid index of the first element. Use `r >= 0`; any negative `r` belongs to the not-found branch.

### Exercise 2 — Decoding the Insertion Point

List `[2, 5, 9]`, searching for 7. What is the return value, and where would 7 be inserted?

**Solution:** The insertion point is 2, before 9, so the return value is -3. Decode it with `-(-3 + 1) = 2`. Do not use absolute value, which gives 3.

### Exercise 3 — Start Boundary, End Boundary, and Empty List

For `[2, 5, 9]`, what do searches for 1 and 12 return? For an empty list, what does searching for any number return?

**Solution:** Searching for 1 has insertion point 0, so it returns -1. Searching for 12 has insertion point 3, so it returns -4. An empty list has insertion point 0, so it returns -1.

### Exercise 4 — Descending Sequence

List `[9, 7, 4]` is sorted by `reverseOrder`. Searching for 8 with that comparator gives what insertion point and return value?

**Solution:** Insert at 1, between 9 and 7; the return value is -2. Searching with natural ordering on this list violates the precondition, so you must not rely on any specific return number.

### Exercise 5 — Duplicate Elements

List `[1, 3, 3, 3, 8]`, searching for 3. Can you assert that the result is 1? What are `lowerBound` and `upperBound` of 3?

**Solution:** You cannot assert that `binarySearch` picks 1; any valid index in `{1, 2, 3}` satisfies the contract. The two bounds are 1 and 4; the number of elements equal to the key is 3.

### Exercise 6 — `compare == 0` vs. `equals`

A list of `Score` is sorted by `points`. The search key has name `"probe"` and `points = 20`. If a `Score` with name `"C"` and `points = 20` is returned, is the result wrong because the name differs?

**Solution:** Not wrong for a comparator on `points` alone. That is a match by score group. If the name must also match, you need an appropriate search relation or an additional check within the group.

### Exercise 7 — Stable Sort and the First Result

A stable sort preserves the order of `Score` objects with equal points. Can you deduce from this that `binarySearch` will return the first `Score` in the group?

**Solution:** No. Stability is a contract of the sorting operation, while which match is returned within a group is a separate contract. To get the first element, search for the lower bound.

### Exercise 8 — `subList` and Negative Codes

`whole` is `[0, 10, 20, 30, 40, 50]`, and `part = whole.subList(2, 5)` is `[20, 30, 40]`. What does searching for 35 in `part` return, and what is the corresponding insertion point in `whole`?

**Solution:** In `part`, the insertion point is 2, so it returns -3. Translate to `whole` after decoding: `2 + 2 = 4`. Do not add the offset 2 directly to -3 and treat that as an index.

### Exercise 9 — Mutating an Element Field

A `List` of `Product` is sorted by `price`. A `Product` in the middle has its `price` changed to the highest price without moving its position. Simply because the list had no `add`/`remove` calls since sorting, is `binarySearch` guaranteed to remain valid?

**Solution:** No. Mutating a field used in comparisons can break order even if the list's structure and size did not change. Updates must be managed to preserve or restore order.

### Exercise 10 — `LinkedList` and Cost

A very large `LinkedList` is sorted. Is it true that `Collections.binarySearch` always runs in `O(log n)` time just because it compares only `O(log n)` elements?

**Solution:** No. Accessing/traversing the data structure also has a cost. The library contract describes `O(n)` link traversals in the iterator-based search for large sequential lists, even though the number of comparisons is `O(log n)`.

### Exercise 11 — Finer-Grained Comparator

A list is sorted by score then name. Does searching only by score necessarily violate the precondition? What about a list sorted only by score when searching by score then name?

**Solution:** A score-then-name order remains non-decreasing by score, so searching by score alone can be valid. The reverse direction does not guarantee name order within each score group; you must sort or verify according to the finer relation used for searching.

### Exercise 12 — Structurally Unmodifiable View

An unmodifiable view wraps a list containing mutable objects, sorted by a mutable field. Is blocking `add`/`set` through the view enough to preserve the search precondition?

**Solution:** No. The owner of the backing list or any holder of an element reference can still mutate state that changes the comparison relation. You need an appropriate element model and update controls, not just a structural wrapper.

## 14. Reference Documentation

- [Collections.binarySearch — ordering precondition, insertion point encoding, and complexity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#binarySearch(java.util.List,T,java.util.Comparator)).
- [List.sort — comparator and sort stability](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).
- [Comparator — ordering relation and differences from equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).
- [Comparable — natural ordering](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html).
- [RandomAccess — indexed access capability](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html).
