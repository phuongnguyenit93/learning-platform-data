# IndexOutOfBoundsException, NoSuchElementException, and IllegalStateException

## 1. Three different questions before a collection operation

On the same empty list, `list.get(0)`, `list.iterator().next()`, and `list.iterator().remove()` can fail in three different ways. They should not be lumped together into a single generic failure called "the collection has no data."

Separate the three questions:

1. **Is the address valid?** An index must fall within the range accepted by the method. Violating the index range leads to `IndexOutOfBoundsException`.
2. **Is there an element to retrieve?** A method that requires retrieving the next element or the first/last element, when no such element exists, can throw `NoSuchElementException`.
3. **Is the operation allowed right now?** The preceding call sequence or current state does not yet permit the operation. Typical examples are calling `Iterator.remove()` when there is no element just returned, or calling `add` on a full bounded queue: `IllegalStateException`.

The exception class name is a clue. The contract of **the exact method on the exact object type** determines how to fix it.

| Illustrative call | What is being requested | Failure to distinguish |
| --- | --- | --- |
| `new ArrayList<String>().get(0)` | Read the element at index 0 | No valid element index exists |
| Calling `next()` on an iterator of an empty List | Return the next element | No more elements left to return |
| Calling `remove()` before `next()` on an iterator that supports removal | Remove the element just returned by the iterator | No such element exists in the cursor state yet |
| Calling `add(value)` on a full `ArrayBlockingQueue` | Immediately insert a new element | Capacity state does not allow insertion |

This article uses Java 17+ and standard collections. The experiments run single-threaded to isolate contract errors from contention across threads.

## 2. IndexOutOfBoundsException: distinguishing element indices from insertion positions

### 2.1. There are n elements, but n + 1 cursor positions

For a list with `n = size()` elements:

- The index of an **existing element** ranges from `0` to `n - 1`.
- An **insertion position** or `ListIterator` initialization position ranges from `0` to `n`.

These two ranges differ at the right boundary:

```text
List:                A       B       C
Element index:       0       1       2
Insertion position: 0       1       2       3
size() = 3

get(2)          -> reads C
get(3)          -> out of element range
add(3, D)       -> inserts D at the end, valid position
listIterator(3) -> cursor at the end; next() has no remaining elements
```

Do not interpret `size()` as the "last index." It is the number of elements, and in applicable methods it is also the position immediately after the last element.

| List method | Valid range of the index argument |
| --- | --- |
| `get(index)` | `0 <= index < size()` |
| `set(index, value)` | `0 <= index < size()` |
| `remove(index)` | `0 <= index < size()` |
| `add(index, value)` | `0 <= index <= size()` |
| `listIterator(index)` | `0 <= index <= size()` |

`set(size(), value)` is not a way to append to the end: `set` replaces an existing element. To insert, use `add` to match the intended operation. The index ranges are specified in the [Java 17 List contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

For an empty List, no index is valid for `get`, `set`, or indexed removal. However, insertion position `0` is still valid if the List supports adding elements.

### 2.2. View indices are measured within the view itself

A sublist uses the half-open convention `[fromIndex, toIndex)`: starting inclusively at `fromIndex` and stopping before `toIndex`.

```text
base = [A, B, C, D]
part = base.subList(1, 3) = [B, C]

part.get(0) -> B
part.get(1) -> C
part.get(2) -> out of part's range, even though base still has index 2
```

`subList(size(), size())` creates an empty view at the end. An empty view still has no element at index `0`.

Keep the endpoints within the list's range, with the left endpoint not greater than the right endpoint. Do not turn an index test into a test of multiple invalid endpoints simultaneously and then infer a fixed exception precedence order for all implementations. Views also have rules tying them to their backing source; a view invalidated by structurally modifying the backing source through another path is a separate issue and must not be handled by guessing index adjustments.

### 2.3. Common causes

**Off-by-one operator in loop conditions.** The following snippet fails when it reaches `i == size()`:

```java
// Incorrect illustrative snippet; values is an existing List in the method.
for (int i = 0; i <= values.size(); i++) {
    System.out.println(values.get(i));
}
```

If you are only reading and do not need the index, an enhanced `for` loop expresses the intent directly. If you need the index, use `i < values.size()` under appropriate conditions, and clearly establish whether the list is modified during traversal.

**Retrieving the last element when empty.** `get(size() - 1)` on an empty List becomes `get(-1)`. The formula works when elements are present, but does not handle the empty case by itself.

**Using a search result while ignoring the not-found case.**

```java
// Illustrative snippet inside a method; names supports the required operation.
int index = names.indexOf("An");
if (index >= 0) {
    names.set(index, "An Nguyen");
}
```

When no match is found, `indexOf` returns `-1`; that value is not a valid index for reading or replacing. Not finding a match can be a normal outcome of the problem domain. Handle it before performing an index-based operation.

**Saving an index and then mutating the list.** Removing an element shifts subsequent elements to the left. An index that once pointed to one item may point to a different item or fall out of bounds after a mutation. When removing during traversal, choose an iterator that supports removal or a well-defined indexing strategy. Simply changing `<=` to `<` does not fix mismatches in element identity.

## 3. remove(int) and remove(Object): same name, two contracts

On a `List<Integer>`, the following call does **not** mean removing the number `20`:

```java
// Illustrative snippet inside a method; requires importing java.util.List and ArrayList.
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
numbers.remove(20); // Selects remove(int index): requests removing index 20.
```

The list only has three elements, so index `20` is invalid. If you want to remove by value:

```java
boolean removed = numbers.remove(Integer.valueOf(20));
```

Here the argument has type `Integer`, so the call selects `remove(Object)`: it removes the first occurrence equal to that value if present, and returns a boolean result.

What needs testing is **which method overload is actually selected**, not just the data stored:

- `remove(0)` on a List removes by index.
- `remove(Integer.valueOf(0))` on a `List<Integer>` removes by value.
- `Queue.remove()` with no arguments retrieves and removes the head element.
- `queue.remove(value)` is a different call that finds and removes an element by value.

A stack trace containing the word `remove` is not enough to classify the bug. Check the method signature and the static type of the argument.

## 4. NoSuchElementException: an element is required to be returned, but none exists

### 4.1. Iterator.next is not a probe to check for data

`Iterator.next()` must return the next element. If the iteration has no more elements, it throws `NoSuchElementException`. `hasNext()` is used to check whether traversal can continue under valid iterator usage conditions. [Iterator contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

Standard reading pattern:

```java
// Pattern applied inside a method; iterator was created from an appropriate source.
while (iterator.hasNext()) {
    Object value = iterator.next();
    System.out.println(value);
}
```

An easy-to-miss bug is calling `next()` twice per check:

```java
// Wrong: a single hasNext call only confirms that at least one element remains.
while (iterator.hasNext()) {
    System.out.println(iterator.next());
    System.out.println(iterator.next()); // may advance past the end when only one element remains
}
```

With two elements, this snippet may finish without error; with one or three elements, the second `next()` on the final iteration has no data left. Therefore, testing only with an even-sized input can mask the bug.

With `ListIterator`, `previous()` has a symmetric situation: when the cursor is at the beginning, there is no preceding element. `hasPrevious()` checks the backward direction. A valid cursor at the end has no next element, but may have a previous element.

### 4.2. Queue and Deque have two method families at the endpoints

Java provides pairs of methods so authors can choose how to express the empty case:

| Purpose | Requires an element to exist | Returns a special value when empty |
| --- | --- | --- |
| Read Queue head | `element()` throws `NoSuchElementException` | `peek()` returns `null` |
| Retrieve and remove Queue head | `remove()` throws `NoSuchElementException` | `poll()` returns `null` |
| Read Deque head | `getFirst()` throws `NoSuchElementException` | `peekFirst()` returns `null` |
| Read Deque tail | `getLast()` throws `NoSuchElementException` | `peekLast()` returns `null` |
| Retrieve and remove Deque head | `removeFirst()` throws `NoSuchElementException` | `pollFirst()` returns `null` |
| Retrieve and remove Deque tail | `removeLast()` throws `NoSuchElementException` | `pollLast()` returns `null` |

`Deque.pop()` is equivalent to retrieving and removing the head via `removeFirst()`, so popping from an empty stack also throws `NoSuchElementException`. This is the published behavior of [Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html) and [Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html).

Choose the method according to domain semantics:

- If emptiness is normal—for instance, there is no work item to process in this turn—`poll` and checking the result usually expresses the intent better.
- If the program has previously established a precondition that an element must exist, `remove()` or `element()` can help detect when that precondition is broken.
- Do not blindly replace every call with `poll` and ignore the return value. That may merely turn a contract violation into silently lost data.

### 4.3. Null values must be handled before use

In the full example below, the queues use `ArrayDeque` or `ArrayBlockingQueue`, neither of which accepts `null` elements. Consequently, a `null` returned from `poll` can be used unambiguously to detect emptiness.

Do not assume every `Queue` implementation shares the same null policy. A queue that permits `null` elements can make the special return value indistinguishable from actual data. Define your data policy right at the API boundary.

The following snippet can throw a `NullPointerException` due to autounboxing, even though it avoids `NoSuchElementException`:

```java
// Illustrative snippet that fails when the queue is empty; queue has type Queue<Integer>.
int value = queue.poll();
```

Read into an `Integer`, check for `null`, and only then use the value. Changing the method must go hand in hand with handling its return contract.

## 5. IllegalStateException on iterators: call sequence violations

### 5.1. remove deletes the most recently returned element

On an iterator that supports removal, `remove()` takes no arguments because it is bound to **the element most recently returned by that same iterator via next()**.

Basic rules:

1. Call `next()` successfully to establish a just-returned element.
2. You may remove that element with `remove()` at most once.
3. To remove another element, you must call `next()` successfully again.

```text
Create iterator
    remove is not yet valid
        |
        | successful next
        v
Has a just-returned element
    remove is valid once
        |
        | successful remove
        v
No new element to remove yet
    immediate second remove -> IllegalStateException
```

`hasNext()` only checks whether traversal can proceed; it does not establish a "just-returned element." Therefore, calling `hasNext()` and then `remove()` immediately after creating an iterator is still an invalid sequence.

Another detail: after `next()` returns the final element, `hasNext()` may be `false`, but the right to remove that final just-returned element still holds if it has not been removed yet. "No next element remains" and "no just-returned element is available to remove" are two distinct states.

These rules apply within the contract of an iterator that permits modification. An iterator that does not support `remove` may throw `UnsupportedOperationException`; calling `next` does not turn a forbidden operation into a supported one. Do not construct a test case that both violates state and lacks removal support and then use it to claim which exception always wins.

### 5.2. ListIterator: cursor position differs from the just-returned element

A `ListIterator` positions its cursor **between elements**, whereas `set` and `remove` act on the element most recently returned by `next` or `previous`. There is no "current element" automatically available simply because a cursor was created.

For a `ListIterator` that supports the corresponding modification operations:

| Sequence | What to understand |
| --- | --- |
| Newly created, has not moved via `next`/`previous` | `set` and `remove` are not yet valid |
| Just moved via `next` or `previous` | May `set` the just-returned element; may `remove` if no `add`/`remove` occurred since that move |
| Calling `set` multiple times after a single move | Permitted as long as no `add`/`remove` intervened |
| After a successful `remove` | An immediate subsequent `set` or `remove` is not valid |
| After a successful `add` | Must move again via `next`/`previous` before calling `set`/`remove` |
| Calling `add` on a newly created cursor | Does not require a prior `next`/`previous` call |

According to the [ListIterator contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html), `add` inserts before the element that would be returned by `next()`, if any. After adding, `previous()` returns the newly added element, whereas a call to `next()` advances to the element that originally lay after the insertion point.

For example:

```text
values = [A, C], cursor at the start
add(B)   -> values = [B, A, C], cursor lies between B and A
set(X)   -> invalid: add just cleared the condition required for set/remove
next()   -> returns A
set(X)   -> values = [B, X, C]
set(Y)   -> values = [B, Y, C], still valid
remove() -> values = [B, C]
set(Z)   -> invalid after remove
```

Test **sequences of operations**, not just individual methods in isolation. Two `set` calls with the exact same argument can produce different outcomes solely because an `add` did or did not precede them.

## 6. IllegalStateException from a full queue differs from iterator errors

A bounded-capacity queue has a different kind of state: space available or full. With `ArrayBlockingQueue`, calling `add(value)` on a full queue throws `IllegalStateException`; the non-blocking `offer(value)` returns `false` when no space remains. [ArrayBlockingQueue documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

```text
Capacity = 1, queue initially empty
add(A)   -> true,  contents [A]
add(B)   -> IllegalStateException because full
offer(B) -> false, contents still [A]
poll()   -> A, contents []
offer(B) -> true, contents [B]
```

This is not a "forgot to call next" bug. It uses the same exception class, but under completely different usage conditions.

Choose the policy that matches how work is accepted:

- `add`: failure to accept the item is an error condition reported via an exception.
- `offer`: inability to accept immediately is a boolean outcome that the caller must handle.
- Blocking methods such as `put` and `take` carry different contracts regarding waiting and thread interruption. Do not substitute them just to make the exception disappear; doing so can cause the program to block indefinitely if no other party changes the queue state.

The program below uses only non-blocking operations and spawns no extra threads. When receiving `false` from `offer`, an application still has to decide whether to reject the work, store it elsewhere, retry according to a policy, or notify the caller. A boolean return value does not make that decision for you.

## 7. Java 17+ program verifying the contracts

Save the code below as **ExceptionContractsDemo.java**. The program uses `AssertionError` to halt if an expectation fails; it does not require `-ea`, JUnit, or external libraries.

Each exception test operation is isolated in a short lambda. The helper accepts exceptions of the requested type, including subclasses, without swallowing an unrelated `RuntimeException`. Data sources are created separately per group so that the sequence in one group does not corrupt the input data of another.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.Objects;
import java.util.Queue;
import java.util.concurrent.ArrayBlockingQueue;

public class ExceptionContractsDemo {
    private static int passed;

    private static void checkEquals(String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        passed++;
    }

    private static void expectThrows(
            String label, Class<? extends RuntimeException> type, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError(label + ": unexpected exception", ex);
            }
            passed++;
            return;
        }
        throw new AssertionError(label + ": expected " + type.getSimpleName());
    }

    private static void checkIndices() {
        List<String> empty = new ArrayList<>();
        expectThrows("empty get", IndexOutOfBoundsException.class, () -> empty.get(0));
        expectThrows("empty set", IndexOutOfBoundsException.class, () -> empty.set(0, "X"));
        expectThrows("empty indexed remove", IndexOutOfBoundsException.class,
                () -> empty.remove(0));
        empty.add(0, "A");
        checkEquals("empty insertion position", List.of("A"), empty);

        List<String> values = new ArrayList<>(List.of("B", "A", "C"));
        expectThrows("negative element index", IndexOutOfBoundsException.class,
                () -> values.get(-1));
        expectThrows("size is not an element index", IndexOutOfBoundsException.class,
                () -> values.get(values.size()));
        expectThrows("set cannot append", IndexOutOfBoundsException.class,
                () -> values.set(values.size(), "D"));
        expectThrows("indexed remove at size", IndexOutOfBoundsException.class,
                () -> values.remove(values.size()));
        checkEquals("last element", "C", values.get(values.size() - 1));
        values.add(values.size(), "D");
        checkEquals("insert at end", List.of("B", "A", "C", "D"), values);
        expectThrows("beyond insertion range", IndexOutOfBoundsException.class,
                () -> values.add(values.size() + 1, "E"));
        checkEquals("half-open slice", List.of("A", "C"), values.subList(1, 3));
        checkEquals("empty slice at end", List.of(),
                values.subList(values.size(), values.size()));

        List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
        expectThrows("remove int selects index", IndexOutOfBoundsException.class,
                () -> numbers.remove(20));
        checkEquals("failed indexed remove preserves values", List.of(10, 20, 30), numbers);
        checkEquals("remove Integer selects value", true, numbers.remove(Integer.valueOf(20)));
        checkEquals("value removed", List.of(10, 30), numbers);
        checkEquals("absent value", false, numbers.remove(Integer.valueOf(99)));
        System.out.println("indices=PASS");
    }

    private static void checkIterator() {
        List<String> values = new ArrayList<>(List.of("A", "B"));
        Iterator<String> cursor = values.iterator();
        expectThrows("remove before next", IllegalStateException.class, cursor::remove);
        checkEquals("first next", "A", cursor.next());
        cursor.remove();
        checkEquals("first removal", List.of("B"), values);
        expectThrows("double remove", IllegalStateException.class, cursor::remove);
        checkEquals("last next", "B", cursor.next());
        checkEquals("no next element", false, cursor.hasNext());
        cursor.remove();
        checkEquals("last returned element can still be removed", List.of(), values);
        expectThrows("exhausted next", java.util.NoSuchElementException.class, cursor::next);

        Iterator<String> readOnly = List.of("A").iterator();
        checkEquals("read-only iterator can read", "A", readOnly.next());
        expectThrows("unsupported remove after valid next", UnsupportedOperationException.class,
                readOnly::remove);
        System.out.println("iterator=PASS");
    }

    private static void checkListIterator() {
        List<String> values = new ArrayList<>(List.of("A", "C"));
        ListIterator<String> cursor = values.listIterator();
        expectThrows("no previous at start", java.util.NoSuchElementException.class,
                cursor::previous);
        expectThrows("set before movement", IllegalStateException.class,
                () -> cursor.set("X"));
        expectThrows("remove before movement", IllegalStateException.class, cursor::remove);

        cursor.add("B");
        checkEquals("add without prior movement", List.of("B", "A", "C"), values);
        expectThrows("set immediately after add", IllegalStateException.class,
                () -> cursor.set("X"));
        expectThrows("remove immediately after add", IllegalStateException.class, cursor::remove);
        checkEquals("next after add", "A", cursor.next());
        cursor.set("X");
        cursor.set("Y");
        checkEquals("repeated set is allowed", List.of("B", "Y", "C"), values);
        cursor.remove();
        checkEquals("remove after set", List.of("B", "C"), values);
        expectThrows("set after remove", IllegalStateException.class, () -> cursor.set("X"));
        expectThrows("remove twice", IllegalStateException.class, cursor::remove);

        checkEquals("next after removal", "C", cursor.next());
        cursor.set("Z");
        checkEquals("replace last returned element", List.of("B", "Z"), values);
        checkEquals("at end", false, cursor.hasNext());
        checkEquals("previous at end", "Z", cursor.previous());
        cursor.remove();
        checkEquals("remove after previous", List.of("B"), values);

        ListIterator<String> end = values.listIterator(values.size());
        checkEquals("end position is valid", false, end.hasNext());
        expectThrows("next at end", java.util.NoSuchElementException.class, end::next);
        expectThrows("negative iterator position", IndexOutOfBoundsException.class,
                () -> values.listIterator(-1));
        expectThrows("too-large iterator position", IndexOutOfBoundsException.class,
                () -> values.listIterator(values.size() + 1));
        System.out.println("listIterator=PASS");
    }

    private static void checkEmptyEndpoints() {
        Queue<String> queue = new ArrayDeque<>();
        expectThrows("empty queue remove", java.util.NoSuchElementException.class,
                () -> queue.remove());
        expectThrows("empty queue element", java.util.NoSuchElementException.class,
                queue::element);
        checkEquals("empty poll", null, queue.poll());
        checkEquals("empty peek", null, queue.peek());
        checkEquals("remove absent value has another contract", false, queue.remove("missing"));
        queue.add("A");
        checkEquals("element reads head", "A", queue.element());
        checkEquals("element does not remove", 1, queue.size());
        checkEquals("remove returns head", "A", queue.remove());
        checkEquals("queue emptied", true, queue.isEmpty());

        Deque<String> stack = new ArrayDeque<>();
        expectThrows("empty getFirst", java.util.NoSuchElementException.class, stack::getFirst);
        expectThrows("empty getLast", java.util.NoSuchElementException.class, stack::getLast);
        expectThrows("empty removeFirst", java.util.NoSuchElementException.class,
                stack::removeFirst);
        expectThrows("empty removeLast", java.util.NoSuchElementException.class, stack::removeLast);
        expectThrows("empty pop", java.util.NoSuchElementException.class, stack::pop);
        checkEquals("empty pollFirst", null, stack.pollFirst());
        checkEquals("empty pollLast", null, stack.pollLast());
        checkEquals("empty peekFirst", null, stack.peekFirst());
        checkEquals("empty peekLast", null, stack.peekLast());
        stack.push("A");
        stack.push("B");
        checkEquals("LIFO first pop", "B", stack.pop());
        checkEquals("LIFO second pop", "A", stack.pop());
        checkEquals("stack emptied", true, stack.isEmpty());
        System.out.println("empty endpoints=PASS");
    }

    private static void checkBoundedQueue() {
        Queue<String> queue = new ArrayBlockingQueue<>(1);
        checkEquals("first add", true, queue.add("A"));
        expectThrows("add to full queue", IllegalStateException.class, () -> queue.add("B"));
        checkEquals("offer to full queue", false, queue.offer("B"));
        checkEquals("failed insertions preserve queue", List.of("A"), new ArrayList<>(queue));
        checkEquals("make room", "A", queue.poll());
        checkEquals("offer after space becomes available", true, queue.offer("B"));
        checkEquals("read new head", "B", queue.element());
        checkEquals("remove new head", "B", queue.remove());
        checkEquals("poll after draining", null, queue.poll());
        System.out.println("bounded queue=PASS");
    }

    public static void main(String[] args) {
        checkIndices();
        checkIterator();
        checkListIterator();
        checkEmptyEndpoints();
        checkBoundedQueue();
        System.out.println("PASS: " + passed + " checks");
    }
}
```

Compile and run in the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ExceptionContractsDemo.java
java ExceptionContractsDemo
```

Stdout when all checks pass:

```text
indices=PASS
iterator=PASS
listIterator=PASS
empty endpoints=PASS
bounded queue=PASS
PASS: 78 checks
```

The program was compiled with `--release 17` and run on OpenJDK 24.0.2. `--release 17` enforces the target language level and API surface; it does not mean the runtime process uses a JDK 17 JVM.

### 7.1. Why verify data after the operations?

Checking only whether an exception was thrown does not sufficiently protect domain semantics. The program also confirms that:

- Attempting to remove index 20 does not turn into removing value 20.
- Removing by value actually removes the right element, and returns `false` when not found.
- Removing via an iterator updates the list; the next removal is valid only after advancing again.
- `ListIterator` allows replacing the same element multiple times, whereas `add`/`remove` changes the preconditions for `set`/`remove`.
- `element` does not remove, while `remove()` and `poll()` retrieve and remove the queue head.
- Two pops yield the proper stack order.
- Failing to insert into a full queue does not silently replace element A with B.
- Freeing one slot allows a subsequent insertion to succeed.

The state assertions here are tied to the specific classes and operations instantiated. Do not infer an automatic rollback guarantee for arbitrary bulk operations or custom collections.

### 7.2. Limits of the experiment

This is a single-threaded contract check over small data sets, not a concurrency test or a performance benchmark. The `ArrayList` instances in the example support modification operations; `List.of` appears only in the read-only iterator comparison case and for constructing expected values.

Do not assume that every misuse must throw one of the exact three exceptions in the title. Type mismatches, nulls, unsupported operations, or out-of-policy backing modifications can lead to other exception types. Design each test case around **a single clear violation condition**.

## 8. Debugging workflow: inspect the method, inputs, and state

### 8.1. When encountering IndexOutOfBoundsException

Record:

1. Is the method an indexed `get`/`set`/`remove`, a positional `add`, or a cursor initialization?
2. What were the index value at the moment of the call and the list's size at that moment?
3. Is the index measured against the original list or a smaller view?
4. Did the index come from a loop, `indexOf`, user input, or a value saved before a mutation?
5. For `remove`, which overload was selected?

Fix the root cause that produced the wrong address. Do not mechanically clamp every index into the valid range: turning index 100 into the last element can cause the program to silently corrupt the wrong data without reporting an error.

### 8.2. When encountering NoSuchElementException

Identify the exact direction and observation point:

- Has the iterator already been exhausted, or was `next` accidentally called twice?
- Is the `ListIterator` at the beginning or end, and is it moving forward or backward?
- Is the `Queue`/`Deque` genuinely empty, or was the element already consumed by another path?
- Does the contract permit emptiness, and should the code use an exception-throwing method or a special-value method?

If missing data is a normal situation, express it explicitly. If it violates a required invariant, preserve the diagnostic information needed to locate where the element was lost. Do not catch the exception and fabricate a dummy default value that the domain does not allow.

### 8.3. When encountering IllegalStateException

The exception name alone does not describe the state sufficiently. For an iterator, log the relevant `next/previous/add/set/remove` sequence. For a bounded queue, log its capacity and the outcomes of prior insertion/removal calls.

A small operation log like the following is often much more useful than printing `size` alone:

```text
create iterator
next -> A
remove -> succeeded
remove -> IllegalStateException
```

The list's size at the end may still be greater than 0, but that does not grant permission to call `remove` a second time on the same iterator. The violated condition is the call sequence, not whether data remains.

Do not catch `IllegalStateException` across an entire large method and assume "the queue is full." Another call inside the method might be the actual source of the error. Narrow the scope of the operation and read the stack trace.

## 9. Pre-operation checks do not automatically create atomicity

Within a single thread and when no other code interferes with the backing collection, checking an index or calling `hasNext` helps select the right operation. When state can change between two calls, a pre-check is not enough.

An illustrative example of an error-prone pattern:

```java
// Illustrative snippet: two separate calls, not a single transaction.
if (!queue.isEmpty()) {
    String value = queue.remove();
    System.out.println(value);
}
```

When multiple consumers take elements from a queue, the queue can become empty right after the `isEmpty` check. If the chosen concurrent queue API provides a safe retrieval operation and the requirements allow an empty outcome, call `poll()` directly and handle the return value of that call. Choosing a concurrent collection or synchronizing the proper scope remains a separate requirement; changing `remove` to `poll` does not make an unsynchronized shared `ArrayDeque` thread-safe.

Similarly, checking `index < list.size()` before calling `get(index)` does not protect a `List` being modified concurrently without synchronization. Address access control to the shared resource rather than using a loop that catches `IndexOutOfBoundsException` and retries as a substitute for synchronization.

With iterators, modifying the backing collection outside the path permitted by the contract can also lead to `ConcurrentModificationException` or unspecified behavior. Guarantees around `hasNext`/`next` must be understood under valid iterator usage conditions.

## 10. Designing test cases with discriminative power

### 10.1. Test both sides of the boundary

For a list of size `n`, pick points such as `-1`, `0`, `n - 1`, `n`, and `n + 1`, but evaluate the meaning of each point against the actual `n`:

- When `n = 0`, `n - 1` is also `-1`; there is no "valid last element" case.
- When `n = 1`, the only element index is `0`, while valid insertion positions include both `0` and `1`.
- For larger `n`, `index = n` clearly distinguishes read/replace operations from insertion operations.

Do not count duplicate values in a template table as evidence that you have tested an additional region of behavior.

### 10.2. Test state transitions, not just initial states

| Group | Insufficient test case | Important supplementary test cases |
| --- | --- | --- |
| Indices | Only testing `get(0)` on a non-empty List | Empty list, negative index, `index = size`, and `add` at `size` |
| Iterator | Only testing `next` while data remains | Exhausted iterator; `remove` before `next`; double `remove`; `remove` after the final `next` |
| ListIterator | Only testing `set` immediately after `next` | `set` before moving, after `add`/`remove`, repeated `set`, and `remove` after `previous` |
| Queue | Only testing retrieval from a non-empty queue | `remove`/`poll` and `element`/`peek` pairs when empty |
| Capacity | Only testing `add` when space is available | Failing `add`, `offer` returning `false`, draining an item and inserting again |
| Stack | Only testing `pop` once | Empty, one element, two elements, and LIFO ordering |

With `ListIterator`, observing `nextIndex()` and `previousIndex()` is also helpful for diagnosing cursor position, but knowing the index does not change the "has a just-returned element" requirement for `set`/`remove`.

### 10.3. Do not set expectations stronger than the contract

In application testing:

- Catch the exception only around the exact call under test, after valid test data has already been prepared.
- When a contract specifies `IndexOutOfBoundsException`, do not require an internal subclass or a specific message string unless your own application's API explicitly commits to that.
- Do not rely on stack trace line numbers or internal iterator class names; they can change across JDK versions.
- Do not mix an invalid index, an unsupported operation, and an invalid state in the same test case and then infer a universal validation order across all implementations.
- Verify the contents, positions, or processing counts after valid operations, rather than merely checking that the program "did not throw an error."
- Do not treat a single error-free run as proof that a concurrently mutated backing collection is thread-safe.

In JUnit Jupiter, the corresponding idea is to use `assertThrows` around a short lambda and separate assertions for the post-operation state. The demonstration program in this article uses self-checking helpers so it can run standalone without requiring a JUnit setup.

## 11. Recognizing related errors with different root causes

All three exceptions in this article are unchecked exceptions that do not require declaration or catching as checked exceptions. That does not mean a program should ignore them; many cases reflect API misuse that should be fixed at the source.

| Situation | Issue type to consider |
| --- | --- |
| List index falls outside the method's valid range | `IndexOutOfBoundsException` |
| `Iterator.next` or `Queue.remove` has no element to return | `NoSuchElementException` |
| `Iterator.remove` called out of sequence; `add` on a full `ArrayBlockingQueue` | `IllegalStateException` |
| Calling `add` on `List.of` or `remove` via an iterator that does not support modification | `UnsupportedOperationException` |
| Modifying the backing source outside a fail-fast iterator's policy | `ConcurrentModificationException` may detect the violation |
| Autounboxing a `null` result from `poll` | `NullPointerException` |

This table is a guide for the situations discussed, not an exhaustive rule excluding all other failures. When an object is misused across multiple conditions at once, read the specific contract instead of guessing an exception by intuition.

A good fix should answer two questions: which precondition must hold before the operation, and who is responsible for maintaining that precondition. The caller may need to validate input; the owner of the collection may need to expose a more appropriate API; the algorithm may need to change how it traverses or how it handles empty/full states.

## 12. Self-check and practice

### Question 1: A List has three elements; why is add(3, value) valid while set(3, value) is not?

`add` uses an insertion position, which includes the position immediately after the last element. `set` requires an existing element; valid element indices only go up to 2.

### Question 2: Does hasNext returning false mean remove must throw IllegalStateException?

No. If `next` just returned the last element and that element has not been removed yet, `remove` can still be valid on an iterator that supports removal. `hasNext` describes the next element, whereas `remove` depends on the element already returned.

### Question 3: Is changing Queue.remove to poll enough to fix the bug?

Not by itself. You must decide whether an empty queue is valid in that context and handle `null`. You must also respect the collection's concurrency policy; swapping two method names does not replace proper shared-resource access design.

### Question 4: Can a ListIterator call set twice after a single next call?

Yes, if it supports `set` and no `add` or `remove` has intervened. A `set` call does not consume replacement permission the way `remove` clears the condition required for another removal.

### Question 5: Is IllegalStateException always related to iterators?

No. A full bounded queue is another example. You need to inspect the method throwing the exception and the state of that target object.

### Practice exercises

1. Add test cases for `get`/`set`/`add` on a single-element List; document the element index range and the insertion position range separately.
2. Write a test proving that `remove(1)` and `remove(Integer.valueOf(1))` can remove two different things given the same initial data.
3. Track `nextIndex()` before and after the `ListIterator` sequence: `add`, `next`, `set`, `remove`, `previous`. Predict the list contents after each step before running it.
4. Create a two-element deque and compare `getFirst`, `peekFirst`, `removeFirst`, and `pollFirst`; verify which operations preserve the size.
5. With a queue of capacity 2, write a test case that fills it, removes one element, and inserts again. Compare the boolean results, exceptions, and element order.
6. Reproduce the bug of calling `next` twice inside a `while` loop, test it with inputs of 0, 1, 2, and 3 elements, and then fix it so each element is processed exactly once.
7. Design one function where "empty is normal" and one function where "an element must exist." Clearly choose the appropriate API and failure outcome for each function.

The goal is to see the address, available element, and operation sequence as three distinct preconditions. When a precondition fails, fix how that precondition is established or maintained, and then re-test both the return value and the resulting data state.
