# Indexed get, set, add, and Element Shifting

`List<E>` describes a positional sequence. When working by index, three operations have distinct meanings:

- `get(index)`: reads the element currently at a position.
- `set(index, value)`: replaces the element at an existing position.
- `add(index, value)`: inserts a new element into the sequence.

Insertion is not replacement. Replacement is not adding an element. Properly distinguishing these three meanings helps avoid wrong-size bugs, data loss, or using an index that no longer points to the intended element.

The running examples use a modifiable list:

~~~java
// Code snippet inside a method; requires importing java.util.List and java.util.ArrayList.
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
~~~

## 1. Element Indices and Insertion Positions

Java uses 0-based indexing:

~~~text
Elements: A  B  C
Indices:  0  1  2
size:     3
~~~

When a list has `n` elements:

- Valid element indices range from `0` to `n - 1`.
- Valid insertion positions range from `0` to `n`.

You can visualize the gaps available for insertion:

~~~text
Gaps:    0   1   2   3
         | A | B | C |
~~~

Gap `3` at the end is valid for insertion, but there is no element at index `3` to read or replace.

| Operation | Valid index range when size = n | Return value | Size after success |
| --- | --- | --- | --- |
| `get(index)` | `0 <= index < n` | Element at that position | `n` |
| `set(index, value)` | `0 <= index < n` | Old replaced element | `n` |
| `add(index, value)` | `0 <= index <= n` | `void` | `n + 1` |

The table describes the effect when the operation is supported by the source and completes successfully. Modifiability is a separate requirement, not determined solely by a valid index. The contracts are specified in the [Java SE 17 List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

## 2. get: Reading an Element Without Removing or Shifting the Sequence

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));

String result = values.get(1);

System.out.println(result);        // B
System.out.println(values);        // [A, B, C]
System.out.println(values.size()); // 3
~~~

`get(1)` returns B, while B remains at index `1`. The list is neither consumed like an iterator traversal pass nor stripped of an element like a queue when polling its head.

You can call `get(1)` multiple times to re-read that position, as long as the list and the content at that position have not changed.

### get Does Not Return null to Indicate a Non-Existent Index

~~~java
// values has size 3.
values.get(3);  // IndexOutOfBoundsException
values.get(-1); // IndexOutOfBoundsException
~~~

If the source permits `null` elements, `get` at a valid index may return `null` as data. That is distinct from an invalid index.

Do not check "whether a position exists" by calling `get` and comparing the result with `null`. For normal read operations, the valid range is determined by `size()` and the index.

Java does not use `get(-1)` to retrieve the last element like some other languages. If you need the last element via index-based APIs, the index is `size() - 1` and there must be at least one element.

### The Returned Value May Be a Shared Reference

When elements are objects, `get` returns a reference to the element; it does not automatically perform a deep copy of that object.

If the object allows content updates, mutating the retrieved object can be observed through the list because the list still holds the same reference. Conversely, reassigning a local variable to a new object does not automatically replace the slot in the list.

In the String examples, we use immutable values to focus on positional ordering. Do not infer that every element of every List is also immutable.

## 3. set: Replacing at an Existing Position

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));

String old = values.set(1, "B*");

System.out.println(old);           // B
System.out.println(values);        // [A, B*, C]
System.out.println(values.size()); // 3
~~~

Meaning:

~~~text
Before:
index  0   1   2
       A   B   C

set(1, "B*")

After:
index  0   1   2
       A   B*  C
~~~

A and C keep their indices. No new element is inserted, trailing elements do not shift, and the size remains `3`.

`set` returns the old element. This can be useful if you need to record the value prior to updating or make a decision based on the replaced value.

### set Does Not Automatically Expand the List

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));

// Invalid: index 3 does not yet have an element.
values.set(3, "D");
~~~

There is no rule where "calling set right at the end automatically appends". To create a new position, you must choose an addition operation.

Similarly, you cannot use `set` at index `10` to automatically create empty slots from `3` to `9`. A Java List is not by default a sparse table that auto-fills missing gaps.

### set Does Not Automatically Update Previously Read Variables

~~~java
List<String> values = new ArrayList<>(List.of("A", "B"));
String saved = values.get(0);

values.set(0, "NEW");

System.out.println(saved);         // A
System.out.println(values.get(0));  // NEW
~~~

`saved` is not a live binding to "slot 0". It holds the reference value received at the time of `get`. Replacing the reference stored by the list does not automatically reassign every variable that previously read the old element.

If another variable points to the list itself:

~~~java
List<String> alias = values;
values.set(0, "HEAD");

System.out.println(alias.get(0)); // HEAD
~~~

`alias` sees the change because both variables reference the same List object, not two separate copies.

## 4. Indexed add: Inserting and Shifting the Tail to the Right

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
values.add(1, "X");

System.out.println(values);        // [A, X, B, C]
System.out.println(values.size()); // 4
~~~

`add(1, "X")` places X at index `1`, before the element that was previously at index `1`.

~~~text
Before:
index  0   1   2
       A   B   C

add(1, "X")

After:
index  0   1   2   3
       A   X   B   C
~~~

B moves from `1` to `2`; C moves from `2` to `3`. A stands before the insertion point, so it stays at `0`.

Positional rules for insertion index `p`:

- Existing elements at indices less than `p` keep their indices.
- The new element receives index `p`.
- Existing elements from `p` onward have their indices incremented by one.

The relative order of existing elements does not change. B is still before C; only X is wedged in before B.

### Inserting at the Beginning

~~~java
values.add(0, "HEAD");
~~~

All existing elements have their indices incremented by one. This is why saving an index and continuing to use it after inserting at the beginning can read the wrong element.

### Inserting at the End

~~~java
values.add(values.size(), "TAIL");
~~~

There are no existing trailing elements whose indices need shifting. The new element receives an index equal to the old size.

If the initial size is `3`, the element added at the end is placed at index `3`, and the new size becomes `4`.

### Inserting into an Empty List

~~~java
List<String> values = new ArrayList<>();
values.add(0, "first");

System.out.println(values); // [first]
~~~

With size `0`, the only valid insertion position is `0`. However, there is no valid index for calling `get` or `set` prior to adding.

## 5. Two add Overloads Have Different Return Types

| Call | Meaning | Return type |
| --- | --- | --- |
| `add(element)` | Append to the end | `boolean` |
| `add(index, element)` | Insert at a specified position | `void` |

Example:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B"));

boolean changed = values.add("C");
values.add(1, "X");

System.out.println(changed); // true
System.out.println(values);  // [A, X, B, C]
~~~

Do not assign the result of the two-parameter overload to a variable:

~~~java
// Does not compile: add(index, element) returns void.
// boolean changed = values.add(1, "X");
~~~

In terms of resulting content for a typical list that supports addition, `add(e)` has the same appending effect as `add(size(), e)`. However, they are two distinct signatures with different return types.

### List<Integer>: Position Is Still the First Parameter

~~~java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));

numbers.add(1, 99);
System.out.println(numbers); // [10, 99, 20, 30]
~~~

The number `1` is the insertion index, and `99` is the element boxed into an `Integer`. There is no interpretation of "insert 1 at value 99" just because both arguments are written as numbers.

Similarly:

~~~java
int old = numbers.set(2, 77);

System.out.println(old);     // 20
System.out.println(numbers); // [10, 99, 77, 30]
~~~

The index specifies the position in the sequence, not the value to look up.

## 6. Multiple Insertions and Index Shifting

Starting state:

~~~text
[A, B, C]
~~~

Two insertions at the same index:

~~~java
values.add(1, "X");
values.add(1, "Y");
~~~

Result:

~~~text
[A, Y, X, B, C]
~~~

On the first call, X is placed at index `1`. On the second call, Y is inserted before the element currently at index `1`, which is X. Therefore, Y stands before X.

If you want X followed by Y:

~~~java
values.add(1, "X");
values.add(2, "Y");
~~~

The result from the initial source is:

~~~text
[A, X, Y, B, C]
~~~

You must compute indices based on the list state **after each step**, not against an initial snapshot that is no longer valid.

When you need to insert an entire sequence at a position, an API such as `addAll(index, collection)` can express the intent more clearly. When inserting multiple times, verify both the contents and the order of the added elements, not just the final size.

### Indices Are Not Stable Identifiers

In the complete program:

~~~text
[A, B*, C]        -> B* is at 1
[A, X, B*, C]     -> B* is at 2
[H, A, X, B*, C]  -> B* is at 3
~~~

B* does not change its content, yet its index changes twice.

If an application saves "the user currently selected row 1" and data is subsequently inserted before it, position `1` may no longer be the original entity. When tracking an entity, use an identifier that belongs to the data; when tracking a position, update the position according to the exact modification rules.

`indexOf(value)` can locate a position using the list's value comparison, but it does not automatically become a unique identifier. If duplicate elements exist, it yields only one result according to the List search contract.

## 7. Why Doesn't Capacity Expand the Index Range?

~~~java
ArrayList<String> values = new ArrayList<>(10);

System.out.println(values.size()); // 0

// values.set(0, "A"); // IndexOutOfBoundsException
values.add(0, "A");    // Valid.
~~~

The argument `10` sets the initial capacity of the ArrayList; it does not create ten elements.

Distinguish between:

- **Size:** the number of elements currently belonging to the list.
- **Capacity:** the capacity of the internal storage buffer at a given moment.

The public index range of `get`/`set`/`add` is determined by **size**, not by how many slots the internal array might still be able to hold.

An array `new String[10]` has a length of `10` with slots initially holding `null`. An ArrayList with capacity `10` but size `0` is still an empty list. The two initializations do not mean the same thing.

Do not use repeated `set` calls to fill pre-allocated capacity. If the intent is to add elements, use `add` within the valid insertion position range.

## 8. Logical Shifting and Physical Storage

The List contract defines the resulting indices after an insertion. It does not mandate that every List class must store elements in an array and copy elements using the same algorithm.

### With ArrayList

You can visualize an internal array currently holding:

~~~text
A B C D _
~~~

Inserting X at index `2` must preserve C and D while making room for X:

~~~text
Before: A B C D _
After:  A B X C D
~~~

The tail starting from the insertion point must be shifted within the backing array. If the storage buffer is no longer large enough, there is also the cost of allocating a larger buffer and transferring the data into it.

This is a mental model for understanding performance costs, not an instruction to directly access ArrayList's internal array. The capacity growth rate is an implementation detail; do not rely on a specific growth factor when writing application logic. See the [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### With LinkedList

LinkedList can traverse to the node at the required position and then relink pointers. Subsequent elements still have their logical indices increased by one, even though individual elements do not need to be shifted into different array slots.

Therefore, the statement "insertion shifts subsequent indices" is true at the List abstraction level. The statement "every List must copy the entire tail in memory" is false.

Locating a node by index also incurs a cost. Do not infer from "adding a node is fast once the node position is known" that `add(index, value)` at an arbitrary index is always constant time. See the indexed access characteristics in the [LinkedList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

### Cost Table for Orientation

For standard implementations, where `n` is the number of elements and `p` is the position:

| Operation | ArrayList | LinkedList |
| --- | --- | --- |
| `get`/`set` at arbitrary index | Array slot access, typically O(1) | Requires node traversal, O(n) in the worst case |
| Insert at head | Must shift the tail, O(n) | Can operate directly at the head, O(1) |
| Insert in the middle by index | Cost of shifting the tail, typically O(n - p), plus potential resizing cost | Finding the position can be O(n), followed by node linking |
| Append at tail | Amortized O(1), though a single resize can take O(n) | Can operate directly at the tail, O(1) |

This table is not a blanket recommendation to always pick one class over the other. Data size, access patterns, memory locality, and the overall processing pattern all influence the choice.

If you only need to traverse an entire List without knowing its concrete class, a for-each loop or an iterator avoids forcing the algorithm to depend on random access via `get`. Looping with `get(i)` on a LinkedList can drive the total cost up to O(n²).

## 9. A Valid Index Is Not Enough: Does the Source Allow Modification?

`get` is a read operation. `set` and `add` are mutating operations that may not be supported by the source.

| Source | `get` at valid index | `set` | `add` that increases size |
| --- | --- | --- | --- |
| Modifiable ArrayList | Allowed | Allowed | Allowed |
| Modifiable LinkedList | Allowed | Allowed | Allowed |
| `Arrays.asList(array)` | Allowed | Allowed; changes reflect back to the array | Unsupported |
| `List.of` / `List.copyOf` | Allowed | Unsupported | Unsupported |
| `Collections.unmodifiableList` view | Allowed | Unsupported through the view | Unsupported through the view |

Example of a fixed-size list:

~~~java
String[] array = {"L", "R"};
List<String> fixed = Arrays.asList(array);

fixed.set(0, "L*");

System.out.println(fixed);                  // [L*, R]
System.out.println(Arrays.toString(array)); // [L*, R]

// fixed.add(1, "M"); // UnsupportedOperationException
~~~

It can replace an element, but cannot change its size. Do not label every list returned by `Arrays.asList` as completely unmodifiable. See [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

For an unmodifiable list, if you want to edit a new sequence, you can create a copy:

~~~java
List<String> editable = new ArrayList<>(source);
editable.add(0, "new");
~~~

Creating a copy does not make the original source modifiable; it creates a separate list object. Object elements may still be shared because this is not a deep copy.

### Element Restrictions Are a Separate Requirement

A source may restrict `null`, runtime types, or valid values. Do not assume that "the index is valid and `add` is supported" means every element will be accepted.

With generics, the compiler helps check element types, but checked wrapper classes or specialized sources may also enforce their own runtime rules. Distinguish index-range errors from unsupported-operation errors and rejected-data errors.

## 10. Inserting While Traversing: Avoid Mismanaging Progress

An index-based reading loop:

~~~java
for (int i = 0; i < values.size(); i++) {
    String value = values.get(i);
    System.out.println(value);
}
~~~

When the list is not modified inside the loop, positional meaning is straightforward. However, if you insert before the current element:

~~~java
// Illustrates a logic pitfall, not a recommended processing pattern.
for (int i = 0; i < values.size(); i++) {
    if (needsMarker(values.get(i))) {
        values.add(i, "marker");
    }
}
~~~

`needsMarker` is an illustrative condition supplied by the application.

After inserting at `i`, the element that was just inspected shifts to `i + 1`. The loop increments `i` and may inspect that exact same element again. If the condition remains true, the list can grow endlessly without the algorithm advancing past the original element as intended.

You must clearly design whether newly inserted elements should be visited. Alternative approaches include:

- Using a `ListIterator` to control insertion/replacement relative to the traversal position.
- Building a new result list from an unchanged source.
- Collecting modifications first and applying them in a subsequent phase.
- Explicitly working out the index update rules if indices are an essential part of the algorithm.

Do not directly mutate the structure of a List inside a for-each loop and merely check whether an exception occurs. The absence of an exception does not prove the traversal algorithm is correct, and fail-fast behavior is not a mechanism for controlling insertion.

### View Indices Are Relative to the View

If you operate on a `subList`, index `0` is the start of that view, not necessarily the start of the backing list. Modifications made through the view are reflected in the backing source.

Therefore, when passing an index across layers, you must know which sequence it belongs to and at what point in time. A raw integer does not carry information about the source it describes.

### Check-Then-Act Is Not Automatically Atomic

In a multi-threaded environment, checking `index < size()` and then calling `get`/`set`/`add` in a subsequent step does not automatically guarantee that the source has not changed between the two steps. This is a concurrent access protocol issue that must be addressed separately; the index ranges remain valid in principle, but do not form a lock across a sequence of operations.

## 11. Complete Program

Save as **ListIndexOperationsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ListIndexOperationsDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        show("Initial", values);

        String read = values.get(1);
        System.out.println("get(1) = " + read);
        show("After get", values);

        String replaced = values.set(1, "B*");
        System.out.println("set(1) returned = " + replaced);
        show("After set", values);

        values.add(1, "X");
        show("After add(1, X)", values);
        System.out.println("B* now has index = " + values.indexOf("B*"));

        values.add(0, "H");
        show("After add(0, H)", values);
        System.out.println("B* after another insertion = "
                + values.indexOf("B*"));

        values.add(values.size(), "T");
        show("After add(size, T)", values);
        boolean changed = values.add("U");
        System.out.println("add(U) returned = " + changed);
        show("After append", values);

        String oldFirst = values.get(0);
        List<String> alias = values;
        values.set(0, "HEAD");
        System.out.println("Saved old first = " + oldFirst);
        System.out.println("Alias first = " + alias.get(0));

        expectIndexError("get(size)", () -> values.get(values.size()));
        expectIndexError("set(size)",
                () -> values.set(values.size(), "bad"));
        expectIndexError("add(size + 1)",
                () -> values.add(values.size() + 1, "bad"));
        expectIndexError("get(-1)", () -> values.get(-1));

        ArrayList<String> reserved = new ArrayList<>(10);
        System.out.println("Reserved capacity, size = " + reserved.size());
        expectIndexError("set on empty", () -> reserved.set(0, "first"));
        reserved.add(0, "first");
        show("Empty list after add(0)", reserved);

        List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
        numbers.add(1, 99);
        System.out.println("Integer list after add(1, 99) = " + numbers);
        int oldNumber = numbers.set(2, 77);
        System.out.println("Integer set returned = " + oldNumber);
        System.out.println("Integer list after set(2, 77) = " + numbers);

        String[] array = {"L", "R"};
        List<String> fixed = Arrays.asList(array);
        fixed.set(0, "L*");
        System.out.println("Fixed-size after set = " + fixed);
        System.out.println("Backing array = " + Arrays.toString(array));
        expectUnsupported("Fixed-size indexed add",
                () -> fixed.add(1, "M"));

        List<String> unmodifiable = List.of("A", "B");
        System.out.println("Unmodifiable get(1) = " + unmodifiable.get(1));
        expectUnsupported("Unmodifiable set",
                () -> unmodifiable.set(1, "B*"));
    }

    private static void show(String label, List<?> values) {
        System.out.println(label + " = " + values + "; size=" + values.size());
    }

    private static void expectIndexError(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected IndexOutOfBoundsException");
        } catch (IndexOutOfBoundsException exception) {
            System.out.println(label + " -> "
                    + exception.getClass().getSimpleName());
        }
    }

    private static void expectUnsupported(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException exception) {
            System.out.println(label + " -> "
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 ListIndexOperationsDemo.java
java ListIndexOperationsDemo
~~~

Stdout:

~~~text
Initial = [A, B, C]; size=3
get(1) = B
After get = [A, B, C]; size=3
set(1) returned = B
After set = [A, B*, C]; size=3
After add(1, X) = [A, X, B*, C]; size=4
B* now has index = 2
After add(0, H) = [H, A, X, B*, C]; size=5
B* after another insertion = 3
After add(size, T) = [H, A, X, B*, C, T]; size=6
add(U) returned = true
After append = [H, A, X, B*, C, T, U]; size=7
Saved old first = H
Alias first = HEAD
get(size) -> IndexOutOfBoundsException
set(size) -> IndexOutOfBoundsException
add(size + 1) -> IndexOutOfBoundsException
get(-1) -> IndexOutOfBoundsException
Reserved capacity, size = 0
set on empty -> IndexOutOfBoundsException
Empty list after add(0) = [first]; size=1
Integer list after add(1, 99) = [10, 99, 20, 30]
Integer set returned = 20
Integer list after set(2, 77) = [10, 99, 77, 30]
Fixed-size after set = [L*, R]
Backing array = [L*, R]
Fixed-size indexed add -> UnsupportedOperationException
Unmodifiable get(1) = B
Unmodifiable set -> UnsupportedOperationException
~~~

The exception-catching helper methods in the program serve to verify error cases. If an operation does not throw as expected, the program actively throws an `AssertionError` so the example never silently treats a different outcome as correct.

## 12. Reading the Results Operation by Operation

### Read Then Replace

`get(1)` returns B while the sequence and size remain unchanged. `set(1, B*)` returns the old B and replaces position `1` in place, keeping size `3`.

### Insert in the Middle, Then at the Head

`add(1, X)` shifts B* from `1` to `2`. Adding H at the head shifts B* to `3`. These are two index changes for the same content, not B* having its value replaced.

### Two Ways to Append at the End

`add(size, T)` adds T at the end. `add(U)` also appends at the end, returning `boolean` `true`. The program does not assign the result of the two-parameter overload because it returns `void`.

### Saved Variable and List Alias

The variable `oldFirst` receives H before the first element is replaced with HEAD. It still retains H. The variable `alias` points to the same List, so `alias.get(0)` receives HEAD after the change.

### Out-of-Bounds Index Ranges

`get(size)`, `set(size)`, `add(size + 1)`, and `get(-1)` all fall outside their respective valid ranges. The program checks only the exception class name rather than depending on the full error message text, which may vary across versions.

### Initial Capacity

`new ArrayList(10)` does not create elements yet; its size is still `0`. `set(0)` fails, whereas `add(0)` creates the first element.

### Integer List

`add(1, 99)` inserts `99` before `20`. Next, `set(2, 77)` replaces `20` with `77` and returns `20`. The index and the numeric value serve two separate roles.

### Restricted Sources

`Arrays.asList` allows replacing L with L*, reflecting back to the array, but rejects insertion. `List.of` allows reading B at a valid index, but rejects `set`. Modifiability cannot be inferred solely from the declared type `List<String>`.

## 13. How to Verify an Index-Based Algorithm

For each operation, write down the before and after states:

1. What is the size before the operation?
2. Does the operation require an existing element or an insertion gap?
3. Is the index within the proper range?
4. Does the source support modification?
5. Which element changes value, and which elements change indices?
6. Do indices stored elsewhere still match the intended elements?

Useful small test cases:

- Empty list: `get`/`set` have no valid indices; `add` only has position `0`.
- Single element: `get`/`set` at `0`; `add` at `0` or `1`.
- Multi-element list: operations at the head, middle, and tail.
- Indices `-1`, `size()`, and `size() + 1`.
- Call `set` and verify both the returned old element and that size is unchanged.
- Call `add` and verify the entire tail order, not just the newly added element.
- Two insertions at the same position.
- Duplicate elements to avoid treating a value as a unique identifier.
- Fixed-size or unmodifiable sources.

When an index is computed from a search step or user selection, verify that it still accurately describes the current state before performing an update.

## 14. Common Mistakes

| Misconception or Code Pattern | Problem | Fix |
| --- | --- | --- |
| Using `set` to append an element at the end | The index does not yet have an element | Use `add` for a new position. |
| Using `add` to update a value | Existing data is shifted and size increases | Use `set` if you want replacement. |
| Assuming `get(size)` retrieves the last element | The last index is `size - 1` when non-empty | Distinguish element count from the maximum index. |
| Thinking `add(size, e)` is also out of bounds | The insertion position is allowed to equal `size` | Use the dedicated range for `add`. |
| Using `get(-1)` | Java does not support negative indexing here | Compute the last index and check that the list is non-empty. |
| Setting capacity and calling `set` on a non-existent element | Capacity is not size | Create elements using an addition operation. |
| Inserting multiple times at the same index expecting insertion order to be preserved | Each new insertion is placed before the current position | Increment the position or use a bulk addition operation. |
| Saving an index as a long-lived ID | Insertion, removal, or sorting can change the element at that position | Track a data identifier or update the position. |
| Assuming every List has O(1) indexed access | The List contract does not mandate storage representation | Consider the implementation and access pattern. |
| Assuming any List that supports `get` also supports `set`/`add` | Mutability is optional | Check the source or create a modifiable copy. |
| Switching to an indexed loop just to avoid exceptions | Progress or concurrency bugs can still occur | Verify the contents and processing count, not just the absence of exceptions. |

## 15. Practice

1. Given `[A, B, C, D]`, predict the resulting list and size after `get(2)`, `set(2, X)`, and `add(2, Y)`. Record the return value of each method separately.
2. Starting from an empty list, build `[A, B, C]` using indexed `add`. Indicate the valid positions at each step.
3. Insert X and then Y at the same index `0`. Write down the final order, then adjust the calls to keep X before Y.
4. Save the index of B in `[A, B, C]`, insert two elements before B, and observe what the old index points to afterward.
5. Compare `set` and `add` on `ArrayList`, `Arrays.asList`, and `List.of`. Distinguish out-of-bounds indices from unsupported operations.
6. Write a function that takes a `List` and a user-selected insertion position. Clearly define the valid position range, error policy, and whether the function mutates the source or creates a new sequence.
7. Evaluate the cost of a `get(i)` loop on `ArrayList` versus `LinkedList`, and choose the appropriate traversal method when you only need to process every element.

When reading an index-based call, determine first whether it is **reading**, **replacing an existing position**, or **creating a new position**. Then use the current size to check the valid range and update any assumptions about the elements trailing the insertion point.
