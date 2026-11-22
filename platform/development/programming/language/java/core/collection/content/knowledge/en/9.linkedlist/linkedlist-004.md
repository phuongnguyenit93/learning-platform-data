# Inserting and Removing at an Existing ListIterator Position in LinkedList

## 1. Why Is "Already Having a ListIterator" an Important Condition?

`LinkedList` stores elements using doubly linked nodes. Changing links near a known node is a local operation, whereas locating a node by an index in the middle may require traversing many nodes.

Therefore, two distinct tasks should be separated:

1. Navigating to the position that needs modification.
2. Inserting or removing at the position already reached.

If you are traversing with a `ListIterator`, the iterator already holds information about the position around its cursor. Using `iterator.add(...)` or `iterator.remove()` leverages that position instead of calling `list.add(index, ...)` or `list.remove(index)` to locate the node by index again.

The benefit is not limited to lookup cost. `ListIterator` also defines how to traverse and modify a list simultaneously while keeping the cursor in a valid state.

However, it is important to understand the exact behavior:

- `add` inserts into the gap between two elements, based on the cursor position.
- `remove` does not delete an arbitrary "element at the cursor"; it deletes the element most recently returned by `next` or `previous`.
- Simply holding an iterator does not mean you can call `remove` immediately.

The examples use APIs available in Java 17 with `LinkedList` as the concrete implementation. The `ListIterator` contract applies more broadly, while the cost of local operations is analyzed specifically for `LinkedList`. [ListIterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html), [LinkedList.listIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html#listIterator(int)).

## 2. The Cursor Sits Between Elements

`ListIterator` does not have a single "current element" serving as a common anchor for every method. Its cursor sits between the element that `previous` would return and the element that `next` would return.

For `[A, B, C]`, there are four cursor positions:

```text
| A B C
A | B C
A B | C
A B C |
```

The `|` symbol is for illustration only and is not an element in the list.

The following illustrative snippet inside a method requires importing `java.util.List`, `java.util.LinkedList`, and `java.util.ListIterator`:

```java
List<String> values = new LinkedList<>(List.of("A", "B", "C"));
ListIterator<String> iterator = values.listIterator(1);

// A | B C
// iterator.nextIndex() = 1
// iterator.previousIndex() = 0
```

The index passed to `listIterator(index)` is the position that `next` will read if elements remain:

- `listIterator(0)`: stands before the first element.
- `listIterator(size())`: stands after the last element.
- `listIterator()`: corresponds to the starting position.
- Valid indices satisfy `0 <= index <= size()`.

Allowing a position equal to `size` does not mean there is an element at index `size`. At the end, `hasNext()` is `false` and `next()` throws `NoSuchElementException`.

`nextIndex()` equals `size` when at the end. `previousIndex()` equals `-1` when at the beginning. Methods that query indices or `hasNext`/`hasPrevious` do not move the cursor and do not select an element for `remove`.

## 3. `next` and `previous` Determine Which Element Was Most Recently Returned

From the position:

```text
A | B C
```

Calling `next()`:

```text
Returns: B
Afterward: A B | C
```

Calling `previous()` immediately after:

```text
Returns: B
Afterward: A | B C
```

Two consecutive calls in opposite directions can return the same element. This matches the between-elements cursor model; the iterator is neither skipping a node nor repeating due to a bug.

Two states must be tracked separately:

- **Cursor position**: determines where insertions happen and which element comes next in each direction.
- **Most recently returned element**: determines the target of `remove` or `set` when the state permits.

That is why a call to `add` and a call to `remove` cannot both be understood as "modifying the element at the current position."

## 4. `add` Inserts Before the Element That `next` Would Return

From `A | B C`, calling `iterator.add("X")`:

```text
Before: A | B C
After:  A X | B C
```

Consequences:

- `X` is inserted between `A` and `B`.
- The subsequent `next` still returns `B`.
- The subsequent `previous` returns `X`.
- The size increases by one.
- Both `nextIndex()` and `previousIndex()` increase by one compared to before the insertion.
- `add` does not require a preceding call to `next` or `previous`.

Consequently, you can insert into an empty list or insert right at the beginning or end through a `ListIterator` positioned at the appropriate boundary.

### 4.1. Inserting Multiple Elements Preserves Call Order

From `A | B C`:

```java
iterator.add("X");
iterator.add("Y");
```

Result:

```text
A X Y | B C
```

The cursor moves past the newly inserted element, so the order of `add` calls is preserved. This differs from repeatedly calling `list.add(sameIndex, value)` at a fixed index, which places each new element before the one just inserted.

If there is an independent, stable batch to insert at this position, you can call `add` sequentially for each element. Do not use the list being modified as the concurrent traversal source for the batch without an explicit policy.

### 4.2. `add` Invalidates `remove`/`set` Eligibility on the Previous Return

Suppose `next` returned `B` and then `add` was called. You may no longer call `remove` or `set` targeting the `B` returned prior to `add`. Calling `add` resets the element-selection state.

If you want to remove the newly inserted element `X` from position `A X | B C`, you can call `previous` so that `X` is actually returned, and then call `remove`. Do not call `remove` immediately after `add` expecting it to automatically delete `X`.

By contract, `ListIterator.add(E)` returns `void`; it does not return the new element, the insertion index, or a success flag.

## 5. `remove` Deletes the Element Most Recently Returned by `next`/`previous`

### 5.1. Removing the Next Element Ahead

From `A | B C`:

```java
String removed = iterator.next(); // B
iterator.remove();
```

Result:

```text
A | C
```

Iterator `remove` returns `void`. If you need to keep the removed value, capture it from `next` or `previous` before calling `remove`.

After removing `B`, the next call to `next` returns `C`. There is no need to manually increment an index or call an extra `next` to "compensate" for the deletion; doing so would skip `C`.

### 5.2. Removing the Element Behind the Cursor

From `A B | C`:

```java
String removed = iterator.previous(); // B
iterator.remove();
```

The result is also:

```text
A | C
```

However, the movement path differs: `previous` moved the cursor before `B`, and then `remove` deleted `B`. Regarding `nextIndex`:

- Calling `remove` after `next` decreases `nextIndex` by one compared to right before `remove`.
- Calling `remove` after `previous` does not decrease `nextIndex` again; `previous` had already decremented the index.

The easiest way to verify is to track which element `next` will return, rather than mentally adding or subtracting numbers.

### 5.3. `remove` Targets the Specific Returned Element, Not a Value Lookup

`iterator.remove()` takes neither an index nor an object to search for. It deletes the exact element most recently returned during traversal.

If the list contains duplicate values, the iterator does not scan from the beginning for the first occurrence like `list.remove(Object)`. This is useful when you need to remove the specific occurrence at the position currently being processed.

If `next` returns `null` on a `LinkedList`, an element was still traversed. Calling `remove` afterward is valid as long as no `add` or `remove` intervened; a `null` element value does not mean "no element selected."

## 6. State Rules for `add`, `remove`, and `set`

`set` is included in the table to distinguish replacing an element from inserting or removing. `iterator.set(value)` replaces the element most recently returned by `next` or `previous` without changing the list size.

| State after most recent relevant operation | Can call `add`? | Can call `remove`? | Can call `set`? |
|---|---|---|---|
| Just created iterator, no `next`/`previous` yet | Yes | No | No |
| `next` or `previous` just returned an element | Yes | Yes, once for that selection | Yes |
| Just called `remove`, no new `next`/`previous` yet | Yes | No | No |
| Just called `add`, no new `next`/`previous` yet | Yes | No | No |
| Just called `set` on a valid selection | Yes | Can still `remove` that selection | Can call `set` again |

The table assumes the iterator remains valid and the implementation supports modification. `LinkedList` supports these mutating operations. With a `ListIterator` from an unmodifiable list, you may instead encounter `UnsupportedOperationException`.

State violations—such as calling `remove` before the first traversal step, calling `remove` twice in a row, or calling `set` immediately after `add`—throw `IllegalStateException` on a valid `LinkedList` iterator.

A call to `hasNext()` returning `true` does not grant permission to call `remove`. It only checks whether an element exists ahead. Either `next` or `previous` must actually return an element first.

Modification methods on the iterator have different signatures from direct `List` methods:

| API | Return Type | Target |
|---|---|---|
| `iterator.add(e)` | `void` | Gap at the cursor |
| `iterator.remove()` | `void` | Element most recently returned |
| `iterator.set(e)` | `void` | Element most recently returned |
| `list.remove(index)` | Element | Current index in the list |
| `list.remove(object)` | `boolean` | First occurrence matching the search value |

Do not substitute one method directly for another simply because both are named `remove`. [ListIterator add/remove/set contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html).

## 7. Complete Program: Inserting and Removing in Both Directions

Save as `LinkedListCursorEditDemo.java`. The program uses APIs available in Java 17:

```java
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class LinkedListCursorEditDemo {
    private static void show(
            String label, List<String> values, ListIterator<String> iterator) {
        System.out.println(label + ": " + values
                + "; previousIndex = " + iterator.previousIndex()
                + "; nextIndex = " + iterator.nextIndex());
    }

    public static void main(String[] args) {
        List<String> values =
                new LinkedList<>(List.of("A", "B", "C", "D"));
        ListIterator<String> iterator = values.listIterator(1);
        show("start", values, iterator);

        iterator.add("X");
        iterator.add("Y");
        show("after two adds", values, iterator);

        System.out.println("next = " + iterator.next());
        iterator.remove();
        show("after remove following next", values, iterator);

        System.out.println("next = " + iterator.next());
        System.out.println("previous = " + iterator.previous());
        iterator.remove();
        show("after remove following previous", values, iterator);

        iterator.add("Z");
        System.out.println("next after add = " + iterator.next());
        iterator.set("D*");
        show("after set", values, iterator);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LinkedListCursorEditDemo.java
java LinkedListCursorEditDemo
```

Standard output:

```text
start: [A, B, C, D]; previousIndex = 0; nextIndex = 1
after two adds: [A, X, Y, B, C, D]; previousIndex = 2; nextIndex = 3
next = B
after remove following next: [A, X, Y, C, D]; previousIndex = 2; nextIndex = 3
next = C
previous = C
after remove following previous: [A, X, Y, D]; previousIndex = 2; nextIndex = 3
next after add = D
after set: [A, X, Y, Z, D*]; previousIndex = 4; nextIndex = 5
```

Corresponding cursor trace:

| Step | List and cursor position |
|---|---|
| Initialized at 1 | `A \| B C D` |
| Add X | `A X \| B C D` |
| Add Y | `A X Y \| B C D` |
| `next` returns B | `A X Y B \| C D` |
| Remove B | `A X Y \| C D` |
| `next` returns C | `A X Y C \| D` |
| `previous` returns C | `A X Y \| C D` |
| Remove C | `A X Y \| D` |
| Add Z | `A X Y Z \| D` |
| `next` returns D, then `set` D* | `A X Y Z D* \|` |

In the program, `X` and `Y` are inserted in order before `B`. Calling `next` after the two `add` calls still returns `B`, not `X` or `Y`.

Element `C` is returned by `next` and then by `previous`, so the subsequent `remove` targets `C`. The iterator continues to hold the gap right before `D`. After inserting `Z`, `next` returns `D`; `set` replaces `D` with `D*` without changing the size.

The `show` helper prints the entire list for observation. Printing requires traversing the list, so do not use the runtime of a step-by-step printing example to benchmark the isolated cost of local `add`/`remove` operations.

## 8. Cost When Already Holding an Iterator at the Target Position

In OpenJDK's `LinkedList` implementation, `ListIterator` holds references to the next node and the last returned node. `add` links a new node before the next node (or appends at the tail); `remove` unlinks the last returned node. It does not re-traverse from the ends by index for each edit.

| Operation on `LinkedList` | Typical Complexity Considered |
|---|---|
| Creating `listIterator(index)` at a middle position | `O(n)` in the worst case due to traversing to the position |
| Creating an iterator at the head or tail | `O(1)` |
| Single `next`/`previous` step | `O(1)` |
| `add` at an existing cursor | `O(1)` for node linking |
| Valid `remove` of the last returned element | `O(1)` for node unlinking |
| Valid `set` of the last returned element | `O(1)` |

This analysis reflects standard structural complexity; adding a node also allocates a node object. It is not a real-time fixed-latency guarantee.

If you must first traverse to a distant position and then perform `k` local insertions or removals, the total cost takes the form "cost to reach the position + cost of `k` operations." Do not omit the initial traversal cost and claim that every operation at an arbitrary index is constant-time.

For example, recreating `listIterator(index)` in the middle for every single insertion repeatedly pays the position-lookup cost. Retaining and moving a single iterator appropriately is what leverages the already known position.

Also, do not infer this complexity merely from the `ListIterator` interface name. An `ArrayList`'s `ListIterator` may still need to shift elements when inserting or removing in the middle. Sharing the same operational contract does not force different data structures to have the same cost. [ListItr and node linking in OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedList.java).

## 9. A Single Traversal Pass That Both Filters and Inserts

Pattern for removing during forward traversal:

```java
ListIterator<Integer> iterator = values.listIterator();
while (iterator.hasNext()) {
    Integer value = iterator.next();
    if (value == null || value < 0) {
        iterator.remove();
    }
}
```

This is an illustrative snippet assuming `values` is a declared `LinkedList`. The `null` branch is checked before the numeric comparison to avoid unboxing `null`.

After `remove`, the next `next()` reads the subsequent unprocessed element. You do not need to adjust an index variable to account for shifting positions.

To insert immediately after the element just returned by `next`, call `add` at the current cursor position:

```java
Integer value = iterator.next();
if (Integer.valueOf(2).equals(value)) {
    iterator.add(20);
}
```

This is a standalone illustrative snippet assuming element availability was checked beforehand. From `... 2 | next-element ...`, the result is `... 2 20 | next-element ...`.

If the loop continues calling only `next` in the forward direction, the newly inserted `20` lies behind the cursor and will not be visited by the next `next()` call. That is often the intended behavior when you only want to process the original elements.

If an algorithm needs to process newly inserted data as well, you must deliberately design the cursor movement rules and termination condition. Calling `previous` and re-processing an element under the same insertion rule can easily create an infinite loop.

### 9.1. Inserting Before the Just-Read Element Requires Explicit Cursor Management

After `next` returns `B`, the cursor already stands after `B`. Calling `add` immediately would insert after `B`, not before `B`.

An illustrative pattern for inserting a marker before `B`:

```java
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("B".equals(value)) {
        iterator.previous(); // Move back to the gap before B.
        iterator.add("before-B");
        iterator.next();     // Step over B to continue after B.
    }
}
```

This snippet uses an independent `ListIterator<String>` over an existing list of strings. Given `[A, B, C]`, the result is `[A, before-B, B, C]`.

The final `next()` call at the end of the branch serves a critical purpose: stepping past `B` after inserting the marker. If you omit it, the next iteration will read `B` again and keep inserting before `B` indefinitely. That is an algorithmic cursor bug, even though every individual `add` call is legal.

### 9.2. Removing a Range Starting from the Cursor

If you need to remove up to `limit` elements on the `next` side, you can repeat the pattern "`next` to select, `remove` to delete":

```java
int removedCount = 0;
while (removedCount < limit && iterator.hasNext()) {
    iterator.next();
    iterator.remove();
    removedCount++;
}
```

This illustrative snippet assumes a valid iterator and `limit >= 0`. It removes at most `limit` elements and does not guarantee removing `limit` elements if the end of the list is reached early.

If business requirements demand removing an exact count and forbid partial modification when fewer elements remain, check the condition upfront or design the operation according to that policy before starting. Do not assume the iterator provides automatic rollback.

## 10. Complete Program: A Single Edit Pass and State Exceptions

Save as `LinkedListEditPassDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class LinkedListEditPassDemo {
    private static void expectIllegalState(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": no exception");
        } catch (IllegalStateException ex) {
            System.out.println(label + ": IllegalStateException");
        }
    }

    public static void main(String[] args) {
        List<Integer> values =
                new LinkedList<>(Arrays.asList(-1, null, 0, -2, 2, 3));
        List<Integer> visited = new ArrayList<>();
        ListIterator<Integer> iterator = values.listIterator();

        while (iterator.hasNext()) {
            Integer value = iterator.next();
            visited.add(value);
            if (value == null || value < 0) {
                iterator.remove();
            } else if (value == 0) {
                iterator.set(10);
                iterator.add(11);
            } else if (value == 2) {
                iterator.add(20);
            }
        }

        System.out.println("visited: " + visited);
        System.out.println("edited: " + values);

        List<String> words = new LinkedList<>(List.of("A", "B", "C"));
        ListIterator<String> edit = words.listIterator(1);
        expectIllegalState("remove before traversal", edit::remove);

        System.out.println("selected: " + edit.next());
        edit.remove();
        expectIllegalState("second remove", edit::remove);

        System.out.println("selected: " + edit.next());
        edit.add("X");
        expectIllegalState("remove after add", edit::remove);
        expectIllegalState("set after add", () -> edit.set("bad"));

        System.out.println("previous after add: " + edit.previous());
        edit.remove();
        System.out.println("words: " + words);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LinkedListEditPassDemo.java
java LinkedListEditPassDemo
```

Standard output:

```text
visited: [-1, null, 0, -2, 2, 3]
edited: [10, 11, 2, 20, 3]
remove before traversal: IllegalStateException
selected: B
second remove: IllegalStateException
selected: C
remove after add: IllegalStateException
set after add: IllegalStateException
previous after add: X
words: [A, C]
```

The numeric processing pass performs the following:

- Removes negative numbers and `null` elements immediately after traversing them.
- Replaces `0` with `10` via `set`, then inserts `11` right after it.
- Inserts `20` after the value `2`.
- Continues reading the remaining original unprocessed elements.

The `visited` list shows that the iterator processed all six original elements, including `null`. The newly added values `11` and `20` were not re-read by `next` during this forward pass. The pass neither skipped `-2` after inserting `11` nor skipped any element after a removal.

The string section verifies the state contract:

1. Right after creating the iterator, `remove` is rejected.
2. `next` selects `B`, and `remove` deletes `B`; calling `remove` a second time is rejected.
3. `next` selects `C`, but `add("X")` invalidates the prior selection for `remove`/`set`.
4. `previous` after `add` returns `X`, establishing a new valid selection.
5. `remove` then deletes `X`, leaving `[A, C]`.

If you only need conditional filtering, an API like `removeIf` expresses it more concisely. `ListIterator` shines when you need to coordinate position, traversal direction, replacement, and insertion/removal within a single pass governed by explicit rules.

## 11. Only Modify Structure Through the Iterator Managing the Traversal

An illustrative snippet showing improper usage:

```java
ListIterator<String> iterator = words.listIterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("B".equals(value)) {
        words.remove(value); // Structural modification outside the active iterator.
    }
}
```

Here, even though the element was reached via the iterator, the code calls `remove` directly on the list. Doing so can:

- Search for and delete by value rather than the exact occurrence just traversed.
- Spend extra work searching from the start.
- Invalidate the active iterator against the list's structural state.

On `LinkedList`, iterators employ a modification-detection mechanism and may throw `ConcurrentModificationException`. This detection is fail-fast on a best-effort basis rather than a synchronization mechanism or a guaranteed control-flow strategy; never write code relying on the assumption that "if it didn't throw, it must be safe."

During an active edit pass, use `iterator.remove()` and `iterator.add(...)` so the iterator updates its own internal state to reflect those changes.

If two iterators exist on the same list, modifying the structure through the first iterator does not keep the second iterator valid. Similarly, adding elements through a `Deque` reference pointing to the same `LinkedList` still counts as an external structural modification relative to the current iterator.

`ListIterator` is not a snapshot copy of the data and does not make `LinkedList` thread-safe. If concurrent access occurs, you need a dedicated policy for ownership and synchronization. [LinkedList iterator rules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

## 12. Common Pitfalls and How to Check

| Misconception or Code Pattern | Consequence | Fix According to Intent |
|---|---|---|
| Assuming the cursor always points at a current element | `add`/`remove` positions are misread | Sketch the gap between `previous` and `next` |
| Calling `remove` right after `listIterator(index)` | No element has been returned yet | Call `next` or `previous` to select the desired side, then `remove` |
| Calling `remove` right after `add` to delete the new element | `IllegalStateException` | Call `previous` to return the newly inserted element, then `remove` if that is the target |
| Calling `remove` twice after a single `next` | Second call is in an invalid state | Traverse to select another element before the next `remove` |
| Calling `set` after `add` without re-traversing | Selection prior to `add` can no longer be used for `set` | Re-select using `next` or `previous` |
| Calling `add` after `next` expecting insertion before the just-read element | Element is inserted after the just-read element | Recalculate cursor movement explicitly |
| Calling an extra `next` after `remove` to compensate for index shift | May skip the subsequent element | Let the loop's normal `next` step read the following element |
| Repeatedly creating an iterator by a middle index | Re-traverses to locate the position each time | Reuse the iterator when the local editing pattern allows |
| Calling `list.remove(value)` inside an iterator loop | Searches/removes via a different path and can invalidate the iterator | Mutate through the iterator managing the traversal |
| Concluding that every `ListIterator` has `O(1)` `add`/`remove` | Ignores the underlying data structure | Tie complexity analysis to the concrete `LinkedList` implementation |

## 13. Self-Check from a Cursor Position

Each question starts independently from the list `[A, B, C]` and an iterator created by `listIterator(1)`, i.e., `A | B C`.

1. Call `add("X")` then `add("Y")`. What is the list and what does the next `next()` return?
2. Call `next()` then `remove()`. What is the list and what is `nextIndex()`?
3. Call `previous()` then `remove()`. Which element is removed?
4. Call `add("X")` then `remove()` immediately. Is this valid?
5. Call `add("X")`, `previous()`, `remove()`. What is the result?
6. Call only `hasNext()` and then `remove()`. Does `hasNext()` grant permission to remove?

Answers:

1. `[A, X, Y, B, C]`; the cursor is at `A X Y | B C`, so `next()` returns `B`.
2. `next()` returns `B`; `remove()` deletes `B`; `[A, C]` remains, cursor is at `A | C`, and `nextIndex()` is `1`.
3. `previous()` returns `A`; `remove()` deletes `A`; `[B, C]` remains, cursor is at the beginning.
4. No; `add` resets the selection state, so `remove()` throws `IllegalStateException`.
5. After `add`, the state is `A X | B C`; `previous()` returns `X`; `remove()` deletes `X`. The list returns to `[A, B, C]` with the cursor at `A | B C`.
6. No; `next()` or `previous()` must actually return an element before `remove()` can be called.

When working with an existing `ListIterator`, keep three facts clear: which gap the cursor currently occupies, which element was most recently returned, and whether the current state allows `remove` or `set`. On a `LinkedList`, understanding these three points ensures both that you modify the intended element and that you leverage the known node position for local insertions and removals.
