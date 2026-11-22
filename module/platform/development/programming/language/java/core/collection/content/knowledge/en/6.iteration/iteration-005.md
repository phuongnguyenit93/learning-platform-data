# ListIterator.add, set, and remove

`ListIterator<E>` allows traversing a `List` in both directions and modifying the list at the current traversal position. Its three mutation operations have different targets:

- `add(e)`: inserts a new element into the gap at the cursor.
- `set(e)`: replaces the element that `next()` or `previous()` last returned.
- `remove()`: removes the occurrence that `next()` or `previous()` last returned.

To use them properly, track the **cursor position** and the **last returned element** as two separate pieces of information. Looking only at the cursor position and guessing whether `set/remove` acts on the left or right leads to bugs when changing traversal direction.

The examples use Java 17 or later and a modifiable list, except for the dedicated section illustrating unsupported operations.

## 1. The cursor sits between elements

For a list A, B, C, there are four cursor positions:

~~~text
| A B C
A | B C
A B | C
A B C |
~~~

The `|` symbol is an illustrative cursor, not an element in the list.

From the position:

~~~text
A | B C
~~~

- `next()` returns B and moves the cursor to the right.
- `previous()` returns A and moves the cursor to the left.

For a list of length `n`, there are `n + 1` such gaps. There is no single "current element" that every operation acts on.

Creating iterators:

~~~java
// Code snippet inside a method; requires the corresponding java.util imports.
List<String> values = new ArrayList<>(List.of("A", "B", "C"));

ListIterator<String> start = values.listIterator();  // | A B C
ListIterator<String> middle = values.listIterator(1); // A | B C
ListIterator<String> end = values.listIterator(values.size()); // A B C |
~~~

The index passed to `listIterator(index)` is the position that the element returned by `next()` would have, if an element remains. Because the end-of-sequence cursor is valid, `index == size()` is allowed; this is not a valid element index for `get(index)`. See the contract in [List.listIterator in Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#listIterator(int)).

The iterators above have their own state but reference the same list. They are not copies of the data; do not use them concurrently to structurally modify the backing list and expect the other iterators to automatically update their state.

## 2. Cursor indices and the last returned element

Two useful observation methods:

| Method | Meaning |
| --- | --- |
| `nextIndex()` | The index of the element that `next()` would return; equals `size()` at the end. |
| `previousIndex()` | The index of the element that `previous()` would return; equals `-1` at the beginning. |

Example:

~~~text
List: A | B C
nextIndex()     = 1
previousIndex() = 0
~~~

These indices describe the gap at the cursor. They do not directly tell which element is the target of `set/remove`.

Two navigation sequences can reach the same gap while having different modification targets:

~~~text
Way 1:
| A B C
next() returns A
A | B C
Last returned element: A

Way 2:
A B | C
previous() returns B
A | B C
Last returned element: B
~~~

With the same cursor `A | B C`, `set/remove` in way 1 targets A, whereas in way 2 it targets B.

This is the core point of this article. The official description in the [ListIterator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html) also distinguishes the cursor from the last returned element.

## 3. add: inserts at the cursor without requiring a prior element traversal

Starting state:

~~~text
P | Q
~~~

Calling `add("X")`:

~~~text
P X | Q
~~~

The new element is placed:

- After the element that `previous()` would have returned before the insertion.
- Before the element that `next()` would have returned before the insertion.
- To the left of the cursor after the insertion.

Therefore, after `add("X")`:

- `next()` still retrieves Q if no other operation intervenes.
- `previous()` retrieves X if no other operation intervenes.
- The list size increases by one.
- Both `nextIndex()` and `previousIndex()` increase by one compared to before the insertion.

Example:

~~~java
List<String> values = new ArrayList<>(List.of("P", "Q"));
ListIterator<String> iterator = values.listIterator(1);

iterator.add("X");

System.out.println(values);               // [P, X, Q]
System.out.println(iterator.nextIndex());  // 2
System.out.println(iterator.previous());   // X
~~~

The final `previous()` line in the example moved the cursor to the left. When reasoning about the next step, use the new position rather than continuing to treat it as standing after X.

### Consecutive add calls preserve insertion order in the forward direction

~~~java
List<String> values = new ArrayList<>(List.of("P", "Q"));
ListIterator<String> iterator = values.listIterator(1);

iterator.add("X");
iterator.add("Y");

System.out.println(values);         // [P, X, Y, Q]
System.out.println(iterator.next()); // Q
~~~

Progression:

~~~text
P | Q
P X | Q
P X Y | Q
~~~

The second `add` inserts at the cursor that has already moved past X. The result is not P, Y, X, Q.

There is no need to call `next/previous` between two `add` calls. You can add immediately upon creating the iterator—at the beginning, in the middle, at the end, or in an empty list—as long as the operation is supported by the list and the element is valid.

### add does not make the new element a valid target for set/remove

Immediately after a successful `add`, you cannot call `set` or `remove` relying on an element returned earlier.

~~~java
iterator.add("X");

// iterator.set("Y"); // Invalid state without calling next/previous again.
// iterator.remove(); // Likewise.
~~~

If you want to modify or remove the newly inserted X, you can explicitly retrieve it with `previous()` and then perform the valid operation. Keep in mind, however, that this navigation operation also changes the cursor position.

## 4. set: replaces the exact element most recently returned by next/previous

Forward traversal example:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
ListIterator<String> iterator = values.listIterator();

String first = iterator.next(); // A
iterator.set("A*");

System.out.println(first);                // A
System.out.println(values);               // [A*, B, C]
System.out.println(iterator.nextIndex());  // 1
~~~

`set` replaces the element in the list. The variable `first` still holds the reference or value obtained from the earlier call; it is not automatically reassigned by the iterator operation.

`set`:

- Does not add elements.
- Does not remove elements.
- Does not change the size.
- Does not move the cursor.
- Requires a prior qualifying successful `next` or `previous` call.

Do not call `set` immediately after creating an iterator, because no element has been returned to replace yet.

### set after backward traversal

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
ListIterator<String> iterator = values.listIterator(2); // A B | C

System.out.println(iterator.previous()); // B
iterator.set("B*");

System.out.println(values);              // [A, B*, C]
System.out.println(iterator.nextIndex()); // 1
~~~

B is the target because `previous()` just returned B. The cursor after `previous` is A | B C; `set` does not move it.

Looking at the cursor position and always replacing the element to the left would be wrong in this case. The element just returned by `previous` lies to the right of the cursor.

### set can be called multiple times

~~~java
ListIterator<String> iterator = values.listIterator();

iterator.next();
iterator.set("first replacement");
iterator.set("second replacement");
~~~

If the replacement elements are valid and the iterator supports it, the second `set` call remains valid. `set` does not clear the eligibility to act on the occurrence identified by `next/previous`.

After one or more `set` calls, `remove` can still remove that occurrence, provided no intervening `add/remove` has invalidated the condition.

### Replacing an element differs from mutating the object inside

Suppose the element is a mutable object:

- `iterator.set(otherObject)` replaces the reference held by the list at that occurrence.
- Calling an update method on the retrieved object mutates the object's contents without calling `ListIterator.set`.

A list that disallows replacing elements may still contain mutable objects inside. These two levels of mutability must be considered separately.

## 5. remove: removes the occurrence just returned

Example after `next()`:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
ListIterator<String> iterator = values.listIterator();

System.out.println(iterator.next()); // A
iterator.remove();

System.out.println(values);              // [B, C]
System.out.println(iterator.nextIndex()); // 0
System.out.println(iterator.next());      // B
~~~

A is returned and then removed. The cursor is adjusted so that B remains the next element; the code does not need to manually decrement an external index variable to avoid skipping B.

Progression:

~~~text
| A B C
next() returns A -> A | B C
remove()         -> | B C
~~~

### After previous: the target lies to the right of the cursor

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
ListIterator<String> iterator = values.listIterator(2); // A B | C

System.out.println(iterator.previous()); // B
iterator.remove();

System.out.println(values);              // [A, C]
System.out.println(iterator.nextIndex()); // 1
System.out.println(iterator.next());      // C
~~~

Progression:

~~~text
A B | C
previous() returns B -> A | B C
remove()             -> A | C
~~~

After `previous`, the cursor has already moved backward. Removing B does not move the cursor back another step; C becomes the next element at the current gap.

### remove does not search by equals

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "A"));
ListIterator<String> iterator = values.listIterator(values.size());

iterator.previous(); // Returns the last occurrence of A in the list.
iterator.remove();

System.out.println(values); // [A, B]
~~~

The iterator removes **the occurrence that was returned**; it does not perform a fresh search from the beginning by value A.

If you used `values.remove("A")`, the meaning would be to remove an element matching the value according to the list's contract; for this list, that is the first A. Beyond removing the wrong occurrence, structurally modifying the list directly can also invalidate the active iterator.

`ListIterator.remove()` takes no parameters and returns `void`. Do not confuse it with `List.remove(index)` or `List.remove(Object)`.

### Only one remove per navigation step

~~~java
iterator.next();
iterator.remove();

// iterator.remove(); // IllegalStateException without calling next/previous again.
~~~

Once the target is removed, there is no longer a valid target from that navigation step. To remove another element, you must validly retrieve a next or previous element first.

## 6. State table for the three operations

The table assumes the iterator supports the corresponding operation, the supplied element is valid, and the mentioned steps completed successfully.

| Most recent state | add | set | remove |
| --- | --- | --- | --- |
| Newly created, before any next/previous | Allowed | No valid target | No valid target |
| Just called next or previous | Allowed | Allowed on the just-returned element | Allowed on the just-returned element |
| Just called set, with no add/remove since navigation | Allowed | Allowed again on the same occurrence | Allowed on the same occurrence |
| Just called add, without calling next/previous again | Allowed again | Invalid | Invalid |
| Just called remove, without calling next/previous again | Allowed | Invalid | Invalid |

Short rules for tracking state:

1. A successful `next/previous` selects a target for `set/remove`.
2. `set` replaces the target without invalidating further actions on that occurrence.
3. A successful `add` or `remove` clears the previous modification target.
4. `hasNext`, `hasPrevious`, `nextIndex`, and `previousIndex` only observe; they do not select a new target.

Do not use throwing exceptions from an operation as normal state-control flow. In particular, with custom implementations or unsupported operations, do not generalize the entire post-error state from a single run on `ArrayList`.

### Alternating navigation can return the same element again

~~~java
List<String> values = new ArrayList<>(List.of("A", "B"));
ListIterator<String> iterator = values.listIterator();

System.out.println(iterator.next());     // A
System.out.println(iterator.previous()); // A
iterator.set("A*");

System.out.println(values); // [A*, B]
~~~

`previous` steps backward across the very element that `next` just passed. These are not two different elements. The most recent successful navigation operation is `previous`, so the cursor state and target must be read according to that step.

## 7. add, set, and remove are all optional operations

Having a method on the interface does not mean every backing source permits it.

| Common source | set via list iterator | add/remove via list iterator |
| --- | --- | --- |
| Modifiable `ArrayList` | Supported | Supported |
| Modifiable `LinkedList` | Supported | Supported |
| List from `Arrays.asList(array)` | Supports replacing elements; writes through to the array | Does not support resizing |
| List from `List.of(...)` or `List.copyOf(...)` | Not supported | Not supported |
| View from `Collections.unmodifiableList(...)` | Not supported through the view | Not supported through the view |

A fixed-size list does not mean elements cannot be replaced at all. `Arrays.asList` is an important example.

The complete program below verifies that:

- `set` can replace an element of an array-backed list.
- The backing array also sees the new value.
- `add/remove` on that source throws `UnsupportedOperationException`.
- `set` on an iterator from `List.of` is also unsupported.

If you do not need to keep the restricted backing source, you can create a modifiable copy:

~~~java
List<String> editable = new ArrayList<>(source);
ListIterator<String> iterator = editable.listIterator();
~~~

This copy holds the element references from the source; it does not perform a deep copy of each object's contents.

## 8. Distinguishing state errors, capability errors, and data errors

| Situation | Error category to distinguish |
| --- | --- |
| set/remove when there is no valid returned element | `IllegalStateException` on an iterator that supports the operation and checks the corresponding state. |
| Mutation operation not supported by the implementation | `UnsupportedOperationException`. |
| No remaining element in the next/previous direction | `NoSuchElementException`. |
| Starting index for listIterator is outside the allowed range | `IndexOutOfBoundsException`. |
| Added/replaced value violates type or content restrictions of the source | May throw a corresponding exception such as `ClassCastException` or `IllegalArgumentException`, depending on the contract. |
| Source forbids null but null is passed | Follows the source's policy and exception; do not assume null is always permitted. |

Do not write tests demanding a specific exception according to a guessed precedence order when multiple conditions are violated simultaneously—for example, when an iterator both lacks support for the operation and has no valid target.

In the demonstration program, state errors use a modifiable `ArrayList`, while unsupported-operation errors are tested separately on restricted sources. That separation makes it clear exactly what is being demonstrated.

## 9. Application: traversing, removing, replacing, and inserting in a single pass

Suppose we need to process a list of strings:

- Remove empty strings.
- Convert the remaining strings to uppercase using a locale-neutral rule for the example.
- Insert the marker `"|"` after each remaining string.

The marker in this example is actual data, distinct from the cursor symbol used in the diagrams.

~~~java
// Requires import java.util.Locale along with the list imports.
List<String> tokens = new ArrayList<>(List.of("a", "", "b"));
ListIterator<String> editor = tokens.listIterator();

while (editor.hasNext()) {
    String token = editor.next();
    if (token.isEmpty()) {
        editor.remove();
    } else {
        editor.set(token.toUpperCase(Locale.ROOT));
        editor.add("|");
    }
}

System.out.println(tokens); // [A, |, B, |]
~~~

Why doesn't this loop infinitely over the newly inserted markers?

After `next()` retrieves an original string, the cursor stands after it. `add("|")` inserts the marker before the cursor and leaves the cursor after the marker. The subsequent `next()` retrieves the next original element ahead rather than revisiting the marker just inserted.

In the empty-string branch, `remove()` removes the exact element just retrieved and adjusts the iterator so the next element is not skipped.

In the other branch, `set` must be called before `add`. If reversed to `add` then `set`, the `add` call would clear the previous modification target, making `set` invalid until another navigation step occurs.

The example assumes tokens are non-`null`. If the data domain permits `null`, define an appropriate handling branch before calling `isEmpty`.

## 10. Complete program

Save as **ListIteratorMutationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;

public class ListIteratorMutationDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        ListIterator<String> iterator = values.listIterator();
        show("Start", values, iterator);

        expectIllegalState("set before navigation",
                () -> iterator.set("bad"));
        expectIllegalState("remove before navigation", iterator::remove);

        System.out.println("next -> " + iterator.next());
        iterator.set("A1");
        iterator.set("A2");
        show("After repeated set", values, iterator);

        iterator.remove();
        show("After remove following next", values, iterator);
        expectIllegalState("remove twice", iterator::remove);

        iterator.add("X");
        show("After add X", values, iterator);
        expectIllegalState("set immediately after add",
                () -> iterator.set("bad"));
        expectIllegalState("remove immediately after add", iterator::remove);

        System.out.println("previous -> " + iterator.previous());
        iterator.set("Y");
        show("After set following previous", values, iterator);

        iterator.remove();
        show("After remove following previous", values, iterator);
        System.out.println("next after removing Y -> " + iterator.next());

        List<String> insertions = new ArrayList<>(List.of("P", "Q"));
        ListIterator<String> insertion = insertions.listIterator(1);
        insertion.add("X");
        insertion.add("Y");
        show("Two adds at the same gap", insertions, insertion);
        System.out.println("next after adds -> " + insertion.next());
        System.out.println("previous after next -> " + insertion.previous());
        System.out.println("previous again -> " + insertion.previous());
        insertion.remove();
        show("After removing returned Y", insertions, insertion);

        List<String> duplicates =
                new ArrayList<>(List.of("A", "B", "A"));
        ListIterator<String> last = duplicates.listIterator(duplicates.size());
        last.previous();
        last.remove();
        System.out.println("Remove last returned occurrence = " + duplicates);

        String[] array = {"A", "B"};
        List<String> fixed = Arrays.asList(array);
        ListIterator<String> fixedSet = fixed.listIterator();
        fixedSet.next();
        fixedSet.set("A*");
        System.out.println("Fixed-size set = " + fixed);
        System.out.println("Backing array = " + Arrays.toString(array));

        expectUnsupported("fixed-size add",
                () -> fixed.listIterator().add("X"));

        ListIterator<String> fixedRemove = fixed.listIterator();
        fixedRemove.next();
        expectUnsupported("fixed-size remove", fixedRemove::remove);

        ListIterator<String> readOnly = List.of("A").listIterator();
        readOnly.next();
        expectUnsupported("unmodifiable set", () -> readOnly.set("X"));

        List<String> tokens = new ArrayList<>(List.of("a", "", "b"));
        ListIterator<String> editor = tokens.listIterator();
        while (editor.hasNext()) {
            String token = editor.next();
            if (token.isEmpty()) {
                editor.remove();
            } else {
                editor.set(token.toUpperCase(Locale.ROOT));
                editor.add("|");
            }
        }
        System.out.println("Edited tokens = " + tokens);
    }

    private static void show(
            String label,
            List<String> values,
            ListIterator<String> iterator
    ) {
        System.out.println(label + " = " + values
                + "; nextIndex=" + iterator.nextIndex()
                + "; previousIndex=" + iterator.previousIndex());
    }

    private static void expectIllegalState(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected IllegalStateException");
        } catch (IllegalStateException exception) {
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
javac --release 17 -encoding UTF-8 ListIteratorMutationDemo.java
java ListIteratorMutationDemo
~~~

Stdout:

~~~text
Start = [A, B, C]; nextIndex=0; previousIndex=-1
set before navigation -> IllegalStateException
remove before navigation -> IllegalStateException
next -> A
After repeated set = [A2, B, C]; nextIndex=1; previousIndex=0
After remove following next = [B, C]; nextIndex=0; previousIndex=-1
remove twice -> IllegalStateException
After add X = [X, B, C]; nextIndex=1; previousIndex=0
set immediately after add -> IllegalStateException
remove immediately after add -> IllegalStateException
previous -> X
After set following previous = [Y, B, C]; nextIndex=0; previousIndex=-1
After remove following previous = [B, C]; nextIndex=0; previousIndex=-1
next after removing Y -> B
Two adds at the same gap = [P, X, Y, Q]; nextIndex=3; previousIndex=2
next after adds -> Q
previous after next -> Q
previous again -> Y
After removing returned Y = [P, X, Q]; nextIndex=2; previousIndex=1
Remove last returned occurrence = [A, B]
Fixed-size set = [A*, B]
Backing array = [A*, B]
fixed-size add -> UnsupportedOperationException
fixed-size remove -> UnsupportedOperationException
unmodifiable set -> UnsupportedOperationException
Edited tokens = [A, |, B, |]
~~~

The two helper methods `expectIllegalState` and `expectUnsupported` in the program serve only for demonstration: if an operation fails to throw the expected exception, the program throws an `AssertionError` so it does not silently report a false result. Do not copy this exception-catching pattern into normal business logic flows.

## 11. Reading the states in the program

### Newly created

The list A, B, C has the cursor at the beginning. `nextIndex == 0`, `previousIndex == -1`. There is no target yet, so `set/remove` is invalid.

### next, repeated set, then remove

`next` returns A. Two `set` calls still act on the same position, leaving the list as A2, B, C with the cursor standing after A2.

`remove` deletes that occurrence. B, C remain, and the cursor returns to the gap at the start of the sequence. A subsequent `remove` has no target.

### add then previous

`add("X")` produces X, B, C with the cursor after X. Calling `set/remove` immediately is not allowed.

`previous` returns X and moves the cursor to the beginning. From here, `set("Y")` is valid, and `remove` then deletes Y. B remains the next element.

### Two add calls in P, Q

The iterator starts at P | Q. Adding X and then Y produces P, X, Y | Q. `next` returns Q. Calling `previous` right after returns Q again; calling `previous` once more returns Y.

`remove` deletes Y rather than Q, because the target is the element from the most recent successful navigation call. After deletion, the list is P, X | Q.

### Duplicate elements

An iterator starting from the end returns the final A in A, B, A. `remove` deletes that last occurrence, leaving A, B. It does not search for another A from the beginning of the list.

### Restricted sources

`Arrays.asList` allows replacing A with A*, mutating the backing array as well. However, adding or removing elements—which changes the size—is unsupported. The iterator of `List.of` rejects even replacing A with X.

### Single-pass token editing

The order `next → set → add` or `next → remove` satisfies the state conditions, transforming the input `a`, empty string, `b` into `A`, marker, `B`, marker.

## 12. Modifying via the iterator and modifying directly via List are two different paths

When using an iterator over a standard list with modification detection, perform necessary mutations through the active iterator itself, within the bounds of what it supports.

Do not replace:

~~~java
iterator.remove();
~~~

with:

~~~java
values.remove(value);
~~~

and assume the iterator remains valid. Structurally modifying the backing source through another path can cause the iterator to detect the change and throw `ConcurrentModificationException`.

This exception is not a synchronization mechanism, nor does it guarantee that every concurrent access bug is detected immediately. Likewise, there is no guarantee that modifying through one iterator causes other iterators holding the same source to automatically adjust their state properly.

`set` usually does not change the size, but "non-structural modification" does not mean automatic thread safety or zero impact on an algorithm currently reading the source.

If multiple threads are involved, choose an appropriate synchronization model or a data structure with a suitable contract. For example, do not assume that the iterator of a snapshot-based list supports `add/set/remove` merely because its type is `ListIterator`.

### Do not use forEachRemaining for arbitrary mutations

When mutating a list element by element, an explicit loop makes it easy to accurately track the target and operation order. Do not rely on `forEachRemaining` and arbitrarily invoke mutating methods inside the callback; the iterator contract places its own restrictions on modifying the source during that traversal.

This article considers only modifications between `next/previous` calls directly controlled by the caller.

## 13. Performance: being at the right position does not mean equal cost

`ListIterator` helps express pass-based algorithms, but it does not give every list implementation the same cost characteristics:

- With `ArrayList`, inserting or removing in the middle may require shifting many elements.
- With `LinkedList`, once the iterator is positioned at the target node, link manipulation has different characteristics; reaching the initial position still carries a traversal cost.
- Replacing an element is not the same problem as resizing the list.

Do not pick `LinkedList` simply because the code calls `add/remove`, and do not claim that using an iterator automatically makes every mid-list operation constant time.

For bulk edits, consider whether building a new result list, using dedicated bulk operations, or batching changes is clearer and more efficient. Decide after identifying the data size, traversal pattern, and whether the original source instance must be preserved.

## 14. How to verify a sequence of operations yourself

After each step, record four pieces of information:

1. The contents and size of the list.
2. The cursor gap, or `nextIndex/previousIndex`.
3. The element returned by the most recent successful `next/previous`.
4. Whether any successful `add/remove` since that navigation has cleared the target.

Use data with duplicate elements to catch value-based deletion mistaken for occurrence-based deletion. Use both forward and backward directions to catch the assumption that the target is always to the left of the cursor.

Edge cases to include:

- Empty list followed by `add`.
- Cursor at the very beginning and at the very end.
- Single-element list followed by `remove` to become empty.
- `set` immediately upon creation.
- Multiple `set` calls after a single navigation.
- `remove` after `set`.
- `remove` twice in a row.
- `set/remove` immediately after `add`.
- Multiple consecutive `add` calls.
- `previous` immediately after `add`.
- `next` followed immediately by `previous`.
- Sources that support only a subset of mutation operations.

Do not experiment by overwriting real user data to observe exceptions; learning exercises should use small, freshly created lists like the program in this article.

## 15. Common mistakes

| Mistake | Cause | Proper reasoning |
| --- | --- | --- |
| Calling set right after creating the iterator | No element has been returned yet | Navigate successfully before modifying. |
| Assuming set/remove always acts on the element to the left of the cursor | Confusing the cursor with the target | Track the last `next` or `previous` call. |
| Expecting next to return the element just added | add places the new element before the cursor after the operation | Only `previous` steps back over the newly inserted element if no other step intervenes. |
| Calling set immediately after add | The previous target was invalidated | Navigate again, or call `set` before `add` if that was the intent. |
| Assuming set can be called only once | Confusing the rule for remove with set | `set` can be repeated as long as no `add/remove` has invalidated the target. |
| Calling remove consecutively without navigating | The target occurrence has already been deleted | Retrieve the next or previous element before removing again. |
| Using list.remove(value) instead of iterator.remove | Changes both the semantics and the modification path on the source | Remove the exact occurrence through the active iterator. |
| Assuming any ListIterator supports add/set/remove | The mutation operations are optional | Check the capabilities of the specific list and iterator. |
| Manually adjusting an external index variable after iterator.remove | Managing two progress models easily falls out of sync | Let the iterator manage traversal position; use external indices only when truly necessary. |
| Treating iterator mutation support as a guarantee of multi-threaded safety | Confusing traversal state with synchronization | Design concurrent access according to a dedicated concurrency contract. |

## 16. Practice

1. With A, B, C and the cursor at `A | B C`, construct two navigation sequences that end at the same cursor position but have different `set` targets.
2. Predict the outcome of: `add("X")`, `add("Y")`, `previous()`, `remove()`. Write down the list and cursor after each step.
3. Retrieve an element, call `set` twice, and then call `remove`. Explain why this is valid whereas calling `remove` twice is invalid.
4. Start from the end of A, B, A and remove the A returned by `previous`. Compare this with the meaning of value-based `remove` on `List`.
5. Write an algorithm that replaces non-empty strings with their normalized form, removes empty strings, and inserts a label after each kept string. Verify whether the inserted label is revisited during forward traversal.
6. Run the same idea on `ArrayList`, `LinkedList`, `Arrays.asList`, and `List.of`; separate operation capability from performance cost and valid iterator state.
7. Write test cases for adding into an empty list, removing the sole element, and alternating `next/previous` directions.

Before calling a mutation operation, determine whether it acts on the **cursor gap** or the **last returned occurrence**. Then verify whether the source supports the operation and whether the current state is valid. These two checks explain most of the behavior of `add`, `set`, and `remove`.
