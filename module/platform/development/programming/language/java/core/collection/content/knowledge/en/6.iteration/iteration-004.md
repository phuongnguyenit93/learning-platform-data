# ListIterator: Bidirectional Traversal, Indices, and the Cursor

`Iterator` retrieves elements one by one in a single direction. With lists, we sometimes need to move forward, step backward, check the next position, or modify elements near the current traversal position. `ListIterator<E>` provides those capabilities.

The key concept to grasp before any method name is:

> **The cursor of a ListIterator sits between two elements, not on a current element.**

This model explains why `next()` followed by `previous()` can return the same element, why an iterator can be created at `list.size()`, and why `remove()` must remember the most recently returned element.

This lesson uses the Java 17 API. Three complete programs were compiled with `--release 17` and run to verify stdout. Other shortened code snippets illustrate operations inside a method rather than standalone runnable files.

After this lesson, you will be able to:

- Draw the cursor position before and after `next` and `previous`.
- Distinguish the iterator starting position from an element index.
- Use `nextIndex` and `previousIndex` properly, including at boundaries.
- Traverse forward, backward, and reverse direction intentionally.
- Track the cursor and the most recently returned element separately during modifications.

## 1. Where Does ListIterator Fit in the Collection Model?

`ListIterator<E>` extends `Iterator<E>`, adding capabilities tailored to a sequence of elements with positional ordering.

| Capability | Iterator | ListIterator |
| --- | --- | --- |
| Check whether an element exists ahead | `hasNext()` | `hasNext()` |
| Retrieve and advance forward | `next()` | `next()` |
| Remove the last returned element, if supported | `remove()` | `remove()` |
| Check whether an element exists behind | No corresponding method | `hasPrevious()` |
| Retrieve and step backward | No corresponding method | `previous()` |
| Query indices on both sides of the cursor | No | `nextIndex()`, `previousIndex()` |
| Replace the last returned element, if supported | No | `set(element)` |
| Insert at the cursor position, if supported | No | `add(element)` |

Ways to obtain one from a `List<E>`:

```java
ListIterator<String> fromBeginning = values.listIterator();
ListIterator<String> fromPosition = values.listIterator(2);
```

This snippet assumes `values` has type `List<String>`, has a size of at least `2`, and `ListIterator` is imported.

Not every `Collection` provides a `ListIterator`. For instance, a `Set` does not have list indices and does not inherently support this contract.

An enhanced `for` loop on a list only requires the `Iterator` mechanism; it does not give the author direct control over the bidirectional capabilities of `ListIterator`.

## 2. The Cursor Model: n Elements Have n + 1 Positions

For the list:

```text
[A, B, C]
```

there are four cursor positions:

```text
| A B C
A | B C
A B | C
A B C |
```

The `|` symbol represents the gap where the cursor currently rests.

Let that position be `p`:

- There are `p` elements before the cursor.
- If an element exists in the next direction, `next()` returns the element at index `p`.
- If an element exists in the previous direction, `previous()` returns the element at index `p - 1`.

When working with a `ListIterator`, prefer thinking in two explicit directions:

- **The next direction:** moving from beginning to end.
- **The previous direction:** moving from end to beginning.

### State Table for a Three-Element List

| Cursor | nextIndex | previousIndex | hasNext | hasPrevious |
| --- | --- | --- | --- | --- |
| `\| A B C` | `0` | `-1` | `true` | `false` |
| `A \| B C` | `1` | `0` | `true` | `true` |
| `A B \| C` | `2` | `1` | `true` | `true` |
| `A B C \|` | `3` | `2` | `false` | `true` |

You can picture it as:

```text
nextIndex()     = p
previousIndex() = p - 1
```

While using a valid iterator, these two indices describe the adjacent positions on either side of the same cursor. They are not two separate cursors.

## 3. Starting at a Position Other Than the Beginning of the List

`listIterator(index)` places the cursor right before the element at that index.

With `[A, B, C]`:

```java
ListIterator<String> cursor = values.listIterator(1);
```

creates the state:

```text
A | B C
```

Immediately after that:

- `next()` will return `B`.
- `previous()` will return `A`.
- `nextIndex()` is `1`.
- `previousIndex()` is `0`.

### Why Is listIterator(size) Valid?

The starting position is allowed to fall within the range:

```text
0 <= index <= list.size()
```

`index == size` means the cursor is at the end of the list, after the last element. There is no element for `next`, but traversal can begin with `previous`.

Conversely, `get(size)` is invalid because `get` requires **an element** at that index, whereas the last element's index is only `size - 1`.

| Call on a list of size n | Valid index range |
| --- | --- |
| `get(index)` | `0..n-1` |
| `listIterator(index)` | `0..n` |

For an empty list, the only valid iterator position is `0`. Initializing with a negative index or an index greater than the size throws `IndexOutOfBoundsException`.

## 4. Next and Previous Both Return an Element and Move the Cursor

Starting at:

```text
A | B C
```

Calling `next()`:

```text
Return value: B
New cursor:   A B | C
```

Then calling `previous()`:

```text
Return value: B
New cursor:   A | B C
```

Both calls return the same `B` because the cursor just crossed over that element and then crossed back over it in the opposite direction.

### Previous Does Not Mean "Get a Different Element Than the Last Next"

A common misconception is thinking that after `next()` returns `B`, `previous()` should return `A`. The cursor model shows why that is wrong: after `next`, `B` sits immediately to the left of the cursor, so `previous` must cross back over `B`.

To reach `A` in this sequence of operations, you must call `previous` one more time.

### State-Querying Methods Do Not Move the Cursor

- `hasNext()`.
- `hasPrevious()`.
- `nextIndex()`.
- `previousIndex()`.

They do not substitute for `next()` or `previous()`. A loop that only checks state without an appropriate forward or backward step will not advance through the elements on its own.

### Reversing Direction Can Cause the Same Element to Be Processed Multiple Times

If you keep alternating `next()` and `previous()` across the same gap, you can retrieve the same element indefinitely.

This is not an iterator bug. Your program needs a clear condition or strategy for changing direction so that it makes actual progress toward solving its problem.

## 5. Complete Program: Walking Forward and Back

Create the file **`ListCursorWalkDemo.java`**:

```java
import java.util.List;
import java.util.ListIterator;

public class ListCursorWalkDemo {
    public static void main(String[] args) {
        List<String> values = List.of("A", "B", "C");
        ListIterator<String> cursor = values.listIterator(1);

        show("initial", cursor);
        System.out.println("next = " + cursor.next());
        show("after next", cursor);
        System.out.println("previous = " + cursor.previous());
        show("after previous", cursor);

        while (cursor.hasNext()) {
            System.out.println("forward = " + cursor.next());
        }
        show("at end", cursor);

        while (cursor.hasPrevious()) {
            System.out.println("backward = " + cursor.previous());
        }
        show("at beginning", cursor);
    }

    private static void show(String label, ListIterator<String> cursor) {
        System.out.println(label
                + ": nextIndex=" + cursor.nextIndex()
                + ", previousIndex=" + cursor.previousIndex()
                + ", hasNext=" + cursor.hasNext()
                + ", hasPrevious=" + cursor.hasPrevious());
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ListCursorWalkDemo.java
java -Dfile.encoding=UTF-8 ListCursorWalkDemo
```

Stdout:

```text
initial: nextIndex=1, previousIndex=0, hasNext=true, hasPrevious=true
next = B
after next: nextIndex=2, previousIndex=1, hasNext=true, hasPrevious=true
previous = B
after previous: nextIndex=1, previousIndex=0, hasNext=true, hasPrevious=true
forward = B
forward = C
at end: nextIndex=3, previousIndex=2, hasNext=false, hasPrevious=true
backward = C
backward = B
backward = A
at beginning: nextIndex=0, previousIndex=-1, hasNext=true, hasPrevious=false
```

### Tracing the Stages

1. The iterator starts at the gap `A | B C`.
2. `next` returns `B` and moves the cursor to the right of `B`.
3. `previous` returns `B` again, returning the cursor to its initial gap.
4. The forward loop from that position retrieves `B`, `C`; it does not automatically rewind to the beginning to retrieve `A`.
5. At the end, `nextIndex` equals `size`, while `hasNext` is `false`.
6. The backward loop retrieves `C`, `B`, `A`.
7. At the beginning, `previousIndex` is `-1` and `hasPrevious` is `false`.

A list created via `List.of` does not allow modification, yet it still supports moving the iterator in this example. Traversal capability and modification capability are two separate parts of the contract that should be distinguished.

## 6. Use Indices to Describe Position, Not to Guess State

### nextIndex Is Not Always a Valid Index for get

At the end of the list:

```text
nextIndex() == list.size()
```

This value reports the next position if one existed, not a valid element index to pass to `get`.

Similarly, `previousIndex() == -1` at the beginning does not mean there is an element at `-1`.

The proper usage is to check whether elements remain in that direction:

```java
if (cursor.hasNext()) {
    int index = cursor.nextIndex();
    String value = cursor.next();
    System.out.println(index + " -> " + value);
}
```

Or in the reverse direction:

```java
if (cursor.hasPrevious()) {
    int index = cursor.previousIndex();
    String value = cursor.previous();
    System.out.println(index + " -> " + value);
}
```

Reading the index **before** the step records the exact position of the element about to be returned.

### The Index After an Operation Already Describes the New Gap

If you call `next()` first and then read `nextIndex()`, that index is the position of the following element, not the element you just received.

For example:

```text
Before next: nextIndex = 1
next returns: B at index 1
After next: nextIndex = 2
```

Avoid vague variable names like "currentIndex" without clarifying which element's index it represents or whether it was read before or after the step.

## 7. The Cursor Is Distinct from the Most Recently Returned Element

To understand modifications, you need to track two separate pieces of state:

1. **The cursor position:** the gap between elements.
2. **The most recently returned element:** the one just supplied by `next()` or `previous()`.

`set` and `remove` act on the most recently returned element, provided the current state permits it. They do not simply mean "edit/delete the element to the right of the cursor."

### Why Does the Direction of Movement Matter?

- After `next()`, the last returned element sits to the left of the cursor.
- After `previous()`, the last returned element sits to the right of the cursor.

Therefore, calling `remove()` adjusts the cursor index differently depending on which retrieval operation preceded it.

If you only remember "the iterator is at index 2" while forgetting the `next`/`previous` history, you do not have enough information to accurately predict which element will be affected by `set` or `remove`.

### Stepping Forward and Back Does Not Necessarily Restore All Modification State

Calling `next()` and then `previous()` may return the **cursor** to the same gap, but the history of the last returned element has been updated.

Consequently, do not treat this sequence as a completely side-effect-free "peek" if subsequent code relies on the state preconditions of `set` or `remove`. The index-querying methods do not cause that kind of history change.

## 8. How Do Set, Add, and Remove Affect the Cursor?

The following operations are optional. Only use them when the underlying list's iterator supports them.

### Set: Replace the Most Recently Returned Element

After a valid `next` or `previous`:

```java
cursor.set("replacement");
```

replaces the value of the element that was just returned.

- Does not increase or decrease the list size.
- Does not move the cursor.
- Does not automatically advance to another element.
- Invalid if no element has been returned by `next`/`previous` in the required state.
- Invalid immediately after `add` or `remove` before calling `next`/`previous` again.

A valid `set` call does not consume the right to replace that same element again. The state rule is not "every operation may only be called once"; each operation has its own preconditions.

### Add: Insert Immediately Before the Cursor

If you currently have:

```text
A B | C
```

calling `add("X")` produces:

```text
A B X | C
```

Consequences:

- The new element sits immediately before the cursor, on the side that `previous` will visit next.
- The subsequent `next()` still returns `C`, just as before the insertion.
- The subsequent `previous()` will return the newly inserted element `X`.
- `nextIndex` increases by one.
- You cannot immediately call `set` or `remove` targeting the previously returned element; an appropriate `next` or `previous` call is required first.

`add` does not make the newly inserted element the "last returned element." Those are two distinct states.

### Remove After Next

For example:

```text
A B | C
```

If this gap was reached right after `next()` returned `B`, then `remove()` deletes `B`:

```text
A | C
```

`nextIndex` decreases by one because an element before the cursor was removed.

### Remove After Previous

If you have:

```text
A B | C D
```

right after `previous()` returned `C`, then `remove()` deletes `C`:

```text
A B | D
```

`nextIndex` keeps the same numeric value in this situation because the removed element sat immediately after the cursor.

### Do Not Call Remove Twice for the Same Retrieval

Once removed, there is no longer a valid last-returned element to remove again. To call `remove` again, you must first call `next` or `previous` to obtain another element.

Likewise, calling `set` after `remove` without a new retrieval in between is invalid.

## 9. Complete Program: Tracking Modifications and Indices

Create the file **`ListCursorEditDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.ListIterator;

public class ListCursorEditDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        ListIterator<String> cursor = values.listIterator(1);

        System.out.println("next = " + cursor.next());
        cursor.set("B*");
        show("after set", values, cursor);

        cursor.add("X");
        show("after add", values, cursor);

        try {
            cursor.set("blocked");
        } catch (IllegalStateException exception) {
            System.out.println("set immediately after add = "
                    + exception.getClass().getSimpleName());
        }

        System.out.println("previous = " + cursor.previous());
        cursor.remove();
        show("after remove(previous)", values, cursor);

        System.out.println("next = " + cursor.next());
        cursor.remove();
        show("after remove(next)", values, cursor);

        try {
            cursor.remove();
        } catch (IllegalStateException exception) {
            System.out.println("remove twice = "
                    + exception.getClass().getSimpleName());
        }
    }

    private static void show(
            String label, List<String> values, ListIterator<String> cursor) {
        System.out.println(label + ": " + values
                + ", nextIndex=" + cursor.nextIndex()
                + ", previousIndex=" + cursor.previousIndex());
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ListCursorEditDemo.java
java -Dfile.encoding=UTF-8 ListCursorEditDemo
```

Stdout:

```text
next = B
after set: [A, B*, C], nextIndex=2, previousIndex=1
after add: [A, B*, X, C], nextIndex=3, previousIndex=2
set immediately after add = IllegalStateException
previous = X
after remove(previous): [A, B*, C], nextIndex=2, previousIndex=1
next = C
after remove(next): [A, B*], nextIndex=2, previousIndex=1
remove twice = IllegalStateException
```

### Step-by-Step Progression in the Cursor Model

| Operation just completed | Data and cursor | nextIndex |
| --- | --- | --- |
| Initialized at 1 | `A \| B C` | `1` |
| `next()` returns B | `A B \| C` | `2` |
| `set("B*")` | `A B* \| C` | `2` |
| `add("X")` | `A B* X \| C` | `3` |
| `previous()` returns X | `A B* \| X C` | `2` |
| `remove()` removes X | `A B* \| C` | `2` |
| `next()` returns C | `A B* C \|` | `3` |
| `remove()` removes C | `A B* \|` | `2` |

The two exceptions in the program are intentional state errors:

- `set` immediately after `add` lacks a newly returned element from `next`/`previous`.
- The second `remove` lacks a new retrieval call.

The concrete list here is an `ArrayList`, which supports the iterator modifications used in the program. Do not generalize that support to every `List`.

## 10. Beginning, End, Empty Lists, and Exceptions

| Situation | Expected Outcome |
| --- | --- |
| `next()` when no element remains in the next direction | `NoSuchElementException` |
| `previous()` when no element remains in the previous direction | `NoSuchElementException` |
| Creating an iterator at a negative index or greater than size | `IndexOutOfBoundsException` |
| `set`/`remove` without valid state | `IllegalStateException`, in an iterator that supports the operation and checks that state |
| Modification operation not supported | `UnsupportedOperationException` |

An operation can violate multiple conditions simultaneously. Do not design programs assuming every implementation class prioritizes the exact same check first in every invalid scenario. Call operations in a valid state on a source known to support them.

### Complete Program

Create the file **`ListCursorBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.ListIterator;
import java.util.NoSuchElementException;

public class ListCursorBoundaryDemo {
    public static void main(String[] args) {
        List<String> empty = new ArrayList<>();
        ListIterator<String> cursor = empty.listIterator(0);

        System.out.println("empty hasNext = " + cursor.hasNext());
        System.out.println("empty hasPrevious = " + cursor.hasPrevious());
        System.out.println("empty nextIndex = " + cursor.nextIndex());
        System.out.println("empty previousIndex = " + cursor.previousIndex());

        try {
            cursor.next();
        } catch (NoSuchElementException exception) {
            System.out.println("empty next = "
                    + exception.getClass().getSimpleName());
        }

        try {
            cursor.previous();
        } catch (NoSuchElementException exception) {
            System.out.println("empty previous = "
                    + exception.getClass().getSimpleName());
        }

        try {
            empty.listIterator(1);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("invalid start position = "
                    + exception.getClass().getSimpleName());
        }

        ListIterator<String> readOnly = List.of("A", "B").listIterator(2);
        System.out.println("read-only previous = " + readOnly.previous());

        try {
            readOnly.set("changed");
        } catch (UnsupportedOperationException exception) {
            System.out.println("read-only set = "
                    + exception.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ListCursorBoundaryDemo.java
java -Dfile.encoding=UTF-8 ListCursorBoundaryDemo
```

Stdout:

```text
empty hasNext = false
empty hasPrevious = false
empty nextIndex = 0
empty previousIndex = -1
empty next = NoSuchElementException
empty previous = NoSuchElementException
invalid start position = IndexOutOfBoundsException
read-only previous = B
read-only set = UnsupportedOperationException
```

### Verified Points

- An empty list has a single cursor gap at `0`.
- No elements remain in either direction.
- `nextIndex` is `0`, and `previousIndex` is `-1`.
- Calling `next` or `previous` when no elements exist fails with the appropriate exception.
- Creating an iterator at position `1` on an empty list is out of bounds.
- An iterator from `List.of("A", "B")` can traverse backward from the end and receive `B`.
- Even though an element was just returned, `set` is still unsupported because this list is unmodifiable.

Having no elements in an empty list is different from a list containing a `null` element. A `null` value is not used as an end-of-traversal sentinel by `next` or `previous`.

## 11. Modification Support Depends on the Source and the Iterator

| Common Source | Bidirectional Traversal | set via iterator | add/remove via iterator |
| --- | --- | --- | --- |
| Standard `ArrayList` | Yes | Yes | Yes |
| Standard `LinkedList` | Yes | Yes | Yes |
| List from `Arrays.asList` | Yes | Yes | No, due to fixed size |
| List from `List.of` | Yes | No | No |
| Snapshot iterator of `CopyOnWriteArrayList` | Yes | No | No |

This table highlights that even when a list itself is mutable, its iterator may still not support modifications.

With `Arrays.asList`, replacing an element via `set` affects the data shared with the backing array. The ability to replace an element does not mean the list can grow or shrink.

With a snapshot iterator, the traversed data is a view with its own contract captured when the iterator was created. Do not assume that the indices it reports always describe a live list being modified elsewhere.

When writing a method that accepts a `List`, document clearly whether it requires read-only traversal, element replacement, or element insertion/removal. The `List` type alone is not enough to guarantee that every mutating operation will succeed.

## 12. Do Not Structurally Modify the List Externally and Expect the Cursor to Fix Itself

With iterators of classes like `ArrayList`, adding or removing elements directly through the list after creating the iterator can cause the iterator to detect an invalid state.

An example of an anti-pattern to avoid:

```java
ListIterator<String> cursor = values.listIterator();
values.add("new");
cursor.next();
```

If you are traversing with an iterator that uses modification detection, perform any supported structural changes through **that iterator itself** during the traversal.

Key points to remember:

- You can encounter `ConcurrentModificationException` even within a single thread.
- Modification detection is a bug-finding aid (fail-fast), not a synchronization lock or a thread-safety guarantee.
- Do not rely on every invalid modification being guaranteed to throw at the exact same method call.
- Two iterators over the same list do not coordinate modifications with each other by default. One iterator modifying the structure can invalidate the other.
- Snapshot or specialized iterators have different contracts; always check the exact nature of the underlying source.

### Iterator Indices Are Not Stable Element Identifiers

When elements are inserted or removed, element indices can shift. Do not save a `nextIndex` value and treat it as the long-lived identity of an object.

If you need to identify a task, user, or record across multiple modifications, use an appropriate domain identifier. An index describes a position within a single list state; it does not replace a business identifier.

## 13. Efficiency and Appropriate Usage

### With ArrayList

- Stepping with `next`/`previous` and replacing an element (`set`) have direct positional cost in the backing array structure.
- Inserting or removing in the middle typically requires shifting elements.
- Using `ListIterator` does not turn a mid-list insertion into a zero-data-movement operation.

### With LinkedList

- Initializing an iterator at a specific index requires traversing to the corresponding node.
- Once at that position, stepping forward or backward along node links does not require re-indexing from the start for each step.
- Inserting or removing through the iterator at a known position can relink nodes without searching from the beginning by index again.

These characteristics belong to the concrete implementation classes; the `ListIterator` interface itself does not promise the same time complexity across all lists.

### Avoid Recreating the Iterator for Every Element

If you want to traverse a segment of a linked list, obtain a single iterator at the starting point and step forward or backward. Repeatedly calling `listIterator(index)` can re-incur the positional lookup cost every time.

### When Should You Use It?

| Need | Suitable Choice |
| --- | --- |
| Read-only sequential traversal of the entire list | An enhanced `for` loop or standard `Iterator` is usually sufficient |
| Need to move forward and backward within the same traversal pass | `ListIterator` |
| Need to start near the middle and traverse bidirectionally | `listIterator(startPosition)` |
| Need to replace or insert elements near the current traversal position | `ListIterator`, when supported by the source |
| Need independent random access to arbitrary positions | Use `get` if appropriate for the data structure |
| Need reverse traversal for reading only | Obtaining an iterator at `size` and stepping with `previous` is a clean approach |

Choose `ListIterator` when cursor state genuinely helps solve the problem. There is no need to add complexity to a simple read-only loop if you do not need its extra capabilities.

## 14. Common Mistakes

### Thinking the Cursor Points Directly at the Last Retrieved Element

The cursor sits between elements; the "last returned element" is a separate piece of state. Draw the `|` marker after each step to avoid faulty assumptions.

### Thinking Next Followed by Previous Must Return Two Different Elements

Two consecutive steps in opposite directions cross the very same element twice. To move to a different element, you must structure your sequence of calls intentionally.

### Calling Previous on a Newly Created Iterator at the Beginning

At position `0`, there is no element on the `previous` side. To traverse the entire list backward, create the iterator at `list.size()`.

### Passing a nextIndex Equal to Size into get

`size` is a valid cursor position at the end of the list, not a valid element index. Always rely on `hasNext` or `hasPrevious` before retrieving an element.

### Calling Add Followed by Remove Expecting to Delete the Newly Inserted Element

`add` does not return an element via `next`/`previous` and clears the state required for `set`/`remove` from any prior retrieval. If you need to act on the newly inserted element, you must first step across it in the appropriate direction.

### Thinking Set Always Replaces the Element on the Next Side

`set` replaces whichever element was most recently returned by `next` or `previous` in a valid state. That element can sit on either side of the cursor depending on the direction of the last step.

### Confusing Bidirectional Traversal with Not Needing a Termination Condition

Loops that step forward and backward can oscillate around the same position forever. Always define a clear direction, scope, and termination condition.

### Assuming the Iterator Automatically Syncs with Every Direct Change to the List

There is no such guarantee. Keep all operations within the contract of the iterator and its backing source, especially when multiple traversals or mutators are involved.

## 15. Practice

### Exercise 1: Fill in the Cursor Table

Given `[10, 20, 30, 40]`, create an iterator at position `2`, then execute:

```text
previous()
next()
next()
previous()
```

For each step, record:

- The return value.
- The position of the `|` marker.
- `nextIndex`.
- `previousIndex`.

The returned values in order should be `20`, `20`, `30`, `30`. Explain why in terms of cursor movement.

### Exercise 2: Reverse Traversal from the End

Create a list of three strings, obtain an iterator at `size`, and print the elements in reverse using `hasPrevious`/`previous`.

Also test with an empty list. Explain why you do not subtract `1` when passing the starting position for an iterator at the end of a list.

### Exercise 3: Predict Modifications via the Iterator

Given a mutable list `[A, B, C]` and an initial cursor at position `1`:

```text
add(X)
previous()
set(Y)
next()
```

Predict the list contents and cursor position after each step.

After this sequence, the list should be `[A, Y, B, C]`; the final `next` operation returns `Y` again, not `B`. Explain why based on the cursor gap after `previous`.

### Exercise 4: Distinguish State Errors from Unsupported Operations

Test the following cases on appropriate sources:

1. Calling `remove` on an `ArrayList` iterator before any `next`/`previous` call.
2. Calling `next`, then `remove`, and then `remove` again.
3. Calling `set` on a `List.of` iterator after retrieving an element.
4. Calling `previous` on an empty list.
5. Initializing an iterator at a position greater than `size`.

Record the exception type and reason for each case, distinguishing among missing valid state, no remaining elements, out-of-bounds starting position, and operations unsupported by the backing source.

The completion criterion is being able to track both the cursor position and the last-returned-element history, accurately predict which element is retrieved in each direction, and avoid using indices or mutating operations outside their contract.
