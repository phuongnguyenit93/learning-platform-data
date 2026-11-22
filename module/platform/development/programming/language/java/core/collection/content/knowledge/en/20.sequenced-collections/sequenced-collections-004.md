# addFirst, addLast, and Optional Operations on Sorted Sets

## 1. Having an Order Does Not Mean Choosing Positions Freely

Since Java 21, a sorted set such as TreeSet can be used through the Sequenced Collections interface hierarchy. As a result, learners may see addFirst and addLast on SortedSet and assume they can place an element at the beginning or end of the set.

What matters is **who decides the order**. With TreeSet, the comparison relation determines an element's position. With LinkedHashSet, the program can control the encounter order of elements without following a Comparator.

For example, suppose a set of numbers sorted in natural order currently contains 10,20,30:

- Adding 25 with add changes the set to 10,20,25,30.
- Asking to place 25 at the front with addFirst conflicts with the set's positioning policy.
- Even asking to place 5 at the front with addFirst is rejected by TreeSet; the API does not provide this operation conditionally based on the value.
- You can read or remove the first element without breaking the sorting rules of the remaining elements.

This lesson explains why the method exists yet may be unsupported, how to choose the right operation, and how to test behavior on Java 21. All complete programs in this lesson require **JDK 21 or later**; they do not use preview features.

### 1.1. Terms to Distinguish

| Concept | Meaning in This Lesson |
|---|---|
| Set | Stores elements while enforcing uniqueness; has no indices like List |
| Encounter order | The order in which elements appear when traversing a collection |
| Sorted set, SortedSet | Order governed by natural ordering or a Comparator |
| SequencedSet | A Set with a defined encounter order, along with operations at both ends |
| Explicit positioning | Requesting that an element be placed at the front or back using addFirst/addLast |
| Optional operation | A method declared in the API that an implementation may reject with UnsupportedOperationException |
| View | A way of looking at another collection's data, not by default a copy |

Reading these relationships accurately helps avoid two wrong conclusions: "TreeSet has addFirst, so it can definitely be called" and "TreeSet does not support addFirst, so the entire set cannot be modified."

## 2. How Does Java 21 Connect the Interfaces?

Before Java 21, SortedSet already had first, last, and range operations. Starting in Java 21, SortedSet also belongs to the SequencedSet hierarchy. Therefore, the same sorted set can be accessed through interfaces that share conventions for the first and last elements.

The diagram below shows only the branch of relationships needed for this lesson:

```text
SequencedCollection<E> + Set<E>
                  ↓
           SequencedSet<E>
                  ↓
             SortedSet<E>
                  ↓
           NavigableSet<E>
                  ↓
               TreeSet<E>
```

Arrows point from a broader interface to a more specialized interface or class. SequencedSet combines having an encounter order with Set semantics. SortedSet adds an ordering policy based on comparison.

Not every Set implements SequencedSet. For example, a variable declared as Set only allows calling Set methods at compile time. To write code using the new API, choose a declared type that matches the contract you actually intend to use.

The [SequencedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html) documentation describes this combined interface. It does not turn every order-modifying operation into a required supported operation.

### 2.1. Two Separate Questions at Two Different Times

| Question | Determined By |
|---|---|
| Can the code call this method name? | Declared type, generics, and API version at compile time |
| Can the call succeed? | Contract and capabilities of the actual object at runtime |

With SortedSet<Integer> on Java 21, addFirst exists, so the call compiles. However, the TreeSet object rejects the operation with UnsupportedOperationException.

Changing the receiving variable from SortedSet to SequencedSet does not create a different collection. Operations on the actual object still retain TreeSet's policy. Casting also does not add an order-changing mechanism to the object.

## 3. What Do addFirst and addLast Require?

### 3.1. Positioning Postconditions

addFirst takes an element and requires that, upon normal completion, that element is the first element in encounter order. addLast requires the element to be at the end.

Both methods return void. Do not treat their return value like the boolean result of add.

| Method | Return Value | What the Program Is Requesting |
|---|---|---|
| add(e) on a modifiable Set | boolean | Ensure the element is present according to the set's rules, and report whether the set changed as a result |
| addFirst(e) | void | Place the element at the front in encounter order |
| addLast(e) | void | Place the element at the end in encounter order |

Sharing the same method name across different collections does not erase each collection's own policy. On a List, adding at the front/back and handling duplicate elements have a different meaning than on a Set, which only keeps unique elements. In this lesson, the focus is on sets and the positioning limits of sorted sets.

### 3.2. "Optional" Does Not Mean the Parameter Can Be Omitted

An optional operation still has a full signature; the caller does not omit the parameter e. "Optional" here refers to whether an implementation supports that data-modifying operation.

[SequencedCollection — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html) declares addFirst and addLast as optional operations. The default implementations in the interface reject them. Classes that support positioning provide appropriate behavior; classes that cannot let the caller choose positions keep or document the rejection.

UnsupportedOperationException is an unchecked exception—the compiler does not force you to declare or catch it. Code that compiles does not prove the call will succeed.

### 3.3. TreeSet Does Not Position by Front/Back Requests

[SortedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html) specifies that addFirst and addLast throw UnsupportedOperationException; the comparison rules already govern placement. [TreeSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html) documents the same behavior.

With a standard TreeSet, there is no special branch saying "if the element would naturally be first, allow addFirst." All of the following cases are rejected:

- The new element is smaller than all elements under natural ordering.
- The new element is larger than all elements when calling addLast.
- The element already exists.
- The set is currently empty.
- The reference variable has the broader type SequencedSet.

Treat this as part of the operation's contract. Do not write code that relies on predicting "my value surely fits at the front of the set."

## 4. Program 1: Positioning Is Rejected, but add Still Works

Save to `SortedPositionDemo.java`. The expectUnsupported helper is used to verify calls that are expected to fail; if a call does not throw an exception, the program throws AssertionError so it does not report a misleading test result.

```java
import java.util.List;
import java.util.SequencedSet;
import java.util.SortedSet;
import java.util.TreeSet;

public class SortedPositionDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        SortedSet<Integer> sorted = new TreeSet<>(List.of(10, 30));
        System.out.println("initial=" + sorted);
        expectUnsupported("addFirstSmaller", () -> sorted.addFirst(5));
        expectUnsupported("addLastLarger", () -> sorted.addLast(40));
        expectUnsupported("addFirstExisting", () -> sorted.addFirst(10));
        System.out.println("afterRejected=" + sorted);
        System.out.println("add20=" + sorted.add(20));
        System.out.println("add10Again=" + sorted.add(10));
        System.out.println("afterAdd=" + sorted);
        System.out.println("ends=" + sorted.getFirst() + "," + sorted.getLast());

        SequencedSet<Integer> throughInterface = sorted;
        expectUnsupported("throughSequencedSet",
                () -> throughInterface.addFirst(5));

        SortedSet<Integer> empty = new TreeSet<>();
        expectUnsupported("emptyAddFirst", () -> empty.addFirst(1));
        expectUnsupported("emptyAddLast", () -> empty.addLast(1));
        System.out.println("emptyStillEmpty=" + empty.isEmpty());
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 SortedPositionDemo.java
java SortedPositionDemo
```

Stdout:

```text
initial=[10, 30]
addFirstSmaller=UnsupportedOperationException
addLastLarger=UnsupportedOperationException
addFirstExisting=UnsupportedOperationException
afterRejected=[10, 30]
add20=true
add10Again=false
afterAdd=[10, 20, 30]
ends=10,30
throughSequencedSet=UnsupportedOperationException
emptyAddFirst=UnsupportedOperationException
emptyAddLast=UnsupportedOperationException
emptyStillEmpty=true
```

### 4.1. Elements Matching the Two Ends Are Still Rejected

5 is less than 10, and 40 is greater than 30. Yet both corresponding positioning calls throw UnsupportedOperationException. TreeSet does not perform add and then verify the position; it simply does not provide explicit positioning.

Calling addFirst(10) also fails even though 10 is already the first element. You cannot turn addFirst into a "no-op is fine" call just because the element is already in that spot.

`afterRejected=[10, 30]` confirms that the three test calls did not modify the set in this example.

### 4.2. add Still Inserts According to Sorting Rules

add(20) returns true and the set becomes `[10, 20, 30]`. add(10) then returns false because the element is already present. This is the behavior of add on a set of numbers using natural ordering, unrelated to permission to place an element at the front.

getFirst and getLast read the two ends as 10 and 30. Reading elements at either end is completely compatible with the sorting policy.

### 4.3. Reference Type and Empty State Do Not Grant Extra Permissions

throughInterface still points to the exact same original TreeSet. Therefore, addFirst through SequencedSet is also rejected.

The empty set has no elements yet, but addFirst and addLast still throw an exception; `emptyStillEmpty=true`. There is no need to check whether the set is empty before deciding to use addFirst on a TreeSet. If the goal is to add a value to the set according to its Comparator, use add.

## 5. Adding to a Sorted Set the Right Way

### 5.1. Let the Comparator Decide the Position

With a modifiable TreeSet, the standard approach is add(e) or addAll(collection). Elements are placed according to natural ordering or the Comparator chosen when creating the set.

If a task needs to "add a new smallest element" in business terms, compute that value first and still call add so the set places it in the right spot. The business requirement's wording does not make addFirst a supported API.

If the business requirement wants an arbitrary element to come before all others regardless of the Comparator, that requirement differs from a set always sorted by the current Comparator. You need to change the data model or design an appropriate priority key instead of breaking the SortedSet contract.

### 5.2. Duplicates Are Determined by Comparison

In the example's TreeSet<Integer>, 10 compares equal to 10, so calling add again does not create another entry. With custom data types, the Comparator determines whether the set treats two elements as the same element when comparison returns 0.

The Comparator should be consistent with equals so the set fulfills the general Set contract. Do not use a Comparator solely to force an object to the front if it accidentally makes distinct elements compare as 0 and get merged.

If the order depends on an element's property, do not mutate that property while the element is still inside the TreeSet and expect the tree to re-sort itself. The standard design is to remove the element from the set before changing its sort key, then add it back; operations should be coordinated according to the program's access requirements.

### 5.3. Do Not Silently Change Meaning When Catching Exceptions

An intent-breaking anti-pattern is: try addFirst; if UnsupportedOperationException occurs, call add and treat the request as fulfilled.

With TreeSet, add may place the element in the middle. In that case, the code does not satisfy the caller's "place at the front" request. If you only need to ensure the element belongs to the set, choose add from the start. If positioning is mandatory, use a structure that supports it or clearly document the API's preconditions.

Do not use a mutating operation as a harmless capability probe on an arbitrary collection. On a class that supports it, the probe call can actually alter the order.


## 6. When You Need Position Control, Choose the Right Ordering Policy

### 6.1. LinkedHashSet Can Change Encounter Order

A set with an encounter order does not have to be sorted by a Comparator. LinkedHashSet is an example: it preserves Set uniqueness and has an iteration order that the program can adjust using addFirst/addLast in Java 21.

For a new element, addFirst puts it at the front and addLast puts it at the end. For an existing element, these two methods can move that element's position to the front or end without creating a duplicate in the set.

This differs from ordinary add on LinkedHashSet. Calling add with an existing element does not move that element to the end. You must distinguish between "ensure the element is present" and "move the element to the front/end."

The specific contract is described in [LinkedHashSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html). This is the behavior of a structure that supports positioning; you cannot infer in reverse that TreeSet must do the same.

### 6.2. Copying to Another Structure Is a Policy-Changing Decision

You can create a LinkedHashSet from the elements currently yielded by iterating a TreeSet. When newly created, the copy receives that iteration order. Afterward, calling addFirst/addLast on the LinkedHashSet can make its order completely different from the TreeSet's comparison order.

This is appropriate if the task has shifted to maintaining a manual order. It is not a way to add addFirst support to the source TreeSet itself. The source set and target set have different underlying storage structures.

With custom types, you must also consider how uniqueness is determined: TreeSet relies on comparison, whereas LinkedHashSet uses the hash-based Set contract of equals/hashCode. If the Comparator is inconsistent with equals, switching structures can change which elements are kept or deduplicated later. Do not choose a copy merely to bypass an exception while ignoring business requirements.

## 7. Program 2: Adding New Elements and Moving Existing Ones in LinkedHashSet

Save to `SequencedInsertionDemo.java`:

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;

public class SequencedInsertionDemo {
    public static void main(String[] args) {
        LinkedHashSet<String> names = new LinkedHashSet<>(List.of("beta", "gamma"));
        names.addFirst("alpha");
        names.addLast("delta");
        System.out.println("afterNewElements=" + names);
        names.addFirst("gamma");
        System.out.println("afterMoveFirst=" + names);
        System.out.println("sizeAfterMove=" + names.size());
        System.out.println("ordinaryAddExisting=" + names.add("alpha"));
        System.out.println("afterOrdinaryAdd=" + names);
        names.addLast("gamma");
        System.out.println("afterMoveLast=" + names);

        TreeSet<Integer> sorted = new TreeSet<>(List.of(3, 1, 2));
        LinkedHashSet<Integer> manualOrder = new LinkedHashSet<>(sorted);
        manualOrder.addFirst(99);
        System.out.println("manualOrder=" + manualOrder);
        System.out.println("originalSorted=" + sorted);
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 SequencedInsertionDemo.java
java SequencedInsertionDemo
```

Stdout:

```text
afterNewElements=[alpha, beta, gamma, delta]
afterMoveFirst=[gamma, alpha, beta, delta]
sizeAfterMove=4
ordinaryAddExisting=false
afterOrdinaryAdd=[gamma, alpha, beta, delta]
afterMoveLast=[alpha, beta, delta, gamma]
manualOrder=[99, 1, 2, 3]
originalSorted=[1, 2, 3]
```

### 7.1. A New Element Is Placed at the Front or End

names starts with beta,gamma. addFirst(alpha) and addLast(delta) produce `[alpha, beta, gamma, delta]`. There is no Comparator forcing alpha or delta to find their positions by alphabetical comparison.

This is the order produced by the operations. Do not treat the fact that the resulting list of names happens to look alphabetically readable as evidence that LinkedHashSet sorts itself.

### 7.2. Existing Elements Are Repositioned, Not Duplicated

gamma already exists. addFirst(gamma) moves it to the front, producing `[gamma, alpha, beta, delta]`; size remains 4.

add(alpha) returns false and does not change the order. Then addLast(gamma) moves gamma to the end, producing `[alpha, beta, delta, gamma]`. The set still contains only one gamma.

Because addFirst/addLast return void, the example checks the order and size after the calls. They do not return a boolean indicating "newly added vs. merely repositioned."

### 7.3. A Manual-Order Copy No Longer Auto-Sorts Like TreeSet

The numeric TreeSet prints as `[1, 2, 3]` even though it was created from 3,1,2. The LinkedHashSet copied from it initially has the same order, and then addFirst(99) turns the copy into `[99, 1, 2, 3]`.

The source TreeSet remains `[1, 2, 3]`. If the task requires all elements to stay in ascending order, the copy after that operation no longer satisfies that requirement. If the task wants to prioritize displaying 99 first, a structure with manual ordering may be more suitable.

## 8. reversed and Subsets Do Not Remove the Sorting Policy

### 8.1. Reversing the View Does Not Turn SortedSet into a Free-Order List

TreeSet is a NavigableSet. In Java 21, NavigableSet's reversed is equivalent to descendingSet: viewing the elements in the reverse of the current order.

For a natural-order TreeSet containing 10,20,30,40, the reversed view has order 40,30,20,10. The "first" element in the reversed view is 40; the "last" element in the reversed view is 10.

Even so, the view is still a set with a sorting policy. You cannot use reversed to unlock addFirst/addLast. Ordinary additions via add on the view are placed according to the set's ordering and are reflected in the source set if the view is modifiable.

The API's reversal relationship is stated in [NavigableSet.reversed — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html). For the TreeSet in this example, views share the source data; they are not independent copies.

### 8.2. Subsets Enforce Additional Range Constraints

A subSet view of a TreeSet only allows working with elements within the selected range. It still maintains order, and a valid addition must satisfy both the range bounds and the set's element constraints.

Two different errors:

- addFirst/addLast request explicit positioning, so they are rejected on this TreeSet view.
- add with an out-of-range value is an ordered insertion that violates the view's bounds, so it throws IllegalArgumentException.

Do not explain every exception on a subset with a single "unmodifiable" cause. The view is modifiable within its range, but it does not support explicit positioning and does not accept out-of-range values.

## 9. Program 3: Reversed View and Range View

Save to `SortedViewsDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.SortedSet;
import java.util.TreeSet;

public class SortedViewsDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        NavigableSet<Integer> base = new TreeSet<>(List.of(10, 20, 30, 40));
        NavigableSet<Integer> reverse = base.reversed();
        System.out.println("reverseInitial=" + reverse);
        expectUnsupported("reverseAddFirst", () -> reverse.addFirst(50));
        expectUnsupported("reverseAddLast", () -> reverse.addLast(5));
        System.out.println("reverseAdd25=" + reverse.add(25));
        System.out.println("baseAfterAdd=" + base);
        System.out.println("reverseAfterAdd=" + reverse);
        System.out.println("reverseRemoveFirst=" + reverse.removeFirst());
        System.out.println("baseAfterReverseRemove=" + base);

        SortedSet<Integer> middle = base.subSet(15, true, 30, false);
        System.out.println("middleInitial=" + middle);
        expectUnsupported("middleAddFirst", () -> middle.addFirst(17));
        System.out.println("middleAdd17=" + middle.add(17));
        try {
            middle.add(50);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("middleOutside=IllegalArgumentException");
        }
        System.out.println("middleAfterAdd=" + middle);
        System.out.println("middleRemoveLast=" + middle.removeLast());
        System.out.println("baseFinal=" + base);
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 SortedViewsDemo.java
java SortedViewsDemo
```

Stdout:

```text
reverseInitial=[40, 30, 20, 10]
reverseAddFirst=UnsupportedOperationException
reverseAddLast=UnsupportedOperationException
reverseAdd25=true
baseAfterAdd=[10, 20, 25, 30, 40]
reverseAfterAdd=[40, 30, 25, 20, 10]
reverseRemoveFirst=40
baseAfterReverseRemove=[10, 20, 25, 30]
middleInitial=[20, 25]
middleAddFirst=UnsupportedOperationException
middleAdd17=true
middleOutside=IllegalArgumentException
middleAfterAdd=[17, 20, 25]
middleRemoveLast=25
baseFinal=[10, 17, 20, 30]
```

### 9.1. add on a Reversed View Still Places by Comparison

reverse is initially `[40, 30, 20, 10]`. addFirst(50) and addLast(5) both fail even though those values appear to fit the two ends of the reversed order.

reverse.add(25) succeeds. The source set becomes `[10, 20, 25, 30, 40]`, while the reversed view displays `[40, 30, 25, 20, 10]`. No new element is forced to the front or end.

### 9.2. Removing the First Element of the Reversed View Removes the Last Element of the Source

reverse.removeFirst retrieves and removes 40. The source set afterward is `[10, 20, 25, 30]`.

Removing an element does not require arbitrarily repositioning a remaining element. The remaining elements stay in order, so a modifiable TreeSet can support removal at both ends even though it does not support positional insertion.

### 9.3. Range [15,30) and Three Different Calls

middle uses the NavigableSet overload with an inclusive lower bound of 15 and an exclusive upper bound of 30. The initial data in range is 20,25.

- middle.addFirst(17) throws UnsupportedOperationException because positioning is not supported.
- middle.add(17) returns true because 17 is valid within the range and not yet present.
- middle.add(50) throws IllegalArgumentException because 50 is outside the range.

Afterward middle is `[17, 20, 25]`. middle.removeLast removes 25 from the view and from the source set. The final source set is `[10, 17, 20, 30]`.

The middle variable is declared as SortedSet even though it was created from a TreeSet with NavigableSet capabilities. That still allows calling addFirst, getFirst, or removeLast on Java 21. The reference type does not change the positioning policy or range bounds of the actual object.


## 10. Other Operations at Both Ends Must Be Considered Separately

### 10.1. Reading First/Last Is Not Adding First/Last

getFirst and getLast return the elements at the two ends according to the collection's current order. For SortedSet, they correspond to first and last. They do not remove elements.

Do not assume "first is always the smallest number." If a TreeSet uses Comparator.reverseOrder, the order is 30,20,10; getFirst returns 30 and getLast returns 10. "First" is interpreted according to the set's Comparator, not ascending numeric intuition.

When a modifiable set is empty, there is no element for getFirst/getLast to return; these read operations throw NoSuchElementException. Do not treat null as their empty result.

### 10.2. Removing at Both Ends Can Be Supported

A modifiable TreeSet supports removeFirst and removeLast in Java 21. They return the removed element; the remaining elements maintain their order.

For an empty TreeSet, removeFirst/removeLast throw NoSuchElementException. NavigableSet also has pollFirst/pollLast, which return null when empty. The example in this lesson uses non-null Integer values, so the null result from pollFirst clearly illustrates the empty case.

Do not generalize that every SortedSet allows removal. Removal operations can still be unsupported on an unmodifiable view or an implementation with corresponding restrictions. Evaluate each operation on the actual object.

### 10.3. Rejecting Positioning Differs from Disallowing All Modifications

An ordinary TreeSet rejects addFirst/addLast due to its ordering policy, yet allows add and remove.

A view created by Collections.unmodifiableSortedSet has a different constraint: it prevents the user from modifying data through that view. Therefore, even add or removeFirst is rejected, even though the source TreeSet is modifiable.

An unmodifiable view is not necessarily an independent snapshot that never changes over time. If another reference can still modify the source set, reading through the view can observe the new source data. This contract is described in [Collections.unmodifiableSortedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

Do not use addFirst as a test for "is this collection modifiable?": a modifiable TreeSet rejects it too. Likewise, do not use a successful add to infer that every other mutating operation will succeed.

## 11. Program 4: Comparator, End Removals, and Unmodifiable View

Save to `SortedOptionalOperationsDemo.java`:

```java
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.SortedSet;
import java.util.TreeSet;

public class SortedOptionalOperationsDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    static void expectEmpty(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (java.util.NoSuchElementException expected) {
            System.out.println(label + "=NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        TreeSet<Integer> descending = new TreeSet<>(Comparator.reverseOrder());
        descending.addAll(List.of(10, 20, 30));
        System.out.println("descending=" + descending);
        System.out.println("ends=" + descending.getFirst() + "," + descending.getLast());
        expectUnsupported("descendingAddFirst", () -> descending.addFirst(40));
        expectUnsupported("descendingAddLast", () -> descending.addLast(0));
        System.out.println("removeFirst=" + descending.removeFirst());
        System.out.println("removeLast=" + descending.removeLast());
        System.out.println("afterEndRemovals=" + descending);

        SortedSet<Integer> readOnly = Collections.unmodifiableSortedSet(descending);
        System.out.println("readOnlyFirst=" + readOnly.getFirst());
        expectUnsupported("readOnlyAdd", () -> readOnly.add(25));
        expectUnsupported("readOnlyRemoveFirst", () -> readOnly.removeFirst());
        descending.add(15);
        System.out.println("readOnlyAfterSourceAdd=" + readOnly);

        TreeSet<Integer> empty = new TreeSet<>();
        expectEmpty("emptyGetFirst", () -> empty.getFirst());
        expectEmpty("emptyRemoveFirst", () -> empty.removeFirst());
        System.out.println("emptyPollFirst=" + empty.pollFirst());
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 SortedOptionalOperationsDemo.java
java SortedOptionalOperationsDemo
```

Stdout:

```text
descending=[30, 20, 10]
ends=30,10
descendingAddFirst=UnsupportedOperationException
descendingAddLast=UnsupportedOperationException
removeFirst=30
removeLast=10
afterEndRemovals=[20]
readOnlyFirst=20
readOnlyAdd=UnsupportedOperationException
readOnlyRemoveFirst=UnsupportedOperationException
readOnlyAfterSourceAdd=[20, 15]
emptyGetFirst=NoSuchElementException
emptyRemoveFirst=NoSuchElementException
emptyPollFirst=null
```

### 11.1. First/Last Follow the Comparator

descending has order `[30, 20, 10]` and ends prints `30,10`. addFirst(40) and addLast(0) are rejected even though both values match the two ends under descending order.

removeFirst removes 30; removeLast removes 10. The set has `[20]` remaining. The output shows that you cannot lump every method containing First/Last into a single support level.

### 11.2. Unmodifiable Views Remain Readable and Backed by the Source

readOnly can read the first element 20. add(25) and removeFirst both throw UnsupportedOperationException because they are called through the unmodifiable view.

The call descending.add(15) runs through the source TreeSet reference and succeeds. Afterward readOnly sees `[20, 15]`, following the source's descending Comparator.

The example does not use multiple threads. The fact that two references share data does not mean TreeSet is thread-safe for concurrent access; synchronization requirements are a separate concern.

### 11.3. Missing Elements Differ from Unsupported Operations

empty is a modifiable TreeSet that is currently empty. getFirst and removeFirst throw NoSuchElementException because there are no elements, whereas pollFirst returns null.

This case differs from addFirst on an empty set in Program 1: the positioning operation is rejected with UnsupportedOperationException. If an object has multiple constraints at once, do not write logic that relies on a single universal exception-checking order across all implementations. The examples test each condition separately on concrete objects.

## 12. Designing Caller Code to Match Actual Requirements

### 12.1. Choosing Operations by Intent

| Caller's Intent | Appropriate Choice | What Must Be Ensured |
|---|---|---|
| Keep unique values always ordered by a Comparator | TreeSet with add/addAll | Comparable elements, valid Comparator, object permits addition |
| Read the first or last element of a sorted set | getFirst/getLast or first/last | Elements exist; use first/last according to the Comparator |
| Retrieve and remove the first/last element | removeFirst/removeLast on a modifiable TreeSet | Non-empty and removal is supported |
| Retrieve and remove with null when empty | NavigableSet's pollFirst/pollLast | Understand the source's null policy and removal semantics |
| Control encounter order while keeping uniqueness | LinkedHashSet with addFirst/addLast | Accept manual ordering instead of always sorting by Comparator |
| Need multiple positions with duplicate elements and chosen order | An appropriate List | Requirement differs from Set uniqueness |
| Provide read-only access to a sorted set | Appropriate unmodifiable view | Do not treat the view as a deep copy or fixed snapshot |

Do not choose based only on the phrase "ordered collection." Ask whether the order comes from comparison, insertion order, or explicit repositioning operations.

### 12.2. A SequencedSet Signature Is Not Enough to Promise Positioning

A method accepting SequencedSet<E> may receive a LinkedHashSet, a TreeSet, or an unmodifiable view. Therefore, looking at this signature alone is not enough to promise that addFirst will always succeed.

If the method truly needs positioning, it must document the requirement that the argument support that operation, or own an appropriate structure internally. If the input is only for reading, it can create a new result structure with the chosen ordering policy.

Do not detect capabilities by checking a short list of classes and assuming all other classes behave identically. Wrappers and custom classes may have their own restrictions. The API contract for inputs and outputs should make modification permissions explicit.

### 12.3. Java Version Is Part of the Deployment Contract

The examples use APIs added in Java 21, so both the compile target and runtime environment must match. Using a newer JDK with `--release 17` still will not make Java 21 APIs available to code compiled for Java 17.

Check which JDK installation `javac` and `java` point to if multiple versions are installed. Do not simply rename variable types or add casts to work around missing-API errors caused by version mismatches.

In code that must remain Java 17-compatible, TreeSet still has add, first, last, and the corresponding older APIs; do not call new methods such as addFirst/getFirst through Java 21 APIs and expect to run unchanged on Java 17.

### 12.4. Valid Elements Are Still a Separate Precondition

Ordinary add can also fail because elements are not comparable, null is not accepted by the source, or a value falls outside a view's range. "Use add instead of addFirst for TreeSet" does not mean ignoring all other preconditions.

The examples in this lesson use non-null integers or strings with simple contracts to isolate unsupported-positioning errors clearly. When switching to business data, also check Comparator, equals/hashCode, and view bounds accordingly.

## 13. Common Mistakes and How to Test

| Mistake | Why It Is Wrong | How to Correct Your Understanding |
|---|---|---|
| addFirst appears in IDE autocomplete, so it must work | Having a method at the type level does not guarantee runtime support | Read the contract of the actual object |
| An empty TreeSet must allow addFirst | TreeSet rejects positioning operations even when empty | Use add if you need ordered insertion |
| Only passing a value smaller than all elements avoids the exception | Rejection does not depend on the value's predicted position | Do not use addFirst/addLast on TreeSet |
| Changing the variable to SequencedSet unlocks positioning | It is still the same TreeSet object | Choose a structure with the right policy if positioning is needed |
| Seeing UnsupportedOperationException and concluding the set is unmodifiable | Perhaps only the positioning operation is unsupported | Evaluate each operation and wrapper separately |
| Catching addFirst's error and calling add as if it means the same thing | add does not guarantee placing at the front | Clearly choose ordered insertion vs. explicit positioning |
| Using add to move an existing LinkedHashSet element to the end | add on an existing element does not change encounter order | Use addLast when you actually want to move to the end |
| Expecting addFirst on a Set to create a duplicate | Set still enforces uniqueness | Use a different structure if duplicates are required |
| Assuming reversed removes the comparison policy | The reversed view still has a constrained order | Use add according to order, not explicit positioning |
| Confusing out-of-range insertion with unsupported positioning | IllegalArgumentException and UnsupportedOperationException are two different conditions | Check range bounds and operation type separately |
| Assuming getFirst returns null when the set is empty | That operation throws NoSuchElementException | Check for emptiness or choose an API with a different contract |
| Treating an unmodifiable view as a copy that never changes | The source set can still be modified through another reference | Create a copy if independent data storage is required |

When testing code that uses this API, include cases for: non-empty sets; empty sets; new elements; existing elements; ascending and descending Comparators; reversed views; range views; and unmodifiable views. Check the data after calls as well to catch unintended order changes or source-set mutations.

The expectUnsupported helpers in this lesson are for verification examples. In production code, do not catch a broad Exception and ignore it: that hides element errors, range errors, and other unrelated bugs.

## 14. Self-Check and Practice

### 14.1. Questions and Answers

1. **Why does SortedSet have addFirst starting in Java 21, yet TreeSet throws an exception?** SortedSet participates in the SequencedSet hierarchy, while placement in TreeSet is determined by comparison. The shared API defines optional operations; TreeSet does not support explicit positioning.
2. **A TreeSet contains 10,30; does addFirst(5) work since 5 is indeed the smallest?** No. TreeSet throws UnsupportedOperationException. To add 5 according to sorting rules, call add(5).
3. **Does switching to a SequencedSet variable change the behavior?** No. The object is still a TreeSet, so its restrictions remain unchanged.
4. **Does TreeSet not supporting addLast prove that removeLast is also unsupported?** No. A modifiable TreeSet can remove the last element, while disallowing element positioning via addLast.
5. **A LinkedHashSet contains beta,gamma; does addFirst(gamma) increase its size?** No. gamma is moved to the front if needed, not duplicated.
6. **Does add(alpha) when alpha is already in LinkedHashSet move alpha to the end?** No. add on an existing element does not change encounter order; addLast expresses the request to move to the end.
7. **If a TreeSet has a descending Comparator, does getFirst return the smallest or largest number in the non-null number example?** With Comparator.reverseOrder and the numbers in the example, getFirst returns the largest number in standard numeric order, because it comes first under the descending Comparator.
8. **Does a TreeSet's reversed view allow addFirst?** No. It is still subject to the sorted set's positioning policy.
9. **Why can subSet allow add(17) while rejecting addFirst(17)?** 17 can be valid within the range for ordinary insertion; explicit positioning is still unsupported.
10. **If an unmodifiable view rejects add, can we conclude the source set can never change?** No. The source may still be modified through another reference; the view restricts modifications through itself.

### 14.2. Exercise: Classify Operations on the Same Data

Create a `TreeSet<Integer>` with data 9,3,6. Before running, predict each operation individually: add(1), addFirst(0), addLast(10), getFirst, removeLast.

Run them on fresh sets with the same data if you want independent tests. Expected outcomes:

- add(1) succeeds and the set has order 1,3,6,9.
- addFirst(0) and addLast(10) throw UnsupportedOperationException.
- getFirst on the initial set returns 3 without removing it.
- removeLast on the initial set returns 9 and leaves 3,6.

Explain in terms of ordering policy and operation support, not just by naming the exceptions.

### 14.3. Exercise: Choose a Structure from Requirements

One screen needs to keep unique codes in ascending order. Another screen needs to let users move an existing code to the top of a priority list.

For the first screen, use TreeSet and add according to sorting rules. For the second screen, a LinkedHashSet with addFirst can work if uniqueness is still needed and only front/back control is required.

State clearly what changes if you copy the ascending set into a LinkedHashSet and move a large code to the front: the stored data becomes structurally independent, and the always-ascending policy is no longer maintained in that copy.

### 14.4. Exercise: Observe First Element by Comparator and View

Create a `TreeSet<Integer>` with a descending Comparator containing 4,8,12. Predict getFirst on the original set, getFirst on reversed, and then try addFirst on each side.

Expect the first element of the original set to be 12, and the first element of the reversed view to be 4. Both addFirst calls are still rejected. To add 10 to the set, use add and observe 10's position from both views.

## 15. References and Verification

- [SortedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html): relationship with SequencedSet, unsupported positioning operations, and reading/removing at both ends.
- [TreeSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html): comparison-based ordering and the concrete class's addFirst/addLast behavior.
- [SequencedCollection — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): common operations at both ends and the optional nature of mutating operations.
- [SequencedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html): Set with encounter order while preserving uniqueness.
- [LinkedHashSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html): positioning new elements or moving existing ones.
- [NavigableSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html): reversed, removeFirst/removeLast, and range views.
- [Collections — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): unmodifiableSortedSet view.

All four complete programs were compiled with `javac --release 21 -encoding UTF-8` and run on JDK 21.0.9. The Stdout in this lesson matches the actual run output. Calls expected to throw exceptions were verified directly, and data before/after was printed to illustrate mutability and the relationship between source sets and views.
