# List: Positional Characteristics, Duplicate Elements, and Traversal Order

`List<E>` represents a **sequence of elements ordered by position**. When reading a list, we care not only about "which values are present," but also "at what position and in what order each value appears."

For example:

```text
[C, A, C, B]
```

This sequence has four elements. The two occurrences of C are at two different positions. The current order is C, then A, then C, then B; it does not need to be in ascending order.

Three characteristics must be understood together:

1. **Positional:** elements can be accessed or manipulated at an index.
2. **Can hold duplicate elements:** equal occurrences remain distinct positions.
3. **Traversed in sequence order:** normal forward traversal proceeds from the first position to the last.

## 1. Why Use the List Model?

A music playlist can play the same song multiple times. An action history can record the same operation at multiple points in time. Steps in a workflow have a before-and-after order.

In these situations, knowing only the set of unique values is not enough:

```text
Playlist 1: [A, B, A]
Playlist 2: [A, A, B]
```

Both contain A and B with three occurrences in total, but the playback experience is different because the order differs.

A `List` is suitable when **position and occurrence count** are part of the data that must be preserved. If the requirement is to have no duplicate values, you should not expect `List` to automatically enforce that uniqueness constraint.

`List` is an interface in the Java Collections Framework that extends `Collection` and `Iterable`. Classes such as `ArrayList` and `LinkedList` provide different implementations of this model. See the [Java 17 List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

## 2. Indices Are 0-Based and Tied to the Current State

Given:

```text
List:   [C, A, C, B]
Index:   0  1  2  3
```

- The first element is at index 0.
- The last element is at index `size() - 1`.
- With a size of 4, valid element indices are 0, 1, 2, 3.

An index is not a persistent identifier for an object. It describes a position in the **current sequence**.

### 2.1. size Counts Occurrences

The `size()` of `[C, A, C, B]` is 4, not 3. C appears twice, and each occurrence occupies one position.

If a list permits `null`, a `null` is also an element counted toward `size`. A `null` does not create an unindexed "gap" outside the index sequence.

### 2.2. Index Bounds Differ by Operation

Suppose a list has `n` elements and the corresponding mutating operations are supported:

| Operation | Index Range |
| --- | --- |
| `get(index)` | `0 <= index < n` |
| `set(index, value)` | `0 <= index < n` |
| `remove(index)` | `0 <= index < n` |
| `add(index, value)` | `0 <= index <= n` |

For insertion, an index equal to `n` means inserting at the end. However, `get(n)` is invalid because no element exists at that position yet.

An empty list has a size of 0:

- No index can be used to read an element.
- You can insert at index 0 if the list supports addition.

Do not call `get(size())` to retrieve the last element. For a non-empty list, the last position is `size() - 1`.

### 2.3. Insertion and Removal Shift Positions

Initially:

```text
[C, A, C, B]
 0  1  2  3
```

Insert X at index 1:

```text
[C, X, A, C, B]
 0  1  2  3  4
```

The element previously at index 1 moves to index 2. Subsequent elements also receive new indices.

If you store an index and then insert or remove elements before it, the old index may point to a different value or become invalid. When business logic requires identifying a record across multiple modifications, use a dedicated identifier rather than treating the index as an identity.

## 3. Distinguishing Appending, Inserting, Replacing, and Removing

The following operations do not mean the same thing:

| Operation | Effect if Successful | Size Change |
| --- | --- | --- |
| `add(value)` | Appends to the end of the sequence | Increases by 1 |
| `add(index, value)` | Inserts before the element currently at that position, or at the end of the sequence | Increases by 1 |
| `set(index, value)` | Replaces the value at an existing position | Unchanged |
| `remove(index)` | Removes the occurrence at that position | Decreases by 1 |
| `remove(value)` | Removes the first matching occurrence by value | Decreases by 1 if an element was removed |

Starting with `[C, A, C, B]`:

- `add(1, "X")` produces `[C, X, A, C, B]`.
- From that result, `set(2, "M")` produces `[C, X, M, C, B]`; A is replaced, and no new position is created.
- `remove(0)` removes the first C, producing `[X, M, C, B]`.

`set` returns the old value at the replaced position. `remove(int)` returns the removed element. `remove(Object)` returns a `boolean` indicating whether an occurrence was removed.

These distinctions help explain how the sequence changes without needing to know whether the underlying implementation uses an array or linked nodes.

## 4. Duplicate Elements Are Distinct Occurrences

### 4.1. Value Equality Does Not Require Reference Identity

A list can contain two different objects that are equal according to `equals`.

With a record:

```java
record Entry(String code) {}
```

two `new Entry("A")` calls create two separate objects. However, the record's `equals` method considers them equal because they share the same `code`.

If both are added to an `ArrayList`, both occurrences are kept. These are not two variables "pointing to the same list slot."

A list can also hold the exact same object reference at multiple positions. In that case, mutating the object's state becomes visible at every position referencing it. A list stores references; adding an object again does not perform a deep copy of that object.

### 4.2. indexOf and lastIndexOf Answer Two Different Questions

For `[A, B, A]`:

| Query | Result |
| --- | --- |
| `indexOf("A")` | 0 |
| `lastIndexOf("A")` | 2 |
| `indexOf("Z")` | -1 |
| `contains("A")` | true |

`indexOf` finds the first occurrence, `lastIndexOf` finds the last occurrence, and `contains` only asks whether at least one matching element exists.

Object search operations use the `equals` contract rather than comparing references solely with `==`.

Do not pass a `-1` result as an index to `get`. Always check whether the element was found first.

### 4.3. Removing by Value Does Not Remove All Copies

On `[A, B, A]`, `remove("A")` removes the first A, leaving `[B, A]`.

To remove all occurrences matching a condition, use an operation designed for that intent, such as `removeIf` on a supporting source, rather than expecting a single value-based `remove` to delete every match.

If you need to remove the specific occurrence currently being visited during traversal, an explicit iterator can target it accurately when the source supports removal. Do not casually substitute value-based `remove` when multiple equal elements exist.

### 4.4. Do Not Use List as a Uniqueness Constraint

Common implementations such as `ArrayList` and `LinkedList` allow duplicate elements. The `List` contract describes this as typical behavior, though a specialized implementation may still impose documented restrictions.

The practical design takeaway is: **do not choose a `List` and assume it automatically prevents duplicates**. If domain logic requires both occurrence order and unique key enforcement, you must define the constraint and validation mechanism explicitly.

## 5. List Ordering Does Not Mean Sorted

The sequence:

```text
[C, A, C, B]
```

has a defined order even though it is not in ascending order.

### 5.1. Positional Order

This is the order currently present in the sequence. When elements are only appended with `add(value)`, each new element goes to the end. When an element is inserted at a specific position, the sequence changes according to that insertion request.

### 5.2. Sorted Order by a Criterion

This is the result of applying a rule such as sorting by name, score, or timestamp. A `List` does not automatically choose such a rule.

If you sort a list with a `Comparator`, subsequent traversal order reflects the newly sorted sequence. If you append an arbitrary element to the end after sorting, the list remains a positionally ordered sequence, even though it may no longer be ordered according to the comparator.

### 5.3. Order Is Not Immutable

You can reverse positions, swap elements, insert, remove, or sort a list if the source supports modification.

"A `List` is ordered" means that every state of the sequence has a well-defined order for manipulation and traversal. It does not mean that the position of a value never changes.

For example, `Collections.reverse` reverses the current sequence without sorting by value. The contract of this operation is described in the [Collections.reverse API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#reverse(java.util.List)).

## 6. Traversal Order Follows the Current Sequence

### 6.1. Forward Traversal with an Iterator or for-each Loop

A `List` iterator returns elements in sequence order. A standard forward `for-each` loop reflects that same order.

For:

```text
[X, M, C, B, X]
```

a forward traversal visits X, M, C, B, and then X. The final occurrence is not skipped just because it equals the first one.

The loop variable in a `for-each` loop holds the current element, not the index. If you also need the position for display purposes, use an index-tracking traversal approach rather than assuming the element itself represents a position identifier.

### 6.2. Index-Based Traversal

Example inside a method:

```java
for (int i = 0; i < values.size(); i++) {
    System.out.println(i + ": " + values.get(i));
}
```

This clearly expresses the position being read.

However, the `List` interface does not guarantee that every `get(index)` call runs in constant time. Repeated index-based traversal can be inefficient on a sequential-access implementation.

`ArrayList` uses a backing structure that supports efficient indexed access, whereas `LinkedList` may have to traverse nodes to reach a position. When you do not need the index and do not know the concrete implementation, an iterator or `for-each` loop usually expresses the traversal intent better. See [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) and [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

### 6.3. Backward Traversal Does Not Mutate the Sequence

`ListIterator` supports `previous` for backward traversal. You can start at the boundary after the last element with:

```java
ListIterator<String> iterator = values.listIterator(values.size());

while (iterator.hasPrevious()) {
    System.out.println(iterator.previous());
}
```

Simply stepping backward through the elements does not reverse the list's structure. This changes the traversal direction, which is different from calling `Collections.reverse` to mutate the sequence. See the [ListIterator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html).

## 7. Complete Program on Position and Order

Save as **ListPositionDemo.java**. Compatible with Java 17 and later:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class ListPositionDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(List.of("C", "A", "C", "B"));

        System.out.println("Initial: " + values);
        System.out.println("Size: " + values.size());
        System.out.println("Index 2: " + values.get(2));
        System.out.println("First/last C: "
                + values.indexOf("C") + "/" + values.lastIndexOf("C"));

        values.add(1, "X");
        System.out.println("After insert: " + values);

        String previous = values.set(2, "M");
        System.out.println("Replaced value: " + previous);
        System.out.println("After set: " + values);

        String removed = values.remove(0);
        values.add("X");
        System.out.println("Removed at index 0: " + removed);
        System.out.println("Current: " + values);

        List<String> forward = new ArrayList<>();
        for (String value : values) {
            forward.add(value);
        }
        System.out.println("Forward traversal: " + forward);

        List<String> backward = new ArrayList<>();
        ListIterator<String> iterator = values.listIterator(values.size());
        while (iterator.hasPrevious()) {
            backward.add(iterator.previous());
        }
        System.out.println("Backward traversal: " + backward);

        List<String> sameSequence = new LinkedList<>(values);
        System.out.println("ArrayList equals LinkedList: "
                + values.equals(sameSequence));

        List<String> reversedCopy = new ArrayList<>(values);
        Collections.reverse(reversedCopy);
        System.out.println("Equals reversed sequence: "
                + values.equals(reversedCopy));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ListPositionDemo.java
java ListPositionDemo
```

Stdout:

```text
Initial: [C, A, C, B]
Size: 4
Index 2: C
First/last C: 0/2
After insert: [C, X, A, C, B]
Replaced value: A
After set: [C, X, M, C, B]
Removed at index 0: C
Current: [X, M, C, B, X]
Forward traversal: [X, M, C, B, X]
Backward traversal: [X, B, C, M, X]
ArrayList equals LinkedList: true
Equals reversed sequence: false
```

### 7.1. Positions and Sequence Changes

Initially, C is at indices 0 and 2. Inserting X at index 1 grows the sequence from four to five elements.

Calling `set` at index 2 replaces A with M and returns A. It does not add a sixth position.

Calling `remove` at index 0 returns C. Appending X afterward results in two occurrences of X—one at the beginning and one at the end.

### 7.2. Two Traversal Directions

Forward traversal collects the exact current sequence.

Backward traversal starts at the `size` boundary and repeatedly calls `previous`, producing `[X, B, C, M, X]`. The source list remains `[X, M, C, B, X]`; traversal direction does not mutate the source.

### 7.3. Lists with Different Implementation Classes Can Still Be Equal

The `ArrayList` and `LinkedList` in the example contain the same sequence of elements, so `equals` returns `true`.

The reversed copy contains the same values and occurrence counts but in a different order, so it is not equal to the original list.

This highlights an important characteristic: `List` equality has **sequence** semantics, not merely "contains the same set of values" semantics.

## 8. Order and Occurrence Count Participate in Equality

Two lists are equal when they have the same size and corresponding elements at the same positions are equal according to the contract.

For example:

```text
[A, B, A] equals [A, B, A]
[A, B, A] does not equal [A, A, B]
[A, B, A] does not equal [A, B]
```

The two lists do not need to belong to the same implementation class. However, order and occurrence count cannot be ignored.

Practical consequences:

- When testing a `List` result, you must decide whether verifying the exact order is required.
- If domain logic does not care about order, do not use `List.equals` and be surprised by a `false` result.
- If you convert a `List` to a `Set` for comparison, duplicate elements may be collapsed; that conversion changes the question being tested.
- If two lists are equal, their `hashCode` values must be consistent under the contract; do not replace list equality with a simple count of unique elements.

The element search methods, `equals`, and `hashCode` of `List` are specified in the [List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

## 9. Complete Program on Duplicates and Source Restrictions

Save as **ListDuplicateDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ListDuplicateDemo {
    record Entry(String code) {}

    private static List<String> codes(List<Entry> entries) {
        return entries.stream().map(Entry::code).toList();
    }

    public static void main(String[] args) {
        Entry first = new Entry("A");
        Entry last = new Entry("A");
        List<Entry> entries =
                new ArrayList<>(List.of(first, new Entry("B"), last));

        System.out.println("Same reference: " + (first == last));
        System.out.println("Equal values: " + first.equals(last));
        System.out.println("Entries: " + codes(entries));
        System.out.println("First/last equal A: "
                + entries.indexOf(new Entry("A")) + "/"
                + entries.lastIndexOf(new Entry("A")));

        boolean removed = entries.remove(new Entry("A"));
        System.out.println("Removed by value: " + removed);
        System.out.println("After removal: " + codes(entries));

        List<String> nulls =
                new ArrayList<>(Arrays.asList("A", null, null));
        System.out.println("Null list size: " + nulls.size());
        System.out.println("First/last null: "
                + nulls.indexOf(null) + "/" + nulls.lastIndexOf(null));

        List<String> readOnly = List.of("A", "A", "B");
        System.out.println("Read-only duplicates: " + readOnly);

        try {
            readOnly.set(0, "C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Read-only set: " + ex.getClass().getSimpleName());
        }

        try {
            List.of("A", null);
        } catch (NullPointerException ex) {
            System.out.println("List.of null: " + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ListDuplicateDemo.java
java ListDuplicateDemo
```

Stdout:

```text
Same reference: false
Equal values: true
Entries: [A, B, A]
First/last equal A: 0/2
Removed by value: true
After removal: [B, A]
Null list size: 3
First/last null: 1/2
Read-only duplicates: [A, A, B]
Read-only set: UnsupportedOperationException
List.of null: NullPointerException
```

### 9.1. Two Objects with the Same Value

`first` and `last` are created with two separate `new` expressions, so `first == last` is `false`.

The record's `equals` method compares the `code` component, so they are equal. The list retains both occurrences, and `indexOf`/`lastIndexOf` find matches at positions 0 and 2.

The `remove` call receives a new value-equal `Entry` and removes the first occurrence. The remaining sequence is B followed by A.

### 9.2. null Is Counted as an Element When Supported by the Source

The `ArrayList` in the example holds two `null` values; its size is 3, and the two `null` indices are 1 and 2.

This does not prove that every `List` accepts `null`. `List.of` rejects `null` immediately upon creation in the example.

### 9.3. Being Ordered and Allowing Duplicates Does Not Require Mutability

`List.of("A", "A", "B")` has a well-defined sequence and retains both A occurrences. However, it does not allow `set`, `add`, or `remove`.

The ability to represent a sequence, the `null` policy, and mutability are separate characteristics that must be verified independently. Do not conclude that "it is declared as a `List`, so it must be modifiable."

## 10. Easily Confused Boundaries

### 10.1. A Positional List Differs from a Set with Predictable Iteration Order

A `LinkedHashSet` can preserve the insertion order of unique elements, but that does not make it a `List`. It does not provide `List.get(index)`, and under set semantics it does not retain multiple equal elements.

If `[A, B, A]` is converted into a set of unique elements, information about the second occurrence of A is lost. Preserving the order of the remaining values cannot restore that information. See the [LinkedHashSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html).

### 10.2. List Is Not Synonymous with ArrayList

`List` is a contract. `ArrayList` is one specific data organization.

Positional reads and sequence order do not require every implementation to use an internal array. Choosing an implementation also depends on access patterns, update patterns, and concurrency requirements; this article focuses on the common semantics of `List`.

### 10.3. The Source Collection's Order Matters When Copying

When constructing a list from another `Collection`, the resulting order depends on the iteration order provided by the source during the copy.

A new `ArrayList` cannot magically recover an "original insertion order" if the source collection no longer preserves that information. If a specific business order is required, you must supply appropriately ordered data or an explicit sorting rule.

## 11. Common Practical Mistakes

| Mistake | Why It Is Wrong | Correct Mindset |
| --- | --- | --- |
| Calling `get(size())` | The last position is `size - 1` | Check for emptiness and validate index bounds |
| Using `add(index, value)` to replace an element | `add` inserts a new position | Use `set` when replacing in place |
| Storing an index as a permanent identifier | Prior insertions/removals shift indices | An index belongs only to the current state |
| Assuming `List` automatically deduplicates | Common implementations keep all occurrences | Choose or enforce a uniqueness constraint separately |
| Assuming `remove(value)` deletes all copies | It removes only the first matching occurrence | Use a filtering operation when removing all matches |
| Assuming ordered means sorted in ascending order | Sequence order differs from a sorting rule | Sort explicitly with a clear requirement and comparator |
| Assuming two lists with the same unique values are equal | `List` compares each position and occurrence count | Compare using the appropriate data model |
| Assuming `get(index)` is always O(1) | Cost depends on the implementation | Choose an appropriate traversal strategy |
| Assuming every `List` allows `null` and mutation | Those guarantees do not come from the interface name | Check the creation source and concrete class |

### Watch Out for the remove Overload with Integers

In a `List<Integer>`:

```java
numbers.remove(1);
```

selects the index-based `remove(int)` overload; it does not mean "remove the `Integer` value equal to 1."

To remove by value, write:

```java
numbers.remove(Integer.valueOf(1));
```

These two calls ask two different questions. When you need to remove the specific occurrence currently being visited during traversal, choose a traversal API that supports element removal directly.

### Watch Out When Removing Elements While Incrementing an Index

When you remove an element inside an index-incrementing loop, subsequent elements shift into the position that was just removed. If you unconditionally increment the index without adjusting the loop logic, an element can be skipped.

This is a direct consequence of the positional model. Using `removeIf` or an iterator that supports removal is usually clearer when the goal is filtering data. Never mutate a list's structure arbitrarily inside a `for-each` loop and rely on a single test run happening not to throw an exception.

## 12. How to Choose a List Based on Data Needs

A `List` is typically appropriate when one or more of the following hold:

- The order of occurrences must be preserved.
- The same value may appear multiple times with distinct meaning.
- Operations by current position are required.
- A result with a well-defined sequence order must be returned to callers.
- Full-sequence equality matches what the application needs to compare.

If you only need unique-value membership checks or stable key-based lookups, evaluate a different collection model rather than forcing every requirement into `List` indices.

Even after choosing the right interface, you must still determine whether the source is modifiable, whether it accepts `null`, and what concurrency requirements apply.

## 13. Self-Check Exercises

1. Given `[A, B, A]`, state `size()`, `indexOf(A)`, and `lastIndexOf(A)`.
2. Insert X at index 1 and then remove index 0. Write out the sequence and all updated indices after each operation.
3. Explain the difference between `add(1, X)` and `set(1, X)` on the same modifiable list.
4. Can an `ArrayList` and a `LinkedList` containing the same sequence be equal? What happens if the order of one list is changed?
5. Why can two objects with different references but equal `equals` results coexist in a list?
6. Modify the first program to traverse backward without calling `Collections.reverse`. Is the source list reversed?
7. With a `List.of` holding two A elements, why is having duplicate elements while disallowing modification not a contradiction?
8. If you need to store a playlist with repeated songs, what information is lost when converting it to a `Set`?

The core mental model to retain is a sequence of occurrences at their current positions. Positional access, insertion, removal, value search, equality, and traversal all build on that model, even though the internal storage mechanism of each implementation class may differ.
